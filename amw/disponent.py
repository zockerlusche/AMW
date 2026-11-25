"""Disponent (A1874, M50 S6c; D1258 v17 §2, §6.1): der Dienst startet startklare p-Pakete selbst.

Je Runde des Dienstes, nur in Projekten mit Arbeitsplätzen (plaetze > 0):
1. Verwaiste Läufe: läuft ein Paket, dessen Starter nicht mehr lebt (und kein Job-Objekt mehr besteht) → E1 „Starter weg“.
2. Startfolge (waechter.reihenfolge) → Wächter (pruefen + protokollieren). Darf eins starten: freien Platz vorbereiten
   (eigener Klon, Zweig ab main) → Basis vermerken → Regel 6 (Abnahme vor dem Bau rot; sonst zurückgestellt + Lead) → Zustand
   laeuft → Starter als eigener, losgelöster Prozess. Je Runde höchstens ein Start.
3. Planungs-Weckruf (B2898): Platz frei und kein startklares p-Paket im aktiven Bogen, oder alle Pakete eines aktiven Bogens
   fertig → eine Nachricht mit Inhalt an den Lead, höchstens einmal je Anlass, bis sich etwas ändert.

Der Starter (amw-arbeiter.py → starter()) besitzt das Job-Objekt des Arbeiters – ein Neustart des Dienstes beendet ihn nicht
(D1270 Nr. 17). Er lässt den Arbeiter laufen, danach Prüfung C (über die Lauf-Schlange: Tests sind ein schwerer Lauf auf einem
geteilten PC) mit der beim Vorbereiten vermerkten Basis – nie aus dem Klon – und wendet die Entscheidungstabelle an (E5: ein
Nachbesserungslauf auf demselben Platz).
"""
import json
import os
import subprocess
import sys
import time

from . import db, kern

VERMERK = "platz_belegt"                      # plan_ereignis: {"platz", "basis", "zweig", "starter_pid", "start_utc"}
EINSTIEG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "amw-arbeiter.py")


def _einst(con, pid):
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    return json.loads((r[0] if r else None) or "{}")


def vermerk(con, pid, aid):
    """Letzter Belegungs-Vermerk eines Pakets (die AMW schreibt ihn beim Vorbereiten – Quelle der Basis für Prüfung C)."""
    r = con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND aufgabe_id = ? AND art = ? ORDER BY id DESC LIMIT 1",
                    (pid, aid, VERMERK)).fetchone()
    return json.loads(r[0]) if r else None


def belegte_plaetze(con, pid):
    """{platz_nr: aid} der Pakete, die einen Platz halten (laeuft … merge_reihe – der Platz bleibt bis zum Merge)."""
    from . import waechter
    aus = {}
    for r in waechter.belegt(con, con.execute(f"SELECT k.aufgabe_id, k.zustand FROM paket k JOIN aufgabe a ON a.id = k.aufgabe_id"
                                              f" WHERE a.projekt_id = ? AND k.art = 'p' AND k.zustand IN ({','.join('?' * len(waechter.LAUFEND))})",
                                              (pid, *waechter.LAUFEND)).fetchall()):   # A1897 Zusatz 3: angenommene geben den Platz frei
        v = vermerk(con, pid, r[0])
        if v:
            aus[v["platz"]] = r[0]
    return aus


def _lebt(pid_):
    if not pid_:
        return False
    if os.name != "nt":
        try:
            os.kill(pid_, 0)
            return True
        except OSError:
            return False
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    h = k.OpenProcess(0x1000, False, int(pid_))
    if not h:
        return False
    try:
        code = wintypes.DWORD()
        return bool(k.GetExitCodeProcess(h, ctypes.byref(code))) and code.value == 259
    finally:
        k.CloseHandle(h)


def _job_besteht(p):
    if os.name != "nt":
        return False
    from . import arbeiter
    k = arbeiter._kernel()
    h = k.OpenJobObjectW(0x0004, False, arbeiter.job_name(p))
    if h:
        k.CloseHandle(h)
        return True
    return False


class PlatzBelegt(RuntimeError):
    pass


