"""Zuarbeit frischer claude -p-Agenten je Thema (A1914, D1304 v12 §4/§6b, F5352, W2423).

Liefert ein Pfleger (Agent) eine neue Fassung eines Themas, stößt die AMW EINEN Gegenleser an: einen frischen claude -p, der
nur liest (Glob/Grep/Read im eigenen Ordner, kein Bash, kein Schreiben, --restricted wie die Arbeiter). Er läuft als
angemeldeter Lauf der Lauf-Schlange (leicht) in einem losgelösten Prozess, bekommt die Fassung, die geltenden Beschlüsse und
die zuletzt freigegebene Fassung als Dateien und antwortet mit Einwänden als Text. Die gehen als Auftrag an den Pfleger – er
liefert eine neue Fassung oder lässt sie so. Erst wenn der Gegenleser fertig ist, steht das Thema auf „wartet auf dich“;
solange er liest, sieht der Mensch „wird gegengelesen · seit …“ (themen.status). Eine Fassung, die nach dem Gegenlesen als
Antwort darauf kommt (seit der letzten Handlung des Menschen), wird nicht noch einmal gegengelesen – je Runde ein Gegenleser.

Ereignisse (plan_ereignis, ohne Schemaänderung, Text JSON mit "thema" vorn wie alle Themen-Ereignisse):
  thema_gegenlesen    {"thema", "fassung", "rolle", "modell", "prozess"}            – angestoßen
  thema_gegengelesen  {"thema", "fassung", "rolle", "modell", "einwaende", "usd", "lauf", "fehler"} – fertig (auch mit Fehler)

Einstellung je Projekt: themen_gegenlesen = haiku (Vorgabe) | sonnet | aus (Lead oder Mensch, amw projekt einstellen).
Weitere Rollen (Gliederung, Machbarkeit) sind in ROLLEN vorbereitet, aber nicht gebaut.
"""
import datetime
import functools
import json
import os
import subprocess
import sys
import tempfile
import time

from . import db, kern, planer_fortschritt

ANGESTOSSEN, FERTIG = "thema_gegenlesen", "thema_gegengelesen"
EINSTIEG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "amw-gegenlesen.py")
OHNE_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)
LAEUFT_H = 2                 # so lange gilt ein Gegenleser ohne Ende als laufend (fällt der Prozess weg, sperrt er das Thema nicht)
MODELLE = {"opus": "opus", "haiku": "haiku", "sonnet": "sonnet"}
EFFORT = {"opus": "high", "haiku": "low", "sonnet": "low"}     # A1930 (TH159, #29978): Gegenlesen Opus high als Vorgabe
# D1304 v12 §4: Rollen der Zuarbeit. Gebaut ist nur das Gegenlesen; die anderen sind vorbereitet (gebaut: False).
ROLLEN = {
    "gegenlesen": {"gebaut": True, "titel": "Gegenlesen",
                   "auftrag": "Du liest eine neue Fassung eines Konzept-Themas gegen. Lies thema.md (die neue Fassung), "
                              "beschluesse.md (die geltenden Beschlüsse dazu) und, falls vorhanden, freigegeben.md (die zuletzt "
                              "freigegebene Fassung). Nenne Einwände: Widersprüche zu einem Beschluss, Lücken, Unklares, "
                              "Behauptungen ohne Grundlage, Stellen, die sich gegenüber freigegeben.md verschlechtert haben. Je "
                              "Einwand eine Zeile mit „- “, kurz, mit der Stelle. Keine Einwände: antworte genau „Keine Einwände.“ "
                              "Du änderst nichts, du schreibst keine Dateien, du führst nichts aus."},
    "gliederung": {"gebaut": False, "titel": "Gliederung", "auftrag": None},
    "machbarkeit": {"gebaut": False, "titel": "Machbarkeit", "auftrag": None},
}


def einstellung(con, pid):
    return kern.projekt_wahl(con, pid, "themen_gegenlesen")


def _ereignisse(con, pid, tid, art=None):
    arten = (art,) if art else (ANGESTOSSEN, FERTIG)
    aus = []
    for r in con.execute(f"SELECT id, art, von, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art IN ({','.join('?' * len(arten))})"
                         " AND text LIKE ? ORDER BY id", (pid, *arten, f'{{"thema": {tid},%')):
        try:
            aus.append({**dict(r), **json.loads(r["text"])})
        except ValueError:
            continue
    return aus


def _alt(zeit_utc, jetzt=None):
    t = db.utc_lesen(zeit_utc)
    return ((jetzt or datetime.datetime.now(datetime.timezone.utc)) - t).total_seconds() > LAEUFT_H * 3600


