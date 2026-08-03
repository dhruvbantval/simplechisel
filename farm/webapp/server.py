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
from urllib.parse import parse_qs, unquote, urlparse

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
# experiment deps live here; posix venvs use bin/, Windows venvs Scripts/
FARM_VENV = next((p for p in (FARM / ".venv" / "bin" / "python",
                              FARM / ".venv" / "Scripts" / "python.exe") if p.exists()), None)
PY = str(FARM_VENV) if FARM_VENV else sys.executable

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
        from farm.config import experiments as _experiments, load_config, venv_python
        exps = _experiments(load_config())
        # `setup:` is shown to the user as a command to run, so spell the
        # interpreter for this platform rather than hardcoding a posix path.
        for e in exps:
            if isinstance(e.get("setup"), str):
                e["setup"] = e["setup"].replace("{python}", venv_python())
        return exps
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
    # children must write UTF-8 too; a piped python otherwise uses the locale codec
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def have(tool: str) -> bool:
    exts = ["", ".exe", ".bat", ".cmd"] if os.name == "nt" else [""]
    return any((Path(d) / f"{tool}{e}").exists()
               for d in child_env()["PATH"].split(os.pathsep) for e in exts)


def sh(p) -> str:
    """A path in the form bash understands.

    Windows backslashes are eaten as escapes by bash; forward slashes with a
    drive letter work. No-op on posix.
    """
    return Path(p).as_posix()


