"""A2042 (D1531 §1/§7, V1): eine Pause für alles – ein Schalter statt dreier Wege.

„Pause an“ (Lead oder Mensch) setzt zugleich:
- einen Halt für alle Agenten des Projekts (stopp-Nachricht: aktuelle Arbeit sauber beenden, nichts Neues anfangen) – er hält auch
  die Lauf-Schlange an, denn ein Halt lässt keinen Lauf starten oder nachrücken (betrieb),
- die Wächter-Pause (keine neuen Headless-Pakete; laufende laufen zu Ende),
- optional ein Ende (bis): danach gilt der Halt nicht mehr (sperre.bis_utc), die Wächter-Pause endet, und die AMW hebt die
  Pause in ihrer nächsten Runde auf und gibt allen „weiter“.
„Pause aus“ hebt alles wieder auf. Was gerade läuft, wird nicht abgebrochen – die Rückmeldung je Agent zeigt, wo jeder steht:
„wird pausiert“ (stopp noch nicht zugestellt), „beendet Schritt“ (arbeitet noch), „pausiert“ (steht oder keine Sitzung); dazu
„läuft zu Ende“ für Headless-Pakete und Läufe, die schon liefen – und für einen Agenten ohne laufenden Schritt, dessen eigener
Lauf oder Headless-Paket noch läuft (A2043).

Ereignisse (plan_ereignis): pause_an {"bis", "grund", "halt", "stopp"} · pause_aus {"durch"}
"""
import datetime
import json

from . import db, kern

AN, AUS = "pause_an", "pause_aus"
ARBEITET_S = 120                                       # wie der Dienst: Lebenszeichen jünger als das = arbeitet gerade


def _jetzt():
    return datetime.datetime.now(datetime.timezone.utc)


def _iso(t):
    return t.strftime("%Y-%m-%dT%H:%M:%SZ")


def _letzte(con, pid):
    """Das jüngste pause_an ohne späteres pause_aus (dict) oder None."""
    r = con.execute("SELECT id, zeit_utc, von, text FROM plan_ereignis WHERE projekt_id = ? AND art IN (?, ?) ORDER BY id DESC LIMIT 1",
                    (pid, AN, AUS)).fetchone()
    if not r or r["text"] is None:
        return None
    d = json.loads(r["text"] or "{}")
    return {**d, "id": r["id"], "seit": r["zeit_utc"], "von": r["von"]} if d.get("art") == AN else None


def bis_aus(text, jetzt=None):
    """„HH:MM“ (heute, sonst morgen) oder „2h“/„90min“ → UTC-ISO; None bei leer."""
    if not text:
        return None
    jetzt = jetzt or _jetzt()
    t = str(text).strip().lower().replace(" ", "")
    try:
        if t.endswith("h"):
            return _iso(jetzt + datetime.timedelta(hours=float(t[:-1].replace(",", "."))))
        if t.endswith("min"):
            return _iso(jetzt + datetime.timedelta(minutes=float(t[:-3])))
        h, m = (int(x) for x in t.split(":"))
        lokal = datetime.datetime.now().astimezone()
        ziel = lokal.replace(hour=h, minute=m, second=0, microsecond=0)
        if ziel <= lokal:
            ziel += datetime.timedelta(days=1)
        return _iso(ziel.astimezone(datetime.timezone.utc))
    except (ValueError, TypeError):
        raise kern.AmwFehler(f"Ende „{text}“: HH:MM, 2h oder 90min") from None


def an(con, pid, von, bis=None, grund=None) -> dict:
    """Pause für alles. bis: UTC-ISO (bis_aus) oder None (bis „Pause aus“). Lead oder Mensch."""
    from . import waechter
    if not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Die Pause schalten der Lead oder der Mensch")
    if _letzte(con, pid):
        raise kern.AmwFehler("Die Pause ist schon an – erst „Pause aus“")
    grund = (grund or "").strip()[:300] or "Pause"
    text = grund + (f" (bis {bis[11:16]} UTC)" if bis else "")
    sid = kern.halt(con, pid, von, "alle", text)
    with db.schreiben(con):
        if bis:
            con.execute("UPDATE sperre SET bis_utc = ? WHERE id = ?", (bis, sid))
        stopp = con.execute("SELECT max(id) FROM nachricht WHERE projekt_id = ? AND art = 'stopp'", (pid,)).fetchone()[0]
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=AN,
                     text=json.dumps({"art": AN, "bis": bis, "grund": grund, "halt": sid, "stopp": stopp}, ensure_ascii=False))
    waechter.pause_an(f"Pause für alles: {grund}", bis=bis)
    return {"an": True, "bis": bis, "halt": sid}


