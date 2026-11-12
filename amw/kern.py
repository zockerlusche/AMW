"""Fachlogik der AMW: Nachrichten, Aufgaben, Fragen, Halt, Pflicht-Kontext.

Jede Funktion bekommt eine offene Verbindung und schreibt über db.schreiben/db.einfuegen.
Regeln, die hier geprüft werden, beschreibt doc/architektur.md.
Die Prüfungen schützen vor Versehen, nicht vor Absicht: Agenten laufen unter dem Benutzer des Entwicklers.
"""
import json
import os
import re

from . import db

ENTWICKLER = "Entwickler"       # Absender für Eingaben über die Workbench
WURZEL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# so ruft ein Agent AMW auf – in jeder Shell (Git Bash kennt amw.cmd nicht)
BEFEHL = f"python {WURZEL.replace(os.sep, '/')}/amw-cli.py"
OFFEN_STATUS = ("wartet", "laeuft", "blockiert")


class AmwFehler(Exception):
    """Fehler, den der Aufrufer dem Nutzer zeigen soll (kein Programmfehler)."""


# --- Agenten und Projekt -------------------------------------------------------------------------

def agent_zeile(con, pid, kennung):
    r = con.execute("SELECT * FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, kennung or "")).fetchone()
    if not r and kennung and kennung != kennung_heute(con, kennung, pid):     # frühere Kennung (Alias)
        r = con.execute("SELECT * FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, kennung_heute(con, kennung, pid))).fetchone()
    if not r:
        raise AmwFehler(f"Agent „{kennung}“ gibt es im Projekt nicht")
    return r


def _aliase(r):
    return [x.strip() for x in (r["alias"] or "").split(",") if x.strip()]


def kennung_heute(con, name, pid=None):
    """Frühere Kennung eines umbenannten Agenten → heutige (Groß/klein genau); sonst unverändert. Ohne pid über alle
    Projekte, wenn eindeutig."""
    if not name:
        return name
    bedingung, par = (" AND projekt_id = ?", (pid,)) if pid else ("", ())
    if con.execute("SELECT 1 FROM agent WHERE kennung = ?" + bedingung, (name, *par)).fetchone():
        return name
    treffer = {r["kennung"] for r in con.execute("SELECT kennung, alias FROM agent WHERE alias IS NOT NULL" + bedingung, par)
               if name in _aliase(r)}
    return treffer.pop() if len(treffer) == 1 else name


KENNUNG_NAME = re.compile(r"[A-Za-z][A-Za-z0-9_-]{1,23}")
KENNUNG_SPALTEN = {"von", "agent", "pruefer", "bauer", "gilt_fuer", "zustaendig", "verantwortlich"}
KEINE_KENNUNG = {"abhaengig_von", "folge_von"}             # Nummern, keine Kennungen


def _kennung_spalten(con):
    """(Tabelle, Spalte, Bezug) für jede Spalte, in der eine Agenten-Kennung steht – aus dem Schema gelesen, damit neue
    Tabellen beim Umbenennen nicht vergessen werden. Bezug: wie die Zeile zum Projekt gehört."""
    for (t,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
                            " AND name != 'agent' ORDER BY name").fetchall():
        spalten = {c["name"]: c for c in con.execute(f"PRAGMA table_info({t})")}
        if "projekt_id" in spalten:
            bezug = "projekt_id = ?"
        elif "nachricht_id" in spalten:
            bezug = "nachricht_id IN (SELECT id FROM nachricht WHERE projekt_id = ?)"
        elif "frage_id" in spalten:
            bezug = "frage_id IN (SELECT id FROM frage WHERE projekt_id = ?)"
        elif "aufgabe_id" in spalten:
            bezug = "aufgabe_id IN (SELECT id FROM aufgabe WHERE projekt_id = ?)"
        elif "agent_id" in spalten:
            bezug = "agent_id IN (SELECT id FROM agent WHERE projekt_id = ?)"
        else:
            continue                                     # PC-weit (z. B. schirm): bleibt, wie es war
        for name, c in spalten.items():
            if name in KEINE_KENNUNG or "TEXT" not in (c["type"] or "").upper():
                continue
            if name in KENNUNG_SPALTEN or name.endswith("_von"):
                yield t, name, bezug


def agent_umbenennen(con, pid, von, alt, neu):
    """Neue Kennung für einen Agenten. Alle Spalten mit seiner Kennung bekommen die neue (Nachrichten von/an, Aufgaben,
    Fragen, Läufe, Prüfungen, Sperren …); Freitexte bleiben. Die alte Kennung bleibt als Alias gültig – laufende
    Sitzungen mit AMW_AGENT=<alt> und Gewohnheiten wie `--an <alt>` gehen weiter. Gibt {Tabelle.Spalte: Zeilen} zurück."""
    if not ist_lead(con, pid, von):
        raise AmwFehler("Agenten umbenennen nur Entwickler und Lead")
    if not KENNUNG_NAME.fullmatch(neu or ""):
        raise AmwFehler(f"„{neu}“ taugt nicht als Name: Buchstabe, dann Buchstaben/Ziffern/-/_ (2–24 Zeichen)")
    if neu.lower() in ("alle", ENTWICKLER.lower(), "amw"):
        raise AmwFehler(f"„{neu}“ ist reserviert")
    with db.schreiben(con):
        a = agent_zeile(con, pid, alt)
        alt = a["kennung"]
        if neu == alt:
            raise AmwFehler(f"{alt} heißt schon so")
        for r in con.execute("SELECT kennung, alias FROM agent WHERE projekt_id = ? AND id != ?", (pid, a["id"])):
            if neu == r["kennung"] or neu in _aliase(r):
                raise AmwFehler(f"„{neu}“ ist schon vergeben ({r['kennung']})")
        anzahl = {}
        for t, sp, bezug in _kennung_spalten(con):
            n = con.execute(f"UPDATE {t} SET {sp} = ? WHERE {sp} = ? AND {bezug}", (neu, alt, pid)).rowcount
            if n:
                anzahl[f"{t}.{sp}"] = n
        n = con.execute("UPDATE wartegrund SET bezug = ? WHERE projekt_id = ? AND art = 'agent' AND bezug = ?",
                        (neu, pid, alt)).rowcount
        if n:
            anzahl["wartegrund.bezug"] = n
        aliase = [x for x in _aliase(a) if x != neu] + [alt]
        con.execute("UPDATE agent SET kennung = ?, alias = ? WHERE id = ?", (neu, ",".join(dict.fromkeys(aliase)), a["id"]))
        e = json.loads(con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()[0] or "{}")
        if e.get("merge_dienst") == alt:                 # Abnahme-Kette: der Merge-Dienst heißt jetzt anders
            e["merge_dienst"] = neu
            con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps(e), pid))
            anzahl["projekt.merge_dienst"] = 1
    return anzahl


def lead(con, pid):
    """Kennung des Lead-Agenten (oder None)."""
    r = con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND rolle = 'lead' ORDER BY id LIMIT 1", (pid,)).fetchone()
    return r["kennung"] if r else None


def ist_lead(con, pid, kennung):
    if kennung == ENTWICKLER:
        return True
    r = con.execute("SELECT rolle FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, kennung)).fetchone()
    return bool(r) and r["rolle"] == "lead"


ARBEITSWEISEN = ("terminal", "desktop", "chat")   # Claude Code im Terminal · Claude Code in der Desktop-App · Chat über die Brücke


def lead_und_fach(rolle, fachgebiet=None):
    """„rolle“ ist seit Schema 22 nur noch der Schalter „führt das Projekt“ (lead oder leer). Wer noch eine Rolle als
    Freitext angibt (frühere Schreibweise), meint das Fachgebiet. Rückgabe: (rolle, fachgebiet)."""
    rolle, fachgebiet = (rolle or "").strip() or None, (fachgebiet or "").strip() or None
    if rolle and rolle.lower() == "lead":
        return "lead", fachgebiet
    return None, fachgebiet or rolle


def agent_neu(con, pid, kennung, rolle=None, grenzen=None, startbefehl=None, empfaengt_rund=True, fachgebiet=None,
              arbeitsweise="terminal"):
    if kennung_heute(con, kennung, pid) != kennung:
        raise AmwFehler(f"„{kennung}“ ist der frühere Name von {kennung_heute(con, kennung, pid)}")
    if arbeitsweise not in ARBEITSWEISEN:
        raise AmwFehler(f"arbeitsweise: {' | '.join(ARBEITSWEISEN)}")
    rolle, fachgebiet = lead_und_fach(rolle, fachgebiet)
    with db.schreiben(con):
        return db.einfuegen(con, "agent", projekt_id=pid, kennung=kennung, rolle=rolle, fachgebiet=fachgebiet,
                            zustaendig=(grenzen or "").strip() or None, arbeitsweise=arbeitsweise,
                            startbefehl=startbefehl, empfaengt_rund=int(empfaengt_rund), angelegt_utc=db.jetzt(),
                            fernsteuerung=0)            # Remote Control nur auf Wunsch (Profil)


def entwickler_name(con, pid=None):
    """Wie der Mensch in Meldungen heißt: Projekt-Einstellung entwickler_name, sonst „Entwickler“. Ohne pid das erste
    Projekt (für PC-weite Meldungen wie den Schirm)."""
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone() if pid else \
        con.execute("SELECT einstellungen FROM projekt ORDER BY id LIMIT 1").fetchone()
    try:
        return (json.loads(r[0] or "{}").get("entwickler_name") or ENTWICKLER) if r else ENTWICKLER
    except ValueError:
        return ENTWICKLER


PROJEKT_TEXTE = {"entwickler_name": 30}       # Text-Einstellungen: Schlüssel → höchste Länge (leer = Vorgabe)
# Auswahl-Einstellungen: Schlüssel → erlaubte Werte, der erste ist die Vorgabe.
# dateien_online: welche Dateien von Dokumenten von selbst „auch online“ stehen (wunsch = nur auf Wunsch, wie bis 1.10.0)
PROJEKT_WAHL = {"dateien_online": ("wunsch", "bilder", "alle"),
                # Wege (Fehlerbericht aus einem Projekt, Entscheid des Entwicklers): Fragen der Agenten an den Entwickler gehen zuerst an den
                # Lead (er beantwortet selbst oder leitet weiter), Spezifikationen legt nur der Lead vor; freigeben darf
                # der Lead nur, wo es eingeschaltet ist (spec_frei = lead).
                "agentenfragen": ("lead", "direkt"),
                "spec_vorlegen": ("lead", "alle"),
                "spec_frei": ("entwickler", "lead"),
                # Abnahme-Kette (doc/plan-federfuehrung.md B): nach grüner Prüfung + Merge-OK des Leads geht die
                # Merge-Bitte von selbst an den Merge-Dienst (Projekt-Einstellung merge_dienst). Vorgabe aus, der Lead schaltet ein.
                "abnahme_kette": ("aus", "an"),
                # farbe: Streifen über dem Kopf und Marke in der Projekt-Auswahl (Farbtöne setzt die Oberfläche)
                "farbe": ("bernstein", "gruen", "blau", "violett", "tuerkis", "rot", "grau")}


def projekt_wahl(con, pid, schluessel):
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    v = json.loads(r[0] or "{}").get(schluessel) if r else None
    return v if v in PROJEKT_WAHL[schluessel] else PROJEKT_WAHL[schluessel][0]


def projekt_ordner(con, pid):
    """Projektordner: das Repository, in dem die Agenten des Projekts arbeiten (None: nicht eingetragen)."""
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    return json.loads(r[0] or "{}").get("ordner") if r else None


def projekt_ordner_setzen(con, pid, ordner):
    """Nur am PC (Assistent, Workbench „Neues Projekt“, amw projekt ordner). Den Ordner legt der Mensch selbst an; ein
    Ordner gehört zu genau einem Projekt."""
    ordner = os.path.abspath(ordner)
    if not os.path.isdir(ordner):
        raise AmwFehler(f"Ordner {ordner} gibt es nicht – lege ihn zuerst an")
    for r in con.execute("SELECT id, name FROM projekt WHERE id != ?", (pid,)).fetchall():
        if os.path.normcase(projekt_ordner(con, r["id"]) or "") == os.path.normcase(ordner):
            raise AmwFehler(f"Ordner {ordner} gehört schon zum Projekt {r['name']} – ein Ordner gehört zu genau einem Projekt")
    with db.schreiben(con):
        e = json.loads(con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()[0] or "{}")
        e["ordner"] = ordner
        con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps(e, ensure_ascii=False), pid))
    return ordner


