"""Starter für das Symbol im Infobereich (A1746) – mit pythonw ohne Konsole: pythonw F:/amw/amw-tray.pyw"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from amw import tray  # noqa: E402

sys.exit(tray.main())
