"""Shared fixtures and helpers: the clone of the reference model repository, throw-away
repositories, one full run of the start commit of the reference chain (release N on the fixed
model) through the run contract with its replay, the stub engines, and the helpers the test
modules share. A test module imports a shared helper from
here, never from another test module.

The reference model is read from the local clone ``repositories/delib-history``. A session
without that clone, or with a clone that lacks the pinned commit, fails at its start:
nothing is skipped.
"""
from __future__ import annotations

import csv
import difflib
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import threading
import time
from contextlib import contextmanager
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

import pytest

from degelmann.deltarecon import changes as changes_contract
from degelmann.deltarecon.__main__ import main
from degelmann.deltarecon.documents import (CONTRACT_VERSION, RECORD_SCHEMA, RUN_REQUEST, RUN_SCHEMA, Rejection,
                                            document_bytes, schema_errors, sha256_file)
from degelmann.deltarecon.regression import read_regression_input, regression
from degelmann.deltarecon.run import (History, ModelPointFailure, Revision, from_worker_outcome, run_request,
                                      worker_outcome)

ROOT = Path(__file__).resolve().parent.parent
REPOSITORIES = ROOT / "repositories"
CLONE_NAME = "delib-history"
CLONE = REPOSITORIES / CLONE_NAME
REPOSITORY_URL = "https://github.com/Degelmann-Solutions/delib-history"
RELEASE_N = "b64334e09613c45a7a12468dfddc0d9ec47819bb"  # the first commit of delib-history
START = "fa368575a66d97c94e96dffc62b273ec95511b12"  # release N on the fixed model, the older end of the reference walk
NEWER = "887b7181d22550eda2fb52fa1a6bd77376d4eb2e"  # the newer revision of the reference walk
PRODUCT_FOLDER = "risikolebensversicherung"
EXAMPLES = ROOT / "contracts" / "v3" / "examples"


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


def committed(path: str, revision: str = START, clone: Path = CLONE) -> bytes:
    """The bytes of a file of a commit, read from the object store."""
    return git(clone, "cat-file", "blob", f"{revision}:{path}")


def require_clone(clone: Path = CLONE, revision: str = START) -> None:
    """End the test session unless ``clone`` is a clone that holds the pinned commit."""
    found = clone.is_dir() and subprocess.run(
        ["git", "--no-optional-locks", "-C", str(clone), "cat-file", "-e", f"{revision}^{{commit}}"],
        capture_output=True, env={"GIT_CEILING_DIRECTORIES": str(clone.parent), "PATH": os.environ.get("PATH", "")})
    if not found or found.returncode != 0:
        pytest.exit(f"The tests read the reference model from a clone at {clone} that holds the commit "
                    f"{revision}. Create it with: git clone {REPOSITORY_URL} {clone}", returncode=1)


# The modules that stamp the contract version on the documents they write.
WRITER_MODULES = ("run", "compare", "signature", "derive", "walk", "search")


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
    for revision in (RELEASE_N, START, NEWER):
        require_clone(revision=revision)


def export_coordinates(path: Path) -> dict[tuple[str, int, str], float]:
    """The values of an export by coordinate, read without ``degelmann.deltarecon``."""
    rows = list(csv.reader(io.StringIO(path.read_text("utf-8"), newline="")))
    return {(row[0], int(row[1]), quantity): float(value)
            for row in rows[1:] for quantity, value in zip(rows[0][2:], row[2:])}


def projection_periods(values: dict[tuple, object]) -> dict[tuple, object]:
    """``values`` on projection periods: each key starts with a model point and a period, and the period
    becomes the period less the first period of its model point in ``values``, as on ``policy_month``,
    whose origin is the issue date. Further members of a key, such as a quantity, are kept."""
    first: dict[str, int] = {}
    for point, period, *_ in values:
        first[point] = min(period, first.get(point, period))
    return {(point, period - first[point], *rest): value for (point, period, *rest), value in values.items()}


def without_volatile(record: dict, *extra: str) -> dict:
    """A run record without the members that name its execution, ``record_id`` and ``recorded_at``,
    and without the members ``extra``."""
    return {key: value for key, value in record.items() if key not in ("record_id", "recorded_at", *extra)}