def bash_exe() -> str:
    """Path to an MSYS/Git bash that can see this repo.

    On Windows, CreateProcess searches System32 before PATH, so a bare "bash"
    resolves to the WSL launcher, which cannot open 'C:/repo/x.sh'. Resolve a
    real MSYS bash by path instead. FARM_BASH overrides.
    """
    override = os.environ.get("FARM_BASH")
    if override and Path(override).exists():
        return override
    if os.name != "nt":
        return "bash"

    system32 = (Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32").resolve()
    candidates = []
    found = shutil.which("bash")
    if found:
        candidates.append(Path(found))
    for base in (os.environ.get("ProgramFiles", r"C:\Program Files"),
                 os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"),
                 os.environ.get("LOCALAPPDATA", "")):
        if base:
            candidates += [Path(base) / "Git" / "bin" / "bash.exe",
                           Path(base) / "Git" / "usr" / "bin" / "bash.exe"]
    for c in candidates:
        try:
            if c.exists() and c.resolve().parent != system32:
                return str(c)
        except OSError:
            continue
    return "bash"


BASH = bash_exe()


def to_wsl_path(p) -> str:
    """C:\\a\\b -> /mnt/c/a/b, the same file as seen from inside WSL."""
    p = Path(p).resolve()
    drive = p.drive.rstrip(":").lower()
    rest = p.as_posix()[len(p.drive):].lstrip("/")
    return f"/mnt/{drive}/{rest}" if drive else p.as_posix()


def wsl_available() -> bool:
    """True if WSL is installed with a usable default distro. Cached."""
    global _WSL_OK
    if _WSL_OK is None:
        _WSL_OK = False
        if os.name == "nt":
            try:
                out = subprocess.run(["wsl", "-e", "bash", "-lc", "echo ok"],
                                     capture_output=True, timeout=25)
                # wsl.exe emits UTF-16 for its own messages; the payload is ascii
                text = out.stdout.decode("utf-8", "ignore").replace("\x00", "")
                _WSL_OK = out.returncode == 0 and "ok" in text
            except (OSError, subprocess.SubprocessError):
                _WSL_OK = False
    return _WSL_OK


_WSL_OK = None


def wsl_command(cwd: Path, script: Path, env_vars: dict, args=()) -> list:
    """Run a repo script inside WSL with the given environment.

    The whole cosim toolchain is Linux-only (riscv-dv's pyvsc dependency has no
    Windows wheel; verilator, spike and the RISC-V gcc have no Windows builds),
    so on Windows it runs under WSL against this same checkout over /mnt/c. The
    riscv-dv venv lives in WSL's own filesystem: it holds Linux binaries, and
    DrvFs is slow for many small files.
    """
    assign = " ".join(f"{k}='{v}'" for k, v in env_vars.items())
    argv = " ".join(f"'{a}'" for a in args)
    inner = (f"cd '{to_wsl_path(cwd)}' && "
             f"VENV=\"$HOME/.cache/dino-riscv-dv-venv\" {assign} "
             f"bash '{to_wsl_path(script)}' {argv}".rstrip())
    return ["wsl", "-e", "bash", "-lc", inner]


# Install commands per platform. Mirrors farm/README.md and installHints.js.
def _install_hints() -> dict:
    if sys.platform == "darwin":
        return {"clang": "xcode-select --install",
                "ngspice": "brew install ngspice",
                "verilator": "brew install verilator",
                "spike": "brew install riscv-isa-sim",
                "riscv64-elf-gcc": "brew install riscv64-elf-gcc riscv64-elf-binutils",
                "sbt": "brew install sbt"}
    if os.name == "nt":
        return {"clang": "winget install LLVM.LLVM",
                "ngspice": "choco install ngspice",
                "verilator": "wsl -- sudo apt install -y verilator",
                "spike": "bash cosim/install_spike.sh   (run inside WSL)",
                "riscv64-elf-gcc": "wsl -- sudo apt install -y gcc-riscv64-unknown-elf",
                "sbt": "winget install sbt.sbt"}
    return {"clang": "sudo apt install -y clang",
            "ngspice": "sudo apt install -y ngspice",
            "verilator": "sudo apt install -y verilator",
            "spike": "bash cosim/install_spike.sh",
            "riscv64-elf-gcc": "sudo apt install -y gcc-riscv64-unknown-elf",
            "sbt": "see scala-sbt.org/download"}


INSTALL_HINTS = _install_hints()


# Tools that are satisfied by any one of several executables. run_cosim.sh picks
# whichever RISC-V gcc prefix is present, so detection has to accept both.
TOOL_ALIASES = {
    "riscv64-elf-gcc": ("riscv64-elf-gcc", "riscv64-unknown-elf-gcc"),
    "riscv64-unknown-elf-gcc": ("riscv64-unknown-elf-gcc", "riscv64-elf-gcc"),
}

_WSL_TOOLS: set | None = None


def wsl_tools() -> set:
    """Names of the cosim toolchain executables present inside WSL. Cached."""
    global _WSL_TOOLS
    if _WSL_TOOLS is None:
        _WSL_TOOLS = set()
        if wsl_available():
            names = ["verilator", "spike", "riscv64-unknown-elf-gcc",
                     "riscv64-elf-gcc", "sbt", "python3"]
            probe = "; ".join(f"command -v {n} >/dev/null 2>&1 && echo {n}" for n in names)
            try:
                out = subprocess.run(["wsl", "-e", "bash", "-lc", probe],
                                     capture_output=True, timeout=60)
                text = out.stdout.decode("utf-8", "ignore").replace("\x00", "")
                _WSL_TOOLS = {ln.strip() for ln in text.splitlines() if ln.strip()}
            except (OSError, subprocess.SubprocessError):
                _WSL_TOOLS = set()
    return _WSL_TOOLS


def runs_in_wsl(exp_type: str) -> bool:
    """True when an experiment executes inside WSL rather than natively.

    cosim's toolchain (riscv-dv, verilator, spike, the RISC-V cross-compiler) has
    no Windows build, so on Windows both generation and runs go through WSL.
    """
    return os.name == "nt" and exp_type == "cosim" and wsl_available()


def _tool_present(tool: str, in_wsl: bool) -> bool:
    names = TOOL_ALIASES.get(tool, (tool,))
    if in_wsl:
        available = wsl_tools()
        return any(n in available for n in names)
    return any(have(n) for n in names)


def missing_tools(exp_type: str) -> list:
    """Tools an experiment declares in farm.yaml (`system:`) that aren't available.

    Looked up wherever the experiment will actually run: inside WSL for cosim on
    Windows, on the host PATH otherwise.
    """
    in_wsl = runs_in_wsl(exp_type)
    for e in load_experiments():
        if e.get("type") == exp_type:
            return [t for t in (e.get("system") or []) if not _tool_present(t, in_wsl)]
    return []


def experiment_tools() -> dict:
    """Per-experiment tool availability, keyed by experiment type."""
    out = {}
    for e in load_experiments():
        exp_type = e["type"]
        tools = e.get("system") or []
        in_wsl = runs_in_wsl(exp_type)
        out[exp_type] = {
            "tools": {t: _tool_present(t, in_wsl) for t in tools},
            "missing": [t for t in tools if not _tool_present(t, in_wsl)],
            "wsl": in_wsl,
        }
    return out


FOLDER_NAME_MAX = 64      # keeps the full path well inside Windows' MAX_PATH


def safe_folder(name: str) -> str:
    """A filesystem-safe folder name (no traversal, no separators, bounded length)."""
    keep = "".join(c if (c.isalnum() or c in "-_") else "-" for c in (name or "").strip())
    return keep.strip("-")[:FOLDER_NAME_MAX].strip("-") or f"batch-{int(time.time())}"


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
                                 cwd=str(ROOT), capture_output=True, text=True,
                                 encoding="utf-8", errors="replace")
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
        self.lane = ""
        self.log: list[str] = []
        self.run: dict | None = None
        self.error: str | None = None
        self._lock = threading.Lock()

    def append(self, line: str):
        with self._lock:
            # strip \r as well, so CRLF output does not leave a trailing CR
            self.log.append(line.rstrip("\r\n"))

    def snapshot(self, since: int = 0) -> dict:
        with self._lock:
            return {"id": self.id, "kind": self.kind, "status": self.status,
                    "log": self.log[since:], "logLen": len(self.log),
                    "run": self.run, "error": self.error}


