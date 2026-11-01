# Recherche: Agenten-Workbenches – Grundlage für Stufen B–D, F

Stand 01.11.2026. „(u)“ = nur Sekundärquelle.

- **Feine Zustände je Agent über Hooks** (Claude Code, Agentenansicht „claude agents“: Working, Needs input, Idle, Completed, Failed, Stopped): Hook-Ereignisse `Notification` (Typen u. a. `permission_prompt`, `idle_prompt`, `agent_needs_input`, `agent_completed`, `elicitation_dialog`), `Stop`, `StopFailure` (Fehlerart: rate_limit, overloaded, authentication_failed, billing_error, server_error, max_output_tokens, …), `UserPromptSubmit`, `SessionEnd` (Grund: clear, resume, logout, prompt_input_exit, other). Command-Hooks mit `"async": true` blockieren nicht; HTTP-Hooks posten das JSON. Gemeinsame Felder: session_id, transcript_path, cwd, hook_event_name, permission_mode, effort.
- **Statusline-JSON** (bei jeder Änderung): session_id, model.display_name, effort.level, cost.total_cost_usd, context_window.used_percentage / context_window_size, rate_limits.five_hour/seven_day.used_percentage + resets_at (nur Abo, nach der ersten Antwort), prompt_cache …
- **Verbrauch:** OpenTelemetry (`claude_code.cost.usage`, `claude_code.token.usage`, Ereignis `api_request` mit Kosten/Tokens; kein Datei-Exporter) · Transkript-JSONL ist intern und ändert sich (nur Notbehelf) · ccusage zum Gegenprüfen. Kosten sind Schätzungen zum Listenpreis; im Abo zählt die 5-Stunden-Grenze.
- **Push:** ntfy (kostenlos, Topic = Geheimnis, X-Cache/X-Firebase abschaltbar, bis 3 Aktionsknöpfe), Pushover (4,99 $ einmalig, zuverlässig), Telegram-Bot (kostenlos, nicht E2E) – nur Metadaten senden.
- **Kurz reinschauen und antworten** (Agentenansicht): offene Frage zeigen, mit Ziffer beantworten.
- **Zeitleiste je Sitzung** (AgentOps, Langfuse): Ereignisse zeitlich, „blocked on user“ messen.
- **Qualitäts-Gates per Hook** (TaskCompleted/TeammateIdle: Exit 2 blockiert mit Rückmeldung).
- **Prognose mit Bandbreite** (Linear: Tempo der letzten Wochen, ±40 %; Monte Carlo P50/P85).
- **„Was ist passiert, während du weg warst“** (Session-Recap).
- **Aufgabenbrett als MCP-Server, Worktree je Agent** (Vibe Kanban, Claude Squad) – später.
- Wecken über Named Pipe: erste Zeile `{"type":"auth","token":…}`, eine Zeile innerhalb 30 s, Drosselung bei schnellen Folgen.
- Claude Code CLI (2.1.309): `--session-id <uuid>`, `-n/--name`, `--resume <id>`, `--settings <json|datei>`, `--effort`, `--model`, `--permission-mode`, `--add-dir`, `--remote-control [name]`, `--bg`.

Quellen: code.claude.com/docs/en/{agent-view, hooks, statusline, monitoring-usage, agent-teams, cross-session-messaging, sessions} ·
docs.ntfy.sh · pushover.net · core.telegram.org/bots · github.com/ryoppippi/ccusage · langfuse.com · github.com/BloopAI/vibe-kanban ·
docs.devin.ai · linear.app/docs/project-graph · prokanban.org.
