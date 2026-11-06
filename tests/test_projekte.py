"""Tests für mehrere Projekte in einer AMW (→ doc/plan-projektwahl.md): Projekt der Agenten, Brücke, Push je Projekt,
Startskript, Verbrauch."""
import contextlib
import io
import json
import os
import tempfile
import time
import unittest
from unittest import mock

from amw import bruecke, cli, db, kern, push, statusline, steuerung


class ZweiProjekte(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        pfad = os.path.join(self.ordner.name, "amw.db")
        p = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name, "AMW_DB": pfad})
        p.start()
        self.addCleanup(p.stop)
        from amw import abgleich
        v = mock.patch.dict(abgleich.VERZEICHNIS, {"projekte": [], "stand": 0.0})      # nichts aus anderen Tests
        v.start()
        self.addCleanup(v.stop)
        for k in ("AMW_PROJEKT", "AMW_AGENT"):
            if k in os.environ:
                q = mock.patch.dict(os.environ)
                q.start()
                self.addCleanup(q.stop)
                os.environ.pop(k)
        self.con = db.anlegen()
        with db.schreiben(self.con):
            self.a = db.einfuegen(self.con, "projekt", name="Webshop", angelegt_utc=db.jetzt())
            self.b = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        for pid, kennungen in ((self.a, ("TL", "Shop1")), (self.b, ("TL", "Spiel1"))):
            for k in kennungen:
                kern.agent_neu(self.con, pid, k, rolle="lead" if k == "TL" else None)

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def cli(self, *args):
        aus, fehler = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(fehler):
            rc = cli.main(list(args))
        return rc, aus.getvalue() + fehler.getvalue()

    def posteingang(self, pid):
        return [r[0] for r in self.con.execute("SELECT kurz FROM nachricht WHERE projekt_id = ? ORDER BY id", (pid,))]


class ProjektDerAgenten(ZweiProjekte):
    def test_projekt_aus_name_kennung_oder_eindeutiger_kennung(self):
        uid = self.con.execute("SELECT uid FROM projekt WHERE id = ?", (self.b,)).fetchone()[0]
        self.assertEqual(db.projekt_fuer(self.con, "Spiel"), self.b)
        self.assertEqual(db.projekt_fuer(self.con, uid), self.b)                     # so steht es online
        self.assertEqual(db.projekt_fuer(self.con, None, "Shop1"), self.a)
        self.assertEqual(db.projekt_fuer(self.con, None, "Spiel1"), self.b)
        with self.assertRaisesRegex(LookupError, r"mehrere Projekte \(Webshop, Spiel\)"):
            db.projekt_fuer(self.con, None, "TL")                                    # gibt es in beiden
        with self.assertRaises(LookupError):
            db.projekt_fuer(self.con, None, None)

    def test_agenten_befehl_ohne_projekt_landet_im_projekt_der_kennung(self):
        # vorher: „mehrere oder keine Projekte“ für jeden Befehl, sobald es ein zweites Projekt gab
        rc, aus = self.cli("posten", "--an", "TL", "--art", "info", "--kurz", "aus dem Shop", "--von", "Shop1")
        self.assertEqual(rc, 0, aus)
        rc, aus = self.cli("posten", "--an", "TL", "--art", "info", "--kurz", "aus dem Spiel", "--von", "Spiel1")
        self.assertEqual(rc, 0, aus)
        self.assertEqual((self.posteingang(self.a), self.posteingang(self.b)), (["aus dem Shop"], ["aus dem Spiel"]))
        rc, aus = self.cli("posten", "--an", "Shop1", "--art", "info", "--kurz", "x", "--von", "TL")
        self.assertNotEqual(rc, 0)
        self.assertIn("mehrere Projekte (Webshop, Spiel)", aus)
        rc, aus = self.cli("posten", "--an", "Spiel1", "--art", "info", "--kurz", "vom TL", "--von", "TL", "--projekt", "Spiel")
        self.assertEqual(rc, 0, aus)
        with mock.patch.dict(os.environ, {"AMW_PROJEKT": "Webshop"}):
            rc, aus = self.cli("posten", "--an", "Shop1", "--art", "info", "--kurz", "Umgebung", "--von", "TL")
        self.assertEqual(rc, 0, aus)
        self.assertEqual(self.posteingang(self.b)[-1], "vom TL")
        self.assertEqual(self.posteingang(self.a)[-1], "Umgebung")

    def test_startskript_setzt_das_projekt(self):
        p = steuerung.profil(self.con, self.b, "Spiel1")
        self.assertIn("$env:AMW_PROJEKT = 'Spiel'", steuerung.befehl(p, None, "1111-2222"))

    def test_verbrauch_gleiche_kennung_zaehlt_nur_im_eigenen_projekt(self):
        zeit = lambda m: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - m * 60))
        for pid, usd in ((self.a, 2.0), (self.b, 5.0)):
            aid = self.con.execute("SELECT id FROM agent WHERE projekt_id = ? AND kennung = 'TL'", (pid,)).fetchone()[0]
            with db.schreiben(self.con):
                sid = db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung=f"s-{pid}", gestartet_utc=db.jetzt())
                for minuten, wert in ((10, 1.0), (0, 1.0 + usd)):                  # erster Messpunkt zählt nicht
                    db.einfuegen(self.con, "verbrauch", sitzung_id=sid, agent="TL", kosten_usd=wert, zeit_utc=zeit(minuten))
        summe = lambda pid: sum(statusline.verbrauch_tage(self.con, pid, 2)["agenten"].get("TL", {}).values())
        self.assertEqual((summe(self.a), summe(self.b)), (2.0, 5.0))


