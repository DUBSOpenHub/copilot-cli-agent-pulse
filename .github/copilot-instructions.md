# Copilot Instructions — Agent Pulse

## File Map

```
agent_pulse.py          — Main dashboard (single-file, ~1500 lines Python/Rich)
pyproject.toml          — Python packaging + console entry point
requirements.txt        — Python deps (rich>=13.0.0)
start.sh                — Launcher (auto-opens in a new terminal window)
site/index.html         — Showcase website (GitHub Pages)
experimental/ink/       — React/Ink TUI (experimental, separate stack)
```

## Non-Negotiables

1. **Single-file architecture** — `agent_pulse.py` is the entire app. Do not split into modules.
2. **Rich-only dependency** — No new Python deps without explicit approval.
3. **Every panel wrapped in try/except** — Broken panels must not crash the dashboard.
4. **DB lock resilience** — Always `sqlite3.connect(timeout=5)` and catch `OperationalError`.
5. **3-tier responsive** — Full ≥100w/40h, Compact ≥80w, Micro <80w/<24h.
6. **Python 3.10+ syntax** — `str | None`, `list[int]`, etc.
7. **CLI flag stability** — `--live`, `--history`, `--export`, `--compact`, `--refresh` are public API.

## PR Requirements

- `python agent_pulse.py --help` exits 0
- `python agent_pulse.py --export` produces valid JSON
- No new dependencies added without discussion
- No changes to experimental/ink/ in Python PRs (and vice versa)

## Prohibited

- No secrets, tokens, or credentials in code
- No telemetry or external network calls
- No removal of resilience wrappers or signal handlers
