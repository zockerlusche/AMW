"""Menü nach TH156 (A2018): Leitstand · Projektweg · Fragen (bis „Für dich“) · Wissen · Betrieb · Einstellungen. Was früher ein eigener Menüpunkt war, gehört zu einem dieser Bereiche; die alten Adressen bleiben gültig."""
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

    def test_punkte_und_namen(self):
        nav = self.html.split('<nav id="nav">')[1].split("</nav>")[0]
        self.assertEqual(re.findall(r'<a data-sicht="(\w+)"', nav),
                         ["start", "projektweg", "fragen", "wissen", "betrieb", "einstellungen"])   # A1896: + Themen (W2429/W2431); A2033: + Projektweg (TL #31935, bis A2018)
        self.assertEqual(re.findall(r'<a data-sicht="(\w+)" class="im-mehr"', nav), ["betrieb", "einstellungen"])   # am Handy unter „Mehr“
        for x in ('n_start: "Leitstand"', 'n_start: "Control room"', 'n_projektweg: "Project path"', 'n_fragen: "Fragen"', 'n_planung: "Planung"', 'n_nachrichten: "Nachrichten"'):
            self.assertIn(x, self.html)

    def test_alte_seiten_sind_reiter_ihres_bereichs(self):
        bereich = dict(re.findall(r'(\w+): "(\w+)"', self.html.split("const BEREICH = {")[1].split("};")[0]))
        self.assertEqual(bereich, {"planung": "projektweg", "themen": "projektweg", "arbeit": "projektweg", "verlauf": "projektweg", "nachrichten": "wissen",
                                   "teamchat": "wissen", "runde": "wissen", "dokumente": "wissen", "releases": "wissen", "termine": "betrieb"})
        sichten = self.html.split("const fertig = ({")[1].split("}[sicht]")[0]
        for s in ("planung", "themen", "nachrichten", "arbeit", "verlauf", "teamchat", "runde", "dokumente", "releases", "termine"):   # alte Adressen gehen weiter
            self.assertIn(f"{s}: sicht", sichten)
        self.assertIn('m.append(planReiter("arbeit"))', self.html)
        self.assertIn('m.append(planReiter("verlauf"))', self.html)
        self.assertIn('m.append(nrReiterLeiste("teamchat"))', self.html)
        self.assertIn('m.append(wissenReiter("dokumente"))', self.html)
        self.assertIn('m.append(wissenReiter("releases"))', self.html)


if __name__ == "__main__":
    unittest.main()
