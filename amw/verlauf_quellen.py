"""Verlauf im Projektweg je Schritt: was an anderer Stelle schon gespeichert ist, wird hier abgeleitet (A2077, TH164 „Verlauf“).

verlauf.projektweg liest die Ereignisse zu Themen, Grobplan und Freigaben. Dieses Modul ergänzt aus den Daten, die es ohnehin gibt –
nichts wird doppelt gespeichert, der Altbestand erscheint mit:
- Feinplanung: Feinplaner angestoßen und sein Ergebnis je Fassung (auch abgelehnt, mit Gründen), Konzeptänderung (Ja, angewandt, gestartet).
- Umsetzung (nur Pakete mit Meilenstein): zugeteilt, gestartet (Headless je Start, Fenster der erste Start), abgegeben, Prüfung
  grün/rot, fertig/verworfen (nur der letzte Abschluss), ausgeliefert, Meilenstein gestartet.
- Abschluss: Prüfung angestoßen und Ergebnis, bereit zur Abnahme, abgeschlossen.
- Pause (A2137, in Umsetzung): an (Grund, Ende) und aufgehoben, auch durch die AMW nach dem Ende.
Je Tatsache genau eine Quelle: ein Headless-Start steht in headless_start (davor paket_zustand), nicht noch einmal aus begonnen_utc;
eine Entscheidung der AMW steht nur da, wenn es zum Paket keine Prüfung in der Tabelle pruefung gibt.

Die Reihenfolge bei gleicher Sekunde ist fest (RANG der Quelle, dann Nummer). Aufeinanderfolgende gleiche Einträge (dieselbe Art, derselbe,
derselbe Meilenstein, höchstens BUENDEL_S Abstand) werden eine Zeile; die Titel und Nummern stehen im Feld „mehr“ (auf Klick).
Begrenzt: ROH Zeilen je Quelle, danach GRENZE Einträge je Schritt – gezählt nach dem Zusammenfassen.
"""
import json
import re

from . import db, kern

ROH = 500                        # so viele jüngste Rohzeilen je Quelle
GRENZE = 120                     # so viele Einträge je Schritt zeigt die Seite
BUENDEL_S = 10 * 60
TITEL_MAX = 70                   # gekürzt wird der Titel, nicht der Satz – was geschah, bleibt lesbar; ganz auf Klick
RANG = ("weg", "feinplan_angestossen", "feinplan_entwurf", "delta", "ms_start", "schieben", "schieben_ende", "pruefpunkt", "pruefpunkt_ende", "agent", "pause", "verteilt", "start", "abgabe", "pruefung", "entscheidung", "abschluss",
        "auslieferung", "ab_angestossen", "ab_bereit", "ab_ergebnis", "ms_fertig")
# Art → (ein Paket, mehrere); {m} Meilenstein, {t} Titel, {n} Anzahl, {x} Zusatz
TEXTE = {
    "verteilt": ("{m}: „{t}“ an {x} zugeteilt", "{m}: {n} Pakete an {x} zugeteilt"),
    "start": ("{m}: „{t}“ gestartet", "{m}: {n} Pakete gestartet"),
    "abgabe": ("{m}: „{t}“ abgegeben", "{m}: {n} Pakete abgegeben"),
    "pruefung_gruen": ("{m}: Prüfung grün – „{t}“", "{m}: Prüfung grün – {n} Pakete"),
    "pruefung_rot": ("{m}: Prüfung rot – „{t}“", "{m}: Prüfung rot – {n} Pakete"),
    "entschieden_e7": ("{m}: geprüft und angenommen – „{t}“", "{m}: geprüft und angenommen – {n} Pakete"),
    "entschieden_e5": ("{m}: Nachbesserung – „{t}“", "{m}: Nachbesserung – {n} Pakete"),
    "entschieden_lead": ("{m}: geht an den Lead – „{t}“", "{m}: {n} Pakete gehen an den Lead"),
    "fertig": ("{m}: „{t}“ fertig", "{m}: {n} Pakete fertig"),
    "verworfen": ("{m}: „{t}“ verworfen", "{m}: {n} Pakete verworfen"),
}


def _json(text):
    try:
        d = json.loads(text or "{}")
    except ValueError:
        return {}
    return d if isinstance(d, dict) else {}


