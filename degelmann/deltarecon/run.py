"""The run procedure of ``contracts/v3/run.md``.

A run reads a run request and writes, beside it, the response, the per-model-point
export, and the run record. The calculation sits behind the :class:`Engine` protocol; this
module knows no engine. An engine restores the release state a request names and applies
the enabled changes to it; this module copies no release and applies no change.

Order of the request checks: JSON profile, contract version, schema, stage, release
references, manifest and patch artifacts, manifest rules, combination rules, the held kinds
of ``changes.hold``, parameter inventory, selection.

An exception that an engine call raises while the engine resolves the release, restores
it, or reads the model points, the parameters, the quantities, or the time basis ends the
run with the outcome ``error`` and the diagnostic ``state_not_readable``; a
:class:`~degelmann.deltarecon.documents.Rejection` and a :class:`UsageError` keep their meaning. A
state without a model point gives ``no_model_point``, an id the schema forbids
``invalid_model_point_id``. A :class:`ModelPointFailure` of ``project`` still fails the
model point, and an error of the core still stops the procedure.
"""
from __future__ import annotations

import json
import math
import re
import tempfile
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import ContextManager, Mapping, Protocol

from . import changes as changes_contract
from .documents import (CHANGES_SCHEMA, CONTRACT_VERSION, RECORD_SCHEMA, RUN_REQUEST, RUN_SCHEMA,
                        Rejection, artifact_reference, check_artifact, check_schema, check_version,
                        new_record_id, parse_document, read_document, schema_errors, validator,
                        write_document)
from .export import write_export

RESPONSE_NAME = "response.json"
EXPORT_NAME = "results.csv"
RECORD_NAME = "run-record.json"
# The folder that holds what an engine restores a release from, below the working directory.
REPOSITORIES_FOLDER = "repositories"
# An engine restores a release into a folder of the system's temporary folder whose name
# starts with this prefix. A message of the outcome ``error`` names it ``<scratch>``.
SCRATCH_PREFIX = "deltarecon-"

# The quantities of each stage, in the order of its domain reference.
STAGE_QUANTITIES = {
    "liability_cashflow": [
        "Anzahl Verträge", "Bruttobeitrag", "Zahlbeitrag", "Beitragsverrechnung",
        "garantierte Todesfallleistung", "garantierter Rückkaufswert",
        "garantierte Erlebensfallleistung", "kalkulatorische Kosten",
        "Kosten 2. Ordnung ohne Provisionen", "Provisionen", "Netto-Cashflow",
    ],
}


class UsageError(Exception):
    """The procedure cannot start: a file is missing or an output exists already."""


class ModelPointFailure(Exception):
    """The engine could not calculate one model point."""


class Session(Protocol):
    """One release state, opened for a run."""

    time_basis: str
    quantities: list[tuple[str, str]]  # name and unit, in export column order

    def model_point_ids(self) -> list[str]:
        """The public id of every model point of the release state, repeats included."""

    def project(self, model_point_id: str) -> list[tuple[int, list[float]]]:
        """The periods of one model point with one value per quantity.

        Raises :class:`ModelPointFailure` when the model point cannot be calculated.
        """

    def parameters(self) -> list[dict]:
        """The parameter inventory of the release state, in the form of the run record.

        The order of the parameters and of the rows of a keyed table carries no meaning.
        """


@dataclass(frozen=True)
class Revision:
    """One revision on the main line of a history, as an engine reports it."""

    id: str                 # the full identifier of the revision
    message: str            # its log message as written; it may be empty
    classes: frozenset[str]  # the classes of the paths it touches: data, parameter, code


@dataclass(frozen=True)
class History:
    """The history between two release identities."""

    source: str                # the kind of history, for example ``git``
    older: str                 # the identifier of the older revision
    newer: str                 # the identifier of the newer revision
    revisions: tuple[Revision, ...]  # the main line after ``older`` up to ``newer``, oldest first


