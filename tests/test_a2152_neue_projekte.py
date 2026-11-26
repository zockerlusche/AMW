"""A2152 (M14, D1974; TH155, TH164): neue Projekte bekommen meilenstein_fertig=automatisch und verteilen=an – auf allen drei
Anlegewegen (Einrichtung, amw projekt neu, amw init --projekt); bestehende Projekte bleiben, wie sie sind."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os

from amw import aktionen, assistent, db, kern
from tests.test_projekte import ZweiProjekte

NEU = {"meilenstein_fertig": "automatisch", "verteilen": "an"}


class NeueProjekte(ZweiProjekte):
    def werte(self, name):
        pid = db.projekt_id(self.con, name)
        return {k: kern.projekt_wahl(self.con, pid, k) for k in NEU}

    def test_einrichtung(self):
        ordner = os.path.join(self.ordner.name, "neu")
        os.makedirs(ordner)
        assistent.schnell("Neu", "Chef", ["CC1"], ordner, startskript=os.path.join(self.ordner.name, "s.ps1"), ausgabe=lambda x: None,
                          farbe="blau", regelwerk={"sprache": "de"})
        self.assertEqual(self.werte("Neu"), NEU)
        pid = db.projekt_id(self.con, "Neu")
        self.assertEqual((kern.projekt_wahl(self.con, pid, "farbe"), kern.projekt_wahl(self.con, pid, "versionen")), ("blau", "pflicht"))

    def test_workbench_neues_projekt(self):
        ordner = os.path.join(self.ordner.name, "seite")
        os.makedirs(ordner)
        aktionen.projekt_neu(self.con, {"name": "Seite", "ordner": ordner, "lead": "Chef"})
        self.assertEqual(self.werte("Seite"), NEU)

    def test_projekt_neu(self):
        rc, aus = self.cli("projekt", "neu", "Filiale")
        self.assertEqual(rc, 0, aus)
        self.assertEqual(self.werte("Filiale"), NEU)

    def test_init_mit_projekt(self):
        pfad = os.path.join(self.ordner.name, "zweite.db")
        os.environ["AMW_DB"] = pfad                      # setUp hat AMW_DB schon per patch.dict gesetzt – der räumt es wieder weg
        rc, aus = self.cli("init", "--projekt", "Start")
        self.assertEqual(rc, 0, aus)
        con = db.verbinde()
        try:
            pid = db.projekt_id(con, "Start")
            self.assertEqual({k: kern.projekt_wahl(con, pid, k) for k in NEU}, NEU)
        finally:
            con.close()

    def test_bestehende_projekte_bleiben(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps({"verteilen": "aus"}), self.b))
        vorher = {r[0]: r[1] for r in self.con.execute("SELECT id, einstellungen FROM projekt")}
        rc, aus = self.cli("projekt", "neu", "Filiale")
        self.assertEqual(rc, 0, aus)
        self.assertEqual({r[0]: r[1] for r in self.con.execute("SELECT id, einstellungen FROM projekt WHERE id IN (?, ?)",
                                                                   (self.a, self.b))}, {self.a: vorher[self.a], self.b: vorher[self.b]})
        self.assertEqual({k: kern.projekt_wahl(self.con, self.a, k) for k in NEU}, {"meilenstein_fertig": "vorschlag", "verteilen": "vorschlag"})
        self.assertEqual(kern.projekt_wahl(self.con, self.b, "verteilen"), "aus")


if __name__ == "__main__":
    import unittest
    unittest.main()
