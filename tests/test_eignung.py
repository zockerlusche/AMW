"""A1930 (TH159, #29978): Eignungstabelle je Modell/Effort × Zelle – gemessen aus Ereignissen (p-Pakete: Entscheidungen und
Kosten; interaktiv: Sitzungen, rote Prüfungen), „ohne Nacharbeit“ nach F5362 A, Regel „gemessen ersetzt Startwert“ ab n ≥ 5,
Fable nie, ein gesetzter Projektwert geht vor; amw empfehlung tabelle."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import unittest

from amw import arbeitspaket, db, eignung, empfehlung, kern
from tests import test_empfehlung as te


def zeile(paar, ohne, usd, zelle=("einfach", "S"), typ="normal"):
    return {"aufgabe": 0, "quelle": "p", "zelle": zelle, "paar": paar, "pakettyp": typ, "usd": usd, "dauer_s": 60.0, "ohne": ohne}


class Regeln(unittest.TestCase):
    def test_ohne_nacharbeit_nach_f5362(self):
        f = eignung.ohne_nacharbeit_p
        self.assertIsNone(f([], "normal"))
        self.assertTrue(f([("E7", "grün")], "normal"))
        self.assertTrue(f([("E4", "C/diff"), ("E7", "lead_nach_e4")], "test-ergaenzen"))      # Lesen + Annehmen ohne Änderung
        self.assertFalse(f([("E4", "C/diff"), ("E7", "lead_nach_e4")], "normal"))
        self.assertFalse(f([("E5", "C/rot"), ("E7", "grün")], "normal"))                     # zweiter Lauf
        self.assertFalse(f([("E8", "Konflikt")], "normal"))                                  # an einen interaktiven Agenten
        self.assertFalse(f([("E1", "Starter weg")], "normal"))

    def test_kurzname(self):
        self.assertEqual([eignung.kurz(m) for m in ("claude-opus-5-5", "Sonnet 5.5", "haiku", "minimax@MiniMax-M2", None)],
                         ["opus", "sonnet", "haiku", "minimax@minimax-m2", "?"])

    def test_tabelle_und_beste(self):
        zs = [zeile("haiku/low", True, 0.2) for _ in range(5)] + [zeile("sonnet/medium", i < 4, 1.0) for i in range(5)] \
            + [zeile("opus/high", True, 3.0) for _ in range(4)] + [zeile("fable/high", True, 0.1) for _ in range(9)]
        t = eignung.tabelle(None, None, zs)[("einfach", "S")]
        self.assertEqual((t["haiku/low"]["n"], t["haiku/low"]["ohne_anteil"], t["haiku/low"]["kosten_median"]), (5, 1.0, 0.2))
        self.assertEqual(t["sonnet/medium"]["ohne_anteil"], 0.8)
        self.assertEqual(eignung.beste(t, "sonnet/medium"), "haiku/low")                       # opus n 4 zählt nicht, fable nie
        gleich = {"a/low": {"n": 5, "ohne_anteil": 1.0, "kosten_median": 2.0}, "b/low": {"n": 6, "ohne_anteil": 1.0, "kosten_median": 1.0}}
        self.assertEqual(eignung.beste(gleich, "x/y"), "b/low")                                  # Gleichstand: billiger
        start_besser = {"neu/low": {"n": 5, "ohne_anteil": 0.8, "kosten_median": 0.1},
                        "alt/high": {"n": 5, "ohne_anteil": 0.6, "kosten_median": 1.0}}
        self.assertEqual(eignung.beste(start_besser, "alt/high"), "neu/low")
        self.assertIsNone(eignung.beste({"neu/low": {"n": 4, "ohne_anteil": 1.0, "kosten_median": 0.1}}, "alt/high"))
        self.assertIsNone(eignung.beste({"alt/high": {"n": 5, "ohne_anteil": 1.0, "kosten_median": 1.0}}, "alt/high"))
        self.assertEqual(eignung.tabelle(None, None, zs)[("einfach", "S")]["sonnet/medium"]["pakettypen"], {"normal": 5})


class Gemessen(unittest.TestCase):
    setUp, fertig, sitzung, cli = te.Empfehlung.setUp, te.Empfehlung.fertig, te.Empfehlung.sitzung, te.Empfehlung.cli

    def fuenf(self, n=5):
        sid = self.sitzung()
        return [self.fertig("S", "text", te.z(8 + i), te.z(8 + i, 30), float(i), float(i) + 1.0, sid) for i in range(n)]

    def test_interaktiv_ab_fuenf_ersetzt_den_startwert(self):
        self.fuenf(4)
        self.assertEqual(empfehlung.herkunft(self.con, self.pid)["einfach"]["S"], ("sonnet/medium", "start"))
        sid = self.sitzung()
        self.fertig("S", "mechanisch", te.z(14), te.z(14, 30), 10.0, 11.0, sid)               # gleiche Zelle (einfach · S)
        t = eignung.tabelle(self.con, self.pid)[("einfach", "S")]["opus/high"]
        self.assertEqual((t["n"], t["ohne_anteil"], t["kosten_median"], t["pakettypen"]), (5, 1.0, 1.0, {"interaktiv": 5}))
        self.assertEqual(empfehlung.herkunft(self.con, self.pid)["einfach"]["S"], ("opus/high", "gemessen"))
        self.assertEqual(empfehlung.tabelle(self.con, self.pid)["einfach"]["S"], "opus/high")
        self.assertEqual(empfehlung.tabelle(self.con, self.pid, gemessen=False)["einfach"]["S"], "sonnet/medium")
        kern.projekt_einstellen(self.con, self.pid, "TL", empfehlung={"einfach": {"S": "haiku/low"}})   # gesetzt geht vor
        self.assertEqual(empfehlung.herkunft(self.con, self.pid)["einfach"]["S"], ("haiku/low", "projekt"))

    def test_rot_ist_nacharbeit(self):
        sid = self.sitzung()
        a = self.fertig("M", "fehlersuche", te.z(8), te.z(9), 0.0, 2.0, sid, rot=True)
        z = [x for x in eignung.zeilen(self.con, self.pid) if x["aufgabe"] == a][0]
        self.assertEqual((z["quelle"], z["zelle"], z["paar"], z["ohne"]), ("interaktiv", ("mittel", "M"), "opus/high", False))

    def test_p_paket(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Paket", "TL")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET groesse = 'S', art = 'text' WHERE id = ?", (aid,))
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p", modell="sonnet", effort="medium")
        offen = kern.aufgabe_neu(self.con, self.pid, "TL", "noch offen", "TL")
        arbeitspaket.setzen(self.con, self.pid, "TL", offen, art="p")
        with db.schreiben(self.con):
            for art, text in (("paket_entscheidung", {"zeile": "E7", "code": "grün"}), ("kosten", {"usd": 0.4, "dauer_s": 120})):
                db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art=art, aufgabe_id=aid,
                             text=json.dumps(text))
        zs = {x["aufgabe"]: x for x in eignung.zeilen(self.con, self.pid)}
        self.assertNotIn(offen, zs)                                                            # ohne Entscheidung zählt es nicht
        self.assertEqual({k: zs[aid][k] for k in ("quelle", "zelle", "paar", "pakettyp", "usd", "dauer_s", "ohne")},
                         {"quelle": "p", "zelle": ("einfach", "S"), "paar": "sonnet/medium", "pakettyp": "normal", "usd": 0.4,
                          "dauer_s": 120.0, "ohne": True})

    def test_spanne_p50_p85_ab_fuenf_messungen(self):                                       # A1955 (TH165)
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Paket", "TL")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET groesse = 'S', art = 'text' WHERE id = ?", (aid,))
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p", modell="claude-sonnet-5-5", effort="medium")
        zs = [dict(zeile("sonnet/medium", True, u), dauer_s=s) for u, s in ((1.0, 600), (2.0, 900), (3.0, 1200), (4.0, 1500))]
        tab = eignung.tabelle(None, None, zs)
        self.assertIsNone(eignung.spanne(self.con, self.pid, aid, tab))                         # unter MIN_N: keine Spanne
        zs.append(dict(zeile("sonnet/medium", True, 5.0), dauer_s=1800))
        sp = eignung.spanne(self.con, self.pid, aid, eignung.tabelle(None, None, zs))
        self.assertEqual(sp, {"n": 5, "kosten": (3.0, 4.4), "dauer_s": (1200.0, 1620.0)})
        self.assertEqual(eignung.spanne_text(sp), "Gemessen (5, P50–P85): Dauer 20–27 min · Kosten 3.00–4.40 $")
        self.assertEqual(eignung.spanne_text(sp, "en"), "Measured (5, P50–P85): time 20–27 min · cost 3.00–4.40 $")
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, modell="claude-opus-5-5")             # anderes Modell: andere Messungen
        self.assertIsNone(eignung.spanne(self.con, self.pid, aid, eignung.tabelle(None, None, zs)))

    def test_befehl_tabelle(self):
        self.fuenf()
        rc, aus = self.cli("empfehlung", "tabelle", "--von", "TL", "--projekt", "Eins")
        self.assertEqual(rc, 0, aus)
        self.assertIn("einfach · S: Empfehlung opus/high (gemessen)", aus)
        self.assertRegex(aus, r"→ opus/high +n 5 +ohne Nacharbeit 100 % · Median 1\.00 \$")
        self.assertIn("heikel · XL: Empfehlung opus/high (Startwert)", aus)


if __name__ == "__main__":
    unittest.main()
