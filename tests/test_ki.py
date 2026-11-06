"""Tests für lokale KIs: Eintragen (nur lokal), Freigaben, Rechte, Auftrag als Lauf (Platz gpu), Ausführung durch den Dienst
gegen nachgebaute Ollama-/ComfyUI-Schnittstellen, Herkunft, Gegenprobe, Abbruch, Brücke, Nachweis."""
import http.server
import json
import os
import tempfile
import threading
import unittest
import urllib.parse
import zlib
from unittest import mock

from amw import betrieb, bruecke, db, dokumente, ki, kern, workbench


def png(seed):
    """Kleinste PNG mit tEXt „prompt“ wie von ComfyUI (Seed im KSampler)."""
    def stueck(typ, daten):
        return len(daten).to_bytes(4, "big") + typ + daten + zlib.crc32(typ + daten).to_bytes(4, "big")
    prompt = json.dumps({"3": {"class_type": "KSampler", "inputs": {"seed": seed}}})
    return b"\x89PNG\r\n\x1a\n" + stueck(b"tEXt", b"prompt\0" + prompt.encode("latin-1")) + stueck(b"IEND", b"")


class Nachbau(http.server.BaseHTTPRequestHandler):
    """Ollama und ComfyUI in einem: zeichnet Anfragen auf; das Verhalten steuert die Klasse."""
    anfragen, history, sperre = [], {}, threading.Lock()
    halten = False                       # ComfyUI: Bilder bleiben „in Arbeit“ (für den Abbruch)
    falscher_seed = False

    def log_message(self, *a):
        pass

    def _antwort(self, daten, typ="application/json"):
        roh = daten if isinstance(daten, bytes) else json.dumps(daten).encode()
        self.send_response(200)
        self.send_header("Content-Type", typ)
        self.send_header("Content-Length", str(len(roh)))
        self.end_headers()
        self.wfile.write(roh)

    def do_GET(self):
        u = urllib.parse.urlsplit(self.path)
        with self.sperre:
            self.anfragen.append(("GET", u.path, None))
        if u.path == "/api/version":
            return self._antwort({"version": "0.40.14"})
        if u.path == "/api/tags":
            return self._antwort({"models": [{"name": "qwen3.5:9b", "digest": "ab" * 32}]})
        if u.path == "/api/ps":
            return self._antwort({"models": []})
        if u.path == "/system_stats":
            return self._antwort({"system": {"comfyui_version": "0.44.0"}})
        if u.path.startswith("/history/"):
            pid = u.path.rsplit("/", 1)[1]
            if self.halten or pid not in self.history:
                return self._antwort({})
            return self._antwort({pid: self.history[pid]})
        if u.path == "/view":
            seed = int(urllib.parse.parse_qs(u.query)["filename"][0].split("_")[1])
            return self._antwort(png(seed + 1 if self.falscher_seed else seed), "image/png")
        self.send_error(404)

    def do_POST(self):
        u = urllib.parse.urlsplit(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        roh = self.rfile.read(n)
        daten = json.loads(roh) if self.headers.get("Content-Type") == "application/json" else roh
        with self.sperre:
            self.anfragen.append(("POST", u.path, daten))
        if u.path == "/api/generate":
            return self._antwort({"response": f"Antwort zu Seed {daten['options']['seed']}", "done": True})
        if u.path == "/prompt":
            seed = next(v["inputs"]["seed"] for v in daten["prompt"].values() if "seed" in v["inputs"])
            pid = f"p{seed}"
            self.history[pid] = {"status": {"status_str": "success", "completed": True,
                                            "messages": [["execution_start", {"timestamp": 1000}],
                                                         ["execution_success", {"timestamp": 10600}]]},
                                 "outputs": {"9": {"images": [{"filename": f"amw_{seed}_.png", "subfolder": "", "type": "output"}]}}}
            return self._antwort({"prompt_id": pid, "number": 1, "node_errors": {}})
        if u.path == "/upload/image":
            return self._antwort({"name": "amw-D1.png", "subfolder": "", "type": "input"})
        if u.path in ("/free", "/interrupt", "/queue"):
            return self._antwort({})
        self.send_error(404)


WORKFLOW = {
    "4": {"class_type": "CheckpointLoaderSimple", "inputs": {"ckpt_name": "sd_xl_base_1.0.safetensors"}},
    "6": {"class_type": "CLIPTextEncode", "inputs": {"text": "{prompt}", "clip": ["4", 1]}},
    "7": {"class_type": "CLIPTextEncode", "inputs": {"text": "{negativ}", "clip": ["4", 1]}},
    "5": {"class_type": "EmptyLatentImage", "inputs": {"width": "{breite}", "height": "{hoehe}", "batch_size": 1}},
    "3": {"class_type": "KSampler", "inputs": {"seed": "{seed}", "steps": 25, "model": ["4", 0]}},
    "9": {"class_type": "SaveImage", "inputs": {"filename_prefix": "amw", "images": ["8", 0]}},
}


class Grund(unittest.TestCase):
    def setUp(self):
        self.ordner = tempfile.TemporaryDirectory()
        self.alt_db = os.environ.get("AMW_DB")
        os.environ["AMW_DB"] = os.path.join(self.ordner.name, "amw.db")
        self.con = db.anlegen()
        with db.schreiben(self.con):
            self.pid = db.einfuegen(self.con, "projekt", name="P", angelegt_utc=db.jetzt())
            self.pid2 = db.einfuegen(self.con, "projekt", name="Q", angelegt_utc=db.jetzt())
        for k, r in (("Lead", "lead"), ("Grafik", "grafik"), ("Bauer", None)):
            kern.agent_neu(self.con, self.pid, k, rolle=r)
        kern.agent_neu(self.con, self.pid2, "Fremd", rolle=None)
        self.speicher = mock.patch.object(betrieb, "speicher_frei_gb", return_value=(30.0, 32.0))
        self.speicher.start()
        Nachbau.anfragen, Nachbau.history, Nachbau.halten, Nachbau.falscher_seed = [], {}, False, False
        self.server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Nachbau)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.ep = f"http://127.0.0.1:{self.server.server_address[1]}"

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.speicher.stop()
        self.con.close()
        if self.alt_db is None:
            os.environ.pop("AMW_DB", None)
        else:
            os.environ["AMW_DB"] = self.alt_db
        self.ordner.cleanup()

    def ollama(self, frei=True):
        ki.ki_setzen(self.con, "Bauer", "ollama", "sprache", "ollama", self.ep, lizenz="MIT")
        ki.modell_setzen(self.con, "Bauer", "ollama", "qwen3.5:9b", lizenz="Apache 2.0", kommerziell="ja", sekunden=30)
        if frei:
            ki.freigeben(self.con, self.pid, "Lead", "ollama", "qwen3.5:9b")

    def comfyui(self):
        ki.ki_setzen(self.con, "Bauer", "comfyui", "bild", "comfyui", self.ep, lizenz="GPL-3.0")
        ki.modell_setzen(self.con, "Bauer", "comfyui", "sdxl-base", datei="sd_xl_base_1.0.safetensors",
                         lizenz="CreativeML Open RAIL++-M", kommerziell="ja", nutzungsregeln=True)
        ki.freigeben(self.con, self.pid, kern.ENTWICKLER, "comfyui", "sdxl-base")
        p = os.path.join(self.ordner.name, "wf.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(WORKFLOW, f)
        ki.vorlage_setzen(self.con, self.pid, "Lead", "comfyui", "sprite", p, "SDXL 1 Bild")

    def lauf(self, lid):
        return betrieb.lauf_zeile(self.con, self.pid, lid)

    def runde(self):
        a = ki.Arbeiter(db.verbinde())
        try:
            return a.runde()
        finally:
            a.con.close()


class Eintragen(Grund):
    def test_endpunkt_nur_lokal(self):
        for falsch in ("http://10.0.0.5:11434", "http://example.com", "https://127.0.0.1:8188", "http://127.0.0.1.nip.io:1"):
            with self.assertRaises(kern.AmwFehler, msg=falsch):
                ki.ki_setzen(self.con, "Bauer", "x", "bild", "comfyui", falsch)
        ki.ki_setzen(self.con, "Bauer", "c", "bild", "comfyui", "localhost")
        self.assertEqual(ki.ki_zeile(self.con, "C")["endpunkt"], "http://localhost:8188")
        with self.assertRaises(kern.AmwFehler):                       # gibt es schon
            ki.ki_setzen(self.con, "Bauer", "c", "bild", "comfyui")

    def test_freigabe_regeln(self):
        self.ollama(frei=False)
        with self.assertRaises(kern.AmwFehler):                       # kein Lead
            ki.freigeben(self.con, self.pid, "Bauer", "ollama", "qwen3.5:9b")
        ki.freigeben(self.con, self.pid, "Lead", "ollama", "qwen3.5:9b")
        # Lizenz geändert → wieder offen
        _, was = ki.modell_setzen(self.con, "Bauer", "ollama", "qwen3.5:9b", lizenz="andere")
        self.assertIn("wieder offen", was)
        self.assertEqual(ki.modell_zeile(self.con, ki.ki_zeile(self.con, "ollama"), "qwen3.5:9b")["freigabe"], "offen")
        # Nutzungsregeln → nur der Entwickler; nicht kommerziell → gar nicht
        ki.modell_setzen(self.con, "Bauer", "ollama", "rail", lizenz="Open RAIL++-M", kommerziell="ja", nutzungsregeln=True)
        with self.assertRaises(kern.AmwFehler):
            ki.freigeben(self.con, self.pid, "Lead", "ollama", "rail")
        ki.freigeben(self.con, self.pid, kern.ENTWICKLER, "ollama", "rail")
        ki.modell_setzen(self.con, "Bauer", "ollama", "flux-dev", lizenz="non-commercial", kommerziell="nein")
        with self.assertRaises(kern.AmwFehler):
            ki.freigeben(self.con, self.pid, kern.ENTWICKLER, "ollama", "flux-dev")
        with self.assertRaises(kern.AmwFehler):                       # sperren braucht Grund
            ki.freigeben(self.con, self.pid, "Lead", "ollama", "flux-dev", frei=False)
        ki.freigeben(self.con, self.pid, "Lead", "ollama", "flux-dev", frei=False, grund="nicht kommerziell")
        m = {x["name"]: x for x in ki.uebersicht(self.con, self.pid)["modelle"]}
        self.assertEqual((m["flux-dev"]["freigabe"], m["flux-dev"]["freigabe_grund"]), ("gesperrt", "nicht kommerziell"))

    def test_rechte(self):
        self.ollama()
        with self.assertRaises(kern.AmwFehler):
            ki.auftrag(self.con, self.pid, "Grafik", "ollama", "Hallo", "qwen3.5:9b")
        with self.assertRaises(kern.AmwFehler):                       # Rechte setzt nur der Lead
            ki.recht(self.con, self.pid, "Grafik", "ollama", "Grafik")
        ki.recht(self.con, self.pid, "Lead", "ollama", "rolle:grafik")
        self.assertTrue(ki.darf(self.con, self.pid, "Grafik", ki.ki_zeile(self.con, "ollama")))
        self.assertFalse(ki.darf(self.con, self.pid, "Bauer", ki.ki_zeile(self.con, "ollama")))
        ki.recht(self.con, self.pid, "Lead", "ollama", "alle")
        self.assertTrue(ki.darf(self.con, self.pid, "Bauer", ki.ki_zeile(self.con, "ollama")))
        self.assertFalse(ki.darf(self.con, self.pid2, "Fremd", ki.ki_zeile(self.con, "ollama")))   # Rechte je Projekt
        with self.assertRaises(kern.AmwFehler):
            ki.recht(self.con, self.pid, "Lead", "ollama", "Niemand")

    def test_auftrag_nur_mit_freiem_modell_und_vorlage(self):
        self.ollama(frei=False)
        with self.assertRaises(kern.AmwFehler):
            ki.auftrag(self.con, self.pid, "Lead", "ollama", "Hallo", "qwen3.5:9b")
        self.comfyui()
        with self.assertRaises(kern.AmwFehler):                       # ohne Vorlage kein Bild-Auftrag
            ki.auftrag(self.con, self.pid, "Lead", "comfyui", "Baum")
        wf = dict(WORKFLOW, **{"10": {"class_type": "VAELoader", "inputs": {"vae_name": "unbekannt.safetensors"}}})
        p = os.path.join(self.ordner.name, "wf2.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(wf, f)
        ki.vorlage_setzen(self.con, self.pid, "Lead", "comfyui", "mit-vae", p)
        with self.assertRaises(kern.AmwFehler) as e:                  # jede beteiligte Datei muss eingetragen und frei sein
            ki.auftrag(self.con, self.pid, "Lead", "comfyui", "Baum", vorlage="mit-vae")
        self.assertIn("unbekannt.safetensors", str(e.exception))
        with self.assertRaises(kern.AmwFehler):                       # Vorlage nicht im API-Format
            p3 = os.path.join(self.ordner.name, "ui.json")
            with open(p3, "w", encoding="utf-8") as f:
                json.dump({"nodes": [], "links": []}, f)
            ki.vorlage_setzen(self.con, self.pid, "Lead", "comfyui", "ui", p3)
        self.assertEqual(self.con.execute("SELECT count(*) FROM lauf").fetchone()[0], 0)


class VorlageJeProjekt(Grund):
    def test_vorlage_gehoert_dem_projekt(self):
        self.comfyui()
        ki.freigeben(self.con, self.pid2, kern.ENTWICKLER, "comfyui", "sdxl-base")
        with self.assertRaises(kern.AmwFehler) as f:                  # Q sieht die Vorlage von P nicht
            ki.auftrag(self.con, self.pid2, kern.ENTWICKLER, "comfyui", "Ein Baum", modell="sdxl-base", vorlage="sprite")
        self.assertIn("gibt es bei comfyui nicht", str(f.exception))
        self.assertEqual(ki.uebersicht(self.con, self.pid2)["vorlagen"], [])
        p = os.path.join(self.ordner.name, "wf.json")
        self.assertEqual(ki.vorlage_setzen(self.con, self.pid2, kern.ENTWICKLER, "comfyui", "sprite", p), "angelegt")
        self.assertEqual(self.con.execute("SELECT count(*) FROM ki_vorlage").fetchone()[0], 2)
        self.assertEqual([v["name"] for v in ki.uebersicht(self.con, self.pid)["vorlagen"]], ["sprite"])


class Schlange(Grund):
    def test_ki_lauf_wartet_auf_die_grafikkarte_und_startet_ohne_sitzung(self):
        self.ollama()
        l1 = betrieb.lauf_start(self.con, self.pid, "Bauer", "Godot mit Grafikkarte", schwer=False, gpu=True)
        lid, aid, laeuft = ki.auftrag(self.con, self.pid, "Lead", "ollama", "Hallo", "qwen3.5:9b")
        self.assertFalse(laeuft)
        self.assertIn("GPU-Lauf L%d" % l1, betrieb.wartegrund(self.con, self.pid, self.lauf(lid)))
        self.assertTrue(self.lauf(lid)["gpu"])
        n = self.con.execute("SELECT count(*) FROM nachricht").fetchone()[0]
        self.assertEqual(betrieb.lauf_ende(self.con, self.pid, "Bauer", l1, 0), [lid])   # Lead hat keine Sitzung – egal
        self.assertEqual(self.lauf(lid)["status"], "laeuft")
        self.assertEqual(self.con.execute("SELECT count(*) FROM nachricht").fetchone()[0], n)  # keine Freigabe an den Agenten

    def test_gpu_pc_weit(self):
        self.ollama()
        ki.recht(self.con, self.pid, "Lead", "ollama", "alle")
        fremd = betrieb.lauf_start(self.con, self.pid2, "Fremd", "Blender anderes Projekt", schwer=False, gpu=True)
        lid, _, laeuft = ki.auftrag(self.con, self.pid, "Bauer", "ollama", "Hallo", "qwen3.5:9b")
        self.assertFalse(laeuft)
        self.assertIn(f"GPU-Lauf L{fremd}", betrieb.wartegrund(self.con, self.pid, self.lauf(lid)))
        betrieb.lauf_ende(self.con, self.pid2, "Fremd", fremd, 0)
        self.assertEqual(betrieb.warteschlange(self.con, self.pid), [lid])
        with self.assertRaises(kern.AmwFehler) as e:                  # jetzt wartet umgekehrt der GPU-Lauf des anderen Projekts
            betrieb.lauf_start(self.con, self.pid2, "Fremd", "noch einmal", schwer=False, gpu=True)
        self.assertIn(f"L{lid}", str(e.exception))
        with self.assertRaises(kern.AmwFehler):                       # … und ein Lauf mit Fenster
            with mock.patch.object(betrieb.schirm_mod, "sperrgrund", return_value=None):
                betrieb.lauf_start(self.con, self.pid2, "Fremd", "Godot mit Fenster", schwer=False, schirm=True)
        betrieb.lauf_start(self.con, self.pid2, "Fremd", "dotnet build", schwer=False)   # ohne GPU: frei


class Ausfuehren(Grund):
    def test_ollama_text_mit_herkunft_und_meldung(self):
        self.ollama()
        lid, aid, _ = ki.auftrag(self.con, self.pid, "Lead", "ollama", "Übersetze: Hallo", "qwen3.5:9b", seed=7, anzahl=2,
                                 parameter='{"temperature": 0.2}', titel="Übersetzung")
        e = self.runde()
        self.assertIn(f"L{lid} fertig", e[0])
        a = self.con.execute("SELECT * FROM ki_auftrag WHERE id = ?", (aid,)).fetchone()
        self.assertEqual(a["zustand"], "fertig")
        dids = json.loads(a["dokumente"])
        self.assertEqual(len(dids), 2)
        roh, endung = dokumente.inhalt(self.con, self.pid, dids[1])
        self.assertEqual((roh.decode().strip(), endung), ("Antwort zu Seed 8", ".md"))
        h = ki.herkunft_von(self.con, self.pid, dids[0])[0]
        self.assertEqual((h["ki"], h["ki_version"], h["modell"], h["modell_lizenz"], h["seed"], h["modell_sha256"]),
                         ("ollama", "0.40.14", "qwen3.5:9b", "Apache 2.0", 7, "ab" * 32))
        self.assertEqual(json.loads(h["parameter"]), {"temperature": 0.2})
        gen = [d for m, p, d in Nachbau.anfragen if p == "/api/generate"]
        self.assertEqual([g["keep_alive"] for g in gen], ["2m", 0])          # nach dem letzten: entladen
        self.assertEqual(gen[0]["options"], {"temperature": 0.2, "seed": 7})
        self.assertEqual(self.lauf(lid)["status"], "fertig")
        m = self.con.execute("SELECT n.von, n.art, n.kurz, e.agent FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                             " ORDER BY n.id DESC LIMIT 1").fetchone()
        self.assertEqual((m["von"], m["art"], m["agent"]), ("AMW", "meldung", "Lead"))
        self.assertIn(f"D{dids[0]}", m["kurz"])
        with self.assertRaises(Exception):                            # Herkunft bleibt, wie sie ist
            with db.schreiben(self.con):
                self.con.execute("UPDATE ki_herkunft SET seed = 1")
        # Dokument zeigt die Herkunft (Workbench/online)
        d = workbench.daten_dokument(self.con, self.pid, {"id": [str(dids[0])]})
        self.assertEqual(d["ki_herkunft"][0]["modell"], "qwen3.5:9b")
        self.assertIn("qwen3.5:9b", ki.nachweis_text(ki.nachweis(self.con, self.pid)))

    def test_comfyui_bilder_gegenprobe_und_entladen(self):
        self.comfyui()
        lid, aid, _ = ki.auftrag(self.con, self.pid, "Lead", "comfyui", "isometrischer Baum", vorlage="sprite", seed=100,
                                 anzahl=2, breite=512, hoehe=512)
        self.runde()
        a = self.con.execute("SELECT * FROM ki_auftrag WHERE id = ?", (aid,)).fetchone()
        self.assertEqual(a["zustand"], "fertig", a["fehler"])
        dids = json.loads(a["dokumente"])
        self.assertEqual(len(dids), 2)
        gesendet = [d["prompt"] for m, p, d in Nachbau.anfragen if p == "/prompt"]
        self.assertEqual([g["3"]["inputs"]["seed"] for g in gesendet], [100, 101])     # Seed als Zahl, je Bild +1
        self.assertEqual((gesendet[0]["5"]["inputs"]["width"], gesendet[0]["6"]["inputs"]["text"]), (512, "isometrischer Baum"))
        h = ki.herkunft_von(self.con, self.pid, dids[1])[0]
        self.assertEqual((h["seed"], h["vorlage"], h["modell"], h["gegenprobe"], h["dauer_s"]),
                         (101, "sprite", "sdxl-base", "Seed 101 im Bild bestätigt", 9.6))
        self.assertEqual(json.loads(h["modelle"])[0]["lizenz"], "CreativeML Open RAIL++-M")
        self.assertIn(("POST", "/free"), [(m, p) for m, p, _ in Nachbau.anfragen])
        self.assertEqual(dokumente.dokument(self.con, self.pid, dids[0])["art"], "bild")

    def test_gegenprobe_meldet_abweichung(self):
        self.comfyui()
        Nachbau.falscher_seed = True
        lid, aid, _ = ki.auftrag(self.con, self.pid, "Lead", "comfyui", "Baum", vorlage="sprite", seed=5)
        self.runde()
        did = json.loads(self.con.execute("SELECT dokumente FROM ki_auftrag WHERE id = ?", (aid,)).fetchone()[0])[0]
        self.assertTrue(ki.herkunft_von(self.con, self.pid, did)[0]["gegenprobe"].startswith("ABWEICHUNG"))

    def test_abbruch_ueber_die_schnittstelle(self):
        self.comfyui()
        Nachbau.halten = True
        lid, aid, _ = ki.auftrag(self.con, self.pid, "Lead", "comfyui", "Baum", vorlage="sprite", seed=5)
        f = threading.Thread(target=self.runde)          # wie im Dienst: eigener Faden, eigene Verbindung
        f.start()
        for _ in range(100):
            if any(p == "/history/p5" for _, p, _ in Nachbau.anfragen):
                break
            threading.Event().wait(0.05)
        betrieb.lauf_ende(self.con, self.pid, "Lead", lid, None, abgebrochen=True)
        f.join(30)
        self.assertFalse(f.is_alive())
        wege = [p for _, p, _ in Nachbau.anfragen]
        self.assertIn("/interrupt", wege)
        self.assertIn("/free", wege)
        self.assertEqual(self.con.execute("SELECT zustand FROM ki_auftrag WHERE id = ?", (aid,)).fetchone()[0], "abgebrochen")
        self.assertEqual(self.lauf(lid)["status"], "abgebrochen")

    def test_ki_aus_ohne_startbefehl_meldet_fehler(self):
        ki.ki_setzen(self.con, "Bauer", "tot", "sprache", "ollama", "http://127.0.0.1:9")   # Port 9: niemand
        ki.modell_setzen(self.con, "Bauer", "tot", "m", lizenz="MIT", kommerziell="ja")
        ki.freigeben(self.con, self.pid, "Lead", "tot", "m")
        lid, aid, _ = ki.auftrag(self.con, self.pid, "Lead", "tot", "Hallo", "m", aufgabe_id=None)
        self.runde()
        a = self.con.execute("SELECT zustand, fehler FROM ki_auftrag WHERE id = ?", (aid,)).fetchone()
        self.assertEqual(a["zustand"], "fehler")
        self.assertIn("keinen Startbefehl", a["fehler"])
        self.assertEqual((self.lauf(lid)["status"], self.lauf(lid)["rc"]), ("fertig", 1))

    def test_startet_ki_mit_startbefehl(self):
        ki.ki_setzen(self.con, "Bauer", "comfy2", "bild", "comfyui", "http://127.0.0.1:9", startbefehl="start.bat")
        k = ki.ki_zeile(self.con, "comfy2")
        gestartet = []
        with mock.patch.object(ki, "_starten", side_effect=lambda x: gestartet.append(x["name"])), \
                mock.patch.object(ki.time, "sleep"):
            with self.assertRaises(ki.KiFehler):
                ki.bereit(k, warten_s=0.2)
        self.assertEqual(gestartet, ["comfy2"])

    def test_dienst_neustart_fragt_ollama_neu(self):
        self.ollama()
        lid, aid, _ = ki.auftrag(self.con, self.pid, "Lead", "ollama", "Hallo", "qwen3.5:9b")
        with db.schreiben(self.con):
            self.con.execute("UPDATE ki_auftrag SET zustand = 'laeuft' WHERE id = ?", (aid,))
        self.runde()                                                  # neuer Arbeiter: setzt zurück und führt aus
        self.assertEqual(self.con.execute("SELECT zustand FROM ki_auftrag WHERE id = ?", (aid,)).fetchone()[0], "fertig")


class Bruecke(unittest.TestCase):
    def test_ki_ueber_die_bruecke(self):
        with tempfile.TemporaryDirectory() as eingang:
            with self.assertRaises(ValueError):
                bruecke.argumente({"befehl": "ki", "aktion": "neu", "kennung": "x", "start": "cmd /c calc"}, eingang)
            with self.assertRaises(ValueError):                       # Dateien nur aus eingang-tl/
                bruecke.argumente({"befehl": "ki", "aktion": "auftrag", "kennung": "ollama", "prompt_datei": "C:/geheim.txt"},
                                  eingang)
            args = bruecke.argumente({"befehl": "ki", "aktion": "freigeben", "kennung": "ollama", "wert": "qwen3.5:9b"}, eingang)
            self.assertEqual(args, ["ki", "freigeben", "ollama", "qwen3.5:9b", "--von", "TL"])
            args = bruecke.argumente({"befehl": "ki", "aktion": "auftrag", "kennung": "ollama", "prompt_datei": "p/a.md"}, eingang)
            self.assertEqual(args[args.index("--prompt-datei") + 1], os.path.realpath(os.path.join(eingang, "p", "a.md")))


if __name__ == "__main__":
    unittest.main()
