"""Token-Pause: Wie weit verschiebt die Wochen-Grenze des Kontos das Ende der Arbeit?

Die AMW schreibt den Wochenverbrauch mit (Tabelle `verbrauch`, Wert je Sitzung in Prozent). Die Grenze gilt für das
Konto – alle Projekte dieses PCs verbrauchen dasselbe Kontingent; gerechnet wird deshalb mit allen Messpunkten.

Rechenweg (steht so auch in der Oberfläche):
  1. Konto-Verlauf: je Viertelstunde ein Wert. Melden die Sitzungen sehr Verschiedenes, gilt der niedrige Wert – dann
     hat es einen Reset gegeben und einige Sitzungen zeigen noch den alten Stand.
  2. Reset: ein Abfall um mehr als 30 Punkte, auch außer der Reihe. Er ist ein Ereignis, kein Verbrauch.
  3. Tempo: Anstieg je Tag an den Tagen der letzten 14 Tage, an denen gearbeitet wurde – wahrscheinlich (Mittel) und
     vorsichtig (oberes Viertel).
  4. Diese Woche: Rest ÷ Tempo = „leer am“. Liegt das vor dem Reset, ist von dort bis zum Reset Pause.
  5. Folgewochen: 100 ÷ Tempo Tage Arbeit (höchstens 7), der Rest der Woche ist Pause.

Keine eigene Tabelle, nichts wird gespeichert; die 5-Stunden-Grenze kommt in den Messwerten nicht an und fehlt deshalb.
"""
import datetime

FENSTER_MIN = 15            # Raster des Konto-Verlaufs
RESET_ABFALL = 30.0         # Punkte: so viel weniger als zuvor (oder Uneinigkeit im selben Fenster) heißt Reset
TAGE = 14                   # Zeitraum für das Tempo
ARBEIT_AB = 1.0             # Punkte Anstieg, ab denen ein Tag als Arbeitstag zählt
WOCHE = 7.0


