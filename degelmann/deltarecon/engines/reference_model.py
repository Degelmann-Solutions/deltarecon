"""The reference model ``RLV_DE_S`` behind the run contract.

This is the only module that imports modelx and the only one that starts Git. It checks
the release identity, restores the state of the named revisions to a scratch folder,
applies the enabled text patches there, lists the model points, projects a selection,
maps the model's variables to the quantity names of the domain reference, reports
failures, and builds the parameter inventory. It also reads the history between two
revisions: the main line, the log messages, and the classes of the touched paths. The
clone it reads is never written: no checkout, no worktree, no fetch, and no modelx writer.

Release identity
----------------
A release is a commit of the reference model repository ``delib-history``. The caller names
it by four opaque references without an artifact:

- one reference for each kind a revision determines, ``code_state``, ``parameter_set``,
  and ``input_data``, each with a value ``git:<repository URL>@<full commit hash>``;
- one ``engine_version`` that names modelx, pandas, numpy, and Python.

``code_state`` and ``parameter_set`` name one commit, the state commit. ``input_data``
names the same commit or another one, the input-data commit: a regression run names a
newer state commit and the input-data commit of the recorded run. The engine restores the
tree of the state commit and lays ``model_point_table.csv`` of the input-data commit over
it. The model and the parameter tables must be in the state commit, the model point table
in the input-data commit.

The set must be complete. A missing or a surplus reference is rejected with
``unknown_reference``, and so are two state commits, a repository the engine does not
know, a hash that is not a commit of the local clone, and a commit that lacks the model
or one of the input files it is read for.

The repository URL says where the state comes from; the commit hash proves it. The engine
reads the clone ``<repositories folder>/delib-history`` and never uses the network. It does
not look at the remote of the clone.

Changes
-------
The path of a text patch is relative to the root of the repository, for example
``risikolebensversicherung/lapse_table.csv``.

A change of the type ``revision`` names a commit. With an enabled prefix of revisions the
engine restores the last enabled revision instead of the state commit of the request: its
tree is the state, and its model point table is the input data. With ``changes.hold``
naming ``input_data``, the only kind the engine can hold, the model point table stays that
of the input-data commit of the request. A revision state that lacks the model or an input
file cannot be restored and ends the run with the outcome ``error``.

``state_release`` names such a state as a release identity without restoring it: the
revision as state commit, the revision or the held input-data commit as input-data commit,
the label of the base identity, and the present engine version.

History
-------
The revision of a release identity is the state commit. The history between two
identities is the first-parent chain from the newer state commit back to the older one; a
merge is one revision. The class of a touched path:

- ``risikolebensversicherung/model_point_table.csv`` is ``data``;
- every other ``*.csv`` directly in ``risikolebensversicherung/`` is ``parameter``;
- everything under ``risikolebensversicherung/RLV_DE_S/`` is ``code``;
- every other path has no class.

The paths a revision touches are those that differ from its first parent, without rename
detection: a moved file counts with its old and its new path. Git is asked through
plumbing commands with explicit options, and the log message is read from the commit
object, so that no configuration of the user or the system changes the result.
"""
from __future__ import annotations

import os
import platform
import re
import subprocess
import tempfile
from contextlib import contextmanager
from pathlib import Path

import modelx as mx
from modelx.core import errors as mx_errors
import numpy as np
import pandas as pd

from .. import changes as changes_contract
from ..documents import Rejection
from ..run import SCRATCH_PREFIX, History, ModelPointFailure, Revision, UsageError

STAGE = "liability_cashflow"
SOURCE = "git"
REPOSITORY_URL = "https://github.com/Degelmann-Solutions/delib-history"
CLONE_NAME = "delib-history"          # the folder of the clone below the repositories folder
PRODUCT_FOLDER = "risikolebensversicherung"
MODEL_NAME = "RLV_DE_S"
# The kinds of release reference a revision fixes. ``engine_version`` stays its own reference.
DETERMINED_KINDS = frozenset({"code_state", "parameter_set", "input_data"})
STATE_KINDS = ("code_state", "parameter_set")  # the kinds that name the state commit
REVISION_VALUE = re.compile(r"(?P<source>git):(?P<repository>[^@\s]+)@(?P<revision>[0-9a-f]{40})")
MODEL_POINT_FILE = "model_point_table.csv"
MODEL_POINT_ID_COLUMN = "policy_id"
PARAMETER_TABLES = ("benefit_schedule", "freq_loading_table", "lapse_table", "mort_table",
                    "nvg_schedule")
