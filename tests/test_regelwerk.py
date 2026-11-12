"""Grund-Regelwerk: die mitgelieferte Vorlage (Deutsch/Englisch), ihre Übernahme beim Anlegen eines Projekts (Arbeitsregeln
mit Herkunft, Beschluss, Definition of Done, erste Version), Anzeige der Herkunft und die Umstellung auf Schema 23."""
import os
import tempfile
import unittest
from unittest import mock

from amw import assistent, db, kern, planung, regelwerk, wissen, workbench


class Vorlage(unittest.TestCase):
    def test_beide_sprachen_sind_vollstaendig_und_deckungsgleich(self):
        self.assertEqual(regelwerk.pruefen(), [])
        de = regelwerk.vorlage("de")
        self.assertEqual([r["nr"] for r in de["regeln"]], [f"G{i}" for i in range(1, 20)] + ["W1", "W2", "W3", "W4"])
        self.assertEqual(de["versionen"], {"schema": "MAJOR.MINOR.PATCH", "erste": "0.1.0"})
        self.assertEqual(regelwerk.vorlage("xx")["name"], de["name"])                       # unbekannte Sprache: Deutsch

    def test_erfahrung_nur_wo_sie_belegt_ist(self):
        """Eine „Erfahrung“ steht nur an den Regeln, deren Anlass belegt ist – alle anderen haben ein „Warum“ aus der Regel selbst."""
        de = regelwerk.vorlage("de")
        self.assertEqual([r["nr"] for r in de["regeln"] if "erfahrung" in r], ["G1", "G2", "G4", "G7", "G15", "G17", "G19", "W1", "W4"])
        self.assertEqual(sum("warum" in r for r in de["regeln"]), 14)

    def test_vorgabe_alle_grundregeln_takt_nur_fuer_chat_leads(self):
        self.assertEqual(regelwerk.vorgabe(), [f"G{i}" for i in range(1, 20)])
        self.assertEqual(regelwerk.vorgabe(lead_chat=True)[-1], "W4")

    def test_vorlage_nennt_keine_werkzeuge_und_keine_namen(self):
        for sprache in regelwerk.SPRACHEN:
            text = open(os.path.join(regelwerk.ORDNER, f"grundregelwerk.{sprache}.json"), encoding="utf-8").read().lower()
            for wort in ("claude", "cowork", "schedule"):
                self.assertNotIn(wort, text, sprache)


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(lambda: self.con.close())
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "Chef", rolle="lead", arbeitsweise="chat")
        kern.agent_neu(self.con, self.pid, "Maler")

    def regeln(self):
        return self.con.execute("SELECT nr, text, beleg, vorlage FROM regel WHERE projekt_id = ? AND ebene = 'arbeit' ORDER BY nr", (self.pid,)).fetchall()


