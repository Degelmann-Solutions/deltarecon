"""The measurement tool ``tools/measure_quick_start.py``: fast tests only, no measurement runs.

The tool's step list must equal the ``uv run`` lines of the README quick-start block, so a change
of the quick start changes the measurement with it.
"""
from __future__ import annotations

import importlib.util
import json
import os
import re
import shlex
import sys

import pytest

from conftest import ROOT

TOOL = ROOT / "tools" / "measure_quick_start.py"
MEASUREMENTS = sorted((ROOT / "measurements").glob("*.json"))


def load_tool():
    spec = importlib.util.spec_from_file_location("measure_quick_start", TOOL)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


tool = load_tool()


def quick_start_commands() -> list[list[str]]:
    """The ``uv run`` lines of the first ``sh`` block under the heading "Quick start" of the README."""
    text = (ROOT / "README.md").read_text("utf-8")
    section = text[text.index("## Quick start"):]
    block = re.search(r"```sh\n(.*?)```", section, re.S).group(1)
    return [shlex.split(line) for line in block.splitlines() if line.startswith("uv run ")]


def test_steps_are_the_readme_quick_start_commands_in_order():
    assert [step["argv"] for step in tool.STEPS.values()] == quick_start_commands()
    assert list(tool.STEPS) == ["request", "run", "replay", "regression", "derive", "search"]
    assert tool.STEPS["search"]["needs"] == ("run", "regression")
    assert "--target-only" in tool.STEPS["search"]["argv"] and "--walk" not in tool.STEPS["search"]["argv"]
    assert list(tool.STATES) == ["search"]
    assert {name: step["expect"] for name, step in tool.STEPS.items() if step["expect"] != 0} == {"regression": 1}


def test_rewrite_replaces_the_leading_runs_folder_only(tmp_path):
    work = tmp_path / "work"
    argv = ["uv", "run", "deltarecon", "walk", "runs/x", "runs/a/b.json", "--tolerance",
            "profiles/tolerance-bruttobeitrag.json", "other/runs/y", "runs"]
    assert tool.rewrite(argv, work) == ["uv", "run", "deltarecon", "walk", str(work / "x"), str(work / "a/b.json"),
                                        "--tolerance", "profiles/tolerance-bruttobeitrag.json", "other/runs/y", "runs"]


def test_needed_steps_are_added_and_only_the_named_ones_reported(tmp_path, monkeypatch, capsys):
    assert tool.expand(["search"]) == ["request", "run", "regression", "search"]
    assert tool.expand(["derive", "request"]) == ["request", "run", "regression", "derive"]
    ran = []

    def execute(argv, log):
        ran.append(argv)
        return (1 if argv == tool.rewrite(tool.STEPS["regression"]["argv"], work) else 0), 2.0, 10.0

    work = tmp_path / "work"
    monkeypatch.setattr(tool, "execute", execute)
    assert tool.main(["--steps", "search", "--work", str(work), "--output", str(tmp_path / "m.json"),
                      "--baseline", str(tmp_path / "none.json")]) == 0
    assert ran == [tool.rewrite(tool.STEPS[name]["argv"], work) for name in ("request", "run", "regression",
                                                                             "search")]
    record = json.loads((tmp_path / "m.json").read_text("utf-8"))
    assert {step["name"] for step in record["steps"]} == {"search"}
    assert record["steps"][0]["states"] is None and record["total"] == {"seconds": 2.0, "peak_mib": 10.0}


def test_unknown_step_exits_2_with_the_names(tmp_path, capsys):
    with pytest.raises(SystemExit) as exit:
        tool.main(["--steps", "nothing", "--work", str(tmp_path / "work")])
    assert exit.value.code == 2
    error = capsys.readouterr().err
    assert all(name in error for name in tool.STEPS)
    assert not (tmp_path / "work").exists()


# The records taken before the quick start dropped the walk and the tests hold the earlier eight steps.
EARLIER_RECORDS = {"baseline.json", "2026-10-23-release-itemspaces.json"}
EARLIER_STEPS = ["request", "run", "replay", "regression", "derive", "walk", "search", "tests"]


def test_the_earlier_records_and_a_record_of_the_present_steps_are_recorded():
    assert EARLIER_RECORDS < {path.name for path in MEASUREMENTS}
    assert any(path.name not in EARLIER_RECORDS for path in MEASUREMENTS)


