"""A1948 (Befund 22.11., L2980–L2982): Läufe, die die AMW selbst ausführt und beendet (Gegenlesen, Planer, Negativprobe,
Arbeiter, Bündel), bekommen aus der Schlange keine „jetzt starten“-Freigabe und keinen Weckruf – andere Läufe wie bisher."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest
from unittest import mock

from amw import betrieb, gegenlesen
from tests.test_rechner_schlange import Grund


class Selbst(Grund):
    def post(self, agent):
        return [r["kurz"] for r in self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                                                    " WHERE e.agent = ? AND n.von = 'AMW' ORDER BY n.id", (agent,))]

    def test_selbst_gestarteter_lauf_ohne_freigabe(self):
        a = self.start("Eins", "A")                                                  # belegt die Spur des Agenten
        s = betrieb.lauf_start(self.con, self.p["Eins"], "A", "Gegenlesen TH1 Fassung 1 (haiku, A1914, automatisch)", None, False,
                               False, None, warten=True, speicher_frei=32.0, selbst=True)
        n = self.start("Eins", "A", "normaler Lauf")
        self.assertEqual((self.status(s), self.status(n)), ("angemeldet", "angemeldet"))
        self.assertTrue(betrieb.selbst_gestartet(self.con, s))
        self.assertFalse(betrieb.selbst_gestartet(self.con, n))
        betrieb.lauf_ende(self.con, self.p["Eins"], "A", a, 0, speicher_frei=32.0)
        self.assertEqual(self.status(s), "laeuft")
        self.assertEqual([k for k in self.post("A") if k.startswith(f"L{s} ")], [])          # keine Freigabe, kein Weckruf
        betrieb.lauf_ende(self.con, self.p["Eins"], "A", s, 0, speicher_frei=32.0)
        self.assertEqual(self.status(n), "laeuft")
        self.assertTrue(any(k.startswith(f"L{n} ist dran – jetzt starten") for k in self.post("A")))   # normaler Lauf wie bisher

    def test_gegenlesen_meldet_sich_als_selbst_an(self):
        gesehen = {}
        echt = betrieb.lauf_start

        def merken(*args, **kw):
            gesehen.update(kw)
            raise RuntimeError("nur ansehen")
        with mock.patch.object(betrieb, "lauf_start", side_effect=merken):
            try:
                gegenlesen.ausfuehren(self.con, self.p["Eins"], 1, 1)
            except Exception:                                                        # noqa: BLE001 – es geht nur um den Aufruf
                pass
        self.assertTrue(gesehen.get("selbst"))
        self.assertTrue(echt)


if __name__ == "__main__":
    unittest.main()
