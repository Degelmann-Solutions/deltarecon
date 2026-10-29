"""The Windows host helper ``tools/windows_host.py``: fast tests with an injected runner.

No test calls ``powershell.exe``: every host call goes through a fake runner that records the
decoded script and answers with a fixed exit status.
"""
from __future__ import annotations

import base64
import hashlib
import subprocess

import pytest

from conftest import load_windows_host_tool

tool = load_windows_host_tool()

COMMIT = "0123456789abcdef0123456789abcdef01234567"
WORK = "C:\\tmp\\deltarecon-test\\work"


def decode(argv: list[str]) -> str:
    assert argv[1:4] == ["-NoProfile", "-NonInteractive", "-EncodedCommand"] and len(argv) == 5
    return base64.b64decode(argv[4]).decode("utf-16-le")


class Runner:
    """A fake ``subprocess.run``: the probe answers ``found``, the quick start ``status``."""

    def __init__(self, status: int = 0, missing: tuple[str, ...] = ()):
        self.status, self.missing, self.scripts = status, missing, []

    def __call__(self, argv, **options):
        script = decode(argv)
        self.scripts.append(script)
        if script.endswith(tool.PROBE):
            out = "".join(f"missing {name}\n" if name in self.missing else f"found {name}: {name} 1.0\n"
                          for name in ("git", "uv"))
            return subprocess.CompletedProcess(argv, 0, out, "")
        return subprocess.CompletedProcess(argv, self.status, None, None)


@pytest.fixture
def host(monkeypatch):
    """A host that has powershell.exe and no work folder; preparing writes nothing."""
    monkeypatch.setattr(tool, "powershell_path", lambda: "/mnt/c/fake/powershell.exe")
    monkeypatch.setattr(tool, "host_exists", lambda windows: False)
    monkeypatch.setattr(tool, "prepare", lambda work: (COMMIT, {"deltarecon": work + "\\d.bundle",
                                                                "delib-history": work + "\\h.bundle"}))
    monkeypatch.setattr(tool, "engine_version", lambda work: "modelx test, Python 3.14.9")
    return monkeypatch


@pytest.mark.parametrize("windows, wsl", [("C:\\tmp\\a b", "/mnt/c/tmp/a b"), ("C:\\", "/mnt/c"),
                                          ("C:\\x\\it's $y", "/mnt/c/x/it's $y")])
def test_paths_round_trip_exactly(windows, wsl):
    assert tool.wsl_path(windows) == wsl and tool.windows_path(wsl) == windows
    assert tool.windows_path(tool.wsl_path(windows)) == windows


@pytest.mark.parametrize("wsl", ["/home/x", "/mnt/d/x", "/mnt/cx", "/mnt/c/", "/mnt/c//x", "/mnt/c/a\\b",
                                 "/mnt/c/../x", "/mnt/c/a:b", "mnt/c/x"])
def test_other_wsl_forms_are_refused(wsl):
    with pytest.raises(tool.Refused):
        tool.windows_path(wsl)


@pytest.mark.parametrize("windows", ["/home/x", "\\\\wsl.localhost\\Ubuntu\\home\\x", "\\\\?\\C:\\x", "D:\\x",
                                     "C:relative", "C:/tmp/x", "c:\\tmp", "C:\\", "C:\\tmp\\..\\x",
                                     "C:\\tmp\\\\x", "C:\\tmp\\", "C:\\tmp\\a|b", "C:\\tmp\\x."])
def test_host_folders_outside_c_or_not_plain_are_refused(windows):
    with pytest.raises(tool.Refused):
        tool.require_host_folder(windows)


def test_a_folder_under_c_is_accepted():
    assert tool.require_host_folder("C:\\tmp\\a b") == "C:\\tmp\\a b"


@pytest.mark.parametrize("value, quoted", [("plain", "'plain'"), ("it's", "'it''s'"), ("$x y", "'$x y'"),
                                           ("a\u2019b", "'a\u2019\u2019b'"), ("", "''")])
def test_literal_doubles_every_quote(value, quoted):
    assert tool.literal(value) == quoted


def test_encoded_decodes_to_the_prefix_and_the_script():
    script = "Write-Output 'ä €'\n"
    text = base64.b64decode(tool.encoded(script)).decode("utf-16-le")
    assert text == tool.PREFIX + script
    assert "UTF8Encoding" in tool.PREFIX and "$ErrorActionPreference = 'Stop'" in tool.PREFIX


