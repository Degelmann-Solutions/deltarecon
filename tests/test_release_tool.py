"""The release tool ``tools/release.py``: fast tests with a fake builder and a fake git.

No test starts uv, ``powershell.exe`` or the network; the only command started is the local
``sha256sum``.
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess

import pytest

from tools import assembly, common, python_runtime, quick_start_steps, targets
from tools import release as tool

VERSION, PYTHON = python_runtime.project()
COMMIT = "0123456789abcdef0123456789abcdef01234567"
LINUX_ARCHIVE = f"deltarecon-{VERSION}-x86_64-unknown-linux-gnu.tar.gz"
WINDOWS_ARCHIVE = f"deltarecon-{VERSION}-x86_64-pc-windows-msvc.zip"


class FakeGit:
    """Answers ``status --porcelain`` and ``rev-parse HEAD`` as git_text does: stripped text, None on failure."""

    def __init__(self, status: str = "", commit: str | None = COMMIT):
        self.status, self.commit, self.calls = status, commit, []

    def __call__(self, *arguments):
        self.calls.append(arguments)
        if arguments == ("status", "--porcelain"):
            return self.status.strip()
        if arguments == ("rev-parse", "HEAD"):
            return self.commit
        raise AssertionError(f"unexpected git call {arguments}")


class FakeBuilder:
    """Writes a small archive per target, as ``build`` names it, and records the calls."""

    def __init__(self, after=None):
        self.calls, self.after = [], after

    def __call__(self, output, source, target):
        self.calls.append((output, source, target))
        output.mkdir(parents=True, exist_ok=True)
        archive = output / targets.archive_name(VERSION, target)
        archive.write_bytes(f"archive of {target}\n".encode())
        if self.after:
            self.after(target)
        return archive


def test_a_clean_tree_gives_both_archives_the_sums_and_the_notes(tmp_path):
    output = tmp_path / "release"
    builder = FakeBuilder()
    commit, archives = tool.release(output, "SOURCE", builder=builder, git=FakeGit())
    assert commit == COMMIT
    assert [archive.name for archive in archives] == [LINUX_ARCHIVE, WINDOWS_ARCHIVE]
    assert builder.calls == [(output, "SOURCE", "x86_64-unknown-linux-gnu"),
                             (output, "SOURCE", "x86_64-pc-windows-msvc")]
    assert sorted(path.name for path in output.iterdir()) == sorted(
        [LINUX_ARCHIVE, WINDOWS_ARCHIVE, "SHA256SUMS", "release-notes.md"])
    digests = {name: hashlib.sha256((output / name).read_bytes()).hexdigest()
               for name in (LINUX_ARCHIVE, WINDOWS_ARCHIVE)}
    sums = (output / "SHA256SUMS").read_bytes()
    assert sums == "".join(f"{digests[name]}  {name}\n" for name in sorted(digests)).encode()
    assert b"\r" not in sums


@pytest.mark.skipif(shutil.which("sha256sum") is None, reason="sha256sum is not on PATH")
def test_the_sums_pass_sha256sum_in_the_release_folder(tmp_path):
    output = tmp_path / "release"
    tool.release(output, "SOURCE", builder=FakeBuilder(), git=FakeGit())
    done = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=output, capture_output=True, text=True)
    assert done.returncode == 0, done.stdout + done.stderr
    assert done.stdout.splitlines() == [f"{WINDOWS_ARCHIVE}: OK", f"{LINUX_ARCHIVE}: OK"]


def test_the_notes_name_the_commit_the_tag_and_both_hashes(tmp_path):
    output = tmp_path / "release"
    tool.release(output, str(tmp_path / "source"), builder=FakeBuilder(), git=FakeGit())
    notes = (output / "release-notes.md").read_bytes().decode("utf-8")
    assert notes.startswith(f"# DeltaRecon {VERSION}\n")
    assert f"`v{VERSION}`" in notes and COMMIT in notes
    for name, platform in ((LINUX_ARCHIVE, "Linux x86-64"), (WINDOWS_ARCHIVE, "Windows x86-64")):
        digest = hashlib.sha256((output / name).read_bytes()).hexdigest()
        assert f"| {platform} | `{name}` | `{digest}` |" in notes
    assert f"CPython {PYTHON}" in notes
    assert ("https://github.com/Degelmann-Solutions/deltarecon/blob/"
            f"v{VERSION}/README.md#quick-start") in notes
    assert "sha256sum -c SHA256SUMS" in notes and "Get-FileHash -Algorithm SHA256" in notes
    assert "not signed" in notes
    assert str(tmp_path) not in notes and "\r" not in notes


def test_the_notes_start_with_the_demo(tmp_path):
    output = tmp_path / "release"
    tool.release(output, "SOURCE", builder=FakeBuilder(), git=FakeGit())
    notes = (output / "release-notes.md").read_text("utf-8")
    demo, holds = notes.index("\n## Start with the demo\n"), notes.index("\n## What a package holds\n")
    assert notes.index("| Platform | Archive | SHA-256 |") < demo < holds
    section = notes[demo:holds]
    assert "double-click `quickstart.cmd`" in section
    assert "```bat\nquickstart.cmd\n```" in section and "```powershell\n.\\quickstart.cmd\n```" in section
    assert "\n./quickstart\n```" in section
    assert f"cd deltarecon-{VERSION}-x86_64-unknown-linux-gnu\n" in section
    assert "`LIESMICH.txt`" in section and "`README.txt`" in section
    listed = notes[holds:]
    for name in ("`quickstart`", "`quickstart.cmd`", "`LIESMICH.txt`", "`README.txt`"):
        assert name in listed, name


def test_the_same_inputs_give_the_same_notes(tmp_path):
    texts = []
    for name in ("one", "two"):
        output = tmp_path / name
        tool.release(output, str(tmp_path / name / "source"), builder=FakeBuilder(), git=FakeGit())
        texts.append((output / "release-notes.md").read_bytes())
    assert texts[0] == texts[1]


@pytest.mark.parametrize("status", [" M README.md\n", "?? new-file.txt\n", "M  tools/release.py\n?? notes\n"])
def test_a_dirty_tree_is_refused_and_nothing_is_built(tmp_path, monkeypatch, capsys, status):
    builder = FakeBuilder()
    monkeypatch.setattr(assembly, "build", builder)
    monkeypatch.setattr(common, "git_text", FakeGit(status=status))
    assert tool.main(["--output", str(tmp_path / "release")]) == 2
    error = capsys.readouterr().err
    assert error.startswith("release: the working tree is not clean: ")
    for line in status.splitlines():
        assert line[3:] in error
    assert builder.calls == [] and not (tmp_path / "release").exists()


def test_an_existing_output_is_refused(tmp_path, monkeypatch, capsys):
    builder = FakeBuilder()
    monkeypatch.setattr(assembly, "build", builder)
    monkeypatch.setattr(common, "git_text", FakeGit())
    output = tmp_path / "release"
    output.mkdir()
    assert tool.main(["--output", str(output)]) == 2
    assert f"release: the output {output} exists already" in capsys.readouterr().err
    assert builder.calls == [] and list(output.iterdir()) == []


def test_a_failing_git_is_refused(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(assembly, "build", FakeBuilder())
    monkeypatch.setattr(common, "git_text", lambda *arguments: None)
    assert tool.main(["--output", str(tmp_path / "release")]) == 2
    assert "release: git status failed" in capsys.readouterr().err


@pytest.mark.parametrize("change", ["head", "tree"])
def test_a_change_during_the_build_fails_without_sums_or_notes(tmp_path, monkeypatch, capsys, change):
    git = FakeGit()

    def move(target):
        if target == "x86_64-pc-windows-msvc":
            if change == "head":
                git.commit = "f" * 40
            else:
                git.status = "?? stray.txt"

    monkeypatch.setattr(assembly, "build", FakeBuilder(after=move))
    monkeypatch.setattr(common, "git_text", git)
    output = tmp_path / "release"
    assert tool.main(["--output", str(output)]) == 1
    error = capsys.readouterr().err
    assert error.startswith("release: ") and "changed during the build" in error
    assert not (output / "SHA256SUMS").exists() and not (output / "release-notes.md").exists()


@pytest.mark.parametrize("kind, status", [("Refused", 2), ("Failed", 1)])
def test_a_build_that_refuses_or_fails_passes_its_message(tmp_path, monkeypatch, capsys, kind, status):
    def builder(output, source, target):
        raise getattr(common, kind)("uv is not on PATH")

    monkeypatch.setattr(assembly, "build", builder)
    monkeypatch.setattr(common, "git_text", FakeGit())
    assert tool.main(["--output", str(tmp_path / "release")]) == status
    assert capsys.readouterr().err == "release: uv is not on PATH\n"


def test_main_passes_the_source_and_defaults_to_the_build_source(tmp_path, monkeypatch, capsys):
    builder = FakeBuilder()
    monkeypatch.setattr(assembly, "build", builder)
    monkeypatch.setattr(common, "git_text", FakeGit())
    assert tool.main(["--output", str(tmp_path / "one")]) == 0
    assert tool.main(["--output", str(tmp_path / "two"), "--source", "/some/clone"]) == 0
    assert [call[1] for call in builder.calls] == [assembly.DEFAULT_SOURCE] * 2 + ["/some/clone"] * 2
    assert f"of commit {COMMIT}" in capsys.readouterr().out


def test_the_default_output_is_the_release_folder_of_the_version():
    assert tool.default_output(VERSION) == tool.ROOT / "dist" / f"release-v{VERSION}"
    assert tool.parse([]).output is None


def test_the_package_quick_start_runs_the_checkout_steps():
    measure = quick_start_steps
    text = (tool.ROOT / "README.md").read_text("utf-8")
    section = text[text.index("### From a package"):text.index("### From a checkout")]
    blocks = re.findall(r"```(sh|bat|powershell)\n(.*?)```", section, re.S)
    # The guided demo comes first: Linux, cmd, PowerShell; then the single commands in the same order.
    assert [language for language, _ in blocks] == ["sh", "bat", "powershell", "sh", "bat", "powershell"]
    assert blocks[0][1].splitlines()[-1] == "./quickstart"
    assert blocks[1][1] == "quickstart.cmd\n" and blocks[2][1] == ".\\quickstart.cmd\n"
    linux, windows, powershell = (body for _, body in blocks[3:])
    steps = [step["argv"][3:] for step in measure.STEPS.values()]
    assert [line.split() for line in linux.splitlines()] == [["./deltarecon", *argv] for argv in steps]
    expected = [["deltarecon.cmd", *(argument.replace("/", "\\") if argument.startswith(("runs/", "profiles/"))
                                     else argument for argument in argv)] for argv in steps]
    assert [line.split() for line in windows.splitlines()] == expected
    assert [line.split() for line in powershell.splitlines()] == [[".\\" + line[0], *line[1:]] for line in expected]
