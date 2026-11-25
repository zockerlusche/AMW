"""A2031 (TH164 F2 Schritt 3, TL #31457 a): rollende Feinplanung – kein Stillstand zwischen Meilensteinen.

Voll geplant wird immer nur der nächste Meilenstein. Die AMW stößt seine Feinplanung selbst an:
- nach dem Grobplan, solange noch kein Meilenstein läuft: für den ersten,
- sobald der laufende Meilenstein „bereit zur Abnahme“ ist (A2002) oder nur noch sein letztes Paket läuft: für den nächsten.
Der Mensch gibt den Plan von M(n+1) frei, während M(n) noch auf seine Abnahme wartet. Das Ja zum Feinplan ist zugleich der
Start (plan_starten): freigeben und – sobald frei – den Meilenstein an den Disponenten übergeben (reihenfolge.starten).

„Nächster“ = der geplante Meilenstein mit der kleinsten Nummer, dessen Grob-Freigabe steht und der noch keine Pakete hat.
Meilensteine, die laut Grobplan „gleichzeitig mit“ ihm laufen dürfen (grobplan_ja, A2030), werden zusammen fein geplant – in
einem Lauf, damit Abhängigkeiten zwischen ihnen sichtbar werden. Einmal je Meilenstein (plan_ereignis FAELLIG).

Der Feinplaner ist ein frischer claude -p (headless, nur Lesen, gründliches Modell) als angemeldeter Lauf der Lauf-Schlange –
das Muster von grobplan.py. Er liest Meilenstein(e), ihre Themen, Beschlüsse, die übrigen Meilensteine, offene und fertige
Pakete und liefert Pakete nach dem Paket-Schema von planer.py (zusätzlich je Paket sein Thema). Die AMW prüft den Entwurf
(planer.pruefen: Schema, p-Regeln, Abnahme-Befehl, gesperrte Bereiche, kein Kreis; dazu: Thema gehört zum Meilenstein, nichts
schon Gebautes) und legt die Pakete gleich an (Status wartet, nichts startet). Der Plan wartet dann auf das Ja – „Plan freigeben
und starten“. „Überarbeiten lassen“ (neu_planen mit Hinweis) plant eine neue Fassung; die nicht begonnenen Pakete der vorigen
Fassung werden verworfen (nie gelöscht). Fragen des Planers gehen an den Lead (A2021). Kosten zählen zur gemeinsamen
Tagesgrenze der Planer (planer.heute_usd), der Fortschritt erscheint wie bei den anderen Planern (A2025, Art „feinplaner“).

Ereignisse (plan_ereignis, ohne Schemaänderung, Text JSON):
  feinplan_faellig      {"bogen", "nr", "anlass"}                                    – einmal je Meilenstein
  feinplan_angestossen  {"boegen", "fassung", "modell", "hinweis", "prozess"}
  feinplan_entwurf      {"boegen", "fassung", "modell", "usd", "lauf", "entwurf", "angelegt"} | {…, "fehler"}

Schema des Feinplans (JSON):
  {"pakete": [{"schluessel": "P1", "meilenstein": "M7", "thema": "TH12", "titel": "…", "auftrag": "…", "groesse": "S|M|L|XL",
               "art": "text|mechanisch|fehlersuche|oberflaeche|sicherheit|konzept", "ausfuehrung": "agent|p",
               "modell": "haiku|sonnet|opus", "effort": "low|medium|high", "fertig_quelle": "commit|release|thema|dokument|frist|ja",
               "nach": ["P0", "A1234"], "abnahme_befehl": "python -m unittest tests.test_x" | null,
               "bereiche": "amw/x.py, tests/test_x.py" | null, "pakettyp": "normal|test-schreiben|test-ergaenzen" | null,
               "interaktiv_grund": "…" | null, "lead_liest": true | false}],
   "fragen": [{"frage": "…", "optionen": {"A": "…", "B": "…"}, "empfehlung": "A", "grund": "…"}],
   "grund": "warum dieser Schnitt und diese Reihenfolge"}

  "meilenstein" ist die Nummer eines der zu planenden Meilensteine (M7), "thema" eines seiner Themen. Jeder dieser Meilensteine
  bekommt mindestens ein Paket. p ist die Vorgabe (A2004): ein Paket der Größe S – oder M bei Art mechanisch –, das keine
  Oberfläche ist, läuft mit "ausfuehrung": "p", mit "abnahme_befehl" und engen "bereiche"; "agent" nur mit "interaktiv_grund".
  "lead_liest": true bei Urteils-Arbeit (Konzepttexte, Architektur) – das Paket nimmt die AMW nie selbst ab (A2054).
  "nach": erst wenn das andere Paket gemergt ist. Die Arbeitsschritte im Paket plant niemand vorher.
"""
import datetime
import functools
import json
import os
import re
import subprocess
import sys
import tempfile
import time

from . import db, kern

FAELLIG = "feinplan_faellig"        # plan_ereignis.art – {"bogen", "nr", "anlass"}, einmal je Meilenstein
ANGESTOSSEN, ENTWURF = "feinplan_angestossen", "feinplan_entwurf"
FORTSCHRITT = "feinplaner"          # planer_fortschritt.art
MODELL, EFFORT = "opus", "high"     # TH164: gründliches Modell (Einstellung je Projekt kommt mit den Freigaben, A2032)
FRIST_S = 20 * 60
LAEUFT_H = 6
MAX_FRAGEN = 5
SCHEMA_TEXT = (__doc__ or "")[(__doc__ or "").find("Schema des Feinplans"):].strip()
_TH = re.compile(r"\bTH(\d+)\b")