def aus(con, pid, von, durch=None):
    """Pause aufheben: Halt weg (alle bekommen „weiter“), Wächter-Pause weg. Lead oder Mensch; die AMW selbst nach dem Ende."""
    from . import waechter
    p = _letzte(con, pid)
    if not p:
        raise kern.AmwFehler("Die Pause ist nicht an")
    if von != "AMW" and not kern.ist_lead(con, pid, von):
        raise kern.AmwFehler("Die Pause heben der Lead oder der Mensch auf")
    with db.schreiben(con):
        con.execute("UPDATE sperre SET aufgehoben_utc = ? WHERE id = ? AND aufgehoben_utc IS NULL", (db.jetzt(), p.get("halt")))
        kern._posten(con, pid, von, "alle", "freigabe", "WEITER: Pause vorbei", f"Die Pause ist aufgehoben ({durch or von}).")
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=AUS,
                     text=json.dumps({"art": AUS, "durch": durch or von}, ensure_ascii=False))
    waechter.weiter(con, pid, von)
    return {"an": False}


def runde(con):
    """Vom Dienst: Pausen mit abgelaufenem Ende aufheben (alle bekommen „weiter“). Rückgabe [(Projekt, Text)]."""
    aus_ = []
    for (pid,) in con.execute("SELECT id FROM projekt").fetchall():
        p = _letzte(con, pid)
        if p and p.get("bis") and p["bis"] <= db.jetzt():
            aus(con, pid, "AMW", durch=f"Ende {p['bis'][11:16]} UTC erreicht")
            aus_.append((pid, "Pause vorbei"))
    return aus_


def _laeuft_noch(con, pid, kennung):
    """A2043: Hat der Agent einen eigenen laufenden Lauf oder ein laufendes Headless-Paket?"""
    return bool(con.execute("SELECT 1 FROM lauf WHERE projekt_id = ? AND agent = ? AND status = 'laeuft'", (pid, kennung)).fetchone()
                or con.execute("SELECT 1 FROM paket k JOIN aufgabe a ON a.id = k.aufgabe_id WHERE a.projekt_id = ? AND a.agent = ?"
                               " AND k.art = 'p' AND k.zustand = 'laeuft'", (pid, kennung)).fetchone())


def zustand(con, pid) -> dict:
    """Rückmeldung: {"an", "bis", "grund", "seit", "agenten": [{"kennung", "zustand"}], "pakete": [{"aid", "titel", "zustand"}],
    "laeufe": [{"lauf", "beschreibung", "zustand"}]} – für die Workbench (/api/pause) und `amw pause zeige`."""
    p = _letzte(con, pid)
    if not p:
        return {"an": False}
    grenze = _iso(_jetzt() - datetime.timedelta(seconds=ARBEITET_S))
    agenten = []
    for g in con.execute("SELECT id, kennung FROM agent WHERE projekt_id = ? AND entfernt_utc IS NULL ORDER BY kennung", (pid,)).fetchall():
        s = con.execute("SELECT ereignis, letzter_puls_utc FROM sitzung WHERE agent_id = ? AND beendet_utc IS NULL ORDER BY id DESC LIMIT 1",
                        (g["id"],)).fetchone()
        zu = con.execute("SELECT geweckt_utc FROM empfang WHERE nachricht_id = ? AND agent = ?", (p.get("stopp"), g["kennung"])).fetchone()
        if not s:
            z = "pausiert"                               # keine Sitzung: es läuft nichts
        elif zu is not None and not zu["geweckt_utc"]:
            z = "wird pausiert"                          # stopp noch nicht zugestellt
        elif s["ereignis"] == "arbeitet" and (s["letzter_puls_utc"] or "") >= grenze:
            z = "beendet Schritt"
        else:
            z = "pausiert"
        if z == "pausiert" and _laeuft_noch(con, pid, g["kennung"]):
            z = "läuft zu Ende"                          # A2043: sein Lauf oder Headless-Paket läuft noch
        agenten.append({"kennung": g["kennung"], "zustand": z})
    pakete = [{"aid": r["id"], "titel": r["titel"], "zustand": "läuft zu Ende"} for r in con.execute(
        "SELECT a.id, a.titel FROM paket k JOIN aufgabe a ON a.id = k.aufgabe_id WHERE a.projekt_id = ? AND k.art = 'p'"
        " AND k.zustand = 'laeuft' ORDER BY a.id", (pid,))]
    laeufe = [{"lauf": r["id"], "beschreibung": r["beschreibung"], "zustand": "läuft zu Ende" if r["status"] == "laeuft" else "wartet"}
              for r in con.execute("SELECT id, beschreibung, status FROM lauf WHERE projekt_id = ? AND status IN ('laeuft', 'angemeldet')"
                                   " ORDER BY id", (pid,))]
    return {"an": True, "bis": p.get("bis"), "grund": p.get("grund"), "seit": p["seit"], "agenten": agenten, "pakete": pakete,
            "laeufe": laeufe}
