"""MP4 faststart (A1675): Verzeichnis (moov) vor die Daten, Chunk-Adressen mitziehen – nur Umpacken. Und: Bilder und Videos
gehen ohne „sandbox“ hinaus (Safari/iOS spielt sonst keine Videos, WebKit-Bug 225865), SVG/Mockup bleiben abgeschottet."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import struct
import unittest

from amw import mp4

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def block(typ, inhalt):
    return struct.pack(">I4s", 8 + len(inhalt), typ) + inhalt


def stco(adressen, breit=False):
    fmt = ">Q" if breit else ">I"
    return block(b"co64" if breit else b"stco", b"\0\0\0\0" + struct.pack(">I", len(adressen)) + b"".join(struct.pack(fmt, a) for a in adressen))


def film(moov_vorn=False, breit=False):
    """ftyp · mdat (drei Proben) · moov mit Adressen der Proben – oder moov vorn."""
    ftyp = block(b"ftyp", b"isom\0\0\0\0isomavc1")
    proben = [b"A" * 40, b"B" * 25, b"C" * 33]
    mdat_inhalt = b"".join(proben)

    def moov_mit(basis):
        adressen, p = [], basis
        for x in proben:
            adressen.append(p)
            p += len(x)
        stbl = block(b"stbl", block(b"stsd", b"\0" * 16) + stco(adressen, breit))
        return block(b"moov", block(b"mvhd", b"\0" * 100) + block(b"trak", block(b"mdia", block(b"minf", stbl))))

    if moov_vorn:
        laenge = len(moov_mit(0))
        return ftyp + moov_mit(len(ftyp) + laenge + 8) + block(b"mdat", mdat_inhalt), proben
    return ftyp + block(b"mdat", mdat_inhalt) + moov_mit(len(ftyp) + 8), proben


def adressen(roh):
    aus = []

    def gehen(s, e):
        for t, a, k, ee in mp4._bloecke(roh, s, e):
            if t in mp4.BEHAELTER:
                gehen(a + k, ee)
            elif t in (b"stco", b"co64"):
                w = 4 if t == b"stco" else 8
                n = struct.unpack(">I", roh[a + k + 4:a + k + 8])[0]
                aus.extend(struct.unpack(">I" if w == 4 else ">Q", roh[a + k + 8 + i * w:a + k + 8 + (i + 1) * w])[0] for i in range(n))
    m = next(x for x in mp4._bloecke(roh) if x[0] == b"moov")
    gehen(m[1] + 8, m[3])
    return aus


class Schnellstart(unittest.TestCase):
    def test_moov_nach_vorn_und_adressen_stimmen(self):
        for breit in (False, True):
            with self.subTest(co64=breit):
                roh, proben = film(breit=breit)
                self.assertFalse(mp4.moov_vorn(roh))
                neu = mp4.schnellstart(roh)
                self.assertTrue(mp4.moov_vorn(neu))
                self.assertEqual(len(neu), len(roh))
                self.assertEqual([neu[a:a + len(p)] for a, p in zip(adressen(neu), proben)], proben)   # jede Adresse trifft ihre Probe
                self.assertEqual(mp4.schnellstart(neu), neu)                                           # zweimal: nichts mehr zu tun

    def test_schon_vorn_oder_unsicher_bleibt_unveraendert(self):
        vorn, proben = film(moov_vorn=True)
        self.assertEqual([vorn[a:a + len(p)] for a, p in zip(adressen(vorn), proben)], proben)
        self.assertIs(mp4.schnellstart(vorn), vorn)
        for kaputt in (b"", b"\0\0\0\x20ftyp", film()[0][:-5], b"x" * 100):
            self.assertIs(mp4.schnellstart(kaputt), kaputt)

    def test_ablegen_stellt_um(self):
        import tempfile
        from amw import db, dokumente
        with tempfile.TemporaryDirectory() as ordner:
            alt = os.environ.get("AMW_DB")
            os.environ["AMW_DB"] = os.path.join(ordner, "amw.db")
            try:
                con = db.anlegen()
                with db.schreiben(con):
                    pid = db.einfuegen(con, "projekt", name="P", angelegt_utc=db.jetzt())
                from amw import kern
                kern.agent_neu(con, pid, "TL", rolle="lead")
                pfad = os.path.join(ordner, "film.mp4")
                with open(pfad, "wb") as f:
                    f.write(film()[0])
                did = dokumente.ablegen(con, pid, "TL", pfad, "Film")
                roh, endung = dokumente.inhalt(con, pid, did)[:2]
                self.assertEqual(endung, ".mp4")
                self.assertTrue(mp4.moov_vorn(roh))
                con.close()
            finally:
                if alt is None:
                    os.environ.pop("AMW_DB", None)
                else:
                    os.environ["AMW_DB"] = alt


class OhneSandbox(unittest.TestCase):
    def test_online_und_pc_gleiche_regel(self):
        with open(os.path.join(WURZEL, "web", "api.php"), encoding="utf-8") as f:
            api = f.read()
        self.assertIn("} elseif (!in_array($vorschau, ['pdf', 'video'], true) && !($vorschau === 'bild' && $endung !== '.svg')) {", api)
        self.assertIn("header('X-Content-Type-Options: nosniff');", api)
        with open(os.path.join(WURZEL, "amw", "workbench.py"), encoding="utf-8") as f:
            pc = f.read()
        self.assertIn('elif vorschau not in ("pdf", "video") and not (vorschau == "bild" and endung != ".svg"):', pc)


if __name__ == "__main__":
    unittest.main()
