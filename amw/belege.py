"""A2088: Belege fertiger Pakete prüfen – ohne Modell, nur lesend. Dazu der Code des geprüften Stands für den Prüfer zum Abschluss.

Der Beleg ist Freitext (z. B. „8a31992, Gesamtlauf L3506“ oder „Ja von CCamwTL“). Bei der Fertig-Quelle commit (auch wenn keine
gespeichert ist) muss mindestens ein Hex-Teil oder Versions-Tag (v1.71.0) daraus ein Commit sein, der auf dem ausgelieferten Zweig liegt (main, sonst master):
- ok            – gefunden
- nicht_pruefbar – ein genannter Commit ist nirgends im Repo, oder es gibt gar keinen erkennbaren Beleg
- vorbehalt     – der Commit ist im Repo, liegt aber nicht auf dem Zweig (dann zeigt der Prüfer am Code, ob der Inhalt da ist); der
                  Beleg ist etwas anderes (Ja, D-, P-, B-, R-, L-Nummer, #Nachricht), als die Fertig-Quelle verlangt; Code nicht prüfbar
- urteil        – Fertig-Quelle „ja“: ein Mensch oder der Lead hat entschieden, hier ist nichts zu prüfen

Alle git-Aufrufe lesen nur: keine Haken, keine Filter, kein Netz, Umgebung ohne GIT_*. Der Code kommt als Blobs (cat-file), nicht als
archive – das wendete Filter und export-subst an (LFS holte Dateien). Pfade und Arten, die nicht zum Lesen gehören, bleiben weg.
"""
import os
import re
import subprocess

FRIST_S = 60
ZWEIGE = ("main", "master")
HEX = re.compile(r"\b[0-9a-f]{7,40}\b")
VERSION = re.compile(r"\bv(\d+\.\d+\.\d+)\b")
ANDERE = re.compile(r"(?i)^\s*(ja\b|nein\b|abgenommen|freigegeben)|\b[DPBRL]\d+\b|#\d+")
DOKUMENT = re.compile(r"\bD(\d+)\b")
MAX_DATEIEN_JE_PAKET = 40
MAX_COMMITS_JE_PAKET = 20
BETREFF = re.compile(r"A(\d+):")         # A2092: so beginnt der Betreff eines Commits zu Aufgabe A<nr>
# Grenzen des Codes für den Prüfer
MAX_DATEIEN, MAX_DATEI, MAX_GESAMT = 2000, 400 * 1024, 20 * 1024 * 1024
WEG_NAMEN = re.compile(r"(?i)(^|/)(\.env[^/]*|\.git[^/]*|\.claude|CLAUDE(\.local)?\.md|\.mcp\.json|id_[a-z0-9]+(\.pub)?|\.npmrc|\.netrc|\.pgpass|credentials[^/]*|secrets?[^/]*)(/|$)")
WEG_ENDUNG = re.compile(r"(?i)\.(pem|key|pfx|p12|cer|crt|der|jks|keystore|kdbx|ppk|gpg|asc)$")
GERAET = re.compile(r"(?i)^(con|prn|aux|nul|com\d|lpt\d)(\.|$)")


class GitFehler(RuntimeError):
    pass


def _umgebung():
    u = {k: v for k, v in os.environ.items() if not k.upper().startswith("GIT_")}
    u.update(GIT_TERMINAL_PROMPT="0", GIT_CONFIG_NOSYSTEM="1", GIT_OPTIONAL_LOCKS="0", GIT_LFS_SKIP_SMUDGE="1", LC_ALL="C",
             GIT_NO_REPLACE_OBJECTS="1",                  # ein ersetztes Objekt zeigte etwas anderes als das ausgelieferte
             GIT_NO_LAZY_FETCH="1")                       # Teil-Klon: nichts aus dem Netz nachholen
    return u


