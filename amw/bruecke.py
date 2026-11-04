"""Datei-Brücke für Sitzungen, die amw.db nicht direkt öffnen können (→ doc/architektur.md „Datei-Brücke“).

Der TL arbeitet in einer Linux-VM, F:\\amw ist dort per FUSE eingehängt; SQLite im WAL-Modus scheitert darüber
(„disk I/O error“). Darum:
- Lesen: Der Wächter schreibt höchstens jede Minute (nur nach Änderungen) eine Kopie ohne WAL nach
  daten/tl_lesen.db (journal_mode=DELETE). Lesen mit `file:…/tl_lesen.db?immutable=1`. Stand in daten/tl_lesen.stand.
- Schreiben: Befehlsdateien eingang-tl/befehle/*.json (erst als .tmp schreiben, dann umbenennen). Inhalt entweder
  {"args": ["posten", "--an", "CC1", "--art", "auftrag", "--kurz", "…"]} oder
  {"befehl": "posten", "an": "CC1", "art": "auftrag", "kurz": "…"} (Schlüssel = CLI-Optionen; "aktion", "kennung",
  "schluessel", "id"/"ids" sind die Positionsangaben, bei spec/rueckblick auch "bogen" und "teil"). `--datei` nur aus
  eingang-tl/ (sonst könnte ein Befehl beliebige Dateien dieses PCs in die Datenbank und online holen). Der Wächter führt sie als `--von TL` aus und legt Ergebnis + Befehl in eingang-tl/erledigt/.
Vertrauensmodell wie die CLI in Stufe 1: wer auf diesem PC Dateien schreiben kann, kann auch `amw --von TL` aufrufen.
"""
import contextlib
import io
import json
import logging
import os
import re
import sqlite3
import sys
import threading
import time

from . import cli, db

log = logging.getLogger("amw.bruecke")

WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
EINGANG = os.path.join(WURZEL, "eingang-tl")
KOPIE_S = 60
BEFEHLE_S = 5
VON = "TL"
ERLAUBT = {"posten", "lesen", "erledigt", "aufgabe", "frage", "halt", "weiter", "kontext", "regeln", "lauf", "pruefung", "taetigkeit",
           "hinweis", "rezept", "wortlaut", "beschluss", "regel", "notiz", "release", "agent",
           "leitbild", "bogen", "spec", "schritt", "risiko", "plan", "rueckblick", "verlauf", "dokument",
           "schirm"}   # Freigaben: nur der Mensch (Schirm frei: der Lead auf Marcels Wort, B2419)


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


