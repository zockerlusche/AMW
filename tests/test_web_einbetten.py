"""Online-Seite: Wer darf was einbetten (1.35.1). Die Seite selbst nie; Dokument-Dateien (Mockup, PDF, Video) nur in der
eigenen Seite. Die Angabe kommt aus PHP – setzt die .htaccess sie zusätzlich, kommt sie doppelt an und der Browser nimmt
die strengere: Das Mockup im Dokument-Fenster blieb leer („darf diese eingebettete Seite nicht öffnen“)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import re
import unittest

WEB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "web")


def lies(*teile):
    with open(os.path.join(WEB, *teile), encoding="utf-8") as f:
        return f.read()


class Einbetten(unittest.TestCase):
    def test_htaccess_setzt_die_angabe_nicht_doppelt(self):
        zeilen = [z for z in lies(".htaccess").splitlines() if not z.strip().startswith("#")]
        self.assertFalse([z for z in zeilen if "X-Frame-Options" in z], "X-Frame-Options gehört nur in PHP")
        self.assertTrue(any("X-Content-Type-Options" in z for z in zeilen))             # die übrigen Kopfzeilen bleiben

    def test_seite_selbst_bleibt_verboten(self):
        lib = lies("inc", "lib.php")
        self.assertIn("header('X-Frame-Options: DENY');", lib)
        self.assertIn("frame-ancestors 'none'", lib)

    def test_dokument_dateien_nur_in_der_eigenen_seite_und_abgeschottet(self):
        api = lies("api.php")
        self.assertIn("header('X-Frame-Options: SAMEORIGIN');", api)
        csp = re.findall(r'header\("Content-Security-Policy: (sandbox[^"]*)"\s*(?:\.\s*"([^"]*)")?\)', api)
        self.assertEqual(len(csp), 2, csp)                                               # Mockup und übrige Vorschau
        for teile in csp:
            ganz = "".join(teile)
            self.assertTrue(ganz.startswith("sandbox"), ganz)                            # Abschottung bleibt
            self.assertIn("default-src 'none'", ganz)
            self.assertIn("frame-ancestors 'self'", ganz)
        self.assertNotIn("allow-same-origin", api)                                       # ein Mockup bekommt nie den Ursprung der Seite


if __name__ == "__main__":
    unittest.main()