NOT_A_PARAMETER = {"point_id"}       # the argument of the projection space
NOT_A_VALUE_COLUMN = {"provenance"}  # documentation of a row, not an assumption
TIME_BASIS = "policy_month"
# Quantity name, unit, and the column of ``result_cf`` it is read from, in domain order.
# ``kalkulatorische Kosten`` is not exported yet; ``liability_cf`` is the negative of
# ``net_cf`` and is not exported.
QUANTITIES = (
    ("Anzahl Verträge", "policies", "pols_if"),
    ("Bruttobeitrag", "EUR", "prem_gross"),
    ("Zahlbeitrag", "EUR", "premiums"),
    ("Beitragsverrechnung", "EUR", "prem_rebate"),
    ("garantierte Todesfallleistung", "EUR", "claims_death"),
    ("garantierter Rückkaufswert", "EUR", "claims_lapse"),
    ("garantierte Erlebensfallleistung", "EUR", "claims_maturity"),
    ("Kosten 2. Ordnung ohne Provisionen", "EUR", "expenses"),
    ("Provisionen", "EUR", "commissions"),
    ("Netto-Cashflow", "EUR", "net_cf"),
)
CHECKS = ("check_net_cf", "check_pols_roll_fwd", "check_prem_split", "check_res_roll_fwd",
          "check_no_cash_value")


def engine_version() -> str:
    return (f"modelx {mx.__version__}, pandas {pd.__version__}, numpy {np.__version__}, "
            f"Python {platform.python_version()}")


def reference_value(revision: str) -> str:
    """The value that names the commit ``revision`` of the reference model repository."""
    return f"{SOURCE}:{REPOSITORY_URL}@{revision}"


def parse_identity(release: dict) -> tuple[str, str]:
    """The state revision and the input-data revision a release identity names.

    Raises ``unknown_reference`` unless the identity holds exactly one reference per
    determined kind, each with a value of the form ``git:<repository URL>@<full commit
    hash>``, ``code_state`` and ``parameter_set`` with the same value, and one
    ``engine_version`` that names this engine.
    """
    return _identity(release, strict=True)


def recorded_identity(release: dict) -> tuple[str, str]:
    """The state revision and the input-data revision of a recorded identity, of any engine version.

    As :func:`parse_identity`, but the ``engine_version`` reference may name another engine
    than this one. A regression run reads the identity of a recorded run in this way; a
    run and a replay resolve it with :func:`parse_identity`.
    """
    return _identity(release, strict=False)


def _identity(release: dict, strict: bool) -> tuple[str, str]:
    references = release["references"]
    if any("artifact" in reference for reference in references):
        raise Rejection("unknown_reference", "A reference of the release identity names an artifact; "
                        "the engine resolves references without an artifact only.")
    kinds = sorted(reference["kind"] for reference in references)
    if kinds != sorted(DETERMINED_KINDS | {"engine_version"}):
        raise Rejection("unknown_reference", "The release identity holds exactly one reference of each "
                        f"kind {', '.join(sorted(DETERMINED_KINDS))}, and engine_version; it holds "
                        f"{', '.join(kinds)}.")
    values = {reference["kind"]: reference["value"] for reference in references}
    if strict and values["engine_version"] != engine_version():
        raise Rejection("unknown_reference", f"The release identity names the engine version "
                        f"{values['engine_version']!r}; this engine is {engine_version()!r}.")
    if values["code_state"] != values["parameter_set"]:
        raise Rejection("unknown_reference", "The references of the kinds code_state and parameter_set "
                        "name more than one revision.")
    return _named_revision(values["code_state"]), _named_revision(values["input_data"])


def _named_revision(value: str) -> str:
    """The commit hash a reference value names."""
    match = REVISION_VALUE.fullmatch(value)
    if not match:
        raise Rejection("unknown_reference", "A release is named by a value of the form "
                        "git:<repository URL>@<full commit hash>, the hash as 40 lowercase hexadecimal digits.")
    if match["repository"] != REPOSITORY_URL:
        raise Rejection("unknown_reference", f"The engine knows no repository {match['repository']}; "
                        f"it knows {REPOSITORY_URL}.")
    return match["revision"]


