"""Prüfung C für Fenster-Pakete (A2054, TH167 Fassung 4): dieselbe Prüfung wie bei p-Paketen, auf genau dem Kopf des Zweigs.

Ablauf: `amw paket ergebnis` (erledigt, mit Abnahme-Befehl) bzw. `amw paket fertig` meldet die Prüfung an (anmelden). Der leichte
Teil (Diff-Tor, Geheimnis, nach außen) läuft dort sofort; trifft er, geht wie bisher eine Prüfbitte an den Lead. Sonst rechnet
der Dienst (runde) im eigenen Faden über die Lauf-Schlange: frischer Checkout genau des Kopfs, Abnahme, Testproben, Kurzsuite des
Projekts, Sprachprüfung. Dann entscheidet die Tabelle wie bei p (entscheiden):
- grün und nichts Riskantes (riskant.einordnen) → E7: die AMW legt eine Prüfung „grün“ mit Prüfer AMW an, mit Beleg (Lauf der
  Prüfung C, Abnahme, Kurzsuite, Sprachprüfung, Riskant-Einordnung mit Version). Merge-OK bleibt beim Lead (Lead F5389).
- grün, aber riskant → Prüfbitte an den Lead mit den getroffenen Regeln; bei g12 zusätzlich eine Info an den Menschen.
- C/rot das erste Mal → E5: Meldung an den Agenten mit der Ausgabe, er bessert nach und meldet neu; danach rot → E6 an den Lead.
- C/leer, C/diff, C/aussen → E4, C/technik → E1: Prüfbitte an den Lead mit dem Befund.
Die Aufgabe wartet dabei auf „pruefung:C-A<nr>“ (gibt den Agenten frei, A2053); das Ergebnis schließt den Grund.
Ereignisse (plan_ereignis): fenster_pruefung {"zweig", "kopf", "von"} · fenster_pruefung_ergebnis {"ereignis", "zeile", "code",
"riskant", "pruefung", "lauf"}.
"""
import datetime
import json
import os
import socket
import subprocess
import threading

from . import db, kern

ANGEMELDET, ERGEBNIS = "fenster_pruefung", "fenster_pruefung_ergebnis"
_laufend = set()
_sperre = threading.Lock()


def grund_bezug(aid):
    from . import wartegrund
    return wartegrund.stichwort("wartet_pruefung", f"C-A{aid}")


def warten_auf(con, pid, von, aid):
    """Wartegrund „pruefung:C-A<nr>“ eintragen (innerhalb eines Schreibvorgangs) – die Sorte wartet_pruefung gibt den Agenten frei."""
    from . import wartegrund
    art, bezug = grund_bezug(aid)
    if not any(g["bezug"] == bezug for g in wartegrund.offene(con, aid)):
        db.einfuegen(con, "wartegrund", projekt_id=pid, aufgabe_id=aid, art=art, bezug=bezug, angelegt_utc=db.jetzt(), angelegt_von=von)


def _kopf(quelle, zweig):
    r = subprocess.run(["git", "-C", quelle, "rev-parse", "--verify", f"refs/heads/{zweig}^{{commit}}"], capture_output=True, text=True,
                       stdin=subprocess.DEVNULL, timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if r.returncode:
        raise kern.AmwFehler(f"Zweig {zweig} gibt es im Projekt nicht")
    return r.stdout.strip()


def anmelden(con, pid, aid, zweig, von):
    """Prüfung C für diesen Zweig anmelden (der Dienst rechnet sie). Rückgabe: Nummer des Ereignisses."""
    quelle = kern.projekt_ordner(con, pid)
    if not quelle:
        raise kern.AmwFehler("Das Projekt hat keinen Ordner (amw projekt ordner …) – die AMW kann den Zweig nicht prüfen")
    kopf = _kopf(quelle, zweig)
    with db.schreiben(con):
        return db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ANGEMELDET, aufgabe_id=aid,
                            text=json.dumps({"zweig": zweig, "kopf": kopf, "von": von}, ensure_ascii=False))


def offen(con):
    """Angemeldete Prüfungen ohne Ergebnis: [Zeile plan_ereignis]."""
    fertig = set()
    for (t,) in con.execute("SELECT text FROM plan_ereignis WHERE art = ?", (ERGEBNIS,)):
        try:
            fertig.add(json.loads(t or "{}").get("ereignis"))
        except ValueError:
            pass
    return [r for r in con.execute("SELECT * FROM plan_ereignis WHERE art = ? ORDER BY id", (ANGEMELDET,)).fetchall() if r["id"] not in fertig]


