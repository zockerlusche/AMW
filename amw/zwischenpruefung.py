"""A2102: Eingriffe – wer auf einen Prüfpunkt warten würde.

Für eine Stelle im Plan (hinter einem Paket) sagt diese Sicht, was bei einem Prüfpunkt beim Menschen warten würde und was
weiterläuft. Vorgänger sind die der Planung (Tabelle abhaengigkeit; die alte Textspalte aufgabe.abhaengig_von ist seit
Schema 7 dorthin übernommen und wird nirgends mehr gelesen). Ob ein Paket schon begonnen hat, entscheidet dieselbe Einteilung
wie bei der Konzeptänderung (auch für p-Pakete nach ihrem Zustand).

Nur lesen: nichts wird gesetzt, angehalten oder gemeldet.
"""
from . import kern, konzeptaenderung, planung


def wartende(con, pid, nach_aufgabe):
    """Was bei einem Prüfpunkt hinter nach_aufgabe geschähe – Nummern in der Reihenfolge Rang, Nummer:

    {"wartet": [A…]        – nicht begonnene Pakete direkt oder über mehrere Stufen dahinter (auch hinter fertigen),
     "laeuft_schon": [A…]  – davon die schon begonnenen; sie laufen zu Ende,
     "weiter": n}          – Zahl der übrigen offenen Pakete des Projekts (auch nach_aufgabe selbst, solange es offen ist).

    Fertige (auch gemergte p-Pakete) und verworfene zählen nirgends mit."""
    a = con.execute("SELECT id FROM aufgabe WHERE id = ? AND projekt_id = ?", (nach_aufgabe, pid)).fetchone()
    if not a:
        raise kern.AmwFehler(f"A{nach_aufgabe} gibt es nicht")
    start = a["id"]
    aus = {"wartet": [], "laeuft_schon": [], "weiter": 0}
    for x in kern.aufgaben(con, pid):                     # offene, nach Rang und Nummer
        gruppe = konzeptaenderung.einteilen(con, x)
        if gruppe not in ("stoppen", "zu_ende"):
            continue
        if x["id"] == start or not planung._erreichbar(con, start, x["id"]):     # im Kreis wartet ein Paket nicht auf sich selbst
            aus["weiter"] += 1
        else:
            aus["wartet" if gruppe == "stoppen" else "laeuft_schon"].append(x["id"])
    return aus
