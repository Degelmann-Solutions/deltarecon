"""Build the DeltaRecon package for Linux, a folder that holds everything a run needs, and check it.

    uv run python tools/build_package.py build [--output DIR] [--source URL|PATH]
    uv run python tools/build_package.py check ARCHIVE [--work DIR]

``build`` assembles ``deltarecon-<version>-<target>/`` and its ``.tar.gz`` in the output folder
(default ``dist/``), with this layout:

- ``python/``: the standalone CPython build that uv manages (python-build-standalone), pinned by
  URL and SHA-256 in ``TARGETS``; its version must equal the pin of ``requires-python`` in
  ``pyproject.toml``. The download is cached in ``build/python-downloads/`` and verified before
  use; a file whose SHA-256 differs from the pin is deleted.
- the runtime libraries of ``uv.lock`` (``uv export --locked --no-dev``, installed with
  ``--require-hashes --no-deps --no-build`` for the target platform) and the DeltaRecon wheel of
  ``uv build --wheel`` (with the contract pack) in the ``site-packages`` of that Python; the
  ``pip`` the build brings and the ``bin`` folder of the installed scripts are removed, so the
  installed distributions are exactly the locked ones.
- ``delib-history/``: a full ``git clone`` of ``--source`` (default the GitHub repository; a local
  path is allowed). A shallow clone is refused.
- ``profiles/`` and ``LICENSE`` of this checkout.
- ``deltarecon``: a POSIX launcher that uses only shell builtins, resolves its own folder from
  ``$0``, sets ``DELTARECON_REPOSITORIES`` to that folder, and runs
  ``python/bin/python3 -m degelmann.deltarecon`` with the arguments unchanged. It passes no ``-I``
  or ``-E``, so ``PYTHONPATH`` reaches the packaged Python. A symbolic link to the launcher from
  another folder is not supported.

The folder and the archive are assembled in a temporary folder inside the output folder and moved
to their final names only when both are complete, so a failed build leaves nothing behind; nothing
is written when the folder or the archive exists already.

``check`` unpacks the archive into a new folder outside this checkout (``--work``, default a new
folder in the system's temporary folder) and proves three claims, printing each result:

1. The README quick start (``STEPS`` of ``tools/measure_quick_start.py``) runs through the
   launcher from the work folder, which holds no ``repositories/``, with ``PATH`` an empty folder
   (no ``uv``, no ``git``) and without ``PYTHONPATH``, ``PYTHONHOME``, ``VIRTUAL_ENV`` and
   ``DELTARECON_REPOSITORIES``; every step exits with its expected status, and the search folder
   matches the pin ``measurements/quick-start-search.SHA256SUMS``.
2. The distributions installed in the packaged Python (name normalised, version) equal the
   runtime lines of ``uv export --locked --no-dev`` whose markers hold for the target, plus
   ``degelmann-deltarecon`` itself.
3. A module written to ``<work>/engines/`` imports in the packaged Python with ``PYTHONPATH`` set
   to that folder and an empty ``PATH``, and is read from that folder.

It also prints the ``engine_version`` the request step recorded.

Exit status: 0 when the build completes or every check holds; 1 when a build step fails (a
failing command, a shallow clone) or a check does not hold; 2 when the tool cannot start (an
existing output or work folder, a work folder inside this checkout, a missing archive, ``uv`` or
``git`` missing from ``PATH``, a target URL that does not name the pinned Python, a failed download,
a download whose SHA-256 differs from the pin, a Python version other than the pin). Standard library and
``packaging`` (in the development environment) only.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

from packaging.requirements import Requirement
from packaging.utils import canonicalize_name
from packaging.version import Version

ROOT = Path(__file__).resolve().parent.parent
MEASURE_TOOL = ROOT / "tools" / "measure_quick_start.py"
WINDOWS_HOST_TOOL = ROOT / "tools" / "windows_host.py"
PYPROJECT = ROOT / "pyproject.toml"
DOWNLOADS = ROOT / "build" / "python-downloads"
DEFAULT_OUTPUT = ROOT / "dist"
DEFAULT_SOURCE = "https://github.com/Degelmann-Solutions/delib-history"
PROJECT = "degelmann-deltarecon"
CLONE_NAME = "delib-history"
PROFILES = "profiles"
LICENSE = "LICENSE"
LAUNCHER = "deltarecon"
REPOSITORIES_VARIABLE = "DELTARECON_REPOSITORIES"
PROBE_MODULE = "deltarecon_probe_engine"
# Variables of the caller's environment that would move the packaged Python or the clone it reads.
CLEARED = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", REPOSITORIES_VARIABLE)

TARGET = "x86_64-unknown-linux-gnu"
# One row per target platform: the python-build-standalone archive (URL and SHA-256 of the
# release's SHA256SUMS), where the interpreter and site-packages lie in the unpacked ``python/``,
# and the marker environment the lock's markers are evaluated in.
TARGETS: dict[str, dict] = {
    "x86_64-unknown-linux-gnu": {
        "url": "https://releases.astral.sh/github/python-build-standalone/releases/download/20261021/"
               "cpython-3.14.9%2B20261021-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
        "sha256": "561e91c1cadf30e84aec94d1917384ae3267e5f3e6e135e51fd1578bb19f4064",
        "python": "python/bin/python3",
        "site_packages": "python/lib/python3.14/site-packages",
        "pip": ("python/bin/pip*",),
        "markers": {
            "implementation_name": "cpython",
            "implementation_version": "3.14.9",
            "os_name": "posix",
            "platform_machine": "x86_64",
            "platform_python_implementation": "CPython",
            "platform_release": "",
            "platform_system": "Linux",
            "platform_version": "",
            "python_full_version": "3.14.9",
            "python_version": "3.14",
            "sys_platform": "linux",
        },
    },
}

LAUNCHER_TEXT = """#!/bin/sh
# DeltaRecon launcher: runs the packaged Python on the DeltaRecon command line, with the clone
# of delib-history in this folder. Shell builtins only, so it runs with an empty PATH.
case $0 in
    */*) here=${0%/*} ;;
    *) here=. ;;
esac
here=$(CDPATH= cd -- "$here" && pwd -P) || exit 2
DELTARECON_REPOSITORIES=$here
export DELTARECON_REPOSITORIES
exec "$here/python/bin/python3" -m degelmann.deltarecon "$@"
"""


class Failed(Exception):
    """A build step or a check that does not hold: exit status 1."""


class Refused(Exception):
    """The tool cannot start: exit status 2."""


def _load_tool(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def project(pyproject: Path = PYPROJECT) -> tuple[str, str]:
    """The version of the project and the Python version ``requires-python`` pins (``==X.Y.Z``)."""
    table = tomllib.loads(pyproject.read_text("utf-8"))["project"]
    pin = table["requires-python"].strip()
    if not pin.startswith("==") or "," in pin or "*" in pin:
        raise Refused(f"requires-python must pin one version (==X.Y.Z), found {pin!r}")
    return table["version"], pin[2:].strip()


def package_name(version: str, target: str = TARGET) -> str:
    return f"deltarecon-{version}-{target}"


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for block in iter(lambda: file.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def _download(url: str, path: Path) -> None:
    # The release host refuses the default user agent of urllib.
    request = urllib.request.Request(url, headers={"User-Agent": "deltarecon-build-package"})
    try:
        with urllib.request.urlopen(request, timeout=60) as response, path.open("wb") as file:
            shutil.copyfileobj(response, file)
    except OSError as error:  # URLError and HTTPError are OSErrors
        path.unlink(missing_ok=True)
        raise Refused(f"the download of {url} failed: {error}") from None


def fetch_python(target: dict, cache: Path = DOWNLOADS, fetcher=_download) -> Path:
    """The archive of the target's Python in ``cache``, downloaded when absent and verified.

    A file whose SHA-256 differs from the pin is deleted and refused, naming both hashes.
    """
    path = cache / urllib.parse.unquote(target["url"].rsplit("/", 1)[1])
    if not path.is_file():
        cache.mkdir(parents=True, exist_ok=True)
        partial = path.with_name(path.name + ".partial")
        fetcher(target["url"], partial)
        partial.replace(path)
    found = sha256_file(path)
    if found != target["sha256"]:
        path.unlink()
        raise Refused(f"the SHA-256 of {path.name} is {found}, the pin is {target['sha256']}; "
                      "the file is deleted")
    return path


def run(argv: list[str], what: str, **options) -> subprocess.CompletedProcess:
    """Run a build command; a failing command fails the build with its output."""
    done = subprocess.run(argv, capture_output=True, text=True, **options)
    if done.returncode != 0:
        raise Failed(f"{what} failed with exit status {done.returncode}: {' '.join(argv)}\n"
                     f"{done.stdout}{done.stderr}".rstrip())
    return done


def remove_pip(folder: Path, target: dict) -> list[str]:
    """Remove the ``pip`` of the Python build and the ``bin`` folder of the installed scripts from
    the package ``folder``; the paths removed, relative to that folder."""
    site = folder / target["site_packages"]
    paths = [site / "bin", site / "pip", *site.glob("pip-*.dist-info")]
    for pattern in target["pip"]:
        paths += folder.glob(pattern)
    removed = []
    for path in sorted(set(paths)):
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        else:
            continue
        removed.append(path.relative_to(folder).as_posix())
    return removed


def write_launcher(folder: Path) -> Path:
    path = folder / LAUNCHER
    path.write_text(LAUNCHER_TEXT, "utf-8", newline="\n")
    path.chmod(0o755)
    return path


def is_shallow(clone: Path) -> bool:
    done = run(["git", "-C", str(clone), "rev-parse", "--is-shallow-repository"], "git rev-parse")
    return done.stdout.strip() == "true"


def clone_history(source: str, destination: Path) -> None:
    """A full clone of ``source`` at ``destination``; a shallow result is refused."""
    run(["git", "clone", "--quiet", source, str(destination)], f"git clone of {source}")
    if is_shallow(destination):
        raise Failed(f"the clone of {source} is shallow; the package needs the full history of {CLONE_NAME}")


def _anonymous(member: tarfile.TarInfo) -> tarfile.TarInfo:
    """A member without the builder's user and group; mode and link target stay."""
    member.uid = member.gid = 0
    member.uname = member.gname = ""
    return member


def make_archive(folder: Path, archive: Path) -> None:
    """``archive`` (``.tar.gz``) with ``folder`` as its one top folder; links stay links, owners are
    recorded as uid and gid 0 without names."""
    partial = archive.with_name(archive.name + ".partial")
    with tarfile.open(partial, "w:gz") as tar:
        tar.add(folder, arcname=folder.name, filter=_anonymous)
    partial.replace(archive)


def unpack(archive: Path, destination: Path) -> Path:
    """Unpack ``archive`` into ``destination`` with the ``data`` filter; its one top folder."""
    with tarfile.open(archive, "r:*") as tar:
        tops = {Path(member.name).parts[0] for member in tar.getmembers()}
        if len(tops) != 1:
            raise Failed(f"the archive {archive} holds {len(tops)} top folders, expected one: {sorted(tops)}")
        tar.extractall(destination, filter="data")
    return destination / tops.pop()


def python_version(python: Path) -> str:
    done = run([str(python), "-I", "-c", "import platform; print(platform.python_version())"],
               "the packaged Python")
    return done.stdout.strip()


def build(output: Path, source: str, target_name: str = TARGET) -> Path:
    """Assemble the package folder and its archive in ``output``; the archive."""
    target = TARGETS[target_name]
    version, python_pin = project()
    if f"cpython-{python_pin}%2B" not in target["url"] or target_name not in target["url"]:
        raise Refused(f"the Python archive of {target_name} does not name Python {python_pin}: {target['url']}")
    name = package_name(version, target_name)
    folder, archive = output / name, output / f"{name}.tar.gz"
    for path in (folder, archive):
        if path.exists() or path.is_symlink():
            raise Refused(f"the output {path} exists already")
    for tool in ("uv", "git"):
        if shutil.which(tool) is None:
            raise Refused(f"{tool} is not on PATH")
    python_archive = fetch_python(target)
    print(f"build_package: Python archive {python_archive.name} verified", flush=True)
    output.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{name}.", dir=output))
    try:
        package = staging / name
        package.mkdir()
        with tarfile.open(python_archive, "r:gz") as tar:
            tar.extractall(package, filter="data")
        python = package / target["python"]
        found = python_version(python)
        if found != python_pin:
            raise Refused(f"the Python build is {found}, requires-python pins {python_pin}")
        print(f"build_package: Python {found}", flush=True)
        site = package / target["site_packages"]
        requirements = staging / "requirements.txt"
        exported = run(["uv", "export", "--locked", "--no-dev", "--no-emit-project", "--format", "requirements-txt",
                        "--quiet"], "uv export", cwd=ROOT)
        requirements.write_text(exported.stdout, "utf-8")
        platform_options = ["--python-platform", target_name, "--python-version", python_pin]
        run(["uv", "pip", "install", "--quiet", "--target", str(site), *platform_options, "--require-hashes",
             "--no-deps", "--no-build", "-r", str(requirements)], "uv pip install of the locked libraries", cwd=ROOT)
        wheels = staging / "wheel"
        run(["uv", "build", "--wheel", "--quiet", "--out-dir", str(wheels)], "uv build --wheel", cwd=ROOT)
        wheel = [path for path in wheels.glob("*.whl")]
        if len(wheel) != 1:
            raise Failed(f"uv build --wheel left {len(wheel)} wheels, expected one")
        run(["uv", "pip", "install", "--quiet", "--target", str(site), *platform_options, "--no-deps",
             str(wheel[0])], "uv pip install of the DeltaRecon wheel", cwd=ROOT)
        removed = remove_pip(package, target)
        print(f"build_package: libraries installed; removed {', '.join(removed) or 'nothing'}", flush=True)
        clone_history(source, package / CLONE_NAME)
        print(f"build_package: cloned {source}", flush=True)
        shutil.copytree(ROOT / PROFILES, package / PROFILES)
        shutil.copy2(ROOT / LICENSE, package / LICENSE)
        write_launcher(package)
        make_archive(package, staging / archive.name)
        package.replace(folder)
        (staging / archive.name).replace(archive)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return archive


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


def installed_packages(python: Path) -> list[tuple[str, str]]:
    """The distributions the packaged Python finds, name normalised and version, sorted."""
    script = ("import importlib.metadata, json; print(json.dumps([[d.metadata['Name'], d.version] "
              "for d in importlib.metadata.distributions()]))")
    done = subprocess.run([str(python), "-I", "-c", script], capture_output=True, text=True, env=clean_environment())
    if done.returncode != 0:
        raise Failed(f"the packaged Python could not list its distributions: {done.stderr.strip()}")
    return sorted((canonicalize_name(name), str(Version(version))) for name, version in json.loads(done.stdout))


def clean_environment(path: Path | None = None, **extra: str) -> dict[str, str]:
    """This process's environment without ``CLEARED``, ``PATH`` set to ``path``, and ``extra``."""
    environment = {name: value for name, value in os.environ.items() if name not in CLEARED}
    if path is not None:
        environment["PATH"] = str(path)
    environment.update(extra)
    return environment


def chain_commands(package: Path, runs: Path, steps: dict[str, dict], rewrite) -> list[tuple[str, list[str], int]]:
    """The quick-start steps through the launcher: name, command, expected exit status.

    ``uv run deltarecon`` becomes the launcher, ``runs/`` the folder ``runs``, ``profiles/`` the
    profiles of the package."""
    commands = []
    for name, step in steps.items():
        assert step["argv"][:3] == ["uv", "run", "deltarecon"], step["argv"]
        arguments = [str(package / argument) if argument.startswith(PROFILES + "/") else argument
                     for argument in rewrite(step["argv"][3:], runs)]
        commands.append((name, [str(package / LAUNCHER), *arguments], step["expect"]))
    return commands


def check_chain(package: Path, work: Path, empty: Path, measure, compare) -> bool:
    runs, logs = work / "runs", work / "logs"
    logs.mkdir()
    environment = clean_environment(empty)
    for tool in ("uv", "git"):
        if shutil.which(tool, path=environment["PATH"]) is not None:
            raise Failed(f"{tool} is reachable on the PATH of the chain")
    print(f"build_package: chain: PATH={empty}, no uv, no git, cwd={work}", flush=True)
    for name, command, expect in chain_commands(package, runs, measure.STEPS, measure.rewrite):
        log = logs / f"{name}.log"
        start = time.perf_counter()
        with log.open("wb") as output:
            code = subprocess.run(command, cwd=work, env=environment, stdout=output, stderr=subprocess.STDOUT).returncode
        seconds = time.perf_counter() - start
        print(f"build_package: chain: {name} exit {code} (expected {expect}) in {seconds:.1f} s", flush=True)
        if code != expect:
            print(f"build_package: chain: the step {name} failed; log: {log}", file=sys.stderr)
            return False
    code, lines = compare(runs / "search")
    for line in lines:
        print(f"build_package: pin: {line}")
    print(f"build_package: engine_version: {measure.engine_version(runs)}")
    return code == 0


def check_lock(package: Path, target: dict, version: str) -> bool:
    exported = run(["uv", "export", "--locked", "--no-dev", "--no-hashes", "--format", "requirements-txt", "--quiet"],
                   "uv export", cwd=ROOT).stdout
    expected = expected_packages(exported, target["markers"], version)
    installed = installed_packages(package / target["python"])
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


def check_import(package: Path, work: Path, empty: Path, target: dict) -> bool:
    engines = work / "engines"
    engines.mkdir()
    (engines / f"{PROBE_MODULE}.py").write_text('"""A module that stands for an engine the user names."""\n', "utf-8")
    script = f"import {PROBE_MODULE}; print({PROBE_MODULE}.__file__)"
    done = subprocess.run([str(package / target["python"]), "-c", script], capture_output=True, text=True, cwd=work,
                          env=clean_environment(empty, PYTHONPATH=str(engines)))
    if done.returncode != 0:
        print(f"build_package: import: failed: {done.stderr.strip()}")
        return False
    where = Path(done.stdout.strip()).resolve()
    inside = where.parent == engines.resolve()
    print(f"build_package: import: {PROBE_MODULE} read from {where}")
    return inside


def check(archive: Path, work: Path | None, target_name: str = TARGET) -> bool:
    target = TARGETS[target_name]
    version, _ = project()
    if not archive.is_file():
        raise Refused(f"no archive at {archive}")
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
    measure = _load_tool("measure_quick_start", MEASURE_TOOL)
    host = _load_tool("windows_host", WINDOWS_HOST_TOOL)
    results = {
        "chain and pin": check_chain(package, work, empty, measure, host.compare),
        "installed packages equal uv.lock": check_lock(package, target, version),
        "import from a user-named folder": check_import(package, work, empty, target),
    }
    for claim, holds in results.items():
        print(f"build_package: {claim}: {'OK' if holds else 'FAILED'}")
    return all(results.values())


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="build_package", description="Build and check the DeltaRecon package.")
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build", help="build the package folder and its archive")
    build_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="the output folder (default dist/)")
    build_parser.add_argument("--source", default=DEFAULT_SOURCE,
                              help=f"what delib-history is cloned from, a URL or a local path (default {DEFAULT_SOURCE})")
    check_parser = commands.add_parser("check", help="unpack an archive elsewhere and check it")
    check_parser.add_argument("archive", type=Path, help="the .tar.gz that build wrote")
    check_parser.add_argument("--work", type=Path, help="a new folder outside this checkout (default a new temporary folder)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse(argv)
    try:
        if arguments.command == "build":
            archive = build(arguments.output.resolve(), arguments.source)
            print(f"build_package: written {archive.parent / archive.name.removesuffix('.tar.gz')} and {archive}")
            return 0
        return 0 if check(arguments.archive.resolve(), arguments.work) else 1
    except Refused as refusal:
        print(f"build_package: {refusal}", file=sys.stderr)
        return 2
    except Failed as failure:
        print(f"build_package: {failure}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
