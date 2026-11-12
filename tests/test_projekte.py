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

    def test_jedes_projekt_hat_seine_bruecke(self):
        alle = bruecke.bruecken(self.con)
        self.assertEqual([(b["name"], os.path.basename(b["eingang"]), os.path.basename(b["kopie"]), b["von"]) for b in alle],
                         [("Webshop", "eingang-tl", "tl_lesen.db", "TL"), ("Spiel", "eingang-spiel", "lesen-spiel.db", "TL")])
        spiel = os.path.join(self.ordner.name, "eingang-spiel")
        self.eingang = spiel
        self.einwerfen("ohne.json", {"befehl": "posten", "an": "Spiel1", "art": "info", "kurz": "ohne Projekt"})
        self.einwerfen("fremd.json", {"befehl": "posten", "an": "Shop1", "art": "info", "kurz": "x", "projekt": "Webshop"})
        self.einwerfen("args.json", {"args": ["posten", "--an", "Shop1", "--art", "info", "--kurz", "y", "--projekt", "Webshop"]})
        bruecke.befehle(spiel, "Spiel", "TL")
        self.assertEqual(self.ergebnis("ohne")["rc"], 0, self.ergebnis("ohne"))      # TL in beiden: die Brücke weiß es
        self.assertEqual(self.posteingang(self.b), ["ohne Projekt"])
        for stamm in ("fremd", "args"):
            self.assertIn("gehört zum Projekt Spiel", self.ergebnis(stamm)["fehler"])
        self.assertEqual(self.posteingang(self.a), [])

    def test_lese_kopie_nur_mit_dem_eigenen_projekt(self):
        kern.posten(self.con, self.a, "TL", "Shop1", "info", "Geheimnis des Shops")
        kern.posten(self.con, self.b, "TL", "Spiel1", "info", "vom Spiel")
        aid = self.con.execute("SELECT id FROM agent WHERE projekt_id = ? AND kennung = 'Shop1'", (self.a,)).fetchone()[0]
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=aid, gestartet_utc=db.jetzt())
        ziel = os.path.join(self.ordner.name, "lesen-spiel.db")
        bruecke.lese_kopie(ziel=ziel, pid=self.b)
        import sqlite3
        k = sqlite3.connect(f"file:{ziel}?immutable=1", uri=True)
        try:
            self.assertEqual(k.execute("SELECT name FROM projekt").fetchall(), [("Spiel",)])
            self.assertEqual(sorted(r[0] for r in k.execute("SELECT kennung FROM agent")), ["Spiel1", "TL"])
            self.assertEqual([r[0] for r in k.execute("SELECT kurz FROM nachricht")], ["vom Spiel"])
            self.assertEqual(k.execute("SELECT count(*) FROM sitzung").fetchone()[0], 0)      # hing am Agenten des Shops
            self.assertEqual(k.execute("SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
                                       " WHERE n.kurz LIKE '%Shop%'").fetchone()[0], 0)
            self.assertEqual(k.execute("PRAGMA foreign_key_check").fetchall(), [])
        finally:
            k.close()


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



