"""Load farm.yaml — the single file that declares what experiments exist.

Everything about an experiment that isn't code lives here: its label, what the
design-under-test and golden reference are, which adapter runs it, what it needs
installed, and which cases make up a campaign. Adding a science is a block in that
file plus an adapter module — no edits to the server, runner, or dashboard.

    from farm.config import load_config, experiment, cases_for
"""
from __future__ import annotations

from pathlib import Path

FARM = Path(__file__).resolve().parent
ROOT = FARM.parent
CONFIG_PATH = FARM / "farm.yaml"


def venv_python() -> str:
    """The venv interpreter path to show in messages, spelled for this platform.

    posix venvs put it in bin/, Windows venvs in Scripts/.
    """
    import os
    return r"farm\.venv\Scripts\python" if os.name == "nt" else "farm/.venv/bin/python"


def venv_pip() -> str:
    """The venv pip path to show in messages, spelled for this platform."""
    import os
    return r"farm\.venv\Scripts\pip" if os.name == "nt" else "farm/.venv/bin/pip"


def _require_yaml():
    try:
        import yaml  # noqa: PLC0415
        return yaml
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "farm.yaml needs PyYAML. Install the farm core requirements:\n"
            f"  {venv_pip()} install -r farm/requirements/core.txt"
        ) from exc


def load_config(path: Path | None = None) -> dict:
    yaml = _require_yaml()
    p = Path(path) if path else CONFIG_PATH
    with p.open() as f:
        return yaml.safe_load(f) or {}


def experiments(config: dict | None = None) -> list[dict]:
    cfg = config if config is not None else load_config()
    return cfg.get("experiments", [])


def experiment(type_: str, config: dict | None = None) -> dict | None:
    for e in experiments(config):
        if e.get("type") == type_:
            return e
    return None


GENERATED_DIR = FARM / "build" / "generated"


NAME_MAX = 64      # keeps the full path well inside Windows' MAX_PATH


def safe_batch(name: str) -> str:
    """A filesystem-safe batch name (no traversal, no separators, bounded length)."""
    import time
    keep = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (name or "").strip())
    return keep.strip("-")[:NAME_MAX].strip("-") or f"batch-{int(time.time())}"


def batch_dir(type_: str) -> Path:
    return GENERATED_DIR / type_


def batches(type_: str) -> list[dict]:
    """Saved generated batches for an experiment, one JSON file each, newest first."""
    import json
    out = []
    d = batch_dir(type_)
    if d.is_dir():
        for f in sorted(d.glob("*.json")):
            try:
                cases = json.loads(f.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            out.append({"name": f.stem, "count": len(cases),
                        "created": f.stat().st_mtime})
    # a pre-batch flat file (farm/build/generated/<type>.json) still counts
    legacy = GENERATED_DIR / f"{type_}.json"
    if legacy.exists():
        try:
            cases = json.loads(legacy.read_text())
            out.append({"name": "generated", "count": len(cases),
                        "created": legacy.stat().st_mtime, "legacy": True})
        except (OSError, json.JSONDecodeError):
            pass
    out.sort(key=lambda b: b["created"], reverse=True)
    return out


def batch_cases(type_: str, name: str) -> list[dict]:
    """The cases in one saved batch."""
    import json
    f = batch_dir(type_) / f"{safe_batch(name)}.json"
    if not f.exists() and name == "generated":
        f = GENERATED_DIR / f"{type_}.json"      # legacy flat file
    try:
        return json.loads(f.read_text())
    except (OSError, json.JSONDecodeError):
        return []


def generated_cases(type_: str) -> list[dict]:
    """Every generated case for an experiment, tagged with its batch."""
    cases: list[dict] = []
    for b in batches(type_):
        for c in batch_cases(type_, b["name"]):
            cases.append({**c, "batch": b["name"]})
    return cases


def cases_for(exp: dict, batch: str | None = None) -> list[dict]:
    """The experiment cases a campaign runs, one record each.

    Without `batch`: the configured `cases:`, files found via
    `cases_from_corpus:`, and every generated batch.
    With `batch`: only that saved batch.
    """
    type_ = exp.get("type", "")
    if batch:
        return [{**c, "batch": batch} for c in batch_cases(type_, batch)]

    cases: list[dict] = []
    if exp.get("cases"):
        cases += [dict(c) for c in exp["cases"]]

    corpus = exp.get("cases_from_corpus")
    if corpus:
        pattern = exp.get("corpus_glob", "*")
        key = exp.get("corpus_key", "program")
        d = (ROOT / corpus) if not Path(corpus).is_absolute() else Path(corpus)
        cases += [{"name": f.name, key: str(f)} for f in sorted(d.glob(pattern))]

    cases += generated_cases(type_)
    return cases
