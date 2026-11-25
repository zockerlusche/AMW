"""Wochenlimit-Halt (A1888, Marcel 20.11., D1305): Ab einer einstellbaren Schwelle hält die AMW alle Coder des Projekts an.

- Projekt-Einstellung `limit_halt` (Prozent 1–100, Vorgabe 95; 0/leer = aus) – nur Mensch oder Lead (kern.projekt_einstellen).
- Messung wie Startregel 8 (tokenprognose.lage_gemerkt). Ab der Schwelle: je Coder (alle Agenten außer Leads, nicht
  ausgeschaltet/entfernt) ein Halt (Tabelle sperre, art halt, von AMW, Text „Wochenlimit …“) mit STOPP-Nachricht; Meldung an
  Lead und Mensch. Ein Halt beendet nichts hart: laufende Arbeit endet sauber mit Zwischenstand und Übergabe-Notiz.
- Höchstens einmal je Woche (seit dem letzten Reset): heben Lead oder Mensch den Halt auf (amw weiter / Workbench), kommt er
  in derselben Woche nicht wieder.
- Von selbst aufgehoben, wenn der Verbrauch unter der Schwelle liegt (nach dem Wochenwechsel) oder die Einstellung aus ist.
  Ohne Messung bleibt ein gesetzter Halt stehen."""
import json

from . import db, kern

VORGABE = 95
TEXT = "Wochenlimit"                                # Anfang des Halt-Texts – daran erkennt die AMW ihre eigenen Halte


def schwelle(con, pid):
    """Schwelle in Prozent oder None (aus). A1925 (E4, #29883): Das Konto ist eines – es gilt die PC-Einstellung limit_halt
    (Vorgabe 95, 0 = aus) für alle Projekte; ein Wert des Projekts gilt nur, wenn er strenger (kleiner) ist."""
    from . import einstellungen
    pc = einstellungen.wert("limit_halt")
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        e = json.loads((r[0] if r else None) or "{}")
        eigen = int(e.get("limit_halt") or 0)
    except (TypeError, ValueError):
        eigen = 0
    werte = [v for v in (pc, eigen) if 1 <= v <= 100]
    return min(werte) if werte else None


def aktive(con, pid):
    return con.execute("SELECT * FROM sperre WHERE projekt_id = ? AND art = 'halt' AND von = 'AMW' AND text LIKE ?"
                       " AND aufgehoben_utc IS NULL ORDER BY id", (pid, TEXT + "%")).fetchall()


def coder(con, pid):
    """Wen der Halt trifft: alle Agenten des Projekts außer Leads, nicht ausgeschaltet, nicht entfernt."""
    return [r["kennung"] for r in con.execute(
        "SELECT kennung FROM agent WHERE projekt_id = ? AND entfernt_utc IS NULL AND soll != 'aus' ORDER BY kennung", (pid,))
        if not kern.ist_lead(con, pid, r["kennung"])]


def _lage(con):
    from . import tokenprognose
    try:
        return tokenprognose.lage_gemerkt(con) or {}
    except Exception:                                # Messung ist Zusatz – ohne sie entscheidet die AMW nichts
        return {}


def _an_lead_und_mensch(con, pid):
    return ",".join(dict.fromkeys([k for k in (kern.lead(con, pid), kern.ENTWICKLER) if k]))


def runde(con, lage=None):
    """Dienst-Runde über alle Projekte. lage: {"wert", "letzter_reset_utc"} (Tests); sonst gemessen. Rückgabe: Ereignisse."""
    lage = _lage(con) if lage is None else lage
    wert = lage.get("wert")
    periode = str(lage.get("letzter_reset_utc") or "ohne Reset")
    ereignisse = []
    for (pid,) in con.execute("SELECT id FROM projekt").fetchall():
        s = schwelle(con, pid)
        halte = aktive(con, pid)
        if halte and (s is None or (wert is not None and wert < s)):
            grund = "Halt beim Wochenlimit ist aus" if s is None else f"Wochenlimit bei {wert:.0f} % – unter {s} %"
            with db.schreiben(con):
                con.execute(f"UPDATE sperre SET aufgehoben_utc = ? WHERE id IN ({','.join('?' * len(halte))})",
                            (db.jetzt(), *[h["id"] for h in halte]))
                kern._posten(con, pid, "AMW", ",".join(dict.fromkeys(h["gilt_fuer"] for h in halte)), "freigabe",
                             f"WEITER: {grund}", "Der Halt beim Wochenlimit ist aufgehoben – weiter mit deiner Liste.")
                kern._posten(con, pid, "AMW", _an_lead_und_mensch(con, pid), "info", f"Halt beim Wochenlimit aufgehoben: {grund}")
            ereignisse.append(f"P{pid}: Halt aufgehoben ({grund})")
            continue
        if s is None or wert is None or wert < s or halte:
            continue
        if con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = 'limit_halt' AND text = ?",
                       (pid, periode)).fetchone():
            continue                                    # diese Woche schon angehalten – von Hand aufgehoben, gilt
        wen = coder(con, pid)
        if not wen:
            continue
        text = f"{TEXT} bei {wert:.0f} % (Schwelle {s} %)"
        jetzt = db.jetzt()
        with db.schreiben(con):
            for k in wen:
                db.einfuegen(con, "sperre", projekt_id=pid, art="halt", gilt_fuer=k, von="AMW", text=text, seit_utc=jetzt)
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=jetzt, von="AMW", art="limit_halt", text=periode)
            kern._posten(con, pid, "AMW", ",".join(wen), "stopp", f"HALT: {text}",
                         "Laufende Arbeit sauber beenden: Zwischenstand auf deinen Zweig committen, Übergabe-Notiz an die Aufgabe,"
                         " keine neuen Läufe, keine Auslieferung, nichts Neues anfangen – bis „weiter“ kommt (Lead oder Mensch,"
                         " sonst von selbst nach dem Wochenwechsel).")
            for wer in _an_lead_und_mensch(con, pid).split(","):          # A2108: der Mensch soll es nur wissen
                kern._posten(con, pid, "AMW", wer, "info" if wer == kern.ENTWICKLER else "meldung", f"Wochenlimit-Halt: {text}",
                         f"Angehalten: {', '.join(wen)}. Auch du: nichts Neues anfangen, nur noch Weckrufe, bei denen sonst etwas"
                         " kaputtginge. Aufheben: amw weiter (Lead oder Mensch) – dann diese Woche kein neuer Halt;"
                         " sonst hebt die AMW ihn nach dem Wochenwechsel selbst auf. Schwelle: amw projekt einstellen limit_halt=<Prozent>"
                         " (0 = aus).")
        ereignisse.append(f"P{pid}: Halt für {', '.join(wen)} ({text})")
    return ereignisse
