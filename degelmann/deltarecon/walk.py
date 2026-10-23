"""The walk of ``contracts/v2/localise.md``: every state between two recorded results.

A walk reads the records of two succeeded runs without enabled changes, the older one
first, derives the change manifest of the history between the revisions they name, runs
state 0 to state n on the common selection of both records, checks state 0 against the
older and state n against the newer recorded result, compares each state that ran with
the one that ran before it, and writes one walk result: per revision and quantity the
contribution of that revision. This module knows no engine and no kind of reference: it
compares opaque references for equality and asks the engine everything else.

Before anything runs:

- both records name one stage (``stage_mismatch``) and one selection
  (``selection_mismatch``);
- the manifest is derived as by ``derive``;
- a kind the engine can hold whose references are equal in both records is held at the
  older release for every state; every other kind a revision determines moves with the
  states. For each moving kind the engine's identity of the base revision must name what
  the older record names, and its identity of the last revision what the newer record
  names; otherwise the walk refuses with ``reference_mismatch``;
- the engine resolves the release every state is requested on.

A refusal raises a :class:`~degelmann.deltarecon.documents.Rejection` and writes nothing. The output
folder must not exist; a walk that is interrupted leaves no folder behind. It receives:

- ``changes.json``, the derived manifest;
- ``older/`` and ``newer/``: request, response, export, and record of the two recorded
  runs, byte for byte, and ``tolerance.json``, the tolerance file as given;
- ``state-00/`` to ``state-<n>/``: one normal run per state, with a copy of the manifest
  from state 1 on;
- at the root, the comparisons the walk keeps: ``step-<k>.compare.*`` for a step that
  contributes, ``state-<k>.check-older.*`` and ``state-<k>.check-newer.*`` for an end
  that is not reproduced;
- ``walk.result.json`` and ``walk.run-record.json``.

Sums are exact: every binary64 value is an integer multiple of 2**-1074, so the walk adds
integers and rounds once, to the nearest binary64 value, when it writes a sum.

The checks before the first run, the folder setup, the run of a state, the checks of the
ends, and the comparisons kept are shared with the search of ``degelmann/deltarecon/search.py``
(:func:`prepare`, :class:`States`), as is the reader of a walk folder
(:func:`read_walk_folder`), which applies the reader rules of a walk folder.
"""
from __future__ import annotations

import json
import shutil
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from . import changes as changes_contract
from .compare import (COMPARE_REQUEST, CheckedRun, CompareResult, compare, compare_request_document, compare_runs,
                      read_tolerance, shows_no_deviation)
from .derive import CLASS_ORDER, build_manifest, read_derive_input, remainder
from .documents import (CONTRACT_VERSION, RECORD_SCHEMA, RUN_SCHEMA, SCHEMA_FOLDERS, Rejection, artifact_reference,
                        check_artifact, copy_files, document_bytes, parse_document, read_document, sha256_file,
                        write_document, write_new)
from .replay import RecordedRun, check_response
from .run import Engine, RunResult, UsageError, repositories_folder, run_record, run_request, run_request_document

LOCALISE_SCHEMA = "localise.schema.json"
MANIFEST_NAME = "changes.json"
REQUEST_NAME = "request.json"
TOLERANCE_NAME = "tolerance.json"
RESULT_NAME = "walk.result.json"
RECORD_NAME = "walk.run-record.json"
OLDER, NEWER = "older", "newer"
# Every finite binary64 value is an integer multiple of 2**-1074.
_SHIFT = 1074


@dataclass
class WalkResult:
    result: dict = field(repr=False)
    result_path: Path
    record_path: Path

    @property
    def attributed(self) -> bool:
        """Both ends ran and are reproduced, so every revision is attributed."""
        ends = self.result["ends"]
        return ends["zero"]["outcome"] == ends["n"]["outcome"] == "reproduced"


# --- exact sums ------------------------------------------------------------------------


def _scaled(value: float) -> int:
    """``value`` as an integer multiple of 2**-1074, exactly."""
    numerator, denominator = float(value).as_integer_ratio()
    return numerator << (_SHIFT - (denominator.bit_length() - 1))


