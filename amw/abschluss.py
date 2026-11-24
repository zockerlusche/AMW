"""A2029 (TH164 F2 Schritt 5): Abschluss je Meilenstein – Gesamttest und Prüfer gegen das Konzept, dann Abnehmen oder Nacharbeit.

Sind alle Pakete eines Meilensteins, der mit einem Urteil endet (A2002), fertig, meldet die AMW ihn nicht sofort „bereit zur
Abnahme“. Erst laufen – einmal je Stand (welche Pakete, wann zuletzt fertig) – in einem losgelösten Prozess:
1. der Gesamttest: der gesamtlauf_befehl des Projekts im Projektordner, als Lauf der Lauf-Schlange (schwer; ohne Befehl:
   „kein Gesamttest eingestellt“, das hält nichts auf),
2. ein Prüfer: frischer claude -p (nur Lesen, Sonnet), der jedes Thema des Meilensteins gegen die fertigen Pakete abgleicht,
   die Vorführung vorbereitet und – wenn etwas fehlt oder der Test rot ist – Nacharbeits-Pakete nach dem Paket-Schema vorschlägt.
Ist alles erfüllt und der Test grün (oder nicht eingestellt), geht der Meilenstein wie bisher „bereit zur Abnahme“ – der
Abschlussbericht enthält dann die Prüfung und die Vorführung. Sonst (Fehlerweg) legt die AMW die Nacharbeits-Pakete im selben
Meilenstein an und startet sie gleich – ohne neues Start-Ja; der Lead bekommt eine Meldung, der Mensch eine Info.
„Nacharbeit anfordern“ (der Mensch oder der Lead, auch nach „bereit“): der Feinplaner plant mit dem Hinweis neue Pakete im
selben Meilenstein, die AMW legt sie an und startet sie (feinplanung, Art „nacharbeit“). Nach dem Ja zum Abschluss plant die AMW
den nächsten Meilenstein von selbst fein (A2031). Ist der Planer aus, bleibt es beim Bisherigen: gleich „bereit zur Abnahme“.

Ereignisse (plan_ereignis, Text JSON):
  abschluss_angestossen  {"bogen", "stand", "prozess"}
  abschluss_ergebnis     {"bogen", "stand", "test": {"lauf", "rc", "befehl"}, "themen": [...], "vorfuehrung": [...],
                          "ok": bool, "angelegt": {"N1": "A123"}, "usd", "fehler"?}

Schema des Prüfers (JSON):
  {"themen": [{"thema": "TH12", "erfuellt": true, "beleg": "welches Paket / welcher Commit es zeigt", "fehlt": "…" | null}],
   "vorfuehrung": ["Schritt 1 …", "Schritt 2 …"],
   "nacharbeit": [Pakete wie im Feinplan: {"schluessel": "N1", "meilenstein": "M7", "thema": "TH12", "titel", "auftrag", …}]}
  "nacharbeit" nur, wenn ein Thema nicht erfüllt oder der Gesamttest rot ist – dann mindestens ein Paket.
"""
import datetime
import json
import os
import subprocess
import sys
import tempfile

from . import db, kern

ANGESTOSSEN, ERGEBNIS = "abschluss_angestossen", "abschluss_ergebnis"
MODELL, EFFORT = "sonnet", "medium"
FRIST_S = 20 * 60
TEST_FRIST_S = 2 * 3600
LAEUFT_H = 6
MAX_RUNDEN = 2                 # TL #31785 (b): höchstens so viele automatische Nacharbeits-Runden je Meilenstein
SCHEMA_TEXT = (__doc__ or "")[(__doc__ or "").find("Schema des Prüfers"):].strip()

