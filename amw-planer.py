"""Planer eines Themas (A1940): eigener, losgelöster Prozess, den die AMW nach der Freigabe eines Themas (oder auf Befehl) startet.
Er meldet sich in der Lauf-Schlange an, lässt einen frischen claude -p (nur Lesen) einen Plan als Daten entwerfen und trägt ihn ein.

    python -I amw-planer.py --projekt-id <n> --thema <TH-Nr> --fassung <nr>

Der Bindestrich im Namen ist Absicht: die Datei ist nicht importierbar und verdeckt das Paket `amw` nicht.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import planer  # noqa: E402

planer.main(sys.argv[1:])