def written(total: int) -> float | None:
    """An exact sum in units of 2**-1074, rounded to the nearest binary64 value; ``None`` when
    it does not fit a finite one."""
    try:
        return total / (1 << _SHIFT)  # integer division into a float is correctly rounded
    except OverflowError:
        return None


def exact_sums(left: CheckedRun, right: CheckedRun, names: list[str]) -> tuple[list[int], list[int]]:
    """Per quantity of ``names``: the sum of ``right - left`` over every coordinate and the sum of
    its absolute values, both exact in units of 2**-1074. A missing coordinate counts as 0."""
    left_index = {quantity["name"]: i for i, quantity in enumerate(left.response["quantities"])}
    right_index = {quantity["name"]: i for i, quantity in enumerate(right.response["quantities"])}
    positions = [(j, left_index.get(name), right_index.get(name)) for j, name in enumerate(names)]
    same_layout = all(a == b for _, a, b in positions)
    signed, absolute = [0] * len(names), [0] * len(names)
    for key in left.values.keys() | right.values.keys():
        old, new = left.values.get(key), right.values.get(key)
        if same_layout and old == new:
            continue
        for j, at_left, at_right in positions:
            a = old[at_left] if old is not None and at_left is not None else 0.0
            b = new[at_right] if new is not None and at_right is not None else 0.0
            if a == b:
                continue
            difference = _scaled(b) - _scaled(a)
            signed[j] += difference
            absolute[j] += abs(difference)
    return signed, absolute


# --- reading the two records -------------------------------------------------------------


def _references(release: dict, kind: str) -> list[str]:
    """The references of one kind, as a set: compared for equality and nothing else."""
    return sorted(json.dumps(reference, sort_keys=True, ensure_ascii=False)
                  for reference in release["references"] if reference["kind"] == kind)


def held_kinds(older: dict, newer: dict, holdable, determines) -> list[str]:
    """The determined kinds the engine can hold whose references are present and equal in both identities."""
    return sorted(kind for kind in holdable if kind in determines
                  and _references(older, kind) and _references(older, kind) == _references(newer, kind))


def _selection(request: dict) -> tuple[str, frozenset]:
    selection = request["selection"]
    return selection["mode"], frozenset(selection.get("model_point_ids", []))


def _checked(recorded: RecordedRun) -> CheckedRun:
    return CheckedRun(recorded.response, recorded.values)


# --- the checks before the first run --------------------------------------------------


@dataclass
class Prepared:
    """What the checks before the first run establish, for a walk and for a search."""

    older: RecordedRun = field(repr=False)
    newer: RecordedRun = field(repr=False)
    profile: dict
    manifest: dict = field(repr=False)
    hold: list[str]
    base: dict
    holdable: dict = field(repr=False)

    @property
    def stage(self) -> str:
        return self.older.record["stage"]

    @property
    def ids(self) -> list[str]:
        return [change["id"] for change in self.manifest["changes"]]

    @property
    def releases(self) -> tuple[dict, dict]:
        return self.older.record["releases"][0], self.newer.record["releases"][0]

    def held(self) -> list[dict]:
        """Per held kind: its classes and the revisions whose effect on it is not shown."""
        classes = {change["id"]: change["class"] for change in self.manifest["changes"]}
        ids = self.ids
        return [{"kind": kind, "classes": [name for name in CLASS_ORDER if name in self.holdable[kind]],
                 "not_shown": [i for i in ids if set(classes[i]) & set(self.holdable[kind])]}
                for kind in self.hold if ids]


