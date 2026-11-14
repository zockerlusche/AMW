"""Release-Takt je Projekt (A1656): Der Dienst stößt im Takt an, was ausgeliefert werden kann – er pusht nie selbst.

Bereit ist eine Aufgabe, wenn ihr letzter geprüfter Stand GRÜN ist, der Lead für genau diesen Zweig das Merge-OK gegeben hat,
ein grüner Gesamtlauf genau diesen Stand sauber geprüft hat und der Stand noch nicht in main liegt. Takt (Projekt-Wahl
„release_takt“): sofort (jede Runde der Aufsicht), taeglich (einmal am Tag ab „release_zeit“ HH:MM Ortszeit, Vorgabe
18:00), meilenstein (erst, wenn jede offene Aufgabe des Meilensteins bereit ist), aus (Vorgabe).

Angestoßen wird einmal je Stand: ein Auftrag an den Merge-Dienst des Projekts (sonst den Lead). Im Repository der AMW selbst
nennt er den Befehl `amw release ausliefern --zweig …`; andere Projekte haben eigene Schritte – dort heißt es nur „bereit zum
Ausliefern“.
"""
import datetime
import os
import subprocess

from . import betrieb, db, kern

ZEIT_VORGABE = "18:00"


def _git(ordner, *args):
    try:
        r = subprocess.run(["git", "-C", ordner, *args], capture_output=True, text=True, timeout=60, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.returncode


def eigenes_repo(ordner):
    """Ist der Projektordner das Repository dieser AMW? (Nur dort gibt es `amw release ausliefern`.)"""
    wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return bool(ordner) and os.path.normcase(os.path.abspath(ordner)) == os.path.normcase(wurzel)


def bereit(con, pid):
    """Aufgaben, die ausgeliefert werden können: [{aufgabe_id, zweig, sha, pruefung, lauf, bogen_id}]."""
    ordner = kern.projekt_ordner(con, pid)
    if not ordner:
        return []
    aus = []
    for p in con.execute("SELECT p.* FROM pruefung p WHERE p.projekt_id = ? AND p.aufgabe_id IS NOT NULL AND p.id = ("
                         " SELECT max(id) FROM pruefung q WHERE q.projekt_id = p.projekt_id AND q.aufgabe_id = p.aufgabe_id)"
                         " AND p.ergebnis = 'gruen'", (pid,)).fetchall():
        if not betrieb.merge_ok(con, pid, p["aufgabe_id"], p["zweig"]):
            continue
        sha = betrieb.voller_sha(con, pid, p["sha"])           # ältere Prüfbitten nennen kurze Stände
        lauf = con.execute("SELECT id FROM lauf WHERE projekt_id = ? AND status = 'fertig' AND rc = 0 AND ergebnis LIKE ?"
                           " ORDER BY id DESC LIMIT 1", (pid, f"%{betrieb.stand_text(('', sha, True))}%")).fetchone()
        if not lauf:
            continue
        if _git(ordner, "merge-base", "--is-ancestor", sha, "main") == 0:         # schon in main: nichts mehr zu tun
            continue
        a = con.execute("SELECT bogen_id FROM aufgabe WHERE id = ?", (p["aufgabe_id"],)).fetchone()
        aus.append({"aufgabe_id": p["aufgabe_id"], "zweig": p["zweig"], "sha": sha, "pruefung": p["id"], "lauf": lauf["id"],
                    "bogen_id": a["bogen_id"] if a else None})
    return aus


def _zeit(con, pid):
    import json
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    return (json.loads(r[0] or "{}").get("release_zeit") if r else None) or ZEIT_VORGABE


def _schon(con, pid, art, text):
    return con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND text = ?", (pid, art, text)).fetchone()


def anstossen(con, pid, jetzt=None):
    """Eine Runde für ein Projekt. Rückgabe: die angestoßenen Aufgaben (Liste von Texten)."""
    takt = kern.projekt_wahl(con, pid, "release_takt")
    if takt == "aus":
        return []
    jetzt = jetzt or datetime.datetime.now().astimezone()
    if takt == "taeglich":
        tag = jetzt.strftime("%Y-%m-%d")
        if jetzt.strftime("%H:%M") < _zeit(con, pid) or _schon(con, pid, "release_takt_tag", tag):
            return []
        with db.schreiben(con):                      # einmal am Tag geschaut – was später fertig wird, wartet bis morgen
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="release_takt_tag", text=tag)
    kandidaten = bereit(con, pid)
    if takt == "meilenstein":
        ids = {k["aufgabe_id"] for k in kandidaten}
        fertig_boegen = set()
        for b in {k["bogen_id"] for k in kandidaten if k["bogen_id"]}:
            offen = {r[0] for r in con.execute("SELECT id FROM aufgabe WHERE projekt_id = ? AND bogen_id = ?"
                                               " AND status NOT IN ('fertig', 'verworfen')", (pid, b))}   # ausgeliefert = fertig
            if offen <= ids:
                fertig_boegen.add(b)
        kandidaten = [k for k in kandidaten if k["bogen_id"] in fertig_boegen]
    an = betrieb.merge_dienst(con, pid) or kern.lead(con, pid)
    if not an:
        return []
    eigen = eigenes_repo(kern.projekt_ordner(con, pid))
    aus = []
    for k in kandidaten:
        if _schon(con, pid, "release_angestossen", k["sha"]):
            continue
        kurz = f"Bereit zum Ausliefern: A{k['aufgabe_id']} {k['zweig']}@{k['sha'][:8]}"
        text = (f"Prüfung P{k['pruefung']} grün, Merge-OK, Gesamtlauf L{k['lauf']} hat genau diesen Stand geprüft.\n"
                + (f"amw release ausliefern --zweig {k['zweig']}" if eigen else "Ausliefern mit den Schritten eures Projekts."))
        with db.schreiben(con):
            kern._posten(con, pid, "AMW", an, "auftrag", kurz, text, aufgabe_id=k["aufgabe_id"])
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="release_angestossen",
                         aufgabe_id=k["aufgabe_id"], text=k["sha"])
        aus.append(kurz)
    return aus


def runde(con):
    """Vom Dienst je Aufsicht: alle Projekte mit eingeschaltetem Takt."""
    aus = []
    for (pid,) in con.execute("SELECT id FROM projekt").fetchall():
        try:
            aus += anstossen(con, pid)
        except Exception as x:                       # noqa: BLE001 – ein Projekt hält die anderen nie auf
            aus.append(f"Release-Takt Projekt {pid}: {type(x).__name__}: {x}")
    return aus
