"""Schritt-für-Schritt-Hilfen (R1a): ein Baustein, gespeist aus doc/hilfe/ – Aufbau der Dateien, beide Sprachen, jede
Hilfe, auf die die Oberfläche verweist, gibt es; am PC und online unter derselben Adresse."""
import json
import os
import re
import unittest

from amw import hilfen

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class Aufbau(unittest.TestCase):
    def test_zerlegen(self):
        d = hilfen.zerlegen("""# Titel der Hilfe

Wozu das gut ist.
Zweite Zeile.

## Du brauchst
- ein Konto
- zehn Minuten

## Schritte
1. **Anmelden** Auf der Seite anmelden.
   Fortsetzung mit `befehl`. ![Anmeldeseite](np-start)
2. Ohne Kurztitel.

## Diese Werte trägst du ein
| Feld | Woher |
|---|---|
| Adresse | von der Seite |

## Typische Fehler
- **Abgelehnt** – Schlüssel neu erzeugen.

## Danach
- weiter mit dem nächsten Schritt

## Häufige Fragen
### Kostet das?
Nein.
""")
        self.assertEqual((d["titel"], d["kurz"]), ("Titel der Hilfe", "Wozu das gut ist. Zweite Zeile."))
        self.assertEqual(d["brauchst"], ["ein Konto", "zehn Minuten"])
        self.assertEqual(d["schritte"][0], {"titel": "Anmelden", "text": "Auf der Seite anmelden. Fortsetzung mit `befehl`.",
                                            "bilder": [{"name": "np-start", "alt": "Anmeldeseite"}]})
        self.assertEqual(d["schritte"][1], {"titel": "", "text": "Ohne Kurztitel.", "bilder": []})
        self.assertEqual(d["werte"], [["Adresse", "von der Seite"]])
        self.assertEqual(d["fehler"], [["Abgelehnt", "Schlüssel neu erzeugen."]])
        self.assertEqual((d["danach"], d["fragen"]), (["weiter mit dem nächsten Schritt"], [["Kostet das?", "Nein."]]))

    def test_englische_ueberschriften(self):
        d = hilfen.zerlegen("# T\n\n## You need\n- a\n\n## Steps\n1. x\n\n## Values to enter\n| F | W |\n|---|---|\n| a | b |\n\n"
                            "## Common problems\n- **p** – q\n\n## Next\n- n\n\n## Questions\n### Q?\nA.\n")
        self.assertEqual([len(d[k]) for k in ("brauchst", "schritte", "werte", "fehler", "danach", "fragen")], [1, 1, 1, 1, 1, 1])

    def test_ohne_titel_oder_schritte_ist_keine_hilfe(self):
        for text in ("## Schritte\n1. x\n", "# Nur ein Titel\n\nText.\n"):
            with self.assertRaises(ValueError):
                hilfen.zerlegen(text)

    def test_unbekannt_und_keine_pfade(self):
        for name in ("gibt-es-nicht", "../kern", "ntfy.md", "", "NTFY"):
            with self.assertRaises(LookupError):
                hilfen.lesen(name)
        with self.assertRaises(LookupError):
            hilfen.lesen("ntfy", "fr")


class Inhalt(unittest.TestCase):
    def test_jede_hilfe_in_beiden_sprachen_und_lesbar(self):
        da = hilfen.pruefen()
        self.assertGreaterEqual(len(da), 3)
        for thema, sprachen in da.items():
            self.assertEqual(sprachen, ["de", "en"], thema)
            de, en = hilfen.lesen(thema, "de"), hilfen.lesen(thema, "en")
            self.assertEqual(en["sprache"], "en")
            self.assertEqual(len(de["schritte"]), len(en["schritte"]), thema)      # dieselben Schritte in beiden Sprachen
            self.assertEqual([[b["name"] for b in s["bilder"]] for s in de["schritte"]],
                             [[b["name"] for b in s["bilder"]] for s in en["schritte"]], thema)
            for s in de["schritte"]:
                for b in s["bilder"]:                                                # jedes Bild gibt es
                    self.assertTrue(os.path.isfile(os.path.join(WURZEL, "amw", "hilfe", b["name"] + ".webp")), b["name"])

    def test_oberflaeche_verweist_nur_auf_vorhandene_hilfen(self):
        with open(os.path.join(WURZEL, "amw", "workbench.html"), encoding="utf-8") as f:
            seite = f.read()
        gemeint = set(re.findall(r'(?:hilfe|hilfeKnopf|mitHilfe)\("([a-z0-9-]+)"', seite))
        self.assertTrue({"neues-projekt", "ntfy", "online-speicher-turso"} <= gemeint, gemeint)
        self.assertEqual(gemeint - set(hilfen.themen()), set())
        self.assertNotIn("npa_s1", seite)                                            # die alten Texte stehen nur noch in doc/hilfe

    def test_online_liegen_dieselben_dateien(self):
        """`amw web bauen` legt jede Hilfe je Sprache nach web/hilfe/ – und die .htaccess lässt genau diese Namen durch."""
        ordner = os.path.join(WURZEL, "web", "hilfe")
        for thema in hilfen.themen():
            for sprache in hilfen.SPRACHEN:
                with open(os.path.join(ordner, f"{thema}.{sprache}.json"), encoding="utf-8") as f:
                    self.assertEqual(json.load(f), hilfen.lesen(thema, sprache), f"{thema}.{sprache} – amw web bauen ausführen")
        with open(os.path.join(WURZEL, "web", ".htaccess"), encoding="utf-8") as f:
            regel = next(z for z in f.read().splitlines() if z.startswith("RewriteCond %{REQUEST_URI}") and "hilfe/" in z)
        muster = re.compile(regel.split(" !", 1)[1])
        for erlaubt in ("/hilfe/ntfy.de.json", "/hilfe/np-start.webp", "/index.php", "/api.php", "/"):
            self.assertTrue(muster.search(erlaubt), erlaubt)
        for gesperrt in ("/hilfe/ntfy.fr.json", "/hilfe/x.php", "/inc/lib.php", "/hilfe/../inc/seite.html", "/amw-konfig.php"):
            self.assertFalse(muster.search(gesperrt), gesperrt)


if __name__ == "__main__":
    unittest.main()