class _Platzsperre:
    """P272 (b): Sperre um „Platz wählen + vorbereiten + laeuft setzen“ – eine gesperrte Datei neben dem Platz (msvcrt.locking),
    sie wird nie gelöscht. Wer sie nicht bekommt, nimmt den Platz nicht."""
    def __init__(self, p):
        wurzel = os.path.dirname(p["klon"])                       # neben den Platz – der Datenordner muss für vorbereiten leer sein
        os.makedirs(wurzel, exist_ok=True)
        self.pfad = os.path.join(wurzel, f"platz{p['nr']}.sperre")

    def __enter__(self):
        self.f = open(self.pfad, "a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            self.f.close()
            raise PlatzBelegt("Platz wird gerade von einem anderen Start vorbereitet") from None
        return self

    def __exit__(self, *a):
        try:
            if os.name == "nt":
                import msvcrt
                self.f.seek(0)
                msvcrt.locking(self.f.fileno(), msvcrt.LK_UNLCK, 1)
        finally:
            self.f.close()


def _alter_s(utc):
    import datetime
    try:
        t = db.utc_lesen(utc)
        return (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds()
    except (TypeError, ValueError):
        return 10 ** 9


def _lauf_fertig(p, v):
    """A1877 (i): liegt ein vollständiges Protokoll des Arbeiters dieses Starts vor (result-Ereignis, nach dem Start geschrieben)?"""
    from . import arbeiter, rueckmeldung
    pfad = os.path.join(arbeiter.ordner(p), "lauf.jsonl")
    try:
        if os.path.getmtime(pfad) < time.time() - _alter_s(v.get("start_utc")) - 5:
            return False                                          # älter als dieser Start: gehört zu einem früheren Lauf
    except OSError:
        return False
    return any(isinstance(e, dict) and e.get("type") == "result" for e in rueckmeldung.ereignisse_lesen(pfad))


def _nachholen(con, pid, aid, p, v, umgebung=None):
    """Den Nachhol-Starter losgelöst starten (Prüfung C + Entscheidung aus dem vorhandenen Protokoll) – der Dienst blockiert nie."""
    befehl = [sys.executable, "-I", "-X", "utf8", EINSTIEG, "--projekt-id", str(pid), "--aufgabe", str(aid), "--platz", str(p["nr"]),
              "--basis", v["basis"], "--vermerk", str(_vermerk_id(con, pid, aid)), "--nachholen"]
    flags = (0x00000008 | 0x00000200 | getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0
    proc = subprocess.Popen(befehl, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                            creationflags=flags, env=umgebung, start_new_session=os.name != "nt")
    vid = _vermerk_id(con, pid, aid)
    with db.schreiben(con):
        con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?", (json.dumps(dict(v, starter_pid=proc.pid, nachholen=True)), vid))
    return f"A{aid}: Starter weg, Lauf fertig → Prüfung C wird nachgeholt (Starter {proc.pid})"


def _vermerk_id(con, pid, aid):
    r = con.execute("SELECT id FROM plan_ereignis WHERE projekt_id = ? AND aufgabe_id = ? AND art = ? ORDER BY id DESC LIMIT 1",
                    (pid, aid, VERMERK)).fetchone()
    return r[0] if r else 0


START_GRUND = "headless_start"   # A2047 (V9, D1531 §9): {"aufgabe", "platz", "reihe", "grund", "von"} – warum dieses Paket jetzt


def warum(con, pid, aid):
    """A2047: Der zuletzt gespeicherte Grund, warum ein Paket gestartet bzw. zugeteilt wurde – Headless (headless_start) oder
    Fenster-Agent (verteilt): {"art", "zeit_utc", …} oder None."""
    r = con.execute("SELECT art, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND aufgabe_id = ? AND art IN (?, 'verteilt')"
                    " ORDER BY id DESC LIMIT 1", (pid, aid, START_GRUND)).fetchone()
    if not r:
        return None
    try:
        d = json.loads(r["text"] or "{}")
    except ValueError:
        d = {}
    return {**d, "art": r["art"], "zeit_utc": r["zeit_utc"]}


def _start_grund(con, pid, aid, p, von):
    """Warum dieses Paket jetzt: Platz in der berechneten Reihenfolge und ihr Grund (reihenfolge.berechnen) – oder von Hand."""
    from . import reihenfolge
    try:
        z = next((x for x in reihenfolge.berechnen(con, pid) if x["aid"] == aid), None)
    except Exception:                                    # noqa: BLE001 – ohne Berechnung bleibt der Start, der Grund ist knapper
        z = None
    teile = [f"von Hand gestartet ({von})"] if von != "AMW" else []
    if z:
        teile.append(f"Platz {z['platz']} in der Reihenfolge · {z['grund']}")
    teile.append(f"Arbeitsplatz {p['nr']} frei, Regeln des Wächters erfüllt")
    return {"aufgabe": aid, "platz": p["nr"], "reihe": z["platz"] if z else None, "grund": " · ".join(teile), "von": von}


def starten(con, pid, aid, p, quelle, prog=None, umgebung=None, von="AMW"):
    """Platz vorbereiten, Basis vermerken, Regel 6, Zustand laeuft, Starter losgelöst starten. Rückgabe: Text fürs Protokoll.
    von: AMW (Disponent) oder wer von Hand startet – steht im gespeicherten Grund (A2047)."""
    with _Platzsperre(p):
        if p["nr"] in belegte_plaetze(con, pid):                  # nach dem Sperren nochmal: ein anderer Start war schneller
            raise PlatzBelegt(f"Headless {p['nr']} ist inzwischen belegt")
        return _starten(con, pid, aid, p, quelle, prog, umgebung, von)


def _starten(con, pid, aid, p, quelle, prog=None, umgebung=None, von="AMW"):
    from . import abnahme, arbeitspaket, platz, waechter
    a = con.execute("SELECT pruefbefehl FROM aufgabe WHERE id = ?", (aid,)).fetchone()
    f = arbeitspaket.lesen(con, aid)
    zweig = f"paket-A{aid}"
    r = platz.vorbereiten(p, quelle, zweig, aufgabe=aid)
    from . import pruefung_c
    rot = abnahme.rot_vor_bau(p, a["pruefbefehl"], f.get("pakettyp"), pruefung_c.projekt_abnahme(con, pid)["frist_s"])   # A1920
    if not rot["ok"]:                                          # Regel 6: prüft nichts → nicht starten, Lead melden
        antwort = waechter.regel6(rot)
        waechter.protokollieren(con, pid, aid, antwort)
        arbeitspaket.zustand_setzen(con, pid, "AMW", aid, "zurueckgestellt", grund=f"Regel 6: {rot.get('grund')}"[:200])
        with db.schreiben(con):
            kern._posten(con, pid, "AMW", kern.lead(con, pid) or kern.ENTWICKLER, "meldung", f"A{aid} nicht gestartet, Regel 6"[:140],
                         f"A{aid}: {rot.get('grund')} – das Paket ist zurückgestellt; Abnahme-Befehl ändern, dann wieder startklar.",
                         aufgabe_id=aid)
        return f"A{aid} nicht gestartet, Regel 6: {rot.get('grund')}"
    g = _start_grund(con, pid, aid, p, von)                    # A2047: vor dem Zustand rechnen – danach läuft es schon
    arbeitspaket.zustand_setzen(con, pid, "AMW", aid, "laeuft", grund=f"Start als Headless {p['nr']}")
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=START_GRUND, aufgabe_id=aid,
                     text=json.dumps(g, ensure_ascii=False))
    # P272 (1): der Vermerk mit der Basis steht VOR dem Start des Starters; der Starter bekommt Basis und Vermerk-Nummer als
    # Argument und liest keinen (womöglich alten) Vermerk nach
    v = {"platz": p["nr"], "basis": r["basis"], "zweig": zweig, "starter_pid": None, "start_utc": db.jetzt()}
    with db.schreiben(con):
        vid = db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=VERMERK, aufgabe_id=aid,
                           text=json.dumps(v))
    befehl = [sys.executable, "-I", "-X", "utf8", EINSTIEG, "--projekt-id", str(pid), "--aufgabe", str(aid), "--platz", str(p["nr"]),
              "--basis", r["basis"], "--vermerk", str(vid)]
    if prog:
        befehl += ["--prog", json.dumps(prog)]
    flags = (0x00000008 | 0x00000200 | getattr(subprocess, "CREATE_NO_WINDOW", 0)) if os.name == "nt" else 0   # DETACHED, NEW_GROUP
    proc = subprocess.Popen(befehl, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                            creationflags=flags, env=umgebung, start_new_session=os.name != "nt")
    with db.schreiben(con):
        con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?", (json.dumps(dict(v, starter_pid=proc.pid)), vid))
    return f"A{aid} gestartet als Headless {p['nr']} (Starter {proc.pid}, Basis {r['basis'][:8]})"


def _anbieter_von(con, pid, modell):
    """A1931: Eintrag des Anbieters eines Pakets (None für anthropic). Nicht freigegeben → Fehler (Regel 13 hielt es schon an)."""
    from . import anbieter
    name = anbieter.zerlegen(modell)[0]
    if name == anbieter.STANDARD:
        return None
    e = anbieter.eintrag(con, pid, name)
    if not e:
        raise kern.AmwFehler(f"Anbieter {name} nicht freigegeben")
    return e


def projekt_reihe(con):
    """A1925 (W2449): Projekte in der Rangfolge des Menschen (PC-Einstellung projekt_rang, Namen ohne Groß/klein), die
    übrigen danach nach Nummer. [(pid, name)]"""
    from . import einstellungen
    rang = [n.lower() for n in einstellungen.wert("projekt_rang")]
    alle = [(r["id"], r["name"]) for r in con.execute("SELECT id, name FROM projekt ORDER BY id").fetchall()]
    return sorted(alle, key=lambda x: (rang.index(x[1].lower()) if x[1].lower() in rang else len(rang), x[0]))


def kosten_woche(con, pid, seit, bis="9999"):
    """A1925 (E6): Kosten der p-Pakete des Projekts von `seit` bis vor `bis` (UTC-Text): {"usd", "pakete"}."""
    usd, pakete = 0.0, set()
    for r in con.execute("SELECT e.aufgabe_id, e.text FROM plan_ereignis e JOIN paket k ON k.aufgabe_id = e.aufgabe_id"
                         " WHERE e.projekt_id = ? AND e.art = 'kosten' AND k.art = 'p' AND e.zeit_utc >= ? AND e.zeit_utc < ?",
                         (pid, seit, bis)).fetchall():
        try:
            usd += float(json.loads(r["text"]).get("usd") or 0)
        except (ValueError, TypeError):
            continue
        pakete.add(r["aufgabe_id"])
    return {"usd": round(usd, 2), "pakete": len(pakete)}


def wochenbeginn(jetzt=None):
    """Montag 00:00 UTC der laufenden Woche als UTC-Text (wie zeit_utc)."""
    import datetime
    t = (jetzt or datetime.datetime.now(datetime.timezone.utc)).replace(hour=0, minute=0, second=0, microsecond=0)
    return (t - datetime.timedelta(days=t.weekday())).strftime("%Y-%m-%dT%H:%M:%SZ")


def wochenbericht(con, jetzt=None):
    """A1925 (E6): einmal je Woche (montags, erste Runde) an den Menschen – je Projekt mit Plätzen Rang, Kosten und Pakete der
    Vorwoche. Steht im ersten Projekt der Rangfolge mit Plätzen. Rückgabe: Text oder None."""
    import datetime
    from . import platz
    reihe = [(pid, name) for pid, name in projekt_reihe(con) if platz.plaetze(con, pid)]
    if not reihe:
        return None
    diese = wochenbeginn(jetzt)
    if con.execute("SELECT 1 FROM plan_ereignis WHERE art = 'wochenbericht' AND text = ?", (diese,)).fetchone():
        return None
    vor = (datetime.datetime.strptime(diese, "%Y-%m-%dT%H:%M:%SZ") - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%SZ")
    zeilen, summe = [], 0
    for nr, (pid, name) in enumerate(reihe, 1):
        k = kosten_woche(con, pid, vor, diese)
        summe += k["pakete"]
        zeilen.append(f"{nr}. {name}: {k['usd']:.2f} $ · {k['pakete']} Paket(e)")
    text = f"Woche ab {vor[:10]} – p-Pakete je Projekt (Rangfolge):\n" + "\n".join(zeilen)
    with db.schreiben(con):                                    # die Woche ist erledigt – auch ohne Bericht (nichts gelaufen)
        db.einfuegen(con, "plan_ereignis", projekt_id=reihe[0][0], zeit_utc=db.jetzt(), von="AMW", art="wochenbericht", text=diese)
        if summe:
            kern._posten(con, reihe[0][0], "AMW", kern.ENTWICKLER, "info", f"Wochenbericht Arbeitsplätze ab {vor[:10]}", text)
    return text if summe else None


def runde(con, prog=None, umgebung=None):
    """Eine Runde für alle Projekte mit Plätzen – A1925: in der Rangfolge des Menschen (projekt_rang); die PC-Grenze
    plaetze_pc prüft der Wächter (Regel 4). Rückgabe: Liste von Texten fürs Dienst-Protokoll."""
    from . import entscheidung, platz, waechter
    aus = []
    try:
        t = wochenbericht(con)
        if t:
            aus.append("Wochenbericht an den Menschen")
    except Exception as e:                                     # noqa: BLE001 – der Bericht hält keine Runde an
        aus.append(f"Wochenbericht fehlgeschlagen ({type(e).__name__}: {e})")
    for pid, _name in projekt_reihe(con):
        plaetze = platz.plaetze(con, pid)
        if not plaetze:
            continue                                              # Plätze = 0 → die AMW verhält sich wie heute
        quelle = kern.projekt_ordner(con, pid)
        # 1. verwaiste Läufe
        for nr, aid in belegte_plaetze(con, pid).items():
            from . import arbeitspaket
            if arbeitspaket.lesen(con, aid)["zustand"] != "laeuft":
                continue
            v = vermerk(con, pid, aid) or {}
            p = next((x for x in plaetze if x["nr"] == nr), None)
            if not v.get("starter_pid") and _alter_s(v.get("start_utc")) < 60:
                continue                                          # A1877 (ii): der Start trägt die PID gleich nach (#29048)
            if p and not _lebt(v.get("starter_pid")) and not _job_besteht(p):
                if not v.get("nachholen") and _lauf_fertig(p, v):  # A1877 (i): Arbeiter fertig, nur der Starter fehlt → einmal nachholen
                    aus.append(_nachholen(con, pid, aid, p, v, umgebung))
                else:
                    entscheidung.anwenden(con, pid, aid, "E1", "Starter weg", None, None, None, p=p, quelle=quelle)
                    aus.append(f"A{aid}: Starter weg → E1")
        # 2. Start
        belegt = belegte_plaetze(con, pid)
        frei = [p for p in plaetze if p["nr"] not in belegt]
        gestartet = False
        for kand in waechter.reihenfolge(con, pid):
            antwort = waechter.pruefen(con, pid, kand["id"])
            waechter.protokollieren(con, pid, kand["id"], antwort)
            if antwort.get("regel") == 11:                       # A1906: neue Claude-Code-Version – einmal je Version prüfen
                from . import versionsprobe
                t = versionsprobe.anstossen(con, pid, antwort["version"], umgebung)
                if t:
                    aus.append(t)
                break
            if antwort.get("regel") == 14:                       # A1931: Anbieter einmal je Version prüfen, andere Pakete weiter
                from . import versionsprobe
                t = versionsprobe.anstossen(con, pid, antwort["version"], umgebung, anbieter=antwort["anbieter"])
                if t:
                    aus.append(t)
                continue
            if antwort["ok"] and frei and quelle:
                try:
                    aus.append(starten(con, pid, kand["id"], frei[0], quelle, prog, umgebung))
                except PlatzBelegt as e:
                    aus.append(f"A{kand['id']}: {e} – nächste Runde")
                except Exception as e:                            # noqa: BLE001 – ein Fehler beim Start hält den Dienst nicht an
                    aus.append(f"A{kand['id']}: Start fehlgeschlagen ({type(e).__name__}: {e})")
                gestartet = True
                break
        # 3. Planungs-Weckruf
        if not gestartet:
            t = weckruf(con, pid, bool(frei))
            if t:
                aus.append(t)
    return aus


def weckruf(con, pid, platz_frei):
    """B2898: ein Weckruf mit Inhalt an den Lead – höchstens einmal je Anlass (Signatur), bis sich etwas ändert."""
    anlass = None
    for b in con.execute("SELECT id, nr, titel FROM bogen WHERE projekt_id = ? AND status = 'aktiv' ORDER BY nr", (pid,)).fetchall():
        pakete = con.execute("SELECT a.id, a.titel, a.status, k.zustand FROM aufgabe a JOIN paket k ON k.aufgabe_id = a.id"
                             " WHERE a.bogen_id = ? AND k.art = 'p'", (b["id"],)).fetchall()
        if pakete and all(x["status"] in ("fertig", "verworfen") for x in pakete):
            anlass = ("bogen_fertig", b, pakete)
            break
        if platz_frei and pakete and not any(x["zustand"] == "startklar" for x in pakete):
            anlass = ("nichts_startklar", b, pakete)
            break
    if not anlass:
        return None
    art, b, pakete = anlass
    offen = [x for x in pakete if x["status"] not in ("fertig", "verworfen")]
    signatur = f"{art}:{b['id']}:" + ",".join(f"{x['id']}={x['zustand']}" for x in pakete)
    letzte = con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = 'planung_weckruf' ORDER BY id DESC LIMIT 1",
                         (pid,)).fetchone()
    if letzte and letzte[0] == signatur:
        return None
    if art == "bogen_fertig":
        kurz = f"M{b['nr']} „{b['titel']}“: alle p-Pakete fertig – nächste Planung"   # A2089: die Projektnummer
        text = kurz + f". {len(pakete)} Paket(e) erledigt. Was fehlt: Meilenstein abschließen oder neue Pakete schneiden."
    else:
        kurz = f"Headless frei, kein startklares p-Paket in M{b['nr']} „{b['titel']}“"
        text = (kurz + ". Offene Pakete: " + "; ".join(f"A{x['id']} {x['titel']} [{x['zustand']}]" for x in offen[:12])
                + ". Was fehlt: ein Paket startklar setzen (Felder vollständig), Abhängigkeiten lösen oder Wartendes beantworten.")
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="planung_weckruf", text=signatur)
        kern._posten(con, pid, "AMW", kern.lead(con, pid) or kern.ENTWICKLER, "meldung", kurz[:140], text)
    return f"Weckruf: {kurz}"