def test_powershell_passes_the_encoded_script_to_the_runner():
    calls = []
    tool.powershell("exit 0", lambda argv, **options: calls.append((argv, options)), capture=True,
                    executable="ps.exe")
    (argv, options), = calls
    assert argv[0] == "ps.exe" and decode(argv) == tool.PREFIX + "exit 0"
    assert options["capture_output"] and options["stdin"] == subprocess.DEVNULL


def test_the_script_names_each_step_and_the_commit_and_checks_every_exit_status():
    bundles = {"deltarecon": WORK + "\\d.bundle", "delib-history": WORK + "\\h.bundle"}
    script = tool.quick_start_script(WORK, bundles, COMMIT)
    steps = ["clone deltarecon", f"checkout {COMMIT}", "clone delib-history", "fetch delib-history remote branches",
             "install Python 3.14.9", "uv sync --locked", "run the quick start chain"]
    positions = [script.index(f"'windows_host: step {step}'") for step in steps]
    assert positions == sorted(positions)
    assert script.count("if ($LASTEXITCODE -ne 0)") == len(steps)
    assert script.count("exit 1") == len(steps) + 1  # and the check of the detached commit
    assert script.count("core.autocrlf=false") >= 4 and f"checkout --detach '{COMMIT}'" in script
    assert f"'{WORK}\\deltarecon\\repositories\\delib-history'" in script
    assert f"$env:UV_PYTHON_INSTALL_DIR = '{WORK}\\python'" in script
    assert "uv python install --no-bin --no-registry '3.14.9'" in script
    assert f"uv run python tools/measure_quick_start.py --work '{WORK}\\runs'" in script
    assert "2>&1" not in script


def test_the_script_refuses_a_work_folder_outside_c():
    with pytest.raises(tool.Refused):
        tool.quick_start_script("\\\\wsl.localhost\\x", {"deltarecon": "", "delib-history": ""}, COMMIT)


@pytest.mark.parametrize("work", ["/home/x", "\\\\wsl.localhost\\Ubuntu\\x", "D:\\x", "C:relative"])
def test_main_refuses_a_work_folder_without_running_anything(host, work, capsys):
    runner = Runner()
    assert tool.main(["quick-start", "--work", work], runner) == 2
    error = capsys.readouterr().err
    assert runner.scripts == [] and error.startswith("windows_host: the work folder: ") and "C:\\" in error


def test_main_refuses_an_existing_work_folder(host, capsys):
    host.setattr(tool, "host_exists", lambda windows: True)
    runner = Runner()
    assert tool.main(["quick-start", "--work", WORK], runner) == 2
    assert runner.scripts == [] and "exists already" in capsys.readouterr().err


def test_main_needs_powershell(host, capsys):
    host.setattr(tool, "powershell_path", lambda: None)
    runner = Runner()
    assert tool.main(["quick-start", "--work", WORK], runner) == 2
    assert runner.scripts == [] and "powershell.exe" in capsys.readouterr().err


NO_POWERSHELL = "powershell.exe is not on PATH; the caller's sentence"


@pytest.mark.parametrize("case, work, powershell, exists, refusal", [
    ("good folder", WORK, "/fake/powershell.exe", False, None),
    ("refused folder", "\\\\wsl.localhost\\Ubuntu\\x", "/fake/powershell.exe", False, "the work folder: a UNC path"),
    ("no powershell", WORK, None, False, NO_POWERSHELL),
    ("folder exists", WORK, "/fake/powershell.exe", True, f"the work folder {WORK} exists already"),
])
def test_open_work_checks_the_folder_then_powershell_then_that_the_folder_is_new(monkeypatch, case, work, powershell,
                                                                                exists, refusal):
    asked = []
    monkeypatch.setattr(tool, "powershell_path", lambda: asked.append("powershell") or powershell)
    monkeypatch.setattr(tool, "host_exists", lambda windows: asked.append(("exists", windows)) or exists)
    if refusal is None:
        assert tool.open_work(work, NO_POWERSHELL) == powershell
    else:
        with pytest.raises(tool.Refused) as raised:
            tool.open_work(work, NO_POWERSHELL)
        assert str(raised.value).startswith(refusal)
    expected = {"refused folder": [], "no powershell": ["powershell"]}.get(case, ["powershell", ("exists", WORK)])
    assert asked == expected


