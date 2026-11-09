"""What every release tool shares: the checkout root, the pin of the quick-start search, the two
exceptions that set the exit status, Git in this checkout, and the names the package shares with
DeltaRecon itself (taken from ``degelmann.deltarecon``, the clone's names from the reference model,
so each has one source).
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

from degelmann.deltarecon.documents import sha256_file
from degelmann.deltarecon.engines.reference_model import CLONE_NAME, REPOSITORIES_VARIABLE

__all__ = ["ROOT", "PIN", "REPOSITORY_URL", "CLONE_NAME", "REPOSITORIES_VARIABLE", "Failed", "Refused", "git_text",
           "engine_version", "sha256_file"]

ROOT = Path(__file__).resolve().parent.parent
PIN = ROOT / "measurements" / "quick-start-search.SHA256SUMS"
REPOSITORY_URL = "https://github.com/Degelmann-Solutions/deltarecon"


class Failed(Exception):
    """A build step or a check that does not hold: exit status 1."""


class Refused(Exception):
    """The tool cannot start: exit status 2."""


def git_text(*arguments: str, folder: Path = ROOT) -> str | None:
    """The stripped output of ``git -C folder <arguments>``; None when git fails or cannot start."""
    try:
        done = subprocess.run(["git", "-C", str(folder), *arguments], capture_output=True, text=True)
    except OSError:
        return None
    return done.stdout.strip() if done.returncode == 0 else None


def engine_version(runs: Path) -> str | None:
    """The ``engine_version`` reference of the request the request step wrote below ``runs``."""
    path = runs / "n-full" / "request.json"
    if not path.is_file():
        return None
    references = json.loads(path.read_text("utf-8"))["release"]["references"]
    return next((r["value"] for r in references if r["kind"] == "engine_version"), None)
