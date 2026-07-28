"""Load a controller from a file, whatever interface it uses, and drive it uniformly.

Different PID implementations expose different shapes. This adapter layer detects
the shape and wraps it so the simulation only ever calls one method:

    adapter.output(setpoint, measurement, dt) -> control signal u

Supported so far:
  * native      a `Controller` class with `.step(error, dt)`      (our template)
  * simple-pid  a `PID` class called `pid(measurement, dt=...)`   (the popular lib)
  * callable    any class whose instance is callable on the measurement
  * function    a module-level `controller`/`control`/`pid`/`update` function
  * C           a `.c` file exposing `PIDController_Update(pid, setpoint, meas)`
                (Philip Salmony's widely-copied PID); compiled and driven via ctypes

Anything else raises a clear error listing what is supported, so an unrecognised
file is an honest "can't run this shape", never a silent wrong answer.
"""
from __future__ import annotations

import importlib.util
import inspect
from pathlib import Path


def _import(path: Path):
    spec = importlib.util.spec_from_file_location("user_controller", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# --------------------------------------------------------------- python shapes ---
class _Native:
    kind = "native Controller.step(error, dt)"

    def __init__(self, cls, kp, ki, kd, dt):
        self.c = cls(kp=kp, ki=ki, kd=kd, dt=dt)

    def output(self, setpoint, measurement, dt):
        return float(self.c.step(setpoint - measurement, dt))


class _SimplePID:
    kind = "simple-pid PID(measurement, dt)"

    def __init__(self, cls, kp, ki, kd, dt):
        # no output limits so we compare the controller, not its clamps; disable the
        # sample-time gate so every tick updates
        self.c = cls(kp, ki, kd, setpoint=1.0, output_limits=(None, None))
        try:
            self.c.sample_time = None
        except Exception:  # noqa: BLE001
            pass

    def output(self, setpoint, measurement, dt):
        self.c.setpoint = setpoint
        return float(self.c(measurement, dt=dt))


class _Callable:
    kind = "callable controller(measurement)"

    def __init__(self, obj):
        self.c = obj

    def output(self, setpoint, measurement, dt):
        try:
            return float(self.c(setpoint - measurement, dt))
        except TypeError:
            return float(self.c(setpoint - measurement))


def _from_python(path, kp, ki, kd, dt):
    mod = _import(path)
    if hasattr(mod, "Controller"):
        return _Native(mod.Controller, kp, ki, kd, dt)
    if hasattr(mod, "PID"):
        return _SimplePID(mod.PID, kp, ki, kd, dt)
    # a module-level function that looks like a controller
    for name in ("controller", "control", "pid", "update", "step"):
        fn = getattr(mod, name, None)
        if callable(fn) and not inspect.isclass(fn):
            return _Callable(fn)
    # a single class whose instances are callable (simple-pid-like, other name)
    for _, obj in inspect.getmembers(mod, inspect.isclass):
        if obj.__module__ == mod.__name__ and callable(getattr(obj, "__call__", None)):
            try:
                return _Callable(obj(kp, ki, kd))
            except Exception:  # noqa: BLE001
                continue
    raise ValueError(
        "no recognised controller in this file. Provide one of: a `Controller` "
        "class with step(error, dt); a `PID` class called pid(measurement, dt); or "
        "a controller() function.")


def build_adapter(path, kp, ki, kd, dt):
    p = Path(path)
    if p.suffix in (".c", ".h"):
        from farm.experiments.controllers.c_adapter import build_c_adapter
        return build_c_adapter(p, kp, ki, kd, dt)
    return _from_python(p, kp, ki, kd, dt)
