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
import os
import shutil
import sys
from pathlib import Path

FARM = Path(__file__).resolve().parents[1]
EXPERIMENTS = FARM / "experiments"
# posix venvs put the interpreter in bin/, Windows venvs in Scripts/
_VENV_PY = [FARM / ".venv" / "bin" / "python",
            FARM / ".venv" / "Scripts" / "python.exe"]


def python_bin() -> str:
    """The interpreter that has the experiment dependencies installed."""
    for py in _VENV_PY:
        if py.exists():
            return str(py)
    return sys.executable or "python3"


def bash_bin() -> str:
    """Path to an MSYS/Git bash that can see this repo.

    On Windows, CreateProcess searches System32 before PATH, so a bare "bash"
    resolves to the WSL launcher, which cannot open 'C:/repo/x.sh'. FARM_BASH
    overrides.
    """
    override = os.environ.get("FARM_BASH")
    if override and Path(override).exists():
        return override
    if os.name != "nt":
        return "bash"
    system32 = (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32").resolve()
    candidates = []
    found = shutil.which("bash")
    if found:
        candidates.append(Path(found))
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")):
        candidates += [Path(base) / "Git" / "bin" / "bash.exe",
                       Path(base) / "Git" / "usr" / "bin" / "bash.exe"]
    for c in candidates:
        try:
            if c.exists() and c.resolve().parent != system32:
                return str(c)
        except OSError:
            continue
    return "bash"


def sh_path(p) -> str:
    """A path spelled for bash: forward slashes, drive letter kept."""
    return Path(p).as_posix()


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
