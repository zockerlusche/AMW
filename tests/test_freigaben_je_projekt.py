"""A2032 (TH164 „Freigaben“): wer Grobplan, Feinplan und Abschluss freigibt, ist je Projekt einstellbar (grobplan_freigabe,
feinplan_freigabe, abschluss_freigabe: mensch | co+lead), Vorgabe der Mensch – unabhängig von thema_freigabe. Setzen dürfen
nur Lead und Mensch; was der Lead umstellt, steht im Protokoll."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import db, grobplan, kern, planansicht, planung, projektweg, themen, tore


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "Co")
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="Co")
        self.th = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        self.m1 = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", ziel=f"TH{self.th}", abnahme="Vorführung")
        self.a1 = planung.schritt_setzen(self.con, self.pid, "TL", titel="SSO bauen", bogen_id=self.m1)
        themen.verweise_setzen(self.con, self.pid, "TL", self.a1, [f"TH{self.th}"])

    def regel(self, **werte):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, **werte)

    def frei(self, art):
        return bool((planansicht._zustaende(self.con, self.pid).get((self.m1, art)) or {}).get("an"))


class Einstellung(Grund):
    def test_vorgabe_mensch_auch_wenn_themen_co_lead(self):
        """Geändertes Verhalten: thema_freigabe = co+lead gilt nur noch für Themen. Meilensteine gibt der Mensch frei, bis er
        grobplan_/feinplan_/abschluss_freigabe selbst umstellt."""
        self.regel(thema_freigabe="co+lead")
        for stufe, k in (("grob", "grobplan_freigabe"), ("plan", "feinplan_freigabe"), ("abschluss", "abschluss_freigabe")):
            self.assertEqual(themen.freigabe_regel(self.con, self.pid, stufe), "mensch", k)
        self.assertEqual(themen.freigabe_regel(self.con, self.pid), "co+lead")
        self.assertEqual(themen.freigabe_regel(self.con, self.pid, "konzept"), "co+lead")
        with self.assertRaisesRegex(kern.AmwFehler, r"Meilensteine gibt in diesem Projekt der Mensch frei \(grobplan_freigabe = mensch\)"):
            planansicht.freigeben(self.con, self.pid, "Co", self.m1, "grob")

    def test_je_art_unabhaengig(self):
        self.regel(grobplan_freigabe="co+lead")
        self.assertEqual(planansicht.freigeben(self.con, self.pid, "Co", self.m1, "grob"), {"frei": False, "ja_fehlt": ["Lead"]})
        self.assertEqual(planansicht.freigeben(self.con, self.pid, "TL", self.m1, "grob"), {"frei": True})
        self.assertTrue(self.frei("grob"))
        with self.assertRaisesRegex(kern.AmwFehler, r"Pläne gibt in diesem Projekt der Mensch frei \(feinplan_freigabe = mensch\)"):
            planansicht.freigeben(self.con, self.pid, "TL", self.m1, "plan")
        self.regel(feinplan_freigabe="co+lead")
        planansicht.freigeben(self.con, self.pid, "TL", self.m1, "plan")
        self.assertFalse(self.frei("plan"))
        planansicht.freigeben(self.con, self.pid, "Co", self.m1, "plan")
        self.assertTrue(self.frei("plan"))
        m = next(x for x in planansicht.daten(self.con, self.pid)["meilensteine"] if x["id"] == self.m1)
        self.assertEqual(m["grob"]["ja_fehlt"], [])

    def test_ja_fehlt_nur_bei_co_lead_der_art(self):
        self.regel(grobplan_freigabe="co+lead")
        m = next(x for x in planansicht.daten(self.con, self.pid)["meilensteine"] if x["id"] == self.m1)
        self.assertEqual(m["grob"]["ja_fehlt"], ["Co-Entwickler", "Lead"])
        self.assertEqual(m["plan"]["ja_fehlt"], [])                                   # Plan: der Mensch, kein Ja von Co/Lead

    def test_nur_lead_und_mensch_stellen_um_lead_im_protokoll(self):
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "CC1", grobplan_freigabe="co+lead")
        with self.assertRaises(kern.AmwFehler):
            self.regel(abschluss_freigabe="alle")
        kern.projekt_einstellen(self.con, self.pid, "TL", abschluss_freigabe="co+lead")
        self.assertEqual(themen.freigabe_regel(self.con, self.pid, "abschluss"), "co+lead")
        p = self.con.execute("SELECT von, text FROM plan_ereignis WHERE art = 'einstellung_lead'").fetchall()
        self.assertEqual(len(p), 1)
        self.assertEqual(json.loads(p[0]["text"])["schluessel"], "abschluss_freigabe")
        from amw import cli
        for k in ("grobplan_freigabe", "feinplan_freigabe", "abschluss_freigabe"):
            self.assertIn(k, cli.RECHTE_EINSTELLUNGEN)                              # Sperre wie „agent lead“


class Folgen(Grund):
    def test_fuer_dich_und_wer_ist_dran_je_art(self):
        """tore.stand „für dich“ und projektweg „wer“ richten sich nach der Einstellung der jeweiligen Art."""
        st = lambda: tore.stand(self.con, self.pid)["fuer_dich"]["meilensteine"]
        self.assertEqual(st(), 1)                                  # Grob fehlt, der Mensch gibt frei
        self.regel(grobplan_freigabe="co+lead")
        self.assertEqual(st(), 0)                                  # Grob geben Co und Lead – kein Handlungsbedarf für dich
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m1, "grob")
        self.assertEqual(st(), 1)                                  # jetzt fehlt der Plan, den gibst du frei
        self.assertEqual(projektweg._freigebende(self.con, self.pid, "plan"), [kern.entwickler_name(self.con, self.pid)])
        self.assertEqual(projektweg._freigebende(self.con, self.pid, "grob"), ["Co", "TL"])
        self.regel(feinplan_freigabe="co+lead")
        self.assertEqual(st(), 0)

    def test_grobplan_ja_nach_grobplan_freigabe_konzept_nach_thema_freigabe(self):
        q = mock.patch.object(grobplan, "STARTER", lambda pid, fassung: 1)
        q.start()
        self.addCleanup(q.stop)
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'verworfen' WHERE projekt_id = ?", (self.pid,))
        themen.pflegen(self.con, self.pid, "CC1", self.th, "Anmelden mit Firmen-Konto.")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.th)
        self.regel(grobplan_freigabe="co+lead")
        with self.assertRaisesRegex(kern.AmwFehler, r"thema_freigabe = mensch"):
            grobplan.abschliessen(self.con, self.pid, "Co")                    # Konzept-Ja nach thema_freigabe
        grobplan.abschliessen(self.con, self.pid, kern.ENTWICKLER)
        plan = {"befunde": [], "fragen": [], "meilensteine": [{"schluessel": "M1", "titel": "Anmelden", "ziel": f"TH{self.th}",
                "themen": [f"TH{self.th}"], "fertig_wenn": "vorgeführt", "endet_mit": "vorfuehrung", "nach": [], "gleichzeitig": [],
                "aufwand": "S"}]}
        grobplan.entwurf_eintragen(self.con, self.pid, 1, json.dumps(plan))
        self.assertEqual(grobplan.annehmen(self.con, self.pid, "Co"), {"angenommen": False, "ja_fehlt": ["Lead"]})
        self.assertTrue(grobplan.annehmen(self.con, self.pid, "TL")["angenommen"])
        self.regel(grobplan_freigabe="mensch")
        with self.assertRaisesRegex(kern.AmwFehler, r"grobplan_freigabe = mensch"):
            grobplan._stimme(self.con, self.pid, "TL", grobplan.JA_STIMME, 0, "grob")

    def test_abschlussbericht_meldung_an_den_menschen_nach_abschluss_freigabe(self):
        self.regel(thema_freigabe="co+lead")                       # Themen co+lead, Abschluss bleibt beim Menschen
        tore.bericht_erstellen(self.con, self.pid, self.m1, bereit=True)
        an = {r["agent"] for r in self.con.execute(
            "SELECT e.agent FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE n.kurz LIKE '%bereit zur Abnahme%'")}
        self.assertIn(kern.ENTWICKLER, an)


if __name__ == "__main__":
    unittest.main()
