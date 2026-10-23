"""The derived change manifest: ``degelmann/deltarecon/derive.py`` and the history reader of the adapter.

The core is tested on the stub engine of ``conftest.py``, whose history is a list
that a test sets. The history reader of the reference engine is tested on throw-away
repositories that are built on the fly and hold no model: reading a history needs none.
One chain of two subset runs on a throw-away clone of the reference model checks the
command from the records to the manifest, in two processes.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from degelmann.deltarecon import changes as changes_contract
from degelmann.deltarecon.__main__ import main
from degelmann.deltarecon.derive import build_manifest, derive, remainder
from degelmann.deltarecon.documents import CHANGES_SCHEMA, Rejection, document_bytes, read_document, schema_errors, sha256_file
from degelmann.deltarecon.replay import replay
from degelmann.deltarecon.run import STAGE_QUANTITIES, History, Revision, UsageError

from conftest import (CLONE_NAME, LAPSE_TABLE, NEW_BUSINESS, PARAMS, POINTS, POINTS_B, PRODUCT_FOLDER, RELEASE_N,
                      REPOSITORIES, REPOSITORY_URL, ROOT, StubEngine, branch, change, cli, clone_state, commit,
                      commit_message, edit_file, empty_repository, folder_hashes, git, git_environment, merge,
                      patch_text, run_stub, stored, stub_request, throwaway, with_manifest, write_files)

# --- the core on the stub engine ----------------------------------------------------

LINE = (
    ("r0", "The base.\n", ()),
    ("r1", "Lower the lapse rate\n\nIt was 0.06 and is 0.05.\n\n", ("parameter",)),
    ("r2", "", ("code", "data")),
    ("r3", "Touch nothing that has a class\r\n", ()),
)


class HistoryStub(StubEngine):
    """The stub engine with a history. It reads identities that hold further kinds."""

    line = LINE

    def _folder(self, release, repositories):
        kept = [r for r in release["references"] if r["kind"] in ("release_folder", "input_data")]
        return super()._folder({**release, "references": kept}, repositories)


def record(world: Path, name: str, folder: str | None = None, further=(), label: str | None = None,
           engine=None, **members) -> Path:
    """Run the stub release ``name`` and return the path of its run record."""
    release = world / name
    if not release.exists():
        release.mkdir()
        (release / "points.csv").write_text(POINTS, "utf-8")
        (release / "params.csv").write_text(PARAMS, "utf-8")
    identity = {"label": label or name, "references": StubEngine.references(release, name) + list(further)}
    folder = folder or f"run-{name}"
    request = stub_request(world, run_id=folder, release=identity, **members)
    result, _ = run_stub(world, request, engine or HistoryStub(), folder=folder)
    assert result.outcome == "succeeded"
    return result.record_path


def enabling(manifest: dict, ids: list[str]) -> dict:
    return {"stage": manifest["stage"], "release": {"label": manifest["base_release"]},
            "changes": {"enabled": ids}}


def test_linear_history_gives_one_chained_change_per_revision(world):
    older, newer = record(world, "r0", label="N"), record(world, "r3", label="N+3")
    before = folder_hashes(world)
    result = derive(older, newer, world / "changes.json", HistoryStub(), repositories=world)
    manifest = read_document(world / "changes.json", CHANGES_SCHEMA)
    assert manifest == result.manifest and result.manifest_path == world / "changes.json"
    assert list(manifest) == ["document", "contract_version", "stage", "manifest_id", "base_release",
                              "history", "changes"]
    assert (manifest["document"], manifest["contract_version"], manifest["stage"]) == (
        "change_manifest", "2.0", "liability_cashflow")
    assert manifest["manifest_id"] == "history-r0-r3" and manifest["base_release"] == "N"
    assert manifest["history"] == {"source": "git", "from": "r0", "to": "r3",
                                   "determines": ["input_data", "release_folder"], "remainder": []}
    changes = manifest["changes"]
    assert [c["id"] for c in changes] == ["r1", "r2", "r3"]
    assert [c["prerequisites"] for c in changes] == [[], ["r1"], ["r2"]]
    assert all(c["conflicts"] == [] for c in changes)
    assert [c["realisation"] for c in changes] == [
        {"type": "revision", "source": "git", "revision": name} for name in ("r1", "r2", "r3")]
    # A class list in the stated order, and the empty list for a revision without a class.
    assert [c["class"] for c in changes] == [["parameter"], ["data", "code"], []]
    # The whole message without the line breaks at its end; the identifier for an empty one.
    assert [c["description"] for c in changes] == [
        "Lower the lapse rate\n\nIt was 0.06 and is 0.05.", "r2", "Touch nothing that has a class"]
    # Nothing but the manifest is written, and it holds no path of the machine.
    assert {**before, "changes.json": sha256_file(world / "changes.json")} == folder_hashes(world)
    assert str(world) not in (world / "changes.json").read_text("utf-8")


def test_a_derived_manifest_keeps_the_manifest_rules_and_a_prefix_satisfies_rule_8(world):
    older, newer = record(world, "r0", label="N"), record(world, "r3")
    manifest = derive(older, newer, world / "changes.json", HistoryStub(), repositories=world).manifest
    changes_contract.check_manifest_rules(manifest)  # rules 1 to 5
    ids = [c["id"] for c in manifest["changes"]]
    for length in range(len(ids) + 1):
        selected = changes_contract.check_combination(manifest, enabling(manifest, ids[:length][::-1]),
                                                      frozenset({"revision"}))
        assert [c["id"] for c in selected] == ids[:length]
    for other in (["r2"], ["r3"], ["r1", "r3"], ["r2", "r3"]):
        with pytest.raises(Rejection) as caught:
            changes_contract.check_combination(manifest, enabling(manifest, other), frozenset({"revision"}))
        assert caught.value.code == "unmet_prerequisite"
    # An engine that does not declare the type cannot realise a prefix either.
    with pytest.raises(Rejection) as caught:
        changes_contract.check_combination(manifest, enabling(manifest, ["r1"]), frozenset({"text_patch"}))
    assert caught.value.code == "unsupported_realisation" and caught.value.change_ids == ["r1"]


@pytest.mark.parametrize("breach", ["no-prerequisites", "skipped-prerequisite", "first-with-prerequisite",
                                    "other-revision", "other-source", "last-not-newer", "empty-of-two"])
def test_a_derived_manifest_whose_changes_break_the_chain_is_invalid(world, breach):
    older, newer = record(world, "r0", label="N"), record(world, "r3")
    manifest = derive(older, newer, world / "changes.json", HistoryStub(), repositories=world).manifest
    changes = manifest["changes"]
    if breach == "no-prerequisites":  # every change alone, so any one could be enabled
        for change in changes:
            change["prerequisites"] = []
    elif breach == "skipped-prerequisite":
        changes[2]["prerequisites"] = [changes[0]["id"]]
    elif breach == "first-with-prerequisite":
        changes[0]["prerequisites"], changes[1]["prerequisites"] = [changes[1]["id"]], []
        changes[0], changes[1] = changes[1], changes[0]
    elif breach == "other-revision":
        changes[1]["realisation"]["revision"] = changes[2]["id"]
    elif breach == "other-source":
        changes[1]["realisation"]["source"] = "svn"
    elif breach == "last-not-newer":
        manifest["history"]["to"] = "r9"
    else:
        manifest["changes"] = []
    with pytest.raises(Rejection) as caught:
        changes_contract.check_manifest_rules(manifest)
    assert caught.value.code == "invalid_manifest"


def test_the_same_two_records_give_the_same_bytes_and_the_changes_depend_on_the_revisions_alone(world):
    older, newer = record(world, "r0", label="N"), record(world, "r3")
    (world / "a").mkdir(), (world / "b").mkdir()
    derive(older, newer, world / "a" / "changes.json", HistoryStub(), repositories=world)
    derive(older, newer, world / "b" / "other-name.json", HistoryStub(), repositories=world)
    assert (world / "a" / "changes.json").read_bytes() == (world / "b" / "other-name.json").read_bytes()
    # Other records of the same two revisions: another label, run id, selection, and engine version.
    again = record(world, "r0", folder="again-r0", label="base",
                   further=[{"kind": "engine_version", "value": "1"}],
                   selection={"mode": "subset", "model_point_ids": ["MP-A"]})
    later = record(world, "r3", folder="again-r3", further=[{"kind": "engine_version", "value": "2"}])
    other = derive(again, later, world / "c.json", HistoryStub(), repositories=world).manifest
    first = stored(world / "a" / "changes.json")
    assert other["changes"] == first["changes"] and other["manifest_id"] == first["manifest_id"]
    assert other["base_release"] == "base" and [e["kind"] for e in other["history"]["remainder"]] == ["engine_version"]


def test_two_records_of_one_revision_give_a_manifest_without_a_change(world):
    older = record(world, "r1", folder="run-a", further=[{"kind": "engine_version", "value": "engine 1.0"}])
    newer = record(world, "r1", folder="run-b", further=[{"kind": "engine_version", "value": "engine 1.1"}])
    manifest = derive(older, newer, world / "changes.json", HistoryStub(), repositories=world).manifest
    assert not schema_errors(stored(world / "changes.json"), CHANGES_SCHEMA)
    assert manifest["changes"] == [] and manifest["manifest_id"] == "history-r1-r1"
    assert manifest["history"]["from"] == manifest["history"]["to"] == "r1"
    assert manifest["history"]["remainder"] == [{
        "kind": "engine_version",
        "from": [{"kind": "engine_version", "value": "engine 1.0"}],
        "to": [{"kind": "engine_version", "value": "engine 1.1"}]}]
    # Without ``history`` a manifest still needs one change at least.
    authored = {name: value for name, value in manifest.items() if name != "history"}
    assert any("changes" in error for error in schema_errors(authored, CHANGES_SCHEMA))


def artifact(digit: str) -> dict:
    return {"path": "request.json", "sha256": digit * 64}


def test_the_remainder_names_every_differing_kind_no_revision_fixes_with_both_reference_lists(world):
    same = [{"kind": "calendar", "value": "b"}, {"kind": "calendar", "value": "a"}]
    tables = [{"kind": "tables", "value": "t", "artifact": artifact("b")},
              {"kind": "tables", "value": "t", "artifact": artifact("a")},
              {"kind": "tables", "value": "t"}, {"kind": "tables", "value": "s", "artifact": artifact("c")}]
    older = record(world, "r0", further=[{"kind": "engine_version", "value": "1.0"}, *same, *tables])
    newer = record(world, "r1", further=[{"kind": "engine_version", "value": "1.1"}, *same[::-1],
                                         {"kind": "zone", "value": "z"}, {"kind": "added", "value": "x"}])
    manifest = derive(older, newer, world / "changes.json", HistoryStub(), repositories=world).manifest
    assert not schema_errors(manifest, CHANGES_SCHEMA)
    # By kind. ``calendar`` is the same set on both sides; the release folder and the
    # input data are fixed by a revision and never part of the remainder.
    assert manifest["history"]["remainder"] == [
        {"kind": "added", "from": [], "to": [{"kind": "added", "value": "x"}]},
        {"kind": "engine_version", "from": [{"kind": "engine_version", "value": "1.0"}],
         "to": [{"kind": "engine_version", "value": "1.1"}]},
        # By value, then a reference without an artifact, then by the byte hash.
        {"kind": "tables", "from": [tables[3], tables[2], tables[1], tables[0]], "to": []},
        {"kind": "zone", "from": [], "to": [{"kind": "zone", "value": "z"}]},
    ]
    assert [c["id"] for c in manifest["changes"]] == ["r1"]


def test_remainder_ignores_the_determined_kinds_and_the_order_of_the_references():
    left = {"label": "a", "references": [{"kind": "x", "value": "1"}, {"kind": "x", "value": "2"},
                                         {"kind": "fixed", "value": "old"}]}
    right = {"label": "b", "references": [{"kind": "fixed", "value": "new"}, {"kind": "x", "value": "2"},
                                          {"kind": "x", "value": "1"}]}
    assert remainder(left, right, frozenset({"fixed"})) == []
    assert [entry["kind"] for entry in remainder(left, right, frozenset())] == ["fixed"]


@pytest.mark.parametrize("history, message", [
    (History("git", "a", "c", (Revision("b", "", frozenset()),)), "does not lead"),
    (History("git", "a", "b", ()), "does not lead"),
    (History("git", "a", "b", (Revision("b", "", frozenset({"model"})),)), "class"),
])
def test_a_history_the_contract_does_not_allow_writes_no_manifest(history, message):
    with pytest.raises(RuntimeError, match=message):
        build_manifest(history, "liability_cashflow", "N", frozenset(), [])


def derive_command(monkeypatch, world: Path, older, newer, output, engine=HistoryStub) -> int:
    monkeypatch.setattr("degelmann.deltarecon.__main__.engine", engine)
    return main(["derive", str(older), str(newer), "--output", str(output), "--repositories", str(world)])


def test_derive_command_prints_the_changes_and_the_remainder(world, monkeypatch, capsys):
    older = record(world, "r0", label="N", further=[{"kind": "engine_version", "value": "1.0"}])
    newer = record(world, "r3", further=[{"kind": "engine_version", "value": "1.1"}])
    monkeypatch.chdir(world)
    assert derive_command(monkeypatch, world, older, newer, world / "changes.json") == 0
    assert capsys.readouterr().out.splitlines() == [
        "derive: 3 changes from r0 to r3",
        "  r1 [parameter] Lower the lapse rate",
        "  r2 [data, code] r2",
        "  r3 [no class] Touch nothing that has a class",
        "remainder: engine_version",
        "manifest: changes.json",
    ]
    # No command overwrites a file.
    kept = folder_hashes(world)
    assert derive_command(monkeypatch, world, older, newer, world / "changes.json") == 2
    assert "exists already" in capsys.readouterr().err and folder_hashes(world) == kept


def test_derive_command_prints_a_message_that_stdout_cannot_encode(world, monkeypatch, capsysbinary):
    import io
    import sys

    class Odd(HistoryStub):
        line = (("r0", "", ()), ("r1", "Not UTF-8: \ufffd and 保険\n", ("data",)))

    older, newer = record(world, "r0"), record(world, "r1")
    buffer = io.BytesIO()
    monkeypatch.setattr(sys, "stdout", io.TextIOWrapper(buffer, encoding="ascii", errors="strict"))
    assert derive_command(monkeypatch, world, older, newer, world / "changes.json", Odd) == 0
    sys.stdout.flush()
    assert b"  r1 [data] Not UTF-8: ? and ??" in buffer.getvalue()
    assert stored(world / "changes.json")["changes"][0]["description"] == "Not UTF-8: \ufffd and 保険"


@pytest.mark.parametrize("case, code", [("wrong-order", "unrelated_revisions"),
                                        ("unknown-revision", "unknown_reference")])
def test_a_manifest_that_cannot_be_derived_is_rejected_with_its_code_and_writes_nothing(
        world, monkeypatch, capsys, case, code):
    older, newer = record(world, "r0"), record(world, "r3")
    if case == "wrong-order":
        older, newer = newer, older
    else:
        newer = record(world, "outside")
    before = folder_hashes(world)
    assert derive_command(monkeypatch, world, older, newer, world / "changes.json") == 1
    output = capsys.readouterr()
    assert output.out.splitlines()[0] == "derive: rejected" and f"diagnostic: {code}: " in output.out
    assert folder_hashes(world) == before
    with pytest.raises(Rejection) as caught:
        derive(older, newer, world / "changes.json", HistoryStub(), repositories=world)
    assert caught.value.code == code and folder_hashes(world) == before


class TwoStages(HistoryStub):
    stages = frozenset({"liability_cashflow", "other_stage"})


def test_records_of_two_stages_are_a_stage_mismatch(world, monkeypatch, capsys):
    monkeypatch.setitem(STAGE_QUANTITIES, "other_stage", STAGE_QUANTITIES["liability_cashflow"])
    older = record(world, "r0", engine=TwoStages())
    newer = record(world, "r3", engine=TwoStages(), stage="other_stage")
    before = folder_hashes(world)
    assert derive_command(monkeypatch, world, older, newer, world / "changes.json", TwoStages) == 1
    assert "diagnostic: stage_mismatch: " in capsys.readouterr().out and folder_hashes(world) == before


@pytest.mark.parametrize("case", ["no-record", "failed-run", "enabled-changes", "replay", "newer-enabled-changes"])
def test_derive_command_starts_nothing_for_a_record_it_does_not_take(world, monkeypatch, capsys, case):
    good = record(world, "r0")
    bad = world / "run" / "run-record.json"
    if case == "failed-run":
        (world / "rel" / "points.csv").write_text(POINTS.replace("MP-B,0,2,2", "MP-B,0,2,raise"), "utf-8")
        assert run_stub(world)[0].outcome == "failed"
    elif case in ("enabled-changes", "newer-enabled-changes"):
        entries = [change("chg-point-b", patch_text("points.csv", POINTS, POINTS_B), world / "run")]
        request = stub_request(world, changes=with_manifest(world, entries, ["chg-point-b"]))
        assert run_stub(world, request)[0].outcome == "succeeded"
    elif case == "replay":
        assert run_stub(world)[0].outcome == "succeeded"
        assert replay(bad, StubEngine(), repositories=world).outcome == "reproduced_exactly"
        bad = world / "run" / "replay-record.json"
    older, newer = (good, bad) if case == "newer-enabled-changes" else (bad, good)
    before = folder_hashes(world)
    assert derive_command(monkeypatch, world, older, newer, world / "changes.json") == 2
    assert capsys.readouterr().err.startswith("error: ") and folder_hashes(world) == before
    with pytest.raises(UsageError):
        derive(older, newer, world / "changes.json", HistoryStub(), repositories=world)


def test_the_output_must_not_exist_and_its_folder_must(world, monkeypatch, capsys):
    older, newer = record(world, "r0"), record(world, "r3")
    (world / "changes.json").write_text("kept", "utf-8")
    before = folder_hashes(world)
    for output, reason in ((world / "changes.json", "exists already"),
                           (world / "absent" / "changes.json", "does not exist")):
        assert derive_command(monkeypatch, world, older, newer, output) == 2
        assert reason in capsys.readouterr().err
        with pytest.raises(UsageError, match=reason):
            derive(older, newer, output, HistoryStub(), repositories=world)
    assert folder_hashes(world) == before and not (world / "absent").exists()


# --- the history reader of the reference engine -------------------------------------

POINTS_FILE = f"{PRODUCT_FOLDER}/model_point_table.csv"
LAPSE = f"{PRODUCT_FOLDER}/lapse_table.csv"
CODE = f"{PRODUCT_FOLDER}/RLV_DE_S/Projection/__init__.py"
BASE = {"README.md": "readme\n", POINTS_FILE: "points\n", LAPSE: "lapse\n", CODE: "code\n",
        f"{PRODUCT_FOLDER}/mort_table.csv": "mortality\n"}


def identity(revision: str, label: str = "release") -> dict:
    from degelmann.deltarecon.engines.reference_model import release_references
    return {"label": label, "references": release_references(revision)}


def read_history(repositories: Path, older: str, newer: str) -> History:
    from degelmann.deltarecon.engines.reference_model import ReferenceModel
    return ReferenceModel().history(identity(older), identity(newer), repositories)


def revise(clone: Path, message: str, files: dict | None = None) -> str:
    write_files(clone, files or {})
    return commit_message(clone, message.encode("utf-8"))


def move(clone: Path, old: str, new: str) -> None:
    clone.joinpath(*new.split("/")).parent.mkdir(parents=True, exist_ok=True)
    git(clone, "mv", old, new)


@pytest.fixture
def repository(tmp_path):
    """A throw-away repository with one commit that holds a file of every class."""
    repositories, clone = empty_repository(tmp_path)
    return repositories, clone, revise(clone, "Base", BASE)


@pytest.mark.parametrize("path, expected", [
    (POINTS_FILE, "data"),
    (LAPSE, "parameter"), (f"{PRODUCT_FOLDER}/a_new_table.csv", "parameter"),
    (CODE, "code"), (f"{PRODUCT_FOLDER}/RLV_DE_S/_system.json", "code"),
    (f"{PRODUCT_FOLDER}/RLV_DE_S/Data/table.csv", "code"), (f"{PRODUCT_FOLDER}/RLV_DE_S/model_point_table.csv", "code"),
    ("README.md", None), (f"{PRODUCT_FOLDER}/UPSTREAM.md", None), (f"{PRODUCT_FOLDER}/lapse_table.CSV", None),
    (f"{PRODUCT_FOLDER}/archive/lapse_table.csv", None), ("model_point_table.csv", None),
    ("lapse_table.csv", None), (f"other/{LAPSE}", None), (f"{PRODUCT_FOLDER}/RLV_DE_S", None),
    (f"{PRODUCT_FOLDER}/RLV_DE_S_2/x.py", None), ("tools/build_portfolio.py", None),
])
def test_the_class_of_a_path(path, expected):
    from degelmann.deltarecon.engines.reference_model import path_class
    assert path_class(path) == expected


def test_history_lists_the_main_line_with_the_classes_of_every_touched_path(repository):
    repositories, clone, base = repository
    expected = [
        (revise(clone, "A parameter table", {LAPSE: "lapse 2\n"}), {"parameter"}),
        # Two classes: a parameter table and the model code. The revision is not split.
        (revise(clone, "A table and the code that reads it", {LAPSE: "lapse 3\n", CODE: "code 2\n"}),
         {"parameter", "code"}),
        (revise(clone, "The portfolio", {POINTS_FILE: "points 2\n"}), {"data"}),
        # No class: a file outside the mapped paths, and a revision that changes nothing.
        (revise(clone, "The README", {"README.md": "readme 2\n", "tools/tool.py": "tool\n"}), set()),
        (revise(clone, "Nothing"), set()),
        # Added and removed files have the class of their path.
        (revise(clone, "Add a table", {f"{PRODUCT_FOLDER}/new_table.csv": "new\n"}), {"parameter"}),
        (revise(clone, "Remove the code", {CODE: None}), {"code"}),
        (revise(clone, "Remove a table and the portfolio",
                {f"{PRODUCT_FOLDER}/new_table.csv": None, POINTS_FILE: None}), {"data", "parameter"}),
    ]
    state = clone_state(clone)
    history = read_history(repositories, base, expected[-1][0])
    assert (history.source, history.older, history.newer) == ("git", base, expected[-1][0])
    assert [(r.id, set(r.classes)) for r in history.revisions] == expected
    assert [r.message for r in history.revisions][:2] == ["A parameter table", "A table and the code that reads it"]
    # A part of the main line, and both ends at one revision.
    part = read_history(repositories, expected[1][0], expected[3][0])
    assert [r.id for r in part.revisions] == [expected[2][0], expected[3][0]]
    same = read_history(repositories, expected[2][0], expected[2][0])
    assert same.revisions == () and same.older == same.newer == expected[2][0]
    assert clone_state(clone) == state


def test_a_moved_file_counts_with_its_old_and_its_new_path(repository):
    repositories, clone, base = repository
    move(clone, LAPSE, "docs/lapse_table.csv")  # out of the mapped paths: the old path decides
    out = revise(clone, "Move a table out")
    move(clone, POINTS_FILE, f"{PRODUCT_FOLDER}/RLV_DE_S/points.csv")  # data and code
    both = revise(clone, "Move the portfolio into the model")
    move(clone, "README.md", f"{PRODUCT_FOLDER}/readme.csv")  # into the mapped paths
    into = revise(clone, "Move the README in")
    history = read_history(repositories, base, into)
    assert [(r.id, set(r.classes)) for r in history.revisions] == [
        (out, {"parameter"}), (both, {"data", "code"}), (into, {"parameter"})]


def test_a_merge_is_one_change_with_the_classes_of_the_difference_to_its_first_parent(repository):
    repositories, clone, base = repository
    first = revise(clone, "On the main line", {"README.md": "readme 2\n"})
    branch(clone, "side")
    inside = [revise(clone, "A table on the branch", {LAPSE: "lapse 2\n"}),
              revise(clone, "The code on the branch", {CODE: "code 2\n"})]
    git(clone, "checkout", "--quiet", "work")
    beside = revise(clone, "Meanwhile on the main line", {POINTS_FILE: "points 2\n"})
    merged = merge(clone, "work", "side", "Merge the branch side")
    last = revise(clone, "After the merge", {"README.md": "readme 3\n"})
    history = read_history(repositories, base, last)
    # The two commits of the branch are not listed; the merge carries their classes and
    # not that of the main-line commit beside them.
    assert [(r.id, set(r.classes)) for r in history.revisions] == [
        (first, set()), (beside, {"data"}), (merged, {"parameter", "code"}), (last, set())]
    assert not set(inside) & {r.id for r in history.revisions}
    assert history.revisions[2].message == "Merge the branch side\n"
    # A commit inside the merged branch is an ancestor, but no point of the main line.
    for older in inside:
        with pytest.raises(Rejection) as caught:
            read_history(repositories, older, last)
        assert caught.value.code == "unrelated_revisions"
    # From the branch itself its commits are the main line.
    assert [r.id for r in read_history(repositories, first, inside[1]).revisions] == inside


def test_revisions_that_are_not_on_one_main_line_are_unrelated(repository):
    repositories, clone, base = repository
    branch(clone, "left")
    left = revise(clone, "Left", {LAPSE: "left\n"})
    branch(clone, "right", base)
    right = revise(clone, "Right", {CODE: "right\n"})
    # A merge whose second parent is the main line: the older revision is reached through it only.
    git(clone, "checkout", "--quiet", "left")
    reversed_merge = merge(clone, "left", "right", "Merge right into left")
    for older, newer in ((left, right), (right, left), (right, reversed_merge), (left, base), (reversed_merge, left)):
        with pytest.raises(Rejection) as caught:
            read_history(repositories, older, newer)
        assert caught.value.code == "unrelated_revisions" and older in caught.value.message
    assert [r.id for r in read_history(repositories, left, reversed_merge).revisions] == [reversed_merge]


def test_a_shallow_clone_is_refused_and_never_called_unrelated(repository, tmp_path):
    repositories, clone, base = repository
    middle = revise(clone, "Second", {LAPSE: "lapse 2\n"})
    last = revise(clone, "Third", {LAPSE: "lapse 3\n"})
    shallow = tmp_path / "shallow"
    shallow.mkdir()
    git(tmp_path, "clone", "--quiet", "--depth", "2", clone.as_uri(), str(shallow / CLONE_NAME))
    for older in (base, middle, last):  # absent, at the cut, and present
        with pytest.raises(UsageError, match="cut off"):
            read_history(shallow, older, last)
    assert [r.id for r in read_history(repositories, base, last).revisions] == [middle, last]


def test_a_revision_the_clone_does_not_hold_is_an_unknown_reference(repository, tmp_path):
    repositories, clone, base = repository
    last = revise(clone, "Second", {LAPSE: "lapse 2\n"})
    tree = git(clone, "rev-parse", f"{last}^{{tree}}").decode("ascii").strip()
    for older, newer in ((base, "1" * 40), ("1" * 40, last), (base, tree)):
        with pytest.raises(Rejection) as caught:
            read_history(repositories, older, newer)
        assert caught.value.code == "unknown_reference"
    for absent in (tmp_path / "absent", tmp_path):  # no repositories folder, and one without the clone
        with pytest.raises(Rejection) as caught:
            read_history(absent, base, last)
        assert caught.value.code == "unknown_reference" and "git clone" in caught.value.message


def test_the_revision_of_an_identity_is_read_whatever_its_engine_version_and_input_data(repository):
    from degelmann.deltarecon.engines.reference_model import ReferenceModel
    repositories, clone, base = repository
    last = revise(clone, "Second", {LAPSE: "lapse 2\n"})
    value = f"git:{REPOSITORY_URL}@"
    older = {"label": "old", "references": [
        {"kind": "code_state", "value": value + base}, {"kind": "parameter_set", "value": value + base},
        {"kind": "input_data", "value": value + "2" * 40}, {"kind": "engine_version", "value": "another engine"}]}
    newer = {"label": "new", "references": [
        {"kind": "parameter_set", "value": value + last}, {"kind": "code_state", "value": value + last},
        {"kind": "some_other_kind", "value": "anything"}]}
    assert [r.id for r in ReferenceModel().history(older, newer, repositories).revisions] == [last]
    for edit in (lambda refs: refs.pop(0), lambda refs: refs[0].update(value=value + last),
                 lambda refs: refs[0].update(value=f"git:https://example.invalid/other@{base}"),
                 lambda refs: refs[1].update(artifact={"path": "x", "sha256": "0" * 64}),
                 lambda refs: refs.append(dict(refs[0], value=value + last)),
                 lambda refs: [r.update(value=r["value"][:-30]) for r in refs[:2]]):
        broken = json.loads(json.dumps(older))
        edit(broken["references"])
        with pytest.raises(Rejection) as caught:
            ReferenceModel().history(broken, newer, repositories)
        assert caught.value.code == "unknown_reference"


def test_the_log_message_is_read_from_the_commit_object(repository):
    repositories, clone, base = repository
    messages = [b"One line\n", b"Subject\n\nA body of\nseveral lines.\n\n# no comment line is cut\n\n\n",
                b"", b"\n\n", b"Not UTF-8: \xff\xfe and Latin-1 \xe4\n", b"  indented, no line end",
                "Ümlaut und 保険\n".encode("utf-8"), b"Carriage return\r\n"]
    revisions = [commit_message(clone, message) for message in messages]
    history = read_history(repositories, base, revisions[-1])
    assert [r.id for r in history.revisions] == revisions
    assert [r.message for r in history.revisions] == [
        "One line\n", "Subject\n\nA body of\nseveral lines.\n\n# no comment line is cut\n\n\n", "", "\n\n",
        "Not UTF-8: �� and Latin-1 �\n", "  indented, no line end", "Ümlaut und 保険\n",
        "Carriage return\r\n"]
    manifest = build_manifest(history, "liability_cashflow", "N", frozenset({"code_state"}), [])
    assert not schema_errors(manifest, CHANGES_SCHEMA)
    assert [c["description"] for c in manifest["changes"]] == [
        "One line", "Subject\n\nA body of\nseveral lines.\n\n# no comment line is cut", revisions[2], revisions[3],
        "Not UTF-8: �� and Latin-1 �", "  indented, no line end", "Ümlaut und 保険", "Carriage return"]
    document_bytes(manifest).decode("utf-8")


HOSTILE_CONFIGURATION = """[diff]
\trenames = copies
\tignoreSubmodules = all
\tnoprefix = true
[core]
\tquotePath = true
[i18n]
\tlogOutputEncoding = latin1
\tcommitEncoding = latin1
[log]
\tshowSignature = true
\tfollow = true
[format]
\tpretty = oneline
"""


def test_the_history_does_not_depend_on_the_configuration_of_the_user(repository, tmp_path, monkeypatch):
    repositories, clone, base = repository
    move(clone, LAPSE, "docs/Tafel größer.csv")
    moved = revise(clone, "Verschiebe die Tafel: größer\n")
    last = commit_message(clone, b"Latin-1 \xe4\n")
    plain = read_history(repositories, base, last)
    assert [set(r.classes) for r in plain.revisions] == [{"parameter"}, set()] and plain.revisions[0].id == moved
    configuration = tmp_path / "hostile.gitconfig"
    configuration.write_text(HOSTILE_CONFIGURATION, "utf-8")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(configuration))
    monkeypatch.setenv("LC_ALL", "C")
    assert read_history(repositories, base, last) == plain


# --- from two run records of the reference model to the manifest -------------------


@pytest.fixture(scope="module")
def chain(tmp_path_factory):
    """A throw-away clone with three main-line revisions after release N, one of them a merge,
    and the records of a subset run of release N and of the newest revision."""
    tmp_path = tmp_path_factory.mktemp("derive-chain")
    repositories, clone = throwaway(tmp_path)
    edit_file(clone, LAPSE_TABLE, "\n1,0.06,", "\n1,0.05,")
    lapse = commit(clone, "Lower the lapse rate of policy year 1\n\nFrom 0.06 to 0.05.")
    (clone / "README.md").write_bytes((clone / "README.md").read_bytes() + b"\nA note.\n")
    note = commit(clone, "Add a note to the README")
    branch(clone, "side")
    edit_file(clone, LAPSE_TABLE, "\n2,0.04,", "\n2,0.05,")
    inside = [commit(clone, "Raise the lapse rate of policy year 2")]
    (clone / "README.md").write_bytes((clone / "README.md").read_bytes() + b"Another note.\n")
    inside.append(commit(clone, "Add another note"))
    merged = merge(clone, "work", "side", "Merge the branch side")
    records = {}
    for name, revision, label in (("older", RELEASE_N, "N"), ("newer", merged, "N+1")):
        folder = tmp_path / name
        assert main(["request", "--revision", revision, "--repositories", str(repositories), "--label", label,
                     "--run-id", f"run-{name}", "--output", str(folder / "request.json"),
                     "--subset", NEW_BUSINESS]) == 0
        assert main(["run", str(folder / "request.json"), "--repositories", str(repositories)]) == 0
        records[name] = folder / "run-record.json"
    return {"tmp": tmp_path, "repositories": repositories, "clone": clone, "records": records,
            "revisions": [lapse, note, merged], "inside": inside}


def derive_process(chain: dict, output: Path, environment: dict | None = None, order=("older", "newer"),
                   repositories: Path | None = None) -> subprocess.CompletedProcess:
    """One ``derive`` command in a process of its own."""
    return subprocess.run(
        [sys.executable, "-m", "degelmann.deltarecon", "derive", *(str(chain["records"][name]) for name in order),
         "--output", str(output), "--repositories", str(repositories or chain["repositories"])],
        cwd=ROOT, capture_output=True, text=True, env={**git_environment(), **(environment or {})})


def test_two_processes_derive_the_same_bytes_from_two_run_records(chain, tmp_path):
    state = clone_state(chain["clone"])
    before = {name: folder_hashes(path.parent) for name, path in chain["records"].items()}
    configuration = tmp_path / "hostile.gitconfig"
    configuration.write_text(HOSTILE_CONFIGURATION, "utf-8")
    (tmp_path / "manifest-a").mkdir(), (tmp_path / "manifest-b" / "deeper").mkdir(parents=True)
    first = derive_process(chain, tmp_path / "manifest-a" / "changes.json")
    second = derive_process(chain, tmp_path / "manifest-b" / "deeper" / "other.json",
                            {"GIT_CONFIG_GLOBAL": str(configuration), "LC_ALL": "C", "TZ": "Asia/Tokyo"})
    assert (first.returncode, second.returncode) == (0, 0), first.stderr + second.stderr
    written = (tmp_path / "manifest-a" / "changes.json").read_bytes()
    assert written == (tmp_path / "manifest-b" / "deeper" / "other.json").read_bytes()

    manifest = read_document(tmp_path / "manifest-a" / "changes.json", CHANGES_SCHEMA)
    lapse, note, merged = chain["revisions"]
    assert manifest["manifest_id"] == f"history-{RELEASE_N}-{merged}" and manifest["base_release"] == "N"
    assert manifest["stage"] == "liability_cashflow"
    assert manifest["history"] == {"source": "git", "from": RELEASE_N, "to": merged,
                                   "determines": ["code_state", "input_data", "parameter_set"], "remainder": []}
    # Every main-line revision between the two, in order; the commits of the branch are not listed.
    assert [c["id"] for c in manifest["changes"]] == [lapse, note, merged]
    assert [c["class"] for c in manifest["changes"]] == [["parameter"], [], ["parameter"]]
    assert [c["description"] for c in manifest["changes"]] == [
        "Lower the lapse rate of policy year 1\n\nFrom 0.06 to 0.05.", "Add a note to the README",
        "Merge the branch side"]
    assert [c["prerequisites"] for c in manifest["changes"]] == [[], [lapse], [note]]
    assert [c["realisation"] for c in manifest["changes"]] == [
        {"type": "revision", "source": "git", "revision": revision} for revision in (lapse, note, merged)]
    changes_contract.check_manifest_rules(manifest)
    # No timestamp and no path of the machine.
    text = written.decode("utf-8")
    assert str(chain["tmp"]) not in text and str(ROOT) not in text and "recorded_at" not in text
    assert first.stdout.splitlines()[0] == f"derive: 3 changes from {RELEASE_N} to {merged}"
    assert "remainder: none" in first.stdout
    # The clone and the folders of both records are as they were.
    assert clone_state(chain["clone"]) == state
    assert {name: folder_hashes(path.parent) for name, path in chain["records"].items()} == before


def test_the_records_in_the_wrong_order_are_unrelated_and_nothing_is_written(chain, tmp_path):
    state = clone_state(chain["clone"])
    done = derive_process(chain, tmp_path / "changes.json", order=("newer", "older"))
    assert done.returncode == 1 and "diagnostic: unrelated_revisions: " in done.stdout
    assert list(tmp_path.iterdir()) == [] and clone_state(chain["clone"]) == state


def test_a_clone_without_the_revision_and_no_clone_are_unknown_references(chain, tmp_path):
    # The clone of the session holds release N and not the newest revision of the throw-away clone.
    state = clone_state()
    for repositories in (REPOSITORIES, tmp_path / "absent"):
        done = derive_process(chain, tmp_path / "changes.json", repositories=repositories)
        assert done.returncode == 1 and "diagnostic: unknown_reference: " in done.stdout
    assert list(tmp_path.iterdir()) == [] and clone_state() == state


def test_a_shallow_clone_does_not_start_the_command(chain, tmp_path):
    shallow = tmp_path / "shallow"
    shallow.mkdir()
    git(tmp_path, "clone", "--quiet", "--depth", "1", "--branch", "work", chain["clone"].as_uri(),
        str(shallow / CLONE_NAME))
    done = derive_process(chain, tmp_path / "changes.json", repositories=shallow)
    assert done.returncode == 2 and "cut off" in done.stderr
    assert "unrelated_revisions" not in done.stdout + done.stderr and not (tmp_path / "changes.json").exists()


def other_engine_version(source: Path, target: Path, version: str) -> Path:
    """A copy of a recorded run whose release identity names another engine version."""
    shutil.copytree(source, target)
    for name in ("request.json", "response.json"):
        document = stored(target / name)
        for reference in document["release"]["references"]:
            if reference["kind"] == "engine_version":
                reference["value"] = version
        (target / name).write_bytes(document_bytes(document))
    record = stored(target / "run-record.json")
    record["releases"] = [stored(target / "request.json")["release"]]
    for entry in record["inputs"] + record["outputs"]:
        entry["artifact"]["sha256"] = sha256_file(target / entry["artifact"]["path"])
    (target / "run-record.json").write_bytes(document_bytes(record))
    return target / "run-record.json"


def test_one_revision_with_two_engine_versions_gives_no_change_and_names_the_remainder(chain, tmp_path, monkeypatch,
                                                                                    capsys):
    older = chain["records"]["older"]
    newer = other_engine_version(older.parent, tmp_path / "upgraded", "another engine 2.0")
    (tmp_path / "out").mkdir()
    assert cli(monkeypatch, "derive", older, newer, "--output", tmp_path / "out" / "changes.json",
               "--repositories", chain["repositories"]) == 0
    assert "derive: 0 changes" in capsys.readouterr().out
    manifest = read_document(tmp_path / "out" / "changes.json", CHANGES_SCHEMA)
    version = next(r for r in stored(older)["releases"][0]["references"] if r["kind"] == "engine_version")
    assert manifest["changes"] == []
    assert manifest["history"]["from"] == manifest["history"]["to"] == RELEASE_N
    assert manifest["history"]["remainder"] == [{
        "kind": "engine_version", "from": [version],
        "to": [{"kind": "engine_version", "value": "another engine 2.0"}]}]
    # ``regression`` takes the record of another engine version: it runs the revision on the
    # present engine, compares, and names both versions in its output and in the compare result.
    capsys.readouterr()
    assert cli(monkeypatch, "regression", newer, "--revision", RELEASE_N, "--repositories", chain["repositories"],
               "--output", tmp_path / "regression") == 0
    output = capsys.readouterr().out
    present = version["value"]
    assert "regression: no deviation above tolerance" in output
    assert f"engine version: left another engine 2.0, right {present}" in output
    result = read_document(tmp_path / "regression" / "compare.result.json", "compare.schema.json")
    assert result["engine_version"] == {"left": "another engine 2.0", "right": present}
    run = stored(tmp_path / "regression" / "run" / "request.json")
    assert {"kind": "engine_version", "value": present} in run["release"]["references"]
    # ``replay`` stays strict: it refuses the same record and writes nothing.
    before = folder_hashes(newer.parent)
    assert cli(monkeypatch, "replay", newer, "--repositories", chain["repositories"]) == 1
    output = capsys.readouterr().out
    assert "replay: rejected" in output and "diagnostic: unknown_reference:" in output
    assert "another engine 2.0" in output and folder_hashes(newer.parent) == before


def test_the_record_of_a_regression_run_derives_the_manifest_of_two_runs(chain, tmp_path, monkeypatch):
    """The call of the quick start: the newer record is the run of a regression folder.

    That record lies in ``run/`` beside a copy of the recorded run, and its input data
    names the commit of the recorded run, not the newer one. Only the state revision
    counts, so the manifest is the one of two plain runs, byte for byte.
    """
    older, merged = chain["records"]["older"], chain["revisions"][-1]
    state, before = clone_state(chain["clone"]), folder_hashes(older.parent)
    assert cli(monkeypatch, "regression", older, "--revision", merged, "--repositories", chain["repositories"],
               "--output", tmp_path / "regression") == 1  # the lapse change moves results
    newer = tmp_path / "regression" / "run" / "run-record.json"
    values = {r["kind"]: r["value"] for r in stored(newer)["releases"][0]["references"]}
    assert values["code_state"].endswith(merged) and values["input_data"].endswith(RELEASE_N)
    regression_folder = folder_hashes(tmp_path / "regression")
    (tmp_path / "out").mkdir()
    assert cli(monkeypatch, "derive", older, newer, "--output", tmp_path / "out" / "regression.json",
               "--repositories", chain["repositories"]) == 0
    assert cli(monkeypatch, "derive", older, chain["records"]["newer"], "--output", tmp_path / "out" / "runs.json",
               "--repositories", chain["repositories"]) == 0
    written = (tmp_path / "out" / "regression.json").read_bytes()
    assert written == (tmp_path / "out" / "runs.json").read_bytes()
    assert [c["id"] for c in stored(tmp_path / "out" / "regression.json")["changes"]] == chain["revisions"]
    assert folder_hashes(tmp_path / "regression") == regression_folder
    assert folder_hashes(older.parent) == before and clone_state(chain["clone"]) == state
