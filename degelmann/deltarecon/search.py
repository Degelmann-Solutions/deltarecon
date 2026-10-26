"""The search of ``contracts/v3/localise.md``: halving the history between two recorded results.

A search starts, as the walk does, from the records of two succeeded runs without enabled
changes, the older one first, and needs no walk. Its checks before the first run are those
of the walk (:func:`degelmann.deltarecon.walk.prepare`). It runs state 0 and state n and checks them
against the two recorded results, then halves the history for a target: the quantities
and periods asked about, by default every coordinate.

- An interval ``(a, b)`` is judged by comparing state ``a`` with state ``b`` on the target's
  coordinates only: both runs are aligned on projection periods, as every comparison is, each
  model point counted from its own valuation date in that run, then restricted to the target
  periods and to the target quantities, and the tolerance profile to the entries of those
  quantities, so a quantity outside the target cannot change the judgement. It differs for a quantity when a coordinate of it deviates
  under the tolerance rule or a coordinate is added or removed; a comparison without the
  outcome ``compared`` differs for every quantity it judges.
- An interval whose ends agree for a quantity is not divided further for it. An interval
  ``(a, b)`` with ``b - a > 1`` is split at ``m = (a + b) // 2``, and both halves are
  judged for the quantities on which it differs, depth first, the earlier half first. A
  midpoint that does not run is replaced by the nearest state strictly inside the interval
  that runs, ``m + 1``, ``m - 1``, ``m + 2``, and so on. A state runs at most once.
- An interval of one revision that differs, or an interval in which no inner state runs,
  is a contribution: its sums run over the target's coordinates, exactly as in the walk.
  Without a target, or with a target that names every quantity and no period range, a
  contribution holds the signature row of each quantity it contributes to, and none for a
  quantity it does not contribute to.
  An interval that differs for a quantity while neither half differs for it is the finding
  ``interval_not_resolved``.

With a walk folder of the same two records the search reads it under the reader rules of a
walk folder before anything runs, copies it into ``walk/``, recomputes from its state
exports which steps change the target, and names the contributions it missed. The opt-in
switch ``reuse_walk`` takes every state the search needs from that copy instead of running
it: a reused state is no run, keeps the walk's run id, and is counted in ``runs.reused``.

The opt-in switch ``target_only`` needs a narrowed target. Every inner state the search runs
itself is then a target-only run: its request carries the target, and the engine computes the
target alone and evaluates no model check. State 0 and state n stay full runs; a reused state
stays as the walk ran it. The kept comparison of a contribution is then on the target only: a
side that is a target-only run is referenced as it is, and a full state is replaced by its
target view, ``<state>.target/``: the response and the export of the state restricted to the
target, as a target-only run of it would return them, with no run record. It is derived and is
no run. The compare request carries the tolerance profile restricted to the target quantities.

This module knows no engine and no kind of reference, and starts no process.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from .compare import ISSUE_ORIGIN, CheckedRun, align, compare_runs
from .documents import (CONTRACT_VERSION, RUN_SCHEMA, Rejection, artifact_reference, copy_files, read_document,
                        write_document, write_new)
from .export import write_export
from .replay import check_response
from .run import (EXPORT_NAME, RECORD_NAME as STATE_RECORD_NAME, RESPONSE_NAME, Engine, RunResult, UsageError,
                  repositories_folder, written_values)
from .walk import (LOCALISE_SCHEMA, MANIFEST_NAME, NEWER, OLDER, REQUEST_NAME, RESULT_NAME as WALK_RESULT_NAME,
                   Prepared, States, WalkFolder, flags, new_folder, prepare, read_walk_folder)

RESULT_NAME = "search.result.json"
RECORD_NAME = "search.run-record.json"
WALK_FOLDER = "walk"
# The opt-in switch that takes every state from the copied walk folder instead of running it.
REUSE_WALK = "reuse_walk"
# The opt-in switch that runs the inner states of the search on the target alone.
TARGET_ONLY = "target_only"
# The suffix of the folder of the target view of a full state.
VIEW_SUFFIX = ".target"
# The checked states kept in memory at one time; the others are read again from their exports.
_CACHED = 4


@dataclass(frozen=True)
class Target:
    """The coordinates a search judges: quantities in the order of the response, and projection
    periods, counted from the valuation date of each model point in each run."""

    quantities: tuple[str, ...]
    periods: tuple[int, int] | None = None
    narrowed: bool = False  # a proper subset of the quantities or a period range was asked for

    def document(self) -> dict:
        target = {"quantities": list(self.quantities)}
        if self.periods is not None:
            target["periods"] = {"first": self.periods[0], "last": self.periods[1]}
        return target

    def within(self, values) -> list[tuple[str, int]]:
        """The coordinates of ``values``, aligned on projection periods, inside the target periods,
        in their order."""
        if self.periods is None:
            return list(values)
        first, last = self.periods
        return [key for key in values if first <= key[1] <= last]


def read_target(quantities, periods: str | None, prepared: Prepared) -> Target:
    """The target of the options ``--quantity`` and ``--periods``. A fault is a usage error."""
    names = [quantity["name"] for quantity in prepared.older.response["quantities"]]
    asked = list(dict.fromkeys(quantities or []))
    unknown = [name for name in asked if name not in names]
    if unknown:
        raise UsageError(f"the older record declares no quantity {unknown[0]!r}")
    span = None
    if periods is not None:
        match = re.fullmatch(r"([0-9]+)-([0-9]+)", periods)
        if not match or int(match[1]) > int(match[2]):
            raise UsageError(f"the period range {periods!r} is not FIRST-LAST with integers 0 <= FIRST <= LAST")
        span = (int(match[1]), int(match[2]))
    chosen = tuple(name for name in names if name in asked) if asked else tuple(names)
    # A quantity list that names every quantity, without a period range, narrows nothing: the
    # search is the one without a target and keeps the signature rows of its contributions.
    narrowed = set(chosen) != set(names) or span is not None
    target = Target(chosen, span, narrowed)
    if span is not None and not any(target.within(align(CheckedRun(run.response, run.values)).values)
                                    for run in (prepared.older, prepared.newer)):
        raise UsageError(f"neither recorded export has a coordinate in the projection periods {periods}")
    return target


def restrict(checked: CheckedRun, target: Target) -> CheckedRun:
    """A run aligned on projection periods (:func:`~degelmann.deltarecon.compare.align`) and restricted
    to the target: the rows of the target periods and the target quantities only, in the quantity order
    of the response. Without a target the run itself."""
    if not target.narrowed:
        return checked
    checked = align(checked)
    quantities = checked.response["quantities"]
    keep = [i for i, quantity in enumerate(quantities) if quantity["name"] in target.quantities]
    response = {**checked.response, "quantities": [quantities[i] for i in keep]}
    values = {key: [checked.values[key][i] for i in keep] for key in target.within(checked.values)}
    return CheckedRun(response, values, aligned=True)


def restrict_profile(profile: dict, target: Target) -> dict:
    """The tolerance profile with the entries of the target quantities only. Without a target the
    profile itself."""
    if not target.narrowed:
        return profile
    return {**profile, "per_quantity": {name: entry for name, entry in profile["per_quantity"].items()
                                        if name in target.quantities}}


def judgement(stage: str, compare_id: str, profile: dict, left: CheckedRun, right: CheckedRun,
              target: Target, quantities) -> tuple[list[str], dict]:
    """The target quantities among ``quantities`` for which two states differ on the target, and the
    comparison that judges it."""
    result, deviations = compare_runs({"stage": stage, "compare_id": compare_id,
                                       "tolerance": restrict_profile(profile, target)},
                                      restrict(left, target), restrict(right, target))
    differs = flags(result, deviations, list(target.quantities))
    return [name for name, flag in zip(target.quantities, differs) if flag and name in quantities], result


@dataclass
class SearchResult:
    result: dict = field(repr=False)
    result_path: Path
    record_path: Path

    @property
    def searched(self) -> bool:
        """Both ends ran and are reproduced."""
        ends = self.result["ends"]
        return ends["zero"]["outcome"] == ends["n"]["outcome"] == "reproduced"


class _Search(States):
    """The state of one search while it writes its folder."""

    procedure = "search"
    record_name = RECORD_NAME

    def __init__(self, output: Path, engine: Engine, repositories: Path, prepared: Prepared, prefix: str,
                 target: Target, reused: list[dict] | None = None, target_only: bool = False):
        super().__init__(output, engine, repositories, prepared, prefix)
        self.target = target
        # Under the switch reuse_walk: the states of the walk result, read from the copy under walk/.
        self.reused = reused
        # Under the switch target_only: the inner states run on the target, and the target views of
        # the full states a kept comparison names, by state: the response path and the checked view.
        self.target_only = target_only
        self.views: dict[int, tuple[Path, CheckedRun]] = {}
        self.ran: dict[int, tuple[RunResult, dict] | None] = {}  # None: the state did not run
        self.cache: OrderedDict[int, CheckedRun] = OrderedDict()
        self.intervals, self.found = [], []

    def carried(self, k: int, outcome: str) -> str:
        if k in (0, len(self.ids)):
            return f"State {k} ended with the outcome {outcome}; the search stops."
        return (f"State {k} ended with the outcome {outcome}; the search uses the nearest other state inside "
                "the interval that runs.")

    def ensure(self, k: int) -> bool:
        """Run state ``k``, or under the switch reuse_walk take it from the walk, unless that is done.
        Whether it succeeded."""
        if k not in self.ran:
            inner = self.target_only and 0 < k < len(self.ids)
            run, request = (self.run_state(k, self.target.document() if inner else None) if self.reused is None
                            else self.reuse_state(k))
            self.ran[k] = (run, request) if run.outcome == "succeeded" else None
        return self.ran[k] is not None

    def reuse_state(self, k: int) -> tuple[RunResult, dict]:
        """State ``k`` as the walk ran it, read from the copy under ``walk/``: no run and no folder of
        its own. Its entry keeps the walk's run id and references the copy."""
        walked = self.reused[k]
        run, request = read_walk_state(self.output / WALK_FOLDER, walked)
        entry = {"state": k, **({"revision": walked["revision"]} if k else {}), "run_id": walked["run_id"],
                 "outcome": run.outcome, "reused": True,
                 "response": artifact_reference(self.output, run.response_path)}
        if run.outcome == "succeeded":
            entry["export"] = artifact_reference(self.output, run.export_path)
        self.states.append(entry)
        if run.outcome != "succeeded":
            self.did_not_run(k, run)
        return run, request

    def state(self, k: int) -> CheckedRun:
        """The checked values of a state that succeeded, read again when they are not cached."""
        if k in self.cache:
            self.cache.move_to_end(k)
            return self.cache[k]
        run, request = self.ran[k]
        checked = self.checked(run, request)
        self.cache[k] = checked
        while len(self.cache) > _CACHED:
            self.cache.popitem(last=False)
        return checked

    def midpoint(self, a: int, b: int) -> int | None:
        """The state the interval is split at: ``(a + b) // 2``, or the nearest state strictly inside
        that runs. ``None`` when no inner state runs."""
        m = (a + b) // 2
        for offset in range(b - a):
            for k in ((m,) if offset == 0 else (m + offset, m - offset)):
                if a < k < b and self.ensure(k):
                    return k
        return None

    def judge(self, a: int, b: int, quantities: list[str]) -> list[str]:
        """Judge the interval ``(a, b)`` for ``quantities`` and divide it where it differs."""
        differs, judged = judgement(self.stage, f"{self.prefix}-interval-{a}-{b}", self.profile,
                                    self.state(a), self.state(b), self.target, quantities)
        self.intervals.append({"from_state": a, "to_state": b, "revisions": self.ids[a:b], "differs": differs})
        if not differs:
            return differs
        m = self.midpoint(a, b) if b - a > 1 else None
        if m is None:
            self.contribute(a, b, differs, judged)
            return differs
        left = self.judge(a, m, differs)
        right = self.judge(m, b, differs)
        for name in differs:
            if name not in left and name not in right:
                self.findings.append({
                    "code": "interval_not_resolved",
                    "message": f"The interval from state {a} to state {b} differs for {name}, and neither of its "
                               f"halves at state {m} does; nothing is attributed for it.",
                    "state": b, "revisions": self.ids[a:b], "quantity": name})
        return differs

    def target_view(self, k: int) -> tuple[Path, CheckedRun]:
        """The target view of the full state ``k``, written once into ``<state>.target/``: its response and
        export restricted to the target, as a target-only run of the state returns them, in the periods of
        the time basis. A point without a period in its target window is left out. The view has no run
        record."""
        if k in self.views:
            return self.views[k]
        run, _ = self.ran[k]
        response, values = run.response, self.state(k).values
        quantities = response["quantities"]
        keep = [i for i, quantity in enumerate(quantities) if quantity["name"] in self.target.quantities]
        # The window of a point: its periods whose projection period lies in the target periods.
        issue_origin = response["time_basis"]["id"] in ISSUE_ORIGIN
        rows, ranges = [], []
        for point in response["model_points"]:
            start, end = point["first_period"], point["last_period"]
            first, last = start, end
            if self.target.periods is not None:
                offset = start if issue_origin else 0  # the period of projection period 0
                first = max(start, offset + self.target.periods[0])
                last = min(end, offset + self.target.periods[1])
            if first > last:
                continue
            identifier = point["model_point_id"]
            ranges.append({"model_point_id": identifier, "first_period": first, "last_period": last})
            rows.extend((identifier, t, [values[(identifier, t)][i] for i in keep]) for t in range(first, last + 1))
        folder = self.output / f"{self.name(k)}{VIEW_SUFFIX}"
        folder.mkdir()
        if "manifest" in response["changes"]:  # the manifest the repeated change set names, beside the view
            write_new(folder / MANIFEST_NAME, self.manifest_bytes)
        write_export(folder / EXPORT_NAME, [quantities[i]["name"] for i in keep], rows)
        view = {}
        for member, value in response.items():
            if member == "quantities":
                value = [quantities[i] for i in keep]
            elif member == "model_points":
                value = ranges
            elif member == "export":
                value = {"artifact": artifact_reference(folder, folder / EXPORT_NAME), "data_rows": len(rows)}
            view[member] = value
            if member == "selection":
                view["target"] = self.target.document()
        write_document(folder / RESPONSE_NAME, view, RUN_SCHEMA)
        self.views[k] = (folder / RESPONSE_NAME, CheckedRun(view, written_values(rows)))
        return self.views[k]

    def kept_side(self, k: int) -> tuple[tuple[Path, Path | None], CheckedRun]:
        """One side of the comparison kept for a contribution: the response and the run record of state
        ``k`` and its checked values; under the switch target_only on the target, a full state by its
        target view."""
        run, _ = self.ran[k]
        if not self.target_only or "target" in run.response:
            return (run.response_path, run.record_path), self.state(k)
        path, view = self.target_view(k)
        return (path, None), view

    def contribute(self, a: int, b: int, differs: list[str], judged: dict) -> None:
        """An interval of one revision that differs, or one without an inner state that runs."""
        revisions = self.ids[a:b]
        (left, left_checked), (right, right_checked) = self.kept_side(a), self.kept_side(b)
        compared = self.write_compare(f"interval-{a:0{self.width}d}-{b:0{self.width}d}.compare",
                                      f"{self.prefix}-interval-{a}-{b}", left, right,
                                      (left_checked, right_checked),
                                      restrict_profile(self.profile, self.target) if self.target_only else None)
        entry = {"from_state": a, "to_state": b, "revisions": revisions, "compare": self.reference(compared)}
        if judged["outcome"] != "compared":
            self.findings.append({
                "code": "step_not_compared",
                "message": f"The comparison of state {a} with state {b} on the target has the outcome "
                           f"{judged['outcome']}; the sums are kept and every quantity the interval judges differs.",
                "state": b, "revisions": revisions, "diagnostic": judged["diagnostics"][0],
                "compare": entry["compare"]})
        names = list(self.target.quantities)
        table = None if self.target.narrowed else compared.table
        entry["contributions"] = self.contributions(
            a, b, restrict(self.state(a), self.target), restrict(self.state(b), self.target), names,
            [name in differs for name in names], table)
        self.found.append(entry)

    def run(self) -> tuple[dict, dict]:
        """Run the ends and search the history. Return the two ends."""
        n = len(self.ids)
        not_run = {"state": n, "outcome": "not_run"}
        if not self.ensure(0):
            return {"state": 0, "outcome": "not_run"}, not_run
        run, _ = self.ran[0]
        zero = self.check_end(0, self.state(0), run, self.older, OLDER)
        if zero["outcome"] != "reproduced" or n == 0:
            last = self.check_end(0, self.state(0), run, self.newer, NEWER) if n == 0 else not_run
            return zero, last
        if not self.ensure(n):
            return zero, not_run
        run, _ = self.ran[n]
        last = self.check_end(n, self.state(n), run, self.newer, NEWER)
        if last["outcome"] == "reproduced":
            self.judge(0, n, list(self.target.quantities))
        return zero, last