class Engine(Protocol):
    """A calculation engine behind the run contract."""

    stages: frozenset[str]
    realisations: frozenset[str]  # the realisation types of a change the engine can apply
    determines: frozenset[str]    # the kinds of release reference one revision fixes
    # The kinds the engine can hold at the release of a request while revisions are enabled,
    # each with the classes of the paths that carry it, for example ``input_data``: ``data``.
    holdable: Mapping[str, frozenset[str]]

    def resolve(self, release: dict, repositories: Path) -> None:
        """Check that the release identity names a state the engine can restore.

        ``repositories`` is the folder that holds what the engine restores a release from,
        for example local clones. Nothing is restored and nothing is written.

        Raises a :class:`Rejection` with ``unknown_reference`` when the references cannot
        be resolved.
        """

    def open(self, release: dict, enabled: list[dict], manifest_dir: Path | None,
             repositories: Path, hold: frozenset[str] = frozenset()) -> ContextManager[Session]:
        """Restore the release state, apply the enabled changes, and open it for reading.

        ``enabled`` holds the enabled changes in application order; every one has a
        realisation type the engine declares. ``manifest_dir`` is the folder of the change
        manifest, which the paths of its artifacts are relative to; it is ``None`` when no
        change is enabled. What ``repositories`` holds is never altered. A scratch folder
        is created in the system's temporary folder with a name that starts with
        :data:`SCRATCH_PREFIX`.

        For changes of the type ``revision`` the engine restores the state after the last
        enabled revision. ``hold`` names the kinds of release reference it then takes from
        ``release`` instead of from that revision; each is a kind of ``holdable``.

        Raises a :class:`Rejection` with ``invalid_manifest`` when a change does not apply.
        Any other exception, here or from a call of the session other than ``project``,
        ends the run with the outcome ``error``.
        """

    def history(self, older: dict, newer: dict, repositories: Path) -> History:
        """The history between the revisions two release identities name.

        Which references of an identity name its revision is the engine's matter; it reads
        no reference that a revision does not fix and does not check its own version. The
        result lists every revision on the main line after the older one, up to and
        including the newer one, each with its log message and the classes of the paths it
        touches against the revision before it. It is empty when both identities name one
        revision. Nothing is restored and nothing is written.

        The message is the text of the revision as it was written, decoded by the engine:
        bytes that are not UTF-8 become U+FFFD. The line breaks at its end stay; the caller
        removes them and puts the identifier in the place of an empty message.

        Raises a :class:`Rejection` with ``unknown_reference`` when an identity names no
        revision the engine can read, and with ``unrelated_revisions`` when the older
        revision does not lie on the main line of the newer one. Raises a
        :class:`UsageError` when the history at hand is cut off.
        """

    def state_release(self, base: dict, revision: str | None, hold: frozenset[str],
                      repositories: Path) -> dict:
        """The release identity of the state after ``revision``, as this engine would record it.

        ``base`` is a recorded release identity, of any engine version. The result has the
        label of ``base``, names the present engine, on the computation path ``base`` names
        when the engine has several, and names the state after ``revision``
        with the kinds in ``hold`` taken from ``base``; for ``revision`` ``None`` it names
        the state of ``base`` itself. Nothing is restored and nothing is written.

        Raises a :class:`Rejection` with ``unknown_reference`` when ``base`` names no state
        the engine can read.
        """


@dataclass
class RunResult:
    outcome: str
    response: dict
    response_path: Path
    record_path: Path | None = None
    export_path: Path | None = None
    record: dict | None = field(default=None, repr=False)


def quantity_errors(stage: str, names: list[str]) -> str | None:
    """Rule 7: declared names are domain names, unique, and in domain order."""
    domain = STAGE_QUANTITIES[stage]
    if not names:
        return "no quantity is declared"
    if len(set(names)) != len(names):
        return "a quantity name is declared twice"
    unknown = [name for name in names if name not in domain]
    if unknown:
        return f"the domain reference defines no quantity {unknown[0]!r}"
    if names != [name for name in domain if name in names]:
        return "the quantity names stand in another order than the domain reference"
    return None


