"""Folgenprüfer (A1957): eigener, losgelöster Prozess, den die AMW nach einer eigenen Änderung des Menschen startet.
Er meldet sich in der Lauf-Schlange an, lässt einen frischen claude -p (nur Lesen) die Folgen prüfen und trägt das Ergebnis ein.

    python -I amw-folgen.py --projekt-id <n> --aenderung <Ereignis-Nr>

Der Bindestrich im Namen ist Absicht: die Datei ist nicht importierbar und verdeckt das Paket `amw` nicht.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import folgen  # noqa: E402

folgen.main(sys.argv[1:])
