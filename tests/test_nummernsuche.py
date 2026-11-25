"""Tests: Suche nach einer Nummer findet das Ding selbst (amw.nummernsuche, dokumente.liste mit q)."""
import tests.abschotten  # noqa: F401 – immer als erster Import
import os
import tempfile
import unittest
from unittest import mock

from amw import db, dokumente, nummernsuche

JETZT = "2026-01-01T00:00:00Z"


class Nummern(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        umgebung = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        for k in ("AMW_PROJEKT", "AMW_AGENT"):
            os.environ.pop(k, None)
        self.con = db.anlegen()
        self.addCleanup(self.ordner.cleanup)
        self.addCleanup(self.con.close)
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=JETZT)
            self.fremd = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=JETZT)

    def ids(self, tabelle, pid, **w):
        """Legt eine Zeile an und gibt die id zurück."""
        with db.schreiben(self.con):
            return db.einfuegen(self.con, tabelle, projekt_id=pid, **w)

    def dok(self, pid, titel="Bericht", status="aktuell", art="bericht"):
        did = self.ids("dokument", pid, titel=titel, art=art, status=status, angelegt_von="CC1", angelegt_utc=JETZT)
        with db.schreiben(self.con):
            self.con.execute("INSERT INTO dokument_version (dokument_id, nr, sha256, endung, groesse, von, zeit_utc, suchtext)"
                             " VALUES (?, 1, 'x', '.md', 1, 'CC1', ?, '')", (did, JETZT))
        return did

    def alles(self, pid):
        """Je Art eine Zeile mit derselben Nummer n (id, bei Meilenstein nr); gibt n zurück."""
        n = self.dok(pid)
        a = self.ids("aufgabe", pid, titel="Auf", angelegt_von="TL", angelegt_utc=JETZT)
        f = self.ids("frage", pid, an="tl", von="CC1", zeit_utc=JETZT, kurz="Fr")
        b = self.ids("beschluss", pid, zeit_utc=JETZT, stichwort="Be", regel="r", quelle="q", angelegt_von="TL", angelegt_utc=JETZT)
        w = self.ids("wortlaut", pid, zeit_utc=JETZT, text="Wo", kanal="seite", erfasst_von="TL", erfasst_utc=JETZT)
        t = self.ids("thema", pid, name="Th", angelegt_von="TL", angelegt_utc=JETZT)
        l = self.ids("lauf", pid, agent="CC1", beschreibung="La", angemeldet_utc=JETZT)
        p = self.ids("pruefung", pid, zweig="zw", sha="s", bauer="CC1", pruefer="CC2", angefragt_utc=JETZT)
        m = self.ids("nachricht", pid, zeit_utc=JETZT, von="TL", art="info", kurz="Na")
        return n, a, f, b, w, t, l, p, m

    def test_kuerzel_und_schreibweise(self):
        self.assertEqual(nummernsuche.treffer(self.con, self.pid, "D1"), [])
        did = self.dok(self.pid)
        for such in (f"D{did}", f" d{did} ", f"d {did}"):
            t = nummernsuche.treffer(self.con, self.pid, such)
            self.assertEqual([(x["art"], x["ref"], x["titel"], x["zusatz"], x["zeit"], x["genau"]) for x in t],
                             [("dokument", f"D{did}", "Bericht", "bericht", JETZT, True)])

    def test_jede_art(self):
        n = self.alles(self.pid)
        a, f, b, w, t, l, p, m = n[1:]
        self.ids("bogen", self.pid, nr=19, titel="Meil", angelegt_von="TL", angelegt_utc=JETZT)
        for such, art, ref in ((f"D{n[0]}", "dokument", f"D{n[0]}"), (f"A{a}", "aufgabe", f"A{a}"), (f"f{f}", "frage", f"F{f}"),
                               (f"B{b}", "beschluss", f"B{b}"), (f"W{w}", "wortlaut", f"W{w}"), (f"TH{t}", "thema", f"TH{t}"),
                               (f"th{t}", "thema", f"TH{t}"), (f"L{l}", "lauf", f"L{l}"), (f"P{p}", "pruefung", f"P{p}"),
                               (f"#{m}", "nachricht", f"#{m}"), ("M19", "meilenstein", "M19")):
            self.assertEqual([(x["art"], x["ref"]) for x in nummernsuche.treffer(self.con, self.pid, such)], [(art, ref)], such)

    def test_meilenstein_ist_die_projektnummer_nicht_die_id(self):
        self.ids("bogen", self.pid, nr=7, titel="Sieben", angelegt_von="TL", angelegt_utc=JETZT)
        bid = self.ids("bogen", self.pid, nr=3, titel="Drei", angelegt_von="TL", angelegt_utc=JETZT)
        self.assertEqual([x["titel"] for x in nummernsuche.treffer(self.con, self.pid, "M7")], ["Sieben"])
        self.assertEqual([x["titel"] for x in nummernsuche.treffer(self.con, self.pid, "M3")], ["Drei"])
        if bid not in (3, 7):
            self.assertEqual(nummernsuche.treffer(self.con, self.pid, f"M{bid}"), [])

    def test_nur_zahl_reihenfolge(self):
        ids = self.alles(self.pid)                        # frische Datenbank: überall die Nummer 1
        self.assertEqual(set(ids), {1})
        self.ids("bogen", self.pid, nr=1, titel="M", angelegt_von="TL", angelegt_utc=JETZT)
        arten = [x["art"] for x in nummernsuche.treffer(self.con, self.pid, " 1 ")]
        self.assertEqual(arten, ["dokument", "aufgabe", "frage", "meilenstein", "beschluss", "wortlaut", "thema", "lauf",
                                 "pruefung", "nachricht"])
        self.assertEqual(nummernsuche.treffer(self.con, self.fremd, "1"), [])

    def test_anderes_projekt_und_geloeschtes(self):
        fremd = self.dok(self.fremd)
        self.assertEqual(nummernsuche.treffer(self.con, self.pid, f"D{fremd}"), [])
        weg = self.dok(self.pid, status="geloescht")
        self.assertEqual(nummernsuche.treffer(self.con, self.pid, f"D{weg}"), [])
        self.assertEqual(nummernsuche.treffer(self.con, self.pid, str(weg)), [])

    def test_alles_andere_ist_leer(self):
        did = self.dok(self.pid)
        for such in (f"D{did} Bericht", "x1", "", None, "  ", "D", "#", "D-1", "D1.5", f"D{did}D", "9" * 40, "TH"):
            self.assertEqual(nummernsuche.treffer(self.con, self.pid, such), [], repr(such))


