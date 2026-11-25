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

A1909: core.autocrlf im Bündel ist der Wert, den git im Projekt-Repo selbst sieht (Repo vor System) – derselbe wie beim
Stand-Vergleich (betrieb.pruefstand) und in jedem Entwicklungsbaum. Vorher galt der Systemwert: das Bündel lag mit CRLF vor, die
Nacharbeit schrieb LF mit gleichem Inhalt, und git hielt jede neu geschriebene Datei wegen der Größe für geändert.
`amw paket buendeln --gesamtlauf buendel-X.Y.Z` stößt den Gesamtlauf eines vorhandenen Bündels neu an.

A1923 (TH160 F2, Mehrprojekt 5): release_modus = datei (Vorgabe: Nummer in version_datei) | tag (Nummer aus dem höchsten Tag
vX.Y.Z des Projekt-Repos, kein Versions-Commit an einer Datei – der Bündel-Commit ändert nur den CHANGELOG); changelog_format =
amw (Vorgabe: „## X.Y.Z – TT.MM.JJJJ · Titel“) | keepachangelog („## [Unreleased]“ → „## [X.Y.Z] - JJJJ-MM-TT“ mit Added/Changed/
Fixed, darüber ein neues leeres [Unreleased]). Den Tag setzt das Bündel nie: das bleibt `release ausliefern` (Lead bzw. Mensch).
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
KAC_GRUPPEN = (("neu", "Added"), ("verbessert", "Changed"), ("behoben", "Fixed"))     # Keep a Changelog 1.1.0
UNRELEASED = re.compile(r"^## \[Unreleased\][^\n]*\n", re.M | re.I)


class BuendelFehler(kern.AmwFehler):
    """Das Bündel hält an – mit Befund (an den Lead)."""


# --- Einstellungen -----------------------------------------------------------------------------------------------------------

def vorgaben_amw():
    """Vorgaben für das Projekt, dessen Ordner der AMW-Ordner selbst ist (D1306 F2)."""
    return {"version_datei": "amw/__init__.py", "changelog_datei": "CHANGELOG.md",
            "buendel_schritt": json.dumps({"befehl": "python -X utf8 amw-cli.py web bauen",
                                           "dateien": ["web/inc/VERSION", "web/hilfe/*.json", "web/inc/seite.html"]}),
            "gesamtlauf_befehl": GESAMTLAUF_PARALLEL}


# A1966: die ganze Suite parallel (amw/testlauf.py); der serielle Befehl zählt weiter als Gesamtlauf (freigabereif.ist_gesamtlauf)
GESAMTLAUF_PARALLEL = "python -X utf8 -m amw.testlauf"
GESAMTLAUF_SERIELL = "python -X utf8 -m unittest discover -s tests"


def einstellungen(con, pid):
    """Die vier Einstellungen (Projekt, sonst Vorgabe für das AMW-Projekt). Fehlt version_datei, changelog_datei oder
    gesamtlauf_befehl → BuendelFehler mit dem Befehl zum Setzen."""
    from . import einrichtung
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    e = json.loads((r[0] if r else None) or "{}")
    ordner = kern.projekt_ordner(con, pid)
    amw = bool(ordner) and os.path.normcase(os.path.abspath(ordner)) == os.path.normcase(os.path.abspath(einrichtung.WURZEL))
    v = {k: (e.get(k) or (vorgaben_amw()[k] if amw else "")) for k in kern.BUENDEL_EINSTELLUNGEN}
    v["release_modus"] = kern.projekt_wahl(con, pid, "release_modus")              # A1923
    v["changelog_format"] = kern.projekt_wahl(con, pid, "changelog_format")
    fehlt = [k for k in (("version_datei",) if v["release_modus"] == "datei" else ()) + ("changelog_datei", "gesamtlauf_befehl")
             if not v[k]]
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


