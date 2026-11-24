"""Dasselbe Ergebnis je Anfrage, Dienst-Runde und Synchronisierung nur einmal rechnen (A2081).

`with einmal.merken(con): …` schaltet den Merker an der Verbindung ein, `einmal.einmal(con, schlüssel, f)` rechnet f() darin nur beim
ersten Mal. Außerhalb von merken() ist einmal() einfach f() – dort ändert sich nichts.
- Gültig ist ein Wert nur, solange sich die Datenbank nicht ändert: PRAGMA data_version (andere Verbindungen) und total_changes
  (die eigene) – nie nach Zeit. Ändert sich eins davon, fängt der Merker leer an; eine Änderung ist also sofort sichtbar.
- In einer offenen Schreib-Transaktion wird nichts gemerkt und nichts Gemerktes geliefert (ein ROLLBACK nähme die Grundlage weg).
- schnappschuss=True (Anfrage der Seite, Synchronisierung): die Verbindung liest für den ganzen Block einen festen Stand (Lese-
  Transaktion, nur im WAL-Modus) – sonst fängt der Merker bei jeder fremden Änderung während einer langen Runde neu an. Nur für
  reines Lesen: ein db.schreiben() darin scheitert. Die nächste Anfrage sieht den neuen Stand.
- Wer den Wert verändern könnte, bekommt eine Kopie: kopie=True kopiert eine Ebene (dict oder Liste von dicts).
- Nicht für Werte, die von der Uhrzeit oder von Prozessen abhängen, über die Dauer einer Anfrage hinaus.
"""
from contextlib import contextmanager
from typing import Any


@contextmanager
def merken(con, schnappschuss=False):
    """Den Merker dieser Verbindung für diesen Block einschalten (verschachtelt: der äußere gilt weiter)."""
    if getattr(con, "merker", None) is not None or not hasattr(con, "merker"):
        yield
        return
    fest = schnappschuss and not con.in_transaction and con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    con.merker = {}
    if fest:
        con.execute("BEGIN")
        con.schnappschuss = True
    try:
        yield
    finally:
        con.merker, con.schnappschuss = None, False
        if fest and con.in_transaction:
            con.execute("ROLLBACK")                       # nur gelesen – es gibt nichts zu behalten


def _stand(con):
    if con.schnappschuss:                                   # fester Stand: andere Verbindungen ändern daran nichts
        return "fest", con.total_changes
    return con.execute("PRAGMA data_version").fetchone()[0], con.total_changes


def _kopie(x: Any) -> Any:
    if isinstance(x, dict):
        return dict(x)
    if isinstance(x, list):
        return [dict(z) if isinstance(z, dict) else z for z in x]
    return x


def einmal(con, schluessel, f, kopie=False) -> Any:
    """f() – in merken() nur einmal je Stand der Datenbank. Ein Fehler wird nicht gemerkt."""
    m = getattr(con, "merker", None)
    if m is None or (con.in_transaction and not con.schnappschuss):
        return f()
    stand = _stand(con)
    if m.get("stand") != stand:
        m.clear()
        m["stand"] = stand
    if schluessel in m:
        wert = m[schluessel]
    else:
        wert = f()
        if m.get("stand") == stand == _stand(con):           # änderte sich währenddessen etwas, gilt der Wert nur für diesen Aufruf
            m[schluessel] = wert
    return _kopie(wert) if kopie else wert
