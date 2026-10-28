"""Stage contracts version 3: schemas, examples, hashes, number format and neutrality.

The tests check the published pack under ``contracts/v3``. They validate the examples
against the schemas and check the stored bytes. They do not implement a contract reader:
the semantic reader rules are normative text, shown by indexed examples. The packs of
versions 1.0 and 2.0 under ``contracts/v1`` and ``contracts/v2`` stay published; their
examples still validate under their own schemas, which the tool uses to read 1.0 and 2.0
documents.
"""
from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator

from degelmann.deltarecon.documents import load_schemas, strict_json_text, validator
from degelmann.deltarecon.export import (INTEGER, READER_INTEGER, export_errors, export_rows,
                               is_profile_number, is_readable_number)

from conftest import EXACT, EXAMPLES, artifacts, deviates, rounded

ROOT = Path(__file__).resolve().parent.parent
PACK = ROOT / "contracts" / "v3"
# The published packs of the earlier versions the tool reads, by version.
EARLIER_PACKS = {"1.0": ROOT / "contracts" / "v1", "2.0": ROOT / "contracts" / "v2"}
SCHEMAS = PACK / "schemas"
TEXT_FILES = ["README.md", "run.md", "changes.md", "compare.md", "localise.md", "domain/liability_cashflow.md"]

# The rows of the behaviour matrix in contracts/v3/README.md.
MATRIX_ROWS = {
    "complete-run", "malformed-input", "opaque-release-identity", "inconsistent-result",
    "model-point-failure", "incompatible-compare", "coverage-difference",
    "tolerance-boundary", "parameter-diff", "change-combination", "signature-table",
    "derived-manifest", "engine-error", "non-finite-difference", "deviation-file", "walk", "search",
}
# Rows whose behaviour is a rejection, and the outcome an example of the row must have.
EXPECTED_BY_ROW = {
    "malformed-input": "reject", "inconsistent-result": "reject",
    "change-combination": "reject", "model-point-failure": "failed",
    "incompatible-compare": "incompatible", "engine-error": "error",
    "non-finite-difference": "reject", "deviation-file": "reject",
}
# Levels of a rejected case whose named file is itself malformed.
FILE_LEVELS = {"schema", "parse", "export_format"}

ENGINE_NAMES = re.compile(r"modelx|python|pandas", re.IGNORECASE)


def cases() -> list[dict]:
    return json.loads((EXAMPLES / "index.json").read_text("utf-8"))["cases"]


def case_ids() -> list[str]:
    return [case["id"] for case in cases()]


def case(case_id: str) -> dict:
    return next(c for c in cases() if c["id"] == case_id)


def strict_json(path: Path):
    """Parse a file under the JSON profile, which also fixes UTF-8."""
    return strict_json_text(path.read_bytes().decode("utf-8"))


def artifact_states(example: dict) -> list[tuple[str, str]]:
    """(path, state) for every artifact of a case; state is ok, missing or mismatch."""
    states = []
    for document in example["documents"]:
        path = EXAMPLES / document["path"]
        for reference in artifacts(json.loads(path.read_text("utf-8"))):
            target = path.parent / reference["path"]
            if not target.is_file():
                state = "missing"
            elif hashlib.sha256(target.read_bytes()).hexdigest() != reference["sha256"]:
                state = "mismatch"
            else:
                state = "ok"
            states.append((f"{document['path']} -> {reference['path']}", state))
    return states


def anchors(text: str) -> set[str]:
    """Anchors of the headings of a Markdown text, as common renderers derive them."""
    result = set()
    for heading in re.findall(r"^#+ (.+)$", text, re.MULTILINE):
        slug = re.sub(r"[^a-z0-9 _-]", "", heading.lower()).replace(" ", "-")
        result.add(slug)
    return result


# --- JSON profile -------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    '{"a": NaN}', '{"a": Infinity}', '{"a": -Infinity}', '{"a": 1e999}', '{"a": -1e999}',
    '{"a": 1' + "0" * 400 + "}", '{"a": 1, "a": 2}'])
def test_json_profile_rejects(text):
    with pytest.raises(ValueError):
        strict_json_text(text)


@pytest.mark.parametrize("text", ['{"a": 1e308}', '{"a": 9007199254740993}', '{"a": -0.0}'])
def test_json_profile_accepts(text):
    strict_json_text(text)


# --- schemas ------------------------------------------------------------------------


@pytest.mark.parametrize("name", sorted(load_schemas()))
def test_schema_is_a_valid_2020_12_schema(name):
    schema = load_schemas()[name]
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    assert schema["$id"] == name
    Draft202012Validator.check_schema(schema)


def test_schema_folder_holds_exactly_the_six_schemas():
    assert len(load_schemas()) == 6
    assert sorted(p.name for p in SCHEMAS.iterdir()) == sorted(load_schemas())


def test_schema_references_resolve_locally():
    schemas = load_schemas()

    def refs(node):
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "$ref":
                    yield value
                else:
                    yield from refs(value)
        elif isinstance(node, list):
            for value in node:
                yield from refs(value)

    for name, schema in schemas.items():
        for ref in refs(schema):
            file_name, _, pointer = ref.partition("#")
            target = schemas[file_name] if file_name else schema  # KeyError: not a local file
            for part in pointer.strip("/").split("/"):
                target = target[part]
            assert isinstance(target, dict), f"{name}: {ref}"


def test_schema_objects_are_closed():
    """Every object shape forbids unknown members, except the extensible realisation.

    A map from name to a closed shape, such as per_quantity, counts as closed.
    """
    open_shapes = []

    def walk(node, where):
        if isinstance(node, dict):
            if node.get("type") == "object" and not (
                    node.get("additionalProperties") is False
                    or "$ref" in (node.get("additionalProperties") or {})):
                open_shapes.append(where)
            for key, value in node.items():
                walk(value, f"{where}/{key}")
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{where}/{index}")

    for name, schema in load_schemas().items():
        walk(schema, name)
    assert open_shapes == ["changes.schema.json/$defs/realisation"]


