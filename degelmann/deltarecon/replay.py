"""Replay of a recorded run.

A replay checks the run record (rules 15 to 17 of ``contracts/v3/run.md``) and the
recorded result (rules 6 to 13), repeats the run in the folder ``replay/`` beside the
record, and compares the recorded run, as the left side, with the repeated run, as the
right side, through the compare procedure of ``contracts/v3/compare.md``. Without a
tolerance profile the comparison is exact.

- The replay repeats runs recorded under contract version 2.0 or 3.0. A run record written
  under 1.0 is read by ``regression``, ``derive``, ``walk``, and ``search``, but it is not
  replayed: the replay rejects it with ``unsupported_version`` (``contracts/v3/README.md``,
  "Version compatibility").

- The replay writes ``replay-compare.request.json``, ``replay-compare.result.json``, and,
  when the outcome of the comparison is ``compared``, ``replay-compare.deviations.csv``
  beside the record, and a run record with the procedure type ``replay`` that lists them.
  It writes no run record of the comparison and no signature table.
- The outcome is ``reproduced_exactly``, ``reproduced_at_decimals``, or
  ``reproduced_within_tolerances``, by what the profile holds, when the comparison reports
  no deviation. Otherwise it is ``not_reproduced``: also when the repeated run does not
  succeed or the comparison is not ``compared``. Deviating coordinates are in the
  deviation file.
- A recorded run with the outcome ``error`` has no export. It is repeated, nothing is
  compared, and it is ``reproduced_exactly`` when the new response is byte for byte the
  recorded one, else ``not_reproduced``. The replay record lists the new response only.
- A rejected replay raises a :class:`~degelmann.deltarecon.documents.Rejection` and writes nothing.
  The replay stays strict: the engine resolves the recorded release identity as it is, so
  the run is repeated on the computation path its engine version names.
"""
from __future__ import annotations

import shutil
from dataclasses import dataclass, field
from pathlib import Path

from . import changes as changes_contract
from .compare import (COMPARE_REQUEST, CompareResult, compare, compare_request_document, no_deviation,
                      read_tolerance)
from .documents import (CHANGES_SCHEMA, CONTRACT_VERSION, RECORD_SCHEMA, RUN_REQUEST, RUN_SCHEMA,
                        Rejection, artifact_reference, check_artifact, copy_files, document_bytes,
                        parse_document, read_document, same_release, write_document)
from .export import check_export
from .run import (RECORD_NAME, STAGE_QUANTITIES, Engine, UsageError, quantity_errors,
                  repositories_folder, run_record, run_request)

# The contract versions of the run records a replay repeats; a 1.0 record is not replayed.
REPLAY_VERSIONS = ("2.0", "3.0")
REPLAY_FOLDER = "replay"
REPLAY_RECORD_NAME = "replay-record.json"
REPLAY_COMPARE_REQUEST_NAME = "replay-compare.request.json"
REPLAY_COMPARE_RESULT_NAME = "replay-compare.result.json"
REPLAY_DEVIATIONS_NAME = "replay-compare.deviations.csv"


@dataclass
class RecordedRun:
    """A recorded run as its record describes it, after rules 15 to 17 and 6 to 13.

    A run with the outcome ``error`` has no export: ``export_ref`` is ``None`` and
    ``values`` is empty.
    """

    record_path: Path
    record: dict = field(repr=False)
    request: dict = field(repr=False)
    response: dict = field(repr=False)
    manifest: dict | None = field(repr=False)
    request_ref: dict
    response_ref: dict
    export_ref: dict | None
    manifest_ref: dict | None
    values: dict = field(repr=False)

    @property
    def folder(self) -> Path:
        return self.record_path.parent

    def files(self) -> list[str]:
        """Request, response, export, and record of a succeeded run, relative to its folder."""
        return [self.request_ref["path"], self.response_ref["path"], self.export_ref["path"], self.record_path.name]


@dataclass
class ReplayResult:
    """What a replay found. Without a comparison, the replay of an ``error`` run, the
    compare members are ``None``."""

    outcome: str
    record_path: Path
    record: dict = field(repr=False)
    compare_result: dict | None = field(repr=False)
    compare_request_path: Path | None
    compare_result_path: Path | None
    comparison: CompareResult | None = field(default=None, repr=False)
    response_path: Path | None = None  # the response of the repeated run


