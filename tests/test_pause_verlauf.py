"""A2137: Pause an und aus stehen im Verlauf – wer, wann, Grund, Ende in Menschensprache; auch das Aufheben durch die AMW."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import datetime
import os
import tempfile
import unittest
from unittest import mock

from amw import db, kern, pause, projektweg_seite, verlauf_quellen

ARTEN = (pause.AN, pause.AUS)


def iso(t):
    return t.astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def heute_um(stunde, tage=0):
    """Ortszeit heute (oder `tage` später) als UTC-ISO."""
    t = datetime.datetime.now().replace(hour=stunde, minute=0, second=0, microsecond=0) + datetime.timedelta(days=tage)
    return iso(t.astimezone())


class PauseImVerlauf(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        u = mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "amw.db"), "LOCALAPPDATA": os.path.join(self.ordner.name, "lad")})
        u.start()
        self.addCleanup(u.stop)
        self.con = db.anlegen(os.environ["AMW_DB"])
        self.addCleanup(self.con.close)
        self.pid, self.anders = self.projekt("P"), self.projekt("Q")

    def projekt(self, name):
        with db.schreiben(self.con):
            pid = db.einfuegen(self.con, "projekt", name=name, angelegt_utc=db.jetzt())
        kern.agent_neu(self.con, pid, "TL", rolle="lead")
        kern.agent_neu(self.con, pid, "CC1")
        return pid

    def verlauf(self, pid=None):
        return [e for e in verlauf_quellen.gesamt(self.con, pid or self.pid, [], lambda e: "umsetzung") if e["art"] in ARTEN]

    def kurz(self, pid=None):
        return [(e["art"], e["rolle"], e["von"], e["text"]) for e in self.verlauf(pid)]

    def test_an_und_aus_in_der_reihenfolge(self):
        pause.an(self.con, self.pid, "TL", bis=heute_um(18), grund="Update")
        pause.aus(self.con, self.pid, kern.ENTWICKLER)
        pause.an(self.con, self.pid, kern.ENTWICKLER, grund="Mittag")
        self.assertEqual(self.kurz(), [("pause_an", "agent", "TL", "Pause für alles bis 18:00 – Update"),
                                       ("pause_aus", "mensch", kern.ENTWICKLER, "Pause aufgehoben"),
                                       ("pause_an", "mensch", kern.ENTWICKLER, "Pause für alles – Mittag")])
        zeiten = [r[0] for r in self.con.execute("SELECT zeit_utc FROM plan_ereignis WHERE projekt_id = ? AND art IN (?, ?) ORDER BY id",
                                                  (self.pid, *ARTEN))]
        self.assertEqual([(e["zeit"], e["schritt"]) for e in self.verlauf()], [(z, "umsetzung") for z in zeiten])

    def test_ohne_grund_und_ende_an_einem_anderen_tag(self):
        bis = heute_um(7, tage=2)
        pause.an(self.con, self.pid, "TL", bis=bis)
        tag = db.utc_lesen(bis).astimezone().strftime("%d.%m.")
        self.assertEqual([e["text"] for e in self.verlauf()], [f"Pause für alles bis {tag} 07:00"])

    def test_ende_hebt_die_amw_auf(self):
        vorbei = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(minutes=1)
        pause.an(self.con, self.pid, "TL", bis=iso(vorbei), grund="Umzug")
        self.assertEqual(pause.runde(self.con), [(self.pid, "Pause vorbei")])
        self.assertEqual(self.kurz()[1:], [("pause_aus", "amw", "AMW", "Pause aufgehoben – Ende erreicht")])
        self.assertEqual(self.kurz()[0][0], "pause_an")

    def test_nur_im_eigenen_projekt(self):
        pause.an(self.con, self.anders, "TL", grund="Fremd")
        pause.aus(self.con, self.anders, "TL")
        self.assertEqual(self.verlauf(), [])
        self.assertEqual([e["art"] for e in self.verlauf(self.anders)], ["pause_an", "pause_aus"])

    def test_auf_der_seite(self):
        pause.an(self.con, self.pid, "TL", grund="Update")
        self.assertIn(("Pause für alles – Update", "umsetzung"),
                      [(e["zeile"], e["schritt"]) for e in projektweg_seite.verlauf_gesamt(self.con, self.pid)])

    def test_ohne_pause_wie_heute(self):
        self.assertEqual(verlauf_quellen.gesamt(self.con, self.pid, [], lambda e: "umsetzung"), [])


if __name__ == "__main__":
    unittest.main()