def runde(con, starten=None):
    """Dienst: jede offene Prüfung in einem eigenen Faden rechnen (einmal je Ereignis). Rückgabe: Texte."""
    starten = starten or (lambda ziel, *a: threading.Thread(target=ziel, args=a, daemon=True, name="fensterpruefung").start())
    aus = []
    for e in offen(con):
        with _sperre:
            if e["id"] in _laufend:
                continue
            _laufend.add(e["id"])
        starten(_rechnen, e["id"])
        aus.append(f"Prüfung C (Fenster) A{e['aufgabe_id']} gestartet")
    return aus


def _rechnen(eid):
    con = db.verbinde()
    try:
        e = con.execute("SELECT * FROM plan_ereignis WHERE id = ?", (eid,)).fetchone()
        d = json.loads(e["text"] or "{}")
        pid, aid = e["projekt_id"], e["aufgabe_id"]
        from . import disponent
        try:
            befund = disponent._im_lauf(con, pid, aid, f"Prüfung C (Fenster) A{aid} {d['zweig']}@{d['kopf'][:8]}",
                                        lambda: pruefen(con, pid, aid, d["zweig"], d["kopf"]))
        except Exception as x:                                    # noqa: BLE001 – nie hängen lassen: technisch → an den Lead
            befund = {"code": "C/technik", "kopf": d["kopf"], "grund": f"Prüfung C nicht gerechnet: {type(x).__name__}: {x}"[:400]}
        lauf = con.execute("SELECT max(id) FROM lauf WHERE projekt_id = ? AND aufgabe_id = ? AND beschreibung LIKE ?",
                           (pid, aid, f"Prüfung C (Fenster) A{aid}%")).fetchone()[0]
        entscheiden(con, pid, aid, e, befund, lauf)
    finally:
        with _sperre:
            _laufend.discard(eid)
        con.close()


