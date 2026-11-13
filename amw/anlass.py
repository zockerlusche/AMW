"""Verbrauch nach Anlass (A1642, Pareto): Wofür geben die Agenten ihr Geld aus? Nur rechnen und zeigen – nichts steuern.

Grundlage wie in aufwand.py: der Kosten-Zähler je Sitzung (`verbrauch`, alle paar Minuten). Jeder Zuwachs zwischen zwei
Messpunkten gehört zu den Weckrufen, die der Agent in diesem Zeitraum bekommen hat (mehrere: zu gleichen Teilen) – ohne
Weckruf ist es „eigene Arbeit“ (er arbeitet von sich aus an seiner Aufgabe weiter). Ein Weckruf ist ein Empfang mit
geweckt_utc. Seine Art ergibt sich aus Absender, Nachrichten-Art und Text. Vermeidbar heißt: der Agent musste nichts tun
(„ist dran“ bei einem Lauf, der von selbst startet, Leerlauf-Hinweis, reine Zustandsmeldung). Kein KI-Aufruf, kein Schema.
"""
import datetime

# (Erkennung im Text bei Absender AMW, Kennung, Anlass, vermeidbar) – die Kennung übersetzt die Seite (anl_<kennung>)
AMW_ARTEN = (("ist dran", "lauf_dran", "Lauf ist dran", True),
             ("vom Dienst gerechnet", "lauf_dienst", "Lauf fertig (Dienst)", False),
             ("zu Ende", "lauf_ende", "Lauf zu Ende → weiter", False),
             ("Leerlauf", "leerlauf", "Leerlauf-Hinweis", True),
             ("hat geschrieben", "antwort_weiter", "Antwort → weiter", False),
             ("weiter in deiner Liste", "aufgabe_naechste", "Aufgabe fertig → nächste", False),
             ("läuft seit", "lauf_lang", "Lauf läuft länger", True),
             ("Kontext zu", "kontext", "Kontext fast voll", False),
             ("Grenze zu", "grenze", "Nutzungsgrenze", False),
             ("wartet seit", "vorrang_wartet", "Vorrang wartet", True))
ARTEN = {"pruefbitte": "Prüfbitte", "auftrag": "Auftrag", "frage": "Frage", "antwort": "Antwort", "info": "Info",
         "freigabe": "Freigabe", "stopp": "Halt", "korrektur": "Korrektur", "meldung": "Meldung"}
EIGENE = "eigene Arbeit (ohne Weckruf)"


def art(von, nart, kurz):
    """(Anlass, vermeidbar) eines Weckrufs."""
    return art_mit_kennung(von, nart, kurz)[1:]


def art_mit_kennung(von, nart, kurz):
    """(Kennung, Anlass, vermeidbar) eines Weckrufs."""
    kurz = kurz or ""
    if von == "AMW":
        for muster, kennung, name, vermeidbar in AMW_ARTEN:
            if muster in kurz:
                return kennung, name, vermeidbar
        return f"amw_{nart}", "AMW: " + ARTEN.get(nart, nart), False
    if nart == "meldung" and ("GRUEN" in kurz or "ROT" in kurz):
        return "pruefergebnis", "Prüfergebnis", False
    if von == "Entwickler":
        return f"mensch_{nart}", "vom Menschen: " + ARTEN.get(nart, nart), False
    return nart, ARTEN.get(nart, nart), False


def _weckrufe(con, pid, kennung, ab):
    return con.execute("SELECT e.geweckt_utc AS t, n.von, n.art, n.kurz FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
                       " WHERE n.projekt_id = ? AND e.agent = ? AND e.geweckt_utc >= ? ORDER BY e.geweckt_utc",
                       (pid, kennung, ab)).fetchall()


def anlaesse(con, pid, ab, bis=None):
    """{"zeilen": [{"anlass", "usd", "weckrufe", "je_weckruf", "vermeidbar", "anteil", "kumuliert"}], "gesamt", "vermeidbar_usd",
    "weckrufe", "vermeidbar_weckrufe"} – nach Kosten absteigend (Pareto). ab/bis: UTC-Texte."""
    bis = bis or "9999"
    summe, zahl, vermeidbar, kennungen = {}, {}, {}, {EIGENE: "eigene"}
    weck_gesamt = weck_verm = 0
    for (kennung,) in con.execute("SELECT kennung FROM agent WHERE projekt_id = ?", (pid,)).fetchall():
        weckrufe = [w for w in _weckrufe(con, pid, kennung, ab) if w["t"] < bis]
        for w in weckrufe:
            k, a, v = art_mit_kennung(w["von"], w["art"], w["kurz"])
            kennungen[a] = k
            zahl[a] = zahl.get(a, 0) + 1
            vermeidbar[a] = v
            weck_gesamt += 1
            weck_verm += int(v)
        zeilen = con.execute(
            "SELECT v.sitzung_id, v.zeit_utc, v.kosten_usd FROM verbrauch v JOIN sitzung s ON s.id = v.sitzung_id"
            " JOIN agent g ON g.id = s.agent_id AND g.projekt_id = ? AND g.kennung = ?"
            " WHERE v.agent = ? AND v.kosten_usd IS NOT NULL AND v.zeit_utc >= ? AND v.zeit_utc < ? ORDER BY v.sitzung_id, v.zeit_utc",
            (pid, kennung, kennung, ab, bis)).fetchall()
        vorher = {}
        for z in zeilen:
            alt = vorher.get(z["sitzung_id"])
            vorher[z["sitzung_id"]] = (z["kosten_usd"], z["zeit_utc"])
            if alt is None:
                continue
            zuwachs = z["kosten_usd"] if z["kosten_usd"] < alt[0] else z["kosten_usd"] - alt[0]
            if zuwachs <= 0:
                continue
            drin = [w for w in weckrufe if alt[1] < w["t"] <= z["zeit_utc"]]
            if not drin:
                summe[EIGENE] = summe.get(EIGENE, 0.0) + zuwachs
                vermeidbar.setdefault(EIGENE, False)
                continue
            for w in drin:
                a, v = art(w["von"], w["art"], w["kurz"])
                summe[a] = summe.get(a, 0.0) + zuwachs / len(drin)
    gesamt = sum(summe.values())
    aus, kum = [], 0.0
    for a in sorted(set(summe) | set(zahl), key=lambda x: -summe.get(x, 0.0)):
        usd = summe.get(a, 0.0)
        kum += usd
        n = zahl.get(a, 0)
        aus.append({"kennung": kennungen.get(a, ""), "anlass": a, "usd": round(usd, 2), "weckrufe": n, "je_weckruf": round(usd / n, 2) if n else None,
                    "vermeidbar": bool(vermeidbar.get(a)), "anteil": round(100 * usd / gesamt, 1) if gesamt else 0.0,
                    "kumuliert": round(100 * kum / gesamt, 1) if gesamt else 0.0})
    return {"zeilen": aus, "gesamt": round(gesamt, 2), "vermeidbar_usd": round(sum(r["usd"] for r in aus if r["vermeidbar"]), 2),
            "weckrufe": weck_gesamt, "vermeidbar_weckrufe": weck_verm}


def zeitraum(tage):
    """UTC-Beginn für die letzten `tage` Tage ab lokaler Mitternacht."""
    tag = datetime.date.today() - datetime.timedelta(days=max(1, tage) - 1)
    return datetime.datetime.combine(tag, datetime.time.min).astimezone(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