def expected_deviations(left: Path, right: Path, per_quantity: dict, issue_origin: bool = True) -> list[dict]:
    """The deviation list of two exports, recomputed without ``degelmann/deltarecon/compare.py``.

    The tolerance rule is that of :func:`deviates`. With ``issue_origin``, the time basis of the stub
    and of the model, both exports are aligned on projection periods first.
    """
    old, new = export_coordinates(left), export_coordinates(right)
    if issue_origin:
        old, new = projection_periods(old), projection_periods(new)
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

    Its branch ``work`` starts at the start commit of the reference chain, release N on the fixed model.
    """
    repositories = tmp_path / "repositories"
    repositories.mkdir()
    clone = repositories / CLONE_NAME
    git(ROOT, "clone", "--quiet", "--no-hardlinks", str(CLONE), str(clone))
    git(clone, "checkout", "--quiet", "-B", "work", START)
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


# --- the tolerance rule of compare.md, recomputed without degelmann.deltarecon ---

def rounded(value: float, decimals: int) -> float:
    """Commercial rounding of the decimal number the writer form denotes."""
    step = Decimal(1).scaleb(-decimals)
    return float(Decimal(repr(value)).quantize(step, rounding=ROUND_HALF_UP))


def deviates(left, right, entry):
    """The tolerance rule of compare.md, for the worked values only."""
    if "decimals" in entry:
        left, right = rounded(left, entry["decimals"]), rounded(right, entry["decimals"])
    d, m = right - left, max(abs(left), abs(right))
    return (d > max(entry["upper"]["abs_tol"], entry["upper"]["rel_tol"] * m)
            or -d > max(entry["lower"]["abs_tol"], entry["lower"]["rel_tol"] * m))


# --- a stub engine behind the protocol and the helpers of a stub run ---

RECORD_ID = re.compile(r"record-[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}")
EXACT = {"abs_tol": 0, "rel_tol": 0}
POINTS = "id,first,last,base\nMP-B,0,2,2\nMP-A,12,13,1.5\nMP-C,0,0,1e-05\nMP-D,3,4,1e16\n"
PARAMS = "name,value\nrate,0.01\nlabel,base\n"
POINTS_B = POINTS.replace("MP-B,0,2,2", "MP-B,0,2,4")
PARAMS_RATE = PARAMS.replace("rate,0.01", "rate,0.02")
NEW_BUSINESS = "RLV-000001"
POINT_TABLE = f"{PRODUCT_FOLDER}/model_point_table.csv"
LAPSE_TABLE = f"{PRODUCT_FOLDER}/lapse_table.csv"
MODEL_CODE = f"{PRODUCT_FOLDER}/RLV_DE_S/Projection/__init__.py"


class StubSession:
    """A release state of two text files: ``points.csv`` and ``params.csv``.

    A base that ends with ``!`` names a point whose model check is false: a full run fails it, a
    target-only run, which evaluates no check, computes it. ``project_target`` restricts the
    periods of ``project`` to the target window: on ``policy_month`` counted from the first period
    of a point, its valuation month, on another time basis the periods as they are.
    """

    time_basis = "policy_month"
    quantities = [("Anzahl Verträge", "policies"), ("Netto-Cashflow", "EUR")]
    checks = True  # whether ``project`` evaluates the model check

    def __init__(self, folder: Path):
        self.folder = folder
        lines = (folder / "points.csv").read_text("utf-8").splitlines()[1:]
        self.points = [line.split(",") for line in lines]
        self.params = [line.split(",") for line in
                       (folder / "params.csv").read_text("utf-8").splitlines()[1:]]

    def model_point_ids(self):
        return [point[0] for point in self.points]

    def project(self, model_point_id):
        _, first, last, base = next(p for p in self.points if p[0] == model_point_id)
        if base == "raise":
            raise ModelPointFailure("The stub cannot calculate this model point.")
        if base.endswith("!") and self.checks:
            raise ModelPointFailure("check_stub is false")
        base = base.rstrip("!")
        return [(period, [float(base), float(base) * (period + 1)])
                for period in range(int(first), int(last) + 1)]

    def project_target(self, model_point_ids, quantities, periods):
        keep = [i for i, (name, _) in enumerate(self.quantities) if name in quantities]
        outcomes = []
        for model_point_id in model_point_ids:
            self.checks = False
            try:
                full = self.project(model_point_id)
            except ModelPointFailure as failure:
                outcomes.append(failure)
                continue
            finally:
                self.checks = True
            start, end = full[0][0], full[-1][0]
            offset = start if self.time_basis == "policy_month" else 0  # the period of projection period 0
            first, last = (start, end) if periods is None else (max(start, offset + periods[0]),
                                                                min(end, offset + periods[1]))
            outcomes.append([(period, [values[i] for i in keep]) for period, values in full
                             if first <= period <= last])
        return outcomes

    def parameters(self):
        def value(text):
            try:
                return float(text)
            except ValueError:
                return text
        return [{"name": name, "type": "scalar", "value": value(text)} for name, text in self.params]


class StubEngine:
    """A release is the folder ``rel`` below the repositories folder, named by a file hash.

    The release folder is the revision of the stub: ``line`` is its main line. A change of
    the type ``revision`` names another folder; the state after it is that folder, with
    ``points.csv`` of the release folder of the request when ``input_data`` is held.
    """

    stages = frozenset({"liability_cashflow"})
    realisations = frozenset({"text_patch", "revision"})
    determines = frozenset({"release_folder", "input_data"})
    holdable = {"input_data": frozenset({"data"})}
    line: tuple = ()  # the main line, oldest first: (release folder, log message, classes)

    def __init__(self):
        self.opened = 0
        self.received = []  # the enabled changes of the last call of ``open``

    def history(self, older, newer, repositories):
        """The part of ``line`` after the folder of ``older`` up to the folder of ``newer``."""
        names = [name for name, _, _ in self.line]
        ends = []
        for release in (older, newer):
            folders = [r["value"] for r in release["references"] if r["kind"] == "release_folder"]
            if len(folders) != 1 or folders[0] not in names:
                raise Rejection("unknown_reference", "The release folder is no revision of the stub history.")
            ends.append(names.index(folders[0]))
        if ends[0] > ends[1]:
            raise Rejection("unrelated_revisions", "The older folder does not stand before the newer one.")
        return History("git", names[ends[0]], names[ends[1]],
                       tuple(Revision(name, message, frozenset(classes))
                             for name, message, classes in self.line[ends[0] + 1:ends[1] + 1]))

    @staticmethod
    def references(folder: Path, value: str) -> list[dict]:
        points = folder / "points.csv"
        data = f"points.csv sha256:{sha256_file(points)}" if points.is_file() else "points.csv absent"
        return [{"kind": "release_folder", "value": value}, {"kind": "input_data", "value": data}]

    def state_release(self, base, revision, hold, repositories):
        """The identity of the state after the folder ``revision``; nothing is restored."""
        kept = [r for r in base["references"] if r["kind"] in self.determines]
        if revision is None:
            return {"label": base["label"], "references": kept}
        moved = self.references(Path(repositories) / revision, revision)
        return {"label": base["label"], "references": [moved[0]] + [
            r for r in (kept if "input_data" in hold else moved) if r["kind"] == "input_data"]}

    def _folder(self, release, repositories) -> Path:
        folders = [r["value"] for r in release["references"] if r["kind"] == "release_folder"]
        if len(folders) != 1 or not (Path(repositories) / folders[0] / "points.csv").is_file():
            raise Rejection("unknown_reference", "The release folder cannot be resolved.")
        folder = Path(repositories) / folders[0]
        if sorted(map(str, release["references"])) != sorted(map(str, self.references(folder, folders[0]))):
            raise Rejection("unknown_reference", "The references do not name the release state.")
        return folder

    def resolve(self, release, repositories):
        self._folder(release, repositories)

    @contextmanager
    def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
        """Restore the state to a scratch folder and apply the text patches there."""
        folder = self._folder(release, repositories)
        revisions = [c["realisation"]["revision"] for c in enabled if c["realisation"]["type"] == "revision"]
        with tempfile.TemporaryDirectory() as scratch:
            state = Path(scratch) / folder.name
            if revisions:  # the state after the last enabled revision
                source = Path(repositories) / revisions[-1]
                if not (source / "points.csv").is_file():
                    raise RuntimeError(f"the revision {revisions[-1]} holds no points.csv")
                shutil.copytree(source, state)
                if "input_data" in hold:
                    shutil.copyfile(folder / "points.csv", state / "points.csv")
            else:
                shutil.copytree(folder, state)
            patches = [c for c in enabled if c["realisation"]["type"] == "text_patch"]
            changes_contract.apply_changes(state, patches, manifest_dir)
            for realisation in (c["realisation"] for c in enabled):
                if realisation["type"] == "file_replace":
                    shutil.copyfile(manifest_dir / realisation["file"]["path"], state / realisation["target"])
            self.received, self.held = list(enabled), hold
            self.opened += 1
            yield StubSession(state)


def as_bits(periods) -> list[tuple[int, list[str]]]:
    """The periods of a projection with every value as ``float.hex``, so that equal means bit for bit."""
    return [(period, [value.hex() for value in values]) for period, values in periods]


# --- a stub engine whose sessions project in worker processes ---

_stub_session = None  # the session of a stub worker process


def _stub_start(folder: str) -> None:
    global _stub_session
    _stub_session = StubSession(Path(folder))


def _stub_project(model_point_id: str):
    """One point in a stub worker. An earlier point in writer order sleeps longer, so that the
    points finish in reverse; the base ``crash`` raises an error that is no model point failure."""
    ids = sorted(_stub_session.model_point_ids())
    time.sleep(0.05 * (len(ids) - ids.index(model_point_id)))
    if next(p for p in _stub_session.points if p[0] == model_point_id)[3] == "crash":
        raise RuntimeError("the stub worker crashes")
    return worker_outcome(_stub_session.project, model_point_id)


class WorkerSession(StubSession):
    """The stub session whose ``project_many`` projects the points in worker processes."""

    def __init__(self, folder: Path, engine: "WorkerStub"):
        super().__init__(folder)
        self.engine = engine

    def project_many(self, model_point_ids):
        from degelmann.deltarecon.workers import ordered_map
        self.engine.asked.append(list(model_point_ids))
        results = ordered_map(_stub_start, (str(self.folder),), _stub_project, model_point_ids,
                              self.engine.workers)
        return [from_worker_outcome(result) for result in results]


class WorkerStub(StubEngine):
    """The stub engine with ``workers`` worker processes per session. ``asked`` holds the ids of
    every call of ``project_many``."""

    def __init__(self, workers: int):
        super().__init__()
        self.workers, self.asked = workers, []

    @contextmanager
    def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
        with super().open(release, enabled, manifest_dir, repositories, hold) as session:
            yield WorkerSession(session.folder, self)


@pytest.fixture
def world(tmp_path):
    """A folder with a stub release ``rel`` and an empty run folder ``run``.

    It is the repositories folder of the stub engine.
    """
    release = tmp_path / "rel"
    release.mkdir()
    (release / "points.csv").write_text(POINTS, "utf-8")
    (release / "params.csv").write_text(PARAMS, "utf-8")
    (tmp_path / "run").mkdir()
    return tmp_path


def stub_request(world: Path, **members) -> dict:
    request = {
        "document": "run_request", "contract_version": CONTRACT_VERSION, "stage": "liability_cashflow",
        "run_id": "run-stub",
        "release": {"label": "N", "references": StubEngine.references(world / "rel", "rel")},
        "changes": {"enabled": []}, "selection": {"mode": "full"},
    }
    request.update(members)
    return request


def store(world: Path, request, folder: str = "run") -> Path:
    path = world / folder / "request.json"
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(request if isinstance(request, bytes) else document_bytes(request))
    return path


def run_stub(world: Path, request=None, engine=None, folder: str = "run"):
    engine = engine or StubEngine()
    path = store(world, stub_request(world) if request is None else request, folder)
    return run_request(path, engine, repositories=world), engine


def stored(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def roles(entries: list[dict]) -> dict[str, str]:
    return {entry["role"]: entry["artifact"]["path"] for entry in entries}


def assert_documents_valid(folder: Path) -> None:
    """Every document a run wrote passes its schema, and every listed artifact hashes."""
    assert not schema_errors(stored(folder / "response.json"), RUN_SCHEMA)
    record_path = folder / "run-record.json"
    if record_path.exists():
        record = stored(record_path)
        assert not schema_errors(record, RECORD_SCHEMA)
        for entry in record["inputs"] + record["outputs"]:
            assert sha256_file(folder / entry["artifact"]["path"]) == entry["artifact"]["sha256"]


def patch_text(name: str, old: str, new: str) -> str:
    return "".join(difflib.unified_diff(old.splitlines(keepends=True), new.splitlines(keepends=True),
                                        fromfile=name, tofile=name))


def change(change_id: str, patch: str | None, folder: Path, **members) -> dict:
    """A change entry; its patch file is written into ``folder/patches``."""
    entry = {"id": change_id, "class": "data", "description": f"Synthetic change {change_id}.",
             "prerequisites": [], "conflicts": []}
    entry.update(members)
    if "realisation" not in entry:
        path = folder / "patches" / f"{change_id}.patch"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(patch.encode("utf-8"))
        entry["realisation"] = {"type": "text_patch", "format": "unified_diff",
                                "artifact": {"path": f"patches/{change_id}.patch",
                                             "sha256": sha256_file(path)}}
    return entry


def with_manifest(world: Path, entries: list[dict], enabled: list[str], folder: str = "run",
                  **manifest_members) -> dict:
    """Store a manifest beside the request and return the ``changes`` member that enables it."""
    manifest = {"document": "change_manifest", "contract_version": CONTRACT_VERSION,
                "stage": "liability_cashflow", "manifest_id": "changes-stub", "base_release": "N",
                "changes": entries}
    manifest.update(manifest_members)
    path = world / folder / "changes.json"
    path.write_bytes(document_bytes(manifest))
    return {"enabled": enabled, "manifest": {"path": "changes.json", "sha256": sha256_file(path)}}


def rehash(folder: Path) -> None:
    """Make the stored response and record name the current bytes of the export."""
    digest = sha256_file(folder / "results.csv")
    response = stored(folder / "response.json")
    response["export"]["artifact"]["sha256"] = digest
    (folder / "response.json").write_bytes(document_bytes(response))
    record = stored(folder / "run-record.json")
    for entry in record["outputs"]:
        entry["artifact"]["sha256"] = sha256_file(folder / entry["artifact"]["path"])
    (folder / "run-record.json").write_bytes(document_bytes(record))


def stub_release(world: Path, name: str, points: str = POINTS, params: str = PARAMS, label: str = "regression"):
    """Another stub release below ``world``. Return its release identity."""
    folder = world / name
    folder.mkdir()
    (folder / "points.csv").write_text(points, "utf-8")
    (folder / "params.csv").write_text(params, "utf-8")
    return {"label": label, "references": StubEngine.references(folder, name)}


def stub_regression(world: Path, release: dict, engine=None, tolerance=None):
    engine = engine or StubEngine()
    recorded = read_regression_input(world / "run" / "run-record.json", engine.stages)
    return regression(recorded, release, world / "out", engine, repositories=world, tolerance=tolerance)


def cli(monkeypatch, *arguments) -> int:
    monkeypatch.chdir(ROOT)
    return main([str(argument) for argument in arguments])


def text(path: str) -> str:
    """A file of the start commit of the reference chain, as committed. Its data files are those of release N."""
    return committed(path).decode("utf-8")


def model_request(monkeypatch, folder: Path, *ids: str, revision: str = START,
                  repositories: Path = REPOSITORIES, run_id: str = "run-n-subset", path: str | None = None) -> Path:
    arguments = ["request", "--revision", revision, "--repositories", repositories, "--label", "N",
                 "--run-id", run_id, "--output", folder / "request.json"]
    if path is not None:
        arguments += ["--path", path]
    if ids:
        arguments += ["--subset", *ids]
    assert cli(monkeypatch, *arguments) == 0
    assert not schema_errors(stored(folder / "request.json"), RUN_REQUEST)
    return folder / "request.json"


def with_columns(columns: list[str], line: str, **changes: str) -> str:
    values = line.split(",")
    for column, value in changes.items():
        assert values[columns.index(column)] != value
        values[columns.index(column)] = value
    return ",".join(values)


def edit_file(clone: Path, path: str, old: str, new: str) -> None:
    """Replace one place of a file in the working tree of a throw-away clone, as bytes."""
    file = clone / path
    data = file.read_bytes()
    assert data.count(old.encode("utf-8")) == 1
    file.write_bytes(data.replace(old.encode("utf-8"), new.encode("utf-8")))


# --- a stub engine with a main line, for derive, walk, and search ---

POINTS_E = POINTS_B + "MP-E,0,1,7\n"
# MP-B up by 0.5 and MP-A down by 0.5: the counts of the step partly cancel.
POINTS_CANCEL = POINTS_E.replace("MP-B,0,2,4", "MP-B,0,2,4.5").replace("MP-A,12,13,1.5", "MP-A,12,13,1")
# name, log message, classes, points, parameters
LINE = (
    ("w0", "The base.\n", (), POINTS, PARAMS),
    ("w1", "Raise the rate\n", ("parameter",), POINTS, PARAMS_RATE),
    ("w2", "Touch nothing that has a class\n", (), POINTS, PARAMS_RATE),
    ("w3", "Raise MP-B and add MP-E\n", ("data",), POINTS_E, PARAMS_RATE),
    ("w4", "Move MP-B up and MP-A down\n", ("data", "code"), POINTS_CANCEL, PARAMS_RATE),
)


class WalkSession(StubSession):
    """The stub session whose Netto-Cashflow depends on the parameter ``rate``."""

    def project(self, model_point_id):
        rate = float(dict(self.params)["rate"])
        return [(period, [values[0], values[1] * (1 + rate)])
                for period, values in super().project(model_point_id)]


class WalkStub(StubEngine):
    """The stub engine with a main line of folders. It reads identities that hold further kinds.

    ``drift`` adds a number to every value of the states of the named folders, ``broken``
    names folders whose state cannot be opened, as a recorded result may differ from a state
    or a state may not run.
    """

    def __init__(self, line=LINE, drift: dict | None = None, broken=()):
        super().__init__()
        self.line = tuple((name, message, classes) for name, message, classes, *_ in line)
        self.drift, self.broken = drift or {}, set(broken)

    def _folder(self, release, repositories):
        kept = [r for r in release["references"] if r["kind"] in self.determines]
        return super()._folder({**release, "references": kept}, repositories)

    @contextmanager
    def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
        revisions = [c["realisation"]["revision"] for c in enabled if c["realisation"]["type"] == "revision"]
        name = revisions[-1] if revisions else self._folder(release, repositories).name
        if name in self.broken:
            raise RuntimeError(f"the state {name} cannot be read")
        with super().open(release, enabled, manifest_dir, repositories, hold) as session:
            session.__class__ = WalkSession
            delta = self.drift.get(name)
            if delta is not None:
                plain = session.project
                session.project = lambda point: [(p, [v + delta for v in values]) for p, values in plain(point)]
            yield session


def build(world: Path, line=LINE) -> None:
    for name, _, _, points, params in line:
        folder = world / name
        folder.mkdir(exist_ok=True)
        if points is not None:
            (folder / "points.csv").write_text(points, "utf-8")
        (folder / "params.csv").write_text(params, "utf-8")


def record(world: Path, name: str, engine=None, folder: str | None = None, further=(), label: str | None = None,
           **members) -> Path:
    """Run the stub folder ``name`` without changes and return the path of its run record."""
    identity = {"label": label or name, "references": StubEngine.references(world / name, name) + list(further)}
    folder = folder or f"run-{name}"
    request = stub_request(world, run_id=folder, release=identity, **members)
    path = world / folder / "request.json"
    path.parent.mkdir()
    path.write_bytes(document_bytes(request))
    result = run_request(path, engine or WalkStub(), repositories=world)
    assert result.outcome == "succeeded", result.response
    return result.record_path


class TwoStages(WalkStub):
    stages = frozenset({"liability_cashflow", "other_stage"})


# --- the stub histories of the search ---

CASH = "Netto-Cashflow"
# Placed against the split points of n = 8: the offsetting pair r1, r2 and the revert pair r3, r4
# fall into the interval (0, 4), whose ends agree on the target; the sub-tolerance steps r5 and r6
# into the two halves of (4, 6); r7 adds a model point; r8 moves the cash flow alone.
POINTS_UP = POINTS.replace("MP-B,0,2,2", "MP-B,0,2,3")
POINTS_C = POINTS.replace("MP-C,0,0,1e-05", "MP-C,0,0,1")
POINTS_T1 = POINTS.replace("MP-B,0,2,2", "MP-B,0,2,2.006")
POINTS_T2 = POINTS.replace("MP-B,0,2,2", "MP-B,0,2,2.012")
POINTS_T2E = POINTS_T2 + "MP-E,0,1,7\n"
HISTORY = (
    ("h0", "The base.\n", (), POINTS, PARAMS),
    ("h1", "Raise MP-B\n", ("data",), POINTS_UP, PARAMS),
    ("h2", "Offset the raise of MP-B\n", ("data",), POINTS.replace("MP-B,0,2,2", "MP-B,0,2,2.0"), PARAMS),
    ("h3", "Raise MP-C\n", ("data",), POINTS_C, PARAMS),
    ("h4", "Revert the raise of MP-C\n", ("data",), POINTS, PARAMS),
    ("h5", "Raise MP-B a little\n", ("data",), POINTS_T1, PARAMS),
    ("h6", "Raise MP-B a little more\n", ("data",), POINTS_T2, PARAMS),
    ("h7", "Add MP-E\n", ("data",), POINTS_T2E, PARAMS),
    ("h8", "Raise the rate\n", ("parameter",), POINTS_T2E, PARAMS_RATE),
)
# A, its revert B, C that contributes, and D without effect.
CANCEL = (
    ("c0", "The base.\n", (), POINTS, PARAMS),
    ("c1", "A: raise the rate\n", ("parameter",), POINTS, PARAMS_RATE),
    ("c2", "B: revert A\n", ("parameter",), POINTS, PARAMS),
    ("c3", "C: raise MP-B\n", ("data",), POINTS_B, PARAMS),
    ("c4", "D: touch nothing\n", (), POINTS_B, PARAMS),
)


# --- two stub runs and a compare request between them ---


def release(world: Path, name: str, points: str, params: str | None = None) -> dict:
    """A second stub release below ``world``. Return its release identity."""
    folder = world / name
    folder.mkdir()
    (folder / "points.csv").write_text(points, "utf-8")
    (folder / "params.csv").write_text(params or (world / "rel" / "params.csv").read_text("utf-8"), "utf-8")
    return {"label": name, "references": StubEngine.references(folder, name)}


def run_side(world: Path, side: str, points: str | None = None, params: str | None = None, engine=None,
             **members):
    """One stub run in the folder ``side``, of the base release or of a release with other files."""
    if points is not None or params is not None:
        members["release"] = release(world, f"rel-{side}", points or POINTS, params)
    result, _ = run_stub(world, stub_request(world, run_id=f"run-{side}", **members), engine, folder=side)
    return result


def reference(world: Path, relative: str) -> dict:
    return {"path": relative, "sha256": sha256_file(world / relative)}


def compare_request(world: Path, per_quantity: dict | None = None, records: bool = True,
                    left: str = "left", right: str = "right", **members) -> Path:
    """Store a compare request in ``world`` that names the runs in the folders ``left`` and ``right``."""
    request = {"document": "compare_request", "contract_version": CONTRACT_VERSION, "stage": "liability_cashflow",
               "compare_id": "compare-stub"}
    for name, folder in (("left", left), ("right", right)):
        request[name] = {"response": reference(world, f"{folder}/response.json")}
        if records:
            request[name]["run_record"] = reference(world, f"{folder}/run-record.json")
    request["tolerance"] = {"per_quantity": per_quantity or {}}
    request.update(members)
    path = world / "compare.request.json"
    path.write_bytes(document_bytes(request))
    return path


@pytest.fixture(scope="session")
def full_chain_process(tmp_path_factory):
    """Start request, full run, and replay as three commands in a row, without waiting.

    The release is named by the pinned commit, and the clone is found at the default place,
    ``repositories/`` in the working directory. The chain takes about twice the time of a
    full run. It is started in a thread so that it runs beside the other tests.
    """
    folder = tmp_path_factory.mktemp("full-chain") / "run"
    commands = [
        ["request", "--revision", START, "--label", "N", "--run-id", "run-n-full",
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
