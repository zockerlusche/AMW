"""Nachgestellter OpenID-Connect-Anbieter für die Tests der Firmen-Anmeldung (Stufe R2) – verhält sich wie Microsoft
Entra ID bzw. Keycloak an den Stellen, die die Seite benutzt: Beschreibung (.well-known), Anmelden (Code mit state),
Token (prüft PKCE, Rückkehr-Adresse und Client-Geheimnis bzw. signierte Bestätigung mit Zertifikat), Schlüssel (JWKS).
Ohne echtes Konto. Was der „Benutzer“ beim Anbieter ist und welche Fehler der Anbieter macht, stellt der Test ein."""
import base64
import datetime
import hashlib
import json
import secrets
import threading
import time
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.x509.oid import NameOID


def b64url(roh):
    return base64.urlsafe_b64encode(roh).rstrip(b"=").decode("ascii")


def b64url_roh(s):
    return base64.urlsafe_b64decode(s + "=" * (-len(s) % 4))


def schluessel():
    return rsa.generate_private_key(public_exponent=65537, key_size=2048)


def jwt(privat, kopf, inhalt):
    roh = b64url(json.dumps(kopf).encode()) + "." + b64url(json.dumps(inhalt).encode())
    return roh + "." + b64url(privat.sign(roh.encode(), padding.PKCS1v15(), hashes.SHA256()))


def zertifikat(privat, name="AMW Test"):
    """Selbst signiertes Zertifikat wie aus dem Portal (PEM) – für die Anmeldung der Seite mit Zertifikat."""
    n = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, name)])
    jetzt = datetime.datetime.now(datetime.timezone.utc)
    z = (x509.CertificateBuilder().subject_name(n).issuer_name(n).public_key(privat.public_key()).serial_number(x509.random_serial_number())
         .not_valid_before(jetzt - datetime.timedelta(days=1)).not_valid_after(jetzt + datetime.timedelta(days=30)).sign(privat, hashes.SHA256()))
    return (z.public_bytes(serialization.Encoding.PEM).decode(),
            privat.private_bytes(serialization.Encoding.PEM, serialization.PrivateFormat.PKCS8, serialization.NoEncryption()).decode())


