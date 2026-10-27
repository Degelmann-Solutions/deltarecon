"""Contract versions: the tool writes 3.0 and reads 1.0, 2.0, and 3.0 (``contracts/v3/README.md``,
"Version compatibility").

Genuine documents of an earlier version are written by the tool itself under
:func:`conftest.written_under`, so their hashes agree. Each version row of the I/O matrices of the plans
of the stories "Fix the search contribution invariant and release the next contract version" (1.0) and
"Open the next contract version and archive the oracle" (2.0) has a test here; the rows of the search
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

from conftest import (CANCEL, CASH, LINE, POINTS_B, StubEngine, StubSession, WalkStub, assert_documents_valid, build,
                      compare_request, folder_hashes, record, run_side, run_stub, stored, stub_regression,
                      stub_release, stub_request, written_under)

# The earlier versions the tool reads; each is read against the schemas of its own pack.
EARLIER = ["1.0", "2.0"]


def versions(folder) -> set[str]:
    """The contract versions of every document below ``folder``."""
    return {stored(path)["contract_version"] for path in folder.rglob("*.json")
            if "contract_version" in stored(path)}


def recorded_under(world, version: str, folder: str = "run"):
    """A succeeded stub run whose request, response, and run record are documents of ``version``."""
    with written_under(version):
        result, _ = run_stub(world, stub_request(world, contract_version=version), folder=folder)
    assert result.outcome == "succeeded"
    assert versions(world / folder) == {version}
    return result


def test_the_tool_writes_3_0_and_reads_1_0_2_0_and_3_0():
    assert CONTRACT_VERSION == "3.0"
    for version in ("1.0", "2.0", "3.0"):
        check_version({"contract_version": version})
    check_version({})  # a missing version is a schema fault, found by the schema


@pytest.mark.parametrize("version", ["4.0", "3.1", "2.1", "1.1", "3", "1", 3.0, 1.0, ["3.0"], {"major": 3}])
def test_another_version_is_rejected_before_the_schema(world, version):
    with pytest.raises(Rejection) as caught:
        check_version({"contract_version": version})
    assert caught.value.code == "unsupported_version"
    result, _ = run_stub(world, stub_request(world, contract_version=version, selection={"mode": "none"}))
    assert result.outcome == "rejected"
    assert [d["code"] for d in result.response["diagnostics"]] == ["unsupported_version"]


@pytest.mark.parametrize("version", EARLIER)
def test_a_record_of_another_version_is_rejected(world, version):
    result = recorded_under(world, version)
    path = result.record_path
    record = stored(path)
    record["contract_version"] = version[0] + ".1"
    path.write_bytes(document_bytes(record))
    with pytest.raises(Rejection) as caught:
        read_recorded_run(path, StubEngine().stages)
    assert caught.value.code == "unsupported_version"


# --- requests of an earlier version ---------------------------------------------------------


@pytest.mark.parametrize("version", EARLIER)
def test_an_earlier_run_request_is_accepted_and_answered_under_3_0(world, version):
    result, _ = run_stub(world, stub_request(world, contract_version=version))
    assert result.outcome == "succeeded"
    folder = world / "run"
    assert_documents_valid(folder)
    assert stored(folder / "request.json")["contract_version"] == version
    assert stored(folder / "response.json")["contract_version"] == "3.0"
    assert stored(folder / "run-record.json")["contract_version"] == "3.0"


@pytest.mark.parametrize("version", EARLIER)
def test_a_schema_fault_of_an_earlier_request_is_reported_against_its_own_schema(world, version):
    request = stub_request(world, contract_version=version, priority="high")
    # The fault the reader names is that of the schema of its version; the 3.0 schema also refuses
    # the version.
    under_own = sorted(e.message for e in validator(RUN_REQUEST, version).iter_errors(request))
    under_3_0 = sorted(e.message for e in validator(RUN_REQUEST, "3.0").iter_errors(request))
    assert len(under_own) == 1 and "priority" in under_own[0] and len(under_3_0) > len(under_own)
    assert schema_errors(request, RUN_REQUEST) == [f"(document): {under_own[0]}"]
    result, _ = run_stub(world, request)
    assert result.outcome == "rejected"
    (diagnostic,) = result.response["diagnostics"]
    assert diagnostic["code"] == "schema_violation" and "priority" in diagnostic["message"]
    assert "'3.0' was expected" not in diagnostic["message"]
    assert result.response["contract_version"] == "3.0"


@pytest.mark.parametrize("version", EARLIER)
def test_an_earlier_compare_request_is_accepted_and_answered_under_3_0(world, version):
    run_side(world, "left")
    run_side(world, "right", points=POINTS_B)
    compared = compare(compare_request(world, contract_version=version))
    assert compared.result["outcome"] == "compared" and compared.result["contract_version"] == "3.0"
    assert stored(world / "compare.request.json")["contract_version"] == version
    for name in ("compare.result.json", "signature-table.json", "compare.run-record.json"):
        assert stored(world / name)["contract_version"] == "3.0", name


# --- run records of an earlier version as input ---------------------------------------------


@pytest.mark.parametrize("version", EARLIER)
def test_an_earlier_record_is_read_by_the_regression(world, version):
    recorded_under(world, version)
    before = folder_hashes(world / "run")
    done = stub_regression(world, stub_release(world, "rel-new", POINTS_B))
    out = world / "out"
    assert done.run.outcome == "succeeded" and not done.no_deviation
    assert folder_hashes(out / "recorded") == before
    assert versions(out / "recorded") == {version}
    assert versions(out / "run") == {"3.0"}
    for name in ("compare.request.json", "compare.result.json", "signature-table.json", "compare.run-record.json"):
        assert stored(out / name)["contract_version"] == "3.0", name


@pytest.mark.parametrize("version", EARLIER)
def test_a_compare_of_recorded_runs_of_an_earlier_version(world, version):
    with written_under(version):
        run_side(world, "left", contract_version=version)
        run_side(world, "right", points=POINTS_B, contract_version=version)
    assert versions(world / "left") == versions(world / "right") == {version}
    compared = compare(compare_request(world))
    assert compared.result["outcome"] == "compared" and compared.result["deviating_model_points"] == ["MP-B"]
    assert stored(world / "compare.run-record.json")["contract_version"] == "3.0"


@pytest.mark.parametrize("version", EARLIER)
def test_earlier_records_are_read_by_derive_and_walk(world, version):
    build(world)
    with written_under(version):
        older = record(world, "w0", label="N", contract_version=version)
        newer = record(world, "w4", label="N+1", contract_version=version)
    assert stored(older)["contract_version"] == stored(newer)["contract_version"] == version
    manifest = derive(older, newer, world / "changes.json", WalkStub(), repositories=world).manifest
    assert manifest["contract_version"] == "3.0"
    assert read_document(world / "changes.json", CHANGES_SCHEMA) == manifest
    walked = walk(older, newer, world / "walk", WalkStub(), repositories=world)
    assert walked.attributed
    folder = world / "walk"
    assert stored(folder / "walk.result.json")["contract_version"] == "3.0"
    assert read_document(folder / "walk.run-record.json", RECORD_SCHEMA)["contract_version"] == "3.0"
    # Only the copies of the two records keep their version.
    assert versions(folder / "older") == versions(folder / "newer") == {version}
    assert len(walked.result["steps"]) == len(LINE) - 1


@pytest.mark.parametrize("version", EARLIER)
def test_earlier_records_are_read_by_a_search_checked_against_their_walk(world, version):
    build(world, CANCEL)
    with written_under(version):
        older = record(world, "c0", WalkStub(CANCEL), label="N", contract_version=version)
        newer = record(world, "c4", WalkStub(CANCEL), label="N+1", contract_version=version)
    assert stored(older)["contract_version"] == stored(newer)["contract_version"] == version
    assert walk(older, newer, world / "walk", WalkStub(CANCEL), repositories=world).attributed
    done = search(older, newer, world / "search", WalkStub(CANCEL), repositories=world, walk=world / "walk")
    assert done.searched and done.result["contract_version"] == "3.0"
    assert [c["revisions"] for c in done.result["contributions"]] == [["c3"]]
    assert done.result["missed"] == [{"revision": "c1", "quantity": CASH}, {"revision": "c2", "quantity": CASH}]
    assert read_document(world / "search" / "search.run-record.json", RECORD_SCHEMA)["contract_version"] == "3.0"


# --- replay: 2.0 and 3.0, not 1.0 ------------------------------------------------------------


def test_the_replay_rejects_a_1_0_record_and_writes_nothing(world):
    result = recorded_under(world, "1.0")
    before = folder_hashes(world / "run")
    with pytest.raises(Rejection) as caught:
        replay(result.record_path, StubEngine(), repositories=world)
    assert caught.value.code == "unsupported_version"
    assert folder_hashes(world / "run") == before


def test_the_replay_repeats_a_2_0_record(world):
    result = recorded_under(world, "2.0")
    assert replay(result.record_path, StubEngine(), repositories=world).outcome == "reproduced_exactly"
    assert stored(world / "run" / "replay-record.json")["contract_version"] == "3.0"


@pytest.mark.parametrize("version", EARLIER)
def test_the_replay_repeats_a_3_0_record_of_an_earlier_request(world, version):
    result, _ = run_stub(world, stub_request(world, contract_version=version))
    assert stored(result.record_path)["contract_version"] == "3.0"
    assert replay(result.record_path, StubEngine(), repositories=world).outcome == "reproduced_exactly"


def recorded_error_under_2_0(world):
    """A stub run recorded under 2.0 that ends with an error: the points table holds no model point."""
    (world / "rel" / "points.csv").write_text("id,first,last,base\n", "utf-8")
    with written_under("2.0"):
        result, _ = run_stub(world, stub_request(world, contract_version="2.0"))
    assert result.outcome == "error" and versions(world / "run") == {"2.0"}
    return result


def test_the_replay_reproduces_a_2_0_error_record_whose_response_differs_in_the_version_only(world):
    result = recorded_error_under_2_0(world)
    done = replay(result.record_path, StubEngine(), repositories=world)
    assert done.outcome == "reproduced_exactly"
    repeated = stored(world / "run" / "replay" / "response.json")
    assert repeated["contract_version"] == "3.0"
    assert document_bytes({**repeated, "contract_version": "2.0"}) == (world / "run" / "response.json").read_bytes()


def test_the_replay_does_not_reproduce_a_2_0_error_record_whose_response_differs_otherwise(world, monkeypatch):
    result = recorded_error_under_2_0(world)
    monkeypatch.setattr(StubSession, "model_point_ids", lambda self: ["MP-A", 7])  # another error
    assert replay(result.record_path, StubEngine(), repositories=world).outcome == "not_reproduced"
