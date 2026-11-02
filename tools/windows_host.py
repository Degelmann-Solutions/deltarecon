"""Run the README quick start natively on the Windows host of a WSL session through ``powershell.exe``.

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

The scripts run through the helpers of ``tools/host.py``, which other host checks reuse.

Exit status: 0 when every pinned file reports ``OK``; 1 when a Git command that writes a bundle here
fails, a host step fails (nothing is compared then) or a pinned file differs or is missing; 2 when the
tool cannot start (a refused or existing work folder, no ``powershell.exe``, a host without ``git`` or
``uv``). Standard library and the DeltaRecon package of this checkout only.
"""
from __future__ import annotations

import argparse
import datetime
import subprocess
import sys
from pathlib import Path

# Run as a file, the folder of this file is first on sys.path; the package ``tools`` needs its parent.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import common, host  # noqa: E402
from tools.common import CLONE_NAME, ROOT, Failed, Refused  # noqa: E402

CLONE = ROOT / "repositories" / CLONE_NAME
PYTHON = "3.14.9"
DEFAULT_PARENT = "C:\\tmp\\deltarecon-windows"


def quick_start_script(work: str, bundle_paths: dict[str, str], commit: str) -> str:
    """The host script of ``quick-start``: clone both bundles, detach at ``commit``, install Python,
    sync the locked libraries, and run the measure tool with its work folder ``<work>\\runs``."""
    work = host.require_host_folder(work)
    literal, step = host.literal, host.step
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
    done = host.powershell(PROBE, runner, capture=True, executable=executable)
    lines = host.lines_of(done.stdout)
    missing = [line.split(" ", 1)[1] for line in lines if line.startswith("missing ")]
    if done.returncode != 0 and not missing:
        missing = [f"a working powershell.exe (probe exit status {done.returncode}: {(done.stderr or '').strip()})"]
    return [line for line in lines if line.startswith("found ")], missing


def _git(*arguments: str, folder: Path = ROOT) -> str:
    """``common.git_text`` in ``folder``; a failing Git command raises ``Failed`` naming it."""
    text = common.git_text(*arguments, folder=folder)
    if text is None:
        raise Failed(f"git {' '.join(arguments)} failed in {folder}")
    return text


def prepare(work: str) -> tuple[str, dict[str, str]]:
    """Create the work folder and write both bundles into it: the commit carried and the bundle paths."""
    folder = Path(host.wsl_path(work))
    folder.mkdir(parents=True)
    commit = _git("rev-parse", "HEAD")
    bundles = {"deltarecon": work + "\\deltarecon.bundle", "delib-history": work + "\\delib-history.bundle"}
    _git("bundle", "create", "--quiet", host.wsl_path(bundles["deltarecon"]), "HEAD")
    _git("bundle", "create", "--quiet", host.wsl_path(bundles["delib-history"]), "--all", folder=CLONE)
    return commit, bundles


def engine_version(work: str) -> str | None:
    """The ``engine_version`` of the host run, read from ``<work>\\runs\\n-full\\request.json``."""
    return common.engine_version(Path(host.wsl_path(work + "\\runs")))


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="windows_host", description="Run checks natively on the Windows host.")
    commands = parser.add_subparsers(dest="command", required=True)
    quick = commands.add_parser("quick-start", help="run the README quick start on the host and compare with the pin")
    quick.add_argument("--work", help=f"the host work folder under {host.DRIVE}\\; must not exist "
                                      f"(default {DEFAULT_PARENT}\\<UTC timestamp>)")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None, runner=subprocess.run) -> int:
    arguments = parse(argv)
    now = datetime.datetime.now(datetime.timezone.utc)
    work = arguments.work or f"{DEFAULT_PARENT}\\{now:%Y%m%dT%H%M%SZ}"
    try:
        executable = host.open_work(work, "powershell.exe is not on PATH; the tool runs in WSL on a Windows host")
    except Refused as refusal:
        print(f"windows_host: {refusal}", file=sys.stderr)
        return 2
    found, missing = probe(runner, executable)
    if missing:
        print(f"windows_host: the host lacks {', '.join(missing)}", file=sys.stderr)
        return 2
    for line in found:
        print(f"windows_host: host {line}")
    if common.git_text("status", "--porcelain"):
        print("windows_host: the tree is dirty; uncommitted changes are not carried to the host")
    try:
        commit, bundles = prepare(work)
    except Failed as failure:
        print(f"windows_host: {failure}", file=sys.stderr)
        return 1
    print(f"windows_host: carrying commit {commit} to {work}", flush=True)
    done = host.powershell(quick_start_script(work, bundles, commit), runner, executable=executable)
    if done.returncode != 0:
        print(f"windows_host: a host step failed with exit status {done.returncode} (see the host output above); "
              f"nothing compared", file=sys.stderr)
        return 1
    print(f"windows_host: host engine_version: {engine_version(work) or 'unknown'}")
    status, lines = host.compare(Path(host.wsl_path(work + "\\runs\\search")))
    for line in lines:
        print(line)
    print(f"windows_host: {host.count_ok(lines)} pinned files OK; compare exit status {status}")
    return 0 if status == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