# --- change manifests: authored and derived -----------------------------------------


def authored_manifest() -> dict:
    return json.loads((EXAMPLES / "reference" / "changes.json").read_text("utf-8"))


def derived_manifest() -> dict:
    return json.loads((EXAMPLES / "reference" / "changes.derived.json").read_text("utf-8"))


def first_change(manifest: dict, **members) -> dict:
    manifest["changes"][0].update(members)
    return manifest


def realised(manifest: dict, index: int = 0, **members) -> dict:
    realisation = manifest["changes"][index]["realisation"]
    for name, value in members.items():
        if value is None:
            del realisation[name]
        else:
            realisation[name] = value
    return manifest


def with_history(manifest: dict, **members) -> dict:
    for name, value in members.items():
        if value is None:
            del manifest["history"][name]
        else:
            manifest["history"][name] = value
    return manifest


REVISION = {"type": "revision", "source": "git", "revision": "0123456789abcdef0123456789abcdef01234567"}
REFERENCE = {"kind": "engine_version", "value": "engine build 2026.09"}

MANIFEST_SHAPES = {
    # An authored manifest: one class or a list of distinct classes, never the empty list.
    "authored": (lambda: authored_manifest(), True),
    "authored-class-list": (lambda: first_change(authored_manifest(), **{"class": ["parameter", "code"]}), True),
    "authored-class-list-of-one": (lambda: first_change(authored_manifest(), **{"class": ["code"]}), True),
    "authored-class-twice": (lambda: first_change(authored_manifest(), **{"class": ["code", "code"]}), False),
    "authored-unknown-class": (lambda: first_change(authored_manifest(), **{"class": ["code", "model"]}), False),
    "authored-empty-class": (lambda: first_change(authored_manifest(), **{"class": []}), False),
    "authored-without-a-change": (lambda: {**authored_manifest(), "changes": []}, False),
    # A revision stands only in a derived manifest, so a set of revisions that is no prefix
    # breaks rule 8; another type stays open.
    "authored-revision": (lambda: realised(first_change(authored_manifest(), realisation=dict(REVISION))), False),
    "authored-type-named-like-revision": (
        lambda: realised(first_change(authored_manifest(), realisation={"type": "revisions", "x": 1})), True),
    # The type ``revision`` is closed.
    "revision-with-a-further-member": (lambda: realised(derived_manifest(), note="x"), False),
    "revision-without-source": (lambda: realised(derived_manifest(), source=None), False),
    "revision-without-revision": (lambda: realised(derived_manifest(), revision=None), False),
    "revision-of-another-source": (lambda: realised(derived_manifest(), source="tape"), False),
    "engine-declared-type": (
        lambda: first_change(authored_manifest(), realisation={"type": "engine_switch", "switch": "RC-1"}), True),
    # A derived manifest.
    "derived": (lambda: derived_manifest(), True),
    "derived-without-a-change": (lambda: {**derived_manifest(), "changes": []}, True),
    "derived-without-a-remainder": (lambda: with_history(derived_manifest(), remainder=[]), True),
    "derived-class-as-one-value": (lambda: first_change(derived_manifest(), **{"class": "parameter"}), False),
    "derived-class-twice": (lambda: first_change(derived_manifest(), **{"class": ["code", "code"]}), False),
    "derived-with-a-conflict": (
        lambda: first_change(derived_manifest(), conflicts=[derived_manifest()["changes"][1]["id"]]), False),
    "derived-with-two-prerequisites": (
        lambda: first_change(derived_manifest(), prerequisites=[c["id"] for c in derived_manifest()["changes"][1:3]]),
        False),
    "derived-with-a-text-patch": (
        lambda: first_change(derived_manifest(), realisation=authored_manifest()["changes"][0]["realisation"]),
        False),
    "derived-with-an-engine-declared-type": (
        lambda: first_change(derived_manifest(), realisation={"type": "engine_switch", "switch": "RC-1"}), False),
    "history-without-determines": (lambda: with_history(derived_manifest(), determines=None), False),
    "history-without-remainder": (lambda: with_history(derived_manifest(), remainder=None), False),
    "history-without-from": (lambda: with_history(derived_manifest(), **{"from": None}), False),
    "history-with-a-further-member": (lambda: with_history(derived_manifest(), derived_at="2026-10-13"), False),
    "history-of-another-source": (lambda: with_history(derived_manifest(), source="tape"), False),
    "history-determines-a-kind-twice": (
        lambda: with_history(derived_manifest(), determines=["code_state", "code_state"]), False),
    "history-determines-nothing": (lambda: with_history(derived_manifest(), determines=[]), True),
    "remainder-with-an-empty-side": (
        lambda: with_history(derived_manifest(), remainder=[{"kind": "engine_version", "from": [], "to": [REFERENCE]}]),
        True),
    "remainder-with-an-artifact": (
        lambda: with_history(derived_manifest(), remainder=[{"kind": "tables", "from": [], "to": [
            {"kind": "tables", "value": "t", "artifact": {"path": "t.csv", "sha256": "0" * 64}}]}]), True),
    "remainder-without-a-side": (
        lambda: with_history(derived_manifest(), remainder=[{"kind": "engine_version", "from": [REFERENCE]}]), False),
    "remainder-of-values-alone": (
        lambda: with_history(derived_manifest(), remainder=[{"kind": "engine_version", "from": ["a"], "to": ["b"]}]),
        False),
    "remainder-with-a-further-member": (
        lambda: with_history(derived_manifest(), remainder=[{"kind": "engine_version", "from": [], "to": [REFERENCE],
                                                             "note": "x"}]), False),
}


@pytest.mark.parametrize("name", sorted(MANIFEST_SHAPES))
def test_change_manifest_schema(name):
    build, valid = MANIFEST_SHAPES[name]
    errors = list(validator("changes.schema.json").iter_errors(build()))
    assert (not errors) == valid, errors[:1]