def _neueste(con, sql, par):
    """Die jüngsten ROH Zeilen einer Quelle (jede Abfrage sortiert absteigend nach ihrer Zeit)."""
    return con.execute(sql + f" LIMIT {ROH}", par).fetchall()


def _rolle(von):
    return "mensch" if von == kern.ENTWICKLER else "amw" if von == "AMW" else "agent"


def _eintrag(quelle, nr, zeit, rolle, von, art, schritt, bogen, ms, titel=None, zusatz=None, text=None, mehr=None, aufgabe=None, fehler=None):
    return {"id": f"{quelle}:{nr}", "zeit": zeit, "rolle": rolle, "von": von, "art": art, "schritt": schritt, "aufgabe_id": aufgabe,
            "bogen_id": bogen, "ms": ms, "titel": titel, "zusatz": zusatz, "text": text, "nummer": mehr, "fehler": fehler,
            "rang": (RANG.index(quelle), nr)}


# --- Quellen -----------------------------------------------------------------------------------------------------------------

def _mengen(con, pid):
    """Einmal gelesen statt je Zeile gefragt: Meilenstein-Pakete {id: Zeile} und die Aufgaben mit Headless-Start, Wechsel auf „läuft“,
    Rückmeldung, Prüfung; dazu wer zuletzt abgeschlossen hat."""
    pakete = {r["id"]: r for r in con.execute(
        "SELECT a.id, a.titel, a.bogen_id, a.agent, a.status, a.begonnen_utc, a.fertig_utc, b.nr FROM aufgabe a JOIN bogen b ON b.id = a.bogen_id"
        " AND b.projekt_id = a.projekt_id WHERE a.projekt_id = ?", (pid,))}
    je = {"headless_start": set(), "paket_zustand": set(), "paket_ergebnis": set()}
    wer = {}
    for r in con.execute("SELECT art, aufgabe_id, von, text FROM plan_ereignis WHERE projekt_id = ? AND art IN ('headless_start', 'paket_zustand',"
                         " 'paket_ergebnis', 'aufgabe_abschluss') AND aufgabe_id IS NOT NULL ORDER BY id", (pid,)):
        if r["art"] == "aufgabe_abschluss":
            wer[r["aufgabe_id"]] = r["von"]                # der letzte gilt
        elif r["art"] != "paket_zustand" or "→ laeuft" in (r["text"] or ""):
            je[r["art"]].add(r["aufgabe_id"])
    geprueft = {r[0] for r in con.execute("SELECT DISTINCT aufgabe_id FROM pruefung WHERE projekt_id = ? AND aufgabe_id IS NOT NULL", (pid,))}
    return pakete, je, geprueft, wer


EREIGNISSE = ("verteilt", "headless_start", "paket_zustand", "paket_ergebnis", "paket_entscheidung")


