"""A1612: das Altfeld agent.grenzen ist aufgeräumt – die Team-Ansicht liest „Zuständig für“ jetzt unter seinem Namen (zustaendig,
nicht mehr als „grenzen“) und zeigt sie wie vorher; die Daten der Startseite und der Einstellungen tragen kein „grenzen“ mehr."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
from amw import db, kern, workbench
from tests.rundgang import Rundgang


class TeamZustaendig(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        kern.agent_neu(self.con, self.pid, "Maler", rolle="Grafik", zustaendig="Karten-Look und Sprites")
        kern.agent_neu(self.con, self.pid, "Leer")
        with db.schreiben(self.con):
            self.con.execute("UPDATE agent SET soll = 'aus' WHERE projekt_id = ? AND kennung IN ('Maler', 'Leer')", (self.pid,))

    def test_daten_ohne_altnamen(self):
        a = {x["kennung"]: x for x in workbench.daten_start(self.con, self.pid)["agenten"]}
        self.assertEqual(a["Maler"]["zustaendig"], "Karten-Look und Sprites")
        self.assertNotIn("grenzen", a["Maler"])
        e = {x["kennung"]: x for x in workbench.daten_einstellungen(self.con, self.pid)["agenten"]}
        self.assertEqual(e["Maler"]["zustaendig"], "Karten-Look und Sprites")
        self.assertNotIn("grenzen", e["Maler"])

    def test_team_zeigt_zustaendigkeit_wie_vorher(self):
        for g in ("pc", "handy"):
            with self.subTest(g=g):
                self.groesse(g)
                self.oeffnen("start", "document.querySelector('#team [data-k=Maler] .ls-auf')")
                self.assertEqual(self.tab.js("document.querySelector('#team [data-k=Maler] .ls-auf').textContent"), "Karten-Look und Sprites")
                self.assertEqual(self.tab.js("document.querySelector('#team [data-k=Leer] .ls-auf').textContent"),
                                 self.tab.js("TEXTE[sprache].tm_keine"))                # ohne Angabe: wie vorher „keine“
