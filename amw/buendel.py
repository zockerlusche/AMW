"""Bündeln automatisch (A1876, Entwurf D1306, Entscheidungen CCamwTL #29279): die AMW setzt freigegebene p-Pakete zu einem
Release-Stand zusammen – ohne Coder.

`amw paket buendeln [A… | --alle]` (Lead oder Mensch):
1. Pakete: Art p im Zustand merge_reihe, für ihren Zweig paket-A<nr> freigegeben (Merge-OK), Reihenfolge Rang, dann Nummer.
   „nach X“ (Abhängigkeit): X ist fertig oder kommt im selben Bündel davor – sonst bleibt das Paket für später.
2. Eigener Arbeitsbaum <platz_wurzel>/buendel (git worktree des Projekt-Repos) – nie der Live-Ordner, nie ein Platz.
   Alle git-Aufrufe in neutraler Umgebung (keine Hooks, keine Konfiguration des Menschen, fester Autor).
3. Je Paket `cherry-pick` seines Commits. Konflikt → abbrechen, Paket nach E8 (wartet_interaktiv) an den Lead; Pakete, die
   „nach“ ihm kommen, bleiben ebenfalls draußen (in merge_reihe).
4. Versions-Commit: Nummer nach KR1 (MINOR, wenn ein Paket die Hinweis-Gruppe „neu“ hat, sonst PATCH), CHANGELOG-Abschnitt aus
   den Hinweisen der Pakete (ohne Hinweis keine Zeile; gar keiner: eine Zeile „Intern“), Nacharbeit (buendel_schritt).
   DIFF-TOR: committet werden nur version_datei, changelog_datei und die Dateien, die buendel_schritt erzeugen darf; ändert der
   Schritt eine andere versionierte Datei → Stopp mit Befund an den Lead. Betreff „X.Y.Z: Bündel (n Pakete)“ ohne A-Nummern.
5. Zweig buendel-X.Y.Z; GRÜN und Merge-OK der Pakete gehen über die patch-id-Übernahme der Kette (A1814) mit.
Gesamtlauf, GRÜN auf der Spitze und Meldung „Bündel X.Y.Z bereit“ folgen im zweiten Schritt (lauf_und_meldung).
"""
import datetime
import fnmatch
import json
import os
import re
import subprocess

from . import db, kern

NAME, EMAIL = "AMW-Bündel", "buendel@amw.invalid"
VERSION = re.compile(r"\b(\d+)\.(\d+)\.(\d+)\b")
GRUPPEN = (("neu", "Neu"), ("verbessert", "Verbessert"), ("behoben", "Behoben"))


class BuendelFehler(kern.AmwFehler):
    """Das Bündel hält an – mit Befund (an den Lead)."""


# --- Einstellungen -----------------------------------------------------------------------------------------------------------

def vorgaben_amw():
    """Vorgaben für das Projekt, dessen Ordner der AMW-Ordner selbst ist (D1306 F2)."""
    return {"version_datei": "amw/__init__.py", "changelog_datei": "CHANGELOG.md",
            "buendel_schritt": json.dumps({"befehl": "python -X utf8 amw-cli.py web bauen",
                                           "dateien": ["web/inc/VERSION", "web/hilfe/*.json", "web/inc/seite.html"]}),
            "gesamtlauf_befehl": "python -X utf8 -m unittest discover -s tests"}


def einstellungen(con, pid):
    """Die vier Einstellungen (Projekt, sonst Vorgabe für das AMW-Projekt). Fehlt version_datei, changelog_datei oder
    gesamtlauf_befehl → BuendelFehler mit dem Befehl zum Setzen."""
    from . import einrichtung
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    e = json.loads((r[0] if r else None) or "{}")
    ordner = kern.projekt_ordner(con, pid)
    amw = bool(ordner) and os.path.normcase(os.path.abspath(ordner)) == os.path.normcase(os.path.abspath(einrichtung.WURZEL))
    v = {k: (e.get(k) or (vorgaben_amw()[k] if amw else "")) for k in kern.BUENDEL_EINSTELLUNGEN}
    fehlt = [k for k in ("version_datei", "changelog_datei", "gesamtlauf_befehl") if not v[k]]
    if fehlt:
        raise BuendelFehler(f"Bündeln braucht die Projekt-Einstellungen {', '.join(fehlt)} – z. B. amw projekt einstellen"
                            f" {fehlt[0]}=…")
    schritt = v["buendel_schritt"]
    if schritt.startswith("{"):
        s = json.loads(schritt)
        v["schritt_befehl"], v["schritt_dateien"] = s["befehl"].strip(), [str(x) for x in s.get("dateien") or []]
    else:
        v["schritt_befehl"], v["schritt_dateien"] = schritt.strip(), []
    return v