def prepare(older_record: Path | str, newer_record: Path | str, engine: Engine, repositories: Path,
            tolerance: Path | str | None, procedure: str = "walk") -> Prepared:
    """The checks of ``localise.md`` before the first run. A refusal raises a :class:`Rejection`."""
    older = read_derive_input(older_record, engine.stages)
    newer = read_derive_input(newer_record, engine.stages)
    stage = older.record["stage"]
    if newer.record["stage"] != stage:
        raise Rejection("stage_mismatch", f"The older record names the stage {stage}, the newer one "
                        f"the stage {newer.record['stage']}.")
    if _selection(older.request) != _selection(newer.request):
        runs = "every state" if procedure == "walk" else "its states"
        raise Rejection("selection_mismatch", f"The two records hold different selections; a {procedure} runs "
                        f"{runs} on the common selection of both.")
    profile = read_tolerance(tolerance, older.response["quantities"])
    old_release, new_release = older.record["releases"][0], newer.record["releases"][0]
    history = engine.history(old_release, new_release, repositories)
    manifest = build_manifest(history, stage, old_release["label"], engine.determines,
                              remainder(old_release, new_release, engine.determines))
    changes_contract.check_manifest_rules(manifest)

    holdable = engine.holdable
    hold = held_kinds(old_release, new_release, holdable, engine.determines)
    base = engine.state_release(old_release, None, frozenset(), repositories)
    start = engine.state_release(old_release, history.older, frozenset(), repositories)
    end = engine.state_release(old_release, history.newer, frozenset(hold), repositories)
    for kind in sorted(set(engine.determines) - set(hold)):
        for side, state, recorded in ((OLDER, start, old_release), (NEWER, end, new_release)):
            if _references(state, kind) != _references(recorded, kind):
                raise Rejection("reference_mismatch", f"The references of the kind {kind} move with the states, "
                                f"and the {'base' if side == OLDER else 'last'} revision does not name what the "
                                f"{side} record names.")
    engine.resolve(base, repositories)
    return Prepared(older, newer, profile, manifest, hold, base, dict(holdable))


def state_request(prepared: Prepared, k: int) -> tuple[dict, list[str], list[str] | None, dict]:
    """The release, the enabled changes, the held kinds (``None`` when none is held), and the
    selection of the request of state ``k``."""
    hold = list(prepared.hold) if k and prepared.hold else None
    return prepared.base, prepared.ids[:k], hold, prepared.older.request["selection"]


@contextmanager
def new_folder(output: Path):
    """Create ``output``; an error or an interruption removes it again, so that no folder blocks the next attempt."""
    output.mkdir(parents=True)
    try:
        yield
    except BaseException:
        shutil.rmtree(output, ignore_errors=True)
        raise


# --- the states ----------------------------------------------------------------------