def test_derived_example_follows_the_rules_and_orders_of_a_derived_manifest():
    manifest = derived_manifest()
    history, changes = manifest["history"], manifest["changes"]
    ids = [change["id"] for change in changes]
    assert len(ids) == len(set(ids)) >= 3 and history["from"] not in ids and history["to"] == ids[-1]
    assert manifest["manifest_id"] == f"history-{history['from']}-{history['to']}"
    assert manifest["base_release"] == authored_manifest()["base_release"]
    # One chain: each change names the change before it, the first none.
    assert [change["prerequisites"] for change in changes] == [[]] + [[previous] for previous in ids[:-1]]
    assert all(change["conflicts"] == [] for change in changes)
    assert [change["realisation"] for change in changes] == [
        {"type": "revision", "source": history["source"], "revision": change_id} for change_id in ids]
    order = ["data", "parameter", "code"]
    classes = [change["class"] for change in changes]
    assert all(listed == [name for name in order if name in listed] for listed in classes)
    assert any(len(listed) == 2 for listed in classes) and [] in classes
    assert all(change["description"] == change["description"].rstrip("\r\n") for change in changes)
    assert any("\n" in change["description"] for change in changes)
    # The stated orders of the history member.
    assert history["determines"] == sorted(history["determines"])
    kinds = [entry["kind"] for entry in history["remainder"]]
    assert kinds == sorted(kinds) and kinds and not set(kinds) & set(history["determines"])
    for entry in history["remainder"]:
        assert entry["from"] != entry["to"]
        for side in (entry["from"], entry["to"]):
            assert all(reference["kind"] == entry["kind"] for reference in side)
            assert [r["value"] for r in side] == sorted(r["value"] for r in side)


def test_changes_contract_states_the_revision_profile_and_the_derived_manifest():
    text = (PACK / "changes.md").read_text("utf-8")
    assert {"revision-profile", "derived-manifest", "text-patch-reference-profile"} <= anchors(text)
    # The text-patch profile keeps one class per change; a revision is never split.
    assert "One change has one class" in text and "A revision is never split" in text
    assert "Version 1 defines one type" not in text and "Only the type `text_patch` has a closed shape" not in text
    assert "`unrelated_revisions`" in text and "byte for byte" in text
    readme = (PACK / "README.md").read_text("utf-8")
    assert "| `unrelated_revisions` |" in readme and "A reader accepts exactly the versions it implements" in readme


# --- the localise contract ----------------------------------------------------------


@pytest.mark.parametrize("changes, valid", [
    ({"enabled": ["a"], "manifest": {"path": "changes.json", "sha256": "0" * 64}, "hold": ["input_data"]}, True),
    ({"enabled": [], "hold": ["input_data"]}, True),  # the engine rejects it with invalid_hold
    ({"enabled": ["a"], "manifest": {"path": "changes.json", "sha256": "0" * 64}, "hold": []}, False),
    ({"enabled": ["a"], "manifest": {"path": "changes.json", "sha256": "0" * 64}, "hold": ["x", "x"]}, False),
    ({"enabled": ["a"], "manifest": {"path": "changes.json", "sha256": "0" * 64}, "hold": ["Input data"]}, False),
])
def test_a_request_may_name_held_kinds(changes, valid):
    request = json.loads((EXAMPLES / "reference" / "full-run.request.json").read_text("utf-8"))
    request["changes"] = changes
    assert (not list(validator("run.schema.json").iter_errors(request))) == valid


@pytest.mark.parametrize("target, valid", [
    ({"quantities": ["Bruttobeitrag"], "periods": {"first": 0, "last": 59}}, True),
    ({"quantities": ["Bruttobeitrag"]}, True),
    ({"quantities": []}, False),
    ({"quantities": ["Bruttobeitrag", "Bruttobeitrag"]}, False),
    ({"quantities": ["Bruttobeitrag"], "periods": {"first": -1, "last": 59}}, False),
    ({"quantities": ["Bruttobeitrag"], "periods": {"first": 0}}, False),
    ({"quantities": ["Bruttobeitrag"], "offset": 0}, False),
])
def test_a_request_may_name_a_target(target, valid):
    request = json.loads((EXAMPLES / "reference" / "full-run.request.json").read_text("utf-8"))
    request["target"] = target
    assert (not list(validator("run.schema.json").iter_errors(request))) == valid


def test_a_response_without_a_model_point_is_valid_under_a_target_only():
    response = json.loads((EXAMPLES / "reference" / "full-run.response.json").read_text("utf-8"))
    empty = {**response, "model_points": [], "export": {**response["export"], "data_rows": 0}}
    assert list(validator("run.schema.json").iter_errors(empty))
    assert not list(validator("run.schema.json").iter_errors({**empty, "target": {"quantities": ["Bruttobeitrag"]}}))
    for switches, valid in ((["reuse_walk", "target_only"], True), (["target_only"], True), (["walk_only"], False)):
        record = json.loads((EXAMPLES / "reference" / "full-run.run-record.json").read_text("utf-8"))
        assert (not list(validator("run-record.schema.json").iter_errors({**record, "switches": switches}))) == valid


def walk_example() -> dict:
    return json.loads((EXAMPLES / "walk" / "walk.result.json").read_text("utf-8"))


