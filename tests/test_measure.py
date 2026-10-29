"""The measurement tool ``tools/measure_quick_start.py``: fast tests only, no measurement runs.

The tool's step list must equal the ``uv run`` lines of the README quick-start block, so a change
of the quick start changes the measurement with it.
"""
from __future__ import annotations

import json
import os
import re
import shlex
import sys

import pytest

from conftest import ROOT, load_measure_tool

MEASUREMENTS = sorted((ROOT / "measurements").glob("*.json"))

tool = load_measure_tool()


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


def check_record(record: dict, name: str = "") -> None:
    """A measurement record holds the steps it names in ``measured_steps``, a non-empty part of the
    present steps in their order; a record without the member holds every step of its time."""
    if "measured_steps" in record:
        expected = record["measured_steps"]
        assert expected and expected == [step for step in tool.STEPS if step in expected]
    else:
        expected = EARLIER_STEPS if name in EARLIER_RECORDS else list(tool.STEPS)
    assert [step["name"] for step in record["steps"]] == expected
    for step in record["steps"]:
        assert isinstance(step["seconds"], (int, float)) and not isinstance(step["seconds"], bool)
    for entry in record.get("beside", []):
        assert set(entry) == {"name", "seconds"} and entry["seconds"] >= 0
    assert record["total"]["seconds"] == pytest.approx(sum(step["seconds"] for step in record["steps"]))


@pytest.mark.parametrize("path", MEASUREMENTS, ids=lambda path: path.name)
def test_recorded_measurement_holds_its_steps(path):
    check_record(json.loads(path.read_text("utf-8")), path.name)


