"""Kommandozeile `amw` – einziger Schreibweg der Agenten (→ doc/10-architektur.md §2).

Wer bin ich: --von oder Umgebungsvariable AMW_AGENT. Welches Projekt: --projekt, AMW_PROJEKT oder das
einzige vorhandene. Ausgabe immer UTF-8 (→ 04: cp1252-Abbrüche).
"""
import argparse
import json
import os
import sys
from datetime import datetime

from . import betrieb, db, kern, wissen


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


def cmd_aufgabe(a, con):
    pid = _projekt(con, a)
    if a.aktion == "neu":
        aid = kern.aufgabe_neu(con, pid, _von(a), a.titel, a.agent, a.auftrag, a.rang, a.pruefer, a.abhaengig_von)
        print(f"A{aid} angelegt")
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
        neu = kern.aufgabe_status(con, pid, _von(a), a.id, a.aktion, a.beleg, a.wartet_auf, a.bemerkung)
        print(f"A{a.id} → {neu}")


def cmd_frage(a, con):
    pid = _projekt(con, a)
    if a.aktion == "neu":
        optionen = []
        for o in a.option or []:
            kenn, _, text = o.partition("=")
            optionen.append((kenn.strip(), text.strip()))
        fid = kern.frage_neu(con, pid, _von(a), a.an, a.kurz, optionen, a.empfehlung, a.grund, a.worum,
                             a.fundstellen, a.aufgabe, a.blockiert)
        print(f"F{fid} angelegt")
    elif a.aktion == "liste":
        for r in kern.offene_fragen(con, pid, a.an):
            opt = " · ".join(f"{o['kenn']}) {o['text']}" for o in json.loads(r["optionen"]))
            print(f"F{r['id']} an {r['an']} von {r['von']}{' BLOCKIERT' if r['blockiert'] else ''}: {r['kurz']}"
                  + (f"\n   {opt}" if opt else "") + (f"  → Empfehlung {r['empfehlung']}" if r["empfehlung"] else ""))
    elif a.aktion == "antworten":
        art, wert = ("option", a.option[0]) if a.option else ("rueckfrage", a.rueckfrage) if a.rueckfrage else ("text", a.text)
        if not wert:
            raise kern.AmwFehler("--option, --text oder --rueckfrage angeben")
        # kein stilles „Entwickler“ als Absender: Marcel antwortet in der Workbench, wer hier antwortet, nennt sich
        print(f"F{a.id} → {kern.frage_antworten(con, pid, a.id, art, wert, 'cli', _von(a))}")


def cmd_halt(a, con):
    sid = kern.halt(con, _projekt(con, a), _von(a), a.fuer, a.text)
    print(f"Halt #{sid} für {a.fuer} gesetzt; STOPP verschickt")


def cmd_weiter(a, con):
    n = kern.weiter(con, _projekt(con, a), _von(a), a.fuer)
    print(f"{n} Halt aufgehoben" if n else "kein Halt aktiv")


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
        lid = betrieb.lauf_start(con, pid, _von(a), a.beschreibung or a.rezept, a.rezept, not a.leicht, a.schirm, a.aufgabe)
        print(f"L{lid} läuft – am Ende: amw lauf ende {lid} --rc <Code>")
    elif a.aktion == "ende":
        betrieb.lauf_ende(con, pid, _von(a), a.id, a.rc, a.ergebnis, a.abgebrochen)
        print(f"L{a.id} beendet")
    else:
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


def cmd_notiz(a, con):
    pid = _projekt(con, a)
    if a.aktion == "setzen":
        print(wissen.notiz_setzen(con, pid, _von(a), a.schluessel, _text(a)))
    else:
        sql = "SELECT schluessel, wert, geaendert_utc FROM notiz WHERE projekt_id = ?" + (" AND schluessel = ?" if a.schluessel else "")
        for r in con.execute(sql + " ORDER BY schluessel", (pid, a.schluessel) if a.schluessel else (pid,)):
            print(f"[{r['schluessel']}] {_zeit(r['geaendert_utc'])}\n{r['wert'] if a.schluessel else r['wert'][:160]}\n")


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


def cmd_dienst(a):
    from . import einrichtung
    if a.aktion == "status":
        print(einrichtung.status(a.port))
        return 0
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
    """Laufende Sitzung ohne Neustart anmelden (Umschalten, doc/10 §6): wie der Hook bei startup, aus der eigenen
    Umgebung der Claude-Code-Shell. Der Schlüssel landet nur in der Sitzungsdatei, nie in der Ausgabe."""
    from . import hook
    kennung = _von(a)
    hinweis = hook.anmelden(con, _projekt(con, a), kennung,
                            {"session_id": os.environ.get("CLAUDE_CODE_SESSION_ID"), "cwd": os.getcwd()})
    if hinweis:
        raise kern.AmwFehler(hinweis)
    print(f"{kennung} angemeldet – der Wächter weckt diese Sitzung ab jetzt bei neuen Nachrichten")