@pytest.mark.parametrize("path", MEASUREMENTS, ids=lambda path: path.name)
def test_recorded_measurement_holds_every_step(path):
    record = json.loads(path.read_text("utf-8"))
    expected = EARLIER_STEPS if path.name in EARLIER_RECORDS else list(tool.STEPS)
    assert [step["name"] for step in record["steps"]] == expected
    for step in record["steps"]:
        assert isinstance(step["seconds"], (int, float)) and not isinstance(step["seconds"], bool)
    for entry in record.get("beside", []):
        assert set(entry) == {"name", "seconds"} and entry["seconds"] >= 0
    assert record["total"]["seconds"] == pytest.approx(sum(step["seconds"] for step in record["steps"]))


SYNTHETIC = {
    "date": "2026-10-23T00:00:00Z", "commit": "0" * 40, "dirty": False, "platform": "Linux", "cpu_count": 1,
    "engine_version": "x", "note": "synthetic",
    "steps": [{"name": "run", "seconds": 10.0, "peak_mib": 155.0},
              {"name": "walk", "seconds": 360.0, "peak_mib": 160.0, "states": 36, "seconds_per_state": 10.0}],
    "total": {"seconds": 370.0, "peak_mib": 160.0},
}


def test_report_without_a_baseline():
    lines = tool.report(SYNTHETIC, None).splitlines()
    assert lines[0].split() == ["step", "seconds", "peak", "MiB"]
    assert lines[1].split() == ["run", "10.0", "155"]
    assert lines[3].split() == ["total", "370.0", "160"]
    assert lines[4] == "walk: 36 states, 10.0 s per state"


def test_report_beside_a_baseline():
    baseline = json.loads(json.dumps(SYNTHETIC))
    baseline["steps"][0].update(seconds=100.0, peak_mib=8000.0)
    baseline["steps"][1].update(seconds=720.0, seconds_per_state=20.0)
    baseline["total"]["seconds"] = 820.0
    lines = tool.report(SYNTHETIC, baseline).splitlines()
    assert lines[0].split() == ["step", "seconds", "peak", "MiB", "baseline", "s", "baseline", "MiB", "factor"]
    assert lines[1].split() == ["run", "10.0", "155", "100.0", "8000", "10.00"]
    assert lines[2].split() == ["walk", "360.0", "160", "720.0", "160", "2.00"]
    assert lines[3].split() == ["total", "370.0", "160", "820.0", "160", "2.22"]
    assert lines[4] == "walk: 36 states, 10.0 s per state (baseline 36 states, 20.0 s per state)"
    # A baseline of other steps gives no total to compare with.
    baseline["steps"].pop()
    assert tool.report(SYNTHETIC, baseline).splitlines()[3].split() == ["total", "370.0", "160", "-", "-", "-"]


def cheap(code: str, expect: int = 0) -> dict:
    return {"argv": [sys.executable, "-c", code], "needs": (), "expect": expect}


def test_failing_step_exits_1_and_writes_nothing(tmp_path, capsys):
    steps = {"first": cheap("pass"), "bad": cheap("raise SystemExit(3)"), "after": cheap("pass")}
    output = tmp_path / "m.json"
    assert tool.main(["--work", str(tmp_path / "work"), "--output", str(output)], steps) == 1
    error = capsys.readouterr().err
    assert "bad exited with status 3, expected 0" in error and "raise SystemExit(3)" in error
    assert not output.exists()
    assert not (tmp_path / "work" / "logs" / "after.log").exists()


def test_expected_status_other_than_0_passes(tmp_path, capsys):
    steps = {"deviates": cheap("raise SystemExit(1)", expect=1)}
    assert tool.main(["--work", str(tmp_path / "work"), "--baseline", str(tmp_path / "none")], steps) == 0


def test_existing_work_folder_exits_2_before_running(tmp_path, capsys):
    work = tmp_path / "work"
    work.mkdir()
    marker = tmp_path / "ran"
    steps = {"touch": cheap(f"open({str(marker)!r}, 'w').close()")}
    assert tool.main(["--work", str(work)], steps) == 2
    assert "exists already" in capsys.readouterr().err
    assert not marker.exists() and list(work.iterdir()) == []


