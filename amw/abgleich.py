"""Stufe 2: Abgleich mit dem Online-Speicher (Turso) – Schaufenster + Briefkasten (→ doc/12-online.md).

Schaufenster: Der PC berechnet die Ansichten der Workbench (dieselben wie lokal) und legt sie als fertiges JSON in
`ansicht` ab, nur wenn sich etwas geändert hat. Die Seite im Netz zeigt nur diese Ansichten – sie sieht keine
Tabellen, und der PC ist aus dem Netz nicht erreichbar.
Briefkasten: Was der Entwickler online tut (Antwort, Nachricht, Halt, Weiter), schreibt die Seite als Zeile in
`eingang`. Der PC holt neue Zeilen ab, führt sie über denselben Weg wie die lokale Seite aus (aktionen.py) und
trägt das Ergebnis zurück. Jede Zeile wirkt höchstens einmal (lokale Liste `netz_eingang`).

Zugang: %LOCALAPPDATA%\\amw\\turso.json {"url", "token", "abgleich": true}. Ohne "abgleich": true bleibt alles aus.
Der Schlüssel wird nie ausgegeben oder protokolliert.
"""
import hashlib
import json
import logging
import os
import sqlite3
import threading
import time
import urllib.error
import urllib.request

from . import aktionen, db, kern, workbench

log = logging.getLogger("amw.abgleich")

HOCH_S = 30          # Ansichten höchstens so oft hochladen (nur bei Änderung)
PULS_S = 300         # spätestens dann Start/Betrieb neu (zeigt online: „PC zuletzt gesehen“)
EINGANG_S = 15       # Briefkasten so oft leeren

SCHEMA = [
    "CREATE TABLE IF NOT EXISTS ansicht (weg TEXT PRIMARY KEY, inhalt TEXT NOT NULL, pruef TEXT NOT NULL,"
    " stand_utc TEXT NOT NULL)",
    "CREATE TABLE IF NOT EXISTS eingang (id INTEGER PRIMARY KEY, zeit_utc TEXT NOT NULL, weg TEXT NOT NULL,"
    " daten TEXT NOT NULL, ip TEXT, status TEXT NOT NULL DEFAULT 'neu', ergebnis TEXT, erledigt_utc TEXT)",
    "CREATE INDEX IF NOT EXISTS eingang_neu ON eingang (status, id)",
    "CREATE TABLE IF NOT EXISTS versuch (id INTEGER PRIMARY KEY, zeit_utc TEXT NOT NULL, ip TEXT, ok INTEGER NOT NULL)",
    "CREATE INDEX IF NOT EXISTS versuch_zeit ON versuch (zeit_utc)",
    "CREATE TABLE IF NOT EXISTS zustand (schluessel TEXT PRIMARY KEY, wert TEXT)",
]
SICHTEN = ("offen", "geparkt", "pool", "erledigt")


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

def ansichten(con, pid):
    """Dieselben Antworten wie die lokale Workbench, Schlüssel = Weg, wie ihn die Seite anfragt."""
    leer = {"agent": [""], "q": [""]}
    a = {"/api/start": workbench.daten_start(con, pid),
         "/api/fragen": workbench.daten_fragen(con, pid),
         "/api/fragen?alle=1": workbench.daten_fragen(con, pid, True),
         "/api/wissen": workbench.daten_wissen(con, pid, {"q": [""]}),
         "/api/betrieb": workbench.daten_betrieb(con, pid),
         "/api/releases": workbench.daten_releases(con, pid),
         "/api/projekte": workbench.zeilen(con.execute("SELECT id, name FROM projekt ORDER BY id"))}
    for s in SICHTEN:
        a[f"/api/aufgaben?sicht={s}"] = workbench.daten_aufgaben(con, pid, {"sicht": [s], **leer})
    return a


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
        self.letzt_hoch = self.letzt_puls = 0.0
        self.con.execute("CREATE TABLE IF NOT EXISTS netz_eingang (id INTEGER PRIMARY KEY, ergebnis TEXT,"
                         " zeit_utc TEXT NOT NULL)")

    def schema(self):
        self.sp.ausfuehren([(s, []) for s in SCHEMA])
        self.bekannt = {w: p for w, p in self.sp.ausfuehren([("SELECT weg, pruef FROM ansicht", [])])[0]}

    def hochladen(self, alle=False):
        t = db.jetzt()
        neu = []
        for weg, inhalt in ansichten(self.con, self.pid).items():
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
        zeilen = self.sp.ausfuehren([("SELECT id, weg, daten FROM eingang WHERE status = 'neu' ORDER BY id LIMIT 20",
                                      [])])[0]
        for eid, weg, roh in zeilen:
            eid = int(eid)
            schon = self.con.execute("SELECT ergebnis FROM netz_eingang WHERE id = ?", (eid,)).fetchone()
            if schon:                                  # schon ausgeführt, nur die Rückmeldung fehlte
                status, ergebnis = json.loads(schon[0])
            else:
                try:
                    daten = json.loads(roh)
                    if not isinstance(daten, dict):
                        raise aktionen.Ungueltig("Daten")
                    status, ergebnis = "erledigt", aktionen.ausfuehren(self.con, self.pid, weg, daten, kanal="netz")
                except (aktionen.Ungueltig, kern.AmwFehler, LookupError, ValueError) as e:
                    status, ergebnis = "fehler", {"fehler": str(e) or type(e).__name__}
                self.con.execute("INSERT INTO netz_eingang (id, ergebnis, zeit_utc) VALUES (?, ?, ?)",
                                 (eid, json.dumps([status, ergebnis], ensure_ascii=False), db.jetzt()))
                log.info("Briefkasten #%s %s → %s", eid, weg, status)
            self.sp.ausfuehren([("UPDATE eingang SET status = ?, ergebnis = ?, erledigt_utc = ? WHERE id = ?",
                                 [status, json.dumps(ergebnis, ensure_ascii=False), db.jetzt(), eid])])
        return len(zeilen)

    def schritt(self, geaendert):
        """Ein Durchgang der Schleife; `geaendert`: die lokale Datenbank hat sich seit dem letzten Mal geändert."""
        jetzt = time.time()
        if self.eingang():
            geaendert = True
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
