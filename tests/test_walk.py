"""The walk of ``contracts/v3/localise.md``: ``degelmann/deltarecon/walk.py`` and the revision states of the adapter.

The core is tested on the stub engine with a main line of ``conftest.py``: a revision of the stub
is a folder, and ``line`` is its main line. The reference engine is tested on a throw-away
clone whose base commit shrinks the portfolio to two model points, so that every state
runs in seconds. Each row of the I/O matrix of the Story 7 plan has a test here; the rows
of the run request (prefix, hold) are in ``test_run_contract.py`` as well.
"""
from __future__ import annotations

import json
import subprocess
import sys
from fractions import Fraction
from pathlib import Path

import pytest

from degelmann.deltarecon.__main__ import main
from degelmann.deltarecon.documents import (RECORD_SCHEMA, RUN_SCHEMA, Rejection, document_bytes, read_document,
                                  schema_errors, sha256_file)
from degelmann.deltarecon.run import STAGE_QUANTITIES, UsageError, run_request
from degelmann.deltarecon.walk import exact_sums, held_kinds, walk, written

from conftest import (LAPSE_TABLE, MODEL_CODE, PARAMS, PARAMS_RATE, POINTS, POINTS_B, POINTS_E, POINT_TABLE,
                      RELEASE_N, ROOT, StubEngine, TwoStages, WalkStub, build, change, cli, clone_state, commit,
                      export_coordinates, folder_hashes, git, patch_text, record, stored, stub_request, throwaway,
                      with_manifest, write_files)

QUANTITIES = ["Anzahl Verträge", "Netto-Cashflow"]


@pytest.fixture
def linear(world):
    build(world)
    return world, record(world, "w0", label="N"), record(world, "w4", label="N+1")


def run_walk(world: Path, older: Path, newer: Path, engine=None, output: str = "walk", **options):
    return walk(older, newer, world / output, engine or WalkStub(), repositories=world, **options)


def exact_deviation(left: Path, right: Path) -> dict[str, Fraction]:
    """The sum of ``right - left`` per quantity over every coordinate, a missing one counted as 0,
    in exact arithmetic and read without ``degelmann.deltarecon``."""
    old, new = export_coordinates(left), export_coordinates(right)
    totals = {name: Fraction(0) for name in QUANTITIES}
    for key in set(old) | set(new):
        totals[key[2]] += Fraction(new.get(key, 0.0)) - Fraction(old.get(key, 0.0))
    return totals


def assert_walk_folder_valid(folder: Path) -> dict:
    """Every document validates; every state that ran holds request, response, and run record; the
    walk result references no run record and holds no path of the machine."""
    result = read_document(folder / "walk.result.json", "localise.schema.json")
    for state in result["states"]:
        state_folder = folder / Path(state["response"]["path"]).parent
        for name in ("request.json", "response.json", "run-record.json"):
            assert (state_folder / name).is_file(), state_folder / name
        assert not schema_errors(stored(state_folder / "response.json"), RUN_SCHEMA)
        assert not schema_errors(stored(state_folder / "run-record.json"), RECORD_SCHEMA)
    for path in folder.rglob("*.json"):
        document = stored(path)
        schema = {"run_request": RUN_SCHEMA, "run_response": RUN_SCHEMA, "run_record": RECORD_SCHEMA,
                  "change_manifest": "changes.schema.json", "compare_request": "compare.schema.json",
                  "compare_result": "compare.schema.json", "signature_table": "compare.schema.json",
                  "walk_result": "localise.schema.json"}.get(document.get("document"))
        if schema is not None:
            assert not schema_errors(document, schema), path
    record = read_document(folder / "walk.run-record.json", RECORD_SCHEMA)
    assert record["procedure"] == {"type": "walk"}
    for entry in record["inputs"] + record["outputs"]:
        assert sha256_file(folder / entry["artifact"]["path"]) == entry["artifact"]["sha256"]
    text = (folder / "walk.result.json").read_text("utf-8")
    assert "run-record" not in text and str(folder.parent) not in text
    references = []

    def collect(node):
        if isinstance(node, dict):
            if set(node) == {"path", "sha256"}:
                references.append(node)
            for value in node.values():
                collect(value)
        elif isinstance(node, list):
            for value in node:
                collect(value)
    collect(result)
    for reference in references:
        assert sha256_file(folder / reference["path"]) == reference["sha256"], reference["path"]
    return result


# --- the core on the stub engine ----------------------------------------------------


