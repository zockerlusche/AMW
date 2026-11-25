"""A2116 (Marcel 25.11.): abnehmen erst, wenn alles ausgeliefert ist – „wartet auf Auslieferung“ statt Fehlertext; gefragt wird nach dem
Commit in der Version, nicht nach der Uhrzeit; Pakete ohne eigenen Code brauchen keine Version."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import re
import subprocess
import unittest
from unittest import mock

from amw import abschlusslage, aktionen, auslieferstand, belege, db, kern, planansicht, planung, tore, verlauf_quellen
from tests import test_a2082_abschlusslage as a2082

FRUEH, VERSION, SPAET = "2026-11-25T10:00:00Z", "2026-11-25T11:30:50Z", "2026-11-25T11:35:48Z"


class Grund(a2082.Grund):
    """Projekt mit Versions-Pflicht und einem echten Repo: c1 steckt in Version 1.0.0 (v), c2 liegt danach auf main."""
    def setUp(self):
        super().setUp()
        auslieferstand._GEMERKT.clear()
        self.repo = os.path.join(self.ordner.name, "repo")
        os.makedirs(self.repo)
        self.g("init", "-q", "-b", "main")
        self.c1 = self.commit("A1: Login")
        self.v = self.commit("1.0.0: Version")
        self.c2 = self.commit("Nachtsicherung")
        kern.projekt_ordner_setzen(self.con, self.pid, self.repo)
        kern.projekt_einstellen(self.con, self.pid, "TL", versionen="pflicht")
        with db.schreiben(self.con):
            self.con.execute("UPDATE bogen SET nr = 19 WHERE id = ?", (self.m,))                  # Projektnummer ≠ interne Nummer
        self.version("1.0.0", VERSION, self.v)
        self.setzen(self.a1, self.c1[:8], FRUEH)
        self.setzen(self.a2, f"1.0.0 ({self.v[:7]}); D1714", SPAET)                              # die Vorführung, nach der Version fertig

    def g(self, *args):
        u = {k: w for k, w in os.environ.items() if not k.upper().startswith("GIT_")}
        u.update(GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@e", GIT_COMMITTER_NAME="t", GIT_COMMITTER_EMAIL="t@e", GIT_CONFIG_NOSYSTEM="1")
        return subprocess.run(["git", "-C", self.repo, *args], check=True, capture_output=True, text=True, env=u).stdout.strip()

    def commit(self, betreff):
        self.g("commit", "-q", "--allow-empty", "-m", betreff)
        return self.g("rev-parse", "HEAD")

    def version(self, nr, zeit, sha):
        with db.schreiben(self.con):
            db.einfuegen(self.con, "release", projekt_id=self.pid, art="version", version=nr, zeit_utc=zeit, commit_sha=sha, titel=nr, eingetragen_von="TL")

    def setzen(self, aid, beleg, zeit):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET beleg = ?, fertig_utc = ? WHERE id = ?", (beleg, zeit, aid))

    def fehlt(self):
        return auslieferstand.fehlt(self.con, self.pid, self.m)


class Frage(Grund):
    def test_vorfuehrung_nach_der_version(self):
        self.assertEqual(self.fehlt(), [])

    def test_ohne_code_braucht_keine_version(self):
        for beleg in ("Ja von Alex", "D12 Bericht", "abgenommen von Alex"):
            self.setzen(self.a2, beleg, SPAET)
            self.assertEqual(self.fehlt(), [], beleg)
        for beleg in ("Gesamtlauf L3506 grün", "fertig", None):                                 # kein Urteil, kein Dokument: nach der Zeit
            self.setzen(self.a2, beleg, SPAET)
            self.assertEqual(self.fehlt(), [self.a2], beleg)
            self.setzen(self.a2, beleg, FRUEH)
            self.assertEqual(self.fehlt(), [], beleg)

    def test_code_nach_der_version(self):
        for zeit in (FRUEH, SPAET):                                                             # die Zeit entscheidet nicht mehr
            self.setzen(self.a2, self.c2[:8], zeit)
            self.assertEqual(self.fehlt(), [self.a2], zeit)
        self.version("1.1.0", "2026-11-25T12:00:00Z", self.c2)
        self.assertEqual(self.fehlt(), [])

    def test_beleg_aus_der_zeit_vor_dem_stapeln(self):
        """Der notierte Commit liegt neben main: dann zählen die Commits auf main mit „A<nr>:“ im Betreff."""
        self.g("switch", "-q", "-c", "seite", self.c1)
        alt = self.commit(f"A{self.a2}: gebaut")
        self.g("switch", "-q", "main")
        self.setzen(self.a2, f"{alt[:8]} auf 1.0.0 ({self.v[:7]})", FRUEH)
        self.assertEqual(self.fehlt(), [])                                                      # nichts auf main: nach der Zeit
        auslieferstand._GEMERKT.clear()
        neu = self.commit(f"A{self.a2}: gebaut")
        self.assertEqual(self.fehlt(), [self.a2])                                               # auf main, aber nach der Version
        self.version("1.1.0", "2026-11-25T12:00:00Z", neu)
        self.assertEqual(self.fehlt(), [])

    def test_nicht_zu_entscheiden_nach_der_zeit(self):
        self.setzen(self.a2, self.c2[:8], SPAET)
        with mock.patch.object(belege, "_git", side_effect=belege.GitFehler("weg")):
            self.assertEqual(self.fehlt(), [self.a2])
            self.setzen(self.a2, self.c2[:8], VERSION)                                          # gleiche Sekunde: wie bisher kein Grund
            self.assertEqual(self.fehlt(), [])
        auslieferstand._GEMERKT.clear()
        with db.schreiben(self.con):
            self.con.execute("UPDATE release SET commit_sha = NULL")                            # die Version hat keinen Commit
        self.assertEqual(self.fehlt(), [])
        self.setzen(self.a2, self.c2[:8], SPAET)
        self.assertEqual(self.fehlt(), [self.a2])

    def test_ohne_pflicht_und_ohne_version(self):
        self.setzen(self.a2, self.c2[:8], SPAET)
        kern.projekt_einstellen(self.con, self.pid, "TL", versionen="empfohlen")
        self.assertEqual(self.fehlt(), [])
        kern.projekt_einstellen(self.con, self.pid, "TL", versionen="pflicht")
        self.setzen(self.a1, "Ja von Alex", FRUEH)
        with mock.patch.object(auslieferstand, "_version", return_value=(None, None)):
            self.assertEqual(self.fehlt(), [self.a2])                                           # noch gar keine Version: was Code hat, fehlt

    def test_gemerkt(self):
        self.assertEqual(self.fehlt(), [])
        with mock.patch.object(belege, "_git", side_effect=AssertionError("noch einmal git")):
            self.assertEqual(self.fehlt(), [])                                                  # alles ausgeliefert: bleibt
        self.setzen(self.a2, self.c2[:8], SPAET)
        self.assertEqual(self.fehlt(), [self.a2])
        with mock.patch.object(belege, "_git", side_effect=AssertionError("noch einmal git")):
            self.assertEqual(self.fehlt(), [self.a2])
        with mock.patch.object(auslieferstand, "MERKEN_S", 0), mock.patch.object(belege, "_git", side_effect=belege.GitFehler("x")) as git:
            self.fehlt()
            self.assertTrue(git.called)

    def test_liste(self):
        self.assertEqual([auslieferstand.liste(list(range(1, n + 1))) for n in (1, 2, 4, 5, 6)],
                         ["A1", "A1 und A2", "A1, A2, A3 und A4", "A1, A2, A3, A4 und einem weiteren Paket", "A1, A2, A3, A4 und 2 weiteren Paketen"])


class Ablauf(Grund):
    """Vom fertigen Paket bis zur Abnahme: solange die Auslieferung fehlt, kommt beim Menschen nichts an."""
    def bereit(self, an=kern.ENTWICKLER):
        return self.anzahl(an, "bereit zur Abnahme")

    def test_m19_ist_abnehmbar(self):
        self.ergebnis()
        self.runde()
        self.assertEqual((self.lage(), self.bereit()), ("abnehmbar", 1))
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m, "abschluss")
        self.assertEqual(self.b()["status"], "fertig")

    def test_mit_lead_erst_nach_der_auslieferung(self):
        self.setzen(self.a2, self.c2[:8], SPAET)
        self.ergebnis()
        self.runde()
        self.runde()
        k, schritt, _ = self.karte()
        self.assertEqual((self.lage(), k["bei_dir"], k["lage_zaehlt"], k["auslieferung"], schritt["bei_dir"]),
                         ("auslieferung", False, False, [self.a2], False))
        pa = next(x for x in planansicht.daten(self.con, self.pid)["meilensteine"] if x["id"] == self.m)
        self.assertEqual((pa["lage"], pa["bei_dir"], pa["auslieferung"]), ("auslieferung", False, [self.a2]))
        self.assertEqual((self.bereit(), self.bereit("TL")), (0, 0))
        self.assertIn(f"wartet auf die Auslieferung von A{self.a2}", tore.bericht_text(self.con, self.pid, self.m))
        self.version("1.1.0", "2026-11-25T12:00:00Z", self.c2)
        self.runde()
        self.runde()
        self.assertEqual((self.lage(), self.bereit(), self.bereit("TL")), ("abnehmbar", 1, 1))   # genau einmal
        texte = [e["text"] for e in verlauf_quellen.gesamt(self.con, self.pid, [], lambda e: "abschluss") if e["art"] in ("bogen_bereit_abnahme", "abschluss_abnehmbar")]
        self.assertEqual(texte, ["M19: wartet auf Auslieferung", "M19: ausgeliefert, bereit zur Abnahme"])   # der Verlauf sagt nie zu früh „bereit“
        self.assertNotIn("Auslieferung", tore.bericht_text(self.con, self.pid, self.m))
        planansicht.freigeben(self.con, self.pid, kern.ENTWICKLER, self.m, "abschluss")
        self.assertEqual(self.b()["status"], "fertig")

    def test_ohne_lead_erst_nach_der_auslieferung(self):
        self.setzen(self.a2, self.c2[:8], SPAET)
        self.ergebnis()
        self.ohne_lead()
        self.runde()
        self.runde()
        k, schritt, _ = self.karte()
        self.assertEqual((k["bei_dir"], schritt["bei_dir"], self.bereit()), (False, False, 0))
        self.version("1.1.0", "2026-11-25T12:00:00Z", self.c2)
        self.runde()
        self.runde()
        self.assertEqual((self.karte()[0]["bei_dir"], self.bereit()), (True, 1))

    def test_eine_schon_gemeldete_abnahme_endet(self):
        """Ein Paket kommt nach „bereit“ dazu und ist noch nicht ausgeliefert: die offene Meldung endet."""
        self.ergebnis()
        self.runde()
        offen = ("SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id WHERE e.agent = ? AND e.status != 'erledigt'"
                 " AND n.kurz LIKE '%bereit zur Abnahme%'")
        self.assertEqual(self.con.execute(offen, (kern.ENTWICKLER,)).fetchone()[0], 1)
        self.paket("Nachtrag", "fertig")                                                        # Beleg abc1234: kein Commit, nach der Version
        tore.bereit_beenden(self.con, self.pid)
        self.assertEqual((self.lage(), self.con.execute(offen, (kern.ENTWICKLER,)).fetchone()[0]), ("auslieferung", 0))


class Texte(Grund):
    """Was beim Klick auf Abnehmen vor dem Menschen landen kann: nie ein Befehl, nie die interne Nummer."""
    def klick(self, weg="/api/meilenstein/freigeben", **daten):
        with self.assertRaises((kern.AmwFehler, aktionen.Ungueltig)) as e:
            aktionen.ausfuehren(self.con, self.pid, weg, {"bogen": self.m, "art": "abschluss", **daten}, "seite")
        text = str(e.exception)
        self.assertIsNone(re.search(r"\bamw |--\w|`|erzwingen", text), text)
        self.assertNotRegex(text, rf"Meilenstein {self.m}\b|\bM{self.m}\b")
        return text

    def test_klick_auf_abnehmen(self):
        self.setzen(self.a2, self.c2[:8], SPAET)
        self.ergebnis()
        self.runde()
        self.assertEqual(self.klick(), f"Meilenstein 19 wartet auf die Auslieferung von A{self.a2}. Danach geht die Abnahme.")
        with mock.patch.object(abschlusslage, "auslieferung", return_value=[]):                   # Rennen: erst der Abschluss selbst merkt es
            self.assertEqual(self.klick(), f"Meilenstein 19 wartet auf die Auslieferung von A{self.a2}.")
        self.assertEqual(self.b()["status"], "aktiv")
        self.assertFalse((planansicht._zustaende(self.con, self.pid).get((self.m, "abschluss")) or {}).get("an"))   # nichts halb

    def test_andere_fehler_beim_abnehmen(self):
        self.assertIn("Abschlussbericht fehlt noch", self.klick())                                # bereit, aber noch kein Bericht
        self.paket("offen")
        self.assertIn("noch nicht bereit zur Abnahme", self.klick())

    def test_abschliessen_in_der_planung(self):
        self.setzen(self.a2, self.c2[:8], SPAET)
        for paket in (False, True):
            if paket:
                self.paket("offen")
            with self.assertRaises(kern.AmwFehler) as e:
                planung.bogen_status(self.con, self.pid, kern.ENTWICKLER, self.m, "fertig")
            self.assertIsNone(re.search(r"\bamw |--\w|`|erzwingen", str(e.exception)), str(e.exception))
            self.assertIn("19", str(e.exception))

    def test_lead_bekommt_den_befehl(self):
        self.setzen(self.a2, self.c2[:8], SPAET)
        with self.assertRaisesRegex(kern.AmwFehler, "amw release version --version 1.1.0"):
            planung.bogen_status(self.con, self.pid, "TL", self.m, "fertig")
        planung.bogen_status(self.con, self.pid, kern.ENTWICKLER, self.m, "fertig", erzwingen=True)
        self.assertEqual(self.b()["status"], "fertig")

    def test_co_und_lead_warten_auch(self):
        self.setzen(self.a2, self.c2[:8], SPAET)
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, abschluss_freigabe="co+lead", co_entwickler="CC1")
        self.ergebnis()
        self.runde()
        for wer in ("CC1", "TL"):
            with self.assertRaisesRegex(kern.AmwFehler, "wartet auf die Auslieferung"):
                planansicht.freigeben(self.con, self.pid, wer, self.m, "abschluss")


class Seite(a2082.Seite):
    """Karte im Projektweg und in Planung › Meilensteine, im echten Browser."""
    def daten(self):
        super().daten()
        auslieferstand._GEMERKT.clear()
        self.ergebnis()
        kern.projekt_einstellen(self.con, self.pid, kern.ENTWICKLER, versionen="pflicht")          # noch keine Version: nichts ausgeliefert
        self.aids = [r[0] for r in self.con.execute("SELECT id FROM aufgabe WHERE bogen_id = ? AND status = 'fertig' ORDER BY id", (self.m1,))]

    PLANUNG = "document.querySelector('.pm-abschluss')"

    def planung_zeigen(self):
        self.oeffnen("planung", "document.querySelector('#inhalt')")
        self.tab.js("zustand.planReiter = 'meilensteine'; zustand.msOffen = " + str(self.m1) + "; void zeige('planung', true)")
        self.warten(self.PLANUNG)

    def test_kein_knopf_bis_zur_auslieferung(self):
        self.zeigen()
        self.assertEqual(self.tab.js("document.querySelector('.pjw-ab-karte').dataset.lage"), "auslieferung")
        self.assertIn(f"wartet auf Auslieferung (A{self.aids[0]}", self.leiste())
        self.assertIn(f"Wartet auf die Auslieferung von A{self.aids[0]}", self.text())
        self.assertNotIn("wartet auf dich", self.text() + self.leiste())
        for k in ("pjw_trotzdem", "pjw_a_starten", "pjw_a_erneut"):
            self.assertFalse(self.tab.js("!!" + self.knopf(k)), k)
        self.assertFalse(self.tab.js("[...document.querySelectorAll('.pjw-ansicht button')].some(b => b.textContent.includes('abnehmen'))"))
        self.planung_zeigen()
        self.assertFalse(self.tab.js("!!document.querySelector('.pm-abschluss button[data-h=ab-ja]')"))
        self.assertIn("Wartet auf die Auslieferung von", self.tab.js(self.PLANUNG + ".innerText"))
        with db.schreiben(self.con):
            db.einfuegen(self.con, "release", projekt_id=self.pid, art="version", version="1.0.0", zeit_utc="2099-01-01T00:00:00Z", titel="x", eingetragen_von="TL")
        self.zeigen()
        self.assertEqual(self.tab.js("document.querySelector('.pjw-ab-karte').dataset.lage"), "abnehmbar")
        self.assertIn("wartet auf dich", self.text())

    def test_rundgang(self):
        self.ueberall("projektweg", "a2116-projektweg", bereit="document.querySelector('.pjw-schritt')",
                      tun="zustand.pwSicht = 4; zustand.pwOffen = true; void zeige('projektweg', true)",
                      danach="document.querySelector('.pjw-ab-karte[data-lage=auslieferung]')")
        self.ueberall("planung", "a2116-planung", bereit="document.querySelector('#inhalt')",
                      tun=f"zustand.planReiter = 'meilensteine'; zustand.msOffen = {self.m1}; void zeige('planung', true)", danach=self.PLANUNG)


if __name__ == "__main__":
    unittest.main()