def laeuft(con, pid, tid, fassung):
    """Liest gerade ein Gegenleser diese Fassung? Das Ereignis „angestoßen“ (oder None)."""
    ev = _ereignisse(con, pid, tid)
    an = [e for e in ev if e["art"] == ANGESTOSSEN and e.get("fassung") == fassung]
    if not an or any(e["art"] == FERTIG and e.get("fassung") == fassung and e["id"] > an[-1]["id"] for e in ev):
        return None
    return None if _alt(an[-1]["zeit_utc"]) else an[-1]


def letztes(con, pid, tid):
    """Das jüngste fertige Gegenlesen des Themas (Ereignis) oder None."""
    ev = _ereignisse(con, pid, tid, FERTIG)
    return ev[-1] if ev else None


def _schon_in_dieser_runde(con, pid, tid):
    """Gab es seit der letzten Handlung des Menschen schon ein Gegenlesen? Dann ist die neue Fassung die Antwort darauf."""
    from . import themen
    mensch = [e for e in themen._ereignisse(con, pid, tid) if e["art"] in (themen.EREIGNIS["freigegeben"], themen.EREIGNIS["zurueck"],
                                                                          themen.EREIGNIS["bearbeitet"])]
    seit = mensch[-1]["id"] if mensch else 0
    return any(e["id"] > seit for e in _ereignisse(con, pid, tid, ANGESTOSSEN))


def _spawn(pid, tid, fassung, umgebung=None):
    befehl = [sys.executable, "-I", "-X", "utf8", EINSTIEG, "--projekt-id", str(pid), "--thema", str(tid), "--fassung", str(fassung)]
    flags = (0x00000008 | 0x00000200 | OHNE_FENSTER) if os.name == "nt" else 0        # DETACHED, NEW_GROUP wie der Starter
    return subprocess.Popen(befehl, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                            creationflags=flags, env=umgebung, start_new_session=os.name != "nt").pid


STARTER = _spawn             # Tests setzen eine Attrappe; tests/abschotten schaltet das Anstoßen ganz ab (AMW_GEGENLESEN_AUS)


def anstossen(con, pid, tid, fassung, rolle="gegenlesen", von="AMW"):
    """Nach einer neuen Fassung eines Agenten (themen.pflegen, eigene Transaktion): einen Gegenleser anstoßen – außer die
    Einstellung ist aus, es ist schon einer für diese Fassung da oder es gab in dieser Runde schon einen. Rückgabe: Text oder None."""
    if os.environ.get("AMW_GEGENLESEN_AUS") or einstellung(con, pid) == "aus" or not ROLLEN[rolle]["gebaut"]:
        return None
    from . import kern
    if kern.projekt_schalter(con, pid) != "an":               # A1926: Themen-Ablauf nur bei eingeschaltetem Projekt
        return None
    modell = MODELLE[einstellung(con, pid)]
    wer = planer_fortschritt.ausloeser(von)                   # A2078: wer die Fassung vorgelegt hat
    with db.schreiben(con):                                   # in einer Schreib-Transaktion: nie doppelt angestoßen
        if _schon_in_dieser_runde(con, pid, tid):
            return None
        eid = db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=ANGESTOSSEN,
                           text=json.dumps({"thema": tid, "fassung": fassung, "rolle": rolle, "modell": modell, **wer}, ensure_ascii=False))
    try:
        prozess = STARTER(pid, tid, fassung)
    except OSError as e:                                      # ließ sich nicht starten → fertig mit Fehler, das Thema wartet nicht
        abschliessen(con, pid, tid, fassung, {"einwaende": None, "usd": None, "lauf": None, "modell": modell,
                                              "fehler": f"Gegenleser ließ sich nicht starten: {e}"})
        return f"TH{tid}: Gegenleser ließ sich nicht starten ({e})"
    with db.schreiben(con):
        con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?",
                    (json.dumps({"thema": tid, "fassung": fassung, "rolle": rolle, "modell": modell, "prozess": prozess, **wer},
                                ensure_ascii=False), eid))
    return f"TH{tid} Fassung {fassung}: Gegenleser ({modell}) angestoßen"


# --- der Lauf -------------------------------------------------------------------------------------------------------------

