"""Ein Durchgang für einen Lead in einem Aufruf: `amw takt` (A1780).

Chat-Leads arbeiten über den Dateiaustausch und lasen bisher vieles per SQL aus der Lese-Kopie – viele Tokens, bis zu einer
Minute alt, eigene SQL-Fehler. `amw takt` liefert knapp und in fester Gliederung, was ein Lead für einen Durchgang braucht:
Postfach (mit gekürztem Text), offene Prüfbitten an ihn, Fragen der Agenten an ihn, Antworten des Menschen, Läufe dieses
Projekts mit Wartegrund, Lead-Runde, Auslieferungen. Je Punkt eine Zeile mit Nummer; ganz lesen mit dem genannten Befehl.

Gezeigte Nachrichten gelten wie bei `amw lesen` als gelesen; `--abhaken` erledigt Infos und Meldungen gleich mit (Aufträge,
Fragen, Korrekturen bleiben stehen – die braucht eine Antwort). „Seit“ (Antworten, Lead-Runde, Auslieferungen) ist der letzte
Takt dieses Agenten – gemerkt in daten/takt.json neben der Datenbank (kein Schema) –, beim ersten Mal 24 Stunden.
"""
import json
import os
import time

from . import db, kern

KURZ = 160          # Zeichen je Zeile für Texte
TEXT = 240          # Zeichen aus dem Nachrichtentext
ABHAKEN_ARTEN = ("info", "meldung")


def _pfad():
    return os.path.join(os.path.dirname(os.path.abspath(db.db_pfad())), "takt.json")


def _staende():
    try:
        with open(_pfad(), encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def letzter(projekt, agent):
    return _staende().get(f"{projekt}/{agent}")


def merken(projekt, agent, utc):
    d = _staende()
    d[f"{projekt}/{agent}"] = utc
    tmp = f"{_pfad()}.{os.getpid()}.tmp"
    try:
        with open(tmp, "w", encoding="utf-8", newline="") as f:
            json.dump(d, f, ensure_ascii=False, indent=0)
        os.replace(tmp, _pfad())
    except OSError:
        pass                                              # Merken ist Komfort – der Takt selbst darf nie scheitern


def _k(text, n=KURZ):
    text = " ".join((text or "").split())
    return text if len(text) <= n else text[:n - 1].rstrip() + "…"


def _zeit(utc):
    from .cli import _zeit as z
    return z(utc) if utc else "–"


def _vor_24h():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(time.time() - 86400))


