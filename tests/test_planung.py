"""Tests für die Projektplanung: Leitbild, Bögen/Baseline, Spezifikation mit Freigabe und Klärungen, Abhängigkeiten,
Plan-Gate, Kriterien/Zusammenfassung, nächster Schritt, Risiken, Prognose, Plan-Check, Wartet auf dich."""
import datetime
import os
import random
import tempfile
import unittest

from amw import db, kern, planung


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None), ("CC2", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def bogen(self, **k):
        return planung.bogen_neu(self.con, self.pid, "TL", k.pop("titel", "Erster Bogen"), **k)

    def schritt(self, titel="S", **k):
        return planung.schritt_setzen(self.con, self.pid, "TL", titel=titel, **k)

    def an(self, wer):
        return [r[0] for r in self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                                               " WHERE e.agent = ? ORDER BY n.id", (wer,))]


class Leitbild(Grund):
    def test_setzen_nur_lead_und_kontext(self):
        with self.assertRaises(kern.AmwFehler):
            planung.leitbild_setzen(self.con, self.pid, "CC1", ziel="x")
        planung.leitbild_setzen(self.con, self.pid, "Entwickler", ziel="Spiel spielbar", nicht_ziele=["kein Mehrspieler"],
                                prinzipien=["Einfach|Versteht es ein Neuling?"], dod=["Tests grün", "Doku angepasst"])
        lb = planung.leitbild(self.con, self.pid)
        self.assertEqual(lb["prinzipien"][0], {"text": "Einfach", "pruefung": "Versteht es ein Neuling?"})
        text = kern.kontext(self.con, self.pid, "CC1")
        self.assertIn("Projektziel: Spiel spielbar", text)
        self.assertIn("Definition of Done: Tests grün | Doku angepasst", text)


class Boegen(Grund):
    def test_baseline_beim_aktivieren_und_aenderung_nur_mit_grund(self):
        bid = self.bogen(zieldatum="2026-12-01", abnahme="Demo läuft")
        planung.bogen_status(self.con, self.pid, "TL", bid, "aktiv")
        self.assertEqual(planung.bogen_zeile(self.con, self.pid, bid)["baseline_datum"], "2026-12-01")
        with self.assertRaises(kern.AmwFehler):
            planung.bogen_aendern(self.con, self.pid, "TL", bid, zieldatum="2026-12-15")
        planung.bogen_aendern(self.con, self.pid, "TL", bid, zieldatum="2026-12-15", grund="Umfang gewachsen")
        b = planung.bogen_zeile(self.con, self.pid, bid)
        self.assertEqual((b["zieldatum"], b["baseline_datum"]), ("2026-12-15", "2026-12-01"))
        self.assertEqual(self.con.execute("SELECT art FROM plan_ereignis ORDER BY id DESC").fetchone()[0], "baseline")

    def test_fertig_nur_ohne_offene_schritte(self):
        bid = self.bogen()
        self.schritt(bogen_id=bid)
        with self.assertRaises(kern.AmwFehler):
            planung.bogen_status(self.con, self.pid, "TL", bid, "fertig")
        planung.bogen_status(self.con, self.pid, "TL", bid, "fertig", erzwingen=True)


