"""A2004 (TL #31229, Marcel 23.11., TH164/TH166): p ist die Vorgabe – der Planer schneidet S und M-mechanisch (ohne Oberfläche)
als p-Paket mit Abnahme-Befehl und engen Bereichen; interaktiv nur mit Grund, sonst „Achtung“ beim Ja. aufgabe neu weist darauf
hin. Messung: Anteil p an fertigen Paketen je Tag, Kosten und Wartezeiten p gegen interaktiv; Kennzahl im Betrieb; unter 50 %
einmal je Tag eine Meldung an den Lead."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import copy
import datetime
import io
import json

from amw import arbeitspaket, cli, db, kern, messung, planer, themen, workbench
from tests.test_planer import ERGEBNIS, Grund

S_AGENT = {"schluessel": "P3", "meilenstein": "M1", "titel": "Hilfetext anpassen", "auftrag": "Text ändern.", "groesse": "S",
           "art": "mechanisch", "ausfuehrung": "agent", "fertig_quelle": "commit"}


class Planer(Grund):
    def setUp(self):
        super().setUp()
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)

    def befehl(self, *args):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Produkt", *args])
        return rc, aus.getvalue()

    def test_vorgabe(self):
        for groesse, art, p in (("S", "mechanisch", True), ("S", "text", True), ("S", "sicherheit", True), ("M", "mechanisch", True),
                                ("M", "text", False), ("L", "mechanisch", False), ("S", "oberflaeche", False), ("M", "oberflaeche", False)):
            with self.subTest(groesse=groesse, art=art):
                self.assertEqual(planer.p_vorgabe({"groesse": groesse, "art": art}), p)

    def test_p_braucht_bereiche_ohne_gesperrtes(self):
        d = copy.deepcopy(ERGEBNIS)
        del d["pakete"][1]["bereiche"]
        self.assertTrue(any("braucht enge Bereiche" in x for x in self.funde(d)))
        d["pakete"][1]["bereiche"] = "amw/kern.py, tests/test_anmeldung.py"
        self.assertTrue(any("gesperrte Pfade (amw/kern.py)" in x and "interaktiv_grund" in x for x in self.funde(d)))
        d["pakete"][1]["pakettyp"] = "malen"
        self.assertTrue(any("pakettyp „malen“" in x for x in self.funde(d)))

    def test_achtung_ohne_grund_beim_ja(self):
        d = copy.deepcopy(ERGEBNIS)
        d["pakete"].append(dict(S_AGENT))
        d["pakete"].append({**S_AGENT, "schluessel": "P4", "titel": "Seite prüfen", "interaktiv_grund": "Marcels Auge"})
        e = planer.pruefen(d, self.con, self.pid)
        self.assertEqual(planer.achtung(e), ["P3 „Hilfetext anpassen“ (S · mechanisch) läuft interaktiv ohne Grund – p wäre die Vorgabe"])
        self.assertIn("Achtung (p ist die Vorgabe):", planer.zusammenfassung(e))
        self.assertIn("Interaktiv, Grund: Marcels Auge", planer.zusammenfassung(e))
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, d)
        a = planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        m = [k for art, k in self.post("TL") if art == "meldung" and "Achtung" in k]
        self.assertEqual(m, [f"TH{self.tid}: Achtung – 1 Paket(e) interaktiv ohne Grund"])
        p4 = self.con.execute("SELECT auftrag FROM aufgabe WHERE id = ?", (int(a["P4"][1:]),)).fetchone()[0]
        self.assertTrue(p4.endswith("Interaktiv, Grund: Marcels Auge"))                       # der Grund steht im Paket

    def test_p_paket_mit_bereichen_typ_und_empfehlung(self):
        d = copy.deepcopy(ERGEBNIS)
        del d["pakete"][1]["modell"], d["pakete"][1]["effort"]                                 # weglassen = Empfehlung
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, d)
        a = planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        aid = int(a["P2"][1:])
        f = arbeitspaket.lesen(self.con, aid)
        self.assertEqual((f["art"], f["pakettyp"], f["modell"], f["effort"]), ("p", "test-schreiben", "sonnet", "medium"))
        self.assertEqual(self.con.execute("SELECT dateibereich FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0], "tests/test_anmeldung.py")
        from amw import reihenfolge
        self.assertEqual(reihenfolge.fehlende_felder(self.con, self.pid, self.con.execute("SELECT * FROM aufgabe WHERE id = ?",
                                                                                           (aid,)).fetchone()), [])   # startklar

    def test_plan_ja_im_terminal_nennt_achtung(self):
        d = copy.deepcopy(ERGEBNIS)
        d["pakete"].append(dict(S_AGENT))
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, d)
        rc, aus = self.befehl("thema", "plan-ja", f"TH{self.tid}", "--von", "TL")
        self.assertEqual(rc, 0, aus)
        self.assertIn("Achtung: P3 „Hilfetext anpassen“ (S · mechanisch) läuft interaktiv ohne Grund – p wäre die Vorgabe (P3 → A", aus)

    def test_planer_auftrag_und_schema(self):
        self.assertIn("p ist die Vorgabe", planer.AUFTRAG)
        for feld in ("bereiche", "pakettyp", "interaktiv_grund"):
            self.assertIn(feld, planer.SCHEMA_TEXT)

    def test_aufgabe_neu_hinweis(self):
        rc, aus = self.befehl("aufgabe", "neu", "--titel", "Kleinigkeit", "--groesse", "S", "--art", "mechanisch", "--von", "TL")
        self.assertEqual(rc, 0, aus)
        self.assertIn("p möglich: amw aufgabe aendern", aus)
        for extra in (["--paket", "p"], ["--auftrag", "Interaktiv, Grund: Erkundung"], []):
            groesse = ["--groesse", "L"] if not extra else ["--groesse", "S"]
            rc, aus = self.befehl("aufgabe", "neu", "--titel", "Noch was", *groesse, "--art", "mechanisch", *extra, "--von", "TL")
            self.assertNotIn("p möglich", aus, extra)


class Messung(Grund):
    def paket(self, p, tage_her=0, usd=None):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", f"Paket {p}", "CC1")
        if p:
            arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p")
        z = (datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(days=tage_her)).strftime("%Y-%m-%dT%H:%M:%SZ")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', begonnen_utc = ?, fertig_utc = ?, beleg = 'x' WHERE id = ?", (z, z, aid))
        if usd is not None:
            messung.erfassen(self.con, self.pid, "AMW", aid, usd=usd)
        return aid

    def plaetze(self):
        e = {"platz_wurzel": "D:\\plaetze", "plaetze": 1}
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps(e), self.pid))

    def test_quote_je_tag_und_kosten(self):
        self.paket(True, usd=0.3)
        self.paket(False, usd=4.0)
        self.paket(False, usd=6.0)
        self.paket(False, tage_her=2)
        self.paket(True, tage_her=9)                                                            # außerhalb von 7 Tagen
        q = messung.p_quote(self.con, self.pid)
        self.assertEqual((q["n"], q["p"], q["anteil"], q["ziel"]), (4, 1, 0.25, 0.5))
        self.assertEqual([(t["n"], t["p"]) for t in q["tage"]], [(1, 0), (3, 1)])
        k = q["kosten"]
        self.assertEqual((k["p"]["n"], k["p"]["median"], k["interaktiv"]["n"], k["interaktiv"]["median"], k["interaktiv"]["summe"]),
                         (1, 0.3, 2, 5.0, 10.0))
        self.assertNotIn("kosten", messung.p_quote(self.con, self.pid, kosten=False))

    def test_meldung_einmal_je_tag_nur_mit_plaetzen(self):
        self.paket(True)
        self.paket(False)
        self.paket(False)
        self.assertIsNone(messung.p_quote_melden(self.con, self.pid))                           # ohne Plätze kein p möglich
        self.plaetze()
        self.assertIn("Anteil p 33 %", messung.p_quote_melden(self.con, self.pid))
        m = [k for art, k in self.post("TL") if art == "meldung" and k.startswith("Anteil p")]
        self.assertEqual(m, ["Anteil p 33 % (Ziel ≥ 50 %)"])
        self.assertIsNone(messung.p_quote_melden(self.con, self.pid))                           # heute schon gemeldet
        self.assertEqual(messung.p_quote_runde(self.con), [])

    def test_keine_meldung_am_ziel(self):
        self.plaetze()
        self.paket(True)
        self.paket(False)
        self.assertIsNone(messung.p_quote_melden(self.con, self.pid))                           # 50 % – am Ziel

    def test_betrieb_und_befehl(self):
        self.paket(True, usd=0.26)
        self.paket(False, usd=3.0)
        d = workbench.daten_betrieb(self.con, self.pid)["p_quote"]
        self.assertEqual((d["n"], d["p"], d["anteil"]), (2, 1, 0.5))
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            cli.main(["--projekt", "Produkt", "messung", "--p", "--von", "TL"])
        self.assertIn("Anteil p (letzte 7 Tage): 1 von 2 = 50 % · Ziel ≥ 50 % – erreicht", aus.getvalue())
        self.assertIn("Kosten p: Median 0.26 $ · Summe 0.26 $ · n = 1", aus.getvalue())
        self.assertIn("Kosten interaktiv: Median 3.00 $", aus.getvalue())


if __name__ == "__main__":
    import unittest
    unittest.main()
