"""Measure the quick start: run the README quick-start commands one by one and record wall time
and peak memory per step and the cost per state of the search.

    uv run python tools/measure_quick_start.py [--steps NAME ...] [--work DIR] [--output FILE]
                                               [--baseline FILE] [--note TEXT] [--beside NAME=SECONDS ...]
                                               [--windows-package ARCHIVE]

Each step runs from the root of the repository, exactly as the README lists it, with the
leading ``runs/`` of every path argument replaced by the work folder. ``--steps`` runs the named
steps and the steps they need before them, and reports only the named ones. The table shows the
recorded baseline (``measurements/baseline.json`` by default) beside the measurement; the factor
is the baseline seconds divided by the measured seconds, so a factor above 1 is a gain.

``--beside NAME=SECONDS`` (repeatable) records a duration taken outside the tool, such as the clone
of both repositories and ``uv sync``: it is stored in ``beside``, printed below the table, and not
counted in ``total``.

Peak memory (``peak_mib``) is the ``ru_maxrss`` that ``os.wait4`` returns for the step: the largest
resident size of a single process among the step and the descendants it waited for, so the ``uv run``
wrapper reports the Python process it starts. It is not the sum of the processes alive at once, so a
step whose model points run in worker processes may hold more than it shows; the record says so in
``peak_mib_covers``. Without ``os.wait4`` (Windows) only the times are measured. The record names the
steps it reports, in the order of the quick start, in ``measured_steps``.

``--windows-package ARCHIVE`` measures the Windows package natively on the Windows host of this WSL
session instead of the ``uv run`` steps here. ``ARCHIVE`` is the ``.zip`` that ``tools/build_package.py
build --target x86_64-pc-windows-msvc`` wrote. The tool copies it to a new host folder (``--work``, a
local folder under ``C:\\`` that does not exist yet, default
``C:\\tmp\\deltarecon-measure\\<UTC timestamp>``), and runs the host chain script of
``tools/build_package.py`` through ``powershell.exe``: it unpacks the zip into ``<work>\\package``,
sets ``PATH`` to an empty folder, and runs the chosen steps through ``deltarecon.cmd`` with
``<work>\\runs`` in place of ``runs/``. The host output streams through to the terminal. The
seconds of each step are those of the host's stopwatch (0.1 s resolution), so the start of
PowerShell and the WSL interop are not counted; the seconds of the unpacking are recorded in
``beside`` as ``unpack`` and not counted in ``total``. When the search ran, its folder must match
the pin ``measurements/quick-start-search.SHA256SUMS``, compared from WSL; every pinned file is
printed as ``OK`` or ``FAILED``. ``commit`` and ``dirty`` are those of this checkout, ``platform``
and ``cpu_count`` those the packaged Python reports on the host; memory is not measured there, so
every ``peak_mib`` is null. The record holds a ``windows`` block with the host folder, the name of
the zip, and its SHA-256; a zip does not carry its commit, so the note should name the commit it
was built from. The host folder is left on the host. This mode loads ``tools/build_package.py``,
which needs ``packaging`` of the development environment.

Exit status: 0 when every step exits with its expected status (and, in the Windows mode, the search
matches the pin when it ran), 1 when a step does not, a host step fails, the host output names no
seconds for a step that ran, the platform probe of the packaged Python fails or its output does not
end in a number, or the search differs from the pin (nothing is written then), 2 when the tool
cannot start (an unknown step, a malformed ``--beside``, an existing work folder or output file; in
the Windows mode also an archive that is missing or whose name names no Windows package, no
``powershell.exe``, or a ``--work`` that is not a new local folder under ``C:\\``). Standard library
only, except the Windows mode.
"""
from __future__ import annotations

import argparse
import datetime
import importlib.util
import json
import math
import os
import platform
import re
import shlex
import shutil
import subprocess
import sys
import time
from pathlib import Path, PureWindowsPath

ROOT = Path(__file__).resolve().parent.parent
RUNS = "runs/"
# What the peak memory of a step covers, in the record and below the table.
PEAK_COVERS = ("the largest single process of the step (ru_maxrss of os.wait4), "
               "not the sum of processes alive at once")