class Spezifikation(Grund):
    def test_reihenfolge_klaerungen_freigabe_durch_den_menschen(self):
        bid = self.bogen()
        planung.spec_schreiben(self.con, self.pid, "TL", bid, "entwurf", "Architektur")
        with self.assertRaises(kern.AmwFehler):
            planung.spec_vorlegen(self.con, self.pid, "TL", bid, "entwurf")            # erst Anforderungen
        planung.spec_schreiben(self.con, self.pid, "TL", bid, "anforderungen", "R1 Login\nR2 [KLÄREN: Passwortregeln?]")
        fragen = planung.spec_vorlegen(self.con, self.pid, "TL", bid, "anforderungen")
        self.assertEqual(len(fragen), 1)
        with self.assertRaises(kern.AmwFehler):
            planung.spec_entscheiden(self.con, self.pid, "TL", bid, "anforderungen", True)   # nur der Mensch
        with self.assertRaises(kern.AmwFehler):
            planung.spec_entscheiden(self.con, self.pid, "Entwickler", bid, "anforderungen", True)   # Klärung offen
        kern.frage_antworten(self.con, self.pid, fragen[0], "text", "mind. 12 Zeichen", "seite")
        planung.spec_entscheiden(self.con, self.pid, "Entwickler", bid, "anforderungen", True)
        self.assertIn(f"Bogen {bid} „Erster Bogen“: anforderungen FREIGEGEBEN", self.an("TL"))
        self.assertEqual(planung.spec_vorlegen(self.con, self.pid, "TL", bid, "anforderungen") if False else
                         planung.spec(self.con, bid, "anforderungen")["status"], "frei")

    def test_aendern_nach_freigabe_neue_version_und_zurueck_nur_mit_kommentar(self):
        bid = self.bogen()
        planung.spec_schreiben(self.con, self.pid, "TL", bid, "anforderungen", "R1 a")
        planung.spec_vorlegen(self.con, self.pid, "TL", bid, "anforderungen")
        with self.assertRaises(kern.AmwFehler):
            planung.spec_entscheiden(self.con, self.pid, "Entwickler", bid, "anforderungen", False)
        planung.spec_entscheiden(self.con, self.pid, "Entwickler", bid, "anforderungen", False, "R1 genauer")
        self.assertEqual(planung.spec(self.con, bid, "anforderungen")["status"], "zurueck")
        planung.spec_vorlegen(self.con, self.pid, "TL", bid, "anforderungen")
        planung.spec_entscheiden(self.con, self.pid, "Entwickler", bid, "anforderungen", True)
        self.assertEqual(planung.spec_schreiben(self.con, self.pid, "TL", bid, "anforderungen", "R1 b"), 2)
        self.assertEqual(planung.spec(self.con, bid, "anforderungen")["status"], "entwurf")


