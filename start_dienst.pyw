"""Starter für amw-dienst ohne Konsolenfenster (pythonw). Wird von der geplanten Aufgabe „AMW Dienst“ aufgerufen.

Setzt nur den Suchpfad auf diesen Ordner; Datenbank ist daten/amw.db, sofern AMW_DB nicht gesetzt ist.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import dienst  # noqa: E402

sys.exit(dienst.main(sys.argv[1:]))
