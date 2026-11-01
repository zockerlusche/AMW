"""Kommandozeile `amw` – einziger Schreibweg der Agenten (→ doc/10-architektur.md §2).

Wer bin ich: --von oder Umgebungsvariable AMW_AGENT. Welches Projekt: --projekt, AMW_PROJEKT oder das
einzige vorhandene. Ausgabe immer UTF-8 (→ 04: cp1252-Abbrüche).
"""
import argparse
import json
import os
import sys

from . import db, kern


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
    return (t or "")[5:16].replace("T", " ")


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
        von = a.von or os.environ.get("AMW_AGENT") or kern.ENTWICKLER
        print(f"F{a.id} → {kern.frage_antworten(con, pid, a.id, art, wert, 'cli', von)}")


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
    x.add_argument("aktion", choices=["neu", "liste", "zeige", "start", "blockiert", "wartet", "fertig", "verwerfen"])
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
            a.f(a)
        else:
            con = db.verbinde()
            try:
                a.f(a, con)
            finally:
                con.close()
    except (kern.AmwFehler, LookupError, FileNotFoundError, FileExistsError) as e:
        print(f"FEHLER: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