def test_the_walk_example_derives_the_manifest_of_the_reference_and_its_sums_add_up():
    from fractions import Fraction
    folder = EXAMPLES / "walk"
    result = walk_example()
    assert (folder / "changes.json").read_bytes() == (EXAMPLES / "reference" / "changes.derived.json").read_bytes()
    ids = [change["id"] for change in derived_manifest()["changes"]]
    assert [state["state"] for state in result["states"]] == list(range(len(ids) + 1))
    assert [state.get("revision") for state in result["states"]] == [None] + ids
    assert [step["revisions"] for step in result["steps"]] == [[i] for i in ids]
    assert result["remainder"] == derived_manifest()["history"]["remainder"]
    assert result["ends"]["zero"]["outcome"] == result["ends"]["n"]["outcome"] == "reproduced"
    names = [total["quantity"] for total in result["totals"]]

    def values(path: str) -> dict:
        rows = export_rows(folder / path)
        return {(row[0], int(row[1]), name): Fraction(float(value))
                for row in rows[1:] for name, value in zip(rows[0][2:], row[2:])}

    exports = [values(state["export"]["path"]) for state in result["states"]]
    for step in result["steps"]:
        left, right = exports[step["from_state"]], exports[step["to_state"]]
        assert [c["quantity"] for c in step["contributions"]] == names
        for contribution in step["contributions"]:
            name = contribution["quantity"]
            exact = sum((right.get(key, 0) - left.get(key, 0) for key in set(left) | set(right) if key[2] == name),
                        Fraction(0))
            assert contribution["sum"] == float(exact)
            assert ("compare" in step) == any(c["contributes"] for c in step["contributions"])
    for total in result["totals"]:
        name = total["quantity"]
        exact = sum((exports[-1].get(key, 0) - exports[0].get(key, 0)
                     for key in set(exports[0]) | set(exports[-1]) if key[2] == name), Fraction(0))
        assert total["sum"] == float(exact)
    # The walk result references no run record and holds no timestamp.
    text = (folder / "walk.result.json").read_text("utf-8")
    assert "run-record" not in text and "recorded_at" not in text


@pytest.mark.parametrize("edit", ["export-of-a-failed-state", "compare-of-a-reproduced-end", "empty-step",
                                  "revision-of-state-zero", "state-without-revision",
                                  "contributing-step-without-compare", "compare-of-a-step-without-contribution",
                                  "unknown-finding", "unknown-member"])
def test_the_walk_result_schema_states_its_assertions(edit):
    result = walk_example()
    if edit == "export-of-a-failed-state":
        result["states"][2]["outcome"] = "failed"
    elif edit == "compare-of-a-reproduced-end":
        result["ends"]["zero"]["compare"] = result["steps"][0]["compare"]
    elif edit == "empty-step":
        result["steps"][0]["revisions"] = []
    elif edit == "revision-of-state-zero":
        result["states"][0]["revision"] = result["states"][1]["revision"]
    elif edit == "state-without-revision":
        del result["states"][1]["revision"]
    elif edit == "contributing-step-without-compare":
        del next(step for step in result["steps"] if "compare" in step)["compare"]
    elif edit == "compare-of-a-step-without-contribution":
        quiet = next(step for step in result["steps"] if "compare" not in step)
        quiet["compare"] = result["steps"][0]["compare"]
    elif edit == "unknown-finding":
        result["findings"] = [{"code": "something_else", "message": "x"}]
    else:
        result["searched"] = True
    assert list(validator("localise.schema.json").iter_errors(result))


def search_example() -> dict:
    return json.loads((EXAMPLES / "search" / "search.result.json").read_text("utf-8"))


def test_the_search_example_is_checked_against_the_walk_example_and_its_sums_are_exact():
    from fractions import Fraction
    folder = EXAMPLES / "search"
    result = search_example()
    # The copied walk is the walk example, byte for byte, and so is the manifest derived again.
    for path in (EXAMPLES / "walk").rglob("*"):
        if path.is_file():
            relative = path.relative_to(EXAMPLES / "walk")
            assert (folder / "walk" / relative).read_bytes() == path.read_bytes(), relative
    assert (folder / "changes.json").read_bytes() == (EXAMPLES / "walk" / "changes.json").read_bytes()
    walk = walk_example()
    assert result["walk"]["walk_id"] == walk["walk_id"]
    ids = [change["id"] for change in derived_manifest()["changes"]]
    assert result["runs"] == {"walk": len(walk["states"]), "search": len(result["states"]),
                              "saved": len(walk["states"]) - len(result["states"])}
    assert result["runs"]["saved"] > 0
    assert [state["state"] for state in result["states"]] == sorted(state["state"] for state in result["states"])
    # Pre-order, the earlier half first: every interval after the first is a half of an earlier one.
    intervals = [(i["from_state"], i["to_state"]) for i in result["intervals"]]
    assert intervals[0] == (0, len(ids))
    for interval in result["intervals"]:
        assert interval["revisions"] == ids[interval["from_state"]:interval["to_state"]]
    target = result["target"]
    first, last = target["periods"]["first"], target["periods"]["last"]

    def values(path: str) -> dict:
        rows = export_rows(folder / path)
        return {(row[0], int(row[1]), name): Fraction(float(value))
                for row in rows[1:] for name, value in zip(rows[0][2:], row[2:])
                if name in target["quantities"] and first <= int(row[1]) <= last}

    exports = {state["state"]: values(state["export"]["path"]) for state in result["states"]}
    for entry in result["contributions"]:
        left, right = exports[entry["from_state"]], exports[entry["to_state"]]
        for contribution in entry["contributions"]:
            name = contribution["quantity"]
            exact = sum((right.get(key, 0) - left.get(key, 0) for key in set(left) | set(right) if key[2] == name),
                        Fraction(0))
            assert contribution["sum"] == float(exact) and "signature" not in contribution
    # Every revision whose walk step changes the target is found: nothing is missed.
    assert result["missed"] == []
    text = (folder / "search.result.json").read_text("utf-8")
    assert "run-record" not in text and "recorded_at" not in text


@pytest.mark.parametrize("edit", ["unknown-member", "walk-without-missed", "missed-without-walk",
                                  "contribution-without-compare", "contribution-that-contributes-nothing",
                                  "empty-target", "walk-finding-code", "negative-saved"])
