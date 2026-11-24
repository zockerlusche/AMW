"""Sperrliste vor dem ersten echten -p-Start (A1872, M50 S3b; Befund D1289, D1258 §5/§6a.3): alles, was einen Arbeiter
abschottet, prüft, startet oder Rechte vergibt, und alle automatisch geladenen Dateien sind für p-Pakete gesperrt – vor dem
Start (Startregel 5) und danach (Diff-Tor, auch in Prüfung C). Die Liste gibt es genau einmal (abnahme.GESPERRT)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import unittest

from amw import abnahme, pruefung_c

PFLICHT = ("amw/arbeiter.py", "amw/waechter.py", "amw/entscheidung.py", "amw/pruefung_c.py", "amw/tokenprognose.py", "amw/db.py",
           "amw/einstellungen.py", "amw/betrieb.py", "amw/laufdienst.py", "amw/belegung.py", "amw/kern.py", "amw/steuerung.py",
           "amw/cli.py", "amw/aktionen.py", "amw/schluessel.py", "amw/versionsnummer.py", "amw/versionshinweise.py", "amw/__main__.py",
           "amw/disponent.py", "amw/rueckmeldung.py", "amw/abnahme.py", "amw/platz.py", "amw/auslieferung.py", "amw/dienst.py",
           "amw/vorlagen/auftrag_p.md", "amw-cli.py", "amw-arbeiter.py", "amw/versionsprobe.py", "amw-versionsprobe.py", "amw/anbieter.py", "amw/anbieter_schluessel.py", "amw/schalter.py", "amw/eignung.py", "amw/sicherung.py", "amw/fertigquelle.py", "amw/urteil.py", "amw/reihenfolge.py", "amw-anbieter-schluessel.py", "amw/gegenlesen.py", "amw-gegenlesen.py", "amw/fragentopf.py", "amw/stil.py", "amw-stil.py", "amw/vorpruefung.py", "amw-vorpruefung.py", "amw/planer.py", "amw-planer.py", "amw/folgen.py", "amw-folgen.py", "amw/verteilen.py", "amw/veroeffentlichung.py", "amw-rueckmeldung.py", "amw-hook.py", "start_dienst.pyw",
           # P274
           "amw/schema.sql", "amw/migration_34.sql", "amw/workbench.py", "amw/abgleich.py", "amw/einrichtung.py", "amw/assistent.py",
           "amw/pruefstufe.py", "amw/schirm.py", "amw/ki.py", "amw/pipe.py", "amw/tray.py", "amw/paket.py", "amw/push.py",
           "amw/wissen.py", "amw/regelwerk.py", "amw/server/nginx-amw.conf", "bin/amw", "werkzeug/x.sh", "web/.htaccess",
           "web/inc/.htaccess", "web/daten/.htaccess", "web/sso.php", "web/inc/sso.php", "web/inc/lib.php")
# P274 Gegenrichtung: Module mit Rechte-/Kanal-/Token-Merkmalen sind gesperrt – oder hier bewusst eingeordnet. Ein neues Modul mit
# solchen Merkmalen fällt auf und muss entschieden werden. (Ob auch diese Fach-Module mit eigener Lead-Sperre gesperrt werden
# sollen, entscheidet der TL – bis dahin: frei, weil ihre Lead-Sperren nur Fach-Aktionen schützen, keine Abschottung/Rechte.)
EINGEORDNET_FREI = {
    "amw/arbeitsliste.py": "Lead-Sperre nur für Reihenfolge der Arbeitsliste",
    "amw/dokumente.py": "secrets.token_hex für Dateinamen, keine Rechte",
    "amw/empfehlung.py": "nur Anzeige (Modell-Empfehlung)",
    "amw/fenster.py": "Lead-Sperre nur für Meldung „Fenster ohne Schirm“",
    "amw/gespraech.py": "Muster zum Ausblenden von Geheimnissen (Anzeige)",
    "amw/messung.py": "Wort „tokens“ in Kostenwerten",
    "amw/planung.py": "Lead-Sperren für Planung (Bögen, Pakete)",
    "amw/platte.py": "Absender Entwickler in Meldungen",
    "amw/runde.py": "Lead-Runde (Nachrichten zwischen Leads)",
    "amw/takt.py": "Lead-Durchgang (nur Lesen/Melden)",
    "amw/termine.py": "Lead-Sperre für Termine",
    "amw/themen.py": "Lead-Sperre für Design-Seiten",
    "amw/abschluss.py": "Abschluss je Meilenstein: wer Nacharbeit anfordert (Lead oder Mensch, Fach-Aktion wie planansicht.py, A2029) – keine Abschottung/Rechte",
    "amw/feinplanung.py": "rollende Feinplanung: wer den freigegebenen Plan startet (Lead oder Mensch, Fach-Aktion wie planansicht.py, A2031) – keine Abschottung/Rechte",
    "amw/pause.py": "Pause für alles: wer sie schaltet (Lead oder Mensch, wie amw halt) – setzt nur Halt und Wächter-Pause, keine Abschottung (A2042)",
    "amw/planansicht.py": "Freigabe-Regeln für Meilensteine und Pläne (Fach-Aktion wie planung.py, K1-Regel B2913) – keine Abschottung/Rechte",
    "amw/tore.py": "Tore abgeleitet, Abschlussbericht, Bestätigung „nichts zu bauen“ durch den Co (Fach-Regel TH154 wie planansicht.py) – keine Abschottung/Rechte",
    "amw/konzept_uebernahme.py": "Lead/Co legen Themen-Entwürfe aus einem Konzept an (Fach-Regel wie themen.py, A1994) – keine Abschottung/Rechte",
    "amw/verlauf.py": "Absender Entwickler (Anzeige)",
    "amw/wartegrund.py": "Absender Entwickler in Wartegründen",
}
AUTOMATISCH = ("sitecustomize.py", "lib/sitecustomize.py", "usercustomize.py", "tests/usercustomize.py", "conftest.py",
               "tests/conftest.py", "a/b/conftest.py", "x.pth", "lib/site/x.pth", "pyproject.toml", "web/pyproject.toml", "setup.cfg",
               "sub/setup.cfg", "tox.ini")
FREI = ("amw/hilfen.py", "amw/messung.py", "doc/hilfe/agenten.md", "web/hilfe/agenten.de.json", "amw/planung.py", "web/inc/seite.html")


class Sperrliste(unittest.TestCase):
    def test_pflicht_dateien_gesperrt_vor_und_nach_dem_start(self):
        for pfad in PFLICHT + AUTOMATISCH:
            with self.subTest(pfad=pfad):
                self.assertTrue(abnahme.gesperrt([pfad]), "Diff-Tor")                              # danach (diff_tor, Prüfung C)
                self.assertTrue(abnahme.startregel([pfad]), "Startregel 5")                        # davor (Bereich des Pakets)
                self.assertTrue(abnahme.gesperrt([pfad.upper()]), "Groß/Klein")                    # Windows: CLI.PY ist cli.py

    def test_auch_beim_pakettyp_test_schreiben(self):
        for pfad in PFLICHT + AUTOMATISCH:
            self.assertTrue(abnahme.gesperrt([pfad], abnahme.TEST_SCHREIBEN), pfad)

    def test_ordner_als_bereich_mit_gesperrtem_inhalt(self):
        self.assertTrue(abnahme.startregel(["amw/"]))                                              # amw/ enthält gesperrte Dateien
        self.assertTrue(abnahme.startregel(["amw/vorlagen/"]))

    def test_normale_dateien_bleiben_frei(self):
        for pfad in FREI:
            with self.subTest(pfad=pfad):
                self.assertEqual(abnahme.gesperrt([pfad]), [])
                self.assertEqual(abnahme.startregel([pfad]), [])

    def test_gegenrichtung_module_mit_rechte_merkmalen(self):
        """P274: jedes Modul mit ist_lead/ENTWICKLER/kanal/token/settings.local ist gesperrt oder bewusst eingeordnet."""
        import glob
        import re
        muster = re.compile(r"ist_lead|ENTWICKLER|\bkanal\b|KANAL|token|settings\.local")
        wurzel = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        offen = []
        for f in sorted(glob.glob(os.path.join(wurzel, "amw", "*.py"))):
            rel = os.path.relpath(f, wurzel).replace(os.sep, "/")
            with open(f, encoding="utf-8") as d:
                if muster.search(d.read()) and not abnahme.gesperrt([rel]) and rel not in EINGEORDNET_FREI:
                    offen.append(rel)
        self.assertEqual(offen, [], "neue Module mit Rechte-Merkmalen: sperren oder in EINGEORDNET_FREI einordnen (TL)")
        for rel in EINGEORDNET_FREI:                                                              # eingeordnet heißt: wirklich frei
            self.assertEqual(abnahme.gesperrt([rel]), [], rel)

    def test_eine_liste_fuer_automatisch_geladene(self):
        """Prüfung C leitet „automatisch geladen“ aus abnahme.GESPERRT ab – keine zweite Liste."""
        for pfad in AUTOMATISCH:
            self.assertTrue(pruefung_c.autogeladen([pfad]), pfad)
        eigene = set(pruefung_c.AUTOGELADEN) - {m for m, _, _ in abnahme.GESPERRT}
        self.assertTrue(all("pytest" in m for m in eigene), eigene)


if __name__ == "__main__":
    unittest.main()
