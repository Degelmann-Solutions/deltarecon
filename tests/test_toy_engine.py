"""The toy engine of ``examples/toy_engine``: an engine with two stages, built against the protocol
module alone, whose history is a folder and not a Git repository.

Each stage runs through ``request``, ``run``, ``regression``, ``compare``, and ``search`` on the
command line, with the engine loaded through ``--engine`` and ``--engine-path`` and its default
repositories folder, the history beside the module.
"""
from __future__ import annotations

import ast
import csv
import json
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from degelmann.deltarecon.__main__ import ENGINE_PATH_VARIABLE, ENGINE_VARIABLE, main
from degelmann.deltarecon.compare import compare_request_document
from degelmann.deltarecon.documents import artifact_reference, document_bytes

from conftest import ROOT, folder_hashes, stored

TOY = ROOT / "examples" / "toy_engine"
ENGINE = ["--engine", "toy_engine:ToyEngine", "--engine-path", "examples/toy_engine"]
REFERENCE_MODULE = "degelmann.deltarecon.engines.reference_model"
# The quantity each stage is searched on, and the revisions that change it between r1 and r5.
TARGETS = {"toy_premium": ("premium", {"r2", "r4"}), "toy_claims": ("expected_claims", {"r2", "r4", "r5"})}
QUANTITIES = {"toy_premium": [{"name": "policies", "unit": "policies"}, {"name": "premium", "unit": "EUR"}],
              "toy_claims": [{"name": "expected_claims", "unit": "EUR"}]}
# Exit status of each command of the walkthrough: request and run of r1 and r5, a regression and a
# comparison that find deviations, and a search whose two ends are reproduced.
STATUSES = [0, 0, 0, 0, 1, 1, 0]


def walkthrough(folder: Path, stage: str) -> list[int]:
    """The five commands of one stage through ``main``, from the root of the checkout, without
    ``--repositories``. Return the exit status of each."""
    statuses = []
    for revision in ("r1", "r5"):
        request = folder / revision / "request.json"
        statuses.append(main(["request", "--revision", revision, "--stage", stage, "--label", revision,
                              "--run-id", f"run-{revision}", "--output", str(request), *ENGINE]))
        statuses.append(main(["run", str(request), *ENGINE]))
    statuses.append(main(["regression", str(folder / "r1" / "run-record.json"), "--revision", "r5",
                          "--output", str(folder / "regression"), *ENGINE]))
    sides = [tuple(artifact_reference(folder, folder / revision / name) for name in ("response.json", "run-record.json"))
             for revision in ("r1", "r5")]
    compare_path = folder / "compare.request.json"
    compare_path.write_bytes(document_bytes(compare_request_document(stage, f"compare-{stage}", *sides,
                                                                     {"per_quantity": {}})))
    statuses.append(main(["compare", str(compare_path)]))
    statuses.append(main(["search", str(folder / "r1" / "run-record.json"), str(folder / "r5" / "run-record.json"),
                          "--quantity", TARGETS[stage][0], "--output", str(folder / "search"), *ENGINE]))
    return statuses


@pytest.fixture
def toy(monkeypatch):
    """The working directory is the root of the checkout; the import path, the toy module, and the
    history are as before afterwards."""
    monkeypatch.chdir(ROOT)
    monkeypatch.setattr(sys, "path", list(sys.path))
    monkeypatch.delitem(sys.modules, "toy_engine", raising=False)
    monkeypatch.delenv(ENGINE_VARIABLE, raising=False)
    monkeypatch.delenv(ENGINE_PATH_VARIABLE, raising=False)
    before = folder_hashes(TOY / "history")
    yield
    sys.modules.pop("toy_engine", None)
    assert folder_hashes(TOY / "history") == before


def expected_rows(revision: str, stage: str) -> list[list[str]]:
    """The export rows the formulas of DOMAIN.md give for the files of ``revision``, as text."""
    history = TOY / "history" / revision
    q = float((history / "parameters.csv").read_text("utf-8").splitlines()[1].split(",")[1])
    f = {"plain": 1.0, "loaded": 1.05}[json.loads((history / "rules.json").read_text("utf-8"))["claims"]]
    with open(history / "points.csv", newline="", encoding="utf-8") as stream:
        points = sorted(csv.DictReader(stream), key=lambda point: point["id"])
    rows = []
    for point in points:
        for t in range(int(point["term"])):
            values = {"policies": (1 - q) ** t, "premium": float(point["premium"]) * (1 - q) ** t,
                      "expected_claims": float(point["sum_insured"]) * q * (1 - q) ** t * f}
            rows.append([point["id"], str(t), *(repr(values[quantity["name"]]) for quantity in QUANTITIES[stage])])
    return rows


def export_rows(path: Path) -> list[list[str]]:
    with open(path, newline="", encoding="utf-8") as stream:
        rows = list(csv.reader(stream))[1:]
    return [[point, period, *(repr(float(value)) for value in values)] for point, period, *values in rows]


