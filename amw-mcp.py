"""Starter für den MCP-Server der AMW ohne PYTHONPATH (für die Claude-Desktop-Konfiguration):

    python F:/amw/amw-mcp.py --projekt <Name> --von <Lead>

Der Bindestrich im Namen ist Absicht: die Datei ist nicht importierbar und verdeckt das Paket `amw` nicht.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import mcp_server  # noqa: E402

mcp_server.main(sys.argv[1:])
