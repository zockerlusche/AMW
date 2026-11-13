"""Betrieb: Rechen-Läufe, Prüfungen, Hinweis-Sperren, Lauf-Rezepte (→ doc/architektur.md).

Läufe und Prüfbitten sind Daten, keine Freitext-Nachrichten: das nimmt dem Nachrichtenstrom das Rauschen
(heute 48 % Job-Zeilen) und macht „läuft gerade etwas?“ und „ist SHA x grün?“ abfragbar.
"""
import ctypes
import json

from . import db, kern
from . import schirm as schirm_mod     # „schirm“ ist hier schon der Name der Spalte/des Parameters

SPEICHER_GRENZE_GB = 8.0      # Vorgabe, je Projekt überschreibbar: einstellungen {"speicher_grenze_gb": …}


def auslastung(con, pid):
    """Der Rechner aus Sicht eines Projekts: wie viele Läufe laufen und warten (alle Projekte zusammen), wie viele davon
    eigene sind, wann er voraussichtlich frei wird (spätestes erwartetes Ende der laufenden, soweit angegeben) und wie
    viel Arbeitsspeicher frei ist. Über fremde Läufe steht hier nur die Anzahl."""
    import datetime
    laufen = con.execute("SELECT l.projekt_id, l.start_utc, l.erwartet_min, l.braucht_gb FROM lauf l WHERE l.status = 'laeuft' AND " + HIER,
                         (rechner(),)).fetchall()
    warten = con.execute("SELECT l.projekt_id FROM lauf l WHERE l.status = 'angemeldet' AND " + HIER, (rechner(),)).fetchall()
    enden = []
    for l in laufen:
        if l["start_utc"] and l["erwartet_min"]:
            try:
                enden.append(datetime.datetime.strptime(l["start_utc"][:19], "%Y-%m-%dT%H:%M:%S") + datetime.timedelta(minutes=l["erwartet_min"]))
            except ValueError:
                pass
    frei, gesamt = speicher_frei_gb()
    from . import belegung                              # Programme außerhalb der Warteschlange, die lange viel Speicher halten
    dauer = belegung.aktuell(con)
    from . import platte                                # Laufwerke mit Datenbank oder Projektordnern, die knapp werden
    knapp = [{k: l[k] for k in ("laufwerk", "frei_gb", "gesamt_gb", "frei_prozent", "stufe")} for l in platte.laufwerke(con) if l["stufe"]]
    return {"dauer": dauer, "dauer_gb": round(sum(x["gb"] for x in dauer), 1) or None, "platte": knapp,
            "laufen": len(laufen), "warten": len(warten), "eigene_laufen": sum(1 for l in laufen if l["projekt_id"] == pid),
            "eigene_warten": sum(1 for l in warten if l["projekt_id"] == pid),
            "frei_ab_utc": max(enden).strftime("%Y-%m-%dT%H:%M:%SZ") if enden and len(enden) == len(laufen) else None,
            "angemeldet_gb": round(sum(l["braucht_gb"] or 0 for l in laufen), 1) or None,     # so viel haben die laufenden angemeldet
            "frei_gb": frei, "gesamt_gb": gesamt, "rechner": rechner(), "vorrang": vorrang_liste(con)}
def tagesverlauf(con, pid, jetzt=None, tage=60):
    """Der Rechner heute, für den Zeitstrahl in der Planung: Läufe aller Projekte auf diesem Rechner, die heute liefen,
    laufen oder warten – eigene mit Nummer, Agent und Beschreibung, fremde nur als Zeitraum und Bedarf („anderes
    Projekt“). Dazu, was außerhalb der Warteschlange dauerhaft Speicher belegt, und je Tag der letzten `tage` Tage, wie
    viele Stunden der Rechner mit Läufen belegt war (für die gemeinsame Zeitachse der Übersicht).
    Zeiten als UTC-Text; „heute“ ist der Kalendertag in der Ortszeit des Rechners."""
    import datetime
    utc = datetime.timezone.utc
    jetzt = jetzt or datetime.datetime.now(utc)
    beginn = jetzt.astimezone().replace(hour=0, minute=0, second=0, microsecond=0)
    von, bis = beginn.astimezone(utc), (beginn + datetime.timedelta(days=1)).astimezone(utc)
    iso = lambda x: x.strftime("%Y-%m-%dT%H:%M:%SZ")

    def zeit(text):
        try:
            return datetime.datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=utc) if text else None
        except ValueError:
            return None
    zeilen = con.execute(
        "SELECT l.*, r.braucht_speicher_gb FROM lauf l LEFT JOIN rezept r ON r.id = l.rezept_id WHERE " + HIER
        + " AND (l.status IN ('angemeldet', 'laeuft') OR coalesce(l.ende_utc, l.start_utc, l.angemeldet_utc) >= ?) ORDER BY l.id",
        (rechner(), iso(von - datetime.timedelta(days=tage)))).fetchall()
    heute, je_tag = [], {}
    v = vorrang()
    reihe = {x["id"]: i for i, x in enumerate(wartende(con))}           # Wartende in der Reihenfolge der Schlange
    zeilen = sorted(zeilen, key=lambda l: (l["status"] == "angemeldet", reihe.get(l["id"], 0), l["id"]))
    for l in zeilen:
        start, ende = zeit(l["start_utc"]), zeit(l["ende_utc"])
        wartet, laeuft = l["status"] == "angemeldet", l["status"] == "laeuft"
        if start and not wartet:                       # Belegung je Tag (Ortszeit), auch über Mitternacht
            a, e = start, ende or (jetzt if laeuft else start)
            while a < e:
                tag = a.astimezone().date()
                naechster = (a.astimezone().replace(hour=0, minute=0, second=0, microsecond=0) + datetime.timedelta(days=1)).astimezone(utc)
                stueck = min(e, naechster)
                eintrag = je_tag.setdefault(tag.isoformat(), {"stuecke": [], "laeufe": set(), "eigene": set()})
                eintrag["stuecke"].append((a, stueck))
                eintrag["laeufe"].add(l["id"])
                if l["projekt_id"] == pid:
                    eintrag["eigene"].add(l["id"])
                a = stueck
        if not (wartet or laeuft or (start and (ende or start) >= von and start < bis)):
            continue
        eigen = l["projekt_id"] == pid
        heute.append({"id": l["id"] if eigen else None, "eigen": eigen, "wer": l["agent"] if eigen else None,
                      "text": kurzfassung(l["beschreibung"], 80) if eigen else None,
                      "status": "wartet" if wartet else l["status"], "angemeldet_utc": l["angemeldet_utc"] if wartet else None,
                      "start_utc": None if wartet else l["start_utc"], "ende_utc": l["ende_utc"], "erwartet_min": l["erwartet_min"],
                      "gb": _bedarf(con, l) or None, "vram_gb": l["braucht_vram_gb"], "gpu": bool(l["gpu"]), "schirm": bool(l["schirm"]),
                      "vorrang": None if vorrang_stufe(con, l["projekt_id"], v) == "normal" else vorrang_stufe(con, l["projekt_id"], v)})
    tage_liste = []
    for tag, e in sorted(je_tag.items()):
        belegt, bis_jetzt = datetime.timedelta(), None          # Vereinigung der Zeiträume: gleichzeitige Läufe zählen einmal
        for a, b in sorted(e["stuecke"]):
            if bis_jetzt is None or a > bis_jetzt:
                belegt += b - a
                bis_jetzt = b
            elif b > bis_jetzt:
                belegt += b - bis_jetzt
                bis_jetzt = b
        tage_liste.append({"tag": tag, "stunden": round(belegt.total_seconds() / 3600, 2), "laeufe": len(e["laeufe"]), "eigene": len(e["eigene"])})
    from . import belegung
    return {"rechner": rechner(), "von_utc": iso(von), "bis_utc": iso(bis), "jetzt_utc": iso(jetzt), "gesamt_gb": speicher_frei_gb()[1],
            "laeufe": heute, "dauer": belegung.aktuell(con), "tage": tage_liste}


