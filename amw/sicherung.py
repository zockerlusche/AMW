"""Sicherung (A1929, TH158 Ebene 2, Marcel W2453): Die AMW schiebt einmal am Tag ALLE Zweige und Tags des Projekt-Repos an ein
Sicherungsziel – ohne neue Version und ohne Homepage.

- Ziel: Projekt-Einstellung sicherung_ziel (URL oder Name eines Remotes; setzen nur der Mensch im eigenen Terminal). Ohne
  Einstellung geschieht nichts. Keine Zugangsdaten in der AMW: Eine URL mit Benutzer/Passwort/Token wird abgelehnt; git
  nutzt die vorhandene Anmeldung des Menschen.
- Dienst-Runde: höchstens ein Versuch je Tag und Projekt, und nur, wenn sich die Refs seit dem letzten Push geändert haben.
- Nie mit Gewalt: kein --force, kein --prune, kein --mirror – am Ziel wird nichts gelöscht oder überschrieben. Ein Zweig, der
  dort nicht vorspulen kann (lokal neu aufgesetzt), wird abgewiesen und steht im Fehler; die übrigen Refs gehen trotzdem mit.
- Ergebnis als Ereignis sicherung_push (Zeit, Ziel ohne Zugangsdaten, Anzahl Refs, Stand, rc); ein Fehler als Meldung an den Lead.
- `amw sicherung jetzt` (Lead oder Mensch): ein Push von Hand, auch am selben Tag.

P408 (Betriebssicherheit, der Push läuft im Dienst):
1. Nie eine Anmeldeabfrage: git mit GIT_TERMINAL_PROMPT=0, GCM_INTERACTIVE=never (Git Credential Manager) und ssh im
   BatchMode. Fehlt die Anmeldung, scheitert der Push sofort und meldet „Anmeldung fehlt – einmal git push von Hand“.
2. Die Dienst-Runde wartet nicht: im_hintergrund() rechnet in einem eigenen Faden mit eigener Verbindung, höchstens einer zur
   Zeit, jeder Push mit Frist.
3. Ein abgewiesener Zweig wird nur EINMAL gemeldet (im Ereignis gemerkt: „gemeldet“), nicht jeden Tag.
"""
import datetime
import hashlib
import json
import os
import re
import subprocess
import threading

from . import db, kern

ART = "sicherung_push"
REMOTE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}")
SCP = re.compile(r"[A-Za-z0-9_.-]+@[A-Za-z0-9.-]+:[^\s]+")            # git@github.com:konto/repo.git (ohne Passwort)
URL = re.compile(r"(https|ssh|file)://[^\s]+")
FRIST_S = 600
ANMELDUNG = re.compile(r"Authentication failed|could not read Username|could not read Password|terminal prompts disabled|"
                       r"Permission denied \(publickey|HTTP Basic: Access denied|The requested URL returned error: 40[13]|"
                       r"Host key verification failed", re.I)
_FADEN = {"faden": None}


def umgebung():
    """P408 (1): git darf im Dienst nie nach einer Anmeldung fragen (kein Fenster, kein Hängen bis zur Frist)."""
    u = dict(os.environ, GIT_TERMINAL_PROMPT="0", GCM_INTERACTIVE="never")
    u.setdefault("GIT_SSH_COMMAND", "ssh -o BatchMode=yes")
    return u


def ziel_pruefen(v):
    """sicherung_ziel: URL (https/ssh/file), scp-Form (git@host:pfad) oder Name eines Remotes – nie mit Zugangsdaten."""
    v = str(v or "").strip()
    if not v:
        return ""
    if URL.fullmatch(v):
        if re.match(r"[a-z]+://[^/]*@", v) and not v.startswith("ssh://git@"):
            raise ValueError("keine Zugangsdaten in der URL – git nimmt die Anmeldung des Menschen")
        return v
    if SCP.fullmatch(v) or REMOTE.fullmatch(v):
        return v
    raise ValueError("URL (https://…), git@host:pfad oder Name eines Remotes")


def ziel(con, pid):
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        return ziel_pruefen(json.loads((r[0] if r else None) or "{}").get("sicherung_ziel") or "")
    except (ValueError, TypeError):
        return ""


def anzeige(z):
    """Ziel für Ereignisse und Meldungen – ohne etwaige Zugangsdaten (es gibt keine, aber sicher ist sicher)."""
    return re.sub(r"(://)[^/@]*@", r"\1", z)