@pytest.mark.parametrize("stage", list(TARGETS))
def test_each_stage_runs_through_the_five_commands(toy, tmp_path, capsys, stage):
    folder = tmp_path / stage
    assert walkthrough(folder, stage) == STATUSES
    printed = capsys.readouterr().out
    assert "regression: " in printed and "deviating coordinates" in printed
    for revision in ("r1", "r5"):
        request = stored(folder / revision / "request.json")
        assert request["stage"] == stage
        assert request["release"]["references"] == [
            {"kind": "code_state", "value": f"toy:{revision}"}, {"kind": "parameter_set", "value": f"toy:{revision}"},
            {"kind": "input_data", "value": f"toy:{revision}"}, {"kind": "engine_version", "value": "toy-engine 1"}]
        response = stored(folder / revision / "response.json")
        assert response["outcome"] == "succeeded"
        assert response["domain_reference"] == {"id": f"deltarecon-examples/{stage}", "version": "1"}
        assert response["time_basis"] == {"id": "projection_year"}
        assert response["quantities"] == QUANTITIES[stage]
        assert export_rows(folder / revision / "results.csv") == expected_rows(revision, stage)
    # The regression runs r5 on the input data of the recorded run, r1.
    regressed = stored(folder / "regression" / "run" / "request.json")
    assert [r["value"] for r in regressed["release"]["references"]] == ["toy:r5", "toy:r5", "toy:r1", "toy-engine 1"]
    for result in (folder / "regression" / "compare.result.json", folder / "compare.result.json"):
        compared = stored(result)
        assert compared["outcome"] == "compared" and compared["deviations"]
    search = stored(folder / "search" / "search.result.json")
    assert search["ends"]["zero"]["outcome"] == search["ends"]["n"]["outcome"] == "reproduced"
    assert search["target"]["quantities"] == [TARGETS[stage][0]]
    contributing = {revision for entry in search["contributions"] for revision in entry["revisions"]
                    if any(c["contributes"] for c in entry["contributions"])}
    assert contributing == TARGETS[stage][1]
    # The classes of each revision are those of the files it changes; r3 changes code without effect.
    manifest = stored(folder / "search" / search["manifest"]["path"])
    assert [(change["id"], change["class"]) for change in manifest["changes"]] == [
        ("r2", ["parameter"]), ("r3", ["code"]), ("r4", ["data"]), ("r5", ["code"])]


def test_the_toy_engine_loads_no_reference_model(tmp_path):
    """In a fresh process, the walkthrough of each stage loads neither modelx nor the reference model."""
    script = textwrap.dedent(f"""\
        import json, sys
        from pathlib import Path
        sys.path.insert(0, {str(ROOT / "tests")!r})
        from test_toy_engine import TARGETS, walkthrough
        statuses = [walkthrough(Path({str(tmp_path)!r}) / stage, stage) for stage in TARGETS]
        print(json.dumps([statuses, "modelx" in sys.modules, {REFERENCE_MODULE!r} in sys.modules]))
        """)
    done = subprocess.run([sys.executable, "-c", script], capture_output=True, text=True, cwd=ROOT, check=True)
    assert json.loads(done.stdout.strip().splitlines()[-1]) == [[STATUSES, STATUSES], False, False]


@pytest.mark.parametrize("stage", list(TARGETS))
@pytest.mark.parametrize("options, status, printed", [
    (("--revision", "r9"), 1, "request: rejected\ndiagnostic: unknown_reference: "),
    (("--revision", "r1", "--engine-option", "x=y"), 2, "error: the toy engine takes no engine option"),
], ids=["unknown-revision", "engine-option"])
def test_a_request_the_toy_engine_refuses_writes_nothing(toy, tmp_path, capsys, stage, options, status, printed):
    output = tmp_path / "refused" / "request.json"
    assert main(["request", *options, "--stage", stage, "--label", "N", "--run-id", "run-x",
                 "--output", str(output), *ENGINE]) == status
    captured = capsys.readouterr()
    assert (captured.out if status == 1 else captured.err).startswith(printed)
    assert not output.parent.exists()


def test_an_enabled_revision_the_history_does_not_hold_does_not_apply(toy):
    """Every enabled revision change is checked, not only the last: the first one that names no
    revision of the history is rejected with ``invalid_manifest``."""
    from degelmann.deltarecon.__main__ import engine_class
    from degelmann.deltarecon.protocol import Rejection

    engine = engine_class("toy_engine:ToyEngine", "examples/toy_engine")()
    repositories = engine.repositories_folder(None)
    release = engine.describe("toy_premium", "N", "r1", {}, repositories)
    enabled = [{"id": change_id, "realisation": {"type": "revision", "source": "git", "revision": revision}}
               for change_id, revision in (("c1", "r2"), ("c2", "r9"), ("c3", "r4"))]
    with pytest.raises(Rejection) as raised:
        with engine.open("toy_premium", release, enabled, None, repositories):
            pass
    assert (raised.value.code, raised.value.change_ids) == ("invalid_manifest", ["c2"])


def test_the_toy_engine_imports_the_protocol_module_alone():
    """Of DeltaRecon it imports only ``degelmann.deltarecon.protocol``, else the standard library,
    and never ``conftest``."""
    imported = []
    for node in ast.walk(ast.parse((TOY / "toy_engine.py").read_text("utf-8"))):
        if isinstance(node, ast.Import):
            imported += [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            assert node.level == 0, ast.unparse(node)
            imported.append(node.module)
    ours = {name for name in imported if name == "degelmann" or name.startswith("degelmann.")}
    assert ours == {"degelmann.deltarecon.protocol"}
    others = {name.split(".")[0] for name in imported} - {"degelmann"}
    assert "conftest" not in others
    assert others <= set(sys.stdlib_module_names) | {"__future__"}, others - set(sys.stdlib_module_names)