AUFTRAG = (
    "Du bist der Planer eines Software-Projekts und machst die Feinplanung für den nächsten Meilenstein (oder die Meilensteine, "
    "die gleichzeitig laufen dürfen). Lies meilenstein.md (was zu planen ist: Ziel, fertig wenn, Themen), jede Datei unter "
    "themen/, beschluesse.md, meilensteine.md (der ganze Grobplan), pakete.md (offene Pakete), gebaut.md (fertige Pakete zu "
    "diesen Themen – nichts davon noch einmal planen), hinweise.md (Hinweise des Menschen, falls vorhanden), sperrliste.md (Pfade, "
    "die ein p-Paket nie ändern darf), befehle.md (Befehle, die als Abnahme-Befehl gesperrt sind – kein python -c, nichts Verkettetes) und schema.md (das Antwort-Format). Zerlege jeden Meilenstein in Arbeitspakete: je Paket Ziel (auftrag), Thema, Dateien (bereiche), Abnahme "
    "mit Prüfbefehl, Abhängigkeiten (nach), Größe und Art, und die Entscheidung, wer es ausführt: p (headless) ist die Vorgabe "
    "für kleine Pakete ohne Oberfläche, sonst ein Agent im Fenster mit Grund; Modell und Denkstufe nur, wenn sie von der "
    "Empfehlung abweichen sollen. Ein p-Paket nennt in bereiche nie einen Pfad aus sperrliste.md: Testdateien (tests/…) nur mit "
    "pakettyp test-schreiben oder test-ergaenzen; braucht ein Paket andere gesperrte Pfade, läuft es als agent mit interaktiv_grund "
    "„gesperrter Bereich“ (A2067). Pakete, die gleichzeitig laufen, ändern nie dieselben Dateien. Die Arbeitsschritte im Paket "
    "planst du nicht. Unklares, das den Schnitt ändert, stellst du als Frage mit Optionen, Empfehlung und Grund. Antworte NUR "
    "mit dem JSON-Objekt nach schema.md – kein Text davor oder danach. Du änderst nichts, du schreibst keine Dateien, du führst "
    "nichts aus.")


# --- Wann fein planen ------------------------------------------------------------------------------------------------------

def _zustaende(con, pid):
    from . import planansicht
    return planansicht._zustaende(con, pid)


def _grob_offen(con, pid):
    z = _zustaende(con, pid)
    return any(not (z.get((r[0], "grob")) or {}).get("an")
               for r in con.execute("SELECT id FROM bogen WHERE projekt_id = ? AND status = 'geplant'", (pid,)))


def _offene(con, bid):
    return [r[0] for r in con.execute("SELECT status FROM aufgabe WHERE bogen_id = ? AND status NOT IN ('fertig', 'verworfen')", (bid,))]


def _hat_pakete(con, bid):
    return bool(con.execute("SELECT 1 FROM aufgabe WHERE bogen_id = ? AND status != 'verworfen' LIMIT 1", (bid,)).fetchone())


def letztes_laeuft(con, bid):
    """Nur noch laufende Pakete offen (mindestens eins) – nichts wartet mehr auf einen Start."""
    offen = _offene(con, bid)
    return bool(offen) and all(s == "laeuft" for s in offen)


def anlass(con, pid):
    """Warum jetzt fein planen? „erster“ (kein Meilenstein läuft), „bereit“ (der laufende ist bereit zur Abnahme), „letztes“
    (sein letztes Paket läuft) – oder None, solange ein laufender noch Pakete vor sich hat."""
    from . import planautomatik
    aktiv = con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status = 'aktiv' ORDER BY nr, id", (pid,)).fetchall()
    if not aktiv:
        return "erster"
    for b in aktiv:
        if not (planautomatik.bereit_zur_abnahme(con, b) or letztes_laeuft(con, b["id"])):
            return None                              # ein laufender hat noch Arbeit vor sich – nicht vorplanen
    return "bereit" if all(planautomatik.bereit_zur_abnahme(con, b) for b in aktiv) else "letztes"


def naechster(con, pid):
    """Der nächste Meilenstein, der fein geplant werden muss (Zeile) – oder None. Der Reihe nach (Nummer): steht davor ein
    Meilenstein, dessen Grob-Freigabe fehlt oder dessen Plan noch auf das Ja wartet, wird nichts vorgeplant."""
    z = _zustaende(con, pid)
    for b in con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status = 'geplant' ORDER BY nr, id", (pid,)).fetchall():
        if not (z.get((b["id"], "grob")) or {}).get("an"):
            return None                              # erst wenn sein Meilenstein freigegeben ist
        if not _hat_pakete(con, b["id"]):
            return b
        if not (z.get((b["id"], "plan")) or {}).get("an"):
            return None                              # ein Plan wartet schon auf das Ja – nur der nächste ist voll geplant
    return None


def gruppe(con, pid, b):
    """Der Meilenstein und die, die laut Grobplan gleichzeitig mit ihm laufen dürfen und noch fein zu planen sind (geplant,
    Grob-Freigabe, ohne Pakete) – Zeilen, nach Nummer."""
    from . import grobplan
    ja = grobplan.angenommen(con, pid) or {}
    gleich = ja.get("gleichzeitig") or {}
    nrs = {f"M{b['nr']}"} | set(gleich.get(f"M{b['nr']}") or []) | {k for k, v in gleich.items() if f"M{b['nr']}" in (v or [])}
    z = _zustaende(con, pid)
    aus = [b]
    for x in con.execute("SELECT * FROM bogen WHERE projekt_id = ? AND status = 'geplant' AND id != ? ORDER BY nr, id",
                         (pid, b["id"])).fetchall():
        if f"M{x['nr']}" in nrs and (z.get((x["id"], "grob")) or {}).get("an") and not _hat_pakete(con, x["id"]):
            aus.append(x)
    return sorted(aus, key=lambda x: (x["nr"], x["id"]))


def _schon(con, pid, bid):
    return con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND bogen_id = ?", (pid, FAELLIG, bid)).fetchone()


def _lead_beauftragen(con, pid, boegen, grund):
    """Wenn kein Feinplaner laufen kann (aus, Tagesgrenze): der Lead zerlegt den Meilenstein selbst in Pakete."""
    lead = kern.lead(con, pid)
    if not lead:
        return
    namen = ", ".join(f"{b['nr']} „{b['titel'][:50]}“" for b in boegen)
    with db.schreiben(con):
        kern._posten(con, pid, "AMW", lead, "auftrag", f"Meilenstein {namen} jetzt fein planen"[:140],
                     f"{grund}. Pakete für Meilenstein {namen} anlegen (Ziel, Thema, Dateien, Abnahme, Abhängigkeiten, Dauer)"
                     " und den Plan zur Freigabe stellen – das Ja startet ihn.")


