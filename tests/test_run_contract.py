"""The run contract as implemented by ``degelmann.deltarecon``: run, run record, replay, and regression.

The core rows of the matrix run against a stub engine through the engine protocol, so
they need no calculation engine. The rows that concern the reference model name a release
by a commit: the pinned first commit of the clone ``repositories/delib-history``, or a commit
of a throw-away clone. They use subset runs of a few model points, and one chain of a full
run and its replay (``conftest.py``).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from contextlib import contextmanager
from pathlib import Path

import pytest

from degelmann.deltarecon import changes as changes_contract
from degelmann.deltarecon.__main__ import main
from degelmann.deltarecon.documents import (CHANGES_SCHEMA, RECORD_SCHEMA, RUN_REQUEST, RUN_SCHEMA, Rejection,
                                  document_bytes, read_document, schema_errors, sha256_file)
from degelmann.deltarecon.export import (check_export, export_bytes, export_errors, format_number,
                               is_profile_number, read_export)
from degelmann.deltarecon.compare import COMPARE_SCHEMA
from degelmann.deltarecon.regression import read_regression_input, regression
from degelmann.deltarecon.replay import check_response, replay
from degelmann.deltarecon.run import SCRATCH_PREFIX, ModelPointFailure, UsageError, run_request

from conftest import (CLONE, CLONE_NAME, EXACT, LAPSE_TABLE, MODEL_CODE, NEW_BUSINESS, PARAMS, PARAMS_RATE,
                      POINTS, POINTS_B, POINT_TABLE, PRODUCT_FOLDER, RECORD_ID, RELEASE_N, REPOSITORIES, START,
                      REPOSITORY_URL, ROOT, StubEngine, StubSession, assert_documents_valid, change, cli,
                      clone_state, commit, committed, deviation_rows, edit_file, expected_deviations,
                      folder_hashes, git, patch_text, rehash, require_clone, roles, run_stub, stored,
                      stub_regression, stub_release, stub_request, text, throwaway, with_columns, with_manifest,
                      model_request, without_volatile, written_under)

CORE_MODULES = ["errors", "documents", "export", "changes", "run", "compare", "signature", "replay", "regression",
                "derive", "walk", "search", "workers", "__main__"]
POINTS_PLUS_E = POINTS + "MP-E,0,1,7\n"


# --- full and subset runs -----------------------------------------------------------


def test_full_run_exports_every_model_point_and_writes_the_record(world):
    before = folder_hashes(world / "rel")
    result, _ = run_stub(world)
    folder = world / "run"
    assert result.outcome == "succeeded"
    assert sorted(p.name for p in folder.iterdir()) == [
        "request.json", "response.json", "results.csv", "run-record.json"]
    assert_documents_valid(folder)

    response, record, request = stored(folder / "response.json"), stored(folder / "run-record.json"), \
        stored(folder / "request.json")
    for member in ("stage", "run_id", "release", "changes", "selection"):
        assert response[member] == request[member]
    assert response["contract_version"] == record["contract_version"] == "3.1"
    assert response["time_basis"] == {"id": "policy_month"}
    assert response["model_points"] == [
        {"model_point_id": "MP-A", "first_period": 12, "last_period": 13},
        {"model_point_id": "MP-B", "first_period": 0, "last_period": 2},
        {"model_point_id": "MP-C", "first_period": 0, "last_period": 0},
        {"model_point_id": "MP-D", "first_period": 3, "last_period": 4}]
    assert response["export"]["data_rows"] == 8

    assert record["stage"] == "liability_cashflow" and record["procedure"] == {"type": "run"}
    assert RECORD_ID.fullmatch(record["record_id"]) and record["outcome"] == "succeeded"
    assert record["releases"] == [request["release"]] and "recorded_at" in record
    assert roles(record["inputs"]) == {"request": "request.json"}
    assert roles(record["outputs"]) == {"response": "response.json", "export": "results.csv"}
    assert record["parameters"] == [{"name": "label", "type": "scalar", "value": "base"},
                                    {"name": "rate", "type": "scalar", "value": 0.01}]

    # The export is in writer form and in deterministic order, and the result is complete.
    assert (folder / "results.csv").read_text("utf-8") == (
        "model_point_id,period,Anzahl Verträge,Netto-Cashflow\n"
        "MP-A,12,1.5,19.5\nMP-A,13,1.5,21\nMP-B,0,2,2\nMP-B,1,2,4\nMP-B,2,2,6\n"
        "MP-C,0,1e-5,1e-5\nMP-D,3,1e16,4e16\nMP-D,4,1e16,5e16\n")
    assert export_errors(folder / "results.csv") == []
    assert len(check_response(request, response, folder)) == 8
    assert folder_hashes(world / "rel") == before


def test_subset_run_exports_exactly_the_named_ids_with_the_values_of_the_full_run(world):
    full, _ = run_stub(world)
    request = stub_request(world, run_id="run-subset",
                           selection={"mode": "subset", "model_point_ids": ["MP-D", "MP-A"]})
    subset, _ = run_stub(world, request, folder="subset")
    assert subset.outcome == "succeeded"
    assert_documents_valid(world / "subset")
    assert [p["model_point_id"] for p in subset.response["model_points"]] == ["MP-A", "MP-D"]
    all_values = check_export(full.response, full.export_path)
    values = check_export(subset.response, subset.export_path)
    assert {key[0] for key in values} == {"MP-A", "MP-D"}
    assert values == {key: numbers for key, numbers in all_values.items() if key[0] in {"MP-A", "MP-D"}}


def test_a_run_overwrites_no_file(world):
    run_stub(world)
    before = folder_hashes(world / "run")
    with pytest.raises(UsageError):
        run_request(world / "run" / "request.json", StubEngine(), repositories=world)
    assert folder_hashes(world / "run") == before


# --- rejected requests --------------------------------------------------------------


def request_bytes(world: Path, **members) -> bytes:
    return document_bytes(stub_request(world, **members))


@pytest.mark.parametrize("case, code", [
    ("not-json", "invalid_json"), ("non-finite", "invalid_json"), ("too-large", "invalid_json"),
    ("not-an-object", "invalid_json"), ("byte-order-mark", "invalid_json"),
    ("lone-surrogate", "invalid_json"),
    ("duplicate-member", "duplicate_member"), ("wrong-version", "unsupported_version"),
    ("empty-selection", "schema_violation"), ("duplicate-selection", "schema_violation"),
    ("unknown-member", "schema_violation"), ("a-response", "schema_violation"),
    ("no-version", "schema_violation")])
def test_bad_request_is_rejected_with_the_response_alone(world, case, code):
    valid = request_bytes(world)
    text = valid.decode("utf-8")
    data = {
        "not-json": b"{ this is not JSON",
        "non-finite": text.replace('"N"', "NaN", 1).encode("utf-8"),
        "too-large": text.replace('"N"', "1e999", 1).encode("utf-8"),
        "not-an-object": b"[1, 2]\n",
        "byte-order-mark": b"\xef\xbb\xbf" + valid,
        "lone-surrogate": text.replace('"run-stub"', '"run-\\ud800"', 1).encode("utf-8"),
        "duplicate-member": text.replace('"run_id"', '"run_id": "other",\n  "run_id"', 1).encode("utf-8"),
        "wrong-version": request_bytes(world, contract_version="4.0"),
        "empty-selection": request_bytes(world, selection={"mode": "subset", "model_point_ids": []}),
        "duplicate-selection": request_bytes(
            world, selection={"mode": "subset", "model_point_ids": ["MP-A", "MP-A"]}),
        "unknown-member": request_bytes(world, priority="high"),
        "a-response": document_bytes({"document": "run_response", "contract_version": "3.1",
                                      "stage": "liability_cashflow", "run_id": "run-stub",
                                      "outcome": "rejected",
                                      "diagnostics": [{"code": "invalid_json", "message": "x"}]}),
        "no-version": document_bytes({k: v for k, v in stub_request(world).items()
                                      if k != "contract_version"}),
    }[case]
    result, engine = run_stub(world, data)
    folder = world / "run"
    assert result.outcome == "rejected" and engine.opened == 0
    assert sorted(p.name for p in folder.iterdir()) == ["request.json", "response.json"]
    response = stored(folder / "response.json")
    assert not schema_errors(response, RUN_SCHEMA)
    assert [d["code"] for d in response["diagnostics"]] == [code]
    assert response["contract_version"] == "3.1"
    # Stage and run id are repeated where they can be read.
    readable = case not in {"not-json", "non-finite", "too-large", "not-an-object", "byte-order-mark",
                            "duplicate-member", "lone-surrogate"}
    assert ("stage" in response) == readable and ("run_id" in response) == readable


def test_the_version_is_checked_before_the_schema(world):
    result, _ = run_stub(world, request_bytes(world, contract_version="4.0", selection={"mode": "none"}))
    assert result.response["diagnostics"][0]["code"] == "unsupported_version"


def test_unsupported_stage_is_rejected_with_a_record(world):
    result, engine = run_stub(world, stub_request(world, stage="asset_cashflow"))
    folder = world / "run"
    assert result.outcome == "rejected" and engine.opened == 0
    assert result.response["diagnostics"][0]["code"] == "unsupported_stage"
    assert sorted(p.name for p in folder.iterdir()) == ["request.json", "response.json", "run-record.json"]
    assert_documents_valid(folder)
    record = stored(folder / "run-record.json")
    assert record["stage"] == result.response["stage"] == "asset_cashflow"
    assert record["outcome"] == "rejected" and record["parameters"] == []
    assert roles(record["outputs"]) == {"response": "response.json"}


def test_unknown_model_point_rejects_the_whole_request(world):
    request = stub_request(world, selection={"mode": "subset",
                                             "model_point_ids": ["MP-A", "MP-9999", "MP-0000"]})
    result, _ = run_stub(world, request)
    assert result.outcome == "rejected"
    assert result.response["diagnostics"] == [{
        "code": "unknown_model_point", "message": "The release holds no model point with this id.",
        "model_point_ids": ["MP-0000", "MP-9999"]}]
    assert not (world / "run" / "results.csv").exists()  # no partial run
    assert_documents_valid(world / "run")
    assert stored(world / "run" / "run-record.json")["parameters"] == []


def test_unresolvable_release_is_rejected(world):
    request = stub_request(world)
    request["release"]["references"][1]["value"] = "points.csv sha256:" + "0" * 64
    result, engine = run_stub(world, request)
    assert result.outcome == "rejected" and engine.opened == 0
    assert result.response["diagnostics"][0]["code"] == "unknown_reference"
    assert_documents_valid(world / "run")


def test_diagnostics_follow_the_order_of_the_checks(world):
    """Stage, then release references, then the change set, then the selection."""
    broken = stub_request(world, stage="asset_cashflow",
                          changes={"enabled": ["chg"], "manifest": {"path": "none.json", "sha256": "0" * 64}},
                          selection={"mode": "subset", "model_point_ids": ["MP-9999"]})
    broken["release"]["references"][1]["value"] = "points.csv sha256:" + "0" * 64
    expected = ["unsupported_stage", "unknown_reference", "artifact_missing", "unknown_model_point"]
    for number, code in enumerate(expected):
        result, _ = run_stub(world, broken, folder=f"run-{number}")
        assert result.response["diagnostics"][0]["code"] == code
        if code == "unsupported_stage":
            broken["stage"] = "liability_cashflow"
        elif code == "unknown_reference":
            broken["release"] = stub_request(world)["release"]
        elif code == "artifact_missing":
            broken["changes"] = {"enabled": []}


# --- changes ------------------------------------------------------------------------


def test_the_core_passes_on_every_realisation_type_the_engine_declares(world):
    """The core does not cut the types down to text patches and applies no change itself."""
    class SwitchEngine(StubEngine):
        realisations = frozenset({"text_patch", "engine_switch"})

    switch = {"type": "engine_switch", "switch": "RC-1"}
    entries = [change("chg-switch", None, world / "run", realisation=switch, **{"class": "code"}),
               change("chg-point-b", patch_text("points.csv", POINTS, POINTS_B), world / "run"),
               change("chg-unused", None, world / "run", realisation={**switch, "switch": "RC-2"})]
    changes = with_manifest(world, entries, ["chg-point-b", "chg-switch"])
    result, engine = run_stub(world, stub_request(world, changes=changes), SwitchEngine())
    assert result.outcome == "succeeded"
    assert [(c["id"], c["realisation"]["type"]) for c in engine.received] == [
        ("chg-switch", "engine_switch"), ("chg-point-b", "text_patch")]
    assert check_export(result.response, result.export_path)[("MP-B", 1)] == [4, 8]
    assert replay(world / "run" / "run-record.json", SwitchEngine(), repositories=world).outcome == \
        "reproduced_exactly"

    # The same change set is rejected by an engine that does not declare the type.
    other = world / "other"
    other.mkdir()
    shutil.copytree(world / "run" / "patches", other / "patches")
    shutil.copy(world / "run" / "changes.json", other / "changes.json")
    result, engine = run_stub(world, stub_request(world, changes=changes), folder="other")
    assert result.outcome == "rejected" and engine.opened == 0
    assert result.response["diagnostics"][0]["code"] == "unsupported_realisation"
    assert result.response["diagnostics"][0]["change_ids"] == ["chg-switch"]


def test_a_file_of_any_realisation_is_checked_by_the_run_and_copied_by_the_replay(world):
    """A realisation of another type than a text patch may point to a stored file too."""
    class ReplaceEngine(StubEngine):
        realisations = frozenset({"text_patch", "file_replace"})

    def replace(change_id: str, content: str) -> dict:
        path = world / "run" / "files" / f"{change_id}.csv"
        path.parent.mkdir(exist_ok=True)
        path.write_text(content, "utf-8")
        realisation = {"type": "file_replace", "target": "points.csv",
                       "file": {"path": f"files/{change_id}.csv", "sha256": sha256_file(path)}}
        return change(change_id, None, world / "run", realisation=realisation)

    entries = [replace("chg-replace", POINTS_B), replace("chg-unused", POINTS_PLUS_E)]
    changes = with_manifest(world, entries, ["chg-replace"])
    (world / "run" / "files" / "chg-unused.csv").unlink()  # no file of a change that is not enabled is read
    result, _ = run_stub(world, stub_request(world, changes=changes), ReplaceEngine())
    assert result.outcome == "succeeded"
    assert check_export(result.response, result.export_path)[("MP-B", 1)] == [4, 8]
    record = world / "run" / "run-record.json"
    assert replay(record, ReplaceEngine(), repositories=world).outcome == "reproduced_exactly"
    assert sorted(p.name for p in (world / "run" / "replay" / "files").iterdir()) == ["chg-replace.csv"]

    # A replay with an altered file is rejected and writes nothing more.
    remove_replay(world / "run")
    (world / "run" / "files" / "chg-replace.csv").write_text(POINTS_PLUS_E, "utf-8")
    with pytest.raises(Rejection) as caught:
        replay(record, ReplaceEngine(), repositories=world)
    assert caught.value.code == "artifact_hash_mismatch" and not (world / "run" / "replay").exists()
    # And so is a run: the file is checked before the engine opens the release.
    other = world / "other"
    shutil.copytree(world / "run" / "files", other / "files")
    shutil.copy(world / "run" / "changes.json", other / "changes.json")
    result, engine = run_stub(world, stub_request(world, changes=changes), ReplaceEngine(), folder="other")
    assert result.outcome == "rejected" and engine.opened == 0
    assert result.response["diagnostics"][0]["code"] == "artifact_hash_mismatch"
    assert result.response["diagnostics"][0]["change_ids"] == ["chg-replace"]


def test_enabled_changes_are_applied_in_manifest_order_to_a_scratch_copy(world):
    base, _ = run_stub(world, folder="base")
    before = folder_hashes(world / "rel")
    entries = [
        change("chg-point-b", patch_text("points.csv", POINTS, POINTS_B), world / "run"),
        change("chg-rate", patch_text("params.csv", PARAMS, PARAMS_RATE), world / "run",
               **{"class": "parameter"}),
        change("chg-add-e", patch_text("points.csv", POINTS_B, POINTS_PLUS_E.replace("MP-B,0,2,2", "MP-B,0,2,4")),
               world / "run", prerequisites=["chg-point-b"]),
        change("chg-unused", patch_text("params.csv", PARAMS, PARAMS.replace("base", "other")), world / "run"),
    ]
    # The order of the ids in the request carries no meaning.
    changes = with_manifest(world, entries, ["chg-add-e", "chg-rate", "chg-point-b"])
    result, _ = run_stub(world, stub_request(world, changes=changes))
    folder = world / "run"
    assert result.outcome == "succeeded"
    assert_documents_valid(folder)
    assert folder_hashes(world / "rel") == before  # the base release is never altered

    record = stored(folder / "run-record.json")
    assert roles(record["inputs"]) == {"request": "request.json", "change_manifest": "changes.json"}
    assert record["inputs"][1]["artifact"] == changes["manifest"]
    assert record["parameters"] == [{"name": "label", "type": "scalar", "value": "base"},
                                    {"name": "rate", "type": "scalar", "value": 0.02}]
    values = check_export(result.response, result.export_path)
    old = check_export(base.response, base.export_path)
    assert values[("MP-B", 1)] == [4, 8] and old[("MP-B", 1)] == [2, 4]
    assert ("MP-E", 0) in values and ("MP-E", 0) not in old
    assert values[("MP-A", 12)] == old[("MP-A", 12)]
    assert result.response["changes"] == changes


def bad_change_sets(world: Path) -> dict:
    """Name -> (changes member of the request, diagnostic code, change ids named)."""
    folder = world / "run"
    good = patch_text("points.csv", POINTS, POINTS_B)

    def manifest(entries, enabled, **members):
        return with_manifest(world, entries, enabled, **members)

    def a(**members):
        return change("chg-a", good, folder, **members)

    def b(**members):
        return change("chg-b", patch_text("params.csv", PARAMS, PARAMS_RATE), folder, **members)

    cases = {
        "unknown-id": lambda: (manifest([a()], ["chg-a", "chg-x"]), "unknown_change", ["chg-x"]),
        "unmet-prerequisite": lambda: (
            manifest([a(), b(prerequisites=["chg-a"])], ["chg-b"]), "unmet_prerequisite", ["chg-b"]),
        "conflict": lambda: (
            manifest([a(), b(conflicts=["chg-a"])], ["chg-a", "chg-b"]), "change_conflict",
            ["chg-a", "chg-b"]),
        "rule-1-duplicate-id": lambda: (manifest([a(), a()], ["chg-a"]), "invalid_manifest", ["chg-a"]),
        "rule-2-foreign-id": lambda: (
            manifest([a(prerequisites=["chg-x"])], ["chg-a"]), "invalid_manifest", ["chg-a"]),
        "rule-2-names-itself": lambda: (
            manifest([a(conflicts=["chg-a"])], ["chg-a"]), "invalid_manifest", ["chg-a"]),
        "rule-3-both-lists": lambda: (
            manifest([b(), a(prerequisites=["chg-b"], conflicts=["chg-b"])], ["chg-a", "chg-b"]),
            "invalid_manifest", ["chg-a"]),
        "rule-4-prerequisite-after": lambda: (
            manifest([a(prerequisites=["chg-b"]), b()], ["chg-a", "chg-b"]), "invalid_manifest", ["chg-a"]),
        "rule-5-conflict-with-prerequisite": lambda: (
            manifest([a(), b(prerequisites=["chg-a"]),
                      change("chg-c", good, folder, prerequisites=["chg-b"], conflicts=["chg-a"])],
                     ["chg-a"]), "invalid_manifest", ["chg-c", "chg-a"]),
        "other-base-release": lambda: (manifest([a()], ["chg-a"], base_release="M"), "invalid_manifest", []),
        "other-stage": lambda: (manifest([a()], ["chg-a"], stage="asset_cashflow"), "stage_mismatch", []),
        "other-realisation": lambda: (
            manifest([a(realisation={"type": "engine_switch", "switch": "RC-1"})], ["chg-a"]),
            "unsupported_realisation", ["chg-a"]),
        "hunk-does-not-apply": lambda: (
            manifest([change("chg-a", good.replace(" MP-A,12,13,1.5", " MP-A,12,13,1.6"), folder)],
                     ["chg-a"]), "invalid_manifest", ["chg-a"]),
        "manifest-not-a-manifest": lambda: (
            manifest([a()], ["chg-a"], document="run_request"), "schema_violation", []),
    }

    def manifest_missing():
        changes = manifest([a()], ["chg-a"])
        (folder / "changes.json").unlink()
        return changes, "artifact_missing", []

    def manifest_other_hash():
        changes = manifest([a()], ["chg-a"])
        changes["manifest"]["sha256"] = "0" * 64
        return changes, "artifact_hash_mismatch", []

    def patch_missing():
        changes = manifest([a()], ["chg-a"])
        (folder / "patches" / "chg-a.patch").unlink()
        return changes, "artifact_missing", ["chg-a"]

    def patch_other_hash():
        changes = manifest([a()], ["chg-a"])
        (folder / "patches" / "chg-a.patch").write_text(good.replace("MP-B,0,2,4", "MP-B,0,2,5"), "utf-8")
        return changes, "artifact_hash_mismatch", ["chg-a"]

    cases.update({"manifest-missing": manifest_missing, "manifest-other-hash": manifest_other_hash,
                  "patch-missing": patch_missing, "patch-other-hash": patch_other_hash})
    return cases


BAD_CHANGE_SETS = [
    "unknown-id", "unmet-prerequisite", "conflict", "rule-1-duplicate-id", "rule-2-foreign-id",
    "rule-2-names-itself", "rule-3-both-lists", "rule-4-prerequisite-after",
    "rule-5-conflict-with-prerequisite", "other-base-release", "other-stage", "other-realisation",
    "hunk-does-not-apply", "manifest-not-a-manifest", "manifest-missing", "manifest-other-hash",
    "patch-missing", "patch-other-hash"]


@pytest.mark.parametrize("name", BAD_CHANGE_SETS)
def test_bad_change_set_is_rejected_and_nothing_runs(world, name):
    cases = bad_change_sets(world)
    assert sorted(cases) == sorted(BAD_CHANGE_SETS)
    changes, code, change_ids = cases[name]()
    before = folder_hashes(world / "rel")
    result, engine = run_stub(world, stub_request(world, changes=changes))
    assert result.outcome == "rejected" and engine.opened == 0
    diagnostic = result.response["diagnostics"][0]
    assert diagnostic["code"] == code
    assert sorted(diagnostic.get("change_ids", [])) == sorted(change_ids)
    assert not (world / "run" / "results.csv").exists()
    assert not schema_errors(stored(world / "run" / "response.json"), RUN_SCHEMA)
    record = stored(world / "run" / "run-record.json")
    assert not schema_errors(record, RECORD_SCHEMA)
    assert record["outcome"] == "rejected" and record["parameters"] == []
    assert folder_hashes(world / "rel") == before


def test_a_change_set_that_enables_nothing_needs_no_manifest(world):
    changes = {"enabled": [], "manifest": {"path": "absent.json", "sha256": "0" * 64}}
    result, _ = run_stub(world, stub_request(world, changes=changes))
    assert result.outcome == "succeeded"
    assert roles(stored(world / "run" / "run-record.json")["inputs"]) == {"request": "request.json"}


# --- the patch applier --------------------------------------------------------------

TEXT = "".join(f"line {n}\n" for n in range(1, 11))


def applied(tmp_path: Path, patch: str, text: str = TEXT, name: str = "file.txt") -> str:
    root = tmp_path / "root"
    (root / "sub").mkdir(parents=True, exist_ok=True)
    (root / name).write_bytes(text.encode("utf-8"))
    changes_contract.apply_patch(root, patch)
    return (root / name).read_bytes().decode("utf-8")


def test_patch_applies_with_exact_context(tmp_path):
    new = TEXT.replace("line 5\n", "line five\n").replace("line 10\n", "line 10\nline 11\n")
    assert applied(tmp_path, patch_text("file.txt", TEXT, new)) == new
    assert applied(tmp_path, patch_text("sub/file.txt", TEXT, new), name="sub/file.txt") == new


def test_patch_allows_a_shifted_line_number_but_no_inexact_context(tmp_path):
    new = TEXT.replace("line 5\n", "line five\n")
    patch = patch_text("file.txt", TEXT, new)
    shifted = "intro\nintro 2\n" + TEXT
    assert applied(tmp_path, patch, shifted) == "intro\nintro 2\n" + new
    with pytest.raises(ValueError, match="no place"):
        applied(tmp_path, patch, TEXT.replace("line 4\n", "line 4 \n"))
    with pytest.raises(ValueError, match="no place"):
        applied(tmp_path, patch, new)  # the removed line is not there any more


def test_patch_rejects_a_hunk_that_matches_in_several_places(tmp_path):
    patch = "--- file.txt\n+++ file.txt\n@@ -1,2 +1,2 @@\n a\n-b\n+c\n"
    assert applied(tmp_path, patch, "a\nb\nx\n") == "a\nc\nx\n"
    with pytest.raises(ValueError, match="2 places"):
        applied(tmp_path, patch, "a\nb\nx\na\nb\n")


def test_patch_honours_the_marker_for_a_missing_final_newline(tmp_path):
    old, new = "a\nb", "a\nc\n"
    patch = patch_text("file.txt", old, new).replace("-b", "-b\n\\ No newline at end of file\n")
    assert "\\ No newline" in patch
    assert applied(tmp_path, patch, old) == new
    with pytest.raises(ValueError, match="no place"):
        applied(tmp_path, patch, "a\nb\n")  # the file does end with a line feed
    removing = "--- file.txt\n+++ file.txt\n@@ -1,2 +1,2 @@\n a\n-b\n+c\n\\ No newline at end of file\n"
    assert applied(tmp_path, removing, "a\nb\n") == "a\nc"


@pytest.mark.parametrize("patch, reason", [
    ("--- /dev/null\n+++ file.txt\n@@ -0,0 +1 @@\n+a\n", "creates and deletes"),
    ("--- file.txt\n+++ /dev/null\n@@ -1 +0,0 @@\n-line 1\n", "creates and deletes"),
    ("--- file.txt\n+++ other.txt\n@@ -1 +1 @@\n-line 1\n+x\n", "renames"),
    ("--- ../file.txt\n+++ ../file.txt\n@@ -1 +1 @@\n-line 1\n+x\n", "not a path inside"),
    ("--- /etc/hosts\n+++ /etc/hosts\n@@ -1 +1 @@\n-line 1\n+x\n", "not a path inside"),
    ("--- absent.txt\n+++ absent.txt\n@@ -1 +1 @@\n-line 1\n+x\n", "holds no file"),
    ("--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-line 1\n+x\n", "renames"),
    ("--- a/file.txt\n+++ a/file.txt\n@@ -1 +1 @@\n-line 1\n+x\n", "holds no file"),  # no prefix is stripped
    ("diff --git a/file.txt b/file.txt\n--- file.txt\n+++ file.txt\n@@ -1 +1 @@\n-line 1\n+x\n", "expected"),
    ("--- file.txt\n+++ file.txt\n@@ -1,2 +1 @@\n-line 1\n+x\n", "stated line counts"),
    ("--- file.txt\n+++ file.txt\n@@ -1 +1 @@\n-line 1\n+x\n+y\n", "expected"),
    ("--- file.txt\n+++ file.txt\n", "no hunk"),
    ("", "changes no file"),
])
def test_patch_rejects_what_the_profile_excludes(tmp_path, patch, reason):
    with pytest.raises(ValueError, match=reason):
        applied(tmp_path, patch)
    assert (tmp_path / "root" / "file.txt").read_text("utf-8") == TEXT


# --- failed runs --------------------------------------------------------------------


@pytest.mark.parametrize("base, message", [
    ("raise", "The stub cannot calculate this model point."),
    ("nan", "The value of Anzahl Verträge in period 0 is not finite."),
    ("inf", "The value of Anzahl Verträge in period 0 is not finite."),
])
def test_failing_model_point_gives_a_failed_run_without_export(world, base, message):
    (world / "rel" / "points.csv").write_text(POINTS.replace("MP-B,0,2,2", f"MP-B,0,2,{base}"), "utf-8")
    result, _ = run_stub(world)
    folder = world / "run"
    assert result.outcome == "failed"
    assert result.response["failed_model_points"] == [{"model_point_id": "MP-B", "message": message}]
    assert "diagnostics" not in result.response
    assert sorted(p.name for p in folder.iterdir()) == ["request.json", "response.json", "run-record.json"]
    assert_documents_valid(folder)
    record = stored(folder / "run-record.json")
    assert record["outcome"] == "failed" and roles(record["outputs"]) == {"response": "response.json"}
    assert [p["name"] for p in record["parameters"]] == ["label", "rate"]  # present for a failed run


def test_an_integer_parameter_too_large_for_binary64_rejects_the_request(world, monkeypatch):
    monkeypatch.setattr(StubSession, "parameters",
                        lambda self: [{"name": "rate", "type": "scalar", "value": 10 ** 400}])
    result, _ = run_stub(world)
    assert result.outcome == "rejected"
    assert result.response["diagnostics"][0]["code"] == "non_finite_value"
    assert_documents_valid(world / "run")
    read_document(world / "run" / "run-record.json", RECORD_SCHEMA)  # the record reads back


@pytest.mark.parametrize("text", ["nan", "inf"])
def test_non_finite_parameter_rejects_the_request(world, text):
    (world / "rel" / "params.csv").write_text(PARAMS.replace("rate,0.01", f"rate,{text}"), "utf-8")
    request = stub_request(world, selection={"mode": "subset", "model_point_ids": ["MP-9999"]})
    result, _ = run_stub(world, request)  # the inventory is checked before the selection
    folder = world / "run"
    assert result.outcome == "rejected"
    (diagnostic,) = result.response["diagnostics"]
    assert diagnostic["code"] == "non_finite_value" and "parameter rate " in diagnostic["message"]
    assert sorted(p.name for p in folder.iterdir()) == ["request.json", "response.json", "run-record.json"]
    assert_documents_valid(folder)
    record = stored(folder / "run-record.json")
    assert record["outcome"] == "rejected" and record["parameters"] == []


def test_model_point_id_that_occurs_twice_is_a_failed_model_point(world):
    (world / "rel" / "points.csv").write_text(POINTS + "MP-A,0,1,9\n", "utf-8")
    result, _ = run_stub(world)
    assert result.outcome == "failed"
    assert [f["model_point_id"] for f in result.response["failed_model_points"]] == ["MP-A"]


# --- the outcome error -------------------------------------------------------------


def assert_error_run(world: Path, result, code: str, folder: str = "run") -> dict:
    """A run with the outcome error: response and record written, no export, one diagnostic."""
    path = world / folder
    assert result.outcome == "error" and result.export_path is None
    assert sorted(p.name for p in path.iterdir()) == ["request.json", "response.json", "run-record.json"]
    assert_documents_valid(path)
    response, request = stored(path / "response.json"), stored(path / "request.json")
    assert [d["code"] for d in response["diagnostics"]] == [code]
    for member in ("stage", "run_id", "release", "changes", "selection"):
        assert response[member] == request[member]
    assert "failed_model_points" not in response and "export" not in response
    record = stored(path / "run-record.json")
    assert record["outcome"] == "error" and roles(record["outputs"]) == {"response": "response.json"}
    assert RECORD_ID.fullmatch(record["record_id"])
    return response["diagnostics"][0]


def test_a_state_without_a_model_point_ends_with_the_outcome_error(world):
    (world / "rel" / "points.csv").write_text("id,first,last,base\n", "utf-8")
    result, _ = run_stub(world)
    diagnostic = assert_error_run(world, result, "no_model_point")
    assert diagnostic == {"code": "no_model_point", "message": "The release state holds no model point."}
    # The inventory could be read, so the record holds it.
    assert [p["name"] for p in stored(world / "run" / "run-record.json")["parameters"]] == ["label", "rate"]
    # A subset is checked first: an id the empty state does not hold is a rejection.
    request = stub_request(world, run_id="run-subset", selection={"mode": "subset", "model_point_ids": ["MP-A"]})
    result, _ = run_stub(world, request, folder="subset")
    assert result.outcome == "rejected"
    assert result.response["diagnostics"][0]["code"] == "unknown_model_point"


@pytest.mark.parametrize("line, shown", [(",0,0,1", '""'), ("MP-\x01,0,0,1", '"MP-\\u0001"')])
def test_a_model_point_id_the_schema_forbids_ends_with_the_outcome_error(world, line, shown):
    (world / "rel" / "points.csv").write_text(POINTS + line + "\n", "utf-8")
    result, _ = run_stub(world)
    diagnostic = assert_error_run(world, result, "invalid_model_point_id")
    assert shown in diagnostic["message"] and "model_point_ids" not in diagnostic
    # A subset that does not select the id runs as before.
    request = stub_request(world, run_id="run-subset", selection={"mode": "subset", "model_point_ids": ["MP-A"]})
    assert run_stub(world, request, folder="subset")[0].outcome == "succeeded"


def test_a_model_point_id_that_is_no_string_ends_with_the_outcome_error(world, monkeypatch):
    monkeypatch.setattr(StubSession, "model_point_ids", lambda self: ["MP-A", 7])
    result, _ = run_stub(world)
    assert "id 7," in assert_error_run(world, result, "invalid_model_point_id")["message"]


class ScratchEngine(StubEngine):
    """Restores into a scratch folder named as the core expects, and raises where it is told to.

    The message of the exception names the scratch folder and the repositories folder.
    """

    def __init__(self, where: str, error=OSError):
        super().__init__()
        self.where, self.error = where, error
        self.scratch = None

    def fail(self, where: str, repositories) -> None:
        if where == self.where:
            raise self.error(f"first line\ncannot read {self.scratch}/rel/points.csv beside "
                             f"{Path(repositories).resolve()}/rel/params.csv")

    def resolve(self, release, repositories):
        self.scratch = Path(tempfile.gettempdir()) / f"{SCRATCH_PREFIX}resolve"
        self.fail("resolve", repositories)
        super().resolve(release, repositories)

    @contextmanager
    def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
        with tempfile.TemporaryDirectory(prefix=SCRATCH_PREFIX) as scratch:
            self.scratch = scratch
            self.fail("enter", repositories)
            with super().open(release, enabled, manifest_dir, repositories, hold) as session:
                for name in ("model_point_ids", "parameters"):
                    if self.where == name:
                        setattr(session, name, lambda name=name: self.fail(name, repositories))
                if self.where in ("quantities", "time_basis"):
                    engine = self

                    class Failing(type(session)):
                        quantities = property(lambda s: engine.fail("quantities", repositories) or [])
                        time_basis = property(lambda s: engine.fail("time_basis", repositories) or "")
                    session.__class__ = Failing
                yield session
            self.fail("leave", repositories)


ENGINE_CALLS = ["resolve", "enter", "leave", "model_point_ids", "parameters", "quantities", "time_basis"]


@pytest.mark.parametrize("where", ENGINE_CALLS)
def test_an_engine_that_raises_while_it_restores_or_reads_the_state_ends_with_the_outcome_error(world, where):
    engine = ScratchEngine(where)
    result, _ = run_stub(world, engine=engine)
    diagnostic = assert_error_run(world, result, "state_not_readable")
    # The kind of error and the last line of its message; no folder of this machine.
    assert diagnostic["message"] == ("OSError: cannot read <scratch>/rel/points.csv beside "
                                     "<repositories>/rel/params.csv")
    assert str(world) not in diagnostic["message"] and tempfile.gettempdir() not in diagnostic["message"]
    assert SCRATCH_PREFIX not in diagnostic["message"]


def test_an_engine_error_with_an_empty_message_is_named_by_its_kind_alone(world):
    result, _ = run_stub(world, engine=ScratchEngine("enter", lambda message: RuntimeError()), folder="empty")
    assert assert_error_run(world, result, "state_not_readable", folder="empty")["message"] == "RuntimeError"


def test_a_rejection_and_a_usage_error_of_the_engine_keep_their_meaning(world):
    result, _ = run_stub(world, engine=ScratchEngine("enter", lambda message: Rejection("invalid_manifest", message)))
    assert result.outcome == "rejected" and result.response["diagnostics"][0]["code"] == "invalid_manifest"
    with pytest.raises(UsageError):
        run_stub(world, engine=ScratchEngine("resolve", UsageError), folder="usage")
    assert sorted(p.name for p in (world / "usage").iterdir()) == ["request.json"]


def test_a_model_point_failure_stays_failed_and_an_error_of_the_core_stops_the_run(world, monkeypatch):
    monkeypatch.setattr(StubSession, "project", lambda self, model_point_id: (_ for _ in ()).throw(
        ModelPointFailure("no lapse rate")))
    assert run_stub(world)[0].outcome == "failed"
    monkeypatch.setattr(StubSession, "quantities", [("Anzahl Verträge", "policies"), ("Provisionen", "x"),
                                                    ("Provisionen", "y")])
    with pytest.raises(RuntimeError, match="quantities the stage does not allow"):
        run_stub(world, folder="core")
    assert sorted(p.name for p in (world / "core").iterdir()) == ["request.json"]


def test_a_run_that_ended_with_an_error_is_replayed_by_its_response(world):
    (world / "rel" / "points.csv").write_text("id,first,last,base\n", "utf-8")
    run_stub(world)
    folder = world / "run"
    before = folder_hashes(folder)
    done = replay(folder / "run-record.json", StubEngine(), repositories=world)
    assert done.outcome == "reproduced_exactly" and done.compare_result is None
    record = stored(folder / "replay-record.json")
    assert not schema_errors(record, RECORD_SCHEMA) and record["outcome"] == "reproduced_exactly"
    assert roles(record["outputs"]) == {"response": "replay/response.json"}
    assert (folder / "replay" / "response.json").read_bytes() == (folder / "response.json").read_bytes()
    assert not any(p.name.startswith("replay-compare") for p in folder.iterdir())
    assert {k: v for k, v in folder_hashes(folder).items() if not k.startswith("replay")} == before
    # The state can be read now: the repeated run differs and the run is not reproduced.
    remove_replay(folder)
    (world / "rel" / "points.csv").write_text(POINTS, "utf-8")
    with pytest.raises(Rejection):  # the release identity names the input data by its hash
        replay(folder / "run-record.json", StubEngine(), repositories=world)


def test_a_run_whose_engine_raised_is_reproduced_with_another_scratch_folder(world, monkeypatch, capsys):
    run_stub(world, engine=ScratchEngine("model_point_ids"))
    folder = world / "run"
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: ScratchEngine("model_point_ids"))
    assert main(["replay", str(folder / "run-record.json"), "--repositories", str(world)]) == 0
    output = capsys.readouterr().out
    assert "replay: reproduced_exactly" in output and "the repeated run writes the same response" in output
    remove_replay(folder)
    # Another error message is not reproduced.
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: ScratchEngine("parameters", ValueError))
    assert main(["replay", str(folder / "run-record.json"), "--repositories", str(world)]) == 1
    assert "replay: not_reproduced" in capsys.readouterr().out
    # An engine that raises while it resolves a recorded error run leaves it to the repeated run.
    remove_replay(folder)
    shutil.rmtree(world / "run")
    run_stub(world, engine=ScratchEngine("resolve"))
    assert replay(folder / "run-record.json", ScratchEngine("resolve"), repositories=world).outcome == \
        "reproduced_exactly"


class ReadError(Exception):
    """The kind of error of the example ``state-not-readable``."""


class AnyRelease(StubEngine):
    """Restores the stub folder ``rel`` for any release identity, as the examples name opaque ones."""

    def __init__(self, points: str | None = None, raises: bool = False):
        super().__init__()
        self.points, self.raises = points, raises

    def _folder(self, release, repositories) -> Path:
        folder = Path(repositories) / "rel"
        if self.points is not None:
            (folder / "points.csv").write_text(self.points, "utf-8")
        return folder

    @contextmanager
    def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
        with tempfile.TemporaryDirectory(prefix=SCRATCH_PREFIX) as scratch:
            if self.raises:
                raise ReadError(f"the table {scratch}/tables/lapse_table.csv has no column policy_year")
            with super().open(release, enabled, manifest_dir, repositories, hold) as session:
                yield session


@pytest.mark.parametrize("case, engine", [
    ("no-model-point", lambda: AnyRelease("id,first,last,base\n")),
    ("invalid-model-point-id", lambda: AnyRelease(POINTS + ",0,0,1\n")),
    ("state-not-readable", lambda: AnyRelease(raises=True)),
])
def test_the_error_examples_of_the_pack_are_written_by_the_core(world, case, engine):
    example = ROOT / "contracts" / "v3" / "examples" / "negative" / case
    shutil.copyfile(example / "request.json", world / "run" / "request.json")
    with written_under("3.0"):  # the examples are 3.0 documents
        result = run_request(world / "run" / "request.json", engine(), repositories=world)
    assert result.outcome == "error"
    assert (world / "run" / "response.json").read_bytes() == (example / "response.json").read_bytes()


def test_an_error_run_with_enabled_changes_lists_its_manifest_and_is_replayed(world):
    """The engine raises while it resolves, before the core checks the manifest."""
    entries = [change("chg-point-b", patch_text("points.csv", POINTS, POINTS_B), world / "run")]
    request = stub_request(world, changes=with_manifest(world, entries, ["chg-point-b"]))
    result, _ = run_stub(world, request, ScratchEngine("resolve"))
    assert result.outcome == "error"
    record = stored(world / "run" / "run-record.json")
    assert roles(record["inputs"]) == {"request": "request.json", "change_manifest": "changes.json"}
    assert_documents_valid(world / "run")
    done = replay(world / "run" / "run-record.json", ScratchEngine("resolve"), repositories=world)
    assert done.outcome == "reproduced_exactly"
    assert (world / "run" / "replay" / "changes.json").read_bytes() == (world / "run" / "changes.json").read_bytes()
    # A manifest that fails its artifact check is left out; the run still ends with an error.
    path = world / "other" / "request.json"
    path.parent.mkdir()
    path.write_bytes(document_bytes(request))
    (path.parent / "changes.json").write_bytes(b"{}")
    assert run_request(path, ScratchEngine("resolve"), repositories=world).outcome == "error"
    assert roles(stored(path.parent / "run-record.json")["inputs"]) == {"request": "request.json"}


def test_a_run_of_one_request_repeated_differs_only_in_its_record(world):
    """Two executions of one request: equal bytes except the record id and the time of the record."""
    first, _ = run_stub(world, folder="first")
    second, _ = run_stub(world, folder="second")
    one, two = folder_hashes(world / "first"), folder_hashes(world / "second")
    assert {k: v for k, v in one.items() if k != "run-record.json"} == \
        {k: v for k, v in two.items() if k != "run-record.json"}
    records = [stored(world / name / "run-record.json") for name in ("first", "second")]
    assert records[0]["record_id"] != records[1]["record_id"]
    assert all(RECORD_ID.fullmatch(record["record_id"]) for record in records)
    assert without_volatile(records[0]) == without_volatile(records[1])


TABLE = {"name": "table", "type": "keyed_table", "key_columns": ["year", "kind"], "value_columns": ["rate"],
         "rows": [{"key": [10, "b"], "values": [0.3]}, {"key": [2, "b"], "values": [0.2]},
                  {"key": [2, "a"], "values": [0.1]}]}


def test_the_core_orders_the_parameter_inventory_of_an_engine(world, monkeypatch):
    scalar = {"name": "rate", "type": "scalar", "value": 0.01}
    monkeypatch.setattr(StubSession, "parameters", lambda self: [TABLE, scalar])
    result, _ = run_stub(world)
    assert result.outcome == "succeeded"
    record = stored(world / "run" / "run-record.json")
    assert [p["name"] for p in record["parameters"]] == ["rate", "table"]
    assert [row["key"] for row in record["parameters"][1]["rows"]] == [[2, "a"], [2, "b"], [10, "b"]]


@pytest.mark.parametrize("inventory", [
    [{"name": "rate", "type": "scalar"}],
    [{"name": "rate", "type": "scalar", "value": None}],
    [{"name": "rate", "type": "scalar", "value": 1}, {"name": "rate", "type": "scalar", "value": 2}],
    [{**TABLE, "rows": TABLE["rows"] + [{"key": [2, "a"], "values": [0.5]}]}],
    [{**TABLE, "rows": TABLE["rows"] + [{"key": [2.0, "a"], "values": [0.5]}]}],  # 2 and 2.0 are one key
    [{**TABLE, "rows": [{"key": [2], "values": [0.5]}]}],
    [{**TABLE, "rows": [{"key": [2, "a"], "values": [0.5, 0.6]}]}],
])
def test_an_inventory_the_record_does_not_allow_writes_no_document(world, monkeypatch, inventory):
    monkeypatch.setattr(StubSession, "parameters", lambda self: inventory)
    with pytest.raises(RuntimeError, match="parameter inventory"):
        run_stub(world)
    assert sorted(p.name for p in (world / "run").iterdir()) == ["request.json"]


# --- number format ------------------------------------------------------------------


@pytest.mark.parametrize("value, text", [
    (1.0, "1"), (-0.0, "0"), (0, "0"), (1e-05, "1e-5"), (1e16, "1e16"), (1.5e-07, "1.5e-7"),
    (-2.5e+20, "-2.5e20"), (0.1, "0.1"), (-380.0, "-380"), (1e22, "1e22"), (123456789.125, "123456789.125"),
    (0.1 + 0.2, "0.30000000000000004"), (5e-324, "5e-324"), (1.7976931348623157e308, "1.7976931348623157e308"),
    (9999999999999998.0, "9999999999999998"), (0.0001, "0.0001"), (True, "1")])
def test_writer_form(value, text):
    assert format_number(value) == text
    assert is_profile_number(text)
    assert float(text) == float(value)


@pytest.mark.parametrize("value", [float("nan"), float("inf"), float("-inf")])
def test_writer_refuses_a_non_finite_value(value):
    with pytest.raises(ValueError):
        format_number(value)


def test_export_quotes_only_where_the_profile_requires_it(tmp_path):
    data = export_bytes(["Anzahl Verträge"], [('b,"x"', 1, [1.0]), ("a b", 0, [2.5]), ('b,"x"', 0, [0.0])])
    assert data.decode("utf-8") == (
        'model_point_id,period,Anzahl Verträge\na b,0,2.5\n"b,""x""",0,0\n"b,""x""",1,1\n')
    path = tmp_path / "results.csv"
    path.write_bytes(data)
    assert read_export(path, ["Anzahl Verträge"]) == [("a b", 0, [2.5]), ('b,"x"', 0, [0.0]), ('b,"x"', 1, [1.0])]


