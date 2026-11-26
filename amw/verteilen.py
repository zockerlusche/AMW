"""Verteilen an interaktive Agenten (A1927, TH157 „Wecken und Verteilen“).

Ist ein interaktiver Agent frei, gibt die AMW ihm das nächste passende startklare Paket nach dem Plan des Leads – kritischer
Pfad zuerst. Fällt ein Agent aus, geht sein Paket mit Übergabe-Notiz zurück. Eine neue Sitzung startet nur der Mensch; die AMW
schlägt sie vor.

- Frei: Agent im Terminal mit aktiver Sitzung, nicht Lead oder Co-Entwickler, kein Halt, ohne Aufgabe in „läuft“ und ohne
  Aufgabe ohne Wartegrund (wartegrund.freie_arbeit leer). A2053: Warten auf Prüfung, Stapel oder Lauf gibt ihn sofort frei,
  Warten auf eine Antwort oder ein anderes Paket erst nach 10 Minuten (wartegrund.haelt_fest).
- Kandidaten: offene Aufgaben ohne Bearbeiter in aktiven Meilensteinen, Art agent (keine p-Pakete), startklar: Status wartet,
  kein offener Wartegrund, kein Wartetext, kein offener Vorgänger. Reihenfolge: Rang, dann kritischer Pfad (die längere
  Kette offener Nachfolger zuerst), dann Nummer.
- Passt: passt() – Größe gegen das Profil (empfehlung) und Fachgebiet gegen die Art (Projekt-Einstellung verteilen_fach).
- Projekt-Einstellung verteilen = vorschlag (Vorgabe: der Lead bekommt die Zuteilung als Frage) | an (die AMW teilt zu: Auftrag
  an den Agenten mit Begründung, Meldung an den Lead) | aus.
- Ausfall: ein Agent mit Aufgabe in „läuft“, dessen Sitzung seit ausfall_min (Vorgabe 30) beendet ist (die Aufsicht des Dienstes
  prüft die Pipe – ein stiller, wartender Agent hat Puls) und keine neue hat. Die Aufgabe geht in den Pool zurück (ohne
  Bearbeiter, wartet) mit Übergabe-Notiz (letzter Commit, letzte Tätigkeit, offene Punkte); Meldung an den Lead; der Mensch
  bekommt eine Frage „Sitzung neu starten?“ – gestartet wird nie von selbst.
Ohne Schemaänderung: Ereignisse verteilt, verteil_vorschlag, ausfall (plan_ereignis).
"""
import json
import subprocess
import time

from . import db, kern, wartegrund

AUSFALL_MIN = 30
# A2147: eine Nachricht, die ganz im Weckruf stand, gilt beim Wecken als gelesen (gelesen_utc = geweckt_utc) – das ist keine
# Reaktion des Agenten. Reagiert hat er erst, wenn er selbst liest, etwas sendet oder seine Sitzung ein Hook-Ereignis meldet.
UNGELESEN_SQL = "(e.status = 'offen' OR e.gelesen_utc <= e.geweckt_utc)"


def reagiert(s, geweckt_utc):
    """Hat die Sitzung seit dem Weckruf ein Hook-Ereignis (Prompt angenommen, Halt …) gemeldet?"""
    return bool(s["ereignis_utc"] and geweckt_utc and s["ereignis_utc"] > geweckt_utc)
# Vorgabe Art → Fachgebiete (Teilwort, Groß/klein egal); je Projekt überschreibbar (verteilen_fach). Leere Liste = jedes.
FACH_VORGABE = {"text": ["text", "doku", "code"], "mechanisch": ["code"], "fehlersuche": ["code"], "oberflaeche": ["code", "grafik"],
                "sicherheit": ["code"], "konzept": ["konzept"]}
MODELL_RANG = ("haiku", "sonnet", "opus", "fable")
STUFE_RANG = ("low", "medium", "high", "xhigh", "max")


def einstellung(con, pid):
    return kern.projekt_wahl(con, pid, "verteilen")


def _einst(con, pid, k):
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        return json.loads((r[0] if r else None) or "{}").get(k)
    except ValueError:
        return None


