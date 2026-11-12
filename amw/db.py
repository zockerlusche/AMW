"""Datenzugriffs-Schicht der AMW (→ doc/architektur.md).

Alles, was die Datenbank anfasst, geht hier durch: Verbindung (WAL, Wartezeit), Anlegen des Schemas,
Zeitstempel, Herkunft. Wird die Datenbank später gewechselt (Stufe 2/3), ändert sich nur dieses Modul.
Nur Python-Standardbibliothek.
"""
import os
import re
import socket
import sqlite3
import sys
import threading
import time
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA_VERSION = 27        # Änderungen: amw/migration_<n>.sql, laufen beim ersten Schreib-Zugriff
HIER = os.path.dirname(os.path.abspath(__file__))
STANDARD_DB = os.path.join(os.path.dirname(HIER), "daten", "amw.db")


def db_pfad():
    if os.environ.get("AMW_DB"):
        return os.environ["AMW_DB"]
    from . import einstellungen                  # Einstellung „db_pfad“ (Zahnrad), sonst <AMW-Ordner>\daten\amw.db
    return einstellungen.wert("db_pfad") or STANDARD_DB


WARTE_MELDUNG_S = 10      # so lange still warten, dann alle 10 s eine Zeile auf stderr (amw-cli)
_phase = {"was": None, "seit": 0.0}


@contextmanager
def _warten(was):
    """Markiert, worauf gerade gewartet wird (Datenbank öffnen, Schreibsperre) – für die Wartemeldung."""
    _phase["was"], _phase["seit"] = was, time.monotonic()
    try:
        yield
    finally:
        _phase["was"] = None


def wartemeldung_an(strom=None, takt=1.0):
    """Hintergrund-Faden für amw-cli: Wer länger als WARTE_MELDUNG_S auf die Datenbank wartet, sieht es, statt still zu
    hängen. Nach busy_timeout (30 s) bricht SQLite mit „database is locked“ ab – das meldet cli.main klar."""
    strom = strom or sys.stderr
    gruende = {"oeffnen": "Datenbank öffnen dauert – Rechner ausgelastet?",
               "sperre": "ein anderer Prozess schreibt gerade (Schreibsperre); Abbruch nach 30 s"}

    def lauf():
        zuletzt = 0.0
        while True:
            time.sleep(takt)
            was = _phase["was"]
            if not was:
                zuletzt = 0.0
                continue
            n = time.monotonic() - _phase["seit"]
            if n >= WARTE_MELDUNG_S and n - zuletzt >= WARTE_MELDUNG_S:
                zuletzt = n
                try:
                    print(f"amw: warte seit {int(n)} s auf die Datenbank – {gruende.get(was, was)}", file=strom, flush=True)
                except (OSError, ValueError):
                    return
    threading.Thread(target=lauf, name="amw-wartemeldung", daemon=True).start()


def jetzt():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def herkunft():
    return socket.gethostname()


