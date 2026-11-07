"""Betrieb: Rechen-Läufe, Prüfungen, Hinweis-Sperren, Lauf-Rezepte (→ doc/architektur.md).

Läufe und Prüfbitten sind Daten, keine Freitext-Nachrichten: das nimmt dem Nachrichtenstrom das Rauschen
(heute 48 % Job-Zeilen) und macht „läuft gerade etwas?“ und „ist SHA x grün?“ abfragbar.
"""
import ctypes
import json

from . import db, kern
from . import schirm as schirm_mod     # „schirm“ ist hier schon der Name der Spalte/des Parameters

SPEICHER_GRENZE_GB = 8.0      # Vorgabe, je Projekt überschreibbar: einstellungen {"speicher_grenze_gb": …}
ANLAUF_S = 180                # so lange zählt ein gerade gestarteter schwerer Lauf seine Grenze als belegt (sein Speicher
                              # ist in der Messung noch nicht zu sehen)


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


def cpu_laeufe():
    """So viele schwere Läufe ohne Fenster und ohne Grafikkarte rechnen zugleich (Einstellung dieses PCs, Vorgabe 2)."""
    from . import einstellungen
    return einstellungen.wert("cpu_laeufe")


def _plaetze(schwer, schirm, gpu=0, agent=None):
    """Zwei Spuren: Grafikkarte und Schirm (PC-weit ein Lauf zur Zeit; ein Fenster rechnet auf der Grafikkarte) und
    „cpu“ für schwere Läufe ohne beides (cpu_laeufe() zugleich). agent: schwere Läufe eines Agenten nie gleichzeitig –
    er rechnet in seinem Klon, zwei Godot-Imports im selben Klon gehen schief. KI-Aufträge rechnet der Dienst (ohne Klon)."""
    p = {"schirm", "gpu"} if schirm else ({"gpu"} if gpu else set())   # ein Fenster belegt auch die Grafikkarte
    if schwer and not p:
        p.add("cpu")
    if schwer and agent:
        p.add("agent:" + agent)
    return p


def _plaetze_von(l):
    return _plaetze(l["schwer"], l["schirm"], l["gpu"], None if l["ki_auftrag"] else l["agent"])


def _besetzt(con, pid, plaetze):
    """(Grund, Platz), wenn ein laufender Lauf einen der Plätze belegt, sonst (None, None)."""
    for p in sorted(x for x in plaetze if x.startswith("agent:")):
        b = con.execute("SELECT l.id, l.beschreibung FROM lauf l LEFT JOIN ki_auftrag k ON k.lauf_id = l.id WHERE l.projekt_id = ?"
                        " AND l.agent = ? AND l.status = 'laeuft' AND l.schwer = 1 AND k.id IS NULL ORDER BY l.id LIMIT 1",
                        (pid, p[6:])).fetchone()
        if b:
            return f"L{b['id']} von {p[6:]} läuft noch (ein Agent rechnet nie zwei schwere Läufe zugleich – sein Klon): {b['beschreibung']}", p
    if plaetze & {"gpu", "schirm"}:
        b = con.execute("SELECT id, agent, beschreibung, gpu FROM lauf WHERE status = 'laeuft' AND (gpu = 1 OR schirm = 1)"
                        " ORDER BY id LIMIT 1").fetchone()
        if b:
            platz = "gpu" if "gpu" in plaetze else "schirm"
            if b["gpu"]:
                return f"GPU-Lauf L{b['id']} von {b['agent']} belegt die Grafikkarte: {b['beschreibung']}", platz
            return f"Schirm-Lauf L{b['id']} von {b['agent']} läuft noch: {b['beschreibung']}", platz
    if "cpu" in plaetze:
        r = con.execute("SELECT id FROM lauf WHERE status = 'laeuft' AND schwer = 1 AND schirm = 0 AND gpu = 0 ORDER BY id").fetchall()
        n = cpu_laeufe()
        if len(r) >= n:
            return f"CPU-Spur voll ({len(r)} von {n} Läufen ohne Fenster: {', '.join('L%d' % x['id'] for x in r)})", "cpu"
    return None, None


def _anlauf_gb(con):
    """Speicher, den gerade gestartete schwere Läufe gleich brauchen (ihre Grenze, ANLAUF_S lang nach dem Start)."""
    r = con.execute("SELECT l.projekt_id, l.schwer, l.start_utc, r.braucht_speicher_gb FROM lauf l LEFT JOIN rezept r ON r.id = l.rezept_id"
                    " WHERE l.status = 'laeuft' AND l.schwer = 1 AND l.start_utc >= strftime('%Y-%m-%dT%H:%M:%SZ', 'now', ?)",
                    (f"-{ANLAUF_S} seconds",)).fetchall()
    return sum(_grenze(con, x["projekt_id"], x["braucht_speicher_gb"], x["schwer"]) for x in r)


