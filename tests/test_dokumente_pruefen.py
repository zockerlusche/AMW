"""Tests für dokumente.hoch_pruefen (Größe und SHA-256 eines Uploads) und dokumente.von_selbst_online
(Projekt-Einstellung dateien_online je Endung)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import hashlib
import unittest

from amw import dokumente, kern


class HochPruefen(unittest.TestCase):
    def setUp(self):
        self.roh = b"Hallo AMW \x00\xff Bytes"
        self.sha = hashlib.sha256(self.roh).hexdigest()

    def test_passend_gibt_bytes_zurueck(self):
        self.assertEqual(dokumente.hoch_pruefen(self.roh, len(self.roh), self.sha), self.roh)

    def test_groesse_als_text(self):
        self.assertEqual(dokumente.hoch_pruefen(self.roh, str(len(self.roh)), self.sha), self.roh)

    def test_leer_passend(self):
        self.assertEqual(dokumente.hoch_pruefen(b"", 0, hashlib.sha256(b"").hexdigest()), b"")

    def test_falsche_groesse(self):
        for groesse in (len(self.roh) - 1, len(self.roh) + 1, 0):
            with self.subTest(groesse=groesse), self.assertRaises(kern.AmwFehler) as f:
                dokumente.hoch_pruefen(self.roh, groesse, self.sha)
            self.assertIn("Prüfsumme", str(f.exception))

    def test_falsche_pruefsumme(self):
        for sha in (hashlib.sha256(b"anders").hexdigest(), "", self.sha.upper(), "0" * 64):
            with self.subTest(sha=sha), self.assertRaises(kern.AmwFehler):
                dokumente.hoch_pruefen(self.roh, len(self.roh), sha)

    def test_beides_falsch(self):
        with self.assertRaises(kern.AmwFehler):
            dokumente.hoch_pruefen(self.roh, 1, "abc")

    def test_gleiche_groesse_anderer_inhalt(self):
        anders = bytes(len(self.roh))
        with self.assertRaises(kern.AmwFehler):
            dokumente.hoch_pruefen(anders, len(self.roh), self.sha)


class VonSelbstOnline(unittest.TestCase):
    BILDER = (".png", ".jpg", ".jpeg", ".webp", ".gif", ".svg", ".html", ".htm")
    KEINE_BILDER = (".md", ".txt", ".pdf", ".mp4", ".webm", ".docx", ".xlsx")

    def test_alle_immer(self):
        for endung in list(dokumente.FORMATE) + [".unbekannt", ""]:
            with self.subTest(endung=endung):
                self.assertTrue(dokumente.von_selbst_online("alle", endung))

    def test_bilder_nur_bild_und_mockup(self):
        for endung, (_, _, vorschau) in dokumente.FORMATE.items():
            with self.subTest(endung=endung):
                self.assertEqual(dokumente.von_selbst_online("bilder", endung), vorschau in ("bild", "mockup"))

    def test_bilder_feste_endungen(self):
        for endung in self.BILDER:
            with self.subTest(endung=endung):
                self.assertTrue(dokumente.von_selbst_online("bilder", endung))
        for endung in self.KEINE_BILDER:
            with self.subTest(endung=endung):
                self.assertFalse(dokumente.von_selbst_online("bilder", endung))

    def test_aus_und_leer_nie(self):
        for einstellung in ("aus", "", None):
            for endung in list(dokumente.FORMATE) + [".unbekannt"]:
                with self.subTest(einstellung=einstellung, endung=endung):
                    self.assertFalse(dokumente.von_selbst_online(einstellung, endung))

    def test_unbekannte_endung(self):
        for endung in (".exe", ".unbekannt", "", "png", ".PNG"):
            with self.subTest(endung=endung):
                self.assertFalse(dokumente.von_selbst_online("bilder", endung))
                self.assertTrue(dokumente.von_selbst_online("alle", endung))
                self.assertFalse(dokumente.von_selbst_online("aus", endung))

    def test_unbekannte_einstellung_nie(self):
        for einstellung in ("ALLE", "Bilder", "ja"):
            with self.subTest(einstellung=einstellung):
                self.assertFalse(dokumente.von_selbst_online(einstellung, ".png"))


if __name__ == "__main__":
    unittest.main()
