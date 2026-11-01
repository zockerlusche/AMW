"""Betrieb: Rechen-Läufe, Prüfungen, Hinweis-Sperren, Lauf-Rezepte (→ doc/10 §3, doc/04 #10, #17, #20).

Läufe und Prüfbitten sind Daten, keine Freitext-Nachrichten: das nimmt dem Nachrichtenstrom das Rauschen
(heute 48 % Job-Zeilen) und macht „läuft gerade etwas?“ und „ist SHA x grün?“ abfragbar.
"""
import ctypes
import json

from . import db, kern

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

def lauf_start(con, pid, agent, beschreibung, rezept=None, schwer=True, schirm=False, aufgabe_id=None,
               speicher_frei=None):
    """Meldet einen Lauf an und startet ihn, wenn er darf. Sonst AmwFehler mit Grund (nichts wird angelegt).
    Regeln: kein Halt; schwere Läufe nur einer zur Zeit; Schirm-Läufe nur einer zur Zeit; freier Speicher ≥ Grenze."""
    if kern.halt_gilt(con, pid, agent):
        raise kern.AmwFehler("HALT gilt – keine Läufe starten")
    rez = None
    if rezept:
        rez = con.execute("SELECT * FROM rezept WHERE projekt_id = ? AND name = ?", (pid, rezept)).fetchone()
        if not rez:
            raise kern.AmwFehler(f"Rezept „{rezept}“ gibt es nicht")
        schwer, schirm = bool(rez["schwer"]), bool(rez["braucht_schirm"])
    grenze = float(rez["braucht_speicher_gb"]) if rez and rez["braucht_speicher_gb"] else \
        float(_einstellung(con, pid, "speicher_grenze_gb", SPEICHER_GRENZE_GB)) if schwer else 0.0
    if speicher_frei is None:
        speicher_frei = speicher_frei_gb()[0]
    if grenze and speicher_frei is not None and speicher_frei < grenze:
        raise kern.AmwFehler(f"nur {speicher_frei} GB frei, Grenze {grenze:g} GB – später erneut versuchen")
    pruefen = ([("schwer", "schwerer Lauf")] if schwer else []) + ([("schirm", "Schirm-Lauf")] if schirm else [])
    with db.schreiben(con):
        for spalte, name in pruefen:            # Spaltenname kommt nur aus dieser Liste
            besetzt = con.execute(f"SELECT id, agent, beschreibung FROM lauf WHERE projekt_id = ? AND status = 'laeuft'"
                                  f" AND {spalte} = 1", (pid,)).fetchone()
            if besetzt:
                raise kern.AmwFehler(f"{name} L{besetzt['id']} von {besetzt['agent']} läuft noch: {besetzt['beschreibung']}")
        t = db.jetzt()
        return db.einfuegen(con, "lauf", projekt_id=pid, agent=agent, rezept_id=rez["id"] if rez else None,
                            beschreibung=beschreibung, schwer=int(schwer), schirm=int(schirm), status="laeuft",
                            angemeldet_utc=t, start_utc=t, speicher_frei_gb=speicher_frei, aufgabe_id=aufgabe_id)


def lauf_ende(con, pid, agent, lid, rc, ergebnis=None, abgebrochen=False):
    with db.schreiben(con):
        l = con.execute("SELECT * FROM lauf WHERE id = ? AND projekt_id = ?", (lid, pid)).fetchone()
        if not l:
            raise kern.AmwFehler(f"Lauf L{lid} gibt es nicht")
        if l["agent"] != agent and not kern.ist_lead(con, pid, agent):
            raise kern.AmwFehler(f"L{lid} gehört {l['agent']}")
        if l["status"] != "laeuft":
            raise kern.AmwFehler(f"L{lid} ist schon {l['status']}")
        con.execute("UPDATE lauf SET status = ?, ende_utc = ?, rc = ?, ergebnis = ? WHERE id = ?",
                    ("abgebrochen" if abgebrochen else "fertig", db.jetzt(), rc, ergebnis, lid))


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
        kern._posten(con, pid, pruefer, p["bauer"], "meldung",
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

def rezept_setzen(con, pid, name, befehl, beschreibung=None, schirm=False, speicher_gb=0.0, schwer=True):
    with db.schreiben(con):
        t = db.jetzt()
        if con.execute("SELECT 1 FROM rezept WHERE projekt_id = ? AND name = ?", (pid, name)).fetchone():
            con.execute("UPDATE rezept SET befehl = ?, beschreibung = coalesce(?, beschreibung), braucht_schirm = ?,"
                        " braucht_speicher_gb = ?, schwer = ?, stand_utc = ? WHERE projekt_id = ? AND name = ?",
                        (befehl, beschreibung, int(schirm), speicher_gb, int(schwer), t, pid, name))
            return "geändert"
        db.einfuegen(con, "rezept", projekt_id=pid, name=name, befehl=befehl, beschreibung=beschreibung,
                     braucht_schirm=int(schirm), braucht_speicher_gb=speicher_gb, schwer=int(schwer), stand_utc=t)
        return "angelegt"