def _git(ordner, *args, eingabe=None, ok=(0,)):
    """Ein lesender git-Aufruf; Rückgabe (rc, stdout als bytes). Jeder andere Rückgabewert ist ein GitFehler."""
    if args[0] not in LESEND:
        raise GitFehler(f"git {args[0]} ist hier nicht erlaubt (nur Lesen)")
    try:
        r = subprocess.run(["git", "--no-optional-locks", "-c", "core.hooksPath=" + os.devnull, "-c", "core.fsmonitor=false", "-C", ordner, *args],
                           input=eingabe or b"", capture_output=True, timeout=FRIST_S, env=_umgebung(),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired) as e:
        raise GitFehler(f"git {args[0]}: {type(e).__name__}") from None
    if r.returncode not in ok:
        raise GitFehler(f"git {args[0]}: rc {r.returncode}")
    return r.returncode, r.stdout


LESEND = ("rev-parse", "rev-list", "cat-file", "diff-tree", "ls-tree")


def stand(ordner):
    """(Zweig, SHA) des ausgelieferten Stands – main, sonst master – oder None (kein Ordner, kein Repo, keiner der Zweige)."""
    if not ordner or not os.path.isdir(ordner):
        return None
    for z in ZWEIGE:
        try:
            rc, aus = _git(ordner, "rev-parse", "--verify", "--quiet", f"refs/heads/{z}^{{commit}}", ok=(0, 1))
        except GitFehler:
            return None
        if rc == 0:
            return z, aus.decode("ascii", "replace").strip()
    return None


def hex_teile(text):
    """Was im Beleg ein Commit sein kann: Hex-Teile und Versions-Tags (v1.71.0 → refs/tags/v1.71.0)."""
    t = (text or "").lower()
    return list(dict.fromkeys(HEX.findall(t) + [f"refs/tags/v{x}" for x in VERSION.findall(t)]))


def commits(ordner, kopf, teile):
    """Je Teil, was er ist – ("drauf", sha): Commit auf kopf, ("daneben", sha): Commit im Repo, aber nicht auf kopf, ("fremd", None):
    kein Commit. Zwei git-Aufrufe für alle Teile zusammen (#32747)."""
    teile = list(dict.fromkeys(teile))
    if not teile:
        return {}
    _, aus = _git(ordner, "cat-file", "--batch-check=%(objectname) %(objecttype)", eingabe="".join(f"{t}^{{commit}}\n" for t in teile).encode())
    _, alle = _git(ordner, "rev-list", kopf)
    auf = set(alle.decode("ascii", "replace").split())
    erg = {}
    for t, zeile in zip(teile, aus.decode("utf-8", "replace").splitlines(), strict=True):
        x = zeile.split()
        erg[t] = ("fremd", None) if len(x) != 2 or x[1] != "commit" else ("drauf" if x[0] in auf else "daneben", x[0])
    return erg


def dateien_der(ordner, shas):
    """Je Commit die geänderten Dateien (gegen den ersten Vorfahren): {sha: ([höchstens MAX_DATEIEN_JE_PAKET], gab es mehr?)}."""
    shas = list(dict.fromkeys(shas))
    if not shas:
        return {}
    eingabe = "".join(f"{x}\n" for x in shas).encode()
    _, eltern = _git(ordner, "rev-list", "--no-walk=unsorted", "--parents", "--stdin", eingabe=eingabe)
    paare = [" ".join(z.split()[:2]) for z in eltern.decode("ascii", "replace").splitlines()]          # „Commit erster-Vorfahr“
    _, aus = _git(ordner, "diff-tree", "--stdin", "--root", "--name-only", "-r", "--no-ext-diff", "--no-textconv", "-z",
                  eingabe="".join(f"{x}\n" for x in paare).encode())
    je, offen, jetzt = {x: [] for x in shas}, set(shas), None
    for x in aus.decode("utf-8", "replace").replace("\n", "\0").split("\0"):
        if x in offen:                                    # die Kopfzeile des Commits; jeder kommt einmal
            jetzt = x
            offen.discard(x)
        elif x and jetzt:
            je[jetzt].append(x)
    return {k: (list(dict.fromkeys(v))[:MAX_DATEIEN_JE_PAKET], len(set(v)) > MAX_DATEIEN_JE_PAKET) for k, v in je.items()}