def test_a_linear_walk_attributes_every_revision_and_the_sums_add_up(linear, monkeypatch, capsys):
    world, older, newer = linear
    before = folder_hashes(world)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", WalkStub)
    monkeypatch.chdir(world)
    assert main(["walk", str(older), str(newer), "--output", str(world / "walk"), "--repositories", str(world)]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "walk: every revision attributed; 5 states run, 4 steps"
    assert "walk result: walk/walk.result.json" in out
    folder = world / "walk"
    result = assert_walk_folder_valid(folder)
    # The clone and the record folders are only read.
    assert {path: digest for path, digest in folder_hashes(world).items() if not path.startswith("walk/")} == before

    assert result["walk_id"] == "walk-run-w0-run-w4" and result["stage"] == "liability_cashflow"
    assert result["older"] == {"run_id": "run-w0", "release_label": "N"}
    assert result["newer"] == {"run_id": "run-w4", "release_label": "N+1"}
    assert result["ends"] == {"zero": {"state": 0, "outcome": "reproduced"},
                              "n": {"state": 4, "outcome": "reproduced"}}
    assert [s["state"] for s in result["states"]] == [0, 1, 2, 3, 4]
    assert [s.get("revision") for s in result["states"]] == [None, "w1", "w2", "w3", "w4"]
    assert [s["run_id"] for s in result["states"]] == [f"walk-run-w0-run-w4-state-{k}" for k in range(5)]
    assert all(s["outcome"] == "succeeded" for s in result["states"])
    assert [(s["from_state"], s["to_state"], s["revisions"]) for s in result["steps"]] == [
        (0, 1, ["w1"]), (1, 2, ["w2"]), (2, 3, ["w3"]), (3, 4, ["w4"])]
    assert result["held"] == [] and result["remainder"] == [] and result["unattributed"] == []
    assert result["findings"] == []
    assert result["tolerance"] == {"per_quantity": {}}

    # Per revision and quantity: contributes, the exact sums, and the signature row.
    contributes = [[c["contributes"] for c in s["contributions"]] for s in result["steps"]]
    assert contributes == [[False, True], [False, False], [True, True], [True, True]]
    assert [[c["quantity"] for c in s["contributions"]] for s in result["steps"]] == [QUANTITIES] * 4
    states = [folder / s["export"]["path"] for s in result["states"]]
    exact = []
    for step in result["steps"]:
        deviation = exact_deviation(states[step["from_state"]], states[step["to_state"]])
        exact.append(deviation)
        for contribution in step["contributions"]:
            assert contribution["sum"] == float(deviation[contribution["quantity"]])
            assert ("signature" in contribution) == contribution["contributes"]
            if "signature" in contribution:
                assert contribution["signature"]["quantity"] == contribution["quantity"]
    # The step of w4 cancels: MP-B up by 0.5 in three periods, MP-A down by 0.5 in two.
    w4 = result["steps"][3]["contributions"][0]
    assert (w4["sum"], w4["absolute_sum"]) == (0.5, 2.5)
    # The no-effect revision w2: no compare result, sums 0.
    assert "compare" not in result["steps"][1]
    assert all((c["sum"], c["absolute_sum"]) == (0, 0) for c in result["steps"][1]["contributions"])
    assert [("compare" in s) for s in result["steps"]] == [True, False, True, True]
    assert not (folder / "step-02.compare.result.json").exists() and (folder / "step-03.compare.result.json").exists()
    # Added coordinates contribute and are listed by the compare result.
    added = stored(folder / result["steps"][2]["compare"]["result"]["path"])["added"]
    assert added == [{"model_point_id": "MP-E", "first_period": 0, "last_period": 1}]
    # Additivity: the exact step sums add up to the exact deviation between the two records.
    recorded = exact_deviation(older.parent / "results.csv", newer.parent / "results.csv")
    for name in QUANTITIES:
        assert sum(step[name] for step in exact) == recorded[name]
    assert result["totals"] == [{"quantity": name, "sum": float(recorded[name])} for name in QUANTITIES]
    # Ends that are reproduced write no comparison.
    assert not list(folder.glob("state-*.check-*"))
    record = stored(folder / "walk.run-record.json")
    assert record["outcome"] == "attributed"
    assert [e["role"] for e in record["inputs"]] == ["older_record", "newer_record"]
    assert [e["role"] for e in record["outputs"]] == ["change_manifest", "result"] + ["compare_result"] * 3
    assert record["releases"] == [stored(older)["releases"][0], stored(newer)["releases"][0]]
    # Every state but state 0 holds a copy of the manifest and enables a prefix of it.
    for k in range(5):
        request = stored(folder / f"state-0{k}" / "request.json")
        assert request["changes"]["enabled"] == ["w1", "w2", "w3", "w4"][:k] and "hold" not in request["changes"]
        assert request["release"] == stored(older)["releases"][0]
        assert (folder / f"state-0{k}" / "changes.json").exists() == (k > 0)


WALK_PROCESS = """
import sys
sys.path[:0] = [sys.argv[1]]
from conftest import WalkStub
from degelmann.deltarecon.walk import walk
walk(sys.argv[2], sys.argv[3], sys.argv[4], WalkStub(), repositories=sys.argv[5])
"""


def test_the_same_records_give_the_same_walk_result_bytes_in_two_processes(linear):
    world, older, newer = linear
    for name in ("a", "b"):
        done = subprocess.run([sys.executable, "-c", WALK_PROCESS, str(ROOT / "tests"), str(older), str(newer),
                               str(world / name / "walk"), str(world)], cwd=ROOT, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
    first, second = world / "a" / "walk", world / "b" / "walk"
    assert (first / "walk.result.json").read_bytes() == (second / "walk.result.json").read_bytes()
    # Run records differ in record_id and recorded_at, and every other document is the same.
    one, two = folder_hashes(first), folder_hashes(second)
    assert set(one) == set(two)
    differing = {path for path in one if one[path] != two[path]}
    assert differing and all(path.endswith("run-record.json") or ".compare.request.json" in path
                             for path in differing)


def test_one_revision_runs_state_zero_and_checks_it_against_both_records(world):
    build(world)
    older = record(world, "w1", folder="run-a")
    newer = record(world, "w1", folder="run-b", further=[{"kind": "engine_version", "value": "2"}])
    result = run_walk(world, older, newer).result
    assert [s["state"] for s in result["states"]] == [0] and result["steps"] == []
    assert result["ends"] == {"zero": {"state": 0, "outcome": "reproduced"}, "n": {"state": 0, "outcome": "reproduced"}}
    assert result["remainder"][0]["kind"] == "engine_version"
    # Both records name one input, but no state enables a revision, so nothing is held.
    assert result["held"] == []
    assert "hold" not in stored(world / "walk" / "state-00" / "request.json")["changes"]


def test_state_zero_that_does_not_reproduce_the_older_record_stops_the_walk(linear, monkeypatch, capsys):
    world, older, newer = linear
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: WalkStub(drift={"w0": 1}))
    assert main(["walk", str(older), str(newer), "--output", str(world / "walk"), "--repositories", str(world)]) == 1
    assert "finding: state_zero_not_reproduced (state 0)" in capsys.readouterr().out
    result = assert_walk_folder_valid(world / "walk")
    assert [s["state"] for s in result["states"]] == [0] and result["steps"] == []
    assert result["ends"]["zero"]["outcome"] == "not_reproduced" and result["ends"]["n"]["outcome"] == "not_run"
    assert result["unattributed"] == ["w1", "w2", "w3", "w4"]
    check = stored(world / "walk" / result["ends"]["zero"]["compare"]["result"]["path"])
    assert check["outcome"] == "compared" and check["deviating_model_points"]
    assert [f["code"] for f in result["findings"]] == ["state_zero_not_reproduced"]
    assert stored(world / "walk" / "walk.run-record.json")["outcome"] == "not_attributed"


def test_state_zero_that_does_not_run_stops_the_walk(linear):
    world, older, newer = linear
    done = run_walk(world, older, newer, WalkStub(broken={"w0"}))
    result = done.result
    assert not done.attributed and [s["outcome"] for s in result["states"]] == ["error"]
    assert result["ends"]["zero"] == {"state": 0, "outcome": "not_run"}
    assert [f["code"] for f in result["findings"]] == ["state_did_not_run"]
    assert result["findings"][0]["diagnostic"]["code"] == "state_not_readable"
    assert result["unattributed"] == ["w1", "w2", "w3", "w4"]


def test_an_intermediate_state_that_does_not_run_is_carried_by_the_next_step(linear, monkeypatch, capsys):
    world, older, newer = linear
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: WalkStub(broken={"w2"}))
    assert main(["walk", str(older), str(newer), "--output", str(world / "walk"), "--repositories", str(world)]) == 0
    assert "finding: state_did_not_run (state 2)" in capsys.readouterr().out
    result = assert_walk_folder_valid(world / "walk")
    assert [s["outcome"] for s in result["states"]] == ["succeeded", "succeeded", "error", "succeeded", "succeeded"]
    assert [(s["from_state"], s["to_state"], s["revisions"]) for s in result["steps"]] == [
        (0, 1, ["w1"]), (1, 3, ["w2", "w3"]), (3, 4, ["w4"])]
    assert result["findings"][0]["revisions"] == ["w2"] and result["unattributed"] == []
    assert (world / "walk" / "step-03.compare.result.json").exists()


