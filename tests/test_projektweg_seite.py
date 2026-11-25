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

from amw import aktionen, arbeitspaket, db, grobplan, kern, planer, planer_fortschritt, planung, projektweg, projektweg_seite, themen
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
    from amw import abschlusslage                                            # A2082: das Ergebnis gilt nur für den geprüften Stand
    stand = abschlusslage.stand(con, con.execute("SELECT * FROM bogen WHERE id = ?", (m1,)).fetchone())
    with db.schreiben(con):                                                  # Ergebnis des Prüfers, wie abschluss.eintragen es schreibt
        abschluss._ereignis(con, pid, abschluss.ERGEBNIS, bogen=m1, stand=stand, test={"befehl": "godot --headless -s tests/alle.gd", "lauf": 7, "rc": 0},
                            themen=[{"thema": f"TH{t[0]}", "erfuellt": True, "beleg": "Aquarium-Szene mit Kamera"},
                                    {"thema": f"TH{t[2]}", "erfuellt": True, "beleg": "Speichern und Laden"}],
                            ziel={"erfuellt": True, "zustand": "erfuellt", "beleg": "Aquarium läuft und speichert"},                            # A2098
                            vorfuehrung=["Aquarium starten", "Welt speichern", "neu laden – alles ist noch da"], ok=True, angelegt={},
                            belege={"zweig": "main", "sha": "c" * 40, "pakete": []})         # A2088: mit geprüften Belegen
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

    def test_leiste_wartet_auf_dich_und_menschensprache(self):
        """A2076 (5), B2938: zuerst klärt es der Lead (Leiste ohne „wartet auf dich“), ohne Lead der Mensch; Gründe ohne „Sperre Bash(…)“."""
        from amw import feinplanung, planfunde
        demo(self.con, self.pid, "grob2")
        grobplan.annehmen(self.con, self.pid, kern.ENTWICKLER, 2)
        m1 = self.con.execute("SELECT id FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()[0]
        thema = feinplanung.themen_der(self.con, self.pid, self.con.execute("SELECT * FROM bogen WHERE id = ?", (m1,)).fetchone())[0]
        plan = {"pakete": [{"schluessel": "P1", "meilenstein": "M1", "thema": f"TH{thema}", "titel": "Gerüst", "auftrag": "Gerüst anlegen.",
                            "groesse": "S", "art": "mechanisch", "ausfuehrung": "p", "fertig_quelle": "commit", "bereiche": "welt.gd",
                            "abnahme_befehl": "python -c \"import welt\""}]}
        feinplanung.entwurf_eintragen(self.con, self.pid, [m1], 1, plan, modell="sonnet", usd=0.07)
        d = self.daten()
        m = d["fein"]["meilensteine"][0]
        self.assertIn({"art": "sperre", "x": {}}, m["gruende"])
        self.assertNotIn("Bash(", " ".join(planfunde.saetze(self.con, self.pid, m["fehler"])))
        fein = next(s for s in d["schritte"] if s["schritt"] == "fein")
        self.assertEqual((fein["zustand"], fein["wer"], fein["bei_dir"]), ("dran", ["TL"], False))
        with mock.patch.object(kern, "lead", return_value=None):
            fein = next(s for s in self.daten()["schritte"] if s["schritt"] == "fein")
            self.assertEqual((fein["zustand"], fein["bei_dir"]), ("dran", True))


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


class Ausloeser(Grund):
    """A2078: wer einen Lauf ausgelöst hat – das Fenster nur beim eigenen Klick auf der Seite."""
    def setUp(self):
        super().setUp()
        from amw import abschluss, feinplanung, gegenlesen, schalter
        u = mock.patch.dict(os.environ)
        u.start()
        self.addCleanup(u.stop)
        os.environ["AMW_GEGENLESEN_AUS"] = "1"                                             # nur ein Test lässt gegenlesen
        os.environ.pop("AMW_PLANER_AUS", None)
        for ziel in (gegenlesen, feinplanung, abschluss):
            m = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
            m.start()
            self.addCleanup(m.stop)
        with db.schreiben(self.con):
            schalter._setzen(self.con, self.pid, "an")

    def an(self, art):
        return [json.loads(r[0]) for r in self.con.execute("SELECT text FROM plan_ereignis WHERE art = ? ORDER BY id", (art,))]

    def lauf(self):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="TL", beschreibung="x", status="laeuft", angemeldet_utc=db.jetzt(), start_utc=db.jetzt())

    def test_gegenleser_eines_agenten(self):
        os.environ.pop("AMW_GEGENLESEN_AUS")
        tid = themen.neu(self.con, self.pid, "TL", "Neu", pfleger="CC1")
        themen.pflegen(self.con, self.pid, "CC1", tid, "Ein Text.")
        e = self.an("thema_gegenlesen")[-1]
        self.assertEqual((e["ausloeser"], e.get("anlass")), ("CC1", None))

    def test_klick_auf_der_seite_und_kein_klick_danach(self):
        demo(self.con, self.pid, "konzept")
        aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/konzept-abschliessen", {})
        e = self.an("grobplan_angestossen")[-1]
        self.assertEqual((e["ausloeser"], e["anlass"], e["prozess"]), (kern.ENTWICKLER, "klick", 4711))   # bleibt auch nach dem Start stehen
        self.assertIsNone(planer_fortschritt.KLICK.get())
        grobplan.entwurf_eintragen(self.con, self.pid, 1, None, fehler="x")
        grobplan.anstossen(self.con, self.pid, von="TL")
        e = self.an("grobplan_angestossen")[-1]
        self.assertEqual((e["ausloeser"], e.get("anlass")), ("TL", None))

    def test_themen_ja_ist_eine_folge_kein_fenster(self):
        t = demo(self.con, self.pid, "fein")
        themen.pflegen(self.con, self.pid, "CC1", t[2], "Neue Fassung.")
        aktionen.ausfuehren(self.con, self.pid, "/api/thema/freigeben", {"thema": t[2]})
        e = self.an("thema_planer")[-1]
        self.assertEqual((e["ausloeser"], e.get("anlass")), ("AMW", None))

    def test_laeufe_mit_schritt_rolle_und_mein(self):
        kern.agent_neu(self.con, self.pid, "Co")
        kern.projekt_einstellen(self.con, self.pid, "TL", co_entwickler="Co")
        faelle: list[dict] = [dict(art="gegenlesen", thema=3, fassung=8, ausloeser="TL"), dict(art="planer", thema=3, fassung=2, ausloeser="Co"),
                   dict(art="feinplaner", ziel="M1", ausloeser="AMW"), dict(art="grobplaner", fassung=1, ausloeser=kern.ENTWICKLER, anlass="klick"),
                   dict(art="grobplaner", fassung=1, ausloeser=kern.ENTWICKLER), dict(art="grobplaner", fassung=1)]   # zuletzt: ohne Klick, alter Eintrag
        for kw in faelle:
            planer_fortschritt.melden(self.con, self.pid, self.lauf(), was="x", sofort=True, **kw)
        x = {(l["art"], l["ausloeser"], l["anlass"]): (l["schritt"], l["rolle"], l["mein"]) for l in self.daten()["laeufe"]}
        self.assertEqual(x[("gegenlesen", "TL", None)], ("konzept", "lead", False))
        self.assertEqual(x[("planer", "Co", None)], ("fein", "co", False))
        self.assertEqual(x[("feinplaner", "AMW", None)], ("fein", "amw", False))
        self.assertEqual(x[("grobplaner", kern.ENTWICKLER, "klick")], ("grob", "mensch", True))
        self.assertEqual(x[("grobplaner", kern.ENTWICKLER, None)], ("grob", "mensch", False))
        self.assertEqual(x[("grobplaner", None, None)], ("grob", None, False))

    def test_der_lauf_reicht_den_ausloeser_weiter(self):
        t = demo(self.con, self.pid, "fein")
        with db.schreiben(self.con):
            planer._ereignis(self.con, self.pid, "AMW", planer.ANGESTOSSEN, t[0], fassung=1, modell="sonnet", ausloeser=kern.ENTWICKLER, anlass="klick")
        with mock.patch.object(planer, "planen", return_value={"ergebnis": "kein JSON", "usd": 0.1, "fehler": None}):
            planer.ausfuehren(self.con, self.pid, t[0], 1)
        s = [l for l in planer_fortschritt.alle(self.con, self.pid) if l["art"] == "planer"][0]
        self.assertEqual((s["ausloeser"], s["anlass"], s["fassung"]), (kern.ENTWICKLER, "klick", 1))

    def test_pruefung_starten_laeuft_als_mein(self):
        demo(self.con, self.pid, "abschluss-ohne")
        x = self.daten()["abschluss"][0]
        aktionen.ausfuehren(self.con, self.pid, "/api/projektweg/pruefung-starten", {"bogen": x["bogen"]})
        l = [y for y in self.daten()["laeufe"] if y["art"] == "abschluss"]
        self.assertEqual([(y["ziel"], y["schritt"], y["mein"]) for y in l], [(f"M{x['nr']}", "abschluss", True)])


