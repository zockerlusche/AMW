"""Sieben Menüpunkte (A1657, Marcel 14.11., B47): Übersicht · Fragen · Planung · Nachrichten · Wissen · Betrieb · Einstellungen.
Was früher ein eigener Menüpunkt war, ist ein Reiter seines Bereichs; die alten Adressen bleiben gültig."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import io
import os
import re
import unittest

from amw import workbench


class Menue(unittest.TestCase):
    def setUp(self):
        with io.StringIO(workbench.seite()) as f:
            self.html = f.read()

    def test_sieben_punkte_und_namen(self):
        nav = self.html.split('<nav id="nav">')[1].split("</nav>")[0]
        self.assertEqual(re.findall(r'<a data-sicht="(\w+)"', nav),
                         ["start", "fragen", "projektweg", "planung", "themen", "nachrichten", "wissen", "betrieb", "einstellungen"])   # A1896: + Themen (W2429/W2431); A2033: + Projektweg (TL #31935, bis A2018)
        self.assertEqual(re.findall(r'<a data-sicht="(\w+)" class="im-mehr"', nav), ["projektweg", "themen", "wissen", "betrieb", "einstellungen"])   # am Handy unter „Mehr“
        for x in ('n_start: "Übersicht"', 'n_start: "Overview"', 'n_fragen: "Fragen"', 'n_planung: "Planung"', 'n_nachrichten: "Nachrichten"'):
            self.assertIn(x, self.html)

    def test_alte_seiten_sind_reiter_ihres_bereichs(self):
        self.assertIn('const BEREICH = { arbeit: "planung", verlauf: "planung", teamchat: "nachrichten", runde: "nachrichten",'
                      ' dokumente: "wissen", releases: "wissen" };', self.html)
        sichten = self.html.split("const fertig = ({")[1].split("}[sicht]")[0]
        for s in ("arbeit", "verlauf", "teamchat", "runde", "dokumente", "releases"):   # alte Adressen gehen weiter
            self.assertIn(f"{s}: sicht", sichten)
        self.assertIn('m.append(planReiter("arbeit"))', self.html)
        self.assertIn('m.append(planReiter("verlauf"))', self.html)
        self.assertIn('m.append(nrReiterLeiste("teamchat"))', self.html)
        self.assertIn('m.append(wissenReiter("dokumente"))', self.html)
        self.assertIn('m.append(wissenReiter("releases"))', self.html)


if __name__ == "__main__":
    unittest.main()