def _dateien(con, pid, t, fassung, ordner):
    """Was der Gegenleser liest – als Dateien in seinem eigenen Ordner (er liest nichts sonst)."""
    from . import themen
    f = con.execute("SELECT text FROM thema_fassung WHERE thema_id = ? AND nr = ?", (t["id"], fassung)).fetchone()
    if not f:
        raise kern.AmwFehler(f"TH{t['id']} hat keine Fassung {fassung}")
    b = con.execute("SELECT id, stichwort, regel FROM beschluss WHERE projekt_id = ? AND thema = ? COLLATE NOCASE AND status = 'gilt'"
                    " ORDER BY id", (pid, t["name"])).fetchall()
    s = themen.status(con, t)
    frei = con.execute("SELECT text FROM thema_fassung WHERE thema_id = ? AND nr = ?", (t["id"], s["freigegeben"])).fetchone() \
        if s["freigegeben"] and s["freigegeben"] != fassung else None
    teile = {"thema.md": f"# {t['name']} – Fassung {fassung}\n\n{f['text']}\n",
             "beschluesse.md": f"# Geltende Beschlüsse zu „{t['name']}“\n\n"
                               + ("\n".join(f"- B{x['id']} {x['stichwort']}: {x['regel']}" for x in b) or "(keine)") + "\n"}
    if frei:
        teile["freigegeben.md"] = f"# {t['name']} – zuletzt freigegeben (Fassung {s['freigegeben']})\n\n{frei['text']}\n"
    for name, text in teile.items():
        with open(os.path.join(ordner, name), "w", encoding="utf-8", newline="\n") as d:
            d.write(text)
    return sorted(teile)


def lesen(con, pid, t, fassung, modell, prog=None, zusatz=None):
    """Der Gegenleser selbst, in einem leeren eigenen Ordner (wie ein Platz). Rückgabe {"einwaende", "usd", "fehler", "lauf"}."""
    from . import arbeiter, platz, versionsprobe
    with tempfile.TemporaryDirectory(prefix="amw-gegenlesen-", ignore_cleanup_errors=True) as ordner:
        p = platz.pfade(os.path.join(ordner, "plaetze"), 1)
        os.makedirs(p["klon"])
        subprocess.run(["git", "init", "-q", "-b", "main", p["klon"]], check=True, capture_output=True, creationflags=OHNE_FENSTER)
        dateien = _dateien(con, pid, t, fassung, p["klon"])
        auftrag = ROLLEN["gegenlesen"]["auftrag"] + "\n\nDateien: " + ", ".join(dateien)
        r = arbeiter.laufen(p, auftrag, None, modell=modell, effort=EFFORT.get(modell, "low"), prog=prog, zusatz=zusatz, nur_lesen=True,
                            geprueft=versionsprobe.geprueft(con))
    erg = r.get("ergebnis") or {}
    usd = erg.get("total_cost_usd")
    if r.get("abweichungen"):
        return {"einwaende": None, "usd": usd, "fehler": "; ".join(r["abweichungen"])[:500], "lauf": r}
    text = (erg.get("result") or "").strip()
    if r.get("rc") != 0 or erg.get("is_error") or not text:
        return {"einwaende": None, "usd": usd, "fehler": r.get("fehler") or f"kein Ergebnis (rc {r.get('rc')})", "lauf": r}
    return {"einwaende": text[:6000], "usd": usd, "fehler": None, "lauf": r}


def abschliessen(con, pid, tid, fassung, aus, lauf=None):
    """Ergebnis eintragen und dem Pfleger (sonst dem Lead) schicken – auch einen Fehler, dann wartet das Thema nicht."""
    t = con.execute("SELECT * FROM thema WHERE id = ? AND projekt_id = ?", (tid, pid)).fetchone()
    an = (t["pfleger"] if t and t["pfleger"] and t["pfleger"] != kern.ENTWICKLER else None) or kern.lead(con, pid)
    kosten = f"{aus['usd']:.2f} $" if isinstance(aus.get("usd"), (int, float)) else "Kosten unbekannt"
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=FERTIG,
                     text=json.dumps({"thema": tid, "fassung": fassung, "rolle": "gegenlesen", "modell": aus.get("modell"),
                                      "einwaende": aus.get("einwaende"), "usd": aus.get("usd"), "lauf": lauf, "fehler": aus.get("fehler")},
                                     ensure_ascii=False))
        if an and an != kern.ENTWICKLER and t:
            name = t["name"][:60]
            if aus.get("fehler"):
                kern._posten(con, pid, "AMW", an, "meldung", f"Thema „{name}“: Gegenlesen von Fassung {fassung} ging nicht",
                             f"TH{tid}: {aus['fehler']}\nDie Fassung wartet trotzdem auf {kern.entwickler_name(con, pid)}.")
            else:
                keine = aus["einwaende"].strip().rstrip(".").lower() == "keine einwände"
                kern._posten(con, pid, "AMW", an, "meldung" if keine else "auftrag",
                             f"Thema „{name}“: Gegenleser zu Fassung {fassung} – " + ("keine Einwände" if keine else "Einwände"),
                             f"TH{tid} Fassung {fassung}, gegengelesen ({aus.get('modell')}, {kosten}" + (f", L{lauf}" if lauf else "")
                             + f"):\n\n{aus['einwaende']}\n\n"
                             + ("" if keine else f"Neue Fassung: amw thema pflegen TH{tid} --text-datei … – oder so lassen. ")
                             + f"Die Fassung wartet jetzt auf {kern.entwickler_name(con, pid)}.")


