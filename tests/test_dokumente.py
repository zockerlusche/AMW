"""Tests für Dokumente: Ablage mit Versionen, Formate und Schutz, Bezüge, Suche, Kommentar an den Verfasser, Löschen,
Sicherung, Auslieferung in der Workbench (abgeschottet) und Ablegen über die Brücke."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import io
import json
import os
import tempfile
import unittest
import zipfile
from unittest import mock

from amw import aktionen, db, dokumente, kern, planung, verlauf


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.alt_db = os.environ.get("AMW_DB")
        os.environ["AMW_DB"] = os.path.join(self.ordner.name, "amw.db")
        umgebung = mock.patch.dict(os.environ)            # unabhängig von AMW_PROJEKT/AMW_AGENT der Sitzung, die testet
        umgebung.start()
        self.addCleanup(umgebung.stop)
        for k in ("AMW_PROJEKT", "AMW_AGENT"):
            os.environ.pop(k, None)
        self.con = db.anlegen()
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        for k, r in (("TL", "lead"), ("CC1", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        self.bid = planung.bogen_neu(self.con, self.pid, "TL", "Login")

    def tearDown(self):
        self.con.close()
        if self.alt_db is None:
            os.environ.pop("AMW_DB", None)
        else:
            os.environ["AMW_DB"] = self.alt_db
        self.ordner.cleanup()

    def datei(self, name, inhalt):
        p = os.path.join(self.ordner.name, "quelle", name)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "wb") as f:
            f.write(inhalt if isinstance(inhalt, bytes) else inhalt.encode("utf-8"))
        return p


class Ablage(Grund):
    def test_ablegen_version_suche_und_bezug(self):
        did = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("bericht.md", "# Bericht\nSpeicher **gelb**"),
                                "Prüfbericht", "bericht", bogen=self.bid)
        d = dokumente.dokument(self.con, self.pid, did)
        self.assertEqual((d["bezug_art"], d["bezug_id"], d["versionen"][0]["vorschau"]), ("bogen", self.bid, "text"))
        with self.assertRaises(kern.AmwFehler):                                         # gleicher Inhalt
            dokumente.version(self.con, self.pid, "CC1", did, self.datei("bericht.md", "# Bericht\nSpeicher **gelb**"))
        self.assertEqual(dokumente.version(self.con, self.pid, "CC1", did, self.datei("b2.md", "# Bericht\nSpeicher grün"), "neu"), 2)
        self.assertEqual([x["id"] for x in dokumente.liste(self.con, self.pid, q="gelb")], [did])     # alte Versionen zählen mit
        self.assertEqual(dokumente.liste(self.con, self.pid, bezug_art="bogen", bezug_id=self.bid)[0]["version"], 2)
        self.assertEqual(dokumente.zaehler(self.con, self.pid, "bogen", self.bid), 1)
        roh, endung = dokumente.inhalt(self.con, self.pid, did, 1)
        self.assertEqual((roh.decode(), endung), ("# Bericht\nSpeicher **gelb**", ".md"))
        ereignisse = verlauf.verlauf(self.con, self.pid, "2000-01-01T00:00:00Z", arten=["dokument"])
        self.assertEqual(sorted(x["zusatz"] for x in ereignisse), ["bericht", "v2"])

    def test_formate_groesse_und_geheimnisse(self):
        for name, inhalt in (("x.exe", b"MZ"), ("ohne", b"x")):
            with self.assertRaises(kern.AmwFehler):
                dokumente.ablegen(self.con, self.pid, "CC1", self.datei(name, inhalt))
        for geheim in ("key sk-ant-api03-abcdefghijklmnopqrstuvwxyz", "-----BEGIN RSA PRIVATE KEY-----", "ghp_" + "a" * 36):
            with self.assertRaises(kern.AmwFehler):
                dokumente.ablegen(self.con, self.pid, "CC1", self.datei("g.md", geheim))
        with self.assertRaises(kern.AmwFehler):                                         # auch im Skript eines Mockups
            dokumente.ablegen(self.con, self.pid, "CC1", self.datei("m.html", "<script>var k='sk-abcdefghijklmnopqrstuvwxyz12'</script>"))
        with mock.patch.object(dokumente, "GROESSE_MAX", 10), self.assertRaises(kern.AmwFehler):
            dokumente.ablegen(self.con, self.pid, "CC1", self.datei("gross.png", b"x" * 11))
        with self.assertRaises(kern.AmwFehler):
            dokumente.ablegen(self.con, self.pid, "CC1", self.datei("a.md", "x"), aufgabe=999)
        with self.assertRaises(kern.AmwFehler):
            dokumente.ablegen(self.con, self.pid, "CC1", self.datei("a.md", "x"), bogen=self.bid, aufgabe=1)
        self.assertEqual(self.con.execute("SELECT count(*) FROM dokument").fetchone()[0], 0)

    def test_suchtext_aus_html_und_docx(self):
        h = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("m.html", "<h1>Start</h1><script>geheimeLogik()</script><p>Variante B</p>"))
        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w") as z:
            z.writestr("word/document.xml", "<w:document><w:p><w:t>Rechnung Hoster</w:t></w:p></w:document>")
        w = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("r.docx", puffer.getvalue()), art="quelle")
        self.assertEqual([x["id"] for x in dokumente.liste(self.con, self.pid, q="Variante B")], [h])
        self.assertEqual(dokumente.liste(self.con, self.pid, q="geheimeLogik"), [])
        self.assertEqual([x["id"] for x in dokumente.liste(self.con, self.pid, q="Rechnung Hoster")], [w])

    def test_gleicher_inhalt_einmal_loeschen_nur_entwickler(self):
        a = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("a.png", b"\x89PNG bild"))
        b = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("b.png", b"\x89PNG bild"))
        v = dokumente.dokument(self.con, self.pid, a)["versionen"][0]
        pfad = dokumente.datei_pfad(v["sha256"], v["endung"])
        self.assertTrue(os.path.exists(pfad))
        with self.assertRaises(kern.AmwFehler):
            dokumente.loeschen(self.con, self.pid, "TL", a)
        self.assertEqual(dokumente.loeschen(self.con, self.pid, "Entwickler", a), 0)    # b braucht die Datei noch
        self.assertTrue(os.path.exists(pfad))
        self.assertEqual(dokumente.loeschen(self.con, self.pid, "Entwickler", b), 1)
        self.assertFalse(os.path.exists(pfad))
        with self.assertRaises(kern.AmwFehler):
            dokumente.inhalt(self.con, self.pid, a)
        with self.assertRaises(Exception):                                             # Verlauf: Zeile bleibt
            self.con.execute("DELETE FROM dokument WHERE id = ?", (a,))
        self.assertEqual(dokumente.liste(self.con, self.pid, status=None)[0]["status"], "geloescht")

    def test_kommentar_und_ueberarbeiten_gehen_an_den_verfasser(self):
        did = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("e.md", "Entwurf"), art="entwurf")
        dokumente.melden(self.con, self.pid, "Entwickler", did, "Bitte kürzer")
        nid, namen = dokumente.melden(self.con, self.pid, "Entwickler", did, "Abschnitt 2 neu", ueberarbeiten=True)
        self.assertEqual(namen, ["CC1"])
        g = dokumente.gespraech(self.con, self.pid, did)
        self.assertEqual([(x["art"], x["an"]) for x in g], [("meldung", "CC1"), ("auftrag", "CC1")])
        self.assertIn(f"amw dokument version {did}", g[1]["text"])
        nid, namen = dokumente.melden(self.con, self.pid, "CC1", did, "erledigt?")      # Verfasser selbst → an den Lead
        self.assertEqual(namen, ["TL"])
        with self.assertRaises(kern.AmwFehler):
            dokumente.melden(self.con, self.pid, "Entwickler", did, " ")

    def test_zuordnen_archivieren_online_und_sichern(self):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "Login bauen")
        did = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("s.png", b"\x89PNG"), "Standbild", "bild")
        d = dokumente.setzen(self.con, self.pid, "TL", did, titel="Standbild Login", aufgabe=f"A{aid}")
        self.assertEqual((d["titel"], d["bezug_art"], d["bezug_id"]), ("Standbild Login", "aufgabe", aid))
        self.assertIsNone(dokumente.setzen(self.con, self.pid, "TL", did, bogen=None)["bezug_art"])
        dokumente.status_setzen(self.con, self.pid, "TL", did, "archiviert")
        self.assertEqual(dokumente.liste(self.con, self.pid), [])
        self.assertEqual(len(dokumente.liste(self.con, self.pid, status="archiviert")), 1)
        dokumente.online_setzen(self.con, self.pid, "Entwickler", did)
        self.assertEqual(dokumente.dokument(self.con, self.pid, did)["online"], 1)
        ziel = os.path.join(self.ordner.name, "sicherung")
        self.assertEqual(dokumente.sichern(ziel), 1)
        self.assertEqual(dokumente.sichern(ziel), 0)                                      # nur Fehlendes

    def test_aktionen_loeschen_nur_am_pc(self):
        did = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("a.md", "x"))
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.pid, "/api/dokument/loeschen", {"id": did}, kanal="online")
        r = aktionen.ausfuehren(self.con, self.pid, "/api/dokument/kommentar", {"id": did, "text": "gut"}, kanal="online")
        self.assertEqual(r["an"], ["CC1"])
        aktionen.ausfuehren(self.con, self.pid, "/api/dokument/setzen", {"id": did, "bogen": self.bid})
        self.assertEqual(dokumente.dokument(self.con, self.pid, did)["bezug_id"], self.bid)
        self.assertEqual(aktionen.ausfuehren(self.con, self.pid, "/api/dokument/loeschen", {"id": did})["dateien"], 1)


class Workbench(Grund):
    def setUp(self):
        super().setUp()
        import urllib.request
        from amw import workbench
        from tests.test_workbench import freier_port
        self.port = freier_port()
        self.srv = workbench.starten(self.port)
        self.lese = lambda weg: urllib.request.urlopen(f"http://127.0.0.1:{self.port}{weg}", timeout=5)

    def tearDown(self):
        self.srv.shutdown()
        self.srv.server_close()
        super().tearDown()

    def test_liste_detail_und_auslieferung_abgeschottet(self):
        m = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("m.html", "<p>Mockup</p>"), "Variante", "mockup", bogen=self.bid)
        s = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("s.svg", "<svg xmlns='http://www.w3.org/2000/svg'/>"))
        t = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("t.md", "# Titel"))
        puffer = io.BytesIO()
        with zipfile.ZipFile(puffer, "w") as z:
            z.writestr("word/document.xml", "<w:t>x</w:t>")
        w = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("w.docx", puffer.getvalue()))
        liste = json.loads(self.lese("/api/dokumente").read())
        self.assertEqual(len(liste["dokumente"]), 4)
        self.assertNotIn("sha256", liste["dokumente"][0])
        self.assertEqual(json.loads(self.lese(f"/api/dokumente?bezug_art=bogen&bezug_id={self.bid}").read())["dokumente"][0]["id"], m)
        d = json.loads(self.lese(f"/api/dokument?id={t}").read())
        self.assertEqual(d["text"], "# Titel")
        r = self.lese(f"/api/dokument/datei?id={m}")
        self.assertIn("sandbox allow-scripts", r.headers["Content-Security-Policy"])
        self.assertEqual(r.headers["X-Content-Type-Options"], "nosniff")
        r = self.lese(f"/api/dokument/datei?id={s}")
        self.assertTrue(r.headers["Content-Security-Policy"].startswith("sandbox;"))
        self.assertTrue(self.lese(f"/api/dokument/datei?id={w}").headers["Content-Disposition"].startswith("attachment"))
        seite = self.lese("/").read().decode()
        self.assertIn("frame-src 'self'", self.lese("/").headers["Content-Security-Policy"])
        self.assertIn("sichtDokumente", seite)
        suche = json.loads(self.lese("/api/suche?q=Variante").read())
        self.assertIn(f"D{m}", [x["ref"] for x in suche])


class Bruecke(Grund):
    def test_ablegen_ueber_die_bruecke_nur_aus_dem_eingang(self):
        from amw import bruecke
        eingang = os.path.join(self.ordner.name, "eingang-tl")
        os.makedirs(os.path.join(eingang, "plan"))
        with open(os.path.join(eingang, "plan", "entwurf.md"), "w", encoding="utf-8") as f:
            f.write("# Plan")
        args = bruecke.argumente({"befehl": "dokument", "aktion": "ablegen", "datei": "plan/entwurf.md", "titel": "Plan", "bogen": self.bid},
                                 eingang)
        self.assertEqual(args[:2], ["dokument", "ablegen"])
        from amw import cli
        self.assertEqual(cli.main(args), 0)
        self.assertEqual(dokumente.liste(self.con, self.pid)[0]["angelegt_von"], "TL")
        with self.assertRaises(ValueError):
            bruecke.argumente({"befehl": "dokument", "aktion": "ablegen", "datei": self.datei("x.md", "x")}, eingang)


MP4 = b"\0\0\0\x18ftypisom\0\0\x02\0isomavc1" + b"\0\0\0\x08free" + bytes(range(256)) * 40 + b"moov....avc1"


class Video(Workbench):
    """GlassWorld-TL #18867: Videos (Abnahmen, Look-Prototyp) als Dokument – ablegen, prüfen, abspielen mit Spulen."""

    def test_ablegen_pruefen_und_abspielen(self):
        v = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("probe.mp4", MP4), "Abnahme Level 1")
        w = dokumente.ablegen(self.con, self.pid, "CC1", self.datei("probe.webm", b"\x1a\x45\xdf\xa3" + b"\0" * 64))
        d = dokumente.dokument(self.con, self.pid, v)
        self.assertEqual((d["art"], d["versionen"][0]["vorschau"]), ("ergebnis", "video"))
        self.assertEqual(dokumente.dokument(self.con, self.pid, w)["versionen"][0]["format"], "video")
        for name, roh, text in (("falsch.mp4", b"<html>kein Video</html>", "kein MP4"), ("falsch.webm", MP4, "kein WEBM"),
                                ("hevc.mp4", b"\0\0\0\x18ftypisom\0\0\x02\0isomhvc1", "H.264")):
            with self.assertRaises(kern.AmwFehler, msg=name) as e:
                dokumente.ablegen(self.con, self.pid, "CC1", self.datei(name, roh))
            self.assertIn(text, str(e.exception))
        import urllib.request
        r = self.lese(f"/api/dokument/datei?id={v}")
        self.assertEqual((r.status, r.headers["Content-Type"], r.headers["Accept-Ranges"]), (200, "video/mp4", "bytes"))
        self.assertEqual(r.read(), MP4)
        teil = lambda bereich: urllib.request.urlopen(urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/dokument/datei?id={v}", headers={"Range": bereich}), timeout=5)
        r = teil("bytes=4-11")
        self.assertEqual((r.status, r.headers["Content-Range"], r.read()), (206, f"bytes 4-11/{len(MP4)}", b"ftypisom"))
        self.assertEqual(teil("bytes=-4").read(), b"avc1")
        self.assertEqual(teil(f"bytes={len(MP4) - 2}-").read(), b"c1")
        with self.assertRaises(urllib.error.HTTPError) as e:
            teil(f"bytes={len(MP4)}-")
        self.assertEqual(e.exception.code, 416)
        self.assertIn("media-src 'self'", self.lese("/").headers["Content-Security-Policy"])
        from amw import workbench
        self.assertEqual([workbench._bereich(k, 10) for k in (None, "bytes=0-", "bytes=2-3", "bytes=8-99", "bytes=-3", "bytes=0-1,4-5",
                                                               "bytes=x-", "bytes=10-", "bytes=5-2")],
                         [None, (0, 9), (2, 3), (8, 9), (7, 9), None, None, "falsch", "falsch"])

    def test_online_gleiche_formate(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "web", "inc", "lib.php"), encoding="utf-8") as f:
            php = f.read()
        for endung, (_, typ, vorschau) in dokumente.FORMATE.items():
            if vorschau != "text":
                self.assertIn(f"'{endung}' => ['{typ}', '{vorschau}']", php, endung)
            self.assertIn(f"'{endung}'", php[php.index("const HOCH_ENDUNGEN"):][:400], endung)


if __name__ == "__main__":
    unittest.main()