class UebernahmeImVerlauf(Grund):
    """A2075: die Übernahme des Bestands ist EINE Zeile in der Grobplanung; echte Freigaben bleiben einzeln."""
    def test_eine_zeile_in_der_grobplanung(self):
        from amw import planansicht
        _, alt, neu = bestand(self.con, self.pid)
        self.assertTrue(grobplan.uebernehmen(self.con, self.pid))
        v = self.daten()["verlauf"]
        x = [e for e in v if "Bestand übernommen" in (e["text"] or "")]
        self.assertEqual([(e["zeile"], e["schritt"], e["rolle"]) for e in x], [("Bestand übernommen: 2 Meilensteine", "grob", "amw")])
        self.assertEqual(x[0]["lang"], "M1, M2")
        self.assertEqual([e for e in v if e["schritt"] == "fein"], [])
        planansicht.zurueck(self.con, self.pid, kern.ENTWICKLER, neu, "grob", "nochmal")            # eine echte Entscheidung
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, neu, "grob")
        v = self.daten()["verlauf"]
        self.assertEqual(sum("Bestand übernommen" in (e["text"] or "") for e in v), 1)
        self.assertEqual([e["schritt"] for e in v if e["art"] == "meilenstein_frei"], ["grob", "grob"])

    def test_leiste_zaehlt_verworfene_nicht_mit(self):
        _, alt, neu = bestand(self.con, self.pid)
        weg = planung.bogen_neu(self.con, self.pid, "TL", "Verworfen")
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'verworfen' WHERE id = ?", (weg,))
        grobplan.uebernehmen(self.con, self.pid)
        a = self.daten()["grob"]["angenommen"]
        self.assertEqual((a["n"], len(a["angelegt"])), (2, 3))                              # wie „Bestand übernommen: 2 Meilensteine“
        self.assertIn("Bestand übernommen: 2 Meilensteine", [e["zeile"] for e in self.daten()["verlauf"]])

    def test_verworfene_auch_nicht_in_liste_und_zuordnung(self):
        """A2086 (1): nur die Anzeige – der angenommene Grobplan selbst bleibt, wie er ist."""
        _, alt, neu = bestand(self.con, self.pid)
        weg = planung.bogen_neu(self.con, self.pid, "TL", "Verworfen")
        nr = self.con.execute("SELECT nr FROM bogen WHERE id = ?", (weg,)).fetchone()[0]
        grobplan.uebernehmen(self.con, self.pid)
        ja = grobplan.angenommen(self.con, self.pid) or {}
        schluessel = next(k for k, v in ja["angelegt"].items() if v == f"M{nr}")
        d = (grobplan.entwurf(self.con, self.pid, ja["fassung"]) or {})["entwurf"]
        erster = d["meilensteine"][0]["schluessel"]
        with db.schreiben(self.con):                                                        # ein anderer Meilenstein kommt „nach“ dem verworfenen
            for r in self.con.execute("SELECT id, text FROM plan_ereignis WHERE art = ?", (grobplan.ENTWURF,)).fetchall():
                x = json.loads(r["text"])
                x["entwurf"]["meilensteine"][0]["nach"] = [schluessel]
                self.con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?", (json.dumps(x), r["id"]))

        def ms():
            return {m["schluessel"]: m for m in self.daten()["grob"]["fassungen"][-1]["meilensteine"]}
        self.assertEqual((len(ms()), ms()[erster]["nach"]), (3, [schluessel]))
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET status = 'verworfen' WHERE id = ?", (weg,))
        self.assertEqual((sorted(set(ms())), ms()[erster]["nach"]), (sorted(set(ja["angelegt"]) - {schluessel}), []))
        self.assertEqual(len((grobplan.entwurf(self.con, self.pid, ja["fassung"]) or {})["entwurf"]["meilensteine"]), 3)

    def test_naechster_meilenstein_ohne_plan(self):
        """A2086 (8): nach der Abnahme nennt die Feinplanung den Meilenstein, der als Nächstes geplant wird."""
        bestand(self.con, self.pid)
        self.assertIsNone(self.daten()["fein"]["naechster"])
        m = planung.bogen_neu(self.con, self.pid, "TL", "Noch ohne Plan")
        n = self.daten()["fein"]["naechster"]
        self.assertEqual((n["bogen"], n["titel"]), (m, "Noch ohne Plan"))

    def test_zahl_stimmt_auch_wenn_die_grenze_schneidet(self):
        from amw import verlauf
        bestand(self.con, self.pid)
        grobplan.uebernehmen(self.con, self.pid)
        e = verlauf.projektweg(self.con, self.pid, grenze=1, buendeln=True)
        self.assertEqual([x["text"] for x in e], ["Bestand übernommen: 2 Meilensteine"])
        self.assertGreater(len(verlauf.projektweg(self.con, self.pid)), len(verlauf.projektweg(self.con, self.pid, buendeln=True)))

    def test_langer_auftrag_ist_als_gekuerzt_markiert(self):
        _, _, neu = bestand(self.con, self.pid)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET auftrag = ? WHERE bogen_id = ? AND status != 'fertig'", ("Satz. " * 300, neu))
        p = [x for m in self.daten()["fein"]["meilensteine"] if m["bogen"] == neu for x in m["pakete"]]
        self.assertEqual({(x["auftrag_mehr"], len(x["auftrag"])) for x in p if x["status"] != "fertig"}, {(True, projektweg_seite.AUFTRAG_KURZ)})
        self.assertEqual({x["auftrag_mehr"] for x in p if x["status"] == "fertig"}, {False})