def autocrlf(ordner):
    """A1909: core.autocrlf, wie git im Repo von `ordner` selbst ihn sieht (Repo-Einstellung vor System und Benutzer) – derselbe
    Wert wie beim Stand-Vergleich (betrieb.pruefstand ruft git ohne neutrale Umgebung). Ein Worktree teilt die Einstellung
    seines Repos. Seit A1911 dieselbe Ermittlung wie für Arbeiter-Klone und Prüfung C (pruefung_c.autocrlf_projekt)."""
    from . import pruefung_c
    return pruefung_c.autocrlf_projekt(ordner)


def _umgebung(daten, ordner=None):
    from . import pruefung_c                             # dieselbe neutrale Umgebung wie Prüfung C, eigener Autor
    extra = {"GIT_AUTHOR_NAME": NAME, "GIT_AUTHOR_EMAIL": EMAIL, "GIT_COMMITTER_NAME": NAME, "GIT_COMMITTER_EMAIL": EMAIL}
    if ordner:                                           # A1909: Zeilenenden wie im Projekt-Repo, nicht wie der Systemwert
        extra["GIT_CONFIG_VALUE_3"] = autocrlf(ordner)
    u = pruefung_c._umgebung({"daten": daten}, extra)
    if u.get("GIT_CONFIG_KEY_3") != "core.autocrlf":     # die Stelle in pruefung_c._umgebung, die hier ersetzt wird
        raise BuendelFehler("neutrale git-Umgebung: core.autocrlf steht nicht mehr an Stelle 3")
    return u


