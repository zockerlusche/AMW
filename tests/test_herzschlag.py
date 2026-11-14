"""Herzschlag je Strang, Aufpasser und Gesundheit (A1655): ein hängender Faden wird ersetzt, die anderen laufen weiter; einmal
je Vorfall eine Meldung; die Hauptschleife kann der Aufpasser nicht ersetzen; Gesundheit auch aus der Datei."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import threading
import time
import unittest
from unittest import mock

from amw import herzschlag


class Herzschlag(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        herzschlag._zuruecksetzen()
        self.addCleanup(herzschlag._zuruecksetzen)
        self.stops = []
        self.addCleanup(lambda: [s.set() for s in self.stops])

    def test_zustand_gruen_gelb_rot(self):
        herzschlag.schlag("dateiaustausch", 0.2)
        e, jetzt = dict(herzschlag._stand["dateiaustausch"]), time.time()
        self.assertEqual(herzschlag.zustand("dateiaustausch", e, jetzt), "gruen")
        self.assertEqual(herzschlag.zustand("dateiaustausch", e, jetzt + 301), "gelb")    # älter als die Grenze (300 s)
        self.assertEqual(herzschlag.zustand("dateiaustausch", e, jetzt + 901), "rot")     # älter als 3× die Grenze
        herzschlag.schlag("dateiaustausch", 0.1, ValueError("kaputt"))
        e = dict(herzschlag._stand["dateiaustausch"])
        self.assertEqual(herzschlag.zustand("dateiaustausch", e, time.time()), "gelb")     # letzte Runde mit Fehler
        self.assertIn("ValueError: kaputt", e["fehler"])
        self.assertEqual(herzschlag.zustand("ki", None, jetzt), "aus")

    def test_haengender_faden_wird_ersetzt_die_anderen_laufen_weiter(self):
        aufrufe, haengt = [], threading.Event()

        def bruecke(stop):                              # erster Durchlauf hängt ohne Herzschlag, der zweite schlägt
            aufrufe.append(stop)
            self.stops.append(stop)
            if len(aufrufe) == 1:
                haengt.wait(30)
                return
            while not stop.is_set():
                herzschlag.schlag("dateiaustausch", 0.01)
                stop.wait(0.05)

        def ki(stop):
            self.stops.append(stop)
            while not stop.is_set():
                herzschlag.schlag("ki", 0.01)
                stop.wait(0.05)
        self.addCleanup(haengt.set)
        herzschlag.strang("dateiaustausch", bruecke)
        herzschlag.strang("ki", ki)
        time.sleep(0.2)
        meldungen = []
        spaeter = time.time() + 301                     # 301 s ohne Herzschlag vom Dateiaustausch – der KI-Faden schlägt weiter
        with mock.patch.dict(herzschlag._stand["ki"], {"zeit": spaeter}):
            ereignisse = herzschlag.aufpassen(melden=lambda text, teil=None: meldungen.append(text), jetzt=spaeter)
        self.assertEqual(len(ereignisse), 1)
        self.assertIn("Dateiaustausch war 301 s still", ereignisse[0])
        self.assertEqual(len(aufrufe), 2)                # neue Instanz gestartet …
        self.assertTrue(aufrufe[0].is_set())            # … die alte hat ihr Stop-Zeichen
        self.assertEqual(herzschlag._stand["dateiaustausch"]["neustarts"], 1)
        self.assertEqual(herzschlag._stand["ki"].get("neustarts", 0), 0)     # die anderen bleiben unberührt
        time.sleep(0.2)
        self.assertEqual(herzschlag.zustand("dateiaustausch", dict(herzschlag._stand["dateiaustausch"]), time.time()), "gelb")   # neu gestartet
        self.assertEqual(len(meldungen), 1)
        herzschlag.aufpassen(melden=lambda text, teil=None: meldungen.append(text), jetzt=time.time() + 400)   # derselbe Vorfall … (hängt weiter in der Probe)
        self.assertEqual(len(meldungen), 1)                                     # … wird nicht noch einmal gemeldet

    def test_ki_arbeiter_wird_nie_ersetzt_und_lebenszeichen_zaehlen(self):
        """Ein zweiter KI-Arbeiter nähme den laufenden Auftrag noch einmal – darum nur Meldung. Ein Lebenszeichen mitten in der
        Runde (je Befehlsdatei, während ein Auftrag rechnet) ist kein Stillstand."""
        aufrufe = []

        def ki(stop):
            aufrufe.append(stop)
            self.stops.append(stop)
            stop.wait(30)
        herzschlag.strang("ki", ki, ersetzbar=False)
        meldungen = []
        herzschlag.aufpassen(melden=lambda text, teil=None: meldungen.append(text), jetzt=time.time() + 1801)
        self.assertEqual(len(aufrufe), 1)                                    # kein zweiter Arbeiter
        self.assertIn("kann nur ein Neustart des Dienstes beheben", meldungen[0])
        herzschlag._zuruecksetzen()
        herzschlag.schlag("dateiaustausch", 0.1)
        herzschlag._stand["dateiaustausch"]["zeit"] -= 290
        herzschlag.lebt("dateiaustausch")                                    # Runde mit vielen Dateien: lebt noch
        self.assertEqual(herzschlag.aufpassen(jetzt=time.time() + 100), [])
        self.assertEqual(herzschlag._stand["dateiaustausch"]["runden"], 1)   # zählt nicht als Runde

    def test_online_zaehlt_nur_die_farbe(self):
        """Die Betrieb-Ansicht online wird nicht bei jeder Runde neu hochgeladen – nur wenn sich eine Farbe oder die Zahl der
        Neustarts ändert (abgleich._ruhig)."""
        from amw import abgleich
        herzschlag.schlag("hauptschleife", 0.1)
        jetzt = time.time()
        a = abgleich._ruhig({"gesundheit": herzschlag.gesundheit(jetzt=jetzt)})
        herzschlag.schlag("hauptschleife", 0.7)                              # neue Runde, andere Dauer
        self.assertEqual(abgleich._ruhig({"gesundheit": herzschlag.gesundheit(jetzt=jetzt + 5)}), a)
        self.assertNotEqual(abgleich._ruhig({"gesundheit": herzschlag.gesundheit(jetzt=jetzt + 200)}), a)   # jetzt gelb

    def test_meldung_ins_projekt_amw_und_push_wenn_die_hauptschleife_steht(self):
        """TL P152: Dienst-Meldungen sind PC-weit → Projekt AMW (nicht das erste Projekt); steht die Hauptschleife, verschickt
        niemand mehr Pushs – dann schickt der Aufpasser ihn selbst."""
        from amw import db, dienst, kern, push
        con = db.anlegen()
        self.addCleanup(con.close)
        with db.schreiben(con):
            fremd = db.einfuegen(con, "projekt", name="Anderes", angelegt_utc=db.jetzt())
            amw = db.einfuegen(con, "projekt", name="AMW", angelegt_utc=db.jetzt())
        self.assertEqual(dienst.dienst_projekt(con), amw)
        gesendet = []
        cfg = {"an": True}
        with mock.patch.object(push, "laden", lambda: cfg), \
                mock.patch.object(push, "senden", lambda c, titel, text, prio, link: gesendet.append((titel, prio)) or {"ntfy": None}), \
                mock.patch.object(push, "_link", lambda c, sicht: sicht):
            dienst.aufpasser_melden("Dateiaustausch war 400 s still", "dateiaustausch")
            self.assertEqual(gesendet, [])                                   # das schickt die Hauptschleife selbst
            dienst.aufpasser_melden("Hauptschleife ist 200 s still", "hauptschleife")
        self.assertEqual(gesendet, [("AMW: Dienst steht", 5)])
        zeilen = con.execute("SELECT projekt_id FROM nachricht WHERE kurz LIKE 'Dienst:%'").fetchall()
        self.assertEqual({r[0] for r in zeilen}, {amw})
        self.assertNotIn(fremd, {r[0] for r in zeilen})
        self.assertTrue(kern.ENTWICKLER)

    def test_beim_ersetzen_steht_da_wo_der_faden_hing(self):
        """A1648: die Ursache eines Stillstands – die Aufrufkette des alten Fadens geht ins Protokoll, die letzte Stelle in die
        Meldung und unter Betrieb › Dienst."""
        haengt = threading.Event()
        self.addCleanup(haengt.set)

        def wartet_auf_freigabe_im_netzlaufwerk():           # ein sprechender Name – genau der soll in der Meldung stehen
            haengt.wait(30)

        def bruecke(stop):
            self.stops.append(stop)
            wartet_auf_freigabe_im_netzlaufwerk()
        herzschlag.strang("dateiaustausch", bruecke)
        time.sleep(0.2)
        meldungen = []
        with self.assertLogs("amw.herzschlag", level="WARNING") as protokoll:
            herzschlag.aufpassen(melden=lambda text, teil=None: meldungen.append(text), jetzt=time.time() + 400)
        self.assertTrue(any("wartet_auf_freigabe_im_netzlaufwerk" in z for z in protokoll.output))
        self.assertIn("hing bei", meldungen[0])
        self.assertIn("test_herzschlag.py", meldungen[0])
        g = {t["teil"]: t for t in herzschlag.gesundheit()["teile"]}
        self.assertIn("test_herzschlag.py", g["dateiaustausch"]["hing"])

    def test_hauptschleife_nur_meldung(self):
        herzschlag.schlag("hauptschleife", 0.1)
        meldungen = []
        herzschlag.aufpassen(melden=lambda text, teil=None: meldungen.append(text), jetzt=time.time() + 200)
        self.assertEqual(len(meldungen), 1)
        self.assertIn("kann nur ein Neustart des Dienstes beheben", meldungen[0])

    def test_gesundheit_aus_der_datei_und_dienst_steht(self):
        herzschlag.schlag("hauptschleife", 0.5)
        herzschlag.aufpassen(jetzt=time.time())         # schreibt die Datei
        self.assertTrue(os.path.exists(herzschlag.pfad()))
        with herzschlag._sperre:
            herzschlag._stand.clear()                    # ein anderer Prozess: nur die Datei
        g = herzschlag.gesundheit()
        self.assertEqual(g["quelle"], "datei")
        self.assertEqual({t["teil"]: t["zustand"] for t in g["teile"]}["hauptschleife"], "gruen")
        g = herzschlag.gesundheit(jetzt=time.time() + 1000)
        self.assertEqual(g["quelle"], "alt")             # der Aufpasser schreibt nicht mehr
        self.assertEqual({t["teil"]: t["zustand"] for t in g["teile"]}["hauptschleife"], "rot")


if __name__ == "__main__":
    unittest.main()
