"""The check of a Windows archive natively on the Windows host of this WSL session, and the host
sequence it shares with the Windows mode of ``tools/measure_quick_start.py``.

``start_host_chain`` opens a new host work folder under ``C:\\`` (``tools/host.py``), creates it with
``empty-path``, copies the archive there, and runs the host chain script: it unpacks the zip with
.NET ``ZipFile`` into ``<work>\\package``, sets ``PATH`` to the empty folder (the rest of the host
user's environment stays), and runs the chosen quick-start steps through ``deltarecon.cmd``,
printing each step with its exit status and the seconds of the host's stopwatch. ``check_windows`` then lists the installed distributions, imports a probe module
from a user-named folder and runs the guided demo, each as a host script; the pin and the lock are
compared from WSL. Needs ``packaging`` of the development environment.
"""
from __future__ import annotations

import datetime
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path, PureWindowsPath

from tools import host
from tools.common import engine_version
from tools.package_check import (LIST_DISTRIBUTIONS, PROBE_IMPORT, PROBE_MODULE, PROBE_SOURCE, chain_commands,
                                 compare_demo, compare_lock, demo_folders, distributions, locked_packages)
from tools.quick_start_steps import STEPS, rewrite
from tools.targets import PYTHON_FLAGS, TARGETS, WINDOWS_STARTER, WINDOWS_TARGET, package_name

DEFAULT_WINDOWS_PARENT = "C:\\tmp\\deltarecon-package-check"
LISTER_SCRIPT = "list_distributions.py"
PROBE_SCRIPT = "probe_import.py"
DEMO_SCRIPT = "demo.cmd"
# The PowerShell expression of the seconds a ``$watch`` stopwatch has run, as ``0.0`` with a decimal
# point; ``STEP_LINE`` and ``UNPACK_LINE`` of ``tools/measure_quick_start.py`` read it.
WATCH_SECONDS = "$watch.Elapsed.TotalSeconds.ToString('0.0', [Globalization.CultureInfo]::InvariantCulture)"


def _say(text: str, stream: str = "Out") -> str:
    return f"[Console]::{stream}.WriteLine({host.literal(text)})\n"


def host_environment(work: str) -> str:
    """The host lines that change to ``work`` and set ``PATH`` to ``<work>\\empty-path``; the rest of
    the host user's environment stays as it is (``PYTHONPATH``, ``PYTHONHOME`` and the like included),
    as for the Linux check."""
    return (f"Set-Location -LiteralPath {host.literal(work)}\n"
            f"$env:PATH = {host.literal(work + '\\empty-path')}\n")


def windows_chain_script(work: str, archive: str, name: str, commands: list[tuple[str, list[str], int]]) -> str:
    """The first host script of a Windows check: unpack ``<work>\\<archive>`` into ``<work>\\package``
    with .NET ``ZipFile``, verify its one top folder ``name``, set ``PATH`` to the empty folder, verify that
    ``uv`` and ``git`` are not found, and run each chain command, stopping at the first exit status
    other than the expected one."""
    work = host.require_host_folder(work)
    literal = host.literal
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
        f"[Console]::Out.WriteLine('build_package: host: unpacked in ' + {WATCH_SECONDS} + ' s')\n",
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
            f"{literal(f' (expected {expect}) in ')} + {WATCH_SECONDS} + ' s')\n",
            f"if ($code -ne {expect}) {{ [Console]::Error.WriteLine("
            f"{literal('build_package: step ' + step + ' exit ')} + $code + {literal(f', expected {expect}')}); "
            f"exit 1 }}\n",
        ]
    return "".join(lines)


def windows_python_script(work: str, python: str, arguments: list[str], name: str, pythonpath: str | None = None) -> str:
    """A captured host script: the environment of the check (and, when given, ``PYTHONPATH``, with
    ``PYTHONHOME`` removed as the launcher does, since the probe starts the packaged Python directly),
    then the packaged Python with ``arguments`` as the host step ``name``."""
    work = host.require_host_folder(work)
    script = host_environment(work)
    if pythonpath is not None:
        script += ("Remove-Item -LiteralPath 'Env:PYTHONHOME' -ErrorAction SilentlyContinue\n"
                   f"$env:PYTHONPATH = {host.literal(pythonpath)}\n")
    return script + host.step(name, "& " + " ".join(host.literal(a) for a in [python, *arguments]))


def windows_demo_script(package: str) -> str:
    """The cmd script ``<work>\\scripts\\demo.cmd``: the starter of the package with ``--no-pause`` and
    its input from ``NUL``, so neither the demo nor ``pause`` waits; it exits with the starter's status."""
    return "\r\n".join([
        "@echo off",
        f'call "{package}\\{WINDOWS_STARTER}" --no-pause < NUL',
        "exit /b %ERRORLEVEL%",
        "",
    ])


def windows_demo_host_script(work: str, demo: str) -> str:
    """The host script that runs ``demo`` (the script of ``windows_demo_script``) with the
    environment and the empty ``PATH`` of the chain, as the host step ``guided demo``."""
    work = host.require_host_folder(work)
    return host_environment(work) + host.step("guided demo", "& " + host.literal(demo))


def _last_line(text: str | None) -> str:
    lines = host.lines_of(text)
    return lines[-1] if lines else ""