@pytest.mark.parametrize("body, code", [
    ("MP-A,0,1\n", None), ("MP-A,007,1.50\n", None), ("MP-A,0,1E+7\n", None), ("MP-A,0,-0\n", None),
    ("MP-A,0,NaN\n", "non_finite_value"), ("MP-A,0,-Infinity\n", "non_finite_value"),
    ("MP-A,0,1e999\n", "number_format"), ("MP-A,0,\n", "number_format"), ("MP-A,0,\"1,5\"\n", "number_format"),
    ("MP-A,0,+1\n", "number_format"), ("MP-A,0,0x10\n", "number_format"), ("MP-A,1.0,1\n", "number_format"),
    ("MP-A,0\n", "export_format"), ("MP-A,0,1,2\n", "export_format"), (",0,1\n", "export_format"),
    ("MP-A,0,1\r\n", "export_format"), ("MP-A,0,1", "export_format"), ("\nMP-A,0,1\n", "export_format"),
    ('MP-"A,0,1\n', "export_format"), ('"MP-A",0,1\n', "export_format"), ('MP-A,0,"1"\n', "export_format"),
])
def test_export_reader_grammar(tmp_path, body, code):
    path = tmp_path / "results.csv"
    path.write_bytes(("model_point_id,period,Netto-Cashflow\n" + body).encode("utf-8"))
    if code is None:
        assert len(read_export(path, ["Netto-Cashflow"])) == 1
    else:
        with pytest.raises(Rejection) as caught:
            read_export(path, ["Netto-Cashflow"])
        assert caught.value.code == code