JOBS: dict[str, Job] = {}
_counter = 0
_counter_lock = threading.Lock()

# Jobs are serialized per lane and run in parallel across lanes, so a long cosim
# run does not block the other experiments.
#
# Everything cosim shares one lane: generation and runs both touch the riscv-dv
# checkout, the CPU source (bug injection) and the Verilator build, so they must
# not overlap. Each campaign experiment gets its own lane -- they only share the
# record store, which is one file per record.
JOB_LANES: dict[str, "queue.Queue[Job]"] = {}
_LANES_LOCK = threading.Lock()


def lane_for(kind: str, params: dict) -> str:
    if kind in ("generate", "run"):
        return "cosim"
    return f"campaign:{params.get('type', 'unknown')}"


def new_job(kind: str, params: dict) -> Job:
    global _counter
    with _counter_lock:
        _counter += 1
        job_id = f"{kind}_{int(time.time())}_{_counter}"
    job = Job(job_id, kind, params)
    job.lane = lane_for(kind, params)
    JOBS[job_id] = job

    with _LANES_LOCK:
        q = JOB_LANES.get(job.lane)
        if q is None:
            q = JOB_LANES[job.lane] = queue.Queue()
            threading.Thread(target=worker, args=(q,), daemon=True,
                             name=f"job-{job.lane}").start()
    q.put(job)
    return job


