"""A1949 (Co #30170, W2458): der Pflichtkontext nennt das Konzept als „Einstiegs-Thema + Thema deines laufenden Pakets“ – keine
Konzept-Dokumente. Ohne laufendes Paket nur der Einstieg; Einstieg je Projekt einstellbar (konzept_einstieg, Lead/Mensch)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest
from unittest import mock

from amw import db, kern, themen


class KonzeptZeile(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.einstieg = themen.neu(self.con, self.pid, "TL", "Gesamtkonzept", pfleger="TL")
        self.paket_thema = themen.neu(self.con, self.pid, "TL", "Grob- und Feinplanung", pfleger="TL")
        themen.pflegen(self.con, self.pid, "TL", self.paket_thema, "Fassung eins.")
        themen.pflegen(self.con, self.pid, "TL", self.paket_thema, "Fassung zwei.")

    def zeile(self):
        return themen.konzept_zeile(self.con, self.pid, "CC1")

    def test_ohne_einstellung_und_paket_nichts(self):
        self.assertIsNone(self.zeile())

    def test_einstieg_dann_paket_thema(self):
        with self.assertRaisesRegex(kern.AmwFehler, "nur Lead und Entwickler"):
            kern.projekt_einstellen(self.con, self.pid, "CC1", konzept_einstieg=f"TH{self.einstieg}")
        kern.projekt_einstellen(self.con, self.pid, "TL", konzept_einstieg="Gesamtkonzept")              # Name geht auch
        e = f"TH{self.einstieg}"
        self.assertEqual(self.zeile(), f"Konzept: {e} Gesamtkonzept (Einstieg) – lesen: amw thema zeige {e}"
                                       " (nur diese; abgelöste Konzept-Dokumente nicht)")
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "K4 Planer", "CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", aid, "laeuft")
        self.assertIn(f"dein Paket A{aid} hat noch kein Thema", self.zeile())
        themen.verweise_setzen(self.con, self.pid, "TL", aid, [f"TH{self.paket_thema}"])
        p = f"TH{self.paket_thema}"
        self.assertEqual(self.zeile(), f"Konzept: {e} Gesamtkonzept (Einstieg) · dein Paket A{aid} → {p} Grob- und Feinplanung"
                                       f" (Fassung 2) – lesen: amw thema zeige {e} · amw thema zeige {p}"
                                       " (nur diese; abgelöste Konzept-Dokumente nicht)")

    def test_steht_im_pflichtkontext_ohne_dokumente(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", konzept_einstieg=f"TH{self.einstieg}")
        text = "\n".join(kern.kontext(self.con, self.pid, "CC1")) if isinstance(kern.kontext(self.con, self.pid, "CC1"), list) \
            else kern.kontext(self.con, self.pid, "CC1")
        self.assertIn(f"Konzept: TH{self.einstieg} Gesamtkonzept (Einstieg)", text)
        self.assertNotIn("D1258", text)
        self.assertNotIn("D1304", text)
        with self.assertRaisesRegex(kern.AmwFehler, "gibt es nicht"):
            kern.projekt_einstellen(self.con, self.pid, "TL", konzept_einstieg="TH999")


if __name__ == "__main__":
    unittest.main()
