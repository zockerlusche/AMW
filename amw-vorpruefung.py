"""Sprachprüfung einer Prüfbitte (A2004): eigener, losgelöster Prozess, den die AMW nach jeder Prüfbitte startet. Er meldet sich
in der Lauf-Schlange an, fährt pyright auf genau dem Stand gegen main (nur neue Fehler) und schickt den Befund an den Prüfer.

    python -I amw-vorpruefung.py --projekt-id <n> --pruefung <P-Nr>

Der Bindestrich im Namen ist Absicht: die Datei ist nicht importierbar und verdeckt das Paket `amw` nicht.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import vorpruefung  # noqa: E402

vorpruefung.main(sys.argv[1:])