def test_the_search_result_schema_states_its_assertions(edit):
    result = search_example()
    contribution = result["contributions"][0]
    if edit == "unknown-member":
        result["walked"] = True
    elif edit == "walk-without-missed":
        del result["missed"]
    elif edit == "missed-without-walk":
        del result["walk"]
    elif edit == "contribution-without-compare":
        del contribution["compare"]
    elif edit == "contribution-that-contributes-nothing":
        for entry in contribution["contributions"]:
            entry["contributes"] = False
    elif edit == "empty-target":
        result["target"]["quantities"] = []
    elif edit == "walk-finding-code":
        result["findings"] = [{"code": "something_else", "message": "x"}]
    else:
        result["runs"]["saved"] = -1
    assert list(validator("localise.schema.json").iter_errors(result))
    # A walk result may not carry the finding of a search.
    walk = walk_example()
    walk["findings"] = [{"code": "interval_not_resolved", "message": "x"}]
    assert list(validator("localise.schema.json").iter_errors(walk))


def test_localise_contract_is_no_stage_contract_and_names_its_findings():
    text = (PACK / "localise.md").read_text("utf-8")
    assert "It is no stage contract. No engine implements it" in text
    for code in ("state_zero_not_reproduced", "state_n_not_reproduced", "state_did_not_run", "step_not_compared",
                 "non_finite_difference", "selection_mismatch", "reference_mismatch", "interval_not_resolved",
                 "walk_not_attributed", "walk_mismatch", "target_only_record"):
        assert f"`{code}`" in text, code
    assert "does not see contributions that cancel within one\ninterval" in text  # known limit 6
    readme = (PACK / "README.md").read_text("utf-8")
    for code in ("invalid_hold", "selection_mismatch", "reference_mismatch", "walk_not_attributed", "walk_mismatch",
                 "target_only_record"):
        assert f"| `{code}` |" in readme, code
    assert "sums of\ndifferences" not in (PACK / "compare.md").read_text("utf-8")
    assert "localise.md#contribution" in (PACK / "compare.md").read_text("utf-8")


# --- index --------------------------------------------------------------------------


def test_index_names_every_case_once_and_completely():
    index = json.loads((EXAMPLES / "index.json").read_text("utf-8"))
    assert index["contract_version"] == "3.0"
    assert len(case_ids()) == len(set(case_ids()))
    for example in cases():
        assert example["expected"] in {"accept", "reject", "failed", "error", "incompatible"}, example["id"]
        assert example["shows"] and example["rules"] and example["matrix_rows"], example["id"]
        assert example["documents"] or example["exports"], example["id"]
        if example["expected"] == "reject":
            assert example["level"] in FILE_LEVELS | {"semantic"}, example["id"]
            assert ("failing" in example) == (example["level"] in FILE_LEVELS), example["id"]
        else:
            assert "level" not in example and "failing" not in example, example["id"]
        if example["expected"] != "accept":
            assert re.fullmatch(r"[a-z][a-z0-9_]*", example["diagnostic"]), example["id"]
            assert f"`{example['diagnostic']}`" in (PACK / "README.md").read_text("utf-8")
        for path in [d["path"] for d in example["documents"]] + example["exports"]:
            assert path.startswith("negative/" + example["id"] + "/") == (
                example["expected"] != "accept"), path


def test_index_covers_every_matrix_row():
    readme = (PACK / "README.md").read_text("utf-8")
    covered: dict[str, set[str]] = {}
    for example in cases():
        assert set(example["matrix_rows"]) <= MATRIX_ROWS, example["id"]
        for row in example["matrix_rows"]:
            covered.setdefault(row, set()).add(example["expected"])
    assert set(covered) == MATRIX_ROWS
    for row in MATRIX_ROWS:
        assert f"| `{row}` |" in readme, row
        assert EXPECTED_BY_ROW.get(row, "accept") in covered[row], row


def test_index_lists_every_example_folder_and_file():
    listed = {path for example in cases()
              for path in [d["path"] for d in example["documents"]] + example["exports"]}
    for path in listed:
        assert (EXAMPLES / path).is_file(), path
    negative = {p.name for p in (EXAMPLES / "negative").iterdir()}
    assert negative == {c["id"] for c in cases() if c["expected"] != "accept"}
    # Every JSON and CSV file belongs to a case, except the release inputs that
    # artifact references point to.
    for path in EXAMPLES.rglob("*"):
        relative = path.relative_to(EXAMPLES).as_posix()
        if (path.is_file() and path.suffix in {".json", ".csv"} and relative != "index.json"
                and "/release/" not in relative):
            assert relative in listed, relative


def test_index_rules_point_to_existing_sections():
    sections = {name: anchors((PACK / name).read_text("utf-8")) for name in TEXT_FILES}
    for example in cases():
        for rule in example["rules"]:
            name, _, anchor = rule.partition("#")
            assert anchor in sections[name], f"{example['id']}: {rule}"


def test_readme_capability_map_names_existing_cases_and_sections():
    readme = (PACK / "README.md").read_text("utf-8")
    table = readme.split("## Capability map")[1].split("## Examples")[0]
    rows = [line for line in table.splitlines() if line.startswith("| ") and "---" not in line][1:]
    assert [row.split("|")[1].strip() for row in rows] == [
        "Stage identity", "Subset runs", "Per-model-point export", "Parameter diff", "Signature table",
        "Derived manifest", "Walk", "Search"]
    assert f"{['Zero', 'One', 'Two', 'Three', 'Four', 'Five', 'Six', 'Seven', 'Eight'][len(rows)]} capabilities must be" in readme
    sections = {name: anchors((PACK / name).read_text("utf-8")) for name in TEXT_FILES}
    for row in rows:
        _, _, specified, examples, _ = row.split("|")
        links = re.findall(r"\]\(([^)#]*)#([^)]+)\)", specified)
        assert links, row
        for name, anchor in links:
            assert anchor in sections[name or "README.md"], f"{name}#{anchor}"
        named = re.findall(r"`([^`]+)`", examples)
        assert named and set(named) <= set(case_ids()), row


# --- examples against the schemas ---------------------------------------------------


