"""Paket für den eigenen Server im Firmennetz (Stufe R3b): `amw web paket` baut am PC eine ZIP mit allem, was der
Webserver braucht – die Online-Seite (web/), eine fertige Konfiguration (Speicher-Adresse, Schlüssel der Seite, erster
Admin, nur_https), Vorlagen für nginx und Apache, docker compose für den libSQL-Server und eine LIESMICH.

Warum am PC und nicht per Assistent im Netz: Die Adresse des Speichers darf die Seite nie aus einem Formular nehmen (sonst
ließe sie sich als Sprungbrett ins interne Netz missbrauchen) – sie steht in der Konfigurationsdatei, und die legt nur ab,
wer Dateizugriff auf den Server hat.

Das Passwort des ersten Admins steht nur als Hash in der Konfiguration: SHA-512-crypt („$6$rounds=…$“), das PHP mit
password_verify() prüft – Python bringt bcrypt nicht mit, SHA-512-crypt lässt sich ohne Zusatzpaket rechnen.
"""
import datetime
import hashlib
import io
import json
import os
import secrets
import urllib.parse
import zipfile

from . import __version__, abgleich, betriebsart, kern, schluessel

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
VORLAGEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "server")
WEB_ORDNER = "/var/www/amw/web"
KONFIG = "/var/www/amw/konfig/amw-konfig.php"
PREFIX = "amw-paket/"
RUNDEN = 200_000
ITOA = "./0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz"
PW_ZEICHEN = "abcdefghjkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789"    # ohne leicht Verwechselbares (l, 1, O, 0 …)
ZERT = ("/etc/ssl/firma/amw.crt", "/etc/ssl/firma/amw.key")
HTTPS_UMLEITUNG = ("# immer HTTPS\nRewriteCond %{HTTPS} !=on\nRewriteCond %{HTTP:X-Forwarded-Proto} !=https\n"
                   "RewriteRule ^ https://%{HTTP_HOST}%{REQUEST_URI} [R=301,L]\n")


# --- SHA-512-crypt (Ulrich Drepper, „Unix crypt using SHA-256 and SHA-512“) -----------------------------------------

def _b64_24(a, b, c, n):
    w = (a << 16) | (b << 8) | c
    aus = ""
    for _ in range(n):
        aus += ITOA[w & 0x3F]
        w >>= 6
    return aus


