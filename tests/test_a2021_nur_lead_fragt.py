"""A2021 (Marcel 23.11. 20:28 „Nur noch der Teamleiter fragt“): Fragen eines Agenten an den Menschen gehen immer an den Lead
(unabhängig von agentenfragen); Lead und Co-Entwickler fragen direkt. Weitergeleitet sieht der Mensch die Frage als Frage des
Leads (der Fragesteller steht im Verlauf); der Lead kann sie vorher überarbeiten oder mehrere bündeln – die Antwort gilt dann auch
für die alten. posten --an Entwickler mit Art frage/auftrag eines Agenten geht an den Lead; info bleibt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import unittest

from amw import db, kern, workbench


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        for k in ("Co", "CC1", "CC2"):
            kern.agent_neu(self.con, self.pid, k)
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="Co", agentenfragen="direkt")   # direkt: wirkt nicht mehr

    def frage(self, von, kurz="A oder B?"):
        return kern.frage_neu(self.con, self.pid, von, "entwickler", kurz, [("A", "a"), ("B", "b")], "A", "kürzer",
                              geprueft="keine Treffer")

    def an(self, fid):
        return self.con.execute("SELECT an FROM frage WHERE id = ?", (fid,)).fetchone()[0]

    def post(self, an):
        return [r[0] for r in self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ?"
                                               " ORDER BY n.id", (an,))]


class Fragen(Grund):
    def test_nur_lead_und_co_fragen_direkt(self):
        self.assertEqual([self.an(self.frage(k)) for k in ("CC1", "TL", "Co")], ["tl", "entwickler", "entwickler"])
        self.assertTrue(any("für den Entwickler – selbst beantworten oder weiterleiten" in k for k in self.post("TL")))

    def test_weiterleiten_als_frage_des_leads_ueberarbeitet(self):
        fid = self.frage("CC1", "Welche Farbe?")
        with self.assertRaisesRegex(kern.AmwFehler, "keine der Optionen"):
            kern.frage_weiterleiten(self.con, self.pid, "TL", fid, empfehlung="C")
        kern.frage_weiterleiten(self.con, self.pid, "TL", fid, "bitte bis morgen", kurz="Bernstein oder Grün für „läuft“?",
                                optionen=[("A", "Bernstein"), ("B", "Grün")], empfehlung="B", grund="Grün heißt überall „läuft“")
        f = self.con.execute("SELECT * FROM frage WHERE id = ?", (fid,)).fetchone()
        self.assertEqual((f["an"], f["von"], f["kurz"], f["empfehlung"]), ("entwickler", "CC1", "Bernstein oder Grün für „läuft“?", "B"))
        self.assertEqual([o["text"] for o in json.loads(f["optionen"])], ["Bernstein", "Grün"])
        self.assertEqual(kern.frage_ueber(self.con, self.pid, fid), "TL")
        d = next(x for x in workbench.daten_fragen(self.con, self.pid) if x["id"] == fid)
        self.assertEqual((d["von"], d["fragesteller"]), ("TL", "CC1"))                       # Marcel sieht: TL fragt
        self.assertIn("gestellt von CC1", d["verlauf"][-1]["text"])
        self.assertEqual([x["von"] for x in workbench.daten_start(self.con, self.pid)["fragen"] if x["id"] == fid], ["TL"])

    def test_buendeln_antwort_gilt_auch_fuer_die_alten(self):
        f1, f2 = self.frage("CC1", "Farbe?"), self.frage("CC2", "Farbe auch hier?")
        with self.assertRaisesRegex(kern.AmwFehler, "Bündeln"):
            kern.frage_neu(self.con, self.pid, "CC1", "entwickler", "x", [("A", "a")], "A", "g", geprueft="k", buendel=[f2])
        neu = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Eine Farbe für „läuft“ überall?", [("A", "Grün"), ("B", "Bernstein")],
                             "A", "einheitlich", geprueft="keine Treffer", buendel=[f"F{f1}", f2])
        self.assertEqual(kern.frage_gebuendelt(self.con, self.pid, neu), [f1, f2])
        offen_lead = [r["id"] for r in kern.offene_fragen(self.con, self.pid, "tl")]
        self.assertNotIn(f1, offen_lead)                                                      # beim Lead nicht mehr offen
        kern.frage_antworten(self.con, self.pid, neu, "option", "A", "seite")
        for alt, wer in ((f1, "CC1"), (f2, "CC2")):
            g = self.con.execute("SELECT status, antwort FROM frage WHERE id = ?", (alt,)).fetchone()
            self.assertEqual(g["status"], "beantwortet")
            self.assertTrue(g["antwort"].startswith(f"Antwort auf F{neu}: A) Grün"), g["antwort"])
            self.assertTrue(any(k.startswith(f"Antwort zu F{alt}") for k in self.post(wer)), wer)   # der Fragesteller wird geweckt
        with self.assertRaisesRegex(kern.AmwFehler, "offenen Fragen beim Lead"):
            kern.frage_neu(self.con, self.pid, "TL", "entwickler", "noch mal", [("A", "a")], "A", "g", geprueft="k", buendel=[f1])


class Posten(Grund):
    def test_frage_und_auftrag_an_den_menschen_gehen_an_den_lead(self):
        hinweise = []
        _, namen = kern.posten(self.con, self.pid, "CC1", "Entwickler", "frage", "Darf ich A2000 schließen?", hinweise=hinweise)
        self.assertEqual(namen, ["TL"])
        self.assertTrue(hinweise and "fragt nur der Lead" in hinweise[0])
        _, namen = kern.posten(self.con, self.pid, "CC1", "Entwickler,CC2", "auftrag", "bitte entscheiden")
        self.assertEqual(sorted(namen), ["CC2", "TL"])
        self.assertTrue(any("fragt nur der Lead" in k for k in self.post("CC1")))            # ohne Ausgabe: Meldung an den Absender
        for von, art in (("CC1", "info"), ("TL", "frage"), ("Co", "auftrag")):              # info bleibt; Lead und Co dürfen
            _, namen = kern.posten(self.con, self.pid, von, "Entwickler", art, f"{art} von {von}")
            self.assertEqual(namen, [kern.ENTWICKLER], (von, art))


if __name__ == "__main__":
    unittest.main()