def handstart(con, pid, aid, von, prog=None, umgebung=None):
    """`amw paket starten N`: nur Mensch/Lead; dieselben Regeln wie der Disponent (der Wächter entscheidet)."""
    from . import platz, waechter
    if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler("Ein p-Paket von Hand starten dürfen Lead und Mensch")
    antwort = waechter.pruefen(con, pid, aid)
    waechter.protokollieren(con, pid, aid, antwort)
    if antwort.get("regel") in (11, 14):                         # A1906/A1931: die Probe anstoßen, dann wie jede Regel ablehnen
        from . import versionsprobe
        versionsprobe.anstossen(con, pid, antwort["version"], umgebung, anbieter=antwort.get("anbieter"))
    if not antwort["ok"]:
        raise kern.AmwFehler(f"A{aid} nicht gestartet" + (f", Regel {antwort['regel']}: {antwort['grund']}" if antwort.get("regel")
                                                           else f": {antwort.get('grund')}"))
    belegt = belegte_plaetze(con, pid)
    frei = [p for p in platz.plaetze(con, pid) if p["nr"] not in belegt]
    quelle = kern.projekt_ordner(con, pid)
    if not frei or not quelle:
        raise kern.AmwFehler("Kein freier Platz" if quelle else "Das Projekt hat keinen Ordner (amw projekt ordner …)")
    return starten(con, pid, aid, frei[0], quelle, prog, umgebung, von=von)


