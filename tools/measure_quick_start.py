"""Measure the quick start: run the README quick-start commands one by one and record wall time
and peak memory per step, the cost per state of the walk and the search, and the test suite.

    uv run python tools/measure_quick_start.py [--steps NAME ...] [--work DIR] [--output FILE]
                                               [--baseline FILE] [--note TEXT]

Each step runs from the root of the repository, exactly as the README lists it, with the
leading ``runs/`` of every path argument replaced by the work folder. ``--steps`` runs the named
steps and the steps they need before them, and reports only the named ones. The table shows the
recorded baseline (``measurements/baseline.json`` by default) beside the measurement; the factor
is the baseline seconds divided by the measured seconds, so a factor above 1 is a gain.

Peak memory is the ``ru_maxrss`` that ``os.wait4`` returns for the step, which includes the
descendants the step waited for, so the ``uv run`` wrapper reports the Python process it starts.
Without ``os.wait4`` (Windows) only the times are measured.

Exit status: 0 when every step exits with its expected status, 1 when a step does not (nothing
is written then), 2 when the tool cannot start (an unknown step, an existing work folder or
output file). Standard library only.
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import platform
import shlex
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RUNS = "runs/"
DEFAULT_BASELINE = ROOT / "measurements" / "baseline.json"


def _step(command: str, needs: tuple[str, ...] = (), expect: int = 0) -> dict:
    return {"argv": shlex.split(command), "needs": needs, "expect": expect}


# The quick-start commands of the README, verbatim and in order; tests/test_measure.py keeps them in sync.
STEPS: dict[str, dict] = {
    "request": _step("uv run deltarecon request --revision b64334e09613c45a7a12468dfddc0d9ec47819bb --label N "
                     "--run-id run-n-full --output runs/n-full/request.json"),
    "run": _step("uv run deltarecon run runs/n-full/request.json", ("request",)),
    "replay": _step("uv run deltarecon replay runs/n-full/run-record.json", ("run",)),
    "regression": _step("uv run deltarecon regression runs/n-full/run-record.json "
                        "--revision ab5dc790f5bed52f94a4c8fb8d6b710bc31f0a33 --output runs/regression-n",
                        ("run",), expect=1),
    "derive": _step("uv run deltarecon derive runs/n-full/run-record.json runs/regression-n/run/run-record.json "
                    "--output runs/changes.json", ("run", "regression")),
    "walk": _step("uv run deltarecon walk runs/n-full/run-record.json runs/regression-n/run/run-record.json "
                  "--tolerance profiles/tolerance-bruttobeitrag.json --output runs/walk", ("run", "regression")),
    "search": _step("uv run deltarecon search runs/n-full/run-record.json runs/regression-n/run/run-record.json "
                    "--quantity Bruttobeitrag --periods 0-59 --tolerance profiles/tolerance-bruttobeitrag.json "
                    "--walk runs/walk --output runs/search", ("run", "regression", "walk")),
    "tests": _step("uv run pytest -q"),
}

# Where a step's result names its number of states: the file below the work folder and the reader.
STATES = {
    "walk": ("walk/walk.result.json", lambda result: len(result["states"])),
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
    """The fixed-width table of a measurement beside a baseline, and the cost per state."""
    old = {step["name"]: step for step in baseline["steps"]} if baseline else {}
    columns = ("step", "seconds", "peak MB")
    if baseline:
        columns += ("baseline s", "baseline MB", "factor")
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
    for step in record["steps"]:
        if step.get("states") is not None:
            line = (f"{step['name']}: {step['states']} states, "
                    f"{_number(step['seconds_per_state'], 1)} s per state")
            before = old.get(step["name"])
            if before and before.get("seconds_per_state") is not None:
                line += (f" (baseline {before['states']} states, "
                         f"{_number(before['seconds_per_state'], 1)} s per state)")
            lines.append(line)
    return "\n".join(lines)


def parse(argv: list[str] | None, steps: dict[str, dict]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="measure_quick_start",
                                     description="Measure the README quick start step by step.")
    parser.add_argument("--steps", action="append", choices=list(steps), metavar="NAME",
                        help=f"a step to measure, repeatable; one of {', '.join(steps)}")
    parser.add_argument("--work", type=Path, help="the work folder in place of runs/; must not exist "
                                                  "(default runs/measure-<UTC timestamp>)")
    parser.add_argument("--output", type=Path, help="write the measurement as JSON to this file")
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE,
                        help="the recorded baseline (default measurements/baseline.json)")
    parser.add_argument("--note", default="", help="a note stored in the record")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, steps: dict[str, dict] = STEPS) -> int:
    arguments = parse(argv, steps)
    now = datetime.datetime.now(datetime.timezone.utc)
    work = (arguments.work or ROOT / RUNS / f"measure-{now:%Y%m%dT%H%M%SZ}").resolve()
    if work.exists():
        print(f"measure: the work folder {work} exists already", file=sys.stderr)
        return 2
    if arguments.output is not None and arguments.output.exists():
        print(f"measure: the output {arguments.output} exists already", file=sys.stderr)
        return 2
    baseline = None
    if arguments.baseline.is_file():
        baseline = json.loads(arguments.baseline.read_text("utf-8"))
    named = arguments.steps or list(steps)
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
    peaks = [step["peak_mib"] for step in measured if step["peak_mib"] is not None]
    dirty = git_text("status", "--porcelain")
    record = {
        "date": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "commit": git_text("rev-parse", "HEAD"),
        "dirty": None if dirty is None else bool(dirty),
        "platform": platform.platform(),
        "cpu_count": os.cpu_count(),
        "engine_version": engine_version(work),
        "note": arguments.note,
        "steps": measured,
        "total": {"seconds": sum(step["seconds"] for step in measured),
                  "peak_mib": max(peaks) if peaks else None},
    }
    print(report(record, baseline))
    if arguments.output is not None:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(json.dumps(record, indent=2) + "\n", "utf-8")
        print(f"measure: written {arguments.output}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
