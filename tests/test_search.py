"""The search of ``contracts/v3/localise.md``: ``degelmann/deltarecon/search.py`` and its check against the walk.

The core is tested on the stub engine with a main line of ``conftest.py``: a revision of the
stub is a folder, and ``line`` is its main line. The quantities of the stub are ``Anzahl Verträge``, the
column ``base`` of a model point in every period, and ``Netto-Cashflow``, which also
depends on the parameter ``rate``. The cancelling pair is also run on the reference engine,
on a throw-away clone of two model points. Each row of the I/O matrix of the Story 8 plan
has a test here.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from contextlib import contextmanager
from fractions import Fraction
from pathlib import Path

import pytest

from degelmann.deltarecon.__main__ import main
from degelmann.deltarecon.documents import (RECORD_SCHEMA, RUN_SCHEMA, Rejection, document_bytes, read_document,
                                  schema_errors, sha256_file)
from degelmann.deltarecon.run import STAGE_QUANTITIES, UsageError, run_request
from degelmann.deltarecon.search import Target, read_target, restrict, search, walk_changes
from degelmann.deltarecon.walk import prepare, read_walk_folder, walk

from conftest import (CANCEL, CASH, HISTORY, LAPSE_TABLE, LINE, PARAMS, PARAMS_RATE, POINTS, POINTS_B,
                      POINT_TABLE, ROOT, StubEngine, TwoStages, WalkStub, build, clone_state, commit,
                      export_coordinates, folder_hashes, projection_periods, record, stored, stub_request, throwaway,
                      write_files, written_under)

COUNT = "Anzahl Verträge"
PROFILE = {"per_quantity": {COUNT: {"upper": {"abs_tol": 0.01, "rel_tol": 0}, "lower": {"abs_tol": 0.01, "rel_tol": 0},
                                    "derivation": "A test bound of 0.01 policies."}}}


@pytest.fixture
def history(world):
    build(world, HISTORY)
    (world / "tolerance.json").write_text(json.dumps(PROFILE), "utf-8")
    engine = WalkStub(HISTORY)
    return world, record(world, "h0", engine, label="N"), record(world, "h8", engine, label="N+1")


@pytest.fixture
def cancel(world):
    build(world, CANCEL)
    engine = WalkStub(CANCEL)
    return world, record(world, "c0", engine, label="N"), record(world, "c4", engine, label="N+1")


def run_search(world: Path, older: Path, newer: Path, engine, output: str = "search", **options):
    return search(older, newer, world / output, engine, repositories=world, **options)


def run_walk(world: Path, older: Path, newer: Path, engine, output: str = "walk", **options):
    return walk(older, newer, world / output, engine, repositories=world, **options)


def references(node, found=None) -> list[dict]:
    """Every artifact reference of a document outside the release identities."""
    found = [] if found is None else found
    if isinstance(node, dict):
        if set(node) == {"path", "sha256"}:
            found.append(node)
        for key, value in node.items():
            if key not in ("release", "releases"):
                references(value, found)
    elif isinstance(node, list):
        for value in node:
            references(value, found)
    return found


def assert_references_resolve(folder: Path) -> None:
    """Every artifact reference of every document below ``folder`` resolves with its hash."""
    for path in folder.rglob("*.json"):
        for reference in references(stored(path)):
            target = path.parent / reference["path"]
            assert target.is_file() and sha256_file(target) == reference["sha256"], (path, reference["path"])


def assert_search_folder_valid(folder: Path) -> dict:
    """Every document validates; every state that ran holds request, response, export, and record;
    the search result references no run record and holds no path of the machine."""
    result = read_document(folder / "search.result.json", "localise.schema.json", "search_result")
    for state in result["states"]:
        state_folder = folder / Path(state["response"]["path"]).parent
        for name in ("request.json", "response.json", "run-record.json"):
            assert (state_folder / name).is_file(), state_folder / name
        assert (state_folder / "results.csv").is_file() == (state["outcome"] == "succeeded")
        assert not schema_errors(stored(state_folder / "run-record.json"), RECORD_SCHEMA)
    for path in folder.rglob("*.json"):
        document = stored(path)
        schema = {"run_request": RUN_SCHEMA, "run_response": RUN_SCHEMA, "run_record": RECORD_SCHEMA,
                  "change_manifest": "changes.schema.json", "compare_request": "compare.schema.json",
                  "compare_result": "compare.schema.json", "signature_table": "compare.schema.json",
                  "walk_result": "localise.schema.json", "search_result": "localise.schema.json"}.get(
            document.get("document"))
        if schema is not None:
            assert not schema_errors(document, schema), path
    record = read_document(folder / "search.run-record.json", RECORD_SCHEMA)
    assert record["procedure"] == {"type": "search"}
    for entry in record["inputs"] + record["outputs"]:
        assert sha256_file(folder / entry["artifact"]["path"]) == entry["artifact"]["sha256"]
    text = (folder / "search.result.json").read_text("utf-8")
    assert "run-record" not in text and str(folder.parent) not in text
    assert_references_resolve(folder)
    return result


def exact(left: Path, right: Path, quantities, periods=None) -> dict[str, Fraction]:
    """The sum of ``right - left`` per quantity over the coordinates of a target, read without ``degelmann.deltarecon``.

    Target periods are projection periods: on ``policy_month`` a period less the first period of its model
    point in the same export."""
    def kept(coordinates) -> dict:
        return {key: value for key, value in projection_periods(coordinates).items() if key[2] in quantities and (
            periods is None or periods[0] <= key[1] <= periods[1])}

    old, new = kept(export_coordinates(left)), kept(export_coordinates(right))
    totals = {name: Fraction(0) for name in quantities}
    for key in set(old) | set(new):
        totals[key[2]] += Fraction(new.get(key, 0.0)) - Fraction(old.get(key, 0.0))
    return totals


# --- the targeted search and its check against the walk -------------------------------


def test_a_targeted_search_saves_runs_and_names_what_it_missed(history, monkeypatch, capsys):
    world, older, newer = history
    assert run_walk(world, older, newer, WalkStub(HISTORY), tolerance=world / "tolerance.json").attributed
    before = folder_hashes(world)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: WalkStub(HISTORY))
    monkeypatch.chdir(world)
    assert main(["search", str(older), str(newer), "--output", str(world / "search"), "--repositories", str(world),
                 "--quantity", COUNT, "--periods", "0-2", "--tolerance", str(world / "tolerance.json"),
                 "--walk", str(world / "walk")]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "search: searched; 6 states run, 9 for a walk, 3 saved"
    assert "search result: search/search.result.json" in out and "  missed: " in out
    # The record folders and the walk folder are only read.
    assert {p: d for p, d in folder_hashes(world).items() if not p.startswith("search/")} == before
    folder = world / "search"
    result = assert_search_folder_valid(folder)
    assert result["search_id"] == "search-run-h0-run-h8" and result["target"] == {
        "quantities": [COUNT], "periods": {"first": 0, "last": 2}}
    assert result["walk"]["walk_id"] == "walk-run-h0-run-h8"
    assert result["runs"] == {"walk": 9, "search": 6, "saved": 3}
    assert [s["state"] for s in result["states"]] == [0, 4, 5, 6, 7, 8]
    assert [s["run_id"] for s in result["states"]][0] == "search-run-h0-run-h8-state-0"
    # Pre-order, the earlier half first; an interval whose ends agree is not divided.
    assert [(i["from_state"], i["to_state"], i["differs"]) for i in result["intervals"]] == [
        (0, 8, [COUNT]), (0, 4, []), (4, 8, [COUNT]), (4, 6, [COUNT]), (4, 5, []), (5, 6, []),
        (6, 8, [COUNT]), (6, 7, [COUNT]), (7, 8, [])]
    (found,) = result["contributions"]
    assert (found["from_state"], found["to_state"], found["revisions"]) == (6, 7, ["h7"])
    assert found["contributions"] == [{"quantity": COUNT, "contributes": True, "sum": 14.0, "absolute_sum": 14.0}]
    assert (folder / "interval-06-07.compare.result.json").is_file()
    # The offsetting pair and the revert pair are missed; the sub-tolerance pair is not resolved.
    assert result["missed"] == [{"revision": name, "quantity": COUNT} for name in ("h1", "h2", "h3", "h4")]
    (finding,) = result["findings"]
    assert finding["code"] == "interval_not_resolved" and finding["revisions"] == ["h5", "h6"]
    assert finding["quantity"] == COUNT and finding["state"] == 6
    # Every contribution found equals the walk's step on the target.
    walked = stored(world / "walk" / "walk.result.json")
    step = next(s for s in walked["steps"] if s["revisions"] == ["h7"])
    exports = {s["state"]: world / "walk" / s["export"]["path"] for s in walked["states"]}
    assert float(exact(exports[6], exports[7], [COUNT], (0, 2))[COUNT]) == found["contributions"][0]["sum"]
    assert next(c for c in step["contributions"] if c["quantity"] == COUNT)["contributes"]
    # The walk is copied with what it references, and listed as an input.
    record = stored(folder / "search.run-record.json")
    assert [e["role"] for e in record["inputs"]] == ["older_record", "newer_record", "tolerance", "walk_result"]
    assert [e["role"] for e in record["outputs"]] == ["change_manifest", "result", "compare_result"]
    assert record["outcome"] == "searched" and record["releases"] == [stored(older)["releases"][0],
                                                                       stored(newer)["releases"][0]]
    assert (folder / "walk" / "walk.result.json").read_bytes() == (world / "walk" / "walk.result.json").read_bytes()
    assert (folder / "walk" / "state-03" / "request.json").is_file()
    assert (folder / "walk" / "state-03" / "run-record.json").is_file()


def test_without_a_target_and_without_a_walk_the_search_has_no_missed(history):
    world, older, newer = history
    result = run_search(world, older, newer, WalkStub(HISTORY), tolerance=world / "tolerance.json").result
    assert "walk" not in result and "missed" not in result
    assert result["target"] == {"quantities": [COUNT, CASH]}
    assert result["runs"]["walk"] == 9 and result["runs"]["saved"] == 9 - len(result["states"])
    # The cash flow has no tolerance entry, so the small raises of h5 and h6 contribute to it.
    assert [c["revisions"] for c in result["contributions"]] == [["h5"], ["h6"], ["h7"], ["h8"]]
    # Without a target a contribution holds its signature row, as a walk step.
    assert all(c["contributes"] for e in result["contributions"] for c in e["contributions"] if "signature" in c)
    assert any("signature" in c for e in result["contributions"] for c in e["contributions"])


def test_every_contribution_found_without_a_target_equals_the_walk_step(cancel):
    world, older, newer = cancel
    run_walk(world, older, newer, WalkStub(CANCEL))
    result = run_search(world, older, newer, WalkStub(CANCEL), walk=world / "walk").result
    steps = {tuple(s["revisions"]): s for s in stored(world / "walk" / "walk.result.json")["steps"]}
    assert result["contributions"]
    for entry in result["contributions"]:
        step = steps[tuple(entry["revisions"])]
        assert entry["contributions"] == step["contributions"]


def test_the_cancelling_pair_is_missed_and_the_contribution_found(cancel, monkeypatch, capsys):
    world, older, newer = cancel
    run_walk(world, older, newer, WalkStub(CANCEL))
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: WalkStub(CANCEL))
    assert main(["search", str(older), str(newer), "--output", str(world / "search"), "--repositories", str(world),
                 "--walk", str(world / "walk")]) == 0
    result = assert_search_folder_valid(world / "search")
    assert [c["revisions"] for c in result["contributions"]] == [["c3"]]
    # A moves only the cash flow, and so does its revert B.
    assert result["missed"] == [{"revision": "c1", "quantity": CASH}, {"revision": "c2", "quantity": CASH}]
    assert result["runs"]["saved"] >= 1
    # No-effect interval: the interval of D is judged, not divided, and not found; the walk has no miss there.
    assert {"from_state": 3, "to_state": 4, "revisions": ["c4"], "differs": []} in result["intervals"]
    assert "c4" not in {m["revision"] for m in result["missed"]}


# Target {count, cash} in projection period 2, which only MP-B reaches: t1 moves the cash flow; t2
# raises MP-B and t3 lowers it again, so the counts of (0, 4) agree and the halves are judged for the
# cash flow alone; t4 moves MP-A outside the target, so that the input data move with the states.
POINTS_A = POINTS.replace("MP-A,12,13,1.5", "MP-A,12,13,2")
TWO = (
    ("t0", "The base.\n", (), POINTS, PARAMS),
    ("t1", "Raise the rate\n", ("parameter",), POINTS, PARAMS_RATE),
    ("t2", "Raise MP-B\n", ("data",), POINTS_B, PARAMS_RATE),
    ("t3", "Lower MP-B again\n", ("data",), POINTS, PARAMS_RATE),
    ("t4", "Raise MP-A\n", ("data",), POINTS_A, PARAMS_RATE),
)


def test_a_quantity_that_cancels_in_a_parent_interval_is_not_judged_in_its_halves(world):
    build(world, TWO)
    engine = WalkStub(TWO)
    older, newer = record(world, "t0", engine, label="N"), record(world, "t4", engine, label="N+1")
    run_walk(world, older, newer, WalkStub(TWO))
    result = run_search(world, older, newer, WalkStub(TWO), quantities=[COUNT, CASH], periods="2-2",
                        walk=world / "walk").result
    assert [(i["from_state"], i["to_state"], i["differs"]) for i in result["intervals"]][:3] == [
        (0, 4, [CASH]), (0, 2, [CASH]), (0, 1, [CASH])]
    # The halves of (0, 4) are judged for the cash flow only: t2 contributes to it, not to the count,
    # although its sum of the count is written and is not zero.
    t2 = next(e for e in result["contributions"] if e["revisions"] == ["t2"])
    count = next(c for c in t2["contributions"] if c["quantity"] == COUNT)
    assert not count["contributes"] and count["sum"] != 0
    # The walk shows that t2 and t3 change the count, so both are missed for it.
    assert result["missed"] == [{"revision": "t2", "quantity": COUNT}, {"revision": "t3", "quantity": COUNT}]


# The count moves with s1 and back with s3, so it cancels over the outer interval (0, 3); the cash flow
# moves with every revision, and so does it over (0, 3). s3 writes the old base of MP-B as 2.0, so that
# the input data of the two ends differ and move with the states.
CANCEL_COUNT = (
    ("s0", "The base.\n", (), POINTS, PARAMS),
    ("s1", "Raise MP-B\n", ("data",), POINTS_B, PARAMS),
    ("s2", "Raise the rate\n", ("parameter",), POINTS_B, PARAMS_RATE),
    ("s3", "Lower MP-B again\n", ("data",), POINTS.replace("MP-B,0,2,2", "MP-B,0,2,2.0"), PARAMS_RATE),
)


def every_contribution(result: dict) -> list[dict]:
    return [c for entry in result["contributions"] for c in entry["contributions"]]


def test_a_contribution_holds_a_signature_row_only_for_a_quantity_it_contributes_to(world):
    """R1: an un-narrowed search and a search that names every quantity judge the halves of (0, 3) for
    the cash flow alone; the count moves with s1 as well, and its row of the signature table is not
    attached."""
    build(world, CANCEL_COUNT)
    engine = WalkStub(CANCEL_COUNT)
    older, newer = record(world, "s0", engine, label="N"), record(world, "s3", engine, label="N+1")
    plain = run_search(world, older, newer, WalkStub(CANCEL_COUNT)).result
    named = run_search(world, older, newer, WalkStub(CANCEL_COUNT), output="named",
                       quantities=[CASH, COUNT]).result
    assert plain["intervals"][0] == {"from_state": 0, "to_state": 3, "revisions": ["s1", "s2", "s3"],
                                     "differs": [CASH]}
    assert [c["revisions"] for c in plain["contributions"]] == [["s1"], ["s2"], ["s3"]]
    for result in (plain, named):
        assert_search_folder_valid(world / ("search" if result is plain else "named"))
        assert all(("signature" in c) == c["contributes"] for c in every_contribution(result))
    s1 = plain["contributions"][0]
    count, cash = s1["contributions"]
    assert count["quantity"] == COUNT and not count["contributes"] and count["sum"] != 0
    assert "signature" not in count and cash["contributes"] and "signature" in cash
    # Naming every quantity narrows nothing: the same contributions, signature rows included.
    assert named["contributions"] == plain["contributions"]
    assert named["target"] == plain["target"] == {"quantities": [COUNT, CASH]}
    assert named == plain


def test_only_a_proper_subset_of_the_quantities_or_a_period_range_narrows_the_target(history):
    world, older, newer = history
    prepared = prepare(older, newer, WalkStub(HISTORY), world, None, "search")
    assert not read_target([], None, prepared).narrowed
    assert not read_target([COUNT, CASH], None, prepared).narrowed
    assert not read_target([CASH, COUNT, CASH], None, prepared).narrowed
    assert read_target([COUNT], None, prepared).narrowed
    assert read_target([COUNT, CASH], "0-2", prepared).narrowed
    # A narrowed search holds no signature row, as before.
    result = run_search(world, older, newer, WalkStub(HISTORY), quantities=[CASH]).result
    assert result["contributions"] and not any("signature" in c for c in every_contribution(result))
    assert all(c["quantity"] == CASH for c in every_contribution(result))


@pytest.mark.parametrize("version", ["1.0", "2.0", "3.0"])
def test_a_walk_folder_written_under_an_earlier_version_is_a_reference(cancel, version):
    world, older, newer = cancel
    with written_under(version):
        run_walk(world, older, newer, WalkStub(CANCEL))
    walked = world / "walk"
    assert stored(walked / "walk.result.json")["contract_version"] == version
    assert stored(walked / "changes.json")["contract_version"] == version
    assert stored(walked / "state-02" / "changes.json")["contract_version"] == version
    run_walk(world, older, newer, WalkStub(CANCEL), output="walk-2")
    result = run_search(world, older, newer, WalkStub(CANCEL), walk=walked).result
    again = run_search(world, older, newer, WalkStub(CANCEL), output="search-2", walk=world / "walk-2").result
    assert result["contract_version"] == "3.1"
    assert result["missed"] == again["missed"] == [{"revision": "c1", "quantity": CASH},
                                                   {"revision": "c2", "quantity": CASH}]
    # The copy of the walk keeps its bytes and its version.
    assert (world / "search" / "walk" / "walk.result.json").read_bytes() == (walked / "walk.result.json").read_bytes()


@pytest.mark.parametrize("version", ["1.0", "2.0", "3.0"])
def test_an_earlier_walk_folder_whose_manifest_differs_otherwise_is_refused(cancel, version):
    world, older, newer = cancel
    with written_under(version):
        run_walk(world, older, newer, WalkStub(CANCEL))
    rewrite_state(world / "walk", 2, edit_manifest=redescribe)
    with pytest.raises(Rejection) as caught:
        run_search(world, older, newer, WalkStub(CANCEL), walk=world / "walk")
    assert caught.value.code == "walk_mismatch", caught.value.message
    assert not (world / "search").exists()


@pytest.mark.parametrize("version", [["1.0"], "4.0"])
def test_a_walk_manifest_of_a_version_the_tool_does_not_read_is_refused(cancel, version):
    world, older, newer = cancel
    run_walk(world, older, newer, WalkStub(CANCEL))
    manifest = stored(world / "walk" / "changes.json")
    manifest["contract_version"] = version
    (world / "walk" / "changes.json").write_bytes(document_bytes(manifest))

    def rehash(result):
        result["manifest"]["sha256"] = sha256_file(world / "walk" / "changes.json")
    rewrite_walk_result(world / "walk", rehash)
    record = stored(world / "walk" / "walk.run-record.json")  # the record lists the manifest as well
    for entry in record["inputs"] + record["outputs"]:
        entry["artifact"]["sha256"] = sha256_file(world / "walk" / entry["artifact"]["path"])
    (world / "walk" / "walk.run-record.json").write_bytes(document_bytes(record))
    with pytest.raises(Rejection) as caught:
        run_search(world, older, newer, WalkStub(CANCEL), walk=world / "walk")
    assert caught.value.code == "walk_mismatch", caught.value.message
    assert caught.value.message == "The manifest of the walk is not the one derived again."
    assert not (world / "search").exists()


# x1 moves the cash flow and x3 reverts it; state 2 does not run, so the walk carries x2 and x3 in one
# step; x4 raises MP-B.
CARRY = (
    ("x0", "The base.\n", (), POINTS, PARAMS),
    ("x1", "Raise the rate\n", ("parameter",), POINTS, PARAMS_RATE),
    ("x2", "Touch nothing\n", (), POINTS, PARAMS_RATE),
    ("x3", "Revert the rate\n", ("parameter",), POINTS, PARAMS),
    ("x4", "Raise MP-B\n", ("data",), POINTS_B, PARAMS),
)


def test_a_carried_step_of_the_walk_counts_for_each_revision_it_carries(world):
    build(world, CARRY)
    engine = WalkStub(CARRY)
    older, newer = record(world, "x0", engine, label="N"), record(world, "x4", engine, label="N+1")
    walked = run_walk(world, older, newer, WalkStub(CARRY, broken={"x2"}))
    assert walked.attributed
    assert [s["revisions"] for s in walked.result["steps"]] == [["x1"], ["x2", "x3"], ["x4"]]
    result = run_search(world, older, newer, WalkStub(CARRY, broken={"x2"}), walk=world / "walk").result
    assert [c["revisions"] for c in result["contributions"]] == [["x4"]]
    # The carried step (1, 3) changes the cash flow: x2 and x3 are each missed for it.
    assert result["missed"] == [{"revision": name, "quantity": CASH} for name in ("x1", "x2", "x3")]


def test_the_check_recomputes_the_walk_flags_from_the_exports(history):
    world, older, newer = history
    run_walk(world, older, newer, WalkStub(HISTORY), tolerance=world / "tolerance.json")
    prepared = prepare(older, newer, WalkStub(HISTORY), world, world / "tolerance.json", "search")
    folder = read_walk_folder(world / "walk", prepared)
    target = read_target([], None, prepared)
    changes = walk_changes(folder, prepared, target)
    steps = folder.result["steps"]
    assert [revisions for revisions, _ in changes] == [s["revisions"] for s in steps]
    assert [[name in differs for name in target.quantities] for _, differs in changes] == [
        [c["contributes"] for c in s["contributions"]] for s in steps]


SEARCH_PROCESS = """
import sys
sys.path[:0] = [sys.argv[1]]
from conftest import HISTORY, WalkStub
from degelmann.deltarecon.search import search
search(sys.argv[2], sys.argv[3], sys.argv[4], WalkStub(HISTORY), repositories=sys.argv[5], tolerance=sys.argv[6],
       quantities=["Anzahl Verträge"], periods="0-2", walk=sys.argv[7])
