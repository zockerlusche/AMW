"""A1915 (D1304 v12 §1.3/§6d): Themen → Pakete. Aufgaben verweisen auf Themen (`amw aufgabe aendern N --thema TH…`, mehrere,
ohne Schemaänderung über plan_ereignis). Bekommt ein freigegebenes Thema eine neue Fassung (Pfleger oder Mensch), gehen die
offenen Aufgaben mit Verweis als „Thema geändert – prüfen“ an ihren Agenten – eine Nachricht je Agent; p-Pakete an den Lead,
ein laufendes wird nicht unterbrochen. Kein Status von Hand, keiner wird gesetzt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import unittest
from unittest import mock

from amw import arbeitspaket, cli, db, kern, themen
from tests.test_themen_bereich import Grund


class Basis(Grund):
    def setUp(self):
        super().setUp()
        for k in ("CC2", "CC3"):
            kern.agent_neu(self.con, self.pid, k)
        self.a = kern.aufgabe_neu(self.con, self.pid, "TL", "Anmeldeseite bauen", agent="CC2")
        self.b = kern.aufgabe_neu(self.con, self.pid, "TL", "Abmelden bauen", agent="CC2")
        self.c = kern.aufgabe_neu(self.con, self.pid, "TL", "SSO-Test", agent="CC3")
        self.fertig = kern.aufgabe_neu(self.con, self.pid, "TL", "Alte Anmeldung", agent="CC3")
        self.anderes = themen.neu(self.con, self.pid, "TL", "Speichern", pfleger="CC1")

    def freigeben(self):
        self.vorlage(0)
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)

    def meldungen(self, an):
        return [(r["kurz"], r["text"]) for r in self.con.execute(
            "SELECT n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW'"
            " AND n.kurz LIKE 'Thema geändert%' ORDER BY n.id", (an,))]

    def cli(self, *args):
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Produkt", *args])
        return rc, aus.getvalue()


class Verweise(Basis):
    def test_setzen_loesen_rechte_und_anzeige(self):
        rc, aus = self.cli("aufgabe", "aendern", str(self.a), "--thema", f"TH{self.tid},Speichern", "--von", "TL")
        self.assertEqual(rc, 0, aus)
        self.assertIn(f"A{self.a}: Themen TH{self.tid}, TH{self.anderes}", aus)
        self.assertEqual(themen.verweise(self.con, self.pid, self.a), [self.tid, self.anderes])
        rc, aus = self.cli("aufgabe", "zeige", str(self.a), "--von", "TL")
        self.assertIn(f"themen: TH{self.tid} Anmeldung, TH{self.anderes} Speichern", aus)
        themen.verweise_setzen(self.con, self.pid, "CC2", self.a, ["Speichern"], entfernen=True)     # ihr Agent darf
        self.assertEqual(themen.verweise(self.con, self.pid, self.a), [self.tid])
        with self.assertRaisesRegex(kern.AmwFehler, "Lead, Entwickler, Co-Entwickler oder ihr Agent"):
            themen.verweise_setzen(self.con, self.pid, "CC3", self.a, ["Speichern"])                 # ein fremder Agent nicht
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="CC3")
        themen.verweise_setzen(self.con, self.pid, "CC3", self.a, ["Speichern"])                     # der Co-Entwickler schon
        with self.assertRaisesRegex(kern.AmwFehler, "gibt es nicht"):
            themen.verweise_setzen(self.con, self.pid, "TL", self.a, ["TH999"])
        n = self.con.execute("SELECT count(*) FROM plan_ereignis WHERE art = ?", (themen.VERWEIS,)).fetchone()[0]
        themen.verweise_setzen(self.con, self.pid, "TL", self.a, [f"TH{self.tid}"])                  # schon gesetzt: kein Eintrag
        self.assertEqual(self.con.execute("SELECT count(*) FROM plan_ereignis WHERE art = ?", (themen.VERWEIS,)).fetchone()[0], n)
        self.assertEqual([x["id"] for x in themen.aufgaben_zu(self.con, self.pid, self.tid)], [self.a])


class Melden(Basis):
    def verweisen(self):
        for aid in (self.a, self.b, self.c, self.fertig):
            themen.verweise_setzen(self.con, self.pid, "TL", aid, [f"TH{self.tid}"])
        kern.aufgabe_status(self.con, self.pid, "CC3", self.fertig, "fertig", beleg="abc")

    def test_nur_freigegebene_themen_melden(self):
        self.verweisen()
        self.vorlage(0)                                                                             # nie freigegeben
        self.assertEqual((self.meldungen("CC2"), self.meldungen("CC3")), ([], []))

    def test_neue_fassung_des_pflegers_eine_nachricht_je_agent(self):
        self.verweisen()
        status_vorher = {aid: self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0] for aid in (self.a, self.b, self.c)}
        self.freigeben()
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Anmeldung mit Firmen-Konto, jetzt auch am Handy.")
        m2, m3 = self.meldungen("CC2"), self.meldungen("CC3")
        self.assertEqual(len(m2), 1)                                                                # gebündelt: zwei Aufgaben, eine Nachricht
        self.assertEqual(m2[0][0], f"Thema geändert – prüfen: TH{self.tid} „Anmeldung“ (Fassung 2), 2 Aufgabe(n)")
        self.assertIn(f"A{self.a} ", m2[0][1])
        self.assertIn(f"A{self.b} ", m2[0][1])
        self.assertIn(f"amw thema zeige TH{self.tid}", m2[0][1])
        self.assertEqual(len(m3), 1)
        self.assertIn(f"A{self.c} ", m3[0][1])
        self.assertNotIn(f"A{self.fertig} ", m3[0][1])                                             # fertige nicht
        for aid, s in status_vorher.items():                                                        # kein Status wird gesetzt
            self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0], s)

    def test_bearbeitung_des_menschen_meldet_auch_und_geloeste_verweise_nicht(self):
        self.verweisen()
        themen.verweise_setzen(self.con, self.pid, "TL", self.c, [f"TH{self.tid}"], entfernen=True)
        self.freigeben()
        themen.bearbeiten(self.con, self.pid, kern.ENTWICKLER, self.tid, "Mein Text.")
        self.assertEqual(len(self.meldungen("CC2")), 1)
        self.assertEqual(self.meldungen("CC3"), [])

    def test_p_paket_an_den_lead_laufendes_laeuft_weiter(self):
        p = kern.aufgabe_neu(self.con, self.pid, "TL", "Paket Anmeldung", "TL")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET pruefbefehl = 'python -m unittest tests.test_x', dateibereich = 'web/' WHERE id = ?", (p,))
        arbeitspaket.setzen(self.con, self.pid, "TL", p, art="p")
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", p, "startklar")
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", p, "laeuft")
        themen.verweise_setzen(self.con, self.pid, "TL", p, [f"TH{self.tid}"])
        self.freigeben()
        r = themen.pflegen(self.con, self.pid, "CC1", self.tid, "Neue Fassung.")
        m = self.meldungen("TL")
        self.assertEqual(len(m), 1)
        self.assertIn(f"A{p} ", m[0][1])
        self.assertIn("p-Paket läuft weiter, nach dem Lauf prüfen", m[0][1])
        self.assertEqual(arbeitspaket.lesen(self.con, p)["zustand"], "laeuft")                      # nicht unterbrochen
        self.assertEqual(r, 2)


if __name__ == "__main__":
    unittest.main()
