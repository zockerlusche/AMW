"""A1939 (K3, TH155 Punkte 1, 4, 5): „bereit zur Abnahme“ bei einem Urteil (Fertig-Quelle „ja“), ein Ja genügt und den Status setzt
die AMW; Themen am Meilenstein statt Spezifikation; Ziel und Abnahme als Verweis mit geltender Fassung."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, cli, db, dokumente, fertigquelle, kern, planung, themen, urteil, workbench


class Urteil(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None), ("CC2", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        self.bid = planung.bogen_neu(self.con, self.pid, "TL", "Konzept fertig", ziel="Konzept steht (TH1)", abnahme="D1 freigegeben")
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Marktübersicht schreiben", "CC1")
        planung.schritt_setzen(self.con, self.pid, "TL", aid=self.aid, bogen_id=self.bid, kriterien=["liest sich gut", "Zahlen belegt"])
        fertigquelle.pruefquelle_setzen(self.con, self.pid, "TL", self.aid, 2, "pruefung")
        fertigquelle.setzen(self.con, self.pid, "TL", self.aid, "ja")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.aid, "start")

    def a(self):
        return self.con.execute("SELECT * FROM aufgabe WHERE id = ?", (self.aid,)).fetchone()

    def test_bereit_nur_mit_fakt(self):
        self.assertEqual(urteil.zur_abnahme(self.con, self.pid), [])
        with self.assertRaisesRegex(kern.AmwFehler, "nicht bereit"):
            urteil.entscheiden(self.con, self.pid, kern.ENTWICKLER, self.aid)
        with self.assertRaisesRegex(kern.AmwFehler, "meldet der Bearbeiter"):
            urteil.bereit_melden(self.con, self.pid, "CC2", self.aid)
        urteil.bereit_melden(self.con, self.pid, "CC1", self.aid)
        z = urteil.zur_abnahme(self.con, self.pid)
        self.assertEqual([(x["id"], x["grund_art"], x["grund_ref"], x["offen"]) for x in z], [(self.aid, "gemeldet", "CC1", ["liest sich gut"])])
        self.assertTrue(self.con.execute("SELECT 1 FROM nachricht WHERE kurz LIKE ?", (f"A{self.aid} bereit zur Abnahme%",)).fetchone())

    def test_bereit_durch_pruefung_oder_ergebnis(self):
        with db.schreiben(self.con):
            p = db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=self.aid, zweig="z", sha="c" * 40, bauer="CC1",
                             pruefer="TL", ergebnis="gruen", angefragt_utc="2099-01-01T00:00:00Z", ergebnis_utc="2099-01-01T00:00:00Z")
        self.assertEqual(urteil.grund(self.con, self.a()), f"P{p} grün")
        b = kern.aufgabe_neu(self.con, self.pid, "TL", "Bericht", "CC2")
        fertigquelle.setzen(self.con, self.pid, "TL", b, "ja")
        datei = os.path.join(self.ordner.name, "bericht.md")
        with open(datei, "w", encoding="utf-8") as f:
            f.write("# Bericht\n")
        d = dokumente.ablegen(self.con, self.pid, "CC2", datei, art="bericht", aufgabe=b)
        self.assertEqual({x["id"]: x["grund"] for x in urteil.zur_abnahme(self.con, self.pid)}, {self.aid: f"P{p} grün", b: f"D{d} abgelegt"})

    def test_bereit_nicht_ohne_urteil(self):
        b = kern.aufgabe_neu(self.con, self.pid, "TL", "Code", "CC2")
        fertigquelle.setzen(self.con, self.pid, "TL", b, "commit")
        with self.assertRaisesRegex(kern.AmwFehler, "schließt die AMW selbst"):
            urteil.bereit_melden(self.con, self.pid, "CC2", b)

    def test_ein_ja_genuegt(self):
        urteil.bereit_melden(self.con, self.pid, "CC1", self.aid)
        with self.assertRaisesRegex(kern.AmwFehler, "Mensch oder der Lead"):
            urteil.entscheiden(self.con, self.pid, "CC2", self.aid)
        self.assertEqual(urteil.entscheiden(self.con, self.pid, kern.ENTWICKLER, self.aid), "fertig")
        a = self.a()
        self.assertEqual((a["status"], a["beleg"]), ("fertig", "Ja von Entwickler · gemeldet von CC1"))
        self.assertIn("Abgenommen von dem Menschen (gemeldet von CC1). Kriterien 1/2.", a["zusammenfassung"])
        k = json.loads(a["kriterien"])
        self.assertEqual([(x["erfuellt"], x.get("beleg")) for x in k], [(True, "Ja von Entwickler"), (False, None)])   # Prüfquelle bleibt der AMW
        self.assertEqual(urteil.zur_abnahme(self.con, self.pid), [])
        self.assertTrue(self.con.execute("SELECT 1 FROM nachricht WHERE kurz = ?", (f"A{self.aid} abgenommen – fertig",)).fetchone())

    def test_bearbeiter_nimmt_nicht_selbst_ab(self):
        tl = kern.aufgabe_neu(self.con, self.pid, "TL", "Plan", "TL")
        fertigquelle.setzen(self.con, self.pid, "TL", tl, "ja")
        urteil.bereit_melden(self.con, self.pid, "TL", tl)
        with self.assertRaisesRegex(kern.AmwFehler, "eigene Aufgabe"):
            urteil.entscheiden(self.con, self.pid, "TL", tl)
        self.assertEqual(urteil.entscheiden(self.con, self.pid, kern.ENTWICKLER, tl), "fertig")

    def test_zurueck(self):
        urteil.bereit_melden(self.con, self.pid, "CC1", self.aid)
        with self.assertRaisesRegex(kern.AmwFehler, "nur mit Grund"):
            urteil.entscheiden(self.con, self.pid, "TL", self.aid, ja=False)
        self.assertEqual(urteil.entscheiden(self.con, self.pid, "TL", self.aid, ja=False, grund_text="Quellen fehlen"), "zurueck")
        self.assertEqual(urteil.zur_abnahme(self.con, self.pid), [])                            # bis zum nächsten Fakt
        self.assertEqual(self.a()["status"], "laeuft")
        self.assertTrue(self.con.execute("SELECT 1 FROM nachricht WHERE art = 'korrektur' AND text = 'Quellen fehlen'").fetchone())
        with db.schreiben(self.con):                                                               # später erneut gemeldet
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc="2099-01-01T00:00:00Z", von="CC1", art=urteil.BEREIT,
                         aufgabe_id=self.aid, text="")
        self.assertEqual(len(urteil.zur_abnahme(self.con, self.pid)), 1)

    def test_verweise_und_themen(self):
        tid = themen.neu(self.con, self.pid, "TL", "Marktlage", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", tid, "Text.")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, tid)
        datei = os.path.join(self.ordner.name, "konzept.md")
        with open(datei, "w", encoding="utf-8") as f:
            f.write("# Konzept\n")
        d = dokumente.ablegen(self.con, self.pid, "TL", datei, titel="Konzept AMW 2.0", art="ergebnis")
        v = urteil.verweise(self.con, self.pid, f"siehe TH{tid}, D{d} und TH99 (TH{tid} doppelt)")
        self.assertEqual([urteil.verweis_text(x) for x in v],
                         [f"TH{tid} Marktlage · freigegeben (Fassung 1)", f"D{d} Konzept AMW 2.0 · Fassung 1", "TH99 gibt es nicht"])
        self.assertEqual(urteil.bogen_themen(self.con, self.pid, self.bid), [])
        themen.verweise_setzen(self.con, self.pid, "TL", self.aid, [f"TH{tid}"])
        self.assertEqual(urteil.bogen_themen(self.con, self.pid, self.bid), [{"id": tid, "name": "Marktlage", "status": "frei", "aufgaben": [self.aid]}])

    def test_keine_spezifikation_mehr(self):
        self.assertFalse(planung.hat_spec(self.con, self.bid))
        with self.assertRaisesRegex(kern.AmwFehler, "keine Spezifikation – das Konzept steht in Themen"):
            planung.spec_schreiben(self.con, self.pid, "TL", self.bid, "anforderungen", "R1")
        planung.bogen_status(self.con, self.pid, "TL", self.bid, "aktiv")
        codes = {x["code"] for x in planung.pruefen(self.con, self.pid)}
        self.assertFalse(codes & {"aktiv_ohne_anforderungen", "anforderung_ungedeckt"})
        self.assertNotIn("aktiv_ohne_anforderungen", planung.CHECKS)

    def befehl(self, *args, von="TL"):
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Produkt", "--von", von, *args])
        return rc, aus.getvalue()

    def test_befehlszeile(self):
        rc, t = self.befehl("bogen", "neu", "--titel", "Zweiter")
        self.assertEqual(rc, 0, t)
        self.assertIn("Ziel und Abnahme dürfen auf Themen und Dokumente verweisen", t)
        self.assertNotIn("Spezifikation", t)
        rc, t = self.befehl("bogen", "zeigen", str(self.bid))
        self.assertIn("ziel: TH1 gibt es nicht", t)
        self.assertNotIn("Spezifikation", t)
        rc, t = self.befehl("aufgabe", "bereit", str(self.aid), von="CC1")
        self.assertIn("bereit zur Abnahme – steht unter „Für dich“", t)
        rc, t = self.befehl("aufgabe", "abnehmen", str(self.aid), "--zurueck", "--kommentar", "noch nicht")
        self.assertIn("zurück an den Bearbeiter", t)

    def test_workbench_und_knopf(self):
        urteil.bereit_melden(self.con, self.pid, "CC1", self.aid)
        self.assertEqual([x["id"] for x in workbench._aufgaben_zur_abnahme(self.con, self.pid)], [self.aid])
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.pid, "/api/aufgabe/abnehmen", {"aufgabe": self.aid}, kanal="netz")
        r = aktionen.ausfuehren(self.con, self.pid, "/api/aufgabe/abnehmen", {"aufgabe": self.aid, "ja": True})
        self.assertEqual(r["text"], "fertig")
        self.assertEqual(self.a()["status"], "fertig")


if __name__ == "__main__":
    unittest.main()