def fach_tabelle(con, pid):
    t = dict(FACH_VORGABE)
    t.update(_einst(con, pid, "verteilen_fach") or {})
    return t


def fach_pruefen(v):
    """Projekt-Einstellung verteilen_fach: {art: [Fachgebiete]} (JSON); nur bekannte Arten, je höchstens 10 Wörter."""
    from .empfehlung import ARTEN
    if isinstance(v, str):
        try:
            v = json.loads(v) if v.strip() else {}
        except ValueError:
            raise ValueError("JSON, z. B. {\"oberflaeche\": [\"code\", \"grafik\"]}") from None
    if not isinstance(v, dict):
        raise ValueError("eine Zuordnung Art → Liste von Fachgebieten")
    aus = {}
    for art, liste in v.items():
        if art not in ARTEN:
            raise ValueError(f"Art „{art}“ – bekannt: {', '.join(ARTEN)}")
        if not isinstance(liste, list) or len(liste) > 10 or not all(isinstance(x, str) and 0 < len(x.strip()) <= 40 for x in liste):
            raise ValueError(f"{art}: Liste von höchstens 10 Fachgebieten (je bis 40 Zeichen)")
        aus[art] = [x.strip().lower() for x in liste]
    return aus


# --- frei, Kandidaten, passt -----------------------------------------------------------------------------------------------

def freie_agenten(con, pid):
    """[(kennung, sitzung)] – frei im Sinne von TH157, die am längsten freien zuerst."""
    from . import herausnehmen
    co, lead = kern.co_entwickler(con, pid), kern.lead(con, pid)
    aus = []
    for s in con.execute("SELECT s.*, a.kennung FROM sitzung s JOIN agent a ON a.id = s.agent_id WHERE a.projekt_id = ? AND a.soll = 'an'"
                         " AND a.entfernt_utc IS NULL AND coalesce(a.arbeitsweise, 'terminal') = 'terminal' AND coalesce(a.rolle, '') != 'lead'"
                         " AND s.zustand = 'aktiv' AND s.schluessel_datei IS NOT NULL ORDER BY coalesce(s.ereignis_utc, s.gestartet_utc)",
                         (pid,)).fetchall():
        k = s["kennung"]
        if k in (co, lead) or kern.halt_gilt(con, pid, k) or herausnehmen.ist(con, pid, k) or wartegrund.freie_arbeit(con, pid, k):
            continue                                                                        # A2095: ein Herausgenommener bekommt nichts
        if wartegrund.haelt_fest(con, pid, k):                # A2053: Antwort/Paket in den ersten 10 min – Prüfung/Stapel/Lauf nie
            continue
        if k not in [x for x, _ in aus]:
            aus.append((k, s))
    return aus


def _tiefe(con, aid, gesehen=None):
    """Länge der längsten Kette offener Nachfolger (kritischer Pfad ab dieser Aufgabe)."""
    gesehen = (gesehen or set()) | {aid}
    nach = [r[0] for r in con.execute("SELECT d.nach FROM abhaengigkeit d JOIN aufgabe a ON a.id = d.nach WHERE d.vor = ?"
                                      " AND a.status NOT IN ('fertig', 'verworfen')", (aid,)) if r[0] not in gesehen]
    return 1 + max((_tiefe(con, n, gesehen) for n in nach), default=0) if nach else 0


def kandidaten(con, pid):
    """Startklare Aufgaben ohne Bearbeiter in aktiven Meilensteinen, Art agent – in der Reihenfolge der Zuteilung."""
    from . import planung
    aus = []
    for r in wartegrund.freie_bogen_aufgaben(con, pid):
        a = con.execute("SELECT * FROM aufgabe WHERE id = ?", (r["id"],)).fetchone()
        if a["status"] != "wartet" or wartegrund.offene(con, a["id"]) or (a["wartet_auf"] or "").strip() \
                or planung.offene_vorgaenger(con, a["id"]):
            continue
        aus.append((a["rang"] if a["rang"] is not None else 999999, -_tiefe(con, a["id"]), a["id"], a))
    if not aus:
        return []
    from . import reihenfolge                            # A1941 (K5): kritischer Pfad vor Rang – die berechnete Reihenfolge
    platz = reihenfolge.plaetze(con, pid)
    return [(x[3], -x[1]) for x in sorted(aus, key=lambda x: (platz.get(x[2], 10 ** 9), x[2]))]


