"""Online: Was der Mensch erledigt hat, bleibt weg – auch in den Sekunden, in denen der PC die Eingabe schon ausgeführt,
die neue Ansicht aber noch nicht hochgeladen hat (vorher: verschwindet → taucht wieder auf → verschwindet). Mit dem echten
PHP der Seite gegen eine SQLite-Datei: Ansicht /api/start mit zwei Nachrichten an den Menschen, „gelesen“ im Briefkasten."""
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from amw import abgleich

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHP = shutil.which("php")


@unittest.skipUnless(PHP, "PHP nicht installiert")
class Briefkasten(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.online = os.path.join(self.ordner.name, "online.db")
        self.sp = abgleich.SqliteSpeicher(self.online)
        self.sp.ausfuehren([(s, []) for s in abgleich.SCHEMA])
        abgleich.nachruesten(self.sp)
        self.konfig = os.path.join(self.ordner.name, "amw-konfig.php")
        with open(self.konfig, "w", encoding="utf-8") as f:
            f.write(f"<?php return ['sqlite' => {json.dumps(self.online.replace(os.sep, '/'))}, 'benutzer' => 'p', 'passwort_hash' => 'x'];\n")

    def eingang(self, status, zeit, erledigt=None, projekt="P1", ids=(5,)):
        self.sp.ausfuehren([("INSERT INTO eingang (zeit_utc, weg, daten, status, erledigt_utc, projekt) VALUES (?, '/api/gelesen', ?, ?, ?, ?)",
                             [zeit, json.dumps({"ids": list(ids)}), status, erledigt, projekt])])

    def wirkt(self, stand):
        datei = os.path.join(self.ordner.name, "probe.php")
        with open(datei, "w", encoding="utf-8") as f:
            f.write("<?php require getenv('AMW_LIB'); echo json_encode(briefkasten_wirkt('P1', " + json.dumps(stand) + "));")
        env = {**os.environ, "AMW_KONFIG": self.konfig, "AMW_LIB": os.path.join(WURZEL, "web", "inc", "lib.php").replace(os.sep, "/")}
        r = subprocess.run([PHP, "-d", "extension=pdo_sqlite", "-d", "extension=mbstring", datei], capture_output=True, text=True, env=env, timeout=60)
        if "could not find driver" in r.stdout + r.stderr:
            self.skipTest("PHP ohne pdo_sqlite")
        try:
            return [json.loads(d)["ids"] for _, d in json.loads(r.stdout.strip().splitlines()[-1])]
        except (ValueError, IndexError):
            self.fail(r.stdout + r.stderr)

    def test_erledigt_aber_ansicht_noch_alt_bleibt_weg(self):
        stand = "2026-11-12T06:07:40Z"                              # Ansicht mit Nachricht 5, hochgeladen vor dem Klick
        self.eingang("neu", "2026-11-12T06:07:45Z")
        self.assertEqual(self.wirkt(stand), [[5]])                  # im Briefkasten: ausgeblendet (wie bisher)
        self.sp.ausfuehren([("UPDATE eingang SET status = 'erledigt', erledigt_utc = '2026-11-12T06:07:56Z'", [])])
        self.assertEqual(self.wirkt(stand), [[5]])                  # PC hat ausgeführt, neue Ansicht noch nicht oben: weiter weg
        self.assertEqual(self.wirkt("2026-11-12T06:08:01Z"), [])    # neue Ansicht da (ohne Nachricht 5): nichts mehr zu tun

    def test_fehler_und_andere_projekte_wirken_nicht(self):
        stand = "2026-11-12T06:00:00Z"
        self.eingang("fehler", "2026-11-12T06:01:00Z", "2026-11-12T06:01:05Z", ids=(7,))     # am PC abgewiesen: wieder zeigen
        self.eingang("neu", "2026-11-12T06:02:00Z", projekt="P2", ids=(8,))                  # anderes Projekt
        self.eingang("neu", "2026-11-12T06:03:00Z", projekt=None, ids=(9,))                  # ohne Projekt (alte Seite): gilt
        self.eingang("erledigt", "2026-11-12T05:58:00Z", "2026-11-12T05:59:00Z", ids=(4,))   # schon vor der Ansicht erledigt
        self.assertEqual(self.wirkt(stand), [[9]])


if __name__ == "__main__":
    unittest.main()
