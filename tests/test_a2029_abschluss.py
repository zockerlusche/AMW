"""A2029 (TH164 F2 Schritt 5): Abschluss je Meilenstein – vor „bereit zur Abnahme“ laufen Gesamttest und Prüfer gegen das
Konzept (einmal je Stand); erfüllt → bereit mit Prüfung und Vorführung im Bericht; nicht erfüllt oder Test rot → die AMW legt
Nacharbeit im selben Meilenstein an und startet sie ohne neues Ja; „Nacharbeit anfordern“ plant mit Hinweis neue Pakete."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import abschluss, db, feinplanung, kern, planautomatik, planung, themen


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_PLANER_AUS", None)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
            from amw import schalter
            schalter._setzen(self.con, self.pid, "an")
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.t1 = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        self.t2 = themen.neu(self.con, self.pid, "TL", "Sicherung", pfleger="CC1")
        self.m = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", ziel=f"TH{self.t1} Anmeldung, TH{self.t2} Sicherung",
                                   abnahme="Vorführung beim Menschen")
        self.a1 = planung.schritt_setzen(self.con, self.pid, "TL", titel="Login", bogen_id=self.m, agent="CC1")
        self.a2 = planung.schritt_setzen(self.con, self.pid, "TL", titel="Nachtsicherung", bogen_id=self.m, agent="CC1")
        planung.bogen_status(self.con, self.pid, "TL", self.m, "aktiv")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234', fertig_utc = ? WHERE bogen_id = ?", (db.jetzt(), self.m))
        self.gestartet = []
        s = mock.patch.object(abschluss, "STARTER", lambda pid, bid, stand: self.gestartet.append((bid, stand)) or 4711)
        s.start()
        self.addCleanup(s.stop)
        f = mock.patch.object(feinplanung, "STARTER", lambda _pid, boegen, fassung: self.gestartet.append(("fein", boegen, fassung)) or 1)
        f.start()
        self.addCleanup(f.stop)

    def runde(self):
        return planautomatik.meilenstein_projekt(self.con, self.pid)

    def stand(self):
        return self.gestartet[0][1]

    def urteil(self, erfuellt=(True, True), nacharbeit=None):
        return {"themen": [{"thema": f"TH{self.t1}", "erfuellt": erfuellt[0], "beleg": "A%d Login" % self.a1, "fehlt": None if erfuellt[0] else "SSO fehlt"},
                           {"thema": f"TH{self.t2}", "erfuellt": erfuellt[1], "beleg": "A%d" % self.a2}],
                "vorfuehrung": ["Seite öffnen", "mit Firmenkonto anmelden"], **({"nacharbeit": nacharbeit} if nacharbeit else {})}

    def post(self, an):
        return [(r["art"], r["kurz"]) for r in self.con.execute(
            "SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW' ORDER BY n.id", (an,))]

    def offen(self):
        return [r[0] for r in self.con.execute("SELECT titel FROM aufgabe WHERE bogen_id = ? AND status != 'fertig' ORDER BY id", (self.m,))]


class VorDerAbnahme(Grund):
    def test_erst_pruefen_dann_bereit(self):
        self.assertEqual(self.runde(), [])                                                 # nicht „bereit“: die Prüfung läuft
        self.assertEqual(len(self.gestartet), 1)
        self.assertEqual(self.runde(), [])                                                 # einmal je Stand
        self.assertEqual(len(self.gestartet), 1)
        e = abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"lauf": 7, "rc": 0, "befehl": "python -m unittest"}, self.urteil())
        self.assertTrue(e["ok"])
        self.assertEqual(self.runde(), [(self.m, "bereit")])
        from amw import tore
        text = tore.bericht_text(self.con, self.pid, self.m)
        self.assertIn("## Prüfung gegen das Konzept", text)
        self.assertIn("Gesamttest: L7 · rc 0 · grün", text)
        self.assertIn(f"- TH{self.t1}: erfüllt", text)
        self.assertIn("1. Seite öffnen", text)

    def test_nicht_erfuellt_nacharbeit_ohne_neues_ja(self):
        self.runde()
        n = [{"schluessel": "N1", "meilenstein": "M1", "thema": f"TH{self.t1}", "titel": "SSO ergänzen", "auftrag": "Firmenkonto anbinden.",
              "groesse": "M", "art": "sicherheit", "ausfuehrung": "agent", "fertig_quelle": "commit", "interaktiv_grund": "gesperrter Bereich"}]
        e = abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"lauf": 7, "rc": 0, "befehl": "x"}, self.urteil((False, True), n))
        self.assertFalse(e["ok"])
        self.assertEqual(self.offen(), ["SSO ergänzen"])
        self.assertEqual(self.runde(), [])                                                 # offenes Paket: nicht bereit
        self.assertIn(("meldung", "Meilenstein 1: Nacharbeit – 1 Paket(e) gestartet"), self.post("TL"))
        self.assertIn(("info", "Meilenstein 1: Nacharbeit – 1 Paket(e) gestartet"), self.post(kern.ENTWICKLER))

    def test_test_rot_ohne_vorschlag_legt_ein_paket_an(self):
        self.runde()
        abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"lauf": 9, "rc": 1, "befehl": "x"}, self.urteil())
        self.assertEqual(self.offen(), ["Gesamttest rot beheben (L9)"])

    def test_pruefer_ging_nicht_dann_bereit_wie_bisher(self):
        self.runde()
        abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"befehl": None, "rc": None}, None, fehler="Zeitüberschreitung")
        self.assertEqual(self.runde(), [(self.m, "bereit")])
        self.assertIn(("meldung", "Meilenstein 1: Abschlussprüfung ging nicht"), self.post("TL"))

    def test_ohne_planer_gleich_bereit(self):
        os.environ["AMW_PLANER_AUS"] = "1"
        self.assertEqual(self.runde(), [(self.m, "bereit")])
        self.assertEqual(self.gestartet, [])

    def test_pruefer_muss_jedes_thema_bewerten(self):
        from amw import planer
        u = self.urteil()
        u["themen"] = u["themen"][:1] + [{"thema": "TH999", "erfuellt": True, "beleg": "x"}]
        b = planung.bogen_zeile(self.con, self.pid, self.m)
        with self.assertRaises(planer.PlanFehler) as x:
            abschluss._pruefen(u, self.con, self.pid, b, False)
        self.assertIn(f"nicht bewertet: TH{self.t2}", " ".join(x.exception.fehler))
        with self.assertRaises(planer.PlanFehler) as x:
            abschluss._pruefen(self.urteil((False, True)), self.con, self.pid, b, False)
        self.assertIn("keine nacharbeit", " ".join(x.exception.fehler))


class NacharbeitAnfordern(Grund):
    def test_feinplaner_mit_hinweis_und_sofort_gestartet(self):
        r = abschluss.nacharbeit(self.con, self.pid, kern.ENTWICKLER, self.m, "Die Anmeldung braucht noch das Firmenkonto")
        self.assertTrue(r["gestartet"], r)
        self.assertEqual(self.gestartet[-1], ("fein", [self.m], 1))
        plan = {"pakete": [{"schluessel": "P1", "meilenstein": "M1", "thema": f"TH{self.t1}", "titel": "Firmenkonto anbinden",
                            "auftrag": "SSO.", "groesse": "M", "art": "sicherheit", "ausfuehrung": "agent", "fertig_quelle": "commit",
                            "interaktiv_grund": "gesperrter Bereich"}]}
        e = feinplanung.entwurf_eintragen(self.con, self.pid, [self.m], 1, plan)
        self.assertTrue(e.get("nacharbeit"))
        self.assertEqual(self.offen(), ["Firmenkonto anbinden"])
        self.assertIn(("meldung", "Nacharbeit M1: 1 Pakete angelegt und gestartet"), self.post("TL"))

    def test_rechte_und_hinweis(self):
        with self.assertRaisesRegex(kern.AmwFehler, "Mensch oder der Lead"):
            abschluss.nacharbeit(self.con, self.pid, "CC1", self.m, "x")
        with self.assertRaisesRegex(kern.AmwFehler, "was fehlt"):
            abschluss.nacharbeit(self.con, self.pid, "TL", self.m, " ")
        planung.bogen_status(self.con, self.pid, "TL", self.m, "fertig", automatik=True)
        with self.assertRaisesRegex(kern.AmwFehler, "laufenden Meilenstein"):
            abschluss.nacharbeit(self.con, self.pid, "TL", self.m, "x")

    def test_befehl_und_einstieg(self):
        from amw import cli, planer
        aus = io.StringIO()
        mensch = {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}
        with mock.patch.dict(os.environ, mensch), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "P", "bogen", "nacharbeit", str(self.m), "--hinweis", "SSO fehlt", "--von", "Entwickler"])
        self.assertEqual(rc, 0, aus.getvalue())
        self.assertIn("angestoßen", aus.getvalue())
        with mock.patch.object(abschluss, "ausfuehren") as a, mock.patch("amw.db.verbinde", return_value=mock.MagicMock()):
            planer.main(["--abschluss", "--projekt-id", "3", "--bogen", "7", "--stand", "[Stand 1 · x]"])
        self.assertEqual(a.call_args[0][1:], (3, 7, "[Stand 1 · x]"))


if __name__ == "__main__":
    unittest.main()