def _planer_anstossen(con, pid, boegen, grund):
    """Der Weg für fällige Meilensteine: den Feinplaner anstoßen; geht das nicht, plant der Lead."""
    erg = anstossen(con, pid, [b["id"] for b in boegen])
    if not erg["gestartet"]:
        _lead_beauftragen(con, pid, boegen, f"{grund}. Feinplaner nicht gestartet: {erg['text']}")


ANSTOSSEN = _planer_anstossen        # Tests setzen eine Attrappe

GRUND = {"erster": "Der Grobplan steht, noch läuft kein Meilenstein",
         "bereit": "Der laufende Meilenstein ist bereit zur Abnahme",
         "letztes": "Im laufenden Meilenstein läuft das letzte Paket"}


def projekt(con, pid):
    """Eine Runde für ein Projekt: Feinplanung des nächsten Meilensteins (mit seinen gleichzeitigen) anstoßen, wenn es Zeit
    ist – einmal je Meilenstein. Rückgabe [(Bogen-Id, Anlass)]."""
    from . import planautomatik
    if not planautomatik.an(con, pid):
        return []
    a = anlass(con, pid)
    if a == "erster" and _grob_offen(con, pid):
        return []                                    # „nach dem Grobplan“: erst wenn alle geplanten Meilensteine frei sind
    b = naechster(con, pid) if a else None
    if not a or not b or _schon(con, pid, b["id"]):
        return []
    boegen = [x for x in gruppe(con, pid, b) if x["id"] == b["id"] or not _schon(con, pid, x["id"])]
    with db.schreiben(con):
        for x in boegen:
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art=FAELLIG, bogen_id=x["id"],
                         text=json.dumps({"bogen": x["id"], "nr": x["nr"], "anlass": a}, ensure_ascii=False))
    ANSTOSSEN(con, pid, boegen, GRUND[a])
    return [(x["id"], a) for x in boegen]


def runde(con):
    """Vom Dienst je Aufsichtsrunde: alle Projekte; ein Projekt hält die anderen nie auf."""
    aus = []
    for (pid,) in con.execute("SELECT id FROM projekt").fetchall():
        try:
            aus += projekt(con, pid)
        except Exception as x:                       # noqa: BLE001
            aus.append((0, f"Projekt {pid}: {type(x).__name__}: {x}"))
    return aus


def plan_starten(con, pid, von, bid) -> dict:
    """„Plan freigeben und starten“ – ein Klick: das Ja zum Feinplan; ist der Plan damit frei (Mensch allein, oder das zweite Ja
    von Co bzw. Lead), geht der Meilenstein sofort in die Umsetzung (reihenfolge.starten: aktiv, startklar, verteilen) –
    auch während der vorige noch auf seine Abnahme wartet. {"frei", "ja_fehlt"?, "gestartet"?}"""
    from . import planansicht, reihenfolge
    r = planansicht.freigeben(con, pid, von, bid, "plan")
    if not r.get("frei"):
        return r
    starter = von if kern.ist_lead(con, pid, von) else (kern.lead(con, pid) or kern.ENTWICKLER)
    return {**r, "gestartet": reihenfolge.starten(con, pid, starter, bid)}


# --- Ereignisse ------------------------------------------------------------------------------------------------------------

def _ereignis(con, pid, von, art, **werte):
    """In der Transaktion des Aufrufers."""
    return db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=art,
                        bogen_id=(werte.get("boegen") or [None])[0], text=json.dumps(werte, ensure_ascii=False))


