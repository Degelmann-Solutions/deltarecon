"""The compare procedure of ``contracts/v3/compare.md``.

A comparison reads a compare request and writes, beside it, the compare result, the
deviation file and the signature table when the outcome is ``compared``, and the run
record of the comparison. This module knows no engine: it reads the documents and the
exports of two runs.

Order of the checks: JSON profile, contract version, and schema of the request; the
stage; the artifacts the request names; the two responses as documents; rule 1 with rules
7 to 13 of the run contract, the left run before the right one; rules 2 to 5; rule 6; the
finite differences; the two run records and rule 7.

A request that fails the JSON profile, the version check, or its schema raises a
:class:`~degelmann.deltarecon.documents.Rejection` and nothing is written. Every later broken rule
gives a written result with the outcome ``rejected`` or ``incompatible``. The run record
is written when the release identities of both runs can be read.

Rule 1 names no diagnostic of its own for a response that has not succeeded. A failed
response is rejected with ``model_point_failed``, the code its outcome implies, and a
rejected response or one with the outcome ``error`` with the code of its first diagnostic.

Values are paired by projection period (:func:`align`): on a time basis whose origin is the
issue date, ``ISSUE_ORIGIN``, each run counts a model point from its own first exported period;
on every other basis the periods stay as they are. The coverage lists, the deviation file and the
signature table write projection periods; the responses and exports of the runs are not changed.

The signature table is built from the compare result and the deviation file as written:
the file is read back under rules 8 to 13 before the table is derived from it.

A walk or a search that has just run both sides passes them as checked runs (``runs``): the
two runs are then not checked again (rule 1 with rules 7 to 13 of the run contract) and their
exports are not read; the responses are still read for their release identities, the
artifacts the request names are still checked, and the run records, the deviation file, and
the signature table are read and written as without them.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Context, Decimal
from pathlib import Path

from .documents import (CONTRACT_VERSION, RECORD_SCHEMA, RUN_SCHEMA, Rejection, artifact_reference,
                        check_artifact, check_document, check_schema, check_version, parse_document,
                        read_document, schema_errors, strict_json_text, write_document, write_new)
from .export import check_export, deviation_bytes, format_number, read_deviations
from .run import STAGE_QUANTITIES, UsageError, _key_order, _typed_key, quantity_errors, run_record
from .signature import signature_table

COMPARE_SCHEMA = "compare.schema.json"
COMPARE_REQUEST = f"{COMPARE_SCHEMA}#/$defs/compare_request"
TOLERANCE = f"{COMPARE_SCHEMA}#/$defs/tolerance"
RESULT_NAME = "compare.result.json"
RECORD_NAME = "compare.run-record.json"
SIGNATURE_NAME = "signature-table.json"
DEVIATIONS_NAME = "compare.deviations.csv"

# Wide enough for the largest binary64 value with fifteen decimal places.
_ROUNDING = Context(prec=400, rounding=ROUND_HALF_UP)


# The time bases whose origin is the issue date of a model point. On them a run is aligned on
# projection periods before it is compared; every other identifier keeps its periods as they are.
ISSUE_ORIGIN = frozenset({"policy_month"})


@dataclass
class CheckedRun:
    """A succeeded run that passed rule 1: its response and its values by model point and period.

    ``aligned`` marks values whose periods are projection periods already (:func:`align`)."""

    response: dict
    values: dict[tuple[str, int], list[float]] = field(repr=False)
    aligned: bool = False
    _view: CheckedRun | None = field(default=None, init=False, repr=False, compare=False)


def first_periods(values) -> dict[str, int]:
    """The first period of every model point of ``values``."""
    first: dict[str, int] = {}
    for point, period in values:
        if point not in first or period < first[point]:
            first[point] = period
    return first


def align(run: CheckedRun) -> CheckedRun:
    """The run on projection periods: on a time basis whose origin is the issue date, coordinate
    (p, t) becomes (p, t - s_p), where s_p is the first exported period of p in this run, the
    period of its valuation date. On any other basis the run itself. An aligned run is not
    aligned again, and the aligned view of a run is built once."""
    if run.aligned or run.response["time_basis"]["id"] not in ISSUE_ORIGIN:
        return run
    if run._view is None:
        first = first_periods(run.values)
        run._view = CheckedRun(run.response, {(point, period - first[point]): numbers
                                              for (point, period), numbers in run.values.items()}, True)
    return run._view


@dataclass
class CompareResult:
    outcome: str
    result: dict = field(repr=False)
    result_path: Path
    record_path: Path | None = None
    signature_path: Path | None = None
    table: dict | None = field(default=None, repr=False)
    deviations_path: Path | None = None
    deviations: list[dict] = field(default_factory=list, repr=False)  # the rows of the deviation file

    @property
    def no_deviation(self) -> bool:
        return shows_no_deviation(self.result, self.deviations)


def shows_no_deviation(result: dict, rows: list[dict]) -> bool:
    """The statement "no deviation" of the compare contract: a compared result without a row
    of its deviation file, ``rows``, and without an added or removed coordinate."""
    return result["outcome"] == "compared" and not rows and not result["added"] and not result["removed"]


def read_result_deviations(result: dict, folder: Path) -> list[dict]:
    """The rows of the deviation file a compared result references, after rules 8 to 13."""
    path = check_artifact(folder, result["deviations"])  # rule 8
    profile = result["tolerance"]["per_quantity"]

    def deviates(row: dict) -> bool:  # rule 13: the tolerance rule of the result, as in compare_runs
        return row["left"] != row["right"] and exceeds(row["left"], row["right"], profile.get(row["quantity"]))

    return read_deviations(path, [quantity["name"] for quantity in result["quantities"]], deviates)


def no_deviation(result: dict, folder: Path) -> bool:
    """The statement "no deviation" of the compare contract for a result stored in ``folder``.

    The deviation file of a compared result is read under rules 8 to 13 and its rows are
    counted, also when a coverage difference decides the answer.
    """
    if result["outcome"] != "compared":
        return False
    return shows_no_deviation(result, read_result_deviations(result, folder))


# --- tolerance rule -----------------------------------------------------------------


def round_half_away(value: float, decimals: int) -> float:
    """Commercial rounding of the decimal number that the writer form of ``value`` denotes."""
    written = Decimal(format_number(value))
    # The schema accepts a whole number written as ``2.0``; it denotes the integer 2.
    return float(written.quantize(Decimal(1).scaleb(-int(decimals)), context=_ROUNDING))


def exceeds(left: float, right: float, entry: dict | None) -> bool:
    """The tolerance rule for one common coordinate. ``entry`` is the tolerance of its quantity."""
    if entry is None:  # no entry: not rounded, all four parts at zero
        return left != right
    if "decimals" in entry:
        left, right = round_half_away(left, entry["decimals"]), round_half_away(right, entry["decimals"])
    d = right - left
    m = max(abs(left), abs(right))
    upper, lower = entry["upper"], entry["lower"]
    return (d > max(upper["abs_tol"], upper["rel_tol"] * m)
            or -d > max(lower["abs_tol"], lower["rel_tol"] * m))


def read_tolerance(path: Path | str | None, quantities: list[dict]) -> dict:
    """The tolerance profile of a tolerance file, or the empty profile without a file.

    The file holds JSON in the form of the ``tolerance`` member of a compare request. It is
    checked against the schema and against the declared ``quantities``. A fault is a usage
    error.
    """
    if path is None:
        return {"per_quantity": {}}
    path = Path(path)
    if not path.is_file():
        raise UsageError(f"no tolerance file at {path}")
    try:
        tolerance = strict_json_text(path.read_bytes().decode("utf-8"))
    except (ValueError, RecursionError) as error:
        raise UsageError(f"the tolerance file {path} is not JSON under the JSON profile: {error}") from None
    errors = schema_errors(tolerance, TOLERANCE)
    if errors:
        raise UsageError(f"the tolerance file {path} violates its schema at {errors[0]}")
    declared = {quantity["name"] for quantity in quantities}
    unknown = sorted(set(tolerance["per_quantity"]) - declared)
    if unknown:
        raise UsageError(f"the tolerance file {path} names the quantity {unknown[0]!r}, which the "
                         "run does not declare")
    return tolerance


# --- coverage -----------------------------------------------------------------------


def _ranges(keys) -> list[dict]:
    """The longest contiguous period ranges of ``keys``, by model point id and first period."""
    ranges: list[dict] = []
    for model_point_id, period in sorted(keys):
        last = ranges[-1] if ranges else None
        if last and last["model_point_id"] == model_point_id and last["last_period"] + 1 == period:
            last["last_period"] = period
        else:
            ranges.append({"model_point_id": model_point_id, "first_period": period, "last_period": period})
    return ranges


# --- parameter diff -----------------------------------------------------------------


def check_inventory(parameters: list[dict]) -> None:
    """Rule 7: unique names, unique keys, and rows that fit their columns."""
    names = [parameter["name"] for parameter in parameters]
    if len(set(names)) != len(names):
        repeated = sorted(name for name in set(names) if names.count(name) > 1)
        raise Rejection("invalid_inventory", f"The inventory holds the parameter {repeated[0]} twice.")
    for parameter in parameters:
        if parameter["type"] != "keyed_table":
            continue
        rows = parameter["rows"]
        if any(len(row["key"]) != len(parameter["key_columns"])
               or len(row["values"]) != len(parameter["value_columns"]) for row in rows):
            raise Rejection("invalid_inventory", f"A row of the table {parameter['name']} does not "
                            "hold one element per column.")
        if len({_typed_key(row["key"]) for row in rows}) != len(rows):
            raise Rejection("invalid_inventory", f"Two rows of the table {parameter['name']} have the same key.")


def _table_rows(old: dict, new: dict) -> list[dict]:
    left = {_typed_key(row["key"]): row for row in old["rows"]}
    right = {_typed_key(row["key"]): row for row in new["rows"]}
    entries = []
    for key in set(left) | set(right):
        if key not in left:
            entries.append({"key": right[key]["key"], "change": "added", "new": right[key]["values"]})
        elif key not in right:
            entries.append({"key": left[key]["key"], "change": "removed", "old": left[key]["values"]})
        elif _typed_key(left[key]["values"]) != _typed_key(right[key]["values"]):
            entries.append({"key": left[key]["key"], "change": "changed",
                            "old": left[key]["values"], "new": right[key]["values"]})
    return sorted(entries, key=lambda entry: _key_order(entry["key"]))


def parameter_diff(left: list[dict], right: list[dict]) -> list[dict]:
    """The parameter diff of two inventories that passed rule 7. It is exact."""
    old = {parameter["name"]: parameter for parameter in left}
    new = {parameter["name"]: parameter for parameter in right}
    diff = []
    for name in sorted(set(old) | set(new)):
        if name not in old:
            diff.append({"name": name, "change": "added", "new": new[name]})
        elif name not in new:
            diff.append({"name": name, "change": "removed", "old": old[name]})
        elif old[name]["type"] == new[name]["type"] == "scalar":
            if _typed_key([old[name]["value"]]) != _typed_key([new[name]["value"]]):
                diff.append({"name": name, "change": "changed", "type": "scalar",
                             "old": old[name]["value"], "new": new[name]["value"]})
        elif (old[name]["type"] == new[name]["type"] == "keyed_table"
              and old[name]["key_columns"] == new[name]["key_columns"]
              and old[name]["value_columns"] == new[name]["value_columns"]):
            rows = _table_rows(old[name], new[name])
            if rows:
                diff.append({"name": name, "change": "changed", "type": "keyed_table", "rows": rows})
        else:
            diff.append({"name": name, "change": "replaced", "old": old[name], "new": new[name]})
    return diff


# --- the comparison of two checked runs ---------------------------------------------


def _head(request: dict, outcome: str) -> dict:
    return {"document": "compare_result", "contract_version": CONTRACT_VERSION,
            "stage": request["stage"], "compare_id": request["compare_id"], "outcome": outcome}


def _not_compared(request: dict, outcome: str, rejection: Rejection) -> dict:
    return {**_head(request, outcome), "diagnostics": [rejection.diagnostic()]}


class _Incompatible(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.rejection = Rejection(code, message)


def compare_runs(request: dict, left: CheckedRun, right: CheckedRun) -> tuple[dict, list[dict]]:
    """Compare two runs that passed rule 1.

    Return the compare result without a parameter diff and without the reference to the
    deviation file, and the deviations in the order of the deviation file. Rules 2 to 6
    are applied here, then alignment on projection periods (:func:`align`), the check that
    every difference is finite, coverage, and the tolerance rule. Coverage ranges and the
    deviations carry projection periods.
    """
    try:
        _check_compatible(request, left.response, right.response)
    except _Incompatible as incompatible:
        return _not_compared(request, "incompatible", incompatible.rejection), []

    quantities = left.response["quantities"]
    names = [quantity["name"] for quantity in quantities]
    profile = request["tolerance"]["per_quantity"]
    unknown = sorted(set(profile) - set(names))  # rule 6
    if unknown:
        return _not_compared(request, "rejected", Rejection(
            "unknown_quantity", f"The request sets a tolerance for {unknown[0]}, which the two runs "
            "do not declare.")), []

    left, right = align(left), align(right)
    common = sorted(set(left.values) & set(right.values))
    # Every difference of the exported values is finite, before any rounding or tolerance.
    overflow = sorted({key[0] for key in common
                       if any(a != b and not math.isfinite(b - a)
                              for a, b in zip(left.values[key], right.values[key]))})
    if overflow:
        return _not_compared(request, "rejected", Rejection(
            "non_finite_difference", "The difference of the right and the left value of a coordinate is "
            "not a finite number.", model_point_ids=overflow)), []

    entries = [profile.get(name) for name in names]
    deviations = []
    for key in common:
        old, new = left.values[key], right.values[key]
        if old == new:  # equal values never deviate
            continue
        for name, entry, a, b in zip(names, entries, old, new):
            if a != b and exceeds(a, b, entry):
                deviations.append({"model_point_id": key[0], "period": key[1], "quantity": name,
                                   "left": a, "right": b})
    result = {
        **_head(request, "compared"),
        "left": {"run_id": left.response["run_id"], "release_label": left.response["release"]["label"]},
        "right": {"run_id": right.response["run_id"], "release_label": right.response["release"]["label"]},
        "tolerance": request["tolerance"],
        "time_basis": left.response["time_basis"],
        "quantities": quantities,
        "compared_coordinates": len(common) * len(names),
        "deviating_model_points": sorted({deviation["model_point_id"] for deviation in deviations}),
        "added": _ranges(set(right.values) - set(left.values)),
        "removed": _ranges(set(left.values) - set(right.values)),
    }
    return result, deviations


def _insert_after(document: dict, after: str, name: str, value) -> dict:
    """``document`` with the member ``name`` placed after the member ``after``."""
    placed = {}
    for key, member in document.items():
        placed[key] = member
        if key == after:
            placed[name] = value
    return placed


def _check_compatible(request: dict, left: dict, right: dict) -> None:
    """Rules 2 to 5."""
    if not left["stage"] == right["stage"] == request["stage"]:
        raise _Incompatible("stage_mismatch", f"The request names the stage {request['stage']}, the left "
                            f"run {left['stage']}, and the right run {right['stage']}.")
    if left["time_basis"]["id"] != right["time_basis"]["id"]:
        raise _Incompatible("time_basis_mismatch", f"The left run declares the time basis "
                            f"{left['time_basis']['id']} and the right run {right['time_basis']['id']}.")
    left_units = {quantity["name"]: quantity["unit"] for quantity in left["quantities"]}
    right_units = {quantity["name"]: quantity["unit"] for quantity in right["quantities"]}
    if set(left_units) != set(right_units):
        other = sorted(set(left_units) ^ set(right_units))[0]
        raise _Incompatible("quantity_mismatch", f"Only one of the two runs declares the quantity {other}.")
    for name, unit in left_units.items():
        if right_units[name] != unit:
            raise _Incompatible("unit_mismatch", f"The left run declares {name} in {unit} and the right "
                                f"run in {right_units[name]}.")


# --- the procedure ------------------------------------------------------------------


def check_run(response: dict, folder: Path, side: str) -> CheckedRun:
    """Rule 1: the response has succeeded and passes rules 7 to 13 of the run contract."""
    if response["outcome"] == "failed":
        raise Rejection("model_point_failed", f"The {side} run has failed; only a succeeded run is compared.",
                        model_point_ids=sorted({point["model_point_id"]
                                                for point in response["failed_model_points"]}))
    if response["outcome"] == "error":
        raise Rejection(response["diagnostics"][0]["code"],
                        f"The {side} run has ended with an error; only a succeeded run is compared.")
    if response["outcome"] != "succeeded":
        raise Rejection(response["diagnostics"][0]["code"],
                        f"The {side} run was rejected; only a succeeded run is compared.")
    if response["stage"] not in STAGE_QUANTITIES:
        raise Rejection("unsupported_stage", f"The stage {response['stage']} of the {side} run is not supported.")
    problem = quantity_errors(response["stage"], [quantity["name"] for quantity in response["quantities"]])
    if problem:  # rule 7
        raise Rejection("quantity_mismatch", f"The {side} run declares its quantities wrongly: {problem}.")
    export_path = check_artifact(folder, response["export"]["artifact"])  # rule 8
    return CheckedRun(response, check_export(response, export_path))  # rules 9 to 13


def _read_release(folder: Path, side: dict) -> dict | None:
    """The release identity of one side, when its response can be read and carries one."""
    try:
        path = check_artifact(folder, side["response"])
        return read_document(path, RUN_SCHEMA, "run_response").get("release")
    except Rejection:
        return None


def _engine_version(path: Path | None) -> str | None:
    """The value of the one ``engine_version`` reference of a run record, if it can be read."""
    if path is None:
        return None
    try:
        record = read_document(path, RECORD_SCHEMA, "run_record")
    except Rejection:
        return None
    values = [reference["value"] for release in record["releases"] for reference in release["references"]
              if reference["kind"] == "engine_version"]
    return values[0] if len(values) == 1 else None


def _with_engine_versions(result: dict, paths: dict) -> dict:
    """The result with the member ``engine_version`` when both run records name different versions."""
    if result["outcome"] == "incompatible":
        return result
    versions = [_engine_version(paths.get((name, "run_record"))) for name in ("left", "right")]
    if None in versions or versions[0] == versions[1]:
        return result
    member = {"left": versions[0], "right": versions[1]}
    return _insert_after(result, "right" if result["outcome"] == "compared" else "outcome",
                         "engine_version", member)


def _compare_request(request: dict, folder: Path,
                     preloaded: tuple[CheckedRun, CheckedRun] | None = None) -> tuple[dict, list[dict]]:
    """Every check after the schema of the request. Return the compare result and the deviations.

    ``preloaded`` are the two runs, already checked, of the responses the request names.
    """
    paths = {}
    try:
        if request["stage"] not in STAGE_QUANTITIES:
            raise Rejection("unsupported_stage", f"The stage {request['stage']} is not supported.")
        sides = (("left", request["left"]), ("right", request["right"]))
        for name, side in sides:
            for member in ("response", "run_record"):
                if member in side:
                    paths[name, member] = check_artifact(folder, side[member])
        if preloaded is not None:
            runs = dict(zip(("left", "right"), preloaded))
        else:
            responses = {name: read_document(paths[name, "response"], RUN_SCHEMA, "run_response")
                         for name, _ in sides}
            runs = {name: check_run(responses[name], paths[name, "response"].parent, name)
                    for name, _ in sides}
    except Rejection as rejection:
        return _with_engine_versions(_not_compared(request, "rejected", rejection), paths), []

    result, deviations = compare_runs(request, runs["left"], runs["right"])
    if result["outcome"] != "compared" or ("left", "run_record") not in paths \
            or ("right", "run_record") not in paths:
        return _with_engine_versions(result, paths), deviations
    try:
        inventories = []
        for name, _ in sides:
            record = read_document(paths[name, "run_record"], RECORD_SCHEMA)
            check_inventory(record["parameters"])  # rule 7
            inventories.append(record["parameters"])
    except Rejection as rejection:
        return _with_engine_versions(_not_compared(request, "rejected", rejection), paths), []
    result["parameter_diff"] = parameter_diff(*inventories)
    return _with_engine_versions(result, paths), deviations


def compare_request_document(stage: str, compare_id: str, left: tuple[dict, dict], right: tuple[dict, dict],
                             tolerance: dict) -> dict:
    """A compare request the tool writes. ``left`` and ``right`` hold the artifact references
    of the response and the run record of each side."""
    return {
        "document": "compare_request", "contract_version": CONTRACT_VERSION, "stage": stage,
        "compare_id": compare_id,
        "left": {"response": left[0], "run_record": left[1]},
        "right": {"response": right[0], "run_record": right[1]},
        "tolerance": tolerance,
    }


def compare(request_path: Path | str, *, result_name: str = RESULT_NAME,
            record_name: str | None = RECORD_NAME,
            signature_name: str | None = SIGNATURE_NAME,
            deviations_name: str = DEVIATIONS_NAME,
            runs: tuple[CheckedRun, CheckedRun] | None = None) -> CompareResult:
    """Compare the two runs a stored compare request names and write the documents beside it.

    ``record_name`` and ``signature_name`` are ``None`` for a caller that records the
    comparison itself and wants no table, such as the replay. The deviation file is
    written for every comparison with the outcome ``compared``. ``runs`` are the left and
    the right run, already checked, of the two responses the request names; with them the two
    runs are not checked again (rule 1 with rules 7 to 13) and their exports are not read. The
    responses are still read for their release identities.
    """
    request_path = Path(request_path).resolve()
    folder = request_path.parent
    if not request_path.is_file():
        raise UsageError(f"no compare request at {request_path}")
    result_path = folder / result_name
    deviations_path = folder / deviations_name
    record_path = folder / record_name if record_name else None
    signature_path = folder / signature_name if signature_name else None
    for target in (result_path, deviations_path, record_path, signature_path):
        if target is not None and target.exists():
            raise UsageError(f"{target} exists already; a comparison overwrites no file")

    request = parse_document(request_path.read_bytes())
    check_version(request)
    check_schema(request, COMPARE_REQUEST)

    result, deviations = _compare_request(request, folder, runs)
    outcome = result["outcome"]
    releases = [_read_release(folder, request[name]) for name in ("left", "right")]

    # The deviation file comes first, because the result holds its hash. The table is
    # derived from the result and the file as written, read back under rules 8 to 13.
    # The result and the table are checked before either is written; the run record
    # follows them, because it holds their hashes.
    written: list[Path] = []
    table = None
    try:
        if outcome == "compared":
            write_new(deviations_path, deviation_bytes(deviations))
            written.append(deviations_path)
            result = _insert_after(result, "compared_coordinates", "deviations",
                                   artifact_reference(folder, deviations_path))
            deviations = read_result_deviations(result, folder)
            if signature_path is not None:
                table = signature_table(result, deviations)
        files = [(result_path, result, COMPARE_SCHEMA)]
        if table is not None:
            files.append((signature_path, table, COMPARE_SCHEMA))
        stored = [(path, check_document(document, schema, path.name)) for path, document, schema in files]
        for path, data in stored:
            write_new(path, data)
            written.append(path)
    except BaseException:  # also an interruption: leave no part of a comparison behind
        for path in written:
            path.unlink(missing_ok=True)
        raise

    written_record = None
    if record_path is not None and all(release is not None for release in releases):
        outputs = [{"role": "result", "artifact": artifact_reference(folder, result_path)}]
        if outcome == "compared":
            outputs.append({"role": "deviations", "artifact": artifact_reference(folder, deviations_path)})
        if table is not None:
            outputs.append({"role": "signature_table", "artifact": artifact_reference(folder, signature_path)})
        inputs = [{"role": "request", "artifact": artifact_reference(folder, request_path)}]
        write_document(record_path, run_record(request["stage"], "compare", outcome, inputs, releases, [], outputs),
                       RECORD_SCHEMA)
        written_record = record_path
    return CompareResult(outcome, result, result_path, written_record,
                         signature_path if table is not None else None, table,
                         deviations_path if outcome == "compared" else None, deviations)