class Anbieter:
    def __init__(self, client_id="amw-test", geheimnis="geheim-0123456789", zert_pem=None):
        self.client_id, self.geheimnis = client_id, geheimnis
        self.zert_pem = zert_pem                    # gesetzt: die Seite muss sich mit Zertifikat ausweisen
        self.privat = schluessel()
        self.kid = "k1"
        self.benutzer = {"sub": "sub-marie", "email": "Marie@Firma.example", "name": "Marie Muster"}
        self.fehler = {}                            # z. B. {"iss": "…"}, {"aud": "…"}, {"exp": -3600}, {"nonce": "x"}, {"fremd_signiert": True}, {"alg": "none"}
        self.codes = {}
        self.anfragen = []                          # (Weg, Angaben) – für Prüfungen im Test
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.port = self.server.server_address[1]
        self.aussteller = f"http://127.0.0.1:{self.port}/tenant-1/v2.0"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def stop(self):
        self.server.shutdown()
        self.server.server_close()

    def jwks(self):
        z = self.privat.public_key().public_numbers()
        laenge = (z.n.bit_length() + 7) // 8
        return {"keys": [{"kty": "RSA", "use": "sig", "kid": self.kid, "alg": "RS256", "n": b64url(z.n.to_bytes(laenge, "big")),
                          "e": b64url(z.e.to_bytes(3, "big"))}]}

    def id_token(self, nonce):
        f = self.fehler
        t = int(time.time())
        inhalt = {"iss": f.get("iss", self.aussteller), "aud": f.get("aud", self.client_id), "iat": t, "nbf": t,
                  "exp": t + f.get("exp", 3600), "nonce": f.get("nonce", nonce), "tid": "tenant-1", "ver": "2.0", **self.benutzer}
        if f.get("ohne_email"):
            inhalt.pop("email", None)
        kopf = {"alg": "RS256", "typ": "JWT", "kid": self.kid}
        if f.get("alg") == "none":
            return b64url(json.dumps({"alg": "none"}).encode()) + "." + b64url(json.dumps(inhalt).encode()) + "."
        return jwt(schluessel() if f.get("fremd_signiert") else self.privat, kopf, inhalt)

    def _ausweis_ok(self, form, token_url):
        if self.zert_pem is None:
            return form.get("client_id") == self.client_id and secrets.compare_digest(form.get("client_secret", ""), self.geheimnis)
        if form.get("client_assertion_type") != "urn:ietf:params:oauth:client-assertion-type:jwt-bearer":
            return False
        kopf_s, inhalt_s, sig = form.get("client_assertion", "..").split(".")
        kopf, inhalt = json.loads(b64url_roh(kopf_s)), json.loads(b64url_roh(inhalt_s))
        z = x509.load_pem_x509_certificate(self.zert_pem.encode())
        der = z.public_bytes(serialization.Encoding.DER)
        if kopf.get("x5t") != b64url(hashlib.sha1(der).digest()) or kopf.get("x5t#S256") != b64url(hashlib.sha256(der).digest()):
            return False
        try:
            z.public_key().verify(b64url_roh(sig), f"{kopf_s}.{inhalt_s}".encode(), padding.PKCS1v15(), hashes.SHA256())
        except Exception:
            return False
        return (inhalt.get("aud") == token_url and inhalt.get("iss") == inhalt.get("sub") == self.client_id
                and inhalt.get("exp", 0) > time.time() and form.get("client_id") == self.client_id)

    def _handler(anbieter):
        class H(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass

            def _json(self, code, d):
                roh = json.dumps(d).encode()
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(roh)))
                self.end_headers()
                self.wfile.write(roh)

            def do_GET(self):
                u = urllib.parse.urlparse(self.path)
                q = dict(urllib.parse.parse_qsl(u.query))
                basis = f"http://127.0.0.1:{anbieter.port}/tenant-1"
                anbieter.anfragen.append((u.path, q))
                if u.path == "/tenant-1/v2.0/.well-known/openid-configuration":
                    return self._json(200, {"issuer": anbieter.fehler.get("discovery_issuer", anbieter.aussteller),
                                            "authorization_endpoint": basis + "/oauth2/v2.0/authorize",
                                            "token_endpoint": basis + "/oauth2/v2.0/token", "jwks_uri": basis + "/discovery/v2.0/keys",
                                            "id_token_signing_alg_values_supported": ["RS256"]})
                if u.path == "/tenant-1/discovery/v2.0/keys":
                    return self._json(200, anbieter.jwks())
                if u.path == "/tenant-1/oauth2/v2.0/authorize":
                    if q.get("client_id") != anbieter.client_id or q.get("response_type") != "code" or "openid" not in q.get("scope", "").split():
                        return self._json(400, {"error": "invalid_request"})
                    code = secrets.token_urlsafe(16)
                    anbieter.codes[code] = q
                    ziel = q["redirect_uri"] + "?" + urllib.parse.urlencode({"code": code, "state": q["state"]})
                    self.send_response(302)
                    self.send_header("Location", ziel)
                    self.end_headers()
                    return
                self._json(404, {"error": "not_found"})

            def do_POST(self):
                u = urllib.parse.urlparse(self.path)
                n = int(self.headers.get("Content-Length") or 0)
                form = dict(urllib.parse.parse_qsl(self.rfile.read(n).decode()))
                anbieter.anfragen.append((u.path, form))
                token_url = f"http://127.0.0.1:{anbieter.port}/tenant-1/oauth2/v2.0/token"
                if u.path != "/tenant-1/oauth2/v2.0/token":
                    return self._json(404, {"error": "not_found"})
                q = anbieter.codes.pop(form.get("code", ""), None)        # jeder Code genau einmal
                if q is None:
                    return self._json(400, {"error": "invalid_grant", "error_description": "AADSTS70008: code used or unknown"})
                if not anbieter._ausweis_ok(form, token_url):
                    return self._json(401, {"error": "invalid_client", "error_description": "AADSTS7000215: Invalid client secret"})
                if form.get("redirect_uri") != q["redirect_uri"]:
                    return self._json(400, {"error": "invalid_grant", "error_description": "redirect_uri"})
                if b64url(hashlib.sha256(form.get("code_verifier", "").encode()).digest()) != q.get("code_challenge") or q.get("code_challenge_method") != "S256":
                    return self._json(400, {"error": "invalid_grant", "error_description": "AADSTS501481: PKCE"})
                return self._json(200, {"token_type": "Bearer", "expires_in": 3600, "access_token": "egal",
                                        "id_token": anbieter.id_token(q.get("nonce", ""))})
        return H
