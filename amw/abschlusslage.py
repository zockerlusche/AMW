"""A2082 (B2938): wie steht der Abschluss eines Meilensteins – und wer ist dran?

Der Mensch sieht „wartet auf dich“ erst, wenn er abnehmen kann: Gesamttest, Prüfung gegen das Konzept und Abschlussbericht sind zum
aktuellen Stand da und erfüllt. Fehlt die Prüfung oder ging sie nicht, ist das Sache des Leads (er holt sie nach:
`amw bogen pruefung-starten N`); der Mensch darf die Knöpfe weiter drücken. Ohne Lead im Projekt wie bisher: der Mensch ist dran.

Laufende Meilensteine (Wartung ohne natürliches Ende): der Lead oder der Mensch schaltet sie mit `amw bogen laufend N an|aus`. Solange
ein laufender nicht vorgelegt ist, wird er nicht geprüft, nicht „bereit zur Abnahme“ gemeldet und nicht abgeschlossen; er hält auch die
Feinplanung des nächsten nicht auf. `amw bogen vorlegen N` (ohne offene Pakete) stößt dieselbe Abschlussprüfung an wie sonst; ein
neues Paket danach macht die Vorlage ungültig. Nichts davon steht im Freitext der Abnahme.

Ereignisse (plan_ereignis, Text JSON):
  bogen_laufend        {"an": bool}
  bogen_vorgelegt      {"stand"}
  abschluss_beim_lead  {"stand", "lage", "ergebnis"}   – einmal je Stand und Ergebnis
  abschluss_abnehmbar  {"stand", "ausgeliefert"}                       – „bereit zur Abnahme“ ging raus, nachdem es beim Lead lag

A2116: Vor der Auslieferung nimmt niemand ab (lage „auslieferung“, auslieferstand.py): kein Knopf, keine Meldung, niemand ist dran. Das
Ereignis abschluss_beim_lead mit dieser Lage merkt es; ist alles ausgeliefert, geht „bereit zur Abnahme“ hinaus.
"""
import json
import os

from . import db, kern

LAUFEND, VORGELEGT, BEIM_LEAD, ABNEHMBAR = "bogen_laufend", "bogen_vorgelegt", "abschluss_beim_lead", "abschluss_abnehmbar"
AUSLIEFERUNG = "auslieferung"
LEAD_KLAERT = ("fehlt", "fehler", "nicht_erfuellt", "nicht_pruefbar")


def _ereignis(con, pid, von, art, bid, **werte):
    return db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=art, bogen_id=bid,
                        text=json.dumps(werte, ensure_ascii=False))


def _letztes(con, bid, art):
    r = con.execute("SELECT id, text FROM plan_ereignis WHERE bogen_id = ? AND art = ? ORDER BY id DESC LIMIT 1", (bid, art)).fetchone()
    return (r["id"], json.loads(r["text"] or "{}")) if r else (0, {})


def stand(con, b):
    """Der Stand, zu dem die AMW die Abschlussprüfung führt – derselbe wie in planautomatik.meilenstein_projekt."""
    from . import planautomatik
    letzte = con.execute("SELECT max(coalesce(fertig_utc, geaendert_utc, angelegt_utc)) FROM aufgabe WHERE bogen_id = ?",
                         (b["id"],)).fetchone()[0] or ""
    return planautomatik._stand(con, b, letzte)


# --- laufende Meilensteine ---------------------------------------------------------------------------------------------------

def laufend(con, bid):
    return bool(_letztes(con, bid, LAUFEND)[1].get("an"))


def ruht(con, b):
    """Laufend und (zum aktuellen Stand) nicht vorgelegt – er kommt nicht zur Abnahme."""
    sid, schalter = _letztes(con, b["id"], LAUFEND)
    if not schalter.get("an"):
        return False
    vid, v = _letztes(con, b["id"], VORGELEGT)
    return vid < sid or v.get("stand") != stand(con, b)


def _darf(con, pid, von, was):
    if not (von == kern.ENTWICKLER or kern.ist_lead(con, pid, von)):
        raise kern.AmwFehler(f"{was}: nur der Lead oder der Mensch")


def _bogen(con, pid, bid):
    b = con.execute("SELECT * FROM bogen WHERE id = ? AND projekt_id = ?", (bid, pid)).fetchone()
    if not b:
        from . import meilensteine
        raise kern.AmwFehler(meilensteine.unbekannt(bid))
    if b["status"] not in ("geplant", "aktiv"):
        raise kern.AmwFehler(f"M{b['nr']} „{b['titel']}“ ist {b['status']}")
    return b


def schalten(con, pid, von, bid, an):
    """`amw bogen laufend N an|aus`. Rückgabe: Text."""
    _darf(con, pid, von, "Einen Meilenstein als laufend schalten")
    b = _bogen(con, pid, bid)
    name = f"M{b['nr']} „{b['titel']}“"
    if laufend(con, bid) == an:
        return f"{name} ist schon {'laufend' if an else 'nicht laufend'}"
    with db.schreiben(con):
        _ereignis(con, pid, von, LAUFEND, bid, an=an)
    return (f"{name} ist laufend – er kommt erst zur Abnahme, wenn du ihn vorlegst: amw bogen vorlegen M{b['nr']}" if an
            else f"{name} ist nicht mehr laufend – sind alle Pakete fertig, kommt er von selbst zur Abnahme")


