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
- Zeitgrenze (A2051): steht ein Arbeiter länger als AMW_TEST_ZEITGRENZE_S Sekunden (Vorgabe 300) still – kein neuer Test hat
  begonnen –, beendet die Steuerung genau diesen eigenen Prozess samt Kindern (Edge, php), meldet das Modul mit Testmethode
  als rot („Zeitgrenze“, mit der bisherigen Ausgabe des Arbeiters) und lässt die restlichen Module dieses Arbeiters in einem
  neuen Prozess weiterlaufen. Fortschritt: je fertigem Modul eine Zeile „[n/N] modul ok|ROT Xs (pK)“.
- Frist (A2051): setzt `amw lauf ausfuehren` AMW_LAUF_ENDE (Ende der Frist, Sekunden seit 1970), hört die Steuerung kurz
  davor selbst auf: je Arbeiter „Läuft gerade: …“ mit Modul, Testmethode und bisheriger Ausgabe, dann FAILED und rc 124.
- Baum (A2055): am Anfang und am Ende Stand (HEAD) und geänderte Dateien des Repos (git status, ohne daten/) samt Größe und
  Zeit; hat sich etwas geändert (jemand baut im selben Baum), steht „!! Baum während des Laufs geändert: …“ da, das Ergebnis
  ist FAILED und rc 3 – der Lauf gilt nicht als Beleg. Kein Git-Repo: keine Prüfung.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import typing
import unittest

TESTS = "tests"
MUSTER = re.compile(r"^test_\w+\.py$")
BROWSER = re.compile(r"test_aktualisieren import|tests\.rundgang|from tests import rundgang|\bmsedge\b|--headless")
DAUER_DATEI = os.path.join(os.environ.get("LOCALAPPDATA") or tempfile.gettempdir(), "AMW", "testdauer.json")
PAKET_WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # dort liegt amw/ – nur für den Start eines Prozesses
START = "import sys; sys.path.insert(1, {0!r}); from amw import testlauf; sys.exit(testlauf.main())"   # [0] = Arbeitsordner


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

ZAEHLER = ("ran", "failures", "errors", "skipped", "expected_failures", "unexpected_successes")


def _dateien(bericht):
    """Neben dem Bericht: stand.txt (Modul und Test, die gerade laufen – ihre Änderungszeit ist das Lebenszeichen) und
    fortschritt.jsonl (je fertigem Modul eine Zeile)."""
    ordner = os.path.dirname(bericht)
    return os.path.join(ordner, "stand.txt"), os.path.join(ordner, "fortschritt.jsonl")


def _stand_schreiben(datei, modul, test=""):
    try:
        with open(datei, "w", encoding="utf-8") as f:
            f.write(f"{modul}\t{test}\n")
    except OSError:
        pass                                              # Lebenszeichen ist Zusatz – der Test läuft trotzdem


def _json_ersetzen(datei, daten):
    tmp = datei + ".neu"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(daten, f)
    os.replace(tmp, datei)


