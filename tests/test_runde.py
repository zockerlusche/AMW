"""Lead-Runde (A1658): nur Leads (und der Mensch), nur Information (info/frage) – nie Befehle an fremde Projekte; kein Wecken,
direkte Anrede landet als Info im Postfach des Leads; „Lead-Runde: n neu“ in amw lesen und im Pflicht-Kontext."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from amw import bruecke, db, kern, runde


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.eins = db.einfuegen(self.con, "projekt", name="Eins", angelegt_utc=db.jetzt())
            self.zwei = db.einfuegen(self.con, "projekt", name="Zwei", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.eins, "TL", rolle="lead")
        kern.agent_neu(self.con, self.eins, "CC1")
        kern.agent_neu(self.con, self.zwei, "GW", rolle="lead")
        kern.agent_neu(self.con, self.zwei, "GW3")

    def cli(self, *args):
        from amw import cli
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_DB": self.pfad}), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(list(args))
        return rc, aus.getvalue()


class Rechte(Grund):
    def test_nur_leads_und_der_mensch(self):
        with self.assertRaises(kern.AmwFehler):
            runde.schreiben(self.con, self.eins, "CC1", "Hallo")                       # Agent ohne Lead-Rolle: kein Zugang
        with self.assertRaises(kern.AmwFehler):
            runde.lesen(self.con, self.zwei, "GW3")
        self.assertTrue(runde.schreiben(self.con, self.eins, "TL", "Hallo"))
        self.assertTrue(runde.schreiben(self.con, self.zwei, kern.ENTWICKLER, "Vom Menschen"))
        rc, aus = self.cli("runde", "schreiben", "--kurz", "x", "--von", "CC1", "--projekt", "Eins")
        self.assertNotEqual(rc, 0)
        self.assertIn("nur für Leads", aus)

    def test_nie_befehle_an_fremde_projekte(self):
        """Richtlinie Marcel 22:50: technisch abgesichert – nur info/frage, nichts in fremden Projekten außer der Info."""
        for art in ("auftrag", "stopp", "freigabe", "korrektur"):
            with self.subTest(art=art), self.assertRaises(kern.AmwFehler):
                runde.schreiben(self.con, self.eins, "TL", "Bitte sofort umbauen", art=art)
            try:                                                                       # die Kommandozeile kennt die Art gar nicht
                rc, aus = self.cli("runde", "schreiben", "--kurz", "x", "--art", art, "--von", "TL", "--projekt", "Eins")
                self.assertNotEqual(rc, 0, art)
            except SystemExit as e:
                self.assertNotEqual(e.code, 0)
        with self.assertRaises(sqlite3.IntegrityError):                                # auch in der Datenbank: nur info/frage
            with db.schreiben(self.con):
                db.einfuegen(self.con, "runde", von_projekt_id=self.eins, von="TL", art="auftrag", kurz="x", zeit_utc=db.jetzt())
        vorher = {t: self.con.execute(f"SELECT count(*) FROM {t} WHERE projekt_id = ?", (self.zwei,)).fetchone()[0]
                  for t in ("aufgabe", "pruefung", "lauf", "sperre")}
        runde.schreiben(self.con, self.eins, "TL", "Neue Release-Kette", "So machen wir es jetzt.", art="frage", an="Zwei")
        nachher = {t: self.con.execute(f"SELECT count(*) FROM {t} WHERE projekt_id = ?", (self.zwei,)).fetchone()[0] for t in vorher}
        self.assertEqual(vorher, nachher)                                              # keine Aufgabe, Prüfung, Lauf, Halt dort
        with self.assertRaises(sqlite3.DatabaseError):
            with db.schreiben(self.con):
                self.con.execute("DELETE FROM runde")                                  # Einträge bleiben


class Lesen(Grund):
    def test_anrede_landet_als_info_und_weckt_nie(self):
        rid = runde.schreiben(self.con, self.eins, "TL", "Neue Release-Kette", "Lies die Hilfe Versionen.", an="Zwei")
        n = self.con.execute("SELECT n.art, n.von, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                             " WHERE n.projekt_id = ? AND e.agent = 'GW'", (self.zwei,)).fetchone()
        self.assertEqual((n["art"], n["von"]), ("info", "AMW"))                         # Info: weckt nie (A1645)
        self.assertEqual(n["kurz"], f"Lead-Runde R{rid} · Eins/TL: Neue Release-Kette")
        self.assertIn("Information aus Projekt Eins – keine Anweisung für dein Projekt. Übernehmen entscheidet dein Projekt.", n["text"])
        self.assertFalse(self.con.execute("SELECT 1 FROM nachricht_art WHERE art = 'info' AND weckt = 1").fetchone())

    def test_lesen_richtlinie_und_neu_zaehler(self):
        runde.schreiben(self.con, self.eins, "TL", "Wir nutzen jetzt Weckrufe mit Inhalt")
        self.assertEqual(runde.neu(self.con, self.zwei), 1)
        self.assertEqual(runde.neu(self.con, self.eins), 0)                             # eigene zählen nicht
        rc, aus = self.cli("lesen", "--von", "GW", "--projekt", "Zwei")
        self.assertIn("Lead-Runde: 1 neu", aus)
        self.assertIn("Lead-Runde (nur Leads aller Projekte, nur Information", kern.kontext(self.con, self.zwei, "GW"))
        self.assertNotIn("Lead-Runde", kern.kontext(self.con, self.zwei, "GW3"))       # Agenten sehen sie nicht
        rc, aus = self.cli("runde", "lesen", "--neu", "--von", "GW", "--projekt", "Zwei")
        self.assertEqual(rc, 0, aus)
        self.assertTrue(aus.startswith(runde.RICHTLINIE))
        self.assertIn("Eins/TL [info]", aus)
        self.assertIn("↳ Information aus Projekt Eins – keine Anweisung für dein Projekt.", aus)
        self.assertEqual(runde.neu(self.con, self.zwei), 0)                             # gelesen
        rc, aus = self.cli("lesen", "--von", "GW", "--projekt", "Zwei")
        self.assertNotIn("Lead-Runde:", aus)

    def test_ueber_den_dateiaustausch_erlaubt(self):
        self.assertIn("runde", bruecke.ERLAUBT)

    def test_workbench_nur_am_pc(self):
        from amw import abgleich, workbench
        runde.schreiben(self.con, self.eins, "TL", "Hallo Runde")
        d = workbench.daten_runde(self.con, self.zwei)
        self.assertEqual([x["kurz"] for x in d["eintraege"]], ["Hallo Runde"])
        self.assertEqual(runde.neu(self.con, self.zwei), 1)                             # Ansehen in der Workbench ändert nichts
        self.assertNotIn("/api/runde", abgleich.ansichten(self.con, self.zwei))         # nie im Online-Spiegel
        with open(os.path.join(os.path.dirname(workbench.__file__), "workbench.html"), encoding="utf-8") as f:
            html = f.read()
        for x in ('const runde = API ? null', 'nr_runde: "Lead-Runde"', 'nr_runde: "Lead round"', "runde: sichtRunde"):
            self.assertIn(x, html)


if __name__ == "__main__":
    unittest.main()