class States:
    """The states of one walk or search while it writes its folder: the runs, the end checks,
    and the comparisons it keeps."""

    procedure = "walk"
    record_name = RECORD_NAME

    def __init__(self, output: Path, engine: Engine, repositories: Path, prepared: Prepared, prefix: str):
        self.output, self.engine, self.repositories = output, engine, repositories
        self.prepared = prepared
        self.older, self.newer, self.manifest = prepared.older, prepared.newer, prepared.manifest
        self.base, self.hold, self.profile = prepared.base, prepared.hold, prepared.profile
        self.stage = prepared.stage
        self.prefix = prefix
        self.ids = prepared.ids
        self.width = max(2, len(str(len(self.ids))))
        self.names = [quantity["name"] for quantity in self.older.response["quantities"]]
        self.manifest_bytes = document_bytes(self.manifest)
        self.states, self.findings = [], []
        self.compares: list[Path] = []  # the compare results written, in the order of writing

    def name(self, k: int) -> str:
        return f"state-{k:0{self.width}d}"

    def setup(self, tolerance: Path | str | None) -> None:
        """The manifest, the copies of the two recorded runs, and the tolerance file."""
        write_new(self.output / MANIFEST_NAME, self.manifest_bytes)
        self.copy_recorded(self.older, OLDER)
        self.copy_recorded(self.newer, NEWER)
        if tolerance is not None:
            write_new(self.output / TOLERANCE_NAME, Path(tolerance).read_bytes())

    # The recorded runs, byte for byte.
    def copy_recorded(self, recorded: RecordedRun, side: str) -> None:
        copy_files(recorded.folder, self.output / side, recorded.files())

    def recorded_files(self, recorded: RecordedRun, side: str) -> tuple[Path, Path]:
        return (self.output / side / recorded.response_ref["path"], self.output / side / recorded.record_path.name)

    def state_changes(self, k: int) -> tuple[list[str], list[str] | None]:
        """The enabled changes and the held kinds of the request of state ``k``."""
        return state_request(self.prepared, k)[1:3]

    def carried(self, k: int, outcome: str) -> str:
        return (f"State {k} ended with the outcome {outcome}; its revisions are carried "
                "by the next state that runs.")

    # One state: a normal run of the run contract in a folder of its own.
    def run_state(self, k: int) -> tuple[RunResult, dict]:
        folder = self.output / self.name(k)
        folder.mkdir()
        enabled, hold = self.state_changes(k)
        changes = {"enabled": enabled}
        if k:
            write_new(folder / MANIFEST_NAME, self.manifest_bytes)
            changes["manifest"] = artifact_reference(folder, folder / MANIFEST_NAME)
            if hold:
                changes["hold"] = hold
        request = run_request_document(self.stage, f"{self.prefix}-state-{k}", self.base, changes,
                                       self.older.request["selection"], f"the request of state {k}")
        write_new(folder / REQUEST_NAME, document_bytes(request))
        run = run_request(folder / REQUEST_NAME, self.engine, self.repositories)
        entry = {"state": k, **({"revision": self.ids[k - 1]} if k else {}), "run_id": request["run_id"],
                 "outcome": run.outcome, "response": artifact_reference(self.output, run.response_path)}
        if run.outcome == "succeeded":
            entry["export"] = artifact_reference(self.output, run.export_path)
        self.states.append(entry)
        if run.outcome != "succeeded":
            response = run.response
            if run.outcome == "failed":
                diagnostic = Rejection("model_point_failed", "A model point of the state could not be calculated.",
                                       model_point_ids=sorted({point["model_point_id"]
                                                               for point in response["failed_model_points"]}))
                diagnostic = diagnostic.diagnostic()
            else:
                diagnostic = response["diagnostics"][0]
            finding = {"code": "state_did_not_run", "message": self.carried(k, run.outcome), "state": k}
            if k:
                finding["revisions"] = [self.ids[k - 1]]
            finding["diagnostic"] = diagnostic
            self.findings.append(finding)
        return run, request

    def checked(self, run: RunResult, request: dict) -> CheckedRun:
        return CheckedRun(run.response, check_response(request, run.response, run.response_path.parent))

    # A comparison the procedure keeps, written at the root of the folder.
    def write_compare(self, prefix: str, compare_id: str, left: tuple[Path, Path],
                      right: tuple[Path, Path]) -> CompareResult:
        request = compare_request_document(
            self.stage, compare_id, tuple(artifact_reference(self.output, path) for path in left),
            tuple(artifact_reference(self.output, path) for path in right), self.profile)
        request_path = self.output / f"{prefix}.request.json"
        write_document(request_path, request, COMPARE_REQUEST)
        compared = compare(request_path, result_name=f"{prefix}.result.json",
                           record_name=f"{prefix}.run-record.json",
                           signature_name=f"{prefix}.signature-table.json",
                           deviations_name=f"{prefix}.deviations.csv")
        self.compares.append(compared.result_path)
        return compared

    def reference(self, compared: CompareResult) -> dict:
        reference = {"result": artifact_reference(self.output, compared.result_path)}
        if compared.deviations_path is not None:
            reference["deviations"] = artifact_reference(self.output, compared.deviations_path)
        return reference

    def check_end(self, k: int, state: CheckedRun, run: RunResult, recorded: RecordedRun, side: str) -> dict:
        """State ``k`` against the recorded result of one end: no deviation, no added or removed coordinate."""
        compare_id = f"{self.prefix}-state-{k}-check-{side}"
        result, deviations = compare_runs({"stage": self.stage, "compare_id": compare_id,
                                           "tolerance": self.profile}, _checked(recorded), state)
        if shows_no_deviation(result, deviations):
            return {"state": k, "outcome": "reproduced"}
        compared = self.write_compare(f"{self.name(k)}.check-{side}", compare_id,
                                      self.recorded_files(recorded, side), (run.response_path, run.record_path))
        end = {"state": k, "outcome": "not_reproduced", "compare": self.reference(compared)}
        code = "state_zero_not_reproduced" if side == OLDER else "state_n_not_reproduced"
        self.findings.append({"code": code, "message": f"State {k} does not reproduce the {side} recorded result "
                              f"under the tolerance of the {self.procedure}.", "state": k,
                              "compare": end["compare"]})
        return end

    def contributions(self, from_k: int, to_k: int, left: CheckedRun, right: CheckedRun, names: list[str],
                      contributes: list[bool], table: dict | None) -> list[dict]:
        """One contribution per quantity of ``names``: the flag, the exact sums, and the signature row."""
        revisions = self.ids[from_k:to_k]
        signed, absolute = exact_sums(left, right, names)
        rows = {row["quantity"]: row for row in (table or {}).get("rows", [])}
        entries = []
        for name, flag, total, size in zip(names, contributes, signed, absolute):
            contribution = {"quantity": name, "contributes": flag}
            for member, value in (("sum", written(total)), ("absolute_sum", written(size))):
                if value is None:
                    self.findings.append({
                        "code": "non_finite_difference",
                        "message": f"The {member.replace('_', ' ')} of {name} from state {from_k} to state {to_k} "
                                   "does not fit a finite binary64 number and is not written.",
                        "state": to_k, "revisions": revisions, "quantity": name})
                else:
                    contribution[member] = value
            if flag and name in rows:  # a quantity that does not contribute holds no signature row
                contribution["signature"] = rows[name]
            entries.append(contribution)
        return entries

    def write_record(self, outcome: str, result_path: Path, tolerance: Path | str | None,
                     further_inputs: list[dict] = ()) -> Path:
        """The run record of the procedure: the two recorded runs as copied, the tolerance file, the
        manifest, the result, and every comparison kept."""
        output = self.output
        inputs = [{"role": "older_record",
                   "artifact": artifact_reference(output, self.recorded_files(self.older, OLDER)[1])},
                  {"role": "newer_record",
                   "artifact": artifact_reference(output, self.recorded_files(self.newer, NEWER)[1])}]
        if tolerance is not None:
            inputs.append({"role": "tolerance", "artifact": artifact_reference(output, output / TOLERANCE_NAME)})
        inputs += list(further_inputs)
        outputs = [{"role": "change_manifest", "artifact": artifact_reference(output, output / MANIFEST_NAME)},
                   {"role": "result", "artifact": artifact_reference(output, result_path)}]
        outputs += [{"role": "compare_result", "artifact": artifact_reference(output, path)}
                    for path in self.compares]
        record = run_record(self.stage, self.procedure, outcome, inputs, list(self.prepared.releases), [], outputs)
        record_path = output / self.record_name
        write_document(record_path, record, RECORD_SCHEMA)
        return record_path