def _rang(liste, wert):
    w = str(wert or "").lower()
    return max((i for i, x in enumerate(liste) if x in w), default=None)


def passt(con, pid, kennung, a):
    """(ergebnis, Gründe) mit ergebnis „ja“ | „schwach“ | „nein“ (CCamwTL #29773, Option A).
    Größe: das Profil (Modell/Denkaufwand) ist nicht schwächer als die Empfehlung für die Aufgabe (empfehlung). Schwächer →
    „schwach“: nie selbst zuteilen, nur dem Lead vorschlagen – Modell und Denkaufwand wechseln in einer laufenden Sitzung nicht
    (TH159). Ein Profil ohne Modell oder Denkaufwand passt („offen“). Fachgebiet: ein Wort aus der Tabelle der Art
    (verteilen_fach) steht im Fachgebiet des Agenten; sonst „nein“. Ohne Fachgebiet oder ohne Art passt es. Die Gründe nennen
    beide Treffer, damit der Lead die Zuteilung nachvollziehen kann."""
    from . import empfehlung
    g = con.execute("SELECT modell, denkstufe, fachgebiet FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, kennung)).fetchone()
    fach = (g["fachgebiet"] or "").strip() if g else ""
    if fach and a["art"]:
        erlaubt = fach_tabelle(con, pid).get(a["art"]) or []
        treffer = [w for w in erlaubt if w in fach.lower()]
        if erlaubt and not treffer:
            return "nein", [f"Fachgebiet „{fach}“ passt nicht zur Art {a['art']} ({', '.join(erlaubt)})"]
        fach_grund = (f"Fach-Treffer „{treffer[0]}“ im Fachgebiet {fach} (Art {a['art']})" if treffer
                      else f"Fach: Art {a['art']} ohne Vorgabe")
    else:
        fach_grund = "Fach: " + ("Aufgabe ohne Art" if fach else f"{kennung} ohne Fachgebiet")
    v = empfehlung.fuer_aufgabe(con, pid, a["id"])
    if not v:
        groesse_grund = "Größe: Aufgabe ohne Größe oder Art – keine Empfehlung"
    elif not (g and g["modell"] and g["denkstufe"]):
        groesse_grund = f"Größe: Profil offen (Empfehlung {v['modell']}/{v['denkstufe']})"
    else:
        m, s = _rang(MODELL_RANG, g["modell"]), _rang(STUFE_RANG, g["denkstufe"])
        vm, vs = MODELL_RANG.index(v["modell"]), STUFE_RANG.index(v["denkstufe"])
        if m is not None and s is not None and (m < vm or (m == vm and s < vs)):
            return "schwach", [f"A{a['id']} bräuchte {v['modell']}/{v['denkstufe']}, {kennung} hat {g['modell']}/{g['denkstufe']}",
                               fach_grund]
        groesse_grund = f"Größe: Profil {g['modell']}/{g['denkstufe']} ≥ Empfehlung {v['modell']}/{v['denkstufe']} ({a['groesse']}, {a['art']})"
    return "ja", [fach_grund, groesse_grund]


# --- Verteilen -------------------------------------------------------------------------------------------------------------

def offener_vorschlag(con, pid, kennung):
    """A1927 (P374): die Aufgabe eines noch offenen Vorschlags an diesen Agenten (noch ohne Bearbeiter, nicht fertig) oder None."""
    for r in con.execute("SELECT aufgabe_id FROM plan_ereignis WHERE projekt_id = ? AND art = 'verteil_vorschlag' AND text LIKE ?"
                         " ORDER BY id DESC", (pid, f"{kennung}:%")).fetchall():
        a = con.execute("SELECT id FROM aufgabe WHERE id = ? AND coalesce(agent, '') = '' AND status NOT IN ('fertig', 'verworfen')",
                        (r[0],)).fetchone()
        if a:
            return a["id"]
    return None


def _schon(con, pid, art, text):
    return con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND text = ?", (pid, art, text)).fetchone()


def verteilen(con, pid):
    """Eine Runde für ein Projekt: je freiem Agenten das erste passende Paket – zugeteilt (an) oder vorgeschlagen. Rückgabe: Texte."""
    wie = einstellung(con, pid)
    if wie == "aus":
        return []
    lead = kern.lead(con, pid)
    frei = freie_agenten(con, pid)
    if not frei:
        return []
    vergeben, aus = set(), []
    liste = kandidaten(con, pid)
    for k, _ in frei:
        for a, tiefe in liste:
            if a["id"] in vergeben:
                continue
            from . import arbeitspaket, waechter
            if n := arbeitspaket.nebenlaeufer(con, pid, a["id"]):   # A2153 (TH165): wartet, bis das andere nicht mehr arbeitet
                waechter.protokollieren(con, pid, a["id"], waechter._nein(16, n[1]))
                vergeben.add(a["id"])
                continue
            ergebnis, gruende = passt(con, pid, k, a)
            if ergebnis == "nein":
                continue
            grund = "; ".join([f"Rang {a['rang']}", f"kritischer Pfad: {tiefe} offene Nachfolger" if tiefe else "ohne Nachfolger",
                               *gruende])
            if ergebnis == "schwach":                            # #29773 (2): nie selbst zuteilen, nur vorschlagen
                zeichen = f"{k}:{a['id']}"
                if not _schon(con, pid, "verteil_vorschlag", zeichen) and lead and lead != k:
                    with db.schreiben(con):
                        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="verteil_vorschlag",
                                     aufgabe_id=a["id"], text=zeichen)
                        kern._posten(con, pid, "AMW", lead, "frage", f"Vorschlag: A{a['id']} an {k}? – {gruende[0]}"[:200],
                                     f"{k} ist frei, A{a['id']} „{a['titel'][:90]}“ ist das nächste startklare Paket nach deinem Plan"
                                     f" ({grund}). Das Profil ist schwächer als die Empfehlung – Modell und Denkaufwand wechseln in einer"
                                     " laufenden Sitzung nicht (TH159), deshalb teilt die AMW nicht selbst zu.\nTrotzdem zuteilen:"
                                     f" amw aufgabe aendern {a['id']} --agent {k} · oder eine passende Sitzung starten lassen.",
                                     aufgabe_id=a["id"])
                    aus.append(f"Vorschlag A{a['id']} an {k} (Profil schwächer)")
                vergeben.add(a["id"])
                break                                            # der Plan geht vor: nicht am kritischen Pfad vorbei zuteilen
            if wie == "an":
                with db.schreiben(con):
                    n = con.execute("UPDATE aufgabe SET agent = ? WHERE id = ? AND coalesce(agent, '') = ''", (k, a["id"])).rowcount
                    if not n:
                        continue                                 # inzwischen von jemandem zugeteilt
                    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="verteilt", aufgabe_id=a["id"],
                                 text=json.dumps({"aufgabe": a["id"], "agent": k, "grund": grund}, ensure_ascii=False))
                    kern._posten(con, pid, "AMW", k, "auftrag", f"A{a['id']} ist dir zugeteilt: {a['titel'][:90]}",
                                 f"Du warst frei, und A{a['id']} ist das nächste passende startklare Paket nach dem Plan ({grund}).\n"
                                 f"Starten: amw aufgabe start {a['id']} · ganz lesen: amw aufgabe zeige {a['id']}", aufgabe_id=a["id"])
                    if lead and lead != k:
                        kern._posten(con, pid, "AMW", lead, "meldung", f"Verteilt: A{a['id']} an {k}",
                                     f"{k} war frei. A{a['id']} „{a['titel'][:90]}“ – {grund}. Zurück: amw aufgabe aendern {a['id']}"
                                     " --agent <andere> · abschalten: amw projekt einstellen verteilen=vorschlag|aus", aufgabe_id=a["id"])
                aus.append(f"A{a['id']} an {k} ({grund})")
            else:
                zeichen = f"{k}:{a['id']}"
                if _schon(con, pid, "verteil_vorschlag", zeichen) or not lead or lead == k:
                    vergeben.add(a["id"])
                    break                                        # schon vorgeschlagen: nicht jede Runde wieder
                with db.schreiben(con):
                    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="verteil_vorschlag",
                                 aufgabe_id=a["id"], text=zeichen)
                    kern._posten(con, pid, "AMW", lead, "frage", f"Vorschlag: A{a['id']} an {k}? ({a['titel'][:70]})",
                                 f"{k} ist frei. Nächstes passendes startklares Paket nach deinem Plan: A{a['id']} „{a['titel'][:90]}“ –"
                                 f" {grund}.\nZuteilen: amw aufgabe aendern {a['id']} --agent {k} · die AMW selbst zuteilen lassen:"
                                 " amw projekt einstellen verteilen=an", aufgabe_id=a["id"])
                aus.append(f"Vorschlag A{a['id']} an {k} ({grund})")
            vergeben.add(a["id"])
            break
    return aus