def projekt_einstellen(con, pid, von, **werte):
    """Zahnrad „Projekt“: takt_min (0 = aus, bis 1440), speicher_grenze_gb (1–512), stillstand_min und
    lauf_ohne_angabe_min (Warnungen, 5–1440), entwickler_name (wie der Mensch in Meldungen heißt). Nur Lead und Entwickler."""
    if not ist_lead(con, pid, von):
        raise AmwFehler("Projekt-Einstellungen dürfen nur Lead und Entwickler ändern")
    grenzen = {"takt_min": (0, 1440), "speicher_grenze_gb": (1, 512), "stillstand_min": (5, 1440), "lauf_ohne_angabe_min": (5, 1440),
               "eskalation_min": (0, 1440), "info_ablage_h": (1, 168)}
    with db.schreiben(con):
        e = json.loads(con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()[0] or "{}")
        for k, v in werte.items():
            if k in PROJEKT_WAHL:
                if v not in PROJEKT_WAHL[k]:
                    raise AmwFehler(f"{k}: {' | '.join(PROJEKT_WAHL[k])}")
                e[k] = v
                if k == "dateien_online" and v != "wunsch":       # vorhandene Dateien gleich mit (zurück: je Dokument)
                    from . import dokumente
                    dokumente.online_nach_einstellung(con, pid, v)
                continue
            if k == "schwere_befehle":                   # eigene Muster für schwere Läufe (amw/schwer.py), zusätzlich zu den mitgelieferten
                from . import schwer
                try:
                    v = schwer.eigene_pruefen(v or [])
                except ValueError as f:
                    raise AmwFehler(f"schwere_befehle: {f}") from None
                if v:
                    e[k] = v
                else:
                    e.pop(k, None)
                continue
            if k == "merge_dienst":                      # wer mergt (Abnahme-Kette): ein Agent dieses Projekts oder leer
                v = str(v or "").strip()
                if v:
                    e[k] = agent_zeile(con, pid, v)["kennung"]
                else:
                    e.pop(k, None)
                continue
            if k in PROJEKT_TEXTE:
                v = " ".join(str(v or "").split())
                if len(v) > PROJEKT_TEXTE[k] or v.lower() in ("alle", "amw"):
                    raise AmwFehler(f"{k}: bis {PROJEKT_TEXTE[k]} Zeichen")
                if v:
                    e[k] = v
                else:
                    e.pop(k, None)
                continue
            if k not in grenzen:
                raise AmwFehler(f"unbekannte Projekt-Einstellung: {k}")
            try:
                v = float(v)
            except (TypeError, ValueError):
                raise AmwFehler(f"{k}: Zahl erwartet") from None
            lo, hi = grenzen[k]
            if not lo <= v <= hi:
                raise AmwFehler(f"{k}: zwischen {lo} und {hi}")
            e[k] = int(v) if v == int(v) else v
        con.execute("UPDATE projekt SET einstellungen = ? WHERE id = ?", (json.dumps(e), pid))
    return e


# Was am Agenten hängt (Verlauf) – solange etwas da ist, wird nur entfernt (ausgeblendet), nie die Zeile gelöscht
VERLAUF_SQL = {
    "nachrichten": "SELECT count(*) FROM nachricht WHERE projekt_id = :p AND von = :k",
    "empfangen": "SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id WHERE n.projekt_id = :p AND e.agent = :k",
    "aufgaben": "SELECT count(*) FROM aufgabe WHERE projekt_id = :p AND (agent = :k OR angelegt_von = :k)",
    "pruefungen": "SELECT count(*) FROM pruefung WHERE projekt_id = :p AND (bauer = :k OR pruefer = :k)",
    "laeufe": "SELECT count(*) FROM lauf WHERE projekt_id = :p AND agent = :k",
    "dokumente": "SELECT count(*) FROM dokument WHERE projekt_id = :p AND angelegt_von = :k",
    "fragen": "SELECT count(*) FROM frage WHERE projekt_id = :p AND von = :k",
    "sitzungen": "SELECT count(*) FROM sitzung s JOIN agent g ON g.id = s.agent_id WHERE g.projekt_id = :p AND g.kennung = :k",
}


def agent_verlauf(con, pid, kennung):
    """{art: Anzahl} – nur Arten mit Einträgen."""
    aus = {}
    for art, sql in VERLAUF_SQL.items():
        n = con.execute(sql, {"p": pid, "k": kennung}).fetchone()[0]
        if n:
            aus[art] = n
    return aus


def agent_entfernen(con, pid, von, kennung):
    """Nur der Mensch. Stilllegen (Soll aus) und aus allen Listen ausblenden; der Verlauf bleibt mit Namen lesbar. Läuft
    eine Sitzung, wird sie vorher gesichert und beendet (wie „Speichern & beenden“)."""
    if von != ENTWICKLER:
        raise AmwFehler("Agenten entfernt nur der Mensch")
    a = agent_zeile(con, pid, kennung)
    if a["entfernt_utc"]:
        raise AmwFehler(f"{a['kennung']} ist schon entfernt")
    from . import steuerung
    laeuft = con.execute("SELECT 1 FROM sitzung WHERE agent_id = ? AND zustand = 'aktiv'", (a["id"],)).fetchone() is not None
    ende = None
    if laeuft:                                       # zuerst sichern & beenden lassen – der Auftrag muss ihn noch erreichen
        try:
            ende = steuerung.ende_anfordern(con, pid, [a["kennung"]])
        except AmwFehler:                            # Sitzung ohne Prozess (z. B. Chat) oder Sichern läuft schon: nichts zu tun
            ende = None
    with db.schreiben(con):
        con.execute("UPDATE agent SET soll = 'aus', entfernt_utc = ? WHERE id = ?", (db.jetzt(), a["id"]))
    return {"agent": a["kennung"], "endet": bool(ende and ende.get("agenten")), "bis_utc": (ende or {}).get("bis_utc")}


def agent_wiederaufnehmen(con, pid, von, kennung):
    if von != ENTWICKLER:
        raise AmwFehler("Agenten nimmt nur der Mensch wieder auf")
    a = agent_zeile(con, pid, kennung)
    if not a["entfernt_utc"]:
        raise AmwFehler(f"{a['kennung']} ist nicht entfernt")
    with db.schreiben(con):
        con.execute("UPDATE agent SET entfernt_utc = NULL WHERE id = ?", (a["id"],))
    return {"agent": a["kennung"], "soll": "aus"}


def agent_loeschen(con, pid, von, kennung):
    """Endgültig – nur ein Agent ohne jeden Verlauf (sonst bleibt nur Entfernen)."""
    if von != ENTWICKLER:
        raise AmwFehler("Agenten löscht nur der Mensch")
    a = agent_zeile(con, pid, kennung)
    v = agent_verlauf(con, pid, a["kennung"])
    if v:
        raise AmwFehler(f"{a['kennung']} hat Verlauf ({', '.join(f'{n} {k}' for k, n in v.items())}) – endgültig löschen geht nur"
                        " ohne Verlauf; entfernen blendet ihn aus und lässt den Verlauf lesbar")
    with db.schreiben(con):
        con.execute("DELETE FROM agent WHERE id = ?", (a["id"],))
    return {"agent": a["kennung"], "geloescht": True}


