"""Run scripts natively on the Windows host of a WSL session through ``powershell.exe``.

Every script runs as ``powershell.exe -NoProfile -NonInteractive -EncodedCommand`` (UTF-16LE base64)
with UTF-8 output, so no quoting passes through two shells; values enter a script only as PowerShell
single-quoted literals (``literal``). A host work folder must be an absolute local path under ``C:\\``
(``require_host_folder``); WSL paths, UNC paths, other drives and relative paths raise ``Refused`` of
``tools/common.py``. ``compare`` checks a search folder against the pin
``measurements/quick-start-search.SHA256SUMS`` with ``sha256sum -c``, run from WSL inside that folder.
``stream`` runs a script with its output echoed as it comes and collected; ``step_line`` reads the
line a host script prints for each step it ran.
"""
from __future__ import annotations

import base64
import re
import shutil
import subprocess
import sys
from pathlib import Path

from tools.common import PIN, Refused

MOUNT = "/mnt/c"
DRIVE = "C:"
# Characters Windows refuses in a path component, and the quote characters PowerShell reads as '.
FORBIDDEN = re.compile(r'[<>:"/|?*\x00-\x1f]')
QUOTES = "'\u2018\u2019\u201a\u201b"
# The prefix of every script: UTF-8 output, and a failing PowerShell command stops the script.
PREFIX = ("$OutputEncoding = [Console]::OutputEncoding = [System.Text.UTF8Encoding]::new($false)\n"
          "$ErrorActionPreference = 'Stop'\n"
          "$ProgressPreference = 'SilentlyContinue'\n")


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


def stream(argv: list[str], **options) -> subprocess.CompletedProcess:
    """A runner for ``powershell``: every output line (stdout and stderr merged) is
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


def step_line(label: str) -> re.Pattern:
    """The line ``build_package: <label>: <step> exit <code> (expected <expect>) in <seconds> s`` a
    host script prints after each step: the groups are the step, the exit status, the expected one and
    the seconds."""
    return re.compile(rf"build_package: {re.escape(label)}: (\S+) exit (-?\d+) \(expected (-?\d+)\) "
                      r"in ([0-9]+(?:\.[0-9]+)?) s")


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
