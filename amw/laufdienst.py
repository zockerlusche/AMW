"""Läufe überleben den Warte-Prozess (A1640) und die AMW lernt ihren Bedarf (A1641) – im Dienst, je Runde.

- Übernehmen: Ein Lauf von „amw lauf ausfuehren“ ist dran, aber sein Warte-Prozess im Fenster des Agenten lebt nicht mehr
  (Claude Code beendet Hintergrund-Prozesse bei knappem Speicher). Dann startet der Dienst genau den beim Einreihen
  gespeicherten Befehl im gespeicherten Ordner – nie etwas anderes. Die Ausgabe geht direkt in die Ergebnis-Datei, am Ende
  steht der Lauf mit seinem Rückgabewert da und der Agent bekommt eine Meldung (die einzige, die ihn weckt).
  Läufe mit Fenster (Bildschirm) übernimmt der Dienst nicht.
- Umgebung: die des Dienstes ohne AMW_AGENT, AMW_PROJEKT und alles von Claude Code (CLAUDE_CODE_*) – gespeichert wird keine.
- Neustart des Dienstes: Lebt ein vom Dienst gestarteter Befehl noch, passt die neue Runde weiter auf ihn auf (Rückgabewert
  dann unbekannt); ist er weg, endet der Lauf mit diesem Hinweis.
- Spitze: je laufendem Lauf mit bekanntem Prozess der belegte Speicher des Prozessbaums, das Maximum steht in lauf.spitze_gb.
"""
import json
import logging
import os
import subprocess
import threading
import time

from . import belegung, betrieb, db, kern

log = logging.getLogger("amw.laufdienst")
PRUEF_S = 5
RC_FRIST, RC_BEENDET = 124, 202          # wie „amw lauf ausfuehren“


def umgebung():
    """Umgebung für einen Dienst-Lauf: die des Dienstes, ohne Kennung des Agenten und ohne alles von Claude Code."""
    return {k: v for k, v in os.environ.items()
            if k not in ("AMW_AGENT", "AMW_PROJEKT") and not k.startswith("CLAUDE_CODE_") and k != "CLAUDECODE"}


def ergebnis_pfad(l):
    """Die gespeicherte Ergebnis-Datei, sonst daten/laeufe/L<nr>.txt neben der Datenbank."""
    if l["ergebnis_datei"]:
        return l["ergebnis_datei"]
    ordner = os.path.join(os.path.dirname(db.db_pfad()), "laeufe")
    os.makedirs(ordner, exist_ok=True)
    return os.path.join(ordner, f"L{l['id']}.txt")


def _baum_beenden(prozess_id):
    """Den selbst gestarteten Befehl samt Kindern beenden (nur eigene Prozesse des Dienstes)."""
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(prozess_id)], capture_output=True)
    else:
        import signal
        try:
            os.killpg(prozess_id, signal.SIGKILL)
        except OSError:
            pass


def darf_ausfuehren(con, l):
    """Grund, warum der Dienst diesen Lauf NICHT ausführen darf – oder None (TL D982): Agent entfernt oder angehalten; Ordner
    nicht innerhalb seines Arbeitsordners oder eines Zusatzordners (aufgelöster Pfad, keine Umwege über ..)."""
    a = con.execute("SELECT ordner, zusatzordner, entfernt_utc FROM agent WHERE projekt_id = ? AND kennung = ?",
                    (l["projekt_id"], l["agent"])).fetchone()
    if not a or a["entfernt_utc"]:
        return f"{l['agent']} ist entfernt"
    if kern.halt_gilt(con, l["projekt_id"], l["agent"]):
        return "HALT gilt"
    if not l["ordner"]:
        return "kein Ordner gespeichert"
    try:
        zusatz = json.loads(a["zusatzordner"] or "[]")
    except ValueError:
        zusatz = []
    basen = [b for b in [a["ordner"], *zusatz] if b]
    if not basen:
        return f"für {l['agent']} ist kein Arbeitsordner eingetragen"
    norm = lambda x: os.path.normcase(os.path.realpath(x))
    ziel = norm(l["ordner"])
    for b in basen:
        try:
            if os.path.commonpath([ziel, norm(b)]) == norm(b):
                return None
        except ValueError:                              # anderes Laufwerk
            continue
    return f"Ordner {l['ordner']} liegt nicht im Arbeitsordner von {l['agent']}"


def _letzte_zeile(pfad):
    try:
        with open(pfad, encoding="utf-8", errors="replace") as f:
            zeilen = [z.strip() for z in f.readlines()[-20:] if z.strip() and not z.startswith("# ")]
        return zeilen[-1][:200] if zeilen else ""
    except OSError:
        return ""


