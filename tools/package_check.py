"""The parts the check of a Linux and of a Windows archive share: the probe and lister scripts, the
cleared environment, the quick-start chain through the launcher, the comparison of the installed
distributions with ``uv.lock``, the comparison of the guided demo with the pin, and the report of
the four claims. Needs ``packaging`` of the development environment.
"""
from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path, PureWindowsPath

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

from tools import host
from tools.assembly import PROFILES, run
from tools.common import REPOSITORIES_VARIABLE, ROOT, Failed
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
# Variables of the caller's environment that would move the packaged Python or the clone it reads.
CLEARED = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", REPOSITORIES_VARIABLE)


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
    done = subprocess.run([str(python), "-I", "-c", LIST_DISTRIBUTIONS], capture_output=True, text=True,
                          env=clean_environment())
    if done.returncode != 0:
        raise Failed(f"the packaged Python could not list its distributions: {done.stderr.strip()}")
    return distributions(done.stdout)


def clean_environment(path: Path | None = None, **extra: str) -> dict[str, str]:
    """This process's environment without ``CLEARED``, ``PATH`` set to ``path``, and ``extra``."""
    environment = {name: value for name, value in os.environ.items() if name not in CLEARED}
    if path is not None:
        environment["PATH"] = str(path)
    environment.update(extra)
    return environment


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