class FehlerWort(unittest.TestCase):
    def test_teilweise_ist_kein_passte_nicht(self):
        """A2086 (4)"""
        t, n = {"teilweise": True}, {}
        self.assertEqual([projektweg_seite._fehler_wort(x) for x in ([n, n], [t], [t, n])], ["der Plan passte nicht", "teilweise umgesetzt", "zu klären"])


class Gespeichert(Grund):
    def test_nach_dem_speichern_weiss_die_seite_was_gilt(self):
        """A2086 (7): eigene Bearbeitung gilt als freigegeben – und ob der Planer läuft."""
        t = demo(self.con, self.pid, "fein")[2]
        for laeuft in (True, False):
            f = self.con.execute("SELECT max(nr) FROM thema_fassung WHERE thema_id = ?", (t,)).fetchone()[0]
            with mock.patch.object(planer, "laeuft", return_value=laeuft):
                r = aktionen.ausfuehren(self.con, self.pid, "/api/thema/bearbeiten", {"thema": t, "text": f"Neu {laeuft}", "fassung": f})
            self.assertEqual((r["status"], r["planer"]), ("frei", laeuft))


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


def gescheiterte_aenderung(con, pid):
    """A2076: M1 läuft (ein Paket fertig, eines läuft, eines offen), das Thema „Speichern und Laden“ wird geändert, der Planer nennt
    zweimal das laufende Paket als Nacharbeit – wie in der Vorführung (L3452)."""
    from amw import feinplanung, planer_delta
    t = demo(con, pid, "fein")
    m1 = con.execute("SELECT id FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()[0]
    feinplanung.plan_starten(con, pid, kern.ENTWICKLER, m1)
    ids = {r["titel"]: r["id"] for r in con.execute("SELECT id, titel FROM aufgabe WHERE bogen_id = ?", (m1,))}
    for titel in ("Projekt anlegen, Godot-Gerüst", "Speichern und Laden", "Tests für Speichern"):
        themen.verweise_setzen(con, pid, "TL", ids[titel], [f"TH{t[2]}"])
    with db.schreiben(con):
        con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'abc1234' WHERE id = ?", (ids["Projekt anlegen, Godot-Gerüst"],))
        con.execute("UPDATE aufgabe SET status = 'laeuft', begonnen_utc = ? WHERE id = ?", (db.jetzt(), ids["Speichern und Laden"]))
    themen.bearbeiten(con, pid, kern.ENTWICKLER, t[2], "Die Welt bleibt erhalten, auch nach einem Neustart, mit drei Speicherplätzen.")
    antwort = json.dumps({"meilensteine": [], "pakete": [], "nacharbeit": [{"paket": f"A{ids['Speichern und Laden']}", "grund": "Plätze"}],
                          "verwerfen": [{"paket": f"A{ids['Tests für Speichern']}", "grund": "kommt neu"}]})
    planer.entwurf_eintragen(con, pid, t[2], 2, antwort, modell="sonnet", usd=0.05, delta=planer_delta.kontext(con, pid, t[2]))
    return t


class GescheiterteAenderung(Grund):
    def test_schritt_ist_dran_mit_grund_in_menschensprache(self):
        t = gescheiterte_aenderung(self.con, self.pid)
        d = self.daten()
        x = d["fein"]["delta_fehler"]
        self.assertEqual([(y["thema"], y["fassung"]) for y in x], [(t[2], 2)])
        self.assertEqual(x[0]["gruende"], [{"art": "laeuft", "x": {"p": "Speichern und Laden"}}])
        fein = next(s for s in d["schritte"] if s["schritt"] == "fein")
        self.assertEqual((fein["zustand"], fein["wer"], fein["bei_dir"], d["fein"]["lead_klaert"]), ("dran", ["TL"], False, "TL"))   # B2938
        self.assertEqual(d["dran"], "umsetzung")                                            # der Mensch bleibt bei seinem Schritt
        e = [y for y in d["verlauf"] if y["art"] == "thema_planentwurf"][-1]
        self.assertEqual(e["schritt"], "fein")
        self.assertIn("Planer meldet einen Fehler", e["zeile"])
        self.assertIn("wird gerade gebaut", e["lang"])
        self.assertNotIn("nacharbeit 1", e["lang"])

    def test_ohne_lead_wartet_es_auf_den_menschen(self):
        gescheiterte_aenderung(self.con, self.pid)
        with mock.patch.object(kern, "lead", return_value=None):
            d = self.daten()
        fein = next(s for s in d["schritte"] if s["schritt"] == "fein")
        self.assertEqual((fein["zustand"], fein["bei_dir"], d["dran"], d["fein"]["lead_klaert"]), ("dran", True, "fein", None))

    def test_nichts_zu_bauen_blendet_aus(self):
        t = gescheiterte_aenderung(self.con, self.pid)
        self.assertEqual(len(self.daten()["fein"]["delta_fehler"]), 1)
        themen.nichts_zu_bauen(self.con, self.pid, "TL", f"TH{t[2]}", "gebaut mit A1")
        self.assertEqual(self.daten()["fein"]["delta_fehler"], [])
        themen.nichts_zu_bauen(self.con, self.pid, "TL", f"TH{t[2]}", "doch nicht", aufheben=True)
        self.assertEqual(len(self.daten()["fein"]["delta_fehler"]), 1)

    def test_ein_frueherer_vermerk_blendet_nicht_aus(self):
        t = gescheiterte_aenderung(self.con, self.pid)
        e = planer.letzter_entwurf(self.con, self.pid, t[2])
        assert e is not None
        themen.nichts_zu_bauen(self.con, self.pid, "TL", f"TH{t[2]}", "alter Vermerk")
        with db.schreiben(self.con):                                                        # der Vermerk lag vor dem Entwurf
            self.con.execute("UPDATE plan_ereignis SET id = 999999 WHERE id = ?", (e["id"],))
        self.assertEqual(len(self.daten()["fein"]["delta_fehler"]), 1)

    def test_ein_altes_ereignis_ohne_delta_feld_zaehlt_auch(self):
        t = gescheiterte_aenderung(self.con, self.pid)
        e = planer.letzter_entwurf(self.con, self.pid, t[2])
        assert e is not None
        with db.schreiben(self.con):
            self.con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?", (json.dumps(
                {"thema": t[2], "fassung": 2, "fehler": ["verwerfen 1: grund länger als 1000 Zeichen"]}, ensure_ascii=False), e["id"]))
        self.assertEqual(self.daten()["fein"]["delta_fehler"][0]["gruende"], [{"art": "lang", "x": {"n": 1000}}])

    def test_alte_fassung_und_erster_plan_stehen_nicht_da(self):
        t = gescheiterte_aenderung(self.con, self.pid)
        themen.bearbeiten(self.con, self.pid, kern.ENTWICKLER, t[2], "Noch eine Fassung.")
        self.assertEqual(self.daten()["fein"]["delta_fehler"], [])
        planer.entwurf_eintragen(self.con, self.pid, t[3], 1, "kein JSON")        # nie geplant: keine Konzeptänderung
        self.assertEqual(self.daten()["fein"]["delta_fehler"], [])

    def test_jede_art_hat_texte_in_beiden_sprachen(self):
        from amw import planfunde, workbench
        arten = {a for _, a in planfunde._ARTEN} | {"sonst"}
        for s in ("de", "en"):
            self.assertEqual([a for a in arten if "pjw_fx_" + a not in workbench.texte(s)], [])


