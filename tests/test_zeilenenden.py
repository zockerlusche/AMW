"""Zeilenenden als Automatismus statt Gebot (A1902, Befund P309: CHANGELOG.md ganz auf CRLF umgeschrieben, 4705 Zeilen Diff,
erst im Review bemerkt). Jede versionierte Textdatei hat LF ohne CR – außer was .gitattributes ausdrücklich auf eol=crlf setzt
(*.cmd, *.ps1), die haben überall CRLF. Git sagt, was Text ist und welches Attribut gilt (git ls-files --eol)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import subprocess
import unittest

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def eintraege(wurzel=WURZEL):
    """[(pfad, eol_attribut)] für jede versionierte Textdatei – eol_attribut „crlf“, „lf“ oder „“; None ohne Git."""
    try:
        r = subprocess.run(["git", "-C", wurzel, "ls-files", "-z", "--eol"], capture_output=True, timeout=60,
                           stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    if r.returncode != 0:
        return None
    liste = []
    for satz in r.stdout.decode("utf-8", "replace").split("\0"):
        if "\t" not in satz:
            continue
        kopf, pfad = satz.split("\t", 1)
        felder = kopf.split()                                    # i/lf  w/crlf  attr/text eol=crlf
        index = next((f[2:] for f in felder if f.startswith("i/")), "")
        if index == "-text":                                     # Binärdatei (Bild, Datenbank …)
            continue
        attr = kopf.split("attr/", 1)[1] if "attr/" in kopf else ""
        eol = "crlf" if "eol=crlf" in attr else "lf" if "eol=lf" in attr else ""
        liste.append((pfad, eol))
    return liste


def befunde(wurzel=WURZEL):
    """[„pfad: n CR“ bzw. „pfad: n Zeilen ohne CR“] – leer, wenn alles stimmt."""
    falsch = []
    for pfad, eol in eintraege(wurzel) or []:
        datei = os.path.join(wurzel, pfad)
        if not os.path.isfile(datei):                            # gerade gelöscht, noch nicht eingetragen
            continue
        with open(datei, "rb") as f:
            inhalt = f.read()
        if eol == "crlf":
            ohne = inhalt.count(b"\n") - inhalt.count(b"\r\n")
            if ohne:
                falsch.append(f"{pfad}: {ohne} Zeilen ohne CR (laut .gitattributes eol=crlf)")
        elif b"\r" in inhalt:
            n = inhalt.count(b"\r")
            falsch.append(f"{pfad}: {n} CR (erwartet LF – in Python mit open(…, newline=\"\\n\") schreiben)")
    return falsch


class Zeilenenden(unittest.TestCase):
    def test_lf_ausser_gitattributes(self):
        liste = eintraege()
        if liste is None:
            self.skipTest("kein Git-Arbeitsbaum")
        self.assertTrue(any(p == "amw/__init__.py" for p, _ in liste))          # die Liste ist wirklich das Repo
        self.assertTrue(any(e == "crlf" for _, e in liste))                     # *.cmd laut .gitattributes
        self.assertEqual(befunde(), [])

    def test_findet_cr_und_fehlendes_crlf(self):
        import tempfile
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            g = lambda *a: subprocess.run(["git", "-C", d, "-c", "core.autocrlf=false", *a], capture_output=True, check=True)
            try:
                g("init", "-q")
            except (OSError, subprocess.CalledProcessError):
                self.skipTest("kein Git")
            dateien = {".gitattributes": b"*.cmd text eol=crlf\n", "gut.md": b"a\nb\n", "schlecht.md": b"a\r\nb\r\n",
                       "gut.cmd": b"@echo\r\n", "schlecht.cmd": b"@echo\nx\r\n", "bild.png": b"\x89PNG\r\n\x1a\n\0\0"}
            for name, inhalt in dateien.items():
                with open(os.path.join(d, name), "wb") as f:
                    f.write(inhalt)
            g("add", "-A")
            self.assertEqual(sorted(befunde(d)), ["schlecht.cmd: 1 Zeilen ohne CR (laut .gitattributes eol=crlf)",
                                                  'schlecht.md: 2 CR (erwartet LF – in Python mit open(…, newline="\\n") schreiben)'])


if __name__ == "__main__":
    unittest.main()
