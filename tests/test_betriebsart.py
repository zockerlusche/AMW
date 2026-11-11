"""Betriebsart: eine Stelle entscheidet über jeden Weg nach außen. In „Nur dieser PC“ kommt keine Verbindung über den
eigenen Rechner hinaus zustande – nicht zum Online-Speicher, nicht zu einem Benachrichtigungs-Dienst, nicht zur Prüfung
der Online-Seite; es wird nicht einmal ein Name aufgelöst."""
import json
import os
import socket
import tempfile
import unittest
import urllib.request
from unittest import mock

from amw import abgleich, betriebsart, einstellungen, push, verbindung


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory(ignore_cleanup_errors=True)
        self.addCleanup(self.ordner.cleanup)
        umgebung = mock.patch.dict(os.environ, {"LOCALAPPDATA": self.ordner.name})
        umgebung.start()
        self.addCleanup(umgebung.stop)
        betriebsart._namen.clear()

    def kein_netz(self):
        """Jeder Verbindungsaufbau und jede Namensauflösung lässt den Test scheitern."""
        def verboten(*a, **k):
            raise AssertionError(f"Verbindung nach außen versucht: {a[:1]}")
        for ziel, name in ((urllib.request, "urlopen"), (socket, "getaddrinfo"), (socket, "create_connection")):
            p = mock.patch.object(ziel, name, side_effect=verboten)
            p.start()
            self.addCleanup(p.stop)


class Einordnung(Grund):
    def test_adresse_fuehrt_zu_pc_firmennetz_oder_internet(self):
        for adresse, stufe in (("http://127.0.0.1:8780", "pc"), ("localhost:11434", "pc"), ("https://[::1]/x", "pc"),
                               ("https://192.168.1.5/x", "firma"), ("10.0.0.7", "firma"), ("ntfy.firma.lan", "firma"), ("speicher", "firma"),
                               ("https://8.8.8.8", "internet"), ("https://dienst.example.com", "internet"), ("", "internet"), ("::::", "internet")):
            self.assertEqual(betriebsart.netz(adresse, None), stufe, adresse)

    def test_name_mit_punkt_gilt_nur_als_firmennetz_wenn_er_nur_dorthin_zeigt(self):
        self.assertEqual(betriebsart.netz("https://intern.example.com", lambda n: ["10.1.2.3"]), "firma")
        self.assertEqual(betriebsart.netz("https://halb.example.com", lambda n: ["10.1.2.3", "93.184.216.34"]), "internet")
        self.assertEqual(betriebsart.netz("https://weg.example.com", lambda n: []), "internet")          # nicht auflösbar: im Zweifel Internet

    def test_was_die_betriebsart_zulaesst(self):
        erlaubt = lambda a: [betriebsart.erlaubt(a, art) for art in betriebsart.ARTEN]
        self.assertEqual(erlaubt("http://127.0.0.1:8780"), [True, True, True])
        self.assertEqual(erlaubt("https://192.168.1.5"), [False, True, True])
        with mock.patch.object(betriebsart, "_aufloesen", return_value=["93.184.216.34"]):
            self.assertEqual(erlaubt("https://dienst.example.com"), [False, False, True])


class Vorgabe(Grund):
    def test_nichts_gewaehlt_gilt_was_bisher_lief(self):
        self.assertEqual((betriebsart.gewaehlt(), betriebsart.aktuell()), ("", "pc"))                    # frische Installation
        os.makedirs(os.path.dirname(abgleich.zugang_pfad()), exist_ok=True)
        with open(abgleich.zugang_pfad(), "w", encoding="utf-8") as f:
            json.dump({"url": "libsql://x.example.io", "token": "t", "abgleich": False}, f)
        self.assertEqual(betriebsart.aktuell(), "pc")                                                    # eingetragen, aber aus
        with open(abgleich.zugang_pfad(), "w", encoding="utf-8") as f:
            json.dump({"url": "libsql://x.example.io", "token": "t", "abgleich": True}, f)
        self.assertEqual(betriebsart.aktuell(), "cloud")
        einstellungen.speichern({"betriebsart": "pc"})                                                   # die Wahl geht vor
        self.assertEqual(betriebsart.aktuell(), "pc")
        with self.assertRaises(ValueError):
            einstellungen.speichern({"betriebsart": "mond"})

    def test_eingeschaltete_benachrichtigungen_gelten_als_cloud(self):
        with mock.patch.object(push, "laden", return_value={"an": True}):
            self.assertEqual(betriebsart.aktuell(), "cloud")


