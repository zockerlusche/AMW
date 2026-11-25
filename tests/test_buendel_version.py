"""A2121: die AMW vergibt die nächste freie Versionsnummer des Bündels und schreibt CHANGELOG und Versionshinweis (TH151) selbst –
Format je Projekt (amw | keepachangelog), Version aus Datei oder Tag; den Tag setzt sie nie."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import json
import os
import unittest

from amw import buendel, buendel_version as bv, buendel_zusammensetzen as bz, db, kern, versionshinweise
from tests import test_buendel_zusammensetzen as tz

HEUTE = datetime.date(2026, 11, 25)
KAC_KOPF = "# Changelog\n\nAll notable changes.\n\n"
KAC_UNREL = "## [Unreleased]\n\n### Fixed\n- Von Hand eingetragen.\n\n"
KAC_ALT = "## [1.4.2] - 2026-10-01\n\n### Added\n- Alt.\n"


class Grund(tz.Grund):
    def setUp(self):
        super().setUp()
        self.auf_main({"amw/__init__.py": '"""Spiel."""\n\n__version__ = "1.2.3"\n',
                       "CHANGELOG.md": "# Änderungen\n\nKopf bleibt oben.\n\n## 1.2.3 – 01.11.2026 · Alt\n- alt\n"})
        self.einstellen(version_datei="amw/__init__.py", changelog_datei="CHANGELOG.md", gesamtlauf_befehl="python -c pass")

    def einstellen(self, **werte):
        for k, v in werte.items():
            kern.projekt_einstellen(self.con, self.pid, "TL", **{k: v})

    def auf_main(self, dateien):
        self.schreiben(dateien)
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "stand")
        self.main = self.git("rev-parse", "main")

    def satz(self, aid, hinweis, gruppe):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET hinweis = ?, hinweis_gruppe = ? WHERE id = ?", (hinweis, gruppe, aid))

    def paket(self, titel, hinweis=None, gruppe=None, art="fenster"):
        self.nr = getattr(self, "nr", 0) + 1
        aid = (self.fenster if art == "fenster" else self.p_paket)(titel, f"2026-11-25T08:00:{self.nr:02d}Z", {f"lib/neu{self.nr}.py": "X = 1\n"})
        if hinweis or gruppe:
            self.satz(aid, hinweis, gruppe)
        return aid

    def los(self, **mehr):
        """Zusammensetzen und Version schreiben, wie es im Bündel aufeinander folgt."""
        z = bz.zusammensetzen(self.con, self.pid)
        self.assertTrue(z["ok"] and z["sha"], z)
        self.ziel = z["ordner"]
        return bv.schreiben(self.con, self.pid, z["drin"], self.ziel, heute=HEUTE, **mehr)

    def lies(self, rel):
        with open(os.path.join(self.ziel, *rel.split("/")), encoding="utf-8") as f:
            return f.read()

    def hinweis(self, aid):
        return tuple(self.con.execute("SELECT hinweis, hinweis_gruppe FROM aufgabe WHERE id = ?", (aid,)).fetchone())

    def abgeleitet(self, aid):
        return [json.loads(r[0]) for r in self.con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = ?",
                                                           (aid, versionshinweise.ABGELEITET))]


class Schreiben(Grund):
    def test_nummer_changelog_und_hinweis(self):
        a = self.paket("plus", "Plus rechnet jetzt richtig.", "behoben")
        b = self.paket("Export", "Listen lassen sich als CSV speichern.", "neu", art="p")
        r = self.los()
        self.assertEqual((r["version"], r["titel"], r["dateien"]), ("1.3.0", "Gebündelte Pakete", ["CHANGELOG.md", "amw/__init__.py"]))
        self.assertEqual(self.lies("CHANGELOG.md"), "# Änderungen\n\nKopf bleibt oben.\n\n## 1.3.0 – 25.11.2026 · Gebündelte Pakete\n"
                         "- **Neu:** Listen lassen sich als CSV speichern.\n- **Behoben:** Plus rechnet jetzt richtig.\n\n"
                         "## 1.2.3 – 01.11.2026 · Alt\n- alt\n")
        self.assertEqual(self.lies("amw/__init__.py"), '"""Spiel."""\n\n__version__ = "1.3.0"\n')
        self.assertEqual(r["hinweis"], "### Neu\n- Listen lassen sich als CSV speichern.\n\n### Behoben\n- Plus rechnet jetzt richtig.")
        self.assertEqual([p["id"] for p in r["pakete"]], [a, b])

    def test_nur_diese_dateien_kein_commit_kein_zweig_kein_tag(self):
        self.paket("plus", "Plus stimmt.", "behoben")
        vorher = (self.git("for-each-ref"), self.git("rev-parse", "main"))
        self.los()
        self.assertEqual(sorted(self.git("diff", "--name-only", "HEAD", ordner=self.ziel).split()), ["CHANGELOG.md", "amw/__init__.py"])
        self.assertEqual(self.git("ls-files", "--others", ordner=self.ziel), "")
        self.assertEqual((self.git("for-each-ref"), self.git("rev-parse", "main")), vorher)
        self.assertEqual(self.git("status", "--porcelain"), "")                              # Projektordner unberührt

    def test_patch_ohne_neues_und_titel(self):
        self.paket("plus", "Plus stimmt wieder.", "behoben")
        r = self.los()
        self.assertEqual((r["version"], r["titel"]), ("1.2.4", "Plus stimmt wieder"))
        self.assertIn("## 1.2.4 – 25.11.2026 · Eigener Titel\n", (self.los(titel="Eigener\nTitel"), self.lies("CHANGELOG.md"))[1])

    def test_alles_intern(self):
        a = self.paket("Neue Testhilfe", "Neue Testhilfe für Agenten.", "neu")
        with db.schreiben(self.con):
            versionshinweise.intern_setzen(self.con, self.pid, "TL", a, True)
        r = self.los()
        self.assertEqual((r["version"], r["titel"], r["hinweis"]), ("1.2.4", "Pflege", ""))   # intern hebt nie MINOR
        self.assertIn("· Pflege\n- **Intern:** 1 Paket(e)", self.lies("CHANGELOG.md"))
        self.assertEqual((self.hinweis(a), self.abgeleitet(a)), ((None, None), []))           # keine Ableitung

    def test_ohne_pakete_und_nie_im_projektordner(self):
        with self.assertRaisesRegex(buendel.BuendelFehler, "Kein Paket"):
            bv.schreiben(self.con, self.pid, [], self.repo)
        a = self.paket("plus", "Plus stimmt.", "behoben")
        with self.assertRaisesRegex(buendel.BuendelFehler, "nie im Projektordner"):
            bv.schreiben(self.con, self.pid, [{"id": a}], self.repo)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_fremdes_paket(self):
        self.paket("plus", "Plus stimmt.", "behoben")
        self.los()
        with self.assertRaisesRegex(buendel.BuendelFehler, "A99999"):
            bv.schreiben(self.con, self.pid, [{"id": 99999}], self.ziel)

    def test_fehlende_versionsdatei_speichert_nichts(self):
        a = self.paket("Neue Ansicht für Termine")
        self.einstellen(version_datei="fehlt.py")
        with self.assertRaisesRegex(buendel.BuendelFehler, "fehlt.py"):
            self.los()
        self.assertEqual((self.hinweis(a), self.lies("CHANGELOG.md").count("## ")), ((None, None), 1))

    def test_zeilenenden_bleiben(self):
        a = self.paket("plus", "Plus stimmt.", "behoben")
        self.los()
        for ende in ("\n", "\r\n"):
            for rel in ("CHANGELOG.md", "amw/__init__.py"):
                text = self.git("show", f"main:{rel}") + "\n"
                with open(os.path.join(self.ziel, *rel.split("/")), "w", encoding="utf-8", newline=ende) as f:
                    f.write(text)
            r = bv.schreiben(self.con, self.pid, [{"id": a}], self.ziel, heute=HEUTE)
            for rel in r["dateien"]:
                with open(os.path.join(self.ziel, *rel.split("/")), "rb") as f:
                    roh = f.read()
                self.assertEqual(roh.count(b"\r\n"), roh.count(b"\n") if ende == "\r\n" else 0, rel)
                self.assertIn(b"1.2.4", roh)

    def test_changelog_fehlt_noch(self):
        self.einstellen(changelog_datei="NEUES.md")
        self.paket("plus", "Plus stimmt.", "behoben")
        r = self.los()
        self.assertEqual(r["dateien"], ["NEUES.md", "amw/__init__.py"])
        self.assertEqual(self.lies("NEUES.md"), "# Änderungen\n\n## 1.2.4 – 25.11.2026 · Plus stimmt\n- **Behoben:** Plus stimmt.\n")

    def test_andere_versionsdatei(self):
        self.auf_main({"projekt.toml": '[projekt]\nname = "spiel"\nversion = "2.0.1"\nbraucht = "2.0.1"\n'})
        self.einstellen(version_datei="projekt.toml")
        self.paket("plus", "Plus stimmt.", "behoben")
        self.assertEqual(self.los()["version"], "2.0.2")
        self.assertEqual(self.lies("projekt.toml"), '[projekt]\nname = "spiel"\nversion = "2.0.2"\nbraucht = "2.0.1"\n')

    def test_versionsdatei_der_amw_mit_nummer_davor(self):
        self.auf_main({"amw/__init__.py": '"""Seit 0.9.0."""\n__version__ = "1.2.3"\n'})
        self.paket("plus", "Plus stimmt.", "behoben")
        self.assertEqual(self.los()["version"], "1.2.4")
        self.assertEqual(self.lies("amw/__init__.py"), '"""Seit 0.9.0."""\n__version__ = "1.2.4"\n')


class Hinweise(Grund):
    def betreff(self, aid, text):
        """Commit des Fenster-Pakets neu betiteln; seine Prüfung nennt den neuen Stand."""
        self.git("checkout", "-q", f"fenster-A{aid}")
        self.git("commit", "-q", "--amend", "-m", text)
        kopf = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        self.pruefung(aid, f"fenster-A{aid}", kopf, tz.T2)
        return kopf

    def test_fenster_aus_dem_commit_betreff(self):
        a = self.paket("Leerer Name")
        kopf = self.betreff(a, f"A{a}: Fehler beim Speichern ohne Namen behoben – intern: speichern()")
        r = self.los()
        self.assertEqual(self.hinweis(a), ("Fehler beim Speichern ohne Namen behoben", "behoben"))
        self.assertEqual(self.abgeleitet(a), [{"quelle": f"Commit {kopf[:8]}", "gruppe": True, "text": True}])
        self.assertEqual(r["hinweis"], "### Behoben\n- Fehler beim Speichern ohne Namen behoben")
        self.assertIn("- **Behoben:** Fehler beim Speichern ohne Namen behoben\n", self.lies("CHANGELOG.md"))

    def test_p_paket_aus_dem_titel_nie_aus_seinem_commit(self):
        a = self.paket("Neue Ansicht für Termine", art="p")
        self.git("checkout", "-q", f"paket-A{a}")
        self.git("commit", "-q", "--amend", "-m", f"A{a}: Stand des Arbeiters (Prüfung C)")
        kopf = self.git("rev-parse", "HEAD")
        self.git("checkout", "-q", "main")
        self.entscheidung(a, tz.T2, zeile="E7", kopf=kopf)
        r = self.los()
        self.assertEqual((self.hinweis(a), r["version"]), (("Neue Ansicht für Termine", "neu"), "1.3.0"))
        self.assertNotIn("Arbeiters", self.lies("CHANGELOG.md"))

    def test_angaben_des_agenten_gehen_vor(self):
        a = self.paket("Neue Ansicht für Termine", "Termine lassen sich nach Woche zeigen.")      # nur der Satz
        b = self.paket("Neuer Filter für Listen", None, "verbessert")                            # nur die Gruppe
        c = self.paket("Neues", "Ein eigener Satz.", "behoben")                                  # beides
        self.los()
        self.assertEqual(self.hinweis(a), ("Termine lassen sich nach Woche zeigen.", "neu"))
        self.assertEqual(self.hinweis(b), ("Neuer Filter für Listen", "verbessert"))
        self.assertEqual(self.hinweis(c), ("Ein eigener Satz.", "behoben"))
        self.assertEqual([(x["gruppe"], x["text"]) for i in (a, b, c) for x in self.abgeleitet(i)], [(True, False), (False, True)])

    def test_zusammenfassung_ja_satz_der_amw_nein(self):
        a, b = self.paket("Kurz"), self.paket("Liste nach Datum sortieren")
        with db.schreiben(self.con):
            for aid, z in ((a, "Die Wochenansicht zeigt Feiertage farbig an."), (b, "Ausgeliefert in 1.2.0: Stapel mit allem")):
                self.con.execute("UPDATE aufgabe SET zusammenfassung = ? WHERE id = ?", (z, aid))
        self.los()
        self.assertEqual(self.hinweis(a)[0], "Die Wochenansicht zeigt Feiertage farbig an.")
        self.assertEqual(self.hinweis(b)[0], "Liste nach Datum sortieren")

    def test_nichts_ausgeliefert_keine_zeile(self):
        a = self.paket("Doku")
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET zusammenfassung = 'Nicht umgesetzt, Entscheidung des Leads' WHERE id = ?", (a,))
        self.assertEqual((self.los()["hinweis"], self.hinweis(a)), ("", (None, None)))

    def test_zweiter_anlauf_gleiches_ergebnis(self):
        a = self.paket("Neue Ansicht für Termine")
        eins, text = self.los(), self.lies("CHANGELOG.md")
        self.assertEqual((self.los(), self.lies("CHANGELOG.md")), (eins, text))                  # zusammensetzen setzt auf main zurück
        self.assertEqual(len(self.abgeleitet(a)), 1)


class Nummer(Grund):
    def naechste(self, neu=False, **mehr):
        return bv.naechste(self.con, self.pid, neu, **mehr)

    def test_freie_nummer(self):
        self.assertEqual(bv.freie_nummer((1, 2, 3), set(), False), "1.2.4")
        self.assertEqual(bv.freie_nummer((1, 2, 3), {(1, 2, 4), (1, 2, 5)}, False), "1.2.6")
        self.assertEqual(bv.freie_nummer((1, 2, 3), {(1, 3, 0)}, True), "1.4.0")
        self.assertEqual(bv.freie_nummer((1, 9, 9), set(), True), "1.10.0")

    def test_tag_ueber_main(self):
        self.git("tag", "v1.2.4")
        self.git("tag", "alt-1.9.0")                                                              # kein Versions-Tag
        self.assertEqual((self.naechste(), self.naechste(True)), ("1.2.5", "1.3.0"))

    def test_eingetragene_version(self):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "release", projekt_id=self.pid, art="version", version="1.10.0", zeit_utc=db.jetzt(), titel="x",
                         eingetragen_von="TL")
            zwei = db.einfuegen(self.con, "projekt", name="Zwei", angelegt_utc=db.jetzt())
            db.einfuegen(self.con, "release", projekt_id=zwei, art="version", version="7.0.0", zeit_utc=db.jetzt(), titel="x",
                         eingetragen_von="TL")
        self.assertEqual(self.naechste(), "1.10.1")                                               # als Zahl verglichen, nur dieses Projekt

    def test_buendel_zweig_belegt(self):
        self.git("branch", "buendel-1.3.0", "main")
        self.git("branch", "buendel-probe", "main")
        self.assertEqual((self.naechste(True), self.naechste()), ("1.4.0", "1.2.4"))

    def stand(self, version, ergebnis="gruen"):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", f"Stapel {version}", "CC1")
        sha = self.commit(f"stapel-{aid}", {"amw/__init__.py": f'__version__ = "{version}"\n'})
        self.pruefung(aid, f"stapel-{aid}", sha, tz.T1, ergebnis=ergebnis)
        return aid

    def test_geprueftes_belegt(self):
        a = self.stand("1.2.4")
        b = self.stand("1.2.5", ergebnis="offen")
        self.stand("1.2.6", ergebnis="rot")                                                       # rot belegt nicht
        self.assertEqual(self.naechste(), "1.2.6")
        self.assertEqual(self.naechste(ohne=[a]), "1.2.4")                                        # das Paket ist selbst im Bündel
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'verworfen', beleg = 'Test' WHERE id IN (?, ?)", (a, b))
        self.assertEqual(self.naechste(), "1.2.4")

    def test_neueste_pruefung_zaehlt_und_fehlender_stand_haelt_nicht(self):
        a = self.stand("1.2.4")
        sha = self.commit("neu-aufgesetzt", {"amw/__init__.py": '__version__ = "1.2.5"\n'})
        self.pruefung(a, "neu-aufgesetzt", sha, tz.T2)
        weg = kern.aufgabe_neu(self.con, self.pid, "TL", "weg", "CC1")
        self.pruefung(weg, "weg", "1" * 40, tz.T2)
        self.assertEqual(self.naechste(), "1.2.4")

    def test_abschnitt_im_changelog_belegt(self):
        self.auf_main({"CHANGELOG.md": "# Änderungen\n\n## 1.2.4 – 02.11.2026 · Von Hand\n- x\n"})
        self.paket("plus", "Plus stimmt.", "behoben")
        self.assertEqual(self.los()["version"], "1.2.5")                                          # nie ein zweiter Abschnitt 1.2.4

    def test_ohne_nummer(self):
        self.auf_main({"amw/__init__.py": "x = 1\n"})
        self.paket("plus", "Plus stimmt.", "behoben")
        with self.assertRaisesRegex(buendel.BuendelFehler, "keine Nummer"):
            self.los()

    def test_ohne_ordner(self):
        with db.schreiben(self.con):
            zwei = db.einfuegen(self.con, "projekt", name="Zwei", angelegt_utc=db.jetzt())
        with self.assertRaisesRegex(buendel.BuendelFehler, "keinen Ordner"):
            bv.naechste(self.con, zwei, False)


class KeepAChangelog(Grund):
    def setUp(self):
        super().setUp()
        self.auf_main({"CHANGELOG.md": KAC_KOPF + KAC_UNREL + KAC_ALT})
        self.einstellen(changelog_format="keepachangelog")

    def test_format_mit_versionsdatei(self):
        self.paket("Export", "Listen lassen sich als CSV speichern.", "neu")
        self.paket("plus", "Plus stimmt.", "behoben")
        self.paket("Liste", "Die Liste lädt schneller.", "verbessert")
        r = self.los()
        self.assertEqual((r["version"], r["dateien"]), ("1.3.0", ["CHANGELOG.md", "amw/__init__.py"]))
        self.assertEqual(self.lies("CHANGELOG.md"), KAC_KOPF + "## [Unreleased]\n\n## [1.3.0] - 2026-11-25\n\n### Added\n"
                         "- Listen lassen sich als CSV speichern.\n\n### Changed\n- Die Liste lädt schneller.\n\n### Fixed\n"
                         "- Von Hand eingetragen.\n- Plus stimmt.\n\n" + KAC_ALT)

    def test_version_aus_dem_tag(self):
        self.git("tag", "v1.4.2")
        self.einstellen(release_modus="tag", version_datei="")
        self.paket("Export", "Listen lassen sich als CSV speichern.", "neu")
        r = self.los()
        self.assertEqual((r["version"], r["dateien"]), ("1.5.0", ["CHANGELOG.md"]))               # aus v1.4.2, keine Versionsdatei
        self.assertIn("## [1.5.0] - 2026-11-25\n\n### Added\n", self.lies("CHANGELOG.md"))
        self.assertIn('"1.2.3"', self.lies("amw/__init__.py"))
        self.assertEqual(self.git("tag", "--list").split(), ["v1.4.2"])                            # den Tag setzt sie nie

    def test_tag_mit_gesetzter_versionsdatei_bleibt_unberuehrt(self):
        self.git("tag", "v1.4.2")
        self.einstellen(release_modus="tag")
        self.paket("plus", "Plus stimmt.", "behoben")
        self.assertEqual((self.los()["dateien"], self.git("diff", "--name-only", "HEAD", ordner=self.ziel)), (["CHANGELOG.md"], "CHANGELOG.md"))

    def test_erste_version_ohne_tag(self):
        self.auf_main({"CHANGELOG.md": KAC_KOPF})
        self.einstellen(release_modus="tag")
        self.paket("Export", "Listen lassen sich als CSV speichern.", "neu")
        self.assertEqual(self.los()["version"], "0.1.0")
        self.assertEqual(self.git("tag", "--list"), "")

    def test_abschnitt_auf_main_ohne_tag_zaehlt(self):
        self.git("tag", "v1.4.1")                                                                  # [1.4.2] steht schon auf main
        self.einstellen(release_modus="tag")
        self.assertEqual(bv.naechste(self.con, self.pid, False), "1.4.3")


if __name__ == "__main__":
    unittest.main()