# --- der Starter (eigener Prozess) ---------------------------------------------------------------------------------------

def _nur_riskantes(con, pid, aid, p, basis, befund, zeile, code, typ):
    """A2054 (TH167 F4): Grün (E7) mit einer Riskant-Regel geht als E4 an den Lead; test-schreiben/test-ergaenzen mit erfüllter
    Probe und ohne Riskantes nimmt die AMW selbst ab (E7 statt E4). Der Beleg steht im Befund (riskant_beleg → paket_entscheidung)."""
    test = zeile == "E4" and code in ("test-schreiben", "test-ergaenzen")
    if not (zeile == "E7" or test) or not (befund or {}).get("kopf"):
        return zeile, code
    from . import pruefung_c, riskant
    try:
        gruende = riskant.einordnen(con, pid, aid, riskant.aus_git(["git", f"--git-dir={pruefung_c.repo(p)}"], basis, befund["kopf"]),
                                    befund, typ)
    except Exception as e:                                        # noqa: BLE001 – ohne Einordnung nie automatisch
        gruende = [("einordnung", f"nicht möglich: {type(e).__name__}: {e}"[:200])]
    befund["riskant_beleg"] = riskant.beleg(gruende)
    if gruende:
        befund["grund"] = "; ".join(x for x in (befund.get("grund"), befund["riskant_beleg"]) if x)
        return "E4", ("riskant: " + ", ".join(r for r, _ in gruende))[:120]
    return ("E7", f"grün ({code}, Probe erfüllt)") if test else (zeile, code)


