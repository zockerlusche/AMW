"""Arbeitspakete (A1845, D1258 v4 §3/§4): Felder mit Standardwerten, Zustandsautomat nur für Art p (erlaubte und verbotene
Übergänge), Spiegelung auf den Status der Aufgabe; Art agent hat keinen Automaten."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket as ap, db, kern


class Felder(unittest.TestCase):
    def test_standard_ohne_zeile_ist_agent(self):
        f = ap.mit_standard(None)
        self.assertEqual((f["art"], f["gewicht"], f["modell"], f["effort"], f["pakettyp"], f["ressourcen"], f["zustand"]),
                         ("agent", "leicht", "claude-opus-5-5", "high", "normal", [], None))
        self.assertEqual(f["standard"], sorted(ap.STANDARD))

    def test_art_p_beginnt_als_entwurf(self):
        f = ap.mit_standard({"art": "p", "effort": "medium"})
        self.assertEqual((f["zustand"], f["effort"]), ("entwurf", "medium"))
        self.assertNotIn("effort", f["standard"])

    def test_pruefen_vereinheitlicht_und_lehnt_ab(self):
        self.assertEqual(ap.felder_pruefen({"ressourcen": "GPU, bildschirm,gpu", "nie_gleichzeitig": "A12, 7;a12"}),
                         {"ressourcen": ["bildschirm", "gpu"], "nie_gleichzeitig": [7, 12]})
        for falsch in ({"art": "q"}, {"gewicht": "mittel"}, {"effort": "max"}, {"pakettyp": "x"}, {"ressourcen": "drucker"},
                       {"nie_gleichzeitig": "B3"}, {"modell": " "}, {"farbe": "rot"}):
            with self.assertRaises(ap.Ungueltig, msg=falsch):
                ap.felder_pruefen(falsch)

    def test_warnungen_nur_bei_p(self):
        self.assertEqual(ap.warnungen(ap.mit_standard(None), None, None), [])
        w = ap.warnungen(ap.mit_standard({"art": "p", "ressourcen": ["gpu"]}), "", None)
        self.assertEqual(len(w), 3)
        self.assertEqual(ap.warnungen(ap.mit_standard({"art": "p"}), "python -m unittest tests.test_x", "amw/x.py"), [])


class Automat(unittest.TestCase):
    def test_hauptweg_geht_durch(self):
        for alt, neu in zip(ap.HAUPTWEG, ap.HAUPTWEG[1:]):
            ap.uebergang_pruefen(alt, neu)

    def test_verbotene_uebergaenge(self):
        for alt, neu in (("entwurf", "laeuft"), ("laeuft", "fertig"), ("abgegeben", "merge_reihe"), ("startklar", "abgegeben"),
                         ("fertig", "entwurf"), ("wartet_interaktiv", "laeuft"), ("gemergt", "laeuft"), ("laeuft", "laeuft")):
            with self.assertRaises(ap.Ungueltig, msg=f"{alt} → {neu}"):
                ap.uebergang_pruefen(alt, neu)
        with self.assertRaisesRegex(ap.Ungueltig, "unbekannter Zustand"):
            ap.uebergang_pruefen("entwurf", "irgendwas")

    def test_jeder_zustand_erreichbar_und_fertig_ist_ende(self):
        self.assertEqual(set(ap.UEBERGAENGE), set(ap.ZUSTAENDE))
        self.assertTrue(all(z in ap.ZUSTAENDE for ziele in ap.UEBERGAENGE.values() for z in ziele))
        erreicht, offen = {ap.START}, [ap.START]
        while offen:
            for z in ap.UEBERGAENGE[offen.pop()]:
                if z not in erreicht:
                    erreicht.add(z)
                    offen.append(z)
        self.assertEqual(erreicht, set(ap.ZUSTAENDE))
        self.assertEqual(ap.UEBERGAENGE["fertig"], set())
        for z in ap.ZUSTAENDE:                                          # aus jedem Nicht-Endzustand kommt man wieder weg
            self.assertTrue(z == "fertig" or ap.UEBERGAENGE[z], z)

    def test_rueckwege_nach_konzept(self):
        ap.uebergang_pruefen("abnahme", "laeuft")                       # Abnahme rot: einmal zurück an den Arbeiter (§7)
        ap.uebergang_pruefen("merge_reihe", "laeuft")                   # Merge-Konflikt: Resume mit Fehlerausgabe
        ap.uebergang_pruefen("blockiert", "wartet_interaktiv")          # Stufe 1: Frage → wartet auf interaktiv

    def test_spiegel_auf_den_aufgabenstatus(self):
        erwartet = {"entwurf": "wartet", "startklar": "wartet", "laeuft": "laeuft", "abgegeben": "wartet", "abnahme": "wartet",
                    "merge_reihe": "wartet", "gemergt": "wartet", "fertig": "fertig", "blockiert": "blockiert", "unklar": "blockiert",
                    "wartet_interaktiv": "blockiert", "abgebrochen": "blockiert", "zurueckgestellt": "wartet"}
        self.assertEqual({z: ap.spiegel(z) for z in ap.ZUSTAENDE}, erwartet)
        self.assertTrue(set(erwartet.values()) <= {"wartet", "laeuft", "blockiert", "fertig"})   # passt in aufgabe.status

    def test_art_wechsel_nur_ohne_arbeiter(self):
        ap.art_wechsel_pruefen("p", "agent", "wartet_interaktiv")       # hochgestuft an einen interaktiven Agenten
        with self.assertRaises(ap.Ungueltig):
            ap.art_wechsel_pruefen("p", "agent", "laeuft")
        ap.art_wechsel_pruefen("agent", "p", None)


class _Datenbank(unittest.TestCase):
    """Gegen die Tabelle paket (Schema 33)."""
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Eins", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Kleines Paket", agent="CC1")
        self.andere = kern.aufgabe_neu(self.con, self.pid, "TL", "Anderes", agent="CC1")

    def status(self):
        return self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (self.aid,)).fetchone()[0]


class Speicher(_Datenbank):
    def test_ohne_zeile_agent_und_heutiger_status(self):
        self.assertEqual(ap.lesen(self.con, self.aid)["art"], "agent")
        with self.assertRaisesRegex(kern.AmwFehler, "nur bei Art p"):
            ap.zustand_setzen(self.con, self.pid, "TL", self.aid, "startklar")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.aid, "start")          # Art agent: wie bisher
        self.assertEqual(self.status(), "laeuft")

    def test_nur_lead_oder_mensch_setzt_felder(self):
        with self.assertRaisesRegex(kern.AmwFehler, "Lead"):
            ap.setzen(self.con, self.pid, "CC1", self.aid, art="p")
        f, w = ap.setzen(self.con, self.pid, "TL", self.aid, art="p", effort="medium", nie_gleichzeitig=f"A{self.andere}")
        self.assertEqual((f["art"], f["zustand"], f["effort"], f["nie_gleichzeitig"], f["modell"]),
                         ("p", "entwurf", "medium", [self.andere], "claude-opus-5-5"))
        self.assertEqual(len(w), 2)                                                # ohne Abnahme-Befehl und Bereiche
        with self.assertRaisesRegex(kern.AmwFehler, "gibt es nicht"):
            ap.setzen(self.con, self.pid, "TL", self.aid, nie_gleichzeitig="A99999")
        with self.assertRaisesRegex(kern.AmwFehler, "Effort"):
            ap.setzen(self.con, self.pid, kern.ENTWICKLER, self.aid, effort="max")

    def test_automat_spiegelt_und_protokolliert(self):
        ap.setzen(self.con, self.pid, "TL", self.aid, art="p")
        for z, s in (("startklar", "wartet"), ("laeuft", "laeuft"), ("abgegeben", "wartet"), ("abnahme", "wartet"),
                     ("laeuft", "laeuft"), ("abgegeben", "wartet"), ("abnahme", "wartet"), ("merge_reihe", "wartet"),
                     ("gemergt", "wartet")):
            self.assertEqual(ap.zustand_setzen(self.con, self.pid, "AMW", self.aid, z)[2], s)
            self.assertEqual(self.status(), s)
        with self.assertRaisesRegex(kern.AmwFehler, "Beleg"):
            ap.zustand_setzen(self.con, self.pid, "AMW", self.aid, "fertig")
        ap.zustand_setzen(self.con, self.pid, "AMW", self.aid, "fertig", beleg="abc1234")
        a = self.con.execute("SELECT status, beleg, begonnen_utc, fertig_utc FROM aufgabe WHERE id = ?", (self.aid,)).fetchone()
        self.assertEqual((a[0], a[1]), ("fertig", "abc1234"))
        self.assertTrue(a[2] and a[3])
        v = ap.verlauf(self.con, self.aid)
        self.assertEqual([(x[1], x[2]) for x in v[:3]], [(None, "entwurf"), ("entwurf", "startklar"), ("startklar", "laeuft")])
        self.assertEqual(v[-1][2], "fertig")

    def test_verbotener_uebergang_aendert_nichts(self):
        ap.setzen(self.con, self.pid, "TL", self.aid, art="p")
        with self.assertRaisesRegex(kern.AmwFehler, "geht nicht"):
            ap.zustand_setzen(self.con, self.pid, "AMW", self.aid, "laeuft")
        self.assertEqual((ap.lesen(self.con, self.aid)["zustand"], self.status()), ("entwurf", "wartet"))
        with self.assertRaisesRegex(kern.AmwFehler, "setzt die AMW"):
            ap.zustand_setzen(self.con, self.pid, "CC1", self.aid, "startklar")

    def test_blockiert_und_zurueck_an_einen_agenten(self):
        ap.setzen(self.con, self.pid, "TL", self.aid, art="p")
        for z in ("startklar", "laeuft", "blockiert"):
            ap.zustand_setzen(self.con, self.pid, "AMW", self.aid, z, grund="Frage F1" if z == "blockiert" else None)
        self.assertEqual(self.status(), "blockiert")
        ap.zustand_setzen(self.con, self.pid, "AMW", self.aid, "wartet_interaktiv")
        f, _ = ap.setzen(self.con, self.pid, "TL", self.aid, art="agent")             # hochgestuft: ein Agent übernimmt
        self.assertEqual((f["art"], f["zustand"]), ("agent", None))
        self.assertEqual(ap.verlauf(self.con, self.aid)[-1][1:], ("wartet_interaktiv", None, "Art agent"))

    def test_art_p_weg_nur_ohne_arbeiter(self):
        ap.setzen(self.con, self.pid, "TL", self.aid, art="p")
        ap.zustand_setzen(self.con, self.pid, "AMW", self.aid, "startklar")
        ap.zustand_setzen(self.con, self.pid, "AMW", self.aid, "laeuft")
        with self.assertRaisesRegex(kern.AmwFehler, "solange"):
            ap.setzen(self.con, self.pid, "TL", self.aid, art="agent")


class Befehle(_Datenbank):
    def cli(self, *args):
        from amw import cli
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")}),                 contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main([*args, "--projekt", "Eins"])
        return rc, aus.getvalue()

    def test_felder_per_aufgabe_aendern_und_zeigen(self):
        rc, aus = self.cli("aufgabe", "aendern", str(self.aid), "--paket", "p", "--effort", "medium", "--ressourcen", "gpu",
                           "--nie-gleichzeitig", f"A{self.andere}", "--pruefbefehl", "python -m unittest tests.test_x", "--von", "TL")
        self.assertEqual(rc, 0, aus)
        self.assertIn("Paket p · Entwurf", aus)
        self.assertIn("ohne Bereiche", aus)                                       # Warnung, kein Fehler
        self.assertIn("Gewicht schwer oder Ressourcen", aus)
        rc, aus = self.cli("paket", "zeigen", str(self.aid), "--von", "TL")
        self.assertEqual(rc, 0, aus)
        for teil in ("Art: p", "Zustand: Entwurf", "Abnahme-Befehl: python -m unittest tests.test_x", "Ressourcen: gpu",
                     "Modell: claude-opus-5-5 (Vorgabe)", "Effort: medium", f"nie gleichzeitig mit: A{self.andere}", "– → Entwurf"):
            self.assertIn(teil, aus)

    def test_neu_mit_paket_und_zustand_und_liste(self):
        rc, aus = self.cli("aufgabe", "neu", "--titel", "Ein p-Paket", "--paket", "p", "--dateien", "amw/x.py",
                           "--pruefbefehl", "python -m unittest tests.test_x", "--ohne-bogen", "--von", "TL")
        self.assertEqual(rc, 0, aus)
        aid = int(aus.split("A", 1)[1].split()[0])
        self.assertNotIn("Achtung", aus)
        rc, aus = self.cli("paket", "zustand", str(aid), "laeuft", "--von", "TL")
        self.assertNotEqual(rc, 0)
        self.assertIn("geht nicht", aus)
        rc, aus = self.cli("paket", "zustand", str(aid), "startklar", "--grund", "Lead", "--von", "TL")
        self.assertEqual(rc, 0, aus)
        self.assertIn("Entwurf → startklar (Aufgabe: wartet)", aus)
        rc, aus = self.cli("paket", "liste", "--nur", "startklar", "--von", "TL")
        self.assertIn(f"A{aid}", aus)
        self.assertNotIn(f"A{self.aid} ", aus)
        rc, aus = self.cli("aufgabe", "aendern", str(aid), "--paket", "p", "--von", "CC1")
        self.assertNotEqual(rc, 0)
        self.assertIn("Lead", aus)


    def test_mcp_hat_dieselben_felder(self):
        from amw import mcp_server
        self.assertEqual(mcp_server.befehlszeile("aufgabe_neu", {"titel": "X", "paket": "p", "pruefbefehl": "python -m unittest t",
                                                                 "nie_gleichzeitig": "A12", "effort": "low"}),
                         ["aufgabe", "neu", "--titel", "X", "--paket", "p", "--pruefbefehl", "python -m unittest t", "--effort", "low",
                          "--nie-gleichzeitig", "A12"])
        self.assertEqual(mcp_server.befehlszeile("paket_zustand", {"id": self.aid, "zustand": "startklar"}),
                         ["paket", "zustand", str(self.aid), "startklar"])


class Migration(unittest.TestCase):
    def test_33_fuegt_nur_hinzu(self):
        """Schema 32 → 33: Tabelle paket kommt dazu, bestehende Aufgaben bleiben unverändert und sind Art agent."""
        ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(ordner.cleanup)
        pfad = os.path.join(ordner.name, "amw.db")
        con = db.anlegen(pfad)
        with db.schreiben(con):
            pid = db.einfuegen(con, "projekt", name="Eins", angelegt_utc=db.jetzt())
        kern.agent_neu(con, pid, "TL", rolle="lead")
        aid = kern.aufgabe_neu(con, pid, "TL", "Alt", agent="TL")
        vorher = tuple(con.execute("SELECT * FROM aufgabe WHERE id = ?", (aid,)).fetchone())
        con.execute("DROP TABLE paket")
        con.execute("PRAGMA user_version = 32")
        con.close()
        con = db.verbinde(pfad)
        self.addCleanup(con.close)
        self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], 33)
        self.assertEqual(tuple(con.execute("SELECT * FROM aufgabe WHERE id = ?", (aid,)).fetchone()), vorher)
        self.assertEqual(con.execute("SELECT count(*) FROM paket").fetchone()[0], 0)
        self.assertEqual(ap.lesen(con, aid)["art"], "agent")


if __name__ == "__main__":
    unittest.main()
