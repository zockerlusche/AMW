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
import calendar
import json
import logging
import logging.handlers
import os
import sys
import time

from . import betrieb, db, kern, pipe, push, statusline, steuerung, ueberwachung

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
        " AND s.zustand = 'aktiv' AND s.schluessel_datei IS NOT NULL ORDER BY s.id DESC LIMIT 1", (pid, kennung)).fetchone()


def lies_schluessel(sitzung):
    with open(sitzung["schluessel_datei"], encoding="utf-8") as f:
        d = json.load(f)
    if sitzung["claude_sitzung"] and d.get("sitzung") and d["sitzung"] != sitzung["claude_sitzung"]:
        raise pipe.ZustellFehler("Schlüssel-Datei gehört zu einer neueren Sitzung")
    return d["pipe"], d["schluessel"]


TAKT_MIN = 120            # Vorgabe; je Projekt: einstellungen {"takt_min": …}, 0 = aus


def takt_text(con, pid, lead, seit):
    """Kurze Zusammenfassung für den Lead seit dem letzten Takt – nur Zahlen und Nummern, Details per amw.
    „>=“: Zeitstempel sind sekundengenau; lieber ein Ereignis an der Grenze doppelt zählen als eins verlieren."""
    z = lambda sql, *p: con.execute(sql, (pid, *p)).fetchone()[0]
    neu_an_lead = z("SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id WHERE n.projekt_id = ?"
                    " AND e.agent = ? AND n.zeit_utc >= ? AND n.art != 'takt'", lead, seit)
    beantwortet = con.execute("SELECT id FROM frage WHERE projekt_id = ? AND antwort_utc >= ? AND status = 'beantwortet'"
                              " ORDER BY id", (pid, seit)).fetchall()
    offen_entw = z("SELECT count(*) FROM frage WHERE projekt_id = ? AND an = 'entwickler' AND status = 'offen'"
                   " AND kurz NOT LIKE 'GEPARKT%'")
    fertig = z("SELECT count(*) FROM aufgabe WHERE projekt_id = ? AND fertig_utc >= ?", seit)
    laeufe = z("SELECT count(*) FROM lauf WHERE projekt_id = ? AND status = 'laeuft'")
    teile = [f"{neu_an_lead} neue Nachricht(en) an dich", f"{fertig} Aufgabe(n) abgeschlossen",
             f"{offen_entw} Frage(n) warten auf den Entwickler", f"{laeufe} Lauf/Läufe aktiv"]
    if beantwortet:
        teile.insert(0, "beantwortet: " + ", ".join(f"F{r[0]}" for r in beantwortet) + " → abarbeiten")
    return "Takt seit " + seit[11:16] + " UTC: " + " · ".join(teile)


