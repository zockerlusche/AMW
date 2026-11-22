"""Stil-Prüfung als Automatik (A1973, Marcel W2464 #30689, Entwurf #30742, Ja #30743).

Ändert der Stand einer Prüfbitte Sichtbares (dieselbe Erkennung wie die Bild-Pflicht, pruefstufe.bilder_pruefen) und hängen
Bilder an der Aufgabe, stößt die AMW EINEN Stil-Leser an: einen frischen claude -p, nur Lesen (wie der Gegenleser, A1914),
Modell aus der Einstellung themen_gegenlesen. Er bekommt das Stil-Thema des Projekts (thema.stil = 1, geltende Fassung) und
die Bilder der Aufgabe als Dateien und urteilt Regel für Regel als JSON. Der Befund hängt als Dokument an der Aufgabe, der
Prüfer bekommt „P… Stil: 9/9 erfüllt“ bzw. „Stil: n Verstöße – R7, R3“. Grün auf eine Prüfung mit Verstoß nur mit Begründung
(pruefung gruen --bemerkung).

Ereignisse (plan_ereignis, ohne Schema):
  stil_angestossen {"pruefung", "modell", "prozess"}
  stil_befund      {"pruefung", "modell", "regeln", "verstoesse", "kleinprobe", "usd", "lauf", "fehler", "dokument"}
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

from . import db, kern

ANGESTOSSEN, BEFUND = "stil_angestossen", "stil_befund"
EINSTIEG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "amw-stil.py")
OHNE_FENSTER = getattr(subprocess, "CREATE_NO_WINDOW", 0)
REGELN = 9
AUFTRAG = ("Du prüfst Bilder einer Oberfläche gegen Stil-Regeln. Lies stil.md (die geltenden Regeln), texte.md (was diese "
           "Prüfbitte ändert – Punkte des Bauers, neue Texte) und alle Bilder in diesem Ordner (bild-*.png; der Name sagt, was es "
           "zeigt). Urteile je Regel 1 bis 9 aus dem Abschnitt „Regeln für jede Seite“ NUR über das, was diese Prüfbitte ändert "
           "(laut texte.md): erfüllt, verstößt oder nicht prüfbar (wenn die Bilder die Änderung nicht zeigen). Bei „verstößt“ nenne "
           "kurz die Stelle und das Bild. Was auf den Bildern schon vorher so war und gegen eine Regel verstößt, gehört NICHT in "
           "„verstößt“, sondern als kurze Zeile mit Regelnummer in „bestand“. Prüfe außerdem: Bringt die Änderung eine neue Ansicht "
           "oder neue Zeilen, für die laut stil.md zuerst eine Kleinprobe nötig wäre? Antworte NUR mit einem JSON-Objekt:\n"
           '{"regeln": [{"nr": 1, "urteil": "erfüllt|verstößt|nicht prüfbar", "grund": "…", "bild": "bild-….png"}], '
           '"bestand": ["R5: …"], "kleinprobe_noetig": false}\n'
           "Du änderst nichts, du schreibst keine Dateien, du führst nichts aus.")


def einstellung(con, pid):
    from . import gegenlesen
    return gegenlesen.einstellung(con, pid) or "haiku"


def modell_fuer(con, pid):
    from . import gegenlesen
    e = einstellung(con, pid)
    return gegenlesen.MODELLE.get(e if e != "aus" else "haiku", "haiku")


def stil_thema(con, pid):
    """Das Stil-Thema des Projekts (thema.stil = 1) mit geltender Fassung: (zeile, text) oder (None, None)."""
    from . import themen
    t = con.execute("SELECT * FROM thema WHERE projekt_id = ? AND stil = 1 ORDER BY id LIMIT 1", (pid,)).fetchone()
    if not t:
        return None, None
    s = themen.status(con, t)
    nr = s.get("freigegeben") or s.get("aktuell") or s.get("fassung")
    f = con.execute("SELECT text FROM thema_fassung WHERE thema_id = ? AND nr = ?", (t["id"], nr)).fetchone() if nr else None
    if not f:
        f = con.execute("SELECT text FROM thema_fassung WHERE thema_id = ? ORDER BY nr DESC LIMIT 1", (t["id"],)).fetchone()
    return t, (f["text"] if f else None)


def bilder(con, pid, aufgabe_id):
    return con.execute("SELECT id, titel FROM dokument WHERE projekt_id = ? AND bezug_art = 'aufgabe' AND bezug_id = ? AND art = 'bild'"
                       " AND status = 'aktuell' ORDER BY id", (pid, aufgabe_id)).fetchall()


def _spawn(pid, prid, umgebung=None):
    befehl = [sys.executable, "-I", "-X", "utf8", EINSTIEG, "--projekt-id", str(pid), "--pruefung", str(prid)]
    flags = (0x00000008 | 0x00000200 | OHNE_FENSTER) if os.name == "nt" else 0        # DETACHED, NEW_GROUP wie der Gegenleser
    return subprocess.Popen(befehl, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                            creationflags=flags, env=umgebung, start_new_session=os.name != "nt").pid


STARTER = _spawn             # Tests setzen eine Attrappe; tests/abschotten schaltet das Anstoßen ganz ab (AMW_STIL_AUS)


def anstossen(con, pid, prid, sichtbar):
    """Nach einer Prüfbitte, deren Stand Sichtbares ändert und an deren Aufgabe Bilder hängen. Rückgabe: Zeile oder „“."""
    if not sichtbar or os.environ.get("AMW_STIL_AUS") or einstellung(con, pid) == "aus":
        return ""
    p = con.execute("SELECT * FROM pruefung WHERE id = ? AND projekt_id = ?", (prid, pid)).fetchone()
    t, _ = stil_thema(con, pid)
    if not p or not p["aufgabe_id"] or not t or not bilder(con, pid, p["aufgabe_id"]):
        return ""
    modell = modell_fuer(con, pid)
    with db.schreiben(con):
        eid = db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=ANGESTOSSEN, aufgabe_id=p["aufgabe_id"],
                           text=json.dumps({"pruefung": prid, "modell": modell}, ensure_ascii=False))
    try:
        prozess = STARTER(pid, prid)
    except OSError as e:
        abschliessen(con, pid, prid, {"fehler": f"Stil-Leser ließ sich nicht starten: {e}", "modell": modell})
        return f"\n\nStil: Prüfung ließ sich nicht starten ({e})"
    with db.schreiben(con):
        con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?",
                    (json.dumps({"pruefung": prid, "modell": modell, "prozess": prozess}, ensure_ascii=False), eid))
    return f"\n\nStil: wird geprüft ({modell}, TH{t['id']} Regel 1–{REGELN}) – Befund folgt als Meldung"


# --- Befund lesen ------------------------------------------------------------------------------------------------------------

URTEILE = ("erfüllt", "verstößt", "nicht prüfbar")


def befund_lesen(text):
    """JSON aus der Antwort (auch in ```-Blöcken) → {"regeln": [{nr, urteil, grund, bild}], "kleinprobe": bool}; ValueError."""
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        raise ValueError("kein JSON in der Antwort")
    d = json.loads(m.group(0))
    regeln = []
    for r in d.get("regeln") or []:
        u = str(r.get("urteil") or "").strip().lower()
        if u not in URTEILE:
            raise ValueError(f"Urteil „{u}“ unbekannt")
        regeln.append({"nr": int(r.get("nr")), "urteil": u, "grund": str(r.get("grund") or "")[:300], "bild": str(r.get("bild") or "")[:80]})
    if sorted(x["nr"] for x in regeln) != list(range(1, REGELN + 1)):
        raise ValueError(f"nicht genau die Regeln 1–{REGELN}")
    bestand = [str(x)[:200] for x in (d.get("bestand") or []) if str(x).strip()][:12]
    return {"regeln": sorted(regeln, key=lambda x: x["nr"]), "kleinprobe": bool(d.get("kleinprobe_noetig")), "bestand": bestand}


def zeile(befund):
    v = [r for r in befund["regeln"] if r["urteil"] == "verstößt"]
    n = [r for r in befund["regeln"] if r["urteil"] == "nicht prüfbar"]
    erfuellt = REGELN - len(v) - len(n)
    text = (f"Stil: {len(v)} " + ("Verstoß" if len(v) == 1 else "Verstöße") + " – " + ", ".join(f"R{r['nr']}" for r in v)) if v \
        else f"Stil: {erfuellt}/{REGELN} erfüllt"
    if n and not v:
        text += " · nicht prüfbar: " + ", ".join(f"R{r['nr']}" for r in n)
    return text + (" · Kleinprobe nötig?" if befund.get("kleinprobe") else "")


def bericht(prid, befund, modell, usd):
    zeilen = [f"# Stil-Befund zu P{prid}", "", zeile(befund), "", f"Modell {modell}" + (f", {usd:.2f} $" if isinstance(usd, (int, float)) else ""), ""]
    for r in befund["regeln"]:
        zeilen.append(f"- **R{r['nr']} {r['urteil']}**" + (f" – {r['grund']}" if r["grund"] else "") + (f" ({r['bild']})" if r["bild"] else ""))
    if befund.get("bestand"):
        zeilen += ["", "Schon vorher so (alter Bestand, zählt hier nicht – eigenes Stil-Paket):"] + [f"- {x}" for x in befund["bestand"]]
    if befund.get("kleinprobe"):
        zeilen += ["", "Hinweis: neue Ansicht oder neue Zeilen – laut Stil-Thema zuerst als Kleinprobe (G4)."]
    return "\n".join(zeilen) + "\n"


# --- der Lauf -------------------------------------------------------------------------------------------------------------

def _dateien(con, pid, p, ordner):
    from . import dokumente
    t, text = stil_thema(con, pid)
    if not t or not text:
        raise kern.AmwFehler("Kein Stil-Thema mit Fassung im Projekt")
    with open(os.path.join(ordner, "stil.md"), "w", encoding="utf-8", newline="\n") as f:
        f.write(f"# {t['name']} (TH{t['id']})\n\n{text}\n")
    if p["punkte"]:
        with open(os.path.join(ordner, "texte.md"), "w", encoding="utf-8", newline="\n") as f:
            f.write(f"# Punkte der Prüfbitte P{p['id']}\n\n{p['punkte']}\n")
    namen = []
    for b in bilder(con, pid, p["aufgabe_id"]):
        v = dokumente.dokument(con, pid, b["id"])["versionen"][-1]
        name = "bild-D{}-{}{}".format(b["id"], re.sub(r"[^\w-]+", "-", b["titel"])[:40].strip("-"), v["endung"])
        shutil.copyfile(dokumente.datei_pfad(v["sha256"], v["endung"]), os.path.join(ordner, name))
        namen.append(name)
    return namen


def lesen(con, pid, p, modell, prog=None, zusatz=None):
    from . import arbeiter, gegenlesen, platz, versionsprobe
    with tempfile.TemporaryDirectory(prefix="amw-stil-", ignore_cleanup_errors=True) as ordner:
        pf = platz.pfade(os.path.join(ordner, "plaetze"), 1)
        os.makedirs(pf["klon"])
        subprocess.run(["git", "init", "-q", "-b", "main", pf["klon"]], check=True, capture_output=True, creationflags=OHNE_FENSTER)
        namen = _dateien(con, pid, p, pf["klon"])
        r = arbeiter.laufen(pf, AUFTRAG + "\n\nBilder: " + ", ".join(namen), None, modell=modell,
                            effort=gegenlesen.EFFORT.get(modell, "low"), prog=prog, zusatz=zusatz, nur_lesen=True,
                            geprueft=versionsprobe.geprueft(con))
    erg = r.get("ergebnis") or {}
    usd = erg.get("total_cost_usd")
    if r.get("abweichungen"):
        return {"fehler": "; ".join(r["abweichungen"])[:500], "usd": usd}
    if r.get("rc") != 0 or erg.get("is_error"):
        return {"fehler": r.get("fehler") or f"kein Ergebnis (rc {r.get('rc')})", "usd": usd}
    try:
        return {"befund": befund_lesen(erg.get("result")), "usd": usd}
    except (ValueError, TypeError) as e:
        return {"fehler": f"Antwort nicht lesbar: {e}", "usd": usd}


def abschliessen(con, pid, prid, aus, lauf=None):
    """Befund eintragen, als Dokument an die Aufgabe, Meldung an den Prüfer – auch ein Fehler (dann prüft der Prüfer selbst)."""
    from . import dokumente
    p = con.execute("SELECT * FROM pruefung WHERE id = ? AND projekt_id = ?", (prid, pid)).fetchone()
    befund, did = aus.get("befund"), None
    if befund and p and p["aufgabe_id"]:
        with tempfile.TemporaryDirectory(prefix="amw-stil-bericht-", ignore_cleanup_errors=True) as d:
            pfad = os.path.join(d, f"stil-P{prid}.md")
            with open(pfad, "w", encoding="utf-8", newline="\n") as f:
                f.write(bericht(prid, befund, aus.get("modell"), aus.get("usd")))
            did = dokumente.ablegen(con, pid, "AMW", pfad, titel=f"Stil-Befund P{prid}: {zeile(befund)}"[:120], art="bericht",
                                    aufgabe=p["aufgabe_id"])
    verstoesse = [r["nr"] for r in (befund or {}).get("regeln", []) if r["urteil"] == "verstößt"]
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=BEFUND,
                     aufgabe_id=p["aufgabe_id"] if p else None,
                     text=json.dumps({"pruefung": prid, "modell": aus.get("modell"), "regeln": (befund or {}).get("regeln"),
                                      "verstoesse": verstoesse, "kleinprobe": (befund or {}).get("kleinprobe"), "usd": aus.get("usd"),
                                      "lauf": lauf, "fehler": aus.get("fehler"), "dokument": did}, ensure_ascii=False))
        if p:
            kurz = f"P{prid} " + (zeile(befund) if befund else "Stil-Prüfung ging nicht – bitte selbst nach TH156 prüfen")
            kern._posten(con, pid, "AMW", p["pruefer"], "meldung", kurz[:140],
                         (bericht(prid, befund, aus.get("modell"), aus.get("usd")) + (f"\nDokument D{did}" if did else "")) if befund
                         else f"{aus.get('fehler')}", aufgabe_id=p["aufgabe_id"])


def letzter_befund(con, pid, prid):
    for (t,) in con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id DESC", (pid, BEFUND)):
        try:
            e = json.loads(t or "{}")
        except ValueError:
            continue
        if e.get("pruefung") == prid:
            return e
    return None


def gruen_pruefen(con, pid, prid, bemerkung):
    """Grün auf eine Prüfung mit Stil-Verstoß nur mit Begründung (--bemerkung)."""
    e = letzter_befund(con, pid, prid)
    if e and e.get("verstoesse") and not (bemerkung or "").strip():
        raise kern.AmwFehler(f"P{prid} hat Stil-Verstöße ({', '.join('R' + str(n) for n in e['verstoesse'])}) – Grün nur mit Begründung:"
                             f" amw pruefung gruen {prid} --bemerkung \"warum es trotzdem passt\"")


def ausfuehren(con, pid, prid, prog=None, zusatz=None):
    from . import belegung, betrieb
    p = con.execute("SELECT * FROM pruefung WHERE id = ? AND projekt_id = ?", (prid, pid)).fetchone()
    modell = modell_fuer(con, pid)
    agent = kern.lead(con, pid) or kern.ENTWICKLER
    lid = betrieb.lauf_start(con, pid, agent, f"Stil-Prüfung P{prid} ({modell}, A1973, automatisch)", None, False, False,
                             p["aufgabe_id"] if p else None, warten=True, waechter=os.getpid(), befehl=None, ordner=None, selbst=True)
    belegung.lauf_merken(lid, os.getpid())
    aus = None
    try:
        while True:
            l = betrieb.lauf_zeile(con, pid, lid)
            if l["status"] == "laeuft":
                break
            if l["status"] in ("fertig", "abgebrochen"):
                raise RuntimeError(f"L{lid} ist {l['status']} – nicht geprüft")
            time.sleep(5)
        betrieb.lauf_uebernehmen(con, lid, "agent")
        if not p:
            raise kern.AmwFehler(f"P{prid} gibt es nicht")
        aus = lesen(con, pid, p, modell, prog=prog, zusatz=zusatz)
    except Exception as e:                                    # noqa: BLE001 – niemand sieht die Ausgabe: als Fehler eintragen
        aus = {"fehler": f"{type(e).__name__}: {e}"[:300]}
    finally:
        aus = aus or {"fehler": "abgebrochen"}
        aus["modell"] = modell
        kosten = f"{aus['usd']:.2f} $" if isinstance(aus.get("usd"), (int, float)) else "Kosten unbekannt"
        try:
            betrieb.lauf_ende(con, pid, agent, lid, 1 if aus.get("fehler") else 0,
                              (f"Stil-Prüfung P{prid}: " + (f"Fehler – {aus['fehler']}" if aus.get("fehler") else zeile(aus["befund"]))
                               + f" · {kosten}")[:500])
        finally:
            belegung.lauf_vergessen(lid)
    abschliessen(con, pid, prid, aus, lid)
    return aus


def main(argv=None):
    import argparse
    ap = argparse.ArgumentParser(prog="amw-stil")
    ap.add_argument("--projekt-id", type=int, required=True)
    ap.add_argument("--pruefung", type=int, required=True)
    x = ap.parse_args(argv)
    con = db.verbinde()
    try:
        ausfuehren(con, x.projekt_id, x.pruefung)
    finally:
        con.close()
