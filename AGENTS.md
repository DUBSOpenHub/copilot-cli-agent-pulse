# AGENTS.md — Agent Pulse

> Operational guidance for AI agents working in this repository.

## What This Project Is

Agent Pulse is a real-time terminal dashboard for monitoring GitHub Copilot CLI sessions and agents. It's a single-file Python application (`agent_pulse.py`) that uses the Rich library for TUI rendering.

## File Map

| File | Purpose | Modify? |
|------|---------|---------|
| `agent_pulse.py` | Main dashboard application (all logic, rendering, data collection) | ✅ Primary target |
| `pyproject.toml` | Python packaging and metadata | Only for version/deps |
| `requirements.txt` | Python dependency list | Keep in sync with pyproject.toml |
| `start.sh` | Launcher — supports `--here` to run in current terminal, otherwise opens a new window | Rarely |
| `site/index.html` | Showcase website | For site updates only |
| `experimental/ink/` | React/Ink TUI (experimental) | Separate from main app |

## Non-Negotiables

1. **Single-file architecture**: `agent_pulse.py` is intentionally a single file. Do not refactor into a package unless explicitly asked.
2. **Rich-only dependency**: The Python app depends only on `rich>=13.0.0`. Do not add new dependencies without approval.
3. **Graceful degradation**: Every panel builder must be wrapped in try/except. A broken panel must never crash the dashboard.
4. **DB lock resilience**: The session-store.db may be locked by active Copilot CLI sessions. Always use `timeout=5` and handle `sqlite3.OperationalError`.
5. **Responsive layouts**: Support three tiers — full (≥100w, ≥40h), compact (≥80w), and micro (<80w or <24h). Never assume terminal size.
6. **Python 3.10+**: Uses `str | None`, `list[int]`, and other 3.10+ syntax. Do not downgrade.
7. **No breaking changes to CLI args**: The `--live`, `--history`, `--export`, `--compact`, `--refresh` flags are the public API.

## Color Palette

```python
C_NEON_GREEN = "#00ff87"
C_NEON_PINK  = "#ff00ff"
C_NEON_CYAN  = "#00f5ff"
C_NEON_RED   = "#ff5f5f"
C_BG_DARK    = "#050510"
```

Do not change the core palette. Extensions are fine.

## Testing

- Smoke test: `python agent_pulse.py --help` must exit 0
- Snapshot mode: `python agent_pulse.py` must render without errors
- Export mode: `python agent_pulse.py --export` must produce valid JSON

## Prohibited Actions

- Do not commit secrets, tokens, or credentials
- Do not add telemetry or analytics
- Do not modify the experimental/ink/ directory when working on the Python app
- Do not remove the SIGWINCH handler or any resilience wrapper