def _umsetzung(con, pid):
    pakete, je, geprueft, wer = _mengen(con, pid)
    aus = []
    for art in EREIGNISSE:
        for r in _neueste(con, "SELECT id, zeit_utc, von, text, aufgabe_id FROM plan_ereignis WHERE projekt_id = ? AND art = ?"
                               + (" AND text LIKE '%→ laeuft%'" if art == "paket_zustand" else "") + " ORDER BY id DESC", (pid, art)):
            a = pakete.get(r["aufgabe_id"])
            if not a:
                continue                                   # ohne Meilenstein: nicht im Projektweg

            def e(quelle, rolle, von, was, zusatz=None, a=a, r=r):
                aus.append(_eintrag(quelle, r["id"], r["zeit_utc"], rolle, von, was, "umsetzung", a["bogen_id"], a["nr"], a["titel"], zusatz=zusatz, aufgabe=a["id"]))
            if art == "verteilt":
                e("verteilt", _rolle(r["von"]), r["von"], "verteilt", _json(r["text"]).get("agent") or "?")
            elif art == "headless_start" or (art == "paket_zustand" and a["id"] not in je["headless_start"]):
                e("start", "amw", "AMW", "start")          # jeder Start; vor A2047 aus dem Wechsel auf „läuft“
            elif art == "paket_ergebnis":
                e("abgabe", "agent", "Headless" if _json(r["text"]).get("quelle") == "p" else r["von"], "abgabe")
            elif art == "paket_entscheidung" and a["id"] not in geprueft:
                z = str(_json(r["text"]).get("zeile") or "")
                e("entscheidung", "pruefer" if r["von"] not in ("AMW", kern.ENTWICKLER) else _rolle(r["von"]), r["von"],
                  "entschieden_e7" if z.startswith("E7") else "entschieden_e5" if z == "E5" else "entschieden_lead")
    for r in _neueste(con, "SELECT id, angefragt_utc, ergebnis_utc, ergebnis, bauer, pruefer, aufgabe_id FROM pruefung WHERE projekt_id = ?"
                           " AND aufgabe_id IS NOT NULL ORDER BY id DESC", (pid,)):
        a = pakete.get(r["aufgabe_id"])
        if not a:
            continue
        if a["id"] not in je["paket_ergebnis"]:            # sonst steht die Abgabe schon aus der Rückmeldung da
            aus.append(_eintrag("abgabe", r["id"], r["angefragt_utc"], _rolle(r["bauer"]), r["bauer"], "abgabe", "umsetzung", a["bogen_id"], a["nr"],
                                a["titel"], mehr=f"P{r['id']}", aufgabe=a["id"]))
        if r["ergebnis"] in ("gruen", "rot") and r["ergebnis_utc"]:
            aus.append(_eintrag("pruefung", r["id"], r["ergebnis_utc"], "amw" if r["pruefer"] == "AMW" else "pruefer", r["pruefer"],
                                f"pruefung_{r['ergebnis']}", "umsetzung", a["bogen_id"], a["nr"], a["titel"], mehr=f"P{r['id']}", aufgabe=a["id"]))
    for feld in ("begonnen_utc", "fertig_utc"):
        for a in sorted((x for x in pakete.values() if x[feld]), key=lambda x: (x[feld], x["id"]))[-ROH:]:
            if feld == "begonnen_utc":                     # Fenster: der erste Start; ein Headless-Start steht schon da
                if a["id"] not in je["headless_start"] and a["id"] not in je["paket_zustand"]:
                    aus.append(_eintrag("start", a["id"], a[feld], _rolle(a["agent"]), a["agent"] or "AMW", "start", "umsetzung", a["bogen_id"], a["nr"],
                                        a["titel"], aufgabe=a["id"]))
            elif a["status"] in ("fertig", "verworfen"):   # der Stand der Aufgabe: wieder geöffnet und neu geschlossen steht nur einmal da
                von = wer.get(a["id"]) or a["agent"] or "AMW"
                aus.append(_eintrag("abschluss", a["id"], a[feld], _rolle(von), von, a["status"], "umsetzung", a["bogen_id"], a["nr"], a["titel"],
                                    aufgabe=a["id"]))
    return aus


def _auslieferung(con, pid):
    """Eine Zeile je Version – nur mit Aufgaben, die zu einem Meilenstein dieses Projekts gehören; Nummern und Titel auf Klick."""
    titel = {r["id"]: r["titel"] for r in con.execute("SELECT a.id, a.titel FROM aufgabe a JOIN bogen b ON b.id = a.bogen_id AND b.projekt_id = a.projekt_id"
                                                      " WHERE a.projekt_id = ?", (pid,))}
    aus = []
    for r in _neueste(con, "SELECT id, zeit_utc, version, aufgaben, commit_sha, eingetragen_von FROM release WHERE projekt_id = ? AND art = 'version'"
                           " AND aufgaben IS NOT NULL ORDER BY id DESC", (pid,)):
        ids = [int(x) for x in re.findall(r"\bA(\d+)", r["aufgaben"]) if int(x) in titel]
        if ids:
            mehr = " · ".join(f"A{x} {titel[x]}" for x in dict.fromkeys(ids)) + (f" · {r['commit_sha'][:8]}" if r["commit_sha"] else "")
            n = len(set(ids))
            aus.append(_eintrag("auslieferung", r["id"], r["zeit_utc"], "amw", "AMW", "auslieferung", "umsetzung", None, None,
                                text=f"Version {r['version']} ausgeliefert: {n} Paket{'e' if n != 1 else ''}", mehr=mehr))
    return aus


