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


def _require_yaml():
    try:
        import yaml  # noqa: PLC0415
        return yaml
    except ImportError as exc:  # pragma: no cover - environment dependent
        raise RuntimeError(
            "farm.yaml needs PyYAML. Install the farm core requirements:\n"
            "  farm/.venv/bin/pip install -r farm/requirements/core.txt"
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


def generated_cases(type_: str) -> list[dict]:
    """Cases produced by an experiment's generator (the "Generate tests" button),
    persisted so they run alongside the configured ones."""
    import json
    f = GENERATED_DIR / f"{type_}.json"
    if f.exists():
        try:
            return json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            return []
    return []


def cases_for(exp: dict) -> list[dict]:
    """The list of experiment cases (one record each) a campaign runs: explicit
    `cases:`, files discovered via `cases_from_corpus:`, plus any generated cases.
    """
    cases: list[dict] = []
    if exp.get("cases"):
        cases += [dict(c) for c in exp["cases"]]

    corpus = exp.get("cases_from_corpus")
    if corpus:
        pattern = exp.get("corpus_glob", "*")
        key = exp.get("corpus_key", "program")
        d = (ROOT / corpus) if not Path(corpus).is_absolute() else Path(corpus)
        cases += [{"name": f.name, key: str(f)} for f in sorted(d.glob(pattern))]

    cases += generated_cases(exp.get("type", ""))
    return cases