# --- the walk --------------------------------------------------------------------------


class _Walk(States):
    """The state of one walk while it writes its folder."""

    def step(self, from_k: int, to_k: int, left: CheckedRun, right: CheckedRun,
             left_run: RunResult, right_run: RunResult) -> None:
        """The step from state ``from_k`` to state ``to_k`` and the revisions it carries."""
        revisions = self.ids[from_k:to_k]
        compare_id = f"{self.prefix}-step-{to_k}"
        result, deviations = compare_runs({"stage": self.stage, "compare_id": compare_id,
                                           "tolerance": self.profile}, left, right)
        contributes = flags(result, deviations, self.names)
        entry = {"from_state": from_k, "to_state": to_k, "revisions": revisions}
        table = None
        if any(contributes):
            compared = self.write_compare(f"step-{to_k:0{self.width}d}.compare", compare_id,
                                          (left_run.response_path, left_run.record_path),
                                          (right_run.response_path, right_run.record_path))
            entry["compare"] = self.reference(compared)
            table = compared.table
            if compared.outcome != "compared":
                self.findings.append({
                    "code": "step_not_compared",
                    "message": f"The comparison of state {from_k} with state {to_k} has the outcome "
                               f"{compared.outcome}; the sums are kept and every quantity contributes.",
                    "state": to_k, "revisions": revisions, "diagnostic": compared.result["diagnostics"][0],
                    "compare": entry["compare"]})
        entry["contributions"] = self.contributions(from_k, to_k, left, right, self.names, contributes, table)
        self.steps.append(entry)

    def totals(self) -> list[dict]:
        """The deviation between the two recorded results, per quantity."""
        signed, _ = exact_sums(_checked(self.older), _checked(self.newer), self.names)
        totals = []
        for name, total in zip(self.names, signed):
            value = written(total)
            totals.append({"quantity": name, **({"sum": value} if value is not None else {})})
            if value is None:
                self.findings.append({"code": "non_finite_difference",
                                      "message": f"The deviation of {name} between the two recorded results does "
                                                 "not fit a finite binary64 number and is not written.",
                                      "quantity": name})
        return totals

    def run(self) -> tuple[dict, dict, list[str]]:
        """Run every state. Return the two ends and the revisions left unattributed."""
        self.steps = []
        n = len(self.ids)
        not_run = {"state": n, "outcome": "not_run"}
        run, request = self.run_state(0)
        if run.outcome != "succeeded":
            return {"state": 0, "outcome": "not_run"}, not_run, list(self.ids)
        state = self.checked(run, request)
        zero = self.check_end(0, state, run, self.older, OLDER)
        if zero["outcome"] != "reproduced":
            last = self.check_end(0, state, run, self.newer, NEWER) if n == 0 else not_run
            return zero, last, list(self.ids)
        previous = (0, state, run)
        for k in range(1, n + 1):
            run, request = self.run_state(k)
            if run.outcome != "succeeded":
                continue
            state = self.checked(run, request)
            self.step(previous[0], k, previous[1], state, previous[2], run)
            previous = (k, state, run)
        if previous[0] != n:
            return zero, not_run, self.ids[previous[0]:]
        return zero, self.check_end(n, previous[1], previous[2], self.newer, NEWER), []


