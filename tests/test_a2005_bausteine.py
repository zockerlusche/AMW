"""A2005 (F5386 A, TH156 AUFRÄUMEN): die Workbench-Seite in Bausteinen – eine Quelle in amw/workbench/ (Gerüst, Stil-Teile,
Sprachdateien texte/de.json und texte/en.json, Skript-Bausteine), zusammengesetzt von workbench.seite().

Der Schnitt-Commit belegte die Byte-Gleichheit mit der letzten amw/workbench.html (SHA-256 a9bf6c2d…, 845706 Bytes). Mit dem
JSON-Schritt ersetzt dieser Test ihn durch „jeder Baustein genau einmal, keine Reste“ (Lead F5392 (2)) – das ist kein geschwächter
Test: er prüft jede Zeile jedes Bausteins und jeden Text jeder Sprache einzeln, statt eine Summe über die alte Datei."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import re
import unittest

from amw import workbench


class Bausteine(unittest.TestCase):
    def test_jeder_baustein_genau_einmal_keine_reste(self):
        s = workbench.seite()
        for ordner in ("stil", "skript"):
            for f in sorted(os.listdir(os.path.join(workbench.BAUSTEINE, ordner))):
                stuecke = workbench._lesen(ordner, f).replace("@@TEXTE_EN@@\n", "@@TEXTE_DE@@\n").split("@@TEXTE_DE@@\n")
                for stueck in (x for x in stuecke if len(x) > 40):
                    with self.subTest(baustein=f"{ordner}/{f}"):
                        self.assertEqual(s.count(stueck), 1)
        self.assertNotIn("@@TEXTE_", s)
        self.assertNotIn("@@STIL@@", s)
        self.assertNotIn("@@SKRIPT@@", s)
        self.assertTrue(s.lower().startswith("<!doctype html>"))
        self.assertEqual(s.count("</script>"), s.count("<script"))

    def test_jeder_text_genau_einmal_in_seiner_sprache(self):
        s = workbench.seite()
        de_a, en_a = s.index("\n  de: {\n"), s.index("\n  en: {\n")
        ende = s.index("\n};", en_a)
        teile = {"de": s[de_a:en_a], "en": s[en_a:ende]}
        for sprache in ("de", "en"):
            t = workbench.texte(sprache)
            self.assertGreater(len(t), 2000)
            for k, v in t.items():
                muster = r"(?<![\w])" + re.escape(f"{k}: {json.dumps(v, ensure_ascii=False)},")   # ganzer Schlüssel
                self.assertEqual(len(re.findall(muster, teile[sprache])), 1, f"{sprache}.{k}")
        self.assertEqual(set(workbench.texte("de")), set(workbench.texte("en")))       # jede Sprache kennt jeden Schlüssel

    def test_sprachdateien_sind_json(self):
        for sprache in ("de", "en"):
            with open(os.path.join(workbench.BAUSTEINE, "texte", f"{sprache}.json"), encoding="utf-8") as f:
                d = json.load(f)
            self.assertTrue(all(isinstance(v, str) for v in d.values()))
        self.assertEqual(sorted(os.listdir(os.path.join(workbench.BAUSTEINE, "texte"))), ["de.json", "en.json"])

    def test_keine_zweite_quelle(self):
        self.assertFalse(os.path.exists(os.path.join(workbench.HIER, "workbench.html")), "amw/workbench.html ist zurück – die Seite"
                         " lebt in amw/workbench/ (A2005, eine Quelle)")


if __name__ == "__main__":
    unittest.main()