@pytest.mark.parametrize("case_id", case_ids())
def test_example_documents_match_their_expected_outcome(case_id):
    example = case(case_id)
    level, failing = example.get("level"), example.get("failing")
    for document in example["documents"]:
        path = EXAMPLES / document["path"]
        if level == "parse" and document["path"] == failing:
            with pytest.raises(ValueError):
                strict_json(path)
            continue
        errors = list(validator(document["schema"]).iter_errors(strict_json(path)))
        if level == "schema" and document["path"] == failing:
            assert errors, f"{document['path']} must violate {document['schema']}"
        else:
            assert not errors, f"{document['path']}: {errors[0].message}"
    if level in {"schema", "parse"}:
        assert failing in [d["path"] for d in example["documents"]]


@pytest.mark.parametrize("version,case_id", [(version, c["id"]) for version, pack in EARLIER_PACKS.items()
                                             for c in json.loads((pack / "examples" / "index.json")
                                                                 .read_text("utf-8"))["cases"]])
def test_the_earlier_examples_still_match_their_outcome_under_their_own_schemas(version, case_id):
    """The 1.0 and 2.0 packs stay as published: their documents validate, or fail, under the
    schemas of their own version, the schemas the tool reads a 1.0 or 2.0 document with."""
    pack = EARLIER_PACKS[version]
    examples = pack / "examples"
    example = next(c for c in json.loads((examples / "index.json").read_text("utf-8"))["cases"]
                   if c["id"] == case_id)
    assert load_schemas(version) == {path.name: json.loads(path.read_text("utf-8"))
                                     for path in (pack / "schemas").iterdir()}
    level, failing = example.get("level"), example.get("failing")
    for document in example["documents"]:
        path = examples / document["path"]
        if level == "parse" and document["path"] == failing:
            continue
        value = strict_json(path)
        errors = list(validator(document["schema"], version).iter_errors(value))
        if level == "schema" and document["path"] == failing:
            assert errors, document["path"]
        else:
            assert not errors, f"{document['path']}: {errors[0].message}"
            assert value.get("contract_version", version) == version


def test_each_version_has_its_own_schemas():
    """A document of 1.0, 2.0, or 3.0 passes the schemas of its own version and fails those of
    the two others; a document of 3.1 passes the schemas of 3.0, which are its own."""
    versions = ("1.0", "2.0", "3.0")
    for version in versions:
        pack = ROOT / "contracts" / f"v{version[0]}"
        request = strict_json(pack / "examples" / "reference" / "full-run.request.json")
        assert request["contract_version"] == version
        assert not list(validator("run.schema.json", version).iter_errors(request))
        for other in versions:
            if other != version:
                assert list(validator("run.schema.json", other).iter_errors(request)), (version, other)
    # Version 3.1 is a minor version of the pack of 3.0: its schemas read both, the earlier packs neither.
    request = {**strict_json(ROOT / "contracts" / "v3" / "examples" / "reference" / "full-run.request.json"),
               "contract_version": "3.1"}
    assert not list(validator("run.schema.json", "3.1").iter_errors(request))
    assert not list(validator("run.schema.json", "3.0").iter_errors(request))
    for other in ("1.0", "2.0"):
        assert list(validator("run.schema.json", other).iter_errors(request)), other


def test_schema_level_cases_exist():
    levels = [c.get("level") for c in cases()]
    assert levels.count("schema") >= 3 and levels.count("parse") >= 1
    assert levels.count("export_format") >= 1 and levels.count("semantic") >= 5


# A case that fails to parse names no artifact whose bytes could be checked.
@pytest.mark.parametrize("case_id", [c["id"] for c in cases() if c.get("level") != "parse"])
def test_artifact_hashes_match_the_stored_bytes(case_id):
    example = case(case_id)
    states = artifact_states(example)
    wrong = {"artifact_missing": "missing", "artifact_hash_mismatch": "mismatch"}.get(
        example.get("diagnostic"))
    if wrong:
        assert [state for _, state in states].count(wrong) == 1, states
        states = [s for s in states if s[1] != wrong]
    assert all(state == "ok" for _, state in states), states


def test_examples_reference_at_least_one_artifact_of_each_kind():
    reference = [name for name, _ in artifact_states(case("compare-result"))
                 + artifact_states(case("change-manifest"))]
    assert any(name.endswith(".patch") for name in reference)
    assert any(name.endswith(".results.csv") for name in reference)
    assert any("release/" in name for name in reference)
    assert artifact_states(case("opaque-identity"))  # the record and the export still hash


# --- exports ------------------------------------------------------------------------


@pytest.mark.parametrize("text", [
    "0", "1", "-380", "0.995", "26.0228", "1e-7", "0.0000001", "1.5e300", "120000", "-0.5"])
def test_number_format_accepts(text):
    assert is_profile_number(text)


@pytest.mark.parametrize("text", [
    "", "NaN", "nan", "inf", "-Infinity", "+1", "01", "1.", ".5", "1.0", "0.50", "1,5",
    "1 000", "1e+7", "1E7", "1e07", "0.10000000000000001", "1e999", "0x10", "-0", "0e5", "-0e5"])
def test_number_format_rejects(text):
    assert not is_profile_number(text)


@pytest.mark.parametrize("text", [
    "0", "-0", "007", "1.50", "1.0", "0.50", "1e+7", "1E7", "1e07", "1E-07", "0e5",
    "0.10000000000000001", "-380", "0.995", "1e-7", "1.5e300"])
def test_reader_grammar_accepts(text):
    assert is_readable_number(text)


@pytest.mark.parametrize("text", [
    "", "NaN", "nan", "inf", "-Infinity", "+1", "1,5", "1 000", "1.000,5", "1'000", "0x10",
    "1.", ".5", "1e", "1e999", "-1e999", " 1", "1e1.5"])
def test_reader_grammar_rejects(text):
    assert not is_readable_number(text)


