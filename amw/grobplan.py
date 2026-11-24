"""A2030 (TH164 Schritt 2): Grobplanung einmal fürs ganze Konzept.

„Konzept abschließen“ – das Konzept-Ja zusätzlich zu den Themen-Ja (TL #31457 f) – startet EINEN Planer-Lauf (headless, nur
Lesen, gründliches Modell) über alle freigegebenen Themen. Er prüft das Konzept (Doppeltes, zu Großes, Unklares, Widersprüche,
Abdeckung) und schneidet Meilensteine mit Ziel als Verweis auf Themen, „fertig, wenn“, Ende mit Vorführung oder Bericht,
Reihenfolge und Abhängigkeiten (nach · gleichzeitig mit), grobem Aufwand und Kosten. Jeder Lauf ist eine Fassung, jede bleibt
sichtbar. Fragen des Planers gehen an den Lead (nur der Lead fragt den Menschen, A2021). Mit dem Grobplan-Ja legt die AMW die
Meilensteine an (Nummern je Projekt, bogen.nr), verknüpft sie über die TH-Verweise im Ziel mit den Themen und vermerkt die
Grob-Freigabe je Meilenstein – das Ja ist diese Freigabe. Der Planer je Thema (planer.py, K4) bleibt für Änderungen danach.

Wer Ja sagt (Konzept abschließen, Grobplan): wie bei den Themen (themen.freigabe_regel) – der Mensch, oder bei co+lead
Co-Entwickler und Lead je ein Ja; der Mensch jederzeit allein. Die einstellbaren Freigaben je Projekt baut A2032.

Ereignisse (plan_ereignis, ohne Schemaänderung, Text JSON):
  konzept_abschluss_ja  {"bezug", "rolle"}                       – ein Ja von Co oder Lead (bei co+lead)
  konzept_abschluss     {"themen": {tid: fassung}, "durch"}       – das Konzept ist abgeschlossen
  grobplan_angestossen  {"fassung", "modell", "themen", "prozess"}
  grobplan_entwurf      {"fassung", "modell", "usd", "lauf", "themen", "entwurf" | "fehler"}
  grobplan_ja_stimme    {"bezug", "rolle"}                       – ein Ja von Co oder Lead zum Grobplan
  grobplan_ja           {"fassung", "entwurf", "angelegt": {"M1": "M7"}, "durch"}

Schema des Grobplans (JSON):
  {"befunde": [{"art": "doppelt|zu_gross|unklar|widerspruch|abdeckung", "themen": ["TH12"], "text": "…", "vorschlag": "…" | null}],
   "fragen": [{"frage": "…", "optionen": {"A": "…", "B": "…"}, "empfehlung": "A", "grund": "…", "themen": ["TH12"]}],
   "meilensteine": [{"schluessel": "M1", "titel": "…", "ziel": "… (mit TH-Verweisen)", "themen": ["TH12", "TH13"],
                     "fertig_wenn": "…", "endet_mit": "vorfuehrung|bericht", "nach": ["M0"], "gleichzeitig": ["M2"],
                     "aufwand": "S|M|L|XL", "tage": 3, "usd": 12.5}],
   "grund": "warum diese Reihenfolge und dieser Schnitt"}

  Jedes freigegebene Thema steckt in mindestens einem Meilenstein – oder ein Befund „abdeckung“ nennt es mit Grund (z. B. nur
  ein Begriff, schon gebaut). Befunde „unklar“ werden zu Fragen (mit Empfehlung), wenn die Antwort den Schnitt ändert.
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

from . import db, kern, planer, planer_fortschritt

ABSCHLUSS_JA, ABSCHLUSS = "konzept_abschluss_ja", "konzept_abschluss"
ANGESTOSSEN, ENTWURF = "grobplan_angestossen", "grobplan_entwurf"
JA_STIMME, JA = "grobplan_ja_stimme", "grobplan_ja"
BEFUND_ARTEN = ("doppelt", "zu_gross", "unklar", "widerspruch", "abdeckung")
AUFWAND = ("S", "M", "L", "XL")
MAX_MEILENSTEINE = 15                           # Richtwert TH164: 20 Themen → 5–10 Meilensteine
MAX_BEFUNDE, MAX_FRAGEN = 40, 10
LAENGE = {"titel": 120, "ziel": 1000, "fertig_wenn": 500, "text": 1000, "vorschlag": 1000, "frage": 300, "grund": 1500,
          "option": 300}
MODELL, EFFORT = "opus", "high"                 # TH159: gründliches Modell für die Grobplanung (Einstellung kommt mit A2032)
FRIST_S = 30 * 60
LAEUFT_H = 6
FORTSCHRITT = "grobplaner"                      # planer_fortschritt.art
SCHEMA_TEXT = (__doc__ or "")[(__doc__ or "").find("Schema des Grobplans"):].strip()
_TH = re.compile(r"^TH(\d+)$")

AUFTRAG = (
    "Du bist der Planer eines Software-Projekts und machst die Grobplanung für das ganze Konzept. Lies uebersicht.md (alle vom "
    "Menschen freigegebenen Themen), jede Datei unter themen/, beschluesse.md, meilensteine.md und pakete.md (was es schon gibt) "
    "sowie schema.md (das Antwort-Format). Prüfe zuerst das Konzept: Doppeltes (zusammenlegen), zu Großes (teilen), Unklares "
    "(als Frage mit Optionen, Empfehlung und Grund, wenn die Antwort den Schnitt ändert), Widersprüche zwischen Themen und die "
    "Abdeckung – jedes Thema gehört in mindestens einen Meilenstein, sonst nennst du es in einem Befund „abdeckung“ mit Grund. "
    "Dann schneidest du Meilensteine: je ein vorführbares Stück mit Ziel (Verweis auf die Themen, z. B. „TH12 Anmeldung“), "
    "„fertig, wenn“, Ende mit Vorführung oder Bericht, Reihenfolge und Abhängigkeiten (nach = erst wenn der andere fertig ist, "
    "gleichzeitig = darf parallel laufen), grobem Aufwand (S, M, L, XL), Tagen und Kosten in Dollar. Richtwert: 20 Themen ergeben "
    "5 bis 10 Meilensteine. Pakete planst du nicht – die kommen später je Meilenstein. Was in meilensteine.md schon offen ist, "
    "planst du nicht doppelt. Antworte NUR mit dem JSON-Objekt nach schema.md – kein Text davor oder danach. "
    "Du änderst nichts, du schreibst keine Dateien, du führst nichts aus.")


# --- Ereignisse ------------------------------------------------------------------------------------------------------------

def _ereignis(con, pid, von, art, **werte):
    """In der Transaktion des Aufrufers."""
    return db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=art,
                        text=json.dumps(werte, ensure_ascii=False))


def _ereignisse(con, pid, art):
    aus = []
    for r in con.execute("SELECT id, von, zeit_utc, text FROM plan_ereignis WHERE projekt_id = ? AND art = ? ORDER BY id", (pid, art)):
        try:
            d = json.loads(r["text"] or "{}")
        except ValueError:
            continue
        if isinstance(d, dict):
            aus.append({**d, "id": r["id"], "von": r["von"], "zeit_utc": r["zeit_utc"]})
    return aus


# --- Themen und Ja ---------------------------------------------------------------------------------------------------------

def themen_frei(con, pid):
    """Die freigegebenen Themen (ohne Lösch-Markierung): {tid: {"name", "fassung", "text"}} – die freigegebene Fassung."""
    from . import themen
    aus = {}
    for t in con.execute("SELECT * FROM thema WHERE projekt_id = ? ORDER BY id", (pid,)).fetchall():
        s = themen.status(con, t)
        if s["status"] != "frei" or s.get("markiert") or not s.get("freigegeben"):
            continue
        f = con.execute("SELECT text FROM thema_fassung WHERE thema_id = ? AND nr = ?", (t["id"], s["freigegeben"])).fetchone()
        aus[t["id"]] = {"name": t["name"], "fassung": s["freigegeben"], "text": f["text"] if f else ""}
    return aus


def _stand(frei):
    return {str(tid): x["fassung"] for tid, x in sorted(frei.items())}


def _stimme(con, pid, von, art_stimme, bezug, stufe):
    """Wer Ja sagt: der Mensch allein → ("mensch", [von]). Bei thema_freigabe = co+lead geben Co und Lead je ein Ja zum selben
    Bezug; das zweite macht es gültig → ("co+lead", [co, lead]); vorher ("fehlt", [was fehlt]). In einer Schreib-Transaktion."""
    from . import themen
    if von == kern.ENTWICKLER:
        return "mensch", [von]
    if themen.freigabe_regel(con, pid, stufe) != "co+lead":                 # A2032: konzept → thema_freigabe, grob → grobplan_freigabe
        raise kern.AmwFehler(f"Das Ja gibt in diesem Projekt der Mensch ({themen.FREIGABE_EINSTELLUNG[stufe]} = mensch)")
    if kern.ist_co(con, pid, von):
        rolle = "co"
    elif kern.ist_lead(con, pid, von):
        rolle = "lead"
    else:
        raise kern.AmwFehler("Ein Ja geben der Co-Entwickler und der Lead (B2913) – sonst der Mensch")
    _ereignis(con, pid, von, art_stimme, bezug=bezug, rolle=rolle)
    j = {}
    for e in _ereignisse(con, pid, art_stimme):
        if e.get("bezug") == bezug:
            j[e.get("rolle")] = e["von"]
    if j.get("co") and j.get("lead"):
        return "co+lead", [j["co"], j["lead"]]
    return "fehlt", [themen.ROLLEN_JA[r] for r in themen.ROLLEN_JA if not j.get(r)]


def abgeschlossen(con, pid):
    """Der jüngste Konzept-Abschluss (dict) oder None."""
    a = _ereignisse(con, pid, ABSCHLUSS)
    return a[-1] if a else None


def angenommen(con, pid):
    """Das Grobplan-Ja (dict) oder None – es gibt höchstens eins; danach plant der Planer je Thema die Änderungen."""
    a = _ereignisse(con, pid, JA)
    return a[-1] if a else None


def aus_grobplan(con, pid, nr):
    """Wurde Meilenstein Nummer nr mit dem Grobplan-Ja angelegt? (Seine Themen stehen dann im Ziel.)"""
    ja = angenommen(con, pid)
    return bool(ja) and f"M{nr}" in (ja.get("angelegt") or {}).values()


def abschliessen(con, pid, von):
    """„Konzept abschließen und Grobplanung starten“. Nur bei geschlossenem Konzept-Tor (alle zählenden Themen frei) und solange
    kein Grobplan angenommen ist. Ein zweiter Abschluss (Konzept seitdem geändert) plant neu. Rückgabe: {"abgeschlossen",
    "ja_fehlt" | "planer"}."""
    from . import themen
    if angenommen(con, pid):
        raise kern.AmwFehler("Der Grobplan ist schon angenommen – Änderungen am Konzept plant der Planer je Thema (amw thema planen TH<n>)")
    t = themen.tor(con, pid)
    if not t["konzept_zu"]:
        raise kern.AmwFehler(f"Erst alle Themen freigeben: {t['n']} von {t['g']} Themen freigegeben")
    frei = themen_frei(con, pid)
    if not frei:
        raise kern.AmwFehler("Es gibt keine freigegebenen Themen")
    stand = _stand(frei)
    bezug = json.dumps(stand, sort_keys=True)
    with db.schreiben(con):
        wer, namen = _stimme(con, pid, von, ABSCHLUSS_JA, bezug, "konzept")
        if wer == "fehlt":
            return {"abgeschlossen": False, "ja_fehlt": namen}
        _ereignis(con, pid, von if wer == "mensch" else "AMW", ABSCHLUSS, themen=stand, durch=namen)   # Verlauf liest es (A2024)
    return {"abgeschlossen": True, "planer": anstossen(con, pid, von="AMW")}


# --- Planer anstoßen und laufen lassen -------------------------------------------------------------------------------------

def _naechste_fassung(con, pid):
    return 1 + max([e.get("fassung") or 0 for e in _ereignisse(con, pid, ANGESTOSSEN)] or [0])


def laeuft(con, pid):
    """Läuft gerade ein Grob-Planer? Das jüngste „angestoßen“ ohne Entwurf derselben Fassung, nicht älter als LAEUFT_H."""
    an = _ereignisse(con, pid, ANGESTOSSEN)
    if not an:
        return None
    if any(e.get("fassung") == an[-1].get("fassung") for e in _ereignisse(con, pid, ENTWURF)):
        return None
    t = db.utc_lesen(an[-1]["zeit_utc"])
    return None if (datetime.datetime.now(datetime.timezone.utc) - t).total_seconds() > LAEUFT_H * 3600 else an[-1]


def heute_usd(con, pid, tag=None):
    """Kosten der Grob-Planer des Projekts an diesem Tag (zählen zur gemeinsamen Tagesgrenze der Planer)."""
    tag = tag or planer._tag()
    return round(sum(e["usd"] for e in _ereignisse(con, pid, ENTWURF)
                     if isinstance(e.get("usd"), (int, float)) and planer._tag(e["zeit_utc"]) == tag), 2)


def _spawn(pid, fassung, umgebung=None):
    befehl = [sys.executable, "-I", "-X", "utf8", planer.EINSTIEG, "--projekt-id", str(pid), "--grob", "--fassung", str(fassung)]
    flags = (0x00000008 | 0x00000200 | planer.OHNE_FENSTER) if os.name == "nt" else 0
    return subprocess.Popen(befehl, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, close_fds=True,
                            creationflags=flags, env=umgebung, start_new_session=os.name != "nt").pid


STARTER = _spawn             # Tests setzen eine Attrappe; tests/abschotten schaltet das Anstoßen ganz ab (AMW_PLANER_AUS)


def anstossen(con, pid, von="AMW"):
    """Den Grob-Planer anstoßen (nach dem Konzept-Abschluss oder auf Befehl „neu planen“) – außer er ist aus, das Projekt ist
    nicht eingeschaltet, einer läuft schon oder die Tagesgrenze der Planer ist erreicht. Rückgabe: Text."""
    if os.environ.get("AMW_PLANER_AUS"):
        return "Planer ist aus"
    aus = planer.schalter_text(con, pid)
    if aus:
        return aus
    if not abgeschlossen(con, pid):
        raise kern.AmwFehler("Erst das Konzept abschließen (amw thema konzept-abschliessen)")
    if angenommen(con, pid):
        raise kern.AmwFehler("Der Grobplan ist schon angenommen")
    frei = themen_frei(con, pid)
    with db.schreiben(con):                               # in einer Schreib-Transaktion: nie doppelt angestoßen
        if laeuft(con, pid):
            return "Es plant schon ein Grob-Planer"
        grenze = planer.tagesgrenze(con, pid)
        usd = planer.heute_usd(con, pid)
        if grenze is not None and usd >= grenze:
            return (f"Tagesgrenze der Planer erreicht ({usd:.2f} von {grenze:.2f} $) – Grenze erhöhen (amw projekt einstellen"
                    " planer_tagesgrenze_usd=…) und neu planen lassen")
        fassung = _naechste_fassung(con, pid)
        eid = _ereignis(con, pid, von, ANGESTOSSEN, fassung=fassung, modell=MODELL, themen=_stand(frei))
    try:
        prozess = STARTER(pid, fassung)
    except OSError as e:
        entwurf_eintragen(con, pid, fassung, None, modell=MODELL, fehler=f"Grob-Planer ließ sich nicht starten: {e}")
        return f"Grob-Planer ließ sich nicht starten ({e})"
    with db.schreiben(con):
        con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?",
                    (json.dumps({"fassung": fassung, "modell": MODELL, "themen": _stand(frei), "prozess": prozess},
                                ensure_ascii=False), eid))
    return f"Grobplan Fassung {fassung}: Planer ({MODELL}) angestoßen – {len(frei)} Themen"


def _dateien(con, pid, frei, ordner):
    os.makedirs(os.path.join(ordner, "themen"), exist_ok=True)
    teile = {"uebersicht.md": "# Freigegebene Themen\n\n" + "\n".join(f"- TH{tid} {x['name']} (Fassung {x['fassung']}) → themen/TH{tid}.md"
                                                                    for tid, x in sorted(frei.items())) + "\n"}
    for tid, x in sorted(frei.items()):
        teile[f"themen/TH{tid}.md"] = f"# TH{tid} {x['name']} – Fassung {x['fassung']}\n\n{x['text']}\n"
    b = con.execute("SELECT id, thema, stichwort, regel FROM beschluss WHERE projekt_id = ? AND status = 'gilt' ORDER BY thema, id",
                    (pid,)).fetchall()
    teile["beschluesse.md"] = "# Geltende Beschlüsse\n\n" + ("\n".join(f"- B{x['id']} [{x['thema'] or '–'}] {x['stichwort']}: {x['regel']}"
                                                                      for x in b) or "(keine)") + "\n"
    ms = con.execute("SELECT nr, titel, status, ziel FROM bogen WHERE projekt_id = ? AND status IN ('geplant', 'aktiv', 'fertig')"
                     " ORDER BY nr", (pid,)).fetchall()
    teile["meilensteine.md"] = "# Meilensteine des Projekts\n\n" + ("\n".join(
        f"- M{x['nr']}: {x['titel']} [{x['status']}]" + (f" – Ziel: {x['ziel']}" if x["ziel"] else "") for x in ms) or "(keine)") + "\n"
    offen = con.execute("SELECT id, titel, status FROM aufgabe WHERE projekt_id = ? AND status NOT IN ('fertig', 'verworfen')"
                        " ORDER BY id DESC LIMIT 200", (pid,)).fetchall()
    teile["pakete.md"] = "# Offene Pakete des Projekts\n\n" + ("\n".join(f"- A{x['id']} [{x['status']}] {x['titel']}" for x in offen)
                                                             or "(keine)") + "\n"
    teile["schema.md"] = "# Antwort-Format\n\n" + SCHEMA_TEXT + "\n"
    for name, text in teile.items():
        with open(os.path.join(ordner, *name.split("/")), "w", encoding="utf-8", newline="\n") as d:
            d.write(text)
    return sorted(teile)


def planen(con, pid, frei, modell, prog=None, zusatz=None):
    """Der Grob-Planer selbst, in einem leeren eigenen Ordner (wie ein Platz). Rückgabe {"ergebnis", "usd", "fehler"}."""
    from . import arbeiter, planhinweis, platz, versionsprobe
    with tempfile.TemporaryDirectory(prefix="amw-grobplan-", ignore_cleanup_errors=True) as ordner:
        p = platz.pfade(os.path.join(ordner, "plaetze"), 1)
        os.makedirs(p["klon"])
        subprocess.run(["git", "init", "-q", "-b", "main", p["klon"]], check=True, capture_output=True, creationflags=planer.OHNE_FENSTER)
        dateien = _dateien(con, pid, frei, p["klon"])
        extra = planhinweis.schreiben(con, pid, "grob", p["klon"])        # A2028: Überarbeiten nach Hinweisen
        r = arbeiter.laufen(p, AUFTRAG + ("\n\n" + planhinweis.AUFTRAG if extra else "") + "\n\nDateien: " + ", ".join(dateien + extra),
                            None, modell=modell, effort=EFFORT, prog=prog,
                            zusatz=zusatz, nur_lesen=True, geprueft=versionsprobe.geprueft(con), frist_s=FRIST_S)
    erg = r.get("ergebnis") or {}
    usd = erg.get("total_cost_usd")
    if r.get("abweichungen"):
        return {"ergebnis": None, "usd": usd, "fehler": "; ".join(r["abweichungen"])[:500]}
    text = (erg.get("result") or "").strip()
    if r.get("rc") != 0 or erg.get("is_error") or not text:
        return {"ergebnis": None, "usd": usd, "fehler": r.get("fehler") or f"kein Ergebnis (rc {r.get('rc')})"}
    return {"ergebnis": planer.json_aus_text(text), "usd": usd, "fehler": None}


def ausfuehren(con, pid, fassung, prog=None, zusatz=None):
    """Als angemeldeter Lauf der Lauf-Schlange (leicht): warten, bis er dran ist, planen, Entwurf eintragen (auch einen Fehler)."""
    from . import belegung, betrieb
    an = next((e for e in _ereignisse(con, pid, ANGESTOSSEN) if e.get("fassung") == fassung), {})
    modell = an.get("modell") or MODELL
    frei = themen_frei(con, pid)
    agent = kern.lead(con, pid) or kern.ENTWICKLER
    lid = betrieb.lauf_start(con, pid, agent, f"Grob-Planer Fassung {fassung} ({modell}, {len(frei)} Themen, A2030, automatisch)", None,
                             False, False, None, warten=True, waechter=os.getpid(), befehl=None, ordner=None, selbst=True)
    belegung.lauf_merken(lid, os.getpid())
    fortschritt = functools.partial(planer_fortschritt.melden_still, con, pid, lid, art=FORTSCHRITT, agent=agent, modell=modell)
    fortschritt(was=f"Grobplan Fassung {fassung}: wartet auf einen Platz in der Lauf-Schlange",
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
        if not frei:
            raise kern.AmwFehler("keine freigegebenen Themen")
        fortschritt(was=f"Grobplan Fassung {fassung}: {len(frei)} Themen werden geplant", sofort=True)
        aus = planen(con, pid, frei, modell, prog=prog, zusatz=zusatz)
    except Exception as e:                                # noqa: BLE001 – niemand sieht die Ausgabe: als Fehler eintragen
        aus = {"ergebnis": None, "usd": None, "fehler": f"{type(e).__name__}: {e}"[:300]}
    finally:
        aus = aus or {"ergebnis": None, "usd": None, "fehler": "abgebrochen"}
        kosten = f"{aus['usd']:.2f} $" if isinstance(aus.get("usd"), (int, float)) else "Kosten unbekannt"
        try:
            betrieb.lauf_ende(con, pid, agent, lid, 1 if aus.get("fehler") else 0,
                              (f"Grob-Planer Fassung {fassung}: " + (f"Fehler – {aus['fehler']}" if aus.get("fehler") else "fertig")
                               + f" · {kosten}")[:500])
        finally:
            belegung.lauf_vergessen(lid)
    e = entwurf_eintragen(con, pid, fassung, aus.get("ergebnis"), modell=modell, usd=aus.get("usd"), lauf=lid, fehler=aus.get("fehler"),
                          frei=frei)
    if e.get("fehler"):
        fortschritt(was=f"Grobplan Fassung {fassung}: nicht geplant", usd=aus.get("usd"), zustand="fehler",
                    fehler="; ".join(e["fehler"])[:300])
    else:
        fortschritt(was=f"Grobplan Fassung {fassung}: Entwurf liegt vor", usd=aus.get("usd"), zustand="fertig")
    return aus


# --- Entwurf prüfen und eintragen ------------------------------------------------------------------------------------------

def _text(x, feld, wo, f, pflicht=True):
    v = " ".join(x.split()) if feld == "titel" and isinstance(x, str) else (x.strip() if isinstance(x, str) else x)
    if v is None or v == "":
        if pflicht:
            f.append(f"{wo}: {feld} fehlt")
        return None
    if not isinstance(v, str):
        f.append(f"{wo}: {feld} ist kein Text")
        return None
    if len(v) > LAENGE[feld]:
        f.append(f"{wo}: {feld} länger als {LAENGE[feld]} Zeichen")
    return v


def _themen(x, frei, wo, f, pflicht=True):
    if x is None:
        x = []
    if not isinstance(x, list):
        f.append(f"{wo}: themen ist keine Liste")
        return []
    aus = []
    for v in x:
        m = _TH.match(str(v).strip().upper())
        if not m:
            f.append(f"{wo}: Thema „{v}“ – Form TH12")
        elif int(m.group(1)) not in frei:
            f.append(f"{wo}: TH{m.group(1)} ist kein freigegebenes Thema")
        elif int(m.group(1)) not in aus:
            aus.append(int(m.group(1)))
    if pflicht and not aus and not any(wo in y for y in f):
        f.append(f"{wo}: themen fehlt (mindestens ein Thema)")
    return aus


def _zahl(x, feld, wo, f):
    if x is None:
        return None
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x < 0:
        f.append(f"{wo}: {feld} ist keine Zahl ≥ 0")
        return None
    return x


def pruefen(daten, frei):
    """Ein Grobplan-Ergebnis (JSON-Text oder dict) gegen das Schema und die freigegebenen Themen prüfen. Rückgabe: der bereinigte
    Entwurf; sonst planer.PlanFehler mit allen Funden auf einmal."""
    f = []
    if isinstance(daten, str):
        try:
            daten = json.loads(daten)
        except ValueError as e:
            raise planer.PlanFehler([f"kein JSON: {e}"])
    if not isinstance(daten, dict):
        raise planer.PlanFehler(["kein JSON-Objekt"])
    aus = {"befunde": [], "fragen": [], "meilensteine": [], "grund": _text(daten.get("grund"), "grund", "Plan", f, pflicht=False)}
    for liste, n in (("befunde", MAX_BEFUNDE), ("fragen", MAX_FRAGEN), ("meilensteine", MAX_MEILENSTEINE)):
        if not isinstance(daten.get(liste) or [], list):
            f.append(f"{liste} ist keine Liste")
        elif len(daten.get(liste) or []) > n:
            f.append(f"mehr als {n} {liste}")
    for i, b in enumerate(daten.get("befunde") or [] if isinstance(daten.get("befunde") or [], list) else [], 1):
        wo = f"Befund {i}"
        if not isinstance(b, dict):
            f.append(f"{wo}: kein Objekt")
            continue
        art = planer._wahl(b.get("art"), BEFUND_ARTEN, "art", wo, f)
        aus["befunde"].append({"art": art, "themen": _themen(b.get("themen"), frei, wo, f),
                               "text": _text(b.get("text"), "text", wo, f), "vorschlag": _text(b.get("vorschlag"), "vorschlag", wo, f, pflicht=False)})
    for i, q in enumerate(daten.get("fragen") or [] if isinstance(daten.get("fragen") or [], list) else [], 1):
        wo = f"Frage {i}"
        if not isinstance(q, dict):
            f.append(f"{wo}: kein Objekt")
            continue
        opt = q.get("optionen")
        if not isinstance(opt, dict) or len(opt) < 2:
            f.append(f"{wo}: optionen braucht mindestens zwei Einträge {{\"A\": \"…\", \"B\": \"…\"}}")
            opt = {}
        optionen = {}
        for k, t in opt.items():
            if not kern.OPTION_KENN.fullmatch(str(k)):
                f.append(f"{wo}: Option „{k}“ – Kürzel wie A, B")
            else:
                optionen[str(k)] = _text(t, "option", f"{wo} Option {k}", f)
        emp = str(q.get("empfehlung") or "").strip()
        if optionen and emp not in optionen:
            f.append(f"{wo}: empfehlung „{emp}“ ist keine der Optionen")
        aus["fragen"].append({"frage": _text(q.get("frage"), "frage", wo, f), "optionen": optionen, "empfehlung": emp,
                              "grund": _text(q.get("grund"), "grund", wo, f), "themen": _themen(q.get("themen"), frei, wo, f, pflicht=False)})
    schluessel = set()
    ms = daten.get("meilensteine") or [] if isinstance(daten.get("meilensteine") or [], list) else []
    if not ms:
        f.append("meilensteine fehlt (mindestens einer)")
    for i, m in enumerate(ms, 1):
        wo = f"Meilenstein {i}"
        if not isinstance(m, dict):
            f.append(f"{wo}: kein Objekt")
            continue
        s = str(m.get("schluessel") or "").strip().upper()
        if not re.fullmatch(r"M\d+", s):
            f.append(f"{wo}: schluessel „{m.get('schluessel')}“ – Form M1")
        elif s in schluessel:
            f.append(f"{wo}: schluessel {s} doppelt")
        schluessel.add(s)
        wo = f"Meilenstein {s or i}"
        listen = {}
        for k in ("nach", "gleichzeitig"):
            v = m.get(k) or []
            if not isinstance(v, list):
                f.append(f"{wo}: {k} ist keine Liste")
                v = []
            listen[k] = [str(x).strip().upper() for x in v]
        aus["meilensteine"].append({
            "schluessel": s, "titel": _text(m.get("titel"), "titel", wo, f), "ziel": _text(m.get("ziel"), "ziel", wo, f),
            "themen": _themen(m.get("themen"), frei, wo, f), "fertig_wenn": _text(m.get("fertig_wenn"), "fertig_wenn", wo, f),
            "endet_mit": planer._wahl(m.get("endet_mit"), tuple(planer.ENDET_MIT), "endet_mit", wo, f),
            "nach": listen["nach"], "gleichzeitig": listen["gleichzeitig"],
            "aufwand": planer._wahl(m.get("aufwand"), AUFWAND, "aufwand", wo, f, klein=False),
            "tage": _zahl(m.get("tage"), "tage", wo, f), "usd": _zahl(m.get("usd"), "usd", wo, f)})
    for m in aus["meilensteine"]:
        for k in ("nach", "gleichzeitig"):
            for v in m[k]:
                if v not in schluessel:
                    f.append(f"Meilenstein {m['schluessel']}: {k} {v} gibt es im Plan nicht")
                elif v == m["schluessel"]:
                    f.append(f"Meilenstein {m['schluessel']}: {k} verweist auf sich selbst")
    kreis = planer._kreis({m["schluessel"]: [v for v in m["nach"] if v in schluessel] for m in aus["meilensteine"]})
    if kreis:
        f.append("Abhängigkeiten im Kreis: " + " → ".join(kreis))
    drin = {tid for m in aus["meilensteine"] for tid in m["themen"]}
    begruendet = {tid for b in aus["befunde"] if b["art"] == "abdeckung" for tid in b["themen"]}
    fehlt = sorted(set(frei) - drin - begruendet)
    if fehlt:
        f.append("Abdeckung: " + ", ".join(f"TH{t}" for t in fehlt) + " in keinem Meilenstein und ohne Befund „abdeckung“")
    if f:
        raise planer.PlanFehler(f)
    return aus


def reihenfolge(entwurf):
    """Meilensteine so, dass jeder nach seinen Vorgängern kommt (stabil: sonst wie geliefert)."""
    rest, fertig, aus = list(entwurf["meilensteine"]), set(), []
    while rest:
        for m in rest:
            if all(v in fertig for v in m["nach"]):
                aus.append(m)
                fertig.add(m["schluessel"])
                rest.remove(m)
                break
        else:
            raise planer.PlanFehler(["Abhängigkeiten im Kreis"])
    return aus


def entwurf_eintragen(con, pid, fassung, ergebnis, modell=None, usd=None, lauf=None, fehler=None, frei=None):
    """Das Ergebnis eines Laufs als Fassung eintragen (geprüft – oder mit den Funden als Fehler). Fragen des Planers gehen als
    Fragen der AMW an den Lead (A2021: nur der Lead fragt den Menschen), der Lead bekommt eine Meldung. Rückgabe: das Ereignis."""
    frei = themen_frei(con, pid) if frei is None else frei
    entwurf, funde = None, None
    if fehler:
        funde = [fehler] if isinstance(fehler, str) else list(fehler)
    else:
        try:
            entwurf = pruefen(planer.json_aus_text(ergebnis) if isinstance(ergebnis, str) else ergebnis, frei)
        except planer.PlanFehler as e:
            funde = e.fehler
    werte = {"fassung": fassung, "modell": modell, "usd": usd, "lauf": lauf, "themen": _stand(frei)}
    werte.update({"entwurf": entwurf} if entwurf else {"fehler": funde})
    lead = kern.lead(con, pid) or kern.ENTWICKLER
    kosten = f"{usd:.2f} $" if isinstance(usd, (int, float)) else "Kosten unbekannt"
    with db.schreiben(con):
        eid = _ereignis(con, pid, "AMW", ENTWURF, **werte)
        if funde or not entwurf:
            funde = funde or ["kein Entwurf"]
            kern._posten(con, pid, "AMW", lead, "meldung", f"Grobplan Fassung {fassung}: Planer-Ergebnis passt nicht"[:140],
                         "Funde:\n" + "\n".join(f"- {x}" for x in funde[:20]) + f"\n\n({modell or '–'}, {kosten})\n"
                         "Neu planen lassen: amw thema grobplan --neu")
        else:
            kern._posten(con, pid, "AMW", lead, "meldung",
                         f"Grobplan Fassung {fassung}: {len(entwurf['meilensteine'])} Meilensteine, {len(entwurf['befunde'])} Befunde,"
                         f" {len(entwurf['fragen'])} Fragen – Ja oder neu planen"[:140],
                         zusammenfassung(entwurf) + f"\n\n({modell or '–'}, {kosten})\nAnsehen: amw thema grobplan · Ja: amw thema grobplan-ja")
    for q in (entwurf or {}).get("fragen") or []:
        try:
            kern.frage_neu(con, pid, "AMW", "tl", f"Grobplan Fassung {fassung}: {q['frage']}"[:200], list(q["optionen"].items()),
                           empfehlung=q["empfehlung"], grund=q["grund"], pruefen=False)
        except kern.AmwFehler:
            pass                                          # eine Frage, die nicht durchgeht, hält den Entwurf nicht auf
    return {**werte, "id": eid}


def zusammenfassung(entwurf):
    z = []
    for m in reihenfolge(entwurf):
        z.append(f"{m['schluessel']} {m['titel']} · {m['aufwand']}" + (f" · {m['tage']:g} Tage" if m.get("tage") is not None else "")
                 + (f" · {m['usd']:.0f} $" if m.get("usd") is not None else "") + f" · endet mit {planer.ENDET_MIT[m['endet_mit']]}"
                 + (f" · nach {', '.join(m['nach'])}" if m["nach"] else "") + (f" · gleichzeitig mit {', '.join(m['gleichzeitig'])}"
                                                                              if m["gleichzeitig"] else ""))
        z.append(f"   Themen: {', '.join(f'TH{t}' for t in m['themen'])} · fertig, wenn: {m['fertig_wenn']}")
    for b in entwurf["befunde"]:
        z.append(f"Befund ({b['art']}): {b['text']}" + (f" → {b['vorschlag']}" if b.get("vorschlag") else ""))
    for q in entwurf["fragen"]:
        z.append(f"Frage: {q['frage']} (Empfehlung {q['empfehlung']})")
    return "\n".join(z)


def fassungen(con, pid):
    """Alle Fassungen, älteste zuerst: [{"fassung", "id", "zeit_utc", "modell", "usd", "fehler", "meilensteine", "befunde",
    "fragen", "angenommen"}] – plus eine laufende ohne Entwurf ({"laeuft": True})."""
    ja = angenommen(con, pid)
    aus = []
    for e in _ereignisse(con, pid, ENTWURF):
        d = e.get("entwurf") or {}
        aus.append({"fassung": e.get("fassung"), "id": e["id"], "zeit_utc": e["zeit_utc"], "modell": e.get("modell"), "usd": e.get("usd"),
                    "fehler": e.get("fehler"), "meilensteine": len(d.get("meilensteine") or []), "befunde": len(d.get("befunde") or []),
                    "fragen": len(d.get("fragen") or []), "angenommen": bool(ja and ja.get("entwurf") == e["id"])})
    l = laeuft(con, pid)
    if l:
        aus.append({"fassung": l.get("fassung"), "laeuft": True, "zeit_utc": l["zeit_utc"], "modell": l.get("modell")})
    return aus


def entwurf(con, pid, fassung=None):
    """Der Entwurf einer Fassung (jüngste ohne Angabe) als Ereignis-dict oder None."""
    alle = _ereignisse(con, pid, ENTWURF)
    if fassung is not None:
        alle = [e for e in alle if e.get("fassung") == int(fassung)]
    return alle[-1] if alle else None


# --- Grobplan-Ja: Meilensteine anlegen -------------------------------------------------------------------------------------

def _ziel(m):
    z = m["ziel"]
    fehlt = [t for t in m["themen"] if not re.search(rf"\bTH{t}\b", z)]
    return z + (" · Themen: " + ", ".join(f"TH{t}" for t in fehlt) if fehlt else "")


def annehmen(con, pid, von, fassung=None):
    """Grobplan-Ja: die Meilensteine der Fassung anlegen (in der Reihenfolge der Abhängigkeiten), je Meilenstein die Themen im
    Ziel und die Grob-Freigabe vermerken. Nur einmal; nur, solange die freigegebenen Themen dieselben sind wie beim Planen.
    Rückgabe: {"angenommen", "ja_fehlt" | "angelegt": {"M1": "M7"}}."""
    from . import planansicht, planung
    e = entwurf(con, pid, fassung)
    if not e:
        raise kern.AmwFehler("Es gibt keinen Grobplan" + (f" in Fassung {fassung}" if fassung is not None else ""))
    if not e.get("entwurf"):
        raise kern.AmwFehler(f"Grobplan Fassung {e.get('fassung')} passte nicht zum Schema – neu planen lassen")
    if angenommen(con, pid):
        raise kern.AmwFehler("Der Grobplan ist schon angenommen")
    if (e.get("themen") or {}) != _stand(themen_frei(con, pid)):
        raise kern.AmwFehler(f"Seit Fassung {e.get('fassung')} haben sich die freigegebenen Themen geändert – Konzept neu abschließen")
    with db.schreiben(con):
        wer, namen = _stimme(con, pid, von, JA_STIMME, e["id"], "grob")
        if wer == "fehlt":
            return {"angenommen": False, "ja_fehlt": namen}
        if angenommen(con, pid):
            raise kern.AmwFehler("Der Grobplan ist schon angenommen")
        merke = _ereignis(con, pid, von if wer == "mensch" else "AMW", JA, fassung=e.get("fassung"), entwurf=e["id"], angelegt={},
                          durch=namen, laeuft=True)
    anleger = von if kern.ist_lead(con, pid, von) else (kern.lead(con, pid) or kern.ENTWICKLER)
    angelegt, bogen = {}, {}
    try:
        for m in reihenfolge(e["entwurf"]):
            bid = planung.bogen_neu(con, pid, anleger, m["titel"], ziel=_ziel(m),
                                    abnahme=f"{m['fertig_wenn']} (endet mit {planer.ENDET_MIT[m['endet_mit']]})")
            bogen[m["schluessel"]] = bid
            angelegt[m["schluessel"]] = f"M{planung.bogen_zeile(con, pid, bid)['nr']}"
        with db.schreiben(con):
            for bid in bogen.values():                    # das Ja zum Grobplan ist die Grob-Freigabe je Meilenstein
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von if wer == "mensch" else "AMW",
                             art=planansicht.FREI, bogen_id=bid,
                             text=json.dumps({"bogen": bid, "art": "grob", "an": True, "fp": planansicht.fingerabdruck(con, pid, bid, "grob"),
                                              "grobplan": e["id"], **({"durch": namen, "regel_von": "B2913"} if wer != "mensch" else {})},
                                             ensure_ascii=False))
            con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?",
                        (json.dumps({"fassung": e.get("fassung"), "entwurf": e["id"], "angelegt": angelegt, "durch": namen,
                                     "nach": {angelegt[m["schluessel"]]: [angelegt[v] for v in m["nach"]] for m in e["entwurf"]["meilensteine"]},
                                     "gleichzeitig": {angelegt[m["schluessel"]]: [angelegt[v] for v in m["gleichzeitig"]]
                                                      for m in e["entwurf"]["meilensteine"]}}, ensure_ascii=False), merke))
    except Exception as x:
        with db.schreiben(con):
            if not angelegt:                              # nichts angelegt: die Marke lösen, ein neues Ja darf es noch einmal versuchen
                con.execute("DELETE FROM plan_ereignis WHERE id = ?", (merke,))
            else:
                con.execute("UPDATE plan_ereignis SET text = ? WHERE id = ?",
                            (json.dumps({"fassung": e.get("fassung"), "entwurf": e["id"], "angelegt": angelegt, "durch": namen,
                                         "abgebrochen": str(x)[:300]}, ensure_ascii=False), merke))
                kern._posten(con, pid, "AMW", kern.lead(con, pid) or kern.ENTWICKLER, "meldung",
                             f"Grobplan Fassung {e.get('fassung')} nur teilweise angelegt"[:140],
                             f"Abbruch beim Anlegen: {str(x)[:300]}\nSchon angelegt: "
                             + ", ".join(f"{k} → {v}" for k, v in angelegt.items()) + "\nDer Rest fehlt – bitte von Hand ergänzen.")
        raise
    return {"angenommen": True, "angelegt": angelegt}


# --- Einstieg für amw-planer.py --grob -------------------------------------------------------------------------------------

def main(argv):
    import argparse
    ap = argparse.ArgumentParser(prog="amw-planer --grob")
    ap.add_argument("--projekt-id", type=int, required=True)
    ap.add_argument("--fassung", type=int, required=True)
    x = ap.parse_args(argv)
    con = db.verbinde()
    try:
        ausfuehren(con, x.projekt_id, x.fassung)
    finally:
        con.close()
