"""A2030: Grobplanung einmal fürs ganze Konzept – Konzept abschließen, ein Grob-Planer über alle freigegebenen Themen, Fassungen,
Prüfung des Ergebnisses, Grobplan-Ja legt Meilensteine an und gibt sie grob frei."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import db, grobplan, kern, planer, planer_fortschritt, planung, projektweg, themen, tore, verlauf


def plan(t1, t2, **mehr):
    """Ein gültiges Planer-Ergebnis über zwei Themen."""
    d = {"befunde": [{"art": "doppelt", "themen": [f"TH{t1}", f"TH{t2}"], "text": "Anmelden steht in beiden.",
                      "vorschlag": "in TH{t1} zusammenlegen"}],
         "fragen": [{"frage": "Anmelden auch mit Passwort?", "optionen": {"A": "nur Firmen-Konto", "B": "auch Passwort"},
                     "empfehlung": "A", "grund": "weniger Pflege", "themen": [f"TH{t1}"]}],
         "meilensteine": [
             {"schluessel": "M2", "titel": "Sichern", "ziel": f"TH{t2} Sicherung läuft jede Nacht", "themen": [f"TH{t2}"],
              "fertig_wenn": "Sicherung und Rücksicherung vorgeführt", "endet_mit": "vorfuehrung", "nach": ["M1"],
              "gleichzeitig": [], "aufwand": "s", "tage": 2, "usd": 8},
             {"schluessel": "M1", "titel": "Anmelden", "ziel": "Anmeldung mit Firmen-Konto", "themen": [f"TH{t1}"],
              "fertig_wenn": "Anmelden am Handy vorgeführt", "endet_mit": "vorfuehrung", "nach": [], "gleichzeitig": [],
              "aufwand": "M", "tage": 4, "usd": 20.5}],
         "grund": "erst anmelden, dann sichern"}
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
        kern.agent_neu(self.con, self.pid, "Co")
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="Co")
        self.schalter("an")
        self.gestartet = []
        p = mock.patch.object(grobplan, "STARTER", lambda pid, fassung: self.gestartet.append((pid, fassung)) or 4711)
        p.start()
        self.addCleanup(p.stop)
        q = mock.patch.object(planer, "STARTER", lambda pid, tid, fassung: 1)      # Planer je Thema nach der Freigabe: Attrappe
        q.start()
        self.addCleanup(q.stop)
        self.t1 = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.t1, "Wer die Seite öffnet, meldet sich mit dem Firmen-Konto an.")
        self.t2 = themen.neu(self.con, self.pid, "TL", "Sicherung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.t2, "Jede Nacht eine Sicherung.")

    def schalter(self, wert):
        from amw import schalter
        with db.schreiben(self.con):
            schalter._setzen(self.con, self.pid, wert)

    def frei(self):
        for t in (self.t1, self.t2):
            themen.freigeben(self.con, self.pid, kern.ENTWICKLER, t)

    def post(self, an):
        return [(r["art"], r["kurz"], r["text"]) for r in self.con.execute(
            "SELECT n.art, n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW'"
            " ORDER BY n.id", (an,))]

    def befehl(self, *args, von="TL"):
        from amw import cli
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            rc = cli.main(["thema", *args, "--projekt", "Produkt", "--von", von])
        return rc, aus.getvalue()


class Pruefen(Grund):
    def test_gueltig_und_bereinigt(self):
        self.frei()
        e = grobplan.pruefen(json.dumps(plan(self.t1, self.t2)), grobplan.themen_frei(self.con, self.pid))
        self.assertEqual([m["schluessel"] for m in grobplan.reihenfolge(e)], ["M1", "M2"])          # nach M1 kommt M2
        self.assertEqual(e["meilensteine"][0]["aufwand"], "S")
        self.assertEqual(e["meilensteine"][1]["themen"], [self.t1])
        self.assertEqual(e["fragen"][0]["empfehlung"], "A")
        z = grobplan.zusammenfassung(e)
        self.assertIn("M1 Anmelden · M · 4 Tage · 20 $ · endet mit Vorführung", z)
        self.assertIn("M2 Sichern · S · 2 Tage · 8 $ · endet mit Vorführung · nach M1", z)
        self.assertIn("Befund (doppelt)", z)

    def test_alle_funde_auf_einmal(self):
        self.frei()
        frei = grobplan.themen_frei(self.con, self.pid)
        d = plan(self.t1, self.t2)
        d["meilensteine"][0].update(themen=["TH999"], nach=["M7"], endet_mit="feier", aufwand="XXL")
        d["meilensteine"][1].update(titel="", fertig_wenn=None)
        d["fragen"][0]["empfehlung"] = "C"
        d["befunde"][0]["art"] = "toll"
        with self.assertRaises(planer.PlanFehler) as f:
            grobplan.pruefen(d, frei)
        alle = " | ".join(f.exception.fehler)
        for erwartet in ("TH999 ist kein freigegebenes Thema", "nach M7 gibt es im Plan nicht", "endet_mit „feier“",
                         "aufwand „XXL“", "titel fehlt", "fertig_wenn fehlt", "empfehlung „C“", "art „toll“",
                         f"Abdeckung: TH{self.t2} in keinem Meilenstein"):
            self.assertIn(erwartet, alle)
        with self.assertRaises(planer.PlanFehler):
            grobplan.pruefen("kein json", frei)

    def test_kreis_und_abdeckung_mit_befund(self):
        self.frei()
        frei = grobplan.themen_frei(self.con, self.pid)
        d = plan(self.t1, self.t2)
        d["meilensteine"][1]["nach"] = ["M2"]
        with self.assertRaisesRegex(planer.PlanFehler, "Kreis"):
            grobplan.pruefen(d, frei)
        d = plan(self.t1, self.t2)
        d["meilensteine"] = d["meilensteine"][1:]                         # nur M1 (TH1) – TH2 fehlt …
        d["befunde"].append({"art": "abdeckung", "themen": [f"TH{self.t2}"], "text": "Sicherung macht der Hoster schon."})
        self.assertEqual(len(grobplan.pruefen(d, frei)["meilensteine"]), 1)  # … mit Befund „abdeckung“ ist das in Ordnung


class Tore(Grund):
    def test_thema_zaehlt_ueber_den_verweis_im_ziel(self):
        """Gegenprobe zu tore.stand: ein Meilenstein ohne Pakete zählt ein Thema nur, wenn sein Ziel auf das Thema verweist."""
        self.frei()
        planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", ziel="Anmeldung mit Firmen-Konto")
        g = lambda: next(x for x in tore.stand(self.con, self.pid)["tore"] if x["tor"] == "grobplanung")
        self.assertEqual((g()["n"], g()["g"]), (0, 2))
        planung.bogen_neu(self.con, self.pid, "TL", "Sichern", ziel=f"TH{self.t2} Sicherung")
        self.assertEqual(g()["n"], 1)
        planung.bogen_neu(self.con, self.pid, "TL", "Fremd", ziel="TH9999 gibt es nicht")
        self.assertEqual((g()["n"], g()["g"]), (1, 2))

    def test_neues_projekt_freigabe_ohne_planer_je_thema(self):
        """TL #31613 A: Im neuen Projekt (keine Meilensteine, kein Abschluss) stößt die Freigabe keinen Planer je Thema an."""
        gestartet = []
        with mock.patch.object(planer, "STARTER", lambda pid, tid, fassung: gestartet.append(tid) or 1):
            self.frei()
        self.assertEqual(gestartet, [])


