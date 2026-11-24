"""Grobplanung aus Themen (K4 / A1940, D1304 v12 §2, Umsetzungsplan #30103): ein frischer claude -p-Planer entwirft zu einem
freigegebenen Thema Meilenstein(e) und Pakete – als DATEN nach festem Schema, nicht als Text. Die AMW prüft den Entwurf, der
Lead sagt Ja oder ändert ihn, erst dann legt die AMW alles an und verknüpft es mit dem Thema (A1915). Kein Anlegen ohne Ja.
Ein Thema, das nichts braucht, bekommt den Vermerk „nichts zu bauen“ mit Grund.

Stand der Vorbereitung (#30112): Schema, Prüfung, Entwurf eintragen, Übernehmen – mit Tests aus festen Planer-Ergebnissen.
Das Anstoßen bei der Freigabe, `amw thema planen` und die Ansicht kommen nach Marcels Ja zur Kleinprobe A1916 (F5366).

Ereignisse (plan_ereignis, ohne Schemaänderung, Text JSON mit "thema" vorn wie alle Themen-Ereignisse):
  thema_planentwurf   {"thema", "fassung", "modell", "usd", "lauf", "entwurf" | "fehler"}   – ein geprüfter Entwurf (oder Fehler)
  thema_plan_ja       {"thema", "entwurf" (Ereignis-Nr.), "angelegt": {Schlüssel: "M12" | "A345"}, "geaendert"}
  thema_nichts_zu_bauen {"thema", "entwurf", "grund"}

Schema des Planer-Ergebnisses (JSON):
  {"nichts_zu_bauen": false,
   "meilensteine": [{"schluessel": "M1", "titel": "…", "endet_mit": "vorfuehrung|bericht"}  |  {"schluessel": "M1", "bestehend": 52}],
   "pakete": [{"schluessel": "P1", "meilenstein": "M1", "titel": "…", "auftrag": "…", "groesse": "S|M|L|XL",
               "art": "text|mechanisch|fehlersuche|oberflaeche|sicherheit|konzept", "ausfuehrung": "agent|p",
               "modell": "haiku|sonnet|opus", "effort": "low|medium|high", "fertig_quelle": "commit|release|thema|dokument|frist|ja",
               "nach": ["P0", "A1234"], "abnahme_befehl": "python -m unittest tests.test_x" | null,
               "bereiche": "amw/x.py, tests/test_x.py" | null, "pakettyp": "normal|test-schreiben|test-ergaenzen" | null,
               "interaktiv_grund": "…" | null, "lead_liest": true | false}]}
  oder {"nichts_zu_bauen": true, "grund": "…"}

  p ist die Vorgabe (A2004, TH164/TH166): ein Paket der Größe S – oder M bei Art mechanisch –, das keine Oberfläche ist, läuft
  mit "ausfuehrung": "p", mit "abnahme_befehl" (vor dem Bau rot: ein neuer Test im Paket, "pakettyp": "test-schreiben", oder ein
  vorgezogenes Test-Paket als Vorgänger) und engen "bereiche" (Dateien/Ordner, die es ändern darf). "modell"/"effort" weglassen
  heißt: nach der Empfehlung des Projekts. "ausfuehrung": "agent" für so ein Paket nur mit "interaktiv_grund" (Optik, Erkundung,
  gesperrter Bereich, Marcels Auge) – sonst meldet die AMW beim Ja „Achtung“. "lead_liest": true bei Urteils-Arbeit (Konzepttexte,
  Architektur): dieses Paket nimmt die AMW nie selbst ab, der Lead liest es (A2054, TH167 F4).
"""
import difflib
import functools
import json
import os
import re
import subprocess
import sys
import tempfile
import time

from . import db, kern, planer_fortschritt

ENTWURF, JA, NICHTS = "thema_planentwurf", "thema_plan_ja", "thema_nichts_zu_bauen"
FERTIG_QUELLEN = ("commit", "release", "thema", "dokument", "frist", "ja")     # K2 (TH155 2/3/6)
AUSFUEHRUNG = ("agent", "p")
MODELLE = ("haiku", "sonnet", "opus")
EFFORTS = ("low", "medium", "high")
MAX_PAKETE, MAX_MEILENSTEINE = 30, 5
LAENGE = {"titel": 120, "auftrag": 4000, "grund": 1000, "abnahme_befehl": 300, "bereiche": 400, "interaktiv_grund": 300}
PAKETTYPEN = ("normal", "test-schreiben", "test-ergaenzen")


def p_vorgabe(p):
    """A2004 (TH164/TH166, TL #31229): soll dieses Paket als p laufen? S – oder M bei Art mechanisch –, keine Oberfläche."""
    return p.get("art") != "oberflaeche" and (p.get("groesse") == "S" or (p.get("groesse") == "M" and p.get("art") == "mechanisch"))


def achtung(entwurf):
    """A2004: Pakete, die nach der Vorgabe p wären, aber interaktiv ohne Grund geplant sind – Texte für „Achtung“ beim Ja."""
    if not entwurf or entwurf.get("nichts_zu_bauen"):
        return []
    return [f"{p['schluessel']} „{p['titel']}“ ({p['groesse']} · {p['art']}) läuft interaktiv ohne Grund – p wäre die Vorgabe"
            for p in entwurf.get("pakete") or [] if p_vorgabe(p) and p.get("ausfuehrung") != "p" and not p.get("interaktiv_grund")]


def p_modell(con, pid, p):
    """A2004: Modell/Effort eines p-Pakets – aus dem Plan, sonst nach der Empfehlung des Projekts (Gruppe × Größe)."""
    from . import empfehlung
    modell, effort = p.get("modell"), p.get("effort")
    if (modell and effort) or not p.get("art") or not p.get("groesse"):
        return modell, effort
    try:
        m, _, s = empfehlung.tabelle(con, pid)[empfehlung.GRUPPE[p["art"]]][p["groesse"]].partition("/")
    except (KeyError, ValueError):
        return modell, effort
    return modell or m, effort or ({"xhigh": "high", "max": "high"}.get(s, s) if s in EFFORTS + ("xhigh", "max") else None)
ENDET_MIT = {"vorfuehrung": "Vorführung", "bericht": "Bericht"}   # TH164: ein Meilenstein endet mit Vorführung oder Bericht
AEHNLICH = 0.85                                                     # A1976: Titel-Ähnlichkeit, ab der ein Paket „schon gebaut“ ist


class PlanFehler(kern.AmwFehler):
    """Der Entwurf passt nicht zum Schema – .fehler ist die Liste der Funde (alle auf einmal, nicht nur der erste)."""
    def __init__(self, fehler):
        self.fehler = list(fehler)
        super().__init__("Entwurf passt nicht zum Schema: " + "; ".join(self.fehler[:8]) + (" …" if len(self.fehler) > 8 else ""))


def _text(x, feld, wo, f, pflicht=True):
    v = " ".join(str(x).split()) if feld in ("titel",) and isinstance(x, str) else (x.strip() if isinstance(x, str) else x)
    if v is None or v == "":
        if pflicht:
            f.append(f"{wo}: {feld} fehlt")
        return None
    if not isinstance(v, str):
        f.append(f"{wo}: {feld} ist kein Text")
        return None
    if len(v) > LAENGE[feld]:
        f.append(f"{wo}: {feld} länger als {LAENGE[feld]} Zeichen")
    return v


def _wahl(x, erlaubt, feld, wo, f, klein=True):
    v = str(x).strip() if x is not None else ""
    v = v.lower() if klein else v.upper()
    if v not in erlaubt:
        f.append(f"{wo}: {feld} „{x}“ – erlaubt: {' | '.join(erlaubt)}")
        return None
    return v


def _woerter(text):
    """Bedeutungstragende Wörter eines Titels (klein, ohne Satzzeichen, ab 4 Zeichen) – für den Vergleich mit dem Bestand."""
    return {w for w in re.findall(r"\w+", (text or "").lower()) if len(w) >= 4}


def aehnlich(a, b):
    """A1976: Sind zwei Paket-Titel so ähnlich, dass es dasselbe Paket ist? Fast gleiche Zeichenfolge, oder (ab zwei Wörtern)
    drei Viertel der Wörter des kürzeren Titels stecken im längeren."""
    x, y = " ".join((a or "").lower().split()), " ".join((b or "").lower().split())
    if not x or not y:
        return False
    if difflib.SequenceMatcher(None, x, y).ratio() >= AEHNLICH:
        return True
    wa, wb = _woerter(x), _woerter(y)
    kurz = min(len(wa), len(wb))
    return kurz >= 2 and len(wa & wb) / kurz >= 0.75


def gebaut_zum_thema(con, pid, tid):
    """Fertige Pakete, die auf das Thema verweisen: [(id, titel)]."""
    from . import themen
    return [(a["id"], a["titel"]) for a in themen.aufgaben_zu(con, pid, tid, alle=True) if a["status"] == "fertig"]


