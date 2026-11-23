"""Festplatte: freier Platz auf den Laufwerken, auf denen die Datenbank und die Projektordner liegen – mit Warnstufen und
einer Meldung an Lead und Mensch, wenn ein Laufwerk knapp wird. Dazu Aufräumvorschläge für alte Sicherungen.

Die AMW löscht und verschiebt hier nichts: Sie zeigt, was sich aufräumen ließe (was, wie groß, wie alt). Aufbewahrt
werden nach der Regel die neuesten Sicherungen (Einstellung sicherungen_behalten) und je veröffentlichter Version die
letzte Sicherung davor; alles andere ist ein Vorschlag.
"""
import datetime
import json
import os
import re
import shutil
import time

from . import db, einstellungen, kern

SICHERUNG = re.compile(r"^(?:amw-)?sicherung(?:-.+)?-(\d{4})-(\d\d)-(\d\d)-(\d\d)(\d\d)\.db$")
PRUEFEN_S = 600               # so oft misst der Wächter die Laufwerke
STUFEN = {None: 0, "gelb": 1, "rot": 2}


def laufwerk(pfad):
    """Das Laufwerk eines Pfads („F:“; ohne Laufwerksbuchstaben die Wurzel „/“)."""
    return os.path.splitdrive(os.path.abspath(pfad))[0].upper() or "/"


def stufe(frei_prozent):
    gelb, rot = float(einstellungen.wert("platte_gelb_prozent")), float(einstellungen.wert("platte_rot_prozent"))
    return "rot" if frei_prozent < rot else "gelb" if frei_prozent < gelb else None


def orte(con):
    """{Laufwerk: {"pfad": ein Ordner darauf, "projekte": [projekt_id, …], "daten": liegt die Datenbank dort?}}"""
    aus = {}
    daten = os.path.dirname(db.db_pfad())
    aus[laufwerk(daten)] = {"pfad": daten, "projekte": [], "daten": True}
    for p in con.execute("SELECT id FROM projekt ORDER BY id").fetchall():
        ordner = kern.projekt_ordner(con, p["id"])
        if ordner:
            aus.setdefault(laufwerk(ordner), {"pfad": ordner, "projekte": [], "daten": False})["projekte"].append(p["id"])
    return aus


def laufwerke(con, messen=None):
    """Je Laufwerk: {"laufwerk", "frei_gb", "gesamt_gb", "frei_prozent", "stufe", "projekte", "daten"} – knappstes zuerst.
    Laufwerke, die sich nicht messen lassen, fehlen."""
    messen, aus = messen or shutil.disk_usage, []
    for name, o in orte(con).items():
        try:
            m = messen(o["pfad"])
        except OSError:
            continue
        if not m.total:
            continue
        prozent = round(m.free * 100 / m.total, 1)
        aus.append({"laufwerk": name, "frei_gb": round(m.free / 2 ** 30, 1), "gesamt_gb": round(m.total / 2 ** 30, 1),
                    "frei_prozent": prozent, "stufe": stufe(prozent), "projekte": o["projekte"], "daten": o["daten"]})
    return sorted(aus, key=lambda x: x["frei_prozent"])


# --- Sicherungen: was nach der Aufbewahrungsregel übrig ist ---------------------------------------------------------

def _groesse(pfad):
    if os.path.isfile(pfad):
        return os.path.getsize(pfad)
    summe = 0
    for wurzel, _, dateien in os.walk(pfad):
        for d in dateien:
            try:
                summe += os.path.getsize(os.path.join(wurzel, d))
            except OSError:
                pass
    return summe


_SICHERUNG_GROESSE = {}      # A2001: (Pfad, Größe, Änderungszeit) → Bytes samt Dokumente-Ablage (135 Sicherungen: 16 s je Aufruf)