class Abschliessen(Grund):
    def test_erst_wenn_alle_themen_frei(self):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.t1)
        with self.assertRaisesRegex(kern.AmwFehler, "Erst alle Themen freigeben: 1 von 2"):
            grobplan.abschliessen(self.con, self.pid, kern.ENTWICKLER)
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.t2)
        with self.assertRaisesRegex(kern.AmwFehler, "der Mensch"):
            grobplan.abschliessen(self.con, self.pid, "TL")                    # thema_freigabe = mensch
        r = grobplan.abschliessen(self.con, self.pid, kern.ENTWICKLER)
        self.assertTrue(r["abgeschlossen"])
        self.assertIn("Grobplan Fassung 1: Planer (opus) angestoßen – 2 Themen", r["planer"])
        self.assertEqual(self.gestartet, [(self.pid, 1)])
        self.assertEqual((grobplan.laeuft(self.con, self.pid) or {}).get("prozess"), 4711)
        self.assertEqual((grobplan.abgeschlossen(self.con, self.pid) or {}).get("themen"), {str(self.t1): 1, str(self.t2): 1})
        self.assertEqual(grobplan.anstossen(self.con, self.pid), "Es plant schon ein Grob-Planer")
        self.assertEqual(len(self.gestartet), 1)

    def test_co_und_lead_je_ein_ja(self):
        self.frei()
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, thema_freigabe="co+lead")
        with self.assertRaisesRegex(kern.AmwFehler, "Co-Entwickler und der Lead"):
            grobplan.abschliessen(self.con, self.pid, "CC1")
        self.assertEqual(grobplan.abschliessen(self.con, self.pid, "Co"), {"abgeschlossen": False, "ja_fehlt": ["Lead"]})
        self.assertEqual(self.gestartet, [])
        self.assertTrue(grobplan.abschliessen(self.con, self.pid, "TL")["abgeschlossen"])
        self.assertEqual((grobplan.abgeschlossen(self.con, self.pid) or {}).get("durch"), ["Co", "TL"])
        self.assertEqual(len(self.gestartet), 1)

    def test_projekt_aus_und_tagesgrenze(self):
        self.frei()
        self.schalter("aus")
        self.assertIn("Projekt ist ausgeschaltet", grobplan.abschliessen(self.con, self.pid, kern.ENTWICKLER)["planer"])
        self.schalter("an")
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, planer_tagesgrenze_usd=1)
        grobplan.entwurf_eintragen(self.con, self.pid, 1, None, modell="opus", usd=1.5, fehler="weg")   # kostete heute schon
        self.assertEqual(planer.heute_usd(self.con, self.pid), 1.5)                           # gemeinsame Grenze der Planer
        self.assertIn("Tagesgrenze der Planer erreicht (1.50 von 1.00 $)", grobplan.anstossen(self.con, self.pid))
        self.assertEqual(self.gestartet, [])


