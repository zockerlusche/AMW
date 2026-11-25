"""Arbeitspakete für den Mischbetrieb (AMW 2.0 Stufe 1, A1845, Konzept D1258 v4 §3/§4).

Jede Aufgabe ist ein Paket. Die Art sagt, wer es ausführt: `agent` (ein vorhandener interaktiver Agent – wie bisher),
`sitzung` (neue Sitzung; in Stufe 1 nur ein Feldwert) oder `p` (ein frischer `claude -p`-Arbeiter, den die AMW startet).
Dieses Modul ist die EINE Stelle für
- die Paketfelder mit ihren Standardwerten und erlaubten Werten (§3),
- den Zustandsautomaten – nur für Art `p` (§4; Art `agent` behält die heutigen Status der Aufgabe, D1270 Nr. 21/38),
- die Spiegelung eines p-Zustands auf den Status der Aufgabe, damit Planung, Karte, „eins nach dem anderen“ und die
  Oberfläche (fertig / läuft / wartet / blockiert) unverändert funktionieren.
Abnahme-Befehl, Bereiche, Rang und „nach X“ gibt es schon an der Aufgabe (pruefbefehl, dateibereich, rang, abhaengigkeit).
"""
ARTEN = ("agent", "sitzung", "p")
GEWICHTE = ("leicht", "schwer")
RESSOURCEN = ("gpu", "bildschirm")
EFFORTS = ("low", "medium", "high")
PAKETTYPEN = ("normal", "test-schreiben", "test-ergaenzen")   # A1895: test-ergaenzen = nur Tests für bestehenden Code

STANDARD = {"art": "agent", "gewicht": "leicht", "ressourcen": [], "modell": "claude-opus-5-5", "effort": "high",
            "pakettyp": "normal", "nie_gleichzeitig": [], "gleiche_ressource": None}

# Zustände eines p-Pakets: Hauptweg und Nebenzustände (§4, §7)
HAUPTWEG = ("entwurf", "startklar", "laeuft", "abgegeben", "abnahme", "merge_reihe", "gemergt", "fertig")
NEBEN = ("blockiert", "unklar", "wartet_interaktiv", "abgebrochen", "zurueckgestellt")
ZUSTAENDE = HAUPTWEG + NEBEN
START = "entwurf"

# Erlaubte Übergänge – alles andere ist ein Fehler. Rückwege nur, wo das Konzept sie vorsieht:
# Abnahme rot → einmal zurück an den Arbeiter (laeuft), Merge-Konflikt → zurück (laeuft), sonst wartet auf interaktiv (§7).
UEBERGAENGE = {
    "entwurf": {"startklar", "zurueckgestellt"},
    "startklar": {"laeuft", "entwurf", "zurueckgestellt"},
    "laeuft": {"abgegeben", "blockiert", "unklar", "abgebrochen"},
    "abgegeben": {"abnahme", "unklar"},
    "abnahme": {"merge_reihe", "laeuft", "wartet_interaktiv"},
    "merge_reihe": {"gemergt", "laeuft", "wartet_interaktiv"},
    "gemergt": {"fertig"},
    "fertig": set(),
    "blockiert": {"wartet_interaktiv", "startklar", "zurueckgestellt"},
    "unklar": {"wartet_interaktiv", "startklar", "zurueckgestellt"},
    "abgebrochen": {"wartet_interaktiv", "startklar", "zurueckgestellt"},
    "wartet_interaktiv": {"startklar", "zurueckgestellt"},
    "zurueckgestellt": {"entwurf", "startklar"},
}

# A1894: der Lead nimmt ein Paket nach E4 an (mergeliste.annehmen) – der einzige Weg von wartet_interaktiv in die Merge-Reihe
LEAD_ANNAHME = ("wartet_interaktiv", "merge_reihe")

# Spiegel auf aufgabe.status (die Oberfläche fasst zusammen: fertig / läuft / wartet / blockiert)
SPIEGEL = {"laeuft": "laeuft", "fertig": "fertig",
           **{z: "blockiert" for z in ("blockiert", "unklar", "wartet_interaktiv", "abgebrochen")}}

TEXT = {"entwurf": "Entwurf", "startklar": "startklar", "laeuft": "läuft", "abgegeben": "abgegeben", "abnahme": "in der Abnahme",
        "merge_reihe": "bereit zum Merge", "gemergt": "gemergt", "fertig": "fertig", "blockiert": "blockiert (Frage offen)",
        "unklar": "unklar (keine Schlusszeile)", "wartet_interaktiv": "wartet auf Lead", "abgebrochen": "abgebrochen",
        "zurueckgestellt": "zurückgestellt"}


class Ungueltig(ValueError):
    pass


def _liste(x):
    if x is None or x == "":
        return []
    if isinstance(x, str):
        return [t.strip() for t in x.replace(";", ",").split(",") if t.strip()]
    return list(x)


