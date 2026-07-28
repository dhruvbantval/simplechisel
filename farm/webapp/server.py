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

import hashlib
import importlib.util
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse

ROOT = Path(__file__).resolve().parents[2]
FARM = ROOT / "farm"                                # the domain-agnostic farm
COSIM = ROOT / "cosim"                              # the CPU experiment's tools
GEN = COSIM / "generator" / "gen_tests.sh"
RUN_COSIM = COSIM / "run_cosim.sh"
MUTATION_PY = COSIM / "mutation" / "run_mutation_campaign.py"
CAMPAIGN_DIR = COSIM / "build" / "campaigns"
TESTS_DIR = COSIM / "build" / "webapp" / "tests"   # the persistent test library
CPU_DIR = COSIM / "build" / "webapp" / "cpu"        # uploaded custom CPUs
BUILTIN_SV = ROOT / "build_singlecyclecpu_nd"       # DINO's generated Verilog
STATIC_DIR = Path(__file__).resolve().parent / "static"
FARM_VENV = FARM / ".venv" / "bin" / "python"       # experiment deps live here
PY = str(FARM_VENV) if FARM_VENV.exists() else sys.executable

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
COMPILER_CORPUS = FARM / "adapters" / "corpus" / "compiler"

# The experiment registry comes from farm.yaml -- adding a science is a block in
# that file plus an adapter, with no change here.
def load_experiments() -> list:
    try:
        from farm.config import experiments as _experiments, load_config
        return _experiments(load_config())
    except Exception as exc:  # noqa: BLE001 - degrade gracefully if PyYAML is absent
        print(f"[webapp] could not read farm.yaml ({exc}); falling back to cosim only")
        return [{"type": "cosim", "label": "CPU cosim", "dut": "DINO CPU",
                 "golden": "Spike", "ui": "cosim"}]


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

# The farm core: every run is also written to the domain-agnostic record store as
# universal ExperimentRecords, so the dashboard's future cross-domain / regression
# views read one unified store instead of cosim-specific campaigns.
sys.path.insert(0, str(ROOT))
from farm.adapters import ADAPTERS, CosimAdapter  # noqa: E402
from farm.store import RecordStore                # noqa: E402
from farm.runner import run_experiments           # noqa: E402
from farm.run_experiment import version_of        # noqa: E402

COSIM_ADAPTER = CosimAdapter()
FARM_STORE = RecordStore(FARM / "build" / "records")


def cpu_source_sha() -> str:
    """A version fingerprint for the CPU under test, so the regression trend can
    key on it. Built-in DINO -> its git commit, with any injected bugs appended
    (an injected bug is a distinct 'version', which is how a regression shows up
    on the trend). A custom upload -> a content hash of its .sv files."""
    cpu = CPUS.snapshot()
    if cpu["active"] is None:
        try:
            out = subprocess.run(["git", "rev-parse", "--short", "HEAD"],
                                 cwd=str(ROOT), capture_output=True, text=True)
            sha = out.stdout.strip() or "unknown"
        except OSError:
            sha = "unknown"
        funcs = sorted(b["function"] for b in BUGS.snapshot()["injected"])
        return sha + ("+" + "+".join(funcs) if funcs else "")
    h = hashlib.sha256()
    for f in sorted((CPU_DIR / cpu["active"]).glob("*.sv")):
        h.update(f.read_bytes())
    return "up-" + h.hexdigest()[:8]


