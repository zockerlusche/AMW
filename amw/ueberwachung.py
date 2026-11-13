"""Überwachung: Projekt-Server und Stillstand (→ doc/ausbau.md §2).

- Server: Ein Projekt meldet seine Dienste an (Name, Port, Startbefehl, Ordner, Zuständiger, Neustart ja/nein). Der
  Wächter prüft in jeder Aufsichtsrunde, ob der Port antwortet. Fällt einer aus, meldet er es dem Zuständigen und den
  Leads; mit Neustart startet er ihn selbst – erst wenn er zwei Runden in Folge aus war (ein Agent, der gerade selbst
  neu startet, kommt so nicht ins Gehege), höchstens NEUSTARTS_JE_STUNDE Mal je Stunde, danach nur noch Meldung.
  Anlass: ein Projekt-Server fiel stundenlang unbemerkt aus.
- Stillstand: Weckruf seit stillstand_min unbeantwortet; Lauf länger als erwartet (doppelte Angabe, sonst
  lauf_ohne_angabe_min).

Der Startbefehl kommt nur über die Kommandozeile am PC in die Datenbank – nie über die Brücke des TL oder die
Online-Seite (sonst könnte von außen ein Befehl auf diesem PC landen).
"""
import calendar
import json
import os
import socket
import subprocess
import time

from . import db, kern

NEUSTARTS_JE_STUNDE = 3
STILLSTAND_MIN = 30
LAUF_OHNE_ANGABE_MIN = 90
FREIGABE_MIN = 2           # Agent hängt an einer Berechtigungsabfrage
KONTEXT_GRENZE = 90        # % des Kontextfensters
LIMIT_GRENZE = 90          # % der 5-Stunden-Grenze


def _sek(utc):
    return calendar.timegm(time.strptime(utc, "%Y-%m-%dT%H:%M:%SZ"))


def _einstellung(con, pid, schluessel, vorgabe):
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        return float(json.loads(r["einstellungen"] or "{}").get(schluessel, vorgabe))
    except (TypeError, ValueError):
        return vorgabe


