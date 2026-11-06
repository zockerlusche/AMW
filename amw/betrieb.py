"""Betrieb: Rechen-Läufe, Prüfungen, Hinweis-Sperren, Lauf-Rezepte (→ doc/architektur.md).

Läufe und Prüfbitten sind Daten, keine Freitext-Nachrichten: das nimmt dem Nachrichtenstrom das Rauschen
(heute 48 % Job-Zeilen) und macht „läuft gerade etwas?“ und „ist SHA x grün?“ abfragbar.
"""
import ctypes
import json

from . import db, kern
from . import schirm as schirm_mod     # „schirm“ ist hier schon der Name der Spalte/des Parameters

SPEICHER_GRENZE_GB = 8.0      # Vorgabe, je Projekt überschreibbar: einstellungen {"speicher_grenze_gb": …}


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


def _plaetze(schwer, schirm, gpu=0):
    return {p for p, n in (("schwer", schwer), ("schirm", schirm), ("gpu", gpu)) if n}


def _besetzt(con, pid, plaetze):
    """Grund, wenn ein laufender Lauf einen der Plätze belegt (schwer: einer zur Zeit je Projekt, Schirm: einer zur Zeit,
    gpu: einer zur Zeit auf dem ganzen PC). Ein Lauf mit Fenster rechnet auch auf der Grafikkarte: GPU- und Schirm-Läufe
    warten PC-weit aufeinander."""
    for spalte, name in (("schwer", "schwerer Lauf"), ("schirm", "Schirm-Lauf")):
        if spalte in plaetze:                    # Spaltenname kommt nur aus dieser Liste
            b = con.execute(f"SELECT id, agent, beschreibung FROM lauf WHERE projekt_id = ? AND status = 'laeuft'"
                            f" AND {spalte} = 1", (pid,)).fetchone()
            if b:
                return f"{name} L{b['id']} von {b['agent']} läuft noch: {b['beschreibung']}"
    if plaetze & {"gpu", "schirm"}:
        b = con.execute("SELECT id, agent, beschreibung, gpu FROM lauf WHERE status = 'laeuft' AND (gpu = 1 OR (? AND schirm = 1))"
                        " ORDER BY id LIMIT 1", (int("gpu" in plaetze),)).fetchone()
        if b:
            return f"{'GPU' if b['gpu'] else 'Schirm'}-Lauf L{b['id']} von {b['agent']} belegt die Grafikkarte: {b['beschreibung']}"
    return None


def wartende(con, pid):
    """Warteschlange: Rang (vorgezogen) vor Reihenfolge der Anmeldung. ki_auftrag: der Lauf ist ein KI-Auftrag (führt der
    Dienst aus, kein Weckruf an den Agenten)."""
    return con.execute("SELECT l.*, r.braucht_speicher_gb, k.id AS ki_auftrag FROM lauf l LEFT JOIN rezept r ON r.id = l.rezept_id"
                       " LEFT JOIN ki_auftrag k ON k.lauf_id = l.id"
                       " WHERE l.projekt_id = ? AND l.status = 'angemeldet' ORDER BY l.rang DESC, l.id", (pid,)).fetchall()


def lauf_start(con, pid, agent, beschreibung, rezept=None, schwer=True, schirm=False, aufgabe_id=None,
               speicher_frei=None, warten=False, erwartet_min=None, gpu=False, dazu=None):
    """Meldet einen Lauf an und startet ihn, wenn er darf. Regeln: kein Halt; schwere Läufe nur einer zur Zeit;
    Schirm-Läufe nur einer zur Zeit; GPU-Läufe nur einer zur Zeit auf dem PC; freier Speicher ≥ Grenze; niemand überholt
    die Warteschlange. Darf er nicht: ohne warten AmwFehler mit Grund (nichts wird angelegt), mit warten eingereiht (status
    'angemeldet'); warteschlange() startet ihn, sobald er dran ist, und weckt den Agenten mit einer Freigabe.
    dazu(lid): läuft in derselben Transaktion (KI-Auftrag zum Lauf) – nie ein Lauf ohne seinen Auftrag."""
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
    plaetze = _plaetze(schwer, schirm, gpu)
    with db.schreiben(con):
        schirm_zu = schirm_mod.sperrgrund(con) if schirm or any(w["schirm"] for w in wartende(con, pid)) else None
        grund = (schirm_zu if schirm else None) or _besetzt(con, pid, plaetze)
        vor = [w for w in wartende(con, pid) if _plaetze(w["schwer"], w["schirm"], w["gpu"]) & plaetze
               and not (w["schirm"] and schirm_zu and not schirm)]     # wer auf den Schirm wartet, hält Läufe ohne Fenster nicht auf
        if not grund and vor:
            grund = "Warteschlange: " + ", ".join(f"L{w['id']} von {w['agent']}" for w in vor) + " wartet schon"
        if not grund and grenze and speicher_frei is not None and speicher_frei < grenze:
            grund = f"nur {speicher_frei} GB frei, Grenze {grenze:g} GB"
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
    Wer warten muss, hält alle hinter sich auf, die denselben Platz brauchen – niemand überholt. Agenten ohne
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
            plaetze = _plaetze(l["schwer"], l["schirm"], l["gpu"])
            if plaetze & gesperrt:
                continue
            if l["schirm"] and schirm_zu:            # hält nur andere Schirm-Läufe auf, nicht die ohne Fenster
                gesperrt.add("schirm")
                continue
            lebt = l["ki_auftrag"] or con.execute(   # KI-Auftrag: rechnet der Dienst, der Agent darf schlafen
                "SELECT 1 FROM sitzung s JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ?"
                " AND a.kennung = ? AND s.zustand = 'aktiv'", (pid, l["agent"])).fetchone()
            if not lebt or kern.halt_gilt(con, pid, l["agent"]):
                continue
            grenze = _grenze(con, pid, l["braucht_speicher_gb"], l["schwer"])
            if _besetzt(con, pid, plaetze) or (grenze and speicher_frei is not None and speicher_frei < grenze):
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
    plaetze = _plaetze(l["schwer"], l["schirm"], l["gpu"])
    gruende = []
    if l["schirm"]:
        g = schirm_mod.sperrgrund(con)
        if g:
            gruende.append(g)
    if kern.halt_gilt(con, pid, l["agent"]):
        gruende.append("HALT gilt")
    b = _besetzt(con, pid, plaetze)
    if b:
        gruende.append(b)
    vor = [x for x in w[:(platz or 1) - 1] if _plaetze(x["schwer"], x["schirm"], x["gpu"]) & plaetze]
    if vor:
        gruende.append("vor dir: " + ", ".join(f"L{x['id']} ({x['agent']})" for x in vor))
    grenze = _grenze(con, pid, l["braucht_speicher_gb"], l["schwer"])
    frei = speicher_frei if speicher_frei is not None else speicher_frei_gb()[0]
    if grenze and frei is not None and frei < grenze:
        gruende.append(f"nur {frei} GB frei, Grenze {grenze:g} GB")
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
