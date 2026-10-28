"""The model points of a run in worker processes.

The rows of order, bytes, crash and count run against a stub engine whose sessions project
through ``degelmann.deltarecon.workers``, so they need no calculation engine. The rows of
the reference model use one throw-away commit with a point of unknown sex and three points.
"""
from __future__ import annotations

import subprocess
import sys
from concurrent import futures

import pytest

from degelmann.deltarecon import workers
from degelmann.deltarecon.engines.reference_model import PATHS
from degelmann.deltarecon.run import ModelPointFailure, UsageError
from degelmann.deltarecon.workers import WORKERS_VARIABLE, ordered_map, worker_count

from conftest import (POINTS, ROOT, as_bits, POINT_TABLE, StubEngine, WorkerStub, _stub_project, _stub_start, cli, commit,
                      edit_file, model_request, run_stub, stored, text, throwaway, with_columns, without_volatile)


# --- stub engine ----------------------------------------------------------------------


def test_every_worker_count_writes_the_bytes_of_the_loop_in_the_order_of_the_selection(world):
    run_stub(world, engine=StubEngine(), folder="loop")
    expected = {name: (world / "loop" / name).read_bytes() for name in ("response.json", "results.csv")}
    for count in (1, 2, 3):
        engine = WorkerStub(count)
        result, _ = run_stub(world, engine=engine, folder=f"workers-{count}")
        folder = world / f"workers-{count}"
        assert result.outcome == "succeeded"
        assert engine.asked == [["MP-A", "MP-B", "MP-C", "MP-D"]]  # writer order, early points finish last
        assert {name: (folder / name).read_bytes() for name in expected} == expected, count
        assert without_volatile(stored(folder / "run-record.json")) == \
            without_volatile(stored(world / "loop" / "run-record.json"))


def test_a_failed_stub_point_and_a_repeated_id_fail_as_in_the_loop(world):
    (world / "rel" / "points.csv").write_text(POINTS.replace("MP-C,0,0,1e-05", "MP-C,0,0,raise")
                                              + "MP-D,3,4,1e16\n", "utf-8")
    run_stub(world, engine=StubEngine(), folder="loop")
    engine = WorkerStub(3)
    result, _ = run_stub(world, engine=engine, folder="workers")
    assert result.outcome == "failed"
    assert engine.asked == [["MP-A", "MP-B", "MP-C"]]  # the repeated id is never sent to a worker
    assert (world / "workers" / "response.json").read_bytes() == (world / "loop" / "response.json").read_bytes()
    assert stored(world / "workers" / "response.json")["failed_model_points"] == [
        {"model_point_id": "MP-C", "message": "The stub cannot calculate this model point."},
        {"model_point_id": "MP-D", "message": "The release holds this model point id more than once."}]


def test_an_error_in_a_worker_reaches_the_caller(world):
    (world / "rel" / "points.csv").write_text(POINTS.replace("MP-C,0,0,1e-05", "MP-C,0,0,crash"), "utf-8")
    with pytest.raises(RuntimeError, match="the stub worker crashes"):
        run_stub(world, engine=WorkerStub(2))
    assert sorted(p.name for p in (world / "run").iterdir()) == ["request.json"]


def test_the_pool_has_no_more_processes_than_points(world, monkeypatch):
    sizes = []

    class Recorded(futures.ProcessPoolExecutor):
        def __init__(self, max_workers, **options):
            sizes.append(max_workers)
            super().__init__(max_workers, **options)

    monkeypatch.setattr(futures, "ProcessPoolExecutor", Recorded)
    folder = str(world / "rel")
    assert ordered_map(_stub_start, (folder,), _stub_project, ["MP-B", "MP-A"], 8) == [
        ("ok", [(0, [2.0, 2.0]), (1, [2.0, 4.0]), (2, [2.0, 6.0])]), ("ok", [(12, [1.5, 19.5]), (13, [1.5, 21.0])])]
    assert sizes == [2]
    assert ordered_map(_stub_start, (folder,), _stub_project, [], 8) == [] and sizes == [2]


# --- the worker count -----------------------------------------------------------------


def test_the_worker_count_is_the_option_else_the_variable_else_the_processors(monkeypatch):
    monkeypatch.setenv(WORKERS_VARIABLE, "5")
    assert worker_count(3) == 3
    assert worker_count() == 5
    monkeypatch.delenv(WORKERS_VARIABLE)
    monkeypatch.setattr(workers.os, "process_cpu_count", lambda: 7)
    assert worker_count() == 7
    monkeypatch.setattr(workers.os, "process_cpu_count", lambda: None)
    assert worker_count() == 1
    for value in ("0", "abc", "", "-2", "1.5", " 4"):
        monkeypatch.setenv(WORKERS_VARIABLE, value)
        with pytest.raises(UsageError, match=f"^{WORKERS_VARIABLE} must be a whole number of at least 1"):
            worker_count()
    with pytest.raises(UsageError, match="^the number of workers must be a whole number"):
        worker_count(0)


