"""A2116 (Marcel 25.11.): ist alles, was ein Meilenstein fertig hat, auch ausgeliefert? Die EINE Frage dafür – für den Abschluss
(planung.bogen_status), die Lage vor der Abnahme (abschlusslage), Knopf, Meldung und Abschlussbericht.

Gilt nur, wo Versionen Pflicht sind. Je fertiges Paket, verglichen mit der höchsten eingetragenen Version:
- Sein Commit steckt im Commit der Version: ausgeliefert. Welcher Commit: der aus dem Beleg; liegt davon keiner auf dem ausgelieferten
  Zweig (z. B. vor dem Stapeln notiert), die Commits dort, deren Betreff mit „A<nr>:“ beginnt.
- Ein solcher Commit liegt auf dem Zweig, aber nicht in der Version: noch nicht ausgeliefert.
- Ohne eigenen Code (kein Commit im Beleg und Fertig-Quelle Ja, Thema oder Frist, oder der Beleg ist ein Ja oder ein Dokument): braucht
  keine Version.
- Nicht zu entscheiden (kein Repo, keine Commits, git ging nicht): wie bisher nach der Zeit – fertig nach der Version heißt, es fehlt.

Nur lesende git-Aufrufe (belege.py). Ein Ergebnis „alles ausgeliefert“ bleibt gemerkt (ein Commit verlässt die Version nicht), „es fehlt“
gilt MERKEN_S lang (eine neue Version oder ein neuer Beleg zählt sofort) – die Ansichten fragen oft.
"""
import re
import time

from . import kern

MERKEN_S = 300
OHNE_CODE = re.compile(r"(?i)^\s*(ja|nein|abgenommen|freigegeben)\b|\bD\d+\b")
_GEMERKT: dict = {}


def _version(con, pid):
    """(Zeit, Commit) der höchsten eingetragenen Version – wie kern.versions_stand – oder (None, None)."""
    alle = con.execute("SELECT version, zeit_utc, commit_sha FROM release WHERE projekt_id = ? AND art = 'version' ORDER BY id DESC", (pid,)).fetchall()
    r = max(alle, key=lambda x: kern.version_teile(x["version"]) or (-1,), default=None)
    return (r["zeit_utc"], r["commit_sha"]) if r else (None, None)


def _je_paket(ordner, sha, zeilen):
    """{Paket: True (in der Version) | False (auf dem Zweig, nicht in der Version)} – was sich nicht entscheiden lässt, fehlt."""
    from . import belege
    st = belege.stand(ordner)
    if not st or not sha:
        return {}
    kopf = belege.commits(ordner, st[1], [sha.lower()]).get(sha.lower(), ("fremd", None))[1]
    if not kopf:
        return {}                                         # der Commit der Version ist hier nicht bekannt
    teile = {a["id"]: belege.hex_teile(a["beleg"]) for a in zeilen}
    alle = [t for x in teile.values() for t in x]
    in_version = belege.commits(ordner, kopf, alle)
    offen = [t for t in alle if in_version[t][0] == "daneben"]
    auf_zweig = belege.commits(ordner, st[1], offen) if offen else {}
    aus, unklar = {}, []
    for a in zeilen:
        drin = [t for t in teile[a["id"]] if in_version[t][0] == "drauf"]
        spaeter = [t for t in teile[a["id"]] if t in auf_zweig and auf_zweig[t][0] == "drauf"]
        daneben = [t for t in teile[a["id"]] if t in auf_zweig and auf_zweig[t][0] == "daneben"]
        if spaeter:
            aus[a["id"]] = False
        elif drin and not daneben:
            aus[a["id"]] = True
        else:
            unklar.append(a["id"])
    if unklar:
        je = belege.commits_zu(ordner, st[1], unklar)[0]
        lage = belege.commits(ordner, kopf, [s for x in je.values() for s in x]) if je else {}
        for aid, shas in je.items():
            aus[aid] = all(lage[s][0] == "drauf" for s in shas)
    return aus


def ohne_code(con, a):
    """Braucht dieses fertige Paket keine Version, weil es keinen eigenen Code hat?"""
    from . import belege, fertigquelle
    text = a["beleg"] or ""
    if belege.hex_teile(text):
        return False
    q = fertigquelle.lesen(con, a["id"]) or {"art": "commit"}
    return q["art"] in ("ja", "thema", "frist") or bool(OHNE_CODE.search(text))


def fehlt(con, pid, bid):
    """Nummern der fertigen Pakete des Meilensteins, die noch nicht ausgeliefert sind – [] heißt: alles ausgeliefert (oder keine Pflicht)."""
    if kern.projekt_wahl(con, pid, "versionen") != "pflicht":
        return []
    zeilen = con.execute("SELECT id, beleg, fertig_utc FROM aufgabe WHERE bogen_id = ? AND projekt_id = ? AND status = 'fertig' ORDER BY id",
                         (bid, pid)).fetchall()
    if not zeilen:
        return []
    from . import belege, fertigquelle
    zeit, sha = _version(con, pid)
    ordner = kern.projekt_ordner(con, pid)
    schluessel = (ordner, zeit, sha, tuple((a["id"], a["beleg"], a["fertig_utc"], str(fertigquelle.lesen(con, a["id"]))) for a in zeilen))
    alt = _GEMERKT.get(schluessel)
    if alt and (not alt[1] or time.monotonic() - alt[0] < MERKEN_S):
        return list(alt[1])
    try:
        je = _je_paket(ordner, sha, zeilen)
    except (belege.GitFehler, ValueError):
        je = {}                                           # git ging nicht: nach der Zeit
    aus = []
    for a in zeilen:
        if a["id"] in je:
            if not je[a["id"]]:
                aus.append(a["id"])
        elif not ohne_code(con, a) and a["fertig_utc"] and (not zeit or zeit < a["fertig_utc"]):
            aus.append(a["id"])
    if len(_GEMERKT) > 200:
        _GEMERKT.clear()
    _GEMERKT[schluessel] = (time.monotonic(), tuple(aus))
    return aus


def satz(nr, aids):
    """„Meilenstein 19 wartet auf die Auslieferung von A12 und A15.“ – für den Menschen, ohne Befehl; nr: die Nummer im Projekt."""
    return f"Meilenstein {nr} wartet auf die Auslieferung von {liste(aids)}."


def liste(aids, hoechstens=4):
    namen = [f"A{a}" for a in aids[:hoechstens]]
    if len(aids) > hoechstens:
        return ", ".join(namen) + f" und {len(aids) - hoechstens} weiteren Paketen" if len(aids) - hoechstens > 1 else ", ".join(namen) + " und einem weiteren Paket"
    return " und ".join([", ".join(namen[:-1]), namen[-1]]) if len(namen) > 1 else namen[0]
