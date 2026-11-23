"""„Macht gerade“ – von der AMW abgeleitet, nicht vom Agenten behauptet (A1953, TH155 Pkt 7, Entwurf #30624, Ja #30625).

Reihenfolge der Quellen (die erste, die es gibt):
1. Lauf: ein Lauf des Agenten mit Status „läuft“ (nie ein beendeter oder abgebrochener) – Zeit = Start des Laufs.
2. Aufgabe: seine zuletzt begonnene laufende Aufgabe – Zeit = Beginn.
3. Meldung: die Aufgabe aus seiner letzten eigenen Nachricht (Nummer oder A1234 im Text) – Zeit = Nachricht; nur, wenn die
   Aufgabe nicht fertig oder verworfen ist (A1989).
Läuft ein Lauf zu einer Aufgabe, zeigt der Text beides („A12 · Titel – L34 läuft“).

`amw taetigkeit` ergänzt nur: der Text erscheint dazu, wenn er nicht älter als die abgeleitete Quelle ist und keine andere
Aufgabe nennt. Gibt es keine abgeleitete Quelle, ist er allein die Angabe (Quelle „angabe“). Nennt der Text einen Lauf L1234,
der nicht mehr läuft, fällt er weg (A1989) – das gilt auch für die Angabe, die beim Laufstart gesetzt wurde.

Alter und veraltet: jeder Wert trägt Quelle und Zeit. Deckendes Ereignis ist der Puls der Sitzung (Hook, Statuszeile,
Ereignis, eigene Angabe). Ohne Puls seit VERALTET_S gilt der Wert als veraltet. Ist die letzte Sitzung eines Terminal-Agenten
beendet, ruht oder tot, gibt es kein „macht gerade“. Ein Chat oder ein Agent ohne Sitzung hat keine Hooks: kein Urteil
„veraltet“.
"""
import re

from . import kern

VERALTET_S = 30 * 60
AUFGABE_IN_TEXT = re.compile(r"\bA(\d{3,6})\b")
LAUF_IN_TEXT = re.compile(r"\bL(\d{1,6})\b")


def _neuester(*zeiten):
    z = [x for x in zeiten if x]
    return max(z) if z else None


