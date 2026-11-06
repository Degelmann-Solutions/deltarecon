"""The engine a command loads: ``--engine`` and ``--engine-path``, else ``DELTARECON_ENGINE`` and
``DELTARECON_ENGINE_PATH``, else the reference model; and the protocol module, which imports
the standard library alone.

The engines here are modules written into a temporary folder whose class subclasses the stub
engine, so they need no calculation engine.
"""
from __future__ import annotations

import subprocess
import sys
import textwrap

import pytest

from degelmann.deltarecon import __main__ as command_line
from degelmann.deltarecon import documents, errors, protocol, run
from degelmann.deltarecon.__main__ import DEFAULT_ENGINE, ENGINE_PATH_VARIABLE, ENGINE_VARIABLE

from conftest import ROOT, cli, store, stored, stub_request

REFERENCE_MODULE = "degelmann.deltarecon.engines.reference_model"


@pytest.fixture
def engines(tmp_path, monkeypatch):
    """A folder with the engine modules ``stub_engine_a`` and ``stub_engine_b``. Each class
    ``Engine`` records the worker count it was called with and the module it comes from.

    The import path and the loaded modules are restored afterwards.
    """
    folder = tmp_path / "engines"
    folder.mkdir()
    for name in ("stub_engine_a", "stub_engine_b"):
        (folder / f"{name}.py").write_text(textwrap.dedent(f"""\
            from conftest import StubEngine

            CALLS = []


            class Engine(StubEngine):
                origin = {name!r}

                def __init__(self, workers=None):
                    super().__init__()
                    CALLS.append(workers)
            """), "utf-8")
        monkeypatch.delitem(sys.modules, name, raising=False)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delenv(ENGINE_VARIABLE, raising=False)
    monkeypatch.delenv(ENGINE_PATH_VARIABLE, raising=False)
    yield folder
    for name in ("stub_engine_a", "stub_engine_b"):
        sys.modules.pop(name, None)


def run_world(monkeypatch, world, *options) -> int:
    path = store(world, stub_request(world))
    return cli(monkeypatch, "run", path, "--repositories", world, *options)


def loaded(name: str):
    return sys.modules[name].CALLS


# --- selection ------------------------------------------------------------------------


def test_the_option_loads_the_engine_from_the_engine_path(world, engines, monkeypatch, capsys):
    status = run_world(monkeypatch, world, "--engine", "stub_engine_a:Engine", "--engine-path", engines)
    assert status == 0
    assert "outcome: succeeded" in capsys.readouterr().out
    assert stored(world / "run" / "response.json")["outcome"] == "succeeded"
    assert loaded("stub_engine_a") == [None]  # no --workers: the class is called with no argument


def test_the_variables_load_the_engine_when_no_option_is_given(world, engines, monkeypatch, capsys):
    monkeypatch.setenv(ENGINE_VARIABLE, "stub_engine_a:Engine")
    monkeypatch.setenv(ENGINE_PATH_VARIABLE, str(engines))
    assert run_world(monkeypatch, world) == 0
    assert "outcome: succeeded" in capsys.readouterr().out
    assert stored(world / "run" / "response.json")["outcome"] == "succeeded"
    assert loaded("stub_engine_a") == [None]


def test_the_option_wins_over_the_variable(world, engines, monkeypatch):
    monkeypatch.setenv(ENGINE_VARIABLE, "stub_engine_a:Engine")
    monkeypatch.setenv(ENGINE_PATH_VARIABLE, str(engines / "missing"))
    assert run_world(monkeypatch, world, "--engine", "stub_engine_b:Engine", "--engine-path", engines) == 0
    assert "stub_engine_a" not in sys.modules
    assert loaded("stub_engine_b") == [None]


def test_the_class_is_called_with_the_worker_count_of_the_command(world, engines, monkeypatch):
    assert run_world(monkeypatch, world, "--engine", "stub_engine_a:Engine", "--engine-path", engines,
                     "--workers", "3") == 0
    assert loaded("stub_engine_a") == [3]