def _feinplan(con, pid):
    nr = {r["id"]: r["nr"] for r in con.execute("SELECT id, nr FROM bogen WHERE projekt_id = ?", (pid,))}
    aus = []
    for r in _neueste(con, "SELECT id, zeit_utc, von, art, text, bogen_id FROM plan_ereignis WHERE projekt_id = ? AND art IN ('feinplan_angestossen',"
                           " 'feinplan_entwurf') ORDER BY id DESC", (pid,)):
        d = _json(r["text"])
        name = ", ".join(f"M{nr[b]}" for b in d.get("boegen") or [] if b in nr) or "?"
        was = "Nacharbeit" if d.get("nacharbeit") else "Feinplan"
        kopf = f"{name}: {was} Fassung {d.get('fassung', '?')}"
        if r["art"] == "feinplan_angestossen":
            aus.append(_eintrag("feinplan_angestossen", r["id"], r["zeit_utc"], _rolle(r["von"]), r["von"], r["art"], "fein", r["bogen_id"], None,
                                text=f"{kopf}: Planer angestoßen"))
            continue
        f = d.get("fehler")
        n = len((d.get("entwurf") or {}).get("pakete") or [])
        aus.append(_eintrag("feinplan_entwurf", r["id"], r["zeit_utc"], "planer", "Planer", r["art"], "fein", r["bogen_id"], None,
                            text=f"{kopf} passte nicht" if f else f"{kopf} mit {n} Paket{'en' if n != 1 else ''} liegt vor", fehler=f or None))
    return aus


def _pruefpunkte(con, pid):
    """A2096: Prüfpunkt gesetzt, entfernt, getestet (ja) oder zurück – wer, wo, warum."""
    from . import urteil, zwischenpruefung
    zeilen = _neueste(con, "SELECT e.id, e.zeit_utc, e.von, e.art, e.text, e.aufgabe_id, a.titel, b.id AS bogen, b.nr FROM plan_ereignis e JOIN aufgabe a ON a.id = e.aufgabe_id"
                           " JOIN bogen b ON b.id = a.bogen_id WHERE e.projekt_id = ? AND e.art IN (?, ?, ?, ?) AND EXISTS (SELECT 1 FROM plan_ereignis p"
                           " WHERE p.aufgabe_id = e.aufgabe_id AND p.art = ?) ORDER BY e.id DESC",
                      (pid, zwischenpruefung.ART, zwischenpruefung.ENDE, urteil.JA, urteil.ZURUECK, zwischenpruefung.ART))
    titel = {r["id"]: r["titel"] for r in con.execute("SELECT id, titel FROM aufgabe WHERE projekt_id = ?", (pid,))} if zeilen else {}
    name, aus, hinter = kern.entwickler_name(con, pid), [], {}
    for r in reversed(zeilen):
        d = _json(r["text"])
        if r["art"] == zwischenpruefung.ART:
            hinter[r["aufgabe_id"]] = _titel_kurz(titel.get(d.get("nach"), "?"), 40)      # kürzer als sonst: danach steht noch viel, sonst schnitte die Zeile ab, worum es geht
        wo = f"M{r['nr']}: Prüfpunkt hinter „{hinter.get(r['aufgabe_id'], '?')}“"
        n = d.get("wartet") or 0
        text = {zwischenpruefung.ART: f"{wo} – {name} testet, {n} {'Paket wartet' if n == 1 else 'Pakete warten'}" + (f" – {d['grund']}" if d.get("grund") else ""),
                zwischenpruefung.ENDE: f"{wo} entfernt" + (f" – {d['grund']}" if d.get("grund") else ""),
                urteil.JA: f"{wo} – getestet, weiter", urteil.ZURUECK: f"{wo} – zurück: {' '.join((r['text'] or '').split())[:160]}"}[r["art"]]
        aus.append(_eintrag("pruefpunkt" if r["art"] == zwischenpruefung.ART else "pruefpunkt_ende", r["id"], r["zeit_utc"], _rolle(r["von"]), r["von"],
                            "pruefpunkt", "umsetzung", r["bogen"], None, text=text, aufgabe=r["aufgabe_id"]))
    return aus


