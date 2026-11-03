"""The version of the project, the Python version ``requires-python`` pins, and the standalone
CPython build of a target: downloaded into a cache, verified against its pinned SHA-256, and its
version read from the ``PY_VERSION`` line of its ``patchlevel.h``.
"""
from __future__ import annotations

import re
import shutil
import tomllib
import urllib.parse
import urllib.request
from pathlib import Path

from tools.common import ROOT, Refused, sha256_file

PYPROJECT = ROOT / "pyproject.toml"
DOWNLOADS = ROOT / "build" / "python-downloads"


def project(pyproject: Path = PYPROJECT) -> tuple[str, str]:
    """The version of the project and the Python version ``requires-python`` pins (``==X.Y.Z``)."""
    table = tomllib.loads(pyproject.read_text("utf-8"))["project"]
    pin = table["requires-python"].strip()
    if not pin.startswith("==") or "," in pin or "*" in pin:
        raise Refused(f"requires-python must pin one version (==X.Y.Z), found {pin!r}")
    return table["version"], pin[2:].strip()


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
