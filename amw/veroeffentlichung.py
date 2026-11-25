"""Releases in drei Ebenen (A1928, TH158).

(1) Lokal live: `amw release ausliefern` – Sicherung, main per Fast-Forward, lokaler Tag, Dienst neu, Versionszeile, Aufgaben
fertig, Web-Abzug (AMW online). (3) Veröffentlichung – Push von main und den Tags, ein GitHub-Release – löst die AMW selbst aus,
wenn ein Meilenstein fertig ist und der Mensch ihn abgenommen hat (`amw bogen abnehmen N` bzw. „Abnehmen“ unter „Für dich“):
einmal, gebündelt über alle Versionen seit der letzten Veröffentlichung, die CHANGELOG-Abschnitte zusammen in einem Release.

Projekt-Einstellung veroeffentlichen = meilenstein (Vorgabe) | sofort (wie früher: Push und Release bei jeder Auslieferung).
Ohne Schemaänderung: Ereignisse lokal_live {version, sha}, bogen_abgenommen (bogen_id), veroeffentlicht {version, versionen,
bogen}. Welche Versionen noch nicht veröffentlicht sind, sagt git selbst: lokale Tags v…, die es bei origin noch nicht gibt.
"""
import json
import os
import re
import subprocess
import tempfile

from . import db, kern

LOKAL, ABNAHME, FERTIG = "lokal_live", "bogen_abgenommen", "veroeffentlicht"


def modus(con, pid):
    return kern.projekt_wahl(con, pid, "veroeffentlichen")


def _laufen(befehl, ordner):
    r = subprocess.run(befehl, cwd=ordner, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300,
                       stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, (r.stdout + r.stderr).strip()


def offen(repo, lauf=None):
    """Lokale Versions-Tags (v1.2.3), die es bei origin noch nicht gibt – aufsteigend. None, wenn origin nicht erreichbar ist."""
    lauf = lauf or _laufen
    rc, fern = lauf(["git", "ls-remote", "--tags", "origin"], repo)
    if rc != 0:
        return None
    dort = {z.split("refs/tags/", 1)[1].removesuffix("^{}") for z in fern.splitlines() if "refs/tags/" in z}
    rc, hier = lauf(["git", "tag", "-l", "v*"], repo)
    tags = [t.strip() for t in hier.splitlines() if t.strip() and t.strip() not in dort and kern.version_teile(t.strip()[1:])]
    return sorted(tags, key=lambda t: kern.version_teile(t[1:]))


def notizen(repo, versionen, lauf=None, changelog="CHANGELOG.md"):
    """Titel und Text eines GitHub-Release für mehrere Versionen: die CHANGELOG-Abschnitte (Stand main), neueste zuerst.
    A1933: CHANGELOG des Projekts (changelog_datei), Abschnitte auch als „## [X.Y.Z] - Datum“ (Keep a Changelog)."""
    lauf = lauf or _laufen
    rc, log = lauf(["git", "show", f"main:{changelog}"], repo)
    teile = []
    for v in sorted(versionen, key=kern.version_teile, reverse=True):
        m = re.search(rf"^## \[?{re.escape(v)}\]?(?![\d.]).*?(?=^## |\Z)", log if rc == 0 else "", re.M | re.S)
        teile.append(m.group(0).strip() if m else f"## {v}")
    neu = max(versionen, key=kern.version_teile)
    kopf = (f"Veröffentlicht nach der Abnahme des Meilensteins – enthält {', '.join(sorted(versionen, key=kern.version_teile))}."
            if len(versionen) > 1 else "")
    return neu, ((kopf + "\n\n") if kopf else "") + "\n\n".join(teile) + "\n"


def veroeffentlichen(con, pid, von, bogen_id=None, lauf=None, repo=None):
    """Push von main und allen offenen Tags, ein GitHub-Release für die neueste Version mit allen Abschnitten. Ergebnis an Lead
    und Mensch. Rückgabe: Text. Ein Fehler wird gemeldet (kern.AmwFehler)."""
    lauf = lauf or _laufen
    repo = repo or kern.projekt_ordner(con, pid)
    if not repo:
        raise kern.AmwFehler("Das Projekt hat keinen Ordner (amw projekt ordner …)")

    def melden(kurz, text):
        lead = kern.lead(con, pid)
        an = ",".join(x for x in dict.fromkeys([lead, kern.ENTWICKLER]) if x)
        with db.schreiben(con):
            kern._posten(con, pid, "AMW", an, "meldung", kurz[:200], text)

    tags = offen(repo, lauf)
    if tags is None:
        melden("Veröffentlichung ging nicht – GitHub nicht erreichbar", "git ls-remote origin schlug fehl; die Abnahme bleibt"
               " vermerkt, `amw bogen abnehmen` noch einmal stößt die Veröffentlichung erneut an.")
        raise kern.AmwFehler("origin nicht erreichbar – nichts veröffentlicht")
    rc, aus = lauf(["git", "push", "-q", "origin", "main", *tags], repo)
    if rc != 0:
        melden("Veröffentlichung ging nicht – Push abgewiesen", f"git push: {aus[-300:]}")
        raise kern.AmwFehler(f"Push: {aus[-300:]}")
    if not tags:
        text = "main ist veröffentlicht; keine neue Version seit der letzten Veröffentlichung – kein GitHub-Release"
    else:
        versionen = [t[1:] for t in tags]
        e = json.loads((con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone() or ["{}"])[0] or "{}")
        neu, inhalt = notizen(repo, versionen, lauf, e.get("changelog_datei") or "CHANGELOG.md")
        with tempfile.NamedTemporaryFile("w", suffix=".md", delete=False, encoding="utf-8", newline="") as f:
            f.write(inhalt)
            datei = f.name
        try:
            rc, aus = lauf(["gh", "release", "create", f"v{neu}", "--title", neu, "--notes-file", datei, "--latest"], repo)
        finally:
            os.remove(datei)
        if rc != 0:
            melden(f"Veröffentlichung {neu}: Push gelungen, GitHub-Release nicht", f"gh release: {aus[-300:]} – von Hand nachholen:"
                   f" gh release create v{neu} --title {neu} --notes-file <CHANGELOG-Abschnitte>")
            raise kern.AmwFehler(f"GitHub-Release: {aus[-300:]}")
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=FERTIG, bogen_id=bogen_id,
                         text=json.dumps({"version": neu, "versionen": versionen, "bogen": bogen_id}, ensure_ascii=False))
        text = (f"Veröffentlicht: {neu}" + (f" (mit {', '.join(versionen[:-1])})" if len(versionen) > 1 else "")
                + " – main und Tags gepusht, ein GitHub-Release mit allen Abschnitten")
    from . import meilensteine
    melden(text + (f" ({meilensteine.name(con, bogen_id)} abgenommen)" if bogen_id else ""), text + ".")
    return text


