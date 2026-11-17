"""Starter eines -p-Pakets (A1874, M50 S6c): eigener, losgelöster Prozess, den der Disponent startet. Er besitzt das
Job-Objekt des Arbeiters – ein Neustart des Dienstes beendet ihn nicht. Arbeiter → Prüfung C → Entscheidung E1–E8.

    python -I amw-arbeiter.py --projekt-id <n> --aufgabe <n> --platz <n>

Der Bindestrich im Namen ist Absicht: die Datei ist nicht importierbar und verdeckt das Paket `amw` nicht.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import disponent  # noqa: E402

disponent.main(sys.argv[1:])