def _git(ordner, daten, *args, ok=(0,)):
    r = subprocess.run(["git", "-C", ordner, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                       stdin=subprocess.DEVNULL, timeout=600, env=_umgebung(daten, ordner),
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
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


def version_aus_tags(tags):
    """A1923: höchste Nummer unter den Tags vX.Y.Z (auch X.Y.Z) – „0.0.0“, wenn es noch keinen gibt."""
    best = (0, 0, 0)
    for x in tags:
        m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", x.strip())
        if m:
            best = max(best, tuple(int(y) for y in m.groups()))
    return ".".join(str(y) for y in best)


def kac_abschnitt(version, datum, pakete, vorhanden=""):
    """A1923: „## [X.Y.Z] - JJJJ-MM-TT“ mit ### Added/Changed/Fixed aus den Hinweisen; was schon unter [Unreleased] stand
    (vorhanden), bleibt erhalten und kommt in dieselben Gruppen. Ohne jeden Eintrag: ### Changed – Intern."""
    gruppen, reihe, aktuell, frei = {}, [], None, []
    for z in vorhanden.strip("\n").splitlines():
        m = re.match(r"^### (.+?)\s*$", z)
        if m:
            aktuell = m.group(1)
            if aktuell not in gruppen:
                gruppen[aktuell] = []
                reihe.append(aktuell)
        elif z.strip():
            (gruppen[aktuell] if aktuell else frei).append(z)
    for gruppe, wort in KAC_GRUPPEN:
        for p in pakete:
            if p["hinweis"] and (p["hinweis_gruppe"] or "verbessert") == gruppe:
                if wort not in gruppen:
                    gruppen[wort] = []
                    reihe.append(wort)
                gruppen[wort].append(f"- {' '.join(p['hinweis'].split())}")
    if not frei and not any(gruppen.values()):
        gruppen["Changed"], reihe = [f"- Intern: {len(pakete)} Paket(e) ohne sichtbare Änderung (Tests und Pflege)."], ["Changed"]
    teile = [f"## [{version}] - {datum}"] + frei
    for wort in sorted(reihe, key=lambda w: [k for _, k in KAC_GRUPPEN].index(w) if w in [k for _, k in KAC_GRUPPEN] else 9):
        if gruppen[wort]:
            teile += ["", f"### {wort}", *gruppen[wort]]
    return "\n".join(teile) + "\n"


def kac_einfuegen(text, version, datum, pakete):
    """A1923: [Unreleased] wird zu [X.Y.Z] - Datum (mit seinem Inhalt), darüber ein neues leeres [Unreleased]. Ohne
    [Unreleased]: beides vor den ersten Abschnitt „## …“ (sonst ans Ende)."""
    m = UNRELEASED.search(text)
    if m:
        ende = re.search(r"^## ", text[m.end():], re.M)
        bis = m.end() + (ende.start() if ende else len(text) - m.end())
        vorhanden, rest = text[m.end():bis], text[bis:]
        return text[:m.start()] + "## [Unreleased]\n\n" + kac_abschnitt(version, datum, pakete, vorhanden) + ("\n" + rest if rest else "")
    return changelog_einfuegen(text, "## [Unreleased]\n\n" + kac_abschnitt(version, datum, pakete))


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
    for a in con.execute("SELECT id, titel, hinweis, hinweis_gruppe, pruefbefehl FROM aufgabe WHERE projekt_id = ?"
                         " AND status NOT IN ('fertig', 'verworfen') ORDER BY coalesce(rang, 999999), id", (pid,)).fetchall():
        if aids is not None and a["id"] not in aids:
            continue
        f = arbeitspaket.lesen(con, a["id"])
        z = mergeliste.zweig(a["id"])
        if f.get("art") == "p" and f.get("zustand") == "merge_reihe" and betrieb.merge_ok(con, pid, a["id"], z):
            aus.append({**dict(a), "zweig": z, "pakettyp": f.get("pakettyp") or "normal"})
    return aus


ABNAHME = re.compile(r"\btests[/\\.](abnahme_\w+?)(?:\.py)?\b")


def abnahme_dateien(pruefbefehl):
    """A1955 (TH165): die Abnahme-Tests, die ein Abnahme-Befehl nennt (tests/abnahme_x.py oder tests.abnahme_x) → Pfade."""
    return list(dict.fromkeys(f"tests/{m}.py" for m in ABNAHME.findall(pruefbefehl or "")))


def abnahme_umbenennen(ziel, daten, drin):
    """Pakettyp normal: tests/abnahme_<x>.py → tests/test_abnahme_<x>.py im Bündel (git mv), damit der Test ab jetzt in der
    Gesamtsuite läuft – schon im Gesamtlauf des Bündels (Entscheidung CCamwTL #30596). Ziel schon vorhanden: bleibt, wie es
    ist (Hinweis). Rückgabe ([(alt, neu)], [Hinweise])."""
    paare, hinweise = [], []
    for p in drin:
        if p.get("pakettyp", "normal") != "normal":
            continue                                             # test-schreiben/-ergaenzen bringen ihre test_*.py selbst
        for alt in abnahme_dateien(p.get("pruefbefehl")):
            neu = "tests/test_" + alt[len("tests/"):]
            if not os.path.isfile(os.path.join(ziel, *alt.split("/"))):
                hinweise.append(f"A{p['id']}: {alt} gibt es im Bündel nicht – nichts umbenannt")
            elif os.path.exists(os.path.join(ziel, *neu.split("/"))):
                hinweise.append(f"A{p['id']}: {neu} gibt es schon – {alt} bleibt")
            else:
                _git(ziel, daten, "mv", "--", alt, neu)
                paare.append((alt, neu))
    return paare, hinweise


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
                         " an einen Agenten im Fenster, verwerfen.", aufgabe_id=aid)


# --- Bündeln -----------------------------------------------------------------------------------------------------------------

def buendeln(con, pid, von, aids=None, titel=None, starten=None):
    """Baut den Bündel-Stand (Schritte 1–5 oben) und startet den Gesamtlauf im eigenen Prozess (starten=False: nicht; sonst
    starten(pid, zweig) bzw. starter_starten). Rückgabe {version, zweig, sha, drin, raus, ordner, uebernommen, starter}. Ein
    Paket mit Konflikt geht nach E8; was nicht ins Bündel kam, steht mit Grund in raus."""
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
    offen = offenes_buendel(con, pid)                              # P298 (c): ein Arbeitsbaum – nie zwei Bündel zugleich
    if offen:
        raise BuendelFehler(f"Bündel {offen['zweig']} ist noch offen (Gesamtlauf nicht zu Ende) – erst abwarten")
    pakete = kandidaten(con, pid, None if aids is None else {int(a) for a in aids})
    if not pakete:
        raise BuendelFehler("Kein freigegebenes Paket in der Merge-Reihe")
    baum_auf(repo, ziel, daten, "main")                          # versionierte Dateien wie main; nichts gelöscht
    _, liegen = _git(ziel, daten, "ls-files", "--others", "--exclude-standard")   # P298 (b): Reste früherer Läufe kommen nie mit
    liegen = {x.strip() for x in liegen.splitlines() if x.strip()}
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
    cpfad = os.path.join(ziel, *e["changelog_datei"].split("/"))
    neu_dabei = any(p["hinweis"] and p["hinweis_gruppe"] == "neu" for p in drin)
    if e["release_modus"] == "tag":                                # A1923: Nummer aus den Tags, keine Versionsdatei
        _, tags = _git(repo, daten, "tag", "--list")
        version = naechste_version(version_aus_tags(tags.splitlines()), neu_dabei)   # über dem höchsten Tag: nie schon vergeben
    else:
        vpfad = os.path.join(ziel, *e["version_datei"].split("/"))
        try:
            with open(vpfad, encoding="utf-8") as f:
                vtext = f.read()
            alt = VERSION.search(vtext).group(0) if VERSION.search(vtext) else ""
        except OSError:
            raise BuendelFehler(f"Versionsdatei {e['version_datei']} fehlt im Projekt") from None
        version = naechste_version(alt, neu_dabei)
    zweig = f"buendel-{version}"
    if _git(repo, daten, "rev-parse", "--verify", "--quiet", f"refs/heads/{zweig}", ok=(0, 1))[0] == 0:
        raise BuendelFehler(f"Zweig {zweig} gibt es schon – erst ausliefern oder den Lead fragen (nichts überschrieben)")
    if e["release_modus"] != "tag":
        with open(vpfad, "w", encoding="utf-8", newline="") as f:
            f.write(vtext.replace(alt, version, 1))
    kac = e["changelog_format"] == "keepachangelog"
    try:
        with open(cpfad, encoding="utf-8") as f:
            ctext = f.read()
    except OSError:
        ctext = "# Changelog\n\n" if kac else "# Änderungen\n\n"
    titel = (titel or "").strip() or ("Gebündelte Pakete" if len(drin) > 1 else (drin[0]["hinweis"] or "Pflege")[:60].rstrip(" ."))
    heute = datetime.date.today()
    with open(cpfad, "w", encoding="utf-8", newline="") as f:
        f.write(kac_einfuegen(ctext, version, heute.isoformat(), drin) if kac
                else changelog_einfuegen(ctext, changelog_abschnitt(version, heute.strftime("%d.%m.%Y"), titel, drin)))
    if e["schritt_befehl"]:
        u = {k: v for k, v in os.environ.items() if k not in ("AMW_AGENT", "AMW_PROJEKT") and not k.startswith("CLAUDE")}
        u["AMW_DB"] = os.path.join(daten, "schritt.db")             # nie die Live-Datenbank (Entwicklungsbaum öffnet sonst amw.db)
        if not os.path.exists(u["AMW_DB"]):
            db.anlegen(u["AMW_DB"]).close()
        r = subprocess.run(e["schritt_befehl"], shell=True, cwd=ziel, env=u, capture_output=True, text=True, encoding="utf-8",
                           errors="replace", stdin=subprocess.DEVNULL, timeout=600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode != 0:
            raise BuendelFehler(f"Nacharbeit „{e['schritt_befehl']}“ endete mit {r.returncode}: {(r.stdout + r.stderr).strip()[-300:]}")
    umbenannt, abnahme_hinweise = abnahme_umbenennen(ziel, daten, drin)   # A1955: Abnahme-Tests → test_*.py (git mv, schon vorgemerkt)
    # DIFF-TOR: nur erlaubte Dateien in den Versions-Commit; jede andere geänderte versionierte Datei hält an
    _, versioniert = _git(ziel, daten, "diff", "--name-only", "HEAD")             # geänderte versionierte Dateien
    _, neu = _git(ziel, daten, "ls-files", "--others", "--exclude-standard")     # neue Dateien (nur erlaubte kommen mit)
    neu = "\n".join(x for x in neu.splitlines() if x.strip() and x.strip() not in liegen)   # nur, was in DIESEM Lauf entstand
    eigene = (e["changelog_datei"],) + ((e["version_datei"],) if e["release_modus"] != "tag" else ())   # A1923: bei tag keine Versionsdatei
    mv = {x for paar in umbenannt for x in paar}                                # genau diese Umbenennungen erlaubt das Tor
    erlaubt = lambda pfad: pfad in eigene or pfad in mv or any(fnmatch.fnmatch(pfad, m) for m in e["schritt_dateien"])
    geaendert = [x for x in versioniert.splitlines() + neu.splitlines() if x.strip() and erlaubt(x.strip()) and x.strip() not in mv]
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
                                      "raus": [{"id": p["id"], "grund": p["grund"]} for p in raus],
                                      "umbenannt": [list(x) for x in umbenannt], "abnahme_hinweise": abnahme_hinweise}, ensure_ascii=False))
    gestartet = (starten or starter_starten)(pid, zweig) if starten is not False else None
    return {"version": version, "zweig": zweig, "sha": sha, "drin": drin, "raus": raus, "ordner": ziel, "uebernommen": uebernommen,
            "starter": gestartet, "umbenannt": umbenannt, "abnahme_hinweise": abnahme_hinweise}