def pruefen(daten, con=None, pid=None, tid=None, delta=None):
    """Prüft ein Planer-Ergebnis (dict oder JSON-Text) gegen das Schema und gibt es vereinheitlicht zurück. Mit con/pid auch:
    „bestehend“ ist ein OFFENER Meilenstein des Projekts, Aufgaben (Verweise „A1234“) gibt es im Projekt; mit tid (A1976) auch:
    kein Paket wiederholt ein fertiges Paket desselben Themas („schon gebaut: A…“). Mit delta (A2027, planer_delta.kontext) auch
    "aendern"/"verwerfen" für nicht begonnene betroffene Pakete; dann dürfen neue Pakete fehlen. Fehler: PlanFehler mit allen Funden."""
    from . import empfehlung
    if isinstance(daten, str):
        try:
            daten = json.loads(daten)
        except ValueError as e:
            raise PlanFehler([f"kein JSON: {e}"]) from None
    if not isinstance(daten, dict):
        raise PlanFehler(["oben muss ein Objekt stehen"])
    f = []
    unbekannt = set(daten) - {"nichts_zu_bauen", "grund", "meilensteine", "pakete"} - ({"aendern", "verwerfen", "nacharbeit"} if delta else set())
    if unbekannt:
        f.append("unbekannte Felder: " + ", ".join(sorted(unbekannt)))
    aendern, verwerfen, nacharbeit = [], [], []
    if delta:                                            # A2027: Delta-Modus – nur die Änderung; A2059: Nacharbeit nur ausdrücklich
        from . import planer_delta
        aendern, verwerfen, nacharbeit = planer_delta.pruefen_teil(daten, delta, f)
    if daten.get("nichts_zu_bauen") is True:
        grund = _text(daten.get("grund"), "grund", "nichts zu bauen", f)
        if daten.get("meilensteine") or daten.get("pakete") or aendern or verwerfen or nacharbeit:
            f.append("nichts zu bauen, aber Meilensteine oder Pakete angegeben" + (" (oder Änderungen)" if aendern or verwerfen else ""))
        if f:
            raise PlanFehler(f)
        return {"nichts_zu_bauen": True, "grund": grund}
    ms, ps = daten.get("meilensteine"), daten.get("pakete")
    nur_aenderung = bool(delta) and bool(aendern or verwerfen) and not ms and not ps    # A2027: ein Delta ohne neue Pakete
    if not nur_aenderung and (not isinstance(ms, list) or not ms):
        f.append("meilensteine: mindestens einer")
    if not nur_aenderung and (not isinstance(ps, list) or not ps):
        f.append("pakete: mindestens eins")
    ms = ms if isinstance(ms, list) else []
    ps = ps if isinstance(ps, list) else []
    if len(ms) > MAX_MEILENSTEINE:
        f.append(f"höchstens {MAX_MEILENSTEINE} Meilensteine je Thema")
    if len(ps) > MAX_PAKETE:
        f.append(f"höchstens {MAX_PAKETE} Pakete je Thema")
    aus_m, aus_p, schluessel = [], [], set()
    for i, m in enumerate(ms, 1):
        wo = f"Meilenstein {i}"
        if not isinstance(m, dict):
            f.append(f"{wo}: kein Objekt")
            continue
        s = str(m.get("schluessel") or "").strip()
        if not s:
            f.append(f"{wo}: schluessel fehlt")
        elif s in schluessel:
            f.append(f"{wo}: Schlüssel {s} doppelt")
        schluessel.add(s)
        wo = f"Meilenstein {s or i}"
        if m.get("bestehend") is not None:
            try:
                nr = int(str(m["bestehend"]).lstrip("Mm"))
            except ValueError:
                f.append(f"{wo}: bestehend ist keine Meilenstein-Nummer")
                continue
            b = con.execute("SELECT status FROM bogen WHERE projekt_id = ? AND nr = ?", (pid, nr)).fetchone() if con is not None else None
            if con is not None and not b:
                f.append(f"{wo}: Meilenstein {nr} gibt es im Projekt nicht")
            elif b and b["status"] not in ("geplant", "aktiv"):     # A1976: nur offene Meilensteine dieses Projekts
                f.append(f"{wo}: Meilenstein {nr} ist {b['status']} – „bestehend“ nur ein offener Meilenstein (geplant oder aktiv)")
            aus_m.append({"schluessel": s, "bestehend": nr})
            continue
        if m.get("ziel") or m.get("abnahme"):           # TH164: Ziel und Abnahme als Verweis (aufs Thema), nicht als Freitext
            f.append(f"{wo}: ziel/abnahme nicht als Text – ein Meilenstein verweist auf seine Themen und endet_mit")
        aus_m.append({"schluessel": s, "titel": _text(m.get("titel"), "titel", wo, f),
                      "endet_mit": _wahl(m.get("endet_mit"), tuple(ENDET_MIT), "endet_mit", wo, f)})
    m_namen = {m["schluessel"] for m in aus_m}
    p_namen = [str(p.get("schluessel") or "").strip() for p in ps if isinstance(p, dict)]
    for i, p in enumerate(ps, 1):
        wo = f"Paket {i}"
        if not isinstance(p, dict):
            f.append(f"{wo}: kein Objekt")
            continue
        s = str(p.get("schluessel") or "").strip()
        if not s:
            f.append(f"{wo}: schluessel fehlt")
        elif s in schluessel:
            f.append(f"{wo}: Schlüssel {s} doppelt")
        schluessel.add(s)
        wo = f"Paket {s or i}"
        m = str(p.get("meilenstein") or "").strip()
        if m not in m_namen:
            f.append(f"{wo}: Meilenstein „{m}“ steht nicht in meilensteine")
        nach = []
        for v in p.get("nach") or []:
            v = str(v).strip()
            if v in p_namen:
                nach.append(v)
            elif v[:1] in "Aa" and v[1:].isdigit():
                if con is not None and not con.execute("SELECT 1 FROM aufgabe WHERE projekt_id = ? AND id = ?", (pid, int(v[1:]))).fetchone():
                    f.append(f"{wo}: nach {v} – die Aufgabe gibt es im Projekt nicht")
                nach.append("A" + v[1:])
            else:
                f.append(f"{wo}: nach „{v}“ ist weder ein Paket dieses Entwurfs noch eine Aufgabe (A1234)")
        if s and s in nach:
            f.append(f"{wo}: hängt von sich selbst ab")
        groesse = _wahl(p.get("groesse"), empfehlung.GROESSEN, "groesse", wo, f, klein=False)
        aus_p.append({"schluessel": s, "meilenstein": m, "titel": _text(p.get("titel"), "titel", wo, f),
                      "auftrag": _text(p.get("auftrag"), "auftrag", wo, f), "groesse": groesse,
                      "art": _wahl(p.get("art"), empfehlung.ARTEN, "art", wo, f),
                      "ausfuehrung": _wahl(p.get("ausfuehrung") or "agent", AUSFUEHRUNG, "ausfuehrung", wo, f),
                      "modell": _wahl(p.get("modell"), MODELLE, "modell", wo, f) if p.get("modell") else None,
                      "effort": _wahl(p.get("effort"), EFFORTS, "effort", wo, f) if p.get("effort") else None,
                      "fertig_quelle": _wahl(p.get("fertig_quelle"), FERTIG_QUELLEN, "fertig_quelle", wo, f),
                      "nach": nach, "abnahme_befehl": _text(p.get("abnahme_befehl"), "abnahme_befehl", wo, f, pflicht=False),
                      "bereiche": _text(p.get("bereiche"), "bereiche", wo, f, pflicht=False),          # A2004
                      "pakettyp": _wahl(p.get("pakettyp"), PAKETTYPEN, "pakettyp", wo, f) if p.get("pakettyp") else None,
                      "interaktiv_grund": _text(p.get("interaktiv_grund"), "interaktiv_grund", wo, f, pflicht=False),
                      "lead_liest": p.get("lead_liest") is True})                                     # A2054
        if aus_p[-1]["ausfuehrung"] == "p" and aus_p[-1]["art"] == "oberflaeche":   # A1976 (TH156): zuerst eine Kleinprobe
            f.append(f"{wo}: ein Oberflächen-Paket nie als p – ausfuehrung agent, mit Kleinprobe zuerst (TH156)")
        if aus_p[-1]["ausfuehrung"] == "p" and not aus_p[-1]["abnahme_befehl"]:
            f.append(f"{wo}: ein p-Paket braucht einen Abnahme-Befehl (die AMW nimmt es selbst ab)")
        if aus_p[-1]["ausfuehrung"] == "p" and not aus_p[-1]["bereiche"]:          # A2004: sonst startet der Wächter es nie
            f.append(f"{wo}: ein p-Paket braucht enge Bereiche (bereiche: Dateien/Ordner, die es ändern darf)")
        if aus_p[-1]["ausfuehrung"] == "p" and aus_p[-1]["bereiche"]:
            from . import abnahme
            gesperrt = abnahme.startregel([x.strip() for x in aus_p[-1]["bereiche"].replace(";", ",").split(",") if x.strip()],
                                          aus_p[-1]["pakettyp"])
            if gesperrt:
                f.append(f"{wo}: Bereiche enthalten gesperrte Pfade ({', '.join(b for b, _ in gesperrt[:3])}) – dann ausfuehrung agent mit"
                         " interaktiv_grund „gesperrter Bereich“")
        if aus_p[-1]["abnahme_befehl"]:                  # P462 (2): wie beim Start des Arbeiters – ein Befehl, keine Verkettung
            from . import arbeiter
            try:
                arbeiter.freigabe(aus_p[-1]["abnahme_befehl"])
            except arbeiter.ArbeiterFehler as x:
                f.append(f"{wo}: {x}")
    if con is not None and tid is not None:              # A1976: Fertiges nie neu vorschlagen
        gebaut = gebaut_zum_thema(con, pid, tid)
        for p in aus_p:
            treffer = [f"A{i} „{t}“" for i, t in gebaut if aehnlich(p["titel"], t)]
            if treffer:
                f.append(f"Paket {p['schluessel']}: schon gebaut: " + ", ".join(treffer[:3]))
    kreis = _kreis({p["schluessel"]: [v for v in p["nach"] if v in p_namen] for p in aus_p})
    if kreis:
        f.append("Abhängigkeiten im Kreis: " + " → ".join(kreis))
    leer = sorted(m_namen - {p["meilenstein"] for p in aus_p} - {m["schluessel"] for m in aus_m if m.get("bestehend")})
    if leer:
        f.append("neue Meilensteine ohne Pakete: " + ", ".join(leer))
    if f:
        raise PlanFehler(f)
    aus = {"nichts_zu_bauen": False, "meilensteine": aus_m, "pakete": aus_p}
    if delta:
        from . import planer_delta
        aus.update(aendern=aendern, verwerfen=verwerfen, nacharbeit=nacharbeit, delta=planer_delta.kurz(delta))
    return aus


