"""Shared fixtures: the clone of the reference model repository, throw-away repositories,
and one full run of release N through the run contract with its replay.

The reference model is read from the local clone ``repositories/delib-history``. A session
without that clone, or with a clone that lacks the pinned commit, fails at its start:
nothing is skipped.
"""
from __future__ import annotations

import csv
import hashlib
import io
import json
import os
import subprocess
import sys
import threading
from contextlib import contextmanager
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
REPOSITORIES = ROOT / "repositories"
CLONE_NAME = "delib-history"
CLONE = REPOSITORIES / CLONE_NAME
REPOSITORY_URL = "https://github.com/Degelmann-Solutions/delib-history"
RELEASE_N = "b64334e09613c45a7a12468dfddc0d9ec47819bb"  # the first commit of delib-history
PRODUCT_FOLDER = "risikolebensversicherung"


def folder_hashes(folder: Path) -> dict[str, str]:
    return {p.relative_to(folder).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in sorted(folder.rglob("*")) if p.is_file()}


def git_environment() -> dict[str, str]:
    """The environment of the Git commands of the tests.

    It names no repository, index, or working tree, so a command started under a Git hook
    acts on the folder it is given, and it ignores replace references.
    """
    environment = {name: value for name, value in os.environ.items()
                   if name not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")}
    environment["GIT_NO_REPLACE_OBJECTS"] = "1"
    return environment


def git(folder: Path, *arguments: str) -> bytes:
    """The output of a Git command in ``folder``. The command must succeed."""
    done = subprocess.run(["git", "--no-optional-locks", "-C", str(folder), *arguments],
                          capture_output=True, env=git_environment())
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    return done.stdout


def clone_state(clone: Path = CLONE) -> tuple[bytes, bytes, bytes]:
    """What a run must leave as it is: the status, ``HEAD``, and the references of a clone."""
    return (git(clone, "status", "--porcelain", "--ignored"), git(clone, "rev-parse", "HEAD"),
            git(clone, "for-each-ref"))


def committed(path: str, revision: str = RELEASE_N, clone: Path = CLONE) -> bytes:
    """The bytes of a file of a commit, read from the object store."""
    return git(clone, "cat-file", "blob", f"{revision}:{path}")


def require_clone(clone: Path = CLONE, revision: str = RELEASE_N) -> None:
    """End the test session unless ``clone`` is a clone that holds the pinned commit."""
    found = clone.is_dir() and subprocess.run(
        ["git", "--no-optional-locks", "-C", str(clone), "cat-file", "-e", f"{revision}^{{commit}}"],
        capture_output=True, env={"GIT_CEILING_DIRECTORIES": str(clone.parent), "PATH": os.environ.get("PATH", "")})
    if not found or found.returncode != 0:
        pytest.exit(f"The tests read the reference model from a clone at {clone} that holds the commit "
                    f"{revision}. Create it with: git clone {REPOSITORY_URL} {clone}", returncode=1)


# The modules that stamp the contract version on the documents they write.
WRITER_MODULES = ("run", "compare", "signature", "derive", "walk", "search", "replay", "regression", "__main__")


@contextmanager
def written_under(version: str):
    """The tool writes ``version`` instead of its own contract version while the block runs.

    It gives genuine documents of an earlier version, with consistent hashes, without editing JSON by
    hand. Reading is not changed: every document is still read against the schemas of its version.
    """
    with pytest.MonkeyPatch.context() as patch:
        for name in WRITER_MODULES:
            patch.setattr(f"degelmann.deltarecon.{name}.CONTRACT_VERSION", version)
        yield


def pytest_sessionstart(session):
    require_clone()


def export_coordinates(path: Path) -> dict[tuple[str, int, str], float]:
    """The values of an export by coordinate, read without ``degelmann.deltarecon``."""
    rows = list(csv.reader(io.StringIO(path.read_text("utf-8"), newline="")))
    return {(row[0], int(row[1]), quantity): float(value)
            for row in rows[1:] for quantity, value in zip(rows[0][2:], row[2:])}


def expected_deviations(left: Path, right: Path, per_quantity: dict) -> list[dict]:
    """The deviation list of two exports, recomputed without ``degelmann/deltarecon/compare.py``.

    The tolerance rule is that of ``rounded`` and ``deviates`` in ``test_contracts.py``.
    """
    from test_contracts import deviates
    old, new = export_coordinates(left), export_coordinates(right)
    order = next(csv.reader(io.StringIO(left.read_text("utf-8"), newline="")))[2:]
    keys = sorted(set(old) & set(new), key=lambda key: (key[0], key[1], order.index(key[2])))
    exact = {"upper": {"abs_tol": 0, "rel_tol": 0}, "lower": {"abs_tol": 0, "rel_tol": 0}}
    return [{"model_point_id": key[0], "period": key[1], "quantity": key[2], "left": old[key], "right": new[key]}
            for key in keys if deviates(old[key], new[key], per_quantity.get(key[2], exact))]


DEVIATION_HEADER = ["model_point_id", "period", "quantity", "left", "right"]


def deviation_rows(result_path: Path) -> list[dict]:
    """The rows of the deviation file a stored compare result references, read without ``degelmann.deltarecon``.

    The file must have the stated hash and the header of a deviation file.
    """
    result = json.loads(result_path.read_text("utf-8"))
    reference = result["deviations"]
    path = result_path.parent / reference["path"]
    assert hashlib.sha256(path.read_bytes()).hexdigest() == reference["sha256"], path
    rows = list(csv.reader(io.StringIO(path.read_text("utf-8"), newline="")))
    assert rows[0] == DEVIATION_HEADER, rows[0]
    return [{"model_point_id": row[0], "period": int(row[1]), "quantity": row[2], "left": float(row[3]),
             "right": float(row[4])} for row in rows[1:]]


def throwaway(tmp_path: Path) -> tuple[Path, Path]:
    """A repositories folder with a clone of the reference model that a test may commit to.

    Its branch ``work`` starts at release N.
    """
    repositories = tmp_path / "repositories"
    repositories.mkdir()
    clone = repositories / CLONE_NAME
    git(ROOT, "clone", "--quiet", "--no-hardlinks", str(CLONE), str(clone))
    git(clone, "checkout", "--quiet", "-B", "work", RELEASE_N)
    return repositories, clone


def commit(clone: Path, message: str) -> str:
    """Commit every change of the working tree of a throw-away clone. Return the full hash."""
    git(clone, "add", "--all")
    git(clone, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false",
        "commit", "--quiet", "--no-verify", "-m", message)
    return git(clone, "rev-parse", "HEAD").decode("ascii").strip()


IDENTITY = ("-c", "user.name=Test", "-c", "user.email=test@example.invalid", "-c", "commit.gpgsign=false")


def empty_repository(tmp_path: Path) -> tuple[Path, Path]:
    """A repositories folder with a new, empty repository in the place of the clone.

    Its branch is ``work``. It holds no model: it serves tests that read a history only.
    """
    repositories = tmp_path / "repositories"
    clone = repositories / CLONE_NAME
    clone.mkdir(parents=True)
    git(clone, "init", "--quiet", "--initial-branch", "work")
    return repositories, clone


def write_files(clone: Path, files: dict[str, str | None]) -> None:
    """Write files into the working tree of a throw-away clone; ``None`` removes a file."""
    for path, content in files.items():
        target = clone.joinpath(*path.split("/"))
        if content is None:
            target.unlink()
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(content.encode("utf-8"))


def commit_message(clone: Path, message: bytes) -> str:
    """Commit every change of the working tree with exactly these message bytes. Return the full hash.

    The commit may change nothing, and its message may be empty or not UTF-8. The commit
    object is written as such, because ``git commit`` cleans a message up and
    ``git commit-tree`` re-encodes one that is not UTF-8.
    """
    git(clone, "add", "--all")
    tree = git(clone, "write-tree").decode("ascii").strip()
    parents = subprocess.run(["git", "-C", str(clone), "rev-parse", "--verify", "--quiet", "HEAD"],
                             capture_output=True, env=git_environment()).stdout.decode("ascii").split()
    person = b"Test <test@example.invalid> 1760000000 +0000"
    content = (f"tree {tree}\n".encode("ascii") + b"".join(f"parent {p}\n".encode("ascii") for p in parents)
               + b"author " + person + b"\ncommitter " + person + b"\n\n" + message)
    done = subprocess.run(["git", "-C", str(clone), "hash-object", "-t", "commit", "-w", "--stdin"],
                          input=content, capture_output=True, env=git_environment())
    assert done.returncode == 0, done.stderr.decode("utf-8", "replace")
    revision = done.stdout.decode("ascii").strip()
    git(clone, "update-ref", "HEAD", revision)
    return revision


def branch(clone: Path, name: str, start: str = "HEAD") -> None:
    """Create the branch ``name`` at ``start`` in a throw-away clone and check it out."""
    git(clone, "checkout", "--quiet", "-b", name, start)


def merge(clone: Path, into: str, name: str, message: str) -> str:
    """Merge the branch ``name`` into ``into`` with a merge commit. Return its full hash.

    ``into`` is the first parent of the merge, also when it could be fast-forwarded.
    """
    git(clone, "checkout", "--quiet", into)
    git(clone, *IDENTITY, "merge", "--quiet", "--no-ff", "--no-verify", "-m", message, name)
    return git(clone, "rev-parse", "HEAD").decode("ascii").strip()


@pytest.fixture(scope="session")
def full_chain_process(tmp_path_factory):
    """Start request, full run, and replay as three commands in a row, without waiting.

    The release is named by the pinned commit, and the clone is found at the default place,
    ``repositories/`` in the working directory. The chain takes about twice the time of a
    full run. It is started in a thread so that it runs beside the other tests.
    """
    folder = tmp_path_factory.mktemp("full-chain") / "run"
    commands = [
        ["request", "--revision", RELEASE_N, "--label", "N", "--run-id", "run-n-full",
         "--output", str(folder / "request.json")],
        ["run", str(folder / "request.json")],
        ["replay", str(folder / "run-record.json")],
    ]
    state = {"folder": folder, "steps": [], "before": clone_state(), "process": None}
    stop, lock = threading.Event(), threading.Lock()

    def work():
        for command in commands:
            with lock:
                if stop.is_set():
                    return
                process = state["process"] = subprocess.Popen(
                    [sys.executable, "-m", "degelmann.deltarecon", *command], cwd=ROOT,
                    stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            stdout, stderr = process.communicate()
            state["steps"].append((process.returncode, stdout, stderr))

    state["thread"] = threading.Thread(target=work, daemon=True)
    state["thread"].start()
    yield state
    # A session that never waited for the chain stops it: no further command starts and a
    # running one is terminated. A finished chain is unaffected.
    with lock:
        stop.set()
        process = state["process"]
        if process is not None and process.poll() is None:
            process.terminate()
    state["thread"].join(timeout=30)


@pytest.fixture(scope="session")
def full_chain(full_chain_process):
    """The finished chain: its folder, the three command results, and the state of the clone."""
    full_chain_process["thread"].join()
    full_chain_process.setdefault("after", clone_state())
    return full_chain_process
