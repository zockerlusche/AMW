"""Kommandozeile `amw` – einziger Schreibweg der Agenten (→ doc/architektur.md).

Wer bin ich: --von oder Umgebungsvariable AMW_AGENT. Welches Projekt: --projekt, AMW_PROJEKT, das einzige
vorhandene oder das, in dem es die Kennung gibt. Ausgabe immer UTF-8 (sonst brechen Umlaute in der Windows-Konsole ab).
"""
import argparse
import contextvars
import json
import os
import re
import sqlite3
import sys
import time
from datetime import datetime

from . import betrieb, db, kern, schirm, ueberwachung, wissen

# Woher ein Befehl kommt (Vermerke an KI-Ergebnissen): „cli“, in bruecke.ausfuehren() „bruecke“ – nie als Argument,
# sonst könnte jeder Agent „vom Handy“ behaupten
KANAL = contextvars.ContextVar("amw_kanal", default="cli")


def _projekt(con, a):
    try:
        return db.projekt_fuer(con, getattr(a, "projekt", None) or os.environ.get("AMW_PROJEKT"),
                               getattr(a, "von", None) or os.environ.get("AMW_AGENT"))
    except LookupError as e:
        raise kern.AmwFehler(str(e))


def _von(a):
    von = a.von or os.environ.get("AMW_AGENT")
    if not von:
        raise kern.AmwFehler("wer bist du? --von oder AMW_AGENT setzen")
    return von


# Optionen mit Agenten-Kennungen: frühere Kennungen (nach `agent umbenennen`) gelten weiter
KENNUNG_OPTIONEN = ("von", "agent", "pruefer", "verantwortlich", "fuer", "zustaendig")


def _eigene_kennung(con, a, pid):
    """Jeder schreibt nur als er selbst: Läuft der Befehl in einer Agenten-Sitzung (AMW_AGENT, setzt jedes Startskript),
    muss --von dazu passen (gleiche Kennung oder ihr früherer Name). Ausgenommen die Brücke (setzt --von selbst); ohne
    AMW_AGENT (Terminal des Entwicklers) gilt --von wie bisher."""
    sitzung = (os.environ.get("AMW_AGENT") or "").strip()
    von = getattr(a, "von", None)
    if not sitzung or not von or KANAL.get() == "bruecke":
        return
    if kern.kennung_heute(con, von, pid) != kern.kennung_heute(con, sitzung, pid):
        raise kern.AmwFehler(f"Du bist {sitzung} (AMW_AGENT dieser Sitzung) – --von {von} geht nicht: jeder schreibt nur als er"
                             " selbst. Lass --von weg oder setze deinen eigenen Namen.")


def _heutige_kennungen(con, a):
    if not getattr(a, "von", None) and os.environ.get("AMW_AGENT"):
        a.von = os.environ["AMW_AGENT"]
    felder = KENNUNG_OPTIONEN + (("an",) if a.f is cmd_posten else ()) + (("kennung",) if a.f is cmd_agent
                                                                          and a.aktion != "neu" else ())
    try:
        pid = _projekt(con, a)
    except (kern.AmwFehler, LookupError):
        pid = None                                   # meldet der Befehl selbst
    _eigene_kennung(con, a, pid)
    for k in felder:
        v = getattr(a, k, None)
        if isinstance(v, str) and v:
            setattr(a, k, ",".join(kern.kennung_heute(con, x.strip(), pid) for x in v.split(",")) if "," in v
                    else kern.kennung_heute(con, v, pid))


def _zeit(t):
    """UTC aus der Datenbank → Ortszeit des PCs, kurz (TT.MM. HH:MM) wie im alten Bus."""
    if not t:
        return ""
    try:
        return datetime.fromisoformat(t.replace("Z", "+00:00")).astimezone().strftime("%d.%m. %H:%M")
    except ValueError:
        return t[5:16].replace("T", " ")


# --- Befehle -------------------------------------------------------------------------------------

def cmd_init(a):
    name = a.projekt_init or a.projekt
    con = db.anlegen()
    if name:
        with db.schreiben(con):
            db.einfuegen(con, "projekt", name=name, angelegt_utc=db.jetzt())
    con.close()
    print(f"angelegt: {db.db_pfad()}" + (f" mit Projekt {name}" if name else ""))


def cmd_projekt(a, con):
    if a.aktion == "neu":
        if not (a.name or "").strip():
            raise kern.AmwFehler("Name fehlt: amw projekt neu <name> [--regeln-von <Projekt>]")
        quelle = db.projekt_id(con, a.regeln_von) if a.regeln_von else None
        if a.ordner and not os.path.isdir(a.ordner):
            raise kern.AmwFehler(f"Ordner {a.ordner} gibt es nicht – lege ihn zuerst an")
        with db.schreiben(con):
            pid = db.einfuegen(con, "projekt", name=a.name, beschreibung=a.beschreibung, angelegt_utc=db.jetzt())
        if a.ordner:
            print(f"Projektordner: {kern.projekt_ordner_setzen(con, pid, a.ordner)}")
        n = wissen.regeln_uebernehmen(con, pid, quelle) if quelle else 0
        print(f"Projekt {a.name} angelegt" + (f" – {n} Arbeitsregeln aus {a.regeln_von} übernommen (eigene Kopie)" if quelle
                                               else " – ohne Regeln (eigene: amw beschluss neu …, dann amw regel …)"))
    elif a.aktion == "einstellen":                    # Lead/Entwickler: amw projekt einstellen spec_frei=lead
        if not a.name or "=" not in a.name:
            raise kern.AmwFehler("amw projekt einstellen <schluessel>=<wert>, z. B. spec_frei=lead | agentenfragen=direkt |"
                                 " spec_vorlegen=alle | info_ablage_h=24")
        k, _, v = a.name.partition("=")
        e = kern.projekt_einstellen(con, _projekt(con, a), _von(a), **{k.strip(): v.strip()})
        print(f"{k.strip()} = {e.get(k.strip())}")
    elif a.aktion == "ordner":
        pid = db.projekt_id(con, a.name) if a.name else _projekt(con, a)
        if a.ordner:
            print(f"Projektordner: {kern.projekt_ordner_setzen(con, pid, a.ordner)}")
        else:
            print(kern.projekt_ordner(con, pid) or "kein Projektordner eingetragen – amw projekt ordner <name> --ordner <pfad>")
    else:
        for r in con.execute("SELECT id, name, beschreibung FROM projekt ORDER BY id"):
            print(f"{r['id']} {r['name']}  {r['beschreibung'] or ''}" + (f"  [{kern.projekt_ordner(con, r['id'])}]"
                                                                           if kern.projekt_ordner(con, r['id']) else ""))


def cmd_agent(a, con):
    pid = _projekt(con, a)
    if a.aktion == "umbenennen":
        if not (a.kennung and a.neu_kennung):
            raise kern.AmwFehler("amw agent umbenennen <alt> <neu> – vorher amw sichern")
        anzahl = kern.agent_umbenennen(con, pid, _von(a), a.kennung, a.neu_kennung)
        print(f"{a.kennung} heißt jetzt {a.neu_kennung} (der alte Name gilt weiter als Alias); geändert: "
              + (", ".join(f"{k} {n}" for k, n in sorted(anzahl.items())) or "nichts"))
        print("Profil, Tab-Titel und Fernsteuerungs-Name wirken beim nächsten Start; Startskripte neu schreiben.")
        return
    if a.aktion == "neu":
        weise = a.arbeitsweise or "terminal"
        kern.agent_neu(con, pid, a.kennung, a.rolle, a.zustaendig or a.grenzen, a.startbefehl, not a.ohne_rund,
                       fachgebiet=a.fachgebiet, arbeitsweise=weise)
        if a.nicht:
            kern.agent_einstellen(con, pid, _von(a), a.kennung, fasst_nicht_an=a.nicht)
        ordner = kern.projekt_ordner(con, pid) if weise != "chat" else None   # ein Chat hat keinen Arbeitsordner
        if ordner and os.path.isdir(ordner):              # Profil-Ordner = Projektordner (änderbar: amw agent profil)
            from . import steuerung
            steuerung.profil_setzen(con, pid, _von(a), a.kennung, ordner=ordner)
        print(f"Agent {a.kennung} angelegt" + (f" – arbeitet in {ordner}" if ordner and os.path.isdir(ordner) else ""))
        return
    if a.aktion in ("profil", "starten", "beenden", "startskript"):
        from . import steuerung
        if a.aktion == "startskript":
            text = steuerung.startskript(con, pid, [a.kennung] if a.kennung else None, alle=a.alle,
                                         abstand_s=steuerung.STARTSKRIPT_ABSTAND_S if a.abstand is None else a.abstand)
            if a.datei:
                with open(a.datei, "w", encoding="utf-8", newline="") as f:              # .bat: ohne BOM
                    f.write(text)
                print(f"geschrieben: {a.datei} – mit Doppelklick starten")
            else:
                print(text)
            return
        if not a.kennung:
            raise kern.AmwFehler(f"amw agent {a.aktion} <kennung>")
        if a.aktion == "starten":
            print(steuerung.starten(con, pid, a.kennung, neu=a.neu))
        elif a.aktion == "beenden":
            # Prozesse beendet nur der Mensch (Workbench am PC); ein Agent darf nur seine eigene Sitzung beenden
            if _von(a).casefold() != a.kennung.casefold():
                raise kern.AmwFehler(f"{_von(a)} darf {a.kennung} nicht beenden – andere Agenten beendet nur der Entwickler"
                                     " in der Workbench am PC (Kachel › Beenden)")
            print(steuerung.beenden(con, pid, a.kennung))
        else:
            schalter = lambda an, aus: True if an else False if aus else None
            aenderung = any(x is not None for x in (a.ordner, a.zusatz, a.denkstufe, a.modell, a.startsatz, a.rechte)) \
                or a.fernsteuerung or a.keine_fernsteuerung or a.neustart or a.kein_neustart
            p = steuerung.profil(con, pid, a.kennung) if not aenderung else steuerung.profil_setzen(con, pid, _von(a), a.kennung, ordner=a.ordner, zusatzordner=a.zusatz,
                                        denkstufe=a.denkstufe, modell=a.modell, startsatz=a.startsatz, rechte=a.rechte,
                                        fernsteuerung=schalter(a.fernsteuerung, a.keine_fernsteuerung),
                                        neustart_auto=schalter(a.neustart, a.kein_neustart))
            wer = {k: v for k, v in (("rolle", a.rolle), ("fachgebiet", a.fachgebiet), ("arbeitsweise", a.arbeitsweise),
                                     ("zustaendig", a.zustaendig if a.zustaendig is not None else a.grenzen), ("fasst_nicht_an", a.nicht)) if v is not None}
            if wer:                                          # dieselbe Prüfung wie im Zahnrad „Agenten“
                kern.agent_einstellen(con, pid, _von(a), a.kennung, **wer)
            z = kern.agent_zeile(con, pid, a.kennung)
            for k, v in {"lead": "ja" if z["rolle"] == "lead" else "nein", "fachgebiet": z["fachgebiet"], "arbeitsweise": z["arbeitsweise"] or "terminal",
                         "zustaendig": z["zustaendig"], "fasst_nicht_an": z["fasst_nicht_an"], **{k: v for k, v in p.items() if k != "kennung"}}.items():
                print(f"{k:<14} {v}")
        return
    for r in con.execute(
            "SELECT g.kennung, g.alias, CASE WHEN g.rolle = 'lead' THEN 'lead' ELSE g.fachgebiet END AS rolle, g.soll, s.zustand, s.letzter_puls_utc, s.taetigkeit, s.taetigkeit_utc,"
            " (SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
            "   WHERE e.agent = g.kennung AND n.projekt_id = g.projekt_id AND e.status != 'erledigt') AS offen"
            " FROM agent g LEFT JOIN sitzung s ON s.id = (SELECT max(id) FROM sitzung WHERE agent_id = g.id)"
            " WHERE g.projekt_id = ? AND g.entfernt_utc IS NULL ORDER BY g.id", (pid,)):
        print(f"{r['kennung']:<8} {r['rolle'] or '':<10} soll {r['soll']:<4} ist {r['zustand'] or 'nie gestartet':<14}"
              f" Puls {_zeit(r['letzter_puls_utc']) or '–':<12} offen {r['offen']}" + (f"  (früher {r['alias']})" if r["alias"] else "")
              + (f"\n         macht: {r['taetigkeit'][:90]} ({_alter(r['taetigkeit_utc'])})"
                 if r["taetigkeit"] and r["zustand"] in ("aktiv", "ruht") else ""))


def _alter(utc):
    """„seit 25 min“, „seit 3 h – veraltet?“ (ab 2 h), „Alter unbekannt“ (vor 1.10.0 gesetzt)."""
    if not utc:
        return "Alter unbekannt"
    s = kern.alter_s(utc)
    text = f"seit {int(s // 60)} min" if s < 3600 else f"seit {s / 3600:.0f} h" if s < 86400 else f"seit {s / 86400:.0f} T"
    return text + (" – veraltet?" if s >= kern.TAETIGKEIT_ALT_S else "")


def cmd_posten(a, con):
    pid = _projekt(con, a)
    text = a.text
    if a.text_datei:
        with open(a.text_datei, encoding="utf-8") as f:
            text = f.read()
    hinweise = []
    nid, namen = kern.posten(con, pid, _von(a), a.an, a.art, a.kurz, text, a.antwort_auf, a.aufgabe, hinweise, bis=a.bis, bezug=a.bezug)
    print(f"#{nid} an {', '.join(namen)}")
    for h in hinweise:
        print(h)


def nummer(text):
    """Nummer mit oder ohne Vorsilbe: „A1162“, „a1162“, „#16000“, „L12“, „F7“, „D5“, „B2“, „1162“ (argparse-Typ)."""
    m = re.fullmatch(r"\s*(?:#|[A-Za-z]{1,2})?(\d+)\s*", str(text))
    if not m:
        raise argparse.ArgumentTypeError(f"keine Nummer: {text!r} (z. B. 1162 oder A1162)")
    return int(m.group(1))


def windows_pfad(pfad):
    """Git-Bash-Pfad (/c/Users/…, /f/amw/…) → C:/Users/…, wenn es ihn so nicht gibt (unter Windows)."""
    if os.name != "nt" or not isinstance(pfad, str):
        return pfad
    m = re.fullmatch(r"/([A-Za-z])(/.*)?", pfad)
    if m and not os.path.exists(pfad):
        return f"{m.group(1).upper()}:{m.group(2) or '/'}"
    return pfad


PFAD_OPTIONEN = ("text_datei", "datei", "pfad", "ordner", "zusatz")


def _pfade_umsetzen(a):
    for k in PFAD_OPTIONEN:
        v = getattr(a, k, None)
        if isinstance(v, str):
            setattr(a, k, windows_pfad(v))
    if isinstance(getattr(a, "anhang", None), list):                  # frage neu --anhang A=bild.png
        a.anhang = [(x.split("=", 1)[0] + "=" + windows_pfad(x.split("=", 1)[1])) if "=" in x else windows_pfad(x)
                    for x in a.anhang]


def _lesezeile(con, r):
    fertig = ""
    if r["aufgabe_id"]:
        st = con.execute("SELECT status FROM aufgabe WHERE id = ?", (r["aufgabe_id"],)).fetchone()
        if st and st["status"] in ("fertig", "verworfen"):
            fertig = f" (A{r['aufgabe_id']} schon {st['status']})"
    stand = {"offen": "", "gelesen": " (gelesen)", "erledigt": " (erledigt)"}.get(r["status"], f" ({r['status']})")
    return f"#{r['id']} {_zeit(r['zeit_utc'])} {r['von']:<8} [{r['art']}]{stand}{fertig} {r['kurz'][:140]}"


def _listenzeile(x):
    gr = ", ".join(x.get("gruende") or [])
    return (f"{x['pos']:>3}. A{x['id']:<6} [{x['status']}]" + (" ◀ in Arbeit" if x["status"] == "laeuft" else "")
            + f" {x['titel'][:100]}" + (f"  ⇢ wartet auf {gr}" if gr else ""))


def cmd_termin(a, con):
    """Terminplaner: neu | liste | aendern | absagen | bereit | kurzliste."""
    from . import termine
    pid = _projekt(con, a)
    if a.aktion == "neu":
        if not a.am:
            raise kern.AmwFehler("termin neu --titel … --art test|frist|schirm|sonstig --am \"2026-11-06 18:00\"")
        tid = termine.neu(con, pid, _von(a), a.titel, a.art or "test", a.am, a.dauer, a.woechentlich, a.bis, a.vorlauf,
                          a.bogen, a.notiz)
        print(f"T{tid} angelegt")
        a.aktion = "liste"
    if a.aktion == "aendern":
        termine.aendern(con, pid, _von(a), a.id, titel=a.titel, am=a.am, dauer_min=a.dauer, bis_datum=a.bis,
                        vorlauf_h=a.vorlauf, bogen_id=a.bogen, notiz=a.notiz, woechentlich=True if a.woechentlich else None)
        print(f"T{a.id} geändert")
        return
    if a.aktion == "absagen":
        termine.absagen(con, pid, _von(a), a.id, a.am)
        print(f"T{a.id} abgesagt" + (f" (nur {a.am})" if a.am else ""))
        return
    if a.aktion == "bereit":
        nid = termine.bereit(con, pid, _von(a), a.id, a.text, a.am)
        print(f"Testbuild für T{a.id} gemeldet (#{nid} an den Entwickler, mit Kurzliste)")
        return
    if a.aktion == "kurzliste":
        print(termine.kurzliste(con, pid, a.id, a.am))
        return
    l = termine.vorkommen(con, pid, tage=a.tage)
    for v in l:
        print(f"T{v['termin_id']:<4} {termine.lokal(v['am_utc'])}  [{v['art']}] {v['titel']}"
              + (" (wöchentlich)" if v["woechentlich"] else "")
              + (f" · Testbuild fertig bis {termine.lokal(v['frist_utc'])}" if v.get("frist_utc") else "")
              + (f" · Meilenstein {v['bogen_id']}: {v['ampel']}" if v.get("ampel") else "")
              + (" · gemeldet" if v["bereit"] else ""))
    if not l:
        print(f"keine Termine in den nächsten {a.tage} Tagen")


def cmd_liste(a, con):
    """Arbeitsliste je Agent (B2429): zeigen, ordnen, schieben."""
    from . import arbeitsliste
    pid = _projekt(con, a)
    wer = (a.wer or "").strip()
    if wer.lower() == "ordnen":
        if len(a.rest) < 2:
            raise kern.AmwFehler("amw liste ordnen <Agent> A12 A15 …")
        ids = [nummer(x) for x in a.rest[1:]]
        l = arbeitsliste.ordnen(con, pid, _von(a), a.rest[0], ids)
    elif wer.lower() == "schieben":
        if len(a.rest) != 1:
            raise kern.AmwFehler("amw liste schieben A15 --vor A12 | --nach A12 | --pos N | --oben | --unten")
        l = arbeitsliste.schieben(con, pid, _von(a), nummer(a.rest[0]), a.vor, a.nach, a.pos, a.oben, a.unten)
    elif wer.lower() == "pool":
        p = arbeitsliste.pool(con, pid)
        for x in p:
            print(f"A{x['id']:<6} [{x['status']}] {x['agent'] or '–':<8} {x['titel'][:100]}")
        print(f"{len(p)} im Pool" if p else "Pool leer")
        return
    elif wer:
        l = arbeitsliste.liste(con, pid, kern.bearbeiter(con, pid, wer))
    else:
        for g in [{"kennung": kern.ENTWICKLER}] + con.execute("SELECT kennung FROM agent WHERE projekt_id = ? ORDER BY id",
                                                                (pid,)).fetchall():
            l = arbeitsliste.liste(con, pid, g["kennung"])
            if l:
                print(f"{g['kennung']} ({len(l)}):")
                for x in l:
                    print(_listenzeile(x))
                print()
        n = len(arbeitsliste.pool(con, pid))
        print(f"Pool: {n} (amw liste pool)")
        return
    for x in l:
        print(_listenzeile(x))
    if not l:
        print("Liste leer")


def _kanal(con, a):
    """Entwickler-Kanal: der Produktentwickler liest ohne --projekt alle Projekte."""
    return _von(a) == db.produkt_entwickler() and not getattr(a, "projekt", None)


def cmd_lesen(a, con):
    von = _von(a)
    kanal = _kanal(con, a)
    pid = None if kanal else _projekt(con, a)
    if a.id:                                           # eine oder mehrere ganze Nachrichten
        for i, nid in enumerate(a.id):
            n = kern.lesen(con, kern.projekt_der_nachricht(con, nid) if kanal else pid, von, nid)
            if i:
                print("\n" + "─" * 60)
            print(f"#{n['id']} {_zeit(n['zeit_utc'])} {n['von']} [{n['art']}]"
                  + (f" · Projekt {db.projekt_name(con, n['projekt_id'])}" if kanal else "")
                  + (f" Antwort auf #{n['antwort_auf']}" if n["antwort_auf"] else "")
                  + (f" · Bezug {kern.bezug_text(con, n['bezug'])}" if n["bezug"] else f" · A{n['aufgabe_id']}" if n["aufgabe_id"] else ""))
            print(n["kurz"])
            if n["text"]:
                print(n["text"])
        return
    if kanal and not a.verlauf:                        # Entwickler-Kanal: alle Projekte, mit Namen
        zeilen = kern.offene_aller_projekte(con, von, a.grenze, neueste_zuerst=a.neu)
        if a.neu:
            zeilen = [r for r in zeilen if r["status"] == "offen"]
        for r in zeilen:
            print(f"[{r['projekt']}] " + _lesezeile(con, r))
        print((f"{len(zeilen)} ungelesen" if a.neu else f"{len(zeilen)} offen") + " (alle Projekte)" if zeilen else "nichts offen")
        kern.als_gelesen(con, von, [r["id"] for r in zeilen if r["status"] == "offen"])   # gezeigt = gelesen (Stand für den Menschen)
        return
    if kanal:
        pid = _projekt(con, a)
    if a.verlauf:                                      # auch Gelesenes/Erledigtes: was kam zuletzt an mich?
        zeilen = con.execute(
            "SELECT n.id, n.zeit_utc, n.von, n.art, n.kurz, n.aufgabe_id, e.status FROM empfang e JOIN nachricht n"
            " ON n.id = e.nachricht_id WHERE n.projekt_id = ? AND e.agent = ? ORDER BY n.id DESC LIMIT ?",
            (pid, von, a.grenze)).fetchall()
        for r in zeilen:
            print(_lesezeile(con, r))
        print(f"{len(zeilen)} Nachrichten an {von}, neueste zuerst")
        return
    zeilen = kern.offene(con, pid, von, a.grenze, neueste_zuerst=a.neu)
    if a.neu:
        zeilen = [r for r in zeilen if r["status"] == "offen"]
    for r in zeilen:
        print(_lesezeile(con, r))
    print((f"{len(zeilen)} ungelesen" if a.neu else f"{len(zeilen)} offen") if zeilen else "nichts offen")
    kern.als_gelesen(con, von, [r["id"] for r in zeilen if r["status"] == "offen"])       # gezeigt = gelesen (Stand für den Menschen)