def _kreis(nach):
    """Ein Kreis in den Abhängigkeiten als Liste von Schlüsseln (erster = letzter) – oder None."""
    farbe = {}

    def tief(k, weg):
        farbe[k] = 1
        for v in nach.get(k, []):
            if farbe.get(v) == 1:
                return weg[weg.index(v):] + [v]
            if not farbe.get(v):
                r = tief(v, weg + [v])
                if r:
                    return r
        farbe[k] = 2
        return None

    for k in nach:
        if not farbe.get(k):
            r = tief(k, [k])
            if r:
                return r
    return None


def reihenfolge(entwurf):
    """Pakete so sortiert, dass jedes nach seinen Vorgängern im Entwurf kommt (stabil: sonst wie geliefert)."""
    rest, fertig, aus = list(entwurf["pakete"]), set(), []
    while rest:
        for p in rest:
            if all(v in fertig or v.startswith("A") for v in p["nach"]):
                aus.append(p)
                fertig.add(p["schluessel"])
                rest.remove(p)
                break
        else:                                            # kann nach pruefen() nicht vorkommen (kein Kreis)
            raise PlanFehler(["Abhängigkeiten im Kreis"])
    return aus


# --- Ereignisse -----------------------------------------------------------------------------------------------------------

def _ereignisse(con, pid, tid, art):
    aus = []
    for r in con.execute("SELECT id, von, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND text LIKE ? ORDER BY id",
                         (pid, art, f'{{"thema": {int(tid)},%')):
        try:
            aus.append({"id": r["id"], "von": r["von"], "zeit_utc": r["zeit_utc"], **json.loads(r["text"])})
        except ValueError:
            continue
    return aus


def _ereignis(con, pid, von, art, tid, **werte):
    return db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=art,
                        text=json.dumps({"thema": int(tid), **werte}, ensure_ascii=False))


def entwurf_eintragen(con, pid, tid, fassung, ergebnis, modell=None, usd=None, lauf=None, fehler=None, delta=None, vorher=None,
                      nachgebessert=None):
    """Das Ergebnis des Planers eintragen: geprüft als Entwurf – oder mit den Funden als Fehler (fehler: der Lauf selbst ging
    nicht; vorher: die Funde der ersten Antwort, wenn die Nachbesserung selbst nicht ging). nachgebessert (A2076): Text dazu für
    den Lead. Der Lead bekommt einen Auftrag (Ja oder ändern) bzw. eine Meldung. Rückgabe: Nummer des Ereignisses."""
    t = con.execute("SELECT * FROM thema WHERE id = ? AND projekt_id = ?", (tid, pid)).fetchone()
    if not t:
        raise kern.AmwFehler(f"TH{tid} gibt es nicht")
    if fehler:
        entwurf, fehler = None, [f"Planer-Lauf: {fehler}", *(vorher or [])]
    else:
        try:
            entwurf, fehler = pruefen(ergebnis, con, pid, tid, delta=delta), None
        except PlanFehler as e:
            entwurf, fehler = None, e.fehler
    lead = kern.lead(con, pid)
    kosten = f"{usd:.2f} $" if isinstance(usd, (int, float)) else "Kosten unbekannt"
    with db.schreiben(con):
        eid = _ereignis(con, pid, "AMW", ENTWURF, tid, fassung=fassung, modell=modell, usd=usd, lauf=lauf,
                        **({"entwurf": entwurf} if entwurf else {"fehler": fehler, **_delta_kurz(delta)}))
        if lead and lead != kern.ENTWICKLER:
            if fehler:
                kern._posten(con, pid, "AMW", lead, "meldung", f"Planentwurf TH{tid} „{t['name'][:50]}“ "
                             + ("ging nicht" if fehler[0].startswith("Planer-Lauf:") else "passt nicht zum Schema"),
                             "Funde:\n" + "\n".join(f"- {x}" for x in fehler[:20]) + (f"\n\n{nachgebessert}" if nachgebessert else "")
                             + f"\n\n({modell or '–'}, {kosten})")
            elif entwurf["nichts_zu_bauen"]:
                kern._posten(con, pid, "AMW", lead, "auftrag", f"Planentwurf TH{tid} „{t['name'][:50]}“: nichts zu bauen – stimmt das?",
                             f"Grund des Planers: {entwurf['grund']}\n\nJa oder neu planen lassen. ({kosten})")
            elif _delta_melden(con, pid, lead, t, tid, entwurf, modell, kosten):   # A2027: Freigabe als Block
                pass
            else:
                kern._posten(con, pid, "AMW", lead, "auftrag",
                             f"Planentwurf TH{tid} „{t['name'][:50]}“: {len(entwurf['meilensteine'])} Meilenstein(e), "
                             f"{len(entwurf['pakete'])} Pakete – Ja oder ändern", zusammenfassung(entwurf) + f"\n\n({modell or '–'}, {kosten})")
    return eid


def _delta_kurz(delta):
    """A2076: auch ein abgelehnter Entwurf merkt sich, dass er eine Konzeptänderung war (für die Seite)."""
    from . import planer_delta
    return {"delta": planer_delta.kurz(delta)} if delta else {}


def _delta_melden(con, pid, lead, t, tid, entwurf, modell, kosten):
    """A2027: Ist der Entwurf ein Delta, sagt die AMW dem Lead, dass der Mensch (bzw. Co + Lead nach feinplan_freigabe) es als
    einen Block freigibt. Rückgabe: True, wenn gemeldet. In der Transaktion des Aufrufers."""
    e = entwurf or {}
    if not e.get("delta"):
        return False
    kern._posten(con, pid, "AMW", lead, "meldung",
                 (f"Delta TH{tid} „{t['name'][:40]}“: {len(e['pakete'])} neu, {len(e['aendern'])} ändern,"
                  f" {len(e['verwerfen'])} verwerfen" + (f", {len(e.get('nacharbeit') or [])} Nacharbeit" if e.get("nacharbeit") else "")
                  + " – Freigabe als Block")[:140],
                 zusammenfassung(e) + f"\n\n({modell or '–'}, {kosten})\nFreigeben: amw thema plan-ja TH{tid}"
                 " (der Mensch; bei feinplan_freigabe = co+lead Co und Lead je ein Ja)")
    return True


def zusammenfassung(entwurf):
    if entwurf["nichts_zu_bauen"]:
        return f"Nichts zu bauen: {entwurf['grund']}"
    zeilen = []
    for m in entwurf["meilensteine"]:
        zeilen.append(f"{m['schluessel']} " + (f"(bestehender Meilenstein {m['bestehend']})" if m.get("bestehend")
                                                else f"{m['titel']} · endet mit {ENDET_MIT[m['endet_mit']]}"))
        for p in reihenfolge(entwurf):
            if p["meilenstein"] == m["schluessel"]:
                zeilen.append(f"  {p['schluessel']} {p['titel']} · {p['groesse']} · {p['art']} · {p['ausfuehrung']}"
                              + (f" {p['modell']}" if p["modell"] else "") + f" · fertig: {p['fertig_quelle']}"
                              + (f" · nach {', '.join(p['nach'])}" if p["nach"] else ""))
                zeilen.append(f"    Auftrag: {' '.join((p['auftrag'] or '').split())[:600]}")   # P462 (2): was angelegt wird
                if p["abnahme_befehl"]:
                    zeilen.append(f"    Abnahme-Befehl: {p['abnahme_befehl']}")
                if p.get("bereiche"):
                    zeilen.append(f"    Bereiche: {p['bereiche']}" + (f" · {p['pakettyp']}" if p.get("pakettyp") else ""))
                if p.get("interaktiv_grund"):                                                       # A2004
                    zeilen.append(f"    Interaktiv, Grund: {p['interaktiv_grund']}")
    if entwurf.get("delta"):                            # A2027
        from . import planer_delta
        zeilen = planer_delta.zeilen(entwurf) + zeilen
    hinweise = achtung(entwurf)
    if hinweise:
        zeilen += ["", "Achtung (p ist die Vorgabe):"] + [f"  {h}" for h in hinweise]
    return "\n".join(zeilen)