@pytest.mark.parametrize("outcome, code", [("failed", "model_point_failed"), ("rejected", "unknown_model_point")])
def test_an_intermediate_state_that_fails_or_is_rejected_is_carried_by_the_next_step(world, outcome, code):
    # State 2 either cannot calculate MP-A or lacks it; the walk selects MP-A and MP-B.
    broken = (POINTS.replace("MP-A,12,13,1.5", "MP-A,12,13,raise") if outcome == "failed"
              else POINTS.replace("MP-A,12,13,1.5\n", ""))
    line = (("v0", "", (), POINTS, PARAMS), ("v1", "Rate\n", ("parameter",), POINTS, PARAMS_RATE),
            ("v2", "Break MP-A\n", ("data",), broken, PARAMS_RATE),
            ("v3", "Repair MP-A\n", ("data",), POINTS_B, PARAMS_RATE))
    build(world, line)
    selection = {"mode": "subset", "model_point_ids": ["MP-A", "MP-B"]}
    older = record(world, "v0", WalkStub(line), selection=selection)
    newer = record(world, "v3", WalkStub(line), selection=selection)
    done = run_walk(world, older, newer, WalkStub(line))
    result = done.result
    assert done.attributed
    assert [s["outcome"] for s in result["states"]] == ["succeeded", "succeeded", outcome, "succeeded"]
    assert "export" not in result["states"][2]
    (finding,) = result["findings"]
    assert finding["code"] == "state_did_not_run" and finding["state"] == 2 and finding["revisions"] == ["v2"]
    assert finding["diagnostic"]["code"] == code and finding["diagnostic"]["model_point_ids"] == ["MP-A"]
    assert [(s["from_state"], s["to_state"], s["revisions"]) for s in result["steps"]] == [
        (0, 1, ["v1"]), (1, 3, ["v2", "v3"])]
    assert result["unattributed"] == []


@pytest.mark.parametrize("case", ["last-does-not-run", "last-not-reproduced"])
def test_a_last_state_that_does_not_run_or_reproduce_leaves_the_walk_unattributed(linear, case):
    world, older, newer = linear
    engine = WalkStub(broken={"w4"}) if case == "last-does-not-run" else WalkStub(drift={"w4": 1})
    done = run_walk(world, older, newer, engine)
    result = done.result
    assert not done.attributed
    if case == "last-does-not-run":
        assert result["ends"]["n"] == {"state": 4, "outcome": "not_run"}
        assert result["unattributed"] == ["w4"] and result["findings"][-1]["code"] == "state_did_not_run"
    else:
        assert result["ends"]["n"]["outcome"] == "not_reproduced" and result["unattributed"] == []
        assert result["findings"][-1]["code"] == "state_n_not_reproduced"
        assert (world / "walk" / "state-04.check-newer.result.json").exists()