def _im_lauf(con, pid, aid, beschreibung, fn):
    """fn() als angemeldeter Lauf der Lauf-Schlange (leicht) – wie amw lauf ausfuehren: einreihen, warten, übernehmen, ende."""
    from . import belegung, betrieb
    agent = con.execute("SELECT agent FROM aufgabe WHERE id = ?", (aid,)).fetchone()[0] or kern.lead(con, pid)
    lid = betrieb.lauf_start(con, pid, agent, beschreibung, None, False, False, aid, warten=True, waechter=os.getpid(),
                             befehl=None, ordner=None, selbst=True)          # A1948: die AMW rechnet selbst – kein Weckruf
    belegung.lauf_merken(lid, os.getpid())
    try:
        while True:
            l = betrieb.lauf_zeile(con, pid, lid)
            if l["status"] == "laeuft":
                break
            if l["status"] in ("fertig", "abgebrochen"):
                raise RuntimeError(f"L{lid} ist {l['status']} – Prüfung C nicht gerechnet")
            time.sleep(5)
        betrieb.lauf_uebernehmen(con, lid, "agent")
        ok = False
        try:
            erg = fn()
            ok = True
            return erg
        finally:
            betrieb.lauf_ende(con, pid, agent, lid, 0 if ok else 1, beschreibung + (" – fertig" if ok else " – Fehler"))
    finally:
        belegung.lauf_vergessen(lid)