def letzter_entwurf(con, pid, tid):
    ev = _ereignisse(con, pid, tid, ENTWURF)
    return ev[-1] if ev else None


def erledigt(con, pid, eid):
    """Ist dieser Entwurf schon übernommen (Ja oder „nichts zu bauen“)?"""
    return any(e.get("entwurf") == eid for art in (JA, NICHTS)
               for e in [json.loads(r[0]) for r in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ?",
                                                               (pid, art))])


# --- Ja des Leads: anlegen -----------------------------------------------------------------------------------------------

def uebernehmen(con, pid, von, tid, eid=None, geaendert=None):
    """Ja des Leads (oder des Menschen): den jüngsten (oder genannten) Entwurf anlegen – neue Meilensteine, Pakete mit Größe,
    Art, Ausführung, Modell/Effort, Abnahme-Befehl und Abhängigkeiten, je Paket der Verweis aufs Thema (A1915). geaendert:
    ein vom Lead geänderter Entwurf (gleiches Schema, wird neu geprüft). Rückgabe: {Schlüssel: "M<nr>" | "A<id>"}."""
    from . import delta_start, planer_delta, themen
    e = next((x for x in _ereignisse(con, pid, tid, ENTWURF) if x["id"] == eid), None) if eid else letzter_entwurf(con, pid, tid)
    ist_delta = bool(((e or {}).get("entwurf") or {}).get("delta"))   # A2027: ein Delta gibt der Mensch frei (feinplan_freigabe)
    if not ist_delta and not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler("Den Planentwurf nimmt der Lead an (oder der Mensch)")
    if not e:
        raise kern.AmwFehler(f"TH{tid} hat keinen Planentwurf" + (f" Nr. {eid}" if eid else ""))
    if ist_delta and geaendert is not None:
        raise kern.AmwFehler(f"Das Delta zu TH{tid} wird als ein Block freigegeben, nicht geändert – sonst neu planen lassen")
    if erledigt(con, pid, e["id"]):
        raise kern.AmwFehler(f"Der Planentwurf zu TH{tid} ist schon angenommen")
    entwurf = pruefen(geaendert, con, pid, tid) if geaendert is not None else e.get("entwurf")
    if not entwurf:
        raise kern.AmwFehler(f"Der Planentwurf zu TH{tid} passte nicht zum Schema – neu planen lassen oder geändert übergeben")
    s = themen.status(con, themen.finden(con, pid, tid))     # P462 (4): nur für die freigegebene Fassung, die er gelesen hat
    if s["status"] != "frei":
        raise kern.AmwFehler(f"TH{tid} ist nicht freigegeben ({s['text']}) – erst freigeben, dann planen lassen")
    if e.get("fassung") is not None and s["fassung"] != e.get("fassung"):
        raise kern.AmwFehler(f"Der Entwurf gilt für Fassung {e.get('fassung')}, TH{tid} hat jetzt Fassung {s['fassung']} – neu planen lassen")
    for m in entwurf.get("meilensteine") or []:
        if m.get("bestehend") and not con.execute("SELECT 1 FROM bogen WHERE projekt_id = ? AND nr = ? AND status IN ('geplant', 'aktiv')",
                                                  (pid, m["bestehend"])).fetchone():
            raise kern.AmwFehler(f"Meilenstein {m['bestehend']} aus dem Entwurf gibt es nicht mehr offen – neu planen lassen oder geändert übergeben")
    with db.schreiben(con):                          # P462 (4): angenommen wird einmal – Marke zuerst, in einer Transaktion
        if erledigt(con, pid, e["id"]):
            raise kern.AmwFehler(f"Der Planentwurf zu TH{tid} ist schon angenommen")
        if ist_delta:
            delta_start.recht_pruefen(con, pid, von, entwurf)     # A2080: neuer Meilenstein → wer auch Grobpläne freigibt
            fehlt = planer_delta.stimme(con, pid, von, tid, e["id"])
            if fehlt:
                return {"ja_fehlt": ", ".join(fehlt)}     # gleicher Typ wie {Schlüssel: "A123"} – P593 (Sprachprüfung)
        merke = _ereignis(con, pid, von, JA, tid, entwurf=e["id"], angelegt={}, laeuft=True)
        zuvor = [con.execute(f"SELECT coalesce(max(id), 0) FROM {tab}").fetchone()[0] for tab in ("aufgabe", "bogen")]   # A2085
    schon, stand = {}, {}
    vorher = delta_start.merken(con, pid, entwurf) if ist_delta else {}
    try:
        angelegt = _anlegen(con, pid, von, tid, e, entwurf, geaendert, merke, schon)
        if ist_delta:                                    # A2027: dann ändern und verwerfen, was der Planer vorschlägt
            planer_delta.anwenden(con, pid, von, tid, e["id"], entwurf, stand)
    except Exception as x:
        unfertig = _entstanden(con, pid, entwurf, schon, zuvor)   # halb Angelegtes zählt: sonst legte das nächste Ja es doppelt an
        bestehend = {m["schluessel"] for m in entwurf.get("meilensteine") or [] if m.get("bestehend")}
        getan = any(k not in bestehend for k in schon) or bool(stand.get("geaendert") or stand.get("verworfen"))
        ja = delta_start._letztes_ja(con, pid, e["id"]) or {}     # A2085: _anlegen hat die Marke vielleicht schon durch das Ja ersetzt
        offen = planer_delta.noch_offen(entwurf, stand) if ist_delta else []
        offen_neu = [x["titel"] for x in (entwurf.get("meilensteine") or []) + (entwurf.get("pakete") or [])
                     if x["schluessel"] not in schon and not x.get("bestehend")]
        with db.schreiben(con):
            if not getan:                            # nichts geschehen: das Ja zurücknehmen, ein neues darf es noch einmal versuchen
                con.execute("DELETE FROM plan_ereignis WHERE id IN (?, ?) AND art = ?", (merke, ja.get("id", merke), JA))
            else:                                    # Vorab-Prüfung 1.164.0 (8): teilweise angelegt – die Marke bleibt (kein
                con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?",   # zweites Anlegen), sie nennt, was schon da ist
                            (json.dumps({"thema": tid, "entwurf": e["id"], "angelegt": schon, "abgebrochen": str(x)[:300],
                                         "unfertig": unfertig, "offen_neu": offen_neu,
                                         **({"geaendert": stand.get("geaendert") or [], "verworfen": stand.get("verworfen") or [],
                                             "offen": offen} if ist_delta else {})}, ensure_ascii=False), ja.get("id", merke)))
                kern._posten(con, pid, "AMW", kern.lead(con, pid) or kern.ENTWICKLER, "meldung",
                             f"Planentwurf TH{tid} nur teilweise angelegt"[:140],
                             f"Abbruch beim Anlegen: {str(x)[:300]}\nSchon angelegt: "
                             + (", ".join(f"{k} → {v}" + (" (vielleicht unvollständig)" if k in unfertig else "") for k, v in schon.items()) or "nichts")
                             + "\nNoch nicht angelegt: " + (", ".join(f"„{t}“" for t in offen_neu) or "nichts")
                             + (f"\nSchon geändert: {', '.join(stand.get('geaendert') or []) or 'nichts'} · schon verworfen: "
                                f"{', '.join(stand.get('verworfen') or []) or 'nichts'} · noch offen: {', '.join(offen) or 'nichts'}" if ist_delta else "")
                             + "\nDer Rest fehlt – bitte von Hand ergänzen oder das Angelegte prüfen; ein neues Ja legt nichts doppelt an.")
        raise
    if ist_delta and not entwurf["nichts_zu_bauen"]:     # A2080: das Ja ist auch die Freigabe – und startet
        try:
            delta_start.nach_dem_ja(con, pid, von, tid, e["id"], entwurf, angelegt, vorher)
        except Exception as x:                           # noqa: BLE001 – angelegt ist alles: die Seite zeigt den wartenden Meilenstein
            with db.schreiben(con):
                kern._posten(con, pid, "AMW", kern.lead(con, pid) or kern.ENTWICKLER, "meldung",
                             f"Änderung TH{tid}: angelegt, aber nicht gestartet"[:140], str(x)[:500])
    return angelegt


