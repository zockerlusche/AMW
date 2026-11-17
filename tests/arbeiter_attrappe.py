"""Attrappe für `claude -p` (Tests zu amw.arbeiter): liest die Schalter, gibt ein init-Ereignis wie Claude Code 2.1.326 aus und
endet mit einem result-Ereignis. ATTRAPPE_ART: ok | mcp | werkzeug | modell | rechte | plugin | kind (startet einen Kindprozess,
schreibt dessen PID nach ATTRAPPE_PID und wartet) | haengt (wartet ohne Ende). ATTRAPPE_UMGEBUNG: Datei für die Umgebung."""
import json
import os
import subprocess
import sys
import time


def wert(name, vorgabe=None):
    a = sys.argv
    return a[a.index(name) + 1] if name in a else vorgabe


art = os.environ.get("ATTRAPPE_ART", "ok")
auftrag = sys.stdin.read()
if os.environ.get("ATTRAPPE_UMGEBUNG"):
    with open(os.environ["ATTRAPPE_UMGEBUNG"], "w", encoding="utf-8") as f:
        json.dump({"umgebung": dict(os.environ), "argv": sys.argv, "auftrag": auftrag}, f)
modell = {"haiku": "claude-haiku-5-5", "opus": "claude-opus-5-5"}.get(wert("--model"), wert("--model"))
init = {"type": "system", "subtype": "init", "cwd": os.getcwd(), "session_id": "00000000-0000-4000-8000-000000000001",
        "tools": (wert("--tools") or "").split(","), "mcp_servers": [], "model": modell, "permissionMode": wert("--permission-mode"),
        "slash_commands": [], "skills": [], "agents": ["claude", "Explore"], "additional_directories": [],
        "plugins": [{"name": "cc-plugin-telemetry", "path": "builtin", "source": "cc-plugin-telemetry@builtin"}],
        "claude_code_version": os.environ.get("ATTRAPPE_VERSION", "2.1.326")}
if "--mcp-config" in sys.argv:                 # S5b: der Rückmelde-Connector ist verbunden (wie Claude Code ihn meldet)
    init["mcp_servers"] = [{"name": "amw-rueckmeldung", "status": os.environ.get("ATTRAPPE_MCP_STATUS", "connected")}]
    init["tools"] = init["tools"] + ["mcp__amw-rueckmeldung__ergebnis_melden"]
if art == "mcp":
    init["mcp_servers"] = init["mcp_servers"] + [{"name": "bus", "status": "connected"}]
elif art == "werkzeug":
    init["tools"] = init["tools"] + ["Agent"]
elif art == "modell":
    init["model"] = "claude-sonnet-5-5"
elif art == "rechte":
    init["permissionMode"] = "default"
elif art == "plugin":
    init["plugins"].append({"name": "fremd", "path": "C:/plugins/fremd", "source": "fremd@markt"})
if art in ("kind", "abweichung_kind", "kind_bleibt"):
    kind = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"], creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    with open(os.environ["ATTRAPPE_PID"], "w") as f:
        f.write(f"{os.getpid()} {kind.pid}")
    if art == "abweichung_kind":
        init["mcp_servers"] = [{"name": "bus", "status": "connected"}]
print(json.dumps(init), flush=True)
if art == "enkel_pipe":                    # P260: ein Enkel erbt stdout und hält die Pipe offen, claude selbst endet
    enkel = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(600)"], stdout=sys.stdout, close_fds=False,
                             creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))   # erbt die Pipe ausdrücklich
    with open(os.environ["ATTRAPPE_PID"], "w") as f:
        f.write(f"{os.getpid()} {enkel.pid}")
if art in ("kind", "haengt", "abweichung_kind"):
    time.sleep(600)
if art == "fremdes_werkzeug":
    print(json.dumps({"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Agent", "input": {}}]}}),
          flush=True)
    time.sleep(600)
for i, m in enumerate(json.loads(os.environ.get("ATTRAPPE_MELDUNGEN", "[]"))):   # S5b: Aufrufe von ergebnis_melden
    ok = m.pop("_ok", True)
    print(json.dumps({"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": f"m{i}", "name": "mcp__amw-rueckmeldung__ergebnis_melden", "input": m}]}}), flush=True)
    print(json.dumps({"type": "user", "message": {"content": [
        {"type": "tool_result", "tool_use_id": f"m{i}", "is_error": not ok, "content": "angenommen" if ok else "Nicht angenommen"}]}}), flush=True)
print(json.dumps({"type": "assistant", "message": {"content": [{"type": "text", "text": "fertig"}]}}), flush=True)
print(json.dumps({"type": "result", "subtype": "success", "is_error": False, "num_turns": 1, "total_cost_usd": 0.001,
                  "session_id": init["session_id"], "result": "fertig", "permission_denials": []}), flush=True)
