"""Sprachprüfung vor der Prüfung (A2004 Punkt 3, TL #31260): nach jeder Prüfbitte stößt die AMW – wie den Stil-Leser (A1973) –
einen losgelösten leichten Lauf der Lauf-Schlange an. Er fährt die vorhandene Sprachprüfung von Prüfung C
(pruefung_c.sprachpruefung: pyright, nur neue Fehler gegen den Start-Commit) auf genau dem SHA der Prüfbitte gegen den merge-base
mit main – in zwei frischen Checkouts in einem eigenen Arbeitsordner, nie im Baum des Bearbeiters. Der Befund geht als Meldung an
den Prüfer und steht an der Prüfbitte (`amw pruefung zeige`). Fällt etwas aus (Start, Lauf-Schlange, Checkout, pyright fehlt), ist
das der Befund „Sprachprüfung nicht gelaufen“ mit Grund – nie still. Projekt-Einstellung sprachpruefung (A1962): auto (nur mit
pyrightconfig.json im Projektordner) | pyright | aus.

Ereignisse (plan_ereignis, ohne Schemaänderung):
  sprache_angestossen {"pruefung", "prozess", "basis", "kennung"}
  sprache_befund      {"pruefung", "stand": "ok" | "neu" | "kein_vergleich" | "nicht_gelaufen", "neu": n, "text", "lauf", "basis", "kennung",
                       "uebernommen": P-Nummer | None}

A2057: die Vergleichsbasis ist der Start-Commit des Pakets – git merge-base <Stand> main ZUM ZEITPUNKT DER PRÜFBITTE, gespeichert in
sprache_angestossen. Rückt main während der Prüfung vor (oder ist der Stand schon gemergt), vergleicht die Prüfung trotzdem mit
dem Start-Commit; ist die Basis der geprüfte Stand selbst, heißt der Befund „kein Vergleich möglich“ statt „keine neuen Fehler“.

A2135: gleicher Stand, gleiche Basis, gleiches pyright, gleiche Einstellung (kennung) wird nur einmal gerechnet. Liegt ein Befund vor, wird er
übernommen (eigener Eintrag, „übernommen von P…“, ohne Lauf); rechnet gerade eine frühere Prüfung daran, wartet die neue auf sie. „nicht
gelaufen“ wird nie übernommen, und ist der Prozess der früheren weg, rechnet die nächste selbst. Der Prüfer bekommt je Kennung eine Meldung.
"""
import json
import os
import subprocess
import sys
import tempfile
import time

from . import db, kern

ANGESTOSSEN, BEFUND = "sprache_angestossen", "sprache_befund"
EINSTIEG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "amw-vorpruefung.py")
OHNE_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)
NICHT_GELAUFEN = "Sprachprüfung nicht gelaufen"
UEBERNEHMBAR = ("ok", "neu", "kein_vergleich")
WARTEN_S = 5                     # so oft sieht eine wartende Prüfung nach
START_FRIST_S = 120              # so lange darf ein Anstoß noch keine Prozessnummer haben
ALT_S = 6 * 3600                 # ein älterer Anstoß ohne Befund hält niemanden mehr auf (Prozessnummern werden neu vergeben)


def einstellung(con, pid):
    return kern.projekt_wahl(con, pid, "sprachpruefung")


def _spawn(pid, prid, umgebung=None):
    befehl = [sys.executable, "-I", "-X", "utf8", EINSTIEG, "--projekt-id", str(pid), "--pruefung", str(prid)]
    flags = (0x00000008 | 0x00000200 | OHNE_FENSTER) if os.name == "nt" else 0        # DETACHED, NEW_GROUP wie der Stil-Leser
    return subprocess.Popen(befehl, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                            creationflags=flags, env=umgebung, start_new_session=os.name != "nt").pid


STARTER = _spawn             # Tests setzen eine Attrappe; tests/abschotten schaltet das Anstoßen ganz ab (AMW_SPRACHE_AUS)


def gilt(con, pid):
    """Soll für dieses Projekt geprüft werden? aus: nie; pyright: immer; auto: nur mit pyrightconfig.json im Projektordner."""
    from . import pruefung_c
    modus = einstellung(con, pid)
    if modus == "aus":
        return False
    ordner = kern.projekt_ordner(con, pid)
    return modus == "pyright" or bool(ordner and pruefung_c.sprache_an(modus, ordner))