def state_revision(release: dict) -> str:
    """The state revision of a release identity: the one ``code_state`` and ``parameter_set`` name.

    No other reference is read: neither the input data nor the engine version, so the
    identity of a run of another engine version is read as well. Raises
    ``unknown_reference`` unless the identity holds exactly one reference of each of the
    two kinds, without an artifact, and both name one commit.
    """
    named = [reference for reference in release["references"] if reference["kind"] in STATE_KINDS]
    if sorted(reference["kind"] for reference in named) != sorted(STATE_KINDS):
        raise Rejection("unknown_reference", "The release identity holds exactly one reference of each "
                        f"kind {' and '.join(sorted(STATE_KINDS))}; it holds "
                        f"{', '.join(sorted(r['kind'] for r in named)) or 'none'}.")
    if any("artifact" in reference for reference in named):
        raise Rejection("unknown_reference", "A reference of the release identity names an artifact; "
                        "the engine resolves references without an artifact only.")
    if named[0]["value"] != named[1]["value"]:
        raise Rejection("unknown_reference", "The references of the kinds code_state and parameter_set "
                        "name more than one revision.")
    return _named_revision(named[0]["value"])


# --- the clone ------------------------------------------------------------------------


def _git(clone: Path, *arguments: str, stdin: bytes | None = None) -> subprocess.CompletedProcess:
    """Run a Git command that reads the clone. It takes no lock and fetches nothing.

    Replace references are ignored: a hash names the object with that hash and no other.
    """
    environment = {name: value for name, value in os.environ.items()
                   if name not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE", "GIT_OBJECT_DIRECTORY")}
    # A folder that is no repository must not resolve to a repository above it.
    environment.update(GIT_OPTIONAL_LOCKS="0", GIT_NO_LAZY_FETCH="1", GIT_TERMINAL_PROMPT="0",
                       GIT_NO_REPLACE_OBJECTS="1",
                       GIT_CEILING_DIRECTORIES=str(clone.parent))
    try:
        return subprocess.run(["git", "--no-optional-locks", "-C", str(clone), *arguments], input=stdin,
                              capture_output=True, env=environment)
    except FileNotFoundError:
        raise UsageError("git is not installed or not on the PATH; the reference model is read "
                         "from a Git clone") from None


def find_clone(repositories: Path) -> Path:
    """The local clone of the reference model repository below ``repositories``."""
    clone = Path(repositories).resolve() / CLONE_NAME
    # Git is started before the folder decides: without Git the command does not start.
    is_repository = _git(clone, "rev-parse", "--git-dir").returncode == 0
    if not clone.is_dir() or not is_repository:
        raise Rejection("unknown_reference", f"There is no clone of {REPOSITORY_URL} at {clone}. "
                        f"Create it with: git clone {REPOSITORY_URL} {clone}")
    return clone


def resolve_revision(name: str, repositories: Path) -> str:
    """The full hash of the commit that ``name`` names in the clone: a hash, a branch, ``HEAD``."""
    clone = find_clone(repositories)
    done = _git(clone, "rev-parse", "--verify", "--quiet", "--end-of-options", f"{name}^{{commit}}")
    revision = done.stdout.decode("ascii", "replace").strip()
    if done.returncode != 0 or not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise Rejection("unknown_reference", f"The clone at {clone} holds no commit named {name!r}.")
    return revision


def release_references(revision: str, input_revision: str | None = None) -> list[dict]:
    """The complete release identity of the commit ``revision``, a full hash.

    ``input_revision`` names another commit that the input data is taken from; without it
    the input data is that of ``revision``.
    """
    value = reference_value(revision)
    return [{"kind": "code_state", "value": value}, {"kind": "parameter_set", "value": value},
            {"kind": "input_data", "value": reference_value(input_revision or revision)},
            {"kind": "engine_version", "value": engine_version()}]


def read_tree(clone: Path, revision: str) -> dict[str, str]:
    """Path and blob id of every file of the commit ``revision``.

    Raises ``unknown_reference`` when the clone holds no commit with this hash, or when
    the commit holds an entry that is not a regular file.
    """
    kind = _git(clone, "cat-file", "-t", revision)
    if kind.returncode != 0:
        raise Rejection("unknown_reference", f"The clone at {clone} holds no object {revision}.")
    if kind.stdout.strip() != b"commit":
        raise Rejection("unknown_reference", f"The object {revision} is a {kind.stdout.decode().strip()}, "
                        "not a commit.")
    listing = _git(clone, "ls-tree", "-r", "-z", "--full-tree", revision)
    if listing.returncode != 0:
        raise Rejection("unknown_reference", f"The tree of the commit {revision} cannot be read from {clone}.")
    files = {}
    for entry in listing.stdout.split(b"\0")[:-1]:
        meta, raw_path = entry.split(b"\t", 1)
        mode, object_type, blob = meta.decode("ascii").split()
        try:
            path = raw_path.decode("utf-8")
        except UnicodeDecodeError:
            raise Rejection("unknown_reference", f"The commit {revision} holds a path that is not "
                            "UTF-8.") from None
        parts = path.split("/")
        if (object_type != "blob" or mode not in ("100644", "100755") or "\\" in path
                or any(part in ("", ".", "..", ".git") for part in parts)):
            raise Rejection("unknown_reference", f"The commit {revision} holds {path}, which is not a "
                            "regular file; the engine restores regular files only.")
        files[path] = blob
    return files


MODEL_POINT_PATH = f"{PRODUCT_FOLDER}/{MODEL_POINT_FILE}"


# --- the history ----------------------------------------------------------------------


def path_class(path: str) -> str | None:
    """The class of a path of the repository: ``data``, ``parameter``, ``code``, or none."""
    if path == MODEL_POINT_PATH:
        return "data"
    if path.startswith(f"{PRODUCT_FOLDER}/{MODEL_NAME}/"):
        return "code"
    folder, _, name = path.rpartition("/")
    if folder == PRODUCT_FOLDER and name.endswith(".csv"):
        return "parameter"
    return None


def _require_commit(clone: Path, revision: str) -> None:
    kind = _git(clone, "cat-file", "-t", revision)
    if kind.returncode != 0:
        raise Rejection("unknown_reference", f"The clone at {clone} holds no object {revision}.")
    if kind.stdout.strip() != b"commit":
        raise Rejection("unknown_reference", f"The object {revision} is a {kind.stdout.decode().strip()}, "
                        "not a commit.")


def _refuse_cut_off_history(clone: Path) -> None:
    """A shallow clone lacks parents, so its main line would end early and look unrelated."""
    shallow = _git(clone, "rev-parse", "--is-shallow-repository")
    if shallow.returncode != 0:
        raise Rejection("unknown_reference", f"The clone at {clone} cannot be read.")
    if shallow.stdout.strip() != b"false":
        raise UsageError(f"the history of the clone at {clone} is cut off (a shallow clone); the history "
                         "between two revisions is read from a complete clone. Complete it with: "
                         f"git -C {clone} fetch --unshallow")


def main_line(clone: Path, revision: str) -> list[str]:
    """The first-parent chain of a commit, the commit itself first."""
    listing = _git(clone, "rev-list", "--first-parent", "--end-of-options", revision)
    hashes = listing.stdout.decode("ascii", "replace").split()
    if listing.returncode != 0 or hashes[:1] != [revision]:
        raise Rejection("unknown_reference", f"The history of the commit {revision} cannot be read from {clone}.")
    return hashes


def touched_paths(clone: Path, parent: str, revision: str) -> list[str]:
    """The paths that differ between a commit and its first parent, sorted.

    Renames are not detected: a moved file is listed with its old and its new path.
    """
    listing = _git(clone, "diff-tree", "-r", "-z", "--name-only", "--no-renames", "--ignore-submodules=none",
                   "--end-of-options", parent, revision)
    if listing.returncode != 0:
        raise Rejection("unknown_reference", f"The difference of the commit {revision} to its first parent "
                        f"cannot be read from {clone}.")
    return sorted(raw.decode("utf-8", "replace") for raw in listing.stdout.split(b"\0") if raw)


def log_messages(clone: Path, revisions: list[str]) -> list[str]:
    """The log message of each commit, read from the commit object.

    The message is everything after the first empty line of the object. Bytes that are not
    UTF-8 become U+FFFD; no setting of the user re-encodes or reformats the text.
    """
    if not revisions:
        return []
    done = _git(clone, "cat-file", "--batch", stdin="".join(f"{revision}\n" for revision in revisions).encode("ascii"))
    if done.returncode != 0:
        raise Rejection("unknown_reference", f"The commits of the history cannot be read from {clone}.")
    data, position, messages = done.stdout, 0, []
    for revision in revisions:
        line_end = data.find(b"\n", position)
        header = data[position:line_end].split() if line_end >= 0 else []
        if len(header) != 3 or header[1] != b"commit":
            raise Rejection("unknown_reference", f"The clone at {clone} does not hold the commit {revision}.")
        size = int(header[2])
        content = data[line_end + 1:line_end + 1 + size]
        position = line_end + 1 + size + 1  # a line feed follows the content
        _, separator, message = content.partition(b"\n\n")
        messages.append(message.decode("utf-8", "replace") if separator else "")
    return messages


def missing_release_files(files, input_files=None) -> list[str]:
    """The input files a release must hold and lacks.

    The parameter tables are looked for in ``files``, the tree of the state commit, and the
    model point table in ``input_files``, the tree of the input-data commit, or in
    ``files`` when both are one commit.
    """
    points = [] if MODEL_POINT_PATH in (files if input_files is None else input_files) else [MODEL_POINT_PATH]
    return points + [name for name in (f"{PRODUCT_FOLDER}/{table}.csv" for table in sorted(PARAMETER_TABLES))
                     if name not in files]


def export_tree(clone: Path, files: dict[str, str], target: Path) -> None:
    """Write the files of a tree into the new folder ``target``, byte for byte.

    The blobs are read from the object store. Neither the working tree nor an archive is
    used, so no line-ending setting and no export attribute of the clone alters a byte.
    """
    paths = sorted(files)
    target = target.resolve()
    for path in paths:  # on Windows a path such as ``D:/x`` leaves the folder it is joined to
        if target not in target.joinpath(*path.split("/")).resolve().parents:
            raise Rejection("unknown_reference", f"The revision holds {path}, which is not a path "
                            "inside the restored state.")
    done = _git(clone, "cat-file", "--batch", stdin="".join(f"{files[path]}\n" for path in paths).encode("ascii"))
    if done.returncode != 0:
        raise Rejection("unknown_reference", f"The files of the revision cannot be read from {clone}.")
    data, position = done.stdout, 0
    for path in paths:
        line_end = data.index(b"\n", position)
        header = data[position:line_end].split()
        if len(header) != 3 or header[1] != b"blob":
            raise Rejection("unknown_reference", f"The clone at {clone} does not hold the file {path} "
                            "of the revision.")
        size = int(header[2])
        content = data[line_end + 1:line_end + 1 + size]
        position = line_end + 1 + size + 1  # a line feed follows the content
        file = target.joinpath(*path.split("/"))
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content)