AUFTRAG = (
    "Du bist der Prüfer eines Software-Projekts. Ein Meilenstein ist fertig gebaut; du gleichst ihn gegen das Konzept ab. Lies "
    "meilenstein.md (Ziel, fertig wenn, Themen), jede Datei unter themen/, pakete.md (was gebaut wurde, mit Belegen) und "
    "test.md (Ergebnis des Gesamttests) sowie schema.md (das Antwort-Format). Prüfe für JEDES Thema des Meilensteins, ob das "
    "Gebaute es erfüllt – mit Beleg (Paket, Commit) oder dem, was fehlt. Schreib die Vorführung für den Menschen in wenigen "
    "Schritten. Fehlt etwas oder ist der Gesamttest rot, schlage Nacharbeits-Pakete nach schema.md vor (klein, mit Abnahme). "
    "Antworte NUR mit dem JSON-Objekt – kein Text davor oder danach. Du änderst nichts, du schreibst keine Dateien, du führst "
    "nichts aus.")


# --- Ereignisse ------------------------------------------------------------------------------------------------------------

def _ereignis(con, pid, art, **werte):
    return db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=art, bogen_id=werte.get("bogen"),
                        text=json.dumps(werte, ensure_ascii=False))


def _ereignisse(con, pid, art, bid):
    aus = []
    for r in con.execute("SELECT id, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND bogen_id = ? ORDER BY id",
                         (pid, art, bid)):
        try:
            aus.append({**json.loads(r["text"] or "{}"), "id": r["id"], "zeit_utc": r["zeit_utc"]})
        except ValueError:
            continue
    return aus


def ergebnis(con, pid, bid, stand=None):
    """Das jüngste Prüf-Ergebnis des Meilensteins (zu diesem Stand) oder None."""
    e = [x for x in _ereignisse(con, pid, ERGEBNIS, bid) if stand is None or x.get("stand") == stand]
    return e[-1] if e else None


def _laeuft(con, pid, bid, stand):
    an = [x for x in _ereignisse(con, pid, ANGESTOSSEN, bid) if x.get("stand") == stand]
    if not an or ergebnis(con, pid, bid, stand):
        return None
    t = db.utc_lesen(an[-1]["zeit_utc"])
    return None if (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() > LAEUFT_H * 3600 else an[-1]


# --- vor „bereit zur Abnahme“ (aus planautomatik) ----------------------------------------------------------------------------

def _spawn(pid, bid, stand, umgebung=None):
    from . import planer
    befehl = [sys.executable, "-I", "-X", "utf8", planer.EINSTIEG, "--abschluss", "--projekt-id", str(pid), "--bogen", str(bid),
              "--stand", stand]
    flags = (0x00000008 | 0x00000200 | planer.OHNE_FENSTER) if os.name == "nt" else 0
    return subprocess.Popen(befehl, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                            creationflags=flags, env=umgebung, start_new_session=os.name != "nt").pid


STARTER = _spawn             # Tests setzen eine Attrappe; tests/abschotten schaltet das Anstoßen ganz ab (AMW_PLANER_AUS)


def vor_bereit(con, pid, b, stand):
    """Aus planautomatik, bevor ein Meilenstein „bereit zur Abnahme“ gemeldet wird: „melden“ (geprüft und erfüllt – oder kein
    Prüfer möglich), „pruefung“ (gerade angestoßen oder läuft) oder „nacharbeit“ (nicht erfüllt, Pakete angelegt)."""
    from . import planer
    e = ergebnis(con, pid, b["id"], stand)
    if e:
        return "melden" if e.get("ok") or e.get("fehler") or e.get("grenze") else "nacharbeit"
    if os.environ.get("AMW_PLANER_AUS") or planer.schalter_text(con, pid):
        return "melden"                                  # ohne Planer wie bisher: gleich bereit
    with db.schreiben(con):
        if _laeuft(con, pid, b["id"], stand):
            return "pruefung"
        grenze, usd = planer.tagesgrenze(con, pid), planer.heute_usd(con, pid)   # TL #31785 (a): gemeinsame Tagesgrenze der Planer
        if grenze is None or usd < grenze:
            eid = _ereignis(con, pid, ANGESTOSSEN, bogen=b["id"], stand=stand)
        else:
            eid = None
    if eid is None:
        eintragen(con, pid, b["id"], stand, None, None, fehler=f"Tagesgrenze der Planer erreicht ({usd:.2f} von {grenze:.2f} $) –"
                                                               " Abschlussprüfung nicht gestartet")
        return "melden"
    try:
        prozess = STARTER(pid, b["id"], stand)
    except OSError as x:
        eintragen(con, pid, b["id"], stand, None, None, fehler=f"Prüfer ließ sich nicht starten: {x}")
        return "melden"
    with db.schreiben(con):
        con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?",
                    (json.dumps({"bogen": b["id"], "stand": stand, "prozess": prozess}, ensure_ascii=False), eid))
    return "pruefung"


