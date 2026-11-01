"""Starter für die Statusline-Brücke ohne PYTHONPATH (→ amw/statusline.py):

    "statusLine": {"type": "command", "command": "python -X utf8 F:/amw/amw-statusline.py"}

Merkt sich je Sitzung Kontext, Nutzungsgrenzen, Kosten und Modell für die AMW und gibt die bisherige Statusline
(Einstellung „statusline_weiter“) unverändert aus. Fällt etwas aus, erscheint eine schlichte Zeile – nie ein Absturz.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from amw import statusline  # noqa: E402
    sys.exit(statusline.main())
except Exception as e:                      # die Statusline darf die Sitzung nie stören
    print(f"AMW-Statusline: {type(e).__name__}")