def test_an_empty_variable_counts_as_unset(monkeypatch):
    monkeypatch.setenv(ENGINE_VARIABLE, "")
    monkeypatch.setenv(ENGINE_PATH_VARIABLE, "")
    from degelmann.deltarecon.engines.reference_model import ReferenceModel
    assert command_line.engine_class() is ReferenceModel
    assert DEFAULT_ENGINE == f"{REFERENCE_MODULE}:ReferenceModel"


def test_the_selection_is_reset_after_the_command(world, engines, monkeypatch):
    assert run_world(monkeypatch, world, "--engine", "stub_engine_a:Engine", "--engine-path", engines) == 0
    assert command_line.selection == (None, None)


# --- selections that cannot be loaded ---------------------------------------------------


@pytest.mark.parametrize("spec", ["stub_engine_a", ":Engine", "stub_engine_a:", "", ".stub_engine_a:Engine"])
def test_a_selection_of_another_form_is_a_usage_error(world, engines, monkeypatch, capsys, spec):
    assert run_world(monkeypatch, world, "--engine", spec, "--engine-path", engines) == 2
    message = capsys.readouterr().err
    assert message.startswith("error: ") and message.count("\n") == 1
    assert repr(spec) in message and "<module>:<class>" in message
    assert not (world / "run" / "response.json").exists()


@pytest.mark.parametrize("spec, named", [("no_such_engine_module:Engine", "'no_such_engine_module'"),
                                         ("stub_engine_a:NoSuchClass", "'NoSuchClass'")])
def test_a_missing_module_or_class_is_a_usage_error(world, engines, monkeypatch, capsys, spec, named):
    assert run_world(monkeypatch, world, "--engine", spec, "--engine-path", engines) == 2
    message = capsys.readouterr().err
    assert message.startswith("error: ") and message.count("\n") == 1
    assert repr(spec) in message and named in message
    assert not (world / "run" / "response.json").exists()


@pytest.mark.parametrize("spec", ["os:sep", "os:path"])
def test_an_attribute_that_is_not_a_class_is_a_usage_error(world, engines, monkeypatch, capsys, spec):
    assert run_world(monkeypatch, world, "--engine", spec) == 2
    message = capsys.readouterr().err
    assert message.startswith("error: ") and message.count("\n") == 1
    assert repr(spec) in message and "is not a class" in message
    assert not (world / "run" / "response.json").exists()


def test_a_request_with_a_bad_selection_is_a_usage_error_before_the_revision_is_read(world, engines, monkeypatch,
                                                                                    capsys):
    output = world / "request" / "request.json"
    assert cli(monkeypatch, "request", "--revision", "0" * 40, "--label", "N", "--run-id", "run-x",
               "--output", output, "--engine", "nomod:X") == 2
    message = capsys.readouterr().err
    assert message.startswith("error: ") and "'nomod:X'" in message
    assert not output.exists()


def test_an_engine_path_already_on_the_import_path_moves_to_its_front(engines, monkeypatch):
    sys.path.append(str(engines))
    assert command_line.engine_class("stub_engine_a:Engine", str(engines)).origin == "stub_engine_a"
    assert sys.path[0] == str(engines) and sys.path.count(str(engines)) == 1


def test_a_variable_that_names_a_missing_module_is_a_usage_error(world, engines, monkeypatch, capsys):
    monkeypatch.setenv(ENGINE_VARIABLE, "no_such_engine_module:Engine")
    assert run_world(monkeypatch, world) == 2
    assert "'no_such_engine_module:Engine'" in capsys.readouterr().err
    assert not (world / "run" / "response.json").exists()