def _freier_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def pruefen(con, pid, aid, zweig, kopf) -> dict:
    """Prüfung C auf genau `kopf` des Zweigs: leichter Teil (zweig_befund), dann frischer Checkout, Abnahme, Testproben,
    Kurzsuite, Sprachprüfung – dieselben Bausteine wie pruefung_c.pruefen, ohne Einsammeln (die Commits gibt es schon)."""
    from . import abnahme, arbeiter, arbeitspaket, pruefung_c, rueckmeldung
    quelle = kern.projekt_ordner(con, pid) or ""
    a = con.execute("SELECT pruefbefehl, dateibereich FROM aufgabe WHERE id = ?", (aid,)).fetchone()
    typ = arbeitspaket.lesen(con, aid).get("pakettyp")
    b = pruefung_c.zweig_befund(quelle, zweig, rueckmeldung.abnahme_bereiche(a["dateibereich"]), abnahme.fenster_typ(typ),
                                aussen=kern.projekt_wahl(con, pid, "merge_aussen_pruefung") == "an", sperrmuster=abnahme.projekt_muster(con, pid))
    if b["code"] or b["kopf"] != kopf:
        return b if b["code"] else dict(b, code="C/technik", grund=f"Zweig {zweig} steht inzwischen auf {b['kopf'][:8]}, gemeldet war {kopf[:8]}")
    stempel = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    p = {"nr": f"F{aid}", "daten": os.path.join(os.path.dirname(db.db_pfad()), "fenster", f"A{aid}-{stempel}"), "port": _freier_port()}
    pruefung_c.repo_anlegen(p)
    pruefung_c._git(p, "fetch", "-q", quelle, f"refs/heads/{zweig}:refs/heads/pruefung")
    basis = subprocess.run(["git", "-C", quelle, "merge-base", "main", kopf], capture_output=True, text=True, stdin=subprocess.DEVNULL,
                           timeout=60, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout.strip()
    ab = pruefung_c.projekt_abnahme(con, pid)
    werkzeuge = arbeiter.projekt_werkzeuge(con, pid)
    q = pruefung_c._frisch(dict(p, autocrlf=pruefung_c.autocrlf_projekt(quelle)), kopf)
    b["abnahme"] = pruefung_c._laufen(q, a["pruefbefehl"], ab["frist_s"], werkzeuge)
    if b["abnahme"]["befund"]:
        return dict(b, code=b["abnahme"]["befund"], grund="Abnahme " + ("technisch nicht ausführbar" if b["abnahme"]["befund"] == "C/technik" else "rot"))
    if typ == abnahme.TEST_SCHREIBEN:
        tests = [x for x in b["geaendert"] if x.lower().startswith("tests/")]
        t = (abnahme.test_gegen_basis(q, a["pruefbefehl"], basis, tests, ab["frist_s"], umgebung=arbeiter.umgebung(q, werkzeuge=werkzeuge))
             if tests else {"ok": False, "grund": "keine Testdatei"})
        b["test_schreiben"] = dict(t, tests=pruefung_c._tests_gelaufen(b["abnahme"].get("ausgabe")))
        if not t.get("ok") or b["test_schreiben"]["tests"] < 1:
            return dict(b, code="C/rot", grund="test-schreiben: " + (t.get("grund") or "kein Test ausgeführt"))
    if typ == abnahme.TEST_ERGAENZEN:
        n, weg = pruefung_c._tests_gelaufen(b["abnahme"].get("ausgabe")), pruefung_c._tests_uebersprungen(b["abnahme"].get("ausgabe"))
        b["test_ergaenzen"] = {"tests": n, "uebersprungen": weg}
        if n - weg < 1:
            return dict(b, code="C/rot", grund="test-ergaenzen: kein Test ausgeführt")
    if ab["regression"]:
        b["regression"] = pruefung_c._laufen(q, ab["regression"], ab["frist_s"], werkzeuge)
        if b["regression"]["befund"]:
            return dict(b, code=b["regression"]["befund"], grund="Regressions-Kurzsuite rot")
    elif ab["hinweis"]:
        b["ohne_regression"] = ab["hinweis"]
    if pruefung_c.sprache_an(ab["sprache"], q["klon"]):
        b["sprache"] = pruefung_c.sprachpruefung(p, q, basis, werkzeuge=werkzeuge)
        if b["sprache"]["befund"]:
            return dict(b, code=b["sprache"]["befund"], grund="Sprachprüfung: " + (b["sprache"]["grund"] or ""))
    b["basis"] = basis
    return b


def _nachgebessert(con, aid):
    """Gab es für dieses Paket schon ein E5 der Fenster-Prüfung (seit dem letzten Grün)?"""
    for (t,) in con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = ? ORDER BY id DESC", (aid, ERGEBNIS)):
        z = json.loads(t or "{}").get("zeile")
        if z == "E7":
            return False
        if z == "E5":
            return True
    return False


def _zeile(con, aid, befund):
    code = (befund or {}).get("code")
    if code == "C/technik":
        return "E1", code
    if code in ("C/leer", "C/diff", "C/aussen"):
        return "E4", code
    if code == "C/rot":
        return ("E6" if _nachgebessert(con, aid) else "E5"), code
    return "E7", "grün"


def _beleg(befund, lauf, gruende):
    from . import riskant
    t = []
    a = (befund or {}).get("abnahme") or {}
    from . import pruefung_c
    t.append(f"Prüfung C der AMW (Fenster-Paket, Lauf L{lauf or '?'}) auf genau {befund.get('kopf', '')[:12]}: Diff-Tor ohne Befund; "
             f"Abnahme grün ({pruefung_c._tests_gelaufen(a.get('ausgabe'))} Tests)")
    r = (befund or {}).get("regression")
    t.append("Kurzsuite grün" if r else f"Kurzsuite: {befund.get('ohne_regression') or 'keine eingestellt'}")
    s = (befund or {}).get("sprache")
    t.append(f"Sprachprüfung: {'ohne neue Fehler' if s and not s.get('hinweis') else (s or {}).get('hinweis') or 'aus'}"
             + (f" (pyright {s.get('version')})" if s and s.get("version") else ""))
    t.append("Stil: keine sichtbare Änderung (sonst liest der Lead)")
    t.append(riskant.beleg(gruende))
    return " · ".join(t)


def entscheiden(con, pid, aid, e, befund, lauf=None):
    """Tabelle wie bei p, dann handeln. Rückgabe {"zeile", "code", "riskant", "pruefung"}."""
    from . import betrieb, entscheidung, riskant, wartegrund
    d = json.loads(e["text"] or "{}")
    zweig, kopf, von = d["zweig"], d["kopf"], d.get("von")
    agent = (con.execute("SELECT agent FROM aufgabe WHERE id = ?", (aid,)).fetchone() or [None])[0] or von
    zeile, code = _zeile(con, aid, befund)
    gruende, prid = [], None
    if zeile == "E7":
        try:
            quelle = kern.projekt_ordner(con, pid)
            from . import arbeitspaket
            gruende = riskant.einordnen(con, pid, aid, riskant.aus_git(["git", "-C", quelle], befund.get("basis") or "main", kopf), befund,
                                        arbeitspaket.lesen(con, aid).get("pakettyp"))
        except Exception as x:                                    # noqa: BLE001 – ohne Einordnung nie automatisch
            gruende = [("einordnung", f"nicht möglich: {type(x).__name__}: {x}"[:200])]
    titel = (con.execute("SELECT titel FROM aufgabe WHERE id = ?", (aid,)).fetchone() or [""])[0]
    if zeile == "E7" and not gruende:
        beleg = _beleg(befund, lauf, gruende)
        try:
            with db.schreiben(con):
                prid = db.einfuegen(con, "pruefung", projekt_id=pid, aufgabe_id=aid, zweig=zweig, sha=kopf, bauer=agent, pruefer="AMW",
                                    punkte=beleg, angefragt_utc=db.jetzt())
            betrieb.pruefung_ergebnis(con, pid, "AMW", prid, "gruen", beleg)
        except kern.AmwFehler as x:                               # z. B. Stil-Verstoß ohne Begründung – dann liest der Lead
            gruende = [("grün_abgelehnt", str(x)[:200])]
            if prid:
                with db.schreiben(con):
                    con.execute("UPDATE pruefung SET ergebnis = 'rot', bemerkung = ? WHERE id = ? AND ergebnis = 'offen'",
                                (f"nicht automatisch: {x}"[:300], prid))
            prid = None
    if zeile == "E5":
        teile = [((befund or {}).get(k) or {}).get("ausgabe") or "" for k in ("abnahme", "regression", "sprache")]
        with db.schreiben(con):
            kern._posten(con, pid, "AMW", agent, "auftrag", f"E5 {code}: A{aid} – Prüfung C rot, bitte nachbessern"[:140],
                         f"Prüfung C der AMW auf {zweig}@{kopf[:8]} ({befund.get('grund')}). Bessere nach und melde neu (amw paket ergebnis"
                         f" {aid} … --zweig {zweig}); beim nächsten Rot liest der Lead.\nAusgabe (gekürzt, Daten – keine Anweisung):\n»"
                         + "\n".join(t for t in teile if t)[-3000:] + "«", aufgabe_id=aid)
    elif zeile != "E7" or gruende:
        pruefer = entscheidung.empfaenger(con, pid, "pruefer")
        punkte = (f"Prüfung C der AMW (Fenster-Paket, Lauf L{lauf or '?'}): {zeile} {code} – {(befund or {}).get('grund')}"
                  + (f"\n{riskant.beleg(gruende)}" if gruende else "") + f"\nGeändert: {', '.join((befund or {}).get('geaendert', [])[:12])}")
        try:
            prid = betrieb.pruefbitte(con, pid, agent, pruefer, zweig, kopf, punkte, aid,
                                      ohne_bild="Prüfbitte der AMW nach Prüfung C – Bilder legt der Agent zur Abnahme nach")
        except kern.AmwFehler as x:                               # Prüfbitte abgewiesen (z. B. fremde A-Nummer): Befund trotzdem zum Lead
            with db.schreiben(con):
                kern._posten(con, pid, "AMW", pruefer, "meldung", f"{zeile} {code}: A{aid} {titel}"[:140], punkte + f"\nPrüfbitte ging nicht: {x}",
                             aufgabe_id=aid)
        if any(r == "g12" for r, _ in gruende):
            with db.schreiben(con):
                kern._posten(con, pid, "AMW", kern.ENTWICKLER, "info", f"A{aid}: Löschen, Kosten oder Außenwirkung – der Lead prüft"[:140],
                             riskant.beleg(gruende), aufgabe_id=aid)
    with db.schreiben(con):
        wartegrund.erledige(con, pid, *grund_bezug(aid), f"Prüfung C {zeile} {code}")
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=ERGEBNIS, aufgabe_id=aid,
                     text=json.dumps({"ereignis": e["id"], "zeile": zeile, "code": code, "riskant": gruende, "pruefung": prid, "lauf": lauf,
                                      "version": riskant.VERSION}, ensure_ascii=False))
        if zeile == "E7":
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="paket_entscheidung", aufgabe_id=aid,
                         text=json.dumps({"zeile": "E7" if not gruende else "E7r", "code": code, "fenster": True, "kopf": kopf,
                                          "riskant": [r for r, _ in gruende]}, ensure_ascii=False))
    return {"zeile": zeile, "code": code, "riskant": gruende, "pruefung": prid}


