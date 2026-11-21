"""A1906 (W2443 Weg B): neue Claude-Code-Version ohne Stillstand – die AMW macht die Negativprobe selbst und gibt bei
Bestehen frei. Neue Version → Probe statt Start (Regel 11, einmal je Version); bestanden → eingetragen, Start geht, wegen der
Version abgebrochene Pakete wieder startklar; nicht bestanden/unklar → Wartungsmodus und Frage an Lead und Mensch; ein
Versionswechsel zählt nie zur Fehlserie; Freigabe von Hand nur mit Sperre wie agent lead."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import sys
import tempfile
import unittest
from unittest import mock

from amw import arbeiter, arbeitspaket, cli, db, disponent, entscheidung, kern, versionsprobe, waechter
from tests import test_disponent as td

NEU = "9.9.9"


class Basis(unittest.TestCase):
    setUp_disponent, plaetze, paket = td.Disponent.setUp, td.Disponent.plaetze, td.Disponent.paket   # ohne die Tests dort erneut

    def setUp(self):
        self.setUp_disponent()
        u = mock.patch.dict(os.environ, {"AMW_CLAUDE_VERSION": NEU})
        u.start()
        self.addCleanup(u.stop)

    def nachrichten(self, kurz_anfang):
        return [(r[0], r[1]) for r in self.con.execute(
            "SELECT e.agent, n.art FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE n.kurz LIKE ? ORDER BY e.agent",
            (kurz_anfang + "%",))]

    def ergebnis(self, wie):
        return {"ergebnis": wie, "version": NEU, "gruende": [] if wie == "bestanden" else ["nicht abgelehnt: Write {…}"],
                "aufrufe": [], "abgelehnt": set(), "bericht": f"# Negativprobe Claude Code {NEU}\n\n- Ergebnis: **{wie}**\n"}


class NeueVersion(Basis):
    def test_probe_statt_start_einmal_je_version(self):
        self.plaetze(1)
        aid = self.paket()
        with mock.patch.object(versionsprobe, "_spawn", return_value=4711) as spawn:
            aus = disponent.runde(self.con)
            self.assertIn(f"Claude Code {NEU} nicht geprüft → Negativprobe gestartet (Prozess 4711)", aus)
            self.assertEqual(arbeitspaket.lesen(self.con, aid)["zustand"], "startklar")              # kein Arbeiter
            self.assertIn("Regel 11", waechter.protokoll(self.con, self.pid, aid)[0]["text"])
            disponent.runde(self.con)
            disponent.runde(self.con)
            self.assertEqual(spawn.call_count, 1)                                                     # eine Probe je Version
        self.assertEqual([e["schritt"] for e in versionsprobe.proben(self.con, NEU)], ["angestossen"])
        with self.assertRaisesRegex(kern.AmwFehler, "Regel 11"):                                     # auch von Hand kein Start
            disponent.handstart(self.con, self.pid, aid, "TL")

    def test_geprueft_startet_wie_gewohnt(self):
        self.plaetze(1)
        aid = self.paket()
        with mock.patch.dict(os.environ, {"AMW_CLAUDE_VERSION": arbeiter.GEPRUEFT[-1]}):
            self.assertTrue(waechter.pruefen(self.con, self.pid, aid)["ok"])

    def test_bestanden_eingetragen_start_geht_und_wieder_startklar(self):
        self.plaetze(1)
        aid = self.paket()
        weg = self.paket()                                                                             # wegen der Version abgebrochen
        arbeitspaket.zustand_setzen(self.con, self.pid, "AMW", weg, "laeuft")
        arbeitspaket.zustand_setzen(self.con, self.pid, "AMW", weg, "abgebrochen", grund="E1n: Version")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art="paket_entscheidung",
                         aufgabe_id=weg, text=json.dumps({"zeile": "E1n", "code": "Version"}))
        with mock.patch.object(versionsprobe, "_spawn", return_value=1):
            versionsprobe.anstossen(self.con, self.pid, NEU)
        did = versionsprobe.abschliessen(self.con, self.pid, NEU, self.ergebnis("bestanden"), lauf=77)
        self.assertIn(NEU, versionsprobe.geprueft(self.con))
        self.assertIn(f"Negativprobe Claude Code {NEU}", self.con.execute("SELECT titel FROM dokument WHERE id = ?", (did,)).fetchone()[0])
        self.assertEqual(self.nachrichten(f"Claude Code {NEU} geprüft und freigegeben, D{did}"), [("TL", "meldung")])
        self.assertTrue(waechter.pruefen(self.con, self.pid, aid)["ok"])                             # Start geht
        self.assertEqual(arbeitspaket.lesen(self.con, weg)["zustand"], "startklar")
        self.assertFalse(waechter.zustand()["wartung"])
        self.assertEqual([e["schritt"] for e in versionsprobe.proben(self.con, NEU)], ["angestossen", "ende"])

    def test_nicht_bestanden_oder_unklar_wartung_und_frage(self):
        self.plaetze(1)
        aid = self.paket()
        for wie in ("nicht bestanden", "unklar"):
            with self.subTest(wie):
                waechter.wartung_aus()
                did = versionsprobe.abschliessen(self.con, self.pid, NEU, self.ergebnis(wie))
                self.assertIn(f"Claude Code {NEU}: Negativprobe {wie}", waechter.zustand()["wartung"]["grund"])
                self.assertEqual(self.nachrichten(f"Claude Code {NEU}: Negativprobe {wie}"), [("Entwickler", "frage"), ("TL", "frage")])
                text = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE ?", (f"Claude Code {NEU}: Negativprobe {wie}%",)).fetchone()[0]
                self.assertIn(f"D{did}", text)
                self.assertIn(f"amw claude freigeben {NEU} --grund", text)
                self.assertNotIn(NEU, versionsprobe.geprueft(self.con))
                self.assertFalse(waechter.pruefen(self.con, self.pid, aid)["ok"])

    def test_versionswechsel_keine_fehlserie(self):
        ab = [f"Claude Code {NEU} ist nicht geprüft (geprüft: 2.1.326) – die AMW prüft die neue Version selbst"]
        self.assertEqual(entscheidung.entscheiden({"rc": None, "abweichungen": ab}), ("E1n", "Version"))
        self.assertFalse(entscheidung.ZEILEN["E1n"]["fehlserie"])
        self.assertEqual(entscheidung.entscheiden({"rc": None, "abweichungen": ab + ["Modell x statt haiku"]})[0], "E1")
        e = {"type": "system", "subtype": "init", "claude_code_version": NEU}                       # die Abweichung aus init_pruefen
        self.assertTrue(arbeiter.nur_version([x for x in arbeiter.init_pruefen(e, {"cwd": "", "modell": "", "werkzeuge": [], "mcp": [],
                                                                                   "versionen": ("2.1.326",)}) if "Claude Code" in x]))

    def test_eingetragene_version_gilt_im_arbeiter(self):
        p = {"klon": self.ordner.name}
        e = {"type": "system", "subtype": "init", "claude_code_version": NEU}
        s = lambda: arbeiter.soll(p, versionen=versionsprobe.geprueft(self.con))
        self.assertTrue([x for x in arbeiter.init_pruefen(e, s()) if "nicht geprüft" in x])
        versionsprobe.abschliessen(self.con, self.pid, NEU, self.ergebnis("bestanden"))
        self.assertFalse([x for x in arbeiter.init_pruefen(e, s()) if "nicht geprüft" in x])
        self.assertEqual(arbeiter.soll(p, versionen=())["versionen"], ())                          # nur die Probe: ohne Prüfung


class Ausfuehren(Basis):
    """Der losgelöste Prozess: angemeldet in der Lauf-Schlange, Probe, Lauf-Ende, abschließen – ein Fehler ist „unklar“."""

    def lauf(self):
        return tuple(self.con.execute("SELECT id, status, rc, beschreibung FROM lauf ORDER BY id DESC LIMIT 1").fetchone())

    def test_bestanden_im_lauf(self):
        with mock.patch.object(versionsprobe, "probe", return_value=self.ergebnis("bestanden")):
            self.assertEqual(versionsprobe.ausfuehren(self.con, self.pid, NEU), "bestanden")
        lid, status, rc, beschreibung = self.lauf()
        self.assertEqual((status, rc, beschreibung), ("fertig", 0, f"Negativprobe Claude Code {NEU} (A1906, automatisch)"))
        e = [x for x in versionsprobe._ereignisse(self.con, versionsprobe.GEPRUEFT_ART) if x["version"] == NEU]
        self.assertEqual((len(e), e[0]["lauf"]), (1, lid))

    def test_fehler_ist_unklar(self):
        with mock.patch.object(versionsprobe, "probe", side_effect=RuntimeError("claude weg")):
            self.assertEqual(versionsprobe.ausfuehren(self.con, self.pid, NEU), "unklar")
        self.assertEqual(self.lauf()[1:3], ("fertig", 1))
        self.assertIn("unklar", waechter.zustand()["wartung"]["grund"])
        text = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE ?", (f"Claude Code {NEU}: Negativprobe unklar%",)).fetchone()[0]
        self.assertIn("RuntimeError: claude weg", text)


class VonHand(Basis):
    def rufen(self, von, *args, **env):
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": "", **env}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "Spiel", "--von", von, "claude", *args])
        return rc, aus.getvalue()

    def test_freigeben_mit_sperre(self):
        rc, aus = self.rufen("Entwickler", "freigeben", NEU, "--grund", "gelesen", CLAUDECODE="1")
        self.assertNotEqual(rc, 0)
        self.assertIn("nicht aus einer Agenten-Sitzung", aus)
        rc, aus = self.rufen("CC1", "freigeben", NEU, "--grund", "gelesen")
        self.assertNotEqual(rc, 0)
        self.assertIn("nur der Lead oder der Mensch", aus)
        rc, aus = self.rufen("TL", "freigeben", NEU)
        self.assertIn("Grund", aus)
        rc, aus = self.rufen("TL", "freigeben", NEU, "--grund", "Bericht gelesen, Ablehnung kam über deny")
        self.assertEqual(rc, 0, aus)
        self.assertIn(NEU, versionsprobe.geprueft(self.con))
        rc, aus = self.rufen("TL", "freigeben", NEU, "--grund", "nochmal")
        self.assertIn("schon geprüft", aus)
        rc, aus = self.rufen("CC1", "status")
        self.assertEqual(rc, 0, aus)
        self.assertIn(f"Installiert: Claude Code {NEU} – geprüft", aus)
        self.assertIn(f"Geprüft {NEU}:", aus)


class Installiert(unittest.TestCase):
    def test_version_aus_claude_dash_dash_version(self):
        versionsprobe._gemerkt.clear()
        self.addCleanup(versionsprobe._gemerkt.clear)
        with mock.patch.dict(os.environ, {"AMW_CLAUDE_VERSION": ""}), \
                mock.patch.object(arbeiter, "programm", return_value=[sys.executable, "-c", "print('2.1.999 (Claude Code)')"]):
            self.assertEqual(versionsprobe.installiert(), "2.1.999")
        with mock.patch.dict(os.environ, {"AMW_CLAUDE_VERSION": ""}), \
                mock.patch.object(arbeiter, "programm", side_effect=arbeiter.ArbeiterFehler("claude nicht gefunden")):
            self.assertEqual(versionsprobe.installiert(), "2.1.999")                                 # gemerkt (5 min)
            versionsprobe._gemerkt.clear()
            self.assertIsNone(versionsprobe.installiert())                                            # unbekannt → keine Sperre


class Auswerten(unittest.TestCase):
    """Die Bewertung der Probe ohne echten Claude Code: Protokoll und permission_denials wie in D1345."""

    def setUp(self):
        self.o = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.o.cleanup)
        o = self.o.name
        self.klon, self.fremd, self.haupt = os.path.join(o, "klon"), os.path.join(o, "fremd"), os.path.join(o, "haupt", "_probe_arbeiter.txt")
        for d in (os.path.join(self.klon, ".git"), self.fremd, os.path.dirname(self.haupt)):
            os.makedirs(d)
        with open(os.path.join(self.klon, ".git", "config"), "w") as f:
            f.write("[core]\n")
        with open(os.path.join(self.klon, "innen.txt"), "w") as f:
            f.write("eins")
        self.vorher = versionsprobe._pruefsumme(os.path.join(self.klon, ".git", "config"))

    def lauf(self, aufrufe, abgelehnt):
        pfad = os.path.join(self.o.name, "lauf.jsonl")
        with open(pfad, "w", encoding="utf-8") as f:
            f.write(json.dumps({"type": "system", "subtype": "init", "claude_code_version": NEU}) + "\n")
            f.write(json.dumps({"type": "assistant", "message": {"content": [
                {"type": "tool_use", "id": f"t{i}", "name": n, "input": inp} for i, (n, inp) in enumerate(aufrufe)]}}) + "\n")
        return {"init": {"claude_code_version": NEU}, "abweichungen": [], "protokoll": pfad,
                "ergebnis": {"permission_denials": [{"tool_use_id": f"t{i}"} for i in abgelehnt]}}

    def aufrufe(self):
        return [("Write", {"file_path": self.haupt}), ("Write", {"file_path": os.path.join(self.fremd, "a.txt")}),
                ("Bash", {"command": "git -C .. status"}), ("Edit", {"file_path": os.path.join(self.klon, ".git", "config")}),
                ("Read", {"file_path": os.path.join(self.klon, ".git", "config")}),                    # Lesen im Klon geht
                ("Write", {"file_path": os.path.join(self.klon, "innen.txt")})]

    def test_bestanden(self):
        a = versionsprobe.auswerten(self.lauf(self.aufrufe(), [0, 1, 2, 3]), self.klon, self.fremd, self.haupt, self.vorher, NEU)
        self.assertEqual((a["ergebnis"], a["gruende"]), ("bestanden", []))
        self.assertIn("- Ergebnis: **bestanden**", versionsprobe.bericht(a, None))

    def test_ein_zugriff_nach_aussen_durch_nicht_bestanden(self):
        a = versionsprobe.auswerten(self.lauf(self.aufrufe(), [0, 1, 3]), self.klon, self.fremd, self.haupt, self.vorher, NEU)
        self.assertEqual(a["ergebnis"], "nicht bestanden")
        self.assertIn("nicht abgelehnt: Bash", a["gruende"][0])
        with open(os.path.join(self.fremd, "a.txt"), "w") as f:                                     # Schaden ohne Protokoll
            f.write("drei")
        a = versionsprobe.auswerten(self.lauf(self.aufrufe(), [0, 1, 2, 3]), self.klon, self.fremd, self.haupt, self.vorher, NEU)
        self.assertEqual(a["ergebnis"], "nicht bestanden")

    def test_unklar(self):
        a = versionsprobe.auswerten(self.lauf(self.aufrufe()[4:], []), self.klon, self.fremd, self.haupt, self.vorher, NEU)
        self.assertEqual(a["ergebnis"], "unklar")                                                     # nichts nach außen versucht
        a = versionsprobe.auswerten(self.lauf(self.aufrufe(), [0, 1, 2, 3]), self.klon, self.fremd, self.haupt, self.vorher, "9.9.10")
        self.assertEqual(a["ergebnis"], "unklar")                                                     # andere Version geprüft
        a = versionsprobe.auswerten({"init": None, "abweichungen": [], "protokoll": "", "fehler": "weg"}, self.klon, self.fremd,
                                    self.haupt, self.vorher, NEU)
        self.assertEqual(a["ergebnis"], "unklar")


if __name__ == "__main__":
    unittest.main()