def cmd_erledigt(a, con):
    pid = _projekt(con, a)
    if a.info:
        vor = _datum(a.vor) if a.vor else None
        print(f"{kern.erledigt_infos(con, pid, _von(a), vor)} info erledigt" + (f" (vor {a.vor})" if vor else ""))
        if not a.ids:
            return
    if not a.ids:
        raise kern.AmwFehler("welche Nachrichten? amw erledigt 12 13 (oder --info für alle info-Nachrichten)")
    if a.fuer:                                         # Lead schließt veraltete Meldungen an den Entwickler (mit Grund)
        print(f"{kern.erledigt_fuer(con, pid, _von(a), a.fuer, a.ids, a.bemerkung)} für {a.fuer} geschlossen")
        return
    if _kanal(con, a):                                 # Entwickler-Kanal: jede Nachricht in ihrem Projekt
        n = sum(kern.erledigt(con, kern.projekt_der_nachricht(con, nid), _von(a), [nid], a.bemerkung) for nid in a.ids)
    else:
        n = kern.erledigt(con, pid, _von(a), a.ids, a.bemerkung)
    print(f"{n} erledigt")


def _datum(text):
    """04.11. / 04.11.2026 / 2026-11-04 → 2026-11-04 (Beginn des Tages, UTC)."""
    from datetime import date
    m = re.fullmatch(r"(\d{1,2})\.(\d{1,2})\.(\d{4})?", text.strip())
    if m:
        return date(int(m.group(3) or date.today().year), int(m.group(2)), int(m.group(1))).isoformat()
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text.strip()):
        return text.strip()
    raise kern.AmwFehler(f"Datum „{text}“ nicht erkannt – 04.11. oder 2026-11-04")


def _schritt_werte(a):
    """Planungs-Optionen von aufgabe neu/aendern (None = nicht angegeben)."""
    nr = lambda t: [int(x.strip().lstrip("Aa")) for x in t.split(",") if x.strip()] if t else None
    return {"bogen_id": a.bogen, "kriterien": a.kriterium, "schaetzung_h": a.schaetzung, "komplexitaet": a.komplexitaet,
            "verantwortlich": a.verantwortlich, "pruefbefehl": a.pruefbefehl, "dateibereich": a.dateien,
            "anforderungen": a.anforderungen, "agent": a.agent, "auftrag": a.auftrag, "pruefer": a.pruefer}, nr(a.nach)


def _ohne(a):
    return [int(x.strip().lstrip("Aa")) for x in (a.ohne_vorgaenger or "").split(",") if x.strip()]


def cmd_aufgabe(a, con):
    pid = _projekt(con, a)
    from . import planung
    if a.aktion == "dazwischen":                     # nur der Mensch; der Lead schlägt vor (Ja/Nein-Frage an den Menschen)
        from . import arbeitsliste
        if not a.id:
            raise kern.AmwFehler("amw aufgabe dazwischen <nr> --grund …")
        art, nr = arbeitsliste.dazwischen(con, pid, _von(a), a.id, a.grund)
        print(f"Frage F{nr} an den Menschen gestellt: A{a.id} dazwischenschieben? – „Ja“ führt es aus" if art == "frage"
              else f"A{a.id} kommt jetzt dran" + (f"; A{nr} wartet und kommt danach wieder dran" if nr else ""))
        return
    if a.aktion == "neu":
        werte, nach = _schritt_werte(a)
        if any(v is not None for k, v in werte.items() if k not in ("agent", "auftrag", "pruefer")) or nach:
            aid = planung.schritt_setzen(con, pid, _von(a), titel=a.titel, nach=nach, rang=a.rang, **werte)
        else:
            aid = kern.aufgabe_neu(con, pid, _von(a), a.titel, a.agent, a.auftrag, a.rang, a.pruefer, sofort=a.sofort)
        if a.pool:
            wissen.einstufen(con, pid, _von(a), aid, "pool")
        z = con.execute("SELECT agent, einstufung FROM aufgabe WHERE id = ?", (aid,)).fetchone()
        if z["einstufung"] == "pool" and z["agent"] and not a.pool:   # der Agent hat gerade ein Stück in Arbeit
            from . import arbeitsliste
            x = arbeitsliste.laufend(con, pid, z["agent"])
            print(f"A{aid} angelegt – steht im Eingang, weil {z['agent']} gerade an A{x['id'] if x else '?'} arbeitet."
                  f" Einplanen: amw liste ordnen {z['agent']} A{aid} … (landet hinter dem laufenden Stück);"
                  " sofort hinter das laufende Stück: beim Anlegen --sofort")
        else:
            print(f"A{aid} angelegt" + (" (Eingang – der Lead plant ein: amw liste ordnen <Agent> …)" if a.pool else ""))
    elif a.aktion == "aendern":
        werte, nach = _schritt_werte(a)
        werte["zusammenfassung"] = a.zusammenfassung              # auch nachträglich (Plan-Check)
        if any(v is not None for v in werte.values()) or nach or a.titel:
            planung.schritt_setzen(con, pid, _von(a), aid=a.id, titel=a.titel, nach=nach, **werte)
        if _ohne(a):
            planung.abhaengigkeit_setzen(con, pid, _von(a), a.id, _ohne(a), entfernen=True)
        if a.federfuehrend is not None:
            ff = kern.federfuehrung_setzen(con, pid, _von(a), "aufgabe", a.id, a.federfuehrend)
            print(f"A{a.id}: federführend {ff or '– (Meilenstein bzw. Lead)'}")
        print(f"A{a.id} geändert")
    elif a.aktion == "kriterium":
        liste = planung.kriterium(con, pid, _von(a), a.id, a.nr, not a.nein)
        for i, k in enumerate(liste, 1):
            print(f"  {i}. [{'x' if k.get('erfuellt') else ' '}] {k['text']}")
    elif a.aktion == "plan":
        planung.plan_vorlegen(con, pid, _von(a), a.id, a.text or "")
        print(f"Plan für A{a.id} vorgelegt – umsetzen erst nach Freigabe")
    elif a.aktion == "planfrei":
        planung.plan_entscheiden(con, pid, _von(a), a.id, not a.zurueck, a.kommentar)
        print(f"Plan A{a.id} " + ("zurück" if a.zurueck else "freigegeben"))
    elif a.aktion == "liste":
        from . import wartegrund
        for r in kern.aufgaben(con, pid, a.agent, a.alle):
            gruende = ", ".join(g["bezug"] for g in wartegrund.offene(con, r["id"]))
            print(f"A{r['id']:<5} {r['agent'] or '–':<8} [{r['status']}/{r['einstufung']}] {r['titel'][:110]}"
                  + (f"  ⇢ {gruende}" if gruende else "") + (f"  ⇢ {r['wartet_auf']}" if r["wartet_auf"] else ""))
    elif a.aktion == "nachtrag":
        if not a.id:
            raise kern.AmwFehler("amw aufgabe nachtrag <nr> --titel … [--auftrag …] [--agent …]")
        aid = kern.aufgabe_nachtrag(con, pid, _von(a), a.id, a.titel, a.auftrag, a.agent)
        print(f"A{aid} angelegt (Nachtrag zu A{a.id}) – Nachrichten und Läufe dazu mit --aufgabe {aid}")
    elif a.aktion == "zeige":
        r = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (a.id, pid)).fetchone()
        if not r:
            raise kern.AmwFehler(f"A{a.id} gibt es nicht")
        if getattr(a, "kurz", False):
            from . import wartegrund
            offen = [g["bezug"] for g in wartegrund.offene(con, a.id)]
            print(f"A{r['id']} [{r['status']}] {r['agent'] or '–'} · {r['titel']}"
                  + (f" · wartet auf {', '.join(offen)}" if offen else "")
                  + (f" · {r['wartet_auf']}" if r["wartet_auf"] and r["status"] in ("wartet", "blockiert") else ""))
            return
        for k in r.keys():
            if r[k] not in (None, "") and k not in ("uid", "herkunft"):
                print(f"{k}: {r[k]}")
        for g in con.execute("SELECT * FROM wartegrund WHERE aufgabe_id = ? ORDER BY id", (a.id,)):
            print(f"wartegrund: {g['bezug']} (seit {_zeit(g['angelegt_utc'])}, {g['angelegt_von']})"
                  + (f" – erledigt {_zeit(g['erledigt_utc'])}: {g['erledigt_durch']}" if g["erledigt_utc"] else " – offen"))
    elif a.aktion in ("parken", "aktiv", "keine_prio", "pool"):
        if not a.id:
            raise kern.AmwFehler("Aufgaben-Nummer fehlt")
        wissen.einstufen(con, pid, _von(a), a.id, "geparkt" if a.aktion == "parken" else a.aktion)
        print(f"A{a.id} → {'geparkt' if a.aktion == 'parken' else a.aktion}")
    else:
        if not a.id:
            raise kern.AmwFehler("Aufgaben-Nummer fehlt")
        if (a.auf or a.erledigt) and a.aktion not in ("wartet", "blockiert"):
            raise kern.AmwFehler("--auf/--erledigt gibt es nur bei aufgabe wartet|blockiert")
        hinweise = []
        neu = kern.aufgabe_status(con, pid, _von(a), a.id, a.aktion, a.beleg, a.wartet_auf, a.bemerkung, a.zusammenfassung,
                                  a.auf, a.erledigt, hinweise, hinweis=a.hinweis, gruppe=a.gruppe)
        from . import wartegrund
        offen = [g["bezug"] for g in wartegrund.offene(con, a.id)]
        print(f"A{a.id} → {neu}" + (f" · wartet auf {', '.join(offen)}" if offen and neu in ("wartet", "blockiert") else ""))
        for h in hinweise:
            print(h)


def cmd_leitbild(a, con):
    from . import planung
    pid = _projekt(con, a)
    if a.aktion == "setzen":
        planung.leitbild_setzen(con, pid, _von(a), a.ziel, a.kennzahl, a.nicht_ziel, a.prinzip, a.dod)
    lb = planung.leitbild(con, pid)
    print(f"Ziel: {lb['ziel'] or '–'}")
    for k, name in (("kennzahlen", "Kennzahl"), ("nicht_ziele", "Nicht-Ziel"), ("dod", "Definition of Done")):
        for x in lb[k]:
            print(f"{name}: {x}")
    for p in lb["prinzipien"]:
        print(f"Prinzip: {p['text']}" + (f"  (Prüffrage: {p['pruefung']})" if p.get("pruefung") else ""))


def cmd_bogen(a, con):
    from . import planung
    pid = _projekt(con, a)
    if a.aktion == "neu":
        bid = planung.bogen_neu(con, pid, _von(a), a.titel, a.ziel, a.abnahme, a.zieldatum, a.nr)
        print(f"Meilenstein {bid} angelegt – Spezifikation: amw spec schreiben {bid} anforderungen --datei …")
    elif a.aktion == "aendern":
        planung.bogen_aendern(con, pid, _von(a), a.id, a.titel, a.ziel, a.abnahme, a.zieldatum, a.nr, a.grund)
        if a.federfuehrend is not None:
            ff = kern.federfuehrung_setzen(con, pid, _von(a), "bogen", a.id, a.federfuehrend)
            print(f"Meilenstein {a.id}: federführend {ff or '– (Lead)'}")
        print(f"Meilenstein {a.id} geändert")
    elif a.aktion == "status":
        planung.bogen_status(con, pid, _von(a), a.id, a.wert, a.erzwingen)
        print(f"Meilenstein {a.id} → {a.wert}")
    elif a.aktion == "zeigen":
        b = next((x for x in planung.boegen(con, pid) if x["id"] == a.id), None)
        if not b:
            raise kern.AmwFehler(f"Meilenstein {a.id} gibt es nicht")
        print(f"Meilenstein {b['id']} [{b['status']}] {b['titel']} · Ziel: {b['ziel'] or '–'} · Abnahme: {b['abnahme'] or '–'}"
              f" · Zieldatum {b['zieldatum'] or '–'} (Baseline {b['baseline_datum'] or '–'})"
              + (f" · federführend {b['federfuehrend']}" if b.get("federfuehrend") else ""))
        stand = {"entwurf": "in Arbeit", "zurueck": "zurück"}
        print("Spezifikation: " + ", ".join(f"{t} {stand.get(b['spec'].get(t), b['spec'].get(t) or '–')}" for t in planung.TEILE))
        stufe = planung.wellen(con, [r[0] for r in con.execute("SELECT id FROM aufgabe WHERE bogen_id = ?", (a.id,))])
        for r in con.execute("SELECT * FROM aufgabe WHERE bogen_id = ? ORDER BY rang, id", (a.id,)):
            print(f"  Stufe {stufe.get(r['id'], 1)}  A{r['id']:<5} {r['agent'] or '–':<10} [{r['status']}] {r['titel'][:90]}"
                  + (f"  ← {', '.join('A' + str(v) for v in planung.vorgaenger(con, r['id']))}" if planung.vorgaenger(con, r["id"]) else ""))
    else:
        prog = planung.prognose(con, pid, laeufe=300)
        for b in planung.boegen(con, pid):
            p = prog["boegen"].get(b["id"], {})
            print(f"Meilenstein {b['id']:<3} [{b['status']:<9}] {b['fertig']}/{b['gesamt'] - b['verworfen']} fertig"
                  + (f", {b['blockiert']} blockiert" if b["blockiert"] else "")
                  + (f" · Ziel {b['zieldatum']}" if b["zieldatum"] else "")
                  + (f" · Prognose {p['p50']}/{p['p85']} ({p['ampel'] or '–'})" if p else "") + f"  {b['titel']}")


def cmd_spec(a, con):
    from . import planung
    pid = _projekt(con, a)
    if a.aktion == "schreiben":
        text = a.text
        if a.datei:
            with open(a.datei, encoding="utf-8") as f:
                text = f.read()
        if not text:
            raise kern.AmwFehler("--text oder --datei")
        print(f"Meilenstein {a.bogen} {a.teil}: Version {planung.spec_schreiben(con, pid, _von(a), a.bogen, a.teil, text)} (Entwurf)")
    elif a.aktion == "vorlegen":
        fragen = planung.spec_vorlegen(con, pid, _von(a), a.bogen, a.teil)
        print(f"Meilenstein {a.bogen} {a.teil} vorgelegt" + (f" – Klärungsfragen: {', '.join('F' + str(f) for f in fragen)}" if fragen else ""))
    elif a.aktion in ("frei", "zurueck"):
        planung.spec_entscheiden(con, pid, _von(a), a.bogen, a.teil, a.aktion == "frei", a.kommentar)
        print(f"Meilenstein {a.bogen} {a.teil}: {a.aktion}")
    else:
        for t in ([a.teil] if a.teil else planung.TEILE):
            s = planung.spec(con, a.bogen, t)
            print(f"== {t} [{s['status']}, v{s['version']}]" + (f" Kommentar: {s['kommentar']}" if s["kommentar"] else ""))
            print(s["text"] or "(leer)")


def cmd_schritt(a, con):
    from . import planung
    pid = _projekt(con, a)
    s = planung.naechster(con, pid, _von(a), nehmen=a.nehmen)
    if not s:
        print("kein bereiter Schritt – alles vergeben, blockiert oder kein aktiver Meilenstein")
        return
    print(f"A{s['id']} [{s.get('status')}] {s['titel']}" + (f" (Meilenstein {s['bogen_id']})" if s.get("bogen_id") else ""))
    for k in planung._json(s.get("kriterien"), []):
        print(f"  Kriterium: {k['text']}")
    for k in ("pruefbefehl", "dateibereich", "hinweis"):
        if s.get(k):
            print(f"  {k}: {s[k]}")
    if not a.nehmen:
        print(f"  übernehmen: amw schritt naechster --nehmen --von {_von(a)}")


def cmd_risiko(a, con):
    from . import planung
    pid = _projekt(con, a)
    if a.aktion in ("neu", "setzen"):
        rid = planung.risiko_setzen(con, pid, _von(a), None if a.aktion == "neu" else a.id, titel=a.titel, ursache=a.ursache,
                                    wirkung=a.wirkung, wahrscheinlichkeit=a.w, auswirkung=a.a, strategie=a.strategie,
                                    massnahme=a.massnahme, verantwortlich=a.verantwortlich, ausloeser=a.ausloeser,
                                    status=a.status, bogen_id=a.bogen)
        print(f"Risiko {rid} gespeichert")
    else:
        for r in planung.risiken(con, pid):
            print(f"R{r['id']:<4} [{r['status']}] W{r['wahrscheinlichkeit']}×A{r['auswirkung']}={r['wert']:<3} {r['titel']}"
                  f" · {r['strategie'] or '–'}: {r['massnahme'] or '–'} · {r['verantwortlich'] or '–'}")


def cmd_rueckblick(a, con):
    from . import verlauf
    pid = _projekt(con, a)
    neu = [(art, getattr(a, art)) for art in verlauf.ARTEN if getattr(a, art)]
    for art, text in neu:
        verlauf.rueckblick_neu(con, pid, _von(a), a.bogen, art, text)
    if a.uebernehmen:
        print(f"→ {a.als} {verlauf.massnahme_uebernehmen(con, pid, _von(a), a.uebernehmen, a.als, a.agent)}")
    for r in verlauf.rueckblicke(con, pid, a.bogen):
        print(f"{r['id']:<4} {r['art']:<10} {r['text']}  ({r['von']}"
              + (f", → A{r['aufgabe_id']}" if r["aufgabe_id"] else "") + (f", → B{r['beschluss_id']}" if r["beschluss_id"] else "") + ")")


def cmd_verlauf(a, con):
    import datetime
    from . import verlauf
    pid = _projekt(con, a)
    ab = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=a.stunden)).strftime("%Y-%m-%dT%H:%M:%SZ")
    if a.zusammenfassung:
        print(verlauf.kurztext(verlauf.zusammenfassung(con, pid, ab)))
        return
    for x in reversed(verlauf.verlauf(con, pid, ab, agent=a.agent, arten=a.art, grenze=a.grenze)):
        print(f"{_zeit(x['zeit'])}  {x['art']:<9} {x['wer'] or '–':<10} {x['ref']:<7} {x['text'][:110]}"
              + (f"  [{x['zusatz']}]" if x["zusatz"] and x["art"] != "nachricht" else ""))


def cmd_plan(a, con):
    from . import planung
    pid = _projekt(con, a)
    if a.aktion == "pruefen":
        alle = planung.pruefen(con, pid, mit_akzeptierten=True)
        liste = [x for x in alle if not x["akzeptiert"]]
        zahl = {s: sum(x["stufe"] == s for x in liste) for s in planung.STUFEN}
        print(f"Plan-Check: {zahl['fehler']} Fehler · {zahl['warnung']} Warnung(en) · {zahl['hinweis']} Hinweis(e)"
              + (f" · {len(alle) - len(liste)} bewusst akzeptiert" if len(alle) > len(liste) else ""))
        if not liste:
            print("keine offenen Lücken")
        titel = {b["id"]: b["titel"] for b in planung.boegen(con, pid)}
        lead = kern.lead(con, pid) or "Lead"
        gruppe = None
        for x in sorted(liste, key=lambda x: (x["gruppe"] != "projekt", x["bogen_id"] or 0, planung.STUFEN.index(x["stufe"]))):
            if x["gruppe"] != gruppe:
                gruppe = x["gruppe"]
                print("\n" + (f"Meilenstein {x['bogen_id']} „{titel.get(x['bogen_id'], '')}“" if gruppe.startswith("bogen:")
                              else "Risiken" if gruppe == "risiken" else "Projekt"))
            print(f"  {x['stufe'].upper():<8} {x['text']}   [{x['schluessel']}]")
            if not a.kurz:
                _, wer, _, texte = planung.CHECKS[x["code"]]
                _, bedeutung, tun = texte["de"]
                print(f"           Bedeutet: {bedeutung.format(**x['werte'])}")
                print(f"           Tun ({'du' if wer == 'du' else lead}): {tun.format(**x['werte'])}")
        if liste and not a.kurz:
            print("\nBewusst so lassen (Warnung/Hinweis): amw plan akzeptieren <schlüssel> --grund …")
    elif a.aktion == "akzeptieren":
        if not a.schluessel:
            raise kern.AmwFehler("Schlüssel fehlt (steht in eckigen Klammern hinter dem Befund)")
        planung.check_akzeptieren(con, pid, _von(a), a.schluessel, a.grund)
        print(f"akzeptiert: {a.schluessel}")
    elif a.aktion == "wieder":
        if not a.schluessel:
            raise kern.AmwFehler("Schlüssel fehlt")
        planung.check_wieder(con, pid, _von(a), a.schluessel)
        print(f"zählt wieder: {a.schluessel}")
    elif a.aktion == "status":
        s = planung.status(con, pid)
        for k in ("termin", "risiko", "qualitaet"):
            print(f"{k:<10} {s[k] or '–':<6} {s['begruendung'][k]}")
    else:
        prog = planung.prognose(con, pid)
        for aid, p in sorted(prog["schritte"].items(), key=lambda x: x[1]["p50"]):
            print(f"A{aid:<5} {p['bearbeiter'] or 'frei':<10} P50 {p['p50']}  P85 {p['p85']}")
        for bid, p in prog["boegen"].items():
            print(f"Meilenstein {bid}: P50 {p['p50']} P85 {p['p85']} Ampel {p['ampel'] or '–'}")


