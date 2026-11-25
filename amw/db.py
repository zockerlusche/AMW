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

from . import anfragezeit

SCHEMA_VERSION = 35        # Änderungen: amw/migration_<n>.sql, laufen beim ersten Schreib-Zugriff
HIER = os.path.dirname(os.path.abspath(__file__))
STANDARD_DB = os.path.join(os.path.dirname(HIER), "daten", "amw.db")
CODE = os.path.dirname(HIER)                       # Ordner dieses Codes (Live-Ordner, Entwicklungsbaum, Prüfbaum, Platz)


# --- Schutz der Live-Datenbank (A1862, Vorfall #28835: ein Befehl aus dem Entwicklungsbaum migrierte die Live-DB) ------------
# Der Dienst vermerkt beim Start neben der Datenbank, aus welchem Ordner sein Code kommt (<db>.code). Öffnet Code aus einem
# ANDEREN Ordner diese Datenbank, ohne dass AMW_DB ausdrücklich gesetzt ist (Entwicklungsbaum, der über die Einstellung db_pfad
# bei der Live-DB landet), darf er lesen – aber nicht migrieren und nicht schreiben. Ohne Vermerk (ältere Installation, Tests)
# bleibt alles wie bisher; mit ausdrücklichem AMW_DB auch (Tests, Plätze, bewusste Kopien).

class LiveSchutz(ValueError):
    pass


class _Verbindung(sqlite3.Connection):
    fremd = None                                   # Ordner des Dienstes, wenn dieser Code fremd ist
    merker = None                                  # A2081: einmal.merken – gemerkte Ergebnisse dieser Anfrage bzw. Runde
    schnappschuss = False                          # … und sie liest dafür einen festen Stand

    # A2144: gezählt wird nur in einer Anfrage der Workbench; execute() der Verbindung holt seinen Cursor nicht über cursor()
    def cursor(self, factory=None):
        if factory is None and anfragezeit.zaehlt():
            factory = anfragezeit.Zaehler
        return super().cursor(factory) if factory else super().cursor()

    def execute(self, *a):
        return self.cursor().execute(*a) if anfragezeit.zaehlt() else super().execute(*a)

    def executemany(self, *a):
        return self.cursor().executemany(*a) if anfragezeit.zaehlt() else super().executemany(*a)


def vermerk_pfad(pfad):
    return pfad + ".code"


def vermerken(pfad=None):
    """Vom Dienst beim Start: dieser Code gehört zu dieser Datenbank."""
    try:
        with open(vermerk_pfad(pfad or db_pfad()), "w", encoding="utf-8") as f:
            f.write(CODE)
    except OSError:
        pass


def fremder_code(pfad):
    """Ordner des Dienstes, wenn dieser Code NICHT von dort kommt und AMW_DB nicht ausdrücklich gesetzt ist – sonst None."""
    if os.environ.get("AMW_DB"):
        return None
    try:
        with open(vermerk_pfad(pfad), encoding="utf-8") as f:
            dienst = f.read().strip()
    except OSError:
        return None
    norm = lambda x: os.path.normcase(os.path.abspath(x))
    return dienst if dienst and norm(dienst) != norm(CODE) else None


_SCHREIBEN = {getattr(sqlite3, n) for n in ("SQLITE_INSERT", "SQLITE_UPDATE", "SQLITE_DELETE", "SQLITE_CREATE_TABLE", "SQLITE_CREATE_INDEX",
              "SQLITE_CREATE_TRIGGER", "SQLITE_CREATE_VIEW", "SQLITE_DROP_TABLE", "SQLITE_DROP_INDEX", "SQLITE_DROP_TRIGGER",
              "SQLITE_DROP_VIEW", "SQLITE_ALTER_TABLE")}


def _nur_lesen(aktion, a1, a2, datenbank, ausloeser):
    if aktion in _SCHREIBEN and datenbank != "temp":
        return sqlite3.SQLITE_DENY
    if aktion == sqlite3.SQLITE_PRAGMA and a1 == "user_version" and a2 is not None:
        return sqlite3.SQLITE_DENY
    return sqlite3.SQLITE_OK


def _schutz_meldung(con, was):
    return (f"Diese Datenbank gehört zum Dienst in {con.fremd}; Code aus {CODE} darf sie nicht {was}. Befehle von hier mit"
            f" AMW_DB=<eigene Datei> ausführen – oder aus {con.fremd} (A1862).")


