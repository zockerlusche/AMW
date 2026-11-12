"""Tests für Dokumente online (Stufe D2): Ansichten mit Liste, Text und Dateikarte, Dateien über den Speicher zum
Webspace (in Teilen, nur „auch online“), Abholen und Aufräumen durch die PHP-Seite."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import base64
import hashlib
import json
import os
import shutil
import subprocess
import unittest

from amw import abgleich, aktionen, dokumente
from test_dokumente import Grund

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 3


class Online(Grund):
    def setUp(self):
        super().setUp()
        self.online = os.path.join(self.ordner.name, "online.db")
        self.sp = abgleich.SqliteSpeicher(self.online)
        self.ab = abgleich.Abgleich(self.con, self.sp, self.pid)
        self.ab.schema()

    def zeilen(self, sql, *args):
        return self.sp.ausfuehren([(sql, list(args))])[0]

    def test_ansichten_liste_text_und_dateikarte(self):
        md = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("b.md", "# Bericht\nSpeicher **gelb**"), "Prüfbericht",
                               "bericht", bogen=self.bid)
        dokumente.version(self.con, self.pid, "CC1", md, self.datei("b2.md", "# Bericht\nSpeicher grün"), "v2")
        bild = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("s.png", PNG), "Standbild", "bild", bogen=self.bid)
        a = abgleich.ansichten(self.con, self.pid)
        liste = {x["id"]: x for x in a["/api/dokumente"]["dokumente"]}
        self.assertIn("gelb", liste[md]["such"])                  # auch ältere Versionen durchsuchbar
        self.assertNotIn("sha256", liste[bild])
        d = a[f"/api/dokument?id={md}"]
        self.assertEqual(d["texte"], {"1": "# Bericht\nSpeicher **gelb**", "2": "# Bericht\nSpeicher grün"})
        self.assertNotIn("text", d)
        self.assertEqual(a["/intern/dateien"], {})                # Bild nicht „auch online“ → keine Datei
        dokumente.online_setzen(self.con, self.pid, "Entwickler", bild)
        sha = hashlib.sha256(PNG).hexdigest()
        self.assertEqual(abgleich.ansichten(self.con, self.pid)["/intern/dateien"], {f"{bild}:1": [sha, ".png"], f"{bild}:0": [sha, ".png"]})
        dokumente.loeschen(self.con, self.pid, "Entwickler", bild)
        a = abgleich.ansichten(self.con, self.pid)
        self.assertNotIn(bild, [x["id"] for x in a["/api/dokumente"]["dokumente"]])
        self.assertEqual(a["/intern/dateien"], {})

    def test_dateien_nur_auch_online_in_teilen_und_wieder_weg(self):
        gross = os.urandom(abgleich.TEIL * 2 + 1000)
        g = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("gross.pdf", b"%PDF-1.4\n" + gross), "Handbuch", "quelle")
        b = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("s.png", PNG), "Standbild", "bild", online=True)
        dokumente.ablegen(self.con, self.pid, "CC1", self.datei("t.md", "# nur Text"), "Text", "bericht", online=True)
        self.assertEqual(self.ab.dateien(), 1)                    # nur das Bild; Texte gehen als Ansicht
        self.assertEqual(self.zeilen("SELECT endung, groesse, teile, status FROM datei"), [[".png", len(PNG), 1, "unterwegs"]])
        self.assertEqual(self.ab.dateien(), 0)                    # schon oben
        aktionen.ausfuehren(self.con, self.pid, "/api/dokument/online", {"id": g, "an": True}, kanal="netz")
        self.assertEqual(self.ab.dateien(), 1)
        sha = self.zeilen("SELECT sha, teile FROM datei WHERE endung = '.pdf'")[0]
        self.assertEqual(sha[1], 3)
        roh = b"".join(base64.b64decode(t) for (t,) in self.zeilen("SELECT inhalt FROM datei_teil WHERE sha = ? ORDER BY nr", sha[0]))
        self.assertEqual(hashlib.sha256(roh).hexdigest(), sha[0])
        dokumente.online_setzen(self.con, self.pid, "Entwickler", b, False)
        self.assertEqual(self.ab.dateien(), 1)                    # abgemeldet
        self.assertEqual([r[0] for r in self.zeilen("SELECT endung FROM datei")], [".pdf"])
        self.assertEqual(self.zeilen("SELECT count(*) FROM datei_teil WHERE sha = ?", hashlib.sha256(PNG).hexdigest()), [[0]])

    def test_verlorene_kopie_wird_neu_hochgeladen(self):
        dokumente.ablegen(self.con, self.pid, "CC1", self.datei("s.png", PNG), "Standbild", "bild", online=True)
        self.ab.dateien()
        self.sp.ausfuehren([("DELETE FROM datei", [])])            # so meldet die Seite eine verlorene Kopie
        self.ab.oben_laden()
        self.assertEqual(self.ab.dateien(), 1)

    @unittest.skipUnless(shutil.which("php"), "PHP nicht installiert")
    def test_php_holt_ab_legt_ab_und_raeumt_auf(self):
        dokumente.ablegen(self.con, self.pid, "CC1", self.datei("s.png", PNG), "Standbild", "bild", online=True)
        self.ab.dateien()
        sha = hashlib.sha256(PNG).hexdigest()
        konfig = os.path.join(self.ordner.name, "amw-konfig.php")
        with open(konfig, "w", encoding="utf-8") as f:
            f.write(f"<?php return ['sqlite' => {json.dumps(self.online.replace(os.sep, '/'))}, 'benutzer' => 'p', 'passwort_hash' => 'x'];\n")
        ablage = os.path.join(self.ordner.name, "webspace")
        lib = os.path.join(WURZEL, "web", "inc", "lib.php").replace(os.sep, "/")
        skript = (f"require '{lib}'; $r = sql([['SELECT sha, endung, groesse, teile FROM datei', []]])[0];"
                  " dateien_nachholen($r); echo 'fertig';")
        php = ["php"] + [a for ext in ("pdo_sqlite", "mbstring") for a in ("-d", f"extension={ext}")]
        env = {**os.environ, "AMW_KONFIG": konfig, "AMW_DATEIEN": ablage}
        try:
            r = subprocess.run(php + ["-r", skript], capture_output=True, text=True, env=env, timeout=60)
        except OSError as e:
            self.skipTest(f"PHP: {e}")
        if "could not find driver" in r.stdout + r.stderr:
            self.skipTest("PHP ohne pdo_sqlite")
        self.assertIn("fertig", r.stdout, r.stdout + r.stderr)
        pfad = os.path.join(ablage, sha[:2], sha + ".png")
        with open(pfad, "rb") as f:
            self.assertEqual(f.read(), PNG)
        self.assertEqual(self.zeilen("SELECT status FROM datei"), [["abgelegt"]])
        self.assertEqual(self.zeilen("SELECT count(*) FROM datei_teil"), [[0]])
        # nicht mehr online → PC meldet ab → die Seite löscht ihre Kopie beim Aufräumen
        dokumente.online_setzen(self.con, self.pid, "Entwickler", self.con.execute("SELECT max(id) FROM dokument").fetchone()[0], False)
        self.ab.dateien()
        os.remove(os.path.join(ablage, ".aufgeraeumt"))
        r = subprocess.run(php + ["-r", skript], capture_output=True, text=True, env=env, timeout=60)
        self.assertIn("fertig", r.stdout, r.stdout + r.stderr)
        self.assertFalse(os.path.exists(pfad))


if __name__ == "__main__":
    unittest.main()