def _ereignisse(con, pid, art, boegen=None):
    aus = []
    for r in con.execute("SELECT id, von, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, art)):
        try:
            d = json.loads(r["text"] or "{}")
        except ValueError:
            continue
        if isinstance(d, dict) and (boegen is None or d.get("boegen") == sorted(boegen)):
            aus.append({**d, "id": r["id"], "von": r["von"], "zeit_utc": r["zeit_utc"]})
    return aus


def _zeilen(con, pid, boegen):
    aus = []
    for bid in boegen:
        b = con.execute("SELECT * FROM bogen WHERE id = ? AND projekt_id = ?", (bid, pid)).fetchone()
        if not b:
            raise kern.AmwFehler(f"Meilenstein {bid} gibt es nicht")
        aus.append(b)
    return sorted(aus, key=lambda x: (x["nr"], x["id"]))


def themen_der(con, pid, b):
    """Die Themen eines Meilensteins (TH-Verweise im Ziel – so legt sie der Grobplan an, A2030), nur vorhandene."""
    aus = []
    for t in _TH.findall(" ".join(str(b[k] or "") for k in ("ziel", "titel"))):
        if int(t) not in aus and con.execute("SELECT 1 FROM thema WHERE id = ? AND projekt_id = ?", (int(t), pid)).fetchone():
            aus.append(int(t))
    return aus


# --- Feinplaner anstoßen und laufen lassen ---------------------------------------------------------------------------------

def laeuft(con, pid, boegen):
    """Läuft gerade ein Feinplaner für genau diese Meilensteine? Das jüngste „angestoßen“ ohne Entwurf derselben Fassung."""
    an = _ereignisse(con, pid, ANGESTOSSEN, boegen)
    if not an:
        return None
    if any(e.get("fassung") == an[-1].get("fassung") for e in _ereignisse(con, pid, ENTWURF, boegen)):
        return None
    t = db.utc_lesen(an[-1]["zeit_utc"])
    return None if (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() > LAEUFT_H * 3600 else an[-1]


def _naechste_fassung(con, pid, boegen):
    return 1 + max([e.get("fassung") or 0 for e in _ereignisse(con, pid, ANGESTOSSEN, boegen)] or [0])


def _spawn(pid, boegen, fassung, umgebung=None):
    from . import planer
    befehl = [sys.executable, "-I", "-X", "utf8", planer.EINSTIEG, "--fein", "--projekt-id", str(pid),
              "--boegen", ",".join(str(b) for b in boegen), "--fassung", str(fassung)]
    flags = (0x00000008 | 0x00000200 | planer.OHNE_FENSTER) if os.name == "nt" else 0
    return subprocess.Popen(befehl, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                            creationflags=flags, env=umgebung, start_new_session=os.name != "nt").pid


STARTER = _spawn             # Tests setzen eine Attrappe; tests/abschotten schaltet das Anstoßen ganz ab (AMW_PLANER_AUS)


def anstossen(con, pid, boegen, von="AMW", hinweis=None, nacharbeit=False) -> dict:
    """Den Feinplaner für diese Meilensteine anstoßen (nacharbeit, A2029: neue Pakete in einem laufenden Meilenstein, die gleich
    starten) – außer er ist aus, das Projekt ist nicht eingeschaltet, einer läuft
    schon oder die Tagesgrenze der Planer ist erreicht. Rückgabe {"gestartet": bool, "text"}."""
    from . import planer, planer_fortschritt
    boegen = sorted(boegen)
    if os.environ.get("AMW_PLANER_AUS"):
        return {"gestartet": False, "text": "Planer ist aus"}
    aus = planer.schalter_text(con, pid)
    if aus:
        return {"gestartet": False, "text": aus}
    zeilen = _zeilen(con, pid, boegen)
    with db.schreiben(con):                               # in einer Schreib-Transaktion: nie doppelt angestoßen
        if laeuft(con, pid, boegen):
            return {"gestartet": False, "text": "Es plant schon ein Feinplaner"}
        grenze = planer.tagesgrenze(con, pid)
        usd = planer.heute_usd(con, pid)
        if grenze is not None and usd >= grenze:
            return {"gestartet": False, "text": f"Tagesgrenze der Planer erreicht ({usd:.2f} von {grenze:.2f} $) – Grenze erhöhen"
                                                " (amw projekt einstellen planer_tagesgrenze_usd=…) und neu planen lassen"}
        fassung = _naechste_fassung(con, pid, boegen)
        werte = {"boegen": boegen, "fassung": fassung, "modell": MODELL, "hinweis": (hinweis or "").strip()[:2000] or None,
                 **({"nacharbeit": True} if nacharbeit else {}), **planer_fortschritt.ausloeser(von)}
        eid = _ereignis(con, pid, von, ANGESTOSSEN, **werte)
    try:
        prozess = STARTER(pid, boegen, fassung)
    except OSError as e:
        entwurf_eintragen(con, pid, boegen, fassung, None, modell=MODELL, fehler=f"Feinplaner ließ sich nicht starten: {e}")
        return {"gestartet": False, "text": f"Feinplaner ließ sich nicht starten ({e})"}
    with db.schreiben(con):
        con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?", (json.dumps({**werte, "prozess": prozess}, ensure_ascii=False), eid))
    namen = ", ".join(f"M{b['nr']}" for b in zeilen)
    return {"gestartet": True, "text": f"Feinplan {namen} Fassung {fassung}: Planer ({MODELL}) angestoßen"}


def neu_planen(con, pid, von, bid, hinweis=None) -> dict:
    """„Überarbeiten lassen“: eine neue Fassung des Feinplans, mit Hinweis an den Planer – Lead oder Mensch, solange der Plan
    nicht freigegeben ist und der Meilenstein noch nicht läuft."""
    if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler("Neu fein planen lassen der Lead oder der Mensch")
    b = _zeilen(con, pid, [bid])[0]
    if b["status"] != "geplant":
        raise kern.AmwFehler(f"Meilenstein {b['nr']} ist {b['status']} – fein geplant wird nur ein geplanter Meilenstein")
    if (_zustaende(con, pid).get((bid, "plan")) or {}).get("an"):
        raise kern.AmwFehler(f"Der Plan von Meilenstein {b['nr']} ist schon freigegeben – erst zurückholen")
    letzte = [e for e in _ereignisse(con, pid, ENTWURF) if bid in (e.get("boegen") or [])]
    boegen = letzte[-1]["boegen"] if letzte else [bid]
    return anstossen(con, pid, boegen, von=von, hinweis=hinweis)


def _dateien(con, pid, zeilen, hinweis, ordner):
    from . import grobplan, planer
    os.makedirs(os.path.join(ordner, "themen"), exist_ok=True)
    themen = []
    for b in zeilen:
        themen += [t for t in themen_der(con, pid, b) if t not in themen]
    ms = []
    for b in zeilen:
        ms.append(f"## M{b['nr']} {b['titel']}\n\nZiel: {b['ziel'] or '–'}\nFertig, wenn: {b['abnahme'] or '–'}\n"
                  f"Themen: {', '.join(f'TH{t}' for t in themen_der(con, pid, b)) or '–'}\n")
    teile = {"meilenstein.md": "# Fein zu planen\n\n" + "\n".join(ms)}
    for tid in themen:
        t = con.execute("SELECT name FROM thema WHERE id = ?", (tid,)).fetchone()
        frei = (grobplan.themen_frei(con, pid).get(tid) or {})
        teile[f"themen/TH{tid}.md"] = f"# TH{tid} {t['name'] if t else ''} – Fassung {frei.get('fassung', '–')}\n\n{frei.get('text', '')}\n"
    b = con.execute("SELECT id, thema, stichwort, regel FROM beschluss WHERE projekt_id = ? AND status = 'gilt' ORDER BY thema, id",
                    (pid,)).fetchall()
    teile["beschluesse.md"] = "# Geltende Beschlüsse\n\n" + ("\n".join(f"- B{x['id']} [{x['thema'] or '–'}] {x['stichwort']}: {x['regel']}"
                                                                      for x in b) or "(keine)") + "\n"
    ja = grobplan.angenommen(con, pid) or {}
    alle = con.execute("SELECT nr, titel, status, ziel FROM bogen WHERE projekt_id = ? AND status IN ('geplant', 'aktiv', 'fertig')"
                       " ORDER BY nr", (pid,)).fetchall()
    zeilen_ms = []
    for x in alle:
        k = f"M{x['nr']}"
        nach, gleich = (ja.get("nach") or {}).get(k) or [], (ja.get("gleichzeitig") or {}).get(k) or []
        zeilen_ms.append(f"- {k}: {x['titel']} [{x['status']}]" + (f" – Ziel: {x['ziel']}" if x["ziel"] else "")
                         + (" – nach " + ", ".join(nach) if nach else "") + (" – gleichzeitig mit " + ", ".join(gleich) if gleich else ""))
    teile["meilensteine.md"] = "# Grobplan – alle Meilensteine\n\n" + ("\n".join(zeilen_ms) or "(keine)") + "\n"
    offen = con.execute("SELECT id, titel, status FROM aufgabe WHERE projekt_id = ? AND status NOT IN ('fertig', 'verworfen')"
                        " ORDER BY id DESC LIMIT 200", (pid,)).fetchall()
    teile["pakete.md"] = "# Offene Pakete des Projekts\n\n" + ("\n".join(f"- A{x['id']} [{x['status']}] {x['titel']}" for x in offen)
                                                             or "(keine)") + "\n"
    gebaut = [f"- TH{tid}: A{i} {t}" for tid in themen for i, t in planer.gebaut_zum_thema(con, pid, tid)]
    teile["gebaut.md"] = "# Schon gebaut zu diesen Themen\n\n" + ("\n".join(gebaut) or "(nichts)") + "\n"
    teile["hinweise.md"] = "# Hinweise des Menschen\n\n" + ((hinweis or "").strip() or "(keine)") + "\n"
    teile["schema.md"] = "# Antwort-Format\n\n" + SCHEMA_TEXT + "\n"
    teile["sperrliste.md"] = sperrliste_text(con, pid)                       # A2067
    from . import arbeiter
    teile["befehle.md"] = arbeiter.befehle_text()                            # A2076
    for name, text in teile.items():
        with open(os.path.join(ordner, *name.split("/")), "w", encoding="utf-8", newline="\n") as d:
            d.write(text)
    return sorted(teile)


def sperrliste_text(con, pid):
    """A2067: die gesperrten Bereiche für den Planer – feste Liste (abnahme.GESPERRT) und Muster des Projekts, mit der Regel."""
    from . import abnahme
    fest = [f"- `{m}` – {g}" for m, art, g in abnahme.GESPERRT if art == "fest"]
    test = [f"- `{m}` – {g} (frei nur mit pakettyp test-schreiben oder test-ergaenzen)" for m, art, g in abnahme.GESPERRT if art == "test"]
    projekt = [f"- `{m}` – Sperrmuster des Projekts" for m in abnahme.projekt_muster(con, pid)]
    return ("# Gesperrte Bereiche – ein p-Paket ändert sie nie\n\n"
            "Regel: Ein Paket mit \"ausfuehrung\": \"p\" nennt in \"bereiche\" keinen dieser Pfade. Testdateien nur mit \"pakettyp\": "
            "\"test-schreiben\" oder \"test-ergaenzen\" (oder ein eigenes Test-Paket als Vorgänger). Braucht ein Paket einen anderen "
            "gesperrten Pfad, läuft es als \"agent\" mit \"interaktiv_grund\": \"gesperrter Bereich\".\n\n"
            "## Testdateien\n\n" + ("\n".join(test) or "(keine)") + "\n\n## Immer gesperrt\n\n" + ("\n".join(fest) or "(keine)")
            + "\n\n## Muster des Projekts\n\n" + ("\n".join(projekt) or "(keine)") + "\n")


def planen_mit_nachbesserung(con, pid, boegen, zeilen, hinweis, modell, prog=None, zusatz=None, melden=None):
    """A2067: planen; passt die Antwort nicht zum Schema (pruefen), geht der Fund EINMAL automatisch zurück an den Planer – erst
    eine zweite Antwort, die nicht passt, sieht der Mensch als „Plan passte nicht“. Kosten beider Läufe zählen zusammen."""
    from . import planer
    aus = planen(con, pid, zeilen, hinweis, modell, prog=prog, zusatz=zusatz)
    if aus.get("fehler") or aus.get("ergebnis") is None:
        return aus
    try:
        pruefen(aus["ergebnis"], con, pid, boegen)
        return aus
    except planer.PlanFehler as e:
        funde = e.fehler
    if melden:
        melden(f"Antwort passte nicht ({len(funde)} Funde) – eine Nachbesserung")
    zweiter = ((hinweis or "").strip() + "\n\n" if (hinweis or "").strip() else "") + (
        "Deine erste Antwort passte nicht zum Schema bzw. zu den Regeln. Bessere genau diese Funde nach und antworte wieder nur mit "
        "dem JSON:\n" + "\n".join(f"- {f}" for f in funde[:25]))
    neu = planen(con, pid, zeilen, zweiter, modell, prog=prog, zusatz=zusatz)
    usd = [x for x in (aus.get("usd"), neu.get("usd")) if isinstance(x, (int, float))]
    return {**neu, "usd": round(sum(usd), 4) if usd else None, "nachgebessert": funde}


def planen(con, pid, zeilen, hinweis, modell, prog=None, zusatz=None):
    """Der Feinplaner selbst, in einem leeren eigenen Ordner (wie ein Platz). Rückgabe {"ergebnis", "usd", "fehler"}."""
    from . import arbeiter, planer, platz, versionsprobe
    with tempfile.TemporaryDirectory(prefix="amw-feinplan-", ignore_cleanup_errors=True) as ordner:
        p = platz.pfade(os.path.join(ordner, "plaetze"), 1)
        os.makedirs(p["klon"])
        subprocess.run(["git", "init", "-q", "-b", "main", p["klon"]], check=True, capture_output=True, creationflags=planer.OHNE_FENSTER)
        dateien = _dateien(con, pid, zeilen, hinweis, p["klon"])
        r = arbeiter.laufen(p, AUFTRAG + "\n\nDateien: " + ", ".join(dateien), None, modell=modell, effort=EFFORT, prog=prog,
                            zusatz=zusatz, nur_lesen=True, geprueft=versionsprobe.geprueft(con), frist_s=FRIST_S)
    erg = r.get("ergebnis") or {}
    usd = erg.get("total_cost_usd")
    if r.get("abweichungen"):
        return {"ergebnis": None, "usd": usd, "fehler": "; ".join(r["abweichungen"])[:500]}
    text = (erg.get("result") or "").strip()
    if r.get("rc") != 0 or erg.get("is_error") or not text:
        return {"ergebnis": None, "usd": usd, "fehler": r.get("fehler") or f"kein Ergebnis (rc {r.get('rc')})"}
    return {"ergebnis": planer.json_aus_text(text), "usd": usd, "fehler": None}


def ausfuehren(con, pid, boegen, fassung, prog=None, zusatz=None):
    """Als angemeldeter Lauf der Lauf-Schlange (leicht): warten, bis er dran ist, planen, Entwurf eintragen (auch einen Fehler)."""
    from . import belegung, betrieb, planer_fortschritt
    boegen = sorted(boegen)
    an = next((e for e in _ereignisse(con, pid, ANGESTOSSEN, boegen) if e.get("fassung") == fassung), {})
    modell = an.get("modell") or MODELL
    zeilen = _zeilen(con, pid, boegen)
    namen = ", ".join(f"M{b['nr']}" for b in zeilen)
    agent = kern.lead(con, pid) or kern.ENTWICKLER
    lid = betrieb.lauf_start(con, pid, agent, f"Feinplaner {namen} Fassung {fassung} ({modell}, A2031, automatisch)", None,
                             False, False, None, warten=True, waechter=os.getpid(), befehl=None, ordner=None, selbst=True)
    belegung.lauf_merken(lid, os.getpid())
    fortschritt = functools.partial(planer_fortschritt.melden_still, con, pid, lid, art=FORTSCHRITT, agent=agent, modell=modell, ziel=namen, fassung=fassung,
                                    **planer_fortschritt.vom(an))
    fortschritt(was=f"Feinplan {namen} Fassung {fassung}: wartet auf einen Platz in der Lauf-Schlange",
                dauer_s=planer_fortschritt.schaetzung(con, pid, FORTSCHRITT), sofort=True)
    aus = None
    try:
        while True:
            l = betrieb.lauf_zeile(con, pid, lid)
            if l["status"] == "laeuft":
                break
            if l["status"] in ("fertig", "abgebrochen"):
                raise RuntimeError(f"L{lid} ist {l['status']} – nicht geplant")
            time.sleep(5)
        betrieb.lauf_uebernehmen(con, lid, "agent")
        fortschritt(was=f"Feinplan {namen} Fassung {fassung}: Meilenstein wird in Pakete zerlegt", sofort=True)
        aus = planen_mit_nachbesserung(con, pid, boegen, zeilen, an.get("hinweis"), modell, prog=prog, zusatz=zusatz,   # A2067
                                       melden=lambda t: fortschritt(was=f"Feinplan {namen} Fassung {fassung}: {t}", sofort=True))
    except Exception as e:                                # noqa: BLE001 – niemand sieht die Ausgabe: als Fehler eintragen
        aus = {"ergebnis": None, "usd": None, "fehler": f"{type(e).__name__}: {e}"[:300]}
    finally:
        aus = aus or {"ergebnis": None, "usd": None, "fehler": "abgebrochen"}
        kosten = f"{aus['usd']:.2f} $" if isinstance(aus.get("usd"), (int, float)) else "Kosten unbekannt"
        try:
            betrieb.lauf_ende(con, pid, agent, lid, 1 if aus.get("fehler") else 0,
                              (f"Feinplaner {namen} Fassung {fassung}: " + (f"Fehler – {aus['fehler']}" if aus.get("fehler") else "fertig")
                               + f" · {kosten}")[:500])
        finally:
            belegung.lauf_vergessen(lid)
    e = entwurf_eintragen(con, pid, boegen, fassung, aus.get("ergebnis"), modell=modell, usd=aus.get("usd"), lauf=lid,
                          fehler=aus.get("fehler"))
    if e.get("fehler"):
        fortschritt(was=f"Feinplan {namen} Fassung {fassung}: nicht geplant", usd=aus.get("usd"), zustand="fehler",
                    fehler="; ".join(e["fehler"])[:300])
    else:
        fortschritt(was=f"Feinplan {namen} Fassung {fassung}: {len(e['angelegt'])} Pakete angelegt", usd=aus.get("usd"), zustand="fertig")
    return aus


# --- Entwurf prüfen, Pakete anlegen ----------------------------------------------------------------------------------------

def pruefen(daten, con, pid, boegen):
    """Prüft einen Feinplan gegen das Schema: das Paket-Schema von planer.py (über planer.pruefen, mit den Meilensteinen als
    „bestehend“), dazu je Paket ein Thema seines Meilensteins, jeder Meilenstein mit Paketen, nichts schon Gebautes, Fragen.
    Rückgabe vereinheitlicht; Fehler: planer.PlanFehler mit allen Funden."""
    from . import planer
    if isinstance(daten, str):
        try:
            daten = json.loads(daten)
        except ValueError as e:
            raise planer.PlanFehler([f"kein JSON: {e}"]) from None
    if not isinstance(daten, dict):
        raise planer.PlanFehler(["oben muss ein Objekt stehen"])
    f = []
    unbekannt = set(daten) - {"pakete", "fragen", "grund"}
    if unbekannt:
        f.append("unbekannte Felder: " + ", ".join(sorted(unbekannt)))
    zeilen = _zeilen(con, pid, boegen)
    themen = {f"M{b['nr']}": themen_der(con, pid, b) for b in zeilen}
    roh = daten.get("pakete")
    pakete: list = roh if isinstance(roh, list) else []
    zu = {}
    for i, p in enumerate(pakete, 1):
        if not isinstance(p, dict):
            continue
        wo = f"Paket {p.get('schluessel') or i}"
        m, t = str(p.get("meilenstein") or "").strip(), str(p.get("thema") or "").strip()
        n = _TH.fullmatch(t)
        if m in themen and not n:
            f.append(f"{wo}: thema fehlt (TH-Nummer eines Themas von {m})")
        elif n and m in themen and themen[m] and int(n.group(1)) not in themen[m]:
            f.append(f"{wo}: {t} gehört nicht zu {m} (Themen: {', '.join(f'TH{x}' for x in themen[m])})")
        if n:
            zu[str(p.get("schluessel") or "").strip()] = int(n.group(1))
    try:
        e = planer.pruefen({"nichts_zu_bauen": False, "meilensteine": [{"schluessel": f"M{b['nr']}", "bestehend": b["nr"]} for b in zeilen],
                            "pakete": pakete}, con, pid)
    except planer.PlanFehler as x:
        f += x.fehler
        e = None
    if e:
        for m in themen:
            if not any(p["meilenstein"] == m for p in e["pakete"]):
                f.append(f"{m}: kein Paket – jeder Meilenstein bekommt mindestens eins")
        for p in e["pakete"]:
            p["thema"] = zu.get(p["schluessel"])
            if p["thema"]:
                treffer = [f"A{i} „{t}“" for i, t in planer.gebaut_zum_thema(con, pid, p["thema"]) if planer.aehnlich(p["titel"], t)]
                if treffer:
                    f.append(f"Paket {p['schluessel']}: schon gebaut: " + ", ".join(treffer[:3]))
    fragen = daten.get("fragen") or []
    if not isinstance(fragen, list) or len(fragen) > MAX_FRAGEN:
        f.append(f"fragen: Liste mit höchstens {MAX_FRAGEN}")
        fragen = []
    aus_q = []
    for i, q in enumerate(fragen, 1):
        o = q.get("optionen") if isinstance(q, dict) else None
        if not isinstance(q, dict) or not str(q.get("frage") or "").strip() or not isinstance(o, dict) or len(o) < 2 \
                or q.get("empfehlung") not in o or not str(q.get("grund") or "").strip():
            f.append(f"Frage {i}: frage, mindestens zwei optionen, empfehlung (eine der Optionen) und grund")
            continue
        aus_q.append({"frage": str(q["frage"]).strip()[:300], "optionen": {str(k): str(v)[:300] for k, v in o.items()},
                      "empfehlung": q["empfehlung"], "grund": str(q["grund"]).strip()[:1000]})
    if f or e is None:
        raise planer.PlanFehler(f or ["kein Entwurf"])
    return {"pakete": e["pakete"], "fragen": aus_q, "grund": str(daten.get("grund") or "").strip()[:1500] or None}


def _verwerfen_alt(con, pid, boegen, fassung):
    """Die nicht begonnenen Pakete früherer Fassungen dieser Meilensteine verwerfen (nie löschen) – die neue Fassung ersetzt sie."""
    alt = [int(v[1:]) for e in _ereignisse(con, pid, ENTWURF, boegen) for v in (e.get("angelegt") or {}).values()]
    if not alt:
        return []
    weg = [r[0] for r in con.execute(f"SELECT id FROM aufgabe WHERE id IN ({','.join('?' * len(alt))}) AND status = 'wartet'"
                                     " AND begonnen_utc IS NULL", alt)]
    with db.schreiben(con):
        for aid in weg:
            con.execute("UPDATE aufgabe SET status = 'verworfen', beleg = ?, geaendert_utc = ? WHERE id = ?",
                        (f"Feinplan Fassung {fassung} ersetzt", db.jetzt(), aid))
    return weg


def _anlegen(con, pid, zeilen, entwurf):
    """Die Pakete eines geprüften Feinplans anlegen – wie planer._anlegen, mit dem Thema je Paket. Rückgabe {Schlüssel: "A<id>"}."""
    from . import arbeitspaket, fertigquelle, planer, planung, themen
    von = kern.lead(con, pid) or kern.ENTWICKLER
    bogen = {f"M{b['nr']}": b["id"] for b in zeilen}
    angelegt = {}
    for p in planer.reihenfolge(entwurf):
        nach = [int(v[1:]) if v.startswith("A") else int(angelegt[v][1:]) for v in p["nach"]]
        auftrag = p["auftrag"] + (f"\n\nInteraktiv, Grund: {p['interaktiv_grund']}" if p.get("interaktiv_grund") else "")
        aid = planung.schritt_setzen(con, pid, von, titel=p["titel"], auftrag=auftrag, bogen_id=bogen[p["meilenstein"]],
                                     groesse=p["groesse"], art=p["art"], pruefbefehl=p["abnahme_befehl"], nach=nach or None,
                                     **({"dateibereich": p["bereiche"]} if p.get("bereiche") else {}))
        modell, effort = planer.p_modell(con, pid, p) if p["ausfuehrung"] == "p" else (p["modell"], p["effort"])
        arbeitspaket.setzen(con, pid, von, aid, art=p["ausfuehrung"], **({"modell": modell} if modell else {}),
                            **({"effort": effort} if effort else {}), **({"pakettyp": p["pakettyp"]} if p.get("pakettyp") else {}))
        if p.get("thema"):
            themen.verweise_setzen(con, pid, von, aid, [p["thema"]])
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=fertigquelle.ART, aufgabe_id=aid,
                         text=json.dumps(planer.fertig_aus_plan(p["fertig_quelle"] if p.get("thema") or p["fertig_quelle"] != "thema"
                                                                else "ja", p.get("thema")), ensure_ascii=False))
            if p.get("lead_liest"):                                 # A2054: „Lead liest“ – nie automatisch abnehmen
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="lead_liest", aufgabe_id=aid,
                             text=json.dumps({"an": True}))
        angelegt[p["schluessel"]] = f"A{aid}"
    return angelegt