class Bestand(Grund):
    """A2062 (a): Projekt mit Meilensteinen → „Konzept abschließen“ abgewiesen (CLI und API über grobplan.abschliessen),
    mit Hinweis auf die Übernahme; ohne Meilensteine (Gegenprobe) startet der Planer wie bisher."""

    def test_bestand_sperrt_ohne_bestand_startet(self):
        self.frei()
        planung.bogen_neu(self.con, self.pid, "TL", "Schon da")
        with self.assertRaisesRegex(kern.AmwFehler, "1 Meilenstein.*bei Bestand gesperrt.*A2062"):
            grobplan.abschliessen(self.con, self.pid, kern.ENTWICKLER)
        self.assertEqual(self.gestartet, [])
        from amw import aktionen
        with self.assertRaisesRegex(aktionen.Ungueltig, "bei Bestand gesperrt"):          # die Seite zeigt den Text als Fehler
            aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/konzept-abschliessen", {}, kanal="seite")
        rc, aus = self.befehl("konzept-abschliessen", von=kern.ENTWICKLER)
        self.assertEqual(rc, 1)
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'verworfen' WHERE projekt_id = ?", (self.pid,))
        self.assertTrue(grobplan.abschliessen(self.con, self.pid, kern.ENTWICKLER)["abgeschlossen"])   # verworfen zählt nicht
        self.assertEqual(len(self.gestartet), 1)