def _entstanden(con, pid, entwurf, schon, zuvor):
    """A2085: Was ist seit der Marke wirklich entstanden? Meilensteine und Pakete des Entwurfs, die es schon gibt, obwohl _anlegen sie
    nicht mehr eingetragen hat (Abbruch mittendrin) – ergänzt schon. Rückgabe: die Schlüssel, die so gefunden wurden (vielleicht
    unvollständig)."""
    gefunden = []
    for liste, tab, spalte, vor, k0 in ((entwurf.get("meilensteine") or [], "bogen", "nr", "M", zuvor[1]),
                                        (entwurf.get("pakete") or [], "aufgabe", "id", "A", zuvor[0])):
        neu = con.execute(f"SELECT id, titel, {spalte} AS nummer FROM {tab} WHERE projekt_id = ? AND id > ? ORDER BY id", (pid, k0)).fetchall()
        vergeben = set(schon.values())
        for x in liste:
            if x["schluessel"] in schon or x.get("bestehend"):
                continue
            r = next((r for r in neu if r["titel"] == x["titel"] and f"{vor}{r['nummer']}" not in vergeben), None)
            if r:
                schon[x["schluessel"]] = f"{vor}{r['nummer']}"
                vergeben.add(schon[x["schluessel"]])
                gefunden.append(x["schluessel"])
    return gefunden


def _anlegen(con, pid, von, tid, e, entwurf, geaendert, merke, angelegt):
    from . import arbeitspaket, fertigquelle, planung, themen
    if entwurf["nichts_zu_bauen"]:
        with db.schreiben(con):
            con.execute("DELETE FROM plan_ereignis WHERE id = ?", (merke,))
            _ereignis(con, pid, von, NICHTS, tid, entwurf=e["id"], grund=entwurf["grund"])
        return {}
    bogen = {}
    for m in entwurf["meilensteine"]:                    # erst prüfen (pruefen oben), dann anlegen
        if m.get("bestehend"):
            bogen[m["schluessel"]] = con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND nr = ?", (pid, m["bestehend"])).fetchone()[0]
            angelegt[m["schluessel"]] = f"M{m['bestehend']}"
        else:
            t = con.execute("SELECT name FROM thema WHERE id = ?", (tid,)).fetchone()
            bid = planung.bogen_neu(con, pid, von, m["titel"], ziel=f"TH{tid} {t['name'] if t else ''}".strip(),   # Verweis (TH164)
                                    abnahme=ENDET_MIT[m["endet_mit"]])
            bogen[m["schluessel"]] = bid
            angelegt[m["schluessel"]] = f"M{planung.bogen_zeile(con, pid, bid)['nr']}"
    fristen = []
    for p in reihenfolge(entwurf):
        nach = [int(v[1:]) if v.startswith("A") else int(angelegt[v][1:]) for v in p["nach"]]
        auftrag = p["auftrag"] + (f"\n\nInteraktiv, Grund: {p['interaktiv_grund']}" if p.get("interaktiv_grund") else "")   # A2004
        aid = planung.schritt_setzen(con, pid, von, titel=p["titel"], auftrag=auftrag, bogen_id=bogen[p["meilenstein"]],
                                     groesse=p["groesse"], art=p["art"], pruefbefehl=p["abnahme_befehl"], nach=nach or None,
                                     **({"dateibereich": p["bereiche"]} if p.get("bereiche") else {}))
        modell, effort = p_modell(con, pid, p) if p["ausfuehrung"] == "p" else (p["modell"], p["effort"])
        felder = {"art": p["ausfuehrung"], **({"modell": modell} if modell else {}), **({"effort": effort} if effort else {}),
                  **({"pakettyp": p["pakettyp"]} if p.get("pakettyp") else {})}
        arbeitspaket.setzen(con, pid, von, aid, **felder)
        themen.verweise_setzen(con, pid, von, aid, [tid])
        q = fertig_aus_plan(p["fertig_quelle"], tid)                # A1996 (K2): die Fertig-Quelle gehört ins Paket
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=fertigquelle.ART, aufgabe_id=aid,
                         text=json.dumps(q, ensure_ascii=False))
            if p.get("lead_liest"):                                 # A2054: „Lead liest“ – nie automatisch abnehmen
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="lead_liest", aufgabe_id=aid,
                             text=json.dumps({"an": True}))
        if q.get("aus_plan") == "frist":
            fristen.append(f"A{aid}")
        angelegt[p["schluessel"]] = f"A{aid}"
    with db.schreiben(con):
        con.execute("DELETE FROM plan_ereignis WHERE id = ?", (merke,))
        _ereignis(con, pid, von, JA, tid, entwurf=e["id"], angelegt=angelegt, geaendert=geaendert is not None,
                  fertig_quellen={p["schluessel"]: p["fertig_quelle"] for p in entwurf["pakete"]})   # wie geplant (A1996: im Paket)
        hinweise = achtung(entwurf)                  # A2004: p ist die Vorgabe – interaktiv ohne Grund fällt auf
        if hinweise:
            kern._posten(con, pid, "AMW", kern.lead(con, pid) or kern.ENTWICKLER, "meldung",
                         f"TH{tid}: Achtung – {len(hinweise)} Paket(e) interaktiv ohne Grund"[:140],
                         "p ist die Vorgabe für S und M-mechanisch (ohne Oberfläche). Diese Pakete laufen interaktiv, ohne dass der Plan"
                         " einen Grund nennt:\n" + "\n".join(f"- {h}" for h in hinweise)
                         + "\nUmstellen: amw aufgabe aendern <N> --paket p --pruefbefehl … --dateien … – oder den Grund in den Auftrag"
                           " schreiben („Interaktiv, Grund: …“).")
        if fristen:                                  # A1996: „frist“ braucht Tage und Version – die stehen nicht im Plan
            kern._posten(con, pid, "AMW", kern.lead(con, pid) or kern.ENTWICKLER, "meldung",
                         f"TH{tid}: Fertig-Quelle „frist“ vorerst „ja“ – {', '.join(fristen)}"[:140],
                         "Der Plan nennt für diese Pakete „frist“, aber keine Tage und keine Version. Bis jemand sie setzt, gilt"
                         " „ja“ (Urteil): " + ", ".join(fristen) + "\nSetzen: amw aufgabe aendern <N> --fertig-wenn \"frist 7 nach <Version>\"")
    return angelegt


def fertig_aus_plan(wert, tid):
    """A1996 (K2): Fertig-Quelle des Plans → Fertig-Quelle des Pakets (fertigquelle.quelle_lesen-Form).
    commit/release → commit (die Kette schließt beim Release); thema → das Thema des Plans; ja/dokument → ja (Urteil – eine
    Quelle „dokument“ gibt es nicht); frist → ja, bis Tage und Version gesetzt sind (stehen nicht im Plan)."""
    if wert in ("commit", "release"):
        return {"art": "commit", "aus_plan": wert}
    if wert == "thema":
        return {"art": "thema", "thema": int(tid), "aus_plan": wert}
    return {"art": "ja", "aus_plan": wert}


# --- der Planer-Lauf (frischer claude -p, nur Lesen) – #30117 ----------------------------------------------------------------
# Auslöser: Freigabe eines Themas (auch die eigene Bearbeitung des Menschen, F5358 A) und `amw thema planen TH<n>` (Lead/Co).
# Projekt-Einstellung themen_planer = sonnet (Vorgabe) | aus. Er läuft wie der Gegenleser als angemeldeter Lauf der
# Lauf-Schlange (leicht) in einem losgelösten Prozess, liest Thema, Beschlüsse, Meilensteine und Pakete als Dateien und
# antwortet mit JSON nach dem Schema oben. Feste Frist; Kosten ins Ereignis.
ANGESTOSSEN = "thema_planer"                     # {"thema", "fassung", "modell", "prozess"}
WARTET = "thema_planer_wartet"                   # A1970 {"thema", "fassung", "tag", "usd", "grenze"} – Tagesgrenze erreicht
WARTEN_ERLEDIGT = "thema_planer_wartet_erledigt"  # A1970 {"thema", "fassung", "grund"} – Thema nicht mehr frei oder neue Fassung
TAGESGRENZE_USD = 5.0                            # Vorgabe der Projekt-Einstellung planer_tagesgrenze_usd (0 = keine Grenze)
EINSTIEG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "amw-planer.py")
OHNE_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)
FRIST_S = 15 * 60
LAEUFT_H = 6                                     # P462 (6): Warten in der Lauf-Schlange + Frist 15 min, mit Luft
AUFTRAG = (
    "Du bist der Planer eines Software-Projekts. Lies thema.md (ein vom Menschen freigegebenes Konzept-Thema), beschluesse.md, "
    "meilensteine.md und pakete.md (was es schon gibt) sowie schema.md (das Antwort-Format). Entwirf, was gebaut werden muss, "
    "damit das Thema erfüllt ist: einen oder wenige Meilensteine (Lieferpunkte, die mit einer Vorführung oder einem Bericht enden – "
    "endet_mit; kein Ziel- oder Abnahme-Text, der Meilenstein verweist auf das Thema; "
    "einen bestehenden Meilenstein nimmst du mit \"bestehend\": Nummer) und kleine Pakete (je eins für einen Agenten an einem Tag "
    "oder weniger), mit Abhängigkeiten. Was es schon gibt, planst du nicht noch einmal; brauchst du ein vorhandenes Paket als "
    "Vorgänger, nennst du es als \"A1234\". Was in pakete.md zu diesem Thema als [fertig] steht, schlägst du nie neu vor. "
    "Steht in meilensteine.md ein offener Meilenstein, dessen Ziel auf dieses Thema verweist (★), hängst du die Pakete dort an "
    "(\"bestehend\": Nummer), statt einen neuen anzulegen. Oberflächen-Pakete (art oberflaeche) laufen immer mit ausfuehrung "
    "agent, das erste davon ist eine Kleinprobe zum Ansehen; ausfuehrung p nur mit einem Abnahme-Befehl, den die AMW selbst "
    "ausführen kann – befehle.md nennt, welche gesperrt sind (kein python -c, nichts Verkettetes). p ist die Vorgabe: jedes Paket der Größe S – und M bei Art mechanisch –, das keine Oberfläche ist, keinen "
    "gesperrten Bereich braucht und weder Bildschirm noch Grafikkarte, schneidest du als ausfuehrung p, mit abnahme_befehl (vor "
    "dem Bau rot: ein neuer Test im Paket mit pakettyp test-schreiben oder ein vorgezogenes Test-Paket als Vorgänger) und engen "
    "bereiche; modell/effort lässt du weg (dann gilt die Empfehlung des Projekts). Interaktiv (ausfuehrung agent) so ein Paket "
    "nur mit interaktiv_grund (Optik, Erkundung, gesperrter Bereich, Marcels Auge). Braucht das Thema nichts (schon gebaut, nur ein Begriff), antworte mit "
    "nichts_zu_bauen und Grund. Antworte NUR mit dem JSON-Objekt nach schema.md – kein Text davor oder danach. "
    "Du änderst nichts, du schreibst keine Dateien, du führst nichts aus.")


