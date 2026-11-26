"""A2174: Verteilen gibt einem Agenten nichts Neues, wenn er schon verteilen_max_offen (Vorgabe 2) zugeteilte, nicht fertige Pakete hat –
auch wenn er gerade nur auf seine Läufe wartet (A2053 gibt ihn dafür frei). Gebaute Pakete, die nur auf eine Prüfung oder auf Stapel/Bündel
warten, zählen nicht; ein anderer freier Agent bekommt das Paket."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest

from amw import db, kern, verteilen
from tests.test_verteilen import Grund


class MaxOffen(Grund):
    def eigenes(self, titel, bezug, k="CC1"):
        """Paket von k im Status wartet mit einem offenen Grund (art monitor, bezug wie wartegrund.stichwort)."""
        aid = self.aufgabe(titel)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET agent = ?, status = 'wartet', begonnen_utc = ? WHERE id = ?", (k, db.jetzt(), aid))
            db.einfuegen(self.con, "wartegrund", projekt_id=self.pid, aufgabe_id=aid, art="monitor" if ":" in bezug else "lauf", bezug=bezug,
                         angelegt_utc="2026-11-26T10:00:00Z", angelegt_von=k)
        return aid

    def frei(self):
        return [k for k, _ in verteilen.freie_agenten(self.con, self.pid)]

    def test_zwei_offene_bekommen_nichts_ein_anderer_schon(self):
        with db.schreiben(self.con):                                          # die Läufe, auf die CC1 wartet, gibt es
            for n in (1, 2):
                db.einfuegen(self.con, "lauf", id=n, projekt_id=self.pid, agent="CC1", beschreibung="Tests", status="angemeldet",
                             angemeldet_utc=db.jetzt())
        self.eigenes("Eins", "L1")
        self.assertEqual(self.frei(), ["CC1", "CC2"])                          # ein offenes: noch frei (wartet_lauf gibt frei, A2053)
        self.eigenes("Zwei", "L2")
        self.assertEqual(verteilen.offene_pakete(self.con, self.pid, "CC1").__len__(), 2)
        self.assertEqual(self.frei(), ["CC2"])                                 # zwei offene: nichts Neues
        kern.projekt_einstellen(self.con, self.pid, "TL", verteilen="an")
        with db.schreiben(self.con):                                          # CC2 passt fachlich (Grund: Grafik)
            self.con.execute("UPDATE agent SET fachgebiet = 'Code' WHERE projekt_id = ? AND kennung = 'CC2'", (self.pid,))
        neu = self.aufgabe("Neu", art="mechanisch")
        verteilen.verteilen(self.con, self.pid)
        self.assertEqual(self.agent_von(neu), "CC2")                           # der andere freie bekommt es

    def test_gebaut_wartende_zaehlen_nicht(self):
        self.eigenes("Gebaut, Prüfung", "pruefung:P5")
        self.eigenes("Gebaut, Stapel", "stapel:ccamw-st68")
        self.assertEqual(verteilen.offene_pakete(self.con, self.pid, "CC1"), [])
        self.assertIn("CC1", self.frei())

    def test_einstellung(self):
        self.assertEqual(verteilen.max_offen(self.con, self.pid), 2)
        kern.projekt_einstellen(self.con, self.pid, "TL", verteilen_max_offen=1)
        self.assertEqual(verteilen.max_offen(self.con, self.pid), 1)
        with db.schreiben(self.con):
            db.einfuegen(self.con, "lauf", id=7, projekt_id=self.pid, agent="CC1", beschreibung="Tests", status="angemeldet",
                         angemeldet_utc=db.jetzt())
        self.eigenes("Eins", "L7")
        self.assertEqual(self.frei(), ["CC2"])                                 # Grenze 1: schon eins offen
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "TL", verteilen_max_offen=9)


if __name__ == "__main__":
    unittest.main()