def argumente(befehl, eingang=EINGANG):
    """Befehlsdatei → Argumente für cli.main; wirft ValueError bei Unerlaubtem."""
    if "args" in befehl:
        args = [str(x) for x in befehl["args"]]
    else:
        b = dict(befehl)
        args = [str(b.pop("befehl", ""))]
        if "aktion" in b:
            args.append(str(b.pop("aktion")))
        if args[0] == "taetigkeit" and "text" in b:      # bei taetigkeit ist der Text die Positionsangabe
            args.append(str(b.pop("text")))
        if args[0] in ("spec", "rueckblick"):            # dort ist der Bogen die Positionsangabe (sonst --bogen)
            for k in ("bogen", "teil"):
                if k in b:
                    args.append(str(b.pop(k)))
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
    if args[0] == "agent" and len(args) > 1 and args[1] in ("starten", "beenden", "profil", "startskript"):
        raise ValueError("Agenten starten, beenden und Profile ändern geht nur am PC (Workbench)")
    if args[0] == "lauf" and len(args) > 1 and args[1] == "warte":
        raise ValueError("lauf warte blockiert – über die Brücke: lauf zeige <nr>")
    if any(a in ("--von", "--projekt") for a in args):
        raise ValueError("--von/--projekt setzt die Brücke selbst")
    if args[0] == "schirm":                                # beim Schirm ist --quelle der Kanal, nicht der Inhalt
        if "--quelle" in args:
            raise ValueError("--quelle setzt beim Schirm die Brücke selbst")
        args = args + ["--quelle", "bruecke"]
    for i, a in enumerate(args):
        if a.startswith("--datei="):
            raise ValueError("--datei bitte als eigenen Schlüssel angeben")
        if a.startswith("--anhang="):
            raise ValueError("--anhang bitte als eigenen Schlüssel angeben")
        if a == "--datei" and i + 1 < len(args):           # relativ zu eingang-tl/, wird absolut weitergegeben
            args[i + 1] = _im_eingang(eingang, args[i + 1], "--datei")
        if a == "--anhang" and i + 1 < len(args):          # A=datei (aus eingang-tl/) oder A=D12
            kenn, _, ref = args[i + 1].partition("=")
            if not re.fullmatch(r"[Dd]?\d+", ref.strip()):
                args[i + 1] = f"{kenn}={_im_eingang(eingang, ref.strip(), '--anhang')}"
    # Dateien nur über --datei (geprüft): sonst ginge eine Positionsangabe an der Prüfung vorbei
    if args[0] == "dokument" and len(args) > 1 and args[1] in ("ablegen", "version"):
        try:
            with contextlib.redirect_stderr(io.StringIO()):
                ns = cli.parser().parse_args(args)
        except SystemExit:
            ns = None                                      # falsch aufgerufen – meldet der Befehl selbst
        if ns is not None and (args[1] == "ablegen" and ns.nr or args[1] == "version" and ns.pfad):
            raise ValueError("Dateien über die Brücke nur mit --datei aus eingang-tl/")
    return args + ["--von", VON]


def _im_eingang(eingang, rel, schalter):
    wurzel = os.path.realpath(eingang)
    pfad = os.path.realpath(os.path.join(wurzel, rel))
    if os.path.commonpath([wurzel, pfad]) != wurzel:
        raise ValueError(f"{schalter} über die Brücke nur aus eingang-tl/ (z. B. \"plan/spec-3.md\")")
    return pfad


def puls(kennung=None, taetigkeit=None):
    """Brücken-Sitzung des TL: ohne Postfach (schluessel_datei leer), der Wächter weckt sie nie; zeigt „läuft“."""
    con = db.verbinde()
    try:
        a = con.execute("SELECT id FROM agent WHERE kennung = ? ORDER BY id LIMIT 1", (kennung or VON,)).fetchone()
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
    """Ein Befehl im Dienst: nie auf Eingabe warten (stdin leer), jeder Fehler wird zum Ergebnis mit rc 1."""
    aus, fehler = io.StringIO(), io.StringIO()
    stdin = sys.stdin
    sys.stdin = io.StringIO()                             # input() → EOFError statt Warten
    try:
        with contextlib.redirect_stdout(aus), contextlib.redirect_stderr(fehler):
            try:
                rc = cli.main(args)
            except SystemExit as e:                       # argparse-Fehler
                rc = e.code if isinstance(e.code, int) else 2
            except Exception as e:                        # z. B. Pflichtfeld leer (IntegrityError), EOFError
                print(f"FEHLER: {type(e).__name__}: {e}", file=sys.stderr)
                rc = 1
    finally:
        sys.stdin = stdin
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
            puls(taetigkeit=taetigkeit)                   # zuerst: die Sitzung lebt, bevor der Befehl sie braucht
            if befehl.get("befehl") == "puls":           # nur Lebenszeichen (Stundentakt des TL)
                args, rc, aus, fehler = ["puls"], 0, "Puls gesetzt\n", ""
            else:
                args = argumente(befehl, eingang)
                rc, aus, fehler = ausfuehren(args)
        except (ValueError, OSError) as e:
            args, rc, aus, fehler = None, 2, "", str(e)
        except Exception as e:                            # nie die Warteschlange anhalten: Fehler wird zum Ergebnis
            args, rc, aus, fehler = None, 1, "", f"{type(e).__name__}: {e}"
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