def anstossen(con, pid, prid):
    """Nach jeder Prüfbitte. Rückgabe: Zeile für die Prüfbitte oder „“ (abgeschaltet bzw. ohne pyright-Konfiguration)."""
    if os.environ.get("AMW_SPRACHE_AUS") or not gilt(con, pid):
        return ""
    p = con.execute("SELECT * FROM pruefung WHERE id = ? AND projekt_id = ?", (prid, pid)).fetchone()
    if not p:
        return ""
    basis = start_commit(con, pid, p["sha"])         # A2057: jetzt festhalten – main rückt bis zum Lauf vielleicht vor
    k = kennung(con, pid, p["sha"], basis)
    with db.schreiben(con):
        eid = db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=ANGESTOSSEN, aufgabe_id=p["aufgabe_id"],
                           text=json.dumps({"pruefung": prid, "basis": basis, "kennung": k}, ensure_ascii=False))
    v = vorhanden(con, pid, k)
    if v:                                                # A2135: schon gerechnet
        return "\n\n" + zeile(uebernehmen(con, pid, prid, v))
    vor = vor_mir(con, pid, prid, k)
    try:
        prozess = STARTER(pid, prid)
    except OSError as e:
        abschliessen(con, pid, prid, {"stand": "nicht_gelaufen", "text": f"{NICHT_GELAUFEN}: Lauf ließ sich nicht starten ({e})"})
        return f"\n\nSprachprüfung: nicht gelaufen ({e})"
    with db.schreiben(con):
        con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?",
                    (json.dumps({"pruefung": prid, "prozess": prozess, "basis": basis, "kennung": k}, ensure_ascii=False), eid))
    if vor:
        return f"\n\nSprachprüfung: wartet auf die von P{vor} (gleicher Stand) – Befund folgt"
    return "\n\nSprachprüfung: läuft (pyright, nur neue Fehler gegen den Start-Commit) – Befund folgt als Meldung"


def start_commit(con, pid, sha):
    """git merge-base <sha> main im Projektordner (voller SHA) oder None."""
    ordner = kern.projekt_ordner(con, pid)
    if not ordner:
        return None
    try:
        return _git(["-C", ordner, "merge-base", sha, "main"], None) or None
    except (RuntimeError, OSError, subprocess.SubprocessError):
        return None


def _ereignisse(con, pid, art, neueste=True):
    """[(Ereignis-Nummer, Zeit, Inhalt)]."""
    for r in con.execute(f"SELECT id, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id {'DESC' if neueste else ''}", (pid, art)).fetchall():
        try:
            yield r["id"], r["zeit_utc"], json.loads(r["text"] or "{}")
        except ValueError:
            continue


def _angestossen(con, pid, prid):
    """(Ereignis-Nummer, Inhalt) des jüngsten Anstoßes dieser Prüfung – (0, {}) ohne."""
    return next(((i, e) for i, _, e in _ereignisse(con, pid, ANGESTOSSEN) if e.get("pruefung") == prid), (0, {}))


def gemerkte_basis(con, pid, prid):
    """Die bei der Prüfbitte gemerkte Basis (A2057) oder None."""
    return _angestossen(con, pid, prid)[1].get("basis")


# --- A2135: gleicher Stand wird nur einmal gerechnet --------------------------------------------------------------------------

def _pyright_version():
    """Version des installierten pyright aus seiner package.json – None, wenn es sich nicht sagen lässt (dann rechnet jede Prüfung selbst)."""
    from . import pruefung_c
    prog = pruefung_c.pyright_programm()
    if not prog:
        return None
    try:
        with open(os.path.join(os.path.dirname(prog[1]), "package.json"), encoding="utf-8") as f:
            return json.load(f).get("version")
    except (OSError, ValueError, AttributeError):
        return None


def kennung(con, pid, sha, basis):
    """Woran der Befund hängt: Stand, Start-Commit, pyright-Version, Einstellung (die pyright-Konfiguration steckt im Stand) – oder None."""
    version = _pyright_version() if basis and len(sha or "") == 40 else None
    return f"{sha}|{basis}|{version}|{einstellung(con, pid)}" if version else None


def vorhanden(con, pid, k):
    """Der selbst gerechnete Befund zu dieser Kennung – oder None. „nicht gelaufen“ zählt nie."""
    return next((e for _, _, e in _ereignisse(con, pid, BEFUND) if k and e.get("kennung") == k and not e.get("uebernommen")
                 and e.get("stand") in UEBERNEHMBAR), None)


def vor_mir(con, pid, prid, k):
    """P-Nummer einer früher angestoßenen Prüfung mit derselben Kennung, die noch daran ist (Prozess lebt) – oder None."""
    from . import steuerung
    if not k:
        return None
    ich = _angestossen(con, pid, prid)[0]
    fertig = {}
    for i, _, e in _ereignisse(con, pid, BEFUND, neueste=False):
        fertig[e.get("pruefung")] = i
    for i, zeit, e in _ereignisse(con, pid, ANGESTOSSEN, neueste=False):
        if i >= ich or e.get("kennung") != k or fertig.get(e.get("pruefung"), 0) > i or e.get("pruefung") == prid:
            continue
        alter = time.time() - db.utc_sek(zeit)
        if alter < ALT_S and (steuerung.lebt(e["prozess"]) if e.get("prozess") else alter < START_FRIST_S):
            return e["pruefung"]
    return None