def load_change_set(request: dict, manifest_path: Path, realisations) -> list[dict]:
    """Check the change set of a request against its manifest. Return the enabled changes.

    Order: the manifest as a document, the artifacts of the enabled changes, the
    manifest rules, the combination rules. The caller has checked the manifest artifact.
    ``realisations`` are the types the engine declares; they are passed on uncut.
    """
    manifest = read_document(manifest_path, CHANGES_SCHEMA)
    enabled = set(request["changes"]["enabled"])
    for change in manifest["changes"]:
        if change["id"] not in enabled:
            continue
        for artifact in changes_contract.artifacts(change["realisation"]):
            try:
                check_artifact(manifest_path.parent, artifact)
            except Rejection as rejection:
                rejection.change_ids = [change["id"]]
                raise
    changes_contract.check_manifest_rules(manifest)
    return changes_contract.check_combination(manifest, request, frozenset(realisations))


def select(request: dict, available: list[str]) -> list[str]:
    """Rule 5: the selected model point ids, in writer order."""
    selection = request["selection"]
    if selection["mode"] == "full":
        return sorted(set(available))
    unknown = sorted(set(selection["model_point_ids"]) - set(available))
    if unknown:
        raise Rejection("unknown_model_point", "The release holds no model point with this id.",
                        model_point_ids=unknown)
    return sorted(selection["model_point_ids"])


def check_parameters(parameters: list[dict]) -> None:
    """Reject a release state whose parameter inventory holds a non-finite number."""
    def finite(value) -> bool:
        if isinstance(value, (bool, str)):
            return True
        try:  # an integer too large for binary64 cannot be read back from the record
            return math.isfinite(float(value))
        except OverflowError:
            return False

    for parameter in parameters:
        if parameter["type"] == "scalar":
            values = [parameter["value"]]
        else:
            values = [value for row in parameter["rows"] for value in row["key"] + row["values"]]
        if not all(finite(value) for value in values):
            raise Rejection("non_finite_value", f"The parameter {parameter['name']} of the release "
                            "state holds a value that is not a finite number.")


def _key_order(key: list):
    # Numbers numerically, strings by code point; a column holds one of the two.
    return [(0, element, "") if not isinstance(element, str) else (1, 0, element) for element in key]


def _typed_key(key: list) -> tuple:
    # Equality as the parameter model states it: numbers as binary64 values, and a
    # number, a string, and a boolean are never equal.
    def typed(element):
        if isinstance(element, (bool, str)):
            return (type(element).__name__, element)
        try:
            return ("number", float(element))
        except OverflowError:
            return ("number", element)
    return tuple(typed(element) for element in key)


class _EngineError(Exception):
    """An exception an engine call raised. The run ends with the outcome ``error``."""

    def __init__(self, error: Exception):
        super().__init__(f"{type(error).__name__}: {error}")
        self.error = error


class _StateError(Exception):
    """The restored state cannot be run: the outcome ``error`` with a diagnostic of its own."""

    def __init__(self, code: str, message: str):
        super().__init__(f"{code}: {message}")
        self.rejection = Rejection(code, message)


def _engine(call, *arguments):
    """Call the engine. A rejection and a usage error pass; any other exception is an engine error."""
    try:
        return call(*arguments)
    except (Rejection, UsageError):
        raise
    except Exception as error:
        raise _EngineError(error) from error


@contextmanager
def _opened(engine: Engine, release: dict, enabled: list[dict], manifest_dir: Path | None,
            repositories: Path, hold: frozenset[str] = frozenset()):
    """``engine.open`` with every exception of entering or leaving it as an engine error.

    An exception of the body wins over one that leaving raises while the body unwinds.
    """
    context = _engine(engine.open, release, enabled, manifest_dir, repositories, hold)
    session = _engine(context.__enter__)
    try:
        yield session
    except BaseException as inside:
        try:
            context.__exit__(type(inside), inside, inside.__traceback__)
        except BaseException:  # noqa: BLE001  (the exception of the body is raised below)
            pass
        raise
    else:
        _engine(context.__exit__, None, None, None)


