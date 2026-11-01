"""amw-dienst – der Wächter (→ doc/10-architektur.md §2, §5).

Läuft außerhalb von Claude Code (gestartet von der Windows-Aufgabenplanung, Stufe 1). Aufgaben:
- Wecker: neue Empfänge, deren Art weckt, werden dem Empfänger über die Pipe seiner angemeldeten Sitzung
  zugestellt (eine Sammelzeile je Agent und Durchgang); empfang.geweckt_utc wird gesetzt.
  Während eines Halts nur stopp/freigabe. Agenten ohne lebende Sitzung werden nicht geweckt – ihre
  Nachrichten bleiben offen, bis sich die Sitzung anmeldet.
- Aufsicht: lebt die Pipe einer angemeldeten Sitzung noch? Sonst Sitzung → beendet.
Erkennen wie die alte Wache über PRAGMA data_version (billig, nur Änderungen anderer Verbindungen).
Der Dienst beendet nie Claude-Code-Sitzungen und startet keine Agenten.

Aufruf: python -X utf8 -m amw.dienst [--einmal] [--takt 1.0]
"""
import argparse
import json
import logging
import logging.handlers
import os
import sys
import time

from . import db, kern, pipe

AUFSICHT_S = 30           # Puls-Prüfung und Wiederholung fehlgeschlagener Zustellungen
NUR_IM_HALT = ("stopp", "freigabe")
ZEILE_MAX = 160
log = logging.getLogger("amw.dienst")


def weckzeile(agent, zeilen, halt):
    teile = [f"#{z['nachricht_id']} {z['von']} [{z['art']}] {z['kurz'][:ZEILE_MAX]}" for z in zeilen[:10]]
    if len(zeilen) > 10:
        teile.append(f"… und {len(zeilen) - 10} weitere")
    kopf = f"AMW-Weckruf für {agent}: {len(zeilen)} neue Nachricht(en)"
    if halt:
        kopf += " – HALT GILT, nichts Neues anfangen"
    return kopf + "\n" + "\n".join(teile) + "\nLies mit `amw lesen` bzw. `amw lesen <Nr>` und arbeite sie ab."


def aktive_sitzung(con, pid, kennung):
    return con.execute(
        "SELECT s.* FROM sitzung s JOIN agent g ON g.id = s.agent_id WHERE g.projekt_id = ? AND g.kennung = ?"
        " AND s.zustand = 'aktiv' ORDER BY s.id DESC LIMIT 1", (pid, kennung)).fetchone()


def lies_schluessel(sitzung):
    with open(sitzung["schluessel_datei"], encoding="utf-8") as f:
        d = json.load(f)
    if sitzung["claude_sitzung"] and d.get("sitzung") and d["sitzung"] != sitzung["claude_sitzung"]:
        raise pipe.ZustellFehler("Schlüssel-Datei gehört zu einer neueren Sitzung")
    return d["pipe"], d["schluessel"]