def stream(job: Job, cmd: list, env: dict, cwd: Path) -> int:
    job.append(f"$ {' '.join(str(c) for c in cmd)}")
    # explicit encoding: text=True alone uses the locale codec (cp1252 on Windows)
    proc = subprocess.Popen(cmd, cwd=str(cwd), env=env,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                            text=True, encoding="utf-8", errors="replace", bufsize=1)
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

    reserve_folder(folder)
    tmp = Path(tempfile.mkdtemp(prefix="gen-", dir=str(TESTS_DIR)))
    try:
        env = child_env()
        env.update(TESTS=str(tests), INSTR_CNT=str(instr), TYPE=ttype, DEST=sh(tmp))
        job.append(
            f"[generate] folder '{folder}': +{tests} test(s), {instr} instr, type={ttype}"
            + (f" (appending to {len(existing)} existing)" if existing else ""))

        # riscv-dv cannot run natively on Windows (see wsl_command); the
        # generated .S files still land in the Windows tree.
        if os.name == "nt" and wsl_available():
            job.append("[generate] using WSL (riscv-dv's solver has no Windows build)")
            cmd = wsl_command(ROOT, GEN, {
                "TESTS": str(tests), "INSTR_CNT": str(instr),
                "TYPE": ttype, "DEST": to_wsl_path(tmp),
            })
        else:
            cmd = [BASH, sh(GEN)]

        rc = stream(job, cmd, env, ROOT)
        if rc != 0:
            raise RuntimeError(f"gen_tests.sh exited {rc}")
        new_files = sorted(tmp.glob("*.S"), key=index_of)
        # exiting 0 without writing anything is still a failure
        if not new_files:
            raise RuntimeError(
                "gen_tests.sh produced no programs (see the log above for why)")
        # re-assert the destination: generation takes minutes and it may have been
        # pruned while empty
        dest.mkdir(parents=True, exist_ok=True)
        for i, f in enumerate(new_files):
            shutil.move(str(f), str(dest / f"{TEST}_{next_idx + i}.S"))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        release_folder(folder)

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

    missing = missing_tools("cosim")
    if missing:
        raise RuntimeError(
            f"cosim needs {', '.join(missing)} — not installed. "
            + "; ".join(f"{t}: {INSTALL_HINTS[t]}" for t in missing if t in INSTALL_HINTS)
            + " (see farm/README.md, then restart the backend)")

    label = BUGS.label()
    bug_state = BUGS.snapshot()
    cpu = CPUS.snapshot()
    in_wsl = runs_in_wsl("cosim")
    as_path = to_wsl_path if in_wsl else sh

    env = child_env()
    env.update(STEPS=str(steps), JOBS="4", RUN_ID=job.id, KEEP_GOING="1")

    sv_dir = CPUS.sv_dir()
    if sv_dir is not None:
        env["CPU_SV"] = as_path(sv_dir)
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

    if in_wsl:
        job.append("[cosim] using WSL (the cosim toolchain is Linux-only)")
        passthrough = ["STEPS", "JOBS", "RUN_ID", "KEEP_GOING", "BUILD_ID",
                       "CPU_SV", "MUTATION_LABEL", "REBUILD"]
        cmd = wsl_command(ROOT, RUN_COSIM,
                          {k: env[k] for k in passthrough if k in env},
                          args=[to_wsl_path(dest)])
    else:
        cmd = [BASH, sh(RUN_COSIM), sh(dest)]

    rc = stream(job, cmd, env, ROOT)
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
    which reads farm.yaml. Records land in the shared store.

    `batch` restricts the run to one saved generated batch."""
    exp_type = job.params.get("type", "")
    batch = job.params.get("batch") or None
    env = child_env()

    missing = missing_tools(exp_type)
    if missing:
        raise RuntimeError(
            f"{exp_type} needs {', '.join(missing)} on PATH — not installed. "
            + "; ".join(f"{t}: {INSTALL_HINTS[t]}" for t in missing if t in INSTALL_HINTS)
            + " (see farm/README.md, then restart the backend)")

    scope = f" batch '{batch}'" if batch else ""
    job.append(f"[{exp_type}] running campaign{scope} from farm.yaml")

    summary_file = Path(tempfile.mkdtemp(prefix="summary-")) / "summary.json"
    cmd = [PY, str(FARM / "run_experiment.py"), exp_type,
           "--json-summary", str(summary_file)]
    if batch:
        cmd += ["--batch", batch]
    try:
        rc = stream(job, cmd, env, ROOT)
        if rc != 0:
            raise RuntimeError(f"{exp_type} campaign exited {rc}")
        # the runner's own count; the store holds every record ever written
        try:
            s = json.loads(summary_file.read_text(encoding="utf-8"))
            passed, total = s.get("passed", 0), s.get("total", 0)
        except (OSError, json.JSONDecodeError):
            recs = [r for r in FARM_STORE.all() if r.get("type") == exp_type]
            passed = sum(1 for r in recs if r.get("status") == "pass")
            total = len(recs)
    finally:
        shutil.rmtree(summary_file.parent, ignore_errors=True)

    job.run = {"type": exp_type, "batch": batch, "passed": passed, "totalTests": total}
    job.append(f"[done] {passed}/{total} passed")


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


def worker(q: "queue.Queue[Job]"):
    """Drain one lane's queue. One thread per lane; see JOB_LANES."""
    while True:
        job = q.get()
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
            q.task_done()


# ----------------------------------------------------------- library + runs ---
def load_campaign(run_id: str) -> dict:
    return json.loads((CAMPAIGN_DIR / f"{run_id}.json").read_text())


# Destination folders of in-flight generations. These are empty until the
# programs are moved in, so the empty-folder sweep must skip them.
_RESERVED_FOLDERS: set[str] = set()
_RESERVED_LOCK = threading.Lock()


