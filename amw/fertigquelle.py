"""Fertig-Quelle je Aufgabe und Prüfquelle je Kriterium (A1938, K2; TH155 Punkte 2, 3, 6; TH165; Entwurf #30214, Antwort #30215).

Die AMW schließt Aufgaben, hakt Kriterien ab und schreibt Beleg und Zusammenfassung selbst – Agenten liefern nur Fakten (B2907).
Ohne Schemaänderung: die Fertig-Quelle steht als Ereignis fertig_quelle (das neueste gilt), die Prüfquelle als Feld „quelle“
im Kriterium (aufgabe.kriterien ist schon eine JSON-Liste).

Fertig-Quellen (`amw aufgabe neu|aendern N --fertig-wenn …`):
- commit: wie bisher – die Kette setzt fertig beim Release (planautomatik.ausgeliefert).
- thema TH<n>: fertig, sobald das Thema freigegeben ist (auch durch Co und Lead, K1).
- frist <Tage> nach <Version>: fertig, wenn seit dem Release der Version so viele Tage vergangen sind und es seitdem keinen
  Fehler gab: kein Revert eines Commits der Aufgabe in main, keine neue „behoben“-Aufgabe, die auf sie verweist, keine rote
  Prüfung der Aufgabe. (Ein roter Gesamtlauf auf main wird nicht eigens gezählt – nicht billig zuzuordnen.)
- ja: nie automatisch – das Urteil kommt über „bereit zur Abnahme“ (K3).
Ohne Fertig-Quelle bleibt alles wie bisher.

Prüfquellen je Kriterium (`amw aufgabe kriterium N nr --quelle …`), geprüft seit Beginn der Aufgabe:
- lauf <Befehl>: ein Lauf der Lauf-Schlange zur Aufgabe mit genau diesem Befehl (wörtlich nach Leerzeichen-Normalisierung),
  rc 0. Der Dienst führt nie selbst einen Befehl aus (TH169) – er liest nur das Ergebnis.
- pruefung: eine grüne Prüfung der Aufgabe.
- thema TH<n>: das Thema ist freigegeben.
- tests <N>: ein Lauf zur Aufgabe mit rc 0, dessen Ergebnis „Ran ≥ N tests“ zeigt.
Ohne Quelle bleibt ein Kriterium ein Ja des Leads (amw aufgabe kriterium N nr). Ist die Fertig-Quelle eingetreten und nur
noch so ein Kriterium offen, schließt die AMW nicht: sie fragt den Lead einmal je Stand („bereit zur Abnahme – Ja des Leads
fehlt für: …“) und schließt in der Runde nach seinem Ja (P429).
"""
import datetime
import json
import os
import re
import subprocess

from . import db, kern

ART = "fertig_quelle"
ABGEHAKT = "kriterium_abgehakt"
WARTET_JA = "fertig_wartet_ja"     # P429: Fertig-Quelle eingetreten, aber ein Kriterium ohne Quelle offen – einmal je Stand gemeldet
AUTO = "AMW"
_ZULETZT = {"t": 0.0}
TAKT_S = 900                      # die Dienst-Runde prüft höchstens alle 15 Minuten


def _norm(s):
    return " ".join(str(s or "").split())


def quelle_lesen(text):
    """Fertig-Quelle aus Text: commit | thema TH12 | frist 7 nach 1.160.0 | ja → dict; ValueError mit Hinweis."""
    t = _norm(text).lower()
    if t in ("commit", "ja"):
        return {"art": t}
    m = re.fullmatch(r"thema\s+th(\d+)", t)
    if m:
        return {"art": "thema", "thema": int(m.group(1))}
    m = re.fullmatch(r"frist\s+(\d{1,3})\s+nach\s+v?(\d+\.\d+\.\d+)", t)
    if m and 1 <= int(m.group(1)) <= 365:
        return {"art": "frist", "tage": int(m.group(1)), "version": m.group(2)}
    raise ValueError("Fertig-Quelle: commit | thema TH<n> | frist <Tage> nach <Version> | ja")


