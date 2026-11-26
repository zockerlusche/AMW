"""A2019 (Marcel W2482, TL #31337): der Co-Entwickler heißt in der Anzeige „Co-Entwickler“ (Kennung klein dahinter; Befehle,
MCP und Dateiaustausch bleiben bei der Kennung). „Arbeitet an“ aus einer Nachricht nur bei der eigenen Aufgabe – wer über die
Aufgabe eines anderen schreibt (Lead oder Co: „A1924 freigegeben“), arbeitet nicht an ihr. Seite: Team (Baum und Liste) und der
Agenten-Dialog; Bilder PC/Handy hell/dunkel über AMW_RUNDGANG_BILDER."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest

from amw import db, gerade, kern, workbench
from tests.rundgang import Rundgang


class Ableitung(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "Lead", rolle="lead")
        kern.agent_neu(self.con, self.pid, "TL", arbeitsweise="chat")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.projekt_einstellen(self.con, self.pid, "Lead", co_entwickler="TL")
        self.fremd = kern.aufgabe_neu(self.con, self.pid, "Lead", "Lauf-Schlange mit Zeitfenster", agent="CC1")
        self.eigen = kern.aufgabe_neu(self.con, self.pid, "Lead", "Konzept Navigation", agent="TL")

    def test_nachricht_ueber_fremde_aufgabe_ist_nicht_seine_arbeit(self):
        kern.posten(self.con, self.pid, "TL", "Lead", "info", f"A{self.fremd} freigegeben – Marcel hat Ja gesagt",   # wie --bezug
                    aufgabe_id=self.fremd)
        self.assertIsNone(gerade.ableiten(self.con, self.pid, "TL"))                           # vorher: „A… Lauf-Schlange …“
        kern.posten(self.con, self.pid, "TL", "Lead", "info", f"A{self.eigen}: Entwurf steht", aufgabe_id=self.eigen)
        g = gerade.ableiten(self.con, self.pid, "TL")
        self.assertEqual((g["aufgabe"], g["quelle"]), (self.eigen, "meldung"))                 # die eigene Aufgabe bleibt

    def test_co_entwickler_in_den_daten(self):
        a = {x["kennung"]: x for x in workbench.daten_start(self.con, self.pid)["agenten"]}
        self.assertEqual((a["TL"]["co"], a["CC1"]["co"], a["Lead"]["co"]), (True, False, False))
        self.assertTrue(workbench.daten_agent(self.con, self.pid, "TL")["co"])
        self.assertFalse(workbench.daten_agent(self.con, self.pid, "CC1")["co"])
        self.assertEqual(kern.co_entwickler(self.con, self.pid), "TL")                           # die Kennung bleibt


class TeamSeite(Rundgang):
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "Co", arbeitsweise="chat")
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="Co")
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Lauf-Schlange mit Zeitfenster", agent="CC1")
        kern.posten(self.con, self.pid, "Co", "TL", "info", f"A{aid} freigegeben", aufgabe_id=aid)

    NAME = "[...document.querySelectorAll('#team .ls-agent')].map(e => e.innerText.replace(/\\s+/g, ' ')).join('|')"

    def test_team_zeigt_co_entwickler_ohne_fremde_aufgabe(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                self.assertEqual(self.besuchen("start", "team-a2019", bereit="document.querySelector('#team .ls-agent')", g=g, t=th,
                                               tun="document.querySelector('#team').scrollIntoView()", danach="true"), [], f"{g} {th}")   # Bild zeigt das Team
                self.assertIn("Co Co-Entwickler", self.tab.js(self.NAME))                    # A2006: Name, darunter die Rolle
                co = "[...document.querySelectorAll('#team [data-k=\"Co\"]')].map(e => e.textContent).join(' ')"
                self.assertNotIn("Lauf-Schlange", self.tab.js(co))                            # nicht „arbeitet an A…“
                self.assertNotIn("Plätze", self.tab.js("document.querySelector('#team').innerText"))   # (3) nie als „Plätze 1/1“ lesbar
        self.groesse("pc")
        self.tab.js("agentDialog('Co')")
        self.warten("document.querySelector('.agent-kopf h3')")
        self.assertEqual(self.tab.js("document.querySelector('.agent-kopf h3').textContent"), "Co-Entwickler Co")


if __name__ == "__main__":
    unittest.main()
