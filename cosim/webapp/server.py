#!/usr/bin/env python3
"""Local backend for the CPU dashboard.

Drives the cosim pipeline from HTTP so the browser can build a library of test
folders, inject CPU bugs, run a folder against the (possibly buggy) CPU, and see
success rates -- without ever touching a JSON file.

Test library + run are decoupled:
    POST /api/generate  {name, tests, instrCnt, type}  -> save a folder of tests
    GET  /api/folders                                  -> list saved folders
    GET  /api/folders/<name>                           -> tests in a folder
    POST /api/run       {folder}                       -> run folder vs current CPU

Bug injection is stateful -- bugs stack on the CPU source and stay applied until
reset (the CPU is rebuilt on the next run):
    GET  /api/injected                                 -> currently injected bugs
    POST /api/inject    {function}                     -> apply one bug (stacks)
    POST /api/reset                                    -> restore the clean CPU

Plus: GET /api/jobs/<id>, /api/runs, /api/runs/<id>, /api/mutations, /api/health.

Heavy jobs (sbt + Verilator + Spike) cannot run on Vercel serverless, so this is
a real long-running process. Pure stdlib -- no pip deps.
"""
from __future__ import annotations

import importlib.util
import json
import os
import queue
import re
import shutil
import subprocess
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
COSIM = ROOT / "cosim"
GEN = COSIM / "generator" / "gen_tests.sh"
RUN_COSIM = COSIM / "run_cosim.sh"
MUTATION_PY = COSIM / "mutation" / "run_mutation_campaign.py"
CAMPAIGN_DIR = COSIM / "build" / "campaigns"
TESTS_DIR = COSIM / "build" / "webapp" / "tests"   # the persistent test library
CPU_DIR = COSIM / "build" / "webapp" / "cpu"        # uploaded custom CPUs
BUILTIN_SV = ROOT / "build_singlecyclecpu_nd"       # DINO's generated Verilog
STATIC_DIR = Path(__file__).resolve().parent / "static"

HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", "8000"))

EXTRA_PATH = [
    "/usr/local/bin",
    "/usr/local/opt/riscv64-elf-gcc/bin",
    "/usr/local/opt/riscv64-elf-binutils/bin",
    "/opt/homebrew/bin",
]

TYPES = ["mixed", "arithmetic"]
TEST = "riscv_rv64i_dino_test"   # program filename prefix (matches gen_tests.sh)


def child_env() -> dict:
    env = os.environ.copy()
    parts = EXTRA_PATH + env.get("PATH", "").split(os.pathsep)
    seen, ordered = set(), []
    for p in parts:
        if p and p not in seen:
            seen.add(p)
            ordered.append(p)
    env["PATH"] = os.pathsep.join(ordered)
    return env


def have(tool: str) -> bool:
    return any((Path(d) / tool).exists() for d in child_env()["PATH"].split(os.pathsep))


def safe_folder(name: str) -> str:
    """A filesystem-safe folder name (no traversal, no separators)."""
    keep = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (name or "").strip())
    return keep.strip("-") or f"batch-{int(time.time())}"


# --- load the mutation catalogue + apply/restore primitives from the CLI tool ---
def _load_mutations():
    spec = importlib.util.spec_from_file_location("rmc", MUTATION_PY)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


RMC = _load_mutations()