def flags(result: dict, deviations: list[dict], names: list[str]) -> list[bool]:
    """Per quantity of ``names``: whether a comparison differs for it. A coordinate of the quantity
    deviates, or a coordinate is added or removed; a comparison without the outcome ``compared``
    differs for every quantity."""
    if result["outcome"] != "compared":
        return [True] * len(names)
    coverage = bool(result["added"] or result["removed"])
    deviating = {deviation["quantity"] for deviation in deviations}
    return [coverage or name in deviating for name in names]


def walk(older_record: Path | str, newer_record: Path | str, output: Path | str, engine: Engine,
         repositories: Path | None = None, tolerance: Path | str | None = None) -> WalkResult:
    """Walk every state between two recorded runs and write the walk result into ``output``."""
    output = Path(output).resolve()
    repositories = repositories_folder(repositories)
    if output.exists():
        raise UsageError(f"{output} exists already; a walk overwrites no file")
    prepared = prepare(older_record, newer_record, engine, repositories, tolerance)
    older, newer = prepared.older, prepared.newer
    old_release, new_release = prepared.releases

    with new_folder(output):
        state = _Walk(output, engine, repositories, prepared,
                      f"walk-{older.request['run_id']}-{newer.request['run_id']}")
        state.setup(tolerance)
        zero, last, unattributed = state.run()
        held = prepared.held()
        totals = state.totals()
        result = {
            "document": "walk_result", "contract_version": CONTRACT_VERSION, "stage": prepared.stage,
            "walk_id": state.prefix,
            "manifest": artifact_reference(output, output / MANIFEST_NAME),
            "older": {"run_id": older.request["run_id"], "release_label": old_release["label"]},
            "newer": {"run_id": newer.request["run_id"], "release_label": new_release["label"]},
            "tolerance": prepared.profile, "held": held, "remainder": prepared.manifest["history"]["remainder"],
            "ends": {"zero": zero, "n": last}, "states": state.states, "steps": state.steps,
            "unattributed": unattributed, "totals": totals, "findings": state.findings,
        }
        result_path = output / RESULT_NAME
        write_document(result_path, result, LOCALISE_SCHEMA)
        outcome = "attributed" if zero["outcome"] == last["outcome"] == "reproduced" else "not_attributed"
        record_path = state.write_record(outcome, result_path, tolerance)
    return WalkResult(result, result_path, record_path)


# --- reading a walk folder -----------------------------------------------------------


