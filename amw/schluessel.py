"""Schlüssel für einen eigenen libSQL-Server (Stufe R3a, Betriebsart „eigener Server im Firmennetz“).

Der libSQL-Server (sqld) prüft jede Anfrage mit einem öffentlichen Ed25519-Schlüssel (`--auth-jwt-key-file`); PC und
Online-Seite schicken ein damit signiertes Token (JWT, alg EdDSA) als `Authorization: Bearer …` – dasselbe Verfahren wie
Turso, darum ändert sich am Abgleich nichts. Hier entstehen Schlüsselpaar und Token. Der private Schlüssel wird nach dem
Signieren verworfen: Neue Token heißt neues Paar (und neuer öffentlicher Schlüssel auf dem Server) – so liegt nirgends
etwas, womit man weitere Token ausstellen könnte.

Am Server (sqld 0.24.32, geprüft 12.11.2026): ohne, mit fremdem oder kaputtem Token 401, mit „a“: „ro“ beim Schreiben
403. Ein Ablaufdatum („exp“) prüft der Server NICHT – Token gelten, bis der Schlüssel auf dem Server ersetzt wird.

Ed25519 kann Python nicht selbst: zuerst das Paket `cryptography` (optional), sonst das Programm `openssl` (≥ 3.0;
auch das von Git für Windows), sonst eine klare Meldung.
"""
import base64
import json
import os
import shutil
import subprocess
import tempfile
import time

from . import kern

ANLEITUNG = ("Für den Schlüssel braucht die AMW das Python-Paket „cryptography“ (`python -m pip install cryptography`)"
             " oder das Programm openssl ab Version 3 (z. B. aus Git für Windows: C:\\Program Files\\Git\\usr\\bin\\openssl.exe).")


def _b64(b):
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _inhalt(rechte, name):
    kopf = _b64(json.dumps({"alg": "EdDSA", "typ": "JWT"}, separators=(",", ":")).encode())
    # „id“ hieße für den Server: Name der Datenbank (wie bei Turso) – dann sucht er eine, die es nicht gibt (404). Der Name
    # des Empfängers steht darum unter „amw“; er dient nur dem Menschen, der Server ignoriert ihn.
    rumpf = _b64(json.dumps({"a": rechte, "iat": int(time.time()), "amw": name}, separators=(",", ":")).encode())
    return f"{kopf}.{rumpf}"


def _mit_cryptography(namen, rechte):
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    k = Ed25519PrivateKey.generate()
    pem = k.public_key().public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo).decode()
    token = {}
    for n in namen:
        roh = _inhalt(rechte, n)
        token[n] = roh + "." + _b64(k.sign(roh.encode()))
    return pem, token


def openssl_pfad():
    for p in (shutil.which("openssl"), r"C:\Program Files\Git\usr\bin\openssl.exe", r"C:\Program Files\Git\mingw64\bin\openssl.exe"):
        if p and os.path.isfile(p):
            return p
    return None


def _mit_openssl(namen, rechte, openssl):
    with tempfile.TemporaryDirectory() as d:                      # privater Schlüssel nur hier, danach weg
        priv, pub = os.path.join(d, "p.pem"), os.path.join(d, "o.pem")
        lauf = lambda *a: subprocess.run([openssl, *a], capture_output=True, timeout=30, check=True)
        try:
            lauf("genpkey", "-algorithm", "ed25519", "-out", priv)
            lauf("pkey", "-in", priv, "-pubout", "-out", pub)
            token = {}
            for n in namen:
                roh = _inhalt(rechte, n)
                ein, aus = os.path.join(d, "e.bin"), os.path.join(d, "s.bin")
                with open(ein, "wb") as f:
                    f.write(roh.encode())
                lauf("pkeyutl", "-sign", "-rawin", "-inkey", priv, "-in", ein, "-out", aus)
                with open(aus, "rb") as f:
                    token[n] = roh + "." + _b64(f.read())
        except (subprocess.CalledProcessError, OSError) as e:
            raise kern.AmwFehler(f"openssl konnte den Schlüssel nicht erzeugen ({e}). " + ANLEITUNG) from None
        with open(pub, encoding="ascii") as f:
            return f.read(), token


def erzeugen(namen=("pc", "seite"), rechte="rw", weg=None):
    """Neues Schlüsselpaar; Rückgabe (öffentlicher Schlüssel als PEM, {name: token}). weg: 'cryptography' | 'openssl'
    erzwingt einen Weg (Tests)."""
    if weg in (None, "cryptography"):
        try:
            return _mit_cryptography(namen, rechte)
        except ImportError:
            if weg:
                raise kern.AmwFehler(ANLEITUNG) from None
    o = openssl_pfad()
    if o is None:
        raise kern.AmwFehler(ANLEITUNG)
    return _mit_openssl(namen, rechte, o)