def _plain(value):
    """A numpy or pandas scalar as a plain JSON value."""
    if isinstance(value, (bool, np.bool_)):
        return bool(value)
    if isinstance(value, (int, np.integer)):
        return int(value)
    if isinstance(value, (float, np.floating)):
        return float(value)
    if isinstance(value, str):
        return str(value)
    raise TypeError(f"not a scalar parameter value: {value!r}")


class FormulaError(Exception):
    """A formula of the model raised while the state is read: the cause and the formula, on one line.

    It stands for a modelx ``FormulaError``, whose message spans many lines and ends with
    the source code of the formula; the run writes the last line of a message.
    """


def formula_error(error: Exception) -> FormulaError | None:
    """The one-line form of a modelx ``FormulaError``: ``<cause line> in <formula>``.

    The cause is the line after the first one; the formula is that of the last entry of
    the formula traceback, the innermost one, which raised. ``None`` when the message has
    not this form.
    """
    lines = str(error).splitlines()
    try:
        cause = lines[1].strip()
        start = lines.index("Formula traceback:") + 1
    except (IndexError, ValueError):
        return None
    entries = []
    for line in lines[start:]:
        if not line.strip():
            break
        entries.append(line.strip())
    match = re.fullmatch(r"\d+: (?P<formula>.+), line \d+", entries[-1]) if entries else None
    if not cause or match is None:
        return None
    return FormulaError(f"{cause} in {match['formula']}")


