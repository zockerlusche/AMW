"""A2096 (TH164 „Eingriffe“): „Stand packen“ und Prüfpunkt beim Menschen – die Pakete dahinter warten über Abhängigkeiten, anderes läuft weiter;
nur der Mensch sagt ja, „zurück“ geht an Packer und Lead, Entfernen nimmt genau die eigenen Kanten weg, später dazugekommene Nachfolger warten
auch, niemand schließt ihn von Hand oder mit der Auslieferung, der Name kommt aus dem Projekt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import contextlib
import io
from unittest import mock

from amw import (aktionen, arbeitspaket, auslieferung, cli, db, dokumente, fertigquelle, kern, planer_delta, planung, reihenfolge, themen, urteil, verlauf_quellen, verteilen, waechter, wartegrund,
                 workbench, zeitplan, zwischenpruefung)
from tests import test_eingriff_verschieben

MENSCH = kern.ENTWICKLER


class Grund(test_eingriff_verschieben.Grund):
    def setUp(self):
        super().setUp()
        self.a = self.paket("Motor")
        self.b = self.paket("Anzeige", nach=[self.a])
        self.c = self.paket("Ton", nach=[self.b])
        self.frei = self.paket("Texte", agent="CC2")

    def setze(self, aid, **w):
        with db.schreiben(self.con):
            self.con.execute(f"UPDATE aufgabe SET {', '.join(k + ' = ?' for k in w)} WHERE id = ?", (*w.values(), aid))

    def fertig(self, aid):
        self.setze(aid, status="fertig", beleg="abc1234", fertig_utc=db.jetzt())

    def punkt(self, nach=None, von=MENSCH, grund="", **w):
        return zwischenpruefung.einfuegen(self.con, self.pid, von, nach or self.a, grund=grund, **w)

    def packen(self, aid, agent="CC1"):
        """Der Packer beginnt und legt sein Ergebnis ab – damit steht es unter „Für dich“."""
        self.setze(aid, agent=agent, status="laeuft", begonnen_utc=db.jetzt())
        dokumente.ablegen_inhalt(self.con, self.pid, agent, b"Stand liegt in dist/", "stand.md", titel="Stand", art="ergebnis", aufgabe=aid)

    def kanten(self):
        return {(r["vor"], r["nach"]) for r in self.con.execute("SELECT vor, nach FROM abhaengigkeit")}

    def post(self, an, wort=""):
        return [(r["art"], r["kurz"]) for r in self.con.execute("SELECT n.art, n.kurz FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE e.agent = ? AND n.kurz LIKE ?"
                                                                " ORDER BY n.id", (an, f"%{wort}%"))]

    def darf_starten(self, aid):
        try:
            kern.aufgabe_status(self.con, self.pid, self.con.execute("SELECT agent FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0], aid, "start")
            return True
        except kern.AmwFehler:
            return False


class Einfuegen(Grund):
    def test_die_dahinter_warten_anderes_laeuft_weiter(self):
        r = self.punkt()
        p = r["paket"]
        self.assertEqual((r["wartet"], r["laeuft_schon"], r["wartet_auf"], r["kanten"]), ([self.b, self.c], [], "Alex", [[self.a, p], [p, self.b]]))
        a = self.con.execute("SELECT * FROM aufgabe WHERE id = ?", (p,)).fetchone()
        self.assertEqual((a["titel"], a["bogen_id"], (fertigquelle.lesen(self.con, p) or {}).get("art")), ("Stand packen – Alex testet", self.bid, "ja"))
        self.fertig(self.a)
        self.assertEqual(planung.offene_vorgaenger(self.con, self.b), [p])
        self.assertFalse(self.darf_starten(self.b))
        self.assertTrue(self.darf_starten(self.frei))                                       # anderes läuft weiter
        self.assertEqual({z["aid"]: z["zustand"] for z in reihenfolge.berechnen(self.con, self.pid)}[self.b], "wartet")
        self.assertNotIn(self.b, {e["id"] for e in self.naechster("CC1")})

    def naechster(self, agent):
        x = planung.naechster(self.con, self.pid, agent)
        return [x] if x else []

    def test_hinter_laufendem_und_fertigem_paket(self):
        self.setze(self.b, status="laeuft", begonnen_utc=db.jetzt())
        r = self.punkt()                                                                    # b läuft schon und läuft zu Ende, c wartet
        self.assertEqual((r["wartet"], r["laeuft_schon"], r["kanten"]), ([self.c], [self.b], [[self.a, r["paket"]], [r["paket"], self.c]]))
        x = self.paket("Hinten", nach=[self.frei])
        self.fertig(self.frei)
        r = self.punkt(self.frei)
        self.assertEqual((r["wartet"], r["kanten"]), ([x], [[r["paket"], x]]))              # fertig: keine Kante davor

    def test_headless_paket_dahinter_startet_nicht(self):
        h = self.p_paket("Headless")
        planung.abhaengigkeit_setzen(self.con, self.pid, "TL", h, [self.a])
        self.fertig(self.a)
        self.assertIn(h, {k["id"] for k in waechter.reihenfolge(self.con, self.pid)})
        self.punkt()
        self.assertNotIn(h, {k["id"] for k in waechter.reihenfolge(self.con, self.pid)})

    def test_rechte_und_wo_es_geht(self):
        for von, nach, muster in (("CC1", self.a, "der Mensch oder der Lead"), ("TL", self.a, "nur mit Grund"), (MENSCH, self.c, "wartet kein Paket"), (MENSCH, 999, "gibt es nicht")):
            with self.subTest(von=von, nach=nach), self.assertRaisesRegex(kern.AmwFehler, muster):
                self.punkt(nach, von=von)
        r = self.punkt(von="TL", grund="vor dem Ton testen")
        for nach, muster in ((self.a, "schon ein Prüfpunkt"), (r["paket"], "selbst ein Prüfpunkt")):
            with self.subTest(nach=nach), self.assertRaisesRegex(kern.AmwFehler, muster):
                self.punkt(nach)
        planung.bogen_status(self.con, self.pid, "TL", self.bid, "verworfen")
        with self.assertRaisesRegex(kern.AmwFehler, "geplanten oder laufenden"):
            self.punkt(self.b)

    def test_plan_stand_bleibt_und_der_lead_erfaehrt_es(self):
        with db.schreiben(self.con):
            reihenfolge.plan_stand_merken(self.con, self.pid, "TL", self.bid)
        alt = [tuple(r) for r in self.con.execute("SELECT id, text FROM plan_ereignis WHERE art = ?", (reihenfolge.PLAN_STAND,))]
        r = self.punkt(grund="")
        self.assertEqual([tuple(x) for x in self.con.execute("SELECT id, text FROM plan_ereignis WHERE art = ?", (reihenfolge.PLAN_STAND,))], alt)
        self.assertEqual(self.post("TL", "Prüfpunkt hinter"), [("info", f"M1: Prüfpunkt hinter A{self.a} – A{r['paket']}, 2 Pakete warten")])
        self.assertEqual(set(r["vorher"]), set(r["nachher"]))

    def test_packen_befehl_gesetzt_und_leer(self):
        r = self.punkt()
        text = self.con.execute("SELECT auftrag FROM aufgabe WHERE id = ?", (r["paket"],)).fetchone()[0]
        for teil in ("Alex testet ihn", "nach den Regeln des Projekts", "Kein Push, kein Tag, kein Release", "--art ergebnis"):
            self.assertIn(teil, text)
        kern.projekt_einstellen(self.con, self.pid, "TL", packen_befehl="python bau.py --lokal")
        x = self.paket("Hinten", nach=[self.frei])
        text = self.con.execute("SELECT auftrag FROM aufgabe WHERE id = ?", (self.punkt(self.frei, hinweis="Auf das Menü achten")["paket"],)).fetchone()[0]
        for teil in ("über die Lauf-Schlange: python bau.py --lokal", "Kein Push", "Hinweis: Auf das Menü achten"):
            self.assertIn(teil, text)
        self.assertTrue(x)
        with self.assertRaisesRegex(kern.AmwFehler, "in einer Zeile"):
            kern.projekt_einstellen(self.con, self.pid, "TL", packen_befehl="a\nb")


class NurPerGrund(Grund):
    """A2134: beim Setzen stehen die Pakete dabei, die nur per Wartegrund warten – der Prüfpunkt hält sie nicht auf, und er setzt dort nichts."""
    def wartet(self, aid, auf):
        kern.aufgabe_status(self.con, self.pid, "TL", aid, "wartet", auf=auf)

    def test_ohne_solche_pakete(self):
        r = self.punkt()
        self.assertEqual((r["nur_grund"], r["nur_grund_text"]), ([], ""))
        self.assertNotIn("nicht aufgehalten", self.befehl(self.b))

    def befehl(self, aid):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            cli.main(["aufgabe", "pruefpunkt", str(aid), "--von", "TL", "--projekt", "Produkt", "--grund", "testen"])
        return aus.getvalue()

    def test_auf_das_paket_selbst_und_auf_eins_davor(self):
        davor, spaet = self.paket("Grundlage"), self.paket("Abschluss", agent="CC2")
        planung.abhaengigkeit_setzen(self.con, self.pid, "TL", self.a, [davor])
        self.wartet(self.frei, f"A{self.a}")
        self.wartet(spaet, f"A{davor}")
        vorher = self.kanten()
        r = self.punkt()
        self.assertEqual(sorted(r["nur_grund"]), sorted([self.frei, spaet]))
        self.assertEqual(r["wartet"], [self.b, self.c])
        self.assertEqual(self.kanten() - vorher, {(self.a, r["paket"]), (r["paket"], self.b)})                # dort nichts gesetzt
        self.assertEqual([x["bezug"] for x in wartegrund.offene(self.con, self.frei)], [f"A{self.a}"])
        text = self.con.execute("SELECT text FROM nachricht WHERE kurz LIKE '%Prüfpunkt hinter%' ORDER BY id DESC").fetchone()[0]
        self.assertIn(f"Nicht aufgehalten: A{self.frei}, A{spaet} (warten nur per Grund).", text)

    def test_befehl_und_aktion_nennen_sie(self):
        self.wartet(self.frei, f"A{self.a}")
        self.assertIn(f"nicht aufgehalten: A{self.frei} (wartet nur per Grund)", self.befehl(self.a))
        p = zwischenpruefung.offene(self.con, self.pid)[0]["paket"]
        aktionen.planen(self.con, self.pid, "pruefpunkt", {"aufgabe": p, "entfernen": True})
        self.assertEqual(aktionen.planen(self.con, self.pid, "pruefpunkt", {"aufgabe": self.a})["nur_grund"], [self.frei])

    def test_wer_nicht_dazu_gehoert(self):
        self.wartet(self.c, f"A{self.a}")                                                   # hat die Abhängigkeit: wartet schon
        haengt = self.paket("Hängt an b")
        self.wartet(haengt, f"A{self.b}")                                                   # wartet auf ein aufgehaltenes: wartet ohnehin
        fremd = self.paket("Anderes")
        self.wartet(fremd, f"A{self.frei}")                                                 # auf etwas, das nicht davor liegt
        agent = self.paket("Wartet auf jemand")
        self.wartet(agent, "CC2")
        self.wartet(self.frei, f"A{self.a}")
        self.setze(self.frei, status="laeuft", begonnen_utc=db.jetzt())                     # begonnen: läuft zu Ende
        self.assertEqual(self.punkt()["nur_grund"], [])

    def test_hinter_dem_paket_wartet_nur_jemand_per_grund(self):
        self.wartet(self.frei, f"A{self.c}")
        with self.assertRaisesRegex(kern.AmwFehler, rf"hielte nichts auf.*nicht aufgehalten: A{self.frei} \(wartet nur per Grund\)"):
            self.punkt(self.c)

    def test_fuer_dich_nennt_das_paket_davor(self):
        p = self.punkt()["paket"]
        self.fertig(self.a)
        self.packen(p)
        self.assertEqual([(x["id"], x["davor"]) for x in urteil.zur_abnahme(self.con, self.pid)], [(p, "Motor")])


class Abnehmen(Grund):
    def test_ja_des_menschen_gibt_frei(self):
        p = self.punkt()["paket"]
        self.fertig(self.a)
        self.assertEqual(zwischenpruefung.zustand(self.con, p), "packt")
        self.assertEqual(urteil.zur_abnahme(self.con, self.pid), [])
        self.packen(p)
        self.assertEqual(zwischenpruefung.zustand(self.con, p), "wartet_mensch")
        self.assertEqual([(x["id"], x["pruefpunkt"]) for x in urteil.zur_abnahme(self.con, self.pid)], [(p, True)])
        for von in ("TL", "CC1", "CC2"):
            with self.subTest(von=von), self.assertRaisesRegex(kern.AmwFehler, "wartet auf Alex|Abnehmen kann"):
                urteil.entscheiden(self.con, self.pid, von, p)
        self.assertFalse(self.darf_starten(self.b))
        self.assertEqual(urteil.entscheiden(self.con, self.pid, MENSCH, p), "fertig")
        self.assertEqual(planung.offene_vorgaenger(self.con, self.b), [])
        self.assertTrue(self.darf_starten(self.b))
        self.assertEqual(zwischenpruefung.offene(self.con, self.pid), [])

    def test_zurueck_an_packer_und_lead_dann_neu(self):
        p = self.punkt()["paket"]
        self.fertig(self.a)
        self.packen(p)
        urteil.entscheiden(self.con, self.pid, MENSCH, p, ja=False, grund_text="Motor ruckelt")
        self.assertEqual(zwischenpruefung.zustand(self.con, p), "zurueck")
        self.assertEqual([a for a, _ in self.post("CC1", "nicht abgenommen")], ["korrektur"])
        self.assertEqual(self.post("TL", "zurück von Alex"), [("auftrag", f"Prüfpunkt A{p}: zurück von Alex – Nacharbeit schneiden")])
        self.assertFalse(self.darf_starten(self.b))
        n = self.paket("Motor glätten", agent="CC2", nach=[self.a])                         # Nacharbeit vor dem Packen
        planung.abhaengigkeit_setzen(self.con, self.pid, "TL", p, [n])
        self.assertNotIn((p, n), self.kanten())                                             # kein Kreis, die Nacharbeit wartet nicht
        self.assertIn((n, p), self.kanten())
        self.assertEqual(planung.offene_vorgaenger(self.con, n), [])
        self.assertEqual(zwischenpruefung.nachziehen(self.con, self.pid), [])
        with mock.patch.object(db, "jetzt", return_value="2099-01-01T00:00:00Z"):
            dokumente.ablegen_inhalt(self.con, self.pid, "CC1", b"neuer Stand", "stand2.md", titel="Stand 2", art="ergebnis", aufgabe=p)
        self.assertEqual(zwischenpruefung.zustand(self.con, p), "wartet_mensch")

    def test_niemand_schliesst_ihn_sonst(self):
        p = self.punkt()["paket"]
        self.packen(p)
        for von, status in (("CC1", "fertig"), ("TL", "fertig"), ("TL", "verwerfen"), (MENSCH, "fertig")):
            with self.subTest(von=von, status=status), self.assertRaisesRegex(kern.AmwFehler, "ist ein Prüfpunkt"):
                kern.aufgabe_status(self.con, self.pid, von, p, status, beleg="abc1234", zusammenfassung="x")
        with self.assertRaisesRegex(kern.AmwFehler, "ist ein Prüfpunkt"):                   # auch die AMW nicht (Auslieferung, gemergter PR)
            kern.aufgabe_status(self.con, self.pid, "AMW", p, "fertig", beleg="abc1234", zusammenfassung="x", automatik=True)
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (p,)).fetchone()[0], "laeuft")

    def test_ausgelieferter_commit_des_packers_schliesst_ihn_nicht(self):
        from amw import planautomatik
        kern.projekt_einstellen(self.con, self.pid, "TL", plan_automatik="an")
        p = self.punkt()["paket"]
        self.packen(p)
        with db.schreiben(self.con):
            db.einfuegen(self.con, "pruefung", projekt_id=self.pid, aufgabe_id=p, zweig="z", sha="a" * 40, bauer="CC1", pruefer="TL", ergebnis="gruen",
                         angefragt_utc=db.jetzt(), ergebnis_utc=db.jetzt())
        with mock.patch("amw.betrieb.merge_ok", return_value={"von": "TL"}):
            planautomatik.ausgeliefert(self.con, self.pid, "1.0.0", "a" * 40, lambda sha: True)
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (p,)).fetchone()[0], "laeuft")

    def test_release_ausliefern_lehnt_ab(self):
        p = self.punkt()["paket"]
        k = auslieferung.Kette.__new__(auslieferung.Kette)
        k.con = self.con
        self.assertEqual(k.pruefpunkte(p, None), [f"Prüfpunkt: A{p} packt nur den Stand zum Testen und liefert nichts aus"])
        self.assertEqual(k.pruefpunkte(None, self.a), [])


class Entfernen(Grund):
    def test_genau_die_eigenen_kanten(self):
        vorher = self.kanten()
        r = self.punkt()
        p = r["paket"]
        planung.abhaengigkeit_setzen(self.con, self.pid, "TL", self.frei, [p])              # von Hand hinter den Prüfpunkt
        e = zwischenpruefung.entfernen(self.con, self.pid, MENSCH, p)
        self.assertEqual(self.kanten(), vorher | {(p, self.frei)})                          # die von Hand gesetzte bleibt
        self.assertEqual(sorted(map(tuple, e["kanten"])), sorted([(self.a, p), (p, self.b)]))
        self.assertEqual(self.con.execute("SELECT status FROM aufgabe WHERE id = ?", (p,)).fetchone()[0], "verworfen")
        self.fertig(self.a)
        self.assertTrue(self.darf_starten(self.b))

    def test_kante_die_es_schon_gab_gehoert_uns_nicht(self):
        p = self.punkt(self.b)["paket"]                                                     # b → p → c
        zwischenpruefung.entfernen(self.con, self.pid, MENSCH, p)
        self.assertIn((self.b, self.c), self.kanten())
        with db.schreiben(self.con):                                                        # eine von Hand gesetzte Kante ist nie „neu“
            self.assertEqual(zwischenpruefung._kanten_setzen(self.con, [(self.b, self.c), (self.frei, self.c)]), [(self.frei, self.c)])

    def test_wer_darf(self):
        p = self.punkt()["paket"]
        with self.assertRaisesRegex(kern.AmwFehler, "hat Alex gesetzt"):
            zwischenpruefung.entfernen(self.con, self.pid, "TL", p, "keine Zeit")
        with self.assertRaisesRegex(kern.AmwFehler, "der Mensch oder der Lead"):
            zwischenpruefung.entfernen(self.con, self.pid, "CC1", p, "x")
        zwischenpruefung.entfernen(self.con, self.pid, MENSCH, p)
        p = self.punkt(von="TL", grund="testen")["paket"]
        with self.assertRaisesRegex(kern.AmwFehler, "nur mit Grund"):
            zwischenpruefung.entfernen(self.con, self.pid, "TL", p)
        zwischenpruefung.entfernen(self.con, self.pid, "TL", p, "erst später")
        with self.assertRaisesRegex(kern.AmwFehler, "kein offener Prüfpunkt"):
            zwischenpruefung.entfernen(self.con, self.pid, MENSCH, p)


class Nachziehen(Grund):
    def test_neuer_nachfolger_wartet_auch(self):
        p = self.punkt()["paket"]
        n = self.paket("Neu", agent="CC2", nach=[self.a])                                   # beim Setzen der Abhängigkeit
        self.assertIn((p, n), self.kanten())
        self.assertEqual(zwischenpruefung.nachziehen(self.con, self.pid), [])               # einmal
        zwischenpruefung.entfernen(self.con, self.pid, MENSCH, p)
        self.assertNotIn((p, n), self.kanten())                                             # auch die später gesetzte gehört dazu

    def test_dienst_runde_findet_was_am_befehl_vorbei_kam(self):
        p = self.punkt()["paket"]
        with db.schreiben(self.con):
            self.con.execute("INSERT INTO abhaengigkeit (vor, nach, art) VALUES (?, ?, 'FS')", (self.a, self.frei))
        self.assertEqual(zwischenpruefung.nachziehen(self.con, self.pid), [f"Prüfpunkt A{p}: A{self.frei} wartet jetzt auch"])
        import inspect
        from amw import dienst
        self.assertIn("zwischenpruefung.nachziehen(self.con, pid_)", inspect.getsource(dienst))

    def test_geloeste_kante_kommt_nicht_wieder(self):
        p = self.punkt()["paket"]
        planung.abhaengigkeit_setzen(self.con, self.pid, "TL", self.b, [p], entfernen=True)
        zwischenpruefung.nachziehen(self.con, self.pid)
        self.assertNotIn((p, self.b), self.kanten())

    def test_zwei_pruefpunkte_hintereinander(self):
        p1 = self.punkt(self.a)["paket"]
        p2 = self.punkt(self.b)["paket"]
        self.assertEqual({(p1, self.b), (self.b, p2), (p2, self.c)} - self.kanten(), set())
        self.assertEqual(zwischenpruefung.dahinter(self.con, self.pid)[self.b], p1)
        self.assertEqual({x["paket"] for x in zwischenpruefung.uebersicht(self.con, self.pid)}, {p1, p2})


class Anzeige(Grund):
    def test_zeitplan_und_prognose_sagen_wartet_auf(self):
        p = self.punkt()["paket"]
        z = {x["aid"]: x for x in zeitplan.berechnen(self.con, self.pid)["pakete"]}
        self.assertEqual([z[x]["wartet_auf"] for x in (self.a, p, self.b, self.c, self.frei)], [None, None, "Alex", "Alex", None])
        self.assertIn("wartet auf Alex", zeitplan.zeile(z[self.b]))
        g = planung.prognose(self.con, self.pid, laeufe=20)
        self.assertEqual([g["schritte"][x].get("wartet_auf") for x in (self.a, self.b, self.frei)], [None, "Alex", None])
        self.assertEqual(g["boegen"][self.bid]["wartet_auf"], "Alex")
        self.fertig(self.a)
        self.packen(p)
        z = {x["aid"]: x for x in zeitplan.berechnen(self.con, self.pid)["pakete"]}
        self.assertEqual(z[p]["wartet_auf"], "Alex")                                        # gepackt: das Paket selbst wartet auf ihn
        urteil.entscheiden(self.con, self.pid, MENSCH, p)
        self.assertNotIn("wartet_auf", planung.prognose(self.con, self.pid, laeufe=20)["boegen"][self.bid])

    def test_verlauf(self):
        p = self.punkt(von="TL", grund="vor dem Ton")["paket"]
        self.fertig(self.a)
        self.packen(p)
        urteil.entscheiden(self.con, self.pid, MENSCH, p, ja=False, grund_text="Motor ruckelt")
        with mock.patch.object(db, "jetzt", return_value="2099-01-01T00:00:00Z"):
            dokumente.ablegen_inhalt(self.con, self.pid, "CC1", b"neu", "s2.md", titel="S2", art="ergebnis", aufgabe=p)
            urteil.entscheiden(self.con, self.pid, MENSCH, p)
        t = [x["text"] for x in verlauf_quellen.gesamt(self.con, self.pid, [], lambda e: "umsetzung") if x["art"] == "pruefpunkt"]
        self.assertEqual(t, ["M1: Prüfpunkt hinter „Motor“ – Alex testet, 2 Pakete warten – vor dem Ton", "M1: Prüfpunkt hinter „Motor“ – zurück: Motor ruckelt",
                             "M1: Prüfpunkt hinter „Motor“ – getestet, weiter"])

    def test_verlauf_kuerzt_den_titel_nicht_das_wichtige(self):
        self.setze(self.a, titel="Navigation Teil 1: Menü und Namen, Übergang mit „Fragen“ bis „Für dich“, Reste von Tor und Phase, Suche im Kopf")
        self.punkt(von="TL", grund="vor dem Ton")
        e = next(x for x in verlauf_quellen.gesamt(self.con, self.pid, [], lambda e: "umsetzung") if x["art"] == "pruefpunkt")
        self.assertIn(" …“ – Alex testet, 2 Pakete warten – vor dem Ton", e["text"])

    def test_startdaten_befehl_und_seite(self):
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(aus):
            rc = cli.main(["aufgabe", "pruefpunkt", str(self.a), "--von", "TL", "--projekt", "Produkt", "--grund", "testen"])
        self.assertEqual(rc, 0, aus.getvalue())
        self.assertIn("2 Paket(e) warten auf Alex", aus.getvalue())
        u = workbench.daten_start(self.con, self.pid)["pruefpunkte"]
        self.assertEqual([(x["nach"], x["zustand"], x["wartet"], x["von"]) for x in u], [(self.a, "packt", [self.b, self.c], "TL")])
        r = aktionen.planen(self.con, self.pid, "pruefpunkt", {"aufgabe": u[0]["paket"], "entfernen": True})
        self.assertEqual((r["ok"], r["nach"]), (True, self.a))
        r = aktionen.planen(self.con, self.pid, "pruefpunkt", {"aufgabe": self.a, "agent": "CC2"})
        self.assertEqual(self.con.execute("SELECT agent FROM aufgabe WHERE id = ?", (r["paket"],)).fetchone()[0], "CC2")

    def test_verteilen_und_weckruf_lassen_die_wartenden(self):
        kern.projekt_einstellen(self.con, self.pid, "TL", verteilen="an")
        p = self.punkt()["paket"]
        self.setze(self.b, agent=None)
        self.fertig(self.a)
        verteilen.verteilen(self.con, self.pid)
        self.assertIsNone(self.con.execute("SELECT agent FROM aufgabe WHERE id = ?", (self.b,)).fetchone()[0])
        wartegrund.startklar_wecken(self.con, self.pid)
        self.assertEqual([k for _, k in self.post("CC1", f"A{self.c} ")], [])
        self.assertTrue(p)

    def test_kein_planer_ruehrt_ihn_an(self):
        p = self.punkt()["paket"]
        self.assertEqual(arbeitspaket.lesen(self.con, p)["art"], "agent")                   # nie headless
        self.assertTrue(zwischenpruefung.ist(self.con, p))
        self.assertFalse(zwischenpruefung.ist(self.con, self.a))
        tid = themen.neu(self.con, self.pid, MENSCH, "Motor")
        r = planer_delta.anwenden(self.con, self.pid, MENSCH, tid, 1, {"verwerfen": [{"paket": p, "grund": "weg"}], "aendern": [{"paket": p, "auftrag": "anders"}]})
        self.assertEqual((r["geaendert"], r["verworfen"], r["uebersprungen"]), ([], [], [f"A{p} ist ein Prüfpunkt"] * 2))
