"""Empfehlung Modell/Denkaufwand (A1611 E2): Größe und Art je Aufgabe (Schema 30), Tabelle je Projekt (nur Abweichungen
gespeichert), Messwert und rote Prüfungen je Zelle, Vergleich mit dem Profil, häufigste Zelle je Agent, Befehlszeile und
Oberfläche (DE+EN). Die AMW stellt nichts selbst um."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
import json
import os
import re
import sqlite3
import tempfile
import unittest
from unittest import mock

from amw import db, empfehlung, kern, planung, steuerung, workbench

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def z(stunde, minute=0):
    return f"2026-11-12T{stunde:02d}:{minute:02d}:00Z"


class Empfehlung(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="Eins", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        steuerung.profil_setzen(self.con, self.pid, kern.ENTWICKLER, "CC1", modell="opus", denkstufe="high")

    def cli(self, *args):
        from amw import cli
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_DB": self.pfad}), contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(list(args))
        return rc, aus.getvalue()

    def fertig(self, groesse, art, beginn, ende, usd_vor, usd_nach, sid, rot=False):
        with db.schreiben(self.con):
            aid = db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel=f"{groesse} {art}", agent="CC1", angelegt_von="TL",
                               angelegt_utc=beginn, status="fertig", begonnen_utc=beginn, fertig_utc=ende, groesse=groesse, art=art)
            db.einfuegen(self.con, "verbrauch", sitzung_id=sid, agent="CC1", zeit_utc=beginn, kosten_usd=usd_vor)
            db.einfuegen(self.con, "verbrauch", sitzung_id=sid, agent="CC1", zeit_utc=ende, kosten_usd=usd_nach)
            if rot:
                db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=aid, zweig="z", sha="abc1234", bauer="CC1", pruefer="TL", ergebnis="rot",
                             angefragt_utc=ende)
        return aid

    def sitzung(self):
        gid = kern.agent_zeile(self.con, self.pid, "CC1")["id"]
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "sitzung", agent_id=gid, gestartet_utc=z(7), modell="Opus 5.5", denkstufe="high")

    def test_schema_30_und_migration(self):
        spalten = [r[1] for r in self.con.execute("PRAGMA table_info(aufgabe)")]
        self.assertIn("groesse", spalten)
        self.assertIn("art", spalten)
        with self.assertRaises(sqlite3.IntegrityError), db.schreiben(self.con):
            db.einfuegen(self.con, "aufgabe", projekt_id=self.pid, titel="x", angelegt_von="TL", angelegt_utc=z(8), groesse="XXL")
        alt = os.path.join(self.ordner.name, "alt.db")                    # Stand 29 → 30
        k = db.anlegen(alt)
        k.execute("ALTER TABLE aufgabe DROP COLUMN groesse")
        k.execute("ALTER TABLE aufgabe DROP COLUMN art")
        k.execute("PRAGMA user_version = 29")
        k.commit()
        db.migrieren(k)
        self.assertEqual(k.execute("PRAGMA user_version").fetchone()[0], db.SCHEMA_VERSION)
        self.assertIn("art", [r[1] for r in k.execute("PRAGMA table_info(aufgabe)")])
        k.close()

    def test_tabelle_standard_abweichung_und_pruefung(self):
        self.assertEqual(empfehlung.tabelle(self.con, self.pid), empfehlung.STANDARD)
        e = kern.projekt_einstellen(self.con, self.pid, "TL", empfehlung={"einfach": {"S": "Haiku/Low", "M": "sonnet/medium"}})
        self.assertEqual(e["empfehlung"], {"einfach": {"S": "haiku/low"}})              # nur die Abweichung
        self.assertEqual(empfehlung.tabelle(self.con, self.pid)["einfach"]["S"], "haiku/low")
        for falsch in ({"einfach": {"S": "gpt/high"}}, {"einfach": {"XXL": "opus/high"}}, {"lustig": {"S": "opus/high"}}):
            with self.assertRaises(kern.AmwFehler):
                kern.projekt_einstellen(self.con, self.pid, "TL", empfehlung=falsch)
        with self.assertRaises(kern.AmwFehler):
            kern.projekt_einstellen(self.con, self.pid, "CC1", empfehlung={})            # nur Lead und Entwickler
        kern.projekt_einstellen(self.con, self.pid, "TL", empfehlung=json.dumps(empfehlung.STANDARD))   # auch als Text (Befehlszeile)
        self.assertNotIn("empfehlung", json.loads(self.con.execute("SELECT einstellungen FROM projekt").fetchone()[0]))

    def test_aufgabe_zelle_profil_und_befehlszeile(self):
        sid = self.sitzung()
        self.fertig("M", "oberflaeche", z(8), z(9), 0.0, 10.0, sid)
        self.fertig("M", "fehlersuche", z(9, 30), z(10), 10.0, 30.0, sid, rot=True)  # gleiche Gruppe „mittel“
        self.fertig("S", "oberflaeche", z(10, 30), z(11), 30.0, 31.0, sid)            # andere Zelle
        rc, aus = self.cli("aufgabe", "neu", "--titel", "Knopf", "--agent", "CC1", "--groesse", "m", "--art", "oberflaeche",
                           "--von", "TL", "--projekt", "Eins")
        self.assertEqual(rc, 0, aus)
        aid = int(aus.split()[0][1:])
        self.assertNotIn("Tipp:", aus)
        e = empfehlung.fuer_aufgabe(self.con, self.pid, aid)
        self.assertEqual((e["modell"], e["denkstufe"], e["gruppe"]), ("opus", "medium", "mittel"))
        self.assertEqual(e["zelle"], {"median": 15.0, "n": 2, "rot": 1})
        self.assertIs(e["passt"], False)                                                  # CC1 läuft mit opus/high
        rc, aus = self.cli("aufgabe", "zeige", str(aid), "--von", "TL", "--projekt", "Eins")
        self.assertIn("empfehlung: opus/medium für M · oberflaeche (gemessen in dieser Zelle: Median 15.00 $ aus 2, 1× rot)"
                      " – CC1 ist eingestellt auf opus/high", aus)
        self.assertEqual(workbench.daten_aufgabe(self.con, self.pid, aid)["empfehlung"]["modell"], "opus")
        rc, aus = self.cli("aufgabe", "neu", "--titel", "ohne", "--agent", "CC1", "--von", "TL", "--projekt", "Eins")
        self.assertIn("Tipp: --groesse", aus)
        self.assertIsNone(empfehlung.fuer_aufgabe(self.con, self.pid, int(aus.split()[0][1:])))
        rc, aus = self.cli("aufgabe", "aendern", str(aid), "--art", "text", "--von", "TL", "--projekt", "Eins")
        self.assertEqual(rc, 0, aus)
        self.assertEqual(empfehlung.fuer_aufgabe(self.con, self.pid, aid)["modell"], "sonnet")
        with self.assertRaises(kern.AmwFehler):
            planung.schritt_setzen(self.con, self.pid, "TL", aid=aid, groesse="riesig")

    def test_agent_haeufigste_zelle_passt_und_uebernehmen(self):
        sid = self.sitzung()
        self.fertig("S", "text", z(8), z(8, 30), 0.0, 1.0, sid)
        self.fertig("S", "mechanisch", z(9), z(9, 30), 1.0, 2.0, sid)
        self.fertig("L", "konzept", z(10), z(10, 30), 2.0, 9.0, sid)
        e = empfehlung.fuer_agent(self.con, self.pid, "CC1")
        self.assertEqual((e["modell"], e["denkstufe"], e["groesse"], e["gruppe"], e["n"], e["von"]), ("sonnet", "low", "S", "einfach", 2, 3))
        self.assertIs(e["passt"], False)
        rc, aus = self.cli("agent", "profil", "CC1", "--von", "TL", "--projekt", "Eins")
        self.assertIn("sonnet/low (meist S · einfach, 2 von 3 letzten Aufgaben) – weicht vom Profil ab", aus)
        steuerung.profil_setzen(self.con, self.pid, kern.ENTWICKLER, "CC1", modell="sonnet", denkstufe="low")   # wie „Ins Profil übernehmen“
        self.assertIs(empfehlung.fuer_agent(self.con, self.pid, "CC1")["passt"], True)
        self.assertEqual(workbench.daten_agent(self.con, self.pid, "CC1")["empfehlung"]["modell"], "sonnet")
        self.assertIsNone(empfehlung.passt({"modell": None, "denkstufe": "high"}, {"modell": "opus", "denkstufe": "high"}))
        self.assertTrue(empfehlung.passt({"modell": "claude-opus-5-5", "denkstufe": "high"}, {"modell": "opus", "denkstufe": "high"}))
        self.assertIsNone(empfehlung.fuer_agent(self.con, self.pid, "TL"))

    def test_oberflaeche_texte_und_einstellung(self):
        with open(os.path.join(WURZEL, "amw", "workbench.html"), encoding="utf-8") as f:
            html = f.read()
        schluessel = ["au_empfehlung", "au_empf_x", "au_empf_zelle", "au_empf_keine_zelle", "au_empf_profil", "empf_h", "k_empf",
                      "k_empf_passt", "k_empf_uebernehmen", "k_empf_frage", "k_empf_ok", "sb_empf", "e_empfehlung", "e_empfehlung_h",
                      "e_empf_art", "e_empf_std"] + ["ga_" + a for a in empfehlung.ARTEN] + ["gg_" + g for g in empfehlung.GRUPPEN]
        for k in schluessel:
            self.assertEqual(len(re.findall(rf"\b{k}: \"", html)), 2, k)
        self.assertIn('"/api/einstellungen/profil", { kennung: d.kennung, modell: e.modell, denkstufe: e.denkstufe }', html)
        self.assertEqual(workbench.daten_einstellungen(self.con, self.pid)["projekt"]["empfehlung"], empfehlung.STANDARD)


if __name__ == "__main__":
    unittest.main()