# --------------------------------------------------------- injected-bug state ---
class BugState:
    """Bugs stack on the Chisel source and stay applied until reset. We keep the
    pristine bytes of every file we touch so reset is exact, and a dirty flag so
    the next run knows to rebuild the CPU."""

    def __init__(self):
        self.injected: list[dict] = []   # [{name, function, description}]
        self.pristine: dict[Path, bytes] = {}
        self.rtl_dirty = False
        self.lock = threading.Lock()

    def inject(self, function: str) -> dict:
        if CPUS.snapshot()["active"] is not None:
            return {"ok": False,
                    "error": "bugs apply to the built-in DINO; switch to it to inject"}
        with self.lock:
            name = RMC.FUNCTION_CHOICES.get(function)
            if not name:
                return {"ok": False, "error": f"unknown bug '{function}'"}
            if any(b["name"] == name for b in self.injected):
                return {"ok": False, "error": f"'{name}' already injected; reset first"}
            mutation = RMC.MUTATION_BY_NAME[name]

            applied, warnings = 0, []
            for rel_path, old, new in mutation.edits:
                path = ROOT / rel_path
                text = path.read_text(encoding="utf-8")
                if text.count(old) != 1:
                    warnings.append(
                        f"skipped an edit in {rel_path} (already changed by another bug)")
                    continue
                if path not in self.pristine:
                    self.pristine[path] = path.read_bytes()
                path.write_text(text.replace(old, new), encoding="utf-8")
                applied += 1

            if applied == 0:
                return {"ok": False,
                        "error": f"'{name}' conflicts with an injected bug", "warnings": warnings}
            self.injected.append(
                {"name": name, "function": function, "description": mutation.description})
            self.rtl_dirty = True
            return {"ok": True, "injected": list(self.injected), "warnings": warnings}

    def reset(self) -> dict:
        with self.lock:
            for path, data in self.pristine.items():
                path.write_bytes(data)
            had = len(self.injected)
            self.injected.clear()
            self.pristine.clear()
            if had:
                self.rtl_dirty = True   # rebuild back to a clean CPU on next run
            return {"ok": True, "injected": []}

    def snapshot(self) -> dict:
        with self.lock:
            return {"injected": list(self.injected), "rtlDirty": self.rtl_dirty}

    def mark_built(self):
        with self.lock:
            self.rtl_dirty = False

    def label(self) -> str | None:
        with self.lock:
            return "+".join(b["name"] for b in self.injected) or None


BUGS = BugState()


# ------------------------------------------------------------- custom CPUs ---
class CPUState:
    """Which CPU runs are built against: the built-in DINO (Chisel, bug-injectable)
    or an uploaded set of .sv files. Switching forces a rebuild."""

    def __init__(self):
        self.active: str | None = None   # None = built-in DINO
        self.dirty = False               # active changed since last build
        self.lock = threading.Lock()

    def select(self, name: str | None) -> dict:
        new = None if name in (None, "", "__builtin__") else safe_folder(name)
        with self.lock:
            if new != self.active:
                self.active = new
                self.dirty = True
        if new is not None:
            BUGS.reset()  # injected bugs edit Chisel source; they don't apply to custom SV
        return self.snapshot()

    def snapshot(self) -> dict:
        with self.lock:
            return {"active": self.active, "dirty": self.dirty,
                    "isBuiltin": self.active is None}

    def sv_dir(self) -> Path | None:
        with self.lock:
            return (CPU_DIR / self.active) if self.active else None

    def mark_built(self):
        with self.lock:
            self.dirty = False


CPUS = CPUState()


def save_cpu(name: str, files: list[dict]) -> dict:
    folder = safe_folder(name)
    dest = CPU_DIR / folder
    dest.mkdir(parents=True, exist_ok=True)
    for f in dest.glob("*.sv"):
        f.unlink()
    saved = 0
    has_top = False
    for f in files:
        fname = safe_folder(Path(f.get("name", "")).stem) + ".sv"
        content = f.get("content", "")
        (dest / fname).write_text(content)
        saved += 1
        if "module SingleCycleCPU" in content:
            has_top = True
    return {"name": folder, "files": saved, "hasTopModule": has_top}


def list_cpus() -> list[dict]:
    active = CPUS.snapshot()["active"]
    out = [{"name": "__builtin__", "label": "Built-in DINO (Chisel)",
            "builtin": True, "active": active is None, "files": 0}]
    if CPU_DIR.exists():
        for d in sorted(CPU_DIR.iterdir()):
            if d.is_dir():
                out.append({"name": d.name, "label": d.name, "builtin": False,
                            "active": active == d.name, "files": len(list(d.glob("*.sv")))})
    return out


def builtin_sv() -> list[dict]:
    """The built-in DINO Verilog, as a downloadable sample custom CPU."""
    src = BUILTIN_SV if any(BUILTIN_SV.glob("*.sv")) else (COSIM / "build" / "dino_verilator")
    return [{"name": f.name, "content": f.read_text(errors="replace")}
            for f in sorted(src.glob("*.sv"))]