def verbinde(pfad=None, nur_lesen=False):
    # isolation_level=None: kein verstecktes BEGIN vor Schreibbefehlen. Transaktionen gibt es nur über
    # schreiben(); sonst bliebe nach einem einzelnen Schreibbefehl die Datenbank für alle anderen gesperrt.
    pfad = pfad or db_pfad()
    if nur_lesen:
        con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True, timeout=30, isolation_level=None)
    else:
        if not os.path.exists(pfad):
            raise FileNotFoundError(f"{pfad} gibt es nicht – erst `amw einrichten`")
        con = sqlite3.connect(pfad, timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    with _warten("oeffnen"):
        con.execute("PRAGMA busy_timeout = 30000")
        con.execute("PRAGMA foreign_keys = ON")
        if not nur_lesen:
            migrieren(con)
    return con


def migrieren(con):
    """Bringt eine ältere Datenbank auf SCHEMA_VERSION (je Stufe eine Datei migration_<n>.sql, in einer Transaktion)."""
    v = con.execute("PRAGMA user_version").fetchone()[0]
    if v == 0 or v >= SCHEMA_VERSION:              # 0 = gerade angelegt bzw. leer: anlegen() setzt die Version
        return
    con.execute("PRAGMA foreign_keys = OFF")       # Tabellen neu anlegen (SQLite: nur außerhalb einer Transaktion
    con.execute("BEGIN IMMEDIATE")                 # umschaltbar); vor dem Abschluss prüft foreign_key_check
    try:
        v = con.execute("PRAGMA user_version").fetchone()[0]   # inzwischen von einem anderen Prozess erledigt?
        vorher = {tuple(r) for r in con.execute("PRAGMA foreign_key_check")}   # Altlasten (z. B. Import) zählen nicht
        for n in range(v + 1, SCHEMA_VERSION + 1):
            with open(os.path.join(HIER, f"migration_{n}.sql"), encoding="utf-8") as f:
                stueck = ""
                for zeile in f:                     # zeilenweise sammeln, bis SQLite eine ganze Anweisung sieht
                    stueck += zeile                 # (auch Trigger mit „…; END;“ bleiben ganz)
                    if sqlite3.complete_statement(stueck):
                        con.execute(stueck)
                        stueck = ""
            con.execute(f"PRAGMA user_version = {n}")
        kaputt = sorted({tuple(r) for r in con.execute("PRAGMA foreign_key_check")} - vorher)
        if kaputt:
            raise sqlite3.IntegrityError(f"Migration: Fremdschlüssel verletzt {kaputt[:3]}")
        con.execute("COMMIT")
    except Exception:
        con.execute("ROLLBACK")
        raise
    finally:
        con.execute("PRAGMA foreign_keys = ON")


def anlegen(pfad=None):
    """Neue, leere Datenbank mit Schema. Bricht ab, wenn es die Datei schon gibt."""
    pfad = pfad or db_pfad()
    if os.path.exists(pfad):
        raise FileExistsError(f"{pfad} gibt es schon")
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    con = sqlite3.connect(pfad)
    con.execute("PRAGMA journal_mode = WAL")
    with open(os.path.join(HIER, "schema.sql"), encoding="utf-8") as f:
        con.executescript(f.read())
    con.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
    con.commit()
    con.close()
    return verbinde(pfad)


def nur_projekt(pfad, pid):
    """In einer Kopie alles anderer Projekte löschen: Zeilen mit fremdem projekt_id, dann Zeilen, die daran hingen
    (sitzung → agent, empfang → nachricht …); eine leere Verweis-Spalte, die erlaubt ist, wird geleert statt gelöscht.
    Was zum Rechner gehört (KIs, Modelle, Schirm), bleibt. Die Schutz-Trigger (nichts löschen) ruhen dafür und kommen
    danach wieder – die Kopie ist eine vollständige AMW-Datenbank mit nur diesem Projekt (Lese-Kopie der Brücke,
    amw sichern --projekt)."""
    k = sqlite3.connect(pfad)
    try:
        k.execute("PRAGMA foreign_keys = OFF")
        tabellen = [r[0] for r in k.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'")]
        with k:
            trigger = k.execute("SELECT name, sql FROM sqlite_master WHERE type = 'trigger'").fetchall()
            for name, _ in trigger:
                k.execute(f'DROP TRIGGER "{name}"')
            k.execute("DELETE FROM projekt WHERE id != ?", (pid,))
            for t in tabellen:
                if t != "projekt" and "projekt_id" in {r[1] for r in k.execute(f'PRAGMA table_info("{t}")')}:
                    k.execute(f'DELETE FROM "{t}" WHERE projekt_id IS NOT NULL AND projekt_id != ?', (pid,))
            verweise = []
            for t in tabellen:
                pflicht = {r[1]: bool(r[3]) for r in k.execute(f'PRAGMA table_info("{t}")')}
                for fk in k.execute(f'PRAGMA foreign_key_list("{t}")').fetchall():
                    verweise.append((t, fk[3], fk[2], fk[4] or "id", pflicht.get(fk[3], False)))
            while True:
                weg = 0
                for t, spalte, eltern, ziel, pflicht in verweise:
                    wo = f'"{spalte}" IS NOT NULL AND "{spalte}" NOT IN (SELECT "{ziel}" FROM "{eltern}")'
                    weg += k.execute(f'DELETE FROM "{t}" WHERE {wo}' if pflicht else f'UPDATE "{t}" SET "{spalte}" = NULL WHERE {wo}').rowcount
                if not weg:
                    break
            for _, sql in trigger:
                k.execute(sql)
        k.execute("VACUUM")
    finally:
        k.close()


def sichern(ziel=None, pfad=None, pid=None, name=None):
    """Vollständige Kopie der Datenbank (VACUUM INTO – geht auch, während Agenten schreiben). Rückgabe: Zielpfad.
    pid: nur dieses Projekt (name: für den Dateinamen) – eine eigene, lauffähige AMW-Datenbank."""
    pfad = pfad or db_pfad()
    teil = f"-{kurzname(name or str(pid), pid)}" if pid else ""
    if not ziel:
        ziel = os.path.join(os.path.dirname(pfad), f"sicherung{teil}-{datetime.now().strftime('%Y-%m-%d-%H%M')}.db")
    elif os.path.isdir(ziel) or not ziel.lower().endswith(".db"):          # ein Ordner (wird angelegt)
        os.makedirs(ziel, exist_ok=True)
        ziel = os.path.join(ziel, f"amw-sicherung{teil}-{datetime.now().strftime('%Y-%m-%d-%H%M')}.db")
    if os.path.exists(ziel):
        raise FileExistsError(f"{ziel} gibt es schon")
    q = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True, timeout=30)
    try:
        q.execute("VACUUM INTO ?", (ziel,))
    finally:
        q.close()
    if pid:
        nur_projekt(ziel, pid)
    return ziel


@contextmanager
def schreiben(con):
    """Eine Schreib-Transaktion; sperrt sofort, damit zwei Agenten sich nicht überholen."""
    with _warten("sperre"):
        con.execute("BEGIN IMMEDIATE")
    try:
        yield con
    except BaseException:
        con.execute("ROLLBACK")
        raise
    con.execute("COMMIT")


def einfuegen(con, tabelle, **werte):
    """INSERT mit Herkunft; gibt die neue rowid zurück. Spaltennamen kommen nur aus dem Code, nie vom Nutzer."""
    werte.setdefault("herkunft", herkunft())
    if tabelle in ("nachricht", "frage_verlauf") and werte.get("von") == "Entwickler" and "benutzer" not in werte:
        from . import benutzer                       # handelt gerade ein Benutzer über die Online-Seite? (Schema 27)
        if benutzer.AKTUELL.get():
            werte["benutzer"] = benutzer.AKTUELL.get()
    spalten = ", ".join(werte)
    platz = ", ".join("?" for _ in werte)
    return con.execute(f"INSERT INTO {tabelle} ({spalten}) VALUES ({platz})", tuple(werte.values())).lastrowid


def kurzname(name, ersatz=""):
    """Projektname als Teil eines Datei- oder Ordnernamens: „Mein Shop“ → mein-shop (Startskript, Brücke)."""
    return re.sub(r"[^\w-]+", "-", name).strip("-").lower() or str(ersatz)


def projekt_name(con, pid):
    r = con.execute("SELECT name FROM projekt WHERE id = ?", (pid,)).fetchone()
    return r[0] if r else str(pid)


def projekt_id(con, name):
    """Projekt nach Name oder Kennung (uid, so steht es online)."""
    r = con.execute("SELECT id FROM projekt WHERE name = ? OR uid = ?", (name, name)).fetchone()
    if not r:
        raise LookupError(f"Projekt „{name}“ gibt es nicht")
    return r["id"]


def _projekte_der_kennung(con, kennung, alle=False):
    """Projekte, in denen es diese Kennung gibt; frühere Kennungen (Umbenennen) zählen nachrangig, mit alle=True immer."""
    treffer = {r["projekt_id"] for r in con.execute("SELECT projekt_id FROM agent WHERE kennung = ?", (kennung,))}
    if treffer and not alle:
        return treffer
    return treffer | {r["projekt_id"] for r in con.execute("SELECT projekt_id, alias FROM agent WHERE alias IS NOT NULL")
                      if kennung in [x.strip() for x in (r["alias"] or "").split(",")]}


def produkt_entwickler():
    """Kennung des AMW-Produktentwicklers (PC-Einstellung, Entwickler-Kanal) oder None."""
    from . import einstellungen
    try:
        return einstellungen.wert("produkt_entwickler") or None
    except (OSError, ValueError):
        return None


def projekt_fuer(con, name=None, kennung=None):
    """Welches Projekt: genannt (--projekt/AMW_PROJEKT), sonst das einzige, sonst das der Kennung (auch frühere
    Kennungen nach dem Umbenennen). Mehrdeutig → LookupError mit den Projekten (doc/plan-projektwahl.md).
    Ein Agent eines Projekts kommt nicht in ein anderes (nur der Entwickler wählt frei) → LookupError."""
    if name:
        pid = projekt_id(con, name)
        heim = (_projekte_der_kennung(con, kennung, alle=True)
                if kennung and kennung not in ("Entwickler", produkt_entwickler()) else set())
        if heim and pid not in heim:                # Projekte sind völlig getrennt: kein Agent arbeitet in einem fremden
            raise LookupError(f"„{kennung}“ ist kein Agent des Projekts {name} – Projekte sind getrennt, "
                              "arbeite nur in deinem eigenen (--projekt weglassen)")
        return pid
    zeilen = con.execute("SELECT id, name FROM projekt ORDER BY id").fetchall()
    if len(zeilen) == 1:
        return zeilen[0]["id"]
    if not zeilen:
        raise LookupError("keine Projekte – amw projekt neu <name>")
    if kennung:
        treffer = _projekte_der_kennung(con, kennung)
        if len(treffer) == 1:
            return treffer.pop()
    namen = ", ".join(r["name"] for r in zeilen)
    raise LookupError(f"mehrere Projekte ({namen}) – --projekt <name> oder AMW_PROJEKT angeben")