@pytest.mark.parametrize("edit, code", [
    (lambda r, rows: None, None),
    (lambda r, rows: r["quantities"].reverse(), "export_format"),
    (lambda r, rows: r["model_points"].pop(0), "missing_coordinate"),
    (lambda r, rows: r["model_points"].append({"model_point_id": "MP-X", "first_period": 0, "last_period": 0}),
     "unrequested_coordinate"),
    (lambda r, rows: r["model_points"].append(dict(r["model_points"][0])), "inconsistent_response"),
    (lambda r, rows: r["model_points"][0].update(first_period=14), "inconsistent_response"),
    (lambda r, rows: rows.append(rows[1]), "duplicate_coordinate"),
    (lambda r, rows: rows.pop(1), "missing_coordinate"),
    (lambda r, rows: rows.append("MP-A,14,1,1"), "unrequested_coordinate"),
    (lambda r, rows: r["export"].update(data_rows=6), "inconsistent_response"),
])
def test_completeness_rules_9_to_13(world, edit, code):
    request = stub_request(world, selection={"mode": "subset", "model_point_ids": ["MP-A", "MP-B"]})
    result, _ = run_stub(world, request)
    response = result.response
    rows = result.export_path.read_text("utf-8").splitlines()
    edit(response, rows)
    result.export_path.write_text("\n".join(rows) + "\n", "utf-8")
    if code is None:
        assert len(check_export(response, result.export_path)) == 5
    else:
        with pytest.raises(Rejection) as caught:
            check_export(response, result.export_path)
        assert caught.value.code == code


def test_a_period_written_as_a_float_is_read_as_the_integer(world):
    """JSON Schema counts ``12.0`` as an integer, and the parser returns a float."""
    result, _ = run_stub(world)
    folder = result.response_path.parent
    written = result.response_path.read_bytes()
    assert written.count(b'"first_period": 12,') == 1 and written.count(b'"last_period": 13\n') == 1
    result.response_path.write_bytes(written.replace(b'"first_period": 12,', b'"first_period": 12.0,')
                                     .replace(b'"last_period": 13\n', b'"last_period": 13.0\n'))
    response = read_document(result.response_path, RUN_SCHEMA, "run_response")
    assert isinstance(response["model_points"][0]["first_period"], float)
    assert check_export(response, result.export_path) == check_export(result.response, result.export_path)
    rehash(folder)
    assert b'"first_period": 12.0,' in result.response_path.read_bytes()
    assert replay(folder / "run-record.json", StubEngine(), repositories=world).outcome == "reproduced_exactly"


# --- replay -------------------------------------------------------------------------


def recorded_run(world: Path, with_changes: bool = False):
    request = None
    if with_changes:
        entries = [change("chg-point-b", patch_text("points.csv", POINTS, POINTS_B), world / "run"),
                   change("chg-unused", patch_text("params.csv", PARAMS, PARAMS_RATE), world / "run")]
        request = stub_request(world, changes=with_manifest(world, entries, ["chg-point-b"]))
    result, _ = run_stub(world, request)
    assert result.outcome == "succeeded"
    return result


def remove_replay(folder: Path) -> None:
    """Remove what a replay wrote beside the record."""
    shutil.rmtree(folder / "replay")
    for name in ("replay-record.json", "replay-compare.request.json", "replay-compare.result.json",
                 "replay-compare.deviations.csv"):
        (folder / name).unlink(missing_ok=True)


@pytest.mark.parametrize("with_changes", [False, True])
def test_replay_of_an_unchanged_run_is_reproduced_exactly(world, with_changes):
    recorded_run(world, with_changes)
    folder = world / "run"
    before = folder_hashes(folder)
    result = replay(folder / "run-record.json", StubEngine(), repositories=world)
    assert result.outcome == "reproduced_exactly"
    compared = stored(folder / "replay-compare.result.json")
    assert compared == result.compare_result and not schema_errors(compared, COMPARE_SCHEMA)
    assert compared["outcome"] == "compared" and compared["tolerance"] == {"per_quantity": {}}
    assert deviation_rows(folder / "replay-compare.result.json") == []
    assert compared["added"] == compared["removed"] == []
    assert compared["compared_coordinates"] == 16 and compared["parameter_diff"] == []
    assert compared["left"] == compared["right"] == {"run_id": "run-stub", "release_label": "N"}
    # The recorded run is the left side, the repeated run the right side.
    request = stored(folder / "replay-compare.request.json")
    assert not schema_errors(request, COMPARE_SCHEMA)
    assert request["compare_id"] == "compare-replay-run-stub"
    assert request["left"]["response"]["path"] == "response.json"
    assert request["left"]["run_record"]["path"] == "run-record.json"
    assert request["right"]["response"]["path"] == "replay/response.json"
    assert request["right"]["run_record"]["path"] == "replay/run-record.json"

    record = stored(folder / "replay-record.json")
    assert not schema_errors(record, RECORD_SCHEMA)
    assert record["procedure"] == {"type": "replay"} and record["outcome"] == "reproduced_exactly"
    assert record["stage"] == "liability_cashflow" and record["contract_version"] == "3.1"
    # Every execution has its own record id: the replay, the repeated run, and the recorded run.
    repeated = stored(folder / "replay" / "run-record.json")
    assert RECORD_ID.fullmatch(record["record_id"]) and RECORD_ID.fullmatch(repeated["record_id"])
    assert len({record["record_id"], repeated["record_id"], stored(folder / "run-record.json")["record_id"]}) == 3
    assert roles(record["inputs"]) == {"run_record": "run-record.json"}
    assert roles(record["outputs"]) == {"response": "replay/response.json", "export": "replay/results.csv",
                                        "run_record": "replay/run-record.json",
                                        "compare_request": "replay-compare.request.json",
                                        "compare_result": "replay-compare.result.json",
                                        "deviations": "replay-compare.deviations.csv"}
    # The replay is recorded as a replay: no record of the comparison and no signature table.
    assert sorted(p.name for p in folder.iterdir() if p.name.startswith("replay")) == [
        "replay", "replay-compare.deviations.csv", "replay-compare.request.json", "replay-compare.result.json",
        "replay-record.json"]
    for entry in record["inputs"] + record["outputs"]:
        assert sha256_file(folder / entry["artifact"]["path"]) == entry["artifact"]["sha256"]
    original = stored(folder / "run-record.json")
    assert record["releases"] == original["releases"] and record["parameters"] == original["parameters"]

    # The repeated run is a normal, self-contained run; its inputs are byte copies.
    assert_documents_valid(folder / "replay")
    assert (folder / "replay" / "request.json").read_bytes() == (folder / "request.json").read_bytes()
    assert (folder / "replay" / "results.csv").read_bytes() == (folder / "results.csv").read_bytes()
    if with_changes:
        for name in ("changes.json", "patches/chg-point-b.patch"):
            assert (folder / "replay" / name).read_bytes() == (folder / name).read_bytes()
        assert not (folder / "replay" / "patches" / "chg-unused.patch").exists()  # not enabled, not read
    assert {name: digest for name, digest in folder_hashes(folder).items()
            if not name.startswith("replay")} == before

    with pytest.raises(UsageError):  # a second replay overwrites nothing
        replay(folder / "run-record.json", StubEngine(), repositories=world)


def test_a_change_that_is_not_enabled_cannot_block_the_replay(world):
    """Its artifact may name any file, even an output of the run; the replay copies none of it."""
    folder = world / "run"
    unused = change("chg-unused", None, folder, realisation={
        "type": "text_patch", "format": "unified_diff",
        "artifact": {"path": "response.json", "sha256": "0" * 64}})
    entries = [change("chg-point-b", patch_text("points.csv", POINTS, POINTS_B), folder), unused]
    result, _ = run_stub(world, stub_request(world, changes=with_manifest(world, entries, ["chg-point-b"])))
    assert result.outcome == "succeeded"
    assert replay(folder / "run-record.json", StubEngine(), repositories=world).outcome == "reproduced_exactly"


def alter_export(folder: Path) -> None:
    path = folder / "results.csv"
    path.write_text(path.read_text("utf-8").replace("MP-B,1,2,4\n", "MP-B,1,2,4.5\n"), "utf-8")


def alter_release(world: Path) -> None:
    (world / "rel" / "points.csv").write_text(POINTS_B, "utf-8")


def alter_request(folder: Path) -> None:
    path = folder / "request.json"
    path.write_bytes(path.read_bytes() + b"\n")


def remove_response(folder: Path) -> None:
    (folder / "response.json").unlink()


def other_stage(folder: Path) -> None:
    record = stored(folder / "run-record.json")
    record["stage"] = "asset_cashflow"
    (folder / "run-record.json").write_bytes(document_bytes(record))


def other_release(folder: Path) -> None:
    record = stored(folder / "run-record.json")
    record["releases"][0]["label"] = "M"
    (folder / "run-record.json").write_bytes(document_bytes(record))


@pytest.mark.parametrize("alter, code", [
    (lambda world: alter_export(world / "run"), "artifact_hash_mismatch"),
    (lambda world: alter_request(world / "run"), "artifact_hash_mismatch"),
    (lambda world: remove_response(world / "run"), "artifact_missing"),
    (alter_release, "unknown_reference"),
    (lambda world: other_stage(world / "run"), "unsupported_stage"),
    (lambda world: other_release(world / "run"), "request_mismatch"),
])
def test_rejected_replay_writes_no_record(world, alter, code):
    recorded_run(world)
    alter(world)
    before = folder_hashes(world / "run")
    with pytest.raises(Rejection) as caught:
        replay(world / "run" / "run-record.json", StubEngine(), repositories=world)
    assert caught.value.code == code
    assert folder_hashes(world / "run") == before
    assert not (world / "run" / "replay").exists()


def test_replay_rule_16_names_a_stage_mismatch(world):
    """The record and a listed document name two supported stages that differ."""
    recorded_run(world)
    folder = world / "run"
    record = stored(folder / "run-record.json")
    record["stage"] = "other_stage"
    (folder / "run-record.json").write_bytes(document_bytes(record))
    engine = StubEngine()
    engine.stages = frozenset({"liability_cashflow", "other_stage"})
    from degelmann.deltarecon import replay as replay_module, run as run_module
    run_module.STAGE_QUANTITIES["other_stage"] = run_module.STAGE_QUANTITIES["liability_cashflow"]
    try:
        with pytest.raises(Rejection) as caught:
            replay_module.replay(folder / "run-record.json", engine, repositories=world)
    finally:
        del run_module.STAGE_QUANTITIES["other_stage"]
    assert caught.value.code == "stage_mismatch"
    assert not (folder / "replay").exists()


def test_replay_with_an_altered_patch_is_rejected(world):
    recorded_run(world, with_changes=True)
    patch = world / "run" / "patches" / "chg-point-b.patch"
    patch.write_text(patch.read_text("utf-8").replace("MP-B,0,2,4", "MP-B,0,2,5"), "utf-8")
    with pytest.raises(Rejection) as caught:
        replay(world / "run" / "run-record.json", StubEngine(), repositories=world)
    assert caught.value.code == "artifact_hash_mismatch"
    assert not (world / "run" / "replay").exists()


def test_replay_with_other_values_is_not_reproduced(world):
    recorded_run(world)
    folder = world / "run"
    alter_export(folder)
    lines = (folder / "results.csv").read_text("utf-8").splitlines()
    lines = [line for line in lines if not line.startswith("MP-C,")]
    # The recorded run exports one more period of MP-A, at its end: projection period 2.
    lines.insert(lines.index(next(line for line in lines if line.startswith("MP-A,13,"))) + 1, "MP-A,14,1.5,22.5")
    (folder / "results.csv").write_text("\n".join(lines) + "\n", "utf-8")
    response = stored(folder / "response.json")
    response["model_points"] = [
        {"model_point_id": "MP-A", "first_period": 12, "last_period": 14},
        {"model_point_id": "MP-B", "first_period": 0, "last_period": 2},
        {"model_point_id": "MP-D", "first_period": 3, "last_period": 4}]
    (folder / "response.json").write_bytes(document_bytes(response))
    rehash(folder)

    result = replay(folder / "run-record.json", StubEngine(), repositories=world)
    assert result.outcome == "not_reproduced"
    record = stored(folder / "replay-record.json")
    assert not schema_errors(record, RECORD_SCHEMA)
    assert record["procedure"] == {"type": "replay"} and record["outcome"] == "not_reproduced"
    assert "replay/results.csv" in roles(record["outputs"]).values()
    # The deviating coordinates are in the deviation file of the compare result; the record lists both.
    assert roles(record["outputs"])["compare_result"] == "replay-compare.result.json"
    assert roles(record["outputs"])["deviations"] == "replay-compare.deviations.csv"
    compared = stored(folder / "replay-compare.result.json")
    assert not schema_errors(compared, COMPARE_SCHEMA) and compared["outcome"] == "compared"
    assert deviation_rows(folder / "replay-compare.result.json") == [
        {"model_point_id": "MP-B", "period": 1, "quantity": "Netto-Cashflow", "left": 4.5, "right": 4.0}]
    assert compared["deviating_model_points"] == ["MP-B"]
    assert compared["removed"] == [{"model_point_id": "MP-A", "first_period": 2, "last_period": 2}]
    assert compared["added"] == [{"model_point_id": "MP-C", "first_period": 0, "last_period": 0}]
    for entry in record["inputs"] + record["outputs"]:
        assert sha256_file(folder / entry["artifact"]["path"]) == entry["artifact"]["sha256"]


def test_a_coverage_difference_alone_is_not_reproduced(world):
    """The recorded export lacks a period that the repeated run exports; no value differs."""
    recorded_run(world)
    folder = world / "run"
    lines = [line for line in (folder / "results.csv").read_text("utf-8").splitlines()
             if not line.startswith("MP-B,2,")]
    (folder / "results.csv").write_text("\n".join(lines) + "\n", "utf-8")
    response = stored(folder / "response.json")
    response["model_points"] = [{**p, "last_period": 1} if p["model_point_id"] == "MP-B" else p
                                for p in response["model_points"]]
    response["export"]["data_rows"] = 7
    (folder / "response.json").write_bytes(document_bytes(response))
    rehash(folder)
    result = replay(folder / "run-record.json", StubEngine(), repositories=world)
    assert result.outcome == "not_reproduced"
    assert deviation_rows(result.compare_result_path) == [] and result.compare_result["removed"] == []
    assert result.compare_result["added"] == [{"model_point_id": "MP-B", "first_period": 2, "last_period": 2}]


def tolerance_file(world: Path, per_quantity: dict) -> Path:
    path = world / "tolerance.json"
    path.write_bytes(document_bytes({"per_quantity": per_quantity}))
    return path


@pytest.mark.parametrize("per_quantity, altered, outcome", [
    ({}, None, "reproduced_exactly"),
    ({"Netto-Cashflow": {"upper": EXACT, "lower": EXACT}}, None, "reproduced_exactly"),
    ({}, "4.004", "not_reproduced"),
    ({"Netto-Cashflow": {"decimals": 2, "upper": EXACT, "lower": EXACT, "derivation": "cents"}}, None,
     "reproduced_at_decimals"),
    ({"Netto-Cashflow": {"decimals": 2, "upper": EXACT, "lower": EXACT, "derivation": "cents"}}, "4.004",
     "reproduced_at_decimals"),
    ({"Netto-Cashflow": {"decimals": 2, "upper": EXACT, "lower": EXACT, "derivation": "cents"}}, "4.006",
     "not_reproduced"),
    # The recorded value is the left side: the repeated value 4 lies below 4.006.
    ({"Netto-Cashflow": {"upper": EXACT, "lower": {"abs_tol": 0.01, "rel_tol": 0}, "derivation": "x"}}, "4.006",
     "reproduced_within_tolerances"),
    ({"Netto-Cashflow": {"upper": {"abs_tol": 0.01, "rel_tol": 0}, "lower": EXACT, "derivation": "x"}}, "4.006",
     "not_reproduced"),
    ({"Netto-Cashflow": {"decimals": 2, "upper": {"abs_tol": 0, "rel_tol": 0.01}, "lower": EXACT,
                         "derivation": "x"}}, None, "reproduced_within_tolerances"),
])
def test_replay_states_what_its_tolerance_profile_holds(world, monkeypatch, capsys, per_quantity, altered,
                                                        outcome):
    recorded_run(world)
    folder = world / "run"
    if altered:
        path = folder / "results.csv"
        path.write_text(path.read_text("utf-8").replace("MP-B,1,2,4\n", f"MP-B,1,2,{altered}\n"), "utf-8")
        rehash(folder)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", StubEngine)
    arguments = ["replay", str(folder / "run-record.json"), "--repositories", str(world)]
    if per_quantity:
        arguments += ["--tolerance", str(tolerance_file(world, per_quantity))]
    assert main(arguments) == (0 if outcome.startswith("reproduced_") else 1)
    output = capsys.readouterr().out
    assert f"replay: {outcome}\n" in output
    assert stored(folder / "replay-record.json")["outcome"] == outcome
    # The compare result carries the profile unchanged.
    assert stored(folder / "replay-compare.result.json")["tolerance"] == {"per_quantity": per_quantity}


@pytest.mark.parametrize("content", [
    b"{ not JSON", b"[]", b'{"per_quantity": {}, "abs_tol": 0}',
    document_bytes({"per_quantity": {"Netto-Cashflow": {"upper": {"abs_tol": 0.1, "rel_tol": 0}, "lower": EXACT}}}),
    document_bytes({"per_quantity": {"Provisionen": {"upper": EXACT, "lower": EXACT}}}),  # not declared
    None])
def test_a_faulty_tolerance_file_is_a_usage_error_and_nothing_is_written(world, monkeypatch, capsys, content):
    recorded_run(world)
    folder = world / "run"
    path = world / "tolerance.json"
    if content is not None:
        path.write_bytes(content)
    before = folder_hashes(folder)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", StubEngine)
    assert main(["replay", str(folder / "run-record.json"), "--repositories", str(world),
                 "--tolerance", str(path)]) == 2
    assert "tolerance file" in capsys.readouterr().err
    assert folder_hashes(folder) == before and not (folder / "replay").exists()


