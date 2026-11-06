"""Geführte Einrichtung `amw einrichten` (→ doc/installation.md).

Schritte, jeder wiederholbar (was es schon gibt, bleibt):
  1 Datenbank anlegen   2 Projekt   3 Lead und Agenten   4 Profile (Ordner, Rechte, Denkstufe)
  5 Hooks + Statusline-Brücke im Projektordner der Agenten   6 Startskript   7 Wächter als geplante Aufgabe
Interaktiv fragt er nach (Vorgaben in Klammern, Enter übernimmt); `schnell(...)` macht dasselbe ohne Fragen.
"""
import os

from . import db, einrichtung, einstellungen, kern, steuerung, wissen

STARTSKRIPT = os.path.join(einrichtung.WURZEL, "agenten-start.ps1")


RECHTE = ("vorgabe", "auto", "umgehen")
DENKSTUFEN = ("", "low", "medium", "high", "xhigh", "max")


def startsatz(kennung, lead=False):
    """Erste Anweisung einer neuen Sitzung: wer bin ich, wie rufe ich AMW auf, womit fange ich an."""
    amw = kern.BEFEHL
    return (f"Du bist {kennung}" + (", der Team-Lead" if lead else "") + f". Wir koordinieren uns über AMW: `{amw}`"
            f" (immer mit --von {kennung}). Lies zuerst `{amw} regeln --von {kennung}` und `{amw} lesen --von {kennung}`"
            + (", plane mit `amw leitbild`, `amw bogen`, `amw spec` und verteile die Schritte." if lead else
               f", dann hole Arbeit mit `{amw} schritt naechster --nehmen --von {kennung}`."))


def startskript_fuer(con, pid, pfad=STARTSKRIPT):
    """Mit mehreren Projekten eines je Projekt (agenten-start-<Projekt>.ps1); das erste Projekt behält den alten Namen,
    damit ein zweites Projekt nie das Skript des ersten überschreibt."""
    if pid == con.execute("SELECT min(id) FROM projekt").fetchone()[0]:
        return pfad
    name = con.execute("SELECT name FROM projekt WHERE id = ?", (pid,)).fetchone()["name"]
    kopf, ende = os.path.splitext(pfad)
    return f"{kopf}-{db.kurzname(name, pid)}{ende}"