class Dienst:
    def __init__(self, con):
        self.con = con
        self.sperre_bis = {}      # (projekt_id, agent) → Zeitpunkt des nächsten Versuchs nach Fehlschlag
        self.ueberwachung = ueberwachung.Waechter(con)
        self.neustarter = steuerung.Neustarter(con)

    def takt(self):
        """Ersetzt die händische Erinnerungskette des TL (→ doc/04 #13): je Projekt alle takt_min Minuten eine
        weckende Takt-Nachricht an jeden Lead mit lebender Sitzung. Im Halt nicht (weckt dann ohnehin nicht)."""
        jetzt = time.time()
        for p in self.con.execute("SELECT id, einstellungen FROM projekt").fetchall():
            try:
                minuten = float(json.loads(p["einstellungen"] or "{}").get("takt_min", TAKT_MIN))
            except ValueError:
                minuten = TAKT_MIN
            if minuten <= 0:
                continue
            for lead in self.con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND rolle = 'lead'", (p["id"],)):
                kennung = lead["kennung"]
                if not aktive_sitzung(self.con, p["id"], kennung) or kern.halt_gilt(self.con, p["id"], kennung):
                    continue
                letzte = self.con.execute("SELECT max(n.zeit_utc) FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                                          " WHERE n.projekt_id = ? AND n.art = 'takt' AND e.agent = ?",
                                          (p["id"], kennung)).fetchone()[0]
                if letzte and jetzt - _sekunden(letzte) < minuten * 60:
                    continue
                seit = letzte or self.con.execute("SELECT min(gestartet_utc) FROM sitzung s JOIN agent g ON g.id = s.agent_id"
                                                  " WHERE g.projekt_id = ? AND g.kennung = ? AND s.zustand = 'aktiv'",
                                                  (p["id"], kennung)).fetchone()[0] or db.jetzt()
                kern.posten(self.con, p["id"], "AMW", kennung, "takt", takt_text(self.con, p["id"], kennung, seit))
                log.info("Takt an %s", kennung)

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
            if s["schluessel_datei"] is None:            # Brücken-Sitzung (TL): kein Postfach, lebt vom Puls
                grenze = self.con.execute("SELECT puls_grenze_s FROM agent WHERE id = ?", (s["agent_id"],)).fetchone()[0]
                if time.time() - _sekunden(s["letzter_puls_utc"] or s["gestartet_utc"]) > (grenze or 10800):
                    with db.schreiben(self.con):
                        self.con.execute("UPDATE sitzung SET zustand = 'beendet', beendet_utc = ? WHERE id = ?",
                                         (db.jetzt(), s["id"]))
                    log.info("Brücken-Sitzung %s beendet (kein Puls)", s["id"])
                continue
            self.pruefe_sitzung(s)
        for p in self.con.execute("SELECT id FROM projekt").fetchall():   # Warteschlange: Speicher wieder frei, Agent wieder da
            for lid in betrieb.warteschlange(self.con, p["id"]):
                log.info("Warteschlange: L%s freigegeben", lid)
        statusline.uebernehmen(self.con)                                     # Kontext, Grenzen, Kosten je Sitzung
        try:                                                                 # abgestürzte Agenten fortsetzen (Profil)
            for e in self.neustarter.runde():
                log.info("Neustart: %s", e)
        except Exception as e:
            log.warning("Neustart: %s: %s", type(e).__name__, e)
        for e in self.ueberwachung.runde():                                  # Projekt-Server, Stillstand
            log.info("Überwachung: %s", e)
        try:                                                                 # Push aufs Handy (eigene Fehler nie störend)
            for p in self.con.execute("SELECT id FROM projekt").fetchall():
                for e in push.runde(self.con, p["id"]):
                    log.info("Push: %s", e)
        except Exception as e:
            log.warning("Push: %s: %s", type(e).__name__, e)


def _sekunden(utc):
    return calendar.timegm(time.strptime(utc, "%Y-%m-%dT%H:%M:%SZ"))


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
    p.add_argument("--port", type=int, default=None, help="Workbench-Oberfläche auf 127.0.0.1 (Vorgabe: Einstellung „port“)")
    p.add_argument("--ohne-web", action="store_true")
    a = p.parse_args(argv)
    global AUFSICHT_S
    from . import einstellungen                      # Zahnrad: Einstellungen dieses PCs (wirken beim Start)
    e = einstellungen.laden()
    AUFSICHT_S = e["aufsicht_s"]
    # die Einstellung geht vor dem Startparameter der geplanten Aufgabe (die immer --port 8780 mitgibt)
    port = e["port"] if "port" in einstellungen._datei() or a.port is None else a.port
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
            workbench.starten(port)
            log.info("Workbench: http://127.0.0.1:%s/", port)
        except OSError as x:                         # Port belegt – Wecker läuft trotzdem
            log.error("Workbench nicht gestartet (Port %s): %s", port, x)
        from . import abgleich                        # Stufe 2: nur mit "abgleich": true in turso.json
        abgleich.HOCH_S, abgleich.PULS_S, abgleich.EINGANG_S = e["abgleich_hoch_s"], e["abgleich_puls_s"], e["abgleich_eingang_s"]
        if abgleich.starten():
            log.info("Abgleich mit dem Online-Speicher an")
        from . import bruecke                         # Lesekopie + Befehlsdateien für den TL (FUSE, kein WAL)
        if e["bruecke_an"]:
            bruecke.KOPIE_S, bruecke.VON = e["bruecke_kopie_s"], e["bruecke_absender"]
            bruecke.starten()
            log.info("Brücke an: %s (Absender %s)", bruecke.EINGANG, bruecke.VON)
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
                d.takt()
                d.zustellen()                       # Wiederholung nach Fehlschlag, neue Anmeldungen, Takt
        except Exception:                           # nie sterben; Fehler protokollieren und weiter
            log.exception("Fehler im Durchgang")
        time.sleep(a.takt)


if __name__ == "__main__":
    sys.exit(main())