# --- der losgelöste Prozess: Gesamttest, Prüfer, Ergebnis ------------------------------------------------------------------

def gesamttest(con, pid, b):
    """Der Gesamttest des Projekts als Lauf der Schlange (schwer, ein Gesamtlauf zur Zeit): {"lauf", "rc", "befehl", "ende"} –
    oder {"rc": None, "befehl": None}, wenn das Projekt keinen gesamtlauf_befehl hat."""
    import time
    from . import belegung, betrieb, einrichtung, freigabereif, laufdienst
    ordner = kern.projekt_ordner(con, pid)
    amw = bool(ordner) and os.path.normcase(os.path.abspath(ordner)) == os.path.normcase(os.path.abspath(einrichtung.WURZEL))   # wie buendel
    befehl = freigabereif._gesamtlauf_befehl(con, pid, amw)
    if not befehl or not ordner or not os.path.isdir(ordner):
        return {"lauf": None, "rc": None, "befehl": None, "ende": ""}
    agent = kern.lead(con, pid) or kern.ENTWICKLER
    lid = betrieb.lauf_start(con, pid, agent, f"Gesamttest Meilenstein {b['nr']} (Abschluss, A2029, automatisch)", None, True, False,
                             None, warten=True, erwartet_min=40, befehl=[befehl], ordner=ordner, waechter=os.getpid(), selbst=True)
    belegung.lauf_merken(lid, os.getpid())
    rc = None
    try:
        while True:
            l = betrieb.lauf_zeile(con, pid, lid)
            if l["status"] == "laeuft":
                break
            if l["status"] in ("fertig", "abgebrochen"):
                return {"lauf": lid, "rc": l["rc"], "befehl": befehl, "ende": f"L{lid} {l['status']}"}
            time.sleep(5)
        betrieb.lauf_uebernehmen(con, lid, "agent")
        pfad = laufdienst.ergebnis_pfad(betrieb.lauf_zeile(con, pid, lid))
        s = betrieb.pruefstand([befehl], ordner)
        with open(pfad, "w", encoding="utf-8", errors="replace") as aus:
            aus.write(f"# AMW L{lid} · Gesamttest Meilenstein {b['nr']}\n# Befehl: {befehl}\n# Ordner: {ordner}\n# {betrieb.stand_text(s)}\n")
            aus.flush()
            try:
                rc = subprocess.run(befehl, shell=True, cwd=ordner, env=laufdienst.umgebung(), stdout=aus, stderr=subprocess.STDOUT,
                                    stdin=subprocess.DEVNULL, timeout=TEST_FRIST_S,
                                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)).returncode
            except subprocess.TimeoutExpired:
                rc = 124
        with open(pfad, encoding="utf-8", errors="replace") as f:
            ende = "".join(f.readlines()[-60:])
        return {"lauf": lid, "rc": rc, "befehl": befehl, "ende": ende}
    finally:
        try:
            betrieb.lauf_ende(con, pid, agent, lid, rc if rc is not None else 1, f"Gesamttest Meilenstein {b['nr']}: rc {rc}"[:500])
        except kern.AmwFehler:
            pass                                          # schon beendet (abgebrochen)
        belegung.lauf_vergessen(lid)