def pruefquelle_lesen(text):
    """Prüfquelle eines Kriteriums: lauf <Befehl> | pruefung | thema TH12 | tests <N> → dict; ValueError."""
    roh = _norm(text)
    t = roh.lower()
    if t == "pruefung":
        return {"art": "pruefung"}
    m = re.fullmatch(r"thema\s+th(\d+)", t)
    if m:
        return {"art": "thema", "thema": int(m.group(1))}
    m = re.fullmatch(r"tests\s+(\d{1,6})", t)
    if m:
        return {"art": "tests", "mindestens": int(m.group(1))}
    if t.startswith("lauf ") and len(roh) > 5:
        return {"art": "lauf", "befehl": roh[5:].strip()}
    raise ValueError("Prüfquelle: lauf <Befehl> | pruefung | thema TH<n> | tests <N>")


def _darf(con, pid, von, a):
    return von == kern.ENTWICKLER or kern.ist_lead(con, pid, von) or von == a["agent"]


def setzen(con, pid, von, aid, text):
    """Fertig-Quelle setzen – Lead, Mensch oder Bearbeiter der Aufgabe. Ereignis (das neueste gilt)."""
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a:
        raise kern.AmwFehler(f"A{aid} gibt es nicht")
    if not _darf(con, pid, von, a):
        raise kern.AmwFehler("Die Fertig-Quelle setzen Lead, Mensch oder der Bearbeiter der Aufgabe")
    try:
        q = quelle_lesen(text)
    except ValueError as e:
        raise kern.AmwFehler(str(e)) from None
    if q["art"] == "thema":
        from . import themen
        themen.finden(con, pid, q["thema"])                      # gibt es das Thema?
    with db.schreiben(con):
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=ART, aufgabe_id=aid,
                     text=json.dumps(q, ensure_ascii=False))
    return q


def lesen(con, aid):
    r = con.execute("SELECT text FROM plan_ereignis WHERE aufgabe_id = ? AND art = ? ORDER BY id DESC LIMIT 1", (aid, ART)).fetchone()
    try:
        return json.loads(r[0]) if r else None
    except ValueError:
        return None


def text(q):
    if not q:
        return "–"
    return {"commit": "commit (beim Release)", "ja": "ja (Urteil)", "thema": f"thema TH{q.get('thema')} freigegeben",
            "frist": f"frist {q.get('tage')} Tage nach {q.get('version')} ohne Fehler"}.get(q["art"], q["art"])


def pruefquelle_setzen(con, pid, von, aid, nr, quelle):
    """Prüfquelle für Kriterium nr – Lead, Mensch oder Bearbeiter. „“ entfernt sie."""
    from . import planung
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a:
        raise kern.AmwFehler(f"A{aid} gibt es nicht")
    if not _darf(con, pid, von, a):
        raise kern.AmwFehler("Prüfquellen setzen Lead, Mensch oder der Bearbeiter der Aufgabe")
    liste = planung._json(a["kriterien"], [])
    if not 1 <= nr <= len(liste):
        raise kern.AmwFehler(f"A{aid} hat {len(liste)} Kriterien")
    if _norm(quelle):
        try:
            liste[nr - 1]["quelle"] = pruefquelle_lesen(quelle)
        except ValueError as e:
            raise kern.AmwFehler(str(e)) from None
    else:
        liste[nr - 1].pop("quelle", None)
    with db.schreiben(con):
        con.execute("UPDATE aufgabe SET kriterien = ?, geaendert_utc = ? WHERE id = ?", (json.dumps(liste, ensure_ascii=False), db.jetzt(), aid))
    return liste


# --- prüfen ------------------------------------------------------------------------------------------------------------------

def _seit(a):
    return a["begonnen_utc"] or a["angelegt_utc"]


def _thema_frei(con, pid, tid):
    from . import themen
    try:
        t = themen.finden(con, pid, tid)
    except kern.AmwFehler:
        return None
    s = themen.status(con, t)
    return s if s["status"] == "frei" else None