def test_a_step_whose_comparison_is_rejected_keeps_its_sums_and_contributes(world):
    huge = "id,first,last,base\nMP-X,0,0,-1e308\nMP-Y,0,0,1e308\n"
    flipped = "id,first,last,base\nMP-X,0,0,1e308\nMP-Y,0,0,-1e308\n"
    line = (("h0", "", (), huge, PARAMS), ("h1", "Flip\n", ("data",), flipped, PARAMS))
    build(world, line)
    engine = WalkStub(line)
    older, newer = record(world, "h0", engine), record(world, "h1", engine)
    result = run_walk(world, older, newer, WalkStub(line)).result
    step = result["steps"][0]
    assert all(c["contributes"] for c in step["contributions"])
    assert all("signature" not in c for c in step["contributions"])
    assert step["contributions"][0]["sum"] == 0 and "absolute_sum" not in step["contributions"][0]
    codes = [f["code"] for f in result["findings"]]
    assert codes[0] == "step_not_compared" and "non_finite_difference" in codes
    assert result["findings"][0]["diagnostic"]["code"] == "non_finite_difference"
    assert stored(world / "walk" / step["compare"]["result"]["path"])["outcome"] == "rejected"


def test_held_input_data_runs_every_state_on_the_older_input_and_marks_the_data_revisions(world):
    # The regression case: both records name the same input data, so the stub holds it.
    line = (("g0", "", (), POINTS, PARAMS), ("g1", "New points\n", ("data",), POINTS_E, PARAMS),
            ("g2", "Rate and the old points\n", ("data", "parameter"), POINTS, PARAMS_RATE))
    build(world, line)
    older, newer = record(world, "g0", WalkStub(line)), record(world, "g2", WalkStub(line))
    done = run_walk(world, older, newer, WalkStub(line))
    result = done.result
    assert done.attributed
    assert result["held"] == [{"kind": "input_data", "classes": ["data"], "not_shown": ["g1", "g2"]}]
    request = stored(world / "walk" / "state-01" / "request.json")
    assert request["changes"]["hold"] == ["input_data"]
    # The new points of g1 are not shown: its step has no effect.
    assert [any(c["contributes"] for c in s["contributions"]) for s in result["steps"]] == [False, True]


def test_records_whose_moving_kind_does_not_match_are_refused_and_nothing_is_written(linear, monkeypatch, capsys):
    world, older, newer = linear
    (world / "w0" / "points.csv").write_text(POINTS_B, "utf-8")  # the older input is no longer that of w0
    before = folder_hashes(world)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", WalkStub)
    assert main(["walk", str(older), str(newer), "--output", str(world / "walk"), "--repositories", str(world)]) == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "walk: rejected" and "diagnostic: reference_mismatch: " in out
    assert folder_hashes(world) == before and not (world / "walk").exists()


def test_records_of_different_selections_are_refused(world):
    build(world)
    older = record(world, "w0", selection={"mode": "subset", "model_point_ids": ["MP-A"]})
    newer = record(world, "w4")
    with pytest.raises(Rejection) as caught:
        run_walk(world, older, newer)
    assert caught.value.code == "selection_mismatch" and not (world / "walk").exists()


def test_a_differing_engine_version_is_named_as_remainder(world):
    build(world)
    older = record(world, "w0", further=[{"kind": "engine_version", "value": "1.0"}])
    newer = record(world, "w4", further=[{"kind": "engine_version", "value": "1.1"}])
    done = run_walk(world, older, newer)
    assert done.attributed
    assert done.result["remainder"] == [{"kind": "engine_version",
                                         "from": [{"kind": "engine_version", "value": "1.0"}],
                                         "to": [{"kind": "engine_version", "value": "1.1"}]}]


@pytest.mark.parametrize("case, status", [("wrong-order", 1), ("stage-mismatch", 1), ("failed-run", 2),
                                          ("existing-output", 2)])
def test_what_derive_refuses_the_walk_refuses_and_no_command_overwrites(world, monkeypatch, capsys, case, status):
    build(world)
    monkeypatch.setitem(STAGE_QUANTITIES, "other_stage", STAGE_QUANTITIES["liability_cashflow"])
    older, newer = record(world, "w0", TwoStages()), record(world, "w4", TwoStages())
    if case == "wrong-order":
        older, newer = newer, older
    elif case == "stage-mismatch":
        newer = record(world, "w4", TwoStages(), folder="other", stage="other_stage")
    elif case == "failed-run":
        (world / "w0" / "points.csv").write_text(POINTS.replace("MP-B,0,2,2", "MP-B,0,2,raise"), "utf-8")
        (world / "fail").mkdir()
        request = stub_request(world, release={"label": "N", "references": StubEngine.references(world / "w0", "w0")})
        (world / "fail" / "request.json").write_bytes(document_bytes(request))
        assert run_request(world / "fail" / "request.json", TwoStages(), repositories=world).outcome == "failed"
        older = world / "fail" / "run-record.json"
    else:
        (world / "walk").mkdir()
    before = folder_hashes(world)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", TwoStages)
    assert main(["walk", str(older), str(newer), "--output", str(world / "walk"), "--repositories", str(world)]) == status
    output = capsys.readouterr()
    if status == 2:
        assert output.err.startswith("error: ")
    else:
        assert output.out.startswith("walk: rejected")
    assert folder_hashes(world) == before and (world / "walk").exists() == (case == "existing-output")


def test_an_interrupted_walk_leaves_no_folder(linear):
    world, older, newer = linear

    class Interrupting(WalkStub):
        def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
            if len(enabled) == 2:
                raise KeyboardInterrupt
            return super().open(release, enabled, manifest_dir, repositories, hold)

    with pytest.raises(KeyboardInterrupt):
        run_walk(world, older, newer, Interrupting())
    assert not (world / "walk").exists()