def test_the_worker_module_loads_the_standard_library_alone():
    code = ("import sys, degelmann.deltarecon.workers\n"
            "loaded = [m for m in ('jsonschema', 'degelmann.deltarecon.run', 'degelmann.deltarecon.documents')"
            " if m in sys.modules]\n"
            "assert not loaded, loaded\n")
    done = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_the_usage_error_is_one_class_wherever_it_is_imported():
    from degelmann.deltarecon import errors, run
    assert run.UsageError is errors.UsageError is workers.UsageError is UsageError


def test_a_faulty_worker_count_cannot_start_a_command(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv(WORKERS_VARIABLE, raising=False)
    for command in (["run", tmp_path / "request.json"], ["walk", tmp_path / "a", tmp_path / "b", "--output", tmp_path / "w"]):
        with pytest.raises(SystemExit) as stopped:
            cli(monkeypatch, *command, "--workers", "0")
        assert stopped.value.code == 2 and "argument --workers: must be a whole number" in capsys.readouterr().err
    monkeypatch.setenv(WORKERS_VARIABLE, "abc")
    for command in (["run", tmp_path / "request.json"], ["replay", tmp_path / "run-record.json"],
                    ["search", tmp_path / "a", tmp_path / "b", "--output", tmp_path / "s"]):
        assert cli(monkeypatch, *command) == 2
        assert capsys.readouterr().err == (f"error: {WORKERS_VARIABLE} must be a whole number of at least 1, "
                                           "not 'abc'\n")
    assert not any(tmp_path.iterdir())


# --- reference model ------------------------------------------------------------------


@pytest.fixture(scope="module")
def unknown_sex(tmp_path_factory):
    """A throw-away clone whose commit gives one point an unknown sex, and three points of it."""
    tmp_path = tmp_path_factory.mktemp("unknown-sex")
    repositories, clone = throwaway(tmp_path)
    lines = text(POINT_TABLE).splitlines()
    columns = lines[0].split(",")
    edit_file(clone, POINT_TABLE, lines[15] + "\n", with_columns(columns, lines[15], sex="X") + "\n")
    revision = commit(clone, "Give one model point an unknown sex")
    ids = [lines[row].split(",")[columns.index("policy_id")] for row in (1, 2, 15)]
    index = lines[15].split(",")[columns.index("point_id")]
    return repositories, revision, ids, index


def test_a_failed_point_among_others_gives_the_same_response_on_every_worker_count(monkeypatch, tmp_path, capsys,
                                                                                   unknown_sex):
    repositories, revision, ids, index = unknown_sex
    responses = {}
    for count in ("1", "3"):
        folder = tmp_path / count
        request_path = model_request(monkeypatch, folder, *ids, revision=revision, repositories=repositories)
        assert cli(monkeypatch, "run", request_path, "--repositories", repositories, "--workers", count) == 1
        assert "outcome: failed" in capsys.readouterr().out
        responses[count] = (folder / "response.json").read_bytes()
        assert not (folder / "results.csv").exists()
    assert responses["3"] == responses["1"]
    assert stored(tmp_path / "3" / "response.json")["failed_model_points"] == [
        {"model_point_id": ids[2], "message": f"result_cf raised ValueError: invalid sex in RLV_DE_S.Projection[{index}].sex()"}]
    assert without_volatile(stored(tmp_path / "3" / "run-record.json")) == \
        without_volatile(stored(tmp_path / "1" / "run-record.json"))


@pytest.mark.parametrize("path", PATHS)
def test_the_workers_give_the_bits_and_the_messages_of_the_parent(path, unknown_sex):
    """One state, projected in three workers and then point by point in the parent."""
    from degelmann.deltarecon.engines.reference_model import ReferenceModel, release_references
    repositories, revision, ids, index = unknown_sex
    release = {"label": "N", "references": release_references(revision, path=path)}
    with ReferenceModel(workers=3).open(release, [], None, repositories) as session:
        pooled = session.project_many(ids)
        alone = []
        for point in ids:
            try:
                alone.append(session.project(point))
            except ModelPointFailure as failure:
                alone.append(failure)

    def plain(outcome):  # a value as its bits
        if isinstance(outcome, ModelPointFailure):
            return "failed", str(outcome)
        return "ok", as_bits(outcome)

    assert [plain(outcome) for outcome in pooled] == [plain(outcome) for outcome in alone]
    assert [kind for kind, _ in map(plain, pooled)] == ["ok", "ok", "failed"]
    assert str(pooled[2]) == f"result_cf raised ValueError: invalid sex in RLV_DE_S.Projection[{index}].sex()"


def test_one_worker_projects_in_the_parent_without_a_pool(monkeypatch, unknown_sex):
    from degelmann.deltarecon.engines import reference_model
    repositories, revision, ids, index = unknown_sex

    def no_pool(*arguments, **options):
        raise AssertionError("one worker starts no pool")

    monkeypatch.setattr(reference_model, "ordered_map", no_pool)
    release = {"label": "N", "references": reference_model.release_references(revision)}
    with reference_model.ReferenceModel(workers=1).open(release, [], None, repositories) as session:
        outcomes = session.project_many(ids)
    assert [isinstance(outcome, ModelPointFailure) for outcome in outcomes] == [False, False, True]
    assert all(outcomes[:2])
    assert str(outcomes[2]) == f"result_cf raised ValueError: invalid sex in RLV_DE_S.Projection[{index}].sex()"
