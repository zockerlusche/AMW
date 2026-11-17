"""Rückmelde-Connector eines -p-Laufs (A1857, D1258 §6a.1): stdio-MCP-Server mit genau einem Werkzeug ergebnis_melden.

Die AMW startet ihn je Lauf über --mcp-config mit `python -I <dieser Pfad>` – absoluter Pfad im Ordner der AMW, damit nie Code
aus dem Klon des Arbeitsplatzes geladen wird. Der Bindestrich im Namen ist Absicht: die Datei ist nicht importierbar.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import rueckmeldung  # noqa: E402

rueckmeldung.laufen()
