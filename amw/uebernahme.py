"""Übernahme des heutigen LayerIT-Busses in eine NEUE amw.db (→ doc/10-architektur.md §6).

Liest bus.db ausschließlich lesend (mode=ro) und schreibt eine neue Datenbank; eine vorhandene Zieldatei wird
nie überschrieben. Wiederholbar: für das Umschalten (doc/07 E6) einfach neu in eine frische Datei laufen lassen.
Nummern von Nachrichten, Aufgaben, Beschlüssen, Wortlaut und Fragen an den Entwickler bleiben gleich
(#16160, A1207, B2362, Frage 334). Fragen an den TL bekommen 100000 + alte Nummer (T5 → F100005).
Übernommene Empfänge gelten als schon geweckt, damit der Dienst den Altbestand nicht zustellt.
Nicht übernommen: LayerIT-Fach-Tabellen (kommen als Projekt-Erweiterung), Alt-Tabellen (doc/03 §2), devlog_post.

Aufruf: python -X utf8 -m amw.uebernahme --von F:\\agent-bus\\projekt-netly\\bus.db --nach daten\\amw.db
"""
import argparse
import json
import os
import sqlite3
import sys

from . import db

PROJEKT = "LayerIT"
TL_FRAGE_VERSATZ = 100000

ART = {  # alte Art → neue Art (doc/04 #15: aus 35 Arten im Altbestand wird die eine Liste)
    "auftrag": "auftrag", "eilig": "auftrag", "dringend": "auftrag", "vorgabe": "auftrag", "richtung": "auftrag",
    "plan": "auftrag", "antrag": "auftrag", "push_bitte": "auftrag",
    "frage": "frage", "anfrage": "frage",
    "antwort": "antwort",
    "entscheidung": "freigabe", "entscheid": "freigabe", "freigabe": "freigabe", "push_ok": "freigabe",
    "korrektur": "korrektur", "storno": "korrektur", "regel": "korrektur",
    "stopp": "stopp",
    "meldung": "meldung", "befund": "meldung", "ergebnis": "meldung", "fertig": "meldung", "abnahme": "meldung",
    "bug": "meldung", "hinweis": "meldung", "ergaenzung": "meldung", "lob": "meldung", "rueckmeldung": "meldung",
    "pruefung": "meldung", "prio": "meldung",
    "info": "info", "takt": "info", "marcel": "info", "puls": "info",
}
EMPFANG = {"offen": "offen", "gelesen": "gelesen", "in_arbeit": "gelesen", "erledigt": "erledigt", "archiv": "erledigt"}
EINSTUFUNG = {"aktiv": "aktiv", "keine_prio": "keine_prio", "geparkt": "geparkt", "pool_ausloeser": "pool",
              "HOCH": "aktiv", "mittel": "aktiv"}
FRAGE_TL = {"offen": "offen", "entschieden": "beantwortet", "an_marcel": "beantwortet", "verworfen": "verworfen"}
RAUSCHEN = ("RECHEN-JOB", "ENDE RECHEN-JOB", "LEICHT-JOB", "ENDE LEICHT-JOB", "MESSFENSTER")


def _alle(q, sql):
    return q.execute(sql).fetchall()


