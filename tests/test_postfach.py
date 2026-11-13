"""A1629 Stufe 1 (Marcel 13.11.): „Fragen“ bleibt ein eigener Menüpunkt – Fragen und ihre Nachträge stehen nur dort, nicht
im Postfach „Nachrichten“ (dort nur ein Hinweis); Nachrichten zeigen die Art (✉ Nachricht / ⚙ System) und lassen sich
mehrere auf einmal erledigen; neuer Menüpunkt „Team-Chat“ für Agenten untereinander (nur lesen, zählt nie). Dazu der Fix
der Faden-Zuordnung: Nachrichten hängen sich nicht mehr von selbst an eine Rückfrage zu einer Frage."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import os
import tempfile
import unittest

from amw import abgleich, db, kern, workbench

E = kern.ENTWICKLER


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        self.con = db.anlegen(os.path.join(self.ordner.name, "t.db"))
        self.addCleanup(lambda: self.con.close())
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        for k in ("CC1", "CC2"):
            kern.agent_neu(self.con, self.pid, k)

    def frage(self):
        return kern.frage_neu(self.con, self.pid, "TL", "entwickler", "Kacheln oder Liste?", [("A", "Kacheln"), ("B", "Liste")],
                              empfehlung="B", grund="Handy", geprueft="keine Treffer", pruefen=False)


class Postfach(Grund):
    def test_fragen_und_nachtraege_nur_unter_fragen(self):
        fid = self.frage()
        kern.frage_antworten(self.con, self.pid, fid, "rueckfrage", "Für wen?", "workbench")
        kern.frage_nachtrag(self.con, self.pid, "TL", fid, "Für alle am Handy.")
        info = kern.posten(self.con, self.pid, "CC1", E, "info", "Seite fertig")[0]
        rf, nt = [r[0] for r in self.con.execute("SELECT nachricht_id FROM frage_verlauf WHERE frage_id = ? AND nachricht_id IS NOT NULL"
                                                  " ORDER BY id", (fid,))]
        for geparkt in (False, True):
            d = workbench.daten_nachrichten(self.con, self.pid)
            self.assertEqual([x["id"] for x in d["eingang"]], [info])                         # Nachtrag nicht im Eingang
            self.assertNotIn(rf, [x["id"] for x in d["gesendet"]])                              # Rückfrage nicht im Gesendet
            self.assertEqual(d["zaehler"]["eingang_offen"], 1)
            self.assertEqual(workbench.an_dich_zahl(self.con, self.pid), 1)
            start = workbench.daten_start(self.con, self.pid)
            self.assertEqual([n["id"] for n in start["an_dich"]], [info])
            self.assertEqual(start["zaehler"]["nachrichten"], 1)
            self.assertEqual(d["zaehler"]["fragen_offen"], 0 if geparkt else 1)                 # nur der Hinweis „n Fragen offen“
            self.assertTrue(nt)
            if not geparkt:
                kern.frage_parken(self.con, self.pid, E, fid)                                   # auch geparkt: Nachträge bleiben bei der Frage

    def test_seite_kennt_hinweis_arten_und_sammel_erledigt(self):
        with open(os.path.join(os.path.dirname(__file__), "..", "amw", "workbench.html"), encoding="utf-8") as f:
            html = f.read()
        nr = html.split("async function sichtNachrichten")[1].split("\nasync function ")[0]
        for x in ('d.zaehler.fragen_offen', '"nr_fragen_offen"', 'class: "nr-sammel"', 'schicken("/api/gelesen", { ids }, projekt)',
                  '" system" : " post"', '"⚙" : "✉"'):
            self.assertIn(x, nr)
        leiste = html.split("function nrReiterLeiste")[1].split("\n}")[0]
        self.assertNotIn('knopf("fragen"', leiste)                                              # „Fragen“ ist ein eigener Menüpunkt
        self.assertIn('rahmen(t("n_fragen"), el("span", { class: "leise" }, t("f_unter")))', html)
        self.assertIn('<a data-sicht="teamchat" class="im-mehr">', html)
        for x in ('n_teamchat: "Team-Chat"', 'n_teamchat: "Team chat"', 'nr_erledigt_n: "Erledigt ({n})"', 'nr_erledigt_n: "Done ({n})"',
                  'nr_fragen_offen: "{n} Fragen an dich offen › Fragen"', 'nr_fragen_offen: "{n} questions for you open › Questions"'):
            self.assertIn(x, html)


class TeamChat(Grund):
    def test_nur_agenten_untereinander_ohne_system(self):
        a = kern.posten(self.con, self.pid, "CC1", "TL", "info", "Prüfbitte ist raus", bezug="@CC2")[0]
        b = kern.posten(self.con, self.pid, "TL", "CC1,CC2", "auftrag", "Bitte die Hilfe ergänzen")[0]
        kern.posten(self.con, self.pid, "CC1", E, "info", "an den Menschen")
        kern.posten(self.con, self.pid, E, "CC1", "auftrag", "vom Menschen")
        kern.posten(self.con, self.pid, "AMW", "CC1", "meldung", "Lauf ist dran")
        d = workbench.daten_teamchat(self.con, self.pid)
        self.assertEqual([x["id"] for x in d["nachrichten"]], [b, a])                            # neueste zuerst
        self.assertEqual(d["nachrichten"][0]["an"], ["CC1", "CC2"])
        self.assertEqual(d["nachrichten"][1]["bezug"]["kuerzel"], "@CC2")
        self.assertEqual(d["agenten"], ["CC1", "CC2", "TL"])
        self.assertIn("/api/teamchat", abgleich.ansichten(self.con, self.pid))                     # auch online
        self.assertIn("teamchat", workbench.stand_je_sicht(self.con, self.pid))                  # aktualisiert sich selbst
        z = workbench.daten_start(self.con, self.pid)["zaehler"]                                   # zählt nie
        self.assertNotIn("teamchat", z)


class Faden(Grund):
    def test_keine_nachricht_haengt_sich_an_eine_rueckfrage(self):
        """Befund A1629: Nach einer Rückfrage hing jede Nachricht des Agenten an den Menschen an der Frage (Auftrag mit Bezug F3)."""
        fid = self.frage()
        kern.frage_antworten(self.con, self.pid, fid, "rueckfrage", "Für wen?", "workbench")
        n = kern.posten(self.con, self.pid, "TL", E, "auftrag", "Bitte die neue Startseite am Handy ansehen")[0]
        r = self.con.execute("SELECT antwort_auf, bezug FROM nachricht WHERE id = ?", (n,)).fetchone()
        self.assertEqual((r["antwort_auf"], r["bezug"]), (None, None))
        self.assertFalse(self.con.execute("SELECT 1 FROM frage_verlauf WHERE nachricht_id = ?", (n,)).fetchone())
        kern.frage_nachtrag(self.con, self.pid, "TL", fid, "ausdrücklich zur Frage")                # so geht ein Nachtrag
        self.assertEqual(self.con.execute("SELECT count(*) FROM frage_verlauf WHERE frage_id = ? AND art = 'nachtrag'", (fid,)).fetchone()[0], 1)

    def test_gespraech_haengt_weiter_an_aber_nicht_bei_anderem_bezug(self):
        m = kern.posten(self.con, self.pid, E, "CC1", "auftrag", "Wie weit ist A1?", bezug="@CC1")[0]
        hinweise = []
        a = kern.posten(self.con, self.pid, "CC1", E, "info", "Fast fertig", hinweise=hinweise)[0]
        self.assertEqual(self.con.execute("SELECT antwort_auf FROM nachricht WHERE id = ?", (a,)).fetchone()[0], m)   # wie bisher
        self.assertTrue(any(f"#{m}" in h for h in hinweise))
        m2 = kern.posten(self.con, self.pid, E, "CC1", "auftrag", "Und die Hilfe?", bezug="@CC1")[0]
        b = kern.posten(self.con, self.pid, "CC1", E, "info", "Dazu etwas ganz anderes", bezug="@CC2")[0]
        self.assertIsNone(self.con.execute("SELECT antwort_auf FROM nachricht WHERE id = ?", (b,)).fetchone()[0])      # eigener Bezug
        c = kern.posten(self.con, self.pid, "CC1", E, "info", "Hilfe kommt", bezug="@CC1")[0]
        self.assertEqual(self.con.execute("SELECT antwort_auf FROM nachricht WHERE id = ?", (c,)).fetchone()[0], m2)   # gleicher Bezug


if __name__ == "__main__":
    unittest.main()