@pytest.mark.parametrize("name", ["replay", "replay-record.json", "replay-compare.request.json",
                                  "replay-compare.result.json"])
def test_replay_overwrites_no_file(world, monkeypatch, name):
    recorded_run(world)
    folder = world / "run"
    (folder / name).write_bytes(b"kept")
    before = folder_hashes(folder)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", StubEngine)
    assert main(["replay", str(folder / "run-record.json"), "--repositories", str(world)]) == 2
    assert folder_hashes(folder) == before


def test_a_repeated_run_that_does_not_succeed_is_not_reproduced(world, monkeypatch, capsys):
    recorded_run(world)
    folder = world / "run"
    monkeypatch.setattr(StubSession, "project", lambda self, model_point_id: (_ for _ in ()).throw(
        ModelPointFailure("The stub cannot calculate this model point.")))
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", StubEngine)
    assert main(["replay", str(folder / "run-record.json"), "--repositories", str(world)]) == 1
    output = capsys.readouterr().out
    assert "replay: not_reproduced" in output and "comparison: rejected" in output
    assert "model_point_failed" in output
    record = stored(folder / "replay-record.json")
    assert record["outcome"] == "not_reproduced" and not schema_errors(record, RECORD_SCHEMA)
    assert "export" not in roles(record["outputs"])
    compared = stored(folder / "replay-compare.result.json")
    assert not schema_errors(compared, COMPARE_SCHEMA)
    assert compared["outcome"] == "rejected" and compared["diagnostics"][0]["code"] == "model_point_failed"


def test_not_reproduced_replay_prints_the_coordinates_and_exits_non_zero(world, monkeypatch, capsys):
    recorded_run(world)
    folder = world / "run"
    alter_export(folder)
    rehash(folder)
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", StubEngine)
    assert main(["replay", str(folder / "run-record.json"), "--repositories", str(world)]) == 1
    output = capsys.readouterr().out
    assert output.splitlines()[:2] == ["replay: not_reproduced", "deviating coordinates: 1"]
    assert "compare result: " in output and "replay-compare.result.json" in output
    assert "replay record: " in output
    assert stored(folder / "replay-record.json")["outcome"] == "not_reproduced"


class CoreBreaker(StubEngine):
    """An engine whose inventory the record does not allow: an error of the core stops the run."""

    @contextmanager
    def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
        with super().open(release, enabled, manifest_dir, repositories, hold) as session:
            session.parameters = lambda: [{"name": "rate", "type": "scalar"}]
            yield session


class OpenBreaks(StubEngine):
    """An engine that raises while it restores the release: the run ends with the outcome error."""

    def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
        raise RuntimeError("the engine broke")


def test_replay_removes_its_folder_when_the_repeated_run_raises(world, monkeypatch):
    recorded_run(world)
    folder = world / "run"
    before = folder_hashes(folder)

    with pytest.raises(RuntimeError, match="parameter inventory"):
        replay(folder / "run-record.json", CoreBreaker(), repositories=world)
    assert not (folder / "replay").exists() and folder_hashes(folder) == before
    # An engine that raises is no error of the core: the repeated run ends with an error.
    done = replay(folder / "run-record.json", OpenBreaks(), repositories=world)
    assert done.outcome == "not_reproduced"
    assert stored(folder / "replay" / "response.json")["outcome"] == "error"
    assert done.compare_result["diagnostics"][0]["code"] == "state_not_readable"
    remove_replay(folder)
    assert replay(folder / "run-record.json", StubEngine(), repositories=world).outcome == "reproduced_exactly"
    # Neither does a comparison that raises leave a file behind.
    remove_replay(folder)
    monkeypatch.setattr("degelmann.deltarecon.replay.compare", lambda *a, **k: (_ for _ in ()).throw(
        RuntimeError("the comparison broke")))
    with pytest.raises(RuntimeError, match="the comparison broke"):
        replay(folder / "run-record.json", StubEngine(), repositories=world)
    assert folder_hashes(folder) == before


def test_only_the_record_of_a_succeeded_run_is_replayed(world):
    (world / "rel" / "points.csv").write_text(POINTS.replace("MP-B,0,2,2", "MP-B,0,2,raise"), "utf-8")
    result, _ = run_stub(world)
    assert result.outcome == "failed"
    with pytest.raises(UsageError):
        replay(world / "run" / "run-record.json", StubEngine(), repositories=world)
    assert not (world / "run" / "replay").exists()


# --- regression on the stub engine --------------------------------------------------


def test_regression_runs_the_release_on_the_recorded_selection_and_compares(world, capsys):
    from degelmann.deltarecon.__main__ import print_comparison
    selection = {"mode": "subset", "model_point_ids": ["MP-B", "MP-A", "MP-D"]}
    result, _ = run_stub(world, stub_request(world, selection=selection))
    assert result.outcome == "succeeded"
    before = folder_hashes(world / "run")
    # The newer release moves MP-B and holds MP-C with another base; MP-C is not selected.
    points = POINTS_B.replace("MP-C,0,0,1e-05", "MP-C,0,0,7")
    release = stub_release(world, "rel-new", points, PARAMS_RATE)
    done = stub_regression(world, release)
    out = world / "out"
    assert done.run.outcome == "succeeded" and not done.no_deviation
    assert sorted(p.name for p in out.iterdir()) == [
        "compare.deviations.csv", "compare.request.json", "compare.result.json", "compare.run-record.json",
        "recorded", "run", "signature-table.json"]
    # The recorded run is copied byte for byte, and its folder stays as it is.
    assert folder_hashes(out / "recorded") == before == folder_hashes(world / "run")
    # The new run is a normal run with the ids of the regression and the recorded selection.
    assert_documents_valid(out / "run")
    request = stored(out / "run" / "request.json")
    assert request["run_id"] == "regression-run-stub" and request["release"] == release
    assert request["selection"] == selection and request["changes"] == {"enabled": []}
    compare_request = stored(out / "compare.request.json")
    assert compare_request["compare_id"] == "compare-regression-run-stub"
    assert compare_request["left"]["response"]["path"] == "recorded/response.json"
    assert compare_request["left"]["run_record"]["path"] == "recorded/run-record.json"
    assert compare_request["right"]["response"]["path"] == "run/response.json"
    assert compare_request["right"]["run_record"]["path"] == "run/run-record.json"
    assert compare_request["tolerance"] == {"per_quantity": {}}
    for name in ("compare.request.json", "compare.result.json", "signature-table.json"):
        assert not schema_errors(stored(out / name), COMPARE_SCHEMA), name

    compared = stored(out / "compare.result.json")
    assert compared["outcome"] == "compared" and compared["added"] == compared["removed"] == []
    listed = deviation_rows(out / "compare.result.json")
    assert listed == expected_deviations(world / "run" / "results.csv", out / "run" / "results.csv", {})
    assert compared["deviating_model_points"] == ["MP-B"] and len(listed) == 6
    assert compared["left"] == {"run_id": "run-stub", "release_label": "N"}
    assert compared["right"] == {"run_id": "regression-run-stub", "release_label": "regression"}
    assert compared["parameter_diff"] == [
        {"name": "rate", "change": "changed", "type": "scalar", "old": 0.01, "new": 0.02}]
    record = stored(out / "compare.run-record.json")
    assert not schema_errors(record, RECORD_SCHEMA) and record["outcome"] == "compared"
    assert roles(record["outputs"]) == {"result": "compare.result.json", "deviations": "compare.deviations.csv",
                                        "signature_table": "signature-table.json"}
    assert record["releases"] == [stored(world / "run" / "request.json")["release"], release]
    table = stored(out / "signature-table.json")
    assert [(row["stage"], row["quantity"], row["deviating_model_points"], row["deviating_coordinates"])
            for row in table["rows"]] == [("liability_cashflow", "Anzahl Verträge", 1, 3),
                                          ("liability_cashflow", "Netto-Cashflow", 1, 3)]

    # The command line names the stage, every deviating model point, and the table.
    assert print_comparison("regression", done.comparison) == 1
    output = capsys.readouterr().out
    assert "regression: 6 deviating coordinates in 1 model points" in output
    assert "stage: liability_cashflow" in output
    assert "deviation: liability_cashflow / model point MP-B: 6 coordinates, periods 0 to 2" in output
    assert "liability_cashflow / Netto-Cashflow: 1 model points, 3 coordinates" in output
    # The table comes before the line per deviating model point.
    assert output.index("signature table:") < output.index("deviation: liability_cashflow / model point MP-B")
    assert "no deviation" not in output

    # A second regression run into the same folder overwrites nothing.
    kept = folder_hashes(out)
    with pytest.raises(UsageError):
        stub_regression(world, release)
    assert folder_hashes(out) == kept


@pytest.mark.parametrize("per_quantity, status", [
    (None, 1),
    ({"Anzahl Verträge": {"upper": {"abs_tol": 2, "rel_tol": 0}, "lower": EXACT, "derivation": "x"},
      "Netto-Cashflow": {"upper": {"abs_tol": 6, "rel_tol": 0}, "lower": EXACT, "derivation": "x"}}, 0),
    ({"Anzahl Verträge": {"upper": {"abs_tol": 2, "rel_tol": 0}, "lower": EXACT, "derivation": "x"},
      "Netto-Cashflow": {"upper": EXACT, "lower": {"abs_tol": 6, "rel_tol": 0}, "derivation": "x"}}, 1),
])
def test_regression_compares_exactly_unless_a_tolerance_file_is_named(world, capsys, per_quantity, status):
    from degelmann.deltarecon.__main__ import print_comparison
    recorded_run(world)
    tolerance = tolerance_file(world, per_quantity) if per_quantity else None
    done = stub_regression(world, stub_release(world, "rel-new", POINTS_B), tolerance=tolerance)
    assert print_comparison("regression", done.comparison) == status
    assert ("regression: no deviation above tolerance" in capsys.readouterr().out) == (status == 0)
    assert stored(world / "out" / "compare.result.json")["tolerance"] == {"per_quantity": per_quantity or {}}


def test_regression_of_an_unchanged_release_shows_no_deviation(world, capsys):
    from degelmann.deltarecon.__main__ import print_comparison
    recorded_run(world)
    done = stub_regression(world, stub_release(world, "rel-new"))
    assert done.no_deviation and print_comparison("regression", done.comparison) == 0
    assert capsys.readouterr().out.splitlines()[:2] == ["regression: no deviation above tolerance",
                                                        "signature table: no rows"]
    assert stored(world / "out" / "signature-table.json")["rows"] == []


class OtherTimeBasis(StubEngine):
    @contextmanager
    def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
        with super().open(release, enabled, manifest_dir, repositories, hold) as session:
            if release["label"] == "regression":
                session.time_basis = "valuation_year"
            yield session


@pytest.mark.parametrize("case", ["coverage", "incompatible"])
def test_regression_never_reports_no_deviation_for_a_coverage_difference_or_no_comparison(world, capsys, case):
    from degelmann.deltarecon.__main__ import print_comparison
    recorded_run(world)
    if case == "coverage":  # only the period range of MP-B differs: it ends two periods later
        done = stub_regression(world, stub_release(world, "rel-new", POINTS.replace("MP-B,0,2,2", "MP-B,0,4,2")))
    else:
        done = stub_regression(world, stub_release(world, "rel-new"), OtherTimeBasis())
    assert not done.no_deviation and print_comparison("regression", done.comparison) == 1
    output = capsys.readouterr().out
    assert "no deviation" not in output
    compared = stored(world / "out" / "compare.result.json")
    if case == "coverage":
        assert deviation_rows(world / "out" / "compare.result.json") == []
        assert compared["added"] == [{"model_point_id": "MP-B", "first_period": 3, "last_period": 4}]
        assert compared["removed"] == []
        assert "added: liability_cashflow / model point MP-B, periods 3 to 4" in output
    else:
        assert compared["outcome"] == "incompatible"
        assert "regression: incompatible" in output and "diagnostic: time_basis_mismatch:" in output
        assert not (world / "out" / "signature-table.json").exists()


def test_regression_whose_run_does_not_succeed_compares_nothing_and_keeps_the_run(world):
    recorded_run(world)
    done = stub_regression(world, stub_release(world, "rel-new", POINTS.replace("MP-B,0,2,2", "MP-B,0,2,raise")))
    assert done.run.outcome == "failed" and done.comparison is None and not done.no_deviation
    out = world / "out"
    assert sorted(p.name for p in out.iterdir()) == ["recorded", "run"]
    assert sorted(p.name for p in (out / "run").iterdir()) == ["request.json", "response.json", "run-record.json"]
    assert_documents_valid(out / "run")


def test_regression_rejects_a_release_that_cannot_be_restored_and_writes_nothing_when_the_engine_raises(world):
    recorded_run(world)
    release = stub_release(world, "rel-new")
    broken = {"label": "regression", "references": [{**r, "value": "points.csv sha256:" + "0" * 64}
                                                    if r["kind"] == "input_data" else r
                                                    for r in release["references"]]}
    # A release the engine cannot restore is a rejected run: its documents stay, nothing is compared.
    done = stub_regression(world, broken)
    out = world / "out"
    assert done.run.outcome == "rejected" and done.comparison is None
    assert done.run.response["diagnostics"][0]["code"] == "unknown_reference"
    assert sorted(p.name for p in out.iterdir()) == ["recorded", "run"]
    assert sorted(p.name for p in (out / "run").iterdir()) == ["request.json", "response.json", "run-record.json"]
    assert_documents_valid(out / "run")
    shutil.rmtree(out)

    # An engine that raises ends the new run with an error: nothing is compared, the run stays.
    done = stub_regression(world, release, OpenBreaks())
    assert done.run.outcome == "error" and done.comparison is None and not done.no_deviation
    assert done.run.response["diagnostics"] == [{"code": "state_not_readable",
                                                 "message": "RuntimeError: the engine broke"}]
    assert sorted(p.name for p in out.iterdir()) == ["recorded", "run"]
    assert_documents_valid(out / "run")
    shutil.rmtree(out)
    # An error of the core stops the regression and leaves no folder.
    with pytest.raises(RuntimeError, match="parameter inventory"):
        stub_regression(world, release, CoreBreaker())
    assert not (world / "out").exists()
    with pytest.raises(UsageError, match="tolerance file"):
        stub_regression(world, release, tolerance=world / "absent.json")
    assert not (world / "out").exists()


def test_a_repeated_regression_and_replay_differ_only_in_records_and_the_requests_that_name_them(world):
    """Only run records carry the identity of an execution; a compare request names records by hash."""
    recorded_run(world)
    release = stub_release(world, "rel-new", POINTS_B)
    recorded = read_regression_input(world / "run" / "run-record.json", StubEngine.stages)
    for name in ("out-1", "out-2"):
        regression(recorded, release, world / name, StubEngine(), repositories=world)
    one, two = folder_hashes(world / "out-1"), folder_hashes(world / "out-2")
    differing = sorted(name for name in one if one[name] != two[name])
    assert differing == ["compare.request.json", "compare.run-record.json", "run/run-record.json"]
    assert set(one) == set(two)
    for name in ("compare.run-record.json", "run/run-record.json"):
        records = [stored(world / out / name) for out in ("out-1", "out-2")]
        assert without_volatile(records[0], "inputs") == without_volatile(records[1], "inputs")
    requests = [stored(world / out / "compare.request.json") for out in ("out-1", "out-2")]
    requests[0]["right"]["run_record"] = requests[1]["right"]["run_record"]
    assert requests[0] == requests[1]

    # Two replays of one record, in two copies of the recorded folder.
    for name in ("copy-1", "copy-2"):
        shutil.copytree(world / "run", world / name)
        replay(world / name / "run-record.json", StubEngine(), repositories=world)
    one, two = folder_hashes(world / "copy-1"), folder_hashes(world / "copy-2")
    assert sorted(name for name in one if one[name] != two[name]) == [
        "replay-compare.request.json", "replay-record.json", "replay/run-record.json"]


@pytest.mark.parametrize("case", ["failed-run", "error-run", "replay", "enabled-changes", "existing-output",
                                  "no-record"])
def test_regression_command_starts_nothing_for_a_record_it_does_not_take(world, monkeypatch, capsys, case):
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", StubEngine)
    record, out = world / "run" / "run-record.json", world / "out"
    if case == "failed-run":
        (world / "rel" / "points.csv").write_text(POINTS.replace("MP-B,0,2,2", "MP-B,0,2,raise"), "utf-8")
        assert run_stub(world)[0].outcome == "failed"
    elif case == "error-run":
        (world / "rel" / "points.csv").write_text("id,first,last,base\n", "utf-8")
        assert run_stub(world)[0].outcome == "error"
    elif case == "enabled-changes":
        recorded_run(world, with_changes=True)
    elif case != "no-record":
        recorded_run(world)
    if case == "replay":
        assert replay(record, StubEngine(), repositories=world).outcome == "reproduced_exactly"
        record = world / "run" / "replay-record.json"
    if case == "existing-output":
        out.mkdir()
    before = folder_hashes(world)
    assert main(["regression", str(record), "--revision", "HEAD", "--repositories", str(world),
                 "--output", str(out)]) == 2
    assert capsys.readouterr().err.startswith("error: ")
    assert folder_hashes(world) == before and out.exists() == (case == "existing-output")


# --- the core and the engine --------------------------------------------------------


def test_core_modules_load_no_engine_and_cannot_start_git():
    """Without ``subprocess`` a module starts no process, so none but the adapter starts Git."""
    code = ("import sys\n"
            + "".join(f"import degelmann.deltarecon.{name}\n" for name in CORE_MODULES)
            + "loaded = [m for m in ('modelx', 'pandas', 'numpy', 'subprocess') if m in sys.modules]\n"
            + "assert not loaded, loaded\n")
    done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_only_the_adapter_imports_the_engine_and_calls_git():
    sources = sorted((ROOT / "degelmann" / "deltarecon").rglob("*.py"))

    def importing(*modules: str) -> list[str]:
        return [p.relative_to(ROOT).as_posix() for p in sources
                if any(line.split()[:1] in (["import"], ["from"]) and line.split()[1].split(".")[0] in modules
                       for line in p.read_text("utf-8").splitlines() if len(line.split()) > 1)]

    assert importing("modelx") == ["degelmann/deltarecon/engines/reference_model.py"]
    # Git is started as a process, and only the adapter can start one: no other module
    # names ``subprocess`` or a process starter of ``os`` in any form.
    starters = (r"\bsubprocess\b|\bos\s*\.\s*(system|popen|exec\w*|spawn\w*|posix_spawn\w*|fork\w*|startfile)\b"
                r"|\bfrom\s+os\s+import\b")
    assert [p.relative_to(ROOT).as_posix() for p in sources if re.search(starters, p.read_text("utf-8"))] == [
        "degelmann/deltarecon/engines/reference_model.py"]
    for line in ("import os, subprocess", "os.system('git')", "os.popen('git')", "os.execvp('git', [])",
                 "os.spawnlp(0, 'git')", "from os import system", "from subprocess import run"):
        assert re.search(starters, line), line
    assert not re.search(starters, "import os\nos.path.relpath(path)")
    assert {p.name for p in sources} >= {f"{name}.py" for name in CORE_MODULES}


# --- the reference model ------------------------------------------------------------

RELEASE_VALUE = f"git:{REPOSITORY_URL}@{START}"


def in_force_id() -> str:
    lines = text(POINT_TABLE).splitlines()
    columns = lines[0].split(",")
    row = next(line.split(",") for line in lines[1:] if line.split(",")[columns.index("duration_y")] != "0")
    return row[columns.index("policy_id")]


def named_revisions(request: dict) -> dict[str, str]:
    return {r["kind"]: r["value"] for r in request["release"]["references"]}


def point_line(policy_id: str) -> tuple[list[str], str]:
    """The columns of the model point table and the line of one model point of the start commit of the reference chain
    (release N on the fixed model)."""
    lines = text(POINT_TABLE).split("\n")
    return lines[0].split(","), next(line for line in lines if line.split(",")[1:2] == [policy_id])


def test_request_command_names_the_complete_release_identity(monkeypatch, tmp_path):
    request = stored(model_request(monkeypatch, tmp_path / "run"))
    references = request["release"]["references"]
    assert all(set(r) == {"kind", "value"} for r in references)  # opaque, without artifact
    assert [r["kind"] for r in references] == ["code_state", "parameter_set", "input_data", "engine_version"]
    # One reference per kind a revision determines, all three with the same value.
    assert [r["value"] for r in references[:3]] == [RELEASE_VALUE] * 3
    assert RELEASE_VALUE == "git:https://github.com/Degelmann-Solutions/delib-history@" + START
    assert re.fullmatch(r"[0-9a-f]{40}", START)
    version = references[3]["value"]
    assert all(name in version for name in ("modelx ", "pandas ", "numpy ", "Python "))
    assert request["selection"] == {"mode": "full"} and request["changes"] == {"enabled": []}
    # The command overwrites no request.
    assert cli(monkeypatch, "request", "--revision", START, "--repositories", REPOSITORIES, "--label", "N",
               "--run-id", "x", "--output", tmp_path / "run" / "request.json") == 2

    from degelmann.deltarecon.engines.reference_model import ReferenceModel
    assert ReferenceModel.determines == {"code_state", "parameter_set", "input_data"}
    assert ReferenceModel.realisations == {"text_patch", "revision"}
    assert ReferenceModel.holdable == {"input_data": {"data"}}


def test_request_command_resolves_any_name_of_a_commit_to_the_full_hash(monkeypatch, tmp_path):
    repositories, clone = throwaway(tmp_path)
    git(clone, "branch", "start", START)
    for number, name in enumerate(["HEAD", "work", "start", START[:10], START]):
        request = stored(model_request(monkeypatch, tmp_path / f"run-{number}", revision=name,
                                       repositories=repositories))
        assert named_revisions(request)["code_state"] == RELEASE_VALUE, name


