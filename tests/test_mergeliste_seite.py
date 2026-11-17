"""„Bereit zum Merge“ in der Seite (A1858): Liste mit geänderten Dateien und Diff zum Aufklappen, „erst ansehen“ bei Server-Code,
„Alle freigeben“ am PC gibt die übrigen frei; Rundgang PC/Handy (Bilder über AMW_RUNDGANG_BILDER)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import shutil
import unittest

from amw import db, kern
from tests.rundgang import Rundgang
from tests.test_mergeliste import bereit, projekt_repo


@unittest.skipUnless(shutil.which("git") and os.name == "nt", "git/Windows fehlt")
class MergeSeite(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        kern.agent_neu(self.con, self.pid, "CC1")
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?",
                             (json.dumps({"platz_wurzel": os.path.join(self.ordner.name, "plaetze"), "plaetze": 2}), self.pid))
        repo = os.path.join(self.ordner.name, "projekt")
        projekt_repo(self.con, self.pid, repo)
        self.lib, _, _ = bereit(self.con, self.pid, repo, "Rechnen korrigieren", {"lib/rechnen.py": "def plus(a, b):\n    return a + b\n"})
        self.web, _, _ = bereit(self.con, self.pid, repo, "Schnittstelle erweitern",
                                {"web/api.php": "<?php\necho json_encode(['ok' => true]);\n"}, nr=2)

    ZEIGEN = "zustand.arbeit.sicht = 'pakete'; zeige('arbeit')"
    MERGE = "document.querySelector('.pk-merge')"

    def oeffnen_merge(self):
        self.oeffnen("arbeit", "document.querySelector('#inhalt .reiter')")
        self.tab.js(self.ZEIGEN)
        self.warten(self.MERGE, 15)

    def test_liste_und_alle_freigeben(self):
        self.oeffnen_merge()
        text = self.tab.js(f"{self.MERGE}.innerText").lower()
        for teil in ("bereit zum merge (2)", "rechnen korrigieren", "lib/rechnen.py", "web/api.php", "server-code", "erst ansehen",
                     "alle freigeben (1)", "angesehen – freigeben"):
            self.assertIn(teil, text)
        self.tab.js("window.confirm = () => true; document.querySelector('#mg-alle').click()")
        lib = f"document.querySelector('.pk-merge-paket[data-a=\"{self.lib}\"] .etikett.gruen')"   # Etikett: Großbuchstaben per CSS
        self.warten(f"{lib} && {lib}.textContent === t('mg_freigegeben')", 20)
        web = self.tab.js(f"document.querySelector('.pk-merge-paket[data-a=\"{self.web}\"]').innerText").lower()
        self.assertIn("erst ansehen", web)                               # Server-Code: „Alle freigeben“ lässt es aus
        self.assertNotIn("\nfreigegeben", web)
        self.assertEqual([r[0] for r in self.con.execute("SELECT aufgabe_id FROM pruefung WHERE ergebnis = 'gruen'")], [self.lib])

    def test_rundgang(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                fehler = self.besuchen("arbeit", "merge", bereit="document.querySelector('#inhalt .reiter')", tun=self.ZEIGEN,
                                       danach=self.MERGE, g=g, t=th)
                self.assertEqual(fehler, [], f"{g} {th}")
