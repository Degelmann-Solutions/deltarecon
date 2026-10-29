"""Run checks natively on the Windows host of a WSL session through ``powershell.exe``.

    uv run python tools/windows_host.py quick-start [--work C:\\...]

``quick-start`` carries the present commit (``HEAD``) of this checkout and the clone
``repositories/delib-history`` with its full history to the host as ``git bundle`` files, clones both
there with the host's Git (``core.autocrlf=false``), installs the managed Python 3.14.9 with the host's
uv into the work folder (no executable in the user's ``bin`` folder, no registry entry), runs
``uv sync --locked``, and runs the README quick start there with ``tools/measure_quick_start.py --work <work>\\runs``. It then compares the host search folder with the
pin ``measurements/quick-start-search.SHA256SUMS`` by ``sha256sum -c``, run from WSL inside that
folder, and prints every pinned file as ``OK`` or ``FAILED``. Uncommitted changes are not carried: the
tool prints the commit it carries and says when the tree is dirty.

The work folder (default ``C:\\tmp\\deltarecon-windows\\<UTC timestamp>``) must be an absolute local
path under ``C:\\`` that does not exist yet; WSL paths, UNC paths (``\\\\wsl.localhost\\...``), other
drives and relative paths are refused before anything runs. The folder is left on the host.

Every script runs as ``powershell.exe -NoProfile -NonInteractive -EncodedCommand`` (UTF-16LE base64)
with UTF-8 output, so no quoting passes through two shells; values enter a script only as PowerShell
single-quoted literals (``literal``). ``Refused``, ``windows_path``, ``wsl_path``,
``require_host_folder``, ``powershell_path``, ``host_exists``, ``open_work``, ``literal``, ``encoded``,
``powershell``, ``step``, ``compare``, ``lines_of`` and ``count_ok`` are the reusable parts for other
host checks.

Exit status: 0 when every pinned file reports ``OK``; 1 when a host step fails (nothing is compared
then) or a pinned file differs or is missing; 2 when the tool cannot start (a refused or existing
work folder, no ``powershell.exe``, a host without ``git`` or ``uv``). Standard library only.
"""
from __future__ import annotations

import argparse
import base64
import datetime
import importlib.util
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MEASURE_TOOL = ROOT / "tools" / "measure_quick_start.py"
PIN = ROOT / "measurements" / "quick-start-search.SHA256SUMS"
CLONE = ROOT / "repositories" / "delib-history"
PYTHON = "3.14.9"
MOUNT = "/mnt/c"
DRIVE = "C:"
DEFAULT_PARENT = "C:\\tmp\\deltarecon-windows"
# Characters Windows refuses in a path component, and the quote characters PowerShell reads as '.
FORBIDDEN = re.compile(r'[<>:"/|?*\x00-\x1f]')
QUOTES = "'\u2018\u2019\u201a\u201b"
# The prefix of every script: UTF-8 output, and a failing PowerShell command stops the script.
PREFIX = ("$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n"
          "$ErrorActionPreference = 'Stop'\n"
          "$ProgressPreference = 'SilentlyContinue'\n")


class Refused(ValueError):
    """A path the host helper does not accept."""


def _components(windows: str) -> list[str]:
    if not windows.startswith(DRIVE + "\\"):
        raise Refused(f"not an absolute path under {DRIVE}\\: {windows!r}")
    rest = windows[len(DRIVE) + 1:]
    parts = rest.split("\\") if rest else []
    for part in parts:
        if part in ("", ".", "..") or FORBIDDEN.search(part) or part != part.rstrip(" ."):
            raise Refused(f"not a plain path under {DRIVE}\\ (empty, '.', '..' or a forbidden character "
                          f"in a component): {windows!r}")
    return parts


def windows_path(wsl: str) -> str:
    """The Windows form ``C:\\...`` of a WSL path ``/mnt/c/...``; other forms are refused."""
    if wsl != MOUNT and not wsl.startswith(MOUNT + "/"):
        raise Refused(f"not a path under {MOUNT}: {wsl!r}")
    parts = wsl[len(MOUNT) + 1:].split("/") if wsl != MOUNT else []
    if any(part == "" or "\\" in part for part in parts):
        raise Refused(f"not a plain path under {MOUNT} (an empty component or a backslash): {wsl!r}")
    windows = DRIVE + "\\" + "\\".join(parts)
    _components(windows)
    return windows


def wsl_path(windows: str) -> str:
    """The WSL form ``/mnt/c/...`` of a Windows path ``C:\\...``; other forms are refused."""
    parts = _components(windows)
    return "/".join([MOUNT, *parts])