def arbeiter(namen, bericht):
    """Läuft im eigenen Prozess: die Module nacheinander, je Modul die Dauer. Der Bericht (JSON) steht nach jedem Modul
    aktuell auf der Platte – wird der Prozess an der Zeitgrenze beendet, zählt, was schon fertig war."""
    sys.path.insert(0, os.path.abspath(TESTS))
    stand, fortschritt = _dateien(bericht)
    modul = [""]

    class Ergebnis(unittest.TextTestResult):
        def startTest(self, test):                        # A2051: jeder Test ein Lebenszeichen mit Modul und Methode
            _stand_schreiben(stand, modul[0], test.id())
            super().startTest(test)

    loader = unittest.TestLoader()
    runner = unittest.TextTestRunner(stream=sys.stdout, verbosity=1, resultclass=typing.cast(typing.Any, Ergebnis))
    summe = {**{k: 0 for k in ZAEHLER}, "dauer": {}}
    for name in namen:
        modul[0] = name
        _stand_schreiben(stand, name)
        t0 = time.monotonic()
        vorher = {k: summe[k] for k in ZAEHLER}
        try:
            suite = loader.loadTestsFromName(name)
        except Exception as e:                            # noqa: BLE001 – Modul lädt nicht (z. B. Syntaxfehler): ein Fehler, wie discover
            print("=" * 70 + f"\nERROR: {name} (Modul lädt nicht)\n" + "-" * 70 + f"\n{type(e).__name__}: {e}\n", flush=True)
            summe["errors"] += 1
            summe["ran"] += 1
        else:
            r = runner.run(suite)
            summe["ran"] += r.testsRun
            summe["failures"] += len(r.failures)
            summe["errors"] += len(r.errors)
            summe["skipped"] += len(r.skipped)
            summe["expected_failures"] += len(r.expectedFailures)
            summe["unexpected_successes"] += len(r.unexpectedSuccesses)
        summe["dauer"][name] = time.monotonic() - t0
        sys.stdout.flush()
        rot = any(summe[k] > vorher[k] for k in ("failures", "errors", "unexpected_successes"))
        _json_ersetzen(bericht, summe)
        with open(fortschritt, "a", encoding="utf-8") as f:
            f.write(json.dumps({"modul": name, "dauer": round(summe["dauer"][name], 1), "rot": rot}) + "\n")
    _json_ersetzen(bericht, summe)
    return 0 if not (summe["failures"] or summe["errors"] or summe["unexpected_successes"]) else 1


# --- Steuerung -----------------------------------------------------------------------------------------------------------------

ZEITGRENZE_S = 300                                        # A2051: so lange darf ein Arbeiter ohne neuen Test still stehen
RESERVE_S = 45                                            # vor dem Ende der Frist: Zeit zum Aufschreiben und Beenden
SCHAU_S = 0.5


def prozesse():
    try:
        n = int(os.environ.get("AMW_TESTPROZESSE") or 0)
    except ValueError:
        n = 0
    return n if n >= 1 else max(2, (os.cpu_count() or 2) // 2)


def zeitgrenze():
    """Sekunden ohne neuen Test, dann gilt ein Arbeiter als hängend: AMW_TEST_ZEITGRENZE_S, sonst ZEITGRENZE_S."""
    try:
        s = float(os.environ.get("AMW_TEST_ZEITGRENZE_S") or 0)
    except ValueError:
        s = 0
    return s if s > 0 else ZEITGRENZE_S


def lauf_ende():
    """Ende der Frist des Laufs (time.time()-Sekunden) aus AMW_LAUF_ENDE, sonst None."""
    try:
        e = float(os.environ.get("AMW_LAUF_ENDE") or 0)
    except ValueError:
        return None
    return e or None


def ergebnis_zeile(s):
    teile = [f"{k}={s[k]}" for k in ("failures", "errors") if s[k]]
    teile += [f"{k}={s[k]}" for k in ("skipped",) if s[k]]
    teile += [f"expected failures={s['expected_failures']}"] if s["expected_failures"] else []
    teile += [f"unexpected successes={s['unexpected_successes']}"] if s["unexpected_successes"] else []
    rot = s["failures"] or s["errors"] or s["unexpected_successes"]
    return ("FAILED" if rot else "OK") + (f" ({', '.join(teile)})" if teile else "")


def _beenden(proc):
    """Nur den eigenen Arbeiter samt seinen Kindern (Edge, php -S) beenden – nie fremde Prozesse (KR14)."""
    if proc.poll() is not None:
        return
    if os.name == "nt":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(proc.pid)], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    else:
        import signal
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            proc.kill()
    try:
        proc.wait(timeout=30)
    except subprocess.TimeoutExpired:
        pass