@dataclass
class HostChain:
    """What ``start_host_chain`` leaves: the ``powershell.exe`` it used, the work folder as a WSL path
    and as a host path, the package folder and its Python on the host, and the finished chain."""
    executable: str
    folder: Path
    host_work: PureWindowsPath
    package: PureWindowsPath
    python: str
    done: subprocess.CompletedProcess


def start_host_chain(archive: Path, work: str, version: str, steps: dict[str, dict], prefix: str,
                     no_powershell: str, runner=subprocess.run) -> HostChain:
    """Open the new host work folder ``work`` (``host.open_work``, which raises ``Refused`` with
    ``no_powershell`` when there is no ``powershell.exe``), create it with ``empty-path``, copy
    ``archive`` there (announced as ``<prefix>: copying ...``), and run the host chain script of
    ``steps`` through the Windows launcher with ``runner``."""
    executable = host.open_work(work, no_powershell)
    target = TARGETS[WINDOWS_TARGET]
    name = package_name(version, WINDOWS_TARGET)
    folder = Path(host.wsl_path(work))
    folder.mkdir(parents=True)
    (folder / "empty-path").mkdir()
    print(f"{prefix}: copying {archive} to {work}", flush=True)
    shutil.copyfile(archive, folder / archive.name)
    host_work = PureWindowsPath(work)
    package = host_work / "package" / name
    python = str(package / PureWindowsPath(target["python"]))
    commands = chain_commands(package, host_work / "runs", steps, rewrite, target["launcher"][0])
    done = host.powershell(windows_chain_script(work, archive.name, name, commands), runner=runner,
                           executable=executable)
    return HostChain(executable, folder, host_work, package, python, done)


def check_windows(archive: Path, work: str | None, version: str) -> dict[str, bool]:
    """Check a Windows archive natively on the Windows host of this WSL session; each claim and
    whether it holds (the traces claim is read from the archive by ``build_package.check``)."""
    now = datetime.datetime.now(datetime.timezone.utc)
    work = work or f"{DEFAULT_WINDOWS_PARENT}\\{now:%Y%m%dT%H%M%SZ}"
    started = start_host_chain(archive, work, version, STEPS, "build_package",
                               "powershell.exe is not on PATH; a Windows archive is checked in WSL on a Windows host")
    executable, folder, host_work, package, python = (started.executable, started.folder, started.host_work,
                                                      started.package, started.python)
    for sub in ("engines", "scripts"):
        (folder / sub).mkdir()
    (folder / "engines" / f"{PROBE_MODULE}.py").write_text(PROBE_SOURCE, "utf-8")
    (folder / "scripts" / LISTER_SCRIPT).write_text(LIST_DISTRIBUTIONS + "\n", "utf-8")
    (folder / "scripts" / PROBE_SCRIPT).write_text(PROBE_IMPORT + "\n", "utf-8")

    chain = started.done.returncode == 0
    if not chain:
        print(f"build_package: chain: a host step failed with exit status {started.done.returncode} (see above)",
              file=sys.stderr)
    code, lines = host.compare(Path(host.wsl_path(work + "\\runs\\search")))
    for line in lines:
        print(f"build_package: pin: {line}")
    print(f"build_package: engine_version: {engine_version(Path(host.wsl_path(work + '\\runs')))}")

    target = TARGETS[WINDOWS_TARGET]
    scripts = str(host_work / "scripts")
    listed = host.powershell(windows_python_script(work, python, ["-X", "utf8", "-I", f"{scripts}\\{LISTER_SCRIPT}"],
                                                   "list distributions"), capture=True, executable=executable)
    if listed.returncode == 0:
        lock = compare_lock(distributions(_last_line(listed.stdout)), locked_packages(target, version))
    else:
        print(f"build_package: lock: the packaged Python could not list its distributions: "
              f"{(listed.stdout or '').strip()} {(listed.stderr or '').strip()}")
        lock = False

    engines = str(host_work / "engines")
    # With the launcher's flags: they must leave PYTHONPATH in force.
    probed = host.powershell(windows_python_script(work, python, ["-X", "utf8", *PYTHON_FLAGS,
                                                                  f"{scripts}\\{PROBE_SCRIPT}"],
                                                   "import the probe", pythonpath=engines),
                             capture=True, executable=executable)
    where = _last_line(probed.stdout)
    if probed.returncode == 0:
        print(f"build_package: import: {PROBE_MODULE} read from {where}")
        inside = str(PureWindowsPath(where).parent).casefold() == engines.casefold()
    else:
        print(f"build_package: import: failed: {(probed.stdout or '').strip()} {(probed.stderr or '').strip()}")
        inside = False
    demo = f"{scripts}\\{DEMO_SCRIPT}"
    (folder / "scripts" / DEMO_SCRIPT).write_bytes(windows_demo_script(str(package)).encode("utf-8"))
    package_wsl = Path(host.wsl_path(str(package)))
    before = demo_folders(package_wsl)
    ran = host.powershell(windows_demo_host_script(work, demo), executable=executable)
    guided = compare_demo(ran.returncode, before, demo_folders(package_wsl))

    print(f"build_package: the work folder {work} is left on the host")
    return {
        "chain and pin": chain and code == 0,
        "installed packages equal uv.lock": lock,
        "import from a user-named folder": inside,
        "guided demo and pin": guided,
    }
