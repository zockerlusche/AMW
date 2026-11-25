"""Lead nimmt E4-Pakete nach dem Lesen an (A1894, Befund S8 T1): bei E4/E6 sichert die AMW den Kopf vor dem Archivieren als
refs/amw/paket-A<n> im Projekt-Repo; „amw paket annehmen“ (Lead/Mensch) führt nach E7 „Lead nach E4“ in die Merge-Reihe; die
Merge-Liste liest den Stand aus dem Projekt-Repo; ein schon archiviertes Paket holt den Kopf einmalig aus dem Archiv."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
from unittest import mock

from amw import arbeitspaket, betrieb, db, disponent, entscheidung, kern, mergeliste, platz, pruefung_c
from tests.test_mergeliste import Grund, g, schreiben


class Annehmen(Grund):
    def setUp(self):
        super().setUp()
        self.plaetze(1)

    def e4(self, titel="Tests für plus"):
        """Ein p-Paket (test-schreiben) bis E4 – wie Disponent + Prüfung C es hinterlassen."""
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, "CC1")
        arbeitspaket.setzen(self.con, self.pid, "TL", aid, art="p", pakettyp="test-schreiben")
        p = platz.plaetze(self.con, self.pid)[0]
        basis = platz.vorbereiten(p, self.repo, mergeliste.zweig(aid), aufgabe=aid)["basis"]
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art=disponent.VERMERK,
                         aufgabe_id=aid, text=json.dumps({"platz": 1, "basis": basis, "zweig": mergeliste.zweig(aid)}))
        schreiben(p["klon"], "tests/test_plus.py", "import subprocess\n\ndef test_plus():\n    assert 1 + 1 == 2\n")
        pruefung_c.basis_holen(p, self.repo, basis)
        kopf = pruefung_c.einsammeln(p, basis, aid, f"A{aid}: {titel}")
        for z in ("startklar", "laeuft"):                                                       # den Rest geht anwenden (WEG E4)
            arbeitspaket.zustand_setzen(self.con, self.pid, "AMW", aid, z)
        r = entscheidung.anwenden(self.con, self.pid, aid, "E4", "test-schreiben", befund={"kopf": kopf, "grund": "Pakettyp test-schreiben"},
                                  p=p, quelle=self.repo)
        self.assertEqual(r["zustand"], "wartet_interaktiv")
        return aid, kopf, r

    def test_e4_sichert_kopf_lead_nimmt_an_und_gibt_frei(self):
        aid, kopf, r = self.e4()
        self.assertEqual(g(self.repo, "rev-parse", f"refs/amw/paket-A{aid}"), kopf)               # gesichert vor dem Archiv
        self.assertTrue(r["archiv"])
        d = json.loads(self.con.execute("SELECT text FROM plan_ereignis WHERE art = 'paket_entscheidung' ORDER BY id DESC").fetchone()[0])
        self.assertEqual(d["gesichert"], f"refs/amw/paket-A{aid}")
        self.assertIn(f"amw paket annehmen {aid} --grund", self.con.execute(
            "SELECT text FROM nachricht WHERE kurz LIKE ?", (f"E4 test-schreiben: A{aid}%",)).fetchone()[0])
        self.assertEqual(mergeliste.liste(self.con, self.pid)["pakete"], [])                       # noch nicht in der Liste
        mergeliste.annehmen(self.con, self.pid, "TL", aid, "Test gelesen: startet nur git im Temp-Repo, Fehlalarm C/aussen")
        self.assertEqual(arbeitspaket.lesen(self.con, aid)["zustand"], "merge_reihe")
        e = mergeliste.liste(self.con, self.pid)["pakete"]
        self.assertEqual([(x["aufgabe"], x["kopf"], x["fehler"], x["angenommen"]) for x in e], [(aid, kopf, None, True)])
        self.assertIn("tests/test_plus.py", e[0]["stat"])                                         # aus dem Projekt-Repo gelesen
        self.assertIn("+import subprocess", mergeliste.eintrag(self.con, self.pid, aid)["diff"])
        f = mergeliste.freigeben(self.con, self.pid, "TL", [aid])
        self.assertTrue(f[0]["ok"], f)
        self.assertEqual(g(self.repo, "rev-parse", f"refs/heads/paket-A{aid}"), kopf)
        self.assertTrue(betrieb.merge_ok(self.con, self.pid, aid, f"paket-A{aid}"))
        self.assertEqual(g(self.repo, "rev-parse", "--abbrev-ref", "HEAD"), "main")

    def test_vor_a1894_archiviert_kopf_aus_dem_archiv(self):
        aid, kopf, _ = self.e4()
        g(self.repo, "update-ref", "-d", f"refs/amw/paket-A{aid}")                                 # wie A1868: nur im Archiv
        mergeliste.annehmen(self.con, self.pid, "TL", aid, "gelesen")
        self.assertEqual(g(self.repo, "rev-parse", f"refs/amw/paket-A{aid}"), kopf)
        self.assertEqual(arbeitspaket.lesen(self.con, aid)["zustand"], "merge_reihe")

    def test_nur_nach_e4_mit_grund_durch_lead_oder_mensch(self):
        aid, kopf, _ = self.e4()
        for von, grund, muster in (("CC1", "x", "Lead oder der Mensch"), ("TL", " ", "Grund")):
            with self.assertRaisesRegex(kern.AmwFehler, muster):
                mergeliste.annehmen(self.con, self.pid, von, aid, grund)
        with self.assertRaisesRegex(kern.AmwFehler, "geht nicht"):                                # sonst kein Weg in die Merge-Reihe
            arbeitspaket.zustand_setzen(self.con, self.pid, "TL", aid, "merge_reihe")
        mergeliste.annehmen(self.con, self.pid, kern.ENTWICKLER, aid, "gelesen")
        with self.assertRaisesRegex(kern.AmwFehler, "nicht „wartet auf Lead“"):              # nur einmal, nur aus E4
            mergeliste.annehmen(self.con, self.pid, "TL", aid, "nochmal")

    def test_angenommen_belegt_keinen_platz_und_haelt_keine_auslieferung(self):   # A1897 Zusatz 3 (#29493)
        from amw import waechter
        aid, _, _ = self.e4()
        mergeliste.annehmen(self.con, self.pid, "TL", aid, "gelesen")
        self.assertEqual(arbeitspaket.lesen(self.con, aid)["zustand"], "merge_reihe")
        self.assertEqual(waechter.laufende(self.con, self.pid), [])
        self.assertFalse(waechter.p_laufend(self.con))
        self.assertEqual(disponent.belegte_plaetze(self.con, self.pid), {})
        with mock.patch.object(waechter, "wartung_an"), mock.patch.object(waechter, "zustand", return_value={"wartung": True}):
            self.assertEqual(waechter.vor_auslieferung(self.con, frist_s=0, schlafen=lambda s: None), (True, []))

    def test_wieder_annehmen_nach_herausnehmen(self):                              # A1897 Zusatz 3
        aid, kopf, _ = self.e4()
        mergeliste.annehmen(self.con, self.pid, "TL", aid, "gelesen")
        arbeitspaket.zustand_setzen(self.con, self.pid, "TL", aid, "wartet_interaktiv", grund="kurz heraus")
        r = mergeliste.annehmen(self.con, self.pid, "TL", aid, "doch passend")
        self.assertEqual((r["kopf"], arbeitspaket.lesen(self.con, aid)["zustand"]), (kopf, "merge_reihe"))

    def test_befehl_mit_sperre(self):
        import contextlib
        import io
        from amw import cli
        aid, _, _ = self.e4()

        def rufen(von, **env):
            aus = io.StringIO()
            with mock.patch.dict(os.environ, {"AMW_AGENT": "", "CLAUDECODE": "", "CLAUDE_CODE_MESSAGING_SOCKET": "", **env}), \
                    contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
                rc = cli.main(["--projekt", "Spiel", "--von", von, "paket", "annehmen", str(aid), "--grund", "gelesen"])
            return rc, aus.getvalue()
        rc, aus = rufen("Entwickler", CLAUDECODE="1")
        self.assertNotEqual(rc, 0)
        self.assertIn("nicht aus einer Agenten-Sitzung", aus)
        rc, aus = rufen("TL")
        self.assertEqual(rc, 0, aus)
        self.assertIn(f"A{aid} angenommen", aus)


if __name__ == "__main__":
    import unittest
    unittest.main()
