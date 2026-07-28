"""Shared helpers for adapters that shell out to a Python experiment script.

The scripts live in farm/experiments/ (not next to the adapters) so an adapter
module never shadows a library the script imports -- e.g. adapters/control.py
would otherwise shadow the `control` package.

The experiment scripts need third-party packages (scipy, wfdb, ...) that the farm
core deliberately does not depend on, so they run out of farm/.venv when it
exists. Each script prints one JSON object; the adapter reads it.
"""
from __future__ import annotations

import json
from pathlib import Path

FARM = Path(__file__).resolve().parents[1]
EXPERIMENTS = FARM / "experiments"
_VENV_PY = FARM / ".venv" / "bin" / "python"


def python_bin() -> str:
    """The interpreter that has the experiment dependencies installed."""
    return str(_VENV_PY) if _VENV_PY.exists() else "python3"


def script(name: str) -> str:
    return str(EXPERIMENTS / name)


def last_json(stdout: str):
    """Experiment scripts print one JSON object; tolerate library chatter around it."""
    for line in reversed((stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None