@pytest.mark.parametrize("work", ["/home/x", "D:\\x", "C:relative"])
def test_open_work_refuses_each_other_folder_form_with_the_prefix(work):
    with pytest.raises(tool.Refused, match="^the work folder: "):
        tool.open_work(work, NO_POWERSHELL)


def test_lines_of_keeps_the_non_empty_lines_stripped():
    assert tool.lines_of(" one \r\n\r\n  \ntwo\n") == ["one", "two"]
    assert tool.lines_of("") == [] and tool.lines_of(None) == []


def test_count_ok_counts_the_pinned_files_reported_ok():
    assert tool.count_ok(["a.json: OK", "b.json: FAILED", "c.json: FAILED open or read", "d.csv: OK"]) == 2
    assert tool.count_ok([]) == 0


def test_a_step_announces_itself_and_stops_on_a_failing_exit_status():
    assert tool.step("sync", "uv sync") == (
        "[Console]::Out.WriteLine('windows_host: step sync')\nuv sync\n"
        "if ($LASTEXITCODE -ne 0) { [Console]::Error.WriteLine('windows_host: the host step sync failed with exit "
        "status ' + $LASTEXITCODE); exit 1 }\n")


def test_main_names_missing_host_tools(host, capsys):
    host.setattr(tool, "prepare", lambda work: pytest.fail("prepared despite a missing tool"))
    runner = Runner(missing=("uv",))
    assert tool.main(["quick-start", "--work", WORK], runner) == 2
    assert len(runner.scripts) == 1 and "the host lacks uv" in capsys.readouterr().err


def test_a_failing_host_step_stops_before_the_comparison(host, capsys):
    host.setattr(tool, "compare", lambda folder: pytest.fail("compared after a failed step"))
    runner = Runner(status=1)
    assert tool.main(["quick-start", "--work", WORK], runner) == 1
    assert len(runner.scripts) == 2 and COMMIT in runner.scripts[1]
    assert "a host step failed with exit status 1" in capsys.readouterr().err


def test_a_differing_file_is_named_and_exits_1(host, capsys):
    folders = []
    host.setattr(tool, "compare", lambda folder: folders.append(folder) or
                 (1, ["search.result.json: OK", "changes.json: FAILED", "state-00/response.json: FAILED open or read"]))
    assert tool.main(["quick-start", "--work", WORK], Runner()) == 1
    assert [str(folder) for folder in folders] == ["/mnt/c/tmp/deltarecon-test/work/runs/search"]
    out = capsys.readouterr().out
    assert "changes.json: FAILED" in out and "state-00/response.json: FAILED open or read" in out
    assert "1 pinned files OK" in out and "Python 3.14.9" in out


def test_all_files_ok_exits_0(host, capsys):
    host.setattr(tool, "compare", lambda folder: (0, ["search.result.json: OK", "changes.json: OK"]))
    assert tool.main(["quick-start", "--work", WORK], Runner()) == 0
    out = capsys.readouterr().out
    assert f"carrying commit {COMMIT}" in out and "2 pinned files OK" in out


def test_the_default_work_folder_is_under_c_tmp(host, capsys):
    host.setattr(tool, "compare", lambda folder: (0, []))
    runner = Runner()
    assert tool.main(["quick-start"], runner) == 0
    assert "C:\\tmp\\deltarecon-windows\\" in capsys.readouterr().out


def test_compare_reports_each_pinned_file(tmp_path):
    (tmp_path / "search").mkdir()
    (tmp_path / "search" / "a.json").write_bytes(b"a")
    (tmp_path / "search" / "b.json").write_bytes(b"changed")
    pin = tmp_path / "pin"
    pin.write_text("".join(f"{hashlib.sha256(data).hexdigest()}  {name}\n"
                           for name, data in (("a.json", b"a"), ("b.json", b"b"), ("c.json", b"c"))))
    status, lines = tool.compare(tmp_path / "search", pin)
    assert status == 1
    assert "a.json: OK" in lines and "b.json: FAILED" in lines and "c.json: FAILED open or read" in lines
    assert tool.compare(tmp_path / "none", pin)[0] == 1