class AbnahmeDran(Grund):
    def schritt(self, name, d=None):
        return next(s for s in (d or self.daten())["schritte"] if s["schritt"] == name)

    def test_abschluss_dran_umsetzung_nicht_mehr(self):
        """A2080 (7): alle Pakete fertig, M1 wartet auf Abnahme – die Leiste sagt es (vorher ○ grau, Umsetzung ● bei 5 von 5)."""
        demo(self.con, self.pid, "abschluss")
        d = self.daten()
        self.assertEqual((self.schritt("abschluss", d)["zustand"], self.schritt("abschluss", d)["bei_dir"]), ("dran", True))
        self.assertNotEqual(self.schritt("umsetzung", d)["zustand"], "dran")
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, abschluss_freigabe="co+lead", co_entwickler="CC1")
        x = self.schritt("abschluss")
        self.assertEqual((x["zustand"], x["bei_dir"]), ("dran", False))

    def test_umsetzung_bleibt_dran_solange_ein_paket_offen_ist(self):
        from amw import feinplanung
        demo(self.con, self.pid, "fein")
        m1 = self.con.execute("SELECT id FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()[0]
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, m1)
        self.assertEqual(self.schritt("umsetzung")["zustand"], "dran")
        self.assertEqual(self.schritt("abschluss")["zustand"], "offen")


def wartende_aenderung(con, pid):
    """A2080: M1 läuft, das Thema „Speichern und Laden“ wurde geändert, der Planer schlägt einen neuen Meilenstein vor."""
    from amw import feinplanung, planer_delta
    t = demo(con, pid, "fein")
    m1 = con.execute("SELECT id FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()[0]
    feinplanung.plan_starten(con, pid, kern.ENTWICKLER, m1)
    for (aid,) in con.execute("SELECT id FROM aufgabe WHERE titel IN ('Speichern und Laden', 'Tests für Speichern')").fetchall():
        themen.verweise_setzen(con, pid, "TL", aid, [f"TH{t[2]}"])
    themen.bearbeiten(con, pid, kern.ENTWICKLER, t[2], "Die Welt bleibt erhalten, auch nach einem Neustart, mit drei Speicherplätzen.")
    plan = {"meilensteine": [{"schluessel": "M9", "titel": "Drei Speicherplätze", "endet_mit": "vorfuehrung"}],
            "pakete": [{"schluessel": "P1", "meilenstein": "M9", "titel": "Speicherplatz wählen", "auftrag": "Drei Plätze anbieten.", "groesse": "S",
                        "art": "mechanisch", "ausfuehrung": "p", "fertig_quelle": "commit", "abnahme_befehl": "python -m unittest tests.test_platz",
                        "bereiche": "scripts/speicher.gd"}]}
    planer.entwurf_eintragen(con, pid, t[2], 2, plan, modell="sonnet", usd=0.05, delta=planer_delta.kontext(con, pid, t[2]))
    return t


class AenderungStarten(Grund):
    def test_altfall_macht_feinplanung_dran(self):
        from amw import delta_start
        t = wartende_aenderung(self.con, self.pid)
        d = self.daten()["fein"]["delta"][0]
        self.assertEqual((d["startet"], d["neuer_ms"], d["wer"]), (True, True, [kern.entwickler_name(self.con, self.pid)]))
        with mock.patch.object(delta_start, "nach_dem_ja", return_value=None):
            planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, t[2])
        d = self.daten()
        m = next(x for x in d["fein"]["meilensteine"] if x["titel"] == "Drei Speicherplätze")
        self.assertEqual((m["delta_start"]["thema"], m["delta_start"]["fehler"]), (t[2], None))
        fein = next(s for s in d["schritte"] if s["schritt"] == "fein")
        self.assertEqual((fein["zustand"], fein["bei_dir"], d["dran"]), ("dran", True, "fein"))