class Sperre(Grund):
    def test_nur_dieser_pc_baut_keine_verbindung_nach_aussen_auf(self):
        einstellungen.speichern({"betriebsart": "pc"})
        self.kein_netz()
        with self.assertRaises(betriebsart.Gesperrt) as e:
            abgleich.TursoSpeicher("libsql://team.example.io", "geheim").ausfuehren([("SELECT 1", [])])
        self.assertIn("team.example.io", str(e.exception))
        self.assertNotIn("geheim", str(e.exception))
        with self.assertRaises(push.Fehler) as e:
            push._anfrage("https://api.telegram.org/botGEHEIM123/sendMessage", {})
        self.assertFalse(e.exception.vorlaeufig)                                                         # kein neuer Versuch
        self.assertIn("api.telegram.org", str(e.exception))
        self.assertNotIn("GEHEIM123", str(e.exception))                                                  # der Schlüssel steht in der Adresse – nie im Text
        r = verbindung.seite("https://amw.example.de")
        self.assertEqual([(s["name"], s["ok"]) for s in r["schritte"]], [("https", True), ("verbindung", False)])
        self.assertIn("blockiert", r["schritte"][1]["wert"])
        self.assertFalse(verbindung.speicher(abgleich.TursoSpeicher("https://192.168.1.5", "x"))["ok"])  # auch das Firmennetz ist nicht dieser PC

    def test_eigener_server_erreicht_das_firmennetz_aber_nicht_das_internet(self):
        einstellungen.speichern({"betriebsart": "server"})

        class Antwort:
            status = 200
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, *a): return json.dumps({"results": [{"type": "ok", "response": {"result": {"rows": []}}}]}).encode()

        with mock.patch.object(urllib.request, "urlopen", return_value=Antwort()) as auf:
            self.assertEqual(abgleich.TursoSpeicher("http://192.168.1.5:8080", "x").ausfuehren([("SELECT 1", [])]), [[]])
            push._anfrage("https://ntfy.firma.lan/", {})
            self.assertEqual(auf.call_count, 2)
            with mock.patch.object(betriebsart, "_aufloesen", return_value=["93.184.216.34"]):
                with self.assertRaises(betriebsart.Gesperrt):
                    abgleich.TursoSpeicher("libsql://team.example.io", "x").ausfuehren([("SELECT 1", [])])
                with self.assertRaises(push.Fehler):
                    push._anfrage("https://api.pushover.net/1/messages.json", {}, form=True)
            self.assertEqual(auf.call_count, 2)                                                          # nichts davon ging hinaus

    def test_cloud_laesst_alles_zu_ohne_nachzufragen(self):
        einstellungen.speichern({"betriebsart": "cloud"})
        with mock.patch.object(socket, "getaddrinfo", side_effect=AssertionError("Namensdienst gefragt")):
            self.assertTrue(betriebsart.erlaubt("https://dienst.example.com"))
            betriebsart.pruefe("https://dienst.example.com", "Probe")


