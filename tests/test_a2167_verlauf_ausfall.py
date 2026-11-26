"""A2167 (TH157 F5, W2487): Ausfall, Stille und Rückgabe in den Pool stehen im Verlauf – je Fall ein ruhiger Satz; nur die Rückgabe ist
hervorgehoben. Über verlauf_quellen.gesamt (projektweg_seite.verlauf_gesamt) mit festen Zeiten."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import json
import unittest

from amw import db, kern, verlauf_quellen
from tests.rundgang import Rundgang
from tests.test_a2077_verlauf import Grund, z


def ortszeit(iso):
    return db.utc_lesen(iso).astimezone().strftime("%H:%M")


class Ausfall(Grund):
    def nachricht(self, an, zeit):
        nid, _ = kern.posten(self.con, self.pid, "TL", an, "auftrag", "Bitte melden")
        with db.schreiben(self.con):
            self.con.execute("UPDATE nachricht SET zeit_utc = ? WHERE id = ?", (zeit, nid))
            self.con.execute("UPDATE empfang SET geweckt_utc = ? WHERE nachricht_id = ?", (zeit, nid))   # wie der Dienst beim Weckruf
        return nid

    def test_rueckgabe_still_und_ausfall_mit_notiz(self):
        a, b = self.paket("Spielstand speichern"), self.paket("Spielstand laden", agent="CC2")
        self.ereignis("ausfall", z(10), aufgabe=a, text=f"still:CC1:7:{a}")
        self.ereignis("uebergabe", z(10), aufgabe=a, agent="CC1", notiz="letzter Commit abc1234, Tests rot")
        self.ereignis("ausfall", z(11), aufgabe=b, text=f"CC2:8:{b}")
        self.ereignis("uebergabe", z(11), aufgabe=b, agent="CC2", notiz="")
        v = {e["zeile"]: e for e in self.v("umsetzung")}
        still = next(e for k, e in v.items() if "Spielstand speichern" in k)
        self.assertEqual(still["zeile"], f"A{a} „Spielstand speichern“ ging von CC1 zurück in den Pool – still (Übergabe-Notiz)")
        self.assertEqual((still["art"], still["lang"]), ("rueckgabe", "Übergabe-Notiz: letzter Commit abc1234, Tests rot"))
        aus = next(e for k, e in v.items() if "Spielstand laden" in k)
        self.assertEqual(aus["zeile"], f"A{b} „Spielstand laden“ ging von CC2 zurück in den Pool – Sitzung beendet")
        self.assertEqual(aus["art"], "rueckgabe")

    def test_vorschlag_rueckfrage_und_nachgeweckt(self):
        a = self.paket("Kasse öffnen")
        self.ereignis("ausfall_vorschlag", z(9), aufgabe=a, text=f"still:CC1:7:{a}")
        self.ereignis("ruhig", z(8), aufgabe=a, text=f"ruhig:CC1:{a}:{z(7, 40)}")
        n1, n2 = self.nachricht("CC2", z(6)), self.nachricht("CC2", z(6, 1))
        self.ereignis("nachgeweckt", z(7), aufgabe=None, text=str(n1))
        self.ereignis("nachgeweckt", z(7), aufgabe=None, text=str(n2))
        zeilen = self.zeilen()
        self.assertIn(f"Vorschlag an den Lead: A{a} „Kasse öffnen“ von CC1 zurück in den Pool – still", zeilen)
        self.assertIn(f"Rückfrage an CC1: kommst du voran mit A{a} „Kasse öffnen“? (ruhig seit {ortszeit(z(7, 40))})", zeilen)
        self.assertIn("CC2 nachgeweckt (2 Nachrichten)", zeilen)
        arten = {e["art"] for e in self.v("umsetzung")}
        self.assertTrue({"ausfall_vorschlag", "ruhig", "nachgeweckt"} <= arten)
        self.assertNotIn("rueckgabe", arten)                                     # nur die Rückgabe ist hervorgehoben

    def test_uebergabe_beim_herausnehmen_kommt_nicht_doppelt(self):
        """Die Übergabe-Notiz gehört zur Rückgabe; eine Übergabe ohne Ausfall (Herausnehmen, A2095) bleibt dessen eigener Eintrag."""
        a = self.paket("Allein")
        self.ereignis("uebergabe", z(12), von="TL", aufgabe=a, agent="CC1", notiz="x")
        self.assertFalse([x for x in self.zeilen() if "zurück in den Pool" in x])

    def test_abfragen_gleich_viele(self):
        """Drei Abfragen für alle Fälle zusammen, gleich viele bei wenigen und vielen Ereignissen."""
        def zaehlen():
            n = []
            self.con.set_trace_callback(n.append)
            try:
                verlauf_quellen._ausfaelle(self.con, self.pid)
            finally:
                self.con.set_trace_callback(None)
            return len(n)
        a = self.paket("Eins")
        self.ereignis("ausfall", z(10), aufgabe=a, text=f"CC1:1:{a}")
        self.ereignis("nachgeweckt", z(10), text=str(self.nachricht("CC2", z(9))))
        wenig = zaehlen()
        for i in range(30):
            b = self.paket(f"Viele {i}")
            self.ereignis("ausfall", z(11, i), aufgabe=b, text=f"still:CC1:{i}:{b}")
            self.ereignis("uebergabe", z(11, i), aufgabe=b, agent="CC1", notiz=json.dumps(i))
            self.ereignis("nachgeweckt", z(11, i), text=str(self.nachricht("CC2", z(9, i))))
        self.assertEqual(zaehlen(), wenig)



UMSETZUNG = "zustand.pwSicht = 3; zustand.pwOffen = true; void zeige('projektweg', true)"


class Seite(Rundgang):
    """Im Verlauf der Umsetzung: die Rückgabe hervorgehoben (Notiz auf Klick), die Rückfrage ruhig."""
    def daten(self):
        from amw import planung
        kern.agent_neu(self.con, self.pid, "CC1")
        m = planung.bogen_neu(self.con, self.pid, "TL", "Speichern", ziel="Z", abnahme="Vorführung")
        planung.bogen_status(self.con, self.pid, "TL", m, "aktiv")
        a = planung.schritt_setzen(self.con, self.pid, "TL", titel="Spielstand speichern", bogen_id=m)
        b = planung.schritt_setzen(self.con, self.pid, "TL", titel="Spielstand laden", bogen_id=m, agent="CC1")
        with db.schreiben(self.con):
            for art, aid, text in (("ruhig", b, f"ruhig:CC1:{b}:{db.jetzt()}"), ("ausfall", a, f"still:CC1:7:{a}"),
                                   ("uebergabe", a, json.dumps({"aufgabe": a, "agent": "CC1", "notiz": "letzter Commit abc1234"}))):
                db.einfuegen(self.con, "plan_ereignis", projekt_id=self.pid, zeit_utc=db.jetzt(), von="AMW", art=art, aufgabe_id=aid, text=text)

    def test_rueckgabe_hervorgehoben(self):
        self.oeffnen("projektweg", "typeof zeige === 'function'")
        self.tab.js(UMSETZUNG)
        self.warten("document.querySelector('.pjw-eintrag.rueckgabe')")
        self.assertEqual(self.tab.js("document.querySelectorAll('aside.pjw-verlauf .pjw-eintrag.rueckgabe').length"), 1)
        self.assertIn("Übergabe-Notiz: letzter Commit abc1234", self.tab.js("document.querySelector('aside.pjw-verlauf .pjw-eintrag.rueckgabe').textContent"))
        self.assertTrue(self.tab.js("[...document.querySelectorAll('aside.pjw-verlauf .pjw-eintrag:not(.rueckgabe)')].some(e => e.innerText.includes('kommst du voran'))"))

    def test_bilder(self):
        self.ueberall("projektweg", "a2167-verlauf", bereit="typeof zeige === 'function'", tun=UMSETZUNG,
                      danach="document.querySelector('.pjw-eintrag.rueckgabe')")


if __name__ == "__main__":
    unittest.main()