def read_walk_state(folder: Path, state: dict, values: bool = False) -> tuple[RunResult, dict]:
    """A state of a walk result, read from the walk folder ``folder``: its run, with the paths of its
    response, run record, and export in the folder, and its request. A state that succeeded has the
    export the walk result names; with ``values`` its export is read and checked into ``run.values``.
    A state that is not readable raises ``walk_mismatch``."""
    k = state["state"]
    response_path = folder / state["response"]["path"]
    try:
        request = read_document(response_path.parent / REQUEST_NAME, RUN_SCHEMA, "run_request")
        response = read_document(response_path, RUN_SCHEMA, "run_response")
        run = RunResult(state["outcome"], response, response_path, response_path.parent / STATE_RECORD_NAME)
        if state["outcome"] == "succeeded":
            if response["export"]["artifact"]["sha256"] != state["export"]["sha256"]:
                raise Rejection("artifact_hash_mismatch", f"The export of state {k} is not the one of the walk result.")
            run.export_path = response_path.parent / response["export"]["artifact"]["path"]
            if values:
                run.values = check_response(request, response, response_path.parent)
    except Rejection as rejection:
        raise Rejection("walk_mismatch", f"State {k} of the walk is not readable: {rejection.message}") from None
    return run, request


def walk_changes(walk: WalkFolder, prepared: Prepared, target: Target) -> list[tuple[list[str], list[str]]]:
    """Per step of the walk: its revisions and the target quantities it changes, recomputed from the
    state exports of the walk folder under the tolerance of the walk, without a run."""
    folder, result = walk.folder, walk.result
    states = {state["state"]: state for state in result["states"]}

    def read(k: int) -> CheckedRun:
        run, _ = read_walk_state(folder, states[k], values=True)
        return CheckedRun(run.response, run.values)

    changes = []
    previous = None
    for step in result["steps"]:
        left = previous if previous is not None and previous[0] == step["from_state"] else (
            step["from_state"], read(step["from_state"]))
        right = (step["to_state"], read(step["to_state"]))
        differs, _ = judgement(prepared.stage, f"{result['walk_id']}-step-{step['to_state']}", prepared.profile,
                               left[1], right[1], target, target.quantities)
        changes.append((step["revisions"], differs))
        previous = right
    return changes


