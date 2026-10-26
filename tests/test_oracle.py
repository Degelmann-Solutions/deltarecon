"""The reproduction oracle: the two published run requests of the reference walk and the SHA-256
of its walk result and of every signature table it writes, under contract version 3.0, and the
archive of the oracle of 2026-10-22, published under contract version 2.0.

The reference walk runs from the start commit of the reference chain of ``delib-history``, which
holds release N on the fixed model, to the newer revision: 32 commits on the main line. The archived
oracle walked the earlier chain from release N to ``ab5dc79``, whose first 32 commits the new chain
repeats one by one on the fixed model; its last three commits changed no result.

The fast tests check the published files: the renewed requests are those of the archive with
contract version 3.0, the engine version of the export path under Python 3.14.9, and the two ends of
the new chain in place of release N and ``ab5dc79``, and the archived files stay well formed. The
reproduction runs both requests and the walk on all 350 model points, and is skipped unless it is
asked for: ``DELTARECON_ORACLE=1``. Besides the renewed hashes it checks every signature table against
the archive. The archived tables were built under 2.0, which paired values by policy month; the present
tables carry projection periods. So each table is rebuilt in policy months from the deviation file of
its step: every row's period gets back the first exported period of its model point in the step's left
state export, the table is derived again from the rows, and its contract version is set back to the
archived ``2.0``. The rebuilt table hashes to the archived digest: the tables are the archived ones,
field for field, apart from ``contract_version`` and the period numbering. The rebuild assumes that
left and right offsets agree for every deviating model point; a hash that matches proves it, since a
moved offset would have paired other values under 2.0. This holds across the move to the new chain
because the fixes keep every result bit for bit, so state k of the new chain gives the bits of state k
of the earlier chain, and the step numbers, run ids and labels are unchanged; a signature table names
no revision. The archived walk result is not compared, because it holds the
hashes of the 2.0 responses and the revisions. The pinned hashes are never rewritten to make a test
pass.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
from pathlib import Path

import pytest

from degelmann.deltarecon.__main__ import main
from degelmann.deltarecon.compare import first_periods, read_result_deviations
from degelmann.deltarecon.documents import RUN_SCHEMA, document_bytes, parse_document, read_document
from degelmann.deltarecon.signature import signature_table

from conftest import CLONE, NEWER, RELEASE_N, REPOSITORIES, ROOT, START, export_coordinates, git, require_clone

ORACLE = ROOT / "oracle"
ARCHIVE = ORACLE / "archive" / "2026-10-22"
ARCHIVED_VERSION = "2.0"
ENGINE_VERSION = "modelx 0.33.0 export, pandas 3.0.6, numpy 2.5.3, Python 3.14.9"
ARCHIVED_ENGINE_VERSION = "modelx 0.33.0, pandas 3.0.6, numpy 2.5.3, Python 3.12.13"
PROFILE = ROOT / "profiles" / "tolerance-bruttobeitrag.json"
REQUESTS = {"n.request.json": ("oracle-n", "N", START), "n1.request.json": ("oracle-n1", "N+1", NEWER)}
# The ends of the archived oracle, release N and the newer revision of the earlier chain.
ARCHIVED_ENDS = {"n.request.json": RELEASE_N,
                 "n1.request.json": "ab5dc790f5bed52f94a4c8fb8d6b710bc31f0a33"}
WALK_RESULT = "walk.result.json"
SUM_LINE = re.compile(r"([0-9a-f]{64})  (walk\.result\.json|step-[0-9]{2}\.compare\.signature-table\.json)")


def listed_hashes(folder: Path = ORACLE) -> dict[str, str]:
    """The file names and hashes of ``SHA256SUMS`` in ``folder``; every line must be well formed."""
    lines = (folder / "SHA256SUMS").read_text("ascii").splitlines()
    hashes = {}
    for line in lines:
        match = SUM_LINE.fullmatch(line)
        assert match, f"not a sha256sum line of a walk file: {line!r}"
        assert match.group(2) not in hashes, f"listed twice: {match.group(2)}"
        hashes[match.group(2)] = match.group(1)
    return hashes


def tables(hashes: dict[str, str]) -> dict[str, str]:
    """The signature tables of a sums file, without the walk result."""
    return {name: digest for name, digest in hashes.items() if name != WALK_RESULT}


def in_policy_months(walk: Path, name: str) -> bytes:
    """The bytes of the signature table ``name`` of the walk folder ``walk`` rebuilt in policy months
    under the archived contract version: the rows of its step's deviation file, each period plus the
    first exported period of its model point in the step's left state export."""
    prefix = name.removesuffix(".signature-table.json")
    result = parse_document((walk / f"{prefix}.result.json").read_bytes())
    request = parse_document((walk / f"{prefix}.request.json").read_bytes())
    deviations = read_result_deviations(result, walk)
    stored = parse_document((walk / name).read_bytes())
    assert stored["contract_version"] == "3.0" and stored == signature_table(result, deviations), name
    left = walk / request["left"]["response"]["path"]
    export = left.parent / parse_document(left.read_bytes())["export"]["artifact"]["path"]
    offsets = first_periods({(point, period) for point, period, _ in export_coordinates(export)})
    rows = [{**row, "period": row["period"] + offsets[row["model_point_id"]]} for row in deviations]
    return document_bytes({**signature_table(result, rows), "contract_version": ARCHIVED_VERSION})


