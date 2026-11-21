"""Gegenleser eines Themas (A1914): eigener, losgelöster Prozess, den die AMW nach einer neuen Fassung eines Pflegers startet.
Er meldet sich in der Lauf-Schlange an, lässt einen frischen claude -p (nur Lesen) gegenlesen und schickt die Einwände.

    python -I amw-gegenlesen.py --projekt-id <n> --thema <TH-Nr> --fassung <nr>

Der Bindestrich im Namen ist Absicht: die Datei ist nicht importierbar und verdeckt das Paket `amw` nicht.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import gegenlesen  # noqa: E402

gegenlesen.main(sys.argv[1:])