def commits_zu(ordner, kopf, aids):
    """A2092: {Aufgabe: [sha, neueste zuerst]} – Commits auf kopf, deren Betreff mit „A<nr>:“ genau dieser Aufgabe beginnt. Nur für die
    Dateiliste (der Beleg nennt oft den Versions-Commit); die Beleg-Prüfung selbst bleibt am Beleg."""
    aids, aus = set(aids), {}
    if not aids:
        return aus
    _, zeilen = _git(ordner, "rev-list", "--format=%H%x00%s", kopf)
    for z in zeilen.decode("utf-8", "replace").splitlines():
        sha, trenner, betreff = z.partition("\0")         # ohne Trenner: die Kopfzeile „commit <sha>“
        m = BETREFF.match(betreff) if trenner else None
        if m and int(m[1]) in aids and len(aus.setdefault(int(m[1]), [])) < MAX_COMMITS_JE_PAKET:
            aus[int(m[1])].append(sha)
    return aus


def paket(con, pid, a, st, gefunden):
    """Der Befund zu einem fertigen Paket: {"paket", "titel", "quelle", "befund", "grund", "sha", "dateien", "mehr", "themen"}.
    gefunden: commits() zu allen Belegen, oder None – git antwortete nicht."""
    from . import fertigquelle, themen
    q = fertigquelle.lesen(con, a["id"]) or {"art": "commit"}
    aus = {"paket": a["id"], "titel": a["titel"], "quelle": q["art"], "befund": "ok", "grund": None, "sha": None, "dateien": [], "mehr": False,
           "themen": themen.verweise(con, pid, a["id"])}
    text = a["beleg"] or ""
    if q["art"] == "ja":
        d = DOKUMENT.search(text)
        if d and not con.execute("SELECT 1 FROM dokument WHERE id = ? AND projekt_id = ?", (int(d.group(1)), pid)).fetchone():
            return {**aus, "befund": "vorbehalt", "grund": "dokument_fehlt"}
        return {**aus, "befund": "urteil"}
    if q["art"] == "thema":
        s = themen.status(con, themen.finden(con, pid, q["thema"]))
        return aus if s["status"] == "frei" else {**aus, "befund": "vorbehalt", "grund": "thema_offen"}
    if q["art"] == "frist":
        erfuellt = fertigquelle.fertig_wenn(con, pid, a, q)
        return aus if erfuellt else {**aus, "befund": "vorbehalt", "grund": "frist_offen"}
    teile = hex_teile(text)
    if not teile:
        if ANDERE.search(text):
            return {**aus, "befund": "vorbehalt", "grund": "kein_commit"}
        return {**aus, "befund": "nicht_pruefbar", "grund": "kein_beleg"}
    if not st or gefunden is None:
        return {**aus, "befund": "vorbehalt", "grund": "code_ungeprueft"}
    for art, befund, grund in (("drauf", "ok", None), ("daneben", "vorbehalt", "commit_daneben")):
        sha = next((gefunden[t][1] for t in teile if gefunden[t][0] == art), None)
        if sha:
            return {**aus, "befund": befund, "grund": grund, "sha": sha}
    return {**aus, "befund": "nicht_pruefbar", "grund": "commit_fehlt"}


def meilenstein(con, pid, bid):
    """Die Belege aller fertigen Pakete eines Meilensteins: {"zweig", "sha", "pakete": [...]}. Der Ordner ist der des Projekts."""
    from . import kern
    ordner = kern.projekt_ordner(con, pid)
    st = stand(ordner)
    zeilen = con.execute("SELECT * FROM aufgabe WHERE bogen_id = ? AND projekt_id = ? AND status = 'fertig' ORDER BY id", (bid, pid)).fetchall()
    gefunden = None
    if st:
        try:
            gefunden = commits(ordner, st[1], [t for a in zeilen for t in hex_teile(a["beleg"])])
        except (GitFehler, ValueError):
            pass                                          # git ging nicht: „Code nicht geprüft“
    pakete = [paket(con, pid, a, st, gefunden) for a in zeilen]
    eigene, je = {}, {}
    if st:
        try:
            eigene = commits_zu(ordner, st[1], [p["paket"] for p in pakete])
            je = dateien_der(ordner, [s for p in pakete for s in [*eigene.get(p["paket"], []), p["sha"]] if s])
        except GitFehler:
            pass                                          # der Befund steht fest, nur die Dateiliste fehlt
    for p in pakete:                                      # erst die eigenen Commits, dann der Beleg
        p["commits"] = eigene.get(p["paket"], [])
        teile = [je.get(s, ([], False)) for s in dict.fromkeys([*p["commits"], p["sha"]]) if s]
        alle = list(dict.fromkeys(d for t in teile for d in t[0]))
        p["dateien"], p["mehr"] = alle[:MAX_DATEIEN_JE_PAKET], len(alle) > MAX_DATEIEN_JE_PAKET or any(t[1] for t in teile)
    return {"zweig": st[0] if st else None, "sha": st[1] if st else None, "pakete": pakete}


