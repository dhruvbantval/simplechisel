"""Reference PID controller — copy this to write your own.

The control experiment drives your controller around a plant and checks the
closed-loop response against the textbook answer (python-control's
step_response of the ideal PID). If your PID is correct the responses match; a
bug (wrong sign, missing term, bad integral) makes them diverge.

Your file must define a `Controller` class with this interface:

    class Controller:
        def __init__(self, kp, ki, kd, dt): ...   # gains + timestep from the case
        def step(self, error, dt) -> float: ...   # called each tick; return u

Point a case at it in farm.yaml:

    - name: my pid
      controller: farm/experiments/controllers/my_pid.py
      kp: 2.0
      ki: 1.0
      kd: 0.5
"""


class Controller:
    def __init__(self, kp, ki, kd, dt=None):
        self.kp = kp
        self.ki = ki
        self.kd = kd
        self._integral = 0.0
        self._prev_error = None

    def step(self, error, dt):
        # integral term: accumulate error over time
        self._integral += error * dt
        # derivative term: rate of change of the error
        derivative = 0.0 if self._prev_error is None else (error - self._prev_error) / dt
        self._prev_error = error
        return self.kp * error + self.ki * self._integral + self.kd * derivative
