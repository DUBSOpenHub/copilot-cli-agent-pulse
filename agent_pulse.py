#!/usr/bin/env python3
"""Agent Pulse — real-time agent tracking dashboard for GitHub Copilot CLI (macOS).

Install:
  pip install textual

Run (persistently, keep open):
  python3 agent_pulse.py

Data (SQLite):
  ~/.copilot/agent-pulse/agent-pulse.db

Telemetry signals (best-effort):
  1) `ps` inspection estimates active Copilot CLI *terminal sessions* (distinct TTYs).
  2) Incremental tail of ~/.copilot/logs/*.log detects agent launches by parsing
     `agent_type` markers and tool task payloads.

This dashboard is intentionally "mission control" styled (neon + motion) so it feels
alive while you work.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import time
import dataclasses
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Optional, Sequence, Tuple

from rich.align import Align
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

from textual.app import App, ComposeResult
from textual.containers import Grid, Horizontal, Vertical
from textual.reactive import reactive
from textual.widgets import DataTable, Footer, Static


# ----------------------------
# Visuals / Theme
# ----------------------------

ASCII_LOGO = r"""
    _                    _     ____        _
   / \   __ _  ___ _ __ | |_  |  _ \ _   _| |___  ___
  / _ \ / _` |/ _ \ '_ \| __| | |_) | | | | / __|/ _ \
 / ___ \ (_| |  __/ | | | |_  |  __/| |_| | \__ \  __/
/_/   \_\__, |\___|_| |_|\__| |_|    \__,_|_|___/\___|
        |___/
""".rstrip("\n")

ASCII_LOGO_COMPACT = "⚡ AGENT PULSE"

AGENT_TYPES = (
    "copilot",
    "tmux-pane",
    "process",
    "task",
    "explore",
    "general-purpose",
    "code-review",
    "rubber-duck",
    "dispatch-worker",
    "stampede-agent",
    "stampede-monitor",
    "stampede-commander",
    "metaswarm-division",
    "metaswarm-commander",
    "metaswarm-swarm",
    "metaswarm-squad",
    "metaswarm-sub-agent",
    "metaswarm-worker",
    "metaswarm-reviewer",
    "swarm-command",
)

TYPE_COLOR: Dict[str, str] = {
    "copilot": "#00ff87",
    "tmux-pane": "#00F5D4",
    "process": "#C7F9CC",
    "task": "#00D1FF",
    "explore": "#7CFF6B",
    "general-purpose": "#B388FF",
    "code-review": "#FF4D6D",
    "rubber-duck": "#FFD166",
    "dispatch-worker": "#00F5D4",
    "stampede-agent": "#FF9F1C",
    "stampede-monitor": "#8D99AE",
    "stampede-commander": "#FF9F1C",
    "metaswarm-division": "#B388FF",
    "metaswarm-commander": "#FF9F1C",
    "metaswarm-swarm": "#80FFDB",
    "metaswarm-squad": "#FFD166",
    "metaswarm-sub-agent": "#00F5D4",
    "metaswarm-worker": "#00F5D4",
    "metaswarm-reviewer": "#FF4D6D",
    "swarm-command": "#80FFDB",
    "custom": "#C7F9CC",
    "unknown": "#8D99AE",
}

LIVE_EVENT_WINDOW_S = 30 * 60
LEVEL_KEYS = (
    "division_commanders",
    "commanders",
    "squad_leads",
    "workers",
    "reviewers",
    "other",
)

_SPARK_CHARS = "▁▂▃▄▅▆▇█"
_WAVE_CHARS = "▁▂▃▄▅▆▇█▇▆▅▄▃▂▁"
_HEARTBEATS = ["💗", "💖", "💓", "❤️", "💓", "💗"]


def now_ts() -> int:
    return int(time.time())


def clamp(n: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, n))


def human_age(seconds: int) -> str:
    if seconds < 60:
        return f"{seconds}s"
    if seconds < 3600:
        return f"{seconds // 60}m"
    return f"{seconds // 3600}h"


def parse_iso_ts(value: object) -> Optional[int]:
    """Parse common ISO-8601 timestamp values into epoch seconds."""
    if not value or not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        return int(datetime.fromisoformat(text).timestamp())
    except ValueError:
        return None


def sparkline(values: Sequence[float], *, width: int = 40) -> str:
    if not values:
        return " " * width

    if len(values) > width:
        step = len(values) / width
        sampled = []
        for i in range(width):
            start = int(i * step)
            end = max(start + 1, int((i + 1) * step))
            chunk = values[start:end]
            sampled.append(sum(chunk) / len(chunk))
        values = sampled
    else:
        values = list(values) + [values[-1]] * (width - len(values))

    vmin = min(values)
    vmax = max(values)
    if vmax - vmin < 1e-9:
        return _SPARK_CHARS[0] * width

    out = []
    for v in values:
        x = (v - vmin) / (vmax - vmin)
        idx = int(clamp(round(x * (len(_SPARK_CHARS) - 1)), 0, len(_SPARK_CHARS) - 1))
        out.append(_SPARK_CHARS[idx])
    return "".join(out)


def pulse_wave(offset: int, width: int = 40) -> Text:
    """Generate a colored animated wave bar."""
    wave_colors = ["#1a1a2e", "#00D1FF", "#7CFF6B", "#FFD166", "#FF4D6D", "#B388FF", "#00F5D4", "#FF4D6D", "#FFD166", "#7CFF6B", "#00D1FF", "#1a1a2e"]
    result = Text()
    for i in range(width):
        char_idx = (i + offset) % len(_WAVE_CHARS)
        color_idx = (i + offset) % len(wave_colors)
        result.append(_WAVE_CHARS[char_idx], style=f"bold {wave_colors[color_idx]}")
    return result


def gradient_text(text: str, colors: Sequence[str]) -> Text:
    """Simple per-character gradient (fast, low-res, looks great on dark terminals)."""

    if not text:
        return Text("")

    stops = list(colors)
    if len(stops) < 2:
        stops = [stops[0], stops[0]]

    n = len(text)
    rich_text = Text()
    for i, ch in enumerate(text):
        t = i / max(1, n - 1)
        seg = int(t * (len(stops) - 1))
        seg = min(seg, len(stops) - 2)
        rich_text.append(ch, style=f"bold {stops[seg]}")
    return rich_text


# ----------------------------
# Process & Log Collection
# ----------------------------

@dataclass(frozen=True)
class Proc:
    pid: int
    ppid: int
    tty: str
    cmd: str


_COPILOT_CMD_RE = re.compile(
    r"(?i)(?:\bgh\s+copilot\b|\bcopilot\b|copilot-cli|@github/copilot|/copilot(?:\s|$))"
)

_AGENT_MARKERS_RE = re.compile(
    r"(?i)(?:\bagent\b|\bsubagent\b|\brubber[-_ ]duck\b|\bcode-review\b|\bexplore\b|\bgeneral-purpose\b|\bstampede\b|\bdispatch\b|\bswarm\b|\btask\b)"
)

_AGENT_TYPE_RE = re.compile(r"\bagent_type\b\s*[:=]\s*\"([^\"]+)\"", re.IGNORECASE)
_AGENT_TYPE_ESCAPED_RE = re.compile(r"agent_type\\\"\s*:\\s*\\\"([^\\\"]+)\\\"", re.IGNORECASE)

# Feature 1: Success/failure detection patterns
_SUCCESS_RE = re.compile(
    r"(?i)(?:completed successfully|exit code 0|task completed|✓|PASS\b)"
)
_FAILURE_RE = re.compile(
    r"(?i)(?:failed|error|exit code [1-9]\d*|exception|traceback|FAIL\b)"
)

# Feature 3: Token usage patterns
_TOKEN_RE = re.compile(
    r"(?:input_tokens|output_tokens|prompt_tokens|completion_tokens)\s*[:=]\s*(\d+)",
    re.IGNORECASE,
)
_INPUT_TOKEN_RE = re.compile(
    r"(?:input_tokens|prompt_tokens)\s*[:=]\s*(\d+)", re.IGNORECASE
)
_OUTPUT_TOKEN_RE = re.compile(
    r"(?:output_tokens|completion_tokens)\s*[:=]\s*(\d+)", re.IGNORECASE
)

# Feature 2: Model family color mapping
MODEL_FAMILY_COLOR: Dict[str, str] = {
    "claude": "#B388FF",
    "gpt": "#7CFF6B",
    "gemini": "#00D1FF",
    "mistral": "#FFD166",
    "llama": "#FF9F1C",
    "deepseek": "#00F5D4",
    "o1": "#FF4D6D",
    "o3": "#FF4D6D",
    "o4": "#FF4D6D",
    "unknown": "#8D99AE",
}


def shorten_model(name: str) -> str:
    """Shorten model names for compact display."""
    replacements = [
        ("claude-", "c/"),
        ("gpt-", "g/"),
        ("gemini-", "gem/"),
        ("mistral-", "mis/"),
    ]
    short = name
    for prefix, repl in replacements:
        if short.startswith(prefix):
            short = repl + short[len(prefix):]
            break
    return short[:20]


def model_color(name: str) -> str:
    """Return a color for a model based on its family."""
    lower = name.lower()
    for family, color in MODEL_FAMILY_COLOR.items():
        if family in lower:
            return color
    return MODEL_FAMILY_COLOR["unknown"]


@dataclass
class AgentEvent:
    ts: int
    agent_type: str
    name: Optional[str] = None
    model: Optional[str] = None
    source: str = ""  # unique id for dedupe
    outcome: str = "unknown"  # success, failure, unknown
    duration_s: Optional[int] = None


@dataclass
class MetaswarmChild:
    ts: int
    run_id: str
    commander_id: str
    child_id: str
    role: str
    event: str
    status: str
    model: Optional[str] = None


@dataclass
class MetaswarmCommander:
    run_id: str
    commander_id: str
    model: Optional[str]
    status: str
    phase: str
    pid_status: str
    squad_leads_launched: int
    squad_leads_target: int
    workers_launched: int
    workers_target: int
    workers_running: int
    workers_completed: int
    workers_failed: int
    atoms_received: int
    heartbeat_age_s: Optional[int]
    child_agents_seen: int = 0
    child_agents_running: int = 0
    child_agents_completed: int = 0
    child_agents_failed: int = 0
    child_agents_stale: int = 0
    division_commanders_seen: int = 0
    commanders_seen: int = 0
    squad_leads_seen: int = 0
    workers_seen: int = 0
    reviewers_seen: int = 0
    other_children_seen: int = 0
    recent_children: List[MetaswarmChild] = field(default_factory=list)


@dataclass
class MetaswarmRun:
    run_id: str
    repo_path: str
    profile: str
    commanders: List[MetaswarmCommander] = field(default_factory=list)


@dataclass
class LiveAgent:
    source: str
    agent_id: str
    agent_type: str
    name: str
    status: str
    age_s: int
    model: Optional[str] = None
    pid: Optional[int] = None
    parent: Optional[str] = None


def empty_level_counts() -> Dict[str, int]:
    return {key: 0 for key in LEVEL_KEYS}


def empty_child_counts() -> Dict[str, int]:
    counts = {
        "total": 0,
        "completed": 0,
        "failed": 0,
        "in_progress": 0,
    }
    counts.update(empty_level_counts())
    return counts


def display_agent_type(agent_type: str) -> str:
    """Map legacy/internal type names to user-facing dashboard labels."""
    return {
        "metaswarm-worker": "metaswarm-sub-agent",
        "stampede-agent": "stampede-sub-agent",
        "dispatch-worker": "dispatch-sub-agent",
    }.get(agent_type, agent_type)


def classify_agent_level(
    agent_type: str,
    name: Optional[str] = None,
    parent: Optional[str] = None,
    source: Optional[str] = None,
) -> str:
    """Classify visible agents into hierarchy levels for swarm dashboards."""

    haystack = " ".join(
        part.lower()
        for part in (agent_type, name or "", parent or "", source or "")
        if part
    )
    normalized_type = agent_type.lower()

    if normalized_type == "metaswarm-swarm":
        return "other"
    if normalized_type == "metaswarm-division" or "division" in haystack or "div-" in haystack:
        return "division_commanders"
    if (
        normalized_type in {"metaswarm-commander", "swarm-command", "stampede-commander"}
        or "commander" in haystack
        or "cmd-" in haystack
        or "hive-auth-" in haystack
        or "hive1k" in haystack
    ):
        return "commanders"
    if normalized_type in {"metaswarm-squad"} or "squad" in haystack:
        return "squad_leads"
    if normalized_type in {"metaswarm-reviewer", "code-review"} or "reviewer" in haystack or "code-review" in haystack:
        return "reviewers"
    if normalized_type in {"metaswarm-sub-agent", "metaswarm-worker", "stampede-agent", "dispatch-worker"}:
        return "workers"
    if normalized_type in {"task", "explore"}:
        return "workers"
    if "worker" in haystack or "sub-agent" in haystack or "subagent" in haystack or "leaf" in haystack or "validator" in haystack:
        return "workers"
    if "lead" in haystack:
        return "squad_leads"
    return "other"


def count_agent_levels(agents: Sequence[LiveAgent], *, running_only: bool = True) -> Dict[str, int]:
    counts = empty_level_counts()
    for agent in agents:
        if agent.agent_type in {"metaswarm-swarm", "stampede-monitor"}:
            continue
        if running_only and agent.status not in {"RUN", "IN-FLIGHT"}:
            continue
        level = classify_agent_level(
            agent.agent_type,
            agent.name,
            agent.parent,
            agent.source,
        )
        counts[level] = counts.get(level, 0) + 1
    return counts


def agent_type_for_child_role(role: object, child_id: object = None) -> str:
    text = str(role or "child")
    level = classify_agent_level(text, str(child_id or ""))
    if level == "division_commanders":
        return "metaswarm-division"
    if level == "commanders":
        return "metaswarm-commander"
    if level == "squad_leads":
        return "metaswarm-squad"
    if level == "workers":
        return "metaswarm-sub-agent"
    if level == "reviewers":
        return "metaswarm-reviewer"
    return "custom"


class ProcessCollector:
    def collect(self) -> List[Proc]:
        out = subprocess.check_output(["ps", "-axo", "pid=,ppid=,tty=,command="])
        text = out.decode("utf-8", errors="replace")
        procs: List[Proc] = []
        for line in text.splitlines():
            parts = line.strip().split(None, 3)
            if len(parts) < 4:
                continue
            try:
                pid = int(parts[0])
                ppid = int(parts[1])
            except ValueError:
                continue
            procs.append(Proc(pid=pid, ppid=ppid, tty=parts[2], cmd=parts[3]))
        return procs

    @staticmethod
    def is_copilot_process(cmd: str) -> bool:
        if "agent_pulse.py" in cmd:
            return False
        return bool(_COPILOT_CMD_RE.search(cmd))

    @staticmethod
    def is_agentish_process(cmd: str) -> bool:
        if "agent_pulse.py" in cmd:
            return False
        return ProcessCollector.is_copilot_process(cmd) and bool(_AGENT_MARKERS_RE.search(cmd))


class TmuxPaneCollector:
    """Best-effort inventory of agent-like tmux panes."""

    def collect(self) -> List[LiveAgent]:
        try:
            out = subprocess.check_output(
                [
                    "tmux",
                    "list-panes",
                    "-a",
                    "-F",
                    "#{session_name}\t#{window_index}\t#{pane_index}\t#{pane_title}\t#{pane_pid}\t#{pane_dead}\t#{pane_dead_status}",
                ],
                stderr=subprocess.DEVNULL,
                timeout=2,
            )
        except (OSError, subprocess.SubprocessError):
            return []

        live: List[LiveAgent] = []
        for line in out.decode("utf-8", errors="replace").splitlines():
            parts = line.split("\t")
            if len(parts) < 7:
                continue
            session_name, window_index, pane_index, title, pane_pid, pane_dead, pane_dead_status = parts[:7]
            haystack = f"{session_name} {title}".lower()
            if not (
                session_name.startswith("stampede-")
                or "copilot" in haystack
                or "agent" in haystack
                or "commander" in haystack
                or "swarm" in haystack
            ):
                continue
            agent_type = "tmux-pane"
            if "monitor" in haystack:
                agent_type = "stampede-monitor"
            elif "commander" in haystack:
                agent_type = "stampede-commander"
            elif "stampede" in haystack:
                agent_type = "stampede-agent"
            elif "swarm" in haystack:
                agent_type = "swarm-command"
            status = "RUN" if pane_dead != "1" else f"DEAD:{pane_dead_status or '?'}"
            model = None
            for token in re.split(r"\s+", title.replace("·", " ")):
                if token.startswith(("claude-", "gpt-", "gemini-", "mistral-")):
                    model = token
                    break
            try:
                pid = int(pane_pid)
            except ValueError:
                pid = None
            live.append(
                LiveAgent(
                    source="tmux",
                    agent_id=f"{session_name}:{window_index}.{pane_index}",
                    agent_type=agent_type,
                    name=title or session_name,
                    status=status,
                    age_s=0,
                    model=model,
                    pid=pid,
                    parent=session_name,
                )
            )
        return live


class CopilotLogTailer:
    """Incremental tail of ~/.copilot/logs/*.log with offsets persisted to our DB."""

    def __init__(self, store: "PulseStore"):
        self.store = store
        self.log_dir = Path.home() / ".copilot" / "logs"

    def _candidate_files(self, limit: int = 12) -> List[Path]:
        if not self.log_dir.exists():
            return []
        files = sorted(self.log_dir.glob("*.log"), key=lambda p: p.stat().st_mtime, reverse=True)
        return files[:limit]

    def poll_new_events(self, max_bytes_per_file: int = 120_000) -> List[AgentEvent]:
        out: List[AgentEvent] = []

        for path in self._candidate_files():
            try:
                last_off = self.store.get_log_offset(str(path))
                size = path.stat().st_size
                if last_off > size:
                    last_off = 0  # rotation

                read_start = last_off
                read_end = min(size, read_start + max_bytes_per_file)
                if read_end <= read_start:
                    continue

                with path.open("rb") as f:
                    f.seek(read_start)
                    chunk = f.read(read_end - read_start)

                self.store.set_log_offset(str(path), read_end)

                text = chunk.decode("utf-8", errors="replace")
                base_source = f"log:{path.name}:{read_start}"

                for i, line in enumerate(text.splitlines()):
                    # Feature 3: Parse token usage from any line
                    self._parse_tokens(line, path.name, read_start, i)

            except Exception:
                # Logs are best-effort; dashboard should never crash because of them.
                continue

        return self.store.insert_agent_events(out)

    def _parse_tokens(self, line: str, filename: str, offset: int, lineno: int) -> None:
        """Extract token usage from a log line and store it."""
        input_tok = 0
        output_tok = 0
        m_in = _INPUT_TOKEN_RE.search(line)
        m_out = _OUTPUT_TOKEN_RE.search(line)
        if not m_in and not m_out:
            return
        if m_in:
            input_tok = int(m_in.group(1))
        if m_out:
            output_tok = int(m_out.group(1))
        # Find model if present in same line
        m_model = re.search(r"\bmodel\b\s*[:=]\s*\"([^\"]{1,80})\"", line)
        model = m_model.group(1) if m_model else None
        ts = self._parse_ts(line) or now_ts()
        source = f"tok:{filename}:{offset}:L{lineno}"
        self.store.insert_token_usage(ts, model, input_tok, output_tok, source)

    @staticmethod
    def _parse_ts(line: str) -> Optional[int]:
        # Example: 2026-04-12T17:45:37.650Z
        m = re.match(r"^(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\.\d{3}Z)", line)
        if not m:
            return None
        try:
            dt = datetime.strptime(m.group(1), "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=timezone.utc)
            return int(dt.timestamp())
        except Exception:
            return None


class SessionEventTailer:
    """Parse agent launches from ~/.copilot/session-state/*/events.jsonl (JSON)."""

    def __init__(self, store: "PulseStore"):
        self.store = store
        self.session_dir = Path.home() / ".copilot" / "session-state"

    def _candidate_dirs(self, limit: int = 30) -> List[Path]:
        if not self.session_dir.exists():
            return []
        dirs = [d for d in self.session_dir.iterdir() if d.is_dir()]
        dirs.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        return dirs[:limit]

    @staticmethod
    def _detect_session_model(text: str) -> str | None:
        """Extract the session-level model from model_change or execution_complete events."""
        session_model: str | None = None
        for line in text.splitlines():
            if "model" not in line:
                continue
            try:
                data = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            ev_type = data.get("type", "")
            dd = data.get("data", {})
            if not isinstance(dd, dict):
                continue
            if ev_type == "session.model_change":
                session_model = dd.get("newModel") or session_model
            elif ev_type == "tool.execution_complete":
                m = dd.get("model")
                if m:
                    session_model = m
        return session_model

    def poll_new_events(self) -> List[AgentEvent]:
        out: List[AgentEvent] = []
        for d in self._candidate_dirs():
            evf = d / "events.jsonl"
            if not evf.exists():
                continue
            try:
                key = str(evf)
                last_off = self.store.get_log_offset(key)
                size = evf.stat().st_size
                if last_off > size:
                    last_off = 0
                if size <= last_off:
                    continue

                with evf.open("rb") as f:
                    f.seek(last_off)
                    chunk = f.read(size - last_off)

                self.store.set_log_offset(key, size)
                text = chunk.decode("utf-8", errors="replace")
                base_source = f"evt:{d.name}:{last_off}"

                # Detect the session-level model to use as fallback
                session_model = self._detect_session_model(text)

                # Two-pass approach:
                # Pass 1: collect agent starts keyed by toolCallId
                # Pass 2: correlate execution_complete outcomes back to starts
                agent_starts: dict[str, int] = {}  # toolCallId -> index in out

                for i, line in enumerate(text.splitlines()):
                    try:
                        data = json.loads(line)
                    except (json.JSONDecodeError, ValueError):
                        continue

                    ev_type = data.get("type", "")
                    dd = data.get("data", {})
                    if not isinstance(dd, dict):
                        continue

                    if ev_type == "tool.execution_complete":
                        # Correlate outcome back to the matching start event
                        tid = dd.get("toolCallId")
                        if tid and tid in agent_starts:
                            idx = agent_starts[tid]
                            success = dd.get("success")
                            if success is True:
                                out[idx] = dataclasses.replace(out[idx], outcome="success")
                            elif success is False:
                                out[idx] = dataclasses.replace(out[idx], outcome="failure")
                        continue

                    if "agent_type" not in line:
                        continue

                    agent_type = None
                    name = None
                    model = None
                    description = None

                    # Source 1: tool.execution_start with arguments (primary)
                    args = dd.get("arguments", {})
                    if isinstance(args, dict) and "agent_type" in args:
                        agent_type = args["agent_type"]
                        name = args.get("name") or None
                        model = args.get("model") or None
                        description = args.get("description") or None

                    # Source 2: tool.call with arguments
                    if not agent_type:
                        # Some events store arguments at data level
                        if isinstance(dd, dict) and "agent_type" in dd:
                            agent_type = dd["agent_type"]
                            name = dd.get("name") or None
                            model = dd.get("model") or None
                            description = dd.get("description") or None

                    if not agent_type:
                        continue

                    agent_type = agent_type if agent_type in AGENT_TYPES else "custom"

                    # Fall back to session model when no explicit model was passed
                    if not model and session_model:
                        model = session_model

                    # Use description as name fallback
                    if not name and description:
                        name = description[:80]

                    # Parse timestamp
                    ts_str = data.get("timestamp") or dd.get("timestamp") or ""
                    ts = now_ts()
                    if ts_str:
                        try:
                            dt = datetime.strptime(ts_str[:23] + "Z", "%Y-%m-%dT%H:%M:%S.%fZ")
                            dt = dt.replace(tzinfo=timezone.utc)
                            ts = int(dt.timestamp())
                        except Exception:
                            pass

                    source = f"{base_source}:L{i}"
                    event_idx = len(out)
                    out.append(AgentEvent(
                        ts=ts, agent_type=agent_type,
                        name=name, model=model,
                        source=source, outcome="unknown",
                    ))

                    # Track toolCallId for outcome correlation
                    tid = dd.get("toolCallId")
                    if tid:
                        agent_starts[tid] = event_idx

            except Exception:
                continue

        return self.store.insert_agent_events(out)


class StampedeTelemetryCollector:
    """Read Terminal Stampede metaswarm telemetry from repo-local .stampede runs."""

    _RUN_DIR_LIMIT = 12
    _LEDGER_MAX_BYTES = 5_000_000

    def __init__(self, store: "PulseStore"):
        self.store = store
        self._bases_cache: List[Path] = []
        self._last_base_scan = 0.0

    @staticmethod
    def _read_json(path: Path) -> Dict:
        try:
            if path.exists():
                data = json.loads(path.read_text(errors="replace"))
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    @staticmethod
    def _pid_alive(pid: object) -> bool:
        try:
            os.kill(int(pid), 0)
            return True
        except (OSError, TypeError, ValueError):
            return False

    def _iter_stampede_bases(self) -> List[Path]:
        """Scan common roots plus an opt-in root list without walking home deeply every tick."""
        if self._bases_cache and time.time() - self._last_base_scan < 10:
            return self._bases_cache

        env_roots = [
            Path(p).expanduser()
            for p in os.environ.get("AGENT_PULSE_SCAN_ROOTS", "").split(os.pathsep)
            if p
        ]
        roots = [Path.cwd(), Path.home(), Path.home() / "dev", Path.home() / "tmp", *env_roots]
        bases: Dict[str, Path] = {}

        def add_base(path: Path) -> None:
            if path.exists() and path.is_dir():
                bases[str(path)] = path

        def scan_depth(root: Path, max_depth: int = 3) -> None:
            stack: List[Tuple[Path, int]] = [(root, 0)]
            while stack and len(bases) < 100:
                current, depth = stack.pop()
                try:
                    add_base(current / ".stampede")
                    if depth >= max_depth:
                        continue
                    for child in current.iterdir():
                        if child.name.startswith(".") or child.name in {
                            "Library",
                            "Applications",
                            "Pictures",
                            "Movies",
                            "Music",
                            "node_modules",
                            ".git",
                            ".venv",
                            "venv",
                        }:
                            continue
                        if child.is_dir():
                            stack.append((child, depth + 1))
                except Exception:
                    continue

        for root in roots:
            try:
                if not root.exists() or not root.is_dir():
                    continue
                scan_depth(root, 2 if root == Path.home() else 3)
            except Exception:
                continue

        self._bases_cache = list(bases.values())
        self._last_base_scan = time.time()
        return self._bases_cache

    def _candidate_run_dirs(self) -> List[Path]:
        runs: Dict[str, Path] = {}
        for base in self._iter_stampede_bases():
            try:
                for run_dir in base.glob("run-*"):
                    if run_dir.is_dir():
                        runs[str(run_dir)] = run_dir
            except Exception:
                continue

        def mtime(path: Path) -> float:
            try:
                return path.stat().st_mtime
            except OSError:
                return 0.0

        return sorted(runs.values(), key=mtime, reverse=True)[: self._RUN_DIR_LIMIT]

    def _poll_ledger_events(self, ledger: Path, run_id: str, commander_id: str) -> None:
        key = f"stampede-ledger:{ledger}"
        try:
            size = ledger.stat().st_size
            last_off = self.store.get_log_offset(key)
            if last_off > size:
                last_off = 0
            if size <= last_off:
                return

            with ledger.open("rb") as f:
                f.seek(last_off)
                chunk = f.read(size - last_off)
            self.store.set_log_offset(key, size)
        except Exception:
            return

        events: List[AgentEvent] = []
        line_offset = last_off
        for raw_line in chunk.splitlines():
            source = f"stampede:{run_id}:{commander_id}:{line_offset}"
            line_offset += len(raw_line) + 1
            try:
                data = json.loads(raw_line.decode("utf-8", errors="replace"))
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(data, dict) or data.get("event") != "launch_started":
                continue

            child_id = str(data.get("child_id") or data.get("agent_id") or data.get("id") or "sub-agent")
            role = str(data.get("role") or data.get("agent_type") or "sub-agent")
            agent_type = agent_type_for_child_role(role, child_id)
            ts = parse_iso_ts(data.get("ts") or data.get("timestamp")) or now_ts()
            events.append(
                AgentEvent(
                    ts=ts,
                    agent_type=agent_type,
                    name=f"{commander_id}/{child_id}",
                    model=data.get("model") if isinstance(data.get("model"), str) else None,
                    source=source,
                    outcome="unknown",
                )
            )

        self.store.insert_agent_events(events)

    def _ledger_children(self, ledger: Path, run_id: str, commander_id: str, limit: int = 12) -> Tuple[List[MetaswarmChild], Dict[str, int]]:
        try:
            size = ledger.stat().st_size
            read_start = max(0, size - self._LEDGER_MAX_BYTES)
            with ledger.open("rb") as f:
                f.seek(read_start)
                text = f.read(size - read_start).decode("utf-8", errors="replace")
        except Exception:
            return [], empty_child_counts()

        latest: Dict[str, MetaswarmChild] = {}
        for line in text.splitlines():
            try:
                data = json.loads(line)
            except (json.JSONDecodeError, ValueError):
                continue
            if not isinstance(data, dict):
                continue
            child_id = data.get("child_id") or data.get("agent_id") or data.get("id")
            if not child_id:
                continue
            child_id = str(child_id)
            event = str(data.get("event") or "update")
            status = str(data.get("status") or event)
            ts = parse_iso_ts(data.get("ts") or data.get("timestamp")) or now_ts()
            previous = latest.get(child_id)
            role = data.get("role") or data.get("agent_type")
            if not role and previous:
                role = previous.role
            model = data.get("model") if isinstance(data.get("model"), str) else previous.model if previous else None
            latest[child_id] = MetaswarmChild(
                ts=ts,
                run_id=run_id,
                commander_id=commander_id,
                child_id=child_id,
                role=str(role or "sub-agent"),
                event=event,
                status=status,
                model=model,
            )

        counts = empty_child_counts()
        counts["total"] = len(latest)
        for child in latest.values():
            status = child.status.lower()
            event = child.event.lower()
            level = classify_agent_level(child.role, child.child_id)
            counts[level] = counts.get(level, 0) + 1
            if event == "completed" or status in {"success", "done", "completed"}:
                counts["completed"] += 1
            elif event == "failed" or status in {"failed", "error"}:
                counts["failed"] += 1
            else:
                counts["in_progress"] += 1

        return sorted(latest.values(), key=lambda c: c.ts, reverse=True)[:limit], counts

    def poll(self) -> List[MetaswarmRun]:
        runs: List[MetaswarmRun] = []
        now = now_ts()

        for run_dir in self._candidate_run_dirs():
            state = self._read_json(run_dir / "state.json")
            fleet = self._read_json(run_dir / "fleet.json")
            run_id = str(state.get("run_id") or run_dir.name)
            profile = str(state.get("profile") or "metaswarm")
            repo_path = str(state.get("repo_path") or run_dir.parent.parent)
            commanders: List[MetaswarmCommander] = []

            for commander_dir in sorted((run_dir / "commanders").glob("commander-*")):
                commander_id = commander_dir.name
                commander_state = self._read_json(commander_dir / "swarm-state.json")
                telemetry = commander_state.get("telemetry", {})
                if not isinstance(telemetry, dict):
                    telemetry = {}
                fleet_meta = fleet.get(commander_id, {}) if isinstance(fleet, dict) else {}
                if not isinstance(fleet_meta, dict):
                    fleet_meta = {}

                ledger = commander_dir / "child-agents.jsonl"
                if ledger.exists():
                    self._poll_ledger_events(ledger, run_id, commander_id)
                    recent_children, child_counts = self._ledger_children(ledger, run_id, commander_id)
                else:
                    recent_children = []
                    child_counts = empty_child_counts()

                pid_status = "unknown"
                pid_file = run_dir / "pids" / f"{commander_id}.pid"
                if pid_file.exists():
                    try:
                        pid_status = "run" if self._pid_alive(pid_file.read_text().strip()) else "dead"
                    except Exception:
                        pid_status = "unknown"

                hb_ts = parse_iso_ts(commander_state.get("last_heartbeat_at") or commander_state.get("updated_at"))
                heartbeat_age = max(0, now - hb_ts) if hb_ts else None
                commander_active = (
                    pid_status == "run"
                    or (
                        pid_status == "unknown"
                        and str(commander_state.get("status") or "") in {"running", "starting"}
                        and (heartbeat_age is None or heartbeat_age < 90)
                    )
                )
                child_in_progress = int(child_counts.get("in_progress") or 0)
                commanders.append(
                    MetaswarmCommander(
                        run_id=run_id,
                        commander_id=commander_id,
                        model=(
                            commander_state.get("model")
                            if isinstance(commander_state.get("model"), str)
                            else fleet_meta.get("model")
                            if isinstance(fleet_meta.get("model"), str)
                            else None
                        ),
                        status=str(commander_state.get("status") or "unknown"),
                        phase=str(commander_state.get("phase") or "unknown"),
                        pid_status=pid_status,
                        squad_leads_launched=int(telemetry.get("squad_leads_launched") or 0),
                        squad_leads_target=int(telemetry.get("squad_leads_target") or 0),
                        workers_launched=int(telemetry.get("workers_launched") or 0),
                        workers_target=int(telemetry.get("workers_target") or 0),
                        workers_running=int(telemetry.get("workers_running") or 0),
                        workers_completed=int(telemetry.get("workers_completed") or 0),
                        workers_failed=int(telemetry.get("workers_failed") or 0),
                        atoms_received=int(telemetry.get("atoms_received") or 0),
                        heartbeat_age_s=heartbeat_age,
                        child_agents_seen=int(child_counts.get("total") or 0),
                        child_agents_running=child_in_progress if commander_active else 0,
                        child_agents_completed=int(child_counts.get("completed") or 0),
                        child_agents_failed=int(child_counts.get("failed") or 0),
                        child_agents_stale=0 if commander_active else child_in_progress,
                        division_commanders_seen=int(child_counts.get("division_commanders") or 0),
                        commanders_seen=int(child_counts.get("commanders") or 0),
                        squad_leads_seen=int(child_counts.get("squad_leads") or 0),
                        workers_seen=int(child_counts.get("workers") or 0),
                        reviewers_seen=int(child_counts.get("reviewers") or 0),
                        other_children_seen=int(child_counts.get("other") or 0),
                        recent_children=recent_children,
                    )
                )

            if commanders:
                runs.append(MetaswarmRun(run_id=run_id, repo_path=repo_path, profile=profile, commanders=commanders))

        return runs

    def live_agents(self, metaswarm_runs: Optional[List[MetaswarmRun]] = None) -> List[LiveAgent]:
        """Return visible Stampede commanders/sub-agents and recent nested sub-agents."""
        now = now_ts()
        live: List[LiveAgent] = []
        seen_stampede_agents: set[str] = set()

        for run_dir in self._candidate_run_dirs():
            state = self._read_json(run_dir / "state.json")
            fleet = self._read_json(run_dir / "fleet.json")
            run_id = str(state.get("run_id") or run_dir.name)
            try:
                run_age_s = max(0, now - int(run_dir.stat().st_mtime))
            except OSError:
                run_age_s = 0
            pids_dir = run_dir / "pids"
            if pids_dir.exists():
                for pid_file in sorted(pids_dir.glob("*.pid")):
                    agent_id = pid_file.stem
                    try:
                        pid_text = pid_file.read_text().strip()
                        pid = int(pid_text)
                    except Exception:
                        pid = None
                    alive = self._pid_alive(pid) if pid is not None else False
                    meta = fleet.get(agent_id, {}) if isinstance(fleet, dict) else {}
                    if not isinstance(meta, dict):
                        meta = {}
                    role = str(meta.get("role") or ("commander" if agent_id.startswith("commander-") else "worker"))
                    if role == "commander":
                        agent_type = "stampede-commander"
                    elif role == "worker":
                        agent_type = "stampede-agent"
                    else:
                        agent_type = agent_type_for_child_role(role, agent_id)
                    live.append(
                        LiveAgent(
                            source="stampede",
                            agent_id=f"{run_id}/{agent_id}",
                            agent_type=agent_type,
                            name=agent_id,
                            status="RUN" if alive else "DEAD",
                            age_s=run_age_s,
                            model=meta.get("model") if isinstance(meta.get("model"), str) else None,
                            pid=pid,
                            parent=run_id,
                        )
                    )
                    seen_stampede_agents.add(f"{run_id}/{agent_id}")

        if metaswarm_runs is None:
            metaswarm_runs = self.poll()

        for run in metaswarm_runs:
            for commander in run.commanders:
                commander_agent_id = f"{run.run_id}/{commander.commander_id}"
                commander_active = (
                    commander.pid_status == "run"
                    or (
                        commander.pid_status == "unknown"
                        and commander.status in {"running", "starting"}
                        and (commander.heartbeat_age_s is None or commander.heartbeat_age_s < 90)
                    )
                )
                if commander_agent_id not in seen_stampede_agents:
                    if commander.status == "blocked":
                        commander_status = "BLOCKED"
                    elif commander.status in {"failed", "error"}:
                        commander_status = "FAILED"
                    elif commander.status in {"success", "done", "completed"}:
                        commander_status = "DONE"
                    elif commander_active:
                        commander_status = "RUN"
                    else:
                        commander_status = "STALE"
                    live.append(
                        LiveAgent(
                            source="metaswarm",
                            agent_id=commander_agent_id,
                            agent_type="stampede-commander",
                            name=f"{commander.commander_id} · {commander.phase}",
                            status=commander_status,
                            age_s=commander.heartbeat_age_s or 0,
                            model=commander.model,
                            parent=run.run_id,
                        )
                    )
                if commander.child_agents_seen:
                    summary_status = "RUN" if commander_active and commander.child_agents_running else "STALE" if commander.child_agents_stale else "DONE"
                    live.append(
                        LiveAgent(
                            source="metaswarm",
                            agent_id=f"{run.run_id}/{commander.commander_id}/sub-agents",
                            agent_type="metaswarm-swarm",
                            name=(
                                f"sub-agents {commander.child_agents_seen} "
                                f"(div {commander.division_commanders_seen}, cmd {commander.commanders_seen}, "
                                f"sq {commander.squad_leads_seen}, sub {commander.workers_seen}, "
                                f"rev {commander.reviewers_seen}, other {commander.other_children_seen}; "
                                f"run {commander.child_agents_running}, stale {commander.child_agents_stale}, "
                                f"done {commander.child_agents_completed}, fail {commander.child_agents_failed})"
                            ),
                            status=summary_status,
                            age_s=commander.heartbeat_age_s or 0,
                            model=commander.model,
                            parent=commander.commander_id,
                        )
                    )
                for child in commander.recent_children:
                    if child.event in {"completed", "failed"}:
                        status = "DONE" if child.status == "success" else child.status.upper()
                    elif commander_active:
                        status = "RUN"
                    else:
                        status = "STALE"
                    if status in {"DONE", "SUCCESS"} and now - child.ts > 300:
                        continue
                    if status in {"STALE", "DEAD"} and now - child.ts > 1800:
                        continue
                    agent_type = agent_type_for_child_role(child.role, child.child_id)
                    live.append(
                        LiveAgent(
                            source="metaswarm",
                            agent_id=f"{run.run_id}/{commander.commander_id}/{child.child_id}",
                            agent_type=agent_type,
                            name=child.child_id,
                            status=status,
                            age_s=max(0, now - child.ts),
                            model=child.model,
                            parent=commander.commander_id,
                        )
                    )

        return live


# ----------------------------
# SQLite Storage
# ----------------------------

class PulseStore:
    def __init__(self) -> None:
        base = Path.home() / ".copilot" / "agent-pulse"
        base.mkdir(parents=True, exist_ok=True)
        self.db_path = base / "agent-pulse.db"
        self._con = sqlite3.connect(self.db_path, timeout=5)
        self._con.execute("PRAGMA journal_mode=WAL")
        self._con.execute("PRAGMA synchronous=NORMAL")
        self._init_schema()

    def close(self) -> None:
        self._con.close()

    def _init_schema(self) -> None:
        cur = self._con.cursor()
        cur.executescript(
            """
            CREATE TABLE IF NOT EXISTS snapshots (
              ts INTEGER PRIMARY KEY,
              active_sessions INTEGER NOT NULL,
              running_agents_est INTEGER NOT NULL,
              agent_events_last5m INTEGER NOT NULL,
              notes_json TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS agent_events (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts INTEGER NOT NULL,
              agent_type TEXT NOT NULL,
              name TEXT,
              model TEXT,
              source TEXT NOT NULL,
              UNIQUE(source)
            );

            CREATE INDEX IF NOT EXISTS idx_agent_events_ts ON agent_events(ts);
            CREATE INDEX IF NOT EXISTS idx_agent_events_type ON agent_events(agent_type);

            CREATE TABLE IF NOT EXISTS log_offsets (
              path TEXT PRIMARY KEY,
              offset INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS seen_agent_pids (
              pid INTEGER PRIMARY KEY,
              first_seen_ts INTEGER NOT NULL,
              cmd TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS token_usage (
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              ts INTEGER NOT NULL,
              model TEXT,
              input_tokens INTEGER NOT NULL DEFAULT 0,
              output_tokens INTEGER NOT NULL DEFAULT 0,
              source TEXT NOT NULL,
              UNIQUE(source)
            );

            CREATE INDEX IF NOT EXISTS idx_token_usage_ts ON token_usage(ts);
            """
        )
        self._con.commit()

        # Feature 1: ALTER TABLE for existing DBs (outcome + duration_s columns)
        for col, typedef in [("outcome", "TEXT DEFAULT 'unknown'"), ("duration_s", "INTEGER")]:
            try:
                self._con.execute(f"ALTER TABLE agent_events ADD COLUMN {col} {typedef}")
                self._con.commit()
            except sqlite3.OperationalError:
                pass  # column already exists

        # One-time backfill: reset event file offsets so model/outcome inference can fill gaps
        null_model_count = self._con.execute(
            "SELECT COUNT(*) FROM agent_events WHERE model IS NULL"
        ).fetchone()[0]
        unknown_outcome_count = self._con.execute(
            "SELECT COUNT(*) FROM agent_events WHERE outcome = 'unknown'"
        ).fetchone()[0]
        if null_model_count > 0 or unknown_outcome_count > 0:
            self._con.execute("DELETE FROM log_offsets WHERE path LIKE '%events.jsonl'")
            self._con.commit()

    def insert_snapshot(
        self,
        ts: int,
        active_sessions: int,
        running_agents_est: int,
        agent_events_last5m: int,
        notes: Dict,
    ) -> None:
        self._con.execute(
            "INSERT OR REPLACE INTO snapshots(ts, active_sessions, running_agents_est, agent_events_last5m, notes_json) VALUES (?,?,?,?,?)",
            (ts, active_sessions, running_agents_est, agent_events_last5m, json.dumps(notes, separators=(",", ":"))),
        )
        self._con.commit()

    def insert_agent_events(self, events_in: List[AgentEvent]) -> List[AgentEvent]:
        if not events_in:
            return []

        inserted: List[AgentEvent] = []
        cur = self._con.cursor()
        for ev in events_in:
            try:
                cur.execute(
                    "INSERT INTO agent_events(ts, agent_type, name, model, source, outcome, duration_s) VALUES (?,?,?,?,?,?,?)",
                    (ev.ts, ev.agent_type, ev.name, ev.model, ev.source, ev.outcome, ev.duration_s),
                )
                inserted.append(ev)
            except sqlite3.IntegrityError:
                # Row exists; update model and outcome if we now have better data
                updates = []
                params: list = []
                if ev.model:
                    updates.append("model = CASE WHEN model IS NULL THEN ? ELSE model END")
                    params.append(ev.model)
                if ev.outcome and ev.outcome != "unknown":
                    updates.append("outcome = CASE WHEN outcome = 'unknown' THEN ? ELSE outcome END")
                    params.append(ev.outcome)
                if updates:
                    params.append(ev.source)
                    cur.execute(
                        f"UPDATE agent_events SET {', '.join(updates)} WHERE source=?",
                        params,
                    )
        self._con.commit()
        return inserted

    def maybe_record_agent_pid(self, pid: int, ts: int, cmd: str) -> bool:
        try:
            self._con.execute(
                "INSERT INTO seen_agent_pids(pid, first_seen_ts, cmd) VALUES (?,?,?)",
                (pid, ts, cmd[:500]),
            )
            self._con.commit()
            return True
        except sqlite3.IntegrityError:
            return False

    def get_log_offset(self, path: str) -> int:
        cur = self._con.cursor()
        cur.execute("SELECT offset FROM log_offsets WHERE path=?", (path,))
        row = cur.fetchone()
        return int(row[0]) if row else 0

    def set_log_offset(self, path: str, offset: int) -> None:
        self._con.execute(
            "INSERT INTO log_offsets(path, offset) VALUES (?,?) ON CONFLICT(path) DO UPDATE SET offset=excluded.offset",
            (path, int(offset)),
        )
        self._con.commit()

    def total_spawned(self) -> int:
        cur = self._con.cursor()
        cur.execute("SELECT COUNT(*) FROM agent_events")
        return int(cur.fetchone()[0])

    def recent_agent_events(self, limit: int = 18) -> List[Tuple[int, str, Optional[str], Optional[str]]]:
        cur = self._con.cursor()
        cur.execute(
            "SELECT ts, agent_type, name, model FROM agent_events ORDER BY ts DESC, id DESC LIMIT ?",
            (limit,),
        )
        return [(int(r[0]), str(r[1]), r[2], r[3]) for r in cur.fetchall()]

    def agent_events_count_since(self, since_ts: int) -> int:
        cur = self._con.cursor()
        cur.execute("SELECT COUNT(*) FROM agent_events WHERE ts>=?", (since_ts,))
        return int(cur.fetchone()[0])

    def agent_events_by_type_since(self, since_ts: int) -> Dict[str, int]:
        cur = self._con.cursor()
        cur.execute("SELECT agent_type, COUNT(*) FROM agent_events WHERE ts>=? GROUP BY agent_type", (since_ts,))
        return {str(k): int(v) for k, v in cur.fetchall()}

    def agent_events_by_level_since(self, since_ts: int) -> Dict[str, int]:
        cur = self._con.cursor()
        cur.execute(
            "SELECT agent_type, name, COUNT(*) FROM agent_events WHERE ts>=? GROUP BY agent_type, name",
            (since_ts,),
        )
        counts = empty_level_counts()
        for agent_type, name, count in cur.fetchall():
            level = classify_agent_level(str(agent_type), name)
            counts[level] = counts.get(level, 0) + int(count)
        return counts

    def series_snapshots(self, seconds: int = 240, step: int = 1) -> List[Tuple[int, int, int]]:
        since = now_ts() - seconds
        cur = self._con.cursor()
        cur.execute(
            "SELECT ts, active_sessions, agent_events_last5m FROM snapshots WHERE ts>=? ORDER BY ts ASC",
            (since,),
        )
        rows = [(int(r[0]), int(r[1]), int(r[2])) for r in cur.fetchall()]
        if not rows:
            return []

        out: List[Tuple[int, int, int]] = []
        row_i = 0
        for t in range(since, now_ts() + 1, step):
            while row_i + 1 < len(rows) and rows[row_i + 1][0] <= t:
                row_i += 1
            out.append((t, rows[row_i][1], rows[row_i][2]))
        return out

    def hourly_activity_24h(self) -> List[int]:
        """Return 24 buckets (one per hour) of combined activity for last 24h.

        Merges agent events and session snapshot activity so the heatmap
        lights up whenever there was any Copilot CLI usage, not just agent launches.
        """
        now = now_ts()
        start = now - 24 * 3600
        cur = self._con.cursor()

        # Agent events
        buckets = [0] * 24
        cur.execute("SELECT ts FROM agent_events WHERE ts>=?", (start,))
        for (ts,) in cur.fetchall():
            hour_idx = min(23, (int(ts) - start) // 3600)
            buckets[hour_idx] += 1

        # Session snapshots (count snapshots with active sessions)
        cur.execute("SELECT ts, active_sessions FROM snapshots WHERE ts>=? AND active_sessions > 0", (start,))
        for ts, sessions in cur.fetchall():
            hour_idx = min(23, (int(ts) - start) // 3600)
            buckets[hour_idx] += int(sessions)

        return buckets

    def daily_activity_14d(self) -> List[int]:
        """Return 14 buckets (one per day) of agent event counts for last 14 days."""
        now = now_ts()
        start = now - 14 * 24 * 3600
        cur = self._con.cursor()
        cur.execute("SELECT ts FROM agent_events WHERE ts>=?", (start,))
        buckets = [0] * 14
        for (ts,) in cur.fetchall():
            day_idx = min(13, (int(ts) - start) // (24 * 3600))
            buckets[day_idx] += 1
        return buckets

    def daily_sessions_14d(self) -> List[int]:
        """Return 14 buckets of peak active sessions per day for last 14 days."""
        now = now_ts()
        start = now - 14 * 24 * 3600
        cur = self._con.cursor()
        cur.execute("SELECT ts, active_sessions FROM snapshots WHERE ts>=?", (start,))
        buckets = [0] * 14
        for ts, sessions in cur.fetchall():
            day_idx = min(13, (int(ts) - start) // (24 * 3600))
            buckets[day_idx] = max(buckets[day_idx], int(sessions))
        return buckets

    def peak_sessions_since(self, since_ts: int) -> int:
        """Return peak active sessions since a given timestamp."""
        cur = self._con.cursor()
        cur.execute("SELECT MAX(active_sessions) FROM snapshots WHERE ts>=?", (since_ts,))
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def unique_sessions_since(self, since_ts: int) -> int:
        """Estimate unique session count from snapshots (sum of peak per distinct hour)."""
        cur = self._con.cursor()
        cur.execute(
            "SELECT COUNT(DISTINCT CAST(ts / 3600 AS INTEGER)) FROM snapshots WHERE ts>=? AND active_sessions > 0",
            (since_ts,),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    # Feature 1: Success rate tracking
    def success_rate_since(self, since_ts: int) -> Tuple[int, int, int]:
        """Return (success_count, fail_count, total) since timestamp."""
        cur = self._con.cursor()
        cur.execute(
            "SELECT outcome, COUNT(*) FROM agent_events WHERE ts>=? AND outcome != 'unknown' GROUP BY outcome",
            (since_ts,),
        )
        counts: Dict[str, int] = {}
        for outcome, cnt in cur.fetchall():
            counts[str(outcome)] = int(cnt)
        success = counts.get("success", 0)
        fail = counts.get("failure", 0)
        total = success + fail
        return (success, fail, total)

    def running_subagents_since(self, since_ts: int) -> int:
        """Count sub-agent events launched since since_ts that have not yet completed.

        A sub-agent is 'running' if its row in agent_events still has outcome='unknown'
        (i.e. we have not yet observed a tool.execution_complete for it) and it was
        started recently enough that it is plausibly still in flight.
        """
        cur = self._con.cursor()
        cur.execute(
            "SELECT COUNT(*) FROM agent_events WHERE ts>=? AND outcome = 'unknown' AND agent_type NOT LIKE 'metaswarm-%'",
            (since_ts,),
        )
        row = cur.fetchone()
        return int(row[0]) if row and row[0] is not None else 0

    def running_agent_events_since(self, since_ts: int, limit: int = 500) -> List[Tuple[int, str, Optional[str], Optional[str]]]:
        """Return recent event-stream agents that still look in-flight."""
        cur = self._con.cursor()
        cur.execute(
            """
            SELECT ts, agent_type, name, model
            FROM agent_events
            WHERE ts>=? AND outcome = 'unknown' AND agent_type NOT LIKE 'metaswarm-%'
            ORDER BY ts DESC, id DESC
            LIMIT ?
            """,
            (since_ts, limit),
        )
        return [(int(r[0]), str(r[1]), r[2], r[3]) for r in cur.fetchall()]

    # Feature 2: Model distribution
    def model_distribution_since(self, since_ts: int) -> Dict[str, int]:
        """Return model->count for events since timestamp."""
        cur = self._con.cursor()
        cur.execute(
            "SELECT model, COUNT(*) FROM agent_events WHERE ts>=? AND model IS NOT NULL GROUP BY model",
            (since_ts,),
        )
        return {str(k): int(v) for k, v in cur.fetchall()}

    # Feature 3: Token usage
    def insert_token_usage(self, ts: int, model: Optional[str], input_tokens: int, output_tokens: int, source: str) -> None:
        try:
            self._con.execute(
                "INSERT INTO token_usage(ts, model, input_tokens, output_tokens, source) VALUES (?,?,?,?,?)",
                (ts, model, input_tokens, output_tokens, source),
            )
            self._con.commit()
        except sqlite3.IntegrityError:
            pass

    def token_totals_since(self, since_ts: int) -> Tuple[int, int]:
        """Return (input_total, output_total) since timestamp."""
        cur = self._con.cursor()
        cur.execute(
            "SELECT COALESCE(SUM(input_tokens),0), COALESCE(SUM(output_tokens),0) FROM token_usage WHERE ts>=?",
            (since_ts,),
        )
        row = cur.fetchone()
        return (int(row[0]), int(row[1]))

    def token_hourly_24h(self) -> List[int]:
        """Return 24 buckets of total tokens per hour for last 24h."""
        now = now_ts()
        start = now - 24 * 3600
        cur = self._con.cursor()
        cur.execute("SELECT ts, input_tokens + output_tokens FROM token_usage WHERE ts>=?", (start,))
        buckets = [0] * 24
        for ts_val, total in cur.fetchall():
            hour_idx = min(23, (int(ts_val) - start) // 3600)
            buckets[hour_idx] += int(total)
        return buckets


# ----------------------------
# Metrics
# ----------------------------

@dataclass
class ActiveSession:
    session_id: str
    pid: int
    tty: str
    agent_type: str
    status: str
    started_at: float


@dataclass
class PulseMetrics:
    active_sessions: int
    sessions_by_tty: Dict[str, int]
    running_agents_est: int
    agent_events_last5m: int
    spawned_all_time: int
    spawned_today: int
    spawned_week: int
    spawned_month: int
    spawned_by_type_24h: Dict[str, int]
    recent_events: List[Tuple[int, str, Optional[str], Optional[str]]]
    velocity: float = 0.0
    peak_velocity: float = 0.0
    active_session_list: List[ActiveSession] = None
    sessions_today: int = 0
    sessions_week: int = 0
    sessions_month: int = 0
    peak_sessions_today: int = 0
    # Feature 1: Success/failure rate
    success_rate_24h: float = 0.0
    error_count_24h: int = 0
    # Feature 2: Model distribution
    model_dist_24h: Dict[str, int] = None
    # Feature 3: Token usage
    tokens_today: int = 0
    # Feature 4: Fleet health score
    health_score: int = 100
    # Real-time sub-agent tracking
    running_subagents: int = 0
    subagents_last5m: int = 0
    total_live_agents: int = 0
    live_level_counts: Dict[str, int] = None
    launch_level_counts_5m: Dict[str, int] = None
    metaswarm_runs: List[MetaswarmRun] = None
    metaswarm_active_commanders: int = 0
    metaswarm_children_running: int = 0
    metaswarm_children_last5m: int = 0
    metaswarm_children_seen: int = 0
    metaswarm_children_stale: int = 0
    live_agents: List[LiveAgent] = None

    def __post_init__(self):
        if self.active_session_list is None:
            self.active_session_list = []
        if self.model_dist_24h is None:
            self.model_dist_24h = {}
        if self.live_level_counts is None:
            self.live_level_counts = empty_level_counts()
        if self.launch_level_counts_5m is None:
            self.launch_level_counts_5m = empty_level_counts()
        if self.metaswarm_runs is None:
            self.metaswarm_runs = []
        if self.live_agents is None:
            self.live_agents = []


class MetricsEngine:
    def __init__(self, store: PulseStore) -> None:
        self.store = store
        self.procs = ProcessCollector()
        self.tmux = TmuxPaneCollector()
        self.logs = CopilotLogTailer(store)
        self.events = SessionEventTailer(store)
        self.stampede = StampedeTelemetryCollector(store)
        self._peak_velocity: float = 0.0
        self._started_at: float = time.time()
        self._session_start_times: Dict[str, float] = {}
        self._process_start_times: Dict[int, float] = {}

    @staticmethod
    def _agent_type_from_cmd(cmd: str) -> str:
        lower = cmd.lower()
        for t in AGENT_TYPES:
            if t in lower:
                return t
        if "copilot" in lower:
            return "copilot"
        return "process"

    @staticmethod
    def _model_from_cmd(cmd: str) -> Optional[str]:
        match = re.search(r"(?:--model(?:=|\s+))([A-Za-z0-9._/-]+)", cmd)
        if match:
            return match.group(1)
        return None

    def _live_from_processes(self, procs: List[Proc], ts: int) -> List[LiveAgent]:
        live: List[LiveAgent] = []
        current_pids = {p.pid for p in procs}
        for old_pid in list(self._process_start_times):
            if old_pid not in current_pids:
                self._process_start_times.pop(old_pid, None)

        for p in procs:
            if not (self.procs.is_copilot_process(p.cmd) or self.procs.is_agentish_process(p.cmd)):
                continue
            if p.pid not in self._process_start_times:
                self._process_start_times[p.pid] = time.time()
            live.append(
                LiveAgent(
                    source="process",
                    agent_id=f"pid-{p.pid}",
                    agent_type=self._agent_type_from_cmd(p.cmd),
                    name=p.cmd[:80],
                    status="RUN",
                    age_s=max(0, int(time.time() - self._process_start_times[p.pid])),
                    model=self._model_from_cmd(p.cmd),
                    pid=p.pid,
                    parent=f"tty:{p.tty}",
                )
            )
        return live

    def poll(self) -> PulseMetrics:
        ts = now_ts()

        # Process-derived snapshot
        procs = self.procs.collect()
        sessions_by_tty: Dict[str, int] = {}
        running_agents_est = 0
        active_session_list: List[ActiveSession] = []
        seen_ttys: set = set()

        for p in procs:
            if self.procs.is_copilot_process(p.cmd) and p.tty not in ("?", "??"):
                sessions_by_tty[p.tty] = sessions_by_tty.get(p.tty, 0) + 1
                if p.tty not in seen_ttys:
                    seen_ttys.add(p.tty)
                    sid = f"sess_{p.tty[-4:].replace('/', '')}"
                    if sid not in self._session_start_times:
                        self._session_start_times[sid] = time.time()
                    # Guess agent type from command
                    atype = "copilot"
                    for t in AGENT_TYPES:
                        if t in p.cmd.lower():
                            atype = t
                            break
                    active_session_list.append(ActiveSession(
                        session_id=sid, pid=p.pid, tty=p.tty,
                        agent_type=atype, status="RUN",
                        started_at=self._session_start_times[sid],
                    ))

            if self.procs.is_agentish_process(p.cmd):
                running_agents_est += 1
                self.store.maybe_record_agent_pid(p.pid, ts, p.cmd)

        active_sessions = len(sessions_by_tty)

        # Log-derived agent launches
        self.logs.poll_new_events()
        # Session events.jsonl — the primary source of agent launches
        self.events.poll_new_events()
        # Terminal Stampede metaswarm ledgers — source of truth for nested children.
        metaswarm_runs = self.stampede.poll()

        agent_events_last5m = self.store.agent_events_count_since(ts - 5 * 60)
        spawned_all_time = self.store.total_spawned()

        # Rolling windows (more useful in a live dashboard than strict calendar buckets)
        spawned_today = self.store.agent_events_count_since(ts - 24 * 3600)
        spawned_week = self.store.agent_events_count_since(ts - 7 * 24 * 3600)
        spawned_month = self.store.agent_events_count_since(ts - 30 * 24 * 3600)

        spawned_by_type_24h = self.store.agent_events_by_type_since(ts - 24 * 3600)
        recent_events = self.store.recent_agent_events(limit=18)

        # Velocity: agents launched per hour over last hour
        spawned_last_hour = self.store.agent_events_count_since(ts - 3600)
        elapsed_hours = min(1.0, (time.time() - self._started_at) / 3600) or 1.0
        velocity = round(spawned_last_hour / elapsed_hours, 1) if elapsed_hours > 0 else 0.0
        if velocity > self._peak_velocity:
            self._peak_velocity = velocity

        # Session counts
        sessions_today = self.store.unique_sessions_since(ts - 24 * 3600)
        sessions_week = self.store.unique_sessions_since(ts - 7 * 24 * 3600)
        sessions_month = self.store.unique_sessions_since(ts - 30 * 24 * 3600)
        peak_sessions_today = self.store.peak_sessions_since(ts - 24 * 3600)

        self.store.insert_snapshot(
            ts=ts,
            active_sessions=active_sessions,
            running_agents_est=running_agents_est,
            agent_events_last5m=agent_events_last5m,
            notes={"sessions_by_tty": sessions_by_tty, "running_agents_est": running_agents_est},
        )

        # Real-time live-run counts. Event-stream rows without completion stay
        # visible long enough for deep swarms, while process/tmux/ledger signals
        # remain the preferred sources for long-lived runs.
        running_subagents_from_events = self.store.running_subagents_since(ts - LIVE_EVENT_WINDOW_S)
        def commander_is_active(c: MetaswarmCommander) -> bool:
            if c.pid_status == "run":
                return True
            if c.pid_status == "dead":
                return False
            return c.status in {"running", "starting"} and (c.heartbeat_age_s is None or c.heartbeat_age_s < 90)

        metaswarm_children_running = sum(
            c.child_agents_running or c.workers_running
            for run in metaswarm_runs
            for c in run.commanders
            if commander_is_active(c)
        )
        metaswarm_children_seen = sum(
            c.child_agents_seen
            for run in metaswarm_runs
            for c in run.commanders
        )
        metaswarm_children_stale = sum(
            c.child_agents_stale
            for run in metaswarm_runs
            for c in run.commanders
        )
        metaswarm_active_commanders = sum(
            1
            for run in metaswarm_runs
            for c in run.commanders
            if commander_is_active(c)
        )
        metaswarm_type_counts = self.store.agent_events_by_type_since(ts - 5 * 60)
        metaswarm_children_last5m = sum(
            count
            for agent_type, count in metaswarm_type_counts.items()
            if agent_type.startswith("metaswarm-") and agent_type != "metaswarm-swarm"
        )

        live_agents: List[LiveAgent] = []
        live_agents.extend(self._live_from_processes(procs, ts))
        live_agents.extend(self.tmux.collect())
        live_agents.extend(self.stampede.live_agents(metaswarm_runs))
        for ev_ts, ev_type, ev_name, ev_model in self.store.running_agent_events_since(
            ts - LIVE_EVENT_WINDOW_S,
            limit=500,
        ):
            if ev_type.startswith("metaswarm-"):
                continue
            live_agents.append(
                LiveAgent(
                    source="event",
                    agent_id=f"event:{ev_type}:{ev_name or ev_ts}:{ev_ts}",
                    agent_type=ev_type,
                    name=ev_name or ev_type,
                    status="IN-FLIGHT",
                    age_s=max(0, ts - ev_ts),
                    model=ev_model,
                )
            )

        deduped_live: Dict[Tuple[str, str], LiveAgent] = {}
        for item in live_agents:
            key = (item.source, item.agent_id)
            existing = deduped_live.get(key)
            if existing is None or (existing.status != "RUN" and item.status == "RUN"):
                deduped_live[key] = item
        def live_rank(a: LiveAgent) -> Tuple[int, int, str, str]:
            status = a.status.upper()
            if a.agent_type == "metaswarm-swarm":
                rank = -1
            elif status in {"RUN", "IN-FLIGHT"}:
                rank = 0
            elif "DEAD" in status or "FAIL" in status:
                rank = 1
            elif status == "STALE":
                rank = 2
            elif status in {"DONE", "SUCCESS"}:
                rank = 3
            else:
                rank = 4
            return (rank, a.age_s, a.source, a.agent_id)

        all_live_agents = sorted(
            deduped_live.values(),
            key=live_rank,
        )
        live_level_counts = count_agent_levels(all_live_agents, running_only=True)
        total_live_agents = sum(live_level_counts.values())
        live_agents = all_live_agents[:80]
        live_running_count = sum(
            1
            for a in all_live_agents
            if a.status in {"RUN", "IN-FLIGHT"} and a.agent_type != "stampede-monitor"
        )

        # Combine filesystem, process, and event signals; take max so we never under-count.
        running_subagents = max(
            running_subagents_from_events,
            running_agents_est,
            metaswarm_children_running,
            live_running_count,
            total_live_agents,
        )
        subagents_last5m = agent_events_last5m
        launch_level_counts_5m = self.store.agent_events_by_level_since(ts - 5 * 60)

        # Feature 1: Success rate
        success_count, fail_count, rate_total = self.store.success_rate_since(ts - 24 * 3600)
        success_rate_24h = round(success_count / rate_total, 3) if rate_total > 0 else 0.0
        error_count_24h = fail_count

        # Feature 2: Model distribution
        model_dist_24h = self.store.model_distribution_since(ts - 24 * 3600)

        # Feature 3: Token usage
        input_tok, output_tok = self.store.token_totals_since(ts - 24 * 3600)
        tokens_today = input_tok + output_tok

        # Feature 4: Health score
        health_score = 100
        if rate_total > 0:
            health_score -= int(40 * (1.0 - success_rate_24h))
        if spawned_today == 0:
            health_score -= 15
        if active_sessions > 0 and running_agents_est == 0:
            health_score -= 15
        _, errors_1h, _ = self.store.success_rate_since(ts - 3600)
        health_score -= min(30, errors_1h * 6)
        health_score = int(clamp(health_score, 0, 100))

        return PulseMetrics(
            active_sessions=active_sessions,
            sessions_by_tty=sessions_by_tty,
            running_agents_est=running_agents_est,
            agent_events_last5m=agent_events_last5m,
            spawned_all_time=spawned_all_time,
            spawned_today=spawned_today,
            spawned_week=spawned_week,
            spawned_month=spawned_month,
            spawned_by_type_24h=spawned_by_type_24h,
            recent_events=recent_events,
            velocity=velocity,
            peak_velocity=self._peak_velocity,
            active_session_list=active_session_list,
            sessions_today=sessions_today,
            sessions_week=sessions_week,
            sessions_month=sessions_month,
            peak_sessions_today=peak_sessions_today,
            success_rate_24h=success_rate_24h,
            error_count_24h=error_count_24h,
            model_dist_24h=model_dist_24h,
            tokens_today=tokens_today,
            health_score=health_score,
            running_subagents=running_subagents,
            subagents_last5m=subagents_last5m,
            total_live_agents=total_live_agents,
            live_level_counts=live_level_counts,
            launch_level_counts_5m=launch_level_counts_5m,
            metaswarm_runs=metaswarm_runs,
            metaswarm_active_commanders=metaswarm_active_commanders,
            metaswarm_children_running=metaswarm_children_running,
            metaswarm_children_last5m=metaswarm_children_last5m,
            metaswarm_children_seen=metaswarm_children_seen,
            metaswarm_children_stale=metaswarm_children_stale,
            live_agents=live_agents,
        )


# ----------------------------
# Textual Widgets
# ----------------------------

class NeonLogo(Static):
    metrics: Optional[PulseMetrics] = reactive(None)
    tick: int = reactive(0)

    def __init__(self, **kwargs) -> None:
        super().__init__(**kwargs)
        self._started_at = time.time()
        self._pid = __import__("os").getpid()

    def render(self) -> Panel:
        # Use compact logo when terminal is narrow
        try:
            width = self.app.size.width
        except Exception:
            width = 120
        if width < 100:
            logo = Text(ASCII_LOGO_COMPACT, style="bold white")
        else:
            logo = Text(ASCII_LOGO, style="bold white")
        tagline = Text("⚡ for GitHub Copilot CLI", style="bold #FF4D6D")

        m = self.metrics
        heart = _HEARTBEATS[self.tick % len(_HEARTBEATS)]
        if m:
            levels = m.live_level_counts or empty_level_counts()
            division_commanders = levels.get("division_commanders", 0)
            commanders = levels.get("commanders", 0)
            sessions = m.active_sessions
            metrics_line_1 = Text.assemble(
                (f"  {heart}  ", ""),
                ("total agents ", "#8D99AE"),
                (str(m.spawned_all_time), "bold #FFD166"),
                (" · live agents ", "#8D99AE"),
                (str(m.total_live_agents), "bold #00F5D4"),
                (" · live sub-agents ", "#8D99AE"),
                (str(m.running_subagents), "bold #7CFF6B"),
                (" · sessions ", "#8D99AE"),
                (str(sessions), "bold #00D1FF"),
            )
            metrics_line_2 = Text.assemble(
                ("div ", "#8D99AE"),
                (str(division_commanders), "bold #B388FF"),
                (" · cmd ", "#8D99AE"),
                (str(commanders), "bold #00F5D4"),
                (" · squads ", "#8D99AE"),
                (str(levels.get("squad_leads", 0)), "bold #FFD166"),
                (" · sub-agents ", "#8D99AE"),
                (str(levels.get("workers", 0)), "bold #7CFF6B"),
                (" · reviewers ", "#8D99AE"),
                (str(levels.get("reviewers", 0)), "bold #FF4D6D"),
                (" · other ", "#8D99AE"),
                (str(levels.get("other", 0)), "bold #8D99AE"),
            )
            metrics_line_3 = Text.assemble(
                ("launches 5m ", "#8D99AE"),
                (str(m.subagents_last5m), "bold #00F5D4"),
                (" · velocity ", "#8D99AE"),
                (f"{m.velocity}/hr", "bold #FFD166"),
                (" · peak ", "#8D99AE"),
                (f"{m.peak_velocity}/hr", "bold #FFD166"),
                (" · launches today ", "#8D99AE"),
                (str(m.spawned_today), "bold #FF4D6D"),
            )
        else:
            metrics_line_1 = Text(f"  {heart}  Initializing…", style="#8D99AE")
            metrics_line_2 = Text("")
            metrics_line_3 = Text("")

        elapsed = int(time.time() - self._started_at)
        h, rem = divmod(elapsed, 3600)
        mi, s = divmod(rem, 60)
        uptime = f"{h:02d}:{mi:02d}:{s:02d}"
        version_line = Text.assemble(
            (f"AGENT PULSE v{VERSION}", "#8D99AE"),
            ("  |  ", "#555"),
            ("uptime: ", "#8D99AE"),
            (uptime, "bold #FFD166"),
            ("  |  ", "#555"),
            ("pid: ", "#8D99AE"),
            (str(self._pid), "bold #00D1FF"),
        )

        return Panel(
            Group(
                Align.center(logo),
                Align.center(tagline),
                Align.center(metrics_line_1),
                Align.center(metrics_line_2),
                Align.center(metrics_line_3),
                Align.center(version_line),
            ),
            border_style="#00D1FF",
            padding=(0, 2),
        )


class StatPanel(Static):
    metrics: Optional[PulseMetrics] = reactive(None)
    tick: int = reactive(0)

    def render(self) -> Panel:
        m = self.metrics
        if not m:
            return Panel("Initializing…", border_style="#00D1FF", title="[bold #00D1FF]● LIVE METRICS[/]")

        lamp_color = "green" if m.active_sessions > 0 else "yellow"
        lamp = Text("●", style=f"bold {lamp_color}")
        spinner = "⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏"[self.tick % 10]

        def bar(val: int, max_val: int = 20, width: int = 16) -> Text:
            filled = int(round((val / max(max_val, 1)) * width))
            filled = max(0, min(width, filled))
            return Text("█" * filled + "░" * (width - filled), style="bold #7CFF6B")

        t = Table.grid(padding=(0, 2))
        t.add_column(justify="left")
        t.add_column(justify="right")
        t.add_column(justify="left")
        levels = m.live_level_counts or empty_level_counts()
        division_commanders = levels.get("division_commanders", 0)
        commanders = levels.get("commanders", 0)
        t.add_row(
            Text("Sessions        :", style="bold white"),
            Text(str(m.active_sessions), style="bold #7CFF6B"),
            bar(m.active_sessions),
        )
        t.add_row(
            Text("All live agents :", style="bold white"),
            Text(str(m.total_live_agents), style="bold #B388FF"),
            bar(m.total_live_agents),
        )
        t.add_row(
            Text("Division cmds   :", style="bold white"),
            Text(str(division_commanders), style="bold #B388FF"),
            bar(division_commanders),
        )
        t.add_row(
            Text("Commanders      :", style="bold white"),
            Text(str(commanders), style="bold #00F5D4"),
            bar(commanders),
        )
        t.add_row(
            Text("Squad leads     :", style="bold white"),
            Text(str(levels.get("squad_leads", 0)), style="bold #FFD166"),
            bar(levels.get("squad_leads", 0)),
        )
        t.add_row(
            Text("Sub-agents      :", style="bold white"),
            Text(str(levels.get("workers", 0)), style="bold #7CFF6B"),
            bar(levels.get("workers", 0)),
        )
        t.add_row(
            Text("Reviewers       :", style="bold white"),
            Text(str(levels.get("reviewers", 0)), style="bold #FF4D6D"),
            bar(levels.get("reviewers", 0)),
        )
        t.add_row(
            Text("Other           :", style="bold white"),
            Text(str(levels.get("other", 0)), style="bold #8D99AE"),
            bar(levels.get("other", 0)),
        )
        t.add_row(
            Text("Launch events 5m:", style="bold white"),
            Text(str(m.subagents_last5m), style="bold #00F5D4"),
            bar(m.subagents_last5m),
        )
        t.add_row(
            Text("Velocity         :", style="bold white"),
            Text(f"{m.velocity}/hr", style="bold #FFD166"),
            Text(f"peak: {m.peak_velocity}/hr", style="#8D99AE"),
        )
        trend = "▲ trending up" if m.spawned_today > 0 else "—"
        t.add_row(
            Text("Launches today  :", style="bold white"),
            Text(str(m.spawned_today), style="bold #FF4D6D"),
            Text(trend, style="#8D99AE"),
        )

        status_line = Text.assemble(
            spinner, " ", ("LIVE", "bold #00F5D4"), "  ", lamp, "  ", ("PULSE LOCK", "bold #8D99AE")
        )
        return Panel(Group(t, "", status_line), border_style="#00D1FF", title="[bold #00D1FF]● LIVE METRICS[/]")


class HistoryPanel(Static):
    """14-day trend analysis with sparklines and daily breakdowns."""
    metrics: Optional[PulseMetrics] = reactive(None)

    def __init__(self, store: PulseStore, **kwargs) -> None:
        super().__init__(**kwargs)
        self.store = store

    def render(self) -> Panel:
        m = self.metrics
        if not m:
            return Panel("…", border_style="#FF4D6D", title="[bold #00D1FF]📊 TREND ANALYSIS[/]")

        # 14-day sparklines
        daily_agents = self.store.daily_activity_14d()
        daily_sessions = self.store.daily_sessions_14d()

        t = Table.grid(padding=(0, 1))
        t.add_column(justify="left", min_width=12)
        t.add_column(justify="right", width=6)
        t.add_column(justify="right", width=6)
        t.add_column(justify="right", width=6)

        # Header
        t.add_row(
            Text("", style=""),
            Text("24h", style="bold #8D99AE"),
            Text("7d", style="bold #8D99AE"),
            Text("30d", style="bold #8D99AE"),
        )
        # Agents row (top-level sessions) + launch-event row (task-tool launches).
        t.add_row(
            Text("Sessions", style="bold #00D1FF"),
            Text(str(m.sessions_today), style="bold #FFD166"),
            Text(str(m.sessions_week), style="bold #00F5D4"),
            Text(str(m.sessions_month), style="bold #B388FF"),
        )
        t.add_row(
            Text("Launches", style="bold #7CFF6B"),
            Text(str(m.spawned_today), style="bold #FFD166"),
            Text(str(m.spawned_week), style="bold #00F5D4"),
            Text(str(m.spawned_month), style="bold #B388FF"),
        )
        t.add_row(Text(""), Text(""), Text(""), Text(""))

        # Sparklines
        t2 = Table.grid(padding=(0, 2))
        t2.add_column(justify="left")
        t2.add_column(justify="left")
        t2.add_row(
            Text("14d launches  ", style="bold #7CFF6B"),
            Text(sparkline(daily_agents, width=14), style="#7CFF6B"),
        )
        t2.add_row(
            Text("14d sessions  ", style="bold #00D1FF"),
            Text(sparkline(daily_sessions, width=14), style="#00D1FF"),
        )

        # Trend arrow
        if len(daily_agents) >= 2 and daily_agents[-1] > daily_agents[-2]:
            trend = Text("  ▲ trending up", style="bold #7CFF6B")
        elif len(daily_agents) >= 2 and daily_agents[-1] < daily_agents[-2]:
            trend = Text("  ▼ trending down", style="bold #FF4D6D")
        else:
            trend = Text("  ► steady", style="#8D99AE")

        all_time = Text.assemble(("All-time: ", "#8D99AE"), (str(m.spawned_all_time), "bold #00D1FF"), (" launch events", "#8D99AE"))

        return Panel(Group(t, t2, trend, all_time), border_style="#FF4D6D", title="[bold #00D1FF]📊 TREND ANALYSIS[/]")


class MixPanel(Static):
    metrics: Optional[PulseMetrics] = reactive(None)

    def render(self) -> Panel:
        m = self.metrics
        if not m:
            return Panel("…", border_style="#7CFF6B", title="[bold #FFD166]◆ LAUNCH EVENT BREAKDOWN[/]")

        by_type = dict(m.spawned_by_type_24h)
        total_24h = sum(by_type.values())
        title = (
            f"[bold #FFD166]◆ LAUNCH EVENT BREAKDOWN[/]  "
            f"[#8D99AE]· live runs[/] [bold #B388FF]{m.running_subagents}[/]  "
            f"[#8D99AE]· 24h events[/] [bold #FFD166]{total_24h}[/]"
        )
        if not by_type:
            body = Text("No launch events observed yet.\n(Leave Agent Pulse running.)", style="#8D99AE")
            return Panel(body, border_style="#7CFF6B", title=title)

        total = max(total_24h, 1)
        maxv = max(by_type.values())
        type_icons = {
            "explore": "⚡", "task": "⚙", "general-purpose": "●",
            "code-review": "🔍", "rubber-duck": "🦆",
            "metaswarm-sub-agent": "◆", "metaswarm-worker": "◆",
        }

        table = Table.grid(padding=(0, 1))
        table.add_column("icon", justify="left", width=2)
        table.add_column("type", justify="left", min_width=18)
        table.add_column("n", justify="right", width=4)
        table.add_column("pct", justify="right", width=6)
        table.add_column("bar", justify="left")

        def bar(n: int, width: int = 16) -> Text:
            filled = int(round((n / maxv) * width))
            filled = max(0, min(width, filled))
            return Text("█" * filled + "░" * (width - filled))

        for k in sorted(by_type.keys(), key=lambda x: (-by_type[x], x)):
            color = TYPE_COLOR.get(k, TYPE_COLOR["custom"])
            pct = round(100 * by_type[k] / total)
            icon = type_icons.get(k, "●")
            table.add_row(
                Text(icon, style=color),
                Text(display_agent_type(k), style=f"bold {color}"),
                Text(str(by_type[k]), style=f"bold {color}"),
                Text(f"({pct:2d}%)", style="#8D99AE"),
                bar(by_type[k]).stylize(color),
            )

        return Panel(table, border_style="#7CFF6B", title=title)


class SignalPanel(Static):
    def __init__(self, store: PulseStore, **kwargs) -> None:
        super().__init__(**kwargs)
        self.store = store

    def render(self) -> Panel:
        heat_chars = " ░▒▓█"

        # 24h activity heatmap
        hourly = self.store.hourly_activity_24h()
        max_h = max(max(hourly), 1)
        heatmap = Text()
        for h_val in hourly:
            idx = min(4, int((h_val / max_h) * 4))
            color = ["#1a1a2e", "#2d6a4f", "#52b788", "#FFD166", "#FF4D6D"][idx]
            heatmap.append(heat_chars[idx], style=f"bold {color}")

        # Real-time signal sparklines
        series = self.store.series_snapshots(seconds=240)
        if series:
            sessions = [float(r[1]) for r in series]
            launches = [float(r[2]) for r in series]
        else:
            sessions = [0]
            launches = [0]

        grid = Table.grid(padding=(0, 1))
        grid.add_column(justify="left")
        grid.add_column(justify="left")

        grid.add_row(
            Text("🔥 24h heatmap", style="bold #FF4D6D"),
            heatmap,
        )
        grid.add_row(
            Text("", style="#8D99AE"),
            Text("0h          12h         23h", style="#555"),
        )
        grid.add_row(Text("", style=""), Text("", style=""))
        grid.add_row(
            Text("sessions   ", style="bold #7CFF6B"),
            Text(sparkline(sessions, width=24), style="#7CFF6B"),
        )
        grid.add_row(
            Text("launches(5m)", style="bold #FFD166"),
            Text(sparkline(launches, width=24), style="#FFD166"),
        )
        return Panel(grid, border_style="#B388FF", title="[bold #FF4D6D]🔥 HEATMAP + SIGNAL[/]")


class RecentTable(DataTable):
    def on_mount(self) -> None:
        self.add_columns("AGE", "TYPE", "NAME", "MODEL")
        self.zebra_stripes = True
        self.show_cursor = False

    def update_rows(self, rows: List[Tuple[int, str, Optional[str], Optional[str]]]) -> None:
        self.clear()
        now = now_ts()
        for ts, typ, name, model in rows:
            age = human_age(max(0, now - ts))
            color = TYPE_COLOR.get(typ, TYPE_COLOR["custom"])
            self.add_row(
                Text(age, style="#8D99AE"),
                Text(typ, style=f"bold {color}"),
                Text(name or "—", style="#C7F9CC" if name else "#8D99AE"),
                Text(model or "—", style="#8D99AE"),
            )


class ActiveSessionsPanel(Static):
    metrics: Optional[PulseMetrics] = reactive(None)

    def render(self) -> Panel:
        m = self.metrics
        if not m or not m.active_session_list:
            return Panel(
                Text("No active sessions detected", style="#8D99AE"),
                border_style="#00ff87",
                title="[bold #00ff87]▶ ACTIVE SESSIONS[/]",
            )

        t = Table.grid(padding=(0, 2))
        t.add_column("sid", justify="left", min_width=12)
        t.add_column("pid", justify="right", width=7)
        t.add_column("type", justify="left", min_width=18)
        t.add_column("status", justify="center", width=8)
        t.add_column("runtime", justify="right", width=8)

        t.add_row(
            Text("SESSION-ID", style="bold #8D99AE"),
            Text("PID", style="bold #8D99AE"),
            Text("TYPE", style="bold #8D99AE"),
            Text("STATUS", style="bold #8D99AE"),
            Text("RUNTIME", style="bold #8D99AE"),
        )

        now = time.time()
        for s in m.active_session_list[:8]:
            elapsed = int(now - s.started_at)
            mi, sec = divmod(elapsed, 60)
            runtime = f"{mi:02d}:{sec:02d}"
            color = TYPE_COLOR.get(s.agent_type, TYPE_COLOR["custom"])
            status_color = "#7CFF6B" if s.status == "RUN" else "#FFD166"
            t.add_row(
                Text(s.session_id, style="bold #00D1FF"),
                Text(str(s.pid), style="#C7F9CC"),
                Text(display_agent_type(s.agent_type), style=f"bold {color}"),
                Text(s.status, style=f"bold {status_color}"),
                Text(runtime, style="bold #00F5D4"),
            )

        return Panel(t, border_style="#00ff87", title="[bold #00ff87]▶ ACTIVE SESSIONS[/]")


class LiveRunsPanel(Static):
    """Unified live inventory: processes, tmux panes, Copilot events, and Stampede ledgers."""

    metrics: Optional[PulseMetrics] = reactive(None)

    def render(self) -> Panel:
        m = self.metrics
        if not m or not m.live_agents:
            return Panel(
                Text(
                    "No live agents/runs detected.\n"
                    "Scanning: processes · tmux panes · Copilot events · .stampede runs · swarm sub-agent ledgers",
                    style="#8D99AE",
                ),
                border_style="#00F5D4",
                title="[bold #00F5D4]◉ LIVE RUNS + SWARM SUB-AGENTS[/]",
            )

        running = sum(
            1
            for a in m.live_agents
            if a.status in {"RUN", "IN-FLIGHT"} and a.agent_type != "stampede-monitor"
        )
        levels = m.live_level_counts or empty_level_counts()
        division_commanders = levels.get("division_commanders", 0)
        commanders = levels.get("commanders", 0)
        title = (
            f"[bold #00F5D4]◉ LIVE RUNS + SWARM SUB-AGENTS[/]  "
            f"[#8D99AE]· running[/] [bold #7CFF6B]{running}[/]  "
            f"[#8D99AE]· div[/] [bold #B388FF]{division_commanders}[/]  "
            f"[#8D99AE]· cmd[/] [bold #00F5D4]{commanders}[/]  "
            f"[#8D99AE]· squads[/] [bold #FFD166]{levels.get('squad_leads', 0)}[/]  "
            f"[#8D99AE]· sub-agents[/] [bold #7CFF6B]{levels.get('workers', 0)}[/]  "
            f"[#8D99AE]· rev[/] [bold #FF4D6D]{levels.get('reviewers', 0)}[/]"
        )

        t = Table.grid(padding=(0, 1))
        t.add_column("src", justify="left", width=10)
        t.add_column("type", justify="left", min_width=15)
        t.add_column("name", justify="left", min_width=30)
        t.add_column("status", justify="center", width=11)
        t.add_column("model", justify="left", min_width=12)
        t.add_column("age", justify="right", width=6)

        t.add_row(
            Text("SOURCE", style="bold #8D99AE"),
            Text("TYPE", style="bold #8D99AE"),
            Text("RUN / AGENT / SWARM SUB-AGENTS", style="bold #8D99AE"),
            Text("STATUS", style="bold #8D99AE"),
            Text("MODEL", style="bold #8D99AE"),
            Text("AGE", style="bold #8D99AE"),
        )

        for agent in m.live_agents[:18]:
            color = TYPE_COLOR.get(agent.agent_type, TYPE_COLOR["custom"])
            if agent.status in {"RUN", "IN-FLIGHT"}:
                status_color = "#7CFF6B"
            elif agent.status in {"DONE", "SUCCESS"}:
                status_color = "#00D1FF"
            elif "DEAD" in agent.status or "FAIL" in agent.status:
                status_color = "#FF4D6D"
            else:
                status_color = "#FFD166"

            name = agent.name
            if agent.parent and agent.source in {"metaswarm", "stampede"}:
                name = f"{agent.parent}/{name}"
            max_name = 58 if agent.agent_type == "metaswarm-swarm" else 38
            if len(name) > max_name:
                name = name[: max_name - 3] + "..."

            t.add_row(
                Text(agent.source, style="#8D99AE"),
                Text(display_agent_type(agent.agent_type), style=f"bold {color}"),
                Text(name, style="#C7F9CC"),
                Text(agent.status, style=f"bold {status_color}"),
                Text(shorten_model(agent.model) if agent.model else "—", style=model_color(agent.model) if agent.model else "#8D99AE"),
                Text(human_age(agent.age_s), style="#8D99AE"),
            )

        foot = Text(
            f"Levels now: {division_commanders} division commanders · "
            f"{commanders} commanders · "
            f"{levels.get('squad_leads', 0)} squad leads · "
            f"{levels.get('workers', 0)} sub-agents · "
            f"{levels.get('reviewers', 0)} reviewers · "
            f"{levels.get('other', 0)} other.  "
            f"Metaswarm ledgers: {m.metaswarm_active_commanders} commanders · "
            f"{m.metaswarm_children_seen} sub-agents seen · "
            f"{m.metaswarm_children_running} running · "
            f"{m.metaswarm_children_stale} stale · "
            f"{m.metaswarm_children_last5m} sub-agent launches in 5m",
            style="#8D99AE",
        )
        return Panel(Group(t, "", foot), border_style="#00F5D4", title=title)


BUILTIN_AGENTS = {
    "task":             ("⚙", "Execute commands, run tests/builds", "#00D1FF"),
    "explore":          ("⚡", "Fast codebase exploration & research", "#7CFF6B"),
    "general-purpose":  ("●", "Full-capability multi-step agent", "#B388FF"),
    "code-review":      ("🔍", "High-signal code review", "#FF4D6D"),
    "rubber-duck":      ("🦆", "Interactive debugging companion", "#FFD166"),
    "dispatch-worker":  ("📡", "Parallel multi-terminal sub-agent", "#00F5D4"),
    "stampede-agent":   ("🐎", "Stampede orchestration sub-agent", "#FF9F1C"),
    "stampede-monitor": ("📊", "Stampede monitor pane", "#8D99AE"),
    "stampede-commander": ("🦬", "Metaswarm commander pane", "#FF9F1C"),
    "metaswarm-division": ("◈", "Metaswarm division commander", "#B388FF"),
    "metaswarm-commander": ("◇", "Metaswarm commander", "#FF9F1C"),
    "metaswarm-swarm":  ("🐝", "Swarm sub-agent summary", "#80FFDB"),
    "metaswarm-squad":  ("⬢", "Metaswarm squad lead", "#FFD166"),
    "metaswarm-sub-agent": ("◆", "Metaswarm leaf sub-agent", "#00F5D4"),
    "metaswarm-worker": ("◆", "Metaswarm leaf sub-agent", "#00F5D4"),
    "metaswarm-reviewer": ("🔍", "Metaswarm reviewer", "#FF4D6D"),
    "swarm-command":    ("🐝", "Multi-model swarm orchestrator", "#80FFDB"),
}

CUSTOM_AGENT_COLORS = [
    "#FF9F1C", "#80FFDB", "#C7F9CC", "#00D1FF", "#B388FF", "#FFD166", "#FF4D6D",
]


def discover_installed_agents() -> List[Tuple[str, str, str, str]]:
    """Dynamically discover installed agents from ~/.copilot/agents/."""
    agents_dir = Path.home() / ".copilot" / "agents"
    discovered: List[Tuple[str, str, str, str]] = []
    seen_names: set = set()

    # Always include builtins first
    for name, (icon, desc, color) in BUILTIN_AGENTS.items():
        discovered.append((name, icon, desc, color))
        seen_names.add(name)

    # Scan for custom agents
    if agents_dir.exists():
        for agent_file in sorted(agents_dir.glob("*.agent.md")):
            try:
                agent_name = agent_file.stem.replace(".agent", "")
                if agent_name in seen_names:
                    continue
                seen_names.add(agent_name)
                # Try to read description from file
                desc = "Custom agent"
                try:
                    content = agent_file.read_text(errors="replace")[:500]
                    for line in content.splitlines():
                        stripped = line.strip().lstrip("#").strip()
                        if stripped and not stripped.startswith("---"):
                            desc = stripped[:60]
                            break
                except Exception:
                    pass
                color_idx = len(discovered) % len(CUSTOM_AGENT_COLORS)
                discovered.append((agent_name, "🔮", desc, CUSTOM_AGENT_COLORS[color_idx]))
            except Exception:
                continue

    return discovered


class InstalledAgentsPanel(Static):
    def render(self) -> Panel:
        agents = discover_installed_agents()
        t = Table.grid(padding=(0, 2))
        t.add_column("icon", justify="left", width=2)
        t.add_column("name", justify="left", min_width=20)
        t.add_column("desc", justify="left")

        for name, icon, desc, color in agents:
            t.add_row(
                Text(icon, style=color),
                Text(name, style=f"bold {color}"),
                Text(desc, style="#8D99AE"),
            )

        return Panel(t, border_style="#B388FF", title=f"[bold #B388FF]⧡ INSTALLED AGENTS · {len(agents)}[/]")


# Feature 4: Health Gauge Widget
class HealthGauge(Static):
    metrics: Optional[PulseMetrics] = reactive(None)
    tick: int = reactive(0)

    def render(self) -> Panel:
        m = self.metrics
        if not m:
            return Panel("…", border_style="#00D1FF", title="[bold #00F5D4]♥ FLEET HEALTH[/]")

        score = m.health_score
        if score >= 90:
            label, color = "EXCELLENT", "#7CFF6B"
        elif score >= 70:
            label, color = "GOOD", "#00F5D4"
        elif score >= 45:
            label, color = "WARNING", "#FFD166"
        else:
            label, color = "CRITICAL", "#FF4D6D"

        bar_width = 24
        filled = int(round(score / 100 * bar_width))
        filled = max(0, min(bar_width, filled))

        t = Table.grid(padding=(0, 2))
        t.add_column(justify="left")
        t.add_column(justify="right")

        t.add_row(
            Text("Health Score", style="bold white"),
            Text(f"{score}/100  {label}", style=f"bold {color}"),
        )

        gauge = Text()
        gauge.append("█" * filled, style=f"bold {color}")
        gauge.append("░" * (bar_width - filled), style="#2a2a3e")

        sr_color = "bold #7CFF6B" if m.success_rate_24h >= 0.9 else "bold #FFD166"
        err_color = "bold #FF4D6D" if m.error_count_24h > 0 else "#8D99AE"

        t.add_row(
            Text("Success Rate", style="#8D99AE"),
            Text(f"{m.success_rate_24h:.0%}", style=sr_color),
        )
        t.add_row(
            Text("Errors (24h)", style="#8D99AE"),
            Text(str(m.error_count_24h), style=err_color),
        )

        pulse = "●" if self.tick % 2 == 0 else "○"
        status = Text.assemble((pulse + " ", f"bold {color}"), ("MONITORING", f"bold {color}"))

        return Panel(
            Group(gauge, "", t, "", status),
            border_style=color,
            title="[bold #00F5D4]♥ FLEET HEALTH[/]",
        )


# Feature 2: Model Distribution Widget
class ModelDistPanel(Static):
    metrics: Optional[PulseMetrics] = reactive(None)

    def render(self) -> Panel:
        m = self.metrics
        if not m or not m.model_dist_24h:
            body = Text("No model data yet.\n(Agent launches with model info will appear here.)", style="#8D99AE")
            return Panel(body, border_style="#B388FF", title="[bold #B388FF]🧠 MODEL DISTRIBUTION[/]")

        dist = m.model_dist_24h
        total = max(sum(dist.values()), 1)
        maxv = max(dist.values())

        table = Table.grid(padding=(0, 1))
        table.add_column("model", justify="left", min_width=14)
        table.add_column("n", justify="right", width=4)
        table.add_column("pct", justify="right", width=6)
        table.add_column("bar", justify="left")

        bar_width = 14
        for model_name in sorted(dist.keys(), key=lambda x: (-dist[x], x)):
            color = model_color(model_name)
            short = shorten_model(model_name)
            cnt = dist[model_name]
            pct = round(100 * cnt / total)
            filled = int(round((cnt / maxv) * bar_width))
            filled = max(0, min(bar_width, filled))
            bar = Text("█" * filled + "░" * (bar_width - filled), style=color)
            table.add_row(
                Text(short, style=f"bold {color}"),
                Text(str(cnt), style=f"bold {color}"),
                Text(f"({pct:2d}%)", style="#8D99AE"),
                bar,
            )

        return Panel(table, border_style="#B388FF", title="[bold #B388FF]🧠 MODEL DISTRIBUTION[/]")


class GlowTitle(Static):
    """Small title strip used above bordered boxes."""

    phase = reactive(0)

    def __init__(self, label: str, *, id: Optional[str] = None) -> None:
        super().__init__(id=id)
        self.label = label

    def render(self) -> Text:
        palettes = [
            ("#00F5D4", "#00D1FF"),
            ("#FFD166", "#FF4D6D"),
            ("#7CFF6B", "#B388FF"),
        ]
        a, b = palettes[self.phase % len(palettes)]
        return gradient_text(self.label, (a, b))


# ----------------------------
# Textual App
# ----------------------------

class AgentPulseApp(App):
    CSS_PATH = "agent_pulse.tcss"
    ENABLE_COMMAND_PALETTE = False
    BINDINGS = [
        ("q", "quit", "Quit"),
        ("r", "refresh", "Refresh"),
        ("space", "pause_resume", "⏸ Pause"),
        ("t", "cycle_timeframe", "⏱ Time"),
        ("e", "export_snapshot", "📤 Export"),
    ]

    # Feature 6: Pause state and timeframe
    _paused: bool = False
    _timeframe_index: int = 2  # default 24h
    _timeframes = [("1h", 3600), ("6h", 6 * 3600), ("24h", 24 * 3600), ("7d", 7 * 24 * 3600)]

    # Feature 5: Alert tracking
    _prev_spawned: int = 0
    _prev_error_rate_high: bool = False
    _alerted_milestones: set = None

    def __init__(self) -> None:
        super().__init__()
        self.store = PulseStore()
        self.engine = MetricsEngine(self.store)
        self._alerted_milestones = set()

    def compose(self) -> ComposeResult:
        yield Vertical(
            NeonLogo(id="logo"),
            Grid(
                StatPanel(id="stats"),
                HealthGauge(id="health"),
                id="row1_grid",
            ),
            Grid(
                HistoryPanel(self.store, id="history"),
                SignalPanel(self.store, id="signal"),
                id="row2_grid",
            ),
            Grid(
                MixPanel(id="mix"),
                ModelDistPanel(id="model_dist"),
                id="row3_grid",
            ),
            Grid(
                LiveRunsPanel(id="live_runs"),
                ActiveSessionsPanel(id="sessions"),
                id="row4_grid",
            ),
            Vertical(
                GlowTitle("RECENT LAUNCHES", id="recent_title"),
                RecentTable(id="recent"),
                id="recent_box",
            ),
            InstalledAgentsPanel(id="installed"),
            Footer(),
            id="root",
        )

    def on_mount(self) -> None:
        self.logo = self.query_one("#logo", NeonLogo)
        self.stats = self.query_one("#stats", StatPanel)
        self.health_gauge = self.query_one("#health", HealthGauge)
        self.history = self.query_one("#history", HistoryPanel)
        self.mix = self.query_one("#mix", MixPanel)
        self.model_dist = self.query_one("#model_dist", ModelDistPanel)
        self.live_runs = self.query_one("#live_runs", LiveRunsPanel)
        self.sessions_panel = self.query_one("#sessions", ActiveSessionsPanel)
        self.recent_title = self.query_one("#recent_title", GlowTitle)
        self.recent = self.query_one("#recent", RecentTable)

        self.set_interval(0.25, self._tick)
        self.set_interval(1.0, self._poll)
        self._poll()
        self._apply_responsive_layout()

    def on_resize(self, event) -> None:
        self._apply_responsive_layout(event.size.width)

    def _apply_responsive_layout(self, width: int | None = None) -> None:
        """Switch grids between 2-column and 1-column based on terminal width."""
        if width is None:
            width = self.size.width
        narrow = width < 100
        for grid_id in ("#row1_grid", "#row2_grid", "#row3_grid", "#row4_grid"):
            try:
                grid = self.query_one(grid_id, Grid)
                if narrow:
                    grid.styles.grid_size_columns = 1
                    grid.styles.grid_columns = "1fr"
                else:
                    grid.styles.grid_size_columns = 2
                    grid.styles.grid_columns = "1fr 1fr"
            except Exception:
                pass

    def action_refresh(self) -> None:
        self._poll()

    def action_pause_resume(self) -> None:
        self._paused = not self._paused
        if self._paused:
            self.notify("⏸ Dashboard paused", timeout=3)
        else:
            self.notify("▶ Dashboard resumed", timeout=3)

    def action_cycle_timeframe(self) -> None:
        self._timeframe_index = (self._timeframe_index + 1) % len(self._timeframes)
        label, _ = self._timeframes[self._timeframe_index]
        self.notify(f"⏱ Timeframe: {label}", timeout=3)
        self._poll()

    def action_export_snapshot(self) -> None:
        export_dir = Path.home() / ".copilot" / "agent-pulse"
        export_dir.mkdir(parents=True, exist_ok=True)
        ts_str = datetime.now().strftime("%Y%m%d-%H%M%S")
        export_path = export_dir / f"export-{ts_str}.json"
        try:
            m = self.engine.poll()
            data = {
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "active_sessions": m.active_sessions,
                "running_agents_est": m.running_agents_est,
                "total_live_agents": m.total_live_agents,
                "live_level_counts": m.live_level_counts,
                "launch_level_counts_5m": m.launch_level_counts_5m,
                "spawned_all_time": m.spawned_all_time,
                "spawned_today": m.spawned_today,
                "spawned_week": m.spawned_week,
                "spawned_month": m.spawned_month,
                "spawned_by_type_24h": m.spawned_by_type_24h,
                "velocity": m.velocity,
                "peak_velocity": m.peak_velocity,
                "success_rate_24h": m.success_rate_24h,
                "error_count_24h": m.error_count_24h,
                "health_score": m.health_score,
                "tokens_today": m.tokens_today,
                "model_dist_24h": m.model_dist_24h,
                "live_agents": [dataclasses.asdict(a) for a in m.live_agents],
                "metaswarm": {
                    "active_commanders": m.metaswarm_active_commanders,
                    "sub_agents_seen": m.metaswarm_children_seen,
                    "sub_agents_running": m.metaswarm_children_running,
                    "sub_agents_stale": m.metaswarm_children_stale,
                    "sub_agents_last5m": m.metaswarm_children_last5m,
                    "children_seen": m.metaswarm_children_seen,
                    "children_running": m.metaswarm_children_running,
                    "children_stale": m.metaswarm_children_stale,
                    "children_last5m": m.metaswarm_children_last5m,
                    "runs": [dataclasses.asdict(r) for r in m.metaswarm_runs],
                },
            }
            with open(export_path, "w") as f:
                json.dump(data, f, indent=2)
            self.notify(f"📤 Exported to {export_path.name}", timeout=5)
        except Exception as e:
            self.notify(f"Export failed: {e}", severity="error", timeout=5)

    def _tick(self) -> None:
        self.logo.tick += 1
        self.stats.tick += 1
        self.health_gauge.tick += 1

    def _poll(self) -> None:
        if self._paused:
            return
        m = self.engine.poll()

        # Feature 5: Alert on new agent launches
        if self._prev_spawned > 0 and m.spawned_all_time > self._prev_spawned:
            diff = m.spawned_all_time - self._prev_spawned
            if m.recent_events:
                latest_type = m.recent_events[0][1]
                self.notify(f"⚡ New {latest_type} agent launched", timeout=4)

        # Feature 5: Error rate alert
        error_high = m.error_count_24h > 3
        if error_high and not self._prev_error_rate_high:
            self.notify("🔴 Error rate elevated", severity="error", timeout=6)
        self._prev_error_rate_high = error_high

        # Feature 5: Milestones
        for milestone in (10, 50, 100, 500, 1000):
            if m.spawned_all_time >= milestone and milestone not in self._alerted_milestones:
                self._alerted_milestones.add(milestone)
                if self._prev_spawned > 0:  # don't alert on first load
                    self.notify(f"🎉 Milestone: {milestone} agents!", timeout=8)

        self._prev_spawned = m.spawned_all_time

        # Update all widgets
        self.logo.metrics = m
        self.stats.metrics = m
        self.health_gauge.metrics = m
        self.history.metrics = m
        self.mix.metrics = m
        self.model_dist.metrics = m
        self.live_runs.metrics = m
        self.sessions_panel.metrics = m
        self.recent.update_rows(m.recent_events)

    def on_shutdown(self) -> None:
        self.store.close()


VERSION = "2.4.2"

BANNER_ART = r"""
    ___   ___  ___ _  _ _____   ___  _   _ _    ___ ___
   /   \ / __|| __| \| |_   _| | _ \| | | | |  / __| __|
   | - || (_ || _|| .` | | |   |  _/| |_| | |__\__ \ _|
   |_|_| \___||___|_|\_| |_|   |_|   \___/|____|___/___|
