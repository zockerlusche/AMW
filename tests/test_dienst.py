"""Tests für den Wecker im amw-dienst – die Pipe wird nachgebildet, es wird keine echte Sitzung geweckt."""
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import db, dienst, kern, pipe


class Wecker(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "CC2")
        self.gesendet = []
        self.lebt = True
        patch_s = mock.patch.object(pipe, "senden", side_effect=lambda p, k, t: self.gesendet.append((p, t)))
        patch_l = mock.patch.object(pipe, "lebt", side_effect=lambda p: self.lebt)
        patch_s.start()
        patch_l.start()
        self.addCleanup(patch_s.stop)
        self.addCleanup(patch_l.stop)
        p = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name})   # aufsicht() schickt sonst echte Pushes
        p.start()
        self.addCleanup(p.stop)
        self.d = dienst.Dienst(self.con)

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def anmelden(self, kennung, sitzung="s1"):
        datei = os.path.join(self.ordner.name, f"{kennung}.json")
        with open(datei, "w", encoding="utf-8") as f:
            json.dump({"pipe": f"\\\\.\\pipe\\LOCAL\\cc-msg-{kennung}", "schluessel": "geheim", "sitzung": sitzung}, f)
        a = kern.agent_zeile(self.con, self.pid, kennung)
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=a["id"], claude_sitzung=sitzung, schluessel_datei=datei,
                         gestartet_utc=db.jetzt())

    def geweckt(self):
        return {(r[0], r[1]) for r in self.con.execute(
            "SELECT nachricht_id, agent FROM empfang WHERE geweckt_utc IS NOT NULL")}

    def test_weckt_nur_weckende_arten_und_nur_einmal(self):
        self.anmelden("CC1")
        if not self.con.execute("SELECT 1 FROM agent WHERE kennung = 'CC2'").fetchone():
            kern.agent_neu(self.con, self.pid, "CC2")
        n1, _ = kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "a")
        kern.posten(self.con, self.pid, "TL", "CC1,CC2", "info", "i an zwei")             # Sammel-Info weckt nicht
        kern.posten(self.con, self.pid, "AMW", "CC1", "info", "Kopie")                    # Kopie der AMW weckt nicht
        self.assertEqual(self.d.zustellen(), 1)
        self.assertEqual(self.geweckt(), {(n1, "CC1")})
        self.assertIn(f"#{n1} TL [auftrag] a", self.gesendet[0][1])
        self.assertNotIn("geheim", self.gesendet[0][1])
        self.assertEqual(self.d.zustellen(), 0)

    def test_nicht_angemeldet_bleibt_offen_bis_anmeldung(self):
        n1, _ = kern.posten(self.con, self.pid, "TL", "CC2", "auftrag", "a")
        self.assertEqual(self.d.zustellen(), 0)
        self.anmelden("CC2")
        self.assertEqual(self.d.zustellen(), 1)
        self.assertEqual(self.geweckt(), {(n1, "CC2")})

    def test_halt_laesst_nur_stopp_und_freigabe_durch(self):
        self.anmelden("CC1")
        kern.halt(self.con, self.pid, "TL", "CC1", "Pause")
        n_auftrag, _ = kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "später")
        self.d.zustellen()
        self.assertEqual([a for _, a in self.geweckt()], ["CC1"])
        self.assertNotIn((n_auftrag, "CC1"), self.geweckt())
        self.assertIn("HALT GILT", self.gesendet[0][1])
        kern.weiter(self.con, self.pid, "TL", "CC1")
        self.d.zustellen()
        self.assertIn((n_auftrag, "CC1"), self.geweckt())

    def test_fehlschlag_bleibt_offen_und_beendet_tote_sitzung(self):
        self.anmelden("CC1")
        kern.posten(self.con, self.pid, "TL", "CC1", "auftrag", "a")
        self.lebt = False
        with mock.patch.object(pipe, "senden", side_effect=pipe.ZustellFehler("weg")):
            self.assertEqual(self.d.zustellen(), 0)
        self.assertEqual(self.geweckt(), set())
        z = self.con.execute("SELECT zustand FROM sitzung").fetchone()[0]
        self.assertEqual(z, "beendet")

    def test_takt_an_lead_nur_mit_sitzung_und_nicht_doppelt(self):
        self.d.takt()
        self.assertEqual(self.con.execute("SELECT count(*) FROM nachricht WHERE art = 'takt'").fetchone()[0], 0)
        self.anmelden("TL")
        fid = kern.frage_neu(self.con, self.pid, "TL", "entwickler", "x?", [("A", "a")], "A", "weil", geprueft="keine Treffer")
        kern.frage_antworten(self.con, self.pid, fid, "option", "A", "seite")
        self.d.takt()
        self.d.takt()
        takte = self.con.execute("SELECT kurz FROM nachricht WHERE art = 'takt'").fetchall()
        self.assertEqual(len(takte), 1)
        self.assertIn(f"beantwortet: F{fid}", takte[0][0])
        self.d.zustellen()
        self.assertTrue(any("[takt]" in t for _, t in self.gesendet))

    def test_takt_abschaltbar(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = '{\"takt_min\": 0}'")
        self.anmelden("TL")
        self.d.takt()
        self.assertEqual(self.con.execute("SELECT count(*) FROM nachricht WHERE art = 'takt'").fetchone()[0], 0)

    def test_aufsicht_setzt_puls_oder_beendet(self):
        self.anmelden("CC1")
        self.d.aufsicht()
        s = self.con.execute("SELECT zustand, letzter_puls_utc FROM sitzung").fetchone()
        self.assertEqual(s[0], "aktiv")
        self.assertTrue(s[1])
        self.lebt = False
        self.d.aufsicht()
        self.assertEqual(self.con.execute("SELECT zustand FROM sitzung").fetchone()[0], "beendet")


class Anmelden(unittest.TestCase):
    """Doppelte Anmeldung: eine Hintergrund-Sitzung darf sich nie als Agent anmelden."""
    def setUp(self):
        from amw import hook
        self.hook = hook
        self.ordner = tempfile.TemporaryDirectory()
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "CC5")
        self.prozesse = {}                                         # Postfach → Eintrag aus ~/.claude/sessions
        for p in (mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name}),
                  mock.patch.object(hook, "claude_prozess", side_effect=lambda pipe: self.prozesse.get(pipe))):
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.con.close()
        self.ordner.cleanup()

    def als(self, pipe, art, **k):
        self.prozesse[pipe] = {"pid": len(self.prozesse) + 100, "art": art, "name": pipe, "sitzung": pipe + "-sitzung"}
        with mock.patch.dict(os.environ, {"CLAUDE_CODE_MESSAGING_SOCKET": pipe, "CLAUDE_CODE_MESSAGING_TOKEN": "t"}):
            return self.hook.anmelden(self.con, self.pid, "CC5", {"session_id": pipe + "-sitzung"}, **k)

    def aktiv(self):
        return [r[0] for r in self.con.execute("SELECT claude_sitzung FROM sitzung WHERE zustand = 'aktiv'")]

    def test_hintergrund_sitzung_wird_nie_angemeldet(self):
        self.assertIn("Hintergrund", self.als("bg", "bg", streng=True))
        self.assertIn("Hintergrund", self.als("bg", "bg"))                        # auch nicht über den Hook
        self.assertEqual(self.aktiv(), [])

    def test_lebende_andere_sitzung_nur_mit_ersetzen(self):
        self.assertIsNone(self.als("fenster1", "interactive", streng=True))
        grund = self.als("fenster2", "interactive", streng=True)
        self.assertIn("--ersetzen", grund)
        self.assertEqual(self.aktiv(), ["fenster1-sitzung"])
        self.assertIsNone(self.als("fenster2", "interactive", streng=True, ersetzen=True))
        self.assertEqual(self.aktiv(), ["fenster2-sitzung"])
        del self.prozesse["fenster2"]                                              # Prozess beendet → frei
        self.assertIsNone(self.als("fenster3", "interactive", streng=True))
        self.assertIsNone(self.als("fenster4", "interactive"))                    # Hook (Neustart) löst immer ab

    def hook_lauf(self, eingabe, agent=None):
        """Startet hook.main wie Claude Code: JSON auf stdin, Ausgabe auf stdout; Postfach dieser Sitzung = pipe-x."""
        import io
        self.prozesse["pipe-x"] = {"pid": 7, "art": "interactive", "name": "x", "sitzung": eingabe["session_id"]}
        umg = {"AMW_DB": os.path.join(self.ordner.name, "t.db"), "CLAUDE_CODE_MESSAGING_SOCKET": "pipe-x",
               "CLAUDE_CODE_MESSAGING_TOKEN": "t"}
        if agent:
            umg["AMW_AGENT"] = agent
        aus = io.StringIO()
        with mock.patch.dict(os.environ, umg), mock.patch("sys.stdin", io.StringIO(json.dumps(eingabe))), \
                mock.patch("sys.stdout", aus):
            if not agent:
                os.environ.pop("AMW_AGENT", None)
            self.hook.main()
        return json.loads(aus.getvalue()) if aus.getvalue().strip() else None

    def test_resume_ohne_amw_agent_erkennt_die_sitzung(self):
        """Resume von Hand (ohne Startskript, kein AMW_AGENT) – die Sitzungs-ID war schon als CC5 angemeldet."""
        self.assertIn("als CC5 angemeldet", self.hook_lauf({"session_id": "abc", "source": "startup", "cwd": "C:\\projekt"}, "CC5")["systemMessage"])
        self.con.execute("UPDATE sitzung SET zustand = 'beendet'")
        aus = self.hook_lauf({"session_id": "abc", "source": "resume", "cwd": "C:\\projekt"})
        self.assertIn("erkannt", aus["systemMessage"])
        self.assertEqual(self.aktiv(), ["abc"])

    def test_unbekannte_sitzung_im_agenten_ordner_meldet_laut_sonst_still(self):
        self.hook_lauf({"session_id": "abc", "source": "startup", "cwd": "C:\\projekt"}, "CC5")
        aus = self.hook_lauf({"session_id": "neu", "source": "startup", "cwd": "c:\\PROJEKT"})
        self.assertIn("NICHT angemeldet", aus["systemMessage"])
        self.assertIsNone(self.hook_lauf({"session_id": "fremd", "source": "startup", "cwd": "D:\\anderes"}))
        self.assertEqual(self.aktiv(), ["abc"])


