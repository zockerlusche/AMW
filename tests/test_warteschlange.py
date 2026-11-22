"""A1918: Viele Verbindungen auf einmal kommen an, auch wenn der Server sie gerade nicht annimmt. Mit der Standard-Warteschlange
(5) nahm Windows die sechste nicht an; im Browser hieß das „Failed to fetch“ und eine leere Seite (Wissen, Dokumente – der
Rundgang wartete 32 s). Hier nimmt der Server absichtlich nichts an, solange die Verbindungen aufgebaut werden."""
import tests.abschotten  # noqa: F401 – immer als erster Import: Tests nie im echten Zugangs-Ordner
import socket
import unittest

from amw import workbench

GLEICHZEITIG = 30          # mehr als die Seite beim ersten Laden auf einmal braucht


class Warteschlange(unittest.TestCase):
    def test_viele_verbindungen_auf_einmal(self):
        srv = workbench.Server(("127.0.0.1", 0), workbench.baue_handler(0, "x", False))   # gebunden und lauscht, nimmt aber nichts an
        self.addCleanup(srv.server_close)
        port = srv.server_address[1]
        offen, fehl = [], []
        for _ in range(GLEICHZEITIG):
            s = socket.socket()
            s.settimeout(2)
            try:
                s.connect(("127.0.0.1", port))
                offen.append(s)
            except OSError as e:
                fehl.append(e)
                s.close()
        for s in offen:
            s.close()
        self.assertEqual(fehl, [], f"{len(fehl)} von {GLEICHZEITIG} Verbindungen nicht angenommen")


if __name__ == "__main__":
    unittest.main()
