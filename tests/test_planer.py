"""K4 / A1940 (Vorbereitung, #30112): Grobplanung aus Themen – Schema des Planer-Ergebnisses, Prüfung mit allen Funden,
Entwurf eintragen (Auftrag an den Lead), Übernehmen erst mit Ja: Meilensteine, Pakete mit Größe/Art/Ausführung/Modell,
Abnahme-Befehl, Abhängigkeiten, Verweis aufs Thema; „nichts zu bauen“ mit Grund. Feste Planer-Ergebnisse, kein echter Lauf."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import copy
import json
import os
import shutil
import tempfile
import unittest
from unittest import mock

from amw import arbeitspaket, db, kern, planer, planung, themen
from tests.test_arbeiter import ATTRAPPE

ERGEBNIS = {
    "meilensteine": [{"schluessel": "M1", "titel": "Anmelden online", "endet_mit": "vorfuehrung"}],
    "pakete": [
        {"schluessel": "P1", "meilenstein": "M1", "titel": "Anmeldung mit Firmen-Konto", "auftrag": "SSO-Anmeldung bauen.",
         "groesse": "m", "art": "sicherheit", "ausfuehrung": "agent", "fertig_quelle": "release"},
        {"schluessel": "P2", "meilenstein": "M1", "titel": "Tests für die Anmeldung", "auftrag": "Tests ergänzen.",
         "groesse": "S", "art": "mechanisch", "ausfuehrung": "p", "modell": "sonnet", "effort": "medium", "fertig_quelle": "commit",
         "nach": ["P1"], "abnahme_befehl": "python -m unittest tests.test_anmeldung"},
    ]}


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
            self.pid = db.einfuegen(self.con, "projekt", name="Produkt", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        self.tid = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", self.tid, "Wer die Online-Seite öffnet, meldet sich mit dem Firmen-Konto an.")

    def post(self, an):
        return [(r["art"], r["kurz"]) for r in self.con.execute(
            "SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.von = 'AMW'"
            " ORDER BY n.id", (an,))]

    def funde(self, daten):
        with self.assertRaises(planer.PlanFehler) as f:
            planer.pruefen(daten, self.con, self.pid)
        return f.exception.fehler


class Schema(Grund):
    def test_gueltig_und_vereinheitlicht(self):
        e = planer.pruefen(json.dumps(ERGEBNIS), self.con, self.pid)                     # auch als JSON-Text
        self.assertFalse(e["nichts_zu_bauen"])
        self.assertEqual([p["groesse"] for p in e["pakete"]], ["M", "S"])                 # Größe groß geschrieben
        self.assertEqual(e["pakete"][0]["modell"], None)
        self.assertEqual(e["pakete"][1]["nach"], ["P1"])

    def test_alle_funde_auf_einmal(self):
        d = copy.deepcopy(ERGEBNIS)
        d["pakete"][0].update(groesse="riesig", art="malen", fertig_quelle="irgendwann", meilenstein="M9")
        d["pakete"][1].update(ausfuehrung="p", abnahme_befehl=None, nach=["P1", "P7"])
        d["extra"] = 1
        f = self.funde(d)
        for teil in ("unbekannte Felder: extra", "groesse „riesig“", "art „malen“", "fertig_quelle „irgendwann“",
                     "Meilenstein „M9“", "p-Paket braucht einen Abnahme-Befehl", "nach „P7“"):
            self.assertTrue(any(teil in x for x in f), (teil, f))

    def test_meilenstein_ohne_pakete(self):
        d = copy.deepcopy(ERGEBNIS)
        d["meilensteine"].append({"schluessel": "M2", "titel": "Leer", "endet_mit": "bericht"})
        self.assertIn("neue Meilensteine ohne Pakete: M2", self.funde(d))
        d["meilensteine"][1].update(ziel="Freitext", endet_mit="feier")                     # TH164: kein Freitext, Vorführung|Bericht
        f = self.funde(d)
        self.assertTrue(any("ziel/abnahme nicht als Text" in x for x in f) and any("endet_mit „feier“" in x for x in f), f)

    def test_kreis_und_selbst(self):
        d = copy.deepcopy(ERGEBNIS)
        d["pakete"][0]["nach"] = ["P2"]
        self.assertTrue(any("im Kreis: P1 → P2 → P1" in x or "im Kreis: P2 → P1 → P2" in x for x in self.funde(d)))
        d["pakete"][0]["nach"] = ["P1"]
        self.assertTrue(any("hängt von sich selbst ab" in x for x in self.funde(d)))

    def test_verweise_ins_projekt(self):
        d = copy.deepcopy(ERGEBNIS)
        d["pakete"][0]["nach"] = ["A999"]
        d["meilensteine"].append({"schluessel": "M2", "bestehend": 7})
        f = self.funde(d)
        self.assertTrue(any("nach A999 – die Aufgabe gibt es im Projekt nicht" in x for x in f))
        self.assertTrue(any("Meilenstein 7 gibt es im Projekt nicht" in x for x in f))

    def test_a1976_schon_gebaut_oberflaeche_und_nur_offene_meilensteine(self):
        """Ein Vorschlag, der einem fertigen Paket desselben Themas gleicht → „schon gebaut: A…“; Oberfläche nie als p;
        „bestehend“ nur ein offener Meilenstein. Ähnliche Pakete anderer Themen oder offene stören nicht."""
        gebaut = kern.aufgabe_neu(self.con, self.pid, "TL", "Release-Modus je Projekt einstellbar (gesammelt/sofort)", "CC1")
        offen = kern.aufgabe_neu(self.con, self.pid, "TL", "Anmeldung mit dem Firmen-Konto", "CC1")
        anderes = themen.neu(self.con, self.pid, "TL", "Betrieb", pfleger="CC1")
        fremd = kern.aufgabe_neu(self.con, self.pid, "TL", "Tests für die Anmeldung", "CC1")
        themen.verweise_setzen(self.con, self.pid, "TL", gebaut, [f"TH{self.tid}"])
        themen.verweise_setzen(self.con, self.pid, "TL", offen, [f"TH{self.tid}"])
        themen.verweise_setzen(self.con, self.pid, "TL", fremd, [f"TH{anderes}"])
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234' WHERE id IN (?, ?)", (gebaut, fremd))
        fertig = planung.bogen_neu(self.con, self.pid, "TL", "Alt")
        planung.bogen_status(self.con, self.pid, "TL", fertig, "fertig")
        d = copy.deepcopy(ERGEBNIS)
        d["pakete"].append({**ERGEBNIS["pakete"][0], "schluessel": "P3", "titel": "Release-Modus je Projekt"})
        d["pakete"].append({**ERGEBNIS["pakete"][1], "schluessel": "P4", "titel": "Knopf auf der Seite", "art": "oberflaeche", "nach": []})
        d["meilensteine"].append({"schluessel": "M2", "bestehend": planung.bogen_zeile(self.con, self.pid, fertig)["nr"]})
        self.assertEqual(planer.pruefen(copy.deepcopy(ERGEBNIS), self.con, self.pid, self.tid)["pakete"][0]["titel"],
                         "Anmeldung mit Firmen-Konto")                    # offen verknüpft / fertig in anderem Thema: kein Fund
        with self.assertRaises(planer.PlanFehler) as f:
            planer.pruefen(d, self.con, self.pid, self.tid)
        funde = f.exception.fehler
        self.assertIn(f"Paket P3: schon gebaut: A{gebaut} „Release-Modus je Projekt einstellbar (gesammelt/sofort)“", funde)
        self.assertEqual([x for x in funde if "schon gebaut" in x and "P3" not in x], [])
        self.assertTrue(any("Paket P4: ein Oberflächen-Paket nie als p" in x for x in funde), funde)
        self.assertTrue(any("ist fertig – „bestehend“ nur ein offener Meilenstein" in x for x in funde), funde)
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, d)                             # auch beim Eintragen geprüft
        self.assertTrue(any("schon gebaut" in x for x in planer.letzter_entwurf(self.con, self.pid, self.tid)["fehler"]))

    def test_a1976_aehnlich(self):
        for a, b in (("Release-Modus je Projekt", "Release-Modus je Projekt einstellbar"),
                     ("Disponent über Projekte", "Disponent über alle Projekte hinweg"),
                     ("Anmeldung mit Firmen-Konto", "Anmeldung mit Firmenkonto")):
            self.assertTrue(planer.aehnlich(a, b), (a, b))
        for a, b in (("Login-Maske", "Release-Modus je Projekt"), ("Tests für die Anmeldung", "Anmeldung mit Firmen-Konto"),
                     ("Seite", "Seite drucken und teilen"), ("", "x")):
            self.assertFalse(planer.aehnlich(a, b), (a, b))

    def test_nichts_zu_bauen(self):
        self.assertEqual(planer.pruefen({"nichts_zu_bauen": True, "grund": "Nur ein Begriff, schon erfüllt."}),
                         {"nichts_zu_bauen": True, "grund": "Nur ein Begriff, schon erfüllt."})
        self.assertTrue(any("grund fehlt" in x for x in self.funde({"nichts_zu_bauen": True})))
        self.assertTrue(any("aber Meilensteine oder Pakete" in x for x in self.funde({"nichts_zu_bauen": True, "grund": "x",
                                                                                      "pakete": ERGEBNIS["pakete"]})))

    def test_kein_json(self):
        self.assertTrue(self.funde("{kaputt")[0].startswith("kein JSON"))


class Ablauf(Grund):
    def setUp(self):
        super().setUp()
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)       # P462 (4): Ja nur zum freigegebenen Thema

    def test_entwurf_an_den_lead_und_erst_mit_ja_angelegt(self):
        vorher = self.con.execute("SELECT count(*) FROM aufgabe").fetchone()[0]
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, ERGEBNIS, modell="sonnet", usd=0.42, lauf=7)
        self.assertEqual(self.post("TL")[-1], ("auftrag", "Planentwurf TH%d „Anmeldung“: 1 Meilenstein(e), 2 Pakete – Ja oder ändern" % self.tid))
        self.assertEqual(self.con.execute("SELECT count(*) FROM aufgabe").fetchone()[0], vorher)   # kein Anlegen ohne Ja
        with self.assertRaisesRegex(kern.AmwFehler, "nimmt der Lead an"):
            planer.uebernehmen(self.con, self.pid, "CC1", self.tid)
        a = planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        self.assertEqual(sorted(a), ["M1", "P1", "P2"])
        b = planung.bogen_zeile(self.con, self.pid, self.con.execute("SELECT id FROM bogen WHERE nr = ?", (int(a["M1"][1:]),)).fetchone()[0])
        self.assertEqual((b["titel"], b["ziel"], b["abnahme"]), ("Anmelden online", f"TH{self.tid} Anmeldung", "Vorführung"))   # Verweis
        p1, p2 = (self.con.execute("SELECT * FROM aufgabe WHERE id = ?", (int(a[k][1:]),)).fetchone() for k in ("P1", "P2"))
        self.assertEqual((p1["groesse"], p1["art"], p1["bogen_id"]), ("M", "sicherheit", b["id"]))
        self.assertEqual((p2["pruefbefehl"], arbeitspaket.lesen(self.con, p2["id"])["art"], arbeitspaket.lesen(self.con, p2["id"])["modell"]),
                         ("python -m unittest tests.test_anmeldung", "p", "sonnet"))
        self.assertEqual(planung.vorgaenger(self.con, p2["id"]), [p1["id"]])
        self.assertEqual(themen.verweise(self.con, self.pid, p1["id"]), [self.tid])            # mit dem Thema verknüpft (A1915)
        with self.assertRaisesRegex(kern.AmwFehler, "schon angenommen"):
            planer.uebernehmen(self.con, self.pid, "TL", self.tid)

    def test_lead_aendert_vor_dem_ja(self):
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, ERGEBNIS)
        d = copy.deepcopy(ERGEBNIS)
        d["pakete"] = d["pakete"][:1]
        a = planer.uebernehmen(self.con, self.pid, "TL", self.tid, geaendert=d)
        self.assertEqual(sorted(a), ["M1", "P1"])
        d["pakete"][0]["art"] = "malen"
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, ERGEBNIS)
        with self.assertRaises(planer.PlanFehler):                                        # Änderung wird neu geprüft
            planer.uebernehmen(self.con, self.pid, "TL", self.tid, geaendert=d)

    def test_fehlerhafter_entwurf_meldet_funde_und_legt_nichts_an(self):
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, {"pakete": []})
        self.assertEqual(self.post("TL")[-1][0], "meldung")
        self.assertIn("passt nicht zum Schema", self.post("TL")[-1][1])
        with self.assertRaisesRegex(kern.AmwFehler, "passte nicht zum Schema"):
            planer.uebernehmen(self.con, self.pid, "TL", self.tid)

    def test_nichts_zu_bauen_mit_grund_vermerkt(self):
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, {"nichts_zu_bauen": True, "grund": "Ist schon gebaut (A1896)."})
        self.assertIn("nichts zu bauen – stimmt das?", self.post("TL")[-1][1])
        self.assertEqual(planer.uebernehmen(self.con, self.pid, "TL", self.tid), {})
        e = planer._ereignisse(self.con, self.pid, self.tid, planer.NICHTS)
        self.assertEqual(e[-1]["grund"], "Ist schon gebaut (A1896).")

    def test_bestehender_meilenstein_und_vorgaenger_im_projekt(self):
        bid = planung.bogen_neu(self.con, self.pid, "TL", "Schon da")
        nr = planung.bogen_zeile(self.con, self.pid, bid)["nr"]
        alt = kern.aufgabe_neu(self.con, self.pid, "TL", "Vorarbeit")
        d = {"meilensteine": [{"schluessel": "M1", "bestehend": nr}],
             "pakete": [{**ERGEBNIS["pakete"][0], "nach": [f"A{alt}"]}]}
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, d)
        a = planer.uebernehmen(self.con, self.pid, "TL", self.tid)
        self.assertEqual(a["M1"], f"M{nr}")
        aid = int(a["P1"][1:])
        self.assertEqual(self.con.execute("SELECT bogen_id FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0], bid)
        self.assertEqual(planung.vorgaenger(self.con, aid), [alt])


class Anstossen(Grund):
    """#30117: Auslöser Freigabe (auch eigene Bearbeitung) und `amw thema planen` (Lead/Co); je Fassung einmal; nicht bei
    „nichts zu bauen“ oder Einstellung aus; der Starter ist in Tests eine Attrappe."""

    def setUp(self):
        super().setUp()
        self.gestartet = []
        p = mock.patch.object(planer, "STARTER", lambda pid, tid, fassung: self.gestartet.append((tid, fassung)) or 4711)
        p.start()
        self.addCleanup(p.stop)
        u = mock.patch.dict(os.environ)
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_PLANER_AUS", None)

    def test_freigabe_stoesst_an_einmal_je_fassung(self):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertEqual(self.gestartet, [(self.tid, 1)])
        self.assertEqual(planer.laeuft(self.con, self.pid, self.tid)["prozess"], 4711)
        self.assertIsNone(planer.anstossen(self.con, self.pid, self.tid, 1))                    # läuft schon / gab es schon
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, ERGEBNIS)
        self.assertIsNone(planer.laeuft(self.con, self.pid, self.tid))
        self.assertIsNone(planer.anstossen(self.con, self.pid, self.tid, 1))                    # diese Fassung ist geplant
        themen.bearbeiten(self.con, self.pid, kern.ENTWICKLER, self.tid, "Neu: auch mit Passkey.", erwartet=1)
        self.assertEqual(self.gestartet, [(self.tid, 1), (self.tid, 2)])                         # eigene Bearbeitung = Freigabe

    def test_nicht_bei_aus_oder_nichts_zu_bauen_und_befehl_erneut(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", themen_planer="aus")
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        self.assertEqual(self.gestartet, [])
        kern.projekt_einstellen(self.con, self.pid, "TL", themen_planer="sonnet")
        with db.schreiben(self.con):
            planer._ereignis(self.con, self.pid, "TL", planer.NICHTS, self.tid, grund="schon gebaut")
        self.assertIsNone(planer.anstossen(self.con, self.pid, self.tid, 1))
        self.assertIn("angestoßen", planer.anstossen(self.con, self.pid, self.tid, 1, von="TL", erneut=True))   # auf Befehl doch
        self.assertIn("plant schon", planer.anstossen(self.con, self.pid, self.tid, 1, von="TL", erneut=True))

    def test_starter_geht_nicht_meldet_dem_lead(self):
        with mock.patch.object(planer, "STARTER", side_effect=OSError("kein Python")):
            self.assertIn("ließ sich nicht starten", planer.anstossen(self.con, self.pid, self.tid, 1))
        self.assertEqual(self.post("TL")[-1], ("meldung", f"Planentwurf TH{self.tid} „Anmeldung“ ging nicht"))
        self.assertIsNone(planer.laeuft(self.con, self.pid, self.tid))

    def test_befehle(self):
        from amw import cli
        import contextlib
        import io

        def befehl(*args, von="TL"):
            aus = io.StringIO()
            with contextlib.redirect_stdout(aus):
                rc = cli.main(["thema", *args, "--projekt", "Produkt", "--von", von])
            return rc, aus.getvalue()

        self.assertNotEqual(befehl("planen", f"TH{self.tid}", von="CC1")[0], 0)                  # nur Lead/Mensch/Co
        rc, aus = befehl("planen", f"TH{self.tid}")
        self.assertIn("Planer (sonnet) angestoßen", aus)
        self.assertIn("noch kein Planentwurf – der Planer läuft", befehl("plan", f"TH{self.tid}")[1])
        planer.entwurf_eintragen(self.con, self.pid, self.tid, 1, ERGEBNIS, modell="sonnet", usd=0.31)
        aus = befehl("plan", f"TH{self.tid}")[1]
        self.assertIn("Planentwurf (Fassung 1, sonnet, 0.31 $)", aus)
        self.assertIn("P2 Tests für die Anmeldung · S · mechanisch · p sonnet · fertig: commit · nach P1", aus)
        datei = os.path.join(self.ordner.name, "geaendert.json")
        with open(datei, "w", encoding="utf-8") as f:
            json.dump({**ERGEBNIS, "pakete": ERGEBNIS["pakete"][:1]}, f)
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)       # P462 (4)
        rc, aus = befehl("plan-ja", f"TH{self.tid}", "--datei", datei)
        self.assertEqual(rc, 0)
        self.assertIn("angelegt – M1 → M", aus)
        self.assertNotIn("P2", aus)


class Lauf(Grund):
    def test_als_lauf_der_schlange_mit_kosten_und_entwurf(self):
        with db.schreiben(self.con):
            planer._ereignis(self.con, self.pid, "AMW", planer.ANGESTOSSEN, self.tid, fassung=1, modell="sonnet")
        antwort = "Hier der Plan:\n```json\n" + json.dumps(ERGEBNIS) + "\n```"
        with mock.patch.object(planer, "planen", return_value={"ergebnis": planer.json_aus_text(antwort), "usd": 0.214, "fehler": None}):
            planer.ausfuehren(self.con, self.pid, self.tid, 1)
        l = self.con.execute("SELECT status, rc, beschreibung, ergebnis FROM lauf ORDER BY id DESC LIMIT 1").fetchone()
        self.assertEqual((l["status"], l["rc"]), ("fertig", 0))
        self.assertEqual(l["beschreibung"], f"Planer TH{self.tid} Fassung 1 (sonnet, A1940, automatisch)")
        self.assertIn("0.21 $", l["ergebnis"])
        e = planer.letzter_entwurf(self.con, self.pid, self.tid)
        self.assertEqual((e["usd"], len(e["entwurf"]["pakete"])), (0.214, 2))
        self.assertIn("Ja oder ändern", self.post("TL")[-1][1])
        with mock.patch.object(planer, "planen", side_effect=RuntimeError("weg")):
            planer.ausfuehren(self.con, self.pid, self.tid, 1)
        self.assertEqual(self.con.execute("SELECT rc FROM lauf ORDER BY id DESC LIMIT 1").fetchone()[0], 1)
        self.assertIn("Planer-Lauf: RuntimeError: weg", planer.letzter_entwurf(self.con, self.pid, self.tid)["fehler"][0])

    def test_dateien_fuer_den_planer(self):
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        bid = planung.bogen_neu(self.con, self.pid, "TL", "Online", ziel="Online-Seite steht")
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Login-Maske", "CC1")
        themen.verweise_setzen(self.con, self.pid, "TL", aid, [f"TH{self.tid}"])
        ordner = os.path.join(self.ordner.name, "planer")
        os.makedirs(ordner)
        namen = planer._dateien(self.con, self.pid, themen.finden(self.con, self.pid, self.tid), 1, ordner)
        self.assertEqual(namen, ["beschluesse.md", "meilensteine.md", "pakete.md", "schema.md", "thema.md"])
        lies = lambda n: open(os.path.join(ordner, n), encoding="utf-8").read()
        self.assertIn("Firmen-Konto", lies("thema.md"))
        self.assertIn(f"- {planung.bogen_zeile(self.con, self.pid, bid)['nr']}: Online", lies("meilensteine.md"))
        self.assertIn(f"- A{aid} [", lies("pakete.md"))
        zu, weitere = lies("pakete.md").split("# Weitere offene Pakete")
        self.assertIn("Login-Maske", zu)                                                         # schon mit dem Thema verknüpft
        self.assertNotIn("Login-Maske", weitere)
        self.assertIn('"nichts_zu_bauen": true', lies("schema.md"))

    def test_a1976_fertiges_und_passende_meilensteine_als_kontext(self):
        """Der Planer sieht die Pakete des Themas MIT Status (auch fertige) und nur offene Meilensteine – ★ am Meilenstein,
        dessen Ziel auf das Thema verweist; der Auftrag sagt: Fertiges nie neu, passenden Meilenstein nutzen, Oberfläche als agent."""
        themen.freigeben(self.con, self.pid, kern.ENTWICKLER, self.tid)
        passt = planung.bogen_neu(self.con, self.pid, "TL", "Übernahme", ziel=f"TH{self.tid} Anmeldung")
        anderer = planung.bogen_neu(self.con, self.pid, "TL", "Bestand", ziel="TH99 Sonstiges")
        alt = planung.bogen_neu(self.con, self.pid, "TL", "Längst fertig")
        planung.bogen_status(self.con, self.pid, "TL", alt, "fertig")
        gebaut = kern.aufgabe_neu(self.con, self.pid, "TL", "Release-Modus je Projekt", "CC1")
        themen.verweise_setzen(self.con, self.pid, "TL", gebaut, [f"TH{self.tid}"])
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234' WHERE id = ?", (gebaut,))
        fremd = kern.aufgabe_neu(self.con, self.pid, "TL", "Etwas anderes", "CC1")
        ordner = os.path.join(self.ordner.name, "planer")
        os.makedirs(ordner)
        planer._dateien(self.con, self.pid, themen.finden(self.con, self.pid, self.tid), 1, ordner)
        lies = lambda n: open(os.path.join(ordner, n), encoding="utf-8").read()
        nr = lambda b: planung.bogen_zeile(self.con, self.pid, b)["nr"]
        ms = lies("meilensteine.md")
        self.assertIn(f"- {nr(passt)}: Übernahme [geplant] – Ziel: TH{self.tid} Anmeldung ★", ms)
        self.assertIn(f"- {nr(anderer)}: Bestand [geplant] – Ziel: TH99 Sonstiges\n", ms + "\n")         # ohne ★
        self.assertNotIn("Längst fertig", ms)                                                    # nur offene Meilensteine
        zu, weitere = lies("pakete.md").split("# Weitere offene Pakete")
        self.assertIn(f"- A{gebaut} [fertig] Release-Modus je Projekt", zu)
        self.assertIn(f"- A{fremd} [", weitere)
        for satz in ("nie neu vor", "(★)", "bestehend", "Oberflächen-Pakete (art oberflaeche) laufen immer mit ausfuehrung agent",
                     "Kleinprobe"):
            self.assertIn(satz, planer.AUFTRAG)

    def test_json_aus_text(self):
        self.assertEqual(json.loads(planer.json_aus_text("```json\n{\"a\": 1}\n```")), {"a": 1})
        self.assertEqual(planer.json_aus_text("kein JSON"), "kein JSON")


@unittest.skipUnless(os.name == "nt" and shutil.which("git"), "Arbeiter nur unter Windows (Job-Objekt)")
class MitAttrappe(Grund):
    """Der Planer mit der Arbeiter-Attrappe: nur Lesen, Sonnet medium, Antwort als JSON; hängt er, beendet ihn die Frist."""

    def planen(self, art, **env):
        datei = os.path.join(self.ordner.name, "aufruf.json")
        aus = planer.planen(self.con, self.pid, themen.finden(self.con, self.pid, self.tid), 1, "sonnet", prog=ATTRAPPE,
                            zusatz={"ATTRAPPE_ART": art, "ATTRAPPE_UMGEBUNG": datei, **env})
        return aus, datei

    def test_liest_und_antwortet_mit_json(self):
        aus, datei = self.planen("gegenlesen", ATTRAPPE_ERGEBNIS="```json\n" + json.dumps(ERGEBNIS) + "\n```")
        self.assertIsNone(aus["fehler"])
        self.assertEqual(planer.pruefen(aus["ergebnis"])["pakete"][1]["schluessel"], "P2")
        with open(datei, encoding="utf-8") as f:
            a = json.load(f)["argv"]
        self.assertEqual((a[a.index("--tools") + 1], a[a.index("--model") + 1], a[a.index("--effort") + 1]), ("Glob,Grep,Read", "sonnet", "medium"))

    def test_frist_beendet_einen_haengenden_planer(self):
        with mock.patch.object(planer, "FRIST_S", 3):
            aus, _ = self.planen("haengt")
        self.assertIsNone(aus["ergebnis"])
        self.assertIn("Frist", aus["fehler"])


if __name__ == "__main__":
    unittest.main()