def einstellung(con, pid):
    return kern.projekt_wahl(con, pid, "themen_planer")


def tagesgrenze(con, pid):
    """A1970: Dollar je Projekt und Tag für alle Planer-Läufe zusammen – None = keine Grenze (Einstellung 0)."""
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    v = (json.loads(r[0] or "{}") if r else {}).get("planer_tagesgrenze_usd")
    v = TAGESGRENZE_USD if v is None else float(v)
    return v if v > 0 else None


def _tag(zeit_utc=None):
    """Der Kalendertag in der Ortszeit des PCs (so meint der Mensch „heute“) – für zeit_utc oder jetzt."""
    import datetime
    if zeit_utc is None:
        return datetime.datetime.now().astimezone().date().isoformat()
    t = db.utc_lesen(zeit_utc)
    return t.astimezone().date().isoformat()


def heute_usd(con, pid, tag=None):
    """Kosten aller Planer-Läufe des Projekts an diesem Tag (aus den Entwürfen, auch fehlerhaften) – je Thema und, seit A2030,
    die Grob-Planer über das ganze Konzept (grobplan_entwurf), seit A2031 die Feinplaner je Meilenstein (feinplan_entwurf) und,
    seit A2029, die Prüfer zum Abschluss (abschluss_ergebnis):
    eine gemeinsame Tagesgrenze."""
    tag = tag or _tag()
    summe = 0.0
    for r in con.execute("SELECT zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art IN (?, 'grobplan_entwurf', 'feinplan_entwurf', 'abschluss_ergebnis')",
                         (pid, ENTWURF)):
        if _tag(r["zeit_utc"]) != tag:
            continue
        try:
            usd = json.loads(r["text"] or "{}").get("usd")
        except ValueError:
            continue
        if isinstance(usd, (int, float)):
            summe += usd
    return round(summe, 2)


def _wartet(con, pid, tid=None):
    """Wartende Planer (Tagesgrenze): je Thema das jüngste Warten, das noch nicht durch ein späteres Anstoßen oder ein
    „Warten erledigt“ abgeschlossen ist."""
    aus = {}
    for r in con.execute("SELECT id, art, text FROM plan_ereignis WHERE projekt_id = ? AND art IN (?, ?, ?) ORDER BY id",
                         (pid, WARTET, ANGESTOSSEN, WARTEN_ERLEDIGT)):
        try:
            d = json.loads(r["text"] or "{}")
        except ValueError:
            continue
        if tid is not None and d.get("thema") != int(tid):
            continue
        if r["art"] == WARTET:
            aus[d.get("thema")] = {**d, "id": r["id"]}
        else:
            aus.pop(d.get("thema"), None)
    return aus


def _grenze_erreicht(con, pid, tid, fassung, lead):
    """Ist die Tagesgrenze erreicht, merkt die AMW das Thema vor (einmal je Fassung) und sagt es dem Lead einmal am Tag.
    Aufruf in einer Schreib-Transaktion. Rückgabe: Text oder None (Grenze nicht erreicht)."""
    grenze = tagesgrenze(con, pid)
    if grenze is None:
        return None
    tag, usd = _tag(), heute_usd(con, pid)
    if usd < grenze:
        return None
    w = _wartet(con, pid, tid).get(int(tid))
    if not (w and w.get("fassung") == fassung):
        heute_gemeldet = any(e.get("tag") == tag and e.get("gemeldet") for e in _alle(con, pid, WARTET))
        _ereignis(con, pid, "AMW", WARTET, tid, fassung=fassung, tag=tag, usd=usd, grenze=grenze, gemeldet=not heute_gemeldet)
        if lead and lead != kern.ENTWICKLER and not heute_gemeldet:
            kern._posten(con, pid, "AMW", lead, "meldung", f"Planer: Tagesgrenze {grenze:.2f} $ erreicht – TH{tid} wartet bis morgen",
                         f"Die Planer-Läufe haben heute {usd:.2f} $ gekostet (Grenze planer_tagesgrenze_usd = {grenze:.2f} $). "
                         f"TH{tid} Fassung {fassung} und weitere Themen von heute plant die AMW morgen selbst. Sofort: "
                         "Grenze erhöhen (amw projekt einstellen planer_tagesgrenze_usd=…) und amw thema planen TH<n>.")
    return f"TH{tid}: Tagesgrenze der Planer erreicht ({usd:.2f} von {grenze:.2f} $) – plant morgen"


def _alle(con, pid, art):
    aus = []
    for (t,) in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ?", (pid, art)):
        try:
            aus.append(json.loads(t or "{}"))
        except ValueError:
            pass
    return aus


def nachholen(con, pid):
    """Dienst-Runde: Themen, deren Planer an einem früheren Tag an der Tagesgrenze wartete, jetzt anstoßen (die Grenze gilt
    wieder) – nur, wenn das Thema noch freigegeben ist, die wartende Fassung die freigegebene ist und kein „nichts zu bauen“
    vermerkt ist; sonst ist das Warten erledigt (Ereignis, kommt nie wieder) – auch, wenn der Projekt-Schalter nicht auf „an“
    steht (A1999: beim Einschalten wird nichts nachgeholt, der Lead stößt mit `amw thema planen` an). Angestoßen wird wie nach
    der Freigabe (ohne erneut): alle Prüfungen von anstossen gelten. Rückgabe: Texte."""
    from . import themen
    heute = _tag()
    aus = []
    ausgeschaltet = kern.projekt_schalter(con, pid) != "an"   # A1999: nichts nachholen – nach dem Einschalten stößt der Lead an
    for tid, w in sorted(_wartet(con, pid).items()):
        if w.get("tag") == heute or tid is None:
            continue
        t = con.execute("SELECT * FROM thema WHERE id = ? AND projekt_id = ?", (tid, pid)).fetchone()
        s = themen.status(con, t) if t else None
        grund = ("Thema gibt es nicht mehr" if not t else "Projekt ausgeschaltet" if ausgeschaltet
                 else "nichts zu bauen" if _nichts_vermerkt(con, pid, tid)
                 else "nicht mehr freigegeben" if s["status"] != "frei"
                 else f"freigegeben ist Fassung {s['freigegeben']}" if s["freigegeben"] != w.get("fassung") else None)
        if grund:
            with db.schreiben(con):
                _ereignis(con, pid, "AMW", WARTEN_ERLEDIGT, tid, fassung=w.get("fassung"), grund=grund)
            aus.append(f"TH{tid}: Warten erledigt – {grund}")
            continue
        x = anstossen(con, pid, tid, w.get("fassung"))
        if x:
            aus.append(x)
        if x and "Tagesgrenze" in x:                  # heute schon wieder voll: der Rest wartet weiter
            break
    return aus


def _angestossen(con, pid, tid):
    return _ereignisse(con, pid, tid, ANGESTOSSEN)


