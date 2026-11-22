"""Versionshinweise ohne KI: Satz für Nutzer und Gruppe beim Abschließen, Entwurf aus den fertigen Aufgaben seit der
letzten Version (mit Vorschlag aus der Zusammenfassung, wenn der Satz fehlt), Eintragen einer Version, Daten der Seite."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import subprocess
import tempfile
import unittest

from amw import db, kern, versionshinweise, wissen, workbench


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "amw.db"))
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")

    def fertig(self, titel, zusammenfassung, **mehr):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, agent="CC1")
        kern.aufgabe_status(self.con, self.pid, "CC1", aid, "start")
        kern.aufgabe_status(self.con, self.pid, "CC1", aid, "fertig", beleg="abc1234", zusammenfassung=zusammenfassung, **mehr)
        return aid


class Entwurf(Grund):
    def test_satz_und_gruppe_vom_agenten_gehen_vor(self):
        a = self.fertig("Export als CSV", "csv.py mit Spaltenkopf (Fix 1a2b3c4)", hinweis="Listen lassen sich als CSV-Datei speichern.", gruppe="neu")
        b = self.fertig("Absturz beim Speichern behoben", "Speichern bricht bei leerem Namen sauber ab, Release 1.2.3")
        c = self.fertig("Doku aufgeräumt", "Nicht umgesetzt, Entscheidung des Leads")
        e = versionshinweise.entwurf(self.con, self.pid)
        self.assertEqual(e["neu"], [{"id": a, "text": "Listen lassen sich als CSV-Datei speichern.", "vorschlag": False}])
        self.assertEqual(e["behoben"], [{"id": b, "text": "Speichern bricht bei leerem Namen sauber ab", "vorschlag": True}])
        self.assertNotIn(c, [x["id"] for g in e.values() for x in g])                          # nichts ausgeliefert
        text = versionshinweise.als_text(e)
        self.assertEqual(text, "### Neu\n- Listen lassen sich als CSV-Datei speichern.\n\n### Behoben\n- Speichern bricht bei leerem Namen sauber ab")
        self.assertIn(f"(A{a})", versionshinweise.als_text(e, mit_aufgaben=True))
        with self.assertRaises(kern.AmwFehler):
            self.fertig("x", "y", gruppe="sonstiges")

    def test_version_eintragen_uebernimmt_den_entwurf_und_beginnt_neu(self):
        a = self.fertig("Filter", "Filter nach Datum", hinweis="Die Liste lässt sich nach Datum filtern.", gruppe="verbessert")
        rid, _ = wissen.release_version(self.con, self.pid, "TL", "1.1.0", "Filter")
        r = self.con.execute("SELECT text_oeffentlich, aufgaben FROM release WHERE id = ?", (rid,)).fetchone()
        self.assertEqual(r["text_oeffentlich"], "### Verbessert\n- Die Liste lässt sich nach Datum filtern.")
        self.assertEqual(r["aufgaben"], f"A{a}")
        self.assertEqual(versionshinweise.als_text(versionshinweise.entwurf(self.con, self.pid)), "")     # danach leer
        self.fertig("Mehr", "Neue Ansicht", hinweis="Neue Ansicht für Termine.", gruppe="neu")
        rid2, _ = wissen.release_version(self.con, self.pid, "TL", "1.2.0", "Termine", oeffentlich="### Neu\n- Eigener Text.")
        self.assertEqual(self.con.execute("SELECT text_oeffentlich FROM release WHERE id = ?", (rid2,)).fetchone()[0], "### Neu\n- Eigener Text.")
        d = workbench.daten_versionshinweise(self.con, self.pid)
        self.assertEqual([v["version"] for v in d["versionen"]], ["1.2.0", "1.1.0"])
        self.assertEqual(sum(len(v) for v in d["entwurf"].values()), 0)

    def test_satz_bereinigt_interne_verweise(self):
        self.assertEqual(versionshinweise.satz("STARTSEITE: Team als Baum (W9999, #99999), live geprüft. Rest"), "Startseite: Team als Baum.")
        self.assertEqual(versionshinweise.satz(""), "")


class Ableiten(Grund):
    """A1954 (TH151): den Hinweis leitet die AMW beim Schließen ab – der Agent ergänzt höchstens."""

    def ereignis(self, aid):
        r = self.con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = ?", (aid, versionshinweise.ABGELEITET)).fetchone()
        return json.loads(r[0]) if r else None

    def hinweis(self, aid):
        r = self.con.execute("SELECT hinweis, hinweis_gruppe FROM aufgabe WHERE id = ?", (aid,)).fetchone()
        return r["hinweis"], r["hinweis_gruppe"]

    def repo(self, *betreffe):
        ordner = os.path.join(self.ordner.name, "repo")
        os.makedirs(ordner)
        g = lambda *a: subprocess.run(["git", "-C", ordner, *a], check=True, capture_output=True, text=True, encoding="utf-8")  # noqa: E731
        g("init", "-q")
        g("config", "user.email", "t@t")
        g("config", "user.name", "t")
        shas = []
        for b in betreffe:
            g("commit", "-q", "--allow-empty", "-m", b)
            shas.append(g("rev-parse", "HEAD").stdout.strip())
        kern.projekt_ordner_setzen(self.con, self.pid, ordner)
        return shas

    def schliessen(self, titel, beleg, zusammenfassung="", art=None, **mehr):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, agent="CC1")
        if art:
            with db.schreiben(self.con):
                self.con.execute("UPDATE aufgabe SET art = ? WHERE id = ?", (art, aid))
        kern.aufgabe_status(self.con, self.pid, "CC1", aid, "start")
        kern.aufgabe_status(self.con, self.pid, "CC1", aid, "fertig", beleg=beleg, zusammenfassung=zusammenfassung or None, **mehr)
        return aid

    def test_kurz_macht_aus_betreff_einen_satz(self):
        self.assertEqual(versionshinweise.kurz("A1964: Patch-ID-Übertragung legt kein Grün – sonst verdrängte es das Grün"),
                         "Patch-ID-Übertragung legt kein Grün")
        self.assertEqual(versionshinweise.kurz("K5 + A12: Reihenfolge rechnet die AMW; Tests, Doku"), "Reihenfolge rechnet die AMW")
        self.assertEqual(versionshinweise.kurz("A1: Plugins laden im Arbeiter nicht (--restricted; Probe L3043)"),
                         "Plugins laden im Arbeiter nicht")                                  # offene Klammer nach dem Schnitt
        self.assertEqual(versionshinweise.kurz("A2: typescript-lsp heraus (CCamwTL #30434) – Grund"), "Typescript-lsp heraus")

    def test_aus_dem_commit_betreff_mit_art_fehlersuche(self):
        sha, = self.repo("A7: Speichern mit leerem Namen bricht sauber ab – intern: Prüfung in speichern()")
        aid = self.schliessen("Leerer Name", sha[:7], "lange technische Zusammenfassung", art="fehlersuche")
        self.assertEqual(self.hinweis(aid), ("Speichern mit leerem Namen bricht sauber ab", "behoben"))
        self.assertEqual(self.ereignis(aid), {"quelle": f"Commit {sha[:7]}", "gruppe": True, "text": True})
        e = versionshinweise.entwurf(self.con, self.pid)
        self.assertEqual(e["behoben"], [{"id": aid, "text": "Speichern mit leerem Namen bricht sauber ab", "vorschlag": True}])

    def test_versions_commit_und_zu_kurze_quelle_zaehlen_nicht(self):
        v, k = self.repo("1.4.0: Stapel – A8 und A9", "A9: Versionsnummer")
        a = self.schliessen("Neue Ansicht für Termine", v[:7])                              # Versions-Commit → Titel
        b = self.schliessen("Kalender zeigt Wochen", k[:7], "Die Wochenansicht zeigt Feiertage farbig an.")
        self.assertEqual(self.hinweis(a), ("Neue Ansicht für Termine", "neu"))
        self.assertEqual(self.hinweis(b)[0], "Die Wochenansicht zeigt Feiertage farbig an.")   # ein Wort → nächste Quelle
        self.assertEqual(self.ereignis(b)["quelle"], "Zusammenfassung")

    def test_der_agent_ergaenzt_hoechstens(self):
        a = self.schliessen("Fehler beim Export", "abc1234", hinweis="Der Export klappt wieder mit Umlauten.")
        self.assertEqual(self.hinweis(a), ("Der Export klappt wieder mit Umlauten.", "behoben"))   # nur die Gruppe abgeleitet
        self.assertEqual(self.ereignis(a), {"quelle": "Titel", "gruppe": True, "text": False})
        self.assertEqual(versionshinweise.entwurf(self.con, self.pid)["behoben"][0]["vorschlag"], False)
        b = self.schliessen("Etwas", "abc1234", hinweis="Ein eigener Satz.", gruppe="neu")
        self.assertEqual((self.hinweis(b), self.ereignis(b)), (("Ein eigener Satz.", "neu"), None))  # nichts abgeleitet
        c = self.schliessen("Doku", "abc1234", "Nicht umgesetzt, Entscheidung des Leads")
        self.assertEqual((self.hinweis(c), self.ereignis(c)), ((None, None), None))               # nichts ausgeliefert

    def test_fertig_quelle_thema_und_automatik(self):
        from amw import fertigquelle, themen
        neu = themen.neu(self.con, self.pid, "TL", "Termine im Kalender verschieben")
        tid = neu if isinstance(neu, int) else neu["id"]
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", "TH9 umsetzen", agent="CC1")
        fertigquelle.setzen(self.con, self.pid, "TL", aid, f"thema TH{tid}")
        kern.aufgabe_status(self.con, self.pid, "AMW", aid, "fertig", beleg=f"TH{tid} Fassung 1", automatik=True,
                            zusammenfassung=f"Fertig: Thema TH{tid} ist freigegeben (Fassung 1) – die AMW hat die Aufgabe geschlossen.")
        self.assertEqual(self.hinweis(aid)[0], "Termine im Kalender verschieben")
        self.assertEqual(self.ereignis(aid)["quelle"], f"Thema TH{tid}")
        b = kern.aufgabe_neu(self.con, self.pid, "TL", "Liste nach Datum sortieren", agent="CC1")
        kern.aufgabe_status(self.con, self.pid, "AMW", b, "fertig", beleg="abc1234", automatik=True,
                            zusammenfassung="Fertig: 7 Tage nach 1.2.0 ohne Revert – von der AMW geschlossen.")
        self.assertEqual(self.hinweis(b)[0], "Liste nach Datum sortieren")                     # nie die Zusammenfassung der AMW


class Intern(Grund):
    """A1978 (#30740/#30741): --gruppe intern – nie in den Versionshinweisen, auch nachträglich vor dem nächsten Versionseintrag."""

    def ids(self):
        return [x["id"] for g in versionshinweise.entwurf(self.con, self.pid).values() for x in g]

    def test_intern_beim_schliessen_und_nachtraeglich(self):
        a = self.fertig("Probe Sprach-Server", "Probe: keine Diagnosen im Arbeiter", gruppe="intern")
        b = self.fertig("Export als CSV", "csv.py", hinweis="Listen lassen sich als CSV speichern.", gruppe="verbessert")
        r = self.con.execute("SELECT hinweis, hinweis_gruppe FROM aufgabe WHERE id = ?", (a,)).fetchone()
        self.assertEqual((tuple(r), versionshinweise.ist_intern(self.con, a)), ((None, None), True))   # keine Ableitung (A1954)
        self.assertEqual(self.ids(), [b])
        self.assertEqual(versionshinweise.nachtragen(self.con, self.pid, "CC1", b, "intern"), "intern")   # wie A1963
        self.assertEqual(self.ids(), [])
        self.assertEqual(versionshinweise.nachtragen(self.con, self.pid, "TL", b, "behoben", "CSV-Export geht wieder."), "behoben")
        self.assertFalse(versionshinweise.ist_intern(self.con, b))
        e = versionshinweise.entwurf(self.con, self.pid)
        self.assertEqual(e["behoben"], [{"id": b, "text": "CSV-Export geht wieder.", "vorschlag": False}])
        kern.agent_neu(self.con, self.pid, "CC2")
        with self.assertRaisesRegex(kern.AmwFehler, "Bearbeiter, der Lead"):
            versionshinweise.nachtragen(self.con, self.pid, "CC2", b, "intern")
        with self.assertRaisesRegex(kern.AmwFehler, "intern"):
            versionshinweise.nachtragen(self.con, self.pid, "CC1", b, "sonstiges")
        wissen.release_version(self.con, self.pid, "TL", "1.1.0", "Export")
        with self.assertRaisesRegex(kern.AmwFehler, "schon in einer eingetragenen Version"):
            versionshinweise.nachtragen(self.con, self.pid, "CC1", b, "intern")


if __name__ == "__main__":
    unittest.main()