def error_message(error: BaseException, repositories: Path) -> str:
    """``<kind>: <last line>`` of an exception, with the scratch and repositories folders as placeholders.

    The message names no folder of one machine, so a repeated run writes the same text.
    Only absolute forms of the two folders are replaced.
    """
    lines = str(error).strip().splitlines()
    text = type(error).__name__ + (f": {lines[-1].strip()}" if lines else "")
    temporary = {tempfile.gettempdir(), str(Path(tempfile.gettempdir()).resolve())}
    for folder in sorted(temporary, key=len, reverse=True):
        scratch = re.escape(folder.rstrip("/\\")) + r"[/\\]" + re.escape(SCRATCH_PREFIX) + r"[^/\\\s'\"]*"
        text = re.sub(scratch, "<scratch>", text)
    places = {str(Path(repositories).resolve()), str(Path(repositories).absolute())}
    for folder in sorted(places, key=len, reverse=True):
        text = text.replace(folder.rstrip("/\\"), "<repositories>")
    return text


def _check_model_point_ids(ids: list) -> None:
    """Every id the state yields is a string that the schema of an id allows."""
    id_schema = validator("common.schema.json#/$defs/id")
    for model_point_id in ids:
        if not isinstance(model_point_id, str) or not id_schema.is_valid(model_point_id):
            shown = json.dumps(model_point_id, ensure_ascii=False, default=str)
            raise _StateError("invalid_model_point_id", f"The release state yields the model point id "
                              f"{shown}, which the schema of an id forbids: an id is a non-empty string "
                              "without a control character.")


def read_inventory(session: Session) -> list[dict]:
    """The parameter inventory of a release state, as the run record holds it.

    The inventory an engine returns is checked against the schema of the record before
    anything is written, and brought into one order for every engine: parameters by name,
    the rows of a keyed table by key.
    """
    inventory = _engine(lambda: list(session.parameters()))
    errors = schema_errors(inventory, "common.schema.json#/$defs/parameter_inventory")
    names = [parameter["name"] for parameter in inventory] if not errors else []
    if not errors and len(set(names)) != len(names):
        errors = ["two parameters have the same name"]
    for parameter in inventory if not errors else []:
        rows = parameter.get("rows", [])
        if any(len(row["key"]) != len(parameter["key_columns"])
               or len(row["values"]) != len(parameter["value_columns"]) for row in rows):
            errors = [f"{parameter['name']}: a row does not hold one element per column"]
        elif len({_typed_key(row["key"]) for row in rows}) != len(rows):
            errors = [f"{parameter['name']}: two rows have the same key"]
    if errors:
        raise RuntimeError(f"the engine returns a parameter inventory the record does not allow: {errors[0]}")
    check_parameters(inventory)
    ordered = [{**parameter, "rows": sorted(parameter["rows"], key=lambda row: _key_order(row["key"]))}
               if parameter["type"] == "keyed_table" else parameter for parameter in inventory]
    return sorted(ordered, key=lambda parameter: parameter["name"])


