"""Tote Läufe erkennen, abschließen und melden (A2074): nach einem Rechner-Neustart oder wenn der Warte-Prozess weg ist.

Je Runde des Dienstes (laufdienst.runde), nur Läufe dieses Rechners, alle Projekte – auch Läufe mit Fenster und ohne gespeicherten
Befehl. Beendet nie einen Prozess; es wird nur nachgesehen und in der Datenbank abgeschlossen.
- Lebt ein Prozess noch? Die Nummer allein reicht nicht (Windows vergibt sie neu): der Prozess darf nicht jünger sein als die
  Anmeldung des Laufs (Warte-Prozess) bzw. als der Vermerk seiner Nummer (Befehl).
- Lebt der Warte-Prozess oder der Befehl nachweislich, schließt nichts den Lauf – auch nicht „Start vor dem Rechnerstart“ (ein
  Uhrsprung verschiebt den errechneten Rechnerstart). Lebt nur noch der Befehl, bleibt der Lauf „läuft“; der Besitzer erfährt es
  einmal, nach Ablauf der Frist einmal der Lead. Endet auch der Befehl, ist der Rückgabewert unbekannt: abgebrochen, nie ein Beleg.
- Ohne jede Prozessnummer (von Hand: lauf start/ende) zählt nur der Rechnerstart, nie „Warte-Prozess weg“.
- Was der Dienst ohnehin übernimmt (dran, aber noch von niemandem gestartet, mit Befehl und ohne Fenster – A1640), bleibt dort.
- Ersatz nur für Gesamtläufe eines Agenten: derselbe Ordner, sauber auf demselben Stand, kein neuerer Lauf dort, höchstens einmal.
  Gestartet wird nur der eingestellte gesamtlauf_befehl des Projekts, nie der gespeicherte Befehlstext.
- Nach einem Rechner-Neustart bekommt die erste neue Sitzung eines Agenten mit laufender Aufgabe einmal einen Weckruf mit dem Stand.
"""
import ctypes
import json
import logging
import os
import re
import subprocess
import time

from . import belegung, betrieb, db, kern

log = logging.getLogger("amw.laufabbruch")
NEUSTART, WARTE_WEG = "Rechner-Neustart", "Warte-Prozess weg"
TOLERANZ_S = 60                  # so viel früher als der errechnete Rechnerstart muss ein Lauf begonnen haben (Uhr-Korrekturen)
GLEICHER_START_S = 120           # zwei errechnete Rechnerstarts, die höchstens so weit auseinanderliegen, sind derselbe
JUENGER_S = 5                    # Spielraum beim Vergleich „Prozess jünger als der Vermerk“ (Zeiten in ganzen Sekunden)
NEUE_SITZUNG_S = 15 * 60         # nur eine frisch angemeldete Sitzung bekommt den Weckruf nach dem Neustart
ERSATZ, VERWAIST, FRIST, GEWECKT = "lauf_ersatz", "lauf_verwaist", "lauf_verwaist_frist", "neustart_geweckt"


# --- Nachsehen ---------------------------------------------------------------------------------------------------------------

def rechnerstart():
    """Wann dieser Rechner gestartet ist (Sekunden seit 1970, errechnet aus Uhrzeit minus Laufzeit) – oder None."""
    try:
        if os.name == "nt":
            f = ctypes.windll.kernel32.GetTickCount64
            f.restype = ctypes.c_ulonglong
            return time.time() - f() / 1000
        with open("/proc/uptime", encoding="ascii") as d:
            return time.time() - float(d.read().split()[0])
    except (OSError, AttributeError, ValueError, IndexError):
        return None


