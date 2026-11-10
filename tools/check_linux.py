"""The check of a Linux archive here: unpacked into a new work folder outside this checkout, nine
of the ten claims of ``tools/build_package.py`` (the quick-start chain and the pin, the installed
distributions against ``uv.lock``, an import from a user-named folder, the guided demo and the pin,
and the five commands of the toy engine walkthrough); the tenth, no build-machine traces, is read
from the archive by ``build_package.check``.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from tools import host
from tools.assembly import unpack
from tools.common import ROOT, Failed, Refused, engine_version
from tools.package_check import (PROBE_IMPORT, PROBE_MODULE, PROBE_SOURCE, chain_commands, check_environment,
                                 compare_demo, compare_lock, copy_toy_engine, demo_folders, installed_packages,
                                 locked_packages, toy_commands, toy_walkthrough)
from tools.quick_start_steps import STEPS, rewrite
from tools.targets import PYTHON_FLAGS


def check_chain(package: Path, work: Path, empty: Path) -> bool:
    runs, logs = work / "runs", work / "logs"
    logs.mkdir()
    environment = check_environment(empty)
    for tool in ("uv", "git"):
        if shutil.which(tool, path=environment["PATH"]) is not None:
            raise Failed(f"{tool} is reachable on the PATH of the chain")
    print(f"build_package: chain: PATH={empty}, no uv, no git, cwd={work}", flush=True)
    for name, command, expect in chain_commands(package, runs, STEPS, rewrite):
        log = logs / f"{name}.log"
        start = time.perf_counter()
        with log.open("wb") as output:
            code = subprocess.run(command, cwd=work, env=environment, stdout=output, stderr=subprocess.STDOUT).returncode
        seconds = time.perf_counter() - start
        print(f"build_package: chain: {name} exit {code} (expected {expect}) in {seconds:.1f} s", flush=True)
        if code != expect:
            print(f"build_package: chain: the step {name} failed; log: {log}", file=sys.stderr)
            return False
    code, lines = host.compare(runs / "search")
    for line in lines:
        print(f"build_package: pin: {line}")
    print(f"build_package: engine_version: {engine_version(runs)}")
    return code == 0


def check_demo(package: Path, work: Path, empty: Path, target: dict) -> bool:
    """The starter with ``--no-pause`` from the work folder, its input empty, with the environment of
    the chain; its output goes to ``<work>/logs/quickstart.log``."""
    logs = work / "logs"
    logs.mkdir(exist_ok=True)
    log = logs / "quickstart.log"
    before = demo_folders(package)
    start = time.perf_counter()
    with log.open("wb") as output:
        code = subprocess.run([str(package / target["starter"][0]), "--no-pause"], cwd=work, env=check_environment(empty),
                              stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT).returncode
    print(f"build_package: demo: {target['starter'][0]} --no-pause in {time.perf_counter() - start:.1f} s; log: {log}",
          flush=True)
    return compare_demo(code, before, demo_folders(package))


def check_lock(package: Path, target: dict, version: str) -> bool:
    return compare_lock(installed_packages(package / target["python"]), locked_packages(target, version))


def probe_environment(empty: Path, engines: Path) -> dict[str, str]:
    """The environment of the import probe: that of the check with ``PYTHONPATH`` set to ``engines`` and,
    as the launcher does, without ``PYTHONHOME``, since the probe starts the packaged Python directly."""
    environment = check_environment(empty, PYTHONPATH=str(engines))
    environment.pop("PYTHONHOME", None)
    return environment


def check_import(package: Path, work: Path, empty: Path, target: dict) -> bool:
    engines = work / "engines"
    engines.mkdir()
    (engines / f"{PROBE_MODULE}.py").write_text(PROBE_SOURCE, "utf-8")
    # With the launcher's flags: they must leave PYTHONPATH in force.
    done = subprocess.run([str(package / target["python"]), *PYTHON_FLAGS, "-c", PROBE_IMPORT], capture_output=True,
                          text=True, cwd=work, env=probe_environment(empty, engines))
    if done.returncode != 0:
        print(f"build_package: import: failed: {done.stderr.strip()}")
        return False
    where = Path(done.stdout.strip()).resolve()
    inside = where.parent == engines.resolve()
    print(f"build_package: import: {PROBE_MODULE} read from {where}")
    return inside


def check_toy_engine(package: Path, work: Path, empty: Path) -> dict[str, bool]:
    """The toy engine walkthrough: the Git-tracked files of ``examples/toy_engine/`` copied to
    ``<work>/toy-engine``, each stage run through the launcher from the work folder with the
    environment of the chain, its runs below ``<work>/toy/<stage>`` and the output of each step in
    ``<work>/logs/toy-<stage>-<step>.log``; the five ``toy engine`` claims."""
    engine, stages, logs = work / "toy-engine", work / "toy", work / "logs"
    copied = copy_toy_engine(engine)
    logs.mkdir(exist_ok=True)
    environment = check_environment(empty)
    print(f"build_package: toy engine: {len(copied)} tracked files copied to {engine}", flush=True)

    def run_steps(stage: str, steps: list[tuple[str, list[str], int]]) -> dict[str, int]:
        codes = {}
        for name, command, expect in steps:
            log = logs / f"toy-{stage}-{name}.log"
            start = time.perf_counter()
            with log.open("wb") as output:
                code = subprocess.run(command, cwd=work, env=environment, stdout=output,
                                      stderr=subprocess.STDOUT).returncode
            print(f"build_package: toy engine: {stage}: {name} exit {code} (expected {expect}) in "
                  f"{time.perf_counter() - start:.1f} s", flush=True)
            codes[name] = code
            if code != expect:
                print(f"build_package: toy engine: {stage}: the step {name} failed; log: {log}", file=sys.stderr)
                break
        return codes

    return toy_walkthrough(stages, lambda stage: toy_commands(package, stages / stage, stage, engine), run_steps)


def check_linux(archive: Path, work: Path | None, target: dict, version: str) -> dict[str, bool]:
    """Unpack ``archive`` into the new work folder ``work`` and check it; each claim and whether it holds."""
    if work is None:
        if Path(tempfile.gettempdir()).resolve().is_relative_to(ROOT):
            raise Refused(f"the temporary folder {tempfile.gettempdir()} lies inside this checkout; name --work")
        work = Path(tempfile.mkdtemp(prefix="deltarecon-package-check-")).resolve()
    else:
        work = work.resolve()
        if work.exists():
            raise Refused(f"the work folder {work} exists already")
        if work.is_relative_to(ROOT):
            raise Refused(f"the work folder {work} lies inside this checkout")
        work.mkdir(parents=True)
    print(f"build_package: unpacking {archive} into {work}", flush=True)
    package = unpack(archive, work / "package")
    empty = work / "empty-path"
    empty.mkdir()
    return {
        "chain and pin": check_chain(package, work, empty),
        "installed packages equal uv.lock": check_lock(package, target, version),
        "import from a user-named folder": check_import(package, work, empty, target),
        "guided demo and pin": check_demo(package, work, empty, target),
        **check_toy_engine(package, work, empty),
    }
