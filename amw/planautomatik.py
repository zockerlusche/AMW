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


# --- A1738 (2): gemergte GitHub-PRs ----------------------------------------------------------------------------------------
GH_TAKT_S = 300            # je Projekt höchstens alle 5 Minuten (TL #26380: „höchstens alle paar Minuten“)
GH_FRIST_S = 30
_gh_zuletzt = {}           # Projekt → Zeitpunkt der letzten Abfrage (Zustand im Dienst)
GRUEN = {"SUCCESS", "NEUTRAL", "SKIPPED"}
# Welche Aufgaben ein PR erledigt (TL P186): nur ausdrücklich – A-Nummern am Anfang des Titels („A1234: …“, „[A1234] …“,
# „A1234, A1235: …“) oder im Text hinter einem Schlüsselwort („fertig: A1234“, „closes A1234“). Bloßes Erwähnen
# („Vorarbeit für A1235“, „siehe A1200“) zählt nicht – sonst wäre die falsche Aufgabe fertig.
_A = r"A\d{1,6}(?!\d)"
_LISTE = rf"{_A}(?:\s*(?:,|/|\+|&|und|and)\s*{_A})*"
PR_TITEL = re.compile(rf"^\s*\[?\s*({_LISTE})\s*\]?\s*(?::|–|—|-|\s|$)", re.IGNORECASE)
PR_TEXT = re.compile(rf"(?<![\w-])(?:fertig|erledigt|closes|closed|close|fixes|fixed|fix|resolves|resolved|resolve)\s*:?\s*({_LISTE})",
                     re.IGNORECASE)


def aufgaben_im_pr(titel, text):
    """Die Aufgaben-Nummern, die ein PR ausdrücklich erledigt (Menge)."""
    nummern = set()
    for m in [PR_TITEL.match(titel or "")] + list(PR_TEXT.finditer(text or "")):
        if m:
            nummern |= {int(x) for x in re.findall(r"\d+", m.group(1))}
    return nummern


def _git_remote(ordner, laufen):
    rc, aus = laufen(["git", "-C", ordner, "remote", "get-url", "origin"], ordner)
    return aus.strip() if rc == 0 else None


def _laufen(befehl, ordner):
    try:
        r = subprocess.run(befehl, cwd=ordner, capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=GH_FRIST_S, stdin=subprocess.DEVNULL)
    except (OSError, subprocess.TimeoutExpired) as e:
        return 1, str(e)
    return r.returncode, r.stdout if r.returncode == 0 else (r.stderr or r.stdout)


def ci_gruen(pr):
    """Alle Prüfungen des PRs grün (oder neutral/übersprungen); ohne Prüfungen zählt er als grün (kein CI im Projekt)."""
    for c in pr.get("statusCheckRollup") or []:
        wert = (c.get("conclusion") or c.get("state") or "").upper()
        if wert not in GRUEN:
            return False
    return True


def github_projekt(con, pid, laufen=_laufen, jetzt=None):
    """A1738 (2) für ein Projekt: gemergte PRs (gh im Projektordner) mit „A1234“ in Titel oder Text und grünen Prüfungen setzen
    die Aufgabe dieses Projekts fertig – Beleg = Merge-Commit. Nur mit Projektordner, dessen origin die Betriebsart erlaubt
    (github.com nur in „Cloud“, ein GitHub im Firmennetz auch in „Server“); höchstens alle GH_TAKT_S Sekunden; die Anmeldung
    hält gh selbst (kein Token in der AMW). Rückgabe wie ausgeliefert()."""
    import json
    import time
    from . import betriebsart, planung, wartegrund
    jetzt = jetzt if jetzt is not None else time.time()
    if not an(con, pid) or jetzt - _gh_zuletzt.get(pid, 0) < GH_TAKT_S:
        return []
    ordner = kern.projekt_ordner(con, pid)
    if not ordner:
        return []
    _gh_zuletzt[pid] = jetzt
    url = _git_remote(ordner, laufen)
    if not url or not betriebsart.erlaubt(url):
        return []
    rc, aus = laufen(["gh", "pr", "list", "--state", "merged", "--limit", "30", "--json",
                      "number,title,body,mergeCommit,mergedAt,statusCheckRollup"], ordner)
    if rc != 0:
        return []
    try:
        prs = json.loads(aus or "[]")
    except ValueError:
        return []
    ergebnis = []
    for pr in prs:
        if not ci_gruen(pr):
            continue
        nummern = aufgaben_im_pr(pr.get("title"), pr.get("body"))
        for aid in sorted(nummern):
            a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
            if not a or a["status"] in ("fertig", "verworfen"):
                continue
            if any(w["art"] == "entwickler" for w in wartegrund.offene(con, aid)):
                continue
            beleg = ((pr.get("mergeCommit") or {}).get("oid") or "")[:7] or f"PR #{pr.get('number')}"
            offen = [k["text"] for k in planung._json(a["kriterien"], []) if not k.get("erfuellt")]
            zusammen = (a["zusammenfassung"] or "").strip() or f"PR #{pr.get('number')} gemergt ({(pr.get('mergedAt') or '')[:10]})."
            if offen:
                zusammen += " Offene Kriterien: " + " | ".join(offen[:5])
            try:
                kern.aufgabe_status(con, pid, "AMW", aid, "fertig", beleg=beleg, zusammenfassung=zusammen[:1000], automatik=True)
            except kern.AmwFehler as e:
                ergebnis.append({"aufgabe": aid, "titel": a["titel"], "fehler": str(e)})
                continue
            with db.schreiben(con):
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="auto_fertig",
                             bogen_id=a["bogen_id"], aufgabe_id=aid, text=f"PR #{pr.get('number')} gemergt · {beleg}")
            ergebnis.append({"aufgabe": aid, "titel": a["titel"], "beleg": beleg, "kriterien_offen": offen, "pr": pr.get("number")})
    ok = [x for x in ergebnis if not x.get("fehler")]
    lead = kern.lead(con, pid)
    if ok and lead:
        with db.schreiben(con):
            kern._posten(con, pid, "AMW", lead, "info", "Fertig nach Merge: " + ", ".join(f"A{x['aufgabe']}" for x in ok)[:200],
                         " ".join(f"A{x['aufgabe']} ← PR #{x['pr']} ({x['beleg']})." for x in ok)
                         + "".join(f" A{x['aufgabe']} hat offene Kriterien: {' | '.join(x['kriterien_offen'][:3])}."
                                   for x in ok if x["kriterien_offen"]))
    return ergebnis


