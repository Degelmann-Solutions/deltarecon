"""Build the DeltaRecon package for Linux and for Windows, a folder that holds everything a run needs, and check it.

    uv run python tools/build_package.py build [--target NAME] [--output DIR] [--source URL|PATH]
    uv run python tools/build_package.py check ARCHIVE [--work DIR]

``build`` assembles ``deltarecon-<version>-<target>/`` and its archive in the output folder
(default ``dist/``). The target (``--target``, default ``x86_64-unknown-linux-gnu``) is a row of
``TARGETS`` (``tools/targets.py``): ``x86_64-unknown-linux-gnu`` writes a ``.tar.gz``,
``x86_64-pc-windows-msvc`` a ``.zip`` (deflated). Both are built on Linux; nothing runs the packaged interpreter at build time, so the
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
  removed, so the installed distributions are exactly the locked ones. Every member of the wheel
  outside its ``.dist-info`` must map to a file Git tracks (the folders of the wheel's
  ``force-include`` to the checkout folders they come from), or the build fails naming it; the
  ``direct_url.json`` the install writes, which names the folder the wheel was built in, is
  removed with its row in ``RECORD``.
- ``delib-history/``: a full ``git clone`` of ``--source`` (default the GitHub repository; a local
  path is allowed). A shallow clone is refused. Whatever ``--source`` is, the remote ``origin`` of
  the clone is set to the GitHub repository and ``.git/logs`` (the reflogs, which name the builder
  and the source) is removed; branches and history stay.
- the files of ``profiles/`` that Git tracks (``git ls-files``; ignored and untracked files stay
  behind) and ``LICENSE`` of this checkout.
- a launcher that sets ``DELTARECON_REPOSITORIES`` to its own folder, removes ``PYTHONHOME`` and
  runs the packaged Python with ``-P -s -m degelmann.deltarecon`` and the arguments unchanged:
  ``-P`` keeps the current folder and ``-s`` the user's site-packages off ``sys.path``, so neither
  replaces the packaged code. It passes no ``-I`` or ``-E``, so ``PYTHONPATH`` reaches the packaged
  Python. On Linux it is ``deltarecon``, a POSIX script that
  uses only shell builtins and resolves its folder from ``$0`` (a symbolic link to it from another
  folder is not supported); on Windows it is ``deltarecon.cmd`` (CRLF, cmd builtins only), which
  resolves its folder from ``%~dp0``.
- the starter of the guided demo, which changes to its own folder, runs the launcher with
  ``quickstart`` and the arguments unchanged, keeps the window open and exits with the launcher's
  status. On Linux it is ``quickstart`` (POSIX sh, builtins only, mode 0755), which resolves its
  folder from ``$0`` like the launcher and waits for Enter only when its input is a terminal; on
  Windows it is ``quickstart.cmd`` (CRLF, cmd builtins only), which changes there with ``pushd``,
  ends with ``pause`` and returns with ``popd``.
- the guides ``LIESMICH.txt`` (German) and ``README.txt`` (English), UTF-8 without BOM, LF on Linux
  and CRLF on Windows (``guide_text``): the version and platform, how to start the guided demo, the
  six commands of the README quick start (from ``STEPS`` of ``tools/quick_start_steps.py``; on
  Windows a cmd and a PowerShell block), and the README at the tag ``v<version>``.

The folder and the archive are assembled in a temporary folder inside the output folder and moved
to their final names only when both are complete, so a failed build leaves nothing behind; nothing
is written when the folder or the archive exists already. A symbolic link in the Windows folder
fails the build.

``check`` takes the target from the archive's name, which must be ``deltarecon-<version>-<target>``
with the target's suffix. It unpacks the archive into a new folder and proves five claims,
printing each result. The chain, the import and the demo run with the caller's environment as it
is (on Windows the host user's), ``PYTHONPATH``, ``PYTHONHOME``, ``VIRTUAL_ENV`` and
``DELTARECON_REPOSITORIES`` included, with only ``PATH`` replaced by an empty folder:

1. The README quick start (``STEPS`` of ``tools/quick_start_steps.py``) runs through the
   launcher from the work folder, which holds no ``repositories/``, with ``PATH`` an empty folder
   (no ``uv``, no ``git``); every step exits with its expected status, and the search folder
   matches the pin ``measurements/quick-start-search.SHA256SUMS``.
2. The distributions installed in the packaged Python (name normalised, version) equal the
   runtime lines of ``uv export --locked --no-dev`` whose markers hold for the target, plus
   ``degelmann-deltarecon`` itself.
3. A module written to ``<work>/engines/`` imports in the packaged Python, started with the
   launcher's flags ``-P -s``, with ``PYTHONPATH`` set to that folder and an empty ``PATH``, and is
   read from that folder.
4. The guided demo: the starter runs with ``--no-pause`` from the work folder, its input empty,
   with the environment of the chain; it exits with 0, and exactly one new folder
   ``runs/quickstart-*/`` in the package folder holds a ``search/`` that matches the pin. On Linux
   its output goes to ``<work>/logs/quickstart.log``.
5. No build-machine traces, read from the archive itself in WSL for both targets after the other
   four: no member lies below ``delib-history/.git/logs/``, and no member's name, bytes or link
   target contains the home folder of this machine, the checkout root or the archive's own folder.
   Each offending member is printed.

It also prints the ``engine_version`` the request step recorded.

A Linux archive is checked here; ``--work`` (default a new folder in the system's temporary folder)
must lie outside this checkout. A Windows archive is checked natively on the Windows host of this
WSL session through ``powershell.exe`` (the helpers of ``tools/host.py``): ``--work``
(default ``C:\\tmp\\deltarecon-package-check\\<UTC timestamp>``) must be a new local folder under
``C:\\``; WSL and UNC paths and other drives are refused. The archive is copied there and unpacked
with .NET ``ZipFile``, the code behind ``Expand-Archive``; the host prints each step with its exit
status and seconds. The lister and the probe run as script files under ``<work>\\scripts\\``, and
the demo through ``<work>\\scripts\\demo.cmd``, which calls the starter with its input from ``NUL``;
its output passes through like the chain's. The pin and the lock are compared from WSL. The folder is
left on the host.

Exit status: 0 when the build completes or every check holds; 1 when a build step fails (a
failing command, a shallow clone, a wheel member Git does not track, a symbolic link in a Windows
folder) or a check does not hold; 2 when the tool cannot start (an existing output or work folder,
a work folder inside this checkout or, for Windows, not a new local folder under ``C:\\``, an archive whose name names no target, a
missing archive, no ``powershell.exe`` for a Windows check, ``uv`` or ``git`` missing from
``PATH``, a target URL that does not name the pinned Python, a failed download, a download whose
SHA-256 differs from the pin, a Python version other than the pin). Standard library, the
DeltaRecon package of this checkout, and ``packaging`` (in the development environment) only.

This module is the command line; the work lies in the library modules of ``tools/``:
``python_runtime`` (the pinned Python), ``assembly`` (``build``), ``guides``, ``package_check`` (what
both checks share), ``check_linux`` and ``check_windows``.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# Run as a file, the folder of this file is first on sys.path; the package ``tools`` needs its parent.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools.assembly import DEFAULT_OUTPUT, DEFAULT_SOURCE, build  # noqa: E402
from tools.check_linux import check_linux  # noqa: E402
from tools.check_windows import DEFAULT_WINDOWS_PARENT, check_windows  # noqa: E402
from tools.common import Failed, Refused  # noqa: E402
from tools.package_check import TRACES_CLAIM, check_traces, report  # noqa: E402
from tools.python_runtime import project  # noqa: E402
from tools.targets import TARGET, TARGETS, WINDOWS_TARGET, package_name, target_of  # noqa: E402


def check(archive: Path, work: str | None) -> bool:
    """Check ``archive`` for the target its name bears: here for Linux, on the Windows host for Windows;
    then, for both, the archive itself for traces of this machine. Whether all five claims hold."""
    version, _ = project()
    target_name = target_of(archive, version)
    archive = archive.resolve()
    if not archive.is_file():
        raise Refused(f"no archive at {archive}")
    if target_name == WINDOWS_TARGET:
        results = check_windows(archive, work, version)
    else:
        results = check_linux(archive, None if work is None else Path(work), TARGETS[target_name], version)
    results[TRACES_CLAIM] = check_traces(archive)
    return report(results)


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
