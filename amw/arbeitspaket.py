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
PAKETTYPEN = ("normal", "test-schreiben")

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

# Spiegel auf aufgabe.status (die Oberfläche fasst zusammen: fertig / läuft / wartet / blockiert)
SPIEGEL = {"laeuft": "laeuft", "fertig": "fertig",
           **{z: "blockiert" for z in ("blockiert", "unklar", "wartet_interaktiv", "abgebrochen")}}

TEXT = {"entwurf": "Entwurf", "startklar": "startklar", "laeuft": "läuft", "abgegeben": "abgegeben", "abnahme": "in der Abnahme",
        "merge_reihe": "bereit zum Merge", "gemergt": "gemergt", "fertig": "fertig", "blockiert": "blockiert (Frage offen)",
        "unklar": "unklar (keine Schlusszeile)", "wartet_interaktiv": "wartet auf interaktiv", "abgebrochen": "abgebrochen",
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