def test_a_tolerance_file_is_copied_listed_and_applied_to_the_ends_and_the_steps(linear):
    world, older, newer = linear
    profile = {"per_quantity": {"Netto-Cashflow": {"upper": {"abs_tol": 1000, "rel_tol": 0},
                                                   "lower": {"abs_tol": 1000, "rel_tol": 0},
                                                   "derivation": "A test bound."}}}
    (world / "tolerance.json").write_text(json.dumps(profile), "utf-8")
    done = run_walk(world, older, newer, WalkStub(drift={"w0": 0.5}), tolerance=world / "tolerance.json")
    result = done.result
    # State 0 differs by 0.5 in the counts, which have no entry: it is not reproduced.
    assert result["tolerance"] == profile and result["ends"]["zero"]["outcome"] == "not_reproduced"
    record = stored(world / "walk" / "walk.run-record.json")
    assert [e["role"] for e in record["inputs"]] == ["older_record", "newer_record", "tolerance"]
    assert (world / "walk" / "tolerance.json").read_bytes() == (world / "tolerance.json").read_bytes()


def test_exact_sums_are_exact_and_rounded_once():
    from degelmann.deltarecon.compare import CheckedRun
    names = ["Anzahl Verträge"]
    response = {"quantities": [{"name": names[0], "unit": "policies"}], "time_basis": {"id": "policy_month"}}
    left = CheckedRun(response, {("A", 0): [0.1], ("B", 0): [1e16]})
    right = CheckedRun(response, {("A", 0): [0.2], ("C", 0): [1.0]})
    signed, absolute = exact_sums(left, right, names)
    expected = Fraction(0.2) - Fraction(0.1) - Fraction(1e16) + Fraction(1.0)
    assert signed[0] == float(expected)
    assert absolute[0] == float(Fraction(0.2) - Fraction(0.1) + Fraction(1e16) + 1)
    assert written(10 ** 400 << 1074) is None


def _one_quantity(left: dict, right: dict):
    from degelmann.deltarecon.compare import CheckedRun
    response = {"quantities": [{"name": "Anzahl Verträge", "unit": "policies"}],
                "time_basis": {"id": "policy_month"}}
    return CheckedRun(response, left), CheckedRun(response, right)


def _integer_sums(left: dict, right: dict) -> tuple[float | None, float | None]:
    """The sums by the integer method: exact in units of 2**-1074, rounded once by ``written``."""
    def aligned(values: dict) -> dict:  # on policy_month: each period less its model point's first one
        first = {}
        for point, period in values:
            first[point] = min(period, first.get(point, period))
        return {(point, period - first[point]): numbers for (point, period), numbers in values.items()}

    left, right = aligned(left), aligned(right)
    signed = absolute = 0
    for key in left.keys() | right.keys():
        a, b = left.get(key, [0.0])[0], right.get(key, [0.0])[0]
        difference = Fraction(b) - Fraction(a)
        signed += difference * (1 << 1074)
        absolute += abs(difference) * (1 << 1074)
    assert signed.denominator == absolute.denominator == 1
    return written(int(signed)), written(int(absolute))


def test_fsum_gives_the_float_of_the_integer_method():
    import random
    generator = random.Random(37)
    specials = [0.0, -0.0, 5e-324, -5e-324, 2.2250738585072014e-308, 1e-310, 1e308, -1e308, 0.1, 0.2, 0.3,
                1.0, 1.0 + 2 ** -52, 2.0 ** 53, 2.0 ** 53 + 2, 0.5, 1.5, 2.5]
    for _ in range(300):
        def value():
            choice = generator.random()
            if choice < 0.3:
                return generator.choice(specials)
            if choice < 0.6:
                return generator.uniform(-1e6, 1e6)
            return generator.choice((1, -1)) * generator.random() * 10.0 ** generator.randint(-320, 300)
        keys = [(f"P{i}", t) for i in range(generator.randint(0, 4)) for t in range(generator.randint(1, 5))]
        left = {key: [value()] for key in keys if generator.random() < 0.9}
        right = {key: ([value()] if generator.random() < 0.5 else list(left.get(key, [value()])))
                 for key in keys if generator.random() < 0.9}
        signed, absolute = exact_sums(*_one_quantity(left, right), ["Anzahl Verträge"])
        expected = _integer_sums(left, right)
        assert (signed[0], absolute[0]) == expected, (left, right)
        for value_ in (signed[0], absolute[0]):
            assert value_ is None or str(value_) != "-0.0"


def test_an_exact_tie_rounds_to_even_and_a_cancellation_is_positive_zero():
    # 2**53 + 1 lies halfway between two binary64 values; the even one is 2**53.
    signed, _ = exact_sums(*_one_quantity({("A", 0): [0.0], ("B", 0): [0.0]},
                                          {("A", 0): [2.0 ** 53], ("B", 0): [1.0]}), ["Anzahl Verträge"])
    assert signed[0] == 2.0 ** 53
    signed, absolute = exact_sums(*_one_quantity({("A", 0): [0.1], ("B", 0): [0.0]},
                                                 {("A", 0): [0.0], ("B", 0): [0.1]}), ["Anzahl Verträge"])
    assert signed[0] == 0.0 and str(signed[0]) == "0.0" and absolute[0] == 0.2


def test_an_intermediate_overflow_falls_back_to_the_integer_method():
    big = 1.7976931348623157e308
    # The terms overflow in fsum, the exact sum is 0 and finite: 2 * big - 2 * big.
    left = {("A", 0): [-big], ("B", 0): [big]}
    right = {("A", 0): [big], ("B", 0): [-big]}
    with pytest.raises(OverflowError):
        import math
        math.fsum([big, big, -big, -big])
    signed, absolute = exact_sums(*_one_quantity(left, right), ["Anzahl Verträge"])
    assert signed[0] == 0.0 and absolute[0] is None


def test_a_final_overflow_is_not_written():
    big = 1.7976931348623157e308
    signed, absolute = exact_sums(*_one_quantity({("A", 0): [-big]}, {("A", 0): [big]}), ["Anzahl Verträge"])
    assert signed == [None] and absolute == [None]


