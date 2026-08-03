#!/usr/bin/env python3
r"""Fetch a few MIT-BIH Arrhythmia Database records for the ECG experiment.

The recordings and their cardiologist annotations are not committed (they're
someone else's dataset, and large). Run this once after installing the ECG
requirements:

    farm/.venv/bin/python farm/experiments/ecg_fetch.py            # macOS / Linux
    farm\.venv\Scripts\python farm/experiments/ecg_fetch.py         # Windows

    ... ecg_fetch.py 100 101 103    # or name the records to fetch

Files land in farm/data/mitdb/ (git-ignored). Source: PhysioNet, needs network.
"""
from __future__ import annotations

import sys
from pathlib import Path

DEST = Path(__file__).resolve().parents[1] / "data" / "mitdb"
DEFAULT_RECORDS = ["100", "101", "103"]


def main() -> int:
    import wfdb
    records = sys.argv[1:] or DEFAULT_RECORDS
    DEST.mkdir(parents=True, exist_ok=True)
    print(f"[ecg] fetching MIT-BIH records {records} -> {DEST}")
    wfdb.dl_database("mitdb", str(DEST), records=records)
    have = sorted(p.stem for p in DEST.glob("*.dat"))
    print(f"[ecg] have records: {have}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