def _dateien(con, pid, b, test, ordner):
    from . import feinplanung, grobplan
    os.makedirs(os.path.join(ordner, "themen"), exist_ok=True)
    themen = feinplanung.themen_der(con, pid, b)
    teile = {"meilenstein.md": f"# M{b['nr']} {b['titel']}\n\nZiel: {b['ziel'] or '–'}\nFertig, wenn: {b['abnahme'] or '–'}\n"
                               f"Themen: {', '.join(f'TH{t}' for t in themen) or '–'}\n"}
    frei = grobplan.themen_frei(con, pid)
    for tid in themen:
        t = con.execute("SELECT name FROM thema WHERE id = ?", (tid,)).fetchone()
        teile[f"themen/TH{tid}.md"] = f"# TH{tid} {t['name'] if t else ''}\n\n{(frei.get(tid) or {}).get('text', '')}\n"
    pk = con.execute("SELECT id, titel, auftrag, status, beleg, zusammenfassung FROM aufgabe WHERE bogen_id = ? ORDER BY id", (b["id"],)).fetchall()
    teile["pakete.md"] = "# Pakete des Meilensteins\n\n" + "\n\n".join(
        f"## A{p['id']} {p['titel']} [{p['status']}]\nAuftrag: {' '.join((p['auftrag'] or '').split())[:1500]}\nBeleg: {p['beleg'] or '–'}\n"
        f"Ergebnis: {p['zusammenfassung'] or '–'}" for p in pk) + "\n"
    teile["test.md"] = ("# Gesamttest\n\n" + ("kein Gesamttest eingestellt\n" if not test.get("befehl") else
                        f"Befehl: {test['befehl']}\nRückgabe: {test.get('rc')}\n\nEnde der Ausgabe:\n\n{test.get('ende') or ''}\n"))
    teile["schema.md"] = "# Antwort-Format\n\n" + SCHEMA_TEXT + "\n\n" + feinplanung.SCHEMA_TEXT + "\n"
    for name, text in teile.items():
        with open(os.path.join(ordner, *name.split("/")), "w", encoding="utf-8", newline="\n") as d:
            d.write(text)
    return sorted(teile)


def pruefer(con, pid, b, test, prog=None, zusatz=None):
    """Der Prüfer (claude -p, nur Lesen). {"ergebnis", "usd", "fehler"}."""
    from . import arbeiter, planer, platz, versionsprobe
    with tempfile.TemporaryDirectory(prefix="amw-abschluss-", ignore_cleanup_errors=True) as ordner:
        p = platz.pfade(os.path.join(ordner, "plaetze"), 1)
        os.makedirs(p["klon"])
        subprocess.run(["git", "init", "-q", "-b", "main", p["klon"]], check=True, capture_output=True, creationflags=planer.OHNE_FENSTER)
        dateien = _dateien(con, pid, b, test, p["klon"])
        r = arbeiter.laufen(p, AUFTRAG + "\n\nDateien: " + ", ".join(dateien), None, modell=MODELL, effort=EFFORT, prog=prog,
                            zusatz=zusatz, nur_lesen=True, geprueft=versionsprobe.geprueft(con), frist_s=FRIST_S)
    erg = r.get("ergebnis") or {}
    usd = erg.get("total_cost_usd")
    text = (erg.get("result") or "").strip()
    if r.get("abweichungen") or r.get("rc") != 0 or erg.get("is_error") or not text:
        return {"ergebnis": None, "usd": usd, "fehler": "; ".join(r.get("abweichungen") or []) or r.get("fehler") or f"kein Ergebnis (rc {r.get('rc')})"}
    return {"ergebnis": planer.json_aus_text(text), "usd": usd, "fehler": None}


