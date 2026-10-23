"""Contract versions: the tool writes 2.0 and reads 1.0 and 2.0 (``contracts/v2/README.md``,
"Version compatibility").

Genuine 1.0 documents are written by the tool itself under :func:`conftest.written_under`, so their
hashes agree. Each row of the version rows of the I/O matrix of the plan of the story "Fix the search
contribution invariant and release the next contract version" has a test here; the rows of the search
are in ``test_search.py``.
"""
from __future__ import annotations

import pytest

from degelmann.deltarecon.compare import compare
from degelmann.deltarecon.derive import derive
from degelmann.deltarecon.documents import (CHANGES_SCHEMA, CONTRACT_VERSION, RECORD_SCHEMA, RUN_REQUEST, Rejection,
                                            check_version, document_bytes, read_document, schema_errors, validator)
from degelmann.deltarecon.replay import read_recorded_run, replay
from degelmann.deltarecon.search import search
from degelmann.deltarecon.walk import walk

from conftest import (CANCEL, CASH, LINE, POINTS_B, StubEngine, WalkStub, assert_documents_valid, build,
                      compare_request, folder_hashes, record, run_side, run_stub, stored, stub_regression,
                      stub_release, stub_request, written_under)


def versions(folder) -> set[str]:
    """The contract versions of every document below ``folder``."""
    return {stored(path)["contract_version"] for path in folder.rglob("*.json")
            if "contract_version" in stored(path)}


def recorded_under_1_0(world, folder: str = "run"):
    """A succeeded stub run whose request, response, and run record are documents of version 1.0."""
    with written_under("1.0"):
        result, _ = run_stub(world, stub_request(world, contract_version="1.0"), folder=folder)
    assert result.outcome == "succeeded"
    assert versions(world / folder) == {"1.0"}
    return result


def test_the_tool_writes_2_0_and_reads_1_0_and_2_0():
    assert CONTRACT_VERSION == "2.0"
    for version in ("1.0", "2.0"):
        check_version({"contract_version": version})
    check_version({})  # a missing version is a schema fault, found by the schema


@pytest.mark.parametrize("version", ["3.0", "1.1", "2.1", "1", 1.0, ["2.0"], {"major": 2}])
def test_another_version_is_rejected_before_the_schema(world, version):
    with pytest.raises(Rejection) as caught:
        check_version({"contract_version": version})
    assert caught.value.code == "unsupported_version"
    result, _ = run_stub(world, stub_request(world, contract_version=version, selection={"mode": "none"}))
    assert result.outcome == "rejected"
    assert [d["code"] for d in result.response["diagnostics"]] == ["unsupported_version"]


def test_a_record_of_another_version_is_rejected(world):
    result = recorded_under_1_0(world)
    path = result.record_path
    record = stored(path)
    record["contract_version"] = "1.1"
    path.write_bytes(document_bytes(record))
    with pytest.raises(Rejection) as caught:
        read_recorded_run(path, StubEngine().stages)
    assert caught.value.code == "unsupported_version"


# --- requests of version 1.0 ----------------------------------------------------------------


def test_a_1_0_run_request_is_accepted_and_answered_under_2_0(world):
    result, _ = run_stub(world, stub_request(world, contract_version="1.0"))
    assert result.outcome == "succeeded"
    folder = world / "run"
    assert_documents_valid(folder)
    assert stored(folder / "request.json")["contract_version"] == "1.0"
    assert stored(folder / "response.json")["contract_version"] == "2.0"
    assert stored(folder / "run-record.json")["contract_version"] == "2.0"


def test_a_schema_fault_of_a_1_0_request_is_reported_against_the_1_0_schema(world):
    request = stub_request(world, contract_version="1.0", priority="high")
    # The fault the reader names is that of the 1.0 schema; the 2.0 schema also refuses the version.
    under_1_0 = sorted(e.message for e in validator(RUN_REQUEST, "1.0").iter_errors(request))
    under_2_0 = sorted(e.message for e in validator(RUN_REQUEST, "2.0").iter_errors(request))
    assert len(under_1_0) == 1 and "priority" in under_1_0[0] and len(under_2_0) > len(under_1_0)
    assert schema_errors(request, RUN_REQUEST) == [f"(document): {under_1_0[0]}"]
    result, _ = run_stub(world, request)
    assert result.outcome == "rejected"
    (diagnostic,) = result.response["diagnostics"]
    assert diagnostic["code"] == "schema_violation" and "priority" in diagnostic["message"]
    assert "'2.0' was expected" not in diagnostic["message"]
    assert result.response["contract_version"] == "2.0"