def kriterium_erfuellt(con, pid, a, q):
    """Beleg (Text) oder None."""
    seit = _seit(a)
    if q["art"] == "pruefung":
        r = con.execute("SELECT id, sha FROM pruefung WHERE aufgabe_id = ? AND ergebnis = 'gruen' AND COALESCE(ergebnis_utc, angefragt_utc) >= ?"
                        " ORDER BY id DESC LIMIT 1", (a["id"], seit)).fetchone()
        return f"P{r['id']} grün auf {r['sha'][:8]}" if r else None
    if q["art"] == "thema":
        s = _thema_frei(con, pid, q["thema"])
        return f"TH{q['thema']} Fassung {s['freigegeben']} freigegeben" if s else None
    if q["art"] in ("lauf", "tests"):
        for r in con.execute("SELECT id, befehl, ergebnis, ergebnis_datei FROM lauf WHERE aufgabe_id = ? AND status = 'fertig' AND rc = 0"
                             " AND COALESCE(ende_utc, angemeldet_utc) >= ? ORDER BY id DESC", (a["id"], seit)).fetchall():
            if q["art"] == "lauf":
                try:
                    befehl = " ".join(json.loads(r["befehl"] or "[]"))
                except (ValueError, TypeError):
                    continue
                if _norm(befehl) == _norm(q["befehl"]):
                    return f"L{r['id']} rc 0"
            else:
                n = _tests(r)
                if n is not None and n >= q["mindestens"]:
                    return f"L{r['id']}: {n} Tests, rc 0"
    return None


def _tests(lauf):
    teile = [lauf["ergebnis"] or ""]
    if lauf["ergebnis_datei"] and os.path.isfile(lauf["ergebnis_datei"]):
        try:
            with open(lauf["ergebnis_datei"], encoding="utf-8", errors="replace") as f:
                teile.append(f.read()[-20000:])
        except OSError:
            pass
    zahlen = [int(x) for x in re.findall(r"^Ran (\d+) tests? in", "\n".join(teile), re.M)]
    return max(zahlen) if zahlen else None


def _release_zeit(con, pid, version):
    r = con.execute("SELECT zeit_utc FROM release WHERE projekt_id = ? AND art = 'version' AND version = ? ORDER BY id LIMIT 1",
                    (pid, version)).fetchone()
    return r[0] if r else None


