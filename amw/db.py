"""Datenzugriffs-Schicht der AMW (→ doc/10-architektur.md L4, 06 §5).

Alles, was die Datenbank anfasst, geht hier durch: Verbindung (WAL, Wartezeit), Anlegen des Schemas,
Zeitstempel, Herkunft. Wird die Datenbank später gewechselt (Stufe 2/3), ändert sich nur dieses Modul.
Nur Python-Standardbibliothek.
"""
import os
import socket
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone

SCHEMA_VERSION = 1
HIER = os.path.dirname(os.path.abspath(__file__))
STANDARD_DB = os.path.join(os.path.dirname(HIER), "daten", "amw.db")


def db_pfad():
    return os.environ.get("AMW_DB") or STANDARD_DB


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
            raise FileNotFoundError(f"{pfad} gibt es nicht – erst `amw init`")
        con = sqlite3.connect(pfad, timeout=30, isolation_level=None)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA busy_timeout = 30000")
    con.execute("PRAGMA foreign_keys = ON")
    return con


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


@contextmanager
def schreiben(con):
    """Eine Schreib-Transaktion; sperrt sofort, damit zwei Agenten sich nicht überholen."""
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
    spalten = ", ".join(werte)
    platz = ", ".join("?" for _ in werte)
    return con.execute(f"INSERT INTO {tabelle} ({spalten}) VALUES ({platz})", tuple(werte.values())).lastrowid


def projekt_id(con, name):
    r = con.execute("SELECT id FROM projekt WHERE name = ?", (name,)).fetchone()
    if not r:
        raise LookupError(f"Projekt „{name}“ gibt es nicht")
    return r["id"]
