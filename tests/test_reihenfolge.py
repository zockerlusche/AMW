"""A1941 (K5, TH164, #30233): Die AMW rechnet die Reihenfolge (kritischer Pfad vor Rang) aus Paketen, Abhängigkeiten, Größe und
gemessener Dauer; die Liste je Agent, das Verteilen und die Prognose folgen ihr; Handordnung nur mit Grund und bis sich die Liste
ändert; „Jetzt starten“ (amw bogen starten) übergibt die startklaren Pakete und merkt den Plan-Stand für die Abweichung."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitsliste, arbeitspaket, cli, db, fertigquelle, kern, planung, reihenfolge, themen, verteilen


class Reihenfolge(unittest.TestCase):
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
        self.bid = planung.bogen_neu(self.con, self.pid, "TL", "Lieferung 1")

    def paket(self, titel, agent="CC1", groesse=None, nach=None, bogen=True, **werte):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, agent)
        planung.schritt_setzen(self.con, self.pid, "TL", aid=aid, bogen_id=self.bid if bogen else None, groesse=groesse,
                               nach=nach, **werte)
        return aid

    def platz(self):
        return [z["aid"] for z in reihenfolge.berechnen(self.con, self.pid)]

    def test_dauer_gemessen_geschaetzt_vorgabe(self):
        a = {"art": "mechanisch", "groesse": "M", "schaetzung_h": 5}
        self.assertEqual(reihenfolge.dauer(a, {("einfach", "M"): (1.5, 4)}), (1.5, "gemessen (4)"))
        self.assertEqual(reihenfolge.dauer(a, {}), (5.0, "geschätzt"))
        self.assertEqual(reihenfolge.dauer(dict(a, schaetzung_h=None), {}), (3.0, "Vorgabe M"))
        self.assertEqual(reihenfolge.dauer({"art": None, "groesse": None, "schaetzung_h": None}, {}), (reihenfolge.OHNE_H, "ohne Größe"))
        with mock.patch("amw.eignung.zeilen", return_value=[{"zelle": ("einfach", "M"), "dauer_s": s} for s in (3600, 7200, 10800)]):
            self.assertEqual(reihenfolge._gemessen(self.con, self.pid), {("einfach", "M"): (2.0, 3)})
        with mock.patch("amw.eignung.zeilen", return_value=[{"zelle": ("einfach", "M"), "dauer_s": 3600}] * 2):
            self.assertEqual(reihenfolge._gemessen(self.con, self.pid), {})               # unter MIN_MESSUNGEN: Schätzung/Vorgabe

    def test_kritischer_pfad_vor_rang(self):
        einzeln = self.paket("Einzeln groß", groesse="L", rang=1)                      # 8 h, kleiner Rang
        a = self.paket("Kette 1", groesse="M", rang=50)                                 # 3 + 3 + 8 = 14 h Rest-Pfad
        b = self.paket("Kette 2", groesse="M", nach=[a], rang=50)
        c = self.paket("Kette 3", groesse="L", nach=[b], rang=50)
        z = {x["aid"]: x for x in reihenfolge.berechnen(self.con, self.pid)}
        self.assertEqual((z[a]["rest_h"], z[b]["rest_h"], z[c]["rest_h"], z[einzeln]["rest_h"]), (14.0, 11.0, 8.0, 8.0))
        self.assertEqual(self.platz()[:2], [a, einzeln])                                 # startklar: der längere Pfad zuerst
        self.assertEqual((z[b]["zustand"], z[c]["zustand"]), ("wartet", "wartet"))       # Vorgänger offen
        self.assertIn("Rest-Pfad 14 h", z[a]["grund"])
        gleich = self.paket("Gleich lang, Rang 2", groesse="L", rang=2)
        self.assertLess(self.platz().index(einzeln), self.platz().index(gleich))       # Gleichstand: der Rang entscheidet

    def test_meilenstein_und_zustand(self):
        ohne = self.paket("Ohne Meilenstein", groesse="XL", bogen=False)
        geplant = self.paket("Geplant", groesse="S")
        b2 = planung.bogen_neu(self.con, self.pid, "TL", "Lieferung 2")
        planung.bogen_status(self.con, self.pid, "TL", b2, "aktiv")
        aktiv = kern.aufgabe_neu(self.con, self.pid, "TL", "Aktiv", "CC2")
        planung.schritt_setzen(self.con, self.pid, "TL", aid=aktiv, bogen_id=b2, groesse="S")
        self.assertEqual(self.platz(), [aktiv, geplant, ohne])
        kern.aufgabe_status(self.con, self.pid, "CC1", geplant, "start")
        laeuft = self.paket("Läuft nicht", groesse="XL")
        self.assertEqual(self.platz()[1:3], [geplant, laeuft])                           # was läuft vor startklar

    def test_liste_folgt_und_handordnung_nur_mit_grund(self):
        klein = self.paket("Klein", groesse="S", rang=1)
        gross = self.paket("Groß", groesse="XL", rang=99)
        ids = lambda: [x["id"] for x in arbeitsliste.liste(self.con, self.pid, "CC1")]
        self.assertEqual(ids(), [gross, klein])                                          # berechnet, nicht nach Rang
        with self.assertRaisesRegex(kern.AmwFehler, "nur mit Grund"):
            arbeitsliste.ordnen(self.con, self.pid, "TL", "CC1", [klein])
        with self.assertRaisesRegex(kern.AmwFehler, "nur mit Grund"):
            arbeitsliste.schieben(self.con, self.pid, "TL", klein, oben=True)
        arbeitsliste.ordnen(self.con, self.pid, "TL", "CC1", [klein], "Kunde wartet auf Klein")
        l = arbeitsliste.liste(self.con, self.pid, "CC1")
        self.assertEqual(([x["id"] for x in l], l[0]["hand"]["grund"]), ([klein, gross], "Kunde wartet auf Klein"))
        arbeitsliste.schieben(self.con, self.pid, "TL", gross, oben=True)               # Verfeinerung: Grund bleibt
        self.assertEqual(ids(), [gross, klein])
        self.assertEqual(reihenfolge.hand_abgelaufen(self.con, self.pid), [])           # Liste unverändert
        neu = self.paket("Neu dazu", groesse="M")                                        # Liste ändert sich → AMW ordnet wieder
        self.assertIsNone(arbeitsliste.liste(self.con, self.pid, "CC1")[0]["hand"])
        self.assertEqual(ids(), [gross, neu, klein])
        self.assertEqual(reihenfolge.hand_abgelaufen(self.con, self.pid), ["Handordnung CC1 beendet"])
        self.assertEqual(reihenfolge.hand_abgelaufen(self.con, self.pid), [])           # einmal
        self.assertTrue(self.con.execute("SELECT 1 FROM nachricht WHERE kurz LIKE 'Liste CC1: Handordnung endet%'").fetchone())

    def test_verteilen_in_der_berechneten_reihenfolge(self):
        planung.bogen_status(self.con, self.pid, "TL", self.bid, "aktiv")
        klein = self.paket("Klein", agent=None, groesse="S", rang=1)
        gross = self.paket("Groß", agent=None, groesse="XL", rang=99)
        self.assertEqual([a["id"] for a, _ in verteilen.kandidaten(self.con, self.pid)], [gross, klein])

    def themen_und_quelle(self, aid, tid):
        themen.verweise_setzen(self.con, self.pid, "TL", aid, [f"TH{tid}"])
        fertigquelle.setzen(self.con, self.pid, "TL", aid, "commit")

    def test_jetzt_starten(self):
        tid = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        voll = self.paket("Voll geplant", groesse="M", auftrag="Login mit Firmenkonto.")
        self.themen_und_quelle(voll, tid)
        p = self.paket("p-Paket", agent=None, groesse="S", auftrag="Test schreiben.", pruefbefehl="python -m unittest tests.test_x",
                       dateibereich="amw/x.py")
        self.themen_und_quelle(p, tid)
        arbeitspaket.setzen(self.con, self.pid, "TL", p, art="p")
        luecke = self.paket("Lücke", groesse="S")                                         # ohne Ziel, Thema, Fertig-Quelle
        with self.assertRaisesRegex(kern.AmwFehler, "Lead oder der Mensch"):
            reihenfolge.starten(self.con, self.pid, "CC1", self.bid)
        r = reihenfolge.starten(self.con, self.pid, kern.ENTWICKLER, self.bid)            # der Mensch startet – der Lead erfährt es
        self.assertEqual((sorted(r["startklar"]), r["fehlt"]), (sorted([voll, p]), {luecke: ["Ziel (Auftrag)", "Thema", "Fertig-Quelle"]}))
        self.assertEqual(planung.bogen_zeile(self.con, self.pid, self.bid)["status"], "aktiv")
        self.assertEqual(arbeitspaket.lesen(self.con, p)["zustand"], "startklar")
        stand = self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'plan_stand' AND bogen_id = ?", (self.bid,)).fetchone()
        self.assertIn(str(voll), json.loads(stand[0])["pakete"])
        ab = reihenfolge.abweichung(self.con, self.pid, self.bid)
        self.assertEqual((ab["bogen"], ab["pakete"].get(voll)), (0, 0))                   # gleich nach dem Start: keine Abweichung
        self.assertIsNone(reihenfolge.abweichung(self.con, self.pid, planung.bogen_neu(self.con, self.pid, "TL", "Ohne Start")))
        info = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE 'Meilenstein % gestartet%'").fetchone()[0]
        self.assertIn(f"Noch nicht startklar: A{luecke}: Ziel (Auftrag), Thema, Fertig-Quelle", info)
        self.assertIn("Reihenfolge (die AMW rechnet sie)", info)

    def test_befehlszeile(self):
        a = self.paket("Kette 1", groesse="M")
        self.paket("Kette 2", groesse="M", nach=[a])
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            self.assertEqual(cli.main(["--projekt", "Produkt", "--von", "TL", "bogen", "reihenfolge", str(self.bid)]), 0)
            rc = cli.main(["--projekt", "Produkt", "--von", "TL", "liste", "ordnen", "CC1", f"A{a}"])
            self.assertEqual(cli.main(["--projekt", "Produkt", "--von", "TL", "bogen", "starten", str(self.bid)]), 0)
        t = aus.getvalue()
        self.assertIn(f"  1. A{a}", t)
        self.assertIn("Rest-Pfad 6 h", t)
        self.assertNotEqual(rc, 0)
        self.assertIn("nur mit Grund", t)
        self.assertIn(f"Meilenstein {self.bid} gestartet – 0 Pakete startklar", t)
        self.assertIn("noch nicht startklar: A", t)


if __name__ == "__main__":
    unittest.main()