# --- git in neutraler Umgebung ---------------------------------------------------------------------------------------------

def arbeitsbaum(con, pid):
    """<platz_wurzel>/buendel – der Ort des Bündels (nie der Live-Ordner)."""
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    wurzel = (json.loads((r[0] if r else None) or "{}").get("platz_wurzel") or "").strip()
    if not wurzel:
        raise BuendelFehler("Bündeln braucht den Ordner der Arbeitsplätze (platz_wurzel) – das Bündel liegt in <platz_wurzel>/buendel")
    return os.path.join(wurzel, "buendel")


def _umgebung(daten):
    from . import pruefung_c                             # dieselbe neutrale Umgebung wie Prüfung C, eigener Autor
    return pruefung_c._umgebung({"daten": daten}, {"GIT_AUTHOR_NAME": NAME, "GIT_AUTHOR_EMAIL": EMAIL,
                                                     "GIT_COMMITTER_NAME": NAME, "GIT_COMMITTER_EMAIL": EMAIL})


def _git(ordner, daten, *args, ok=(0,)):
    r = subprocess.run(["git", "-C", ordner, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL, timeout=600, env=_umgebung(daten), creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode not in ok:
        raise BuendelFehler(f"git {' '.join(args[:3])}: {(r.stdout + r.stderr).strip()[-300:]}")
    return r.returncode, (r.stdout or "").strip()


# --- Inhalt des Versions-Commits ----------------------------------------------------------------------------------------------

def naechste_version(alt, neu_dabei):
    m = VERSION.search(alt or "")
    if not m:
        raise BuendelFehler(f"in der Versionsdatei steht keine Nummer MAJOR.MINOR.PATCH ({(alt or '')[:40]!r})")
    a, b, c = (int(x) for x in m.groups())
    return f"{a}.{b + 1}.0" if neu_dabei else f"{a}.{b}.{c + 1}"


def changelog_abschnitt(version, datum, titel, pakete):
    """„## X.Y.Z – TT.MM.JJJJ · Titel“ und je Hinweis eine Zeile „- **Neu:** …“; ohne jeden Hinweis eine Zeile „Intern“."""
    zeilen = [f"## {version} – {datum} · {titel}"]
    for gruppe, wort in GRUPPEN:
        for p in pakete:
            if p["hinweis"] and (p["hinweis_gruppe"] or "verbessert") == gruppe:
                zeilen.append(f"- **{wort}:** {' '.join(p['hinweis'].split())}")
    if len(zeilen) == 1:
        zeilen.append(f"- **Intern:** {len(pakete)} Paket(e) ohne sichtbare Änderung (Tests und Pflege).")
    return "\n".join(zeilen) + "\n"


def changelog_einfuegen(text, abschnitt):
    """Vor den ersten Abschnitt „## …“ (der Kopf bleibt oben); ohne Abschnitt ans Ende."""
    m = re.search(r"^## ", text, re.M)
    if not m:
        return text.rstrip("\n") + "\n\n" + abschnitt
    return text[:m.start()] + abschnitt + "\n" + text[m.start():]


# --- Pakete ------------------------------------------------------------------------------------------------------------------

def kandidaten(con, pid, aids=None):
    """Freigegebene p-Pakete in merge_reihe, Rang dann Nummer: [{id, titel, hinweis, hinweis_gruppe, zweig}]."""
    from . import arbeitspaket, betrieb, mergeliste
    aus = []
    for a in con.execute("SELECT id, titel, hinweis, hinweis_gruppe FROM aufgabe WHERE projekt_id = ? AND status NOT IN ('fertig', 'verworfen')"
                         " ORDER BY coalesce(rang, 999999), id", (pid,)).fetchall():
        if aids is not None and a["id"] not in aids:
            continue
        f = arbeitspaket.lesen(con, a["id"])
        z = mergeliste.zweig(a["id"])
        if f.get("art") == "p" and f.get("zustand") == "merge_reihe" and betrieb.merge_ok(con, pid, a["id"], z):
            aus.append({**dict(a), "zweig": z})
    return aus


def _vor(con, aid):
    """Aufgaben, nach denen aid kommt („nach X“: abhaengigkeit.vor → nach)."""
    return [r[0] for r in con.execute("SELECT vor FROM abhaengigkeit WHERE nach = ? AND vor IS NOT NULL", (aid,))]


def _e8(con, pid, aid, grund):
    """E8 (D1258 §6a.4): nach dem Zusammenführen Konflikt → wartet_interaktiv, Befund an den Lead; kein Resume in Stufe 1."""
    from . import arbeitspaket
    arbeitspaket.zustand_setzen(con, pid, "AMW", aid, "wartet_interaktiv", grund=f"E8 beim Bündeln: {grund}"[:300])
    lead = kern.lead(con, pid)
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="paket_entscheidung", aufgabe_id=aid,
                     text=json.dumps({"zeile": "E8", "code": "buendel/konflikt", "grund": grund[:300]}, ensure_ascii=False))
        if lead:
            kern._posten(con, pid, "AMW", lead, "meldung", f"A{aid}: Konflikt beim Bündeln (E8) – wartet auf dich",
                         f"{grund}\nDas Paket bleibt draußen, der Rest wird gebündelt. Möglich: Paket ändern und nochmal frisch,"
                         " an einen interaktiven Agenten, verwerfen.", aufgabe_id=aid)


# --- Bündeln -----------------------------------------------------------------------------------------------------------------

def buendeln(con, pid, von, aids=None, titel=None):
    """Baut den Bündel-Stand (Schritte 1–5 oben). Rückgabe {version, zweig, sha, drin, raus, ordner}. Ein Paket mit Konflikt
    geht nach E8; was nicht ins Bündel kam, steht mit Grund in raus."""
    from . import auslieferung
    if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler("Bündeln darf der Lead oder der Mensch (Releases gibt der Lead frei)")
    e = einstellungen(con, pid)
    repo = kern.projekt_ordner(con, pid)
    if not repo:
        raise BuendelFehler("Das Projekt hat keinen Ordner (amw projekt ordner …)")
    ziel = arbeitsbaum(con, pid)
    daten = os.path.join(os.path.dirname(ziel), "buendel-daten")
    os.makedirs(daten, exist_ok=True)
    pakete = kandidaten(con, pid, None if aids is None else {int(a) for a in aids})
    if not pakete:
        raise BuendelFehler("Kein freigegebenes Paket in der Merge-Reihe")
    if not os.path.isdir(os.path.join(ziel, ".git")) and not os.path.isfile(os.path.join(ziel, ".git")):
        _git(repo, daten, "worktree", "add", "--detach", ziel, "main")
    _git(ziel, daten, "checkout", "-f", "--detach", "main")       # versionierte Dateien wie main; nichts gelöscht
    drin, raus = [], []
    fertig = {r[0] for r in con.execute("SELECT id FROM aufgabe WHERE projekt_id = ? AND status = 'fertig'", (pid,))}
    for p in pakete:
        offen = [x for x in _vor(con, p["id"]) if x not in fertig and x not in {d["id"] for d in drin}]
        if offen:
            raus.append({**p, "grund": "kommt nach " + ", ".join(f"A{x}" for x in offen) + " (noch nicht gemergt oder nicht im Bündel)"})
            continue
        _, kopf = _git(repo, daten, "rev-parse", "--verify", f"refs/heads/{p['zweig']}^{{commit}}")
        rc, aus = _git(ziel, daten, "cherry-pick", kopf, ok=(0, 1))
        if rc != 0:
            leer = "empty" in aus or "nothing to commit" in aus
            _git(ziel, daten, "cherry-pick", "--skip" if leer else "--abort", ok=(0, 1, 128))
            if leer:
                raus.append({**p, "grund": "ist schon in main enthalten"})
                continue
            _e8(con, pid, p["id"], f"Konflikt mit main bzw. den Paketen davor ({aus[-160:]})")
            raus.append({**p, "grund": "Konflikt (E8)", "e8": True})
            continue
        drin.append({**p, "kopf": kopf})
    if not drin:
        raise BuendelFehler("Kein Paket ließ sich aufsetzen: " + "; ".join(f"A{p['id']} {p['grund']}" for p in raus))
    # Versions-Commit
    vpfad, cpfad = os.path.join(ziel, *e["version_datei"].split("/")), os.path.join(ziel, *e["changelog_datei"].split("/"))
    try:
        with open(vpfad, encoding="utf-8") as f:
            vtext = f.read()
        alt = VERSION.search(vtext).group(0) if VERSION.search(vtext) else ""
    except OSError:
        raise BuendelFehler(f"Versionsdatei {e['version_datei']} fehlt im Projekt") from None
    version = naechste_version(alt, any(p["hinweis"] and p["hinweis_gruppe"] == "neu" for p in drin))
    zweig = f"buendel-{version}"
    if _git(repo, daten, "rev-parse", "--verify", "--quiet", f"refs/heads/{zweig}", ok=(0, 1))[0] == 0:
        raise BuendelFehler(f"Zweig {zweig} gibt es schon – erst ausliefern oder den Lead fragen (nichts überschrieben)")
    with open(vpfad, "w", encoding="utf-8", newline="") as f:
        f.write(vtext.replace(alt, version, 1))
    try:
        with open(cpfad, encoding="utf-8") as f:
            ctext = f.read()
    except OSError:
        ctext = "# Änderungen\n\n"
    titel = (titel or "").strip() or ("Gebündelte Pakete" if len(drin) > 1 else (drin[0]["hinweis"] or "Pflege")[:60].rstrip(" ."))
    with open(cpfad, "w", encoding="utf-8", newline="") as f:
        f.write(changelog_einfuegen(ctext, changelog_abschnitt(version, datetime.date.today().strftime("%d.%m.%Y"), titel, drin)))
    if e["schritt_befehl"]:
        u = {k: v for k, v in os.environ.items() if k not in ("AMW_AGENT", "AMW_PROJEKT") and not k.startswith("CLAUDE")}
        u["AMW_DB"] = os.path.join(daten, "schritt.db")             # nie die Live-Datenbank (Entwicklungsbaum öffnet sonst amw.db)
        if not os.path.exists(u["AMW_DB"]):
            db.anlegen(u["AMW_DB"]).close()
        r = subprocess.run(e["schritt_befehl"], shell=True, cwd=ziel, env=u, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            raise BuendelFehler(f"Nacharbeit „{e['schritt_befehl']}“ endete mit {r.returncode}: {(r.stdout + r.stderr).strip()[-300:]}")
    # DIFF-TOR: nur erlaubte Dateien in den Versions-Commit; jede andere geänderte versionierte Datei hält an
    _, versioniert = _git(ziel, daten, "diff", "--name-only", "HEAD")             # geänderte versionierte Dateien
    _, neu = _git(ziel, daten, "ls-files", "--others", "--exclude-standard")     # neue Dateien (nur erlaubte kommen mit)
    erlaubt = lambda pfad: pfad in (e["version_datei"], e["changelog_datei"]) or any(fnmatch.fnmatch(pfad, m) for m in e["schritt_dateien"])
    geaendert = [x for x in versioniert.splitlines() + neu.splitlines() if x.strip() and erlaubt(x.strip())]
    fremd = [x for x in versioniert.splitlines() if x.strip() and not erlaubt(x.strip())]
    if fremd:
        raise BuendelFehler("Diff-Tor: der Versions-Commit würde auch andere Dateien ändern: " + ", ".join(fremd[:8])
                            + " – nichts committet")
    _git(ziel, daten, "add", "--", *geaendert)
    _git(ziel, daten, "commit", "-q", "-m", f"{version}: Bündel ({len(drin)} Paket{'e' if len(drin) != 1 else ''})")
    _, sha = _git(ziel, daten, "rev-parse", "HEAD")
    _git(repo, daten, "branch", zweig, sha)
    uebernommen = auslieferung.Kette(con, pid, von, repo, ausgabe=lambda _: None).uebertragen(sha, zweig)
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="buendel",
                     text=json.dumps({"version": version, "zweig": zweig, "sha": sha, "drin": [p["id"] for p in drin],
                                      "raus": [{"id": p["id"], "grund": p["grund"]} for p in raus]}, ensure_ascii=False))
    return {"version": version, "zweig": zweig, "sha": sha, "drin": drin, "raus": raus, "ordner": ziel, "uebernommen": uebernommen}