@pytest.mark.parametrize("name", ["no-such-branch", "0123456789abcdef0123456789abcdef01234567",
                                  f"{START}^{{tree}}", "--all", ""])
def test_request_command_refuses_a_name_that_names_no_commit(monkeypatch, tmp_path, capsys, name):
    output = tmp_path / "run" / "request.json"
    assert cli(monkeypatch, "request", f"--revision={name}", "--repositories", REPOSITORIES, "--label", "N",
               "--run-id", "x", "--output", output) == 1
    printed = capsys.readouterr().out
    assert printed.startswith("request: rejected\ndiagnostic: unknown_reference: ")
    assert "holds no commit named" in printed
    assert not output.exists() and not output.parent.exists()


def test_request_command_with_an_existing_output_starts_nothing_before_it_resolves_the_revision(
        monkeypatch, tmp_path, capsys):
    output = tmp_path / "run" / "request.json"
    output.parent.mkdir()
    output.write_bytes(b"kept")
    assert cli(monkeypatch, "request", "--revision", "no-such-branch", "--repositories", REPOSITORIES,
               "--label", "N", "--run-id", "x", "--output", output) == 2
    printed = capsys.readouterr()
    assert printed.out == "" and printed.err.startswith("error: ") and "exists already" in printed.err
    assert output.read_bytes() == b"kept" and [p.name for p in output.parent.iterdir()] == ["request.json"]


def test_request_command_with_a_misplaced_manifest_starts_nothing_before_it_resolves_the_revision(
        monkeypatch, tmp_path, capsys):
    output = tmp_path / "run" / "request.json"
    manifest = tmp_path / "elsewhere" / "changes.json"
    manifest.parent.mkdir()
    manifest.write_bytes(b"{}")
    assert cli(monkeypatch, "request", "--revision", "no-such-branch", "--repositories", REPOSITORIES,
               "--label", "N", "--run-id", "x", "--output", output, "--enable", "c1", "--manifest", manifest) == 2
    printed = capsys.readouterr()
    assert printed.out == "" and printed.err == ("error: the manifest must be a file in the folder of the request "
                                                 "or below it\n")
    assert not output.parent.exists() and manifest.read_bytes() == b"{}"


def test_request_command_without_a_clone_names_where_it_is_expected(monkeypatch, tmp_path, capsys):
    output = tmp_path / "run" / "request.json"
    (tmp_path / "empty" / CLONE_NAME).mkdir(parents=True)  # a folder that is no repository
    for repositories in (tmp_path / "absent", tmp_path / "empty"):
        assert cli(monkeypatch, "request", "--revision", START, "--repositories", repositories,
                   "--label", "N", "--run-id", "x", "--output", output) == 1
        printed = capsys.readouterr().out
        assert printed.startswith("request: rejected\ndiagnostic: unknown_reference: ")
        assert f"git clone {REPOSITORY_URL} {repositories / CLONE_NAME}" in printed
        assert not output.parent.exists()


def test_subset_run_and_replay_of_release_n(monkeypatch, tmp_path, capsys, full_chain):
    in_force = in_force_id()
    before = clone_state()
    folder = tmp_path / "run"
    request_path = model_request(monkeypatch, folder, in_force, NEW_BUSINESS)
    assert cli(monkeypatch, "run", request_path, "--repositories", REPOSITORIES) == 0
    assert "outcome: succeeded" in capsys.readouterr().out
    assert_documents_valid(folder)
    request, response, record = (stored(folder / name) for name in
                                 ("request.json", "response.json", "run-record.json"))
    values = check_response(request, response, folder)
    assert export_errors(folder / "results.csv") == []
    assert record["releases"] == [request["release"]]  # the record holds the identity unchanged
    assert {p["model_point_id"] for p in response["model_points"]} == {in_force, NEW_BUSINESS}
    ranges = {p["model_point_id"]: p for p in response["model_points"]}
    assert ranges[NEW_BUSINESS]["first_period"] == 0 and ranges[in_force]["first_period"] >= 12
    assert ranges[in_force]["first_period"] % 12 == 0
    assert len(response["quantities"]) == 10
    assert "kalkulatorische Kosten" not in [q["name"] for q in response["quantities"]]

    # The parameter inventory: scalar references by name, the five tables by file stem.
    parameters = {p["name"]: p for p in record["parameters"]}
    assert list(parameters) == sorted(parameters)
    assert parameters["rechnungszins"] == {"name": "rechnungszins", "type": "scalar", "value": 0.01}
    assert parameters["suicide_years"]["value"] == 3 and parameters["val_tol"]["value"] == 1e-09
    assert parameters["lapse_file"]["value"] == "lapse_table.csv"
    assert "point_id" not in parameters
    tables = {name: p for name, p in parameters.items() if p["type"] == "keyed_table"}
    assert sorted(tables) == ["benefit_schedule", "freq_loading_table", "lapse_table", "mort_table",
                              "nvg_schedule"]
    assert tables["mort_table"]["key_columns"] == ["table_id", "sex", "smoker", "age"]
    assert tables["mort_table"]["value_columns"] == ["mort_rate"]
    assert tables["lapse_table"]["rows"][0] == {"key": [1], "values": [0.06]}
    assert tables["freq_loading_table"]["value_columns"] == ["instalments", "prem_freq_load"]
    assert [row["key"] for row in tables["freq_loading_table"]["rows"]] == [
        ["halbjaehrlich"], ["jaehrlich"], ["monatlich"], ["vierteljaehrlich"]]
    for table in tables.values():
        assert "provenance" not in table["value_columns"]
        keys = [row["key"] for row in table["rows"]]
        assert keys == sorted(keys) and len(keys) > 3

    # A subset run returns the values of the full run.
    chain = full_chain["folder"]
    full_values = check_export(stored(chain / "response.json"), chain / "results.csv")
    assert values == {key: numbers for key, numbers in full_values.items() if key[0] in {in_force, NEW_BUSINESS}}

    assert cli(monkeypatch, "replay", folder / "run-record.json", "--repositories", REPOSITORIES) == 0
    assert "replay: reproduced_exactly" in capsys.readouterr().out
    assert stored(folder / "replay-record.json")["outcome"] == "reproduced_exactly"
    assert clone_state() == before


def run_model(path: Path, request: dict | None = None, repositories: Path = REPOSITORIES):
    from degelmann.deltarecon.engines.reference_model import ReferenceModel
    if request is not None:
        path.write_bytes(document_bytes(request))
    return run_request(path, ReferenceModel(), repositories=repositories)


def assert_unknown_reference(result, folder: Path) -> str:
    assert result.outcome == "rejected"
    assert [d["code"] for d in result.response["diagnostics"]] == ["unknown_reference"]
    assert_documents_valid(folder)
    assert sorted(p.name for p in folder.iterdir()) == ["request.json", "response.json", "run-record.json"]
    return result.response["diagnostics"][0]["message"]


IDENTITY_EDITS = {
    # A determined kind or the engine version is missing, surplus, or differing.
    "missing-kind": lambda refs: refs.pop(1),
    "surplus-kind": lambda refs: refs.append({**refs[1], "value": RELEASE_VALUE[:-40] + "1" * 40}),
    "surplus-other-kind": lambda refs: refs.append({"kind": "release_folder", "value": "releases/N"}),
    # ``code_state`` and ``parameter_set`` name one commit; ``input_data`` may name another
    # one, which the clone must hold.
    "two-state-revisions": lambda refs: refs[1].update(value=RELEASE_VALUE[:-40] + "1" * 40),
    "input-data-at-an-unknown-hash": lambda refs: refs[2].update(value=RELEASE_VALUE[:-40] + "1" * 40),
    "input-data-in-another-repository": lambda refs: refs[2].update(
        value=refs[2]["value"].replace("delib-history", "other-history")),
    "no-engine": lambda refs: refs.pop(3),
    "other-engine": lambda refs: refs[3].update(value="modelx 0.0.1"),
    # A value of the export form that names another Python, and one whose suffix stands elsewhere.
    "other-engine-on-the-export-path": lambda refs: refs[3].update(value=refs[3]["value"].replace(", Python ", ", Python 0.")),
    "export-suffix-on-another-part": lambda refs: refs[3].update(
        value=refs[3]["value"].replace(" export,", ",").replace(", numpy", " export, numpy")),
    "with-artifact": lambda refs: refs[2].update(artifact={"path": "request.json", "sha256": "0" * 64}),
    # The value does not name a commit of the repository the engine knows.
    "other-repository": lambda refs: [r.update(value=r["value"].replace("delib-history", "other-history"))
                                      for r in refs[:3]],
    "other-source": lambda refs: [r.update(value=r["value"].replace("git:", "svn:")) for r in refs[:3]],
    "short-hash": lambda refs: [r.update(value=r["value"][:-28]) for r in refs[:3]],
    "name-of-a-commit": lambda refs: [r.update(value=r["value"][:-40] + "HEAD") for r in refs[:3]],
    "upper-case-hash": lambda refs: [r.update(value=r["value"][:-40] + r["value"][-40:].upper())
                                     for r in refs[:3]],
    "unknown-hash": lambda refs: [r.update(value=r["value"][:-40] + "1" * 40) for r in refs[:3]],
    "no-revision": lambda refs: [r.update(value=r["value"][:-41]) for r in refs[:3]],
}


@pytest.mark.parametrize("edit", sorted(IDENTITY_EDITS))
def test_incomplete_or_wrong_release_identity_is_an_unknown_reference(monkeypatch, tmp_path, edit):
    path = model_request(monkeypatch, tmp_path / "run", NEW_BUSINESS)
    request = stored(path)
    before = json.dumps(request["release"])
    IDENTITY_EDITS[edit](request["release"]["references"])
    assert json.dumps(request["release"]) != before
    assert not schema_errors(request, RUN_REQUEST)
    assert_unknown_reference(run_model(path, request), tmp_path / "run")


def test_a_hash_that_names_no_commit_is_an_unknown_reference(monkeypatch, tmp_path):
    repositories, clone = throwaway(tmp_path)
    git(clone, "-c", "user.name=Test", "-c", "user.email=test@example.invalid", "tag", "-a", "-m", "N", "n")
    objects = {"tree": git(clone, "rev-parse", "HEAD^{tree}"), "tag": git(clone, "rev-parse", "n"),
               "blob": git(clone, "rev-parse", "HEAD:README.md")}
    request = stored(model_request(monkeypatch, tmp_path / "base", NEW_BUSINESS, repositories=repositories))
    for kind, object_id in objects.items():
        object_id = object_id.decode("ascii").strip()
        assert object_id != START and git(clone, "cat-file", "-t", object_id).strip() == kind.encode()
        for reference in request["release"]["references"][:3]:
            reference["value"] = f"git:{REPOSITORY_URL}@{object_id}"
        folder = tmp_path / kind
        folder.mkdir()
        message = assert_unknown_reference(
            run_model(folder / "request.json", request, repositories), folder)
        assert f"is a {kind}, not a commit" in message


def test_run_without_a_clone_is_rejected_and_names_where_the_clone_is_expected(monkeypatch, tmp_path, capsys):
    folder = tmp_path / "run"
    path = model_request(monkeypatch, folder, NEW_BUSINESS)
    assert cli(monkeypatch, "run", path, "--repositories", tmp_path / "absent") == 1
    assert "unknown_reference" in capsys.readouterr().out
    (diagnostic,) = stored(folder / "response.json")["diagnostics"]
    assert diagnostic["code"] == "unknown_reference"
    assert f"git clone {REPOSITORY_URL} {tmp_path / 'absent' / CLONE_NAME}" in diagnostic["message"]
    assert_documents_valid(folder)
    assert not (folder / "results.csv").exists()


def test_without_git_no_command_starts(monkeypatch, tmp_path, capsys):
    folder = tmp_path / "run"
    path = model_request(monkeypatch, folder, NEW_BUSINESS)
    recorded = tmp_path / "recorded"
    assert cli(monkeypatch, "run", model_request(monkeypatch, recorded, NEW_BUSINESS),
               "--repositories", REPOSITORIES) == 0
    capsys.readouterr()
    (tmp_path / "bin").mkdir()
    monkeypatch.setenv("PATH", str(tmp_path / "bin"))
    assert cli(monkeypatch, "run", path, "--repositories", REPOSITORIES) == 2
    assert "git is not installed" in capsys.readouterr().err
    assert cli(monkeypatch, "replay", recorded / "run-record.json", "--repositories", REPOSITORIES) == 2
    assert "git is not installed" in capsys.readouterr().err
    assert not (recorded / "replay").exists() and not (recorded / "replay-record.json").exists()
    assert cli(monkeypatch, "request", "--revision", START, "--repositories", REPOSITORIES, "--label", "N",
               "--run-id", "x", "--output", tmp_path / "other" / "request.json") == 2
    assert "git is not installed" in capsys.readouterr().err
    # Neither does a command start when the repositories folder is absent as well.
    assert cli(monkeypatch, "run", path, "--repositories", tmp_path / "absent") == 2
    assert "git is not installed" in capsys.readouterr().err
    assert sorted(p.name for p in tmp_path.iterdir()) == ["bin", "recorded", "run"]
    assert sorted(p.name for p in folder.iterdir()) == ["request.json"]


def test_a_missing_clone_ends_the_test_session_with_the_clone_command(tmp_path):
    require_clone()  # the clone of this session passes
    (tmp_path / "empty").mkdir()  # a folder inside no repository must not pass as a clone
    for clone, revision in ((tmp_path / "absent", START), (tmp_path / "empty", START),
                            (CLONE, "1" * 40)):
        with pytest.raises(pytest.exit.Exception) as caught:
            require_clone(clone, revision)
        assert f"git clone {REPOSITORY_URL} {clone}" in str(caught.value.msg)
        assert caught.value.returncode == 1


def test_the_restored_files_are_the_committed_bytes_whatever_the_line_ending_setting(tmp_path):
    from degelmann.deltarecon.engines import reference_model
    repositories = tmp_path / "repositories"
    clone = repositories / CLONE_NAME
    git(ROOT, "clone", "--quiet", "--no-hardlinks", "--no-checkout", "-c", "core.autocrlf=true",
        str(CLONE), str(clone))
    # The repository pins line feeds in ``.gitattributes``. The clone overrides that too, so
    # that its working tree, and an archive made from it, really hold other bytes.
    (clone / ".git" / "info" / "attributes").write_text("* text eol=crlf\n", "utf-8")
    git(clone, "checkout", "--quiet", "--detach", RELEASE_N)
    assert git(clone, "config", "core.autocrlf").strip() == b"true"
    assert b"\r\n" in git(clone, "archive", "--format=tar", RELEASE_N, LAPSE_TABLE)
    assert b"\r\n" in (clone / LAPSE_TABLE).read_bytes()  # the working tree is not the committed state
    before = clone_state(clone)

    target = tmp_path / "state"
    target.mkdir()
    files = reference_model.read_tree(clone, RELEASE_N)
    reference_model.export_tree(clone, files, target)
    restored = {p.relative_to(target).as_posix(): p.read_bytes() for p in target.rglob("*") if p.is_file()}
    assert sorted(restored) == sorted(files) == sorted(
        git(CLONE, "ls-tree", "-r", "--name-only", RELEASE_N).decode("utf-8").splitlines())
    for path, data in restored.items():
        assert data == committed(path, RELEASE_N), path
        assert b"\r" not in data, path
    # The hashes UPSTREAM.md records for the files copied from lifelib, and the portfolio hash.
    recorded = dict(re.findall(r"^\| `([^`]+)` \| `([0-9a-f]{64})` \|$",
                               restored[f"{PRODUCT_FOLDER}/UPSTREAM.md"].decode("utf-8"), re.MULTILINE))
    assert len(recorded) == 10
    for name, digest in recorded.items():
        assert hashlib.sha256(restored[f"{PRODUCT_FOLDER}/{name}"]).hexdigest() == digest, name
    assert hashlib.sha256(restored[POINT_TABLE]).hexdigest() == (
        "d3d90e3725304643cfa12b79a874b34dacd2bf2edba7baabe582d0f97a11c693")
    assert clone_state(clone) == before


def test_no_file_is_restored_outside_the_scratch_folder(tmp_path):
    """A path that leaves the folder it is joined to is refused before anything is written."""
    from degelmann.deltarecon.engines import reference_model
    files = reference_model.read_tree(CLONE, RELEASE_N)
    blob = files["README.md"]
    target = tmp_path / "scratch" / "state"
    target.mkdir(parents=True)
    with pytest.raises(Rejection) as caught:
        reference_model.export_tree(CLONE, {"README.md": blob, "../outside.txt": blob}, target)
    assert caught.value.code == "unknown_reference" and "../outside.txt" in caught.value.message
    assert list(target.iterdir()) == [] and not (target.parent / "outside.txt").exists()


def test_a_later_revision_is_run_as_committed(monkeypatch, tmp_path, capsys, full_chain):
    """Release N plus one commit that changes a table; a change that is not committed is not run."""
    repositories, clone = throwaway(tmp_path)
    in_force = in_force_id()
    edit_file(clone, LAPSE_TABLE, "\n1,0.06,", "\n1,0.05,")
    dirty = clone_state(clone)
    assert b"lapse_table.csv" in dirty[0]

    def run(name: str, revision: str) -> tuple[dict, dict, dict]:
        folder = tmp_path / name
        path = model_request(monkeypatch, folder, in_force, NEW_BUSINESS, revision=revision,
                             repositories=repositories, run_id=f"run-{name}")
        assert cli(monkeypatch, "run", path, "--repositories", repositories) == 0
        assert_documents_valid(folder)
        request, response, record = (stored(folder / n) for n in
                                     ("request.json", "response.json", "run-record.json"))
        return request, check_response(request, response, folder), {p["name"]: p for p in record["parameters"]}

    # The working tree holds the change, the commit does not: the run is that of the start commit
    # of the reference chain (release N on the fixed model).
    request, first, parameters = run("first", "HEAD")
    assert named_revisions(request)["input_data"] == RELEASE_VALUE
    assert parameters["lapse_table"]["rows"][0] == {"key": [1], "values": [0.06]}
    chain = full_chain["folder"]
    full_values = check_export(stored(chain / "response.json"), chain / "results.csv")
    assert first == {key: numbers for key, numbers in full_values.items() if key[0] in {in_force, NEW_BUSINESS}}
    assert clone_state(clone) == dirty

    second_hash = commit(clone, "Lower the lapse rate of policy year 1")
    assert second_hash != START
    committed_state = clone_state(clone)
    request, second, parameters = run("second", "work")
    assert set(named_revisions(request).values()) - {named_revisions(request)["engine_version"]} == {
        f"git:{REPOSITORY_URL}@{second_hash}"}
    assert parameters["lapse_table"]["rows"][0] == {"key": [1], "values": [0.05]}
    assert set(second) == set(first)
    assert second[(NEW_BUSINESS, 0)][0] == first[(NEW_BUSINESS, 0)][0] == 1  # the opening in-force count
    assert second[(NEW_BUSINESS, 1)] != first[(NEW_BUSINESS, 1)]
    assert clone_state(clone) == committed_state

    # The first commit is still run as the start commit, and the replay of the second is reproduced.
    assert cli(monkeypatch, "replay", tmp_path / "first" / "run-record.json", "--repositories", repositories) == 0
    assert cli(monkeypatch, "replay", tmp_path / "second" / "run-record.json", "--repositories", repositories) == 0
    assert capsys.readouterr().out.count("replay: reproduced_exactly") == 2
    assert clone_state(clone) == committed_state
    # The pinned clone does not hold the second commit.
    other = tmp_path / "other"
    other.mkdir()
    assert "holds no object" in assert_unknown_reference(
        run_model(other / "request.json", stored(tmp_path / "second" / "request.json")), other)


def test_a_replace_reference_does_not_change_what_a_hash_names(monkeypatch, tmp_path):
    """After ``git replace`` the hash of release N still restores the tree of release N."""
    repositories, clone = throwaway(tmp_path)
    edit_file(clone, LAPSE_TABLE, "\n1,0.06,", "\n1,0.05,")
    other = commit(clone, "Lower the lapse rate of policy year 1")
    git(clone, "replace", RELEASE_N, other)
    # Git itself now reads the other commit under the hash of release N.
    replaced = subprocess.run(["git", "-C", str(clone), "cat-file", "blob", f"{RELEASE_N}:{LAPSE_TABLE}"],
                              capture_output=True, env={"PATH": os.environ["PATH"]}).stdout
    assert b"\n1,0.05," in replaced and b"\n1,0.06," in committed(LAPSE_TABLE, RELEASE_N)

    folder = tmp_path / "run"
    path = model_request(monkeypatch, folder, NEW_BUSINESS, revision=RELEASE_N, repositories=repositories)
    assert named_revisions(stored(path))["code_state"] == f"git:{REPOSITORY_URL}@{RELEASE_N}"
    assert cli(monkeypatch, "run", path, "--repositories", repositories) == 0
    parameters = {p["name"]: p for p in stored(folder / "run-record.json")["parameters"]}
    assert parameters["lapse_table"]["rows"][0] == {"key": [1], "values": [0.06]}


def test_revision_without_one_of_its_input_files_is_refused(monkeypatch, tmp_path, capsys):
    repositories, clone = throwaway(tmp_path)
    request = stored(model_request(monkeypatch, tmp_path / "base", NEW_BUSINESS, repositories=repositories))
    (clone / LAPSE_TABLE).unlink()
    without_table = commit(clone, "Remove the lapse table")
    shutil.rmtree(clone / PRODUCT_FOLDER / "RLV_DE_S")
    without_model = commit(clone, "Remove the model")
    capsys.readouterr()
    for name, revision, named in (("table", without_table, LAPSE_TABLE),
                                  ("model", without_model, f"{PRODUCT_FOLDER}/RLV_DE_S")):
        # The request command writes no request for the incomplete release.
        assert cli(monkeypatch, "request", "--revision", revision, "--repositories", repositories,
                   "--label", "N", "--run-id", "x", "--output", tmp_path / "none" / "request.json") == 1
        printed = capsys.readouterr().out
        assert printed.startswith("request: rejected\ndiagnostic: unknown_reference: ")
        assert named in printed and not (tmp_path / "none").exists()
        # A request that names it is rejected, not run.
        for reference in request["release"]["references"][:3]:
            reference["value"] = f"git:{REPOSITORY_URL}@{revision}"
        folder = tmp_path / name
        folder.mkdir()
        assert named in assert_unknown_reference(run_model(folder / "request.json", request, repositories), folder)


