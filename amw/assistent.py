"""Geführte Einrichtung `amw einrichten` (→ doc/installation.md).

Schritte, jeder wiederholbar (was es schon gibt, bleibt):
  1 Datenbank anlegen   2 Projekt   3 Lead und Agenten   4 Profile (Ordner, Rechte, Denkstufe)
  5 Hooks + Statusline-Brücke im Projektordner der Agenten   6 Startskript   7 Wächter als geplante Aufgabe
Interaktiv fragt er nach (Vorgaben in Klammern, Enter übernimmt); `schnell(...)` macht dasselbe ohne Fragen.
"""
import os

from . import db, einrichtung, einstellungen, kern, steuerung

STARTSKRIPT = os.path.join(einrichtung.WURZEL, "agenten-start.ps1")


def schnell(projekt, lead="TL", agenten=("CC1",), ordner=None, rechte="vorgabe", denkstufe=None, dienst=False,
            startskript=STARTSKRIPT, hooks=True, ausgabe=print):
    """Richtet alles ein; gibt die Liste der erledigten Schritte zurück."""
    schritte = []
    pfad = db.db_pfad()
    if not os.path.exists(pfad):
        db.anlegen(pfad).close()
        schritte.append(f"Datenbank angelegt: {pfad}")
    con = db.verbinde(pfad)
    try:
        r = con.execute("SELECT id FROM projekt WHERE name = ?", (projekt,)).fetchone()
        if r:
            pid = r["id"]
        else:
            with db.schreiben(con):
                pid = db.einfuegen(con, "projekt", name=projekt, angelegt_utc=db.jetzt())
            schritte.append(f"Projekt „{projekt}“ angelegt")
        for kennung, rolle in [(lead, "lead")] + [(a, None) for a in agenten]:
            if not kennung:
                continue
            if not con.execute("SELECT 1 FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, kennung)).fetchone():
                kern.agent_neu(con, pid, kennung, rolle=rolle)
                schritte.append(f"Agent {kennung}" + (" (Lead)" if rolle else "") + " angelegt")
        if ordner:
            if not os.path.isdir(ordner):
                raise kern.AmwFehler(f"Projektordner {ordner} gibt es nicht")
            for a in agenten:
                steuerung.profil_setzen(con, pid, kern.ENTWICKLER, a, ordner=ordner, rechte=rechte, denkstufe=denkstufe or None,
                                        fernsteuerung=True,
                                        startsatz=f"Du bist {a}. Lies zuerst: python {einrichtung.WURZEL.replace(os.sep, '/')}/amw-cli.py"
                                                  f" lesen --von {a}")
            schritte.append(f"Profile für {', '.join(agenten)}: Ordner {ordner}, Rechte {rechte}")
            if hooks:
                aenderungen = einrichtung.agenten_ordner_einrichten(ordner)
                schritte.append(f"Projektordner eingerichtet ({', '.join(aenderungen) or 'war schon eingerichtet'})")
            if startskript:
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


def _ja(text, vorgabe=True, eingabe=input):
    antwort = eingabe(f"{text} [{'J/n' if vorgabe else 'j/N'}]: ").strip().lower()
    return vorgabe if not antwort else antwort.startswith(("j", "y"))


def interaktiv(eingabe=input, ausgabe=print):
    ausgabe("AMW einrichten – Enter übernimmt die Vorgabe in Klammern. Abbrechen mit Strg+C.\n")
    ausgabe(f"Datenbank: {db.db_pfad()}" + ("" if os.path.exists(db.db_pfad()) else " (wird angelegt)"))
    projekt = _frage("Name des Projekts", "Mein Projekt", eingabe)
    lead = _frage("Kennung des Lead-Agenten (Team-Lead; leer = keiner)", "TL", eingabe)
    agenten = [a.strip() for a in _frage("Kennungen der Agenten, mit Komma", "CC1,CC2", eingabe).split(",") if a.strip()]
    ordner = _frage("Projektordner, in dem die Agenten arbeiten (leer = später)", os.getcwd(), eingabe)
    rechte = _frage("Rechte der Agenten: vorgabe (fragen) | auto | umgehen (alles erlauben)", "vorgabe", eingabe)
    denkstufe = _frage("Denkstufe: low | medium | high | xhigh | max (leer = Vorgabe von Claude Code)", "", eingabe)
    hooks = bool(ordner) and _ja(f"Hooks und Statusline-Brücke in {ordner}\\.claude\\settings.local.json eintragen?", True, eingabe)
    dienst = _ja("Wächter als geplante Windows-Aufgabe einrichten (startet bei Anmeldung, weckt Agenten)?", True, eingabe)
    ausgabe("")
    schnell(projekt, lead or None, agenten, ordner or None, rechte, denkstufe, dienst, hooks=hooks, ausgabe=ausgabe)
    port = einstellungen.wert("port")
    ausgabe(f"""
Fertig. Nächste Schritte:
  1. Workbench öffnen: http://127.0.0.1:{port}/  (läuft, sobald der Wächter läuft: amw dienst status)
  2. Agenten starten: in der Workbench auf die Kachel › „Starten“ – oder {STARTSKRIPT} ausführen
  3. Optional: Benachrichtigungen aufs Handy (doc/anleitung-push.md), Online-Seite (doc/online.md),
     Planung mit Leitbild und Bögen (doc/anleitung-planung.md)""")