# --- Ausfall ---------------------------------------------------------------------------------------------------------------

def _letzter_commit(con, pid, aid):
    ordner = kern.projekt_ordner(con, pid)
    if not ordner:
        return None
    try:
        r = subprocess.run(["git", "-C", ordner, "log", "--all", "-1", "--format=%h %s (%cr)", f"--grep=A{aid}\\b"], capture_output=True,
                           text=True, encoding="utf-8", errors="replace", timeout=30, stdin=subprocess.DEVNULL,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        return r.stdout.strip()[:200] or None
    except (OSError, subprocess.SubprocessError):
        return None


def uebergabe(con, pid, a, s=None):
    """Übergabe-Notiz für den, der übernimmt: letzter Commit zur Aufgabe, letzte Tätigkeit, offene Kriterien und Wartegründe."""
    from . import planung
    teile = [f"letzter Commit: {_letzter_commit(con, pid, a['id']) or '–'}"]
    if s is not None and s["taetigkeit"]:
        teile.append(f"zuletzt: {s['taetigkeit'][:200]}")
    offen = [k["text"] for k in planung._json(a["kriterien"], []) if not k.get("erfuellt")]
    if offen:
        teile.append("offene Kriterien: " + " | ".join(x[:80] for x in offen[:5]))
    gr = [g["bezug"] for g in wartegrund.offene(con, a["id"])]
    if gr:
        teile.append("Wartegründe: " + ", ".join(gr))
    return " · ".join(teile)


def _frist_min(con, pid):
    try:
        return int(_einst(con, pid, "ausfall_min") or AUSFALL_MIN)
    except (TypeError, ValueError):
        return AUSFALL_MIN


def _laufende(con, pid):
    """Aufgaben in „läuft“ bei Agenten im Terminal, die nicht Lead sind."""
    return con.execute("SELECT a.* FROM aufgabe a JOIN agent g ON g.projekt_id = a.projekt_id AND g.kennung = a.agent WHERE a.projekt_id = ?"
                       " AND a.status = 'laeuft' AND coalesce(g.rolle, '') != 'lead' AND coalesce(g.arbeitsweise, 'terminal') = 'terminal'",
                       (pid,)).fetchall()


def _in_pool(con, pid, a, k, s, zeichen, lead, kurz, warum, frage=None, grund=None):
    """Aufgabe `a` von Agent `k` ohne Bearbeiter zurück in den Pool: Ereignisse `ausfall` (zeichen) und `uebergabe` (Notiz),
    Meldung an den Lead (`kurz`, `warum`), mit `frage` auch eine Frage an den Menschen (`grund`). Kein Prozess wird beendet,
    nichts gestartet."""
    notiz = uebergabe(con, pid, a, s)
    with db.schreiben(con):
        con.execute("UPDATE aufgabe SET agent = NULL, status = 'wartet' WHERE id = ?", (a["id"],))
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="ausfall", aufgabe_id=a["id"], text=zeichen)
        db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="uebergabe", aufgabe_id=a["id"],
                     text=json.dumps({"aufgabe": a["id"], "agent": k, "notiz": notiz}, ensure_ascii=False))
        if lead:
            kern._posten(con, pid, "AMW", lead, "meldung", kurz,
                         f"{warum} A{a['id']} „{a['titel'][:90]}“ lief bei {k} und steht jetzt ohne Bearbeiter im Pool.\nÜbergabe: {notiz}\n"
                         f"Neu zuteilen: amw aufgabe aendern {a['id']} --agent <Agent>. "
                         + (f"{kern.entwickler_name(con, pid)} hat die Frage, ob die Sitzung neu starten soll – " if frage else "")
                         + "die AMW startet nie selbst.", aufgabe_id=a["id"])
    if not frage:
        return
    try:
        kern.frage_neu(con, pid, "AMW", "entwickler", frage,
                       [("A", f"Ja – {k} in der Workbench › Agenten neu starten"), ("B", "Nein – die Aufgabe bekommt ein anderer")],
                       empfehlung="A", grund=grund, aufgabe_id=a["id"], pruefen=False)
    except kern.AmwFehler:
        pass


