# Sign flipped on the proportional term. Should FAIL (goes unstable).
class Controller:
    def __init__(self, kp, ki, kd, dt=None):
        self.kp, self.ki, self.kd = kp, ki, kd
        self._i = 0.0; self._prev = None
    def step(self, error, dt):
        self._i += error * dt
        d = 0.0 if self._prev is None else (error - self._prev) / dt
        self._prev = error
        return -self.kp * error + self.ki * self._i + self.kd * d