def test_only_a_determined_kind_is_held():
    """A kind no revision determines never moves, so the walk does not hold it."""
    same = [{"kind": "input_data", "value": "points"}, {"kind": "calendar", "value": "2026"}]
    identity = {"label": "N", "references": same}
    holdable = {"input_data": frozenset({"data"}), "calendar": frozenset({"data"})}
    assert held_kinds(identity, identity, holdable, frozenset({"input_data", "release_folder"})) == ["input_data"]

def test_walk_names_no_kind_of_reference():
    text = (ROOT / "degelmann" / "deltarecon" / "walk.py").read_text("utf-8")
    for kind in ("input_data", "code_state", "parameter_set", "engine_version", "release_folder"):
        assert kind not in text, kind


# --- the run request: a prefix of revisions and held kinds ---------------------------


def revision_manifest(world: Path, ids, folder: str = "run") -> dict:
    """Store a manifest of revisions beside the request, as ``derive`` writes it."""
    entries = [{"id": i, "class": [], "description": i, "prerequisites": ids[k - 1:k] if k else [],
                "conflicts": [], "realisation": {"type": "revision", "source": "git", "revision": i}}
               for k, i in enumerate(ids)]
    history = {"source": "git", "from": "rel", "to": ids[-1], "determines": ["input_data", "release_folder"],
               "remainder": []}
    return with_manifest(world, entries, [], folder, history=history)


def test_a_prefix_of_revisions_restores_the_last_one_and_a_skipped_one_is_unmet(world):
    build(world)
    changes = revision_manifest(world, ["w1", "w2", "w3"])
    request = stub_request(world, changes={**changes, "enabled": ["w2", "w1"]})
    path = world / "run" / "request.json"
    path.write_bytes(document_bytes(request))
    engine = WalkStub()
    assert run_request(path, engine, repositories=world).outcome == "succeeded"
    assert [c["id"] for c in engine.received] == ["w1", "w2"]
    (world / "skip").mkdir()
    changes = revision_manifest(world, ["w1", "w2", "w3"], "skip")
    (world / "skip" / "request.json").write_bytes(document_bytes(
        stub_request(world, changes={**changes, "enabled": ["w1", "w3"]})))
    result = run_request(world / "skip" / "request.json", WalkStub(), repositories=world)
    assert result.outcome == "rejected"
    assert result.response["diagnostics"][0] == {"code": "unmet_prerequisite", "message": result.response[
        "diagnostics"][0]["message"], "change_ids": ["w3"]}


@pytest.mark.parametrize("case", ["kind-not-holdable", "no-revision-enabled", "nothing-enabled"])
def test_a_hold_the_engine_cannot_honour_is_rejected(world, case):
    build(world)
    if case == "kind-not-holdable":
        changes = {**revision_manifest(world, ["w1"]), "enabled": ["w1"], "hold": ["release_folder"]}
    elif case == "no-revision-enabled":
        entries = [change("chg-point-b", patch_text("points.csv", POINTS, POINTS_B), world / "run")]
        changes = {**with_manifest(world, entries, ["chg-point-b"]), "hold": ["input_data"]}
    else:
        changes = {"enabled": [], "hold": ["input_data"]}
    path = world / "run" / "request.json"
    path.write_bytes(document_bytes(stub_request(world, changes=changes)))
    engine = WalkStub()
    result = run_request(path, engine, repositories=world)
    assert result.outcome == "rejected" and result.response["diagnostics"][0]["code"] == "invalid_hold"
    assert engine.opened == 0


def test_a_held_kind_is_passed_to_the_engine_and_repeated_by_the_response(world):
    build(world)
    changes = {**revision_manifest(world, ["w1", "w2", "w3"]), "enabled": ["w1", "w2", "w3"],
               "hold": ["input_data"]}
    path = world / "run" / "request.json"
    path.write_bytes(document_bytes(stub_request(world, changes=changes)))
    engine = WalkStub()
    result = run_request(path, engine, repositories=world)
    assert result.outcome == "succeeded" and engine.held == {"input_data"}
    assert result.response["changes"]["hold"] == ["input_data"]
    # The points are those of the release of the request, so MP-E of w3 is not there.
    assert [p["model_point_id"] for p in result.response["model_points"]] == ["MP-A", "MP-B", "MP-C", "MP-D"]


# --- the reference engine on a throw-away clone -------------------------------------


@pytest.fixture(scope="module")
def adapter_walk(tmp_path_factory):
    """A throw-away clone with five revisions after a base of two model points, the records of a
    full run of the base and of the newest revision, and the walk between them.

    Revision 2 breaks the model and revision 3 repairs it; revision 4 empties the model point
    table and revision 5 holds three model points, one of them new.
    """
    tmp = tmp_path_factory.mktemp("walk-chain")
    repositories, clone = throwaway(tmp)
    lines = (clone / POINT_TABLE).read_text("utf-8").splitlines(keepends=True)
    header, rows = lines[0], lines[1:]
    write_files(clone, {POINT_TABLE: header + rows[0] + rows[1]})
    base = commit(clone, "Keep two model points")
    lapse = (clone / LAPSE_TABLE).read_text("utf-8")
    assert "\n1,0.06," in lapse
    write_files(clone, {LAPSE_TABLE: lapse.replace("\n1,0.06,", "\n1,0.05,")})
    revisions = [commit(clone, "Lower the lapse rate of policy year 1")]
    code = (clone / MODEL_CODE).read_text("utf-8")
    write_files(clone, {MODEL_CODE: "this is not a model (\n"})
    revisions.append(commit(clone, "Break the model"))
    write_files(clone, {MODEL_CODE: code})
    revisions.append(commit(clone, "Repair the model"))
    write_files(clone, {POINT_TABLE: header})
    revisions.append(commit(clone, "Empty the model point table"))
    columns = header.strip().split(",")
    third = rows[2].strip().split(",")
    third[columns.index("policy_id")] = "RLV-NEW-1"
    write_files(clone, {POINT_TABLE: header + rows[0] + rows[1] + ",".join(third) + "\n"})
    revisions.append(commit(clone, "Add a model point"))
    records = {}
    for name, revision in (("older", base), ("newer", revisions[-1])):
        folder = tmp / name
        assert main(["request", "--revision", revision, "--repositories", str(repositories), "--label", name,
                     "--run-id", f"run-{name}", "--output", str(folder / "request.json")]) == 0
        assert main(["run", str(folder / "request.json"), "--repositories", str(repositories)]) == 0
        records[name] = folder / "run-record.json"
    state = clone_state(clone)
    before = {name: folder_hashes(path.parent) for name, path in records.items()}
    done = subprocess.run([sys.executable, "-m", "degelmann.deltarecon", "walk", str(records["older"]), str(records["newer"]),
                           "--output", str(tmp / "walk"), "--repositories", str(repositories)],
                          cwd=ROOT, capture_output=True, text=True)
    return {"tmp": tmp, "repositories": repositories, "clone": clone, "records": records, "base": base,
            "revisions": revisions, "done": done, "state": state, "before": before}