def laeuft(con, pid, tid):
    """Plant gerade ein Planer dieses Thema? Das Ereignis „angestoßen“ ohne Entwurf danach (und nicht älter als LAEUFT_H)."""
    import datetime
    an = _angestossen(con, pid, tid)
    if not an:
        return None
    if any(e["id"] > an[-1]["id"] for e in _ereignisse(con, pid, tid, ENTWURF)):
        return None
    t = db.utc_lesen(an[-1]["zeit_utc"])
    return None if (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() > LAEUFT_H * 3600 else an[-1]


def _spawn(pid, tid, fassung, umgebung=None):
    befehl = [sys.executable, "-I", "-X", "utf8", EINSTIEG, "--projekt-id", str(pid), "--thema", str(tid), "--fassung", str(fassung)]
    flags = (0x00000008 | 0x00000200 | OHNE_FENSTER) if os.name == "nt" else 0        # DETACHED, NEW_GROUP wie der Gegenleser
    return subprocess.Popen(befehl, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                            creationflags=flags, env=umgebung, start_new_session=os.name != "nt").pid


STARTER = _spawn             # Tests setzen eine Attrappe; tests/abschotten schaltet das Anstoßen ganz ab (AMW_PLANER_AUS)


def _nichts_vermerkt(con, pid, tid):
    ev = _ereignisse(con, pid, tid, NICHTS)
    return bool(ev) and ev[-1].get("an", True)


def schalter_text(con, pid):
    """A1999: Steht der Projekt-Schalter nicht auf „an“, läuft kein Planer – Rückgabe: die Antwort für `amw thema planen`, sonst None."""
    s = kern.projekt_schalter(con, pid)
    if s == "an":
        return None
    return ("Projekt ist ausgeschaltet" if s == "aus" else "Projekt steht auf Probe") + " – Planer läuft erst nach dem Einschalten"


def neues_projekt(con, pid):
    """A2030 (TL #31613 A): Ein Projekt ohne Konzept-Abschluss und ohne Meilensteine geht den neuen Weg – erst „Konzept
    abschließen“, dann EIN Grob-Planer über alle Themen. Bis dahin stößt die Freigabe eines Themas keinen Planer je Thema an
    (`amw thema planen` von Hand geht immer). Bestehende Projekte mit Meilensteinen bleiben wie bisher."""
    if con.execute("SELECT 1 FROM bogen WHERE projekt_id = ? AND status != 'verworfen' LIMIT 1", (pid,)).fetchone():
        return False
    return not con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = 'konzept_abschluss' LIMIT 1", (pid,)).fetchone()


def anstossen(con, pid, tid, fassung, von="AMW", erneut=False):
    """Nach der Freigabe (themen.freigeben/bearbeiten, eigene Transaktion) bzw. auf Befehl: einen Planer anstoßen – außer die
    Einstellung ist aus, das Thema hat „nichts zu bauen“, für diese Fassung gab es schon einen (ohne erneut) oder einer läuft.
    Rückgabe: Text oder None."""
    if os.environ.get("AMW_PLANER_AUS") or einstellung(con, pid) == "aus":
        return "Planer ist aus (themen_planer=aus)" if erneut else None
    aus = schalter_text(con, pid)                         # A1999: wie der Gegenleser (A1926) – nur bei eingeschaltetem Projekt
    if aus:
        return aus if erneut else None
    if not erneut and neues_projekt(con, pid):           # A2030 (TL #31613 A): erst die Grobplanung über das ganze Konzept
        return None
    modell = einstellung(con, pid)
    with db.schreiben(con):                               # in einer Schreib-Transaktion: nie doppelt angestoßen
        if laeuft(con, pid, tid):
            return f"TH{tid}: es plant schon ein Planer" if erneut else None
        if not erneut and (any(e.get("fassung") == fassung for e in _angestossen(con, pid, tid)) or _nichts_vermerkt(con, pid, tid)):
            return None
        grenze = _grenze_erreicht(con, pid, tid, fassung, kern.lead(con, pid))   # A1970: Kosten je Projekt und Tag
        if grenze:
            return grenze
        wer = planer_fortschritt.ausloeser(von)           # A2078
        eid = _ereignis(con, pid, von, ANGESTOSSEN, tid, fassung=fassung, modell=modell, **wer)
    try:
        prozess = STARTER(pid, tid, fassung)
    except OSError as e:                                  # ließ sich nicht starten → Entwurf mit Fehler, der Lead erfährt es
        entwurf_eintragen(con, pid, tid, fassung, None, modell=modell, fehler=f"Planer ließ sich nicht starten: {e}")
        return f"TH{tid}: Planer ließ sich nicht starten ({e})"
    with db.schreiben(con):
        con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?",
                    (json.dumps({"thema": int(tid), "fassung": fassung, "modell": modell, "prozess": prozess, **wer}, ensure_ascii=False), eid))
    return f"TH{tid} Fassung {fassung}: Planer ({modell}) angestoßen"


SCHEMA_TEXT = __doc__[__doc__.index("Schema des Planer-Ergebnisses"):].strip()


def _dateien(con, pid, t, fassung, ordner, delta=None, nachbessern=None):
    from . import themen
    f = con.execute("SELECT text FROM thema_fassung WHERE thema_id = ? AND nr = ?", (t["id"], fassung)).fetchone()
    if not f:
        raise kern.AmwFehler(f"TH{t['id']} hat keine Fassung {fassung}")
    b = con.execute("SELECT id, stichwort, regel FROM beschluss WHERE projekt_id = ? AND thema = ? COLLATE NOCASE AND status = 'gilt'"
                    " ORDER BY id", (pid, t["name"])).fetchall()
    ms = con.execute("SELECT nr, titel, status, ziel FROM bogen WHERE projekt_id = ? AND status IN ('geplant', 'aktiv') ORDER BY nr",
                     (pid,)).fetchall()                  # A1976: nur offene – fertige taugen nicht als „bestehend“
    verknuepft = themen.aufgaben_zu(con, pid, t["id"], alle=True)
    zum_thema = {a["id"] for a in verknuepft}
    th = f"TH{t['id']}"
    offen = con.execute("SELECT id, titel, status FROM aufgabe WHERE projekt_id = ? AND status NOT IN ('fertig', 'verworfen')"
                        " ORDER BY id DESC LIMIT 200", (pid,)).fetchall()
    teile = {"thema.md": f"# TH{t['id']} {t['name']} – Fassung {fassung}\n\n{f['text']}\n",
             "beschluesse.md": "# Geltende Beschlüsse zum Thema\n\n"
                               + ("\n".join(f"- B{x['id']} {x['stichwort']}: {x['regel']}" for x in b) or "(keine)") + "\n",
             "meilensteine.md": f"# Offene Meilensteine des Projekts (★ = Ziel verweist auf {th})\n\n"
                                + ("\n".join(f"- {x['nr']}: {x['titel']} [{x['status']}]" + (f" – Ziel: {x['ziel']}" if x["ziel"] else "")
                                             + (" ★" if th in re.findall(r"TH\d+", x["ziel"] or "") else "") for x in ms)
                                   or "(keine)") + "\n",
             "pakete.md": f"# Pakete zu {th} mit Status ([fertig] = schon gebaut, nie neu vorschlagen)\n\n"
                          + ("\n".join(f"- A{x['id']} [{x['status']}] {x['titel']}" for x in verknuepft) or "(keine)")
                          + "\n\n# Weitere offene Pakete des Projekts\n\n"
                          + ("\n".join(f"- A{x['id']} [{x['status']}] {x['titel']}" for x in offen if x["id"] not in zum_thema)
                             or "(keine)") + "\n",
             "schema.md": "# Antwort-Format\n\n" + SCHEMA_TEXT + "\n"}
    from . import arbeiter
    teile["befehle.md"] = arbeiter.befehle_text()        # A2076: gesperrte Abnahme-Befehle
    if delta:                                            # A2027: was sich am Thema geändert hat und wen es betrifft
        from . import planer_delta
        teile["aenderung.md"] = planer_delta.datei(con, pid, delta)
        teile["erlaubt.md"] = planer_delta.erlaubt(con, delta)          # A2076: je Paket, was der Planer damit darf
    if nachbessern:                                      # A2076: die erste Antwort passte nicht – genau diese Funde
        teile["nachbessern.md"] = ("# Deine erste Antwort passte nicht\n\n## Funde\n\n"
                                   + "\n".join(f"- {x}" for x in nachbessern["funde"][:25])
                                   + "\n\n## Deine erste Antwort\n\n" + str(nachbessern.get("antwort") or "")[:40000] + "\n")
    for name, text in teile.items():
        with open(os.path.join(ordner, name), "w", encoding="utf-8", newline="\n") as d:
            d.write(text)
    return sorted(teile)


def json_aus_text(text):
    """Das JSON-Objekt aus der Antwort (auch in einem Code-Block oder mit einem Satz drumherum) – oder der Text selbst."""
    s = (text or "").strip()
    a, b = s.find("{"), s.rfind("}")
    return s[a:b + 1] if 0 <= a < b else s


NACHBESSERN = (
    "NACHBESSERN: Deine erste Antwort passte nicht zum Schema bzw. zu den Regeln. Lies nachbessern.md (die Funde und deine erste "
    "Antwort), bessere genau diese Funde nach und antworte wieder nur mit dem vollständigen JSON.")