def uebernehmen(con, pid, prid, e):
    """Den Befund einer anderen Prüfung für diese eintragen – ohne Lauf. Rückgabe wie pruefen."""
    aus = {"stand": e["stand"], "neu": e.get("neu"), "basis": e.get("basis"), "uebernommen": e["pruefung"],
           "text": f"Übernommen von P{e['pruefung']}: gleicher Stand, gleicher Start-Commit.\n{e.get('text') or ''}".strip()}
    abschliessen(con, pid, prid, aus, e.get("lauf"))
    return aus


def _git(args, umgebung, cwd=None):
    r = subprocess.run(["git", *args], capture_output=True, text=True, env=umgebung, cwd=cwd, stdin=subprocess.DEVNULL,
                       timeout=600, creationflags=OHNE_FENSTER)
    if r.returncode:
        raise RuntimeError(f"git {' '.join(args[:2])}: {(r.stdout + r.stderr).strip()[-300:]}")
    return r.stdout.strip()


def pruefen(con, pid, sha, arbeit, werkzeuge=None, basis=None):
    """Die Sprachprüfung auf `sha` gegen `basis` (A2057: der bei der Prüfbitte gemerkte Start-Commit; ohne ihn der merge-base mit
    main) – in `arbeit` (eigener Ordner). Rückgabe wie abschliessen sie braucht: {"stand", "neu", "text", "basis"}."""
    from . import pruefung_c
    ordner = kern.projekt_ordner(con, pid)
    if not ordner or not os.path.isdir(ordner):
        return {"stand": "nicht_gelaufen", "text": f"{NICHT_GELAUFEN}: kein Projektordner"}
    p = {"nr": 0, "daten": arbeit, "port": 0, "autocrlf": pruefung_c.autocrlf_projekt(ordner)}
    u = pruefung_c._umgebung(p)
    repo = pruefung_c.repo_anlegen(p)                # eigenes Prüf-Repo (bare) – nie das .git des Projekts
    _git(["--git-dir", repo, "fetch", "-q", "--no-tags", ordner, "+refs/heads/*:refs/heads/*"], u)
    try:
        _git(["--git-dir", repo, "cat-file", "-e", f"{sha}^{{commit}}"], u)
    except RuntimeError:
        return {"stand": "nicht_gelaufen", "text": f"{NICHT_GELAUFEN}: {sha[:8]} steht in keinem Zweig des Projekts"}
    if basis:
        try:
            _git(["--git-dir", repo, "cat-file", "-e", f"{basis}^{{commit}}"], u)
        except RuntimeError:
            basis = None
    basis = basis or _git(["--git-dir", repo, "merge-base", sha, "refs/heads/main"], u)
    if basis.startswith(sha) or sha.startswith(basis):   # A2057: Stand = Basis (z. B. schon gemergt) – kein Vergleich, kein „ok“
        return {"stand": "kein_vergleich", "neu": 0, "basis": basis[:8],
                "text": f"Sprachprüfung: kein Vergleich möglich – der Start-Commit ist der geprüfte Stand selbst ({sha[:8]})."}
    q = pruefung_c._frisch(p, sha)
    r = pruefung_c.sprachpruefung(p, q, basis, werkzeuge=werkzeuge)
    if r.get("hinweis"):                             # pyright fehlt auf diesem PC
        return {"stand": "nicht_gelaufen", "text": f"{NICHT_GELAUFEN}: {r['hinweis']}"}
    if r["befund"] == "C/technik":
        return {"stand": "nicht_gelaufen", "text": f"{NICHT_GELAUFEN}: {r.get('grund') or r['ausgabe']}"}
    return {"stand": "neu" if r["neu"] else "ok", "neu": len(r["neu"]), "text": r["ausgabe"], "basis": basis[:8]}


def zeile(aus):
    von = f" (übernommen von P{aus['uebernommen']})" if aus.get("uebernommen") else ""
    if aus.get("stand") == "ok":
        return "Sprachprüfung: keine neuen Fehler" + von
    if aus.get("stand") == "neu":
        return f"Sprachprüfung: {aus.get('neu')} neue Fehler" + von
    if aus.get("stand") == "kein_vergleich":
        return "Sprachprüfung: kein Vergleich möglich (Start-Commit = geprüfter Stand)" + von
    return (aus.get("text") or NICHT_GELAUFEN).split("\n")[0][:160]