def test_a_measurement_of_one_step_names_it_and_passes_the_record_check(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(tool, "execute", lambda argv, log: (0, 2.0, 10.0))
    output = tmp_path / "m.json"
    assert tool.main(["--steps", "run", "--work", str(tmp_path / "work"), "--output", str(output),
                      "--baseline", str(tmp_path / "none.json")]) == 0
    record = json.loads(output.read_text("utf-8"))
    assert record["measured_steps"] == ["run"] and [step["name"] for step in record["steps"]] == ["run"]
    assert record["peak_mib_covers"] == tool.PEAK_COVERS
    check_record(record)
    for wrong in ([], ["run", "request"], ["walk"]):  # empty, out of order, or not a present step
        with pytest.raises(AssertionError):
            check_record({**record, "measured_steps": wrong, "steps": [{"name": n} for n in wrong]})


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
    assert lines[4] == "peak MiB: the largest single process of a step, not the sum of its worker processes"
    assert lines[5] == "walk: 36 states, 10.0 s per state"


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
    assert lines[4] == tool.PEAK_LINE
    assert lines[5] == "walk: 36 states, 10.0 s per state (baseline 36 states, 20.0 s per state)"
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
    assert lines[table_end + 1:table_end + 4] == [
        tool.PEAK_LINE, "beside, not in the total: git-clone 12.3 s", "beside, not in the total: uv-sync 40.1 s"]


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
    assert lines[len(tool.STEPS) + 2] == tool.PEAK_LINE
    assert lines[len(tool.STEPS) + 3].startswith("search: 10 states, 0.2 s per state (baseline ")
    assert lines[-1] == "beside, not in the total: uv-sync 40.0 s"


# The Windows mode: every host call is replaced, so no test starts powershell.exe, uv, or the network.

ENGINE = "modelx 0.33.0 export, pandas 3.0.6, numpy 2.5.3, Python 3.14.9"
HOST_PLATFORM = "Windows-11-10.0.26100-SP0"


def chain_output(commands, seconds: float = 1.5, failing: str | None = None) -> tuple[int, str]:
    """What the host chain script prints for ``commands``: the unpack line and one line per step."""
    lines = ["build_package: host: unpacking x", "build_package: host: unpacked in 3.4 s", "build_package: chain: PATH=x"]
    for step, _, expect in commands:
        code = expect + 2 if step == failing else expect
        lines += [f"build_package: chain: step {step}", "output of the step",
                  f"build_package: chain: {step} exit {code} (expected {expect}) in {seconds:.1f} s"]
        if code != expect:
            lines.append(f"build_package: step {step} exit {code}, expected {expect}")
            return 1, "\r\n".join(lines)
    return 0, "\r\n".join(lines)


class FakeHost:
    """The host: a folder ``C`` below ``tmp_path`` for ``C:\\``, a recorded ``powershell``, a ``compare``."""

    def __init__(self, tmp_path, monkeypatch, failing=None, compared=(0, ["a.json: OK", "b.csv: OK"])):
        self.build, self.host = tool.windows_tools()
        self.drive = tmp_path / "C"
        self.calls, self.commands, self.failing, self.compared = [], [], failing, compared
        self.version = self.build.project()[0]
        self.archive = tmp_path / self.build.archive_name(self.version, self.build.WINDOWS_TARGET)
        self.archive.write_bytes(b"zip")
        original_wsl_path, chain_script = self.host.wsl_path, self.build.windows_chain_script

        def wsl_path(windows):
            return str(self.drive) + original_wsl_path(windows)[len(self.host.MOUNT):]

        def windows_chain_script(work, archive, name, commands):
            self.commands = commands
            return chain_script(work, archive, name, commands)

        monkeypatch.setattr(self.host, "wsl_path", wsl_path)
        monkeypatch.setattr(self.host, "powershell_path", lambda: "/host/powershell.exe")
        monkeypatch.setattr(self.host, "powershell", self.powershell)
        monkeypatch.setattr(self.host, "compare", self.compare)
        monkeypatch.setattr(self.build, "windows_chain_script", windows_chain_script)

    def folder(self, windows: str):
        return self.drive / windows[3:].replace("\\", "/")

    def powershell(self, script, runner=None, capture=False, executable=None):
        self.calls.append({"script": script, "runner": runner, "capture": capture, "executable": executable})
        if capture:
            return tool.subprocess.CompletedProcess([], 0, stdout=f"windows_host: step probe\n{HOST_PLATFORM}\n16\n")
        work = next(path for path in self.drive.glob("tmp/*/*") if path.is_dir())
        (work / "runs" / "n-full").mkdir(parents=True)
        (work / "runs" / "n-full" / "request.json").write_text(json.dumps(
            {"release": {"references": [{"kind": "engine_version", "value": ENGINE}]}}), "utf-8")
        (work / "runs" / "search").mkdir()
        (work / "runs" / "search" / "search.result.json").write_text(json.dumps({"runs": {"search": 17}}), "utf-8")
        code, text = chain_output(self.commands, failing=self.failing)
        return tool.subprocess.CompletedProcess([], code, stdout=text)

    def compare(self, folder):
        self.compared_folder = folder
        return self.compared


def windows_main(fake, tmp_path, *extra):
    return tool.main(["--windows-package", str(fake.archive), "--output", str(tmp_path / "m.json"),
                      "--baseline", str(tmp_path / "none.json"), *extra])


def test_host_seconds_reads_the_step_and_unpack_lines():
    commands = [("request", [], 0), ("regression", [], 1)]
    _, text = chain_output(commands, seconds=111.66)
    assert tool.host_seconds(text) == ({"request": 111.7, "regression": 111.7}, 3.4)
    assert tool.host_seconds("noise\nbuild_package: chain: step run\n") == ({}, None)


def test_the_stream_runner_echoes_and_collects_every_line(capsys):
    done = tool.stream([sys.executable, "-c", "import sys; print('one', flush=True); print('two', file=sys.stderr); sys.exit(3)"],
                       stdin=tool.subprocess.DEVNULL)
    assert done.returncode == 3 and done.stdout.splitlines() == ["one", "two"]
    assert capsys.readouterr().out.splitlines() == ["one", "two"]


def test_a_windows_measurement_writes_a_record_with_the_host_seconds(tmp_path, monkeypatch, capsys):
    fake = FakeHost(tmp_path, monkeypatch)
    assert windows_main(fake, tmp_path, "--work", "C:\\tmp\\m\\one", "--beside", "build=60") == 0
    record = json.loads((tmp_path / "m.json").read_text("utf-8"))
    check_record(record)
    assert record["measured_steps"] == list(tool.STEPS)
    assert record["commit"] == tool.git_text("rev-parse", "HEAD") and record["platform"] == HOST_PLATFORM
    assert record["cpu_count"] == 16 and record["engine_version"] == ENGINE
    assert all(step["peak_mib"] is None and step["seconds"] == 1.5 for step in record["steps"])
    assert record["total"] == {"seconds": pytest.approx(1.5 * len(tool.STEPS)), "peak_mib": None}
    assert record["steps"][-1]["states"] == 17 and record["steps"][-1]["seconds_per_state"] == pytest.approx(1.5 / 17)
    assert record["beside"] == [{"name": "build", "seconds": 60.0}, {"name": "unpack", "seconds": 3.4}]
    assert record["peak_mib_covers"] == tool.WINDOWS_PEAK_COVERS
    assert record["windows"] == {"work": "C:\\tmp\\m\\one", "package": fake.archive.name,
                                 "package_sha256": fake.build.sha256_file(fake.archive)}
    work = fake.folder("C:\\tmp\\m\\one")
    assert (work / fake.archive.name).read_bytes() == b"zip" and (work / "empty-path").is_dir()
    assert fake.compared_folder == work / "runs" / "search"
    chain, probe = fake.calls
    assert chain["runner"] is tool.stream and not chain["capture"] and chain["executable"] == "/host/powershell.exe"
    assert probe["capture"] and tool.PLATFORM_PROBE in probe["script"] and '"' not in tool.PLATFORM_PROBE
    launcher = "C:\\tmp\\m\\one\\package\\" + fake.build.package_name(fake.version, fake.build.WINDOWS_TARGET) + \
        "\\deltarecon.cmd"
    assert [command[1][0] for command in fake.commands] == [launcher] * len(tool.STEPS)
    out = capsys.readouterr().out
    assert "measure: pin: a.json: OK" in out and "measure: 2 pinned files OK" in out


def test_windows_steps_search_runs_what_it_needs_and_reports_only_the_search(tmp_path, monkeypatch, capsys):
    fake = FakeHost(tmp_path, monkeypatch)
    assert windows_main(fake, tmp_path, "--steps", "search") == 0
    assert [(name, expect) for name, _, expect in fake.commands] == [
        ("request", 0), ("run", 0), ("regression", 1), ("search", 0)]
    record = json.loads((tmp_path / "m.json").read_text("utf-8"))
    check_record(record)
    assert record["measured_steps"] == ["search"] and record["steps"][0]["states"] == 17
    assert record["total"]["seconds"] == 1.5
    assert record["windows"]["work"].startswith(tool.WINDOWS_PARENT + "\\")


def test_windows_without_the_search_compares_nothing(tmp_path, monkeypatch, capsys):
    fake = FakeHost(tmp_path, monkeypatch, compared=(1, ["a.json: FAILED"]))
    assert windows_main(fake, tmp_path, "--steps", "run") == 0
    assert [name for name, _, _ in fake.commands] == ["request", "run"]
    assert not hasattr(fake, "compared_folder")


@pytest.mark.parametrize("case", ["linux archive", "no target", "missing", "no host", "wsl work", "unc work",
                                  "other drive", "existing work"])
def test_windows_refusals_exit_2_and_copy_nothing(tmp_path, monkeypatch, capsys, case):
    fake = FakeHost(tmp_path, monkeypatch)
    archive, work = fake.archive, "C:\\tmp\\m\\one"
    if case == "linux archive":
        archive = tmp_path / fake.build.archive_name(fake.version, fake.build.TARGET)
        archive.write_bytes(b"tar")
    elif case == "no target":
        archive = tmp_path / "deltarecon.zip"
        archive.write_bytes(b"zip")
    elif case == "missing":
        fake.archive.unlink()
    elif case == "no host":
        monkeypatch.setattr(fake.host, "powershell_path", lambda: None)
    elif case == "wsl work":
        work = "/mnt/c/tmp/m/one"
    elif case == "unc work":
        work = "\\\\wsl.localhost\\Ubuntu\\tmp\\one"
    elif case == "other drive":
        work = "D:\\tmp\\one"
    elif case == "existing work":
        fake.folder(work).mkdir(parents=True)
    assert tool.main(["--windows-package", str(archive), "--work", work, "--output", str(tmp_path / "m.json")]) == 2
    error = capsys.readouterr().err
    assert error.startswith("measure: ")
    if case in ("wsl work", "unc work", "other drive"):
        assert error.startswith("measure: the work folder: ")
    elif case == "existing work":
        assert error == f"measure: the work folder {work} exists already\n"
    elif case == "no host":
        assert error == "measure: powershell.exe is not on PATH; --windows-package runs in WSL on a Windows host\n"
    assert fake.calls == [] and not (tmp_path / "m.json").exists()
    copied = list(fake.drive.rglob("*.zip")) if fake.drive.exists() else []
    assert copied == []


def test_windows_existing_output_exits_2_before_anything_is_copied(tmp_path, monkeypatch, capsys):
    fake = FakeHost(tmp_path, monkeypatch)
    (tmp_path / "m.json").write_text("{}", "utf-8")
    assert windows_main(fake, tmp_path) == 2
    assert fake.calls == [] and not fake.drive.exists()


def test_windows_failing_host_step_exits_1_and_writes_nothing(tmp_path, monkeypatch, capsys):
    fake = FakeHost(tmp_path, monkeypatch, failing="regression")
    assert windows_main(fake, tmp_path) == 1
    assert "a host step failed with exit status 1" in capsys.readouterr().err
    assert len(fake.calls) == 1 and not (tmp_path / "m.json").exists()


def test_windows_search_that_differs_from_the_pin_exits_1_and_writes_nothing(tmp_path, monkeypatch, capsys):
    fake = FakeHost(tmp_path, monkeypatch, compared=(1, ["a.json: OK", "b.csv: FAILED"]))
    assert windows_main(fake, tmp_path) == 1
    captured = capsys.readouterr()
    assert "measure: pin: b.csv: FAILED" in captured.out and "differs from the pin" in captured.err
    assert not (tmp_path / "m.json").exists()
