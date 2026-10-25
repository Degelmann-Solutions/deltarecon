"""The search of ``contracts/v3/localise.md``: halving the history between two recorded results.

A search starts, as the walk does, from the records of two succeeded runs without enabled
changes, the older one first, and needs no walk. Its checks before the first run are those
of the walk (:func:`degelmann.deltarecon.walk.prepare`). It runs state 0 and state n and checks them
against the two recorded results, then halves the history for a target: the quantities
and periods asked about, by default every coordinate.

- An interval ``(a, b)`` is judged by comparing state ``a`` with state ``b`` on the target's
  coordinates only: the runs are restricted to the target periods, counted from the valuation
  date, and to the target quantities, and the tolerance profile to the entries of those
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
exports which steps change the target, and names the contributions it missed.

This module knows no engine and no kind of reference, and starts no process.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

from .compare import CheckedRun, compare_runs
from .documents import (CONTRACT_VERSION, RUN_SCHEMA, Rejection, artifact_reference, copy_files, read_document,
                        write_document)
from .replay import check_response
from .run import Engine, RunResult, UsageError, repositories_folder
from .walk import (LOCALISE_SCHEMA, MANIFEST_NAME, NEWER, OLDER, REQUEST_NAME, RESULT_NAME as WALK_RESULT_NAME,
                   Prepared, States, WalkFolder, flags, new_folder, prepare, read_walk_folder)

RESULT_NAME = "search.result.json"
RECORD_NAME = "search.run-record.json"
WALK_FOLDER = "walk"
# The checked states kept in memory at one time; the others are read again from their exports.
_CACHED = 4


# The time basis whose origin is the issue date of a model point; target periods are shifted on it.
ISSUE_ORIGIN = "policy_month"


@dataclass(frozen=True)
class Target:
    """The coordinates a search judges: quantities in the order of the response, and periods counted
    from the valuation date.

    ``offsets`` holds, on a basis whose origin is the issue date, the first period of every model point
    of the older recorded export: the period of the valuation date. ``None`` on a basis whose origin is
    the valuation date, where target periods are used as they are."""

    quantities: tuple[str, ...]
    periods: tuple[int, int] | None = None
    narrowed: bool = False  # a proper subset of the quantities or a period range was asked for
    offsets: dict[str, int] | None = field(default=None, compare=False, repr=False)

    def document(self) -> dict:
        target = {"quantities": list(self.quantities)}
        if self.periods is not None:
            target["periods"] = {"first": self.periods[0], "last": self.periods[1]}
        return target

    def projection(self, values) -> dict[tuple[str, int], int]:
        """The projection period of every coordinate of ``values``: its period counted from the valuation
        date. On a basis whose origin is the issue date the period less the model point's offset, which
        for a model point absent from the older recorded export is its first period in ``values``."""
        if self.offsets is None:
            return {key: key[1] for key in values}
        own = first_periods(values)
        return {key: key[1] - self.offsets.get(key[0], own[key[0]]) for key in values}

    def within(self, values) -> list[tuple[str, int]]:
        """The coordinates of ``values`` inside the target periods, in their order."""
        if self.periods is None:
            return list(values)
        first, last = self.periods
        projection = self.projection(values)
        return [key for key in values if first <= projection[key] <= last]


def first_periods(values) -> dict[str, int]:
    """The first period of every model point of ``values``."""
    first: dict[str, int] = {}
    for point, period in values:
        if point not in first or period < first[point]:
            first[point] = period
    return first


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
    offsets = (first_periods(prepared.older.values)
               if span is not None and prepared.older.response["time_basis"]["id"] == ISSUE_ORIGIN else None)
    chosen = tuple(name for name in names if name in asked) if asked else tuple(names)
    # A quantity list that names every quantity, without a period range, narrows nothing: the
    # search is the one without a target and keeps the signature rows of its contributions.
    narrowed = set(chosen) != set(names) or span is not None
    target = Target(chosen, span, narrowed, offsets)
    if span is not None and not any(target.within(run.values) for run in (prepared.older, prepared.newer)):
        raise UsageError(f"neither recorded export has a coordinate in the projection periods {periods}")
    return target


def restrict(checked: CheckedRun, target: Target) -> CheckedRun:
    """A run restricted to the target: the rows of the target periods, counted from the valuation date,
    and the target quantities only, in the quantity order of the response. Without a target the run
    itself."""
    if not target.narrowed:
        return checked
    quantities = checked.response["quantities"]
    keep = [i for i, quantity in enumerate(quantities) if quantity["name"] in target.quantities]
    response = {**checked.response, "quantities": [quantities[i] for i in keep]}
    values = {key: [checked.values[key][i] for i in keep] for key in target.within(checked.values)}
    return CheckedRun(response, values)


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
                 target: Target):
        super().__init__(output, engine, repositories, prepared, prefix)
        self.target = target
        self.ran: dict[int, tuple[RunResult, dict] | None] = {}  # None: the state did not run
        self.cache: OrderedDict[int, CheckedRun] = OrderedDict()
        self.intervals, self.found = [], []

    def carried(self, k: int, outcome: str) -> str:
        if k in (0, len(self.ids)):
            return f"State {k} ended with the outcome {outcome}; the search stops."
        return (f"State {k} ended with the outcome {outcome}; the search uses the nearest other state inside "
                "the interval that runs.")

    def ensure(self, k: int) -> bool:
        """Run state ``k`` unless it has run. Whether it succeeded."""
        if k not in self.ran:
            run, request = self.run_state(k)
            self.ran[k] = (run, request) if run.outcome == "succeeded" else None
        return self.ran[k] is not None

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

    def contribute(self, a: int, b: int, differs: list[str], judged: dict) -> None:
        """An interval of one revision that differs, or one without an inner state that runs."""
        revisions = self.ids[a:b]
        (left_run, _), (right_run, _) = self.ran[a], self.ran[b]
        compared = self.write_compare(f"interval-{a:0{self.width}d}-{b:0{self.width}d}.compare",
                                      f"{self.prefix}-interval-{a}-{b}",
                                      (left_run.response_path, left_run.record_path),
                                      (right_run.response_path, right_run.record_path),
                                      (self.state(a), self.state(b)))
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


def walk_changes(walk: WalkFolder, prepared: Prepared, target: Target) -> list[tuple[list[str], list[str]]]:
    """Per step of the walk: its revisions and the target quantities it changes, recomputed from the
    state exports of the walk folder under the tolerance of the walk, without a run."""
    folder, result = walk.folder, walk.result
    states = {state["state"]: state for state in result["states"]}

    def read(k: int) -> CheckedRun:
        response_path = folder / states[k]["response"]["path"]
        try:
            request = read_document(response_path.parent / REQUEST_NAME, RUN_SCHEMA, "run_request")
            response = read_document(response_path, RUN_SCHEMA, "run_response")
            if response["export"]["artifact"]["sha256"] != states[k]["export"]["sha256"]:
                raise Rejection("artifact_hash_mismatch", f"The export of state {k} is not the one of the walk result.")
            return CheckedRun(response, check_response(request, response, response_path.parent))
        except Rejection as rejection:
            raise Rejection("walk_mismatch", f"State {k} of the walk is not readable: {rejection.message}") from None

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
           periods: str | None = None, walk: Path | str | None = None) -> SearchResult:
    """Search the history between two recorded runs and write the search result into ``output``."""
    output = Path(output).resolve()
    repositories = repositories_folder(repositories)
    if output.exists():
        raise UsageError(f"{output} exists already; a search overwrites no file")
    prepared = prepare(older_record, newer_record, engine, repositories, tolerance, procedure="search")
    target = read_target(quantities, periods, prepared)
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
        state = _Search(output, engine, repositories, prepared,
                        f"search-{older.request['run_id']}-{newer.request['run_id']}", target)
        state.setup(tolerance)
        further = []
        head = {"document": "search_result", "contract_version": CONTRACT_VERSION, "stage": prepared.stage,
                "search_id": state.prefix}
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
            "runs": {"walk": n + 1, "search": len(states), "saved": n + 1 - len(states)},
        }
        if changes is not None:
            # A search that stops judges no interval; it names no missed contribution.
            searched = zero["outcome"] == last["outcome"] == "reproduced"
            result["missed"] = missed(changes, result["contributions"], target) if searched else []
        result["findings"] = state.findings
        result_path = output / RESULT_NAME
        write_document(result_path, result, LOCALISE_SCHEMA)
        outcome = "searched" if zero["outcome"] == last["outcome"] == "reproduced" else "stopped"
        record_path = state.write_record(outcome, result_path, tolerance, further)
    return SearchResult(result, result_path, record_path)
