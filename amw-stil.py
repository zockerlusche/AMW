"""Stil-Leser einer Prüfbitte (A1973): eigener, losgelöster Prozess, den die AMW nach einer Prüfbitte mit sichtbarer Änderung
startet. Er meldet sich in der Lauf-Schlange an, lässt einen frischen claude -p (nur Lesen) die Bilder gegen das Stil-Thema
prüfen und schickt den Befund.

    python -I amw-stil.py --projekt-id <n> --pruefung <P-Nr>

Der Bindestrich im Namen ist Absicht: die Datei ist nicht importierbar und verdeckt das Paket `amw` nicht.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import stil  # noqa: E402

stil.main(sys.argv[1:])