def test_a_1_0_compare_request_is_accepted_and_answered_under_2_0(world):
    run_side(world, "left")
    run_side(world, "right", points=POINTS_B)
    compared = compare(compare_request(world, contract_version="1.0"))
    assert compared.result["outcome"] == "compared" and compared.result["contract_version"] == "2.0"
    for name in ("compare.result.json", "signature-table.json", "compare.run-record.json"):
        assert stored(world / name)["contract_version"] == "2.0", name


# --- run records of version 1.0 as input ---------------------------------------------------


def test_a_1_0_record_is_read_by_the_regression(world):
    recorded_under_1_0(world)
    before = folder_hashes(world / "run")
    done = stub_regression(world, stub_release(world, "rel-new", POINTS_B))
    out = world / "out"
    assert done.run.outcome == "succeeded" and not done.no_deviation
    assert folder_hashes(out / "recorded") == before
    assert versions(out / "recorded") == {"1.0"}
    assert versions(out / "run") == {"2.0"}
    for name in ("compare.request.json", "compare.result.json", "signature-table.json", "compare.run-record.json"):
        assert stored(out / name)["contract_version"] == "2.0", name


def test_a_compare_of_recorded_runs_of_version_1_0(world):
    with written_under("1.0"):
        run_side(world, "left", contract_version="1.0")
        run_side(world, "right", points=POINTS_B, contract_version="1.0")
    assert versions(world / "left") == versions(world / "right") == {"1.0"}
    compared = compare(compare_request(world))
    assert compared.result["outcome"] == "compared" and compared.result["deviating_model_points"] == ["MP-B"]
    assert stored(world / "compare.run-record.json")["contract_version"] == "2.0"


def test_1_0_records_are_read_by_derive_and_walk(world):
    build(world)
    with written_under("1.0"):
        older = record(world, "w0", label="N", contract_version="1.0")
        newer = record(world, "w4", label="N+1", contract_version="1.0")
    assert stored(older)["contract_version"] == stored(newer)["contract_version"] == "1.0"
    manifest = derive(older, newer, world / "changes.json", WalkStub(), repositories=world).manifest
    assert manifest["contract_version"] == "2.0"
    assert read_document(world / "changes.json", CHANGES_SCHEMA) == manifest
    walked = walk(older, newer, world / "walk", WalkStub(), repositories=world)
    assert walked.attributed
    folder = world / "walk"
    assert stored(folder / "walk.result.json")["contract_version"] == "2.0"
    assert read_document(folder / "walk.run-record.json", RECORD_SCHEMA)["contract_version"] == "2.0"
    # Only the copies of the two records keep their version.
    assert versions(folder / "older") == versions(folder / "newer") == {"1.0"}
    assert len(walked.result["steps"]) == len(LINE) - 1


def test_1_0_records_are_read_by_a_search_checked_against_their_walk(world):
    build(world, CANCEL)
    with written_under("1.0"):
        older = record(world, "c0", WalkStub(CANCEL), label="N", contract_version="1.0")
        newer = record(world, "c4", WalkStub(CANCEL), label="N+1", contract_version="1.0")
    assert stored(older)["contract_version"] == stored(newer)["contract_version"] == "1.0"
    assert walk(older, newer, world / "walk", WalkStub(CANCEL), repositories=world).attributed
    done = search(older, newer, world / "search", WalkStub(CANCEL), repositories=world, walk=world / "walk")
    assert done.searched and done.result["contract_version"] == "2.0"
    assert [c["revisions"] for c in done.result["contributions"]] == [["c3"]]
    assert done.result["missed"] == [{"revision": "c1", "quantity": CASH}, {"revision": "c2", "quantity": CASH}]
    assert read_document(world / "search" / "search.run-record.json", RECORD_SCHEMA)["contract_version"] == "2.0"


# --- no replay of version 1.0 ----------------------------------------------------------------


def test_the_replay_rejects_a_1_0_record_and_writes_nothing(world):
    result = recorded_under_1_0(world)
    before = folder_hashes(world / "run")
    with pytest.raises(Rejection) as caught:
        replay(result.record_path, StubEngine(), repositories=world)
    assert caught.value.code == "unsupported_version"
    assert folder_hashes(world / "run") == before


def test_the_replay_repeats_a_2_0_record_of_a_1_0_request(world):
    result, _ = run_stub(world, stub_request(world, contract_version="1.0"))
    assert stored(result.record_path)["contract_version"] == "2.0"
    assert replay(result.record_path, StubEngine(), repositories=world).outcome == "reproduced_exactly"
