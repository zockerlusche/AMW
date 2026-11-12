"""Fehlerbericht GlassWorld 07.11. (1.30.0): Wege im Projekt – Meldungen mit Bezug, Lead schließt Meldungen an den
Entwickler, Spezifikationen über den Lead (vorlegen, freigeben, nie still zurücksetzen), Agentenfragen zuerst an den Lead,
geparkte Fragen, Wortlaut und Beschluss in einem Zug."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import sqlite3
import tempfile
import unittest
from unittest import mock

from amw import bruecke, db, kern, planung, wissen, workbench


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.pfad = os.path.join(self.ordner.name, "t.db")
        self.con = db.anlegen(self.pfad)
        umgebung = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="GlassWorld", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "GW1")
        kern.agent_neu(self.con, self.pid, "GW2")

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def offen(self, nid, agent="Entwickler"):
        return self.con.execute("SELECT status, bemerkung FROM empfang WHERE nachricht_id = ? AND agent = ?", (nid, agent)).fetchone()

    def bogen(self):
        bid = planung.bogen_neu(self.con, self.pid, "TL", "Welt bauen", abnahme="läuft")
        return bid


class Meldungen(Grund):
    def test_wartemeldung_erledigt_sich_mit_dem_bezug(self):
        n1, _ = kern.posten(self.con, self.pid, "GW2", "TL", "info", "bin da, warte auf Leitbild", bis="leitbild")
        n2, _ = kern.posten(self.con, self.pid, "GW1", "TL", "info", "bin da, warte auf Aufgabe", bis="Aufgabe")
        with self.assertRaises(kern.AmwFehler):
            kern.posten(self.con, self.pid, "GW1", "TL", "info", "x", bis="morgen")
        with self.assertRaises(kern.AmwFehler):
            kern.posten(self.con, self.pid, "GW1", "TL", "info", "x", bis="A999")
        self.assertEqual(kern.bezuege_erledigen(self.con), [])
        planung.leitbild_setzen(self.con, self.pid, "TL", ziel="Eine gläserne Welt")
        self.assertEqual([n for n, _ in kern.bezuege_erledigen(self.con)], [n1])
        self.assertEqual(self.offen(n1, "TL")["status"], "erledigt")
        self.assertIn("Leitbild steht", self.offen(n1, "TL")["bemerkung"])
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Erste Szene", agent="GW1")
        self.assertEqual(kern.bezuege_erledigen(self.con), [(n2, f"GW1 hat A{aid}")])
        n3, _ = kern.posten(self.con, self.pid, "GW1", "TL", "info", "warte auf A", bis=f"a{aid}")
        self.assertEqual(self.con.execute("SELECT bis FROM nachricht WHERE id = ?", (n3,)).fetchone()[0], f"A{aid}")
        n4, _ = kern.posten(self.con, self.pid, "GW1", "TL", "info", "warte auf A (groß)", bis=f"A{aid}")   # CC2 #18719
        fid = kern.frage_neu(self.con, self.pid, "GW2", "tl", "Glas?", [])
        n5, _ = kern.posten(self.con, self.pid, "GW1", "TL", "info", "warte auf F", bis=f"F{fid}")
        with self.assertRaises(kern.AmwFehler) as f:
            kern.posten(self.con, self.pid, "GW1", "TL", "info", "x", bis="A999")
        self.assertIn("gibt es in diesem Projekt nicht", str(f.exception))
        self.assertEqual(kern.bezuege_erledigen(self.con), [])
        kern.aufgabe_status(self.con, self.pid, "GW1", aid, "start")
        kern.aufgabe_status(self.con, self.pid, "TL", aid, "fertig", beleg="abc1234")
        kern.frage_antworten(self.con, self.pid, fid, "text", "ja", "cli", "TL")
        self.assertEqual(sorted(n for n, _ in kern.bezuege_erledigen(self.con)), [n3, n4, n5])

    def test_lead_schliesst_meldungen_an_den_entwickler_mit_grund(self):
        n, _ = kern.posten(self.con, self.pid, "GW2", "Entwickler", "info", "noch kein Leitbild, warte")
        f, _ = kern.posten(self.con, self.pid, "GW2", "Entwickler", "frage", "darf ich?")
        with self.assertRaises(kern.AmwFehler):
            kern.erledigt_fuer(self.con, self.pid, "GW1", "Entwickler", [n], "veraltet")       # kein Lead
        with self.assertRaises(kern.AmwFehler):
            kern.erledigt_fuer(self.con, self.pid, "TL", "Entwickler", [n], " ")              # ohne Grund
        with self.assertRaises(kern.AmwFehler):
            kern.erledigt_fuer(self.con, self.pid, "TL", "Entwickler", [f], "veraltet")       # nur info/meldung
        self.assertEqual(kern.erledigt_fuer(self.con, self.pid, "TL", "Entwickler", [n], "Leitbild steht seit 10:05"), 1)
        self.assertEqual(tuple(self.offen(n)), ("erledigt", "geschlossen von TL: Leitbild steht seit 10:05"))
        self.assertTrue(self.con.execute("SELECT 1 FROM plan_ereignis WHERE art = 'info_geschlossen' AND von = 'TL'").fetchone())

    def test_aeltere_infos_ohne_bezug_wandern_in_die_ablage(self):
        alt, _ = kern.posten(self.con, self.pid, "GW1", "Entwickler", "info", "alt")
        neu, _ = kern.posten(self.con, self.pid, "GW1", "Entwickler", "info", "neu")
        mit, _ = kern.posten(self.con, self.pid, "GW1", "Entwickler", "info", "alt mit Bezug", bis="leitbild")
        self.con.execute("UPDATE nachricht SET zeit_utc = '2020-01-01T00:00:00Z' WHERE id IN (?, ?)", (alt, mit))
        d = workbench.daten_start(self.con, self.pid)
        abgelegt = {n["id"]: n["abgelegt"] for n in d["an_dich"]}
        self.assertEqual(abgelegt, {alt: True, neu: False, mit: False})
        self.assertEqual(d["zaehler"]["an_dich"], 2)


class Spezifikation(Grund):
    def test_nur_der_lead_legt_vor_und_die_karte_nennt_beide(self):
        bid = self.bogen()
        planung.spec_schreiben(self.con, self.pid, "GW1", bid, "anforderungen", "Die Welt ist aus Glas.")
        with self.assertRaises(kern.AmwFehler) as f:
            planung.spec_vorlegen(self.con, self.pid, "GW1", bid, "anforderungen")
        self.assertIn("nur der Lead", str(f.exception))
        planung.spec_vorlegen(self.con, self.pid, "TL", bid, "anforderungen")
        s = planung.freigaben_offen(self.con, self.pid)["spezifikationen"][0]
        self.assertEqual((s["geschrieben_von"], s["vorgelegt_von"]), ("GW1", "TL"))
        kern.projekt_einstellen(self.con, self.pid, "TL", spec_vorlegen="alle")
        planung.spec_schreiben(self.con, self.pid, "GW1", bid, "anforderungen", "Die Welt ist aus Glas. Neu.")
        planung.spec_vorlegen(self.con, self.pid, "GW1", bid, "anforderungen")            # umgestellt: jeder Agent

    def test_lead_gibt_frei_nur_wenn_eingeschaltet(self):
        bid = self.bogen()
        planung.spec_schreiben(self.con, self.pid, "GW1", bid, "anforderungen", "A")
        planung.spec_vorlegen(self.con, self.pid, "TL", bid, "anforderungen")
        with self.assertRaises(kern.AmwFehler):
            planung.spec_entscheiden(self.con, self.pid, "TL", bid, "anforderungen", True)
        kern.projekt_einstellen(self.con, self.pid, "Entwickler", spec_frei="lead")
        with self.assertRaises(kern.AmwFehler):
            planung.spec_entscheiden(self.con, self.pid, "GW1", bid, "anforderungen", True)     # Agent nie
        planung.spec_entscheiden(self.con, self.pid, "TL", bid, "anforderungen", True)
        self.assertEqual(planung.spec(self.con, bid, "anforderungen")["status"], "frei")
        self.assertEqual(planung.spec_wer(self.con, bid, "anforderungen", 1), ("TL", "TL"))

    def test_neue_fassung_hebt_freigabe_nicht_still_auf(self):
        bid = self.bogen()
        planung.spec_schreiben(self.con, self.pid, "GW1", bid, "anforderungen", "Zeile eins\nZeile zwei")
        planung.spec_vorlegen(self.con, self.pid, "TL", bid, "anforderungen")
        planung.spec_entscheiden(self.con, self.pid, "Entwickler", bid, "anforderungen", True)
        planung.spec_schreiben(self.con, self.pid, "GW1", bid, "anforderungen", "Zeile eins\nZeile drei")
        n = self.con.execute("SELECT id, kurz, text FROM nachricht WHERE kurz LIKE '%Freigabe von anforderungen v1 aufgehoben%'").fetchone()
        self.assertIsNotNone(n)
        self.assertIn("-Zeile zwei", n["text"])
        self.assertIn("+Zeile drei", n["text"])
        an = {r[0] for r in self.con.execute("SELECT agent FROM empfang WHERE nachricht_id = ?", (n["id"],))}
        self.assertEqual(an, {"Entwickler", "TL"})


class Fragen(Grund):
    def frage(self, von="GW1", **k):
        return kern.frage_neu(self.con, self.pid, von, "entwickler", "Glas oder Kristall?", [("A", "Glas"), ("B", "Kristall")], "A",
                              "Glas passt zum Namen", geprueft="nichts dazu gefunden", **k)

    def test_agentenfragen_gehen_zuerst_an_den_lead_und_werden_weitergeleitet(self):
        fid = self.frage()
        f = self.con.execute("SELECT an FROM frage WHERE id = ?", (fid,)).fetchone()
        self.assertEqual(f["an"], "tl")
        self.assertTrue(self.con.execute("SELECT 1 FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id WHERE e.agent = 'TL'"
                                         " AND n.kurz LIKE ?", (f"Frage F{fid} für den Entwickler%",)).fetchone())
        self.assertEqual(self.con.execute("SELECT count(*) FROM frage WHERE an = 'entwickler'").fetchone()[0], 0)   # Workbench: noch nicht
        with self.assertRaises(kern.AmwFehler):
            kern.frage_weiterleiten(self.con, self.pid, "GW2", fid)                          # nur der Lead
        kern.frage_weiterleiten(self.con, self.pid, "TL", fid, "bitte entscheiden")
        self.assertEqual(self.con.execute("SELECT an FROM frage WHERE id = ?", (fid,)).fetchone()[0], "entwickler")
        v = self.con.execute("SELECT text FROM frage_verlauf WHERE frage_id = ?", (fid,)).fetchone()[0]
        self.assertIn("Weitergeleitet von TL", v)
        with self.assertRaises(kern.AmwFehler):
            kern.frage_weiterleiten(self.con, self.pid, "TL", fid)                           # schon dort

    def test_lead_und_umgestelltes_projekt_fragen_direkt(self):
        self.assertEqual(self.con.execute("SELECT an FROM frage WHERE id = ?", (self.frage(von="TL"),)).fetchone()[0], "entwickler")
        kern.projekt_einstellen(self.con, self.pid, "TL", agentenfragen="direkt")
        self.assertEqual(self.con.execute("SELECT an FROM frage WHERE id = ?", (self.frage(),)).fetchone()[0], "entwickler")

    def test_geparkte_frage_heisst_in_der_lesekopie_und_der_suche_geparkt(self):
        fid = self.frage(von="TL")
        kern.frage_parken(self.con, self.pid, "Entwickler", fid, True, "später")
        ziel = os.path.join(self.ordner.name, "kopie.db")
        self.con.commit()
        bruecke.lese_kopie(self.pfad, ziel, self.pid)
        k = sqlite3.connect(ziel)
        self.assertEqual(k.execute("SELECT zustand FROM frage_zustand WHERE id = ?", (fid,)).fetchone()[0], "geparkt")
        k.close()
        from amw import abgleich
        import base64, zlib
        idx = json.loads(zlib.decompress(base64.b64decode(abgleich.suchindex(self.con, self.pid)["gepackt"])))
        self.assertIn(["frage", f"F{fid}"], [e[:2] for e in idx])
        self.assertEqual(next(e for e in idx if e[1] == f"F{fid}")[4], "geparkt")


class Bruecke(unittest.TestCase):
    def test_lead_stellt_ueber_die_bruecke_nur_ein(self):
        self.assertEqual(bruecke.argumente({"args": ["projekt", "einstellen", "spec_frei=lead"]})[:3],
                         ["projekt", "einstellen", "spec_frei=lead"])
        for verboten in (["projekt", "neu", "X"], ["projekt", "ordner", "X", "--ordner", "C:/"], ["projekt"]):
            with self.assertRaises(ValueError):
                bruecke.argumente({"args": verboten})


class Wortlaut(Grund):
    def test_beschluss_mit_wortlaut_in_einem_zug(self):
        hinweise = []
        bid = wissen.beschluss_neu(self.con, self.pid, "TL", "Glas", "Die Welt ist aus Glas", "Marcel 10:22", hinweise=hinweise,
                                   wortlaut_neu=("Die Welt soll aus Glas sein.", "chat-tl", None), neues_thema=True, thema="Welt")
        b = self.con.execute("SELECT wortlaut_ids FROM beschluss WHERE id = ?", (bid,)).fetchone()[0]
        w = self.con.execute("SELECT id, text FROM wortlaut").fetchone()
        self.assertEqual(b, str(w["id"]))
        self.assertEqual(w["text"], "Die Welt soll aus Glas sein.")
        self.assertIn(f"W{w['id']} erfasst und verknüpft", hinweise)


if __name__ == "__main__":
    unittest.main()