@contextmanager
def _readable_formula_errors():
    """Re-raise a modelx ``FormulaError`` as a :class:`FormulaError` with a one-line message."""
    try:
        yield
    except mx_errors.FormulaError as error:
        readable = formula_error(error)
        if readable is None:
            raise
        raise readable from error


def _is_scalar(value) -> bool:
    return isinstance(value, (bool, int, float, str, np.bool_, np.integer, np.floating))


class ReferenceModelSession:
    time_basis = TIME_BASIS
    quantities = [(name, unit) for name, unit, _ in QUANTITIES]

    def __init__(self, model):
        self._model = model
        self._table = None

    def _points(self):
        if self._table is None:
            self._table = self._model.Data.model_point_table()
        return self._table

    def model_point_ids(self) -> list[str]:
        with _readable_formula_errors():
            return [str(value) for value in self._points()[MODEL_POINT_ID_COLUMN]]

    def project(self, model_point_id: str) -> list[tuple[int, list[float]]]:
        table = self._points()
        matches = table.index[table[MODEL_POINT_ID_COLUMN].astype(str) == model_point_id]
        if len(matches) != 1:
            raise ModelPointFailure(f"The model point table holds {len(matches)} rows with this id.")
        try:
            projection = self._model.Projection[int(matches[0])]
            frame = projection.result_cf()
        except Exception as exc:  # a modelx FormulaError wraps the cause
            reason = str(exc).strip().splitlines()
            raise ModelPointFailure(f"result_cf raised {type(exc).__name__}"
                                    + (f": {reason[-1]}" if reason else "")) from None
        problems = []
        for check in CHECKS:
            try:
                if not bool(getattr(projection, check)()):
                    problems.append(f"{check} is false")
            except Exception as exc:
                problems.append(f"{check} raised {type(exc).__name__}")
        if problems:
            raise ModelPointFailure("; ".join(problems))
        try:
            columns = [[float(value) for value in frame[column]] for _, _, column in QUANTITIES]
            periods = [int(period) for period in frame.index]
        except Exception as exc:
            raise ModelPointFailure(f"result_cf has not the expected form: {type(exc).__name__}") from None
        return [(period, [column[row] for column in columns]) for row, period in enumerate(periods)]

    def parameters(self) -> list[dict]:
        with _readable_formula_errors():
            return self._parameters()

    def _parameters(self) -> list[dict]:
        inventory: dict[str, dict] = {}

        def add(parameter: dict) -> None:
            if parameter["name"] in inventory:
                raise RuntimeError(f"two parameters of the model have the name {parameter['name']}")
            inventory[parameter["name"]] = parameter

        for space in (self._model.Projection, self._model.Data):
            for name, value in space.refs.items():
                if not name.startswith("_") and name not in NOT_A_PARAMETER and _is_scalar(value):
                    add({"name": name, "type": "scalar", "value": _plain(value)})
        for name in PARAMETER_TABLES:
            frame = getattr(self._model.Data, name)()
            value_columns = [str(c) for c in frame.columns if c not in NOT_A_VALUE_COLUMN]
            rows = []
            for key, values in zip(frame.index, frame[value_columns].itertuples(index=False, name=None)):
                key = list(key) if isinstance(key, tuple) else [key]
                rows.append({"key": [_plain(k) for k in key], "values": [_plain(v) for v in values]})
            add({"name": name, "type": "keyed_table",
                 "key_columns": [str(c) for c in frame.index.names],
                 "value_columns": value_columns, "rows": rows})
        return [inventory[name] for name in sorted(inventory)]