def test_an_engine_path_that_is_not_a_folder_is_a_usage_error(world, engines, monkeypatch, capsys):
    missing = engines / "missing"
    assert run_world(monkeypatch, world, "--engine", "stub_engine_a:Engine", "--engine-path", missing) == 2
    message = capsys.readouterr().err
    assert message.startswith("error: ") and repr(str(missing)) in message
    assert not (world / "run" / "response.json").exists()


@pytest.mark.parametrize("command", ["request", "run", "replay", "regression", "derive", "walk", "search"])
def test_every_command_that_uses_an_engine_takes_the_options(command, capsys):
    with pytest.raises(SystemExit):
        command_line.main([command, "--help"])
    usage = capsys.readouterr().out
    assert "--engine MODULE:CLASS" in usage and "--engine-path DIR" in usage


@pytest.mark.parametrize("command", ["compare", "quickstart"])
def test_compare_and_quickstart_take_no_engine_option(command, capsys):
    with pytest.raises(SystemExit):
        command_line.main([command, "--help"])
    assert "--engine" not in capsys.readouterr().out


# --- lazy loading ------------------------------------------------------------------------


def test_parsing_and_compare_load_no_engine(tmp_path):
    """In a fresh process, ``compare`` gives the same status and output with ``DELTARECON_ENGINE``
    naming a missing module as without it, and imports no engine module."""
    script = textwrap.dedent(f"""\
        import os, sys
        if sys.argv[1] == "set":
            os.environ[{ENGINE_VARIABLE!r}] = "no_such_engine_module:Engine"
        from degelmann.deltarecon.__main__ import main
        status = main(["compare", {str(tmp_path / "compare.request.json")!r}])
        print(status, {REFERENCE_MODULE!r} in sys.modules, "modelx" in sys.modules,
              "no_such_engine_module" in sys.modules)
        """)
    done = {mode: subprocess.run([sys.executable, "-c", script, mode], capture_output=True, text=True,
                                 cwd=ROOT, check=True) for mode in ("unset", "set")}
    assert (done["set"].stdout, done["set"].stderr) == (done["unset"].stdout, done["unset"].stderr)
    assert done["set"].stdout.strip().splitlines()[-1].endswith(" False False False")
    assert "no_such_engine_module" not in done["set"].stderr


# --- the protocol module -------------------------------------------------------------------


def test_the_protocol_module_imports_the_standard_library_alone():
    script = ("import sys; import degelmann.deltarecon.protocol; "
              "print(sorted(m for m in sys.modules if m.split('.')[0] in "
              "('jsonschema', 'modelx', 'referencing', 'pandas', 'numpy', 'dulwich')"
              " or m in ('degelmann.deltarecon.run', 'degelmann.deltarecon.documents')))")
    done = subprocess.run([sys.executable, "-I", "-c", script], capture_output=True, text=True, cwd=ROOT,
                          check=True)
    assert done.stdout.strip() == "[]"


def test_the_compared_quantities_are_those_the_reference_model_declares():
    """The core copy of the quantities a compare checks against cannot drift from the adapter's."""
    from degelmann.deltarecon.compare import COMPARED_QUANTITIES
    from degelmann.deltarecon.engines.reference_model import STAGE_QUANTITIES, ReferenceModel
    assert list(ReferenceModel.stages) == ["liability_cashflow"]
    assert tuple(ReferenceModel.stages["liability_cashflow"]) == COMPARED_QUANTITIES["liability_cashflow"]
    assert tuple(STAGE_QUANTITIES["liability_cashflow"]) == COMPARED_QUANTITIES["liability_cashflow"]


def test_each_moved_name_is_one_class_wherever_it_is_imported_from():
    from degelmann.deltarecon.engines import reference_model
    assert documents.Rejection is protocol.Rejection is run.Rejection is reference_model.Rejection
    assert errors.UsageError is protocol.UsageError is run.UsageError is reference_model.UsageError
    for name in ("SCRATCH_PREFIX", "Engine", "Session", "ModelPointFailure", "Revision", "History"):
        assert getattr(run, name) is getattr(protocol, name)