class GleicheKennungZweiProjekte(Anmelden):
    """TL gibt es in P und Q: eine Sitzung landet nie im falschen Projekt – dort würden Nachrichten des anderen sie wecken."""
    def setUp(self):
        super().setUp()
        with db.schreiben(self.con):
            self.q = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        for pid, ordner in ((self.pid, "C:/p"), (self.q, "C:/q")):
            kern.agent_neu(self.con, pid, "TL", rolle="lead")
            with db.schreiben(self.con):
                self.con.execute("UPDATE agent SET ordner = ? WHERE projekt_id = ? AND kennung = 'TL'", (ordner, pid))

    def projekt_der(self, sitzung):
        r = self.con.execute("SELECT a.projekt_id FROM sitzung s JOIN agent a ON a.id = s.agent_id"
                             " WHERE s.claude_sitzung = ? AND s.zustand = 'aktiv'", (sitzung,)).fetchone()
        return r[0] if r else None

    def test_projekt_aus_ordner_umgebung_oder_gar_nicht(self):
        self.hook_lauf({"session_id": "in-q", "source": "startup", "cwd": "c:/Q"}, "TL")       # von Hand im Ordner von Q
        self.assertEqual(self.projekt_der("in-q"), self.q)
        aus = self.hook_lauf({"session_id": "irgendwo", "source": "startup", "cwd": "D:/x"}, "TL")
        self.assertIn("NICHT angemeldet", aus["systemMessage"])
        self.assertIn("mehreren Projekten", aus["systemMessage"])
        self.assertIsNone(self.projekt_der("irgendwo"))                    # früher: still im ersten Projekt
        with mock.patch.dict(os.environ, {"AMW_PROJEKT": "P"}):              # Startbefehl bzw. Projektordner
            self.hook_lauf({"session_id": "in-p", "source": "startup", "cwd": "D:/x"}, "TL")
        self.assertEqual(self.projekt_der("in-p"), self.pid)
        self.con.execute("UPDATE sitzung SET zustand = 'beendet' WHERE claude_sitzung = 'in-q'")
        self.hook_lauf({"session_id": "in-q", "source": "resume", "cwd": "D:/x"})              # Resume: frühere Anmeldung
        self.assertEqual(self.projekt_der("in-q"), self.q)

    def test_nachricht_weckt_nur_die_sitzung_ihres_projekts(self):
        for sitzung, pid in (("s-p", self.pid), ("s-q", self.q)):
            datei = os.path.join(self.ordner.name, f"{sitzung}.json")
            with open(datei, "w", encoding="utf-8") as f:
                json.dump({"pipe": f"pipe-{sitzung}", "schluessel": "k", "sitzung": sitzung}, f)
            a = kern.agent_zeile(self.con, pid, "TL")
            with db.schreiben(self.con):
                db.einfuegen(self.con, "sitzung", agent_id=a["id"], claude_sitzung=sitzung, schluessel_datei=datei,
                             gestartet_utc=db.jetzt())
        gesendet = []
        with mock.patch.object(pipe, "senden", side_effect=lambda p, k, t: gesendet.append(p)),                 mock.patch.object(pipe, "lebt", return_value=True):
            kern.posten(self.con, self.q, "Entwickler", "TL", "auftrag", "nur für Q")
            dienst.Dienst(self.con).zustellen()
        self.assertEqual(gesendet, ["pipe-s-q"])


if __name__ == "__main__":
    unittest.main()