# --- was daraus folgt ------------------------------------------------------------------------------------------------------

TEXT = {"commit_fehlt": ("1 Paket ohne gefundenen Commit", "{n} Pakete ohne gefundenen Commit"),
        "kein_beleg": ("1 Paket ohne Beleg", "{n} Pakete ohne Beleg"),
        "commit_daneben": ("1 Paket: Commit gefunden, liegt aber nicht auf {zweig}", "{n} Pakete: Commit gefunden, liegt aber nicht auf {zweig}"),
        "kein_commit": ("1 Paket: im Beleg steht kein Commit", "{n} Pakete: im Beleg steht kein Commit"),
        "thema_offen": ("1 Paket: sein Thema ist nicht freigegeben", "{n} Pakete: ihr Thema ist nicht freigegeben"),
        "frist_offen": ("1 Paket: die Frist ist nicht erfüllt", "{n} Pakete: die Frist ist nicht erfüllt"),
        "dokument_fehlt": ("1 Paket: das genannte Dokument gibt es nicht", "{n} Pakete: das genannte Dokument gibt es nicht"),
        "code_ungeprueft": ("Code nicht geprüft", "Code nicht geprüft"),
        "kein_gesamttest": ("kein Gesamttest eingestellt – Projekt-Einstellung", "kein Gesamttest eingestellt – Projekt-Einstellung")}


def text(x):
    """Ein Grund bzw. Vorbehalt {"art", "n"} in Worten (Meldungen, Abschlussbericht; die Seite hat dafür pjw_vb_<art>)."""
    if x["art"] == "pruefer":
        return x["text"]
    return TEXT[x["art"]][0 if x.get("n") == 1 else 1].format(n=x.get("n"), zweig=x.get("zweig") or ZWEIGE[0])


def auswerten(bef, themen_, test=None):
    """test: der Gesamttest – mit Code-Stand, aber ohne eingestellten Gesamttest ist das ein Vorbehalt (Lead #32815; ohne Code-Stand
    nur ein Hinweis auf der Karte). Was die Befunde für das Urteil heißen: {"themen": {Thema: [Gründe]}, "ziel": [Gründe], "vorbehalte": [...]} – Gründe {"art",
    "n"}, warum ein Thema bzw. das Ziel nicht prüfbar ist. Ein Paket ohne Thema dieses Meilensteins zählt fürs Ziel."""
    je, vorbehalt = {}, {}
    for p in bef["pakete"]:
        if p["befund"] == "nicht_pruefbar":
            for z in sorted(set(p["themen"]) & set(themen_)) or [None]:
                je.setdefault(z, {}).setdefault(p["grund"], []).append(p["paket"])
        elif p["befund"] == "vorbehalt":
            vorbehalt.setdefault(p["grund"], []).append(p["paket"])
    if not bef["sha"] or bef.get("code") is False:        # kein Repo, kein main/master oder der Code ließ sich nicht holen
        vorbehalt.setdefault("code_ungeprueft", [])
    if bef["sha"] and test is not None and not test.get("befehl"):
        vorbehalt["kein_gesamttest"] = []

    def liste(x):
        return [{"art": g, "n": len(a), "pakete": a, **({"zweig": bef["zweig"]} if g == "commit_daneben" else {})} for g, a in x.items()]
    return {"themen": {k: liste(v) for k, v in je.items() if k is not None}, "ziel": liste(je.get(None) or {}), "vorbehalte": liste(vorbehalt)}