def uebernehmen(quelle, ziel, ausgabe=print):
    if os.path.exists(ziel):
        raise FileExistsError(f"{ziel} gibt es schon – Übernahme nur in eine neue Datei")
    q = sqlite3.connect(f"file:{quelle}?mode=ro", uri=True)
    q.row_factory = sqlite3.Row
    z = db.anlegen(ziel)
    z.execute("PRAGMA foreign_keys = OFF")          # Altbestand verweist teils auf fehlende Zeilen; Prüfung am Ende
    t = db.jetzt()
    zahlen = {}

    def ein(tabelle, **w):
        w.setdefault("herkunft", "bus.db")
        db.einfuegen(z, tabelle, **w)
        zahlen[tabelle] = zahlen.get(tabelle, 0) + 1

    with db.schreiben(z):
        ein("projekt", name=PROJEKT, beschreibung="Godot-Spiel; übernommen aus dem LayerIT-Bus",
            pfad_repo="F:\\layerit", angelegt_utc=t)
        pid = z.execute("SELECT id FROM projekt WHERE name = ?", (PROJEKT,)).fetchone()[0]

        rund = set((q.execute("SELECT wert FROM meta WHERE schluessel = 'agenten'").fetchone() or [""])[0].split(","))
        for r in _alle(q, "SELECT * FROM agent_status ORDER BY rowid"):
            ein("agent", projekt_id=pid, kennung=r["agent"], rolle="lead" if r["agent"] == "TL" else None,
                soll="an" if r["soll"] == "online" else "aus", empfaengt_rund=int(r["agent"] in rund),
                puls_grenze_s=r["puls_grenze_s"] or 120, angelegt_utc=r["geaendert_utc"] or t)

        for r in _alle(q, "SELECT * FROM nachricht ORDER BY id"):
            alt = (r["art"] or "info").strip()
            neu = ART.get(alt, "info")
            text = r["text"]
            if alt != neu:
                text = (text or "") + f"\n— Übernahme: Art im alten Bus „{alt}“"
            if r["datei_pfad"]:
                text = (text or "") + f"\n— Anhang: {r['datei_pfad']}"
            ein("nachricht", id=r["id"], projekt_id=pid, zeit_utc=r["zeit_utc"], von=r["von"], art=neu,
                kurz=r["kurz"], text=text, antwort_auf=r["antwort_auf"], aufgabe_id=r["aufgabe_id"])

        rauschen = {r["id"] for r in q.execute(
            "SELECT id FROM nachricht WHERE " + " OR ".join("kurz LIKE ?" for _ in RAUSCHEN), [p + "%" for p in RAUSCHEN])}
        for r in _alle(q, "SELECT e.*, n.zeit_utc AS nzeit FROM empfang e JOIN nachricht n ON n.id = e.nachricht_id"):
            status = EMPFANG.get(r["status"], "offen")
            bem = r["bemerkung"]
            if r["status"] not in ("offen", "gelesen", "erledigt"):
                bem = ((bem + " · ") if bem else "") + f"Übernahme: Status im alten Bus „{r['status']}“"
            if status == "offen" and r["nachricht_id"] in rauschen:
                status, bem = "erledigt", ((bem + " · ") if bem else "") + "Übernahme: Job-Zeile, nie handlungspflichtig"
            ein("empfang", nachricht_id=r["nachricht_id"], agent=r["agent"], status=status,
                gelesen_utc=r["gelesen_utc"], erledigt_utc=r["erledigt_utc"] or (t if status == "erledigt" else None),
                geweckt_utc=r["nzeit"], bemerkung=bem)

        for r in _alle(q, "SELECT * FROM aufgabe ORDER BY id"):
            beleg = r["commit_sha"] or r["ergebnis_pfad"] or (f"Nachricht #{r['ergebnis_nachricht']}"
                                                               if r["ergebnis_nachricht"] else None)
            if r["status"] in ("fertig", "verworfen") and not beleg:
                beleg = f"Altbestand bus.db A{r['id']} (ohne eigenen Beleg)"
            bem = r["bemerkung"]
            if r["einstufung"] not in ("aktiv", "keine_prio", "geparkt", "pool_ausloeser", None):
                bem = ((bem + " || ") if bem else "") + f"Übernahme: Einstufung im alten Bus „{r['einstufung']}“"
            ein("aufgabe", id=r["id"], projekt_id=pid, titel=r["titel"], auftrag=r["auftrag"], agent=r["agent"],
                angelegt_von="TL", status=r["status"], einstufung=EINSTUFUNG.get(r["einstufung"], "aktiv"),
                rang=10 if r["einstufung"] == "HOCH" else (r["rang"] or 50), wartet_auf=r["wartet_auf"],
                abhaengig_von=r["abhaengig_von"], phase=r["phase"], beleg=beleg, bemerkung=bem,
                angelegt_utc=r["angelegt_utc"], begonnen_utc=r["begonnen_utc"], fertig_utc=r["fertig_utc"],
                geparkt_utc=r["geparkt_utc"], geparkt_von=r["geparkt_von"])

        for r in _alle(q, "SELECT * FROM frage_marcel ORDER BY id"):
            ein("frage", id=r["id"], projekt_id=pid, an="entwickler", von=r["von"] or "TL", zeit_utc=r["zeit_utc"],
                kurz=r["frage"], worum=r["erklaerung"],
                optionen=json.dumps([{"kenn": "alt", "text": r["optionen"]}] if r["optionen"] else [], ensure_ascii=False),
                empfehlung=None, grund=" · ".join(x for x in (r["empfehlung"] and f"Empfehlung: {r['empfehlung']}",
                                                              r["empfehlung_grund"]) if x) or None,
                fundstellen=r["quelle"], aufgabe_id=r["aufgabe_id"], blockiert=int(bool(r["blockiert"])),
                folge_von=r["folge_von"], status=r["status"], antwort=r["antwort"], antwort_utc=r["antwort_utc"],
                antwort_art="text" if r["antwort"] else None, antwort_kanal="bus.db" if r["antwort"] else None)

        for r in _alle(q, "SELECT * FROM frage_tl ORDER BY id"):
            antwort = r["antwort"] or (f"an Marcel weitergegeben: Frage {r['frage_marcel_id']}" if r["frage_marcel_id"] else None)
            ein("frage", id=TL_FRAGE_VERSATZ + r["id"], projekt_id=pid, an="tl", von=r["von"], zeit_utc=r["zeit_utc"],
                kurz=r["frage"], aufgabe_id=r["aufgabe_id"], status=FRAGE_TL.get(r["status"], "offen"),
                antwort=antwort, antwort_utc=r["antwort_utc"], antwort_art="text" if antwort else None,
                antwort_kanal="bus.db" if antwort else None)

        for r in _alle(q, "SELECT * FROM marcel_wort ORDER BY id"):
            ein("wortlaut", id=r["id"], projekt_id=pid, zeit_utc=r["zeit_utc"], text=r["wortlaut"], kanal=r["kanal"],
                erfasst_von=r["erfasst_von"], erfasst_utc=r["erfasst_utc"], bemerkung=r["bemerkung"])

        for r in _alle(q, "SELECT * FROM beschluss ORDER BY id"):
            ein("beschluss", id=r["id"], projekt_id=pid, zeit_utc=r["zeit_utc"] or r["angelegt_utc"], thema=r["thema"],
                stichwort=r["stichwort"] or "(ohne Stichwort)", regel=r["regel"] or "", quelle=r["quelle"] or "–",
                status=r["status"] or "unklar", ersetzt_durch=r["ersetzt_durch"],
                wortlaut_ids=str(r["wort_id"]) if r["wort_id"] else None, aufgabe_ids=r["aufgabe_ids"],
                angelegt_von=r["angelegt_von"], angelegt_utc=r["angelegt_utc"])

        for r in _alle(q, "SELECT * FROM kernregel ORDER BY nr"):
            ein("regel", ebene="arbeit", projekt_id=None, nr=r["nr"], text=r["regel"], beleg=r["beleg"],
                stand_utc=r["angelegt_utc"])
        for r in _alle(q, "SELECT * FROM baugesetz ORDER BY nr"):
            ein("regel", ebene="projekt", projekt_id=pid, nr=r["nr"], teil=r["teil"], text=r["regel"], beleg=r["beleg"],
                stand_utc=r["angelegt_utc"])

        for r in _alle(q, "SELECT * FROM release ORDER BY eingetragen_utc"):
            ein("release", projekt_id=pid, art="version", version=r["version"], zeit_utc=r["zeit_utc"] or r["eingetragen_utc"],
                commit_sha=r["commit_sha"], titel=r["titel"] or r["version"], text_intern=r["text_spielsprache"],
                text_oeffentlich=r["devlog_text"], aufgaben=r["aufgaben"],
                veroeffentlicht_utc=r["zeit_utc"] if r["oeffentlich"] else None,
                eingetragen_von=r["eingetragen_von"] or "TL")

        for r in _alle(q, "SELECT * FROM tl_stand"):
            ein("notiz", projekt_id=pid, schluessel=r["schluessel"], wert=r["wert"])

    fehlende = z.execute("PRAGMA foreign_key_check").fetchall()
    z.execute("PRAGMA foreign_keys = ON")
    vergleich = [("agent_status", "agent"), ("nachricht", "nachricht"), ("empfang", "empfang"), ("aufgabe", "aufgabe"),
                 ("marcel_wort", "wortlaut"), ("beschluss", "beschluss"), ("release", "release"), ("tl_stand", "notiz")]
    ausgabe(f"Übernahme {quelle} → {ziel}")
    for alt, neu in vergleich:
        n_alt = q.execute(f"SELECT count(*) FROM {alt}").fetchone()[0]
        n_neu = z.execute(f"SELECT count(*) FROM {neu}").fetchone()[0]
        ausgabe(f"  {alt:<13} {n_alt:>6} → {neu:<10} {n_neu:>6} {'ok' if n_alt == n_neu else 'ABWEICHUNG'}")
    n_alt = sum(q.execute(f"SELECT count(*) FROM {t_}").fetchone()[0] for t_ in ("frage_marcel", "frage_tl"))
    ausgabe(f"  frage_marcel+frage_tl {n_alt:>6} → frage {z.execute('SELECT count(*) FROM frage').fetchone()[0]:>6}")
    n_alt = sum(q.execute(f"SELECT count(*) FROM {t_}").fetchone()[0] for t_ in ("kernregel", "baugesetz"))
    ausgabe(f"  kernregel+baugesetz   {n_alt:>6} → regel {z.execute('SELECT count(*) FROM regel').fetchone()[0]:>6}")
    if fehlende:
        je = {}
        for f in fehlende:
            je[(f[0], f[2])] = je.get((f[0], f[2]), 0) + 1
        ausgabe("  Verweise ins Leere (Altbestand, bleiben stehen): "
                + ", ".join(f"{a}→{b} {n}" for (a, b), n in sorted(je.items())))
    q.close()
    z.close()
    return zahlen


def main(argv=None):
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except AttributeError:
        pass
    p = argparse.ArgumentParser(prog="amw-uebernahme")
    p.add_argument("--von", required=True, help="alte bus.db (wird nur gelesen)")
    p.add_argument("--nach", required=True, help="neue amw.db (darf es noch nicht geben)")
    a = p.parse_args(argv)
    uebernehmen(a.von, a.nach)
    return 0


if __name__ == "__main__":
    sys.exit(main())
