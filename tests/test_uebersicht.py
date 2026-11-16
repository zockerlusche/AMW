"""Übersicht und Fragen-Reiter (A1657, Marcel 14.11.): Daten der Karten „Stand“, „Läuft gerade“, „Zustand“ und der
Reiter „Erledigt“; die Zeit der letzten Synchronisierung löst allein kein Hochladen aus."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import abgleich, db, herzschlag, kern, workbench


class Uebersicht(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
            b = db.einfuegen(self.con, "bogen", projekt_id=self.pid, nr=1, titel="Erste Version", status="aktiv", zieldatum="2026-12-01",
                              angelegt_von="TL", angelegt_utc=db.jetzt())
            db.einfuegen(self.con, "bogen", projekt_id=self.pid, nr=2, titel="Später", status="geplant", angelegt_von="TL",
                         angelegt_utc=db.jetzt())
            for i, st in enumerate(["fertig", "fertig", "laeuft", "wartet", "verworfen"]):
                db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel=f"T{i}", agent="CC1", status=st, einstufung="aktiv",
                             bogen_id=b, angelegt_utc=db.jetzt(), angelegt_von="TL")
            db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel="Logo", agent="CC1", status="wartet", einstufung="aktiv",
                         angelegt_utc=db.jetzt(), angelegt_von="TL")
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def gesund(self, alter=None):
        teile = [{"teil": "hauptschleife", "zustand": "gruen", "alter_s": 5}]
        if alter is not None:
            teile.append({"teil": "synchronisierung", "zustand": "gruen", "alter_s": alter})
        return {"teile": teile}

    def test_stand_und_zustand(self):
        u = workbench._uebersicht(self.con, self.pid, self.gesund(60))
        self.assertEqual([(b["titel"], b["gesamt"], b["fertig"], b["verworfen"]) for b in u["boegen"]], [("Erste Version", 5, 2, 1)])
        self.assertEqual(u["ohne_bogen"], 1)
        self.assertEqual(u["dienst"], "gruen")
        self.assertEqual(u["sync"]["zustand"], "gruen")
        self.assertIsNone(workbench._uebersicht(self.con, self.pid, self.gesund())["sync"])    # ohne Synchronisierung: aus

    def test_sync_zeit_laedt_allein_nicht_neu_hoch(self):
        a = workbench._uebersicht(self.con, self.pid, self.gesund(60))
        b = workbench._uebersicht(self.con, self.pid, self.gesund(600))
        self.assertNotEqual(a["sync"]["zeit_utc"], b["sync"]["zeit_utc"])
        self.assertEqual(abgleich._ruhig({"uebersicht": a}), abgleich._ruhig({"uebersicht": b}))

    def test_start_hat_die_uebersicht(self):
        with mock.patch.object(herzschlag, "gesundheit", return_value=self.gesund(30)):
            d = workbench.daten_start(self.con, self.pid)
        self.assertEqual(d["uebersicht"]["boegen"][0]["titel"], "Erste Version")

    def test_erledigte_fragen(self):
        with db.schreiben(self.con):
            for i, (st, art, antwort) in enumerate([("beantwortet", "option", "B"), ("verworfen", None, None), ("offen", None, None),
                                                    ("beantwortet", "text", "Lieber rot")]):
                db.einfuegen(self.con, "frage", projekt_id=self.pid, von="TL", an="entwickler", zeit_utc=f"2026-11-1{i}T10:00:00Z",
                             kurz=f"F{i}", optionen=json.dumps([{"kenn": "A", "text": "Blau"}, {"kenn": "B", "text": "Orange"}]),
                             status=st, antwort_art=art, antwort=antwort, antwort_utc=f"2026-11-1{i}T11:00:00Z" if st != "offen" else None)
        erl = workbench.daten_fragen_erledigt(self.con, self.pid)
        self.assertEqual([f["kurz"] for f in erl], ["F3", "F1", "F0"])                       # neueste zuerst, offene nicht
        self.assertEqual(erl[2]["option_text"], "Orange")
        self.assertNotIn("optionen", erl[0])
        leer = db.anlegen(os.path.join(self.ordner.name, "leer.db"))                          # auch online (eigene DB: die
        self.addCleanup(leer.close)                                                           # Meilensteine oben haben keine Spezifikation)
        with db.schreiben(leer):
            p = db.einfuegen(leer, "projekt", name="Leer", angelegt_utc=db.jetzt())
        self.assertIn("/api/fragen?erledigt=1", abgleich.ansichten(leer, p))

    def test_nachtraege_einer_frage_lassen_sich_als_gelesen_markieren(self):
        """A1837 (Marcel 16.11.: „kommt immer wieder als neu“): Nachträge zu einer Frage stehen nur unter Fragen – die Seite
        bekommt ihre Nummern (nachtrag_ids) und markiert sie beim Anzeigen; danach gelten sie nicht mehr als neu."""
        from amw import aktionen
        fid = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Welche Farbe?", [("A", "Blau"), ("B", "Orange")],
                             empfehlung="A", grund="ruhiger", geprueft="keine Treffer")
        kern.frage_nachtrag(self.con, self.pid, "TL", fid, "Orange ginge auch")
        f = next(x for x in workbench.daten_fragen(self.con, self.pid) if x["id"] == fid)
        self.assertEqual(len(f["nachtrag_ids"]), 1)
        aktionen.ausfuehren(self.con, self.pid, "/api/gelesen", {"ids": f["nachtrag_ids"]})
        f = next(x for x in workbench.daten_fragen(self.con, self.pid) if x["id"] == fid)
        self.assertEqual(f["nachtrag_ids"], [])
        self.assertEqual(next(x for x in workbench.daten_start(self.con, self.pid)["fragen"] if x["id"] == fid)["nachtraege"], 0)


if __name__ == "__main__":
    unittest.main()
