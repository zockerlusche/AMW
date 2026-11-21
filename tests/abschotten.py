"""Tests arbeiten nie im echten Zugangs-Ordner des PCs.

Jede Testdatei importiert dieses Modul als Allererstes (tests/test_abschotten.py prüft das). Es setzt LOCALAPPDATA auf
einen leeren, eigenen Ordner – dort liegen bei der AMW Zugänge (Online-Speicher, Benachrichtigungen), Einstellungen des
PCs und Protokolle. So kann kein Test den echten Zugang lesen, überschreiben oder vom Zustand des PCs abhängen. Der
Ordner gilt für den ganzen Testlauf (auch für Kindprozesse) und wird am Ende gelöscht. Tests, die einen eigenen Ordner
brauchen, setzen LOCALAPPDATA weiter selbst.
"""
import atexit
import os
import shutil
import tempfile

if not os.environ.get("AMW_TEST_LOKAL"):
    ORDNER = tempfile.mkdtemp(prefix="amw-test-lokal-")
    os.makedirs(os.path.join(ORDNER, "amw"), exist_ok=True)
    os.environ["AMW_TEST_LOKAL"] = ORDNER
    os.environ["LOCALAPPDATA"] = ORDNER
    os.environ["AMW_CLAUDE_BASIS"] = os.path.join(ORDNER, "claude")   # A1779: nie die echten Claude-Ablagen messen
    os.environ["AMW_STARTSKRIPT"] = os.path.join(ORDNER, "agenten-start.bat")   # A1883: nie ins Repo (Arbeitsordner/Prüfklon)
    os.environ["AMW_CLAUDE_VERSION"] = "2.1.326"   # A1906: nie vom installierten Claude Code abhängen (Grundbestand, wie die Attrappe)
    os.environ["AMW_GEGENLESEN_AUS"] = "1"         # A1914: thema pflegen stößt in Tests nie einen echten Gegenleser an
    atexit.register(shutil.rmtree, ORDNER, True)
else:
    ORDNER = os.environ["AMW_TEST_LOKAL"]