class ZielDerAenderung(Grund):
    def test_bestehend_ist_die_projektnummer(self):
        """A2091: die Karte suchte die interne Id – „in Mnull“ oder ein falscher Meilenstein."""
        with db.schreiben(self.con):
            anderes = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, anderes, "TLQ", rolle="lead")
        fremd = planung.bogen_neu(self.con, anderes, "TLQ", "Fremder Meilenstein")          # gleiche Nummer, Id 1
        m1, m2 = (planung.bogen_neu(self.con, self.pid, "TL", x) for x in ("Eigener erster", "Eigener zweiter"))
        nr = {b: self.con.execute("SELECT nr FROM bogen WHERE id = ?", (b,)).fetchone()[0] for b in (fremd, m1, m2)}
        self.assertEqual((nr[fremd], nr[m1], nr[m2]), (1, 1, 2))
        self.assertNotIn(m2, (nr[m1], nr[m2]))                                              # Id und Nummer verschieden
        paket = {"schluessel": "P1", "meilenstein": "M1", "titel": "Neu", "ausfuehrung": "p", "groesse": "S", "nach": []}
        for n, titel in ((1, "Eigener erster"), (2, "Eigener zweiter")):
            x = projektweg_seite._entwurf_karten(self.con, self.pid, {"meilensteine": [{"schluessel": "M1", "bestehend": n}], "pakete": [paket]})
            self.assertEqual(x["ziele"], [{"nr": n, "titel": titel, "neu": False}])


class KonzeptWiederOffen(Grund):
    """A2091 (10): wird das Konzept wieder offen, zeigt die Leiste weiter, was läuft."""
    def zeichen(self):
        d = self.daten()
        return d["dran"], {s["schritt"]: s["zeichen"] for s in d["schritte"]}, {s["schritt"]: s["bei_dir"] for s in d["schritte"]}

    def test_laufende_pakete_bleiben_dran(self):
        from amw import feinplanung, planansicht
        t = demo(self.con, self.pid, "fein")
        m1 = self.con.execute("SELECT id FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()[0]
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, m1)
        vorher = self.zeichen()[1]
        themen.pflegen(self.con, self.pid, "CC1", t[3], "Neue Fassung, wartet auf das Ja.")
        dran, z, dir_ = self.zeichen()
        self.assertEqual(dran, "konzept")                                                   # wer dran ist, bleibt
        self.assertEqual((vorher["grob"], z["konzept"], z["grob"], z["umsetzung"], z["abschluss"]), ("✓", "●", "✓", "●", "○"))
        self.assertEqual((dir_["konzept"], dir_["grob"], dir_["umsetzung"]), (True, False, False))
        m3 = self.con.execute("SELECT id FROM bogen WHERE titel = 'Spieler greift ein'").fetchone()[0]
        planansicht.zurueck(self.con, self.pid, kern.ENTWICKLER, m3, "grob", "nochmal")     # ein Meilenstein ohne Ja: Grobplanung ist nicht ✓
        self.assertEqual(self.zeichen()[1]["grob"], "○")
        with self.assertRaises(kern.AmwFehler):                                             # die Regel selbst bleibt: erst das Konzept
            projektweg.uebergang_pruefen(self.con, self.pid, "umsetzung")

    def test_ohne_laufende_pakete_bleibt_es_offen(self):
        t = demo(self.con, self.pid, "fein")
        themen.pflegen(self.con, self.pid, "CC1", t[3], "Neue Fassung, wartet auf das Ja.")
        self.assertEqual([self.zeichen()[1][s] for s in ("grob", "umsetzung")], ["○", "○"])


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
        namen = self.tab.js("[...document.querySelectorAll('#pjw-fenster .pjw-felder > span:nth-child(odd)')].map(x => x.textContent)")
        self.assertEqual(namen[:3], ["Ziel", "Fertig, wenn", "Themen"])                   # A2072 (CCamwTL #32485): nicht „Ziel und …“
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
        planer_fortschritt.melden(self.con, self.pid, lid, art="grobplaner", modell="opus", was="Thema 2 von 4", nr=2, gesamt=4, usd=0.3,
                                  ausloeser=kern.ENTWICKLER, anlass="klick")                 # A2078: nur der eigene Klick öffnet das Fenster
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



