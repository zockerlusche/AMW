"""Datei-Brücke für Sitzungen, die amw.db nicht direkt öffnen können (→ doc/11 §3, TL-Übergabe 01.11. 12:35).

Der TL arbeitet in einer Linux-VM, F:\\amw ist dort per FUSE eingehängt; SQLite im WAL-Modus scheitert darüber
(„disk I/O error“). Darum:
- Lesen: Der Wächter schreibt höchstens jede Minute (nur nach Änderungen) eine Kopie ohne WAL nach
  daten/tl_lesen.db (journal_mode=DELETE). Lesen mit `file:…/tl_lesen.db?immutable=1`. Stand in daten/tl_lesen.stand.
- Schreiben: Befehlsdateien eingang-tl/befehle/*.json (erst als .tmp schreiben, dann umbenennen). Inhalt entweder
  {"args": ["posten", "--an", "CC1", "--art", "auftrag", "--kurz", "…"]} oder
  {"befehl": "posten", "an": "CC1", "art": "auftrag", "kurz": "…"} (Schlüssel = CLI-Optionen; "aktion", "kennung",
  "schluessel", "id"/"ids" sind die Positionsangaben). Der Wächter führt sie als `--von TL` aus und legt Ergebnis + Befehl in eingang-tl/erledigt/.
Vertrauensmodell wie die CLI in Stufe 1: wer auf diesem PC Dateien schreiben kann, kann auch `amw --von TL` aufrufen.
"""
import contextlib
import io
import json
import logging
import os
import sqlite3
import threading
import time

from . import cli, db

log = logging.getLogger("amw.bruecke")

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EINGANG = os.path.join(WURZEL, "eingang-tl")
KOPIE_S = 60
BEFEHLE_S = 5
VON = "TL"
ERLAUBT = {"posten", "lesen", "erledigt", "aufgabe", "frage", "halt", "weiter", "kontext", "regeln", "pruefung",
           "hinweis", "rezept", "wortlaut", "beschluss", "regel", "notiz", "release", "agent"}


def lese_kopie(quelle=None, ziel=None):
    """Kopie ohne WAL; ersetzt die alte erst, wenn die neue fertig ist."""
    quelle = quelle or db.db_pfad()
    ziel = ziel or os.path.join(os.path.dirname(quelle), "tl_lesen.db")
    neu = ziel + ".neu"
    if os.path.exists(neu):
        os.remove(neu)
    q = sqlite3.connect(f"file:{quelle}?mode=ro", uri=True, timeout=30)
    try:
        q.execute("VACUUM INTO ?", (neu,))
        stand = q.execute("SELECT max(id) FROM nachricht").fetchone()[0]
    finally:
        q.close()
    k = sqlite3.connect(neu)
    k.execute("PRAGMA journal_mode = DELETE")
    k.close()
    for _ in range(10):                                  # liest gerade jemand die alte Kopie, kurz warten
        try:
            os.replace(neu, ziel)
            break
        except PermissionError:
            time.sleep(1)
    else:
        raise OSError(f"{ziel} ist gesperrt")
    with open(ziel[:-3] + ".stand", "w", encoding="utf-8") as f:
        f.write(f"{db.jetzt()} neueste Nachricht #{stand}\n")
    return stand


def argumente(befehl):
    """Befehlsdatei → Argumente für cli.main; wirft ValueError bei Unerlaubtem."""
    if "args" in befehl:
        args = [str(x) for x in befehl["args"]]
    else:
        b = dict(befehl)
        args = [str(b.pop("befehl", ""))]
        if "aktion" in b:
            args.append(str(b.pop("aktion")))
        for k in ("kennung", "schluessel", "id", "ids"):
            if k in b:
                v = b.pop(k)
                args += [str(x) for x in (v if isinstance(v, list) else [v])]
        for k, v in b.items():
            name = "--" + k.replace("_", "-")
            if v is True:
                args.append(name)
            elif v not in (None, False):
                for x in (v if isinstance(v, list) else [v]):
                    args += [name, str(x)]
    if not args or args[0] not in ERLAUBT:
        raise ValueError(f"Befehl „{args[0] if args else ''}“ ist über die Brücke nicht erlaubt; erlaubt: {', '.join(sorted(ERLAUBT))}")
    if any(a in ("--von", "--projekt") for a in args):
        raise ValueError("--von/--projekt setzt die Brücke selbst")
    return args + ["--von", VON]