PEAK_LINE = "peak MiB: the largest single process of a step, not the sum of its worker processes"
DEFAULT_BASELINE = ROOT / "measurements" / "baseline.json"
BUILD_PACKAGE_TOOL = ROOT / "tools" / "build_package.py"
WINDOWS_PARENT = "C:\\tmp\\deltarecon-measure"
WINDOWS_PEAK_COVERS = "nothing: memory is not measured on the Windows host"
# The lines of the host chain script of tools/build_package.py that carry the host's seconds.
STEP_LINE = re.compile(r"build_package: chain: (\S+) exit (-?\d+) \(expected (-?\d+)\) in ([0-9]+(?:\.[0-9]+)?) s")
UNPACK_LINE = re.compile(r"build_package: host: unpacked in ([0-9]+(?:\.[0-9]+)?) s")
# What the packaged Python prints on the host: the platform, then the processor count. No double
# quote, which PowerShell 5.1 drops from a native argument.
PLATFORM_PROBE = "import os,platform;print(platform.platform());print(os.cpu_count())"


def _step(command: str, needs: tuple[str, ...] = (), expect: int = 0) -> dict:
    return {"argv": shlex.split(command), "needs": needs, "expect": expect}


# The quick-start commands of the README, verbatim and in order; tests/test_measure.py keeps them in sync.
STEPS: dict[str, dict] = {
    "request": _step("uv run deltarecon request --revision fa368575a66d97c94e96dffc62b273ec95511b12 --label N "
                     "--run-id run-n-full --output runs/n-full/request.json"),
    "run": _step("uv run deltarecon run runs/n-full/request.json", ("request",)),
    "replay": _step("uv run deltarecon replay runs/n-full/run-record.json", ("run",)),
    "regression": _step("uv run deltarecon regression runs/n-full/run-record.json "
                        "--revision 887b7181d22550eda2fb52fa1a6bd77376d4eb2e --output runs/regression-n",
                        ("run",), expect=1),
    "derive": _step("uv run deltarecon derive runs/n-full/run-record.json runs/regression-n/run/run-record.json "
                    "--output runs/changes.json", ("run", "regression")),
    "search": _step("uv run deltarecon search runs/n-full/run-record.json runs/regression-n/run/run-record.json "
                    "--quantity Bruttobeitrag --periods 0-59 --tolerance profiles/tolerance-bruttobeitrag.json "
                    "--target-only --output runs/search", ("run", "regression")),
}

# Where a step's result names its number of states: the file below the work folder and the reader.
STATES = {
    "search": ("search/search.result.json", lambda result: result["runs"]["search"]),
}


def rewrite(argv: list[str], work: Path) -> list[str]:
    """``argv`` with the leading ``runs/`` of every argument replaced by the work folder."""
    return [str(work / argument[len(RUNS):]) if argument.startswith(RUNS) else argument for argument in argv]


def expand(names: list[str], steps: dict[str, dict] = STEPS) -> list[str]:
    """The named steps and every step they need, in the order of ``steps``."""
    wanted: set[str] = set()

    def add(name: str) -> None:
        if name not in wanted:
            wanted.add(name)
            for need in steps[name]["needs"]:
                add(need)

    for name in names:
        add(name)
    return [name for name in steps if name in wanted]


def peak_mib(rusage) -> float:
    """``ru_maxrss`` in MiB: KiB on Linux, bytes on macOS."""
    divisor = 1024 * 1024 if sys.platform == "darwin" else 1024
    return rusage.ru_maxrss / divisor


