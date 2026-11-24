"""A2028: Hinweise an den Planer und „Überarbeiten lassen“ – für den Grobplan und den Plan je Thema; jede Fassung bleibt,
Änderungen gegenüber der vorigen sind markiert, der Verlauf zeigt die Hinweise."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import copy
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeiter, db, grobplan, kern, planer, planhinweis, themen, verlauf

PLAN = {"meilensteine": [{"schluessel": "M1", "titel": "Anmelden online", "endet_mit": "vorfuehrung"}],
        "pakete": [{"schluessel": "P1", "meilenstein": "M1", "titel": "Anmeldung mit Firmen-Konto", "auftrag": "SSO bauen.",
                    "groesse": "M", "art": "sicherheit", "ausfuehrung": "agent", "fertig_quelle": "release"},
                   {"schluessel": "P2", "meilenstein": "M1", "titel": "Abmelden", "auftrag": "Knopf.",
                    "groesse": "S", "art": "oberflaeche", "ausfuehrung": "agent", "fertig_quelle": "commit"}]}


def grob(tid, **mehr):
    d = {"befunde": [], "fragen": [], "meilensteine": [
        {"schluessel": "M1", "titel": "Anmelden", "ziel": f"TH{tid}", "themen": [f"TH{tid}"], "fertig_wenn": "vorgeführt",
         "endet_mit": "vorfuehrung", "nach": [], "gleichzeitig": [], "aufwand": "M"}]}
    d.update(mehr)
    return d


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_PLANER_AUS", None)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        from amw import schalter
        with db.schreiben(self.con):
            schalter._setzen(self.con, self.pid, "an")
        self.gestartet = []
        for mod, f in ((planer, lambda pid, tid, fassung: self.gestartet.append(("thema", tid)) or 1),
                       (grobplan, lambda pid, fassung: self.gestartet.append(("grob", fassung)) or 1)):
            p = mock.patch.object(mod, "STARTER", f)
            p.start()
            self.addCleanup(p.stop)
        self.tid = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Anmelden mit Firmen-Konto.")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)

    def befehl(self, *args, von="TL"):
        from amw import cli
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            rc = cli.main(["thema", *args, "--projekt", "Produkt", "--von", von])
        return rc, aus.getvalue()


class Hinweise(Grund):
    def test_erst_mit_entwurf_nur_mensch_lead_co(self):
        with self.assertRaisesRegex(kern.AmwFehler, "noch keinen Planentwurf"):
            planhinweis.hinweis(self.con, self.pid, "TL", f"TH{self.tid}", "Passkey auch")
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, PLAN)
        with self.assertRaisesRegex(kern.AmwFehler, "der Mensch, der Lead und der Co-Entwickler"):
            planhinweis.hinweis(self.con, self.pid, "CC1", f"TH{self.tid}", "x")
        for bezug, text in (("Q1", "x"), (None, "  ")):
            with self.assertRaises(kern.AmwFehler):
                planhinweis.hinweis(self.con, self.pid, "TL", f"TH{self.tid}", text, bezug)
        with self.assertRaises(kern.AmwFehler):
            planhinweis.hinweis(self.con, self.pid, "TL", "irgendwas", "x")
        planhinweis.hinweis(self.con, self.pid, kern.ENTWICKLER, self.tid, "Passkey auch", "p1")
        h = planhinweis.offene(self.con, self.pid, f"TH{self.tid}")
        self.assertEqual([(x["von"], x["bezug"], x["text"]) for x in h], [(kern.ENTWICKLER, "P1", "Passkey auch")])

    def test_ueberarbeiten_gibt_dem_planer_vorigen_entwurf_und_hinweise(self):
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, PLAN)
        with self.assertRaisesRegex(kern.AmwFehler, "Keine offenen Hinweise"):
            planhinweis.ueberarbeiten(self.con, self.pid, "TL", f"TH{self.tid}")
        rc, aus = self.befehl("hinweis", f"TH{self.tid}", "--text", "Abmelden entfällt, dafür Passkey", "--zu", "P2")
        self.assertIn("Hinweis vermerkt (1 offen)", aus)
        rc, aus = self.befehl("ueberarbeiten", f"TH{self.tid}")
        self.assertIn("angestoßen", aus)
        self.assertEqual(self.gestartet, [("thema", self.tid)])
        gesehen = {}
        neu = copy.deepcopy(PLAN)
        neu["pakete"][1].update(titel="Passkey", auftrag="Passkey zur Anmeldung.")
        neu["pakete"][0]["groesse"] = "L"

        def laufen(p, auftrag, *_a, **_k):
            gesehen["auftrag"] = auftrag
            gesehen["vorige"] = json.load(open(os.path.join(p["klon"], "vorige.json"), encoding="utf-8"))
            gesehen["hinweise"] = open(os.path.join(p["klon"], "hinweise.md"), encoding="utf-8").read()
            return {"rc": 0, "ergebnis": {"result": json.dumps(neu), "total_cost_usd": 0.1}}
        with mock.patch.object(arbeiter, "laufen", side_effect=laufen):
            planer.ausfuehren(self.con, self.pid, self.tid, 1)
        self.assertIn("ÜBERARBEITEN", gesehen["auftrag"])
        self.assertEqual(gesehen["vorige"]["pakete"][1]["titel"], "Abmelden")
        self.assertIn("TL zu P2: Abmelden entfällt, dafür Passkey", gesehen["hinweise"])
        self.assertEqual(planhinweis.offene(self.con, self.pid, f"TH{self.tid}"), [])          # mit dem Entwurf bearbeitet
        rc, aus = self.befehl("plan", f"TH{self.tid}")
        self.assertIn("Änderungen gegenüber Entwurf 1:", aus)
        self.assertIn("+ neu: Paket „Passkey“", aus)
        self.assertIn("~ geändert: Paket „Anmeldung mit Firmen-Konto“ (groesse)", aus)
        self.assertIn("− entfallen: Paket „Abmelden“", aus)
        self.assertIn("bearbeitet · TL zu P2: Abmelden entfällt", aus)
        self.assertEqual(len(planer._ereignisse(self.con, self.pid, self.tid, planer.ENTWURF)), 2)   # beide Fassungen bleiben

    def test_ohne_hinweise_kein_ueberarbeiten_auftrag(self):
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, PLAN)
        gesehen = {}

        def laufen(p, auftrag, *_a, **_k):
            gesehen["auftrag"], gesehen["dateien"] = auftrag, sorted(os.listdir(p["klon"]))
            return {"rc": 0, "ergebnis": {"result": json.dumps(PLAN)}}
        with mock.patch.object(arbeiter, "laufen", side_effect=laufen):
            planer.planen(self.con, self.pid, themen.finden(self.con, self.pid, self.tid), 1, "sonnet")
        self.assertNotIn("ÜBERARBEITEN", gesehen["auftrag"])
        self.assertNotIn("hinweise.md", gesehen["dateien"])


class Grobplan(Grund):
    def setUp(self):
        super().setUp()
        grobplan.abschliessen(self.con, self.pid, kern.ENTWICKLER)
        grobplan.entwurf_eintragen(self.con, self.pid, 1, json.dumps(grob(self.tid)))

    def test_hinweis_ueberarbeiten_neue_fassung_markiert(self):
        planhinweis.hinweis(self.con, self.pid, kern.ENTWICKLER, "grob", "Anmelden ist größer – L", "M1")
        self.assertIn("Grobplan Fassung 2: Planer (opus) angestoßen",
                      planhinweis.ueberarbeiten(self.con, self.pid, kern.ENTWICKLER, "grob") or "")
        gesehen = {}

        def laufen(p, auftrag, *_a, **_k):
            gesehen["auftrag"], gesehen["dateien"] = auftrag, sorted(os.listdir(p["klon"]))
            d = grob(self.tid)
            d["meilensteine"][0]["aufwand"] = "L"
            return {"rc": 0, "ergebnis": {"result": json.dumps(d), "total_cost_usd": 0.5}}
        with mock.patch.object(arbeiter, "laufen", side_effect=laufen):
            grobplan.ausfuehren(self.con, self.pid, 2)
        self.assertIn("ÜBERARBEITEN", gesehen["auftrag"])
        self.assertIn("hinweise.md", gesehen["dateien"])
        self.assertEqual([f["fassung"] for f in grobplan.fassungen(self.con, self.pid)], [1, 2])
        rc, aus = self.befehl("grobplan")
        self.assertIn("Änderungen gegenüber Fassung 1:", aus)
        self.assertIn("~ geändert: Meilenstein „Anmelden“ (aufwand)", aus)
        rc, aus = self.befehl("grobplan", "--fassung", "1")
        self.assertNotIn("Änderungen gegenüber", aus)                        # Fassung 1 hat keine davor
        weg = [e["text"] for e in verlauf.projektweg(self.con, self.pid)]
        self.assertIn("Hinweis an den Planer – Grobplan, zu M1: Anmelden ist größer – L", weg)


class Vergleich(unittest.TestCase):
    def test_ueber_titel_nicht_schluessel(self):
        alt = copy.deepcopy(PLAN)
        neu = copy.deepcopy(PLAN)
        neu["pakete"][0]["schluessel"], neu["pakete"][1]["schluessel"] = "P2", "P1"     # nur umnummeriert
        v = planhinweis.vergleich(alt, neu)
        self.assertEqual(v["pakete"], {"neu": [], "geaendert": [], "entfallen": []})
        self.assertEqual(planhinweis.zeilen(alt, neu, "Fassung 1"), [])


if __name__ == "__main__":
    unittest.main()