def sicherungen(ordner=None):
    """Sicherungen im Ordner der Datenbank, neueste zuerst: [{"name", "zeit" (Ortszeit laut Name), "bytes"}] – die
    Dokumente-Ablage daneben („…-dokumente“) zählt zur Größe."""
    ordner = ordner or os.path.dirname(db.db_pfad())
    aus = []
    try:
        namen = os.listdir(ordner)
    except OSError:
        return aus
    for n in namen:
        m = SICHERUNG.match(n)
        if not m:
            continue
        try:
            zeit = datetime.datetime(*(int(x) for x in m.groups()))
            pfad = os.path.join(ordner, n)
            st = os.stat(pfad)
            merk = (pfad, st.st_size, st.st_mtime_ns)          # A2001: eine Sicherung ändert sich nicht – Größe einmal zählen
            groesse = _SICHERUNG_GROESSE.get(merk)
            if groesse is None:
                groesse = st.st_size
                ablage = os.path.splitext(pfad)[0] + "-dokumente"
                if os.path.isdir(ablage):
                    groesse += _groesse(ablage)
                _SICHERUNG_GROESSE[merk] = groesse
            aus.append({"name": n, "zeit": zeit, "bytes": groesse})
        except (OSError, ValueError):
            pass
    return sorted(aus, key=lambda x: x["zeit"], reverse=True)


