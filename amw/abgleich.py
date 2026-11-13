"""Stufe 2: Abgleich mit dem Online-Speicher (Turso) – Schaufenster + Briefkasten (→ doc/online.md).

Schaufenster: Der PC berechnet die Ansichten der Workbench (dieselben wie lokal) und legt sie als fertiges JSON in
`ansicht` ab, nur wenn sich etwas geändert hat. Die Seite im Netz zeigt nur diese Ansichten – sie sieht keine
Tabellen, und der PC ist aus dem Netz nicht erreichbar.
Briefkasten: Was der Entwickler online tut (Antwort, Nachricht, Halt, Weiter), schreibt die Seite als Zeile in
`eingang`. Der PC holt neue Zeilen ab, führt sie über denselben Weg wie die lokale Seite aus (aktionen.py) und
trägt das Ergebnis zurück. Jede Zeile wirkt höchstens einmal (lokale Liste `netz_eingang`).

Dokumente (Stufe D2, → doc/plan-dokumente.md): Liste, Details und Texte gehen als Ansichten mit. Dateien nur, wenn ein
Dokument „auch online“ steht: der PC legt sie in Teilen in `datei_teil` und meldet sie in `datei` an, die Seite holt sie
beim nächsten Aufruf auf den Webspace (außerhalb des Deploy-Ordners) und löscht die Teile. Steht ein Dokument nicht mehr
online, nimmt der PC die Zeile aus `datei` – die Seite löscht ihre Kopie dann selbst. Der PC braucht dafür weder die Adresse
der Seite noch einen eigenen Schlüssel.

Mehrere Projekte, auch auf mehreren Rechnern (→ doc/plan-projektwahl.md): Jede Ansicht liegt unter „<Kennung>:<Weg>“
(Kennung = projekt.uid), Befehle vom Handy tragen die Kennung, das Verzeichnis `projekt` listet alle Projekte mit ihrem
Rechner. Ein Rechner schreibt und löscht nur Daten seiner eigenen Projekte; Dateien gehören über `datei_projekt` zu
Projekten und verschwinden erst, wenn keines sie mehr nennt.

Zugang: %LOCALAPPDATA%\\amw\\turso.json {"url", "token", "abgleich": true}. Ohne "abgleich": true bleibt alles aus.
Der Schlüssel wird nie ausgegeben oder protokolliert.
"""
import base64
import datetime
import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import zlib

from . import aktionen, db, kern, verlauf, workbench

log = logging.getLogger("amw.abgleich")

GESPRAECH_S = 600    # Gespräch eines Agenten online: nur auf Wunsch der Seite, so lange nach dem letzten Abruf
HOCH_S = 30          # Ansichten höchstens so oft hochladen (nur bei Änderung)
PULS_S = 300         # spätestens dann Start/Betrieb neu (zeigt online: „PC zuletzt gesehen“)
EINGANG_S = 15       # Briefkasten so oft leeren
TEIL = 256 * 1024    # Datei-Teil in Bytes (Base64 ~350 KB je Zeile)
TEILE_JE_ANFRAGE = 4             # ~1,4 MB je Anfrage an den Speicher
DATEIEN_JE_SCHRITT = 8 << 20     # so viel höchstens je Durchgang hochladen, der Rest beim nächsten
TEXT_MAX = 400_000   # Zeichen je Text-Version online (sehr lange Texte gekürzt, vollständig am PC)
HOCH_ALT_S = 86400   # Uploads vom Handy, die nie fertig wurden, nach einem Tag aus dem Speicher

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS ansicht (weg TEXT PRIMARY KEY, inhalt TEXT NOT NULL, pruef TEXT NOT NULL,"
    " stand_utc TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS eingang (id INTEGER PRIMARY KEY, zeit_utc TEXT NOT NULL, weg TEXT NOT NULL,"
    " daten TEXT NOT NULL, ip TEXT, status TEXT NOT NULL DEFAULT 'neu', ergebnis TEXT, erledigt_utc TEXT)",
    "CREATE INDEX IF NOT EXISTS eingang_neu ON eingang (status, id)",
    "CREATE TABLE IF NOT EXISTS versuch (id INTEGER PRIMARY KEY, zeit_utc TEXT NOT NULL, ip TEXT, ok INTEGER NOT NULL)",
    "CREATE INDEX IF NOT EXISTS versuch_zeit ON versuch (zeit_utc)",
    "CREATE TABLE IF NOT EXISTS zustand (schluessel TEXT PRIMARY KEY, wert TEXT)",
    "CREATE TABLE IF NOT EXISTS datei (sha TEXT PRIMARY KEY, endung TEXT NOT NULL, groesse INTEGER NOT NULL,"
    " teile INTEGER NOT NULL, status TEXT NOT NULL, zeit_utc TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS datei_teil (sha TEXT NOT NULL, nr INTEGER NOT NULL, inhalt TEXT NOT NULL,"
    " PRIMARY KEY (sha, nr))",
    "CREATE TABLE IF NOT EXISTS hoch (id TEXT PRIMARY KEY, name TEXT NOT NULL, endung TEXT NOT NULL, groesse INTEGER NOT NULL,"
    " sha TEXT NOT NULL, teile INTEGER NOT NULL, zeit_utc TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS hoch_teil (id TEXT NOT NULL, nr INTEGER NOT NULL, inhalt TEXT NOT NULL, PRIMARY KEY (id, nr))",
    "CREATE TABLE IF NOT EXISTS projekt (uid TEXT PRIMARY KEY, name TEXT NOT NULL, farbe TEXT, rechner TEXT, gesehen_utc TEXT NOT NULL,"
    " fragen INTEGER NOT NULL DEFAULT 0, agenten INTEGER NOT NULL DEFAULT 0, halt INTEGER NOT NULL DEFAULT 0)",
    "CREATE TABLE IF NOT EXISTS datei_projekt (sha TEXT NOT NULL, projekt TEXT NOT NULL, PRIMARY KEY (sha, projekt))",
    "CREATE TABLE IF NOT EXISTS benutzer (name TEXT PRIMARY KEY, anzeige TEXT, email TEXT, rolle TEXT, gesperrt INTEGER NOT NULL DEFAULT 0,"
    " projekte TEXT NOT NULL DEFAULT '[]', passwort_hash TEXT, totp_geheim TEXT, totp_letzt INTEGER NOT NULL DEFAULT 0,"
    " code_hash TEXT, code_bis TEXT, sitzung_nr INTEGER NOT NULL DEFAULT 0, eingerichtet_utc TEXT, angemeldet_utc TEXT, stand_utc TEXT,"
    " sso_kennung TEXT)",
]
# Spalten, die es in älteren Online-Speichern noch nicht gibt (web/inc/lib.php rüstet dieselben nach)
NACHRUESTEN = [("eingang", "projekt", "ALTER TABLE eingang ADD COLUMN projekt TEXT"),
               # Benutzer (1.65): 1.63/1.64 legen die Tabelle schon an, noch ohne Freischalt-Code und Sitzungszähler
               ("benutzer", "totp_letzt", "ALTER TABLE benutzer ADD COLUMN totp_letzt INTEGER NOT NULL DEFAULT 0"),
               ("benutzer", "code_hash", "ALTER TABLE benutzer ADD COLUMN code_hash TEXT"),
               ("benutzer", "code_bis", "ALTER TABLE benutzer ADD COLUMN code_bis TEXT"),
               ("benutzer", "sitzung_nr", "ALTER TABLE benutzer ADD COLUMN sitzung_nr INTEGER NOT NULL DEFAULT 0"),
               ("benutzer", "eingerichtet_utc", "ALTER TABLE benutzer ADD COLUMN eingerichtet_utc TEXT"),
               ("benutzer", "angemeldet_utc", "ALTER TABLE benutzer ADD COLUMN angemeldet_utc TEXT"),
               # Firmen-Anmeldung (R2): an welches Firmenkonto (Aussteller|sub) der Benutzer beim ersten Mal gebunden wurde
               ("benutzer", "sso_kennung", "ALTER TABLE benutzer ADD COLUMN sso_kennung TEXT")]


