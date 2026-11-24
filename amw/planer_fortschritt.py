"""A2025: Fortschrittsdaten für gestartete Planer- und Prüfer-Läufe.

Jeder Lauf meldet, was er gerade bearbeitet („Thema 17 von 50“), welcher Agent mit welchem Modell, die geschätzte Dauer,
die bisherigen Kosten, den Zustand (laeuft, fertig, fehler) und bei Fehler eine klare Meldung. Der Stand liegt in der AMW
(TH164 „Jeder Zustand liegt in der AMW“ – damit auch online über den Abgleich sichtbar), ohne Schemaänderung:

    plan_ereignis art='planer_fortschritt', ein Eintrag je Lauf, text = JSON {"lauf": n, ...}

Der Eintrag wird fortgeschrieben (UPDATE, geaendert_utc neu – der Abgleich sieht die Änderung). Solange der Lauf läuft und
sich der Zustand nicht ändert, höchstens alle TAKT_S Sekunden (schont die Schreibsperre); Ende und Fehler sofort.
Abfrage: stand() je Lauf, laufende() alle laufenden eines Projekts, alle() jeden Lauf, zum_thema() den laufenden eines Themas.
Ohne eigene Angabe schätzt schaetzung() die Dauer aus den letzten fertigen Läufen derselben Art.
"""
import json
import statistics
import time

from . import db

ART = "planer_fortschritt"
ZUSTAENDE = ("laeuft", "fertig", "fehler")
TAKT_S = 5.0                      # höchstens so oft schreibt ein laufender Lauf seinen Stand
SCHAETZ_LAEUFE = 10               # so viele fertige Läufe derselben Art gehen in die Schätzung der Dauer ein
FELDER = ("art", "thema", "agent", "modell", "was", "nr", "gesamt", "dauer_s", "usd", "zustand", "fehler")


def _praefix(lauf):
    return json.dumps({"lauf": int(lauf)})[:-1] + ","          # '{"lauf": 17,' – der Bezug steht immer vorne


def _zeile(con, pid, lauf):
    return con.execute("SELECT id, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND text LIKE ? ORDER BY id DESC LIMIT 1",
                       (pid, ART, _praefix(lauf) + "%")).fetchone()


def _was(daten):
    if daten.get("was_frei"):
        return daten["was_frei"]
    nr, gesamt = daten.get("nr"), daten.get("gesamt")
    if nr is None:
        return None
    einheit = daten.get("einheit") or "Thema"
    return f"{einheit} {nr} von {gesamt}" if gesamt is not None else f"{einheit} {nr}"


def _schaetzen(daten):
    """Geschätzte Gesamtdauer in Sekunden: angegeben – oder aus dem bisherigen Tempo (nr von gesamt in seit_s)."""
    if daten.get("dauer_vorgabe") is not None:
        return daten["dauer_vorgabe"]
    nr, gesamt = daten.get("nr"), daten.get("gesamt")
    seit = daten["stand_s"] - daten["start_s"]
    if nr and gesamt and seit > 0:
        return round(seit / nr * gesamt)
    return None


def melden(con, pid, lauf, *, art=None, thema=None, agent=None, modell=None, was=None, einheit=None, nr=None, gesamt=None,
           dauer_s=None, usd=None, zustand="laeuft", fehler=None, von="AMW", sofort=False, uhr=time.time):
    """Stand eines Laufs festhalten. Nicht angegebene Felder bleiben wie zuletzt gemeldet; usd sind die Kosten bisher
    (kein Zuwachs). Rückgabe: True, wenn geschrieben wurde – False, wenn gedrosselt (läuft noch, Zustand gleich,
    letzter Stand jünger als TAKT_S; dann einfach später wieder melden)."""
    if zustand not in ZUSTAENDE:
        raise ValueError(f"Zustand {zustand!r} gibt es nicht – erlaubt: {', '.join(ZUSTAENDE)}")
    fehler = (fehler or "").strip() or None
    if zustand == "fehler" and not fehler:
        raise ValueError("Zustand fehler braucht eine klare Meldung (fehler=…), was schiefging")
    jetzt = float(uhr())
    alt = _zeile(con, pid, lauf)
    daten = json.loads(alt["text"]) if alt else {"lauf": int(lauf), "start_s": jetzt}
    if alt and not sofort and zustand == daten.get("zustand") == "laeuft" and jetzt - daten.get("stand_s", 0) < TAKT_S:
        return False
    for k, v in (("art", art), ("thema", thema), ("agent", agent), ("modell", modell), ("was_frei", was), ("einheit", einheit), ("nr", nr),
                 ("gesamt", gesamt), ("dauer_vorgabe", dauer_s), ("usd", usd)):
        if v is not None:
            daten[k] = v
    daten["zustand"] = zustand
    daten["fehler"] = fehler if zustand == "fehler" else None
    daten["stand_s"] = jetzt
    text = json.dumps(daten, ensure_ascii=False)
    with db.schreiben(con):
        if alt:
            con.execute("UPDATE plan_ereignis SET text = ?, geaendert_utc = ? WHERE id = ?", (text, db.jetzt(), alt["id"]))
        else:
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ART, text=text)
    return True