def ausfall(con, pid, jetzt=None):
    """Agenten mit Aufgabe in „läuft“, deren Sitzung seit ausfall_min beendet ist → Aufgabe zurück in den Pool. Rückgabe: Texte."""
    jetzt = jetzt or time.time()
    grenze_min = _frist_min(con, pid)
    lead = kern.lead(con, pid)
    aus = []
    for a in _laufende(con, pid):
        k = a["agent"]
        if k in (kern.ENTWICKLER, lead):
            continue
        s = con.execute("SELECT s.* FROM sitzung s JOIN agent g ON g.id = s.agent_id WHERE g.projekt_id = ? AND g.kennung = ?"
                        " ORDER BY s.id DESC LIMIT 1", (pid, k)).fetchone()
        if not s or s["zustand"] == "aktiv" or not s["beendet_utc"]:
            continue                                             # lebt (oder noch nie gestartet: kein Ausfall)
        if a["begonnen_utc"] and s["beendet_utc"] < a["begonnen_utc"]:
            continue                                             # Aufgabe nach dem Ende begonnen (z. B. von Hand)
        if (jetzt - wartegrund._sek(s["beendet_utc"])) / 60 < grenze_min:
            continue                                             # Zeit für einen Neustart
        zeichen = f"{k}:{s['id']}:{a['id']}"
        if _schon(con, pid, "ausfall", zeichen):
            continue
        _in_pool(con, pid, a, k, s, zeichen, lead, f"Ausfall: {k} – A{a['id']} zurück in den Pool",
                 f"Die Sitzung von {k} ist seit {s['beendet_utc'][11:16]} UTC beendet (seit über {grenze_min} min, keine neue).",
                 f"Sitzung von {k} neu starten? (beendet, A{a['id']} ging zurück in den Pool)",
                 f"{k} hatte A{a['id']} in Arbeit; die Übergabe-Notiz liegt beim Lead.")
        aus.append(f"Ausfall {k}: A{a['id']} zurück in den Pool")
    return aus