class Dienst:
    def __init__(self, con):
        self.con = con
        self.sperre_bis = {}      # (projekt_id, agent) → Zeitpunkt des nächsten Versuchs nach Fehlschlag

    def zustellen(self):
        offen = self.con.execute(
            "SELECT e.nachricht_id, e.agent, n.projekt_id, n.von, n.art, n.kurz FROM empfang e"
            " JOIN nachricht n ON n.id = e.nachricht_id JOIN nachricht_art a ON a.art = n.art"
            " WHERE e.status = 'offen' AND e.geweckt_utc IS NULL AND a.weckt = 1 ORDER BY n.id").fetchall()
        gruppen = {}
        for z in offen:
            gruppen.setdefault((z["projekt_id"], z["agent"]), []).append(z)
        geweckt = 0
        for (pid, agent), zeilen in gruppen.items():
            if self.sperre_bis.get((pid, agent), 0) > time.time():
                continue
            halt = kern.halt_gilt(self.con, pid, agent)
            if halt:
                zeilen = [z for z in zeilen if z["art"] in NUR_IM_HALT]
                if not zeilen:
                    continue
            s = aktive_sitzung(self.con, pid, agent)
            if not s:
                continue                                   # nicht gestartet: bleibt offen bis zur Anmeldung
            try:
                p, k = lies_schluessel(s)
                pipe.senden(p, k, weckzeile(agent, zeilen, halt))
            except (OSError, ValueError, KeyError, pipe.ZustellFehler) as e:
                log.warning("Wecken %s fehlgeschlagen: %s", agent, e)
                self.sperre_bis[(pid, agent)] = time.time() + AUFSICHT_S
                self.pruefe_sitzung(s)
                continue
            t = db.jetzt()
            with db.schreiben(self.con):
                for z in zeilen:
                    self.con.execute("UPDATE empfang SET geweckt_utc = ? WHERE nachricht_id = ? AND agent = ?",
                                     (t, z["nachricht_id"], agent))
            self.sperre_bis.pop((pid, agent), None)
            log.info("%s geweckt: %s", agent, ", ".join(f"#{z['nachricht_id']}" for z in zeilen))
            geweckt += 1
        return geweckt

    def pruefe_sitzung(self, s):
        try:
            p, _ = lies_schluessel(s)
            lebend = pipe.lebt(p)
        except (OSError, ValueError, KeyError, pipe.ZustellFehler):
            lebend = False
        t = db.jetzt()
        with db.schreiben(self.con):
            if lebend:
                self.con.execute("UPDATE sitzung SET letzter_puls_utc = ? WHERE id = ?", (t, s["id"]))
            else:
                self.con.execute("UPDATE sitzung SET zustand = 'beendet', beendet_utc = ? WHERE id = ?", (t, s["id"]))
                log.info("Sitzung %s beendet (Pipe weg)", s["id"])
        return lebend

    def aufsicht(self):
        for s in self.con.execute("SELECT * FROM sitzung WHERE zustand = 'aktiv'").fetchall():
            self.pruefe_sitzung(s)


def einrichten_log():
    ordner = os.path.dirname(db.db_pfad())
    os.makedirs(ordner, exist_ok=True)
    h = logging.handlers.RotatingFileHandler(os.path.join(ordner, "dienst.log"), maxBytes=1_000_000,
                                             backupCount=3, encoding="utf-8")
    h.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(h)
    log.setLevel(logging.INFO)
    if sys.stderr:
        log.addHandler(logging.StreamHandler())


def einzige_instanz():
    """Hält eine Sperre auf daten/dienst.lock, solange der Prozess lebt. None = läuft schon."""
    import msvcrt
    f = open(os.path.join(os.path.dirname(db.db_pfad()), "dienst.lock"), "a+")
    try:
        msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        f.close()
        return None
    return f


def main(argv=None):
    p = argparse.ArgumentParser(prog="amw-dienst")
    p.add_argument("--einmal", action="store_true", help="ein Durchgang (Test)")
    p.add_argument("--takt", type=float, default=1.0)
    p.add_argument("--port", type=int, default=8780, help="Workbench-Oberfläche auf 127.0.0.1")
    p.add_argument("--ohne-web", action="store_true")
    a = p.parse_args(argv)
    einrichten_log()
    sperre = einzige_instanz()
    if sperre is None:
        log.info("Dienst läuft schon – Ende")
        return 0
    while not os.path.exists(db.db_pfad()):        # vor der Übernahme: warten statt abstürzen
        if a.einmal:
            log.error("Datenbank %s fehlt", db.db_pfad())
            return 1
        log.warning("Datenbank %s fehlt – warte (amw init oder Übernahme)", db.db_pfad())
        time.sleep(AUFSICHT_S)
    con = db.verbinde()
    d = Dienst(con)
    log.info("Dienst gestartet (PID %s, %s)", os.getpid(), db.db_pfad())
    if not (a.einmal or a.ohne_web):
        from . import workbench
        try:
            workbench.starten(a.port)
            log.info("Workbench: http://127.0.0.1:%s/", a.port)
        except OSError as e:                         # Port belegt – Wecker läuft trotzdem
            log.error("Workbench nicht gestartet (Port %s): %s", a.port, e)
    d.aufsicht()
    d.zustellen()
    if a.einmal:
        return 0
    stand, letzte_aufsicht = None, time.time()
    while True:
        try:
            v = con.execute("PRAGMA data_version").fetchone()[0]
            if v != stand:
                stand = v
                d.zustellen()
            if time.time() - letzte_aufsicht >= AUFSICHT_S:
                letzte_aufsicht = time.time()
                d.aufsicht()
                d.zustellen()                       # Wiederholung nach Fehlschlag, neue Anmeldungen
        except Exception:                           # nie sterben; Fehler protokollieren und weiter
            log.exception("Fehler im Durchgang")
        time.sleep(a.takt)


if __name__ == "__main__":
    sys.exit(main())
