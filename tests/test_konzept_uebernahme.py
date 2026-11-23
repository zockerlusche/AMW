"""A1994 (TH160, verallgemeinert A1886/K11): Konzept-Markdown eines Projekts halbautomatisch in Themen-Entwürfe – Vorschau ohne
Schreiben, Anlegen nur im eigenen Projekt, nichts freigegeben, Original unverändert und als Dokument lesbar, Zählprobe
(Zeilen, Überschriften, Kennungen, Links) gegen die Datenbank, nicht zuordenbare Stellen gelistet. Synthetisches Fremdprojekt:
zwei Projekte, nichts tritt über."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import collections
import contextlib
import hashlib
import io
import os
import tempfile
import unittest
from unittest import mock

from amw import cli, db, gegenlesen, kern, konzept_uebernahme as ku, themen

KONZEPT = """# Konzept Brücke

Vorwort ohne Abschnitt, siehe A1926.

## 1 Netz

Das Netz gilt nach B12 und §1.5 – Details in [Netz-Plan](netz.md).

### 1.1 Knoten

- Knoten zählen (TH3)

```text
# keine Überschrift, nur Code
```

## 2 Speichern ##

Speichern wie in https://example.org/speichern beschrieben (D1304 §5).

## 3 Leer

## 2 Speichern

