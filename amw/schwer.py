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
    ("Test-Suite", r"-m\s+unittest\s+discover\b|-m\s+amw\.testlauf\b(?!\s+--arbeiter)|\bpytest\b(?![^|;&]*(\s-k\s|::))|\bdotnet\s+test\b|\bnpm\s+(run\s+)?test\b"
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


HEREDOC = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*(?:\n|$)", re.S)        # bash: <<'EOF' … EOF
HERESTRING = re.compile(r"@(['\"])\r?\n.*?\r?\n\1@", re.S)                               # PowerShell: @' … '@
STARTER_VOR = re.compile(r"(?:\b(?:cmd(?:\.exe)?\s+/[ck]|(?:ba|z)?sh\s+-l?c|pwsh(?:\.exe)?(?:\s+-\w+)*\s+-(?:Command|c)|"
                         r"powershell(?:\.exe)?(?:\s+-\w+)*\s+-(?:Command|c)|python\S*\s+-c"
                         # A1980 (#30776): weitere Aufrufe, die Text ausführen – Invoke-Expression/iex, Start-Process (Programm oder
                         # -ArgumentList, auch als Liste "a", "b"), start [/x] ["Titel"] am Befehlsanfang, Aufruf-Operator & (nicht &&)
                         r"|(?:Invoke-Expression|iex)(?:\s+-Command)?"
                         r"|Start-Process(?:\s+-FilePath)?|Start-Process\b[^;|\n]*?-(?:ArgumentList|Args)(?:\s*(?:'[^']*'|\"[^\"]*\")\s*,)*"
                         r")\s*|(?:^|[;|(\n]|&&|\bcmd(?:\.exe)?\s+/[ck])\s*start\b(?:\s+/\w+)*\s+(?:(?:\"[^\"]*\"|'[^']*')\s+)?"
                         r"|(?:^|[^&])&\s*)$", re.I)
ZITAT = re.compile(r"'(?:[^'\\]|\\.)*'|\"(?:[^\"\\]|\\.)*\"", re.S)


def _ohne_text(befehl):
    """A1975: was nur Text ist, fällt weg – Heredocs, Here-Strings, Inhalt in Anführungszeichen. Ausnahme: Anführungszeichen
    direkt nach einem Shell-Aufruf (cmd /c "…", bash -c '…', powershell -Command "…") – dort steht ein Befehl, der läuft."""
    t = HERESTRING.sub(" ", HEREDOC.sub(" ", str(befehl or "")))
    aus, pos = [], 0
    for m in ZITAT.finditer(t):
        aus.append(t[pos:m.start()])
        aus.append(m.group(0)[1:-1] if STARTER_VOR.search(t[:m.start()]) else "''")
        pos = m.end()
    aus.append(t[pos:])
    return "".join(aus)


def erkennen(befehl, eigene=None):
    """Name der Art, wenn der Befehl schwer ist und nicht schon über die Warteschlange läuft – sonst None. A1975: nur was
    ausgeführt wird, zählt – derselbe Text als Nachricht, Commit-Text oder Datei-Inhalt nicht."""
    roh = str(befehl or "")
    befehl = " ".join(roh.split())
    if not befehl or SCHON_ANGEMELDET.search(befehl):
        return None
    ausgefuehrt = " ".join(_ohne_text(roh).split())               # erst Text heraus (Zeilen zählen), dann Leerzeichen
    for name, m in muster(eigene):
        if m.search(ausgefuehrt):
            return name
    return None


def ersatz(befehl, name, amw="amw"):
    """Derselbe Befehl über die Warteschlange. Ein verketteter Befehl geht als eine Befehlszeile in Anführungszeichen."""
    befehl = str(befehl).strip()
    if VERKETTET.search(befehl):
        befehl = '"' + befehl.replace("\\", "\\\\").replace('"', '\\"') + '"'
    return f'{amw} lauf ausfuehren --leicht --beschreibung "{name}" -- {befehl}'


def erkennbar(eingabe):
    """Geht es überhaupt um einen Shell-Befehl vor seinem Start? (Schnelle Vorprüfung, bevor die Datenbank gefragt wird.)"""
    return (eingabe.get("hook_event_name") == "PreToolUse" and eingabe.get("tool_name") in ("Bash", "PowerShell")
            and bool((eingabe.get("tool_input") or {}).get("command")))


def eigene_pruefen(liste):
    """Muster eines Projekts prüfen und säubern: [{"name", "muster"}], höchstens 20; wirft ValueError mit Grund."""
    if not isinstance(liste, list) or len(liste) > 20:
        raise ValueError("höchstens 20 Einträge")
    aus = []
    for e in liste:
        name, m = str((e or {}).get("name") or "").strip()[:40], str((e or {}).get("muster") or "").strip()
        if not name or not m:
            raise ValueError("jeder Eintrag braucht einen Namen und ein Muster")
        if len(m) > 200:
            raise ValueError(f"{name}: Muster höchstens 200 Zeichen")
        try:
            re.compile(m)
        except re.error as f:
            raise ValueError(f"{name}: Muster ungültig ({f})") from None
        aus.append({"name": name, "muster": m})
    return aus


def entscheide(eingabe, eigene=None, amw="amw"):
    """Hook-Eingabe (PreToolUse) → None (nichts tun) oder die Antwort, die den Befehl abweist und den Ersatz nennt."""
    if not erkennbar(eingabe):
        return None
    befehl = (eingabe.get("tool_input") or {}).get("command")
    name = erkennen(befehl, eigene)
    if not name:
        return None
    grund = (f"{name}: Dieser Befehl ist ein schwerer Lauf und geht über die Warteschlange des Rechners – mehrere Projekte "
             f"teilen sich diesen PC. Starte ihn so (wartet, bis der Rechner frei ist, läuft dann und gibt den Rückgabewert durch):\n"
             f"{ersatz(befehl, name, amw)}")
    return {"hookSpecificOutput": {"hookEventName": "PreToolUse", "permissionDecision": "deny", "permissionDecisionReason": grund}}
