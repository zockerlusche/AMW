"""Kommandozeile `amw` – einziger Schreibweg der Agenten (→ doc/architektur.md).

Wer bin ich: --von oder Umgebungsvariable AMW_AGENT. Welches Projekt: --projekt, AMW_PROJEKT oder das
einzige vorhandene. Ausgabe immer UTF-8 (sonst brechen Umlaute in der Windows-Konsole ab).
"""
import argparse
import json
import os
import re
import sys
from datetime import datetime

from . import betrieb, db, kern, ueberwachung, wissen


def _projekt(con, a):
    name = a.projekt or os.environ.get("AMW_PROJEKT")
    if name:
        return db.projekt_id(con, name)
    zeilen = con.execute("SELECT id, name FROM projekt").fetchall()
    if len(zeilen) == 1:
        return zeilen[0]["id"]
    raise kern.AmwFehler("mehrere oder keine Projekte – --projekt oder AMW_PROJEKT angeben")


def _von(a):
    von = a.von or os.environ.get("AMW_AGENT")
    if not von:
        raise kern.AmwFehler("wer bist du? --von oder AMW_AGENT setzen")
    return von


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
        with db.schreiben(con):
            db.einfuegen(con, "projekt", name=a.name, beschreibung=a.beschreibung, angelegt_utc=db.jetzt())
        print(f"Projekt {a.name} angelegt")
    else:
        for r in con.execute("SELECT id, name, beschreibung FROM projekt ORDER BY id"):
            print(f"{r['id']} {r['name']}  {r['beschreibung'] or ''}")


def cmd_agent(a, con):
    pid = _projekt(con, a)
    if a.aktion == "neu":
        kern.agent_neu(con, pid, a.kennung, a.rolle, a.grenzen, a.startbefehl, not a.ohne_rund)
        print(f"Agent {a.kennung} angelegt")
        return
    if a.aktion in ("profil", "starten", "beenden", "startskript"):
        from . import steuerung
        if a.aktion == "startskript":
            text = steuerung.startskript(con, pid, [a.kennung] if a.kennung else None)
            if a.datei:
                with open(a.datei, "w", encoding="utf-8-sig") as f:
                    f.write(text)
                print(f"geschrieben: {a.datei} – mit Rechtsklick „Mit PowerShell ausführen“ starten")
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
            for k, v in p.items():
                print(f"{k:<14} {v}")
        return
    for r in con.execute(
            "SELECT g.kennung, g.rolle, g.soll, s.zustand, s.letzter_puls_utc,"
            " (SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
            "   WHERE e.agent = g.kennung AND n.projekt_id = g.projekt_id AND e.status != 'erledigt') AS offen"
            " FROM agent g LEFT JOIN sitzung s ON s.id = (SELECT max(id) FROM sitzung WHERE agent_id = g.id)"
            " WHERE g.projekt_id = ? ORDER BY g.id", (pid,)):
        print(f"{r['kennung']:<8} {r['rolle'] or '':<10} soll {r['soll']:<4} ist {r['zustand'] or 'nie gestartet':<14}"
              f" Puls {_zeit(r['letzter_puls_utc']) or '–':<12} offen {r['offen']}")


def cmd_posten(a, con):
    pid = _projekt(con, a)
    text = a.text
    if a.text_datei:
        with open(a.text_datei, encoding="utf-8") as f:
            text = f.read()
    nid, namen = kern.posten(con, pid, _von(a), a.an, a.art, a.kurz, text, a.antwort_auf, a.aufgabe)
    print(f"#{nid} an {', '.join(namen)}")


def cmd_lesen(a, con):
    pid = _projekt(con, a)
    von = _von(a)
    if a.id:
        n = kern.lesen(con, pid, von, a.id)
        print(f"#{n['id']} {_zeit(n['zeit_utc'])} {n['von']} [{n['art']}]"
              + (f" Antwort auf #{n['antwort_auf']}" if n["antwort_auf"] else "")
              + (f" · A{n['aufgabe_id']}" if n["aufgabe_id"] else ""))
        print(n["kurz"])
        if n["text"]:
            print(n["text"])
        return
    zeilen = kern.offene(con, pid, von, a.grenze)
    for r in zeilen:
        print(f"#{r['id']} {_zeit(r['zeit_utc'])} {r['von']:<8} [{r['art']}]{'' if r['status'] == 'offen' else ' (gelesen)'}"
              f" {r['kurz'][:140]}")
    print(f"{len(zeilen)} offen" if zeilen else "nichts offen")


