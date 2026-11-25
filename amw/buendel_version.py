"""Version und Versionshinweise eines Bündels (A2121): Nummer, CHANGELOG-Eintrag und Versionshinweis schreibt die AMW selbst.

schreiben(con, pid, pakete, ziel) – pakete: „drin“ aus buendel_zusammensetzen, ziel: der Bündel-Arbeitsbaum (nie der Projektordner):
1. Versionshinweis je Paket nach TH151 (versionshinweise): Satz und Gruppe des Agenten gehen vor; was fehlt, leitet die AMW ab wie beim
   Schließen (Fenster-Paket: Commit-Betreff; p-Paket: Zusammenfassung oder Titel, denn seinen Commit betitelt die AMW selbst) und
   speichert es mit dem Ereignis hinweis_abgeleitet. So nennen CHANGELOG und Versionszeile denselben Satz. „intern“: keine Zeile.
2. Nächste freie Nummer (naechste): MINOR, wenn ein Hinweis „neu“ dabei ist, sonst PATCH – über allem, was schon vergeben ist (main,
   Arbeitsbaum, Tags, eingetragene Versionen), und nicht auf einer Nummer, die jemand reserviert hat (Bündel-Zweig, Stand einer offenen
   oder grünen Prüfung, Abschnitt im CHANGELOG).
3. CHANGELOG im Format des Projekts (changelog_format amw | keepachangelog, A1923); bei release_modus = datei die Nummer in version_datei,
   bei tag keine Versionsdatei.

Geschrieben werden nur diese Dateien im Arbeitsbaum, mit ihren Zeilenenden. Kein Commit, kein Zweig und nie ein Tag – den setzt
`release ausliefern`. Kein Agent, kein Modell.
"""
import datetime
import json
import os
import re

from . import buendel, buendel_zusammensetzen, db, kern, versionshinweise, versionsnummer

ABSCHNITT = re.compile(r"^## \[?v?(\d+\.\d+\.\d+)\b", re.M)          # wie Kette.version_an: „## 1.2.3 – …“ und „## [1.2.3] - …“
ZWEIG = re.compile(r"buendel-(\d+\.\d+\.\d+)")
PRUEFUNGEN_MAX = 60                                                  # wie versionsnummer.pruefen


def _git(repo, *args, ok=(0,)):
    return buendel_zusammensetzen._lauf(repo, None, *args, ok=ok)


# --- Nummer -------------------------------------------------------------------------------------------------------------------

def _stelle(text, datei):
    """(Position, Nummer) der Version in der Versionsdatei, None ohne – dieselbe Stelle, die die Release-Kette liest."""
    m = versionsnummer.VERSION_PY.search(text) if datei == "amw/__init__.py" else None
    if m and buendel.VERSION.fullmatch(m.group(1)):
        return m.start(1), m.group(1)
    m = buendel.VERSION.search(text)
    return (m.start(), m.group(0)) if m else None


def _version_an(repo, e, rev):
    """Version an einem Stand wie die Kette: aus version_datei bzw. (tag) aus dem obersten Abschnitt des CHANGELOG."""
    tag = e["release_modus"] == "tag"
    pfad = e["changelog_datei"] if tag else e["version_datei"]
    rc, text, _ = _git(repo, "show", f"{rev}:{pfad}", ok=None)
    if rc != 0:
        return None
    if tag:
        m = ABSCHNITT.search(text)
        return m.group(1) if m else None
    s = _stelle(text, pfad)
    return s[1] if s else None


def vergeben(con, pid, repo, e):
    """Nummern (als Tripel), die schon vergeben sind: main, Tags, eingetragene Versionen. Darüber liegt die nächste."""
    _git(repo, "rev-parse", "--verify", "refs/heads/main^{commit}")
    _, tags, _ = _git(repo, "tag", "--list")
    alle = [_version_an(repo, e, "refs/heads/main"), buendel.version_aus_tags(tags.splitlines())]
    alle += [r[0] for r in con.execute("SELECT version FROM release WHERE projekt_id = ? AND art = 'version'", (pid,))]
    return {t for t in map(kern.version_teile, alle) if t}