def vorlegen(con, pid, von, bid):
    """`amw bogen vorlegen N`: der laufende Meilenstein kommt zur Abnahme – mit derselben Abschlussprüfung wie sonst. Text."""
    from . import abschluss, planautomatik
    _darf(con, pid, von, "Einen Meilenstein vorlegen")
    b = _bogen(con, pid, bid)
    name = f"M{b['nr']} „{b['titel']}“"
    if not laufend(con, bid):
        raise kern.AmwFehler(f"{name} ist nicht laufend – sind alle Pakete fertig, kommt er von selbst zur Abnahme")
    n = con.execute("SELECT count(*), sum(status NOT IN ('fertig', 'verworfen')) FROM aufgabe WHERE bogen_id = ?", (bid,)).fetchone()
    if not n[0]:
        raise kern.AmwFehler(f"{name} hat noch keine Pakete")
    if n[1]:
        raise kern.AmwFehler(f"{name} hat noch {'ein offenes Paket' if n[1] == 1 else f'{n[1]} offene Pakete'}"
                             " – erst fertig machen, verwerfen oder verschieben")
    if not ruht(con, b):
        raise kern.AmwFehler(f"{name} ist mit diesem Stand schon vorgelegt")
    st = stand(con, b)
    with db.schreiben(con):
        _ereignis(con, pid, von, VORGELEGT, bid, stand=st)
    if not planautomatik.mit_urteil(b):                  # ohne eigenes „fertig wenn“: der normale Weg (Vorschlag, oder die AMW schließt)
        planautomatik.meilenstein_projekt(con, pid)
        return f"{name} vorgelegt"
    if abschluss.vor_bereit(con, pid, b, st, erneut=True) == "pruefung":
        return f"{name} vorgelegt – Gesamttest und Prüfung gegen das Konzept laufen"
    planautomatik.bereit_melden(con, pid, b)
    return f"{name} vorgelegt – {TEXT[lage(con, pid, b) or 'fehlt']}"


# --- wie steht der Abschluss? ------------------------------------------------------------------------------------------------

TEXT = {AUSLIEFERUNG: "wartet auf Auslieferung", "abnehmbar": "bereit zur Abnahme", "laeuft": "Prüfung läuft", "fehlt": "Prüfung fehlt", "fehler": "Prüfung ging nicht",
        "nicht_erfuellt": "Prüfung nicht erfüllt", "nicht_pruefbar": "nicht prüfbar, Belege fehlen", "bericht": "Abschlussbericht kommt"}


def ergebnis(con, pid, b):
    """Das Prüf-Ergebnis zum aktuellen Stand – ein älteres (vor neuen Paketen) zählt nicht."""
    from . import abschluss
    return abschluss.ergebnis(con, pid, b["id"], stand(con, b))


def auslieferung(con, pid, b):
    """A2116: die fertigen Pakete, auf deren Auslieferung die Abnahme wartet – [] heißt: nichts."""
    from . import auslieferstand
    return auslieferstand.fehlt(con, pid, b["id"])


def lage(con, pid, b):
    """„auslieferung“ (A2116) | „abnehmbar“ | „laeuft“ | „fehlt“ | „fehler“ | „nicht_erfuellt“ | „nicht_pruefbar“ (A2088: nur Belege fehlen) | „bericht“ – oder None: nicht bereit zur Abnahme."""
    from . import abschluss, planautomatik, tore
    if not planautomatik.bereit_zur_abnahme(con, b):
        return None
    if auslieferung(con, pid, b):
        return AUSLIEFERUNG
    if abschluss._laeuft(con, pid, b["id"], stand(con, b)):
        return "laeuft"
    e = ergebnis(con, pid, b)
    if not e:
        return "fehlt"
    if e.get("fehler"):
        return "fehler"
    test, themen, ziel = e.get("test") or {}, e.get("themen") or [], e.get("ziel")
    themen_ok = all(x.get("erfuellt") for x in themen) and (bool(ziel.get("erfuellt")) if ziel else bool(themen))
    rot = bool(test.get("befehl") and test.get("rc") != 0)
    if not themen_ok and not rot and all(x.get("erfuellt") or x.get("zustand") == "nicht_pruefbar" for x in [*themen, *([ziel] if ziel else [])]) \
            and any(x.get("zustand") == "nicht_pruefbar" for x in [*themen, *([ziel] if ziel else [])]):
        return "nicht_pruefbar"                           # A2088: sonst ist alles erfüllt – es fehlen Belege
    if not themen_ok or rot:
        return "nicht_erfuellt"
    return "abnehmbar" if tore.bericht(con, pid, b["id"]) is not None else "bericht"