def sha512_crypt(passwort, salz=None, runden=RUNDEN, runden_angeben=True):
    """Hash im Format $6$rounds=N$salz$… – prüfbar mit PHPs password_verify()/crypt(). runden_angeben=False nur für
    die Vorgabe von 5000 Runden (Form $6$salz$…, wie in den Prüfwerten der Beschreibung)."""
    pw = passwort.encode("utf-8")
    salz = (salz if salz is not None else "".join(secrets.choice(ITOA) for _ in range(16)))[:16]
    s = salz.encode("ascii")
    runden = max(1000, min(999_999_999, int(runden)))
    b = hashlib.sha512(pw + s + pw).digest()
    a = hashlib.sha512(pw + s)
    n = len(pw)
    while n > 64:
        a.update(b)
        n -= 64
    a.update(b[:n])
    i = len(pw)
    while i:
        a.update(b if i & 1 else pw)
        i >>= 1
    a = a.digest()
    dp = hashlib.sha512(pw * len(pw)).digest()
    p = dp * (len(pw) // 64) + dp[:len(pw) % 64]
    ds = hashlib.sha512(s * (16 + a[0])).digest()
    sx = ds * (len(s) // 64) + ds[:len(s) % 64]
    c = a
    for r in range(runden):
        h = hashlib.sha512(p if r & 1 else c)
        if r % 3:
            h.update(sx)
        if r % 7:
            h.update(p)
        h.update(c if r & 1 else p)
        c = h.digest()
    teile = ((0, 21, 42), (22, 43, 1), (44, 2, 23), (3, 24, 45), (25, 46, 4), (47, 5, 26), (6, 27, 48), (28, 49, 7),
             (50, 8, 29), (9, 30, 51), (31, 52, 10), (53, 11, 32), (12, 33, 54), (34, 55, 13), (56, 14, 35), (15, 36, 57),
             (37, 58, 16), (59, 17, 38), (18, 39, 60), (40, 61, 19), (62, 20, 41))
    kodiert = "".join(_b64_24(c[x], c[y], c[z], 4) for x, y, z in teile) + _b64_24(0, 0, c[63], 2)
    kopf = f"$6$rounds={runden}$" if runden_angeben else "$6$"
    return f"{kopf}{salz}${kodiert}"


# --- Adressen und Zugang ------------------------------------------------------------------------------------------

def seiten_adresse(url):
    """Adresse der Online-Seite: https://name[:port] – http:// nur im Firmennetz. Sonst ValueError mit einem Satz."""
    url = (url or "").strip().rstrip("/")
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ("", "/"):
        raise ValueError("Adresse der Online-Seite: https://name[:port] ohne Pfad, z. B. https://amw.firma.lan")
    if u.scheme == "http" and not betriebsart.http_im_netz(url):
        raise ValueError("http:// nur im Firmennetz – für eine Adresse im Internet https:// verwenden")
    return url


def _teile(url):
    u = urllib.parse.urlsplit(url)
    return u.scheme == "https", u.hostname, u.port or (443 if u.scheme == "https" else 80)


def zugang_lesen():
    try:
        with open(abgleich.zugang_pfad(), encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def zugang_eintragen(alt, url, token, ca):
    """Zugang zum eigenen Server am PC eintragen – Synchronisierung noch aus (erst prüfen, wenn der Server läuft)."""
    pfad = abgleich.zugang_pfad()
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad + ".neu", "w", encoding="utf-8") as f:
        json.dump({**alt, "art": "libsql", "url": url, "token": token, "ca": ca or "", "abgleich": False}, f, indent=2)
    os.replace(pfad + ".neu", pfad)
    return pfad


# --- Bausteine ----------------------------------------------------------------------------------------------------

def _php(s):
    return "'" + str(s).replace("\\", "\\\\").replace("'", "\\'") + "'"


def konfig_php(admin, passwort_hash, nur_https, speicher, token, mit_ca, seite):
    zeilen = [f"    'benutzer' => {_php(admin)},", f"    'passwort_hash' => {_php(passwort_hash)},",
              f"    'nur_https' => {'true' if nur_https else 'false'},",
              f"    'speicher_url' => {_php(speicher)},", f"    'speicher_token' => {_php(token)},"]
    if mit_ca:
        zeilen.append("    'speicher_ca' => __DIR__ . '/amw-firmen-ca.pem',")
    jetzt = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d %H:%M")
    return ("<?php\n"
            f"// AMW online – erzeugt {jetzt} UTC von „amw web paket“ für {seite}.\n"
            "// Enthält den Schlüssel der Seite für den Online-Speicher: außerhalb des Web-Ordners ablegen, nie ins Repo.\n"
            "return [\n" + "\n".join(zeilen) + "\n];\n")


def _vorlage(name, werte):
    with open(os.path.join(VORLAGEN, name), encoding="utf-8") as f:
        text = f.read()
    for k, v in werte.items():
        text = text.replace("{{" + k + "}}", v)
    if "{{" in text:
        raise kern.AmwFehler(f"Vorlage {name}: Platzhalter ohne Wert ({text[text.index('{{'):][:30]})")
    return text


def _nginx(seite, speicher, php, sqld, web_ordner, konfig, datum):
    s_https, s_host, s_port = _teile(seite)
    p_https, p_host, p_port = _teile(speicher)
    tls = (f"    ssl_certificate     {ZERT[0]};\n    ssl_certificate_key {ZERT[1]};\n") if s_https else ""
    if p_https:
        block = (f"\n# Online-Speicher: https davor, sqld selbst lauscht nur unverschlüsselt ({sqld})\n"
                 "server {\n"
                 f"    listen {p_port} ssl;\n    server_name {p_host};\n"
                 f"    ssl_certificate     {ZERT[0]};\n    ssl_certificate_key {ZERT[1]};\n"
                 "    server_tokens off;\n    client_max_body_size 8m;\n"
                 "    location / {\n"
                 f"        proxy_pass {sqld};\n        proxy_set_header Host $host;\n        proxy_read_timeout 60s;\n"
                 "    }\n}\n")
    else:
        block = f"\n# Online-Speicher über http ({speicher}): kein Block nötig – sqld lauscht selbst (nur im Firmennetz).\n"
    return _vorlage("nginx-amw.conf", {
        "DATUM": datum, "SEITE": seite, "SPEICHER": speicher, "WEB_ORDNER": web_ordner, "KONFIG": konfig, "PHP": php,
        "LISTEN_SEITE": f"    listen {s_port}{' ssl' if s_https else ''};", "SEITE_HOST": s_host, "TLS": tls,
        "SPEICHER_BLOCK": block})


def _apache(seite, speicher, datum):
    s_https, s_host, s_port = _teile(seite)
    p_https, p_host, p_port = _teile(speicher)
    tls = (f"    SSLEngine on\n    SSLCertificateFile {ZERT[0]}\n    SSLCertificateKeyFile {ZERT[1]}\n") if s_https else ""
    if p_https:
        block = ("\n# Online-Speicher: https davor, sqld selbst lauscht nur auf 127.0.0.1:8080\n"
                 f"<VirtualHost *:{p_port}>\n    ServerName {p_host}\n"
                 f"    SSLEngine on\n    SSLCertificateFile {ZERT[0]}\n    SSLCertificateKeyFile {ZERT[1]}\n"
                 "    ProxyPreserveHost On\n    ProxyPass / http://127.0.0.1:8080/\n    ProxyPassReverse / http://127.0.0.1:8080/\n"
                 "</VirtualHost>\n")
    else:
        block = f"\n# Online-Speicher über http ({speicher}): kein Block nötig – sqld lauscht selbst (nur im Firmennetz).\n"
    mods = (" ssl" if s_https or p_https else "") + (" proxy proxy_http" if p_https else "")
    return _vorlage("apache-amw.conf", {
        "DATUM": datum, "SEITE": seite, "SPEICHER": speicher, "WEB_ORDNER": WEB_ORDNER, "KONFIG": KONFIG,
        "MODULE_SPEICHER": ", ssl, proxy, proxy_http (Speicher)" if p_https else (", ssl" if s_https else ""),
        "A2ENMOD": mods, "PORT_SEITE": str(s_port), "SEITE_HOST": s_host, "TLS": tls, "SPEICHER_BLOCK": block})


def _htaccess(text, https):
    """Bei http im Firmennetz: ohne die Umleitung auf https (sonst wäre die Seite nicht erreichbar)."""
    if https:
        return text
    if HTTPS_UMLEITUNG not in text.replace("\r\n", "\n"):
        raise kern.AmwFehler("web/.htaccess: Umleitung auf https nicht gefunden – Paket für http nicht möglich")
    return text.replace("\r\n", "\n").replace(HTTPS_UMLEITUNG, "# http im Firmennetz (amw web paket --seite http://…): keine Umleitung auf https\n")


def _web_dateien(web):
    """(Pfad im Paket, Inhalt) der Online-Seite – ohne Konfiguration und Reste."""
    with open(os.path.join(web, "inc", "VERSION"), encoding="utf-8") as f:
        stand = f.read().strip()
    if stand != __version__:
        raise kern.AmwFehler(f"Die Online-Seite in {web} hat Version {stand}, diese AMW {__version__} – erst `amw web bauen`")
    for wurzel, ordner, dateien in os.walk(web):
        ordner[:] = sorted(o for o in ordner if o not in ("__pycache__",))
        for n in sorted(dateien):
            if n.startswith("amw-konfig.php") or n.endswith((".neu", ".bak")):
                continue
            p = os.path.join(wurzel, n)
            with open(p, "rb") as f:
                yield os.path.relpath(p, web).replace(os.sep, "/"), f.read()


# --- Paket --------------------------------------------------------------------------------------------------------

def bauen(seite, speicher, admin="admin", ca=None, ziel=None, ersetzen=False, passwort=None, web=None):
    """Baut die ZIP und trägt den Zugang am PC ein. Rückgabe: {ziel, zugang, admin, passwort, seite, speicher}.
    Erst wird alles geprüft und gebaut, dann geschrieben – bei einem Fehler bleibt nichts zurück."""
    try:
        seite = seiten_adresse(seite)
        speicher = abgleich.speicher_adresse("libsql", speicher or "")
    except ValueError as e:
        raise kern.AmwFehler(f"{e} – amw web paket --seite https://amw.firma.lan --speicher https://amw-db.firma.lan") from None
    admin = (admin or "").strip()
    if not admin or len(admin) > 40 or not all(c.isalnum() or c in "._-" for c in admin):
        raise kern.AmwFehler("--admin: Name aus Buchstaben, Ziffern, . _ - (höchstens 40 Zeichen)")
    if ca and not os.path.isfile(ca):
        raise kern.AmwFehler(f"Zertifikat-Datei gibt es nicht: {ca}")
    if passwort is not None and len(passwort) < 14:
        raise kern.AmwFehler("Passwort: mindestens 14 Zeichen (wie im Einrichtungs-Assistenten)")
    alt = zugang_lesen()
    if alt.get("url") and not ersetzen:
        raise kern.AmwFehler(f"Es gibt schon einen Online-Speicher ({alt['url']}). Neues Paket mit neuen Schlüsseln: --ersetzen"
                             " – dann gilt der alte Zugang auf diesem PC nicht mehr.")
    host = urllib.parse.urlsplit(seite).hostname
    ziel = os.path.abspath(ziel or f"amw-paket-{host}-{datetime.date.today():%Y-%m-%d}.zip")
    if os.path.exists(ziel):
        raise kern.AmwFehler(f"Gibt es schon: {ziel} – andere Datei mit --ziel wählen")
    web = web or os.path.join(WURZEL, "web")
    s_https = seite.startswith("https://")

    pem, token = schluessel.erzeugen(("pc", "seite"))
    passwort = passwort or "".join(secrets.choice(PW_ZEICHEN) for _ in range(20))
    datum = datetime.datetime.now().strftime("%d.%m.%Y %H:%M")
    p_https, p_host, p_port = _teile(speicher)
    sqld_ports = "127.0.0.1:8080:8080" if p_https else f"{p_port}:8080"
    web_ports = [_teile(seite)[2]] + ([p_port] if p_https and p_port != _teile(seite)[2] else [])
    werte = {"DATUM": datum, "VERSION": __version__, "SEITE": seite, "SPEICHER": speicher, "ADMIN": admin,
             "WEB_ORDNER": WEB_ORDNER, "KONFIG": KONFIG, "KONFIG_CA": " und amw-firmen-ca.pem" if ca else "",
             "SPEICHER_HINWEIS": ("sqld lauscht nur auf 127.0.0.1:8080; https davor macht der Webserver (Block „Online-Speicher“ in den"
                                  " Vorlagen). Läuft sqld auf einem anderen Rechner: Port in docker-compose.yml freigeben und die"
                                  " Adresse im Proxy anpassen." if p_https else
                                  f"sqld lauscht direkt auf Port {p_port} (http, unverschlüsselt – nur im Firmennetz)."),
             "SEITE_HINWEIS": ("Zertifikat und Schlüssel der Firma eintragen (ssl_certificate bzw. SSLCertificateFile)." if s_https else
                               "Die Seite läuft über http (unverschlüsselt) – nur im Firmennetz. Die Anmeldeseite zeigt das als Warnung;"
                               " Dateien hochladen geht nur über https.")}
    with open(os.path.join(web, ".htaccess"), encoding="utf-8") as f:
        htaccess = _htaccess(f.read(), s_https)

    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w", zipfile.ZIP_DEFLATED) as z:
        def dazu(name, inhalt, geheim=False):
            info = zipfile.ZipInfo(PREFIX + name, date_time=datetime.datetime.now().timetuple()[:6])
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = (0o600 if geheim else 0o644) << 16
            z.writestr(info, inhalt)
        dazu("LIESMICH.txt", _vorlage("LIESMICH.txt", werte))
        for name, inhalt in _web_dateien(web):
            dazu("web/" + name, htaccess if name == ".htaccess" else inhalt)
        dazu("konfig/amw-konfig.php", konfig_php(admin, sha512_crypt(passwort), s_https, speicher, token["seite"], bool(ca), seite), True)
        if ca:
            with open(ca, "rb") as f:
                dazu("konfig/amw-firmen-ca.pem", f.read())
        dazu("speicher/amw-speicher-oeffentlich.pem", pem)
        dazu("speicher/docker-compose.yml", _vorlage("docker-compose.yml", {"DATUM": datum, "SQLD_PORTS": sqld_ports}))
        dazu("webserver/nginx-amw.conf", _nginx(seite, speicher, "unix:/run/php/php8.3-fpm.sock", "http://127.0.0.1:8080",
                                                WEB_ORDNER, KONFIG, datum))
        dazu("webserver/apache-amw.conf", _apache(seite, speicher, datum))
        dazu("beispiel/nginx-docker.conf", _nginx(seite, speicher, "php:9000", "http://speicher:8080", WEB_ORDNER, KONFIG, datum))
        dazu("beispiel/docker-compose-alles.yml", _vorlage("docker-compose-alles.yml", {
            "DATUM": datum, "WEB_PORTS": "\n".join(f'      - "{p}:{p}"' for p in web_ports),
            "SPEICHER_PORTS": "" if p_https else f'    ports:\n      - "{p_port}:8080"\n'}))

    os.makedirs(os.path.dirname(ziel), exist_ok=True)
    with open(ziel + ".neu", "wb") as f:
        f.write(puffer.getvalue())
    os.replace(ziel + ".neu", ziel)
    zugang = zugang_eintragen(alt, speicher, token["pc"], os.path.abspath(ca) if ca else "")
    return {"ziel": ziel, "zugang": zugang, "admin": admin, "passwort": passwort, "seite": seite, "speicher": speicher}