def cmd_frage(a, con):
    pid = _projekt(con, a)
    if a.aktion == "neu":
        if not (a.an and (a.kurz or "").strip()):
            raise kern.AmwFehler("frage neu braucht --an entwickler|tl und --kurz \"die Frage in einem Satz\""
                                 " (--text gibt es nur bei antworten/nachtrag)")
        optionen = []
        for o in a.option or []:
            kenn, gleich, text = o.partition("=")
            m = None if gleich and text.strip() else re.match(r"\s*([^\s=:)]{1,12})\s*[:)]\s+(.+)", o, re.S)
            if m:                                   # „V0: Text“ statt „V0=Text“ – gemeint ist dasselbe
                kenn, text = m.groups()
            optionen.append((kenn.strip(), text.strip()))
        from . import dokumente
        anhaenge = dokumente.anhaenge_pruefen(con, pid, a.anhang or [], [k for k, _ in optionen])   # vor dem Anlegen
        fid = kern.frage_neu(con, pid, _von(a), a.an, a.kurz, optionen, a.empfehlung, a.grund, a.worum,
                             a.fundstellen, a.aufgabe, a.blockiert, geprueft=a.geprueft)
        if a.an == "tl":                            # an den Lead: Treffer nur zeigen
            liste = wissen.treffer(con, pid, f"{a.kurz} {a.worum or ''}")
            if liste:
                print("Vielleicht schon entschieden:\n" + wissen.treffer_text(liste))
        zusatz = dokumente.anhaenge_setzen(con, pid, _von(a), fid, anhaenge)
        print(f"F{fid} angelegt" + (" – Varianten: " + ", ".join(f"{k}=D{d}" for k, d in zusatz.items()) if zusatz else ""))
        if a.an == "entwickler" and con.execute("SELECT an FROM frage WHERE id = ?", (fid,)).fetchone()[0] == "tl":
            print(f"→ geht zuerst an den Lead {kern.lead(con, pid)} (Projekt-Regel: Agentenfragen über den Lead) – er beantwortet"
                  " sie selbst oder leitet sie an den Entwickler weiter")
    elif a.aktion == "weiterleiten":
        if not a.id:
            raise kern.AmwFehler("frage weiterleiten <nr> [--text \"Notiz für den Entwickler\"]")
        kern.frage_weiterleiten(con, pid, _von(a), a.id, a.text)
        print(f"F{a.id} an den Entwickler weitergeleitet")
    elif a.aktion in ("parken", "aufnehmen"):
        if not a.id:
            raise kern.AmwFehler(f"frage {a.aktion} <nr> [--grund \"…\"]")
        print(f"F{a.id} → {kern.frage_parken(con, pid, _von(a), a.id, a.aktion == 'parken', a.grund)}")
    elif a.aktion == "liste":
        if a.geparkt:
            for r in kern.offene_fragen(con, pid, a.an, geparkt=True):
                print(f"F{r['id']} an {r['an']} von {r['von']}: {r['kurz']}  (geparkt {_zeit(r['geparkt_utc'])} von {r['geparkt_von']})")
            return
        for r in kern.offene_fragen(con, pid, a.an):
            opt = " · ".join(f"{o['kenn']}) {o['text']}" for o in json.loads(r["optionen"]))
            print(f"F{r['id']} an {r['an']} von {r['von']}{' BLOCKIERT' if r['blockiert'] else ''}: {r['kurz']}"
                  + (f"\n   {opt}" if opt else "") + (f"  → Empfehlung {r['empfehlung']}" if r["empfehlung"] else ""))
    elif a.aktion == "nachtrag":                    # Fragesteller: Antwort auf eine Rückfrage oder Ergänzung
        if not a.id or not a.text:
            raise kern.AmwFehler("frage nachtrag <nr> --text \"…\"")
        print(f"Nachtrag zu F{a.id} – Nachricht #{kern.frage_nachtrag(con, pid, _von(a), a.id, a.text)}")
    elif a.aktion == "verlauf":
        if not a.id:
            raise kern.AmwFehler("frage verlauf <nr>")
        f = con.execute("SELECT von, zeit_utc, kurz, status, geparkt_utc FROM frage WHERE id = ? AND projekt_id = ?",
                        (a.id, pid)).fetchone()
        if not f:
            raise kern.AmwFehler(f"F{a.id} gibt es nicht")
        status = f"geparkt seit {_zeit(f['geparkt_utc'])}" if f["geparkt_utc"] else f["status"]
        print(f"F{a.id} ({status}) {_zeit(f['zeit_utc'])} {f['von']}: {f['kurz']}")
        for v in con.execute("SELECT zeit_utc, von, art, text FROM frage_verlauf WHERE frage_id = ? ORDER BY id", (a.id,)):
            print(f"  {_zeit(v['zeit_utc'])} {v['von']} [{v['art']}]: {v['text']}")
    elif a.aktion == "antworten":
        art, wert = ("option", a.option[0]) if a.option else ("rueckfrage", a.rueckfrage) if a.rueckfrage else ("text", a.text)
        if not wert:
            raise kern.AmwFehler("--option, --text oder --rueckfrage angeben")
        # kein stilles „Entwickler“ als Absender: der Entwickler antwortet in der Workbench, wer hier antwortet, nennt sich
        print(f"F{a.id} → {kern.frage_antworten(con, pid, a.id, art, wert, 'cli', _von(a))}")


def cmd_halt(a, con):
    sid = kern.halt(con, _projekt(con, a), _von(a), a.fuer, a.text)
    print(f"Halt #{sid} für {a.fuer} gesetzt; STOPP verschickt")


def cmd_weiter(a, con):
    n = kern.weiter(con, _projekt(con, a), _von(a), a.fuer)
    print(f"{n} Halt aufgehoben" if n else "kein Halt aktiv")


def cmd_taetigkeit(a, con):
    kern.taetigkeit(con, _projekt(con, a), _von(a), " ".join(a.text), a.aufgabe)
    print("Tätigkeit gesetzt" if a.text else "Tätigkeit gelöscht")


def cmd_kontext(a, con):
    print(kern.kontext(con, _projekt(con, a), a.agent or _von(a)))


def cmd_suche(a, con):
    """Volltext über Aufgaben, Beschlüsse, Fragen, Wortlaut, Nachrichten, Dokumente – kurze Zeilen, dann gezielt `amw zeige`."""
    from . import workbench
    pid = _projekt(con, a)
    such = " ".join(a.text).strip()
    if len(such) < 2:
        raise kern.AmwFehler("amw suche <Stichwort> (mindestens 2 Zeichen)")
    treffer = workbench.daten_suche(con, pid, {"q": [such]})
    if a.art:
        treffer = [t for t in treffer if t["art"] in a.art]
    treffer.sort(key=lambda t: t["zeit"] or "", reverse=True)
    for t in treffer[:a.grenze]:
        titel = " ".join((t["titel"] or "").split())
        print(f"{t['ref']:<7} {_zeit(t['zeit']) or '':<12} [{t['zusatz'] or ''}] {titel[:120]}")
    print(f"{len(treffer)} Treffer" + (f", die neuesten {a.grenze}" if len(treffer) > a.grenze else "")
          + (" – ganz lesen: amw zeige <B…|F…|A…|W…|D…|KR…|PR…|Nachricht-Nr. ohne #>" if treffer else ""))
    if a.wissen:                                        # dieselbe Prüfung wie vor einer Frage an den Entwickler
        liste = wissen.treffer(con, pid, such)
        print("Passende Beschlüsse/Fragen/Regeln:\n" + (wissen.treffer_text(liste) if liste else "  keine"))


def cmd_zeige(a, con):
    """Ein Eintrag ganz, nach seiner Nummer: B12 Beschluss, F7 Frage, A1201 Aufgabe, W3 Wortlaut, 16000 (oder „#16000“ in Anführungszeichen) Nachricht,
    D5 Dokument (Angaben), KR3/PR42 Regel."""
    pid = _projekt(con, a)
    for ref in a.refs:
        m = re.fullmatch(r"\s*(#|[A-Za-z]{1,2})?\s*(\d+)\s*", ref)
        if not m:
            raise kern.AmwFehler(f"„{ref}“: B<nr>, F<nr>, A<nr>, W<nr>, #<nr>, D<nr>, KR<nr> oder PR<nr>")
        art, nr = (m.group(1) or "#").upper(), int(m.group(2))
        if art == "B":
            r = con.execute("SELECT * FROM beschluss WHERE id = ? AND projekt_id = ?", (nr, pid)).fetchone()
            if r:
                print(f"B{nr} [{r['status']}] {_zeit(r['zeit_utc'])} {r['stichwort']}" + (f" (Thema {r['thema']})" if r["thema"] else ""))
                print(r["regel"])
                print(f"Quelle: {r['quelle']}" + (f" · ersetzt durch B{r['ersetzt_durch']}" if r["ersetzt_durch"] else "")
                      + (f" · Aufgaben: {r['aufgabe_ids']}" if r["aufgabe_ids"] else ""))
        elif art == "F":
            r = con.execute("SELECT * FROM frage WHERE id = ? AND projekt_id = ?", (nr, pid)).fetchone()
            if r:
                print(f"F{nr} [{r['status']}] {_zeit(r['zeit_utc'])} {r['von']} an {r['an']}: {r['kurz']}")
                for o in json.loads(r["optionen"] or "[]"):
                    print(f"  {o['kenn']}) {o['text']}" + ("  ← Empfehlung" if o["kenn"] == r["empfehlung"] else ""))
                for k in ("worum", "grund", "geprueft"):
                    if r[k]:
                        print(f"{k}: {r[k]}")
                if r["antwort"]:
                    print(f"Antwort ({_zeit(r['antwort_utc'])}, {r['antwort_art']}): {r['antwort']}")
        elif art == "A":
            a.aktion, a.id = "zeige", nr
            cmd_aufgabe(a, con)
            continue
        elif art == "W":
            r = con.execute("SELECT * FROM wortlaut WHERE id = ? AND projekt_id = ?", (nr, pid)).fetchone()
            if r:
                print(f"W{nr} {_zeit(r['zeit_utc'])} ({r['kanal']}): {r['text']}" + (f"\n{r['bemerkung']}" if r["bemerkung"] else ""))
        elif art == "#":
            r = con.execute("SELECT * FROM nachricht WHERE id = ? AND projekt_id = ?", (nr, pid)).fetchone()
            if r:
                an = ", ".join(x[0] for x in con.execute("SELECT agent FROM empfang WHERE nachricht_id = ?", (nr,)))
                print(f"#{nr} {_zeit(r['zeit_utc'])} {r['von']} → {an} [{r['art']}]" + (f" · A{r['aufgabe_id']}" if r["aufgabe_id"] else ""))
                print(r["kurz"] + (f"\n{r['text']}" if r["text"] else ""))
        elif art == "D":
            r = con.execute("SELECT * FROM dokument WHERE id = ? AND projekt_id = ?", (nr, pid)).fetchone()
            if r:
                print(f"D{nr} [{r['status']}] {r['art']} {r['titel']} – Inhalt: amw dokument zeige {nr}")
        elif art in ("KR", "PR"):
            r = con.execute("SELECT * FROM regel WHERE ebene = ? AND nr = ? AND projekt_id = ?",
                            ("arbeit" if art == "KR" else "projekt", nr, pid)).fetchone()
            if r:
                print(f"{art}{nr} (Stand {_zeit(r['stand_utc'])}, {r['beleg'] or '–'}): {r['text']}")
        else:
            raise kern.AmwFehler(f"„{ref}“: unbekannte Art {art}")
        if not r:
            raise kern.AmwFehler(f"{ref} gibt es nicht")


def cmd_regeln(a, con):
    pid = _projekt(con, a)
    regeln = con.execute("SELECT ebene, nr, text, stand_utc, vorlage FROM regel WHERE projekt_id = ? ORDER BY ebene, nr", (pid,)).fetchall()
    for r in regeln:
        grund = f" · Grundregel {r['vorlage'].split('/')[0]}" if r["vorlage"] else ""
        print(f"{'KR' if r['ebene'] == 'arbeit' else 'PR'}{r['nr']}{grund} (Stand {_zeit(r['stand_utc'])}): {r['text']}\n")
    if not regeln:
        print("Noch keine Regeln in diesem Projekt – es gilt das Leitbild (amw leitbild zeigen). Regeln entstehen aus Beschlüssen.")


def _lauf_warte(con, pid, a):
    """Blockiert, bis der Lauf dran ist: rc 0 = läuft (jetzt rechnen), 2 = abgebrochen/fertig, 3 = --hoechstens erreicht.
    Jede Minute eine Zeile mit dem Grund, damit man Warten von Hängen unterscheiden kann."""
    if not a.id:
        raise kern.AmwFehler("lauf warte <nr> [--hoechstens <min>]")
    ende = time.time() + a.hoechstens * 60 if a.hoechstens else None
    letzte = 0
    while True:
        l = betrieb.lauf_zeile(con, pid, a.id)
        if l["status"] == "laeuft":
            print(f"L{a.id} läuft – jetzt rechnen. Am Ende: amw lauf ende {a.id} --rc <Code>", flush=True)
            return 0
        if l["status"] in ("fertig", "abgebrochen"):
            print(f"L{a.id} ist {l['status']} – nicht rechnen", flush=True)
            return 2
        if time.time() - letzte >= 60:
            letzte = time.time()
            print(f"{time.strftime('%H:%M')} L{a.id} wartet: {betrieb.wartegrund(con, pid, l)}", flush=True)
        if ende and time.time() >= ende:
            print(f"L{a.id} wartet nach {a.hoechstens:g} min noch – bleibt eingereiht", flush=True)
            return 3
        time.sleep(5)


PRUEF_S = 5          # lauf ausfuehren: so oft nachsehen, ob der Schirm zugeht oder der Lauf beendet wurde
# Rückgabewerte von lauf ausfuehren, die nicht vom Befehl stammen (Ketten „nur weiter bei 0“ bleiben sauber)
RC_FRIST, RC_STRG_C, RC_NIE, RC_SCHIRM, RC_BEENDET = 124, 130, 200, 201, 202


def _baum_beenden(proc):
    """Den eigenen Befehl samt Kindern beenden (Prozess des Agenten, nicht der Dienst)."""
    import subprocess
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True)
    else:
        import signal
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
    try:
        proc.wait(timeout=30)
    except Exception:
        pass