Doppelt – darf nicht überschreiben.
"""


class Uebernahme(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.pfad = os.path.join(self.ordner.name, "amw.db")
        u = mock.patch.dict(os.environ, {"AMW_DB": self.pfad, "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(self.pfad)
        self.addCleanup(self.con.close)
        self.pid, self.dir = {}, {}
        for name in ("GlassWorld", "Anderes"):
            with db.schreiben(self.con):
                self.pid[name] = db.einfuegen(self.con, "projekt", name=name, angelegt_utc=db.jetzt())
            kern.agent_neu(self.con, self.pid[name], "TL", rolle="lead")
            kern.agent_neu(self.con, self.pid[name], "CC1")
            self.dir[name] = os.path.join(self.ordner.name, name)
            os.makedirs(self.dir[name])
            kern.projekt_ordner_setzen(self.con, self.pid[name], self.dir[name])
        self.datei = os.path.join(self.dir["GlassWorld"], "kopie", "konzept.md")
        os.makedirs(os.path.dirname(self.datei))
        with open(self.datei, "w", encoding="utf-8", newline="\n") as f:
            f.write(KONZEPT)
        with db.schreiben(self.con):                 # ein vorhandenes Thema im Fremdprojekt mit gleichem Namen stört nicht
            db.einfuegen(self.con, "thema", projekt_id=self.pid["Anderes"], name="1 Netz", stil=0, angelegt_von="TL",
                         angelegt_utc=db.jetzt())

    def zeilen(self, pid=None):
        tabellen = ("thema", "thema_fassung", "dokument", "plan_ereignis", "nachricht", "thema_dokument")
        if pid is None:
            return {t: self.con.execute(f"SELECT count(*) FROM {t}").fetchone()[0] for t in tabellen}
        return {"thema": self.con.execute("SELECT count(*) FROM thema WHERE projekt_id = ?", (pid,)).fetchone()[0],
                "dokument": self.con.execute("SELECT count(*) FROM dokument WHERE projekt_id = ?", (pid,)).fetchone()[0],
                "plan_ereignis": self.con.execute("SELECT count(*) FROM plan_ereignis WHERE projekt_id = ?", (pid,)).fetchone()[0],
                "nachricht": self.con.execute("SELECT count(*) FROM nachricht WHERE projekt_id = ?", (pid,)).fetchone()[0]}

    def sha(self):
        with open(self.datei, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()

    def test_gliederung_titel_vorwort_code_doppelt_leer(self):
        p = ku.gliedern(KONZEPT)
        self.assertEqual(p["ebene"], 2)                                   # ein Titel (#) → Gliederung ##
        self.assertEqual([t["name"] for t in p["themen"]], ["1 Netz", "2 Speichern", "3 Leer"])
        netz = p["themen"][0]["text"]
        self.assertIn("### 1.1 Knoten", netz)                            # Unterabschnitte bleiben im Text
        self.assertIn("# keine Überschrift, nur Code", netz)             # Code-Block ist keine Überschrift
        self.assertEqual(p["themen"][2]["text"], "")
        gruende = [r["grund"] for r in p["rest"]]
        self.assertEqual(gruende, ["Titel des Dokuments", "Thema „2 Speichern“ gibt es schon (doppelt im Dokument)"])
        self.assertIn("Vorwort ohne Abschnitt", p["rest"][0]["text"])     # Text vor dem ersten Abschnitt gehört zum Titel-Block
        self.assertEqual(ku.gliedern(KONZEPT, ebene=3)["themen"][0]["name"], "1.1 Knoten")
        ohne_titel = ku.gliedern("Vorweg\n\n## A\n\nx\n\n## B\n\ny\n")
        self.assertEqual([r["grund"] for r in ohne_titel["rest"]], ["Text vor dem ersten Abschnitt"])
        with self.assertRaises(kern.AmwFehler):
            ku.gliedern("nur Text, keine Überschrift\n")
        with self.assertRaises(kern.AmwFehler):
            ku.gliedern(KONZEPT, ebene=5)

    def test_vorschau_schreibt_nichts_und_zaehlprobe_bestanden(self):
        vorher = self.zeilen()
        r = ku.uebernehmen(self.con, self.pid["GlassWorld"], "TL", self.datei)
        self.assertEqual(self.zeilen(), vorher)
        self.assertFalse(r["angelegt"])
        self.assertTrue(r["bestanden"], r["unterschiede"])
        self.assertTrue(r["unveraendert"])
        k = r["original"]["kennungen"]
        for x in ("A1926", "B12", "§1.5", "TH3", "D1304", "§5"):
            self.assertEqual(k[x], 1, x)
        self.assertEqual(sum(r["original"]["links"].values()), 2)
        text = "\n".join(ku.zeilen(r))
        self.assertIn("Vorschau – nichts angelegt: 3 Themen", text)
        self.assertIn("Nicht zugeordnet: 2", text)
        self.assertIn("Zählprobe (geplant + nicht zugeordnet gegen das Original): bestanden", text)

    def test_anlegen_nur_im_eigenen_projekt_nichts_freigegeben(self):
        g, x = self.pid["GlassWorld"], self.pid["Anderes"]
        fremd_vorher, sha = self.zeilen(x), self.sha()
        with mock.patch.object(gegenlesen, "_spawn") as spawn, mock.patch("amw.planer.anstossen") as planer:
            r = ku.uebernehmen(self.con, g, "TL", self.datei, anlegen=True)
        spawn.assert_not_called()                                         # kein Gegenleser, kein Planer: nur Entwürfe
        planer.assert_not_called()
        self.assertTrue(r["angelegt"] and r["bestanden"], r["unterschiede"])
        self.assertEqual(self.sha(), sha)                                 # Original unverändert
        self.assertEqual(self.zeilen(x), fremd_vorher)                    # im anderen Projekt ändert sich nichts
        ids = [t["id"] for t in r["themen"]]
        for tid in ids:
            t = self.con.execute("SELECT * FROM thema WHERE id = ?", (tid,)).fetchone()
            self.assertEqual(t["projekt_id"], g)
            s = themen.status(self.con, t)
            self.assertIsNone(s["freigegeben"])                           # nichts freigegeben
            self.assertEqual(s["status"], "dich" if s["fassung"] else "arbeit")
            self.assertTrue(self.con.execute("SELECT 1 FROM thema_dokument WHERE thema_id = ? AND dokument_id = ?",
                                             (tid, r["dokument"])).fetchone())   # Original hängt an jedem Thema
        netz = themen.seite(self.con, g, "1 Netz")
        self.assertIn("[Netz-Plan](netz.md)", netz["zusammenfassung"]["text"])
        self.assertEqual(netz["zusammenfassung"]["von"], "TL")
        self.assertIsNone(themen.seite(self.con, g, "3 Leer")["zusammenfassung"])
        d = self.con.execute("SELECT * FROM dokument WHERE id = ?", (r["dokument"],)).fetchone()
        self.assertEqual((d["projekt_id"], d["art"]), (g, "quelle"))
        v = self.con.execute("SELECT sha256 FROM dokument_version WHERE dokument_id = ?", (r["dokument"],)).fetchone()
        self.assertEqual(v["sha256"], sha)                                # das Original ist als Dokument lesbar
        b = self.con.execute("SELECT * FROM dokument WHERE id = ?", (r["bericht"],)).fetchone()
        self.assertEqual((b["projekt_id"], b["art"]), (g, "bericht"))
        e = self.con.execute("SELECT * FROM plan_ereignis WHERE art = ?", (ku.ART,)).fetchall()
        self.assertEqual([x["projekt_id"] for x in e], [g])
        # zweimal: alles gibt es schon → nichts anzulegen, nichts überschrieben
        with self.assertRaises(kern.AmwFehler):
            ku.uebernehmen(self.con, g, "TL", self.datei, anlegen=True)
        self.assertEqual(themen.seite(self.con, g, "1 Netz")["zusammenfassung"]["nr"], 1)

    def test_zaehlprobe_findet_verlust(self):
        o = ku.zaehlen(["## A\n\nsiehe A12 und [x](y)\n"])
        n = ku.zaehlen(["## A\n\nsiehe A13\n"])
        d = {w: (fehlt, zuviel) for w, _, _, fehlt, zuviel in ku.vergleichen(o, n)}
        self.assertEqual(d["Kennungen"], (["A12"], ["A13"]))
        self.assertEqual(d["Links"], (["[x](y)"], []))
        self.assertEqual(ku.vergleichen(o, o), [])
        self.assertEqual(ku.zaehlen(["§ 1.5 und §1.5, A1.2."])["kennungen"], collections.Counter({"§1.5": 2, "A1.2": 1}))

    def test_nur_projektordner_nur_lead_oder_co(self):
        g = self.pid["GlassWorld"]
        fremd = os.path.join(self.dir["Anderes"], "konzept.md")
        with open(fremd, "w", encoding="utf-8", newline="\n") as f:
            f.write(KONZEPT)
        with self.assertRaisesRegex(kern.AmwFehler, "nicht im Projektordner"):
            ku.uebernehmen(self.con, g, "TL", fremd)                     # Datei eines anderen Projekts
        with self.assertRaisesRegex(kern.AmwFehler, "nicht im Projektordner"):
            ku.uebernehmen(self.con, g, "TL", os.path.join(self.dir["GlassWorld"], "..", "Anderes", "konzept.md"))
        with self.assertRaisesRegex(kern.AmwFehler, "Lead"):
            ku.uebernehmen(self.con, g, "CC1", self.datei)
        kern.projekt_einstellen(self.con, g, "TL", co_entwickler="CC1")
        self.assertTrue(ku.uebernehmen(self.con, g, "CC1", self.datei)["bestanden"])   # Co-Entwickler darf
        with open(os.path.join(self.dir["GlassWorld"], "x.txt"), "w", encoding="utf-8") as f:
            f.write("# a\n")
        with self.assertRaisesRegex(kern.AmwFehler, "Markdown"):
            ku.uebernehmen(self.con, g, "TL", os.path.join(self.dir["GlassWorld"], "x.txt"))
        with db.schreiben(self.con):
            self.con.execute("UPDATE projekt SET einstellungen = '{}' WHERE id = ?", (g,))
        with self.assertRaisesRegex(kern.AmwFehler, "kein Projektordner"):
            ku.uebernehmen(self.con, g, "TL", self.datei)

    def cli(self, *argv):
        aus = io.StringIO()
        with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": ""}), \
                contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["--projekt", "GlassWorld", *argv])
        return rc, aus.getvalue()

    def test_cli(self):
        rc, aus = self.cli("--von", "TL", "thema", "uebernehmen", "--datei", self.datei)
        self.assertEqual(rc, 0, aus)
        self.assertIn("Anlegen: derselbe Befehl mit --anlegen", aus)
        self.assertEqual(self.zeilen(self.pid["GlassWorld"])["thema"], 0)
        rc, aus = self.cli("--von", "TL", "thema", "uebernehmen", "--datei", self.datei, "--ebene", "2", "--anlegen")
        self.assertEqual(rc, 0, aus)
        self.assertIn("Angelegt: 3 Themen", aus)
        self.assertIn("freigegeben ist nichts", aus)
        self.assertEqual(self.zeilen(self.pid["GlassWorld"])["thema"], 3)
        rc, aus = self.cli("--von", "TL", "thema", "uebernehmen")
        self.assertNotEqual(rc, 0)
        self.assertIn("--datei", aus)


if __name__ == "__main__":
    unittest.main()
