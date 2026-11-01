"""Starter für den SessionStart-Hook ohne PYTHONPATH (→ amw/hook.py):

    python -X utf8 F:/amw/amw-hook.py

Meldet die Sitzung beim Wächter an, wenn die Umgebungsvariable AMW_AGENT gesetzt ist (Startskript je Agent),
und gibt den Pflicht-Kontext aus. Ohne AMW_AGENT tut er nichts (andere Sitzungen im selben Ordner).
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import hook  # noqa: E402

sys.exit(hook.main())