def agent_einstellen(con, pid, von, kennung, neu=False, **werte):
    """Zahnrad „Agenten“ und `amw agent profil`: rolle (lead oder leer), fachgebiet, arbeitsweise (terminal | desktop |
    chat), zustaendig, fasst_nicht_an, soll (an/aus/ruht), empfaengt_rund, puls_grenze_s. Nur Lead und Entwickler. Der
    einzige Lead gibt die Führung nicht selbst ab (das kann nur der Entwickler)."""
    if not ist_lead(con, pid, von):
        raise AmwFehler("Agenten dürfen nur Lead und Entwickler einstellen")
    kennung = (kennung or "").strip()
    if not kennung or len(kennung) > 20 or not all(c.isalnum() or c in "-_" for c in kennung) or kennung.lower() == ENTWICKLER.lower():
        raise AmwFehler("Name: bis 20 Zeichen, Buchstaben/Ziffern/-/_, nicht „Entwickler“")
    felder = {}
    for k, v in werte.items():
        if k == "rolle":                             # Schalter „führt das Projekt“; frühere Freitext-Rolle = Fachgebiet
            v, fach = lead_und_fach(v)
            if fach and "fachgebiet" not in werte:
                if len(fach) > 40:
                    raise AmwFehler("fachgebiet: höchstens 40 Zeichen")
                felder["fachgebiet"] = fach
        elif k == "fachgebiet":
            v = (v or "").strip() or None
            if v and len(v) > 40:
                raise AmwFehler("fachgebiet: höchstens 40 Zeichen")
        elif k == "arbeitsweise":
            if v not in ARBEITSWEISEN:
                raise AmwFehler(f"arbeitsweise: {' | '.join(ARBEITSWEISEN)}")
        elif k in ("zustaendig", "fasst_nicht_an"):
            v = " ".join(str(v or "").split())[:400] or None
        elif k == "soll":
            if v not in ("an", "aus", "ruht"):
                raise AmwFehler("soll: an, aus oder ruht")
        elif k == "grenzen":                         # früherer Name von „Zuständig für“
            k, v = "zustaendig", " ".join(str(v or "").split())[:400] or None
        elif k == "empfaengt_rund":
            v = 1 if v in (True, 1, "1", "true", "ja", "an") else 0
        elif k == "puls_grenze_s":
            try:
                v = int(v)
            except (TypeError, ValueError):
                raise AmwFehler("puls_grenze_s: ganze Zahl") from None
            if not 60 <= v <= 86400:
                raise AmwFehler("puls_grenze_s: zwischen 60 und 86400")
        else:
            raise AmwFehler(f"unbekannte Agenten-Einstellung: {k}")
        felder[k] = v
    da = con.execute("SELECT entfernt_utc FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, kennung)).fetchone()
    if neu and da:
        raise AmwFehler(f"{kennung} gibt es schon" + (" (entfernt – wieder aufnehmen: Einstellungen › Agenten)" if da[0] else ""))
    if da and da[0] and felder.get("soll") in ("an", "ruht"):
        raise AmwFehler(f"{kennung} ist entfernt – erst wieder aufnehmen")
    if not neu and not da:
        raise AmwFehler(f"Agent {kennung} gibt es nicht")
    einziger_lead = lead(con, pid) == kennung and not con.execute(
        "SELECT 1 FROM agent WHERE projekt_id = ? AND rolle = 'lead' AND kennung != ?", (pid, kennung)).fetchone()
    if not neu and von != ENTWICKLER and felder.get("rolle", "lead") != "lead" and einziger_lead:
        raise AmwFehler(f"{kennung} ist der einzige Lead – erst einen anderen Lead anlegen (sonst kann nur noch der Entwickler einstellen)")
    if neu:
        agent_neu(con, pid, kennung)
    if felder:
        with db.schreiben(con):
            con.execute(f"UPDATE agent SET {', '.join(k + ' = ?' for k in felder)} WHERE projekt_id = ? AND kennung = ?",
                        (*felder.values(), pid, kennung))
    return kennung


def taetigkeit(con, pid, kennung, text, aufgabe_id=None):
    """Was der Agent gerade tut (zeigt die Workbench auf seiner Kachel); leerer Text löscht die Angabe."""
    a = agent_zeile(con, pid, kennung)
    with db.schreiben(con):
        s = con.execute("SELECT id FROM sitzung WHERE agent_id = ? AND zustand = 'aktiv' ORDER BY id DESC LIMIT 1",
                        (a["id"],)).fetchone()
        if not s:
            raise AmwFehler(f"{kennung} hat keine aktive Sitzung – erst: amw anmelden --von {kennung}")
        t = db.jetzt()
        con.execute("UPDATE sitzung SET taetigkeit = ?, taetigkeit_utc = ?, aufgabe_id = ?, letzter_puls_utc = ? WHERE id = ?",
                    ((text or "").strip()[:200] or None, t if (text or "").strip() else None, aufgabe_id, t, s["id"]))


TAETIGKEIT_ALT_S = 2 * 3600      # ab da gilt eine Tätigkeit als veraltet (Workbench: Bernstein, automatisch ersetzbar)


ESKALATION_MIN = 30     # so lange darf eine Frage/Prüfbitte/ein Auftrag beim Federführenden ungelesen liegen


def eskalieren(con, pid):
    """Fragen, Prüfbitten und Aufträge zu einer Aufgabe, die bei ihrem Federführenden (nicht dem Lead) länger als
    eskalation_min ungelesen liegen: einmal eine weckende Zeile an den Lead. Gibt die eskalierten Nummern zurück."""
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    minuten = float(json.loads(r[0] or "{}").get("eskalation_min", ESKALATION_MIN)) if r else ESKALATION_MIN
    l = lead(con, pid)
    if not minuten or not l:
        return []
    from datetime import datetime, timedelta, timezone
    grenze = (datetime.now(timezone.utc) - timedelta(minutes=minuten)).strftime("%Y-%m-%dT%H:%M:%SZ")
    aus = []
    for z in con.execute(
            "SELECT n.id, n.kurz, n.aufgabe_id, n.von, e.agent FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
            " WHERE n.projekt_id = ? AND e.status = 'offen' AND n.art IN ('frage', 'pruefbitte', 'auftrag')"
            " AND n.aufgabe_id IS NOT NULL AND n.von != 'AMW' AND n.zeit_utc < ? AND e.agent != ?",
            (pid, grenze, l)).fetchall():
        if zustaendig(con, pid, z["aufgabe_id"]) != z["agent"]:
            continue                                   # nur was beim Federführenden liegt
        kurz = f"Eskalation #{z['id']}:"
        if con.execute("SELECT 1 FROM nachricht WHERE projekt_id = ? AND von = 'AMW' AND kurz LIKE ?",
                       (pid, kurz + "%")).fetchone():
            continue
        with db.schreiben(con):
            _posten(con, pid, "AMW", l, "meldung", f"{kurz} liegt seit über {minuten:g} min ungelesen bei {z['agent']}"
                    f" (führt A{z['aufgabe_id']}) – {z['von']}: {z['kurz'][:120]}", aufgabe_id=z["aufgabe_id"])
        aus.append(z["id"])
    return aus


def taetigkeit_auto(con, pid, kennung, text, aufgabe_id=None):
    """aufgabe start / lauf start: setzt die Tätigkeit nur, wenn keine da ist oder sie älter als 2 h ist – eine eigene,
    genauere Angabe wird nicht überschrieben. Läuft in der Transaktion des Aufrufers."""
    s = con.execute("SELECT s.id, s.taetigkeit, s.taetigkeit_utc FROM sitzung s JOIN agent g ON g.id = s.agent_id"
                    " WHERE g.projekt_id = ? AND g.kennung = ? AND s.zustand = 'aktiv' ORDER BY s.id DESC LIMIT 1",
                    (pid, kennung)).fetchone()
    if not s:
        return False
    if s["taetigkeit"] and s["taetigkeit_utc"] and alter_s(s["taetigkeit_utc"]) < TAETIGKEIT_ALT_S:
        return False
    con.execute("UPDATE sitzung SET taetigkeit = ?, taetigkeit_utc = ?, aufgabe_id = ? WHERE id = ?",
                (text[:200], db.jetzt(), aufgabe_id, s["id"]))
    return True


def alter_s(utc):
    """Sekunden seit einem Zeitstempel der Datenbank (UTC, ISO)."""
    from datetime import datetime, timezone
    return (datetime.now(timezone.utc) - datetime.strptime(utc, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)).total_seconds()


def abmelden(con, pid, kennung):
    """Sitzung ruht: kein Wecken mehr bis zum nächsten anmelden (bzw. Start/Resume), kein automatischer Neustart;
    der Lead erfährt es. Die Sitzung selbst bleibt offen – beenden tut der Mensch."""
    a = agent_zeile(con, pid, kennung)
    with db.schreiben(con):
        n = con.execute("UPDATE sitzung SET zustand = 'ruht', taetigkeit = 'abgemeldet', taetigkeit_utc = ?"
                        " WHERE agent_id = ? AND zustand = 'aktiv'", (db.jetzt(), a["id"])).rowcount
        if not n:
            raise AmwFehler(f"{kennung} ist nicht angemeldet")
        l = lead(con, pid)
        if l and l != kennung:
            _posten(con, pid, kennung, l, "info", f"{kennung} hat sich abgemeldet – wird nicht benachrichtigt bis zum nächsten"
                                                 f" anmelden")
    return n


# --- Halt und Sperren ----------------------------------------------------------------------------

def aktive_sperren(con, pid, kennung=None, art=None):
    sql = ("SELECT * FROM sperre WHERE projekt_id = ? AND aufgehoben_utc IS NULL"
           " AND (bis_utc IS NULL OR bis_utc > ?)")
    par = [pid, db.jetzt()]
    if kennung:
        sql += " AND gilt_fuer IN ('alle', ?)"
        par.append(kennung)
    if art:
        sql += " AND art = ?"
        par.append(art)
    return con.execute(sql + " ORDER BY seit_utc", par).fetchall()


def halt_gilt(con, pid, kennung):
    return bool(aktive_sperren(con, pid, kennung, "halt"))


def halt(con, pid, von, gilt_fuer, text):
    """Setzt einen Halt und schickt jedem Betroffenen ein STOPP (weckt; der Dienst stellt es zu)."""
    if not ist_lead(con, pid, von):
        raise AmwFehler("Halt dürfen nur Entwickler und Lead setzen")
    with db.schreiben(con):
        sid = db.einfuegen(con, "sperre", projekt_id=pid, art="halt", gilt_fuer=gilt_fuer, von=von,
                           text=text, seit_utc=db.jetzt())
        _posten(con, pid, von, gilt_fuer, "stopp", f"HALT: {text}",
                f"Halt #{sid} von {von}. Aktuelle Arbeit sauber beenden, nichts Neues anfangen, "
                f"bis „weiter“ kommt.")
    return sid


def weiter(con, pid, von, gilt_fuer):
    if not ist_lead(con, pid, von):
        raise AmwFehler("Weiter dürfen nur Entwickler und Lead geben")
    with db.schreiben(con):
        n = con.execute("UPDATE sperre SET aufgehoben_utc = ? WHERE projekt_id = ? AND art = 'halt'"
                        " AND gilt_fuer = ? AND aufgehoben_utc IS NULL", (db.jetzt(), pid, gilt_fuer)).rowcount
        if n:
            _posten(con, pid, von, gilt_fuer, "freigabe", "WEITER: Halt aufgehoben", f"{n} Halt aufgehoben von {von}.")
    return n


# --- Nachrichten ---------------------------------------------------------------------------------

def zustaendig(con, pid, aufgabe_id):
    """Wer für eine Aufgabe zuständig ist: ihre Federführung, sonst die ihres Bogens, sonst der Lead (None ohne Lead)."""
    r = con.execute("SELECT a.federfuehrend AS a_ff, b.federfuehrend AS b_ff FROM aufgabe a LEFT JOIN bogen b ON b.id = a.bogen_id"
                    " WHERE a.id = ? AND a.projekt_id = ?", (aufgabe_id, pid)).fetchone()
    if not r:
        raise AmwFehler(f"A{aufgabe_id} gibt es nicht")
    return r["a_ff"] or r["b_ff"] or lead(con, pid)


def fuehrt(con, pid, kennung):
    """Was ein Agent federführend leitet: (Bögen, Aufgaben) – nur offene."""
    boegen = con.execute("SELECT id, titel FROM bogen WHERE projekt_id = ? AND federfuehrend = ? AND status IN ('geplant', 'aktiv')"
                         " ORDER BY id", (pid, kennung)).fetchall()
    aufgaben = con.execute("SELECT id, titel FROM aufgabe WHERE projekt_id = ? AND federfuehrend = ?"
                           " AND status IN ('wartet', 'laeuft', 'blockiert') ORDER BY id", (pid, kennung)).fetchall()
    return boegen, aufgaben


ZUSTAENDIG = ("zustaendig", "zuständig", "federfuehrend", "federführend")


def empfaenger(con, pid, an, von, aufgabe_id=None):
    namen = []
    for teil in an.replace(";", ",").split(","):
        teil = teil.strip()
        if not teil:
            continue
        if teil.lower() in ZUSTAENDIG:               # wer die Aufgabe gerade führt (Federführung › Bogen › Lead)
            if not aufgabe_id:
                raise AmwFehler("--an zustaendig braucht --aufgabe <nr> (wer zuständig ist, hängt an der Aufgabe)")
            z = zustaendig(con, pid, aufgabe_id)
            if not z:
                raise AmwFehler(f"A{aufgabe_id}: keine Federführung und kein Lead")
            namen.append(z)
        elif teil.lower() == "alle":                    # Soll an/ruht oder Sitzung läuft (auch bei Soll aus)
            namen += [r["kennung"] for r in con.execute(
                "SELECT kennung FROM agent g WHERE projekt_id = ? AND empfaengt_rund = 1 AND entfernt_utc IS NULL AND (soll != 'aus' OR EXISTS"
                " (SELECT 1 FROM sitzung s WHERE s.agent_id = g.id AND s.zustand = 'aktiv')) ORDER BY id", (pid,))]
        elif teil.lower() == ENTWICKLER.lower():         # der Mensch: liest in der Workbench, wird nie geweckt
            namen.append(ENTWICKLER)
        elif db.produkt_entwickler() and teil.lower() == db.produkt_entwickler().lower():   # Entwickler-Kanal
            namen.append(db.produkt_entwickler())
        else:
            z = agent_zeile(con, pid, teil)                          # frühere Kennung → heutige
            if z["entfernt_utc"]:
                raise AmwFehler(f"{z['kennung']} ist entfernt – Nachrichten an ihn gehen nicht mehr (wieder aufnehmen: Einstellungen › Agenten)")
            namen.append(z["kennung"])
    aus = [n for i, n in enumerate(namen) if n != von and n not in namen[:i]]
    if not aus:
        raise AmwFehler("kein Empfänger")
    return aus


def ausgelassen(con, pid):
    """Wen „alle“ nicht erreicht: Soll aus und keine laufende Sitzung, oder keine Rundschreiben."""
    return [f"{r['kennung']} ({'keine Rundschreiben' if not r['empfaengt_rund'] else 'Soll aus, keine Sitzung'})"
            for r in con.execute("SELECT kennung, empfaengt_rund FROM agent g WHERE projekt_id = ? AND entfernt_utc IS NULL AND (empfaengt_rund = 0 OR"
                                 " (soll = 'aus' AND NOT EXISTS (SELECT 1 FROM sitzung s WHERE s.agent_id = g.id"
                                 " AND s.zustand = 'aktiv'))) ORDER BY id", (pid,))]


# Weckt eine Nachricht? Art mit weckt = 1, oder eine info an genau einen Empfänger von einem Agenten/dem Entwickler
# (Einzel-Infos wie „Merge erledigt“ blieben sonst bis zu 75 min liegen; Sammel-Infos und Kopien der AMW wecken nicht).
# n = nachricht, k = nachricht_art.
WECKT_SQL = ("(k.weckt = 1 OR (n.art = 'info' AND n.von != 'AMW'"
             " AND (SELECT count(*) FROM empfang z WHERE z.nachricht_id = n.id) = 1))")


BIS = re.compile(r"leitbild|aufgabe|[AF]\d+")


def bis_pruefen(con, pid, bis):
    """--bis: leitbild | aufgabe | A<nr> | F<nr> (die Aufgabe/Frage muss es im Projekt geben). Gibt den Wert zurück."""
    bis = (bis or "").strip()
    if not bis:
        return None
    bis = bis[0].upper() + bis[1:] if bis[0] in "afAF" and bis[1:].isdigit() else bis.lower()   # A12/a12 → A12
    if not BIS.fullmatch(bis):
        raise AmwFehler("--bis: leitbild | aufgabe | A<nr> | F<nr> – die Meldung erledigt sich, sobald das erfüllt ist")
    if bis[0] in "AF":
        tabelle = "aufgabe" if bis[0] == "A" else "frage"
        if not con.execute(f"SELECT 1 FROM {tabelle} WHERE id = ? AND projekt_id = ?", (int(bis[1:]), pid)).fetchone():
            raise AmwFehler(f"--bis {bis}: gibt es in diesem Projekt nicht")
    return bis


def bis_erfuellt(con, pid, bis, von):
    """Ist der Bezug einer Meldung erfüllt? Grund als Text, sonst None."""
    if bis == "leitbild":
        r = con.execute("SELECT leitbild FROM projekt WHERE id = ?", (pid,)).fetchone()
        try:
            ziel = (json.loads(r[0] or "{}").get("ziel") or "").strip() if r else ""
        except ValueError:
            ziel = ""
        return "Leitbild steht" if ziel else None
    if bis == "aufgabe":
        r = con.execute("SELECT id FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status IN ('wartet', 'laeuft', 'blockiert')"
                        " ORDER BY id LIMIT 1", (pid, von)).fetchone()
        return f"{von} hat A{r[0]}" if r else None
    if bis[0] == "A":
        r = con.execute("SELECT status FROM aufgabe WHERE id = ?", (int(bis[1:]),)).fetchone()
        return f"{bis} {r[0]}" if r and r[0] in ("fertig", "verworfen") else None
    if bis[0] == "F":
        r = con.execute("SELECT status FROM frage WHERE id = ?", (int(bis[1:]),)).fetchone()
        return f"{bis} {r[0]}" if r and r[0] != "offen" else None
    return None


def bezuege_erledigen(con):
    """Wächter: Empfänge von Meldungen, deren Bezug („bis“) erfüllt ist, auf erledigt. Gibt [(nid, grund)] zurück."""
    aus = []
    for n in con.execute("SELECT DISTINCT n.id, n.projekt_id, n.von, n.bis FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id"
                         " WHERE n.bis IS NOT NULL AND e.status != 'erledigt'").fetchall():
        grund = bis_erfuellt(con, n["projekt_id"], n["bis"], n["von"])
        if grund:
            with db.schreiben(con):
                con.execute("UPDATE empfang SET status = 'erledigt', erledigt_utc = ?, bemerkung = ? WHERE nachricht_id = ?"
                            " AND status != 'erledigt'", (db.jetzt(), f"von selbst erledigt: {grund}", n["id"]))
            aus.append((n["id"], grund))
    return aus


def _posten(con, pid, von, an, art, kurz, text=None, antwort_auf=None, aufgabe_id=None, bis=None, bezug=None):
    if not con.execute("SELECT 1 FROM nachricht_art WHERE art = ?", (art,)).fetchone():
        erlaubt = ", ".join(r[0] for r in con.execute("SELECT art FROM nachricht_art ORDER BY art"))
        raise AmwFehler(f"Art „{art}“ gibt es nicht; erlaubt: {erlaubt}")
    if von not in ("AMW", ENTWICKLER, db.produkt_entwickler()) and not con.execute(
            "SELECT 1 FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, von)).fetchone():
        raise AmwFehler(f"Absender „{von}“ ist kein Agent dieses Projekts – --von ist dein eigener Name"
                        " (Empfänger stehen in --an)")
    namen = empfaenger(con, pid, an, von, aufgabe_id)
    if not bezug:                                      # Bezug: Aufgabe, „bis“ F<nr>, sonst geerbt von der Nachricht davor
        if aufgabe_id:
            bezug = f"A{aufgabe_id}"
        elif bis and re.fullmatch(r"[AF]\d+", bis):
            bezug = bis
        elif antwort_auf:
            r = con.execute("SELECT bezug FROM nachricht WHERE id = ?", (antwort_auf,)).fetchone()
            bezug = r[0] if r else None
    dok = int(bezug[1:]) if bezug and bezug[0] == "D" else None
    nid = db.einfuegen(con, "nachricht", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art=art, kurz=kurz,
                       text=text, antwort_auf=antwort_auf, aufgabe_id=aufgabe_id, bis=bis, bezug=bezug, dokument_id=dok)
    for n in namen:
        db.einfuegen(con, "empfang", nachricht_id=nid, agent=n)
    if antwort_auf:                                    # Antwort auf eine Rückfrage → Nachtrag im Verlauf der Frage
        r = con.execute("SELECT frage_id FROM frage_verlauf WHERE nachricht_id = ? AND art = 'rueckfrage'",
                        (antwort_auf,)).fetchone()
        if r:
            db.einfuegen(con, "frage_verlauf", frage_id=r["frage_id"], zeit_utc=db.jetzt(), von=von, art="nachtrag",
                         text=(kurz + ("\n" + text if text else "")).strip(), nachricht_id=nid)
    if aufgabe_id and von != "AMW":                    # wer zur Aufgabe schreibt, erledigt „wartet auf <ihn>“ (L1)
        from . import wartegrund
        if von == ENTWICKLER:
            wartegrund.erledige(con, pid, "entwickler", ENTWICKLER, f"{entwickler_name(con, pid)} hat geschrieben (#{nid})",
                                aufgabe_id)
        else:
            wartegrund.erledige(con, pid, "agent", von, f"{von} hat geschrieben (#{nid})", aufgabe_id)
    return nid, namen


KOPIE_ARTEN = ("info", "meldung", "antwort")      # L5: Kopie an den Besitzer – nicht bei auftrag/pruefbitte (Merge, Prüfung)


def aufgabe_bezug(con, pid, von, aid, antwort_auf=None):
    """L4: --aufgabe muss es geben und darf nicht abgeschlossen sein. Gibt die Aufgabe und ggf. einen Hinweis zurück
    (fremde Aufgabe – kein Fehler, Merge- und Prüfbitten tragen fremde Nummern). Kein Hinweis, wenn der Absender Prüfer
    der Aufgabe ist, schon einmal zu ihr geschrieben hat oder auf eine Nachricht zu ihr antwortet."""
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a:
        raise AmwFehler(f"A{aid} gibt es nicht – Nummer prüfen (amw aufgabe liste --agent {von})")
    if a["status"] in ("fertig", "verworfen"):
        raise AmwFehler(f"A{aid} ist {a['status']} – Folgearbeit dazu: amw aufgabe nachtrag {aid} --titel …"
                        " (neue Aufgabe mit Bezug), sonst ohne --aufgabe")
    hinweis = None
    if (a["agent"] and a["agent"] != von and not ist_lead(con, pid, von) and a["pruefer"] != von
            and not con.execute("SELECT 1 FROM nachricht WHERE projekt_id = ? AND von = ? AND aufgabe_id = ? LIMIT 1",
                                (pid, von, aid)).fetchone()
            and not (antwort_auf and con.execute("SELECT 1 FROM nachricht WHERE id = ? AND aufgabe_id = ?",
                                                 (antwort_auf, aid)).fetchone())):
        hinweis = f"Hinweis: A{aid} gehört {a['agent']} ({a['titel'][:60]}) – richtig?"
    return a, hinweis


BEZUG_ARTEN = {"A": ("aufgabe", "titel"), "F": ("frage", "kurz"), "D": ("dokument", "titel"), "M": ("bogen", "titel"),
               "P": ("pruefung", "zweig"), "L": ("lauf", "beschreibung"), "T": ("thema", "name"), "B": ("beschluss", "stichwort")}


def bezug_pruefen(con, pid, bezug):
    """Kürzel für den Bezug einer Nachricht prüfen und vereinheitlichen: A/F/D/M/P/L/T/B<nr> oder @Kennung."""
    if bezug is None or not str(bezug).strip():
        return None
    b = str(bezug).strip()
    if b.startswith("@"):
        if not con.execute("SELECT 1 FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, b[1:])).fetchone():
            raise AmwFehler(f"Bezug {b}: den Agenten gibt es in diesem Projekt nicht")
        return b
    m = re.fullmatch(r"([A-Za-z])(\d+)", b)
    if not m or m.group(1).upper() not in BEZUG_ARTEN:
        raise AmwFehler(f"Bezug „{b}“ verstehe ich nicht – erlaubt: A12 (Aufgabe), F3 (Frage), D8 (Dokument), M2 (Meilenstein),"
                        " P5 (Prüfung), L7 (Lauf), T1 (Thema), B4 (Beschluss) oder @Kennung (Agent)")
    k, nr = m.group(1).upper(), int(m.group(2))
    if not con.execute(f"SELECT 1 FROM {BEZUG_ARTEN[k][0]} WHERE id = ? AND projekt_id = ?", (nr, pid)).fetchone():
        raise AmwFehler(f"Bezug {k}{nr} gibt es in diesem Projekt nicht")
    return f"{k}{nr}"


def bezug_text(con, bezug):
    """Kürzel + Titel für die Anzeige („A1600 Team-Baum …“); None, wenn kein Bezug."""
    if not bezug:
        return None
    if bezug.startswith("@"):
        return bezug[1:]
    tab, spalte = BEZUG_ARTEN.get(bezug[0], (None, None))
    r = con.execute(f"SELECT {spalte} FROM {tab} WHERE id = ?", (int(bezug[1:]),)).fetchone() if tab else None
    return f"{bezug} {str(r[0])[:60]}" if r and r[0] else bezug


def posten(con, pid, von, an, art, kurz, text=None, antwort_auf=None, aufgabe_id=None, hinweise=None, bis=None, bezug=None):
    """Nachricht von einem Agenten oder dem Entwickler. hinweise: Liste, in die Hinweise für die Ausgabe kommen.
    bis: Bezug, mit dem sich die Meldung von selbst erledigt (leitbild | aufgabe | A<nr> | F<nr>).
    bezug: worum es geht (A/F/D/M/P/L/T/B<nr>, @Kennung); ohne: aus aufgabe_id, „bis“ oder der Nachricht, auf die sie antwortet."""
    bis = bis_pruefen(con, pid, bis)
    bezug = bezug_pruefen(con, pid, bezug)
    if bezug and bezug[0] == "A" and not aufgabe_id:                 # die alten Felder mit füllen (alte Abfragen laufen weiter)
        aufgabe_id = int(bezug[1:])
    with db.schreiben(con):
        a = None
        if aufgabe_id and von != "AMW":
            a, hinweis = aufgabe_bezug(con, pid, von, aufgabe_id, antwort_auf)
            if hinweis and hinweise is not None:
                hinweise.append(hinweis)
        nid, namen = _posten(con, pid, von, an, art, kurz, text, antwort_auf, aufgabe_id, bis=bis, bezug=bezug)
        if hinweise is not None and any(t.strip().lower() == "alle" for t in an.replace(";", ",").split(",")):
            weg = ausgelassen(con, pid)
            if weg:
                hinweise.append("nicht erreicht: " + ", ".join(weg))
        besitzer = a["agent"] if a else None
        if (art in KOPIE_ARTEN and besitzer and besitzer != von and besitzer not in namen
                and con.execute("SELECT 1 FROM agent WHERE projekt_id = ? AND kennung = ?", (pid, besitzer)).fetchone()):
            wartet = a["status"] in ("wartet", "blockiert") and bool(a["begonnen_utc"])
            _posten(con, pid, "AMW", besitzer, "meldung" if wartet else "info",
                    f"Kopie zu deiner A{aufgabe_id}: {von} → {', '.join(namen)}: {kurz[:150]}", text=f"Nachricht #{nid}",
                    aufgabe_id=aufgabe_id)
            if hinweise is not None:
                hinweise.append(f"Kopie an {besitzer} (Besitzer von A{aufgabe_id})")
        return nid, namen


def offene(con, pid, kennung, grenze=50, neueste_zuerst=False):
    return con.execute(
        "SELECT n.id, n.zeit_utc, n.von, n.art, n.kurz, n.aufgabe_id, e.status, a.weckt"
        " FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id JOIN nachricht_art a ON a.art = n.art"
        " WHERE n.projekt_id = ? AND e.agent = ? AND e.status != 'erledigt'"
        f" ORDER BY n.id {'DESC' if neueste_zuerst else ''} LIMIT ?",
        (pid, kennung, grenze)).fetchall()


def anzahl_offen(con, pid, kennung):
    return con.execute("SELECT count(*) FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"
                       " WHERE n.projekt_id = ? AND e.agent = ? AND e.status != 'erledigt'",
                       (pid, kennung)).fetchone()[0]


def als_gelesen(con, kennung, ids):
    """Was `amw lesen` gerade gezeigt hat, gilt für den Leser als gelesen (Stand für den Menschen: „gelesen“)."""
    ids = [int(i) for i in ids]
    if not ids:
        return 0
    with db.schreiben(con):
        return con.execute(f"UPDATE empfang SET status = 'gelesen', gelesen_utc = ? WHERE agent = ? AND status = 'offen'"
                           f" AND nachricht_id IN ({','.join('?' * len(ids))})", (db.jetzt(), kennung, *ids)).rowcount


ZURUECKGEZOGEN = "zurückgezogen"


def zurueckziehen(con, pid, von, nid, benutzer_name=None):
    """Eine Nachricht des Menschen zurückziehen – nur solange kein Empfänger sie gelesen oder erledigt hat. Sie verschwindet
    aus den Listen der Empfänger; beim Menschen bleibt sie als „zurückgezogen“ sichtbar. benutzer_name: online nur die eigene."""
    if von != ENTWICKLER:
        raise AmwFehler("Zurückziehen kann nur der Mensch seine eigenen Nachrichten")
    n = con.execute("SELECT * FROM nachricht WHERE id = ? AND projekt_id = ?", (nid, pid)).fetchone()
    if not n or n["von"] != ENTWICKLER:
        raise AmwFehler(f"#{nid} ist keine Nachricht von dir")
    if benutzer_name is not None and (n["benutzer"] or None) != benutzer_name:
        raise AmwFehler(f"#{nid} hat jemand anderes geschrieben")
    e = con.execute("SELECT agent, status, bemerkung FROM empfang WHERE nachricht_id = ?", (nid,)).fetchall()
    if any(x["bemerkung"] == ZURUECKGEZOGEN for x in e):
        raise AmwFehler(f"#{nid} ist schon zurückgezogen")
    gesehen = [x["agent"] for x in e if x["status"] != "offen"]
    if gesehen:
        raise AmwFehler(f"#{nid} hat {', '.join(gesehen)} schon gelesen – zurückziehen geht nicht mehr; schick eine neue Nachricht")
    with db.schreiben(con):
        con.execute("UPDATE empfang SET status = 'erledigt', erledigt_utc = ?, bemerkung = ? WHERE nachricht_id = ?",
                    (db.jetzt(), ZURUECKGEZOGEN, nid))
    return {"zurueckgezogen": nid, "empfaenger": [x["agent"] for x in e]}


def lesen(con, pid, kennung, nid):
    """Ganze Nachricht; markiert sie für den Leser als gelesen."""
    n = con.execute("SELECT * FROM nachricht WHERE id = ? AND projekt_id = ?", (nid, pid)).fetchone()
    if not n:
        raise AmwFehler(f"Nachricht #{nid} gibt es nicht")
    with db.schreiben(con):
        con.execute("UPDATE empfang SET status = 'gelesen', gelesen_utc = ? WHERE nachricht_id = ? AND agent = ?"
                    " AND status = 'offen'", (db.jetzt(), nid, kennung))
    return n


def projekt_der_nachricht(con, nid):
    r = con.execute("SELECT projekt_id FROM nachricht WHERE id = ?", (nid,)).fetchone()
    if not r:
        raise AmwFehler(f"Nachricht #{nid} gibt es nicht")
    return r[0]


def offene_aller_projekte(con, kennung, grenze=50, neueste_zuerst=False):
    """Entwickler-Kanal: offene Nachrichten an kennung aus allen Projekten (mit Projektname)."""
    return con.execute(
        "SELECT n.id, n.zeit_utc, n.von, n.art, n.kurz, n.aufgabe_id, e.status, a.weckt, p.name AS projekt"
        " FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id JOIN nachricht_art a ON a.art = n.art"
        " JOIN projekt p ON p.id = n.projekt_id WHERE e.agent = ? AND e.status != 'erledigt'"
        f" ORDER BY n.id {'DESC' if neueste_zuerst else ''} LIMIT ?", (kennung, grenze)).fetchall()


def erledigt_fuer(con, pid, von, fuer, nids, grund):
    """Der Lead schließt veraltete Meldungen (info/meldung) an den Entwickler – mit Grund; steht im Verlauf (Planung)."""
    if fuer != ENTWICKLER:
        raise AmwFehler("--fuer: nur „Entwickler“ – jeder Agent erledigt seine Nachrichten selbst")
    if von == ENTWICKLER or not ist_lead(con, pid, von):
        raise AmwFehler("Meldungen an den Entwickler schließt nur der Lead")
    if not (grund or "").strip():
        raise AmwFehler("--bemerkung \"warum erledigt\" ist Pflicht – sie steht im Verlauf")
    n = 0
    with db.schreiben(con):
        for nid in nids:
            r = con.execute("SELECT art FROM nachricht WHERE id = ? AND projekt_id = ?", (nid, pid)).fetchone()
            if not r:
                raise AmwFehler(f"Nachricht #{nid} gibt es in diesem Projekt nicht")
            if r["art"] not in ("info", "meldung"):
                raise AmwFehler(f"#{nid} ist [{r['art']}] – schließen darf der Lead nur info und meldung")
            k = con.execute("UPDATE empfang SET status = 'erledigt', erledigt_utc = ?, bemerkung = ? WHERE nachricht_id = ?"
                            " AND agent = ? AND status != 'erledigt'",
                            (db.jetzt(), f"geschlossen von {von}: {grund.strip()}", nid, ENTWICKLER)).rowcount
            if k:
                db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=db.jetzt(), von=von, art="info_geschlossen",
                             text=f"#{nid} für {entwickler_name(con, pid)} geschlossen: {grund.strip()}")
            n += k
    return n


def erledigt(con, pid, kennung, nids, bemerkung=None):
    """Mehrere Nachrichten auf einmal erledigen . Gibt die Zahl der geänderten Empfänge zurück."""
    with db.schreiben(con):
        n = 0
        for nid in nids:
            n += con.execute(
                "UPDATE empfang SET status = 'erledigt', erledigt_utc = ?, bemerkung = coalesce(?, bemerkung)"
                " WHERE nachricht_id = ? AND agent = ? AND status != 'erledigt'"
                " AND nachricht_id IN (SELECT id FROM nachricht WHERE projekt_id = ?)",
                (db.jetzt(), bemerkung, nid, kennung, pid)).rowcount
            # die Meldung der AMW „A…: X hat geschrieben (#nid) – …“ gehört zu dieser Nachricht – gleich mit erledigen
            con.execute("UPDATE empfang SET status = 'erledigt', erledigt_utc = ? WHERE agent = ? AND status != 'erledigt'"
                        " AND nachricht_id IN (SELECT id FROM nachricht WHERE projekt_id = ? AND von = 'AMW' AND kurz LIKE ?)",
                        (db.jetzt(), kennung, pid, f"%(#{nid})%"))
    return n


def erledigt_infos(con, pid, kennung, vor=None):
    """Alle offenen/gelesenen [info] an kennung erledigen (vor: nur ältere als dieses Datum, JJJJ-MM-TT). Anzahl."""
    sql = ("UPDATE empfang SET status = 'erledigt', erledigt_utc = ?, bemerkung = coalesce(bemerkung, 'info gesammelt')"
           " WHERE agent = ? AND status != 'erledigt' AND nachricht_id IN (SELECT id FROM nachricht WHERE projekt_id = ?"
           " AND art = 'info'" + (" AND zeit_utc < ?" if vor else "") + ")")
    with db.schreiben(con):
        return con.execute(sql, (db.jetzt(), kennung, pid, *([vor] if vor else []))).rowcount


# --- Aufgaben ------------------------------------------------------------------------------------

def bearbeiter(con, pid, x):
    """Kennung eines Bearbeiters: ein Agent (frühere Kennung → heutige) oder der Entwickler („Entwickler“ bzw. sein
    eingestellter Name) – dessen eigene Aufgaben stehen in seiner Liste wie die eines Agenten."""
    if not x:
        return x
    if x.strip().lower() in (ENTWICKLER.lower(), entwickler_name(con, pid).lower()):
        return ENTWICKLER
    return agent_zeile(con, pid, x)["kennung"]


def aufgabe_neu(con, pid, von, titel, agent=None, auftrag=None, rang=50, pruefer=None, abhaengig_von=None, sofort=True):
    """sofort=False: Hat der Agent gerade ein Stück in Arbeit und legt jemand anderes die Aufgabe an, landet sie im
    Eingang (Einstufung pool) – eingeplant wird sie danach, hinter dem laufenden Stück. Aufgaben des Menschen bleiben frei."""
    with db.schreiben(con):
        einstufung = "aktiv"
        if agent:
            agent = bearbeiter(con, pid, agent)
            from . import arbeitsliste                # nie vor das laufende Stück des Agenten
            x = arbeitsliste.laufend(con, pid, agent)
            if x and not sofort and agent != von:
                einstufung = "pool"
            if x and (rang, 10 ** 9) < (x["rang"], x["id"]):
                rang = x["rang"] + 1
        return db.einfuegen(con, "aufgabe", projekt_id=pid, titel=titel, auftrag=auftrag, agent=agent,
                            pruefer=pruefer, angelegt_von=von, rang=rang, abhaengig_von=abhaengig_von,
                            angelegt_utc=db.jetzt(), einstufung=einstufung)


def _aufgabe_fuer_aenderung(con, pid, von, aid):
    a = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not a:
        raise AmwFehler(f"Aufgabe A{aid} gibt es nicht")
    if a["agent"] and a["agent"] != von and not ist_lead(con, pid, von):
        raise AmwFehler(f"A{aid} gehört {a['agent']} – nur der Besitzer oder Lead darf den Status ändern")
    return a


def aufgabe_status(con, pid, von, aid, status, beleg=None, wartet_auf=None, bemerkung=None, zusammenfassung=None,
                   auf=None, erledigt=None, hinweise=None, hinweis=None, gruppe=None):
    """auf: Wartegründe als Verweise (F…, A…, L…, Agent, Entwickler, Monitor:…) – Pflicht bei wartet/blockiert.
    erledigt: Gründe von Hand abhaken; allein (ohne auf) ändert es den Status nicht."""
    from . import wartegrund
    if erledigt and not auf and status in ("wartet", "blockiert"):
        with db.schreiben(con):
            a = _aufgabe_fuer_aenderung(con, pid, von, aid)
            wartegrund.von_hand(con, pid, von, aid, erledigt)
        return a["status"]
    neu = {"start": "laeuft", "blockiert": "blockiert", "wartet": "wartet", "fertig": "fertig",
           "verwerfen": "verworfen"}.get(status, status)
    if neu == "laeuft" and halt_gilt(con, pid, von):
        raise AmwFehler("HALT gilt – keine neuen Aufgaben starten (amw kontext zeigt den Halt)")
    if neu in ("fertig", "verworfen") and not (beleg or "").strip():
        raise AmwFehler("fertig/verworfen nur mit --beleg (Commit, Datei:Zeile oder Folgeaufgabe)")
    with db.schreiben(con):
        a = _aufgabe_fuer_aenderung(con, pid, von, aid)
        from . import planung                       # Regeln der Planung: Vorgänger, Plan-Gate, Kriterien, Zusammenfassung
        planung.pruefe_status(con, a, neu, zusammenfassung)
        if erledigt:
            wartegrund.von_hand(con, pid, von, aid, erledigt)
        if neu in ("wartet", "blockiert"):         # „wartet“ mit Freitext weckt niemanden, wenn es weitergeht
            if auf:
                wartegrund.anlegen(con, pid, von, aid, auf)
            if not wartegrund.offene(con, aid):
                raise AmwFehler(f"{neu} nur mit --auf: worauf? F<nr>, A<nr>, L<nr>, Agent, Entwickler, Monitor:<was>"
                                " (Erklärung dazu mit --wartet-auf)")
        if neu == "laeuft" and a["status"] != "laeuft":
            from . import arbeitsliste                # eins nach dem anderen: läuft schon ein Stück, wird abgewiesen
            arbeitsliste.start_pruefen(con, pid, von, a)
        t = db.jetzt()
        felder = {"status": neu}
        if zusammenfassung:
            felder["zusammenfassung"] = zusammenfassung
        if neu == "laeuft" and not a["begonnen_utc"]:
            felder["begonnen_utc"] = t
        if neu in ("fertig", "verworfen"):
            felder["fertig_utc"] = t
            felder["beleg"] = beleg
        if neu == "fertig" and (hinweis or gruppe):   # für die Versionshinweise (amw release)
            from . import versionshinweise
            try:
                felder["hinweis_gruppe"] = versionshinweise.gruppe_pruefen(gruppe)
            except ValueError as e:
                raise AmwFehler(str(e)) from None
            if (hinweis or "").strip():
                felder["hinweis"] = " ".join(hinweis.split())[:300]
        if wartet_auf is not None or neu in ("laeuft", "fertig", "verworfen"):
            felder["wartet_auf"] = wartet_auf
        if bemerkung:
            felder["bemerkung"] = ((a["bemerkung"] + " || ") if a["bemerkung"] else "") + f"{von} {t}: {bemerkung}"
        satz = ", ".join(f"{k} = ?" for k in felder)
        con.execute(f"UPDATE aufgabe SET {satz} WHERE id = ?", (*felder.values(), aid))
        if neu in ("fertig", "verworfen"):            # wer abgeschlossen hat (kann der Lead statt des Bearbeiters sein)
            db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=t, von=von, art="aufgabe_abschluss",
                         bogen_id=a["bogen_id"], aufgabe_id=aid, text=neu)
        if neu in ("laeuft", "fertig", "verworfen"):
            wartegrund.schliessen(con, aid, f"A{aid} {neu}")
        if neu == "laeuft":                          # „alle Gründe erledigt – weiter“ ist damit abgearbeitet
            con.execute("UPDATE empfang SET status = 'erledigt', erledigt_utc = ? WHERE agent = ? AND status != 'erledigt'"
                        " AND nachricht_id IN (SELECT id FROM nachricht WHERE projekt_id = ? AND von = 'AMW'"
                        " AND aufgabe_id = ? AND art IN ('meldung', 'info'))", (t, von, pid, aid))
            if a["agent"] in (None, "", von):
                taetigkeit_auto(con, pid, von, f"A{aid} · {a['titel']}", aid)
        if neu in ("fertig", "verworfen"):            # wer auf diese Aufgabe gewartet hat, wird geweckt (L2)
            geweckt = wartegrund.erledige(con, pid, "aufgabe", f"A{aid}", f"A{aid} {neu}")
            from . import arbeitsliste                # … und der Besitzer mit der nächsten seiner Liste
            arbeitsliste.beim_abschluss(con, pid, {**dict(a), "status": neu}, geweckt)
    return neu


def federfuehrung_setzen(con, pid, von, art, nr, kennung):
    """Federführung eines Bogens (art=bogen) oder einer Aufgabe (art=aufgabe) setzen; leer nimmt sie weg. Nur Lead/Entwickler.
    Der neue Federführende erfährt es (weckend)."""
    if not ist_lead(con, pid, von):
        raise AmwFehler("Federführung setzen dürfen nur Lead und Entwickler")
    tabelle = {"bogen": "bogen", "aufgabe": "aufgabe"}[art]
    r = con.execute(f"SELECT id, titel FROM {tabelle} WHERE id = ? AND projekt_id = ?", (nr, pid)).fetchone()
    if not r:
        raise AmwFehler(f"{'Meilenstein ' if art == 'bogen' else 'A'}{nr} gibt es nicht")
    kennung = (kennung or "").strip()
    if kennung:
        kennung = agent_zeile(con, pid, kennung)["kennung"]
    with db.schreiben(con):
        con.execute(f"UPDATE {tabelle} SET federfuehrend = ? WHERE id = ?", (kennung or None, nr))
        if kennung and kennung != von:
            was = f"Meilenstein {nr}" if art == "bogen" else f"A{nr}"
            _posten(con, pid, von, kennung, "auftrag", f"Du führst jetzt {was}: {r['titel'][:120]}",
                    "Federführung: Prüfergebnisse, Merge-Bitten und Fragen dazu kommen zu dir (--an zustaendig)."
                    " Du verteilst Schritte, nimmst ab und meldest dem Lead Abschluss und Abweichungen. Beim Lead bleiben:"
                    " Fragen an den Entwickler, Werte, Freigaben, main/Push.", aufgabe_id=nr if art == "aufgabe" else None)
    return kennung or None


def aufgabe_nachtrag(con, pid, von, aid, titel, auftrag=None, agent=None):
    """Folgearbeit zu einer abgeschlossenen Aufgabe: neue Aufgabe mit Bezug (Titel „Nachtrag A…: …“), gleicher Besitzer,
    wenn keiner genannt ist. Darf der Lead und der Besitzer der alten Aufgabe."""
    alt = con.execute("SELECT * FROM aufgabe WHERE id = ? AND projekt_id = ?", (aid, pid)).fetchone()
    if not alt:
        raise AmwFehler(f"A{aid} gibt es nicht")
    if alt["agent"] not in (None, "", von) and not ist_lead(con, pid, von):
        raise AmwFehler(f"Nachtrag zu A{aid}: nur {alt['agent']} oder der Lead")
    if not (titel or "").strip():
        raise AmwFehler("--titel fehlt")
    text = f"Nachtrag zu A{aid} ({alt['titel'][:80]}, {alt['status']})." + (f"\n{auftrag}" if auftrag else "")
    return aufgabe_neu(con, pid, von, f"Nachtrag A{aid}: {titel.strip()}", agent or alt["agent"] or None, text,
                       alt["rang"], alt["pruefer"], sofort=False)


def aufgaben(con, pid, agent=None, alle=False):
    sql = "SELECT * FROM aufgabe WHERE projekt_id = ?"
    par = [pid]
    if agent:
        sql += " AND agent = ?"
        par.append(agent)
    if not alle:
        sql += " AND status IN ('wartet', 'laeuft', 'blockiert')"
    return con.execute(sql + " ORDER BY rang, id", par).fetchall()


# --- Fragen --------------------------------------------------------------------------------------

OPTION_KENN = re.compile(r"[^\s=:)]{1,12}")


def frage_neu(con, pid, von, an, kurz, optionen, empfehlung=None, grund=None, worum=None, fundstellen=None,
              aufgabe_id=None, blockiert=False, folge_von=None, geprueft=None, pruefen=True):
    zu_zustaendig = an in ZUSTAENDIG                 # Frage an die Federführung der Aufgabe – gespeichert wie eine an den Lead
    if zu_zustaendig:
        if not aufgabe_id:
            raise AmwFehler("frage neu --an zustaendig braucht --aufgabe <nr>")
        an = "tl"
    """optionen: Liste von (kenn, text). Empfehlung muss eine der Kennungen sein.
    geprueft: was der Fragesteller in Beschlüssen/Fragen/Regeln geprüft hat – Pflicht bei Fragen an den Entwickler;
    findet die AMW Treffer, muss es mindestens einen nennen. pruefen=False: Fragen, die die AMW selbst stellt."""
    for k, t in optionen:               # sonst steht der ganze Satz in der schmalen Kennungs-Spalte
        if not OPTION_KENN.fullmatch(k or "") or not (t or "").strip():
            raise AmwFehler(f"Option „{(k or '')[:40]}“: Form --option \"A=Text\" – Kürzel (A, B, V0 …), dann = und der Text")
    kenn = [k for k, _ in optionen]
    if empfehlung and empfehlung not in kenn:
        raise AmwFehler(f"Empfehlung „{empfehlung}“ ist keine der Optionen {kenn}")
    if an == "entwickler" and optionen and not (empfehlung and grund):
        raise AmwFehler("Fragen an den Entwickler brauchen Empfehlung und Grund")
    if aufgabe_id:
        aufgabe_bezug(con, pid, von, aufgabe_id)
    if an == "entwickler" and pruefen:
        from . import wissen
        wissen.pruefung_verlangen(con, pid, f"{kurz} {worum or ''}", geprueft)
    ueber_lead = (an == "entwickler" and pruefen and von not in (ENTWICKLER, "AMW", db.produkt_entwickler())
                  and not ist_lead(con, pid, von) and projekt_wahl(con, pid, "agentenfragen") == "lead" and lead(con, pid))
    if ueber_lead:                                  # Vorgabe des Entwicklers: Agentenfragen zuerst an den Lead
        an = "tl"
    with db.schreiben(con):
        fid = db.einfuegen(con, "frage", projekt_id=pid, an=an, von=von, zeit_utc=db.jetzt(), kurz=kurz,
                           worum=worum, optionen=json.dumps([{"kenn": k, "text": t} for k, t in optionen],
                                                            ensure_ascii=False),
                           empfehlung=empfehlung, grund=grund, fundstellen=fundstellen, aufgabe_id=aufgabe_id,
                           blockiert=int(blockiert), folge_von=folge_von, geprueft=(geprueft or "").strip() or None)
        if an == "tl":
            ziel = (zustaendig(con, pid, aufgabe_id) if zu_zustaendig else None) or lead(con, pid)
            if ziel:
                _posten(con, pid, von, ziel, "frage", (f"Frage F{fid} für den Entwickler – selbst beantworten oder weiterleiten"
                                                     f" (amw frage weiterleiten {fid}): {kurz}") if ueber_lead
                        else f"Frage F{fid}: {kurz}", aufgabe_id=aufgabe_id)
    return fid


def frage_weiterleiten(con, pid, von, fid, notiz=None):
    """Der Lead gibt eine Frage an den Entwickler weiter – dieselbe Frage (Nummer, Optionen, Verlauf bleiben)."""
    if von == ENTWICKLER or not ist_lead(con, pid, von):
        raise AmwFehler("Fragen leitet nur der Lead weiter")
    f = con.execute("SELECT * FROM frage WHERE id = ? AND projekt_id = ?", (fid, pid)).fetchone()
    if not f:
        raise AmwFehler(f"Frage F{fid} gibt es nicht")
    if f["status"] != "offen" or f["an"] != "tl":
        raise AmwFehler(f"F{fid} ist {'schon beim Entwickler' if f['an'] == 'entwickler' else f['status']}")
    if json.loads(f["optionen"] or "[]") and not (f["empfehlung"] and f["grund"]):
        raise AmwFehler(f"F{fid}: Fragen an den Entwickler brauchen Empfehlung und Grund – erst eine neue Frage mit beidem stellen")
    with db.schreiben(con):
        con.execute("UPDATE frage SET an = 'entwickler' WHERE id = ?", (fid,))
        db.einfuegen(con, "frage_verlauf", frage_id=fid, zeit_utc=db.jetzt(), von=von, art="nachtrag",
                     text=f"Weitergeleitet von {von} an {entwickler_name(con, pid)}" + (f": {notiz.strip()}" if (notiz or "").strip() else ""))
        if f["von"] not in (von, ENTWICKLER, "AMW"):
            _posten(con, pid, von, f["von"], "info", f"F{fid} an {entwickler_name(con, pid)} weitergeleitet", bis=f"F{fid}")
    return fid


def frage_antworten(con, pid, fid, antwort_art, antwort, kanal, von=ENTWICKLER):
    """Speichert die Antwort und benachrichtigt den Fragesteller (weckt). Text des Entwicklers → wortlaut."""
    f = con.execute("SELECT * FROM frage WHERE id = ? AND projekt_id = ?", (fid, pid)).fetchone()
    if not f:
        raise AmwFehler(f"Frage F{fid} gibt es nicht")
    if f["status"] != "offen":
        raise AmwFehler(f"F{fid} ist schon {f['status']}")
    if antwort_art == "option":
        kenn = [o["kenn"] for o in json.loads(f["optionen"])]
        if antwort not in kenn:
            raise AmwFehler(f"„{antwort}“ ist keine der Optionen {kenn}")
    t = db.jetzt()
    with db.schreiben(con):
        status = "offen" if antwort_art == "rueckfrage" else "beantwortet"
        con.execute("UPDATE frage SET status = ?, antwort_art = ?, antwort = ?, antwort_utc = ?, antwort_kanal = ?,"
                    " geparkt_utc = NULL, geparkt_von = NULL WHERE id = ?", (status, antwort_art, antwort, t, kanal, fid))
        if von == ENTWICKLER and antwort_art in ("text", "rueckfrage"):
            db.einfuegen(con, "wortlaut", projekt_id=pid, zeit_utc=t, text=antwort, kanal=kanal,
                         erfasst_von="amw", erfasst_utc=t, bemerkung=f"Antwort auf F{fid}")
        art = "frage" if antwort_art == "rueckfrage" else "antwort"
        nid = None
        if f["von"] != von:
            nid, _ = _posten(con, pid, von, f["von"], art, f"{'Rückfrage' if art == 'frage' else 'Antwort'} zu F{fid}: {antwort[:120]}",
                             text=antwort if len(antwort) > 120 else None, aufgabe_id=f["aufgabe_id"])
        roh = antwort
        if antwort_art == "option":                    # im Verlauf mit dem Text der Option
            antwort = next((f"{o['kenn']}) {o['text']}" for o in json.loads(f["optionen"]) if o["kenn"] == antwort), antwort)
        db.einfuegen(con, "frage_verlauf", frage_id=fid, zeit_utc=t, von=von,
                     art="rueckfrage" if antwort_art == "rueckfrage" else "antwort", text=antwort, nachricht_id=nid)
        if status == "beantwortet":                    # wer auf diese Frage gewartet hat, wird geweckt (L2)
            from . import wartegrund
            knapp = antwort if len(antwort) <= 60 else antwort[:57] + "…"
            wartegrund.erledige(con, pid, "frage", f"F{fid}", f"F{fid} beantwortet: {knapp}")
            if von == ENTWICKLER and f["aufgabe_id"]:
                wartegrund.erledige(con, pid, "entwickler", ENTWICKLER, f"{entwickler_name(con, pid)} hat F{fid} beantwortet",
                                    f["aufgabe_id"])
            v = con.execute("SELECT text FROM plan_ereignis WHERE projekt_id = ? AND art = 'dazwischen_vorschlag' AND text LIKE ?",
                            (pid, f"F{fid}|%")).fetchone()
            if v and von == ENTWICKLER and antwort_art == "option" and roh == "A":   # „Ja“ zum Vorschlag des Leads
                from . import arbeitsliste
                a = con.execute("SELECT * FROM aufgabe WHERE id = ?", (f["aufgabe_id"],)).fetchone()
                if a and a["status"] in ("wartet", "blockiert"):
                    arbeitsliste.dazwischen_ausfuehren(con, pid, ENTWICKLER, a, v["text"].split("|", 1)[1])
        # wer antwortet, hat die Nachträge im Verlauf gelesen – sie stehen nicht mehr unter „Nachrichten an dich“
        con.execute("UPDATE empfang SET status = 'erledigt', erledigt_utc = ? WHERE agent = ? AND status != 'erledigt'"
                    " AND nachricht_id IN (SELECT nachricht_id FROM frage_verlauf WHERE frage_id = ? AND nachricht_id IS NOT NULL)",
                    (t, von, fid))
    return status


def frage_nachtrag(con, pid, von, fid, text):
    """Der Fragesteller ergänzt seine Frage oder antwortet auf eine Rückfrage. Die Frage bleibt offen; wer gefragt
    wurde (Entwickler bzw. Lead), bekommt eine Nachricht – beim Entwickler unter „Nachrichten an dich“."""
    f = con.execute("SELECT * FROM frage WHERE id = ? AND projekt_id = ?", (fid, pid)).fetchone()
    if not f:
        raise AmwFehler(f"Frage F{fid} gibt es nicht")
    if f["status"] != "offen":
        raise AmwFehler(f"F{fid} ist schon {f['status']}")
    if von != f["von"] and not ist_lead(con, pid, von):
        raise AmwFehler(f"Nachträge zu F{fid} schreibt der Fragesteller ({f['von']}) oder der Lead")
    text = (text or "").strip()
    if not text:
        raise AmwFehler("Text fehlt")
    an = ENTWICKLER if f["an"] == "entwickler" else ",".join(
        r[0] for r in con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND rolle = 'lead'", (pid,))) or ENTWICKLER
    with db.schreiben(con):
        nid, _ = _posten(con, pid, von, an, "antwort", f"Nachtrag zu F{fid}: {text[:120]}",
                         text=text if len(text) > 120 else None, aufgabe_id=f["aufgabe_id"])
        db.einfuegen(con, "frage_verlauf", frage_id=fid, zeit_utc=db.jetzt(), von=von, art="nachtrag", text=text,
                     nachricht_id=nid)
    return nid


def frage_parken(con, pid, von, fid, parken=True, grund=None):
    """Parken: die Frage bleibt offen, steht aber in keiner offenen Liste und in keinem Zähler (geparkt_utc/_von);
    „wieder aufnehmen“ holt sie zurück. Beides steht im Verlauf der Frage. Parken darf der Entwickler, der Lead und
    wer gefragt hat; der Fragesteller bekommt eine Info (weckt nicht)."""
    f = con.execute("SELECT * FROM frage WHERE id = ? AND projekt_id = ?", (fid, pid)).fetchone()
    if not f:
        raise AmwFehler(f"Frage F{fid} gibt es nicht")
    if f["status"] != "offen":
        raise AmwFehler(f"F{fid} ist schon {f['status']}")
    if von != f["von"] and not ist_lead(con, pid, von):
        raise AmwFehler(f"F{fid} parken darf der Entwickler, der Lead oder der Fragesteller ({f['von']})")
    if bool(f["geparkt_utc"]) == parken:
        raise AmwFehler(f"F{fid} ist {'schon geparkt' if parken else 'nicht geparkt'}")
    grund = (grund or "").strip()
    text = ("Geparkt" if parken else "Wieder aufgenommen") + (f": {grund}" if grund else "")
    t = db.jetzt()
    with db.schreiben(con):
        con.execute("UPDATE frage SET geparkt_utc = ?, geparkt_von = ? WHERE id = ?", (t if parken else None, von if parken else None, fid))
        nid = None
        if f["von"] != von:
            nid, _ = _posten(con, pid, von, f["von"], "info", f"F{fid} {text[:1].lower() + text[1:120]}",
                             text=text if len(text) > 120 else None, aufgabe_id=f["aufgabe_id"])
        db.einfuegen(con, "frage_verlauf", frage_id=fid, zeit_utc=t, von=von, art="nachtrag", text=text, nachricht_id=nid)
    return "geparkt" if parken else "offen"


def offene_fragen(con, pid, an=None, geparkt=False):
    """Offene Fragen; geparkte nur mit geparkt=True (dann nur die)."""
    sql = "SELECT * FROM frage WHERE projekt_id = ? AND status = 'offen' AND geparkt_utc IS " + ("NOT NULL" if geparkt else "NULL")
    par = [pid]
    if an:
        sql += " AND an = ?"
        par.append(an)
    return con.execute(sql + " ORDER BY blockiert DESC, id", par).fetchall()


# --- Pflicht-Kontext --------------------------------------------------------------------------

KONTEXT_MAX = 9000   # Hook-Grenze 10 000 Zeichen, mit Luft


def kontext(con, pid, kennung):
    """Text, den der SessionStart-Hook nach Start/Komprimierung einspielt. Erzeugt aus den Daten, nie fest."""
    a = agent_zeile(con, pid, kennung)
    proj = con.execute("SELECT name FROM projekt WHERE id = ?", (pid,)).fetchone()["name"]
    vorher = con.execute("SELECT max(gestartet_utc) FROM sitzung WHERE agent_id = ? AND zustand != 'aktiv'",
                         (a["id"],)).fetchone()[0]
    wer = [x for x in ("Du führst dieses Projekt (Lead)" if a["rolle"] == "lead" else None,
                       f"Fachgebiet: {a['fachgebiet']}" if a["fachgebiet"] else None,
                       f"Zuständig für: {a['zustaendig']}" if a["zustaendig"] else None,
                       f"Fasst nicht an: {a['fasst_nicht_an']}" if a["fasst_nicht_an"] else None) if x]
    z = [f"AMW-PFLICHTKONTEXT für {kennung} (Projekt {proj}, Stand {db.jetzt()}). " + (" · ".join(wer) or "Fachgebiet: –"),
         f"AMW-Befehl: `{BEFEHL}` (unten kurz `amw`), immer mit `--von {kennung}`. Arbeitsweise: `amw lesen` → handeln →"
         " `amw erledigt <nr>` · melden: `amw posten --an <Agent|Entwickler> --art info|auftrag|frage|antwort --kurz …`"
         " · Arbeit holen: `amw schritt naechster --nehmen` · abschließen: `amw aufgabe fertig <nr> --beleg <commit>"
         " [--gruppe neu|verbessert|behoben --hinweis „ein Satz für Nutzer“ – für die Versionshinweise]"
         " --zusammenfassung …` · Ergebnisse (Text als .md, Bilder, Mockup als eine .html, Video als .mp4) nie lose ablegen: `amw dokument"
         " ablegen <datei> --titel … --art ergebnis|bericht|entwurf|mockup|bild --aufgabe <nr>` (neue Fassung: `amw dokument"
         " version <D-nr> <datei> --notiz …`) · Frage an den Menschen: `amw frage neu --an entwickler --kurz … --option A=… --empfehlung A"
         " --grund …` (Varianten zum Ansehen: `--anhang A=bild.png`) · Hilfe: `amw <befehl> --help`."]

    halte = aktive_sperren(con, pid, kennung, "halt")
    if halte:
        z.append("!! HALT GILT: " + " | ".join(f"#{s['id']} {s['von']}: {s['text']}" for s in halte)
                 + " – nichts Neues anfangen.")
    try:                                            # Schirm-Schalter: ob Fenster-Läufe gerade dürfen
        from . import schirm
        z.append(schirm.text(schirm.zustand(con)) + " – Läufe mit Fenster nur über `amw lauf start --schirm --warten`,"
                 " dann `amw lauf warte <nr>`.")
    except Exception:
        pass
    hinweise = aktive_sperren(con, pid, kennung, "hinweis")
    if hinweise:
        z.append("Geltende Anweisungen: " + " | ".join(f"{s['von']}: {s['text']}" for s in hinweise))

    try:                                            # Planung: Leitbild, aktive Bögen, nächster Schritt
        from . import planung
        z += planung.kontext_zeilen(con, pid, kennung)
    except Exception:
        pass

    from . import wartegrund
    eigene = aufgaben(con, pid, kennung)

    def worauf(x):
        g = ", ".join(r["bezug"] for r in wartegrund.offene(con, x["id"]))
        t = "; ".join(v for v in (g, x["wartet_auf"]) if v)
        return f" (wartet auf {t})" if t else ""
    from . import termine, themen
    tz = termine.kontext_zeile(con, pid)
    if tz:
        z.append(tz)
    z += themen.kontext_zeilen(con, pid, kennung)
    boegen, gefuehrt = fuehrt(con, pid, kennung)
    if boegen or gefuehrt:
        z.append("Du führst (federführend – Prüfergebnisse, Merge-Bitten, Fragen dazu kommen zu dir): " + "; ".join(
            [f"Meilenstein {b['id']} {b['titel'][:60]}" for b in boegen] + [f"A{x['id']} {x['titel'][:60]}" for x in gefuehrt]))
    from . import arbeitsliste
    liste = arbeitsliste.liste(con, pid, kennung)
    andere = [x for x in eigene if x["id"] not in {y["id"] for y in liste}]
    z.append(f"Deine Liste ({len(liste)}, von oben nach unten, eins nach dem anderen; wartet die laufende mit Grund, darfst du"
             " die nächste nehmen – ein zweites Stück starten geht nicht, solange eines läuft; Aufträge zu anderen Aufgaben"
             " bekommst du erst, wenn das laufende fertig ist oder wartet): " + ("; ".join(
                 f"{x['pos']}. A{x['id']} [{x['status']}] {x['titel'][:90]}" + worauf(x) for x in liste[:10]) or "leer"))
    if andere:
        z.append("Außerdem bei dir (geparkt/Pool): " + "; ".join(f"A{x['id']} [{x['status']}] {x['titel'][:60]}" for x in andere[:5]))

    wartende = con.execute("SELECT id, agent, titel FROM aufgabe WHERE projekt_id = ? AND status IN ('wartet', 'blockiert')"
                           " AND (wartet_auf LIKE ? OR id IN (SELECT aufgabe_id FROM wartegrund WHERE art = 'agent'"
                           " AND bezug = ? AND erledigt_utc IS NULL)) ORDER BY id LIMIT 10",
                           (pid, f"%{kennung}%", kennung)).fetchall()
    if wartende:
        z.append("Wartet auf dich: " + "; ".join(f"A{x['id']} ({x['agent']}) {x['titel']}" for x in wartende))

    pr = con.execute("SELECT * FROM pruefung WHERE projekt_id = ? AND ergebnis = 'offen' AND (pruefer = ? OR bauer = ?)"
                     " ORDER BY id", (pid, kennung, kennung)).fetchall()
    if pr:
        z.append("Offene Prüfungen: " + "; ".join(
            f"P{p['id']} {p['zweig']}@{p['sha'][:7]} {'prüfst du' if p['pruefer'] == kennung else 'prüft ' + p['pruefer']}"
            for p in pr))

    laeufe = con.execute("SELECT id, beschreibung, status FROM lauf WHERE projekt_id = ? AND agent = ?"
                         " AND status IN ('angemeldet', 'laeuft')", (pid, kennung)).fetchall()
    if laeufe:
        z.append("Deine Läufe: " + "; ".join(f"L{x['id']} [{x['status']}] {x['beschreibung']}" for x in laeufe))

    zahl = anzahl_offen(con, pid, kennung)
    if zahl:
        nachr = offene(con, pid, kennung, 8, neueste_zuerst=True)
        z.append(f"Offene Nachrichten ({zahl}, neueste zuerst): " + "; ".join(
            f"#{x['id']} {x['von']} [{x['art']}] {x['kurz'][:80]}" for x in nachr)
            + (" …" if zahl > 8 else "") + " → `amw lesen`")

    regeln = con.execute("SELECT nr, text, stand_utc, ebene, vorlage FROM regel WHERE projekt_id = ? ORDER BY ebene, nr",
                         (pid,)).fetchall()
    if regeln:
        neu = [r for r in regeln if vorher and r["stand_utc"] > vorher]
        z.append(f"Regeln: {len(regeln)} gültig (`amw regeln`)."
                 + (" GEÄNDERT seit deiner letzten Sitzung: " + " | ".join(
                     f"{'KR' if r['ebene'] == 'arbeit' else 'PR'}{r['nr']}: {r['text']}" for r in neu) if neu else ""))
        # Ein Lead, der als Chat arbeitet, wird nicht geweckt – die Takt-Regel aus dem Grund-Regelwerk steht deshalb im Wortlaut da
        if a["rolle"] == "lead" and (a["arbeitsweise"] or "") == "chat":
            for r in regeln:
                if (r["vorlage"] or "").startswith("W4/"):
                    z.append(f"Dein Rhythmus (KR{r['nr']}): {r['text']}")
    version = con.execute("SELECT version FROM release WHERE projekt_id = ? AND art = 'version' ORDER BY id DESC LIMIT 1", (pid,)).fetchone()
    if version:
        z.append(f"Version: aktuell {version['version']} · Schema MAJOR.MINOR.PATCH · jede Auslieferung eintragen: `amw release version`")

    rez = con.execute("SELECT name FROM rezept WHERE projekt_id = ? ORDER BY name", (pid,)).fetchall()
    if rez:
        z.append("Lauf-Rezepte: " + ", ".join(r["name"] for r in rez) + " (`amw rezept zeige <name>`)")

    text = "\n".join(z)
    return text if len(text) <= KONTEXT_MAX else text[:KONTEXT_MAX - 40] + "\n… (gekürzt, Rest per amw)"