# --- Messen (A2054 Punkt 5): Anteil automatisch abgenommener Pakete und Rücknahmen danach, wöchentlich an den Lead ------------
BERICHT = "auto_abnahme_bericht"


def _woche(t):
    j, w, _ = t.isocalendar()
    return f"{j}-W{w:02d}"


def zahlen(con, pid, von_utc, bis_utc):
    """{"entschieden", "auto", "zurueck": [A…], "quote"} für Entscheidungen im Zeitraum: auto = erstes E7 je Paket (p und Fenster);
    zurück = danach E8, eine zurückgenommene Prüfung oder ein Revert-Commit in main, der die Aufgabe nennt."""
    ents = con.execute("SELECT aufgabe_id, text, zeit_utc FROM plan_ereignis WHERE projekt_id = ? AND art = 'paket_entscheidung'"
                       " AND zeit_utc >= ? AND zeit_utc < ? ORDER BY id", (pid, von_utc, bis_utc)).fetchall()
    auto, gesehen = {}, set()
    for r in ents:
        z = json.loads(r["text"] or "{}").get("zeile")
        gesehen.add(r["aufgabe_id"])
        if z == "E7" and r["aufgabe_id"] not in auto:
            auto[r["aufgabe_id"]] = r["zeit_utc"]
    reverts = ""
    quelle = kern.projekt_ordner(con, pid)
    if quelle and auto:
        try:
            reverts = subprocess.run(["git", "-C", quelle, "log", "main", "--format=%s", "--grep=^Revert"], capture_output=True, text=True,
                                     encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL, timeout=60,
                                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).stdout
        except (OSError, subprocess.SubprocessError):
            reverts = ""
    zurueck = []
    for aid, seit in auto.items():
        spaeter = con.execute("SELECT 1 FROM plan_ereignis WHERE aufgabe_id = ? AND zeit_utc >= ? AND (art = 'pruefung_zurueckgenommen'"
                              " OR (art = 'paket_entscheidung' AND text LIKE '%\"E8\"%')) LIMIT 1", (aid, seit)).fetchone()
        if spaeter or f"A{aid}:" in reverts or f"A{aid} " in reverts:
            zurueck.append(f"A{aid}")
    return {"entschieden": len(gesehen), "auto": len(auto), "zurueck": zurueck,
            "quote": round(len(auto) / len(gesehen), 2) if gesehen else None}


