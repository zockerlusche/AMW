"""Nur Riskantes zum Lead (A2054, TH167 Fassung 4, Lead F5389): eine Einordnung für Fenster- und p-Pakete.

Der Lead prüft ein Paket nur, wenn mindestens eine Regel trifft – sonst nimmt die AMW bei Grün der Prüfung C selbst ab (E7).
Jede Regel liefert ihre Begründung; das Auto-GRÜN nennt „keine Regel getroffen“ und VERSION, damit der Lead jedes nachprüfen kann.

Regeln (REGELN): aussen · server (web/*.php, immer) · schutz (gesperrte Pfade, Prüfstufe „hoch“, Art sicherheit, Geheimnis-Verdacht)
· schema (Schema, Migration, Eingriff in die Live-DB) · g12 (Löschen, Kosten, Außenwirkung – zusätzlich an den Menschen) ·
lead_liest (Paket als „Lead liest“ markiert) · auffaellig (E2/E4/E6/E8 bei diesem Paket) · pruefung (Änderung an der Prüfung
selbst) · claude_p (Module, die claude -p starten) · tests_geschwaecht (Test gelöscht, übersprungen, weniger Tests oder Assertions)
· oberflaeche (sichtbare Änderung: die Stil-Prüfung läuft noch nicht im Autopfad – bis dahin liest der Lead).

Eingabe ist der Diff zwischen Basis und Kopf (aus_git); die Funktion schreibt nichts.
"""
import fnmatch
import json
import re
import subprocess

VERSION = "riskant v1 (24.11.2026)"
REGELN = ("aussen", "server", "schutz", "schema", "g12", "lead_liest", "auffaellig", "pruefung", "claude_p", "tests_geschwaecht",
          "oberflaeche")
LEAD_LIEST = "lead_liest"                                   # plan_ereignis: {"an": true|false} – Lead oder Planer setzt es

PRUEFUNG_SELBST = ("amw/abnahme.py", "amw/testlauf.py", "tests/test_sperrliste.py", "pyrightconfig.json", "amw/pruefung_c.py",
                   "amw/entscheidung.py", "amw/stil.py", "amw/riskant.py", "amw/fensterpruefung.py", "amw/vorpruefung.py",
                   "amw/auslieferung.py", "amw/buendel.py", "amw/dienst.py", "amw/mergeliste.py", "amw/freigabereif.py")
SCHEMA = ("amw/schema.sql", "amw/migration_*.sql", "*migration*", "amw/db.py", "amw/sicherung.py")
AUSSENWIRKUNG = ("amw/veroeffentlichung.py", "amw/abgleich.py", "amw/push*.py", "amw/ntfy*.py", "web/*")
LOESCHEN = re.compile(r"\b(os\.remove|os\.unlink|shutil\.rmtree|os\.rmdir|\.unlink\(|DELETE\s+FROM|DROP\s+TABLE|git\s+branch\s+-D"
                      r"|push\s+--force|--force\b)", re.I)
KOSTEN = re.compile(r"(tagesgrenze|kostenrahmen|kosten_grenze|_usd\b|max_budget)", re.I)
SKIP = re.compile(r"(@unittest\.skip|\.skipTest\(|@skip\b|unittest\.expectedFailure)")
ASSERT = re.compile(r"\bassert\w*\b|\bself\.fail\(")
TESTDEF = re.compile(r"^\s*def test_\w*\(")
SCHEMA_ZEILE = re.compile(r"(ALTER\s+TABLE|CREATE\s+TABLE|PRAGMA\s+user_version)", re.I)