def baum_auf(repo, ziel, daten, rev):
    """Bündel-Arbeitsbaum auf `rev` (versionierte Dateien wie dort, nichts gelöscht). A1909/A1911: Index leeren und
    `reset --hard` schreibt jede versionierte Datei mit den Zeilenenden des Projekt-Repos neu – auch die, die ein früheres
    Bündel mit anderen Zeilenenden ausgecheckt hat (die ließe `checkout -f` liegen, weil ihr Index-Eintrag passt) –, und
    der Index ist danach frisch. Unversionierte Dateien bleiben liegen."""
    if not os.path.isdir(os.path.join(ziel, ".git")) and not os.path.isfile(os.path.join(ziel, ".git")):
        _git(repo, daten, "worktree", "add", "--detach", ziel, rev)
    _git(ziel, daten, "checkout", "-f", "--detach", rev)
    _git(ziel, daten, "read-tree", "--empty")                     # A1911: statt checkout-index -f -a – das übersprang Dateien,
    _git(ziel, daten, "reset", "-q", "--hard", rev)               # deren Stat passte (je nach Zeitpunkt); so wird jede neu geschrieben


def gesamtlauf_neu(con, pid, von, zweig, starten=None):
    """A1909 (3): den Gesamtlauf eines vorhandenen Bündels neu anstoßen (`amw paket buendeln --gesamtlauf buendel-X.Y.Z`) –
    etwa nach „Arbeitsbaum verschoben“. Der Arbeitsbaum geht sauber auf die Spitze des Bündels; der Vermerk wird neu
    geschrieben (das Bündel gilt wieder als offen, bis sein Gesamtlauf endet). Rückgabe {version, zweig, sha, starter}."""
    if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler("Den Gesamtlauf eines Bündels anstoßen darf der Lead oder der Mensch")
    repo = kern.projekt_ordner(con, pid)
    if not repo:
        raise BuendelFehler("Das Projekt hat keinen Ordner (amw projekt ordner …)")
    v = _vermerk(con, pid, zweig)
    offen = offenes_buendel(con, pid)
    if offen:
        raise BuendelFehler(f"Bündel {offen['zweig']} ist noch offen (Gesamtlauf nicht zu Ende) – erst abwarten")
    ziel = arbeitsbaum(con, pid)
    daten = os.path.join(os.path.dirname(ziel), "buendel-daten")
    os.makedirs(daten, exist_ok=True)
    rc, spitze = _git(repo, daten, "rev-parse", "--verify", "--quiet", f"refs/heads/{zweig}^{{commit}}", ok=(0, 1))
    if rc != 0:
        raise BuendelFehler(f"Zweig {zweig} gibt es nicht mehr")
    if spitze != v["sha"]:
        raise BuendelFehler(f"Zweig {zweig} steht auf {spitze[:8]}, das Bündel war {v['sha'][:8]} – neu bündeln (nichts überschrieben)")
    if _git(repo, daten, "merge-base", "--is-ancestor", v["sha"], "main", ok=(0, 1))[0] == 0:
        raise BuendelFehler(f"Bündel {zweig} ist schon in main – schon ausgeliefert")
    baum_auf(repo, ziel, daten, v["sha"])
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="buendel",
                     text=json.dumps(dict(v, neu_angestossen=True), ensure_ascii=False))
    gestartet = (starten or starter_starten)(pid, zweig) if starten is not False else None
    return {"version": v["version"], "zweig": zweig, "sha": v["sha"], "starter": gestartet}