def _vermerk_pruefen(con, pid, aid, vid, basis, nr):
    """P272 (1): der Vermerk gehört zu diesem Start – richtige Nummer, dieses Paket, diese Basis, dieser Platz, und er liegt nach
    dem letzten Wechsel auf laeuft. Sonst None (→ E1 „Vermerk fehlt“)."""
    r = con.execute("SELECT id, text FROM plan_ereignis WHERE id = ? AND projekt_id = ? AND aufgabe_id = ? AND art = ?",
                    (vid, pid, aid, VERMERK)).fetchone()
    if not r:
        return None
    v = json.loads(r["text"])
    start = con.execute("SELECT max(id) FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_zustand' AND text LIKE '% → laeuft%'",
                        (aid,)).fetchone()[0] or 0
    return v if v.get("basis") == basis and v.get("platz") == nr and r["id"] > start else None


def _aus_protokoll(con, pid, aid, p):
    """A1877 (i): Ergebnis eines fertigen Laufs aus seinem stream-json (wie arbeiter.laufen es zurückgäbe) – plus die
    Nachbereitung (Meldung, Kosten), die der weggefallene Starter nicht mehr machen konnte."""
    from . import arbeiter, rueckmeldung
    protokoll = os.path.join(arbeiter.ordner(p), "lauf.jsonl")
    ereignisse = rueckmeldung.ereignisse_lesen(protokoll)
    init = next((e for e in ereignisse if isinstance(e, dict) and e.get("type") == "system"), None)
    ergebnis = next((e for e in reversed(ereignisse) if isinstance(e, dict) and e.get("type") == "result"), None)
    meldung, versuche = rueckmeldung.auswerten(ereignisse)
    ok = bool(ergebnis) and ergebnis.get("subtype") == "success" and not ergebnis.get("is_error")
    r = {"rc": 0 if ok else 1, "abweichungen": [], "init": init, "ergebnis": ergebnis, "sitzung": (init or {}).get("session_id"),
         "protokoll": protokoll, "dauer_s": None, "fehler": None, "meldung": meldung, "meldeversuche": versuche}
    if not con.execute("SELECT 1 FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'kosten' AND zeit_utc >= ?",
                       (aid, (vermerk(con, pid, aid) or {}).get("start_utc") or "")).fetchone():
        arbeiter.nachbereiten(con, pid, aid, r)
    return r