def db_pfad():
    if os.environ.get("AMW_DB"):
        return os.environ["AMW_DB"]
    from . import einstellungen                  # Einstellung „db_pfad“ (Zahnrad), sonst <AMW-Ordner>\daten\amw.db
    return einstellungen.wert("db_pfad") or STANDARD_DB


WARTE_MELDUNG_S = 10      # so lange still warten, dann alle 10 s eine Zeile auf stderr (amw-cli)
_phase = {"was": None, "seit": 0.0}
_wartemeldung_faeden = []          # (Strom, Faden) – je Strom höchstens ein lebender Faden


@contextmanager
def _warten(was):
    """Markiert, worauf gerade gewartet wird (Datenbank öffnen, Schreibsperre) – für die Wartemeldung."""
    _phase["was"], _phase["seit"] = was, time.monotonic()
    try:                                             # A2035: misst die Workbench gerade eine Anfrage, zählt das Warten mit
        with anfragezeit.messen({"oeffnen": "DB öffnen", "sperre": "DB-Sperre"}.get(was, was)):
            yield
    finally:
        _phase["was"] = None


def wartemeldung_an(strom=None, takt=1.0):
    """Hintergrund-Faden für amw-cli: Wer länger als WARTE_MELDUNG_S auf die Datenbank wartet, sieht es, statt still zu
    hängen. Nach busy_timeout (30 s) bricht SQLite mit „database is locked“ ab – das meldet cli.main klar.
    Ein Faden je Ausgabe-Strom und Prozess (cli.main läuft in Tests hundertfach im selben Prozess). Er wartet an einem
    eigenen Event statt mit time.sleep: ersetzt ein Test time.sleep, drehte der Faden sonst ohne Pause und sammelte die
    Aufrufe des Ersatzes – der Testprozess wuchs im Gesamtlauf über 4 GB (14.11., L1718)."""
    strom = strom or sys.stderr
    if any(f.is_alive() for s, f in _wartemeldung_faeden if s is strom):
        return
    gruende = {"oeffnen": "Datenbank öffnen dauert – Rechner ausgelastet?",
               "sperre": "ein anderer Prozess schreibt gerade (Schreibsperre); Abbruch nach 30 s"}
    pause = threading.Event()                          # wird nie gesetzt: wait(takt) ist die Pause

    def lauf():
        zuletzt = 0.0
        while True:
            pause.wait(takt)
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
    f = threading.Thread(target=lauf, name="amw-wartemeldung", daemon=True)
    f.start()
    _wartemeldung_faeden.append((strom, f))


def jetzt():
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


_UTC_MUSTER = re.compile(r"\s*(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?\s*(?:Z|[+-]00:?00|UTC)?\s*")


def utc_lesen(utc):
    """A2001: eine gespeicherte UTC-Zeit lesen – an EINER Stelle und tolerant: „2026-11-23T08:00:00Z“ (das Format der AMW) wie
    ältere Einträge „2026-10-21 07:08:44“ (SQLite datetime('now')), mit Bruchteilen oder „+00:00“. Gibt eine Zeit mit
    Zeitzone UTC zurück; was keine Zeit ist, gibt ValueError (wie strptime)."""
    m = _UTC_MUSTER.fullmatch(utc or "") if isinstance(utc, str) else None
    if not m:
        raise ValueError(f"keine UTC-Zeit: {utc!r}")
    j, mo, t, h, mi, s = (int(x or 0) for x in m.groups())
    return datetime(j, mo, t, h, mi, s, tzinfo=timezone.utc)


def utc_sek(utc):
    """Wie utc_lesen, als Sekunden seit 1970 (ganze Zahl wie calendar.timegm)."""
    return int(utc_lesen(utc).timestamp())


def herkunft():
    return socket.gethostname()