def reserviert(con, pid, repo, e, ohne=()):
    """Nummern, die schon jemand trägt, ohne dass sie ausgeliefert sind: Bündel-Zweige und Stände, deren neueste offene oder grüne Prüfung
    noch nicht in main steckt (ohne: die Pakete dieses Bündels)."""
    _, zweige, _ = _git(repo, "for-each-ref", "--format=%(refname:lstrip=2)", "refs/heads/buendel-*")
    alle = [m.group(1) for m in map(ZWEIG.fullmatch, zweige.splitlines()) if m]
    gesehen = set(ohne)
    for p in con.execute("SELECT p.aufgabe_id, p.sha, a.status FROM pruefung p JOIN aufgabe a ON a.id = p.aufgabe_id WHERE p.projekt_id = ?"
                         " AND p.ergebnis IN ('offen', 'gruen') ORDER BY p.id DESC LIMIT ?", (pid, PRUEFUNGEN_MAX)).fetchall():
        if p["aufgabe_id"] in gesehen:
            continue
        gesehen.add(p["aufgabe_id"])
        if p["status"] in ("fertig", "verworfen") or _git(repo, "merge-base", "--is-ancestor", p["sha"], "refs/heads/main", ok=None)[0] == 0:
            continue
        alle.append(_version_an(repo, e, p["sha"]))
    return {t for t in map(kern.version_teile, alle) if t}


def _tripel(nummer):
    t = kern.version_teile(nummer)
    if t is None:
        raise buendel.BuendelFehler(f"{nummer!r} ist keine Nummer MAJOR.MINOR.PATCH")
    return t


def freie_nummer(basis, belegt, neu_dabei):
    """Die nächste Nummer über basis (Tripel), die nicht in belegt ist – MINOR bei neu_dabei, sonst PATCH."""
    nummer = ".".join(map(str, basis))
    while True:
        nummer = buendel.naechste_version(nummer, neu_dabei)
        if _tripel(nummer) not in belegt:
            return nummer


def naechste(con, pid, neu_dabei, ohne=(), ziel=None):
    """Nächste freie Versionsnummer des Projekts. ziel: Bündel-Arbeitsbaum – seine Versionsdatei und sein CHANGELOG zählen mit."""
    repo, e = _projekt(con, pid)
    basis = vergeben(con, pid, repo, e)
    belegt = reserviert(con, pid, repo, e, ohne)
    if ziel:
        belegt |= {_tripel(x) for x in ABSCHNITT.findall(_lesen(ziel, e["changelog_datei"]) or "")}
        if e["release_modus"] != "tag":
            basis.add(_tripel(_versionsdatei(ziel, e)[2]))
    if not basis:                                                     # nur ohne ziel möglich: die Versionsdatei fehlt auf main
        raise buendel.BuendelFehler(f"Versionsdatei {e['version_datei']} fehlt im Projekt")
    return freie_nummer(max(basis), belegt, neu_dabei)


# --- Versionshinweise (TH151) -------------------------------------------------------------------------------------------------

def _zeile(con, pid, aid):
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a:
        raise buendel.BuendelFehler(f"A{aid} gibt es in diesem Projekt nicht")
    return a


def hinweise_ergaenzen(con, pid, pakete):
    """Fehlenden Satz und/oder Gruppe der Pakete ableiten (TH151) und speichern – was der Agent angab, bleibt. Interne: nichts."""
    for p in pakete:
        a = _zeile(con, pid, p["id"])
        if (a["hinweis"] and a["hinweis_gruppe"]) or versionshinweise.ist_intern(con, a["id"]):
            continue
        z = a["zusammenfassung"]
        if z and versionshinweise.AMW_TEXT.match(z):                  # ein Satz der AMW selbst ist kein Hinweis für Nutzer
            z = None
        v = versionshinweise.ableiten(con, pid, a, p.get("kopf") if p.get("art") == "fenster" else None, z)
        if not v:
            continue
        with db.schreiben(con):
            a = _zeile(con, pid, p["id"])                             # in der Sperre: hat der Agent inzwischen selbst etwas angegeben?
            felder = {k: w for k, w in (("hinweis", v["text"]), ("hinweis_gruppe", v["gruppe"])) if not a[k]}
            if not felder or versionshinweise.ist_intern(con, a["id"]):
                continue
            con.execute(f"UPDATE aufgabe SET {', '.join(k + ' = ?' for k in felder)} WHERE id = ?", (*felder.values(), a["id"]))
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=versionshinweise.ABGELEITET,
                         aufgabe_id=a["id"], text=json.dumps({"quelle": v["quelle"], "gruppe": "hinweis_gruppe" in felder,
                                                              "text": "hinweis" in felder}, ensure_ascii=False))


def hinweise(con, pid, pakete):
    """[{id, titel, hinweis, hinweis_gruppe}] in der Reihenfolge des Bündels, hinweis None = keine Zeile (intern, nichts ausgeliefert)."""
    aus = []
    for p in pakete:
        a = _zeile(con, pid, p["id"])
        text = " ".join((a["hinweis"] or "").split()) if not versionshinweise.ist_intern(con, a["id"]) else ""
        aus.append({"id": a["id"], "titel": a["titel"], "hinweis": text or None,
                    "hinweis_gruppe": (a["hinweis_gruppe"] or "verbessert") if text else None})
    return aus