def calculate(session: Session, stage: str, selected: list[str], available: list[str],
              names: list[str] | None = None):
    """Project the selection. Return the export rows, the period ranges, and the failures.

    ``names`` are the quantity names the session declares; without them they are read.
    """
    if names is None:
        names = [name for name, _ in _engine(lambda: list(session.quantities))]
    problem = quantity_errors(stage, names)
    if problem:
        raise RuntimeError(f"the engine declares quantities the stage does not allow: {problem}")
    rows, ranges, failures = [], [], []
    for model_point_id in selected:
        try:
            if available.count(model_point_id) > 1:
                raise ModelPointFailure("The release holds this model point id more than once.")
            periods = session.project(model_point_id)
            if not periods:
                raise ModelPointFailure("The model point has no period.")
            first = periods[0][0]
            for offset, (period, values) in enumerate(periods):
                if period != first + offset:
                    raise ModelPointFailure("The periods of the model point are not contiguous.")
                if len(values) != len(names):
                    raise ModelPointFailure("A period does not hold one value per quantity.")
                for name, value in zip(names, values):
                    if not math.isfinite(value):
                        raise ModelPointFailure(f"The value of {name} in period {period} is not finite.")
        except ModelPointFailure as failure:
            failures.append({"model_point_id": model_point_id,
                             "message": str(failure) or "The model point could not be calculated."})
            continue
        rows.extend((model_point_id, period, values) for period, values in periods)
        ranges.append({"model_point_id": model_point_id, "first_period": first,
                       "last_period": first + len(periods) - 1})
    return rows, ranges, failures


def _repeatable(document: dict, member: str, definition: str) -> bool:
    return member in document and not list(
        validator(f"common.schema.json#/$defs/{definition}").iter_errors(document[member]))


def rejected_response(document, rejection: Rejection) -> dict:
    """A rejected response. Stage and run id are repeated where they can be read."""
    response = {"document": "run_response", "contract_version": CONTRACT_VERSION}
    if isinstance(document, dict):
        if _repeatable(document, "stage", "stage"):
            response["stage"] = document["stage"]
        if _repeatable(document, "run_id", "id"):
            response["run_id"] = document["run_id"]
    response["outcome"] = "rejected"
    response["diagnostics"] = [rejection.diagnostic()]
    return response


def recorded_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def run_record(stage: str, procedure: str, outcome: str, inputs: list[dict], releases: list[dict],
               parameters: list[dict], outputs: list[dict]) -> dict:
    """The run record of one execution of ``procedure``, with a new record id and the present time."""
    return {
        "document": "run_record", "contract_version": CONTRACT_VERSION, "stage": stage,
        "record_id": new_record_id(), "procedure": {"type": procedure},
        "outcome": outcome, "recorded_at": recorded_now(), "inputs": inputs,
        "releases": releases, "parameters": parameters, "outputs": outputs,
    }


def run_request_document(stage: str, run_id: str, release: dict, changes: dict, selection: dict,
                         subject: str) -> dict:
    """A run request the tool writes. A request that would violate its schema is a usage error
    that names ``subject``, for example "the request of state 3"."""
    request = {
        "document": "run_request", "contract_version": CONTRACT_VERSION, "stage": stage,
        "run_id": run_id, "release": release, "changes": changes, "selection": selection,
    }
    errors = schema_errors(request, RUN_REQUEST)
    if errors:
        raise UsageError(f"{subject} would violate its schema at {errors[0]}")
    return request


def repositories_folder(repositories: Path | str | None) -> Path:
    """The repositories folder: the given one, or ``repositories/`` in the working directory."""
    return Path.cwd() / REPOSITORIES_FOLDER if repositories is None else Path(repositories)