def cmd_erledigt(a, con):
    n = kern.erledigt(con, _projekt(con, a), _von(a), a.ids, a.bemerkung)
    print(f"{n} erledigt")


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
    if a.aktion == "neu":
        werte, nach = _schritt_werte(a)
        if any(v is not None for k, v in werte.items() if k not in ("agent", "auftrag", "pruefer")) or nach:
            aid = planung.schritt_setzen(con, pid, _von(a), titel=a.titel, nach=nach, rang=a.rang, **werte)
        else:
            aid = kern.aufgabe_neu(con, pid, _von(a), a.titel, a.agent, a.auftrag, a.rang, a.pruefer)
        print(f"A{aid} angelegt")
    elif a.aktion == "aendern":
        werte, nach = _schritt_werte(a)
        werte["zusammenfassung"] = a.zusammenfassung              # auch nachträglich (Plan-Check)
        planung.schritt_setzen(con, pid, _von(a), aid=a.id, titel=a.titel, nach=nach, **werte)
        if _ohne(a):
            planung.abhaengigkeit_setzen(con, pid, _von(a), a.id, _ohne(a), entfernen=True)
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
        for r in kern.aufgaben(con, pid, a.agent, a.alle):
            print(f"A{r['id']:<5} {r['agent'] or '–':<8} [{r['status']}/{r['einstufung']}] {r['titel'][:110]}"
                  + (f"  ⇢ {r['wartet_auf']}" if r["wartet_auf"] else ""))
    elif a.aktion == "zeige":
        r = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (a.id, pid)).fetchone()
        if not r:
            raise kern.AmwFehler(f"A{a.id} gibt es nicht")
        for k in r.keys():
            if r[k] not in (None, "") and k not in ("uid", "herkunft"):
                print(f"{k}: {r[k]}")
    elif a.aktion in ("parken", "aktiv", "keine_prio", "pool"):
        if not a.id:
            raise kern.AmwFehler("Aufgaben-Nummer fehlt")
        wissen.einstufen(con, pid, _von(a), a.id, "geparkt" if a.aktion == "parken" else a.aktion)
        print(f"A{a.id} → {'geparkt' if a.aktion == 'parken' else a.aktion}")
    else:
        if not a.id:
            raise kern.AmwFehler("Aufgaben-Nummer fehlt")
        neu = kern.aufgabe_status(con, pid, _von(a), a.id, a.aktion, a.beleg, a.wartet_auf, a.bemerkung, a.zusammenfassung)
        print(f"A{a.id} → {neu}")


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
        print(f"Bogen {bid} angelegt – Spezifikation: amw spec schreiben {bid} anforderungen --datei …")
    elif a.aktion == "aendern":
        planung.bogen_aendern(con, pid, _von(a), a.id, a.titel, a.ziel, a.abnahme, a.zieldatum, a.nr, a.grund)
        print(f"Bogen {a.id} geändert")
    elif a.aktion == "status":
        planung.bogen_status(con, pid, _von(a), a.id, a.wert, a.erzwingen)
        print(f"Bogen {a.id} → {a.wert}")
    elif a.aktion == "zeigen":
        b = next((x for x in planung.boegen(con, pid) if x["id"] == a.id), None)
        if not b:
            raise kern.AmwFehler(f"Bogen {a.id} gibt es nicht")
        print(f"Bogen {b['id']} [{b['status']}] {b['titel']} · Ziel: {b['ziel'] or '–'} · Abnahme: {b['abnahme'] or '–'}"
              f" · Zieldatum {b['zieldatum'] or '–'} (Baseline {b['baseline_datum'] or '–'})")
        stand = {"entwurf": "in Arbeit", "zurueck": "zurück"}
        print("Spezifikation: " + ", ".join(f"{t} {stand.get(b['spec'].get(t), b['spec'].get(t) or '–')}" for t in planung.TEILE))
        stufe = planung.wellen(con, [r[0] for r in con.execute("SELECT id FROM aufgabe WHERE bogen_id = ?", (a.id,))])
        for r in con.execute("SELECT * FROM aufgabe WHERE bogen_id = ? ORDER BY rang, id", (a.id,)):
            print(f"  Welle {stufe.get(r['id'], 1)}  A{r['id']:<5} {r['agent'] or '–':<10} [{r['status']}] {r['titel'][:90]}"
                  + (f"  ← {', '.join('A' + str(v) for v in planung.vorgaenger(con, r['id']))}" if planung.vorgaenger(con, r["id"]) else ""))
    else:
        prog = planung.prognose(con, pid, laeufe=300)
        for b in planung.boegen(con, pid):
            p = prog["boegen"].get(b["id"], {})
            print(f"Bogen {b['id']:<3} [{b['status']:<9}] {b['fertig']}/{b['gesamt'] - b['verworfen']} fertig"
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
        print(f"Bogen {a.bogen} {a.teil}: Version {planung.spec_schreiben(con, pid, _von(a), a.bogen, a.teil, text)} (Entwurf)")
    elif a.aktion == "vorlegen":
        fragen = planung.spec_vorlegen(con, pid, _von(a), a.bogen, a.teil)
        print(f"Bogen {a.bogen} {a.teil} vorgelegt" + (f" – Klärungsfragen: {', '.join('F' + str(f) for f in fragen)}" if fragen else ""))
    elif a.aktion in ("frei", "zurueck"):
        planung.spec_entscheiden(con, pid, _von(a), a.bogen, a.teil, a.aktion == "frei", a.kommentar)
        print(f"Bogen {a.bogen} {a.teil}: {a.aktion}")
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
        print("kein bereiter Schritt – alles vergeben, blockiert oder kein aktiver Bogen")
        return
    print(f"A{s['id']} [{s.get('status')}] {s['titel']}" + (f" (Bogen {s['bogen_id']})" if s.get("bogen_id") else ""))
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
                print("\n" + (f"Bogen {x['bogen_id']} „{titel.get(x['bogen_id'], '')}“" if gruppe.startswith("bogen:")
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
            print(f"Bogen {bid}: P50 {p['p50']} P85 {p['p85']} Ampel {p['ampel'] or '–'}")


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
                             a.fundstellen, a.aufgabe, a.blockiert)
        zusatz = dokumente.anhaenge_setzen(con, pid, _von(a), fid, anhaenge)
        print(f"F{fid} angelegt" + (" – Varianten: " + ", ".join(f"{k}=D{d}" for k, d in zusatz.items()) if zusatz else ""))
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


def cmd_regeln(a, con):
    pid = _projekt(con, a)
    for r in con.execute("SELECT ebene, nr, text, stand_utc FROM regel WHERE ebene = 'arbeit' OR projekt_id = ?"
                         " ORDER BY ebene, nr", (pid,)):
        print(f"{'KR' if r['ebene'] == 'arbeit' else 'PR'}{r['nr']} (Stand {_zeit(r['stand_utc'])}): {r['text']}\n")


def cmd_lauf(a, con):
    pid = _projekt(con, a)
    if a.aktion == "start":
        if not a.beschreibung and not a.rezept:
            raise kern.AmwFehler("--beschreibung oder --rezept angeben")
        lid = betrieb.lauf_start(con, pid, _von(a), a.beschreibung or a.rezept, a.rezept, not a.leicht, a.schirm, a.aufgabe,
                                 warten=a.warten, erwartet_min=a.dauer)
        w = [r["id"] for r in betrieb.wartende(con, pid)]
        if lid in w:
            print(f"L{lid} eingereiht (Platz {w.index(lid) + 1} von {len(w)}) – noch nicht rechnen. Der Wächter weckt dich mit"
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
    else:
        w = betrieb.wartende(con, pid)
        if w:
            print("Warteschlange:")
            for i, r in enumerate(w, 1):
                print(f"  {i}. L{r['id']:<5} {r['agent']:<8}{' schwer' if r['schwer'] else ''}{' Schirm' if r['schirm'] else ''}"
                      f"{' (vorgezogen)' if r['rang'] else ''} seit {_zeit(r['angemeldet_utc'])}  {r['beschreibung']}")
            print()
        for r in con.execute("SELECT * FROM lauf WHERE projekt_id = ? ORDER BY id DESC LIMIT ?", (pid, a.grenze)):
            print(f"L{r['id']:<5} {r['agent']:<8} [{r['status']}]{' schwer' if r['schwer'] else ''}{' Schirm' if r['schirm'] else ''}"
                  f" {_zeit(r['start_utc'])}–{_zeit(r['ende_utc']) or '…'} rc {r['rc'] if r['rc'] is not None else '–'}  {r['beschreibung']}")


def cmd_pruefung(a, con):
    pid = _projekt(con, a)
    if a.aktion == "bitte":
        prid = betrieb.pruefbitte(con, pid, _von(a), a.pruefer, a.zweig, a.sha, a.punkte, a.aufgabe)
        print(f"P{prid} an {a.pruefer}")
    elif a.aktion in ("gruen", "rot"):
        betrieb.pruefung_ergebnis(con, pid, _von(a), a.id, a.aktion, a.bemerkung)
        print(f"P{a.id} → {a.aktion}")
    elif a.aktion == "ist-gruen":
        r = betrieb.ist_gruen(con, pid, a.sha)
        print(f"grün: P{r['id']}" if r else "NICHT grün")
        return 0 if r else 3
    else:
        for r in con.execute("SELECT * FROM pruefung WHERE projekt_id = ? AND (? OR ergebnis = 'offen') ORDER BY id DESC LIMIT 50",
                             (pid, int(a.alle))):
            print(f"P{r['id']:<5} [{r['ergebnis']}] {r['zweig']}@{r['sha'][:8]} {r['bauer']} → {r['pruefer']}"
                  + (f" A{r['aufgabe_id']}" if r["aufgabe_id"] else ""))


def cmd_server(a, con):
    """Projekt-Server, die der Wächter überwacht (Port antwortet?) und auf Wunsch neu startet."""
    pid = _projekt(con, a)
    if a.aktion == "anmelden":
        if not (a.name and a.port):
            raise kern.AmwFehler("server anmelden <name> --port N [--start \"Befehl\" --ordner Pfad --neustart --zustaendig X]")
        print(f"Server {a.name}: " + ueberwachung.server_anmelden(con, pid, _von(a), a.name, a.port, a.start, a.ordner,
                                                                  a.neustart, a.zustaendig)
              + (" – der Wächter startet ihn bei Ausfall neu" if a.neustart else " – Ausfall wird gemeldet"))
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


def cmd_hinweis(a, con):
    pid = _projekt(con, a)
    if a.aktion == "setzen":
        print(f"Anweisung #{betrieb.hinweis(con, pid, _von(a), a.fuer, a.text, a.bis)} gesetzt")
    else:
        print(f"{betrieb.sperre_aufheben(con, pid, _von(a), a.id)} aufgehoben")


def cmd_rezept(a, con):
    pid = _projekt(con, a)
    if a.aktion == "setzen":
        print(betrieb.rezept_setzen(con, pid, a.name, a.befehl, a.beschreibung, a.schirm, a.speicher or 0.0, not a.leicht))
    elif a.aktion == "zeige":
        r = con.execute("SELECT * FROM rezept WHERE projekt_id = ? AND name = ?", (pid, a.name)).fetchone()
        if not r:
            raise kern.AmwFehler(f"Rezept „{a.name}“ gibt es nicht")
        print(f"{r['name']} (Stand {_zeit(r['stand_utc'])}){' · Schirm' if r['braucht_schirm'] else ''}"
              f"{' · schwer' if r['schwer'] else ''} · ≥ {r['braucht_speicher_gb']:g} GB frei\n{r['beschreibung'] or ''}\n{r['befehl']}")
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
    bid = wissen.beschluss_neu(con, _projekt(con, a), _von(a), a.stichwort, _text(a), a.quelle, a.thema, a.zeit,
                               a.wortlaut, a.aufgaben, a.ersetzt)
    print(f"B{bid} angelegt" + (f", B{a.ersetzt} überholt" if a.ersetzt else ""))


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
        sql = "SELECT schluessel, wert, geaendert_utc FROM notiz WHERE projekt_id = ?" + (" AND schluessel = ?" if eins else "")
        for r in con.execute(sql + " ORDER BY schluessel", (pid, eins) if eins else (pid,)):
            print(f"[{r['schluessel']}] {_zeit(r['geaendert_utc'])}\n{r['wert'] if eins else r['wert'][:160]}\n")


def cmd_release(a, con):
    pid = _projekt(con, a)
    if a.aktion == "merge":
        print(f"R{wissen.release_merge(con, pid, _von(a), a.titel, a.commit, _text(a) or None, a.aufgaben)} eingetragen")
    elif a.aktion == "version":
        rid, n = wissen.release_version(con, pid, _von(a), a.version, a.titel, a.commit, _text(a) or None)
        print(f"Version {a.version} (R{rid}) aus {n} Merge(s)")
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
        print("✓ Wächter neu gestartet – er lädt die Ansichten in den nächsten Sekunden hoch")
    else:
        print("! Wächter ist nicht eingerichtet: zuerst `amw dienst einrichten --ja`")
    print("Jetzt die Seite beim Hoster öffnen – der Assistent fragt nach derselben Adresse und einem Schlüssel.")
    return 0


def cmd_web(a, con):
    """Online-Teil (doc/online.md): Seite für den Webhoster bauen, Online-Speicher einrichten, einen Abgleich von Hand."""
    from . import abgleich
    if a.aktion == "bauen":
        quelle = os.path.join(os.path.dirname(__file__), "workbench.html")
        ziel = os.path.join(os.path.dirname(os.path.dirname(__file__)), "web", "inc", "seite.html")
        with open(quelle, encoding="utf-8") as f, open(ziel, "w", encoding="utf-8", newline="\n") as g:
            g.write(f.read())
        from . import __version__
        with open(os.path.join(os.path.dirname(ziel), "VERSION"), "w", encoding="utf-8", newline="\n") as g:
            g.write(__version__ + "\n")
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
        print(f"Abgleich im Dienst: {'an' if an else 'aus'} · PC zuletzt hochgeladen: {_zeit(pc[0][0]) if pc else '–'}"
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
            f"'{einrichtung.AUFGABE}'; 'Wächter neu gestartet' }} else {{ 'Wächter ist nicht eingerichtet (amw dienst einrichten)' }}")
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
          + " – der Wächter weckt diese Sitzung ab jetzt bei neuen Nachrichten")


def cmd_hook(a):
    from . import einrichtung
    print("Für .claude/settings.local.json eines Agenten-Ordners (zusammenführen: amw einrichten agenten-ordner <pfad>):")
    print(json.dumps(einrichtung.hook_einstellungen(), ensure_ascii=False, indent=2))
    print()
    print("Im Startbefehl je Agent vor `claude …` setzen (oder nach dem ersten Start: amw anmelden --von <Kennung>):")
    print(f"  $env:AMW_AGENT = '{a.agent}'")
    return 0


def cmd_sichern(a):
    from . import dokumente
    ziel = db.sichern(a.ziel)
    print(f"gesichert: {ziel}")
    n = dokumente.sichern(os.path.splitext(ziel)[0] + "-dokumente")           # Ablage daneben, nur Fehlendes
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
                          hooks=not a.ohne_hooks, fernsteuerung=a.fernsteuerung)
        return 0
    if a.aktion == "agenten-ordner":
        if not a.pfad:
            raise kern.AmwFehler("amw einrichten agenten-ordner <pfad> [--nur-zeigen] [--entfernen]")
        if a.entfernen:
            weg = einrichtung.agenten_ordner_entfernen(os.path.abspath(a.pfad), schreiben=not a.nur_zeigen)
            for x in weg or ["keine AMW-Einträge gefunden"]:
                print(("würde entfernen: " if a.nur_zeigen else "entfernt: ") + x if weg else x)
            return 0
        aenderungen = einrichtung.agenten_ordner_einrichten(os.path.abspath(a.pfad), schreiben=not a.nur_zeigen,
                                                            sperren=not a.ohne_sperren)
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
    p = argparse.ArgumentParser(prog="amw", description="Agentenmanagement Workbench")
    p.add_argument("--version", action="version", version=f"AMW {__version__}")
    p.add_argument("--projekt")
    p.add_argument("--von")
    s = p.add_subparsers(dest="cmd", required=True)

    x = s.add_parser("init", help="neue Datenbank anlegen")
    x.add_argument("--projekt", dest="projekt_init", help="gleich ein erstes Projekt anlegen")
    x.set_defaults(f=cmd_init, ohne_db=True)

    x = s.add_parser("projekt", help="Projekte: neu <name> | liste")
    x.add_argument("aktion", choices=["neu", "liste"])
    x.add_argument("name", nargs="?")
    x.add_argument("--beschreibung")
    x.set_defaults(f=cmd_projekt)

    x = s.add_parser("agent", help="neu | liste | profil | starten | beenden | startskript")
    x.add_argument("aktion", choices=["neu", "liste", "profil", "starten", "beenden", "startskript"])
    x.add_argument("kennung", nargs="?")
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
    x.add_argument("--rolle")
    x.add_argument("--grenzen")
    x.add_argument("--startbefehl")
    x.add_argument("--ohne-rund", action="store_true", help="bekommt keine Rundschreiben")
    x.set_defaults(f=cmd_agent)

    x = s.add_parser("posten", help="Nachricht schicken: --an CC2 (oder alle, Entwickler) --art auftrag|frage|info|… --kurz …")
    x.add_argument("--an", required=True)
    x.add_argument("--art", required=True)
    x.add_argument("--kurz", required=True)
    x.add_argument("--text")
    x.add_argument("--text-datei")
    x.add_argument("--antwort-auf", type=int)
    x.add_argument("--aufgabe", type=int)
    x.set_defaults(f=cmd_posten)

    x = s.add_parser("lesen", help="ohne Nummer: offene Liste; mit Nummer: ganze Nachricht")
    x.add_argument("id", type=int, nargs="?")
    x.add_argument("--grenze", type=int, default=50)
    x.set_defaults(f=cmd_lesen)

    x = s.add_parser("erledigt", help="Nachrichten als erledigt markieren: amw erledigt 12 13")
    x.add_argument("ids", type=int, nargs="+")
    x.add_argument("--bemerkung")
    x.set_defaults(f=cmd_erledigt)

    x = s.add_parser("aufgabe", help="neu | aendern N | liste | zeige N | start | fertig | … | kriterium N nr | plan N --text |"
                                     " planfrei N [--zurueck --kommentar]")
    x.add_argument("aktion", choices=["neu", "aendern", "liste", "zeige", "start", "blockiert", "wartet", "fertig", "verwerfen",
                                       "parken", "aktiv", "keine_prio", "pool", "kriterium", "plan", "planfrei"])
    x.add_argument("id", type=int, nargs="?")
    x.add_argument("nr", type=int, nargs="?", help="kriterium: Nummer des Kriteriums")
    x.add_argument("--titel")
    x.add_argument("--agent", help="Bearbeiter (auch „Entwickler“ für Schritte des Menschen)")
    x.add_argument("--auftrag")
    x.add_argument("--rang", type=int, default=50)
    x.add_argument("--pruefer")
    x.add_argument("--beleg")
    x.add_argument("--wartet-auf")
    x.add_argument("--bemerkung")
    x.add_argument("--alle", action="store_true")
    x.add_argument("--bogen", type=int, help="Planung: gehört zu Bogen N")
    x.add_argument("--kriterium", action="append", help="Planung: Abnahmekriterium, mehrfach (ersetzt die Liste)")
    x.add_argument("--schaetzung", type=float, help="Planung: Stunden")
    x.add_argument("--komplexitaet", type=int, help="Planung: 1–10; ab 7 braucht der Schritt einen freigegebenen Plan")
    x.add_argument("--nach", "--abhaengig-von", dest="nach", help="Vorgänger, z. B. 1201,1203 (startbar erst, wenn sie fertig sind)")
    x.add_argument("--verantwortlich", help="Planung: wer abnimmt bzw. Pläne freigibt")
    x.add_argument("--pruefbefehl", help="Planung: wie der Bearbeiter selbst prüft")
    x.add_argument("--dateien", help="Planung: Dateibereich, den er anfassen darf")
    x.add_argument("--anforderungen", help="Planung: abgedeckte Anforderungen, z. B. R1,R3")
    x.add_argument("--zusammenfassung", help="fertig: Pflicht für Schritte in einem Bogen; aendern: nachtragen")
    x.add_argument("--ohne-vorgaenger", help="aendern: diese Vorgänger lösen, z. B. 115")
    x.add_argument("--text", help="plan: der Plan")
    x.add_argument("--nein", action="store_true", help="kriterium: wieder als offen markieren")
    x.add_argument("--zurueck", action="store_true", help="planfrei: zurückweisen (mit --kommentar)")
    x.add_argument("--kommentar")
    x.set_defaults(f=cmd_aufgabe)

    x = s.add_parser("frage", help="Fragen an den Entwickler oder Lead: neu | liste [--geparkt] | antworten | nachtrag | verlauf |"
                                    " parken N [--grund] | aufnehmen N")
    x.add_argument("aktion", choices=["neu", "liste", "antworten", "nachtrag", "verlauf", "parken", "aufnehmen"])
    x.add_argument("id", type=int, nargs="?")
    x.add_argument("--an", choices=["entwickler", "tl"])
    x.add_argument("--kurz")
    x.add_argument("--worum")
    x.add_argument("--option", action="append", help="neu: 'A=Text' (mehrfach); antworten: Kennung")
    x.add_argument("--empfehlung")
    x.add_argument("--fundstellen")
    x.add_argument("--aufgabe", type=int)
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
    x.add_argument("--aufgabe", type=int)
    x.set_defaults(f=cmd_taetigkeit)

    x = s.add_parser("kontext", help="Pflicht-Kontext für einen Agenten")
    x.add_argument("agent", nargs="?")
    x.set_defaults(f=cmd_kontext)

    x = s.add_parser("regeln", help="alle geltenden Regeln (Arbeits- und Projektregeln)")
    x.set_defaults(f=cmd_regeln)

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
    x.add_argument("id", type=int, nargs="?")
    x.add_argument("wert", nargs="?", help="status: aktiv | fertig | geplant | verworfen")
    x.add_argument("--titel")
    x.add_argument("--ziel")
    x.add_argument("--abnahme", help="prüfbares Abnahmekriterium")
    x.add_argument("--zieldatum", help="JJJJ-MM-TT")
    x.add_argument("--nr", type=int, help="Reihenfolge")
    x.add_argument("--grund", help="nötig, wenn das Zieldatum nach der Baseline geändert wird")
    x.add_argument("--erzwingen", action="store_true")
    x.set_defaults(f=cmd_bogen)

    x = s.add_parser("spec", help="Spezifikation je Bogen: zeigen N [teil] | schreiben N teil --text/--datei | vorlegen N teil |"
                                  " frei N teil | zurueck N teil --kommentar  (teil: anforderungen | entwurf | schritte)")
    x.add_argument("aktion", choices=["zeigen", "schreiben", "vorlegen", "frei", "zurueck"])
    x.add_argument("bogen", type=int)
    x.add_argument("teil", nargs="?", choices=["anforderungen", "entwurf", "schritte"])
    x.add_argument("--text")
    x.add_argument("--datei")
    x.add_argument("--kommentar")
    x.set_defaults(f=cmd_spec)

    x = s.add_parser("schritt", help="naechster [--nehmen]: nächster bereiter Schritt (aktiver Bogen, ohne offene Vorgänger)")
    x.add_argument("aktion", choices=["naechster"])
    x.add_argument("--nehmen", action="store_true", help="gleich übernehmen (Bearbeiter = du, Status läuft)")
    x.set_defaults(f=cmd_schritt)

    x = s.add_parser("risiko", help="liste | neu --titel … | setzen N --status …")
    x.add_argument("aktion", choices=["liste", "neu", "setzen"])
    x.add_argument("id", type=int, nargs="?")
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
    x.add_argument("--bogen", type=int)
    x.set_defaults(f=cmd_risiko)

    x = s.add_parser("rueckblick", help="Rückblick je Bogen: amw rueckblick <bogen> [--gut … --schlecht … --massnahme … --gelernt …]"
                                        " | --uebernehmen <nr> --als aufgabe|beschluss")
    x.add_argument("bogen", type=int, nargs="?")
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
                                  " | prognose (P50/P85 je Schritt und Bogen) | status (Ampel je Dimension)")
    x.add_argument("aktion", choices=["pruefen", "prognose", "status", "akzeptieren", "wieder"])
    x.add_argument("schluessel", nargs="?", help="akzeptieren/wieder: Schlüssel des Befunds, z. B. bogen_ohne_zieldatum:B3")
    x.add_argument("--grund", help="akzeptieren: warum es so in Ordnung ist")
    x.add_argument("--kurz", action="store_true", help="pruefen: nur eine Zeile je Befund")
    x.set_defaults(f=cmd_plan)

    x = s.add_parser("lauf", help="Rechen-Läufe: start [--warten] prüft Halt, Speicher, einen schweren/Schirm-Lauf zur Zeit, Warteschlange")
    x.add_argument("aktion", choices=["start", "ende", "liste", "vorziehen"])
    x.add_argument("id", type=int, nargs="?")
    x.add_argument("--warten", action="store_true", help="ist der Platz belegt: einreihen statt ablehnen; Freigabe weckt dich")
    x.add_argument("--dauer", type=float, help="erwartete Dauer in Minuten; doppelt so lang → Warnung an den Lead")
    x.add_argument("--beschreibung")
    x.add_argument("--rezept")
    x.add_argument("--leicht", action="store_true", help="kein schwerer Lauf (keine Speicher-Grenze)")
    x.add_argument("--schirm", action="store_true")
    x.add_argument("--aufgabe", type=int)
    x.add_argument("--rc", type=int)
    x.add_argument("--ergebnis")
    x.add_argument("--abgebrochen", action="store_true")
    x.add_argument("--grenze", type=int, default=20)
    x.set_defaults(f=cmd_lauf)

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
    x.add_argument("id", type=int, nargs="?")
    x.add_argument("--pruefer")
    x.add_argument("--zweig")
    x.add_argument("--sha")
    x.add_argument("--punkte")
    x.add_argument("--aufgabe", type=int)
    x.add_argument("--bemerkung")
    x.add_argument("--alle", action="store_true")
    x.set_defaults(f=cmd_pruefung)

    x = s.add_parser("hinweis", help="Anweisung an einen Agenten oder alle (z. B. „keine Rechen-Jobs“)")
    x.add_argument("aktion", choices=["setzen", "aufheben"])
    x.add_argument("id", type=int, nargs="?")
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
    x.set_defaults(f=cmd_rezept)

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
            x.add_argument("--stichwort", required=True)
            x.add_argument("--quelle", required=True)
            x.add_argument("--thema")
            x.add_argument("--zeit")
            x.add_argument("--wortlaut")
            x.add_argument("--aufgaben")
            x.add_argument("--ersetzt", type=int)
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
    x.add_argument("--datei", help="statt der Positionsangabe (Brücke: nur aus eingang-tl/)")
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
    x.add_argument("--beschluss", help="entfernen ohne Lead-Rolle: Nummer eines geltenden Beschlusses (z. B. B2376)")
    x.add_argument("--text")
    x.add_argument("--text-datei")
    x.set_defaults(f=cmd_notiz)

    x = s.add_parser("dienst", help="Wächter als geplante Windows-Aufgabe: einrichten | entfernen | status | neustart |"
                                    " vordergrund (ohne Aufgabe in diesem Fenster, zum Ausprobieren)")
    x.add_argument("aktion", choices=["einrichten", "entfernen", "status", "neustart", "vordergrund"])
    x.add_argument("--port", type=int, default=None, help="Vorgabe: Zahnrad › Dieser PC (8780)")
    x.add_argument("--ja", action="store_true", help="wirklich ausführen (sonst nur anzeigen)")
    x.set_defaults(f=cmd_dienst, ohne_db=True)

    x = s.add_parser("web", help="Online-Teil: einrichten (Turso-Zugang, einmal) | status | einmal (Abgleich) | zweitfaktor-neu | bauen | schema")
    x.add_argument("aktion", choices=["einrichten", "bauen", "schema", "einmal", "status", "zweitfaktor-neu"])
    x.set_defaults(f=cmd_web)

    x = s.add_parser("anmelden", help="laufende Sitzung beim Wächter anmelden (ohne Neustart)")
    x.add_argument("--ersetzen", action="store_true", help="eine noch lebende andere Sitzung derselben Kennung ablösen")
    x.set_defaults(f=cmd_anmelden)

    x = s.add_parser("einrichten", help="ohne Angabe: geführte Einrichtung (fragt nach) | schnell --projekt-name … (ohne Fragen) |"
                                        " agenten-ordner <pfad> (Hooks, Statusline-Brücke, Sperren)")
    x.add_argument("aktion", nargs="?", choices=["assistent", "schnell", "agenten-ordner"], default="assistent")
    x.add_argument("pfad", nargs="?")
    x.add_argument("--nur-zeigen", action="store_true")
    x.add_argument("--ohne-sperren", action="store_true", help="keine Sperr-Regeln (Ordner dessen, der den Wächter betreut)")
    x.add_argument("--projekt-name", help="schnell: Name des Projekts")
    x.add_argument("--lead", default="TL", help="schnell: Kennung des Lead-Agenten (leer = keiner)")
    x.add_argument("--agenten", default="CC1", help="schnell: Kennungen, mit Komma")
    x.add_argument("--ordner", help="schnell: Projektordner der Agenten")
    x.add_argument("--rechte", default="vorgabe", choices=["vorgabe", "auto", "umgehen"])
    x.add_argument("--denkstufe", choices=["low", "medium", "high", "xhigh", "max"])
    x.add_argument("--mit-dienst", action="store_true", help="schnell: Wächter als geplante Aufgabe einrichten")
    x.add_argument("--ohne-hooks", action="store_true", help="schnell: Projektordner nicht anfassen")
    x.add_argument("--fernsteuerung", action="store_true", help="schnell: Remote Control für die Agenten an (Vorgabe aus)")
    x.add_argument("--entfernen", action="store_true", help="agenten-ordner: AMW-Einträge wieder herausnehmen")
    x.set_defaults(f=cmd_einrichten, ohne_db=True)

    x = s.add_parser("befehle", help="Befehlsreferenz als Markdown (für doc/befehle.md)")
    x.set_defaults(f=lambda a: print(befehle_markdown(), end="") or 0, ohne_db=True)

    x = s.add_parser("sichern", help="Sicherung der Datenbank (vollständige Kopie, auch während des Betriebs)")
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

    x = s.add_parser("release", help="Release Notes: je Merge eine Zeile, Version fasst zusammen")
    x.add_argument("aktion", choices=["merge", "version", "liste"])
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
         "Gemeinsam für alle: `--von <Kennung>` (wer handelt; sonst `AMW_AGENT`), `--projekt <Name>` (sonst das erste Projekt).", ""]
    z.append("| Befehl | Zweck |")
    z.append("|---|---|")
    for name in unter.choices:
        z.append(f"| [`{name}`](#{name}) | {(hilfe.get(name) or '').replace('|', '¦')} |")
    for name, sp in unter.choices.items():
        sp.prog = f"amw {name}"
        z += ["", f"## {name}", "```", sp.format_help().rstrip().replace("\r", ""), "```"]
    return "\n".join(z) + "\n"


def main(argv=None):
    for strom in (sys.stdout, sys.stderr):
        try:
            strom.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    a = parser().parse_args(argv)
    try:
        if getattr(a, "ohne_db", False):
            return a.f(a) or 0
        else:
            con = db.verbinde()
            try:
                rc = a.f(a, con)
            finally:
                con.close()
            return rc or 0
    except (kern.AmwFehler, LookupError, FileNotFoundError, FileExistsError, ValueError) as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