def _zeit(text):
    return datetime.datetime.strptime(text[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=datetime.timezone.utc)


def verlauf(punkte):
    """[(zeit_utc, wert)] beliebig vieler Sitzungen → [(datetime, wert)] des Kontos, ein Wert je Fenster."""
    fenster = {}
    for zeit, wert in punkte:
        if wert is None:
            continue
        t = _zeit(zeit) if isinstance(zeit, str) else zeit
        t = t.replace(minute=t.minute - t.minute % FENSTER_MIN, second=0, microsecond=0)
        lo, hi = fenster.get(t, (wert, wert))
        fenster[t] = (min(lo, wert), max(hi, wert))
    # uneinig um mehr als einen Reset-Abfall: die niedrigen Werte sind die frischen
    return [(t, lo if hi - lo > RESET_ABFALL else hi) for t, (lo, hi) in sorted(fenster.items())]


def resets(reihe):
    """Zeitpunkte, an denen der Konto-Wert um mehr als RESET_ABFALL gefallen ist."""
    return [t for (_, vorher), (t, wert) in zip(reihe, reihe[1:]) if vorher - wert > RESET_ABFALL]


def tagesanstiege(reihe, bis, tage=TAGE):
    """{datum: Anstieg in Punkten} der letzten `tage` Tage. Ein Abfall (Reset, Messrauschen) zählt nicht als Verbrauch."""
    ab = bis - datetime.timedelta(days=tage)
    aus = {}
    for (_, vorher), (t, wert) in zip(reihe, reihe[1:]):
        if t >= ab and wert > vorher:
            aus[t.date()] = aus.get(t.date(), 0.0) + (wert - vorher)
    return aus


def tempo(reihe, bis, tage=TAGE):
    """(wahrscheinlich, vorsichtig, arbeitstage) in Punkten je Tag – oder None ohne einen einzigen Arbeitstag.
    Angebrochene Tage zählen nur mit ihrem Anteil: der heutige bis jetzt, der erste Messtag ab dem ersten Messpunkt –
    sonst drückte jeder halbe Tag das Tempo."""
    if not reihe:
        return None
    erster, mitternacht = reihe[0][0], datetime.datetime.combine(bis.date(), datetime.time(), bis.tzinfo)
    summe = gewicht = 0.0
    je_tag = []
    for tag, anstieg in tagesanstiege(reihe, bis, tage).items():
        if anstieg < ARBEIT_AB:
            continue
        beginn = max(erster, datetime.datetime.combine(tag, datetime.time(), bis.tzinfo))
        ende = bis if tag == bis.date() else datetime.datetime.combine(tag, datetime.time(), bis.tzinfo) + datetime.timedelta(days=1)
        anteil = max(1 / 24, min(1.0, (ende - beginn).total_seconds() / 86400))
        summe, gewicht = summe + anstieg, gewicht + anteil
        je_tag.append(anstieg / anteil)
    if not je_tag:
        return None
    je_tag.sort()
    return summe / gewicht, je_tag[min(len(je_tag) - 1, int(0.75 * len(je_tag)))], len(je_tag)


def stand(reihe, jetzt, reset_angekuendigt=None):
    """Lage der laufenden Woche: wert, tempo, leer_utc, reset_utc, pause_tage (diese Woche), arbeitstage_je_woche,
    pause_je_woche, unsicher (Grund oder None). None, wenn es keine Messung gibt."""
    if not reihe:
        return None
    wert = reihe[-1][1]
    letzte = resets(reihe)
    tp = tempo(reihe, jetzt)
    # Reset: der angekündigte, wenn er in der Zukunft liegt; sonst eine Woche nach dem letzten beobachteten
    reset = reset_angekuendigt if reset_angekuendigt and reset_angekuendigt > jetzt else None
    if reset is None and letzte:
        reset = letzte[-1] + datetime.timedelta(days=WOCHE)
        while reset <= jetzt:
            reset += datetime.timedelta(days=WOCHE)
    aus = {"wert": round(wert, 1), "gemessen_utc": reihe[-1][0], "reset_utc": reset, "letzter_reset_utc": letzte[-1] if letzte else None,
           "tempo": None, "tempo_vorsichtig": None, "arbeitstage": 0, "leer_utc": None, "pause_tage": 0.0,
           "arbeitstage_je_woche": WOCHE, "pause_je_woche": 0.0, "unsicher": None}
    if tp is None:
        aus["unsicher"] = "kein_tempo"
        return aus
    wahrscheinlich, vorsichtig, arbeitstage = tp
    leer = jetzt + datetime.timedelta(days=max(0.0, 100.0 - wert) / wahrscheinlich)
    je_woche = min(WOCHE, 100.0 / wahrscheinlich)
    aus.update(tempo=round(wahrscheinlich, 1), tempo_vorsichtig=round(vorsichtig, 1), arbeitstage=arbeitstage, leer_utc=leer,
               arbeitstage_je_woche=round(je_woche, 2), pause_je_woche=round(WOCHE - je_woche, 2))
    if reset is not None and leer < reset:
        aus["pause_tage"] = round((reset - leer).total_seconds() / 86400, 2)
    if arbeitstage < 3:
        aus["unsicher"] = "wenige_tage"
    elif reset is None:
        aus["unsicher"] = "kein_reset"
    elif (jetzt - reihe[-1][0]).total_seconds() > 86400:
        aus["unsicher"] = "alt"
    return aus


def verschieben(lage, tage, jetzt):
    """Ein Ende in `tage` Kalendertagen ab jetzt (so rechnet die Prognose): Wie viele Tage Token-Pause fallen bis dahin
    an? Gezählt wird die Arbeit: bis „leer“ läuft sie, bis zum Reset ruht sie, danach je Woche so viele Tage, wie das
    Kontingent reicht. Rückgabe: Pausen-Tage (0.0, wenn nichts zu rechnen ist)."""
    if not lage or not lage.get("tempo") or lage.get("reset_utc") is None or tage <= 0:
        return 0.0
    bis_reset = (lage["reset_utc"] - jetzt).total_seconds() / 86400
    bis_leer = min(bis_reset, (lage["leer_utc"] - jetzt).total_seconds() / 86400)
    if tage <= bis_leer:
        return 0.0
    rest, pause = tage - bis_leer, bis_reset - bis_leer                 # Arbeit, die nach „leer“ noch zu tun ist
    je_woche, pause_je_woche = lage["arbeitstage_je_woche"], lage["pause_je_woche"]
    while rest > je_woche and pause_je_woche > 0:
        rest -= je_woche
        pause += pause_je_woche
        if pause > 3650:
            break
    return round(pause, 1)


def pause_bis(lage, datum, jetzt=None):
    """Ganze Tage Token-Pause bis zu einem Prognose-Datum (JJJJ-MM-TT)."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    try:
        tage = (datetime.date.fromisoformat(datum) - jetzt.date()).days
    except (TypeError, ValueError):
        return 0
    return int(verschieben(lage, tage, jetzt) + 0.5)


def mit_pause(lage, prognose, jetzt=None):
    """Ergänzt jedes Prognose-Datum (dict mit „p50“) um „pause_tage“ und „p50_mit“ – das Datum selbst bleibt, wie es war."""
    if not lage:
        return
    for p in prognose:
        n = pause_bis(lage, p.get("p50"), jetzt)
        if n:
            p["pause_tage"] = n
            p["p50_mit"] = (datetime.date.fromisoformat(p["p50"]) + datetime.timedelta(days=n)).isoformat()


def als_daten(lage):
    """Für die Oberfläche: Zeiten als Text, sonst unverändert (None bleibt None)."""
    if not lage:
        return None
    iso = lambda x: x.strftime("%Y-%m-%dT%H:%M:%SZ") if x else None
    return {**lage, **{k: iso(lage[k]) for k in ("gemessen_utc", "reset_utc", "letzter_reset_utc", "leer_utc")}}


_gemerkt = {}                                      # je Datenbank: (Zeitpunkt, Lage) – die Startseite fragt alle paar Sekunden


def lage_gemerkt(con, sekunden=60):
    import time
    pfad = con.execute("PRAGMA database_list").fetchone()[2]
    alt = _gemerkt.get(pfad)
    if alt and time.time() - alt[0] < sekunden:
        return alt[1]
    _gemerkt[pfad] = (time.time(), lage(con))
    return _gemerkt[pfad][1]


def punkte(con, seit):
    """Messpunkte aller Projekte (ein Konto) seit `seit` (ISO-Text)."""
    return [(r[0], r[1]) for r in con.execute(
        "SELECT zeit_utc, limit_7t FROM verbrauch WHERE limit_7t IS NOT NULL AND zeit_utc >= ? ORDER BY zeit_utc", (seit,))]


def reset_angekuendigt(con):
    """Der Reset, den die zuletzt gemeldete Sitzung nennt (oder None)."""
    r = con.execute("SELECT limit_7t_reset_utc FROM sitzung WHERE limit_7t_reset_utc IS NOT NULL AND status_utc IS NOT NULL"
                    " ORDER BY status_utc DESC LIMIT 1").fetchone()
    try:
        return _zeit(r[0]) if r and r[0] else None
    except ValueError:
        return None


def lage(con, jetzt=None):
    """Lage des Kontos aus der Datenbank (siehe stand())."""
    jetzt = jetzt or datetime.datetime.now(datetime.timezone.utc)
    seit = (jetzt - datetime.timedelta(days=TAGE + 1)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return stand(verlauf(punkte(con, seit)), jetzt, reset_angekuendigt(con))
