"""A2031 (TH164 F2 Schritt 3, TL #31457 a): rollende Feinplanung – kein Stillstand zwischen Meilensteinen.

Voll geplant wird immer nur der nächste Meilenstein. Die AMW stößt seine Feinplanung selbst an:
- nach dem Grobplan, solange noch kein Meilenstein läuft: für den ersten,
- sobald der laufende Meilenstein „bereit zur Abnahme“ ist (A2002) oder nur noch sein letztes Paket läuft: für den nächsten.
Der Mensch gibt den Plan von M(n+1) frei, während M(n) noch auf seine Abnahme wartet. Das Ja zum Feinplan ist zugleich der
Start (plan_starten): freigeben und – sobald frei – den Meilenstein an den Disponenten übergeben (reihenfolge.starten).

„Nächster“ = der geplante Meilenstein mit der kleinsten Nummer, dessen Grob-Freigabe steht und der noch keine Pakete hat.
Einmal je Meilenstein (plan_ereignis FAELLIG); wer die Pakete erzeugt, steckt in ANSTOSSEN – bis der Feinplaner-Lauf (nach
A2030) steht, ein Auftrag an den Lead. Nichts wird hier gespeichert außer dem Ereignis; alles andere ist abgeleitet.
"""
import json

from . import db, kern

FAELLIG = "feinplan_faellig"        # plan_ereignis.art – {"bogen", "nr", "anlass"}, einmal je Meilenstein
OFFEN = ("wartet", "laeuft", "blockiert")


def _grob_frei(con, pid):
    from . import planansicht
    z = planansicht._zustaende(con, pid)
    return {bid for (bid, art), x in z.items() if art == "grob" and x["an"]}


def _grob_offen(con, pid):
    frei = _grob_frei(con, pid)
    return any(r[0] not in frei for r in con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND status = 'geplant'", (pid,)))


def _offene(con, bid):
    return [r[0] for r in con.execute("SELECT status FROM aufgabe WHERE bogen_id = ? AND status NOT IN ('fertig', 'verworfen')", (bid,))]


def letztes_laeuft(con, bid):
    """Nur noch laufende Pakete offen (mindestens eins) – nichts wartet mehr auf einen Start."""
    offen = _offene(con, bid)
    return bool(offen) and all(s == "laeuft" for s in offen)


def anlass(con, pid):
    """Warum jetzt fein planen? „erster“ (kein Meilenstein läuft, keiner wartet auf seine Abnahme), „bereit“ (der laufende ist
    bereit zur Abnahme), „letztes“ (sein letztes Paket läuft) – oder None, solange der laufende noch Pakete vor sich hat."""
    from . import planautomatik
    aktiv = con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status = 'aktiv' ORDER BY nr, id", (pid,)).fetchall()
    if not aktiv:
        return "erster"
    for b in aktiv:
        if not (planautomatik.bereit_zur_abnahme(con, b) or letztes_laeuft(con, b["id"])):
            return None                              # ein laufender hat noch Arbeit vor sich – nicht vorplanen
    return "bereit" if all(planautomatik.bereit_zur_abnahme(con, b) for b in aktiv) else "letztes"


def naechster(con, pid):
    """Der nächste Meilenstein, der fein geplant werden muss (Zeile) – oder None. Der Reihe nach (Nummer): steht davor ein
    Meilenstein, dessen Grob-Freigabe fehlt oder dessen Plan noch auf das Ja wartet, wird nichts vorgeplant."""
    from . import planansicht
    z = planansicht._zustaende(con, pid)
    for b in con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status = 'geplant' ORDER BY nr, id", (pid,)).fetchall():
        if not (z.get((b["id"], "grob")) or {}).get("an"):
            return None                              # erst wenn sein Meilenstein freigegeben ist
        if not con.execute("SELECT 1 FROM aufgabe WHERE bogen_id = ? LIMIT 1", (b["id"],)).fetchone():
            return b
        if not (z.get((b["id"], "plan")) or {}).get("an"):
            return None                              # ein Plan wartet schon auf das Ja – nur der nächste ist voll geplant
    return None


def _schon(con, pid, bid):
    return con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND bogen_id = ?", (pid, FAELLIG, bid)).fetchone()


def _lead_beauftragen(con, pid, b, grund):
    """Übergang bis zum Feinplaner-Lauf: der Lead zerlegt den Meilenstein in Pakete."""
    lead = kern.lead(con, pid)
    if not lead:
        return
    with db.schreiben(con):
        kern._posten(con, pid, "AMW", lead, "auftrag", f"Meilenstein {b['nr']} „{b['titel'][:70]}“ jetzt fein planen",
                     f"{grund}. Pakete für Meilenstein {b['nr']} anlegen (Ziel, Thema, Dateien, Abnahme, Abhängigkeiten, Dauer)"
                     " und den Plan zur Freigabe stellen – das Ja startet ihn.")


ANSTOSSEN = _lead_beauftragen        # nach A2030: der Feinplaner-Lauf (Meilenstein → Pakete)

GRUND = {"erster": "Der Grobplan steht, noch läuft kein Meilenstein",
         "bereit": "Der laufende Meilenstein ist bereit zur Abnahme",
         "letztes": "Im laufenden Meilenstein läuft das letzte Paket"}


def projekt(con, pid):
    """Eine Runde für ein Projekt: Feinplanung des nächsten Meilensteins anstoßen, wenn es Zeit ist (einmal je Meilenstein).
    Rückgabe [(Bogen-Id, Anlass)]."""
    from . import planautomatik
    if not planautomatik.an(con, pid):
        return []
    a = anlass(con, pid)
    if a == "erster" and _grob_offen(con, pid):
        return []                                    # „nach dem Grobplan“: erst wenn alle geplanten Meilensteine frei sind
    b = naechster(con, pid) if a else None
    if not a or not b or _schon(con, pid, b["id"]):
        return []
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=FAELLIG, bogen_id=b["id"],
                     text=json.dumps({"bogen": b["id"], "nr": b["nr"], "anlass": a}, ensure_ascii=False))
    ANSTOSSEN(con, pid, b, GRUND[a])
    return [(b["id"], a)]


def runde(con):
    """Vom Dienst je Aufsichtsrunde: alle Projekte; ein Projekt hält die anderen nie auf."""
    aus = []
    for (pid,) in con.execute("SELECT id FROM projekt").fetchall():
        try:
            aus += projekt(con, pid)
        except Exception as x:                       # noqa: BLE001
            aus.append((0, f"Projekt {pid}: {type(x).__name__}: {x}"))
    return aus


def plan_starten(con, pid, von, bid):
    """„Plan freigeben und starten“ – ein Klick: das Ja zum Feinplan; ist der Plan damit frei (Mensch allein, oder das zweite Ja
    von Co bzw. Lead), geht der Meilenstein sofort in die Umsetzung (reihenfolge.starten: aktiv, startklar, verteilen) –
    auch während der vorige noch auf seine Abnahme wartet. {"frei", "ja_fehlt"?, "gestartet"?}"""
    from . import planansicht, reihenfolge
    r = planansicht.freigeben(con, pid, von, bid, "plan")
    if not r.get("frei"):
        return r
    starter = von if kern.ist_lead(con, pid, von) else (kern.lead(con, pid) or kern.ENTWICKLER)
    return {**r, "gestartet": reihenfolge.starten(con, pid, starter, bid)}