"""


def test_the_same_inputs_give_the_same_search_result_bytes_in_two_processes(history):
    world, older, newer = history
    run_walk(world, older, newer, WalkStub(HISTORY), tolerance=world / "tolerance.json")
    for name in ("a", "b"):
        done = subprocess.run([sys.executable, "-c", SEARCH_PROCESS, str(ROOT / "tests"), str(older), str(newer),
                               str(world / name / "search"), str(world), str(world / "tolerance.json"),
                               str(world / "walk")], cwd=ROOT, capture_output=True, text=True)
        assert done.returncode == 0, done.stderr
    first, second = world / "a" / "search", world / "b" / "search"
    assert (first / "search.result.json").read_bytes() == (second / "search.result.json").read_bytes()


def test_a_moved_checked_search_folder_resolves_without_the_walk_folder(history, tmp_path_factory):
    world, older, newer = history
    run_walk(world, older, newer, WalkStub(HISTORY), tolerance=world / "tolerance.json")
    run_search(world, older, newer, WalkStub(HISTORY), tolerance=world / "tolerance.json", quantities=[COUNT],
               walk=world / "walk")
    moved = tmp_path_factory.mktemp("moved") / "search"
    shutil.move(str(world / "search"), str(moved))
    shutil.rmtree(world / "walk")
    assert_references_resolve(moved)
    result = stored(moved / "search.result.json")
    copied = moved / result["walk"]["result"]["path"]
    assert sha256_file(copied) == result["walk"]["result"]["sha256"]
    assert_references_resolve(copied.parent)


def test_a_record_without_the_suffix_json_is_copied_with_what_it_references(cancel):
    world, older, newer = cancel
    renamed = older.with_name("record")
    older.rename(renamed)
    run_walk(world, renamed, newer, WalkStub(CANCEL))
    run_search(world, renamed, newer, WalkStub(CANCEL), walk=world / "walk")
    copy = world / "search" / "walk" / "older"
    record = stored(copy / "record")
    for entry in record["inputs"] + record["outputs"]:
        target = copy / entry["artifact"]["path"]
        assert target.is_file() and sha256_file(target) == entry["artifact"]["sha256"], target


def rewrite_state(folder: Path, k: int, edit_request=None, edit_manifest=None) -> None:
    """Edit the request or the manifest of state ``k`` and pass the new hashes up to the state's run
    record, so that only the edit is wrong."""
    state = folder / f"state-{k:02d}"
    request = stored(state / "request.json")
    if edit_manifest is not None:
        manifest = stored(state / "changes.json")
        edit_manifest(manifest)
        (state / "changes.json").write_bytes(document_bytes(manifest))
        request["changes"]["manifest"]["sha256"] = sha256_file(state / "changes.json")
    if edit_request is not None:
        edit_request(request)
    (state / "request.json").write_bytes(document_bytes(request))
    if edit_manifest is not None:  # the response echoes the manifest; the walk result lists the response
        response = stored(state / "response.json")
        response["changes"]["manifest"]["sha256"] = request["changes"]["manifest"]["sha256"]
        (state / "response.json").write_bytes(document_bytes(response))

        def relist(result):
            result["states"][k]["response"]["sha256"] = sha256_file(state / "response.json")
        rewrite_walk_result(folder, relist)
    record = stored(state / "run-record.json")
    for entry in record["inputs"] + record["outputs"]:
        entry["artifact"]["sha256"] = sha256_file(state / entry["artifact"]["path"])
    (state / "run-record.json").write_bytes(document_bytes(record))


def redescribe(manifest):
    manifest["changes"][0]["description"] = "Another change under the same id"


def null_changes(request):
    request["changes"] = None


@pytest.mark.parametrize("case", ["other-state-manifest", "malformed-state-request"])
def test_a_state_of_the_walk_on_another_manifest_or_a_malformed_request_is_refused(cancel, case):
    world, older, newer = cancel
    run_walk(world, older, newer, WalkStub(CANCEL))
    if case == "other-state-manifest":
        rewrite_state(world / "walk", 2, edit_manifest=redescribe)
    else:
        rewrite_state(world / "walk", 2, edit_request=null_changes)
    with pytest.raises(Rejection) as caught:
        run_search(world, older, newer, WalkStub(CANCEL), walk=world / "walk")
    assert caught.value.code == "walk_mismatch", caught.value.message
    assert not (world / "search").exists()


def name_a_target(request):
    request["target"] = {"quantities": [CASH]}


def test_a_walk_folder_with_a_state_whose_request_names_a_target_is_refused(cancel, monkeypatch, capsys):
    """A walk runs every state in full: a state request with a target fails the reader rules of a walk
    folder. State 4 lies in no comparison the walk keeps, so the rehashed folder passes every other rule."""
    world, older, newer = cancel
    run_walk(world, older, newer, WalkStub(CANCEL))
    shutil.copytree(world / "walk", world / "walk-same")
    rewrite_state(world / "walk-same", 4, edit_request=lambda request: None)
    assert run_search(world, older, newer, WalkStub(CANCEL), output="control", walk=world / "walk-same",
                      reuse=True).searched
    rewrite_state(world / "walk", 4, edit_request=name_a_target)
    before = folder_hashes(world)
    engine = WalkStub(CANCEL)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: engine)
    assert main(["search", str(older), str(newer), "--output", str(world / "search"), "--repositories", str(world),
                 "--walk", str(world / "walk"), "--reuse-walk"]) == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "search: rejected" and "diagnostic: walk_mismatch: " in out
    assert "names a target" in out
    assert engine.opened == 0 and folder_hashes(world) == before and not (world / "search").exists()


@pytest.mark.parametrize("side", ["older", "newer"])
def test_the_record_of_a_target_only_run_is_refused_and_nothing_runs(world, monkeypatch, capsys, side):
    build(world, CANCEL)
    target = {"target": {"quantities": [CASH], "periods": {"first": 0, "last": 1}}}
    older = record(world, "c0", WalkStub(CANCEL), label="N", **(target if side == "older" else {}))
    newer = record(world, "c4", WalkStub(CANCEL), label="N+1", **(target if side == "newer" else {}))
    before = folder_hashes(world)
    engine = WalkStub(CANCEL)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: engine)
    assert main(["search", str(older), str(newer), "--output", str(world / "search"), "--repositories", str(world),
                 "--quantity", CASH, "--periods", "0-1"]) == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "search: rejected" and "diagnostic: target_only_record: " in out
    assert engine.opened == 0 and folder_hashes(world) == before and not (world / "search").exists()


# --- reuse of the walk's states -------------------------------------------------------


class Counting(WalkStub):
    """The walk stub that counts the states it is asked to compute."""

    def __init__(self, *args, **options):
        super().__init__(*args, **options)
        self.calls = 0

    def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
        self.calls += 1
        return super().open(release, enabled, manifest_dir, repositories, hold)


def without_compare(node):
    """A document without its comparison references, whose paths name the states compared."""
    if isinstance(node, dict):
        return {key: without_compare(value) for key, value in node.items() if key != "compare"}
    if isinstance(node, list):
        return [without_compare(value) for value in node]
    return node


def assert_same_search(reused: dict, ran: dict) -> None:
    """The halving, the ends, the contributions and their sums, the findings and the missed are those
    of the search that ran its states."""
    for member in ("ends", "target", "intervals", "contributions", "findings", "missed"):
        assert without_compare(reused[member]) == without_compare(ran[member]), member
    assert [s["state"] for s in reused["states"]] == [s["state"] for s in ran["states"]]
    assert [s["outcome"] for s in reused["states"]] == [s["outcome"] for s in ran["states"]]


@pytest.mark.parametrize("options", [
    {"quantities": [COUNT], "periods": "0-2", "tolerance": "tolerance.json"}, {}], ids=["target", "every-coordinate"])
def test_reuse_over_a_full_walk_runs_no_state_and_finds_what_the_search_finds(history, options):
    world, older, newer = history
    if "tolerance" in options:
        options = {**options, "tolerance": world / options["tolerance"]}
    run_walk(world, older, newer, WalkStub(HISTORY), tolerance=options.get("tolerance"))
    ran = run_search(world, older, newer, WalkStub(HISTORY), walk=world / "walk", **options).result
    engine = Counting(HISTORY)
    reused = run_search(world, older, newer, engine, output="reused", walk=world / "walk", reuse=True,
                        **options).result
    assert engine.calls == 0
    assert_same_search(reused, ran)
    folder = world / "reused"
    assert assert_search_folder_valid(folder) == reused
    count = len(ran["states"])
    assert reused["runs"] == {"walk": 9, "search": 0, "saved": 9, "reused": count}
    assert ran["runs"] == {"walk": 9, "search": count, "saved": 9 - count}
    # A reused state is the walk's run: its run id, its files under walk/, and no folder of the search.
    walked = {s["state"]: s for s in stored(world / "walk" / "walk.result.json")["states"]}
    for entry in reused["states"]:
        k = entry["state"]
        assert entry["reused"] is True and entry["run_id"] == walked[k]["run_id"] == f"walk-run-h0-run-h8-state-{k}"
        assert entry["response"] == {**walked[k]["response"], "path": "walk/" + walked[k]["response"]["path"]}
        assert entry["export"] == {**walked[k]["export"], "path": "walk/" + walked[k]["export"]["path"]}
        assert not (folder / f"state-{k:02d}").exists()
    assert list(reused["states"][1]) == ["state", "revision", "run_id", "outcome", "reused", "response", "export"]
    # The comparisons kept reference the reused responses and run records under walk/.
    for entry in reused["contributions"]:
        request = stored(folder / entry["compare"]["result"]["path"].replace(".result.", ".request."))
        assert all(side["path"].startswith("walk/state-") for side in (*request["left"].values(),
                                                                        *request["right"].values()))
    # The result and the run record name the switch; without it neither does.
    record = stored(folder / "search.run-record.json")
    assert reused["switches"] == record["switches"] == ["reuse_walk"]
    assert list(reused)[:5] == ["document", "contract_version", "stage", "search_id", "switches"]
    assert "switches" not in ran and "switches" not in stored(world / "search" / "search.run-record.json")
    assert "reused" not in json.dumps(ran)


def test_a_walk_state_that_did_not_run_is_reused_as_a_state_that_did_not_run(world):
    build(world, CARRY)
    engine = WalkStub(CARRY)
    older, newer = record(world, "x0", engine, label="N"), record(world, "x4", engine, label="N+1")
    assert run_walk(world, older, newer, WalkStub(CARRY, broken={"x2"})).attributed
    ran = run_search(world, older, newer, WalkStub(CARRY, broken={"x2"}), walk=world / "walk").result
    counting = Counting(CARRY, broken={"x2"})
    reused = run_search(world, older, newer, counting, output="reused", walk=world / "walk", reuse=True).result
    assert counting.calls == 0
    assert_same_search(reused, ran)
    assert_search_folder_valid(world / "reused")
    (finding,) = [f for f in reused["findings"] if f["code"] == "state_did_not_run"]
    assert finding["state"] == 2 and finding["revisions"] == ["x2"]
    walked = stored(world / "walk" / "walk.result.json")["states"][2]
    failed = next(s for s in reused["states"] if s["state"] == 2)
    assert failed == {"state": 2, "revision": "x2", "run_id": walked["run_id"], "outcome": walked["outcome"],
                      "reused": True, "response": {**walked["response"], "path": "walk/" + walked["response"]["path"]}}
    assert finding["diagnostic"] == stored(world / "walk" / walked["response"]["path"])["diagnostics"][0]
    assert reused["runs"]["search"] == 0 and reused["runs"]["reused"] == len(reused["states"])


def test_the_switch_without_a_walk_is_a_usage_error_and_writes_nothing(history, monkeypatch, capsys):
    world, older, newer = history
    before = folder_hashes(world)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: WalkStub(HISTORY))
    assert main(["search", str(older), str(newer), "--output", str(world / "search"), "--repositories", str(world),
                 "--reuse-walk"]) == 2
    error = capsys.readouterr().err
    assert "--reuse-walk" in error and "--walk" in error
    assert folder_hashes(world) == before and not (world / "search").exists()
    with pytest.raises(UsageError) as raised:  # a library caller is told the switch, not a flag
        run_search(world, older, newer, WalkStub(HISTORY), reuse=True)
    assert "reuse_walk" in str(raised.value) and "--" not in str(raised.value)


def test_a_refused_walk_is_refused_under_the_switch_before_anything_runs(cancel):
    world, older, newer = cancel
    run_walk(world, older, newer, WalkStub(CANCEL, drift={"c4": 1}))
    engine = Counting(CANCEL)
    with pytest.raises(Rejection) as caught:
        run_search(world, older, newer, engine, walk=world / "walk", reuse=True)
    assert caught.value.code == "walk_not_attributed" and not (world / "search").exists() and engine.calls == 0


def test_a_moved_reuse_search_folder_resolves_inside_itself(history, tmp_path_factory, monkeypatch, capsys):
    world, older, newer = history
    run_walk(world, older, newer, WalkStub(HISTORY), tolerance=world / "tolerance.json")
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: Counting(HISTORY))
    monkeypatch.chdir(world)
    assert main(["search", str(older), str(newer), "--output", str(world / "search"), "--repositories", str(world),
                 "--quantity", COUNT, "--periods", "0-2", "--tolerance", str(world / "tolerance.json"),
                 "--walk", str(world / "walk"), "--reuse-walk"]) == 0
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "search: searched; 0 states run, 6 reused from the walk, 9 for a walk, 9 saved"
    assert "  missed: " in out
    moved = tmp_path_factory.mktemp("moved") / "search"
    shutil.move(str(world / "search"), str(moved))
    shutil.rmtree(world / "walk")
    assert_references_resolve(moved)
    assert_search_folder_valid(moved)


# --- the halving --------------------------------------------------------------------


def test_a_sub_tolerance_pair_is_not_resolved_and_not_missed(history):
    world, older, newer = history
    run_walk(world, older, newer, WalkStub(HISTORY), tolerance=world / "tolerance.json")
    result = run_search(world, older, newer, WalkStub(HISTORY), tolerance=world / "tolerance.json",
                        quantities=[COUNT], periods="0-2", walk=world / "walk").result
    assert [f["code"] for f in result["findings"]] == ["interval_not_resolved"]
    walked = stored(world / "walk" / "walk.result.json")
    for step in walked["steps"]:
        if step["revisions"] in (["h5"], ["h6"]):
            assert not any(c["contributes"] for c in step["contributions"] if c["quantity"] == COUNT)
    assert not {"h5", "h6"} & {m["revision"] for m in result["missed"]}


def test_a_midpoint_that_does_not_run_is_replaced_by_the_nearest_state_that_runs(world, monkeypatch, capsys):
    build(world)
    older, newer = record(world, "w0", label="N"), record(world, "w4", label="N+1")
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: WalkStub(broken={"w2"}))
    assert main(["search", str(older), str(newer), "--output", str(world / "search"),
                 "--repositories", str(world)]) == 0
    assert "finding: state_did_not_run (state 2)" in capsys.readouterr().out
    result = assert_search_folder_valid(world / "search")
    assert [(s["state"], s["outcome"]) for s in result["states"]] == [
        (0, "succeeded"), (1, "succeeded"), (2, "error"), (3, "succeeded"), (4, "succeeded")]
    assert [(i["from_state"], i["to_state"]) for i in result["intervals"]] == [(0, 4), (0, 3), (0, 1), (1, 3), (3, 4)]
    # State 2 is known not to run and is not requested again: the interval (1, 3) is carried.
    assert [c["revisions"] for c in result["contributions"]] == [["w1"], ["w2", "w3"], ["w4"]]
    assert [f["code"] for f in result["findings"]] == ["state_did_not_run"]


def test_an_interval_without_an_inner_state_that_runs_is_one_contribution(world):
    build(world)
    line = LINE[:4]
    build(world, line)
    older, newer = record(world, "w0", WalkStub(line)), record(world, "w3", WalkStub(line))
    result = run_search(world, older, newer, WalkStub(line, broken={"w1", "w2"})).result
    assert [(s["state"], s["outcome"]) for s in result["states"]] == [
        (0, "succeeded"), (1, "error"), (2, "error"), (3, "succeeded")]
    (entry,) = result["contributions"]
    assert entry["revisions"] == ["w1", "w2", "w3"] and (entry["from_state"], entry["to_state"]) == (0, 3)
    assert [f["code"] for f in result["findings"]] == ["state_did_not_run", "state_did_not_run"]
    assert result["runs"] == {"walk": 4, "search": 4, "saved": 0}


def test_one_revision_checks_state_zero_against_both_records(world):
    build(world)
    older = record(world, "w1", folder="run-a")
    newer = record(world, "w1", folder="run-b", further=[{"kind": "engine_version", "value": "2"}])
    result = run_search(world, older, newer, WalkStub()).result
    assert [s["state"] for s in result["states"]] == [0] and result["intervals"] == []
    assert result["ends"] == {"zero": {"state": 0, "outcome": "reproduced"}, "n": {"state": 0, "outcome": "reproduced"}}
    assert result["runs"] == {"walk": 1, "search": 1, "saved": 0}


@pytest.mark.parametrize("case", ["zero-not-reproduced", "n-not-reproduced", "zero-does-not-run",
                                  "n-does-not-run"])
def test_an_end_that_does_not_run_or_reproduce_stops_the_search(world, monkeypatch, capsys, case):
    build(world)
    older, newer = record(world, "w0", label="N"), record(world, "w4", label="N+1")
    engine = {"zero-not-reproduced": WalkStub(drift={"w0": 1}), "n-not-reproduced": WalkStub(drift={"w4": 1}),
              "zero-does-not-run": WalkStub(broken={"w0"}), "n-does-not-run": WalkStub(broken={"w4"})}[case]
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: engine)
    assert main(["search", str(older), str(newer), "--output", str(world / "search"),
                 "--repositories", str(world)]) == 1
    assert capsys.readouterr().out.startswith("search: stopped")
    result = assert_search_folder_valid(world / "search")
    assert result["intervals"] == [] and result["contributions"] == []
    assert stored(world / "search" / "search.run-record.json")["outcome"] == "stopped"
    code = {"zero-not-reproduced": "state_zero_not_reproduced", "n-not-reproduced": "state_n_not_reproduced"}.get(
        case, "state_did_not_run")
    assert result["findings"][-1]["code"] == code
    assert [s["state"] for s in result["states"]] == ([0] if case.startswith("zero") else [0, 4])


# --- target isolation ---------------------------------------------------------------


class Overflowing(WalkStub):
    """The stub whose cash flow of MP-X is the value ``cash[folder]``, so a difference can overflow."""

    def __init__(self, line, cash):
        super().__init__(line)
        self.cash = cash

    @contextmanager
    def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
        revisions = [c["realisation"]["revision"] for c in enabled if c["realisation"]["type"] == "revision"]
        name = revisions[-1] if revisions else self._folder(release, repositories).name
        with super().open(release, enabled, manifest_dir, repositories, hold) as session:
            plain = session.project
            session.project = lambda point: [(p, [v[0], self.cash[name] if point == "MP-X" else v[1]])
                                             for p, v in plain(point)]
            yield session


OVERFLOW = (("o0", "", (), "id,first,last,base\nMP-X,0,0,1\n", PARAMS),
            ("o1", "Raise MP-X and flip its cash flow\n", ("data",), "id,first,last,base\nMP-X,0,0,2\n", PARAMS))
CASH_FLIP = {"o0": -1e308, "o1": 1e308}


def test_a_failure_outside_the_target_does_not_change_the_judgement(world):
    build(world, OVERFLOW)
    engine = Overflowing(OVERFLOW, CASH_FLIP)
    older, newer = record(world, "o0", engine), record(world, "o1", engine)
    result = run_search(world, older, newer, Overflowing(OVERFLOW, CASH_FLIP), quantities=[COUNT]).result
    (entry,) = result["contributions"]
    assert entry["contributions"] == [{"quantity": COUNT, "contributes": True, "sum": 1.0, "absolute_sum": 1.0}]
    assert result["findings"] == []
    # The kept comparison is that of the full states, as evidence: it is rejected.
    assert stored(world / "search" / entry["compare"]["result"]["path"])["outcome"] == "rejected"


def test_a_non_compared_interval_differs_for_every_quantity_as_the_walk_step(world):
    build(world, OVERFLOW)
    engine = Overflowing(OVERFLOW, CASH_FLIP)
    older, newer = record(world, "o0", engine), record(world, "o1", engine)
    run_walk(world, older, newer, Overflowing(OVERFLOW, CASH_FLIP))
    result = run_search(world, older, newer, Overflowing(OVERFLOW, CASH_FLIP), walk=world / "walk").result
    assert result["intervals"][0]["differs"] == [COUNT, CASH]
    (entry,) = result["contributions"]
    assert [c["contributes"] for c in entry["contributions"]] == [True, True]
    assert result["findings"][0]["code"] == "step_not_compared"
    assert result["findings"][0]["diagnostic"]["code"] == "non_finite_difference"
    (step,) = stored(world / "walk" / "walk.result.json")["steps"]
    assert entry["contributions"] == step["contributions"] and result["missed"] == []


# An in-force point B starts at period 144 of policy_month, A is new business: I1 cuts A's cover
# after period 143, outside the first three projection months; I2 raises B.
INFORCE = (
    ("i0", "The base.\n", (), "id,first,last,base\nMP-A,0,150,1\nMP-B,144,150,2\n", PARAMS),
    ("i1", "End the cover of MP-A after period 143\n", ("data",),
     "id,first,last,base\nMP-A,0,143,1\nMP-B,144,150,2\n", PARAMS),
    ("i2", "Raise MP-B\n", ("data",), "id,first,last,base\nMP-A,0,143,1\nMP-B,144,150,3\n", PARAMS),
)


def test_an_in_force_point_is_judged_on_its_projection_periods(world):
    build(world, INFORCE)
    engine = WalkStub(INFORCE)
    older, newer = record(world, "i0", engine, label="N"), record(world, "i2", engine, label="N+1")
    assert run_walk(world, older, newer, WalkStub(INFORCE)).attributed
    result = run_search(world, older, newer, WalkStub(INFORCE), quantities=[COUNT], periods="0-2",
                        walk=world / "walk").result
    assert_search_folder_valid(world / "search")
    # A is judged on its periods 0 to 2, so the end of its cover at period 144 is outside the target;
    # B is judged on its periods 144 to 146.
    assert [(i["from_state"], i["to_state"], i["differs"]) for i in result["intervals"]] == [
        (0, 2, [COUNT]), (0, 1, []), (1, 2, [COUNT])]
    (found,) = result["contributions"]
    assert found["revisions"] == ["i2"]
    assert found["contributions"] == [{"quantity": COUNT, "contributes": True, "sum": 3.0, "absolute_sum": 3.0}]
    exports = {s["state"]: world / "walk" / s["export"]["path"] for s in stored(world / "walk" / "walk.result.json")[
        "states"]}
    assert float(exact(exports[1], exports[2], [COUNT], (0, 2))[COUNT]) == 3.0
    # The walk shows i1 as a change of the full runs, but not of the target: nothing is missed.
    assert result["missed"] == [] and not result["findings"]


# M1 moves the valuation month of the in-force point B from period 144 to 156; its count stays.
# M2 raises B.
MOVED = (
    ("m0", "The base.\n", (), "id,first,last,base\nMP-A,0,150,1\nMP-B,144,150,2\n", PARAMS),
    ("m1", "Move the valuation month of MP-B\n", ("data",), "id,first,last,base\nMP-A,0,150,1\nMP-B,156,162,2\n",
     PARAMS),
    ("m2", "Raise MP-B\n", ("data",), "id,first,last,base\nMP-A,0,150,1\nMP-B,156,162,3\n", PARAMS),
)


def test_each_state_is_judged_on_its_own_valuation_month(world):
    """Target 0-2: B is judged on policy months 144 to 146 of the older state and 156 to 158 of a later one."""
    build(world, MOVED)
    engine = WalkStub(MOVED)
    older, newer = record(world, "m0", engine, label="N"), record(world, "m2", engine, label="N+1")
    walked = run_walk(world, older, newer, WalkStub(MOVED))
    assert walked.attributed
    # The walk pairs B by projection period: m1 keeps its count; only the cash flow, which the stub
    # computes from the policy month, moves.
    first = walked.result["steps"][0]
    assert first["revisions"] == ["m1"] and [(c["quantity"], c["contributes"]) for c in first["contributions"]] == [
        (COUNT, False), (CASH, True)]
    step = stored(world / "walk" / first["compare"]["result"]["path"])
    assert step["added"] == step["removed"] == []
    result = run_search(world, older, newer, WalkStub(MOVED), quantities=[COUNT], periods="0-2",
                        walk=world / "walk").result
    assert_search_folder_valid(world / "search")
    assert [(i["from_state"], i["to_state"], i["differs"]) for i in result["intervals"]] == [
        (0, 2, [COUNT]), (0, 1, []), (1, 2, [COUNT])]
    (found,) = result["contributions"]
    assert found["revisions"] == ["m2"]
    assert found["contributions"] == [{"quantity": COUNT, "contributes": True, "sum": 3.0, "absolute_sum": 3.0}]
    exports = {s["state"]: world / "walk" / s["export"]["path"] for s in stored(world / "walk" / "walk.result.json")[
        "states"]}
    assert float(exact(exports[1], exports[2], [COUNT], (0, 2))[COUNT]) == 3.0
    assert result["missed"] == [] and not result["findings"]


def test_restrict_counts_target_periods_from_the_valuation_date_on_policy_month():
    from degelmann.deltarecon.compare import CheckedRun
    response = {"quantities": [{"name": COUNT, "unit": "policies"}], "time_basis": {"id": "policy_month"}}
    values = {**{("A", t): [1.0] for t in range(0, 150)}, **{("B", t): [2.0] for t in range(144, 150)},
              **{("C", t): [3.0] for t in range(30, 40)}}
    narrowed = restrict(CheckedRun(response, values), Target((COUNT,), (0, 2), True))
    # Every model point counts from its own first period in this run; the result is aligned.
    assert narrowed.aligned and narrowed.values == {
        (point, t): [value] for point, value in (("A", 1.0), ("B", 2.0), ("C", 3.0)) for t in range(3)}


class ValuationStub(WalkStub):
    """The walk stub on a basis whose origin is the valuation date."""

    @contextmanager
    def open(self, *args, **kwargs):
        with super().open(*args, **kwargs) as session:
            session.time_basis = "valuation_year"
            yield session


# On valuation_year, A starts at period 2 and B at period 3. V1 raises B, V2 raises A.
VALUATION = (
    ("v0", "The base.\n", (), "id,first,last,base\nMP-A,2,5,1\nMP-B,3,5,2\n", PARAMS),
    ("v1", "Raise MP-B\n", ("data",), "id,first,last,base\nMP-A,2,5,1\nMP-B,3,5,3\n", PARAMS),
    ("v2", "Raise MP-A\n", ("data",), "id,first,last,base\nMP-A,2,5,2\nMP-B,3,5,3\n", PARAMS),
)


def test_on_a_valuation_origin_basis_target_periods_are_used_as_they_are(world):
    build(world, VALUATION)
    engine = ValuationStub(VALUATION)
    older, newer = record(world, "v0", engine, label="N"), record(world, "v2", engine, label="N+1")
    assert stored(older.parent / "response.json")["time_basis"] == {"id": "valuation_year"}
    assert run_walk(world, older, newer, ValuationStub(VALUATION)).attributed
    result = run_search(world, older, newer, ValuationStub(VALUATION), quantities=[COUNT], periods="1-2",
                        walk=world / "walk").result
    assert_search_folder_valid(world / "search")
    # Periods 1 and 2 as they are: only A's period 2 is inside, B's periods 3 to 5 are not.
    assert [(i["from_state"], i["to_state"], i["differs"]) for i in result["intervals"]] == [
        (0, 2, [COUNT]), (0, 1, []), (1, 2, [COUNT])]
    (found,) = result["contributions"]
    assert found["revisions"] == ["v2"]
    assert found["contributions"] == [{"quantity": COUNT, "contributes": True, "sum": 1.0, "absolute_sum": 1.0}]
    assert result["missed"] == []


def test_restrict_keeps_the_target_periods_and_quantities_in_response_order():
    from degelmann.deltarecon.compare import CheckedRun
    response = {"quantities": [{"name": COUNT, "unit": "policies"}, {"name": CASH, "unit": "EUR"}],
                "time_basis": {"id": "valuation_year"}}
    run = CheckedRun(response, {("A", 0): [1.0, 2.0], ("A", 5): [3.0, 4.0]})
    narrowed = restrict(run, Target((CASH,), (0, 2), True))
    assert narrowed.response["quantities"] == [{"name": CASH, "unit": "EUR"}]
    assert narrowed.values == {("A", 0): [2.0]}
    assert restrict(run, Target((COUNT, CASH))) is run


# --- refusals -----------------------------------------------------------------------


@pytest.mark.parametrize("options, message", [
    (["--quantity", "Provisionen"], "declares no quantity"),
    (["--periods", "5-2"], "FIRST-LAST"),
    (["--periods", "a-2"], "FIRST-LAST"),
    (["--periods=-1-2"], "FIRST-LAST"),
    (["--periods", "100-200"], "neither recorded export"),
])
def test_a_faulty_target_is_a_usage_error_and_writes_nothing(history, monkeypatch, capsys, options, message):
    world, older, newer = history
    before = folder_hashes(world)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: WalkStub(HISTORY))
    assert main(["search", str(older), str(newer), "--output", str(world / "search"),
                 "--repositories", str(world), *options]) == 2
    assert message in capsys.readouterr().err
    assert folder_hashes(world) == before and not (world / "search").exists()


@pytest.mark.parametrize("case, status", [("selection", 1), ("reference", 1), ("wrong-order", 1),
                                          ("existing-output", 2), ("absent-record", 2)])
def test_what_the_walk_refuses_the_search_refuses(world, monkeypatch, capsys, case, status):
    build(world)
    older, newer = record(world, "w0"), record(world, "w4")
    if case == "selection":
        older = record(world, "w0", folder="subset", selection={"mode": "subset", "model_point_ids": ["MP-A"]})
    elif case == "reference":
        (world / "w0" / "points.csv").write_text(POINTS_B, "utf-8")
    elif case == "wrong-order":
        older, newer = newer, older
    elif case == "existing-output":
        (world / "search").mkdir()
    else:
        older = world / "absent.json"
    before = folder_hashes(world)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", WalkStub)
    assert main(["search", str(older), str(newer), "--output", str(world / "search"),
                 "--repositories", str(world)]) == status
    output = capsys.readouterr()
    if status == 1:
        code = {"selection": "selection_mismatch", "reference": "reference_mismatch",
                "wrong-order": "unrelated_revisions"}[case]
        assert output.out.startswith("search: rejected") and f"diagnostic: {code}: " in output.out
    else:
        assert output.err.startswith("error: ")
    assert folder_hashes(world) == before and (world / "search").exists() == (case == "existing-output")


@pytest.mark.parametrize("case, status", [("stage-mismatch", 1), ("failed-run", 2)])
def test_a_stage_mismatch_or_a_failed_record_is_refused_as_by_the_walk(world, monkeypatch, capsys, case, status):
    build(world)
    monkeypatch.setitem(STAGE_QUANTITIES, "other_stage", STAGE_QUANTITIES["liability_cashflow"])
    older, newer = record(world, "w0", TwoStages()), record(world, "w4", TwoStages())
    if case == "stage-mismatch":
        newer = record(world, "w4", TwoStages(), folder="other", stage="other_stage")
    else:
        (world / "w0" / "points.csv").write_text(POINTS.replace("MP-B,0,2,2", "MP-B,0,2,raise"), "utf-8")
        (world / "fail").mkdir()
        request = stub_request(world, release={"label": "N", "references": StubEngine.references(world / "w0", "w0")})
        (world / "fail" / "request.json").write_bytes(document_bytes(request))
        assert run_request(world / "fail" / "request.json", TwoStages(), repositories=world).outcome == "failed"
        older = world / "fail" / "run-record.json"
    before = folder_hashes(world)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", TwoStages)
    assert main(["search", str(older), str(newer), "--output", str(world / "search"),
                 "--repositories", str(world)]) == status
    output = capsys.readouterr()
    if status == 1:
        assert output.out.startswith("search: rejected") and "diagnostic: stage_mismatch: " in output.out
    else:
        assert output.err.startswith("error: ")
    assert folder_hashes(world) == before and not (world / "search").exists()


def test_a_checked_search_that_stops_names_no_missed_contribution(cancel, monkeypatch):
    world, older, newer = cancel
    run_walk(world, older, newer, WalkStub(CANCEL))
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: WalkStub(CANCEL, drift={"c4": 1}))
    assert main(["search", str(older), str(newer), "--output", str(world / "search"), "--repositories", str(world),
                 "--walk", str(world / "walk")]) == 1
    result = assert_search_folder_valid(world / "search")
    assert result["ends"]["n"]["outcome"] == "not_reproduced" and result["intervals"] == []
    assert "walk" in result and result["missed"] == []


def test_a_walk_that_does_not_attribute_every_revision_is_refused(cancel):
    world, older, newer = cancel
    run_walk(world, older, newer, WalkStub(CANCEL, drift={"c4": 1}))
    with pytest.raises(Rejection) as caught:
        run_search(world, older, newer, WalkStub(CANCEL), walk=world / "walk")
    assert caught.value.code == "walk_not_attributed" and not (world / "search").exists()


def rewrite_walk_result(folder: Path, edit) -> None:
    """Edit the walk result and give the run record of the walk its new hash, so that only the edit is wrong."""
    result = stored(folder / "walk.result.json")
    edit(result)
    (folder / "walk.result.json").write_bytes(document_bytes(result))
    record = stored(folder / "walk.run-record.json")
    for entry in record["outputs"]:
        if entry["artifact"]["path"] == "walk.result.json":
            entry["artifact"]["sha256"] = sha256_file(folder / "walk.result.json")
    (folder / "walk.run-record.json").write_bytes(document_bytes(record))


def duplicate_state(result):
    result["states"].insert(2, result["states"][1])


def omit_state(result):
    del result["states"][2]


def break_chain(result):
    result["steps"][1]["from_state"] = 0


@pytest.mark.parametrize("case", ["other-records", "other-tolerance", "other-history", "tampered-export",
                                  "duplicated-state", "omitted-state", "broken-chain", "no-walk-folder"])
def test_a_walk_that_does_not_fit_is_refused_with_walk_mismatch(cancel, case):
    world, older, newer = cancel
    profile = {"per_quantity": {CASH: {"upper": {"abs_tol": 1, "rel_tol": 0}, "lower": {"abs_tol": 1, "rel_tol": 0},
                                       "derivation": "A test bound."}}}
    (world / "tolerance.json").write_text(json.dumps(profile), "utf-8")
    if case == "other-records":
        other = record(world, "c4", WalkStub(CANCEL), folder="run-other", label="N+1")
        run_walk(world, older, other, WalkStub(CANCEL))
    elif case == "other-history":
        run_walk(world, older, record(world, "c3", WalkStub(CANCEL), folder="run-c3"), WalkStub(CANCEL))
    elif case == "other-tolerance":
        run_walk(world, older, newer, WalkStub(CANCEL), tolerance=world / "tolerance.json")
    elif case == "no-walk-folder":
        (world / "walk").mkdir()
    else:
        run_walk(world, older, newer, WalkStub(CANCEL))
    if case == "tampered-export":
        path = world / "walk" / "state-02" / "results.csv"
        path.write_bytes(path.read_bytes().replace(b"\n", b"\r\n", 1))
    elif case in ("duplicated-state", "omitted-state", "broken-chain"):
        rewrite_walk_result(world / "walk", {"duplicated-state": duplicate_state, "omitted-state": omit_state,
                                             "broken-chain": break_chain}[case])
    before = folder_hashes(world)
    with pytest.raises(Rejection) as caught:
        run_search(world, older, newer, WalkStub(CANCEL), walk=world / "walk")
    assert caught.value.code == "walk_mismatch", caught.value.message
    assert folder_hashes(world) == before and not (world / "search").exists()


class Versioned(WalkStub):
    """The stub that records an engine version in the release of every state."""

    def __init__(self, line, version, **options):
        super().__init__(line, **options)
        self.version = version

    def state_release(self, base, revision, hold, repositories):
        identity = super().state_release(base, revision, hold, repositories)
        return {**identity, "references": identity["references"] + [{"kind": "engine_version",
                                                                      "value": self.version}]}


def test_a_walk_of_another_engine_version_is_refused_although_its_ends_agree(cancel, monkeypatch, capsys):
    world, older, newer = cancel
    # The walk ran on version 1, and its engine gave another intermediate state; the ends agree.
    assert run_walk(world, older, newer, Versioned(CANCEL, "1", drift={"c2": 5})).attributed
    before = folder_hashes(world)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: Versioned(CANCEL, "2"))
    assert main(["search", str(older), str(newer), "--output", str(world / "search"), "--repositories", str(world),
                 "--walk", str(world / "walk")]) == 1
    out = capsys.readouterr().out
    assert out.startswith("search: rejected") and "diagnostic: walk_mismatch: " in out
    assert folder_hashes(world) == before and not (world / "search").exists()
    # On the engine of the walk it is accepted.
    assert run_search(world, older, newer, Versioned(CANCEL, "1"), walk=world / "walk").searched


def test_an_interrupted_search_leaves_no_folder(cancel):
    world, older, newer = cancel

    class Interrupting(WalkStub):
        def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
            if len(enabled) == 2:
                raise KeyboardInterrupt
            return super().open(release, enabled, manifest_dir, repositories, hold)

    with pytest.raises(KeyboardInterrupt):
        run_search(world, older, newer, Interrupting(CANCEL))
    assert not (world / "search").exists()


def test_search_names_no_kind_of_reference_and_starts_no_process():
    text = (ROOT / "degelmann" / "deltarecon" / "search.py").read_text("utf-8")
    for kind in ("input_data", "code_state", "parameter_set", "engine_version", "release_folder", "subprocess"):
        assert kind not in text, kind


def test_usage_errors_are_usage_errors(world):
    with pytest.raises(UsageError):
        search(world / "absent.json", world / "absent.json", world / "search", WalkStub(), repositories=world)


# --- the reference engine on a throw-away clone -------------------------------------


def test_the_cancelling_pair_on_the_reference_engine(tmp_path):
    """A lowers the lapse rate from policy year 4 on and B reverts it, C lowers the lapse rate of policy
    year 2, D touches no class."""
    repositories, clone = throwaway(tmp_path)
    lines = (clone / POINT_TABLE).read_text("utf-8").splitlines(keepends=True)
    write_files(clone, {POINT_TABLE: lines[0] + lines[1] + lines[2]})
    base = commit(clone, "Keep two model points")
    lapse = (clone / LAPSE_TABLE).read_text("utf-8")
    assert "\n4,0.03," in lapse and "\n2,0.04," in lapse
    write_files(clone, {LAPSE_TABLE: lapse.replace("\n4,0.03,", "\n4,0.025,")})
    commit(clone, "A: lower the lapse rate from policy year 4 on")
    write_files(clone, {LAPSE_TABLE: lapse})
    commit(clone, "B: revert A")
    write_files(clone, {LAPSE_TABLE: lapse.replace("\n2,0.04,", "\n2,0.02,")})
    commit(clone, "C: halve the lapse rate of policy year 2")
    write_files(clone, {"NOTES.txt": "D\n"})
    newest = commit(clone, "D: touch no class")
    records = {}
    for name, revision in (("older", base), ("newer", newest)):
        folder = tmp_path / name
        assert main(["request", "--revision", revision, "--repositories", str(repositories), "--label", name,
                     "--run-id", f"run-{name}", "--output", str(folder / "request.json")]) == 0
        assert main(["run", str(folder / "request.json"), "--repositories", str(repositories)]) == 0
        records[name] = folder / "run-record.json"
    state = clone_state(clone)
    before = {name: folder_hashes(path.parent) for name, path in records.items()}
    walked = subprocess.run([sys.executable, "-m", "degelmann.deltarecon", "walk", str(records["older"]), str(records["newer"]),
                             "--output", str(tmp_path / "walk"), "--repositories", str(repositories)],
                            cwd=ROOT, capture_output=True, text=True)
    assert walked.returncode == 0, walked.stdout + walked.stderr
    walk_hashes = folder_hashes(tmp_path / "walk")
    done = subprocess.run([sys.executable, "-m", "degelmann.deltarecon", "search", str(records["older"]),
                           str(records["newer"]), "--walk", str(tmp_path / "walk"),
                           "--output", str(tmp_path / "search"), "--repositories", str(repositories)],
                          cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    result = assert_search_folder_valid(tmp_path / "search")
    revisions = [change["id"] for change in stored(tmp_path / "search" / "changes.json")["changes"]]
    a, b, c, _ = revisions
    assert [entry["revisions"] for entry in result["contributions"]] == [[c]]
    steps = stored(tmp_path / "walk" / "walk.result.json")["steps"]
    moved = [[x["quantity"] for x in step["contributions"] if x["contributes"]] for step in steps[:2]]
    assert moved[0] and moved[1]
    assert result["missed"] == ([{"revision": a, "quantity": q} for q in moved[0]]
                                + [{"revision": b, "quantity": q} for q in moved[1]])
    assert result["runs"]["saved"] >= 1
    # The clone, the record folders, and the walk folder are as they were.
    assert clone_state(clone) == state
    assert {n: folder_hashes(p.parent) for n, p in records.items()} == before
    assert folder_hashes(tmp_path / "walk") == walk_hashes


def test_a_walk_runs_on_the_path_of_the_older_record_and_a_walk_on_another_path_is_refused(
        tmp_path, monkeypatch, capsys):
    """Two model points and one revision; the records run on the export path, the default."""
    from degelmann.deltarecon.engines.reference_model import ReferenceModel, engine_version
    repositories, clone = throwaway(tmp_path)
    lines = (clone / POINT_TABLE).read_text("utf-8").splitlines(keepends=True)
    write_files(clone, {POINT_TABLE: lines[0] + lines[1] + lines[2]})
    base = commit(clone, "Keep two model points")
    lapse = (clone / LAPSE_TABLE).read_text("utf-8")
    write_files(clone, {LAPSE_TABLE: lapse.replace("\n2,0.04,", "\n2,0.02,")})
    newest = commit(clone, "Halve the lapse rate of policy year 2")
    records = {}
    for name, revision in (("older", base), ("newer", newest)):
        folder = tmp_path / name
        assert main(["request", "--revision", revision, "--repositories", str(repositories), "--label", name,
                     "--run-id", f"run-{name}", "--output", str(folder / "request.json")]) == 0
        assert main(["run", str(folder / "request.json"), "--repositories", str(repositories)]) == 0
        records[name] = str(folder / "run-record.json")

    def walk_on(output: str) -> None:
        assert main(["walk", records["older"], records["newer"], "--output", str(tmp_path / output),
                     "--repositories", str(repositories)]) == 0

    def versions(output: str) -> set[str]:
        return {reference["value"] for state in ("state-00", "state-01")
                for reference in stored(tmp_path / output / state / "request.json")["release"]["references"]
                if reference["kind"] == "engine_version"}

    walk_on("walk")
    assert versions("walk") == {engine_version("export")}
    # The same two records walked by an engine that names the modelx path for every state.
    real = ReferenceModel.state_release

    def on_modelx(self, base, revision, hold, repositories):
        state = real(self, base, revision, hold, repositories)
        return {**state, "references": [{**r, "value": engine_version("modelx")} if r["kind"] == "engine_version"
                                        else r for r in state["references"]]}

    with monkeypatch.context() as patch:
        patch.setattr(ReferenceModel, "state_release", on_modelx)
        walk_on("walk-modelx")
    assert versions("walk-modelx") == {engine_version("modelx")}
    capsys.readouterr()
    before = folder_hashes(tmp_path / "walk-modelx")
    assert main(["search", records["older"], records["newer"], "--output", str(tmp_path / "refused"),
                 "--repositories", str(repositories), "--walk", str(tmp_path / "walk-modelx")]) == 1
    out = capsys.readouterr().out
    assert out.startswith("search: rejected") and "diagnostic: walk_mismatch: " in out
    assert not (tmp_path / "refused").exists() and folder_hashes(tmp_path / "walk-modelx") == before
    # The walk on the path of the older record is a reference.
    assert main(["search", records["older"], records["newer"], "--output", str(tmp_path / "search"),
                 "--repositories", str(repositories), "--walk", str(tmp_path / "walk")]) == 0
    assert versions("search") == {engine_version("export")}


# --- target-only inner states ------------------------------------------------------------

# The search result of the targeted search and of the search without a target over HISTORY, checked against
# the walk, as the code before the switch target_only wrote them: a search without the switch keeps its bytes.
SWITCH_OFF_RESULTS = {
    "target": "706582bb4a41248a6a99294fe7c09a9f4e635dc88217c5fed1a92366249c2f56",
    "every-coordinate": "bc3af57bdd2215c64f13dd4d6fe5a5abebd38023bc599436306032227154faf2",
}
# Revision 1 changes the count of MP-B; revision 3 the cash flow alone.
ENDS = (
    ("y0", "The base.\n", (), POINTS, PARAMS),
    ("y1", "Raise MP-B\n", ("data",), POINTS_B, PARAMS),
    ("y2", "Touch nothing\n", (), POINTS_B, PARAMS),
    ("y3", "Raise the rate\n", ("parameter",), POINTS_B, PARAMS_RATE),
    ("y4", "Touch nothing again\n", (), POINTS_B, PARAMS_RATE),
)


def state_requests(folder: Path) -> dict[int, dict]:
    """The requests of the states the search ran, by state."""
    return {int(path.parent.name.split("-")[1]): stored(path) for path in folder.glob("state-*/request.json")}


def kept_request(folder: Path, entry: dict) -> dict:
    return stored(folder / entry["compare"]["result"]["path"].replace(".result.", ".request."))


@pytest.mark.parametrize("options", [{"quantities": [COUNT], "periods": "0-2"}, {}],
                         ids=["target", "every-coordinate"])
def test_a_search_without_the_switch_writes_the_bytes_it_wrote_before(world, options):
    # The pins were taken under contract version 3.0; written under 3.0, every byte is the same.
    with written_under("3.0"):
        build(world, HISTORY)
        (world / "tolerance.json").write_text(json.dumps(PROFILE), "utf-8")
        older = record(world, "h0", WalkStub(HISTORY), label="N", contract_version="3.0")
        newer = record(world, "h8", WalkStub(HISTORY), label="N+1", contract_version="3.0")
        run_walk(world, older, newer, WalkStub(HISTORY), tolerance=world / "tolerance.json")
        done = run_search(world, older, newer, WalkStub(HISTORY), tolerance=world / "tolerance.json",
                          walk=world / "walk", **options)
    name = "target" if options else "every-coordinate"
    assert sha256_file(done.result_path) == SWITCH_OFF_RESULTS[name]
    assert not list((world / "search").glob("*.target"))
    assert all("target" not in request for request in state_requests(world / "search").values())


def test_target_only_inner_states_find_what_the_search_finds(history, monkeypatch, capsys):
    world, older, newer = history
    tolerance = world / "tolerance.json"
    run_walk(world, older, newer, WalkStub(HISTORY), tolerance=tolerance)
    full = run_search(world, older, newer, WalkStub(HISTORY), tolerance=tolerance, walk=world / "walk",
                      quantities=[COUNT], periods="0-2").result
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: WalkStub(HISTORY))
    assert main(["search", str(older), str(newer), "--output", str(world / "targeted"), "--repositories", str(world),
                 "--quantity", COUNT, "--periods", "0-2", "--tolerance", str(tolerance), "--walk", str(world / "walk"),
                 "--target-only"]) == 0
    assert "inner states: run on the target only, without the model checks" in capsys.readouterr().out
    folder = world / "targeted"
    targeted = assert_search_folder_valid(folder)
    assert_same_search(targeted, full)
    assert targeted["runs"] == full["runs"] and targeted["states"][0]["run_id"] == full["states"][0]["run_id"]
    record = stored(folder / "search.run-record.json")
    assert targeted["switches"] == record["switches"] == ["target_only"]
    # The inner states carry the target in request and response; the two ends are full runs.
    n = len(HISTORY) - 1
    requests = state_requests(folder)
    assert sorted(requests) == [s["state"] for s in targeted["states"]]
    for k, request in requests.items():
        response = stored(folder / f"state-{k:02d}" / "response.json")
        if k in (0, n):
            assert "target" not in request and "target" not in response
            assert [q["name"] for q in response["quantities"]] == [COUNT, CASH]
        else:
            assert request["target"] == response["target"] == targeted["target"]
            assert [q["name"] for q in response["quantities"]] == [COUNT]
    # The comparison kept for the contribution (6, 7) is between two target-only runs, on the target profile.
    (entry,) = targeted["contributions"]
    request = kept_request(folder, entry)
    assert request["left"]["response"]["path"] == "state-06/response.json"
    assert request["right"]["run_record"]["path"] == "state-07/run-record.json"
    assert request["tolerance"] == PROFILE
    compared = stored(folder / entry["compare"]["result"]["path"])
    assert compared["outcome"] == "compared" and [q["name"] for q in compared["quantities"]] == [COUNT]
    assert not list(folder.glob("*.target"))  # no full state is compared: no target view


def test_a_contribution_at_an_end_is_kept_on_the_target_view_of_the_end(world):
    build(world, ENDS)
    engine = WalkStub(ENDS)
    older, newer = record(world, "y0", engine, label="N"), record(world, "y4", engine, label="N+1")
    options = {"quantities": [COUNT], "periods": "0-1"}
    full = run_search(world, older, newer, WalkStub(ENDS), **options).result
    targeted = run_search(world, older, newer, WalkStub(ENDS), output="targeted", target_only=True, **options).result
    folder = world / "targeted"
    assert assert_search_folder_valid(folder) == targeted
    for member in ("ends", "target", "intervals", "contributions", "findings", "runs"):
        assert without_compare(targeted[member]) == without_compare(full[member]), member
    (entry,) = targeted["contributions"]
    assert (entry["from_state"], entry["to_state"], entry["revisions"]) == (0, 1, ["y1"])
    request = kept_request(folder, entry)
    assert request["left"] == {"response": {"path": "state-00.target/response.json",
                                            "sha256": sha256_file(folder / "state-00.target" / "response.json")}}
    assert request["right"]["response"]["path"] == "state-01/response.json" and "run_record" in request["right"]
    compared = stored(folder / entry["compare"]["result"]["path"])
    assert compared["outcome"] == "compared" and "parameter_diff" not in compared
    assert sorted(path.name for path in (folder / "state-00.target").iterdir()) == ["response.json", "results.csv"]
    # The view is what a target-only run of state 0 returns, but for its run id, and is no run.
    view = stored(folder / "state-00.target" / "response.json")
    state = stored(folder / "state-00" / "request.json")
    again = world / "again"
    again.mkdir()
    (again / "request.json").write_bytes(document_bytes({**state, "target": targeted["target"]}))
    ran = run_request(again / "request.json", WalkStub(ENDS), repositories=world)
    assert ran.outcome == "succeeded"
    assert view == {**ran.response, "run_id": state["run_id"]}
    assert (folder / "state-00.target" / "results.csv").read_bytes() == (again / "results.csv").read_bytes()
    assert view["model_points"] == [{"model_point_id": "MP-A", "first_period": 12, "last_period": 13},
                                    {"model_point_id": "MP-B", "first_period": 0, "last_period": 1},
                                    {"model_point_id": "MP-C", "first_period": 0, "last_period": 0},
                                    {"model_point_id": "MP-D", "first_period": 3, "last_period": 4}]
    assert all(s["outcome"] == "succeeded" for s in targeted["states"])


def test_both_switches_run_no_state_and_keep_comparisons_on_target_views(history):
    world, older, newer = history
    tolerance = world / "tolerance.json"
    run_walk(world, older, newer, WalkStub(HISTORY), tolerance=tolerance)
    options = {"quantities": [COUNT], "periods": "0-2", "tolerance": tolerance, "walk": world / "walk"}
    full = run_search(world, older, newer, WalkStub(HISTORY), **options).result
    engine = Counting(HISTORY)
    both = run_search(world, older, newer, engine, output="both", reuse=True, target_only=True, **options).result
    assert engine.calls == 0
    folder = world / "both"
    assert assert_search_folder_valid(folder) == both
    assert_same_search(both, full)
    assert both["switches"] == stored(folder / "search.run-record.json")["switches"] == ["reuse_walk", "target_only"]
    assert both["runs"]["search"] == 0
    for entry in both["contributions"]:
        request = kept_request(folder, entry)
        for side, k in (("left", entry["from_state"]), ("right", entry["to_state"])):
            assert request[side] == {"response": {
                "path": f"state-{k:02d}.target/response.json",
                "sha256": sha256_file(folder / f"state-{k:02d}.target" / "response.json")}}
            assert stored(folder / request[side]["response"]["path"])["target"] == both["target"]
        assert stored(folder / entry["compare"]["result"]["path"])["outcome"] == "compared"


def test_the_switch_target_only_without_a_narrowed_target_is_a_usage_error(history, monkeypatch, capsys):
    world, older, newer = history
    before = folder_hashes(world)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: WalkStub(HISTORY))
    assert main(["search", str(older), str(newer), "--output", str(world / "search"), "--repositories", str(world),
                 "--target-only"]) == 2
    error = capsys.readouterr().err
    assert all(flag in error for flag in ("--target-only", "--quantity", "--periods"))
    assert main(["search", str(older), str(newer), "--output", str(world / "search"), "--repositories", str(world),
                 "--quantity", COUNT, "--quantity", CASH, "--target-only"]) == 2
    assert "target_only" in capsys.readouterr().err
    assert folder_hashes(world) == before and not (world / "search").exists()
    with pytest.raises(UsageError) as raised:  # every quantity named, no periods: a library caller is told the switch
        run_search(world, older, newer, WalkStub(HISTORY), quantities=[COUNT, CASH], target_only=True)
    assert "target_only" in str(raised.value) and "--" not in str(raised.value)
    assert not (world / "search").exists()


@pytest.mark.parametrize("reuse", [False, True], ids=["target-only", "both-switches"])
def test_on_a_valuation_origin_basis_target_windows_are_the_target_periods_as_they_are(world, reuse):
    build(world, VALUATION)
    engine = ValuationStub(VALUATION)
    older, newer = record(world, "v0", engine, label="N"), record(world, "v2", engine, label="N+1")
    run_walk(world, older, newer, ValuationStub(VALUATION))
    options = {"quantities": [COUNT], "periods": "1-2", "walk": world / "walk"}
    full = run_search(world, older, newer, ValuationStub(VALUATION), **options).result
    targeted = run_search(world, older, newer, ValuationStub(VALUATION), output="targeted", target_only=True,
                          reuse=reuse, **options).result
    folder = world / "targeted"
    assert assert_search_folder_valid(folder) == targeted
    assert_same_search(targeted, full)
    # The end state 2 is compared through its view: A's period 2 alone; B starts at period 3.
    view = stored(folder / "state-02.target" / "response.json")
    assert view["model_points"] == [{"model_point_id": "MP-A", "first_period": 2, "last_period": 2}]
    if not reuse:
        inner = stored(folder / "state-01" / "response.json")
        assert inner["model_points"] == view["model_points"] and inner["target"] == view["target"]