def cmd_hook(a):
    from . import einrichtung
    print("In .claude/settings.local.json des Projektordners zusammenführen (nicht überschreiben):")
    print(json.dumps(einrichtung.hook_einstellungen(), ensure_ascii=False, indent=2))
    print()
    print("Im Startbefehl je Agent (z. B. layerit-agenten.ps1) vor `claude …` setzen:")
    print(f"  $env:AMW_AGENT = '{a.agent}'")
    return 0


# --- Aufbau --------------------------------------------------------------------------------------

def parser():
    p = argparse.ArgumentParser(prog="amw", description="Agentenmanagement Workbench")
    p.add_argument("--projekt")
    p.add_argument("--von")
    s = p.add_subparsers(dest="cmd", required=True)

    x = s.add_parser("init", help="neue Datenbank anlegen")
    x.add_argument("--projekt", dest="projekt_init", help="gleich ein erstes Projekt anlegen")
    x.set_defaults(f=cmd_init, ohne_db=True)

    x = s.add_parser("projekt")
    x.add_argument("aktion", choices=["neu", "liste"])
    x.add_argument("name", nargs="?")
    x.add_argument("--beschreibung")
    x.set_defaults(f=cmd_projekt)

    x = s.add_parser("agent")
    x.add_argument("aktion", choices=["neu", "liste"])
    x.add_argument("kennung", nargs="?")
    x.add_argument("--rolle")
    x.add_argument("--grenzen")
    x.add_argument("--startbefehl")
    x.add_argument("--ohne-rund", action="store_true", help="bekommt keine Rundschreiben")
    x.set_defaults(f=cmd_agent)

    x = s.add_parser("posten")
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

    x = s.add_parser("erledigt")
    x.add_argument("ids", type=int, nargs="+")
    x.add_argument("--bemerkung")
    x.set_defaults(f=cmd_erledigt)

    x = s.add_parser("aufgabe")
    x.add_argument("aktion", choices=["neu", "liste", "zeige", "start", "blockiert", "wartet", "fertig", "verwerfen",
                                       "parken", "aktiv", "keine_prio", "pool"])
    x.add_argument("id", type=int, nargs="?")
    x.add_argument("--titel")
    x.add_argument("--agent")
    x.add_argument("--auftrag")
    x.add_argument("--rang", type=int, default=50)
    x.add_argument("--pruefer")
    x.add_argument("--abhaengig-von")
    x.add_argument("--beleg")
    x.add_argument("--wartet-auf")
    x.add_argument("--bemerkung")
    x.add_argument("--alle", action="store_true")
    x.set_defaults(f=cmd_aufgabe)

    x = s.add_parser("frage")
    x.add_argument("aktion", choices=["neu", "liste", "antworten"])
    x.add_argument("id", type=int, nargs="?")
    x.add_argument("--an", choices=["entwickler", "tl"])
    x.add_argument("--kurz")
    x.add_argument("--worum")
    x.add_argument("--option", action="append", help="neu: 'A=Text' (mehrfach); antworten: Kennung")
    x.add_argument("--empfehlung")
    x.add_argument("--grund")
    x.add_argument("--fundstellen")
    x.add_argument("--aufgabe", type=int)
    x.add_argument("--blockiert", action="store_true")
    x.add_argument("--text")
    x.add_argument("--rueckfrage")
    x.set_defaults(f=cmd_frage)

    x = s.add_parser("halt", help="alle oder einen Agenten anhalten")
    x.add_argument("--fuer", default="alle")
    x.add_argument("--text", required=True)
    x.set_defaults(f=cmd_halt)

    x = s.add_parser("weiter", help="Halt aufheben")
    x.add_argument("--fuer", default="alle")
    x.set_defaults(f=cmd_weiter)

    x = s.add_parser("kontext", help="Pflicht-Kontext für einen Agenten")
    x.add_argument("agent", nargs="?")
    x.set_defaults(f=cmd_kontext)

    x = s.add_parser("regeln")
    x.set_defaults(f=cmd_regeln)

    x = s.add_parser("lauf", help="Rechen-Läufe: start prüft Halt, Speicher, einen schweren/Schirm-Lauf zur Zeit")
    x.add_argument("aktion", choices=["start", "ende", "liste"])
    x.add_argument("id", type=int, nargs="?")
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

    x = s.add_parser("notiz", help="gepflegte Notizen (Schlüssel/Wert)")
    x.add_argument("aktion", choices=["setzen", "zeige"])
    x.add_argument("schluessel", nargs="?")
    x.add_argument("--text")
    x.add_argument("--text-datei")
    x.set_defaults(f=cmd_notiz)

    x = s.add_parser("dienst", help="Wächter als geplante Windows-Aufgabe: einrichten | entfernen | status")
    x.add_argument("aktion", choices=["einrichten", "entfernen", "status"])
    x.add_argument("--port", type=int, default=8780)
    x.add_argument("--ja", action="store_true", help="wirklich ausführen (sonst nur anzeigen)")
    x.set_defaults(f=cmd_dienst, ohne_db=True)

    x = s.add_parser("anmelden", help="laufende Sitzung beim Wächter anmelden (ohne Neustart)")
    x.set_defaults(f=cmd_anmelden)

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
    except (kern.AmwFehler, LookupError, FileNotFoundError, FileExistsError) as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
