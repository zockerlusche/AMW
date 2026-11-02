"""Starter für die Kommandozeile ohne PYTHONPATH – aus jeder Shell gleich (Bash, PowerShell):

    python C:/amw/amw-cli.py lesen --von CC1

Der Bindestrich im Namen ist Absicht: die Datei ist nicht importierbar und verdeckt das Paket `amw` nicht.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import cli  # noqa: E402

sys.exit(cli.main(sys.argv[1:]))
