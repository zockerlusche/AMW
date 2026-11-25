"""A2142: „Für dich“ – alles, was der Mensch tun muss, genau einmal (amw/fuer_dich.py): je Quelle ein Fall, der zählt, und einer, der nicht
zählen darf; Doppelte, Projekte getrennt, leer, Reihenfolge, eine scheiternde Quelle. Nur lesend."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import unittest
from unittest import mock

from amw import (abschlusslage, db, delta_start, feinplanung, fertigquelle, fragentopf, fuer_dich, grobplan, kern, planansicht, planer, planung, projektweg_seite, steuerung,
                 themen, tore, urteil, veroeffentlichung, workbench, zwischenpruefung)
from tests import test_planung
from tests import test_projektweg_seite as pws

MENSCH = kern.ENTWICKLER


class Grund(pws.Grund):
    def sammeln(self, pid=None):
        d = fuer_dich.sammeln(self.con, pid or self.pid)
        self.assertEqual(d["zahl"], len(d["eintraege"]))
        self.assertEqual(len({(e["art"], e["id"]) for e in d["eintraege"]}), d["zahl"], "jedes Ding genau einmal")
        for e in d["eintraege"]:
            self.assertEqual(set(e), {"art", "id", "titel", "was", "seit_utc", "ziel", "blockiert"})
            self.assertTrue(e["titel"] and e["was"] and e["seit_utc"] and e["ziel"]["sicht"], e)
            self.assertIs(type(e["blockiert"]), bool)
        return d

    def art(self, *arten, pid=None):
        d = self.sammeln(pid)
        self.assertEqual(d["fehler"], [])
        return [e for e in d["eintraege"] if e["art"] in arten]

    def alle(self):
        return [(e["art"], e["id"]) for e in self.sammeln()["eintraege"]]

    def setze(self, tabelle, nr, **w):
        with db.schreiben(self.con):
            self.con.execute(f"UPDATE {tabelle} SET {', '.join(k + ' = ?' for k in w)} WHERE id = ?", (*w.values(), nr))

    def regel(self, **w):
        kern.projekt_einstellen(self.con, self.pid, MENSCH, **w)

    def post(self, von="AMW", art="meldung", kurz="Bitte ansehen", **w):
        with db.schreiben(self.con):
            return kern._posten(self.con, self.pid, von, MENSCH, art, kurz, **w)[0]

    def bogen(self, titel):
        return self.con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND titel = ?", (self.pid, titel)).fetchone()

    def frage(self, kurz="Blau oder grün?", an="entwickler", von="TL", **w):
        return kern.frage_neu(self.con, self.pid, von, an, kurz, [], pruefen=False, **w)

    def aufgabe(self, titel="Anleitung schreiben", agent="CC1", quelle=None, bereit=False):
        aid = kern.aufgabe_neu(self.con, self.pid, "TL", titel, agent=agent)
        if quelle:
            fertigquelle.setzen(self.con, self.pid, "TL", aid, quelle)
        if bereit:
            urteil.bereit_melden(self.con, self.pid, "TL", aid)
        return aid


class Leer(Grund):
    def test_leer(self):
        self.assertEqual(fuer_dich.sammeln(self.con, self.pid), {"eintraege": [], "zahl": 0, "fehler": []})

    def test_nur_lesend(self):
        pws.demo(self.con, self.pid, "abschluss")
        self.frage()
        vorher = self.con.total_changes
        self.assertGreaterEqual(self.sammeln()["zahl"], 2)
        self.assertEqual(self.con.total_changes, vorher)


class Fragen(Grund):
    def test_offene_frage_zaehlt(self):
        f = self.frage()
        e, = self.art("frage")
        self.assertEqual((e["id"], e["titel"], e["was"], e["ziel"], e["blockiert"]), (f"F{f}", "Blau oder grün?", "beantworten", {"sicht": "fragen", "nr": f}, False))

    def test_geparkt_beim_lead_und_beantwortet_nicht(self):
        kern.frage_parken(self.con, self.pid, "TL", self.frage())
        self.frage(an="tl", von="CC1")
        kern.frage_antworten(self.con, self.pid, self.frage("Schon klar?"), "text", "ja", "seite")
        self.assertEqual(self.alle(), [])

    def test_alle_nicht_nur_zwanzig(self):
        for i in range(25):
            self.frage(f"Frage {i}?")
        self.assertEqual(len(self.art("frage")), 25)

    def test_nachtrag_zaehlt_nicht_noch_einmal(self):
        f = self.frage()
        kern.frage_nachtrag(self.con, self.pid, "TL", f, "Noch etwas dazu")
        self.post(kurz=f"F{f} seit 24 h ohne Antwort", bezug=f"F{f}")
        self.assertEqual(self.alle(), [("frage", f"F{f}")])

    def test_blockiert(self):
        self.frage(blockiert=True)
        self.assertTrue(self.art("frage")[0]["blockiert"])


class Themen(Grund):
    def thema(self, text="Ein Text."):
        t = themen.neu(self.con, self.pid, "TL", "Anmeldung", pfleger="CC1")
        if text:
            themen.pflegen(self.con, self.pid, "CC1", t, text)
        return t

    def test_wartet_auf_dich(self):
        t = self.thema()
        e, = self.art("thema")
        self.assertEqual((e["id"], e["titel"], e["was"], e["ziel"]), (f"TH{t}", "Anmeldung", "freigeben", {"sicht": "themen", "nr": t}))

    def test_in_arbeit_und_freigegeben_nicht(self):
        t = self.thema("")
        self.assertEqual(self.alle(), [])
        themen.pflegen(self.con, self.pid, "CC1", t, "Text.")
        themen.freigeben(self.con, self.pid, MENSCH, t)
        self.assertEqual(self.art("thema"), [])

    def test_co_und_lead_geben_frei(self):
        self.regel(thema_freigabe="co+lead", co_entwickler="CC1")
        t = self.thema()
        self.assertEqual(self.art("thema"), [])
        themen.nur_mensch_setzen(self.con, self.pid, "TL", t)
        self.assertEqual(len(self.art("thema")), 1)


class Grob(Grund):
    def test_nur_die_neueste_fassung(self):
        pws.demo(self.con, self.pid, "grob2")
        e, = self.art("grob")
        self.assertEqual((e["id"], e["titel"], e["was"], e["ziel"]["sicht"], e["ziel"]["nr"]), ("G2", "Grobplan Fassung 2", "freigeben", "projektweg", 2))

    def test_angenommen_nicht(self):
        pws.demo(self.con, self.pid, "fein")
        self.assertEqual(self.art("grob"), [])

    def test_co_und_lead_nicht(self):
        pws.demo(self.con, self.pid, "grob1")
        self.regel(grobplan_freigabe="co+lead", co_entwickler="CC1")
        self.assertEqual(self.art("grob"), [])

    def test_gescheiterte_fassung_klaert_der_lead(self):
        pws.demo(self.con, self.pid, "grob1")
        grobplan.entwurf_eintragen(self.con, self.pid, 2, None, fehler="kein JSON")
        self.assertEqual(self.art("grob"), [])

    def test_laeuft_gerade_nicht(self):
        pws.demo(self.con, self.pid, "grob1")
        with mock.patch.object(grobplan, "laeuft", return_value={"fassung": 2, "zeit_utc": db.jetzt()}):
            self.assertEqual(self.art("grob"), [])

    def test_meldung_ohne_lead_ist_dasselbe(self):
        pws.demo(self.con, self.pid, "grob2")
        self.post(kurz="Grobplan Fassung 2: 3 Meilensteine, 2 Befunde, 0 Fragen – Ja oder neu planen")
        self.assertEqual([e["art"] for e in self.sammeln()["eintraege"]], ["grob"])
        self.post(kurz="Grobplan Fassung 3: Planer-Ergebnis passt nicht")                       # etwas anderes: bleibt
        self.assertEqual([e["art"] for e in self.sammeln()["eintraege"]], ["grob", "nachricht"])


class Plan(Grund):
    def setUp(self):
        super().setUp()
        pws.demo(self.con, self.pid, "fein")
        self.m = self.bogen("Welt sichtbar")

    def test_feinplan_wartet(self):
        e, = self.art("plan", "start", "grob")
        self.assertEqual((e["art"], e["id"], e["titel"], e["was"], e["ziel"]["sicht"], e["ziel"]["nr"]),
                         ("plan", f"M{self.m['nr']}", "Welt sichtbar", "freigeben", "projektweg", self.m["id"]))

    def test_freigegeben_nicht(self):
        feinplanung.plan_starten(self.con, self.pid, MENSCH, self.m["id"])
        self.assertEqual(self.art("plan", "start", "grob"), [])

    def test_co_und_lead_nicht(self):
        self.regel(feinplan_freigabe="co+lead", co_entwickler="CC1")
        self.assertEqual(self.art("plan"), [])

    def test_der_planer_laeuft_noch(self):
        with mock.patch.object(feinplanung, "laeuft", return_value={"fassung": 2}):
            self.assertEqual(self.art("plan"), [])

    def test_zurueckgegeben_ist_der_lead_dran_bis_sich_etwas_aendert(self):
        planansicht.zurueck(self.con, self.pid, MENSCH, self.m["id"], "plan", "kleiner schneiden")
        self.assertEqual(self.art("plan"), [])
        with db.schreiben(self.con):                                                            # der Lead ändert erst danach
            self.con.execute("UPDATE plan_ereignis SET zeit_utc = '2020-01-01T00:00:00Z' WHERE art = ? AND text LIKE '%kleiner schneiden%'", (planansicht.FREI,))
        aid = self.con.execute("SELECT min(id) FROM aufgabe WHERE bogen_id = ?", (self.m["id"],)).fetchone()[0]
        planung.schritt_setzen(self.con, self.pid, "TL", aid=aid, auftrag="Nur das Gerüst.")
        self.assertEqual(len(self.art("plan")), 1)

    def test_meldung_ohne_lead_ist_dasselbe(self):
        self.post(kurz=f"Feinplan M{self.m['nr']} Fassung 1: 5 Pakete angelegt – wartet auf das Ja")
        self.assertEqual([e["art"] for e in self.sammeln()["eintraege"]], ["plan"])

    def test_erst_der_meilenstein_dann_sein_plan(self):
        b = planung.bogen_neu(self.con, self.pid, "TL", "Zusatz")
        self.assertEqual(self.art("grob"), [])                                                  # noch ohne Pakete
        planung.schritt_setzen(self.con, self.pid, "TL", titel="Schritt", bogen_id=b, agent="CC1")
        self.assertEqual([e["titel"] for e in self.art("grob")], ["Zusatz"])
        planansicht.freigeben(self.con, self.pid, MENSCH, b, "grob")
        self.assertEqual((self.art("grob"), sorted(e["titel"] for e in self.art("plan"))), ([], ["Welt sichtbar", "Zusatz"]))


class Aenderung(Grund):
    def test_aenderung_dann_start(self):
        t = pws.wartende_aenderung(self.con, self.pid)
        e, = self.art("aenderung", "start", "plan")
        self.assertEqual((e["art"], e["titel"], e["was"], e["ziel"]["thema"]), ("aenderung", "Speichern und Laden", "freigeben", t[2]))
        with mock.patch.object(delta_start, "nach_dem_ja", return_value=None):
            planer.uebernehmen(self.con, self.pid, MENSCH, t[2])
        b = self.bogen("Drei Speicherplätze")
        e, = self.art("aenderung", "start", "plan", "grob")
        self.assertEqual((e["art"], e["id"], e["titel"], e["was"], e["ziel"]["nr"]), ("start", f"M{b['nr']}", "Drei Speicherplätze", "starten", b["id"]))
        self.regel(feinplan_freigabe="co+lead", grobplan_freigabe="co+lead", co_entwickler="CC1")
        self.assertEqual([x["art"] for x in self.art("start")], ["start"])                      # nachholen kann nur der Mensch
        delta_start.nachholen(self.con, self.pid, MENSCH, b["id"])
        self.assertEqual(self.art("aenderung", "start", "plan", "grob"), [])

    def test_co_und_lead_nicht(self):
        pws.wartende_aenderung(self.con, self.pid)
        self.regel(feinplan_freigabe="co+lead", grobplan_freigabe="co+lead", co_entwickler="CC1")
        self.assertEqual(self.art("aenderung"), [])

    def test_gescheiterte_klaert_der_lead(self):
        pws.gescheiterte_aenderung(self.con, self.pid)
        self.assertEqual(len(projektweg_seite.daten(self.con, self.pid)["fein"]["delta_fehler"]), 1)
        self.assertEqual(self.alle(), [])


class Abnahme(Grund):
    def bereit(self, bis="abschluss"):
        pws.demo(self.con, self.pid, bis)
        self.m = self.bogen("Welt sichtbar")

    def test_abnahme_und_meldung_zaehlen_einmal(self):
        self.bereit()
        self.assertEqual(abschlusslage.lage(self.con, self.pid, self.m), "abnehmbar")
        self.assertEqual(workbench.an_dich_zahl(self.con, self.pid), 1)                         # die Meldung „bereit zur Abnahme“
        e, = self.sammeln()["eintraege"]
        self.assertEqual((e["art"], e["id"], e["titel"], e["was"], e["ziel"]["sicht"], e["ziel"]["nr"]),
                         ("abnahme", f"M{self.m['nr']}", "Welt sichtbar", "abnehmen", "projektweg", self.m["id"]))
        self.post(kurz=f"Meilenstein {self.m['nr']} „Welt sichtbar“ bereit zur Abnahme (D9)")    # Altbestand ohne Bezug
        self.assertEqual(len(self.alle()), 1)

    def test_abgenommen_nicht_auch_wenn_die_meldung_noch_offen_ist(self):
        self.bereit()
        planansicht.freigeben(self.con, self.pid, MENSCH, self.m["id"], "abschluss")
        self.assertEqual(workbench.an_dich_zahl(self.con, self.pid), 1)
        self.assertEqual(self.alle(), [])

    def test_wartet_auf_auslieferung(self):
        self.bereit()
        with mock.patch.object(abschlusslage, "auslieferung", return_value=[1]):
            self.assertEqual(self.alle(), [])

    def test_pruefung_fehlt_klaert_der_lead(self):
        self.bereit("abschluss-ohne")
        with mock.patch.object(abschlusslage, "pruefer_geht", return_value=True):
            self.assertEqual(self.alle(), [])

    def test_nicht_abnehmbar_aber_beim_menschen_bleibt_die_meldung(self):
        """Planer aus: niemand holt die Prüfung nach. Keine Abnahme, aber die Meldung an ihn geht nicht verloren."""
        self.bereit("abschluss-ohne")
        self.assertEqual([e["art"] for e in self.sammeln()["eintraege"]], ["nachricht"])

    def test_co_und_lead_nicht(self):
        self.bereit()
        self.regel(abschluss_freigabe="co+lead", co_entwickler="CC1")
        self.assertEqual(self.alle(), [])

    def test_zurueckgegeben_bis_zum_neuen_bericht(self):
        self.bereit()
        planansicht.zurueck(self.con, self.pid, MENSCH, self.m["id"], "abschluss", "Ton fehlt")
        self.assertEqual(self.alle(), [])
        tore.bericht_erstellen(self.con, self.pid, self.m["id"], bereit=True)
        self.assertEqual(self.alle(), [("abnahme", f"M{self.m['nr']}")])

    def test_fertig_und_noch_nicht_veroeffentlicht(self):
        b = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden")
        self.setze("bogen", b, status="fertig", fertig_utc=db.jetzt())
        self.assertEqual(self.alle(), [])                                                       # nichts ausgeliefert
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc="2020-01-01T00:00:00Z", von="AMW", art=veroeffentlichung.LOKAL, text="{}")
        e, = self.art("abnahme")
        self.assertEqual((e["titel"], e["was"], e["ziel"]["sicht"], e["ziel"]["nr"]), ("Anmelden", "abnehmen", "start", b))
        with db.schreiben(self.con):
            db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von=MENSCH, art=veroeffentlichung.ABNAHME, bogen_id=b, text="")
        self.assertEqual(self.alle(), [])


class Aufgaben(Grund):
    def test_bereit_zaehlt(self):
        a = self.aufgabe(quelle="ja", bereit=True)
        e, = self.art("aufgabe")
        self.assertEqual((e["id"], e["titel"], e["was"], e["ziel"]), (f"A{a}", "Anleitung schreiben", "abnehmen", {"sicht": "aufgabe", "nr": a}))
        self.post(kurz=f"A{a} bereit zur Abnahme: Anleitung schreiben", aufgabe_id=a)
        self.assertEqual(self.alle(), [("aufgabe", f"A{a}")])

    def test_nicht_bereit_andere_quelle_und_zurueck_nicht(self):
        self.aufgabe("noch dabei", quelle="ja")
        self.aufgabe("schliesst die AMW", quelle="commit")
        urteil.entscheiden(self.con, self.pid, MENSCH, self.aufgabe(quelle="ja", bereit=True), ja=False, grund_text="unvollständig")
        self.assertEqual(self.alle(), [])

    def test_kleinprobe_nimmt_der_co_ab(self):
        for titel in ("Kleinprobe Leitstand", "Für dich: Kleinprobe"):
            self.aufgabe(titel, quelle="ja", bereit=True)
        self.assertEqual(len(self.art("aufgabe")), 2)                                           # ohne Co nimmt sie sonst niemand ab
        self.regel(co_entwickler="CC1")
        self.assertEqual(self.alle(), [])
        a = self.aufgabe("Ausbau nach der Kleinprobe", quelle="ja", bereit=True)                # keine Kleinprobe
        self.assertEqual(self.alle(), [("aufgabe", f"A{a}")])
        self.setze("aufgabe", a, verantwortlich="CC1")                                          # der Co nimmt ausdrücklich ab
        self.assertEqual(self.alle(), [])

    def test_pruefpunkt(self):
        b = planung.bogen_neu(self.con, self.pid, "TL", "Motor")
        a = planung.schritt_setzen(self.con, self.pid, "TL", titel="Motor", bogen_id=b, agent="CC1", groesse="S", art="mechanisch")
        planung.schritt_setzen(self.con, self.pid, "TL", titel="Ton", bogen_id=b, agent="CC1", groesse="S", art="mechanisch", nach=[a])
        p = zwischenpruefung.einfuegen(self.con, self.pid, MENSCH, a)["paket"]
        self.assertEqual(self.art("pruefpunkt", "aufgabe"), [])                                 # er wird noch gepackt
        urteil.bereit_melden(self.con, self.pid, "TL", p)
        self.regel(co_entwickler="CC1")
        e, = self.art("pruefpunkt", "aufgabe")
        self.assertEqual((e["art"], e["id"], e["was"]), ("pruefpunkt", f"A{p}", "testen"))


class Vorschlag(Grund):
    def test_startvorschlag_und_abgelehnt(self):
        steuerung.profil_setzen(self.con, self.pid, MENSCH, "CC1", ordner=self.ordner.name)
        self.assertEqual(self.alle(), [])                                                       # ohne Arbeit kein Vorschlag
        self.aufgabe("Etwas tun")
        e, = self.art("vorschlag")
        self.assertEqual((e["id"], e["titel"], e["was"], e["ziel"]), ("CC1", "CC1: Etwas tun", "starten", {"sicht": "agent", "nr": "CC1"}))
        steuerung.startvorschlag_ablehnen(self.con, self.pid, "CC1")
        self.assertEqual(self.alle(), [])


class PlanungWartet(Grund):
    def test_spezifikation(self):
        b = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", nr=19)                      # Projektnummer ≠ interne Nummer
        test_planung.alter_bestand(self.con, b)
        self.assertEqual(self.alle(), [])                                                       # Entwurf
        with db.schreiben(self.con):
            self.con.execute("UPDATE spezifikation SET status = 'vorgelegt' WHERE bogen_id = ? AND teil = 'anforderungen'", (b,))
        e, = self.art("plan")
        self.assertEqual((e["id"], e["titel"], e["was"], e["ziel"]), ("M19-anforderungen", "Anmelden", "freigeben", {"sicht": "planung", "nr": b, "teil": "anforderungen"}))
        self.regel(spec_frei="lead")
        self.assertEqual(self.alle(), [])

    def test_plan_und_seine_nachricht_einmal(self):
        mein, seiner = self.aufgabe("Umbau"), self.aufgabe("Anderes")
        planung.schritt_setzen(self.con, self.pid, "TL", aid=mein, verantwortlich=MENSCH)
        planung.schritt_setzen(self.con, self.pid, "TL", aid=seiner, verantwortlich="TL")
        for a in (mein, seiner):
            planung.plan_vorlegen(self.con, self.pid, "CC1", a, "So gehe ich vor.")
        self.assertEqual(workbench.an_dich_zahl(self.con, self.pid), 1)
        e, = self.sammeln()["eintraege"]
        self.assertEqual((e["art"], e["id"], e["titel"], e["was"]), ("plan", f"A{mein}", "Umbau", "freigeben"))

    def test_eigene_aufgabe(self):
        a = self.aufgabe("Konto anlegen", agent=MENSCH)
        e, = self.art("eigene")
        self.assertEqual((e["id"], e["titel"], e["was"]), (f"A{a}", "Konto anlegen", "erledigen"))
        self.setze("aufgabe", a, einstufung="geparkt")
        self.assertEqual(self.alle(), [])
        self.setze("aufgabe", a, einstufung="aktiv", status="fertig", beleg="D1")
        self.assertEqual(self.alle(), [])

    def test_eigene_und_zur_abnahme_einmal(self):
        a = self.aufgabe("Text lesen", agent=MENSCH, quelle="ja", bereit=True)
        self.assertEqual(self.alle(), [("aufgabe", f"A{a}")])


class Nachrichten(Grund):
    def test_was_zaehlt(self):
        n = self.post(von="CC1", art="frage", kurz="Passt das so?")
        e, = self.art("nachricht")
        self.assertEqual((e["id"], e["titel"], e["was"], e["ziel"]), (f"N{n}", "Passt das so?", "beantworten", {"sicht": "nachrichten", "nr": n}))
        self.post(kurz="Platz schaffen")
        self.assertEqual([x["was"] for x in self.art("nachricht")], ["beantworten", "lesen"])

    def test_infos_berichte_und_erledigtes_nicht(self):
        self.post(art="info")
        self.post(von="CC1", art="info")
        self.post(von="CC1")                                                                    # Bericht eines Agenten
        kern.erledigt(self.con, self.pid, MENSCH, [self.post()])
        self.assertEqual(self.alle(), [])

    def test_alle_nicht_nur_dreissig(self):
        for i in range(35):
            self.post(kurz=f"Nr. {i}")
        self.assertEqual(len(self.art("nachricht")), 35)

    def test_anderes_zum_selben_ding_bleibt(self):
        a = self.aufgabe(quelle="ja", bereit=True)
        n = self.post(von="TL", art="auftrag", kurz="Bitte den Schlüssel besorgen", aufgabe_id=a)
        self.assertEqual(self.alle(), [("aufgabe", f"A{a}"), ("nachricht", f"N{n}")])


class Getrennt(Grund):
    def test_projekte(self):
        with db.schreiben(self.con):
            q = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, q, "TL", rolle="lead")
        kern.agent_neu(self.con, q, "CC1")
        self.frage()
        self.post(kurz="Platz schaffen")
        self.aufgabe(quelle="ja", bereit=True)
        self.aufgabe("Konto anlegen", agent=MENSCH)
        pws.wartende_aenderung(self.con, self.pid)
        self.assertEqual(self.alle_von(q), [])
        pws.demo(self.con, q, "abschluss")
        self.assertEqual(sorted(self.alle_von(self.pid)), ["aenderung", "aufgabe", "eigene", "frage", "nachricht"])
        self.assertEqual(self.alle_von(q), ["abnahme"])

    def alle_von(self, pid):
        return [e["art"] for e in self.sammeln(pid)["eintraege"]]


class Reihenfolge(Grund):
    def test_blockierende_dann_freigaben_dann_der_rest_aelteste_zuerst(self):
        def z(n):
            return f"2026-11-{n:02d}T10:00:00Z"
        f1, f2, f3, f4 = self.frage("jung, blockiert", blockiert=True), self.frage("alt, blockiert", blockiert=True), self.frage("jung"), self.frage("alt")
        for f, n in ((f1, 20), (f2, 19), (f3, 12), (f4, 2)):
            self.setze("frage", f, zeit_utc=z(n))
        n1 = self.post(kurz="dazwischen")
        self.setze("nachricht", n1, zeit_utc=z(5))
        e1 = self.aufgabe("Konto anlegen", agent=MENSCH)
        self.setze("aufgabe", e1, angelegt_utc=z(1))
        a1, a2 = self.aufgabe("jünger", quelle="ja", bereit=True), self.aufgabe("älter", quelle="ja", bereit=True)
        with db.schreiben(self.con):
            for a, n in ((a1, 18), (a2, 17)):
                self.con.execute("UPDATE aufgabe SET angelegt_utc = ? WHERE id = ?", (z(1), a))
                self.con.execute("UPDATE plan_ereignis SET zeit_utc = ? WHERE aufgabe_id = ? AND art = ?", (z(n), a, urteil.BEREIT))
        d = self.sammeln()["eintraege"]
        self.assertEqual([e["id"] for e in d], [f"F{f2}", f"F{f1}", f"A{a2}", f"A{a1}", f"A{e1}", f"F{f4}", f"N{n1}", f"F{f3}"])
        self.assertEqual([e["seit_utc"] for e in d], [z(n) for n in (19, 20, 17, 18, 1, 2, 5, 12)])


class Fehler(Grund):
    def test_eine_scheiternde_quelle_laesst_die_anderen_stehen(self):
        f = self.frage()
        a = self.aufgabe(quelle="ja", bereit=True)
        n = self.post(kurz="Platz schaffen")
        voll = {("frage", f"F{f}"), ("aufgabe", f"A{a}"), ("nachricht", f"N{n}")}
        for ziel, name, quelle, fehlt in ((fragentopf, "blockiert", "fragen", "frage"), (themen, "fuer_dich", "themen", None), (projektweg_seite, "grob", "grob", None),
                                          (projektweg_seite, "fein", "fein", None), (projektweg_seite, "abschluss", "abnahmen", None),
                                          (veroeffentlichung, "zur_abnahme", "veroeffentlichung", None), (urteil, "zur_abnahme", "aufgaben", "aufgabe"),
                                          (steuerung, "startvorschlaege", "startvorschlaege", None), (planung, "freigaben_offen", "planung", None),
                                          (fuer_dich, "_dargestellt", "nachrichten", "nachricht")):
            with self.subTest(quelle=quelle), mock.patch.object(ziel, name, side_effect=RuntimeError("kaputt")), self.assertLogs("amw.fuer_dich", "WARNING"):
                d = self.sammeln()
                self.assertEqual(d["fehler"], [{"quelle": quelle, "text": "RuntimeError: kaputt"}])
                self.assertEqual({(e["art"], e["id"]) for e in d["eintraege"]}, {x for x in voll if x[0] != fehlt})

    def test_scheitert_die_abnahme_bleibt_ihre_meldung(self):
        pws.demo(self.con, self.pid, "abschluss")
        with mock.patch.object(projektweg_seite, "abschluss", side_effect=RuntimeError("kaputt")), self.assertLogs("amw.fuer_dich", "WARNING"):
            self.assertEqual([e["art"] for e in self.sammeln()["eintraege"]], ["nachricht"])


if __name__ == "__main__":
    unittest.main()
