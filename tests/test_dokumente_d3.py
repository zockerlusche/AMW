"""Tests für Stufe D3: selbst berichtigen (mit Konflikt), Hochladen am PC und vom Handy (über den Speicher, auch mit der
PHP-Seite), Einsammeln mit Freigabe, Varianten an Optionen einer Frage, Brücke."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import base64
import hashlib
import json
import os
import shutil
import subprocess
import unittest

from amw import abgleich, aktionen, cli, dokumente, einsammeln, kern, workbench
from test_dokumente import Grund

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(256)) * 1200          # ~300 KB: zwei Teile


def an(con, agent):
    return [r[0] for r in con.execute("SELECT n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ?"
                                      " ORDER BY n.id", (agent,))]


class Berichtigen(Grund):
    def test_neue_version_meldung_und_konflikt(self):
        did = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("b.md", "# Bericht\nalt"), "Bericht", "bericht")
        r = aktionen.ausfuehren(self.con, self.pid, "/api/dokument/text", {"id": did, "basis": 1, "text": "# Bericht\nneu", "notiz": "Tippfehler"})
        self.assertEqual(r, {"version": 2})
        d = dokumente.dokument(self.con, self.pid, did)
        self.assertEqual((d["versionen"][-1]["von"], d["versionen"][-1]["notiz"]), ("Entwickler", "Tippfehler"))
        self.assertEqual(dokumente.inhalt(self.con, self.pid, did)[0], "# Bericht\nneu".encode())
        self.assertIn(f"D{did} „Bericht“ berichtigt: v2", an(self.con, "CC1"))           # Verfasser erfährt es
        # Agent legt inzwischen v3 ab – wer noch auf v2 aufbaut, überschreibt nichts
        dokumente.version(self.con, self.pid, "CC1", did, self.datei("b3.md", "# Bericht\nvom Agenten"))
        with self.assertRaisesRegex(aktionen.Ungueltig, "Inzwischen gibt es v3"):
            aktionen.ausfuehren(self.con, self.pid, "/api/dokument/text", {"id": did, "basis": 2, "text": "mein Text"})
        for daten, fehler in (({"basis": 3, "text": "# Bericht\nvom Agenten"}, "Nichts geändert"), ({"basis": 3, "text": "  "}, "leer"),
                              ({"basis": 3, "text": "key sk-ant-" + "x" * 30}, "Schlüssel")):
            with self.assertRaisesRegex(aktionen.Ungueltig, fehler):
                aktionen.ausfuehren(self.con, self.pid, "/api/dokument/text", {"id": did, **daten})
        aktionen.ausfuehren(self.con, self.pid, "/api/dokument/text", {"id": did, "basis": 3, "text": "x", "melden": False})
        self.assertEqual(len(an(self.con, "CC1")), 1)                                       # ohne Meldung
        bild = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("s.png", PNG), "Bild", "bild")
        with self.assertRaisesRegex(aktionen.Ungueltig, "kein Text"):
            aktionen.ausfuehren(self.con, self.pid, "/api/dokument/text", {"id": bild, "basis": 1, "text": "x"})


def teile(roh):
    return [roh[i:i + dokumente.HOCH_TEIL] for i in range(0, len(roh), dokumente.HOCH_TEIL)] or [b""]


class HochladenAmPc(Grund):
    def hoch(self, roh, name, sha=None):
        t = teile(roh)
        hid = aktionen.ausfuehren(self.con, self.pid, "/api/hochladen", {"schritt": "start", "name": name, "groesse": len(roh),
                                                                          "sha": sha or hashlib.sha256(roh).hexdigest(), "teile": len(t)})["id"]
        for i, x in enumerate(t):
            aktionen.ausfuehren(self.con, self.pid, "/api/hochladen", {"schritt": "teil", "id": hid, "nr": i, "inhalt": base64.b64encode(x).decode()})
        return hid

    def test_in_teilen_zum_dokument(self):
        hid = self.hoch(PNG, "Foto.png")
        r = aktionen.ausfuehren(self.con, self.pid, "/api/dokument/neu", {"hoch": hid, "titel": "", "art": "", "aufgabe": None, "bogen": self.bid})
        d = dokumente.dokument(self.con, self.pid, r["dokument"])
        self.assertEqual((d["titel"], d["art"], d["bezug_art"], d["angelegt_von"], d["online"]), ("Foto", "bild", "bogen", "Entwickler", 0))
        self.assertEqual(dokumente.inhalt(self.con, self.pid, d["id"])[0], PNG)
        self.assertFalse(os.listdir(dokumente.hoch_ordner()))                               # Teile weg

    def test_beschaedigt_falsches_format_und_nur_am_pc(self):
        hid = self.hoch(PNG, "x.png", sha="0" * 64)
        with self.assertRaisesRegex(aktionen.Ungueltig, "beschädigt"):
            aktionen.ausfuehren(self.con, self.pid, "/api/dokument/neu", {"hoch": hid})
        for daten in ({"schritt": "start", "name": "x.exe", "groesse": 3, "sha": "0" * 64, "teile": 1},
                      {"schritt": "start", "name": "x.png", "groesse": 3, "sha": "0" * 64, "teile": 2},
                      {"schritt": "teil", "id": "../../x", "nr": 0, "inhalt": ""}):
            with self.assertRaises(aktionen.Ungueltig):
                aktionen.ausfuehren(self.con, self.pid, "/api/hochladen", daten)
        with self.assertRaises(aktionen.Ungueltig):                                         # aus dem Netz nicht direkt
            aktionen.ausfuehren(self.con, self.pid, "/api/hochladen", {"schritt": "start"}, kanal="netz")
        hid = self.hoch("# Notiz mit sk-ant-{}".format("y" * 30).encode(), "n.md")
        with self.assertRaisesRegex(aktionen.Ungueltig, "Schlüssel"):
            aktionen.ausfuehren(self.con, self.pid, "/api/dokument/neu", {"hoch": hid})


class HochladenVomHandy(Grund):
    def setUp(self):
        super().setUp()
        self.online = os.path.join(self.ordner.name, "online.db")
        self.sp = abgleich.SqliteSpeicher(self.online)
        self.ab = abgleich.Abgleich(self.con, self.sp, self.pid)
        self.ab.schema()

    def zeilen(self, sql, *args):
        return self.sp.ausfuehren([(sql, list(args))])[0]

    def ablegen_wie_php(self, roh, name, abgelegt=False):
        """So legt web/api.php einen Upload ab (hoch, hoch_teil, eingang)."""
        hid = os.urandom(16).hex()
        sha = hashlib.sha256(roh).hexdigest()
        t = teile(roh)
        anw = [("INSERT INTO hoch (id, name, endung, groesse, sha, teile, zeit_utc) VALUES (?, ?, ?, ?, ?, ?, ?)",
                [hid, name, os.path.splitext(name)[1], len(roh), sha, len(t), "2099-01-01T00:00:00Z"])]
        anw += [("INSERT INTO hoch_teil (id, nr, inhalt) VALUES (?, ?, ?)", [hid, i, base64.b64encode(x).decode()]) for i, x in enumerate(t)]
        if abgelegt:
            anw.append(("INSERT INTO datei (sha, endung, groesse, teile, status, zeit_utc) VALUES (?, ?, ?, 0, 'abgelegt', ?)",
                        [sha, os.path.splitext(name)[1], len(roh), "2099-01-01T00:00:00Z"]))
        anw.append(("INSERT INTO eingang (zeit_utc, weg, daten) VALUES (?, ?, ?)",
                    ["2099-01-01T00:00:00Z", "/api/dokument/neu", json.dumps({"hoch": hid, "titel": "Tafel", "online": True, "frage": None})]))
        self.sp.ausfuehren(anw)
        return hid, sha

    def test_briefkasten_legt_an_und_raeumt_auf(self):
        hid, sha = self.ablegen_wie_php(PNG, "IMG_1.jpg", abgelegt=True)
        self.assertEqual(self.ab.eingang(), 1)
        self.assertEqual(self.zeilen("SELECT status FROM eingang"), [["erledigt"]])
        d = dokumente.liste(self.con, self.pid)[0]
        self.assertEqual((d["titel"], d["art"], d["online"], d["angelegt_von"]), ("Tafel", "bild", 1, "Entwickler"))
        self.assertEqual(self.zeilen("SELECT count(*) FROM hoch_teil"), [[0]])
        self.assertEqual(self.zeilen("SELECT count(*) FROM hoch"), [[0]])
        self.assertEqual(self.ab.dateien(), 0)                     # die Seite hat die Datei schon – nicht noch einmal hoch

    def test_nicht_online_wird_abgemeldet_und_fehler_raeumt_auch_auf(self):
        hid, sha = self.ablegen_wie_php(PNG, "a.png", abgelegt=True)
        self.sp.ausfuehren([("UPDATE eingang SET daten = ?", [json.dumps({"hoch": hid, "online": False})])])
        self.ab.eingang()
        self.assertEqual(self.ab.dateien(), 1)                     # abgemeldet → die Seite löscht ihre Kopie
        self.assertEqual(self.zeilen("SELECT count(*) FROM datei"), [[0]])
        hid, _ = self.ablegen_wie_php(b"kaputt", "b.png")
        self.sp.ausfuehren([("UPDATE hoch SET sha = ? WHERE id = ?", ["1" * 64, hid])])
        self.ab.eingang()
        self.assertEqual(self.zeilen("SELECT status FROM eingang ORDER BY id DESC LIMIT 1"), [["fehler"]])
        self.assertEqual(self.zeilen("SELECT count(*) FROM hoch"), [[0]])

    @unittest.skipUnless(shutil.which("php"), "PHP nicht installiert")
    def test_php_nimmt_teile_an_und_legt_gleich_ab(self):
        konfig = os.path.join(self.ordner.name, "amw-konfig.php")
        with open(konfig, "w", encoding="utf-8") as f:
            f.write(f"<?php return ['sqlite' => {json.dumps(self.online.replace(os.sep, '/'))}, 'benutzer' => 'p', 'passwort_hash' => 'x'];\n")
        ablage = os.path.join(self.ordner.name, "webspace")
        lib = os.path.join(WURZEL, "web", "inc", "lib.php").replace(os.sep, "/")
        sha = hashlib.sha256(PNG).hexdigest()
        t = teile(PNG)
        schritte = [f"$id = hochladen(['schritt' => 'start', 'name' => 'Foto.png', 'groesse' => {len(PNG)}, 'sha' => '{sha}', 'teile' => {len(t)}])['id'];"]
        schritte += [f"hochladen(['schritt' => 'teil', 'id' => $id, 'nr' => {i}, 'inhalt' => '{base64.b64encode(x).decode()}']);" for i, x in enumerate(t)]
        schritte += ["hoch_abschliessen($id);",
                     "try { hochladen(['schritt' => 'start', 'name' => 'x.exe', 'groesse' => 3, 'sha' => str_repeat('0', 64), 'teile' => 1]); }"
                     " catch (InvalidArgumentException $x) { echo 'abgewiesen '; }",
                     "echo 'fertig ', $id;"]
        skript = f"require '{lib}';" + "".join(schritte)
        php = ["php"] + [a for ext in ("pdo_sqlite", "mbstring") for a in ("-d", f"extension={ext}")]
        try:
            datei = os.path.join(self.ordner.name, "probe.php")              # als Datei: die Teile sprengen sonst die Befehlszeile
            with open(datei, "w", encoding="utf-8") as f:
                f.write("<?php " + skript)
            r = subprocess.run(php + [datei], capture_output=True, text=True, timeout=60,
                               env={**os.environ, "AMW_KONFIG": konfig, "AMW_DATEIEN": ablage})
        except OSError as e:
            self.skipTest(f"PHP: {e}")
        if "could not find driver" in r.stdout + r.stderr:
            self.skipTest("PHP ohne pdo_sqlite")
        self.assertIn("abgewiesen fertig", r.stdout, r.stdout + r.stderr)
        hid = r.stdout.split("fertig ")[1].strip()
        with open(os.path.join(ablage, sha[:2], sha + ".png"), "rb") as f:
            self.assertEqual(f.read(), PNG)                       # liegt schon auf dem Webspace
        self.assertEqual(self.zeilen("SELECT status FROM datei"), [["abgelegt"]])
        self.assertFalse(os.path.exists(os.path.join(ablage, ".hoch", hid)))
        self.sp.ausfuehren([("INSERT INTO eingang (zeit_utc, weg, daten) VALUES (?, ?, ?)",
                             ["2099-01-01T00:00:00Z", "/api/dokument/neu", json.dumps({"hoch": hid, "online": True})])])
        self.ab.eingang()
        self.assertEqual(dokumente.inhalt(self.con, self.pid, dokumente.liste(self.con, self.pid)[0]["id"])[0], PNG)
        self.assertEqual(self.ab.dateien(), 0)


class Einsammeln(Grund):
    def baum(self):
        w = os.path.join(self.ordner.name, "ablage")
        for i in range(12):                     # Kürzel ab zwei Ziffern (A4 ist eher ein Papierformat als eine Aufgabe)
            aid = kern.aufgabe_neu(self.con, self.pid, "TL", f"Aufgabe {i}", agent="CC1")
        dateien = {"ergebnisse/bericht_pruefung.md": b"# Pruefung", f"ergebnisse/A{aid}_mockup.html": b"<p>x</p>",
                   "ergebnisse/werkzeug.py": b"print(1)", "tmp/kopie.md": b"# alt", "doppelt/schon.md": b"# schon da"}
        dateien.update({f"lauf/frame_{i:04d}.png": PNG[:50] + bytes([i]) for i in range(45)})
        for rel, roh in dateien.items():
            p = os.path.join(w, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "wb") as f:
                f.write(roh)
        os.makedirs(os.path.join(w, ".git"))
        with open(os.path.join(w, ".git", "x.md"), "w") as f:
            f.write("intern")
        dokumente.ablegen(self.con, self.pid, "CC1", os.path.join(w, "doppelt", "schon.md"))
        return w, aid

    def test_liste_vorschlaege(self):
        w, aid = self.baum()
        l = einsammeln.liste(self.con, self.pid, w)
        a = {x["ordner"]: x for x in l["ablagen"]}
        self.assertNotIn(".git", a)
        self.assertEqual((a["tmp"]["vorschlag"], a["lauf"]["vorschlag"]), ("weg", "weg"))
        self.assertIn("Prüflauf", a["lauf"]["grund"])
        self.assertEqual((a["ergebnisse"]["vorschlag"], a["ergebnisse"]["andere"]), ("behalten", 1))
        d = {x["name"]: x for x in a["ergebnisse"]["dateien"]}
        self.assertEqual(d["bericht_pruefung.md"]["art"], "bericht")
        self.assertEqual(d[f"A{aid}_mockup.html"]["art"], "mockup")
        self.assertEqual((d[f"A{aid}_mockup.html"]["bezug_art"], d[f"A{aid}_mockup.html"]["bezug_id"]), ("aufgabe", aid))
        self.assertIn("schon in der AMW", a["doppelt"]["dateien"][0]["grund"])
        self.assertEqual(einsammeln.summe(l)[0], 2)
        self.assertIn("| `lauf` | 45 |", einsammeln.bericht(l))

    def test_melden_erst_nach_freigabe_uebernehmen(self):
        w, aid = self.baum()
        did, fid = einsammeln.melden(self.con, self.pid, "CC1", einsammeln.liste(self.con, self.pid, w))
        d = dokumente.dokument(self.con, self.pid, did)
        self.assertEqual((d["art"], d["bezug_art"], d["bezug_id"]), ("bericht", "frage", fid))
        self.assertTrue(any("Einsammel-Liste" in k for k in an(self.con, "TL")))
        with self.assertRaisesRegex(kern.AmwFehler, "noch nicht beantwortet"):
            einsammeln.uebernehmen(self.con, self.pid, "CC1", fid)
        with open(os.path.join(w, "ergebnisse", "bericht_pruefung.md"), "ab") as f:      # nach der Liste geändert
            f.write(b"\nneu")
        kern.frage_antworten(self.con, self.pid, fid, "option", "A", "seite")
        neu, weg = einsammeln.uebernehmen(self.con, self.pid, "CC1", fid)
        self.assertEqual([r for r, _ in neu], [f"ergebnisse/A{aid}_mockup.html"])
        self.assertEqual(weg, [("ergebnisse/bericht_pruefung.md", "inzwischen geändert – neu auflisten")])
        self.assertEqual(einsammeln.uebernehmen(self.con, self.pid, "CC1", fid)[0], [])    # zweimal: nichts doppelt
        self.assertTrue(os.path.exists(os.path.join(w, "ergebnisse", "werkzeug.py")))       # nichts verschoben

    def test_antwort_b_oder_text_ohne_auswahl(self):
        w, _ = self.baum()
        _, f1 = einsammeln.melden(self.con, self.pid, "CC1", einsammeln.liste(self.con, self.pid, w))
        kern.frage_antworten(self.con, self.pid, f1, "option", "B", "seite")
        with self.assertRaisesRegex(kern.AmwFehler, "mit B beantwortet"):
            einsammeln.uebernehmen(self.con, self.pid, "CC1", f1)
        _, f2 = einsammeln.melden(self.con, self.pid, "CC1", einsammeln.liste(self.con, self.pid, w))
        kern.frage_antworten(self.con, self.pid, f2, "text", "nur die Ergebnisse", "seite")
        with self.assertRaisesRegex(kern.AmwFehler, "--nur"):
            einsammeln.uebernehmen(self.con, self.pid, "CC1", f2)
        self.assertEqual(len(einsammeln.uebernehmen(self.con, self.pid, "CC1", f2, ["ergebnisse"])[0]), 2)

    def test_befehl_nur_lesen(self):
        w, _ = self.baum()
        import contextlib
        import io
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus):
            self.assertEqual(cli.main(["dokument", "einsammeln", w, "--von", "CC1"]), 0)
        self.assertIn("Vorschlag: 2 übernehmen", aus.getvalue())
        self.assertEqual(self.con.execute("SELECT count(*) FROM frage").fetchone()[0], 0)


class Varianten(Grund):
    def test_anhang_je_option_in_der_frage(self):
        alt = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("b.png", PNG[:900]), "Entwurf B", "bild")
        args = ["frage", "neu", "--an", "entwickler", "--kurz", "Welche Leiste?", "--option", "A=oben", "--option", "B=unten",
                "--empfehlung", "A", "--grund", "kürzer", "--geprueft", "keine Treffer", "--anhang", f"A={self.datei('a.png', PNG[:800])}", "--anhang", f"B=D{alt}",
                "--von", "TL"]                                     # der Lead fragt direkt (Agenten: über den Lead, 1.30.0)
        self.assertEqual(cli.main(args), 0)
        f = workbench.daten_fragen(self.con, self.pid)[0]
        a, b = f["optionen"]
        self.assertEqual((a["anhang"]["vorschau"], a["anhang"]["online"], b["anhang"]["id"]), ("bild", 1, alt))
        self.assertEqual(f["dokumente"], [])                       # Varianten nicht noch einmal als Anhang
        self.assertTrue(dokumente.dokument(self.con, self.pid, alt)["online"])
        for falsch in (["--anhang", "C=D1"], ["--anhang", "A=fehlt.png"]):
            self.assertNotEqual(cli.main(args[:-4] + falsch + ["--von", "TL"]), 0)
        self.assertEqual(self.con.execute("SELECT count(*) FROM frage").fetchone()[0], 1)  # nichts halb angelegt

    def test_bruecke_anhang_nur_aus_dem_eingang(self):
        from amw import bruecke
        eingang = os.path.join(self.ordner.name, "eingang-tl")
        os.makedirs(eingang)
        with self.assertRaises(ValueError):
            bruecke.argumente({"args": ["frage", "neu", "--anhang", f"A={self.datei('x.png', PNG[:10])}"]}, eingang)
        with self.assertRaises(ValueError):
            bruecke.argumente({"args": ["dokument", "ablegen", self.datei("y.md", "x")]}, eingang)
        args = bruecke.argumente({"args": ["frage", "neu", "--anhang", "A=D3", "--anhang", "B=mock/b.html"]}, eingang)
        self.assertIn("A=D3", args)
        self.assertIn(f"B={os.path.realpath(os.path.join(eingang, 'mock', 'b.html'))}", args)


if __name__ == "__main__":
    unittest.main()
