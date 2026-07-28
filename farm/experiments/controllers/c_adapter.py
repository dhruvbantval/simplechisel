"""Drive a C PID controller from Python via ctypes.

C can't expose an arbitrary struct to Python without knowing its layout, so this
targets the specific, extremely widely-copied interface from Philip Salmony's
"PID Controller Implementation in Software" (the `PID-master` repo):

    typedef struct { float Kp,Ki,Kd,tau, limMin,limMax, limMinInt,limMaxInt, T,
                           integrator,prevError,differentiator,prevMeasurement,out; } PIDController;
    void  PIDController_Init(PIDController*);
    float PIDController_Update(PIDController*, float setpoint, float measurement);

We compile the uploaded .c (its .h must sit beside it) into a shared library, set
the gains with wide limits and a small derivative filter, and call Update each tick.
A C file with a different interface raises a clear error.
"""
from __future__ import annotations

import ctypes
import subprocess
import tempfile
from pathlib import Path


class PIDController(ctypes.Structure):
    _fields_ = [(n, ctypes.c_float) for n in (
        "Kp", "Ki", "Kd", "tau", "limMin", "limMax", "limMinInt", "limMaxInt", "T",
        "integrator", "prevError", "differentiator", "prevMeasurement", "out")]


class _CAdapter:
    kind = "C PIDController_Update(pid, setpoint, measurement)"

    def __init__(self, lib, kp, ki, kd, dt):
        self.lib = lib
        self.pid = PIDController()
        self.pid.Kp, self.pid.Ki, self.pid.Kd = kp, ki, kd
        self.pid.tau = max(2.0 * dt, 1e-3)      # derivative low-pass time constant
        self.pid.T = dt
        big = 1e9
        self.pid.limMin, self.pid.limMax = -big, big
        self.pid.limMinInt, self.pid.limMaxInt = -big, big
        lib.PIDController_Init(ctypes.byref(self.pid))

    def output(self, setpoint, measurement, dt):
        return float(self.lib.PIDController_Update(
            ctypes.byref(self.pid), ctypes.c_float(setpoint), ctypes.c_float(measurement)))


def build_c_adapter(path: Path, kp, ki, kd, dt):
    src_dir = path.parent
    sources = sorted(str(p) for p in src_dir.glob("*.c"))  # compile all .c beside it
    if not sources:
        sources = [str(path)]
    so = Path(tempfile.mkdtemp()) / "controller.so"
    cc = "clang"
    proc = subprocess.run(
        [cc, "-shared", "-fPIC", "-O2", f"-I{src_dir}", "-o", str(so), *sources],
        capture_output=True, text=True)
    if proc.returncode != 0:
        raise ValueError(f"could not compile C controller: {proc.stderr.strip()[:300]}")

    lib = ctypes.CDLL(str(so))
    try:
        lib.PIDController_Update.restype = ctypes.c_float
        lib.PIDController_Update.argtypes = [
            ctypes.POINTER(PIDController), ctypes.c_float, ctypes.c_float]
        lib.PIDController_Init.argtypes = [ctypes.POINTER(PIDController)]
    except AttributeError as exc:
        raise ValueError(
            "this C file doesn't expose PIDController_Init/Update — the adapter "
            "targets the Salmony PIDController interface") from exc
    return _CAdapter(lib, kp, ki, kd, dt)