@dataclass
class WalkFolder:
    """A walk folder that passed the reader rules of ``localise.md`` and fits a search."""

    folder: Path
    result: dict = field(repr=False)
    record: dict = field(repr=False)
    files: list[str] = field(repr=False)  # every file the walk documents reference, transitively, by relative path


def _mismatch(message: str) -> Rejection:
    return Rejection("walk_mismatch", message)


def _artifact_nodes(node, found: list[dict]) -> list[dict]:
    """Every artifact reference of a document outside the release identities: an object with
    exactly ``path`` and ``sha256``. A release reference is opaque and is not followed."""
    if isinstance(node, dict):
        if set(node) == {"path", "sha256"}:
            found.append(node)
        for key, value in node.items():
            if key not in ("release", "releases"):
                _artifact_nodes(value, found)
    elif isinstance(node, list):
        for value in node:
            _artifact_nodes(value, found)
    return found


def _closure(folder: Path, starts: list[str]) -> list[str]:
    """The files ``starts`` name and every file their documents reference, directly or through a
    referenced document, each existing below ``folder`` with its hash. By relative path."""
    seen: dict[str, None] = {}
    pending = list(starts)
    while pending:
        relative = pending.pop(0)
        if relative in seen:
            continue
        path = folder / relative
        if not path.is_file():
            raise _mismatch(f"The walk folder holds no file {relative}.")
        seen[relative] = None
        try:
            document = parse_document(path.read_bytes())
        except Rejection as rejection:
            if path.suffix != ".json":  # an export or a deviation file; a document may have another suffix
                continue
            raise _mismatch(f"The file {relative} of the walk folder is not readable: {rejection.message}") from None
        for reference in _artifact_nodes(document, []):
            target = (path.parent / reference["path"]).resolve()
            try:
                inner = target.relative_to(folder).as_posix()
            except ValueError:
                raise _mismatch(f"The file {relative} references a file outside the walk folder.") from None
            if not target.is_file() or sha256_file(target) != reference["sha256"]:
                raise _mismatch(f"The file {inner}, which {relative} references, is missing or has another hash.")
            pending.append(inner)
    return sorted(seen)


def same_manifest(path: Path, manifest: dict) -> bool:
    """Whether the stored manifest at ``path`` is ``manifest`` byte for byte, apart from its contract
    version: a walk folder written under an earlier version the tool reads holds the same manifest
    with that version."""
    data = path.read_bytes()
    try:
        version = parse_document(data).get("contract_version")
    except Rejection:
        return False
    return isinstance(version, str) and version in SCHEMA_FOLDERS and data == document_bytes({**manifest, "contract_version": version})