# --- Gesamtlauf und Meldung (eigener Prozess) ---------------------------------------------------------------------------------

def starter_starten(pid, zweig):
    """Losgelöster Prozess für Gesamtlauf und Meldung – der Befehl des Leads kehrt sofort zurück (ein Gesamtlauf dauert ~30 min,
    der Connector eines Chat-Leads wartet höchstens 2 min). Rückgabe: PID."""
    import sys
    from . import einrichtung
    u = {k: v for k, v in os.environ.items() if k not in ("AMW_AGENT", "AMW_PROJEKT") and not k.startswith("CLAUDE")}
    flags = (0x00000008 | 0x00000200 | getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0   # DETACHED, NEW_GROUP
    proc = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "amw.buendel", str(pid), zweig], cwd=einrichtung.WURZEL,
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                            creationflags=flags, env=u, start_new_session=os.name != "nt")
    return proc.pid


OFFEN_H = 3                                   # so lange gilt ein Bündel ohne Ende als offen (fällt der Prozess weg, sperrt es nicht ewig)


def offenes_buendel(con, pid):
    """P298 (c): das jüngste Bündel, dessen Gesamtlauf noch kein Ende vermerkt hat (höchstens OFFEN_H Stunden alt) – oder None."""
    r = con.execute("SELECT id, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = 'buendel' ORDER BY id DESC LIMIT 1",
                    (pid,)).fetchone()
    if not r:
        return None
    v = json.loads(r["text"])
    grenze = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=OFFEN_H)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ende = con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = 'buendel_ende' AND id > ? AND text LIKE ?",
                       (pid, r["id"], f'%"zweig": "{v["zweig"]}"%')).fetchone()
    return None if ende or r["zeit_utc"] < grenze else v


