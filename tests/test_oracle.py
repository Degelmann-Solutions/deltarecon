"""The reproduction oracle: the two published run requests of the reference walk and the SHA-256
of its walk result and of every signature table it writes.

The fast tests check the published files. The reproduction runs both requests and the walk, about
an hour on all 350 model points, and is skipped unless it is asked for: ``DELTARECON_ORACLE=1``.
The pinned hashes are never rewritten to make a test pass.
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil

import pytest

from degelmann.deltarecon.__main__ import main
from degelmann.deltarecon.documents import RUN_SCHEMA, read_document

from conftest import CLONE, RELEASE_N, REPOSITORIES, ROOT, git, require_clone

ORACLE = ROOT / "oracle"
PROFILE = ROOT / "profiles" / "tolerance-bruttobeitrag.json"
NEWER = "ab5dc790f5bed52f94a4c8fb8d6b710bc31f0a33"  # the newer revision of the reference walk
REQUESTS = {"n.request.json": ("oracle-n", "N", RELEASE_N), "n1.request.json": ("oracle-n1", "N+1", NEWER)}
SUM_LINE = re.compile(r"([0-9a-f]{64})  (walk\.result\.json|step-[0-9]{2}\.compare\.signature-table\.json)")


def listed_hashes() -> dict[str, str]:
    """The file names and hashes of ``oracle/SHA256SUMS``; every line must be well formed."""
    lines = (ORACLE / "SHA256SUMS").read_text("ascii").splitlines()
    hashes = {}
    for line in lines:
        match = SUM_LINE.fullmatch(line)
        assert match, f"not a sha256sum line of a walk file: {line!r}"
        assert match.group(2) not in hashes, f"listed twice: {match.group(2)}"
        hashes[match.group(2)] = match.group(1)
    return hashes


@pytest.mark.parametrize("name", sorted(REQUESTS))
def test_published_request_is_a_2_0_run_request_of_its_pinned_revision(name):
    run_id, label, revision = REQUESTS[name]
    request = read_document(ORACLE / name, RUN_SCHEMA, "run_request")
    assert request["contract_version"] == "2.0"
    assert request["run_id"] == run_id and request["release"]["label"] == label
    assert request["changes"] == {"enabled": []} and request["selection"] == {"mode": "full"}
    references = {reference["kind"]: reference["value"] for reference in request["release"]["references"]}
    expected = f"git:https://github.com/Degelmann-Solutions/delib-history@{revision}"
    assert {kind: references[kind] for kind in ("code_state", "parameter_set", "input_data")} == \
        dict.fromkeys(("code_state", "parameter_set", "input_data"), expected)
    assert references["engine_version"] == "modelx 0.33.0, pandas 3.0.6, numpy 2.5.3, Python 3.12.13"


def test_newer_revision_lies_on_the_main_line_after_release_n():
    require_clone(CLONE, NEWER)
    assert RELEASE_N in git(CLONE, "rev-list", "--first-parent", NEWER).decode("ascii").split()
    assert len(git(CLONE, "rev-list", "--first-parent", f"{RELEASE_N}..{NEWER}").split()) == 35


def test_published_sums_list_the_walk_result_and_signature_tables_only():
    hashes = listed_hashes()
    assert "walk.result.json" in hashes
    assert len(hashes) > 1
    assert PROFILE.is_file()


@pytest.mark.skipif(os.environ.get("DELTARECON_ORACLE") != "1",
                    reason="the reproduction of the reference walk runs on request: DELTARECON_ORACLE=1")
def test_reference_walk_reproduces_every_published_hash(monkeypatch, tmp_path):
    """Run both published requests, walk between them with the profile, and check every hash."""
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
    written = {path.name for path in walk.glob("*.signature-table.json")} | {"walk.result.json"}
    hashes = listed_hashes()
    assert set(hashes) == written
    assert {name: hashlib.sha256((walk / name).read_bytes()).hexdigest() for name in hashes} == hashes