class _Steuerung:
    def __init__(self, wurzel, aus, browser, gesamt):
        self.wurzel, self.aus, self.browser, self.gesamt = wurzel, aus, browser, gesamt
        self.basis = tempfile.mkdtemp(prefix="gl-")        # kurz und neutral: Tests suchen Texte wie „amw-test“ in Pfaden
        self.summe = {k: 0 for k in ZAEHLER}
        self.dauern, self.berichte, self.fertig, self.laufend = {}, [], 0, []

    def starten(self, nr, namen, versuch=0):
        ordner = os.path.join(self.basis, f"p{nr}" + (f"-{versuch}" if versuch else ""))
        os.makedirs(os.path.join(ordner, "tmp"))
        liste, bericht, log = (os.path.join(ordner, x) for x in ("module.json", "bericht.json", "ausgabe.txt"))
        with open(liste, "w", encoding="utf-8") as f:
            json.dump(namen, f)
        env = {k: v for k, v in os.environ.items() if k not in ("AMW_DB", "AMW_AGENT", "AMW_PROJEKT")}
        env.update(TMP=os.path.join(ordner, "tmp"), TEMP=os.path.join(ordner, "tmp"), TMPDIR=os.path.join(ordner, "tmp"),
                   PYTHONIOENCODING="utf-8")
        logf = open(log, "w", encoding="utf-8", errors="replace")
        browser = nr == 0 and bool(self.browser)
        # kein PYTHONPATH: Tests, die selbst Python in einem anderen Repo starten, fänden sonst dieses Paket tests (test_abnahme).
        # -u (A2051): die Ausgabe steht sofort in der Datei – auch wenn der Arbeiter an der Zeitgrenze beendet wird
        p = subprocess.Popen([sys.executable, "-u", "-X", "utf8", "-c", START.format(PAKET_WURZEL), "--arbeiter", liste, bericht],
                             cwd=self.wurzel, env=env, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)
                             | (0 if browser else getattr(subprocess, "BELOW_NORMAL_PRIORITY_CLASS", 0)),
                             start_new_session=os.name != "nt")
        # Browser-Tests warten auf Zeichnen und Zeitgeber – unter Volllast wackeln sie; die anderen Prozesse treten zurück
        stand, fortschritt = _dateien(bericht)
        self.laufend.append({"nr": nr, "namen": namen, "proc": p, "log": log, "logf": logf, "bericht": bericht, "stand": stand,
                             "fortschritt": fortschritt, "gelesen": 0, "erledigt": [], "start": time.time(), "versuch": versuch})

    def _fortschritt(self, w):
        try:
            with open(w["fortschritt"], encoding="utf-8") as f:
                f.seek(w["gelesen"])
                neu = f.read()
        except OSError:
            return
        ganz = neu[:neu.rfind("\n") + 1]                   # nur ganze Zeilen
        w["gelesen"] += len(ganz.encode("utf-8"))
        for z in ganz.splitlines():
            try:
                d = json.loads(z)
            except ValueError:
                continue
            self.fertig += 1
            w["erledigt"].append(d["modul"])
            print(f"[{self.fertig}/{self.gesamt}] {d['modul']} {'ROT' if d.get('rot') else 'ok'} {d.get('dauer', 0):.1f}s (p{w['nr']})",
                  file=self.aus, flush=True)

    @staticmethod
    def _stand(w):
        """(Modul, Test, Sekunden still) des Arbeiters."""
        try:
            with open(w["stand"], encoding="utf-8") as f:
                modul, _, test = f.read().strip().partition("\t")
            seit = os.path.getmtime(w["stand"])
        except OSError:
            modul, test, seit = (w["namen"][0] if w["namen"] else ""), "", w["start"]
        return modul, test, time.time() - max(seit, w["start"])

    @staticmethod
    def _text(w):
        try:
            with open(w["log"], encoding="utf-8", errors="replace") as f:
                return f.read()
        except OSError:
            return ""

    def _zaehlen(self, w):
        """Bericht des Arbeiters (auch unvollständig) in die Summe; Fehlerblöcke merken. False: kein Bericht da."""
        try:
            with open(w["bericht"], encoding="utf-8") as f:
                b = json.load(f)
        except (OSError, ValueError):
            return False
        for k in ZAEHLER:
            self.summe[k] += b[k]
        self.dauern.update(b["dauer"])
        if b["failures"] or b["errors"] or b["unexpected_successes"]:   # die Fehlerberichte (=== FAIL/ERROR …) wie unittest
            self.berichte.append(f"\n=== Prozess {w['nr']}: {ergebnis_zeile(b)}\n" + "\n".join(_berichte(self._text(w))))
        return True

    def abschliessen(self, w):
        w["logf"].close()
        self._fortschritt(w)
        if not self._zaehlen(w) and w["namen"]:              # der Prozess starb ohne Bericht: zählt als Fehler, Ausgabe zeigen
            self.summe["errors"] += 1
            self.berichte.append(f"\n=== Prozess {w['nr']} endete ohne Bericht (rc {w['proc'].returncode}) – Module: "
                                 f"{', '.join(w['namen'])}\n{self._text(w)[-20000:]}")

    def abbrechen(self, w, warum):
        """Arbeiter beenden (eigener Prozess samt Kindern), das laufende Modul als rot mit Testmethode und bisheriger Ausgabe.
        Rückgabe: die Module, die danach noch dran gewesen wären."""
        modul, test, still = self._stand(w)
        _beenden(w["proc"])
        w["logf"].close()
        self._fortschritt(w)
        self._zaehlen(w)
        self.summe["errors"] += 1
        self.summe["ran"] += 1
        self.berichte.append("=" * 70 + f"\nERROR: {test or modul} ({warum}: Prozess p{w['nr']} seit {still:.0f} s still – beendet)\n"
                             + "-" * 70 + f"\nModul {modul}. Bisherige Ausgabe des Arbeiters:\n{self._text(w)[-8000:]}\n")
        rest = [m for m in w["namen"] if m not in w["erledigt"] and m != modul]
        return modul, test, still, rest

    def runde(self, grenze_s):
        for w in list(self.laufend):
            self._fortschritt(w)
            if w["proc"].poll() is not None:
                self.laufend.remove(w)
                self.abschliessen(w)
                continue
            _, _, still = self._stand(w)
            if still > grenze_s:
                self.laufend.remove(w)
                modul, test, still, rest = self.abbrechen(w, "Zeitgrenze")
                print(f"!! Zeitgrenze: {modul} ({test or 'beim Laden'}) in p{w['nr']} seit {still:.0f} s still – Prozess beendet"
                      + (f", weiter mit {len(rest)} Modulen" if rest else ""), file=self.aus, flush=True)
                if rest:
                    self.starten(w["nr"], rest, w["versuch"] + 1)

    def frist(self):
        """Kurz vor dem Ende der Frist: je Arbeiter festhalten, was gerade läuft, dann alle beenden."""
        print(f"\n=== Frist erreicht – Stand der Arbeiter ({len(self.laufend)} laufen noch)", file=self.aus, flush=True)
        for w in list(self.laufend):
            self.laufend.remove(w)
            modul, test, still, rest = self.abbrechen(w, "Frist")
            print(f"Läuft gerade: p{w['nr']} {modul} · {test or 'beim Laden'} (still seit {still:.0f} s)"
                  + (f" – danach noch {len(rest)} Module" if rest else ""), file=self.aus, flush=True)