def abgenommen(con, pid, bid):
    return con.execute("SELECT * FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND bogen_id = ? ORDER BY id DESC LIMIT 1",
                       (pid, ABNAHME, bid)).fetchone()


def abnehmen(con, pid, von, bid, lauf=None, repo=None):
    """`amw bogen abnehmen N` / „Abnehmen“ unter „Für dich“: nur der Mensch, nur ein fertiger Meilenstein. Danach veröffentlicht
    die AMW einmal. Schon abgenommen: die Veröffentlichung wird erneut angestoßen (falls sie fehlgeschlagen war). Rückgabe: Text."""
    if von != kern.ENTWICKLER:
        raise kern.AmwFehler("Einen Meilenstein nimmt nur der Mensch ab")
    b = con.execute("SELECT * FROM bogen WHERE id = ? AND projekt_id = ?", (bid, pid)).fetchone()
    if not b:
        from . import meilensteine
        raise kern.AmwFehler(meilensteine.unbekannt(bid))
    if b["status"] != "fertig":
        raise kern.AmwFehler(f"M{b['nr']} ist {b['status']} – abnehmen lässt sich nur ein fertiger Meilenstein")
    if not abgenommen(con, pid, bid):
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ABNAHME, bogen_id=bid,
                         text=f"M{b['nr']} abgenommen")
    return f"M{b['nr']} abgenommen. " + veroeffentlichen(con, pid, von, bid, lauf, repo)


def zur_abnahme(con, pid):
    """Für „Für dich“: fertige Meilensteine ohne Abnahme, die seit der letzten Veröffentlichung fertig wurden – nur mit
    veroeffentlichen = meilenstein und wenn seit der letzten Veröffentlichung etwas lokal live ging. Alte Meilensteine von vor
    A1928 stehen so nicht da."""
    if modus(con, pid) != "meilenstein":
        return []
    letzte = con.execute("SELECT max(zeit_utc) FROM plan_ereignis WHERE projekt_id = ? AND art = ?", (pid, FERTIG)).fetchone()[0]
    erste_lokal = con.execute("SELECT min(zeit_utc) FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND zeit_utc > ?",
                              (pid, LOKAL, letzte or "")).fetchone()[0]
    if not erste_lokal:
        return []
    seit = letzte or erste_lokal
    return [dict(r) for r in con.execute(
        "SELECT b.id, b.nr, b.titel, b.fertig_utc FROM bogen b WHERE b.projekt_id = ? AND b.status = 'fertig' AND b.fertig_utc >= ?"
        " AND NOT EXISTS (SELECT 1 FROM plan_ereignis e WHERE e.projekt_id = b.projekt_id AND e.art = ? AND e.bogen_id = b.id)"
        " ORDER BY b.fertig_utc", (pid, seit, ABNAHME))]
