"""A2033 (TH164 F2, Kleinprobe D1516 v3): die Seite „Projektweg“ – fünf Schritte als Leiste, Ansicht je Schritt, Verlauf,
Seitenfenster mit Hinweis an den Planer (Esc schließt), Fortschritt eines laufenden Planers als Überlagerung. Die Daten kommen
aus projektweg_seite.daten (nichts im Browser gespeichert), die Handlungen über /api/projektweg/… bzw. die vorhandenen Wege.
Rundgang PC/Handy hell/dunkel (Bilder für die Prüfbitte über AMW_RUNDGANG_BILDER)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import aktionen, arbeitspaket, db, grobplan, kern, planer, planer_fortschritt, planung, projektweg_seite, themen
from tests.rundgang import Rundgang

THEMEN = (("Aquarium-Ansicht der Welt", "Die Welt liegt wie ein Aquarium vor dir; Kamera frei drehbar."),
          ("Bewohner mit lokaler KI", "Jeder Bewohner denkt mit einem kleinen Modell auf deinem Rechner."),
          ("Speichern und Laden", "Die Welt bleibt erhalten, auch nach einem Neustart."),
          ("Spieler greift ein", "Du stellst Dinge ins Aquarium oder nimmst sie heraus."))


def grobplan_entwurf(t, zweite=False):
    """Ein gültiges Planer-Ergebnis über die vier Themen; Fassung 2 zieht M3 vor (gleichzeitig mit M2)."""
    th = [f"TH{x}" for x in t]
    return {"befunde": [{"art": "zu_gross", "themen": [th[1]], "text": "Grundverhalten und Gedächtnis sind zwei Stücke.",
                         "vorschlag": "Grundverhalten in M2, Gedächtnis später"},
                        {"art": "abdeckung", "themen": th, "text": "4 von 4 Themen in mindestens einem Meilenstein.", "vorschlag": None}],
            "fragen": [] if zweite else [{"frage": "Wie viele Bewohner sollen flüssig laufen?", "optionen": {"A": "10", "B": "20"},
                                          "empfehlung": "A", "grund": "reicht und läuft auf einem normalen PC", "themen": [th[1]]}],
            "meilensteine": [
                {"schluessel": "M1", "titel": "Welt sichtbar", "ziel": f"{th[0]} startet und {th[2]} speichert", "themen": [th[0], th[2]],
                 "fertig_wenn": "das Aquarium startet, sieht nach Stil aus und speichert", "endet_mit": "vorfuehrung", "nach": [],
                 "gleichzeitig": [], "aufwand": "M", "tage": 1, "usd": 28},
                {"schluessel": "M2", "titel": "Ein Bewohner lebt", "ziel": f"{th[1]} über einen Tag", "themen": [th[1]],
                 "fertig_wenn": "ein Bewohner erfüllt seine Bedürfnisse über einen Tag", "endet_mit": "vorfuehrung", "nach": ["M1"],
                 "gleichzeitig": [], "aufwand": "L", "tage": 3, "usd": 70},
                {"schluessel": "M3", "titel": "Spieler greift ein", "ziel": f"{th[3]}", "themen": [th[3]],
                 "fertig_wenn": "du stellst etwas ins Aquarium und die Bewohner reagieren", "endet_mit": "vorfuehrung",
                 "nach": ["M1"] if zweite else ["M2"], "gleichzeitig": ["M2"] if zweite else [], "aufwand": "M", "tage": 2, "usd": 40}],
            "grund": "erst die Welt, dann ein Bewohner" + ("; M3 gleichzeitig mit M2" if zweite else "")}


def demo(con, pid, bis="grob2"):
    """Beispielprojekt bis zu einem Stand: konzept (Themen frei) · grob1 · grob2 (mit Hinweis) · fein (Grobplan-Ja, Pakete in M1)."""
    t = []
    for name, text in THEMEN:
        tid = themen.neu(con, pid, "TL", name, pfleger="CC1")
        themen.pflegen(con, pid, "CC1", tid, text)
        themen.freigeben(con, pid, kern.ENTWICKLER, tid)
        t.append(tid)
    if bis == "konzept":
        return t
    grobplan.abschliessen(con, pid, kern.ENTWICKLER)
    grobplan.entwurf_eintragen(con, pid, 1, json.dumps(grobplan_entwurf(t)), modell="opus", usd=1.2)
    if bis == "grob1":
        return t
    from amw import planhinweis
    planhinweis.hinweis(con, pid, kern.ENTWICKLER, "grob", "M3 früher – ich will schnell selbst eingreifen können.", "M3")
    grobplan.anstossen(con, pid, von=kern.ENTWICKLER)
    grobplan.entwurf_eintragen(con, pid, 2, json.dumps(grobplan_entwurf(t, zweite=True)), modell="opus", usd=0.6)
    if bis == "grob2":
        return t
    grobplan.annehmen(con, pid, kern.ENTWICKLER, 2)
    m1 = con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND titel = 'Welt sichtbar'", (pid,)).fetchone()[0]
    ids = {}
    for key, titel, nach, p in (("p1", "Projekt anlegen, Godot-Gerüst", [], False), ("p2", "Aquarium-Szene mit Kamera", ["p1"], False),
                                ("p3", "Farben und Schrift nach Stil", ["p1"], True), ("p4", "Speichern und Laden", ["p1"], False),
                                ("p5", "Tests für Speichern", ["p4"], True)):
        aid = planung.schritt_setzen(con, pid, "TL", titel=titel, nach=[ids[x] for x in nach] or None, bogen_id=m1, groesse="S",
                                     art="mechanisch" if p else "oberflaeche", agent=None if p else "CC1")
        if p:
            arbeitspaket.setzen(con, pid, "TL", aid, art="p", modell="sonnet")
        ids[key] = aid
    if bis == "fein":
        return t
    from amw import feinplanung, planautomatik, abschluss
    feinplanung.plan_starten(con, pid, kern.ENTWICKLER, m1)
    for aid in ids.values():
        with db.schreiben(con):                                              # Umsetzung im Zeitraffer: alle Pakete fertig
            con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234', fertig_utc = ? WHERE id = ?", (db.jetzt(), aid))
    kern.projekt_einstellen(con, pid, "TL", plan_automatik="an")
    if bis == "abschluss-ohne":                                              # bereit wie vor A2029: ohne Prüf-Ergebnis
        kern.projekt_einstellen(con, pid, "TL", plan_automatik="an")
        with mock.patch.object(abschluss, "vor_bereit", return_value="melden"):
            planautomatik.meilenstein_projekt(con, pid)
        return t
    with db.schreiben(con):                                                  # Ergebnis des Prüfers, wie abschluss.eintragen es schreibt
        abschluss._ereignis(con, pid, abschluss.ERGEBNIS, bogen=m1, stand="x", test={"befehl": "godot --headless -s tests/alle.gd", "lauf": 7, "rc": 0},
                            themen=[{"thema": f"TH{t[0]}", "erfuellt": True, "beleg": "Aquarium-Szene mit Kamera"},
                                    {"thema": f"TH{t[2]}", "erfuellt": True, "beleg": "Speichern und Laden"}],
                            vorfuehrung=["Aquarium starten", "Welt speichern", "neu laden – alles ist noch da"], ok=True, angelegt={})
    with mock.patch.object(abschluss, "vor_bereit", return_value="melden"):  # Gesamttest und Prüfer: hier schon durch
        planautomatik.meilenstein_projekt(con, pid)
    return t


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
        for ziel, name in ((grobplan, "STARTER"), (planer, "STARTER")):
            p = mock.patch.object(ziel, name, lambda *a, **k: 4711)
            p.start()
            self.addCleanup(p.stop)

    def daten(self):
        return projektweg_seite.daten(self.con, self.pid)


class Daten(Grund):
    def test_grobplan_mit_fassungen_aenderungen_und_hinweis(self):
        demo(self.con, self.pid, "grob2")
        d = self.daten()
        self.assertEqual(d["dran"], "grob")
        self.assertEqual([s["schritt"] for s in d["schritte"]], ["konzept", "grob", "fein", "umsetzung", "abschluss"])
        self.assertTrue(d["schritte"][1]["bei_dir"])                         # der Mensch gibt den Grobplan frei
        g = d["grob"]
        self.assertEqual([f["fassung"] for f in g["fassungen"]], [1, 2])
        self.assertIsNone(g["fassungen"][0]["aenderung"])
        self.assertEqual(g["fassungen"][1]["aenderung"]["geaendert"], [{"titel": "Spieler greift ein", "felder": ["nach", "gleichzeitig"]}])
        self.assertEqual(len(g["fassungen"][0]["fragen"]), 1)
        self.assertEqual([h["bezug"] for h in g["hinweise"]], ["M3"])
        self.assertFalse(g["hinweise"][0]["offen"])                          # Fassung 2 kam danach
        self.assertEqual(d["konzept"]["n"], 4)
        self.assertTrue(any("Grobplan" in e["text"] or "Konzept" in e["text"] for e in d["verlauf"]))

    def test_feinplan_in_stufen_mit_wer(self):
        demo(self.con, self.pid, "fein")
        d = self.daten()
        self.assertEqual(d["dran"], "fein")
        m = d["fein"]["meilensteine"][0]
        self.assertEqual(m["titel"], "Welt sichtbar")
        self.assertFalse(m["frei"])
        st = {p["titel"]: (p["stufe"], p["wer"]) for p in m["pakete"]}
        self.assertEqual(st["Projekt anlegen, Godot-Gerüst"], (1, "Fenster · CC1"))
        self.assertEqual(st["Farben und Schrift nach Stil"], (2, "Headless · Sonnet"))   # TL #31722: Wörter, nicht „-p sonnet“
        self.assertEqual(st["Tests für Speichern"][0], 3)
        self.assertTrue(d["schritte"][2]["bei_dir"])
        self.assertEqual(d["grob"]["angenommen"]["fassung"], 2)

    def test_laufender_planer_und_frage_vom_lead(self):
        demo(self.con, self.pid, "fein")
        with db.schreiben(self.con):
            lid = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="AMW", beschreibung="Feinplaner", status="laeuft",
                               angemeldet_utc=db.jetzt(), start_utc=db.jetzt())
        planer_fortschritt.melden(self.con, self.pid, lid, art="feinplaner", modell="opus", was="Thema 1 von 2", nr=1, gesamt=2)
        aid = self.con.execute("SELECT id FROM aufgabe WHERE titel = 'Speichern und Laden'").fetchone()[0]
        kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Speichern als Textdatei oder binär?", [("A", "Textdatei"), ("B", "binär")],
                       empfehlung="A", grund="lesbar, bei 10 Bewohnern egal", aufgabe_id=aid, pruefen=False)
        d = self.daten()
        self.assertEqual([x["art"] for x in d["laeufe"]], ["feinplaner"])
        f = d["fragen"][0]
        self.assertEqual((f["paket"], f["vom_lead"]), ("Speichern und Laden", True))

    def test_handlungen_am_pc_und_nicht_online(self):
        t = demo(self.con, self.pid, "konzept")
        self.assertTrue(self.daten()["schritte"][0]["zustand"] == "erledigt" or self.daten()["konzept"]["zu"])
        r = aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/konzept-abschliessen", {})
        self.assertTrue(r["abgeschlossen"])
        grobplan.entwurf_eintragen(self.con, self.pid, 1, json.dumps(grobplan_entwurf(t)), modell="opus", usd=1.0)
        with self.assertRaisesRegex(aktionen.Ungueltig, "am PC"):
            aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/grob-freigeben", {"fassung": 1}, kanal="netz")
        aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/hinweis", {"plan": "grob", "zu": "M2", "text": "M2 kleiner schneiden"})
        self.assertEqual([h["text"] for h in self.daten()["grob"]["hinweise"] if h["offen"]], ["M2 kleiner schneiden"])
        with mock.patch.object(grobplan, "anstossen", return_value="Grob-Planer angestoßen") as an:
            r = aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/ueberarbeiten", {"plan": "grob", "text": "und M3 später"})
        self.assertEqual(r["text"], "Grob-Planer angestoßen")
        an.assert_called_once()
        with self.assertRaisesRegex(aktionen.Ungueltig, "Text fehlt"):
            aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/hinweis", {"plan": "grob", "text": " "})
        r = aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/grob-freigeben", {"fassung": 1})
        self.assertTrue(r["angenommen"])
        self.assertEqual(self.daten()["dran"], "fein")
        with self.assertRaises(LookupError):
            aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/gibtesnicht", {})


class FeinFehler(Grund):
    def test_abgelehnter_feinplan_ist_sichtbar(self):
        """A2056: passt der Feinplan nicht (z. B. gesperrte Bereiche), legt die AMW nichts an – die Seite zeigt den Grund statt
        „Noch kein Feinplan“, und „Überarbeiten lassen“ plant mit Hinweis neu."""
        from amw import feinplanung
        demo(self.con, self.pid, "grob2")
        grobplan.annehmen(self.con, self.pid, kern.ENTWICKLER, 2)
        m1 = self.con.execute("SELECT id FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()[0]
        feinplanung.entwurf_eintragen(self.con, self.pid, [m1], 1, None, modell="sonnet", usd=0.07,
                                      fehler="Paket P1: Bereiche enthalten gesperrte Pfade (tests/x.py)")
        m = self.daten()["fein"]["meilensteine"][0]
        self.assertEqual((m["bogen"], m["pakete"], m["fassung"]), (m1, [], 1))
        self.assertIn("gesperrte Pfade", " ".join(m["fehler"]))


def bestand(con, pid):
    """Projekt mit Bestand (A2061): Themen frei, alte Meilensteine mit Paketen – einer läuft, einer fertig –, kein Grobplan."""
    t = demo(con, pid, "konzept")
    alt = planung.bogen_neu(con, pid, "TL", "Altbestand fertig")
    neu = planung.bogen_neu(con, pid, "TL", "Laufender Bestand")
    for bid, n, status in ((alt, 2, "fertig"), (neu, 3, "laeuft")):
        for i in range(n):
            aid = planung.schritt_setzen(con, pid, "TL", titel=f"Paket {bid}-{i}", bogen_id=bid, groesse="S", art="mechanisch", agent="CC1")
            if status == "fertig" or i == 0:
                with db.schreiben(con):
                    con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234', fertig_utc = ? WHERE id = ?", (db.jetzt(), aid))
    with db.schreiben(con):
        con.execute("UPDATE bogen SET status = 'fertig' WHERE id = ?", (alt,))
        con.execute("UPDATE bogen SET status = 'aktiv' WHERE id = ?", (neu,))
    return t, alt, neu


class Bestand(Grund):
    def test_bestand_ohne_grobplan(self):
        """A2061 (Marcel 24.11.): bei Bestand kein „Konzept abschließen“ (A2030 legte alles neu an), Grob zeigt den Bestand, ein
        laufender Meilenstein ohne Plan-Ja ist Umsetzung und nicht „Feinplan wartet auf dich“."""
        _, alt, neu = bestand(self.con, self.pid)
        d = self.daten()
        self.assertEqual(d["konzept"]["bestand"], 2)
        self.assertEqual([(b["bogen"], b["status"], b["pakete"], b["fertig"]) for b in d["grob"]["bestand"]], [(neu, "aktiv", 3, 1), (alt, "fertig", 2, 2)])
        self.assertEqual([m["bogen"] for m in d["umsetzung"]["meilensteine"]], [neu])
        demo2 = projektweg_seite.bestand(self.con, self.pid)
        self.assertEqual(len(demo2), 2)

    def test_neues_projekt_ohne_bestand(self):
        demo(self.con, self.pid, "grob2")
        self.assertEqual((self.daten()["konzept"]["bestand"], self.daten()["grob"]["bestand"]), (0, []))


class KartenUndVerlauf(Grund):
    def test_delta_als_karten_mit_zielen(self):
        """A2065: ein Entwurf als Karten in Stufen, „wer“ in Worten, Ziel-Meilenstein mit Projektnummer bzw. neu; geändert und
        verworfen mit dem bisherigen Titel."""
        demo(self.con, self.pid, "fein")
        m1, nr = self.con.execute("SELECT id, nr FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()
        alt = self.con.execute("SELECT id, titel FROM aufgabe WHERE titel = 'Tests für Speichern'").fetchone()
        d = {"delta": True, "meilensteine": [{"schluessel": "M1", "bestehend": m1}, {"schluessel": "M2", "titel": "Export"}],
             "pakete": [{"schluessel": "P1", "meilenstein": "M1", "titel": "Schlagwort speichern", "ausfuehrung": "p", "modell": "sonnet",
                         "groesse": "S", "nach": [], "abnahme_befehl": "python -m unittest tests.test_tag"},
                        {"schluessel": "P2", "meilenstein": "M2", "titel": "Export als Markdown", "ausfuehrung": "agent", "groesse": "M",
                         "nach": ["P1"], "interaktiv_grund": "gesperrter Bereich"}],
             "aendern": [{"paket": f"A{alt[0]}", "titel": "Tests für Speichern mit Schlagwort", "grund": "Schlagwort"}],
             "verwerfen": []}
        k = projektweg_seite._entwurf_karten(self.con, self.pid, d)
        self.assertEqual([(x["titel"], x["stufe"], x["wer"]) for x in k["karten"]],
                         [("Schlagwort speichern", 1, "Headless · Sonnet"), ("Export als Markdown", 2, "Fenster")])
        self.assertEqual(k["ziele"], [{"nr": nr, "titel": "Welt sichtbar", "neu": False}, {"nr": None, "titel": "Export", "neu": True}])
        self.assertEqual((k["aendern"][0]["aufgabe"], k["aendern"][0]["alt"]), (alt[0], alt[1]))

    def test_verlauf_je_schritt_in_menschensprache(self):
        """A2063: jeder Eintrag hat einen Schritt; TH-Nummern werden zum Thema mit Namen, interne Kürzel fallen weg, Langes auf Klick."""
        t = demo(self.con, self.pid, "grob2")
        v = self.daten()["verlauf"]
        schritte = {e["art"]: e["schritt"] for e in v}
        self.assertEqual((schritte["thema_freigegeben"], schritte["grobplan_entwurf"], schritte["konzept_abschluss"]), ("konzept", "grob", "konzept"))
        frei = next(e for e in v if e["art"] == "thema_freigegeben")
        self.assertTrue(frei["zeile"].startswith("Thema „"), frei["zeile"])
        self.assertNotIn(f"TH{t[0]} ", frei["zeile"])
        x = projektweg_seite.verlauf_lesbar([{"art": "protokoll", "rolle": "agent", "text": "P4 fertig – siehe #31234 " + "lang " * 60}], {})[0]
        self.assertEqual(x["schritt"], "umsetzung")
        self.assertNotIn("P4", x["zeile"])
        self.assertNotIn("#31234", x["zeile"])
        self.assertTrue(x["zeile"].endswith("…") and x["lang"])
        self.assertEqual(projektweg_seite.verlauf_lesbar([{"art": "plan_hinweis", "rolle": "mensch", "text": "Hinweis an den Planer – Grobplan: mehr"}], {})[0]["schritt"], "grob")
        self.assertEqual(projektweg_seite.verlauf_lesbar([{"art": "meilenstein_frei", "rolle": "mensch", "text": "M3: Abschluss freigegeben"}], {})[0]["schritt"], "abschluss")


class PruefungNachholen(Grund):
    def test_pruefung_starten_fuer_alte_meilensteine(self):
        """A2064 (TL #32217): bereit, aber nie geprüft – „Prüfung starten“ holt Gesamttest und Prüfer nach (abschluss.vor_bereit)."""
        from amw import abschluss
        demo(self.con, self.pid, "abschluss-ohne")
        x = self.daten()["abschluss"][0]
        self.assertEqual((x["bereit"], x["pruefung"], x["pruefung_laeuft"]), (True, None, False))
        gestartet = []
        from amw import schalter
        with db.schreiben(self.con):
            schalter._setzen(self.con, self.pid, "an")                       # Planer an (sonst „melden“ wie ohne Planer)
        with mock.patch.object(abschluss, "STARTER", lambda pid, bid, stand: gestartet.append((bid, stand)) or 4711),                 mock.patch.dict(os.environ, {"AMW_PLANER_AUS": ""}):
            r = aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/pruefung-starten", {"bogen": x["bogen"]})
        self.assertEqual(r, {"ergebnis": "pruefung"})
        self.assertEqual(gestartet[0][0], x["bogen"])
        self.assertTrue(self.daten()["abschluss"][0]["pruefung_laeuft"])
        with self.assertRaisesRegex(aktionen.Ungueltig, "am PC"):
            aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/pruefung-starten", {"bogen": x["bogen"]}, kanal="netz")

    def test_nicht_bei_ergebnis_und_nicht_wenn_nicht_bereit(self):
        demo(self.con, self.pid, "abschluss")
        x = self.daten()["abschluss"][0]
        with self.assertRaisesRegex(aktionen.Ungueltig, "schon ein Prüf-Ergebnis"):
            aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/pruefung-starten", {"bogen": x["bogen"]})
        m3 = self.con.execute("SELECT id FROM bogen WHERE titel = 'Spieler greift ein'").fetchone()[0]
        with self.assertRaisesRegex(aktionen.Ungueltig, "nicht bereit"):
            aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/pruefung-starten", {"bogen": m3})


class OffeneAenderung(Grund):
    def test_offene_aenderung_macht_feinplanung_zu_wartet_auf_dich(self):
        """A2068 (D1601): nach erledigtem Feinplan stand der Schritt auf ✓ „–“, obwohl ein Delta auf Marcel wartete."""
        from amw import feinplanung, planansicht
        t = demo(self.con, self.pid, "fein")
        m1 = self.con.execute("SELECT id FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()[0]
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, m1)
        d = self.daten()
        fein = next(x for x in d["schritte"] if x["schritt"] == "fein")
        self.assertEqual((fein["zustand"], fein["bei_dir"]), ("erledigt", False))           # ohne Änderung: erledigt
        entwurf = {"delta": True, "meilensteine": [{"schluessel": "M1", "bestehend": m1}],
                   "pakete": [{"schluessel": "P1", "meilenstein": "M1", "titel": "Schlagwort", "ausfuehrung": "p", "groesse": "S", "nach": []}]}
        offen = {"entwuerfe": [{"thema": t[2], "name": "Speichern und Laden", "eid": 999, "zeit_utc": "2026-11-24T16:00:00Z", "modell": "sonnet",
                                "usd": 0.03, "fehler": None, "nichts": False, "grund": "x", "meilensteine": 0, "pakete": 1, "zeilen": []}],
                 "planer_laeuft": []}
        with mock.patch.object(planansicht, "entwuerfe", return_value=offen), \
                mock.patch.object(planer, "letzter_entwurf", return_value={"id": 999, "entwurf": entwurf}):
            d = self.daten()
        fein = next(x for x in d["schritte"] if x["schritt"] == "fein")
        self.assertEqual((fein["zustand"], fein["zeichen"], fein["bei_dir"]), ("dran", "●", True))
        self.assertEqual(d["dran"], "fein")                                                 # die Seite öffnet dort


class Abschluss(Grund):
    def test_abnehmen_ist_das_ja_zum_abschluss(self):
        demo(self.con, self.pid, "abschluss")
        d = self.daten()
        x = d["abschluss"][0]
        self.assertEqual((x["bereit"], x["frei"], x["status"]), (True, False, "aktiv"))
        self.assertIsNotNone(x["bericht"])
        aktionen.ausfuehren(self.con, self.pid, "/api/meilenstein/freigeben", {"bogen": x["bogen"], "art": "abschluss"})
        x = self.daten()["abschluss"][0]
        self.assertEqual((x["frei"], x["status"]), (True, "fertig"))


FENSTER = "document.querySelector('#pjw-fenster .pjw-fenster')"


class Seite(Rundgang):
    STAND = "grob2"

    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        for ziel in (grobplan, planer):
            p = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
            p.start()
            self.addCleanup(p.stop)
        demo(self.con, self.pid, self.STAND)

    def test_leiste_ansicht_seitenfenster_esc(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritte')")
        self.assertEqual(self.tab.js("document.querySelectorAll('.pjw-schritt').length"), 5)
        self.assertIn("wartet auf dich", self.tab.js("document.querySelector('.pjw-schritt[data-schritt=grob] .pjw-wert').innerText"))
        self.assertIn("gewaehlt", self.tab.js("document.querySelector('.pjw-schritt[data-schritt=grob]').className"))
        self.assertTrue(self.tab.js("[...document.querySelectorAll('.pjw-ansicht button')].some(b => b.textContent === 'Grobplan freigeben')"))
        self.assertIn("geändert", self.tab.js("document.querySelector('.pjw-karte[data-ms=M3]').innerText"))
        self.tab.js("document.querySelector('.pjw-karte[data-ms=M2]').click()")
        self.warten(f"{FENSTER} && {FENSTER}.innerText.includes('Ein Bewohner lebt')")
        self.tab.js("document.querySelector('#pjw-erg').value = 'M2 mit zwei Bewohnern'; [...document.querySelectorAll('#pjw-fenster button')]"
                    ".find(b => b.textContent === 'Als Hinweis an den Planer').click()")
        self.warten(f"!{FENSTER} && document.querySelector('.pjw-hinweise') && document.querySelector('.pjw-hinweise').innerText.includes('M2 mit zwei Bewohnern')")
        self.tab.js("document.querySelector('.pjw-zeile[data-th]') || document.querySelector('.pjw-karte[data-ms=M1]').click()")
        self.warten(FENSTER)
        self.esc()
        self.warten(f"!{FENSTER}")
        self.tab.js("document.querySelector('.pjw-schritt[data-schritt=konzept]').click()")
        self.warten("document.querySelectorAll('.pjw-ansicht .pjw-zeile[data-th]').length === 4")

    def test_fortschritt_als_ueberlagerung_schliesst_beim_ergebnis(self):
        with db.schreiben(self.con):
            lid = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="AMW", beschreibung="Grob-Planer", status="laeuft",
                               angemeldet_utc=db.jetzt(), start_utc=db.jetzt())
        planer_fortschritt.melden(self.con, self.pid, lid, art="grobplaner", modell="opus", was="Thema 2 von 4", nr=2, gesamt=4, usd=0.3)
        self.oeffnen("projektweg", "document.querySelector('#pjw-ueber .pjw-lauf')")
        self.assertIn("Thema 2 von 4", self.tab.js("document.querySelector('#pjw-ueber').innerText"))
        planer_fortschritt.melden(self.con, self.pid, lid, zustand="fertig", sofort=True)
        self.warten("!document.querySelector('#pjw-ueber')", 10)              # schließt sich von selbst, ohne Klick

    def test_rundgang(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                fehler = self.besuchen("projektweg", "projektweg-grob", bereit="document.querySelector('.pjw-karte[data-ms=M3]')"
                                       + (" || document.querySelector('.pjw-schritt')" if g == "handy" else ""), g=g, t=th)
                self.assertEqual(fehler, [], f"{g} {th}")
                fehler = self.besuchen("projektweg", "projektweg-grob-offen", bereit="document.querySelector('.pjw-schritt')",
                                       tun="zustand.pwSicht = 1; zustand.pwOffen = true; zeige('projektweg', true)",
                                       danach="[...document.querySelectorAll('.pjw-ansicht > .pjw-kopf button')].some(b => b.textContent === t('pjw_g_freigeben'))",
                                       g=g, t=th)                         # TL #31991: die Handlung steht oben neben der Überschrift
                self.assertEqual(fehler, [], f"offen {g} {th}")
                fehler = self.besuchen("projektweg", "projektweg-fenster", bereit="document.querySelector('.pjw-schritt')",
                                       tun="zustand.pwSicht = 1; zustand.pwOffen = true; zeige('projektweg', true).then(() => pwOeffne({art: 'ms', id: 'M3', fassung: 2}))",
                                       danach=FENSTER, g=g, t=th)
                self.assertEqual(fehler, [], f"Fenster {g} {th}")


class SeiteFein(Seite):
    STAND = "fein"

    def test_leiste_ansicht_seitenfenster_esc(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-paket')")
        self.assertEqual(self.tab.js("document.querySelector('.pjw-schritt[data-schritt=fein]').className.includes('gewaehlt')"), True)
        self.assertTrue(self.tab.js("[...document.querySelectorAll('.pjw-paket')].some(p => p.innerText.includes('Headless · Sonnet'))"))
        self.assertEqual(self.tab.js("document.querySelectorAll('.pjw-snr').length"), 3)
        self.assertTrue(self.tab.js("[...document.querySelectorAll('.pjw-ansicht button')].some(b => /Plan M\\d+ freigeben und starten/.test(b.textContent))"))
        self.tab.js("document.querySelector('.pjw-paket').click()")
        self.warten(f"{FENSTER} && {FENSTER}.innerText.includes('Fenster · CC1')")
        self.esc()
        self.warten(f"!{FENSTER}")

    def test_fortschritt_als_ueberlagerung_schliesst_beim_ergebnis(self):
        pass                                                                  # schon in Seite

    def test_rundgang(self):
        for g in ("pc", "handy"):
            for th in ("hell", "dunkel"):
                fehler = self.besuchen("projektweg", "projektweg-fein", bereit="document.querySelector('.pjw-schritt')",
                                       tun="zustand.pwSicht = 2; zustand.pwOffen = true; zeige('projektweg', true)",
                                       danach="document.querySelector('.pjw-paket')", g=g, t=th)
                self.assertEqual(fehler, [], f"{g} {th}")



class SeiteAbschluss(Rundgang):
    """Der Klick auf „Abnehmen“ macht den Meilenstein fertig (vorher ging er an /api/bogen/abnehmen und scheiterte bei „aktiv“)."""
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        for ziel in (grobplan, planer):
            p = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
            p.start()
            self.addCleanup(p.stop)
        demo(self.con, self.pid, "abschluss")

    def test_abnehmen_klicken(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt[data-schritt=abschluss]')")
        self.tab.js("zustand.pwSicht = 4; zeige('projektweg', true)")
        knopf = "[...document.querySelectorAll('.pjw-ansicht > .pjw-kopf button')].find(b => /abnehmen/.test(b.textContent))"           # „M… abnehmen“ (A2064)
        self.warten(knopf)
        self.tab.js(knopf + ".click()")
        self.warten("document.querySelector('.pjw-ansicht .pjw-a-zuletzt') && document.querySelector('.pjw-ansicht .pjw-a-zuletzt').textContent.includes('Zuletzt abgenommen')")
        self.assertEqual(self.con.execute("SELECT status FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()[0], "fertig")

    def test_rundgang(self):
        for g, th in (("pc", "hell"), ("handy", "dunkel")):
            fehler = self.besuchen("projektweg", "projektweg-abschluss", bereit="document.querySelector('.pjw-schritt')",
                                   tun="zustand.pwSicht = 4; zustand.pwOffen = true; zeige('projektweg', true)",
                                   danach="document.querySelector('.pjw-pruefung')", g=g, t=th)
            self.assertEqual(fehler, [], f"{g} {th}")



class SeiteBestand(Rundgang):
    """A2061 in der Seite: Nummern wie überall (M<Id>), kein „Konzept abschließen“ bei Bestand, Grob zeigt den Bestand.
    A2060: ohne Änderung wird nichts neu gezeichnet (das Element bleibt dasselbe), mit Änderung schon."""
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        for ziel in (grobplan, planer):
            p = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
            p.start()
            self.addCleanup(p.stop)
        _, self.alt, self.neu = bestand(self.con, self.pid)
        self.nr_neu = self.con.execute("SELECT nr FROM bogen WHERE id = ?", (self.neu,)).fetchone()[0]

    def test_bestand_und_kein_flackern(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        self.tab.js("zustand.pwSicht = 0; zeige('projektweg', true)")
        self.warten("document.querySelectorAll('.pjw-zeile[data-th]').length === 4")
        self.assertFalse(self.tab.js("[...document.querySelectorAll('.pjw-ansicht button')].some(b => b.textContent === t('pjw_k_abschliessen'))"))
        self.assertIn("Meilensteine", self.tab.js("document.querySelector('.pjw-ansicht').innerText"))
        self.assertIn(f"M{self.nr_neu}", self.tab.js("document.querySelector('.pjw-schritt[data-schritt=umsetzung] .pjw-wert').innerText"))
        self.assertNotIn("wartet", self.tab.js("document.querySelector('.pjw-schritt[data-schritt=fein] .pjw-wert').innerText"))
        self.tab.js("zustand.pwSicht = 1; zeige('projektweg', true)")
        self.warten(f"document.querySelector('.pjw-ansicht .pjw-liste') && document.querySelector('.pjw-ansicht .pjw-liste').innerText.includes('M{self.nr_neu}')")
        # A2060: zweimal „still“ neu zeichnen ohne Änderung – das Element bleibt dasselbe (nichts verschwindet)
        self.tab.js("window._seite = document.querySelector('.pjw-seite'); zeige('projektweg', true).then(() => zeige('projektweg', true)).then(() => window._fertig = 1)")
        self.warten("window._fertig === 1")
        self.assertTrue(self.tab.js("window._seite === document.querySelector('.pjw-seite')"))
        with db.schreiben(self.con):                                         # eine echte Änderung: jetzt wird neu gezeichnet
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'x', fertig_utc = ? WHERE bogen_id = ? AND status != 'fertig'",
                             (db.jetzt(), self.neu))
        self.tab.js("window._fertig = 0; zeige('projektweg', true).then(() => window._fertig = 1)")
        self.warten("window._fertig === 1")
        self.assertFalse(self.tab.js("window._seite === document.querySelector('.pjw-seite')"))

    def test_rundgang(self):
        for g, th in (("pc", "hell"), ("handy", "dunkel")):
            fehler = self.besuchen("projektweg", "projektweg-bestand", bereit="document.querySelector('.pjw-schritt')",
                                   tun="zustand.pwSicht = 1; zustand.pwOffen = true; zeige('projektweg', true)",
                                   danach="document.querySelector('.pjw-ansicht .pjw-liste')", g=g, t=th)
            self.assertEqual(fehler, [], f"{g} {th}")



class SeiteOhnePruefung(Rundgang):
    """A2064: „ohne Abschlussprüfung“ und der Klick auf „Prüfung starten“ – danach „läuft“ statt Knopf."""
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        for ziel in (grobplan, planer):
            p = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
            p.start()
            self.addCleanup(p.stop)
        from amw import abschluss
        p = mock.patch.object(abschluss, "STARTER", lambda *a, **k: 4711)
        p.start()
        self.addCleanup(p.stop)
        demo(self.con, self.pid, "abschluss-ohne")
        from amw import schalter
        with db.schreiben(self.con):
            schalter._setzen(self.con, self.pid, "an")                       # Planer an: der Prüfer würde wirklich starten (Starter ersetzt)
        p = mock.patch.dict(os.environ, {"AMW_PLANER_AUS": ""})
        p.start()
        self.addCleanup(p.stop)

    def test_pruefung_starten_klicken(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        self.tab.js("zustand.pwSicht = 4; zeige('projektweg', true)")
        knopf = "[...document.querySelectorAll('.pjw-ansicht > .pjw-kopf button')].find(b => b.textContent === t('pjw_a_starten'))"
        self.warten(knopf)
        self.assertIn(self.tab.js("t('pjw_a_ohne')"), self.tab.js("document.querySelector('.pjw-ab-karte').innerText"))
        self.tab.js(knopf + ".click()")
        self.warten("document.querySelector('.pjw-ab-karte') && document.querySelector('.pjw-ab-karte').innerText.includes(t('pjw_a_laeuft'))")
        self.assertFalse(self.tab.js(f"!!({knopf})"))


class SeiteDelta(Rundgang):
    """A2065: eine Änderung als Karten in Stufen; der Knopf nennt den Umfang; eine Hauptaktion je Ansicht (TL #32217)."""
    def daten(self):
        from amw import planansicht
        kern.agent_neu(self.con, self.pid, "CC1")
        for ziel in (grobplan, planer):
            p = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
            p.start()
            self.addCleanup(p.stop)
        t = demo(self.con, self.pid, "fein")
        m1 = self.con.execute("SELECT id FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()[0]
        alt = self.con.execute("SELECT id FROM aufgabe WHERE titel = 'Tests für Speichern'").fetchone()[0]
        weg = self.con.execute("SELECT id FROM aufgabe WHERE titel = 'Farben und Schrift nach Stil'").fetchone()[0]
        entwurf = {"delta": True, "meilensteine": [{"schluessel": "M1", "bestehend": m1}],
                   "pakete": [{"schluessel": "P1", "meilenstein": "M1", "titel": "Schlagwort beim Speichern ablegen", "ausfuehrung": "p", "modell": "sonnet",
                               "groesse": "S", "nach": [], "abnahme_befehl": "python -m unittest tests.test_tag", "bereiche": "scripts/speicher.gd"},
                              {"schluessel": "P2", "meilenstein": "M1", "titel": "Schlagwort im Aquarium anzeigen", "ausfuehrung": "agent", "groesse": "M",
                               "nach": ["P1"], "interaktiv_grund": "Optik – Marcels Auge"}],
                   "aendern": [{"paket": f"A{alt}", "titel": "Tests für Speichern mit Schlagwort", "grund": "Schlagwort kommt dazu"}],
                   "verwerfen": [{"paket": f"A{weg}", "grund": "Stil steht schon im Grundgerüst"}]}
        offen = {"entwuerfe": [{"thema": t[2], "name": "Speichern und Laden", "eid": 999, "zeit_utc": "2026-11-24T16:00:00Z", "modell": "sonnet",
                                "usd": 0.03, "fehler": None, "nichts": False, "grund": "Schlagwort", "meilensteine": 0, "pakete": 2, "zeilen": []}],
                 "planer_laeuft": []}
        for ziel, name, wert in ((planansicht, "entwuerfe", offen), (planer, "letzter_entwurf", {"id": 999, "entwurf": entwurf})):
            p = mock.patch.object(ziel, name, return_value=wert)
            p.start()
            self.addCleanup(p.stop)

    def test_karten_knopf_und_eine_hauptaktion(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        self.tab.js("zustand.pwSicht = 2; zeige('projektweg', true)")
        self.warten("document.querySelector('.pjw-delta .pjw-paket')")
        self.assertEqual(self.tab.js("document.querySelectorAll('.pjw-delta .pjw-paket').length"), 2)
        self.assertEqual(self.tab.js("document.querySelectorAll('.pjw-delta .pjw-snr').length"), 2)
        knopf = self.tab.js("[...document.querySelectorAll('.pjw-ansicht button')].map(b => b.textContent).find(x => x.startsWith('Änderung TH'))")
        self.assertIn("2 Pakete in M", knopf)
        self.assertIn("wartet auf dich", self.tab.js("document.querySelector('.pjw-schritt[data-schritt=fein] .pjw-wert').innerText"))   # A2068
        self.assertIn("1 geändert", knopf)
        self.assertEqual(self.tab.js("document.querySelectorAll('.pjw-ansicht .knopf.haupt').length"), 1)   # oben „Plan M… freigeben und starten“
        self.assertTrue(self.tab.js("/^Plan M/.test(document.querySelector('.pjw-ansicht .knopf.haupt').textContent)"))
        self.tab.js("document.querySelector('.pjw-delta .pjw-paket').click()")
        self.warten("document.querySelector('#pjw-fenster .pjw-fenster') && document.querySelector('#pjw-fenster .pjw-fenster').innerText.includes('python -m unittest tests.test_tag')")

    def test_rundgang(self):
        for g, th in (("pc", "hell"), ("handy", "dunkel")):
            fehler = self.besuchen("projektweg", "projektweg-delta", bereit="document.querySelector('.pjw-schritt')",
                                   tun="zustand.pwSicht = 2; zustand.pwOffen = true; zeige('projektweg', true)",
                                   danach="document.querySelector('.pjw-delta .pjw-paket')", g=g, t=th)
            self.assertEqual(fehler, [], f"{g} {th}")


if __name__ == "__main__":
    unittest.main()