class Prozesse:
    """Die Prozessliste einer Runde – erst gelesen, wenn sie gebraucht wird."""
    def __init__(self):
        self._liste = None

    def seit(self, nummer):
        if self._liste is None:
            self._liste = {p["pid"]: p["seit"] for p in belegung.prozesse()}
        s = self._liste.get(nummer)
        return s.timestamp() if s else None

    def lebt(self, nummer, spaetestens):
        """True: der Prozess lebt und ist nicht jünger als `spaetestens` (Sekunden); False: weg oder die Nummer gehört jetzt einem
        anderen; None: keine Nummer bekannt. Ist die Startzeit nicht lesbar, gilt er als lebend – nie ein Abbruch auf Verdacht."""
        if not nummer:
            return None
        if not belegung.prozess_da(nummer):
            return False
        s = self.seit(nummer)
        return s is None or spaetestens is None or s <= spaetestens + JUENGER_S

    def warte_prozess(self, l):
        return self.lebt(l["waechter"], db.utc_sek(l["angemeldet_utc"]))

    def befehl(self, l):
        return self.lebt(belegung.lauf_pid(l["id"]), belegung.lauf_pid_zeit(l["id"]))


def _vermerkt(con, art, lid):
    return con.execute("SELECT 1 FROM plan_ereignis WHERE art = ? AND text = ?", (art, json.dumps({"lauf": lid}))).fetchone() is not None


def _vermerken(con, pid, art, daten, aufgabe_id=None):
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=art, aufgabe_id=aufgabe_id,
                 text=json.dumps(daten))


def _senden(con, pid, an, art, kurz, text, aufgabe_id=None):
    """Nachricht der AMW; ist der Empfänger entfernt oder unbekannt, geht sie an den Lead."""
    try:
        with db.schreiben(con):
            kern._posten(con, pid, "AMW", an, art, kurz[:140], text, aufgabe_id=aufgabe_id)
    except kern.AmwFehler:
        lead = kern.lead(con, pid)
        if lead and lead != an:
            with db.schreiben(con):
                kern._posten(con, pid, "AMW", lead, art, kurz[:140], text)


# --- Eine Runde --------------------------------------------------------------------------------------------------------------

def vom_dienst(l):
    """Dran, aber von niemandem gestartet, mit Befehl und ohne Fenster: den übernimmt der Dienst selbst (A1640)."""
    return l["ausfuehrer"] is None and bool(l["befehl"]) and not l["schirm"]


def grund_tot(l, prozesse, start):
    """Warum dieser laufende Lauf tot ist – oder None. `start`: rechnerstart()."""
    if vom_dienst(l):
        return None
    w, c = prozesse.warte_prozess(l), prozesse.befehl(l)
    if w or c:
        return None                                      # lebt nachweislich: nichts schließt ihn
    if start and l["start_utc"] and db.utc_sek(l["start_utc"]) + TOLERANZ_S < start:
        return NEUSTART
    if w is False and l["ausfuehrer"] != "dienst":       # „dienst“: der Warte-Prozess war schon vorher weg – das prüft laufdienst
        return WARTE_WEG
    return None


def runde(con, faeden=(), start=None, prozesse=None):
    """Tote Läufe dieses Rechners abschließen, verwaiste melden. faeden: Läufe, die dieser Dienst gerade rechnet. Ereignis-Zeilen."""
    start = rechnerstart() if start is None else start
    prozesse = prozesse or Prozesse()
    ereignisse = []
    for l in con.execute("SELECT * FROM lauf l WHERE status = 'laeuft' AND NOT EXISTS (SELECT 1 FROM ki_auftrag k WHERE k.lauf_id = l.id)"
                         " AND " + betrieb.HIER + " ORDER BY id", (betrieb.rechner(),)).fetchall():
        if l["id"] in faeden:
            continue
        try:
            g = grund_tot(l, prozesse, start)
            if g:
                abschliessen(con, l, g)
                ereignisse.append(f"L{l['id']} abgebrochen: {g}")
            elif l["ausfuehrer"] == "agent" and prozesse.warte_prozess(l) is False and prozesse.befehl(l):
                if verwaist(con, l):
                    ereignisse.append(f"L{l['id']}: Warte-Prozess weg, der Befehl läuft noch")
        except kern.AmwFehler as e:                      # im selben Moment von seinem Besitzer beendet
            log.info("L%s: %s", l["id"], e)
    for x in nach_neustart(con, start):
        ereignisse.append(x)
    return ereignisse + erinnern(con)


