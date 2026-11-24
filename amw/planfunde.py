"""A2076: Funde eines abgelehnten Planentwurfs in Menschensprache (TH156: keine Schemabegriffe).

Der Prüfer des Planers (planer.pruefen) nennt Funde technisch, für den Planer und den Lead. Hier wird jeder Fund zu einer Art
mit Angaben – die Seite setzt daraus den Satz in der Sprache des Nutzers zusammen (Texte pjw_fx_<art>), der Verlauf den deutschen.
Unbekanntes bleibt allgemein („sonst“): den genauen Wortlaut hat der Lead in seiner Meldung.
"""
import re

_ARTEN = [
    (re.compile(r"^(Feinp|P)laner-Lauf:"), "lauf"),
    (re.compile(r"\bA(?P<a>\d+) ist laufend"), "laeuft"),
    (re.compile(r"\bA(?P<a>\d+) ist nicht begonnen"), "offen"),
    (re.compile(r"\bA(?P<a>\d+) ist fertig"), "fertig"),
    (re.compile(r"\bA(?P<a>\d+) ist kein betroffenes Paket"), "fremd"),
    (re.compile(r"länger als (?P<n>\d+) Zeichen"), "lang"),
    (re.compile(r"schon gebaut:"), "gebaut"),
    (re.compile(r"gesperrte Pfade"), "pfade"),
    (re.compile(r"trifft die Sperre"), "sperre"),
    (re.compile(r"ohne Verkettung"), "kette"),
    (re.compile(r"Abnahme-Befehl"), "befehl"),
    (re.compile(r"im Kreis"), "kreis"),
    (re.compile(r"doppelt"), "doppelt"),
    (re.compile(r"kein JSON|oben muss ein Objekt|unbekannte Felder|kein Objekt"), "form"),
    (re.compile(r"fehlt$|mindestens ein"), "fehlt"),
]


def deuten(con, pid, funde):
    """Liste der Funde → [{"art", "x": {…}}] ohne Wiederholungen; bei Paketen mit dem Titel."""
    aus = []
    for f in [funde] if isinstance(funde, str) else funde or []:
        art, x = "sonst", {}
        for muster, a in _ARTEN:
            m = muster.search(str(f))
            if m:
                art, g = a, m.groupdict()
                if g.get("a"):
                    r = con.execute("SELECT titel FROM aufgabe WHERE id = ? AND projekt_id = ?", (int(g["a"]), pid)).fetchone()
                    x = {"p": r["titel"] if r else f"A{g['a']}"}
                elif g.get("n"):
                    x = {"n": int(g["n"])}
                break
        e = {"art": art, "x": x}
        if e not in aus:
            aus.append(e)
    return aus


def saetze(con, pid, funde):
    """Die Funde als deutsche Sätze (für den Verlauf)."""
    from . import workbench
    t = workbench.texte("de")
    aus = []
    for e in deuten(con, pid, funde):
        s = t["pjw_fx_" + e["art"]]
        for k, v in e["x"].items():
            s = s.replace("{" + k + "}", str(v))
        aus.append(s)
    return aus