def still(con, pid, jetzt=None):
    """A2147 (TH157 Ausfälle): Ein Agent (nicht Lead) mit lebender Sitzung und laufendem Paket wurde geweckt, hat nicht geantwortet
    und wurde einmal nachgeweckt (Dienst.nachwecken, Ereignis „nachgeweckt“). Ist das Nachwecken `ausfall_min` her, die Nachricht
    noch ungelesen, hat er seit dem ersten Weckruf nichts gesendet und arbeitet er nicht gerade, geht sein Paket mit Übergabe-Notiz
    in den Pool mit Meldung an den Lead – aber nur mit `verteilen = an`; sonst bekommt der Lead einen Vorschlag (TL #33782; keine
    Frage an den Menschen). Nie im Halt oder in der Pause; kein Prozess wird beendet, nichts neu gestartet. Rückgabe: Texte."""
    from . import pause
    from .dienst import arbeitet_gerade
    jetzt = jetzt or time.time()
    if pause._letzte(con, pid):
        return []
    grenze_min = _frist_min(con, pid)
    grenze = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(jetzt - grenze_min * 60))
    lead = kern.lead(con, pid)
    aus = []
    for a in _laufende(con, pid):
        k = a["agent"]
        if k in (kern.ENTWICKLER, lead) or kern.halt_gilt(con, pid, k):
            continue
        s = con.execute("SELECT s.* FROM sitzung s JOIN agent g ON g.id = s.agent_id WHERE g.projekt_id = ? AND g.kennung = ?"
                        " AND s.zustand = 'aktiv' ORDER BY s.id DESC LIMIT 1", (pid, k)).fetchone()
        if not s or arbeitet_gerade(s, jetzt):
            continue                                             # ohne lebende Sitzung: das ist der Ausfall oben; wer arbeitet, behält
        n = con.execute(
            "SELECT n.id, n.kurz, e.geweckt_utc, p.zeit_utc AS nachgeweckt FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
            " JOIN plan_ereignis p ON p.projekt_id = n.projekt_id AND p.art = 'nachgeweckt' AND p.text = CAST(n.id AS TEXT)"
            " WHERE e.agent = ? AND n.projekt_id = ? AND " + UNGELESEN_SQL + " AND e.geweckt_utc >= ? AND p.zeit_utc <= ?"
            " AND NOT EXISTS (SELECT 1 FROM nachricht x WHERE x.projekt_id = n.projekt_id AND x.von = e.agent AND x.zeit_utc > e.geweckt_utc)"
            " ORDER BY p.zeit_utc LIMIT 1", (k, pid, s["gestartet_utc"], grenze)).fetchone()
        if not n or reagiert(s, n["geweckt_utc"]):
            continue
        zeichen = f"still:{k}:{s['id']}:{a['id']}"
        warum = (f"{k} hat auf den Weckruf zu #{n['id']} „{(n['kurz'] or '')[:60]}“ ({n['geweckt_utc'][11:16]} UTC) und das Nachwecken"
                 f" ({n['nachgeweckt'][11:16]} UTC) über {grenze_min} min nicht reagiert und arbeitet nicht.")
        if einstellung(con, pid) == "an":                        # TL #33782: die AMW verteilt selbst – dann gibt sie auch zurück
            if _schon(con, pid, "ausfall", zeichen):
                continue
            _in_pool(con, pid, a, k, s, zeichen, lead, f"Still: {k} – A{a['id']} zurück in den Pool", warum)
            aus.append(f"Still {k}: A{a['id']} zurück in den Pool")
            continue
        if _schon(con, pid, "ausfall_vorschlag", zeichen) or not lead:   # vorschlag (und aus): nur ein Vorschlag an den Lead
            continue
        with db.schreiben(con):
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von="AMW", art="ausfall_vorschlag", aufgabe_id=a["id"],
                         text=zeichen)
            kern._posten(con, pid, "AMW", lead, "frage", f"Vorschlag: A{a['id']} von {k} zurück in den Pool? – {k} ist still",
                         f"{warum} A{a['id']} „{a['titel'][:90]}“ läuft bei {k}.\nÜbergabe, falls du neu zuteilst: {uebergabe(con, pid, a, s)}\n"
                         f"Neu zuteilen: amw aufgabe aendern {a['id']} --agent <Agent> · die AMW selbst zurückgeben lassen:"
                         " amw projekt einstellen verteilen=an. Die AMW beendet und startet keine Sitzung.", aufgabe_id=a["id"])
        aus.append(f"Vorschlag: A{a['id']} von {k} zurück in den Pool ({k} still)")
    return aus


def runde(con, jetzt=None):
    """Dienst-Runde über alle Projekte: erst Ausfall, dann Verteilen. Rückgabe: Texte fürs Protokoll."""
    from . import herausnehmen
    aus = []
    for p in con.execute("SELECT id FROM projekt").fetchall():
        aus += ausfall(con, p["id"], jetzt)
        aus += still(con, p["id"], jetzt)                                # A2147
        aus += herausnehmen.nachziehen(con, p["id"])                     # A2095
        aus += verteilen(con, p["id"])
    return aus