def schnell(projekt, lead="TL", agenten=("CC1",), ordner=None, rechte="vorgabe", denkstufe=None, dienst=False,
            startskript=STARTSKRIPT, hooks=True, ausgabe=print, fernsteuerung=False, regeln_von=None, farbe=None):
    """Richtet alles ein; gibt die Liste der erledigten Schritte zurück. regeln_von: ein neues Projekt startet mit einer
    Kopie der Arbeitsregeln dieses Projekts (danach getrennt). Der Projektordner wird Einstellung des Projekts."""
    schritte = []
    if rechte not in RECHTE:
        raise kern.AmwFehler(f"Rechte: {' | '.join(RECHTE)}")
    if (denkstufe or "") not in DENKSTUFEN:
        raise kern.AmwFehler(f"Denkstufe: {' | '.join(DENKSTUFEN[1:])} oder leer")
    if ordner and not os.path.isdir(ordner):
        raise kern.AmwFehler(f"Projektordner {ordner} gibt es nicht – lege ihn zuerst an")
    if ordner and einrichtung.ordner_projekt(ordner) not in (None, projekt):   # vor dem Anlegen: nichts halb einrichten
        raise kern.AmwFehler(f"Ordner {ordner} gehört schon zum Projekt {einrichtung.ordner_projekt(ordner)} – "
                             "ein Ordner gehört zu genau einem Projekt (anderes Projekt: eigener Ordner)")
    pfad = db.db_pfad()
    if not os.path.exists(pfad):
        db.anlegen(pfad).close()
        schritte.append(f"Datenbank angelegt: {pfad}")
    con = db.verbinde(pfad)
    try:
        r = con.execute("SELECT id FROM projekt WHERE name = ?", (projekt,)).fetchone()
        quelle = db.projekt_id(con, regeln_von) if regeln_von and not r else None    # LookupError vor dem Anlegen
        if ordner and not (r and kern.projekt_ordner(con, r["id"])):
            for x in con.execute("SELECT id, name FROM projekt").fetchall():
                if os.path.normcase(kern.projekt_ordner(con, x["id"]) or "") == os.path.normcase(os.path.abspath(ordner)) \
                        and x["name"] != projekt:
                    raise kern.AmwFehler(f"Ordner {ordner} gehört schon zum Projekt {x['name']}")
        if r:
            pid = r["id"]
        else:
            with db.schreiben(con):
                pid = db.einfuegen(con, "projekt", name=projekt, angelegt_utc=db.jetzt())
            schritte.append(f"Projekt „{projekt}“ angelegt")
            if quelle:
                n = wissen.regeln_uebernehmen(con, pid, quelle)
                schritte.append(f"{n} Arbeitsregeln aus {regeln_von} übernommen (eigene Kopie)")
            if farbe:
                kern.projekt_einstellen(con, pid, kern.ENTWICKLER, farbe=farbe)
        if ordner and not kern.projekt_ordner(con, pid):
            schritte.append(f"Projektordner: {kern.projekt_ordner_setzen(con, pid, ordner)}")
        for kennung, rolle in [(lead, "lead")] + [(a, None) for a in agenten]:
            if not kennung:
                continue
            if not con.execute("SELECT 1 FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, kennung)).fetchone():
                kern.agent_neu(con, pid, kennung, rolle=rolle)
                schritte.append(f"Agent {kennung}" + (" (Lead)" if rolle else "") + " angelegt")
        if ordner:
            neu = []
            for a in ([lead] if lead else []) + list(agenten):   # nur leere Felder füllen – eigene Profile bleiben
                z = con.execute("SELECT ordner, startsatz, rechte, denkstufe FROM agent WHERE projekt_id = ? AND kennung = ?",
                                (pid, a)).fetchone()
                werte = {k: v for k, v in {"ordner": ordner, "startsatz": startsatz(a, a == lead), "rechte": rechte,
                                            "denkstufe": denkstufe or None}.items() if v and not z[k]}
                if "startsatz" in werte and fernsteuerung:  # neues Profil; sonst bleibt Remote Control aus
                    werte["fernsteuerung"] = True
                if werte:
                    steuerung.profil_setzen(con, pid, kern.ENTWICKLER, a, **werte)
                    neu.append(a)
            if neu:
                schritte.append(f"Profile für {', '.join(neu)}: Ordner {ordner}, Rechte {rechte}"
                                + (", Remote Control an" if fernsteuerung else ""))
            if hooks:
                aenderungen = einrichtung.agenten_ordner_einrichten(ordner, projekt=projekt)
                schritte.append(f"Projektordner eingerichtet ({', '.join(aenderungen) or 'war schon eingerichtet'})")
            if startskript:
                startskript = startskript_fuer(con, pid, startskript)
                with open(startskript, "w", encoding="utf-8-sig") as f:
                    f.write(steuerung.startskript(con, pid))
                schritte.append(f"Startskript: {startskript}")
    finally:
        con.close()
    if dienst:
        rc, aus = einrichtung.powershell(einrichtung.skript_einrichten(einstellungen.wert("port")))
        schritte.append("Wächter eingerichtet" if rc == 0 else f"Wächter NICHT eingerichtet: {aus.strip()[:200]}")
    for s in schritte:
        ausgabe("  ✓ " + s)
    return schritte


def _frage(text, vorgabe="", eingabe=input):
    antwort = eingabe(f"{text}" + (f" [{vorgabe}]" if vorgabe else "") + ": ").strip()
    return antwort or vorgabe


def _auswahl(text, erlaubt, vorgabe, eingabe=input, ausgabe=print):
    while True:
        antwort = _frage(text, vorgabe, eingabe)
        if antwort in erlaubt:
            return antwort
        ausgabe(f"  bitte eins von: {', '.join(x for x in erlaubt if x)}")


def _ja(text, vorgabe=True, eingabe=input):
    antwort = eingabe(f"{text} [{'J/n' if vorgabe else 'j/N'}]: ").strip().lower()
    return vorgabe if not antwort else antwort.startswith(("j", "y"))


def interaktiv(eingabe=input, ausgabe=print):
    ausgabe("AMW einrichten – Enter übernimmt die Vorgabe in Klammern. Abbrechen mit Strg+C.\n")
    ausgabe(f"Datenbank: {db.db_pfad()}" + ("" if os.path.exists(db.db_pfad()) else " (wird angelegt)"))
    projekt = _frage("Name des Projekts", "Mein Projekt", eingabe)
    lead = _frage("Kennung des Lead-Agenten (Team-Lead; leer = keiner)", "TL", eingabe)
    agenten = [a.strip() for a in _frage("Kennungen der Agenten, mit Komma", "CC1,CC2", eingabe).split(",") if a.strip()]
    regeln_von = None
    if os.path.exists(db.db_pfad()):                 # weiteres Projekt: Arbeitsregeln eines anderen übernehmen?
        con = db.verbinde()
        try:
            andere = [r[0] for r in con.execute("SELECT name FROM projekt WHERE name != ? ORDER BY id", (projekt,))]
            neu = not con.execute("SELECT 1 FROM projekt WHERE name = ?", (projekt,)).fetchone()
        finally:
            con.close()
        if andere and neu:
            regeln_von = _auswahl(f"Arbeitsregeln übernehmen von ({' | '.join(andere)}; leer = ohne Regeln starten)",
                                  andere + [""], "", eingabe, ausgabe) or None
    ordner = _frage("Projektordner, in dem die Agenten arbeiten (leer = später)", os.getcwd(), eingabe)
    while ordner and not os.path.isdir(ordner):
        ordner = _frage(f"{ordner} gibt es nicht – Projektordner (leer = später)", "", eingabe)
    rechte = _auswahl("Rechte der Agenten: vorgabe (Claude Code fragt) | auto | umgehen (alles erlauben)", RECHTE, "vorgabe",
                      eingabe, ausgabe)
    denkstufe = _auswahl("Denkstufe: low | medium | high | xhigh | max (leer = Vorgabe von Claude Code)", DENKSTUFEN, "",
                         eingabe, ausgabe)
    fern = _ja("Remote Control für die Agenten (Sitzungen auch über claude.ai bzw. die App steuerbar)?", False, eingabe)
    hooks = bool(ordner) and _ja(f"Hooks und Statusline-Brücke in {ordner}\\.claude\\settings.local.json eintragen (nötig zum Wecken)?", True, eingabe)
    ausgabe("\nDer Wächter weckt die Agenten und liefert die Workbench. Als geplante Aufgabe startet er bei jeder Anmeldung"
            " von selbst;\nzum Ausprobieren geht auch `amw dienst vordergrund` in einem eigenen Fenster.")
    dienst = _ja("Wächter als geplante Windows-Aufgabe einrichten?", True, eingabe)
    ausgabe("")
    schnell(projekt, lead or None, agenten, ordner or None, rechte, denkstufe, dienst, hooks=hooks, ausgabe=ausgabe,
            fernsteuerung=fern, regeln_von=regeln_von)
    port = einstellungen.wert("port")
    waechter = "läuft" if dienst else "starten mit `amw dienst einrichten --ja` (dauerhaft) oder `amw dienst vordergrund`"
    ausgabe(f"""
Fertig. Nächste Schritte:
  1. Workbench öffnen: http://127.0.0.1:{port}/  (Wächter {waechter})
  2. Agenten starten: in der Workbench auf die Kachel › „Starten“ – oder {STARTSKRIPT} ausführen
  3. Optional: Benachrichtigungen aufs Handy (doc/anleitung-push.md), Online-Seite (doc/online.md),
     Planung mit Leitbild und Bögen (doc/anleitung-planung.md)""")