def _abschliessen(con, l, rc, pfad, grund=None, rc_bekannt=True, stand=None):
    """Lauf beenden, Fuß in die Ergebnis-Datei, Meldung an den Agenten."""
    try:
        with open(pfad, "a", encoding="utf-8") as f:
            f.write(f"# Ende: {time.strftime('%Y-%m-%d %H:%M:%S')} · rc {rc if rc_bekannt else '?'}"
                    + (f" · abgebrochen: {grund}" if grund else "") + " · gerechnet vom Dienst\n")
    except OSError:
        pass
    letzte = _letzte_zeile(pfad)
    text = (f"rc {rc if rc_bekannt else '?'}" + (f" · {stand}" if stand else "") + f" · Ausgabe: {pfad}" + (f" · {letzte}" if letzte and not grund else "")
            + (f" · abgebrochen: {grund}" if grund else ""))[:500]
    jetzt = betrieb.lauf_zeile(con, l["projekt_id"], l["id"])
    if jetzt["status"] == "laeuft":
        betrieb.lauf_ende(con, l["projekt_id"], l["agent"], l["id"], rc if rc_bekannt else None, text, abgebrochen=bool(grund))
    kurz = (f"L{l['id']} {'abgebrochen' if grund else 'fertig'}, rc {rc if rc_bekannt else '?'} – vom Dienst gerechnet "
            f"(dein Warte-Prozess war weg): {betrieb.kurzfassung(l['beschreibung'], 70)}")
    text = f"Ausgabe: {pfad}" + (f"\n{letzte}" if letzte else "")
    try:
        with db.schreiben(con):
            kern._posten(con, l["projekt_id"], "AMW", l["agent"], "meldung", kurz, text, aufgabe_id=l["aufgabe_id"])
    except kern.AmwFehler:                              # Agent entfernt: dann erfährt es sein Lead
        lead = kern.lead(con, l["projekt_id"])
        if lead and lead != l["agent"]:
            with db.schreiben(con):
                kern._posten(con, l["projekt_id"], "AMW", lead, "meldung", kurz, text)


def rechnen(lid):
    """Faden des Dienstes: genau den gespeicherten Befehl im gespeicherten Ordner ausführen und den Lauf abschließen."""
    con = db.verbinde()
    try:
        l = con.execute("SELECT * FROM lauf WHERE id = ?", (lid,)).fetchone()
        befehl = json.loads(l["befehl"])
        pfad = ergebnis_pfad(l)
        stand = betrieb.stand_text(betrieb.pruefstand(befehl, l["ordner"]))   # was beim Start wirklich dort liegt (TL #24259)
        with open(pfad, "w", encoding="utf-8", errors="replace") as f:
            f.write(f"# AMW L{lid} · {l['agent']} · {l['beschreibung']}\n# Befehl: {' '.join(befehl)}\n"
                    f"# Ordner: {l['ordner']}\n# {stand}\n# Start: {time.strftime('%Y-%m-%d %H:%M:%S')} · gerechnet vom Dienst (Warte-Prozess war weg)\n")
        eins = len(befehl) == 1
        try:
            with open(pfad, "a", encoding="utf-8", errors="replace") as aus:
                proc = subprocess.Popen(befehl[0] if eins else befehl, shell=eins, cwd=l["ordner"] or None, env=umgebung(),
                                        stdout=aus, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), start_new_session=os.name != "nt")
        except OSError as e:
            _abschliessen(con, l, 127, pfad, f"Start fehlgeschlagen: {e}")
            return
        belegung.lauf_merken(lid, proc.pid)
        log.info("L%s: Befehl gestartet (PID %s)", lid, proc.pid)
        frist = time.time() + l["frist_min"] * 60 if l["frist_min"] else None
        grund, rc_grund = None, None
        while proc.poll() is None:
            time.sleep(PRUEF_S)
            if proc.poll() is not None:
                break
            s = con.execute("SELECT status FROM lauf WHERE id = ?", (lid,)).fetchone()["status"]
            if s != "laeuft":
                grund, rc_grund = f"L{lid} wurde beendet ({s})", RC_BEENDET
            elif frist and time.time() >= frist:
                grund, rc_grund = f"Frist {l['frist_min']:g} min erreicht", RC_FRIST
            if grund:
                _baum_beenden(proc.pid)
                try:
                    proc.wait(timeout=30)
                except subprocess.TimeoutExpired:
                    pass
                break
        belegung.lauf_vergessen(lid)
        _abschliessen(con, l, rc_grund if grund else proc.returncode, pfad, grund, stand=stand)
    except Exception as e:                              # nie den Dienst stören – aber den Lauf nicht hängen lassen
        log.warning("L%s: %s: %s", lid, type(e).__name__, e)
        try:
            l = con.execute("SELECT * FROM lauf WHERE id = ?", (lid,)).fetchone()
            if l and l["status"] == "laeuft":
                betrieb.lauf_ende(con, l["projekt_id"], l["agent"], lid, None, f"Dienst-Fehler: {type(e).__name__}: {e}"[:500], abgebrochen=True)
        except Exception:
            pass
    finally:
        con.close()