def felder_pruefen(werte):
    """Neue Werte (Teilmenge) prüfen und vereinheitlichen; Rückgabe: dict nur mit den übergebenen Feldern.
    nie_gleichzeitig: Aufgaben-Nummern (A12 oder 12) → [12]; ressourcen: gpu,bildschirm → Liste."""
    aus = {}
    for k, v in werte.items():
        if k not in STANDARD:
            raise Ungueltig(f"unbekanntes Paketfeld „{k}“")
        if k == "art" and v not in ARTEN:
            raise Ungueltig(f"Art: {' | '.join(ARTEN)}")
        elif k == "gewicht" and v not in GEWICHTE:
            raise Ungueltig(f"Gewicht: {' | '.join(GEWICHTE)}")
        elif k == "effort" and v not in EFFORTS:
            raise Ungueltig(f"Effort: {' | '.join(EFFORTS)}")
        elif k == "pakettyp" and v not in PAKETTYPEN:
            raise Ungueltig(f"Pakettyp: {' | '.join(PAKETTYPEN)}")
        elif k == "ressourcen":
            v = [r.lower() for r in _liste(v)]
            falsch = [r for r in v if r not in RESSOURCEN]
            if falsch:
                raise Ungueltig(f"Ressourcen: {', '.join(RESSOURCEN)} (nicht: {', '.join(falsch)})")
            v = sorted(set(v))
        elif k == "nie_gleichzeitig":
            nrn = []
            for t in _liste(v):
                s = str(t).strip().lstrip("Aa")
                if not s.isdigit():
                    raise Ungueltig(f"nie gleichzeitig: Aufgaben-Nummern (A12 oder 12), nicht „{t}“")
                nrn.append(int(s))
            v = sorted(set(nrn))
        elif k == "modell":
            v = (v or "").strip() or None
            if v is None:
                raise Ungueltig("Modell: leer geht nicht (weglassen = Standard)")
            if "@" in v:                                   # A1931: anbieter@modell
                from . import anbieter
                a, m = anbieter.zerlegen(v)
                if not anbieter.NAME.fullmatch(a) or not m:
                    raise Ungueltig("Modell eines Anbieters: anbieter@modell, z. B. minimax@MiniMax-M2")
                v = f"{a}@{m}"
        elif k == "gleiche_ressource":
            v = (v or "").strip() or None
        aus[k] = v
    return aus


def mit_standard(gespeichert):
    """Gespeicherte Felder (oder None = keine Zeile) + Standardwerte; dazu „standard“: welche Felder nur Standard sind.
    Zustand: bei Art p der gespeicherte (sonst Entwurf), bei anderen Arten None."""
    g = dict(gespeichert or {})
    aus = {k: (g[k] if g.get(k) not in (None, "") else v) for k, v in STANDARD.items()}
    aus["ressourcen"] = list(aus["ressourcen"] or [])
    aus["nie_gleichzeitig"] = list(aus["nie_gleichzeitig"] or [])
    aus["standard"] = sorted(k for k in STANDARD if g.get(k) in (None, "", []))
    aus["zustand"] = (g.get("zustand") or START) if aus["art"] == "p" else None
    from .anbieter import zerlegen                      # A1931: abgeleitet aus dem Modell, kein eigenes Feld in der Tabelle
    aus["anbieter"] = zerlegen(aus["modell"])[0]
    return aus


def uebergang_pruefen(alt, neu):
    """Wirft Ungueltig, wenn alt → neu nicht erlaubt ist."""
    if neu not in ZUSTAENDE:
        raise Ungueltig(f"unbekannter Zustand „{neu}“ – möglich: {', '.join(ZUSTAENDE)}")
    if alt == neu:
        raise Ungueltig(f"steht schon auf „{TEXT[neu]}“")
    if neu not in UEBERGAENGE.get(alt, set()):
        weiter = ", ".join(z for z in ZUSTAENDE if z in UEBERGAENGE.get(alt, set())) or "keiner (Endzustand)"
        raise Ungueltig(f"„{TEXT.get(alt, alt)}“ → „{TEXT[neu]}“ geht nicht – möglich: {weiter}")


def spiegel(zustand):
    """Status der Aufgabe zu einem p-Zustand."""
    return SPIEGEL.get(zustand, "wartet")


def art_wechsel_pruefen(alt_art, neu_art, zustand):
    """Art ändern: von p weg nur, solange kein Arbeiter daran ist (nicht laeuft/abgegeben/abnahme/merge_reihe)."""
    if alt_art == "p" and neu_art != "p" and zustand in ("laeuft", "abgegeben", "abnahme", "merge_reihe"):
        raise Ungueltig(f"Art p → {neu_art} geht nicht, solange das Paket „{TEXT[zustand]}“ ist")


