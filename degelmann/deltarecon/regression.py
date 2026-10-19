"""The regression case: a recorded result checked against another release state.

A regression run takes the record of a succeeded run without enabled changes, runs the
release identity the caller hands in on the selection of the recorded run, and compares
the recorded run, as the left side, with the new run, as the right side, through the
compare procedure of ``contracts/v1/compare.md``. The caller builds the identity: it names
the newer state and the input data of the recorded run. This module knows no engine.

The output folder must not exist. It receives:

- ``recorded/``: request, response, export, and record of the recorded run, byte for byte;
- ``run/``: the new run, a normal run of the run contract;
- ``compare.request.json``, ``compare.result.json``, ``compare.deviations.csv``,
  ``compare.run-record.json``, and ``signature-table.json``: the comparison.

The run id is ``regression-<recorded run id>`` and the compare id ``compare-<that run
id>``; no id depends on a path. Only the run records carry the identity of an execution,
``record_id``. When the new run does not succeed there is no comparison, and its documents
stay: also when the engine cannot restore the release and rejects the run, and when the
run ends with an error.

The recorded run may come from another engine version than the present one: the new run
is run on the present engine, and the compare result names both versions.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from .compare import COMPARE_REQUEST, CompareResult, compare, read_tolerance
from .documents import (CONTRACT_VERSION, RUN_REQUEST, artifact_reference, document_bytes,
                        schema_errors, write_document, write_new)
from .replay import RecordedRun, read_recorded_run
from .run import RECORD_NAME, Engine, RunResult, UsageError, repositories_folder, run_request

RECORDED_FOLDER = "recorded"
RUN_FOLDER = "run"
REQUEST_NAME = "request.json"
COMPARE_REQUEST_NAME = "compare.request.json"


@dataclass
class RegressionResult:
    run: RunResult = field(repr=False)
    comparison: CompareResult | None = field(default=None, repr=False)

    @property
    def no_deviation(self) -> bool:
        return self.comparison is not None and self.comparison.no_deviation


def read_regression_input(record_path: Path | str, stages) -> RecordedRun:
    """The recorded run a regression starts from: succeeded, and without enabled changes."""
    recorded = read_recorded_run(Path(record_path), stages)
    if recorded.request["changes"]["enabled"]:
        raise UsageError("the recorded run has enabled changes; a regression run takes the record of "
                         "a run without enabled changes")
    return recorded


def regression(recorded: RecordedRun, release: dict, output: Path | str, engine: Engine,
               repositories: Path | None = None, tolerance: Path | str | None = None) -> RegressionResult:
    """Run ``release`` on the selection of ``recorded`` and compare the two runs.

    ``recorded`` comes from :func:`read_regression_input`. ``tolerance`` names a tolerance
    file; without it the comparison is exact.
    """
    output = Path(output).resolve()
    repositories = repositories_folder(repositories)
    if output.exists():
        raise UsageError(f"{output} exists already; a regression run overwrites no file")
    if recorded.request["changes"]["enabled"]:
        raise UsageError("the recorded run has enabled changes")
    profile = read_tolerance(tolerance, recorded.response["quantities"])
    run_id = f"regression-{recorded.request['run_id']}"
    request = {
        "document": "run_request", "contract_version": CONTRACT_VERSION, "stage": recorded.record["stage"],
        "run_id": run_id, "release": release, "changes": {"enabled": []},
        "selection": recorded.request["selection"],
    }
    errors = schema_errors(request, RUN_REQUEST)
    if errors:
        raise UsageError(f"the request of the regression run would violate its schema at {errors[0]}")
    folder = recorded.folder
    copies = [recorded.request_ref["path"], recorded.response_ref["path"], recorded.export_ref["path"],
              recorded.record_path.name]
    output.mkdir(parents=True)
    try:
        for relative in dict.fromkeys(copies):
            target = output / RECORDED_FOLDER / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(folder / relative, target)
        (output / RUN_FOLDER).mkdir()
        request_path = output / RUN_FOLDER / REQUEST_NAME
        write_new(request_path, document_bytes(request))
        run = run_request(request_path, engine, repositories)
        if run.outcome != "succeeded":
            return RegressionResult(run)

        compare_request = {
            "document": "compare_request", "contract_version": CONTRACT_VERSION,
            "stage": recorded.record["stage"], "compare_id": f"compare-{run_id}",
            "left": {
                "response": artifact_reference(output, output / RECORDED_FOLDER / recorded.response_ref["path"]),
                "run_record": artifact_reference(output, output / RECORDED_FOLDER / recorded.record_path.name)},
            "right": {"response": artifact_reference(output, run.response_path),
                      "run_record": artifact_reference(output, output / RUN_FOLDER / RECORD_NAME)},
            "tolerance": profile,
        }
        compare_request_path = output / COMPARE_REQUEST_NAME
        write_document(compare_request_path, compare_request, COMPARE_REQUEST)
        return RegressionResult(run, compare(compare_request_path))
    except BaseException:  # also an interruption: leave no folder that blocks the next attempt
        shutil.rmtree(output, ignore_errors=True)
        raise
