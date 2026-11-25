"""A2089: kein Text der AMW nennt einen Meilenstein mit seiner internen Nummer – Textwächter über alle Module (tests/texte_waechter.py)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from tests import texte_waechter

# Vorläufig (A2089 Headless): diese Module stellt ein eigenes Paket um; streng prüft sie tests/streng_a2089.py. Danach: Liste leer, dann weg.
HEADLESS = ("amw/abschlusslage.py", "amw/planansicht.py", "amw/planautomatik.py", "amw/planung.py", "amw/termine.py", "amw/tore.py", "amw/verlauf.py",
            "amw/wartegrund.py")
# Dauerhaft richtig so: (Datei, Text in der Zeile) → Grund
AUSNAHMEN = {
    ("amw/meilensteine.py", "Meilenstein {int(bid)}"): "Notbehelf, wenn es den Meilenstein nicht gibt – es gibt dann keine Projektnummer",
    ("amw/planung.py", 'bezug=f"M{bid}"'): "gespeicherter Bezug einer Nachricht: intern (A2079)",
    ("amw/cli.py", "ab['bogen']:+d} Tage"): "Abweichung in Tagen, keine Nummer",
}


def offen(datei):
    """Funde, die keine Ausnahme sind."""
    z = texte_waechter.zeilen(datei)
    return [f"{datei}:{nr} {text.strip()}" for nr, text in texte_waechter.funde(datei)
            if not any(d == datei and s in z[nr - 1] for d, s in AUSNAHMEN)]


class Texte(unittest.TestCase):
    def test_kein_text_mit_interner_nummer(self):
        for datei in texte_waechter.dateien():
            if datei not in HEADLESS:
                with self.subTest(datei=datei):
                    self.assertEqual(offen(datei), [], "Projektnummer nennen: meilensteine.name(con, id) bzw. nennen(…)")

    def test_jede_ausnahme_wird_gebraucht(self):
        for datei, text in AUSNAHMEN:
            with self.subTest(datei=datei, text=text):
                z = texte_waechter.zeilen(datei)
                self.assertTrue(any(text in z[nr - 1] for nr, _ in texte_waechter.funde(datei)), "Ausnahme ohne Fund: streichen")


class Waechter(unittest.TestCase):
    """Findet er, was er finden soll – und nichts anderes?"""

    def test_findet(self):
        for quelle in ('f"Meilenstein {bid} ist fertig"', 'f"M{b[\'id\']} „x“"', '"Meilenstein " + str(bid)', '"Meilenstein %s" % bid', 'f"amw bogen freigeben {bid} --art grob"',
                       '(f"x"\n f" (M{x[\'bogen_id\']})")', 'f"--bogen {b[\'id\']}"', 'f"Meilenstein {v.get(\'bogen\')}"', 'f"Meilenstein {a.id} → {a.wert}"',
                       '("a " "Meilenstein " + str(int(bogen_id)))', 'f"amw spec vorlegen {bogen_id} entwurf"'):
            self.assertEqual(len(texte_waechter.funde_in(quelle)), 1, quelle)

    def test_findet_nicht(self):
        for quelle in ('f"M{b[\'nr\']}"', 'f"Meilenstein {nr}"', 'f"XM{bid}"', 'f"A{a.id}"', 'f"Aufgabe {x[\'id\']}"', 'f"{meilensteine.name(con, bid)} fertig"',
                       'f"amw aufgabe zeige {a.id}"', 'f"TH{t[\'id\']}"'):
            self.assertEqual(texte_waechter.funde_in(quelle), [], quelle)


if __name__ == "__main__":
    unittest.main()
