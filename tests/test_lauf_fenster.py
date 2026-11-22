"""A1924 (TH160 F2, D1258 §12 Pkt 7 Rechnerzeiten): Zeitfenster je Projekt für schwere Läufe (lauf_fenster, Ortszeit, auch über
Mitternacht) – außerhalb wartet ein schwerer Lauf sichtbar („wartet auf das Zeitfenster ab 18:00“) und hält niemanden auf;
leichte Läufe und KI-Aufträge unberührt; Grafikkarte/Bildschirm PC-weit nie zwei zugleich; Rangfolge der Projekte
(projekt_rang, #29885) als zweites Kriterium nach dem Vorrang. Alles mit fester Uhr."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import unittest
from unittest import mock

from amw import betrieb, einstellungen, kern
from tests.test_rechner_schlange import Grund


def um(h, m=0):
    return datetime.datetime(2026, 11, 22, h, m).astimezone()


class Fenster(Grund):
    def setUp(self):
        super().setUp()
        self.jetzt = um(12)
        p = mock.patch.object(betrieb, "uhr", lambda: self.jetzt)
        p.start()
        self.addCleanup(p.stop)
        kern.projekt_einstellen(self.con, self.p["Eins"], kern.ENTWICKLER, lauf_fenster="18:00-07:00")

    def test_einstellung(self):
        self.assertEqual(betrieb.lauf_fenster(self.con, self.p["Eins"]), (18 * 60, 7 * 60))
        self.assertIsNone(betrieb.lauf_fenster(self.con, self.p["Zwei"]))                     # je Projekt
        kern.projekt_einstellen(self.con, self.p["Zwei"], "Chef", lauf_fenster="schwer: 22–6")  # Lead darf, Schreibweisen
        self.assertEqual(betrieb.lauf_fenster(self.con, self.p["Zwei"]), (22 * 60, 6 * 60))
        with self.assertRaisesRegex(kern.AmwFehler, "nur Lead und Entwickler"):
            kern.projekt_einstellen(self.con, self.p["Zwei"], "A", lauf_fenster="18-07")
        with self.assertRaisesRegex(kern.AmwFehler, "lauf_fenster: .*z. B. 18:00-07:00"):
            kern.projekt_einstellen(self.con, self.p["Zwei"], "Chef", lauf_fenster="abends")
        kern.projekt_einstellen(self.con, self.p["Zwei"], "Chef", lauf_fenster="")             # leer = jederzeit
        self.assertIsNone(betrieb.lauf_fenster(self.con, self.p["Zwei"]))

    def test_schwer_ausserhalb_wartet_sichtbar_und_haelt_niemanden_auf(self):
        a = self.start("Eins", "A")                                                            # 12:00: außerhalb
        self.assertEqual(self.status(a), "angemeldet")
        g = betrieb.wartegrund(self.con, self.p["Eins"], betrieb.lauf_zeile(self.con, self.p["Eins"], a), speicher_frei=32.0)
        self.assertIn("wartet auf das Zeitfenster ab 18:00 (schwere Läufe von Eins nur 18:00–07:00 Uhr", g)
        b = self.start("Zwei", "A")                                                            # anderes Projekt: läuft
        self.assertEqual(self.status(b), "laeuft")
        betrieb.lauf_ende(self.con, self.p["Zwei"], "A", b, 0, speicher_frei=32.0)
        c = self.start("Eins", "B", schwer=False)                                              # leicht: unberührt
        self.assertEqual(self.status(c), "laeuft")
        with self.assertRaisesRegex(kern.AmwFehler, "wartet auf das Zeitfenster ab 18:00.*mit --warten einreihen"):
            betrieb.lauf_start(self.con, self.p["Eins"], "C", "ohne warten", speicher_frei=32.0)
        self.jetzt = um(18, 5)                                                                 # im Fenster: startet
        betrieb.warteschlange(self.con, speicher_frei=32.0)
        self.assertEqual(self.status(a), "laeuft")

    def test_ueber_mitternacht(self):
        for h, drin in ((17, False), (18, True), (23, True), (3, True), (6, True), (7, False)):
            self.jetzt = um(h, 30 if h == 6 else 0)
            self.assertEqual(betrieb.fenster_sperre(self.con, self.p["Eins"], True) is None, drin, h)
        self.assertIsNone(betrieb.fenster_sperre(self.con, self.p["Eins"], False))           # leicht
        self.assertIsNone(betrieb.fenster_sperre(self.con, self.p["Eins"], True, ki_auftrag=True))   # KI: eigenes Fenster

    def test_grafikkarte_und_bildschirm_nie_zwei_zugleich(self):
        kern.projekt_einstellen(self.con, self.p["Eins"], kern.ENTWICKLER, lauf_fenster="")
        a = self.start("Eins", "A", gpu=True)
        b = self.start("Zwei", "A", gpu=True)                                                  # anderes Projekt, gleiche Karte
        self.assertEqual((self.status(a), self.status(b)), ("laeuft", "angemeldet"))
        betrieb.lauf_ende(self.con, self.p["Eins"], "A", a, 0, speicher_frei=32.0)
        self.assertEqual(self.status(b), "laeuft")


class OhneFenster(Grund):
    """TL #31312: Ohne gesetztes lauf_fenster bleibt alles wie vor A1924 – schwere Läufe starten zu jeder Uhrzeit sofort,
    kein Wartegrund „Zeitfenster“, Reihenfolge nach Ankunft."""
    def setUp(self):
        super().setUp()
        self.jetzt = um(12)
        p = mock.patch.object(betrieb, "uhr", lambda: self.jetzt)
        p.start()
        self.addCleanup(p.stop)

    def test_schwer_startet_zu_jeder_zeit_wie_bisher(self):
        for h in (3, 12, 17, 18, 23):
            self.jetzt = um(h)
            self.assertIsNone(betrieb.lauf_fenster(self.con, self.p["Eins"]))
            self.assertIsNone(betrieb.fenster_sperre(self.con, self.p["Eins"], True), h)
            a = self.start("Eins", "A")
            self.assertEqual(self.status(a), "laeuft", h)
            b = self.start("Eins", "B")                                                        # wartet nur auf den Platz
            g = betrieb.wartegrund(self.con, self.p["Eins"], betrieb.lauf_zeile(self.con, self.p["Eins"], b), speicher_frei=32.0)
            self.assertNotIn("Zeitfenster", g, h)
            betrieb.lauf_ende(self.con, self.p["Eins"], "A", a, 0, speicher_frei=32.0)
            self.assertEqual(self.status(b), "laeuft", h)                                     # rückt nach Ankunft nach
            betrieb.lauf_ende(self.con, self.p["Eins"], "B", b, 0, speicher_frei=32.0)
        c = betrieb.lauf_start(self.con, self.p["Eins"], "C", "ohne warten", speicher_frei=32.0)   # ohne --warten: kein Fehler
        self.assertEqual(self.status(c), "laeuft")


class Rangfolge(Grund):
    def setUp(self):
        super().setUp()
        self.rang = []
        alt = einstellungen.wert
        p = mock.patch.object(einstellungen, "wert", lambda k: list(self.rang) if k == "projekt_rang" else alt(k))
        p.start()
        self.addCleanup(p.stop)
        self.v = {}
        q = mock.patch.object(betrieb, "vorrang", lambda: dict(self.v))
        q.start()
        self.addCleanup(q.stop)

    def test_projekt_rang_nach_vorrang_vor_ankunft(self):
        laeuft = self.start("Eins", "A")
        e1 = self.start("Eins", "B")
        z1 = self.start("Zwei", "A")
        self.assertEqual(self.reihenfolge(), [e1, z1])                                         # ohne Rangfolge: Ankunft
        self.rang = ["zwei", "Eins"]                                                           # Groß/klein egal
        self.assertEqual(self.reihenfolge(), [z1, e1])
        self.v = {"Eins": "hoch"}                                                              # Vorrang geht vor
        self.assertEqual(self.reihenfolge(), [e1, z1])
        self.v = {}
        betrieb.lauf_ende(self.con, self.p["Eins"], "A", laeuft, 0, speicher_frei=32.0)
        self.assertEqual((self.status(z1), self.status(e1)), ("laeuft", "angemeldet"))

    def test_nicht_genannte_danach_und_neuer_lauf_eines_hoeheren_projekts(self):
        self.rang = ["Zwei"]
        laeuft = self.start("Eins", "A")
        e1 = self.start("Eins", "B")
        z1 = self.start("Zwei", "B")
        self.assertEqual(self.reihenfolge(), [z1, e1])                                         # Eins steht nicht in der Liste
        g = betrieb.wartegrund(self.con, self.p["Zwei"], betrieb.lauf_zeile(self.con, self.p["Zwei"], z1), speicher_frei=32.0)
        self.assertNotIn(f"L{e1}", g)                                                          # der spätere Eins-Lauf hält ihn nicht auf
        self.assertTrue(laeuft)


if __name__ == "__main__":
    unittest.main()