def ausfuehren(con, pid, bid, stand, prog=None, zusatz=None):
    """Der losgelöste Prozess: Gesamttest, dann Prüfer, dann eintragen (auch einen Fehler)."""
    b = con.execute("SELECT * FROM bogen WHERE id = ? AND projekt_id = ?", (bid, pid)).fetchone()
    test, aus = {"befehl": None, "rc": None}, None
    try:
        test = gesamttest(con, pid, b)
        aus = pruefer(con, pid, b, test, prog=prog, zusatz=zusatz)
    except Exception as x:                                # noqa: BLE001 – niemand sieht die Ausgabe: als Fehler eintragen
        aus = {"ergebnis": None, "usd": None, "fehler": f"{type(x).__name__}: {x}"[:300]}
    return eintragen(con, pid, bid, stand, test, aus.get("ergebnis"), usd=aus.get("usd"), fehler=aus.get("fehler"))


def _pruefen(daten, con, pid, b, rot):
    """Prüft das Ergebnis des Prüfers: jedes Thema bewertet; Nacharbeit (Feinplan-Schema) genau dann, wenn etwas fehlt oder der
    Test rot ist. Rückgabe vereinheitlicht oder planer.PlanFehler."""
    from . import feinplanung, planer
    if isinstance(daten, str):
        daten = planer.json_aus_text(daten)
    if not isinstance(daten, dict):
        raise planer.PlanFehler(["oben muss ein Objekt stehen"])
    f, themen = [], feinplanung.themen_der(con, pid, b)
    bewertet = {}
    for t in daten.get("themen") or []:
        n = str((t or {}).get("thema") or "").strip()
        if not n.startswith("TH") or not n[2:].isdigit() or int(n[2:]) not in themen:
            f.append(f"themen: {n or '?'} gehört nicht zu M{b['nr']}")
            continue
        if not isinstance(t.get("erfuellt"), bool) or not str(t.get("beleg") or t.get("fehlt") or "").strip():
            f.append(f"themen: {n} braucht erfuellt (ja/nein) und beleg bzw. fehlt")
            continue
        bewertet[int(n[2:])] = {"thema": n, "erfuellt": t["erfuellt"], "beleg": str(t.get("beleg") or "")[:500] or None,
                                "fehlt": str(t.get("fehlt") or "")[:500] or None}
    fehlen = [f"TH{x}" for x in themen if x not in bewertet]
    if fehlen:
        f.append("nicht bewertet: " + ", ".join(fehlen))
    vf = [str(x)[:300] for x in (daten.get("vorfuehrung") or []) if str(x).strip()][:12]
    ok = all(x["erfuellt"] for x in bewertet.values()) and not rot
    nach = daten.get("nacharbeit") or []
    pakete = None
    if not ok:
        if not nach:
            f.append("nicht erfüllt oder Test rot, aber keine nacharbeit")
        else:
            try:
                pakete = feinplanung.pruefen({"pakete": nach}, con, pid, [b["id"]])["pakete"]
            except planer.PlanFehler as x:
                f += [f"nacharbeit: {m}" for m in x.fehler]
    if f:
        raise planer.PlanFehler(f)
    return {"themen": [bewertet[x] for x in themen], "vorfuehrung": vf, "ok": ok, "pakete": pakete}


