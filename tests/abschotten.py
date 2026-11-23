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
    os.environ["AMW_STIL_AUS"] = "1"               # A1973: eine Prüfbitte mit Bildern stößt in Tests nie einen echten Stil-Leser an
    os.environ["AMW_SPRACHE_AUS"] = "1"            # A2004: eine Prüfbitte stößt in Tests nie eine echte Sprachprüfung an
    os.environ["AMW_FOLGEN_AUS"] = "1"             # A1957: eigene Änderungen des Menschen gelten in Tests sofort (ohne Prüfer)
    os.environ["AMW_PLANER_AUS"] = "1"             # A1940: thema freigeben stößt in Tests nie einen echten Planer an
    os.environ["AMW_SYSTEMLAUFWERK"] = "-"         # A1921: Test-Ordner liegen auf dem Systemlaufwerk – die Sperre prüft test_platz
    atexit.register(shutil.rmtree, ORDNER, True)
else:
    ORDNER = os.environ["AMW_TEST_LOKAL"]