class Bruecke(ZweiProjekte):
    def setUp(self):
        super().setUp()
        self.eingang = os.path.join(self.ordner.name, "eingang-tl")

    def einwerfen(self, name, inhalt):
        ordner = os.path.join(self.eingang, "befehle")
        os.makedirs(ordner, exist_ok=True)
        with open(os.path.join(ordner, name), "w", encoding="utf-8") as f:
            json.dump(inhalt, f)
        alt = time.time() - 5
        os.utime(os.path.join(ordner, name), (alt, alt))

    def ergebnis(self, stamm):
        with open(os.path.join(self.eingang, "erledigt", stamm + ".ergebnis.json"), encoding="utf-8") as f:
            return json.load(f)

    def test_projekt_in_der_befehlsdatei(self):
        self.einwerfen("ohne.json", {"befehl": "posten", "an": "Spiel1", "art": "info", "kurz": "ohne Projekt"})
        self.einwerfen("mit.json", {"befehl": "posten", "an": "Spiel1", "art": "info", "kurz": "mit Projekt", "projekt": "Spiel"})
        bruecke.befehle(self.eingang)
        self.assertIn("mehrere Projekte", self.ergebnis("ohne")["fehler"])            # TL gibt es in beiden: nicht raten
        self.assertEqual(self.ergebnis("mit")["rc"], 0)
        self.assertEqual(self.posteingang(self.b), ["mit Projekt"])
        s = self.con.execute("SELECT a.projekt_id FROM sitzung s JOIN agent a ON a.id = s.agent_id"
                             " WHERE s.schluessel_datei IS NULL AND s.zustand = 'aktiv'").fetchall()
        self.assertEqual([r[0] for r in s], [self.b])                                   # Puls nur im genannten Projekt