def test_false_built_in_check_is_a_failed_model_point(monkeypatch, tmp_path, capsys):
    repositories, clone = throwaway(tmp_path)
    lines = text(POINT_TABLE).splitlines()
    columns = lines[0].split(",")
    term = lines[15].split(",")[columns.index("policy_term")]
    broken = lines[15].split(",")[columns.index("policy_id")]
    edit_file(clone, POINT_TABLE, lines[15] + "\n", with_columns(columns, lines[15], duration_y=term) + "\n")
    revision = commit(clone, "Set a duration that equals the term")
    folder = tmp_path / "run"
    request_path = model_request(monkeypatch, folder, NEW_BUSINESS, broken, revision=revision,
                                 repositories=repositories)
    assert cli(monkeypatch, "run", request_path, "--repositories", repositories) == 1
    output = capsys.readouterr().out
    assert "outcome: failed" in output and broken in output
    assert_documents_valid(folder)
    response, record = stored(folder / "response.json"), stored(folder / "run-record.json")
    assert response["outcome"] == "failed"
    assert [f["model_point_id"] for f in response["failed_model_points"]] == [broken]
    assert "check_pols_roll_fwd is false" in response["failed_model_points"][0]["message"]
    assert not (folder / "results.csv").exists()
    assert record["outcome"] == "failed" and len(record["parameters"]) > 20


@pytest.mark.parametrize("path", ["export", "modelx"])
def test_projection_releases_the_item_space_of_each_point(tmp_path, path):
    """A run keeps no ItemSpace of a projected point alive, after a point that fails neither, on both paths."""
    from degelmann.deltarecon.engines.reference_model import ReferenceModel, release_references
    repositories, clone = throwaway(tmp_path)
    lines = text(POINT_TABLE).splitlines()
    columns = lines[0].split(",")
    term = lines[15].split(",")[columns.index("policy_term")]
    broken = lines[15].split(",")[columns.index("policy_id")]
    edit_file(clone, POINT_TABLE, lines[15] + "\n", with_columns(columns, lines[15], duration_y=term) + "\n")
    revision = commit(clone, "Set a duration that equals the term")
    release = {"label": "N", "references": release_references(revision, path=path)}
    with ReferenceModel().open(release, [], None, repositories) as session:
        projection = session._computing.Projection
        assert (projection is session._model.Projection) == (path == "modelx")

        def item_spaces() -> dict:  # modelx and the exported package name them differently
            return dict(projection.itemspaces if path == "modelx" else projection._mx_itemspaces)

        projection[1]
        assert item_spaces()  # the probe sees an ItemSpace that is alive
        del projection[1]
        for point in (NEW_BUSINESS, in_force_id()):
            assert session.project(point)
            assert item_spaces() == {}
        with pytest.raises(ModelPointFailure, match="check_pols_roll_fwd is false"):
            session.project(broken)
        assert item_spaces() == {}


def test_projection_keeps_the_failure_when_no_item_space_was_created():
    import pandas as pd
    from degelmann.deltarecon.engines.reference_model import ReferenceModelSession

    class Projection:
        deleted = []

        def __getitem__(self, index):
            raise ValueError("no item space")

        def __delitem__(self, index):
            self.deleted.append(index)
            raise KeyError(index)

    class Data:
        @staticmethod
        def model_point_table():
            return pd.DataFrame({"policy_id": ["RLV-000001"]})

    class Model:
        pass

    model = Model()
    model.Projection, model.Data = Projection(), Data()
    with pytest.raises(ModelPointFailure, match="result_cf raised ValueError: no item space"):
        ReferenceModelSession(model).project("RLV-000001")
    assert Projection.deleted == [0]


def test_projection_releases_the_item_space_when_result_cf_raises():
    import pandas as pd
    from degelmann.deltarecon.engines.reference_model import ReferenceModelSession

    class ItemSpace:
        @staticmethod
        def result_cf():
            raise ValueError("no result")

    class Projection:
        itemspaces = {}

        def __getitem__(self, index):
            return self.itemspaces.setdefault(index, ItemSpace())

        def __delitem__(self, index):
            del self.itemspaces[index]

    class Data:
        @staticmethod
        def model_point_table():
            return pd.DataFrame({"policy_id": ["RLV-000001"]})

    class Model:
        pass

    model = Model()
    model.Projection, model.Data = Projection(), Data()
    with pytest.raises(ModelPointFailure, match="result_cf raised ValueError: no result"):
        ReferenceModelSession(model).project("RLV-000001")
    assert Projection.itemspaces == {}


FORMULA_MESSAGE = (
    "Error raised during formula execution\n"
    "TypeError: unsupported operand type(s) for -: 'str' and 'int'\n"
    "\n"
    "Formula traceback:\n"
    "0: RLV_DE_S.Projection[1].lapse_rate(t=0), line 4\n"
    "1: RLV_DE_S.Data.lapse_table(), line 12\n"
    "\n"
    "Formula source:\n"
    "def lapse_table():\n"
    "    return pd.read_csv(\n"
    "        input_dir() / lapse_file, index_col=\"policy_year\")           # noqa: F821\n")


def test_a_formula_error_of_the_model_is_read_as_one_line():
    from degelmann.deltarecon.engines.reference_model import FormulaError, formula_error
    readable = formula_error(Exception(FORMULA_MESSAGE))
    assert type(readable) is FormulaError
    assert str(readable) == "TypeError: unsupported operand type(s) for -: 'str' and 'int' in RLV_DE_S.Data.lapse_table()"
    # A message of another form is left as it is.
    assert formula_error(Exception("one line")) is None
    assert formula_error(Exception(FORMULA_MESSAGE.replace("Formula traceback:", "Traceback:"))) is None


def test_an_assumption_table_the_model_cannot_read_ends_with_a_one_line_error(monkeypatch, tmp_path, capsys):
    repositories, clone = throwaway(tmp_path)
    edit_file(clone, LAPSE_TABLE, "policy_year,", "year,")
    revision = commit(clone, "Rename the key column of the lapse table")
    folder = tmp_path / "run"
    request_path = model_request(monkeypatch, folder, NEW_BUSINESS, revision=revision, repositories=repositories)
    assert cli(monkeypatch, "run", request_path, "--repositories", repositories) == 1
    response = stored(folder / "response.json")
    assert response["outcome"] == "error" and not (folder / "results.csv").exists()
    assert response["diagnostics"] == [{"code": "state_not_readable", "message":
                                        "FormulaError: ValueError: Index policy_year invalid in "
                                        "RLV_DE_S.Data.lapse_table()"}]
    assert_documents_valid(folder)


def test_blank_cell_in_an_assumption_table_rejects_the_request(monkeypatch, tmp_path, capsys):
    repositories, clone = throwaway(tmp_path)
    edit_file(clone, LAPSE_TABLE, "\n1,0.06,", "\n1,,")
    revision = commit(clone, "Blank the lapse rate of policy year 1")
    folder = tmp_path / "run"
    request_path = model_request(monkeypatch, folder, NEW_BUSINESS, revision=revision, repositories=repositories)
    assert cli(monkeypatch, "run", request_path, "--repositories", repositories) == 1
    assert "non_finite_value" in capsys.readouterr().out
    assert_documents_valid(folder)
    response, record = stored(folder / "response.json"), stored(folder / "run-record.json")
    assert response["outcome"] == "rejected"
    (diagnostic,) = response["diagnostics"]
    assert diagnostic["code"] == "non_finite_value" and "lapse_table" in diagnostic["message"]
    assert record["outcome"] == "rejected" and record["parameters"] == []
    assert not (folder / "results.csv").exists()


def test_unsupported_realisation_over_a_revision_is_rejected_and_names_the_change(monkeypatch, tmp_path, capsys):
    folder = tmp_path / "run"
    folder.mkdir()
    lapse = text(LAPSE_TABLE)
    entries = [
        change("chg-lapse-year-1", patch_text(LAPSE_TABLE, lapse, lapse.replace("\n1,0.06,", "\n1,0.05,")),
               folder, **{"class": "parameter"}),
        change("chg-switch", None, folder, realisation={"type": "engine_switch", "switch": "RC-1"}),
    ]
    manifest = {"document": "change_manifest", "contract_version": "3.1", "stage": "liability_cashflow",
                "manifest_id": "changes-synthetic", "base_release": "N", "changes": entries}
    (folder / "changes.json").write_bytes(document_bytes(manifest))
    assert cli(monkeypatch, "request", "--revision", START, "--repositories", REPOSITORIES, "--label", "N",
               "--run-id", "run-switch", "--output", folder / "request.json", "--subset", NEW_BUSINESS,
               "--enable", "chg-switch", "chg-lapse-year-1", "--manifest", folder / "changes.json") == 0
    assert cli(monkeypatch, "run", folder / "request.json", "--repositories", REPOSITORIES) == 1
    assert "unsupported_realisation" in capsys.readouterr().out
    (diagnostic,) = stored(folder / "response.json")["diagnostics"]
    assert diagnostic["code"] == "unsupported_realisation" and diagnostic["change_ids"] == ["chg-switch"]
    assert_documents_valid(folder)
    assert not (folder / "results.csv").exists()
    assert stored(folder / "run-record.json")["parameters"] == []


def test_an_enabled_revision_the_clone_does_not_hold_ends_with_the_outcome_error(monkeypatch, tmp_path, capsys):
    """The engine realises the type ``revision``: it accepts the request and cannot restore the state."""
    from degelmann.deltarecon.engines.reference_model import ReferenceModel
    assert "revision" in ReferenceModel.realisations
    folder = tmp_path / "run"
    folder.mkdir()
    manifest = {
        "document": "change_manifest", "contract_version": "3.1", "stage": "liability_cashflow",
        "manifest_id": f"history-{START}-{'1' * 40}", "base_release": "N",
        "history": {"source": "git", "from": START, "to": "1" * 40,
                    "determines": ["code_state", "input_data", "parameter_set"], "remainder": []},
        "changes": [{"id": "1" * 40, "class": ["parameter"], "description": "A later revision.",
                     "prerequisites": [], "conflicts": [],
                     "realisation": {"type": "revision", "source": "git", "revision": "1" * 40}}]}
    assert not schema_errors(manifest, CHANGES_SCHEMA)
    (folder / "changes.json").write_bytes(document_bytes(manifest))
    assert cli(monkeypatch, "request", "--revision", START, "--repositories", REPOSITORIES, "--label", "N",
               "--run-id", "run-revision", "--output", folder / "request.json", "--subset", NEW_BUSINESS,
               "--enable", "1" * 40, "--manifest", folder / "changes.json") == 0
    state = clone_state()
    assert cli(monkeypatch, "run", folder / "request.json", "--repositories", REPOSITORIES) == 1
    assert "state_not_readable" in capsys.readouterr().out
    response = stored(folder / "response.json")
    (diagnostic,) = response["diagnostics"]
    assert response["outcome"] == "error"
    assert diagnostic["code"] == "state_not_readable" and "1" * 40 in diagnostic["message"]
    assert str(REPOSITORIES) not in diagnostic["message"]
    assert_documents_valid(folder)
    assert not (folder / "results.csv").exists()
    record = stored(folder / "run-record.json")
    assert [entry["role"] for entry in record["inputs"]] == ["request", "change_manifest"]
    assert record["parameters"] == [] and clone_state() == state


def test_changes_over_a_revision_and_replay_without_the_clone(monkeypatch, tmp_path, capsys):
    in_force = in_force_id()
    base_folder, folder = tmp_path / "base", tmp_path / "run"
    before = clone_state()
    assert cli(monkeypatch, "run", model_request(monkeypatch, base_folder, in_force, NEW_BUSINESS,
                                                 run_id="run-base"), "--repositories", REPOSITORIES) == 0

    lapse, code, points = text(LAPSE_TABLE), text(MODEL_CODE), text(POINT_TABLE)
    assert "\n1,0.06," in lapse and "\nclaim_expense = 250.0\n" in code
    new_code = code.replace("\nclaim_expense = 250.0\n", "\nclaim_expense = 300.0\n\nextra_margin = 0.5\n")
    new_points = points.replace("\n2,RLV-000002,35,F,", "\n2,RLV-NEW-0002,35,F,")
    assert new_points != points
    folder.mkdir()
    # The path of a patch is relative to the root of the repository.
    entries = [
        change("chg-lapse-year-1", patch_text(LAPSE_TABLE, lapse, lapse.replace("\n1,0.06,", "\n1,0.05,")),
               folder, **{"class": "parameter"}),
        change("chg-claim-expense", patch_text(MODEL_CODE, code, new_code), folder, **{"class": "code"}),
        change("chg-rename-point", patch_text(POINT_TABLE, points, new_points), folder),
    ]
    manifest = {"document": "change_manifest", "contract_version": "3.1", "stage": "liability_cashflow",
                "manifest_id": "changes-synthetic", "base_release": "N", "changes": entries}
    (folder / "changes.json").write_bytes(document_bytes(manifest))
    assert not schema_errors(manifest, CHANGES_SCHEMA)
    assert cli(monkeypatch, "request", "--revision", START, "--repositories", REPOSITORIES,
               "--label", "N", "--run-id", "run-changes", "--output", folder / "request.json",
               "--subset", in_force, NEW_BUSINESS, "RLV-NEW-0002",
               "--enable", "chg-rename-point", "chg-claim-expense", "chg-lapse-year-1",
               "--manifest", folder / "changes.json") == 0
    assert cli(monkeypatch, "run", folder / "request.json", "--repositories", REPOSITORIES) == 0
    assert clone_state() == before  # the patches are applied to the restored state, never to the clone
    assert_documents_valid(folder)

    request, response, record = (stored(folder / name) for name in
                                 ("request.json", "response.json", "run-record.json"))
    assert roles(record["inputs"]) == {"request": "request.json", "change_manifest": "changes.json"}
    new = check_response(request, response, folder)
    old = check_export(stored(base_folder / "response.json"), base_folder / "results.csv")
    assert {key[0] for key in new} == {in_force, NEW_BUSINESS, "RLV-NEW-0002"}  # the id exists after the change
    assert new[(NEW_BUSINESS, 1)] != old[(NEW_BUSINESS, 1)]
    assert new[(NEW_BUSINESS, 0)][0] == old[(NEW_BUSINESS, 0)][0] == 1  # the opening in-force count
    parameters = {p["name"]: p for p in record["parameters"]}
    base_parameters = {p["name"]: p for p in stored(base_folder / "run-record.json")["parameters"]}
    assert parameters["claim_expense"]["value"] == 300.0 and base_parameters["claim_expense"]["value"] == 250.0
    assert parameters["extra_margin"]["value"] == 0.5 and "extra_margin" not in base_parameters
    assert parameters["lapse_table"]["rows"][0] == {"key": [1], "values": [0.05]}
    assert base_parameters["lapse_table"]["rows"][0] == {"key": [1], "values": [0.06]}
    assert parameters["mort_table"] == base_parameters["mort_table"]

    # The id that the change removes is unknown after the change.
    other = tmp_path / "other"
    other.mkdir()
    shutil.copytree(folder / "patches", other / "patches")
    shutil.copy(folder / "changes.json", other / "changes.json")
    assert cli(monkeypatch, "request", "--revision", START, "--repositories", REPOSITORIES,
               "--label", "N", "--run-id", "run-unknown", "--output", other / "request.json",
               "--subset", "RLV-000002", "--enable", "chg-rename-point",
               "--manifest", other / "changes.json") == 0
    assert cli(monkeypatch, "run", other / "request.json", "--repositories", REPOSITORIES) == 1
    assert stored(other / "response.json")["diagnostics"][0] == {
        "code": "unknown_model_point", "message": "The release holds no model point with this id.",
        "model_point_ids": ["RLV-000002"]}

    # A replay with the changes is reproduced. Without the clone a replay is rejected and
    # writes nothing.
    capsys.readouterr()
    assert cli(monkeypatch, "replay", folder / "run-record.json", "--repositories", REPOSITORIES) == 0
    assert "replay: reproduced_exactly" in capsys.readouterr().out
    assert cli(monkeypatch, "replay", base_folder / "run-record.json", "--repositories", tmp_path / "absent") == 1
    output = capsys.readouterr().out
    assert "replay: rejected" in output and "unknown_reference" in output
    assert not (base_folder / "replay").exists() and not (base_folder / "replay-record.json").exists()
    assert clone_state() == before


# --- regression against a newer revision --------------------------------------------


@pytest.fixture(scope="module")
def recorded_subset(tmp_path_factory) -> Path:
    """The folder of a recorded subset run of the start commit of the reference chain (release N on the
    fixed model): one in-force and one new-business point."""
    folder = tmp_path_factory.mktemp("recorded-n") / "run"
    assert main(["request", "--revision", START, "--repositories", str(REPOSITORIES), "--label", "N",
                 "--run-id", "run-n-subset", "--output", str(folder / "request.json"),
                 "--subset", in_force_id(), NEW_BUSINESS]) == 0
    assert main(["run", str(folder / "request.json"), "--repositories", str(REPOSITORIES)]) == 0
    return folder


def regress(monkeypatch, record_folder: Path, revision: str, repositories: Path, output: Path, *options) -> int:
    return cli(monkeypatch, "regression", record_folder / "run-record.json", "--revision", revision,
               "--repositories", repositories, "--output", output, *options)


def test_regression_command_without_a_clone_is_rejected_and_writes_nothing(
        monkeypatch, tmp_path, capsys, recorded_subset):
    before = folder_hashes(recorded_subset)
    (tmp_path / "empty" / CLONE_NAME).mkdir(parents=True)  # a folder that is no repository
    for repositories in (tmp_path / "absent", tmp_path / "empty"):
        capsys.readouterr()
        output = tmp_path / f"out-{repositories.name}"
        assert regress(monkeypatch, recorded_subset, START, repositories, output) == 1
        printed = capsys.readouterr()
        assert printed.out.startswith("regression: rejected\ndiagnostic: unknown_reference: ")
        assert f"git clone {REPOSITORY_URL} {repositories / CLONE_NAME}" in printed.out
        assert printed.err == "" and not output.exists()
    assert folder_hashes(recorded_subset) == before


def test_regression_against_a_commit_that_changes_no_model_file_shows_no_deviation(
        monkeypatch, tmp_path, capsys, recorded_subset):
    repositories, clone = throwaway(tmp_path)
    (clone / "README.md").write_bytes((clone / "README.md").read_bytes() + b"\nA note.\n")
    newer = commit(clone, "Add a note to the README")
    state, before = clone_state(clone), folder_hashes(recorded_subset)
    capsys.readouterr()
    out = tmp_path / "out"
    assert regress(monkeypatch, recorded_subset, "work", repositories, out, "--label", "N+1") == 0
    output = capsys.readouterr().out
    assert output.splitlines()[0] == "regression: no deviation above tolerance"
    # The newer commit is the state; the input data is that of the recorded run.
    request = stored(out / "run" / "request.json")
    assert request["release"]["label"] == "N+1" and request["run_id"] == "regression-run-n-subset"
    named = named_revisions(request)
    assert named["code_state"] == named["parameter_set"] == f"git:{REPOSITORY_URL}@{newer}"
    assert named["input_data"] == RELEASE_VALUE
    assert request["selection"] == stored(recorded_subset / "request.json")["selection"]
    compared = stored(out / "compare.result.json")
    assert compared["outcome"] == "compared" and compared["parameter_diff"] == []
    assert deviation_rows(out / "compare.result.json") == compared["added"] == compared["removed"] == []
    assert compared["compared_coordinates"] == 10 * stored(recorded_subset / "response.json")["export"]["data_rows"]
    assert stored(out / "signature-table.json")["rows"] == []
    assert folder_hashes(out / "recorded") == before
    assert clone_state(clone) == state and folder_hashes(recorded_subset) == before

    # The folder exists now: a second regression run starts nothing.
    kept = folder_hashes(out)
    assert regress(monkeypatch, recorded_subset, "work", repositories, out) == 2
    assert folder_hashes(out) == kept
    # Neither does one for a revision the clone does not hold.
    assert regress(monkeypatch, recorded_subset, "no-such-branch", repositories, tmp_path / "other") == 1
    printed = capsys.readouterr().out
    assert printed.startswith("regression: rejected\ndiagnostic: unknown_reference: ")
    assert "holds no commit named" in printed and not (tmp_path / "other").exists()