class ReferenceModel:
    """The engine of the stage ``liability_cashflow``: modelx with the model ``RLV_DE_S``."""

    stages = frozenset({STAGE})
    realisations = frozenset({changes_contract.TEXT_PATCH, changes_contract.REVISION})
    determines = DETERMINED_KINDS
    holdable = {"input_data": frozenset({"data"})}  # the model point table, the class ``data``

    def _locate(self, release: dict, repositories: Path) -> tuple[Path, dict[str, str]]:
        """The clone and the files of the release state: path and blob id.

        The files are those of the state commit, with the model point table of the
        input-data commit in place of its own.
        """
        revision, input_revision = parse_identity(release)
        clone = find_clone(repositories)
        return clone, self._files(clone, revision, input_revision)

    @staticmethod
    def _files(clone: Path, revision: str, input_revision: str) -> dict[str, str]:
        files = read_tree(clone, revision)
        input_files = files if input_revision == revision else read_tree(clone, input_revision)
        if not any(path.startswith(f"{PRODUCT_FOLDER}/{MODEL_NAME}/") for path in files):
            raise Rejection("unknown_reference", f"The commit {revision} holds no model "
                            f"{PRODUCT_FOLDER}/{MODEL_NAME}.")
        missing = missing_release_files(files, input_files)
        if missing[:1] == [MODEL_POINT_PATH]:
            raise Rejection("unknown_reference", f"The commit {input_revision} lacks the release file "
                            f"{MODEL_POINT_PATH}.")
        if missing:
            raise Rejection("unknown_reference", f"The commit {revision} lacks the release file "
                            f"{', '.join(missing)}.")
        return {**files, MODEL_POINT_PATH: input_files[MODEL_POINT_PATH]}

    def state_release(self, base: dict, revision: str | None, hold, repositories: Path) -> dict:
        """The identity of the state after ``revision`` on the present engine, with the label of ``base``."""
        state, input_revision = recorded_identity(base)
        if revision is not None:
            state, input_revision = revision, (input_revision if "input_data" in hold else revision)
        return {"label": base["label"], "references": release_references(state, input_revision)}

    def resolve(self, release: dict, repositories: Path) -> None:
        self._locate(release, repositories)

    def history(self, older: dict, newer: dict, repositories: Path) -> History:
        """The first-parent history from the state commit of ``older`` to that of ``newer``."""
        old, new = state_revision(older), state_revision(newer)
        clone = find_clone(repositories)
        _refuse_cut_off_history(clone)
        for revision in (old, new):
            _require_commit(clone, revision)
        line = main_line(clone, new)
        if old not in line:
            raise Rejection("unrelated_revisions", f"The revision {old} does not lie on the main line of "
                            f"{new}: it is not reached from it by first parents. Name the older "
                            "result first; a revision inside a merged branch is no point of the main line.")
        between = line[:line.index(old)][::-1]  # after the older commit, oldest first
        messages = log_messages(clone, between)
        revisions = []
        for parent, revision, message in zip([old] + between, between, messages):
            classes = {path_class(path) for path in touched_paths(clone, parent, revision)} - {None}
            revisions.append(Revision(revision, message, frozenset(classes)))
        return History(SOURCE, old, new, tuple(revisions))

    @contextmanager
    def open(self, release: dict, enabled: list[dict], manifest_dir: Path | None, repositories: Path,
             hold=frozenset()):
        clone, files = self._locate(release, repositories)
        revisions = [c["realisation"]["revision"] for c in enabled
                     if c["realisation"]["type"] == changes_contract.REVISION]
        patches = [c for c in enabled if c["realisation"]["type"] != changes_contract.REVISION]
        if revisions:  # the state after the last enabled revision; the request's state is the base
            _, input_revision = parse_identity(release)
            last = revisions[-1]
            try:
                files = self._files(clone, last, input_revision if "input_data" in hold else last)
            except Rejection as rejection:  # the request is accepted; the state cannot be restored
                raise RuntimeError(rejection.message) from None
        with tempfile.TemporaryDirectory(prefix=SCRATCH_PREFIX) as scratch:
            state = Path(scratch) / CLONE_NAME
            state.mkdir()
            # The model point table of the input-data commit lies over the restored tree.
            export_tree(clone, files, state)
            if patches:
                changes_contract.apply_changes(state, patches, manifest_dir)
            with _readable_formula_errors():
                model = mx.read_model(state / PRODUCT_FOLDER / MODEL_NAME)
            try:
                yield ReferenceModelSession(model)
            finally:
                model.close()