def cpu_build_id() -> str:
    """Content fingerprint of the CPU actually being built.

    cpu_source_sha() is a *readable label* (commit + injected bugs) for the trend;
    it can be identical for two different builds if the source was modified in a
    way we didn't track. The build stamp must never lie, so it hashes the real
    bytes -- any edit at all produces a different id and forces a rebuild."""
    cpu = CPUS.snapshot()
    h = hashlib.sha256()
    if cpu["active"] is None:
        for f in sorted((ROOT / "src" / "main" / "scala").rglob("*.scala")):
            h.update(f.read_bytes())
    else:
        for f in sorted((CPU_DIR / cpu["active"]).glob("*.sv")):
            h.update(f.read_bytes())
    return h.hexdigest()[:16]


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

    def detect_applied(self) -> list:
        """Which mutations are physically present in the source right now.

        The in-memory pristine backups die with the process, so after a restart we
        can still tell what's injected by looking for each mutation's edited text.
        Without this a killed server leaves a silently-buggy CPU behind."""
        found = []
        for m in RMC.MUTATIONS:
            try:
                if all((ROOT / rel).read_text(encoding="utf-8").count(new) >= 1
                       for rel, _old, new in m.edits):
                    funcs = sorted(fn for fn, t in RMC.FUNCTION_CHOICES.items()
                                   if t == m.name)
                    found.append({"name": m.name,
                                  "function": funcs[0] if funcs else m.name,
                                  "description": m.description})
            except OSError:
                continue
        return found

    def adopt_existing(self) -> list:
        """At startup, treat already-applied mutations as injected so the UI is honest."""
        with self.lock:
            self.injected = self.detect_applied()
            if self.injected:
                self.rtl_dirty = True
            return list(self.injected)

    def reset(self) -> dict:
        with self.lock:
            for path, data in self.pristine.items():
                path.write_bytes(data)
            self.pristine.clear()
            # Undo anything still present by reversing the edit. This is what makes
            # Reset work after a restart, when the backups above are gone.
            for m in RMC.MUTATIONS:
                for rel, old, new in m.edits:
                    path = ROOT / rel
                    try:
                        text = path.read_text(encoding="utf-8")
                    except OSError:
                        continue
                    if new in text:
                        path.write_text(text.replace(new, old), encoding="utf-8")
            self.injected.clear()
            self.rtl_dirty = True   # next run rebuilds a clean CPU
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
    # Stamp the build with the exact CPU version so run_cosim.sh rebuilds whenever
    # the on-disk sim was built from a different CPU (survives server restarts,
    # unlike the in-memory dirty flag below).
    env["BUILD_ID"] = cpu_build_id()
    # Belt-and-suspenders: also force a rebuild when we know the CPU changed this
    # session (bug injected/reset, or the active CPU switched).
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

    # Also record this run in the universal farm store (cosim as the first
    # adapter). One ExperimentRecord per test program.
    try:
        recs = COSIM_ADAPTER.records_from_campaign(
            job.run, source_sha=cpu_source_sha(), cpu=(cpu["active"] or "built-in"),
            tests_dir=str(dest))
        stored = FARM_STORE.save_many(recs)
        job.append(f"[farm] stored {stored} experiment record(s)")
    except Exception as exc:  # noqa: BLE001 -- never fail a run over bookkeeping
        job.append(f"[farm] record ingest skipped: {exc}")

    job.append(f"[done] {job.run.get('passed')}/{job.run.get('totalTests')} passed")


def run_campaign(job: Job):
    """Run any config-driven experiment's campaign (control, ecg, physics,
    compiler-diff...). Generic: it just invokes run_experiment.py for that type,
    which reads farm.yaml. Records land in the shared store."""
    exp_type = job.params.get("type", "")
    env = child_env()
    job.append(f"[{exp_type}] running campaign from farm.yaml")
    rc = stream(job, [PY, str(FARM / "run_experiment.py"), exp_type], env, ROOT)
    if rc != 0:
        raise RuntimeError(f"{exp_type} campaign exited {rc}")
    recs = [r for r in FARM_STORE.all() if r.get("type") == exp_type]
    passed = sum(1 for r in recs if r.get("status") == "pass")
    job.run = {"type": exp_type, "passed": passed, "totalTests": len(recs)}
    job.append(f"[done] {passed}/{len(recs)} passed")


def run_uploaded(job: Job):
    """Run a single uploaded case (a controller, a C program, ...) in-process
    through its adapter. Used by the website's upload buttons so any file-input
    experiment can be tested end to end without touching the filesystem by hand."""
    from farm.config import experiment, load_config
    exp_type = job.params["type"]
    case = job.params["case"]
    adapter = ADAPTERS.get(exp_type)
    exp = experiment(exp_type, load_config())
    if not adapter or not exp:
        raise RuntimeError(f"no adapter/experiment for '{exp_type}'")
    sha = version_of(exp)
    job.append(f"[{exp_type}] running uploaded case '{case.get('name')}'  @ {sha}")
    recs = run_experiments(adapter, [case], FARM_STORE, source_sha=sha,
                           on_log=lambda line: job.append(line))
    r = recs[0].to_dict()
    job.run = {"type": exp_type, "status": r["status"], "detail": r["detail"],
               "passed": 1 if r["status"] == "pass" else 0, "totalTests": 1}
    job.append(f"[done] {r['status']}: {r['detail']}")