def require_host_folder(windows: str) -> str:
    """``windows`` when it is an absolute local folder under ``C:\\`` other than the root itself.

    Refused: WSL paths, UNC paths (``\\\\wsl.localhost\\...``, ``\\\\?\\...``), other drives, relative
    paths such as ``C:relative``, and ``.``, ``..`` or forbidden characters in a component.
    """
    if windows.startswith(("\\\\", "//")):
        raise Refused(f"a UNC path is refused, the host folder must be a local path under {DRIVE}\\: {windows!r}")
    if not _components(windows):
        raise Refused(f"the host folder must be below {DRIVE}\\, not the root: {windows!r}")
    return windows


def literal(value: str) -> str:
    """``value`` as a PowerShell single-quoted literal: every quote character doubled, nothing expanded."""
    return "'" + "".join(c * 2 if c in QUOTES else c for c in value) + "'"


def encoded(script: str) -> str:
    """The argument of ``-EncodedCommand``: the prefix and ``script``, UTF-16LE, base64."""
    return base64.b64encode((PREFIX + script).encode("utf-16-le")).decode("ascii")


def powershell_path() -> str | None:
    return shutil.which("powershell.exe")


def powershell(script: str, runner=subprocess.run, capture: bool = False, executable: str = "powershell.exe"):
    """Run ``script`` on the host and return the completed process.

    With ``capture`` the output is returned as text, otherwise it passes through to this process.
    The script must check ``$LASTEXITCODE`` after each native command itself.
    """
    argv = [executable, "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded(script)]
    options = {"stdin": subprocess.DEVNULL}
    if capture:
        options.update(capture_output=True, text=True, encoding="utf-8", errors="replace")
    return runner(argv, **options)


def step(name: str, command: str) -> str:
    """One host step: announce it, run it, stop the script with a step-named message when it fails."""
    return (f"[Console]::Out.WriteLine({literal('windows_host: step ' + name)})\n"
            f"{command}\n"
            f"if ($LASTEXITCODE -ne 0) {{ [Console]::Error.WriteLine("
            f"{literal('windows_host: the host step ' + name + ' failed with exit status ')} + $LASTEXITCODE); "
            f"exit 1 }}\n")


def quick_start_script(work: str, bundle_paths: dict[str, str], commit: str) -> str:
    """The host script of ``quick-start``: clone both bundles, detach at ``commit``, install Python,
    sync the locked libraries, and run the measure tool with its work folder ``<work>\\runs``."""
    work = require_host_folder(work)
    checkout = work + "\\deltarecon"
    clone = checkout + "\\repositories\\delib-history"
    deltarecon, history = bundle_paths["deltarecon"], bundle_paths["delib-history"]
    python, runs = work + "\\python", work + "\\runs"
    lines = [
        f"Set-Location -LiteralPath {literal(work)}\n",  # not the UNC folder of WSL the host starts in
        step("clone deltarecon", f"git -c core.autocrlf=false clone --config core.autocrlf=false --no-checkout "
                                 f"{literal(deltarecon)} {literal(checkout)}"),
        step(f"checkout {commit}", f"git -C {literal(checkout)} -c core.autocrlf=false checkout --detach "
                                   f"{literal(commit)}"),
        f"$head = git -C {literal(checkout)} rev-parse HEAD\n"
        f"if ($head -ne {literal(commit)}) {{ [Console]::Error.WriteLine("
        f"'windows_host: the host step verify commit found ' + $head); exit 1 }}\n",
        step("clone delib-history", f"git -c core.autocrlf=false clone --config core.autocrlf=false "
                                    f"{literal(history)} {literal(clone)}"),
        step("fetch delib-history remote branches",
             f"git -C {literal(clone)} fetch --quiet {literal(history)} "
             f"{literal('+refs/remotes/origin/*:refs/remotes/wsl-origin/*')}"),
        f"Set-Location -LiteralPath {literal(checkout)}\n",
        f"$env:UV_PYTHON_INSTALL_DIR = {literal(python)}\n",
        step(f"install Python {PYTHON}", f"uv python install --no-bin --no-registry {literal(PYTHON)}"),
        step("uv sync --locked", "uv sync --locked"),
        step("run the quick start chain", f"uv run python tools/measure_quick_start.py --work "
                                           f"{literal(runs)}"),
    ]
    return "".join(lines)


PROBE = ("foreach ($name in 'git', 'uv') {\n"
         "  if (Get-Command $name -CommandType Application -ErrorAction SilentlyContinue) {\n"
         "    [Console]::Out.WriteLine('found ' + $name + ': ' + (& $name --version))\n"
         "  } else { [Console]::Out.WriteLine('missing ' + $name) }\n"
         "}\n")


def probe(runner=subprocess.run, executable: str = "powershell.exe") -> tuple[list[str], list[str]]:
    """The host tools ``quick-start`` needs: the lines found and the names missing."""
    done = powershell(PROBE, runner, capture=True, executable=executable)
    lines = lines_of(done.stdout)
    missing = [line.split(" ", 1)[1] for line in lines if line.startswith("missing ")]
    if done.returncode != 0 and not missing:
        missing = [f"a working powershell.exe (probe exit status {done.returncode}: {(done.stderr or '').strip()})"]
    return [line for line in lines if line.startswith("found ")], missing


def lines_of(text: str | None) -> list[str]:
    """The non-empty lines of a host output ``text`` (``None`` counts as empty), stripped."""
    return [line.strip() for line in (text or "").splitlines() if line.strip()]


def compare(search_folder: Path, pin: Path = PIN) -> tuple[int, list[str]]:
    """``sha256sum -c`` of the pin, run inside ``search_folder``: its exit status and output lines."""
    if not search_folder.is_dir():
        return 1, [f"{search_folder}: no search folder"]
    done = subprocess.run(["sha256sum", "-c", str(pin)], cwd=search_folder, capture_output=True, text=True)
    return done.returncode, (done.stdout + done.stderr).splitlines()


def count_ok(lines: list[str]) -> int:
    """The number of output lines of ``compare`` that report a pinned file as ``OK``."""
    return sum(1 for line in lines if line.endswith(": OK"))


def _git(*arguments: str, folder: Path = ROOT) -> str:
    return subprocess.run(["git", "-C", str(folder), *arguments], capture_output=True, text=True,
                          check=True).stdout.strip()


def prepare(work: str) -> tuple[str, dict[str, str]]:
    """Create the work folder and write both bundles into it: the commit carried and the bundle paths."""
    folder = Path(wsl_path(work))
    folder.mkdir(parents=True)
    commit = _git("rev-parse", "HEAD")
    bundles = {"deltarecon": work + "\\deltarecon.bundle", "delib-history": work + "\\delib-history.bundle"}
    _git("bundle", "create", "--quiet", wsl_path(bundles["deltarecon"]), "HEAD")
    _git("bundle", "create", "--quiet", wsl_path(bundles["delib-history"]), "--all", folder=CLONE)
    return commit, bundles


def host_exists(windows: str) -> bool:
    return Path(wsl_path(windows)).exists()


def open_work(work: str, no_powershell: str) -> str:
    """The ``powershell.exe`` to run host scripts with, once the start-up checks of the new host work
    folder ``work`` hold, in this order: ``work`` is a host folder (``require_host_folder``),
    ``powershell.exe`` is on ``PATH``, and ``work`` does not exist yet.

    Each failing check raises ``Refused``: ``the work folder: <reason>``, then ``no_powershell``, the
    caller's own sentence, then ``the work folder <work> exists already``.
    """
    try:
        require_host_folder(work)
    except Refused as refusal:
        raise Refused(f"the work folder: {refusal}") from None
    executable = powershell_path()
    if executable is None:
        raise Refused(no_powershell)
    if host_exists(work):
        raise Refused(f"the work folder {work} exists already")
    return executable


def engine_version(work: str) -> str | None:
    """The ``engine_version`` of the host run, read by the measure tool from ``n-full/request.json``."""
    spec = importlib.util.spec_from_file_location("measure_quick_start", MEASURE_TOOL)
    measure = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(measure)
    return measure.engine_version(Path(wsl_path(work + "\\runs")))


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="windows_host", description="Run checks natively on the Windows host.")
    commands = parser.add_subparsers(dest="command", required=True)
    quick = commands.add_parser("quick-start", help="run the README quick start on the host and compare with the pin")
    quick.add_argument("--work", help=f"the host work folder under {DRIVE}\\; must not exist "
                                      f"(default {DEFAULT_PARENT}\\<UTC timestamp>)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, runner=subprocess.run) -> int:
    arguments = parse(argv)
    now = datetime.datetime.now(datetime.timezone.utc)
    work = arguments.work or f"{DEFAULT_PARENT}\\{now:%Y%m%dT%H%M%SZ}"
    try:
        executable = open_work(work, "powershell.exe is not on PATH; the tool runs in WSL on a Windows host")
    except Refused as refusal:
        print(f"windows_host: {refusal}", file=sys.stderr)
        return 2
    found, missing = probe(runner, executable)
    if missing:
        print(f"windows_host: the host lacks {', '.join(missing)}", file=sys.stderr)
        return 2
    for line in found:
        print(f"windows_host: host {line}")
    if _git("status", "--porcelain"):
        print("windows_host: the tree is dirty; uncommitted changes are not carried to the host")
    commit, bundles = prepare(work)
    print(f"windows_host: carrying commit {commit} to {work}", flush=True)
    done = powershell(quick_start_script(work, bundles, commit), runner, executable=executable)
    if done.returncode != 0:
        print(f"windows_host: a host step failed with exit status {done.returncode} (see the host output above); "
              f"nothing compared", file=sys.stderr)
        return 1
    print(f"windows_host: host engine_version: {engine_version(work) or 'unknown'}")
    status, lines = compare(Path(wsl_path(work + "\\runs\\search")))
    for line in lines:
        print(line)
    print(f"windows_host: {count_ok(lines)} pinned files OK; compare exit status {status}")
    return 0 if status == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