def planen_mit_nachbesserung(con, pid, t, fassung, modell, prog=None, zusatz=None, melden=None):
    """A2076 (Muster A2067): planen; passt die Antwort nicht (pruefen), gehen die Funde EINMAL zurück an den Planer. Vorher wird
    noch einmal geprüft, ob er darf: Tagesgrenze (samt dem ersten Lauf), Projekt-Schalter, Einstellung. Kosten zählen zusammen.
    Rückgabe wie planen, dazu "nachgebessert" (Text für den Lead) und "vorher" (Funde der ersten Antwort), wenn die erste nicht passte."""
    aus = planen(con, pid, t, fassung, modell, prog=prog, zusatz=zusatz)
    if aus.get("fehler") or aus.get("ergebnis") is None:
        return aus
    try:
        pruefen(aus["ergebnis"], con, pid, t["id"], delta=aus.get("delta"))
        return aus
    except PlanFehler as e:
        funde = e.fehler
    grenze = tagesgrenze(con, pid)
    stand = heute_usd(con, pid) + (aus["usd"] if isinstance(aus.get("usd"), (int, float)) else 0)
    warum = ("die Tagesgrenze der Planer ist erreicht" if grenze is not None and stand >= grenze
             else schalter_text(con, pid) or ("der Planer ist aus" if os.environ.get("AMW_PLANER_AUS") or einstellung(con, pid) == "aus" else None))
    if warum:
        return {**aus, "nachgebessert": f"Nicht nachgebessert: {warum}."}
    if melden:
        melden(f"Antwort passte nicht ({len(funde)} Funde) – eine Nachbesserung")
    try:
        neu = planen(con, pid, t, fassung, modell, prog=prog, zusatz=zusatz, nachbessern={"funde": funde, "antwort": aus["ergebnis"]})
    except Exception as e:                                # noqa: BLE001 – die Kosten des ersten Laufs bleiben gezählt
        neu = {"ergebnis": None, "usd": None, "fehler": f"{type(e).__name__}: {e}"[:300], "delta": aus.get("delta")}
    usd = [x for x in (aus.get("usd"), neu.get("usd")) if isinstance(x, (int, float))]
    return {**neu, "usd": round(sum(usd), 4) if usd else None, "vorher": funde,
            "nachgebessert": "Auch die eine automatische Nachbesserung passte nicht." if not neu.get("fehler")
            else "Die automatische Nachbesserung ging nicht."}


def planen(con, pid, t, fassung, modell, prog=None, zusatz=None, nachbessern=None):
    """Der Planer selbst, in einem leeren eigenen Ordner (wie ein Platz). Rückgabe {"ergebnis", "usd", "fehler"}."""
    from . import arbeiter, planer_delta, planhinweis, platz, versionsprobe
    with tempfile.TemporaryDirectory(prefix="amw-planer-", ignore_cleanup_errors=True) as ordner:
        p = platz.pfade(os.path.join(ordner, "plaetze"), 1)
        os.makedirs(p["klon"])
        subprocess.run(["git", "init", "-q", "-b", "main", p["klon"]], check=True, capture_output=True, creationflags=OHNE_FENSTER)
        delta = planer_delta.kontext(con, pid, t["id"])  # A2027: geändertes, schon geplantes Thema → nur die Änderung
        dateien = _dateien(con, pid, t, fassung, p["klon"], delta, nachbessern)
        extra = planhinweis.schreiben(con, pid, t["id"], p["klon"])     # A2028: Überarbeiten nach Hinweisen
        r = arbeiter.laufen(p, AUFTRAG + ("\n\n" + planer_delta.AUFTRAG if delta else "") + ("\n\n" + planhinweis.AUFTRAG if extra else "")
                            + ("\n\n" + NACHBESSERN if nachbessern else "")
                            + "\n\nDateien: " + ", ".join(dateien + extra), None, modell=modell, effort="medium", prog=prog,
                            zusatz=zusatz, nur_lesen=True, geprueft=versionsprobe.geprueft(con), frist_s=FRIST_S)
    erg = r.get("ergebnis") or {}
    usd = erg.get("total_cost_usd")
    if r.get("abweichungen"):
        return {"ergebnis": None, "usd": usd, "fehler": "; ".join(r["abweichungen"])[:500], "delta": delta}
    text = (erg.get("result") or "").strip()
    if r.get("rc") != 0 or erg.get("is_error") or not text:
        return {"ergebnis": None, "usd": usd, "fehler": r.get("fehler") or f"kein Ergebnis (rc {r.get('rc')})", "delta": delta}
    return {"ergebnis": json_aus_text(text), "usd": usd, "fehler": None, "delta": delta}


def ausfuehren(con, pid, tid, fassung, prog=None, zusatz=None):
    """Als angemeldeter Lauf der Lauf-Schlange (leicht): warten, bis er dran ist, planen, Entwurf eintragen (auch einen Fehler)."""
    from . import belegung, betrieb
    modell = (_angestossen(con, pid, tid) or [{}])[-1].get("modell") or "sonnet"
    t = con.execute("SELECT * FROM thema WHERE id = ? AND projekt_id = ?", (tid, pid)).fetchone()
    agent = kern.lead(con, pid) or kern.ENTWICKLER
    lid = betrieb.lauf_start(con, pid, agent, f"Planer TH{tid} Fassung {fassung} ({modell}, A1940, automatisch)", None, False, False,
                             None, warten=True, waechter=os.getpid(), befehl=None, ordner=None, selbst=True)   # A1948: kein Weckruf
    belegung.lauf_merken(lid, os.getpid())
    name = f"TH{tid}" + (f" {t['name']}" if t else "")
    fortschritt = functools.partial(planer_fortschritt.melden_still, con, pid, lid, art="planer", thema=tid, agent=agent,
                                    modell=modell, fassung=fassung, **planer_fortschritt.vom((_angestossen(con, pid, tid) or [{}])[-1]))            # A2025: Stand in der AMW, gedrosselt
    fortschritt(was=f"{name}: wartet auf einen Platz in der Lauf-Schlange",
                dauer_s=planer_fortschritt.schaetzung(con, pid, "planer"), sofort=True)
    aus = None
    try:
        while True:
            l = betrieb.lauf_zeile(con, pid, lid)
            if l["status"] == "laeuft":
                break
            if l["status"] in ("fertig", "abgebrochen"):
                raise RuntimeError(f"L{lid} ist {l['status']} – nicht geplant")
            time.sleep(5)
        betrieb.lauf_uebernehmen(con, lid, "agent")
        if not t:
            raise kern.AmwFehler(f"TH{tid} gibt es nicht")
        fortschritt(was=f"{name}: Fassung {fassung} wird geplant", sofort=True)
        aus = planen_mit_nachbesserung(con, pid, t, fassung, modell, prog=prog, zusatz=zusatz,             # A2076
                                       melden=lambda x: fortschritt(was=f"{name}: {x}", sofort=True))
    except Exception as e:                                # noqa: BLE001 – niemand sieht die Ausgabe: als Fehler eintragen
        aus = {"ergebnis": None, "usd": None, "fehler": f"{type(e).__name__}: {e}"[:300]}
    finally:
        aus = aus or {"ergebnis": None, "usd": None, "fehler": "abgebrochen"}
        kosten = f"{aus['usd']:.2f} $" if isinstance(aus.get("usd"), (int, float)) else "Kosten unbekannt"
        try:
            betrieb.lauf_ende(con, pid, agent, lid, 1 if aus.get("fehler") else 0,
                              (f"Planer TH{tid} Fassung {fassung}: " + (f"Fehler – {aus['fehler']}" if aus.get("fehler") else "fertig")
                               + f" · {kosten}")[:500])
        finally:
            belegung.lauf_vergessen(lid)
    entwurf_eintragen(con, pid, tid, fassung, aus.get("ergebnis"), modell=modell, usd=aus.get("usd"), lauf=lid, fehler=aus.get("fehler"),
                      delta=aus.get("delta"), vorher=aus.get("vorher"), nachgebessert=aus.get("nachgebessert"))
    if aus.get("fehler"):
        fortschritt(was=f"{name}: nicht geplant", usd=aus.get("usd"), zustand="fehler", fehler=aus["fehler"])
    else:
        fortschritt(was=f"{name}: Entwurf liegt vor", usd=aus.get("usd"), zustand="fertig")
    return aus


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="amw-planer")
    if "--grob" in (argv if argv is not None else sys.argv[1:]):   # A2030: Grob-Planer über das ganze Konzept
        from . import grobplan
        return grobplan.main([x for x in (argv if argv is not None else sys.argv[1:]) if x != "--grob"])
    if "--abschluss" in (argv if argv is not None else sys.argv[1:]):   # A2029: Gesamttest und Prüfer zum Abschluss
        from . import abschluss
        return abschluss.main([x for x in (argv if argv is not None else sys.argv[1:]) if x != "--abschluss"])
    if "--fein" in (argv if argv is not None else sys.argv[1:]):   # A2031: Feinplaner je Meilenstein
        from . import feinplanung
        return feinplanung.main([x for x in (argv if argv is not None else sys.argv[1:]) if x != "--fein"])
    ap.add_argument("--projekt-id", type=int, required=True)
    ap.add_argument("--thema", type=int, required=True)
    ap.add_argument("--fassung", type=int, required=True)
    x = ap.parse_args(argv)
    con = db.verbinde()
    try:
        ausfuehren(con, x.projekt_id, x.thema, x.fassung)
    finally:
        con.close()