def test_regression_against_a_commit_that_changes_a_lapse_rate_names_stage_and_model_points(
        monkeypatch, tmp_path, capsys, recorded_subset):
    repositories, clone = throwaway(tmp_path)
    edit_file(clone, LAPSE_TABLE, "\n1,0.06,", "\n1,0.05,")
    commit(clone, "Lower the lapse rate of policy year 1")
    state, before = clone_state(clone), folder_hashes(recorded_subset)
    in_force = in_force_id()
    capsys.readouterr()
    out = tmp_path / "out"
    assert regress(monkeypatch, recorded_subset, "work", repositories, out) == 1
    output = capsys.readouterr().out
    assert clone_state(clone) == state and folder_hashes(recorded_subset) == before

    # The deviation list equals a recomputation from the two exports that does not use the core.
    compared = stored(out / "compare.result.json")
    assert not schema_errors(compared, COMPARE_SCHEMA) and compared["outcome"] == "compared"
    expected = expected_deviations(recorded_subset / "results.csv", out / "run" / "results.csv", {})
    assert deviation_rows(out / "compare.result.json") == expected and expected
    assert compared["added"] == compared["removed"] == []
    # No in-force point lies in policy year 1, so only the new business moves, from month 1 on.
    assert compared["deviating_model_points"] == [NEW_BUSINESS]
    assert min(d["period"] for d in expected) == 1
    assert compared["parameter_diff"] == [{"name": "lapse_table", "change": "changed", "type": "keyed_table",
                                           "rows": [{"key": [1], "change": "changed", "old": [0.06],
                                                     "new": [0.05]}]}]

    # The output names the stage and every deviating model point, and the table is written.
    assert "stage: liability_cashflow" in output
    assert f"deviation: liability_cashflow / model point {NEW_BUSINESS}: {len(expected)} coordinates" in output
    assert f"model point {in_force}" not in output and "no deviation" not in output
    table = stored(out / "signature-table.json")
    assert not schema_errors(table, COMPARE_SCHEMA)
    quantities = [q["name"] for q in compared["quantities"]]
    assert [row["quantity"] for row in table["rows"]] == [
        name for name in quantities if any(d["quantity"] == name for d in expected)]
    for row in table["rows"]:
        listed = [d for d in expected if d["quantity"] == row["quantity"]]
        assert row["stage"] == "liability_cashflow" and row["deviating_model_points"] == 1
        assert row["deviating_coordinates"] == len(listed)
        assert row["right_above_left"] == sum(d["right"] > d["left"] for d in listed)
        assert row["right_below_left"] == sum(d["right"] < d["left"] for d in listed)
        assert f"liability_cashflow / {row['quantity']}: 1 model points" in output
    # Fewer lapses in year 1 leave more contracts in force from month 1 on.
    counts = next(row for row in table["rows"] if row["quantity"] == "Anzahl Verträge")
    assert counts["right_above_left"] == counts["deviating_coordinates"] and counts["first_period"] == 1
    record = stored(out / "compare.run-record.json")
    assert roles(record["outputs"]) == {"result": "compare.result.json", "deviations": "compare.deviations.csv",
                                        "signature_table": "signature-table.json"}
    assert [r["label"] for r in record["releases"]] == ["N", "regression"]


def test_regression_uses_the_model_point_table_of_the_recorded_run(monkeypatch, tmp_path, capsys, recorded_subset):
    """The newer commit shortens a policy and changes a lapse rate; only the lapse rate is seen."""
    repositories, clone = throwaway(tmp_path)
    columns, line = point_line(NEW_BUSINESS)
    edit_file(clone, POINT_TABLE, line + "\n", with_columns(columns, line, policy_term="20", prem_term="20") + "\n")
    newer = commit(clone, "Shorten the term of the first policy")
    out = tmp_path / "out"
    assert regress(monkeypatch, recorded_subset, newer, repositories, out) == 0
    assert "regression: no deviation above tolerance" in capsys.readouterr().out
    recorded = stored(recorded_subset / "response.json")
    assert stored(out / "run" / "response.json")["model_points"] == recorded["model_points"]
    assert named_revisions(stored(out / "run" / "request.json"))["input_data"] == RELEASE_VALUE

    edit_file(clone, LAPSE_TABLE, "\n1,0.06,", "\n1,0.05,")
    both = commit(clone, "Lower the lapse rate of policy year 1")
    assert regress(monkeypatch, recorded_subset, both, repositories, tmp_path / "both") == 1
    compared = stored(tmp_path / "both" / "compare.result.json")
    assert deviation_rows(tmp_path / "both" / "compare.result.json")
    assert compared["added"] == compared["removed"] == []

    # A run of the newer commit with its own table has another period range for that policy,
    # and so has a run of the start commit that names the newer commit as its input data.
    from degelmann.deltarecon.engines import reference_model
    ranges = {p["model_point_id"]: p for p in recorded["model_points"]}
    for name, references in (("own", reference_model.release_references(newer)),
                             ("mixed", reference_model.release_references(START, newer))):
        folder = tmp_path / name
        path = model_request(monkeypatch, folder, NEW_BUSINESS, revision=newer, repositories=repositories)
        request = stored(path)
        request["release"]["references"] = references
        result = run_model(path, request, repositories)
        assert result.outcome == "succeeded"
        (point,) = result.response["model_points"]
        assert point["last_period"] < ranges[NEW_BUSINESS]["last_period"], name
    assert named_revisions(stored(tmp_path / "mixed" / "request.json")) == {
        "code_state": RELEASE_VALUE, "parameter_set": RELEASE_VALUE,
        "input_data": f"git:{REPOSITORY_URL}@{newer}", "engine_version": reference_model.engine_version()}

    # The input-data commit must hold the model point table.
    (clone / POINT_TABLE).unlink()
    without = commit(clone, "Remove the model point table")
    folder = tmp_path / "without"
    path = model_request(monkeypatch, folder, NEW_BUSINESS, repositories=repositories)
    request = stored(path)
    request["release"]["references"] = reference_model.release_references(START, without)
    assert f"The commit {without} lacks the release file {POINT_TABLE}" in assert_unknown_reference(
        run_model(path, request, repositories), folder)
    # The state commit may lack it: its table is not read.
    folder = tmp_path / "state-without"
    path = model_request(monkeypatch, folder, NEW_BUSINESS, repositories=repositories)
    request = stored(path)
    request["release"]["references"] = reference_model.release_references(without, START)
    assert run_model(path, request, repositories).outcome == "succeeded"


def test_regression_whose_run_is_rejected_compares_nothing(monkeypatch, tmp_path, capsys, recorded_subset):
    repositories, clone = throwaway(tmp_path)
    edit_file(clone, LAPSE_TABLE, "\n1,0.06,", "\n1,,")
    commit(clone, "Blank the lapse rate of policy year 1")
    capsys.readouterr()
    out = tmp_path / "out"
    assert regress(monkeypatch, recorded_subset, "work", repositories, out) == 1
    output = capsys.readouterr().out
    assert "regression: the run of the revision has the outcome rejected; nothing is compared" in output
    assert "diagnostic: non_finite_value:" in output and "no deviation" not in output
    # No comparison; the documents of the run stay.
    assert sorted(p.name for p in out.iterdir()) == ["recorded", "run"]
    assert sorted(p.name for p in (out / "run").iterdir()) == ["request.json", "response.json", "run-record.json"]
    assert_documents_valid(out / "run")
    assert stored(out / "run" / "response.json")["outcome"] == "rejected"


@pytest.mark.skipif(os.environ.get("DELTARECON_FULL") != "1",
                    reason="the changed case on all model points of release N runs on request: DELTARECON_FULL=1")
def test_full_changed_case_on_all_model_points_of_release_n(monkeypatch, tmp_path, capsys):
    """Release N in full against a commit that lowers the lapse rate of policy year 1."""
    repositories, clone = throwaway(tmp_path)
    recorded = tmp_path / "recorded"
    assert cli(monkeypatch, "run", model_request(monkeypatch, recorded, repositories=repositories,
                                                 run_id="run-n-full"), "--repositories", repositories) == 0
    edit_file(clone, LAPSE_TABLE, "\n1,0.06,", "\n1,0.05,")
    commit(clone, "Lower the lapse rate of policy year 1")
    state, before = clone_state(clone), folder_hashes(recorded)
    capsys.readouterr()
    out = tmp_path / "out"
    assert regress(monkeypatch, recorded, "work", repositories, out) == 1
    output = capsys.readouterr().out
    assert clone_state(clone) == state and folder_hashes(recorded) == before

    compared = stored(out / "compare.result.json")
    expected = expected_deviations(recorded / "results.csv", out / "run" / "results.csv", {})
    assert deviation_rows(out / "compare.result.json") == expected
    assert compared["added"] == compared["removed"] == []
    # The deviations lie in a CSV file referenced by hash; the result stays small, and the
    # table is the one that main wrote before the deviations left the result (story 9).
    assert compared["deviations"]["path"] == "compare.deviations.csv"
    assert (out / "compare.result.json").stat().st_size < 64 * 1024
    # Contract version 3.1: the 3.0 table 5ddfe219... with "contract_version": "3.1", byte for byte; that
    # table was the 2.0 table 7ba6c115... with "3.0", and that the table of 1.0 (4fc28fbd...) with "2.0".
    assert sha256_file(out / "signature-table.json") == \
        "b39e4206d7991f2652ab1f458a913d149fbceef43600d08575d8e19c422cfa6d"
    assert len(stored(recorded / "response.json")["model_points"]) == 350
    # Exactly the new business deviates: no in-force point lies in policy year 1.
    lines = text(POINT_TABLE).splitlines()
    columns = lines[0].split(",")
    new_business = sorted(line.split(",")[columns.index("policy_id")] for line in lines[1:]
                          if line.split(",")[columns.index("duration_y")] == "0")
    assert compared["deviating_model_points"] == new_business
    assert "stage: liability_cashflow" in output
    for model_point_id in new_business:
        assert f"deviation: liability_cashflow / model point {model_point_id}: " in output
    table = stored(out / "signature-table.json")
    assert not schema_errors(table, COMPARE_SCHEMA)
    assert sum(row["deviating_coordinates"] for row in table["rows"]) == len(expected)
    with capsys.disabled():  # the output that is noted before the pull request
        print()
        print("\n".join(line for line in output.splitlines() if not line.startswith("deviation: ")))
        print(f"compared coordinates: {compared['compared_coordinates']}, deviating model points: "
              f"{len(new_business)} of 350")


# --- the computation paths -----------------------------------------------------------


def test_the_engine_version_names_the_computation_path():
    from degelmann.deltarecon.engines.reference_model import DEFAULT_PATH, PATHS, engine_version, path_of
    assert PATHS == ("export", "modelx") and DEFAULT_PATH == "export"
    export, modelx = engine_version("export"), engine_version("modelx")
    assert engine_version() == export
    assert re.fullmatch(r"modelx \S+, pandas \S+, numpy \S+, Python \S+", modelx)
    assert export == modelx.replace(", pandas ", " export, pandas ", 1)
    assert (path_of(export), path_of(modelx)) == ("export", "modelx")
    # The rule for any recorded value: the first comma-separated part ends with " export" or not.
    for version, path in (("modelx 0.30.0, pandas 2.2.3, numpy 2.1.0, Python 3.12.7", "modelx"),
                          ("modelx 0.30.0 export, pandas 2.2.3, numpy 2.1.0, Python 3.12.7", "export"),
                          ("12.4.1", "modelx"), ("another engine export", "export"),
                          ("modelx 0.33.0, pandas 3.0.6 export, numpy 2.5.3", "modelx"),
                          ("engine, export", "modelx"), ("modelx export", "export"), ("", "modelx")):
        assert path_of(version) == path, version
    with pytest.raises(ValueError):
        engine_version("lifelib")


@pytest.mark.parametrize("path", [None, "export", "modelx"])
def test_request_command_names_the_engine_version_of_the_path(monkeypatch, tmp_path, path):
    from degelmann.deltarecon.engines.reference_model import engine_version
    request = stored(model_request(monkeypatch, tmp_path / "run", NEW_BUSINESS, path=path))
    assert named_revisions(request)["engine_version"] == engine_version(path or "export")


def test_request_command_refuses_an_unknown_path(monkeypatch, tmp_path, capsys):
    with pytest.raises(SystemExit) as caught:
        cli(monkeypatch, "request", "--revision", START, "--repositories", REPOSITORIES, "--label", "N",
            "--run-id", "x", "--output", tmp_path / "run" / "request.json", "--path", "lifelib")
    assert caught.value.code == 2 and "invalid choice: 'lifelib'" in capsys.readouterr().err
    assert not (tmp_path / "run").exists()


@contextmanager
def counted_exports(monkeypatch):
    """Count the calls of ``mx.export_model``; the export itself runs as it is."""
    from degelmann.deltarecon.engines import reference_model
    calls = []
    real = reference_model.mx.export_model

    def export_model(model, path, *arguments, **options):
        calls.append(Path(path))
        return real(model, path, *arguments, **options)

    with monkeypatch.context() as patch:
        patch.setattr(reference_model.mx, "export_model", export_model)
        yield calls


def exported_modules() -> list[str]:
    return [name for name in sys.modules if name.startswith("_deltarecon_export_")]


def without_engine_version(document: dict) -> dict:
    """A request or a response with the value of its engine version blanked."""
    copy = json.loads(json.dumps(document))
    for reference in copy["release"]["references"]:
        if reference["kind"] == "engine_version":
            reference["value"] = ""
    return copy


def test_both_paths_give_the_same_export_and_each_replays_on_its_own(monkeypatch, tmp_path, capsys):
    from degelmann.deltarecon.engines.reference_model import EXPORT_FOLDER, PATHS, engine_version
    documents = {}
    for path in PATHS:
        folder = tmp_path / path
        request_path = model_request(monkeypatch, folder, in_force_id(), NEW_BUSINESS, path=path)
        with counted_exports(monkeypatch) as calls:
            assert cli(monkeypatch, "run", request_path, "--repositories", REPOSITORIES) == 0
            # The export lies directly in the product folder of the scratch state of the run.
            assert [(call.name, call.parent.name, call.parent.parent.parent.name.startswith(SCRATCH_PREFIX))
                    for call in calls] == ([(EXPORT_FOLDER, PRODUCT_FOLDER, True)] if path == "export" else [])
            assert cli(monkeypatch, "replay", folder / "run-record.json", "--repositories", REPOSITORIES) == 0
            assert len(calls) == (2 if path == "export" else 0)  # the replay repeats the run on its path
        assert "replay: reproduced_exactly" in capsys.readouterr().out
        assert_documents_valid(folder)
        documents[path] = {name: stored(folder / name) for name in ("request.json", "response.json", "run-record.json")}
        assert named_revisions(documents[path]["response.json"])["engine_version"] == engine_version(path)
        assert named_revisions(stored(folder / "replay" / "response.json"))["engine_version"] == engine_version(path)
    assert exported_modules() == []  # the imported packages left sys.modules with their sessions
    assert (tmp_path / "export" / "results.csv").read_bytes() == (tmp_path / "modelx" / "results.csv").read_bytes()
    export, modelx = documents["export"], documents["modelx"]
    for name in ("request.json", "response.json"):
        assert export[name] != modelx[name]
        assert without_engine_version(export[name]) == without_engine_version(modelx[name]), name
    assert export["run-record.json"]["parameters"] == modelx["run-record.json"]["parameters"]
    assert ([without_engine_version({"release": r}) for r in export["run-record.json"]["releases"]]
            == [without_engine_version({"release": r}) for r in modelx["run-record.json"]["releases"]])


def test_a_request_written_before_the_paths_runs_on_modelx(monkeypatch, tmp_path):
    """The requests of the oracle before this story name the modelx string; they still run, on modelx."""
    from degelmann.deltarecon.engines.reference_model import engine_version, path_of
    request = stored(ROOT / "oracle" / "n.request.json")
    for reference in request["release"]["references"]:
        if reference["kind"] == "engine_version":  # the value as the request command wrote it before
            reference["value"] = engine_version("modelx")
    assert path_of(named_revisions(request)["engine_version"]) == "modelx"
    request["selection"] = {"mode": "subset", "model_point_ids": [NEW_BUSINESS, in_force_id()]}
    request["contract_version"] = "3.0"
    folder = tmp_path / "run"
    folder.mkdir()
    with counted_exports(monkeypatch) as calls:
        result = run_model(folder / "request.json", request)
    assert result.outcome == "succeeded" and calls == []
    assert result.response["release"] == request["release"]


@pytest.mark.parametrize("where", ["export", "import"])
def test_an_export_that_fails_ends_the_run_with_an_error_and_does_not_fall_back(monkeypatch, tmp_path, capsys, where):
    from degelmann.deltarecon.engines import reference_model
    real = reference_model.mx.export_model

    def export_model(model, path, *arguments, **options):
        if where == "export":
            raise RuntimeError("the model cannot be exported")
        real(model, path, *arguments, **options)
        (Path(path) / "__init__.py").write_text("raise ImportError('the package cannot be imported')\n")

    monkeypatch.setattr(reference_model.mx, "export_model", export_model)
    folder = tmp_path / "run"
    request_path = model_request(monkeypatch, folder, NEW_BUSINESS)
    assert cli(monkeypatch, "run", request_path, "--repositories", REPOSITORIES) == 1
    assert "outcome: error" in capsys.readouterr().out
    response = stored(folder / "response.json")
    message = ("RuntimeError: the model cannot be exported" if where == "export"
               else "ImportError: the package cannot be imported")
    assert response["outcome"] == "error"
    assert response["diagnostics"] == [{"code": "state_not_readable", "message": message}]
    assert not (folder / "results.csv").exists() and exported_modules() == []
    assert_documents_valid(folder)


def test_a_projection_that_raises_names_result_cf_on_a_full_run_and_projection_on_a_target_run():
    from degelmann.deltarecon.engines.reference_model import ReferenceModelSession

    class Projections:
        def __init__(self):
            self.released = []

        def __getitem__(self, index):
            raise ValueError("no such point")

        def __delitem__(self, index):
            self.released.append(index)
            raise KeyError(index)  # as modelx does for an item space that was never built

    class Model:
        Projection = Projections()

    session = ReferenceModelSession(Model())
    with pytest.raises(ModelPointFailure, match=r"^result_cf raised ValueError: no such point$"):
        session._project_index(7)
    with pytest.raises(ModelPointFailure, match=r"^Projection raised ValueError: no such point$"):
        session._project_target_index(7, ("Bruttobeitrag",), (0, 59))
    assert Model.Projection.released == [7, 7]  # released on both paths, also after the failure


def test_a_point_that_raises_under_the_export_is_a_failed_model_point(monkeypatch, tmp_path, capsys):
    from degelmann.deltarecon.engines.reference_model import PATHS
    repositories, clone = throwaway(tmp_path)
    lines = text(POINT_TABLE).splitlines()
    columns = lines[0].split(",")
    broken = lines[15].split(",")[columns.index("policy_id")]
    index = lines[15].split(",")[columns.index("point_id")]  # the model reads the table by point_id
    edit_file(clone, POINT_TABLE, lines[15] + "\n", with_columns(columns, lines[15], sex="X") + "\n")
    revision = commit(clone, "Give one model point an unknown sex")
    messages = {}
    for path in PATHS:
        folder = tmp_path / path
        request_path = model_request(monkeypatch, folder, NEW_BUSINESS, broken, revision=revision,
                                     repositories=repositories, path=path)
        assert cli(monkeypatch, "run", request_path, "--repositories", repositories) == 1
        assert "outcome: failed" in capsys.readouterr().out
        response = stored(folder / "response.json")
        assert response["outcome"] == "failed" and not (folder / "results.csv").exists()
        assert [f["model_point_id"] for f in response["failed_model_points"]] == [broken]
        messages[path] = response["failed_model_points"][0]["message"]
        assert_documents_valid(folder)
    assert messages == dict.fromkeys(
        PATHS, f"result_cf raised ValueError: invalid sex in RLV_DE_S.Projection[{index}].sex()")


def test_a_formula_of_t_and_a_check_that_raise_name_their_formula_alike_on_both_paths(monkeypatch, tmp_path,
                                                                                       capsys):
    from degelmann.deltarecon.engines.reference_model import PATHS
    repositories, clone = throwaway(tmp_path)
    lines = text(POINT_TABLE).splitlines()
    columns = lines[0].split(",")
    points = {line.split(",")[columns.index("policy_id")]: line.split(",")[columns.index("point_id")]
              for line in lines[1:3]}
    (lapse_id, lapse_index), (check_id, check_index) = points.items()
    edit_file(clone, MODEL_CODE, "    return lapse_rate_base(t) * shock_lapse_factor(t)\n",
              f"    if point_id == {lapse_index} and t == 3:  # noqa: F821\n"
              "        raise ValueError('no lapse rate\\nfor month 3')\n"
              "    return lapse_rate_base(t) * shock_lapse_factor(t)\n")
    edit_file(clone, MODEL_CODE,
              "    tol = val_tol * max(sum_assured(), 1.0)                          # noqa: F821\n"
              "    return all(abs(check_net_cf_resid(t))",
              f"    if point_id == {check_index}:  # noqa: F821\n"
              "        raise TypeError('no reconciliation')\n"
              "    tol = val_tol * max(sum_assured(), 1.0)                          # noqa: F821\n"
              "    return all(abs(check_net_cf_resid(t))")
    revision = commit(clone, "Raise in a formula of t and in a check")
    expected = {
        lapse_id: f"result_cf raised ValueError: no lapse rate in RLV_DE_S.Projection[{lapse_index}].lapse_rate(t=3)",
        check_id: f"check_net_cf raised TypeError: no reconciliation in RLV_DE_S.Projection[{check_index}].check_net_cf()",
    }
    for path in PATHS:
        folder = tmp_path / path
        request_path = model_request(monkeypatch, folder, lapse_id, check_id, revision=revision,
                                     repositories=repositories, path=path)
        assert cli(monkeypatch, "run", request_path, "--repositories", repositories) == 1
        assert "outcome: failed" in capsys.readouterr().out
        response = stored(folder / "response.json")
        assert {f["model_point_id"]: f["message"] for f in response["failed_model_points"]} == expected, path
        assert_documents_valid(folder)


def test_a_failure_under_the_export_names_the_innermost_exported_formula():
    """Stub spaces of a stub exported package: a library frame below a formula, a formula of another
    space, a cause of two lines, and a check that raises beside one that is false."""
    import pandas as pd
    from degelmann.deltarecon.engines.reference_model import ReferenceModelSession

    with pytest.raises(ValueError) as caught:
        pd.to_numeric(pd.Series(["x"]))
    library_cause = f"ValueError: {str(caught.value).splitlines()[0]}"

    class Data:
        _name = "Data"

        @staticmethod
        def model_point_table():
            return pd.DataFrame({"policy_id": ["MP-0", "MP-1", "MP-2"]})

        def _f_lapse_table(self):
            return {}["policy_year"]

    data = Data()

    class ItemSpace:
        _name = "Projection"

        def __init__(self, index):
            self.index = index

        def result_cf(self):
            return self._f_result_cf()

        def _f_result_cf(self):
            if self.index == 0:
                return self._f_premiums(0, "AFT_DECR")
            if self.index == 2:
                return self._f_sex()
            return pd.DataFrame()

        def _f_premiums(self, t, timing):
            return pd.to_numeric(pd.Series(["x"]))  # raises inside pandas

        def _f_sex(self):
            raise ValueError("invalid sex\nX is neither M nor F")

        def check_net_cf(self):
            return self._f_check_net_cf()

        def _f_check_net_cf(self):
            return data._f_lapse_table()

        def check_prem_split(self):
            return False

        def __getattr__(self, name):  # every other check holds
            return lambda: True

    class Projection:
        def __getitem__(self, index):
            return ItemSpace(index)

        def __delitem__(self, index):
            pass

    class Exported:
        pass

    class Model:
        Data = data

    exported = Exported()
    exported.Projection = Projection()
    session = ReferenceModelSession(Model(), exported)
    messages = {}
    for point in ("MP-0", "MP-1", "MP-2"):
        with pytest.raises(ModelPointFailure) as failure:
            session.project(point)
        messages[point] = str(failure.value)
    assert messages == {
        "MP-0": f"result_cf raised {library_cause} in RLV_DE_S.Projection[0].premiums(t=0, timing=AFT_DECR)",
        "MP-1": "check_net_cf raised KeyError: 'policy_year' in RLV_DE_S.Data.lapse_table(); check_prem_split is false",
        "MP-2": "result_cf raised ValueError: invalid sex in RLV_DE_S.Projection[2].sex()",
    }