def nachruesten(sp):
    """Fehlende Spalten älterer Online-Speicher ergänzen (je Spalte geprüft, darum beliebig oft aufrufbar)."""
    for tabelle, spalte, sql in NACHRUESTEN:
        # int(): Turso liefert Zahlen als Text – „0“ wäre sonst wahr (06.11.)
        if not int(sp.ausfuehren([(f"SELECT count(*) FROM pragma_table_info('{tabelle}') WHERE name = ?", [spalte])])[0][0][0]):
            sp.ausfuehren([(sql, [])])
VERZEICHNIS = {"projekte": [], "stand": 0.0}   # zuletzt gelesenes Verzeichnis (für die Projekt-Auswahl am PC)
SICHTEN = ("offen", "geparkt", "pool", "erledigt")

# Online-Seite (web/inc/lib.php liest dieselben Werte mit denselben Grenzen)
WEB_EINSTELLUNGEN = {"leerlauf_min": (30, 5, 240), "hoechstens_h": (12, 1, 72), "fehl_je_ip": (5, 3, 20),
                     "fehl_gesamt": (20, 5, 200)}


def web_einstellungen(speicher):
    """Aktuelle Werte der Online-Seite (Vorgaben, wo nichts gesetzt ist)."""
    roh = speicher.ausfuehren([("SELECT wert FROM zustand WHERE schluessel = 'web_einstellungen'", [])])[0]
    d = json.loads(roh[0][0]) if roh else {}
    return {k: (int(d[k]) if k in d and lo <= int(d[k]) <= hi else v) for k, (v, lo, hi) in WEB_EINSTELLUNGEN.items()}


def sso_einstellungen(speicher):
    """Firmen-Anmeldung (R2): was der PC einstellt (an, Aussteller, Client-ID) und was die Seite meldet (Art des
    Zugangs beim Anbieter – Geheimnis oder Zertifikat –, Rückkehr-Adresse). Das Geheimnis selbst steht nur beim Webhoster."""
    roh = speicher.ausfuehren([("SELECT schluessel, wert FROM zustand WHERE schluessel IN ('sso', 'sso_stand')", [])])[0]
    d = {k: json.loads(v or "{}") for k, v in roh}
    e, st = d.get("sso", {}), d.get("sso_stand", {})
    return {"an": bool(e.get("an")), "aussteller": e.get("aussteller", ""), "client_id": e.get("client_id", ""),
            "zugang": st.get("zugang", ""), "rueckweg": st.get("rueckweg", ""), "gemeldet_utc": st.get("zeit_utc")}


def sso_setzen(speicher, neu):
    d = {k: v for k, v in sso_einstellungen(speicher).items() if k in ("an", "aussteller", "client_id")}
    for k, v in neu.items():
        if k not in d:
            raise ValueError(f"unbekannte Einstellung: {k}")
        d[k] = bool(v) if k == "an" else str(v or "").strip()
    d["aussteller"] = d["aussteller"].rstrip("/")
    u = urllib.parse.urlsplit(d["aussteller"])
    if d["aussteller"] and (u.scheme != "https" or not u.hostname or u.query or u.fragment):
        raise ValueError("Aussteller: eine https-Adresse, z. B. https://login.microsoftonline.com/<Mandanten-ID>/v2.0")
    if any(x in d["aussteller"].lower() for x in ("/common/", "/organizations/", "/consumers/")):
        raise ValueError("Aussteller: statt common/organizations die Mandanten-ID (Tenant ID) eintragen")
    if len(d["client_id"]) > 200 or any(c.isspace() for c in d["client_id"]):
        raise ValueError("Client-ID: ohne Leerzeichen, höchstens 200 Zeichen")
    if d["an"] and not (d["aussteller"] and d["client_id"]):
        raise ValueError("Zum Einschalten braucht es Aussteller und Client-ID")
    speicher.ausfuehren([("INSERT INTO zustand (schluessel, wert) VALUES ('sso', ?) ON CONFLICT(schluessel)"
                          " DO UPDATE SET wert = excluded.wert", [json.dumps(d)])])
    return sso_einstellungen(speicher)


def web_einstellungen_setzen(speicher, neu):
    d = web_einstellungen(speicher)
    for k, v in neu.items():
        if k not in WEB_EINSTELLUNGEN:
            raise ValueError(f"unbekannte Einstellung: {k}")
        _, lo, hi = WEB_EINSTELLUNGEN[k]
        v = int(v)
        if not lo <= v <= hi:
            raise ValueError(f"{k}: zwischen {lo} und {hi}")
        d[k] = v
    speicher.ausfuehren([("INSERT INTO zustand (schluessel, wert) VALUES ('web_einstellungen', ?) ON CONFLICT(schluessel)"
                          " DO UPDATE SET wert = excluded.wert", [json.dumps(d)])])
    return d


# --- Speicher ------------------------------------------------------------------------------------

SPEICHER_ARTEN = ("turso", "libsql")   # Turso (Cloud) · eigener libSQL-Server (sqld) – dasselbe Protokoll