def _lauf_ausfuehren(con, pid, a):
    """Einreihen → warten → Befehl starten → Ausgabe in die Ergebnis-Datei → rc durchreichen → lauf ende. Beim Schirm-Lauf:
    geht der Schirm zu oder beendet jemand den Lauf, endet der eigene Befehl (Prozessbaum) und der Lauf gilt als abgebrochen.
    rc: der des Befehls, sonst 200 = nie gestartet (aus der Schlange genommen, --hoechstens erreicht), 201 = Schirm zu,
    202 = Lauf von außen beendet, 124 = --frist erreicht, 130 = Strg+C."""
    import subprocess
    import threading
    befehl = getattr(a, "befehl", None) or []
    if not befehl:
        raise kern.AmwFehler("lauf ausfuehren --beschreibung … [--schirm] -- <befehl …> (der Befehl steht nach --)")
    beschreibung = a.beschreibung or a.rezept or " ".join(befehl)[:120]
    von = _von(a)
    lid = betrieb.lauf_start(con, pid, von, beschreibung, a.rezept, not a.leicht, a.schirm, a.aufgabe, warten=True,
                             erwartet_min=a.dauer, gpu=a.gpu, braucht_gb=a.braucht_gb, braucht_vram_gb=a.braucht_vram_gb,
                             braucht_platte_gb=a.braucht_platte_gb)
    print(f"L{lid} angemeldet: {beschreibung}", flush=True)
    from . import belegung                           # solange dieser Befehl wartet, gilt der Lauf als lebendig (siehe betrieb._lebt)
    belegung.lauf_merken(lid, os.getpid())
    a.id = lid
    try:
        w = _lauf_warte(con, pid, a)
    except KeyboardInterrupt:
        w = "Strg+C"
    if w != 0:
        if betrieb.lauf_zeile(con, pid, lid)["status"] in ("angemeldet", "laeuft"):
            betrieb.lauf_ende(con, pid, von, lid, None, f"nie gestartet ({'Strg+C' if w == 'Strg+C' else 'Wartezeit um'})",
                              abgebrochen=True)
            print(f"L{lid} aus der Schlange genommen", flush=True)
        belegung.lauf_vergessen(lid)
        return RC_NIE
    ausgabe = open(a.ergebnis, "w", encoding="utf-8", errors="replace") if a.ergebnis else None
    if ausgabe:
        ausgabe.write(f"# AMW L{lid} · {von} · {beschreibung}\n# Befehl: {' '.join(befehl)}\n# Start: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    eins = len(befehl) == 1                      # ein String mit Leerzeichen: als Befehlszeile der Shell
    try:
        proc = subprocess.Popen(befehl[0] if eins else befehl, shell=eins, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=os.name != "nt")
    except OSError as e:
        betrieb.lauf_ende(con, pid, von, lid, 127, f"Start fehlgeschlagen: {e}")
        raise kern.AmwFehler(f"L{lid}: Befehl ließ sich nicht starten ({e}) – Lauf beendet")
    belegung.lauf_merken(lid, proc.pid)              # die Prozesse dieses Laufs sind angemeldet – keine Dauer-Belegung
    letzte = [""]

    def mitschreiben():
        for roh in iter(proc.stdout.readline, b""):
            z = roh.decode("utf-8", errors="replace")
            sys.stdout.write(z)
            sys.stdout.flush()
            if ausgabe:
                ausgabe.write(z)
                ausgabe.flush()
            if z.strip():
                letzte[0] = z.strip()
    leser = threading.Thread(target=mitschreiben, daemon=True)
    leser.start()
    grund, rc_grund = None, None
    frist = time.time() + a.frist * 60 if a.frist else None
    try:
        while proc.poll() is None:
            for _ in range(PRUEF_S * 10):            # kurz schlafen, damit ein schneller Befehl nicht 5 s „hängt“
                if proc.poll() is not None:
                    break
                time.sleep(0.1)
            if proc.poll() is not None:
                break
            l = betrieb.lauf_zeile(con, pid, lid)
            if l["status"] != "laeuft":
                grund, rc_grund = f"L{lid} wurde beendet ({l['status']})", RC_BEENDET
            elif a.schirm and not schirm.zustand(con)["frei"]:
                grund, rc_grund = f"Schirm zu: {schirm.zustand(con)['grund'] or ''}".strip(), RC_SCHIRM
            elif frist and time.time() >= frist:
                grund, rc_grund = f"Frist {a.frist:g} min erreicht", RC_FRIST
            if grund:
                print(f"\n{grund} – beende den Befehl", flush=True)
                _baum_beenden(proc)
                break
    except KeyboardInterrupt:
        grund, rc_grund = "Strg+C", RC_STRG_C
        _baum_beenden(proc)
    leser.join(timeout=10)
    belegung.lauf_vergessen(lid)
    rc = proc.returncode
    if ausgabe:
        ausgabe.write(f"# Ende: {time.strftime('%Y-%m-%d %H:%M:%S')} · rc {rc_grund if grund else rc}"
                      + (f" · abgebrochen: {grund}" if grund else "") + "\n")
        ausgabe.close()
    wo = f" · Ausgabe: {a.ergebnis}" if a.ergebnis else ""
    if grund:
        if betrieb.lauf_zeile(con, pid, lid)["status"] == "laeuft":
            betrieb.lauf_ende(con, pid, von, lid, rc_grund, f"abgebrochen: {grund}{wo}"[:500], abgebrochen=True)
        print(f"L{lid} abgebrochen ({grund}), rc {rc_grund}", flush=True)
        return rc_grund
    betrieb.lauf_ende(con, pid, von, lid, rc, (f"rc {rc}{wo}" + (f" · {letzte[0]}" if letzte[0] else ""))[:500])
    print(f"L{lid} fertig, rc {rc}{wo}", flush=True)
    return rc


def cmd_benutzer(a, con):
    """Benutzer verwalten (nur der Mensch): neu NAME --rolle … [--projekte A,B] [--email …] | liste | aendern NAME
    [--rolle …] [--projekte …] [--email … (leer = entfernen)] | sperren NAME | entsperren NAME. Die E-Mail braucht die
    Firmen-Anmeldung: beim ersten Anmelden mit dem Firmenkonto wird der Benutzer darüber gefunden."""
    from . import benutzer
    von = _von(a)
    projekte = [x.strip() for x in a.projekte.split(",") if x.strip()] if a.projekte is not None else None
    if a.aktion == "neu":
        if not a.name:
            raise kern.AmwFehler("amw benutzer neu <name> [--rolle leser|bearbeiter|projekt_admin|system_admin --projekte A,B]")
        benutzer.neu(con, von, a.name, a.rolle, a.anzeige, a.email, projekte or ())
        print(f"Benutzer {a.name} angelegt – " + (benutzer.NAMEN[a.rolle] if a.rolle else "wartet auf Freigabe (noch keine Rechte)"))
    elif a.aktion == "freischalten":
        from . import abgleich
        if not a.name:
            raise kern.AmwFehler("amw benutzer freischalten <name> [--stunden 24]")
        code, bis = benutzer.freischalten(con, von, a.name, abgleich.speicher_aus_zugang(), a.stunden)
        print(f"Freischalt-Code für {a.name}: {code}")
        print(f"gültig bis {bis} (UTC), nur einmal. Gib ihn {a.name} persönlich weiter – er steht nirgends sonst."
              " Damit setzt er auf der Online-Seite unter „Neue Anmeldung“ sein Passwort und den zweiten Faktor.")
    elif a.aktion in ("aendern", "sperren", "entsperren"):
        if not a.name:
            raise kern.AmwFehler(f"amw benutzer {a.aktion} <name>")
        gesperrt = True if a.aktion == "sperren" else False if a.aktion == "entsperren" else None
        b = benutzer.aendern(con, von, a.name, a.rolle, gesperrt, projekte, a.email)
        print(f"{b['name']}: {benutzer.NAMEN.get(b['rolle'], 'wartet auf Freigabe')}" + (" · gesperrt" if b["gesperrt"] else ""))
    else:
        namen = {r[0]: r[1] for r in con.execute("SELECT id, name FROM projekt")}
        for b in benutzer.liste(con):
            pr = "alle" if b["rolle"] == "system_admin" else ", ".join(namen.get(i, "?") for i in b["projekte"]) or "–"
            print(f"{b['name']:<16} {benutzer.NAMEN.get(b['rolle'], 'wartet auf Freigabe'):<20} {'gesperrt ' if b['gesperrt'] else ''}Projekte: {pr}"
                  + (f" · {b['email']}" if b['email'] else ''))


def cmd_rechner(a, con):
    """Der Rechner auf einen Blick: Arbeitsspeicher, was außerhalb der Warteschlange belegt, Laufwerke, Aufräumvorschläge."""
    from . import belegung, platte
    komma = lambda x: str(x).replace(".", ",")
    frei, gesamt = betrieb.speicher_frei_gb()
    print(f"Arbeitsspeicher: {komma(frei)} von {komma(gesamt)} GB frei · Reserve {komma(betrieb.reserve_gb())} GB")
    dauer = belegung.aktuell(con)
    print("Außerhalb der Warteschlange belegt: " + (belegung.nennen(dauer, 10) if dauer else "nichts über der Grenze"))
    for l in platte.laufwerke(con):
        print(f"Laufwerk {l['laufwerk']} {komma(l['frei_gb'])} von {komma(l['gesamt_gb'])} GB frei ({komma(l['frei_prozent'])} %)"
              + (f" – {'DRINGEND' if l['stufe'] == 'rot' else 'wird knapp'}" if l["stufe"] else ""))
    v = platte.vorschlaege(con)
    if v["sicherungen"]:
        print(f"Aufräumvorschläge: {len(v['sicherungen'])} alte Sicherung(en), {komma(round(v['bytes'] / 2 ** 30, 1))} GB in {v['ordner']}"
              " (die AMW löscht nichts – aufräumen kann nur der Mensch)")
        for x in v["sicherungen"]:
            print(f"  {x['name']}  {komma(round(x['bytes'] / 2 ** 20))} MB  {x['tage']} Tage alt")
    else:
        print("Aufräumvorschläge: keine")
    pid = _projekt(con, a) if getattr(a, "projekt", None) else None
    z = platte.zuwaechse(con, pid)
    if z:
        print("Größte Zuwächse (7 Tage): " + "; ".join(f"{x['ordner']} +{komma(round(x['plus'] / 2 ** 30, 2))} GB" for x in z))
    ab = platte.ablagerungen(con, pid)
    if ab:
        print("Ablagerungen (Build-Reste, Caches, Worktrees – nur Anzeige):")
        for x in ab:
            print(f"  {x['ordner']}  {komma(round(x['bytes'] / 2 ** 30, 2))} GB" + (f"  seit {x['tage']} Tagen unverändert" if x["tage"] else ""))


def cmd_schirm(a, con):
    pid = _projekt(con, a)
    if a.aktion in ("frei", "zu"):
        z = schirm.setzen(con, pid, _von(a), a.aktion == "frei", a.grund, a.bis, a.quelle)
        print(schirm.text(z))
        if a.aktion == "frei":
            print(f"Geht von selbst zu bei Eingabe am PC (ab {schirm.RUHE_S // 60} min nach jetzt), neuer Fernsitzung,"
                  f" Eingabe von {kern.entwickler_name(con, pid)} in der Workbench am PC"
                  + (", zur bis-Zeit" if z["bis_utc"] else "") + ".")
        return
    print(schirm.text(schirm.zustand(con)))
    g = schirm.sperrgrund(con)
    print("Schirm-Läufe: " + ("dürfen starten" if not g else "warten – " + g))
    if a.verlauf:
        for z in schirm.verlauf(con, a.grenze):
            print(f"  {schirm.lokal(z['seit_utc']):<12} {'FREI' if z['frei'] else 'zu  '} {z['von']:<10} {z['quelle']:<9} {z['grund']}")


def cmd_lauf(a, con):
    pid = _projekt(con, a)
    if a.aktion == "start":
        if not a.beschreibung and not a.rezept:
            raise kern.AmwFehler("--beschreibung oder --rezept angeben")
        lid = betrieb.lauf_start(con, pid, _von(a), a.beschreibung or a.rezept, a.rezept, not a.leicht, a.schirm, a.aufgabe,
                                 warten=a.warten, erwartet_min=a.dauer, gpu=a.gpu, braucht_gb=a.braucht_gb,
                                 braucht_vram_gb=a.braucht_vram_gb, braucht_platte_gb=a.braucht_platte_gb)
        w = [r["id"] for r in betrieb.wartende(con, pid)]
        if lid in w:
            print(f"L{lid} eingereiht (Platz {w.index(lid) + 1} von {len(w)}) – noch nicht rechnen. Der Dienst benachrichtigt dich mit"
                  f" einer Freigabe, sobald L{lid} dran ist. Aus der Schlange nehmen: amw lauf ende {lid} --abgebrochen")
        else:
            print(f"L{lid} läuft – am Ende: amw lauf ende {lid} --rc <Code>")
    elif a.aktion == "ende":
        if not a.id:
            raise kern.AmwFehler("lauf ende <nr> --rc <Code>")
        weiter = betrieb.lauf_ende(con, pid, _von(a), a.id, a.rc, a.ergebnis, a.abgebrochen)
        print(f"L{a.id} beendet" + (f" – als Nächstes freigegeben: {', '.join(f'L{x}' for x in weiter)}" if weiter else ""))
    elif a.aktion == "vorziehen":
        if not a.id:
            raise kern.AmwFehler("lauf vorziehen <nr>")
        betrieb.lauf_vorziehen(con, pid, _von(a), a.id)
        weiter = betrieb.warteschlange(con, pid)
        print(f"L{a.id} steht vorn in der Warteschlange" + (f" – freigegeben: {', '.join(f'L{x}' for x in weiter)}" if weiter else ""))
    elif a.aktion == "zeige":
        if not a.id:
            raise kern.AmwFehler("lauf zeige <nr>")
        l = betrieb.lauf_zeile(con, pid, a.id)
        print(f"L{l['id']} {l['agent']} [{l['status']}]{' schwer' if l['schwer'] else ''}{' Schirm' if l['schirm'] else ''}"
              f"{' GPU' if l['gpu'] else ''}  {l['beschreibung']}")
        print(f"angemeldet {_zeit(l['angemeldet_utc'])} · Start {_zeit(l['start_utc']) or '–'} · Ende {_zeit(l['ende_utc']) or '–'}"
              f" · rc {l['rc'] if l['rc'] is not None else '–'}")
        if l["status"] == "angemeldet":
            print(betrieb.wartegrund(con, pid, l))
    elif a.aktion == "warte":
        return _lauf_warte(con, pid, a)
    elif a.aktion == "ausfuehren":
        return _lauf_ausfuehren(con, pid, a)
    else:
        w = betrieb.wartende(con, pid)
        if w:
            print("Warteschlange:")
            for i, r in enumerate(w, 1):                 # die Schlange gilt für den ganzen Rechner; fremde Läufe ohne Inhalt
                eigen = r["projekt_id"] == pid
                print(f"  {i}. L{r['id']:<5} {r['agent'] if eigen else '–':<8}{' schwer' if r['schwer'] else ''}{' Schirm' if r['schirm'] else ''}"
                      f"{' GPU' if r['gpu'] else ''}{' (vorgezogen)' if r['rang'] else ''} seit {_zeit(r['angemeldet_utc'])}"
                      f"  {r['beschreibung'] if eigen else '(anderes Projekt)'}")
            print()
        for r in con.execute("SELECT * FROM lauf WHERE projekt_id = ? ORDER BY id DESC LIMIT ?", (pid, a.grenze)):
            print(f"L{r['id']:<5} {r['agent']:<8} [{r['status']}]{' schwer' if r['schwer'] else ''}{' Schirm' if r['schirm'] else ''}"
                  f"{' GPU' if r['gpu'] else ''} {_zeit(r['start_utc'])}–{_zeit(r['ende_utc']) or '…'} rc {r['rc'] if r['rc'] is not None else '–'}  {r['beschreibung']}")


def cmd_pruefung(a, con):
    pid = _projekt(con, a)
    if a.aktion == "bitte":
        prid = betrieb.pruefbitte(con, pid, _von(a), a.pruefer, a.zweig, a.sha, a.punkte, a.aufgabe)
        print(f"P{prid} an {a.pruefer}")
    elif a.aktion in ("gruen", "rot"):
        kette = betrieb.pruefung_ergebnis(con, pid, _von(a), a.id, a.aktion, a.bemerkung)
        print(f"P{a.id} → {a.aktion}" + (f" · {kette}" if kette else ""))
    elif a.aktion == "ist-gruen":
        r = betrieb.ist_gruen(con, pid, a.sha)
        print(f"grün: P{r['id']}" if r else "NICHT grün")
        return 0 if r else 3
    else:
        for r in con.execute("SELECT * FROM pruefung WHERE projekt_id = ? AND (? OR ergebnis = 'offen') ORDER BY id DESC LIMIT 50",
                             (pid, int(a.alle))):
            print(f"P{r['id']:<5} [{r['ergebnis']}] {r['zweig']}@{r['sha'][:8]} {r['bauer']} → {r['pruefer']}"
                  + (f" A{r['aufgabe_id']}" if r["aufgabe_id"] else ""))


def cmd_freigabe(a, con):
    """Merge-OK des Leads für eine Aufgabe (Abnahme-Kette)."""
    pid = _projekt(con, a)
    print(betrieb.freigabe_merge(con, pid, _von(a), a.aufgabe, a.zweig, a.zurueck))


def cmd_server(a, con):
    """Projekt-Server, die der Wächter überwacht (Port antwortet?) und auf Wunsch neu startet."""
    pid = _projekt(con, a)
    if a.aktion == "anmelden":
        if not (a.name and a.port):
            raise kern.AmwFehler("server anmelden <name> --port N [--start \"Befehl\" --ordner Pfad --neustart --zustaendig X]")
        print(f"Server {a.name}: " + ueberwachung.server_anmelden(con, pid, _von(a), a.name, a.port, a.start, a.ordner,
                                                                  a.neustart, a.zustaendig)
              + (" – der Dienst startet ihn bei Ausfall neu" if a.neustart else " – Ausfall wird gemeldet"))
    elif a.aktion == "abmelden":
        ueberwachung.server_abmelden(con, pid, _von(a), a.name)
        print(f"Server {a.name} wird nicht mehr überwacht")
    elif a.aktion == "pruefen":
        for s in con.execute("SELECT name, port FROM server WHERE projekt_id = ? AND aktiv = 1 ORDER BY name", (pid,)):
            print(f"{s['name']:<20} Port {s['port']:<6} " + ("antwortet" if ueberwachung.antwortet(s["port"]) else "ANTWORTET NICHT"))
    else:
        zeilen = con.execute("SELECT * FROM server WHERE projekt_id = ? AND aktiv = 1 ORDER BY name", (pid,)).fetchall()
        if not zeilen:
            print("keine Server angemeldet – amw server anmelden <name> --port N …")
        for s in zeilen:
            print(f"{s['name']:<20} Port {s['port']:<6} {s['zustand']:<9} seit {_zeit(s['seit_utc']) or '–'}"
                  f"  zuständig {s['zustaendig']}  Neustart {'ja' if s['neustart'] else 'nein'}  Ausfälle {s['ausfaelle']}"
                  + (f"\n    {s['startbefehl']}" if s["startbefehl"] else ""))


def cmd_ki(a, con):
    """Lokale KIs: eintragen, Modelle freigeben, beauftragen (→ amw/ki.py, doc/plan-lokale-ki.md)."""
    from . import ki
    pid = _projekt(con, a)
    von = _von(a)
    if a.aktion in ("neu", "aendern"):
        if not a.name:
            raise kern.AmwFehler("ki neu <name> --art bild --schnittstelle comfyui [--endpunkt … --start \"…\" --ordner …]")
        aktiv = True if a.einschalten else False if a.abschalten else None
        _, was = ki.ki_setzen(con, von, a.name, a.art, a.schnittstelle, a.endpunkt, a.version, a.lizenz, a.ablage, a.start,
                              a.ordner, a.vram, aktiv, neu=a.aktion == "neu")
        print(f"KI {a.name}: {was}")
    elif a.aktion == "modell":
        if not (a.name and a.teil):
            raise kern.AmwFehler("ki modell <ki> <name> [--datei … --lizenz … --kommerziell ja|nein|registrierung"
                                 " --nutzungsregeln --quelle URL --sha256 … --vram GB --sekunden s]")
        regeln = True if a.nutzungsregeln else False if a.ohne_nutzungsregeln else None
        _, was = ki.modell_setzen(con, von, a.name, a.teil, a.datei, a.version, a.sha256, a.quelle, a.lizenz, a.kommerziell,
                                  regeln, a.vram, a.sekunden, a.notiz)
        print(f"Modell {a.teil}: {was}")
    elif a.aktion in ("freigeben", "sperren"):
        if not (a.name and a.teil):
            raise kern.AmwFehler(f"ki {a.aktion} <ki> <modell>" + (" --grund …" if a.aktion == "sperren" else ""))
        ki.freigeben(con, pid, von, a.name, a.teil, a.aktion == "freigeben", a.grund)
        print(f"Modell {a.teil}: {'frei' if a.aktion == 'freigeben' else 'gesperrt'}")
    elif a.aktion == "vorlage":
        if not (a.name and a.teil and a.datei):
            raise kern.AmwFehler("ki vorlage <ki> <name> --datei workflow_api.json [--beschreibung …]")
        print(f"Vorlage {a.teil}: " + ki.vorlage_setzen(con, pid, von, a.name, a.teil, a.datei, a.beschreibung))
    elif a.aktion == "recht":
        if not a.name:
            raise kern.AmwFehler("ki recht <ki> --wer alle|rolle:<rolle>|<Name> [--entziehen]")
        n = ki.recht(con, pid, von, a.name, a.wer, a.entziehen)
        print(f"{a.wer}: " + ("Recht entzogen" if a.entziehen and n else "hatte kein Recht" if a.entziehen
                              else f"darf {a.name} beauftragen"))
    elif a.aktion == "auftrag":
        if not a.name:
            raise kern.AmwFehler("ki auftrag <ki> --prompt … [--modell … --vorlage … --anzahl N --seed N --aufgabe N]")
        prompt = a.prompt
        if a.prompt_datei:
            with open(a.prompt_datei, encoding="utf-8") as f:
                prompt = f.read()
        lid, _, laeuft = ki.auftrag(con, pid, von, a.name, prompt, a.modell, a.vorlage, a.negativ, a.seed, a.anzahl, a.breite,
                                    a.hoehe, a.bild, a.parameter, a.titel, a.aufgabe, a.frist, a.nachts)
        print(f"L{lid} " + ("ist dran – " if laeuft else f"eingereiht ({betrieb.wartegrund(con, pid, betrieb.lauf_zeile(con, pid, lid))}) – ")
              + "die AMW führt den Auftrag selbst aus und legt die Ergebnisse als Dokumente ab. Du wirst benachrichtigt, wenn"
              f" er fertig ist; du musst nicht warten. Stand: amw ki zeige L{lid} · abbrechen: amw lauf ende {lid} --abgebrochen")
    elif a.aktion == "fenster":
        n, sek = ki.nachts_wartend(con)
        sperre = ki.nacht_sperre(con)
        print(f"KI-Fenster: {ki.fenster_text()} (Ortszeit; ändern: Workbench › Zahnrad › Dieser PC) – gerade "
              + (f"zu: {sperre}" if sperre else "offen") + f". {n} Auftrag/Aufträge mit --nachts warten"
              + (f" (≈ {max(1, round(sek / 60))} min nach Modell-Probe)" if sek else "") + ".")
    elif a.aktion == "vermerk":
        if not a.name or not a.art:
            raise kern.AmwFehler("ki vermerk D<nr> --art ausgewaehlt|verworfen|nachbearbeitet [--text …] (nachbearbeitet: --text, was"
                                 " von Hand geändert wurde)")
        art = ki.vermerk_art(a.art)
        vid = ki.vermerken(con, pid, von, a.name, art, a.text, KANAL.get())
        print(f"Vermerk {vid}: D{a.name.strip().lstrip('Dd')} {ki.VERMERK_TEXT[art]}")
    elif a.aktion == "zeige":
        if not a.name:
            raise kern.AmwFehler("ki zeige L<nr>")
        x = ki.auftrag_zeile(con, pid, a.name)
        l = betrieb.lauf_zeile(con, pid, x["lauf_id"])
        k = con.execute("SELECT name FROM ki WHERE id = ?", (x["ki_id"],)).fetchone()[0]
        print(f"L{x['lauf_id']} KI {k} · Auftrag {x['zustand']} · Lauf {l['status']} · von {x['auftraggeber']}"
              + (f" · A{x['aufgabe_id']}" if x["aufgabe_id"] else ""))
        print(f"angemeldet {_zeit(x['angelegt_utc'])} · Start {_zeit(x['start_utc']) or '–'} · Ende {_zeit(x['ende_utc']) or '–'}"
              + (f" · {x['dauer_s'] / 60:.1f} min" if x["dauer_s"] else "") + (f" · bis {x['vram_spitze_gb']:g} GB" if x["vram_spitze_gb"] else ""))
        if l["status"] == "angemeldet":
            print(betrieb.wartegrund(con, pid, l))
        if x["fortschritt"]:
            print(f"Stand: {x['fortschritt']}")
        if x["fehler"]:
            print(f"Fehler: {x['fehler']}")
        print(f"Prompt: {x['prompt']}" + (f"\nNegativ: {x['negativ']}" if x["negativ"] else "")
              + f"\nSeed {x['seed']} · Anzahl {x['anzahl']}")
        for d in json.loads(x["dokumente"] or "[]"):
            for h in ki.herkunft_von(con, pid, d):
                print(f"  D{d} v{h['nr']}: {h['ki']} {h['ki_version'] or ''} · {h['modell'] or ''} ({h['modell_lizenz'] or '?'})"
                      f" · Seed {h['seed']}" + (f" · {h['dauer_s']:g} s" if h["dauer_s"] else "") + f" · {h['gegenprobe'] or ''}")
    elif a.aktion == "pruefen":
        ki.zustand_pruefen(con)
        for r in con.execute("SELECT name, endpunkt, zustand, version, geladen FROM ki WHERE aktiv = 1 ORDER BY name"):
            print(f"{r['name']:<12} {r['endpunkt']:<26} {r['zustand']:<9} {r['version'] or ''}"
                  + (f"  geladen: {', '.join(json.loads(r['geladen']))}" if r["geladen"] and json.loads(r["geladen"]) else ""))
    elif a.aktion == "nachweis":
        print(ki.nachweis_text(ki.nachweis(con, pid, a.aufgabe, a.bogen, a.alle)), end="")
    else:
        u = ki.uebersicht(con, pid)
        if not u["kis"]:
            print("keine KI eingetragen – amw ki neu <name> --art sprache|bild --schnittstelle ollama|comfyui …")
        for k in u["kis"]:
            print(f"{k['name']:<12} {k['art']:<8} {k['schnittstelle']:<8} {k['endpunkt']:<26} {k['zustand']:<9} {k['version'] or ''}"
                  + (f"  · {k['wartend']} wartend" if k["wartend"] else "")
                  + f"  · darf: Lead, Entwickler{', ' + ', '.join(k['darf']) if k['darf'] else ''}")
        if u["modelle"]:
            print("\nModelle:")
            for m in u["modelle"]:
                print(f"  {m['ki']:<10} {m['name']:<34} [{m['freigabe']}]{' Nutzungsregeln' if m['nutzungsregeln'] else ''}"
                      f" kommerziell {m['kommerziell']} · {m['lizenz'] or 'Lizenz?'}"
                      + (f" · {m['freigabe_grund']}" if m["freigabe_grund"] else ""))
        if u["vorlagen"]:
            print("\nVorlagen:")
            for v in u["vorlagen"]:
                print(f"  {v['ki']:<10} {v['name']:<24} {v['beschreibung'] or ''} (Stand {_zeit(v['stand_utc'])}, {v['von']})")
        if u["auftraege"]:
            print("\nAufträge:")
            for x in u["auftraege"][:15]:
                print(f"  L{x['lauf_id']:<5} {x['ki']:<9} {x['zustand']:<11} {x['auftraggeber']:<8} "
                      + (", ".join(f"D{d}" for d in x["dokumente"]) + " · " if x["dokumente"] else "")
                      + betrieb.kurzfassung(x["titel"] or x["prompt"], 70))


def cmd_hinweis(a, con):
    pid = _projekt(con, a)
    if a.aktion == "setzen":
        print(f"Anweisung #{betrieb.hinweis(con, pid, _von(a), a.fuer, a.text, a.bis)} gesetzt")
    else:
        print(f"{betrieb.sperre_aufheben(con, pid, _von(a), a.id)} aufgehoben")


def cmd_rezept(a, con):
    pid = _projekt(con, a)
    if a.aktion == "setzen":
        print(betrieb.rezept_setzen(con, pid, a.name, a.befehl, a.beschreibung, a.schirm, a.speicher or 0.0, not a.leicht, a.gpu))
    elif a.aktion == "zeige":
        r = con.execute("SELECT * FROM rezept WHERE projekt_id = ? AND name = ?", (pid, a.name)).fetchone()
        if not r:
            raise kern.AmwFehler(f"Rezept „{a.name}“ gibt es nicht")
        print(f"{r['name']} (Stand {_zeit(r['stand_utc'])}){' · Schirm' if r['braucht_schirm'] else ''}"
              f"{' · schwer' if r['schwer'] else ''}{' · GPU' if r['gpu'] else ''} · ≥ {r['braucht_speicher_gb']:g} GB frei\n{r['beschreibung'] or ''}\n{r['befehl']}")
    else:
        for r in con.execute("SELECT name, beschreibung FROM rezept WHERE projekt_id = ? ORDER BY name", (pid,)):
            print(f"{r['name']:<24} {r['beschreibung'] or ''}")


def _text(a):
    if getattr(a, "text_datei", None):
        with open(a.text_datei, encoding="utf-8") as f:
            return f.read()
    return a.text or ""


def cmd_wortlaut(a, con):
    wid = wissen.wortlaut_neu(con, _projekt(con, a), _von(a), _text(a), a.kanal, a.zeit, a.bemerkung)
    print(f"W{wid} erfasst")


def cmd_beschluss(a, con):
    pid = _projekt(con, a)
    if a.aktion in ("ueberholt", "unklar", "gilt", "thema"):
        if not a.nr:
            raise kern.AmwFehler(f"amw beschluss {a.aktion} B12" + (" --durch B30" if a.aktion == "ueberholt" else "")
                                 + (" --thema \"…\"" if a.aktion == "thema" else ""))
        if a.aktion == "thema":
            print(f"B{a.nr} → Thema „{wissen.beschluss_thema(con, pid, _von(a), a.nr, a.thema, a.neues_thema)}“")
        else:
            wissen.beschluss_status(con, pid, _von(a), a.nr, a.aktion, a.durch)
            print(f"B{a.nr} → {a.aktion}" + (f" (ersetzt durch B{a.durch})" if a.durch and a.aktion == "ueberholt" else ""))
        return
    hinweise = []
    bid = wissen.beschluss_neu(con, pid, _von(a), a.stichwort, _text(a), a.quelle, a.thema, a.zeit,
                               a.wortlaut, a.aufgaben, a.ersetzt, a.neues_thema, hinweise,
                               wortlaut_neu=(a.wortlaut_text, a.wortlaut_kanal, a.wortlaut_zeit) if a.wortlaut_text else None)
    print(f"B{bid} angelegt" + (f", B{a.ersetzt} überholt" if a.ersetzt else ""))
    for h in hinweise:
        print(h)


def cmd_thema(a, con):
    """Design-Dokument je Thema: liste | zeige | neu | einstellen | pflegen | bestaetigen | dokument."""
    from . import themen
    pid = _projekt(con, a)
    if a.aktion == "liste":
        for t in themen.liste(con, pid):
            if a.suche and a.suche.lower() not in t["name"].lower():
                continue
            st = {"ohne": "ohne Zusammenfassung", "aktuell": "aktuell", "veraltet": f"veraltet seit B{t['veraltet_seit']}"}[t["stand"]]
            print(f"TH{t['id']:<4} {t['gilt']:>4} gilt{(' · ' + str(t['unklar']) + ' unklar') if t['unklar'] else ''}"
                  f"  {'[Stil] ' if t['stil'] else ''}{t['name'][:70]}  · {st} · Pfleger {t['pfleger'] or '–'}")
        return
    if a.aktion == "neu":
        tid = themen.neu(con, pid, _von(a), a.name, a.pfleger, a.stil)
        print(f"TH{tid} angelegt")
        return
    if not a.name:
        raise kern.AmwFehler(f"amw thema {a.aktion} <TH-Nr. oder Name>")
    if a.aktion == "zeige":
        s = themen.seite(con, pid, a.name)
        print(f"TH{s['id']} {s['name']}" + (" [Projekt-Stil]" if s["stil"] else "") + f" · Pfleger {s['pfleger'] or '–'}")
        z = s["zusammenfassung"]
        if z:
            print(f"\nGILT JETZT (Fassung {z['nr']}, {z['von']}, {_zeit(z['zeit_utc'])})"
                  + (f" – VERALTET seit B{s['veraltet_seit']}" if s["stand"] == "veraltet" else "") + f":\n{z['text']}")
        else:
            print("\n(noch keine Zusammenfassung – amw thema pflegen …)")
        print(f"\nGeltende Beschlüsse ({len(s['gilt'])}, neueste zuerst):")
        for b in s["gilt"][:a.grenze]:
            print(f"  B{b['id']} {_zeit(b['zeit_utc'])} {b['stichwort']}: {b['regel'][:220]}")
        if s["unklar"]:
            print(f"Unklar ({len(s['unklar'])}): " + ", ".join(f"B{b['id']}" for b in s["unklar"]))
        if s["ueberholt"]:
            print(f"Überholt ({len(s['ueberholt'])}): " + ", ".join(f"B{b['id']}" + (f"→B{b['ersetzt_durch']}" if b["ersetzt_durch"] else "")
                                                               for b in s["ueberholt"][:30]))
        if s["dokumente"]:
            print("Dokumente: " + "; ".join(f"D{d['id']} {d['titel'][:50]}" for d in s["dokumente"]))
    elif a.aktion == "einstellen":
        t = themen.einstellen(con, pid, _von(a), a.name, a.pfleger, True if a.stil else False if a.kein_stil else None)
        print(f"TH{t['id']}: Pfleger {t['pfleger'] or '–'}" + (" · Projekt-Stil" if t["stil"] else ""))
    elif a.aktion == "pflegen":
        print(f"Fassung {themen.pflegen(con, pid, _von(a), a.name, _text(a))} gespeichert")
    elif a.aktion == "bestaetigen":
        themen.bestaetigen(con, pid, _von(a), a.name)
        print("Zusammenfassung bestätigt – gilt weiter")
    elif a.aktion == "dokument":
        if not a.dokument:
            raise kern.AmwFehler("amw thema dokument <Thema> --dokument D12 [--loesen]")
        themen.dokument(con, pid, _von(a), a.name, int(str(a.dokument).lstrip("Dd")), a.loesen)
        print(f"D{str(a.dokument).lstrip('Dd')} {'gelöst' if a.loesen else 'hängt am Thema'}")


def cmd_regel(a, con):
    print(wissen.regel_setzen(con, _projekt(con, a), _von(a), a.ebene, a.nr, _text(a), a.beschluss, a.teil))


def cmd_dokument(a, con):
    from . import dokumente
    pid = _projekt(con, a)
    bezug = {"bogen": a.bogen, "aufgabe": a.aufgabe, "frage": a.frage, "beschluss": a.beschluss}
    if a.aktion == "ablegen":
        datei = a.datei or a.nr
        if not datei:
            raise kern.AmwFehler("Datei fehlt: amw dokument ablegen <datei> --titel … --art … --aufgabe <nr>")
        did = dokumente.ablegen(con, pid, _von(a), datei, a.titel, a.art or "ergebnis", a.notiz, a.online, **bezug)
        print(f"D{did} abgelegt – ansehen: Workbench › Dokumente oder `amw dokument zeigen {did}`")
        return
    if a.aktion == "einsammeln":
        return _einsammeln(a, con, pid)
    if a.aktion == "liste":
        b_art = next((k for k, v in bezug.items() if v), None)
        for d in dokumente.liste(con, pid, a.art, b_art, int(str(bezug[b_art]).lstrip("ABFabf")) if b_art else None,
                                 a.agent, a.suche, None if a.alle else "aktuell"):
            b = f"{d['bezug_art']} {d['bezug_id']}" if d["bezug_art"] else "–"
            print(f"D{d['id']:<5} v{d['version']:<3} {d['art']:<9} {d['endung']:<6} {max(1, d['groesse'] // 1024):7d} KB"
                  f"  {d['angelegt_von']:<10} {b:<16} {d['titel'][:80]}" + (f"  [{d['status']}]" if d["status"] != "aktuell" else ""))
        return
    if not a.nr:
        raise kern.AmwFehler("Nummer des Dokuments fehlt (z. B. amw dokument zeigen 12)")
    nr = int(str(a.nr).lstrip("Dd"))
    datei = a.datei or a.pfad
    if a.aktion == "zeigen":
        d = dokumente.dokument(con, pid, nr)
        print(f"D{d['id']} „{d['titel']}“ · {d['art']} · {d['status']}" + (" · online" if d["online"] else "")
              + (f" · zu {d['bezug_art']} {d['bezug_id']}" if d["bezug_art"] else "") + f" · von {d['angelegt_von']}")
        for v in d["versionen"]:
            print(f"  v{v['nr']} {v['zeit_utc']} {v['von']:<10} {v['endung']} {max(1, v['groesse'] // 1024)} KB"
                  + (f" – {v['notiz']}" if v["notiz"] else "") + f"\n     {dokumente.datei_pfad(v['sha256'], v['endung'])}")
        for n in dokumente.gespraech(con, pid, nr):
            print(f"  #{n['id']} {n['zeit_utc']} {n['von']} → {n['an']}: {n['kurz']}")
    elif a.aktion == "version":
        if not datei:
            raise kern.AmwFehler("Datei fehlt: amw dokument version <nr> <datei> --notiz …")
        print(f"D{nr} v{dokumente.version(con, pid, _von(a), nr, datei, a.notiz)} abgelegt")
    elif a.aktion in ("kommentar", "ueberarbeiten"):
        nid, namen = dokumente.melden(con, pid, _von(a), nr, a.text, a.aktion == "ueberarbeiten")
        print(f"#{nid} an {', '.join(namen)}")
    elif a.aktion == "zuordnen":
        neu = {"bogen": None} if a.loesen else {k: v for k, v in bezug.items() if v}     # leer = Bezug unverändert
        d = dokumente.setzen(con, pid, _von(a), nr, a.titel, a.art, **neu)
        print(f"D{nr}: " + (f"zu {d['bezug_art']} {d['bezug_id']}" if d["bezug_art"] else "ohne Bezug") + f" · {d['art']} · {d['titel']}")
    elif a.aktion in ("archivieren", "wiederherstellen"):
        dokumente.status_setzen(con, pid, _von(a), nr, "archiviert" if a.aktion == "archivieren" else "aktuell")
        print(f"D{nr} {'archiviert' if a.aktion == 'archivieren' else 'wieder aktuell'}")
    elif a.aktion in ("online", "offline"):
        dokumente.online_setzen(con, pid, _von(a), nr, a.aktion == "online")
        print(f"D{nr}: Datei {'auch online' if a.aktion == 'online' else 'nur am PC'}")
    elif a.aktion == "loeschen":
        if not a.ja:
            raise kern.AmwFehler("Endgültig löschen mit --ja bestätigen (archivieren geht ohne)")
        print(f"D{nr} gelöscht ({dokumente.loeschen(con, pid, _von(a), nr)} Datei(en) entfernt)")


def _einsammeln(a, con, pid):
    from . import einsammeln
    if a.uebernehmen:
        if not a.frage:
            raise kern.AmwFehler("--uebernehmen braucht --frage <F-nr> (die beantwortete Frage zur Liste)")
        angelegt, weg = einsammeln.uebernehmen(con, pid, _von(a), int(str(a.frage).lstrip("Ff")), a.nur)
        for rel, did in angelegt:
            print(f"D{did}  {rel}")
        for rel, grund in weg:
            print(f"–      {rel}: {grund}")
        print(f"{len(angelegt)} übernommen, {len(weg)} übersprungen")
        return
    ordner = a.datei or a.nr
    if not ordner:
        raise kern.AmwFehler("Ordner fehlt: amw dokument einsammeln <ordner> [--melden]")
    liste = einsammeln.liste(con, pid, ordner)
    if a.melden:
        did, fid = einsammeln.melden(con, pid, _von(a), liste)
        n, groesse = einsammeln.summe(liste)
        print(f"Liste als D{did} abgelegt, Frage F{fid} an den Entwickler ({n} Dateien vorgeschlagen). Übernehmen erst nach"
              f" der Antwort: amw dokument einsammeln --uebernehmen --frage {fid}")
        return
    print(einsammeln.bericht(liste).split("<details>")[0].rstrip())
    print("\nNur gelesen. Zur Freigabe: dieselbe Zeile mit --melden (Liste als Dokument + Frage an den Entwickler).")


def cmd_notiz(a, con):
    pid = _projekt(con, a)
    if a.aktion == "entfernen":
        if not a.schluessel:
            raise kern.AmwFehler("welche Schlüssel? (mehrere mit Leerzeichen)")
        beschluss = int(str(a.beschluss).lstrip("Bb")) if a.beschluss else None
        weg, fehlt = wissen.notiz_entfernen(con, pid, _von(a), a.schluessel, beschluss)
        print(f"entfernt: {len(weg)}" + (f" · nicht vorhanden: {', '.join(fehlt)}" if fehlt else ""))
        return
    eins = a.schluessel[0] if a.schluessel else None
    if a.aktion == "setzen":
        if not eins:
            raise kern.AmwFehler("Schlüssel fehlt")
        print(wissen.notiz_setzen(con, pid, _von(a), eins, _text(a)))
    else:
        sql, par = "SELECT schluessel, wert, geaendert_utc FROM notiz WHERE projekt_id = ?", [pid]
        if eins:
            sql += " AND schluessel = ?"
            par.append(eins)
        for w in (a.suche or "").split():              # z. B. --suche CC5 oder --suche A1162 (Schlüssel oder Text)
            sql += " AND (schluessel LIKE ? OR wert LIKE ?)"
            par += [f"%{w}%", f"%{w}%"]
        n = 0
        for r in con.execute(sql + " ORDER BY schluessel", par):
            n += 1
            print(f"[{r['schluessel']}] {_zeit(r['geaendert_utc'])}\n{r['wert'] if eins else r['wert'][:160]}\n")
        if a.suche and not n:
            print(f"keine Notiz mit „{a.suche}“")


def cmd_release(a, con):
    pid = _projekt(con, a)
    if a.aktion == "merge":
        print(f"R{wissen.release_merge(con, pid, _von(a), a.titel, a.commit, _text(a) or None, a.aufgaben)} eingetragen")
    elif a.aktion == "entwurf":                    # Versionshinweise der nächsten Version, ohne KI
        from . import versionshinweise
        e = versionshinweise.entwurf(con, pid)
        text = versionshinweise.als_text(e, mit_aufgaben=True)
        print(text or "Seit der letzten Version ist nichts fertig geworden.")
        n = sum(1 for g in e.values() for x in g if x["vorschlag"])
        if n:
            print(f"\n{n} Satz/Sätze sind Vorschläge aus der Zusammenfassung (kein Satz für Nutzer beim Abschließen) –"
                  " mit eigenem Text: amw release version … --oeffentlich-datei <datei>")
    elif a.aktion == "version":
        oeffentlich = None
        if a.oeffentlich_datei:
            with open(a.oeffentlich_datei, encoding="utf-8") as f:
                oeffentlich = f.read().strip()
        rid, n = wissen.release_version(con, pid, _von(a), a.version, a.titel, a.commit, _text(a) or None, oeffentlich)
        print(f"Version {a.version} (R{rid}) aus {n} Merge(s) – Versionshinweise eingetragen")
    else:
        for r in con.execute("SELECT * FROM release WHERE projekt_id = ? ORDER BY zeit_utc DESC LIMIT 30", (pid,)):
            print(f"R{r['id']:<5} {r['art']:<7} {r['version'] or '(offen)':<9} {_zeit(r['zeit_utc'])} {r['titel']}")


def web_einrichten(abgleich):
    """Einmal am PC: Turso-Zugang abfragen (Schlüssel verdeckt), prüfen, speichern, Abgleich an, Wächter neu starten."""
    import getpass
    from . import einrichtung
    pfad = abgleich.zugang_pfad()
    try:
        with open(pfad, encoding="utf-8") as f:
            alt = json.load(f)
    except (OSError, ValueError):
        alt = {}
    if alt.get("url") and alt.get("token"):
        print(f"Vorhanden: {alt['url']} (Schlüssel gespeichert). Enter = behalten.")
    url = input("Turso-Adresse (libsql://….turso.io): ").strip() or alt.get("url", "")
    token = getpass.getpass("Turso-Schlüssel (wird nicht angezeigt): ").strip() or alt.get("token", "")
    if not url.startswith(("libsql://", "https://")) or ".turso.io" not in url or not token:
        raise kern.AmwFehler("Adresse muss libsql://….turso.io sein, Schlüssel darf nicht leer sein")
    sp = abgleich.TursoSpeicher(url, token)
    try:
        sp.ausfuehren([(s, []) for s in abgleich.SCHEMA])
    except OSError as e:
        raise kern.AmwFehler(f"Turso nicht erreichbar oder Schlüssel abgelehnt ({e}) – nichts gespeichert")
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    neu = pfad + ".neu"
    with open(neu, "w", encoding="utf-8") as f:
        json.dump({**alt, "url": url, "token": token, "abgleich": True}, f, indent=2)
    os.replace(neu, pfad)
    print(f"✓ Turso verbunden, Tabellen bereit, Zugang gespeichert in {pfad} (nur für deinen Windows-Benutzer)")
    rc, aus = einrichtung.powershell(f"if (Get-ScheduledTask -TaskName '{einrichtung.AUFGABE}' -ErrorAction SilentlyContinue) "
                                     f"{{ Stop-ScheduledTask -TaskName '{einrichtung.AUFGABE}'; Start-Sleep 2; "
                                     f"Start-ScheduledTask -TaskName '{einrichtung.AUFGABE}'; 'neu gestartet' }} else {{ 'fehlt' }}")
    if "neu gestartet" in aus:
        print("✓ Dienst neu gestartet – er lädt die Ansichten in den nächsten Sekunden hoch")
    else:
        print("! Dienst ist nicht eingerichtet: zuerst `amw dienst einrichten --ja`")
    print("Jetzt die Seite beim Hoster öffnen – der Assistent fragt nach derselben Adresse und einem Schlüssel.")
    return 0


def _web_sso(a):
    """Firmen-Anmeldung (R2): zeigen oder einstellen. Das Geheimnis des Anbieters trägt ein System-Admin auf der Online-Seite
    ein (sso.php?einrichten) – es liegt nur in der Konfiguration beim Webhoster, nie hier."""
    from . import abgleich
    sp = abgleich.speicher_aus_zugang(nur_wenn_an=False)
    if sp is None:
        raise kern.AmwFehler("Kein Online-Speicher eingerichtet (amw web einrichten)")
    neu = {k: v for k, v in (("aussteller", a.aussteller), ("client_id", a.client_id)) if v is not None}
    if a.an or a.aus:
        neu["an"] = bool(a.an)
    try:
        d = abgleich.sso_setzen(sp, neu) if neu else abgleich.sso_einstellungen(sp)
    except ValueError as e:
        raise kern.AmwFehler(str(e)) from None
    zugang = {"geheimnis": "Geheimnis gespeichert", "zertifikat": "Zertifikat gespeichert"}.get(d["zugang"], "noch kein Geheimnis auf der Online-Seite")
    print(f"Firmen-Anmeldung: {'an' if d['an'] else 'aus'}")
    print(f"  Aussteller:   {d['aussteller'] or '–'}")
    print(f"  Client-ID:    {d['client_id'] or '–'}")
    print(f"  Beim Webhoster: {zugang}" + (f" · Redirect-URI {d['rueckweg']}" if d['rueckweg'] else ''))
    if d["an"] and not d["zugang"]:
        print("  Der Knopf erscheint erst, wenn ein System-Admin das Geheimnis auf der Online-Seite einträgt: <Adresse>/sso.php?einrichten")


def cmd_speicher(a):
    """Eigener Online-Speicher (Stufe R3a): Schlüsselpaar für den libSQL-Server erzeugen, Zugang am PC eintragen (noch
    ohne Synchronisierung), Token für die Online-Seite einmal zeigen. Der private Schlüssel wird nicht gespeichert."""
    from . import abgleich, schluessel
    try:
        url = abgleich.speicher_adresse("libsql", a.url or "")
    except ValueError as e:
        raise kern.AmwFehler(f"{e} – amw speicher schluessel --url https://amw-db.firma.lan") from None
    if a.ca and not os.path.isfile(a.ca):
        raise kern.AmwFehler(f"Zertifikat-Datei gibt es nicht: {a.ca}")
    pfad = abgleich.zugang_pfad()
    try:
        with open(pfad, encoding="utf-8") as f:
            alt = json.load(f)
    except (OSError, ValueError):
        alt = {}
    if alt.get("url") and not a.ersetzen:
        raise kern.AmwFehler(f"Es gibt schon einen Online-Speicher ({alt['url']}). Ersetzen mit --ersetzen – dann gilt der alte"
                             " Zugang auf diesem PC nicht mehr.")
    pem, token = schluessel.erzeugen(("pc", "seite"))
    ordner = a.ordner or os.path.dirname(pfad)
    os.makedirs(ordner, exist_ok=True)
    oeffentlich = os.path.join(ordner, "amw-speicher-oeffentlich.pem")
    with open(oeffentlich, "w", encoding="ascii", newline="\n") as f:
        f.write(pem)
    os.makedirs(os.path.dirname(pfad), exist_ok=True)
    with open(pfad + ".neu", "w", encoding="utf-8") as f:
        json.dump({**alt, "art": "libsql", "url": url, "token": token["pc"], "ca": a.ca or "", "abgleich": False}, f, indent=2)
    os.replace(pfad + ".neu", pfad)
    print(f"Öffentlicher Schlüssel für den libSQL-Server: {oeffentlich}")
    print("  Auf den Server kopieren und sqld damit starten: --auth-jwt-key-file <Datei> (bzw. SQLD_AUTH_JWT_KEY_FILE).")
    print(f"Zugang auf diesem PC eingetragen: {url} (Synchronisierung noch aus) – {pfad}")
    print("Schlüssel für die Online-Seite – nur jetzt sichtbar, in deren amw-konfig.php als 'speicher_token' eintragen:")
    print(f"  {token['seite']}")
    print("Dann: Einstellungen › Speicher und Synchronisierung › „Speicher prüfen“, danach Synchronisierung an.")
    print("Hinweis: Diese Schlüssel laufen nicht ab. Ungültig werden sie, wenn du ein neues Paar erzeugst und den neuen öffentlichen"
          " Schlüssel auf dem Server einlegst.")
    return 0


def cmd_web(a, con):
    """Online-Teil (doc/online.md): Seite für den Webhoster bauen, Online-Speicher einrichten, einen Abgleich von Hand."""
    from . import abgleich
    if a.aktion == "sso":
        return _web_sso(a)
    if a.aktion == "bauen":
        quelle = os.path.join(os.path.dirname(__file__), "workbench.html")
        ziel = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "inc", "seite.html")
        with open(quelle, encoding="utf-8") as f, open(ziel, "w", encoding="utf-8", newline="\n") as g:
            g.write(f.read())
        from . import __version__
        with open(os.path.join(os.path.dirname(ziel), "VERSION"), "w", encoding="utf-8", newline="\n") as g:
            g.write(__version__ + "\n")
        hilfe = os.path.join(os.path.dirname(__file__), "hilfe")   # Bilder der Anleitungen (.htaccess lässt hilfe/*.webp durch)
        if os.path.isdir(hilfe):
            import shutil
            ziel_hilfe = os.path.join(os.path.dirname(os.path.dirname(ziel)), "hilfe")
            os.makedirs(ziel_hilfe, exist_ok=True)
            for n in sorted(os.listdir(hilfe)):
                if n.endswith(".webp"):
                    shutil.copyfile(os.path.join(hilfe, n), os.path.join(ziel_hilfe, n))
        from . import hilfen                                         # Schritt-für-Schritt-Hilfen (doc/hilfe/) als Dateien für die Online-Seite
        ziel_hilfe = os.path.join(os.path.dirname(os.path.dirname(ziel)), "hilfe")
        os.makedirs(ziel_hilfe, exist_ok=True)
        hilfen.pruefen()                                             # eine kaputte Hilfe soll hier auffallen, nicht online
        erwartet = set()
        for thema in hilfen.themen():
            for sprache in hilfen.SPRACHEN:
                name = f"{thema}.{sprache}.json"
                erwartet.add(name)
                with open(os.path.join(ziel_hilfe, name), "w", encoding="utf-8", newline="\n") as g:
                    json.dump(hilfen.lesen(thema, sprache), g, ensure_ascii=False, indent=1)
                    g.write("\n")
        for n in os.listdir(ziel_hilfe):                              # Hilfe gestrichen → Datei mit weg
            if n.endswith(".json") and n not in erwartet:
                os.remove(os.path.join(ziel_hilfe, n))
        print(f"gebaut: {ziel} (Version {__version__})")
        return 0
    if a.aktion == "einrichten":
        return web_einrichten(abgleich)
    sp = abgleich.speicher_aus_zugang(nur_wenn_an=False)
    if sp is None:
        raise kern.AmwFehler(f"kein Zugang in {abgleich.zugang_pfad()}")
    ab = abgleich.Abgleich(con, sp, _projekt(con, a))
    if a.aktion == "schema":
        ab.schema()
        namen = [s.split()[5] for s in abgleich.SCHEMA if s.startswith("CREATE TABLE")]
        print(f"Online-Speicher: Tabellen {', '.join(namen)} bereit")
    elif a.aktion == "zweitfaktor-neu":       # Handy weg/neu: beim nächsten Anmelden gibt es wieder einen QR-Code
        sp.ausfuehren([("DELETE FROM zustand WHERE schluessel IN ('totp_geheim', 'totp_letzt')", [])])
        print("Zweiter Faktor zurückgesetzt – beim nächsten Anmelden (Code leer lassen) kommt ein neuer QR-Code")
    elif a.aktion == "einmal":
        ab.schema()
        print(f"Briefkasten: {ab.eingang()} Zeile(n) bearbeitet · Ansichten hochgeladen: {ab.hochladen()}")
    else:
        neu, pc = sp.ausfuehren([("SELECT count(*) FROM eingang WHERE status = 'neu'", []),
                                 ("SELECT wert FROM zustand WHERE schluessel = 'pc_gesehen_utc'", [])])
        an = abgleich.speicher_aus_zugang() is not None
        print(f"Synchronisierung im Dienst: {'an' if an else 'aus'} · PC zuletzt hochgeladen: {_zeit(pc[0][0]) if pc else '–'}"
              f" · Briefkasten offen: {neu[0][0]}")
    return 0


