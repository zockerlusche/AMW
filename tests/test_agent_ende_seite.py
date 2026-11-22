"""A1965 (Befund #30514) in der Seite: nach „Speichern & beenden“ zeigt die Kachel nicht mehr „läuft“, und im Menü ist
„Starten / fortsetzen“ wieder wählbar – solange die Sitzung nur abgemeldet ist und ihr Fenster lebt, bleibt es grau."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import os
from unittest import mock

from amw import db, kern, steuerung
from tests.rundgang import Rundgang


class AgentEnde(Rundgang):
    def daten(self):                                                     # TL (Lead) legt schon das Gerüst an
        kern.agent_neu(self.con, self.pid, "CC1")
        ordner = os.path.join(self.ordner.name, "cc1")
        os.makedirs(ordner)
        steuerung.profil_setzen(self.con, self.pid, "Entwickler", "CC1", ordner=ordner)
        aid = kern.agent_zeile(self.con, self.pid, "CC1")["id"]
        with db.schreiben(self.con):
            db.einfuegen(self.con, "sitzung", agent_id=aid, claude_sitzung="s-cc1", gestartet_utc=db.jetzt(), schluessel_datei="x.json",
                         claude_pid=4242, zustand="aktiv")

    # Team als Baum, Menü der Karte CC1 öffnen; Ergebnis: ist „Starten / fortsetzen“ grau?
    MENUE = ("[...document.querySelectorAll('.tm-schalter button')][0].click();"
             " (function los() { const b = [...document.querySelectorAll('.tm-knoten[data-k=CC1] button')].find(x => x.textContent === '⋯');"
             " if (!b) return setTimeout(los, 100); b.click(); })()")
    START = "[...document.querySelectorAll('.menue button')].find(x => x.textContent.startsWith(t('m_start')))"

    def start_grau(self):
        self.oeffnen("start", "document.querySelector('#team')")
        self.tab.js(self.MENUE)
        self.warten(self.START)
        return self.tab.js(self.START + ".disabled")

    def test_nach_dem_beenden_wieder_startbar(self):
        lebend = {4242}
        with mock.patch.object(steuerung, "lebt", side_effect=lambda p: p in lebend):
            kern.abmelden(self.con, self.pid, "CC1")                            # gesichert und abgemeldet, Fenster noch offen
            self.assertTrue(self.start_grau())
            steuerung.ende_anfordern(self.con, self.pid, ["CC1"], jetzt=datetime.datetime.now(datetime.timezone.utc))
            steuerung.ende_pruefen(self.con, beenden_mit=lambda p: lebend.discard(p))
        self.assertEqual(self.con.execute("SELECT zustand FROM sitzung").fetchone()[0], "beendet")
        self.assertFalse(self.start_grau())                                     # Kachel und Menü wie agent liste: beendet
        self.assertIn("läuft nicht", self.tab.js("document.querySelector('.tm-knoten[data-k=CC1]').textContent"))
