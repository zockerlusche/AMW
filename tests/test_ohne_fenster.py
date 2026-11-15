"""A1783 (Marcel 15.11. 19:09: „am laufenden Band geht eine Kommandozeile auf, irgendwas mit GitHub“): Der Dienst hat keine
Konsole – jedes Kind ohne CREATE_NO_WINDOW öffnet unter Windows ein Fenster. Darum: kein subprocess-Aufruf in amw/ ohne
creationflags; die eine Ausnahme (lauf ausfuehren im Terminal des Agenten, erbt dessen Konsole) steht mit FENSTER_GEWOLLT da.
Dazu: eine neu vergebene Prozess-Nummer macht ein fremdes Programm nicht zum Kind eines Laufs."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import ast
import datetime
import glob
import os
import unittest

from amw import belegung

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUFRUFE = ("run", "Popen", "check_output", "call", "check_call")


class OhneFenster(unittest.TestCase):
    def test_jeder_kindprozess_ohne_fenster(self):
        fehlt = []
        for p in sorted(glob.glob(os.path.join(WURZEL, "amw", "*.py"))):
            with open(p, encoding="utf-8") as f:
                src = f.read()
            zeilen = src.splitlines()
            for n in ast.walk(ast.parse(src)):
                if (isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute) and isinstance(n.func.value, ast.Name)
                        and n.func.value.id == "subprocess" and n.func.attr in AUFRUFE
                        and "creationflags" not in {k.arg for k in n.keywords}
                        and "FENSTER_GEWOLLT" not in "\n".join(zeilen[max(0, n.lineno - 4):n.end_lineno])):
                    fehlt.append(f"{os.path.basename(p)}:{n.lineno}")
        self.assertEqual(fehlt, [], "subprocess ohne creationflags=CREATE_NO_WINDOW (oder Vermerk FENSTER_GEWOLLT)")

    def test_ausnahme_nur_lauf_ausfuehren(self):
        treffer = []
        for p in sorted(glob.glob(os.path.join(WURZEL, "amw", "*.py"))):
            with open(p, encoding="utf-8") as f:
                treffer += [os.path.basename(p) for z in f if "FENSTER_GEWOLLT" in z and not z.strip().startswith('"')]
        self.assertEqual(treffer, ["cli.py"])


class NeuVergebeneNummer(unittest.TestCase):
    def test_aelteres_kind_zaehlt_nicht(self):
        t = lambda h, m: datetime.datetime(2026, 11, 15, h, m, tzinfo=datetime.timezone.utc)
        liste = [{"pid": 51880, "eltern": 1, "name": "python", "seit": t(19, 5)},          # Lauf L2240 (Nummer neu vergeben)
                 {"pid": 54004, "eltern": 51880, "name": "firefox", "seit": t(18, 33)},    # Firefox des Menschen, älter
                 {"pid": 60000, "eltern": 51880, "name": "Godot_v4", "seit": t(19, 6)}]    # echtes Kind des Laufs
        self.assertEqual(belegung._nachkommen(liste, [51880]), {51880, 60000})

    def test_ohne_startzeit_wie_bisher(self):
        liste = [{"pid": 1, "eltern": 0, "name": "a", "seit": None}, {"pid": 2, "eltern": 1, "name": "b", "seit": None}]
        self.assertEqual(belegung._nachkommen(liste, [1]), {1, 2})


if __name__ == "__main__":
    unittest.main()