def cmd_dienst(a):
    from . import einrichtung
    from . import einstellungen
    a.port = a.port or einstellungen.wert("port")
    if a.aktion == "status":
        print(einrichtung.status(a.port))
        return 0
    if a.aktion == "vordergrund":                   # zum Ausprobieren ohne geplante Aufgabe; Strg+C beendet
        from . import dienst
        return dienst.main(["--port", str(a.port)])
    fremd = einrichtung.fremde_aufgabe()
    if fremd and a.aktion in ("neustart", "entfernen"):
        raise kern.AmwFehler(fremd)
    if a.aktion == "neustart":                      # z. B. nach geänderten Einstellungen (Zahnrad „Dieser PC“)
        rc, aus = einrichtung.powershell(
            f"$x = Get-ScheduledTask -TaskName '{einrichtung.AUFGABE}' -ErrorAction SilentlyContinue; if ($x) "
            f"{{ Stop-ScheduledTask -TaskName '{einrichtung.AUFGABE}'; Start-Sleep 2; Start-ScheduledTask -TaskName "
            f"'{einrichtung.AUFGABE}'; 'Dienst neu gestartet' }} else {{ 'Dienst ist nicht eingerichtet (amw dienst einrichten)' }}")
        print(aus)
        return rc
    skript = einrichtung.skript_einrichten(a.port) if a.aktion == "einrichten" else einrichtung.skript_entfernen()
    if not a.ja:
        print(f"Würde ausführen (PowerShell, Benutzer {os.environ.get('USERNAME')}) – mit --ja wirklich tun:")
        print()
        print(skript)
        return 0
    rc, aus = einrichtung.powershell(skript)
    print(aus)
    return rc