def ausfuehren(con, pid, tid, fassung, prog=None, zusatz=None):
    """Als angemeldeter Lauf der Lauf-Schlange (leicht): warten, bis er dran ist, lesen, abschließen. Ein Fehler wird eingetragen."""
    from . import belegung, betrieb
    an = [e for e in _ereignisse(con, pid, tid, ANGESTOSSEN) if e.get("fassung") == fassung]
    modell = (an[-1].get("modell") if an else None) or MODELLE[einstellung(con, pid) if einstellung(con, pid) != "aus" else "haiku"]
    t = con.execute("SELECT * FROM thema WHERE id = ? AND projekt_id = ?", (tid, pid)).fetchone()
    agent = kern.lead(con, pid) or kern.ENTWICKLER
    lid = betrieb.lauf_start(con, pid, agent, f"Gegenlesen TH{tid} Fassung {fassung} ({modell}, A1914, automatisch)", None, False, False,
                             None, warten=True, waechter=os.getpid(), befehl=None, ordner=None, selbst=True)   # A1948: kein Weckruf
    belegung.lauf_merken(lid, os.getpid())
    name = f"TH{tid}" + (f" {t['name']}" if t else "")
    fortschritt = functools.partial(planer_fortschritt.melden_still, con, pid, lid, art="gegenlesen", thema=tid, agent=agent,
                                    modell=modell, fassung=fassung, **planer_fortschritt.vom(an[-1] if an else {}))            # A2025: Stand in der AMW, gedrosselt
    fortschritt(was=f"{name}: wartet auf einen Platz in der Lauf-Schlange",
                dauer_s=planer_fortschritt.schaetzung(con, pid, "gegenlesen"), sofort=True)
    aus = None
    try:
        while True:
            l = betrieb.lauf_zeile(con, pid, lid)
            if l["status"] == "laeuft":
                break
            if l["status"] in ("fertig", "abgebrochen"):
                raise RuntimeError(f"L{lid} ist {l['status']} – nicht gegengelesen")
            time.sleep(5)
        betrieb.lauf_uebernehmen(con, lid, "agent")
        if not t:
            raise kern.AmwFehler(f"TH{tid} gibt es nicht")
        fortschritt(was=f"{name}: Fassung {fassung} wird gegengelesen", sofort=True)
        aus = lesen(con, pid, t, fassung, modell, prog=prog, zusatz=zusatz)
    except Exception as e:                                    # noqa: BLE001 – niemand sieht die Ausgabe: als Fehler eintragen
        aus = {"einwaende": None, "usd": None, "fehler": f"{type(e).__name__}: {e}"[:300]}
    finally:
        aus = aus or {"einwaende": None, "usd": None, "fehler": "abgebrochen"}
        aus["modell"] = modell
        kosten = f"{aus['usd']:.2f} $" if isinstance(aus.get("usd"), (int, float)) else "Kosten unbekannt"
        try:
            betrieb.lauf_ende(con, pid, agent, lid, 1 if aus.get("fehler") else 0,
                              (f"Gegenlesen TH{tid} Fassung {fassung}: " + (f"Fehler – {aus['fehler']}" if aus.get("fehler") else "fertig")
                               + f" · {kosten}")[:500])
        finally:
            belegung.lauf_vergessen(lid)
    abschliessen(con, pid, tid, fassung, aus, lid)
    if aus.get("fehler"):
        fortschritt(was=f"{name}: nicht gegengelesen", usd=aus.get("usd"), zustand="fehler", fehler=aus["fehler"])
    else:
        fortschritt(was=f"{name}: gegengelesen", usd=aus.get("usd"), zustand="fertig")
    return aus


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="amw-gegenlesen")
    ap.add_argument("--projekt-id", type=int, required=True)
    ap.add_argument("--thema", type=int, required=True)
    ap.add_argument("--fassung", type=int, required=True)
    x = ap.parse_args(argv)
    con = db.verbinde()
    try:
        ausfuehren(con, x.projekt_id, x.thema, x.fassung)
    finally:
        con.close()