class Getrennt(ZweiProjekte):
    """F5187: jedes Projekt für sich – eigene Arbeitsregeln, kein Agent in einem fremden Projekt."""
    def regel(self, pid, ebene, nr, text, von="TL"):
        from amw import wissen
        b = wissen.beschluss_neu(self.con, pid, von, f"Regel {nr} {text}", text, "Entwickler")
        return wissen.regel_setzen(self.con, pid, von, ebene, nr, text, b)

    def test_arbeitsregeln_je_projekt(self):
        self.assertEqual(self.regel(self.a, "arbeit", 1, "Shop: immer mit Kassenbon"), "angelegt")
        self.assertEqual(self.regel(self.b, "arbeit", 1, "Spiel: erst spielen, dann bauen"), "angelegt")   # gleiche Nummer
        rc, aus = self.cli("regeln", "--von", "Shop1")
        self.assertIn("KR1", aus)
        self.assertIn("Kassenbon", aus)
        self.assertNotIn("spielen", aus)
        self.assertIn("Regeln: 1 gültig", kern.kontext(self.con, self.b, "Spiel1"))
        self.assertNotIn("Kassenbon", kern.kontext(self.con, self.b, "Spiel1"))
        rc, aus = self.cli("zeige", "KR1", "--von", "Spiel1")
        self.assertIn("spielen", aus)

    def test_kein_agent_in_einem_fremden_projekt(self):
        rc, aus = self.cli("aufgabe", "neu", "--von", "Shop1", "--projekt", "Spiel", "--titel", "von außen")
        self.assertEqual(rc, 1)
        self.assertIn("Projekte sind getrennt", aus)
        rc, aus = self.cli("regeln", "--von", "Shop1", "--projekt", "Spiel")
        self.assertEqual(rc, 1)
        self.assertEqual(self.con.execute("SELECT count(*) FROM aufgabe").fetchone()[0], 0)
        rc, aus = self.cli("aufgabe", "neu", "--von", "TL", "--projekt", "Spiel", "--titel", "eigener TL")   # TL in beiden
        self.assertEqual(rc, 0, aus)
        rc, aus = self.cli("posten", "--von", kern.ENTWICKLER, "--projekt", "Webshop", "--an", "Shop1", "--art", "info",
                           "--kurz", "vom Menschen")                                 # der Entwickler wählt frei
        self.assertEqual(rc, 0, aus)
        self.assertEqual(db.projekt_fuer(self.con, None, "Shop1"), self.a)         # Hook: falsches AMW_PROJEKT → eigenes
        with self.assertRaises(LookupError):
            db.projekt_fuer(self.con, "Spiel", "Shop1")

    def test_neues_projekt_mit_kopie_der_arbeitsregeln(self):
        self.regel(self.a, "arbeit", 3, "Shop: Belege aufheben")
        self.regel(self.a, "projekt", 1, "Shop: Fachregel")
        rc, aus = self.cli("projekt", "neu", "Filiale", "--regeln-von", "Webshop")
        self.assertEqual(rc, 0, aus)
        self.assertIn("1 Arbeitsregeln aus Webshop übernommen", aus)
        f = db.projekt_id(self.con, "Filiale")
        r = self.con.execute("SELECT ebene, nr, text, beleg FROM regel WHERE projekt_id = ?", (f,)).fetchall()
        self.assertEqual([tuple(x) for x in r], [("arbeit", 3, "Shop: Belege aufheben", "übernommen aus Webshop KR3")])
        kern.agent_neu(self.con, f, "Chef", rolle="lead")
        self.regel(f, "arbeit", 3, "Filiale: Belege digital", von="Chef")
        self.assertEqual(self.con.execute("SELECT text FROM regel WHERE projekt_id = ? AND nr = 3", (self.a,)).fetchone()[0],
                         "Shop: Belege aufheben")                                      # das Original bleibt
        rc, aus = self.cli("projekt", "neu", "Leer")
        self.assertIn("ohne Regeln", aus)


class OrdnerGehoertZumProjekt(ZweiProjekte):
    def json_von(self, datei):
        with open(datei, encoding="utf-8") as f:
            return json.load(f)

    def test_projektordner_traegt_sein_projekt(self):
        from amw import einrichtung
        ordner = os.path.join(self.ordner.name, "spiel")
        os.makedirs(ordner)
        rc, aus = self.cli("einrichten", "agenten-ordner", ordner)               # zwei Projekte: welches?
        self.assertEqual(rc, 1)
        self.assertIn("zu welchem Projekt", aus)
        rc, aus = self.cli("einrichten", "agenten-ordner", ordner, "--projekt", "Spiel")
        self.assertEqual(rc, 0, aus)
        datei = os.path.join(ordner, ".claude", "settings.local.json")
        self.assertEqual(self.json_von(datei)["env"], {"AMW_PROJEKT": "Spiel"})
        rc, aus = self.cli("einrichten", "agenten-ordner", ordner, "--projekt", "Webshop")
        self.assertEqual(rc, 1)
        self.assertIn("gehört schon zum Projekt Spiel", aus)
        self.assertIn("Projekt Spiel (AMW_PROJEKT)", einrichtung.agenten_ordner_entfernen(ordner))
        self.assertNotIn("env", self.json_von(datei))

    def test_startskript_je_projekt(self):
        from amw import assistent
        pfad = os.path.join(self.ordner.name, "agenten-start.bat")
        self.assertEqual(assistent.startskript_fuer(self.con, self.a, pfad), pfad)            # erstes Projekt: wie bisher
        self.assertEqual(assistent.startskript_fuer(self.con, self.b, pfad),
                         os.path.join(self.ordner.name, "agenten-start-spiel.bat"))           # überschreibt es nie


