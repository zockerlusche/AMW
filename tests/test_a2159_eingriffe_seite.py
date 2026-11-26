"""A2159: die vorhandenen Eingriffe als Knöpfe – über den echten Weg (Klick → Rückfrage → Aktion → neu gerechnet und im Verlauf).
Paket früher/später mit gesperrter Stelle und Grund, Prüfpunkt dahinter und weg (Fenster der Aufgabe), Agent herausnehmen und wieder
freigeben (Fenster des Agenten), Pause für alles mit Ende (Projektweg › Planung). Dazu die Daten (workbench.eingriffe_paket, heraus)
und je Ort ein Rundgang in allen Größen und Themen."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json

from amw import db, herausnehmen, kern, pause, planung, verlauf_quellen, workbench, zwischenpruefung
from tests.rundgang import Rundgang


class Daten(Rundgang):
    def daten(self):
        for k in ("CC1", "CC2"):
            kern.agent_neu(self.con, self.pid, k)
        self.m = planung.bogen_neu(self.con, self.pid, "TL", "Anmelden", abnahme="Vorführung")
        self.a = planung.schritt_setzen(self.con, self.pid, "TL", titel="Abmelden oben rechts", bogen_id=self.m, agent="CC1")
        self.b = planung.schritt_setzen(self.con, self.pid, "TL", titel="Passwort vergessen", bogen_id=self.m, agent="CC1", nach=[self.a])
        self.c = planung.schritt_setzen(self.con, self.pid, "TL", titel="Anmeldung am Handy", bogen_id=self.m, agent="CC2", nach=[self.a])
        planung.bogen_status(self.con, self.pid, "TL", self.m, "aktiv")
        # b und c brauchen a: das Paket an zweiter Stelle ist „früher“ gesperrt (braucht a), das an dritter darf früher
        s = {x: workbench.daten_aufgabe(self.con, self.pid, x)["eingriffe"]["schieben"]["frueher"] for x in (self.b, self.c)}
        self.zweit = next(x for x in s if not s[x]["geht"])
        self.dritt = next(x for x in s if s[x]["geht"])
        self.titel = {self.b: "Passwort vergessen", self.c: "Anmeldung am Handy"}

    def dialog(self, js, bereit):
        self.groesse("pc")
        self.oeffnen("planung", "typeof aufgabeDialog === 'function'")
        self.tab.js(js)
        self.warten(bereit)

    def ereignisse(self, art):
        return [json.loads(r[0] or "{}") for r in self.con.execute("SELECT text FROM plan_ereignis WHERE art = ? ORDER BY id", (art,))]


class Paket(Daten):
    def test_daten_zum_paket(self):
        e = workbench.daten_aufgabe(self.con, self.pid, self.zweit)["eingriffe"]
        self.assertFalse(e["schieben"]["frueher"]["geht"])
        self.assertEqual((e["schieben"]["frueher"]["art"], e["schieben"]["frueher"]["x"]), ("braucht", "Abmelden oben rechts"))
        self.assertEqual((e["pruefpunkt"], e["ist_pruefpunkt"]), (None, False))
        self.assertEqual(sorted(workbench.daten_aufgabe(self.con, self.pid, self.a)["eingriffe"]["pruefpunkt_wartet"]), sorted([self.b, self.c]))
        self.assertEqual(e["pruefpunkt_wartet"], [])                                           # hinter dem zweiten wartet nichts
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'fertig', beleg = 'x' WHERE id = ?", (self.c,))
        self.assertIsNone(workbench.daten_aufgabe(self.con, self.pid, self.c)["eingriffe"])

    def test_gesperrte_stelle_mit_grund(self):
        self.dialog(f"aufgabeDialog({self.zweit})", "document.querySelector('.dialog [data-eg=frueher]')")
        self.assertTrue(self.tab.js("document.querySelector('.dialog [data-eg=frueher]').disabled"))
        self.assertIn("Früher: braucht „Abmelden oben rechts“", self.tab.js("document.querySelector('.dialog .eg-sperre').textContent"))

    def test_frueher_schieben_rechnet_neu_und_steht_im_verlauf(self):
        self.dialog(f"aufgabeDialog({self.dritt})", "document.querySelector('.dialog [data-eg=frueher]:not([disabled])')")
        self.tippen(".dialog [data-eg=frueher]")
        self.warten("document.querySelector('.dialog [data-eg=spaeter]') && document.querySelector('.toast')?.textContent.includes('steht jetzt vor')")
        paar, = self.ereignisse("paket_schieben")
        self.assertEqual((paar.get("vor"), paar.get("nach")), (self.dritt, self.zweit))
        von = self.con.execute("SELECT von FROM plan_ereignis WHERE art = 'paket_schieben'").fetchone()[0]
        self.assertEqual(von, kern.ENTWICKLER)
        self.assertTrue(workbench.daten_aufgabe(self.con, self.pid, self.dritt)["eingriffe"]["schieben"]["spaeter"]["geht"])
        texte = [x.get("text") or "" for x in verlauf_quellen.gesamt(self.con, self.pid, [], lambda e: None)]
        self.assertIn(f"„{self.titel[self.dritt]}“ früher, vor „{self.titel[self.zweit]}“", " | ".join(texte))   # im Verlauf mit Person

    def test_pruefpunkt_dahinter_und_wieder_weg(self):
        self.dialog(f"aufgabeDialog({self.a})", "document.querySelector('.dialog [data-eg=pruefpunkt]')")
        self.tippen(".dialog [data-eg=pruefpunkt]")
        frage = self.rueckfrage(True, "Abmelden am Handy")
        self.assertIn("Prüfpunkt hinter „Abmelden oben rechts“", frage)
        self.warten("document.querySelector('.dialog [data-eg=pruefpunkt-weg]')")
        p, = zwischenpruefung.offene(self.con, self.pid)
        self.assertEqual(p["nach"], self.a)
        self.tippen(".dialog [data-eg=pruefpunkt-weg]")
        self.rueckfrage(True, "Probe vorbei")
        self.warten("document.querySelector('.dialog [data-eg=pruefpunkt]')")
        self.assertEqual(zwischenpruefung.offene(self.con, self.pid), [])

    def test_pruefpunkt_gesperrt_wenn_dahinter_nichts_wartet(self):
        self.dialog(f"aufgabeDialog({self.dritt})", "document.querySelector('.dialog [data-eg=pruefpunkt]')")
        self.assertTrue(self.tab.js("document.querySelector('.dialog [data-eg=pruefpunkt]').disabled"))
        self.assertIn("Prüfpunkt dahinter: dahinter wartet kein Paket", self.tab.js("document.querySelector('.dialog .eg-sperre').textContent"))

    def test_abbrechen_tut_nichts(self):
        self.dialog(f"aufgabeDialog({self.a})", "document.querySelector('.dialog [data-eg=pruefpunkt]')")
        self.tippen(".dialog [data-eg=pruefpunkt]")
        self.rueckfrage(False)
        self.assertEqual(zwischenpruefung.offene(self.con, self.pid), [])

    def test_rundgang_fenster_der_aufgabe(self):
        self.ueberall("planung", "eingriffe-paket", bereit="typeof aufgabeDialog === 'function'", tun=f"aufgabeDialog({self.zweit})",
                      danach="document.querySelector('.dialog .eg-block')")


class Agent(Daten):
    def test_herausnehmen_mit_vorschau_und_wieder_frei(self):
        self.dialog("agentDialog('CC1')", "document.querySelector('.dialog [data-eg=herausnehmen]')")
        self.tippen(".dialog [data-eg=herausnehmen]")
        self.warten("document.querySelector('.dialog [data-eg=herausnehmen-ja]') && document.querySelector('.eg-folgen .au-zeile')")
        text = self.tab.js("[...document.querySelectorAll('.dialog')].pop().textContent")
        self.assertIn("CC1 herausnehmen?", text)
        self.assertIn("2 wartende Pakete gehen an die anderen", text)
        self.assertTrue(self.tab.js("document.querySelector('.eg-wahl').hidden"))              # nichts läuft: keine Wahl
        self.tab.js("(() => { const f = [...document.querySelectorAll('.dialog')].pop().querySelector('.feld input'); f.value = 'Probe'; })()")
        self.tippen(".dialog [data-eg=herausnehmen-ja]")
        self.warten("document.querySelector('.dialog [data-eg=freigeben]')")
        self.assertEqual(herausnehmen.stand(self.con, self.pid)["CC1"]["grund"], "Probe")
        self.tippen(".dialog [data-eg=freigeben]")
        self.rueckfrage(True, "Probe vorbei")
        self.warten("document.querySelector('.dialog [data-eg=herausnehmen]')")
        self.assertNotIn("CC1", herausnehmen.stand(self.con, self.pid))

    def test_laufendes_paket_marcel_waehlt_zurueck(self):
        with db.schreiben(self.con):
            self.con.execute("UPDATE aufgabe SET status = 'laeuft', begonnen_utc = ? WHERE id = ?", (db.jetzt(), self.a))
        self.dialog("agentDialog('CC1')", "document.querySelector('.dialog [data-eg=herausnehmen]')")
        self.tippen(".dialog [data-eg=herausnehmen]")
        self.warten("document.querySelector('.eg-wahl') && !document.querySelector('.eg-wahl').hidden")
        self.assertIn("läuft zu Ende", self.tab.js("document.querySelector('.eg-folgen').textContent"))
        self.tab.js("document.querySelector('.eg-wahl input[value=zurueck]').click()")
        self.warten("document.querySelector('.eg-folgen').textContent.includes('Übergabe-Notiz')")
        self.tab.js("(() => { const f = [...document.querySelectorAll('.dialog')].pop().querySelector('.feld input'); f.value = 'Probe'; })()")
        self.tippen(".dialog [data-eg=herausnehmen-ja]")
        self.warten("document.querySelector('.dialog [data-eg=freigeben]')")
        self.assertEqual(herausnehmen.stand(self.con, self.pid)["CC1"]["laufendes"], "zurueck")

    def test_rundgang_fenster_des_agenten(self):
        herausnehmen.nehmen(self.con, self.pid, kern.ENTWICKLER, "CC2", "zu_ende", "Probe")
        self.ueberall("planung", "eingriffe-agent", bereit="typeof agentDialog === 'function'", tun="agentDialog('CC2')",
                      danach="document.querySelector('.dialog [data-eg=freigeben]')")


class Pause(Daten):
    def test_pause_mit_ende_und_wieder_aus(self):
        self.groesse("pc")
        self.oeffnen("planung", "document.querySelector('[data-eg=pause]')")
        self.tippen("[data-eg=pause]")
        self.warten("document.querySelector('.dialog [data-eg=pause-an]')")
        self.tab.js("(() => { const f = document.querySelectorAll('.dialog input'); f[0].value = 'Vorführung'; f[1].value = '90min'; })()")
        self.tippen(".dialog [data-eg=pause-an]")
        self.warten("document.querySelector('[data-eg=pause-aus]') && !document.querySelector('.dialog')")
        z = pause.zustand(self.con, self.pid)
        self.assertTrue(z["an"])
        self.assertTrue(z["bis"])
        self.assertIn("Vorführung", z["grund"])
        self.tippen("[data-eg=pause-aus]")
        self.warten("document.querySelector('[data-eg=pause]')")
        self.assertFalse(pause.zustand(self.con, self.pid)["an"])

    def test_ohne_grund_geht_es_nicht(self):
        self.groesse("pc")
        self.oeffnen("planung", "document.querySelector('[data-eg=pause]')")
        self.tippen("[data-eg=pause]")
        self.warten("document.querySelector('.dialog [data-eg=pause-an]')")
        self.tippen(".dialog [data-eg=pause-an]")
        self.warten("document.querySelector('.toast')?.textContent.includes('Grund')")
        self.assertFalse(pause.zustand(self.con, self.pid)["an"])

    def test_rundgang_pause(self):
        self.ueberall("planung", "eingriffe-pause", bereit="document.querySelector('[data-eg=pause]')", tun="pauseDialog()",
                      danach="document.querySelector('.dialog [data-eg=pause-an]')")