class Uebernahme(Grund):
    def test_regeln_beschluss_und_definition_of_done(self):
        erg = regelwerk.uebernehmen(self.con, self.pid, kern.ENTWICKLER, lead_chat=True)
        regeln = self.regeln()
        self.assertEqual((erg["regeln"], len(regeln), erg["dod"]), (20, 20, True))
        self.assertEqual([r["vorlage"] for r in regeln], [f"G{i}/2" for i in range(1, 20)] + ["W4/2"])
        self.assertEqual({r["beleg"] for r in regeln}, {f"B{erg['beschluss']}"})                # Regeln brauchen einen Beschluss als Quelle
        self.assertTrue(regeln[0]["text"].startswith("Versionen. Jede Auslieferung bekommt eine Version"))
        b = self.con.execute("SELECT stichwort, regel, quelle FROM beschluss WHERE id = ?", (erg["beschluss"],)).fetchone()
        self.assertIn("Grund-Regelwerk 2 übernommen: G1, G2", b["regel"])
        self.assertEqual(planung.leitbild(self.con, self.pid)["dod"], regelwerk.vorlage("de")["dod"])
        with self.assertRaises(kern.AmwFehler):                                                 # nur beim Anlegen
            regelwerk.uebernehmen(self.con, self.pid, kern.ENTWICKLER)

    def test_auswahl_eigener_wortlaut_und_sprache(self):
        regelwerk.uebernehmen(self.con, self.pid, kern.ENTWICKLER, auswahl=["W1", "G13", "G1"], texte={"G13": "  Keine   Geheimnisse – nirgends. "}, sprache="en")
        regeln = self.regeln()
        self.assertEqual([(r["nr"], r["vorlage"]) for r in regeln], [(1, "G1/2"), (2, "G13/2"), (3, "W1/2")])   # Reihenfolge der Vorlage
        self.assertEqual(regeln[1]["text"], "Keine Geheimnisse – nirgends.")
        self.assertTrue(regeln[0]["text"].startswith("Versions. Every delivery"))
        for falsch in (["G99"], []):
            with self.assertRaises(kern.AmwFehler):
                regelwerk.uebernehmen(self.con, self.pid, kern.ENTWICKLER, auswahl=falsch)

    def test_vorhandene_definition_of_done_bleibt(self):
        planung.leitbild_setzen(self.con, self.pid, kern.ENTWICKLER, dod=["Eigene Regel"])
        self.assertFalse(regelwerk.uebernehmen(self.con, self.pid, kern.ENTWICKLER)["dod"])
        self.assertEqual(planung.leitbild(self.con, self.pid)["dod"], ["Eigene Regel"])

    def test_herkunft_warum_und_angepasst(self):
        regelwerk.uebernehmen(self.con, self.pid, kern.ENTWICKLER, auswahl=["G1", "G3"], texte={"G3": "Eigener Weg."})
        d = {r["nr"]: r for r in workbench.daten_wissen(self.con, self.pid, {})["regeln"]}
        self.assertEqual((d[1]["grund"]["de"]["nr"], d[1]["grund"]["de"]["angepasst"]), ("G1", False))
        self.assertIn("erfahrung", d[1]["grund"]["de"])
        self.assertEqual(d[1]["grund"]["en"]["titel"], "Versions")
        self.assertEqual((d[2]["grund"]["de"]["angepasst"], "warum" in d[2]["grund"]["de"], "erfahrung" in d[2]["grund"]["de"]), (True, True, False))
        self.assertEqual(d[2]["grund"]["de"]["gruppe"], "Arbeit und Nachweis")
        bid = wissen.beschluss_neu(self.con, self.pid, "Chef", "Eigene", "Eigene Regel", "Chef")
        wissen.regel_setzen(self.con, self.pid, "Chef", "arbeit", 3, "Projekteigene Regel", bid)
        eigene = next(r for r in workbench.daten_wissen(self.con, self.pid, {})["regeln"] if r["nr"] == 3)
        self.assertIsNone(eigene.get("grund"))                                                  # projekteigen: keine Herkunft
        self.assertIsNone(regelwerk.herkunft("X9/1"))
        self.assertIsNone(regelwerk.herkunft(None))

    def test_kopie_in_ein_anderes_projekt_nimmt_die_herkunft_mit(self):
        regelwerk.uebernehmen(self.con, self.pid, kern.ENTWICKLER, auswahl=["G1", "G2"])
        with db.schreiben(self.con):
            neu = db.einfuegen(self.con, "projekt", name="Zwei", angelegt_utc=db.jetzt())
        self.assertEqual(wissen.regeln_uebernehmen(self.con, neu, self.pid), 2)
        self.assertEqual([r[0] for r in self.con.execute("SELECT vorlage FROM regel WHERE projekt_id = ? ORDER BY nr", (neu,))], ["G1/2", "G2/2"])

    def test_pflicht_kontext_takt_fuer_den_chat_lead_und_version(self):
        regelwerk.uebernehmen(self.con, self.pid, kern.ENTWICKLER, lead_chat=True)
        wissen.release_version(self.con, self.pid, kern.ENTWICKLER, "0.1.0", "Projekt angelegt")
        chef, maler = kern.kontext(self.con, self.pid, "Chef"), kern.kontext(self.con, self.pid, "Maler")
        self.assertIn("Dein Rhythmus (KR20): Rhythmus für einen Lead, der als Chat arbeitet.", chef)
        self.assertNotIn("Dein Rhythmus", maler)                                                    # nur der Chat-Lead
        for text in (chef, maler):
            self.assertIn("Version: aktuell 0.1.0 · Schema MAJOR.MINOR.PATCH", text)