def test_the_reference_engine_walks_states_that_break_lose_and_add_model_points(adapter_walk):
    done, tmp, revisions = adapter_walk["done"], adapter_walk["tmp"], adapter_walk["revisions"]
    assert done.returncode == 0, done.stdout + done.stderr
    result = assert_walk_folder_valid(tmp / "walk")
    assert [s["outcome"] for s in result["states"]] == ["succeeded", "succeeded", "error", "succeeded", "error",
                                                       "succeeded"]
    assert [result["findings"][i]["diagnostic"]["code"] for i in (0, 1)] == ["state_not_readable", "no_model_point"]
    assert [(s["from_state"], s["to_state"]) for s in result["steps"]] == [(0, 1), (1, 3), (3, 5)]
    assert result["steps"][1]["revisions"] == revisions[1:3]
    assert not any(c["contributes"] for c in result["steps"][1]["contributions"])  # broken and repaired
    assert all(c["contributes"] for c in result["steps"][2]["contributions"])  # a model point is added
    added = stored(tmp / "walk" / result["steps"][2]["compare"]["result"]["path"])["added"]
    assert [entry["model_point_id"] for entry in added] == ["RLV-NEW-1"]
    assert result["ends"]["zero"]["outcome"] == result["ends"]["n"]["outcome"] == "reproduced"
    assert result["held"] == [] and result["unattributed"] == []
    # Additivity in exact arithmetic against the deviation between the two records.
    states = {s["state"]: tmp / "walk" / s["export"]["path"] for s in result["states"] if "export" in s}
    older, newer = adapter_walk["records"]["older"].parent, adapter_walk["records"]["newer"].parent
    recorded = exact_deviation_all(older / "results.csv", newer / "results.csv")
    steps = [exact_deviation_all(states[s["from_state"]], states[s["to_state"]]) for s in result["steps"]]
    for name in recorded:
        assert sum(step[name] for step in steps) == recorded[name], name
    for step, exact in zip(result["steps"], steps):
        for contribution in step["contributions"]:
            assert contribution["sum"] == float(exact[contribution["quantity"]])
    # The clone and the record folders are as they were.
    assert clone_state(adapter_walk["clone"]) == adapter_walk["state"]
    assert {n: folder_hashes(p.parent) for n, p in adapter_walk["records"].items()} == adapter_walk["before"]


def exact_deviation_all(left: Path, right: Path) -> dict[str, Fraction]:
    old, new = export_coordinates(left), export_coordinates(right)
    totals: dict[str, Fraction] = {}
    for key in set(old) | set(new):
        totals[key[2]] = totals.get(key[2], Fraction(0)) + Fraction(new.get(key, 0.0)) - Fraction(old.get(key, 0.0))
    return totals


def test_an_enabled_prefix_on_the_reference_engine_is_the_state_of_its_last_revision(adapter_walk, monkeypatch):
    tmp, revisions = adapter_walk["tmp"], adapter_walk["revisions"]
    folder = tmp / "direct"
    assert cli(monkeypatch, "request", "--revision", revisions[0], "--repositories", adapter_walk["repositories"],
               "--label", "direct", "--run-id", "direct", "--output", folder / "request.json") == 0
    assert cli(monkeypatch, "run", folder / "request.json", "--repositories", adapter_walk["repositories"]) == 0
    assert (folder / "results.csv").read_bytes() == (tmp / "walk" / "state-01" / "results.csv").read_bytes()
    response = stored(tmp / "walk" / "state-01" / "response.json")
    assert response["changes"]["enabled"] == revisions[:1] and "hold" not in response["changes"]


def test_a_regression_pair_holds_the_input_data_on_the_reference_engine(adapter_walk, monkeypatch, capsys):
    tmp, repositories, revisions = adapter_walk["tmp"], adapter_walk["repositories"], adapter_walk["revisions"]
    older = adapter_walk["records"]["older"]
    assert cli(monkeypatch, "regression", older, "--revision", revisions[-1], "--repositories", repositories,
               "--output", tmp / "regression") == 1
    newer = tmp / "regression" / "run" / "run-record.json"
    capsys.readouterr()
    assert cli(monkeypatch, "walk", older, newer, "--repositories", repositories, "--output", tmp / "held") == 0
    out = capsys.readouterr().out
    assert "held: input_data; the effect on it of 2 revisions is not shown" in out
    result = assert_walk_folder_valid(tmp / "held")
    assert result["held"] == [{"kind": "input_data", "classes": ["data"], "not_shown": revisions[3:]}]
    # With the input data held, the empty model point table of revision 4 is not restored.
    assert [s["outcome"] for s in result["states"]] == ["succeeded", "succeeded", "error", "succeeded", "succeeded",
                                                       "succeeded"]
    assert stored(tmp / "held" / "state-04" / "request.json")["changes"]["hold"] == ["input_data"]