def ableiten(con, pid, kennung):
    """{"text", "aufgabe", "quelle" (lauf|aufgabe|meldung|angabe), "seit_utc", "ergaenzung", "puls_utc", "veraltet"} oder
    None (nichts bekannt bzw. Sitzung nicht aktiv)."""
    g = con.execute("SELECT g.id, coalesce(g.arbeitsweise, 'terminal') AS weise FROM agent g WHERE g.projekt_id = ? AND g.kennung = ?",
                    (pid, kennung)).fetchone()
    if not g:
        return None
    s = con.execute("SELECT * FROM sitzung WHERE agent_id = ? ORDER BY id DESC LIMIT 1", (g["id"],)).fetchone()
    chat = g["weise"] == "chat"
    if not chat and s and s["zustand"] != "aktiv":
        return None                                    # beendet, ruht oder tot: er macht gerade nichts (ohne Sitzung: abgeleitet)
    aus = None
    l = con.execute("SELECT * FROM lauf WHERE projekt_id = ? AND agent = ? AND status = 'laeuft' ORDER BY id DESC LIMIT 1",
                    (pid, kennung)).fetchone()
    a = con.execute("SELECT id, titel, begonnen_utc FROM aufgabe WHERE projekt_id = ? AND agent = ? AND status = 'laeuft'"
                    " ORDER BY begonnen_utc DESC LIMIT 1", (pid, kennung)).fetchone()
    if l:
        la = l["aufgabe_id"] or (a["id"] if a else None)
        t = con.execute("SELECT titel FROM aufgabe WHERE id = ?", (la,)).fetchone() if la else None
        lauf = f"L{l['id']} läuft" + (f": {l['beschreibung'][:80]}" if l["beschreibung"] else "")
        aus = {"text": f"A{la} · {t['titel']} – {lauf}" if t else lauf, "aufgabe": la if t else None, "quelle": "lauf",
               "seit_utc": l["start_utc"] or l["angemeldet_utc"]}
    elif a:
        aus = {"text": f"A{a['id']} · {a['titel']}", "aufgabe": a["id"], "quelle": "aufgabe", "seit_utc": a["begonnen_utc"]}
    else:
        m = con.execute("SELECT aufgabe_id, kurz, zeit_utc FROM nachricht WHERE projekt_id = ? AND von = ? ORDER BY id DESC LIMIT 1",
                        (pid, kennung)).fetchone()
        if m:
            treffer = AUFGABE_IN_TEXT.search(m["kurz"] or "")
            aid = m["aufgabe_id"] or (int(treffer.group(1)) if treffer else None)
            t = con.execute("SELECT titel, status FROM aufgabe WHERE projekt_id = ? AND id = ?", (pid, aid)).fetchone() if aid else None
            if t and t["status"] not in ("fertig", "verworfen"):      # A1989: Fertiges macht er nicht mehr
                aus = {"text": f"A{aid} · {t['titel']}", "aufgabe": aid, "quelle": "meldung", "seit_utc": m["zeit_utc"]}
    angabe = (s["taetigkeit"] or "").strip() if s and s["zustand"] == "aktiv" else ""
    if angabe and _nennt_beendeten_lauf(con, pid, angabe):
        angabe = ""                                    # A1989: „L3096 Planer …“, aber L3096 ist längst fertig
    angabe_utc = s["taetigkeit_utc"] if angabe else None
    if aus is None:
        if not angabe:
            return None
        aus = {"text": angabe, "aufgabe": s["aufgabe_id"], "quelle": "angabe", "seit_utc": angabe_utc}
        angabe = ""
    passt = angabe and (not s["aufgabe_id"] or s["aufgabe_id"] == aus["aufgabe"]) and not _nennt_andere(angabe, aus["aufgabe"])
    aus["ergaenzung"] = angabe if passt and (angabe_utc or "") >= (aus["seit_utc"] or "") and angabe != aus["text"] else None
    puls = _neuester(*(s[k] for k in ("letzter_puls_utc", "status_utc", "ereignis_utc", "taetigkeit_utc"))) if s else None
    aus["puls_utc"] = puls
    aus["veraltet"] = None if (chat or not s) else (not puls or kern.alter_s(puls) >= VERALTET_S)   # ohne Hooks: kein Urteil
    return aus


def _nennt_beendeten_lauf(con, pid, text):
    """Nennt die eigene Angabe einen beendeten Lauf (fertig, abgebrochen …)? Ein Lauf, der läuft oder in der Schlange wartet
    (angemeldet), zählt nicht als beendet; unbekannte Nummern auch nicht."""
    for n in {int(x) for x in LAUF_IN_TEXT.findall(text)}:
        l = con.execute("SELECT status FROM lauf WHERE projekt_id = ? AND id = ?", (pid, n)).fetchone()
        if l and l["status"] not in ("laeuft", "angemeldet"):
            return True
    return False


def _nennt_andere(text, aid):
    """Nennt die eigene Angabe eine andere Aufgabe als die abgeleitete? („A1955 …“, während A1966 läuft)"""
    nummern = {int(x) for x in AUFGABE_IN_TEXT.findall(text)}
    return bool(nummern) and aid not in nummern


def zeile(g):
    """Eine Zeile für die Befehlszeile: „A12 · Titel – L34 läuft (Lauf, seit 5 min)“ + „ – veraltet?“."""
    if not g:
        return None
    q = {"lauf": "Lauf", "aufgabe": "Aufgabe", "meldung": "letzte Meldung", "angabe": "eigene Angabe"}[g["quelle"]]
    alter = _alter(g["seit_utc"])
    return (g["text"][:110] + (f" · {g['ergaenzung'][:60]}" if g["ergaenzung"] else "") + f" ({q}{', ' + alter if alter else ''})"
            + (" – veraltet? (seit 30 min kein Lebenszeichen)" if g["veraltet"] else ""))


def _alter(utc):
    if not utc:
        return ""
    s = kern.alter_s(utc)
    return f"seit {int(s // 60)} min" if s < 3600 else f"seit {s / 3600:.0f} h" if s < 86400 else f"seit {s / 86400:.0f} T"