class Schritte(Grund):
    def test_abhaengigkeit_kreis_und_start_erst_nach_vorgaenger(self):
        bid = self.bogen()
        a1, a2 = self.schritt("A", bogen_id=bid), self.schritt("B", bogen_id=bid)
        alt1, alt2 = kern.aufgabe_neu(self.con, self.pid, "TL", "alt 1"), kern.aufgabe_neu(self.con, self.pid, "TL", "alt 2")
        planung.abhaengigkeit_setzen(self.con, self.pid, "TL", alt2, [alt1])
        kern.aufgabe_status(self.con, self.pid, "TL", alt2, "start")                  # ohne Bogen: keine Sperre
        planung.abhaengigkeit_setzen(self.con, self.pid, "TL", a2, [a1])
        with self.assertRaises(kern.AmwFehler):
            planung.abhaengigkeit_setzen(self.con, self.pid, "TL", a1, [a2])          # Kreis
        with self.assertRaises(kern.AmwFehler):
            kern.aufgabe_status(self.con, self.pid, "TL", a2, "start")
        kern.aufgabe_status(self.con, self.pid, "TL", a1, "fertig", beleg="x", zusammenfassung="erledigt")
        kern.aufgabe_status(self.con, self.pid, "TL", a2, "start")
        self.assertEqual(planung.wellen(self.con, [a1, a2]), {a1: 1, a2: 2})
        vorher = self.con.execute("SELECT count(*) FROM aufgabe").fetchone()[0]
        with self.assertRaises(kern.AmwFehler):
            self.schritt("C", bogen_id=bid, nach=[a1, 99999])                             # unbekannter Vorgänger
        self.assertEqual(self.con.execute("SELECT count(*) FROM aufgabe").fetchone()[0], vorher)   # nichts halb angelegt

    def test_plan_gate_ab_komplexitaet_7(self):
        aid = self.schritt(komplexitaet=8, agent="CC1", bogen_id=self.bogen())
        with self.assertRaises(kern.AmwFehler):
            kern.aufgabe_status(self.con, self.pid, "CC1", aid, "start")
        planung.plan_vorlegen(self.con, self.pid, "CC1", aid, "1. … 2. …")
        self.assertTrue(any("Plan für A" in k for k in self.an("TL")))
        with self.assertRaises(kern.AmwFehler):
            planung.plan_entscheiden(self.con, self.pid, "CC1", aid, True)              # nicht sich selbst
        planung.plan_entscheiden(self.con, self.pid, "TL", aid, True)
        kern.aufgabe_status(self.con, self.pid, "CC1", aid, "start")

    def test_fertig_im_bogen_nur_mit_kriterien_und_zusammenfassung_ohne_bogen_wie_bisher(self):
        bid = self.bogen()
        aid = self.schritt(bogen_id=bid, agent="CC1", kriterien=["Test grün", "Doku"])
        with self.assertRaises(kern.AmwFehler):
            kern.aufgabe_status(self.con, self.pid, "CC1", aid, "fertig", beleg="abc", zusammenfassung="erledigt")
        planung.kriterium(self.con, self.pid, "CC1", aid, 1)
        planung.kriterium(self.con, self.pid, "CC1", aid, 2)
        with self.assertRaises(kern.AmwFehler):
            kern.aufgabe_status(self.con, self.pid, "CC1", aid, "fertig", beleg="abc")
        kern.aufgabe_status(self.con, self.pid, "CC1", aid, "fertig", beleg="abc", zusammenfassung="gebaut und getestet")
        alt = kern.aufgabe_neu(self.con, self.pid, "TL", "ohne Bogen", "CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", alt, "fertig", beleg="abc")      # bisheriger Ablauf

    def test_kriterien_bleiben_bei_gleichem_text_erfuellt(self):
        aid = self.schritt(kriterien=["a", "b"], agent="CC1")
        planung.kriterium(self.con, self.pid, "CC1", aid, 1)
        planung.schritt_setzen(self.con, self.pid, "TL", aid=aid, kriterien=["a", "c"])
        import json
        k = json.loads(self.con.execute("SELECT kriterien FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0])
        self.assertEqual(k, [{"text": "a", "erfuellt": True}, {"text": "c", "erfuellt": False}])

    def test_naechster_aktiver_bogen_zuerst_ohne_offene_vorgaenger_und_nehmen(self):
        b1, b2 = self.bogen(titel="eins"), self.bogen(titel="zwei")
        planung.bogen_status(self.con, self.pid, "TL", b1, "aktiv")
        planung.bogen_status(self.con, self.pid, "TL", b2, "aktiv")
        x = self.schritt("in zwei", bogen_id=b2, rang=1)
        v = self.schritt("vorher", bogen_id=b1, rang=9, agent="CC2")
        y = self.schritt("in eins", bogen_id=b1, rang=5, nach=[v])
        z = self.schritt("in eins frei", bogen_id=b1, rang=7)
        self.assertEqual(planung.naechster(self.con, self.pid, "CC1")["id"], z)        # y wartet auf v, v gehört CC2
        n = planung.naechster(self.con, self.pid, "CC1", nehmen=True)
        self.assertEqual((n["id"], n["status"]), (z, "laeuft"))
        self.assertEqual(planung.naechster(self.con, self.pid, "CC1")["id"], x)
        self.assertIsNotNone(y)


class Prognose(Grund):
    def test_ampel_aus_durchsatz_und_mensch_eigener_durchsatz(self):
        heute = datetime.date(2026, 11, 2)
        bid = self.bogen(zieldatum="2026-11-05")
        planung.bogen_status(self.con, self.pid, "TL", bid, "aktiv")
        for i in range(14):                                   # CC1 schafft 2 je Tag
            for _ in range(2):
                a = kern.aufgabe_neu(self.con, self.pid, "TL", "alt", "CC1")
                self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'x', fertig_utc = ? WHERE id = ?",
                                 ((heute - datetime.timedelta(days=i + 1)).isoformat() + "T10:00:00Z", a))
        for _ in range(4):
            self.schritt(bogen_id=bid, agent="CC1")
        p = planung.prognose(self.con, self.pid, laeufe=200, heute=heute, zufall=random.Random(1))
        self.assertEqual(p["boegen"][bid]["p50"], "2026-11-04")
        self.assertEqual(p["boegen"][bid]["ampel"], "gruen")
        m = self.schritt(bogen_id=bid, agent="Entwickler")      # der Mensch hat (noch) keinen Durchsatz → langsam
        p = planung.prognose(self.con, self.pid, laeufe=200, heute=heute, zufall=random.Random(1))
        self.assertEqual(p["boegen"][bid]["ampel"], "rot")
        self.assertGreater(p["schritte"][m]["p50"], "2026-11-05")

    def test_vorgaenger_verschiebt_den_nachfolger(self):
        bid = self.bogen()
        a = self.schritt(bogen_id=bid, agent="CC1")
        b = self.schritt(bogen_id=bid, agent="CC2", nach=[a])
        p = planung.prognose(self.con, self.pid, laeufe=100, zufall=random.Random(2))
        self.assertGreater(p["schritte"][b]["p50"], p["schritte"][a]["p50"])


class CheckUndEingang(Grund):
    def test_plan_check_findet_luecken(self):
        bid = self.bogen()
        planung.bogen_status(self.con, self.pid, "TL", bid, "aktiv")
        planung.spec_schreiben(self.con, self.pid, "TL", bid, "anforderungen", "R1 a\nR2 b")
        self.schritt(bogen_id=bid, anforderungen="R1", komplexitaet=9)
        planung.risiko_setzen(self.con, self.pid, "TL", titel="Speicher knapp", wahrscheinlichkeit=4, auswirkung=4)
        texte = " | ".join(x["text"] for x in planung.pruefen(self.con, self.pid))
        for erwartet in ("Kein Projektziel", "kein prüfbares Abnahmekriterium", "Anforderung R2 wird von keinem Schritt",
                         "keine Abnahmekriterien", "besser teilen", "ohne Maßnahme"):
            self.assertIn(erwartet, texte)
        self.assertNotIn("Anforderung R1", texte)
        self.assertEqual(planung.status(self.con, self.pid)["risiko"], "rot")

    def test_wartet_auf_den_menschen(self):
        bid = self.bogen()
        planung.spec_schreiben(self.con, self.pid, "TL", bid, "anforderungen", "R1")
        planung.spec_vorlegen(self.con, self.pid, "TL", bid, "anforderungen")
        aid = self.schritt(agent="CC1", verantwortlich="Entwickler")
        planung.plan_vorlegen(self.con, self.pid, "CC1", aid, "Plan")
        self.schritt("Testen am Handy", agent="Entwickler")
        f = planung.freigaben_offen(self.con, self.pid)
        self.assertEqual((len(f["spezifikationen"]), len(f["plaene"]), len(f["eigene"])), (1, 1, 1))


class Uebernahme(unittest.TestCase):
    def test_alte_textabhaengigkeiten_werden_uebernommen(self):
        with tempfile.TemporaryDirectory() as d:
            con = db.anlegen(os.path.join(d, "t.db"))
            with db.schreiben(con):
                pid = db.einfuegen(con, "projekt", name="P", angelegt_utc=db.jetzt())
            ids = [kern.aufgabe_neu(con, pid, "TL", f"A{i}") for i in range(3)]
            con.execute("UPDATE aufgabe SET abhaengig_von = ? WHERE id = ?", (f"{ids[0]}, A{ids[1]}", ids[2]))
            con.execute("UPDATE aufgabe SET abhaengig_von = 'TL-Wort' WHERE id = ?", (ids[1],))
            with open(os.path.join(os.path.dirname(db.__file__), "migration_7.sql"), encoding="utf-8") as f:
                m = f.read()
            con.execute(m[m.index("INSERT OR IGNORE INTO abhaengigkeit"):])
            self.assertEqual(planung.vorgaenger(con, ids[2]), [ids[0], ids[1]])
            self.assertEqual(planung.vorgaenger(con, ids[1]), [])
            con.close()


if __name__ == "__main__":
    unittest.main()