def read_walk_folder(folder: Path | str, prepared: Prepared) -> WalkFolder:
    """A walk folder that passes the reader rules of ``localise.md`` and is a reference for a
    search of ``prepared``: the same records, manifest, tolerance profile, and held kinds, and
    for every state the request the search would send on the present engine.

    Raises a :class:`Rejection` with ``walk_not_attributed`` or ``walk_mismatch``.
    """
    folder = Path(folder).resolve()
    record_path, result_path = folder / RECORD_NAME, folder / RESULT_NAME
    if not record_path.is_file() or not result_path.is_file():
        raise _mismatch(f"The folder holds no {RECORD_NAME} or no {RESULT_NAME}.")
    try:
        record = read_document(record_path, RECORD_SCHEMA, "run_record")
        result = read_document(result_path, LOCALISE_SCHEMA, "walk_result")
        for entry in record["inputs"] + record["outputs"]:  # rule 15
            check_artifact(folder, entry["artifact"])
    except Rejection as rejection:
        raise _mismatch(f"The walk folder fails a reader rule: {rejection.message}") from None
    if record["procedure"] != {"type": "walk"}:
        raise _mismatch("The run record of the folder is not that of a walk.")
    results = [entry["artifact"] for entry in record["outputs"] if entry["role"] == "result"]
    if [artifact["path"] for artifact in results] != [RESULT_NAME]:
        raise _mismatch(f"The run record of the walk does not list {RESULT_NAME} as its result.")
    if not record["stage"] == result["stage"] == prepared.stage:  # rule 16
        raise _mismatch("The walk names another stage than the two records.")
    if record["outcome"] != "attributed" or not (
            result["ends"]["zero"]["outcome"] == result["ends"]["n"]["outcome"] == "reproduced"):
        raise Rejection("walk_not_attributed", "The walk does not attribute every revision; it is no reference.")

    older, newer = prepared.older, prepared.newer
    walk_id = f"walk-{older.request['run_id']}-{newer.request['run_id']}"
    if result["walk_id"] != walk_id:
        raise _mismatch(f"The walk has the id {result['walk_id']}, not {walk_id}.")
    if record["releases"] != list(prepared.releases):  # rule 17
        raise _mismatch("The run record of the walk holds other release identities than the two records.")
    for role, recorded in (("older_record", older), ("newer_record", newer)):
        copies = [entry["artifact"] for entry in record["inputs"] if entry["role"] == role]
        if len(copies) != 1 or copies[0]["sha256"] != sha256_file(recorded.record_path):
            raise _mismatch(f"The walk was not started from the {role.split('_')[0]} record of the search.")
    manifest_path = folder / result["manifest"]["path"]
    if (not manifest_path.is_file() or sha256_file(manifest_path) != result["manifest"]["sha256"]
            or not same_manifest(manifest_path, prepared.manifest)):
        raise _mismatch("The manifest of the walk is not the one derived again.")
    if result["tolerance"] != prepared.profile:
        raise _mismatch("The walk has another tolerance profile.")
    if result["held"] != prepared.held():
        raise _mismatch("The walk holds other kinds.")

    ids = prepared.ids
    n = len(ids)
    if [state["state"] for state in result["states"]] != list(range(n + 1)):
        raise _mismatch(f"The states of the walk are not the states 0 to {n}, each once and in order.")
    for state in result["states"]:
        k = state["state"]
        if (state.get("revision") != (ids[k - 1] if k else None)
                or state["run_id"] != f"{walk_id}-state-{k}"):
            raise _mismatch(f"State {k} of the walk does not name revision {k} of the manifest and its run id.")
    if result["ends"]["zero"]["state"] != 0 or result["ends"]["n"]["state"] != n or not (
            result["states"][0]["outcome"] == result["states"][n]["outcome"] == "succeeded"):
        raise _mismatch("The ends of the walk do not agree with the outcomes of state 0 and state n.")
    ran = [state["state"] for state in result["states"] if state["outcome"] == "succeeded"]
    expected = [(a, b, ids[a:b]) for a, b in zip(ran, ran[1:])]
    if [(step["from_state"], step["to_state"], step["revisions"]) for step in result["steps"]] != expected:
        raise _mismatch("The steps of the walk do not lead from each state that ran to the next one.")

    # Same environment: the walk ran every state on the request the search would send.
    starts = [RESULT_NAME, RECORD_NAME]
    for state in result["states"]:
        k = state["state"]
        state_folder = Path(state["response"]["path"]).parent.as_posix()
        names = [f"{state_folder}/{REQUEST_NAME}", f"{state_folder}/run-record.json"]
        starts += names
        try:
            request = read_document(folder / names[0], RUN_SCHEMA, "run_request")
            state_record = read_document(folder / names[1], RECORD_SCHEMA, "run_record")
        except (OSError, Rejection):
            raise _mismatch(f"The folder of state {k} holds no readable request or run record.") from None
        release, enabled, hold, selection = state_request(prepared, k)
        changes = request.get("changes", {})
        if (request.get("release") != release or changes.get("enabled") != enabled
                or changes.get("hold") != hold or request.get("selection") != selection
                or state_record.get("releases") != [release]):
            raise _mismatch(f"State {k} of the walk ran on another request or another engine than the search "
                            "would use.")
        if "manifest" in changes:  # the enabled revisions are those of the manifest derived again
            state_manifest = (folder / state_folder / changes["manifest"]["path"]).resolve()
            if not state_manifest.is_file() or not same_manifest(state_manifest, prepared.manifest):
                raise _mismatch(f"State {k} of the walk ran on another manifest than the one derived again.")
    return WalkFolder(folder, result, record, _closure(folder, starts))
