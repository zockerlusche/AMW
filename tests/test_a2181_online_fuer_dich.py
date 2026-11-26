"""A2181: Die Online-Projektliste zeigt dieselbe Zahl „für dich“ wie am PC – der Abgleich rechnet sie einmal je Runde und Projekt (im Merker
der Startdaten, der Themenstand also nicht doppelt) und gibt sie mit jeder /api/projekte-Ansicht hoch."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import sqlite3
import unittest

from amw import abgleich, db, fuer_dich, kern, workbench
from tests.test_a2081_einmal import Grund


class OnlineGleichPc(Grund):
    def setUp(self):
        super().setUp()
        self.bestand()
        with db.schreiben(self.con):
            self.zweit = db.einfuegen(self.con, "projekt", name="Shop", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.zweit, "TL", rolle="lead")
        kern.frage_neu(self.con, self.zweit, "TL", "entwickler", "Versand ins Ausland?", [("A", "ja"), ("B", "nein")], "A", "weil",
                       geprueft="keine Treffer")
        self.online = os.path.join(self.ordner.name, "online.db")

    def test_online_gleich_pc_und_einmal_je_runde(self):
        rufe = self.zaehlen(fuer_dich, "sammeln")
        ab = abgleich.Abgleich(self.con, abgleich.SqliteSpeicher(self.online))           # wie der Dienst: alle Projekte einer Runde
        ab.schema()
        ab.hochladen(alle=True)
        projekte = [r[1] for r in self.con.execute("SELECT id, uid FROM projekt").fetchall()]
        self.assertEqual(len(rufe), len(projekte))                                       # einmal je Projekt und Runde, nicht N×N
        pc = {p["uid"]: p["fuer_dich"] for p in workbench.daten_projekte(self.con, self.pid)["projekte"] if not p.get("fern")}
        o = sqlite3.connect(self.online)
        try:
            for uid in projekte:
                online = json.loads(o.execute("SELECT inhalt FROM ansicht WHERE weg = ?", (f"{uid}:/api/projekte",)).fetchone()[0])
                with self.subTest(uid=uid):
                    self.assertEqual({p["uid"]: p.get("fuer_dich") for p in online["projekte"] if p["uid"] in pc}, pc)
        finally:
            o.close()


if __name__ == "__main__":
    unittest.main()
