"""Build the DeltaRecon package for Linux and for Windows, a folder that holds everything a run needs, and check it.

    uv run python tools/build_package.py build [--target NAME] [--output DIR] [--source URL|PATH]
    uv run python tools/build_package.py check ARCHIVE [--work DIR]

``build`` assembles ``deltarecon-<version>-<target>/`` and its archive in the output folder
(default ``dist/``). The target (``--target``, default ``x86_64-unknown-linux-gnu``) is a row of
``TARGETS``: ``x86_64-unknown-linux-gnu`` writes a ``.tar.gz``, ``x86_64-pc-windows-msvc`` a ``.zip``
(deflated). Both are built on Linux; nothing runs the packaged interpreter at build time, so the
Windows package is cross-built without Windows. The layout:

- ``python/``: the standalone CPython build that uv manages (python-build-standalone), pinned by
  URL and SHA-256 in ``TARGETS``; its version, the ``PY_VERSION`` line of the archive's
  ``patchlevel.h``, must equal the pin of ``requires-python`` in ``pyproject.toml``. The download
  is cached in ``build/python-downloads/`` and verified before use; a file whose SHA-256 differs
  from the pin is deleted.
- the runtime libraries of ``uv.lock`` (``uv export --locked --no-dev``, installed with
  ``--require-hashes --no-deps --no-build`` for the target platform) and the DeltaRecon wheel of
  ``uv build --wheel`` (with the contract pack) in the ``site-packages`` of that Python; the
  ``pip`` the build brings and the ``bin`` and ``Scripts`` folders of the installed scripts are
  removed, so the installed distributions are exactly the locked ones.
- ``delib-history/``: a full ``git clone`` of ``--source`` (default the GitHub repository; a local
  path is allowed). A shallow clone is refused.
- ``profiles/`` and ``LICENSE`` of this checkout.
- a launcher that sets ``DELTARECON_REPOSITORIES`` to its own folder and runs the packaged Python
  with ``-m degelmann.deltarecon`` and the arguments unchanged. It passes no ``-I`` or ``-E``, so
  ``PYTHONPATH`` reaches the packaged Python. On Linux it is ``deltarecon``, a POSIX script that
  uses only shell builtins and resolves its folder from ``$0`` (a symbolic link to it from another
  folder is not supported); on Windows it is ``deltarecon.cmd`` (CRLF, cmd builtins only), which
  resolves its folder from ``%~dp0``.

The folder and the archive are assembled in a temporary folder inside the output folder and moved
to their final names only when both are complete, so a failed build leaves nothing behind; nothing
is written when the folder or the archive exists already. A symbolic link in the Windows folder
fails the build.

``check`` takes the target from the archive's name, which must be ``deltarecon-<version>-<target>``
with the target's suffix. It unpacks the archive into a new folder and proves three claims,
printing each result:

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

A Linux archive is checked here; ``--work`` (default a new folder in the system's temporary folder)
must lie outside this checkout. A Windows archive is checked natively on the Windows host of this
WSL session through ``powershell.exe`` (the helpers of ``tools/windows_host.py``): ``--work``
(default ``C:\\tmp\\deltarecon-package-check\\<UTC timestamp>``) must be a new local folder under
``C:\\``; WSL and UNC paths and other drives are refused. The archive is copied there and unpacked
with .NET ``ZipFile``, the code behind ``Expand-Archive``; the host prints each step with its exit
status and seconds. The lister and the probe run as script files under ``<work>\\scripts\\``. The
pin and the lock are compared from WSL. The folder is left on the host.

Exit status: 0 when the build completes or every check holds; 1 when a build step fails (a
failing command, a shallow clone, a symbolic link in a Windows folder) or a check does not hold; 2
when the tool cannot start (an existing output or work folder, a work folder inside this checkout
or, for Windows, not a new local folder under ``C:\\``, an archive whose name names no target, a
missing archive, no ``powershell.exe`` for a Windows check, ``uv`` or ``git`` missing from
``PATH``, a target URL that does not name the pinned Python, a failed download, a download whose
SHA-256 differs from the pin, a Python version other than the pin). Standard library and
``packaging`` (in the development environment) only.
"""
from __future__ import annotations

