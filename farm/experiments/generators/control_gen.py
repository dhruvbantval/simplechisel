#!/usr/bin/env python3
"""Generate random PID gain sets for the control experiment (a stress sweep of the
reference controller). Prints a JSON list of cases."""
import json, random, sys

REF = "farm/experiments/controllers/pid_reference.py"

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    cases = []
    for _ in range(n):
        kp = round(random.uniform(0.5, 6.0), 2)
        ki = round(random.uniform(0.2, 3.0), 2)
        kd = round(random.uniform(0.0, 1.5), 2)
        cases.append({"name": f"gen kp={kp} ki={ki} kd={kd}",
                      "controller": REF, "kp": kp, "ki": ki, "kd": kd})
    print(json.dumps(cases))

if __name__ == "__main__":
    main()