def _git(ordner, *args, frist=FRIST_S):
    try:
        r = subprocess.run(["git", "-C", ordner, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           stdin=subprocess.DEVNULL, timeout=frist, env=umgebung(),
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except subprocess.TimeoutExpired:
        return 124, f"Frist {frist} s überschritten"
    return r.returncode, (r.stdout + r.stderr).strip()


def stand(ordner):
    """(Prüfsumme, Anzahl) aller lokalen Zweige und Tags."""
    rc, aus = _git(ordner, "for-each-ref", "--format=%(objectname) %(refname)", "refs/heads", "refs/tags")
    if rc != 0:
        raise kern.AmwFehler(f"Refs nicht lesbar: {aus[-200:]}")
    zeilen = sorted(z for z in aus.splitlines() if z.strip())
    return hashlib.sha256("\n".join(zeilen).encode()).hexdigest()[:16], len(zeilen)


def letzte(con, pid):
    r = con.execute("SELECT zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id DESC LIMIT 1", (pid, ART)).fetchone()
    if not r:
        return None
    try:
        return dict(json.loads(r["text"]), zeit_utc=r["zeit_utc"])
    except ValueError:
        return None


def pushen(con, pid, von="AMW"):
    """Ein Push aller Zweige und Tags an das Ziel. Rückgabe: Ereignis-Inhalt. Fehler → Meldung an den Lead."""
    z, ordner = ziel(con, pid), kern.projekt_ordner(con, pid)
    if not z:
        raise kern.AmwFehler("Kein Sicherungsziel eingestellt (amw projekt einstellen sicherung_ziel=… – nur der Mensch)")
    if not ordner:
        raise kern.AmwFehler("Das Projekt hat keinen Ordner (amw projekt ordner …)")
    s, n = stand(ordner)
    rc, aus = _git(ordner, "push", "--porcelain", z, "refs/heads/*:refs/heads/*", "refs/tags/*:refs/tags/*")
    abgewiesen = sorted(x.split("\t")[1].split(":")[0] for x in aus.splitlines() if x.startswith("!") and "\t" in x)
    bisher = set((letzte(con, pid) or {}).get("gemeldet") or [])
    if rc == 0:
        fehler = None
    elif ANMELDUNG.search(aus):
        fehler = "anmeldung"
    elif rc == 124:
        fehler = "frist"
    elif abgewiesen and "fatal:" not in aus:
        fehler = None                                         # nur abgewiesene Zweige – der Rest ist gesichert
    else:
        fehler = "git"
    neu = [x for x in abgewiesen if x not in bisher]          # P408 (3): je Zweig nur einmal melden
    e = {"ziel": anzeige(z), "refs": n, "stand": s, "rc": rc, "fehler": fehler, "abgewiesen": abgewiesen[:50],
         "gemeldet": sorted(bisher | set(abgewiesen))[:500], "von": von}
    lead = kern.lead(con, pid) or kern.ENTWICKLER
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ART, text=json.dumps(e, ensure_ascii=False))
        if fehler == "anmeldung":
            an = lead if lead == kern.ENTWICKLER else f"{lead},{kern.ENTWICKLER}"
            kern._posten(con, pid, "AMW", an, "meldung", f"Sicherung nach {anzeige(z)}: Anmeldung fehlt"[:140],
                         "git hat ohne Abfrage abgebrochen (im Dienst fragt git nie nach einer Anmeldung). Marcel: einmal im eigenen"
                         f" Terminal `git push {anzeige(z)}` im Projektordner, damit die Anmeldung gespeichert ist – danach geht die"
                         " tägliche Sicherung wieder von selbst. Nichts wurde gesichert, nichts verändert.")
        elif fehler:
            kern._posten(con, pid, "AMW", lead, "meldung", f"Sicherung nach {anzeige(z)} nicht gelungen ({fehler})"[:140],
                         f"git push (ohne --force, ohne Löschen) endete mit {rc}: {aus[-300:]}. Nächster Versuch morgen oder mit"
                         " amw sicherung jetzt.")
        elif neu:
            kern._posten(con, pid, "AMW", lead, "meldung", f"Sicherung nach {anzeige(z)}: {len(neu)} Zweig(e) nicht vorspulbar"[:140],
                         f"{', '.join(neu[:12])} – am Ziel nicht vorspulbar (lokal neu aufgesetzt?), dort unverändert gelassen; alle"
                         " anderen Refs sind gesichert. Diese Zweige meldet die AMW nicht noch einmal.")
    return e


def runde(con, heute=None):
    """Dienst-Runde: je Projekt mit Ziel höchstens ein Versuch am Tag, nur bei geänderten Refs. Rückgabe: Texte fürs Protokoll."""
    heute = heute or datetime.date.today().isoformat()
    aus = []
    for (pid,) in con.execute("SELECT id FROM projekt").fetchall():
        if not ziel(con, pid) or not kern.projekt_ordner(con, pid):
            continue
        l = letzte(con, pid)
        if l and _lokaler_tag(l["zeit_utc"]) == heute:
            continue
        try:
            s, _ = stand(kern.projekt_ordner(con, pid))
        except kern.AmwFehler as f:
            aus.append(f"P{pid}: {f}")
            continue
        if l and l.get("stand") == s and not l.get("fehler") and "fehler" in l:
            continue                                          # nichts geändert seit dem letzten Push ohne Fehler
        e = pushen(con, pid)
        aus.append(f"P{pid}: Sicherung {e['ziel']} – {e['refs']} Refs, rc {e['rc']}")
    return aus


def im_hintergrund(pfad, warten=None):
    """P408 (2): runde() in einem eigenen Faden mit eigener Verbindung – die Dienst-Runde wartet nie. Läuft schon einer,
    passiert nichts. Rückgabe: True, wenn gestartet."""
    f = _FADEN["faden"]
    if f and f.is_alive():
        return False

    def lauf():
        import logging
        con = db.verbinde(pfad)
        try:
            if warten:
                warten()
            for x in runde(con):
                logging.getLogger("amw.dienst").info("Sicherung: %s", x)
        except Exception as e:                                # noqa: BLE001 – der Faden meldet, er bricht nichts ab
            logging.getLogger("amw.dienst").warning("Sicherung: %s: %s", type(e).__name__, e)
        finally:
            con.close()
    _FADEN["faden"] = threading.Thread(target=lauf, name="sicherung", daemon=True)
    _FADEN["faden"].start()
    return True


def _lokaler_tag(zeit_utc):
    try:
        t = datetime.datetime.strptime(zeit_utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return None
    return t.astimezone().date().isoformat()