def speicher_adresse(art, url):
    """Prüft die Adresse des Online-Speichers und gibt sie einheitlich zurück – sonst ValueError mit einem Satz für Menschen.
    turso: libsql:// oder https:// auf ….turso.io. libsql (eigener Server): https://host[:port] – http:// nur, wenn das Ziel
    im Firmennetz oder auf diesem PC liegt (sonst ginge der Schlüssel unverschlüsselt durchs Internet)."""
    url = (url or "").strip().rstrip("/")
    if art == "turso":
        if not url.startswith(("libsql://", "https://")) or ".turso.io" not in url:
            raise ValueError("Adresse libsql://….turso.io nötig")
        return url
    if art != "libsql":
        raise ValueError(f"Art: {', '.join(SPEICHER_ARTEN)}")
    if url.startswith("libsql://"):
        url = "https://" + url[len("libsql://"):]
    u = urllib.parse.urlsplit(url)
    if u.scheme not in ("http", "https") or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ("", "/"):
        raise ValueError("Adresse des eigenen Servers: https://name:port (ohne Pfad), z. B. https://amw-db.firma.lan")
    if u.scheme == "http":
        from . import betriebsart
        if betriebsart.netz(url) == "internet":
            raise ValueError("http:// nur im Firmennetz – für eine Adresse im Internet https:// verwenden")
    return url


class TursoSpeicher:
    """Online-Speicher über HTTP /v2/pipeline (nur Standardbibliothek): Turso oder ein eigener libSQL-Server (sqld) –
    dasselbe Protokoll, Schlüssel als Bearer-Token. Eine Anfrage = eine Folge von Anweisungen. ca: Zertifikat der Firma
    (PEM-Datei) für einen eigenen Server mit eigenem Zertifikat; sonst die Zertifikate von Windows."""

    def __init__(self, url, token, ca=None):
        url = url.strip()
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        self.url, self._token = url.rstrip("/") + "/v2/pipeline", token.strip()
        self._ca = ca or None

    @staticmethod
    def _wert(v):
        if v is None:
            return {"type": "null"}
        if isinstance(v, int):
            return {"type": "integer", "value": str(v)}
        return {"type": "text", "value": str(v)}

    def ausfuehren(self, anweisungen):
        from . import betriebsart                    # die Betriebsart entscheidet, ob diese Adresse erreicht werden darf
        betriebsart.pruefe(self.url, "Verbindung zum Online-Speicher")
        body = {"requests": [{"type": "execute", "stmt": {"sql": sql, "args": [self._wert(x) for x in args]}}
                             for sql, args in anweisungen] + [{"type": "close"}]}
        req = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Authorization": f"Bearer {self._token}",
                                              "Content-Type": "application/json"})
        weiter = {}
        if self._ca and self.url.startswith("https://"):
            import ssl
            weiter["context"] = ssl.create_default_context(cafile=self._ca)
        try:
            with urllib.request.urlopen(req, timeout=20, **weiter) as r:
                antwort = json.load(r)
        except urllib.error.HTTPError as e:
            raise OSError(f"Turso HTTP {e.code}") from None      # Text kann den Schlüssel spiegeln – nicht weiterreichen
        ergebnis = []
        for r in antwort["results"][:len(anweisungen)]:
            if r["type"] != "ok":
                raise OSError(f"Turso: {(r.get('error') or {}).get('message', 'Fehler')}")
            res = r["response"].get("result", {})
            ergebnis.append([[z.get("value") for z in zeile] for zeile in res.get("rows", [])])
        return ergebnis


class SqliteSpeicher:
    """Gleiche Schnittstelle auf einer lokalen Datei – für Tests und die Probe der PHP-Seite am PC."""

    def __init__(self, pfad):
        self.pfad = pfad

    def ausfuehren(self, anweisungen):
        con = sqlite3.connect(self.pfad, timeout=30, isolation_level=None)
        try:
            return [[list(z) for z in con.execute(sql, args).fetchall()] for sql, args in anweisungen]
        finally:
            con.close()


def zugang_pfad():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "amw", "turso.json")


def speicher_aus_zugang(nur_wenn_an=True):
    try:
        with open(zugang_pfad(), encoding="utf-8") as f:
            z = json.load(f)
    except (OSError, ValueError):
        return None
    if nur_wenn_an and not z.get("abgleich"):
        return None
    if z.get("sqlite"):                               # Probe am PC: statt Turso eine lokale Datei
        return SqliteSpeicher(z["sqlite"])
    return TursoSpeicher(z["url"], z["token"], z.get("ca"))


def firmen_ca():
    """Pfad zum Zertifikat der Firmen-CA, wenn eines beim Online-Speicher eingetragen ist und die Datei da ist – sonst None.
    Dieselbe Firma stellt meist auch das Zertifikat der Online-Seite und des ntfy-Servers aus."""
    try:
        with open(zugang_pfad(), encoding="utf-8") as f:
            ca = json.load(f).get("ca")
    except (OSError, ValueError, AttributeError):
        return None
    return ca if ca and os.path.isfile(ca) else None


def tls_kontext(url):
    """Für https-Adressen mit eingetragener Firmen-CA: die Zertifikate des Systems und zusätzlich das der Firma (Dienste
    im Internet bleiben so erreichbar). Sonst None – dann gilt, was Python ohnehin prüft."""
    ca = firmen_ca() if str(url).lower().startswith("https://") else None
    if not ca:
        return None
    import ssl
    k = ssl.create_default_context()
    k.load_verify_locations(cafile=ca)
    return k


# --- Abgleich ------------------------------------------------------------------------------------

def hoch_holen(sp, hid):
    """Upload vom Handy aus dem Speicher holen (die Seite hat ihn in Teilen abgelegt) → (roh, name). Prüft Größe und
    Prüfsumme; die Teile löscht danach Abgleich.hoch_weg."""
    from . import dokumente
    hid = str(hid or "")
    if not re.fullmatch(r"[0-9a-f]{32}", hid):
        raise kern.AmwFehler("Upload-Nummer fehlt")
    kopf = sp.ausfuehren([("SELECT name, groesse, sha, teile FROM hoch WHERE id = ?", [hid])])[0]
    if not kopf:
        raise kern.AmwFehler("Upload nicht (mehr) im Speicher – bitte neu hochladen")
    name, groesse, sha, teile = kopf[0][0], int(kopf[0][1]), kopf[0][2], int(kopf[0][3])
    roh = b""
    for i in range(0, teile, 8):
        for (b64,) in sp.ausfuehren([("SELECT inhalt FROM hoch_teil WHERE id = ? AND nr >= ? AND nr < ? ORDER BY nr",
                                      [hid, i, i + 8])])[0]:
            roh += base64.b64decode(b64)
    return dokumente.hoch_pruefen(roh, groesse, sha), name