def bei_mensch(con, pid, lage_):
    """Ist der Mensch dran? Mit Lead nur, wenn er abnehmen kann; ohne Lead oder mit ausgeschaltetem Planer (dann kann niemand eine
    Prüfung nachholen) wie bisher, sobald der Meilenstein bereit ist – dieselbe Regel wie für die Nachricht (nur_lead)."""
    if lage_ == AUSLIEFERUNG:
        return False
    return lage_ == "abnehmbar" or bool(lage_ and not (kern.lead(con, pid) and pruefer_geht(con, pid)))


def pruefer_geht(con, pid):
    from . import planer
    return not (os.environ.get("AMW_PLANER_AUS") or planer.schalter_text(con, pid))


def wie_vorbehalt(con, pid, lage_):
    """A2088 (Lead #32824): alles außer „abnehmbar“ zählt beim Abnehmen wie ein Vorbehalt – Co und Lead nicht allein, der Mensch mit
    Rückfrage. Nur „fehlt“ bei ausgeschaltetem Planer nicht: dann kann niemand eine Prüfung nachholen (wie bei bei_mensch)."""
    return bool(lage_ and lage_ not in ("abnehmbar", AUSLIEFERUNG) and (lage_ != "fehlt" or pruefer_geht(con, pid)))


def nur_lead(con, pid, b):
    """Geht „bereit zur Abnahme“ noch nicht an den Menschen und den Co? Mit Lead und Prüfer, solange nicht abnehmbar. Ist der Planer
    aus, kann niemand eine Prüfung nachholen – dann wie bisher."""
    l = lage(con, pid, b)
    return l == AUSLIEFERUNG or bool(kern.lead(con, pid)) and pruefer_geht(con, pid) and l != "abnehmbar"


def melden(con, pid, b):
    """Je Dienst-Runde für einen bereiten Meilenstein: fehlt die Prüfung, erfährt es der Lead (einmal je Stand, mit dem Befehl; über
    eine gescheiterte oder nicht erfüllte meldet schon abschluss.eintragen). Ist er danach abnehmbar, geht „bereit zur Abnahme“
    raus – einmal. Rückgabe: „lead“, „abnehmbar“ oder None."""
    from . import tore
    lead = kern.lead(con, pid)
    l, st = lage(con, pid, b), stand(con, b)
    if l == AUSLIEFERUNG:                                # A2116: niemand ist dran; gemeldet wird nach der Auslieferung
        neu = {"stand": st, "lage": l, "ergebnis": None}
        if _letztes(con, b["id"], BEIM_LEAD)[1] != neu:
            with db.schreiben(con):
                _ereignis(con, pid, "AMW", BEIM_LEAD, b["id"], **neu)
        return AUSLIEFERUNG
    if not lead or not pruefer_geht(con, pid):           # hier ist der Mensch sofort dran – nach der Auslieferung einmal melden
        lid, gemeldet = _letztes(con, b["id"], BEIM_LEAD)
        if l and gemeldet.get("lage") == AUSLIEFERUNG and gemeldet.get("stand") == st and _letztes(con, b["id"], ABNEHMBAR)[0] < lid:
            with db.schreiben(con):
                _ereignis(con, pid, "AMW", ABNEHMBAR, b["id"], stand=st, ausgeliefert=True)
            tore.bericht_erstellen(con, pid, b["id"], bereit=True)
            return "abnehmbar"
        return None
    if l in LEAD_KLAERT:
        e = ergebnis(con, pid, b)
        neu = {"stand": st, "lage": l, "ergebnis": e["id"] if e else None}
        if _letztes(con, b["id"], BEIM_LEAD)[1] == neu:
            return None
        with db.schreiben(con):
            _ereignis(con, pid, "AMW", BEIM_LEAD, b["id"], **neu)
            if l == "fehlt":
                kern._posten(con, pid, "AMW", lead, "meldung", f"M{b['nr']} „{b['titel'][:60]}“: Abschlussprüfung fehlt – bitte nachholen",
                             "Alle Pakete sind fertig, aber zu diesem Stand gibt es keine Prüfung gegen das Konzept. Solange sie fehlt, wartet"
                             f" der Meilenstein nicht auf die Abnahme. Nachholen: amw bogen pruefung-starten M{b['nr']}\n"
                             f"Soll er offen bleiben (laufende Wartung): amw bogen laufend M{b['nr']} an")
        return "lead"
    if l == "abnehmbar":
        lid, gemeldet = _letztes(con, b["id"], BEIM_LEAD)
        aid, schon = _letztes(con, b["id"], ABNEHMBAR)
        if gemeldet.get("stand") != st or (aid > lid and schon.get("stand") == st):
            return None
        with db.schreiben(con):
            _ereignis(con, pid, "AMW", ABNEHMBAR, b["id"], stand=st, ausgeliefert=gemeldet.get("lage") == AUSLIEFERUNG)
        tore.bericht_erstellen(con, pid, b["id"], bereit=True)
        return "abnehmbar"
    return None