RC_BAUM = 3
AUSGENOMMEN = ("daten/",)                                 # Daten der AMW im Baum zählen nicht als Änderung


def baum_stand(wurzel="."):
    """(HEAD, {Pfad: (Kennung, Größe, Zeit)}) der geänderten und neuen Dateien – oder None ohne Git."""
    def git(*a):
        r = subprocess.run(["git", "-C", wurzel, *a], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0), timeout=120)
        return r.stdout if r.returncode == 0 else None
    try:
        kopf = git("rev-parse", "HEAD")
        status = git("status", "--porcelain", "-uall", "-z")
    except (OSError, subprocess.SubprocessError):
        return None
    if kopf is None or status is None:
        return None
    dateien = {}
    for eintrag in status.split("\0"):
        if len(eintrag) < 4:
            continue
        pfad = eintrag[3:]
        if pfad.startswith(AUSGENOMMEN):
            continue
        try:
            st = os.stat(os.path.join(wurzel, pfad))
            dateien[pfad] = (eintrag[:2], st.st_size, st.st_mtime_ns)
        except OSError:
            dateien[pfad] = (eintrag[:2], None, None)
    return kopf.strip(), dateien


def baum_unterschied(vorher, nachher):
    """Was sich zwischen zwei baum_stand geändert hat: [Text] (leer = gleich)."""
    if vorher is None or nachher is None:
        return []
    aus = [f"HEAD {vorher[0][:8]} → {nachher[0][:8]}"] if vorher[0] != nachher[0] else []
    for pfad in sorted(set(vorher[1]) | set(nachher[1])):
        if vorher[1].get(pfad) != nachher[1].get(pfad):
            aus.append(pfad)
    return aus


