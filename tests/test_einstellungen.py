"""Tests für das Zahnrad: Einstellungen des PCs, Projekt, Agenten, Online-Seite; was nur am PC geändert werden darf."""
import json
import os
import tempfile
import unittest

from amw import abgleich, aktionen, db, einstellungen, kern, workbench


class Einstellungen(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.alt = {k: os.environ.get(k) for k in ("AMW_DB", "LOCALAPPDATA")}
        os.environ["AMW_DB"] = os.path.join(self.ordner.name, "amw.db")
        os.environ["LOCALAPPDATA"] = self.ordner.name
        self.con = db.anlegen()
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.online = os.path.join(self.ordner.name, "online.db")
        os.makedirs(os.path.join(self.ordner.name, "amw"))
        with open(abgleich.zugang_pfad(), "w", encoding="utf-8") as f:
            json.dump({"sqlite": self.online, "url": "libsql://x.turso.io", "token": "GEHEIM-123"}, f)
        abgleich.SqliteSpeicher(self.online).ausfuehren([(s, []) for s in abgleich.SCHEMA])

    def tearDown(self):
        self.con.close()
        for k, v in self.alt.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        self.ordner.cleanup()

    def tun(self, teil, daten, kanal="seite"):
        return aktionen.ausfuehren(self.con, self.pid, f"/api/einstellungen/{teil}", daten, kanal)

    def test_pc_vorgaben_speichern_und_pruefen(self):
        self.assertEqual(einstellungen.laden()["port"], 8780)
        self.tun("pc", {"port": 8790, "aufsicht_s": 45, "bruecke_an": "aus"})
        e = einstellungen.laden()
        self.assertEqual((e["port"], e["aufsicht_s"], e["bruecke_an"]), (8790, 45, False))
        with self.assertRaises(aktionen.Ungueltig):
            self.tun("pc", {"port": 80})
        with self.assertRaises(aktionen.Ungueltig):
            self.tun("pc", {"db_pfad": "C:/gibt/es/nicht/x.db"})
        with self.assertRaises(aktionen.Ungueltig):
            self.tun("pc", {"unbekannt": 1})

    def test_pc_und_turso_nicht_aus_dem_netz(self):
        for teil in ("pc", "turso"):
            with self.assertRaises(aktionen.Ungueltig):
                self.tun(teil, {"port": 9000}, kanal="netz")
        self.assertEqual(einstellungen.laden()["port"], 8780)

    def test_projekt_und_agenten(self):
        self.tun("projekt", {"takt_min": 60, "speicher_grenze_gb": 12}, kanal="netz")
        e = json.loads(self.con.execute("SELECT einstellungen FROM projekt").fetchone()[0])
        self.assertEqual((e["takt_min"], e["speicher_grenze_gb"]), (60, 12))
        with self.assertRaises(kern.AmwFehler):
            self.tun("projekt", {"takt_min": 5000})
        self.tun("agent", {"kennung": "CC1", "soll": "ruht", "rolle": "", "empfaengt_rund": False, "puls_grenze_s": 600})
        a = self.con.execute("SELECT soll, rolle, empfaengt_rund, puls_grenze_s FROM agent WHERE kennung = 'CC1'").fetchone()
        self.assertEqual(tuple(a), ("ruht", None, 0, 600))
        self.tun("agent", {"kennung": "CC9", "neu": True, "grenzen": "nur Doku"}, kanal="netz")
        self.assertEqual(self.con.execute("SELECT zustaendig FROM agent WHERE kennung = 'CC9'").fetchone()[0], "nur Doku")   # „grenzen“ = früherer Name
        self.tun("agent", {"kennung": "CC9", "fachgebiet": "Doku", "arbeitsweise": "desktop", "fasst_nicht_an": "Code"})
        self.assertEqual(tuple(self.con.execute("SELECT rolle, fachgebiet, arbeitsweise, fasst_nicht_an FROM agent WHERE kennung = 'CC9'").fetchone()),
                         (None, "Doku", "desktop", "Code"))
        for falsch in ({"kennung": "CC9", "neu": True}, {"kennung": "Entwickler", "neu": True},
                       {"kennung": "CC1", "soll": "vielleicht"}, {"kennung": "CC1", "id": 3}):
            with self.assertRaises((kern.AmwFehler, aktionen.Ungueltig)):
                self.tun("agent", falsch)
        with self.assertRaises(kern.AmwFehler):                       # Agenten selbst dürfen das nicht
            kern.agent_einstellen(self.con, self.pid, "CC1", "CC1", soll="aus")

    def test_online_seite_im_online_speicher(self):
        self.tun("web", {"leerlauf_min": 60, "fehl_je_ip": 4}, kanal="netz")
        self.assertEqual(abgleich.web_einstellungen(abgleich.SqliteSpeicher(self.online))["leerlauf_min"], 60)
        with self.assertRaises(aktionen.Ungueltig):
            self.tun("web", {"leerlauf_min": 1})

    def test_ansicht_ohne_geheimnisse(self):
        d = workbench.daten_einstellungen(self.con, self.pid)
        self.assertNotIn("GEHEIM-123", json.dumps(d))
        self.assertTrue(d["turso"]["schluessel_gespeichert"])
        self.assertEqual(d["web"]["leerlauf_min"], 30)
        self.assertIn("/api/einstellungen", abgleich.ansichten(self.con, self.pid))


if __name__ == "__main__":
    unittest.main()