def eintragen(con, pid, bid, stand, test, ergebnis_, usd=None, fehler=None):
    """Das Ergebnis eintragen. Erfüllt → nichts weiter (planautomatik meldet „bereit“ mit Bericht). Nicht erfüllt → die
    Nacharbeit anlegen und starten (kein neues Start-Ja). Ging der Prüfer nicht, wird es ein Fehler-Ergebnis – dann meldet
    planautomatik „bereit“ wie bisher, und der Lead weiß, dass die Prüfung fehlt. Rückgabe: das Ereignis."""
    from . import feinplanung, planer, reihenfolge
    b = con.execute("SELECT * FROM bogen WHERE id = ? AND projekt_id = ?", (bid, pid)).fetchone()
    test = test or {"befehl": None, "rc": None}
    rot = test.get("befehl") is not None and test.get("rc") != 0
    werte = {"bogen": bid, "stand": stand, "test": {k: test.get(k) for k in ("lauf", "rc", "befehl")}, "usd": usd}
    e = None
    if not fehler:
        try:
            e = _pruefen(ergebnis_, con, pid, b, rot)
        except planer.PlanFehler as x:
            fehler = "; ".join(x.fehler)[:500]
    if e is None and rot:                                 # rot ohne brauchbare Nacharbeit: ein Paket „Gesamttest rot“
        th = feinplanung.themen_der(con, pid, b)
        e = {"themen": [], "vorfuehrung": [], "ok": False, "pakete": [{
            "schluessel": "N1", "meilenstein": f"M{b['nr']}", "thema": th[0] if th else None, "nach": [],
            "titel": f"Gesamttest rot beheben (L{test.get('lauf')})"[:120],
            "auftrag": f"Der Gesamttest zum Abschluss von Meilenstein {b['nr']} ist rot (L{test.get('lauf')}, rc {test.get('rc')}). Ursache"
                       " finden und beheben, bis er grün ist.", "groesse": "M", "art": "fehlersuche", "ausfuehrung": "agent",
            "modell": None, "effort": None, "fertig_quelle": "commit", "abnahme_befehl": None, "bereiche": None, "pakettyp": None,
            "interaktiv_grund": "Fehlersuche über die ganze Suite"}]}
    angelegt, grenze = {}, False
    runden = sum(1 for x in _ereignisse(con, pid, ERGEBNIS, bid) if x.get("angelegt"))
    if e and not e["ok"] and e["pakete"] and runden >= MAX_RUNDEN:
        grenze = True                                     # TL #31785 (b): keine dritte Runde – „bereit“ mit offenen Punkten
    elif e and not e["ok"] and e["pakete"]:
        angelegt = feinplanung._anlegen(con, pid, [b], {"pakete": e["pakete"]})
        starter = kern.lead(con, pid) or kern.ENTWICKLER
        if b["status"] == "aktiv":
            reihenfolge.starten(con, pid, starter, bid)
    werte.update({"themen": (e or {}).get("themen") or [], "vorfuehrung": (e or {}).get("vorfuehrung") or [],
                  "ok": bool(e and e["ok"]), "angelegt": angelegt, **({"fehler": fehler} if fehler and not angelegt else {}),
                  **({"grenze": True} if grenze else {})})
    lead = kern.lead(con, pid) or kern.ENTWICKLER
    with db.schreiben(con):
        eid = _ereignis(con, pid, ERGEBNIS, **werte)
        if angelegt:
            nicht = [t["thema"] for t in werte["themen"] if not t["erfuellt"]]
            grund = ", ".join(([f"Gesamttest rot (L{test.get('lauf')})"] if rot else []) + ([f"nicht erfüllt: {', '.join(nicht)}"] if nicht else []))
            for wer, art in ((lead, "meldung"), (kern.ENTWICKLER, "info")):
                if wer == kern.ENTWICKLER and lead == kern.ENTWICKLER and art == "info":
                    continue
                kern._posten(con, pid, "AMW", wer, art, f"Meilenstein {b['nr']}: Nacharbeit – {len(angelegt)} Paket(e) gestartet"[:140],
                             f"Die Abschlussprüfung von Meilenstein {b['nr']} „{b['titel']}“ ergab: {grund}. Die AMW hat die Nacharbeit"
                             f" im selben Meilenstein angelegt und gestartet: {', '.join(angelegt.values())}. Danach prüft sie erneut.")
        elif grenze:
            kern._posten(con, pid, "AMW", lead, "meldung", f"Meilenstein {b['nr']}: nach {MAX_RUNDEN} Nacharbeits-Runden noch offen"[:140],
                         f"Die Abschlussprüfung von Meilenstein {b['nr']} „{b['titel']}“ findet noch Lücken, aber die AMW legt nach"
                         f" {MAX_RUNDEN} automatischen Runden keine weitere Nacharbeit an. Der Meilenstein geht „bereit zur Abnahme“; die"
                         " offenen Punkte stehen im Abschlussbericht. Abnehmen oder Nacharbeit von Hand: amw bogen nacharbeit N --hinweis …")
        elif fehler:
            kern._posten(con, pid, "AMW", lead, "meldung", f"Meilenstein {b['nr']}: Abschlussprüfung ging nicht"[:140],
                         f"{fehler}\nDer Meilenstein geht trotzdem „bereit zur Abnahme“ – die Prüfung gegen das Konzept fehlt im Bericht.")
    return {**werte, "id": eid}