def reserve_folder(name: str):
    with _RESERVED_LOCK:
        _RESERVED_FOLDERS.add(name)


def release_folder(name: str):
    with _RESERVED_LOCK:
        _RESERVED_FOLDERS.discard(name)


def prune_empty_folders() -> list[str]:
    """Remove test folders that hold no programs.

    Skips generation temp dirs and folders reserved by a running job.
    """
    removed = []
    if not TESTS_DIR.exists():
        return removed
    with _RESERVED_LOCK:
        reserved = set(_RESERVED_FOLDERS)
    for d in sorted(TESTS_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("gen-") or d.name in reserved:
            continue
        if not any(d.glob("*.S")):
            try:
                shutil.rmtree(d)
                removed.append(d.name)
            except OSError:
                continue
    return removed


def list_folders() -> list[dict]:
    prune_empty_folders()
    out = []
    if TESTS_DIR.exists():
        for d in sorted(TESTS_DIR.iterdir()):
            if not d.is_dir() or d.name.startswith("gen-"):
                continue
            tests = sorted(d.glob("*.S"))
            out.append({"name": d.name, "count": len(tests),
                        "modified": int(d.stat().st_mtime)})
    out.sort(key=lambda f: f["modified"], reverse=True)
    return out


def delete_folder(name: str) -> dict:
    """Remove a whole test folder."""
    d = TESTS_DIR / safe_folder(name)
    if not d.is_dir():
        return {"error": f"no folder '{name}'"}
    shutil.rmtree(d)
    return {"ok": True, "removed": d.name}


def delete_test(folder: str, test: str) -> dict:
    """Remove one program from a folder; removes the folder if it empties."""
    d = TESTS_DIR / safe_folder(folder)
    # basename only: never let a name walk out of the folder
    f = d / Path(test).name
    if not f.is_file() or f.suffix != ".S":
        return {"error": f"no test '{test}' in '{folder}'"}
    f.unlink()
    remaining = len(list(d.glob("*.S")))
    folder_removed = False
    if remaining == 0:
        shutil.rmtree(d, ignore_errors=True)
        folder_removed = True
    return {"ok": True, "removed": f.name, "remaining": remaining,
            "folderRemoved": folder_removed}


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
                               # per-experiment, so each tab can say what it needs
                               "experimentTools": experiment_tools(),
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
            qs = parse_qs(urlparse(self.path).query)
            batch = (qs.get("batch") or [None])[0]
            try:
                from farm.config import cases_for, experiment, load_config
                exp = experiment(t, load_config())
                return self._json({"cases": cases_for(exp, batch=batch) if exp else []})
            except Exception as exc:  # noqa: BLE001
                return self._json({"cases": [], "error": str(exc)})
        # Saved generated batches for an experiment — the campaign-side equivalent
        # of cosim's test folders.
        if path.startswith("/api/campaign/") and path.endswith("/batches"):
            t = unquote(path[len("/api/campaign/"):-len("/batches")])
            try:
                from farm.config import batches
                return self._json({"type": t, "batches": batches(t)})
            except Exception as exc:  # noqa: BLE001
                return self._json({"batches": [], "error": str(exc)})
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
            qs = parse_qs(urlparse(self.path).query)
            try:
                since = max(0, int((qs.get("since") or ["0"])[0]))
            except ValueError:
                since = 0
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
        if path.startswith("/api/campaign/") and path.endswith("/batches/delete"):
            t = unquote(path[len("/api/campaign/"):-len("/batches/delete")])
            return self._delete_batch(t, self._body())
        if path == "/api/folders/delete":
            body = self._body()
            res = delete_folder(body.get("folder", ""))
            return self._json(res, 200 if res.get("ok") else 404)
        if path == "/api/tests/delete":
            body = self._body()
            res = delete_test(body.get("folder", ""), body.get("test", ""))
            return self._json(res, 200 if res.get("ok") else 404)
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
        """Synthesize N test cases and save them as a named batch.

        Driven by the experiment's `generate:` block in farm.yaml. Re-using a
        batch name appends to it."""
        from farm.config import batch_cases, batch_dir, experiment, load_config, safe_batch
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
        batch = safe_batch(body.get("name") or "")

        script = ROOT / gen["script"]
        proc = subprocess.run([PY, str(script), str(count)],
                              capture_output=True, text=True,
                              encoding="utf-8", errors="replace", cwd=str(ROOT))
        if proc.returncode != 0:
            return self._json(
                {"error": f"generator failed: {(proc.stderr or proc.stdout)[-500:]}"}, 500)
        try:
            cases = json.loads(proc.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            return self._json(
                {"error": f"generator produced no JSON: {proc.stdout[-300:]}"}, 500)

        # append to an existing batch, keeping case names unique within it
        existing = batch_cases(exp_type, batch)
        seen = {c.get("name") for c in existing}
        merged = list(existing)
        for c in cases:
            name = c.get("name", "case")
            if name in seen:
                n = 2
                while f"{name} #{n}" in seen:
                    n += 1
                name = f"{name} #{n}"
                c = {**c, "name": name}
            seen.add(name)
            merged.append(c)

        d = batch_dir(exp_type)
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{batch}.json").write_text(json.dumps(merged, indent=2), encoding="utf-8")
        return self._json({"type": exp_type, "batch": batch, "count": len(cases),
                           "total": len(merged), "cases": cases})

    def _delete_batch(self, exp_type, body):
        """Remove a saved batch and any input files it owns."""
        from farm.config import GENERATED_DIR, batch_cases, batch_dir, safe_batch
        requested = body.get("name") or ""
        name = safe_batch(requested)
        targets = [batch_dir(exp_type) / f"{name}.json"]
        if requested == "generated":
            targets.append(GENERATED_DIR / f"{exp_type}.json")   # pre-batch flat file

        # Files a generator wrote for this batch (C programs, WFDB records). Only
        # paths under the generated tree are touched, so a case pointing at a
        # curated corpus file or a user upload is left alone.
        inputs = []
        gen_root = GENERATED_DIR.resolve()
        for case in batch_cases(exp_type, name):
            for value in case.values():
                if not isinstance(value, str):
                    continue
                p = Path(value)
                if not p.is_absolute() or not p.is_file():
                    continue
                try:
                    p.resolve().relative_to(gen_root)
                except ValueError:
                    continue
                inputs.append(p)

        removed = [f for f in targets if f.exists()]
        for f in removed:
            f.unlink()
        for f in inputs:
            try:
                f.unlink()
            except OSError:
                pass
        if not removed:
            return self._json({"error": f"no batch '{name}'"}, 404)
        return self._json({"ok": True, "type": exp_type, "removed": name,
                           "inputsRemoved": len(inputs)})

    CONTENT_TYPES = {
        ".html": "text/html", ".js": "text/javascript", ".css": "text/css",
        ".json": "application/json", ".svg": "image/svg+xml",
        ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg",
        ".webp": "image/webp", ".ico": "image/x-icon", ".woff2": "font/woff2",
        ".map": "application/json", ".txt": "text/plain",
    }

    def _serve_static(self, path):
        if not STATIC_DIR.exists():
            return self._json({"error": "no built dashboard; run serve.sh or npm run build",
                               "hint": "the API is up at /api/*"}, 404)
        rel = path.lstrip("/") or "index.html"
        target = (STATIC_DIR / rel).resolve()
        inside = str(target).startswith(str(STATIC_DIR))

        if not inside or not target.is_file():
            # A request for a file (it has an extension) that isn't there is a 404.
            # Only extensionless paths fall back to index.html for client routing;
            # answering a missing asset with HTML and a 200 hides the mistake.
            if Path(rel).suffix:
                return self._json({"error": f"not found: /{rel}"}, 404)
            target = STATIC_DIR / "index.html"
            if not target.is_file():
                return self._json({"error": "no built dashboard"}, 404)

        data = target.read_bytes()
        ctype = self.CONTENT_TYPES.get(target.suffix, "application/octet-stream")
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
    # Lane workers start on demand in new_job().
    print(f"[webapp] backend on http://{HOST}:{PORT}  (api at /api/*)")
    print("[webapp] tools: " + ", ".join(
        f"{t}={'ok' if have(t) else 'MISSING'}"
        for t in ["sbt", "verilator", "spike", "riscv64-elf-gcc"]))
    ThreadingHTTPServer((HOST, PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