def steuern(n=None, wurzel=".", aus=sys.stdout, dauer_datei=None, grenze_s=None, ende=None):
    t0 = time.monotonic()
    baum = baum_stand(wurzel)                             # A2055
    dauer_datei = dauer_datei or DAUER_DATEI
    grenze_s = grenze_s or zeitgrenze()
    ende = ende if ende is not None else lauf_ende()
    mods = module(wurzel)
    browser = {name for name, p in mods if ist_browser(p)}
    gruppen = verteilen(mods, n or prozesse(), dauern_lesen(dauer_datei), browser)
    s = _Steuerung(wurzel, aus, browser, len(mods))
    for i, namen in enumerate(gruppen):
        s.starten(i, namen)
    print(f"Gesamtlauf parallel: {len(mods)} Module auf {len(gruppen)} Prozesse"
          + (f" (Browser-Tests: {len(browser)} Module nacheinander in Prozess 0)" if browser else "")
          + f" · Zeitgrenze {grenze_s:g} s ohne neuen Test", file=aus, flush=True)
    frist = False
    while s.laufend:
        if ende and time.time() >= ende - RESERVE_S:
            s.frist()
            frist = True
            break
        time.sleep(SCHAU_S)
        s.runde(grenze_s)
    for b in s.berichte:
        print(b, file=aus)
    dauern_schreiben(s.dauern, dauer_datei)
    shutil.rmtree(s.basis, ignore_errors=True)
    print("-" * 70, file=aus)
    geaendert = baum_unterschied(baum, baum_stand(wurzel))
    if geaendert:                                         # A2055: der geprüfte Stand ist nicht mehr der, der im Baum liegt
        print(f"!! Baum während des Laufs geändert: {', '.join(geaendert[:20])}" + (f" … und {len(geaendert) - 20} weitere"
              if len(geaendert) > 20 else "") + " – dieser Lauf gilt nicht als Beleg", file=aus)
    print(f"Ran {s.summe['ran']} tests in {time.monotonic() - t0:.3f}s\n", file=aus)
    zeile = ergebnis_zeile(s.summe)
    if geaendert:
        zeile = "FAILED (baum geaendert" + (", " + zeile.split("(", 1)[1] if "(" in zeile else ")")
    print(zeile, file=aus, flush=True)
    if frist:
        return 124
    if geaendert:
        return RC_BAUM
    return 0 if not (s.summe["failures"] or s.summe["errors"] or s.summe["unexpected_successes"]) else 1


def haenger(text):
    """Für die Meldung an den Lead (A2051): die Zeilen „Läuft gerade: …“ und „!! Zeitgrenze: …“ aus der Ausgabe, sonst die
    letzte Fortschrittszeile."""
    z = [x.strip() for x in text.splitlines() if x.startswith(("Läuft gerade:", "!! Zeitgrenze:"))]
    if z:
        return z
    f = [x.strip() for x in text.splitlines() if re.match(r"^\[\d+/\d+\] ", x)]
    return [f"zuletzt fertig: {f[-1]}"] if f else []


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
