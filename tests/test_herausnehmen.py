"""A2101: Was passiert, wenn ein Agent herausgenommen wird – die Sicht darauf, nur lesend: das laufende Paket läuft zu Ende
oder kommt mit Übergabe-Notiz zurück, die wartenden gehen in ihrer Reihenfolge in den Pool, der Rest bleibt unberührt."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import os
import tempfile
import unittest
from unittest import mock

from amw import arbeitsliste, db, herausnehmen, kern, wissen


class Herausnehmen(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db")})
        u.start()
        self.addCleanup(u.stop)
        for k in ("AMW_AGENT", "AMW_PROJEKT"):
            os.environ.pop(k, None)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        self.pid = self.projekt("Spiel")
        kern.agent_neu(self.con, self.pid, "TL", rolle="lead")
        kern.agent_neu(self.con, self.pid, "CC1")
        kern.agent_neu(self.con, self.pid, "CC2")
        self.laeuft = self.neu("SSO bauen")
        self.a = self.neu("Abmelden")
        self.b = self.neu("Logo")
        self.c = self.neu("Figuren")
        kern.aufgabe_status(self.con, self.pid, "CC1", self.laeuft, "laeuft")
        self.fertig = self.neu("Login-Seite", status="fertig")
        self.verworfen = self.neu("Altes Login", status="verworfen")
        self.geparkt = self.neu("Später")
        wissen.einstufen(self.con, self.pid, "TL", self.geparkt, "geparkt")
        self.fremd = self.neu("Gehört CC2", agent="CC2")

    def projekt(self, name):
        with db.schreiben(self.con):
            return db.einfuegen(self.con, "projekt", name=name, angelegt_utc=db.jetzt())

    def neu(self, titel, agent="CC1", pid=None, **werte):
        aid = kern.aufgabe_neu(self.con, pid or self.pid, "TL", titel, agent=agent)
        if werte.get("status") in ("fertig", "verworfen"):        # die Datenbank verlangt dann einen Beleg
            werte["beleg"] = "abc123"
        self.setzen("aufgabe", aid, **werte)
        return aid

    def setzen(self, tabelle, nr, **werte):
        if werte:
            with db.schreiben(self.con):
                self.con.execute(f"UPDATE {tabelle} SET {', '.join(k + ' = ?' for k in werte)} WHERE id = ?", (*werte.values(), nr))

    def agent(self, kennung, **werte):
        self.setzen("agent", kern.agent_zeile(self.con, self.pid, kennung)["id"], **werte)

    def folgen(self, agent: object = "CC1", laufendes: object = "zu_ende", pid=None):      # object: auch falsche Werte
        return herausnehmen.folgen(self.con, pid or self.pid, agent, laufendes)

    def ids(self, aus):
        return [x["id"] for x in aus["wartend"]]

    # --- laufend und wartend ---------------------------------------------------------------------

    def test_laufendes_laeuft_zu_ende(self):
        aus = self.folgen()
        self.assertEqual(set(aus), {"laufend", "wartend", "unberuehrt", "hinweise"})
        self.assertEqual((aus["laufend"]["id"], aus["laufend"]["titel"]), (self.laeuft, "SSO bauen"))
        self.assertEqual(aus["laufend"]["folge"], "zu_ende")
        self.assertIn("läuft zu Ende", aus["laufend"]["text"])
        self.assertIn(f"A{self.laeuft}", aus["laufend"]["text"])
        self.assertEqual(sorted(self.ids(aus)), sorted([self.a, self.b, self.c]))
        self.assertEqual(aus["unberuehrt"], 3)
        self.assertEqual(aus["hinweise"], [])

    def test_laufendes_kommt_zurueck(self):
        aus = self.folgen(laufendes="zurueck")
        self.assertEqual((aus["laufend"]["id"], aus["laufend"]["folge"]), (self.laeuft, "zurueck"))
        self.assertIn("Übergabe-Notiz", aus["laufend"]["text"])
        self.assertNotIn(self.laeuft, self.ids(aus))          # das laufende steht nur unter laufend
        self.assertEqual(sorted(self.ids(aus)), sorted([self.a, self.b, self.c]))

    def test_wartende_in_der_reihenfolge_der_liste(self):
        arbeitsliste.ordnen(self.con, self.pid, "TL", "CC1", [self.laeuft, self.c, self.a, self.b], grund="Vorführung")
        aus = self.folgen()
        self.assertEqual(self.ids(aus), [self.c, self.a, self.b])
        self.assertEqual(self.ids(aus), [x["id"] for x in arbeitsliste.liste(self.con, self.pid, "CC1") if x["status"] != "laeuft"])
        self.assertEqual(aus["wartend"][0], {"id": self.c, "titel": "Figuren", "status": "wartet", "gruende": []})

    def test_blockierte_gehen_mit_ihrem_grund_in_den_pool(self):
        kern.aufgabe_status(self.con, self.pid, "CC1", self.b, "blockiert", auf="CC2")
        x = next(x for x in self.folgen()["wartend"] if x["id"] == self.b)
        self.assertEqual((x["status"], x["gruende"]), ("blockiert", ["CC2"]))

    def test_eingang_des_agenten_steht_hinter_seiner_liste(self):
        wissen.einstufen(self.con, self.pid, "TL", self.a, "pool")
        aus = self.folgen()
        self.assertEqual(self.ids(aus)[-1], self.a)
        self.assertEqual(sorted(self.ids(aus)), sorted([self.a, self.b, self.c]))

    def test_zweites_laufendes_wird_genannt_und_geht_nicht_still_in_den_pool(self):
        self.setzen("aufgabe", self.b, status="laeuft")
        aus = self.folgen()
        x = arbeitsliste.laufend(self.con, self.pid, "CC1")
        assert x is not None
        erstes = x["id"]
        zweites = ({self.laeuft, self.b} - {erstes}).pop()
        self.assertEqual(aus["laufend"]["id"], erstes)
        self.assertNotIn(zweites, self.ids(aus))
        self.assertTrue(any(f"A{zweites}" in h for h in aus["hinweise"]), aus["hinweise"])

    def test_jedes_paket_kommt_genau_einmal_vor(self):
        wissen.einstufen(self.con, self.pid, "TL", self.a, "pool")
        self.setzen("aufgabe", self.fertig, einstufung="geparkt")          # fertig und geparkt: zählt einmal
        aus = self.folgen()
        self.assertEqual(aus["unberuehrt"], 3)
        self.assertEqual(1 + len(aus["wartend"]) + aus["unberuehrt"],
                         len(kern.aufgaben(self.con, self.pid, "CC1", alle=True)))

    # --- nichts laufend --------------------------------------------------------------------------

    def test_nichts_laufend(self):
        self.setzen("aufgabe", self.laeuft, status="wartet")
        for wie in herausnehmen.LAUFENDES:
            aus = self.folgen(laufendes=wie)
            self.assertIsNone(aus["laufend"])
            self.assertEqual(sorted(self.ids(aus)), sorted([self.laeuft, self.a, self.b, self.c]))

    def test_agent_ohne_pakete(self):
        kern.agent_neu(self.con, self.pid, "CC3")
        aus = self.folgen("CC3")
        self.assertEqual((aus["laufend"], aus["wartend"], aus["unberuehrt"]), (None, [], 0))

    # --- nur dieses Projekt ----------------------------------------------------------------------

    def test_anderes_projekt_bleibt_unberuehrt(self):
        vorher = self.folgen()
        p2 = self.projekt("Anderes")
        kern.agent_neu(self.con, p2, "CC1")
        dort = self.neu("Dort", pid=p2)
        kern.aufgabe_status(self.con, p2, "CC1", dort, "laeuft")
        wartet = self.neu("Dort wartend", pid=p2)
        self.neu("Dort fertig", pid=p2, status="fertig")
        self.assertEqual(self.folgen(), vorher)
        aus = self.folgen(pid=p2)
        self.assertEqual((aus["laufend"]["id"], self.ids(aus), aus["unberuehrt"]), (dort, [wartet], 1))

    def test_aktive_im_anderen_projekt_zaehlen_nicht(self):
        p2 = self.projekt("Anderes")
        kern.agent_neu(self.con, p2, "CC9")
        for k in ("TL", "CC2"):
            self.agent(k, soll="aus")
        self.assertTrue(any("niemand" in h.lower() for h in self.folgen()["hinweise"]))

    # --- Hinweise --------------------------------------------------------------------------------

    def test_hinweis_wenn_niemand_sonst_aktiv_ist(self):
        self.agent("TL", soll="aus")
        self.agent("CC2", entfernt_utc=db.jetzt())
        self.assertIn("Sonst ist niemand im Projekt aktiv – was in den Pool geht, bleibt dort liegen.", self.folgen()["hinweise"])

    def test_laufende_sitzung_zaehlt_als_aktiv(self):
        self.agent("TL", soll="aus")
        self.agent("CC2", soll="aus")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=kern.agent_zeile(self.con, self.pid, "CC2")["id"], gestartet_utc=db.jetzt())
        self.assertEqual(self.folgen()["hinweise"], [])

    def test_hinweis_wenn_nur_lead_und_co_entwickler_bleiben(self):
        self.agent("CC2", soll="aus")
        kern.agent_neu(self.con, self.pid, "CO")
        self.setzen("projekt", self.pid, einstellungen=json.dumps({"co_entwickler": "CO"}))
        h = self.folgen()["hinweise"]
        self.assertEqual(len(h), 1)
        self.assertIn("TL, CO", h[0])

    def test_hinweis_beim_lead(self):
        self.assertTrue(any("führt das Projekt" in h for h in self.folgen("TL")["hinweise"]))

    def test_hinweis_bei_schon_entferntem(self):
        self.agent("CC1", entfernt_utc=db.jetzt())
        self.assertTrue(any("schon entfernt" in h for h in self.folgen()["hinweise"]))

    # --- Fehler ----------------------------------------------------------------------------------

    def test_unbekannter_agent(self):
        p2 = self.projekt("Anderes")
        kern.agent_neu(self.con, p2, "CC9")
        for k in ("CC9", "Gibtsnicht", "", None, kern.ENTWICKLER):          # CC9 gibt es nur im anderen Projekt
            with self.assertRaises(kern.AmwFehler, msg=repr(k)):
                self.folgen(k)

    def test_falscher_wert(self):
        for wie in ("", None, "sofort", "Zu_Ende", "zurück", ["zu_ende"]):
            with self.assertRaises(kern.AmwFehler, msg=repr(wie)) as f:
                self.folgen(laufendes=wie)
            self.assertIn("zu_ende", str(f.exception))

    def test_fruehere_kennung_gilt(self):
        vorher = self.folgen()
        kern.agent_umbenennen(self.con, self.pid, kern.ENTWICKLER, "CC1", "Bauer1")
        self.assertEqual(self.folgen("Bauer1")["laufend"]["id"], self.laeuft)
        self.assertEqual(self.folgen("CC1")["laufend"]["id"], self.laeuft)
        self.assertEqual(self.ids(self.folgen("CC1")), self.ids(vorher))

    # --- nur lesen -------------------------------------------------------------------------------

    def test_datenbank_aendert_sich_nicht(self):
        vorher, n = list(self.con.iterdump()), self.con.total_changes
        for agent in ("CC1", "CC2", "TL"):
            for wie in herausnehmen.LAUFENDES:
                self.folgen(agent, wie)
        for agent, wie in (("Gibtsnicht", "zu_ende"), ("CC1", "sofort")):
            with self.assertRaises(kern.AmwFehler):
                self.folgen(agent, wie)
        self.assertFalse(self.con.in_transaction)
        self.assertEqual(self.con.total_changes, n)
        self.assertEqual(list(self.con.iterdump()), vorher)


if __name__ == "__main__":
    unittest.main()