def warnungen(felder, pruefbefehl, dateibereich):
    """Hinweise beim Anlegen/Ändern (die harte Startregel 1 prüft der Wächter in S3)."""
    w = []
    if felder["art"] == "p":
        if not (pruefbefehl or "").strip():
            w.append("Art p ohne Abnahme-Befehl (--pruefbefehl) – die AMW startet es so nicht (Regel 1)")
        if not (dateibereich or "").strip():
            w.append("Art p ohne Bereiche (--dateien) – die AMW startet es so nicht (Regel 1)")
        if felder["gewicht"] == "schwer" or felder["ressourcen"]:
            w.append("Art p mit Gewicht schwer oder Ressourcen – in Stufe 1 startet die AMW es nicht (Regel 3)")
    return w


# --- Speicher ------------------------------------------------------------------------------------------------------
# Tabelle `paket` (Schema 33, amw/migration_33.sql): 1:1 zur Aufgabe, keine Zeile = Art agent mit Standardwerten.
JSON_FELDER = ("ressourcen", "nie_gleichzeitig")
PLANER_FEHLT = "Paketfelder setzt der Lead (oder der Mensch) – er plant, wer was ausführt"


def _alle(con):
    """A2145: alle Paketzeilen {aufgabe_id: Zeile} – in einer Anfrage oder Runde (einmal.merken) einmal gelesen statt je Paket. None
    außerhalb davon und in einer Schreib-Transaktion: dann einzeln wie bisher; jede Änderung macht den Merker leer."""
    from . import einmal
    if getattr(con, "merker", None) is None or (con.in_transaction and not getattr(con, "schnappschuss", False)):
        return None
    return einmal.einmal(con, ("paket",), lambda: {r["aufgabe_id"]: r for r in con.execute("SELECT * FROM paket")})


def _zeile(con, aid):
    import json
    k = _alle(con)
    if k is not None and isinstance(aid, int):            # eine Nummer als Text o. Ä. vergleicht SQLite anders: dann einzeln
        r = k.get(aid)
    else:
        r = con.execute("SELECT * FROM paket WHERE aufgabe_id = ?", (aid,)).fetchone()
    if not r:
        return None
    d = dict(r)
    for k in JSON_FELDER:
        d[k] = json.loads(d[k]) if d.get(k) else []
    return d


def lesen(con, aid):
    """Alle Paketfelder einer Aufgabe mit Standardwerten (Art agent, wenn nichts gespeichert ist)."""
    z = _zeile(con, aid)
    f = mit_standard(z)
    f["zustand_utc"] = (z or {}).get("zustand_utc") if f["zustand"] else None
    return f


def _aufgabe(con, pid, aid):
    from . import kern
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a:
        raise kern.AmwFehler(f"A{aid} gibt es nicht")
    return a


def _log(con, pid, von, aid, alt, neu, grund=None):
    from . import db
    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="paket_zustand",
                 text=f"{alt or '–'} → {neu or '–'}" + (f": {grund}" if grund else ""), aufgabe_id=aid)


