"""A1973 (#30742/#30743): Stil-Prüfung als Automatik – Befund je Regel 1–9 lesen, Zeile, Anstoßen nur mit Stil-Thema und Bildern,
Befund als Dokument und Meldung an den Prüfer, Grün mit Verstoß nur mit Begründung. Der Stil-Leser selbst ist gemockt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import betrieb, db, dokumente, kern, stil, themen


def befund(verstoesse=(), nicht=(), kleinprobe=False):
    return {"regeln": [{"nr": n, "urteil": "verstößt" if n in verstoesse else "nicht prüfbar" if n in nicht else "erfüllt",
                        "grund": "Spanne unter jeder Zeile" if n in verstoesse else "", "bild": "bild-D1-pc.png"} for n in range(1, 10)],
            "kleinprobe_noetig": kleinprobe}


class Lesen(unittest.TestCase):
    def test_json_auch_im_block_und_genau_neun_regeln(self):
        b = stil.befund_lesen("Hier:\n```json\n" + json.dumps(befund(verstoesse=(7,)), ensure_ascii=False) + "\n```")
        self.assertEqual([r["urteil"] for r in b["regeln"]].count("verstößt"), 1)
        self.assertEqual(stil.zeile(b), "Stil: 1 Verstoß – R7")
        self.assertEqual(stil.zeile(stil.befund_lesen(json.dumps(befund(), ensure_ascii=False))), "Stil: 9/9 erfüllt")
        self.assertEqual(stil.zeile(stil.befund_lesen(json.dumps(befund(nicht=(8,), kleinprobe=True), ensure_ascii=False))),
                         "Stil: 8/9 erfüllt · nicht prüfbar: R8 · Kleinprobe nötig?")
        mit_bestand = dict(befund(), bestand=["R5: „(Regel 4)“ zeigt Maschinerie"])            # Altes zählt nicht als Verstoß
        b = stil.befund_lesen(json.dumps(mit_bestand, ensure_ascii=False))
        self.assertEqual((stil.zeile(b), b["bestand"]), ("Stil: 9/9 erfüllt", ["R5: „(Regel 4)“ zeigt Maschinerie"]))
        self.assertIn("alter Bestand, zählt hier nicht", stil.bericht(1, b, "opus", 0.1))
        kaputt = befund()
        kaputt["regeln"] = kaputt["regeln"][:8]
        for text in ("keine Ahnung", json.dumps(kaputt), json.dumps({"regeln": [{"nr": 1, "urteil": "gut"}]})):
            with self.assertRaises(ValueError):
                stil.befund_lesen(text)


class Ablauf(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Paketliste", agent="CC1")
        with db.schreiben(self.con):
            self.prid = db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=self.aid, zweig="a1", sha="a" * 40,
                                     bauer="CC1", pruefer="TL", punkte="neue Texte: …", angefragt_utc=db.jetzt())
        u = mock.patch.dict(os.environ, {"AMW_STIL_AUS": ""})
        u.start()
        self.addCleanup(u.stop)

    def thema_und_bild(self):
        tid = themen.neu(self.con, self.pid, "TL", "Stil der Oberfläche", stil=True)
        tid = tid if isinstance(tid, int) else tid["id"]
        themen.pflegen(self.con, self.pid, "TL", tid, "REGELN FÜR JEDE SEITE\n1. …\n7. Details auf Klick, nie auf Vorrat.")
        bild = os.path.join(self.ordner.name, "pc.png")
        with open(bild, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n" + b"0" * 32)
        dokumente.ablegen(self.con, self.pid, "CC1", bild, titel="Paketliste PC", art="bild", aufgabe=self.aid)

    def test_anstossen_nur_mit_stil_thema_und_bildern(self):
        gestartet = []
        with mock.patch.object(stil, "STARTER", lambda pid, prid: gestartet.append(prid) or 4711):
            self.assertEqual(stil.anstossen(self.con, self.pid, self.prid, True), "")          # kein Stil-Thema, kein Bild
            self.thema_und_bild()
            self.assertEqual(stil.anstossen(self.con, self.pid, self.prid, False), "")         # nichts Sichtbares
            zeile = stil.anstossen(self.con, self.pid, self.prid, True)
        self.assertIn("Stil: wird geprüft", zeile)
        self.assertEqual(gestartet, [self.prid])
        e = json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE art = ?", (stil.ANGESTOSSEN,)).fetchone()[0])
        self.assertEqual((e["pruefung"], e["prozess"]), (self.prid, 4711))

    def test_befund_dokument_meldung_und_gruen_nur_mit_begruendung(self):
        self.thema_und_bild()
        b = stil.befund_lesen(json.dumps(befund(verstoesse=(7, 3)), ensure_ascii=False))
        stil.abschliessen(self.con, self.pid, self.prid, {"befund": b, "modell": "opus", "usd": 0.42}, lauf=99)
        e = stil.letzter_befund(self.con, self.pid, self.prid)
        self.assertEqual((e["verstoesse"], e["usd"], e["lauf"]), ([3, 7], 0.42, 99))
        d = self.con.execute("SELECT titel, art FROM dokument WHERE id = ?", (e["dokument"],)).fetchone()
        self.assertEqual((d["art"], d["titel"]), ("bericht", f"Stil-Befund P{self.prid}: Stil: 2 Verstöße – R3, R7"))
        m = self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang x ON x.nachricht_id = n.id WHERE x.agent = 'TL'"
                             " ORDER BY n.id DESC").fetchone()
        self.assertEqual(m[0], f"P{self.prid} Stil: 2 Verstöße – R3, R7")
        with self.assertRaisesRegex(kern.AmwFehler, "Grün nur mit Begründung"):
            betrieb.pruefung_ergebnis(self.con, self.pid, "TL", self.prid, "gruen")
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", self.prid, "gruen", "R3/R7 sind alter Bestand, eigenes Stil-Paket")
        self.assertEqual(self.con.execute("SELECT ergebnis FROM pruefung WHERE id = ?", (self.prid,)).fetchone()[0], "gruen")

    def test_fehler_geht_an_den_pruefer_und_sperrt_nicht(self):
        stil.abschliessen(self.con, self.pid, self.prid, {"fehler": "kein Ergebnis (rc 1)", "modell": "opus"})
        m = self.con.execute("SELECT n.kurz FROM nachricht n JOIN empfang x ON x.nachricht_id = n.id WHERE x.agent = 'TL'"
                             " ORDER BY n.id DESC").fetchone()
        self.assertIn("Stil-Prüfung ging nicht", m[0])
        betrieb.pruefung_ergebnis(self.con, self.pid, "TL", self.prid, "gruen")              # ohne Befund: wie bisher


if __name__ == "__main__":
    unittest.main()