def aus_git(git, basis, kopf):
    """git = ["git", "-C", ordner] oder ["git", "--git-dir=…"]. Rückgabe {"geaendert", "geloescht", "plus": [(pfad, zeile)],
    "minus": [(pfad, zeile)]} zwischen basis und kopf."""
    def lauf(*a):
        r = subprocess.run([*git, "-c", "core.quotepath=off", *a], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL, timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if r.returncode:
            raise RuntimeError(f"git {' '.join(a[:3])}: {(r.stdout + r.stderr).strip()[-300:]}")
        return r.stdout
    zwischen = lambda n: "/__pycache__/" in "/" + n or n.endswith((".pyc", ".pyo"))   # wie pruefung_c.geaendert
    status = [z.split("\t") for z in lauf("diff", "--no-renames", "--name-status", basis, kopf).splitlines()
              if "\t" in z and not zwischen(z.split("\t", 1)[1])]
    plus, minus, pfad = [], [], None
    for z in lauf("diff", "--no-renames", "-U0", basis, kopf).splitlines():
        if z.startswith("--- "):
            alt = z[6:] if z.startswith("--- a/") else None
        elif z.startswith("+++ "):
            pfad = z[6:] if z.startswith("+++ b/") else alt
        elif z.startswith("+") and pfad:
            plus.append((pfad, z[1:]))
        elif z.startswith("-") and pfad:
            minus.append((pfad, z[1:]))
    return {"geaendert": sorted(p for _, p in status), "geloescht": sorted(p for s, p in status if s.startswith("D")),
            "plus": plus, "minus": minus, "lesen": lambda pfad: lauf("show", f"{kopf}:{pfad}")}


def _teile(*paare):
    """„; “-Liste der Texte, deren Bedingung zutrifft."""
    return "; ".join(text for bedingung, text in paare if bedingung)


def _passt(pfad, muster):
    return any(fnmatch.fnmatchcase(pfad.lower(), m.lower()) for m in muster)


def _test(pfad):
    return pfad.lower().startswith("tests/") or "/tests/" in pfad.lower()


def lead_liest(con, aid):
    r = con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = ? ORDER BY id DESC LIMIT 1", (aid, LEAD_LIEST)).fetchone()
    try:
        return bool(r and json.loads(r[0] or "{}").get("an"))
    except ValueError:
        return False


def einordnen(con, pid, aid, d, befund=None, typ=None):
    """[(regel, Begründung)] – leer = nichts Riskantes. d = aus_git(…); befund = Prüfung C bzw. zweig_befund (aussen, geheim)."""
    from . import abnahme, pruefstufe
    g, aus = d["geaendert"], []
    b = befund or {}

    def treffer(regel, grund):
        aus.append((regel, grund))
    if b.get("aussen"):
        treffer("aussen", "nach außen: " + "; ".join(f"{x}: {w}"[:80] for x, w in b["aussen"][:4]))
    server = [p for p in g if _passt(p, ("web/*.php", "web/**/*.php"))]
    if server:
        treffer("server", "Online-Server-Code: " + ", ".join(server[:5]))
    gesperrt = abnahme.gesperrt(g, abnahme.fenster_typ(typ), abnahme.projekt_muster(con, pid))   # „fest“ und Projekt-Muster; Tests nicht
    hoch_stufe, hoch = pruefstufe.einstufen(g, pruefstufe.muster(con, pid))
    art = (con.execute("SELECT art FROM aufgabe WHERE id = ?", (aid,)).fetchone() or [None])[0]
    if gesperrt or hoch_stufe == "hoch" or art == "sicherheit" or b.get("geheim"):
        treffer("schutz", _teile((gesperrt, "gesperrt: " + ", ".join(p for p, _ in gesperrt[:5])),
                                 (hoch_stufe == "hoch", "Prüfstufe hoch: " + ", ".join(hoch[:5])),
                                 (art == "sicherheit", "Art sicherheit"), (b.get("geheim"), "Geheimnis-Verdacht")))
    schema = [p for p in g if _passt(p, SCHEMA)] + sorted({p for p, z in d["plus"] if p.endswith(".py") and SCHEMA_ZEILE.search(z)})
    if schema:
        treffer("schema", "Schema/Migration/Live-DB: " + ", ".join(dict.fromkeys(schema[:5])))
    loeschen = sorted({p for p, z in d["plus"] if not _test(p) and LOESCHEN.search(z)})
    kosten = sorted({p for p, z in d["plus"] if not _test(p) and KOSTEN.search(z)})
    aussen_w = [p for p in g if _passt(p, AUSSENWIRKUNG) and not _passt(p, ("web/*.php",))]
    if loeschen or kosten or aussen_w:
        treffer("g12", _teile((loeschen, "Löschen: " + ", ".join(loeschen[:4])), (kosten, "Kosten: " + ", ".join(kosten[:4])),
                              (aussen_w, "Außenwirkung: " + ", ".join(aussen_w[:4]))))
    if lead_liest(con, aid):
        treffer("lead_liest", "als „Lead liest“ markiert")
    auff = [json.loads(r[0] or "{}").get("zeile") for r in con.execute(
        "SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_entscheidung'", (aid,))]
    auff = sorted({z for z in auff if z in ("E2", "E4", "E6", "E8")})
    if auff:
        treffer("auffaellig", "frühere Entscheidung " + ", ".join(auff))
    selbst = [p for p in g if p in PRUEFUNG_SELBST]
    if selbst:
        treffer("pruefung", "ändert die Prüfung selbst: " + ", ".join(selbst[:5]))
    claude = []
    for p in g:
        if p.endswith(".py") and any(fnmatch.fnmatchcase(p.lower(), m.lower()) and a_ == "fest" for m, a_, _ in abnahme.GESPERRT):
            try:
                text = d["lesen"](p)
            except Exception:                                        # noqa: BLE001 – gelöscht oder nicht lesbar: kein Treffer
                continue
            if re.search(r"[\"']claude", text) and re.search(r"[\"']-p[\"']", text):
                claude.append(p)
    if claude:
        treffer("claude_p", "startet claude -p: " + ", ".join(claude[:5]))
    schwach = [f"gelöscht: {p}" for p in d["geloescht"] if _test(p)]
    tplus = [(p, z) for p, z in d["plus"] if _test(p)]
    tminus = [(p, z) for p, z in d["minus"] if _test(p)]
    if any(SKIP.search(z) for _, z in tplus):
        schwach.append("neu übersprungen (skip)")
    if sum(bool(TESTDEF.search(z)) for _, z in tminus) > sum(bool(TESTDEF.search(z)) for _, z in tplus):
        schwach.append("weniger Testmethoden")
    if sum(len(ASSERT.findall(z)) for _, z in tminus) > sum(len(ASSERT.findall(z)) for _, z in tplus):
        schwach.append("weniger Assertions")
    if schwach:
        treffer("tests_geschwaecht", "Tests geschwächt: " + "; ".join(schwach[:5]))
    sichtbar = [p for p in g if p.startswith(pruefstufe.SICHTBAR)]
    if sichtbar:
        treffer("oberflaeche", "sichtbare Änderung (Stil-Prüfung noch nicht im Autopfad): " + ", ".join(sichtbar[:4]))
    return aus


def beleg(gruende):
    """Text für Punkte/Bemerkung: die getroffenen Regeln oder „keine Regel getroffen“ – immer mit VERSION."""
    if not gruende:
        return f"Riskant-Einordnung ({VERSION}): keine Regel getroffen"
    return f"Riskant-Einordnung ({VERSION}): " + " · ".join(f"{r}: {g}" for r, g in gruende)