class Uebernahme(Grund):
    """A2062 (b): Projekt mit Bestand → Grobplan Fassung 0 = Bestand, gilt als angenommen und grob freigegeben; Thema → Meilenstein
    als Daten der Grob-Karten (Ziel-Verweise und Themen der Aufgaben); Marcels Befunde 1/2: Schritt nicht mehr Grob, Grob nicht leer."""

    def test_bestand_wird_fassung_0_und_gilt(self):
        from amw import projektweg, projektweg_seite
        self.frei()
        m1 = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", ziel=f"TH{self.t1} Anmeldung")
        planung.bogen_status(self.con, self.pid, "TL", m1, "aktiv")
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Sichern bauen", "CC1")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET bogen_id = ? WHERE id = ?", (m1, aid))
        themen.verweise_setzen(self.con, self.pid, "TL", aid, [self.t2])
        r = grobplan.uebernehmen(self.con, self.pid)
        self.assertEqual((r["fassung"], r["meilensteine"], r["ohne_meilenstein"]), (0, 1, []))
        self.assertTrue(grobplan.angenommen(self.con, self.pid))
        g = projektweg_seite.grob(self.con, self.pid)
        self.assertEqual(g["angenommen"]["fassung"], 0)
        m = g["fassungen"][0]["meilensteine"][0]                                                  # Befund 2: Grob nicht leer
        self.assertEqual((m["schluessel"], m["bestehend"], sorted(m["themen"]), m["status"]), ("M1", 1, sorted([self.t1, self.t2]), "aktiv"))
        self.assertNotEqual(projektweg.sicht(self.con, self.pid)["dran"], "grob")
        self.assertIsNone(grobplan.uebernehmen(self.con, self.pid))                               # einmal
        with self.assertRaisesRegex(kern.AmwFehler, "schon angenommen"):
            grobplan.abschliessen(self.con, self.pid, kern.ENTWICKLER)
        self.assertEqual(self.gestartet, [])                                                      # ohne Planer, ohne Kosten
        self.assertTrue(any("Grobplan übernommen" in k for _, k, _ in self.post("TL")))

    def test_ohne_bestand_nichts_und_runde(self):
        self.frei()
        self.assertIsNone(grobplan.uebernehmen(self.con, self.pid))                               # Gegenprobe: kein Bestand
        self.assertEqual(grobplan.uebernahme_runde(self.con), [])
        planung.bogen_neu(self.con, self.pid, "TL", "Sichern", ziel=f"TH{self.t2}")
        aus = grobplan.uebernahme_runde(self.con)
        self.assertEqual(len(aus), 1)
        r = grobplan.angenommen(self.con, self.pid)
        self.assertEqual(r["fassung"], 0)
        e = grobplan.entwurf(self.con, self.pid, 0)["entwurf"]
        self.assertEqual(e["befunde"][0]["themen"], [f"TH{self.t1}"])                             # frei, aber ohne Meilenstein