def test_records_with_two_different_foreign_input_data_commits_are_refused(adapter_walk, monkeypatch, capsys):
    tmp, repositories, revisions = adapter_walk["tmp"], adapter_walk["repositories"], adapter_walk["revisions"]
    # The older record runs the base on the input data of release N, the newer one revision 1 on
    # its own: the input data moves, and the base revision does not name what the older record names.
    assert cli(monkeypatch, "request", "--revision", RELEASE_N, "--repositories", repositories, "--label", "n",
               "--run-id", "run-n", "--output", tmp / "n" / "request.json") == 0
    capsys.readouterr()
    state = clone_state(adapter_walk["clone"])
    request = stored(tmp / "n" / "request.json")
    for reference in request["release"]["references"]:
        if reference["kind"] in ("code_state", "parameter_set"):
            reference["value"] = reference["value"].replace(RELEASE_N, adapter_walk["base"])
    request["selection"] = {"mode": "subset", "model_point_ids": [first_point(adapter_walk)]}
    (tmp / "foreign").mkdir()
    (tmp / "foreign" / "request.json").write_bytes(document_bytes(request))
    assert cli(monkeypatch, "run", tmp / "foreign" / "request.json", "--repositories", repositories) == 0
    newer = record_regression(monkeypatch, tmp, repositories, revisions[0])
    capsys.readouterr()
    assert cli(monkeypatch, "walk", tmp / "foreign" / "run-record.json", newer, "--repositories", repositories,
               "--output", tmp / "refused") == 1
    out = capsys.readouterr().out
    assert "diagnostic: reference_mismatch: " in out and not (tmp / "refused").exists()
    assert clone_state(adapter_walk["clone"]) == state


def first_point(adapter_walk) -> str:
    lines = git(adapter_walk["clone"], "show", f"{adapter_walk['base']}:{POINT_TABLE}").decode("utf-8").splitlines()
    columns = lines[0].split(",")
    return lines[1].split(",")[columns.index("policy_id")]


def record_regression(monkeypatch, tmp: Path, repositories: Path, revision: str) -> Path:
    """A run of ``revision`` on its own input data and the subset of one model point."""
    folder = tmp / "own"
    request = stored(tmp / "foreign" / "request.json")
    for reference in request["release"]["references"]:
        if reference["kind"] != "engine_version":
            reference["value"] = reference["value"].rsplit("@", 1)[0] + "@" + revision
    request["run_id"] = "run-own"
    folder.mkdir()
    (folder / "request.json").write_bytes(document_bytes(request))
    assert cli(monkeypatch, "run", folder / "request.json", "--repositories", repositories) == 0
    return folder / "run-record.json"


def test_a_shallow_clone_does_not_start_the_walk(adapter_walk, tmp_path):
    shallow = tmp_path / "shallow"
    shallow.mkdir()
    git(tmp_path, "clone", "--quiet", "--depth", "1", "--branch", "work", adapter_walk["clone"].as_uri(),
        str(shallow / "delib-history"))
    records = adapter_walk["records"]
    done = subprocess.run([sys.executable, "-m", "degelmann.deltarecon", "walk", str(records["older"]), str(records["newer"]),
                           "--output", str(tmp_path / "walk"), "--repositories", str(shallow)],
                          cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 2 and "cut off" in done.stderr and not (tmp_path / "walk").exists()


def test_usage_errors_are_usage_errors(world):
    with pytest.raises(UsageError):
        walk(world / "absent.json", world / "absent.json", world / "walk", WalkStub(), repositories=world)


@pytest.mark.parametrize("drift", [None, {"w4": 0.5}])
def test_a_walk_reads_no_state_export_and_writes_the_same_folder(linear, monkeypatch, drift):
    """The states hand their values to the walk in memory: only the two recorded exports are read,
    and the folder is the one of a walk that reads every export back."""
    from degelmann.deltarecon import compare as compare_module, export, replay, run, walk as walk_module
    world, older, newer = linear
    read = []
    plain = export.check_export

    def counting(response, path):
        read.append(Path(path))
        return plain(response, path)

    monkeypatch.setattr(replay, "check_export", counting)
    monkeypatch.setattr(compare_module, "check_export", counting)
    memory = run_walk(world, older, newer, WalkStub(drift=drift), output="memory/walk").result
    assert sorted(read) == sorted([older.parent / "results.csv", newer.parent / "results.csv"])
    assert (memory["ends"]["n"]["outcome"] == "reproduced") == (drift is None)

    # The same walk with every value read back from the exports and every comparison reading both runs.
    monkeypatch.setattr(run, "written_values", lambda rows: None)
    plain_compare = compare_module.compare
    monkeypatch.setattr(walk_module, "compare", lambda *arguments, runs=None, **options: plain_compare(
        *arguments, **options))
    run_walk(world, older, newer, WalkStub(drift=drift), output="files/walk")
    assert len(read) > 2
    first, second = world / "memory" / "walk", world / "files" / "walk"
    assert (first / "walk.result.json").read_bytes() == (second / "walk.result.json").read_bytes()
    one, two = folder_hashes(first), folder_hashes(second)
    assert set(one) == set(two)
    # Run records differ in record_id and recorded_at, and so do the compare requests that name them.
    assert all(path.endswith("run-record.json") or (path.endswith(".request.json") and "/" not in path)
               for path in one if one[path] != two[path])