def _git(ordner, *args):
    try:
        r = subprocess.run(["git", "-C", ordner, *args], capture_output=True, text=True, encoding="utf-8", errors="replace",
                           timeout=60, stdin=subprocess.DEVNULL, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    except (OSError, subprocess.TimeoutExpired):
        return None
    return r.stdout if r.returncode == 0 else None


def frist_fehler(con, pid, a, seit):
    """Fehler seit dem Release (Texte) – Revert, „behoben“-Aufgabe mit Verweis, rote Prüfung der Aufgabe."""
    aus = []
    aid = a["id"]
    ordner = kern.projekt_ordner(con, pid)
    if ordner:
        eigene = (_git(ordner, "log", "main", "--format=%H", f"--grep=^A{aid}[: (]", "-E") or "").split()
        if eigene:
            log = _git(ordner, "log", "main", f"--since={seit}", "--format=%H %s%n%b") or ""
            for sha in eigene:
                if f"This reverts commit {sha}" in log:
                    aus.append(f"Revert von {sha[:8]} in main")
    for r in con.execute("SELECT id FROM aufgabe WHERE projekt_id = ? AND hinweis_gruppe = 'behoben' AND angelegt_utc >= ? AND id != ?"
                         " AND (titel LIKE ? OR auftrag LIKE ?)", (pid, seit, aid, f"%A{aid}%", f"%A{aid}%")).fetchall():
        aus.append(f"A{r['id']} behebt einen Fehler darin")
    for r in con.execute("SELECT id FROM pruefung WHERE aufgabe_id = ? AND ergebnis = 'rot' AND COALESCE(ergebnis_utc, angefragt_utc) >= ?",
                         (aid, seit)).fetchall():
        aus.append(f"P{r['id']} rot")
    return aus


def fertig_wenn(con, pid, a, q, jetzt=None):
    """(Beleg, Zusammenfassung) wenn die Fertig-Quelle eingetreten ist, sonst None. commit und ja: nie hier."""
    if q["art"] == "thema":
        s = _thema_frei(con, pid, q["thema"])
        if s:
            return (f"TH{q['thema']} Fassung {s['freigegeben']}",
                    f"Fertig: Thema TH{q['thema']} ist freigegeben (Fassung {s['freigegeben']}) – die AMW hat die Aufgabe geschlossen.")
    if q["art"] == "frist":
        seit = _release_zeit(con, pid, q["version"])
        if not seit:
            return None
        t0 = db.utc_lesen(seit)
        jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
        if jetzt - t0 < datetime.timedelta(days=q["tage"]) or frist_fehler(con, pid, a, seit):
            return None
        return (f"{q['version']} + {q['tage']} Tage",
                f"Fertig: {q['tage']} Tage nach {q['version']} ohne Revert, ohne Fehler-Aufgabe und ohne rote Prüfung – von der AMW"
                " geschlossen.")
    return None


def runde(con, jetzt=None, immer=False):
    """Dienst-Runde (höchstens alle TAKT_S): Kriterien mit Prüfquelle abhaken, Aufgaben mit eingetretener Fertig-Quelle
    schließen. Rückgabe: Texte fürs Protokoll."""
    import time
    from . import planung
    if not immer and time.monotonic() - _ZULETZT["t"] < TAKT_S:
        return []
    _ZULETZT["t"] = time.monotonic()
    aus = []
    for a in con.execute("SELECT * FROM aufgabe WHERE status NOT IN ('fertig', 'verworfen') AND (kriterien LIKE '%\"quelle\"%'"
                         " OR id IN (SELECT aufgabe_id FROM plan_ereignis WHERE art = ?))", (ART,)).fetchall():
        pid = a["projekt_id"]
        liste = planung._json(a["kriterien"], [])
        geaendert = []
        for i, k in enumerate(liste, 1):
            if k.get("quelle") and not k.get("erfuellt"):
                beleg = kriterium_erfuellt(con, pid, a, k["quelle"])
                if beleg:
                    k["erfuellt"], k["beleg"] = True, beleg
                    geaendert.append((i, k["text"], beleg))
        if geaendert:
            with db.schreiben(con):
                con.execute("UPDATE aufgabe SET kriterien = ?, geaendert_utc = ? WHERE id = ?",
                            (json.dumps(liste, ensure_ascii=False), db.jetzt(), a["id"]))
                for i, t, beleg in geaendert:
                    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=AUTO, art=ABGEHAKT, aufgabe_id=a["id"],
                                 text=json.dumps({"nr": i, "text": t[:200], "beleg": beleg}, ensure_ascii=False))
            aus += [f"A{a['id']}: Kriterium {i} abgehakt ({b})" for i, _, b in geaendert]
        q = lesen(con, a["id"])
        ergebnis = fertig_wenn(con, pid, a, q, jetzt) if q else None
        if ergebnis:
            beleg, zusammen = ergebnis
            if any(k.get("quelle") and not k.get("erfuellt") for k in liste):
                continue                                 # ein Fakt fehlt noch – die nächste Runde sieht wieder nach
            offen = [k["text"] for k in liste if not k.get("erfuellt")]
            if offen:                                    # P429 (TH155 Pkt 3): ein offenes Urteil wird nie übergangen
                stand = json.dumps(offen, ensure_ascii=False)
                if not con.execute("SELECT 1 FROM plan_ereignis WHERE aufgabe_id = ? AND art = ? AND text = ?",
                                   (a["id"], WARTET_JA, stand)).fetchone():
                    an = kern.lead(con, pid) or kern.ENTWICKLER
                    nummern = [i for i, k in enumerate(liste, 1) if not k.get("erfuellt")]
                    with db.schreiben(con):
                        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=AUTO, art=WARTET_JA, aufgabe_id=a["id"],
                                     text=stand)
                        kern._posten(con, pid, AUTO, an, "frage", f"A{a['id']} bereit zur Abnahme – Ja des Leads fehlt für: "
                                     + " | ".join(offen[:3])[:100],
                                     f"{beleg}: die Fertig-Quelle ist eingetreten, offen sind nur noch Kriterien ohne Prüfquelle. Ja je"
                                     " Kriterium: " + ", ".join(f"amw aufgabe kriterium {a['id']} {n}" for n in nummern)
                                     + " – danach schließt die AMW die Aufgabe selbst.", aufgabe_id=a["id"])
                    aus.append(f"A{a['id']}: wartet auf das Ja des Leads ({len(offen)} Kriterien)")
                continue
            kern.aufgabe_status(con, pid, AUTO, a["id"], "fertig", beleg=beleg, zusammenfassung=zusammen, automatik=True)
            lead = kern.lead(con, pid)
            if lead or a["agent"]:
                with db.schreiben(con):
                    for k in dict.fromkeys(x for x in (a["agent"], lead) if x and x != kern.ENTWICKLER):
                        kern._posten(con, pid, AUTO, k, "info", f"A{a['id']} fertig – {beleg}"[:140], zusammen, aufgabe_id=a["id"])
            aus.append(f"A{a['id']}: fertig ({beleg})")
    return aus