def aufpassen(lid, prozess_id):
    """Nach einem Neustart des Dienstes: auf einen noch laufenden, früher gestarteten Befehl warten (Rückgabewert unbekannt)."""
    con = db.verbinde()
    try:
        while belegung.prozess_da(prozess_id):
            s = con.execute("SELECT status FROM lauf WHERE id = ?", (lid,)).fetchone()["status"]
            if s != "laeuft":
                _baum_beenden(prozess_id)
                break
            time.sleep(PRUEF_S)
        l = con.execute("SELECT * FROM lauf WHERE id = ?", (lid,)).fetchone()
        belegung.lauf_vergessen(lid)
        if l["status"] == "laeuft":
            _abschliessen(con, l, None, ergebnis_pfad(l), rc_bekannt=False)
    finally:
        con.close()


class Laufdienst:
    """Je Runde des Dienstes: Spitzen messen, verwaiste Läufe übernehmen, nach einem Neustart weiter aufpassen."""

    def __init__(self, con, starten=None):
        self.con, self.faeden = con, {}
        self.starten = starten or (lambda ziel, *args: threading.Thread(target=ziel, args=args, daemon=True).start())

    def spitzen(self):
        laufend = self.con.execute("SELECT id, spitze_gb FROM lauf l WHERE status = 'laeuft' AND " + betrieb.HIER,
                                   (betrieb.rechner(),)).fetchall()
        mit_pid = [(l, belegung.lauf_pid(l["id"])) for l in laufend]
        mit_pid = [(l, p) for l, p in mit_pid if p]
        if not mit_pid:
            return
        liste = belegung.prozesse()
        with db.schreiben(self.con):
            for l, p in mit_pid:
                gb = belegung.baum_gb(liste, p) or 0.0
                if gb > (l["spitze_gb"] or 0):
                    self.con.execute("UPDATE lauf SET spitze_gb = ? WHERE id = ?", (round(gb, 2), l["id"]))

    def runde(self):
        ereignisse = []
        try:
            self.spitzen()
        except Exception as e:
            log.warning("Spitzen: %s: %s", type(e).__name__, e)
        for l in self.con.execute("SELECT * FROM lauf l WHERE status = 'laeuft' AND befehl IS NOT NULL AND schirm = 0 AND "
                                  + betrieb.HIER, (betrieb.rechner(),)).fetchall():
            lid = l["id"]
            if lid in self.faeden:
                continue
            if l["ausfuehrer"] is None and not belegung.prozess_da(l["waechter"]):
                if betrieb.lauf_uebernehmen(self.con, lid, "dienst"):
                    self.faeden[lid] = True
                    grund = darf_ausfuehren(self.con, l)
                    if grund:                           # nicht ausführen – Lauf beenden, Agent erfährt warum
                        _abschliessen(self.con, l, None, ergebnis_pfad(l), f"nicht ausgeführt: {grund}", rc_bekannt=False)
                        ereignisse.append(f"L{lid} nicht ausgeführt: {grund}")
                        continue
                    self.starten(rechnen, lid)
                    ereignisse.append(f"L{lid} übernommen – Warte-Prozess {l['waechter']} lebt nicht mehr")
            elif l["ausfuehrer"] == "dienst":           # vom Dienst gestartet, aber nicht von diesem: Neustart dazwischen
                self.faeden[lid] = True
                p = belegung.lauf_pid(lid)
                if p and belegung.prozess_da(p):
                    self.starten(aufpassen, lid, p)
                    ereignisse.append(f"L{lid}: passe nach Neustart weiter auf (PID {p})")
                else:
                    pfad = ergebnis_pfad(l)
                    _abschliessen(self.con, l, None, pfad, "Dienst neu gestartet, der Befehl lief nicht mehr", rc_bekannt=False)
                    ereignisse.append(f"L{lid}: nach Neustart beendet (Befehl lief nicht mehr)")
        return ereignisse