# Ein laufender schwerer Lauf hält seinen angemeldeten Bedarf frei, solange er läuft (_vorgemerkt_gb) – abzüglich dessen,
# was er nachweislich schon belegt. Sonst ließe die Schlange einen zweiten Lauf ein, während der erste noch wächst.


def _einstellung(con, pid, schluessel, vorgabe):
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        return json.loads(r["einstellungen"] or "{}").get(schluessel, vorgabe)
    except ValueError:
        return vorgabe


def speicher_frei_gb():
    class MS(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                    ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                    ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                    ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                    ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
    try:
        m = MS()
        m.dwLength = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return round(m.ullAvailPhys / 2**30, 1), round(m.ullTotalPhys / 2**30, 1)
    except (AttributeError, OSError):
        return None, None


# --- Läufe ---------------------------------------------------------------------------------------

def speicher_grenze(con, pid):
    """Ab so viel freiem Arbeitsspeicher starten schwere Läufe (Einstellung des Projekts, sonst die Vorgabe)."""
    return float(_einstellung(con, pid, "speicher_grenze_gb", SPEICHER_GRENZE_GB))


def _grenze(con, pid, braucht_gb, schwer):
    if braucht_gb:
        return float(braucht_gb)
    return speicher_grenze(con, pid) if schwer else 0.0


def _bedarf(con, l):
    """Arbeitsspeicher, den ein Lauf braucht: seine eigene Angabe, sonst die des Rezepts, sonst die Grenze seines Projekts."""
    return _grenze(con, l["projekt_id"], l["braucht_gb"] or l["braucht_speicher_gb"], l["schwer"])


def rechner():
    """Name dieses Rechners (Einstellung „rechner“). Die Warteschlange gilt je Rechner: Läufe, die auf einem anderen
    angemeldet wurden, zählt sie nicht. Ein Lauf ohne Angabe (Bestand) gilt als Lauf dieses Rechners."""
    from . import einstellungen
    return einstellungen.wert("rechner")


HIER = "(l.rechner IS NULL OR l.rechner = ?)"        # SQL: nur Läufe dieses Rechners (Alias l)


def vram_frei_gb():
    """Freier Grafikspeicher in GB (nvidia-smi) oder None, wenn er sich nicht messen lässt."""
    import subprocess
    try:
        aus = subprocess.run(["nvidia-smi", "--query-gpu=memory.free", "--format=csv,noheader,nounits"], capture_output=True,
                             text=True, timeout=10, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        werte = [int(x.strip()) for x in aus.stdout.split("\n") if x.strip().isdigit()]
        return round(max(werte) / 1024, 1) if not aus.returncode and werte else None
    except (OSError, ValueError, subprocess.SubprocessError):
        return None


def platte_frei_gb(con, pid):
    """Freier Platz in GB auf dem Laufwerk des Projektordners (ohne Ordner: auf dem der Datenbank) oder None."""
    import os
    import shutil
    ort = kern.projekt_ordner(con, pid) or os.path.dirname(db.db_pfad())
    try:
        return round(shutil.disk_usage(ort).free / 2**30, 1)
    except OSError:
        return None


def _mittel_fehlen(con, l):
    """Grund, wenn Grafikspeicher oder Platz auf der Festplatte für diesen Lauf nicht reichen (nur wenn er einen Bedarf
    dafür angemeldet hat und sich der freie Wert messen lässt)."""
    if l["braucht_vram_gb"]:
        frei = vram_frei_gb()
        if frei is not None and frei < l["braucht_vram_gb"]:
            return f"nur {frei:g} GB Grafikspeicher frei, gebraucht {l['braucht_vram_gb']:g} GB"
    if l["braucht_platte_gb"]:
        frei = platte_frei_gb(con, l["projekt_id"])
        if frei is not None and frei < l["braucht_platte_gb"]:
            return f"nur {frei:g} GB auf der Festplatte frei, gebraucht {l['braucht_platte_gb']:g} GB"
    return None


def reserve_gb():
    """So viel Arbeitsspeicher bleibt beim Einlass schwerer Läufe frei (Einstellung dieses PCs, Vorgabe 3 GB)."""
    from . import einstellungen
    return float(einstellungen.wert("speicher_reserve_gb"))


def cpu_laeufe():
    """So viele schwere Läufe ohne Fenster und ohne Grafikkarte rechnen zugleich (Einstellung dieses PCs, Vorgabe 2)."""
    from . import einstellungen
    return einstellungen.wert("cpu_laeufe")


def _plaetze(schwer, schirm, gpu=0, agent=None, pid=None):
    """Zwei Spuren: Grafikkarte und Schirm (PC-weit ein Lauf zur Zeit; ein Fenster rechnet auf der Grafikkarte) und
    „cpu“ für schwere Läufe ohne beides (cpu_laeufe() zugleich). agent: schwere Läufe eines Agenten nie gleichzeitig –
    er rechnet in seinem Klon, zwei Godot-Imports im selben Klon gehen schief. KI-Aufträge rechnet der Dienst (ohne Klon)."""
    p = {"schirm", "gpu"} if schirm else ({"gpu"} if gpu else set())   # ein Fenster belegt auch die Grafikkarte
    if schwer and not p:
        p.add("cpu")
    if schwer and agent:
        p.add(f"agent:{pid}:{agent}")              # je Projekt: gleiche Kennung in zwei Projekten = zwei Agenten, zwei Klone
    return p


def _plaetze_von(l):
    return _plaetze(l["schwer"], l["schirm"], l["gpu"], None if l["ki_auftrag"] else l["agent"], l["projekt_id"])


MENSCH_RANG = 1000            # ab hier: vom Menschen vorgezogen – gilt über alle Projekte; darunter sortiert ein Lead nur
                              # die Läufe seines eigenen Projekts um


def _zeit_kurz(utc):
    """„16:05“ (Ortszeit) aus einem UTC-Text – für Hinweise auf fremde Läufe."""
    import datetime
    try:
        t = datetime.datetime.strptime(utc[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return "?"
    return t.astimezone().strftime("%H:%M")


def lauf_nennen(pid, l, mit_text=True):
    """Ein Lauf im Text. Eigener Lauf: Nummer, Agent, Beschreibung. Lauf eines anderen Projekts: nur, dass der Rechner
    belegt ist und bis wann – nie Agent, Beschreibung oder Projekt (die Projekte mischen sich nicht)."""
    if l["projekt_id"] == pid:
        return f"L{l['id']} von {l['agent']}" + (f": {l['beschreibung']}" if mit_text else "")
    seit = f", läuft seit {_zeit_kurz(l['start_utc'])}" if l["start_utc"] else ""
    bis = ""
    if l["start_utc"] and l["erwartet_min"]:
        import datetime
        ende = datetime.datetime.strptime(l["start_utc"][:19], "%Y-%m-%dT%H:%M:%S") + datetime.timedelta(minutes=l["erwartet_min"])
        bis = f", voraussichtlich bis {_zeit_kurz(ende.strftime('%Y-%m-%dT%H:%M:%S'))}"
    bedarf = f", {l['braucht_gb']:g} GB" if "braucht_gb" in l.keys() and l["braucht_gb"] else ""
    return f"L{l['id']} (anderes Projekt{seit}{bis}{bedarf})"


def _besetzt(con, pid, plaetze):
    """(Grund, Platz), wenn ein laufender Lauf einen der Plätze belegt, sonst (None, None)."""
    for p in sorted(x for x in plaetze if x.startswith("agent:")):
        _, agent_pid, agent = p.split(":", 2)
        b = con.execute("SELECT l.id, l.beschreibung FROM lauf l LEFT JOIN ki_auftrag k ON k.lauf_id = l.id WHERE l.projekt_id = ?"
                        " AND l.agent = ? AND l.status = 'laeuft' AND l.schwer = 1 AND k.id IS NULL AND " + HIER + " ORDER BY l.id LIMIT 1",
                        (int(agent_pid), agent, rechner())).fetchone()
        if b:
            return f"L{b['id']} von {agent} läuft noch (ein Agent rechnet nie zwei schwere Läufe zugleich – sein Klon): {b['beschreibung']}", p
    if plaetze & {"gpu", "schirm"}:                  # Grafikkarte und Bildschirm: ein Lauf zur Zeit auf dem ganzen Rechner
        b = con.execute("SELECT l.id, l.projekt_id, l.agent, l.beschreibung, l.gpu, l.start_utc, l.erwartet_min, l.braucht_gb FROM lauf l"
                        " WHERE l.status = 'laeuft' AND (l.gpu = 1 OR l.schirm = 1) AND " + HIER + " ORDER BY l.id LIMIT 1", (rechner(),)).fetchone()
        if b:
            platz = "gpu" if "gpu" in plaetze else "schirm"
            if b["gpu"]:
                return f"GPU-Lauf {lauf_nennen(pid, b)} belegt die Grafikkarte", platz
            return f"Lauf mit Fenster {lauf_nennen(pid, b)} läuft noch", platz
    if "cpu" in plaetze:
        r = con.execute("SELECT l.id FROM lauf l WHERE l.status = 'laeuft' AND l.schwer = 1 AND l.schirm = 0 AND l.gpu = 0 AND " + HIER
                        + " ORDER BY l.id", (rechner(),)).fetchall()
        n = cpu_laeufe()
        if len(r) >= n:
            return f"CPU-Spur voll ({len(r)} von {n} Läufen ohne Fenster: {', '.join('L%d' % x['id'] for x in r)})", "cpu"
    return None, None


ANLAUF_MIN = 15      # so lange hält ein laufender Lauf OHNE eigene Bedarfsangabe die Grenze seines Projekts frei (A1623 c)


def _vormerkungen(con, jetzt=None):
    """Was laufende schwere Läufe dieses Rechners noch für sich brauchen – [(Lauf-Zeile, GB)], nur Einträge > 0.
    Je Lauf: angemeldeter Bedarf (eigene Angabe, sonst Rezept, sonst Grenze seines Projekts) minus dem, was sein
    Prozessbaum schon belegt – nie unter 0. Den Prozess kennt die AMW bei „amw lauf ausfuehren“; sonst (von Hand
    gestartet, KI-Auftrag) gilt der ganze Bedarf als vorgemerkt – lieber einen Lauf warten lassen als zwei abbrechen.
    Ein Lauf OHNE eigene Angabe (nur die pauschale Grenze seines Projekts) hält sie nur in den ersten ANLAUF_MIN Minuten
    frei: danach steckt, was er wirklich belegt, schon in der Messung des freien Speichers."""
    import datetime
    r = con.execute("SELECT l.*, r.braucht_speicher_gb FROM lauf l LEFT JOIN rezept r ON r.id = l.rezept_id"
                    " WHERE l.status = 'laeuft' AND l.schwer = 1 AND " + HIER + " ORDER BY l.id", (rechner(),)).fetchall()
    if not r:
        return []
    from . import belegung
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    liste, aus = None, []
    for x in r:
        if not (x["braucht_gb"] or x["braucht_speicher_gb"]) and x["start_utc"]:
            try:
                seit = jetzt - datetime.datetime.strptime(x["start_utc"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                seit = None
            if seit is not None and seit > datetime.timedelta(minutes=ANLAUF_MIN):
                continue
        bedarf, schon = _bedarf(con, x), 0.0
        pid = belegung.lauf_pid(x["id"])
        if pid:
            liste = belegung.prozesse() if liste is None else liste
            schon = belegung.baum_gb(liste, pid) or 0.0
        if bedarf - schon > 0:
            aus.append((x, round(bedarf - schon, 1)))
    return aus


def _vorgemerkt_gb(con):
    """Summe von _vormerkungen()."""
    return round(sum(gb for _, gb in _vormerkungen(con)), 1)


def _speicher_fehlt(con, pid, l_grenze, speicher_frei):
    """Grund, wenn für einen Lauf mit dieser Grenze nicht genug frei ist (abzüglich dessen, was laufende Läufe noch für
    sich vorgemerkt haben) – jeder schwere Lauf braucht seine Grenze für sich."""
    if not l_grenze or speicher_frei is None:
        return None
    vm = _vormerkungen(con)
    vorgemerkt, reserve = round(sum(gb for _, gb in vm), 1), reserve_gb()
    if speicher_frei - vorgemerkt - reserve < l_grenze:
        wer = ": " + ", ".join(f"{gb:g} GB für {lauf_nennen(pid, x, mit_text=False)}" for x, gb in vm) if len(vm) else ""
        return f"nur {speicher_frei} GB frei" + (f" ({vorgemerkt:g} GB davon für laufende Läufe vorgemerkt{wer})" if vorgemerkt else "") \
            + f", gebraucht {l_grenze:g} GB" + (f" und {reserve:g} GB Reserve" if reserve else "")
    return None


def _vordermann(con, pid, x, speicher_frei, von=False):
    """Ein wartender Lauf vor einem anderen, als Text – mit Vorrang und, wenn er auf Arbeitsspeicher wartet, wie viel er
    braucht und wie viel nutzbar ist (A1623 a). Fremde Läufe ohne Projekt, Agent und Inhalt."""
    eigen = x["projekt_id"] == pid
    teile = [x["agent"] if eigen else "anderes Projekt"]
    st = vorrang_stufe(con, x["projekt_id"])
    if st != "normal":
        teile.append(t_vorrang(st) + (f" für {projekt_name(con, pid)}" if eigen else ""))
    if lauf_stufe(con, x) > VORRANG[st]:
        teile.append("aufgerückt nach Wartezeit")
    if speicher_frei is not None and _bedarf(con, x):
        nutzbar = round(speicher_frei - _vorgemerkt_gb(con) - reserve_gb(), 1)
        if nutzbar < _bedarf(con, x):
            teile.append(f"wartet auf Arbeitsspeicher: braucht {_bedarf(con, x):g} GB, {max(nutzbar, 0):g} GB nutzbar")
    if von and eigen:                                  # wie lauf_nennen: „L12 von CC2“ (Zusätze dahinter)
        return f"L{x['id']} von {x['agent']}" + (f" ({', '.join(teile[1:])})" if teile[1:] else "")
    return f"L{x['id']} ({', '.join(teile)})"


# --- Vorrang der Projekte (A1623): Einstellung dieses PCs, je Projektname hoch | normal | niedrig ----------------------

VORRANG = {"hoch": 2, "normal": 1, "niedrig": 0}


def vorrang():
    """{Projektname: „hoch“ | „niedrig“} – Einstellung dieses PCs; ein Projekt, das fehlt, hat „normal“."""
    from . import einstellungen
    return einstellungen.wert("vorrang")


def projekt_name(con, pid):
    r = con.execute("SELECT name FROM projekt WHERE id = ?", (pid,)).fetchone()
    return r["name"] if r else "?"


def vorrang_stufe(con, pid, v=None):
    """„hoch“ | „normal“ | „niedrig“ eines Projekts auf diesem Rechner."""
    v = vorrang() if v is None else v
    return v.get(projekt_name(con, pid), "normal") if v else "normal"


def vorrang_liste(con):
    """Projekte dieses Rechners mit Vorrang ≠ normal: [{"projekt", "stufe"}] – hoch zuerst (für den Leitstand, nur am PC)."""
    v = vorrang()
    namen = [r["name"] for r in con.execute("SELECT name FROM projekt ORDER BY name")]
    return sorted(({"projekt": n, "stufe": v[n]} for n in namen if n in v), key=lambda x: (-VORRANG[x["stufe"]], x["projekt"]))


MELDUNG_MIN = 20     # wartet ein Lauf mit Vorrang „hoch“ länger, bekommt der Mensch eine Meldung mit Grund (A1623 V2)


def aufruecken_min():
    """Je so viele Minuten Wartezeit rückt ein wartender Lauf eine Stufe höher (Einstellung dieses PCs; 0 = aus)."""
    from . import einstellungen
    return einstellungen.wert("vorrang_aufruecken_min")


def platz_freihalten():
    from . import einstellungen
    return einstellungen.wert("vorrang_platz_freihalten")


def _minuten_seit(utc, jetzt=None):
    import datetime
    try:
        a = datetime.datetime.strptime(utc[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)
    except (TypeError, ValueError):
        return 0.0
    return max(0.0, ((jetzt or datetime.datetime.now(datetime.timezone.utc)) - a).total_seconds() / 60)


def lauf_stufe(con, l, v=None, jetzt=None):
    """Vorrang eines wartenden Laufs als Zahl (2 hoch, 1 normal, 0 niedrig): die Stufe seines Projekts, je
    aufruecken_min() Minuten Wartezeit eine höher, höchstens „hoch“ – so kommt auch „niedrig“ sicher dran."""
    basis = VORRANG[vorrang_stufe(con, l["projekt_id"], v)]
    n = aufruecken_min()
    if n and basis < VORRANG["hoch"] and l["status"] == "angemeldet":
        basis = min(VORRANG["hoch"], basis + int(_minuten_seit(l["angemeldet_utc"], jetzt) // n))
    return basis


def _halten_fuer(con, kandidaten, stufe_neu, v=None, speicher_frei=None):
    """Platz freihalten (A1623 V2): der größte Speicherbedarf eines wartenden Laufs mit „hoch“, der vor einem Lauf der
    Stufe stufe_neu steht – (GB, Lauf) oder (0, None). Aus, wenn die Einstellung aus ist."""
    if not platz_freihalten():
        return 0.0, None
    beste = (0.0, None)
    for h in kandidaten:
        if lauf_stufe(con, h, v) == VORRANG["hoch"] and stufe_neu < VORRANG["hoch"] and _bedarf(con, h) > beste[0] \
                and not _passt_nie(con, h, speicher_frei_gb()[0] if speicher_frei is None else speicher_frei):
            beste = (float(_bedarf(con, h)), h)
    return beste


def vorrang_meldungen(con, jetzt=None):
    """Wartet ein Lauf eines Projekts mit Vorrang „hoch“ länger als MELDUNG_MIN Minuten, bekommt der Mensch einmal eine
    Meldung mit dem Wartegrund (im Projekt des Laufs). Rückgabe: Texte der neuen Meldungen."""
    v = vorrang()
    if not v:
        return []
    aus = []
    for l in wartende(con):
        if vorrang_stufe(con, l["projekt_id"], v) != "hoch" or _minuten_seit(l["angemeldet_utc"], jetzt) < MELDUNG_MIN:
            continue
        kurz = f"L{l['id']} mit Vorrang wartet seit {int(_minuten_seit(l['angemeldet_utc'], jetzt))} Minuten"
        if con.execute("SELECT 1 FROM nachricht WHERE projekt_id = ? AND von = 'AMW' AND art = 'meldung' AND kurz LIKE ?",
                       (l["projekt_id"], f"L{l['id']} mit Vorrang wartet seit %")).fetchone():
            continue
        grund = wartegrund(con, l["projekt_id"], l)
        with db.schreiben(con):
            kern._posten(con, l["projekt_id"], "AMW", kern.ENTWICKLER, "meldung", kurz,
                         f"{l['agent']}: {l['beschreibung']}\n\nWarum: {grund}\n\nNichts wird abgebrochen. Vorziehen kannst nur du: "
                         f"amw lauf vorziehen {l['id']} (oder in der Planung › Rechner – heute).", aufgabe_id=l["aufgabe_id"])
        aus.append(kurz)
    return aus


def t_vorrang(stufe):
    return {"hoch": "Vorrang", "niedrig": "niedriger Vorrang"}.get(stufe, "")


def _lebt(con, pid, l):
    """Darf der Lauf jetzt überhaupt starten: KI-Auftrag (rechnet der Dienst) oder Agent mit lebender Sitzung, ohne Halt."""
    if l["nachts"]:                              # KI-Auftrag mit --nachts: außerhalb des KI-Fensters wie nicht da
        from . import ki
        if ki.nacht_sperre(con):
            return False
    lebt = l["ki_auftrag"] or con.execute(
        "SELECT 1 FROM sitzung s JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ?"
        " AND a.kennung = ? AND s.zustand = 'aktiv'", (pid, l["agent"])).fetchone()
    if not lebt:                                 # „amw lauf ausfuehren“ wartet als eigener Prozess – der lebt, solange er wartet,
        from . import belegung                   # egal in welchem Projekt die Sitzung des Agenten angemeldet ist
        lebt = belegung.prozess_da(belegung.lauf_pid(l["id"]))
    return bool(lebt) and not kern.halt_gilt(con, pid, l["agent"])


def _schlange_leer(con):
    """Läuft gerade kein schwerer Lauf der Warteschlange auf diesem Rechner?"""
    return not con.execute("SELECT 1 FROM lauf l WHERE l.status = 'laeuft' AND l.schwer = 1 AND " + HIER, (rechner(),)).fetchone()


def _passt_nie(con, l, speicher_frei, leer=None):
    """Ein wartender Lauf, für den der Arbeitsspeicher auch bei leerer Schlange nicht reicht (es läuft kein schwerer Lauf
    und er passt trotzdem nicht): darauf zu warten hilft nichts – nur Speicher außerhalb der Schlange wird frei. Er sperrt
    dann niemanden, und für ihn wird kein Platz frei gehalten (sonst stand die ganze Schlange, Befund CCamw 13.11.)."""
    if speicher_frei is None or not _bedarf(con, l):
        return False
    leer = _schlange_leer(con) if leer is None else leer
    return leer and bool(_speicher_fehlt(con, l["projekt_id"], _bedarf(con, l), speicher_frei))


def _gesperrt(con, pid, wartend, schirm_zu, bis=None, speicher_frei=None):
    """Plätze, auf die schon jemand in der Schlange wartet – dort überholt niemand. {platz: [Lauf-Zeilen]}.
    Dieselben Regeln wie warteschlange(): wer auf seinen Klon oder den Bildschirm wartet, sperrt nur diesen Platz (hält die
    CPU-Spur nicht auf); wer jetzt starten könnte oder auf Speicher wartet, sperrt alle seine Plätze; wer hinter einem
    anderen hängt, ohne Sitzung ist oder im Halt, sperrt nichts. bis: nur Läufe davor."""
    aus = {}
    for w in wartend:
        if bis is not None and w["id"] == bis:
            break
        pw = _plaetze_von(w)
        if pw & set(aus):
            continue
        if w["schirm"] and schirm_zu:
            hier = {"schirm"}
        elif not _lebt(con, w["projekt_id"], w):     # jeder Lauf nach den Regeln seines eigenen Projekts
            continue
        else:
            _, platz = _besetzt(con, w["projekt_id"], pw)
            if not platz and _passt_nie(con, w, speicher_frei):
                continue                             # passt auch bei leerer Schlange nicht: hält niemanden auf
            hier = {platz} if platz else pw          # zu wenig Speicher oder gleich dran: alle seine Plätze
        for p in hier:
            aus.setdefault(p, []).append(w)
    return aus


def wartende(con, pid=None):
    """Die Warteschlange dieses Rechners – über alle Projekte (eine Datenbank = ein Rechner). Vom Menschen Vorgezogene
    stehen ganz vorn; danach zuerst die Projekte mit Vorrang „hoch“, dann „normal“, dann „niedrig“ (Einstellung dieses
    PCs, A1623) – innerhalb einer Stufe: wer zuerst kommt, ist zuerst dran. Ein Lead sortiert nur die Läufe seines
    eigenen Projekts um (sie tauschen untereinander die Plätze, kein fremder Lauf rückt dadurch nach hinten).
    pid ist nur noch der Betrachter (wer fragt), kein Filter. ki_auftrag: der Lauf ist ein KI-Auftrag (führt der Dienst
    aus, kein Weckruf an den Agenten); nachts: startet erst im KI-Fenster."""
    zeilen = con.execute("SELECT l.*, r.braucht_speicher_gb, k.id AS ki_auftrag, json_extract(k.parameter, '$.nachts') AS nachts FROM lauf l LEFT JOIN rezept r ON r.id = l.rezept_id"
                         " LEFT JOIN ki_auftrag k ON k.lauf_id = l.id WHERE l.status = 'angemeldet' AND " + HIER + " ORDER BY l.id",
                         (rechner(),)).fetchall()
    oben = sorted((z for z in zeilen if z["rang"] >= MENSCH_RANG), key=lambda z: (-z["rang"], z["id"]))
    v = vorrang()
    stufe = {z["id"]: lauf_stufe(con, z, v) for z in zeilen}      # mit Aufrücken nach Wartezeit (A1623 V2)
    basis = {p: VORRANG[vorrang_stufe(con, p, v)] for p in {z["projekt_id"] for z in zeilen}}
    # bei gleicher Stufe zuerst die Stufe des Projekts (echtes „hoch“ vor aufgerücktem, TL #23284), dann Ankunft
    rest = sorted((z for z in zeilen if z["rang"] < MENSCH_RANG), key=lambda z: (-stufe[z["id"]], -basis[z["projekt_id"]], z["id"]))
    je_projekt = {}
    for z in rest:
        je_projekt.setdefault(z["projekt_id"], []).append(z)
    zeiger = {p: iter(sorted(v, key=lambda z: (-z["rang"], z["id"]))) for p, v in je_projekt.items()}
    return oben + [next(zeiger[z["projekt_id"]]) for z in rest]      # die Plätze eines Projekts bleiben seine Plätze


def lauf_start(con, pid, agent, beschreibung, rezept=None, schwer=True, schirm=False, aufgabe_id=None,
               speicher_frei=None, warten=False, erwartet_min=None, gpu=False, dazu=None, sperre=None,
               braucht_gb=None, braucht_vram_gb=None, braucht_platte_gb=None):
    """Meldet einen Lauf an und startet ihn, wenn er darf. Regeln: kein Halt; Schirm und Grafikkarte PC-weit ein Lauf
    zur Zeit; schwere Läufe ohne beides parallel bis cpu_laeufe(); ein Agent nie zwei schwere zugleich; freier Speicher
    ≥ Grenze je Lauf; niemand überholt die Warteschlange auf seinem Platz. Darf er nicht: ohne warten AmwFehler mit Grund (nichts wird angelegt), mit warten eingereiht (status
    'angemeldet'); warteschlange() startet ihn, sobald er dran ist, und weckt den Agenten mit einer Freigabe.
    dazu(lid): läuft in derselben Transaktion (KI-Auftrag zum Lauf) – nie ein Lauf ohne seinen Auftrag.
    sperre: Grund, warum er jetzt nicht starten darf, obwohl der Platz frei wäre (KI-Auftrag mit --nachts)."""
    if kern.halt_gilt(con, pid, agent):
        raise kern.AmwFehler("HALT gilt – keine Läufe starten")
    rez = None
    if rezept:
        rez = con.execute("SELECT * FROM rezept WHERE projekt_id = ? AND name = ?", (pid, rezept)).fetchone()
        if not rez:
            raise kern.AmwFehler(f"Rezept „{rezept}“ gibt es nicht")
        schwer, schirm, gpu = bool(rez["schwer"]), bool(rez["braucht_schirm"]), bool(rez["gpu"]) or gpu
    for name, wert in (("Arbeitsspeicher", braucht_gb), ("Grafikspeicher", braucht_vram_gb), ("Festplatte", braucht_platte_gb)):
        if wert is not None and not 0 < float(wert) <= 2048:
            raise kern.AmwFehler(f"Bedarf {name}: eine Zahl in GB zwischen 0 und 2048")
    grenze = _grenze(con, pid, braucht_gb or (rez["braucht_speicher_gb"] if rez else None), schwer)   # eigene Angabe geht vor
    if speicher_frei is None:
        speicher_frei = speicher_frei_gb()[0]
    plaetze = _plaetze(schwer, schirm, gpu, None if dazu else agent, pid)
    with db.schreiben(con):
        w = wartende(con, pid)
        eigene = VORRANG[vorrang_stufe(con, pid)]          # nur wer nach der Reihenfolge vor ihm stünde, hält ihn auf
        w_vor = [x for x in w if x["rang"] >= MENSCH_RANG             # ein neuer Lauf hat noch nicht gewartet: Stufe = Projekt-Stufe;
                 or (lauf_stufe(con, x), VORRANG[vorrang_stufe(con, x["projekt_id"])]) >= (eigene, eigene)]   # Gleichstand wie wartende()
        schirm_zu = schirm_mod.sperrgrund(con) if schirm or any(x["schirm"] for x in w) else None
        grund = sperre or (schirm_zu if schirm else None) or _besetzt(con, pid, plaetze)[0]
        gesperrt = _gesperrt(con, pid, w_vor, schirm_zu, speicher_frei=speicher_frei) if not sperre else {}
        vor = sorted({x["id"]: x for p in plaetze for x in gesperrt.get(p, [])}.values(), key=lambda x: x["id"])
        if not grund and vor:
            grund = "Warteschlange: " + ", ".join(_vordermann(con, pid, x, speicher_frei, von=True) for x in vor) + " wartet schon"
        if not grund:
            grund = _speicher_fehlt(con, pid, grenze, speicher_frei)
        if not grund and grenze:
            halten, h = _halten_fuer(con, w, eigene, speicher_frei=speicher_frei)
            if halten and _speicher_fehlt(con, pid, grenze + halten, speicher_frei):
                grund = f"Platz frei gehalten für L{h['id']} ({h['agent'] if h['projekt_id'] == pid else 'anderes Projekt'}) mit Vorrang: braucht {halten:g} GB"
        if not grund:
            grund = _mittel_fehlen(con, {"projekt_id": pid, "braucht_vram_gb": braucht_vram_gb, "braucht_platte_gb": braucht_platte_gb})
        if grund and not warten:
            raise kern.AmwFehler(grund + " – mit --warten einreihen")
        t = db.jetzt()
        lid = db.einfuegen(con, "lauf", projekt_id=pid, agent=agent, rezept_id=rez["id"] if rez else None,
                           beschreibung=beschreibung, schwer=int(schwer), schirm=int(schirm), gpu=int(bool(gpu)),
                           status="angemeldet" if grund else "laeuft", angemeldet_utc=t, start_utc=None if grund else t,
                           speicher_frei_gb=speicher_frei, aufgabe_id=aufgabe_id, erwartet_min=erwartet_min,
                           braucht_gb=braucht_gb, braucht_vram_gb=braucht_vram_gb, braucht_platte_gb=braucht_platte_gb, rechner=rechner())
        if dazu:
            dazu(lid)
        else:                                    # ein KI-Auftrag rechnet nicht im Namen des Agenten
            kern.taetigkeit_auto(con, pid, agent, f"L{lid} {beschreibung or ''}".strip(), aufgabe_id)
        return lid


def kurzfassung(text, n=110):
    """Für Zeilen mit fester Länge (Weckruf): ganz, oder an einer Wortgrenze gekürzt mit „…“ – nie mitten im Wort."""
    text = " ".join((text or "").split())
    if len(text) <= n:
        return text
    stueck = text[:n - 1]
    return (stueck.rsplit(" ", 1)[0] if " " in stueck else stueck).rstrip(",;:–- ") + " …"


def warteschlange(con, pid=None, speicher_frei=None):
    """Startet wartende Läufe der Reihe nach, sobald ihr Platz frei ist, und weckt den Agenten (Freigabe) – für den ganzen
    Rechner, über alle Projekte (pid ist nur noch aus alten Aufrufen da).
    Wer warten muss, hält alle hinter sich auf, die den Platz brauchen, an dem er hängt – niemand überholt (wer auf
    seinen Klon wartet, hält die CPU-Spur nicht auf; ein Lauf ohne Fenster nicht den Bildschirm). Agenten ohne
    lebende Sitzung oder im Halt werden übersprungen, bis sie wieder da sind. Läufe mit Fenster nur bei freiem Bildschirm
    und ruhigem PC (schirm.py). Rückgabe: gestartete Lauf-Nummern."""
    if not wartende(con, pid):
        return []
    if speicher_frei is None:
        speicher_frei = speicher_frei_gb()[0]
    gestartet, gesperrt, halten = [], set(), 0.0
    freihalten = platz_freihalten()
    with db.schreiben(con):
        schirm_zu = any(l["schirm"] for l in wartende(con, pid)) and schirm_mod.sperrgrund(con)
        for l in wartende(con, pid):
            hoch = lauf_stufe(con, l) == VORRANG["hoch"]
            plaetze = _plaetze_von(l)
            if plaetze & gesperrt:
                continue
            if l["schirm"] and schirm_zu:            # hält nur andere Läufe mit Fenster auf, nicht die ohne Fenster
                gesperrt.add("schirm")
                continue
            lp = l["projekt_id"]                     # jeder Lauf nach den Regeln seines eigenen Projekts
            if not _lebt(con, lp, l):                # KI-Auftrag: rechnet der Dienst, der Agent darf schlafen
                continue
            _, platz = _besetzt(con, lp, plaetze)
            if platz:                                # hält nur auf, wer genau diesen Platz braucht
                gesperrt.add(platz)
                if hoch and freihalten:              # sein Speicher bleibt frei, bis sein Platz frei wird (A1623 V2)
                    halten = max(halten, float(_bedarf(con, l)))
                continue
            if _speicher_fehlt(con, lp, _bedarf(con, l), speicher_frei) or _mittel_fehlen(con, l):
                if not gestartet and _passt_nie(con, l, speicher_frei) and not _mittel_fehlen(con, l):
                    continue                         # passt auch bei leerer Schlange nicht: sperrt niemanden, kein Platz frei halten
                gesperrt |= plaetze
                if hoch and freihalten:
                    halten = max(halten, float(_bedarf(con, l)))
                continue
            if not hoch and halten and _bedarf(con, l) and _speicher_fehlt(con, lp, _bedarf(con, l) + halten, speicher_frei):
                continue                             # ließe zu wenig für den wartenden Vorrang-Lauf übrig
            con.execute("UPDATE lauf SET status = 'laeuft', start_utc = ?, speicher_frei_gb = ? WHERE id = ?",
                        (db.jetzt(), speicher_frei, l["id"]))
            if l["ki_auftrag"]:                      # der KI-Arbeiter im Dienst holt ihn ab
                gestartet.append(l["id"])
                continue
            kern._posten(con, lp, "AMW", l["agent"], "freigabe", f"L{l['id']} ist dran – jetzt starten: {kurzfassung(l['beschreibung'])}",
                         f"{l['beschreibung']}\n\nDer Platz ist für dich reserviert. Am Ende: amw lauf ende {l['id']} --rc <Code>. "
                         f"Kannst du gerade nicht: amw lauf ende {l['id']} --abgebrochen (gibt den Platz frei).",
                         aufgabe_id=l["aufgabe_id"])
            gestartet.append(l["id"])
    return gestartet


def lauf_zeile(con, pid, lid):
    l = con.execute("SELECT l.*, r.braucht_speicher_gb FROM lauf l LEFT JOIN rezept r ON r.id = l.rezept_id"
                    " WHERE l.id = ? AND l.projekt_id = ?", (lid, pid)).fetchone()
    if not l:
        raise kern.AmwFehler(f"Lauf L{lid} gibt es nicht")
    return l


def wartegrund(con, pid, l, speicher_frei=None):
    """Warum ein eingereihter Lauf noch nicht dran ist – dieselben Regeln wie warteschlange(), als Text."""
    w = wartende(con, pid)
    platz = next((i for i, x in enumerate(w, 1) if x["id"] == l["id"]), None)
    ki_auftrag = con.execute("SELECT id, json_extract(parameter, '$.nachts') AS nachts FROM ki_auftrag WHERE lauf_id = ?",
                             (l["id"],)).fetchone()
    plaetze = _plaetze(l["schwer"], l["schirm"], l["gpu"], None if ki_auftrag else l["agent"], pid)
    frei = speicher_frei if speicher_frei is not None else speicher_frei_gb()[0]
    gruende = []
    schirm_zu = schirm_mod.sperrgrund(con) if l["schirm"] or any(x["schirm"] for x in w) else None
    if l["schirm"] and schirm_zu:
        gruende.append(schirm_zu)
    if ki_auftrag and ki_auftrag["nachts"]:
        from . import ki
        s = ki.nacht_sperre(con)
        if s:
            gruende.append(s + " – bis dahin überholen ihn alle anderen")
    if kern.halt_gilt(con, pid, l["agent"]):
        gruende.append("HALT gilt")
    b = _besetzt(con, pid, plaetze)[0]
    if b:
        gruende.append(b)
    gesperrt = _gesperrt(con, pid, w, schirm_zu, bis=l["id"], speicher_frei=frei) if platz else {}
    vor = sorted({x["id"]: x for p in plaetze for x in gesperrt.get(p, [])}.values(), key=lambda x: x["id"])
    if vor:
        gruende.append("vor dir: " + ", ".join(_vordermann(con, pid, x, frei) for x in vor))
    g = _speicher_fehlt(con, pid, _bedarf(con, l), frei)
    if not g and _bedarf(con, l):
        halten, h = _halten_fuer(con, [x for x in w if x["id"] != l["id"]], lauf_stufe(con, l), speicher_frei=frei)
        if halten and _speicher_fehlt(con, pid, _bedarf(con, l) + halten, frei):
            gruende.append(f"Platz frei gehalten für L{h['id']} ({h['agent'] if h['projekt_id'] == pid else 'anderes Projekt'}) mit Vorrang: braucht {halten:g} GB")
    if g and speicher_frei is None:                     # echte Messung: sagen, wer den Speicher außerhalb der Warteschlange hält
        from . import belegung
        dauer = belegung.aktuell(con)
        if dauer:
            g += f" – außerhalb der Warteschlange belegt: {belegung.nennen(dauer)} (beenden kann das nur der Mensch)"
    if g and _passt_nie(con, l, frei):
        g += " – passt auch bei leerer Schlange nicht: andere Läufe ziehen vorbei, bis außerhalb der Schlange Speicher frei wird"
    g = g or _mittel_fehlen(con, l)
    if g:
        gruende.append(g)
    kopf = f"Platz {platz} von {len(w)}" if platz else "nicht in der Schlange"
    st = vorrang_stufe(con, pid)
    if platz and st != "normal":
        kopf += f" ({t_vorrang(st)} für {projekt_name(con, pid)})"
    return kopf + (" – " + " · ".join(gruende) if gruende else " – gleich dran (nächste Runde des Dienstes)")


def warteposition(con, pid, l):
    """Wo ein eingereihter Lauf in der Schlange dieses Rechners steht und auf wen er wartet – für die Team-Ansicht.
    {"lauf", "platz", "von", "auf": [{"lauf", "projekt", "agent", "laeuft"}], "grund"}. Über alle Projekte: Namen fremder
    Projekte stehen drin; was davon online gezeigt wird, entscheidet abgleich (dort nur „anderes Projekt“)."""
    w = wartende(con)
    platz = next((i for i, x in enumerate(w, 1) if x["id"] == l["id"]), None)
    l = next((x for x in w if x["id"] == l["id"]), l)      # die Zeile der Schlange (mit dem angemeldeten Bedarf)
    namen = dict(con.execute("SELECT id, name FROM projekt"))
    ki = con.execute("SELECT 1 FROM ki_auftrag WHERE lauf_id = ?", (l["id"],)).fetchone()
    plaetze = _plaetze(l["schwer"], l["schirm"], l["gpu"], None if ki else l["agent"], pid)
    schirm_zu = schirm_mod.sperrgrund(con) if l["schirm"] or any(x["schirm"] for x in w) else None
    vor = sorted({x["id"]: x for p in plaetze for x in (_gesperrt(con, pid, w, schirm_zu, bis=l["id"], speicher_frei=speicher_frei_gb()[0]) if platz else {}).get(p, [])}.values(),
                 key=lambda x: x["id"])
    auf = [{"lauf": x["id"], "projekt": namen.get(x["projekt_id"]), "agent": x["agent"], "laeuft": False} for x in vor]
    if not auf:                                      # niemand davor: wer hält die Spur bzw. den Speicher gerade?
        spur = []
        if plaetze & {"gpu", "schirm"}:
            spur.append("(l.gpu = 1 OR l.schirm = 1)")
        if "cpu" in plaetze:
            spur.append("(l.schwer = 1 AND l.schirm = 0 AND l.gpu = 0)")
        if any(p.startswith("agent:") for p in plaetze):
            spur.append(f"(l.projekt_id = {int(pid)} AND l.agent = ?)")
        bed = " OR ".join(spur) or "l.schwer = 1"
        args = [l["agent"]] if any(p.startswith("agent:") for p in plaetze) else []
        for x in con.execute(f"SELECT l.id, l.projekt_id, l.agent FROM lauf l WHERE l.status = 'laeuft' AND ({bed}) AND " + HIER
                             + " ORDER BY l.id", (*args, rechner())):
            auf.append({"lauf": x["id"], "projekt": namen.get(x["projekt_id"]), "agent": x["agent"], "laeuft": True})
    return {"lauf": l["id"], "platz": platz, "von": len(w), "auf": auf[:3], "grund": wartegrund(con, pid, l) if platz else None}


def lauf_vorziehen(con, pid, von, lid):
    """Vorziehen. Der Mensch stellt einen wartenden Lauf an die Spitze der Warteschlange des Rechners (über alle Projekte);
    ein Lead stellt ihn an die Spitze der Läufe seines eigenen Projekts – an fremden Läufen zieht er damit nicht vorbei."""
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("vorziehen dürfen nur Lead und Entwickler")
    mensch = von == kern.ENTWICKLER
    with db.schreiben(con):
        l = con.execute("SELECT status FROM lauf WHERE id = ? AND projekt_id = ?", (lid, pid)).fetchone()
        if not l or l["status"] != "angemeldet":
            raise kern.AmwFehler(f"L{lid} wartet nicht")
        if mensch:
            hoechster = con.execute("SELECT coalesce(max(rang), 0) FROM lauf WHERE status = 'angemeldet'").fetchone()[0]
            con.execute("UPDATE lauf SET rang = ? WHERE id = ?", (max(hoechster, MENSCH_RANG - 1) + 1, lid))
        else:
            con.execute("UPDATE lauf SET rang = (SELECT coalesce(max(rang), 0) + 1 FROM lauf WHERE projekt_id = ?"
                        " AND status = 'angemeldet' AND rang < ?) WHERE id = ?", (pid, MENSCH_RANG, lid))


def lauf_ende(con, pid, agent, lid, rc, ergebnis=None, abgebrochen=False, speicher_frei=None):
    """Beendet einen Lauf (oder nimmt einen wartenden aus der Schlange) und startet den nächsten wartenden."""
    with db.schreiben(con):
        l = con.execute("SELECT * FROM lauf WHERE id = ? AND projekt_id = ?", (lid, pid)).fetchone()
        if not l:
            raise kern.AmwFehler(f"Lauf L{lid} gibt es nicht")
        if l["agent"] != agent and not kern.ist_lead(con, pid, agent):
            raise kern.AmwFehler(f"L{lid} gehört {l['agent']}")
        if l["status"] not in ("laeuft", "angemeldet"):
            raise kern.AmwFehler(f"L{lid} ist schon {l['status']}")
        con.execute("UPDATE lauf SET status = ?, ende_utc = ?, rc = ?, ergebnis = ? WHERE id = ?",
                    ("abgebrochen" if abgebrochen or l["status"] == "angemeldet" else "fertig", db.jetzt(), rc, ergebnis, lid))
        from . import wartegrund                     # wer auf diesen Lauf gewartet hat, wird geweckt (L2)
        wartegrund.erledige(con, pid, "lauf", f"L{lid}", f"L{lid} zu Ende (rc {rc})" if rc is not None else f"L{lid} zu Ende")
    return warteschlange(con, pid, speicher_frei)


# --- Prüfungen -----------------------------------------------------------------------------------

def pruefbitte(con, pid, bauer, pruefer, zweig, sha, punkte=None, aufgabe_id=None):
    kern.agent_zeile(con, pid, pruefer)
    with db.schreiben(con):
        prid = db.einfuegen(con, "pruefung", projekt_id=pid, aufgabe_id=aufgabe_id, zweig=zweig, sha=sha, bauer=bauer,
                            pruefer=pruefer, punkte=punkte, angefragt_utc=db.jetzt())
        kern._posten(con, pid, bauer, pruefer, "pruefbitte", f"Prüfbitte P{prid}: {zweig}@{sha[:8]}",
                     punkte, aufgabe_id=aufgabe_id)
    return prid


def pruefung_ergebnis(con, pid, pruefer, prid, ergebnis, bemerkung=None):
    if ergebnis not in ("gruen", "rot"):
        raise kern.AmwFehler("Ergebnis ist gruen oder rot")
    if prid is None:                                 # vorher: „Prüfung PNone gibt es nicht“ – sag, welche offen sind
        offen = con.execute("SELECT id, zweig, sha FROM pruefung WHERE projekt_id = ? AND pruefer = ? AND ergebnis = 'offen'"
                            " ORDER BY id", (pid, pruefer)).fetchall()
        liste = ", ".join(f"P{r['id']} ({r['zweig']}@{r['sha'][:8]})" for r in offen) or "keine"
        raise kern.AmwFehler(f"Welche Prüfung? amw pruefung {ergebnis} <Nummer> – offen für {pruefer}: {liste}")
    with db.schreiben(con):
        p = con.execute("SELECT * FROM pruefung WHERE id = ? AND projekt_id = ?", (prid, pid)).fetchone()
        if not p:
            raise kern.AmwFehler(f"Prüfung P{prid} gibt es nicht")
        if p["pruefer"] != pruefer and not kern.ist_lead(con, pid, pruefer):
            raise kern.AmwFehler(f"P{prid} prüft {p['pruefer']}")
        if p["ergebnis"] != "offen":
            raise kern.AmwFehler(f"P{prid} ist schon {p['ergebnis']} – neue Prüfbitte für einen neuen Stand")
        con.execute("UPDATE pruefung SET ergebnis = ?, bemerkung = ?, ergebnis_utc = ? WHERE id = ?",
                    (ergebnis, bemerkung, db.jetzt(), prid))
        an = [p["bauer"]]
        if p["aufgabe_id"]:                          # der Federführende nimmt ab (ohne Federführung: der Lead)
            z = kern.zustaendig(con, pid, p["aufgabe_id"])
            if z and z not in an and z != pruefer:
                an.append(z)
        kern._posten(con, pid, pruefer, ",".join(an), "meldung",
                     f"P{prid} {ergebnis.upper()}: {p['zweig']}@{p['sha'][:8]}", bemerkung, aufgabe_id=p["aufgabe_id"])
        if ergebnis == "gruen" and p["aufgabe_id"] and kette_an(con, pid):
            ok = merge_ok(con, pid, p["aufgabe_id"], p["zweig"])
            if ok:
                return _merge_bitte(con, pid, p, ok)
            lead = kern.lead(con, pid)
            if lead and lead != pruefer:
                kern._posten(con, pid, "AMW", lead, "meldung",
                             f"A{p['aufgabe_id']} GRÜN auf {p['zweig']}@{p['sha'][:8]} (P{prid}) – Merge-OK? amw freigabe merge"
                             f" A{p['aufgabe_id']}", "Abnahme-Kette: Mit deinem OK geht die Merge-Bitte für genau diesen Stand"
                             f" an {merge_dienst(con, pid)}. Neuer Stand = neue Prüfung.", aufgabe_id=p["aufgabe_id"])
    return None


# --- Abnahme-Kette (Projekt-Einstellung abnahme_kette, Vorgabe aus) --------------------------------

def merge_dienst(con, pid):
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    return json.loads(r[0] or "{}").get("merge_dienst") if r else None


def kette_an(con, pid):
    return kern.projekt_wahl(con, pid, "abnahme_kette") == "an" and bool(merge_dienst(con, pid))


def merge_ok(con, pid, aufgabe_id, zweig=None):
    """Gilt das Merge-OK des Leads (bzw. Entwicklers) für diese Aufgabe (und diesen Zweig)? Der jüngste Eintrag zählt."""
    r = con.execute("SELECT * FROM plan_ereignis WHERE projekt_id = ? AND aufgabe_id = ? AND art IN ('merge_ok', 'merge_ok_zurueck')"
                    " ORDER BY id DESC LIMIT 1", (pid, aufgabe_id)).fetchone()
    if not r or r["art"] != "merge_ok" or (r["text"] and zweig and r["text"] != zweig):
        return None
    return r


def _neuere_pruefung(con, pid, p):
    return con.execute("SELECT id, sha, ergebnis FROM pruefung WHERE projekt_id = ? AND aufgabe_id = ? AND zweig = ? AND id > ?"
                       " ORDER BY id DESC LIMIT 1", (pid, p["aufgabe_id"], p["zweig"], p["id"])).fetchone()


def _merge_bitte(con, pid, p, ok):
    """Merge-Bitte an den Merge-Dienst für genau den grünen Stand – höchstens einmal je Prüfung, nie für einen überholten
    Stand. In der Transaktion des Aufrufers. Rückgabe: Text, was geschah."""
    neuer = _neuere_pruefung(con, pid, p)
    if neuer:
        return f"keine Merge-Bitte: P{p['id']} ist überholt (P{neuer['id']} auf {neuer['sha'][:8]}, {neuer['ergebnis']})"
    if con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = 'merge_bitte' AND text = ?",
                   (pid, f"P{p['id']}")).fetchone():
        return f"Merge-Bitte für P{p['id']} ist schon raus"
    dienst = merge_dienst(con, pid)
    a = p["aufgabe_id"]
    kurz = f"Merge-Bitte A{a}: {p['zweig']}@{p['sha'][:8]} (P{p['id']} GRÜN, Merge-OK {ok['von']})"
    kern._posten(con, pid, "AMW", dienst, "auftrag", kurz,
                 f"Zweig {p['zweig']}, genau dieser Stand: {p['sha']}\nPrüfung P{p['id']} von {p['pruefer']}: GRÜN"
                 f"\nMerge-OK: {ok['von']} am {ok['zeit_utc'][:16].replace('T', ' ')} UTC\nGebaut von: {p['bauer']}"
                 "\n\nNur genau diesen SHA mergen (anderer Stand = neue Prüfung). Ergebnis bitte mit"
                 f" `amw posten --an zustaendig --aufgabe {a} --art meldung --kurz …` melden.", aufgabe_id=a)
    kopie = [x for x in dict.fromkeys([p["bauer"], kern.zustaendig(con, pid, a), kern.lead(con, pid)]) if x and x != dienst]
    if kopie:
        kern._posten(con, pid, "AMW", ",".join(kopie), "info", f"Kopie: {kurz} → {dienst}", aufgabe_id=a)
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="merge_bitte", aufgabe_id=a,
                 text=f"P{p['id']}")
    return f"Merge-Bitte an {dienst}: {p['zweig']}@{p['sha'][:8]} (P{p['id']})"


def freigabe_merge(con, pid, von, aufgabe_id, zweig=None, zurueck=False):
    """Merge-OK des Leads/Entwicklers für eine Aufgabe (optional nur einen Zweig) – „bei grüner Prüfung gilt mein OK“.
    Liegt schon ein GRÜN auf dem neuesten Stand vor, geht die Merge-Bitte sofort. zurueck: OK zurücknehmen."""
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Das Merge-OK geben Lead und Entwickler")
    if not con.execute("SELECT 1 FROM aufgabe WHERE id = ? AND projekt_id = ?", (aufgabe_id, pid)).fetchone():
        raise kern.AmwFehler(f"A{aufgabe_id} gibt es nicht")
    zweig = (zweig or "").strip() or None
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von,
                     art="merge_ok_zurueck" if zurueck else "merge_ok", aufgabe_id=aufgabe_id, text=zweig)
        if zurueck:
            return f"Merge-OK für A{aufgabe_id} zurückgenommen"
        status = con.execute("SELECT status FROM aufgabe WHERE id = ?", (aufgabe_id,)).fetchone()[0]
        if status in ("fertig", "verworfen"):            # z. B. schon von Hand gemergt – keine Bitte, kein Weckruf
            return f"Merge-OK für A{aufgabe_id} vermerkt – die Aufgabe ist {status}, keine Merge-Bitte"
        if not kette_an(con, pid):
            return (f"Merge-OK für A{aufgabe_id} vermerkt – die Abnahme-Kette ist aus (amw projekt einstellen abnahme_kette=an"
                    " merge_dienst=<Name>); die Merge-Bitte schickst du wie bisher selbst")
        sql = "SELECT * FROM pruefung WHERE projekt_id = ? AND aufgabe_id = ?" + (" AND zweig = ?" if zweig else "")
        p = con.execute(sql + " ORDER BY id DESC LIMIT 1", (pid, aufgabe_id, *([zweig] if zweig else []))).fetchone()
        if p and p["ergebnis"] == "gruen":
            return f"Merge-OK für A{aufgabe_id}: " + _merge_bitte(con, pid, p, merge_ok(con, pid, aufgabe_id, p["zweig"]))
        return (f"Merge-OK für A{aufgabe_id} vermerkt – die Merge-Bitte geht von selbst an {merge_dienst(con, pid)}, sobald eine"
                " Prüfung dieser Aufgabe GRÜN ist")


def ist_gruen(con, pid, sha):
    """Gibt es für genau diesen Stand eine grüne Prüfung? (Grundlage für „Merge nur auf grün derselben SHA“)."""
    return con.execute("SELECT id FROM pruefung WHERE projekt_id = ? AND ergebnis = 'gruen' AND (sha = ? OR sha LIKE ?)"
                       " ORDER BY id DESC LIMIT 1", (pid, sha, sha + "%")).fetchone()


# --- Hinweis-Sperren -----------------------------------------------------------------------------

def hinweis(con, pid, von, gilt_fuer, text, bis_utc=None):
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Anweisungen setzen nur Entwickler und Lead")
    with db.schreiben(con):
        sid = db.einfuegen(con, "sperre", projekt_id=pid, art="hinweis", gilt_fuer=gilt_fuer, von=von, text=text,
                           seit_utc=db.jetzt(), bis_utc=bis_utc)
        kern._posten(con, pid, von, gilt_fuer, "korrektur", f"Anweisung #{sid}: {text[:120]}", text)
    return sid


def sperre_aufheben(con, pid, von, sid):
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("aufheben dürfen nur Entwickler und Lead")
    with db.schreiben(con):
        return con.execute("UPDATE sperre SET aufgehoben_utc = ? WHERE id = ? AND projekt_id = ? AND aufgehoben_utc IS NULL",
                           (db.jetzt(), sid, pid)).rowcount


# --- Rezepte -------------------------------------------------------------------------------------

def rezept_setzen(con, pid, name, befehl, beschreibung=None, schirm=False, speicher_gb=0.0, schwer=True, gpu=False):
    with db.schreiben(con):
        t = db.jetzt()
        if con.execute("SELECT 1 FROM rezept WHERE projekt_id = ? AND name = ?", (pid, name)).fetchone():
            con.execute("UPDATE rezept SET befehl = ?, beschreibung = coalesce(?, beschreibung), braucht_schirm = ?,"
                        " braucht_speicher_gb = ?, schwer = ?, gpu = ?, stand_utc = ? WHERE projekt_id = ? AND name = ?",
                        (befehl, beschreibung, int(schirm), speicher_gb, int(schwer), int(gpu), t, pid, name))
            return "geändert"
        db.einfuegen(con, "rezept", projekt_id=pid, name=name, befehl=befehl, beschreibung=beschreibung,
                     braucht_schirm=int(schirm), braucht_speicher_gb=speicher_gb, schwer=int(schwer), gpu=int(gpu), stand_utc=t)
        return "angelegt"