def _ende(con, pid, zweig, ergebnis):
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="buendel_ende",
                     text=json.dumps({"zweig": zweig, "ergebnis": ergebnis}, ensure_ascii=False))


def _vermerk(con, pid, zweig):
    r = con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = 'buendel' AND text LIKE ? ORDER BY id DESC LIMIT 1",
                    (pid, f'%"zweig": "{zweig}"%')).fetchone()
    if not r:
        raise BuendelFehler(f"kein Bündel {zweig}")
    return json.loads(r[0])


def _melden(con, pid, kurz, text):
    lead = kern.lead(con, pid)
    if lead:
        with db.schreiben(con):
            kern._posten(con, pid, "AMW", lead, "meldung", kurz[:200], text)


def lauf_und_meldung(con, pid, zweig, warte=None, frist_s=7200):
    """Gesamtlauf (gesamtlauf_befehl) über die Lauf-Schlange auf genau der Bündel-Spitze im Bündel-Arbeitsbaum. Grün → GRÜN auf
    die Spitze mit dem Lead als Prüfer (F3b: nur er gibt Merge-OK und Release) und Meldung „Bündel X.Y.Z bereit“ mit dem
    Versions-Diff, dem benutzten Befehl und den fertigen Befehlen (F3c, P298 a). Rot oder Stand verschoben → Meldung, kein GRÜN.
    In jedem Fall danach „buendel_ende“ (gibt den Arbeitsbaum frei, P298 c). Rückgabe: (rc, lauf-nr)."""
    rc, lid = None, None
    try:
        rc, lid = _lauf_und_meldung(con, pid, zweig, warte, frist_s)
        return rc, lid
    finally:
        _ende(con, pid, zweig, {"rc": rc, "lauf": lid})