def missed(changes: list[tuple[list[str], list[str]]], contributions: list[dict], target: Target) -> list[dict]:
    """Per revision and target quantity: the walk shows that the step carrying the revision changes the
    target for the quantity, and no contribution of the search names that revision for it."""
    found = {(revision, contribution["quantity"]) for entry in contributions for revision in entry["revisions"]
             for contribution in entry["contributions"] if contribution["contributes"]}
    return [{"revision": revision, "quantity": name}
            for revisions, differs in changes for revision in revisions
            for name in target.quantities if name in differs and (revision, name) not in found]


def search(older_record: Path | str, newer_record: Path | str, output: Path | str, engine: Engine,
           repositories: Path | None = None, tolerance: Path | str | None = None, quantities=(),
           periods: str | None = None, walk: Path | str | None = None, reuse: bool = False,
           target_only: bool = False) -> SearchResult:
    """Search the history between two recorded runs and write the search result into ``output``.
    With ``reuse``, the switch reuse_walk, every state is taken from the copy of ``walk``. With
    ``target_only``, the switch target_only, the inner states the search runs are target-only runs."""
    if reuse and walk is None:
        raise UsageError("the switch --reuse-walk takes the states from a walk folder and needs --walk")
    output = Path(output).resolve()
    repositories = repositories_folder(repositories)
    if output.exists():
        raise UsageError(f"{output} exists already; a search overwrites no file")
    prepared = prepare(older_record, newer_record, engine, repositories, tolerance, procedure="search")
    target = read_target(quantities, periods, prepared)
    if target_only and not target.narrowed:
        raise UsageError("the switch --target-only runs the inner states on the target and needs a target "
                         "narrowed by --quantity or --periods")
    reference = changes = None
    if walk is not None:
        if not Path(walk).is_dir():
            raise UsageError(f"no walk folder at {walk}")
        reference = read_walk_folder(walk, prepared)
        changes = walk_changes(reference, prepared, target)
    older, newer = prepared.older, prepared.newer
    old_release, new_release = prepared.releases
    n = len(prepared.ids)

    with new_folder(output):
        switches = sorted(([REUSE_WALK] if reuse else []) + ([TARGET_ONLY] if target_only else []))
        state = _Search(output, engine, repositories, prepared,
                        f"search-{older.request['run_id']}-{newer.request['run_id']}", target,
                        reference.result["states"] if reuse else None, target_only)
        state.setup(tolerance)
        further = []
        head = {"document": "search_result", "contract_version": CONTRACT_VERSION, "stage": prepared.stage,
                "search_id": state.prefix, **({"switches": switches} if switches else {})}
        if reference is not None:
            copy_files(reference.folder, output / WALK_FOLDER, reference.files)  # byte copies, in their layout
            copied = output / WALK_FOLDER / WALK_RESULT_NAME
            head["walk"] = {"walk_id": reference.result["walk_id"], "result": artifact_reference(output, copied)}
            further.append({"role": "walk_result", "artifact": artifact_reference(output, copied)})
        zero, last = state.run()
        states = sorted(state.states, key=lambda entry: entry["state"])
        if reference is not None:
            assert len(reference.result["states"]) == n + 1, "a walk requests every state"
        result = {
            **head,
            "manifest": artifact_reference(output, output / MANIFEST_NAME),
            "older": {"run_id": older.request["run_id"], "release_label": old_release["label"]},
            "newer": {"run_id": newer.request["run_id"], "release_label": new_release["label"]},
            "tolerance": prepared.profile, "held": prepared.held(),
            "remainder": prepared.manifest["history"]["remainder"],
            "ends": {"zero": zero, "n": last}, "states": states, "target": target.document(),
            "intervals": state.intervals, "contributions": sorted(state.found, key=lambda e: e["from_state"]),
        }
        reused = sum(1 for entry in states if entry.get("reused"))
        ran = len(states) - reused
        result["runs"] = {"walk": n + 1, "search": ran, "saved": n + 1 - ran, **({"reused": reused} if reuse else {})}
        if changes is not None:
            # A search that stops judges no interval; it names no missed contribution.
            searched = zero["outcome"] == last["outcome"] == "reproduced"
            result["missed"] = missed(changes, result["contributions"], target) if searched else []
        result["findings"] = state.findings
        result_path = output / RESULT_NAME
        write_document(result_path, result, LOCALISE_SCHEMA)
        outcome = "searched" if zero["outcome"] == last["outcome"] == "reproduced" else "stopped"
        record_path = state.write_record(outcome, result_path, tolerance, further, switches)
    return SearchResult(result, result_path, record_path)