class Lauf(Grund):
    def setUp(self):
        super().setUp()
        self.frei()
        grobplan.abschliessen(self.con, self.pid, kern.ENTWICKLER)

    def test_lauf_traegt_fassung_ein_mit_fortschritt_meldung_und_fragen(self):
        unterwegs = {}

        def planen(con, pid, frei, modell, **_k):
            unterwegs["frei"], unterwegs["modell"] = sorted(frei), modell
            unterwegs["stand"] = planer_fortschritt.laufende(con, pid)
            return {"ergebnis": "Hier:\n```json\n" + json.dumps(plan(self.t1, self.t2)) + "\n```", "usd": 1.25, "fehler": None}
        with mock.patch.object(grobplan, "planen", side_effect=planen):
            grobplan.ausfuehren(self.con, self.pid, 1)
        self.assertEqual((unterwegs["frei"], unterwegs["modell"]), ([self.t1, self.t2], "opus"))
        self.assertIn("2 Themen werden geplant", unterwegs["stand"][0]["was"])
        l = self.con.execute("SELECT id, status, rc, beschreibung FROM lauf ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual((l["status"], l["rc"]), ("fertig", 0))
        self.assertIn("Grob-Planer Fassung 1 (opus, 2 Themen, A2030", l["beschreibung"])
        e = grobplan.entwurf(self.con, self.pid)
        assert e is not None
        self.assertEqual((e["fassung"], e["usd"], e["lauf"], len(e["entwurf"]["meilensteine"])), (1, 1.25, l["id"], 2))
        self.assertIsNone(grobplan.laeuft(self.con, self.pid))
        s = planer_fortschritt.stand(self.con, self.pid, l["id"])
        assert s is not None
        self.assertEqual((s["zustand"], s["art"]), ("fertig", "grobplaner"))
        self.assertTrue(any("Grobplan Fassung 1: 2 Meilensteine, 1 Befunde, 1 Fragen" in k for _, k, _ in self.post("TL")))
        f = self.con.execute("SELECT von, an, kurz, empfehlung FROM frage WHERE projekt_id = ?", (self.pid,)).fetchall()
        self.assertEqual(len(f), 1)
        self.assertEqual((f[0]["von"], f[0]["empfehlung"]), ("AMW", "A"))
        self.assertIn("Anmelden auch mit Passwort?", f[0]["kurz"])

    def test_fehler_und_neue_fassungen_bleiben_sichtbar(self):
        with mock.patch.object(grobplan, "planen", return_value={"ergebnis": "{}", "usd": 0.5, "fehler": None}):
            grobplan.ausfuehren(self.con, self.pid, 1)
        e = grobplan.entwurf(self.con, self.pid)
        assert e is not None
        self.assertIn("meilensteine fehlt (mindestens einer)", e["fehler"])
        self.assertIn("passt nicht", self.post("TL")[-1][1])
        with self.assertRaisesRegex(kern.AmwFehler, "passte nicht zum Schema"):
            grobplan.annehmen(self.con, self.pid, kern.ENTWICKLER)
        rc, aus = self.befehl("grobplan", "--neu")
        self.assertIn("Grobplan Fassung 2: Planer (opus) angestoßen", aus)
        rc, aus = self.befehl("grobplan", "--neu", von="CC1")
        self.assertNotEqual(rc, 0)
        with mock.patch.object(grobplan, "planen", side_effect=RuntimeError("weg")):
            grobplan.ausfuehren(self.con, self.pid, 2)
        self.assertEqual([(f["fassung"], bool(f["fehler"])) for f in grobplan.fassungen(self.con, self.pid)], [(1, True), (2, True)])
        self.assertIn("RuntimeError: weg", ((grobplan.entwurf(self.con, self.pid, 2) or {}).get("fehler") or [""])[0])
        self.assertEqual((grobplan.entwurf(self.con, self.pid, 1) or {}).get("fassung"), 1)
        rc, aus = self.befehl("grobplan", "--fassung", "1")
        self.assertIn("Fassung 1: Fehler", aus)
        self.assertIn("Fassung 2: Fehler", aus)
        self.assertIn("meilensteine fehlt", aus)


class Annehmen(Grund):
    def setUp(self):
        super().setUp()
        self.frei()
        grobplan.abschliessen(self.con, self.pid, kern.ENTWICKLER)              # A2062 (a): vor jedem Meilenstein – Bestand sperrt
        self.alt = planung.bogen_neu(self.con, self.pid, "TL", "Bestand")        # danach angelegt: neue Nummern zählen weiter
        grobplan.entwurf_eintragen(self.con, self.pid, 1, json.dumps(plan(self.t1, self.t2)), modell="opus", usd=1.0, lauf=None)

    def test_ja_legt_meilensteine_an_und_gibt_sie_grob_frei(self):
        self.assertNotEqual(tore.stand(self.con, self.pid)["aktuell"], "feinplanung")
        rc, aus = self.befehl("grobplan-ja", von=kern.ENTWICKLER)
        self.assertEqual(rc, 0)
        self.assertIn("Grobplan angenommen – Meilensteine angelegt und grob freigegeben: M1 → M2, M2 → M3", aus)
        b = {r["nr"]: r for r in self.con.execute("SELECT * FROM bogen WHERE projekt_id = ?", (self.pid,))}
        self.assertEqual(b[2]["titel"], "Anmelden")
        self.assertEqual(b[2]["ziel"], f"Anmeldung mit Firmen-Konto · Themen: TH{self.t1}")     # Verweis ergänzt
        self.assertEqual(b[3]["ziel"], f"TH{self.t2} Sicherung läuft jede Nacht")               # Verweis stand schon da
        self.assertEqual(b[2]["abnahme"], "Anmelden am Handy vorgeführt (endet mit Vorführung)")
        st = tore.stand(self.con, self.pid)
        g = next(x for x in st["tore"] if x["tor"] == "grobplanung")
        self.assertEqual((g["n"], g["g"], g["mn"], g["mg"]), (2, 2, 2, 3))      # Themen über das Ziel; „Bestand“ ohne Freigabe
        ja = grobplan.angenommen(self.con, self.pid)
        assert ja is not None
        self.assertEqual(ja["angelegt"], {"M1": "M2", "M2": "M3"})
        self.assertEqual(ja["nach"], {"M2": [], "M3": ["M2"]})
        with self.assertRaisesRegex(kern.AmwFehler, "schon angenommen"):
            grobplan.annehmen(self.con, self.pid, kern.ENTWICKLER)
        with self.assertRaisesRegex(kern.AmwFehler, "schon angenommen"):
            grobplan.abschliessen(self.con, self.pid, kern.ENTWICKLER)
        self.assertEqual(projektweg.sicht(self.con, self.pid)["schritte"][0]["zustand"], "erledigt")

    def test_grob_tor_zu_ohne_bestand(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'verworfen' WHERE id = ?", (self.alt,))
        grobplan.annehmen(self.con, self.pid, kern.ENTWICKLER)
        self.assertTrue(next(x for x in tore.stand(self.con, self.pid)["tore"] if x["tor"] == "grobplanung")["zu"])
        self.assertEqual(projektweg.sicht(self.con, self.pid)["dran"], "fein")

    def test_pakete_der_feinplanung_aendern_die_grob_freigabe_nicht(self):
        """CCamw2 #31619: Kommen später Pakete mit Themen in einen Meilenstein aus dem Grobplan, bleibt seine Grob-Freigabe
        gültig, und sein Plan lässt sich freigeben. Ein Meilenstein von früher (nicht aus dem Grobplan) rechnet wie bisher."""
        from amw import planansicht
        grobplan.annehmen(self.con, self.pid, kern.ENTWICKLER)
        m2 = self.con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND nr = 2", (self.pid,)).fetchone()[0]
        for bid in (m2, self.alt):
            aid = planung.schritt_setzen(self.con, self.pid, "TL", titel="Login-Maske", auftrag="bauen", bogen_id=bid)
            themen.verweise_setzen(self.con, self.pid, "TL", aid, [f"TH{self.t1}"])
        z = planansicht._zustaende(self.con, self.pid)
        self.assertTrue(z[(m2, "grob")]["an"])
        self.assertFalse(z[(m2, "grob")]["geaendert"])
        self.assertTrue(grobplan.aus_grobplan(self.con, self.pid, 2))
        self.assertFalse(grobplan.aus_grobplan(self.con, self.pid, 1))
        self.assertEqual(planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, m2, "plan"), {"frei": True})
        fp_alt = planansicht.fingerabdruck(self.con, self.pid, self.alt, "grob")
        aid = planung.schritt_setzen(self.con, self.pid, "TL", titel="Noch eins", auftrag="bauen", bogen_id=self.alt)
        themen.verweise_setzen(self.con, self.pid, "TL", aid, [f"TH{self.t2}"])
        self.assertNotEqual(planansicht.fingerabdruck(self.con, self.pid, self.alt, "grob"), fp_alt)   # alter Weg unverändert

    def test_nicht_wenn_sich_das_konzept_geaendert_hat(self):
        themen.bearbeiten(self.con, self.pid, kern.ENTWICKLER, self.t2, "Jede Stunde eine Sicherung.")
        with self.assertRaisesRegex(kern.AmwFehler, "haben sich die freigegebenen Themen geändert"):
            grobplan.annehmen(self.con, self.pid, kern.ENTWICKLER)
        self.assertEqual(self.con.execute("SELECT count(*) FROM bogen WHERE projekt_id = ?", (self.pid,)).fetchone()[0], 1)

    def test_co_und_lead_und_verlauf(self):
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, grobplan_freigabe="co+lead")
        self.assertEqual(grobplan.annehmen(self.con, self.pid, "TL"), {"angenommen": False, "ja_fehlt": ["Co-Entwickler"]})
        r = grobplan.annehmen(self.con, self.pid, "Co")
        self.assertTrue(r["angenommen"])
        frei = self.con.execute("SELECT von, text FROM plan_ereignis WHERE art = 'meilenstein_frei'").fetchall()
        self.assertEqual(len(frei), 2)
        self.assertEqual({f["von"] for f in frei}, {"AMW"})
        self.assertEqual(json.loads(frei[0]["text"])["durch"], ["Co", "TL"])
        weg = [(e["rolle"], e["text"]) for e in verlauf.projektweg(self.con, self.pid)]
        self.assertIn(("mensch", "Konzept abgeschlossen (2 Themen)"), weg)
        self.assertIn(("amw", "Grobplan Fassung 1: Planer angestoßen"), weg)
        self.assertIn(("planer", "Grobplan Fassung 1: Entwurf mit 2 Meilensteinen liegt vor"), weg)
        self.assertIn(("agent", "Grobplan: Ja (Lead)"), weg)
        self.assertIn(("amw", "Grobplan Fassung 1 angenommen – M2, M3"), weg)

    def test_zeigen(self):
        rc, aus = self.befehl("grobplan")
        self.assertEqual(rc, 0)
        self.assertIn("Fassung 1: 2 Meilensteine, 1 Befunde, 1 Fragen · opus · 1.00 $", aus)
        self.assertIn("M1 Anmelden · M · 4 Tage", aus)


if __name__ == "__main__":
    unittest.main()
