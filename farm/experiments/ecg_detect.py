#!/usr/bin/env python3
"""One ECG experiment: a heartbeat detector vs cardiologists' annotations.

Intern 2's domain. Every heartbeat shows up as a sharp "R peak" in an ECG. The
MIT-BIH Arrhythmia Database ships expert cardiologist beat labels (.atr files), so
a detector can be scored against real human ground truth:

    DUT     NeuroKit2's R-peak detector run on the raw signal
    golden  the cardiologists' beat annotations
    metric  sensitivity (what fraction of real beats we found)
            + PPV (what fraction of our detections were real)

A detection counts as correct if it lands within 150 ms of an annotated beat --
the standard matching tolerance. Prints one JSON object for the adapter.

Data is not committed. Fetch it once:
    farm/.venv/bin/python farm/experiments/ecg_fetch.py

    python ecg_experiment.py '{"record":"100","seconds":60}'
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import numpy as np

DATA = Path(__file__).resolve().parents[1] / "data" / "mitdb"

# MIT-BIH symbols that denote an actual heartbeat (vs rhythm/quality markers).
BEAT_SYMBOLS = set("NLRBAaJSVrFejnE/fQ?")


def match(detected, truth, tol):
    """Greedy nearest matching within `tol` samples. Returns (TP, FP, FN)."""
    detected = sorted(int(d) for d in detected)
    truth = sorted(int(t) for t in truth)
    i = j = tp = 0
    used = [False] * len(detected)
    for t in truth:
        # find the closest unused detection within tolerance
        best, best_d = -1, tol + 1
        for k in range(len(detected)):
            if used[k]:
                continue
            d = abs(detected[k] - t)
            if d <= tol and d < best_d:
                best, best_d = k, d
            if detected[k] - t > tol:
                break
        if best >= 0:
            used[best] = True
            tp += 1
    fn = len(truth) - tp
    fp = len(detected) - tp
    return tp, fp, fn


def main() -> int:
    cfg = json.loads(sys.argv[1]) if len(sys.argv) > 1 else {}
    record = str(cfg.get("record", "100"))
    seconds = float(cfg.get("seconds", 60))
    min_sens = float(cfg.get("min_sensitivity", 0.95))

    path = DATA / record
    if not (DATA / f"{record}.dat").exists():
        print(json.dumps({
            "error": f"MIT-BIH record '{record}' not found in {DATA}. "
                     "Fetch it once: farm/.venv/bin/python farm/experiments/ecg_fetch.py"}))
        return 3

    import wfdb
    import neurokit2 as nk

    rec = wfdb.rdrecord(str(path))
    ann = wfdb.rdann(str(path), "atr")
    fs = int(rec.fs)
    n = int(seconds * fs) if seconds > 0 else rec.p_signal.shape[0]
    n = min(n, rec.p_signal.shape[0])

    signal = np.asarray(rec.p_signal[:n, 0], dtype=float)
    truth = [s for s, sym in zip(ann.sample, ann.symbol) if sym in BEAT_SYMBOLS and s < n]

    # DUT: the detector under test
    _, info = nk.ecg_peaks(signal, sampling_rate=fs)
    detected = list(info.get("ECG_R_Peaks", []))

    tp, fp, fn = match(detected, truth, tol=int(0.15 * fs))
    sensitivity = tp / len(truth) if truth else 0.0
    ppv = tp / len(detected) if detected else 0.0

    print(json.dumps({
        "sensitivity": sensitivity,
        "ppv": ppv,
        "tp": tp, "fp": fp, "fn": fn,
        "true_beats": len(truth), "detected": len(detected),
        "record": record, "seconds": seconds,
        "min_sensitivity": min_sens,
        "ok": bool(sensitivity >= min_sens),
    }))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