# --------------------------------------------------------------------- jobs ---
class Job:
    def __init__(self, job_id: str, kind: str, params: dict):
        self.id, self.kind, self.params = job_id, kind, params
        self.status = "queued"
        self.log: list[str] = []
        self.run: dict | None = None
        self.error: str | None = None
        self._lock = threading.Lock()

    def append(self, line: str):
        with self._lock:
            self.log.append(line.rstrip("\n"))

    def snapshot(self, since: int = 0) -> dict:
        with self._lock:
            return {"id": self.id, "kind": self.kind, "status": self.status,
                    "log": self.log[since:], "logLen": len(self.log),
                    "run": self.run, "error": self.error}


JOBS: dict[str, Job] = {}
JOB_QUEUE: "queue.Queue[Job]" = queue.Queue()
_counter = 0
_counter_lock = threading.Lock()


def new_job(kind: str, params: dict) -> Job:
    global _counter
    with _counter_lock:
        _counter += 1
        job_id = f"{kind}_{int(time.time())}_{_counter}"
    job = Job(job_id, kind, params)
    JOBS[job_id] = job
    JOB_QUEUE.put(job)
    return job


def stream(job: Job, cmd: list, env: dict, cwd: Path) -> int:
    job.append(f"$ {' '.join(str(c) for c in cmd)}")
    proc = subprocess.Popen(cmd, cwd=str(cwd), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, bufsize=1)
    for line in proc.stdout:
        job.append(line)
    proc.wait()
    return proc.returncode


