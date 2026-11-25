"""A2093: der Gesamttest zum Abschluss nutzt einen vorhandenen grünen Gesamtlauf auf genau dem ausgelieferten Stand, rechnet bei zwei
Prüfungen nur einmal und zählt nicht, wenn sich der Stand während des Laufs geändert hat. Das Repo im Test ist echt (git)."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import sys
from unittest import mock

from amw import abschluss, betrieb, db, kern
from tests import test_a2088_abschluss

BEFEHL = f'"{sys.executable}" -c "print(42)"'


class Grund(test_a2088_abschluss.Grund):
    def setUp(self):
        super().setUp()
        for p in (mock.patch("amw.freigabereif._gesamtlauf_befehl", return_value=BEFEHL), mock.patch.object(abschluss, "WARTE_S", 0.02)):
            p.start()
            self.addCleanup(p.stop)
        self.kopf = self.git("rev-parse", "main")

    def lauf(self, sha=None, rc: int | None = 0, status="fertig", sauber="sauber", befehl=BEFEHL, beschreibung="Gesamtlauf Probe", ergebnis=None):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "lauf", projekt_id=self.pid, agent="TL", beschreibung=beschreibung, status=status, angemeldet_utc=db.jetzt(), rc=rc,
                                befehl=json.dumps([befehl]),
                                ergebnis=f"OK · Stand {sha or self.kopf} {sauber}" if ergebnis is None else ergebnis)

    def rechnet(self):
        """gesamttest mit Zähler: {"test", "n"} – n, wie oft wirklich gerechnet wurde."""
        echt, n = abschluss.subprocess.run, []

        def run(befehl, *a, **k):
            if befehl == BEFEHL:
                n.append(befehl)
            return echt(befehl, *a, **k)
        with mock.patch.object(abschluss.subprocess, "run", run):
            t = abschluss.gesamttest(self.con, self.pid, self.b())
        return t, len(n)

    def zeile(self, lid):
        return self.con.execute("SELECT * FROM lauf WHERE id = ?", (lid,)).fetchone()


class Vorhanden(Grund):
    def test_gruener_lauf_auf_genau_diesem_stand(self):
        lid = self.lauf()
        t, n = self.rechnet()
        self.assertEqual((t["lauf"], t["rc"], t["uebernommen"], t["stand"], n), (lid, 0, True, self.kopf, 0))
        self.assertEqual(self.con.execute("SELECT count(*) FROM lauf").fetchone()[0], 1)     # kein neuer Lauf

    def test_nichts_anderes_zaehlt(self):
        for was, werte in {"anderer Stand": {"sha": "a" * 40}, "Zweig daneben": {"sha": self.neben}, "rot": {"rc": 1},
                           "geändert": {"sauber": "geändert"}, "abgebrochen": {"status": "abgebrochen"}, "unbekannt": {"rc": None},
                           "Zusatz": {"befehl": BEFEHL + " tests.test_x"}, "Teil": {"befehl": "python -m unittest tests.test_x"}}.items():
            with self.subTest(was=was):
                self.lauf(**werte)                                                          # Läufe bleiben stehen – keiner davon zählt je
                self.assertIsNone(abschluss._vorhandener(self.con, self.pid, self.repo, BEFEHL, False))
        t, n = self.rechnet()
        self.assertEqual((n, t.get("uebernommen"), t["rc"]), (1, None, 0))                  # also wird gerechnet

    def test_eigener_lauf_traegt_den_stand_und_hilft_der_naechsten_pruefung(self):
        t, n = self.rechnet()
        self.assertEqual((n, t["rc"], t["stand"], t.get("geaendert")), (1, 0, self.kopf, None))
        self.assertIn(f"Stand {self.kopf} sauber", self.zeile(t["lauf"])["ergebnis"])
        t2, n2 = self.rechnet()
        self.assertEqual((n2, t2["lauf"], t2["uebernommen"]), (0, t["lauf"], True))

    def test_ergebnis_und_bericht_nennen_den_lauf(self):
        lid = self.lauf()
        with mock.patch("amw.arbeiter.laufen", return_value={"rc": 0, "abweichungen": [], "ergebnis": {"result": self.text(), "total_cost_usd": 0.1}}):
            e = abschluss.ausfuehren(self.con, self.pid, self.m, self.jetzt())
        self.assertEqual((e["ok"], e["test"]), (True, {"lauf": lid, "rc": 0, "befehl": BEFEHL, "uebernommen": True}))
        self.assertIn(f"L{lid} · rc 0 · grün · vorhandener Gesamtlauf", "\n".join(abschluss.bericht_teil(self.con, self.pid, self.m)))
        self.assertIsNone(e.get("vorbehalte"))

    def test_ohne_repo_wie_bisher(self):
        with mock.patch.object(abschluss, "_ausgeliefert", return_value=None), mock.patch.object(betrieb, "pruefstand", return_value=None):
            self.lauf()
            t, n = self.rechnet()
        self.assertEqual((n, t["rc"], t.get("geaendert")), (1, 0, None))


class ZweiPruefungen(Grund):
    fremd = 0

    def anderer(self, status="laeuft"):
        return self.lauf(status=status, rc=None, ergebnis="", beschreibung=abschluss.GESAMTTEST.format(nr=9))

    def test_wartet_auf_den_lauf_der_anderen(self):
        lid, schlaf = self.anderer(), []

        def sleep(_s):
            schlaf.append(1)
            if len(schlaf) == 3:
                with db.schreiben(self.con):
                    self.con.execute("UPDATE lauf SET status = 'fertig', rc = 0, ergebnis = ? WHERE id = ?", (f"Stand {self.kopf} sauber", lid))
        with mock.patch("time.sleep", sleep):
            t, n = self.rechnet()
        self.assertEqual((t["lauf"], n, len(schlaf)), (lid, 0, 3))

    def test_ist_der_andere_rot_rechnet_diese_selbst(self):
        lid = self.anderer()

        def sleep(_s):
            with db.schreiben(self.con):
                self.con.execute("UPDATE lauf SET status = 'fertig', rc = 1, ergebnis = ? WHERE id = ?", (f"Stand {self.kopf} sauber", lid))
        with mock.patch("time.sleep", sleep):
            t, n = self.rechnet()
        self.assertEqual((n, t["rc"], t["lauf"] != lid), (1, 0, True))

    def test_zugleich_angemeldet_der_aeltere_rechnet(self):
        """Beide sahen nichts: der Lauf mit der kleineren Nummer rechnet, der andere nimmt seinen zurück und wartet."""
        echt, lids = betrieb.lauf_start, []

        def start(*a, **k):
            if not lids:
                lids.append(self.anderer())                                                 # die andere Prüfung war einen Augenblick früher
            lids.append(echt(*a, **k))
            return lids[-1]

        def sleep(_s):
            with db.schreiben(self.con):
                self.con.execute("UPDATE lauf SET status = 'fertig', rc = 0, ergebnis = ? WHERE id = ?", (f"Stand {self.kopf} sauber", lids[0]))
        with mock.patch.object(betrieb, "lauf_start", start), mock.patch("time.sleep", sleep):
            t, n = self.rechnet()
        self.assertEqual((t["lauf"], n, self.zeile(lids[1])["status"]), (lids[0], 0, "abgebrochen"))

    def test_frist_dann_selbst(self):
        self.anderer("angemeldet")
        with mock.patch.object(abschluss, "WARTE_FRIST_S", -1), mock.patch.object(betrieb, "lauf_start", side_effect=kern.AmwFehler("gestartet")):
            with self.assertRaisesRegex(kern.AmwFehler, "gestartet"):
                self.rechnet()

    def test_waehrend_des_wartens_gruen_geworden(self):
        """Der eigene Lauf stand in der Schlange; als er dran kommt, gibt es schon einen grünen – nichts wird gerechnet."""
        echt = betrieb.lauf_start

        def start(*a, **k):
            lid = echt(*a, **k)
            self.fremd = self.lauf()
            return lid
        with mock.patch.object(betrieb, "lauf_start", start):
            t, n = self.rechnet()
        self.assertEqual((t["lauf"], n), (self.fremd, 0))
        eigener = self.con.execute("SELECT * FROM lauf WHERE beschreibung LIKE 'Gesamttest Meilenstein%'").fetchone()
        self.assertEqual(eigener["status"], "abgebrochen")
        self.assertIn(f"L{self.fremd} ist grün", eigener["ergebnis"])


class Geaendert(Grund):
    def waehrend(self, tun):
        echt = abschluss.subprocess.run

        def run(befehl, *a, **k):
            r = echt(befehl, *a, **k)
            if befehl == BEFEHL:
                tun()
            return r
        with mock.patch.object(abschluss.subprocess, "run", run), mock.patch("amw.arbeiter.laufen", side_effect=AssertionError("der Prüfer darf nicht laufen")):
            return abschluss.ausfuehren(self.con, self.pid, self.m, self.jetzt())

    def test_anderer_stand_am_ende_zaehlt_nicht(self):
        e = self.waehrend(lambda: self.commit("app/neu.py", "x = 2\n"))
        self.assertIn("Stand hat sich geändert", e["fehler"])
        self.assertEqual((e["ok"], e["angelegt"], self.offen(), e["test"]["befehl"]), (False, {}, [], None))      # weder rot noch nicht erfüllt
        self.assertEqual((self.lage(), abschluss.deuten(e["fehler"])), ("fehler", [{"art": "geaendert", "x": {}}]))
        self.assertEqual(len(self.meldungen("TL", "Abschlussprüfung ging nicht")), 1)
        lauf = self.con.execute("SELECT * FROM lauf").fetchone()
        self.assertIn("Stand hat sich geändert", lauf["ergebnis"])
        self.assertNotIn("sauber", lauf["ergebnis"])                                        # dient keiner anderen Prüfung

    def test_nur_der_ausgelieferte_zweig_aendert_sich(self):
        self.git("switch", "-q", "seite")
        e = self.waehrend(lambda: self.git("branch", "-f", "main", self.neben))
        self.assertIn("Stand hat sich geändert", e["fehler"])

    def test_abgebrochen_ist_nicht_rot(self):
        """Von außen abgebrochen (in der Schlange oder während er rechnet) oder ohne Rückgabewert: „Prüfung ging nicht“, keine Nacharbeit."""
        def lauf_id():
            return self.con.execute("SELECT max(id) FROM lauf").fetchone()[0]
        echt = betrieb.lauf_zeile

        def in_der_schlange(con, pid, lid):
            with db.schreiben(self.con):
                self.con.execute("UPDATE lauf SET status = 'abgebrochen' WHERE id = ?", (lid,))
            return echt(con, pid, lid)

        def beim_rechnen():
            betrieb.lauf_ende(self.con, self.pid, "TL", lauf_id(), None, "von Hand", abgebrochen=True)
        for was, ausfuehren in (("Schlange", lambda: self.mit(betrieb, "lauf_zeile", in_der_schlange)), ("Rechnen", lambda: self.waehrend(beim_rechnen))):
            with self.subTest(was=was):
                e = ausfuehren()
                self.assertIn("wurde abgebrochen", e["fehler"])
                self.assertEqual((e["angelegt"], self.offen(), self.lage(), abschluss.deuten(e["fehler"])), ({}, [], "fehler", [{"art": "abgebrochen", "x": {}}]))

    def mit(self, wo, name, ersatz):
        with mock.patch.object(wo, name, ersatz), mock.patch("amw.arbeiter.laufen", side_effect=AssertionError("der Prüfer darf nicht laufen")):
            return abschluss.ausfuehren(self.con, self.pid, self.m, self.jetzt())

    def test_frist_ist_nicht_rot(self):
        echt = abschluss.subprocess.run

        def run(befehl, *a, **k):
            if befehl == BEFEHL:
                raise abschluss.subprocess.TimeoutExpired(befehl, 1)
            return echt(befehl, *a, **k)
        e = self.mit(abschluss.subprocess, "run", run)
        self.assertIn("lief länger als", e["fehler"])
        self.assertEqual((e["angelegt"], abschluss.deuten(e["fehler"])), ({}, [{"art": "testfrist", "x": {}}]))
        self.assertEqual(self.con.execute("SELECT status FROM lauf").fetchone()[0], "abgebrochen")

    def test_echt_rot_bleibt_rot(self):
        rot = f'"{sys.executable}" -c "raise SystemExit(3)"'
        n = [{"schluessel": "N1", "meilenstein": "M1", "thema": f"TH{self.t1}", "titel": "Beheben", "auftrag": "x", "groesse": "M", "art": "sicherheit",
              "ausfuehrung": "agent", "fertig_quelle": "commit", "interaktiv_grund": "y"}]
        with mock.patch("amw.freigabereif._gesamtlauf_befehl", return_value=rot), \
                mock.patch("amw.arbeiter.laufen", return_value={"rc": 0, "abweichungen": [], "ergebnis": {"result": self.text(self.urteil((True, True), n)), "total_cost_usd": 0.1}}):
            e = abschluss.ausfuehren(self.con, self.pid, self.m, self.jetzt())
        self.assertEqual((e["test"]["rc"], e.get("fehler"), self.offen()), (3, None, ["Beheben"]))

    def mit_vorbehalt(self):
        with mock.patch("amw.arbeiter.laufen", return_value={"rc": 0, "abweichungen": [], "ergebnis": {"result": self.text(), "total_cost_usd": 0.1}}):
            e = abschluss.ausfuehren(self.con, self.pid, self.m, self.jetzt())
        self.assertEqual((e["ok"], e.get("fehler"), [v["art"] for v in e["vorbehalte"]]), (True, None, ["test_anderer_stand"]))
        return e

    def test_anderer_zweig_ist_ein_vorbehalt(self):
        self.git("switch", "-q", "seite")
        e = self.mit_vorbehalt()
        self.assertIn(f"Stand {self.neben} sauber", self.zeile(e["test"]["lauf"])["ergebnis"])
        self.assertIsNone(abschluss._vorhandener(self.con, self.pid, self.repo, BEFEHL, False))     # hilft main nicht

    def test_unsauberer_ordner_ist_ein_vorbehalt(self):
        with open(os.path.join(self.repo, "app", "login.py"), "a", encoding="utf-8") as f:
            f.write("# in Arbeit\n")
        self.mit_vorbehalt()
        self.assertIsNone(abschluss._vorhandener(self.con, self.pid, self.repo, BEFEHL, False))
        self.assertIn("Vorbehalt: der Gesamttest lief auf einem anderen oder unsauberen Stand", "\n".join(abschluss.bericht_teil(self.con, self.pid, self.m)))

    def test_am_ende_geaenderte_dateien_dann_nicht_sauber(self):
        def tun():
            with open(os.path.join(self.repo, "app", "login.py"), "a", encoding="utf-8") as f:
                f.write("# neu\n")
        with mock.patch("amw.arbeiter.laufen", return_value={"rc": 0, "abweichungen": [], "ergebnis": {"result": self.text(), "total_cost_usd": 0.1}}):
            echt = abschluss.subprocess.run

            def run(befehl, *a, **k):
                r = echt(befehl, *a, **k)
                if befehl == BEFEHL:
                    tun()
                return r
            with mock.patch.object(abschluss.subprocess, "run", run):
                e = abschluss.ausfuehren(self.con, self.pid, self.m, self.jetzt())
        self.assertTrue(e["ok"], e.get("fehler"))
        self.assertEqual([v["art"] for v in e["vorbehalte"]], ["test_anderer_stand"])
        self.assertIn("geändert", self.zeile(e["test"]["lauf"])["ergebnis"])
        self.assertNotIn("sauber", self.zeile(e["test"]["lauf"])["ergebnis"])

    def test_zwischen_lauf_und_belegen_ausgeliefert(self):
        self.lauf()
        echt = abschluss.gesamttest

        def test_(*a):
            t = echt(*a)
            self.commit("app/neu.py", "x = 2\n")
            return t
        with mock.patch.object(abschluss, "gesamttest", test_), mock.patch("amw.arbeiter.laufen", side_effect=AssertionError("der Prüfer darf nicht laufen")):
            e = abschluss.ausfuehren(self.con, self.pid, self.m, self.jetzt())
        self.assertIn("Stand hat sich geändert", e["fehler"])