def abschliessen(con, pid, prid, aus, lauf=None):
    """Befund eintragen und dem Prüfer melden – auch „nicht gelaufen“ (dann prüft der Prüfer selbst). Ein übernommener Befund geht nur an
    einen Prüfer, der zu dieser Kennung noch keine Meldung hat (A2135)."""
    p = con.execute("SELECT * FROM pruefung WHERE id = ? AND projekt_id = ?", (prid, pid)).fetchone()
    k = _angestossen(con, pid, prid)[1].get("kennung")
    kennt = {r[0] for _, _, e in _ereignisse(con, pid, BEFUND) if k and e.get("kennung") == k and e.get("stand") in UEBERNEHMBAR
             for r in con.execute("SELECT pruefer FROM pruefung WHERE id = ?", (e.get("pruefung"),))} if aus.get("uebernommen") else set()
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=BEFUND, aufgabe_id=p["aufgabe_id"] if p else None,
                     text=json.dumps({"pruefung": prid, "stand": aus.get("stand"), "neu": aus.get("neu"), "text": (aus.get("text") or "")[:4000],
                                      "lauf": lauf, "basis": aus.get("basis"), "kennung": k, "uebernommen": aus.get("uebernommen")},
                                     ensure_ascii=False))
        if p and p["pruefer"] not in kennt:
            kern._posten(con, pid, "AMW", p["pruefer"], "meldung", f"P{prid} {zeile(aus)}"[:140],
                         (aus.get("text") or NICHT_GELAUFEN) + (f"\n\nStand {p['sha'][:8]} gegen den Start-Commit {aus['basis']}." if aus.get("basis") else ""),
                         aufgabe_id=p["aufgabe_id"])


def letzter_befund(con, pid, prid):
    for (t,) in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id DESC", (pid, BEFUND)):
        try:
            e = json.loads(t or "{}")
        except ValueError:
            continue
        if e.get("pruefung") == prid:
            return e
    return None


def ausfuehren(con, pid, prid, werkzeuge=None):
    """Im losgelösten Prozess: als leichter Lauf anmelden, warten bis er dran ist, prüfen, Befund eintragen. A2135: rechnet schon eine
    frühere Prüfung an demselben Stand, erst auf sie warten und ihren Befund übernehmen."""
    from . import belegung, betrieb
    p = con.execute("SELECT * FROM pruefung WHERE id = ? AND projekt_id = ?", (prid, pid)).fetchone()
    k = _angestossen(con, pid, prid)[1].get("kennung")
    while p and k:
        v = vorhanden(con, pid, k)
        if v:
            return uebernehmen(con, pid, prid, v)
        if not vor_mir(con, pid, prid, k):
            break
        time.sleep(WARTEN_S)
    agent = kern.lead(con, pid) or kern.ENTWICKLER
    aus, lid = None, None
    try:
        lid = betrieb.lauf_start(con, pid, agent, f"Sprachprüfung P{prid} (pyright, A2004, automatisch)", None, False, False,
                                 p["aufgabe_id"] if p else None, warten=True, waechter=os.getpid(), befehl=None, ordner=None, selbst=True)
        belegung.lauf_merken(lid, os.getpid())
        while True:
            l = betrieb.lauf_zeile(con, pid, lid)
            if l["status"] == "laeuft":
                break
            if l["status"] in ("fertig", "abgebrochen"):
                raise RuntimeError(f"L{lid} ist {l['status']} – in der Lauf-Schlange nicht drangekommen")
            time.sleep(5)
        betrieb.lauf_uebernehmen(con, lid, "agent")
        if not p:
            raise kern.AmwFehler(f"P{prid} gibt es nicht")
        with tempfile.TemporaryDirectory(prefix="amw-vorpruefung-", ignore_cleanup_errors=True) as arbeit:
            aus = pruefen(con, pid, p["sha"], arbeit, werkzeuge=werkzeuge, basis=gemerkte_basis(con, pid, prid))
    except Exception as e:                                    # noqa: BLE001 – niemand sieht die Ausgabe: als Befund eintragen
        aus = {"stand": "nicht_gelaufen", "text": f"{NICHT_GELAUFEN}: {type(e).__name__}: {e}"[:400]}
    finally:
        aus = aus or {"stand": "nicht_gelaufen", "text": f"{NICHT_GELAUFEN}: abgebrochen"}
        if lid:
            try:
                betrieb.lauf_ende(con, pid, agent, lid, 0 if aus["stand"] != "nicht_gelaufen" else 1, f"P{prid} {zeile(aus)}"[:500])
            finally:
                belegung.lauf_vergessen(lid)
    abschliessen(con, pid, prid, aus, lid)
    return aus


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="amw-vorpruefung")
    ap.add_argument("--projekt-id", type=int, required=True)
    ap.add_argument("--pruefung", type=int, required=True)
    x = ap.parse_args(argv)
    con = db.verbinde()
    try:
        ausfuehren(con, x.projekt_id, x.pruefung)
    finally:
        con.close()