def gesamtlauf_rechnen(con, pid, ziel, sha, titel, aufgabe, warte=None, frist_s=7200):
    """A2123 (aus _lauf_und_meldung): der Gesamtlauf (gesamtlauf_befehl) über die Lauf-Schlange auf genau `sha` im Bündel-Arbeitsbaum
    `ziel`. Rückgabe (rc, lauf, None) – oder (None, lauf, Grund), wenn er nicht rechnete (vorher beendet, Arbeitsbaum verschoben)."""
    import time
    from . import belegung, betrieb, laufdienst
    warte = warte or time.sleep
    e = einstellungen(con, pid)
    lead = kern.lead(con, pid)
    agent = lead or con.execute("SELECT kennung FROM agent WHERE projekt_id = ? ORDER BY id LIMIT 1", (pid,)).fetchone()[0]
    befehl = [e["gesamtlauf_befehl"]]
    lid = betrieb.lauf_start(con, pid, agent, titel, None, False, False, aufgabe, warten=True, erwartet_min=40, befehl=befehl, ordner=ziel,
                             waechter=os.getpid(), selbst=True)                # A1948: kein Weckruf
    belegung.lauf_merken(lid, os.getpid())
    try:
        while True:
            l = betrieb.lauf_zeile(con, pid, lid)
            if l["status"] == "laeuft":
                break
            if l["status"] in ("fertig", "abgebrochen"):
                return None, lid, f"Gesamtlauf L{lid} ist {l['status']}, bevor er rechnete"
            warte(5)
        if not betrieb.lauf_uebernehmen(con, lid, "agent"):                       # der Dienst rechnet ihn (dieser Prozess galt als tot)
            while betrieb.lauf_zeile(con, pid, lid)["status"] == "laeuft":
                warte(15)
            return betrieb.lauf_zeile(con, pid, lid)["rc"], lid, None
        s = betrieb.pruefstand(befehl, ziel)
        stand = betrieb.stand_text(s)
        l = betrieb.lauf_zeile(con, pid, lid)
        pfad = laufdienst.ergebnis_pfad(l)
        if not s or s[1] != sha or not s[2]:
            betrieb.lauf_ende(con, pid, agent, lid, 1, f"nicht gerechnet: Bündel-Arbeitsbaum steht nicht sauber auf {sha[:8]} ({stand})")
            return None, lid, f"Arbeitsbaum {ziel} steht auf {stand}, erwartet {sha}"
        with open(pfad, "w", encoding="utf-8", errors="replace") as aus:
            aus.write(f"# AMW L{lid} · {agent} · {titel}\n# Befehl: {befehl[0]}\n# Ordner: {ziel}\n# {stand}\n")
            aus.flush()
            try:
                rc = subprocess.run(befehl[0], shell=True, cwd=ziel, env=laufdienst.umgebung(), stdout=aus, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, timeout=frist_s, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode
            except subprocess.TimeoutExpired:
                rc = 124
        betrieb.lauf_ende(con, pid, agent, lid, rc, f"rc {rc} · {stand} · Ausgabe: {pfad}"[:500])
        return rc, lid, None
    finally:
        belegung.lauf_vergessen(lid)


def _lauf_und_meldung(con, pid, zweig, warte, frist_s):
    v = _vermerk(con, pid, zweig)
    e, ziel = einstellungen(con, pid), arbeitsbaum(con, pid)
    befehl = [e["gesamtlauf_befehl"]]
    rc, lid, grund = gesamtlauf_rechnen(con, pid, ziel, v["sha"], f"Gesamtlauf Bündel {v['version']} {zweig}@{v['sha'][:8]}", v["drin"][0],
                                        warte, frist_s)
    if grund and grund.startswith("Gesamtlauf"):
        _melden(con, pid, f"Bündel {v['version']}: {grund} – kein Release",
                "Neu anstoßen: amw paket buendeln … (das Bündel liegt als Zweig " + zweig + ")")
        return None, lid
    if grund:
        _melden(con, pid, f"Bündel {v['version']}: Arbeitsbaum verschoben – kein Gesamtlauf, kein Release",
                f"{grund}. Neu bündeln: amw paket buendeln …")
        return None, lid
    return bereit_melden(con, pid, zweig, v, rc, lid, befehl[0])


def bereit_melden(con, pid, zweig, v, rc, lid, befehl):
    """Nach dem Gesamtlauf: rot → Meldung; grün → GRÜN mit dem Lead als Prüfer und „Bündel X.Y.Z bereit“ (A1876 F3b). Rückgabe (rc, lid)."""
    e, ziel = einstellungen(con, pid), arbeitsbaum(con, pid)
    lead = kern.lead(con, pid)
    agent = lead or con.execute("SELECT kennung FROM agent WHERE projekt_id = ? ORDER BY id LIMIT 1", (pid,)).fetchone()[0]
    befehl = [befehl]
    if rc != 0:
        _melden(con, pid, f"Bündel {v['version']}: Gesamtlauf L{lid} rot (rc {rc}) – kein Release",
                f"Zweig {zweig}@{v['sha'][:8]}. Ausgabe beim Lauf L{lid}. Pakete bleiben in der Merge-Reihe.")
        return rc, lid
    daten = os.path.join(os.path.dirname(ziel), "buendel-daten")
    _, stat = _git(ziel, daten, "show", "--stat", "--format=", v["sha"])
    _, log = _git(ziel, daten, "show", f"{v['sha']}:{e['changelog_datei']}")
    m = re.search(rf"^## \[?{re.escape(v['version'])}\b.*?(?=^## |\Z)", log, re.M | re.S)      # A1923: auch [X.Y.Z]
    jetzt = db.jetzt()
    text_gruen = (f"Bündel {v['version']}: Pakete " + ", ".join(f"A{x}" for x in v["drin"]) + f" (je einzeln geprüft und freigegeben),"
                  f" Versions-Commit nur erlaubte Dateien (Diff-Tor), Gesamtlauf L{lid} grün auf genau {v['sha'][:8]}"
                  f" (Befehl: {befehl[0]})")
    with db.schreiben(con):
        db.einfuegen(con, "pruefung", projekt_id=pid, aufgabe_id=v["drin"][0], zweig=zweig, sha=v["sha"], bauer="AMW", pruefer=lead or agent,
                     punkte=text_gruen, ergebnis="gruen", bemerkung="automatisch von der AMW (A1876) – Release gibt der Lead frei",
                     angefragt_utc=jetzt, ergebnis_utc=jetzt)
    _melden(con, pid, f"Bündel {v['version']} bereit – Release freigeben ({len(v['drin'])} Paket(e), Gesamtlauf L{lid} grün)",
            f"{text_gruen}.\n\nVersions-Commit:\n{stat}\n\n{(m.group(0) if m else '').strip()}\n\n"
            f"Freigeben und ausliefern:\namw freigabe merge {v['drin'][0]} --zweig {zweig}\namw release ausliefern --zweig {zweig} --gesamtlauf L{lid}")
    return rc, lid


def main(argv=None):
    import sys
    argv = sys.argv[1:] if argv is None else argv
    con = db.verbinde()
    try:
        pid, zweig = int(argv[0]), argv[1]
        try:
            lauf_und_meldung(con, pid, zweig)
        except Exception as f:                                                     # nie still: der Lead erfährt es
            _melden(con, pid, f"Bündel {zweig}: Gesamtlauf nicht möglich – {type(f).__name__}", str(f)[:500])
    finally:
        con.close()


if __name__ == "__main__":
    main()