def _speicher_fehlt(con, pid, l_grenze, speicher_frei):
    """Grund, wenn für einen Lauf mit dieser Grenze nicht genug frei ist (abzüglich dessen, was gerade Gestartete gleich
    brauchen) – jeder schwere Lauf braucht seine Grenze für sich."""
    if not l_grenze or speicher_frei is None:
        return None
    anlauf = _anlauf_gb(con)
    if speicher_frei - anlauf < l_grenze:
        return f"nur {speicher_frei} GB frei" + (f" ({anlauf:g} GB gleich für gerade gestartete Läufe)" if anlauf else "") \
            + f", Grenze {l_grenze:g} GB"
    return None


def _lebt(con, pid, l):
    """Darf der Lauf jetzt überhaupt starten: KI-Auftrag (rechnet der Dienst) oder Agent mit lebender Sitzung, ohne Halt."""
    if l["nachts"]:                              # KI-Auftrag mit --nachts: außerhalb des KI-Fensters wie nicht da
        from . import ki
        if ki.nacht_sperre(con):
            return False
    lebt = l["ki_auftrag"] or con.execute(
        "SELECT 1 FROM sitzung s JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ?"
        " AND a.kennung = ? AND s.zustand = 'aktiv'", (pid, l["agent"])).fetchone()
    return bool(lebt) and not kern.halt_gilt(con, pid, l["agent"])