class NeuesProjekt(ZweiProjekte):
    """Workbench „Neues Projekt“ (nur am PC): wie der Assistent, mit Projektordner, Startskript je Projekt und Regel-Kopie."""
    def setUp(self):
        super().setUp()
        from amw import assistent
        p = mock.patch.object(assistent, "STARTSKRIPT", os.path.join(self.ordner.name, "agenten-start.bat"))
        p.start()
        self.addCleanup(p.stop)
        self.repo = os.path.join(self.ordner.name, "laden")
        os.makedirs(self.repo)

    def neu(self, kanal="seite", **d):
        from amw import aktionen
        return aktionen.ausfuehren(self.con, self.a, "/api/projekt/neu", {"name": "Laden", "ordner": self.repo, "lead": "TL",
                                                                          "agenten": "CC1, CC2", **d}, kanal)

    def test_neues_projekt_wie_der_assistent(self):
        from amw import aktionen, wissen
        b = wissen.beschluss_neu(self.con, self.a, "TL", "Belege", "Belege aufheben", "Entwickler")
        wissen.regel_setzen(self.con, self.a, "TL", "arbeit", 2, "Belege aufheben", b)
        with self.assertRaises(aktionen.Ungueltig):
            self.neu(kanal="netz")                                                   # nie vom Handy
        with self.assertRaisesRegex(aktionen.Ungueltig, "gibt es nicht"):
            self.neu(ordner=os.path.join(self.ordner.name, "fehlt"))
        self.assertIsNone(self.con.execute("SELECT 1 FROM projekt WHERE name = 'Laden'").fetchone())   # nichts halb angelegt
        r = self.neu(regeln_von="Webshop", farbe="blau")
        pid = db.projekt_id(self.con, "Laden")
        self.assertEqual(r["uid"], self.con.execute("SELECT uid FROM projekt WHERE id = ?", (pid,)).fetchone()[0])
        self.assertEqual(kern.projekt_ordner(self.con, pid), os.path.abspath(self.repo))
        self.assertEqual([tuple(x) for x in self.con.execute("SELECT kennung, rolle, ordner FROM agent WHERE projekt_id = ? ORDER BY id",
                                                             (pid,))],
                         [("TL", "lead", os.path.abspath(self.repo)), ("CC1", None, os.path.abspath(self.repo)),
                          ("CC2", None, os.path.abspath(self.repo))])
        self.assertEqual(self.con.execute("SELECT text FROM regel WHERE projekt_id = ?", (pid,)).fetchone()[0], "Belege aufheben")
        self.assertEqual(kern.projekt_wahl(self.con, pid, "farbe"), "blau")
        with open(os.path.join(self.repo, ".claude", "settings.local.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["env"], {"AMW_PROJEKT": "Laden"})
        self.assertTrue(os.path.exists(os.path.join(self.ordner.name, "agenten-start-laden.bat")))
        self.assertFalse(os.path.exists(os.path.join(self.ordner.name, "agenten-start.bat")))   # das des ersten bleibt unberührt

        self.assertTrue(any("Arbeitsregeln aus Webshop" in x for x in r["schritte"]))
        with self.assertRaisesRegex(aktionen.Ungueltig, "gehört schon zum Projekt Laden"):
            self.neu(name="Zweiter Laden")                                           # ein Ordner, ein Projekt
        self.assertIsNone(self.con.execute("SELECT 1 FROM projekt WHERE name = 'Zweiter Laden'").fetchone())
        rc, aus = self.cli("agent", "neu", "CC3", "--von", kern.ENTWICKLER, "--projekt", "Laden")
        self.assertIn(f"arbeitet in {os.path.abspath(self.repo)}", aus)             # neuer Agent: Projektordner als Profil

    def test_lead_als_chat_wird_nie_gestartet(self):
        """#18200: der Lead arbeitet als Chat (Cowork) – kein Ordner im Profil, nicht im Startskript."""
        self.neu(lead_chat=True)
        pid = db.projekt_id(self.con, "Laden")
        ordner = dict(self.con.execute("SELECT kennung, ordner FROM agent WHERE projekt_id = ?", (pid,)).fetchall())
        self.assertFalse(ordner["TL"])
        self.assertEqual(ordner["CC1"], os.path.abspath(self.repo))
        with open(os.path.join(self.ordner.name, "agenten-start-laden.bat"), encoding="utf-8") as f:
            text = f.read()
        self.assertNotIn("--title TL", text)
        self.assertIn("--title CC1", text)
        self.assertTrue(text.startswith("@echo off"))                                          # .bat ohne BOM

    def test_erster_start_im_neuen_projekt(self):
        """#18115: woher weiß der erste Agent alles – Startsatz, Pflicht-Kontext ohne Leitbild, amw ohne Rückfrage, Tab-Titel."""
        from amw import einrichtung, planung, steuerung
        self.neu()
        pid = db.projekt_id(self.con, "Laden")
        satz = self.con.execute("SELECT startsatz FROM agent WHERE projekt_id = ? AND kennung = 'CC1'", (pid,)).fetchone()[0]
        self.assertIn("Du bist CC1", satz)
        self.assertIn("schritt naechster --nehmen --von CC1", satz)
        self.assertIn("rate nicht", kern.kontext(self.con, pid, "CC1"))            # ohne Leitbild: melden, nicht raten
        self.assertIn("frage den Entwickler nach Ziel", kern.kontext(self.con, pid, "TL"))
        planung.leitbild_setzen(self.con, pid, "TL", ziel="Ein Laden")
        self.assertNotIn("Projekt NEU", kern.kontext(self.con, pid, "CC1"))
        self.assertIn("Projektziel: Ein Laden", kern.kontext(self.con, pid, "CC1"))
        with open(os.path.join(self.repo, ".claude", "settings.local.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f)["permissions"]["allow"], einrichtung.ERLAUBT)   # amw ohne Rückfrage
        args = []
        with mock.patch.object(steuerung, "laeuft", return_value=False), mock.patch.object(steuerung.shutil, "which", return_value="wt.exe"):
            steuerung.starten(self.con, pid, "CC1", ausfuehren=lambda a, f, o: args.extend(a))
        self.assertEqual(args[args.index("--title") + 1], "CC1 · Laden")
        einrichtung.agenten_ordner_entfernen(self.repo)
        with open(os.path.join(self.repo, ".claude", "settings.local.json"), encoding="utf-8") as f:
            self.assertEqual(json.load(f).get("permissions", {}).get("allow"), [])


class SichernJeProjekt(ZweiProjekte):
    """Eine Datenbank je Rechner (F5190) – ein Projekt lässt sich trotzdem als eigene, lauffähige Datenbank sichern."""
    def test_projekt_als_eigene_datenbank(self):
        from amw import dokumente
        for pid, name, inhalt in ((self.a, "shop.md", b"# Shop"), (self.b, "spiel.md", b"# Spiel")):
            pfad = os.path.join(self.ordner.name, name)
            with open(pfad, "wb") as f:
                f.write(inhalt)
            dokumente.ablegen(self.con, pid, "TL", pfad, name, "bericht")
        kern.posten(self.con, self.a, "TL", "Shop1", "info", "Geheimnis des Shops")
        kern.posten(self.con, self.b, "TL", "Spiel1", "info", "vom Spiel")
        ziel = os.path.join(self.ordner.name, "sicherung")
        rc, aus = self.cli("sichern", "--projekt", "Spiel", "--ziel", ziel)
        self.assertEqual(rc, 0, aus)
        self.assertIn("nur Projekt Spiel", aus)
        datei = next(os.path.join(ziel, x) for x in os.listdir(ziel) if x.endswith(".db"))
        self.assertIn("-spiel-", os.path.basename(datei))
        k = db.verbinde(datei)                                   # lauffähig: öffnet ohne Umstellung, Trigger da
        try:
            self.assertEqual(k.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
            self.assertEqual(k.execute("PRAGMA integrity_check").fetchone()[0], "ok")
            self.assertEqual(k.execute("PRAGMA foreign_key_check").fetchall(), [])
            self.assertEqual([r[0] for r in k.execute("SELECT name FROM projekt")], ["Spiel"])
            self.assertEqual([r[0] for r in k.execute("SELECT kurz FROM nachricht")], ["vom Spiel"])
            self.assertEqual([r[0] for r in k.execute("SELECT titel FROM dokument")], ["spiel.md"])
            self.assertTrue(k.execute("SELECT count(*) FROM sqlite_master WHERE type = 'trigger'").fetchone()[0] > 0)
            with self.assertRaises(Exception):                   # Schutz wirkt wieder: Verlauf bleibt
                with db.schreiben(k):
                    k.execute("DELETE FROM nachricht")
        finally:
            k.close()
        dateien = [x for _, _, xs in os.walk(os.path.splitext(datei)[0] + "-dokumente") for x in xs]
        self.assertEqual(len(dateien), 1)                         # nur die Datei des Spiels


class Schema19(unittest.TestCase):
    """Altbestand: Arbeitsregeln ohne Projekt und PC-weite KI-Vorlagen gehen an ihr Projekt."""
    ALT = """
DROP TABLE regel;
CREATE TABLE regel (id INTEGER PRIMARY KEY, ebene TEXT NOT NULL CHECK (ebene IN ('arbeit', 'projekt')),
  projekt_id INTEGER REFERENCES projekt(id), nr INTEGER NOT NULL, teil TEXT, text TEXT NOT NULL, beleg TEXT,
  stand_utc TEXT NOT NULL, uid TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))), herkunft TEXT NOT NULL DEFAULT '',
  geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  CHECK ((ebene = 'arbeit') = (projekt_id IS NULL)));
CREATE UNIQUE INDEX regel_nr ON regel (ebene, coalesce(projekt_id, 0), nr);
DROP TABLE ki_vorlage;
CREATE TABLE ki_vorlage (id INTEGER PRIMARY KEY, ki_id INTEGER NOT NULL REFERENCES ki(id), name TEXT NOT NULL,
  beschreibung TEXT, inhalt TEXT NOT NULL, sha256 TEXT NOT NULL, von TEXT NOT NULL, stand_utc TEXT NOT NULL,
  aktiv INTEGER NOT NULL DEFAULT 1, uid TEXT NOT NULL UNIQUE DEFAULT (lower(hex(randomblob(16)))),
  herkunft TEXT NOT NULL DEFAULT '', geaendert_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
  UNIQUE (ki_id, name));
"""

    def test_migration(self):
        with tempfile.TemporaryDirectory() as ordner:
            pfad = os.path.join(ordner, "alt.db")
            con = db.anlegen(pfad)
            self.addCleanup(con.close)
            con.execute("PRAGMA foreign_keys = OFF")
            con.executescript(self.ALT)
            t = db.jetzt()
            with db.schreiben(con):
                for pid, name in ((1, "Erst"), (2, "Zweit")):
                    db.einfuegen(con, "projekt", id=pid, name=name, angelegt_utc=t)
                kern_id = db.einfuegen(con, "agent", projekt_id=2, kennung="Maler", angelegt_utc=t)
                db.einfuegen(con, "beschluss", id=7, projekt_id=2, zeit_utc=t, stichwort="s", regel="r", quelle="q",
                             angelegt_von="TL", angelegt_utc=t)
                for ebene, pid, nr, text, beleg in (("arbeit", None, 1, "aus B7", "B7"), ("arbeit", None, 2, "ohne Beleg", None),
                                                    ("projekt", 1, 1, "Fach", "B1")):
                    db.einfuegen(con, "regel", ebene=ebene, projekt_id=pid, nr=nr, text=text, beleg=beleg, stand_utc=t)
                db.einfuegen(con, "ki", id=1, name="comfyui", art="bild", schnittstelle="comfyui", endpunkt="http://127.0.0.1:1",
                             angelegt_von="Maler", angelegt_utc=t)
                db.einfuegen(con, "ki_vorlage", id=5, ki_id=1, name="sprite", inhalt="{}", sha256="x", von="Maler", stand_utc=t)
                db.einfuegen(con, "lauf", id=9, projekt_id=2, agent="Maler", beschreibung="Bild", angemeldet_utc=t)
                db.einfuegen(con, "ki_auftrag", projekt_id=2, lauf_id=9, ki_id=1, vorlage_id=5, auftraggeber="Maler",
                             prompt="p", seed=1, angelegt_utc=t)                # verweist auf die neu angelegte Tabelle
                db.einfuegen(con, "frage", projekt_id=1, an="entwickler", von="TL", zeit_utc=t, kurz="Altlast", folge_von=999)
            self.assertTrue(kern_id)
            # (die Regel-Tabelle steht hier schon in ihrer alten Form – die Spalte „vorlage“ aus Schema 23 gibt es darin nicht)
            for sp in ("braucht_gb", "braucht_vram_gb", "braucht_platte_gb", "rechner"):   # Bedarf und Rechner je Lauf kamen mit Schema 24
                con.execute(f"ALTER TABLE lauf DROP COLUMN {sp}")
            for sp in ("hinweis", "hinweis_gruppe"):   # Satz für die Versionshinweise kam mit Schema 26
                con.execute(f"ALTER TABLE aufgabe DROP COLUMN {sp}")
            for tab in ("nachricht", "frage_verlauf"):   # wer von den Menschen es war, kam mit Schema 27
                if con.execute("SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (tab,)).fetchone():
                    con.execute(f"ALTER TABLE {tab} DROP COLUMN benutzer")
            for sp in ("fachgebiet", "arbeitsweise", "zustaendig", "fasst_nicht_an"):   # Agenten-Einstellungen kamen mit Schema 22
                con.execute(f"ALTER TABLE agent DROP COLUMN {sp}")
            con.execute("DROP TABLE ki_vermerk")              # Vermerke an KI-Ergebnissen kamen mit Schema 21
            con.execute("ALTER TABLE nachricht DROP COLUMN bis")      # Bezug von Meldungen kam mit Schema 20
            con.execute("PRAGMA user_version = 18")
            con.close()
            con = db.verbinde(pfad)
            try:
                self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
                self.assertEqual(con.execute("PRAGMA foreign_keys").fetchone()[0], 1)
                self.assertEqual([tuple(r) for r in con.execute("SELECT ebene, nr, projekt_id FROM regel ORDER BY id")],
                                 [("arbeit", 1, 2), ("arbeit", 2, 1), ("projekt", 1, 1)])
                self.assertEqual(tuple(con.execute("SELECT id, projekt_id FROM ki_vorlage").fetchone()), (5, 2))
                self.assertEqual(con.execute("SELECT vorlage_id FROM ki_auftrag").fetchone()[0], 5)
                self.assertEqual([r[0] for r in con.execute("PRAGMA foreign_key_check")], ["frage"])  # Altlast bleibt, stört nicht
                with db.schreiben(con):                                 # gleiche Nummer/Name in zwei Projekten geht jetzt
                    db.einfuegen(con, "regel", ebene="arbeit", projekt_id=1, nr=1, text="eigen", stand_utc=db.jetzt())
                    db.einfuegen(con, "ki_vorlage", projekt_id=1, ki_id=1, name="sprite", inhalt="{}", sha256="y",
                                 von="Lead", stand_utc=db.jetzt())
                    con.execute("UPDATE regel SET geaendert_utc = '' WHERE nr = 2")
                self.assertNotEqual(con.execute("SELECT geaendert_utc FROM regel WHERE nr = 2").fetchone()[0], "")  # Trigger
                self.assertTrue(con.execute("SELECT 1 FROM sqlite_master WHERE name = 'ki_vorlage_geaendert'").fetchone())
            finally:
                con.close()


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



class WieTurso(unittest.TestCase):
    def test_nachruesten_mit_zahlen_als_text(self):
        # 06.11.: Turso liefert count(*) als „0“ – die Spalte eingang.projekt wurde nicht angelegt
        from amw import abgleich

        class Speicher(abgleich.SqliteSpeicher):
            def ausfuehren(self, anweisungen):
                return [[[None if v is None else str(v) for v in z] for z in e] for e in super().ausfuehren(anweisungen)]

        with tempfile.TemporaryDirectory() as ordner:
            alt = os.path.join(ordner, "online.db")
            sp = Speicher(alt)
            sp.ausfuehren([("CREATE TABLE eingang (id INTEGER PRIMARY KEY, zeit_utc TEXT NOT NULL, weg TEXT NOT NULL,"
                            " daten TEXT NOT NULL, ip TEXT, status TEXT NOT NULL DEFAULT 'neu', ergebnis TEXT, erledigt_utc TEXT)", [])])
            con = db.anlegen(os.path.join(ordner, "amw.db"))
            with db.schreiben(con):
                pid = db.einfuegen(con, "projekt", name="P", angelegt_utc=db.jetzt())
            ab = abgleich.Abgleich(con, sp, pid)
            ab.schema()
            self.assertEqual(ab.eingang(), 0)
            self.assertEqual(sp.ausfuehren([("SELECT count(*) FROM pragma_table_info('eingang') WHERE name = 'projekt'", [])])[0], [["1"]])
            con.close()

if __name__ == "__main__":
    unittest.main()