# --- Nacharbeit anfordern (Mensch oder Lead) -------------------------------------------------------------------------------

def nacharbeit(con, pid, von, bid, hinweis):
    """„Nacharbeit anfordern“: der Feinplaner plant mit dem Hinweis neue Pakete im selben Meilenstein; sie starten ohne neues
    Ja (feinplanung, Art nacharbeit). Lead oder Mensch, Hinweis Pflicht, Meilenstein aktiv (läuft oder wartet auf die Abnahme)."""
    from . import feinplanung
    if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler("Nacharbeit fordern der Mensch oder der Lead an")
    if not (hinweis or "").strip():
        raise kern.AmwFehler("Nacharbeit: was fehlt? (--hinweis …)")
    b = con.execute("SELECT * FROM bogen WHERE id = ? AND projekt_id = ?", (bid, pid)).fetchone()
    if not b or b["status"] != "aktiv":
        raise kern.AmwFehler(f"Meilenstein {bid}: Nacharbeit nur für einen laufenden Meilenstein (auch wenn er auf die Abnahme wartet)")
    return feinplanung.anstossen(con, pid, [bid], von=von, hinweis=hinweis, nacharbeit=True)


def bericht_teil(con, pid, bid):
    """Zeilen für den Abschlussbericht: Gesamttest, Prüfung je Thema, Vorführung – aus dem jüngsten Ergebnis."""
    e = ergebnis(con, pid, bid)
    if not e:
        return []
    t = e.get("test") or {}
    z = ["", "## Prüfung gegen das Konzept", "",
         "Gesamttest: " + ("nicht eingestellt" if not t.get("befehl") else f"L{t.get('lauf')} · rc {t.get('rc')}"
                           + (" · grün" if t.get("rc") == 0 else " · rot"))]
    if e.get("fehler"):
        z.append(f"Prüfer: ging nicht – {e['fehler']}")
    if e.get("grenze"):
        z.append(f"Nach {MAX_RUNDEN} automatischen Nacharbeits-Runden noch offen – keine weitere Nacharbeit angelegt:")
    z += [f"- {x['thema']}: {'erfüllt' if x['erfuellt'] else 'nicht erfüllt'}" + (f" – {x['beleg']}" if x.get("beleg") else "")
          + (f" – fehlt: {x['fehlt']}" if x.get("fehlt") else "") for x in e.get("themen") or []]
    if e.get("vorfuehrung"):
        z += ["", "## Vorführung", ""] + [f"{i}. {s}" for i, s in enumerate(e["vorfuehrung"], 1)]
    return z


# --- Einstieg für amw-planer.py --abschluss --------------------------------------------------------------------------------

def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="amw-planer --abschluss")
    ap.add_argument("--projekt-id", type=int, required=True)
    ap.add_argument("--bogen", type=int, required=True)
    ap.add_argument("--stand", required=True)
    x = ap.parse_args(argv)
    con = db.verbinde()
    try:
        ausfuehren(con, x.projekt_id, x.bogen, x.stand)
    finally:
        con.close()