def _gesperrt(con, pid, wartend, schirm_zu, bis=None):
    """Plätze, auf die schon jemand in der Schlange wartet – dort überholt niemand. {platz: [Lauf-Zeilen]}.
    Dieselben Regeln wie warteschlange(): wer auf seinen Klon oder den Schirm wartet, sperrt nur diesen Platz (hält die
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
        elif not _lebt(con, pid, w):
            continue
        else:
            _, platz = _besetzt(con, pid, pw)
            hier = {platz} if platz else pw          # zu wenig Speicher oder gleich dran: alle seine Plätze
        for p in hier:
            aus.setdefault(p, []).append(w)
    return aus


def wartende(con, pid):
    """Warteschlange: Rang (vorgezogen) vor Reihenfolge der Anmeldung. ki_auftrag: der Lauf ist ein KI-Auftrag (führt der
    Dienst aus, kein Weckruf an den Agenten); nachts: startet erst im KI-Fenster."""
    return con.execute("SELECT l.*, r.braucht_speicher_gb, k.id AS ki_auftrag, json_extract(k.parameter, '$.nachts') AS nachts FROM lauf l LEFT JOIN rezept r ON r.id = l.rezept_id"
                       " LEFT JOIN ki_auftrag k ON k.lauf_id = l.id"
                       " WHERE l.projekt_id = ? AND l.status = 'angemeldet' ORDER BY l.rang DESC, l.id", (pid,)).fetchall()


def lauf_start(con, pid, agent, beschreibung, rezept=None, schwer=True, schirm=False, aufgabe_id=None,
               speicher_frei=None, warten=False, erwartet_min=None, gpu=False, dazu=None, sperre=None):
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
    grenze = _grenze(con, pid, rez["braucht_speicher_gb"] if rez else None, schwer)
    if speicher_frei is None:
        speicher_frei = speicher_frei_gb()[0]
    plaetze = _plaetze(schwer, schirm, gpu, None if dazu else agent)
    with db.schreiben(con):
        w = wartende(con, pid)
        schirm_zu = schirm_mod.sperrgrund(con) if schirm or any(x["schirm"] for x in w) else None
        grund = sperre or (schirm_zu if schirm else None) or _besetzt(con, pid, plaetze)[0]
        gesperrt = _gesperrt(con, pid, w, schirm_zu) if not sperre else {}
        vor = sorted({x["id"]: x for p in plaetze for x in gesperrt.get(p, [])}.values(), key=lambda x: x["id"])
        if not grund and vor:
            grund = "Warteschlange: " + ", ".join(f"L{x['id']} von {x['agent']}" for x in vor) + " wartet schon"
        if not grund:
            grund = _speicher_fehlt(con, pid, grenze, speicher_frei)
        if grund and not warten:
            raise kern.AmwFehler(grund + " – mit --warten einreihen")
        t = db.jetzt()
        lid = db.einfuegen(con, "lauf", projekt_id=pid, agent=agent, rezept_id=rez["id"] if rez else None,
                           beschreibung=beschreibung, schwer=int(schwer), schirm=int(schirm), gpu=int(bool(gpu)),
                           status="angemeldet" if grund else "laeuft", angemeldet_utc=t, start_utc=None if grund else t,
                           speicher_frei_gb=speicher_frei, aufgabe_id=aufgabe_id, erwartet_min=erwartet_min)
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


def warteschlange(con, pid, speicher_frei=None):
    """Startet wartende Läufe der Reihe nach, sobald ihr Platz frei ist, und weckt den Agenten (Freigabe).
    Wer warten muss, hält alle hinter sich auf, die den Platz brauchen, an dem er hängt – niemand überholt (wer auf
    seinen Klon wartet, hält die CPU-Spur nicht auf; ein Lauf ohne Fenster nicht den Schirm). Agenten ohne
    lebende Sitzung oder im Halt werden übersprungen, bis sie wieder da sind. Schirm-Läufe nur bei freiem Schirm
    und ruhigem PC (schirm.py). Rückgabe: gestartete Lauf-Nummern."""
    if not wartende(con, pid):
        return []
    if speicher_frei is None:
        speicher_frei = speicher_frei_gb()[0]
    gestartet, gesperrt = [], set()
    with db.schreiben(con):
        schirm_zu = any(l["schirm"] for l in wartende(con, pid)) and schirm_mod.sperrgrund(con)
        for l in wartende(con, pid):
            plaetze = _plaetze_von(l)
            if plaetze & gesperrt:
                continue
            if l["schirm"] and schirm_zu:            # hält nur andere Schirm-Läufe auf, nicht die ohne Fenster
                gesperrt.add("schirm")
                continue
            if not _lebt(con, pid, l):               # KI-Auftrag: rechnet der Dienst, der Agent darf schlafen
                continue
            _, platz = _besetzt(con, pid, plaetze)
            if platz:                                # hält nur auf, wer genau diesen Platz braucht
                gesperrt.add(platz)
                continue
            if _speicher_fehlt(con, pid, _grenze(con, pid, l["braucht_speicher_gb"], l["schwer"]), speicher_frei):
                gesperrt |= plaetze
                continue
            con.execute("UPDATE lauf SET status = 'laeuft', start_utc = ?, speicher_frei_gb = ? WHERE id = ?",
                        (db.jetzt(), speicher_frei, l["id"]))
            if l["ki_auftrag"]:                      # der KI-Arbeiter im Dienst holt ihn ab
                gestartet.append(l["id"])
                continue
            kern._posten(con, pid, "AMW", l["agent"], "freigabe", f"L{l['id']} ist dran – jetzt starten: {kurzfassung(l['beschreibung'])}",
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
    plaetze = _plaetze(l["schwer"], l["schirm"], l["gpu"], None if ki_auftrag else l["agent"])
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
    gesperrt = _gesperrt(con, pid, w, schirm_zu, bis=l["id"]) if platz else {}
    vor = sorted({x["id"]: x for p in plaetze for x in gesperrt.get(p, [])}.values(), key=lambda x: x["id"])
    if vor:
        gruende.append("vor dir: " + ", ".join(f"L{x['id']} ({x['agent']})" for x in vor))
    g = _speicher_fehlt(con, pid, _grenze(con, pid, l["braucht_speicher_gb"], l["schwer"]), frei)
    if g:
        gruende.append(g)
    kopf = f"Platz {platz} von {len(w)}" if platz else "nicht in der Schlange"
    return kopf + (" – " + " · ".join(gruende) if gruende else " – gleich dran (nächste Runde des Wächters)")


def lauf_vorziehen(con, pid, von, lid):
    """Lead/Entwickler stellt einen wartenden Lauf an die Spitze der Warteschlange."""
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("vorziehen dürfen nur Lead und Entwickler")
    with db.schreiben(con):
        l = con.execute("SELECT status FROM lauf WHERE id = ? AND projekt_id = ?", (lid, pid)).fetchone()
        if not l or l["status"] != "angemeldet":
            raise kern.AmwFehler(f"L{lid} wartet nicht")
        con.execute("UPDATE lauf SET rang = (SELECT coalesce(max(rang), 0) + 1 FROM lauf WHERE projekt_id = ?"
                    " AND status = 'angemeldet') WHERE id = ?", (pid, lid))


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
        if not kette_an(con, pid):
            return (f"Merge-OK für A{aufgabe_id} vermerkt – die Abnahme-Kette ist aus (amw projekt einstellen abnahme_kette=an"
                    " merge_dienst=<Kennung>); die Merge-Bitte schickst du wie bisher selbst")
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