def _betrieb_ohne_namen(betrieb):
    """Online: laufende Läufe anderer Projekte (Grafikkarte/Bildschirm belegt) ohne Projektnamen – den sieht nur der PC (B2691)."""
    for f in betrieb.get("fremd", []):
        f["projekt"] = None
    return betrieb


def _fremde_ohne_namen(start, pid, con):
    """Online nennt die Team-Ansicht bei Läufen anderer Projekte weder Projekt noch Agent (die Projekte mischen sich nicht;
    online können Benutzer nur einzelne Projekte sehen). Am PC stehen die Namen."""
    eigen = con.execute("SELECT name FROM projekt WHERE id = ?", (pid,)).fetchone()[0]
    for a in start.get("agenten", []):
        for x in (a.get("warteplatz") or {}).get("auf", []):
            if x.get("projekt") != eigen:
                x["projekt"], x["agent"] = None, None
        if a.get("warteplatz"):
            a["warteplatz"]["grund"] = None
    return start


def ansichten(con, pid, speicher=None):
    """Dieselben Antworten wie die lokale Workbench, Schlüssel = Weg, wie ihn die Seite anfragt."""
    leer = {"agent": [""], "q": [""]}
    a = {"/api/start": _fremde_ohne_namen(workbench.daten_start(con, pid), pid, con),
         "/api/fragen": workbench.daten_fragen(con, pid),
         "/api/nachrichten": workbench.daten_nachrichten(con, pid),
         "/api/teamchat": workbench.daten_teamchat(con, pid),
         "/api/fragen?alle=1": workbench.daten_fragen(con, pid, True),
         "/api/wissen": workbench.daten_wissen(con, pid, {"q": [""]}),
         "/api/betrieb": _betrieb_ohne_namen(workbench.daten_betrieb(con, pid)),
         "/api/releases": workbench.daten_releases(con, pid),
         "/api/versionshinweise": workbench.daten_versionshinweise(con, pid),
         "/api/projekte": workbench.daten_projekte(con, pid),
         "/api/einstellungen": workbench.daten_einstellungen(con, pid, speicher),
         "/api/agenten": workbench.daten_agenten_alle(con, pid),
         "/api/planung": workbench.daten_planung(con, pid),
         "/api/verlauf": workbench.daten_verlauf(con, pid, {"tage": ["3"]}),
         "/api/seit": verlauf.seit_daten(con, pid),
         "/api/listen": workbench.daten_listen(con, pid),
         "/api/themen": workbench.daten_themen(con, pid)}
    a["/api/start"]["heimnetz"] = None                   # Heimnetz (A1643): nur am PC von Belang
    eigen = con.execute("SELECT name FROM projekt WHERE id = ?", (pid,)).fetchone()["name"]
    re_ = a["/api/start"].get("rechner")
    if isinstance(re_, dict):                     # Vorrang der Projekte (A1623): fremde Projektnamen bleiben am PC
        re_["vorrang"] = [x for x in re_.get("vorrang") or [] if x["projekt"] == eigen]
    pc = a["/api/einstellungen"].get("pc") or {}
    pc["vorrang"] = {k: v for k, v in (pc.get("vorrang") or {}).items() if k == eigen}
    pc["vorrang_projekte"] = [eigen]
    for t in a["/api/themen"]:
        a[f"/api/thema?id={t['id']}"] = workbench.daten_thema(con, pid, t["id"])
    for s in SICHTEN:
        a[f"/api/aufgaben?sicht={s}"] = workbench.daten_aufgaben(con, pid, {"sicht": [s], **leer})
    for (aid,) in con.execute("SELECT id FROM aufgabe WHERE projekt_id = ? AND (status IN ('wartet', 'laeuft', 'blockiert')"
                              " OR fertig_utc >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', '-3 days'))", (pid,)).fetchall():
        a[f"/api/aufgabe?id={aid}"] = workbench.daten_aufgabe(con, pid, aid)      # offene und kürzlich abgeschlossene
    a.update(dokument_ansichten(con, pid))
    return a


_texte = {}          # sha → Text (Inhalt je Prüfsumme unveränderlich)


def _text(sha, endung):
    from . import dokumente
    if sha not in _texte:
        with open(dokumente.datei_pfad(sha, endung), "rb") as f:
            t = f.read().decode("utf-8", errors="replace")
        _texte[sha] = t if len(t) <= TEXT_MAX else t[:TEXT_MAX] + "\n\n… (gekürzt – vollständig am PC)"
    return _texte[sha]


def dokument_ansichten(con, pid):
    """Dokumente online: die ganze Liste mit Suchtext (gefiltert wird in web/api.php wie am PC), je Dokument die Details mit
    den Texten aller Text-Versionen und – nie ausgeliefert – welche Datei zu welcher Version gehört (nur Dokumente, die
    auch online stehen)."""
    from . import dokumente
    basis = workbench.daten_dokumente(con, pid, {"status": ["alle"]})
    such = {r[0]: r[1] for r in con.execute(
        "SELECT v.dokument_id, substr(group_concat(substr(coalesce(v.suchtext, ''), 1, 20000), ' '), 1, 30000)"
        " FROM dokument_version v JOIN dokument d ON d.id = v.dokument_id WHERE d.projekt_id = ? GROUP BY v.dokument_id", (pid,))}
    liste = []
    for d in basis["dokumente"]:
        if d["status"] != "geloescht":
            liste.append({**d, "such": f"{d['titel']} {such.get(d['id']) or ''}".lower()})
    a = {"/api/dokumente": {**basis, "dokumente": liste}}
    dateien = {}
    versionen = {}
    for did, nr, sha, endung in con.execute(
            "SELECT v.dokument_id, v.nr, v.sha256, v.endung FROM dokument_version v JOIN dokument d ON d.id = v.dokument_id"
            " WHERE d.projekt_id = ? ORDER BY v.dokument_id, v.nr", (pid,)):
        versionen.setdefault(did, []).append((nr, sha, endung))
    gespraeche = {}
    for r in con.execute(
            "SELECT n.dokument_id, n.id, n.zeit_utc, n.von, n.art, n.kurz, n.text, (SELECT group_concat(agent, ', ') FROM empfang"
            " WHERE nachricht_id = n.id) AS an FROM nachricht n WHERE n.projekt_id = ? AND n.dokument_id IS NOT NULL ORDER BY n.id", (pid,)):
        gespraeche.setdefault(r[0], []).append(dict(zip(("id", "zeit_utc", "von", "art", "kurz", "text", "an"), tuple(r)[1:])))
    for did, online, status in con.execute("SELECT id, online, status FROM dokument WHERE projekt_id = ?", (pid,)).fetchall():
        try:
            d = workbench.daten_dokument(con, pid, {"id": [str(did)]}, gespraeche.get(did, []))
        except (kern.AmwFehler, OSError) as e:        # Datei fehlt in der Ablage: dieses Dokument online auslassen
            log.warning("D%s nicht online: %s", did, e)
            continue
        d.pop("text", None)
        d.pop("gezeigt", None)
        if status != "geloescht":
            texte = {}
            for nr, sha, endung in versionen.get(did, []):
                vorschau = dokumente.FORMATE.get(endung, ("", "", "download"))[2]
                if vorschau == "text":
                    try:
                        texte[str(nr)] = _text(sha, endung)
                    except OSError:
                        pass
                elif online:
                    dateien[f"{did}:{nr}"] = [sha, endung]
                    dateien[f"{did}:0"] = [sha, endung]
            d["texte"] = texte
        a[f"/api/dokument?id={did}"] = d
    a["/intern/dateien"] = dateien
    return a