def _eingriffe(con, pid):
    """A2094: Paket früher/später – wer, was, warum; ein Handgriff, der endet, ohne erfüllt zu sein (ersetzt: der neue steht da)."""
    from . import paket_schieben
    zeilen = _neueste(con, "SELECT e.id, e.zeit_utc, e.von, e.art, e.text, e.aufgabe_id, e.bogen_id, b.nr FROM plan_ereignis e"
                           " JOIN bogen b ON b.id = e.bogen_id WHERE e.projekt_id = ? AND e.art IN (?, ?) ORDER BY e.id DESC",
                      (pid, paket_schieben.ART, paket_schieben.ENDE))
    titel = {r["id"]: r["titel"] for r in con.execute("SELECT id, titel FROM aufgabe WHERE projekt_id = ?", (pid,))} if zeilen else {}
    aus = []
    for r in zeilen:
        d, t = _json(r["text"]), titel.get(r["aufgabe_id"], "?")
        if r["art"] == paket_schieben.ART:
            frueher = d.get("richtung") == "frueher"
            nachbar = titel.get(d.get("nach") if frueher else d.get("vor"), "?")
            text = f"M{r['nr']}: „{t}“ {'früher, vor' if frueher else 'später, hinter'} „{nachbar}“" + (f" – {d['grund']}" if d.get("grund") else "")
            aus.append(_eintrag("schieben", r["id"], r["zeit_utc"], _rolle(r["von"]), r["von"], "schieben", "umsetzung", r["bogen_id"], None,
                                text=text, aufgabe=r["aufgabe_id"]))
        elif d.get("art") not in ("erfuellt", "ersetzt"):
            aus.append(_eintrag("schieben_ende", r["id"], r["zeit_utc"], _rolle(r["von"]), r["von"], "schieben_ende", "umsetzung", r["bogen_id"], None,
                                text=f"M{r['nr']}: Verschiebung von „{t}“ gilt nicht mehr – {d.get('grund') or '?'}", aufgabe=r["aufgabe_id"]))
    return aus


def _agenten(con, pid):
    """A2095: Agent herausgenommen oder wieder freigegeben – wer, warum, wie viele Pakete in den Pool gingen."""
    from . import herausnehmen
    nr = {str(r["id"]): r["nr"] for r in con.execute("SELECT id, nr FROM bogen WHERE projekt_id = ?", (pid,))}
    aus = []
    for r in _neueste(con, "SELECT id, zeit_utc, von, art, text FROM plan_ereignis WHERE projekt_id = ? AND art IN (?, ?) ORDER BY id DESC",
                      (pid, herausnehmen.HERAUS, herausnehmen.FREI)):
        d = _json(r["text"])
        grund = f" – {d['grund']}" if d.get("grund") else ""
        if r["art"] == herausnehmen.FREI:
            text = f"{d.get('agent', '?')} wieder freigegeben{grund}"
        else:
            n, je = len(d.get("pakete") or []), ", ".join(f"M{nr[b]}: {k}" for b, k in (d.get("je") or {}).items() if b in nr)
            text = f"{d.get('agent', '?')} herausgenommen{grund}" + (f"; {n} Paket{'e' if n != 1 else ''} in den Pool" + (f" ({je})" if je else "") if n else "")
        aus.append(_eintrag("agent", r["id"], r["zeit_utc"], _rolle(r["von"]), r["von"], r["art"], "umsetzung", None, None, text=text))
    return aus


def _pausen(con, pid):
    """A2137: Pause an und aus – wer, Grund, Ende in Ortszeit; von „AMW“ aufgehoben heißt: das Ende war erreicht."""
    from . import pause
    aus = []
    for r in _neueste(con, "SELECT id, zeit_utc, von, art, text FROM plan_ereignis WHERE projekt_id = ? AND art IN (?, ?) ORDER BY id DESC",
                      (pid, pause.AN, pause.AUS)):
        if r["art"] == pause.AUS:
            text = "Pause aufgehoben" + (" – Ende erreicht" if r["von"] == "AMW" else "")
        else:
            d = _json(r["text"])
            grund = " ".join((d.get("grund") or "").split())
            text = "Pause für alles" + (f" bis {_ortszeit(d['bis'], r['zeit_utc'])}" if d.get("bis") else "")
            text += f" – {grund}" if grund and grund != "Pause" else ""       # „Pause“ setzt pause.an, wenn keiner genannt ist
        aus.append(_eintrag("pause", r["id"], r["zeit_utc"], _rolle(r["von"]), r["von"], r["art"], "umsetzung", None, None, text=text))
    return aus