def _one(entries: list[dict], role: str, required: bool = True) -> dict | None:
    found = [entry["artifact"] for entry in entries if entry["role"] == role]
    if len(found) > 1 or (required and not found):
        raise Rejection("schema_violation",
                        f"The record of a run lists exactly one artifact with the role {role}.")
    return found[0] if found else None


def check_repeated(request: dict, response: dict) -> None:
    """Rule 6 of the run contract: the response repeats stage, run id, release, changes, and selection."""
    if response["stage"] != request["stage"]:
        raise Rejection("stage_mismatch", "The response names another stage than its request.")
    same_changes = (set(response["changes"]["enabled"]) == set(request["changes"]["enabled"])
                    and response["changes"].get("manifest") == request["changes"].get("manifest")
                    and set(response["changes"].get("hold", [])) == set(request["changes"].get("hold", []))
                    and ("hold" in response["changes"]) == ("hold" in request["changes"]))
    same_selection = (response["selection"]["mode"] == request["selection"]["mode"]
                      and set(response["selection"].get("model_point_ids", []))
                      == set(request["selection"].get("model_point_ids", [])))
    if (response["run_id"] != request["run_id"] or not same_changes or not same_selection
            or not same_release(response["release"], request["release"])):
        raise Rejection("request_mismatch", "The response does not repeat the run id, release "
                        "identity, change set, and selection of its request.")


def check_response(request: dict, response: dict, folder: Path) -> dict:
    """Rules 6 to 13 of the run contract for a succeeded response. Return the export values."""
    check_repeated(request, response)  # rule 6
    problem = quantity_errors(response["stage"], [q["name"] for q in response["quantities"]])  # rule 7
    if problem:
        raise Rejection("quantity_mismatch", f"The response declares its quantities wrongly: {problem}.")
    export_path = check_artifact(folder, response["export"]["artifact"])  # rule 8
    return check_export(response, export_path)  # rules 9 to 13


def read_recorded_run(record_path: Path, stages, allow_error: bool = False) -> RecordedRun:
    """Read the record of a succeeded run and check it and the recorded result.

    ``stages`` are the stages the engine supports. A record of another procedure than a
    run, or of a run that has not succeeded, is a usage error; a broken rule a rejection.
    ``allow_error`` also takes the record of a run with the outcome ``error``; only the
    replay sets it.
    """
    record_path = Path(record_path).resolve()
    folder = record_path.parent
    if not record_path.is_file():
        raise UsageError(f"no run record at {record_path}")
    record = read_document(record_path, RECORD_SCHEMA)
    stage = record["stage"]
    if stage not in stages or stage not in STAGE_QUANTITIES:
        raise Rejection("unsupported_stage", f"The stage {stage} is not supported.")
    outcomes = ("succeeded", "error") if allow_error else ("succeeded",)
    if record["procedure"]["type"] != "run" or record["outcome"] not in outcomes:
        taken = "a succeeded run or of one that ended with an error" if allow_error else "a succeeded run"
        raise UsageError(f"only the record of {taken} can be used, not one of the "
                         f"procedure {record['procedure']['type']} with the outcome {record['outcome']}")

    # Rule 15: every artifact of the record exists and has the stated hash.
    for entry in record["inputs"] + record["outputs"]:
        check_artifact(folder, entry["artifact"])
    request_ref = _one(record["inputs"], "request")
    manifest_ref = _one(record["inputs"], "change_manifest", required=False)
    response_ref = _one(record["outputs"], "response")
    export_ref = _one(record["outputs"], "export", required=record["outcome"] == "succeeded")
    if "/" in request_ref["path"] or "/" in response_ref["path"]:
        raise UsageError("the request and the response of the run must sit beside its record")

    # Rule 16: the record and the documents it lists name one stage.
    request = read_document(folder / request_ref["path"], RUN_REQUEST)
    response = read_document(folder / response_ref["path"], RUN_SCHEMA, "run_response")
    manifest = read_document(folder / manifest_ref["path"], CHANGES_SCHEMA) if manifest_ref else None
    for document in (request, response, manifest):
        if document is not None and document.get("stage") != stage:
            raise Rejection("stage_mismatch", "The record and a document it lists name different stages.")

    # Rule 17: the record holds the release identity of the listed request.
    if len(record["releases"]) != 1 or not same_release(record["releases"][0], request["release"]):
        raise Rejection("request_mismatch",
                        "The record holds another release identity than the request it lists.")
    other_manifest = bool(request["changes"]["enabled"]) and request["changes"]["manifest"] != manifest_ref
    if record["outcome"] == "error":
        if response["outcome"] != "error" or export_ref is not None or other_manifest:
            raise Rejection("request_mismatch", "The record lists other artifacts than its request and "
                            "its response name, or the response is not that of a run with an error.")
        check_repeated(request, response)  # rule 6
        return RecordedRun(record_path, record, request, response, manifest, request_ref, response_ref,
                           None, manifest_ref, {})
    if response["outcome"] != "succeeded" or response["export"]["artifact"] != export_ref or other_manifest:
        raise Rejection("request_mismatch", "The record lists other artifacts than its request and "
                        "its response name, or the response is not that of a succeeded run.")
    values = check_response(request, response, folder)
    return RecordedRun(record_path, record, request, response, manifest, request_ref, response_ref,
                       export_ref, manifest_ref, values)


