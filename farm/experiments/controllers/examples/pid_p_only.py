# Proportional only — no integral, no derivative. Should FAIL (steady-state error).
class Controller:
    def __init__(self, kp, ki, kd, dt=None):
        self.kp = kp
    def step(self, error, dt):
        return self.kp * error