def _ortszeit(bis, seit):
    """HH:MM; liegt das Ende an einem anderen Tag als der Eintrag, mit Datum davor."""
    ende = db.utc_lesen(bis).astimezone()
    return ende.strftime("%H:%M" if ende.date() == db.utc_lesen(seit).astimezone().date() else "%d.%m. %H:%M")


DELTA = ("thema_delta_stimme","thema_delta_angewandt", "thema_delta_start")
_ROLLE = {"co": "Co-Entwickler", "lead": "Lead"}


def _delta(con, pid):
    aus = []
    for r in _neueste(con, "SELECT id, zeit_utc, von, art, text FROM plan_ereignis WHERE projekt_id = ? AND art IN (?, ?, ?)"
                           " ORDER BY id DESC", (pid, *DELTA)):
        d = _json(r["text"])
        th = f"TH{d.get('thema', '?')}"
        if r["art"] == "thema_delta_stimme":
            text = f"{th}: Ja zur Änderung" + (f" ({_ROLLE.get(d['rolle'], d['rolle'])})" if d.get("rolle") else "")
        elif r["art"] == "thema_delta_angewandt":
            n = len(d.get("uebersprungen") or [])
            text = f"{th}: Änderung angewandt" + (f", {n} Paket{'e' if n != 1 else ''} blieb{'en' if n != 1 else ''} unverändert" if n else "")
        else:
            text = f"{th}: Änderung " + ("nicht ganz gestartet" if d.get("fehler") or d.get("offen") else "gestartet")
        aus.append(_eintrag("delta", r["id"], r["zeit_utc"], _rolle(r["von"]), r["von"], r["art"], "fein", None, None, text=text))
    return aus


def _abschluss(con, pid):
    from . import abschluss, workbench
    nr = {r["id"]: r["nr"] for r in con.execute("SELECT id, nr FROM bogen WHERE projekt_id = ?", (pid,))}
    aus, t = [], None
    for r in _neueste(con, "SELECT id, zeit_utc, von, art, text, bogen_id FROM plan_ereignis WHERE projekt_id = ? AND (art IN ('abschluss_angestossen',"
                           " 'abschluss_ergebnis', 'bogen_bereit_abnahme') OR (art = 'abschluss_abnehmbar' AND text LIKE '%ausgeliefert_: true%')"
                           " OR (art = 'bogen_status' AND (text LIKE '%→ fertig' OR text LIKE '%→ aktiv')))"
                           " ORDER BY id DESC", (pid,)):
        m = f"M{nr.get(r['bogen_id'], '?')}"
        rolle, von, d = _rolle(r["von"]), r["von"], _json(r["text"])
        if r["art"] == "bogen_status":
            fertig = r["text"].endswith("fertig")
            aus.append(_eintrag("ms_fertig" if fertig else "ms_start", r["id"], r["zeit_utc"], rolle, von, "meilenstein", "abschluss" if fertig else "umsetzung",
                                r["bogen_id"], None, text=f"{m}: " + ("abgeschlossen" if fertig else "Meilenstein gestartet")))
        elif r["art"] == "abschluss_angestossen":
            aus.append(_eintrag("ab_angestossen", r["id"], r["zeit_utc"], "amw", "AMW", r["art"], "abschluss", r["bogen_id"], None, text=f"{m}: Prüfung gestartet"))
        elif r["art"] == "bogen_bereit_abnahme":
            aus.append(_eintrag("ab_bereit", r["id"], r["zeit_utc"], "amw", "AMW", r["art"], "abschluss", r["bogen_id"], None,
                                text=f"{m}: " + ("wartet auf Auslieferung" if ": wartet auf Auslieferung –" in (r["text"] or "") else "bereit zur Abnahme")))   # A2116
        elif r["art"] == "abschluss_abnehmbar":                          # A2116: nach der Auslieferung
            aus.append(_eintrag("ab_bereit", r["id"], r["zeit_utc"], "amw", "AMW", r["art"], "abschluss", r["bogen_id"], None, text=f"{m}: ausgeliefert, bereit zur Abnahme"))
        else:
            if d.get("fehler"):
                t = t or workbench.texte("de")
                text = f"{m}: Prüfung ging nicht – " + " · ".join(t["pjw_ax_" + g["art"]] for g in abschluss.deuten(d["fehler"]))
            elif d.get("angelegt"):
                n = len(d["angelegt"])
                text = f"{m}: Prüfung – {n} Paket{'e' if n != 1 else ''} Nacharbeit"
            else:
                text = f"{m}: Prüfung {abschluss.wort(d)}"
            aus.append(_eintrag("ab_ergebnis", r["id"], r["zeit_utc"], "pruefer", "Prüfer", r["art"], "abschluss", r["bogen_id"], None, text=text))
    return aus