"""


def _show_startup_splash() -> None:
    """Animated boot splash before launching the Textual app."""
    from rich.console import Console
    from rich.align import Align as RAlign

    console = Console()
    console.clear()
    console.print()

    for line in BANNER_ART.strip("\n").split("\n"):
        console.print(RAlign.center(Text(line, style="bold white")))
    console.print(RAlign.center(Text("Agent Dashboard for the Copilot CLI", style="bold white")))
    console.print()

    stages = [
        ("Scanning processes",         0.8, "#00f5ff"),
        ("Connecting to session store", 0.9, "#00ff87"),
        ("Loading agent registry",     0.9, "#ff00ff"),
        ("Mapping active sessions",    1.0, "#ffd75f"),
        ("Rendering dashboard",        0.7, "#bf7fff"),
    ]
    for label, duration, color in stages:
        with console.status(
            f"[bold {color}]{label}[/]",
            spinner="dots",
            spinner_style=f"bold {color}",
        ):
            time.sleep(duration)
        console.print(RAlign.center(Text(f"  ✓ {label}", style=f"bold {color}")))

    console.print()
    online = Text(justify="center")
    online.append("  ◉ ", style="bold #00ff87")
    online.append("ONLINE", style="bold #00ff87")
    console.print(RAlign.center(online))
    time.sleep(0.3)


def _mode_export() -> None:
    """Export current metrics as JSON to stdout."""
    store = PulseStore()
    engine = MetricsEngine(store)
    m = engine.poll()
    data = {
        "exported_at": datetime.now(timezone.utc).isoformat(),
        "version": VERSION,
        "active_sessions": m.active_sessions,
        "running_agents_est": m.running_agents_est,
        "total_live_agents": m.total_live_agents,
        "live_level_counts": m.live_level_counts,
        "launch_level_counts_5m": m.launch_level_counts_5m,
        "spawned_all_time": m.spawned_all_time,
        "spawned_today": m.spawned_today,
        "spawned_week": m.spawned_week,
        "spawned_month": m.spawned_month,
        "spawned_by_type_24h": m.spawned_by_type_24h,
        "velocity": m.velocity,
        "peak_velocity": m.peak_velocity,
        "success_rate_24h": m.success_rate_24h,
        "error_count_24h": m.error_count_24h,
        "health_score": m.health_score,
        "tokens_today": m.tokens_today,
        "model_dist_24h": m.model_dist_24h,
        "live_agents": [dataclasses.asdict(a) for a in m.live_agents],
        "metaswarm": {
            "active_commanders": m.metaswarm_active_commanders,
            "sub_agents_seen": m.metaswarm_children_seen,
            "sub_agents_running": m.metaswarm_children_running,
            "sub_agents_stale": m.metaswarm_children_stale,
            "sub_agents_last5m": m.metaswarm_children_last5m,
            "children_seen": m.metaswarm_children_seen,
            "children_running": m.metaswarm_children_running,
            "children_stale": m.metaswarm_children_stale,
            "children_last5m": m.metaswarm_children_last5m,
            "runs": [dataclasses.asdict(r) for r in m.metaswarm_runs],
        },
        "installed_agents": [a[0] for a in discover_installed_agents()],
    }
    store.close()
    print(json.dumps(data, indent=2))


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(
        description="Agent Pulse — real-time agent tracking dashboard for GitHub Copilot CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Modes:
  (default)    Launch the live Textual dashboard
  --export     Export current metrics as JSON to stdout
  --no-splash  Skip the boot animation

Examples:
  python agent_pulse.py                 # Launch dashboard
  python agent_pulse.py --export        # JSON export
  python agent_pulse.py --no-splash     # Skip boot animation
""",
    )
    parser.add_argument("--export", "-e", action="store_true", help="Export JSON to stdout")
    parser.add_argument("--no-splash", action="store_true", help="Skip boot animation")
    parser.add_argument("--version", "-v", action="version", version=f"Agent Pulse v{VERSION}")
    args = parser.parse_args()

    if args.export:
        _mode_export()
        return

    if not args.no_splash and os.environ.get("AGENT_PULSE_NO_SPLASH") != "1":
        _show_startup_splash()

    AgentPulseApp().run()


if __name__ == "__main__":
    main()
