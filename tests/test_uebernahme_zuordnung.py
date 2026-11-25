"""A2109: Konzept-Übernahme mit Zuordnung – ähnliche Themennamen melden, Abschnitte vorhandenen Themen zuordnen (ziel) oder
ausschließen (ohne), die ganze Datei in ein Thema (ganz). Überall gilt: nichts überschrieben, nichts freigegeben, Zählprobe."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import db, kern, konzept_uebernahme as ku, themen

KONZEPT = """# Konzept Insel

Vorwort, siehe A1926.

## Welt und Ressourcen

Holz und Stein nach B12, Plan in [Karte](karte.md).

### Fundorte

- Steinbruch (TH3)

```text
# keine Überschrift, nur Code
```

## Wetter

Regen nach §1.5.

## Änderungen Mai

- D1304 eingearbeitet

## Änderungen Juni

- https://example.org/juni
"""
ALT = "Die Welt ist rund (B7).\n\n## Alte Überschrift\n\nBleibt stehen."


class Zuordnung(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": pfad, "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(pfad)
        self.addCleanup(self.con.close)
        self.pid, self.dir = {}, {}
        for name in ("Insel", "Anderes"):
            with db.schreiben(self.con):
                self.pid[name] = db.einfuegen(self.con, "projekt", name=name, angelegt_utc=db.jetzt())
            kern.agent_neu(self.con, self.pid[name], "TL", rolle="lead")
            kern.agent_neu(self.con, self.pid[name], "CC1")
            self.dir[name] = os.path.join(self.ordner.name, name)
            os.makedirs(self.dir[name])
            kern.projekt_ordner_setzen(self.con, self.pid[name], self.dir[name])
        self.p = self.pid["Insel"]
        self.datei = self.schreiben("konzept.md", KONZEPT)
        self.welt = themen.neu(self.con, self.p, "TL", "Welt")
        themen.pflegen(self.con, self.p, "TL", self.welt, ALT)
        self.fremd = themen.neu(self.con, self.pid["Anderes"], "TL", "Fremdes")

    def schreiben(self, name, text):
        pfad = os.path.join(self.dir["Insel"], name)
        with open(pfad, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return pfad

    def stand(self):
        return {t: self.con.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in ("thema", "thema_fassung", "dokument", "plan_ereignis", "nachricht", "thema_dokument")}

    def fassungen(self, tid):
        return [r[0] for r in self.con.execute("SELECT text FROM thema_fassung WHERE thema_id = ? ORDER BY nr", (tid,))]

    def ueber(self, von="TL", **mit):
        return ku.uebernehmen(self.con, self.p, von, mit.pop("datei", self.datei), **mit)

    def schlaegt_fehl(self, muster, **mit):
        """Fehler in Vorschau und beim Anlegen – und geschrieben ist nichts."""
        vorher = self.stand()
        for anlegen in (False, True):
            with self.assertRaisesRegex(kern.AmwFehler, muster):
                self.ueber(anlegen=anlegen, **mit)
        self.assertEqual(self.stand(), vorher)

    # --- (1) ähnliche Namen ---

    def test_aehnlich_regel(self):
        for a, b in (("Welt und Ressourcen", "Welt"), ("Welt", "welt und Ressourcen"), ("Die Ressourcen der Welt", "Welt: Ressourcen"),
                     ("1 Netz", "Netz"), ("Netz-Plan", "Netz")):
            self.assertTrue(ku.aehnlich(a, b), (a, b))
        for a, b in (("Weltall", "Welt"), ("Wetter und Wind", "Welt und Wasser"), ("Und", "Welt und Ressourcen"), ("–", "Welt")):
            self.assertFalse(ku.aehnlich(a, b), (a, b))

    def test_vorschau_meldet_aehnliche_und_entscheidet_nichts(self):
        vorher = self.stand()
        r = self.ueber()
        self.assertEqual(self.stand(), vorher)
        je = {t["name"]: t["aehnlich"] for t in r["themen"]}
        self.assertEqual(je["Welt und Ressourcen"], [{"id": self.welt, "name": "Welt"}])
        self.assertEqual(je["Wetter"], [])
        text = "\n".join(ku.zeilen(r))
        self.assertIn(f"ähnlich: TH{self.welt} „Welt“", text)
        self.assertEqual(text.count("ähnlich:"), 1)
        self.assertTrue(r["bestanden"], r["unterschiede"])
        a = self.ueber(anlegen=True)                  # der Hinweis hält nichts auf und ordnet nichts zu
        self.assertEqual(len(a["themen"]), 4)
        self.assertEqual(self.fassungen(self.welt), [ALT])

    def test_aehnlich_nur_im_eigenen_projekt(self):
        themen.neu(self.con, self.pid["Anderes"], "TL", "Wetter und Wind")
        self.assertEqual([t["aehnlich"] for t in self.ueber()["themen"] if t["name"] == "Wetter"], [[]])

    # --- (2) ziel ---

    def test_ziel_vorschau_schreibt_nichts(self):
        vorher = self.stand()
        r = self.ueber(ziel={"Welt und Ressourcen": self.welt})
        self.assertEqual(self.stand(), vorher)
        self.assertNotIn("Welt und Ressourcen", [t["name"] for t in r["themen"]])
        self.assertEqual([(z["abschnitt"], z["thema"], z["thema_name"], z["fassung"]) for z in r["ziele"]],
                         [("Welt und Ressourcen", self.welt, "Welt", 2)])
        self.assertTrue(r["bestanden"], r["unterschiede"])
        self.assertIn(f"TH{self.welt}", "\n".join(ku.zeilen(r)))

    def test_ziel_anlegen_haengt_an_und_gibt_nichts_frei(self):
        themen.freigeben(self.con, self.p, kern.ENTWICKLER, self.welt)
        r = self.ueber(ziel={"welt und  Ressourcen": f"TH{self.welt}"}, anlegen=True)
        self.assertTrue(r["bestanden"], r["unterschiede"])
        alt, neu = self.fassungen(self.welt)
        self.assertEqual(alt, ALT)                    # die alte Fassung bleibt
        self.assertTrue(neu.startswith(ALT + "\n\n"))
        anhang = neu[len(ALT):].strip().splitlines()
        self.assertIn("konzept.md", anhang[0])
        self.assertIn("Welt und Ressourcen", anhang[0])
        self.assertIn("## Welt und Ressourcen", anhang)
        self.assertIn("### Fundorte", anhang)
        self.assertNotIn("Regen", neu)
        s = themen.status(self.con, themen.finden(self.con, self.p, self.welt))
        self.assertEqual((s["fassung"], s["freigegeben"], s["status"]), (2, 1, "dich"))
        self.assertEqual([t["name"] for t in r["themen"]], ["Wetter", "Änderungen Mai", "Änderungen Juni"])
        self.assertTrue(self.con.execute("SELECT 1 FROM thema_dokument WHERE thema_id = ? AND dokument_id = ?",
                                         (self.welt, r["dokument"])).fetchone())
        e = self.con.execute("SELECT text FROM plan_ereignis WHERE art = ?", (ku.ART,)).fetchone()
        self.assertEqual(json.loads(e[0])["ziele"], [{"thema": self.welt, "fassung": 2}])
        self.assertTrue(r["bericht"])

    def test_ziel_benutzt_thema_pflegen(self):
        with mock.patch.object(themen, "pflegen", wraps=themen.pflegen) as pflegen:
            self.ueber(ziel={"Wetter": self.welt}, anlegen=True)
        pflegen.assert_called_once()

    def test_ziel_mehrere_abschnitte_ein_thema_und_thema_ohne_text(self):
        leer = themen.neu(self.con, self.p, "TL", "Leer")
        r = self.ueber(ziel={"Änderungen Mai": self.welt, "Änderungen Juni": self.welt, "Wetter": leer}, anlegen=True)
        self.assertTrue(r["bestanden"], r["unterschiede"])
        self.assertEqual(len(self.fassungen(self.welt)), 2)          # ein Thema, eine neue Fassung – beide Abschnitte darin
        neu = self.fassungen(self.welt)[-1]
        self.assertLess(neu.index("## Änderungen Mai"), neu.index("## Änderungen Juni"))
        self.assertEqual(neu.count("Übernommen aus"), 2)
        self.assertEqual(len(self.fassungen(leer)), 1)
        self.assertTrue(self.fassungen(leer)[0].startswith("Übernommen aus konzept.md"))

    def test_ziel_bei_gleichem_namen_und_nur_ziele(self):
        datei = self.schreiben("nur.md", "## Welt\n\nNeues zu B9.\n")
        self.assertEqual(len(self.ueber(datei=datei)["rest"]), 1)     # ohne ziel wie heute: gibt es schon
        r = self.ueber(datei=datei, ziel={"Welt": self.welt}, anlegen=True)
        self.assertTrue(r["bestanden"], r["unterschiede"])
        self.assertEqual((r["themen"], r["rest"]), ([], []))
        self.assertIn("Neues zu B9.", self.fassungen(self.welt)[-1])

    def test_ziel_doppelter_abschnitt_geht_ganz_mit(self):
        datei = self.schreiben("doppelt.md", "## A\n\neins\n\n## A\n\nzwei\n\n## B\n\ndrei\n")
        r = self.ueber(datei=datei, ziel={"A": self.welt}, anlegen=True)
        self.assertTrue(r["bestanden"], r["unterschiede"])
        neu = self.fassungen(self.welt)[-1]
        self.assertTrue("eins" in neu and "zwei" in neu and "drei" not in neu)

    def test_ziel_fehler(self):
        self.schlaegt_fehl("Gibt es nicht", ziel={"Gibt es nicht": self.welt})
        self.schlaegt_fehl("Fundorte", ziel={"Fundorte": self.welt})  # Unterabschnitt, nicht die Gliederungsebene
        self.schlaegt_fehl(f"TH{self.fremd}", ziel={"Wetter": self.fremd})
        self.schlaegt_fehl("TH99999", ziel={"Wetter": 99999})
        self.schlaegt_fehl("Themennummer", ziel={"Wetter": "Welt"})
        self.schlaegt_fehl("zwei Themen", ziel={"Wetter": self.welt, "wetter": themen.neu(self.con, self.p, "TL", "Z")})
        self.assertEqual(self.fassungen(self.fremd), [])

    def test_ziel_nur_pfleger_oder_lead(self):
        kern.projekt_einstellen(self.con, self.p, "TL", co_entwickler="CC1")
        self.schlaegt_fehl("Pfleger", von="CC1", ziel={"Wetter": self.welt})
        themen.einstellen(self.con, self.p, "TL", self.welt, pfleger="CC1")
        self.assertTrue(self.ueber(von="CC1", ziel={"Wetter": self.welt}, anlegen=True)["bestanden"])

    def test_zaehlprobe_findet_ueberschriebenen_text(self):
        def verliert(con, pid, von, name, text):
            with db.schreiben(con):
                db.einfuegen(con, "thema_fassung", thema_id=self.welt, nr=2, text=text.replace("Bleibt stehen.", ""), von=von,
                             zeit_utc=db.jetzt())
            return 2
        with mock.patch.object(themen, "pflegen", verliert):
            self.assertFalse(self.ueber(ziel={"Wetter": self.welt}, anlegen=True)["bestanden"])

    def test_zaehlprobe_findet_offenen_code_block_im_thema(self):
        themen.pflegen(self.con, self.p, "TL", self.welt, "Text\n\n```\noffen")
        r = self.ueber(ziel={"Wetter": self.welt})                   # die Überschrift ginge im Code-Block unter
        self.assertFalse(r["bestanden"])
        self.assertEqual([u[0] for u in r["unterschiede"]], ["Überschriften"])

    # --- (3) ohne ---

    def test_ohne(self):
        for anlegen in (False, True):
            r = self.ueber(ohne=["änderungen*"], anlegen=anlegen)
            self.assertTrue(r["bestanden"], r["unterschiede"])
            self.assertEqual([t["name"] for t in r["themen"]], ["Welt und Ressourcen", "Wetter"])
            aus = [x for x in r["rest"] if "usgeschlossen" in x["grund"]]
            self.assertEqual([x["text"].splitlines()[0] for x in aus], ["## Änderungen Mai", "## Änderungen Juni"])
            self.assertIn("änderungen*", aus[0]["grund"])
            self.assertIn("Nicht zugeordnet: 3", "\n".join(ku.zeilen(r)))

    def test_ohne_als_text_ist_ein_muster(self):
        self.assertEqual(len(self.ueber(ohne="Änderungen*")["themen"]), 2)

    def test_ohne_alles_legt_nichts_an(self):
        vorher = self.stand()
        self.assertTrue(self.ueber(ohne=["*"])["bestanden"])
        with self.assertRaisesRegex(kern.AmwFehler, "Nichts anzulegen"):
            self.ueber(ohne=["*"], anlegen=True)
        self.assertEqual(self.stand(), vorher)

    def test_ziel_und_ohne(self):
        r = self.ueber(ziel={"Wetter": self.welt}, ohne=["Änderungen*"], anlegen=True)
        self.assertTrue(r["bestanden"], r["unterschiede"])
        self.assertEqual([t["name"] for t in r["themen"]], ["Welt und Ressourcen"])
        self.schlaegt_fehl("Wetter", ziel={"Wetter": self.welt}, ohne=["Wet*"])   # beides zugleich ist widersprüchlich

    # --- (4) ganz ---

    def test_ganz_vorschau_und_anlegen(self):
        vorher = self.stand()
        r = self.ueber(ganz=self.welt)
        self.assertEqual(self.stand(), vorher)
        self.assertEqual((r["themen"], r["rest"], r["ebene"]), ([], [], None))
        self.assertTrue(r["bestanden"], r["unterschiede"])
        self.assertIn("ganze Datei", "\n".join(ku.zeilen(r)))
        r = self.ueber(ganz=self.welt, anlegen=True)
        self.assertTrue(r["bestanden"], r["unterschiede"])
        alt, neu = self.fassungen(self.welt)                         # genau eine neue Fassung
        self.assertEqual(alt, ALT)
        self.assertTrue(neu.startswith(ALT + "\n\nÜbernommen aus konzept.md"))
        self.assertTrue(neu.endswith(KONZEPT.strip()))
        self.assertEqual(self.con.execute("SELECT count(*) FROM thema WHERE projekt_id = ?", (self.p,)).fetchone()[0], 1)
        self.assertIsNone(themen.status(self.con, themen.finden(self.con, self.p, self.welt))["freigegeben"])

    def test_ganz_ohne_ueberschriften(self):
        datei = self.schreiben("notiz.md", "﻿nur Text zu A5\r\n\r\nund mehr\r\n")
        r = self.ueber(datei=datei, ganz=self.welt, anlegen=True)
        self.assertTrue(r["bestanden"], r["unterschiede"])
        self.assertTrue(self.fassungen(self.welt)[-1].endswith("nur Text zu A5\n\nund mehr"))

    def test_ganz_fehler(self):
        self.schlaegt_fehl("ganz", ganz=self.welt, ziel={"Wetter": self.welt})
        self.schlaegt_fehl("ganz", ganz=self.welt, ohne=["Änderungen*"])
        self.schlaegt_fehl(f"TH{self.fremd}", ganz=self.fremd)
        self.schlaegt_fehl("TH0", ganz=0)
        self.schlaegt_fehl("leer", ganz=self.welt, datei=self.schreiben("leer.md", " \n\n"))

    # --- ohne die neuen Angaben wie bisher ---

    def test_leere_angaben_wie_bisher(self):
        self.assertEqual(self.ueber(), self.ueber(ziel={}, ohne=[], ganz=None))
        self.assertEqual(ku.gliedern(KONZEPT), ku.gliedern(KONZEPT, ziel={}, ohne=[]))
        r = self.ueber(anlegen=True)
        self.assertEqual(r["ziele"], [])
        e = self.con.execute("SELECT text FROM plan_ereignis WHERE art = ?", (ku.ART,)).fetchone()
        self.assertNotIn("ziele", json.loads(e[0]))


if __name__ == "__main__":
    unittest.main()