class PushJeProjekt(ZweiProjekte):
    def setUp(self):
        super().setUp()
        self.gesendet = []
        push.speichern({"ntfy": {"an": True, "topic": "amw-test"}, "link": "https://amw.example/"})
        push.speichern({"an": True})
        self.cfg = push.laden()
        self.cfg["seit_utc"] = "2000-01-01T00:00:00Z"
        self.cfg["ereignisse"]["rueckblick"] = False
        s = mock.patch.dict(push.SENDER, {"ntfy": lambda c, titel, text, prio, link: self.gesendet.append((titel, link))})
        s.start()
        self.addCleanup(s.stop)

    def test_jedes_projekt_bekommt_seine_meldung_mit_name_und_link(self):
        # vorher: die Runde des einen Projekts hielt die Meldung des anderen für „überholt“ – sie ging nie raus
        for pid in (self.a, self.b):
            kern.frage_neu(self.con, pid, "TL", "entwickler", "Wie?", [("A", "ja")], "A", "weil", geprueft="keine Treffer")
        push.runde(self.con, self.a, self.cfg)
        push.runde(self.con, self.b, self.cfg)
        self.assertEqual(sorted(t.split(" · ")[0] for t, _ in self.gesendet), ["AMW: Spiel", "AMW: Webshop"])
        uid = self.con.execute("SELECT uid FROM projekt WHERE id = ?", (self.b,)).fetchone()[0]
        self.assertIn(f"https://amw.example/?projekt={uid}#", [l for t, l in self.gesendet if "Spiel" in t][0])
        stand = self.con.execute("SELECT projekt_id, ergebnis FROM push_versand ORDER BY projekt_id").fetchall()
        self.assertEqual([tuple(r) for r in stand], [(self.a, "gesendet"), (self.b, "gesendet")])

    def test_ein_projekt_ohne_namen_im_titel(self):
        with db.schreiben(self.con):
            self.con.execute("DELETE FROM agent WHERE projekt_id = ?", (self.b,))
            self.con.execute("DELETE FROM projekt WHERE id = ?", (self.b,))
        kern.frage_neu(self.con, self.a, "TL", "entwickler", "Wie?", [("A", "ja")], "A", "weil", geprueft="keine Treffer")
        push.runde(self.con, self.a, self.cfg)
        self.assertNotIn("Webshop", self.gesendet[0][0])
        self.assertNotIn("?projekt=", self.gesendet[0][1])



class Workbench(ZweiProjekte):
    def test_projektliste_mit_fragen_farbe_und_auswahl(self):
        from amw import workbench
        kern.frage_neu(self.con, self.b, "TL", "entwickler", "Wie?", [("A", "ja")], "A", "weil", geprueft="keine Treffer")
        kern.projekt_einstellen(self.con, self.b, "Entwickler", farbe="gruen")
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.b, "Entwickler", farbe="pink")
        d = workbench.daten_projekte(self.con, self.b)
        self.assertEqual([(p["name"], p["fragen"], p["farbe"], p["aktiv"]) for p in d["projekte"]],
                         [("Webshop", 0, "bernstein", False), ("Spiel", 1, "gruen", True)])
        self.assertTrue(d["rechner"])

    def test_fremder_gpu_lauf_ohne_inhalt(self):
        from amw import betrieb, workbench
        betrieb.lauf_start(self.con, self.b, "Spiel1", "geheimer Titel", gpu=True, speicher_frei=50)
        d = workbench.daten_betrieb(self.con, self.a)
        self.assertEqual([(f["projekt"], f["gpu"]) for f in d["fremd"]], [("Spiel", 1)])
        self.assertNotIn("geheimer Titel", json.dumps(d["fremd"]))
        self.assertEqual(workbench.daten_betrieb(self.con, self.b)["fremd"], [])

    def test_name_des_rechners(self):
        from amw import einstellungen
        einstellungen.speichern({"rechner": "  Werkstatt   PC "})
        self.assertEqual(einstellungen.wert("rechner"), "Werkstatt PC")
        with self.assertRaises(ValueError):
            einstellungen.speichern({"rechner": "x" * 41})