@pytest.mark.parametrize("text", [
    "0", "1", "-380", "0.995", "26.0228", "1e-7", "0.0000001", "1.5e300", "120000", "-0.5"])
def test_writer_form_is_readable(text):
    assert is_profile_number(text) and is_readable_number(text)


def test_reader_grammar_for_periods():
    assert all(READER_INTEGER.fullmatch(t) for t in ("0", "-0", "007", "-3", "144"))
    assert not any(READER_INTEGER.fullmatch(t) for t in ("", "+1", "1.0", "1e2", "0x10"))


@pytest.mark.parametrize("text, valid", [
    ("0", True), ("144", True), ("-3", True), ("-0", False), ("01", False), ("1.0", False)])
def test_period_format(text, valid):
    assert bool(INTEGER.fullmatch(text)) == valid


def test_parameter_inventories_are_ordered_by_name():
    records = [EXAMPLES / d["path"] for c in cases() for d in c["documents"]
               if d["schema"] == "run-record.schema.json"]
    assert len(set(records)) >= 4
    for path in set(records):
        names = [p["name"] for p in json.loads(path.read_text("utf-8"))["parameters"]]
        assert names == sorted(names) and len(names) == len(set(names)), path


@pytest.mark.parametrize("case_id", [c["id"] for c in cases() if c["exports"]])
def test_export_numbers_follow_the_csv_profile(case_id):
    example = case(case_id)
    for export in example["exports"]:
        if example.get("level") == "export_format" and export == example["failing"]:
            # A rejection must hold for a reader, so the tolerant grammar decides.
            errors = export_errors(EXAMPLES / export, is_readable_number, READER_INTEGER)
            assert errors, f"{export} must be unreadable under the reader grammar"
        else:
            errors = export_errors(EXAMPLES / export)  # the pack's own exports: writer form
            assert not errors, f"{export}: {errors}"


@pytest.mark.parametrize("case_id", [c["id"] for c in cases() if c["expected"] == "accept"])
def test_accepted_exports_agree_with_their_responses(case_id):
    """The valid bundles are internally consistent; this is a check of the examples only."""
    for document in case(case_id)["documents"]:
        response = json.loads((EXAMPLES / document["path"]).read_text("utf-8"))
        if response.get("document") != "run_response":
            continue
        path = (EXAMPLES / document["path"]).parent / response["export"]["artifact"]["path"]
        rows = export_rows(path)
        assert rows[0] == ["model_point_id", "period"] + [q["name"] for q in response["quantities"]]
        expected = [(point["model_point_id"], str(period)) for point in response["model_points"]
                    for period in range(point["first_period"], point["last_period"] + 1)]
        assert [(row[0], row[1]) for row in rows[1:]] == expected
        assert response["export"]["data_rows"] == len(expected)


def test_domain_reference_declares_the_eleven_quantities_in_export_order():
    text = (PACK / "domain" / "liability_cashflow.md").read_text("utf-8")
    declared = re.findall(r"^\| \d+ \| `([^`]+)` \| `([A-Za-z]+)` \|", text, re.MULTILINE)
    response = json.loads((EXAMPLES / "reference" / "full-run.response.json").read_text("utf-8"))
    assert len(declared) == 11
    # The reference full run exports every quantity but the calculatory costs.
    exported = [d for d in declared if d[0] != "kalkulatorische Kosten"]
    assert exported == [(q["name"], q["unit"]) for q in response["quantities"]]
    assert f"`{response['time_basis']['id']}`" in text


def domain_quantities() -> list[str]:
    text = (PACK / "domain" / "liability_cashflow.md").read_text("utf-8")
    return re.findall(r"^\| \d+ \| `([^`]+)` \|", text, re.MULTILINE)


def test_every_response_declares_domain_quantities_in_domain_order():
    """A run may export a subset; the opaque-identity example shows a proper one."""
    domain = domain_quantities()
    sizes = {}
    for example in cases():
        if example["expected"] != "accept":
            continue
        for document in example["documents"]:
            response = json.loads((EXAMPLES / document["path"]).read_text("utf-8"))
            if response.get("document") != "run_response":
                continue
            names = [q["name"] for q in response["quantities"]]
            assert names and set(names) <= set(domain), document["path"]
            assert names == [n for n in domain if n in names], document["path"]
            sizes[document["path"]] = len(names)
    assert sizes["opaque-identity/response.json"] < len(domain)
    # The reference model does not export the calculatory costs yet.
    assert sizes["reference/full-run.response.json"] == len(domain) - 1


def test_domain_reference_declares_selection_independence():
    text = (PACK / "domain" / "liability_cashflow.md").read_text("utf-8")
    assert "selection-independence" in anchors(text)
    assert "is declared by the domain reference of the stage" in (PACK / "run.md").read_text("utf-8")


# --- tolerance ----------------------------------------------------------------------


def test_reference_comparison_uses_a_derived_profile_per_quantity():
    request = json.loads((EXAMPLES / "reference" / "compare.request.json").read_text("utf-8"))
    result = json.loads((EXAMPLES / "reference" / "compare.result.json").read_text("utf-8"))
    profile = request["tolerance"]["per_quantity"]
    assert set(request["tolerance"]) == {"per_quantity"}
    assert result["tolerance"] == request["tolerance"]
    assert set(profile) <= {q["name"] for q in result["quantities"]}
    assert all(entry["derivation"] for entry in profile.values())
    # Upper and lower bounds are set separately, and at least one entry is asymmetric.
    assert any(entry["upper"] != entry["lower"] for entry in profile.values())
    # A quantity without an entry is compared exactly and shows up as a deviation.
    assert "Anzahl Verträge" not in profile
    assert "Anzahl Verträge" in {d["quantity"] for d in deviation_file(folder_of("reference"), result)}


def folder_of(name: str) -> Path:
    return EXAMPLES / name


