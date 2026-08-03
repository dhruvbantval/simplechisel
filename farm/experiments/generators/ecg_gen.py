#!/usr/bin/env python3
"""Add real MIT-BIH records to the ECG experiment. Prints a JSON list of cases.

The database holds 48 recordings and the farm starts with three. This fetches
records that are not present yet and emits one case each, so generating grows
coverage with real patient signals and real cardiologist annotations.

Synthetic waveforms are deliberately not produced. A clean signal with spikes at
positions we chose is found by any detector, so it scores 100% regardless of
whether the detector is any good. The difficulty in this domain comes from the
artifacts in real recordings — baseline wander, muscle noise, electrode motion,
unusual beat morphologies — and only real data has those.

    python ecg_gen.py 3

Needs network. Records land in farm/data/mitdb/ (git-ignored).
"""
import json
import sys
from pathlib import Path

DATA = Path(__file__).resolve().parents[1].parent / "data" / "mitdb"

# MIT-BIH Arrhythmia Database record numbers (physionet.org/content/mitdb).
ALL_RECORDS = [
    "100", "101", "102", "103", "104", "105", "106", "107", "108", "109",
    "111", "112", "113", "114", "115", "116", "117", "118", "119", "121",
    "122", "123", "124", "200", "201", "202", "203", "205", "207", "208",
    "209", "210", "212", "213", "214", "215", "217", "219", "220", "221",
    "222", "223", "228", "230", "231", "232", "233", "234",
]

SECONDS = 60


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    DATA.mkdir(parents=True, exist_ok=True)

    have = {p.stem for p in DATA.glob("*.dat")}
    missing = [r for r in ALL_RECORDS if r not in have][:n]
    if not missing:
        print(f"[ecg] all {len(ALL_RECORDS)} MIT-BIH records are already present",
              file=sys.stderr)
        print(json.dumps([]))
        return

    import wfdb
    print(f"[ecg] fetching {len(missing)} record(s): {', '.join(missing)}",
          file=sys.stderr)
    wfdb.dl_database("mitdb", str(DATA), records=missing)

    fetched = [r for r in missing if (DATA / f"{r}.dat").exists()]
    cases = [{"name": f"record {r}", "record": r, "seconds": SECONDS}
             for r in fetched]
    print(json.dumps(cases))


if __name__ == "__main__":
    main()