class Verbindungen(Grund):
    def einrichten(self):
        os.makedirs(os.path.dirname(abgleich.zugang_pfad()), exist_ok=True)
        with open(abgleich.zugang_pfad(), "w", encoding="utf-8") as f:
            json.dump({"url": "libsql://team.example.io", "token": "geheim", "abgleich": True}, f)
        with open(push.pfad(), "w", encoding="utf-8") as f:
            json.dump({"an": True, "link": "https://amw.example.de/x?y=1", "ntfy": {"an": True, "server": "https://ntfy.firma.lan", "topic": "kanal"},
                       "telegram": {"an": True, "bot_token": "GEHEIM123", "chat_id": "7"}}, f)

    def test_liste_nennt_jede_adresse_ohne_schluessel_und_ohne_zu_verbinden(self):
        self.einrichten()
        einstellungen.speichern({"betriebsart": "pc"})
        self.kein_netz()
        d = verbindung.liste()
        kurz = [(x["wer"], x["zusatz"], f"{x['rechner']}:{x['port']}", x["stufe"], x["aktiv"], x["erlaubt"]) for x in d["zeilen"]]
        self.assertEqual(kurz, [("workbench", None, "127.0.0.1:8780", "pc", True, True),
                                ("speicher", None, "team.example.io:443", "internet", True, False),
                                ("seite", None, "amw.example.de:443", "internet", False, False),
                                ("push", "ntfy", "ntfy.firma.lan:443", "firma", True, False),
                                ("push", "telegram", "api.telegram.org:443", "internet", True, False)])
        self.assertEqual((d["betriebsart"], d["gewaehlt"], d["fehler"]), ("pc", "pc", 3))            # eingeschaltet, aber gesperrt
        self.assertNotIn("geheim", json.dumps(d).lower())
        self.assertTrue(next(x for x in d["zeilen"] if x["wer"] == "seite")["nur_pruefung"])

    def test_eigener_server_laesst_das_firmennetz_zu(self):
        self.einrichten()
        einstellungen.speichern({"betriebsart": "server"})
        with mock.patch.object(betriebsart, "_aufloesen", return_value=["93.184.216.34"]):
            d = verbindung.liste()
        self.assertEqual({(x["wer"], x["zusatz"]): x["erlaubt"] for x in d["zeilen"]},
                         {("workbench", None): True, ("speicher", None): False, ("seite", None): False, ("push", "ntfy"): True, ("push", "telegram"): False})
        self.assertEqual(d["fehler"], 2)

    def test_erreichbarkeit_fasst_gesperrte_ziele_nicht_an(self):
        self.einrichten()
        einstellungen.speichern({"betriebsart": "pc"})
        versucht = []
        d = verbindung.erreichbar(verbinde=lambda rechner, port: versucht.append(rechner) or True)
        self.assertEqual(versucht, ["127.0.0.1"])
        self.assertEqual([x["erreichbar"] for x in d["zeilen"]], [True, None, None, None, None])

    def test_befehle(self):
        import contextlib
        import io
        from amw import cli
        self.einrichten()
        aus = io.StringIO()
        with contextlib.redirect_stdout(aus), mock.patch.dict(os.environ, {"AMW_DB": os.path.join(self.ordner.name, "fehlt.db")}):
            self.assertEqual(cli.main(["einrichten", "betriebsart"]), 0)
            self.assertIn("Cloud (cloud) – nicht gewählt", aus.getvalue())                         # Abgleich an: es gilt, was bisher lief
            self.assertEqual(cli.main(["einrichten", "betriebsart", "pc"]), 0)
            self.assertEqual(betriebsart.gewaehlt(), "pc")
            self.assertEqual(cli.main(["einrichten", "verbindungen"]), 1)                          # Fehler: eingeschaltet, aber gesperrt
            self.assertEqual(cli.main(["einrichten", "betriebsart", "mond"]), 1)
        text = aus.getvalue()
        self.assertIn("team.example.io:443", text)
        self.assertIn("eingeschaltet, aber in dieser Betriebsart blockiert", text)
        self.assertNotIn("GEHEIM123", text)


if __name__ == "__main__":
    unittest.main()
