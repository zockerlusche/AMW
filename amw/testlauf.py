"""Gesamtlauf parallel (A1966, Marcel W2465/W2466): die ganze Suite auf N Prozesse verteilt – Ausgabe wie unittest.

Aufruf (der gesamtlauf_befehl der AMW): `python -X utf8 -m amw.testlauf` im Wurzelordner des Repos.

- Module: alle tests/test_*.py, geladen wie `unittest discover -s tests` (Ordner tests vorn im Suchpfad, Namen test_x).
- Verteilen: nach gemessener Dauer (frühere Läufe, Datei DAUER_DATEI außerhalb des Repos; ohne Messung nach Dateigröße) –
  das längste Modul zuerst an den am wenigsten belasteten Prozess. Browser-Tests (Edge) laufen alle nacheinander in einem
  eigenen Prozess: mehrere Edge gleichzeitig machen sie unter Last wacklig.
- N: Umgebung AMW_TESTPROZESSE (setzt `amw lauf ausfuehren` aus der Projekt-Einstellung gesamtlauf_prozesse), sonst die
  halbe Kernzahl, mindestens 2. N = 1: alles in einem Prozess.
- Isolation: je Prozess ein eigener Temp-Ordner (TMP/TEMP/TMPDIR); AMW_DB, AMW_AGENT, AMW_PROJEKT sind leer – Tests öffnen nie
  die Live-Datenbank (tests.abschotten). Ports wählen die Tests selbst frei (bind auf Port 0).
- Ausgabe: die Fehlerberichte aller Prozesse, dann wie unittest „Ran N tests in X.XXXs“ und „OK (…)“ bzw. „FAILED (…)“ –
  daran erkennen freigabereif, Kette und fertigquelle den Lauf. rc 0 nur, wenn alles grün ist.
- Keine neue Abhängigkeit: nur die Standardbibliothek.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import unittest

TESTS = "tests"
MUSTER = re.compile(r"^test_\w+\.py$")
BROWSER = re.compile(r"test_aktualisieren import|tests\.rundgang|from tests import rundgang|\bmsedge\b|--headless")
DAUER_DATEI = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "AMW", "testdauer.json")
PAKET_WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # dort liegt amw/ – für -m amw.testlauf im Prozess


def module(wurzel="."):
    """Testmodule (Namen wie bei discover -s tests) mit Pfad: [(name, pfad)]."""
    ordner = os.path.join(wurzel, TESTS)
    return [(f[:-3], os.path.join(ordner, f)) for f in sorted(os.listdir(ordner)) if MUSTER.match(f)]


def ist_browser(pfad):
    try:
        with open(pfad, encoding="utf-8", errors="replace") as f:
            return bool(BROWSER.search(f.read()))
    except OSError:
        return False


def dauern_lesen(datei=DAUER_DATEI):
    try:
        with open(datei, encoding="utf-8") as f:
            d = json.load(f)
        return {k: float(v) for k, v in d.items() if isinstance(v, (int, float))}
    except (OSError, ValueError):
        return {}


def dauern_schreiben(neu, datei=DAUER_DATEI):
    d = dauern_lesen(datei)
    d.update({k: round(v, 2) for k, v in neu.items()})
    try:
        os.makedirs(os.path.dirname(datei), exist_ok=True)
        tmp = datei + ".neu"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(d, f, ensure_ascii=False, indent=0, sort_keys=True)
        os.replace(tmp, datei)
    except OSError:
        pass                                              # Messung ist Zusatz – der Lauf zählt trotzdem


def verteilen(mods, n, dauern, browser):
    """[[name, …] je Prozess]: Browser-Module zusammen in Prozess 0 (falls es welche gibt), der Rest nach Dauer (längstes zuerst
    an den leichtesten Prozess). Unbekannte Dauer: Dateigröße / 20 kB je Sekunde als grobe Schätzung."""
    def dauer(name, pfad):
        if name in dauern:
            return dauern[name]
        try:
            return os.path.getsize(pfad) / 20000
        except OSError:
            return 1.0
    b = [(name, dauer(name, p)) for name, p in mods if name in browser]
    rest = sorted(((name, dauer(name, p)) for name, p in mods if name not in browser), key=lambda x: (-x[1], x[0]))
    n = max(1, n)
    if n == 1:
        return [[name for name, _ in b] + [name for name, _ in rest]]
    gruppen = [[name for name, _ in b]] if b else []
    last = [sum(d for _, d in b)] if b else []
    frei = n - len(gruppen)
    gruppen += [[] for _ in range(frei)]
    last += [0.0] * frei
    start = 1 if b else 0
    for name, d in rest:                                  # Browser-Prozess bekommt nur dann mehr, wenn er der leichteste ist
        i = min(range(start, len(gruppen)), key=lambda k: last[k]) if len(gruppen) > start else 0
        if b and last[0] < last[i]:
            i = 0
        gruppen[i].append(name)
        last[i] += d
    return [g for g in gruppen if g]


# --- ein Prozess ---------------------------------------------------------------------------------------------------------------

def arbeiter(namen, bericht):
    """Läuft im eigenen Prozess: die Module nacheinander, je Modul die Dauer; Bericht als JSON."""
    sys.path.insert(0, os.path.abspath(TESTS))
    loader = unittest.TestLoader()
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=1)
    summe = {"ran": 0, "failures": 0, "errors": 0, "skipped": 0, "expected_failures": 0, "unexpected_successes": 0, "dauer": {}}
    for name in namen:
        t0 = time.monotonic()
        try:
            suite = loader.loadTestsFromName(name)
        except Exception as e:                            # noqa: BLE001 – Modul lädt nicht (z. B. Syntaxfehler): ein Fehler, wie discover
            print("=" * 70 + f"\nERROR: {name} (Modul lädt nicht)\n" + "-" * 70 + f"\n{type(e).__name__}: {e}\n", flush=True)
            summe["errors"] += 1
            summe["ran"] += 1
            summe["dauer"][name] = time.monotonic() - t0
            continue
        r = runner.run(suite)
        summe["dauer"][name] = time.monotonic() - t0
        summe["ran"] += r.testsRun
        summe["failures"] += len(r.failures)
        summe["errors"] += len(r.errors)
        summe["skipped"] += len(r.skipped)
        summe["expected_failures"] += len(r.expectedFailures)
        summe["unexpected_successes"] += len(r.unexpectedSuccesses)
        sys.stdout.flush()
    with open(bericht, "w", encoding="utf-8") as f:
        json.dump(summe, f)
    return 0 if not (summe["failures"] or summe["errors"] or summe["unexpected_successes"]) else 1


# --- Steuerung -----------------------------------------------------------------------------------------------------------------

def prozesse():
    try:
        n = int(os.environ.get("AMW_TESTPROZESSE") or 0)
    except ValueError:
        n = 0
    return n if n >= 1 else max(2, (os.cpu_count() or 2) // 2)


def ergebnis_zeile(s):
    teile = [f"{k}={s[k]}" for k in ("failures", "errors") if s[k]]
    teile += [f"{k}={s[k]}" for k in ("skipped",) if s[k]]
    teile += [f"expected failures={s['expected_failures']}"] if s["expected_failures"] else []
    teile += [f"unexpected successes={s['unexpected_successes']}"] if s["unexpected_successes"] else []
    rot = s["failures"] or s["errors"] or s["unexpected_successes"]
    return ("FAILED" if rot else "OK") + (f" ({', '.join(teile)})" if teile else "")


def steuern(n=None, wurzel=".", aus=sys.stdout, dauer_datei=None):
    t0 = time.monotonic()
    dauer_datei = dauer_datei or DAUER_DATEI
    mods = module(wurzel)
    browser = {name for name, p in mods if ist_browser(p)}
    gruppen = verteilen(mods, n or prozesse(), dauern_lesen(dauer_datei), browser)
    basis = tempfile.mkdtemp(prefix="amw-testlauf-")
    laeufe = []
    for i, namen in enumerate(gruppen):
        ordner = os.path.join(basis, f"p{i}")
        os.makedirs(os.path.join(ordner, "tmp"))
        liste, bericht, log = (os.path.join(ordner, x) for x in ("module.json", "bericht.json", "ausgabe.txt"))
        with open(liste, "w", encoding="utf-8") as f:
            json.dump(namen, f)
        env = {k: v for k, v in os.environ.items() if k not in ("AMW_DB", "AMW_AGENT", "AMW_PROJEKT")}
        env.update(TMP=os.path.join(ordner, "tmp"), TEMP=os.path.join(ordner, "tmp"), TMPDIR=os.path.join(ordner, "tmp"),
                   PYTHONIOENCODING="utf-8",
                   PYTHONPATH=os.pathsep.join(x for x in (os.path.abspath(wurzel), PAKET_WURZEL, env.get("PYTHONPATH")) if x))
        logf = open(log, "w", encoding="utf-8", errors="replace")
        p = subprocess.Popen([sys.executable, "-X", "utf8", "-m", "amw.testlauf", "--arbeiter", liste, bericht], cwd=wurzel, env=env,
                             stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL)
        laeufe.append({"nr": i, "namen": namen, "proc": p, "log": log, "logf": logf, "bericht": bericht, "browser": i == 0 and bool(browser)})
    print(f"Gesamtlauf parallel: {len(mods)} Module auf {len(gruppen)} Prozesse"
          + (f" (Browser-Tests: {len(browser)} Module nacheinander in Prozess 0)" if browser else ""), file=aus, flush=True)
    summe = {"ran": 0, "failures": 0, "errors": 0, "skipped": 0, "expected_failures": 0, "unexpected_successes": 0}
    dauern = {}
    for l in laeufe:
        rc = l["proc"].wait()
        l["logf"].close()
        try:
            with open(l["bericht"], encoding="utf-8") as f:
                b = json.load(f)
        except (OSError, ValueError):
            b = None
        with open(l["log"], encoding="utf-8", errors="replace") as f:
            text = f.read()
        if b is None:                                     # der Prozess starb ohne Bericht: zählt als Fehler, Ausgabe zeigen
            summe["errors"] += 1
            print(f"\n=== Prozess {l['nr']} endete ohne Bericht (rc {rc}) – Module: {', '.join(l['namen'])}\n{text[-20000:]}", file=aus)
            continue
        for k in summe:
            summe[k] += b[k]
        dauern.update(b["dauer"])
        rot = b["failures"] or b["errors"] or b["unexpected_successes"]
        if rot:                                          # die Fehlerberichte (=== FAIL/ERROR …) wie unittest sie schreibt
            print(f"\n=== Prozess {l['nr']}: {ergebnis_zeile(b)}", file=aus)
            print("\n".join(z for z in _berichte(text)), file=aus)
    dauern_schreiben(dauern, dauer_datei)
    shutil.rmtree(basis, ignore_errors=True)
    print("-" * 70, file=aus)
    print(f"Ran {summe['ran']} tests in {time.monotonic() - t0:.3f}s\n", file=aus)
    print(ergebnis_zeile(summe), file=aus, flush=True)
    return 0 if not (summe["failures"] or summe["errors"] or summe["unexpected_successes"]) else 1


def _berichte(text):
    """Aus der Ausgabe eines Prozesses nur die Fehlerblöcke (von „=====“ + FAIL/ERROR bis zur nächsten Trennlinie „-----“ vor
    „Ran …“) – die Punktreihen und Zusammenfassungen je Modul fallen weg."""
    zeilen, aus, drin = text.splitlines(), [], False
    for i, z in enumerate(zeilen):
        if z.startswith("=" * 70) and i + 1 < len(zeilen) and re.match(r"^(FAIL|ERROR|UNEXPECTED SUCCESS):", zeilen[i + 1]):
            drin = True
        elif z.startswith("-" * 70) and i + 1 < len(zeilen) and zeilen[i + 1].startswith("Ran "):
            drin = False
        if drin:
            aus.append(z)
    return aus


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["--arbeiter"]:
        with open(argv[1], encoding="utf-8") as f:
            namen = json.load(f)
        return arbeiter(namen, argv[2])
    return steuern()


if __name__ == "__main__":
    sys.exit(main())