def reproduction(result: dict, folder: Path) -> str:
    """The outcome of a replay, from the compare result stored in ``folder`` and what its
    tolerance profile holds."""
    if not no_deviation(result, folder):
        return "not_reproduced"
    entries = result["tolerance"]["per_quantity"].values()
    if any(part > 0 for entry in entries for bound in (entry["upper"], entry["lower"])
           for part in bound.values()):
        return "reproduced_within_tolerances"
    if any("decimals" in entry for entry in entries):
        return "reproduced_at_decimals"
    return "reproduced_exactly"


def replay(record_path: Path, engine: Engine, repositories: Path | None = None,
           tolerance: Path | str | None = None) -> ReplayResult:
    """Repeat the run a run record describes and state whether it is reproduced.

    ``tolerance`` names a tolerance file; without it the comparison is exact.
    """
    record_path = Path(record_path).resolve()
    repositories = repositories_folder(repositories)
    folder = record_path.parent
    if not record_path.is_file():
        raise UsageError(f"no run record at {record_path}")
    replay_dir, replay_record_path = folder / REPLAY_FOLDER, folder / REPLAY_RECORD_NAME
    compare_request_path = folder / REPLAY_COMPARE_REQUEST_NAME
    compare_result_path = folder / REPLAY_COMPARE_RESULT_NAME
    deviations_path = folder / REPLAY_DEVIATIONS_NAME
    targets = (replay_dir, replay_record_path, compare_request_path, compare_result_path, deviations_path)
    for target in targets:
        if target.exists():
            raise UsageError(f"{target} exists already; a replay overwrites no file")
    if tolerance is not None and not Path(tolerance).is_file():
        raise UsageError(f"no tolerance file at {tolerance}")

    recorded = read_recorded_run(record_path, engine.stages, allow_error=True)
    if recorded.record["contract_version"] not in REPLAY_VERSIONS:
        raise Rejection("unsupported_version",
                        f"The replay repeats only runs recorded under contract version "
                        f"{' or '.join(REPLAY_VERSIONS)}, not {recorded.record['contract_version']}.")
    record, request, manifest = recorded.record, recorded.request, recorded.manifest
    request_ref, manifest_ref = recorded.request_ref, recorded.manifest_ref
    failed_before = recorded.response["outcome"] == "error"
    profile = None if failed_before else read_tolerance(tolerance, recorded.response["quantities"])

    # What the repeated run needs is checked before anything is written. A rejection
    # refuses the replay. For a run that ended with an error, any other exception of the
    # engine is left to the repeated run, which records it as its outcome.
    try:
        engine.resolve(request["release"], repositories)
    except (Rejection, UsageError):
        raise
    except Exception:
        if not failed_before:
            raise
    copies = [request_ref["path"]]
    if request["changes"]["enabled"]:
        manifest_path = folder / manifest_ref["path"]
        copies.append(manifest_ref["path"])
        enabled = set(request["changes"]["enabled"])
        for change in manifest["changes"]:
            if change["id"] not in enabled:  # the run reads no file of a change that is not enabled
                continue
            for artifact in changes_contract.artifacts(change["realisation"]):
                stored = check_artifact(manifest_path.parent, artifact)
                copies.append(stored.relative_to(folder).as_posix())

    # The repeated run is a normal, self-contained run in its own folder.
    replay_dir.mkdir()
    try:
        copy_files(folder, replay_dir, copies)
        result = run_request(replay_dir / request_ref["path"], engine, repositories)
        if failed_before:
            return _replay_of_an_error(recorded, result, replay_record_path)

        # The recorded run is the left side, the repeated run the right side.
        compare_request = compare_request_document(
            record["stage"], f"compare-replay-{request['run_id']}",
            (dict(recorded.response_ref), artifact_reference(folder, record_path)),
            (artifact_reference(folder, result.response_path), artifact_reference(folder, replay_dir / RECORD_NAME)),
            profile)
        write_document(compare_request_path, compare_request, COMPARE_REQUEST)
        compared = compare(compare_request_path, result_name=REPLAY_COMPARE_RESULT_NAME,
                           record_name=None, signature_name=None, deviations_name=REPLAY_DEVIATIONS_NAME)
        outcome = reproduction(compared.result, folder)

        outputs = [{"role": "response", "artifact": artifact_reference(folder, result.response_path)}]
        if result.export_path is not None:
            outputs.append({"role": "export", "artifact": artifact_reference(folder, result.export_path)})
        outputs.append({"role": "run_record", "artifact": artifact_reference(folder, replay_dir / RECORD_NAME)})
        outputs.append({"role": "compare_request",
                        "artifact": artifact_reference(folder, compare_request_path)})
        outputs.append({"role": "compare_result",
                        "artifact": artifact_reference(folder, compare_result_path)})
        if compared.deviations_path is not None:
            outputs.append({"role": "deviations", "artifact": artifact_reference(folder, deviations_path)})
        replay_record = run_record(
            record["stage"], "replay", outcome,
            [{"role": "run_record", "artifact": artifact_reference(folder, record_path)}],
            record["releases"], result.record["parameters"], outputs)
        write_document(replay_record_path, replay_record, RECORD_SCHEMA)
    except BaseException:  # also an interruption: leave nothing that blocks the next replay
        shutil.rmtree(replay_dir, ignore_errors=True)
        for target in (replay_record_path, compare_request_path, compare_result_path, deviations_path):
            target.unlink(missing_ok=True)
        raise
    return ReplayResult(outcome, replay_record_path, replay_record, compared.result,
                        compare_request_path, compare_result_path, compared, result.response_path)


def _replay_of_an_error(recorded: RecordedRun, result, replay_record_path: Path) -> ReplayResult:
    """Write the replay record of a run that ended with an error. Nothing is compared.

    The repeated response must equal the recorded one byte for byte. For a run recorded under an
    earlier version the two may differ in ``contract_version`` only: the recorded version is written
    into the repeated response before the bytes are compared.
    """
    folder = recorded.folder
    repeated = result.response_path.read_bytes()
    stored = (folder / recorded.response_ref["path"]).read_bytes()
    version = recorded.response["contract_version"]
    if version != CONTRACT_VERSION:
        repeated = document_bytes({**parse_document(repeated), "contract_version": version})
    same = repeated == stored
    outcome = "reproduced_exactly" if same else "not_reproduced"
    replay_record = run_record(
        recorded.record["stage"], "replay", outcome,
        [{"role": "run_record", "artifact": artifact_reference(folder, recorded.record_path)}],
        recorded.record["releases"], result.record["parameters"],
        [{"role": "response", "artifact": artifact_reference(folder, result.response_path)}])
    write_document(replay_record_path, replay_record, RECORD_SCHEMA)
    return ReplayResult(outcome, replay_record_path, replay_record, None, None, None, None,
                        result.response_path)