def _leads(con, pid):
    return [r["kennung"] for r in con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND rolle = 'lead'", (pid,))]


# --- Server --------------------------------------------------------------------------------------

def server_anmelden(con, pid, von, name, port, startbefehl=None, ordner=None, neustart=False, zustaendig=None):
    name = (name or "").strip()
    if not name or len(name) > 40:
        raise kern.AmwFehler("Name: 1–40 Zeichen")
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise kern.AmwFehler("Port: Zahl") from None
    if not 1 <= port <= 65535:
        raise kern.AmwFehler("Port: 1–65535")
    if neustart and not startbefehl:
        raise kern.AmwFehler("Neustart braucht einen Startbefehl (--start)")
    if ordner and not os.path.isdir(ordner):
        raise kern.AmwFehler(f"Ordner {ordner} gibt es nicht")
    zustaendig = zustaendig or von
    kern.empfaenger(con, pid, zustaendig, "")            # prüft die Kennung
    with db.schreiben(con):
        t = db.jetzt()
        alt = con.execute("SELECT id FROM server WHERE projekt_id = ? AND name = ?", (pid, name)).fetchone()
        if alt:
            con.execute("UPDATE server SET port = ?, startbefehl = ?, ordner = ?, neustart = ?, zustaendig = ?, aktiv = 1,"
                        " zustand = 'unbekannt', geaendert_utc = ? WHERE id = ?",
                        (port, startbefehl, ordner, int(neustart), zustaendig, t, alt["id"]))
            return "geändert"
        db.einfuegen(con, "server", projekt_id=pid, name=name, port=port, startbefehl=startbefehl, ordner=ordner,
                     neustart=int(neustart), zustaendig=zustaendig, angelegt_utc=t)
        return "angelegt"


def server_abmelden(con, pid, von, name):
    with db.schreiben(con):
        n = con.execute("UPDATE server SET aktiv = 0, geaendert_utc = ? WHERE projekt_id = ? AND name = ? AND aktiv = 1",
                        (db.jetzt(), pid, name)).rowcount
    if not n:
        raise kern.AmwFehler(f"Server „{name}“ ist nicht angemeldet")


def antwortet(port, host="127.0.0.1", warten_s=2.0):
    try:
        with socket.create_connection((host, port), timeout=warten_s):
            return True
    except OSError:
        return False


def starten(s):
    """Startet den Server losgelöst vom Wächter (läuft weiter, wenn der Wächter neu startet). Ausgabe ins Protokoll.
    Rückgabe: der Prozess (lokale KIs merken sich PID und Startzeit, um nur selbst Gestartetes wieder zu beenden)."""
    log = os.path.join(os.path.dirname(db.db_pfad()), f"server-{s['name']}.log")
    with open(log, "a", encoding="utf-8") as f:
        f.write(f"\n--- {db.jetzt()} Neustart durch den AMW-Dienst: {s['startbefehl']}\n")
        f.flush()
        flags = 0
        for name in ("DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP", "CREATE_NO_WINDOW"):
            flags |= getattr(subprocess, name, 0)
        if flags & getattr(subprocess, "CREATE_NO_WINDOW", 0) and flags & getattr(subprocess, "DETACHED_PROCESS", 0):
            flags &= ~subprocess.CREATE_NO_WINDOW            # beide zusammen verbietet Windows
        return subprocess.Popen(s["startbefehl"], cwd=s["ordner"] or None, stdout=f, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, creationflags=flags, close_fds=True)


def server_pruefen(con, pid, pruefen=antwortet, start=starten):
    """Eine Aufsichtsrunde für alle angemeldeten Server. Rückgabe: Liste kurzer Ereignistexte (fürs Protokoll)."""
    ereignisse = []
    for s in con.execute("SELECT * FROM server WHERE projekt_id = ? AND aktiv = 1 ORDER BY id", (pid,)).fetchall():
        lebt = pruefen(s["port"])
        neu, t = ("laeuft" if lebt else "aus"), db.jetzt()
        an = ",".join(dict.fromkeys([s["zustaendig"], *_leads(con, pid)]))
        with db.schreiben(con):
            con.execute("UPDATE server SET geprueft_utc = ? WHERE id = ?", (t, s["id"]))
            if neu != s["zustand"]:
                con.execute("UPDATE server SET zustand = ?, seit_utc = ? WHERE id = ?", (neu, t, s["id"]))
                if neu == "aus":
                    con.execute("UPDATE server SET ausfaelle = ausfaelle + 1 WHERE id = ?", (s["id"],))
                    kern._posten(con, pid, "AMW", an, "meldung", f"Server {s['name']} (Port {s['port']}) ist AUS",
                                 "Der Dienst startet ihn in der nächsten Runde neu." if s["neustart"] else
                                 "Kein automatischer Neustart angemeldet – bitte selbst starten.")
                    ereignisse.append(f"{s['name']} aus")
                elif s["zustand"] == "aus":
                    kern._posten(con, pid, "AMW", an, "info", f"Server {s['name']} (Port {s['port']}) läuft wieder")
                    ereignisse.append(f"{s['name']} wieder da")
        if lebt or not s["neustart"] or s["zustand"] != "aus":
            continue                                     # erst nach der zweiten Runde „aus“ neu starten
        jetzt = time.time()
        versuche = [x for x in json.loads(s["neustarts"] or "[]") if jetzt - x < 3600]
        if len(versuche) >= NEUSTARTS_JE_STUNDE:
            if len(versuche) == NEUSTARTS_JE_STUNDE:      # Grenze einmal melden
                versuche.append(jetzt)
                with db.schreiben(con):
                    con.execute("UPDATE server SET neustarts = ? WHERE id = ?", (json.dumps(versuche), s["id"]))
                    kern._posten(con, pid, "AMW", an, "meldung",
                                 f"Server {s['name']}: {NEUSTARTS_JE_STUNDE} Neustarts in einer Stunde – ich höre auf",
                                 f"Bitte selbst ansehen; Protokoll: daten/server-{s['name']}.log")
                ereignisse.append(f"{s['name']} Neustart-Grenze")
            continue
        try:
            start(s)
            text = None
        except OSError as e:
            text = f"{type(e).__name__}: {e}"
        versuche.append(jetzt)
        with db.schreiben(con):
            con.execute("UPDATE server SET neustarts = ?, letzter_neustart_utc = ? WHERE id = ?",
                        (json.dumps(versuche), db.jetzt(), s["id"]))
            kern._posten(con, pid, "AMW", an, "info" if not text else "meldung",
                         f"Server {s['name']}: Neustart {'versucht' if not text else 'FEHLGESCHLAGEN'} ({len(versuche)}. in dieser Stunde)",
                         text or f"Befehl: {s['startbefehl']} · Protokoll: daten/server-{s['name']}.log")
        ereignisse.append(f"{s['name']} Neustart" + (" fehlgeschlagen" if text else ""))
    return ereignisse


# --- Warnungen (Workbench, Wächter) --------------------------------------------------------------

def warnungen(con, pid, jetzt=None):
    """Was gerade nicht stimmt: Server aus, Weckruf unbeantwortet, Lauf überfällig. Liste von
    {"art", "schluessel", "text", "an"} – schluessel bleibt gleich, solange der Zustand besteht."""
    jetzt = jetzt or time.time()
    aus = []
    for s in con.execute("SELECT name, port, seit_utc, zustaendig FROM server WHERE projekt_id = ? AND aktiv = 1"
                         " AND zustand = 'aus'", (pid,)):
        aus.append({"art": "server", "schluessel": f"server:{s['name']}:{s['seit_utc']}", "an": s["zustaendig"],
                    "text": f"Server {s['name']} (Port {s['port']}) ist aus seit {s['seit_utc']}"})
    grenze = _einstellung(con, pid, "stillstand_min", STILLSTAND_MIN) * 60
    for r in con.execute(
            "SELECT e.agent, min(e.geweckt_utc) AS seit, count(*) AS n, min(e.nachricht_id) AS erste FROM empfang e"
            " JOIN nachricht n ON n.id = e.nachricht_id JOIN agent a ON a.kennung = e.agent AND a.projekt_id = n.projekt_id"
            " WHERE n.projekt_id = ? AND e.status = 'offen' AND e.geweckt_utc IS NOT NULL AND a.soll = 'an'"
            " AND EXISTS (SELECT 1 FROM sitzung s WHERE s.agent_id = a.id AND s.zustand = 'aktiv')"
            # wer seit dem Weckruf etwas gemeldet hat, lebt – nur nicht abgehakt (alte Weckprobe o. Ä.)
            " AND NOT EXISTS (SELECT 1 FROM nachricht m WHERE m.projekt_id = n.projekt_id AND m.von = e.agent"
            "   AND m.zeit_utc >= e.geweckt_utc)"
            " GROUP BY e.agent", (pid,)):
        if jetzt - _sek(r["seit"]) >= grenze:
            aus.append({"art": "stillstand", "schluessel": f"still:{r['agent']}:{r['erste']}", "an": r["agent"],
                        "text": f"{r['agent']} reagiert nicht: {r['n']} Benachrichtigung(en) unbeantwortet seit "
                                f"{int((jetzt - _sek(r['seit'])) // 60)} min (ab #{r['erste']})"})
    for s in con.execute(
            "SELECT s.id, a.kennung, s.ereignis, s.ereignis_text, s.ereignis_utc, s.kontext_prozent, s.limit_5h, s.status_utc"
            " FROM sitzung s JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ? AND s.zustand = 'aktiv'", (pid,)):
        if s["ereignis"] == "wartet_freigabe" and jetzt - _sek(s["ereignis_utc"]) >= FREIGABE_MIN * 60:
            aus.append({"art": "freigabe", "schluessel": f"freigabe:{s['id']}:{s['ereignis_utc']}", "an": s["kennung"],
                        "text": f"{s['kennung']} wartet seit {int((jetzt - _sek(s['ereignis_utc'])) // 60)} min auf eine Freigabe"
                                " im eigenen Fenster" + (f": {s['ereignis_text']}" if s["ereignis_text"] else "")})
        if s["ereignis"] == "fehler":
            aus.append({"art": "fehler", "schluessel": f"fehler:{s['id']}:{s['ereignis_utc']}", "an": s["kennung"],
                        "text": f"{s['kennung']}: Abbruch mit Fehler ({s['ereignis_text'] or 'unbekannt'}) – arbeitet erst nach neuer Eingabe weiter"})
        frisch = s["status_utc"] and jetzt - _sek(s["status_utc"]) < 1800
        if frisch and (s["kontext_prozent"] or 0) >= KONTEXT_GRENZE:
            aus.append({"art": "kontext", "schluessel": f"kontext:{s['id']}", "an": s["kennung"],
                        "text": f"{s['kennung']}: Kontext zu {s['kontext_prozent']:.0f} % voll – Kompaktierung steht bevor"})
        if frisch and (s["limit_5h"] or 0) >= LIMIT_GRENZE:
            aus.append({"art": "limit", "schluessel": f"limit:{s['id']}:{int(s['limit_5h'] // 5)}", "an": s["kennung"],
                        "text": f"{s['kennung']}: 5-Stunden-Grenze zu {s['limit_5h']:.0f} % ausgeschöpft"})
    ohne = _einstellung(con, pid, "lauf_ohne_angabe_min", LAUF_OHNE_ANGABE_MIN)
    for l in con.execute("SELECT id, agent, beschreibung, start_utc, erwartet_min FROM lauf WHERE projekt_id = ?"
                         " AND status = 'laeuft' AND start_utc IS NOT NULL", (pid,)):
        soll = (l["erwartet_min"] * 2) if l["erwartet_min"] else ohne
        dauer = (jetzt - _sek(l["start_utc"])) / 60
        if dauer >= soll:
            aus.append({"art": "lauf", "schluessel": f"lauf:{l['id']}", "an": l["agent"],
                        "text": f"Lauf L{l['id']} von {l['agent']} läuft seit {int(dauer)} min"
                                + (f" (erwartet {l['erwartet_min']:g})" if l["erwartet_min"] else "") + f": {l['beschreibung'][:80]}"})
    return aus


class Waechter:
    """Im Wächter: Server prüfen und neue Warnungen einmal den Leads melden (gemerkt bis zum Neustart des Wächters)."""

    def __init__(self, con):
        self.con, self.gemeldet = con, set()

    def runde(self):
        ereignisse = []
        for p in self.con.execute("SELECT id FROM projekt").fetchall():
            ereignisse += server_pruefen(self.con, p["id"])
            for w in warnungen(self.con, p["id"]):
                if w["art"] == "server" or w["schluessel"] in self.gemeldet:
                    continue                              # Server meldet server_pruefen selbst
                self.gemeldet.add(w["schluessel"])
                an = ",".join(dict.fromkeys(_leads(self.con, p["id"])))
                if an:
                    with db.schreiben(self.con):
                        # „läuft länger als erwartet“ ist ein Zustand, kein Auftrag: Info (weckt nicht, steht in der Workbench) – A1641
                        kern._posten(self.con, p["id"], "AMW", an, "info" if w["art"] == "lauf" else "meldung", "Achtung: " + w["text"])
                ereignisse.append(w["text"])
        return ereignisse