def verwaist(con, l):
    """Nur noch der Befehl lebt: der Besitzer erfährt es einmal; ist die Frist des Laufs um, einmal der Lead."""
    lid, pid, neu = l["id"], l["projekt_id"], False
    if not _vermerkt(con, VERWAIST, lid):
        with db.schreiben(con):
            _vermerken(con, pid, VERWAIST, {"lauf": lid}, l["aufgabe_id"])
        _senden(con, pid, l["agent"], "meldung", f"L{lid}: dein Warte-Prozess ist weg, der Befehl läuft noch",
                f"{betrieb.kurzfassung(l['beschreibung'], 120)}\nDer Lauf bleibt „läuft“, bis der Befehl endet. Der Rückgabewert ist dann"
                " unbekannt – als Beleg gilt er nicht. Bitte nicht parallel neu starten.", l["aufgabe_id"])
        neu = True
    if l["frist_min"] and l["start_utc"] and time.time() > db.utc_sek(l["start_utc"]) + l["frist_min"] * 60 and not _vermerkt(con, FRIST, lid):
        with db.schreiben(con):
            _vermerken(con, pid, FRIST, {"lauf": lid}, l["aufgabe_id"])
        _senden(con, pid, kern.lead(con, pid) or l["agent"], "meldung", f"L{lid} läuft ohne Warte-Prozess über seine Frist ({l['frist_min']:g} min)",
                f"{betrieb.kurzfassung(l['beschreibung'], 120)} · von {l['agent']}\nDie AMW beendet den Befehl nicht; er belegt weiter seinen Platz.")
        neu = True
    return neu


# --- Abschließen und melden --------------------------------------------------------------------------------------------------

def ausgabestand(pfad):
    """Letzter Stand der Ausgabe: „Modul 41 von 235“ (letztes „[n/m]“) und die letzte Zeile – so viel, wie da ist."""
    try:
        with open(pfad, encoding="utf-8", errors="replace") as f:
            zeilen = [z.strip() for z in f if z.strip() and not z.startswith("# ")]
    except (OSError, TypeError):
        return "keine Ausgabe"
    if not zeilen:
        return "keine Ausgabe"
    m = next((m for m in (re.match(r"\[(\d+)/(\d+)\]", z) for z in reversed(zeilen)) if m), None)
    return (f"Modul {m.group(1)} von {m.group(2)} · " if m else "") + "letzte Zeile: " + zeilen[-1][:160]


def _befehl(l):
    try:
        return [str(x) for x in json.loads(l["befehl"] or "[]")]
    except ValueError:
        return []


def neustart_befehl(l, pfad):
    """Der fertige Befehl, mit dem der Besitzer den Lauf neu startet – die alte Ausgabe bleibt (neue Ergebnis-Datei)."""
    b = _befehl(l)
    text = " ".join(str(l["beschreibung"]).split()).replace('"', "'")
    kopf = f'--{"schwer" if l["schwer"] else "leicht"}{" --schirm" if l["schirm"] else ""} --beschreibung "{text}"' + (
        f' --aufgabe {l["aufgabe_id"]}' if l["aufgabe_id"] else "")
    if not b:
        return f"amw lauf start {kopf}"
    stamm, endung = os.path.splitext(pfad)
    zeile = f'"{b[0]}"' if len(b) == 1 else subprocess.list2cmdline(b)
    return f'amw lauf ausfuehren {kopf}' + (f' --dauer {l["erwartet_min"]:g}' if l["erwartet_min"] else "") + (
        f' --ergebnis "{stamm}-neu{endung}" -- {zeile}') + (f"   (im Ordner {l['ordner']})" if l["ordner"] else "")