def reihenfolge_fehlt(con, fehlt):
    """A2083: Zeilen „starten noch nicht – Angaben fehlen“ für Meldungen an den Lead."""
    titel = {a: (con.execute("SELECT titel FROM aufgabe WHERE id = ?", (a,)).fetchone() or [""])[0] for a in fehlt}
    return "\n\nStarten noch nicht, Angaben fehlen:\n" + "\n".join(f"- A{a} {titel[a]}: {', '.join(f)}" for a, f in fehlt.items())


def entwurf_eintragen(con, pid, boegen, fassung, ergebnis, modell=None, usd=None, lauf=None, fehler=None):
    """Das Ergebnis eines Laufs als Fassung eintragen: geprüft → die Pakete anlegen (die der vorigen Fassung, nicht begonnen,
    verwerfen) – oder mit den Funden als Fehler. Fragen gehen an den Lead (A2021), der Lead bekommt eine Meldung; der Plan
    wartet dann auf das Ja („Plan freigeben und starten“). Rückgabe: das Ereignis (dict)."""
    from . import planer
    boegen = sorted(boegen)
    zeilen = _zeilen(con, pid, boegen)
    namen = ", ".join(f"M{b['nr']}" for b in zeilen)
    an = next((e for e in _ereignisse(con, pid, ANGESTOSSEN, boegen) if e.get("fassung") == fassung), {})
    nacharbeit = bool(an.get("nacharbeit"))                 # A2029: neue Pakete im laufenden Meilenstein, starten gleich
    entwurf, funde, angelegt, verworfen, fehlt = None, None, {}, [], {}
    if fehler:
        funde = [f"Feinplaner-Lauf: {fehler}"]
    else:
        try:
            entwurf = pruefen(planer.json_aus_text(ergebnis) if isinstance(ergebnis, str) else ergebnis, con, pid, boegen)
        except planer.PlanFehler as e:
            funde = e.fehler
    if entwurf and nacharbeit:
        if any(b["status"] != "aktiv" for b in zeilen):
            entwurf, funde = None, [f"{namen} läuft nicht mehr – Nacharbeit nicht angelegt"]
    elif entwurf:
        if any(b["status"] != "geplant" for b in zeilen) or any((_zustaende(con, pid).get((b["id"], "plan")) or {}).get("an") for b in zeilen):
            entwurf, funde = None, [f"{namen} läuft schon oder der Plan ist freigegeben – Entwurf nicht angelegt"]
    if entwurf:
        verworfen = [] if nacharbeit else _verwerfen_alt(con, pid, boegen, fassung)
        angelegt = _anlegen(con, pid, zeilen, entwurf)
        if nacharbeit:                                    # kein neues Start-Ja: der Meilenstein läuft schon
            from . import reihenfolge
            for b in zeilen:                              # A2083: nur diese Pakete, der Plan-Stand bleibt
                fehlt.update(reihenfolge.neue_startklar(con, pid, kern.lead(con, pid) or kern.ENTWICKLER, b["id"],
                                                        [int(v[1:]) for v in angelegt.values()]))
    werte = {"boegen": boegen, "fassung": fassung, "modell": modell, "usd": usd, "lauf": lauf, **({"nacharbeit": True} if nacharbeit else {})}
    werte.update({"entwurf": entwurf, "angelegt": angelegt} if entwurf else {"fehler": funde})
    lead = kern.lead(con, pid) or kern.ENTWICKLER
    kosten = f"{usd:.2f} $" if isinstance(usd, (int, float)) else "Kosten unbekannt"
    with db.schreiben(con):
        eid = _ereignis(con, pid, "AMW", ENTWURF, **werte)
        if not entwurf:
            kern._posten(con, pid, "AMW", lead, "meldung", f"Feinplan {namen} Fassung {fassung}: Planer-Ergebnis passt nicht"[:140],
                         "Funde:\n" + "\n".join(f"- {x}" for x in (funde or ["kein Entwurf"])[:20]) + f"\n\n({modell or '–'}, {kosten})\n"
                         f"Neu planen lassen: amw bogen feinplanen {boegen[0]} [--hinweis …]")
        else:
            kern._posten(con, pid, "AMW", lead, "meldung",
                         (f"Nacharbeit {namen}: {len(angelegt)} Pakete angelegt und gestartet" if nacharbeit else
                          f"Feinplan {namen} Fassung {fassung}: {len(angelegt)} Pakete angelegt – wartet auf das Ja")[:140],
                         planer.zusammenfassung({"nichts_zu_bauen": False, "pakete": entwurf["pakete"],
                                                 "meilensteine": [{"schluessel": f"M{b['nr']}", "bestehend": b["nr"]} for b in zeilen]})
                         + (reihenfolge_fehlt(con, fehlt) if fehlt else "")
                         + (f"\n\nVerworfen (vorige Fassung, nicht begonnen): {', '.join(f'A{x}' for x in verworfen)}" if verworfen else "")
                         + f"\n\n({modell or '–'}, {kosten})\n"
                         + ("Der Meilenstein läuft schon – es braucht kein neues Ja." if nacharbeit else      # A2086 (9)
                            f"Ja = Start: Planung › Pakete › „Plan freigeben und starten“ (amw bogen freigeben {boegen[0]} --art plan --starten)"
                            f" · überarbeiten: amw bogen feinplanen {boegen[0]} --hinweis …"))
    for q in (entwurf or {}).get("fragen") or []:
        try:
            kern.frage_neu(con, pid, "AMW", "tl", f"Feinplan {namen}: {q['frage']}"[:200], list(q["optionen"].items()),
                           empfehlung=q["empfehlung"], grund=q["grund"], pruefen=False)
        except kern.AmwFehler:
            pass                                          # eine Frage, die nicht durchgeht, hält den Entwurf nicht auf
    return {**werte, "id": eid}


def heute_usd(con, pid, tag=None):
    """Kosten der Feinplaner des Projekts an diesem Tag (zählen zur gemeinsamen Tagesgrenze, planer.heute_usd)."""
    from . import planer
    tag = tag or planer._tag()
    return round(sum(e["usd"] for e in _ereignisse(con, pid, ENTWURF)
                     if isinstance(e.get("usd"), (int, float)) and planer._tag(e["zeit_utc"]) == tag), 2)


# --- Einstieg für amw-planer.py --fein -------------------------------------------------------------------------------------

def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="amw-planer --fein")
    ap.add_argument("--projekt-id", type=int, required=True)
    ap.add_argument("--boegen", required=True, help="Meilensteine (Id), mit Komma")
    ap.add_argument("--fassung", type=int, required=True)
    x = ap.parse_args(argv)
    con = db.verbinde()
    try:
        ausfuehren(con, x.projekt_id, [int(b) for b in x.boegen.split(",") if b.strip()], x.fassung)
    finally:
        con.close()
