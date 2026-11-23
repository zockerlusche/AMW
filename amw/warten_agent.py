"""Stillstand beim Warten auf einen anderen Agenten (A1997, TH157 → doc/automatismen.md).

Befund 23.11.: A1993 wartete auf CCamw2 („1.168.1 live, dann eigener Stapel“). CCamw2 lieferte aus, schrieb aber nicht –
der Wartegrund blieb offen, der Wartende stand 3 h still, und keine Leerlauf-Meldung kam (mit wartender Aufgabe gilt ein
Agent nicht als frei).

Die Dienst-Runde prüft je Agent, der NUR Aufgaben hat, die auf einen ANDEREN Agenten warten (kein Stück in „läuft“, jede
wartende Aufgabe hat offene Gründe, und alle sind Agenten-Gründe), je offenem Agenten-Grund:
- seit `warten_agent_min` (Projekt-Einstellung, Vorgabe 60) nichts vom Erwarteten an den Wartenden gekommen (gezählt ab
  dem Grund oder seiner letzten Nachricht an ihn) → einmal eine Meldung an den Lead „CC1 wartet seit … auf CC2 (A12) –
  Grund noch aktuell?“; kommt wieder etwas und danach erneut Funkstille, wieder einmal;
- seit dem Grund ist eine Version live gegangen → sofort die Meldung an den Lead und ein Weckruf an den Wartenden mit der
  Version (einmal je Grund und Version).
Nichts wird automatisch abgehakt. Ereignis `warten_agent` (Text: Grund-Nummer und Anlass). Kein Schema.
"""
import json
import time

from . import db, kern

MIN = 60
ART = "warten_agent"


def _sek(utc):
    return db.utc_sek(utc)


def _utc(sek):
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(sek))


def warte_min(con, pid):
    r = con.execute("SELECT einstellungen FROM projekt WHERE id = ?", (pid,)).fetchone()
    try:
        v = json.loads((r[0] if r else None) or "{}").get("warten_agent_min")
        return float(v) if v is not None else MIN
    except (TypeError, ValueError):
        return MIN


def nur_auf_agenten(con, pid, kennung):
    """Offene Agenten-Gründe [(grund, aufgabe)], wenn der Agent nur auf andere Agenten wartet – sonst []."""
    if con.execute("SELECT 1 FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status = 'laeuft' AND einstufung = 'aktiv'"
                   " LIMIT 1", (pid, kennung)).fetchone():
        return []
    aus = []
    for a in con.execute("SELECT * FROM aufgabe WHERE projekt_id = ? AND agent = ? AND einstufung = 'aktiv'"
                         " AND status IN ('wartet', 'blockiert') ORDER BY rang, id", (pid, kennung)).fetchall():
        gruende = con.execute("SELECT * FROM wartegrund WHERE aufgabe_id = ? AND erledigt_utc IS NULL ORDER BY id",
                              (a["id"],)).fetchall()
        if not gruende or any(g["art"] != "agent" or g["bezug"] == kennung for g in gruende):
            return []                                   # startklar, oder wartet (auch) auf anderes als einen Agenten
        aus += [(g, a) for g in gruende]
    return aus


def _letzte_von(con, pid, von, an):
    r = con.execute("SELECT max(n.zeit_utc) FROM nachricht n JOIN empfang e ON e.nachricht_id = n.id WHERE n.projekt_id = ?"
                    " AND n.von = ? AND e.agent = ?", (pid, von, an)).fetchone()
    return r[0] if r else None


def _schon(con, pid, signatur):
    return bool(con.execute("SELECT 1 FROM plan_ereignis WHERE projekt_id = ? AND art = ? AND text = ?",
                            (pid, ART, signatur)).fetchone())


def runde(con, jetzt=None):
    """Dienst-Runde über alle Projekte. Gibt Ereignis-Zeilen zurück."""
    jetzt = jetzt or time.time()
    ereignisse = []
    for p in con.execute("SELECT id FROM projekt").fetchall():
        pid = p["id"]
        lead = kern.lead(con, pid)
        grenze = warte_min(con, pid) * 60
        for ag in con.execute("SELECT kennung FROM agent WHERE projekt_id = ? AND entfernt_utc IS NULL ORDER BY id",
                              (pid,)).fetchall():
            k = ag["kennung"]
            for g, a in nur_auf_agenten(con, pid, k):
                x = g["bezug"]
                seit = g["angelegt_utc"]
                version = con.execute("SELECT id, version, zeit_utc FROM release WHERE projekt_id = ? AND art = 'version'"
                                      " AND zeit_utc > ? ORDER BY zeit_utc DESC, id DESC LIMIT 1", (pid, seit)).fetchone()
                basis = max(seit, _letzte_von(con, pid, x, k) or seit)
                still = jetzt - _sek(basis) >= grenze
                if version:
                    signatur, anlass = f"G{g['id']}:R{version['id']}", (
                        f"Seither ist {version['version']} live ({version['zeit_utc'][11:16]} UTC) – von {x} kam dazu nichts.")
                elif still:
                    signatur, anlass = f"G{g['id']}:{basis}", (
                        f"Seit {basis[11:16]} UTC ({int((jetzt - _sek(basis)) // 60)} min) kam nichts von {x} an {k}.")
                else:
                    continue
                if _schon(con, pid, signatur):
                    continue
                kurz = f"{k} wartet seit {seit[11:16]} UTC auf {x} (A{a['id']}) – Grund noch aktuell?"
                text = (f"{anlass}\nA{a['id']} {a['titel']}\nIst der Grund erledigt: amw aufgabe wartet {a['id']} --erledigt {x}"
                        f" (oder {x} schreibt mit --aufgabe {a['id']}).")
                with db.schreiben(con):
                    db.einfuegen(con, "plan_ereignis", projekt_id=pid, zeit_utc=_utc(jetzt), von="AMW", art=ART,
                                 aufgabe_id=a["id"], text=signatur)
                    if lead and lead != k:
                        kern._posten(con, pid, "AMW", lead, "meldung", kurz[:140], text, aufgabe_id=a["id"])
                    if version:
                        kern._posten(con, pid, "AMW", k, "meldung",
                                     f"{version['version']} ist live – du wartest auf {x} (A{a['id']}): Grund noch aktuell?"[:140],
                                     f"{anlass}\nWeiter: amw aufgabe wartet {a['id']} --erledigt {x}, dann amw aufgabe start {a['id']}"
                                     " – oder weiter warten, wenn der Grund noch gilt.", aufgabe_id=a["id"])
                ereignisse.append(f"{k} wartet auf {x} (A{a['id']}): {'Version ' + version['version'] if version else 'Funkstille'}")
    return ereignisse