def abschliessen(con, l, grund):
    """Toten Lauf als abgebrochen abschließen (Rückgabewert unbekannt), Ausgabe behalten, PID-Vermerk weg, Gründe offen lassen,
    Besitzer (auftrag) und Lead (meldung) je einmal benachrichtigen; Gesamtläufe unter den Bedingungen oben neu einreihen."""
    from . import laufdienst, wartegrund
    pid, lid = l["projekt_id"], l["id"]
    pfad = laufdienst.ergebnis_pfad(l)
    stand = ausgabestand(pfad)
    betrieb.lauf_ende(con, pid, l["agent"], lid, None, f"abgebrochen: {grund} · Ausgabe: {pfad} · {stand}"[:500], abgebrochen=True,
                      melden=False)
    if os.path.isfile(pfad):
        try:
            with open(pfad, "a", encoding="utf-8") as f:
                f.write(f"\n# Ende: {time.strftime('%Y-%m-%d %H:%M:%S')} · rc ? · abgebrochen: {grund} · festgestellt vom Dienst\n")
        except OSError:
            pass
    belegung.lauf_vergessen(lid)
    neu, schon = (None, False) if betrieb.selbst_gestartet(con, lid) else ersatz(con, l, pfad)
    if neu:
        with db.schreiben(con):
            wartegrund.lauf_ersetzen(con, pid, lid, neu)
    selbst = betrieb.selbst_gestartet(con, lid)
    if neu:
        weiter = (f"L{neu} rechnet diesen Stand schon – nicht selbst starten." if schon else
                  f"Ersatz L{neu} läuft (vom Dienst gerechnet) – nicht selbst starten.")
    elif selbst:
        weiter = "Ein Lauf der AMW selbst – sie startet ihn auf ihrem eigenen Weg neu, hier wird nichts eingereiht."
    else:
        weiter = "Neu starten: " + neustart_befehl(l, pfad)
    wartende = wartegrund.wartet_auf_lauf(con, pid, neu or lid)
    liste = "" if not wartende else wartegrund.warteliste(lid, wartende) if not neu else (
        "\nEs warten: " + ", ".join(f"A{a['id']} ({a['agent'] or '–'})" for a in wartende) + f" – jetzt auf L{neu}")
    kurz = f"L{lid} abgebrochen ({grund}): {betrieb.kurzfassung(l['beschreibung'], 60)}"
    text = f"{betrieb.kurzfassung(l['beschreibung'], 200)} · von {l['agent']}\nStand: {stand}\nAusgabe: {pfad}\n{weiter}{liste}"
    lead = kern.lead(con, pid)
    if not selbst and l["agent"] != lead:
        _senden(con, pid, l["agent"], "auftrag", kurz, text, l["aufgabe_id"] if _offen(con, l["aufgabe_id"]) else None)
    if lead:
        _senden(con, pid, lead, "meldung" if selbst or l["agent"] != lead else "auftrag", kurz, text)
    for a in {a["agent"] for a in wartende if a["agent"]} - {l["agent"], lead}:     # wartet ein Dritter darauf, erfährt er es auch
        _senden(con, pid, a, "meldung", kurz, text)
    return neu


def _offen(con, aid):
    r = con.execute("SELECT status FROM aufgabe WHERE id = ?", (aid,)).fetchone() if aid else None
    return bool(r) and r[0] not in ("fertig", "verworfen")


# --- Ersatz ------------------------------------------------------------------------------------------------------------------

def _norm(p):
    return os.path.normcase(os.path.realpath(p)) if p else None


def gesamtlauf(con, l):
    """Der eingestellte Gesamtlauf-Befehl des Projekts, wenn dieser Lauf ihn gerechnet hat – sonst None. Verlangt einen
    gespeicherten Befehl; die Beschreibung allein reicht nicht."""
    from . import einrichtung, freigabereif
    if not _befehl(l):
        return None
    pid = l["projekt_id"]
    amw = bool(_norm(kern.projekt_ordner(con, pid))) and _norm(kern.projekt_ordner(con, pid)) == _norm(einrichtung.WURZEL)
    b = freigabereif._gesamtlauf_befehl(con, pid, amw)
    return b if b and freigabereif.ist_gesamtlauf(con, pid, l, amw) else None


