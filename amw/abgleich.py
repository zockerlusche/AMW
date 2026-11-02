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
]
SICHTEN = ("offen", "geparkt", "pool", "erledigt")

# Online-Seite (web/inc/lib.php liest dieselben Werte mit denselben Grenzen)
WEB_EINSTELLUNGEN = {"leerlauf_min": (30, 5, 240), "hoechstens_h": (12, 1, 72), "fehl_je_ip": (5, 3, 20),
                     "fehl_gesamt": (20, 5, 200)}


def web_einstellungen(speicher):
    """Aktuelle Werte der Online-Seite (Vorgaben, wo nichts gesetzt ist)."""
    roh = speicher.ausfuehren([("SELECT wert FROM zustand WHERE schluessel = 'web_einstellungen'", [])])[0]
    d = json.loads(roh[0][0]) if roh else {}
    return {k: (int(d[k]) if k in d and lo <= int(d[k]) <= hi else v) for k, (v, lo, hi) in WEB_EINSTELLUNGEN.items()}


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

class TursoSpeicher:
    """Turso über HTTP /v2/pipeline (nur Standardbibliothek). Eine Anfrage = eine Folge von Anweisungen."""

    def __init__(self, url, token):
        url = url.strip()
        if url.startswith("libsql://"):
            url = "https://" + url[len("libsql://"):]
        self.url, self._token = url.rstrip("/") + "/v2/pipeline", token.strip()

    @staticmethod
    def _wert(v):
        if v is None:
            return {"type": "null"}
        if isinstance(v, int):
            return {"type": "integer", "value": str(v)}
        return {"type": "text", "value": str(v)}

    def ausfuehren(self, anweisungen):
        body = {"requests": [{"type": "execute", "stmt": {"sql": sql, "args": [self._wert(x) for x in args]}}
                             for sql, args in anweisungen] + [{"type": "close"}]}
        req = urllib.request.Request(self.url, data=json.dumps(body).encode("utf-8"), method="POST",
                                     headers={"Authorization": f"Bearer {self._token}",
                                              "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
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
    return TursoSpeicher(z["url"], z["token"])


# --- Abgleich ------------------------------------------------------------------------------------

def hoch_holen(sp, hid):
    """Upload vom Handy aus dem Speicher holen (die Seite hat ihn in Teilen abgelegt) → (roh, name). Prüft Größe und
    Prüfsumme; die Teile löscht danach Abgleich.hoch_weg."""
    from . import dokumente
    hid = str(hid or "")
    if not re.fullmatch(r"[0-9a-f]{32}", hid):
        raise kern.AmwFehler("Upload-Kennung")
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


def ansichten(con, pid, speicher=None):
    """Dieselben Antworten wie die lokale Workbench, Schlüssel = Weg, wie ihn die Seite anfragt."""
    leer = {"agent": [""], "q": [""]}
    a = {"/api/start": workbench.daten_start(con, pid),
         "/api/fragen": workbench.daten_fragen(con, pid),
         "/api/fragen?alle=1": workbench.daten_fragen(con, pid, True),
         "/api/wissen": workbench.daten_wissen(con, pid, {"q": [""]}),
         "/api/betrieb": workbench.daten_betrieb(con, pid),
         "/api/releases": workbench.daten_releases(con, pid),
         "/api/projekte": workbench.zeilen(con.execute("SELECT id, name FROM projekt ORDER BY id")),
         "/api/einstellungen": workbench.daten_einstellungen(con, pid, speicher),
         "/api/agenten": workbench.daten_agenten_alle(con, pid),
         "/api/planung": workbench.daten_planung(con, pid),
         "/api/verlauf": workbench.daten_verlauf(con, pid, {"tage": ["3"]}),
         "/api/seit": verlauf.seit_daten(con, pid)}
    for s in SICHTEN:
        a[f"/api/aufgaben?sicht={s}"] = workbench.daten_aufgaben(con, pid, {"sicht": [s], **leer})
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
        ("frage", "SELECT 'F' || id, kurz, substr(coalesce(antwort, ''), 1, 300), status, zeit_utc FROM frage"
                  " WHERE projekt_id = ? ORDER BY id DESC"),
        ("wortlaut", "SELECT 'W' || id, substr(text, 1, 200), substr(text, 201, 400), kanal, zeit_utc FROM wortlaut"
                     " WHERE projekt_id = ? ORDER BY id DESC"),
        ("nachricht", "SELECT '#' || id, kurz, '', von, zeit_utc FROM nachricht WHERE projekt_id = ? ORDER BY id DESC LIMIT 2000"),
    ]
    eintraege = [[art, *r] for art, sql in teile for r in con.execute(sql, (pid,))]
    roh = json.dumps(eintraege, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    return {"gepackt": base64.b64encode(zlib.compress(roh, 9)).decode("ascii"), "anzahl": len(eintraege)}


def _pruef(inhalt):
    # Zeitstempel und freier Speicher ändern sich ständig – sie allein lösen kein Hochladen aus
    if isinstance(inhalt, dict):
        inhalt = {k: v for k, v in inhalt.items() if k not in ("zeit", "speicher")}
    return hashlib.sha256(json.dumps(inhalt, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:32]


class Abgleich:
    def __init__(self, con, speicher, pid=None):
        self.con, self.sp = con, speicher
        self.pid = pid or con.execute("SELECT min(id) FROM projekt").fetchone()[0]
        self.bekannt = {}                      # weg → Prüfsumme, wie sie online liegt
        self.letzt_hoch = self.letzt_puls = self.letzt_index = self.letzt_oben = 0.0
        self.oben = {}                         # sha → Status der Dateien im Speicher (unterwegs | abgelegt)
        self.con.execute("CREATE TABLE IF NOT EXISTS netz_eingang (id INTEGER PRIMARY KEY, ergebnis TEXT,"
                         " zeit_utc TEXT NOT NULL)")
        # Merkmal = Zeit + Weg + Inhalt: eine neue Online-Datenbank zählt wieder ab 1 – die Nummer allein reicht nicht
        if "merkmal" not in [r[1] for r in self.con.execute("PRAGMA table_info(netz_eingang)")]:
            self.con.execute("ALTER TABLE netz_eingang ADD COLUMN merkmal TEXT")

    def schema(self):
        self.sp.ausfuehren([(s, []) for s in SCHEMA])
        self.bekannt = {w: p for w, p in self.sp.ausfuehren([("SELECT weg, pruef FROM ansicht", [])])[0]}
        self.oben_laden()

    def oben_laden(self):
        alt = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=HOCH_ALT_S)).strftime("%Y-%m-%dT%H:%M:%SZ")
        self.oben = {s: st for s, st in self.sp.ausfuehren([
            ("SELECT sha, status FROM datei", []),
            # Uploads vom Handy, die nie fertig wurden (Funkloch, Seite zu): nach einem Tag weg
            ("DELETE FROM hoch_teil WHERE id IN (SELECT id FROM hoch WHERE zeit_utc < ?)", [alt]),
            ("DELETE FROM hoch WHERE zeit_utc < ?", [alt])])[0]}
        self.letzt_oben = time.time()

    def dateien(self):
        """Dateien der Dokumente, die auch online stehen, zum Webspace reichen; nicht mehr gebrauchte abmelden.
        Gibt die Zahl der hochgeladenen und abgemeldeten Dateien zurück."""
        from . import dokumente
        soll = {}
        for sha, endung, groesse in self.con.execute(
                "SELECT DISTINCT v.sha256, v.endung, v.groesse FROM dokument_version v JOIN dokument d ON d.id = v.dokument_id"
                " WHERE d.projekt_id = ? AND d.online = 1 AND d.status != 'geloescht'", (self.pid,)):
            if dokumente.FORMATE.get(endung, ("", "", "download"))[2] != "text":   # Texte gehen als Ansicht mit
                soll[sha] = (endung, groesse)
        weg = [s for s in self.oben if s not in soll]
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
        t = db.jetzt()
        neu = []
        alle_ansichten = ansichten(self.con, self.pid, self.sp)
        if alle or time.time() - self.letzt_index >= INDEX_S:
            alle_ansichten["/api/suchindex"] = suchindex(self.con, self.pid)
            self.letzt_index = time.time()
        for weg, inhalt in alle_ansichten.items():
            p = _pruef(inhalt)
            if alle or self.bekannt.get(weg) != p:
                neu.append((weg, json.dumps(inhalt, ensure_ascii=False), p))
        anw = [("INSERT INTO ansicht (weg, inhalt, pruef, stand_utc) VALUES (?, ?, ?, ?) ON CONFLICT(weg) DO UPDATE"
                " SET inhalt = excluded.inhalt, pruef = excluded.pruef, stand_utc = excluded.stand_utc", [w, i, p, t])
               for w, i, p in neu]
        anw.append(("INSERT INTO zustand (schluessel, wert) VALUES ('pc_gesehen_utc', ?) ON CONFLICT(schluessel)"
                    " DO UPDATE SET wert = excluded.wert", [t]))
        self.sp.ausfuehren(anw)
        for w, _, p in neu:
            self.bekannt[w] = p
        return len(neu)

    def eingang(self):
        """Neue Zeilen aus dem Briefkasten ausführen. Gibt die Zahl der bearbeiteten Zeilen zurück."""
        zeilen = self.sp.ausfuehren([("SELECT id, weg, daten, zeit_utc FROM eingang WHERE status = 'neu' ORDER BY id"
                                      " LIMIT 20", [])])[0]
        for eid, weg, roh, zeit in zeilen:
            eid = int(eid)
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
                    if not isinstance(daten, dict):
                        raise aktionen.Ungueltig("Daten")
                    status, ergebnis = "erledigt", aktionen.ausfuehren(self.con, self.pid, weg, daten, kanal="netz",
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
        if any(w == "/api/dokument/neu" for _, w, _, _ in zeilen):
            self.oben_laden()                          # die Seite hat ihre Kopie schon abgelegt – nicht noch einmal hochladen
        return len(zeilen)

    def gespraeche(self):
        """Gesprächsansicht online nur auf Wunsch: Die Seite setzt beim Abruf zustand „gespraech:<Agent>“ (Zeit). Solange
        der Wunsch jünger als GESPRAECH_S ist, hält der PC die Ansicht aktuell (nur Text, Werkzeugnamen, Geheimnisse
        verdeckt); danach löscht er sie wieder. Rückgabe: Zahl der geänderten Ansichten."""
        from . import gespraech
        grenze = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(seconds=GESPRAECH_S)).strftime("%Y-%m-%dT%H:%M:%SZ")
        zeilen = self.sp.ausfuehren([("SELECT schluessel, wert FROM zustand WHERE schluessel LIKE 'gespraech:%'", [])])[0]
        bekannt = {k for (k,) in self.con.execute("SELECT kennung FROM agent WHERE projekt_id = ?", (self.pid,))}
        wunsch = {k[10:] for k, w in zeilen if str(w) >= grenze and k[10:] in bekannt}
        anw = [("DELETE FROM zustand WHERE schluessel = ?", [k]) for k, w in zeilen if k[10:] not in wunsch]
        for weg in [w for w in self.bekannt if w.startswith("/api/gespraech?kennung=")]:
            if weg.split("=", 1)[1] not in wunsch:
                anw.append(("DELETE FROM ansicht WHERE weg = ?", [weg]))
                self.bekannt.pop(weg)
        t, n = db.jetzt(), len(anw)
        for k in sorted(wunsch):
            weg = f"/api/gespraech?kennung={k}"
            try:
                d = gespraech.daten(self.con, self.pid, k, online=True)
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
        if self.eingang():
            geaendert = True
        self.gespraeche()
        if jetzt - self.letzt_oben >= PULS_S:       # die Seite meldet eine verlorene Kopie ab – dann neu hochladen
            self.oben_laden()
        self.dateien()
        if (geaendert and jetzt - self.letzt_hoch >= HOCH_S) or jetzt - self.letzt_puls >= PULS_S:
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
            log.warning("Abgleich: %s: %s", type(e).__name__, e)
            time.sleep(60)
        time.sleep(EINGANG_S)


def starten():
    if speicher_aus_zugang() is None:
        return None
    f = threading.Thread(target=schleife, name="abgleich", daemon=True)
    f.start()
    return f