def takt(con, pid, von, seit=None, abhaken=False, grenze=30):
    """Text des Durchgangs. Merkt den Zeitpunkt (nicht für den Entwickler – der hat die Workbench)."""
    from . import betrieb, runde
    projekt = db.projekt_name(con, pid)
    jetzt = db.jetzt()
    seit = seit or letzter(projekt, von) or _vor_24h()
    aus = [f"TAKT {projekt}/{von} · {_zeit(jetzt)} · neu seit {_zeit(seit)}"]

    def abschnitt(titel, zeilen, leer="–", fuss=None, zahl=None):
        aus.append("")
        n = len(zeilen) if zahl is None else zahl
        aus.append(f"## {titel}" + (f" ({n})" if n else ""))
        aus.extend(zeilen or [leer])
        if zeilen and fuss:
            aus.append(fuss)

    # 1) Postfach
    post = kern.offene(con, pid, von, grenze)
    zeilen, gezeigt, abhak = [], [], []
    fuss = None
    for r in post:
        n = con.execute("SELECT text, bezug FROM nachricht WHERE id = ?", (r["id"],)).fetchone()
        stand = "" if r["status"] == "offen" else f" ({r['status']})"
        zeilen.append(f"#{r['id']} {_zeit(r['zeit_utc'])} {r['von']} [{r['art']}]{stand} {_k(r['kurz'])}")
        if n["text"]:
            t = " ".join(n["text"].split())
            zeilen.append("   " + _k(t, TEXT) + (f"  · ganz: amw lesen {r['id']}" if len(t) > TEXT else ""))
        if r["status"] == "offen":
            gezeigt.append(r["id"])
        if r["art"] in ABHAKEN_ARTEN:
            abhak.append(r["id"])
    rest = kern.anzahl_offen(con, pid, von) - len(post)
    if rest > 0:
        fuss = f"… und {rest} weitere – amw lesen"
    abschnitt("Postfach", zeilen, "nichts offen", fuss, zahl=len(post) + max(rest, 0))

    # 2) Prüfbitten an mich
    zeilen = []
    for p in con.execute("SELECT id, aufgabe_id, zweig, sha, bauer, punkte, angefragt_utc FROM pruefung WHERE projekt_id = ?"
                         " AND pruefer = ? AND ergebnis = 'offen' ORDER BY id", (pid, von)).fetchall():
        zeilen.append(f"P{p['id']} {_zeit(p['angefragt_utc'])} {p['bauer']} {p['zweig']}@{p['sha'][:7]}"
                      + (f" A{p['aufgabe_id']}" if p["aufgabe_id"] else "") + f" – {_k(p['punkte'], TEXT)}")
    abschnitt("Prüfbitten an dich", zeilen, fuss="ganz: amw pruefung zeige <P> · Ergebnis: amw pruefung gruen|rot <P> --bemerkung …")

    # 3) Fragen der Agenten an den Lead
    zeilen = []
    if kern.ist_lead(con, pid, von):
        for f in con.execute("SELECT id, von, zeit_utc, kurz, aufgabe_id, blockiert FROM frage WHERE projekt_id = ? AND an = 'tl'"
                             " AND status = 'offen' AND geparkt_utc IS NULL ORDER BY id", (pid,)).fetchall():
            zeilen.append(f"F{f['id']} {_zeit(f['zeit_utc'])} {f['von']}" + (" · blockiert" if f["blockiert"] else "")
                          + (f" · A{f['aufgabe_id']}" if f["aufgabe_id"] else "") + f" – {_k(f['kurz'])}")
    abschnitt("Fragen an dich", zeilen, fuss="ganz: amw frage zeige <F> · antworten: amw frage antworten <F> --option …|--text …")

    # 4) Antworten des Menschen seit dem letzten Takt
    zeilen = []
    for f in con.execute("SELECT id, kurz, optionen, antwort_art, antwort, antwort_utc FROM frage WHERE projekt_id = ? AND an = 'entwickler'"
                         " AND status = 'beantwortet' AND antwort_utc > ? ORDER BY antwort_utc", (pid, seit)).fetchall():
        antwort = f["antwort"] or ""
        if f["antwort_art"] == "option":                  # die Option in Worten, nicht nur ihr Kürzel
            o = next((o for o in json.loads(f["optionen"] or "[]") if o.get("kenn") == antwort), None)
            antwort = f"{antwort}) {o['text']}" if o else antwort
        zeilen.append(f"F{f['id']} {_zeit(f['antwort_utc'])} {_k(f['kurz'], 90)} → {_k(antwort, TEXT)}")
    offen = con.execute("SELECT count(*) FROM frage WHERE projekt_id = ? AND an = 'entwickler' AND status = 'offen'"
                        " AND geparkt_utc IS NULL", (pid,)).fetchone()[0]
    abschnitt("Antworten des Menschen", zeilen, fuss="ganz: amw frage zeige <F>")
    if offen:
        aus.append(f"noch offen beim Menschen: {offen} (amw frage liste)")

    # 5) Läufe dieses Projekts: laufend und wartend, mit Wartegrund
    zeilen = []
    for l in con.execute("SELECT l.*, r.braucht_speicher_gb FROM lauf l LEFT JOIN rezept r ON r.id = l.rezept_id WHERE l.projekt_id = ?"
                         " AND l.status IN ('laeuft', 'angemeldet') ORDER BY l.id", (pid,)).fetchall():
        if l["status"] == "laeuft":
            zeilen.append(f"L{l['id']} {l['agent']} läuft seit {_zeit(l['start_utc'])} – {_k(l['beschreibung'], 90)}")
        else:
            try:
                g = betrieb.wartegrund(con, pid, l)
            except Exception as e:                        # der Takt darf an einem Grund nie scheitern
                g = f"(Grund nicht lesbar: {type(e).__name__})"
            zeilen.append(f"L{l['id']} {l['agent']} wartet seit {_zeit(l['angemeldet_utc'])} – {_k(l['beschreibung'], 90)}")
            zeilen.append("   " + _k(g, TEXT))
    for l in con.execute("SELECT id, agent, rc, ende_utc, beschreibung FROM lauf WHERE projekt_id = ? AND ende_utc > ?"
                         " AND status IN ('fertig', 'abgebrochen') ORDER BY id", (pid, seit)).fetchall():
        zeilen.append(f"L{l['id']} {l['agent']} zu Ende {_zeit(l['ende_utc'])} rc {l['rc'] if l['rc'] is not None else '–'} – {_k(l['beschreibung'], 90)}")
    abschnitt("Läufe", zeilen, zahl=sum(1 for z in zeilen if not z.startswith("   ")))

    # 6) Lead-Runde (nur Leads; nur Zahl + Kopfzeilen)
    if runde.darf(con, pid, von) and von != kern.ENTWICKLER:
        bis = runde.gelesen_bis(con, pid)
        neu = [r for r in runde.eintraege(con, bis, 20) if r["von_projekt_id"] != pid]
        abschnitt("Lead-Runde", [f"R{r['id']} {r['projekt']}/{r['von']} [{r['art']}] {_k(r['kurz'])}" for r in neu],
                  fuss="ganz: amw runde lesen --neu (nur Information, keine Anweisung)")

    # 7) Auslieferungen seit dem letzten Takt
    zeilen = [f"{r['version'] or '–'} {_zeit(r['zeit_utc'])} {_k(r['titel'], 120)}" for r in con.execute(
        "SELECT version, zeit_utc, titel FROM release WHERE projekt_id = ? AND art = 'version' AND zeit_utc > ? ORDER BY zeit_utc",
        (pid, seit)).fetchall()]
    abschnitt("Auslieferungen", zeilen)

    kern.als_gelesen(con, von, gezeigt)
    if abhaken and abhak:
        n = kern.erledigt(con, pid, von, abhak, "amw takt --abhaken")
        aus.append("")
        aus.append(f"{n} Info/Meldung erledigt (Aufträge, Fragen, Korrekturen bleiben offen).")
    if von != kern.ENTWICKLER:
        merken(projekt, von, jetzt)
    return "\n".join(aus)