def ersatz(con, l, pfad):
    """(Nummer, schon da): neuer Gesamtlauf statt des toten – oder der neuere, der diesen Ordner schon rechnet; (None, False) ohne."""
    from . import laufdienst
    pid, lid = l["projekt_id"], l["id"]
    if l["ausfuehrer"] != "agent" or l["schirm"] or not l["ordner"]:
        return None, False
    b = gesamtlauf(con, l)
    if not b:
        return None, False
    try:
        with open(pfad, encoding="utf-8", errors="replace") as f:
            m = next((m for m in (re.match(r"# Stand ([0-9a-f]{40}) sauber\s*$", z) for z in f.read(4000).splitlines()) if m), None)
    except OSError:
        m = None
    alt = betrieb.pruefstand(_befehl(l), l["ordner"])     # beginnt der Befehl mit cd, muss es derselbe Ordner sein
    jetzt = betrieb.pruefstand([b], l["ordner"])
    if not m or not alt or not jetzt or _norm(alt[0]) != _norm(l["ordner"]) or _norm(jetzt[0]) != _norm(l["ordner"]) or not jetzt[2] \
            or jetzt[1] != m.group(1):
        return None, False
    for n in con.execute("SELECT * FROM lauf l WHERE projekt_id = ? AND id > ? AND status IN ('laeuft', 'angemeldet') AND ordner IS NOT NULL"
                         " AND " + betrieb.HIER + " ORDER BY id", (pid, lid, betrieb.rechner())).fetchall():
        if _norm(n["ordner"]) == _norm(l["ordner"]) and gesamtlauf(con, n):
            return n["id"], True
    if any(json.loads(r[0]).get("neu") == lid for r in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ?",
                                                                   (pid, ERSATZ))):
        return None, False                                # selbst schon ein Ersatz: ein zweites Mal startet der Besitzer
    if laufdienst.darf_ausfuehren(con, l):
        return None, False
    try:
        neu = betrieb.lauf_start(con, pid, l["agent"], f"{l['beschreibung']} (Ersatz für L{lid})", None, bool(l["schwer"]), False,
                                 l["aufgabe_id"] if _offen(con, l["aufgabe_id"]) else None, warten=True, erwartet_min=l["erwartet_min"],
                                 braucht_gb=l["braucht_gb"], befehl=[b], ordner=l["ordner"], frist_min=l["frist_min"])
    except kern.AmwFehler as e:
        log.info("L%s: kein Ersatz: %s", lid, e)
        return None, False
    with db.schreiben(con):
        _vermerken(con, pid, ERSATZ, {"alt": lid, "neu": neu}, l["aufgabe_id"])
    return neu, False


# --- Weckruf nach dem Neustart, Erinnerung -----------------------------------------------------------------------------------

