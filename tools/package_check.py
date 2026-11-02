"""The parts the check of a Linux and of a Windows archive share: the probe and lister scripts, the
environment of the check (the caller's, with ``PATH`` an empty folder), the quick-start chain
through the launcher, the comparison of the installed distributions with ``uv.lock``, the
comparison of the guided demo with the pin, the search of the archive for traces of this machine,
and the report of the five claims. Needs ``packaging`` of the development environment.
"""
from __future__ import annotations

import json
import os
import subprocess
import tarfile
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from tools import host
from tools.assembly import PROFILES, run
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
    folder of ``archive``, each absolute; the root folder itself is left out."""
    needles = []
    for folder in (Path.home(), ROOT, archive.resolve().parent):
        text = str(folder)
        if len(Path(text).parts) > 1 and text not in needles:
            needles.append(text)
    return needles


def _members(archive: Path):
    """Each member of ``archive`` (a ``.zip`` or a ``.tar.gz``): its name, its bytes (empty for a
    folder) and the target of a link (empty for other members)."""
    if archive.name.endswith(".zip"):
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
    below ``delib-history/.git/logs/``, or a member whose name, bytes or link target contains one of
    ``needles``."""
    found = []
    encoded = [(needle, needle.encode("utf-8")) for needle in needles]
    for name, content, link in _members(archive):
        inside = "/".join(PurePosixPath(name).parts[1:])
        if inside == REFLOGS or inside.startswith(REFLOGS + "/"):
            found.append(f"{name}: the reflogs of {CLONE_NAME}")
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