def _aufbereiten(text):
    d = json.loads(text)
    return {
        "lauf": d["lauf"], "art": d.get("art"), "thema": d.get("thema"), "agent": d.get("agent"), "modell": d.get("modell"), "was": _was(d),
        "nr": d.get("nr"), "gesamt": d.get("gesamt"), "dauer_s": _schaetzen(d), "usd": d.get("usd"),
        "zustand": d.get("zustand"), "fehler": d.get("fehler"), "seit_s": round(d["stand_s"] - d["start_s"]),
        "stand_s": d["stand_s"],
    }


def stand(con, pid, lauf):
    """Der zuletzt geschriebene Stand eines Laufs (dict) oder None."""
    r = _zeile(con, pid, lauf)
    return _aufbereiten(r["text"]) if r else None


def alle(con, pid):
    """Der Stand jedes Laufs des Projekts, neuester zuerst."""
    aus, gesehen = [], set()
    for r in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id DESC", (pid, ART)):
        s = _aufbereiten(r["text"])
        if s["lauf"] not in gesehen:
            gesehen.add(s["lauf"])
            aus.append(s)
    return aus


def laufende(con, pid):
    """Die Läufe des Projekts, die gerade laufen."""
    return [s for s in alle(con, pid) if s["zustand"] == "laeuft"]


def zum_thema(con, pid, tid, art=None):
    """Der neueste laufende Lauf zu einem Thema (wahlweise nur einer Art) oder None."""
    return next((s for s in laufende(con, pid) if s.get("thema") == tid and (art is None or s.get("art") == art)), None)


def schaetzung(con, pid, art):
    """Geschätzte Dauer in Sekunden aus den letzten fertigen Läufen derselben Art (Median) – None ohne Vorbild."""
    dauern = [s["seit_s"] for s in alle(con, pid) if s.get("art") == art and s["zustand"] == "fertig" and s["seit_s"] > 0]
    return round(statistics.median(dauern[:SCHAETZ_LAEUFE])) if dauern else None


def melden_still(con, pid, lauf, **kw):
    """Wie melden(), aber ein Fehler beim Schreiben (z. B. Sperre) hält den Lauf nicht auf: Der Planer ist wichtiger als
    seine Anzeige. Rückgabe wie melden(), bei einem Fehler False."""
    try:
        return melden(con, pid, lauf, **kw)
    except Exception:                                   # noqa: BLE001 – Anzeige ist Nebensache, der Lauf geht vor
        return False


def zeile(s):
    """Eine Zeile für die Anzeige: „Lauf 17 · Thema 17 von 50 · PL (opus) · ~10 min · 0.42 $ · läuft“."""
    teile = [f"Lauf {s['lauf']}"]
    if s.get("was"):
        teile.append(s["was"])
    if s.get("agent") or s.get("modell"):
        teile.append(" ".join(x for x in (s.get("agent"), f"({s['modell']})" if s.get("modell") else None) if x))
    if s.get("dauer_s"):
        teile.append(f"~{max(1, round(s['dauer_s'] / 60))} min")
    if s.get("usd") is not None:
        teile.append(f"{s['usd']:.2f} $")
    teile.append({"laeuft": "läuft", "fertig": "fertig", "fehler": f"Fehler: {s.get('fehler')}"}.get(s.get("zustand"), "?"))
    return " · ".join(teile)
