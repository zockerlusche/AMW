"""Lokale KIs (→ doc/plan-lokale-ki.md): eintragen, Modelle freigeben, beauftragen, ausführen, Herkunft.

- Eine KI (Ollama, ComfyUI …) gehört dem PC, nicht einem Projekt: ki und ki_modell sind PC-weit (Marke „dieser PC“); Vorlagen
  (ki_vorlage) gehören dem Projekt, das sie setzt; wer im Projekt beauftragen darf, steht in ki_recht (Lead und Entwickler immer). Endpunkte nur lokal (127.0.0.1, localhost, ::1).
- Ein Modell, das nicht „frei“ ist, kann nicht beauftragt werden. Frei gibt der Lead; bei Nutzungsregeln (z. B. Open RAIL++-M)
  oder Registrierung nur der Entwickler. Ändert sich Lizenz, Datei oder Prüfsumme, ist die Freigabe wieder offen.
- Ein Auftrag ist ein Lauf in der gemeinsamen Schlange (schwer + Platz gpu, PC-weit einer zur Zeit). Ist er dran, führt ihn
  der Dienst selbst über die HTTP-Schnittstelle aus (Arbeiter) – der Agent muss nicht wach sein. Jedes Ergebnis wird ein
  Dokument; die Herkunft (KI, Version, Modell, Lizenz, Vorlage, Prompt, Seed, Dauer) schreibt die AMW (ki_herkunft).
- Nur bei Bedarf (A1649, Marcel F5314): Antwortet eine KI nicht, startet der Dienst sie erst, wenn ein Auftrag für sie dran
  ist (Startbefehl ohne Fenster, wie Projekt-Server). Hat eine KI, die er selbst gestartet hat, ki_leerlauf_min (30) Minuten
  keinen Auftrag mehr, beendet er sie samt Kindern – nur genau diesen Prozess (PID und Startzeit gemerkt in
  daten/ki-gestartet.json), nie eine KI, die jemand anders gestartet hat, und nie, solange die KI selbst Nutzung zeigt
  (Ollama: geladenes Modell; ComfyUI: Warteschlange/letzte Ausführung – auch direkte Aufrufe an der AMW vorbei) oder nicht
  antwortet. KIs in ki_immer_an startet er wie früher von
  selbst und beendet sie nie. Platz im Grafikspeicher schafft er sonst über die Schnittstelle (Ollama keep_alive 0, ComfyUI
  /free), abbrechen über /interrupt bzw. Schließen der Anfrage.
- Startbefehl und Endpunkt kommen nur über die Kommandozeile am PC in die Datenbank (nie über Brücke oder Online-Seite).
"""
import datetime
import hashlib
import http.client
import json
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
import zlib

from . import betrieb, db, dokumente, kern, ueberwachung

log = logging.getLogger("amw.ki")

ARTEN = ("sprache", "bild", "ton", "3d", "video", "sonstig")
SCHNITTSTELLEN = {"ollama": 11434, "comfyui": 8188}     # „befehl“ (Blender, ffmpeg) folgt in Stufe 3
LOKAL = ("127.0.0.1", "localhost", "::1")
KOMMERZIELL = ("ja", "nein", "registrierung", "unklar")
PLATZHALTER = ("prompt", "negativ", "seed", "breite", "hoehe", "bild", "modell")
PLATZ = re.compile(r"\{(" + "|".join(PLATZHALTER) + r")\}")
INTERN = ("frist_min", "nachts")       # in ki_auftrag.parameter, gehen nie an die KI
MODELL_ENDUNGEN = (".safetensors", ".gguf", ".ckpt", ".pt", ".pth", ".bin", ".sft")
ANZAHL_MAX = 16
PROMPT_MAX = 20_000
VORLAGE_MAX = 1_000_000
FRIST_MIN = 60             # ein Auftrag darf so lange rechnen, dann Abbruch (je Auftrag änderbar: --frist)
START_S = 240              # so lange auf eine gerade gestartete KI warten
PRUEF_S = 60               # Zustand der KIs (an/aus, geladen) so oft prüfen
HOCH_S = 600               # eine KI, die nicht antwortet, höchstens so oft neu starten
TAKT_S = 3                 # Arbeiter: so oft nach Arbeit und Abbruch sehen


# --- Eintragen -----------------------------------------------------------------------------------

def _endpunkt(text, schnittstelle):
    """Nur lokal; ergänzt Schema und Port → 'http://127.0.0.1:11434'."""
    text = (text or "").strip() or f"http://127.0.0.1:{SCHNITTSTELLEN.get(schnittstelle, 80)}"
    if "://" not in text:
        text = "http://" + text
    u = urllib.parse.urlsplit(text)
    if u.scheme != "http" or (u.hostname or "") not in LOKAL:
        raise kern.AmwFehler("Endpunkt nur lokal: http://127.0.0.1:<port>, localhost oder [::1] – nichts im Netz")
    try:
        port = u.port or SCHNITTSTELLEN.get(schnittstelle, 80)
    except ValueError:
        raise kern.AmwFehler("Endpunkt: Port ist keine Zahl") from None
    host = f"[{u.hostname}]" if ":" in u.hostname else u.hostname
    return f"http://{host}:{port}"


def ki_zeile(con, name):
    r = con.execute("SELECT * FROM ki WHERE name = ? COLLATE NOCASE", ((name or "").strip(),)).fetchone()
    if not r:
        namen = ", ".join(x[0] for x in con.execute("SELECT name FROM ki WHERE aktiv = 1 ORDER BY name")) or "keine"
        raise kern.AmwFehler(f"KI „{name}“ ist nicht eingetragen (eingetragen: {namen}) – amw ki neu <name> …")
    return r