def github_runde():
    """Vom Dienst in einem eigenen Faden (gh braucht Netz und kann dauern – die Hauptschleife wartet nicht). Eigene Verbindung."""
    con = db.verbinde()
    try:
        aus = []
        for (pid,) in con.execute("SELECT id FROM projekt").fetchall():
            try:
                aus += github_projekt(con, pid)
            except Exception as x:                       # noqa: BLE001 – ein Projekt hält die anderen nie auf
                aus.append({"aufgabe": 0, "fehler": f"Projekt {pid}: {type(x).__name__}: {x}"})
        return aus
    finally:
        con.close()


# --- A1742: Meilenstein fertig, wenn alle Aufgaben fertig sind ----------------------------------------------------------
VORSCHLAG = "bogen_fertig_vorschlag"      # plan_ereignis.art – einmal je Stand (neue fertige Aufgabe danach → neu)


def meilenstein_projekt(con, pid):
    """Geplante oder aktive Meilensteine mit mindestens einer Aufgabe und keiner offenen: Vorschlag an den Lead (einmal je Stand)
    oder – Projekt-Einstellung meilenstein_fertig = automatisch – selbst abschließen; hält die Versions-Pflicht das auf, wird es
    ein Vorschlag mit Grund. Rückgabe [(Bogen-Nr, „fertig“ | „vorschlag“)]."""
    from . import planung
    if not an(con, pid):
        return []
    auto = kern.projekt_wahl(con, pid, "meilenstein_fertig") == "automatisch"
    lead = kern.lead(con, pid)
    aus = []
    for b in con.execute(
            "SELECT b.* FROM bogen b WHERE b.projekt_id = ? AND b.status IN ('geplant', 'aktiv') AND EXISTS"
            " (SELECT 1 FROM aufgabe a WHERE a.bogen_id = b.id) AND NOT EXISTS (SELECT 1 FROM aufgabe a WHERE a.bogen_id = b.id"
            " AND a.status NOT IN ('fertig', 'verworfen'))", (pid,)).fetchall():
        letzte = con.execute("SELECT max(coalesce(fertig_utc, geaendert_utc, angelegt_utc)) FROM aufgabe WHERE bogen_id = ?",
                             (b["id"],)).fetchone()[0] or ""
        if con.execute("SELECT 1 FROM plan_ereignis WHERE bogen_id = ? AND art = ? AND zeit_utc >= ?",
                       (b["id"], VORSCHLAG, letzte)).fetchone():
            continue                                     # schon vorgeschlagen, seitdem nichts Neues fertig
        n = con.execute("SELECT count(*), sum(status = 'fertig') FROM aufgabe WHERE bogen_id = ?", (b["id"],)).fetchone()
        grund = None
        if auto:
            try:
                planung.bogen_status(con, pid, "AMW", b["id"], "fertig", automatik=True)
                if lead:
                    with db.schreiben(con):
                        kern._posten(con, pid, "AMW", lead, "info", f"Meilenstein {b['id']} „{b['titel'][:80]}“ abgeschlossen – alle Aufgaben fertig",
                                     f"{n[1] or 0} von {n[0]} Aufgaben fertig, der Rest verworfen. Die AMW hat ihn abgeschlossen"
                                     " (Einstellungen › Projekt › Meilenstein fertig: automatisch).")
                aus.append((b["id"], "fertig"))
                continue
            except kern.AmwFehler as e:
                grund = str(e)
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=VORSCHLAG, bogen_id=b["id"],
                         text=f"{n[1] or 0}/{n[0]} fertig" + (f" · {grund[:200]}" if grund else ""))
            if lead:
                kern._posten(con, pid, "AMW", lead, "meldung",
                             f"Meilenstein {b['id']} „{b['titel'][:80]}“: alle Aufgaben fertig – abschließen?",
                             f"{n[1] or 0} von {n[0]} Aufgaben fertig, keine offen. Abschließen: Planung › Meilenstein › „Abschließen“"
                             f" oder amw bogen status {b['id']} fertig."
                             + (f" Automatisch ging es nicht: {grund}" if grund else ""))
        aus.append((b["id"], "vorschlag"))
    return aus


def meilensteine(con):
    """Vom Dienst je Aufsichtsrunde: alle Projekte; ein Projekt hält die anderen nie auf."""
    aus = []
    for (pid,) in con.execute("SELECT id FROM projekt").fetchall():
        try:
            aus += meilenstein_projekt(con, pid)
        except Exception as x:                           # noqa: BLE001
            aus.append((0, f"Projekt {pid}: {type(x).__name__}: {x}"))
    return aus