class ZweiRechner(unittest.TestCase):
    """Zwei AMW-Installationen (je eigene Datenbank) an einem Online-Speicher: jede hält nur ihre Projekte."""
    @staticmethod
    def png():
        """1 x 1 Pixel, echtes PNG."""
        import struct, zlib
        st = lambda typ, d: struct.pack(">I", len(d)) + typ + d + struct.pack(">I", zlib.crc32(typ + d))
        return (bytes([137]) + b"PNG" + bytes([13, 10, 26, 10]) + st(b"IHDR", struct.pack(">IIBBBBB", 1, 1, 8, 2, 0, 0, 0))
                + st(b"IDAT", zlib.compress(bytes(4))) + st(b"IEND", b""))

    def setUp(self):
        from amw import abgleich
        self.ordner = tempfile.TemporaryDirectory()
        a = os.path.join(self.ordner.name, "a.db")
        p = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name, "AMW_DB": a})
        p.start()
        self.addCleanup(p.stop)
        self.cons, self.pids, self.uids = [], [], []
        for datei, name in (("a.db", "Webshop"), ("b.db", "Spiel")):
            con = db.anlegen(os.path.join(self.ordner.name, datei))
            with db.schreiben(con):
                pid = db.einfuegen(con, "projekt", name=name, angelegt_utc=db.jetzt())
            kern.agent_neu(con, pid, "Lead", rolle="lead")
            self.cons.append(con)
            self.pids.append(pid)
            self.uids.append(con.execute("SELECT uid FROM projekt WHERE id = ?", (pid,)).fetchone()[0])
        self.sp = abgleich.SqliteSpeicher(os.path.join(self.ordner.name, "online.db"))
        self.ab = [abgleich.Abgleich(c, self.sp) for c in self.cons]
        self.ab[0].schema()
        self.sp.ausfuehren([("INSERT INTO ansicht (weg, inhalt, pruef, stand_utc) VALUES ('/api/start', '{}', 'x', 'x')", [])])
        self.ab[0].schema()
        self.ab[1].schema()
        self.addCleanup(abgleich.VERZEICHNIS.update, {"projekte": [], "stand": 0.0})

    def tearDown(self):
        for c in self.cons:
            c.close()
        self.ordner.cleanup()

    def hochladen(self, i):
        from amw import einstellungen
        einstellungen.speichern({"rechner": ["Werkstatt", "Laptop"][i]})
        return self.ab[i].hochladen()

    def zeilen(self, sql, args=()):
        return self.sp.ausfuehren([(sql, list(args))])[0]

    def test_verzeichnis_ansichten_und_altbestand(self):
        self.hochladen(0)
        self.hochladen(1)
        self.assertEqual(self.zeilen("SELECT name, rechner FROM projekt ORDER BY name"), [["Spiel", "Laptop"], ["Webshop", "Werkstatt"]])
        for uid in self.uids:                                   # keiner überschreibt oder löscht den anderen
            self.assertEqual(len(self.zeilen("SELECT 1 FROM ansicht WHERE weg = ?", [f"{uid}:/api/start"])), 1)
        self.assertEqual(self.zeilen("SELECT count(*) FROM ansicht WHERE weg LIKE '/%'"), [[0]])   # alte Schlüssel weg
        from amw import push, workbench
        push.speichern({"link": "https://amw.example/"})
        fern = [p for p in workbench.daten_projekte(self.cons[0], self.pids[0])["projekte"] if p.get("fern")]
        self.assertEqual([(p["name"], p["rechner"], p["online"]) for p in fern],
                         [("Spiel", "Laptop", f"https://amw.example/?projekt={self.uids[1]}")])

    def test_handy_befehl_nur_auf_dem_rechner_des_projekts(self):
        self.sp.ausfuehren([("INSERT INTO eingang (zeit_utc, weg, daten, projekt) VALUES (?, '/api/halt', ?, ?)",
                             [db.jetzt(), json.dumps({"fuer": "alle", "text": "unterwegs"}), self.uids[1]])])
        self.assertEqual(self.ab[0].eingang(), 0)
        self.assertEqual(self.ab[1].eingang(), 1)
        halt = lambda i: self.cons[i].execute("SELECT count(*) FROM sperre WHERE art = 'halt'").fetchone()[0]
        self.assertEqual((halt(0), halt(1)), (0, 1))

    def test_gleiche_datei_in_zwei_projekten_bleibt_bis_keiner_sie_braucht(self):
        from amw import dokumente
        bild = os.path.join(self.ordner.name, "bild.png")
        with open(bild, "wb") as f:
            f.write(self.png())
        dids = [dokumente.ablegen(c, p, "Lead", bild, online=True) for c, p in zip(self.cons, self.pids)]
        for ab in self.ab:
            ab.dateien()
        self.assertEqual(self.zeilen("SELECT count(*) FROM datei"), [[1]])
        self.assertEqual(sorted(r[0] for r in self.zeilen("SELECT projekt FROM datei_projekt")), sorted(self.uids))
        dokumente.online_setzen(self.cons[0], self.pids[0], "Lead", dids[0], False)
        self.ab[0].dateien()
        self.assertEqual(self.zeilen("SELECT count(*) FROM datei"), [[1]])     # das andere Projekt braucht sie noch
        dokumente.online_setzen(self.cons[1], self.pids[1], "Lead", dids[1], False)
        self.ab[1].oben_laden()
        self.ab[1].dateien()
        self.assertEqual(self.zeilen("SELECT count(*) FROM datei"), [[0]])


if __name__ == "__main__":
    unittest.main()