def archive_mismatches(walk: Path) -> list[str]:
    """The signature tables of ``walk`` whose rebuild in policy months does not hash to the archived digest."""
    archived = tables(listed_hashes(ARCHIVE))
    return [name for name, digest in archived.items()
            if hashlib.sha256(in_policy_months(walk, name)).hexdigest() != digest]


def check_request(request: dict, name: str, engine_version: str, revision: str) -> None:
    run_id, label, _ = REQUESTS[name]
    assert request["run_id"] == run_id and request["release"]["label"] == label
    assert request["changes"] == {"enabled": []} and request["selection"] == {"mode": "full"}
    references = {reference["kind"]: reference["value"] for reference in request["release"]["references"]}
    expected = f"git:https://github.com/Degelmann-Solutions/delib-history@{revision}"
    assert {kind: references[kind] for kind in ("code_state", "parameter_set", "input_data")} == \
        dict.fromkeys(("code_state", "parameter_set", "input_data"), expected)
    assert references["engine_version"] == engine_version


@pytest.mark.parametrize("name", sorted(REQUESTS))
def test_published_request_is_a_3_0_run_request_of_its_pinned_revision(name):
    request = read_document(ORACLE / name, RUN_SCHEMA, "run_request")
    assert request["contract_version"] == "3.0"
    check_request(request, name, ENGINE_VERSION, REQUESTS[name][2])


@pytest.mark.parametrize("name", sorted(REQUESTS))
def test_published_request_is_the_archived_one_but_for_the_contract_and_engine_version_and_the_revision(name):
    published = parse_document((ORACLE / name).read_bytes())
    archived = parse_document((ARCHIVE / name).read_bytes())
    archived_bytes = (ARCHIVE / name).read_bytes()
    assert archived_bytes.count(ARCHIVED_ENDS[name].encode()) == 3
    renewed = parse_document(archived_bytes.replace(ARCHIVED_ENGINE_VERSION.encode(), ENGINE_VERSION.encode())
                             .replace(ARCHIVED_ENDS[name].encode(), REQUESTS[name][2].encode()))
    assert renewed != archived
    assert {**published, "contract_version": ARCHIVED_VERSION} == renewed
    assert (ORACLE / name).read_bytes() == document_bytes({**renewed, "contract_version": "3.0"})


@pytest.mark.parametrize("name", sorted(REQUESTS))
def test_archived_request_is_a_2_0_run_request_of_its_pinned_revision(name):
    request = read_document(ARCHIVE / name, RUN_SCHEMA, "run_request")
    assert request["contract_version"] == ARCHIVED_VERSION
    check_request(request, name, ARCHIVED_ENGINE_VERSION, ARCHIVED_ENDS[name])


def test_newer_revision_lies_on_the_main_line_32_commits_after_the_start():
    require_clone(CLONE, NEWER)
    assert START in git(CLONE, "rev-list", "--first-parent", NEWER).decode("ascii").split()
    assert len(git(CLONE, "rev-list", "--first-parent", f"{START}..{NEWER}").split()) == 32


@pytest.mark.parametrize("folder", [ORACLE, ARCHIVE], ids=["published", "archived"])
def test_sums_list_the_walk_result_and_signature_tables_only(folder):
    hashes = listed_hashes(folder)
    assert WALK_RESULT in hashes
    assert len(hashes) > 1
    assert (folder / "REPRODUCTIONS.md").is_file()
    assert PROFILE.is_file()


def test_published_sums_list_the_archived_signature_tables():
    assert set(tables(listed_hashes())) == set(tables(listed_hashes(ARCHIVE)))


def test_archive_holds_the_four_files_of_the_oracle_only():
    assert sorted(path.name for path in ARCHIVE.iterdir()) == \
        ["REPRODUCTIONS.md", "SHA256SUMS", "n.request.json", "n1.request.json"]


@pytest.mark.skipif(os.environ.get("DELTARECON_ORACLE") != "1",
                    reason="the reproduction of the reference walk runs on request: DELTARECON_ORACLE=1")
def test_reference_walk_reproduces_every_published_hash(monkeypatch, tmp_path):
    """Run both published requests, walk between them with the profile, and check every hash, and
    every signature table against the archive."""
    require_clone(CLONE, NEWER)
    monkeypatch.chdir(ROOT)
    records = []
    for name, (run_id, _, _) in sorted(REQUESTS.items()):
        request = tmp_path / run_id / "request.json"
        request.parent.mkdir()
        shutil.copyfile(ORACLE / name, request)
        assert main(["run", str(request), "--repositories", str(REPOSITORIES)]) == 0
        records.append(str(request.parent / "run-record.json"))
    walk = tmp_path / "oracle-walk"
    assert main(["walk", *records, "--tolerance", str(PROFILE), "--output", str(walk),
                 "--repositories", str(REPOSITORIES)]) == 0
    written = {path.name for path in walk.glob("*.signature-table.json")} | {WALK_RESULT}
    hashes = listed_hashes()
    assert set(hashes) == written
    assert {name: hashlib.sha256((walk / name).read_bytes()).hexdigest() for name in hashes} == hashes
    # Each table, rebuilt in policy months with the archived contract version written back, is the
    # archived table byte for byte; the member order is kept, so equal bytes mean equal fields.
    assert set(tables(listed_hashes(ARCHIVE))) == set(tables(hashes))
    assert archive_mismatches(walk) == []