def versionen(con):
    """Zeitpunkte (Ortszeit) aller veröffentlichten Versionen – je Version bleibt die letzte Sicherung davor."""
    aus = []
    for r in con.execute("SELECT zeit_utc FROM release WHERE art = 'version' AND zeit_utc IS NOT NULL").fetchall():
        try:
            aus.append(datetime.datetime.strptime(r[0][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
                       .astimezone().replace(tzinfo=None))
        except ValueError:
            pass
    return aus


def aufraeumen(liste, behalten, versionen=(), jetzt=None):
    """Aufräumvorschläge: die Sicherungen, die nach der Regel nicht gebraucht werden – [{"name", "bytes", "tage"}],
    älteste zuerst. Bleiben: die `behalten` neuesten und je Version die letzte Sicherung davor."""
    jetzt = jetzt or datetime.datetime.now()
    bleibt = {x["name"] for x in liste[:max(0, int(behalten))]}
    for v in versionen:
        davor = next((x for x in liste if x["zeit"] <= v), None)       # liste: neueste zuerst
        if davor:
            bleibt.add(davor["name"])
    return [{"name": x["name"], "bytes": x["bytes"], "tage": max(0, (jetzt - x["zeit"]).days)}
            for x in reversed(liste) if x["name"] not in bleibt]


def vorschlaege(con):
    """Aufräumvorschläge für diesen PC: {"sicherungen": […], "bytes": Summe, "ordner": wo sie liegen}."""
    liste = aufraeumen(sicherungen(), einstellungen.wert("sicherungen_behalten"), versionen(con))
    return {"sicherungen": liste, "bytes": sum(x["bytes"] for x in liste), "ordner": os.path.dirname(db.db_pfad())}


def archivieren(con, namen):
    """Verschiebt die genannten Aufräumvorschläge (alte Sicherungen samt Dokumente-Ablage) in den Archiv-Ordner dieses
    PCs – nur, was gerade in der Vorschlagsliste steht; gelöscht wird nichts. Jede Verschiebung steht im Protokoll
    archiv-protokoll.txt im Archiv-Ordner. Rückgabe: [(alt, neu), …]."""
    ziel = einstellungen.wert("archiv_ordner")
    if not ziel or not os.path.isdir(ziel):
        raise kern.AmwFehler("Kein Archiv-Ordner eingestellt (Einstellungen › Dieser PC)")
    erlaubt = {x["name"] for x in vorschlaege(con)["sicherungen"]}
    falsch = [n for n in namen if n not in erlaubt]
    if falsch:
        raise kern.AmwFehler(f"Nicht in den Aufräumvorschlägen: {', '.join(falsch)}")
    quelle, aus = os.path.dirname(db.db_pfad()), []
    zeit = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    for n in namen:
        for teil in (n, os.path.splitext(n)[0] + "-dokumente"):
            alt = os.path.join(quelle, teil)
            if not os.path.exists(alt):
                continue
            neu = os.path.join(ziel, teil)
            i = 2
            while os.path.exists(neu):                       # nie überschreiben
                stamm, endung = os.path.splitext(teil) if os.path.isfile(alt) else (teil, "")
                neu = os.path.join(ziel, f"{stamm}-{i}{endung}")
                i += 1
            shutil.move(alt, neu)
            aus.append((alt, neu))
            with open(os.path.join(ziel, "archiv-protokoll.txt"), "a", encoding="utf-8") as f:
                f.write(f"{zeit} | {alt} → {neu}\n")
    return aus


# --- Ordnergrößen: einmal am Tag messen, Zuwächse und Ablagerungen zeigen (nur Anzeige) --------------------------------

ABLAGEN = {"build", "dist", "out", "bin", "obj", ".godot", ".import", "node_modules", "__pycache__", ".pytest_cache",
           "tmp", "temp", "test-output", "testergebnisse", ".mypy_cache", ".gradle", "target"}
MESSEN_ALLE_S = 20 * 3600     # so oft (höchstens) misst der Dienst
AUFBEWAHREN_TAGE = 90


def _ordnergroesse(pfad):
    """(Bytes, Dateien, jüngste Änderung als UTC-Text) eines Ordners; Verknüpfungen werden nicht verfolgt."""
    summe = n = 0
    juengste = 0.0
    for wurzel, ordner, dateien in os.walk(pfad, followlinks=False):
        for d in dateien:
            try:
                st = os.stat(os.path.join(wurzel, d), follow_symlinks=False)
            except OSError:
                continue
            summe += st.st_size
            n += 1
            juengste = max(juengste, st.st_mtime)
    zeit = datetime.datetime.fromtimestamp(juengste, datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if juengste else None
    return summe, n, zeit


def _ablagen(ordner, tiefe=2):
    """Typische Ablagerungen (Build-Reste, Caches, Temp-Ordner) bis zur zweiten Ebene des Projektordners."""
    aus = []
    def suche(pfad, ebene):
        try:
            eintraege = list(os.scandir(pfad))
        except OSError:
            return
        for e in eintraege:
            if not e.is_dir(follow_symlinks=False) or e.name == ".git":
                continue
            if e.name.lower() in ABLAGEN:
                aus.append(e.path)
            elif ebene < tiefe:
                suche(e.path, ebene + 1)
    suche(ordner, 1)
    return aus


def _worktrees(ordner):
    """Weitere Arbeitsbäume des Git-Repositorys im Projektordner (nur lesen: git worktree list)."""
    import subprocess
    try:
        aus = subprocess.run(["git", "-C", ordner, "worktree", "list", "--porcelain"], capture_output=True, text=True, timeout=30,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return []
    pfade = [z[9:].strip() for z in aus.stdout.splitlines() if z.startswith("worktree ")]
    haupt = os.path.normcase(os.path.abspath(ordner))
    return [p for p in pfade if os.path.normcase(os.path.abspath(p)) != haupt and os.path.isdir(p)]


def ziele(con):
    """Was gemessen wird: [(projekt_id, ordner, art)] – Projektordner dieses PCs, ihre Ablagerungen und Worktrees,
    dazu der Ordner der Sicherungen."""
    aus = []
    for p in con.execute("SELECT id FROM projekt ORDER BY id").fetchall():
        ordner = kern.projekt_ordner(con, p["id"])
        if ordner and os.path.isdir(ordner):
            aus.append((p["id"], os.path.abspath(ordner), "projekt"))
            aus += [(p["id"], a, "ablage") for a in _ablagen(ordner)]
            aus += [(p["id"], w, "worktree") for w in _worktrees(ordner)]
    return aus


def messen(con, jetzt=None):
    """Misst alle Ziele und speichert die Werte (eigene Transaktion je Ziel – lange Messungen sperren nichts). Räumt
    Messwerte älter als AUFBEWAHREN_TAGE weg. Rückgabe: Anzahl gemessener Ordner."""
    from . import betrieb
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    zeit = jetzt.strftime("%Y-%m-%dT%H:%M:%SZ")
    rechner = betrieb.rechner()
    n = 0
    for pid, ordner, art in ziele(con):
        b, d, z = _ordnergroesse(ordner)
        with db.schreiben(con):
            db.einfuegen(con, "ordner_messung", zeit_utc=zeit, rechner=rechner, projekt_id=pid, ordner=ordner, art=art,
                         bytes=b, dateien=d, zuletzt_utc=z)
        n += 1
    s = sicherungen()
    with db.schreiben(con):
        db.einfuegen(con, "ordner_messung", zeit_utc=zeit, rechner=rechner, projekt_id=None, ordner=os.path.dirname(db.db_pfad()),
                     art="sicherungen", bytes=sum(x["bytes"] for x in s), dateien=len(s), zuletzt_utc=None)
        con.execute("DELETE FROM ordner_messung WHERE zeit_utc < ?",
                    ((jetzt - datetime.timedelta(days=AUFBEWAHREN_TAGE)).strftime("%Y-%m-%dT%H:%M:%SZ"),))
    try:
        claude_messen(con, jetzt=jetzt)                   # A1779: Claude-Ablagen gleich mit
    except Exception:                                     # nie die Messung der Projektordner stören
        pass
    return n + 1


def faellig(con, jetzt=None):
    """Ist eine Messung fällig? Nur, wenn die letzte länger als MESSEN_ALLE_S her ist und kein schwerer Lauf läuft."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    letzte = con.execute("SELECT max(zeit_utc) FROM ordner_messung").fetchone()[0]
    if letzte:
        try:
            alt = (jetzt - db.utc_lesen(letzte)).total_seconds()
        except ValueError:
            alt = MESSEN_ALLE_S
        if alt < MESSEN_ALLE_S:
            return False
    return not con.execute("SELECT 1 FROM lauf WHERE status = 'laeuft' AND schwer = 1 LIMIT 1").fetchone()


def zuwaechse(con, pid=None, tage=7, n=5):
    """Die größten Zuwächse: je Ordner der neueste Wert gegen den Wert von vor etwa `tage` Tagen –
    [{"ordner", "art", "bytes", "plus"}], größter Zuwachs zuerst; nur Zuwächse ab 1 MB. pid: nur Ordner dieses Projekts
    und die Sicherungen (die Projekte mischen sich nicht)."""
    neu = {r["ordner"]: dict(r) for r in con.execute(
        "SELECT m.ordner, m.art, m.bytes, m.zeit_utc FROM ordner_messung m WHERE m.id = (SELECT max(id) FROM ordner_messung x WHERE x.ordner = m.ordner)"
        " AND (? IS NULL OR m.projekt_id IS NULL OR m.projekt_id = ?)", (pid, pid))}
    aus = []
    for ordner, r in neu.items():
        alt = con.execute("SELECT bytes FROM ordner_messung WHERE ordner = ? AND zeit_utc <= strftime('%Y-%m-%dT%H:%M:%SZ', ?, ?)"
                          " ORDER BY zeit_utc DESC LIMIT 1", (ordner, r["zeit_utc"], f"-{tage} days")).fetchone()
        if not alt:
            alt = con.execute("SELECT bytes FROM ordner_messung WHERE ordner = ? ORDER BY zeit_utc LIMIT 1", (ordner,)).fetchone()
        plus = r["bytes"] - (alt[0] if alt else r["bytes"])
        if plus >= 2 ** 20:
            aus.append({"ordner": ordner, "art": r["art"], "bytes": r["bytes"], "plus": plus})
    return sorted(aus, key=lambda x: -x["plus"])[:n]


def ablagerungen(con, pid=None, n=10, jetzt=None):
    """Ablagen und Worktrees nach Größe, mit Tagen seit der letzten Änderung darin – [{"ordner", "art", "bytes", "tage"}].
    pid: nur die dieses Projekts."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    aus = []
    for r in con.execute("SELECT m.ordner, m.art, m.bytes, m.zuletzt_utc FROM ordner_messung m WHERE m.art IN ('ablage', 'worktree')"
                         " AND m.id = (SELECT max(id) FROM ordner_messung x WHERE x.ordner = m.ordner) AND (? IS NULL OR m.projekt_id = ?)"
                         " ORDER BY m.bytes DESC LIMIT ?", (pid, pid, n)):
        tage = None
        if r["zuletzt_utc"]:
            try:
                tage = max(0, (jetzt - db.utc_lesen(r["zuletzt_utc"])).days)
            except ValueError:
                pass
        aus.append({"ordner": r["ordner"], "art": r["art"], "bytes": r["bytes"], "tage": tage})
    return aus


# --- Claude-Ablagen (A1779): Arbeitsordner der Claude-Sitzungen in %TEMP%\claude ----------------------------------------
# 15.11.: eine Sitzung legte 64 GB Arbeitskopien in ihrem Scratchpad ab, C: lief fast voll – gemessen wurden nur Projektordner.
# Gemessen wird je Sitzungsordner (<TEMP>/claude/<Ordner>/<Sitzungs-ID>); die Sitzungs-ID führt über die Tabelle sitzung zu
# Projekt und Agent. Werte in einer Datei dieses PCs (kein Schema, nichts geht online). Die AMW löscht nichts.

CLAUDE_GRENZE_GB = 10            # ab hier bekommen Lead und Mensch eine Meldung
KOPIE_ALT_TAGE = 1               # Arbeitskopien (Ordner mit .git), die so lange unverändert sind, werden vorgeschlagen


def claude_basis():
    import tempfile                                       # AMW_CLAUDE_BASIS: Tests (tests/abschotten.py) – nie das echte
    return os.environ.get("AMW_CLAUDE_BASIS") or os.path.join(tempfile.gettempdir(), "claude")


def _claude_datei():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "amw", "claude_ablagen.json")


def _arbeitskopien(pfad, tiefe=5):
    """Ordner mit .git (Datei bei Worktrees, Ordner bei Klonen) bis `tiefe` Ebenen – nicht in sie hinein."""
    aus = []
    def suche(p, ebene):
        try:
            eintraege = list(os.scandir(p))
        except OSError:
            return
        if any(e.name == ".git" for e in eintraege):
            aus.append(p)
            return
        if ebene < tiefe:
            for e in eintraege:
                if e.is_dir(follow_symlinks=False):
                    suche(e.path, ebene + 1)
    suche(pfad, 0)
    return aus


def _alter_tage(utc, jetzt):
    try:
        return max(0, (jetzt - db.utc_lesen(utc)).days)
    except (TypeError, ValueError):
        return None


def befehl_entfernen(pfad):
    """Fertiger PowerShell-Befehl für den Menschen – die AMW führt ihn nie aus."""
    return f"Remove-Item -LiteralPath '{pfad.replace(chr(39), chr(39) * 2)}' -Recurse -Force"


def _git(pfad, *args):
    import subprocess
    try:
        r = subprocess.run(["git", "-C", pfad, *args], capture_output=True, text=True, timeout=30,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.SubprocessError):
        return None
    return r


def worktree_lage(pfad):
    """A1825 (G14, Marcel 16.11.): Ist die Arbeitskopie ein Worktree, ohne offene Änderungen und ihr Stand schon im
    Hauptzweig (main/master des Repositorys)? Dann darf der Agent, dem sie gehört, sie selbst entfernen –
    {"haupt", "zweig", "befehl"}; sonst None (nur lesen, die AMW führt nichts aus)."""
    if not os.path.isfile(os.path.join(pfad, ".git")):    # Klon (.git-Ordner) oder kein Repo: nicht unter die Ausnahme
        return None
    gemeinsam = _git(pfad, "rev-parse", "--path-format=absolute", "--git-common-dir")
    status = _git(pfad, "status", "--porcelain")
    if not gemeinsam or gemeinsam.returncode or not status or status.returncode or status.stdout.strip():
        return None
    haupt = os.path.dirname(gemeinsam.stdout.strip().rstrip("/\\"))
    zweig = _git(pfad, "rev-parse", "--abbrev-ref", "HEAD")
    for basis in ("main", "master"):
        r = _git(pfad, "merge-base", "--is-ancestor", "HEAD", basis)
        if r is not None and r.returncode == 0:
            q = lambda x: "'" + x.replace("'", "''") + "'"
            return {"haupt": haupt, "zweig": (zweig.stdout.strip() if zweig and not zweig.returncode else "") or "HEAD",
                    "befehl": f"git -C {q(haupt)} worktree remove {q(pfad)}; git -C {q(haupt)} worktree prune"}
    return None


def claude_messen(con, basis=None, jetzt=None):
    """Misst die Sitzungsordner unter <TEMP>/claude, ordnet sie über sitzung.claude_sitzung zu und schreibt das Ergebnis
    in claude_ablagen.json. Meldet Sitzungen über CLAUDE_GRENZE_GB einmal an Lead + Mensch. Rückgabe: das Ergebnis."""
    basis = basis or claude_basis()
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    alt = claude_ablagen()
    sitzungen = []
    try:
        oben = [e for e in os.scandir(basis) if e.is_dir(follow_symlinks=False)]
    except OSError:
        oben = []
    for o in oben:
        try:
            unten = [e for e in os.scandir(o.path) if e.is_dir(follow_symlinks=False)]
        except OSError:
            continue
        for u in unten:
            b, d, z = _ordnergroesse(u.path)
            s = {"ordner": u.path, "sitzung": u.name, "bytes": b, "dateien": d, "zuletzt_utc": z, "tage": _alter_tage(z, jetzt)}
            r = con.execute("SELECT a.kennung, p.id AS pid, p.name FROM sitzung s JOIN agent a ON a.id = s.agent_id JOIN projekt p"
                            " ON p.id = a.projekt_id WHERE s.claude_sitzung = ? ORDER BY s.id DESC LIMIT 1", (u.name,)).fetchone()
            if r:
                s.update(agent=r["kennung"], projekt=r["name"], projekt_id=r["pid"])
            kopien = []
            for k in _arbeitskopien(u.path):
                kb, kd, kz = _ordnergroesse(k)
                t = _alter_tage(kz, jetzt)
                if kb >= 2 ** 20 and t is not None and t >= KOPIE_ALT_TAGE:
                    w = worktree_lage(k) if s.get("agent") else None    # A1825: gemergter Worktree → räumt der Agent selbst
                    kopien.append({"ordner": k, "bytes": kb, "tage": t, "befehl": w["befehl"] if w else befehl_entfernen(k),
                                   **({"selbst": s["agent"], "zweig": w["zweig"]} if w else {})})
            s["arbeitskopien"] = sorted(kopien, key=lambda x: -x["bytes"])
            sitzungen.append(s)
    sitzungen.sort(key=lambda x: -x["bytes"])
    gemeldet = set(alt.get("gemeldet") or [])
    for s in sitzungen:
        if s["bytes"] >= CLAUDE_GRENZE_GB * 2 ** 30 and s["sitzung"] not in gemeldet:
            _claude_melden(con, s)
            gemeldet.add(s["sitzung"])
        for k in s["arbeitskopien"]:                      # A1825: gemergte eigene Worktrees dem Agenten vorschlagen, einmal
            if k.get("selbst") and "kopie:" + k["ordner"] not in gemeldet and s.get("projekt_id"):
                _kopie_melden(con, s, k)
                gemeldet.add("kopie:" + k["ordner"])
    erg = {"zeit_utc": jetzt.strftime("%Y-%m-%dT%H:%M:%SZ"), "basis": basis, "sitzungen": sitzungen,
           "gemeldet": sorted(g for g in gemeldet if any(s["sitzung"] == g or any("kopie:" + k["ordner"] == g for k in s["arbeitskopien"])
                                                         for s in sitzungen))}
    try:
        os.makedirs(os.path.dirname(_claude_datei()), exist_ok=True)
        tmp = f"{_claude_datei()}.{os.getpid()}.tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(erg, f, ensure_ascii=False)
        os.replace(tmp, _claude_datei())
    except OSError:
        pass
    return erg


def _claude_melden(con, s):
    gb = f"{s['bytes'] / 2 ** 30:.1f}".replace(".", ",")
    wer = f"{s['agent']} ({s['projekt']})" if s.get("agent") else "eine Sitzung ohne Zuordnung"
    kurz = f"Claude-Ablage von {wer}: {gb} GB in %TEMP%\\claude"
    text = (f"Der Arbeitsordner {s['ordner']} belegt {gb} GB ({s['dateien']} Dateien)."
            + (f" Darin {len(s['arbeitskopien'])} alte Arbeitskopien – Vorschläge unter Einstellungen › Dieser PC › Claude-Ablagen."
               if s["arbeitskopien"] else "")
            + " Die AMW löscht nichts; aufräumen kann nur der Mensch. Sitzung noch aktiv? Dann bitte dort keine weiteren Kopien anlegen.")
    pid = s.get("projekt_id") or (con.execute("SELECT id FROM projekt ORDER BY id LIMIT 1").fetchone() or [None])[0]
    if pid is None:
        return
    with db.schreiben(con):
        lead = kern.lead(con, pid)
        if lead:
            kern._posten(con, pid, "AMW", lead, "meldung", kurz, text)
        kern._posten(con, pid, "AMW", kern.ENTWICKLER, "meldung", kurz, text)


def _kopie_melden(con, s, k):
    gb = f"{k['bytes'] / 2 ** 30:.1f}".replace(".", ",")
    kurz = f"Deine Arbeitskopie (Zweig {k['zweig']}, gemergt) belegt {gb} GB – bitte selbst entfernen"
    text = (f"{k['ordner']} ist ein Worktree ohne offene Änderungen, sein Stand steckt schon im Hauptzweig. Nach G14 darfst du"
            f" eigene gemergte Arbeitskopien selbst entfernen – nur diese, nichts anderes: {k['befehl']}")
    with db.schreiben(con):
        kern._posten(con, s["projekt_id"], "AMW", s["agent"], "meldung", kurz, text)


def claude_ablagen():
    """Letztes Ergebnis von claude_messen() ({} vor der ersten Messung)."""
    try:
        with open(_claude_datei(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


# --- Wache: melden, wenn ein Laufwerk knapp wird --------------------------------------------------------------------

def _merk_datei():
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "amw", "platte.json")


def _gemeldet():
    try:
        with open(_merk_datei(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _merken(d):
    try:
        os.makedirs(os.path.dirname(_merk_datei()), exist_ok=True)
        with open(_merk_datei(), "w", encoding="utf-8") as f:
            json.dump(d, f)
    except OSError:
        pass


def meldetext(l, vorschlag_bytes=0):
    text = (f"Laufwerk {l['laufwerk']} wird knapp: noch {str(l['frei_gb']).replace('.', ',')} GB frei"
            f" ({str(l['frei_prozent']).replace('.', ',')} % von {str(l['gesamt_gb']).replace('.', ',')} GB).")
    if l["stufe"] == "rot":
        text += " Schwere Läufe und Sicherungen können daran scheitern."
    if vorschlag_bytes >= 2 ** 20:
        text += f" Alte Sicherungen belegen {vorschlag_bytes / 2 ** 30:.1f} GB – Vorschläge zeigt `amw rechner`.".replace(".", ",", 1)
    return text + " Die AMW löscht nichts; aufräumen kann nur der Mensch."


class Wache:
    """Misst alle PRUEFEN_S die Laufwerke. Wird eines knapper als zuletzt gemeldet (frei → gelb → rot), bekommen die
    Leads der Projekte auf diesem Laufwerk eine Meldung und der Mensch eine. Erholt es sich, wird das vermerkt – die
    nächste Verschlechterung meldet wieder. Der Stand je Laufwerk steht in einer Datei dieses PCs (kein Neu-Melden nach
    einem Neustart)."""

    def __init__(self, con, messen=None):
        self.con, self.messen, self.zuletzt = con, messen, 0.0

    def runde(self, jetzt=None):
        jetzt = jetzt or time.time()
        if jetzt - self.zuletzt < PRUEFEN_S:
            return []
        self.zuletzt = jetzt
        gemeldet, aus, neu = _gemeldet(), [], {}
        for l in laufwerke(self.con, self.messen):
            neu[l["laufwerk"]] = l["stufe"]
            if STUFEN[l["stufe"]] <= STUFEN.get(gemeldet.get(l["laufwerk"]), 0):
                continue
            text = meldetext(l, vorschlaege(self.con)["bytes"] if l["daten"] else 0)
            projekte = l["projekte"] or [p["id"] for p in self.con.execute("SELECT id FROM projekt ORDER BY id LIMIT 1").fetchall()]
            mensch = False
            for pid in projekte:
                with db.schreiben(self.con):
                    lead = kern.lead(self.con, pid)
                    if lead:
                        kern._posten(self.con, pid, "AMW", lead, "meldung", text)
                    if not mensch:                           # der Mensch bekommt sie einmal, nicht je Projekt
                        kern._posten(self.con, pid, "AMW", kern.ENTWICKLER, "meldung", text)
                        mensch = True
            aus.append(text)
        if neu != {k: gemeldet.get(k) for k in neu} or set(gemeldet) - set(neu):
            _merken(neu)
        return aus