INDEX_S = 900        # Suchindex höchstens alle 15 min (gepackt ~1 MB; nur bei Änderung)


def suchindex(con, pid):
    """Für die Suche online (web/api.php): Aufgaben, Beschlüsse, Fragen, Wortlaut vollständig, Nachrichten die
    letzten 2000 (nur Kurztext). Je Eintrag [art, ref, titel, suchtext, zusatz, zeit]; gepackt (zlib + Base64)."""
    teile = [
        ("aufgabe", "SELECT 'A' || id, titel, substr(coalesce(bemerkung, ''), 1, 300), status, angelegt_utc FROM aufgabe"
                    " WHERE projekt_id = ? ORDER BY id DESC"),
        ("beschluss", "SELECT 'B' || id, stichwort, substr(regel, 1, 400), status, zeit_utc FROM beschluss WHERE projekt_id = ?"
                      " ORDER BY id DESC"),
        ("frage", "SELECT 'F' || id, kurz, substr(coalesce(antwort, ''), 1, 300),"
                  " CASE WHEN status = 'offen' AND geparkt_utc IS NOT NULL THEN 'geparkt' ELSE status END, zeit_utc FROM frage"
                  " WHERE projekt_id = ? ORDER BY id DESC"),
        ("wortlaut", "SELECT 'W' || id, substr(text, 1, 200), substr(text, 201, 400), kanal, zeit_utc FROM wortlaut"
                     " WHERE projekt_id = ? ORDER BY id DESC"),
        ("nachricht", "SELECT '#' || id, kurz, '', von, zeit_utc FROM nachricht WHERE projekt_id = ? ORDER BY id DESC LIMIT 2000"),
    ]
    eintraege = [[art, *r] for art, sql in teile for r in con.execute(sql, (pid,))]
    roh = json.dumps(eintraege, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {"gepackt": base64.b64encode(zlib.compress(roh, 9)).decode("ascii"), "anzahl": len(eintraege)}


def _ruhig(inhalt):
    """Eine Ansicht ohne das, was sich von selbst ständig ändert: Zeitstempel, freier Arbeitsspeicher, freier Platz, Größe
    der Dauer-Belegung, „jetzt“ im Tagesverlauf, die Hochrechnung des Wochenlimits. Diese Werte werden mitgeschickt,
    sobald sich sonst etwas ändert – allein lösen sie kein Hochladen aus. Was eine Aussage ändert (ein Laufwerk wird
    knapp, ein Programm kommt dazu, ein Lauf startet oder endet, ein neuer Messwert des Verbrauchs), bleibt drin."""
    if not isinstance(inhalt, dict):
        return inhalt
    d = {k: v for k, v in inhalt.items() if k not in ("zeit", "speicher")}
    namen = lambda liste: [x.get("name") for x in liste or [] if isinstance(x, dict)]
    stufen = lambda liste: [(x.get("laufwerk"), x.get("stufe")) for x in liste or [] if isinstance(x, dict)]
    r = d.get("rechner")
    if isinstance(r, dict) and "laufwerke" in r:                      # Einstellungen: Laufwerke und Aufräumvorschläge
        d["rechner"] = {"laufwerke": stufen(r.get("laufwerke")),
                        "aufraeumen": [x.get("name") for x in (r.get("aufraeumen") or {}).get("sicherungen", [])],
                        "archiv": r.get("archiv"),
                        "zuwaechse": [(x.get("ordner"), x.get("plus")) for x in r.get("zuwaechse") or []],
                        "ablagerungen": [(x.get("ordner"), x.get("bytes")) for x in r.get("ablagerungen") or []]}
    elif isinstance(r, dict):                                         # Startseite: Auslastung des Rechners
        d["rechner"] = {**{k: v for k, v in r.items() if k not in ("frei_gb", "dauer_gb", "dauer", "platte")},
                        "dauer": namen(r.get("dauer")), "platte": stufen(r.get("platte"))}
    t = d.get("token")
    if isinstance(t, dict):                                           # Wochenlimit: der Messwert zählt, nicht die Hochrechnung
        d["token"] = {k: t.get(k) for k in ("wert", "reset_utc", "unsicher")}
    h = d.get("rechner_heute")
    if isinstance(h, dict):                                           # Tagesverlauf: Läufe und ihre Zustände
        d["rechner_heute"] = {"laeufe": [[l.get(k) for k in ("id", "eigen", "status", "start_utc", "ende_utc", "erwartet_min", "gb")]
                                         for l in h.get("laeufe") or []],
                              "dauer": namen(h.get("dauer")), "von_utc": h.get("von_utc"),
                              "tage": [(x.get("tag"), x.get("laeufe")) for x in h.get("tage") or []]}
    return d


def _pruef(inhalt):
    # Zeitstempel und Messwerte ändern sich ständig – sie allein lösen kein Hochladen aus (siehe _ruhig)
    return hashlib.sha256(json.dumps(_ruhig(inhalt), ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:32]


class Abgleich:
    def __init__(self, con, speicher, pid=None):
        self.con, self.sp = con, speicher
        self.nur = pid                         # nur dieses Projekt (Tests); sonst alle Projekte dieser AMW
        self.bekannt = {}                      # Schlüssel „<uid>:<weg>“ → Prüfsumme, wie sie online liegt
        self.alt_weg = False                   # Ansichten aus der Zeit vor den Projekt-Kennungen sind gelöscht
        self.letzt_hoch = self.letzt_puls = self.letzt_index = self.letzt_oben = 0.0
        self.oben = {}                         # sha → Status der Dateien im Speicher (unterwegs | abgelegt)
        self.paare = set()                     # (sha, uid): welche Datei zu welchem Projekt gehört
        self.con.execute("CREATE TABLE IF NOT EXISTS netz_eingang (id INTEGER PRIMARY KEY, ergebnis TEXT,"
                         " zeit_utc TEXT NOT NULL)")
        # Merkmal = Zeit + Weg + Inhalt: eine neue Online-Datenbank zählt wieder ab 1 – die Nummer allein reicht nicht
        if "merkmal" not in [r[1] for r in self.con.execute("PRAGMA table_info(netz_eingang)")]:
            self.con.execute("ALTER TABLE netz_eingang ADD COLUMN merkmal TEXT")

    @property
    def pid(self):
        """Erstes Projekt: dorthin gehören Befehle ohne Kennung (Seite von vor 1.19.0)."""
        return self.nur or self.con.execute("SELECT min(id) FROM projekt").fetchone()[0]

    def projekte(self):
        """[(pid, uid)] der Projekte, die dieser Rechner online hält."""
        if self.nur:
            return [tuple(r) for r in self.con.execute("SELECT id, uid FROM projekt WHERE id = ?", (self.nur,))]
        return [tuple(r) for r in self.con.execute("SELECT id, uid FROM projekt ORDER BY id")]

    def schema(self):
        self.sp.ausfuehren([(s, []) for s in SCHEMA])
        nachruesten(self.sp)
        self.bekannt = {w: p for w, p in self.sp.ausfuehren([("SELECT weg, pruef FROM ansicht", [])])[0]}
        self.oben_laden()

    def oben_laden(self):
        alt = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=HOCH_ALT_S)).strftime("%Y-%m-%dT%H:%M:%SZ")
        oben, paare = self.sp.ausfuehren([
            ("SELECT sha, status FROM datei", []),
            ("SELECT sha, projekt FROM datei_projekt", []),
            # Uploads vom Handy, die nie fertig wurden (Funkloch, Seite zu): nach einem Tag weg
            ("DELETE FROM hoch_teil WHERE id IN (SELECT id FROM hoch WHERE zeit_utc < ?)", [alt]),
            ("DELETE FROM hoch WHERE zeit_utc < ?", [alt])])[:2]
        self.oben = {s: st for s, st in oben}
        self.paare = {(s, p) for s, p in paare}       # welche Datei zu welchem Projekt gehört (alle Rechner)
        self.letzt_oben = time.time()

    def dateien(self):
        """Dateien der Dokumente, die auch online stehen, zum Webspace reichen; nicht mehr gebrauchte abmelden.
        Je Projekt (datei_projekt): eine Datei verschwindet erst, wenn kein Projekt – auch keines eines anderen
        Rechners – sie mehr nennt. Gibt die Zahl der hochgeladenen und abgemeldeten Dateien zurück."""
        from . import dokumente
        soll, soll_paare = {}, set()
        for pid, uid in self.projekte():
            for sha, endung, groesse in self.con.execute(
                    "SELECT DISTINCT v.sha256, v.endung, v.groesse FROM dokument_version v JOIN dokument d ON d.id = v.dokument_id"
                    " WHERE d.projekt_id = ? AND d.online = 1 AND d.status != 'geloescht'", (pid,)):
                if dokumente.FORMATE.get(endung, ("", "", "download"))[2] != "text":   # Texte gehen als Ansicht mit
                    soll[sha] = (endung, groesse)
                    soll_paare.add((sha, uid))
        meine = {u for _, u in self.projekte()}
        neu_paare = soll_paare - self.paare
        alt_paare = {(s, u) for s, u in self.paare if u in meine and (s, u) not in soll_paare}
        if neu_paare or alt_paare:
            self.sp.ausfuehren([("INSERT INTO datei_projekt (sha, projekt) VALUES (?, ?) ON CONFLICT DO NOTHING", [s, u])
                                for s, u in neu_paare] + [("DELETE FROM datei_projekt WHERE sha = ? AND projekt = ?", [s, u])
                                                          for s, u in alt_paare])
            self.paare = (self.paare | neu_paare) - alt_paare
        genannt = {s for s, _ in self.paare}
        weg = [s for s in self.oben if s not in soll and s not in genannt]     # auch Altbestand ohne Projekt
        if weg:                                       # frisch nachsehen: ein anderer Rechner kann sie gerade angemeldet haben
            noch = {r[0] for r in self.sp.ausfuehren([(f"SELECT DISTINCT sha FROM datei_projekt WHERE sha IN"
                                                        f" ({', '.join('?' for _ in weg)})", weg)])[0]}
            self.paare |= {(s, u) for s, u in self.sp.ausfuehren([(f"SELECT sha, projekt FROM datei_projekt WHERE sha IN"
                                                                   f" ({', '.join('?' for _ in noch)})", list(noch))])[0]} if noch else set()
            weg = [s for s in weg if s not in noch]
        if weg:
            self.sp.ausfuehren([a for s in weg for a in (("DELETE FROM datei WHERE sha = ?", [s]),
                                                         ("DELETE FROM datei_teil WHERE sha = ?", [s]))])
            for s in weg:
                self.oben.pop(s)
        budget, n = DATEIEN_JE_SCHRITT, 0
        for sha, (endung, _) in sorted(soll.items(), key=lambda x: x[1][1]):       # kleine zuerst
            if sha in self.oben:
                continue
            if budget <= 0:
                break
            try:
                with open(dokumente.datei_pfad(sha, endung), "rb") as f:
                    roh = f.read()
            except OSError:
                log.warning("Datei %s… fehlt in der Ablage – nicht hochgeladen", sha[:12])
                continue
            if hashlib.sha256(roh).hexdigest() != sha:
                log.warning("Datei %s… passt nicht zur Prüfsumme – nicht hochgeladen", sha[:12])
                continue
            teile = [roh[i:i + TEIL] for i in range(0, len(roh), TEIL)] or [b""]
            self.sp.ausfuehren([("DELETE FROM datei_teil WHERE sha = ?", [sha])])
            for i in range(0, len(teile), TEILE_JE_ANFRAGE):
                self.sp.ausfuehren([("INSERT INTO datei_teil (sha, nr, inhalt) VALUES (?, ?, ?)",
                                     [sha, i + j, base64.b64encode(t).decode("ascii")])
                                    for j, t in enumerate(teile[i:i + TEILE_JE_ANFRAGE])])
            # erst wenn alle Teile da sind, erfährt die Seite von der Datei
            self.sp.ausfuehren([("INSERT INTO datei (sha, endung, groesse, teile, status, zeit_utc) VALUES (?, ?, ?, ?,"
                                 " 'unterwegs', ?) ON CONFLICT(sha) DO UPDATE SET status = 'unterwegs', teile = excluded.teile,"
                                 " zeit_utc = excluded.zeit_utc", [sha, endung, len(roh), len(teile), db.jetzt()])])
            self.oben[sha] = "unterwegs"
            budget -= len(roh)
            n += 1
        return n + len(weg)

    def hochladen(self, alle=False):
        """Ansichten aller eigenen Projekte unter „<uid>:<weg>“, dazu das Verzeichnis und „zuletzt gesehen“ je Projekt."""
        from . import einstellungen
        t = db.jetzt()
        neu, n = [], 0
        index = alle or time.time() - self.letzt_index >= INDEX_S
        rechner = einstellungen.wert("rechner")
        verzeichnis = []
        for pid, uid in self.projekte():
            alle_ansichten = ansichten(self.con, pid, self.sp)
            if index:
                alle_ansichten["/api/suchindex"] = suchindex(self.con, pid)
            for weg, inhalt in alle_ansichten.items():
                p = _pruef(inhalt)
                if alle or self.bekannt.get(f"{uid}:{weg}") != p:
                    neu.append((f"{uid}:{weg}", json.dumps(inhalt, ensure_ascii=False), p))
            e = next(x for x in workbench.daten_projekte(self.con, pid)["projekte"] if x["uid"] == uid)
            verzeichnis.append(("INSERT INTO projekt (uid, name, farbe, rechner, gesehen_utc, fragen, agenten, halt) VALUES"
                                " (?, ?, ?, ?, ?, ?, ?, ?) ON CONFLICT(uid) DO UPDATE SET name = excluded.name, farbe = excluded.farbe,"
                                " rechner = excluded.rechner, gesehen_utc = excluded.gesehen_utc, fragen = excluded.fragen,"
                                " agenten = excluded.agenten, halt = excluded.halt",
                                [uid, e["name"], e["farbe"], rechner, t, e["fragen"], e["agenten"], int(e["halt"])]))
            verzeichnis.append(("INSERT INTO zustand (schluessel, wert) VALUES (?, ?) ON CONFLICT(schluessel)"
                                " DO UPDATE SET wert = excluded.wert", [f"pc_gesehen_utc:{uid}", t]))
        if index:
            self.letzt_index = time.time()
        for i in range(0, len(neu), 40):             # nicht alles in eine Anfrage (viele Projekte, große Ansichten)
            stueck = neu[i:i + 40]
            self.sp.ausfuehren([("INSERT INTO ansicht (weg, inhalt, pruef, stand_utc) VALUES (?, ?, ?, ?) ON CONFLICT(weg) DO UPDATE"
                                 " SET inhalt = excluded.inhalt, pruef = excluded.pruef, stand_utc = excluded.stand_utc", [w, i_, p, t])
                                for w, i_, p in stueck])
            for w, _, p in stueck:
                self.bekannt[w] = p
            n += len(stueck)
        verzeichnis.append(("INSERT INTO zustand (schluessel, wert) VALUES ('pc_gesehen_utc', ?) ON CONFLICT(schluessel)"
                            " DO UPDATE SET wert = excluded.wert", [t]))          # für Seiten von vor 1.19.0
        from . import benutzer                        # Benutzer ohne Passwort und Geheimnis – die setzt jeder online selbst
        for b in benutzer.fuer_online(self.con):
            verzeichnis.append((benutzer.ONLINE_EINTRAGEN, [b["name"], b["anzeige"], b["email"], b["rolle"], b["gesperrt"], b["projekte"], t]))
        if not self.alt_weg:                          # Ansichten ohne Kennung (vor 1.19.0) – jetzt doppelt: weg
            verzeichnis.append(("DELETE FROM ansicht WHERE weg LIKE '/%'", []))
            self.alt_weg = True
            for w in [w for w in self.bekannt if w.startswith("/")]:
                self.bekannt.pop(w)
        self.sp.ausfuehren(verzeichnis)
        self.verzeichnis_lesen()
        return n

    def verzeichnis_lesen(self):
        """Alle Projekte im Online-Speicher (auch anderer Rechner) für die Projekt-Auswahl am PC merken."""
        spalten = ("uid", "name", "farbe", "rechner", "gesehen_utc", "fragen", "agenten", "halt")
        zeilen = self.sp.ausfuehren([(f"SELECT {', '.join(spalten)} FROM projekt ORDER BY name", [])])[0]
        VERZEICHNIS["projekte"] = [dict(zip(spalten, z)) for z in zeilen]
        VERZEICHNIS["stand"] = time.time()

    def eingang(self):
        """Neue Zeilen aus dem Briefkasten ausführen – nur die der eigenen Projekte (Kennung), dazu Zeilen ohne Kennung
        (Seite von vor 1.19.0) im ersten Projekt. Gibt die Zahl der bearbeiteten Zeilen zurück."""
        eigene = dict((uid, pid) for pid, uid in self.projekte())
        if not eigene:
            return 0
        platz = ", ".join("?" for _ in eigene)
        zeilen = self.sp.ausfuehren([(f"SELECT id, weg, daten, zeit_utc, projekt FROM eingang WHERE status = 'neu'"
                                      f" AND (projekt IN ({platz}) OR projekt IS NULL OR projekt = '') ORDER BY id LIMIT 20",
                                      list(eigene))])[0]
        for eid, weg, roh, zeit, uid in zeilen:
            eid = int(eid)
            pid = eigene.get(uid) or self.pid
            merkmal = hashlib.sha256(f"{zeit}|{weg}|{roh}".encode("utf-8")).hexdigest()[:24]
            schon = self.con.execute("SELECT ergebnis, merkmal FROM netz_eingang WHERE id = ?", (eid,)).fetchone()
            # gleiche Nummer, anderer Eintrag (neue Online-Datenbank) – alte Zeilen ohne Merkmal gelten nicht als Beleg:
            # abgeholt werden nur Einträge im Status „neu“, erledigte kommen ohnehin nie wieder
            if schon and schon[1] != merkmal:
                self.con.execute("DELETE FROM netz_eingang WHERE id = ?", (eid,))
                schon = None
            if schon:                                  # schon ausgeführt, nur die Rückmeldung fehlte
                status, ergebnis = json.loads(schon[0])
            else:
                try:
                    daten = json.loads(roh)
                    if daten == []:                    # PHP schreibt ein leeres Objekt als []
                        daten = {}
                    if not isinstance(daten, dict):
                        raise aktionen.Ungueltig("Daten")
                    status, ergebnis = "erledigt", aktionen.ausfuehren(self.con, pid, weg, daten, kanal="netz",
                                                                        speicher=self.sp)
                except (aktionen.Ungueltig, kern.AmwFehler, LookupError, ValueError) as e:
                    status, ergebnis = "fehler", {"fehler": str(e) or type(e).__name__}
                self.con.execute("INSERT INTO netz_eingang (id, ergebnis, zeit_utc, merkmal) VALUES (?, ?, ?, ?)",
                                 (eid, json.dumps([status, ergebnis], ensure_ascii=False), db.jetzt(), merkmal))
                log.info("Briefkasten #%s %s → %s", eid, weg, status)
                if weg == "/api/dokument/neu":
                    self.hoch_weg(roh)
            self.sp.ausfuehren([("UPDATE eingang SET status = ?, ergebnis = ?, erledigt_utc = ? WHERE id = ?",
                                 [status, json.dumps(ergebnis, ensure_ascii=False), db.jetzt(), eid])])
        if any(w == "/api/dokument/neu" for _, w, _, _, _ in zeilen):
            self.oben_laden()                          # die Seite hat ihre Kopie schon abgelegt – nicht noch einmal hochladen
        return len(zeilen)

    def gespraeche(self):
        """Gesprächsansicht online nur auf Wunsch: Die Seite setzt beim Abruf zustand „gespraech:<Agent>“ (Zeit). Solange
        der Wunsch jünger als GESPRAECH_S ist, hält der PC die Ansicht aktuell (nur Text, Werkzeugnamen, Geheimnisse
        verdeckt); danach löscht er sie wieder. Rückgabe: Zahl der geänderten Ansichten."""
        from . import gespraech
        grenze = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=GESPRAECH_S)).strftime("%Y-%m-%dT%H:%M:%SZ")
        eigene = dict((uid, pid) for pid, uid in self.projekte())
        # Schlüssel „gespraech:<uid>:<Kennung>“; ältere ohne Kennung des Projekts räumt der Rechner des ersten Projekts weg
        zeilen = self.sp.ausfuehren([("SELECT schluessel, wert FROM zustand WHERE schluessel LIKE 'gespraech:%'", [])])[0]
        bekannt = {(uid, k) for uid, pid in eigene.items()
                   for (k,) in self.con.execute("SELECT kennung FROM agent WHERE projekt_id = ?", (pid,))}
        teile = {s: tuple(s.split(":", 2)[1:]) if s.count(":") == 2 else (None, s[10:]) for s, _ in zeilen}
        wunsch = {teile[s] for s, w in zeilen if str(w) >= grenze and teile[s] in bekannt}
        anw = [("DELETE FROM zustand WHERE schluessel = ?", [s]) for s, w in zeilen
               if teile[s] not in wunsch and (teile[s][0] in eigene or teile[s][0] is None)]
        for schl in [w for w in self.bekannt if ":/api/gespraech?kennung=" in w]:
            uid, weg = schl.split(":", 1)
            if uid in eigene and (uid, weg.split("=", 1)[1]) not in wunsch:
                anw.append(("DELETE FROM ansicht WHERE weg = ?", [schl]))
                self.bekannt.pop(schl)
        t, n = db.jetzt(), len(anw)
        for uid, k in sorted(wunsch):
            weg = f"{uid}:/api/gespraech?kennung={k}"
            try:
                d = gespraech.daten(self.con, eigene[uid], k, online=True)
            except (OSError, kern.AmwFehler, LookupError) as e:
                d = {"kennung": k, "eintraege": [], "fehler": str(e)}
            for x in ("ab", "vor", "sitzungen"):
                d.pop(x, None)
            p = _pruef(d)
            if self.bekannt.get(weg) != p:
                anw.append(("INSERT INTO ansicht (weg, inhalt, pruef, stand_utc) VALUES (?, ?, ?, ?) ON CONFLICT(weg) DO UPDATE"
                            " SET inhalt = excluded.inhalt, pruef = excluded.pruef, stand_utc = excluded.stand_utc",
                            [weg, json.dumps(d, ensure_ascii=False), p, t]))
                self.bekannt[weg] = p
                n += 1
        if anw:
            self.sp.ausfuehren(anw)
        return n

    def hoch_weg(self, daten):
        """Teile eines Uploads im Speicher löschen – nach dem Übernehmen und auch, wenn er nicht übernommen wurde."""
        try:
            hid = str(json.loads(daten).get("hoch") or "")
        except (ValueError, AttributeError):
            return
        if re.fullmatch(r"[0-9a-f]{32}", hid):
            self.sp.ausfuehren([("DELETE FROM hoch_teil WHERE id = ?", [hid]), ("DELETE FROM hoch WHERE id = ?", [hid])])

    def schritt(self, geaendert):
        """Ein Durchgang der Schleife; `geaendert`: die lokale Datenbank hat sich seit dem letzten Mal geändert."""
        jetzt = time.time()
        sofort = bool(self.eingang())               # der Mensch wartet online auf das Ergebnis: nicht auf den Takt warten
        if sofort:
            geaendert = True
        self.gespraeche()
        if jetzt - self.letzt_oben >= PULS_S:       # die Seite meldet eine verlorene Kopie ab – dann neu hochladen
            self.oben_laden()
        self.dateien()
        if (geaendert and (sofort or jetzt - self.letzt_hoch >= HOCH_S)) or jetzt - self.letzt_puls >= PULS_S:
            self.hochladen()
            self.letzt_hoch = self.letzt_puls = jetzt
            return True
        return False


def schleife(stop=None):
    """Eigener Faden im Dienst: eigene Verbindung, Netzfehler halten den Wecker nie auf."""
    sp = speicher_aus_zugang()
    if sp is None:
        return
    con = db.verbinde()
    ab = Abgleich(con, sp)
    stand, offen = None, False
    while not (stop and stop.is_set()):
        try:
            if not ab.bekannt and ab.letzt_puls == 0:
                ab.schema()
            v = con.execute("PRAGMA data_version").fetchone()[0]
            offen = offen or v != stand
            stand = v
            if ab.schritt(offen):
                offen = False
        except Exception as e:                       # Netz weg, Turso gesperrt …: nur protokollieren
            log.warning("Synchronisierung: %s: %s", type(e).__name__, e)
            time.sleep(60)
        time.sleep(EINGANG_S)


def starten():
    if speicher_aus_zugang() is None:
        return None
    f = threading.Thread(target=schleife, name="abgleich", daemon=True)
    f.start()
    return f
