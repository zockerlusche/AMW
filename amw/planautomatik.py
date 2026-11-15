"""Planung automatisch (Marcel 15.11., W2153): Pläne leben mit dem Projekt – der Lead sagt nur, was passiert ist, die AMW
passt den Plan selbst an.

A1741: Startet ein Agent einen Lauf zu einer seiner Aufgaben, die noch nicht begonnen hat, gilt sie als „läuft“. Die Aufgabe
kommt aus --aufgabe, sonst aus „A1234“ in der Beschreibung, sonst aus dem Zweig im Ordner des Laufs (a1234, a1234-2 …).
Nur wenn die Aufgabe dem Agenten gehört, auf „wartet“ steht und keinen offenen Wartegrund hat (wartet sie auf jemanden, ist ein
Lauf dazu kein Beginn – etwa ein Gesamtlauf, während die Prüfung beim Lead liegt). Eins nach dem anderen gilt weiter: läuft beim
Agenten schon ein anderes Stück, bleibt alles, wie es ist. Abschaltbar je Projekt (plan_automatik = aus).
"""
import re
import subprocess

from . import db, kern

AUFGABE_IM_TEXT = re.compile(r"(?<![A-Za-z0-9])A(\d{1,6})(?![0-9])")
AUFGABE_IM_ZWEIG = re.compile(r"^a(\d{1,6})(?:-\d+)?$", re.IGNORECASE)


def an(con, pid):
    return kern.projekt_wahl(con, pid, "plan_automatik") == "an"


def zweig(ordner):
    """Name des ausgecheckten Zweigs im Ordner (None: kein Git, losgelöster Stand oder Fehler). Nur lesen."""
    if not ordner:
        return None
    try:
        r = subprocess.run(["git", "-C", ordner, "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, timeout=5,
                           stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired):
        return None
    name = r.stdout.strip() if r.returncode == 0 else ""
    return name if name and name != "HEAD" else None


def aufgabe_zum_lauf(aufgabe_id=None, beschreibung=None, ordner=None):
    """(Aufgaben-Nr, woher) – woher: aufgabe | beschreibung | zweig; (None, None), wenn nichts passt."""
    if aufgabe_id:
        return int(aufgabe_id), "aufgabe"
    m = AUFGABE_IM_TEXT.search(beschreibung or "")
    if m:
        return int(m.group(1)), "beschreibung"
    m = AUFGABE_IM_ZWEIG.match(zweig(ordner) or "")
    if m:
        return int(m.group(1)), "zweig"
    return None, None


def lauf_gestartet(con, pid, agent, lid, aufgabe_id=None, beschreibung=None, ordner=None):
    """Nach dem Anmelden eines Laufs (auch eingereiht – der Agent hat damit angefangen). Rückgabe: die Aufgabe, die jetzt
    läuft, sonst None. Wirft nie – ein Lauf scheitert nie an der Planung."""
    try:
        if not an(con, pid):
            return None
        aid, woher = aufgabe_zum_lauf(aufgabe_id, beschreibung, ordner)
        if not aid:
            return None
        a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
        if not a or a["agent"] != agent or a["status"] != "wartet":
            return None
        from . import wartegrund
        if wartegrund.offene(con, aid):
            return None
        kern.aufgabe_status(con, pid, agent, aid, "start")
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="auto_laeuft",
                         bogen_id=a["bogen_id"], aufgabe_id=aid, text=f"L{lid} ({woher})")
        return aid
    except Exception:          # Halt, eins-nach-dem-anderen, Plan-Gate …: dann eben nicht automatisch
        return None


def ausgeliefert(con, pid, version, sha, enthalten):
    """A1738 (1): Nach der Auslieferung von `sha` als `version` gilt jede Aufgabe als fertig, deren grüne Prüfung mit gültigem
    Merge-OK auf ihrem Zweig im ausgelieferten Stand enthalten ist – Beleg = geprüfter Stand. enthalten(sha_pruefung) → bool
    (git merge-base --is-ancestor). Nicht: Aufgaben, die schon fertig/verworfen sind, deren Prüfung überholt ist oder die auf
    den Entwickler warten (z. B. „erst schließen, wenn Marcel am iPad bestätigt“). Versionshinweis: was die Prüfbitte
    (--gruppe/--hinweis) an der Aufgabe hinterlegt hat. Offene Kriterien sperren nicht – sie gehen in die Rückgabe, der Lead
    erfährt sie. Rückgabe [{aufgabe, titel, beleg, kriterien_offen}]; leer, wenn plan_automatik aus ist."""
    from . import betrieb, planung, wartegrund
    if not an(con, pid):
        return []
    aus, gesehen = [], set()
    for p in con.execute("SELECT * FROM pruefung WHERE projekt_id = ? AND ergebnis = 'gruen' AND aufgabe_id IS NOT NULL"
                         " ORDER BY id DESC LIMIT 200", (pid,)).fetchall():
        aid = p["aufgabe_id"]
        if aid in gesehen:
            continue                                     # die jüngste grüne Prüfung je Aufgabe zählt
        gesehen.add(aid)
        a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
        if not a or a["status"] in ("fertig", "verworfen") or not betrieb.merge_ok(con, pid, aid, p["zweig"]):
            continue
        if con.execute("SELECT 1 FROM pruefung WHERE projekt_id = ? AND aufgabe_id = ? AND id > ? AND ergebnis != 'gruen'",
                       (pid, aid, p["id"])).fetchone():
            continue                                     # danach neu zur Prüfung gegeben oder rot: nicht dieser Stand
        if any(w["art"] == "entwickler" for w in wartegrund.offene(con, aid)):
            continue
        if not enthalten(p["sha"]):
            continue
        offen = [k["text"] for k in planung._json(a["kriterien"], []) if not k.get("erfuellt")]
        zusammen = (a["zusammenfassung"] or "").strip() or f"Ausgeliefert in {version} (main {sha[:8]})."
        if offen:
            zusammen += " Offene Kriterien: " + " | ".join(offen[:5])
        try:
            kern.aufgabe_status(con, pid, "AMW", aid, "fertig", beleg=p["sha"][:7], zusammenfassung=zusammen[:1000], automatik=True)
        except kern.AmwFehler as e:                     # eine Aufgabe hält die anderen nicht auf
            aus.append({"aufgabe": aid, "titel": a["titel"], "fehler": str(e)})
            continue
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="auto_fertig",
                         bogen_id=a["bogen_id"], aufgabe_id=aid, text=f"{version} · P{p['id']} {p['zweig']}@{p['sha'][:8]}")
        aus.append({"aufgabe": aid, "titel": a["titel"], "beleg": p["sha"][:7], "kriterien_offen": offen})
    return aus