class DokumenteListe(Nummern):
    def test_dokument_zuerst_dann_textfunde(self):
        erwaehnt = self.dok(self.pid, titel="Siehe D99 hier")
        ziel = self.dok(self.pid, titel="Ganz anders")
        with db.schreiben(self.con):
            self.con.execute("UPDATE dokument_version SET suchtext = ? WHERE dokument_id = ?", (f"zu D{ziel} und {ziel}", erwaehnt))
            self.con.execute("UPDATE dokument SET titel = ? WHERE id = ?", (f"Bezug D{ziel}", erwaehnt))
        for q in (f"D{ziel}", str(ziel)):
            self.assertEqual([d["id"] for d in dokumente.liste(self.con, self.pid, q=q)], [ziel, erwaehnt], q)

    def test_filter_gelten_weiter(self):
        ziel = self.dok(self.pid, art="bild")
        self.assertEqual([d["id"] for d in dokumente.liste(self.con, self.pid, q=f"D{ziel}", art="bericht")], [])
        self.assertEqual([d["id"] for d in dokumente.liste(self.con, self.pid, q=f"D{ziel}", art="bild")], [ziel])
        self.assertEqual(dokumente.liste(self.con, self.pid, q=f"D{ziel}", status="archiviert"), [])

    def test_fremdes_und_geloeschtes_nicht(self):
        fremd = self.dok(self.fremd)
        self.assertEqual(dokumente.liste(self.con, self.pid, q=f"D{fremd}"), [])
        weg = self.dok(self.pid, status="geloescht")
        self.assertEqual(dokumente.liste(self.con, self.pid, q=f"D{weg}", status=""), [])

    def test_ohne_nummer_wie_heute(self):
        a = self.dok(self.pid, titel="Alpha")
        self.dok(self.pid, titel="Beta")
        self.assertEqual([d["id"] for d in dokumente.liste(self.con, self.pid, q="Alpha")], [a])
        self.assertEqual(len(dokumente.liste(self.con, self.pid)), 2)


if __name__ == "__main__":
    unittest.main()
