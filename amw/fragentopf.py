"""Fragen-Topf (A1945, K10, D1258 §12 Pkt 2, Entwurf #30877, Ja #30878).

- Bündeln: Fragen an den Menschen gehen nicht einzeln als Push, sondern höchstens alle fragen_takt_h Stunden (Projekt-Einstellung,
  Vorgabe 4; 0 = sofort wie bisher) als EIN Push „n Fragen an dich“. Sofort geht eine Frage, die blockiert: als blockierend
  gestellt (frage.blockiert) oder ein Agent, der an ihr hängt, hat sonst nichts Startklares in seiner Liste.
- Was hängt: die Aufgaben mit offenem Wartegrund F<n> und ihre Agenten – abgeleitet, nichts zu pflegen.
- Frist: bleibt eine Frage länger als fragen_frist_h (Vorgabe 24) offen, meldet die AMW das einmal dem Lead und sagt jedem
  Agenten, der an ihr hängt, womit er weitermacht (seine nächste startklare Aufgabe) – der Rest läuft weiter. Ereignis
  frage_frist (einmal je Frage). Nie automatisch verwerfen oder die Empfehlung annehmen.
"""
import datetime
import json

from . import db, kern

TAKT_H = 4
FRIST_H = 24
FRIST_ART = "frage_frist"


def _einstellung(con, pid, name, vorgabe):
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        v = json.loads((r[0] if r else None) or "{}").get(name)
    except ValueError:
        v = None
    return vorgabe if v is None else float(v)


def takt_h(con, pid):
    return _einstellung(con, pid, "fragen_takt_h", TAKT_H)


def frist_h(con, pid):
    return _einstellung(con, pid, "fragen_frist_h", FRIST_H)


def haengt(con, pid, fid):
    """[{aufgabe, titel, agent}] – Aufgaben mit offenem Wartegrund F<fid>."""
    return [dict(r) for r in con.execute(
        "SELECT a.id AS aufgabe, a.titel, a.agent FROM wartegrund w JOIN aufgabe a ON a.id = w.aufgabe_id WHERE a.projekt_id = ?"
        " AND w.bezug = ? AND w.erledigt_utc IS NULL AND a.status NOT IN ('fertig', 'verworfen') ORDER BY a.id", (pid, f"F{int(fid)}"))]


def naechste_startklare(con, pid, agent, ohne=()):
    from . import arbeitsliste
    return next((x for x in arbeitsliste.liste(con, pid, agent) if x["status"] == "wartet" and not x["gruende"] and x["id"] not in ohne), None)


def blockiert(con, pid, fid):
    """Hält die Frage Arbeit auf? Als blockierend gestellt, oder ein Agent, der an ihr hängt, hat nichts anderes Startklares."""
    f = con.execute("SELECT blockiert FROM frage WHERE id = ? AND projekt_id = ?", (fid, pid)).fetchone()
    if f and f["blockiert"]:
        return True
    h = haengt(con, pid, fid)
    return any(x["agent"] and not naechste_startklare(con, pid, x["agent"], {y["aufgabe"] for y in h}) for x in h)


def zurueckhalten(con, pid, eintraege, jetzt_s):
    """Für push.runde: welche fälligen Frage-Pushes jetzt noch warten (Takt nicht um, keine blockiert). Rückgabe: Menge der ids."""
    takt = takt_h(con, pid)
    fragen = [p for p in eintraege if p["ereignis"] == "frage"]
    if not fragen or takt <= 0:
        return set()
    if any(blockiert(con, pid, _fid(p["schluessel"])) for p in fragen):
        return set()                                   # eine blockiert: alle zusammen jetzt
    r = con.execute("SELECT max(geaendert_utc) FROM push_versand WHERE projekt_id = ? AND ereignis = 'frage'"
                    " AND ergebnis IN ('gesendet', 'teilweise')", (pid,)).fetchone()[0]
    if not r:
        return set()                                   # noch nie gebündelt: jetzt
    alt = jetzt_s - datetime.datetime.strptime(r, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()
    return {p["id"] for p in fragen} if alt < takt * 3600 else set()


def _fid(schluessel):
    try:
        return int(str(schluessel).split(":")[1])
    except (IndexError, ValueError):
        return 0


def runde(con, jetzt=None):
    """Dienst-Runde: Fristen der offenen Fragen an den Menschen – einmal je Frage Lead + hängende Agenten. Rückgabe: Texte."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    aus = []
    for f in con.execute("SELECT * FROM frage WHERE an = 'entwickler' AND status = 'offen' AND geparkt_utc IS NULL").fetchall():
        pid = f["projekt_id"]
        alt_h = (jetzt - datetime.datetime.strptime(f["zeit_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)).total_seconds() / 3600
        if alt_h < frist_h(con, pid) or con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND text = ?",
                                                   (pid, FRIST_ART, f"F{f['id']}")).fetchone():
            continue
        h = haengt(con, pid, f["id"])
        lead = kern.lead(con, pid)
        zeilen = []
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=FRIST_ART, text=f"F{f['id']}")
            for x in h:
                if not x["agent"] or x["agent"] in (kern.ENTWICKLER, lead):
                    continue
                n = naechste_startklare(con, pid, x["agent"], {y["aufgabe"] for y in h})
                zeilen.append(f"A{x['aufgabe']} ({x['agent']})" + (f" → weiter mit A{n['id']}" if n else " → nichts Startklares"))
                if n:
                    kern._posten(con, pid, "AMW", x["agent"], "auftrag", f"F{f['id']} seit {int(alt_h)} h offen – weiter mit A{n['id']}"[:140],
                                 f"A{x['aufgabe']} wartet auf F{f['id']} ({f['kurz'][:120]}). Bis die Antwort kommt: A{n['id']} · {n['titel']}."
                                 " Die AMW meldet sich, sobald die Frage beantwortet ist.", aufgabe_id=n["id"])
            if lead:
                kern._posten(con, pid, "AMW", lead, "meldung", f"F{f['id']} seit {int(alt_h)} h ohne Antwort"[:140],
                             f"F{f['id']}: {f['kurz']}\nHängt: " + (", ".join(zeilen) or "nichts") + "\nDie AMW verwirft nichts und nimmt "
                             "keine Empfehlung an – erinnern, umplanen oder parken entscheidest du.")
        aus.append(f"F{f['id']}: Frist ({len(h)} hängen)")
    return aus
