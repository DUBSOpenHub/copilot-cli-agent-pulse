#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════╗
║  Agent Pulse — Real-time GitHub Copilot CLI Dashboard   ║
║  Cyberpunk · Responsive · Resilient · Info-dense        ║
╚══════════════════════════════════════════════════════════╝

Modes:
  python agent_pulse.py              → one-shot snapshot
  python agent_pulse.py --live       → persistent live dashboard
  python agent_pulse.py --history    → historical stats only
  python agent_pulse.py --export     → export JSON to stdout
  python agent_pulse.py --compact    → force compact mode
"""

import argparse
import datetime
import json
import math
import os
import re
import signal
import sqlite3
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Optional

# ─── Graceful Rich import (from C) ───────────────────────────────────────────
try:
    from rich import box
    from rich.align import Align
    from rich.columns import Columns
    from rich.console import Console, Group
    from rich.layout import Layout
    from rich.live import Live
    from rich.panel import Panel
    from rich.rule import Rule
    from rich.spinner import Spinner
    from rich.table import Table
    from rich.text import Text
except ImportError:
    print("╭─────────────────────────────────────────────────────╮")
    print("│  ⚠️  Missing required package: rich                 │")
    print("│                                                     │")
    print("│  Install with:                                      │")
    print("│    pip install rich                                 │")
    print("│                                                     │")
    print("│  Or use the requirements file:                      │")
    print("│    pip install -r requirements.txt                  │")
    print("╰─────────────────────────────────────────────────────╯")
    sys.exit(1)

# ─── Paths ────────────────────────────────────────────────────────────────────
COPILOT_DIR      = Path.home() / ".copilot"
SESSION_DB       = COPILOT_DIR / "session-store.db"
SESSION_STATE    = COPILOT_DIR / "session-state"
AGENTS_DIR       = COPILOT_DIR / "agents"
HISTORY_DIR      = Path.home() / ".copilot" / "agent-pulse"
HISTORY_FILE     = HISTORY_DIR / "history.json"
HISTORY_DIR.mkdir(parents=True, exist_ok=True)

# ─── Cyberpunk Neon Palette (from D) ─────────────────────────────────────────
C_NEON_GREEN = "#00ff87"
C_NEON_PINK  = "#ff00ff"
C_NEON_CYAN  = "#00f5ff"
C_NEON_RED   = "#ff5f5f"
C_BG_DARK    = "#050510"

C_ACCENT    = C_NEON_CYAN
C_GOOD      = C_NEON_GREEN
C_WARN      = "#ffd75f"
C_HOT       = C_NEON_RED
C_MUTED     = "#6c6f93"
C_HEADER    = f"bold {C_NEON_CYAN}"
C_LABEL     = "bold white"
C_DIM       = "dim #a0a0c0"

# Agent-type badge colours
AGENT_COLORS = {
    "general-purpose":      (f"bold {C_NEON_GREEN}",   "◉"),
    "explore":              (f"bold {C_NEON_CYAN}",    "⚡"),
    "task":                 ("bold #ffd75f",            "⚙"),
    "code-review":          (f"bold {C_NEON_PINK}",    "🔍"),
    "havoc-hackathon":      (f"bold {C_NEON_RED}",     "🏟"),
    "hive1k":               ("bold #ffd75f",            "🐝"),
    "swarm-command":        (f"bold {C_NEON_CYAN}",    "🌊"),
    "stampede-agent":       ("bold #ff8700",            "🐎"),
    "dark-factory":         ("bold #8a8a8a",            "🏭"),
    "dispatch-worker":      ("bold #5f87d7",            "📦"),
    "ai-edge":              ("bold #5f87ff",            "🔮"),
    "security-audit":       (f"bold {C_NEON_RED}",     "🛡"),
    "full-sweep":           ("bold white",              "🔭"),
    "octoscanner":          ("bold #00af5f",            "🐙"),
    "repo-detective":       ("bold #d7af5f",            "🔎"),
    "compliance-inspector": ("bold #ffd700",            "⚖"),
}
DEFAULT_AGENT_COLOR = ("bold white", "●")

# ─── ASCII Art Banner ─────────────────────────────────────────────────────────
BANNER_ART = r"""
    ___   ___  ___ _  _ _____   ___  _   _ _    ___ ___
   /   \ / __|| __| \| |_   _| | _ \| | | | |  / __| __|
   | - || (_ || _|| .` | | |   |  _/| |_| | |__\__ \ _|
   |_|_| \___||___|_|\_| |_|   |_|   \___/|____|___/___|
"""

BANNER_SUBTITLE = "Agent Dashboard for the Copilot CLI"

BANNER_COMPACT = "  ⚡ Agent Pulse  ·  Agent Dashboard for the Copilot CLI"

# ─── Dashboard start time (from A — for uptime tracking) ─────────────────────
_DASHBOARD_START = datetime.datetime.now()

# ─── Peak concurrent tracking (from A — in-memory for live mode) ─────────────
_peak_concurrent_sessions = 0
_peak_concurrent_procs = 0
_last_agent_launched_ts: str | None = None

# ─── Heartbeat animation frames (from A) ─────────────────────────────────────
HEARTBEAT_FRAMES = ["💗", "💖", "💗", "💓", "❤️ ", "💓", "💗", "💖"]
HEARTBEAT_BRAILLE = ["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]

# ─── Pulse wave animation (from C) ───────────────────────────────────────────
PULSE_WAVE_CHARS = "▁▂▃▄▅▆▇█▇▆▅▄▃▂"

# ─── Spark / bar characters ──────────────────────────────────────────────────
SPARK_CHARS = " ▁▂▃▄▅▆▇█"

# ─── Heatmap blocks (from D) ─────────────────────────────────────────────────
HEATMAP_BLOCKS = " ░▒▓█"

# ─── SIGWINCH signal handler for terminal resize (from E) ────────────────────
_terminal_resized = False

def _sigwinch_handler(signum, frame):
    global _terminal_resized
    _terminal_resized = True

if hasattr(signal, 'SIGWINCH'):
    signal.signal(signal.SIGWINCH, _sigwinch_handler)

def check_terminal_resized() -> bool:
    global _terminal_resized
    if _terminal_resized:
        _terminal_resized = False
        return True
    return False


# ─── Terminal dimension helpers (from A — 3-tier adaptive layout) ─────────────

def _get_term_size() -> tuple[int, int]:
    try:
        c = Console()
        return c.size.width, c.size.height
    except Exception:
        return 80, 24

def _is_compact(height: int) -> bool:
    return height < 40

def _is_narrow(width: int) -> bool:
    return width < 100

def _is_tiny(width: int, height: int) -> bool:
    return width < 80 or height < 24


# ─── Gradient helpers (from B — green→yellow→red bar charts) ─────────────────

def _clamp01(x: float) -> float:
    return 0.0 if x < 0 else 1.0 if x > 1 else x

def _rgb(r: int, g: int, b: int) -> str:
    return f"rgb({r},{g},{b})"

def _lerp(a: int, b: int, t: float) -> int:
    return int(round(a + (b - a) * t))

def _heat_rgb(t: float) -> tuple[int, int, int]:
    """Green → Yellow → Red heat scale for t in [0,1]."""
    t = _clamp01(t)
    if t <= 0.5:
        u = t / 0.5
        return (_lerp(0, 255, u), 255, 0)
    u = (t - 0.5) / 0.5
    return (255, _lerp(255, 40, u), 0)


# ─── Contextual number styling (from E) ──────────────────────────────────────

def style_number(value: int, context: str = "default") -> Text:
    """0=dim, low=cyan, medium=yellow, high=green, extreme=red."""
    if value == 0:
        return Text(str(value), style="dim grey50")
    thresholds = {
        "sessions": (5, 20, 50, 100),
        "agents":   (10, 50, 100, 200),
        "turns":    (50, 200, 500, 1000),
        "procs":    (1, 3, 5, 10),
        "default":  (5, 20, 50, 100),
    }
    low, med, high, extreme = thresholds.get(context, thresholds["default"])
    if value >= extreme:
        return Text(str(value), style=f"bold {C_NEON_RED}")
    elif value >= high:
        return Text(str(value), style=f"bold {C_NEON_GREEN}")
    elif value >= med:
        return Text(str(value), style=C_WARN)
    elif value >= low:
        return Text(str(value), style=C_NEON_CYAN)
    else:
        return Text(str(value), style=f"dim {C_NEON_CYAN}")


# ─── Last scan delta (from E) ────────────────────────────────────────────────

def format_time_delta(collected_at: str) -> str:
    try:
        collected = datetime.datetime.fromisoformat(collected_at)
        delta = (datetime.datetime.now() - collected).total_seconds()
        if delta < 60:
            return f"{int(delta)}s ago"
        elif delta < 3600:
            return f"{int(delta // 60)}m ago"
        return f"{int(delta // 3600)}h ago"
    except Exception:
        return "just now"


# ─── Bar chart helpers ────────────────────────────────────────────────────────

def spark(values: list[int], width: int = 12) -> str:
    """Sparkline from a list of integers."""
    if not values or max(values) == 0:
        return "·" * width
    mx = max(values)
    tail = values[-width:]
    padded = [0] * (width - len(tail)) + tail
    scaled = [int(v / mx * 8) for v in padded]
    return "".join(SPARK_CHARS[s] for s in scaled)


def spark_with_trend(values: list[int], width: int = 12) -> tuple[str, str]:
    """Sparkline + trend arrow ↑↓→ (from A)."""
    sp = spark(values, width)
    if len(values) < 2:
        return sp, "→"
    recent = values[-3:] if len(values) >= 3 else values
    older = values[-6:-3] if len(values) >= 6 else values[:len(values)//2] or [0]
    avg_recent = sum(recent) / len(recent)
    avg_older = sum(older) / len(older) if older else 0
    if avg_recent > avg_older * 1.2:
        return sp, "↑"
    elif avg_recent < avg_older * 0.8:
        return sp, "↓"
    return sp, "→"


def bar_chart_gradient(value: int, maximum: int, width: int = 20) -> Text:
    """Gradient-filled bar chart green→yellow→red (from B)."""
    maximum = max(maximum, 1)
    filled = max(0, min(width, int((value / maximum) * width)))
    t = Text()
    for i in range(width):
        if i < filled:
            heat_t = 0.0 if width <= 1 else i / (width - 1)
            r, g, b = _heat_rgb(heat_t)
            t.append("█", style=_rgb(r, g, b))
        else:
            t.append("░", style="#303050")
    t.append(f"  {value}", style=C_LABEL)
    return t


def bar_chart(value: int, maximum: int, width: int = 20, color: str = C_ACCENT) -> Text:
    """Simple colored bar chart."""
    if maximum == 0:
        filled = 0
    else:
        filled = max(0, min(width, int(value / maximum * width)))
    bar = "█" * filled + "░" * (width - filled)
    t = Text()
    t.append(bar, style=color)
    t.append(f"  {value}", style=C_LABEL)
    return t


def gradient_share_bar(pct: float, width: int = 20) -> Text:
    """Gradient share bar for agent breakdown (from B)."""
    pct = _clamp01(pct)
    filled = int(pct * width)
    t = Text()
    for i in range(width):
        if i < filled:
            heat_t = 0.0 if width <= 1 else i / (width - 1)
            r, g, b = _heat_rgb(heat_t)
            t.append("█", style=_rgb(r, g, b))
        else:
            t.append("░", style="#303050")
    return t


def pulse_wave(offset: int = 0, width: int = 40) -> str:
    """Scrolling sine wave animation (from C)."""
    wave = ""
    for i in range(width):
        idx = (i + offset) % len(PULSE_WAVE_CHARS)
        wave += PULSE_WAVE_CHARS[idx]
    return wave


def activity_heatmap(hourly_counts: list[int]) -> Text:
    """24-hour activity heatmap ░▒▓█ (from D)."""
    text = Text()
    if not hourly_counts:
        text.append(" " * 24, style=C_MUTED)
        return text
    mx = max(hourly_counts) or 1
    for v in hourly_counts[-24:]:
        if v <= 0:
            ch = " "
            style = C_MUTED
        else:
            level = max(1, min(len(HEATMAP_BLOCKS) - 1, int(v / mx * (len(HEATMAP_BLOCKS) - 1)) or 1))
            ch = HEATMAP_BLOCKS[level]
            style = C_NEON_PINK if level >= len(HEATMAP_BLOCKS) - 2 else C_NEON_CYAN
        text.append(ch, style=style)
    return text


def make_stacked_bar(agents: dict[str, int], width: int = 40) -> Text:
    """Horizontal stacked bar for agent type distribution (from E)."""
    total = sum(agents.values())
    if total == 0:
        return Text("░" * width, style="dim grey50")
    bar = Text()
    remaining_width = width
    sorted_agents = sorted(agents.items(), key=lambda x: -x[1])
    for i, (name, count) in enumerate(sorted_agents):
        if remaining_width <= 0:
            break
        color, icon = AGENT_COLORS.get(name, DEFAULT_AGENT_COLOR)
        segment_width = max(1, int(count / total * width))
        if i == len(sorted_agents) - 1:
            segment_width = remaining_width
        segment_width = min(segment_width, remaining_width)
        bar.append("█" * segment_width, style=color.replace("bold ", ""))
        remaining_width -= segment_width
    return bar


def format_uptime(start: datetime.datetime) -> str:
    """Dashboard uptime as compact string (from A)."""
    delta = datetime.datetime.now() - start
    total_secs = int(delta.total_seconds())
    if total_secs < 60:
        return f"{total_secs}s"
    mins = total_secs // 60
    secs = total_secs % 60
    if mins < 60:
        return f"{mins}m{secs:02d}s"
    hrs = mins // 60
    mins = mins % 60
    return f"{hrs}h{mins:02d}m"


def activity_status_dot(stats: dict) -> str:
    active_sessions = len(stats.get("active_sessions", []))
    active_procs = len(stats.get("active_procs", []))
    if active_sessions > 0 or active_procs > 0:
        return "🟢"
    elif stats.get("today_sessions", 0) > 0:
        return "🟡"
    return "🔴"


def _is_active(stats: dict) -> bool:
    """True if agents are active (from B)."""
    return bool(stats.get("active_sessions") or stats.get("active_procs"))


def _border_style(stats: dict) -> str:
    """Dynamic border: green when active, cyan when idle (from B)."""
    return f"bold {C_NEON_GREEN}" if _is_active(stats) else C_NEON_CYAN


# ─── Data Collection ──────────────────────────────────────────────────────────

def get_active_copilot_procs() -> list[dict]:
    try:
        result = subprocess.run(["ps", "aux"], capture_output=True, text=True, timeout=5)
        procs = []
        for line in result.stdout.splitlines():
            if "copilot-cli" in line.lower() or ("/copilot" in line and "grep" not in line):
                parts = line.split(None, 10)
                if len(parts) >= 2:
                    try:
                        pid = int(parts[1])
                    except ValueError:
                        continue
                    cpu = parts[2] if len(parts) > 2 else "?"
                    mem = parts[3] if len(parts) > 3 else "?"
                    cmd = parts[-1][:60] if len(parts) > 10 else ""
                    procs.append({"pid": pid, "cpu": cpu, "mem": mem, "cmd": cmd})
        return procs
    except Exception:
        return []


def get_active_sessions() -> list[dict]:
    active = []
    if not SESSION_STATE.exists():
        return active
    for sess_dir in SESSION_STATE.iterdir():
        if not sess_dir.is_dir():
            continue
        locks = list(sess_dir.glob("inuse.*.lock"))
        if locks:
            lock = locks[0]
            pid_str = lock.stem.split(".")[-1]
            try:
                pid = int(pid_str)
            except ValueError:
                pid = None
            summary = _get_session_summary(sess_dir)
            mtime = datetime.datetime.fromtimestamp(sess_dir.stat().st_mtime)
            active.append({
                "id": sess_dir.name[:8],
                "full_id": sess_dir.name,
                "pid": pid,
                "summary": summary,
                "mtime": mtime,
            })
    return sorted(active, key=lambda x: x["mtime"], reverse=True)


ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

def _strip_ansi(text: str) -> str:
    return ANSI_ESCAPE.sub("", text)


def _get_session_summary(sess_dir: Path) -> str:
    ws = sess_dir / "workspace.yaml"
    if ws.exists():
        try:
            content = ws.read_text()
            for line in content.splitlines():
                if "summary" in line.lower() or "title" in line.lower():
                    val = line.split(":", 1)[-1].strip().strip('"').strip("'")
                    if val:
                        return val[:60]
        except Exception:
            pass
    events_file = sess_dir / "events.jsonl"
    if events_file.exists():
        try:
            with open(events_file) as f:
                for line in f:
                    e = json.loads(line)
                    if e.get("type") == "user.message":
                        msg = _strip_ansi(e.get("data", {}).get("content", ""))[:60]
                        if msg:
                            return msg
        except Exception:
            pass
    return "Active session"


def get_recent_agents(hours: int = 24) -> dict[str, int]:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    counts: dict[str, int] = defaultdict(int)
    if not SESSION_STATE.exists():
        return counts
    for sess_dir in SESSION_STATE.iterdir():
        if not sess_dir.is_dir():
            continue
        ef = sess_dir / "events.jsonl"
        if not ef.exists():
            continue
        try:
            mtime = datetime.datetime.fromtimestamp(ef.stat().st_mtime, tz=datetime.timezone.utc)
            if mtime < since - datetime.timedelta(hours=1):
                continue
            with open(ef) as f:
                for line in f:
                    try:
                        ev = json.loads(line)
                        if ev.get("type") != "subagent.started":
                            continue
                        ts_str = ev.get("timestamp", "")
                        if ts_str:
                            ts = datetime.datetime.fromisoformat(ts_str.replace("Z", "+00:00"))
                            if ts < since:
                                continue
                        name = ev.get("data", {}).get("agentName", "unknown")
                        counts[name] += 1
                    except Exception:
                        pass
        except Exception:
            pass
    return dict(counts)


def get_skill_invocations(hours: int = 24) -> dict[str, int]:
    since = datetime.datetime.now(datetime.timezone.utc) - datetime.timedelta(hours=hours)
    counts: dict[str, int] = defaultdict(int)
    if not SESSION_STATE.exists():
        return counts
    for sess_dir in SESSION_STATE.iterdir():
        if not sess_dir.is_dir():
            continue
        ef = sess_dir / "events.jsonl"
        if not ef.exists():
            continue
        try:
            mtime = datetime.datetime.fromtimestamp(ef.stat().st_mtime, tz=datetime.timezone.utc)
            if mtime < since - datetime.timedelta(hours=1):
                continue
            with open(ef) as f:
                for line in f:
                    try:
                        ev = json.loads(line)
                        if ev.get("type") != "skill.invoked":
                            continue
                        name = ev.get("data", {}).get("skillName", "unknown")
                        counts[name] += 1
                    except Exception:
                        pass
        except Exception:
            pass
    return dict(counts)


def get_db_stats() -> dict[str, Any]:
    """Query session-store.db with sqlite3.OperationalError handling (from E)."""
    stats = {
        "total_sessions": 0, "total_turns": 0,
        "today_sessions": 0, "today_turns": 0,
        "week_sessions": 0, "month_sessions": 0,
        "daily_sessions": [], "recent_sessions": [],
        "peak_concurrent": 0,
        "hourly_sessions_24h": [],
        "db_locked": False,
    }
    if not SESSION_DB.exists():
        return stats
    try:
        conn = sqlite3.connect(str(SESSION_DB), timeout=5)
        conn.row_factory = sqlite3.Row
        now = datetime.datetime.now(datetime.timezone.utc)
        today = now.strftime("%Y-%m-%d")
        week_ago = (now - datetime.timedelta(days=7)).strftime("%Y-%m-%dT%H:%M:%S")
        month_ago = (now - datetime.timedelta(days=30)).strftime("%Y-%m-%dT%H:%M:%S")

        stats["total_sessions"] = conn.execute("SELECT COUNT(*) FROM sessions").fetchone()[0]
        stats["total_turns"] = conn.execute("SELECT COUNT(*) FROM turns").fetchone()[0]
        stats["today_sessions"] = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE created_at LIKE ?", (f"{today}%",)
        ).fetchone()[0]
        stats["today_turns"] = conn.execute(
            "SELECT COUNT(*) FROM turns WHERE timestamp LIKE ?", (f"{today}%",)
        ).fetchone()[0]
        stats["week_sessions"] = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE created_at >= ?", (week_ago,)
        ).fetchone()[0]
        stats["month_sessions"] = conn.execute(
            "SELECT COUNT(*) FROM sessions WHERE created_at >= ?", (month_ago,)
        ).fetchone()[0]

        # Daily breakdown — last 14 days
        daily = []
        for i in range(13, -1, -1):
            d = (now - datetime.timedelta(days=i)).strftime("%Y-%m-%d")
            c = conn.execute(
                "SELECT COUNT(*) FROM sessions WHERE created_at LIKE ?", (f"{d}%",)
            ).fetchone()[0]
            daily.append({"date": d, "count": c})
        stats["daily_sessions"] = daily

        # Peak concurrent estimate (from A)
        try:
            rows = conn.execute(
                "SELECT substr(created_at, 1, 13) AS hour_bucket, COUNT(*) AS cnt "
                "FROM sessions WHERE created_at LIKE ? GROUP BY hour_bucket ORDER BY cnt DESC LIMIT 1",
                (f"{today}%",)
            ).fetchone()
            if rows:
                stats["peak_concurrent"] = rows[1]
        except Exception:
            pass

        # Hourly activity for last 24h — for heatmap (from D)
        try:
            cutoff_24h = (now - datetime.timedelta(hours=24)).strftime("%Y-%m-%dT%H:%M:%S")
            rows = conn.execute(
                "SELECT substr(created_at, 1, 13) AS hour, COUNT(*) AS c "
                "FROM sessions WHERE created_at >= ? GROUP BY hour",
                (cutoff_24h,),
            ).fetchall()
            by_hour = {r["hour"]: r["c"] for r in rows}
            hours_24: list[dict[str, Any]] = []
            for i in range(23, -1, -1):
                h = (now - datetime.timedelta(hours=i)).strftime("%Y-%m-%dT%H")
                hours_24.append({"hour": h, "count": by_hour.get(h, 0)})
            stats["hourly_sessions_24h"] = hours_24
        except Exception:
            pass

        # Recent sessions
        rows = conn.execute(
            "SELECT id, summary, created_at, cwd FROM sessions "
            "ORDER BY created_at DESC LIMIT 10"
        ).fetchall()
        stats["recent_sessions"] = [dict(r) for r in rows]
        conn.close()

    except sqlite3.OperationalError as e:
        if "locked" in str(e).lower():
            stats["db_locked"] = True
        stats["error"] = str(e)
    except Exception as e:
        stats["error"] = str(e)
    return stats


def count_all_subagents() -> int:
    total = 0
    if not SESSION_STATE.exists():
        return total
    for sess_dir in SESSION_STATE.iterdir():
        if not sess_dir.is_dir():
            continue
        ef = sess_dir / "events.jsonl"
        if not ef.exists():
            continue
        try:
            with open(ef) as f:
                for line in f:
                    try:
                        ev = json.loads(line)
                        if ev.get("type") == "subagent.started":
                            total += 1
                    except Exception:
                        pass
        except Exception:
            pass
    return total


def get_last_agent_launched() -> str | None:
    latest_ts: str | None = None
    if not SESSION_STATE.exists():
        return None
    # Sort session dirs by modification time (newest first) and limit scan
    try:
        sess_dirs = sorted(
            (d for d in SESSION_STATE.iterdir() if d.is_dir()),
            key=lambda d: d.stat().st_mtime,
            reverse=True,
        )
    except Exception:
        return None
    for sess_dir in sess_dirs[:20]:  # Only check 20 most recent sessions
        ef = sess_dir / "events.jsonl"
        if not ef.exists():
            continue
        try:
            # Read file in reverse to find latest event faster
            lines = ef.read_text().splitlines()
            for line in reversed(lines):
                try:
                    ev = json.loads(line)
                    if ev.get("type") == "subagent.started":
                        ts = ev.get("timestamp", "")
                        if ts and (latest_ts is None or ts > latest_ts):
                            latest_ts = ts
                        break  # Found latest in this file, move on
                except Exception:
                    pass
        except Exception:
            pass
        if latest_ts:
            break  # Found one — most recent session wins
    return latest_ts


def get_installed_agents() -> list[str]:
    if not AGENTS_DIR.exists():
        return []
    return [
        p.name.replace(".agent.md", "")
        for p in sorted(AGENTS_DIR.glob("*.agent.md"))
    ]


def collect_all_stats() -> dict[str, Any]:
    """Master data collection — merges features from A/D/E."""
    global _peak_concurrent_sessions, _peak_concurrent_procs, _last_agent_launched_ts

    try:
        db = get_db_stats()
    except sqlite3.OperationalError:
        db = {"total_sessions": 0, "total_turns": 0, "today_sessions": 0,
              "today_turns": 0, "week_sessions": 0, "month_sessions": 0,
              "daily_sessions": [], "recent_sessions": [], "peak_concurrent": 0,
              "hourly_sessions_24h": [], "db_locked": True, "error": "DB locked"}

    procs  = get_active_copilot_procs()
    active = get_active_sessions()
    agents = get_recent_agents(24)
    skills = get_skill_invocations(24)
    inst   = get_installed_agents()

    total_agents_24h = sum(agents.values())

    # Peak concurrent (from A)
    current_sessions = len(active)
    current_procs = len(procs)
    _peak_concurrent_sessions = max(_peak_concurrent_sessions, current_sessions)
    _peak_concurrent_procs = max(_peak_concurrent_procs, current_procs)

    # Last agent launched (from A)
    last_agent_ts = get_last_agent_launched()
    if last_agent_ts:
        _last_agent_launched_ts = last_agent_ts

    # Agent velocity (from D)
    agent_velocity = total_agents_24h / 24.0 if total_agents_24h else 0.0

    # History persistence
    history = _load_history()
    today = datetime.datetime.now().strftime("%Y-%m-%d")
    history.setdefault(today, {"sessions": 0, "agents": 0, "turns": 0})
    history[today]["sessions"] = db["today_sessions"]
    history[today]["agents"] = total_agents_24h
    history[today]["turns"] = db["today_turns"]
    _save_history(history)

    now = datetime.datetime.now()
    days_14 = [(now - datetime.timedelta(days=i)).strftime("%Y-%m-%d") for i in range(13, -1, -1)]
    daily_agents = [history.get(d, {}).get("agents", 0) for d in days_14]

    return {
        "collected_at":              datetime.datetime.now().isoformat(timespec="seconds"),
        "active_procs":              procs,
        "active_sessions":           active,
        "total_sessions":            db["total_sessions"],
        "total_turns":               db["total_turns"],
        "today_sessions":            db["today_sessions"],
        "today_turns":               db["today_turns"],
        "week_sessions":             db["week_sessions"],
        "month_sessions":            db["month_sessions"],
        "daily_sessions":            db.get("daily_sessions", []),
        "daily_agents":              [{"date": d, "count": c} for d, c in zip(days_14, daily_agents)],
        "agents_24h":                agents,
        "skills_24h":                skills,
        "installed_agents":          inst,
        "total_subagents_24h":       total_agents_24h,
        "history":                   history,
        "peak_concurrent_sessions":  _peak_concurrent_sessions,
        "peak_concurrent_procs":     _peak_concurrent_procs,
        "peak_concurrent_hour":      db.get("peak_concurrent", 0),
        "last_agent_launched":       _last_agent_launched_ts,
        "dashboard_uptime":          format_uptime(_DASHBOARD_START),
        "agent_velocity_per_hour":   agent_velocity,
        "hourly_sessions_24h":       db.get("hourly_sessions_24h", []),
        "db_locked":                 db.get("db_locked", False),
    }


# ─── History persistence ──────────────────────────────────────────────────────

def _load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text())
        except Exception:
            pass
    return {}

def _save_history(data: dict) -> None:
    try:
        HISTORY_FILE.write_text(json.dumps(data, indent=2))
    except Exception:
        pass


# ─── Rich rendering helpers ──────────────────────────────────────────────────

def _agent_badge(name: str) -> Text:
    color, icon = AGENT_COLORS.get(name, DEFAULT_AGENT_COLOR)
    t = Text()
    t.append(f" {icon} {name} ", style=f"{color} on grey15")
    return t


# ─── Panel builders — ALL wrapped in try/except (from E) ─────────────────────

def make_banner(tick: int = 0, stats: dict | None = None, force_compact: bool = False) -> Panel:
    """Banner with C's Unicode art, A's heartbeat, C's pulse wave, B's dynamic border."""
    try:
        term_w, term_h = _get_term_size()
        status_dot = activity_status_dot(stats) if stats else "🟡"
        heartbeat = HEARTBEAT_FRAMES[tick % len(HEARTBEAT_FRAMES)]
        uptime = stats.get("dashboard_uptime", "0s") if stats else "0s"
        now_str = datetime.datetime.now().strftime("%H:%M:%S")
        date_str = datetime.datetime.now().strftime("%a %d %b %Y")
        active = _is_active(stats) if stats else False
        border = f"bold {C_NEON_GREEN}" if active else f"bold {C_NEON_CYAN}"

        if force_compact or _is_compact(term_h) or _is_narrow(term_w):
            wave = pulse_wave(offset=tick, width=20)
            line = Text(justify="center")
            line.append(f" {heartbeat} ", style=f"bold {C_NEON_PINK}")
            line.append("Agent Pulse", style=f"bold {C_NEON_CYAN}")
            line.append(f"  {status_dot} ", style="white")
            line.append(f"  {date_str}  {now_str}", style=f"dim {C_NEON_CYAN}")
            line.append(f"  ⏱ {uptime}", style=C_DIM)
            wave_text = Text(wave, style=C_NEON_CYAN, justify="center")
            content = Text.assemble(line, "\n", wave_text)
            return Panel(Align.center(content), border_style=border, box=box.HEAVY, padding=(0, 1))

        # Full banner with original ASCII art
        banner_text = Text(BANNER_ART, style="bold white", justify="center")
        subtitle_text = Text(BANNER_SUBTITLE, style=f"bold {C_NEON_CYAN}", justify="center")
        wave = pulse_wave(offset=tick, width=50)
        wave_text = Text(wave, style=C_NEON_CYAN, justify="center")

        title_line = Text(justify="center")
        title_line.append(f" {heartbeat} ", style=f"bold {C_NEON_PINK}")
        title_line.append("powered by GitHub Copilot CLI", style=f"dim {C_NEON_CYAN}")

        info_line = Text(justify="center")
        info_line.append(f" {status_dot} ", style="white")
        info_line.append("LIVE", style=f"bold {C_NEON_GREEN}")
        info_line.append(f"  ·  {date_str}  {now_str}", style=f"dim {C_NEON_CYAN}")
        info_line.append(f"  ·  ⏱ uptime {uptime}", style=C_DIM)

        content = Group(
            Align.center(banner_text),
            Align.center(subtitle_text),
            Text(),
            Align.center(wave_text),
            Align.center(title_line),
            Align.center(info_line),
        )
        return Panel(content, border_style=border, box=box.HEAVY, padding=(0, 2))
    except Exception:
        return Panel(Text("⚡ Agent Pulse", style=f"bold {C_NEON_CYAN}"), border_style=C_NEON_CYAN, box=box.HEAVY)


def make_live_stats(stats: dict, tick: int = 0) -> Panel:
    """Key metrics with contextual coloring, peak concurrent, velocity, heatmap."""
    try:
        term_w, term_h = _get_term_size()
        narrow = _is_narrow(term_w)
        compact = _is_compact(term_h)
        border = _border_style(stats)
        last_scan = format_time_delta(stats["collected_at"])

        t = Table(show_header=False, box=None, padding=(0, 1), expand=True)
        t.add_column("Label", style=C_MUTED, min_width=18)
        t.add_column("Value", style=C_LABEL, justify="right", min_width=6)
        if not narrow:
            t.add_column("Chart", min_width=16)

        procs = stats["active_procs"]
        sessions = stats["active_sessions"]

        def row(label, value, chart_val=0, mx=1, ctx="default"):
            styled_val = style_number(value, ctx)
            if narrow:
                t.add_row(label, styled_val)
            else:
                t.add_row(label, styled_val, bar_chart_gradient(chart_val, mx, width=14))

        # Header
        if narrow:
            t.add_row(Text("◉ Sessions", style=C_HEADER), style_number(len(sessions), "sessions"))
            t.add_row(Text("◉ Processes", style=C_HEADER), style_number(len(procs), "procs"))
            t.add_row(Text("◉ Agents 24h", style=C_HEADER), style_number(stats["total_subagents_24h"], "agents"))
        else:
            t.add_row(Text("◉ Sessions", style=C_HEADER), style_number(len(sessions), "sessions"), Text(f"scanned {last_scan}", style="dim grey50"))
            t.add_row(Text("◉ Processes", style=C_HEADER), style_number(len(procs), "procs"), Text(""))
            t.add_row(Text("◉ Agents 24h", style=C_HEADER), style_number(stats["total_subagents_24h"], "agents"), Text(""))

        if not compact:
            if narrow:
                t.add_row("", "")
            else:
                t.add_row("", "", Text(""))
            row("  Today", stats["today_sessions"], stats["today_sessions"], max(stats["week_sessions"] // 7, 1), "sessions")
            row("  This Week", stats["week_sessions"], stats["week_sessions"], stats["month_sessions"] or 1, "sessions")
            row("  This Month", stats["month_sessions"], stats["month_sessions"], stats["total_sessions"] or 1, "sessions")
            row("  All-time", stats["total_sessions"], stats["total_sessions"], stats["total_sessions"] or 1, "sessions")

        # Extra metrics separator
        if narrow:
            t.add_row("", "")
        else:
            t.add_row("", "", Text(""))

        # Peak concurrent (from A)
        peak_sess = stats.get("peak_concurrent_sessions", 0)
        peak_hour = stats.get("peak_concurrent_hour", 0)
        peak_val = max(peak_sess, peak_hour)
        if narrow:
            t.add_row(Text("⚡ Peak concurrent", style=C_WARN), style_number(peak_val, "sessions"))
        else:
            t.add_row(Text("⚡ Peak concurrent", style=C_WARN), style_number(peak_val, "sessions"), Text(""))

        # Agent velocity (from D)
        velocity = stats.get("agent_velocity_per_hour", 0.0)
        vel_text = Text(f"{velocity:.1f}/h", style=C_NEON_CYAN)
        if narrow:
            t.add_row(Text("🚀 Agent velocity", style=C_NEON_CYAN), vel_text)
        else:
            t.add_row(Text("🚀 Agent velocity", style=C_NEON_CYAN), vel_text, Text(""))

        # Last agent launched (from A/E)
        last_agent = stats.get("last_agent_launched")
        if last_agent:
            try:
                ts = datetime.datetime.fromisoformat(last_agent.replace("Z", "+00:00"))
                age = datetime.datetime.now(datetime.timezone.utc) - ts
                if age.total_seconds() < 60:
                    ago = f"{int(age.total_seconds())}s ago"
                elif age.total_seconds() < 3600:
                    ago = f"{int(age.total_seconds() // 60)}m ago"
                else:
                    ago = f"{int(age.total_seconds() // 3600)}h ago"
                agent_ts_text = Text(ago, style=C_NEON_CYAN)
            except Exception:
                agent_ts_text = Text(last_agent[:19], style=C_MUTED)
        else:
            agent_ts_text = Text("—", style=C_MUTED)

        if narrow:
            t.add_row(Text("🕐 Last agent", style=C_NEON_CYAN), agent_ts_text)
        else:
            t.add_row(Text("🕐 Last agent", style=C_NEON_CYAN), agent_ts_text, Text(""))

        # 24-hour activity heatmap (from D) — only if not narrow
        if not narrow and not compact:
            hourly = stats.get("hourly_sessions_24h") or []
            counts = [h["count"] for h in hourly]
            if counts:
                t.add_row(Text("📊 24h heatmap", style=C_NEON_PINK), Text(""), activity_heatmap(counts))

        # DB lock warning (from C/E)
        if stats.get("db_locked"):
            warning = Text("  ⚠ DB locked — some stats unavailable", style=C_WARN)
            body = Group(t, warning)
        else:
            body = t

        return Panel(body, title=f"[bold {C_NEON_CYAN}]● LIVE METRICS[/]", border_style=border, box=box.ROUNDED)
    except Exception as e:
        return Panel(Text(f"Error building stats: {e}", style=C_NEON_RED), title=f"[bold {C_NEON_RED}]● ERROR[/]", border_style=C_NEON_RED, box=box.ROUNDED)


def make_active_sessions(stats: dict, tick: int = 0) -> Panel:
    """Active sessions panel with try/except safety."""
    try:
        term_w, term_h = _get_term_size()
        compact = _is_compact(term_h)
        sessions = stats["active_sessions"]
        border = _border_style(stats)

        t = Table(box=box.SIMPLE_HEAD, expand=True, show_lines=False)
        t.add_column("PID", style=C_MUTED, width=7)
        t.add_column("Session", style=C_NEON_CYAN, width=10)
        t.add_column("Summary", style="white", ratio=1)
        t.add_column("Since", style=C_MUTED, width=6)

        max_rows = 4 if compact else 8
        if not sessions:
            t.add_row(Text("—", style=C_MUTED), Text("no active sessions", style=C_MUTED), "", "")
        else:
            for s in sessions[:max_rows]:
                since = s["mtime"].strftime("%H:%M")
                summary_max = 40 if _is_narrow(term_w) else 55
                t.add_row(str(s["pid"] or "?"), s["id"], s["summary"][:summary_max], since)

        procs = stats["active_procs"]
        proc_text = Text()
        if procs:
            for p in procs[:3 if compact else 4]:
                proc_text.append(f"  PID {p['pid']}  CPU {p['cpu']}%  MEM {p['mem']}%\n", style=C_MUTED)
        else:
            proc_text.append("  no copilot processes found", style=C_MUTED)

        body = Group(t, Rule(style="#303050"), proc_text)
        return Panel(body, title=f"[bold {C_NEON_GREEN}]⚡ ACTIVE[/]", border_style=border, box=box.ROUNDED)
    except Exception as e:
        return Panel(Text(f"Error: {e}", style=C_NEON_RED), title=f"[bold {C_NEON_RED}]⚡ ERROR[/]", border_style=C_NEON_RED, box=box.ROUNDED)


def make_agent_breakdown(stats: dict, tick: int = 0) -> Panel:
    """Agent breakdown with stacked bar (from E) and gradient shares (from B)."""
    try:
        term_w, term_h = _get_term_size()
        compact = _is_compact(term_h)
        narrow = _is_narrow(term_w)
        agents = stats["agents_24h"]
        total = stats["total_subagents_24h"]
        border = _border_style(stats)

        # Stacked bar (from E)
        stacked = make_stacked_bar(agents, width=40 if not narrow else 24)
        bar_line = Text()
        bar_line.append("  Distribution: ", style=C_MUTED)
        bar_line.append_text(stacked)

        t = Table(box=box.SIMPLE_HEAD, expand=True)
        t.add_column("Agent Type", style="white", ratio=1)
        t.add_column("Count", style=C_LABEL, width=5, justify="right")
        if not narrow:
            t.add_column("Share", width=18)

        max_rows = 5 if compact else 10
        if not agents:
            if narrow:
                t.add_row(Text("No agents (24h)", style=C_MUTED), "")
            else:
                t.add_row(Text("No agents launched in last 24h", style=C_MUTED), "", "")
        else:
            for name, count in sorted(agents.items(), key=lambda x: -x[1])[:max_rows]:
                color, icon = AGENT_COLORS.get(name, DEFAULT_AGENT_COLOR)
                badge = Text()
                badge.append(f"{icon} {name}", style=color)
                pct = count / total if total else 0
                if narrow:
                    t.add_row(badge, style_number(count, "agents"))
                else:
                    t.add_row(badge, style_number(count, "agents"), gradient_share_bar(pct, width=16))

        # Skills
        skills = stats["skills_24h"]
        skill_text = Text()
        if skills:
            skill_text.append("  Skills: ", style=C_MUTED)
            for sname, cnt in sorted(skills.items(), key=lambda x: -x[1])[:4 if compact else 6]:
                skill_text.append(f" {sname}×{cnt}", style=C_NEON_CYAN)
        else:
            skill_text.append("  No skills (24h)", style=C_MUTED)

        body = Group(bar_line, Text(""), t, skill_text)
        return Panel(body, title=f"[bold {C_WARN}]⚙ AGENTS (24h) · {total}[/]", border_style=border, box=box.ROUNDED)
    except Exception as e:
        return Panel(Text(f"Error: {e}", style=C_NEON_RED), title=f"[bold {C_NEON_RED}]⚙ ERROR[/]", border_style=C_NEON_RED, box=box.ROUNDED)


def make_trends(stats: dict, tick: int = 0) -> Panel:
    """7-day trend with sparklines and trend arrows (from A)."""
    try:
        term_w, term_h = _get_term_size()
        compact = _is_compact(term_h)
        narrow = _is_narrow(term_w)
        border = _border_style(stats)

        daily_s = stats.get("daily_sessions", [])
        daily_a = stats.get("daily_agents", [])
        if not daily_s:
            daily_s = [{"date": datetime.datetime.now().strftime("%Y-%m-%d"), "count": 0}]
        if not daily_a:
            daily_a = [{"date": datetime.datetime.now().strftime("%Y-%m-%d"), "count": 0}]

        sess_vals = [d["count"] for d in daily_s]
        agent_vals = [d["count"] for d in daily_a]
        max_sess = max(sess_vals + [1])
        max_agent = max(agent_vals + [1])

        t = Table(box=None, show_header=True, padding=(0, 1), expand=True)
        t.add_column("Date", style=C_MUTED, width=12)
        t.add_column("Sess", style="white", width=5, justify="right")
        if not narrow:
            t.add_column("▾", min_width=16)
        t.add_column("Agnt", style="white", width=5, justify="right")
        if not narrow:
            t.add_column("▾", min_width=16)

        today = datetime.datetime.now().strftime("%Y-%m-%d")
        num_days = 5 if compact else 7

        for ds, da in zip(daily_s[-num_days:], daily_a[-num_days:]):
            is_today = ds["date"] == today
            date_style = f"bold {C_NEON_CYAN}" if is_today else C_MUTED
            suffix = " ◀" if is_today else ""
            if narrow:
                t.add_row(
                    Text(ds["date"][5:] + suffix, style=date_style),
                    style_number(ds["count"], "sessions"),
                    style_number(da["count"], "agents"),
                )
            else:
                t.add_row(
                    Text(ds["date"][5:] + suffix, style=date_style),
                    style_number(ds["count"], "sessions"),
                    bar_chart_gradient(ds["count"], max_sess, width=12),
                    style_number(da["count"], "agents"),
                    bar_chart_gradient(da["count"], max_agent, width=12),
                )

        # Sparkline with trend arrows (from A)
        if not narrow:
            sp_s, trend_s = spark_with_trend(sess_vals, 14)
            sp_a, trend_a = spark_with_trend(agent_vals, 14)
            sparkline = Text()
            sparkline.append(f"\n  sessions {trend_s} ", style=C_MUTED)
            sparkline.append(sp_s, style=C_NEON_CYAN)
            sparkline.append(f"  agents {trend_a} ", style=C_MUTED)
            sparkline.append(sp_a, style=C_WARN)
            body = Group(t, sparkline)
        else:
            body = Group(t)

        return Panel(body, title=f"[bold {C_NEON_PINK}]📈 TREND[/]", border_style=border, box=box.ROUNDED)
    except Exception as e:
        return Panel(Text(f"Error: {e}", style=C_NEON_RED), title=f"[bold {C_NEON_RED}]📈 ERROR[/]", border_style=C_NEON_RED, box=box.ROUNDED)


def make_installed_agents(stats: dict, tick: int = 0) -> Panel:
    """Installed agents grid."""
    try:
        term_w, _ = _get_term_size()
        agents = stats["installed_agents"]
        cols = 2 if _is_narrow(term_w) else 3
        border = _border_style(stats)

        t = Table(box=None, show_header=False, padding=(0, 1), expand=True)
        for _ in range(cols):
            t.add_column(ratio=1)

        row = []
        for name in agents:
            color, icon = AGENT_COLORS.get(name, DEFAULT_AGENT_COLOR)
            badge = Text()
            badge.append(f" {icon} {name}", style=color)
            row.append(badge)
            if len(row) == cols:
                t.add_row(*row)
                row = []
        if row:
            while len(row) < cols:
                row.append("")
            t.add_row(*row)

        return Panel(t, title=f"[bold {C_NEON_CYAN}]🤖 AGENTS · {len(agents)}[/]", border_style=border, box=box.ROUNDED)
    except Exception as e:
        return Panel(Text(f"Error: {e}", style=C_NEON_RED), title=f"[bold {C_NEON_RED}]🤖 ERROR[/]", border_style=C_NEON_RED, box=box.ROUNDED)


def make_micro_dashboard(stats: dict, tick: int) -> Panel:
    """Micro dashboard fallback for very tiny terminals (from D)."""
    try:
        active = len(stats["active_sessions"])
        agents_24h = stats["total_subagents_24h"]
        velocity = stats.get("agent_velocity_per_hour", 0.0)
        uptime = stats.get("dashboard_uptime", "")
        heartbeat = HEARTBEAT_FRAMES[tick % len(HEARTBEAT_FRAMES)]

        cards: list[Panel] = []
        metrics = [
            ("SESSIONS", str(active), C_NEON_GREEN if active else C_MUTED),
            ("AGENTS 24H", str(agents_24h), C_NEON_PINK if agents_24h else C_MUTED),
            ("VELOCITY", f"{velocity:.1f}/h", C_NEON_CYAN),
        ]
        for label, value, color in metrics:
            body = Text(justify="center")
            body.append(f"\n {value}\n", style=f"bold {color}")
            body.append(f" {label}\n", style=C_DIM)
            cards.append(Panel(Align.center(body), box=box.HEAVY, border_style=f"bold {color}", padding=(0, 2)))

        header = Align.center(Text(f"{heartbeat} MICRO PULSE  ·  UPTIME {uptime}", style=f"bold {C_NEON_PINK}"))
        group = Group(header, Columns(cards, expand=True, equal=True))
        return Panel(group, box=box.ROUNDED, border_style=f"bold {C_NEON_CYAN}")
    except Exception as e:
        return Panel(Text(f"Micro error: {e}", style=C_NEON_RED), border_style=C_NEON_RED)


def make_footer(tick: int = 0, refresh: int = 5) -> Text:
    """Footer with heartbeat, countdown timer (from C), scan indicator."""
    spinner_frames = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"
    spin = spinner_frames[tick % len(spinner_frames)]
    heartbeat = HEARTBEAT_BRAILLE[tick % len(HEARTBEAT_BRAILLE)]
    countdown = refresh - (tick % refresh) if refresh > 0 else 0
    t = Text(justify="center")
    t.append(f" {spin}{heartbeat} scanning  ", style=C_NEON_CYAN)
    t.append(f"  next in {countdown}s  ", style=C_MUTED)
    t.append("  Q quit  R refresh  H history  E export  ", style=C_MUTED)
    return t


# ─── Layout builder (RESPONSIVE — from A's 3-tier with D's micro) ────────────

def build_live_layout(stats: dict, tick: int, refresh: int = 5, force_compact: bool = False) -> Layout:
    """Build a responsive layout that adapts to terminal dimensions.

    3 tiers from A: tiny → compact → full, plus D's micro dashboard.
    All panel updates wrapped in try/except (from E).
    """
    term_w, term_h = _get_term_size()

    # Force compact if CLI flag set
    if force_compact:
        compact = True
        tiny = False
    else:
        compact = _is_compact(term_h)
        tiny = _is_tiny(term_w, term_h)

    layout = Layout()

    # D's micro dashboard for very tiny terminals
    if tiny and not force_compact:
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body", ratio=1),
            Layout(name="footer", size=1),
        )
        try:
            layout["header"].update(make_banner(tick, stats, force_compact=True))
        except Exception:
            layout["header"].update(Panel(Text("⚡ Agent Pulse", style=f"bold {C_NEON_CYAN}")))
        try:
            layout["body"].update(make_micro_dashboard(stats, tick))
        except Exception:
            layout["body"].update(make_live_stats(stats, tick))
        layout["footer"].update(make_footer(tick, refresh))
        return layout

    if compact:
        layout.split_column(
            Layout(name="header", size=4),
            Layout(name="top", ratio=2),
            Layout(name="mid", ratio=2),
            Layout(name="footer", size=1),
        )
        layout["top"].split_row(
            Layout(name="live_stats", ratio=2),
            Layout(name="sessions", ratio=3),
        )
        layout["mid"].split_row(
            Layout(name="agents", ratio=1),
            Layout(name="trends", ratio=1),
        )
        try:
            layout["header"].update(make_banner(tick, stats, force_compact=True))
        except Exception:
            layout["header"].update(Panel(Text("⚡ Agent Pulse", style=f"bold {C_NEON_CYAN}")))
        try:
            layout["live_stats"].update(make_live_stats(stats, tick))
        except Exception as e:
            layout["live_stats"].update(Panel(Text(f"Error: {e}", style=C_NEON_RED)))
        try:
            layout["sessions"].update(make_active_sessions(stats, tick))
        except Exception as e:
            layout["sessions"].update(Panel(Text(f"Error: {e}", style=C_NEON_RED)))
        try:
            layout["agents"].update(make_agent_breakdown(stats, tick))
        except Exception as e:
            layout["agents"].update(Panel(Text(f"Error: {e}", style=C_NEON_RED)))
        try:
            layout["trends"].update(make_trends(stats, tick))
        except Exception as e:
            layout["trends"].update(Panel(Text(f"Error: {e}", style=C_NEON_RED)))
        layout["footer"].update(make_footer(tick, refresh))
        return layout

    # Full layout
    layout.split_column(
        Layout(name="header", size=10),
        Layout(name="top", ratio=3),
        Layout(name="mid", ratio=4),
        Layout(name="bottom", ratio=2),
        Layout(name="footer", size=1),
    )
    layout["top"].split_row(
        Layout(name="live_stats", ratio=2),
        Layout(name="sessions", ratio=3),
    )
    layout["mid"].split_row(
        Layout(name="agents", ratio=3),
        Layout(name="trends", ratio=3),
    )

    try:
        layout["header"].update(make_banner(tick, stats))
    except Exception:
        layout["header"].update(Panel(Text("⚡ Agent Pulse", style=f"bold {C_NEON_CYAN}")))
    try:
        layout["live_stats"].update(make_live_stats(stats, tick))
    except Exception as e:
        layout["live_stats"].update(Panel(Text(f"Error: {e}", style=C_NEON_RED)))
    try:
        layout["sessions"].update(make_active_sessions(stats, tick))
    except Exception as e:
        layout["sessions"].update(Panel(Text(f"Error: {e}", style=C_NEON_RED)))
    try:
        layout["agents"].update(make_agent_breakdown(stats, tick))
    except Exception as e:
        layout["agents"].update(Panel(Text(f"Error: {e}", style=C_NEON_RED)))
    try:
        layout["trends"].update(make_trends(stats, tick))
    except Exception as e:
        layout["trends"].update(Panel(Text(f"Error: {e}", style=C_NEON_RED)))
    try:
        layout["bottom"].update(make_installed_agents(stats, tick))
    except Exception as e:
        layout["bottom"].update(Panel(Text(f"Error: {e}", style=C_NEON_RED)))
    layout["footer"].update(make_footer(tick, refresh))

    return layout


# ─── Startup splash ──────────────────────────────────────────────────────────

def _show_startup_splash(console: Console) -> None:
    """Clean boot sequence with in-place braille spinners."""
    console.clear()
    console.print()

    # Banner — instant, white
    for line in BANNER_ART.strip("\n").split("\n"):
        console.print(Align.center(Text(line, style="bold white")))
    console.print(Align.center(Text(BANNER_SUBTITLE, style="bold white")))
    console.print()

    # Boot stages — each a different color with spinner (~5s total)
    stages = [
        ("Scanning processes",         0.8, C_NEON_CYAN),
        ("Connecting to session store", 0.9, C_NEON_GREEN),
        ("Loading agent registry",     0.9, C_NEON_PINK),
        ("Mapping active sessions",    1.0, C_WARN),
        ("Rendering dashboard",        0.7, "#bf7fff"),
    ]
    for label, duration, color in stages:
        with console.status(
            f"[bold {color}]{label}[/]",
            spinner="dots",
            spinner_style=f"bold {color}",
        ):
            time.sleep(duration)
        console.print(Align.center(Text(f"  ✓ {label}", style=f"bold {color}")))

    console.print()
    online = Text(justify="center")
    online.append("  ◉ ", style=f"bold {C_NEON_GREEN}")
    online.append("ONLINE", style=f"bold {C_NEON_GREEN}")
    console.print(Align.center(online))
    time.sleep(0.3)


# ─── Modes ────────────────────────────────────────────────────────────────────

def mode_live(refresh: int = 5, force_compact: bool = False) -> None:
    """Persistent live dashboard with SIGWINCH resize handling (from E)."""
    console = Console()
    tick = 0

    # ─── Animated startup splash ─────────────────────────────────────────
    _show_startup_splash(console)

    try:
        stats = collect_all_stats()
    except Exception as e:
        console.print(f"[{C_NEON_RED}]Error collecting stats:[/] {e}")
        return

    try:
        with Live(
            build_live_layout(stats, tick, refresh, force_compact),
            console=console,
            refresh_per_second=4,
            screen=True,
        ) as live:
            while True:
                try:
                    time.sleep(refresh)
                    tick += 1

                    # SIGWINCH resize detection (from E)
                    if check_terminal_resized():
                        console = Console()

                    try:
                        stats = collect_all_stats()
                    except sqlite3.OperationalError:
                        pass  # Keep old stats if DB locked
                    except Exception:
                        pass

                    live.update(build_live_layout(stats, tick, refresh, force_compact))
                except KeyboardInterrupt:
                    break
    except Exception as e:
        console.print(f"\n[{C_NEON_RED}]Live mode error:[/] {e}")


def mode_snapshot() -> None:
    """One-shot snapshot view."""
    console = Console()
    try:
        stats = collect_all_stats()
    except Exception as e:
        console.print(f"[{C_NEON_RED}]Error collecting stats:[/] {e}")
        return

    console.print()
    banner_content = Text.assemble(
        Text(BANNER_ART, style=f"bold {C_NEON_CYAN}", justify="center"),
        "\n",
        Text(BANNER_SUBTITLE, style=f"bold {C_NEON_CYAN}", justify="center"),
    )
    console.print(Panel(
        Align.center(banner_content),
        box=box.DOUBLE_EDGE,
        border_style=C_NEON_CYAN,
        padding=(0, 2),
    ))

    summary = Table(
        title=f"[bold {C_NEON_CYAN}]Quick Snapshot[/]",
        box=box.ROUNDED,
        expand=False,
        min_width=60,
    )
    summary.add_column("Metric", style=C_MUTED, width=30)
    summary.add_column("Value", style=C_LABEL, justify="right", width=10)
    summary.add_column("Detail", style=C_DIM)

    procs = stats["active_procs"]
    sessions = stats["active_sessions"]

    summary.add_row(Text("◉ Active CLI processes", style=C_GOOD), str(len(procs)), f"PIDs: {', '.join(str(p['pid']) for p in procs[:4])}")
    summary.add_row(Text("◉ Open sessions", style=C_GOOD), str(len(sessions)), f"IDs: {', '.join(s['id'] for s in sessions[:4])}")
    summary.add_row(Rule(style="#303050"), "", "")
    summary.add_row("Sessions today", str(stats["today_sessions"]), f"turns: {stats['today_turns']}")
    summary.add_row("Sessions this week", str(stats["week_sessions"]), "")
    summary.add_row("Sessions this month", str(stats["month_sessions"]), "")
    summary.add_row("All-time sessions", str(stats["total_sessions"]), f"turns: {stats['total_turns']}")
    summary.add_row(Rule(style="#303050"), "", "")
    summary.add_row(Text("Agents launched (24h)", style=C_WARN), str(stats["total_subagents_24h"]), _fmt_agent_types(stats["agents_24h"]))
    summary.add_row("Installed agents", str(len(stats["installed_agents"])), ", ".join(stats["installed_agents"][:5]))
    summary.add_row(Rule(style="#303050"), "", "")

    # Peak concurrent & velocity (from A/D)
    peak_val = max(stats.get("peak_concurrent_sessions", 0), stats.get("peak_concurrent_hour", 0))
    summary.add_row(Text("⚡ Peak concurrent", style=C_WARN), str(peak_val), "max sessions/hour today")
    velocity = stats.get("agent_velocity_per_hour", 0.0)
    summary.add_row(Text("🚀 Agent velocity", style=C_NEON_CYAN), f"{velocity:.1f}/h", "agents per hour")

    last_agent = stats.get("last_agent_launched")
    if last_agent:
        summary.add_row(Text("🕐 Last agent launched", style=C_NEON_CYAN), last_agent[:19], "")

    if stats.get("db_locked"):
        summary.add_row(Rule(style="#303050"), "", "")
        summary.add_row(Text("⚠ Database", style=C_WARN), "LOCKED", "Some stats may be unavailable")

    console.print(Align.center(summary))

    if stats["active_sessions"]:
        console.print(make_active_sessions(stats))

    # Sparklines with trend arrows
    sess_vals = [d["count"] for d in stats["daily_sessions"]]
    agent_vals = [d["count"] for d in stats["daily_agents"]]
    sp_s, trend_s = spark_with_trend(sess_vals, 14)
    sp_a, trend_a = spark_with_trend(agent_vals, 14)
    spark_panel = Panel(
        Text.assemble(
            Text(f"  14-day sessions {trend_s} ", style=C_MUTED),
            Text(sp_s, style=C_NEON_CYAN),
            Text(f"   ·   agents {trend_a} ", style=C_MUTED),
            Text(sp_a, style=C_WARN),
        ),
        title=f"[{C_NEON_PINK}]📈 14-Day Sparklines[/]",
        border_style=C_NEON_PINK,
        box=box.ROUNDED,
    )
    console.print(spark_panel)

    # 24h heatmap in snapshot too
    hourly = stats.get("hourly_sessions_24h") or []
    counts = [h["count"] for h in hourly]
    if counts:
        heatmap_panel = Panel(
            Text.assemble(
                Text("  24h activity  ", style=C_MUTED),
                activity_heatmap(counts),
                Text("  (░▒▓█ = session density per hour)", style=C_DIM),
            ),
            title=f"[{C_NEON_PINK}]📊 24-Hour Heatmap[/]",
            border_style=C_NEON_PINK,
            box=box.ROUNDED,
        )
        console.print(heatmap_panel)

    console.print(
        f"\n  [dim]Snapshot taken {stats['collected_at']}  ·  "
        f"last scan: {format_time_delta(stats['collected_at'])}  ·  "
        f"history saved to {HISTORY_FILE}[/dim]\n"
    )


def _fmt_agent_types(agents: dict) -> str:
    if not agents:
        return "none"
    parts = [f"{n}×{c}" for n, c in sorted(agents.items(), key=lambda x: -x[1])[:4]]
    return "  ".join(parts)


def mode_history() -> None:
    """Display historical stats."""
    console = Console()
    try:
        stats = collect_all_stats()
    except Exception as e:
        console.print(f"[{C_NEON_RED}]Error collecting stats:[/] {e}")
        return

    console.print()
    console.print(Rule(f"[bold {C_NEON_PINK}]📈 Agent Pulse — HISTORICAL STATS[/]"))
    console.print()
    console.print(make_trends(stats))

    history = stats["history"]
    t = Table(
        title=f"[bold {C_NEON_CYAN}]All-time Daily History[/]",
        box=box.ROUNDED,
        expand=False,
    )
    t.add_column("Date", style=C_MUTED)
    t.add_column("Sessions", style=C_NEON_CYAN, justify="right")
    t.add_column("Turns", style=C_LABEL, justify="right")
    t.add_column("Agents", style=C_WARN, justify="right")
    t.add_column("Activity", min_width=20)

    for date in sorted([k for k in history.keys() if isinstance(history[k], dict) and k[:2] == "20"], reverse=True)[:30]:
        d = history[date]
        s = d.get("sessions", 0)
        a = d.get("agents", 0)
        r = d.get("turns", 0)
        activity = Text()
        activity.append("S" * min(s, 20), style=C_NEON_CYAN)
        activity.append("A" * min(a // max(a // 10 + 1, 1), 10), style=C_WARN)
        t.add_row(date, str(s), str(r), str(a), activity)

    console.print(Align.center(t))
    console.print()


def mode_export() -> None:
    """Export stats as JSON to stdout."""
    try:
        stats = collect_all_stats()
        for s in stats["active_sessions"]:
            s["mtime"] = s["mtime"].isoformat()
        print(json.dumps(stats, indent=2, default=str))
    except Exception as e:
        print(json.dumps({"error": str(e)}, indent=2))


# ─── Entry point ─────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(
        prog="agent-pulse",
        description="⚡ Agent Pulse — Real-time GitHub Copilot CLI Dashboard",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python agent_pulse.py              # one-shot snapshot
  python agent_pulse.py --live       # persistent live dashboard (Ctrl+C to quit)
  python agent_pulse.py --history    # historical stats only
  python agent_pulse.py --export     # export JSON to stdout
  python agent_pulse.py --live -r 10 # refresh every 10 seconds
  python agent_pulse.py --compact    # force compact mode
        """,
    )
    parser.add_argument("--live",    "-l", action="store_true",  help="persistent live dashboard")
    parser.add_argument("--history", "-H", action="store_true",  help="show historical stats")
    parser.add_argument("--export",  "-e", action="store_true",  help="export JSON to stdout")
    parser.add_argument("--compact", "-c", action="store_true",  help="force compact mode")
    parser.add_argument("--refresh", "-r", type=int, default=5,  help="live refresh interval in seconds (default: 5)")
    args = parser.parse_args()

    if args.export:
        mode_export()
    elif args.history:
        mode_history()
    elif args.live:
        mode_live(refresh=args.refresh, force_compact=args.compact)
    else:
        mode_snapshot()


if __name__ == "__main__":
    main()
