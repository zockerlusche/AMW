"""Token-Pause: Konto-Verlauf aus den Messpunkten aller Sitzungen, Reset als Ereignis (auch außer der Reihe), Tempo,
„leer am“, Pause bis zum Reset und in den Folgewochen. Die Verläufe sind nachgestellt (Muster aus echten Messungen)."""
import datetime
import os
import tempfile
import unittest

from amw import db, kern, planung, tokenprognose as tp, workbench

UTC = datetime.timezone.utc


def t(tag, stunde=0, minute=0):
    return datetime.datetime(2026, 11, tag, stunde, minute, tzinfo=UTC)


def linie(von, bis, wert_von, wert_bis, schritt_min=30):
    """Messpunkte in gleichmäßigem Anstieg."""
    n = max(1, int((bis - von).total_seconds() // (schritt_min * 60)))
    return [(von + datetime.timedelta(minutes=schritt_min * i), wert_von + (wert_bis - wert_von) * i / n) for i in range(n + 1)]


class Verlauf(unittest.TestCase):
    def test_ein_wert_je_fenster_der_hoechste(self):
        reihe = tp.verlauf([("2026-11-03T10:01:00Z", 40.0), ("2026-11-03T10:07:00Z", 42.0), ("2026-11-03T10:14:59Z", 38.0),   # alte Sitzung hinkt nach
                            ("2026-11-03T10:16:00Z", 43.0), ("2026-11-03T10:20:00Z", None)])
        self.assertEqual(reihe, [(t(3, 10, 0), 42.0), (t(3, 10, 15), 43.0)])

    def test_grosse_uneinigkeit_im_selben_fenster_heisst_reset(self):
        # nach einem Reset zeigen einige Sitzungen noch den alten Stand – der niedrige Wert ist der frische
        reihe = tp.verlauf([(t(11, 3, 20), 90.0), (t(11, 3, 31), 90.0), (t(11, 3, 33), 2.0), (t(11, 3, 50), 4.0)])
        self.assertEqual([w for _, w in reihe], [90.0, 2.0, 4.0])
        self.assertEqual(tp.resets(reihe), [t(11, 3, 30)])

    def test_reset_ausser_der_reihe_ist_kein_verbrauch(self):
        # Woche läuft, Reset wie angekündigt, dann zwei Resets außer der Reihe am selben Tag
        punkte = (linie(t(5), t(7, 5), 50, 78) + linie(t(7, 5, 15), t(10, 12), 0, 98) + linie(t(10, 12, 30), t(11, 3), 90, 90)
                  + linie(t(11, 3, 30), t(11, 12, 30), 0, 51) + linie(t(11, 12, 45), t(11, 14), 3, 7))
        reihe = tp.verlauf(punkte)
        self.assertEqual(tp.resets(reihe), [t(7, 5, 15), t(11, 3, 30), t(11, 12, 45)])
        anstiege = tp.tagesanstiege(reihe, t(11, 14))
        self.assertAlmostEqual(anstiege[datetime.date(2026, 11, 11)], 51 + 4, delta=0.6)       # beide Stücke des Tages, kein Abfall
        self.assertAlmostEqual(sum(anstiege.values()), 28 + 98 + 51 + 4, delta=1.0)             # Rauschen 98 → 90 zählt nicht


class Lage(unittest.TestCase):
    def test_leer_vor_dem_reset_ergibt_pause(self):
        reihe = tp.verlauf(linie(t(7, 5), t(10, 5), 0, 90))                                      # 30 Punkte je Tag
        lage = tp.stand(reihe, t(10, 5), reset_angekuendigt=t(14, 5))
        self.assertEqual((lage["wert"], lage["tempo"]), (90.0, 30.0))
        self.assertEqual(lage["leer_utc"], t(10, 13))                                            # Rest 10 Punkte = 8 Stunden
        self.assertAlmostEqual(lage["pause_tage"], 3.67, places=2)                               # bis zum Reset am 14.
        self.assertAlmostEqual(lage["arbeitstage_je_woche"], 3.33, places=2)
        self.assertAlmostEqual(lage["pause_je_woche"], 3.67, places=2)
        self.assertIsNone(lage["unsicher"])

    def test_reicht_das_kontingent_gibt_es_keine_pause(self):
        reihe = tp.verlauf(linie(t(7, 5), t(11, 5), 0, 40))                                      # 10 Punkte je Tag
        lage = tp.stand(reihe, t(11, 5), reset_angekuendigt=t(14, 5))
        self.assertEqual((lage["pause_tage"], lage["arbeitstage_je_woche"], lage["pause_je_woche"]), (0.0, 7.0, 0.0))
        self.assertEqual(tp.verschieben(lage, 30, t(11, 5)), 0.0)

    def test_ohne_angekuendigten_reset_eine_woche_nach_dem_letzten(self):
        reihe = tp.verlauf(linie(t(1), t(4), 20, 80) + linie(t(4, 0, 15), t(8), 0, 60))
        lage = tp.stand(reihe, t(8), reset_angekuendigt=t(2))                                    # Ankündigung liegt in der Vergangenheit
        self.assertEqual((lage["letzter_reset_utc"], lage["reset_utc"]), (t(4, 0, 15), t(11, 0, 15)))

    def test_unsicher_wird_gesagt(self):
        self.assertIsNone(tp.stand([], t(8)))
        flach = tp.stand(tp.verlauf(linie(t(7), t(8), 40, 40)), t(8), t(14))
        self.assertEqual((flach["unsicher"], flach["tempo"]), ("kein_tempo", None))
        self.assertEqual(tp.verschieben(flach, 30, t(8)), 0.0)
        kurz = tp.stand(tp.verlauf(linie(t(7), t(8, 12), 0, 30)), t(8, 12), t(14))
        self.assertEqual(kurz["unsicher"], "wenige_tage")
        alt = tp.stand(tp.verlauf(linie(t(1), t(5), 0, 60)), t(8), t(9))
        self.assertEqual(alt["unsicher"], "alt")

    def test_verschieben_zaehlt_die_pausen_bis_zum_ende(self):
        reihe = tp.verlauf(linie(t(7, 5), t(10, 5), 0, 90))
        jetzt = t(10, 5)
        lage = tp.stand(reihe, jetzt, reset_angekuendigt=t(14, 5))                               # leer in 8 h, je Woche 3,33 T Arbeit
        self.assertEqual(tp.verschieben(lage, 0.2, jetzt), 0.0)                                  # fertig, bevor das Kontingent leer ist
        self.assertAlmostEqual(tp.verschieben(lage, 2, jetzt), 3.7, places=1)                    # eine Pause bis zum Reset
        self.assertAlmostEqual(tp.verschieben(lage, 5, jetzt), 7.3, places=1)                    # … und die der Folgewoche
        self.assertAlmostEqual(tp.verschieben(lage, 9, jetzt), 11.0, places=1)


class AusDerDatenbank(unittest.TestCase):
    def test_alle_projekte_zaehlen_zum_selben_konto(self):
        ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(ordner.cleanup)
        con = db.anlegen(os.path.join(ordner.name, "t.db"))
        self.addCleanup(con.close)
        iso = lambda x: x.strftime("%Y-%m-%dT%H:%M:%SZ")
        sitzungen = []
        for name in ("Eins", "Zwei"):
            with db.schreiben(con):
                pid = db.einfuegen(con, "projekt", name=name, angelegt_utc=db.jetzt())
            kern.agent_neu(con, pid, "CC1")
            aid = kern.agent_zeile(con, pid, "CC1")["id"]
            with db.schreiben(con):
                sitzungen.append(db.einfuegen(con, "sitzung", agent_id=aid, claude_sitzung=name, gestartet_utc=db.jetzt(), schluessel_datei="x.json",
                                              limit_7t_reset_utc=iso(t(14, 5)), status_utc=iso(t(10, 5))))
        with db.schreiben(con):
            for i, (zeit, wert) in enumerate(linie(t(7, 5), t(10, 5), 0, 90)):                    # abwechselnd aus beiden Projekten
                db.einfuegen(con, "verbrauch", sitzung_id=sitzungen[i % 2], agent="CC1", zeit_utc=iso(zeit), limit_7t=wert)
        lage = tp.lage(con, jetzt=t(10, 5))
        self.assertEqual((lage["wert"], lage["tempo"], lage["reset_utc"]), (90.0, 30.0, t(14, 5)))
        self.assertAlmostEqual(lage["pause_tage"], 3.67, places=2)
        self.assertIsNone(tp.lage(con, jetzt=t(30)))                                             # nichts im Zeitraum: keine Messung


def plan_mit_verbrauch(con, pid, lead="TL", agent="CC1", jetzt=None):
    """Ein aktiver Bogen mit offenen Schritten, Durchsatz der letzten Tage und ein Konto, das morgen leer ist."""
    jetzt = jetzt or datetime.datetime.now(UTC).replace(microsecond=0)
    iso = lambda x: x.strftime("%Y-%m-%dT%H:%M:%SZ")
    bid = planung.bogen_neu(con, pid, lead, "Karten-Look", ziel="z", abnahme="a")
    aid = kern.agent_zeile(con, pid, agent)["id"]
    with db.schreiben(con):
        con.execute("UPDATE bogen SET status = 'aktiv' WHERE id = ?", (bid,))
        for i in range(12):
            db.einfuegen(con, "aufgabe", projekt_id=pid, titel=f"Schritt {i}", agent=agent, angelegt_von=lead, status="wartet", rang=i + 1,
                         bogen_id=bid, angelegt_utc=iso(jetzt))
        for i in range(6):
            db.einfuegen(con, "aufgabe", projekt_id=pid, titel=f"Fertig {i}", agent=agent, angelegt_von=lead, status="fertig", beleg="abc1234",
                         angelegt_utc=iso(jetzt), fertig_utc=iso(jetzt - datetime.timedelta(days=i, hours=2)))
        sid = db.einfuegen(con, "sitzung", agent_id=aid, claude_sitzung="s", gestartet_utc=iso(jetzt), schluessel_datei="x.json",
                           limit_7t_reset_utc=iso(jetzt + datetime.timedelta(days=4)), status_utc=iso(jetzt), zustand="ruht")
        for zeit, wert in linie(jetzt - datetime.timedelta(days=3), jetzt, 0, 88):
            db.einfuegen(con, "verbrauch", sitzung_id=sid, agent=agent, zeit_utc=iso(zeit), limit_7t=round(wert, 1))
    tp._gemerkt.clear()
    return bid


class Pausentage(unittest.TestCase):
    def test_tage_ohne_kontingent(self):
        # 3.11. 06:00 aufgebraucht, Reset am 5.11. 10:00: der 3. (18 h) und der 4. (24 h) sind Pausentage, der 5. (10 h) nicht
        reihe = tp.verlauf([(z.strftime("%Y-%m-%dT%H:%M:%SZ"), w) for z, w in
                            linie(t(1), t(3, 5, 30), 20, 90) + linie(t(3, 6), t(5, 9, 30), 100, 100) + linie(t(5, 10), t(6), 2, 10)])
        self.assertEqual(tp.pausen(reihe, t(6)), [(t(3, 6), t(5, 10))])
        self.assertEqual(tp.pausentage(reihe, t(6)), {"2026-11-03", "2026-11-04"})
        offen = tp.verlauf([(z.strftime("%Y-%m-%dT%H:%M:%SZ"), w) for z, w in linie(t(1), t(3, 5, 30), 20, 90) + [(t(3, 6), 100.0)]])
        self.assertEqual(tp.pausen(offen, t(4, 12)), [(t(3, 6), t(4, 12))])                      # noch kein Reset: bis jetzt
        self.assertEqual(tp.pausentage(offen, t(4, 12)), {"2026-11-03", "2026-11-04"})
        self.assertEqual(tp.pausentage(tp.verlauf([("2026-11-01T00:00:00Z", 50.0)]), t(6)), set())

    def test_pausentage_zaehlen_nicht_in_den_durchsatz(self):
        ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(ordner.cleanup)
        con = db.anlegen(os.path.join(ordner.name, "t.db"))
        self.addCleanup(con.close)
        with db.schreiben(con):
            pid = db.einfuegen(con, "projekt", name="P", angelegt_utc=db.jetzt())
            for tag in (10, 9, 8, 7):                                                            # je Tag ein Schritt fertig
                db.einfuegen(con, "aufgabe", projekt_id=pid, titel=f"s{tag}", agent="CC1", angelegt_von="TL", status="fertig", beleg="abc1234",
                             angelegt_utc="2026-11-01T00:00:00Z", fertig_utc=f"2026-11-{tag:02d}T12:00:00Z")
        heute = datetime.date(2026, 11, 10)
        alle = planung.durchsatz(con, pid, None, tage=6, heute=heute)
        self.assertEqual(alle, [1, 1, 1, 1, 0, 0])
        self.assertEqual(planung.durchsatz(con, pid, None, tage=6, heute=heute, ohne={"2026-11-06", "2026-11-05"}), [1, 1, 1, 1])   # ohne die Pausentage
        self.assertEqual(planung.durchsatz(con, pid, None, tage=2, heute=heute, ohne={"2026-11-10", "2026-11-09"}), [1, 1])        # kein Tag übrig: alle gelten
        self.assertEqual(tp.pausentage_aus(con), set())                                          # ohne Messung: nichts, kein Fehler


class InDerPlanung(unittest.TestCase):
    def test_prognose_bleibt_und_bekommt_die_pause_als_eigenes_stueck(self):
        ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(ordner.cleanup)
        con = db.anlegen(os.path.join(ordner.name, "t.db"))
        self.addCleanup(con.close)
        with db.schreiben(con):
            pid = db.einfuegen(con, "projekt", name="P", angelegt_utc=db.jetzt())
        kern.agent_neu(con, pid, "TL", rolle="lead")
        kern.agent_neu(con, pid, "CC1")
        ohne = workbench.daten_planung(con, pid)
        self.assertIsNone(ohne["token"])                                                         # ohne Messung: nichts, kein Fehler
        self.assertIsNone(workbench.daten_start(con, pid)["token"])
        bid = plan_mit_verbrauch(con, pid)
        d = workbench.daten_planung(con, pid)
        self.assertEqual(round(d["token"]["wert"]), 88)
        self.assertGreater(d["token"]["pause_tage"], 2)
        self.assertRegex(d["token"]["reset_utc"], r"^20\d\d-\d\d-\d\dT\d\d:\d\d:\d\dZ$")          # Zeiten als Text
        p = next(b for b in d["boegen"] if b["id"] == bid)["prognose"]
        self.assertGreater(p["pause_tage"], 0)
        self.assertEqual(p["p50_mit"], (datetime.date.fromisoformat(p["p50"]) + datetime.timedelta(days=p["pause_tage"])).isoformat())
        self.assertEqual(p["p50"], planung.prognose(con, pid, laeufe=600)["boegen"][bid]["p50"])   # das Datum selbst ist unverändert
        self.assertEqual(round(workbench.daten_start(con, pid)["token"]["wert"]), 88)             # Leitstand: dieselbe Lage
        # die Ampel rechnet die Pause ein: ein Termin, der ohne Pause sicher hält, steht mit Pause nicht mehr grün
        self.assertIsNone(p["ampel"])                                                            # ohne Zieldatum keine Ampel
        self.assertGreater(p["p85_mit"], p["p85"])
        with db.schreiben(con):
            con.execute("UPDATE bogen SET zieldatum = ? WHERE id = ?", (p["p85"], bid))
        q = planung.prognose(con, pid, laeufe=600)["boegen"][bid]
        self.assertEqual((q["p85"], q["ampel_ohne_pause"]), (p["p85"], "gruen"))
        self.assertIn(q["ampel"], ("gelb", "rot"))
        self.assertEqual(q["ampel"], "gelb" if q["p50_mit"] <= p["p85"] else "rot")
        self.assertEqual(planung.status(con, pid)["termin"], q["ampel"])                          # Status und Plan-Check sehen dieselbe Ampel
        with db.schreiben(con):
            con.execute("UPDATE bogen SET zieldatum = ? WHERE id = ?", (q["p85_mit"], bid))
        r = planung.prognose(con, pid, laeufe=600)["boegen"][bid]
        self.assertEqual((r["ampel"], r.get("ampel_ohne_pause")), ("gruen", None))               # hält auch mit Pause: grün, kein Zusatz
        fest = planung.prognose(con, pid, laeufe=600, heute=datetime.date.today())["boegen"][bid]
        self.assertNotIn("p85_mit", fest)                                                        # gedachtes Heute: ohne Pause


if __name__ == "__main__":
    unittest.main()
