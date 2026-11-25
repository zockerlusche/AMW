"""A2139: passt an der Antwort der Abschlussprüfung nur die vorgeschlagene Nacharbeit nicht, gilt das Urteil trotzdem (M16, Ereignis 8853:
alles verworfen, weil zwei p-Pakete Testdateien in den Bereichen hatten). Der Weg ist der echte: ausfuehren → pruefer → arbeiter.laufen
(Attrappe, TEXT wie von claude -p) → eintragen. Dazu die eine Regel für Planer, Feinplaner und Prüfer: ein p-Paket mit Testdatei in den
Bereichen ist vom Typ test-schreiben."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
from unittest import mock

from amw import abschluss, abschlusslage, arbeitspaket, feinplanung, planer, planung, tore
from tests import test_a2029_abschluss

VORBEHALT = "Der Wechsel des Firmenkontos ist nur für einen Anbieter gezeigt"
EINS = "Meilenstein 1: 1 Nacharbeits-Paket passt nicht und ist nicht angelegt"


class Grund(test_a2029_abschluss.Grund):
    def p(self, schluessel, bereiche, titel, **mehr):
        return {"schluessel": schluessel, "meilenstein": "M1", "thema": f"TH{self.t1}", "titel": titel, "auftrag": f"Auftrag zu {titel}.", "groesse": "S",
                "art": "fehlersuche", "ausfuehrung": "p", "fertig_quelle": "commit", "abnahme_befehl": "python -m unittest tests.test_login",
                "bereiche": bereiche, "pakettyp": "normal", **mehr}

    def antwort(self, *pakete):
        u = {**self.urteil((False, True), list(pakete)), "vorbehalte": [VORBEHALT]}
        return "Ich habe den Code gelesen. Mein Urteil:\n\n```json\n" + json.dumps(u, ensure_ascii=False, indent=1) + "\n```\n"

    def laufen(self, *antworten):
        self.auftraege = []

        def attrappe(_p, auftrag, *_a, **_k):
            self.auftraege.append(auftrag)
            return {"rc": 0, "abweichungen": [], "ergebnis": {"result": antworten[len(self.auftraege) - 1], "total_cost_usd": 1.52}}
        self.runde()
        with mock.patch("amw.arbeiter.laufen", attrappe):
            return abschluss.ausfuehren(self.con, self.pid, self.m, self.stand())

    def an_lead(self):
        return [(r["kurz"], r["text"]) for r in self.con.execute(
            "SELECT n.kurz, n.text FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = 'TL' AND n.von = 'AMW' AND n.art = 'meldung' ORDER BY n.id")]


class FallM16(Grund):
    def test_testdatei_in_den_bereichen_zwei_pakete(self):
        e = self.laufen(self.antwort(self.p("N1", "app/login.py, tests/test_login.py", "Firmenkonto anbinden"),
                                     self.p("N2", "app/sitzung.py, tests/test_sitzung.py", "Sitzung beim Abmelden beenden")))
        self.assertEqual(len(self.auftraege), 1)                                              # kein zweiter bezahlter Lauf
        self.assertIsNone(e.get("fehler"))
        self.assertEqual(e["themen"][0]["zustand"], "nicht_erfuellt")
        self.assertIn({"art": "pruefer", "text": VORBEHALT}, e["vorbehalte"])
        self.assertEqual(e["vorfuehrung"], ["Seite öffnen", "mit Firmenkonto anmelden"])
        self.assertEqual(self.offen(), ["Firmenkonto anbinden", "Sitzung beim Abmelden beenden"])
        self.assertEqual([arbeitspaket.lesen(self.con, int(a[1:]))["pakettyp"] for a in e["angelegt"].values()], ["test-schreiben"] * 2)
        self.assertNotIn("unpassend", e)
        self.assertIn("Meilenstein 1: Nacharbeit – 2 Paket(e) gestartet", [k for k, _ in self.an_lead()])


class Unpassend(Grund):
    def test_wirklich_gesperrt_geht_an_den_lead(self):
        e = self.laufen(self.antwort(self.p("N1", "amw/kern.py, tests/test_login.py", "Kern ändern"), self.p("N2", "app/sitzung.py", "Sitzung beenden")))
        self.assertEqual(len(self.auftraege), 1)
        self.assertIsNone(e.get("fehler"))
        self.assertEqual(self.offen(), ["Sitzung beenden"])
        self.assertEqual([(x["titel"], x["auftrag"]) for x in e["unpassend"]], [("Kern ändern", "Auftrag zu Kern ändern.")])
        self.assertIn("gesperrte Pfade (amw/kern.py)", e["unpassend"][0]["gruende"][0])       # nur der wirklich gesperrte, nicht die Testdatei
        text = dict(self.an_lead())[EINS]
        for teil in ("Kern ändern", "Auftrag zu Kern ändern.", "gesperrte Pfade (amw/kern.py)", "Das Urteil der Prüfung gilt", "amw bogen nacharbeit M1"):
            self.assertIn(teil, text)
        bericht = tore.bericht_text(self.con, self.pid, self.m)
        self.assertIn(VORBEHALT, bericht)
        self.assertIn("1. Seite öffnen", bericht)
        self.assertIn("Nicht angelegt, beim Lead: „Kern ändern“", bericht)

    def test_keins_passt_bleibt_nicht_haengen(self):
        e = self.laufen(self.antwort(self.p("N1", "amw/kern.py", "Kern ändern")))
        self.assertEqual((e["angelegt"], e["ok"], e.get("fehler")), ({}, False, None))
        self.assertEqual(self.offen(), [])
        self.assertEqual(self.runde(), [(self.m, "bereit")])                                  # gemeldet, nicht still „Nacharbeit läuft“
        b = planung.bogen_zeile(self.con, self.pid, self.m)
        self.assertEqual(abschlusslage.lage(self.con, self.pid, b), "nicht_erfuellt")
        self.assertIn(EINS, dict(self.an_lead()))

    def test_nachfolger_eines_unpassenden_wird_nicht_allein_gestartet(self):
        e = self.laufen(self.antwort(self.p("N3", "app/c.py", "Anzeige dazu", nach=["N2"]), self.p("N2", "app/b.py", "Auswertung", nach=["N1"]),
                                     self.p("N1", "amw/kern.py", "Kern ändern"), self.p("N5", "app/e.py", "Hinweis zeigen", nach=["N4"]), self.p("N4", "app/d.py", "Abmelden")))
        self.assertEqual(sorted(self.offen()), ["Abmelden", "Hinweis zeigen"])                # ein Vorgänger darf später in der Liste stehen
        self.assertEqual(sorted(x["titel"] for x in e["unpassend"]), ["Anzeige dazu", "Auswertung", "Kern ändern"])
        self.assertIn("N1", " ".join(next(x for x in e["unpassend"] if x["titel"] == "Auswertung")["gruende"]))
        self.assertIn("Meilenstein 1: 3 Nacharbeits-Pakete passen nicht und sind nicht angelegt", dict(self.an_lead()))

    def test_gleiche_dateien_der_zweite_geht_an_den_lead(self):
        e = self.laufen(self.antwort(self.p("N1", "app/login.py", "Firmenkonto anbinden"), self.p("N2", "app/login.py", "Abmelden verbessern")))
        self.assertEqual(self.offen(), ["Firmenkonto anbinden"])
        self.assertIn("app/login.py", " ".join(e["unpassend"][0]["gruende"]))

    def test_unlesbares_paket_geht_als_text_mit(self):
        e = self.laufen(self.antwort("irgendwas", self.p("N2", "app/b.py", "Auswertung")))
        self.assertEqual(self.offen(), ["Auswertung"])
        self.assertIn("irgendwas", e["unpassend"][0]["auftrag"])

    def test_rot_und_keins_passt_ein_paket_fuer_den_test(self):
        self.runde()
        e = abschluss.eintragen(self.con, self.pid, self.m, self.stand(), {"lauf": 9, "rc": 1, "befehl": "x"},
                                json.dumps(self.urteil((False, True), [self.p("N1", "amw/kern.py", "Kern ändern")])))
        self.assertEqual(self.offen(), ["Gesamttest rot beheben (L9)"])
        self.assertEqual(e["themen"][0]["zustand"], "nicht_erfuellt")                          # das Urteil bleibt
        self.assertEqual([x["titel"] for x in e["unpassend"]], ["Kern ändern"])

    def test_grenze_unpassende_gehen_trotzdem_an_den_lead(self):
        with mock.patch.object(abschluss, "MAX_RUNDEN", 0):
            e = self.laufen(self.antwort(self.p("N1", "amw/kern.py", "Kern ändern"), self.p("N2", "app/b.py", "Auswertung")))
        self.assertEqual((e["angelegt"], e.get("grenze")), ({}, True))
        self.assertEqual([x["titel"] for x in e["unpassend"]], ["Kern ändern"])
        self.assertIn(EINS, dict(self.an_lead()))


class UrteilUngueltig(Grund):
    """Ist das Urteil selbst ungültig, bleibt alles wie bisher: der Fund geht einmal zurück, mit den Funden der Nacharbeit."""

    def test_geht_zurueck_mit_allen_funden(self):
        u = self.urteil((False, True), [self.p("N1", "amw/kern.py", "Kern ändern")])
        u["themen"] = u["themen"][:1]
        e = self.laufen(json.dumps(u), json.dumps(u))
        self.assertEqual(len(self.auftraege), 2)
        self.assertIn(f"nicht bewertet: TH{self.t2}", self.auftraege[1])
        self.assertIn("nacharbeit: Paket N1: Bereiche enthalten gesperrte Pfade", self.auftraege[1])
        self.assertIn("nicht bewertet", e["fehler"])
        self.assertEqual(self.offen(), [])


class TypTestSchreiben(Grund):
    """Eine Regel für Planer, Feinplaner und Prüfer (planer.pruefen)."""

    def typ(self, bereiche, **mehr):
        return feinplanung.pruefen({"pakete": [self.p("P1", bereiche, "Firmenkonto anbinden", **mehr)]}, self.con, self.pid, [self.m])["pakete"][0]["pakettyp"]

    def test_gesetzt_nur_wenn_eine_testdatei_dabei_ist(self):
        for bereiche, typ, soll in (("app/a.py, tests/test_a.py", "normal", "test-schreiben"), ("app/a.py, tests/test_a.py", None, "test-schreiben"),
                                    ("app/a.py; tests/neu/test_b.py", None, "test-schreiben"), ("app/a.py", "normal", "normal"), ("app/a.py", None, None),
                                    ("tests/test_a.py", "test-ergaenzen", "test-ergaenzen"), ("app/a.py, tests/test_a.py", "test-schreiben", "test-schreiben")):
            with self.subTest(bereiche=bereiche, typ=typ):
                self.assertEqual(self.typ(bereiche, pakettyp=typ), soll)

    def test_agent_bleibt_wie_angegeben(self):
        self.assertEqual(self.typ("app/a.py, tests/test_a.py", ausfuehrung="agent", interaktiv_grund="Erkundung"), "normal")

    def test_planer_dieselbe_regel(self):
        d = {"nichts_zu_bauen": False, "meilensteine": [{"schluessel": "M1", "bestehend": 1}],
             "pakete": [{k: v for k, v in self.p("P1", "app/a.py, tests/test_a.py", "Firmenkonto anbinden").items() if k != "thema"}]}
        self.assertEqual(planer.pruefen(d, self.con, self.pid)["pakete"][0]["pakettyp"], "test-schreiben")
        d["pakete"][0]["bereiche"] = "amw/kern.py, tests/test_a.py"
        with self.assertRaises(planer.PlanFehler) as x:
            planer.pruefen(d, self.con, self.pid)
        self.assertIn("gesperrte Pfade (amw/kern.py)", " ".join(x.exception.fehler))

    def test_der_text_sagt_es(self):
        for text in (planer.SCHEMA_TEXT, feinplanung.SCHEMA_TEXT, feinplanung.sperrliste_text(self.con, self.pid)):
            self.assertIn("setzt die AMW selbst auf test-schreiben", " ".join(text.split()))