class Anlegen(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"), "LOCALAPPDATA": self.ordner.name})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        for k in ("AMW_PROJEKT", "AMW_AGENT"):
            os.environ.pop(k, None)

    def test_neues_projekt_mit_grund_regelwerk(self):
        schritte = assistent.schnell("Neu", lead="Chef", agenten=("A1",), hooks=False, ausgabe=lambda *a: None, lead_chat=True,
                                     regelwerk={"auswahl": None, "texte": {}, "sprache": "de"})
        self.assertTrue(any("Grund-Regelwerk 2: 20 Regeln übernommen" in s and "Definition of Done" in s for s in schritte), schritte)
        self.assertTrue(any("Version 0.1.0 eingetragen" in s for s in schritte), schritte)
        con = db.verbinde()
        self.addCleanup(con.close)
        pid = db.projekt_id(con, "Neu")
        self.assertEqual(con.execute("SELECT count(*) FROM regel WHERE projekt_id = ? AND vorlage IS NOT NULL", (pid,)).fetchone()[0], 20)
        self.assertEqual(tuple(con.execute("SELECT art, version, titel FROM release WHERE projekt_id = ?", (pid,)).fetchone()), ("version", "0.1.0", "Projekt angelegt"))
        nochmal = assistent.schnell("Neu", lead="Chef", agenten=("A1",), hooks=False, ausgabe=lambda *a: None, regelwerk={"auswahl": None})
        self.assertFalse(any("Regelwerk" in s for s in nochmal), nochmal)                       # das Projekt gibt es schon: nichts doppelt
        with self.assertRaises(kern.AmwFehler):
            assistent.schnell("Drei", lead="Chef", agenten=(), hooks=False, ausgabe=lambda *a: None, regeln_von="Neu", regelwerk={})

    def test_ohne_angabe_bleibt_alles_wie_bisher(self):
        assistent.schnell("Leer", lead="Chef", agenten=(), hooks=False, ausgabe=lambda *a: None)
        con = db.verbinde()
        self.addCleanup(con.close)
        pid = db.projekt_id(con, "Leer")
        self.assertEqual((con.execute("SELECT count(*) FROM regel WHERE projekt_id = ?", (pid,)).fetchone()[0],
                          con.execute("SELECT count(*) FROM release WHERE projekt_id = ?", (pid,)).fetchone()[0]), (0, 0))


class Umstellung(Grund):
    def test_22_nach_23(self):
        bid = wissen.beschluss_neu(self.con, self.pid, "Chef", "Alt", "Alte Regel", "Chef")
        wissen.regel_setzen(self.con, self.pid, "Chef", "arbeit", 1, "Alte Regel", bid)
        for sp in ("braucht_gb", "braucht_vram_gb", "braucht_platte_gb", "rechner"):   # Bedarf und Rechner je Lauf kamen mit Schema 24
            self.con.execute(f"ALTER TABLE lauf DROP COLUMN {sp}")
        self.con.execute("ALTER TABLE regel DROP COLUMN vorlage")
        self.con.execute("PRAGMA user_version = 22")
        pfad = self.con.execute("PRAGMA database_list").fetchone()[2]
        self.con.close()
        self.con = db.verbinde(pfad)
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
        r = self.con.execute("SELECT text, vorlage FROM regel").fetchone()
        self.assertEqual(tuple(r), ("Alte Regel", None))                                        # Bestand bleibt, projekteigen


if __name__ == "__main__":
    unittest.main()