class SeiteReste(Rundgang):
    """A2091: Konzept wieder offen bei laufenden Paketen; Handy ohne Seitwärts-Scrollen und mit Verlauf im geöffneten Schritt."""
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        for ziel in (grobplan, planer):
            p = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
            p.start()
            self.addCleanup(p.stop)
        from amw import feinplanung, planansicht
        t = demo(self.con, self.pid, "fein")
        m1, m3 = (self.con.execute("SELECT id FROM bogen WHERE titel = ?", (x,)).fetchone()[0] for x in ("Welt sichtbar", "Spieler greift ein"))
        feinplanung.plan_starten(self.con, self.pid, kern.ENTWICKLER, m1)
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET titel = ? WHERE id = ?", ("Spieler greift ein: Gegenstände stellen, Bewohner reagieren, Möbel und Pflanzen verschieben", m3))
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, m3, "grob")               # der neue Titel braucht das Ja noch einmal
        planung.schritt_setzen(self.con, self.pid, "TL", titel="Gegenstand stellen", bogen_id=m3, groesse="S", art="mechanisch", agent="CC1")
        themen.pflegen(self.con, self.pid, "CC1", t[3], "Neue Fassung, wartet auf das Ja.")

    def test_leiste(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        z = self.tab.js("[...document.querySelectorAll('.pjw-schritt')].map(x => x.dataset.schritt + x.querySelector('.pjw-zeichen').innerText + x.classList.contains('offen-z'))")
        self.assertEqual((z[0], z[1], z[3]), ("konzept●false", "grob✓false", "umsetzung●false"))
        self.assertIn("gewaehlt", self.tab.js("document.querySelector('.pjw-schritt[data-schritt=konzept]').className"))

    def test_handy_verlauf_im_schritt_und_kein_seitwaerts(self):
        self.groesse("handy")
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        self.tab.js("zustand.pwSicht = 2; zustand.pwOffen = true; zeige('projektweg', true)")
        self.warten("document.querySelectorAll('.pjw-chips .pjw-chip').length === 2")
        self.assertFalse(self.tab.js("document.querySelector('.pjw-chips').getBoundingClientRect().right > innerWidth"
                                     " || [...document.querySelectorAll('.pjw-chips .pjw-chip')].some(x => x.getBoundingClientRect().right > innerWidth)"))
        self.assertTrue(self.tab.js("(v => v.offsetParent !== null && v.getBoundingClientRect().top >= document.querySelector('.pjw-ansicht').getBoundingClientRect().bottom)"
                                    "(document.querySelector('.pjw-verlauf-handy'))"))
        self.assertIn("Verlauf", self.tab.js("document.querySelector('.pjw-verlauf-handy summary').innerText"))

    def test_rundgang(self):
        for g, th in (("pc", "hell"), ("pc", "dunkel"), ("handy", "hell"), ("handy", "dunkel")):
            fehler = self.besuchen("projektweg", "projektweg-reste", bereit="document.querySelector('.pjw-schritt')",
                                   tun="zustand.pwSicht = 2; zustand.pwOffen = true; zeige('projektweg', true)",
                                   danach="document.querySelector('.pjw-chips')", g=g, t=th)
            self.assertEqual(fehler, [], f"{g} {th}")


class SeiteUebernahme(Rundgang):
    """A2075: Übernahme im Verlauf und der ganze Auftrag im Seitenfenster."""
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        for ziel in (grobplan, planer):
            p = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
            p.start()
            self.addCleanup(p.stop)
        _, _, self.neu = bestand(self.con, self.pid)
        grobplan.uebernehmen(self.con, self.pid)
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET auftrag = ? WHERE bogen_id = ?", ("Ein Satz im Auftrag. " * 60 + "Das ist das Ende.", self.neu))

    def test_verlauf_und_mehr(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        self.tab.js("zustand.pwSicht = 2; zustand.pwOffen = true; zeige('projektweg', true)")
        self.warten("document.querySelector('.pjw-paket')")
        self.assertNotIn("Bestand übernommen", self.tab.js("document.querySelector('.pjw-verlauf').innerText"))
        self.tab.js("document.querySelector('.pjw-paket').click(); 1")
        self.warten("document.querySelector('#pjw-fenster .pjw-mehr')")
        self.assertNotIn("Das ist das Ende.", self.tab.js("document.querySelector('#pjw-fenster').innerText"))
        self.tab.js("document.querySelector('#pjw-fenster .pjw-mehr').click(); 1")
        self.warten("document.querySelector('#pjw-fenster').innerText.includes('Das ist das Ende.')")
        self.assertFalse(self.tab.js("!!document.querySelector('#pjw-fenster .pjw-mehr')"))
        self.tab.js("zustand.pwFenster = null; document.getElementById('pjw-fenster').remove(); zustand.pwSicht = 1; zeige('projektweg', true)")
        self.warten("document.querySelector('.pjw-verlauf').innerText.includes('Bestand übernommen: 2 Meilensteine')")

    def test_rundgang(self):
        for g, th in (("pc", "hell"), ("handy", "dunkel")):
            for schritt in (1, 2):
                fehler = self.besuchen("projektweg", f"projektweg-uebernahme-{schritt}", bereit="document.querySelector('.pjw-schritt')",
                                       tun=f"zustand.pwSicht = {schritt}; zustand.pwOffen = true; zeige('projektweg', true)",
                                       danach="document.querySelector('.pjw-ansicht')", g=g, t=th)
                self.assertEqual(fehler, [], f"{g} {th}")


class SeiteLaeuft(Rundgang):
    """A2078: Lauf eines Agenten = Zeile am Schritt, kein Fenster; eigener Klick = Fenster, auch nach Neuladen; alter Eintrag = kein Fenster."""
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        for ziel in (grobplan, planer):
            p = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
            p.start()
            self.addCleanup(p.stop)
        self.t = demo(self.con, self.pid, "grob1")

    def melden(self, **kw):
        with db.schreiben(self.con):
            lid = db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="TL", beschreibung="x", status="laeuft", angemeldet_utc=db.jetzt(), start_utc=db.jetzt())
        planer_fortschritt.melden(self.con, self.pid, lid, modell="opus", was="Thema wird gelesen", sofort=True, **kw)

    def test_agent_zeile_klick_fenster_alter_eintrag(self):
        self.melden(art="gegenlesen", thema=self.t[2], fassung=8, ausloeser="TL")
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        self.tab.js("zustand.pwSicht = 0; zustand.pwOffen = true; zeige('projektweg', true)")
        self.warten("document.querySelector('.pjw-laeuft')")
        zeile = self.tab.js("document.querySelector('.pjw-laeuft').innerText")
        self.assertIn(f"Gegenleser prüft TH{self.t[2]} Fassung 8", zeile)
        self.assertIn("TL (Lead)", zeile)
        self.assertNotIn("opus", zeile)
        self.assertFalse(self.tab.js("!!document.querySelector('#pjw-ueber')"))
        self.tab.js("document.querySelector('.pjw-laeuft').click(); 1")
        self.warten("document.querySelector('#pjw-fenster') && document.querySelector('#pjw-fenster').innerText.includes('opus')")
        self.tab.js("zustand.pwFenster = null; document.getElementById('pjw-fenster').remove(); 1")
        self.melden(art="grobplaner", fassung=2)                                       # alter Eintrag ohne Auslöser
        self.tab.js("zeige('projektweg', true)")
        self.warten("zustand.pwDaten.laeufe.length === 2")
        self.assertFalse(self.tab.js("!!document.querySelector('#pjw-ueber')"))
        self.melden(art="grobplaner", fassung=2, ausloeser=kern.ENTWICKLER, anlass="klick")
        self.tab.js("zeige('projektweg', true)")
        self.warten("document.querySelector('#pjw-ueber')")
        self.assertIn("Grob-Planer plant Fassung 2", self.tab.js("document.querySelector('#pjw-ueber').innerText"))
        self.oeffnen("projektweg", "document.querySelector('#pjw-ueber .pjw-lauf')")    # wieder geöffnet: noch da, solange er läuft

    def test_rundgang(self):
        self.melden(art="gegenlesen", thema=self.t[2], fassung=8, ausloeser="TL")
        for g, th in (("pc", "hell"), ("handy", "dunkel")):
            fehler = self.besuchen("projektweg", "projektweg-laeuft", bereit="document.querySelector('.pjw-schritt')",
                                   tun="zustand.pwSicht = 0; zustand.pwOffen = true; zeige('projektweg', true)",
                                   danach="document.querySelector('.pjw-laeuft')", g=g, t=th)
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
        knopf = "[...document.querySelectorAll('.pjw-ab-karte button')].find(b => b.textContent === t('pjw_a_starten'))"
        self.warten(knopf)
        self.assertIn(self.tab.js("t('pjw_a_ohne')"), self.tab.js("document.querySelector('.pjw-ab-karte').innerText"))
        self.tab.js(knopf + ".click()")
        self.warten("document.querySelector('.pjw-ab-karte') && document.querySelector('.pjw-ab-karte').innerText.includes(t('pjw_a_laeuft'))")
        self.assertFalse(self.tab.js(f"!!({knopf})"))


class SeitePruefungErneut(Rundgang):
    """A2072 (P633): die Prüfung ging nicht – die Karte nennt den Grund in Menschensprache, ein nicht eingestellter Gesamttest hat
    keinen Haken, und der Klick auf „Prüfung erneut starten“ startet sie wirklich (danach „läuft“)."""
    FEHLER = "kein JSON: Expecting property name enclosed in double quotes: line 1 column 2 (char 1)"

    def daten(self):
        from amw import abschluss, abschlusslage, schalter
        kern.agent_neu(self.con, self.pid, "CC1")
        self.gestartet = []
        for ziel, f in ((grobplan, lambda *a, **k: 4711), (planer, lambda *a, **k: 4711),
                        (abschluss, lambda pid, bid, stand: self.gestartet.append(bid) or 4711)):
            p = mock.patch.object(ziel, "STARTER", f)
            p.start()
            self.addCleanup(p.stop)
        demo(self.con, self.pid, "abschluss-ohne")
        self.m1 = self.con.execute("SELECT id FROM bogen WHERE titel = 'Welt sichtbar'").fetchone()[0]
        with db.schreiben(self.con):
            schalter._setzen(self.con, self.pid, "an")
            b = self.con.execute("SELECT * FROM bogen WHERE id = ?", (self.m1,)).fetchone()
            abschluss._ereignis(self.con, self.pid, abschluss.ERGEBNIS, bogen=self.m1, stand=abschlusslage.stand(self.con, b),
                                test={"befehl": None, "lauf": None, "rc": None}, themen=[], vorfuehrung=[], ok=False, angelegt={},
                                fehler=self.FEHLER, roh="{nicht: json}")
        p = mock.patch.dict(os.environ, {"AMW_PLANER_AUS": ""})
        p.start()
        self.addCleanup(p.stop)

    KNOPF = "[...document.querySelectorAll('.pjw-ab-karte button')].find(b => b.textContent === t('pjw_a_erneut'))"     # A2082: mit Lead kein Hauptknopf oben

    def test_grund_und_klick(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        self.tab.js("zustand.pwSicht = 4; zeige('projektweg', true)")
        self.warten(self.KNOPF)
        text = self.tab.js("document.querySelector('.pjw-ab-karte').innerText")
        self.assertIn("Prüfung ging nicht: Antwort des Prüfers nicht lesbar", text)
        for wort in ("JSON", "Expecting", "column", "(char"):
            self.assertNotIn(wort, text)
        erste = "document.querySelector('.pjw-pruefung > div > span')"
        self.assertEqual(self.tab.js(erste + ".textContent"), "–")                       # nicht gelaufen: kein Haken
        self.assertNotIn("pjw-ok", self.tab.js(erste + ".className"))
        self.tab.js(self.KNOPF + ".click()")
        self.warten("document.querySelector('.pjw-ab-karte') && document.querySelector('.pjw-ab-karte').innerText.includes(t('pjw_a_laeuft'))")
        self.assertFalse(self.tab.js(f"!!({self.KNOPF})"))
        self.assertEqual(self.gestartet, [self.m1])

    def test_rundgang(self):
        for g, th in (("pc", "hell"), ("handy", "dunkel")):
            fehler = self.besuchen("projektweg", "projektweg-pruefung-erneut", bereit="document.querySelector('.pjw-schritt')",
                                   tun="zustand.pwSicht = 4; zustand.pwOffen = true; zeige('projektweg', true)",
                                   danach="document.querySelector('.pjw-pruefung')", g=g, t=th)
            self.assertEqual(fehler, [], f"{g} {th}")


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


class SeiteDeltaFehler(Rundgang):
    """A2076: eine gescheiterte Konzeptänderung auf der Seite – Leiste, Grund, Hinweis, „Überarbeiten lassen“."""
    def daten(self):
        from amw import schalter
        kern.agent_neu(self.con, self.pid, "CC1")
        u = mock.patch.dict(os.environ)
        u.start()
        self.addCleanup(u.stop)
        os.environ.pop("AMW_PLANER_AUS", None)
        for ziel in (grobplan, planer):
            p = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
            p.start()
            self.addCleanup(p.stop)
        with db.schreiben(self.con):
            schalter._setzen(self.con, self.pid, "an")
        self.t = gescheiterte_aenderung(self.con, self.pid)

    def test_grund_und_ueberarbeiten_klicken(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        leiste = self.tab.js("document.querySelector('.pjw-schritt[data-schritt=fein] .pjw-wert').innerText")
        self.assertIn("Plan passte nicht", leiste)
        self.assertNotIn("wartet auf dich", leiste)                                         # B2938: der Lead klärt es
        self.tab.js("zustand.pwSicht = 2; zustand.pwOffen = true; zeige('projektweg', true)")
        self.warten("document.querySelector('.pjw-delta-fehler li')")
        text = self.tab.js("document.querySelector('.pjw-delta-fehler').innerText")
        self.assertIn("wird gerade gebaut", text)
        for wort in ("nacharbeit", "Schema", "verwerfen", "zu_ende"):
            self.assertNotIn(wort, text)
        self.assertIn("klärt es", text)
        self.assertEqual(self.tab.js("document.querySelectorAll('.pjw-delta-fehler .knopf.haupt').length"), 0)   # normaler Knopf
        self.tab.js("document.querySelector('.pjw-delta-fehler textarea').value = 'Speicherplätze erst danach'; "
                    "[...document.querySelectorAll('.pjw-delta-fehler button')].find(b => b.textContent === t('pjw_ueberarbeiten')).click(); 1")
        self.warten("!document.querySelector('.pjw-delta-fehler')")
        art = [r[0] for r in self.con.execute("SELECT art FROM plan_ereignis ORDER BY id DESC LIMIT 6")]
        self.assertIn("plan_hinweis", art)
        self.assertTrue(planer.laeuft(self.con, self.pid, self.t[2]))

    def test_rundgang(self):
        for g, th in (("pc", "hell"), ("handy", "dunkel")):
            fehler = self.besuchen("projektweg", "projektweg-delta-fehler", bereit="document.querySelector('.pjw-schritt')",
                                   tun="zustand.pwSicht = 2; zustand.pwOffen = true; zeige('projektweg', true)",
                                   danach="document.querySelector('.pjw-delta-fehler')", g=g, t=th)
            self.assertEqual(fehler, [], f"{g} {th}")


class SeiteAenderungStarten(Rundgang):
    """A2080: ein Klick gibt die Änderung frei und startet – und der Altfall holt es nach."""
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        for ziel in (grobplan, planer):
            p = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
            p.start()
            self.addCleanup(p.stop)
        self.t = wartende_aenderung(self.con, self.pid)

    def status(self):
        r = self.con.execute("SELECT status FROM bogen WHERE titel = 'Drei Speicherplätze'").fetchone()
        return r and r[0]

    def knopf(self, anfang):
        return f"[...document.querySelectorAll('.pjw-ansicht button')].find(b => b.textContent.startsWith('{anfang}'))"

    def test_klick_gibt_frei_und_startet(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        self.tab.js("zustand.pwSicht = 2; zustand.pwOffen = true; zeige('projektweg', true)")
        self.warten(self.knopf("Änderung TH"))
        self.assertIn("freigeben und starten (1 Paket, neuer Meilenstein)", self.tab.js(self.knopf("Änderung TH") + ".textContent"))
        karte = self.tab.js("document.querySelector('.pjw-delta').innerText")
        for teil in ("Das Ja gibt:", "in neuem Meilenstein", "1 Paket"):
            self.assertIn(teil, karte)
        self.assertNotIn("1 Pakete", karte + self.tab.js("document.querySelector('.pjw-schritt[data-schritt=fein]').innerText"))
        self.tab.js(self.knopf("Änderung TH") + ".click(); 1")
        self.warten("!document.querySelector('.pjw-delta')")
        self.assertEqual(self.status(), "aktiv")

    def test_altfall_klick_holt_es_nach(self):
        from amw import delta_start
        with mock.patch.object(delta_start, "nach_dem_ja", return_value=None):
            planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.t[2])
        self.assertEqual(self.status(), "geplant")
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        self.tab.js("zustand.pwSicht = 2; zustand.pwOffen = true; zeige('projektweg', true)")
        self.warten("[...document.querySelectorAll('.pjw-ansicht button')].some(b => b.textContent.includes('aus Änderung TH'))")
        self.assertEqual(self.tab.js("document.querySelectorAll('.pjw-ansicht .knopf.haupt').length"), 1)
        self.tab.js("[...document.querySelectorAll('.pjw-ansicht button')].find(b => b.textContent.includes('aus Änderung TH')).click(); 1")
        self.warten("![...document.querySelectorAll('.pjw-ansicht button')].some(b => b.textContent.includes('aus Änderung TH'))")
        self.assertEqual(self.status(), "aktiv")

    def test_rundgang(self):
        for g, th in (("pc", "hell"), ("handy", "dunkel")):
            fehler = self.besuchen("projektweg", "projektweg-aenderung-starten", bereit="document.querySelector('.pjw-schritt')",
                                   tun="zustand.pwSicht = 2; zustand.pwOffen = true; zeige('projektweg', true)",
                                   danach="document.querySelector('.pjw-delta')", g=g, t=th)
            self.assertEqual(fehler, [], f"{g} {th}")


class SeiteTeilweise(Rundgang):
    """A2085: bricht eine Änderung beim Anwenden ab, sagt die Karte, was geändert und was offen ist – der Lead klärt es."""
    def daten(self):
        kern.agent_neu(self.con, self.pid, "CC1")
        for ziel in (grobplan, planer):
            p = mock.patch.object(ziel, "STARTER", lambda *a, **k: 4711)
            p.start()
            self.addCleanup(p.stop)
        self.t = gescheiterte_aenderung(self.con, self.pid)
        from amw import planer_delta
        ids = [r[0] for r in self.con.execute("SELECT id FROM aufgabe WHERE titel IN ('Speichern und Laden', 'Tests für Speichern') ORDER BY id")]
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'wartet', begonnen_utc = NULL WHERE id IN (?, ?)", ids)
        plan = {"meilensteine": [], "pakete": [], "aendern": [{"paket": f"A{a}", "titel": f"{t} mit drei Plätzen", "auftrag": "Drei Plätze.", "grund": "Plätze"}
                                                             for a, t in zip(ids, ("Speichern und Laden", "Tests für Speichern"))]}
        planer.entwurf_eintragen(self.con, self.pid, self.t[2], 2, plan, modell="sonnet", usd=0.05, delta=planer_delta.kontext(self.con, self.pid, self.t[2]))
        echt, n = planung.schritt_setzen, [0]

        def setzen(*a, **k):
            n[0] += 1
            if n[0] == 2:
                raise kern.AmwFehler("Platte voll")
            return echt(*a, **k)
        with mock.patch.object(planung, "schritt_setzen", setzen):
            with self.assertRaises(kern.AmwFehler):
                planer.uebernehmen(self.con, self.pid, kern.ENTWICKLER, self.t[2])

    def test_karte_sagt_was_offen_ist(self):
        self.oeffnen("projektweg", "document.querySelector('.pjw-schritt')")
        self.assertIn("teilweise umgesetzt", self.tab.js("document.querySelectorAll('.pjw-schritt .pjw-wert')[2].innerText"))   # A2086 (4)
        self.assertNotIn("passte nicht", self.tab.js("document.querySelector('.pjw-schritte').innerText"))
        leer = "{ ...zustand.pwDaten, fein: { ...zustand.pwDaten.fein, meilensteine: [], delta: [], delta_fehler: [], naechster: %s } }"
        self.assertEqual([self.tab.js(f"pwWert({leer % n}, 2)") for n in ("{ nr: 5 }", "null")], ["als Nächstes M5", "–"])   # A2086 (8)
        self.tab.js("zustand.pwSicht = 2; zustand.pwOffen = true; zeige('projektweg', true)")
        self.warten("document.querySelector('.pjw-delta-fehler li')")
        text = self.tab.js("document.querySelector('.pjw-delta-fehler').innerText")
        for teil in ("nur teilweise umgesetzt", "Schon geändert: „Speichern und Laden mit drei Plätzen“.", "Noch offen: „Tests für Speichern“.", "Der Lead weiß Bescheid"):
            self.assertIn(teil, text)

    def test_rundgang(self):
        for g, th in (("pc", "hell"), ("pc", "dunkel"), ("handy", "hell"), ("handy", "dunkel")):
            fehler = self.besuchen("projektweg", "projektweg-teilweise", bereit="document.querySelector('.pjw-schritt')",
                                   tun="zustand.pwSicht = 2; zustand.pwOffen = true; zeige('projektweg', true)",
                                   danach="document.querySelector('.pjw-delta-fehler')", g=g, t=th)
            self.assertEqual(fehler, [], f"{g} {th}")


if __name__ == "__main__":
    unittest.main()