def worker():
    while True:
        job = JOB_QUEUE.get()
        job.status = "running"
        try:
            {"generate": run_generate, "run": run_folder,
             "campaign": run_campaign, "uploaded": run_uploaded}[job.kind](job)
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
        if path == "/api/experiments":
            return self._json(load_experiments())
        if path.startswith("/api/campaign/") and path.endswith("/cases"):
            t = unquote(path[len("/api/campaign/"):-len("/cases")])
            try:
                from farm.config import cases_for, experiment, load_config
                exp = experiment(t, load_config())
                return self._json({"cases": cases_for(exp) if exp else []})
            except Exception as exc:  # noqa: BLE001
                return self._json({"cases": [], "error": str(exc)})
        if path == "/api/records":
            return self._json(FARM_STORE.all())
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
        if path == "/api/upload-tests":
            return self._upload_tests(self._body())
        if path == "/api/run":
            return self._json({"jobId": new_job("run", self._body()).id})
        if path == "/api/campaign/run":
            return self._json({"jobId": new_job("campaign", self._body()).id})
        if path.startswith("/api/campaign/") and path.endswith("/upload"):
            t = unquote(path[len("/api/campaign/"):-len("/upload")])
            return self._upload_case(t, self._body())
        if path.startswith("/api/campaign/") and path.endswith("/custom"):
            t = unquote(path[len("/api/campaign/"):-len("/custom")])
            return self._custom_case(t, self._body())
        if path.startswith("/api/campaign/") and path.endswith("/generate"):
            t = unquote(path[len("/api/campaign/"):-len("/generate")])
            return self._generate(t, self._body())
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

    def _upload_case(self, exp_type, body):
        """Save an uploaded input file and run it as one case, driven by the
        experiment's `upload:` block in farm.yaml."""
        from farm.config import experiment, load_config
        exp = experiment(exp_type, load_config())
        up = (exp or {}).get("upload")
        if not up:
            return self._json({"error": f"'{exp_type}' has no upload configured"}, 400)

        # Accept a single file (content) or several (files: [{name, content}]).
        # Multiple is for sources that come in pieces -- e.g. C's PID.c + PID.h.
        files = body.get("files")
        if not files:
            if not (body.get("content") or "").strip():
                return self._json({"error": "empty file"}, 400)
            nm = body.get("name", "upload")
            if "." not in Path(nm).name:   # no extension given: default to Python
                nm += ".py"
            files = [{"name": nm, "content": body["content"]}]

        import base64
        b64 = body.get("encoding") == "base64"

        def decode(content):
            if b64:
                return base64.b64decode(content)
            return content.encode() if isinstance(content, str) else content

        keep_names = up.get("keep_names")
        stems = {Path(f.get("name", "")).stem for f in files}
        base = safe_folder(sorted(stems)[0]) if stems else "upload"
        dest_dir = ROOT / up["dir"]
        # keep_names writes files exactly (WFDB needs <rec>.dat/.hea/.atr together);
        # otherwise a multi-file set gets its own subfolder.
        if len(files) > 1 and not keep_names:
            dest_dir = dest_dir / base
        dest_dir.mkdir(parents=True, exist_ok=True)

        saved = []
        for f in files:
            fn = Path(f.get("name", "file")).name
            if keep_names:
                p = dest_dir / fn
            else:
                p = dest_dir / f"{safe_folder(Path(fn).stem)}{Path(fn).suffix}"
            p.write_bytes(decode(f.get("content", "")))
            saved.append(p)

        if up.get("key_from") == "basename":
            key_value = sorted(stems)[0] if len(stems) == 1 else base
        else:
            # entry file: a Python controller, else the C source with the update fn,
            # else the first non-header file
            entry = next((p for p in saved if p.suffix == ".py"), None)
            if entry is None:
                entry = next((p for p in saved if p.suffix == ".c"
                              and "PIDController_Update" in p.read_text(errors="replace")), None)
            if entry is None:
                entry = next((p for p in saved if p.suffix != ".h"), saved[0])
            key_value = str(entry.relative_to(ROOT))

        case = {"name": base, up["case_key"]: key_value}
        for p in up.get("params", []):
            key = p["name"]
            if key in (body.get("params") or {}):
                case[key] = body["params"][key]
            elif "default" in p:
                case[key] = p["default"]
        job = new_job("uploaded", {"type": exp_type, "case": case})
        return self._json({"jobId": job.id})

    def _upload_tests(self, body):
        """Save uploaded RISC-V .S programs as a cosim test folder, so your own
        programs show up in the Run dropdown next to generated ones."""
        folder = safe_folder(body.get("folder", "my-tests"))
        files = body.get("files", [])
        if not files:
            return self._json({"error": "no .S files provided"}, 400)
        dest = TESTS_DIR / folder
        dest.mkdir(parents=True, exist_ok=True)
        for f in files:
            stem = safe_folder(Path(f.get("name", "prog")).stem)
            (dest / f"{stem}.S").write_text(f.get("content", ""))
        return self._json({"folder": folder, "count": len(list(dest.glob("*.S")))})

    def _custom_case(self, exp_type, body):
        """Run a one-off case built from form parameters (no file) — for experiments
        whose inputs are values, not files (a circuit's R/C, an ECG record id)."""
        from farm.config import experiment, load_config
        exp = experiment(exp_type, load_config())
        cc = (exp or {}).get("custom_case")
        if not cc:
            return self._json({"error": f"'{exp_type}' has no custom case configured"}, 400)
        given = body.get("params") or {}
        case = {}
        for p in cc.get("params", []):
            case[p["name"]] = given.get(p["name"], p.get("default"))
        case["name"] = ", ".join(f"{k}={v}" for k, v in case.items()) or "custom"
        job = new_job("uploaded", {"type": exp_type, "case": case})
        return self._json({"jobId": job.id})

    def _generate(self, exp_type, body):
        """Run an experiment's generator to synthesize N test cases and save them,
        so they show up in the case list and run alongside the configured cases.
        Driven by the experiment's `generate:` block in farm.yaml."""
        from farm.config import experiment, load_config, GENERATED_DIR
        exp = experiment(exp_type, load_config())
        gen = (exp or {}).get("generate")
        if not gen:
            return self._json({"error": f"'{exp_type}' has no generator configured"}, 400)

        default = gen.get("default", 5)
        try:
            count = int((body.get("params") or {}).get("count", body.get("count", default)))
        except (TypeError, ValueError):
            count = default
        count = max(1, min(count, 50))

        script = ROOT / gen["script"]
        proc = subprocess.run([PY, str(script), str(count)],
                              capture_output=True, text=True, cwd=str(ROOT))
        if proc.returncode != 0:
            return self._json(
                {"error": f"generator failed: {(proc.stderr or proc.stdout)[-500:]}"}, 500)
        try:
            cases = json.loads(proc.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return self._json(
                {"error": f"generator produced no JSON: {proc.stdout[-300:]}"}, 500)

        GENERATED_DIR.mkdir(parents=True, exist_ok=True)
        (GENERATED_DIR / f"{exp_type}.json").write_text(json.dumps(cases, indent=2))
        return self._json({"type": exp_type, "count": len(cases), "cases": cases})

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
    leftover = BUGS.adopt_existing()
    if leftover:
        print("[webapp] WARNING: the CPU source still has injected bug(s): "
              + ", ".join(b["name"] for b in leftover))
        print("[webapp]          hit Reset in the UI (or: git checkout -- src/main/scala/)")
    threading.Thread(target=worker, daemon=True).start()
    print(f"[webapp] backend on http://{HOST}:{PORT}  (api at /api/*)")
    print("[webapp] tools: " + ", ".join(
        f"{t}={'ok' if have(t) else 'MISSING'}"
        for t in ["sbt", "verilator", "spike", "riscv64-elf-gcc"]))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
