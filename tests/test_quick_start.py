"""The pin of the quick-start search: ``measurements/quick-start-search.SHA256SUMS``.

The pin holds the SHA-256 of ``search.result.json`` that the last command of the README quick start
writes, and of every file that the search result hashes, in ``sha256sum`` format with paths relative
to the search folder: ``search.result.json`` first, the others in the order in which the search result
first names them. ``sha256sum -c`` run inside a search folder compares the folder with the pin. Run
records are not pinned: they hold the time of the run and a random record id.

The fast tests check the format of the pin and the check of a search folder against it on a
synthetic folder. The chain test runs the quick start, the steps of ``tools/measure_quick_start.py``,
which equal the README lines, in process; its twin runs the guided quick start ``deltarecon quickstart``.
Both are skipped unless they are asked for:
``DELTARECON_QUICK_START=1``. The pinned hashes are never rewritten to make a test pass.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest

from degelmann.deltarecon.__main__ import main
from degelmann.deltarecon.documents import sha256_file

from conftest import CLONE, NEWER, REPOSITORIES, ROOT, artifacts, load_measure_tool, require_clone

PIN = ROOT / "measurements" / "quick-start-search.SHA256SUMS"
SEARCH_RESULT = "search.result.json"
PIN_LINE = re.compile(r"([0-9a-f]{64})  ((?:[A-Za-z0-9_.-]+/)*[A-Za-z0-9_.-]+)")

tool = load_measure_tool()


def parse_pin(text: str) -> dict[str, str]:
    """The paths and hashes of a pin, in its order; every line must be a ``sha256sum`` line of a
    relative path below the search folder, and no path may be listed twice."""
    hashes = {}
    for line in text.splitlines():
        match = PIN_LINE.fullmatch(line)
        assert match, f"not a sha256sum line of a file below the search folder: {line!r}"
        path = match.group(2)
        assert not {".", ".."} & set(path.split("/")), f"not a path below the search folder: {line!r}"
        assert path not in hashes, f"listed twice: {line!r}"
        hashes[path] = match.group(1)
    return hashes


def read_pin() -> dict[str, str]:
    return parse_pin(PIN.read_text("ascii"))


def hashed_paths(folder: Path) -> list[str]:
    """``search.result.json`` and every path its artifact references name, in the order of first appearance."""
    paths = [SEARCH_RESULT]
    for reference in artifacts(json.loads((folder / SEARCH_RESULT).read_text("utf-8"))):
        if reference["path"] not in paths:
            paths.append(reference["path"])
    return paths


def pin_problems(folder: Path, pinned: dict[str, str]) -> list[str]:
    """What differs between the search folder ``folder`` and the pin: ``missing: <path>`` for a pinned
    file that is absent, ``mismatch: <path>`` for one with another hash, and ``unlisted: <path>`` for a
    path the search result hashes that the pin lacks. An empty list means the folder matches the pin."""
    problems = []
    for path, digest in pinned.items():
        file = folder / path
        if not file.is_file():
            problems.append(f"missing: {path}")
        elif sha256_file(file) != digest:
            problems.append(f"mismatch: {path}")
    try:
        written = hashed_paths(folder)
    except (OSError, ValueError):  # absent or no longer JSON: reported above as missing or mismatch
        written = []
    problems += [f"unlisted: {path}" for path in written if path not in pinned]
    return problems


def test_pin_is_well_formed_and_starts_with_the_search_result():
    pinned = read_pin()
    assert PIN.read_bytes().endswith(b"\n")
    assert list(pinned)[0] == SEARCH_RESULT
    assert len(pinned) > 1


def test_pin_names_no_run_record():
    for path in read_pin():
        assert not path.endswith("run-record.json"), path


@pytest.mark.parametrize("text", [
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b85  search.result.json",  # 63 hex digits
    "E3B0C44298FC1C149AFBF4C8996FB92427AE41E4649B934CA495991B7852B855  search.result.json",  # upper case
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 search.result.json",  # one space
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 *search.result.json",  # binary mark
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  /tmp/search.result.json",
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  ../oracle/SHA256SUMS",
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  state-00/results.csv\n"
    "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855  state-00/results.csv",
])
def test_malformed_pin_line_is_rejected(text):
    with pytest.raises(AssertionError, match="state-00/results.csv|search.result.json|SHA256SUMS"):
        parse_pin(text)


def synthetic_search(folder: Path) -> dict[str, str]:
    """A search folder whose result hashes two files, and its pin in the order of the real one."""
    (folder / "state-00").mkdir(parents=True)
    (folder / "changes.json").write_bytes(b'{"changes": []}\n')
    (folder / "state-00" / "results.csv").write_bytes(b"model_point_id,period\n1,0\n")
    (folder / "search.run-record.json").write_bytes(b'{"recorded_at": "now"}\n')
    result = {"manifest": {"path": "changes.json", "sha256": sha256_file(folder / "changes.json")},
              "states": [{"results": {"path": "state-00/results.csv",
                                      "sha256": sha256_file(folder / "state-00" / "results.csv")}}]}
    (folder / SEARCH_RESULT).write_text(json.dumps(result, indent=2) + "\n", "utf-8")
    pin = "".join(f"{sha256_file(folder / path)}  {path}\n" for path in hashed_paths(folder))
    (folder / "pin.SHA256SUMS").write_text(pin, "ascii")
    return parse_pin(pin)


def flip_one_byte(path: Path) -> None:
    data = bytearray(path.read_bytes())
    data[-2] ^= 0x01
    path.write_bytes(bytes(data))


def test_a_matching_folder_has_no_problem(tmp_path):
    pinned = synthetic_search(tmp_path)
    assert list(pinned) == [SEARCH_RESULT, "changes.json", "state-00/results.csv"]
    assert pin_problems(tmp_path, pinned) == []


@pytest.mark.parametrize("path", [SEARCH_RESULT, "changes.json", "state-00/results.csv"])
def test_one_changed_byte_is_reported(tmp_path, path):
    pinned = synthetic_search(tmp_path)
    flip_one_byte(tmp_path / path)
    assert pin_problems(tmp_path, pinned) == [f"mismatch: {path}"]


def test_a_missing_file_is_reported(tmp_path):
    pinned = synthetic_search(tmp_path)
    (tmp_path / "state-00" / "results.csv").unlink()
    assert pin_problems(tmp_path, pinned) == ["missing: state-00/results.csv"]


def test_a_hashed_path_the_pin_lacks_is_reported(tmp_path):
    pinned = synthetic_search(tmp_path)
    del pinned["changes.json"]
    assert pin_problems(tmp_path, pinned) == ["unlisted: changes.json"]


@pytest.mark.skipif(shutil.which("sha256sum") is None, reason="needs sha256sum")
def test_sha256sum_reports_the_changed_file(tmp_path):
    """The documented compare command reads the pin as the test does."""
    synthetic_search(tmp_path)
    command = ["sha256sum", "-c", "pin.SHA256SUMS"]
    assert subprocess.run(command, cwd=tmp_path, capture_output=True).returncode == 0
    flip_one_byte(tmp_path / "state-00" / "results.csv")
    done = subprocess.run(command, cwd=tmp_path, capture_output=True, text=True)
    assert done.returncode == 1
    assert "state-00/results.csv: FAILED" in done.stdout


@pytest.mark.skipif(os.environ.get("DELTARECON_QUICK_START") != "1",
                    reason="the quick-start chain runs on request: DELTARECON_QUICK_START=1")
def test_quick_start_chain_writes_the_pinned_search(monkeypatch, tmp_path):
    """Run the README quick start in process and check the search folder against the pin."""
    require_clone(CLONE, NEWER)
    monkeypatch.chdir(ROOT)
    for name, step in tool.STEPS.items():
        argv = tool.rewrite(step["argv"], tmp_path)
        assert argv[:3] == ["uv", "run", "deltarecon"], name
        assert main([*argv[3:], "--repositories", str(REPOSITORIES)]) == step["expect"], name
    search = tmp_path / "search"
    pinned = read_pin()
    assert pin_problems(search, pinned) == []
    assert list(pinned) == hashed_paths(search)


@pytest.mark.skipif(os.environ.get("DELTARECON_QUICK_START") != "1",
                    reason="the quick-start chain runs on request: DELTARECON_QUICK_START=1")
def test_the_guided_quick_start_writes_the_pinned_search(monkeypatch, tmp_path, capsys):
    """Run ``deltarecon quickstart`` in process in a new working directory and check its search folder against
    the pin; the demo works in its folder, names the clone relative to it, and changes back at the end."""
    require_clone(CLONE, NEWER)
    monkeypatch.chdir(tmp_path)
    assert main(["quickstart", "--no-pause", "--lang", "en", "--repositories", str(REPOSITORIES)]) == 0
    assert Path.cwd() == tmp_path
    folders = list((tmp_path / "runs").glob("quickstart-*"))
    assert len(folders) == 1
    assert {path.name for path in folders[0].iterdir()} == {"release-n", "regression", "changes.json", "search"}
    search = folders[0] / "search"
    pinned = read_pin()
    assert pin_problems(search, pinned) == []
    assert list(pinned) == hashed_paths(search)
    assert " ".join(capsys.readouterr().out.split()).endswith(f"Done. Every file is in {Path('runs') / folders[0].name}.")