import argparse
import datetime
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import tomllib
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath

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
WINDOWS_LAUNCHER = "deltarecon.cmd"
REPOSITORIES_VARIABLE = "DELTARECON_REPOSITORIES"
PROBE_MODULE = "deltarecon_probe_engine"
# The script that prints the distributions a Python finds, as JSON pairs of name and version.
LIST_DISTRIBUTIONS = ("import importlib.metadata, json; print(json.dumps([[d.metadata['Name'], d.version] "
                      "for d in importlib.metadata.distributions()]))")
# The script that imports the probe module and prints where it was read from.
PROBE_IMPORT = f"import {PROBE_MODULE}; print({PROBE_MODULE}.__file__)"
# Variables of the caller's environment that would move the packaged Python or the clone it reads.
CLEARED = ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", REPOSITORIES_VARIABLE)

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

# The Windows launcher: cmd builtins only, so it runs with an empty PATH. %~dp0 is the launcher's
# folder with a trailing backslash, which the second set removes.
WINDOWS_LAUNCHER_TEXT = "\r\n".join([
    "@echo off",
    "rem DeltaRecon launcher: runs the packaged Python on the DeltaRecon command line, with the clone",
    "rem of delib-history in this folder. cmd builtins only, so it runs with an empty PATH.",
    "setlocal",
    f'set "{REPOSITORIES_VARIABLE}=%~dp0"',
    f'set "{REPOSITORIES_VARIABLE}=%{REPOSITORIES_VARIABLE}:~0,-1%"',
    '"%~dp0python\\python.exe" -m degelmann.deltarecon %*',
    "exit /b %ERRORLEVEL%",
    "",
])

