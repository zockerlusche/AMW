"""Negativprobe einer neuen Claude-Code-Version (A1906): eigener, losgelöster Prozess, den der Disponent einmal je Version
startet. Er meldet sich in der Lauf-Schlange an, prüft mit echtem Claude Code (Haiku) und trägt das Ergebnis ein.

    python -I amw-versionsprobe.py --projekt-id <n> --version <x.y.z>

Der Bindestrich im Namen ist Absicht: die Datei ist nicht importierbar und verdeckt das Paket `amw` nicht.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import versionsprobe  # noqa: E402

versionsprobe.main(sys.argv[1:])
