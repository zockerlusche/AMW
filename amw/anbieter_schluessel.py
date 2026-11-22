"""apiKeyHelper für Arbeiter mit einem freigegebenen Anbieter (A1931, #29930): gibt den Inhalt einer Schlüsseldatei aus –
nur, wenn ihr Pfad in der Freigabe-Liste der AMW steht (anbieter.FREIGABE). Mit jedem anderen Pfad: nichts ausgeben, Code 2.
Keine Abhängigkeit zur Datenbank (läuft in der Umgebung des Arbeiters mit der Datenbank des Platzes)."""
import json
import os
import sys

FREIGABE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "daten", "anbieter-freigabe.json")   # = anbieter.FREIGABE


def erlaubt(pfad, freigabe):
    try:
        with open(freigabe, encoding="utf-8") as f:
            liste = json.load(f).get("pfade") or []
    except (OSError, ValueError, AttributeError):
        return False
    return os.path.normcase(os.path.abspath(pfad)) in {os.path.normcase(x) for x in liste}


def ausgeben(pfad, freigabe=None, aus=None, fehler=None):
    """Rückgabe: Code (0 ausgegeben, 2 nicht freigegeben oder nicht lesbar). Der Inhalt geht nur nach `aus`, nie in eine Meldung."""
    aus, fehler = aus or sys.stdout, fehler or sys.stderr
    if not pfad or not erlaubt(pfad, freigabe or FREIGABE):
        fehler.write("Schlüsseldatei nicht freigegeben\n")
        return 2
    try:
        with open(pfad, encoding="utf-8") as f:
            wert = f.read().strip()
    except OSError:
        fehler.write("Schlüsseldatei nicht lesbar\n")
        return 2
    if not wert:
        fehler.write("Schlüsseldatei leer\n")
        return 2
    aus.write(wert)
    return 0


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    return ausgeben(argv[0] if argv else None)
