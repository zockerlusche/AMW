"""Schwere Befehle erkennen – damit sie sich von selbst bei der Warteschlange des Rechners anmelden.

Mehrere Projekte teilen sich einen PC. Eine ganze Test-Suite, Browser-Tests, ein Build oder ein Abzug des Web-Zweigs
brauchen Arbeitsspeicher und Rechenzeit; starten mehrere zugleich, scheitern sie. Statt eines Gebots („denk an die
Warteschlange“) gibt es einen Automatismus: Ein Hook sieht jeden Befehl, bevor er startet. Ist er schwer und läuft nicht
schon über die Warteschlange, wird er abgewiesen – und der fertige Ersatz-Befehl steht dabei.

Diese Datei entscheidet nur (rein, ohne Datenbank und ohne Prozess); eingehängt wird sie in amw/hook.py.
"""
import re

# (Name, Muster). Der Name steht in der Warteschlange als Beschreibung, wenn der Agent keine eigene angibt.
MUSTER = (
    ("Browser-Tests", r"\b(playwright\s+test|cypress\s+run)\b|-m\s+unittest\b[^|;&]*\btest_bedienung\b(?![\w.]*\.)"),
    ("Test-Suite", r"-m\s+unittest\s+discover\b|\bpytest\b(?![^|;&]*(\s-k\s|::))|\bdotnet\s+test\b|\bnpm\s+(run\s+)?test\b"
                   r"|\bcargo\s+test\b|\bgo\s+test\s+\./\.\.\."),
    ("Build", r"\bdotnet\s+(build|publish)\b|\bmsbuild\b|\bnpm\s+run\s+build\b|\bcargo\s+build\b"
              r"|\bgodot\S*\s[^|;&]*--(build-solutions|export-release|export-debug|import)\b"),
    ("Web-Abzug", r"\bgit\s+subtree\s+split\b"),
)
SCHON_ANGEMELDET = re.compile(r"\blauf\s+(ausfuehren|start|warte)\b")
VERKETTET = re.compile(r"&&|\|\||[|;<>]")


def muster(eigene=None):
    """Die mitgelieferten Muster und die des Projekts ([{"name": …, "muster": …}]; ein ungültiges wird übergangen)."""
    aus = []
    for e in eigene or ():
        try:
            aus.append((str(e["name"])[:40] or "Schwerer Lauf", re.compile(str(e["muster"]), re.I)))
        except (KeyError, TypeError, re.error):
            continue
    return aus + [(name, re.compile(m, re.I)) for name, m in MUSTER]


def erkennen(befehl, eigene=None):
    """Name der Art, wenn der Befehl schwer ist und nicht schon über die Warteschlange läuft – sonst None."""
    befehl = " ".join(str(befehl or "").split())
    if not befehl or SCHON_ANGEMELDET.search(befehl):
        return None
    for name, m in muster(eigene):
        if m.search(befehl):
            return name
    return None


def ersatz(befehl, name, amw="amw"):
    """Derselbe Befehl über die Warteschlange. Ein verketteter Befehl geht als eine Befehlszeile in Anführungszeichen."""
    befehl = str(befehl).strip()
    if VERKETTET.search(befehl):
        befehl = '"' + befehl.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f'{amw} lauf ausfuehren --beschreibung "{name}" -- {befehl}'


def entscheide(eingabe, eigene=None, amw="amw"):
    """Hook-Eingabe (PreToolUse) → None (nichts tun) oder die Antwort, die den Befehl abweist und den Ersatz nennt."""
    if eingabe.get("hook_event_name") != "PreToolUse" or eingabe.get("tool_name") not in ("Bash", "PowerShell"):
        return None
    befehl = (eingabe.get("tool_input") or {}).get("command")
    name = erkennen(befehl, eigene)
    if not name:
        return None
    grund = (f"{name}: Dieser Befehl ist ein schwerer Lauf und geht über die Warteschlange des Rechners – mehrere Projekte "
             f"teilen sich diesen PC. Starte ihn so (wartet, bis der Rechner frei ist, läuft dann und gibt den Rückgabewert durch):\n"
             f"{ersatz(befehl, name, amw)}")
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": grund}}