def verbinde(pfad=None, nur_lesen=False):
    # isolation_level=None: kein verstecktes BEGIN vor Schreibbefehlen. Transaktionen gibt es nur über
    # schreiben(); sonst bliebe nach einem einzelnen Schreibbefehl die Datenbank für alle anderen gesperrt.
    pfad = pfad or db_pfad()
    if nur_lesen:
        con = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True, timeout=30, isolation_level=None, factory=_Verbindung)
    else:
        if not os.path.exists(pfad):
            raise FileNotFoundError(f"{pfad} gibt es nicht – erst `amw einrichten`")
        con = sqlite3.connect(pfad, timeout=30, isolation_level=None, factory=_Verbindung)
    con.fremd = fremder_code(pfad)
    if con.fremd:                                  # A1862: auch Schreibbefehle außerhalb von schreiben() abweisen
        con.set_authorizer(_nur_lesen)
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
    if getattr(con, "fremd", None):                # A1862: fremder Code migriert die Live-DB nie
        raise LiveSchutz(_schutz_meldung(con, f"von Schema {v} auf {SCHEMA_VERSION} migrieren"))
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


def _freier_name(ziel):
    """A2136: den automatisch gebildeten Namen belegen – gibt es ihn schon (zwei Sicherungen in einer Minute), kommt ein Zähler dazu
    („…-1850-2.db“). Die leere Datei reserviert ihn (VACUUM INTO nimmt eine leere an); überschrieben wird nie."""
    stamm, i = ziel[:-3], 1
    while True:
        pfad = ziel if i == 1 else f"{stamm}-{i}.db"
        try:
            os.close(os.open(pfad, os.O_CREAT | os.O_EXCL | os.O_WRONLY))
            return pfad
        except FileExistsError:
            i += 1


def sichern(ziel=None, pfad=None, pid=None, name=None):
    """Vollständige Kopie der Datenbank (VACUUM INTO – geht auch, während Agenten schreiben). Rückgabe: Zielpfad.
    pid: nur dieses Projekt (name: für den Dateinamen) – eine eigene, lauffähige AMW-Datenbank. Ein selbst genannter Dateiname, den es
    schon gibt, bleibt ein Fehler; ein automatischer bekommt einen Zähler (A2136)."""
    pfad = pfad or db_pfad()
    teil = f"-{kurzname(name or str(pid), pid)}" if pid else ""
    automatisch = not ziel or os.path.isdir(ziel) or not ziel.lower().endswith(".db")
    if not ziel:
        ziel = os.path.join(os.path.dirname(pfad), f"sicherung{teil}-{datetime.now().strftime('%Y-%m-%d-%H%M')}.db")
    elif os.path.isdir(ziel) or not ziel.lower().endswith(".db"):          # ein Ordner (wird angelegt)
        os.makedirs(ziel, exist_ok=True)
        ziel = os.path.join(ziel, f"amw-sicherung{teil}-{datetime.now().strftime('%Y-%m-%d-%H%M')}.db")
    if automatisch:
        ziel = _freier_name(ziel)
    elif os.path.exists(ziel):
        raise FileExistsError(f"{ziel} gibt es schon")
    try:
        q = sqlite3.connect(f"file:{pfad}?mode=ro", uri=True, timeout=30)
        try:
            q.execute("VACUUM INTO ?", (ziel,))
        finally:
            q.close()
    except BaseException:
        if automatisch and os.path.exists(ziel) and not os.path.getsize(ziel):      # nur die eigene leere Reservierung
            os.remove(ziel)
        raise
    if pid:
        nur_projekt(ziel, pid)
    return ziel


@contextmanager
def schreiben(con):
    """Eine Schreib-Transaktion; sperrt sofort, damit zwei Agenten sich nicht überholen."""
    if getattr(con, "fremd", None):                # A1862: fremder Code schreibt nicht in die Live-DB
        raise LiveSchutz(_schutz_meldung(con, "beschreiben"))
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
    """Entwickler-Kanal – entfernt (A1758, Marcel 15.11. 09:31): Leads anderer Projekte sprechen nicht mit dem Entwickler der
    AMW, sondern über die Lead-Runde mit dem AMW-Lead. Immer None – damit fallen Empfang, Schreiben und Wecken über
    Projektgrenzen und das Lesen aller Projekte überall weg, wo der Kanal früher galt."""
    return None


def produkt_entwickler_name():
    """Nur noch zur Anzeige: die Kennung aus der PC-Einstellung „produkt_entwickler“ (oder None) – damit ein fremder Lead,
    der ihn anschreiben will, erfährt, wohin seine Nachricht stattdessen gehört."""
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