def puls(kennung=VON, taetigkeit=None):
    """Brücken-Sitzung des TL: ohne Postfach (schluessel_datei leer), der Wächter weckt sie nie; zeigt „läuft“."""
    con = db.verbinde()
    try:
        a = con.execute("SELECT id FROM agent WHERE kennung = ? ORDER BY id LIMIT 1", (kennung,)).fetchone()
        if not a:
            return
        t = db.jetzt()
        with db.schreiben(con):
            s = con.execute("SELECT id FROM sitzung WHERE agent_id = ? AND zustand = 'aktiv' AND schluessel_datei IS NULL",
                            (a["id"],)).fetchone()
            if s:
                con.execute("UPDATE sitzung SET letzter_puls_utc = ?, taetigkeit = coalesce(?, taetigkeit) WHERE id = ?",
                            (t, taetigkeit, s["id"]))
            else:
                db.einfuegen(con, "sitzung", agent_id=a["id"], arbeitsordner="brücke", gestartet_utc=t,
                             letzter_puls_utc=t, taetigkeit=taetigkeit)
    finally:
        con.close()


def ausfuehren(args):
    aus, fehler = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(fehler):
        try:
            rc = cli.main(args)
        except SystemExit as e:                           # argparse-Fehler
            rc = e.code if isinstance(e.code, int) else 2
    return rc, aus.getvalue(), fehler.getvalue()


def befehle(eingang=EINGANG):
    """Alle fertigen Befehlsdateien abarbeiten; Rückgabe: Anzahl."""
    ordner, erledigt = os.path.join(eingang, "befehle"), os.path.join(eingang, "erledigt")
    os.makedirs(ordner, exist_ok=True)
    os.makedirs(erledigt, exist_ok=True)
    n = 0
    for name in sorted(os.listdir(ordner)):
        pfad = os.path.join(ordner, name)
        if not name.endswith(".json") or time.time() - os.path.getmtime(pfad) < 1:
            continue
        stamm = name[:-5]
        try:
            with open(pfad, encoding="utf-8") as f:
                befehl = json.load(f)
            if not isinstance(befehl, dict):
                raise ValueError("Befehlsdatei muss ein JSON-Objekt sein")
            taetigkeit = befehl.pop("taetigkeit", None)   # optional: was der TL gerade tut (zeigt die Workbench)
            if befehl.get("befehl") == "puls":           # nur Lebenszeichen (Stundentakt des TL)
                args, rc, aus, fehler = ["puls"], 0, "Puls gesetzt\n", ""
            else:
                args = argumente(befehl)
                rc, aus, fehler = ausfuehren(args)
            puls(taetigkeit=taetigkeit)
        except (ValueError, OSError) as e:
            args, rc, aus, fehler = None, 2, "", str(e)
        ergebnis = {"datei": name, "zeit_utc": db.jetzt(), "args": args, "rc": rc, "ausgabe": aus, "fehler": fehler}
        with open(os.path.join(erledigt, stamm + ".ergebnis.json"), "w", encoding="utf-8") as f:
            json.dump(ergebnis, f, ensure_ascii=False, indent=1)
        os.replace(pfad, os.path.join(erledigt, name))
        log.info("Brücke: %s → rc %s", name, rc)
        n += 1
    return n


def schleife(stop=None):
    con = db.verbinde(nur_lesen=True)
    stand, letzte_kopie = None, 0.0
    while not (stop and stop.is_set()):
        try:
            befehle()
            v = con.execute("PRAGMA data_version").fetchone()[0]
            if (v != stand or not os.path.exists(os.path.join(os.path.dirname(db.db_pfad()), "tl_lesen.db"))) \
                    and time.time() - letzte_kopie >= KOPIE_S:
                lese_kopie()
                stand, letzte_kopie = v, time.time()
        except Exception as e:                            # nie den Wächter stören
            log.warning("Brücke: %s: %s", type(e).__name__, e)
        time.sleep(BEFEHLE_S)


def starten():
    f = threading.Thread(target=schleife, name="bruecke", daemon=True)
    f.start()
    return f