def execute(argv: list[str], log: Path) -> tuple[int, float, float | None]:
    """Run one command from the root of the repository: its exit status, seconds and peak MiB."""
    with log.open("wb") as output:
        start = time.perf_counter()
        process = subprocess.Popen(argv, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        if hasattr(os, "wait4"):
            _, status, rusage = os.wait4(process.pid, 0)
            seconds = time.perf_counter() - start
            process.returncode = os.waitstatus_to_exitcode(status)
            return process.returncode, seconds, peak_mib(rusage)
        code = process.wait()
        return code, time.perf_counter() - start, None


def git_text(*arguments: str) -> str | None:
    try:
        done = subprocess.run(["git", "-C", str(ROOT), *arguments], capture_output=True, text=True)
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def engine_version(work: Path) -> str | None:
    """The ``engine_version`` reference of the request the request step wrote."""
    path = work / "n-full" / "request.json"
    if not path.is_file():
        return None
    references = json.loads(path.read_text("utf-8"))["release"]["references"]
    return next((r["value"] for r in references if r["kind"] == "engine_version"), None)


def states_of(name: str, work: Path) -> int | None:
    if name not in STATES:
        return None
    path, read = STATES[name]
    file = work / path
    return read(json.loads(file.read_text("utf-8"))) if file.is_file() else None


def _number(value: float | None, digits: int) -> str:
    return "-" if value is None else f"{value:.{digits}f}"


def report(record: dict, baseline: dict | None) -> str:
    """The fixed-width table of a measurement beside a baseline, the cost per state, and the durations beside."""
    old = {step["name"]: step for step in baseline["steps"]} if baseline else {}
    columns = ("step", "seconds", "peak MiB")
    if baseline:
        columns += ("baseline s", "baseline MiB", "factor")
    lines = [f"{columns[0]:<12}" + "".join(f"{column:>13}" for column in columns[1:])]
    rows = [(step["name"], step) for step in record["steps"]] + [("total", record["total"])]
    for name, step in rows:
        cells = [_number(step["seconds"], 1), _number(step["peak_mib"], 0)]
        if baseline:
            if name != "total":
                before = old.get(name)
            else:  # the totals compare only over the same steps
                same = [s["name"] for s in baseline["steps"]] == [s["name"] for s in record["steps"]]
                before = baseline.get("total") if same else None
            seconds = before["seconds"] if before else None
            factor = seconds / step["seconds"] if seconds and step["seconds"] else None
            cells += [_number(seconds, 1), _number(before["peak_mib"] if before else None, 0),
                      _number(factor, 2)]
        lines.append(f"{name:<12}" + "".join(f"{cell:>13}" for cell in cells))
    lines.append(PEAK_LINE)
    for step in record["steps"]:
        if step.get("states") is not None:
            line = (f"{step['name']}: {step['states']} states, "
                    f"{_number(step['seconds_per_state'], 1)} s per state")
            before = old.get(step["name"])
            if before and before.get("seconds_per_state") is not None:
                line += (f" (baseline {before['states']} states, "
                         f"{_number(before['seconds_per_state'], 1)} s per state)")
            lines.append(line)
    for entry in record.get("beside", []):
        lines.append(f"beside, not in the total: {entry['name']} {_number(entry['seconds'], 1)} s")
    return "\n".join(lines)


def beside(value: str) -> dict:
    """One ``--beside NAME=SECONDS``: a name and a non-negative number of seconds."""
    name, separator, seconds = value.partition("=")
    try:
        number = float(seconds)
    except ValueError:
        number = None
    if not separator or not name or number is None or not math.isfinite(number) or number < 0:
        raise argparse.ArgumentTypeError(f"expected NAME=SECONDS with a non-negative number of seconds: {value!r}")
    return {"name": name, "seconds": number}


_WINDOWS_TOOLS: list = []


def windows_tools():
    """``tools/build_package.py`` and the ``tools/windows_host.py`` it loads, loaded once on first use."""
    if not _WINDOWS_TOOLS:
        spec = importlib.util.spec_from_file_location("build_package", BUILD_PACKAGE_TOOL)
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        _WINDOWS_TOOLS.append(build)
    build = _WINDOWS_TOOLS[0]
    return build, build.HOST


def stream(argv: list[str], **options) -> subprocess.CompletedProcess:
    """A runner for ``windows_host.powershell``: every output line (stdout and stderr merged) is
    echoed to this process as it comes and collected into ``stdout`` of the result."""
    process = subprocess.Popen(argv, stdin=options.get("stdin"), stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, encoding="utf-8", errors="replace")
    lines = []
    for line in process.stdout:
        sys.stdout.write(line)
        sys.stdout.flush()
        lines.append(line.rstrip("\r\n"))
    process.stdout.close()
    return subprocess.CompletedProcess(argv, process.wait(), stdout="\n".join(lines))


def host_seconds(text: str) -> tuple[dict[str, float], float | None]:
    """The seconds of each step and of the unpacking in the output of the host chain script."""
    steps, unpack = {}, None
    for line in text.splitlines():
        line = line.strip()
        if found := STEP_LINE.fullmatch(line):
            steps[found.group(1)] = float(found.group(4))
        elif found := UNPACK_LINE.fullmatch(line):
            unpack = float(found.group(1))
    return steps, unpack


def measure_windows(arguments: argparse.Namespace, names: list[str], steps: dict[str, dict],
                    now: datetime.datetime) -> int | dict:
    """Run ``names`` (expanded) through the Windows package on the host: an exit status, or the
    measured step entries, the durations beside, ``platform``, ``cpu_count``, ``engine_version`` and
    the ``windows`` block."""
    build, host = windows_tools()
    archive = arguments.windows_package
    version, _ = build.project()
    try:
        target_name = build.target_of(archive, version)
    except build.Refused as refusal:
        print(f"measure: {refusal}", file=sys.stderr)
        return 2
    if target_name != build.WINDOWS_TARGET:
        print(f"measure: {archive.name} is no Windows package; expected "
              f"{build.archive_name(version, build.WINDOWS_TARGET)}", file=sys.stderr)
        return 2
    archive = archive.resolve()
    if not archive.is_file():
        print(f"measure: no archive at {archive}", file=sys.stderr)
        return 2
    work = arguments.work or f"{WINDOWS_PARENT}\\{now:%Y%m%dT%H%M%SZ}"
    try:
        host.require_host_folder(work)
    except host.Refused as refusal:
        print(f"measure: the work folder: {refusal}", file=sys.stderr)
        return 2
    executable = host.powershell_path()
    if executable is None:
        print("measure: powershell.exe is not on PATH; --windows-package runs in WSL on a Windows host",
              file=sys.stderr)
        return 2
    if host.host_exists(work):
        print(f"measure: the work folder {work} exists already", file=sys.stderr)
        return 2

    package_sha256 = build.sha256_file(archive)
    folder = Path(host.wsl_path(work))
    folder.mkdir(parents=True)
    (folder / "empty-path").mkdir()
    print(f"measure: copying {archive} to {work}", flush=True)
    shutil.copyfile(archive, folder / archive.name)
    target = build.TARGETS[build.WINDOWS_TARGET]
    name = build.package_name(version, build.WINDOWS_TARGET)
    host_work = PureWindowsPath(work)
    package = host_work / "package" / name
    ran = expand(names, steps)
    commands = build.chain_commands(package, host_work / "runs", {step: steps[step] for step in ran}, rewrite,
                                    target["launcher"][0])
    done = host.powershell(build.windows_chain_script(work, archive.name, name, commands), runner=stream,
                           executable=executable)
    if done.returncode != 0:
        print(f"measure: a host step failed with exit status {done.returncode} (see the host output above); "
              f"nothing written; the work folder {work} is left on the host", file=sys.stderr)
        return 1
    seconds, unpack = host_seconds(done.stdout or "")
    missing = [step for step in ran if step not in seconds]
    if missing:
        print(f"measure: the host output names no seconds for {', '.join(missing)}; nothing written", file=sys.stderr)
        return 1

    python = str(package / PureWindowsPath(target["python"]))
    probed = host.powershell(build.windows_python_script(work, python, ["-I", "-c", PLATFORM_PROBE], "probe the platform"),
                             capture=True, executable=executable)
    lines = [line.strip() for line in (probed.stdout or "").splitlines() if line.strip()]
    if probed.returncode != 0 or len(lines) < 2 or not lines[-1].isdigit():
        print(f"measure: the packaged Python could not report its platform (exit status {probed.returncode}): "
              f"{(probed.stdout or '').strip()} {(probed.stderr or '').strip()}; nothing written", file=sys.stderr)
        return 1
    host_platform, cpu_count = lines[-2], int(lines[-1])

    runs = Path(host.wsl_path(work + "\\runs"))
    if "search" in ran:
        code, compared = host.compare(Path(host.wsl_path(work + "\\runs\\search")))
        for line in compared:
            print(f"measure: pin: {line}")
        good = sum(1 for line in compared if line.endswith(": OK"))
        print(f"measure: {good} pinned files OK; compare exit status {code}")
        if code != 0:
            print("measure: the search differs from the pin; nothing written", file=sys.stderr)
            return 1
    print(f"measure: the work folder {work} is left on the host")

    measured = []
    for step in ran:
        if step in names:
            entry = {"name": step, "seconds": seconds[step], "peak_mib": None}
            if step in STATES:
                states = states_of(step, runs)
                entry["states"] = states
                entry["seconds_per_state"] = seconds[step] / states if states else None
            measured.append(entry)
    return {
        "steps": measured,
        "beside": [] if unpack is None else [{"name": "unpack", "seconds": unpack}],
        "platform": host_platform,
        "cpu_count": cpu_count,
        "engine_version": engine_version(runs),
        "windows": {"work": work, "package": archive.name, "package_sha256": package_sha256},
    }


def parse(argv: list[str] | None, steps: dict[str, dict]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="measure_quick_start",
                                     description="Measure the README quick start step by step.")
    parser.add_argument("--steps", action="append", choices=list(steps), metavar="NAME",
                        help=f"a step to measure, repeatable; one of {', '.join(steps)}")
    parser.add_argument("--work", help="the work folder in place of runs/; must not exist (default "
                                       "runs/measure-<UTC timestamp>); with --windows-package a new local host folder "
                                       f"under C:\\ (default {WINDOWS_PARENT}\\<UTC timestamp>)")
    parser.add_argument("--output", type=Path, help="write the measurement as JSON to this file")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE,
                        help="the recorded baseline (default measurements/baseline.json)")
    parser.add_argument("--note", default="", help="a note stored in the record")
    parser.add_argument("--beside", action="append", type=beside, default=[], metavar="NAME=SECONDS",
                        help="a duration taken outside the tool, repeatable; recorded and printed, not in the total")
    parser.add_argument("--windows-package", type=Path, metavar="ARCHIVE",
                        help="measure this Windows package .zip natively on the Windows host of this WSL session "
                             "through powershell.exe, timed by the host")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, steps: dict[str, dict] = STEPS) -> int:
    arguments = parse(argv, steps)
    now = datetime.datetime.now(datetime.timezone.utc)
    commit, dirty = git_text("rev-parse", "HEAD"), git_text("status", "--porcelain")  # before any step runs
    if arguments.output is not None and arguments.output.exists():
        print(f"measure: the output {arguments.output} exists already", file=sys.stderr)
        return 2
    named = arguments.steps or list(steps)
    baseline = None
    if arguments.windows_package is not None:
        measured_windows = measure_windows(arguments, named, steps, now)
        if isinstance(measured_windows, int):
            return measured_windows
        measured = measured_windows["steps"]
        extra = {"platform": measured_windows["platform"], "cpu_count": measured_windows["cpu_count"],
                 "engine_version": measured_windows["engine_version"], "peak_mib_covers": WINDOWS_PEAK_COVERS,
                 "beside": arguments.beside + measured_windows["beside"], "windows": measured_windows["windows"]}
    else:
        work = (Path(arguments.work) if arguments.work else ROOT / RUNS / f"measure-{now:%Y%m%dT%H%M%SZ}").resolve()
        if work.exists():
            print(f"measure: the work folder {work} exists already", file=sys.stderr)
            return 2
        measured = measure_here(named, steps, work)
        if isinstance(measured, int):
            return measured
        extra = {"platform": platform.platform(), "cpu_count": os.cpu_count(), "engine_version": engine_version(work),
                 "peak_mib_covers": PEAK_COVERS, "beside": arguments.beside}
    if arguments.baseline.is_file():
        baseline = json.loads(arguments.baseline.read_text("utf-8"))
    peaks = [step["peak_mib"] for step in measured if step["peak_mib"] is not None]
    record = {
        "date": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": commit,
        "dirty": None if dirty is None else bool(dirty),
        "platform": extra["platform"],
        "cpu_count": extra["cpu_count"],
        "engine_version": extra["engine_version"],
        "note": arguments.note,
        "beside": extra["beside"],
        "peak_mib_covers": extra["peak_mib_covers"],
        "measured_steps": [step["name"] for step in measured],
        "steps": measured,
        "total": {"seconds": sum(step["seconds"] for step in measured),
                  "peak_mib": max(peaks) if peaks else None},
    }
    if "windows" in extra:
        record["windows"] = extra["windows"]
    print(report(record, baseline))
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(json.dumps(record, indent=2) + "\n", "utf-8")
        print(f"measure: written {arguments.output}")
    return 0


def measure_here(named: list[str], steps: dict[str, dict], work: Path) -> int | list[dict]:
    """Run ``named`` (expanded) here with ``work`` in place of ``runs/``: the reported step entries, or 1."""
    reported = set(named)
    logs = work / "logs"
    logs.mkdir(parents=True)
    measured = []
    for name in expand(named, steps):
        command = rewrite(steps[name]["argv"], work)
        print(f"measure: {name}: {shlex.join(command)}", flush=True)
        status, seconds, peak = execute(command, logs / f"{name}.log")
        if status != steps[name]["expect"]:
            print(f"measure: the step {name} exited with status {status}, expected {steps[name]['expect']}\n"
                  f"command: {shlex.join(command)}\nlog: {logs / f'{name}.log'}", file=sys.stderr)
            return 1
        if name in reported:
            entry = {"name": name, "seconds": seconds, "peak_mib": peak}
            states = states_of(name, work)
            if name in STATES:
                entry["states"] = states
                entry["seconds_per_state"] = seconds / states if states else None
            measured.append(entry)
    return measured


if __name__ == "__main__":
    sys.exit(main())