def run_request(request_path: Path, engine: Engine, repositories: Path | None = None) -> RunResult:
    """Run the request stored at ``request_path`` and write the documents of the run beside it."""
    request_path = Path(request_path).resolve()
    repositories = repositories_folder(repositories)
    folder = request_path.parent
    if not request_path.is_file():
        raise UsageError(f"no request at {request_path}")
    response_path, export_path, record_path = (
        folder / RESPONSE_NAME, folder / EXPORT_NAME, folder / RECORD_NAME)
    for target in (response_path, export_path, record_path):
        if target.exists():
            raise UsageError(f"{target} exists already; a run overwrites no file")

    # JSON profile, contract version, schema. A request that fails here has no stage and
    # no release identity to record, so only the rejected response is written.
    request = None
    try:
        request = parse_document(request_path.read_bytes())
        check_version(request)
        check_schema(request, RUN_REQUEST)
    except Rejection as rejection:
        response = rejected_response(request, rejection)
        write_document(response_path, response, RUN_SCHEMA)
        return RunResult("rejected", response, response_path)

    repeated = {name: request[name] for name in ("stage", "run_id")}
    carried = {name: request[name] for name in ("release", "changes", "selection")}
    head = {"document": "run_response", "contract_version": CONTRACT_VERSION, **repeated}
    manifest_path, parameters, rows = None, [], None
    try:
        if request["stage"] not in engine.stages or request["stage"] not in STAGE_QUANTITIES:
            raise Rejection("unsupported_stage", f"The stage {request['stage']} is not supported.")
        _engine(engine.resolve, request["release"], repositories)
        enabled = []
        if request["changes"]["enabled"]:  # the empty set is always valid and needs no manifest
            manifest_path = check_artifact(folder, request["changes"]["manifest"])
            enabled = load_change_set(request, manifest_path, engine.realisations)
        hold = changes_contract.check_hold(request, enabled, engine.holdable)
        manifest_dir = manifest_path.parent if enabled else None
        with _opened(engine, request["release"], enabled, manifest_dir, repositories, hold) as session:
            inventory = read_inventory(session)
            parameters = inventory
            available = _engine(lambda: list(session.model_point_ids()))
            if any(not isinstance(model_point_id, str) for model_point_id in available):
                _check_model_point_ids(available)
            selected = select(request, available)
            # The request is accepted. From here the outcome is succeeded, failed, or error.
            if not selected:
                raise _StateError("no_model_point", "The release state holds no model point.")
            _check_model_point_ids(selected)
            declared = _engine(lambda: [(name, unit) for name, unit in session.quantities])
            time_basis = {"id": _engine(lambda: session.time_basis)}
            rows, ranges, failures = calculate(session, request["stage"], selected, available,
                                               [name for name, _ in declared])
            quantities = [{"name": name, "unit": unit} for name, unit in declared]
    except Rejection as rejection:
        response, parameters = rejected_response(request, rejection), []
    except _EngineError as error:
        response = {**head, "outcome": "error", **carried, "diagnostics": [Rejection(
            "state_not_readable", error_message(error.error, repositories)).diagnostic()]}
    except _StateError as error:
        response = {**head, "outcome": "error", **carried, "diagnostics": [error.rejection.diagnostic()]}
    else:
        if failures:
            response = {**head, "outcome": "failed", **carried, "failed_model_points": failures}
        else:
            write_export(export_path, [quantity["name"] for quantity in quantities], rows)
            response = {**head, "outcome": "succeeded", **carried, "time_basis": time_basis,
                        "quantities": quantities, "model_points": ranges,
                        "export": {"artifact": artifact_reference(folder, export_path),
                                   "data_rows": len(rows)}}
    outcome = response["outcome"]
    write_document(response_path, response, RUN_SCHEMA)

    if outcome == "error" and manifest_path is None and request["changes"]["enabled"]:
        # The engine raised before the manifest was checked. It is listed when it passes its
        # artifact check now, so that a replay can repeat the run; otherwise it is left out.
        try:
            manifest_path = check_artifact(folder, request["changes"]["manifest"])
        except Rejection:
            pass
    inputs = [{"role": "request", "artifact": artifact_reference(folder, request_path)}]
    if manifest_path is not None:
        # Listed once the manifest file has passed its artifact check, so the stored hash
        # is the one the request states.
        inputs.append({"role": "change_manifest", "artifact": dict(request["changes"]["manifest"])})
    outputs = [{"role": "response", "artifact": artifact_reference(folder, response_path)}]
    if outcome == "succeeded":
        outputs.append({"role": "export", "artifact": artifact_reference(folder, export_path)})
    record = run_record(request["stage"], "run", outcome, inputs, [request["release"]], parameters, outputs)
    write_document(record_path, record, RECORD_SCHEMA)
    return RunResult(outcome, response, response_path, record_path,
                     export_path if outcome == "succeeded" else None, record)
