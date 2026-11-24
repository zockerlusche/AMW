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
    AMW_AGENT gilt --von wie bisher – nur nicht als ein Agent, der in einer anderen lebenden Claude-Sitzung angemeldet ist
    (_zwilling)."""
    sitzung = (os.environ.get("AMW_AGENT") or "").strip()
    von = getattr(a, "von", None)
    if not von or KANAL.get() in ("bruecke", "mcp"):     # Identität kommt vom Dienst bzw. vom Start des MCP-Servers (A1781)
        return
    if not sitzung:
        _zwilling(con, a, pid, von)
        return
    if kern.kennung_heute(con, von, pid) != kern.kennung_heute(con, sitzung, pid):
        raise kern.AmwFehler(f"Du bist {sitzung} (AMW_AGENT dieser Sitzung) – --von {von} geht nicht: jeder schreibt nur als er"
                             " selbst. Lass --von weg oder setze deinen eigenen Namen.")


def _zwilling(con, a, pid, von):
    """Eine Claude-Sitzung ohne AMW_AGENT (z. B. von Hand in einem anderen Ordner gestartet) schreibt nicht als ein Agent, der
    gerade in einer anderen, noch lebenden Sitzung angemeldet ist – sonst könnte ein Zwilling gleicher Kennung Nachrichten
    lesen, posten oder Aufgaben abschließen. Das Terminal des Entwicklers (kein Claude-Postfach) bleibt wie bisher;
    `amw anmelden` prüft selbst (mit --ersetzen nach Bestätigung)."""
    pipe = os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET")
    if not pipe or not pid or getattr(a, "f", None) is cmd_anmelden:
        return
    from . import hook
    kennung = kern.kennung_heute(con, von, pid)
    try:
        with open(hook.schluessel_datei(con, pid, kennung), encoding="utf-8") as f:
            alt_pipe = json.load(f).get("pipe")
    except (OSError, ValueError, TypeError):
        return
    alt = hook.claude_prozess(alt_pipe) if alt_pipe and alt_pipe != pipe else None
    if alt:
        raise kern.AmwFehler(f"{kennung} ist in einer anderen Sitzung angemeldet ({hook.beschreibung(alt)}) – diese Sitzung ist"
                             f" es nicht, --von {kennung} geht hier nicht. Bist du der richtige {kennung}: amw anmelden --von"
                             f" {kennung} --ersetzen")


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
        if k.strip() in GESPERRTE_EINSTELLUNGEN:     # A1876/A1892: Befehle oder Rechte – --von Entwickler nur im eigenen Terminal
            _rolle_nur_mensch_oder_lead(con, _projekt(con, a), a, f"{k.strip()} setzen")
        e = kern.projekt_einstellen(con, _projekt(con, a), _von(a), **{k.strip(): v.strip()})
        print(f"{k.strip()} = {e.get(k.strip())}")
    elif a.aktion == "schalter":                     # A1926 (D1304 §5): Projekt-Schalter mit Probe an einer Kopie
        from . import schalter
        if not a.name or a.wert not in schalter.STUFEN:
            raise kern.AmwFehler("amw projekt schalter <Projekt> probe | an | aus")
        pid = db.projekt_id(con, a.name)
        if a.wert == "probe":
            _rolle_nur_mensch_oder_lead(con, pid, a, "Probe des Projekt-Schalters")
            r = schalter.probe(con, pid, _von(a))
            print(f"Probe {'bestanden' if r['bestanden'] else 'NICHT bestanden'} – Bericht D{r['dokument']}, Kopie {r['kopie']} ·"
                  f" Schalter {r['stufe']}" + ("" if r["bestanden"] else f" · {len(r['unterschiede'])} Unterschied(e), siehe Bericht"))
            return
        if _von(a) != kern.ENTWICKLER or _aus_agenten_sitzung():
            raise kern.AmwFehler("Ein- und ausschalten nur der Mensch im eigenen Terminal (--von Entwickler)")
        alt, neu = schalter.umschalten(con, pid, _von(a), a.wert)
        print(f"{a.name}: Schalter {alt} → {neu}" + (" – p-Pakete und Themen-Ablauf frei" if neu == "an" else
                                                    " – keine p-Starts, kein automatisches Gegenlesen"))
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


def _arbeit_zeile(con, pid, kennung):
    """A1821 (LayerIT R33): woran der Agent gerade ist und worauf er wartet – eine Zeile, ohne SQL beim Lead."""
    from . import wartegrund
    a = con.execute("SELECT id, status, titel FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status IN ('laeuft', 'wartet', 'blockiert')"
                    " ORDER BY CASE status WHEN 'laeuft' THEN 0 ELSE 1 END, rang, id LIMIT 1", (pid, kennung)).fetchone()
    if not a:
        return ""
    auf = [g["bezug"] for g in wartegrund.offene(con, a["id"])]
    return (f"\n         Aufgabe: A{a['id']} {a['status']}" + (f" auf {', '.join(auf)}" if auf else "") + f" – {a['titel'][:70]}")


def _aus_agenten_sitzung():
    """Läuft dieser Befehl nicht im eigenen Terminal des Menschen? (Dateiaustausch/MCP/Seite, oder aus einer Claude-Sitzung:
    AMW_AGENT, Postfach, CLAUDECODE – jede Sitzung, P256)."""
    return (KANAL.get() != "cli" or bool(os.environ.get("AMW_AGENT") or os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET")
                                          or os.environ.get("CLAUDECODE")))


# A1892 (P294): Projekt-Einstellungen, die Rechte vergeben (Freigeben in der Merge-Liste, Weckrufe, Halt) – gleiche Sperre wie
# „agent lead“; merge_blick/merge_aussen_pruefung setzt zusätzlich nur der Mensch (kern.NUR_MENSCH_WAHL); thema_freigabe und
# sicherung_ziel Lead oder Mensch (A1951, kern.LEAD_ODER_MENSCH_WAHL)
RECHTE_EINSTELLUNGEN = ("paket_pruefer", "leerlauf_lead", "limit_halt", "merge_blick", "merge_aussen_pruefung",
                        "co_entwickler",                  # A1908 (P352): der Co-Entwickler legt Themen an
                        "verteilen", "verteilen_fach",    # A1927 (#29773, P374): ob und wem die AMW Arbeit zuteilt
                        "veroeffentlichen",               # A1928 (#29781): wann die AMW nach außen veröffentlicht
                        "sperrmuster",                    # A1919: was p-Pakete im Projekt nie ändern dürfen
                        "regression_befehl", "abnahme_frist_min",   # A1920: was Prüfung C je Projekt ausführt
                        "sprachpruefung",                 # A1962: Sprach-Server in Prüfung C (auto | pyright | aus)
                        "gesamtlauf_prozesse",            # A1966: Prozesse des parallelen Gesamtlaufs
                        "gesamtlauf_frist_min",           # A2051: Vorgabe-Frist eines Gesamtlaufs (0 = keine)
                        "planer_tagesgrenze_usd",         # A1970: Kosten der Planer je Projekt und Tag
                        "arbeiter_umgebung",              # A1922: Variablen und Pfade der Arbeiter
                        "sicherung_ziel",                 # A1929/A1951: wohin die tägliche Sicherung schiebt (Lead oder Mensch)
                        "thema_freigabe",                 # A1937/A1951: wer Themen freigibt (Lead oder Mensch)
                        "grobplan_freigabe", "feinplan_freigabe", "abschluss_freigabe",   # A2032: wer Meilensteine freigibt
                        "release_modus", "changelog_format",   # A1923: wie Bündel ihre Version und ihren CHANGELOG schreiben
                        "release_sicherung")              # A1933: Sicherung vor der Auslieferung eines Projekts
# eine Stelle für alle Einstellungen mit dieser Sperre (CCamwTL P299): Rechte (A1892) und ausführbare Bündel-Befehle (A1876, P298)
GESPERRTE_EINSTELLUNGEN = RECHTE_EINSTELLUNGEN + kern.BUENDEL_EINSTELLUNGEN


def _nicht_als_mensch_aus_sitzung(a, was):
    """--von Entwickler gilt nur im eigenen Terminal des Menschen (oder in der Workbench am PC), nie aus einer Agenten-Sitzung –
    sonst gäbe eine Sitzung als Mensch allein frei (B2913)."""
    if _von(a) == kern.ENTWICKLER and _aus_agenten_sitzung():
        raise kern.AmwFehler(f"{was}: als Entwickler nur im eigenen Terminal des Menschen oder in der Workbench am PC –"
                             " nicht aus einer Agenten-Sitzung")


def _rolle_nur_mensch_oder_lead(con, pid, a, was):
    """A1887 (P293): Wer die Führung vergibt, ist der Lead – oder der Mensch, aber „--von Entwickler“ gilt dafür nur im
    eigenen Terminal des Menschen. Sonst könnte sich jeder Agent mit --von Entwickler selbst zum Lead machen."""
    if _von(a) == kern.ENTWICKLER and _aus_agenten_sitzung():
        raise kern.AmwFehler(f"{was}: als Entwickler nur im eigenen Terminal des Menschen oder in der Workbench am PC –"
                             " nicht aus einer Agenten-Sitzung")
    if not kern.ist_lead(con, pid, _von(a)):
        raise kern.AmwFehler(f"{was}: nur der Lead oder der Mensch")


def cmd_agent(a, con):
    pid = _projekt(con, a)
    if a.aktion == "lead":                           # A1887 (B2904): Führung in einem Schritt übergeben
        if not a.kennung:
            raise kern.AmwFehler("amw agent lead <neuer Lead> [--co <bisheriger Lead>] [--zustaendig … --nicht …] --grund …")
        _rolle_nur_mensch_oder_lead(con, pid, a, "Den Lead wechseln")
        alt, neu = kern.lead_wechsel(con, pid, _von(a), a.kennung, co=a.co, zustaendig=a.zustaendig, fasst_nicht_an=a.nicht,
                                     grund=a.grund, wort=a.wort)
        if not alt and a.co:                          # A2000: war schon Lead – nur der Co-Entwickler ist neu
            print(f"{neu} bleibt Lead; {a.co} ist Co-Entwickler und behält den Dateiaustausch")
            return
        print(f"{neu} führt jetzt das Projekt (vorher: {', '.join(alt) or '–'})"
              + (f"; {a.co} ist Co-Entwickler und behält den Dateiaustausch" if a.co else ""))
        return
    if a.aktion in ("entfernen", "wiederaufnehmen"):  # A2000 (B2917): wie /api/agent/… – der Mensch im eigenen Terminal;
        if not a.kennung:                             # wiederaufnehmen auch der Lead auf ein frisches Wort (--wort W<nr>)
            raise kern.AmwFehler(f"amw agent {a.aktion} <Agent> --von Entwickler"
                                 + (" (oder als Lead mit --wort W<nr>)" if a.aktion == "wiederaufnehmen" else ""))
        _nicht_als_mensch_aus_sitzung(a, f"Agenten {a.aktion}")
        if a.aktion == "entfernen":
            r = kern.agent_entfernen(con, pid, _von(a), a.kennung)
            print(f"{r['agent']} ist entfernt (Soll aus, ausgeblendet; der Verlauf bleibt)"
                  + ("; die laufende Sitzung wird gesichert und beendet" if r["endet"] else "")
                  + f" – zurück: amw agent wiederaufnehmen {r['agent']} --von Entwickler")
        else:
            r = kern.agent_wiederaufnehmen(con, pid, _von(a), a.kennung, wort=a.wort)
            print(f"{r['agent']} ist wieder aufgenommen (Soll aus – starten: amw agent starten {r['agent']})")
        return
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
        _rolle_nur_mensch_oder_lead(con, pid, a, "Einen Lead anlegen" if kern.lead_und_fach(a.rolle)[0] == "lead"   # A1887 (P293)
                                    else "Einen Agenten anlegen")   # A2039 (D1531 §6): jeder neue Agent nur vom Lead oder Menschen
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
    if a.aktion in ("alle-beenden", "ende-stand"):          # A2048 (V12): Sammelbefehl „Alle speichern & beenden“, Rückmeldung
        from . import steuerung
        projekte = [r[0] for r in con.execute("SELECT id FROM projekt ORDER BY id")] if a.alle_projekte else [pid]
        namen = {r[0]: r[1] for r in con.execute("SELECT id, name FROM projekt")}
        if a.aktion == "alle-beenden":
            if _von(a) != kern.ENTWICKLER or _aus_agenten_sitzung():   # Prozesse beendet nur der Mensch (G14), nie aus einer Sitzung
                raise kern.AmwFehler("Alle speichern & beenden lässt nur der Mensch: in seinem eigenen Terminal mit --von Entwickler"
                                     " oder in der Workbench am PC (Leitstand › Sitzungen)")
            for name, r in steuerung.alle_beenden(con, projekte, a.frist).items():
                print(f"{name}: " + (f"{', '.join(r['agenten'])} sichern – beendet spätestens {_zeit(r['bis_utc'])}" if r["agenten"]
                                     else "keine laufende Sitzung"))
            print("Rückmeldung: amw agent ende-stand" + (" --alle-projekte" if a.alle_projekte else ""))
            return
        for p in projekte:
            st = steuerung.ende_stand(con, p)
            if not st["agenten"]:
                continue
            print(f"{namen.get(p, p)}: " + ("alle beendet" if st["fertig"] else "läuft noch"))
            for x in st["agenten"]:
                print(f"  {x['kennung']:<12} {x['zustand']}" + (f" (bis {_zeit(x['bis_utc'])})" if x["zustand"] != "beendet" else ""))
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
            # A1865 (B2897): starten nur der Mensch – im eigenen Terminal mit --von Entwickler oder in der Workbench am PC
            # (mit Rückfrage); nie ein Agent (auch nicht über Dateiaustausch/MCP), nie aus einer Claude-Sitzung, nie online
            if _von(a) != kern.ENTWICKLER or _aus_agenten_sitzung():   # CLAUDECODE: jede Sitzung (P256)
                raise kern.AmwFehler("Agenten startet nur der Mensch: in der Workbench am PC (Kachel › Starten, mit Rückfrage) oder"
                                     " in seinem eigenen Terminal mit --von Entwickler – nie ein Agent und nie online")
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
            wer = {k: v for k, v in (("rolle", a.rolle), ("fachgebiet", a.fachgebiet), ("arbeitsweise", a.arbeitsweise),
                                     ("zustaendig", a.zustaendig if a.zustaendig is not None else a.grenzen), ("fasst_nicht_an", a.nicht)) if v is not None}
            if a.wort and wer:                               # A1662: auf ein Wort nur Profilfelder – Rolle & Co. nur am PC
                raise kern.AmwFehler(f"mit --wort nur Profilfelder (Ordner, Zusatzordner, Denkaufwand, Modell, Startsatz, Rechte …), nicht {', '.join(wer)}")
            if KANAL.get() in ("bruecke", "mcp") and (aenderung or wer) and not a.wort:
                raise kern.AmwFehler("über den Dateiaustausch nur mit --wort W<nr> (ein frisches Wort des Entwicklers)")
            p = steuerung.profil(con, pid, a.kennung) if not aenderung else steuerung.profil_setzen(con, pid, _von(a), a.kennung, wort=a.wort, ordner=a.ordner, zusatzordner=a.zusatz,
                                        denkstufe=a.denkstufe, modell=a.modell, startsatz=a.startsatz, rechte=a.rechte,
                                        fernsteuerung=schalter(a.fernsteuerung, a.keine_fernsteuerung),
                                        neustart_auto=schalter(a.neustart, a.kein_neustart))
            if "rolle" in wer:                               # A1887 (P293): die Führung nie per --von Entwickler aus einer Sitzung
                _rolle_nur_mensch_oder_lead(con, pid, a, "Die Rolle ändern")
            if wer:                                          # dieselbe Prüfung wie im Zahnrad „Agenten“
                kern.agent_einstellen(con, pid, _von(a), a.kennung, **wer)
            z = kern.agent_zeile(con, pid, a.kennung)
            for k, v in {"lead": "ja" if z["rolle"] == "lead" else "nein", "fachgebiet": z["fachgebiet"], "arbeitsweise": z["arbeitsweise"] or "terminal",
                         "zustaendig": z["zustaendig"], "fasst_nicht_an": z["fasst_nicht_an"], **{k: v for k, v in p.items() if k != "kennung"}}.items():
                print(f"{k:<14} {v}")
            from . import aufwand                            # gemessen (A1611 E1): Dollar-Gegenwert je Aufgabe, genähert
            w = aufwand.je_agent(con, pid, a.kennung)
            if w and w["median"] is not None:
                print(f"{'verbrauch':<14} Median {w['median']:.2f} $ je Aufgabe (letzte {w['n']} fertigen: "
                      + ", ".join(f"A{x['id']} {x['usd']:.2f} $" for x in w["aufgaben"]) + ")")
            if w and w["laufend"]:
                print(f"{'in arbeit':<14} A{w['laufend']['id']} bisher {w['laufend']['usd']:.2f} $")
            from . import empfehlung
            e = empfehlung.fuer_agent(con, pid, a.kennung)
            if e:
                print(f"{'empfehlung':<14} {e['modell']}/{e['denkstufe']} (meist {e['groesse']} · {e['gruppe']}, {e['n']} von {e['von']}"
                      f" letzten Aufgaben)" + {True: " – passt zum Profil", False: " – weicht vom Profil ab (wirkt erst beim nächsten Start)",
                                               None: ""}[e["passt"]])
        return
    for r in con.execute(
            "SELECT g.kennung, g.alias, CASE WHEN g.rolle = 'lead' THEN 'lead' ELSE g.fachgebiet END AS rolle, g.soll, s.zustand, s.letzter_puls_utc, s.taetigkeit, s.taetigkeit_utc,"
            " (g.arbeitsweise = 'chat') AS chat,"
            " (SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
            "   WHERE e.agent = g.kennung AND n.projekt_id = g.projekt_id AND e.status != 'erledigt') AS offen"
            " FROM agent g LEFT JOIN sitzung s ON s.id = (SELECT max(id) FROM sitzung WHERE agent_id = g.id)"
            " WHERE g.projekt_id = ? AND g.entfernt_utc IS NULL ORDER BY g.id", (pid,)):
        ist = r["zustand"] or "nie gestartet"
        if r["chat"]:                                      # A1831: ein Chat wird nie gestartet oder beendet – er war zuletzt da
            ist = "aktiv (Chat)" if r["zustand"] == "aktiv" else (f"zuletzt {_zeit(r['letzter_puls_utc'])} (Chat)"
                                                                if r["letzter_puls_utc"] else "noch nie (Chat)")
        print(f"{r['kennung']:<8} {r['rolle'] or '':<10} soll {r['soll']:<4} ist {ist:<14}"
              f" Puls {_zeit(r['letzter_puls_utc']) or '–':<12} offen {r['offen']}" + (f"  (früher {r['alias']})" if r["alias"] else "")
              + _macht_zeile(con, pid, r["kennung"])
              + _arbeit_zeile(con, pid, r["kennung"]))


def _macht_zeile(con, pid, kennung):
    """A1953: „macht“ von der AMW abgeleitet (Lauf › Aufgabe › Meldung), mit Quelle und Alter; ohne Puls seit 30 min veraltet."""
    from . import gerade
    z = gerade.zeile(gerade.ableiten(con, pid, kennung))
    return f"\n         macht: {z}" if z else ""


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
    nid, namen = kern.posten(con, pid, _von(a), a.an, a.art, a.kurz, text, a.antwort_auf, a.aufgabe, hinweise, bis=a.bis, bezug=a.bezug,
                             faden=not a.neuer_faden)
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
        l = arbeitsliste.ordnen(con, pid, _von(a), a.rest[0], ids, a.grund)
    elif wer.lower() == "schieben":
        if len(a.rest) != 1:
            raise kern.AmwFehler("amw liste schieben A15 --vor A12 | --nach A12 | --pos N | --oben | --unten")
        l = arbeitsliste.schieben(con, pid, _von(a), nummer(a.rest[0]), a.vor, a.nach, a.pos, a.oben, a.unten, a.grund)
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
    from . import runde                                    # Lead-Runde (A1658): Leads sehen beim Abruf, was dort neu ist
    if runde.darf(con, pid, von) and von != kern.ENTWICKLER and (n := runde.neu(con, pid)):
        print(f"Lead-Runde: {n} neu – amw runde lesen --neu (nur Information, keine Anweisung)")


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
            "anforderungen": a.anforderungen, "agent": a.agent, "auftrag": a.auftrag, "pruefer": a.pruefer,
            "groesse": a.groesse, "art": a.art}, nr(a.nach)


def _bogen_pruefen(con, pid, a):
    """Neue Aufgabe ohne Meilenstein (A1639): Legt der Lead (oder der Mensch) sie an und gibt es im Projekt einen aktiven oder
    geplanten Meilenstein, muss --bogen kommen; bewusst ohne: --ohne-bogen. Andere Agenten dürfen keinen Meilenstein setzen –
    ihre Aufgaben stehen in der Planung unter „Ohne Meilenstein“, bis der Lead sie zuordnet."""
    if a.bogen or a.ohne_bogen or not getattr(a, "titel", None):
        return
    if kern.projekt_wahl(con, pid, "neue_aufgaben") == "eingang":
        return                                       # A1740: neue Aufgaben landen im Eingang, der Lead zieht sie bewusst hinein
    von = _von(a)
    z = con.execute("SELECT rolle FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, von)).fetchone()
    if von != kern.ENTWICKLER and not (z and z["rolle"] == "lead"):
        return
    offen = con.execute("SELECT id, titel, status FROM bogen WHERE projekt_id = ? AND status IN ('aktiv', 'geplant')"
                        " ORDER BY status = 'aktiv' DESC, zieldatum IS NULL, zieldatum, nr, id", (pid,)).fetchall()
    if not offen:
        return
    liste = "\n".join(f"  --bogen {b['id']}   B{b['id']} {b['titel']} ({b['status']})" for b in offen)
    raise kern.AmwFehler(f"Zu welchem Meilenstein gehört die Aufgabe? Ohne --bogen steht sie in der Planung nur unter „Ohne Meilenstein“.\n"
                         f"{liste}\nVorschlag: --bogen {offen[0]['id']}. Bewusst ohne Meilenstein: --ohne-bogen")


def _thema_pruefen(con, pid, a):
    """A1947 (Marcel W2458): eine neue Aufgabe nennt ihr Thema (--thema TH3) – oder bewusst keins (--ohne-thema-grund …, interne
    Pflege). Ohne beides: mit thema_pflicht=an Abbruch (vor dem Anlegen), sonst ein Hinweis. Nur, wenn das Projekt Themen hat."""
    if a.thema or getattr(a, "ohne_thema_grund", None) or not getattr(a, "titel", None):
        if getattr(a, "ohne_thema_grund", None) is not None and not a.ohne_thema_grund.strip():
            raise kern.AmwFehler("--ohne-thema-grund: bitte einen Grund (z. B. Aufräumen, Fehlerbehebung)")
        return None
    if not con.execute("SELECT 1 FROM thema WHERE projekt_id = ? LIMIT 1", (pid,)).fetchone():
        return None
    text = ("Zu welchem Thema gehört die Aufgabe? --thema TH… (amw thema liste) – bewusst ohne (interne Pflege, z. B. Aufräumen,"
            " Fehlerbehebung): --ohne-thema-grund \"…\"")
    if kern.projekt_wahl(con, pid, "thema_pflicht") == "an":
        raise kern.AmwFehler(text + " – nichts angelegt (Projekt-Einstellung thema_pflicht=an)")
    return "Hinweis: " + text + " – ohne Thema steht sie in der Planung unter „Paket ohne Thema“."


def _ohne(a):
    return [int(x.strip().lstrip("Aa")) for x in (a.ohne_vorgaenger or "").split(",") if x.strip()]


PAKET_OPTIONEN = {"art": "paket", "gewicht": "gewicht", "ressourcen": "ressourcen", "modell": "modell", "effort": "effort",
                  "pakettyp": "pakettyp", "nie_gleichzeitig": "nie_gleichzeitig", "gleiche_ressource": "gleiche_ressource"}


def _fertig_wenn(con, pid, a, aid):
    """A1938 (K2): --fertig-wenn aus aufgabe neu/aendern."""
    if getattr(a, "fertig_wenn", None):
        from . import fertigquelle
        q = fertigquelle.setzen(con, pid, _von(a), aid, a.fertig_wenn)
        print(f"A{aid}: fertig wenn {fertigquelle.text(q)}")


def _paket_holen(con, pid, a):
    """A1943 (K9): nächste Aufgabe (oder N) starten, Auftrag + Startwissen zeigen, Zweig a<N> und – mit baum_wurzel – Arbeitsbaum
    anlegen (nur anlegen, nie entfernen; nie im Projektordner)."""
    import subprocess
    from . import arbeitsliste, startwissen
    von = _von(a)
    aid = a.id
    if not aid:
        frei = [x for x in arbeitsliste.liste(con, pid, von) if x["status"] == "wartet" and not x["gruende"]]
        laeuft = [x for x in arbeitsliste.liste(con, pid, von) if x["status"] == "laeuft"]
        if laeuft:
            raise kern.AmwFehler(f"A{laeuft[0]['id']} läuft noch – eins nach dem anderen (erst fertig oder wartet)")
        if not frei:
            raise kern.AmwFehler("In deiner Liste ist nichts startklar")
        aid = frei[0]["id"]
    kern.aufgabe_status(con, pid, von, aid, "start")
    r = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    print(f"A{aid} → laeuft · {r['titel']}")
    if r["auftrag"]:
        print(f"Auftrag: {r['auftrag']}")
    from . import planung, themen
    for i, k in enumerate(planung._json(r["kriterien"], []), 1):
        print(f"Kriterium {i}: {k.get('text')}" + (" ✓" if k.get("erfuellt") else ""))
    th = themen.verweise(con, pid, aid)
    if th:
        print("Thema: " + ", ".join(f"TH{t}" for t in th))
    _startwissen_drucken(con, pid, aid)
    ordner = kern.projekt_ordner(con, pid)
    e = json.loads(con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()[0] or "{}")
    zweig, wurzel = f"a{aid}", e.get("baum_wurzel")
    if not ordner:
        return 0
    if not wurzel:
        print(f"\nZweig: git -C {ordner} worktree add -b {zweig} <eigener Ordner>/{zweig} main  (mit amw projekt einstellen"
              " baum_wurzel=<Ordner> legt holen ihn selbst an)")
        return 0
    ziel = os.path.join(wurzel, zweig)
    if os.path.exists(ziel):
        print(f"\nArbeitsbaum {ziel} gibt es schon – nichts angelegt")
        return 0
    vorhanden = subprocess.run(["git", "-C", ordner, "rev-parse", "--verify", "--quiet", f"refs/heads/{zweig}"], capture_output=True,
                               stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode == 0
    args = ["git", "-C", ordner, "worktree", "add"] + ([ziel, zweig] if vorhanden else ["-b", zweig, ziel, "main"])
    p = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    print(f"\nArbeitsbaum {ziel} ({zweig}" + (", vorhandener Zweig" if vorhanden else ", neu auf main") + ")" if p.returncode == 0
          else f"\nArbeitsbaum nicht angelegt: {(p.stderr or p.stdout).strip()[:200]}")
    if p.returncode == 0:
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="paket_holen", aufgabe_id=aid,
                         text=json.dumps({"zweig": zweig, "baum": ziel}, ensure_ascii=False))
    return 0


def _paket_fertig(con, pid, a):
    """A1943 (K9): Tests-Hinweis, Prüfbitte an den Prüfer, Aufgabe wartet auf ihn, Messung – ein Befehl."""
    from . import startwissen
    von, aid = _von(a), a.id
    r = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not r:
        raise kern.AmwFehler(f"A{aid} gibt es nicht")
    if not (a.sha and a.punkte):
        raise kern.AmwFehler("amw paket fertig <N> --sha <Commit> --punkte \"was du geprüft hast\" [--zweig … --pruefer … --gruppe … --hinweis …]")
    pruefer = a.pruefer or r["pruefer"] or kern.lead(con, pid)
    if not pruefer:
        raise kern.AmwFehler("Kein Prüfer: --pruefer <Agent>")
    zweig = a.zweig or f"a{aid}"
    ordner = kern.projekt_ordner(con, pid)
    if ordner:
        dateien = (startwissen._git(ordner, "diff", "--name-only", f"main...{a.sha}") or "").split()
        tests = startwissen.tests_zu(ordner, dateien)
        if tests:
            print("Tests zu den geänderten Dateien: " + " ".join(tests))
    prid = betrieb.pruefbitte(con, pid, von, pruefer, zweig, a.sha, a.punkte, aid, gruppe=a.gruppe, hinweis=a.hinweis,
                              ohne_bild=a.ohne_bild)
    print(f"P{prid} an {pruefer}")
    neu = kern.aufgabe_status(con, pid, von, aid, "wartet", auf=pruefer, wartet_auf=f"Prüfung P{prid}")
    print(f"A{aid} → {neu} · wartet auf {pruefer}")
    holen = con.execute("SELECT 1 FROM plan_ereignis WHERE aufgabe_id = ? AND art IN ('paket_holen', 'startwissen')", (aid,)).fetchone()
    n = startwissen.befehle_seit(db.projekt_name(con, pid), von, r["begonnen_utc"])
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=startwissen.MESSUNG, aufgabe_id=aid,
                     text=json.dumps({"befehle": n, "holen": bool(holen), "pruefung": prid}, ensure_ascii=False))
    return 0


def _paket_setzen(con, pid, a, aid):
    """Paketfelder aus aufgabe neu/aendern (A1845) – nur, wenn eine Paket-Option angegeben ist; Warnungen ausgeben."""
    werte = {feld: getattr(a, opt, None) for feld, opt in PAKET_OPTIONEN.items()}
    if all(v is None for v in werte.values()):
        return
    from . import arbeitspaket
    f, warn = arbeitspaket.setzen(con, pid, _von(a), aid, **werte)
    print(f"A{aid}: Paket {f['art']}" + (f" · {arbeitspaket.TEXT[f['zustand']]}" if f["zustand"] else ""))
    for w in warn:
        print(f"  Achtung: {w}")


def _paket_zeilen(f, a):
    from . import arbeitspaket
    std = lambda k: " (Vorgabe)" if k in f["standard"] else ""
    z = [f"Art: {f['art']}{std('art')}" + (f" · Zustand: {arbeitspaket.TEXT[f['zustand']]} seit {f['zustand_utc'] or '–'}" if f["zustand"] else
                                          " · Zustände: keine (es gilt der Status der Aufgabe)"),
         f"Abnahme-Befehl: {a['pruefbefehl'] or '–'}", f"Bereiche: {a['dateibereich'] or '–'}",
         f"Gewicht: {f['gewicht']}{std('gewicht')} · Ressourcen: {', '.join(f['ressourcen']) or 'keine'}{std('ressourcen')}",
         f"Modell: {f['modell']}{std('modell')} · Effort: {f['effort']}{std('effort')} · Pakettyp: {f['pakettyp']}{std('pakettyp')}",
         f"Rang: {a['rang']} · nie gleichzeitig mit: {', '.join(f'A{n}' for n in f['nie_gleichzeitig']) or '–'}"
         f" · gleiche Ressource: {f['gleiche_ressource'] or '–'}"]
    return z


def cmd_paket(a, con):
    """Arbeitspakete (A1845): zeigen, Zustand wechseln (Lead/Mensch von Hand; später die AMW selbst), Liste der p-Pakete."""
    from . import arbeitspaket
    pid = _projekt(con, a)
    if a.aktion in ("zeigen", "zustand", "ergebnis", "starten", "fertig") and not a.id:
        raise kern.AmwFehler(f"amw paket {a.aktion} <Aufgabe> …")
    if a.aktion == "holen":                            # A1943 (K9): ein Befehl statt vieler zum Anfangen
        return _paket_holen(con, pid, a)
    if a.aktion == "fertig":                           # A1943 (K9): ein Befehl statt vieler zum Abgeben
        return _paket_fertig(con, pid, a)
    if a.aktion == "mergeliste":                      # A1858: Liste „bereit zum Merge“
        from . import mergeliste
        d = mergeliste.liste(con, pid, diff=a.diff)
        print(f"Bereit zum Merge: {len(d['pakete'])} · Blick: {d['merge_blick']} · Außen-Prüfung: {d['merge_aussen_pruefung']}")
        for e in d["pakete"]:
            marken = [m for m, ja in (("freigegeben", e["freigegeben"]), ("Server-Code", e["server"]),
                                      ("Blick nötig", e["blick"] and not e["freigegeben"])) if ja]
            print()
            print(f"A{e['aufgabe']} {e['titel'][:80]} – {e['zweig']}@{(e['kopf'] or '–')[:8]}" + (f" [{', '.join(marken)}]" if marken else ""))
            if e["fehler"]:
                print(f"  Achtung: {e['fehler']}")
            for z in e["stat"].splitlines():
                print("  " + z)
            for x in e["aussen"]:
                print(f"  nach außen (Hinweis): {x}")
            if e.get("ohne_regression"):
                print(f"  Hinweis: {e['ohne_regression']}")
            if a.diff:
                for z in e["diff"].splitlines():
                    print("  " + z)
                if e["gekuerzt"]:
                    print("  … gekürzt")
        if any(e["blick"] and not e["freigegeben"] for e in d["pakete"]):
            print()
            print("Prüfliste für den Blick: " + " · ".join(d["pruefliste"]))
        if d["pakete"]:
            print()
            print("Freigeben: amw paket freigeben --alle | amw paket freigeben <A> [--blick]")
        return
    if a.aktion == "freigeben":                       # A1858: eine Freigabe über alle (Prüfer der Pakete, Lead, Mensch)
        from . import mergeliste
        if not a.alle and not a.id:
            raise kern.AmwFehler("amw paket freigeben --alle | amw paket freigeben <Aufgabe> [--blick]")
        if a.blick and not a.id:
            raise kern.AmwFehler("--blick gilt für ein einzelnes Paket: amw paket freigeben <Aufgabe> --blick (nach dem Ansehen des Diffs)")
        for r in mergeliste.freigeben(con, pid, _von(a), None if a.alle else [a.id], blick=[a.id] if a.blick else ()):
            print(f"A{r['aufgabe']}: {'freigegeben' if r['ok'] else 'nicht freigegeben'} – {r['text']}")
        return
    if a.aktion == "annehmen":                        # A1894: E4-Paket nach dem Lesen annehmen → Merge-Liste (Lead, Mensch)
        from . import mergeliste
        if not a.id:
            raise kern.AmwFehler("amw paket annehmen <Aufgabe> --grund „was du gelesen hast und warum es passt“")
        _rolle_nur_mensch_oder_lead(con, pid, a, "Ein Paket annehmen")
        r = mergeliste.annehmen(con, pid, _von(a), a.id, a.grund)
        print(f"A{r['aufgabe']} angenommen: {r['zweig']}@{r['kopf'][:8]} steht in der Merge-Liste (bereit zum Merge) –"
              f" freigeben: amw paket freigeben {r['aufgabe']}")
        return
    if a.aktion == "buendeln":                        # A1876 (D1306): freigegebene Pakete zu einem Release-Stand (Lead, Mensch)
        from . import buendel
        if a.gesamtlauf:                              # A1909 (3): Gesamtlauf eines vorhandenen Bündels neu anstoßen
            _rolle_nur_mensch_oder_lead(con, pid, a, "Bündel-Gesamtlauf anstoßen")
            r = buendel.gesamtlauf_neu(con, pid, _von(a), a.gesamtlauf)
            print(f"Bündel {r['version']}: Gesamtlauf für {r['zweig']}@{r['sha'][:8]} neu angestoßen (Prozess {r['starter']}) –"
                  " die Meldung kommt, wenn er zu Ende ist")
            return
        if not a.alle and not a.id:
            raise kern.AmwFehler("amw paket buendeln --alle | amw paket buendeln <Aufgabe> [--titel …]"
                                 " | amw paket buendeln --gesamtlauf buendel-X.Y.Z")
        _rolle_nur_mensch_oder_lead(con, pid, a, "Bündeln")   # P298: wie agent lead – kein --von Entwickler aus einer Sitzung
        r = buendel.buendeln(con, pid, _von(a), None if a.alle else [a.id], titel=a.titel)
        print(f"Bündel {r['version']}: {r['zweig']}@{r['sha'][:8]} mit {len(r['drin'])} Paket(en): "
              + ", ".join(f"A{p['id']}" for p in r["drin"]) + f" (Arbeitsbaum {r['ordner']})")
        for p in r["raus"]:
            print(f"  nicht im Bündel: A{p['id']} – {p['grund']}")
        for alt, neu in r.get("umbenannt") or []:
            print(f"  Abnahme-Test läuft ab jetzt in der Gesamtsuite: {alt} → {neu}")
        for h in r.get("abnahme_hinweise") or []:
            print(f"  Hinweis: {h}")
        for t in r["uebernommen"]:
            print(f"  übernommen: {t}")
        return
    if a.aktion == "starten":                         # A1874: Handstart zum Probieren – nur Mensch/Lead, der Wächter entscheidet
        from . import disponent
        print(disponent.handstart(con, pid, a.id, _von(a)))
        return
    if a.aktion == "ergebnis":                        # A1857 (§6a.6): Ergebnis eines interaktiven Pakets, gleiches Schema wie -p
        from . import rueckmeldung
        if a.json is not None:
            if a.json != "-":
                raise kern.AmwFehler("--json nur über stdin: … | amw paket ergebnis <nr> --json - (kein JSON als Argument – "
                                     "PowerShell verschluckt Anführungszeichen); oder einzelne Schalter --status --zusammenfassung …")
            try:
                meldung = json.loads(sys.stdin.read() or "null")
            except ValueError:
                raise kern.AmwFehler("--json -: auf stdin kam kein gültiges JSON") from None
        else:
            meldung = {k: v for k, v in (("status", a.status), ("zusammenfassung", a.zusammenfassung), ("frage", a.frage),
                                          ("frage_an", a.frage_an), ("grund", a.grund), ("hinweis", a.hinweis)) if v is not None}
        r = rueckmeldung.melden_interaktiv(con, pid, _von(a), a.id, meldung, zweig=a.zweig)
        print(f"A{a.id}: Ergebnis „{meldung['status']}“ angenommen – die AMW prüft selbst; es gilt die letzte gültige Meldung"
              + (f" · P{r['pruefbitte']['id']} an {r['pruefbitte']['an']} mit Befund {r['pruefbitte']['befund'] or 'ohne Befund'}"
                 if r.get("pruefbitte") else ""))
        return
    if a.aktion == "zeigen":
        r = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (a.id, pid)).fetchone()
        if not r:
            raise kern.AmwFehler(f"A{a.id} gibt es nicht")
        f = arbeitspaket.lesen(con, a.id)
        print(f"A{a.id} [{r['status']}] {r['titel']}")
        for z in _paket_zeilen(f, r):
            print("  " + z)
        from . import eignung                            # A1955 (TH165): Werte als Spanne P50–P85 aus der Eignungstabelle
        sp = eignung.spanne(con, pid, a.id)
        if sp:
            print("  " + eignung.spanne_text(sp))
        for w in arbeitspaket.warnungen(f, r["pruefbefehl"], r["dateibereich"]):
            print(f"  Achtung: {w}")
        for zeit, alt, neu, grund in arbeitspaket.verlauf(con, a.id)[-8:]:
            print(f"  {zeit[:16].replace('T', ' ')}  {arbeitspaket.TEXT.get(alt, '–') if alt else '–'} → "
                  f"{arbeitspaket.TEXT.get(neu, '–') if neu else '–'}" + (f"  ({grund})" if grund else ""))
    elif a.aktion == "zustand":
        if not a.zustand:
            raise kern.AmwFehler("amw paket zustand <Aufgabe> <zustand> – möglich: " + ", ".join(arbeitspaket.ZUSTAENDE))
        alt, neu, status = arbeitspaket.zustand_setzen(con, pid, _von(a), a.id, a.zustand, a.grund, a.beleg)
        print(f"A{a.id}: {arbeitspaket.TEXT[alt]} → {arbeitspaket.TEXT[neu]} (Aufgabe: {status})")
    else:
        nur = {z.strip() for z in (a.nur or "").split(",") if z.strip()}
        falsch = nur - set(arbeitspaket.ZUSTAENDE)
        if falsch:
            raise kern.AmwFehler(f"unbekannter Zustand: {', '.join(sorted(falsch))}")
        zeilen = con.execute("SELECT a.id, a.titel, a.rang, p.zustand, p.zustand_utc FROM paket p JOIN aufgabe a ON a.id = p.aufgabe_id"
                             " WHERE a.projekt_id = ? AND p.art = 'p' ORDER BY a.rang, a.id", (pid,)).fetchall()
        zeilen = [z for z in zeilen if not nur or z["zustand"] in nur]
        if not zeilen:
            print("keine p-Pakete" + (f" in {', '.join(sorted(nur))}" if nur else ""))
        for z in zeilen:
            print(f"A{z['id']:<5} {arbeitspaket.TEXT.get(z['zustand'], z['zustand'] or '–'):<24} Rang {z['rang']:<4} {z['titel'][:90]}")


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
        _bogen_pruefen(con, pid, a)
        thema_hinweis = _thema_pruefen(con, pid, a)          # A1947: kein Paket ohne Thema
        werte, nach = _schritt_werte(a)
        if any(v is not None for k, v in werte.items() if k not in ("agent", "auftrag", "pruefer", "groesse", "art")) or nach:
            aid = planung.schritt_setzen(con, pid, _von(a), titel=a.titel, nach=nach, rang=a.rang, **werte)
        else:
            aid = kern.aufgabe_neu(con, pid, _von(a), a.titel, a.agent, a.auftrag, a.rang, a.pruefer, sofort=a.sofort)
            if a.groesse or a.art:                      # Größe/Art (A1611 E2) – Empfehlung für Modell/Denkaufwand
                planung.schritt_setzen(con, pid, _von(a), aid=aid, groesse=a.groesse, art=a.art)
        if a.pool:
            wissen.einstufen(con, pid, _von(a), aid, "pool")
        eingang = not a.bogen and not a.pool and kern.projekt_wahl(con, pid, "neue_aufgaben") == "eingang"
        if eingang:                                      # A1740: ohne --bogen in den Eingang (--bogen = für die Abnahme nötig)
            with db.schreiben(con):
                con.execute("UPDATE aufgabe SET einstufung = 'pool' WHERE id = ?", (aid,))
        z = con.execute("SELECT agent, einstufung FROM aufgabe WHERE id = ?", (aid,)).fetchone()
        if eingang:
            print(f"A{aid} angelegt – steht im Eingang (Projekt-Einstellung „Neue Aufgaben landen im Eingang“). Der Lead zieht sie"
                  f" in einen Meilenstein: amw aufgabe aendern {aid} --bogen <nr>; direkt in den Meilenstein: beim Anlegen --bogen <nr>")
        elif z["einstufung"] == "pool" and z["agent"] and not a.pool:   # der Agent hat gerade ein Stück in Arbeit
            from . import arbeitsliste
            x = arbeitsliste.laufend(con, pid, z["agent"])
            print(f"A{aid} angelegt – steht im Eingang, weil {z['agent']} gerade an A{x['id'] if x else '?'} arbeitet."
                  f" Einplanen: amw liste ordnen {z['agent']} A{aid} … (landet hinter dem laufenden Stück);"
                  " sofort hinter das laufende Stück: beim Anlegen --sofort")
        else:
            print(f"A{aid} angelegt" + (" (Eingang – der Lead plant ein: amw liste ordnen <Agent> …)" if a.pool else ""))
        _paket_setzen(con, pid, a, aid)
        _fertig_wenn(con, pid, a, aid)
        from . import planer                                 # A2004: p ist die Vorgabe für S und M-mechanisch
        if not getattr(a, "paket", None) and planer.p_vorgabe({"groesse": a.groesse, "art": a.art}) \
                and "interaktiv, grund" not in (a.auftrag or "").lower():
            print(f"Hinweis: A{aid} ({a.groesse} · {a.art}) – p möglich: amw aufgabe aendern {aid} --paket p --pruefbefehl … --dateien …"
                  " – oder den Grund in den Auftrag („Interaktiv, Grund: …“)")
        if a.thema:                                          # A1947: gleich beim Anlegen mit dem Thema verknüpfen (A1915)
            from . import themen
            print("Thema: " + ", ".join(f"TH{t}" for t in themen.verweise_setzen(con, pid, _von(a), aid, a.thema.split(","))))
        elif a.ohne_thema_grund:
            from . import themen
            themen.ohne_thema_vermerken(con, pid, _von(a), aid, a.ohne_thema_grund)
        elif thema_hinweis:
            print(thema_hinweis)
        if not (a.groesse and a.art):
            print("Tipp: --groesse S|M|L|XL und --art … geben eine Empfehlung für Modell und Denkaufwand (amw aufgabe aendern"
                  f" {aid} --groesse M --art oberflaeche)")
    elif a.aktion == "aendern":
        werte, nach = _schritt_werte(a)
        werte["zusammenfassung"] = a.zusammenfassung              # auch nachträglich (Plan-Check)
        if _von(a) == kern.ENTWICKLER and not _aus_agenten_sitzung():   # A1957: Titel/Auftrag/Kriterien/Meilenstein erst als Vorschlag
            from . import folgen
            inhalt = {"titel": a.titel, "auftrag": werte.pop("auftrag", None), "kriterien": werte.pop("kriterien", None),
                      "bogen_id": werte.pop("bogen_id", None)}
            a.titel = None
            r = folgen.vorschlagen(con, pid, kern.ENTWICKLER, "paket", a.id, **inhalt)
            if r["stand"] == "prueft":
                print(f"A{a.id}: Änderung wird geprüft (Ä{r['aenderung']}) – gilt von selbst, wenn Ziel, Erfolg und Kosten nicht berührt"
                      " sind; sonst Ja in der Planung")
        if any(v is not None for v in werte.values()) or nach or a.titel:
            planung.schritt_setzen(con, pid, _von(a), aid=a.id, titel=a.titel, nach=nach, **werte)
        if _ohne(a):
            planung.abhaengigkeit_setzen(con, pid, _von(a), a.id, _ohne(a), entfernen=True)
        if a.federfuehrend is not None:
            ff = kern.federfuehrung_setzen(con, pid, _von(a), "aufgabe", a.id, a.federfuehrend)
            print(f"A{a.id}: federführend {ff or '– (Meilenstein bzw. Lead)'}")
        _paket_setzen(con, pid, a, a.id)
        _fertig_wenn(con, pid, a, a.id)
        if a.thema or a.ohne_thema:                               # A1915: Verweise auf Themen (Themen → Pakete)
            from . import themen
            if a.thema:
                themen.verweise_setzen(con, pid, _von(a), a.id, a.thema.split(","))
            if a.ohne_thema:
                themen.verweise_setzen(con, pid, _von(a), a.id, a.ohne_thema.split(","), entfernen=True)
            print(f"A{a.id}: Themen " + (", ".join(f"TH{x}" for x in themen.verweise(con, pid, a.id)) or "–"))
        print(f"A{a.id} geändert")
    elif a.aktion == "bereit":                        # A1939 (K3): der Bearbeiter meldet – das Ergebnis steht
        from . import urteil
        urteil.bereit_melden(con, pid, _von(a), a.id)
        print(f"A{a.id} bereit zur Abnahme – steht unter „Für dich“; ein Ja genügt, den Status setzt die AMW")
    elif a.aktion == "abnehmen":                      # A1939 (K3): Ja (oder --zurueck --kommentar) – Mensch oder Lead
        from . import urteil
        r = urteil.entscheiden(con, pid, _von(a), a.id, not a.zurueck, a.kommentar)
        print(f"A{a.id} abgenommen – fertig" if r == "fertig" else f"A{a.id} zurück an den Bearbeiter")
    elif a.aktion == "kriterium":
        if getattr(a, "quelle", None) is not None:              # A1938 (K2): Prüfquelle statt Abhaken von Hand
            from . import fertigquelle
            liste = fertigquelle.pruefquelle_setzen(con, pid, _von(a), a.id, a.nr, a.quelle)
        else:
            liste = planung.kriterium(con, pid, _von(a), a.id, a.nr, not a.nein)
        for i, k in enumerate(liste, 1):
            q = k.get("quelle")
            print(f"  {i}. [{'x' if k.get('erfuellt') else ' '}] {k['text']}"
                  + (f"  · Quelle: {q['art']}{(' ' + str(q.get('befehl') or q.get('thema') or q.get('mindestens'))) if len(q) > 1 else ''}" if q else "")
                  + (f"  · {k['beleg']}" if k.get("beleg") else ""))
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
    elif a.aktion == "hinweis":                       # A1978: Versionshinweis ändern oder zurücknehmen (intern), auch nach fertig
        if not a.id:
            raise kern.AmwFehler("amw aufgabe hinweis <nr> --gruppe neu|verbessert|behoben|intern [--hinweis „Satz“]")
        from . import versionshinweise
        r = versionshinweise.nachtragen(con, pid, _von(a), a.id, a.gruppe, a.hinweis)
        print(f"A{a.id}: " + ("intern – erscheint nicht in den Versionshinweisen" if r == "intern" else f"Versionshinweis ({r}) gesetzt"))
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
        from . import fertigquelle
        q = fertigquelle.lesen(con, a.id)
        if q:                                                     # A1938 (K2)
            print(f"fertig_wenn: {fertigquelle.text(q)}")
        from . import themen
        th = themen.verweise(con, pid, a.id)
        if th:                                                    # A1915
            print("themen: " + ", ".join(f"TH{x} {themen.finden(con, pid, x)['name']}" for x in th))
        for g in con.execute("SELECT * FROM wartegrund WHERE aufgabe_id = ? ORDER BY id", (a.id,)):
            print(f"wartegrund: {g['bezug']} (seit {_zeit(g['angelegt_utc'])}, {g['angelegt_von']})"
                  + (f" – erledigt {_zeit(g['erledigt_utc'])}: {g['erledigt_durch']}" if g["erledigt_utc"] else " – offen"))
        from . import aufwand
        v = aufwand.je_aufgabe(con, pid, a.id)
        if v:
            print(f"verbrauch: {v['usd']:.2f} $ Gegenwert" + (f" ({', '.join(v['modelle'])})" if v["modelle"] else "")
                  + " – genähert aus dem Kosten-Zähler zwischen Beginn und Abschluss")
        from . import empfehlung
        e = empfehlung.fuer_aufgabe(con, pid, a.id)
        if e:
            z = e["zelle"]
            print(f"empfehlung: {e['modell']}/{e['denkstufe']} für {e['groesse']} · {e['art']}"
                  + (f" (gemessen in dieser Zelle: Median {z['median']:.2f} $ aus {z['n']}, {z['rot']}× rot)" if z else "")
                  + ("" if e["passt"] is not False else f" – {e['agent']} ist eingestellt auf {e['profil']['modell']}/{e['profil']['denkstufe']}")
                  + " – nur Empfehlung, gesetzt wird im Profil")
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
        from . import wartegrund
        vorher = [g["bezug"] for g in wartegrund.offene(con, a.id)]
        neu = kern.aufgabe_status(con, pid, _von(a), a.id, a.aktion, a.beleg, a.wartet_auf, a.bemerkung, a.zusammenfassung,
                                  a.auf, a.erledigt, hinweise, hinweis=a.hinweis, gruppe=a.gruppe)
        offen = [g["bezug"] for g in wartegrund.offene(con, a.id)]
        print(f"A{a.id} → {neu}" + (f" · wartet auf {', '.join(offen)}" if offen and neu in ("wartet", "blockiert") else ""))
        if a.auf and neu in ("wartet", "blockiert"):   # A1677: --auf fügt hinzu – alte Gründe bleiben offen, bis sie abgehakt sind
            genannt = {x.strip().lower() for x in wartegrund.teile(a.auf)}
            alt = [b for b in vorher if b in offen and b.lower() not in genannt]
            if alt:
                print(f"Hinweis: --auf fügt Gründe hinzu – von vorher noch offen: {', '.join(alt)}. Erledigt? "
                      f"amw aufgabe {a.aktion} {a.id} --erledigt {','.join(alt)}")
        for h in hinweise:
            print(h)
        if neu == "laeuft" and a.aktion == "start":     # A1943 (K9): Startwissen mit festem Budget (#30728)
            _startwissen_drucken(con, pid, a.id)


def _startwissen_drucken(con, pid, aid):
    from . import startwissen
    try:
        t = startwissen.startwissen(con, pid, aid)
    except Exception:                                  # noqa: BLE001 – Startwissen ist Zusatz
        t = ""
    if t:
        print("\n" + t)


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
        print(f"Meilenstein {bid} angelegt – Ziel und Abnahme dürfen auf Themen und Dokumente verweisen (TH<n>, D<n>);"
              " seine Themen kommen aus den Aufgaben (amw aufgabe aendern <nr> --thema TH<n>)")
    elif a.aktion in ("freigeben", "zurueck"):        # K6/K7: Ja (Co, Lead; der Mensch allein) bzw. zurück mit Notiz
        from . import planansicht
        _nicht_als_mensch_aus_sitzung(a, f"bogen {a.aktion}")   # Vorab-Prüfung 1.164.0 (1)
        if not a.id or not a.art:
            raise kern.AmwFehler(f"amw bogen {a.aktion} <Nummer> --art grob|plan|abschluss" + (" --notiz …" if a.aktion == "zurueck" else ""))
        if a.aktion == "zurueck":
            planansicht.zurueck(con, pid, _von(a), a.id, a.art, a.notiz)
            print(f"Meilenstein {a.id} ({a.art}): zurück")
        else:
            if a.starten and a.art != "plan":
                raise kern.AmwFehler("--starten gibt es nur mit --art plan")
            if a.starten:                             # A2031: das Feinplan-Ja ist der Start
                from . import feinplanung
                r: dict = feinplanung.plan_starten(con, pid, _von(a), a.id)
            else:
                r = dict(planansicht.freigeben(con, pid, _von(a), a.id, a.art))
            fehlt = [str(x) for x in (r.get("ja_fehlt") or [])]
            gestartet = r.get("gestartet") or {}
            print(f"Meilenstein {a.id} ({a.art}): " + ("freigegeben" if r.get("frei") else "dein Ja steht – fehlt noch: " + ", ".join(fehlt))
                  + (f" · gestartet, {len(gestartet.get('startklar') or [])} Pakete startklar" if gestartet else ""))
    elif a.aktion == "nacharbeit":                    # A2029: „Nacharbeit anfordern“ – neue Pakete im selben Meilenstein, starten gleich
        from . import abschluss
        _nicht_als_mensch_aus_sitzung(a, "bogen nacharbeit")
        if not a.id:
            raise kern.AmwFehler("amw bogen nacharbeit <Nummer des Meilensteins> --hinweis „was fehlt“")
        print(abschluss.nacharbeit(con, pid, _von(a), a.id, a.hinweis)["text"])
    elif a.aktion == "feinplanen":                    # A2031: Feinplan (neu) planen lassen – „Überarbeiten lassen“
        from . import feinplanung
        _nicht_als_mensch_aus_sitzung(a, "bogen feinplanen")
        if not a.id:
            raise kern.AmwFehler("amw bogen feinplanen <Nummer des Meilensteins> [--hinweis …]")
        print(feinplanung.neu_planen(con, pid, _von(a), a.id, a.hinweis)["text"])
    elif a.aktion == "bericht":                       # K7: Abschlussbericht (neu) erstellen – Lead oder Mensch
        from . import tore
        _nicht_als_mensch_aus_sitzung(a, "bogen bericht")
        if not a.id:
            raise kern.AmwFehler("amw bogen bericht <Nummer des Meilensteins>")
        if not kern.ist_lead(con, pid, _von(a)):
            raise kern.AmwFehler("Einen Abschlussbericht neu erstellen lassen Lead oder Mensch")
        print(f"Abschlussbericht D{tore.bericht_erstellen(con, pid, a.id)}")
    elif a.aktion == "tore":                          # K7: Stand der fünf Tore
        from . import tore
        s = tore.stand(con, pid)
        print(s["zeile"])
        for x in s["tore"]:
            print(f"  {'✓' if x['zu'] else ('●' if x['tor'] == s['aktuell'] else '○')} {x['name']:<12} {x['text']}")
        for x in s["nichts_offen"]:
            print(f"  „nichts zu bauen“ TH{x['id']} {x['name']} wartet auf Bestätigung des Co (amw thema vermerk TH{x['id']} --bestaetigen)")
    elif a.aktion == "abnehmen":                      # A1928 (TH158): nur der Mensch – danach veröffentlicht die AMW
        if not a.id:
            raise kern.AmwFehler("bogen abnehmen <Nummer des Meilensteins>")
        if _von(a) != kern.ENTWICKLER or _aus_agenten_sitzung():
            raise kern.AmwFehler("Einen Meilenstein nimmt nur der Mensch ab – im eigenen Terminal (--von Entwickler) oder in der"
                                 " Workbench am PC, nicht aus einer Agenten-Sitzung")
        from . import veroeffentlichung
        print(veroeffentlichung.abnehmen(con, pid, kern.ENTWICKLER, a.id))
    elif a.aktion == "aendern":
        if _von(a) == kern.ENTWICKLER and not _aus_agenten_sitzung():   # A1957: die eigene Änderung erst als Vorschlag
            from . import folgen
            if a.nr is not None:
                planung.bogen_aendern(con, pid, _von(a), a.id, nr=a.nr)
            r = folgen.vorschlagen(con, pid, kern.ENTWICKLER, "meilenstein", a.id, grund=a.grund, titel=a.titel, ziel=a.ziel,
                                   abnahme=a.abnahme, zieldatum=a.zieldatum)
            if r["stand"] == "prueft":
                print(f"Meilenstein {a.id}: Änderung wird geprüft (Ä{r['aenderung']}) – gilt von selbst, wenn Ziel, Erfolg und Kosten"
                      " nicht berührt sind; sonst Ja in der Planung")
        else:
            planung.bogen_aendern(con, pid, _von(a), a.id, a.titel, a.ziel, a.abnahme, a.zieldatum, a.nr, a.grund)
        if a.federfuehrend is not None:
            ff = kern.federfuehrung_setzen(con, pid, _von(a), "bogen", a.id, a.federfuehrend)
            print(f"Meilenstein {a.id}: federführend {ff or '– (Lead)'}")
        print(f"Meilenstein {a.id} geändert")
    elif a.aktion == "status":
        planung.bogen_status(con, pid, _von(a), a.id, a.wert, a.erzwingen)
        print(f"Meilenstein {a.id} → {a.wert}")
    elif a.aktion == "starten":                       # A1941 (K5): Jetzt starten – an den Disponenten
        if not a.id:
            raise kern.AmwFehler("bogen starten <Nummer des Meilensteins>")
        from . import reihenfolge
        r = reihenfolge.starten(con, pid, _von(a), a.id)
        print(f"Meilenstein {a.id} gestartet – {len(r['startklar'])} Pakete startklar" + (f", verteilt: {'; '.join(r['verteilt'])}" if r["verteilt"] else ""))
        for aid, f in r["fehlt"].items():
            print(f"  noch nicht startklar: A{aid} – fehlt {', '.join(f)}")
    elif a.aktion == "reihenfolge":                   # A1941 (K5): die berechnete Reihenfolge
        from . import reihenfolge
        prog = planung.prognose(con, pid, laeufe=300)
        for z in reihenfolge.berechnen(con, pid):
            if a.id and z["bogen"] != a.id:
                continue
            p = prog["schritte"].get(z["aid"]) or {}
            print(f"{z['platz']:>3}. A{z['aid']:<5} {z['agent'] or '–':<10} {z['titel'][:60]:<60} {z['grund']}"
                  + (f" · P50 {p['p50']} / P85 {p['p85']}" if p.get("p50") else ""))
    elif a.aktion == "zeitplan":                      # A2045 (V7): geplante Start- und Endzeit je Paket
        from . import zeitplan
        z = zeitplan.berechnen(con, pid)
        bogen = {r[0]: r[1] for r in con.execute("SELECT id, bogen_id FROM aufgabe WHERE projekt_id = ?", (pid,))}
        print(f"Zeitplan · jetzt {_zeit(z['jetzt'])} · {z['plaetze']} Headless-Platz/Plätze")
        for x in z["pakete"]:
            if a.id and bogen.get(x["aid"]) != a.id:
                continue
            print(f"{x['platz']:>3}. {zeitplan.zeile(x)} · {x['agent'] or ('Headless' if x['art'] == 'headless' else '–')} · {x['titel'][:60]}")
    elif a.aktion == "zeigen":
        b = next((x for x in planung.boegen(con, pid) if x["id"] == a.id), None)
        if not b:
            raise kern.AmwFehler(f"Meilenstein {a.id} gibt es nicht")
        print(f"Meilenstein {b['id']} [{b['status']}] {b['titel']} · Ziel: {b['ziel'] or '–'} · Abnahme: {b['abnahme'] or '–'}"
              f" · Zieldatum {b['zieldatum'] or '–'} (Baseline {b['baseline_datum'] or '–'})"
              + (f" · federführend {b['federfuehrend']}" if b.get("federfuehrend") else ""))
        from . import urteil                              # A1939 (K3): Verweise mit geltender Fassung, Themen statt Spezifikation
        for feld in ("ziel", "abnahme"):
            for v in urteil.verweise(con, pid, b[feld]):
                print(f"  {feld}: {urteil.verweis_text(v)}")
        th = urteil.bogen_themen(con, pid, a.id)
        if th:
            from . import themen
            print("Themen: " + " · ".join(f"TH{x['id']} {x['name']} ({themen.STATUS_TEXT.get(x['status'], x['status'])})" for x in th))
        if b["spec"]:
            stand = {"entwurf": "in Arbeit", "zurueck": "zurück"}
            print("Spezifikation (alter Bestand): " + ", ".join(f"{t} {stand.get(b['spec'].get(t), b['spec'].get(t) or '–')}" for t in planung.TEILE))
        from . import reihenfolge                         # A1941: Abweichung gegenüber dem Plan-Stand beim Start
        ab = reihenfolge.abweichung(con, pid, a.id)
        if ab:
            print(f"Abweichung seit dem Start ({ab['seit'][:16].replace('T', ' ')}): Meilenstein {ab['bogen']:+d} Tage" if ab["bogen"] is not None
                  else "Abweichung: keine Prognose")
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
                  + (f" · seit Start {b['zuwachs']['seit'][:10]}: +{b['zuwachs']['neu']} neu, {b['zuwachs']['erledigt']} erledigt, {b['zuwachs']['offen']} offen"
                     if b.get("zuwachs") else "")
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


def _frage_optionen(liste):
    """--option „A=Text“ (auch „A: Text“) → [(kenn, text)]."""
    optionen = []
    for o in liste or []:
        kenn, gleich, text = o.partition("=")
        m = None if gleich and text.strip() else re.match(r"\s*([^\s=:)]{1,12})\s*[:)]\s+(.+)", o, re.S)
        if m:                                   # „V0: Text“ statt „V0=Text“ – gemeint ist dasselbe
            kenn, text = m.groups()
        optionen.append((kenn.strip(), text.strip()))
    return optionen


def cmd_frage(a, con):
    pid = _projekt(con, a)
    if a.aktion == "neu":
        if not (a.an and (a.kurz or "").strip()):
            raise kern.AmwFehler("frage neu braucht --an entwickler|tl und --kurz \"die Frage in einem Satz\""
                                 " (--text gibt es nur bei antworten/nachtrag)")
        optionen = _frage_optionen(a.option)
        from . import dokumente
        anhaenge = dokumente.anhaenge_pruefen(con, pid, a.anhang or [], [k for k, _ in optionen])   # vor dem Anlegen
        fid = kern.frage_neu(con, pid, _von(a), a.an, a.kurz, optionen, a.empfehlung, a.grund, a.worum,
                             a.fundstellen, a.aufgabe, a.blockiert, geprueft=a.geprueft,
                             buendel=[x for x in (a.buendeln or "").replace(";", ",").split(",") if x.strip()] or None)
        if a.an == "tl":                            # an den Lead: Treffer nur zeigen
            liste = wissen.treffer(con, pid, f"{a.kurz} {a.worum or ''}")
            if liste:
                print("Vielleicht schon entschieden:\n" + wissen.treffer_text(liste))
        zusatz = dokumente.anhaenge_setzen(con, pid, _von(a), fid, anhaenge)
        print(f"F{fid} angelegt" + (" – Varianten: " + ", ".join(f"{k}=D{d}" for k, d in zusatz.items()) if zusatz else ""))
        if a.an == "entwickler" and con.execute("SELECT an FROM frage WHERE id = ?", (fid,)).fetchone()[0] == "tl":
            print(f"→ geht an den Lead {kern.lead(con, pid)} – den Entwickler fragt nur der Lead (A2021); er beantwortet sie selbst"
                  " oder stellt sie ihm, auch gebündelt mit anderen")
    elif a.aktion == "weiterleiten":
        if not a.id:
            raise kern.AmwFehler("frage weiterleiten <nr> [--text \"Notiz\"] [--kurz … --worum … --option A=… --empfehlung A --grund …]")
        kern.frage_weiterleiten(con, pid, _von(a), a.id, a.text, kurz=a.kurz, worum=a.worum,          # A2021: vorher überarbeiten
                                optionen=_frage_optionen(a.option) or None, empfehlung=a.empfehlung, grund=a.grund)
        print(f"F{a.id} an den Entwickler weitergeleitet – er sieht sie als deine Frage")
    elif a.aktion in ("parken", "aufnehmen"):
        if not a.id:
            raise kern.AmwFehler(f"frage {a.aktion} <nr> [--grund \"…\"]")
        print(f"F{a.id} → {kern.frage_parken(con, pid, _von(a), a.id, a.aktion == 'parken', a.grund)}")
    elif a.aktion == "liste":
        if a.geparkt:
            for r in kern.offene_fragen(con, pid, a.an, geparkt=True):
                print(f"F{r['id']} an {r['an']} von {r['von']}: {r['kurz']}  (geparkt {_zeit(r['geparkt_utc'])} von {r['geparkt_von']})")
            return
        from . import fragentopf
        for r in kern.offene_fragen(con, pid, a.an):
            opt = " · ".join(f"{o['kenn']}) {o['text']}" for o in json.loads(r["optionen"]))
            h = fragentopf.haengt(con, pid, r["id"])         # A1945 (K10): was an der Frage hängt
            print(f"F{r['id']} an {r['an']} von {r['von']}{' BLOCKIERT' if r['blockiert'] else ''}: {r['kurz']}"
                  + (f"\n   {opt}" if opt else "") + (f"  → Empfehlung {r['empfehlung']}" if r["empfehlung"] else "")
                  + ("\n   hängt: " + ", ".join(f"A{x['aufgabe']}" + (f" ({x['agent']})" if x["agent"] else "") for x in h) if h else ""))
    elif a.aktion == "nachtrag":                    # Fragesteller: Antwort auf eine Rückfrage oder Ergänzung
        if not a.id or not a.text:
            raise kern.AmwFehler("frage nachtrag <nr> --text \"…\"")
        print(f"Nachtrag zu F{a.id} – Nachricht #{kern.frage_nachtrag(con, pid, _von(a), a.id, a.text)}")
    elif a.aktion == "zeige":                            # A1780: ganze Frage mit Optionen und Antwort ohne SQL
        if not a.id:
            raise kern.AmwFehler("frage zeige <nr>")
        f = con.execute("SELECT * FROM frage WHERE id = ? AND projekt_id = ?", (a.id, pid)).fetchone()
        if not f:
            raise kern.AmwFehler(f"F{a.id} gibt es nicht")
        status = f"geparkt seit {_zeit(f['geparkt_utc'])}" if f["geparkt_utc"] and f["status"] == "offen" else f["status"]
        print(f"F{f['id']} ({status}) an {f['an']} · {_zeit(f['zeit_utc'])} {f['von']}" + (f" · A{f['aufgabe_id']}" if f["aufgabe_id"] else "")
              + (" · blockiert" if f["blockiert"] else ""))
        print(f["kurz"])
        if f["worum"]:
            print("Worum: " + f["worum"])
        for o in json.loads(f["optionen"] or "[]"):
            print(f"  {o.get('kenn')}) {o.get('text')}" + ("  ← Empfehlung" if o.get("kenn") == f["empfehlung"] else ""))
        if f["grund"]:
            print("Grund: " + f["grund"])
        if f["antwort"]:
            print(f"Antwort ({f['antwort_art']}, {_zeit(f['antwort_utc'])}): {f['antwort']}")
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
    _nicht_als_mensch_aus_sitzung(a, "halt")          # A2038: der Lead hält mit eigenem Namen an, der Mensch nur im eigenen Terminal
    sid = kern.halt(con, _projekt(con, a), _von(a), a.fuer, a.text)
    print(f"Halt #{sid} für {a.fuer} gesetzt; STOPP verschickt")


def cmd_pause(a, con):
    """A2042: eine Pause für alles – Halt (alle), Wächter-Pause und Lauf-Schlange, mit Ende; Rückmeldung je Agent."""
    from . import pause
    pid = _projekt(con, a)
    if a.aktion == "zeige":
        z = pause.zustand(con, pid)
        if not z["an"]:
            print("Keine Pause")
            return
        print(f"Pause seit {_zeit(z['seit'])}" + (f" bis {_zeit(z['bis'])}" if z["bis"] else " (bis „amw pause aus“)") + f" – {z['grund']}")
        for x in z["agenten"]:
            print(f"  {x['kennung']:<14} {x['zustand']}")
        for x in z["pakete"]:
            print(f"  A{x['aid']:<13} {x['zustand']} – {x['titel'][:60]}")
        for x in z["laeufe"]:
            print(f"  L{x['lauf']:<13} {x['zustand']} – {x['beschreibung'][:60]}")
        return
    _nicht_als_mensch_aus_sitzung(a, f"pause {a.aktion}")
    if a.aktion == "an":
        r = pause.an(con, pid, _von(a), pause.bis_aus(a.bis), a.grund)
        print("Pause an – Halt für alle, keine neuen Headless-Pakete und Läufe" + (f", bis {_zeit(r['bis'])}" if r["bis"] else "")
              + ". Rückmeldung: amw pause zeige")
    else:
        pause.aus(con, pid, _von(a))
        print("Pause aus – alle bekommen „weiter“")


def cmd_weiter(a, con):
    _nicht_als_mensch_aus_sitzung(a, "weiter")
    n = kern.weiter(con, _projekt(con, a), _von(a), a.fuer)
    print(f"{n} Halt aufgehoben" if n else "kein Halt aktiv")


def cmd_taetigkeit(a, con):
    kern.taetigkeit(con, _projekt(con, a), _von(a), " ".join(a.text), a.aufgabe)
    print("Tätigkeit gesetzt" if a.text else "Tätigkeit gelöscht")


ART_FEHLT = ("Gib an, ob der Lauf leicht (normales Coding/Tests, läuft parallel) oder schwer ist (KI/GPU/Fenster/viel"
             " Speicher, läuft einzeln): --leicht | --schwer")


def _schwer(a, rezept=None, dauerlauf=False):
    """A1822 (Marcel 16.11. 10:45): keine Vorgabe – leicht oder schwer gibt der Agent an. Ein Rezept trägt die Art fest,
    ein Dauerlauf ist leicht. Rückgabe: True = schwer."""
    if getattr(a, "leicht", False) and getattr(a, "schwer", False):
        raise kern.AmwFehler("--leicht oder --schwer – nicht beides")
    if dauerlauf and getattr(a, "schwer", False):
        raise kern.AmwFehler("Ein Dauerlauf ist immer leicht – --schwer passt nicht")
    if rezept or dauerlauf:
        return True                                      # lauf_start nimmt die Art aus dem Rezept bzw. setzt Dauerlauf leicht
    if not (getattr(a, "leicht", False) or getattr(a, "schwer", False)):
        raise kern.AmwFehler(ART_FEHLT)
    return bool(a.schwer)


def _messung_zeile(m):
    from . import messung
    namen = {"vor_start": "vor dem Start", "nach_abgabe": "nach der Abgabe", "frage": "Frage", "aufgabe": "andere Aufgabe", "lauf": "Lauf",
             "agent": "Agent/Prüfung", "entwickler": "Entwickler", "monitor": "Beobachtung"}
    w = ", ".join(f"{namen.get(k, k)} {messung.dauer(v)}" for k, v in sorted(m["warten"].items(), key=lambda x: -x[1]))
    return (f"aktiv {messung.dauer(m['aktiv_s'])} · wartet {messung.dauer(m['warten_s'])}"
            + (f" ({w})" if w else "") + f" · {m['usd']:.2f} $" + (" – noch offen" if m["offen"] else ""))


def cmd_skills(a, con):
    """A1956: die Hilfe-Seiten als Skills ins Repo schreiben (Quelle bleibt doc/hilfe)."""
    from . import skills
    namen, verwaist = skills.bauen(os.path.join(a.ziel, ".claude", "skills") if a.ziel else skills.ZIEL)
    ziel = a.ziel or skills.WURZEL
    print(f"{len(namen)} Skills in {ziel}" + (f" · ohne Hilfe-Seite (liegen gelassen): {', '.join(verwaist)}" if verwaist else ""))


def cmd_messung(a, con):
    if getattr(a, "hebel7", False):                  # A1956 (TH168 Hebel 7): Startkontext und Kosten je Agent
        from . import skills
        pid = _projekt(con, a)
        if a.basis and not kern.ist_lead(con, pid, _von(a)):
            raise kern.AmwFehler("Die Basis halten Lead oder Mensch fest")
        m = skills.basis_merken(con, pid, _von(a)) if a.basis else skills.kontext_masse(con, pid)
        for x in m:
            print(f"{x['agent']:<14} Kontext {x['kontext_zeilen']:>3} Zeilen / {x['kontext_zeichen']:>6} Zeichen · Regeln"
                  f" {x['regeln_zeilen']:>3} / {x['regeln_zeichen']:>6} · Paket-Median "
                  + (f"{x['usd_median']:.2f} $ (n={x['n']})" if x["usd_median"] is not None else "–"))
        if a.basis:
            print("als Basis festgehalten (basis_hebel7)")
        return
    """A1844: Wartezeit und Kosten je Aufgabe – nur lesen."""
    from . import messung
    pid = _projekt(con, a)
    if getattr(a, "prognose", False):                # A2046 (V8): Schätzung gegen Ist, Trefferquote
        from . import prognosemessung
        seit = (a.seit.strip() if re.fullmatch(r"\d{4}-\d{2}-\d{2}T[\d:]+Z?", a.seit.strip()) else _datum(a.seit)) if a.seit else None
        q = prognosemessung.trefferquote(con, pid, seit)
        if not q["n"]:
            print("Noch keine Messung – die AMW hält Schätzung und Ist je fertigem Paket fest (ab dem nächsten Ende).")
            return
        r = prognosemessung.IM_RAHMEN
        print(f"Trefferquote {round(q['quote'] * 100)} % ({q['treffer']} von {q['n']} Paketen im Rahmen {1 / r:.2g}–{r:g}×)"
              f" · Faktor Ist/Schätzung Median {q['faktor_median']:g} · zu lang {q['zu_lang']} · zu kurz {q['zu_kurz']}")
        for k, v in q["je_quelle"].items():
            print(f"  {k:<10} {round(v['quote'] * 100):>3} % von {v['n']:>3} · Median ×{v['faktor_median']:g}")
        for x in q["pakete"][-10:]:
            print(f"  A{x['aufgabe']:<5} geschätzt {x['schaetzung_h']:g} h ({x['quelle']}) · gebraucht {x['ist_h']:g} h · ×{x['faktor']:g}")
        return
    if getattr(a, "gesamt", False):                  # A2040: Summe und Rest je Projekt
        k = messung.projekt_kosten(con, pid)
        print(f"Kosten bisher {k['bisher']:.2f} $ (Fenster-Agenten {k['fenster_usd']:.2f} $ · Headless und erfasst {k['erfasst_usd']:.2f} $)"
              f" · noch ≈ {k['noch']:.2f} $ · gesamt ≈ {k['gesamt']:.2f} $")
        print(f"  {k['offen']} offene Pakete, davon {k['ohne_schaetzung']} ohne Schätzung (zu wenig Messungen gleicher Größe und Art)"
              + (f" · {k['unbekannt']} Läufe ohne Kostenangabe" if k["unbekannt"] else ""))
        return
    if getattr(a, "p", False):                       # A2004: Anteil p je Tag, Kosten p gegen interaktiv
        q = messung.p_quote(con, pid, tage=a.tage or 7)
        ziel = f"Ziel ≥ {round(q['ziel'] * 100)} %"
        print(f"Anteil p (letzte {a.tage or 7} Tage): " + (f"{q['p']} von {q['n']} = {round(q['anteil'] * 100)} % · {ziel}"
                                                          + (" – erreicht" if q["anteil"] >= q["ziel"] else " – darunter")
                                                          if q["n"] else f"keine fertigen Pakete · {ziel}"))
        for t in q["tage"]:
            print(f"  {t['tag']}: {t['p']} von {t['n']} p ({round(t['anteil'] * 100)} %)")
        for k, name in (("p", "p"), ("interaktiv", "interaktiv")):
            w = q["kosten"][k]
            print(f"  Kosten {name}: " + (f"Median {w['median']:.2f} $ · Summe {w['summe']:.2f} $ · n = {w['n']}" if w["n"] else "–")
                  + "".join(f" · {txt} Median {messung.dauer(w[s])}" for s, txt in (("vor_start_median_s", "vor dem Start"),
                                                                                    ("nach_abgabe_median_s", "nach der Abgabe")) if w.get(s)))
        return
    if a.nr:
        m = messung.je_aufgabe(con, pid, int(str(a.nr).lstrip("Aa")))
        if not m:
            raise kern.AmwFehler(f"A{a.nr} gibt es nicht")
        print(f"A{str(a.nr).lstrip('Aa')}: {_messung_zeile(m)}")
        if m["zaehler"]:
            print(f"  Kosten-Zähler {m['agent']}: {m['zaehler']['usd']:.2f} $" + (f" ({', '.join(m['zaehler']['modelle'])})" if m["zaehler"]["modelle"] else ""))
        for e in m["erfasst"]:
            print(f"  erfasst {_zeit(e['zeit_utc'])} {e['von']}: " + ("unbekannt" if e.get("unbekannt") else f"{e['usd']:.2f} $")
                  + "".join(f" · {k} {e[k]}" for k in ("turns", "dauer_s", "eingabe", "cache_schreiben", "cache_lesen", "ausgabe", "denken",
                                                       "modell") if e.get(k))
                  + (f" – {e['notiz']}" if e.get("notiz") else ""))
        for l in m["luecken"]:
            print(f"  Lücke: {l}")
        return
    if a.vergleich:
        v = messung.vergleich(con, pid)
        for k, name in (("diese", "letzte 7 Tage"), ("vorher", "7 Tage davor")):
            x = v[k]
            print(f"{name:<14} {x['n']:>3} fertige Aufgaben · Kosten Median {x['usd_median'] if x['usd_median'] is not None else '–'} $"
                  f" (Summe {x['usd_summe']:.2f} $) · wartet Median {messung.dauer(x['warten_median_s'] or 0)}"
                  f" · aktiv Median {messung.dauer(x['aktiv_median_s'] or 0)} · mit Lücken {x['mit_luecken']}")
        return
    zeilen = messung.liste(con, pid, seit=(a.seit.strip() if re.fullmatch(r"\d{4}-\d{2}-\d{2}T[\d:]+Z?", a.seit.strip()) else _datum(a.seit)) if a.seit else None, agent=a.agent)
    if not zeilen:
        print("Keine begonnenen Aufgaben im Zeitraum")
    for m in zeilen:
        print(f"A{m['id']} {m['agent'] or '–':<8} {_messung_zeile(m)} · {m['titel'][:60]}"
              + (f"  [Lücken: {len(m['luecken'])}]" if len(m["luecken"]) > 1 else ""))
    if zeilen:
        print(f"Summe: {sum(m['usd'] for m in zeilen):.2f} $ · aktiv {sum(m['aktiv_s'] for m in zeilen) / 3600:.1f} h"
              f" · wartet {sum(m['warten_s'] for m in zeilen) / 3600:.1f} h")


def cmd_kosten(a, con):
    """A1844: Kosten eines Laufs außerhalb der Sitzungs-Zähler (claude -p …) einer Aufgabe zuordnen."""
    from . import messung
    pid = _projekt(con, a)
    text = None
    if a.json:
        with open(a.json, encoding="utf-8-sig") as f:
            text = f.read()
    e = messung.erfassen(con, pid, _von(a), int(str(a.aufgabe).lstrip("Aa")), usd=a.usd, unbekannt=a.unbekannt, json_text=text, notiz=a.notiz)
    print(f"A{str(a.aufgabe).lstrip('Aa')}: " + ("Lauf ohne Kostenangabe als Lücke vermerkt" if e.get("unbekannt") and "usd" not in e
                                                else f"{e['usd']:.2f} $ erfasst"))


def cmd_waechter(a, con):
    """A1847: Wächter für p-Pakete – prüfen (darf A starten?), protokoll, reihenfolge, zustand; wartung an|aus, weiter (Lead/Mensch)."""
    from . import waechter
    pid = _projekt(con, a)
    if a.aktion == "pruefen":
        if not a.nr:
            raise kern.AmwFehler("amw waechter pruefen <Aufgabe>")
        aid = int(str(a.nr).lstrip("Aa"))
        r = waechter.pruefen(con, pid, aid)
        print(f"A{aid}: " + ("darf starten (Regel 6 prüft der Starter am Platz)" if r["ok"] else
                             f"nicht gestartet, Regel {r['regel']}: {r['grund']}" + (" – später erneut" if r["warten"] else "")
                             if r["regel"] else r["grund"]))
        return
    if a.aktion == "protokoll":
        zeilen = waechter.protokoll(con, pid, int(str(a.nr).lstrip("Aa")) if a.nr else None)
        print("\n".join(f"{_zeit(z['zeit_utc'])}  {z['text']}" for z in zeilen) or "Noch keine Einträge")
        return
    if a.aktion == "reihenfolge":
        r = waechter.reihenfolge(con, pid)
        print("\n".join(f"{i}. A{x['id']} (Platz {x['platz'] if x.get('platz') is not None else '–'} der Reihenfolge, Rang"
                        f" {x['rang'] if x['rang'] is not None else '–'}) {x['titel'][:70]}" for i, x in enumerate(r, 1))
              or "Kein startklares p-Paket ohne offene Vorgänger")
        return
    if a.aktion == "zustand":
        z = waechter.zustand()
        print("Wartungsmodus: " + (f"an seit {_zeit(z['wartung']['seit'])} – {z['wartung'].get('grund') or ''}" if z["wartung"] else "aus"))
        print("Pause: " + (f"an seit {_zeit(z['pause']['seit'])} – {z['pause'].get('grund') or ''}" if z["pause"] else "aus"))
        return
    if not kern.ist_lead(con, pid, _von(a)):
        raise kern.AmwFehler("Wartungsmodus und Pause schalten Lead und Mensch")
    if a.aktion == "wartung":
        if a.nr == "an":
            waechter.wartung_an(a.grund or f"von Hand ({_von(a)})")
            print("Wartungsmodus an – keine neuen p-Starts, Laufendes läuft zu Ende")
        elif a.nr == "aus":
            waechter.wartung_aus()
            print("Wartungsmodus aus")
        else:
            raise kern.AmwFehler("amw waechter wartung an|aus")
        return
    waechter.weiter(con, _projekt(con, a), _von(a))
    print("Wartungsmodus und Pause aufgehoben – p-Pakete dürfen wieder starten (nach den übrigen Regeln)")


def cmd_claude(a, con):
    """A1906: Claude-Code-Versionen der Arbeiter – status (installiert, geprüft, Proben) | freigeben X.Y.Z --grund (Sperre wie
    agent lead; nur nach einer nicht bestandenen oder unklaren Probe nötig – sonst prüft und gibt die AMW selbst frei)."""
    from . import versionsprobe
    pid = _projekt(con, a)
    if a.aktion == "freigeben":
        _rolle_nur_mensch_oder_lead(con, pid, a, "Claude-Code-Version freigeben")
        v = versionsprobe.freigeben(con, pid, _von(a), a.version, a.grund)
        print(f"Claude Code {v} freigegeben (von Hand, {_von(a)}) – ein Wartungsmodus bleibt an, bis ihn der Lead aufhebt")
        return 0
    s = versionsprobe.status(con)
    i = s["installiert"]
    print(f"Installiert: Claude Code {i or 'unbekannt'}" + ("" if not i else " – geprüft" if i in s["geprueft"]
                                                             else " – NICHT geprüft: Arbeiter starten nicht (Regel 11), die AMW prüft selbst"))
    print(f"Grundbestand: {', '.join(s['grundbestand'])}")
    for e in s["eingetragen"]:
        print(f"Geprüft {e['version']}: {e['zeit_utc'][:16].replace('T', ' ')} · "
              + (f"von Hand ({e.get('von')}): {e.get('grund')}" if e.get("hand") else f"Probe D{e.get('dokument')}, L{e.get('lauf')}"))
    for e in s["proben"]:
        print(f"Probe {e['version']}: {e['zeit_utc'][:16].replace('T', ' ')} · {e.get('schritt')}"
              + (f" · {e.get('ergebnis')} · D{e.get('dokument')}" if e.get("schritt") == "ende" else ""))
    return 0


PC_NUR_MENSCH = ("projekt_rang",)                         # A1925 (E1): nur der Mensch im eigenen Terminal
PC_LEAD_ODER_MENSCH = ("plaetze_pc", "limit_halt")        # A1925 (E2, E4): Lead oder Mensch, gesperrt wie RECHTE_EINSTELLUNGEN


def cmd_sicherung(a, con):
    """A1929: tägliche Sicherung aller Zweige und Tags – zeigen | jetzt (Lead oder Mensch, ein Push von Hand)."""
    from . import sicherung
    pid = _projekt(con, a)
    if a.aktion == "jetzt":
        _rolle_nur_mensch_oder_lead(con, pid, a, "Sicherung von Hand")
        e = sicherung.pushen(con, pid, _von(a))
        print(f"Sicherung nach {e['ziel']}: {e['refs']} Refs, rc {e['rc']}" + (f" – abgewiesen: {', '.join(e['abgewiesen'])}" if e["abgewiesen"] else ""))
        return
    z = sicherung.ziel(con, pid)
    l = sicherung.letzte(con, pid)
    print(f"Ziel: {sicherung.anzeige(z) if z else 'keins (amw projekt einstellen sicherung_ziel=… – Lead oder Mensch)'}")
    if l:
        print(f"Zuletzt: {l['zeit_utc'][:16].replace('T', ' ')} · {l.get('refs')} Refs · rc {l.get('rc')}"
              + (f" · abgewiesen: {', '.join(l['abgewiesen'])}" if l.get("abgewiesen") else ""))


def cmd_empfehlung(a, con):
    """A1930 (TH159): Eignungstabelle – je Zelle (Gruppe × Größe) und Modell/Effort: Anzahl, Anteil ohne Nacharbeit, Median Kosten
    und Dauer, Pakettypen; dazu, was die Empfehlung nimmt (Projektwert, gemessen oder Startwert)."""
    from . import eignung, empfehlung
    pid = _projekt(con, a)
    t = eignung.tabelle(con, pid)
    h = empfehlung.herkunft(con, pid)
    print(f"Eignungstabelle – gemessen ersetzt den Startwert ab {eignung.MIN_N} Aufgaben je Paar; ohne Nacharbeit nach F5362")
    for g in empfehlung.GRUPPEN:
        for gr in empfehlung.GROESSEN:
            w, woher = h[g][gr]
            print(f"\n{g} · {gr}: Empfehlung {w} ({ {'projekt': 'vom Projekt gesetzt', 'gemessen': 'gemessen', 'start': 'Startwert'}[woher] })")
            for paar, x in sorted((t.get((g, gr)) or {}).items(), key=lambda p: -p[1]["n"]):
                kosten = f"{x['kosten_median']:.2f} $" if x["kosten_median"] is not None else "– $"
                dauer = f"{x['dauer_median_s'] / 60:.0f} min" if x["dauer_median_s"] is not None else "– min"
                typen = ", ".join(f"{k} {n}" for k, n in sorted(x["pakettypen"].items()))
                print(f"  {'→' if paar == w else ' '} {paar:<16} n {x['n']:<3} ohne Nacharbeit {x['ohne_anteil'] * 100:.0f} %"
                      f" · Median {kosten} · {dauer} · {typen}")


def cmd_anbieter(a, con):
    """A1931 (TH159): Anbieter je Projekt – liste | freigeben NAME --url … --schluessel-datei … --modelle … [--lokal] |
    entfernen NAME. Freigeben und entfernen nur der Mensch im eigenen Terminal (auch nicht der Lead). Nie der Schlüssel selbst."""
    from . import anbieter, versionsprobe
    pid = _projekt(con, a)
    if a.aktion in ("freigeben", "entfernen"):
        if _von(a) != kern.ENTWICKLER or _aus_agenten_sitzung():
            raise kern.AmwFehler("Anbieter gibt nur der Mensch frei oder entfernt sie – im eigenen Terminal mit --von Entwickler")
        if not a.name:
            raise kern.AmwFehler(f"amw anbieter {a.aktion} <name> …")
        if a.aktion == "entfernen":
            print(f"Anbieter {anbieter.entfernen(con, pid, _von(a), a.name)} entfernt – Pakete mit ihm starten nicht mehr (Regel 13)")
            return
        name, e = anbieter.freigeben(con, pid, _von(a), a.name, a.url, a.schluessel_datei, a.lokal,
                                     [m for m in (a.modelle or "").split(",")])
        print(f"Anbieter {name} freigegeben: {e['basis_url']} · Schlüsseldatei {e['schluessel_datei']} · Modelle {', '.join(e['modelle'])}"
              + (" · lokal (Grafikkarte – startet erst mit der Lauf-Schlange für gpu)" if e["lokal"] else "")
              + " – vor dem ersten Paket prüft die AMW ihn selbst (Negativprobe)")
        return
    v = versionsprobe.installiert()
    print("anthropic: Standard (ohne Eintrag freigegeben)")
    for name, e in sorted(anbieter.liste(con, pid).items()):
        geprueft = v and versionsprobe.anbieter_geprueft(con, name, v)
        print(f"{name}: {e.get('basis_url')} · Schlüsseldatei {e.get('schluessel_datei')} · Modelle {', '.join(e.get('modelle') or [])}"
              + (" · lokal" if e.get("lokal") else "") + f" · Claude Code {v or '?'}: {'geprüft' if geprueft else 'noch nicht geprüft'}")


def cmd_pc(a, con):
    """A1925: Einstellungen dieses PCs, die der Disponent über alle Projekte nutzt – zeigen | einstellen k=v."""
    from . import disponent, einstellungen, waechter
    if a.aktion == "einstellen":
        if not a.wert or "=" not in a.wert:
            raise kern.AmwFehler("amw pc einstellen projekt_rang=AMW,GlassWorld,LayerIT | plaetze_pc=2 | limit_halt=90")
        k, _, v = a.wert.partition("=")
        k = k.strip()
        if k in PC_NUR_MENSCH:
            if _von(a) != kern.ENTWICKLER or _aus_agenten_sitzung():
                raise kern.AmwFehler(f"{k}: stellt nur der Mensch im eigenen Terminal ein (--von Entwickler, nicht aus einer Agenten-Sitzung)")
        elif k in PC_LEAD_ODER_MENSCH:
            _rolle_nur_mensch_oder_lead(con, _projekt(con, a), a, f"{k} setzen")
            if k == "limit_halt" and _von(a) != kern.ENTWICKLER:      # P392 (#29892): der Lead nur strenger
                try:
                    neu = int(v.strip() or 0)
                except ValueError:
                    neu = None
                alt = einstellungen.wert("limit_halt")
                if neu is not None and (neu == 0 or (alt and neu > alt)):
                    raise kern.AmwFehler(f"limit_halt: ausschalten oder lockern (jetzt {alt or 'aus'}) nur der Mensch im eigenen"
                                         " Terminal – der Lead stellt ihn nur strenger")
        else:
            raise kern.AmwFehler(f"{k}: hier nur {', '.join(PC_NUR_MENSCH + PC_LEAD_ODER_MENSCH)} – die übrigen im Zahnrad › Dieser PC")
        try:
            print(f"{k} = {einstellungen.speichern({k: v.strip()})[k]}")
        except ValueError as e:
            raise kern.AmwFehler(str(e)) from None
        return
    pc = waechter.pc_belegt(con)
    print(f"Rangfolge: {', '.join(n for _, n in disponent.projekt_reihe(con))}"
          + ("" if einstellungen.wert("projekt_rang") else " (ohne projekt_rang: nach Nummer)"))
    print(f"p-Arbeiter: {len(pc['arbeiten'])}" + (f" von {pc['grenze']} (plaetze_pc)" if pc["grenze"] else " (keine gemeinsame Grenze)")
          + "".join(f" · {n} A{x}" for n, x in pc["arbeiten"]))
    print(f"Halt beim Wochenlimit: {einstellungen.wert('limit_halt') or 'aus'} % für alle Projekte (ein Projekt nur strenger)")
    seit = disponent.wochenbeginn()
    for nr, (pid, name) in enumerate(disponent.projekt_reihe(con), 1):
        from . import platz
        k = disponent.kosten_woche(con, pid, seit)
        print(f"{nr}. {name}: Schalter {kern.projekt_schalter(con, pid)} · {len(platz.plaetze(con, pid))} Plätze · diese Woche"
              f" {k['usd']:.2f} $ in {k['pakete']} Paket(en)")


def cmd_platz(a, con):
    """A1855: Arbeitsplätze für -p – zeigen, vorbereiten, zurücksetzen (Lead und Mensch)."""
    from . import platz
    pid = _projekt(con, a)
    ps = platz.plaetze(con, pid)
    if a.aktion == "liste":
        if not ps:
            print("Keine Arbeitsplätze (Projekt-Einstellung plaetze = 0 oder platz_wurzel fehlt) – die AMW arbeitet wie bisher")
        else:
            w = os.path.dirname(ps[0]["klon"])
            arch, loe = platz.groesse(os.path.join(w, "_archiv")), platz.groesse(os.path.join(w, "_loeschen"))
            print(f"Archiv {arch / 2 ** 20:.1f} MB · zum Löschen {loe / 2 ** 20:.1f} MB in {os.path.join(w, '_loeschen')}"
                  + (" – leeren kann nur der Mensch" if loe else ""))
        for p in ps:
            da = os.path.isdir(os.path.join(p["klon"], ".git"))
            print(f"Platz {p['nr']}: {p['klon']} · Daten {p['daten']} · Port {p['port']} · "
                  + (("sauber" if platz.sauber(p) else "nicht sauber") if da else "noch nicht angelegt"))
        return
    if a.aktion == "notbremse":                       # A1848: nur der Mensch – beendet den Arbeiter samt Kindern
        from . import arbeiter
        if KANAL.get() != "cli":                      # wie der Agentenstart (A1865): nur an der Befehlszeile des PCs
            raise kern.AmwFehler("Die Notbremse zieht nur der Mensch an diesem PC (amw platz notbremse N --von Entwickler)")
        p = next((x for x in ps if x["nr"] == a.nr), None)
        if not p:
            raise kern.AmwFehler(f"Platz {a.nr} gibt es nicht ({len(ps)} eingerichtet)")
        print(arbeiter.notbremse_ziehen(con, pid, p, _von(a), a.aufgabe))
        return
    if not kern.ist_lead(con, pid, _von(a)):
        raise kern.AmwFehler("Arbeitsplätze vorbereiten und zurücksetzen dürfen Lead und Mensch")
    if a.aktion == "aufraeumen":
        if not ps:
            raise kern.AmwFehler("Keine Arbeitsplätze eingerichtet")
        n = platz.aufraeumen(con, pid, os.path.dirname(ps[0]["klon"]))
        print(f"{len(n)} Archiv(e) fertiger Pakete nach _loeschen verschoben" + (f": {', '.join(n)}" if n else ""))
        return
    p = next((x for x in ps if x["nr"] == a.nr), None)
    if not p:
        raise kern.AmwFehler(f"Platz {a.nr} gibt es nicht ({len(ps)} eingerichtet)")
    if a.aktion == "vorbereiten":
        quelle = kern.projekt_ordner(con, pid)
        if not quelle:
            raise kern.AmwFehler("Das Projekt hat keinen Ordner (amw projekt ordner …)")
        r = platz.vorbereiten(p, quelle, a.zweig or f"platz{p['nr']}", aufgabe=a.aufgabe)
        print(f"Platz {p['nr']} bereit: {r['klon']} · Zweig {r['zweig']} ab main {r['basis'][:8]} · Port {p['port']}")
    else:
        r = platz.zuruecksetzen(p, projektordner=kern.projekt_ordner(con, pid), aufgabe=a.aufgabe)
        print(f"Platz {p['nr']} " + ("sauber" if r["sauber"] else "NICHT sauber – bitte ansehen")
              + (f" · Reste im Archiv: {r['archiv']}" if r["archiv"] else " · nichts zu sichern"))


def cmd_mcp(a, con):
    """A1826: Schlüssel je Projekt für den MCP-Server – nur der Mensch, nur im Terminal (nie über Dateiaustausch/Connector)."""
    from . import mcp_schluessel
    pid = _projekt(con, a)
    name = db.projekt_name(con, pid)
    lead = kern.lead(con, pid) or "TL"
    if a.aktion == "eintrag":
        st = mcp_schluessel.stand(name)
        print(mcp_schluessel.eintrag(name, lead))
        print("Schlüssel: " + (f"erzeugt {_zeit(st['erzeugt_utc'])}" if st["da"] else "noch keiner – amw mcp schluessel"))
        return
    if (KANAL.get() != "cli" or _von(a) != kern.ENTWICKLER or os.environ.get("AMW_AGENT")
            or os.environ.get("CLAUDE_CODE_MESSAGING_SOCKET")):    # nie aus einer Agenten-/Claude-Sitzung
        raise kern.AmwFehler("Den MCP-Schlüssel erzeugt nur der Mensch im Terminal (--von Entwickler) oder in der Workbench am PC")
    s = mcp_schluessel.erzeugen(name)
    print(f"Neuer Schlüssel für Projekt {name} (ein alter gilt ab jetzt nicht mehr) – nur jetzt sichtbar, nirgends gespeichert:")
    print(s)
    print("Trag ihn in die Projekt-Anweisungen des Lead-Chats dieses Projekts ein, z. B.: ‚AMW-Schlüssel: " + s + "‘."
          " Eintrag für claude_desktop_config.json: " + mcp_schluessel.eintrag(name, lead))


def cmd_takt(a, con):
    """Ein Durchgang für einen Lead in einem Aufruf (A1780)."""
    from . import takt
    seit = None
    if a.seit:
        seit = _datum(a.seit) if len(a.seit) > 5 else None
        if seit is None:                                 # nur Uhrzeit (HH:MM): heute, lokale Zeit
            import datetime
            h, m = (int(x) for x in a.seit.split(":"))
            lokal = datetime.datetime.now().replace(hour=h, minute=m, second=0, microsecond=0)
            seit = lokal.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    print(takt.takt(con, _projekt(con, a), _von(a), seit, a.abhaken, a.grenze))


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


def cmd_verbrauch(a, con):
    """Verbrauch nach Anlass (A1642): Kostenzuwachs je Sitzung → Weckrufe im selben Zeitraum, sonst eigene Arbeit."""
    from . import anlass
    pid = _projekt(con, a)
    d = anlass.anlaesse(con, pid, anlass.zeitraum(a.tage))
    print(f"Verbrauch nach Anlass, letzte {a.tage} Tage: {d['gesamt']:.2f} $ · vermeidbar {d['vermeidbar_usd']:.2f} $"
          f" · Weckrufe {d['weckrufe']}, davon vermeidbar {d['vermeidbar_weckrufe']}")
    for r in d["zeilen"]:
        je = f"{r['je_weckruf']:.2f} $/Weckruf" if r["je_weckruf"] is not None else ""
        print(f"  {r['usd']:8.2f} $ {r['anteil']:5.1f} % (bis hier {r['kumuliert']:5.1f} %)  {r['weckrufe']:4}×  {je:>16}  "
              f"{'vermeidbar · ' if r['vermeidbar'] else ''}{r['anlass']}")
    if not d["zeilen"]:
        print("  Noch keine Messwerte in diesem Zeitraum.")


def cmd_runde(a, con):
    """Lead-Runde (A1658): nur Leads, nur Information – nie Befehle an fremde Projekte."""
    from . import runde
    pid = _projekt(con, a)
    von = _von(a)
    if a.aktion == "schreiben":
        text = a.text
        if a.text_datei:
            with open(a.text_datei, encoding="utf-8") as f:
                text = f.read()
        rid = runde.schreiben(con, pid, von, a.kurz, text, a.art, a.an, a.antwort_auf)
        print(f"R{rid} in der Lead-Runde" + (f" – {a.an} bekommt eine Info in sein Postfach (weckt nicht)" if a.an else ""))
    else:
        liste, bis = runde.lesen(con, pid, von, nur_neu=a.neu)
        print(runde.text(con, pid, liste, bis))


def cmd_regeln(a, con):
    pid = _projekt(con, a)
    regeln = con.execute("SELECT ebene, nr, text, stand_utc, vorlage FROM regel WHERE projekt_id = ? ORDER BY ebene, nr", (pid,)).fetchall()
    if getattr(a, "nr", None):                       # A1956: eine Regel ganz (KR3, PR2, 3 = KR3)
        import re as _re
        m = _re.fullmatch(r"(KR|PR)?(\d+)", a.nr.strip().upper())
        if not m:
            raise kern.AmwFehler("amw regeln KR3 | PR2 | 3")
        ebene = "projekt" if m.group(1) == "PR" else "arbeit"
        regeln = [r for r in regeln if r["ebene"] == ebene and r["nr"] == int(m.group(2))]
        if not regeln:
            raise kern.AmwFehler(f"{a.nr} gibt es nicht – amw regeln")
    for r in regeln:
        grund = f" · Grundregel {r['vorlage'].split('/')[0]}" if r["vorlage"] else ""
        print(f"{'KR' if r['ebene'] == 'arbeit' else 'PR'}{r['nr']}{grund} (Stand {_zeit(r['stand_utc'])}): {r['text']}\n")
    if not regeln:
        print("Noch keine Regeln in diesem Projekt – es gilt das Leitbild (amw leitbild zeigen). Regeln entstehen aus Beschlüssen.")


def _lauf_warte(con, pid, a):
    """Blockiert, bis der Lauf dran ist: rc 0 = läuft (jetzt rechnen), 2 = abgebrochen/fertig, 3 = --hoechstens erreicht.
    Der Grund steht nur, wenn er sich ändert (höchstens einmal je Minute nachgesehen) – dazwischen gibt es nichts zu deuten:
    die AMW entscheidet, wann der Lauf dran ist (A1641)."""
    if not a.id:
        raise kern.AmwFehler("lauf warte <nr> [--hoechstens <min>]")
    ende = time.time() + a.hoechstens * 60 if a.hoechstens else None
    letzte, gesagt = 0, None
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
            grund = betrieb.wartegrund(con, pid, l)
            if grund != gesagt:
                if gesagt is None:
                    print(f"L{a.id} wartet – du musst nichts tun, die AMW startet ihn, sobald er dran ist.", flush=True)
                print(f"{time.strftime('%H:%M')} L{a.id}: {grund}", flush=True)
                gesagt = grund
        if ende and time.time() >= ende:
            print(f"L{a.id} wartet nach {a.hoechstens:g} min noch – bleibt eingereiht", flush=True)
            return 3
        time.sleep(5)


PRUEF_S = 5          # lauf ausfuehren: so oft nachsehen, ob der Bildschirm zugeht oder der Lauf beendet wurde
# Rückgabewerte von lauf ausfuehren, die nicht vom Befehl stammen (Ketten „nur weiter bei 0“ bleiben sauber)
RC_FRIST, RC_STRG_C, RC_NIE, RC_SCHIRM, RC_BEENDET = 124, 130, 200, 201, 202


def _baum_beenden(proc):
    """Den eigenen Befehl samt Kindern beenden (Prozess des Agenten, nicht der Dienst)."""
    import subprocess
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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


def _lauf_vom_dienst(con, pid, lid):
    """Der Dienst rechnet diesen Lauf (A1640): warten, bis er fertig ist, und seinen Rückgabewert durchreichen."""
    print(f"L{lid} rechnet der Dienst – warte auf das Ende", flush=True)
    while True:
        l = betrieb.lauf_zeile(con, pid, lid)
        if l["status"] in ("fertig", "abgebrochen"):
            print(f"L{lid} {l['status']}: {l['ergebnis'] or ''}", flush=True)
            return l["rc"] if l["rc"] is not None else RC_BEENDET
        time.sleep(5)


def _lauf_ausfuehren(con, pid, a):
    """Einreihen → warten → Befehl starten → Ausgabe in die Ergebnis-Datei → rc durchreichen → lauf ende. Beim Lauf mit Fenster:
    geht der Bildschirm zu oder beendet jemand den Lauf, endet der eigene Befehl (Prozessbaum) und der Lauf gilt als abgebrochen.
    rc: der des Befehls, sonst 200 = nie gestartet (aus der Schlange genommen, --hoechstens erreicht), 201 = Bildschirm zu,
    202 = Lauf von außen beendet, 124 = --frist erreicht, 130 = Strg+C."""
    import subprocess
    import threading
    befehl = getattr(a, "befehl", None) or []
    if KANAL.get() != "cli":                          # nie über Brücke/Briefkasten: der Dienst könnte den Befehl später ausführen
        raise kern.AmwFehler("lauf ausfuehren geht nur im Terminal des Agenten")
    if not befehl:
        raise kern.AmwFehler("lauf ausfuehren --leicht|--schwer --beschreibung … [--schirm] -- <befehl …> (der Befehl steht nach --)")
    beschreibung = a.beschreibung or a.rezept or " ".join(befehl)[:120]
    von = _von(a)
    from . import laufdienst
    gesamt = laufdienst.ist_gesamtlauf(con, pid, befehl, beschreibung)
    if gesamt and not a.frist:                       # A2051: ein Gesamtlauf hat immer eine Frist (Projekt-Einstellung)
        a.frist = laufdienst.gesamtlauf_frist(con, pid) or None
    lid = betrieb.lauf_start(con, pid, von, beschreibung, a.rezept, _schwer(a, a.rezept, getattr(a, "dauerlauf", False)), a.schirm, a.aufgabe, warten=True,
                             erwartet_min=a.dauer, gpu=a.gpu, braucht_gb=a.braucht_gb, braucht_vram_gb=a.braucht_vram_gb,
                             braucht_platte_gb=a.braucht_platte_gb, befehl=befehl, ordner=os.getcwd(),
                             ergebnis_datei=os.path.abspath(a.ergebnis) if a.ergebnis else None, frist_min=a.frist,
                             waechter=os.getpid(), dauerlauf=a.dauerlauf)
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
    if not betrieb.lauf_uebernehmen(con, lid, "agent"):    # der Dienst war schneller (dieser Prozess galt als tot) – A1640
        belegung.lauf_vergessen(lid)
        return _lauf_vom_dienst(con, pid, lid)
    stand = betrieb.stand_text(betrieb.pruefstand(befehl, os.getcwd()))   # was beim Start wirklich im Ordner liegt (TL #24259)
    # A1904: die ganze Ausgabe immer auch in eine Datei – ohne --ergebnis nach daten/laeufe/L<nr>.txt (laufdienst.ergebnis_pfad),
    # damit sie nicht verloren geht, wenn jemand stdout kürzt, und der Prüfer sie dort findet
    ziel = os.path.abspath(a.ergebnis) if a.ergebnis else laufdienst.ergebnis_pfad(betrieb.lauf_zeile(con, pid, lid))
    try:
        ausgabe = open(ziel, "w", encoding="utf-8", errors="replace")
    except OSError as e:                             # Datei geht nicht auf: der Lauf läuft trotzdem, nur ohne Mitschrift
        print(f"L{lid}: Ausgabe-Datei {ziel} geht nicht auf ({e}) – nur auf dem Bildschirm", flush=True)
        ausgabe, ziel = None, None
    if ausgabe:
        ausgabe.write(f"# AMW L{lid} · {von} · {beschreibung}\n# Befehl: {' '.join(befehl)}\n# {stand}\n"
                      f"# Start: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
    eins = len(befehl) == 1                      # ein String mit Leerzeichen: als Befehlszeile der Shell
    umgebung = None
    try:                                             # A1966: Prozesse des parallelen Gesamtlaufs aus der Projekt-Einstellung
        n = int(json.loads(con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()[0] or "{}")
                .get("gesamtlauf_prozesse") or 0)
    except (TypeError, ValueError):
        n = 0
    if n >= 1:
        umgebung = {**os.environ, "AMW_TESTPROZESSE": str(n)}
    frist = time.time() + a.frist * 60 if a.frist else None
    if frist:                                        # A2051: der Gesamtlauf hört kurz vorher selbst auf und hält den Stand fest
        umgebung = {**(umgebung or os.environ), "AMW_LAUF_ENDE": str(int(frist))}
    try:
        # FENSTER_GEWOLLT (A1783): läuft im Terminal des Agenten und erbt dessen Konsole – ohne Konsole öffnete jedes Kind
        # (z. B. Godot_*_console.exe) ein eigenes Fenster
        proc = subprocess.Popen(befehl[0] if eins else befehl, shell=eins, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, start_new_session=os.name != "nt", env=umgebung)
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
                grund, rc_grund = f"Bildschirm zu: {schirm.zustand(con)['grund'] or ''}".strip(), RC_SCHIRM
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
    wo = f" · Ausgabe: {ziel}" if ziel else ""
    if gesamt and (rc_grund if grund else rc) == RC_FRIST:   # A2051: der Lead erfährt, welches Modul zuletzt lief
        laufdienst.frist_melden(con, pid, lid, von, beschreibung, ziel, a.aufgabe)
    if grund:
        if betrieb.lauf_zeile(con, pid, lid)["status"] == "laeuft":
            betrieb.lauf_ende(con, pid, von, lid, rc_grund, f"abgebrochen: {grund}{wo}"[:500], abgebrochen=True)
        print(f"L{lid} abgebrochen ({grund}), rc {rc_grund}", flush=True)
        return rc_grund
    betrieb.lauf_ende(con, pid, von, lid, rc, (f"rc {rc} · {stand}{wo}" + (f" · {letzte[0]}" if letzte[0] else ""))[:500])
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
        if a.aktion == "frei" and schirm.BIS_GEAENDERT not in (z["grund"] or ""):   # nur „bis“ geändert (A1745): die Zeile oben reicht
            print(f"Geht von selbst zu bei Eingabe am PC (ab {schirm.RUHE_S // 60} min nach jetzt), neuer Fernsitzung,"
                  f" Eingabe von {kern.entwickler_name(con, pid)} in der Workbench am PC"
                  + (", zur bis-Zeit" if z["bis_utc"] else "") + ".")
        return
    print(schirm.text(schirm.zustand(con)))
    g = schirm.sperrgrund(con)
    print("Läufe mit Fenster: " + ("dürfen starten" if not g else "warten – " + g))
    if a.verlauf:
        for z in schirm.verlauf(con, a.grenze):
            print(f"  {schirm.lokal(z['seit_utc']):<12} {'FREI' if z['frei'] else 'zu  '} {z['von']:<10} {z['quelle']:<9} {z['grund']}")


def cmd_lauf(a, con):
    pid = _projekt(con, a)
    if a.aktion == "start":
        if not a.beschreibung and not a.rezept:
            raise kern.AmwFehler("--beschreibung oder --rezept angeben")
        lid = betrieb.lauf_start(con, pid, _von(a), a.beschreibung or a.rezept, a.rezept, _schwer(a, a.rezept, getattr(a, "dauerlauf", False)), a.schirm, a.aufgabe,
                                 warten=a.warten, erwartet_min=a.dauer, gpu=a.gpu, braucht_gb=a.braucht_gb,
                                 braucht_vram_gb=a.braucht_vram_gb, braucht_platte_gb=a.braucht_platte_gb, dauerlauf=a.dauerlauf)
        w = [r["id"] for r in betrieb.wartende(con, pid)]
        if lid in w:
            print(f"L{lid} eingereiht (Platz {w.index(lid) + 1} von {len(w)}) – noch nicht rechnen. Der Dienst benachrichtigt dich mit"
                  f" einer Freigabe, sobald L{lid} dran ist. Aus der Schlange nehmen: amw lauf ende {lid} --abgebrochen")
            zeile = con.execute("SELECT l.*, r.braucht_speicher_gb FROM lauf l LEFT JOIN rezept r ON r.id = l.rezept_id WHERE l.id = ?",
                                (lid,)).fetchone()
            if zeile["braucht_vram_gb"] and betrieb._grafik_passt_nie(con, zeile):   # A1765: gleich sagen, wenn es so nie passt
                print("ACHTUNG: " + betrieb.wartegrund(con, pid, zeile))
        else:
            print(f"L{lid} läuft – am Ende: amw lauf ende {lid} --rc <Code>")
    elif a.aktion == "ende":
        if not a.id:
            raise kern.AmwFehler("lauf ende <nr> --rc <Code>")
        weiter = betrieb.lauf_ende(con, pid, _von(a), a.id, a.rc, a.ergebnis, a.abgebrochen)
        print(f"L{a.id} beendet" + (f" – als Nächstes freigegeben: {', '.join(f'L{x}' for x in weiter)}" if weiter else ""))
    elif a.aktion == "fehlalarm":                     # A1783: Fenster-Meldung war falsch – Sperre „nur mit --schirm“ aufheben
        from . import fenster
        if not a.id:
            raise kern.AmwFehler("lauf fehlalarm <nr>")
        fenster.fehlalarm(con, pid, _von(a), a.id)
        print(f"L{a.id}: Fenster-Meldung als Fehlalarm vermerkt – derselbe Lauf geht wieder ohne --schirm")
    elif a.aktion == "vorziehen":
        if not a.id:
            raise kern.AmwFehler("lauf vorziehen <nr>")
        wo = betrieb.lauf_vorziehen(con, pid, _von(a), a.id)
        weiter = betrieb.warteschlange(con, pid)
        print(f"L{a.id} steht jetzt {wo}" + (f" – freigegeben: {', '.join(f'L{x}' for x in weiter)}" if weiter else ""))
    elif a.aktion == "zeige":
        if not a.id:
            raise kern.AmwFehler("lauf zeige <nr>")
        l = betrieb.lauf_zeile(con, pid, a.id)
        print(f"L{l['id']} {l['agent']} [{l['status']}]{' schwer' if l['schwer'] else ''}{' Bildschirm' if l['schirm'] else ''}"
              f"{' GPU' if l['gpu'] else ''}  {l['beschreibung']}")
        print(f"angemeldet {_zeit(l['angemeldet_utc'])} · Start {_zeit(l['start_utc']) or '–'} · Ende {_zeit(l['ende_utc']) or '–'}"
              f" · rc {l['rc'] if l['rc'] is not None else '–'}")
        from . import laufdienst                     # A1904: wo die ganze Ausgabe liegt
        pfad = laufdienst.ergebnis_pfad(l)
        print(f"Ausgabe: {pfad}" + ("" if os.path.isfile(pfad) else " (noch keine Datei)"))
        if l["status"] == "angemeldet":
            print(betrieb.wartegrund(con, pid, l))
    elif a.aktion == "warte":
        return _lauf_warte(con, pid, a)
    elif a.aktion == "ausfuehren":
        return _lauf_ausfuehren(con, pid, a)
    else:
        laufen = con.execute("SELECT l.*, r.braucht_speicher_gb FROM lauf l LEFT JOIN rezept r ON r.id = l.rezept_id WHERE l.status = 'laeuft' AND "
                             + betrieb.HIER + " ORDER BY l.id", (betrieb.rechner(),)).fetchall()
        if laufen:                                       # was den Rechner gerade belegt – auch fremde Läufe, ohne Inhalt (A1623)
            vm = {x["id"]: gb for x, gb in betrieb._vormerkungen(con)}
            print("Läuft auf diesem Rechner:")
            for r in laufen:
                print(f"  {betrieb.lauf_nennen(pid, r, mit_text=False)}{' schwer' if r['schwer'] else ''}{' Bildschirm' if r['schirm'] else ''}"
                      f"{' GPU' if r['gpu'] else ''}" + (f" · {vm[r['id']]:g} GB vorgemerkt" if r["id"] in vm else ""))
            print()
        w = betrieb.wartende(con, pid)
        if w:
            print("Warteschlange:")
            v = betrieb.vorrang()
            for i, r in enumerate(w, 1):                 # die Schlange gilt für den ganzen Rechner; fremde Läufe ohne Inhalt
                eigen = r["projekt_id"] == pid
                st = betrieb.vorrang_stufe(con, r["projekt_id"], v)
                print(f"  {i}. L{r['id']:<5} {r['agent'] if eigen else '–':<8}{' schwer' if r['schwer'] else ''}{' Bildschirm' if r['schirm'] else ''}"
                      f"{' GPU' if r['gpu'] else ''}{(' (vom Entwickler vorgezogen)' if r['rang'] >= betrieb.MENSCH_RANG else ' (im Projekt vorgezogen)') if r['rang'] else ''}{' ' + betrieb.t_vorrang(st) if st != 'normal' else ''}"
                      f" seit {_zeit(r['angemeldet_utc'])}  {r['beschreibung'] if eigen else '(anderes Projekt)'}")
            print()
        for r in con.execute("SELECT * FROM lauf WHERE projekt_id = ? ORDER BY id DESC LIMIT ?", (pid, a.grenze)):
            print(f"L{r['id']:<5} {r['agent']:<8} [{r['status']}]{' schwer' if r['schwer'] else ''}{' Bildschirm' if r['schirm'] else ''}"
                  f"{' GPU' if r['gpu'] else ''} {_zeit(r['start_utc'])}–{_zeit(r['ende_utc']) or '…'} rc {r['rc'] if r['rc'] is not None else '–'}  {r['beschreibung']}")


def cmd_pruefung(a, con):
    pid = _projekt(con, a)
    if a.aktion == "bitte":
        prid = betrieb.pruefbitte(con, pid, _von(a), a.pruefer, a.zweig, a.sha, a.punkte, a.aufgabe, stufe=a.stufe,
                                  gruppe=a.gruppe, hinweis=a.hinweis, ohne_bild=a.ohne_bild)
        print(f"P{prid} an {a.pruefer}")
    elif a.aktion in ("gruen", "rot"):
        if a.grund and a.bemerkung:                   # A1991: --grund nie still verwerfen – gleichwertig zu --bemerkung
            raise kern.AmwFehler(f"pruefung {a.aktion}: --bemerkung oder --grund, nicht beides")
        kette = betrieb.pruefung_ergebnis(con, pid, _von(a), a.id, a.aktion, a.bemerkung or a.grund)
        print(f"P{a.id} → {a.aktion}" + (f" · {kette}" if kette else ""))
    elif a.aktion == "zuruecknehmen":                   # A1917: ein GRÜN mit Grund widerrufen
        if not a.id:
            raise kern.AmwFehler("pruefung zuruecknehmen <nr> --grund „was nicht stimmt“")
        if _von(a) == kern.ENTWICKLER and _aus_agenten_sitzung():    # Sperre wie agent lead
            raise kern.AmwFehler("Zurücknehmen als Entwickler nur im eigenen Terminal des Menschen oder in der Workbench am PC –"
                                 " nicht aus einer Agenten-Sitzung")
        print(betrieb.pruefung_zuruecknehmen(con, pid, _von(a), a.id, a.grund))
    elif a.aktion == "stil":                             # A1973: Stil-Prüfung (neu) anstoßen
        if not a.id:
            raise kern.AmwFehler("pruefung stil <nr>")
        r = con.execute("SELECT pruefer FROM pruefung WHERE id = ? AND projekt_id = ?", (a.id, pid)).fetchone()
        if not r:
            raise kern.AmwFehler(f"P{a.id} gibt es nicht")
        if _von(a) not in (r["pruefer"], kern.ENTWICKLER) and not kern.ist_lead(con, pid, _von(a)):
            raise kern.AmwFehler("Die Stil-Prüfung stoßen Prüfer, Lead oder Mensch an")
        from . import stil
        z = stil.anstossen(con, pid, a.id, True)
        print(z.strip() or f"P{a.id}: keine Stil-Prüfung – kein Stil-Thema, keine Bilder an der Aufgabe oder abgeschaltet (themen_gegenlesen=aus)")
    elif a.aktion == "zeige":                            # A1780: ganze Prüfbitte ohne SQL
        if not a.id:
            raise kern.AmwFehler("pruefung zeige <nr>")
        r = con.execute("SELECT * FROM pruefung WHERE id = ? AND projekt_id = ?", (a.id, pid)).fetchone()
        if not r:
            raise kern.AmwFehler(f"P{a.id} gibt es nicht")
        z = betrieb.zurueckgenommen(con, pid, r["id"])     # A1917: im Verlauf sichtbar, dass es GRÜN war
        erg = f"{r['ergebnis']} · zurückgenommen (war GRÜN) am {_zeit(z['zeit_utc'])} von {z['von']}" if z else r["ergebnis"]
        print(f"P{r['id']} [{erg}] {r['zweig']}@{r['sha']} {r['bauer']} → {r['pruefer']}"
              + (f" · A{r['aufgabe_id']}" if r["aufgabe_id"] else "") + f" · angefragt {_zeit(r['angefragt_utc'])}"
              + (f" · Ergebnis {_zeit(r['ergebnis_utc'])}" if r["ergebnis_utc"] else ""))
        if r["punkte"]:
            print(r["punkte"])
        if r["bemerkung"]:
            print("Bemerkung: " + r["bemerkung"])
        from . import vorpruefung                         # A2004: Befund der Sprachprüfung am Eintrag
        s = vorpruefung.letzter_befund(con, pid, r["id"])
        if s:
            print(vorpruefung.zeile(s) + ("\n" + s["text"] if s.get("stand") == "neu" and s.get("text") else ""))
    elif a.aktion == "ist-gruen":
        r = betrieb.ist_gruen(con, pid, a.sha)
        print(f"grün: P{r['id']}" if r else "NICHT grün")
        return 0 if r else 3
    else:
        for r in con.execute("SELECT * FROM pruefung WHERE projekt_id = ? AND (? OR ergebnis = 'offen') ORDER BY id DESC LIMIT 50",
                             (pid, int(a.alle))):
            erg = "rot · zurückgenommen" if r["ergebnis"] == "rot" and betrieb.zurueckgenommen(con, pid, r["id"]) else r["ergebnis"]
            print(f"P{r['id']:<5} [{erg}] {r['zweig']}@{r['sha'][:8]} {r['bauer']} → {r['pruefer']}"
                  + (f" A{r['aufgabe_id']}" if r["aufgabe_id"] else ""))


def cmd_freigabe(a, con):
    """Merge-OK des Leads für eine Aufgabe (Abnahme-Kette)."""
    pid = _projekt(con, a)
    print(betrieb.freigabe_merge(con, pid, _von(a), a.aufgabe, a.zweig, a.zurueck, getattr(a, "ausnahme", None)))


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
        if a.immer_an or a.bei_bedarf:                # Einstellung dieses PCs (ki_immer_an), nicht in der Datenbank
            from . import einstellungen
            name = ki.ki_zeile(con, a.name)["name"].lower()
            namen = (ki.immer_an() | {name}) if a.immer_an else (ki.immer_an() - {name})
            einstellungen.speichern({"ki_immer_an": sorted(namen)})
            was += " · " + ("immer an (die AMW startet sie von selbst und beendet sie nie)" if a.immer_an else
                            f"nur bei Bedarf (startet mit einem Auftrag, nach {ki.leerlauf_min()} min ohne Auftrag beendet)")
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
        vid = ki.vermerken(con, pid, von, a.name, art, a.text, "bruecke" if KANAL.get() == "mcp" else KANAL.get())
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
                  + ({"immer": "  · immer an", "bedarf": "  · bei Bedarf"}.get(k.get("betrieb"), ""))
                  + ("  · von der AMW gestartet" if k.get("von_amw") else "")
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
        print(betrieb.rezept_setzen(con, pid, a.name, a.befehl, a.beschreibung, a.schirm, a.speicher or 0.0, _schwer(a), a.gpu))
    elif a.aktion == "zeige":
        r = con.execute("SELECT * FROM rezept WHERE projekt_id = ? AND name = ?", (pid, a.name)).fetchone()
        if not r:
            raise kern.AmwFehler(f"Rezept „{a.name}“ gibt es nicht")
        print(f"{r['name']} (Stand {_zeit(r['stand_utc'])}){' · Bildschirm' if r['braucht_schirm'] else ''}"
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
    if a.liste:                                          # A1821 (LayerIT R33): Kontrolle, dass jede Aussage erfasst ist
        seit = (a.seit.strip() if re.fullmatch(r"\d{4}-\d{2}-\d{2}T[\d:]+Z?", a.seit.strip()) else _datum(a.seit)) if a.seit else None
        zeilen = con.execute("SELECT id, zeit_utc, kanal, text FROM wortlaut WHERE projekt_id = ? AND (? IS NULL OR zeit_utc >= ?)"
                             " ORDER BY zeit_utc DESC, id DESC LIMIT ?", (_projekt(con, a), seit, seit, a.grenze)).fetchall()
        for w in zeilen:
            t = " ".join(w["text"].split())
            print(f"W{w['id']} {_zeit(w['zeit_utc'])} [{w['kanal']}] {t[:200]}" + ("…" if len(t) > 200 else ""))
        print(f"{len(zeilen)} Aussagen" + (f" seit {_zeit(seit)}" if seit else "") + " – ganz: amw zeige W<nr>" if zeilen else "keine")
        return
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


def _tor_zeile(x):
    return (f"Grobplanung · Konzept fertig: {x['g']} von {x['g']} Themen freigegeben" if x["konzept_zu"]
            else f"Konzept · {x['n']} von {x['g']} Themen freigegeben")


def _plan_aenderungen_zeigen(con, pid, plan, e, vorher):
    """A2028: Änderungen gegenüber der vorigen gültigen Fassung markieren und die Hinweise des Plans zeigen."""
    from . import grobplan, planer, planhinweis
    alt = None
    for v in reversed(vorher):
        x = grobplan.entwurf(con, pid, v["fassung"]) if plan == "grob" else next(
            (y for y in planer._ereignisse(con, pid, int(plan[2:]), planer.ENTWURF) if y["id"] == v["id"]), None)
        if x and x.get("entwurf"):
            alt = (x, v)
            break
    if alt and e.get("entwurf"):
        gegen = f"Fassung {alt[1]['fassung']}" if plan == "grob" else f"Entwurf {alt[1]['nr']}"
        for z in planhinweis.zeilen(alt[0]["entwurf"], e["entwurf"], gegen):
            print(z)
    h = planhinweis.alle(con, pid, plan)
    if h:
        print("Hinweise an den Planer:")
        for x in h:
            print(f"  {'offen' if x['offen'] else 'bearbeitet'} · {x['von']}" + (f" zu {x['bezug']}" if x["bezug"] else "") + f": {x['text']}")


def _grobplan_befehl(con, pid, a):
    """A2030: konzept-abschliessen | grobplan [--fassung N] [--neu] | grobplan-ja [--fassung N]."""
    from . import grobplan
    von = _von(a)
    if a.aktion == "konzept-abschliessen":
        r = grobplan.abschliessen(con, pid, von)
        if not r["abgeschlossen"]:
            print("Dein Ja ist vermerkt – es fehlt noch: " + ", ".join(r["ja_fehlt"]))
            return 0
        print("Konzept abgeschlossen – " + (r["planer"] or "Grobplanung startet"))
        return 0
    if a.aktion == "grobplan-ja":
        r = grobplan.annehmen(con, pid, von, a.fassung)
        if not r["angenommen"]:
            print("Dein Ja ist vermerkt – es fehlt noch: " + ", ".join(r["ja_fehlt"]))
            return 0
        print("Grobplan angenommen – Meilensteine angelegt und grob freigegeben: "
              + ", ".join(f"{k} → {v}" for k, v in r["angelegt"].items()))
        return 0
    if a.neu:
        if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von) or kern.ist_co(con, pid, von)):
            raise kern.AmwFehler("Neu planen lassen dürfen Lead, Co-Entwickler und der Mensch")
        print(grobplan.anstossen(con, pid, von=von))
        return 0
    ab = grobplan.abgeschlossen(con, pid)
    if not ab:
        print("Konzept noch nicht abgeschlossen – amw thema konzept-abschliessen (wenn alle Themen frei sind)")
        return 0
    for f in grobplan.fassungen(con, pid):
        if f.get("laeuft"):
            print(f"Fassung {f['fassung']}: der Grob-Planer läuft ({f['modell']}, seit {_zeit(f['zeit_utc'])})")
            continue
        kosten = f"{f['usd']:.2f} $" if isinstance(f.get("usd"), (int, float)) else "Kosten unbekannt"
        print(f"Fassung {f['fassung']}: " + (f"Fehler ({len(f['fehler'] or [])} Funde)" if f["fehler"] else
                                             f"{f['meilensteine']} Meilensteine, {f['befunde']} Befunde, {f['fragen']} Fragen")
              + f" · {f['modell'] or '–'} · {kosten}" + (" · angenommen" if f["angenommen"] else ""))
    e = grobplan.entwurf(con, pid, a.fassung)
    if e:
        print()
        print(f"Grobplan Fassung {e.get('fassung')}:")
        print(grobplan.zusammenfassung(e["entwurf"]) if e.get("entwurf") else "Funde:\n" + "\n".join(f"- {x}" for x in e.get("fehler") or []))
        _plan_aenderungen_zeigen(con, pid, "grob", e,
                                 [x for x in grobplan.fassungen(con, pid) if not x.get("laeuft") and x["id"] < e["id"]])
    return 0


def cmd_thema(a, con):
    """Design-Dokument je Thema: liste | zeige | neu | einstellen | pflegen | bestaetigen | dokument."""
    from . import themen
    pid = _projekt(con, a)
    if a.aktion in ("hinweis", "ueberarbeiten"):                         # A2028: Hinweis an den Planer, neue Fassung
        from . import planhinweis
        if not a.name:
            raise kern.AmwFehler("Welcher Plan? grob oder TH<n>")
        if a.aktion == "hinweis":
            planhinweis.hinweis(con, pid, _von(a), a.name, a.text, a.zu)
            n = len(planhinweis.offene(con, pid, a.name))
            print(f"Hinweis vermerkt ({n} offen) – überarbeiten lassen: amw thema ueberarbeiten {a.name}")
            return 0
        print(planhinweis.ueberarbeiten(con, pid, _von(a), a.name))
        return 0
    if a.aktion in ("konzept-abschliessen", "grobplan", "grobplan-ja"):    # A2030: Grobplanung einmal fürs ganze Konzept
        return _grobplan_befehl(con, pid, a)
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
    if a.aktion == "status":                          # A1896: Status je Thema (abgeleitet) – für Agenten und den Menschen
        print(_tor_zeile(themen.tor(con, pid)))       # A1913: wo das Projekt steht
        for t in themen.liste(con, pid):
            z = t["zustand"]
            print(f"TH{t['id']:<4} {('zum Löschen markiert' if z['markiert'] else z['text']):<18} {t['name'][:70]}"
                  + (f"  · Grund: {z['grund']}" if z["grund"] else "") + (f"  · Fassung {z['fassung']}" if z["fassung"] else "")
                  + (f"  · Ja fehlt: {', '.join(z['ja_fehlt'])}" if z.get("ja_fehlt") else "")      # A1937
                  + ("  · nur der Mensch" if z.get("nur_mensch") else ""))
        return
    if a.aktion == "freigeben" and _von(a) != kern.ENTWICKLER and themen.freigabe_regel(con, pid) == "co+lead":   # A1937 (B2913)
        if not a.name:
            raise kern.AmwFehler("amw thema freigeben <TH-Nr. oder Name>")
        z = themen.ja_geben(con, pid, _von(a), a.name)
        print(f"{a.name}: Ja gegeben – {z['text']}" + (f" · es fehlt noch: {', '.join(z['ja_fehlt'])}" if z.get("ja_fehlt") else ""))
        return
    if a.aktion in ("nur_mensch", "nicht_nur_mensch"):           # A1937: Thema bleibt beim Menschen (G12)
        if not a.name:
            raise kern.AmwFehler(f"amw thema {a.aktion} <TH-Nr. oder Name>")
        if a.aktion == "nicht_nur_mensch" and (_von(a) != kern.ENTWICKLER or _aus_agenten_sitzung()):
            raise kern.AmwFehler("„nur der Mensch“ aufheben: nur der Mensch in seinem eigenen Terminal")
        themen.nur_mensch_setzen(con, pid, _von(a), a.name, an=a.aktion == "nur_mensch")
        print(f"{a.name}: " + ("gibt nur der Mensch frei" if a.aktion == "nur_mensch" else "Freigabe wieder nach thema_freigabe"))
        return
    if a.aktion == "uebernehmen":                    # A1994: Konzept-Markdown halbautomatisch in Themen-Entwürfe
        from . import konzept_uebernahme
        datei = a.datei or a.name
        if not datei:
            raise kern.AmwFehler("amw thema uebernehmen --datei <konzept.md im Projektordner> [--ebene 2] [--anlegen]")
        r = konzept_uebernahme.uebernehmen(con, pid, _von(a), datei, ebene=a.ebene, anlegen=a.anlegen)
        print("\n".join(konzept_uebernahme.zeilen(r)))
        if r["angelegt"]:
            print(f"Bericht: D{r['bericht']} · Status: amw thema status – freigegeben ist nichts")
        else:
            print("Anlegen: derselbe Befehl mit --anlegen")
        return 0 if r["bestanden"] else 1
    if a.aktion == "luecken":                        # A1947: was die AMW als Lücke zeigt
        l = themen.luecken(con, pid)
        print(f"Freigegebene Themen ohne Paket: {len(l['thema_ohne_paket'])}")
        for x in l["thema_ohne_paket"]:
            print(f"  TH{x['id']:<4} {x['name'][:80]}")
        print(f"Pakete ohne Thema: {len(l['paket_ohne_thema'])}")
        for x in l["paket_ohne_thema"]:
            print(f"  A{x['id']:<5} [{x['status']}] {x['titel'][:80]} ({x['agent'] or '–'})")
        return
    if a.aktion == "vermerk":                        # A1947: „nichts zu bauen“ mit Grund (Lead, Mensch, Co-Entwickler)
        if not a.name or not (a.nichts_zu_bauen or a.aufheben or a.bestaetigen):
            raise kern.AmwFehler("amw thema vermerk TH<n> --nichts-zu-bauen --grund … (aufheben: --aufheben)")
        if a.bestaetigen:                             # K7 (TH154): der Co bestätigt den Grund des Leads
            _nicht_als_mensch_aus_sitzung(a, "thema vermerk --bestaetigen")
            from . import tore
            tid = tore.nichts_bestaetigen(con, pid, _von(a), a.name)
            print(f"TH{tid}: „nichts zu bauen“ bestätigt")
            return
        tid = themen.nichts_zu_bauen(con, pid, _von(a), a.name, a.grund, aufheben=a.aufheben)
        print(f"TH{tid}: " + ("Vermerk „nichts zu bauen“ aufgehoben" if a.aufheben else "„nichts zu bauen“ vermerkt – keine Lücke mehr"))
        return
    if a.aktion == "anhalten":                        # K8 (A1942): nicht begonnene Pakete eines geänderten Themas anhalten
        from . import planansicht
        if not a.name:
            raise kern.AmwFehler("amw thema anhalten TH<n> [--meilenstein N]")
        t = themen.finden(con, pid, a.name)
        bid = None
        if a.meilenstein is not None:
            r = con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND nr = ?", (pid, a.meilenstein)).fetchone()
            if not r:
                raise kern.AmwFehler(f"Meilenstein {a.meilenstein} gibt es nicht")
            bid = r[0]
        weg = planansicht.anhalten(con, pid, _von(a), t["id"], bid)
        print(f"TH{t['id']}: " + (f"angehalten: {', '.join(f'A{x}' for x in weg)}" if weg else "keine nicht begonnenen Pakete"))
        return
    if a.aktion in ("planen", "plan-ja") and _von(a) == kern.ENTWICKLER and _aus_agenten_sitzung():   # P462 (3)
        raise kern.AmwFehler(f"thema {a.aktion}: als Entwickler nur im eigenen Terminal des Menschen oder in der Workbench am PC –"
                             " nicht aus einer Agenten-Sitzung")
    if a.aktion in ("planen", "plan", "plan-ja"):     # A1940 (K4): Grobplanung aus Themen per -p-Planer
        from . import planer
        if not a.name:
            raise kern.AmwFehler(f"amw thema {a.aktion} TH<n>")
        t = themen.finden(con, pid, a.name)
        if a.aktion == "planen":
            if not (kern.ist_lead(con, pid, _von(a)) or kern.ist_co(con, pid, _von(a))):
                raise kern.AmwFehler("Den Planer stoßen Lead, Mensch oder Co-Entwickler an")
            s = themen.status(con, t)
            if not s["fassung"]:
                raise kern.AmwFehler(f"TH{t['id']} hat noch keinen Text – erst eine Fassung")
            print(planer.anstossen(con, pid, t["id"], s["fassung"], von=_von(a), erneut=True))
            return
        e = planer.letzter_entwurf(con, pid, t["id"])
        if a.aktion == "plan":
            if not e:
                print(f"TH{t['id']}: noch kein Planentwurf" + (" – der Planer läuft" if planer.laeuft(con, pid, t["id"]) else ""))
                return
            kopf = f"TH{t['id']} Planentwurf (Fassung {e.get('fassung')}, {e.get('modell') or '–'}" + (
                f", {e['usd']:.2f} $" if isinstance(e.get("usd"), (int, float)) else "") + ")"
            print(kopf + (" – schon angenommen" if planer.erledigt(con, pid, e["id"]) else ""))
            print(planer.zusammenfassung(e["entwurf"]) if e.get("entwurf") else "Fehler:" + chr(10) + chr(10).join(f"- {x}" for x in e.get("fehler") or []))
            alle = planer._ereignisse(con, pid, t["id"], planer.ENTWURF)                  # A2028: Änderungen und Hinweise
            _plan_aenderungen_zeigen(con, pid, f"TH{t['id']}", e,
                                     [{"id": x["id"], "nr": i, "fassung": x.get("fassung")} for i, x in enumerate(alle, 1) if x["id"] < e["id"]])
            return
        geaendert = None
        if a.datei:
            with open(a.datei, encoding="utf-8") as f:
                geaendert = f.read()
        angelegt = planer.uebernehmen(con, pid, _von(a), t["id"], geaendert=geaendert)
        if "ja_fehlt" in angelegt:                         # A2027: Delta bei feinplan_freigabe = co+lead
            print(f"TH{t['id']}: dein Ja zum Delta ist vermerkt – es fehlt noch: " + angelegt["ja_fehlt"])
            return
        if ((e or {}).get("entwurf") or {}).get("delta"):
            from . import planer_delta
            d = planer_delta.letzte(con, pid, t["id"])
            print(f"TH{t['id']}: Delta freigegeben – " + "; ".join(x for x in (
                ", ".join(f"{k} → {v}" for k, v in angelegt.items()) and "angelegt " + ", ".join(f"{k} → {v}" for k, v in angelegt.items()),
                d.get("geaendert") and "geändert " + ", ".join(d["geaendert"]),
                d.get("verworfen") and "verworfen " + ", ".join(d["verworfen"]),
                d.get("uebersprungen") and "nicht angewandt: " + ", ".join(d["uebersprungen"])) if x))
            return
        print(f"TH{t['id']}: " + ("„nichts zu bauen“ vermerkt" if not angelegt else "angelegt – " + ", ".join(f"{k} → {v}" for k, v in angelegt.items())))
        try:
            ent = planer.pruefen(geaendert) if geaendert is not None else (e or {}).get("entwurf")
        except planer.PlanFehler:
            ent = None
        for h in planer.achtung(ent):                     # A2004: p ist die Vorgabe
            print(f"Achtung: {h} ({', '.join(f'{k} → {v}' for k, v in angelegt.items() if h.startswith(k + ' '))})")
        return
    if a.aktion in ("freigeben", "zurueck", "markieren", "entmarkieren"):   # A1896: nur der Mensch, nur im eigenen Terminal
        if _von(a) != kern.ENTWICKLER or _aus_agenten_sitzung():
            raise kern.AmwFehler(f"thema {a.aktion}: nur der Mensch in seinem eigenen Terminal oder in der Workbench am PC")
        if not a.name:
            raise kern.AmwFehler(f"amw thema {a.aktion} <TH-Nr. oder Name>" + (" --notiz …" if a.aktion == "zurueck" else ""))
        vorher = themen.tor(con, pid)
        z = (themen.freigeben(con, pid, _von(a), a.name) if a.aktion == "freigeben"
             else themen.zurueck(con, pid, _von(a), a.name, a.notiz) if a.aktion == "zurueck"
             else themen.markieren(con, pid, _von(a), a.name, an=a.aktion == "markieren"))
        print(f"{a.name}: {'zum Löschen markiert' if z['markiert'] else z['text']}")
        nachher = themen.tor(con, pid)
        if nachher["konzept_zu"] != vorher["konzept_zu"]:                  # A1913: das Tor schließt bzw. öffnet von selbst
            print("Damit ist das Tor Konzept geschlossen – " + _tor_zeile(nachher) if nachher["konzept_zu"]
                  else "Das Tor Konzept ist wieder offen – " + _tor_zeile(nachher))
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


TEXT_ENDUNGEN = (".md", ".txt", ".html", ".htm", ".json", ".csv", ".svg", ".py", ".log", ".yaml", ".yml", ".xml", ".ini", ".toml")
INHALT_MAX = 20000


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
        if a.inhalt:                                     # A1821 (GlassWorld R43): den Inhalt lesen – ohne Dateizugriff/SQL
            v = next((x for x in d["versionen"] if x["nr"] == a.fassung), None) if a.fassung else d["versionen"][-1]
            if not v:
                raise kern.AmwFehler(f"D{d['id']} hat keine Fassung {a.fassung}")
            pfad = dokumente.datei_pfad(v["sha256"], v["endung"])
            print(f"\n--- Inhalt v{v['nr']} ({v['endung']}) ---")
            if v["endung"].lower() in TEXT_ENDUNGEN:
                try:
                    with open(pfad, encoding="utf-8", errors="replace") as f:
                        t = f.read(INHALT_MAX + 1)
                except OSError as e:
                    raise kern.AmwFehler(f"Datei nicht lesbar: {e}") from None
                print(t[:INHALT_MAX] + (f"\n… (gekürzt nach {INHALT_MAX} Zeichen – ganz: {pfad})" if len(t) > INHALT_MAX else ""))
            else:
                print(f"{v['endung']} ist kein Text (Bild, Video, PDF …) – ansehen in der Workbench › Dokumente oder die Datei: {pfad}")
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
    elif a.aktion == "berichtigen":                  # A1985: Text einer eingetragenen Version berichtigen (Lead/Mensch)
        if not a.version:
            raise kern.AmwFehler("amw release berichtigen --version X.Y.Z --aus-changelog | --oeffentlich-datei <datei> [--aufgaben …]")
        text = None
        if a.oeffentlich_datei:
            with open(a.oeffentlich_datei, encoding="utf-8") as f:
                text = f.read()
        rid = wissen.release_berichtigen(con, pid, _von(a), a.version, oeffentlich=text, aus_changelog=a.aus_changelog, aufgaben=a.aufgaben)
        print(f"R{rid} ({a.version}) berichtigt – der alte Text steht im Verlauf (release_berichtigt)")
    elif a.aktion == "ausliefern":                   # Release-Kette in einem Schritt (A1644)
        from . import auslieferung
        if not a.zweig:
            raise kern.AmwFehler("release ausliefern --zweig <zweig|stand> [--gesamtlauf L<nr>]")
        if KANAL.get() != "cli":
            raise kern.AmwFehler("release ausliefern geht nur im Terminal")
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # das Repository dieser AMW
        from . import pruefung_c
        ordner = kern.projekt_ordner(con, pid)
        if ordner and not pruefung_c.ist_amw(ordner):        # A1933: ein Projekt, das nicht die AMW ist – sein eigener Ordner
            _rolle_nur_mensch_oder_lead(con, pid, a, "release ausliefern für dieses Projekt")
            auslieferung.Kette(con, pid, _von(a), ordner, amw=False).ausliefern(a.zweig, a.gesamtlauf, a.aufgabe)
        else:
            auslieferung.Kette(con, pid, _von(a), wurzel, amw=True).ausliefern(a.zweig, a.gesamtlauf, a.aufgabe)
    elif a.aktion == "version":
        oeffentlich = None
        if a.oeffentlich_datei:
            with open(a.oeffentlich_datei, encoding="utf-8") as f:
                oeffentlich = f.read().strip()
        rid, n = wissen.release_version(con, pid, _von(a), a.version, a.titel, a.commit, _text(a) or None, oeffentlich,
                                        nachtrag=a.nachtrag)
        print(f"Version {a.version} (R{rid}) " + ("nachgetragen (Zeit und Text aus Tag und CHANGELOG)" if a.nachtrag
                                                 else f"aus {n} Merge(s) – Versionshinweise eingetragen"))
    else:
        for r in con.execute("SELECT * FROM release WHERE projekt_id = ? ORDER BY zeit_utc DESC LIMIT 30", (pid,)):
            print(f"R{r['id']:<5} {r['art']:<7} {r['version'] or '(offen)':<9} {_zeit(r['zeit_utc'])} {r['titel']}")


def cmd_regelwerk(a, con):
    """Grund-Regelwerk für Bestandsprojekte: abgleich (nur lesen; --ablegen: als Dokument an den Lead) | uebernehmen Gx."""
    from . import dokumente, regelwerk
    pid = _projekt(con, a)
    if a.aktion == "abgleich":
        text = regelwerk.bericht(con, pid)
        if not a.ablegen:
            print(text)
            return
        did = dokumente.ablegen_inhalt(con, pid, _von(a), text.encode("utf-8"), "regelwerk-abgleich.md", "Abgleich mit dem Grund-Regelwerk", "bericht")
        lead = con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND rolle = 'lead' AND entfernt_utc IS NULL ORDER BY id LIMIT 1",
                           (pid,)).fetchone()
        an = lead["kennung"] if lead and lead["kennung"] != _von(a) else kern.ENTWICKLER
        z = regelwerk.abgleich(con, pid)["zahl"]
        nid, _ = kern.posten(con, pid, _von(a), an, "info", f"Abgleich mit dem Grund-Regelwerk: {z['fehlt']} fehlen, {z['aehnlich']} vermutlich"
                             f" abgedeckt – Vorschlag, bitte prüfen", bezug=f"D{did}")
        print(f"D{did} abgelegt, #{nid} an {an}")
    else:
        if not a.nr:
            raise kern.AmwFehler("welche Grundregel? z. B. amw regelwerk uebernehmen G7 (mehrere: G1,G2 · alle fehlenden: alle)")
        nummern = regelwerk.alle_fehlenden(con, pid) if a.nr.strip().lower() == "alle" else [x for x in a.nr.replace(" ", ",").split(",") if x]
        if not nummern:
            print("Alle Grundregeln sind schon übernommen")
        if len(nummern) > 1 and a.text:
            raise kern.AmwFehler("--text nur bei einer Grundregel")
        for nr in nummern:                               # A1782: mehrere auf einmal – jede mit eigenem Beschluss, wie einzeln
            r = regelwerk.nachziehen(con, pid, _von(a), nr, a.text)
            print(f"{nr.upper()} " + ("neue Fassung in" if r.get("neue_fassung") else "übernommen als") + f" KR{r['regel']} (B{r['beschluss']})")


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
    from . import paket
    pfad = abgleich.zugang_pfad()
    alt = paket.zugang_lesen()
    if alt.get("url") and not a.ersetzen:
        raise kern.AmwFehler(f"Es gibt schon einen Online-Speicher ({alt['url']}). Ersetzen mit --ersetzen – dann gilt der alte"
                             " Zugang auf diesem PC nicht mehr.")
    pem, token = schluessel.erzeugen(("pc", "seite"))
    ordner = a.ordner or os.path.dirname(pfad)
    os.makedirs(ordner, exist_ok=True)
    oeffentlich = os.path.join(ordner, "amw-speicher-oeffentlich.pem")
    with open(oeffentlich, "w", encoding="ascii", newline="\n") as f:
        f.write(pem)
    paket.zugang_eintragen(alt, url, token["pc"], a.ca or "")
    print(f"Öffentlicher Schlüssel für den libSQL-Server: {oeffentlich}")
    print("  Auf den Server kopieren und sqld damit starten: --auth-jwt-key-file <Datei> (bzw. SQLD_AUTH_JWT_KEY_FILE).")
    print(f"Zugang auf diesem PC eingetragen: {url} (Synchronisierung noch aus) – {pfad}")
    print("Schlüssel für die Online-Seite – nur jetzt sichtbar, in deren amw-konfig.php als 'speicher_token' eintragen:")
    print(f"  {token['seite']}")
    print("Dann: Einstellungen › Speicher und Synchronisierung › „Verbindung testen“, danach Synchronisierung an.")
    print("Hinweis: Diese Schlüssel laufen nicht ab. Ungültig werden sie, wenn du ein neues Paar erzeugst und den neuen öffentlichen"
          " Schlüssel auf dem Server einlegst.")
    return 0


def _web_paket(a):
    """Eigener Server im Firmennetz (R3b): ZIP für den Webserver bauen und den Zugang am PC eintragen."""
    from . import betriebsart, paket, push
    passwort = None
    if a.passwort_abfragen:
        import getpass
        passwort = getpass.getpass("Passwort für den Admin der Online-Seite (mind. 14 Zeichen): ")
        if getpass.getpass("Noch einmal: ") != passwort:
            raise kern.AmwFehler("Die beiden Passwörter sind verschieden – nichts gebaut")
    r = paket.bauen(a.seite, a.speicher, admin=a.admin, ca=a.ca, ziel=a.ziel, ersetzen=a.ersetzen, passwort=passwort)
    try:
        push.speichern({"link": r["seite"]})            # Adresse der Seite: Links in Benachrichtigungen, „Online-Seite testen“
        link = f"Adresse der Online-Seite eingetragen: {r['seite']}"
    except ValueError as e:
        link = f"Adresse der Online-Seite nicht eingetragen ({e}) – unter Einstellungen › Online-Seite nachholen"
    print(f"Paket gebaut: {r['ziel']}")
    print("  Die ZIP ist ein Geheimnis: Sie enthält den Schlüssel der Seite für den Speicher – wer ihn hat, kann alle Daten"
          " lesen und ändern. Nicht weitergeben, nicht per E-Mail oder Chat schicken, nach dem Kopieren auf den Server löschen.")
    print(f"Zugang auf diesem PC eingetragen: {r['speicher']} (Synchronisierung noch aus) – {r['zugang']}")
    print(link)
    if r["seite"].startswith("http://"):
        print("Achtung: Die Seite läuft über http – Passwörter und Codes gehen unverschlüsselt durchs Netz. Besser https mit"
              " einem Zertifikat der Firma.")
    if not a.passwort_abfragen:
        print(f"Admin der Online-Seite: {r['admin']} · Passwort – nur jetzt sichtbar: {r['passwort']}")
    else:
        print(f"Admin der Online-Seite: {r['admin']} (Passwort wie eingetippt)")
    if betriebsart.aktuell() != "server":
        print("Betriebsart: Einstellungen › Betriebsart › „Eigener Server im Firmennetz“ wählen (oder amw einrichten betriebsart server).")
    print("Weiter: LIESMICH.txt in der ZIP – Speicher starten, Seite einrichten, dann am PC „Verbindung testen“ und Synchronisierung an.")
    return 0


def cmd_web(a, con):
    """Online-Teil (doc/online.md): Seite für den Webhoster bauen, Online-Speicher einrichten, einen Abgleich von Hand."""
    from . import abgleich
    if a.aktion == "sso":
        return _web_sso(a)
    if a.aktion == "paket":
        return _web_paket(a)
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


def _dienst_neustart_darf(a):
    """A2039 (D1531 §7): Den Dienst startet der Mensch neu (eigenes Terminal, Workbench am PC), die AMW selbst (Release-Kette,
    --von AMW) oder der Lead – nicht ein beliebiger Agent aus seiner Sitzung: ein Neustart unterbricht Zustellung, Läufe und
    Wächter für alle. Gegen Versehen, keine Sperre gegen Absicht (wer PowerShell hat, kann die Aufgabe selbst anstoßen)."""
    if not _aus_agenten_sitzung():
        return
    von = getattr(a, "von", None) or os.environ.get("AMW_AGENT")
    if von == "AMW":
        return
    if von and von != kern.ENTWICKLER:
        con = db.verbinde()
        try:
            if any(kern.ist_lead(con, pid, von) for (pid,) in con.execute("SELECT id FROM projekt").fetchall()):
                return
        finally:
            con.close()
    raise kern.AmwFehler("dienst neustart: nur der Mensch im eigenen Terminal oder in der Workbench, der Lead oder die"
                         " Release-Kette – nicht aus einer Agenten-Sitzung. Bitte den Lead fragen.")


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
    if a.aktion == "neustart":
        _dienst_neustart_darf(a)
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
    x.add_argument("aktion", choices=["neu", "liste", "ordner", "einstellen", "schalter"])
    x.add_argument("name", nargs="?", help="einstellen: schluessel=wert · schalter: Projektname")
    x.add_argument("wert", nargs="?", help="schalter: probe (Lead oder Mensch) | an | aus (nur der Mensch im eigenen Terminal)")
    x.add_argument("--beschreibung")
    x.add_argument("--regeln-von", dest="regeln_von", metavar="PROJEKT",
                   help="neu: die Arbeitsregeln (KR) eines Projekts einmal kopieren – danach getrennt änderbar")
    x.add_argument("--ordner", help="Projektordner (das Repository, in dem die Agenten arbeiten; vorher selbst anlegen)")
    x.set_defaults(f=cmd_projekt)

    x = s.add_parser("agent", help="neu | liste | profil | starten | beenden | startskript | umbenennen ALT NEU | lead NEU --co ALT --grund …"
                                   " | entfernen | wiederaufnehmen AGENT (der Mensch; wiederaufnehmen auch der Lead mit --wort W<nr>)"
                                   " | alle-beenden [--alle-projekte] [--frist N] (alle Fenster-Agenten sichern und beenden lassen; nur der Mensch)"
                                   " | ende-stand [--alle-projekte] (Rückmeldung: sichert, abgemeldet, beendet) – A2048")
    x.add_argument("aktion", choices=["neu", "liste", "profil", "starten", "beenden", "startskript", "umbenennen", "lead",
                                      "entfernen", "wiederaufnehmen", "alle-beenden", "ende-stand"])
    x.add_argument("--alle-projekte", action="store_true", help="alle-beenden, ende-stand: über alle Projekte auf diesem PC – A2048")
    x.add_argument("--frist", type=int, help="alle-beenden: Minuten bis zum Beenden (Vorgabe: Projekt-Einstellung ende_frist_min, 5)")
    x.add_argument("--co", help="lead: der bisherige Lead wird Co-Entwickler (Wortlaut, Beschlüsse, Fragen an den Menschen,"
                                " Dokumente; behält den Dateiaustausch); ist NEU schon Lead, setzt --co nur den Co-Entwickler")
    x.add_argument("--grund", help="lead: warum (z. B. der Beschluss)")
    x.add_argument("kennung", nargs="?")
    x.add_argument("neu_kennung", nargs="?", metavar="neu", help="umbenennen: der neue Name (der alte bleibt als Alias gültig)")
    x.add_argument("--ordner", help="profil: Arbeitsordner")
    x.add_argument("--zusatz", help="profil: weitere Ordner, mit ; getrennt")
    x.add_argument("--denkstufe", help="profil: low | medium | high | xhigh | max")
    x.add_argument("--modell", help="profil: z. B. opus, sonnet (leer = Vorgabe)")
    x.add_argument("--startsatz", help="profil: erste Anweisung einer neuen Sitzung")
    x.add_argument("--rechte", help="profil: vorgabe | auto | umgehen")
    x.add_argument("--wort", help="profil, wiederaufnehmen, lead: auf ein Wort des Entwicklers (W<nr>, höchstens 24 h alt) – darf der"
                                  " Lead, auch über den Dateiaustausch")
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
    x.add_argument("--neuer-faden", action="store_true", help="an den Menschen: nicht von selbst an seine letzte Nachricht an dich"
                                                             " hängen (sonst tut die AMW das, wenn sie höchstens 2 Tage alt ist)")
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
                                     " bereit N (Ergebnis steht, bei --fertig-wenn ja) | abnehmen N [--zurueck --kommentar] |"
                                     " plan N --text | planfrei N [--zurueck --kommentar] | nachtrag N --titel … (Folgearbeit"
                                     " zu einer fertigen Aufgabe)")
    x.add_argument("aktion", choices=["neu", "aendern", "liste", "zeige", "start", "blockiert", "wartet", "fertig", "verwerfen",
                                       "parken", "aktiv", "keine_prio", "pool", "kriterium", "plan", "planfrei", "nachtrag",
                                       "dazwischen", "bereit", "abnehmen", "hinweis"])
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
                                 " (Pflicht; erledigt sich von selbst und benachrichtigt dich). Fügt Gründe HINZU – alte bleiben"
                                 " offen, bis sie sich erledigen oder du sie mit --erledigt abhakst")
    x.add_argument("--erledigt", help="wartet/blockiert: diese Gründe von Hand abhaken, z. B. F12 oder CCamw (allein: Status bleibt;"
                                      " mit --auf: alten Grund abhaken und neuen setzen in einem Schritt)")
    x.add_argument("--bemerkung")
    x.add_argument("--alle", action="store_true")
    x.add_argument("--bogen", type=nummer, help="Planung: gehört zu Meilenstein N (neu: Pflicht, solange es einen aktiven oder"
                                              " geplanten gibt)")
    x.add_argument("--ohne-bogen", action="store_true", help="neu: Lead – bewusst ohne Meilenstein; steht dann in der Planung"
                                                            " unter „Ohne Meilenstein“")
    x.add_argument("--kriterium", action="append", help="Planung: Abnahmekriterium, mehrfach (ersetzt die Liste)")
    x.add_argument("--fertig-wenn", dest="fertig_wenn", help="neu/aendern (A1938): Fertig-Quelle – commit | thema TH<n> |"
                                                             " frist <Tage> nach <Version> | ja; die AMW schließt die Aufgabe selbst")
    x.add_argument("--quelle", help="kriterium N nr (A1938): Prüfquelle – lauf <Befehl> | pruefung | thema TH<n> | tests <N>;"
                                    " leer entfernt sie; die AMW hakt selbst ab")
    x.add_argument("--schaetzung", type=float, help="Planung: Stunden")
    x.add_argument("--komplexitaet", type=int, help="Planung: 1–10; ab 7 braucht der Schritt einen freigegebenen Plan")
    x.add_argument("--groesse", type=str.upper, choices=["S", "M", "L", "XL"],
                   help="Größe (für die Empfehlung Modell/Denkaufwand): S klein … XL sehr groß")
    x.add_argument("--art", choices=["text", "mechanisch", "fehlersuche", "oberflaeche", "sicherheit", "konzept"],
                   help="Art (für die Empfehlung): text = Text/Doku, mechanisch = mechanische Änderung, fehlersuche,"
                        " oberflaeche, sicherheit, konzept = Architektur/Konzept")
    x.add_argument("--nach", "--abhaengig-von", dest="nach", help="Vorgänger, z. B. 1201,1203 (startbar erst, wenn sie fertig sind)")
    x.add_argument("--verantwortlich", help="Planung: wer abnimmt bzw. Pläne freigibt")
    x.add_argument("--pruefbefehl", help="Planung: wie der Bearbeiter selbst prüft")
    x.add_argument("--dateien", help="Planung: Dateibereich, den er anfassen darf")
    x.add_argument("--anforderungen", help="Planung: abgedeckte Anforderungen, z. B. R1,R3")
    x.add_argument("--zusammenfassung", help="fertig: Pflicht für Schritte in einem Meilenstein; aendern: nachtragen")
    x.add_argument("--ohne-vorgaenger", help="aendern: diese Vorgänger lösen, z. B. 115")
    x.add_argument("--thema", help="neu/aendern: verweist auf diese Themen, z. B. TH3,TH5 – ändert sich ein freigegebenes Thema, meldet"
                                   " die AMW die Aufgabe zum Prüfen (A1915)")
    x.add_argument("--ohne-thema", help="aendern: diese Themen-Verweise lösen, z. B. TH3")
    x.add_argument("--ohne-thema-grund", help="neu: bewusst ohne Thema (interne Pflege, z. B. Aufräumen, Fehlerbehebung) – mit Grund (A1947)")
    x.add_argument("--text", help="plan: der Plan")
    x.add_argument("--nein", action="store_true", help="kriterium: wieder als offen markieren")
    x.add_argument("--zurueck", action="store_true", help="planfrei, abnehmen: zurückweisen (mit --kommentar)")
    x.add_argument("--kommentar")
    x.add_argument("--kurz", action="store_true", help="zeige: nur Status, Agent, Titel und Wartegründe")
    x.add_argument("--federfuehrend", help="aendern: wer diese Aufgabe führt (Lead/Entwickler; leer = weg)")
    x.add_argument("--pool", action="store_true", help="neu: in den Eingang (noch in keiner Arbeitsliste)")
    x.add_argument("--grund", help="dazwischen: warum diese Aufgabe vor das laufende Stück muss (Pflicht)")
    x.add_argument("--hinweis", help="fertig|hinweis: ein Satz für die Versionshinweise, in der Sprache der Nutzer (ohne: die AMW leitet"
                   " ihn ab – aus Commit-Betreff, Thema oder Titel)")
    x.add_argument("--gruppe", choices=["neu", "verbessert", "behoben", "intern"], help="fertig|hinweis: Gruppe in den Versionshinweisen"
                   " (ohne: die AMW leitet sie ab – Art fehlersuche = behoben, sonst nach Stichworten; intern = nie in den Versionshinweisen)")
    x.add_argument("--sofort", action="store_true", help="neu: direkt hinter das laufende Stück des Agenten einplanen statt in den"
                                                          " Eingang (ohne laufendes Stück: wie bisher in die Liste)")
    # Paketfelder (A1845, AMW 2.0 Mischbetrieb) – Abnahme-Befehl = --pruefbefehl, Bereiche = --dateien, Rang = --rang, nach X = --nach
    x.add_argument("--paket", choices=["agent", "sitzung", "p"], help="Paket: wer ausführt – agent (interaktiver Agent, Vorgabe),"
                                                                    " sitzung (neue Sitzung), p (frischer claude -p-Arbeiter)")
    x.add_argument("--gewicht", choices=["leicht", "schwer"], help="Paket: leicht (Vorgabe) oder schwer")
    x.add_argument("--ressourcen", help="Paket: gpu,bildschirm (Vorgabe: keine)")
    x.add_argument("--modell", help="Paket: wie claude --model (Vorgabe claude-opus-5-5); bei einem freigegebenen Anbieter"
                                    " anbieter@modell, z. B. minimax@MiniMax-M2 (A1931)")
    x.add_argument("--effort", choices=["low", "medium", "high"], help="Paket: wie claude --effort (Vorgabe high)")
    x.add_argument("--pakettyp", choices=["normal", "test-schreiben", "test-ergaenzen"], help="Paket: normal (Vorgabe), test-schreiben (Test + Änderung, rot gegen alt) oder test-ergaenzen (nur Tests für bestehenden Code, grün; Lead liest)")
    x.add_argument("--nie-gleichzeitig", help="Paket: nie gleichzeitig mit diesen Aufgaben, z. B. A12,A13")
    x.add_argument("--gleiche-ressource", help="Paket: Name einer gemeinsamen Ressource – Pakete mit demselben Namen laufen nacheinander")
    x.set_defaults(f=cmd_aufgabe)

    x = s.add_parser("paket", help="Arbeitspakete (Mischbetrieb): zeigen N | zustand N <zustand> [--grund … --beleg …] | liste"
                                   " [--zustand …] | ergebnis N (--json - über stdin oder --status/--zusammenfassung/--frage/"
                                   "--frage-an/--grund/--hinweis; nur der zugeteilte Agent, Art agent/sitzung, Paket läuft)"
                                   " | starten N (Lead/Mensch: ein startklares p-Paket jetzt starten – der Wächter entscheidet)"
                                   " | mergeliste [--diff] (bereit zum Merge: diff --stat, Server-Code, Blick nötig)"
                                   " | freigeben --alle | freigeben N [--blick] (Prüfer der Pakete, Lead, Mensch)"
                                   " | buendeln --alle | buendeln N [--titel …] (freigegebene Pakete zu einem Release-Stand; Lead, Mensch)"
                                   " | annehmen N --grund … (E4-Paket nach dem Lesen in die Merge-Liste; Lead, Mensch)"
                                   " | holen [N] (interaktiv: nächste Aufgabe nehmen, Auftrag + Startwissen, Zweig/Arbeitsbaum)"
                                   " | fertig N --sha … --punkte … (interaktiv: Tests-Hinweis, Prüfbitte, wartet auf den Prüfer)"
                                   " – Felder setzen: amw aufgabe neu|aendern … --paket p …")
    x.add_argument("aktion", choices=["zeigen", "zustand", "liste", "ergebnis", "starten", "mergeliste", "freigeben", "buendeln", "annehmen",
                                      "holen", "fertig"])
    x.add_argument("id", type=nummer, nargs="?")
    x.add_argument("zustand", nargs="?", help="zustand: entwurf, startklar, laeuft, abgegeben, abnahme, merge_reihe, gemergt, fertig,"
                                              " blockiert, unklar, wartet_interaktiv, abgebrochen, zurueckgestellt")
    x.add_argument("--grund", help="zustand: warum (steht im Planungs-Protokoll) · ergebnis aufgegeben: warum es nicht geht · annehmen: was du gelesen hast und warum es passt")
    x.add_argument("--beleg", help="zustand fertig: Commit")
    x.add_argument("--nur", help="liste: nur diese Zustände, z. B. startklar,laeuft")
    x.add_argument("--diff", action="store_true", help="mergeliste: auch den gekürzten Diff zeigen")
    x.add_argument("--alle", action="store_true", help="freigeben: alle Pakete, die bereit zum Merge sind (außer denen, die einen Blick brauchen)")
    x.add_argument("--blick", action="store_true", help="freigeben N: du hast in den Diff gesehen (nötig laut merge_blick)")
    x.add_argument("--titel", help="buendeln: Titel des Abschnitts in den Versionshinweisen (sonst aus dem Hinweis bzw. „Gebündelte Pakete“)")
    x.add_argument("--gesamtlauf", metavar="ZWEIG", help="buendeln: den Gesamtlauf eines vorhandenen Bündels (buendel-X.Y.Z) neu anstoßen")
    x.add_argument("--json", help="ergebnis: „-“ = die Meldung als JSON von stdin")
    x.add_argument("--status", choices=["erledigt", "blockiert", "aufgegeben"], help="ergebnis: genau ein Status")
    x.add_argument("--zusammenfassung", help="ergebnis: ein Satz, was gemacht wurde")
    x.add_argument("--frage", help="ergebnis blockiert: die eine Frage, die dich stoppt")
    x.add_argument("--frage-an", dest="frage_an", choices=["lead", "mensch"], help="ergebnis blockiert: wer antworten soll (Vorgabe lead)")
    x.add_argument("--hinweis", help="ergebnis: optional, geht nur an den Lead")
    x.add_argument("--zweig", help="ergebnis erledigt bei einem Paket mit Abnahme-Befehl: dein Zweig (Pflicht) – die AMW prüft ihn und"
                                    " stellt die Prüfbitte mit ihrem Befund · fertig: dein Zweig (Vorgabe a<N>)")
    x.add_argument("--sha", help="fertig: der genaue Stand (Commit) für die Prüfbitte")
    x.add_argument("--punkte", help="fertig: was du geprüft hast (Proben, Läufe) – steht in der Prüfbitte")
    x.add_argument("--pruefer", help="fertig: wer prüft (Vorgabe: Prüfer der Aufgabe, sonst der Lead)")
    x.add_argument("--gruppe", choices=["neu", "verbessert", "behoben"], help="fertig: Gruppe für die Versionshinweise")
    x.add_argument("--ohne-bild", dest="ohne_bild", help="fertig: sichtbare Änderung ausnahmsweise ohne Bild – mit Grund")
    x.set_defaults(f=cmd_paket)

    x = s.add_parser("thema", help="Design-Dokument je Thema: liste [--suche] | zeige TH12 | neu \"Name\" [--pfleger X] [--stil] |"
                                   " einstellen TH12 --pfleger X | --stil | pflegen TH12 --text-datei … | bestaetigen TH12 |"
                                   " dokument TH12 --dokument D5 [--loesen] | status (ein Status je Thema) |"
                                   " freigeben TH12 | zurueck TH12 --notiz … | markieren|entmarkieren TH12 (nur der Mensch;"
                                   " bei thema_freigabe=co+lead gibt freigeben von Co und Lead je ein Ja, B2913) |"
                                   " nur_mensch TH12 (Pfleger, Lead, Mensch) | nicht_nur_mensch TH12 (nur der Mensch) |"
                                   " vermerk TH12 --nichts-zu-bauen --grund … [--aufheben] | luecken (Thema ohne Paket, Paket ohne Thema) |"
                                   " planen TH12 (Planer anstoßen, Lead/Co) | plan TH12 (Entwurf zeigen) | plan-ja TH12 [--datei geändert.json] (Lead) |"
                                   " anhalten TH12 [--meilenstein N] (nicht begonnene Pakete eines geänderten Themas, Lead/Co) |"
                                   " uebernehmen --datei konzept.md [--ebene 2] [--anlegen] (Konzept-Markdown aus dem Projektordner"
                                   " in Themen-Entwürfe, mit Zählprobe; ohne --anlegen nur Vorschau – Lead/Co) |"
                                   " konzept-abschliessen (alle Themen frei: Konzept-Ja, startet die Grobplanung über alle Themen) |"
                                   " grobplan [--fassung N] [--neu] (Fassungen und Entwurf zeigen, neu planen lassen) |"
                                   " grobplan-ja [--fassung N] (legt die Meilensteine an – wer Ja sagt wie bei den Themen) – A2030 |"
                                   " hinweis grob|TH12 --text … [--zu TH3|M2|P4|A123] (Ergänzung an den Planer) |"
                                   " ueberarbeiten grob|TH12 (Planer legt mit den offenen Hinweisen eine neue Fassung vor; Mensch, Lead, Co) – A2028")
    x.add_argument("aktion", nargs="?", default="liste", choices=["liste", "zeige", "neu", "einstellen", "pflegen", "bestaetigen",
                                                                  "dokument", "status", "freigeben", "zurueck", "markieren",
                                                                  "entmarkieren", "nur_mensch", "nicht_nur_mensch", "vermerk", "luecken", "planen", "plan", "plan-ja", "anhalten",
                                                                  "uebernehmen", "konzept-abschliessen", "grobplan", "grobplan-ja",
                                                                  "hinweis", "ueberarbeiten"])
    x.add_argument("--zu", help="hinweis: die Karte – TH3, M2, P4 oder A123 (ohne: der ganze Plan) – A2028")
    x.add_argument("--fassung", type=int, help="grobplan, grobplan-ja: diese Fassung des Grobplans statt der neuesten – A2030")
    x.add_argument("--neu", action="store_true", help="grobplan: den Grob-Planer neu planen lassen (neue Fassung) – A2030")
    x.add_argument("--ebene", type=int, choices=range(1, 7), metavar="1-6",
                   help="uebernehmen: welche Überschriften-Ebene zu Themen wird (Vorgabe: die Gliederung unter dem Titel)")
    x.add_argument("--anlegen", action="store_true", help="uebernehmen: wirklich anlegen (ohne: nur Vorschau, nichts geschrieben)")
    x.add_argument("--meilenstein", type=int, help="anhalten: nur in diesem Meilenstein (Nummer) – K8")
    x.add_argument("--nichts-zu-bauen", action="store_true", help="vermerk: das Thema braucht kein Paket (mit --grund) – A1947")
    x.add_argument("--aufheben", action="store_true", help="vermerk: den Vermerk „nichts zu bauen“ wieder aufheben")
    x.add_argument("--bestaetigen", action="store_true", help="vermerk: „nichts zu bauen“ bestätigen (Co-Entwickler oder Mensch) – K7")
    x.add_argument("--grund")
    x.add_argument("--datei", help="plan-ja: geänderter Entwurf als JSON-Datei (gleiches Schema, wird neu geprüft) – A1940;"
                                   " uebernehmen: die Konzept-Datei (.md) im Projektordner – A1994")
    x.add_argument("--notiz", help="zurueck: was soll anders werden (Pflicht)")
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

    x = s.add_parser("liste", help="Arbeitsliste je Agent: liste [Agent|pool] | ordnen <Agent> A12 A15 … --grund … | schieben A15"
                                   " --vor A12 | --nach | --pos N | --oben | --unten [--grund …] (ordnen/schieben: Lead; die"
                                   " Reihenfolge rechnet sonst die AMW)")
    x.add_argument("wer", nargs="?", help="Agent, pool, ordnen oder schieben")
    x.add_argument("rest", nargs="*", help="ordnen: Agent und Aufgaben-Nummern · schieben: die Aufgabe")
    x.add_argument("--vor", type=nummer)
    x.add_argument("--nach", type=nummer)
    x.add_argument("--pos", type=int)
    x.add_argument("--oben", action="store_true")
    x.add_argument("--unten", action="store_true")
    x.add_argument("--grund", help="ordnen/schieben (A1941): warum von Hand – sonst rechnet die AMW die Reihenfolge")
    x.set_defaults(f=cmd_liste)

    x = s.add_parser("frage", help="Fragen an den Entwickler oder Lead: neu | liste [--geparkt] | antworten | nachtrag | verlauf |"
                                    " parken N [--grund] | aufnehmen N | weiterleiten N [--text] (Lead → Entwickler)")
    x.add_argument("aktion", choices=["neu", "liste", "zeige", "antworten", "nachtrag", "verlauf", "parken", "aufnehmen", "weiterleiten"])
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
    x.add_argument("--buendeln", help="neu (Lead): diese offenen Fragen der Agenten in eine neue Frage an den Entwickler bündeln,"
                                     " z. B. F12,F13 – die Antwort gilt auch für sie (A2021)")
    x.add_argument("--anhang", action="append", help="neu: Bild/Mockup zu einer Option, 'A=datei.png' oder 'A=D12' (mehrfach) –"
                                                     " erscheint als Variante zum Anklicken, auch online")
    x.set_defaults(f=cmd_frage)

    x = s.add_parser("pause", help="Pause für alles (A2042): an [--bis HH:MM|2h|90min] [--grund …] | aus | zeige (Rückmeldung je Agent)")
    x.add_argument("aktion", choices=["an", "aus", "zeige"])
    x.add_argument("--bis", help="an: Ende – HH:MM (heute, sonst morgen), 2h oder 90min; ohne: bis „amw pause aus“")
    x.add_argument("--grund")
    x.set_defaults(f=cmd_pause)

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

    x = s.add_parser("waechter", help="Wächter für p-Pakete: pruefen A | protokoll [A] | reihenfolge | zustand | wartung an|aus | weiter")
    x.add_argument("aktion", choices=["pruefen", "protokoll", "reihenfolge", "zustand", "wartung", "weiter"])
    x.add_argument("nr", nargs="?", help="Aufgabe (pruefen, protokoll) bzw. an|aus (wartung)")
    x.add_argument("--grund")
    x.set_defaults(f=cmd_waechter)

    x = s.add_parser("claude", help="Claude-Code-Versionen der Arbeiter: status (installiert, geprüft, Proben) | freigeben X.Y.Z --grund"
                                    " (Lead oder Mensch, nicht aus einer Agenten-Sitzung) – eine neue Version prüft die AMW selbst (A1906)")
    x.add_argument("aktion", choices=["status", "freigeben"])
    x.add_argument("version", nargs="?", help="freigeben: die Version, z. B. 2.1.331")
    x.add_argument("--grund", help="freigeben: warum die Version trotz Probe in Ordnung ist")
    x.set_defaults(f=cmd_claude)
    x = s.add_parser("platz", help="Arbeitsplätze für kopflose Arbeiter (claude -p): liste | vorbereiten N | zuruecksetzen N | aufraeumen"
                                   " | notbremse N (nur der Mensch: Arbeiter samt Kindern beenden) – nichts wird gelöscht: Reste ins"
                                   " Archiv, fertige Pakete nach _loeschen")
    x.add_argument("aktion", choices=["liste", "vorbereiten", "zuruecksetzen", "aufraeumen", "notbremse"])
    x.add_argument("nr", nargs="?", type=int)
    x.add_argument("--aufgabe", type=int, help="Aufgabe des Pakets (Name des Archivs, damit aufraeumen es nach Paketende verschiebt)")
    x.add_argument("--zweig", help="vorbereiten: Name des Zweigs ab main (Vorgabe platzN)")
    x.set_defaults(f=cmd_platz)

    x = s.add_parser("sicherung", help="Tägliche Sicherung aller Zweige und Tags an sicherung_ziel (A1929): zeigen | jetzt (Lead oder"
                                       " Mensch) – ohne --force, nie löschen, keine Zugangsdaten")
    x.add_argument("aktion", choices=["zeigen", "jetzt"], nargs="?", default="zeigen")
    x.set_defaults(f=cmd_sicherung)

    x = s.add_parser("empfehlung", help="Eignungstabelle (A1930, TH159): tabelle – je Zelle und Modell/Effort Anzahl, Anteil ohne"
                                        " Nacharbeit, Median Kosten und Dauer; was die Empfehlung nimmt (nur lesen)")
    x.add_argument("aktion", choices=["tabelle"], nargs="?", default="tabelle")
    x.set_defaults(f=cmd_empfehlung)

    x = s.add_parser("anbieter", help="Anbieter je Projekt (A1931, TH159): liste | freigeben NAME --url https://… --schluessel-datei"
                                      " <Pfad> --modelle a,b [--lokal] | entfernen NAME – freigeben/entfernen nur der Mensch im eigenen"
                                      " Terminal; nur der Pfad der Schlüsseldatei wird gespeichert, nie der Schlüssel")
    x.add_argument("aktion", choices=["liste", "freigeben", "entfernen"], nargs="?", default="liste")
    x.add_argument("name", nargs="?")
    x.add_argument("--url", help="Basis-URL der Anthropic-kompatiblen Schnittstelle (https://…; lokal auch http://localhost:…)")
    x.add_argument("--schluessel-datei", dest="schluessel_datei", help="absoluter Pfad zur Datei mit dem Schlüssel (außerhalb jedes Repos)")
    x.add_argument("--modelle", help="Modelle des Anbieters, mit Komma (das erste prüft die Negativprobe)")
    x.add_argument("--lokal", action="store_true", help="lokales Modell (belegt die Grafikkarte)")
    x.set_defaults(f=cmd_anbieter)

    x = s.add_parser("pc", help="Disponent über Projekte (A1925): zeigen (Rangfolge, p-Arbeiter, Kosten je Projekt diese Woche) |"
                                " einstellen projekt_rang=A,B,C (nur der Mensch) | plaetze_pc=N | limit_halt=P (Lead oder Mensch)")
    x.add_argument("aktion", choices=["zeigen", "einstellen"], nargs="?", default="zeigen")
    x.add_argument("wert", nargs="?", help="schluessel=wert")
    x.set_defaults(f=cmd_pc)

    x = s.add_parser("messung", help="Wartezeit und Kosten je Aufgabe (Liegezeit, aktiv, wartet nach Grund, $, Lücken) – nur lesen")
    x.add_argument("nr", nargs="?", help="eine Aufgabe (A12 oder 12); ohne: alle begonnenen")
    x.add_argument("--seit", help="nur Aufgaben, die ab dann noch liefen (17.11. oder ISO-Zeit)")
    x.add_argument("--agent")
    x.add_argument("--vergleich", action="store_true", help="letzte 7 Tage gegen die 7 Tage davor (Mediane, D1258 v2 §8)")
    x.add_argument("--hebel7", action="store_true", help="Startkontext je Agent (Zeilen/Zeichen) und Kosten je Paket (Median der"
                                                        " letzten 10) – A1956, TH168 Hebel 7")
    x.add_argument("--basis", action="store_true", help="mit --hebel7: als Basis festhalten (Ereignis basis_hebel7; Lead oder Mensch)")
    x.add_argument("--p", action="store_true", help="Anteil p an fertigen Paketen je Tag (Ziel ≥ 50 %%) und Kosten p gegen interaktiv"
                                                   " (Median, Summe) – A2004")
    x.add_argument("--tage", type=int, help="mit --p: so viele Tage zurück (Vorgabe 7)")
    x.add_argument("--prognose", action="store_true", help="Prognose messen: Schätzung (P50) gegen Ist je fertigem Paket, Trefferquote"
                                                          " im Rahmen 0,67–1,5× und Median-Faktor, je Quelle; mit --seit – A2046")
    x.add_argument("--gesamt", action="store_true", help="Kosten des Projekts: bisher (gemessen, Fenster-Agenten und Headless), noch"
                                                         " (Schätzung offener Pakete) und gesamt")
    x.set_defaults(f=cmd_messung)

    x = s.add_parser("skills", help="Anleitungen als Claude-Code-Skills: bauen (aus doc nach .claude/skills, A1956)")
    x.add_argument("aktion", choices=["bauen"])
    x.add_argument("--ziel", help="anderer Ordner für .claude/skills (z. B. der Agenten-Ordner eines anderen Projekts)")
    x.set_defaults(f=cmd_skills)

    x = s.add_parser("kosten", help="Kosten eines Laufs außerhalb der Sitzungs-Zähler einer Aufgabe zuordnen (z. B. claude -p)")
    x.add_argument("aktion", choices=["erfassen"])
    x.add_argument("--aufgabe", required=True)
    g = x.add_mutually_exclusive_group(required=True)
    g.add_argument("--json", help="Datei mit der Ausgabe von claude -p --output-format json")
    g.add_argument("--usd", type=float)
    g.add_argument("--unbekannt", action="store_true", help="Lauf ohne Ergebnis (abgebrochen) – als Lücke vermerken")
    x.add_argument("--notiz")
    x.set_defaults(f=cmd_kosten)

    x = s.add_parser("mcp", help="Connector für Chat-Leads: schluessel (neu erzeugen – nur der Mensch, einmal sichtbar) | eintrag"
                                 " (Zeile für claude_desktop_config.json)")
    x.add_argument("aktion", choices=["schluessel", "eintrag"])
    x.set_defaults(f=cmd_mcp)

    x = s.add_parser("takt", help="ein Durchgang für Leads: Postfach mit Text, Prüfbitten, Fragen, Antworten des Menschen,"
                                  " Läufe, Lead-Runde, Auslieferungen – knapp, je Punkt eine Zeile")
    x.add_argument("--seit", help="Antworten/Läufe/Auslieferungen seit (HH:MM oder Datum); sonst seit dem letzten Takt")
    x.add_argument("--abhaken", action="store_true", help="gezeigte Infos und Meldungen gleich erledigen")
    x.add_argument("--grenze", type=int, default=30, help="höchstens so viele Nachrichten (Vorgabe 30)")
    x.set_defaults(f=cmd_takt)

    x = s.add_parser("kontext", help="Startinformationen für einen Agenten")
    x.add_argument("agent", nargs="?")
    x.set_defaults(f=cmd_kontext)

    x = s.add_parser("runde", help="Lead-Runde: Kanal nur zwischen den Leads aller Projekte – nur Information, nie Befehle"
                                   " (runde schreiben --kurz … [--an Projekt] · runde lesen [--neu])")
    x.add_argument("aktion", nargs="?", default="lesen", choices=["lesen", "schreiben"])
    x.add_argument("--kurz")
    x.add_argument("--text")
    x.add_argument("--text-datei", help="Text aus einer Datei (UTF-8)")
    x.add_argument("--art", default="info", choices=["info", "frage"], help="nur info oder frage – keine Aufträge an andere Projekte")
    x.add_argument("--an", help="direkte Anrede: Projekt, dessen Lead zusätzlich eine Info ins Postfach bekommt (weckt nicht)")
    x.add_argument("--antwort-auf", type=lambda v: int(str(v).lstrip("Rr")), help="Antwort auf Eintrag R<nr>")
    x.add_argument("--neu", action="store_true", help="lesen: nur Ungelesenes")
    x.set_defaults(f=cmd_runde)

    x = s.add_parser("regeln", help="alle geltenden Regeln (Arbeits- und Projektregeln) – oder eine ganz: amw regeln KR3")
    x.add_argument("nr", nargs="?", help="eine Regel: KR3, PR2 oder 3 (= KR3)")
    x.set_defaults(f=cmd_regeln)

    x = s.add_parser("verbrauch", help="Verbrauch nach Anlass (Pareto): wofür die Agenten des Projekts ihr Geld ausgeben")
    x.add_argument("aktion", choices=["pareto"])
    x.add_argument("--tage", type=int, default=7, help="Zeitraum ab lokaler Mitternacht (Vorgabe 7)")
    x.set_defaults(f=cmd_verbrauch)

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

    x = s.add_parser("bogen", help="Meilensteine: liste | neu | zeigen N | aendern N | status N aktiv|fertig|geplant|verworfen |"
                                   " starten N (Jetzt starten: an den Disponenten) | reihenfolge [N] (berechnet, kritischer Pfad) |"
                                   " zeitplan [N] (geplante Start- und Endzeit je Paket, gleichzeitig, +n min – A2045) |"
                                   " abnehmen N (nur der Mensch: fertigen Meilenstein abnehmen, danach veröffentlicht die AMW)")
    x.add_argument("aktion", choices=["liste", "neu", "zeigen", "aendern", "status", "abnehmen", "freigeben", "zurueck", "bericht",
                                      "tore", "starten", "reihenfolge", "zeitplan", "feinplanen", "nacharbeit"])
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
    x.add_argument("--art", choices=["grob", "plan", "abschluss"], help="freigeben/zurueck: Meilenstein (grob), sein Plan oder sein"
                                                                       " Abschlussbericht – K6/K7")
    x.add_argument("--notiz", help="zurueck: was soll anders werden (Pflicht)")
    x.add_argument("--hinweis", help="feinplanen: Hinweis an den Feinplaner (was er anders machen soll); nacharbeit: was fehlt (Pflicht)")
    x.add_argument("--starten", action="store_true", help="freigeben --art plan: Plan freigeben und den Meilenstein gleich starten"
                                                          " (ein Klick wie in der Workbench)")
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

    x = s.add_parser("lauf", help="Rechen-Läufe: start [--warten] prüft Halt, Bildschirm, Speicher je Lauf, zwei Spuren (Grafikkarte/"
                                  "Bildschirm: einer zur Zeit; schwere ohne Fenster: parallel bis cpu_laeufe, je Agent einer), Warteschlange · warte <nr> blockiert, bis er dran ist · zeige <nr> mit Wartegrund ·"
                                  " ausfuehren --beschreibung … [--schirm] [--ergebnis datei] -- <befehl …> (einreihen, warten,"
                                  " starten, rc durchreichen, Ende melden; bei Bildschirm zu den eigenen Befehl beenden)")
    x.add_argument("aktion", choices=["start", "ende", "liste", "vorziehen", "zeige", "warte", "ausfuehren", "fehlalarm"])
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
    x.add_argument("--leicht", action="store_true", help="Pflicht (oder --schwer): normales Bauen/Testen – läuft parallel, wartet nie auf schwere")
    x.add_argument("--schwer", action="store_true", help="Pflicht (oder --leicht): KI, Grafikkarte, Fenster oder viel Speicher – läuft einzeln")
    x.add_argument("--dauerlauf", action="store_true", help="start/ausfuehren: kopflos, ohne KI/GPU/Fenster, mit --braucht-gb als"
                   " fester Grenze – läuft neben dem schweren Lauf, die Grenze wird vorgemerkt, der Dienst passt auf, dass er sie hält")
    x.add_argument("--schirm", action="store_true")
    x.add_argument("--gpu", action="store_true", help="belegt die Grafikkarte: PC-weit nur ein GPU-Lauf zur Zeit"
                                                     " (auch KI-Aufträge; ein Lauf mit Fenster wartet ebenfalls)")
    x.add_argument("--aufgabe", type=nummer)
    x.add_argument("--rc", type=int)
    x.add_argument("--ergebnis", help="ende: Ergebnis-Text · ausfuehren: Datei für die Ausgabe des Befehls (ohne: laeufe/L<nr>.txt neben der Datenbank)")
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

    x = s.add_parser("schirm", help="Bildschirm-Schalter: zeige | frei --grund … [--bis HH:MM] (Entwickler/Lead; schon frei: ändert nur --bis, ohne --bis = ohne Ende) | zu [--grund …] (alle)")
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

    x = s.add_parser("pruefung", help="Prüfbitte je Stand (SHA), Ergebnis grün/rot; zuruecknehmen N --grund … (ein GRÜN widerrufen:"
                                      " Prüfer, Lead, Mensch); stil N (Stil-Prüfung der Bilder nach dem Stil-Thema neu anstoßen:"
                                      " Prüfer, Lead, Mensch)")
    x.add_argument("aktion", choices=["bitte", "gruen", "rot", "zuruecknehmen", "ist-gruen", "liste", "zeige", "stil"])
    x.add_argument("id", type=nummer, nargs="?")
    x.add_argument("--pruefer")
    x.add_argument("--zweig")
    x.add_argument("--sha")
    x.add_argument("--punkte")
    x.add_argument("--aufgabe", type=nummer)
    x.add_argument("--bemerkung", help="gruen/rot: Befund (bei rot Pflicht)")
    x.add_argument("--grund", help="zuruecknehmen: was nicht stimmt (Pflicht) · gruen/rot: wie --bemerkung")
    x.add_argument("--alle", action="store_true")
    x.add_argument("--stufe", choices=["niedrig", "mittel", "hoch"], help="Prüfstufe höher einstufen als die geänderten Dateien ergeben (nie niedriger)")
    x.add_argument("--gruppe", choices=["neu", "verbessert", "behoben"], help="bitte: Versionshinweis der Aufgabe (setzt sie die Release-Kette fertig, gilt er)")
    x.add_argument("--hinweis", help="bitte: ein Satz für Nutzer zu den Versionshinweisen")
    x.add_argument("--ohne-bild", dest="ohne_bild", metavar="GRUND",
                   help="bitte: sichtbare Änderung ausnahmsweise ohne Bild-Dokument an der Aufgabe – mit Grund")
    x.set_defaults(f=cmd_pruefung)
    x = s.add_parser("freigabe", help="Merge-OK (Lead/Entwickler oder der Prüfer der jüngsten grünen Prüfung): freigabe merge A<nr> [--zweig z] [--zurueck] – Abnahme-Kette:"
                                      " nach grüner Prüfung geht die Merge-Bitte von selbst an den Merge-Dienst")
    x.add_argument("was", choices=["merge"])
    x.add_argument("aufgabe", type=nummer)
    x.add_argument("--zweig", help="nur für diesen Zweig – muss zu einer grünen oder offenen Prüfung der Aufgabe passen;"
                                   " ohne: der Zweig der jüngsten grünen Prüfung (vor der ersten Prüfung: jeder Zweig)")
    x.add_argument("--zurueck", action="store_true", help="OK zurücknehmen")
    x.add_argument("--ausnahme", help="ohne eigenen Gesamtlauf ausliefern dürfen – mit Grund (liest amw release ausliefern)")
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
    x.add_argument("--leicht", action="store_true", help="Pflicht (oder --schwer): Läufe mit diesem Rezept sind leicht")
    x.add_argument("--schwer", action="store_true", help="Pflicht (oder --leicht): Läufe mit diesem Rezept sind schwer")
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
    x.add_argument("--start", help="neu/aendern: Startbefehl ohne Fenster (der Dienst startet die KI, wenn ein Auftrag für sie dran"
                                    " ist und sie nicht antwortet)")
    x.add_argument("--ordner", help="neu/aendern: Arbeitsordner für den Startbefehl")
    x.add_argument("--vram", type=float, help="GB Grafikspeicher (Richtwert/Probe)")
    x.add_argument("--abschalten", action="store_true", help="aendern: KI nicht mehr beauftragen")
    x.add_argument("--einschalten", action="store_true")
    x.add_argument("--immer-an", action="store_true", help="neu/aendern: die AMW hält die KI am Laufen (startet sie von selbst,"
                                                          " beendet sie nie) – Einstellung dieses PCs")
    x.add_argument("--bei-bedarf", action="store_true", help="neu/aendern: Vorgabe – startet erst mit einem Auftrag; hat die AMW"
                                                            " sie gestartet, beendet sie sie nach ki_leerlauf_min (30) min ohne Auftrag")
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
            x.add_argument("--liste", action="store_true", help="erfasste Aussagen zeigen (neueste zuerst) statt eine zu erfassen")
            x.add_argument("--seit", help="mit --liste: nur ab diesem Zeitpunkt (Datum, z. B. 15.11. oder 2026-11-15T18:00:00Z)")
            x.add_argument("--grenze", type=int, default=50, help="mit --liste: höchstens so viele")
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
    x.add_argument("--inhalt", action="store_true", help="zeigen: auch den Inhalt der neuesten (oder --fassung) Fassung – Text bis 20 000 Zeichen,"
                                                          " sonst Hinweis + Pfad")
    x.add_argument("--fassung", type=int, help="zeigen --inhalt: diese Fassung (Nummer) statt der neuesten")
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
                                 " | sso [--aussteller URL --client-id ID --an|--aus] (Firmen-Anmeldung; Geheimnis nur auf der Online-Seite)"
                                 " | paket --seite https://… --speicher https://… [--admin NAME] [--ca firma.pem] [--ziel datei.zip]"
                                 " (eigener Server im Firmennetz: ZIP für den Webserver)")
    x.add_argument("aktion", choices=["einrichten", "bauen", "schema", "einmal", "status", "zweitfaktor-neu", "sso", "paket"])
    x.add_argument("--seite", help="paket: Adresse der Online-Seite, z. B. https://amw.firma.lan (http:// nur im Firmennetz)")
    x.add_argument("--speicher", help="paket: Adresse des libSQL-Servers, z. B. https://amw-db.firma.lan (http:// nur im Firmennetz)")
    x.add_argument("--admin", default="admin", help="paket: Name des ersten Admins der Online-Seite (Vorgabe: admin)")
    x.add_argument("--ca", help="paket: Zertifikat der Firmen-CA (PEM) für PC und Seite, wenn die Zertifikate der Server von der Firma sind")
    x.add_argument("--ziel", help="paket: wohin die ZIP kommt (Vorgabe: amw-paket-<Name>-<Datum>.zip im aktuellen Ordner)")
    x.add_argument("--passwort-abfragen", action="store_true", help="paket: Passwort des Admins eintippen statt erzeugen lassen")
    x.add_argument("--ersetzen", action="store_true", help="paket: einen schon eingetragenen Online-Speicher ersetzen (neue Schlüssel)")
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

    x = s.add_parser("regelwerk", help="Grund-Regelwerk im bestehenden Projekt: abgleich [--ablegen] | uebernehmen G7 [--text …]")
    x.add_argument("aktion", choices=["abgleich", "uebernehmen"])
    x.add_argument("nr", nargs="?", help="uebernehmen: Nummer der Grundregel (G1 … G19, W1 … W4)")
    x.add_argument("--text", help="uebernehmen: eigener Wortlaut statt dem der Vorlage")
    x.add_argument("--ablegen", action="store_true", help="abgleich: als Dokument ablegen und dem Lead schicken")
    x.set_defaults(f=cmd_regelwerk)

    x = s.add_parser("befehle", help="Befehlsreferenz als Markdown (für doc/befehle.md)")
    x.set_defaults(f=_befehle_ausgeben, ohne_db=True)

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
    x.add_argument("aktion", choices=["merge", "version", "liste", "entwurf", "ausliefern", "berichtigen"],
                   help="ausliefern --zweig X: die ganze Release-Kette in einem Schritt (Prüfung GRÜN, Merge-OK und Gesamtlauf nötig) ·"
                        " berichtigen --version X --aus-changelog | --oeffentlich-datei … [--aufgaben …] (Lead/Mensch: Text einer"
                        " eingetragenen Version)")
    x.add_argument("--aus-changelog", dest="aus_changelog", action="store_true",
                   help="berichtigen: Text aus dem Abschnitt der Version im CHANGELOG auf main")
    x.add_argument("--zweig", help="ausliefern: Zweig oder Stand, der live gehen soll")
    x.add_argument("--gesamtlauf", help="ausliefern: grüner Gesamtlauf L<nr> (sonst sucht die AMW den Lauf, der genau diesen Stand sauber geprüft hat)")
    x.add_argument("--aufgabe", type=nummer, help="ausliefern ohne Prüfbitte (Prüfstufe niedrig, nur Doku/Tests): die Aufgabe mit dem Merge-OK")
    x.add_argument("--oeffentlich-datei", help="version: eigener Text für alle statt des Entwurfs (Markdown)")
    x.add_argument("--titel")
    x.add_argument("--commit")
    x.add_argument("--nachtrag", action="store_true", help="version: eine fehlende kleinere Version nachtragen, die es als Git-Tag gibt (nur Lead)")
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


def _befehle_ausgeben(a):
    """`amw befehle > doc/befehle.md`: Zeilenenden LF auch unter Windows (A1902 – sonst schlägt test_zeilenenden an)."""
    try:
        sys.stdout.reconfigure(newline="\n")
    except (AttributeError, ValueError):                 # umgeleitet auf etwas ohne reconfigure – dann so, wie es ist
        pass
    print(befehle_markdown(), end="")
    return 0


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
                if a.cmd in ("lesen", "kontext", "takt") and _von(a) not in (kern.ENTWICKLER, "AMW"):   # A1757: Nachlesen messen
                    from . import nachlesen
                    try:
                        nachlesen.merken(db.projekt_name(con, _projekt(con, a)), _von(a), a.cmd)
                    except Exception:                        # noqa: BLE001 – Messen darf den Befehl nie stören
                        pass
                wer = getattr(a, "von", None) or os.environ.get("AMW_AGENT")   # nie _von(): ohne Absender kein Abbruch
                if wer and wer not in (kern.ENTWICKLER, "AMW"):              # A1943 (K9): Befehle je Paket zählen
                    from . import startwissen
                    try:
                        startwissen.befehl_merken(db.projekt_name(con, _projekt(con, a)), wer, a.cmd)
                    except Exception:                        # noqa: BLE001 – Messen darf den Befehl nie stören
                        pass
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