# --- Zusammenführen ----------------------------------------------------------------------------------------------------------

def _titel_kurz(titel, grenze=TITEL_MAX):
    return titel[:grenze].rsplit(" ", 1)[0] + " …" if titel and len(titel) > grenze else titel


def _satz(art, ms, titel, zusatz, n):
    einer, viele = TEXTE[art]
    titel = _titel_kurz(titel)
    return (einer if n == 1 else viele).format(m=f"M{ms}" if ms is not None else "?", t=titel, x=zusatz, n=n)


def zusammenfassen(liste):
    """Aufeinanderfolgende gleiche Einträge eines Schritts zu einer Zeile; liste: zeitlich sortiert. Der Eintrag steht an der Stelle
    des letzten."""
    gruppen, offen = [], {}                                # Schritt → zuletzt begonnene Gruppe
    for e in liste:
        g = offen.get(e["schritt"])
        schluessel = (e["art"], e["von"], e["bogen_id"], e["zusatz"]) if e["art"] in TEXTE else None
        if g and schluessel and g["schluessel"] == schluessel and db.utc_sek(e["zeit"]) - db.utc_sek(g["teile"][-1]["zeit"]) <= BUENDEL_S:
            g["teile"].append(e)
            continue
        g = {"schluessel": schluessel, "teile": [e]}
        offen[e["schritt"]] = g
        gruppen.append(g)
    aus = []
    for g in gruppen:
        e = g["teile"][-1]
        je = list({x["aufgabe_id"] or x["titel"]: x for x in g["teile"]}.values())      # A2106: je Paket einmal (mehrere Prüfungen desselben Pakets)
        n = len(je)
        if g["schluessel"]:
            mehr = " · ".join(f"{(x['nummer'] + ' ') if x['nummer'] else ''}{x['titel']}" for x in je) if n > 1 else (
                " · ".join(x for x in (e["nummer"], e["titel"] if len(e["titel"] or "") > TITEL_MAX else None) if x) or None)
            e = {**e, "text": _satz(e["art"], e["ms"], e["titel"], e["zusatz"], n), "mehr": mehr}
        else:
            e = {**e, "mehr": e.get("mehr") or e["nummer"]}
        aus.append(e)
    return sorted(aus, key=lambda x: (x["zeit"], x["rang"]))


FELDER = ("id", "zeit", "rolle", "von", "text", "art", "aufgabe_id", "bogen_id", "schritt", "mehr", "fehler")


def gesamt(con, pid, weg, schritt_von, grenze=GRENZE):
    """Der ganze Verlauf: die Einträge aus verlauf.projektweg (`weg`, schon gebündelt) und die abgeleiteten, älteste zuerst, höchstens
    `grenze` je Schritt. schritt_von(eintrag) → Schritt eines Eintrags aus `weg`."""
    alle = [{**e, "schritt": schritt_von(e), "rang": (0, e["id"]), "zusatz": None, "nummer": None, "titel": None, "ms": None} for e in weg]
    for quelle in (_umsetzung, _auslieferung, _feinplan, _delta, _abschluss, _eingriffe, _pruefpunkte, _agenten, _pausen):
        alle += quelle(con, pid)
    alle.sort(key=lambda x: (x["zeit"], x["rang"]))
    je, aus = {}, zusammenfassen(alle)
    for e in reversed(aus):
        je.setdefault(e["schritt"], []).append(e)
    bleibt = {id(e) for liste in je.values() for e in liste[:grenze]}
    return [{k: e[k] for k in FELDER if e.get(k) is not None or k in ("aufgabe_id", "bogen_id")} for e in aus if id(e) in bleibt]