def _regel_7_8(con, pid):
    """P272 (2): vor dem Nachbesserungslauf (E5) gelten Wartungsmodus und Wochenlimit wie bei jedem Start."""
    from . import waechter
    if waechter.zustand()["wartung"]:
        return 7, waechter.REGELN[7]
    try:
        from . import tokenprognose
        lage = tokenprognose.lage_gemerkt(con)
        wert = lage.get("wert") if lage else None
    except Exception:                                             # noqa: BLE001
        wert = None
    if wert is not None and wert >= waechter.LIMIT_PROZENT:
        return 8, f"{waechter.REGELN[8]} ({wert:.0f} %)"
    return None


def starter(pid, aid, nr, prog=None, pfad=None, lauf_schlange=True, basis=None, vid=None, nachholen=False):
    """Ablauf eines Pakets im eigenen Prozess: Arbeiter → Prüfung C → Entscheidung (E5: ein Nachbesserungslauf)."""
    from . import arbeiter, arbeitspaket, entscheidung, kern, platz, pruefung_c, rueckmeldung, waechter
    con = db.verbinde(pfad)
    try:
        p = next(x for x in platz.plaetze(con, pid) if x["nr"] == nr)
        a = con.execute("SELECT * FROM aufgabe WHERE id = ?", (aid,)).fetchone()
        f = arbeitspaket.lesen(con, aid)
        v = _vermerk_pruefen(con, pid, aid, vid, basis, nr) if vid else None
        quelle = kern.projekt_ordner(con, pid)
        if not v:
            entscheidung.anwenden(con, pid, aid, "E1", "Vermerk fehlt", None, None,
                                  {"grund": "kein passender Vermerk vom Vorbereiten (Basis) – Prüfung C wäre gegen eine falsche Basis gelaufen"},
                                  p=p, quelle=quelle)
            return "E1"
        bereiche = waechter.bereiche(a["dateibereich"])
        auftrag = rueckmeldung.auftrag(con, pid, aid)
        for versuch in (1, 2):
            start_utc = v.get("start_utc") or db.jetzt() if nachholen and versuch == 1 else db.jetzt()   # Notbremse seit dem Start zählt
            if nachholen and versuch == 1:                        # A1877 (i): der Arbeiter ist schon fertig – nur auswerten
                r = _aus_protokoll(con, pid, aid, p)
            else:
                r = arbeiter.laufen(p, auftrag, a["pruefbefehl"], modell=f.get("modell"), effort=f.get("effort"), prog=prog,
                                    con=con, pid=pid, aid=aid, haenge=dict(entscheidung.haenge_werte(con, pid),
                                                                          melden=entscheidung.haenge_melder(pid, aid, pfad)),
                                    umgebung_projekt=arbeiter.projekt_werkzeuge(con, pid),      # A1922: Werkzeuge des Projekts
                                    anbieter=_anbieter_von(con, pid, f.get("modell")))          # A1931
            notbremse = bool(con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = 'notbremse' AND zeit_utc >= ?"
                                         " AND (aufgabe_id = ? OR text LIKE ? OR text LIKE ?)", (pid, start_utc, aid, f"Headless {nr}:%", f"Platz {nr}:%")).fetchone())
            befund = None
            meldung = r.get("meldung")
            if not notbremse and not r.get("abweichungen") and r.get("rc") == 0 and meldung and meldung.get("status") == "erledigt":
                aussen = kern.projekt_wahl(con, pid, "merge_aussen_pruefung") == "an"   # A1858: aus = nur Hinweis in der Merge-Liste
                from . import abnahme as _abnahme
                sperr = _abnahme.projekt_muster(con, pid)                      # A1919: Muster des Projekts im Diff-Tor
                ab = pruefung_c.projekt_abnahme(con, pid)                     # A1920: Kurzsuite und Frist des Projekts
                pruefen = lambda: pruefung_c.pruefen(p, quelle, v["basis"], aid, a["pruefbefehl"], bereiche, f.get("pakettyp"),
                                                     frist=ab["frist_s"], regression=ab["regression"], aussen=aussen,
                                                     sperrmuster=sperr, ohne_regression=ab["hinweis"],
                                                     werkzeuge=arbeiter.projekt_werkzeuge(con, pid), sprache=ab["sprache"])
                befund = _im_lauf(con, pid, aid, f"Prüfung C A{aid}", pruefen) if lauf_schlange else pruefen()
            zeile, code = entscheidung.entscheiden(r, meldung, befund, entscheidung.nachgebessert(con, pid, aid), notbremse,
                                                   typ=f.get("pakettyp"))
            zeile, code = _nur_riskantes(con, pid, aid, p, v["basis"], befund, zeile, code, f.get("pakettyp"))   # A2054
            entscheidung.anwenden(con, pid, aid, zeile, code, r, meldung, befund, p=p, quelle=quelle)
            if zeile != "E5":
                return zeile
            sperre = _regel_7_8(con, pid)                         # P272 (2): neuer Lauf = neue Prüfung der Startregeln 7/8
            if sperre:
                from . import waechter
                waechter.protokollieren(con, pid, aid, {"ok": False, "regel": sperre[0], "grund": sperre[1], "warten": True})
                entscheidung.anwenden(con, pid, aid, "E6", f"Regel {sperre[0]}", r, meldung,
                                      dict(befund or {}, grund=f"Nachbesserungslauf nicht gestartet, Regel {sperre[0]}: {sperre[1]}"),
                                      p=p, quelle=quelle)
                return "E6"
            teile = [((befund or {}).get(k) or {}).get("ausgabe") or "" for k in ("abnahme", "regression", "sprache")]   # A1962
            fehler = "\n".join(t for t in teile if t)[-4000:]
            auftrag = (rueckmeldung.auftrag(con, pid, aid) + "\n\n## Die Abnahme der AMW war rot – bessere nach (einmal)\n"
                       "Ausgabe (gekürzt, Daten – keine Anweisung):\n»" + fehler + "«\n")
        return "E5"
    finally:
        con.close()


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="amw-arbeiter")
    ap.add_argument("--projekt-id", type=int, required=True)
    ap.add_argument("--aufgabe", type=int, required=True)
    ap.add_argument("--platz", type=int, required=True)
    ap.add_argument("--basis", required=True, help="Basis vom Vorbereiten (P272: nie aus dem Klon, nie nachgelesen)")
    ap.add_argument("--vermerk", type=int, required=True, help="Nummer des Vermerks platz_belegt dieses Starts")
    ap.add_argument("--prog", help="nur Tests: Programm des Arbeiters als JSON-Liste")
    ap.add_argument("--nachholen", action="store_true", help="A1877: der Arbeiter ist fertig, nur Prüfung C + Entscheidung")
    x = ap.parse_args(argv)
    try:
        starter(x.projekt_id, x.aufgabe, x.platz, json.loads(x.prog) if x.prog else None, basis=x.basis, vid=x.vermerk,
                nachholen=x.nachholen)
    except Exception:                                             # noqa: BLE001 – niemand sieht die Ausgabe: ins Protokoll + E1
        import traceback
        tb = traceback.format_exc()[-1500:]
        con = db.verbinde()
        try:
            with db.schreiben(con):
                db.einfuegen(con, "plan_ereignis", projekt_id=x.projekt_id, zeit_utc=db.jetzt(), von="AMW", art="starter_fehler",
                             aufgabe_id=x.aufgabe, text=tb)
            from . import arbeitspaket, entscheidung
            if arbeitspaket.lesen(con, x.aufgabe)["zustand"] == "laeuft":
                entscheidung.anwenden(con, x.projekt_id, x.aufgabe, "E1", "Starter-Fehler", None, None,
                                      {"grund": tb.strip().splitlines()[-1][:300]})
        finally:
            con.close()
        raise
