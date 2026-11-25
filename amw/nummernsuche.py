"""Suche nach einer Nummer: „D1714“, „a12“, „#33327“ oder nur „1714“ findet das Ding selbst (nur lesen).

Eine Zeile je Treffer: {"art", "ref", "titel", "zusatz", "zeit", "genau": True}. ref ist Kürzel + Nummer („D1714“,
„M19“ mit der Projektnummer bogen.nr, „#33327“). Alles, was keine reine Nummer (mit oder ohne Kürzel) ist, findet nichts.
"""
import re

MUSTER = re.compile(r"^(TH|[DAFBWMLP#])\s*(\d{1,18})$", re.IGNORECASE)
ZAHL = re.compile(r"^\d{1,18}$")

# Reihenfolge bei einer Zahl ohne Kürzel
REIHENFOLGE = ("D", "A", "F", "M", "B", "W", "TH", "L", "P", "#")

# Kürzel → (art, SQL mit Spalten titel, zusatz, zeit; ? = Projekt, ? = Nummer)
_SQL = {
    "D": ("dokument", "SELECT titel, art AS zusatz, angelegt_utc AS zeit FROM dokument"
                      " WHERE projekt_id = ? AND id = ? AND status != 'geloescht'"),
    "A": ("aufgabe", "SELECT titel, status AS zusatz, angelegt_utc AS zeit FROM aufgabe WHERE projekt_id = ? AND id = ?"),
    "F": ("frage", "SELECT kurz AS titel, status AS zusatz, zeit_utc AS zeit FROM frage WHERE projekt_id = ? AND id = ?"),
    "B": ("beschluss", "SELECT stichwort AS titel, status AS zusatz, zeit_utc AS zeit FROM beschluss"
                       " WHERE projekt_id = ? AND id = ?"),
    "W": ("wortlaut", "SELECT substr(text, 1, 120) AS titel, kanal AS zusatz, zeit_utc AS zeit FROM wortlaut"
                      " WHERE projekt_id = ? AND id = ?"),
    "M": ("meilenstein", "SELECT titel, status AS zusatz, angelegt_utc AS zeit FROM bogen WHERE projekt_id = ? AND nr = ?"),
    "TH": ("thema", "SELECT name AS titel, CASE stil WHEN 1 THEN 'stil' ELSE '' END AS zusatz, angelegt_utc AS zeit"
                    " FROM thema WHERE projekt_id = ? AND id = ?"),
    "L": ("lauf", "SELECT beschreibung AS titel, status AS zusatz, angemeldet_utc AS zeit FROM lauf"
                  " WHERE projekt_id = ? AND id = ?"),
    "P": ("pruefung", "SELECT zweig AS titel, ergebnis AS zusatz, angefragt_utc AS zeit FROM pruefung"
                      " WHERE projekt_id = ? AND id = ?"),
    "#": ("nachricht", "SELECT kurz AS titel, art AS zusatz, zeit_utc AS zeit FROM nachricht WHERE projekt_id = ? AND id = ?"),
}


def lesen(such):
    """(Kürzel oder None, Nummer) oder None, wenn such keine reine Nummer ist."""
    s = (such or "").strip()
    m = MUSTER.match(s)
    if m:
        return m.group(1).upper(), int(m.group(2))
    if ZAHL.match(s):
        return None, int(s)
    return None


def dokument_nr(such):
    """Nummer des Dokuments, das such meint („D1714“ oder „1714“), sonst None."""
    p = lesen(such)
    return p[1] if p and p[0] in (None, "D") else None


def treffer(con, pid, such):
    p = lesen(such)
    if not p:
        return []
    kuerzel, nr = p
    aus = []
    for k in ((kuerzel,) if kuerzel else REIHENFOLGE):
        art, sql = _SQL[k]
        for r in con.execute(sql, (pid, nr)):
            aus.append({"art": art, "ref": f"{k}{nr}", "titel": r["titel"], "zusatz": r["zusatz"], "zeit": r["zeit"],
                        "genau": True})
    return aus