# --- Code für den Prüfer ---------------------------------------------------------------------------------------------------

def _pfad_grund(pfad):
    """Warum dieser Pfad nicht mitkommt – oder None."""
    if pfad.startswith(("/", "\\")) or "\\" in pfad or ":" in pfad or any(t in ("", ".", "..") for t in pfad.split("/")):
        return "Pfad"
    if any(t.endswith((".", " ")) or GERAET.match(t) or any(ord(c) < 32 for c in t) for t in pfad.split("/")):
        return "Pfad"
    if WEG_NAMEN.search(pfad) or WEG_ENDUNG.search(pfad):
        return "Zugangs- oder Steuerdatei"
    return None


def code(ordner, sha, ziel, zuerst=()):
    """Den Code des Stands sha als Dateien unter ziel ablegen – nur gewöhnliche Dateien, Grenzen zuerst mit „zuerst“ (vom Meilenstein
    geändert) gefüllt. Rückgabe {"dateien": n, "bytes": n, "weg": [(Pfad, Grund)]}."""
    _, aus = _git(ordner, "ls-tree", "-r", "-l", "-z", "--full-tree", sha)
    eintraege, weg = [], []
    for z in aus.split(b"\0"):
        if not z:
            continue
        kopf, _, name = z.partition(b"\t")
        modus, art, oid, groesse = kopf.split()
        try:
            pfad = name.decode("utf-8")
        except UnicodeDecodeError:
            weg.append((name.decode("utf-8", "replace"), "Pfad"))
            continue
        if art != b"blob" or modus not in (b"100644", b"100755"):
            weg.append((pfad, "Verweis oder Untermodul"))
            continue
        grund = _pfad_grund(pfad) or ("zu groß" if int(groesse) > MAX_DATEI else None)
        if grund:
            weg.append((pfad, grund))
            continue
        eintraege.append((pfad, oid.decode("ascii"), int(groesse)))
    vorne = set(zuerst)
    eintraege.sort(key=lambda x: (x[0] not in vorne, x[0]))
    wahl, gesamt = [], 0
    for pfad, oid, groesse in eintraege:
        if len(wahl) >= MAX_DATEIEN or gesamt + groesse > MAX_GESAMT:
            weg.append((pfad, "Grenze"))
            continue
        wahl.append((pfad, oid, groesse))
        gesamt += groesse
    n, b = 0, 0
    if wahl:
        _, daten = _git(ordner, "cat-file", "--batch", eingabe="".join(f"{o}\n" for _, o, _ in wahl).encode())
        pos, kleiner = 0, set()
        for pfad, _, _ in wahl:
            ende = daten.index(b"\n", pos)
            kopf = daten[pos:ende].split()
            groesse = int(kopf[2])
            inhalt = daten[ende + 1:ende + 1 + groesse]
            pos = ende + 1 + groesse + 1
            if b"\0" in inhalt[:8192]:
                weg.append((pfad, "Binärdatei"))
                continue
            if pfad.lower() in kleiner:                  # nur die Schreibweise unterscheidet sich – unter Windows dieselbe Datei
                weg.append((pfad, "Pfad"))
                continue
            kleiner.add(pfad.lower())
            z = os.path.join(ziel, *pfad.split("/"))
            os.makedirs(os.path.dirname(z), exist_ok=True)
            with open(z, "wb") as f:
                f.write(inhalt)
            n, b = n + 1, b + len(inhalt)
    return {"dateien": n, "bytes": b, "weg": weg}


def grenze_text(erg):
    """Inhalt von code-grenze.md: was fehlt, ohne Inhalt."""
    z = ["# Grenzen des Codes", "", f"{erg['dateien']} Dateien ({erg['bytes'] // 1024} KB) liegen unter code/. Es fehlen {len(erg['weg'])} Dateien:", ""]
    z += [f"- {p}: {g}" for p, g in erg["weg"][:400]]
    if len(erg["weg"]) > 400:
        z.append(f"- … und {len(erg['weg']) - 400} weitere")
    return "\n".join(z) + "\n"
