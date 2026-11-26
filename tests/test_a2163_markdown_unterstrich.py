"""A2163 (Bild D1995): Unterstriche mitten im Wort machen nichts kursiv – snake_case, Pfade und Dateinamen bleiben, wie sie sind;
_kursiv_ und __fett__ nur am Wortrand (wie CommonMark), *kursiv* und **fett** wie bisher. Am PC und online (dieselbe Funktion)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import unittest

from tests.rundgang import OnlineRundgang, Rundgang

FAELLE = [
    ("nie_gleichzeitig und gleiche_ressource", "nie_gleichzeitig und gleiche_ressource"),
    ("feinplanung._anlegen in amw/feinplanung.py", "feinplanung._anlegen in amw/feinplanung.py"),
    ("Bild mein_bild_v2.png ablegen", "Bild mein_bild_v2.png ablegen"),
    ("ein _echtes_ Wort", "ein <em>echtes</em> Wort"),
    ("(_kursiv_), __fett__ und *stern*", "(<em>kursiv</em>), <strong>fett</strong> und <em>stern</em>"),
    ("**fett** mit `code_x`", "<strong>fett</strong> mit <code>code_x</code>"),
]


def pruefen(test):
    test.oeffnen("start", "typeof markdown === 'function'")
    for roh, html in FAELLE:
        with test.subTest(roh=roh):
            test.assertEqual(test.tab.js(f"markdown({json.dumps(roh)}).querySelector('p').innerHTML"), html)


class Seite(Rundgang):
    def test_unterstrich_mitten_im_wort(self):
        pruefen(self)


class Online(OnlineRundgang):
    def test_unterstrich_mitten_im_wort(self):
        pruefen(self)


if __name__ == "__main__":
    unittest.main()
