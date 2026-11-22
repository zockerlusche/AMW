"""K8b / A1957 (F5358/F5359, Änderungsgrenze F5353): die eigene Änderung des Menschen an Meilenstein oder Paket gilt erst nach
der Folgenprüfung – als Vorschlag, ein frischer -p prüft (hier mit festem Ergebnis bzw. der Attrappe); nichts berührt → gilt von
selbst mit Info; sonst Ja oder Verwerfen; Fehler/Frist → bleibt Vorschlag, Ja übernimmt trotzdem; in Tests sonst sofort."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from amw import aktionen, cli, db, folgen, kern, planansicht, planung
from tests.test_arbeiter import ATTRAPPE

NICHTS = {"beruehrt_ziel": False, "beruehrt_erfolg": False, "beruehrt_kosten": False, "folgen": ["A2: Titel im Bericht anpassen"]}
KOSTEN = {"beruehrt_ziel": False, "beruehrt_erfolg": False, "beruehrt_kosten": True, "folgen": ["A2 wird größer (M statt S)"]}


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT", "AMW_FOLGEN_AUS"):
            os.environ.pop(k, None)                                     # hier wird geprüft (Starter ist eine Attrappe)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.m = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", ziel="Online anmelden", abnahme="Vorführung")
        self.a1 = planung.schritt_setzen(self.con, self.pid, "TL", titel="SSO bauen", bogen_id=self.m, agent="CC1", auftrag="SSO.")
        self.a2 = planung.schritt_setzen(self.con, self.pid, "TL", titel="Tests", bogen_id=self.m, nach=[self.a1])
        self.gestartet = []
        p = mock.patch.object(folgen, "STARTER", lambda pid, eid: self.gestartet.append(eid) or 1)
        p.start()
        self.addCleanup(p.stop)

    def titel(self):
        return planung.bogen_zeile(self.con, self.pid, self.m)["titel"]

    def post(self):
        return [(r["art"], r["kurz"], r["text"]) for r in self.con.execute(
            "SELECT n.art, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW'"
            " ORDER BY n.id", (kern.ENTWICKLER,))]


class Ablauf(Grund):
    def test_vorschlag_dann_gilt_von_selbst_ohne_beruehrung(self):
        r = folgen.vorschlagen(self.con, self.pid, kern.ENTWICKLER, "meilenstein", self.m, titel="Anmelden online")
        self.assertEqual((r["stand"], self.gestartet), ("prueft", [r["aenderung"]]))
        self.assertEqual(self.titel(), "Anmelden")                                            # gilt noch nicht
        o = folgen.offene(self.con, self.pid)
        self.assertEqual((o[0]["stand"], o[0]["alt"], o[0]["neu"]), ("prueft", {"titel": "Anmelden"}, {"titel": "Anmelden online"}))
        self.assertEqual(planansicht.daten(self.con, self.pid)["aenderungen"][0]["stand"], "prueft")   # die Seite zeigt es sofort
        self.assertEqual(folgen.abschliessen(self.con, self.pid, r["aenderung"], json.dumps(NICHTS), usd=0.04), "gilt")
        self.assertEqual(self.titel(), "Anmelden online")
        self.assertEqual(folgen.offene(self.con, self.pid), [])
        art, kurz, text = self.post()[-1]
        self.assertEqual((art, kurz), ("info", "Änderung gilt: Meilenstein 1 „Anmelden“ – Titel"))
        self.assertIn("A2: Titel im Bericht anpassen", text)

    def test_beruehrt_kosten_wartet_auf_ja(self):
        r = folgen.vorschlagen(self.con, self.pid, kern.ENTWICKLER, "meilenstein", self.m, abnahme="Vorführung am Handy")
        self.assertEqual(folgen.abschliessen(self.con, self.pid, r["aenderung"], KOSTEN), "wartet")
        self.assertEqual(planung.bogen_zeile(self.con, self.pid, self.m)["abnahme"], "Vorführung")
        o = folgen.offene(self.con, self.pid)[0]
        self.assertEqual((o["stand"], o["beruehrt"], o["folgen"]), ("wartet", ["Kosten"], ["A2 wird größer (M statt S)"]))
        self.assertIn("wartet auf dein Ja", self.post()[-1][1])
        with self.assertRaisesRegex(kern.AmwFehler, "entscheidet der Mensch"):
            folgen.entscheiden(self.con, self.pid, "TL", r["aenderung"], True)
        self.assertEqual(folgen.entscheiden(self.con, self.pid, kern.ENTWICKLER, r["aenderung"], True), "gilt")
        self.assertEqual(planung.bogen_zeile(self.con, self.pid, self.m)["abnahme"], "Vorführung am Handy")
        with self.assertRaisesRegex(kern.AmwFehler, "schon entschieden"):
            folgen.entscheiden(self.con, self.pid, kern.ENTWICKLER, r["aenderung"], False)

    def test_verwerfen(self):
        r = folgen.vorschlagen(self.con, self.pid, kern.ENTWICKLER, "paket", self.a1, auftrag="SSO und Passkey.")
        folgen.abschliessen(self.con, self.pid, r["aenderung"], KOSTEN)
        self.assertEqual(folgen.entscheiden(self.con, self.pid, kern.ENTWICKLER, r["aenderung"], False), "verworfen")
        self.assertEqual(self.con.execute("SELECT auftrag FROM aufgabe WHERE id = ?", (self.a1,)).fetchone()[0], "SSO.")
        self.assertEqual(folgen.offene(self.con, self.pid), [])

    def test_fehler_oder_unbrauchbar_bleibt_vorschlag_ja_uebernimmt(self):
        r = folgen.vorschlagen(self.con, self.pid, kern.ENTWICKLER, "paket", self.a1, titel="SSO")
        folgen.abschliessen(self.con, self.pid, r["aenderung"], None, fehler="Frist 10 min überschritten – beendet")
        o = folgen.offene(self.con, self.pid)[0]
        self.assertEqual((o["stand"], o["fehler"]), ("fehler", "Frist 10 min überschritten – beendet"))
        self.assertIn("Ja übernimmt sie trotzdem", self.post()[-1][2])
        folgen.entscheiden(self.con, self.pid, kern.ENTWICKLER, r["aenderung"], True)
        self.assertEqual(self.con.execute("SELECT titel FROM aufgabe WHERE id = ?", (self.a1,)).fetchone()[0], "SSO")
        r = folgen.vorschlagen(self.con, self.pid, kern.ENTWICKLER, "paket", self.a1, titel="SSO bauen")
        folgen.abschliessen(self.con, self.pid, r["aenderung"], "kein JSON hier")
        self.assertIn("unbrauchbar", folgen.offene(self.con, self.pid)[0]["fehler"])

    def test_nur_der_mensch_unveraendert_und_aus(self):
        with self.assertRaisesRegex(kern.AmwFehler, "eigene Änderung des Menschen"):
            folgen.vorschlagen(self.con, self.pid, "TL", "meilenstein", self.m, titel="x")
        self.assertEqual(folgen.vorschlagen(self.con, self.pid, kern.ENTWICKLER, "meilenstein", self.m, titel="Anmelden")["stand"], "unveraendert")
        kern.projekt_einstellen(self.con, self.pid, "TL", themen_gegenlesen="aus")              # Prüfen aus: gilt sofort
        self.assertEqual(folgen.vorschlagen(self.con, self.pid, kern.ENTWICKLER, "meilenstein", self.m, titel="Neu")["stand"], "gilt")
        self.assertEqual(self.titel(), "Neu")


class Wege(Grund):
    def test_workbench_meilenstein_dialog_und_ja(self):
        r = aktionen.planen(self.con, self.pid, "bogen", {"bogen": self.m, "titel": "Anmelden online", "ziel": "Online anmelden",
                                                          "abnahme": "Vorführung"})
        self.assertEqual((r["stand"], self.titel()), ("prueft", "Anmelden"))
        folgen.abschliessen(self.con, self.pid, r["aenderung"], KOSTEN)
        aktionen.ausfuehren(self.con, self.pid, "/api/meilenstein/aenderung-ja", {"aenderung": r["aenderung"]}, "seite") \
            if hasattr(aktionen, "ausfuehren") else folgen.entscheiden(self.con, self.pid, kern.ENTWICKLER, r["aenderung"], True)
        self.assertEqual(self.titel(), "Anmelden online")

    def test_befehle_des_menschen_im_eigenen_terminal(self):
        def befehl(*args):
            aus = io.StringIO()
            with contextlib.redirect_stdout(aus), mock.patch.object(cli, "_aus_agenten_sitzung", return_value=False):
                rc = cli.main([*args, "--projekt", "Spiel", "--von", "Entwickler"])
            return rc, aus.getvalue()
        rc, aus = befehl("aufgabe", "aendern", str(self.a1), "--titel", "SSO mit Passkey", "--auftrag", "Neu.")
        self.assertEqual(rc, 0)
        self.assertIn("Änderung wird geprüft", aus)
        self.assertEqual(self.con.execute("SELECT titel, auftrag FROM aufgabe WHERE id = ?", (self.a1,)).fetchone()[:], ("SSO bauen", "SSO."))
        o = folgen.offene(self.con, self.pid)[-1]
        self.assertEqual(o["neu"], {"titel": "SSO mit Passkey", "auftrag": "Neu."})
        planung.schritt_setzen(self.con, self.pid, "TL", aid=self.a1, titel="Vom Lead")                 # Agenten/Lead: wie bisher sofort
        self.assertEqual(self.con.execute("SELECT titel FROM aufgabe WHERE id = ?", (self.a1,)).fetchone()[0], "Vom Lead")

    def test_lauf_in_der_schlange_selbst_mit_kosten(self):
        from amw import betrieb
        r = folgen.vorschlagen(self.con, self.pid, kern.ENTWICKLER, "meilenstein", self.m, titel="Anmelden online")
        with mock.patch.object(folgen, "pruefer", return_value={"ergebnis": json.dumps(NICHTS), "usd": 0.031, "fehler": None}):
            folgen.ausfuehren(self.con, self.pid, r["aenderung"])
        l = self.con.execute("SELECT id, status, rc, beschreibung, ergebnis FROM lauf ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual((l["status"], l["rc"]), ("fertig", 0))
        self.assertTrue(betrieb.selbst_gestartet(self.con, l["id"]))                            # kein Weckruf (A1948)
        self.assertIn("0.03 $", l["ergebnis"])
        self.assertEqual(self.titel(), "Anmelden online")


@unittest.skipUnless(os.name == "nt" and shutil.which("git"), "Arbeiter nur unter Windows (Job-Objekt)")
class MitAttrappe(Grund):
    def pruefe(self, art, **env):
        r = folgen.vorschlagen(self.con, self.pid, kern.ENTWICKLER, "meilenstein", self.m, titel="Anmelden online")
        datei = os.path.join(self.ordner.name, "aufruf.json")
        aus = folgen.pruefer(self.con, self.pid, folgen.vorschlag(self.con, self.pid, r["aenderung"]), "haiku", prog=ATTRAPPE,
                             zusatz={"ATTRAPPE_ART": art, "ATTRAPPE_UMGEBUNG": datei, **env})
        return aus, datei

    def test_nur_lesen_mit_dateien(self):
        aus, datei = self.pruefe("gegenlesen", ATTRAPPE_ERGEBNIS=json.dumps(KOSTEN))
        self.assertEqual(folgen.pruefen(aus["ergebnis"])["beruehrt_kosten"], True)
        with open(datei, encoding="utf-8") as f:
            a = json.load(f)
        self.assertEqual(a["argv"][a["argv"].index("--tools") + 1], "Glob,Grep,Read")
        self.assertEqual(a["dateien"], [".git", "aenderung.md", "darunter.md"])

    def test_frist(self):
        with mock.patch.object(folgen, "FRIST_S", 3):
            aus, _ = self.pruefe("haengt")
        self.assertIn("Frist", aus["fehler"])


if __name__ == "__main__":
    unittest.main()
