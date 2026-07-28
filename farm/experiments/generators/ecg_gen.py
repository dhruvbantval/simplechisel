#!/usr/bin/env python3
"""Generate synthetic ECG recordings with known beats for the ECG experiment.

We place R-peaks at known sample positions (with slight heart-rate variability),
sum a QRS-shaped spike at each, add mild noise, and write a WFDB record whose .atr
annotation IS our ground truth. The same experiment then scores the detector
against those known beats — synthetic data with perfect labels.

    python ecg_gen.py 3
"""
import json
import math
import sys
from pathlib import Path

import numpy as np
import wfdb

DATA = Path(__file__).resolve().parents[1].parent / "data" / "mitdb"


def qrs(k):
    """A dominant R spike with small Q/S deflections."""
    return (1.2 * math.exp(-(k ** 2) / 18.0)
            - 0.25 * math.exp(-((k - 8) ** 2) / 32.0)
            - 0.25 * math.exp(-((k + 8) ** 2) / 32.0))


def synth(seed, fs=360, duration=30, heart_rate=75):
    rng = np.random.default_rng(seed)
    n = fs * duration
    rr = fs * 60.0 / heart_rate
    beats, t = [], rr
    while t < n - fs:
        beats.append(int(round(t)))
        t += rr * (1.0 + rng.normal(0, 0.03))
    sig = rng.normal(0, 0.01, n)
    for b in beats:
        for k in range(-20, 25):
            i = b + k
            if 0 <= i < n:
                sig[i] += qrs(k)
    return sig.astype(float), np.array(beats, dtype=int), fs


def main():
    count = int(sys.argv[1]) if len(sys.argv) > 1 else 3
    DATA.mkdir(parents=True, exist_ok=True)
    cases = []
    for k in range(count):
        hr = 60 + 10 * k
        sig, beats, fs = synth(seed=1000 + k, heart_rate=hr)
        name = f"synthetic_{hr}bpm_{k}"
        wfdb.wrsamp(name, fs=fs, units=["mV"], sig_name=["ECG"],
                    p_signal=sig.reshape(-1, 1), fmt=["16"], write_dir=str(DATA))
        wfdb.wrann(name, "atr", sample=beats, symbol=["N"] * len(beats),
                   write_dir=str(DATA))
        cases.append({"name": f"synthetic {hr}bpm", "record": name, "seconds": 0})
    print(json.dumps(cases))


if __name__ == "__main__":
    main()