def setzen(con, pid, von, aid, **werte):
    """Paketfelder setzen (nur die übergebenen, None = nicht angegeben). Lead oder Mensch. Wird eine Aufgabe zu Art p, beginnt
    sie als Entwurf; wird sie wieder agent/sitzung, endet der Automat (Zustand leer) – beides im Planungs-Protokoll.
    Rückgabe: (Felder nach lesen(), Warnungen)."""
    import json
    from . import db, kern
    if not (von in (kern.ENTWICKLER, "AMW") or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler(PLANER_FEHLT)
    a = _aufgabe(con, pid, aid)
    try:
        neu = felder_pruefen({k: v for k, v in werte.items() if v is not None})
    except Ungueltig as e:
        raise kern.AmwFehler(str(e)) from None
    for n in neu.get("nie_gleichzeitig", []):
        if n == aid or not con.execute("SELECT 1 FROM aufgabe WHERE id = ? AND projekt_id = ?", (n, pid)).fetchone():
            raise kern.AmwFehler(f"nie gleichzeitig: A{n} " + ("ist diese Aufgabe selbst" if n == aid else "gibt es nicht"))
    vorher = lesen(con, aid)
    if "art" in neu:
        try:
            art_wechsel_pruefen(vorher["art"], neu["art"], vorher["zustand"])
        except Ungueltig as e:
            raise kern.AmwFehler(str(e)) from None
    if neu:
        spalten = {k: (json.dumps(v) if k in JSON_FELDER else v) for k, v in neu.items()}
        jetzt = db.jetzt()
        with db.schreiben(con):
            if con.execute("SELECT 1 FROM paket WHERE aufgabe_id = ?", (aid,)).fetchone():
                con.execute(f"UPDATE paket SET {', '.join(k + ' = ?' for k in spalten)}, geaendert_utc = ? WHERE aufgabe_id = ?",
                            (*spalten.values(), jetzt, aid))       # Spaltennamen nur aus STANDARD (felder_pruefen)
            else:
                db.einfuegen(con, "paket", aufgabe_id=aid, geaendert_utc=jetzt, **spalten)
            art = neu.get("art", vorher["art"])
            if art == "p" and vorher["art"] != "p":
                con.execute("UPDATE paket SET zustand = ?, zustand_utc = ? WHERE aufgabe_id = ?", (START, jetzt, aid))
                _log(con, pid, von, aid, None, START, "Art p")
            elif art != "p" and vorher["art"] == "p":
                con.execute("UPDATE paket SET zustand = NULL, zustand_utc = NULL WHERE aufgabe_id = ?", (aid,))
                _log(con, pid, von, aid, vorher["zustand"], None, f"Art {art}")
    f = lesen(con, aid)
    return f, warnungen(f, a["pruefbefehl"], a["dateibereich"])


def zustand_setzen(con, pid, von, aid, neu, grund=None, beleg=None, annahme=False):
    """Zustand eines p-Pakets wechseln – nur erlaubte Übergänge; spiegelt den Status der Aufgabe (eine Stelle) und schreibt
    plan_ereignis „paket_zustand“ (Grundlage der Messung). Wer: die AMW selbst, der Lead oder der Mensch. „fertig“ braucht
    einen Beleg (Commit). Rückgabe: (alt, neu, Status der Aufgabe)."""
    from . import db, kern
    if not (von in (kern.ENTWICKLER, "AMW") or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler("Den Zustand eines p-Pakets setzt die AMW (oder Lead/Mensch von Hand)")
    a = _aufgabe(con, pid, aid)
    f = lesen(con, aid)
    if f["art"] != "p":
        raise kern.AmwFehler(f"A{aid} ist Art {f['art']} – Zustände gibt es nur bei Art p; sonst gilt der Status der Aufgabe")
    if not (annahme and (f["zustand"], neu) == LEAD_ANNAHME):    # A1894: wartet_interaktiv → merge_reihe nur über „annehmen“
        try:
            uebergang_pruefen(f["zustand"], neu)
        except Ungueltig as e:
            raise kern.AmwFehler(f"A{aid}: {e}") from None
    status = spiegel(neu)
    if status == "fertig" and not (beleg or a["beleg"] or "").strip():
        raise kern.AmwFehler(f"A{aid} fertig nur mit Beleg (Commit) – --beleg …")
    jetzt = db.jetzt()
    with db.schreiben(con):
        if not con.execute("SELECT 1 FROM paket WHERE aufgabe_id = ?", (aid,)).fetchone():
            db.einfuegen(con, "paket", aufgabe_id=aid, art="p", geaendert_utc=jetzt)
        con.execute("UPDATE paket SET zustand = ?, zustand_utc = ?, geaendert_utc = ? WHERE aufgabe_id = ?", (neu, jetzt, jetzt, aid))
        felder = {"status": status, "geaendert_utc": jetzt}
        if beleg:
            felder["beleg"] = beleg.strip()
        if status == "laeuft" and not a["begonnen_utc"]:
            felder["begonnen_utc"] = jetzt
        if status == "fertig":
            felder["fertig_utc"] = jetzt
        con.execute(f"UPDATE aufgabe SET {', '.join(k + ' = ?' for k in felder)} WHERE id = ?", (*felder.values(), aid))
        _log(con, pid, von, aid, f["zustand"], neu, grund)
    return f["zustand"], neu, status


def verlauf(con, aid):
    """[(zeit_utc, alt, neu, grund)] der Zustandswechsel (für Messung und Anzeige), älteste zuerst."""
    aus = []
    for r in con.execute("SELECT zeit_utc, text FROM plan_ereignis WHERE aufgabe_id = ? AND art = 'paket_zustand' ORDER BY id", (aid,)):
        teil, _, grund = r["text"].partition(": ")
        alt, _, neu = teil.partition(" → ")
        aus.append((r["zeit_utc"], None if alt == "–" else alt, None if neu == "–" else neu, grund or None))
    return aus


def zeitpunkte(con, aid):
    """Für die Messung (A1844, D1258 v4 §8): erstes Erreichen von startklar, laeuft, abgegeben, gemergt (UTC-Text oder None)
    eines p-Pakets – None, wenn die Aufgabe nicht Art p ist (dann gilt die Näherung der Messung)."""
    if lesen(con, aid)["art"] != "p":
        return None
    aus = {"startklar": None, "laeuft": None, "abgegeben": None, "gemergt": None}
    for zeit, _, neu, _ in verlauf(con, aid):
        if neu in aus and aus[neu] is None:
            aus[neu] = zeit
    return aus