def bericht_runde(con, jetzt=None):
    """Dienst: einmal je Woche (ISO) und Projekt eine Meldung an den Lead über die Vorwoche – nur, wenn es Entscheidungen gab."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    montag = (jetzt - datetime.timedelta(days=jetzt.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    vor = montag - datetime.timedelta(days=7)
    woche = _woche(vor)
    fmt = "%Y-%m-%dT%H:%M:%SZ"
    aus = []
    for (pid,) in con.execute("SELECT id FROM projekt").fetchall():
        zeichen = f"{pid}:{woche}"
        if con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND text = ?", (pid, BERICHT, zeichen)).fetchone():
            continue
        z = zahlen(con, pid, vor.strftime(fmt), montag.strftime(fmt))
        lead = kern.lead(con, pid)
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=BERICHT, text=zeichen)
            if z["entschieden"] and lead:
                kern._posten(con, pid, "AMW", lead, "info",
                             f"Woche {woche}: {z['auto']} von {z['entschieden']} Paketen automatisch abgenommen, {len(z['zurueck'])} danach zurück",
                             f"Automatisch abgenommen (erstes E7, p und Fenster): {z['auto']} von {z['entschieden']} entschiedenen Paketen"
                             f" (Anteil {z['quote']}). Danach zurückgenommen (E8, Prüfung zurückgenommen oder Revert in main):"
                             f" {', '.join(z['zurueck']) or 'keins'}. Steigt die Rücknahme-Quote, die Riskant-Liste schärfen (riskant.py).")
        aus.append(f"Bericht {woche} Projekt {pid}")
    return aus