def test_without_wait4_memory_is_null_and_shown_as_dash(tmp_path, monkeypatch, capsys):
    monkeypatch.delattr(os, "wait4", raising=False)
    output = tmp_path / "m.json"
    steps = {"run": cheap("pass")}
    assert tool.main(["--work", str(tmp_path / "work"), "--output", str(output),
                      "--baseline", str(tmp_path / "none")], steps) == 0
    record = json.loads(output.read_text("utf-8"))
    assert record["steps"][0]["peak_mib"] is None and record["total"]["peak_mib"] is None
    assert isinstance(record["steps"][0]["seconds"], float)
    row = next(line for line in capsys.readouterr().out.splitlines() if line.startswith("run "))
    assert row.split()[2] == "-"


@pytest.mark.skipif(not hasattr(os, "wait4"), reason="no os.wait4 on this platform")
def test_peak_memory_is_measured_with_wait4(tmp_path, capsys):
    output = tmp_path / "m.json"
    steps = {"run": cheap("block = bytearray(64 * 1024 * 1024); block[::4096] = b'x' * len(block[::4096])")}
    assert tool.main(["--work", str(tmp_path / "work"), "--output", str(output),
                      "--baseline", str(tmp_path / "none")], steps) == 0
    assert json.loads(output.read_text("utf-8"))["steps"][0]["peak_mib"] >= 64


def test_durations_beside_are_recorded_and_printed_but_not_in_the_total(tmp_path, capsys):
    output = tmp_path / "m.json"
    steps = {"run": cheap("pass")}
    assert tool.main(["--work", str(tmp_path / "work"), "--output", str(output), "--baseline", str(tmp_path / "none"),
                      "--beside", "git-clone=12.3", "--beside", "uv-sync=40.1"], steps) == 0
    record = json.loads(output.read_text("utf-8"))
    assert record["beside"] == [{"name": "git-clone", "seconds": 12.3}, {"name": "uv-sync", "seconds": 40.1}]
    assert record["total"]["seconds"] == record["steps"][0]["seconds"] < 12.3
    lines = capsys.readouterr().out.splitlines()
    table_end = next(number for number, line in enumerate(lines) if line.startswith("total "))
    assert lines[table_end + 1:table_end + 3] == ["beside, not in the total: git-clone 12.3 s",
                                                  "beside, not in the total: uv-sync 40.1 s"]


def test_without_durations_beside_the_record_holds_an_empty_list(tmp_path, capsys):
    output = tmp_path / "m.json"
    assert tool.main(["--work", str(tmp_path / "work"), "--output", str(output), "--baseline", str(tmp_path / "none")],
                     {"run": cheap("pass")}) == 0
    assert json.loads(output.read_text("utf-8"))["beside"] == []
    assert "beside, not in the total" not in capsys.readouterr().out


@pytest.mark.parametrize("value", ["git-clone", "git-clone=", "=12", "git-clone=-1", "git-clone=ten", "git-clone=nan",
                                   "git-clone=inf"])
def test_a_malformed_duration_beside_exits_2_before_any_step_runs(tmp_path, capsys, value):
    marker = tmp_path / "ran"
    steps = {"touch": cheap(f"open({str(marker)!r}, 'w').close()")}
    with pytest.raises(SystemExit) as exit:
        tool.main(["--work", str(tmp_path / "work"), "--beside", value], steps)
    assert exit.value.code == 2
    assert "NAME=SECONDS" in capsys.readouterr().err
    assert not marker.exists() and not (tmp_path / "work").exists()


def test_the_present_steps_beside_the_recorded_baseline_of_the_earlier_steps():
    baseline = json.loads((ROOT / "measurements" / "baseline.json").read_text("utf-8"))
    steps = [{"name": name, "seconds": 2.0, "peak_mib": 200.0} for name in tool.STEPS]
    steps[-1].update(states=10, seconds_per_state=0.2)
    record = {"steps": steps, "total": {"seconds": 12.0, "peak_mib": 200.0},
              "beside": [{"name": "uv-sync", "seconds": 40.0}]}
    lines = tool.report(record, baseline).splitlines()
    old = {step["name"]: step for step in baseline["steps"]}
    for line, name in zip(lines[1:], tool.STEPS):
        assert line.split()[0] == name and line.split()[-1] == f"{old[name]['seconds'] / 2.0:.2f}"
    assert lines[len(tool.STEPS) + 1].split() == ["total", "12.0", "200", "-", "-", "-"]
    assert lines[len(tool.STEPS) + 2].startswith("search: 10 states, 0.2 s per state (baseline ")
    assert lines[-1] == "beside, not in the total: uv-sync 40.0 s"
