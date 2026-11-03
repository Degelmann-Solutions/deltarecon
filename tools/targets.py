"""The target platforms of the package: one row of ``TARGETS`` per platform, the texts of the
launcher and of the starter of the guided demo, and the names of a package folder and its archive.
"""
from __future__ import annotations

from pathlib import Path

from tools.common import REPOSITORIES_VARIABLE, Refused

LAUNCHER = "deltarecon"
WINDOWS_LAUNCHER = "deltarecon.cmd"

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

# The starter of the guided demo: changes to its own folder, so the demo writes ``runs/`` there,
# runs ``deltarecon quickstart`` through the launcher with the arguments unchanged, keeps the window
# open, and exits with the launcher's status. Shell builtins only, so it runs with an empty PATH; it
# waits for Enter only when its input is a terminal.
STARTER = "quickstart"
WINDOWS_STARTER = "quickstart.cmd"
STARTER_TEXT = f"""#!/bin/sh
# DeltaRecon guided demo: runs "deltarecon quickstart" in this folder. Shell builtins only.
case $0 in
    */*) here=${{0%/*}} ;;
    *) here=. ;;
esac
CDPATH= cd -- "$here" || exit 2
./{LAUNCHER} quickstart "$@"
status=$?
if [ -t 0 ]; then
    printf '%s\n' 'Press Enter to close. / Enter schließt das Fenster.'
    read -r line
fi
exit $status
"""

# The Windows starter: cmd builtins only. pushd changes to the starter's folder and popd returns,
# so a double click and a call from another folder both write runs\ in the package folder.
WINDOWS_STARTER_TEXT = "\r\n".join([
    "@echo off",
    "rem DeltaRecon guided demo: runs \"deltarecon quickstart\" in this folder. cmd builtins only.",
    "setlocal",
    'pushd "%~dp0"',
    f'call "%~dp0{WINDOWS_LAUNCHER}" quickstart %*',
    'set "status=%ERRORLEVEL%"',
    "pause",
    "popd",
    "exit /b %status%",
    "",
])

TARGET = "x86_64-unknown-linux-gnu"
WINDOWS_TARGET = "x86_64-pc-windows-msvc"
# One row per target platform: the python-build-standalone archive (URL and SHA-256 of the
# release's SHA256SUMS), where the interpreter, site-packages, pip and the header that names the
# Python version lie in the unpacked ``python/``, the marker environment the lock's markers are
# evaluated in, the launcher and the starter of the guided demo (name and text), the platform the
# guides and the release notes name, and the suffix of the package archive.
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
        "starter": (STARTER, STARTER_TEXT),
        "platform": "Linux x86-64",
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
        "starter": (WINDOWS_STARTER, WINDOWS_STARTER_TEXT),
        "platform": "Windows x86-64",
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


def package_name(version: str, target: str = TARGET) -> str:
    return f"deltarecon-{version}-{target}"


def archive_name(version: str, target_name: str) -> str:
    return f"{package_name(version, target_name)}.{TARGETS[target_name]['archive']}"


def target_of(archive: Path, version: str) -> str:
    """The target whose archive name ``archive`` bears; another name is refused."""
    for name in TARGETS:
        if archive.name == archive_name(version, name):
            return name
    expected = ", ".join(archive_name(version, name) for name in TARGETS)
    raise Refused(f"the archive name {archive.name} names no target; expected one of {expected}")
