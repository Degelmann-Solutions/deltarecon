"""The derived change manifest of ``contracts/v3/changes.md``.

A derivation reads the records of two succeeded runs without enabled changes, the older
one first, asks the engine for the history between the revisions their release identities
name, and writes one change manifest: one change per revision on the main line, each with
the change before it as its only prerequisite, realised as a revision. This module knows
no engine and no kind of history; which revision an identity names, what the main line is,
and which class a touched path has are the engine's answers.

- ``stage`` is that of both records, ``base_release`` the label of the older release, and
  ``manifest_id`` is ``history-<older revision>-<newer revision>``.
- ``history.determines`` holds the kinds the engine declares, by name. A kind outside
  them whose references differ between the two release identities is an entry of
  ``history.remainder``, by kind, with the complete references of both sides, each list
  by value and then by the byte hash of the artifact.
- The manifest holds no timestamp and no path, so the same two records give the same
  bytes. The list of changes depends on the two revisions alone.
- A manifest that cannot be derived raises a :class:`~degelmann.deltarecon.documents.Rejection`;
  nothing is written. The output file must not exist and its folder must.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from . import changes as changes_contract
from .documents import CHANGES_SCHEMA, CONTRACT_VERSION, Rejection, write_document
from .replay import RecordedRun, read_recorded_run
from .run import Engine, History, UsageError, repositories_folder

REVISION = "revision"
CLASS_ORDER = ("data", "parameter", "code")


@dataclass
class DeriveResult:
    manifest_path: Path
    manifest: dict = field(repr=False)


def read_derive_input(record_path: Path | str, stages) -> RecordedRun:
    """A recorded run a derivation starts from: succeeded, and without enabled changes.

    The state of a run with enabled changes is no revision of the history.
    """
    recorded = read_recorded_run(Path(record_path), stages)
    if recorded.request["changes"]["enabled"]:
        raise UsageError(f"the run of {recorded.record_path} has enabled changes; a manifest is derived "
                         "from the records of two runs without enabled changes")
    return recorded


def _reference_order(reference: dict):
    artifact = reference.get("artifact")
    # A reference without an artifact stands before one with the same value.
    return (reference["value"], artifact is not None, (artifact or {}).get("sha256", ""),
            (artifact or {}).get("path", ""))


def remainder(older: dict, newer: dict, determines) -> list[dict]:
    """The kinds no revision fixes whose references differ between two release identities."""
    def of_kind(release: dict, kind: str) -> list[dict]:
        return sorted((reference for reference in release["references"] if reference["kind"] == kind),
                      key=_reference_order)

    kinds = {reference["kind"] for release in (older, newer) for reference in release["references"]}
    entries = []
    for kind in sorted(kinds - set(determines)):
        before, after = of_kind(older, kind), of_kind(newer, kind)
        if before != after:
            entries.append({"kind": kind, "from": before, "to": after})
    return entries


def description(message: str, revision: str) -> str:
    """The log message without the line breaks at its end, or the identifier when it is empty."""
    return message.rstrip("\r\n") or revision


def build_manifest(history: History, stage: str, base_release: str, determines, rest: list[dict]) -> dict:
    """The manifest of a history: one change per revision, chained by one prerequisite each."""
    ids = [revision.id for revision in history.revisions]
    if ids and (ids[-1] != history.newer or history.older in ids) or (not ids and history.older != history.newer):
        raise RuntimeError("the engine returns a history that does not lead from the older to the newer revision")
    changes = []
    for index, revision in enumerate(history.revisions):
        unknown = sorted(set(revision.classes) - set(CLASS_ORDER))
        if unknown:
            raise RuntimeError(f"the engine returns a class the changes contract does not define: {unknown[0]}")
        changes.append({
            "id": revision.id,
            "class": [name for name in CLASS_ORDER if name in revision.classes],
            "description": description(revision.message, revision.id),
            "prerequisites": ids[index - 1:index] if index else [],
            "conflicts": [],
            "realisation": {"type": REVISION, "source": history.source, "revision": revision.id},
        })
    return {
        "document": "change_manifest", "contract_version": CONTRACT_VERSION, "stage": stage,
        "manifest_id": f"history-{history.older}-{history.newer}", "base_release": base_release,
        "history": {"source": history.source, "from": history.older, "to": history.newer,
                    "determines": sorted(determines), "remainder": rest},
        "changes": changes,
    }


def derive(older_record: Path | str, newer_record: Path | str, output: Path | str, engine: Engine,
           repositories: Path | None = None) -> DeriveResult:
    """Derive the change manifest between two recorded runs and write it to ``output``."""
    output = Path(output).resolve()
    repositories = repositories_folder(repositories)
    if output.exists():
        raise UsageError(f"{output} exists already; no file is overwritten")
    if not output.parent.is_dir():
        raise UsageError(f"the folder {output.parent} does not exist; the manifest is written into an "
                         "existing folder")
    older = read_derive_input(older_record, engine.stages)
    newer = read_derive_input(newer_record, engine.stages)
    stage = older.record["stage"]
    if newer.record["stage"] != stage:
        raise Rejection("stage_mismatch", f"The older record names the stage {stage}, the newer one "
                        f"the stage {newer.record['stage']}.")
    old_release, new_release = older.record["releases"][0], newer.record["releases"][0]
    history = engine.history(old_release, new_release, repositories)
    manifest = build_manifest(history, stage, old_release["label"], engine.determines,
                              remainder(old_release, new_release, engine.determines))
    changes_contract.check_manifest_rules(manifest)
    write_document(output, manifest, CHANGES_SCHEMA)
    return DeriveResult(output, manifest)