def deviation_file(folder: Path, result: dict) -> list[dict]:
    """The rows of the deviation file a compare result of the pack references, read as text."""
    rows = export_rows(folder / result["deviations"]["path"])
    assert rows[0] == ["model_point_id", "period", "quantity", "left", "right"]
    return [{"model_point_id": row[0], "period": int(row[1]), "quantity": row[2], "left": float(row[3]),
             "right": float(row[4])} for row in rows[1:]]


def test_reference_deviation_list_follows_the_tolerance_rule():
    """Recompute the deviation list of the reference example from its two exports."""
    folder = EXAMPLES / "reference"
    request = json.loads((folder / "compare.request.json").read_text("utf-8"))
    result = json.loads((folder / "compare.result.json").read_text("utf-8"))
    profile = request["tolerance"]["per_quantity"]

    def coordinates(name):
        rows = export_rows(folder / name)
        return {(row[0], int(row[1]), quantity): float(value)
                for row in rows[1:] for quantity, value in zip(rows[0][2:], row[2:])}

    left, right = coordinates("full-run.results.csv"), coordinates("subset-run.results.csv")
    common = sorted(set(left) & set(right))
    expected = [key for key in common
                if deviates(left[key], right[key], profile.get(key[2], {"upper": EXACT, "lower": EXACT}))]
    deviations = deviation_file(folder, result)
    listed = [(d["model_point_id"], d["period"], d["quantity"]) for d in deviations]
    assert sorted(listed) == expected
    assert result["compared_coordinates"] == len(common)
    for d in deviations:
        key = (d["model_point_id"], d["period"], d["quantity"])
        assert (d["left"], d["right"]) == (left[key], right[key])
    # The two boundary cases of the example lie exactly on their bounds.
    cost = ("MP-0001", 0, "Kosten 2. Ordnung ohne Provisionen")
    assert right[cost] - left[cost] == profile[cost[2]]["upper"]["abs_tol"] and cost not in expected
    # Exchanging the sides exchanges the bounds: the same pair then deviates.
    assert deviates(right[cost], left[cost], profile[cost[2]])
    # Rounding to the defined places removes a difference beyond the cent.
    commission = ("MP-0002", 145, "Provisionen")
    assert left[commission] != right[commission] and commission not in expected
    assert profile["Provisionen"]["decimals"] == 2


@pytest.mark.parametrize("value, decimals, expected", [
    (0.125, 2, 0.13), (-0.125, 2, -0.13), (2.675, 2, 2.68), (0.6972, 2, 0.7), (0.6949, 2, 0.69),
    (0.6951, 2, 0.7), (1234.5, 0, 1235.0), (0.1 + 0.2, 15, 0.3)])
def test_rounding_is_commercial_on_the_written_decimal(value, decimals, expected):
    assert rounded(value, decimals) == expected


@pytest.mark.parametrize("per_quantity, valid", [
    ({}, True),
    ({"Anzahl Verträge": {"upper": EXACT, "lower": EXACT}}, True),
    ({"Anzahl Verträge": {"upper": {"abs_tol": 0.1, "rel_tol": 0}, "lower": EXACT, "derivation": "x"}}, True),
    ({"Anzahl Verträge": {"upper": {"abs_tol": 0.1, "rel_tol": 0}, "lower": EXACT}}, False),
    ({"Anzahl Verträge": {"upper": EXACT, "lower": {"abs_tol": 0, "rel_tol": 1e-9}}}, False),
    ({"Anzahl Verträge": {"upper": {"abs_tol": 0.1, "rel_tol": 0}, "lower": EXACT, "derivation": ""}}, False),
    ({"Anzahl Verträge": {"decimals": 2, "upper": EXACT, "lower": EXACT, "derivation": "x"}}, True),
    ({"Anzahl Verträge": {"decimals": 2, "upper": EXACT, "lower": EXACT}}, False),
    ({"Anzahl Verträge": {"decimals": -1, "upper": EXACT, "lower": EXACT, "derivation": "x"}}, False),
    ({"Anzahl Verträge": {"decimals": 2.5, "upper": EXACT, "lower": EXACT, "derivation": "x"}}, False),
    ({"Anzahl Verträge": {"upper": EXACT}}, False),
    ({"Anzahl Verträge": {"upper": {"abs_tol": 0.1}, "lower": EXACT, "derivation": "x"}}, False),
    ({"Anzahl Verträge": {"upper": {"abs_tol": -0.1, "rel_tol": 0}, "lower": EXACT, "derivation": "x"}}, False),
    ({"Anzahl Verträge": {"upper": EXACT, "lower": EXACT, "extra": 1}}, False),
    ({"Anzahl Verträge": {"abs_tol": 0.1, "rel_tol": 0}}, False),
    ({"": {"upper": EXACT, "lower": EXACT}}, False),
])
def test_tolerance_profile_schema(per_quantity, valid):
    request = json.loads((EXAMPLES / "reference" / "compare.request.json").read_text("utf-8"))
    request["tolerance"] = {"per_quantity": per_quantity}
    errors = list(validator("compare.schema.json").iter_errors(request))
    assert (not errors) == valid, errors[:1]


@pytest.mark.parametrize("tolerance", [
    {}, {"abs_tol": 0, "rel_tol": 0}, {"abs_tol": 0.5, "rel_tol": 0.001, "per_quantity": {}}])
def test_there_is_no_general_tolerance(tolerance):
    request = json.loads((EXAMPLES / "reference" / "compare.request.json").read_text("utf-8"))
    request["tolerance"] = tolerance
    assert list(validator("compare.schema.json").iter_errors(request))

# --- neutrality ---------------------------------------------------------------------


def test_contract_pack_names_no_engine_or_language():
    files = [p for p in (ROOT / "contracts").rglob("*") if p.is_file()]
    assert len(files) > 50
    for path in files:
        name = path.relative_to(ROOT).as_posix()
        assert not ENGINE_NAMES.search(name), name
        match = ENGINE_NAMES.search(path.read_bytes().decode("utf-8"))
        assert not match, f"{name}: {match.group(0)}"