def run_generate(job: Job):
    p = job.params
    folder = safe_folder(p.get("name", ""))
    tests = int(p.get("tests", 10))
    instr = int(p.get("instrCnt", 250))
    ttype = p.get("type", "mixed")
    if ttype not in TYPES:
        raise ValueError(f"unknown type '{ttype}'")

    dest = TESTS_DIR / folder
    dest.mkdir(parents=True, exist_ok=True)

    # Append rather than overwrite: gen_tests.sh always numbers programs from _0,
    # so generating into an existing folder would clobber the previous batch.
    # Generate into a temp dir, then move the new programs in with their numbers
    # continued past what's already there. Re-run with the same name to grow a
    # folder; use a new name for a separate one.
    def index_of(path: Path) -> int:
        m = re.search(r"_(\d+)\.S$", path.name)
        return int(m.group(1)) if m else -1

    existing = sorted(dest.glob("*.S"))
    next_idx = max((index_of(p) for p in existing), default=-1) + 1

    tmp = Path(tempfile.mkdtemp(prefix="gen-", dir=str(TESTS_DIR)))
    try:
        env = child_env()
        env.update(TESTS=str(tests), INSTR_CNT=str(instr), TYPE=ttype, DEST=str(tmp))
        job.append(
            f"[generate] folder '{folder}': +{tests} test(s), {instr} instr, type={ttype}"
            + (f" (appending to {len(existing)} existing)" if existing else ""))
        rc = stream(job, ["bash", str(GEN)], env, ROOT)
        if rc != 0:
            raise RuntimeError(f"gen_tests.sh exited {rc}")
        new_files = sorted(tmp.glob("*.S"), key=index_of)
        for i, f in enumerate(new_files):
            shutil.move(str(f), str(dest / f"{TEST}_{next_idx + i}.S"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = len(list(dest.glob("*.S")))
    job.run = {"folder": folder, "count": total, "added": len(new_files)}
    job.append(f"[done] folder '{folder}' now has {total} tests (+{len(new_files)})")


def run_folder(job: Job):
    p = job.params
    folder = safe_folder(p.get("folder", ""))
    steps = int(p.get("steps", 80))
    dest = TESTS_DIR / folder
    if not dest.is_dir() or not any(dest.glob("*.S")):
        raise RuntimeError(f"folder '{folder}' has no tests")

    label = BUGS.label()
    bug_state = BUGS.snapshot()
    cpu = CPUS.snapshot()
    env = child_env()
    env.update(STEPS=str(steps), JOBS="4", RUN_ID=job.id, KEEP_GOING="1")

    sv_dir = CPUS.sv_dir()
    if sv_dir is not None:
        env["CPU_SV"] = str(sv_dir)
        job.append(f"[cosim] custom CPU '{cpu['active']}'")
    if label:
        env["MUTATION_LABEL"] = label
    # Rebuild when the CPU source changed (bug injected/reset) or the active CPU
    # switched. Custom vs built-in produce different Verilog either way.
    if bug_state["rtlDirty"] or cpu["dirty"]:
        env["REBUILD"] = "1"
        job.append("[cosim] CPU changed; rebuilding")

    who = cpu["active"] or "built-in DINO"
    job.append(f"[cosim] running folder '{folder}' at {steps} steps vs Spike"
               + f" — CPU: {who}" + (f", bugs: {label}" if label else ""))
    rc = stream(job, ["bash", str(RUN_COSIM), str(dest)], env, ROOT)
    if rc not in (0, 1):
        raise RuntimeError(f"run_cosim.sh exited {rc}")
    BUGS.mark_built()
    CPUS.mark_built()
    job.run = load_campaign(job.id)
    job.append(f"[done] {job.run.get('passed')}/{job.run.get('totalTests')} passed")


def worker():
    while True:
        job = JOB_QUEUE.get()
        job.status = "running"
        try:
            {"generate": run_generate, "run": run_folder}[job.kind](job)
            job.status = "done"
        except Exception as exc:  # noqa: BLE001
            job.status = "error"
            job.error = str(exc)
            job.append(f"[error] {exc}")
        finally:
            JOB_QUEUE.task_done()


# ----------------------------------------------------------- library + runs ---
def load_campaign(run_id: str) -> dict:
    return json.loads((CAMPAIGN_DIR / f"{run_id}.json").read_text())


def list_folders() -> list[dict]:
    out = []
    if TESTS_DIR.exists():
        for d in sorted(TESTS_DIR.iterdir()):
            if not d.is_dir():
                continue
            tests = sorted(d.glob("*.S"))
            out.append({"name": d.name, "count": len(tests),
                        "modified": int(d.stat().st_mtime)})
    out.sort(key=lambda f: f["modified"], reverse=True)
    return out


def folder_detail(name: str) -> dict:
    d = TESTS_DIR / safe_folder(name)
    if not d.is_dir():
        return {"name": name, "tests": []}
    tests = []
    for f in sorted(d.glob("*.S")):
        body = f.read_text(errors="replace")
        instrs = sum(1 for ln in body.splitlines()
                     if ln.strip() and not ln.strip().startswith(("#", ".", "_")) and ":" not in ln)
        tests.append({"name": f.name, "instrCount": instrs})
    return {"name": d.name, "tests": tests}


def list_runs() -> list[dict]:
    out = []
    if CAMPAIGN_DIR.exists():
        for path in CAMPAIGN_DIR.glob("*.json"):
            if path.name == "mutation_campaign_index.json":
                continue
            try:
                d = json.loads(path.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            if "runId" not in d or "tests" not in d:
                continue
            out.append({"runId": d.get("runId"), "timestamp": d.get("timestamp"),
                        "totalTests": d.get("totalTests", len(d.get("tests", []))),
                        "passed": d.get("passed"), "failed": d.get("failed"),
                        "mutationLabel": d.get("mutationLabel")})
    out.sort(key=lambda r: r.get("timestamp") or "", reverse=True)
    return out


def list_mutations() -> list[dict]:
    out = []
    for m in RMC.MUTATIONS:
        funcs = sorted(fn for fn, target in RMC.FUNCTION_CHOICES.items() if target == m.name)
        out.append({"name": m.name, "functions": funcs,
                    "function": funcs[0] if funcs else m.name, "description": m.description})
    return out


# ------------------------------------------------------------------- server ---
class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):
        pass

    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def _json(self, obj, status=200):
        body = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self._cors()
        self.end_headers()
        self.wfile.write(body)

    def _body(self) -> dict:
        n = int(self.headers.get("Content-Length", "0"))
        if not n:
            return {}
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except json.JSONDecodeError:
            return {}

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self._json({"ok": True, "types": TYPES,
                               "tools": {t: have(t) for t in
                                         ["sbt", "verilator", "spike", "riscv64-elf-gcc",
                                          "riscv64-unknown-elf-gcc"]},
                               "mutations": len(list_mutations())})
        if path == "/api/mutations":
            return self._json(list_mutations())
        if path == "/api/injected":
            return self._json(BUGS.snapshot())
        if path == "/api/cpus":
            return self._json({"cpus": list_cpus(), **CPUS.snapshot()})
        if path == "/api/cpu/sample":
            return self._json({"name": "dino-sample", "files": builtin_sv()})
        if path == "/api/folders":
            return self._json(list_folders())
        if path.startswith("/api/folders/"):
            return self._json(folder_detail(unquote(path[len("/api/folders/"):])))
        if path == "/api/runs":
            return self._json(list_runs())
        if path.startswith("/api/runs/"):
            try:
                return self._json(load_campaign(unquote(path[len("/api/runs/"):])))
            except (OSError, json.JSONDecodeError):
                return self._json({"error": "run not found"}, 404)
        if path.startswith("/api/jobs/"):
            job = JOBS.get(path[len("/api/jobs/"):])
            if not job:
                return self._json({"error": "job not found"}, 404)
            since = int(self.path.split("since=")[-1]) if "since=" in self.path else 0
            return self._json(job.snapshot(since))
        return self._serve_static(path)

    def do_POST(self):
        path = urlparse(self.path).path
        if path == "/api/generate":
            return self._json({"jobId": new_job("generate", self._body()).id})
        if path == "/api/run":
            return self._json({"jobId": new_job("run", self._body()).id})
        if path == "/api/inject":
            res = BUGS.inject(self._body().get("function", ""))
            return self._json(res, 200 if res.get("ok") else 400)
        if path == "/api/reset":
            return self._json(BUGS.reset())
        if path == "/api/cpu":
            body = self._body()
            files = body.get("files", [])
            if not files:
                return self._json({"error": "no .sv files provided"}, 400)
            saved = save_cpu(body.get("name", "custom"), files)
            if not saved["hasTopModule"]:
                return self._json(
                    {"error": "no 'module SingleCycleCPU' found in the uploaded files; "
                              "the top module must be named SingleCycleCPU", **saved}, 400)
            CPUS.select(saved["name"])
            return self._json({"ok": True, **saved, **CPUS.snapshot()})
        if path == "/api/cpu/select":
            return self._json(CPUS.select(self._body().get("name")))
        return self._json({"error": "not found"}, 404)

    def _serve_static(self, path):
        if not STATIC_DIR.exists():
            return self._json({"error": "no built dashboard; run serve.sh or npm run build",
                               "hint": "the API is up at /api/*"}, 404)
        rel = path.lstrip("/") or "index.html"
        target = (STATIC_DIR / rel).resolve()
        if not str(target).startswith(str(STATIC_DIR)) or not target.is_file():
            target = STATIC_DIR / "index.html"
        data = target.read_bytes()
        ctype = {".html": "text/html", ".js": "text/javascript", ".css": "text/css",
                 ".json": "application/json", ".svg": "image/svg+xml"}.get(
                     target.suffix, "application/octet-stream")
        self.send_response(200)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self._cors()
        self.end_headers()
        self.wfile.write(data)


def main():
    CAMPAIGN_DIR.mkdir(parents=True, exist_ok=True)
    TESTS_DIR.mkdir(parents=True, exist_ok=True)
    CPU_DIR.mkdir(parents=True, exist_ok=True)
    threading.Thread(target=worker, daemon=True).start()
    print(f"[webapp] backend on http://{HOST}:{PORT}  (api at /api/*)")
    print("[webapp] tools: " + ", ".join(
        f"{t}={'ok' if have(t) else 'MISSING'}"
        for t in ["sbt", "verilator", "spike", "riscv64-elf-gcc"]))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
