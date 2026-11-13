"""Benutzer online verwalten (A1615 a): Die Online-Seite prüft dieselben Rechte wie der PC (benutzer_darf_verwalten in
lib.php = benutzer.darf_verwalten), zeigt einem Projekt-Admin nur seine Benutzer, und eine Änderung geht über den
Briefkasten an den PC, der sie noch einmal prüft und ausführt. Mit dem echten PHP der Seite gegen eine SQLite-Datei."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import shutil
import subprocess
import tempfile
import unittest

from amw import abgleich, aktionen, benutzer, db, kern

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PHP = shutil.which("php")


@unittest.skipUnless(PHP, "PHP nicht installiert")
class Online(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.a = db.einfuegen(self.con, "projekt", name="Spiel", angelegt_utc=db.jetzt())
            self.b = db.einfuegen(self.con, "projekt", name="Shop", angelegt_utc=db.jetzt())
        self.ua, self.ub = (self.con.execute("SELECT uid FROM projekt WHERE id = ?", (p,)).fetchone()[0] for p in (self.a, self.b))
        E = kern.ENTWICKLER
        benutzer.neu(self.con, E, "lea", "leser", projekte=["Spiel"])
        benutzer.neu(self.con, E, "bert", "bearbeiter", projekte=["Spiel"])
        benutzer.neu(self.con, E, "pia", "projekt_admin", projekte=["Spiel"])
        benutzer.neu(self.con, E, "sam", "system_admin")
        benutzer.neu(self.con, E, "fremd", "bearbeiter", projekte=["Shop"])
        benutzer.neu(self.con, E, "neuling")
        benutzer.neu(self.con, E, "paul", "projekt_admin", projekte=["Spiel", "Shop"])     # Projekt-Admin mit Zusatzprojekt
        benutzer.neu(self.con, E, "bea", "bearbeiter", projekte=["Spiel", "Shop"])        # Bearbeiter mit Fremdprojekt
        self.online = os.path.join(self.ordner.name, "online.db")
        self.sp = abgleich.SqliteSpeicher(self.online)
        self.sp.ausfuehren([(s, []) for s in abgleich.SCHEMA])
        abgleich.nachruesten(self.sp)
        t = db.jetzt()
        self.sp.ausfuehren([(benutzer.ONLINE_EINTRAGEN, [b["name"], b["anzeige"], b["email"], b["rolle"], b["gesperrt"], b["projekte"], t])
                            for b in benutzer.fuer_online(self.con)])
        self.konfig = os.path.join(self.ordner.name, "amw-konfig.php")
        with open(self.konfig, "w", encoding="utf-8") as f:
            f.write(f"<?php return ['sqlite' => {json.dumps(self.online.replace(os.sep, '/'))}, 'benutzer' => 'p', 'passwort_hash' => 'x'];\n")

    def php(self, code):
        datei = os.path.join(self.ordner.name, "probe.php")
        with open(datei, "w", encoding="utf-8") as f:
            f.write("<?php require getenv('AMW_LIB');\n" + code)
        env = {**os.environ, "AMW_KONFIG": self.konfig, "AMW_LIB": os.path.join(WURZEL, "web", "inc", "lib.php").replace(os.sep, "/")}
        r = subprocess.run([PHP, "-d", "extension=pdo_sqlite", "-d", "extension=mbstring", datei], capture_output=True, text=True,
                           env=env, timeout=60)
        if "could not find driver" in r.stdout + r.stderr:
            self.skipTest("PHP ohne pdo_sqlite")
        try:
            return json.loads(r.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            self.fail(r.stdout + r.stderr)

    def ich(self, name):
        return f"$ich = benutzer_zeile('{name}'); $ich['projekte'] = json_decode((string)$ich['projekte'], true) ?: [];"

    def test_gleiche_rechte_wie_am_pc(self):
        """Dieselben Fälle auf beiden Seiten – die Seite darf nie mehr erlauben als der PC (und umgekehrt keine Überraschung)."""
        u = {self.a: self.ua, self.b: self.ub}
        faelle = [("sam", "pia", {"rolle": "system_admin"}), ("sam", "sam", {"gesperrt": True}), ("pia", "bert", {"rolle": "projekt_admin"}),
                  ("pia", "bert", {"rolle": "system_admin"}), ("pia", "sam", {"gesperrt": True}), ("pia", "fremd", {"gesperrt": True}),
                  ("pia", "bert", {"projekte": [self.a, self.b]}), ("pia", "pia", {"gesperrt": True}), ("pia", "lea", {"gesperrt": True}),
                  ("pia", "neuling", {"rolle": "bearbeiter", "projekte": [self.a]}), ("pia", None, {"neu": True, "projekte": [self.a]}),
                  ("pia", None, {"neu": True, "projekte": []}), ("bert", "lea", {"gesperrt": True}), ("lea", "lea", {"rolle": "leser"}),
                  # TL P126: keine Kontoübernahme über Freischalten/Sperren/Rolle
                  ("pia", "paul", {"freischalten": True}), ("pia", "paul", {"gesperrt": True}), ("pia", "paul", {"rolle": "leser"}),
                  ("pia", "bea", {"freischalten": True}), ("pia", "bea", {"gesperrt": True}), ("pia", "bea", {"projekte": [self.a, self.b]}),
                  ("pia", "bert", {"freischalten": True}), ("pia", "neuling", {"freischalten": True}), ("sam", "paul", {"freischalten": True})]
        for wer, ziel, kw in faelle:
            with self.subTest(wer=wer, ziel=ziel, **{k: str(v) for k, v in kw.items()}):
                am_pc = benutzer.darf_verwalten(self.con, wer, ziel, kw.get("rolle"), kw.get("projekte"), kw.get("gesperrt"), kw.get("neu", False),
                                                kw.get("freischalten", False))[0]
                p = json.dumps([u[x] for x in kw["projekte"]]) if "projekte" in kw else "null"
                code = (self.ich(wer) + f"echo json_encode(benutzer_darf_verwalten($ich, {json.dumps(ziel or 'neu-x')}, "
                        f"{json.dumps(kw.get('rolle'))}, json_decode('{p}', true), {json.dumps(kw.get('gesperrt'))}, {json.dumps(kw.get('neu', False))}, "
                        f"{json.dumps(kw.get('freischalten', False))}) === '');")
                self.assertEqual(self.php(code), am_pc)
                if (wer, ziel) in (("pia", "paul"), ("pia", "bea")) and "projekte" not in kw:
                    self.assertFalse(am_pc)                                              # Kontoübernahme ausgeschlossen

    def test_liste_projekt_admin_sieht_nur_seine(self):
        verz = json.dumps([[self.ua, "Spiel"], [self.ub, "Shop"]])
        pia = self.php(self.ich("pia") + f"echo json_encode(benutzer_liste_online($ich, json_decode('{verz}', true)));")
        self.assertEqual(sorted(b["name"] for b in pia["benutzer"]), ["bea", "bert", "lea", "neuling", "paul", "pia"])   # nicht sam, nicht fremd
        self.assertEqual([p["name"] for p in pia["projekte"]], ["Spiel"])
        self.assertNotIn("system_admin", pia["rollen"])
        alle = self.php(f"echo json_encode(benutzer_liste_online(null, json_decode('{verz}', true)));")
        self.assertEqual(len(alle["benutzer"]), 8)
        self.assertIn("system_admin", alle["rollen"])
        self.assertNotIn("passwort_hash", json.dumps(alle))

    def code(self, wer, name, stunden=24):
        ich = self.ich(wer) if wer else "$ich = null;"
        return self.php(ich + f"echo json_encode(benutzer_code_online($ich, '{name}', {stunden}, '{self.ua}'));")

    def zeile_online(self, name):
        z = self.sp.ausfuehren([("SELECT code_hash, code_bis, passwort_hash, sitzung_nr FROM benutzer WHERE name = ?", [name])])[0]
        return z[0] if z else None

    def test_code_entsteht_auf_der_seite_nur_als_hash(self):
        """F1: die Seite erzeugt den Code wie der PC; gespeichert wird nur sein Hash, in den Briefkasten nur Name und Ablauf."""
        vorher = int(self.zeile_online("neuling")[3])
        r = self.code("pia", "neuling")
        self.assertRegex(r["code"], r"^[A-Z2-9]{4}(-[A-Z2-9]{4}){3}$")
        h, bis, pw, nr = self.zeile_online("neuling")
        self.assertEqual(h, benutzer.code_hash(r["code"]))                          # derselbe Hash wie am PC
        self.assertEqual((bis, pw, int(nr)), (r["bis"], None, vorher + 1))           # Passwort weg, alle Sitzungen enden
        alles = json.dumps(self.sp.ausfuehren([("SELECT * FROM eingang", []), ("SELECT * FROM benutzer", [])]))
        self.assertNotIn(r["code"], alles)
        self.assertNotIn(r["code"].replace("-", ""), alles)
        weg, daten = self.sp.ausfuehren([("SELECT weg, daten FROM eingang ORDER BY id DESC LIMIT 1", [])])[0][0]
        self.assertEqual((weg, json.loads(daten)), ("/api/benutzer/code_online", {"name": "neuling", "bis": r["bis"], "_benutzer": "pia"}))
        self.assertIn("fehler", self.code("pia", "sam"))                            # System-Admin: nicht ihrer
        self.assertIn("fehler", self.code("bert", "lea"))                           # Bearbeiter: gar nicht
        self.assertIn("fehler", self.code("pia", "neuling", 500))
        self.assertIn("code", self.code(None, "sam"))                               # Zugang der Seite = System-Admin

    def test_pc_prueft_nach_und_macht_ungueltig(self):
        r = self.code("pia", "neuling")
        ok = aktionen.ausfuehren(self.con, self.a, "/api/benutzer/code_online", {"name": "neuling", "bis": r["bis"], "_benutzer": "pia"},
                                 kanal="netz", speicher=self.sp)
        self.assertEqual(ok, {"geprueft": True})
        self.assertIsNotNone(self.zeile_online("neuling")[0])                             # erlaubt: Code bleibt
        r = self.code(None, "fremd")                                                # angenommen, die Seite hätte sich geirrt:
        with self.assertRaises(aktionen.Ungueltig):                                 # pia darf „fremd“ nicht – der PC sieht es
            aktionen.ausfuehren(self.con, self.a, "/api/benutzer/code_online", {"name": "fremd", "bis": r["bis"], "_benutzer": "pia"},
                                kanal="netz", speicher=self.sp)
        self.assertEqual(list(self.zeile_online("fremd")[:2]), [None, None])
        for ziel in ("bea", "paul"):                                                # TL P126: gemeinsames Projekt reicht nicht
            self.assertIn("fehler", self.code("pia", ziel))                         # die Seite lehnt ab …
            r = self.code(None, ziel)
            with self.assertRaises(aktionen.Ungueltig):                             # … und der PC macht ihn ungültig
                aktionen.ausfuehren(self.con, self.a, "/api/benutzer/code_online", {"name": ziel, "bis": r["bis"], "_benutzer": "pia"},
                                    kanal="netz", speicher=self.sp)
            self.assertEqual(list(self.zeile_online(ziel)[:2]), [None, None])                    # sofort ungültig
        kurz = [x[0] for x in self.con.execute("SELECT kurz FROM nachricht ORDER BY id")]
        self.assertTrue(any("ungültig gemacht" in k and "fremd" in k for k in kurz), kurz)
        self.assertTrue(any("online einen Freischalt-Code für neuling" in k for k in kurz), kurz)

    def test_aenderung_ueber_den_briefkasten_prueft_der_pc_noch_einmal(self):
        """Selbst wenn ein Eintrag an der Seite vorbei in den Briefkasten käme: der PC lehnt ab, was nicht erlaubt ist."""
        ok = aktionen.ausfuehren(self.con, self.a, "/api/benutzer/aendern", {"name": "neuling", "rolle": "bearbeiter", "projekte": [self.ua],
                                 "_benutzer": "pia"}, kanal="netz")
        self.assertEqual((ok["benutzer"]["rolle"], ok["benutzer"]["projekte"]), ("bearbeiter", [self.a]))
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.a, "/api/benutzer/aendern", {"name": "pia", "rolle": "system_admin", "_benutzer": "pia"}, kanal="netz")
        with self.assertRaises(aktionen.Ungueltig):
            aktionen.ausfuehren(self.con, self.a, "/api/benutzer/freischalten", {"name": "neuling", "_benutzer": "sam"}, kanal="netz")


if __name__ == "__main__":
    unittest.main()