def hinweis_text(liste):
    """Der Versionshinweis für Nutzer: „### Neu / ### Verbessert / ### Behoben“ – leer, wenn kein Paket einen Satz hat."""
    return versionshinweise.als_text({g: [{"id": h["id"], "text": h["hinweis"]} for h in liste if h["hinweis"] and h["hinweis_gruppe"] == g]
                                      for g in versionshinweise.GRUPPEN})


# --- Dateien ------------------------------------------------------------------------------------------------------------------

def _projekt(con, pid):
    """(Projektordner, Einstellungen des Bündels)."""
    repo = kern.projekt_ordner(con, pid)
    if not repo:
        raise buendel.BuendelFehler("Das Projekt hat keinen Ordner (amw projekt ordner …)")
    return repo, buendel.einstellungen(con, pid)


def _roh(ziel, rel):
    """Inhalt mit seinen Zeilenenden; None, wenn es die Datei nicht gibt."""
    try:
        with open(os.path.join(ziel, *rel.split("/")), encoding="utf-8", newline="") as f:
            return f.read()
    except FileNotFoundError:
        return None


def _lesen(ziel, rel):
    roh = _roh(ziel, rel)
    return None if roh is None else roh.replace("\r\n", "\n")


def _versionsdatei(ziel, e):
    """(Inhalt, Position, Nummer) der Versionsdatei im Arbeitsbaum."""
    text = _roh(ziel, e["version_datei"])
    if text is None:
        raise buendel.BuendelFehler(f"Versionsdatei {e['version_datei']} fehlt im Projekt")
    s = _stelle(text, e["version_datei"])
    if not s:
        raise buendel.BuendelFehler(f"in {e['version_datei']} steht keine Nummer MAJOR.MINOR.PATCH")
    ab, nummer = s
    return text, ab, nummer


def _ablegen(ziel, rel, text):
    with open(os.path.join(ziel, *rel.split("/")), "w", encoding="utf-8", newline="") as f:
        f.write(text)


def _changelog(ziel, e, version, heute, titel, liste):
    """Der ganze neue CHANGELOG, mit den Zeilenenden der vorhandenen Datei."""
    kac = e["changelog_format"] == "keepachangelog"
    roh = _roh(ziel, e["changelog_datei"])
    text = ("# Changelog\n\n" if kac else "# Änderungen\n\n") if roh is None else roh.replace("\r\n", "\n")
    neu = (buendel.kac_einfuegen(text, version, heute.isoformat(), liste) if kac
           else buendel.changelog_einfuegen(text, buendel.changelog_abschnitt(version, heute.strftime("%d.%m.%Y"), titel, liste)))
    return neu.replace("\n", "\r\n") if roh and "\r\n" in roh else neu


def schreiben(con, pid, pakete, ziel, titel=None, heute=None):
    """Nummer vergeben, CHANGELOG (und bei release_modus = datei die Versionsdatei) in ziel schreiben. Rückgabe {"version", "titel",
    "dateien": [geschriebene, relativ], "hinweis": Versionshinweis für Nutzer, "pakete": wie hinweise()}."""
    if not pakete:
        raise buendel.BuendelFehler("Kein Paket im Bündel – keine Version")
    repo, e = _projekt(con, pid)
    if os.path.normcase(os.path.realpath(ziel)) == os.path.normcase(os.path.realpath(repo)):
        raise buendel.BuendelFehler("Version und CHANGELOG schreibt die AMW nur im Bündel-Arbeitsbaum, nie im Projektordner")
    tag = e["release_modus"] == "tag"
    datei = None if tag else _versionsdatei(ziel, e)                  # fehlt sie, ist noch nichts gespeichert
    hinweise_ergaenzen(con, pid, pakete)
    liste = hinweise(con, pid, pakete)
    version = naechste(con, pid, any(h["hinweis_gruppe"] == "neu" for h in liste), [h["id"] for h in liste], ziel)
    titel = " ".join((titel or "").split()) or ("Gebündelte Pakete" if len(liste) > 1
                                                else (liste[0]["hinweis"] or "Pflege")[:60].rstrip(" ."))
    neu = {e["changelog_datei"]: _changelog(ziel, e, version, heute or datetime.date.today(), titel, liste)}
    if datei:
        text, ab, alt = datei
        neu[e["version_datei"]] = text[:ab] + version + text[ab + len(alt):]
    for rel, inhalt in neu.items():                                   # erst hier: alles andere ist schon gerechnet
        _ablegen(ziel, rel, inhalt)
    return {"version": version, "titel": titel, "dateien": sorted(neu), "hinweis": hinweis_text(liste), "pakete": liste}