def nach_neustart(con, start, jetzt=None):
    """Je Rechnerstart und Agent einmal: die erste Sitzung nach dem Start, frisch angemeldet, und eine Aufgabe, die seit vor dem
    Start läuft → auftrag mit dem Stand. Kein Weckruf bei Kompaktierung oder Sitzungswechsel ohne Rechner-Neustart."""
    if not start:
        return []
    jetzt = jetzt or time.time()
    aus = []
    for g in con.execute("SELECT id, projekt_id, kennung FROM agent WHERE entfernt_utc IS NULL ORDER BY id").fetchall():
        zeiten = [(db.utc_sek(s["gestartet_utc"]), s["zustand"]) for s in con.execute(
            "SELECT gestartet_utc, zustand FROM sitzung WHERE agent_id = ? ORDER BY id", (g["id"],)) if s["gestartet_utc"]]
        zeiten = [(t, z) for t, z in zeiten if t >= start]
        if not zeiten or jetzt - zeiten[0][0] > NEUE_SITZUNG_S or zeiten[-1][1] not in ("aktiv", "ruht"):
            continue
        aufgabe = next((a for a in con.execute("SELECT * FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status = 'laeuft' ORDER BY rang, id",
                                               (g["projekt_id"], g["kennung"])) if a["begonnen_utc"] and db.utc_sek(a["begonnen_utc"]) < start), None)
        if not aufgabe:
            continue
        if any(d.get("agent") == g["kennung"] and abs(d.get("start", 0) - start) <= GLEICHER_START_S for d in (
                json.loads(r[0]) for r in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ?",
                                                      (g["projekt_id"], GEWECKT)))):
            continue
        tote = con.execute("SELECT id, beschreibung FROM lauf WHERE projekt_id = ? AND agent = ? AND status = 'abgebrochen' AND ergebnis LIKE ?"
                           " AND ende_utc >= ? ORDER BY id", (g["projekt_id"], g["kennung"], f"abgebrochen: {NEUSTART}%",
                                                              time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(start)))).fetchall()
        with db.schreiben(con):
            _vermerken(con, g["projekt_id"], GEWECKT, {"agent": g["kennung"], "start": int(start)}, aufgabe["id"])
            kern._posten(con, g["projekt_id"], "AMW", g["kennung"], "auftrag",
                         f"Rechner neu gestartet – A{aufgabe['id']} läuft noch: weiter"[:140],
                         f"A{aufgabe['id']} {aufgabe['titel'][:120]} (läuft seit {aufgabe['begonnen_utc'][11:16]} UTC)\n"
                         + ("Beim Neustart abgebrochen: " + ", ".join(f"L{t['id']} {betrieb.kurzfassung(t['beschreibung'], 60)}" for t in tote)
                            if tote else "Kein Lauf von dir wurde dabei abgebrochen."), aufgabe_id=aufgabe["id"])
        aus.append(f"{g['kennung']}: Weckruf nach Rechner-Neustart (A{aufgabe['id']})")
    return aus


def erinnern(con, jetzt=None):
    """Wartet eine Aufgabe nach der üblichen Frist (warten_agent) noch auf einen abgebrochenen Lauf, einmal „Grund noch aktuell?“."""
    from . import warten_agent
    jetzt = jetzt or time.time()
    aus = []
    for g in con.execute("SELECT w.id, w.projekt_id, w.bezug, w.aufgabe_id, a.agent, a.titel, l.ende_utc FROM wartegrund w"
                         " JOIN aufgabe a ON a.id = w.aufgabe_id JOIN lauf l ON w.bezug = 'L' || l.id AND l.projekt_id = w.projekt_id"
                         " WHERE w.art = 'lauf' AND w.erledigt_utc IS NULL AND l.status = 'abgebrochen' AND a.status IN ('wartet', 'blockiert')"
                         " AND a.einstufung = 'aktiv'").fetchall():
        if not g["agent"] or not g["ende_utc"] or jetzt - db.utc_sek(g["ende_utc"]) < warten_agent.warte_min(con, g["projekt_id"]) * 60:
            continue
        if con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = 'lauf_grund_erinnert' AND text = ?",
                       (g["projekt_id"], f"G{g['id']}")).fetchone():
            continue
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=g["projekt_id"], zeit_utc=db.jetzt(), von="AMW", art="lauf_grund_erinnert",
                         aufgabe_id=g["aufgabe_id"], text=f"G{g['id']}")
        _senden(con, g["projekt_id"], g["agent"], "meldung", f"A{g['aufgabe_id']} wartet noch auf den abgebrochenen {g['bezug']} – Grund noch aktuell?",
                f"{g['titel']}\nErsatz nennen: amw aufgabe wartet {g['aufgabe_id']} --auf L<neu> · aufheben: --erledigt {g['bezug']}", g["aufgabe_id"])
        aus.append(f"A{g['aufgabe_id']} wartet noch auf abgebrochenen {g['bezug']}")
    return aus