def test_a_failure_without_a_formula_keeps_its_last_line():
    """A raise outside every exported formula, on the path export: the last line of the message."""
    import pandas as pd
    from degelmann.deltarecon.engines.reference_model import ReferenceModelSession

    class ItemSpace:
        _name = "Projection"

        def result_cf(self):
            raise ValueError("first line\nlast line")

        def check_net_cf(self):
            raise TypeError()

        def __getattr__(self, name):  # every other check holds
            return lambda: True

    class Projection:
        def __getitem__(self, index):
            return ItemSpace()

        def __delitem__(self, index):
            pass

    class Data:
        @staticmethod
        def model_point_table():
            return pd.DataFrame({"policy_id": ["MP-0"]})

    class Exported:
        pass

    class Model:
        pass

    model, exported = Model(), Exported()
    model.Data, exported.Projection = Data(), Projection()
    with pytest.raises(ModelPointFailure, match="^result_cf raised ValueError: last line$"):
        ReferenceModelSession(model, exported).project("MP-0")
    ItemSpace.result_cf = lambda self: None
    with pytest.raises(ModelPointFailure, match="^check_net_cf raised TypeError$"):
        ReferenceModelSession(model, exported).project("MP-0")


def test_a_state_takes_the_computation_path_of_the_older_record():
    from degelmann.deltarecon.engines.reference_model import ReferenceModel, engine_version, release_references
    other = "1" * 40
    for version, path in ((engine_version("export"), "export"), (engine_version("modelx"), "modelx"),
                          ("modelx 0.30.0, pandas 2.2.3, numpy 2.1.0, Python 3.12.7", "modelx"),
                          ("modelx 0.30.0 export, pandas 2.2.3, numpy 2.1.0, Python 3.12.7", "export")):
        base = {"label": "N", "references": release_references(START)[:3]
                + [{"kind": "engine_version", "value": version}]}
        for revision, hold in ((None, frozenset()), (other, frozenset()), (other, frozenset({"input_data"}))):
            state = ReferenceModel().state_release(base, revision, hold, REPOSITORIES)
            assert state["label"] == "N"
            assert named_revisions({"release": state})["engine_version"] == engine_version(path), version


def test_regression_runs_on_the_path_it_is_given(monkeypatch, tmp_path, capsys, recorded_subset):
    from degelmann.deltarecon.engines.reference_model import engine_version
    recorded = named_revisions(stored(recorded_subset / "request.json"))["engine_version"]
    assert recorded == engine_version("export")
    for options, path in (((), "export"), (("--path", "modelx"), "modelx")):
        out = tmp_path / path
        assert regress(monkeypatch, recorded_subset, START, REPOSITORIES, out, *options) == 0
        assert "regression: no deviation above tolerance" in capsys.readouterr().out
        assert named_revisions(stored(out / "run" / "request.json"))["engine_version"] == engine_version(path)
        compared = stored(out / "compare.result.json")
        assert compared.get("engine_version") == (
            None if path == "export" else {"left": engine_version("export"), "right": engine_version("modelx")})


# --- the full run of the start commit (release N on the fixed model) and its replay ---


def test_full_run_of_release_n_is_reproduced_by_its_replay(full_chain):
    steps, folder = full_chain["steps"], full_chain["folder"]
    assert [code for code, _, _ in steps] == [0, 0, 0], [s[2] for s in steps]
    assert "outcome: succeeded" in steps[1][1] and "model points: 350" in steps[1][1]
    assert "replay: reproduced_exactly" in steps[2][1]

    assert_documents_valid(folder)
    assert_documents_valid(folder / "replay")
    request, response, record = (stored(folder / name) for name in
                                 ("request.json", "response.json", "run-record.json"))
    values = check_response(request, response, folder)
    assert len(response["model_points"]) == 350 and len(values) == response["export"]["data_rows"]
    assert export_errors(folder / "results.csv") == []
    assert roles(record["inputs"]) == {"request": "request.json"}
    assert roles(record["outputs"]) == {"response": "response.json", "export": "results.csv"}
    assert len(record["parameters"]) > 20
    # The release is named by repository and commit, and the record holds the identity unchanged.
    assert [r["value"] for r in request["release"]["references"][:3]] == [RELEASE_VALUE] * 3
    assert record["releases"] == [request["release"]] == [response["release"]]

    replay_record = stored(folder / "replay-record.json")
    assert not schema_errors(replay_record, RECORD_SCHEMA)
    assert replay_record["procedure"] == {"type": "replay"}
    assert replay_record["outcome"] == "reproduced_exactly"
    assert replay_record["stage"] == record["stage"] == response["stage"] == "liability_cashflow"
    assert read_document(folder / "replay-record.json", RECORD_SCHEMA)["releases"] == record["releases"]
    for entry in replay_record["inputs"] + replay_record["outputs"]:
        assert sha256_file(folder / entry["artifact"]["path"]) == entry["artifact"]["sha256"]


def test_runs_through_the_contract_leave_the_clone_untouched(full_chain):
    """Status, ``HEAD``, and the references of the clone are as before the run and the replay."""
    assert full_chain["after"] == full_chain["before"]
    assert full_chain["before"][1].decode("ascii").strip() == git(CLONE, "rev-parse", "HEAD").decode().strip()


# --- the values a run keeps in memory ---------------------------------------------------


def test_the_values_in_memory_are_the_values_read_back_from_the_export(world):
    """A succeeded run hands on its values as ``check_export`` reads them back: ``-0.0`` as ``0.0``,
    a ``numpy.float64`` as a float, a subnormal and ``0.1`` unchanged, in writer order."""
    import numpy as np

    (world / "rel" / "points.csv").write_text(
        "id,first,last,base\nMP-D,2,3,3\nMP-A,0,1,-0.0\nMP-B,0,1,0.1\nMP-C,0,0,1e-310\n", "utf-8")

    class Float64Stub(StubEngine):
        @contextmanager
        def open(self, *arguments, **options):
            with super().open(*arguments, **options) as session:
                plain = session.project
                session.project = lambda point: [
                    (period, [np.float64(value) for value in values]) if point == "MP-D" else (period, values)
                    for period, values in plain(point)]
                yield session

    result, _ = run_stub(world, engine=Float64Stub())
    assert result.outcome == "succeeded"
    request = stored(world / "run" / "request.json")
    read_back = check_response(request, result.response, world / "run")
    assert result.values == read_back and list(result.values) == list(read_back)
    assert all(type(value) is float and str(value) != "-0.0" for numbers in result.values.values() for value in numbers)
    assert all(type(period) is int for _, period in result.values)
    assert result.values[("MP-A", 0)] == [0.0, 0.0] and result.values[("MP-C", 0)] == [1e-310, 1e-310]
    # With the values, rules 6 and 7 still apply and the export is not read.
    (world / "run" / "results.csv").unlink()
    assert check_response(request, result.response, world / "run", result.values) is result.values
    with pytest.raises(Rejection) as raised:
        check_response({**request, "run_id": "another"}, result.response, world / "run", result.values)
    assert raised.value.code == "request_mismatch"


def test_a_run_that_has_not_succeeded_holds_no_values(world):
    (world / "rel" / "points.csv").write_text("id,first,last,base\nMP-A,0,1,raise\n", "utf-8")
    result, _ = run_stub(world)
    assert result.outcome == "failed" and result.values is None


def test_the_reference_engine_exports_a_product_folder_once_per_engine_object(tmp_path, monkeypatch):
    """Same release twice: exported once, the same periods. Another product tree: exported again. A
    state with a text patch: exported, neither kept nor served from the kept packages."""
    import modelx as mx
    from degelmann.deltarecon.engines import reference_model
    from degelmann.deltarecon.engines.reference_model import ReferenceModel, release_references
    from conftest import NEWER

    require_clone()
    exports = []
    plain = mx.export_model

    def counting(model, path, *arguments, **options):
        exports.append(Path(path))
        return plain(model, path, *arguments, **options)

    monkeypatch.setattr(reference_model.mx, "export_model", counting)
    engine = ReferenceModel(workers=1)
    release = {"label": "N", "references": release_references(START)}
    points = [NEW_BUSINESS, in_force_id()]

    def projected(enabled=(), manifest_dir=None, use=release) -> list:
        with engine.open(use, list(enabled), manifest_dir, REPOSITORIES) as session:
            assert (session._state / PRODUCT_FOLDER / reference_model.EXPORT_FOLDER).is_dir()
            return [session.project(point) for point in points] if use is release else []

    first = projected()
    assert len(exports) == 1 and len(engine._exports) == 1
    kept = next(iter(engine._exports.values()))
    assert kept.is_dir() and not list(kept.rglob("__pycache__"))
    second = projected()
    assert len(exports) == 1 and second == first  # served from the kept package

    newer = {"label": "N+1", "references": release_references(NEWER)}
    projected(use=newer)
    assert len(exports) == 2 and len(engine._exports) == 2  # another product tree: exported again

    folder = tmp_path / "patched"
    folder.mkdir()
    code = text(MODEL_CODE)
    entry = change("chg-comment", patch_text(MODEL_CODE, code, code + "# a comment\n"), folder, **{"class": "code"})
    projected([entry], folder)
    assert len(exports) == 3 and len(engine._exports) == 2  # exported, not kept
    assert Path(engine._export_folder.name).name.startswith(SCRATCH_PREFIX)
    folder_name = engine._export_folder.name
    del engine
    import gc
    gc.collect()
    assert not Path(folder_name).exists()


# --- target-only runs ------------------------------------------------------------------

CASH_TARGET = {"quantities": ["Netto-Cashflow"], "periods": {"first": 1, "last": 1}}
ALL_FOUR = {"mode": "subset", "model_point_ids": ["MP-A", "MP-B", "MP-C", "MP-D"]}


def test_a_target_only_stub_run_computes_the_target_window_of_each_point(world):
    full, _ = run_stub(world, folder="full")
    request = stub_request(world, selection=ALL_FOUR, target=CASH_TARGET)
    result, _ = run_stub(world, request)
    assert result.outcome == "succeeded"
    folder = world / "run"
    assert_documents_valid(folder)
    response = stored(folder / "response.json")
    assert response["target"] == CASH_TARGET and list(response)[7:9] == ["selection", "target"]
    assert response["quantities"] == [{"name": "Netto-Cashflow", "unit": "EUR"}]
    # MP-C has projection period 0 alone: its window is empty, and it is absent although selected.
    assert response["model_points"] == [{"model_point_id": "MP-A", "first_period": 13, "last_period": 13},
                                        {"model_point_id": "MP-B", "first_period": 1, "last_period": 1},
                                        {"model_point_id": "MP-D", "first_period": 4, "last_period": 4}]
    assert response["export"]["data_rows"] == 3
    values = check_response(request, response, folder)
    whole = check_response(stub_request(world), full.response, world / "full")
    assert values == {key: [whole[key][1]] for key in [("MP-A", 13), ("MP-B", 1), ("MP-D", 4)]}
    assert (folder / "results.csv").read_text("utf-8") == (
        "model_point_id,period,Netto-Cashflow\nMP-A,13,21\nMP-B,1,4\nMP-D,4,5e16\n")


def test_a_target_only_run_without_a_target_period_succeeds_with_no_model_point(world):
    request = stub_request(world, target={"quantities": ["Anzahl Verträge"], "periods": {"first": 5, "last": 9}})
    result, _ = run_stub(world, request)
    assert result.outcome == "succeeded"
    assert_documents_valid(world / "run")
    response = stored(world / "run" / "response.json")
    assert response["model_points"] == [] and response["export"]["data_rows"] == 0
    assert (world / "run" / "results.csv").read_text("utf-8") == "model_point_id,period,Anzahl Verträge\n"
    assert check_response(request, response, world / "run") == {}
    assert roles(stored(world / "run" / "run-record.json")["outputs"]) == {"response": "response.json",
                                                                         "export": "results.csv"}
    # Without a target the schema keeps requiring a model point and a row.
    assert schema_errors({key: value for key, value in response.items() if key != "target"}, RUN_SCHEMA)


def test_a_target_only_run_evaluates_no_model_check(world):
    release = stub_release(world, "checked", POINTS.replace("MP-B,0,2,2", "MP-B,0,2,2!"))
    full, _ = run_stub(world, stub_request(world, release=release), folder="full")
    assert full.outcome == "failed"
    assert full.response["failed_model_points"] == [{"model_point_id": "MP-B", "message": "check_stub is false"}]
    result, _ = run_stub(world, stub_request(world, release=release, target={"quantities": ["Anzahl Verträge"]}))
    assert result.outcome == "succeeded"
    assert {p["model_point_id"]: (p["first_period"], p["last_period"]) for p in result.response["model_points"]}[
        "MP-B"] == (0, 2)


def test_the_regression_refuses_the_record_of_a_target_only_run_and_nothing_runs(world, monkeypatch, capsys):
    result, _ = run_stub(world, stub_request(world, selection=ALL_FOUR, target=CASH_TARGET))
    assert result.outcome == "succeeded"
    before = folder_hashes(world)
    engine = StubEngine()
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", lambda: engine)
    assert main(["regression", str(result.record_path), "--revision", "HEAD", "--output", str(world / "out"),
                 "--repositories", str(world)]) == 1
    out = capsys.readouterr().out
    assert out.splitlines()[0] == "regression: rejected" and "diagnostic: target_only_record: " in out
    assert engine.opened == 0 and folder_hashes(world) == before and not (world / "out").exists()


def test_the_replay_still_repeats_a_target_only_run(world):
    result, _ = run_stub(world, stub_request(world, selection=ALL_FOUR, target=CASH_TARGET))
    assert replay(result.record_path, StubEngine(), repositories=world).outcome == "reproduced_exactly"


class _NoTargetEngine(StubEngine):
    @contextmanager
    def open(self, release, enabled, manifest_dir, repositories, hold=frozenset()):
        with super().open(release, enabled, manifest_dir, repositories, hold) as session:
            session.project_target = None  # a session that cannot compute a target
            yield session


@pytest.mark.parametrize("target, engine, code", [
    ({"quantities": ["Bruttobeitrag"]}, None, "unknown_quantity"),
    ({"quantities": ["Netto-Cashflow"], "periods": {"first": 3, "last": 2}}, None, "schema_violation"),
    ({"quantities": ["Netto-Cashflow"]}, _NoTargetEngine(), "target_not_supported"),
], ids=["undeclared-quantity", "reversed-periods", "not-supported"])
def test_a_target_the_engine_cannot_run_is_rejected(world, target, engine, code):
    result, _ = run_stub(world, stub_request(world, target=target), engine)
    assert result.outcome == "rejected"
    assert [d["code"] for d in result.response["diagnostics"]] == [code]
    assert not (world / "run" / "results.csv").exists()
    assert_documents_valid(world / "run")


def test_a_target_only_response_repeats_the_target_and_holds_no_longer_window(world):
    request = stub_request(world, selection=ALL_FOUR, target=CASH_TARGET)
    result, _ = run_stub(world, request)
    response, folder = result.response, world / "run"
    for other in ({key: value for key, value in response.items() if key != "target"},
                  {**response, "target": {"quantities": ["Netto-Cashflow"]}}):
        with pytest.raises(Rejection) as caught:
            check_response(request, other, folder)
        assert caught.value.code == "request_mismatch"
    # A full response read as one of the target 1-1 holds ranges longer than the window.
    full, _ = run_stub(world, folder="full")
    with pytest.raises(Rejection) as caught:
        check_export({**full.response, "target": CASH_TARGET}, world / "full" / "results.csv")
    assert caught.value.code == "unrequested_coordinate" and caught.value.model_point_ids == ["MP-A", "MP-B", "MP-D"]
    assert check_export({**full.response, "target": {"quantities": ["Netto-Cashflow"]}},
                        world / "full" / "results.csv")


@pytest.mark.parametrize("workers", [1, 2])
def test_a_target_only_run_of_release_n_is_the_full_run_restricted_to_the_target(tmp_path, full_chain, workers):
    """Bit for bit, on the default computation path, in the parent and in worker processes."""
    from degelmann.deltarecon.engines.reference_model import ReferenceModel
    assert full_chain["steps"][1][0] == 0, full_chain["steps"][1][2]
    chain = full_chain["folder"]
    request, full = stored(chain / "request.json"), stored(chain / "response.json")
    target = {"quantities": ["Bruttobeitrag", "Netto-Cashflow"], "periods": {"first": 12, "last": 59}}
    folder = tmp_path / "target"
    folder.mkdir()
    targeted = {**request, "run_id": "run-n-target", "target": target}
    (folder / "request.json").write_bytes(document_bytes(targeted))
    run = run_request(folder / "request.json", ReferenceModel(workers), REPOSITORIES)
    assert run.outcome == "succeeded", run.response
    assert_documents_valid(folder)
    response = run.response
    assert response["target"] == target and [q["name"] for q in response["quantities"]] == target["quantities"]
    whole = check_response(request, full, chain)
    names = [q["name"] for q in full["quantities"]]
    keep = [names.index(name) for name in target["quantities"]]
    ranges, rows = [], []
    for point in full["model_points"]:
        start, end = point["first_period"], point["last_period"]
        first, last = start + 12, min(start + 59, end)
        if first <= last:
            ranges.append({"model_point_id": point["model_point_id"], "first_period": first, "last_period": last})
            rows.extend((point["model_point_id"], t, [whole[(point["model_point_id"], t)][i] for i in keep])
                        for t in range(first, last + 1))
    assert response["model_points"] == ranges
    assert (folder / "results.csv").read_bytes() == export_bytes(target["quantities"], rows)
    assert check_response(targeted, response, folder)
    # The in-force point is computed from its valuation month on: its window starts 12 months after it.
    in_force = in_force_id()
    start = next(p["first_period"] for p in full["model_points"] if p["model_point_id"] == in_force)
    assert start >= 144 and next(p for p in response["model_points"] if p["model_point_id"] == in_force)[
        "first_period"] == start + 12


def test_a_target_only_subset_run_on_the_modelx_path_is_the_full_run_restricted_to_the_target(
        monkeypatch, tmp_path):
    """Bit for bit, on the computation path ``modelx`` with the real engine: the target-only run of the
    quick start's target, Bruttobeitrag in projection periods 0 to 59, on a subset of a new and an in-force
    point."""
    from degelmann.deltarecon.engines.reference_model import engine_version, path_of
    from degelmann.deltarecon.run import run_request_document
    full_folder, target_folder = tmp_path / "full", tmp_path / "target"
    request_path = model_request(monkeypatch, full_folder, NEW_BUSINESS, in_force_id(), path="modelx")
    request = stored(request_path)
    assert path_of(named_revisions(request)["engine_version"]) == "modelx" == path_of(engine_version("modelx"))
    with counted_exports(monkeypatch) as calls:
        full = run_model(request_path)
        assert full.outcome == "succeeded", full.response
        target = {"quantities": ["Bruttobeitrag"], "periods": {"first": 0, "last": 59}}
        targeted = run_request_document(request["stage"], "run-n-subset-target", request["release"],
                                        request["changes"], request["selection"], "the target-only request",
                                        target=target)
        target_folder.mkdir()
        run = run_model(target_folder / "request.json", targeted)
    assert run.outcome == "succeeded", run.response
    assert calls == []  # the modelx path exports nothing
    assert_documents_valid(target_folder)
    assert run.response["target"] == target and [q["name"] for q in run.response["quantities"]] == ["Bruttobeitrag"]
    whole = check_response(request, full.response, full_folder)
    values = check_response(targeted, run.response, target_folder)
    index = [q["name"] for q in full.response["quantities"]].index("Bruttobeitrag")
    expected = {}
    for point in full.response["model_points"]:
        start = point["first_period"]
        for period in range(start, min(start + 59, point["last_period"]) + 1):
            expected[(point["model_point_id"], period)] = [whole[(point["model_point_id"], period)][index]]
    assert len({point for point, _ in expected}) == 2
    assert values == expected
    assert [value.hex() for (value,) in values.values()] == [value.hex() for (value,) in expected.values()]


def test_a_target_cell_that_returns_no_number_fails_its_point_alone():
    """A cell value that is not a number fails the point with one line naming the cell, as the full path does."""
    from degelmann.deltarecon.engines.reference_model import ReferenceModelSession

    class Point:
        def proj_start(self):
            return 0

        def proj_len(self):
            return 2

        def prem_gross(self, t):
            return None if t == 1 else 1.5

    class Computing:
        Projection: dict = {}

    computing = Computing()
    session = ReferenceModelSession(None, computing)
    computing.Projection = {0: Point()}
    session._index = lambda model_point_id: 0
    (failure,) = session.project_target(["P"], ["Bruttobeitrag"], None)
    assert isinstance(failure, ModelPointFailure)
    assert str(failure) == "prem_gross has not the expected form: TypeError"
    assert computing.Projection == {}  # the point's space is released
    computing.Projection = {0: Point()}
    assert session.project_target(["P"], ["Bruttobeitrag"], (0, 0)) == [[(0, [1.5])]]