def ki_setzen(con, von, name, art=None, schnittstelle=None, endpunkt=None, version=None, lizenz=None, ablage=None,
              startbefehl=None, ordner=None, vram_gb=None, aktiv=None, neu=True):
    """neu: anlegen (Fehler, wenn es sie gibt); sonst ändern. Leere Angaben bleiben beim Ändern, wie sie sind."""
    name = (name or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,39}", name):
        raise kern.AmwFehler("Name: 1–40 Zeichen, Buchstaben, Ziffern, _ . -")
    if art and art not in ARTEN:
        raise kern.AmwFehler(f"Art: {', '.join(ARTEN)}")
    if schnittstelle and schnittstelle not in (*SCHNITTSTELLEN, "befehl"):
        raise kern.AmwFehler(f"Schnittstelle: {', '.join(SCHNITTSTELLEN)} | befehl (eigenes Programm, rechnen über lauf ausfuehren --gpu)")
    if ordner and not os.path.isdir(ordner):
        raise kern.AmwFehler(f"Ordner {ordner} gibt es nicht")
    alt = con.execute("SELECT * FROM ki WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
    if neu and alt:
        raise kern.AmwFehler(f"KI „{alt['name']}“ gibt es schon – ändern: amw ki aendern {alt['name']} …")
    if not neu and not alt:
        ki_zeile(con, name)
    schnittstelle = schnittstelle or (alt["schnittstelle"] if alt else None)
    if not schnittstelle:
        raise kern.AmwFehler(f"--schnittstelle {' | '.join(SCHNITTSTELLEN)} | befehl angeben")
    if not (art or alt):
        raise kern.AmwFehler(f"--art {' | '.join(ARTEN)} angeben")
    werte = {"art": art, "schnittstelle": schnittstelle,
             "endpunkt": _endpunkt(endpunkt, schnittstelle) if endpunkt or not alt else None,
             "version": version, "lizenz": lizenz, "ablage": ablage, "startbefehl": startbefehl, "ordner": ordner,
             "vram_gb": vram_gb, "aktiv": None if aktiv is None else int(bool(aktiv))}
    with db.schreiben(con):
        if alt:
            felder = {k: v for k, v in werte.items() if v is not None}
            if felder:
                con.execute(f"UPDATE ki SET {', '.join(k + ' = ?' for k in felder)} WHERE id = ?", (*felder.values(), alt["id"]))
            return alt["id"], "geändert"
        kid = db.einfuegen(con, "ki", name=name, **{k: v for k, v in werte.items() if v is not None},
                           angelegt_von=von, angelegt_utc=db.jetzt())
        return kid, "angelegt"


def modell_zeile(con, ki, name):
    r = con.execute("SELECT * FROM ki_modell WHERE ki_id = ? AND (name = ? OR datei = ?)", (ki["id"], name, name)).fetchone()
    if not r:
        raise kern.AmwFehler(f"Modell „{name}“ ist bei {ki['name']} nicht eingetragen – amw ki modell {ki['name']} <name> …")
    return r


def modell_setzen(con, von, ki_name, name, datei=None, version=None, sha256=None, quelle=None, lizenz=None,
                  kommerziell=None, nutzungsregeln=None, vram_gb=None, sekunden=None, notiz=None):
    """Modell eintragen oder ändern (Freigabe bleibt offen; ändern sich Lizenz, Datei oder Prüfsumme: wieder offen)."""
    ki = ki_zeile(con, ki_name)
    name = (name or "").strip()
    if not name or len(name) > 120:
        raise kern.AmwFehler("Modellname: 1–120 Zeichen")
    if kommerziell and kommerziell not in KOMMERZIELL:
        raise kern.AmwFehler(f"kommerziell: {', '.join(KOMMERZIELL)}")
    if sha256 and not re.fullmatch(r"(sha256:)?[0-9a-fA-F]{64}", sha256.strip()):
        raise kern.AmwFehler("sha256: 64 Hex-Zeichen")
    werte = {"datei": datei, "version": version, "sha256": sha256 and sha256.strip().lower().removeprefix("sha256:"),
             "quelle": quelle, "lizenz": lizenz, "kommerziell": kommerziell,
             "nutzungsregeln": None if nutzungsregeln is None else int(bool(nutzungsregeln)), "vram_gb": vram_gb,
             "sekunden": sekunden, "notiz": notiz}
    with db.schreiben(con):
        alt = con.execute("SELECT * FROM ki_modell WHERE ki_id = ? AND name = ?", (ki["id"], name)).fetchone()
        if alt:
            felder = {k: v for k, v in werte.items() if v is not None}
            pruefen = any(k in felder and felder[k] != alt[k] for k in ("datei", "sha256", "lizenz", "kommerziell", "nutzungsregeln"))
            if pruefen and alt["freigabe"] == "frei":
                felder.update(freigabe="offen", freigabe_grund="Angaben geändert – bitte neu prüfen", freigabe_von=von,
                              freigabe_utc=db.jetzt())
            if felder:
                con.execute(f"UPDATE ki_modell SET {', '.join(k + ' = ?' for k in felder)} WHERE id = ?",
                            (*felder.values(), alt["id"]))
            return alt["id"], "geändert" + (" – Freigabe wieder offen" if pruefen and alt["freigabe"] == "frei" else "")
        mid = db.einfuegen(con, "ki_modell", ki_id=ki["id"], name=name, **{k: v for k, v in werte.items() if v is not None},
                           angelegt_von=von, angelegt_utc=db.jetzt())
        return mid, "eingetragen (Freigabe offen)"


def freigeben(con, pid, von, ki_name, name, frei=True, grund=None):
    """frei: Lead – bei Nutzungsregeln oder Registrierung nur der Entwickler; nur kommerziell nutzbare Modelle.
    gesperrt: Lead oder Entwickler, mit Grund (bleibt sichtbar, damit es keiner erneut lädt)."""
    ki = ki_zeile(con, ki_name)
    m = modell_zeile(con, ki, name)
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Modelle geben Lead und Entwickler frei")
    if frei:
        if m["kommerziell"] in ("nein", "unklar"):
            raise kern.AmwFehler(f"{m['name']}: kommerziell „{m['kommerziell']}“ – frei nur mit kommerziell nutzbarer Lizenz"
                                 f" (eintragen: amw ki modell {ki['name']} \"{m['name']}\" --kommerziell ja|registrierung)")
        if not m["lizenz"]:
            raise kern.AmwFehler(f"{m['name']}: Lizenz fehlt – erst eintragen (--lizenz)")
        if (m["nutzungsregeln"] or m["kommerziell"] == "registrierung") and von != kern.ENTWICKLER:
            raise kern.AmwFehler(f"{m['name']}: Lizenz mit Nutzungsregeln bzw. Registrierung – frei gibt nur der Entwickler")
    elif not (grund or "").strip():
        raise kern.AmwFehler("sperren braucht --grund (z. B. nicht kommerziell, nicht in der EU)")
    with db.schreiben(con):
        con.execute("UPDATE ki_modell SET freigabe = ?, freigabe_grund = ?, freigabe_von = ?, freigabe_utc = ? WHERE id = ?",
                    ("frei" if frei else "gesperrt", (grund or "").strip() or None, von, db.jetzt(), m["id"]))


def _workflow(text):
    try:
        wf = json.loads(text)
    except ValueError as e:
        raise kern.AmwFehler(f"Vorlage ist kein JSON: {e}") from None
    if not isinstance(wf, dict) or not wf or not all(isinstance(v, dict) and "class_type" in v and "inputs" in v
                                                     for v in wf.values()):
        raise kern.AmwFehler("Vorlage bitte im API-Format von ComfyUI (Workflow → Export (API)): {\"3\": {\"class_type\": …,"
                             " \"inputs\": …}, …}")
    return wf


def vorlage_setzen(con, pid, von, ki_name, name, pfad, beschreibung=None):
    ki = ki_zeile(con, ki_name)
    if not darf(con, pid, von, ki):
        raise kern.AmwFehler(f"Vorlagen für {ki['name']} setzt, wer sie beauftragen darf (amw ki recht)")
    name = (name or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,59}", name):
        raise kern.AmwFehler("Vorlagen-Name: 1–60 Zeichen, Buchstaben, Ziffern, _ . -")
    if not os.path.isfile(pfad or ""):
        raise kern.AmwFehler(f"Datei {pfad} gibt es nicht")
    if os.path.getsize(pfad) > VORLAGE_MAX:
        raise kern.AmwFehler("Vorlage größer als 1 MB")
    with open(pfad, encoding="utf-8") as f:
        text = f.read()
    if ki["schnittstelle"] == "comfyui":
        _workflow(text)
    if dokumente.GEHEIM.search(text):
        raise kern.AmwFehler("Die Vorlage enthält etwas, das wie ein Schlüssel aussieht – nicht übernommen")
    sha = hashlib.sha256(text.encode("utf-8")).hexdigest()
    with db.schreiben(con):
        alt = con.execute("SELECT id, sha256 FROM ki_vorlage WHERE projekt_id = ? AND ki_id = ? AND name = ?",
                          (pid, ki["id"], name)).fetchone()
        if alt:
            con.execute("UPDATE ki_vorlage SET inhalt = ?, sha256 = ?, beschreibung = coalesce(?, beschreibung), von = ?,"
                        " stand_utc = ?, aktiv = 1 WHERE id = ?", (text, sha, beschreibung, von, db.jetzt(), alt["id"]))
            return "unverändert" if alt["sha256"] == sha else "neuer Stand"
        db.einfuegen(con, "ki_vorlage", projekt_id=pid, ki_id=ki["id"], name=name, beschreibung=beschreibung, inhalt=text, sha256=sha,
                     von=von, stand_utc=db.jetzt())
        return "angelegt"


def recht(con, pid, von, ki_name, wer, entziehen=False):
    """wer: alle | rolle:<rolle> | Kennung. Setzen Lead und Entwickler."""
    ki = ki_zeile(con, ki_name)
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Rechte für KIs setzen Lead und Entwickler")
    wer = (wer or "").strip()
    if not wer:
        raise kern.AmwFehler("--wer alle | rolle:<rolle> | <Name>")
    if wer != "alle" and not wer.startswith("rolle:"):
        a = kern.agent_zeile(con, pid, wer)
        if not a:
            raise kern.AmwFehler("--wer: alle, rolle:<rolle> oder der Name eines Agenten dieses Projekts")
        wer = a["kennung"]
    with db.schreiben(con):
        if entziehen:
            return con.execute("DELETE FROM ki_recht WHERE projekt_id = ? AND ki_id = ? AND wer = ?", (pid, ki["id"], wer)).rowcount
        if not con.execute("SELECT 1 FROM ki_recht WHERE projekt_id = ? AND ki_id = ? AND wer = ?", (pid, ki["id"], wer)).fetchone():
            db.einfuegen(con, "ki_recht", projekt_id=pid, ki_id=ki["id"], wer=wer, von=von, seit_utc=db.jetzt())
        return 1


def darf(con, pid, von, ki):
    if kern.ist_lead(con, pid, von):
        return True
    a = kern.agent_zeile(con, pid, von)
    # „rolle:<x>“ in einer Freigabe meint Lead oder – wie vor Schema 22 – das Fachgebiet
    wer = ["alle", von] + [f"rolle:{x}" for x in ((a["rolle"], a["fachgebiet"]) if a else ()) if x]
    return bool(con.execute(f"SELECT 1 FROM ki_recht WHERE projekt_id = ? AND ki_id = ? AND wer IN ({','.join('?' * len(wer))})",
                            (pid, ki["id"], *wer)).fetchone())


# --- Auftrag -------------------------------------------------------------------------------------

def _fuellen(wert, werte):
    """Platzhalter einsetzen; steht ein Platzhalter allein, behält der Wert seinen Typ (Seed als Zahl)."""
    if isinstance(wert, dict):
        return {k: _fuellen(v, werte) for k, v in wert.items()}
    if isinstance(wert, list):
        return [_fuellen(v, werte) for v in wert]
    if isinstance(wert, str):
        m = PLATZ.fullmatch(wert)
        if m and m.group(1) in werte:
            return werte[m.group(1)]
        return PLATZ.sub(lambda x: str(werte[x.group(1)]) if x.group(1) in werte else x.group(0), wert)
    return wert


def _platzhalter(wert, gefunden=None):
    gefunden = set() if gefunden is None else gefunden
    if isinstance(wert, dict):
        for v in wert.values():
            _platzhalter(v, gefunden)
    elif isinstance(wert, list):
        for v in wert:
            _platzhalter(v, gefunden)
    elif isinstance(wert, str):
        gefunden.update(PLATZ.findall(wert))
    return gefunden


def _modell_dateien(wf):
    """Alle Modell-Dateien, die ein (gefüllter) Workflow nennt."""
    dateien = []

    def gehe(w):
        if isinstance(w, dict):
            for v in w.values():
                gehe(v)
        elif isinstance(w, list):
            for v in w:
                gehe(v)
        elif isinstance(w, str) and w.lower().endswith(MODELL_ENDUNGEN) and w not in dateien:
            dateien.append(w)
    gehe(wf)
    return dateien


def _frei_oder_fehler(m, ki):
    if m["freigabe"] != "frei":
        raise kern.AmwFehler(f"Modell {m['name']} ({ki['name']}) ist nicht frei ({m['freigabe']}"
                             + (f": {m['freigabe_grund']}" if m["freigabe_grund"] else "") + ") – frei gibt der Lead,"
                             " bei Nutzungsregeln der Entwickler: amw ki freigeben " + ki["name"] + f" \"{m['name']}\"")


def auftrag(con, pid, von, ki_name, prompt, modell=None, vorlage=None, negativ=None, seed=None, anzahl=1, breite=None,
            hoehe=None, bild=None, parameter=None, titel=None, aufgabe_id=None, frist_min=None, nachts=False):
    """Prüft Recht, Freigaben und Vorlage, legt Lauf (schwer + gpu) und Auftrag in einer Transaktion an.
    nachts: startet erst im KI-Fenster (PC-Einstellung ki_fenster) und nie in der Vorlaufzeit eines Testtermins – bis dahin
    überholen ihn alle anderen Läufe. Rückgabe (lauf_id, auftrag_id, läuft_schon)."""
    ki = ki_zeile(con, ki_name)
    if not ki["aktiv"]:
        raise kern.AmwFehler(f"KI {ki['name']} ist abgeschaltet")
    if ki["schnittstelle"] not in SCHNITTSTELLEN:
        raise kern.AmwFehler(f"Schnittstelle {ki['schnittstelle']} beauftragt die AMW noch nicht (Stufe 3) – bis dahin"
                             " amw lauf ausfuehren --gpu …")
    if not darf(con, pid, von, ki):
        raise kern.AmwFehler(f"{von} darf {ki['name']} nicht beauftragen – das Recht setzt der Lead (amw ki recht {ki['name']}"
                             f" --wer {von})")
    prompt = (prompt or "").strip()
    if not prompt:
        raise kern.AmwFehler("--prompt oder --prompt-datei angeben")
    if len(prompt) > PROMPT_MAX or len(negativ or "") > PROMPT_MAX:
        raise kern.AmwFehler(f"Prompt länger als {PROMPT_MAX} Zeichen")
    if dokumente.GEHEIM.search(prompt):
        raise kern.AmwFehler("Der Prompt enthält etwas, das wie ein Schlüssel aussieht – nicht beauftragt")
    anzahl = int(anzahl or 1)
    if not 1 <= anzahl <= ANZAHL_MAX:
        raise kern.AmwFehler(f"--anzahl 1–{ANZAHL_MAX}")
    seed = int(seed) if seed is not None else secrets.randbelow(2**31)
    if not 0 <= seed < 2**53:
        raise kern.AmwFehler("--seed: 0 bis 2^53")
    for n, w in (("breite", breite), ("hoehe", hoehe)):
        if w is not None and not 64 <= int(w) <= 4096:
            raise kern.AmwFehler(f"--{n}: 64–4096")
    if isinstance(parameter, str):
        try:
            parameter = json.loads(parameter) if parameter.strip() else {}
        except ValueError as e:
            raise kern.AmwFehler(f"--parameter ist kein JSON: {e}") from None
    if parameter is not None and not isinstance(parameter, dict):
        raise kern.AmwFehler("--parameter: ein JSON-Objekt, z. B. {\"temperature\": 0.2}")
    eingabe = []
    if bild:
        did = int(str(bild).lstrip("Dd"))
        d = dokumente.dokument(con, pid, did)
        if d["status"] == "geloescht" or d["versionen"][-1]["vorschau"] != "bild":
            raise kern.AmwFehler(f"D{did} ist kein (vorhandenes) Bild")
        eingabe.append(f"D{did}")
    if aufgabe_id and not con.execute("SELECT 1 FROM aufgabe WHERE id = ? AND projekt_id = ?", (aufgabe_id, pid)).fetchone():
        raise kern.AmwFehler(f"Aufgabe {aufgabe_id} gibt es nicht")
    m, v = None, None
    if modell:
        m = modell_zeile(con, ki, modell)
        _frei_oder_fehler(m, ki)
    if ki["schnittstelle"] == "ollama":
        if not m:
            raise kern.AmwFehler("--modell angeben (Ollama-Modellname, eingetragen und frei)")
        if vorlage:
            raise kern.AmwFehler("Ollama braucht keine Vorlage")
    else:
        if not vorlage:
            raise kern.AmwFehler(f"--vorlage angeben – ohne Vorlage kein Bild-Auftrag (amw ki vorlage {ki['name']} <name>"
                                 " --datei workflow_api.json)")
        v = con.execute("SELECT * FROM ki_vorlage WHERE projekt_id = ? AND ki_id = ? AND name = ? AND aktiv = 1",
                        (pid, ki["id"], vorlage)).fetchone()
        if not v:
            raise kern.AmwFehler(f"Vorlage „{vorlage}“ gibt es bei {ki['name']} nicht")
        wf = _workflow(v["inhalt"])
        brauch = _platzhalter(wf)
        if "bild" in brauch and not bild:
            raise kern.AmwFehler(f"Vorlage {vorlage} braucht ein Eingabebild: --bild D<nr>")
        if "modell" in brauch and not m:
            raise kern.AmwFehler(f"Vorlage {vorlage} setzt das Modell ein: --modell angeben")
        gefuellt = _fuellen(wf, {"modell": m["datei"] or m["name"]} if m else {})
        for datei in _modell_dateien(gefuellt):    # jedes beteiligte Modell muss eingetragen und frei sein
            r = con.execute("SELECT * FROM ki_modell WHERE ki_id = ? AND (datei = ? OR name = ?)", (ki["id"], datei, datei)).fetchone()
            if not r:
                raise kern.AmwFehler(f"Vorlage {vorlage} nutzt {datei} – nicht eingetragen (amw ki modell {ki['name']} <name>"
                                     f" --datei \"{datei}\" --lizenz … --kommerziell …)")
            _frei_oder_fehler(r, ki)
            m = m or r
    erwartet = round((m["sekunden"] or 0) * anzahl / 60 + 2, 1) if m and m["sekunden"] else None
    kurz = titel or prompt
    beschreibung = f"KI {ki['name']} · {m['name'] if m else vorlage}{f' · {anzahl}×' if anzahl > 1 else ''}: {betrieb.kurzfassung(kurz, 90)}"
    neu = {}

    def dazu(lid):
        neu["id"] = db.einfuegen(
            con, "ki_auftrag", projekt_id=pid, lauf_id=lid, ki_id=ki["id"], modell_id=m["id"] if m else None,
            vorlage_id=v["id"] if v else None, vorlage_sha256=v["sha256"] if v else None, auftraggeber=von,
            aufgabe_id=aufgabe_id, titel=(titel or "").strip()[:200] or None, prompt=prompt, negativ=negativ or None,
            seed=seed, anzahl=anzahl, breite=breite, hoehe=hoehe, eingabe=json.dumps(eingabe) if eingabe else None,
            parameter=json.dumps(intern, ensure_ascii=False) if intern else None, angelegt_utc=db.jetzt())
    if parameter and any(k in parameter for k in INTERN):
        raise kern.AmwFehler(f"--parameter: {', '.join(INTERN)} setzt die AMW selbst (--frist, --nachts)")
    intern = {**(parameter or {}), **({"frist_min": frist_min} if frist_min else {}), **({"nachts": 1} if nachts else {})}
    lid = betrieb.lauf_start(con, pid, von, beschreibung, schwer=True, gpu=True, aufgabe_id=aufgabe_id, warten=True,
                             erwartet_min=erwartet, dazu=dazu, sperre=nacht_sperre(con) if nachts else None)
    laeuft = betrieb.lauf_zeile(con, pid, lid)["status"] == "laeuft"
    return lid, neu["id"], laeuft


def auftrag_zeile(con, pid, nr):
    """nr: Lauf (L812) oder Auftrag (812 → zuerst als Lauf gesucht)."""
    t = str(nr).strip()
    zahl = int(t.lstrip("LlKk") or 0)
    r = con.execute("SELECT * FROM ki_auftrag WHERE projekt_id = ? AND lauf_id = ?", (pid, zahl)).fetchone()
    if not r and not t.upper().startswith("L"):
        r = con.execute("SELECT * FROM ki_auftrag WHERE projekt_id = ? AND id = ?", (pid, zahl)).fetchone()
    if not r:
        raise kern.AmwFehler(f"KI-Auftrag {t} gibt es nicht (Lauf-Nummer, z. B. L812)")
    return r


# --- Schnittstellen (HTTP, nur lokal) ------------------------------------------------------------

class KiFehler(Exception):
    pass


def _anfrage(endpunkt, weg, daten=None, frist=30, roh=False, kopf=None, abbruch=None):
    """GET (daten None) oder POST (dict → JSON, bytes so wie sie sind). abbruch(): bei True wird die Verbindung geschlossen
    (Ollama bricht die Erzeugung dann ab). Rückgabe: JSON bzw. bytes."""
    u = urllib.parse.urlsplit(endpunkt)
    if (u.hostname or "") not in LOKAL:                       # zweite Sicherung neben dem Eintragen
        raise KiFehler("Endpunkt nicht lokal")
    verb = http.client.HTTPConnection(u.hostname, u.port, timeout=frist)
    ergebnis = {}

    def schicken():
        try:
            koerper = None if daten is None else daten if isinstance(daten, bytes) else json.dumps(daten).encode("utf-8")
            k = dict(kopf or {})
            if koerper is not None and not isinstance(daten, bytes):
                k["Content-Type"] = "application/json"
            verb.request("GET" if daten is None else "POST", weg, body=koerper, headers=k)
            a = verb.getresponse()
            ergebnis["status"], ergebnis["inhalt"] = a.status, a.read()
        except Exception as e:                                # noqa: BLE001 – wird unten zur Meldung
            ergebnis["fehler"] = e
    if abbruch is None:
        schicken()
    else:
        f = threading.Thread(target=schicken, daemon=True)
        f.start()
        while f.is_alive():
            f.join(1.0)
            if f.is_alive() and abbruch():
                try:
                    verb.sock and verb.sock.shutdown(socket.SHUT_RDWR)
                except OSError:
                    pass
                verb.close()
                raise KiFehler("abgebrochen")
    verb.close()
    if "fehler" in ergebnis:
        e = ergebnis["fehler"]
        raise KiFehler(f"{weg}: {type(e).__name__}: {e}")
    if ergebnis["status"] >= 400:
        raise KiFehler(f"{weg}: HTTP {ergebnis['status']} {ergebnis['inhalt'][:300].decode('utf-8', 'replace')}")
    if roh:
        return ergebnis["inhalt"]
    try:
        return json.loads(ergebnis["inhalt"] or b"null")
    except ValueError:
        raise KiFehler(f"{weg}: Antwort ist kein JSON") from None


def _version_weg(ki):
    return "/api/version" if ki["schnittstelle"] == "ollama" else "/system_stats"


def _version(ki, antwort):
    if ki["schnittstelle"] == "ollama":
        return (antwort or {}).get("version")
    return ((antwort or {}).get("system") or {}).get("comfyui_version")


def _starten(ki, jetzt=None):
    """KI mit ihrem Startbefehl ohne Fenster starten (wie Projekt-Server) und sich den Prozess merken (PID + Startzeit) –
    nur so gestartete KIs beendet leerlauf_beenden() wieder."""
    p = ueberwachung.starten({"name": f"ki-{ki['name']}", "startbefehl": ki["startbefehl"], "ordner": ki["ordner"]})
    beginn = _prozess_beginn(getattr(p, "pid", None))
    if beginn is not None:
        d = gestartet_laden()
        d[ki["name"].lower()] = {"pid": p.pid, "beginn": beginn, "seit": time.time() if jetzt is None else jetzt}
        gestartet_schreiben(d)


# --- Nur bei Bedarf (A1649) ----------------------------------------------------------------------

def immer_an():
    """Namen (klein) der KIs, die die AMW am Laufen hält; alle anderen nur bei Bedarf."""
    from . import einstellungen
    return set(einstellungen.wert("ki_immer_an"))


def leerlauf_min():
    from . import einstellungen
    return einstellungen.wert("ki_leerlauf_min")


def _gestartet_pfad():
    return os.path.join(os.path.dirname(db.db_pfad()), "ki-gestartet.json")


def gestartet_laden():
    """{Name: {pid, beginn, seit}} der KIs, die der Dienst selbst gestartet hat (überlebt einen Neustart des Dienstes)."""
    try:
        with open(_gestartet_pfad(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def gestartet_schreiben(d):
    tmp = _gestartet_pfad() + ".neu"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(d, f, indent=1)
    os.replace(tmp, _gestartet_pfad())


def _prozess_beginn(pid):
    """Startzeit eines laufenden Prozesses (Zahl) – None, wenn er nicht (mehr) läuft. Damit erkennt die AMW ihren Prozess
    wieder: eine neu vergebene PID hat eine andere Startzeit."""
    if not pid:
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        k = ctypes.WinDLL("kernel32", use_last_error=True)
        k.OpenProcess.restype = wintypes.HANDLE
        k.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
        k.GetExitCodeProcess.argtypes = (wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD))
        k.GetProcessTimes.argtypes = (wintypes.HANDLE,) + (ctypes.POINTER(wintypes.FILETIME),) * 4
        k.CloseHandle.argtypes = (wintypes.HANDLE,)
        h = k.OpenProcess(0x1000, False, int(pid))            # PROCESS_QUERY_LIMITED_INFORMATION
        if not h:
            return None
        try:
            code = wintypes.DWORD()
            if not k.GetExitCodeProcess(h, ctypes.byref(code)) or code.value != 259:    # STILL_ACTIVE
                return None
            t = [wintypes.FILETIME() for _ in range(4)]
            if not k.GetProcessTimes(h, *(ctypes.byref(x) for x in t)):
                return None
            return (t[0].dwHighDateTime << 32) | t[0].dwLowDateTime
        finally:
            k.CloseHandle(h)
    try:
        with open(f"/proc/{int(pid)}/stat", encoding="ascii") as f:
            return int(f.read().rsplit(")", 1)[1].split()[19])
    except (OSError, ValueError, IndexError):
        return None


def _baum_beenden(prozess_id):
    from .laufdienst import _baum_beenden as beenden
    beenden(prozess_id)


def _utc_sek(utc):
    return datetime.datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()


def nutzung(ki, jetzt=None):
    """Fragt die KI selbst, ob sie gerade jemand benutzt – auch an der AMW vorbei (TL P136): Rückgabe (beschaeftigt, zuletzt).
    Ollama: ein geladenes Modell (/api/ps) heißt „eben benutzt“ (es bleibt nur keep_alive lang geladen). ComfyUI: laufende oder
    wartende Prompts (/queue), sonst die Zeit der letzten Ausführung (/history). Antwortet sie nicht: (True, None) – im
    Zweifel nicht beenden."""
    try:
        if ki["schnittstelle"] == "ollama":
            return bool((_anfrage(ki["endpunkt"], "/api/ps", frist=5) or {}).get("models")), None
        if ki["schnittstelle"] == "comfyui":
            q = _anfrage(ki["endpunkt"], "/queue", frist=5) or {}
            if q.get("queue_running") or q.get("queue_pending"):
                return True, None
            h = _anfrage(ki["endpunkt"], "/history?max_items=1", frist=5) or {}
            zeiten = [m[1].get("timestamp") for x in h.values() for m in ((x.get("status") or {}).get("messages") or [])
                      if isinstance(m, (list, tuple)) and len(m) > 1 and isinstance(m[1], dict) and m[1].get("timestamp")]
            return False, (max(zeiten) / 1000 if zeiten else None)
    except (KiFehler, OSError, ValueError, AttributeError, TypeError):
        return True, None
    return False, None


def leerlauf_beenden(con, jetzt=None, beginn=None, beenden_mit=None, immer=None, minuten=None, frage=None):
    """Selbst gestartete KIs beenden (samt Kindern), wenn seit `minuten` weder ein AMW-Auftrag kam NOCH die KI selbst benutzt
    wurde (nutzung(): auch direkte Aufrufe an der AMW vorbei). Nie: KIs in ki_immer_an, KIs mit wartendem oder laufendem
    Auftrag, eine KI, die nicht antwortet (im Zweifel nicht), Prozesse, die nicht mehr genau unsere sind (PID weg oder neu
    vergeben → vergessen). Jede Runde gesehene Nutzung setzt die Zeit zurück. Rückgabe: Ereignistexte."""
    jetzt = time.time() if jetzt is None else jetzt
    beginn = beginn or _prozess_beginn
    beenden_mit = beenden_mit or _baum_beenden
    frage = frage or nutzung
    immer = immer_an() if immer is None else immer
    minuten = leerlauf_min() if minuten is None else minuten
    d = gestartet_laden()
    aus, geaendert = [], False
    for name, g in list(d.items()):
        if g.get("beginn") is None or beginn(g.get("pid")) != g.get("beginn"):
            d.pop(name)                                   # beendet oder PID inzwischen ein anderer Prozess: nicht anfassen
            geaendert = True
            continue
        if name in immer:
            continue
        ki = con.execute("SELECT * FROM ki WHERE name = ? COLLATE NOCASE", (name,)).fetchone()
        zuletzt = g.get("seit") or 0
        if ki:
            if ki["zustand"] == "belegt" or con.execute("SELECT 1 FROM ki_auftrag WHERE ki_id = ? AND zustand IN ('wartet', 'laeuft')",
                                                        (ki["id"],)).fetchone():
                continue
            letzt = con.execute("SELECT max(coalesce(ende_utc, start_utc)) FROM ki_auftrag WHERE ki_id = ?", (ki["id"],)).fetchone()[0]
            if letzt:
                zuletzt = max(zuletzt, _utc_sek(letzt))
            beschaeftigt, direkt = frage(ki, jetzt)             # jede Runde: auch wer die KI direkt benutzt, zählt
            if beschaeftigt:
                if g.get("genutzt") != jetzt:
                    g["genutzt"] = jetzt
                    geaendert = True
                continue
            zuletzt = max(zuletzt, g.get("genutzt") or 0, direkt or 0)
        if jetzt - zuletzt < minuten * 60:
            continue
        beenden_mit(g["pid"])
        d.pop(name)
        geaendert = True
        if ki:
            with db.schreiben(con):
                con.execute("UPDATE ki SET zustand = 'aus', geladen = NULL, geprueft_utc = ? WHERE id = ?", (db.jetzt(), ki["id"]))
        aus.append(f"{name}: {minuten} min weder Auftrag noch Nutzung – beendet (von der AMW gestartet, PID {g['pid']})")
    if geaendert:
        gestartet_schreiben(d)
    return aus


def bereit(ki, abbruch=lambda: False, warten_s=START_S):
    """Antwortet die KI? Sonst mit Startbefehl starten und warten. Rückgabe: Programm-Version."""
    try:
        return _version(ki, _anfrage(ki["endpunkt"], _version_weg(ki), frist=5))
    except KiFehler:
        if not ki["startbefehl"]:
            raise KiFehler(f"{ki['name']} antwortet nicht unter {ki['endpunkt']} und hat keinen Startbefehl") from None
    log.info("KI %s antwortet nicht – starte sie", ki["name"])
    _starten(ki)
    ende = time.time() + warten_s
    while time.time() < ende:
        if abbruch():
            raise KiFehler("abgebrochen")
        time.sleep(3)
        try:
            return _version(ki, _anfrage(ki["endpunkt"], _version_weg(ki), frist=5))
        except KiFehler:
            continue
    raise KiFehler(f"{ki['name']} antwortet nach dem Start {warten_s} s lang nicht (Protokoll: daten/server-ki-{ki['name']}.log)")


def _png_text(roh):
    """Text-Angaben einer PNG (tEXt/iTXt) – ComfyUI schreibt dort Workflow und Prompt hinein."""
    if roh[:8] != b"\x89PNG\r\n\x1a\n":
        return {}
    i, aus = 8, {}
    while i + 8 <= len(roh):
        n, typ = int.from_bytes(roh[i:i + 4], "big"), roh[i + 4:i + 8]
        daten = roh[i + 8:i + 8 + n]
        try:
            if typ == b"tEXt":
                k, _, w = daten.partition(b"\0")
                aus[k.decode("latin-1")] = w.decode("latin-1")
            elif typ == b"iTXt":
                k, _, rest = daten.partition(b"\0")
                gepackt, rest = rest[0], rest[2:]
                _, _, rest = rest.partition(b"\0")
                _, _, w = rest.partition(b"\0")
                aus[k.decode("latin-1")] = (zlib.decompress(w) if gepackt else w).decode("utf-8", "replace")
        except (IndexError, zlib.error):
            pass
        if typ == b"IEND":
            break
        i += 12 + n
    return aus


def gegenprobe(roh, seed):
    """Stimmt der Seed in der PNG mit dem Auftrag überein? (ComfyUI schreibt den Prompt mit Seed ins Bild.)"""
    t = _png_text(roh).get("prompt")
    if not t:
        return "keine Angaben im Bild"
    try:
        wf = json.loads(t)
    except ValueError:
        return "Angaben im Bild nicht lesbar"
    seeds = [v for n in wf.values() if isinstance(n, dict) for k, v in (n.get("inputs") or {}).items()
             if k in ("seed", "noise_seed") and isinstance(v, int)]
    if seed in seeds:
        return f"Seed {seed} im Bild bestätigt"
    return f"ABWEICHUNG: Seed im Bild {', '.join(map(str, seeds)) or 'fehlt'}, Auftrag {seed}"


class VramMesser:
    """Spitze des belegten Grafikspeichers (nvidia-smi alle 2 s), solange der Auftrag läuft – nur lesen."""

    def __init__(self):
        self.spitze, self.stop = None, threading.Event()
        self.prog = shutil.which("nvidia-smi")

    def messen(self):
        try:
            r = subprocess.run([self.prog, "--query-gpu=memory.used", "--format=csv,noheader,nounits"], capture_output=True,
                               text=True, timeout=5, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            gb = round(max(float(z) for z in r.stdout.split()) / 1024, 2)
            self.spitze = max(self.spitze or 0, gb)
        except (OSError, ValueError, subprocess.SubprocessError):
            pass

    def __enter__(self):
        if self.prog:
            def lauf():
                while not self.stop.wait(2):
                    self.messen()
            self.messen()
            threading.Thread(target=lauf, name="amw-vram", daemon=True).start()
        return self

    def __exit__(self, *_):
        self.stop.set()


def _mehrteilig(name, roh):
    grenze = "amw" + secrets.token_hex(8)
    teile = [f"--{grenze}\r\nContent-Disposition: form-data; name=\"image\"; filename=\"{name}\"\r\n"
             f"Content-Type: application/octet-stream\r\n\r\n".encode() + roh + b"\r\n"]
    for k, w in (("overwrite", "true"), ("type", "input")):
        teile.append(f"--{grenze}\r\nContent-Disposition: form-data; name=\"{k}\"\r\n\r\n{w}\r\n".encode())
    return b"".join(teile) + f"--{grenze}--\r\n".encode(), {"Content-Type": f"multipart/form-data; boundary={grenze}"}


# --- Ausführen (im Dienst) -----------------------------------------------------------------------

def hochholen(con, versucht, jetzt=None, immer=None):
    """Nur KIs in ki_immer_an (A1649): antwortet eine davon nicht (z. B. nach einem Neustart des PCs), ohne Fenster starten,
    je KI höchstens alle HOCH_S – eine kaputte KI startet nicht im Minutentakt. Alle anderen startet erst ein Auftrag
    (bereit()). Ohne Startbefehl bleibt sie aus. versucht: {Name: Zeit des letzten Versuchs}."""
    jetzt = time.time() if jetzt is None else jetzt
    immer = immer_an() if immer is None else immer
    aus = []
    for ki in con.execute("SELECT * FROM ki WHERE aktiv = 1 AND zustand = 'aus' AND startbefehl IS NOT NULL AND startbefehl != ''").fetchall():
        if ki["name"].lower() not in immer or jetzt - versucht.get(ki["name"], 0) < HOCH_S:
            continue
        versucht[ki["name"]] = jetzt
        try:
            _starten(ki)
            aus.append(f"{ki['name']} antwortet nicht – gestartet")
        except OSError as e:
            aus.append(f"{ki['name']} antwortet nicht – Start fehlgeschlagen: {e}")
    return aus


class Arbeiter:
    """Holt KI-Aufträge ab, deren Lauf dran ist, und führt sie aus – einer zur Zeit (Platz gpu)."""

    def __init__(self, con=None):
        self.con = con or db.verbinde()
        self.geprueft = 0.0
        self.hoch = {}
        with db.schreiben(self.con):          # Neustart des Dienstes: Ollama-Aufträge neu anfragen, ComfyUI weiter abholen
            self.con.execute("UPDATE ki_auftrag SET zustand = 'wartet' WHERE zustand = 'laeuft' AND (extern IS NULL"
                             " OR ki_id IN (SELECT id FROM ki WHERE schnittstelle = 'ollama'))")

    def runde(self):
        ereignisse = []
        with db.schreiben(self.con):          # Lauf von außen beendet, bevor er dran war
            n = self.con.execute("UPDATE ki_auftrag SET zustand = 'abgebrochen', ende_utc = ? WHERE zustand IN ('wartet', 'laeuft')"
                                 " AND lauf_id IN (SELECT id FROM lauf WHERE status IN ('fertig', 'abgebrochen'))",
                                 (db.jetzt(),)).rowcount
        if n:
            ereignisse.append(f"{n} KI-Auftrag/Aufträge abgebrochen (Lauf beendet)")
        a = self.con.execute("SELECT k.* FROM ki_auftrag k JOIN lauf l ON l.id = k.lauf_id WHERE l.status = 'laeuft'"
                             " AND k.zustand IN ('wartet', 'laeuft') ORDER BY l.start_utc, l.id LIMIT 1").fetchone()
        if a:
            ereignisse.append(self.ausfuehren(a))
        if time.time() - self.geprueft >= PRUEF_S:
            self.geprueft = time.time()
            zustand_pruefen(self.con)
            ereignisse += hochholen(self.con, self.hoch)
            ereignisse += leerlauf_beenden(self.con)
        return ereignisse

    def _abbruch(self, a):
        def pruefen():
            r = self.con.execute("SELECT status FROM lauf WHERE id = ?", (a["lauf_id"],)).fetchone()
            return not r or r["status"] != "laeuft"
        return pruefen

    def _setzen(self, aid, **felder):
        with db.schreiben(self.con):
            self.con.execute(f"UPDATE ki_auftrag SET {', '.join(k + ' = ?' for k in felder)} WHERE id = ?", (*felder.values(), aid))

    def ausfuehren(self, a):
        ki = self.con.execute("SELECT * FROM ki WHERE id = ?", (a["ki_id"],)).fetchone()
        abbruch = self._abbruch(a)
        start = time.time()
        if a["zustand"] == "wartet":
            self._setzen(a["id"], zustand="laeuft", start_utc=a["start_utc"] or db.jetzt(), fehler=None)
        self._belegt(ki, True)
        fertig, fehler = [], None
        try:
            with VramMesser() as vram:
                version = bereit(ki, abbruch)
                if ki["schnittstelle"] == "ollama":
                    fertig = self._ollama(ki, a, version, abbruch, vram)
                else:
                    fertig = self._comfyui(ki, a, version, abbruch, vram)
        except KiFehler as e:
            fehler = str(e)
        except kern.AmwFehler as e:
            fehler = str(e)
        except Exception as e:                                      # noqa: BLE001 – nie den Dienst stören
            log.exception("KI-Auftrag %s", a["id"])
            fehler = f"{type(e).__name__}: {e}"
        finally:
            self._belegt(ki, False)
        return self._abschluss(ki, a, fertig, fehler, abbruch(), time.time() - start)

    def _belegt(self, ki, ja):
        with db.schreiben(self.con):
            self.con.execute("UPDATE ki SET zustand = ? WHERE id = ?", ("belegt" if ja else "an", ki["id"]))

    def _frist_min(self, a):
        return float(json.loads(a["parameter"] or "{}").get("frist_min") or FRIST_MIN)

    def _frist(self, a):
        return time.time() + self._frist_min(a) * 60

    def _ollama(self, ki, a, version, abbruch, vram):
        m = self.con.execute("SELECT * FROM ki_modell WHERE id = ?", (a["modell_id"],)).fetchone()
        digest = next((x.get("digest") for x in (_anfrage(ki["endpunkt"], "/api/tags", frist=10) or {}).get("models", [])
                       if x.get("name") == m["name"] or x.get("model") == m["name"]), None)
        if not digest:
            raise KiFehler(f"Ollama kennt {m['name']} nicht (ollama pull {m['name']} – macht ein Mensch oder Agent, nicht die AMW)")
        p = json.loads(a["parameter"] or "{}")
        for k in INTERN:
            p.pop(k, None)
        system = p.pop("system", None)
        bilder = [self._bild_b64(a)] if a["eingabe"] else []
        fertig = json.loads(a["dokumente"] or "[]")
        frist = self._frist(a)
        for i in range(len(fertig), a["anzahl"]):
            if abbruch():
                raise KiFehler("abgebrochen")
            nutz = {"model": m["name"], "prompt": a["prompt"], "stream": False, "think": False,
                    "keep_alive": 0 if i == a["anzahl"] - 1 else "2m",       # nach dem letzten: Grafikspeicher frei
                    "options": {**p, "seed": a["seed"] + i}}
            if system:
                nutz["system"] = system
            if bilder:
                nutz["images"] = bilder
            self._setzen(a["id"], fortschritt=f"{i}/{a['anzahl']} fertig – Text {i + 1} wird erzeugt")
            t0 = time.time()
            try:
                r = _anfrage(ki["endpunkt"], "/api/generate", nutz, frist=max(30, frist - time.time()),
                             abbruch=lambda: abbruch() or time.time() > frist)
            except KiFehler:
                if not abbruch() and time.time() > frist:
                    raise KiFehler(f"Frist von {self._frist_min(a):g} min erreicht") from None
                raise
            text = (r or {}).get("response", "").strip()
            if not text:
                raise KiFehler("Ollama hat keinen Text geliefert")
            name = f"ki-L{a['lauf_id']}-{i + 1}.md"
            titel = (a["titel"] or betrieb.kurzfassung(a["prompt"], 80)) + (f" ({i + 1}/{a['anzahl']})" if a["anzahl"] > 1 else "")
            did = self._ablegen(a, ki, version, m, text.encode("utf-8") + b"\n", name, titel, "ergebnis", a["seed"] + i,
                                {"modelle": [{"name": m["name"], "sha256": digest, "lizenz": m["lizenz"]}],
                                 "parameter": {**p, **({"system": system} if system else {})}, "dauer_s": time.time() - t0,
                                 "vram": vram.spitze, "gegenprobe": f"Ollama-Digest {digest[:12]}",
                                 "modell_sha256": digest})
            fertig.append(did)
            self._setzen(a["id"], dokumente=json.dumps(fertig))
        return fertig

    def _bild_b64(self, a):
        import base64
        did = int(json.loads(a["eingabe"])[0].lstrip("D"))
        roh, _ = dokumente.inhalt(self.con, a["projekt_id"], did)
        return base64.b64encode(roh).decode("ascii")

    def _comfyui(self, ki, a, version, abbruch, vram):
        v = self.con.execute("SELECT * FROM ki_vorlage WHERE id = ?", (a["vorlage_id"],)).fetchone()
        if v["sha256"] != a["vorlage_sha256"]:
            raise KiFehler(f"Vorlage {v['name']} wurde nach dem Auftrag geändert – bitte neu beauftragen")
        m = self.con.execute("SELECT * FROM ki_modell WHERE id = ?", (a["modell_id"],)).fetchone() if a["modell_id"] else None
        extern = json.loads(a["extern"] or "{}")
        ids, abgeholt = extern.get("ids", []), extern.get("abgeholt", {})
        werte = {"prompt": a["prompt"], "negativ": a["negativ"] or "", "breite": a["breite"] or 1024,
                 "hoehe": a["hoehe"] or 1024}
        if m:
            werte["modell"] = m["datei"] or m["name"]
        if a["eingabe"] and not ids:                   # Eingabebild zu ComfyUI hochladen (landet in dessen input/)
            did = int(json.loads(a["eingabe"])[0].lstrip("D"))
            roh, endung = dokumente.inhalt(self.con, a["projekt_id"], did)
            koerper, kopf = _mehrteilig(f"amw-D{did}{endung}", roh)
            r = _anfrage(ki["endpunkt"], "/upload/image", koerper, kopf=kopf)
            werte["bild"] = (r.get("subfolder") + "/" if r.get("subfolder") else "") + r["name"]
            extern["bild"] = werte["bild"]
        elif extern.get("bild"):
            werte["bild"] = extern["bild"]
        wf = _workflow(v["inhalt"])
        modelle = []
        for datei in _modell_dateien(_fuellen(wf, werte)):       # beim Ausführen noch einmal: alle frei?
            r = self.con.execute("SELECT * FROM ki_modell WHERE ki_id = ? AND (datei = ? OR name = ?)", (ki["id"], datei, datei)).fetchone()
            if not r or r["freigabe"] != "frei":
                raise KiFehler(f"Modell {datei} ist nicht (mehr) frei")
            modelle.append({"name": r["name"], "datei": datei, "sha256": r["sha256"], "lizenz": r["lizenz"]})
        if not ids:
            for i in range(a["anzahl"]):
                if abbruch():
                    raise KiFehler("abgebrochen")
                r = _anfrage(ki["endpunkt"], "/prompt", {"prompt": _fuellen(wf, {**werte, "seed": a["seed"] + i}),
                                                         "client_id": f"amw-L{a['lauf_id']}"})
                if r.get("node_errors"):
                    raise KiFehler(f"ComfyUI lehnt die Vorlage ab: {json.dumps(r['node_errors'], ensure_ascii=False)[:400]}")
                ids.append(r["prompt_id"])
                extern["ids"] = ids
                self._setzen(a["id"], extern=json.dumps(extern))
        frist = self._frist(a)
        fertig = [d for i in ids for d in abgeholt.get(i, [])]
        try:
            while len(abgeholt) < len(ids):
                if abbruch() or time.time() > frist:
                    offen = [i for i in ids if i not in abgeholt]
                    try:
                        _anfrage(ki["endpunkt"], "/queue", {"delete": offen})
                        _anfrage(ki["endpunkt"], "/interrupt", {})
                    except KiFehler:
                        pass
                    raise KiFehler("abgebrochen" if abbruch() else f"Frist von {self._frist_min(a):g} min erreicht")
                for n, pid_ in enumerate(ids):
                    if pid_ in abgeholt:
                        continue
                    h = (_anfrage(ki["endpunkt"], f"/history/{urllib.parse.quote(pid_)}", frist=15) or {}).get(pid_)
                    if not h:
                        continue
                    st = h.get("status") or {}
                    if st.get("status_str") == "error":
                        nachricht = next((m_[1].get("exception_message") for m_ in st.get("messages", [])
                                          if m_[0] == "execution_error"), None)
                        raise KiFehler(f"ComfyUI-Fehler bei Bild {n + 1}: {nachricht or 'unbekannt'}")
                    if not st.get("completed", bool(h.get("outputs"))):
                        continue
                    zeiten = {m_[0]: (m_[1] or {}).get("timestamp") for m_ in st.get("messages", []) if isinstance(m_, list)}
                    dauer = ((zeiten["execution_success"] - zeiten["execution_start"]) / 1000
                             if zeiten.get("execution_success") and zeiten.get("execution_start") else None)
                    neu = []
                    for ausgabe in (h.get("outputs") or {}).values():
                        for b in ausgabe.get("images", []):
                            if b.get("type", "output") != "output":
                                continue
                            q = urllib.parse.urlencode({"filename": b["filename"], "subfolder": b.get("subfolder", ""),
                                                        "type": "output"})
                            roh = _anfrage(ki["endpunkt"], f"/view?{q}", roh=True, frist=60)
                            seed = a["seed"] + n
                            titel = (a["titel"] or betrieb.kurzfassung(a["prompt"], 70)) + f" (Seed {seed})"
                            neu.append(self._ablegen(a, ki, version, m, roh, b["filename"], titel, "bild", seed,
                                                     {"modelle": modelle, "vorlage": v, "dauer_s": dauer, "vram": vram.spitze,
                                                      "gegenprobe": gegenprobe(roh, seed),
                                                      "parameter": {"breite": werte["breite"], "hoehe": werte["hoehe"],
                                                                    "prompt_id": pid_}}))
                    abgeholt[pid_] = neu
                    fertig += neu
                    extern["abgeholt"] = abgeholt
                    self._setzen(a["id"], extern=json.dumps(extern), dokumente=json.dumps(fertig))
                self._setzen(a["id"], fortschritt=f"{len(abgeholt)}/{len(ids)} Bilder fertig")
                if len(abgeholt) < len(ids):
                    time.sleep(2)
        finally:
            try:
                _anfrage(ki["endpunkt"], "/free", {"unload_models": True, "free_memory": True}, frist=30)
            except KiFehler as e:
                log.warning("KI %s: /free ging nicht: %s", ki["name"], e)
        return fertig

    def _ablegen(self, a, ki, version, m, roh, name, titel, art, seed, h):
        """Dokument + Herkunft in derselben Reihenfolge wie die Bilder; ohne Bezug, wenn die Aufgabe fehlt."""
        endung = os.path.splitext(name)[1].lower()
        if endung not in dokumente.FORMATE:
            name += ".png" if roh[:8] == b"\x89PNG\r\n\x1a\n" else ".txt"
        notiz = f"von der AMW abgelegt: KI-Lauf L{a['lauf_id']} ({ki['name']}{', ' + m['name'] if m else ''}, Seed {seed})"
        did = dokumente.ablegen_inhalt(self.con, a["projekt_id"], a["auftraggeber"], roh, name, titel, art, notiz,
                                       **({"aufgabe": a["aufgabe_id"]} if a["aufgabe_id"] else {}))
        vid = self.con.execute("SELECT id FROM dokument_version WHERE dokument_id = ? AND nr = 1", (did,)).fetchone()[0]
        v = h.get("vorlage")
        with db.schreiben(self.con):
            db.einfuegen(self.con, "ki_herkunft", dokument_version_id=vid, auftrag_id=a["id"], lauf_id=a["lauf_id"], ki=ki["name"],
                         ki_version=version, ki_lizenz=ki["lizenz"], modell=m["name"] if m else None,
                         modell_datei=m["datei"] if m else None, modell_sha256=h.get("modell_sha256") or (m["sha256"] if m else None),
                         modell_lizenz=m["lizenz"] if m else None, modelle=json.dumps(h.get("modelle") or [], ensure_ascii=False),
                         vorlage=v["name"] if v else None, vorlage_sha256=v["sha256"] if v else None, prompt=a["prompt"],
                         negativ=a["negativ"], seed=seed, parameter=json.dumps(h.get("parameter") or {}, ensure_ascii=False),
                         eingabe=a["eingabe"], dauer_s=round(h["dauer_s"], 1) if h.get("dauer_s") else None,
                         vram_spitze_gb=h.get("vram"), gegenprobe=h.get("gegenprobe"), zeit_utc=db.jetzt())
        return did

    def _abschluss(self, ki, a, fertig, fehler, abgebrochen, dauer):
        pid = a["projekt_id"]
        nummern = ", ".join(f"D{d}" for d in fertig) if len(fertig) <= 6 else f"D{fertig[0]}–D{fertig[-1]}"
        zustand = "abgebrochen" if abgebrochen else "fehler" if fehler else "fertig"
        vram = self.con.execute("SELECT max(vram_spitze_gb) FROM ki_herkunft WHERE auftrag_id = ?", (a["id"],)).fetchone()[0]
        self._setzen(a["id"], zustand=zustand, fehler=fehler, ende_utc=db.jetzt(), dauer_s=round(dauer, 1), vram_spitze_gb=vram,
                     dokumente=json.dumps(fertig), fortschritt=f"{len(fertig)} Ergebnis(se)")
        einheit = "Bild(er)" if ki["schnittstelle"] == "comfyui" else "Text(e)"
        ergebnis = (f"{len(fertig)} {einheit}: {nummern}" if fertig else "kein Ergebnis") + (f" · {fehler}" if fehler else "")
        if not abgebrochen:                    # wer abgebrochen hat, hat den Lauf schon beendet
            try:
                betrieb.lauf_ende(self.con, pid, a["auftraggeber"], a["lauf_id"], 0 if not fehler else 1, ergebnis[:500])
            except kern.AmwFehler as e:
                log.warning("KI-Lauf L%s: %s", a["lauf_id"], e)
        kurz = (f"L{a['lauf_id']} fertig: {nummern} ({len(fertig)} {einheit})" if zustand == "fertig" else
                f"L{a['lauf_id']} {'abgebrochen' if abgebrochen else 'FEHLER'}: {betrieb.kurzfassung(fehler or '', 90)}"
                + (f" – trotzdem abgelegt: {nummern}" if fertig else ""))
        text = (f"KI-Auftrag {ki['name']} · {betrieb.kurzfassung(a['titel'] or a['prompt'], 100)}\n"
                f"Dauer {dauer / 60:.1f} min" + (f" · Grafikspeicher bis {vram:g} GB" if vram else "")
                + (f"\nErgebnisse: {', '.join(f'D{d}' for d in fertig)} (Herkunft: amw ki zeige L{a['lauf_id']})" if fertig else "")
                + (f"\nFehler: {fehler}" if fehler and not abgebrochen else ""))
        with db.schreiben(self.con):
            kern._posten(self.con, pid, "AMW", a["auftraggeber"], "meldung", kurz, text, aufgabe_id=a["aufgabe_id"])
        return kurz


def zustand_pruefen(con):
    """an/aus je KI; bei Ollama auch, welche Modelle gerade im Grafikspeicher liegen. Startet nichts."""
    for ki in con.execute("SELECT * FROM ki WHERE aktiv = 1 AND schnittstelle IN ('ollama', 'comfyui')").fetchall():
        if ki["zustand"] == "belegt":
            continue
        geladen, version = None, None
        try:
            version = _version(ki, _anfrage(ki["endpunkt"], _version_weg(ki), frist=3))
            neu = "an"
            if ki["schnittstelle"] == "ollama":
                geladen = json.dumps([x.get("name") for x in (_anfrage(ki["endpunkt"], "/api/ps", frist=3) or {}).get("models", [])])
        except KiFehler:
            neu = "aus"
        with db.schreiben(con):
            con.execute("UPDATE ki SET zustand = ?, geladen = ?, geprueft_utc = ?, version = coalesce(?, version) WHERE id = ?",
                        (neu, geladen, db.jetzt(), version, ki["id"]))


def arbeiten(stop=None):
    """Faden im Dienst: KI-Aufträge ausführen. Fehler stören nie den Wächter."""
    a = None
    while not (stop and stop.is_set()):
        try:
            a = a or Arbeiter()
            for e in a.runde():
                log.info("KI: %s", e)
        except Exception as e:                                      # noqa: BLE001
            log.warning("KI-Arbeiter: %s: %s", type(e).__name__, e)
        time.sleep(TAKT_S)


def starten():
    f = threading.Thread(target=arbeiten, name="ki", daemon=True)
    f.start()
    return f


# --- KI-Fenster (--nachts) -----------------------------------------------------------------------

def fenster():
    """(Anfang, Ende) in Minuten nach Mitternacht (Ortszeit) aus der PC-Einstellung ki_fenster, None = kein Fenster."""
    from . import einstellungen
    v = einstellungen.wert("ki_fenster")
    if not v:
        return None
    a, b = (int(x[:2]) * 60 + int(x[3:]) for x in v.split("-"))
    return a, b


_LESEN = object()          # Fenster aus der PC-Einstellung lesen (None heißt: kein Fenster)


def fenster_text(f=_LESEN):
    f = fenster() if f is _LESEN else f
    return f"{f[0] // 60:02d}:{f[0] % 60:02d}–{f[1] // 60:02d}:{f[1] % 60:02d} Uhr" if f else "kein Fenster"


def im_fenster(jetzt=None, f=_LESEN):
    f = fenster() if f is _LESEN else f
    if not f:
        return True
    t = (jetzt or datetime.datetime.now()).astimezone()
    m = t.hour * 60 + t.minute
    a, b = f
    return a <= m < b if a < b else (m >= a or m < b)


def testtermin_vorrang(con, jetzt=None):
    """Text, wenn gerade (PC-weit, in irgendeinem Projekt) die Vorlaufzeit eines Testtermins oder der Termin selbst läuft."""
    from . import termine
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    for t in con.execute("SELECT * FROM termin WHERE art = 'test' AND status = 'geplant'").fetchall():
        vorlauf = datetime.timedelta(hours=t["vorlauf_h"] or 0)    # ohne Vorlauf: nur während des Termins selbst
        for v in termine._vorkommen_eines(t, jetzt - datetime.timedelta(hours=12), jetzt + vorlauf):
            am = termine._dt(v["am_utc"])
            if not am - vorlauf <= jetzt < am + datetime.timedelta(minutes=t["dauer_min"] or 60):
                continue
            if con.execute("SELECT 1 FROM termin_meldung WHERE termin_id = ? AND am_utc = ? AND art = 'abgesagt'",
                           (t["id"], v["am_utc"])).fetchone():
                continue
            return f"Testtermin „{t['titel']}“ ({am.astimezone():%d.%m. %H:%M}) hat Vorrang"
    return None


def nacht_sperre(con, jetzt=None):
    """Warum ein KI-Auftrag mit --nachts jetzt nicht starten darf (Text), sonst None."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    f = fenster()
    if not im_fenster(jetzt, f):
        return f"wartet auf das KI-Fenster {fenster_text(f)} (--nachts)"
    return testtermin_vorrang(con, jetzt)


def nachts_wartend(con):
    """KI-Aufträge mit --nachts, die noch warten: (Zahl, geschätzte Sekunden aus der Modell-Probe)."""
    r = con.execute("SELECT count(*), sum(coalesce(m.sekunden, 0) * a.anzahl) FROM ki_auftrag a JOIN lauf l ON l.id = a.lauf_id"
                    " LEFT JOIN ki_modell m ON m.id = a.modell_id WHERE l.status = 'angemeldet'"
                    " AND json_extract(a.parameter, '$.nachts') = 1").fetchone()
    return r[0], round(r[1] or 0)


# --- Ansicht und Nachweis ------------------------------------------------------------------------

def uebersicht(con, pid):
    """Für Workbench/online (Betrieb → KI): ohne Startbefehl und Ordner."""
    kis = [dict(r) for r in con.execute("SELECT id, name, art, schnittstelle, endpunkt, version, lizenz, vram_gb, zustand,"
                                        " zustand_text, geladen, geprueft_utc FROM ki WHERE aktiv = 1 ORDER BY name")]
    immer, gestartet, minuten = immer_an(), gestartet_laden(), leerlauf_min()
    for k in kis:
        k["geladen"] = json.loads(k["geladen"] or "[]")
        if k["schnittstelle"] != "befehl":                # Betrieb (A1649): immer an / bei Bedarf, ob die AMW sie gestartet hat
            k["betrieb"] = "immer" if k["name"].lower() in immer else "bedarf"
            k["von_amw"] = k["name"].lower() in gestartet
            k["leerlauf_min"] = minuten
        k["wartend"] = con.execute("SELECT count(*) FROM ki_auftrag a JOIN lauf l ON l.id = a.lauf_id WHERE a.ki_id = ?"
                                   " AND l.status = 'angemeldet'", (k["id"],)).fetchone()[0]
        k["darf"] = [r[0] for r in con.execute("SELECT wer FROM ki_recht WHERE projekt_id = ? AND ki_id = ? ORDER BY wer", (pid, k["id"]))]
    modelle = [dict(r) for r in con.execute(
        "SELECT m.id, k.name AS ki, m.name, m.datei, m.version, m.lizenz, m.nutzungsregeln, m.kommerziell, m.freigabe,"
        " m.freigabe_grund, m.freigabe_von, m.freigabe_utc, m.vram_gb, m.sekunden FROM ki_modell m JOIN ki k ON k.id = m.ki_id"
        " WHERE k.aktiv = 1 ORDER BY k.name, m.freigabe != 'frei', m.name")]
    vorlagen = [dict(r) for r in con.execute("SELECT k.name AS ki, v.name, v.beschreibung, v.von, v.stand_utc FROM ki_vorlage v"
                                             " JOIN ki k ON k.id = v.ki_id WHERE v.projekt_id = ? AND v.aktiv = 1 ORDER BY k.name, v.name", (pid,))]
    auftraege = [dict(r) for r in con.execute(
        "SELECT a.id, a.lauf_id, k.name AS ki, m.name AS modell, v.name AS vorlage, a.auftraggeber, a.aufgabe_id, a.titel,"
        " a.prompt, a.anzahl, a.seed, a.zustand, a.fortschritt, a.dokumente, a.fehler, a.angelegt_utc, a.start_utc, a.ende_utc,"
        " a.dauer_s, a.vram_spitze_gb, l.status AS lauf_status FROM ki_auftrag a JOIN ki k ON k.id = a.ki_id"
        " JOIN lauf l ON l.id = a.lauf_id LEFT JOIN ki_modell m ON m.id = a.modell_id LEFT JOIN ki_vorlage v ON v.id = a.vorlage_id"
        " WHERE a.projekt_id = ? ORDER BY a.id DESC LIMIT 30", (pid,))]
    for x in auftraege:
        x["dokumente"] = json.loads(x["dokumente"] or "[]")
        x["prompt"] = betrieb.kurzfassung(x["prompt"], 200)
    return {"kis": kis, "modelle": modelle, "vorlagen": vorlagen, "auftraege": auftraege}


def herkunft_von(con, pid, did):
    """Herkunft je Version eines Dokuments (leer, wenn keine KI beteiligt war)."""
    return [dict(r) for r in con.execute(
        "SELECT v.nr, h.* FROM ki_herkunft h JOIN dokument_version v ON v.id = h.dokument_version_id"
        " JOIN dokument d ON d.id = v.dokument_id WHERE d.id = ? AND d.projekt_id = ? ORDER BY v.nr", (did, pid))]


VERMERKE = ("ausgewaehlt", "verworfen", "nachbearbeitet")
VERMERK_TEXT = {"ausgewaehlt": "ausgewählt", "verworfen": "verworfen", "nachbearbeitet": "nachbearbeitet"}
VERMERK_TEXT_MAX = 2000


def vermerk_art(art):
    """„ausgewählt“, „Ausgewaehlt “ … → ausgewaehlt; AmwFehler bei unbekannter Art."""
    a = (art or "").strip().lower().replace("ä", "ae")
    if a not in VERMERKE:
        raise kern.AmwFehler(f"Vermerk: {' | '.join(VERMERKE)}")
    return a


def vermerken(con, pid, von, dokument, art, text=None, kanal="cli"):
    """Vermerk an einem KI-Ergebnis (Agent des Projekts, Lead oder Entwickler). nachbearbeitet braucht den Text, was von
    Hand geändert wurde – das ist der Nachweis der menschlichen Gestaltungsentscheidung. Rückgabe: id."""
    art = vermerk_art(art)
    text = (text or "").strip() or None
    if art == "nachbearbeitet" and (not text or len(text) < 5):
        raise kern.AmwFehler("nachbearbeitet: --text angeben – was wurde von Hand geändert? (Nachweis für das Urheberrecht)")
    if text and len(text) > VERMERK_TEXT_MAX:
        raise kern.AmwFehler(f"Vermerk länger als {VERMERK_TEXT_MAX} Zeichen")
    if text and dokumente.GEHEIM.search(text):
        raise kern.AmwFehler("Der Text enthält etwas, das wie ein Schlüssel aussieht – nicht vermerkt")
    try:
        did = int(str(dokument).strip().lstrip("Dd"))
    except ValueError:
        raise kern.AmwFehler(f"Dokument „{dokument}“: D<nr>") from None
    with db.schreiben(con):                       # prüfen und anhängen in einem Zug
        return _vermerk_anlegen(con, pid, von, did, art, text, kanal)


def _vermerk_anlegen(con, pid, von, did, art, text, kanal):
    if von not in (kern.ENTWICKLER, db.produkt_entwickler()):
        kern.agent_zeile(con, pid, von)
    d = con.execute("SELECT id, status FROM dokument WHERE id = ? AND projekt_id = ?", (did, pid)).fetchone()
    if not d:
        raise kern.AmwFehler(f"D{did} gibt es nicht")
    if d["status"] == "geloescht":
        raise kern.AmwFehler(f"D{did} ist gelöscht")
    if not con.execute("SELECT 1 FROM ki_herkunft h JOIN dokument_version v ON v.id = h.dokument_version_id"
                       " WHERE v.dokument_id = ?", (did,)).fetchone():
        raise kern.AmwFehler(f"D{did} hat keine KI-Herkunft – Vermerke gibt es nur an KI-Ergebnissen")
    nr = con.execute("SELECT max(nr) FROM dokument_version WHERE dokument_id = ?", (did,)).fetchone()[0]
    return db.einfuegen(con, "ki_vermerk", projekt_id=pid, dokument_id=did, version_nr=nr, art=art, text=text, von=von,
                        kanal=kanal, zeit_utc=db.jetzt())


def vermerke_von(con, pid, did):
    """Alle Vermerke eines Dokuments, älteste zuerst."""
    return [dict(r) for r in con.execute("SELECT id, version_nr, art, text, von, kanal, zeit_utc FROM ki_vermerk"
                                         " WHERE dokument_id = ? AND projekt_id = ? ORDER BY id", (did, pid))]


def vermerk_stand(vermerke):
    """(jüngster Entscheid ausgewaehlt|verworfen als Zeile oder None, Liste der Nachbearbeitungen)."""
    wahl = next((v for v in reversed(vermerke) if v["art"] in ("ausgewaehlt", "verworfen")), None)
    return wahl, [v for v in vermerke if v["art"] == "nachbearbeitet"]


def nachweis(con, pid, aufgabe=None, bogen=None, alle=False):
    """Alle Dokumente mit KI-Herkunft (für Steam-Angabe und ASSET_SOURCES) – Zeilen als dict."""
    sql = ("SELECT d.id AS dokument, d.titel, d.status, d.art, d.bezug_art, d.bezug_id, v.nr AS version, h.ki, h.ki_version,"
           " h.modell, h.modell_lizenz, h.modelle, h.vorlage, h.seed, h.lauf_id, h.zeit_utc, h.gegenprobe, h.prompt"
           " FROM ki_herkunft h JOIN dokument_version v ON v.id = h.dokument_version_id JOIN dokument d ON d.id = v.dokument_id"
           " WHERE d.projekt_id = ?")
    werte = [pid]
    if not alle:
        sql += " AND d.status = 'aktuell'"
    if aufgabe:
        sql += " AND d.bezug_art = 'aufgabe' AND d.bezug_id = ?"
        werte.append(aufgabe)
    if bogen:
        sql += (" AND ((d.bezug_art = 'bogen' AND d.bezug_id = ?) OR (d.bezug_art = 'aufgabe' AND d.bezug_id IN"
                " (SELECT id FROM aufgabe WHERE bogen_id = ?)))")
        werte += [bogen, bogen]
    zeilen = [dict(r) for r in con.execute(sql + " ORDER BY d.id, v.nr", werte)]
    stand = {}
    for z in zeilen:
        if z["dokument"] not in stand:
            stand[z["dokument"]] = vermerk_stand(vermerke_von(con, pid, z["dokument"]))
        wahl, nach = stand[z["dokument"]]
        z["entscheid"] = wahl["art"] if wahl else None
        z["entscheid_von"] = f"{wahl['von']} {wahl['zeit_utc'][:10]}" if wahl else None
        z["nachbearbeitet"] = [f"{v['von']} {v['zeit_utc'][:10]}: {v['text']}" for v in nach]
        b = con.execute("SELECT beleg FROM aufgabe WHERE id = ? AND status = 'fertig'", (z["bezug_id"],)).fetchone() \
            if z["bezug_art"] == "aufgabe" else None
        z["beleg"] = b["beleg"] if b else None
    return zeilen


def nachweis_text(zeilen):
    if not zeilen:
        return "Keine Dokumente mit KI-Herkunft.\n"
    lizenzen = {}
    for z in zeilen:
        for m in json.loads(z["modelle"] or "[]") or [{"name": z["modell"], "lizenz": z["modell_lizenz"]}]:
            lizenzen.setdefault(m.get("name") or m.get("datei"), m.get("lizenz") or "?")
    aus = ["# KI-Nachweis", "", f"{len(zeilen)} Dokument(e) mit KI-Herkunft (Inhalte vorab erzeugt, „pre-generated“).", "",
           "## Modelle und Lizenzen", ""]
    aus += [f"- {n}: {l}" for n, l in sorted(lizenzen.items(), key=lambda x: str(x[0]))]
    entscheid = lambda z: z.get("entscheid")
    aus += ["", f"Ausgewählt: {sum(1 for z in zeilen if entscheid(z) == 'ausgewaehlt')}"
                f" · verworfen: {sum(1 for z in zeilen if entscheid(z) == 'verworfen')}"
                f" · ohne Entscheid: {sum(1 for z in zeilen if not entscheid(z))}"
                f" · von Hand nachbearbeitet: {sum(1 for z in zeilen if z.get('nachbearbeitet'))}"]
    zelle = lambda x: " ".join(str(x or "").replace("|", "/").split())
    aus += ["", "## Dokumente", "", "| D | Titel | Status | KI | Modell | Seed | Lauf | Gegenprobe | Entscheid | Nachbearbeitet | Beleg |",
            "|---|---|---|---|---|---|---|---|---|---|---|"]
    for z in zeilen:
        e = f"{VERMERK_TEXT[entscheid(z)]} ({z['entscheid_von']})" if entscheid(z) else ""
        aus.append(f"| D{z['dokument']} v{z['version']} | {zelle(z['titel'])} | {z['status']} | {z['ki']} {z['ki_version'] or ''}"
                   f" | {zelle(z['modell'] or z['vorlage'])} | {z['seed'] if z['seed'] is not None else ''} | L{z['lauf_id']}"
                   f" | {zelle(z['gegenprobe'])} | {zelle(e)} | {zelle('; '.join(z.get('nachbearbeitet') or []))}"
                   f" | {zelle(z.get('beleg'))} |")
    return "\n".join(aus) + "\n"