def cmd_anmelden(a, con):
    """Laufende Sitzung ohne Neustart anmelden (Umschalten): wie der Hook bei startup, aus der eigenen
    Umgebung der Claude-Code-Shell. Der Schlüssel landet nur in der Sitzungsdatei, nie in der Ausgabe."""
    from . import hook
    kennung = _von(a)
    hinweis = hook.anmelden(con, _projekt(con, a), kennung,
                            {"session_id": os.environ.get("CLAUDE_CODE_SESSION_ID"), "cwd": os.getcwd()},
                            ersetzen=a.ersetzen, streng=True)
    if hinweis:
        raise kern.AmwFehler(hinweis)
    ich = hook.claude_prozess(os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET"))
    print(f"{kennung} angemeldet" + (f" ({hook.beschreibung(ich)})" if ich else "")
          + " – der Dienst benachrichtigt diese Sitzung ab jetzt bei neuen Nachrichten")


def cmd_abmelden(a, con):
    kern.abmelden(con, _projekt(con, a), _von(a))
    print(f"{_von(a)} abgemeldet – kein Wecken und kein automatischer Neustart bis zum nächsten `amw anmelden`"
          " (oder Start/Fortsetzen der Sitzung); der Lead ist informiert")


def cmd_hook(a):
    from . import einrichtung
    print("Für .claude/settings.local.json eines Agenten-Ordners (zusammenführen: amw einrichten agenten-ordner <pfad>):")
    print(json.dumps(einrichtung.hook_einstellungen(), ensure_ascii=False, indent=2))
    print()
    print("Im Startbefehl je Agent vor `claude …` setzen (oder nach dem ersten Start: amw anmelden --von <Name>):")
    print(f"  $env:AMW_AGENT = '{a.agent}'")
    return 0


def cmd_sichern(a):
    from . import dokumente
    pid = name = None
    if getattr(a, "projekt", None):                   # ein Projekt als eigene Datenbank (sichern, umziehen)
        con = db.verbinde(nur_lesen=True)
        try:
            pid = db.projekt_id(con, a.projekt)
            name = con.execute("SELECT name FROM projekt WHERE id = ?", (pid,)).fetchone()[0]
        except LookupError as f:
            raise kern.AmwFehler(str(f))
        finally:
            con.close()
    ziel = db.sichern(a.ziel, pid=pid, name=name)
    print(f"gesichert: {ziel}" + (f" (nur Projekt {name} – eine eigene, vollständige AMW-Datenbank)" if pid else ""))
    n = dokumente.sichern(os.path.splitext(ziel)[0] + "-dokumente", nur_aus=ziel if pid else None)   # Ablage daneben
    if n:
        print(f"Dokumente: {n} Datei(en) nach {os.path.splitext(ziel)[0]}-dokumente")
    return 0


def cmd_einrichten(a):
    from . import assistent, einrichtung
    if a.aktion == "assistent":
        try:
            assistent.interaktiv()
        except (EOFError, KeyboardInterrupt):
            print("\nabgebrochen – bis hierher Angelegtes bleibt; `amw einrichten` kann wiederholt werden")
            return 1
        return 0
    if a.aktion == "schnell":
        if not a.projekt_name:
            raise kern.AmwFehler("amw einrichten schnell --projekt-name … [--lead TL] [--agenten CC1,CC2] [--ordner Pfad] …")
        assistent.schnell(a.projekt_name, a.lead, [x.strip() for x in (a.agenten or "").split(",") if x.strip()],
                          os.path.abspath(a.ordner) if a.ordner else None, a.rechte, a.denkstufe, a.mit_dienst,
                          hooks=not a.ohne_hooks, fernsteuerung=a.fernsteuerung,
                          regelwerk={"auswahl": None, "sprache": "de"} if a.grund_regelwerk else None)
        return 0
    if a.aktion == "betriebsart":                         # zeigen oder setzen: amw einrichten betriebsart [pc|server|cloud]
        from . import betriebsart, einstellungen
        if a.pfad:
            try:
                einstellungen.speichern({"betriebsart": a.pfad})
            except ValueError as f:
                raise kern.AmwFehler(str(f))
        art = betriebsart.aktuell()
        print(f"Betriebsart: {betriebsart.NAMEN[art]} ({art})" + ("" if betriebsart.gewaehlt() else " – nicht gewählt, es gilt, was bisher lief"))
        return 0
    if a.aktion == "verbindungen":                        # jede Adresse, zu der diese Installation eine Verbindung aufbaut
        from . import betriebsart, verbindung
        con = db.verbinde() if os.path.exists(db.db_pfad()) else None
        try:
            d = verbindung.erreichbar(con) if a.pruefen else verbindung.liste(con)
        finally:
            if con is not None:
                con.close()
        wer = {"workbench": "Workbench", "speicher": "Online-Speicher", "seite": "Online-Seite", "push": "Benachrichtigung", "ki": "Lokale KI"}
        stufe = {"pc": "dieser PC", "firma": "Firmennetz", "internet": "Internet"}
        print(f"Betriebsart: {betriebsart.NAMEN[d['betriebsart']]}")
        for x in d["zeilen"]:
            zustand = "blockiert" if not x["erlaubt"] else "nur beim Testen" if x["nur_pruefung"] else "ausgeschaltet" if not x["aktiv"] else "erlaubt"
            probe = "" if x.get("erreichbar") is None else "  erreichbar" if x["erreichbar"] else "  NICHT erreichbar"
            name = wer[x["wer"]] + (f" ({x['zusatz']})" if x["zusatz"] else "")
            ziel = f"{x['rechner']}:{x['port']}"
            print(f"  {name:<26} {ziel:<48} {stufe[x['stufe']]:<14} {zustand}{probe}"
                  + ("   ← eingeschaltet, aber in dieser Betriebsart blockiert" if x["aktiv"] and not x["erlaubt"] else ""))
        print("Nicht erfasst: Claude Code und Git verbinden sich selbst mit ihren Diensten.")
        return 1 if d["fehler"] else 0
    if a.aktion == "agenten-ordner":
        if not a.pfad:
            raise kern.AmwFehler("amw einrichten agenten-ordner <pfad> [--projekt <name>] [--nur-zeigen] [--entfernen]")
        if a.entfernen:
            weg = einrichtung.agenten_ordner_entfernen(os.path.abspath(a.pfad), schreiben=not a.nur_zeigen)
            for x in weg or ["keine AMW-Einträge gefunden"]:
                print(("würde entfernen: " if a.nur_zeigen else "entfernt: ") + x if weg else x)
            return 0
        con = db.verbinde()
        try:                                      # ein Ordner gehört zu genau einem Projekt
            projekt = con.execute("SELECT name FROM projekt WHERE id = ?", (db.projekt_fuer(
                con, getattr(a, "projekt", None) or os.environ.get("AMW_PROJEKT")),)).fetchone()["name"]
        except LookupError as f:
            raise kern.AmwFehler(f"{f} – zu welchem Projekt gehört der Ordner?")
        finally:
            con.close()
        try:
            aenderungen = einrichtung.agenten_ordner_einrichten(os.path.abspath(a.pfad), schreiben=not a.nur_zeigen,
                                                                sperren=not a.ohne_sperren, projekt=projekt)
        except ValueError as f:
            raise kern.AmwFehler(str(f))
        if not aenderungen:
            print("schon eingerichtet – nichts zu tun")
        for x in aenderungen:
            print(("würde ergänzen: " if a.nur_zeigen else "ergänzt: ") + x)
        if aenderungen and not a.nur_zeigen:
            print("Wirkt in neuen bzw. fortgesetzten Sitzungen (Hooks) und sofort (Statusline). Sicherung: *.vor-amw-<Datum>")
    return 0


def cmd_push(a):
    from . import push
    if a.aktion == "status":
        cfg = push.oeffentlich()
        print(f"Push {'AN' if cfg['an'] else 'aus'} (seit {cfg.get('seit_utc') or '–'}) · Datei {cfg['datei']}")
        for an in push.ANBIETER:
            c = cfg[an]
            print(f"  {an:<9} {'an ' if c['an'] else 'aus'} " + ", ".join(f"{k}={v}" for k, v in c.items() if k != "an"))
        print("  Ereignisse: " + ", ".join(f"{k} {'an' if v else 'aus'}" for k, v in cfg["ereignisse"].items()))
        r = cfg["ruhe"]
        print(f"  Ruhezeit: {r['von']}–{r['bis']} {'an' if r['an'] else 'aus'} · höchstens {cfg['max_je_stunde']} je Stunde"
              f" · Link {cfg.get('link') or '(lokale Workbench)'}")
        con = db.verbinde(nur_lesen=True)
        try:
            for p in push.protokoll(con, 10):
                print(f"  {_zeit(p['geaendert_utc'])} {p['ergebnis']:<10} {p['titel']}" + (f"  ({p['fehler']})" if p["fehler"] else ""))
        finally:
            con.close()
    elif a.aktion == "probe":
        for an, ergebnis in push.probe(a.wert).items():
            print(f"{an}: {ergebnis}")
    elif a.aktion in ("an", "aus"):
        push.speichern({"an": a.aktion == "an"})
        print(f"Push {a.aktion}" + (" – gemeldet wird nur, was ab jetzt passiert" if a.aktion == "an" else ""))
    elif a.aktion == "ntfy":
        cfg = push.laden()
        kanal = a.kanal or cfg["ntfy"]["topic"] or push.neuer_ntfy_kanal()
        server = (a.server or cfg["ntfy"]["server"]).rstrip("/")
        push.speichern({"ntfy": {"an": True, "topic": kanal, "server": server, "token": a.token or ""}})
        print(f"ntfy an. In der ntfy-App abonnieren: Server {server}, Kanal {kanal}")
        print(f"  (Link: ntfy://{server.split('://', 1)[1]}/{kanal}) – der Kanalname ist geheim wie ein Passwort.")
    elif a.aktion == "pushover":
        if not (a.app_token and a.user_key):
            raise kern.AmwFehler("amw push pushover --app-token … --user-key …")
        push.speichern({"pushover": {"an": True, "app_token": a.app_token, "user_key": a.user_key}})
        print("Pushover an")
    elif a.aktion == "telegram":
        if not a.token:
            raise kern.AmwFehler("amw push telegram --token <Bot-Token> [--chat <ID>]  (ohne --chat: Chat-IDs anzeigen)")
        if not a.chat:
            chats = push.telegram_chats(a.token)
            if not chats:
                print("Keine Chats gefunden – schreib deinem Bot zuerst eine Nachricht, dann erneut.")
            for cid, name in chats.items():
                print(f"Chat {cid} ({name}) → amw push telegram --token … --chat {cid}")
            return 0
        push.speichern({"telegram": {"an": True, "bot_token": a.token, "chat_id": str(a.chat)}})
        print("Telegram an")
    elif a.aktion == "ruhe":
        if a.wert in ("aus", None):
            push.speichern({"ruhe": {"an": False}})
            print("Ruhezeit aus")
        else:
            von, _, bis = a.wert.partition("-")
            push.speichern({"ruhe": {"an": True, "von": von, "bis": bis}})
            print(f"Ruhezeit {von}–{bis}: nur Dringendes (Priorität 5), der Rest danach gesammelt")
    elif a.aktion == "link":
        push.speichern({"link": a.wert or ""})
        print(f"Link: {a.wert or '(lokale Workbench)'}")
    elif a.aktion == "ereignis":
        art, _, wert = (a.wert or "").partition("=")
        if not wert:
            raise kern.AmwFehler("amw push ereignis <art>=an|aus  (Arten: " + ", ".join(push.EREIGNISSE) + ")")
        push.speichern({"ereignisse": {art: wert == "an"}})
        print(f"{art}: {wert}")
    return 0


# --- Aufbau --------------------------------------------------------------------------------------

def parser():
    from . import __version__
    p = Parser(prog="amw", description="Agentenmanagement Workbench")
    p.add_argument("--version", action="version", version=f"AMW {__version__}")
    p.add_argument("--projekt")
    p.add_argument("--von")
    s = p.add_subparsers(dest="cmd", required=True)

    x = s.add_parser("init", help="neue Datenbank anlegen")
    x.add_argument("--projekt", dest="projekt_init", help="gleich ein erstes Projekt anlegen")
    x.set_defaults(f=cmd_init, ohne_db=True)

    x = s.add_parser("projekt", help="Projekte: neu <name> | liste | ordner [<name>] – jedes Projekt ist für sich (eigene Agenten,"
                                     " Regeln, Daten); bequemer: Workbench › Projekt-Auswahl › Neues Projekt")
    x.add_argument("aktion", choices=["neu", "liste", "ordner", "einstellen"])
    x.add_argument("name", nargs="?", help="einstellen: schluessel=wert")
    x.add_argument("--beschreibung")
    x.add_argument("--regeln-von", dest="regeln_von", metavar="PROJEKT",
                   help="neu: die Arbeitsregeln (KR) eines Projekts einmal kopieren – danach getrennt änderbar")
    x.add_argument("--ordner", help="Projektordner (das Repository, in dem die Agenten arbeiten; vorher selbst anlegen)")
    x.set_defaults(f=cmd_projekt)

    x = s.add_parser("agent", help="neu | liste | profil | starten | beenden | startskript | umbenennen ALT NEU")
    x.add_argument("aktion", choices=["neu", "liste", "profil", "starten", "beenden", "startskript", "umbenennen"])
    x.add_argument("kennung", nargs="?")
    x.add_argument("neu_kennung", nargs="?", metavar="neu", help="umbenennen: der neue Name (der alte bleibt als Alias gültig)")
    x.add_argument("--ordner", help="profil: Arbeitsordner")
    x.add_argument("--zusatz", help="profil: weitere Ordner, mit ; getrennt")
    x.add_argument("--denkstufe", help="profil: low | medium | high | xhigh | max")
    x.add_argument("--modell", help="profil: z. B. opus, sonnet (leer = Vorgabe)")
    x.add_argument("--startsatz", help="profil: erste Anweisung einer neuen Sitzung")
    x.add_argument("--rechte", help="profil: vorgabe | auto | umgehen")
    x.add_argument("--fernsteuerung", action="store_true", help="profil: Remote Control an")
    x.add_argument("--keine-fernsteuerung", action="store_true")
    x.add_argument("--neustart", action="store_true", help="profil: nach Absturz automatisch fortsetzen")
    x.add_argument("--kein-neustart", action="store_true")
    x.add_argument("--neu", action="store_true", help="starten: frische Sitzung statt Fortsetzen")
    x.add_argument("--datei", help="startskript: in diese Datei schreiben")
    x.add_argument("--alle", action="store_true", help="startskript: auch Agenten mit Soll aus/ruht (jeder mit Profil-Ordner)")
    x.add_argument("--abstand", type=int, help="startskript: Sekunden zwischen zwei Starts (Vorgabe 20)")
    x.add_argument("--rolle", help="neu/profil: lead = führt das Projekt, leer = führt nicht (ein anderes Wort gilt als Fachgebiet)")
    x.add_argument("--fachgebiet", help="neu/profil: z. B. Code, Grafik, Prüfen (bis 40 Zeichen; leer = keines)")
    x.add_argument("--arbeitsweise", choices=["terminal", "desktop", "chat"],
                   help="neu/profil: Claude Code im Terminal (startet die AMW) | Claude Code in der Desktop-App | Chat über den Dateiaustausch")
    x.add_argument("--zustaendig", help="neu/profil: wofür der Agent zuständig ist")
    x.add_argument("--nicht", help="neu/profil: was der Agent nicht anfasst")
    x.add_argument("--grenzen", help=argparse.SUPPRESS)        # früherer Name von --zustaendig
    x.add_argument("--startbefehl")
    x.add_argument("--ohne-rund", action="store_true", help="bekommt keine Rundschreiben")
    x.set_defaults(f=cmd_agent)

    x = s.add_parser("posten", help="Nachricht schicken: --an CC2 (oder alle, Entwickler) --art auftrag|frage|info|… --kurz …")
    x.add_argument("--an", required=True)
    x.add_argument("--art", required=True)
    x.add_argument("--kurz", required=True)
    x.add_argument("--text")
    x.add_argument("--text-datei")
    x.add_argument("--antwort-auf", type=nummer)
    x.add_argument("--aufgabe", type=nummer)
    x.add_argument("--bis", help="die Meldung erledigt sich von selbst, sobald das erfüllt ist: leitbild | aufgabe (du hast eine)"
                                 " | A<nr> (fertig) | F<nr> (beantwortet)")
    x.add_argument("--bezug", help="worum es geht: A<nr> Aufgabe, F<nr> Frage, D<nr> Dokument, M<nr> Meilenstein, P<nr> Prüfung,"
                                   " L<nr> Lauf, T<nr> Thema, B<nr> Beschluss, @Kennung Agent; ohne: aus --aufgabe oder geerbt"
                                   " von der Nachricht in --antwort-auf")
    x.set_defaults(f=cmd_posten)

    x = s.add_parser("lesen", help="ohne Nummer: offene Liste; mit Nummern: ganze Nachrichten (lesen 16707 16589)")
    x.add_argument("id", type=nummer, nargs="*")
    x.add_argument("--grenze", type=int, default=50)
    x.add_argument("--neu", action="store_true", help="nur Ungelesenes, neueste zuerst")
    x.add_argument("--verlauf", action="store_true", help="die letzten Nachrichten an mich, auch gelesene und erledigte")
    x.set_defaults(f=cmd_lesen)

    x = s.add_parser("erledigt", help="Nachrichten als erledigt markieren: amw erledigt 12 13 | --info [--vor 04.11.]")
    x.add_argument("ids", type=nummer, nargs="*")
    x.add_argument("--bemerkung")
    x.add_argument("--info", action="store_true", help="alle offenen info-Nachrichten an mich erledigen")
    x.add_argument("--vor", help="mit --info: nur ältere als dieses Datum (04.11. oder 2026-11-04)")
    x.add_argument("--fuer", help="Lead: veraltete info/meldung an den Entwickler schließen (--fuer Entwickler --bemerkung \"warum\")")
    x.set_defaults(f=cmd_erledigt)

    x = s.add_parser("aufgabe", help="neu | aendern N | liste | zeige N [--kurz] | start | fertig | … | kriterium N nr |"
                                     " plan N --text | planfrei N [--zurueck --kommentar] | nachtrag N --titel … (Folgearbeit"
                                     " zu einer fertigen Aufgabe)")
    x.add_argument("aktion", choices=["neu", "aendern", "liste", "zeige", "start", "blockiert", "wartet", "fertig", "verwerfen",
                                       "parken", "aktiv", "keine_prio", "pool", "kriterium", "plan", "planfrei", "nachtrag",
                                       "dazwischen"])
    x.add_argument("id", type=nummer, nargs="?")
    x.add_argument("nr", type=int, nargs="?", help="kriterium: Nummer des Kriteriums")
    x.add_argument("--titel")
    x.add_argument("--agent", help="Bearbeiter (auch „Entwickler“ für Schritte des Menschen)")
    x.add_argument("--auftrag")
    x.add_argument("--rang", type=int, default=50)
    x.add_argument("--pruefer")
    x.add_argument("--beleg")
    x.add_argument("--wartet-auf", help="wartet/blockiert: Erklärung als Text (zusätzlich zu --auf)")
    x.add_argument("--auf", help="wartet/blockiert: worauf, als Verweise – F12,A120,L7,CC2,Entwickler,Monitor:<was>"
                                 " (Pflicht; erledigt sich von selbst und benachrichtigt dich)")
    x.add_argument("--erledigt", help="wartet/blockiert: diese Gründe von Hand abhaken, z. B. F12 (allein: Status bleibt)")
    x.add_argument("--bemerkung")
    x.add_argument("--alle", action="store_true")
    x.add_argument("--bogen", type=nummer, help="Planung: gehört zu Meilenstein N")
    x.add_argument("--kriterium", action="append", help="Planung: Abnahmekriterium, mehrfach (ersetzt die Liste)")
    x.add_argument("--schaetzung", type=float, help="Planung: Stunden")
    x.add_argument("--komplexitaet", type=int, help="Planung: 1–10; ab 7 braucht der Schritt einen freigegebenen Plan")
    x.add_argument("--nach", "--abhaengig-von", dest="nach", help="Vorgänger, z. B. 1201,1203 (startbar erst, wenn sie fertig sind)")
    x.add_argument("--verantwortlich", help="Planung: wer abnimmt bzw. Pläne freigibt")
    x.add_argument("--pruefbefehl", help="Planung: wie der Bearbeiter selbst prüft")
    x.add_argument("--dateien", help="Planung: Dateibereich, den er anfassen darf")
    x.add_argument("--anforderungen", help="Planung: abgedeckte Anforderungen, z. B. R1,R3")
    x.add_argument("--zusammenfassung", help="fertig: Pflicht für Schritte in einem Meilenstein; aendern: nachtragen")
    x.add_argument("--ohne-vorgaenger", help="aendern: diese Vorgänger lösen, z. B. 115")
    x.add_argument("--text", help="plan: der Plan")
    x.add_argument("--nein", action="store_true", help="kriterium: wieder als offen markieren")
    x.add_argument("--zurueck", action="store_true", help="planfrei: zurückweisen (mit --kommentar)")
    x.add_argument("--kommentar")
    x.add_argument("--kurz", action="store_true", help="zeige: nur Status, Agent, Titel und Wartegründe")
    x.add_argument("--federfuehrend", help="aendern: wer diese Aufgabe führt (Lead/Entwickler; leer = weg)")
    x.add_argument("--pool", action="store_true", help="neu: in den Eingang (noch in keiner Arbeitsliste)")
    x.add_argument("--grund", help="dazwischen: warum diese Aufgabe vor das laufende Stück muss (Pflicht)")
    x.add_argument("--hinweis", help="fertig: ein Satz für die Versionshinweise, in der Sprache der Nutzer")
    x.add_argument("--gruppe", choices=["neu", "verbessert", "behoben"], help="fertig: Gruppe in den Versionshinweisen")
    x.add_argument("--sofort", action="store_true", help="neu: direkt hinter das laufende Stück des Agenten einplanen statt in den"
                                                          " Eingang (ohne laufendes Stück: wie bisher in die Liste)")
    x.set_defaults(f=cmd_aufgabe)

    x = s.add_parser("thema", help="Design-Dokument je Thema: liste [--suche] | zeige TH12 | neu \"Name\" [--pfleger X] [--stil] |"
                                   " einstellen TH12 --pfleger X | --stil | pflegen TH12 --text-datei … | bestaetigen TH12 |"
                                   " dokument TH12 --dokument D5 [--loesen]")
    x.add_argument("aktion", nargs="?", default="liste", choices=["liste", "zeige", "neu", "einstellen", "pflegen", "bestaetigen",
                                                                  "dokument"])
    x.add_argument("name", nargs="?", help="TH-Nummer oder Name (eindeutiger Anfang reicht)")
    x.add_argument("--pfleger")
    x.add_argument("--stil", action="store_true", help="dieses Thema ist der Projekt-Stil (es gibt höchstens einen)")
    x.add_argument("--kein-stil", action="store_true")
    x.add_argument("--text")
    x.add_argument("--text-datei")
    x.add_argument("--dokument")
    x.add_argument("--loesen", action="store_true")
    x.add_argument("--suche")
    x.add_argument("--grenze", type=int, default=60)
    x.set_defaults(f=cmd_thema)

    x = s.add_parser("termin", help="Terminplaner: neu --titel … --art test|frist|schirm|sonstig --am \"2026-11-06 18:00\""
                                    " [--woechentlich --bis 2026-12-31] [--vorlauf 4] [--bogen N] | liste [--tage 21] | aendern N |"
                                    " absagen N [--am …] | bereit N --text \"was testen\" | kurzliste N (Planen: Lead/Entwickler)")
    x.add_argument("aktion", nargs="?", default="liste", choices=["neu", "liste", "aendern", "absagen", "bereit", "kurzliste"])
    x.add_argument("id", type=nummer, nargs="?")
    x.add_argument("--titel")
    x.add_argument("--art", choices=["test", "frist", "schirm", "sonstig"])
    x.add_argument("--am", help="Ortszeit: JJJJ-MM-TT HH:MM oder TT.MM. HH:MM (absagen/bereit: dieses Vorkommen)")
    x.add_argument("--dauer", type=int, help="Minuten")
    x.add_argument("--woechentlich", action="store_true")
    x.add_argument("--bis", help="wöchentlich bis zu diesem Tag (JJJJ-MM-TT)")
    x.add_argument("--vorlauf", type=float, help="test: Testbuild fertig so viele Stunden vorher (Vorgabe 4)")
    x.add_argument("--bogen", type=nummer, help="Ampel: Prognose dieses Meilensteins gegen die Frist")
    x.add_argument("--notiz")
    x.add_argument("--text", help="bereit: was ist neu, was soll getestet werden")
    x.add_argument("--tage", type=int, default=21)
    x.set_defaults(f=cmd_termin)

    x = s.add_parser("liste", help="Arbeitsliste je Agent: liste [Agent|pool] | ordnen <Agent> A12 A15 … | schieben A15 --vor A12"
                                   " | --nach | --pos N | --oben | --unten (ordnen/schieben: Lead)")
    x.add_argument("wer", nargs="?", help="Agent, pool, ordnen oder schieben")
    x.add_argument("rest", nargs="*", help="ordnen: Agent und Aufgaben-Nummern · schieben: die Aufgabe")
    x.add_argument("--vor", type=nummer)
    x.add_argument("--nach", type=nummer)
    x.add_argument("--pos", type=int)
    x.add_argument("--oben", action="store_true")
    x.add_argument("--unten", action="store_true")
    x.set_defaults(f=cmd_liste)

    x = s.add_parser("frage", help="Fragen an den Entwickler oder Lead: neu | liste [--geparkt] | antworten | nachtrag | verlauf |"
                                    " parken N [--grund] | aufnehmen N | weiterleiten N [--text] (Lead → Entwickler)")
    x.add_argument("aktion", choices=["neu", "liste", "antworten", "nachtrag", "verlauf", "parken", "aufnehmen", "weiterleiten"])
    x.add_argument("id", type=nummer, nargs="?")
    x.add_argument("--an", choices=["entwickler", "tl", "zustaendig"],
                   help="zustaendig: an die Federführung der --aufgabe (sonst Meilenstein, sonst Lead)")
    x.add_argument("--kurz")
    x.add_argument("--worum")
    x.add_argument("--option", action="append", help="neu: 'A=Text' (mehrfach); antworten: Kürzel der Option")
    x.add_argument("--empfehlung")
    x.add_argument("--fundstellen")
    x.add_argument("--geprueft", help="neu: was du vorher in der AMW geprüft hast (Beschlüsse, Fragen, Regeln) – Pflicht bei"
                                      " Fragen an den Entwickler; findet die AMW Treffer, nenne mindestens einen")
    x.add_argument("--aufgabe", type=nummer)
    x.add_argument("--blockiert", action="store_true")
    x.add_argument("--text")
    x.add_argument("--rueckfrage")
    x.add_argument("--grund", help="neu: warum du das empfiehlst; parken/aufnehmen: warum (steht im Verlauf)")
    x.add_argument("--geparkt", action="store_true", help="liste: nur die geparkten")
    x.add_argument("--anhang", action="append", help="neu: Bild/Mockup zu einer Option, 'A=datei.png' oder 'A=D12' (mehrfach) –"
                                                     " erscheint als Variante zum Anklicken, auch online")
    x.set_defaults(f=cmd_frage)

    x = s.add_parser("halt", help="alle oder einen Agenten anhalten")
    x.add_argument("--fuer", default="alle")
    x.add_argument("--text", required=True)
    x.set_defaults(f=cmd_halt)

    x = s.add_parser("weiter", help="Halt aufheben")
    x.add_argument("--fuer", default="alle")
    x.set_defaults(f=cmd_weiter)

    x = s.add_parser("taetigkeit", help="was ich gerade tue (zeigt die Workbench), z. B. taetigkeit \"A12 Login-Formular\"")
    x.add_argument("text", nargs="*")
    x.add_argument("--aufgabe", type=nummer)
    x.set_defaults(f=cmd_taetigkeit)

    x = s.add_parser("kontext", help="Startinformationen für einen Agenten")
    x.add_argument("agent", nargs="?")
    x.set_defaults(f=cmd_kontext)

    x = s.add_parser("regeln", help="alle geltenden Regeln (Arbeits- und Projektregeln)")
    x.set_defaults(f=cmd_regeln)

    x = s.add_parser("suche", help="Volltext über Aufgaben, Beschlüsse, Fragen, Deine Worte, Nachrichten, Dokumente: amw suche Modem")
    x.add_argument("text", nargs="+")
    x.add_argument("--art", action="append", choices=["aufgabe", "beschluss", "frage", "wortlaut", "nachricht", "dokument"],
                   help="nur diese Art (mehrfach)")
    x.add_argument("--grenze", type=int, default=15)
    x.add_argument("--wissen", action="store_true", help="dazu: passende Beschlüsse/Fragen/Regeln wie bei frage neu")
    x.set_defaults(f=cmd_suche)

    x = s.add_parser("zeige", help="Einträge ganz lesen: amw zeige B5 F12 A120 W3 16000 D5 KR3 PR4 (Nachricht ohne #: in der Shell beginnt mit # ein Kommentar)")
    x.add_argument("refs", nargs="+")
    x.set_defaults(f=cmd_zeige)

    x = s.add_parser("leitbild", help="Projektziel, Kennzahlen, Nicht-Ziele, Prinzipien, Definition of Done: zeigen | setzen")
    x.add_argument("aktion", nargs="?", choices=["zeigen", "setzen"], default="zeigen")
    x.add_argument("--ziel")
    x.add_argument("--kennzahl", action="append", help="mehrfach; ersetzt die Liste")
    x.add_argument("--nicht-ziel", action="append", help="mehrfach; ersetzt die Liste")
    x.add_argument("--prinzip", action="append", help="\"Text|Prüffrage\", mehrfach; ersetzt die Liste")
    x.add_argument("--dod", action="append", help="Definition of Done, mehrfach; ersetzt die Liste")
    x.set_defaults(f=cmd_leitbild)

    x = s.add_parser("bogen", help="Meilensteine: liste | neu | zeigen N | aendern N | status N aktiv|fertig|geplant|verworfen")
    x.add_argument("aktion", choices=["liste", "neu", "zeigen", "aendern", "status"])
    x.add_argument("id", type=nummer, nargs="?")
    x.add_argument("wert", nargs="?", help="status: aktiv | fertig | geplant | verworfen")
    x.add_argument("--titel")
    x.add_argument("--ziel")
    x.add_argument("--abnahme", help="prüfbares Abnahmekriterium")
    x.add_argument("--zieldatum", help="JJJJ-MM-TT")
    x.add_argument("--federfuehrend", help="aendern: wer den Meilenstein führt (Lead/Entwickler; leer = weg)")
    x.add_argument("--nr", type=int, help="Reihenfolge")
    x.add_argument("--grund", help="nötig, wenn das Zieldatum nach der Baseline geändert wird")
    x.add_argument("--erzwingen", action="store_true")
    x.set_defaults(f=cmd_bogen)

    x = s.add_parser("spec", help="Spezifikation je Meilenstein: zeigen N [teil] | schreiben N teil --text/--datei | vorlegen N teil |"
                                  " frei N teil | zurueck N teil --kommentar  (teil: anforderungen | entwurf | schritte)")
    x.add_argument("aktion", choices=["zeigen", "schreiben", "vorlegen", "frei", "zurueck"])
    x.add_argument("bogen", type=nummer)
    x.add_argument("teil", nargs="?", choices=["anforderungen", "entwurf", "schritte"])
    x.add_argument("--text")
    x.add_argument("--datei")
    x.add_argument("--kommentar")
    x.set_defaults(f=cmd_spec)

    x = s.add_parser("schritt", help="naechster [--nehmen]: nächster bereiter Schritt (aktiver Meilenstein, ohne offene Vorgänger)")
    x.add_argument("aktion", choices=["naechster"])
    x.add_argument("--nehmen", action="store_true", help="gleich übernehmen (Bearbeiter = du, Status läuft)")
    x.set_defaults(f=cmd_schritt)

    x = s.add_parser("risiko", help="liste | neu --titel … | setzen N --status …")
    x.add_argument("aktion", choices=["liste", "neu", "setzen"])
    x.add_argument("id", type=nummer, nargs="?")
    x.add_argument("--titel")
    x.add_argument("--ursache")
    x.add_argument("--wirkung")
    x.add_argument("--w", type=int, help="Wahrscheinlichkeit 1–5")
    x.add_argument("--a", type=int, help="Auswirkung 1–5")
    x.add_argument("--strategie", choices=["vermeiden", "mindern", "uebertragen", "akzeptieren"])
    x.add_argument("--massnahme")
    x.add_argument("--verantwortlich")
    x.add_argument("--ausloeser")
    x.add_argument("--status", choices=["offen", "eingetreten", "erledigt"])
    x.add_argument("--bogen", type=nummer)
    x.set_defaults(f=cmd_risiko)

    x = s.add_parser("rueckblick", help="Rückblick je Meilenstein: amw rueckblick <bogen> [--gut … --schlecht … --massnahme … --gelernt …]"
                                        " | --uebernehmen <nr> --als aufgabe|beschluss")
    x.add_argument("bogen", type=nummer, nargs="?")
    for art in ("gut", "schlecht", "massnahme", "gelernt"):
        x.add_argument("--" + art)
    x.add_argument("--uebernehmen", type=int, help="Nummer eines Maßnahmen-Eintrags")
    x.add_argument("--als", choices=["aufgabe", "beschluss"], default="aufgabe")
    x.add_argument("--agent", help="Bearbeiter, wenn eine Maßnahme zur Aufgabe wird")
    x.set_defaults(f=cmd_rueckblick)

    x = s.add_parser("verlauf", help="was passiert ist: amw verlauf [--stunden 24] [--agent CC1] [--art erledigt --art pruefung] [--zusammenfassung]")
    x.add_argument("--stunden", type=int, default=24)
    x.add_argument("--agent")
    x.add_argument("--art", action="append", choices=["nachricht", "erledigt", "lauf", "pruefung", "frage", "beschluss", "plan", "sitzung",
                                                       "dokument"])
    x.add_argument("--grenze", type=int, default=200)
    x.add_argument("--zusammenfassung", action="store_true", help="nur Zahlen")
    x.set_defaults(f=cmd_verlauf)

    x = s.add_parser("plan", help="pruefen (Lücken mit Bedeutung und Abhilfe) | akzeptieren <schlüssel> --grund … | wieder <schlüssel>"
                                  " | prognose (P50/P85 je Schritt und Meilenstein) | status (Ampel je Dimension)")
    x.add_argument("aktion", choices=["pruefen", "prognose", "status", "akzeptieren", "wieder"])
    x.add_argument("schluessel", nargs="?", help="akzeptieren/wieder: Schlüssel des Befunds, z. B. bogen_ohne_zieldatum:B3")
    x.add_argument("--grund", help="akzeptieren: warum es so in Ordnung ist")
    x.add_argument("--kurz", action="store_true", help="pruefen: nur eine Zeile je Befund")
    x.set_defaults(f=cmd_plan)

    x = s.add_parser("lauf", help="Rechen-Läufe: start [--warten] prüft Halt, Schirm, Speicher je Lauf, zwei Spuren (Grafikkarte/"
                                  "Schirm: einer zur Zeit; schwere ohne Fenster: parallel bis cpu_laeufe, je Agent einer), Warteschlange · warte <nr> blockiert, bis er dran ist · zeige <nr> mit Wartegrund ·"
                                  " ausfuehren --beschreibung … [--schirm] [--ergebnis datei] -- <befehl …> (einreihen, warten,"
                                  " starten, rc durchreichen, Ende melden; bei Schirm zu den eigenen Befehl beenden)")
    x.add_argument("aktion", choices=["start", "ende", "liste", "vorziehen", "zeige", "warte", "ausfuehren"])
    x.add_argument("id", type=nummer, nargs="?")
    x.add_argument("--warten", action="store_true", help="ist der Platz belegt: NUR einreihen (noch nicht rechnen!) statt"
                                                         " ablehnen; Freigabe benachrichtigt dich – oder danach: amw lauf warte <nr>")
    x.add_argument("--hoechstens", type=float, help="warte: nach so vielen Minuten aufgeben (rc 3), Lauf bleibt eingereiht ·"
                                                    " ausfuehren: dann aus der Schlange nehmen (rc 200)")
    x.add_argument("--frist", type=float, help="ausfuehren: der Befehl darf so viele Minuten laufen, dann Ende (rc 124)")
    x.add_argument("--dauer", type=float, help="erwartete Dauer in Minuten; doppelt so lang → Warnung an den Lead")
    x.add_argument("--braucht-gb", dest="braucht_gb", type=float, metavar="GB",
                   help="start/ausfuehren: geschätzter Arbeitsspeicher dieses Laufs (sonst Rezept, sonst die Grenze des Projekts)")
    x.add_argument("--braucht-vram-gb", dest="braucht_vram_gb", type=float, metavar="GB", help="start/ausfuehren: benötigter Grafikspeicher")
    x.add_argument("--braucht-platte-gb", dest="braucht_platte_gb", type=float, metavar="GB",
                   help="start/ausfuehren: benötigter freier Platz auf dem Laufwerk des Projekts")
    x.add_argument("--beschreibung")
    x.add_argument("--rezept")
    x.add_argument("--leicht", action="store_true", help="kein schwerer Lauf (keine Speicher-Grenze)")
    x.add_argument("--schirm", action="store_true")
    x.add_argument("--gpu", action="store_true", help="belegt die Grafikkarte: PC-weit nur ein GPU-Lauf zur Zeit"
                                                     " (auch KI-Aufträge; ein Lauf mit Fenster wartet ebenfalls)")
    x.add_argument("--aufgabe", type=nummer)
    x.add_argument("--rc", type=int)
    x.add_argument("--ergebnis", help="ende: Ergebnis-Text · ausfuehren: Datei für die Ausgabe des Befehls")
    x.add_argument("--abgebrochen", action="store_true")
    x.add_argument("--grenze", type=int, default=20)
    x.set_defaults(f=cmd_lauf)

    x = s.add_parser("benutzer", help="Benutzer der Online-Seite (nur der Mensch): neu NAME --rolle … [--projekte A,B] | liste |"
                                      " aendern NAME | sperren NAME | entsperren NAME")
    x.add_argument("aktion", nargs="?", default="liste", choices=["neu", "liste", "aendern", "sperren", "entsperren", "freischalten"])
    x.add_argument("--stunden", type=int, default=24, help="freischalten: so lange gilt der Code (1–168)")
    x.add_argument("name", nargs="?")
    x.add_argument("--rolle", choices=["leser", "bearbeiter", "projekt_admin", "system_admin"])
    x.add_argument("--projekte", help="Namen der Projekte, mit Komma getrennt")
    x.add_argument("--anzeige")
    x.add_argument("--email")
    x.set_defaults(f=cmd_benutzer)

    x = s.add_parser("rechner", help="Der Rechner auf einen Blick: Arbeitsspeicher, was außerhalb der Warteschlange Speicher belegt,"
                                     " freier Platz je Laufwerk, Aufräumvorschläge für alte Sicherungen (nur Anzeige)")
    x.set_defaults(f=cmd_rechner)

    x = s.add_parser("schirm", help="Schirm-Schalter: zeige | frei --grund … [--bis HH:MM] (Entwickler/Lead) | zu [--grund …] (alle)")
    x.add_argument("aktion", nargs="?", default="zeige", choices=["zeige", "frei", "zu"])
    x.add_argument("--grund")
    x.add_argument("--bis", help="frei: geht zu dieser Ortszeit von selbst zu, z. B. 07:00 oder \"2026-11-05 07:00\"")
    x.add_argument("--verlauf", action="store_true", help="zeige: die letzten Wechsel")
    x.add_argument("--grenze", type=int, default=20)
    x.add_argument("--quelle", default="cli", choices=["cli", "bruecke"], help=argparse.SUPPRESS)
    x.set_defaults(f=cmd_schirm)

    x = s.add_parser("server", help="Projekt-Server überwachen: anmelden | abmelden | liste | pruefen")
    x.add_argument("aktion", choices=["anmelden", "abmelden", "liste", "pruefen"])
    x.add_argument("name", nargs="?")
    x.add_argument("--port", type=int)
    x.add_argument("--start", help="Startbefehl, z. B. \"pythonw C:/pfad/server.py --port 8766\"")
    x.add_argument("--ordner", help="Arbeitsordner für den Startbefehl")
    x.add_argument("--neustart", action="store_true", help="bei Ausfall automatisch neu starten")
    x.add_argument("--zustaendig", help="wer bei Ausfall benachrichtigt wird (Vorgabe: du)")
    x.set_defaults(f=cmd_server)

    x = s.add_parser("pruefung", help="Prüfbitte je Stand (SHA), Ergebnis grün/rot")
    x.add_argument("aktion", choices=["bitte", "gruen", "rot", "ist-gruen", "liste"])
    x.add_argument("id", type=nummer, nargs="?")
    x.add_argument("--pruefer")
    x.add_argument("--zweig")
    x.add_argument("--sha")
    x.add_argument("--punkte")
    x.add_argument("--aufgabe", type=nummer)
    x.add_argument("--bemerkung")
    x.add_argument("--alle", action="store_true")
    x.set_defaults(f=cmd_pruefung)
    x = s.add_parser("freigabe", help="Merge-OK (Lead/Entwickler): freigabe merge A<nr> [--zweig z] [--zurueck] – Abnahme-Kette:"
                                      " nach grüner Prüfung geht die Merge-Bitte von selbst an den Merge-Dienst")
    x.add_argument("was", choices=["merge"])
    x.add_argument("aufgabe", type=nummer)
    x.add_argument("--zweig", help="nur für diesen Zweig")
    x.add_argument("--zurueck", action="store_true", help="OK zurücknehmen")
    x.set_defaults(f=cmd_freigabe)

    x = s.add_parser("hinweis", help="Anweisung an einen Agenten oder alle (z. B. „keine Rechen-Jobs“)")
    x.add_argument("aktion", choices=["setzen", "aufheben"])
    x.add_argument("id", type=nummer, nargs="?")
    x.add_argument("--fuer", default="alle")
    x.add_argument("--text")
    x.add_argument("--bis", help="UTC, z. B. 2026-11-02T06:00:00Z")
    x.set_defaults(f=cmd_hinweis)

    x = s.add_parser("rezept", help="Lauf-Rezepte als Daten")
    x.add_argument("aktion", choices=["setzen", "zeige", "liste"])
    x.add_argument("name", nargs="?")
    x.add_argument("--befehl")
    x.add_argument("--beschreibung")
    x.add_argument("--schirm", action="store_true")
    x.add_argument("--speicher", type=float)
    x.add_argument("--leicht", action="store_true")
    x.add_argument("--gpu", action="store_true", help="Läufe mit diesem Rezept belegen die Grafikkarte")
    x.set_defaults(f=cmd_rezept)

    x = s.add_parser("ki", help="Lokale KIs (PC-weit): liste | neu|aendern <ki> (nur am PC) | modell <ki> <name> | freigeben|sperren"
                                " <ki> <modell> | vorlage <ki> <name> --datei | recht <ki> --wer | auftrag <ki> --prompt … |"
                                " zeige L<nr> | pruefen | nachweis | vermerk D<nr> --art … | fenster")
    x.add_argument("aktion", nargs="?", default="liste", choices=["liste", "neu", "aendern", "modell", "freigeben", "sperren",
                                                                  "vorlage", "recht", "auftrag", "zeige", "pruefen", "nachweis",
                                                                  "vermerk", "fenster"])
    x.add_argument("name", nargs="?", help="die KI (z. B. ollama, comfyui) · zeige: Lauf-Nummer L812")
    x.add_argument("teil", nargs="?", help="modell/freigeben/sperren: das Modell · vorlage: Name der Vorlage")
    x.add_argument("--art", help="neu: " + " | ".join(("sprache", "bild", "ton", "3d", "video", "sonstig"))
                   + " · vermerk: ausgewaehlt | verworfen | nachbearbeitet")
    x.add_argument("--schnittstelle", help="neu: ollama | comfyui | befehl (eigenes Programm ohne Dienst-Schnittstelle, z. B."
                                         " eine Ton-KI in Python: eintragen, Recht und Modell-Freigabe wie sonst; rechnen über"
                                         " amw lauf ausfuehren --gpu)")
    x.add_argument("--endpunkt", help="neu: nur lokal, z. B. http://127.0.0.1:8188 (Vorgabe je Schnittstelle)")
    x.add_argument("--version")
    x.add_argument("--lizenz")
    x.add_argument("--ablage", help="neu: Ordner der Installation/Modelle")
    x.add_argument("--start", help="neu/aendern: Startbefehl ohne Fenster (der Dienst startet die KI, wenn sie nicht antwortet)")
    x.add_argument("--ordner", help="neu/aendern: Arbeitsordner für den Startbefehl")
    x.add_argument("--vram", type=float, help="GB Grafikspeicher (Richtwert/Probe)")
    x.add_argument("--abschalten", action="store_true", help="aendern: KI nicht mehr beauftragen")
    x.add_argument("--einschalten", action="store_true")
    x.add_argument("--datei", help="modell: Dateiname wie in der Vorlage · vorlage: API-JSON (ComfyUI: Export (API))")
    x.add_argument("--sha256")
    x.add_argument("--quelle", help="modell: URL")
    x.add_argument("--kommerziell", choices=["ja", "nein", "registrierung", "unklar"])
    x.add_argument("--nutzungsregeln", action="store_true", help="modell: Lizenz mit Nutzungsregeln (z. B. Open RAIL++-M)"
                                                                 " – frei gibt dann nur der Entwickler")
    x.add_argument("--ohne-nutzungsregeln", action="store_true")
    x.add_argument("--sekunden", type=float, help="modell: Probe, Sekunden je Auftrag")
    x.add_argument("--notiz")
    x.add_argument("--grund", help="freigeben/sperren: Begründung (sperren: Pflicht)")
    x.add_argument("--beschreibung")
    x.add_argument("--wer", help="recht: alle | rolle:<rolle> | <Name>")
    x.add_argument("--entziehen", action="store_true")
    x.add_argument("--modell")
    x.add_argument("--vorlage")
    x.add_argument("--prompt")
    x.add_argument("--prompt-datei")
    x.add_argument("--negativ")
    x.add_argument("--seed", type=int)
    x.add_argument("--anzahl", type=int, default=1)
    x.add_argument("--breite", type=int)
    x.add_argument("--hoehe", type=int)
    x.add_argument("--bild", help="auftrag: Eingabebild als Dokument, z. B. D96")
    x.add_argument("--parameter", help="auftrag: JSON, z. B. {\"temperature\": 0.2, \"system\": \"…\"}")
    x.add_argument("--titel")
    x.add_argument("--aufgabe", type=nummer)
    x.add_argument("--bogen", type=nummer)
    x.add_argument("--frist", type=float, help="auftrag: höchstens so viele Minuten rechnen (Vorgabe 60)")
    x.add_argument("--nachts", action="store_true", help="auftrag: erst im KI-Fenster starten (Vorgabe 22–06 Uhr), nie vor einem"
                                                         " Testtermin – eilt nicht, belegt die Grafikkarte nicht, während du am PC bist")
    x.add_argument("--text", help="vermerk: was von Hand nachbearbeitet wurde bzw. warum ausgewählt/verworfen")
    x.add_argument("--alle", action="store_true", help="nachweis: auch archivierte und gelöschte Dokumente")
    x.set_defaults(f=cmd_ki)

    for name, f, hilfe in (("wortlaut", cmd_wortlaut, "Aussage des Entwicklers wörtlich erfassen"),
                           ("beschluss", cmd_beschluss, "Beschluss anlegen (optional einen alten ersetzen)"),
                           ("regel", cmd_regel, "Regel anlegen/ändern – nur mit Beschluss")):
        x = s.add_parser(name, help=hilfe)
        x.add_argument("--text")
        x.add_argument("--text-datei")
        x.set_defaults(f=f)
        if name == "wortlaut":
            x.add_argument("--kanal", default="chat-tl")
            x.add_argument("--zeit", help="UTC der Aussage")
            x.add_argument("--bemerkung")
        elif name == "beschluss":
            x.add_argument("aktion", nargs="?", default="neu", choices=["neu", "ueberholt", "unklar", "gilt", "thema"],
                           help="neu (Vorgabe) | ueberholt B12 [--durch B30] | unklar B12 | gilt B12 | thema B12 --thema …")
            x.add_argument("nr", type=nummer, nargs="?")
            x.add_argument("--durch", type=nummer, help="ueberholt: ersetzt durch diesen Beschluss")
            x.add_argument("--stichwort")
            x.add_argument("--quelle")
            x.add_argument("--thema", help="Pflicht, sobald es Themen gibt: TH-Nr. oder Name (eindeutiger Anfang reicht)")
            x.add_argument("--neues-thema", action="store_true", help="--thema gibt es noch nicht: neu anlegen")
            x.add_argument("--zeit")
            x.add_argument("--wortlaut")
            x.add_argument("--wortlaut-text", help="Aussage des Entwicklers wörtlich: wird im selben Zug als W… erfasst und verknüpft"
                                                   " (keine vorhergesagte W-Nummer)")
            x.add_argument("--wortlaut-kanal", default="chat-tl")
            x.add_argument("--wortlaut-zeit", help="UTC der Aussage")
            x.add_argument("--aufgaben")
            x.add_argument("--ersetzt", type=nummer)
        else:
            x.add_argument("--ebene", choices=["arbeit", "projekt"], required=True)
            x.add_argument("--nr", type=int, required=True)
            x.add_argument("--beschluss", type=int, required=True)
            x.add_argument("--teil")

    x = s.add_parser("dokument", help="Ergebnisse ablegen und finden: ablegen <datei> | version <nr> <datei> | liste | zeigen <nr>"
                                      " | kommentar|ueberarbeiten <nr> --text … | zuordnen <nr> | archivieren|wiederherstellen <nr>"
                                      " | online|offline <nr> | loeschen <nr> --ja | einsammeln <ordner> [--melden]"
                                      " | einsammeln --uebernehmen --frage <nr>")
    x.add_argument("aktion", choices=["ablegen", "version", "liste", "zeigen", "kommentar", "ueberarbeiten", "zuordnen",
                                      "archivieren", "wiederherstellen", "online", "offline", "loeschen", "einsammeln"])
    x.add_argument("nr", nargs="?", help="ablegen: die Datei; einsammeln: der Ordner; sonst Nummer des Dokuments (D12 oder 12)")
    x.add_argument("pfad", nargs="?", help="version: die neue Datei")
    x.add_argument("--datei", help="statt der Positionsangabe (Dateiaustausch: nur aus eingang-tl/)")
    x.add_argument("--titel")
    x.add_argument("--art", choices=["ergebnis", "bericht", "entwurf", "mockup", "bild", "quelle"])
    x.add_argument("--notiz", help="was diese Version ist bzw. was sich geändert hat")
    for k in ("bogen", "aufgabe", "frage", "beschluss"):
        x.add_argument("--" + k, help=f"Bezug: {k} (Nummer)")
    x.add_argument("--loesen", action="store_true", help="zuordnen: Bezug entfernen")
    x.add_argument("--online", action="store_true", help="ablegen: Datei auch online zeigen (Texte sind es immer)")
    x.add_argument("--agent", help="liste: nur von diesem Agenten")
    x.add_argument("--suche", help="liste: in Titel und Text suchen")
    x.add_argument("--alle", action="store_true", help="liste: auch archivierte und gelöschte")
    x.add_argument("--text", help="kommentar/ueberarbeiten: was zu sagen ist")
    x.add_argument("--ja", action="store_true", help="loeschen: bestätigen")
    x.add_argument("--melden", action="store_true", help="einsammeln: Liste als Dokument ablegen und den Entwickler fragen")
    x.add_argument("--uebernehmen", action="store_true", help="einsammeln: nach der Antwort auf --frage übernehmen")
    x.add_argument("--nur", action="append", help="einsammeln --uebernehmen: nur diese Ablage (Unterordner), mehrfach")
    x.set_defaults(f=cmd_dokument)

    x = s.add_parser("notiz", help="gepflegte Notizen (Schlüssel/Wert)")
    x.add_argument("aktion", choices=["setzen", "zeige", "entfernen"])
    x.add_argument("schluessel", nargs="*", help="entfernen: mehrere möglich")
    x.add_argument("--beschluss", help="entfernen ohne Lead-Rolle: Nummer eines geltenden Beschlusses (z. B. B5)")
    x.add_argument("--text")
    x.add_argument("--text-datei")
    x.add_argument("--suche", help="zeige: nur Notizen, deren Schlüssel oder Text alle Wörter enthält (z. B. CC5, A1162)")
    x.set_defaults(f=cmd_notiz)

    x = s.add_parser("dienst", help="Dienst als geplante Windows-Aufgabe: einrichten | entfernen | status | neustart |"
                                    " vordergrund (ohne Aufgabe in diesem Fenster, zum Ausprobieren)")
    x.add_argument("aktion", choices=["einrichten", "entfernen", "status", "neustart", "vordergrund"])
    x.add_argument("--port", type=int, default=None, help="Vorgabe: Zahnrad › Dieser PC (8780)")
    x.add_argument("--ja", action="store_true", help="wirklich ausführen (sonst nur anzeigen)")
    x.set_defaults(f=cmd_dienst, ohne_db=True)

    x = s.add_parser("web", help="Online-Teil: einrichten (Turso-Zugang, einmal) | status | einmal (Synchronisierung) | zweitfaktor-neu | bauen | schema"
                                 " | sso [--aussteller URL --client-id ID --an|--aus] (Firmen-Anmeldung; Geheimnis nur auf der Online-Seite)")
    x.add_argument("aktion", choices=["einrichten", "bauen", "schema", "einmal", "status", "zweitfaktor-neu", "sso"])
    x.add_argument("--aussteller", help="sso: Aussteller (Issuer), z. B. https://login.microsoftonline.com/<Mandanten-ID>/v2.0")
    x.add_argument("--client-id", dest="client_id", help="sso: Anwendungs-ID (Client-ID) aus der App-Registrierung")
    x.add_argument("--an", action="store_true", help="sso: Knopf „Mit Firmenkonto anmelden“ zeigen")
    x.add_argument("--aus", action="store_true", help="sso: Firmen-Anmeldung ausschalten")
    x.set_defaults(f=cmd_web)

    x = s.add_parser("speicher", help="Eigener Online-Speicher (libSQL-Server im Firmennetz): schluessel --url https://… "
                                      "[--ca firma.pem] [--ordner …] [--ersetzen] – Schlüsselpaar und Token erzeugen, Zugang am PC eintragen")
    x.add_argument("aktion", choices=["schluessel"])
    x.add_argument("--url", help="Adresse des libSQL-Servers, z. B. https://amw-db.firma.lan (http:// nur im Firmennetz)")
    x.add_argument("--ca", help="Zertifikat der Firmen-CA (PEM), wenn Windows das Zertifikat des Servers nicht kennt")
    x.add_argument("--ordner", help="wohin der öffentliche Schlüssel kommt (Vorgabe: neben dem Zugang dieses PCs)")
    x.add_argument("--ersetzen", action="store_true", help="einen schon eingetragenen Online-Speicher ersetzen")
    x.set_defaults(f=cmd_speicher, ohne_db=True)


    x = s.add_parser("anmelden", help="laufende Sitzung beim Dienst anmelden (ohne Neustart)")
    x.add_argument("--ersetzen", action="store_true", help="eine noch lebende andere Sitzung mit demselben Namen ablösen")
    x.set_defaults(f=cmd_anmelden)

    x = s.add_parser("abmelden", help="Sitzung ruht: nicht mehr benachrichtigen, nicht automatisch neu starten (bis anmelden)")
    x.set_defaults(f=cmd_abmelden)

    x = s.add_parser("einrichten", help="ohne Angabe: geführte Einrichtung (fragt nach) | schnell --projekt-name … (ohne Fragen) |"
                                        " agenten-ordner <pfad> (Hooks, Statusline-Anbindung, Sperren) | betriebsart [pc|server|cloud] |"
                                        " verbindungen [--pruefen] (jede Adresse, zu der die AMW eine Verbindung aufbaut)")
    x.add_argument("aktion", nargs="?", choices=["assistent", "schnell", "agenten-ordner", "betriebsart", "verbindungen"], default="assistent")
    x.add_argument("pfad", nargs="?", help="agenten-ordner: der Ordner | betriebsart: pc, server oder cloud (ohne Angabe: zeigen)")
    x.add_argument("--pruefen", action="store_true", help="verbindungen: je erlaubter Adresse den Verbindungsaufbau testen")
    x.add_argument("--nur-zeigen", action="store_true")
    x.add_argument("--ohne-sperren", action="store_true", help="keine Sperr-Regeln (Ordner dessen, der den Dienst betreut)")
    x.add_argument("--projekt-name", help="schnell: Name des Projekts")
    x.add_argument("--lead", default="TL", help="schnell: Name des Lead-Agenten (leer = keiner)")
    x.add_argument("--agenten", default="CC1", help="schnell: Namen der Agenten, mit Komma")
    x.add_argument("--ordner", help="schnell: Projektordner der Agenten")
    x.add_argument("--rechte", default="vorgabe", choices=["vorgabe", "auto", "umgehen"])
    x.add_argument("--denkstufe", choices=["low", "medium", "high", "xhigh", "max"])
    x.add_argument("--mit-dienst", action="store_true", help="schnell: Dienst als geplante Aufgabe einrichten")
    x.add_argument("--ohne-hooks", action="store_true", help="schnell: Projektordner nicht anfassen")
    x.add_argument("--fernsteuerung", action="store_true", help="schnell: Remote Control für die Agenten an (Vorgabe aus)")
    x.add_argument("--grund-regelwerk", dest="grund_regelwerk", action="store_true",
                   help="schnell: das mitgelieferte Grund-Regelwerk übernehmen (Regeln, Definition of Done, Version 0.1.0)")
    x.add_argument("--entfernen", action="store_true", help="agenten-ordner: AMW-Einträge wieder herausnehmen")
    x.set_defaults(f=cmd_einrichten, ohne_db=True)

    x = s.add_parser("befehle", help="Befehlsreferenz als Markdown (für doc/befehle.md)")
    x.set_defaults(f=lambda a: print(befehle_markdown(), end="") or 0, ohne_db=True)

    x = s.add_parser("sichern", help="Sicherung der Datenbank (vollständige Kopie, auch während des Betriebs); mit --projekt <name>"
                                     " nur dieses Projekt als eigene Datenbank (z. B. zum Umziehen auf einen anderen Rechner)")
    x.add_argument("--ziel", help="Datei (*.db) oder Ordner (Vorgabe: sicherung-<Datum-Zeit>.db neben der Datenbank)")
    x.set_defaults(f=cmd_sichern, ohne_db=True)

    x = s.add_parser("push", help="Benachrichtigungen aufs Handy: status | probe | an | aus | ntfy | pushover | telegram |"
                                  " ruhe 22:00-07:00|aus | link URL | ereignis art=an|aus")
    x.add_argument("aktion", choices=["status", "probe", "an", "aus", "ntfy", "pushover", "telegram", "ruhe", "link", "ereignis"])
    x.add_argument("wert", nargs="?", help="ruhe: 22:00-07:00 oder aus · link: URL · ereignis: frage=aus · probe: Anbieter")
    x.add_argument("--kanal", help="ntfy: eigener Kanalname (sonst zufällig)")
    x.add_argument("--server", help="ntfy: eigener Server (https://…)")
    x.add_argument("--token", help="ntfy-Zugangstoken bzw. Telegram-Bot-Token")
    x.add_argument("--chat", help="Telegram: Chat-ID")
    x.add_argument("--app-token", help="Pushover: App-Token")
    x.add_argument("--user-key", help="Pushover: Benutzerschlüssel")
    x.set_defaults(f=cmd_push, ohne_db=True)

    x = s.add_parser("hook", help="zeigt die Einstellungen für einen Agenten-Projektordner (schreibt nichts)")
    x.add_argument("aktion", choices=["zeige"])
    x.add_argument("--agent", default="CC1", help="nur für die Beispielzeile des Startbefehls")
    x.set_defaults(f=cmd_hook, ohne_db=True)

    x = s.add_parser("release", help="Versionshinweise: je Merge eine Zeile, Version fasst zusammen")
    x.add_argument("aktion", choices=["merge", "version", "liste", "entwurf"])
    x.add_argument("--oeffentlich-datei", help="version: eigener Text für alle statt des Entwurfs (Markdown)")
    x.add_argument("--titel")
    x.add_argument("--commit")
    x.add_argument("--version")
    x.add_argument("--aufgaben")
    x.add_argument("--text")
    x.add_argument("--text-datei")
    x.set_defaults(f=cmd_release)

    # --von/--projekt auch hinter dem Befehl (`amw lesen --von CC1`); SUPPRESS lässt sonst den Wert von vorn stehen
    for unter in s.choices.values():
        for name in ("--von", "--projekt"):
            if name not in unter._option_string_actions:
                unter.add_argument(name, default=argparse.SUPPRESS)
    return p


def befehle_markdown():
    """Befehlsreferenz aus dem Parser (doc/befehle.md – ein Test prüft, dass sie aktuell ist)."""
    import argparse
    p = parser()
    unter = next(a for a in p._actions if isinstance(a, argparse._SubParsersAction))
    hilfe = {c.dest: c.help for c in unter._choices_actions}
    z = ["# Befehle", "", "Erzeugt aus der Kommandozeile (`amw befehle > doc/befehle.md`). Jeder Befehl zeigt mit `--help` dasselbe.",
         "Gemeinsam für alle: `--von <Name>` (wer handelt; sonst `AMW_AGENT`), `--projekt <Name>` (sonst das erste Projekt).", ""]
    z.append("| Befehl | Zweck |")
    z.append("|---|---|")
    for name in unter.choices:
        z.append(f"| [`{name}`](#{name}) | {(hilfe.get(name) or '').replace('|', '¦')} |")
    for name, sp in unter.choices.items():
        sp.prog = f"amw {name}"
        z += ["", f"## {name}", "```", sp.format_help().rstrip().replace("\r", ""), "```"]
    return "\n".join(z) + "\n"


class Parser(argparse.ArgumentParser):
    """Bei einem Fehler im Aufruf steht der Grund (z. B. die erlaubten Werte) in der ERSTEN Zeile, die Kurzhilfe danach."""
    def error(self, message):
        self.exit(2, f"FEHLER: {self.prog}: {message}\n{self.format_usage()}Hilfe: {self.prog} --help\n")


def main(argv=None):
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    befehl = []
    if "--" in argv:                                  # lauf ausfuehren … -- <befehl …>: alles danach ist der Befehl
        i = argv.index("--")
        argv, befehl = argv[:i], argv[i + 1:]
    a = parser().parse_args(argv)
    a.befehl = befehl
    _pfade_umsetzen(a)
    db.wartemeldung_an()
    try:
        if getattr(a, "ohne_db", False):
            return a.f(a) or 0
        else:
            con = db.verbinde()
            try:
                _heutige_kennungen(con, a)
                rc = a.f(a, con)
            finally:
                con.close()
            return rc or 0
    except (kern.AmwFehler, LookupError, FileNotFoundError, FileExistsError, ValueError) as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 1
    except sqlite3.OperationalError as e:
        if "locked" not in str(e) and "busy" not in str(e):
            raise
        print("FEHLER: Datenbank 30 s lang belegt (ein anderer Prozess schreibt) – nichts geändert, bitte gleich noch"
              " einmal", file=sys.stderr)
        return 3
    return 0


if __name__ == "__main__":
    sys.exit(main())
