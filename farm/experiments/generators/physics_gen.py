#!/usr/bin/env python3
"""Generate random RC circuits for the physics experiment. Prints a JSON list of
cases (each is an R and a C); the closed-form golden covers the whole RC family."""
import json, random, sys

def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    cases = []
    for _ in range(n):
        r = round(random.uniform(100, 100_000), 1)
        c = float(f"{random.uniform(1e-8, 1e-5):.2e}")
        cases.append({"name": f"gen R={r:g} C={c:g}", "r": r, "c": c})
    print(json.dumps(cases))

if __name__ == "__main__":
    main()