TARGET = "x86_64-unknown-linux-gnu"
WINDOWS_TARGET = "x86_64-pc-windows-msvc"
# One row per target platform: the python-build-standalone archive (URL and SHA-256 of the
# release's SHA256SUMS), where the interpreter, site-packages, pip and the header that names the
# Python version lie in the unpacked ``python/``, the marker environment the lock's markers are
# evaluated in, the launcher (name and text), and the suffix of the package archive.
TARGETS: dict[str, dict] = {
    "x86_64-unknown-linux-gnu": {
        "url": "https://releases.astral.sh/github/python-build-standalone/releases/download/20261021/"
               "cpython-3.14.9%2B20261021-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz",
        "sha256": "561e91c1cadf30e84aec94d1917384ae3267e5f3e6e135e51fd1578bb19f4064",
        "python": "python/bin/python3",
        "site_packages": "python/lib/python3.14/site-packages",
        "pip": ("python/bin/pip*",),
        "patchlevel": "python/include/python3.14/patchlevel.h",
        "launcher": (LAUNCHER, LAUNCHER_TEXT),
        "archive": "tar.gz",
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
    "x86_64-pc-windows-msvc": {
        "url": "https://releases.astral.sh/github/python-build-standalone/releases/download/20261021/"
               "cpython-3.14.9%2B20261021-x86_64-pc-windows-msvc-install_only_stripped.tar.gz",
        "sha256": "57cc230da61d897e8e593511c9dac781491675a036cb727b7de5cb7a62ceebea",
        "python": "python/python.exe",
        "site_packages": "python/Lib/site-packages",
        "pip": ("python/Scripts/pip*",),
        "patchlevel": "python/include/patchlevel.h",
        "launcher": (WINDOWS_LAUNCHER, WINDOWS_LAUNCHER_TEXT),
        "archive": "zip",
        "markers": {
            "implementation_name": "cpython",
            "implementation_version": "3.14.9",
            "os_name": "nt",
            "platform_machine": "AMD64",
            "platform_python_implementation": "CPython",
            "platform_release": "",
            "platform_system": "Windows",
            "platform_version": "",
            "python_full_version": "3.14.9",
            "python_version": "3.14",
            "sys_platform": "win32",
        },
    },
}



class Failed(Exception):
    """A build step or a check that does not hold: exit status 1."""


class Refused(Exception):
    """The tool cannot start: exit status 2."""


def _load_tool(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


MEASURE = _load_tool("measure_quick_start", MEASURE_TOOL)
HOST = _load_tool("windows_host", WINDOWS_HOST_TOOL)


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
    """Remove the ``pip`` of the Python build and the ``bin`` and ``Scripts`` folders of the
    installed scripts from the package ``folder``; the paths removed, relative to that folder."""
    site = folder / target["site_packages"]
    paths = [site / "bin", site / "Scripts", site / "pip", *site.glob("pip-*.dist-info")]
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


def write_launcher(folder: Path, target: dict = TARGETS[TARGET]) -> Path:
    """The target's launcher in ``folder``, its text written byte for byte (LF or CRLF as it stands)."""
    name, text = target["launcher"]
    path = folder / name
    path.write_bytes(text.encode("utf-8"))
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
    """``archive`` with ``folder`` as its one top folder. A ``.zip`` is deflated and refuses a
    symbolic link in ``folder``; in a ``.tar.gz`` links stay links, and owners are recorded as uid
    and gid 0 without names."""
    partial = archive.with_name(archive.name + ".partial")
    try:
        if archive.name.endswith(".zip"):
            _write_zip(folder, partial)
        else:
            with tarfile.open(partial, "w:gz") as tar:
                tar.add(folder, arcname=folder.name, filter=_anonymous)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(archive)


def _write_zip(folder: Path, archive: Path) -> None:
    entries = []
    for parent, folders, files in os.walk(folder):
        for name in folders + files:
            path = Path(parent) / name
            if path.is_symlink():
                raise Failed(f"the folder {folder} holds a symbolic link, which a .zip does not keep: {path}")
            entries.append(path)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as zip_file:
        zip_file.write(folder, folder.name)
        for path in sorted(entries):
            zip_file.write(path, f"{folder.name}/{path.relative_to(folder).as_posix()}")


def unpack(archive: Path, destination: Path) -> Path:
    """Unpack ``archive`` (a ``.tar.gz`` with the ``data`` filter, or a ``.zip``) into ``destination``;
    its one top folder."""
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zip_file:
            tops = {PurePosixPath(name).parts[0] for name in zip_file.namelist()}
            _one_top(archive, tops)
            zip_file.extractall(destination)
        return destination / tops.pop()
    with tarfile.open(archive, "r:*") as tar:
        tops = {Path(member.name).parts[0] for member in tar.getmembers()}
        _one_top(archive, tops)
        tar.extractall(destination, filter="data")
    return destination / tops.pop()


def _one_top(archive: Path, tops: set[str]) -> None:
    if len(tops) != 1:
        raise Failed(f"the archive {archive} holds {len(tops)} top folders, expected one: {sorted(tops)}")


PY_VERSION = re.compile(r'^#define\s+PY_VERSION\s+"([^"]+)"', re.MULTILINE)


def header_version(package: Path, target: dict) -> str:
    """The Python version the ``PY_VERSION`` line of the target's ``patchlevel.h`` names."""
    header = package / target["patchlevel"]
    if not header.is_file():
        raise Refused(f"the Python build has no {target['patchlevel']}")
    found = PY_VERSION.search(header.read_text("utf-8", errors="replace"))
    if found is None:
        raise Refused(f"{target['patchlevel']} has no PY_VERSION line")
    return found.group(1)


def require_python(package: Path, target: dict, python_pin: str) -> str:
    """The version of the Python build in ``package``; another version than the pin is refused."""
    found = header_version(package, target)
    if found != python_pin:
        raise Refused(f"the Python build is {found}, requires-python pins {python_pin}")
    return found


def archive_name(version: str, target_name: str) -> str:
    return f"{package_name(version, target_name)}.{TARGETS[target_name]['archive']}"


def target_of(archive: Path, version: str) -> str:
    """The target whose archive name ``archive`` bears; another name is refused."""
    for name in TARGETS:
        if archive.name == archive_name(version, name):
            return name
    expected = ", ".join(archive_name(version, name) for name in TARGETS)
    raise Refused(f"the archive name {archive.name} names no target; expected one of {expected}")


def build(output: Path, source: str, target_name: str = TARGET) -> Path:
    """Assemble the package folder and its archive in ``output``; the archive."""
    target = TARGETS[target_name]
    version, python_pin = project()
    if f"cpython-{python_pin}%2B" not in target["url"] or target_name not in target["url"]:
        raise Refused(f"the Python archive of {target_name} does not name Python {python_pin}: {target['url']}")
    name = package_name(version, target_name)
    folder, archive = output / name, output / archive_name(version, target_name)
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
        found = require_python(package, target, python_pin)
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
        write_launcher(package, target)
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


def locked_packages(target: dict, version: str) -> list[tuple[str, str]]:
    """The distributions ``uv.lock`` names for ``target``, with the project."""
    exported = run(["uv", "export", "--locked", "--no-dev", "--no-hashes", "--format", "requirements-txt", "--quiet"],
                   "uv export", cwd=ROOT).stdout
    return expected_packages(exported, target["markers"], version)


def check_lock(package: Path, target: dict, version: str) -> bool:
    return compare_lock(installed_packages(package / target["python"]), locked_packages(target, version))


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


def check_import(package: Path, work: Path, empty: Path, target: dict) -> bool:
    engines = work / "engines"
    engines.mkdir()
    (engines / f"{PROBE_MODULE}.py").write_text('"""A module that stands for an engine the user names."""\n', "utf-8")
    done = subprocess.run([str(package / target["python"]), "-c", PROBE_IMPORT], capture_output=True, text=True, cwd=work,
                          env=clean_environment(empty, PYTHONPATH=str(engines)))
    if done.returncode != 0:
        print(f"build_package: import: failed: {done.stderr.strip()}")
        return False
    where = Path(done.stdout.strip()).resolve()
    inside = where.parent == engines.resolve()
    print(f"build_package: import: {PROBE_MODULE} read from {where}")
    return inside


def check(archive: Path, work: str | None) -> bool:
    """Check ``archive`` for the target its name bears: here for Linux, on the Windows host for Windows."""
    version, _ = project()
    target_name = target_of(archive, version)
    archive = archive.resolve()
    if not archive.is_file():
        raise Refused(f"no archive at {archive}")
    if target_name == WINDOWS_TARGET:
        return check_windows(archive, work, version)
    return check_linux(archive, None if work is None else Path(work), TARGETS[target_name], version)


def check_linux(archive: Path, work: Path | None, target: dict, version: str) -> bool:
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
    results = {
        "chain and pin": check_chain(package, work, empty, MEASURE, HOST.compare),
        "installed packages equal uv.lock": check_lock(package, target, version),
        "import from a user-named folder": check_import(package, work, empty, target),
    }
    return report(results)


def report(results: dict[str, bool]) -> bool:
    for claim, holds in results.items():
        print(f"build_package: {claim}: {'OK' if holds else 'FAILED'}")
    return all(results.values())


DEFAULT_WINDOWS_PARENT = "C:\\tmp\\deltarecon-package-check"
LISTER_SCRIPT = "list_distributions.py"
PROBE_SCRIPT = "probe_import.py"


def _say(text: str, stream: str = "Out") -> str:
    return f"[Console]::{stream}.WriteLine({HOST.literal(text)})\n"


def host_environment(work: str) -> str:
    """The host lines that set ``PATH`` to ``<work>\\empty-path`` and remove ``CLEARED``."""
    names = ", ".join(HOST.literal(name) for name in CLEARED)
    return (f"Set-Location -LiteralPath {HOST.literal(work)}\n"
            f"$env:PATH = {HOST.literal(work + '\\empty-path')}\n"
            f"foreach ($name in {names}) {{ Remove-Item -LiteralPath ('Env:' + $name) "
            f"-ErrorAction SilentlyContinue }}\n")


def windows_chain_script(work: str, archive: str, name: str, commands: list[tuple[str, list[str], int]]) -> str:
    """The first host script of a Windows check: unpack ``<work>\\<archive>`` into ``<work>\\package``
    with .NET ``ZipFile``, verify its one top folder ``name``, clear the environment, verify that
    ``uv`` and ``git`` are not found, and run each chain command, stopping at the first exit status
    other than the expected one."""
    work = HOST.require_host_folder(work)
    literal = HOST.literal
    destination = work + "\\package"
    lines = [
        f"Set-Location -LiteralPath {literal(work)}\n",
        "Add-Type -AssemblyName System.IO.Compression.FileSystem\n",
        _say("build_package: host: unpacking " + archive + " into " + destination),
        "$watch = [System.Diagnostics.Stopwatch]::StartNew()\n",
        f"[System.IO.Compression.ZipFile]::ExtractToDirectory({literal(work + '\\' + archive)}, {literal(destination)})\n",
        f"$tops = @(Get-ChildItem -LiteralPath {literal(destination)} -Force | ForEach-Object {{ $_.Name }})\n",
        f"if ($tops.Count -ne 1 -or $tops[0] -ne {literal(name)}) {{ [Console]::Error.WriteLine("
        f"'build_package: the archive holds the top folders ' + ($tops -join ', ') + ', expected one: ' + "
        f"{literal(name)}); exit 1 }}\n",
        "[Console]::Out.WriteLine('build_package: host: unpacked in ' + "
        "$watch.Elapsed.TotalSeconds.ToString('0.0', [Globalization.CultureInfo]::InvariantCulture) + ' s')\n",
        host_environment(work),
        "foreach ($name in 'uv', 'git') {\n"
        "  if (Get-Command $name -CommandType Application -ErrorAction SilentlyContinue) {\n"
        "    [Console]::Error.WriteLine('build_package: ' + $name + ' is reachable on the PATH of the chain'); exit 1\n"
        "  }\n"
        "}\n",
        _say(f"build_package: chain: PATH={work}\\empty-path, no uv, no git, cwd={work}"),
    ]
    for step, command, expect in commands:
        call = "& " + " ".join(literal(argument) for argument in command)
        lines += [
            _say(f"build_package: chain: step {step}"),
            "$watch = [System.Diagnostics.Stopwatch]::StartNew()\n",
            f"{call}\n",
            "$code = $LASTEXITCODE\n",
            f"[Console]::Out.WriteLine({literal('build_package: chain: ' + step + ' exit ')} + $code + "
            f"{literal(f' (expected {expect}) in ')} + "
            "$watch.Elapsed.TotalSeconds.ToString('0.0', [Globalization.CultureInfo]::InvariantCulture) + ' s')\n",
            f"if ($code -ne {expect}) {{ [Console]::Error.WriteLine("
            f"{literal('build_package: step ' + step + ' exit ')} + $code + {literal(f', expected {expect}')}); "
            f"exit 1 }}\n",
        ]
    return "".join(lines)


def windows_python_script(work: str, python: str, arguments: list[str], name: str, pythonpath: str | None = None) -> str:
    """A captured host script: the cleared environment (and ``PYTHONPATH`` when given), then the
    packaged Python with ``arguments`` as the host step ``name``."""
    work = HOST.require_host_folder(work)
    script = host_environment(work)
    if pythonpath is not None:
        script += f"$env:PYTHONPATH = {HOST.literal(pythonpath)}\n"
    return script + HOST._step(name, "& " + " ".join(HOST.literal(a) for a in [python, *arguments]))


def _last_line(text: str | None) -> str:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    return lines[-1] if lines else ""


def check_windows(archive: Path, work: str | None, version: str, now: datetime.datetime | None = None) -> bool:
    """Check a Windows archive natively on the Windows host of this WSL session."""
    now = now or datetime.datetime.now(datetime.timezone.utc)
    work = work or f"{DEFAULT_WINDOWS_PARENT}\\{now:%Y%m%dT%H%M%SZ}"
    try:
        HOST.require_host_folder(work)
    except HOST.Refused as refusal:
        raise Refused(f"the work folder: {refusal}") from None
    executable = HOST.powershell_path()
    if executable is None:
        raise Refused("powershell.exe is not on PATH; a Windows archive is checked in WSL on a Windows host")
    if HOST.host_exists(work):
        raise Refused(f"the work folder {work} exists already")
    target = TARGETS[WINDOWS_TARGET]
    name = package_name(version, WINDOWS_TARGET)
    folder = Path(HOST.wsl_path(work))
    folder.mkdir(parents=True)
    for sub in ("empty-path", "engines", "scripts"):
        (folder / sub).mkdir()
    print(f"build_package: copying {archive} to {work}", flush=True)
    shutil.copyfile(archive, folder / archive.name)
    (folder / "engines" / f"{PROBE_MODULE}.py").write_text('"""A module that stands for an engine the user names."""\n',
                                                         "utf-8")
    (folder / "scripts" / LISTER_SCRIPT).write_text(LIST_DISTRIBUTIONS + "\n", "utf-8")
    (folder / "scripts" / PROBE_SCRIPT).write_text(PROBE_IMPORT + "\n", "utf-8")
    host_work = PureWindowsPath(work)
    package = host_work / "package" / name
    python = str(package / PureWindowsPath(target["python"]))
    commands = chain_commands(package, host_work / "runs", MEASURE.STEPS, MEASURE.rewrite, target["launcher"][0])

    done = HOST.powershell(windows_chain_script(work, archive.name, name, commands), executable=executable)
    chain = done.returncode == 0
    if not chain:
        print(f"build_package: chain: a host step failed with exit status {done.returncode} (see above)",
              file=sys.stderr)
    code, lines = HOST.compare(Path(HOST.wsl_path(work + "\\runs\\search")))
    for line in lines:
        print(f"build_package: pin: {line}")
    print(f"build_package: engine_version: {MEASURE.engine_version(Path(HOST.wsl_path(work + '\\runs')))}")

    scripts = str(host_work / "scripts")
    listed = HOST.powershell(windows_python_script(work, python, ["-X", "utf8", "-I", f"{scripts}\\{LISTER_SCRIPT}"],
                                                   "list distributions"), capture=True, executable=executable)
    if listed.returncode == 0:
        lock = compare_lock(distributions(_last_line(listed.stdout)), locked_packages(target, version))
    else:
        print(f"build_package: lock: the packaged Python could not list its distributions: "
              f"{(listed.stdout or '').strip()} {(listed.stderr or '').strip()}")
        lock = False

    engines = str(host_work / "engines")
    probed = HOST.powershell(windows_python_script(work, python, ["-X", "utf8", f"{scripts}\\{PROBE_SCRIPT}"],
                                                   "import the probe", pythonpath=engines),
                             capture=True, executable=executable)
    where = _last_line(probed.stdout)
    if probed.returncode == 0:
        print(f"build_package: import: {PROBE_MODULE} read from {where}")
        inside = str(PureWindowsPath(where).parent).casefold() == engines.casefold()
    else:
        print(f"build_package: import: failed: {(probed.stdout or '').strip()} {(probed.stderr or '').strip()}")
        inside = False
    print(f"build_package: the work folder {work} is left on the host")
    return report({
        "chain and pin": chain and code == 0,
        "installed packages equal uv.lock": lock,
        "import from a user-named folder": inside,
    })


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="build_package", description="Build and check the DeltaRecon package.")
    commands = parser.add_subparsers(dest="command", required=True)
    build_parser = commands.add_parser("build", help="build the package folder and its archive")
    build_parser.add_argument("--target", choices=sorted(TARGETS), default=TARGET,
                              help=f"the target platform (default {TARGET})")
    build_parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT, help="the output folder (default dist/)")
    build_parser.add_argument("--source", default=DEFAULT_SOURCE,
                              help=f"what delib-history is cloned from, a URL or a local path (default {DEFAULT_SOURCE})")
    check_parser = commands.add_parser("check", help="unpack an archive elsewhere and check it")
    check_parser.add_argument("archive", type=Path, help="the .tar.gz or .zip that build wrote; its name names the target")
    check_parser.add_argument("--work", help="Linux: a new folder outside this checkout (default a new temporary "
                                             "folder); Windows: a new host folder under C:\\ (default "
                                             f"{DEFAULT_WINDOWS_PARENT}\\<UTC timestamp>)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse(argv)
    try:
        if arguments.command == "build":
            archive = build(arguments.output.resolve(), arguments.source, arguments.target)
            folder = archive.parent / package_name(project()[0], arguments.target)
            print(f"build_package: written {folder} and {archive}")
            return 0
        return 0 if check(arguments.archive, arguments.work) else 1
    except Refused as refusal:
        print(f"build_package: {refusal}", file=sys.stderr)
        return 2
    except Failed as failure:
        print(f"build_package: {failure}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
