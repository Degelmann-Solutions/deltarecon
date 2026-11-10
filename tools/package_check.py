"""The parts the check of a Linux and of a Windows archive share: the probe and lister scripts, the
environment of the check (the caller's, with ``PATH`` an empty folder), the quick-start chain
through the launcher, the comparison of the installed distributions with ``uv.lock``, the
comparison of the guided demo with the pin, the toy engine walkthrough (its Git-tracked files,
the commands of a stage, the compare request, the check of the search result, and the fold of the
exit statuses into the five ``toy engine`` claims), the search of the archive for traces of this
machine, and the report of the ten claims. Needs ``packaging`` of the development environment.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from degelmann.deltarecon.compare import compare_request_document
from degelmann.deltarecon.documents import artifact_reference, document_bytes

from tools import host
from tools.assembly import PROFILES, run, tracked_files
from tools.common import CLONE_NAME, ROOT, Failed
from tools.targets import LAUNCHER

PROJECT = "degelmann-deltarecon"
PROBE_MODULE = "deltarecon_probe_engine"
# The text of the probe module that the import check writes to ``<work>/engines/``.
PROBE_SOURCE = '"""A module that stands for an engine the user names."""\n'
# The script that prints the distributions a Python finds, as JSON pairs of name and version.
LIST_DISTRIBUTIONS = ("import importlib.metadata, json; print(json.dumps([[d.metadata['Name'], d.version] "
                      "for d in importlib.metadata.distributions()]))")
# The script that imports the probe module and prints where it was read from.
PROBE_IMPORT = f"import {PROBE_MODULE}; print({PROBE_MODULE}.__file__)"
TRACES_CLAIM = "no build-machine traces"
# The reflogs of a clone name the builder and the folder it was cloned from; a package holds none.
REFLOGS = f"{CLONE_NAME}/.git/logs"
ALTERNATES = f"{CLONE_NAME}/.git/objects/info/alternates"
# The toy engine of ``examples/toy_engine``, run from the unpacked package without a rebuild.
TOY_FOLDER = "examples/toy_engine"
TOY_ENGINE = "toy_engine:ToyEngine"
# The quantity each stage is searched on, and the revisions that change it between r1 and r5
# (``TARGETS`` of ``tests/test_toy_engine.py``).
TOY_STAGES = {"toy_premium": ("premium", frozenset({"r2", "r4"})),
              "toy_claims": ("expected_claims", frozenset({"r2", "r4", "r5"}))}
TOY_REVISIONS = ("r1", "r5")
# The steps of one stage and the exit status of each (``STATUSES`` of ``tests/test_toy_engine.py``):
# request and run of r1 and r5, a regression and a comparison that find deviations, and a search
# whose two ends are reproduced.
TOY_STEPS = ("request-r1", "run-r1", "request-r5", "run-r5", "regression", "compare", "search")
TOY_STATUSES = (0, 0, 0, 0, 1, 1, 0)
SEARCH_STATUS = TOY_STATUSES[TOY_STEPS.index("search")]
# The steps that run after the compare request is written.
TOY_LATER = ("compare", "search")
TOY_COMMANDS = ("request", "run", "regression", "compare", "search")
TOY_CLAIMS = {command: f"toy engine: {command}" for command in TOY_COMMANDS}


def expected_packages(exported: str, markers: dict[str, str], version: str) -> list[tuple[str, str]]:
    """The distributions a package for ``markers`` must hold: the pinned lines of an ``uv export``
    whose markers hold there (the project line ``-e .`` and options skipped), and the project."""
    found = [(PROJECT, str(Version(version)))]
    for line in exported.splitlines():
        line = line.strip()
        if not line or line.startswith(("#", "-")):
            continue
        requirement = Requirement(line)
        if requirement.marker is not None and not requirement.marker.evaluate(markers):
            continue
        pins = [spec.version for spec in requirement.specifier if spec.operator == "=="]
        if len(pins) != 1:
            raise Failed(f"an exported line pins no single version: {line!r}")
        found.append((canonicalize_name(requirement.name), str(Version(pins[0]))))
    return sorted(found)


def distributions(listed: str) -> list[tuple[str, str]]:
    """The output of ``LIST_DISTRIBUTIONS``, name normalised and version, sorted."""
    return sorted((canonicalize_name(name), str(Version(version))) for name, version in json.loads(listed))


def installed_packages(python: Path) -> list[tuple[str, str]]:
    """The distributions the packaged Python finds, name normalised and version, sorted."""
    done = subprocess.run([str(python), "-I", "-c", LIST_DISTRIBUTIONS], capture_output=True, text=True)
    if done.returncode != 0:
        raise Failed(f"the packaged Python could not list its distributions: {done.stderr.strip()}")
    return distributions(done.stdout)


def check_environment(path: Path, **extra: str) -> dict[str, str]:
    """The environment of the chain, the demo and the import: this process's environment as the
    caller has it (``PYTHONPATH``, ``PYTHONHOME``, ``VIRTUAL_ENV`` and ``DELTARECON_REPOSITORIES``
    included, which the launcher must withstand), ``PATH`` set to ``path``, and ``extra``."""
    environment = dict(os.environ)
    environment["PATH"] = str(path)
    environment.update(extra)
    return environment


def trace_needles(archive: Path) -> list[str]:
    """What a package must not name: the home folder of this machine, the checkout root and the
    folder of ``archive``, each absolute; the root folder itself is left out, and the folder of
    ``archive`` counts only with at least two components below the root (``/tmp`` would match the
    ``'/tmp'`` the standard library holds)."""
    needles = []
    folder = archive.resolve().parent
    for text, least in ((str(Path.home()), 2), (str(ROOT), 2), (str(folder), 3)):
        if len(Path(text).parts) >= least and text not in needles:
            needles.append(text)
    return needles


def _members(archive: Path):
    """Each member of ``archive`` (a zip or a gzipped tar, told apart by content, not by the name a
    resolved link may lack): its name, its bytes (empty for a folder) and the target of a link (empty
    for other members)."""
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as zip_file:
            for info in zip_file.infolist():
                yield info.filename, b"" if info.is_dir() else zip_file.read(info), ""
        return
    with tarfile.open(archive, "r:*") as tar:
        for member in tar:
            file = tar.extractfile(member) if member.isfile() else None
            yield member.name, file.read() if file else b"", member.linkname or ""


def build_machine_traces(archive: Path, needles: list[str]) -> list[str]:
    """The members of ``archive`` that carry a trace of the build machine, one line each: a member
    below ``delib-history/.git/logs/``, the clone's ``objects/info/alternates``, a
    ``*.dist-info/direct_url.json`` (its URL may percent-encode a path), or a member whose name, bytes
    or link target contains one of ``needles``."""
    found = []
    encoded = [(needle, needle.encode("utf-8")) for needle in needles]
    for name, content, link in _members(archive):
        inside = "/".join(PurePosixPath(name).parts[1:])
        if inside == REFLOGS or inside.startswith(REFLOGS + "/"):
            found.append(f"{name}: the reflogs of {CLONE_NAME}")
            continue
        if inside == ALTERNATES:
            found.append(f"{name}: the alternates of {CLONE_NAME}, which name another object store")
            continue
        if name.endswith(".dist-info/direct_url.json"):  # names where a wheel was installed from, maybe %-encoded
            found.append(f"{name}: the install source of a distribution")
            continue
        for needle, raw in encoded:
            if needle in name or needle in link or raw in content:
                found.append(f"{name}: names {needle}")
    return found


def check_traces(archive: Path) -> bool:
    """The claim ``no build-machine traces``, read from the archive itself: each offending member is printed."""
    needles = trace_needles(archive)
    found = build_machine_traces(archive, needles)
    print(f"build_package: traces: searched {archive.name} for {REFLOGS}/ and for {', '.join(needles)}; "
          f"{len(found)} found", flush=True)
    for line in found:
        print(f"build_package: traces: {line}")
    return not found


def chain_commands(package: Path | PureWindowsPath, runs: Path | PureWindowsPath, steps: dict[str, dict], rewrite,
                   launcher: str = LAUNCHER) -> list[tuple[str, list[str], int]]:
    """The quick-start steps through the launcher: name, command, expected exit status.

    ``uv run deltarecon`` becomes the launcher named ``launcher``, ``runs/`` the folder ``runs``,
    ``profiles/`` the profiles of the package. With ``PureWindowsPath`` folders the paths are
    Windows paths."""
    commands = []
    for name, step in steps.items():
        assert step["argv"][:3] == ["uv", "run", "deltarecon"], step["argv"]
        arguments = [str(package / argument) if argument.startswith(PROFILES + "/") else argument
                     for argument in rewrite(step["argv"][3:], runs)]
        commands.append((name, [str(package / launcher), *arguments], step["expect"]))
    return commands


def copy_toy_engine(destination: Path, root: Path = ROOT) -> list[str]:
    """Copy the files of ``examples/toy_engine/`` that Git tracks in ``root`` to the same paths below
    ``destination`` (``toy_engine.py``, ``DOMAIN.md``, ``history/``); ``__pycache__`` and other
    untracked files stay behind. The paths copied, relative to ``destination``."""
    copied = []
    for name in tracked_files(TOY_FOLDER, root=root):
        source = root / name
        if not source.is_file():
            raise Failed(f"the tracked file {name} is missing from {root}")
        inside = PurePosixPath(name).relative_to(TOY_FOLDER)
        target = destination / inside
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        copied.append(inside.as_posix())
    return copied


def toy_command(step: str) -> str:
    """The command of a toy step: ``request-r1`` is of ``request``."""
    return step.split("-")[0]


def toy_commands(package: Path | PureWindowsPath, folder: Path | PureWindowsPath, stage: str,
                 engine_path: Path | PureWindowsPath, launcher: str = LAUNCHER) -> list[tuple[str, list[str], int]]:
    """The steps of ``stage`` through the launcher named ``launcher``: name, command, expected exit
    status. Each writes below ``folder``; the toy engine is loaded from ``engine_path`` and finds its
    history beside its module, so no ``--repositories`` is given. ``compare`` loads no engine and reads
    ``<folder>/compare.request.json``, which ``write_toy_compare_request`` writes before it. With
    ``PureWindowsPath`` folders the paths are Windows paths."""
    engine = ["--engine", TOY_ENGINE, "--engine-path", str(engine_path)]
    arguments = {}
    for revision in TOY_REVISIONS:
        request = str(folder / revision / "request.json")
        arguments[f"request-{revision}"] = ["request", "--revision", revision, "--stage", stage, "--label", revision,
                                            "--run-id", f"run-{revision}", "--output", request, *engine]
        arguments[f"run-{revision}"] = ["run", request, *engine]
    arguments["regression"] = ["regression", str(folder / "r1" / "run-record.json"), "--revision", "r5",
                               "--output", str(folder / "regression"), *engine]
    arguments["compare"] = ["compare", str(folder / "compare.request.json")]
    arguments["search"] = ["search", str(folder / "r1" / "run-record.json"), str(folder / "r5" / "run-record.json"),
                           "--quantity", TOY_STAGES[stage][0], "--output", str(folder / "search"), *engine]
    return [(step, [str(package / launcher), *arguments[step]], expect)
            for step, expect in zip(TOY_STEPS, TOY_STATUSES, strict=True)]


def write_toy_compare_request(folder: Path, stage: str) -> Path:
    """Write ``<folder>/compare.request.json``, the comparison of the runs of r1 and r5 of ``stage``
    (their responses and run records), as ``tests/test_toy_engine.py`` writes it."""
    older, newer = ((artifact_reference(folder, folder / revision / "response.json"),
                     artifact_reference(folder, folder / revision / "run-record.json")) for revision in TOY_REVISIONS)
    path = folder / "compare.request.json"
    path.write_bytes(document_bytes(compare_request_document(stage, f"compare-{stage}", older, newer,
                                                             {"per_quantity": {}})))
    return path


def check_toy_search(folder: Path, stage: str) -> bool:
    """Whether ``<folder>/search/search.result.json`` has both ends ``reproduced`` and finds exactly
    the expected contributing revisions of ``stage``; each difference is printed."""
    path = folder / "search" / "search.result.json"
    try:
        result = json.loads(path.read_text("utf-8"))
        ends = {end: result["ends"][end]["outcome"] for end in ("zero", "n")}
        contributing = {revision for entry in result["contributions"] for revision in entry["revisions"]
                        if any(c["contributes"] for c in entry["contributions"])}
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"build_package: toy engine: {stage}: the search result {path} cannot be read ({error})")
        return False
    expected = set(TOY_STAGES[stage][1])
    holds = True
    if set(ends.values()) != {"reproduced"}:
        print(f"build_package: toy engine: {stage}: search ends {ends['zero']} and {ends['n']}, expected reproduced")
        holds = False
    if contributing != expected:
        print(f"build_package: toy engine: {stage}: contributing revisions {', '.join(sorted(contributing)) or 'none'}, "
              f"expected {', '.join(sorted(expected))}")
        holds = False
    print(f"build_package: toy engine: {stage}: search ends {ends['zero']} and {ends['n']}; contributing "
          f"{', '.join(sorted(contributing)) or 'none'}")
    return holds


def toy_claims(codes: dict[str, dict[str, int]], searched: dict[str, bool]) -> dict[str, bool]:
    """The five ``toy engine`` claims from the exit status of each step that ran, by stage and step
    (a step missing was skipped), and whether the search result of each stage holds: a claim holds
    when every step of its command, both stages, exited as expected (the search with its result)."""
    holds: dict[str, bool] = dict.fromkeys(TOY_COMMANDS, True)
    for stage in TOY_STAGES:
        ran = codes.get(stage, {})
        skipped = [step for step in TOY_STEPS if step not in ran]
        if skipped:
            print(f"build_package: toy engine: {stage}: skipped {', '.join(skipped)}")
        for step, expect in zip(TOY_STEPS, TOY_STATUSES, strict=True):
            if ran.get(step) != expect:
                holds[toy_command(step)] = False
        if not searched.get(stage, False):
            holds["search"] = False
    return {TOY_CLAIMS[command]: holds[command] for command in TOY_COMMANDS}


def toy_walkthrough(stages: Path, commands_of, run_steps) -> dict[str, bool]:
    """Run each toy stage and return the five claims. ``commands_of(stage)`` gives the steps of
    ``toy_commands``; ``run_steps(stage, steps)`` runs them in order, stops at the first exit status
    other than the expected one, and returns the exit status of each step that ran. The compare request
    is written into ``stages/<stage>`` (a folder of this machine) after the earlier steps all hold;
    otherwise the compare and the search are skipped."""
    codes, searched = {}, {}
    for stage in TOY_STAGES:
        folder = stages / stage
        commands = commands_of(stage)
        earlier = [command for command in commands if command[0] not in TOY_LATER]
        ran = dict(run_steps(stage, earlier))
        if all(ran.get(step) == expect for step, _, expect in earlier):
            write_toy_compare_request(folder, stage)
            ran.update(run_steps(stage, [command for command in commands if command[0] in TOY_LATER]))
        codes[stage] = ran
        searched[stage] = ran.get("search") == SEARCH_STATUS and check_toy_search(folder, stage)
    return toy_claims(codes, searched)


def demo_folders(package: Path) -> set[Path]:
    """The folders ``runs/quickstart-*`` in ``package``."""
    return set((package / "runs").glob("quickstart-*"))


def compare_demo(code: int, before: set[Path], after: set[Path]) -> bool:
    """Whether the starter exited 0 and wrote exactly one new demo folder whose ``search/`` matches the pin."""
    new = sorted(after - before)
    print(f"build_package: demo: starter exit {code}; new demo folders: "
          f"{', '.join(path.name for path in new) or 'none'}", flush=True)
    if code != 0 or len(new) != 1:
        return False
    status, lines = host.compare(new[0] / "search")
    for line in lines:
        print(f"build_package: demo pin: {line}")
    return status == 0

def locked_packages(target: dict, version: str) -> list[tuple[str, str]]:
    """The distributions ``uv.lock`` names for ``target``, with the project."""
    exported = run(["uv", "export", "--locked", "--no-dev", "--no-hashes", "--format", "requirements-txt", "--quiet"],
                   "uv export", cwd=ROOT).stdout
    return expected_packages(exported, target["markers"], version)

def compare_lock(installed: list[tuple[str, str]], expected: list[tuple[str, str]]) -> bool:
    """Print how ``installed`` differs from ``expected``; whether they are equal."""
    missing = sorted(set(expected) - set(installed))
    extra = sorted(set(installed) - set(expected))
    duplicates = len(installed) != len(set(installed))
    print(f"build_package: lock: {len(installed)} distributions installed, {len(expected)} expected")
    for name, version_ in missing:
        print(f"build_package: lock: missing {name} {version_}")
    for name, version_ in extra:
        print(f"build_package: lock: not in the lock {name} {version_}")
    if duplicates:
        print("build_package: lock: a distribution is installed twice")
    return not missing and not extra and not duplicates

def report(results: dict[str, bool]) -> bool:
    for claim, holds in results.items():
        print(f"build_package: {claim}: {'OK' if holds else 'FAILED'}")
    return all(results.values())
