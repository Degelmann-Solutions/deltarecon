"""The package builder ``tools/build_package.py`` and its library modules (``tools/targets.py``,
``tools/python_runtime.py``, ``tools/assembly.py``, ``tools/guides.py``, ``tools/package_check.py``,
``tools/check_windows.py``): fast tests without network and without uv.

The launcher runs against a fake ``python/bin/python3`` script; the download goes through an
injected fetcher; the only commands started are ``/bin/sh`` and local ``git``. No test starts
``powershell.exe``: the Windows host scripts are checked as text.
"""
from __future__ import annotations

import hashlib
import os
import stat
import subprocess
import tarfile
import tomllib
import zipfile
from pathlib import PureWindowsPath

from packaging.markers import default_environment

import pytest

from conftest import ROOT, git
from tools import assembly, check_windows, common, guides, host, package_check, python_runtime, targets
from tools import build_package as tool
from tools import quick_start_steps as measure
LINUX = targets.TARGETS["x86_64-unknown-linux-gnu"]
WINDOWS = targets.TARGETS["x86_64-pc-windows-msvc"]
# The version of pyproject.toml: the archive names that check and build accept carry it.
VERSION = python_runtime.project()[0]

# A Python that prints what the launcher hands it, one item per line; printf is a shell builtin.
FAKE_PYTHON = '#!/bin/sh\nprintf "%s\\n" "$DELTARECON_REPOSITORIES" "$@"\n'


def fake_package(folder):
    folder.mkdir(parents=True)
    python = folder / "python" / "bin" / "python3"
    python.parent.mkdir(parents=True)
    python.write_text(FAKE_PYTHON, "utf-8")
    python.chmod(0o755)
    return assembly.write_launcher(folder)


@pytest.mark.parametrize("relative", [False, True])
def test_launcher_runs_with_an_empty_path_from_another_folder(tmp_path, relative):
    package = tmp_path / "pack age"
    launcher = fake_package(package)
    elsewhere, empty = tmp_path / "elsewhere", tmp_path / "empty"
    elsewhere.mkdir()
    empty.mkdir()
    called = os.path.join("..", "pack age", "deltarecon") if relative else str(launcher)
    arguments = ["run", "a b/request.json", "", "--x=$HOME *"]
    done = subprocess.run([called, *arguments], cwd=elsewhere, capture_output=True, text=True,
                          env={"PATH": str(empty), common.REPOSITORIES_VARIABLE: "/somewhere/else"})
    assert done.returncode == 0, done.stderr
    assert done.stdout.split("\n")[:-1] == [str(package.resolve()), "-m", "degelmann.deltarecon", *arguments]


def test_launcher_is_executable_and_keeps_pythonpath(tmp_path):
    launcher = fake_package(tmp_path / "package")
    assert stat.S_IMODE(launcher.stat().st_mode) == 0o755
    text = launcher.read_text("utf-8")
    assert text.startswith("#!/bin/sh\n") and "\r" not in text
    assert ' -I' not in text and ' -E' not in text and "PYTHONPATH" not in text


def test_pins_match_pyproject():
    table = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["project"]
    version, python = python_runtime.project()
    assert (version, f"=={python}") == (table["version"], table["requires-python"])
    assert set(targets.TARGETS) == {targets.TARGET, targets.WINDOWS_TARGET}
    assert targets.package_name(version) == f"deltarecon-{version}-x86_64-unknown-linux-gnu"
    for name, target in targets.TARGETS.items():
        assert f"cpython-{python}%2B" in target["url"] and name in target["url"]
        assert len(target["sha256"]) == 64 and all(c in "0123456789abcdef" for c in target["sha256"])
        assert target["markers"]["python_full_version"] == python
        assert target["markers"]["python_version"] == python.rsplit(".", 1)[0]
        assert set(target["markers"]) == set(default_environment())
    assert {name: target["archive"] for name, target in targets.TARGETS.items()} == {
        targets.TARGET: "tar.gz", targets.WINDOWS_TARGET: "zip"}


def test_the_windows_row():
    assert WINDOWS["python"] == "python/python.exe" and WINDOWS["site_packages"] == "python/Lib/site-packages"
    assert WINDOWS["patchlevel"] == "python/include/patchlevel.h"
    assert {key: WINDOWS["markers"][key] for key in ("sys_platform", "os_name", "platform_system",
                                                     "platform_machine")} == {
        "sys_platform": "win32", "os_name": "nt", "platform_system": "Windows", "platform_machine": "AMD64"}
    different = {key for key in LINUX["markers"] if LINUX["markers"][key] != WINDOWS["markers"][key]}
    assert different == {"sys_platform", "os_name", "platform_system", "platform_machine"}


@pytest.mark.parametrize("target", [LINUX, WINDOWS], ids=["linux", "windows"])
def test_the_python_version_is_read_from_the_header(tmp_path, target):
    header = tmp_path / target["patchlevel"]
    header.parent.mkdir(parents=True)
    header.write_text('#define PY_MINOR_VERSION        14\n#define PY_VERSION              "3.14.9"\n'
                      "#define PY_VERSION_HEX 0\n", "utf-8")
    assert python_runtime.require_python(tmp_path, target, "3.14.9") == "3.14.9"
    with pytest.raises(common.Refused, match="the Python build is 3.14.9, requires-python pins 3.14.8"):
        python_runtime.require_python(tmp_path, target, "3.14.8")
    header.write_text("#define PY_MINOR_VERSION 14\n", "utf-8")
    with pytest.raises(common.Refused, match="no PY_VERSION"):
        python_runtime.header_version(tmp_path, target)


def test_the_windows_launcher_text(tmp_path):
    launcher = assembly.write_launcher(tmp_path, WINDOWS)
    assert launcher.name == "deltarecon.cmd"
    raw = launcher.read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n") and raw.endswith(b"\r\n")
    lines = raw.decode("utf-8").split("\r\n")
    assert "setlocal" in lines
    assert lines.index("setlocal") < lines.index('set "DELTARECON_REPOSITORIES=%~dp0"')
    assert 'set "DELTARECON_REPOSITORIES=%DELTARECON_REPOSITORIES:~0,-1%"' in lines
    assert '"%~dp0python\\python.exe" -m degelmann.deltarecon %*' in lines
    assert lines[-2:] == ["exit /b %ERRORLEVEL%", ""]
    text = raw.decode("utf-8")
    assert " -I" not in text and " -E" not in text and "PYTHONPATH" not in text


def test_the_windows_markers_keep_tzdata():
    assert ("tzdata", "2026.4") in package_check.expected_packages(EXPORT, WINDOWS["markers"], "0.1.0")


def test_a_cached_download_with_another_hash_is_deleted(tmp_path):
    cached = tmp_path / "cpython-3.14.9+20261021-x86_64-unknown-linux-gnu-install_only_stripped.tar.gz"
    cached.write_bytes(b"not the pinned archive")
    found = hashlib.sha256(b"not the pinned archive").hexdigest()

    def fetcher(url, path):
        raise AssertionError("a cached file is not downloaded again")

    with pytest.raises(common.Refused) as refusal:
        python_runtime.fetch_python(LINUX, tmp_path, fetcher)
    assert found in str(refusal.value) and LINUX["sha256"] in str(refusal.value)
    assert not cached.exists()


def test_a_download_is_verified_and_cached(tmp_path):
    content = b"an archive"
    target = dict(LINUX, sha256=hashlib.sha256(content).hexdigest())
    calls = []

    def fetcher(url, path):
        calls.append(url)
        path.write_bytes(content)

    first = python_runtime.fetch_python(target, tmp_path / "cache", fetcher)
    second = python_runtime.fetch_python(target, tmp_path / "cache", fetcher)
    assert first == second and first.read_bytes() == content and calls == [target["url"]]
    assert first.name.startswith("cpython-3.14.9+") and not list(first.parent.glob("*.partial"))


EXPORT = """\
# This file was autogenerated by uv via the following command:
#    uv export --locked --no-dev --no-hashes --format requirements-txt
-e .
numpy==2.5.3
    # via pandas
Python-DateUtil==2.9.0.post0
tzdata==2026.4 ; sys_platform == 'emscripten' or sys_platform == 'win32'
    # via pandas
"""


def test_expected_packages_follow_the_target_markers():
    assert package_check.expected_packages(EXPORT, LINUX["markers"], "0.1.0") == [
        ("degelmann-deltarecon", "0.1.0"), ("numpy", "2.5.3"), ("python-dateutil", "2.9.0.post0")]
    assert ("tzdata", "2026.4") in package_check.expected_packages(EXPORT, WINDOWS["markers"], "0.1.0")


def test_pip_and_the_script_folder_are_removed(tmp_path):
    site = tmp_path / LINUX["site_packages"]
    for path in ("pip/__init__.py", "pip-26.2.2.dist-info/METADATA", "bin/deltarecon", "numpy/__init__.py",
                 "pipx_like/__init__.py"):
        (site / path).parent.mkdir(parents=True, exist_ok=True)
        (site / path).write_text("", "utf-8")
    python_bin = tmp_path / "python" / "bin"
    python_bin.mkdir()
    for name in ("pip", "pip3", "pip3.14", "python3.14"):
        (python_bin / name).write_text("", "utf-8")
    (python_bin / "python3").symlink_to("python3.14")
    removed = assembly.remove_pip(tmp_path, LINUX)
    assert removed == ["python/bin/pip", "python/bin/pip3", "python/bin/pip3.14",
                       "python/lib/python3.14/site-packages/bin", "python/lib/python3.14/site-packages/pip",
                       "python/lib/python3.14/site-packages/pip-26.2.2.dist-info"]
    assert sorted(p.name for p in site.iterdir()) == ["numpy", "pipx_like"]
    assert sorted(p.name for p in python_bin.iterdir()) == ["python3", "python3.14"]


def test_pip_and_the_script_folders_are_removed_on_windows(tmp_path):
    site = tmp_path / WINDOWS["site_packages"]
    for path in ("pip/__init__.py", "pip-26.2.2.dist-info/METADATA", "Scripts/deltarecon.exe", "numpy/__init__.py"):
        (site / path).parent.mkdir(parents=True, exist_ok=True)
        (site / path).write_text("", "utf-8")
    scripts = tmp_path / "python" / "Scripts"
    scripts.mkdir()
    for name in ("pip.exe", "pip3.exe", ".empty"):
        (scripts / name).write_text("", "utf-8")
    removed = assembly.remove_pip(tmp_path, WINDOWS)
    assert removed == ["python/Lib/site-packages/Scripts", "python/Lib/site-packages/pip",
                       "python/Lib/site-packages/pip-26.2.2.dist-info", "python/Scripts/pip.exe",
                       "python/Scripts/pip3.exe"]
    assert sorted(p.name for p in site.iterdir()) == ["numpy"]
    assert sorted(p.name for p in scripts.iterdir()) == [".empty"]


def test_chain_commands_on_windows_paths():
    work = PureWindowsPath("C:\\tmp\\check")
    package = work / "package" / "deltarecon-0.1.0-x86_64-pc-windows-msvc"
    commands = package_check.chain_commands(package, work / "runs", measure.STEPS, measure.rewrite, "deltarecon.cmd")
    assert [name for name, _, _ in commands] == list(measure.STEPS)
    for _, command, _ in commands:
        assert command[0] == "C:\\tmp\\check\\package\\deltarecon-0.1.0-x86_64-pc-windows-msvc\\deltarecon.cmd"
        assert not any("/" in argument for argument in command if argument.startswith("C:"))
    search = dict((name, command) for name, command, _ in commands)["search"]
    assert search[search.index("--output") + 1] == "C:\\tmp\\check\\runs\\search"
    assert str(package) + "\\profiles\\tolerance-bruttobeitrag.json" in search
    request = dict((name, command) for name, command, _ in commands)["request"]
    assert request[-1] == "C:\\tmp\\check\\runs\\n-full\\request.json"


def test_chain_commands_run_the_launcher(tmp_path):
    package, runs = tmp_path / "package", tmp_path / "runs"
    commands = package_check.chain_commands(package, runs, measure.STEPS, measure.rewrite)
    assert [name for name, _, _ in commands] == list(measure.STEPS)
    assert [expect for _, _, expect in commands] == [step["expect"] for step in measure.STEPS.values()]
    for name, command, _ in commands:
        assert command[0] == str(package / "deltarecon") and command[1] == name
        assert "uv" not in command and not any(argument.startswith(("runs/", "profiles/")) for argument in command)
    search = dict((name, command) for name, command, _ in commands)["search"]
    assert str(package / "profiles" / "tolerance-bruttobeitrag.json") in search
    assert search[search.index("--output") + 1] == str(runs / "search")


def test_the_archive_keeps_the_exec_bit_and_a_relative_link(tmp_path):
    folder = tmp_path / "deltarecon-test"
    (folder / "bin").mkdir(parents=True)
    (folder / "bin" / "python3.14").write_text("#!/bin/sh\n", "utf-8")
    (folder / "bin" / "python3.14").chmod(0o755)
    (folder / "bin" / "python3").symlink_to("python3.14")
    archive = tmp_path / "out" / "deltarecon-test.tar.gz"
    archive.parent.mkdir()
    assembly.make_archive(folder, archive)
    with tarfile.open(archive) as tar:
        assert {member.name.split("/")[0] for member in tar.getmembers()} == {"deltarecon-test"}
        assert {(m.uid, m.gid, m.uname, m.gname) for m in tar.getmembers()} == {(0, 0, "", "")}
    unpacked = assembly.unpack(archive, tmp_path / "unpacked")
    assert unpacked == tmp_path / "unpacked" / "deltarecon-test"
    assert os.readlink(unpacked / "bin" / "python3") == "python3.14"
    assert stat.S_IMODE((unpacked / "bin" / "python3.14").stat().st_mode) == 0o755


def test_the_zip_has_one_top_folder(tmp_path):
    folder = tmp_path / "deltarecon-test"
    (folder / "python" / "Scripts").mkdir(parents=True)
    (folder / "python" / "Scripts" / ".empty").write_text("", "utf-8")
    (folder / "empty").mkdir()
    (folder / "deltarecon.cmd").write_bytes(b"@echo off\r\n")
    archive = tmp_path / "out" / "deltarecon-test.zip"
    archive.parent.mkdir()
    assembly.make_archive(folder, archive)
    with zipfile.ZipFile(archive) as zip_file:
        assert {name.split("/")[0] for name in zip_file.namelist()} == {"deltarecon-test"}
        assert {info.compress_type for info in zip_file.infolist() if not info.is_dir()} == {zipfile.ZIP_DEFLATED}
    unpacked = assembly.unpack(archive, tmp_path / "unpacked")
    assert unpacked == tmp_path / "unpacked" / "deltarecon-test"
    assert (unpacked / "deltarecon.cmd").read_bytes() == b"@echo off\r\n"
    assert (unpacked / "empty").is_dir() and (unpacked / "python" / "Scripts" / ".empty").is_file()


def test_the_zip_refuses_a_symbolic_link(tmp_path):
    folder = tmp_path / "deltarecon-test"
    folder.mkdir()
    (folder / "python.exe").write_text("", "utf-8")
    (folder / "python3.exe").symlink_to("python.exe")
    archive = tmp_path / "deltarecon-test.zip"
    with pytest.raises(common.Failed, match="symbolic link"):
        assembly.make_archive(folder, archive)
    assert sorted(p.name for p in tmp_path.iterdir()) == ["deltarecon-test"]


def test_an_unpacked_zip_with_two_top_folders_is_refused(tmp_path):
    archive = tmp_path / "two.zip"
    with zipfile.ZipFile(archive, "w") as zip_file:
        zip_file.writestr("a/x", "")
        zip_file.writestr("b/y", "")
    with pytest.raises(common.Failed, match="2 top folders"):
        assembly.unpack(archive, tmp_path / "unpacked")


def test_the_target_follows_the_archive_name(tmp_path):
    assert targets.target_of(tmp_path / "deltarecon-0.1.0-x86_64-unknown-linux-gnu.tar.gz", "0.1.0") == targets.TARGET
    assert targets.target_of(tmp_path / "deltarecon-0.1.0-x86_64-pc-windows-msvc.zip", "0.1.0") == targets.WINDOWS_TARGET
    for name in ("deltarecon-0.1.0-x86_64-pc-windows-msvc.tar.gz", "deltarecon-0.1.0-x86_64-unknown-linux-gnu.zip",
                 "deltarecon-0.0.9-x86_64-pc-windows-msvc.zip"):
        with pytest.raises(common.Refused, match="names no target"):
            targets.target_of(tmp_path / name, "0.1.0")


def test_the_target_follows_the_name_given_not_a_link_target(tmp_path, capsys):
    real = tmp_path / "deltarecon-0.1.0-x86_64-unknown-linux-gnu.tar.gz"
    real.write_bytes(b"")
    link = tmp_path / "foo.zip"
    link.symlink_to(real.name)
    assert tool.main(["check", str(link)]) == 2
    assert "the archive name foo.zip names no target" in capsys.readouterr().err


def test_check_refuses_an_unknown_archive_name(tmp_path, capsys):
    archive = tmp_path / "foo.zip"
    archive.write_bytes(b"")
    assert tool.main(["check", str(archive)]) == 2
    assert "names no target" in capsys.readouterr().err


def test_the_windows_host_script():
    work = "C:\\tmp\\deltarecon-package-check\\20261028T000000Z"
    name = "deltarecon-0.1.0-x86_64-pc-windows-msvc"
    host_work = PureWindowsPath(work)
    commands = package_check.chain_commands(host_work / "package" / name, host_work / "runs", measure.STEPS, measure.rewrite,
                                   "deltarecon.cmd")
    script = check_windows.windows_chain_script(work, name + ".zip", name, commands)
    assert f"[System.IO.Compression.ZipFile]::ExtractToDirectory('{work}\\{name}.zip', '{work}\\package')" in script
    assert f"$env:PATH = '{work}\\empty-path'" in script
    for variable in ("PYTHONPATH", "PYTHONHOME", "VIRTUAL_ENV", "DELTARECON_REPOSITORIES"):
        assert f"'{variable}'" in script
    assert "foreach ($name in 'uv', 'git')" in script and "Get-Command $name -CommandType Application" in script
    position = script.index("foreach ($name in 'uv', 'git')")
    for step, command, expect in commands:
        call = "& " + " ".join(host.literal(argument) for argument in command)
        assert script.index(call) > position
        position = script.index(call)
        assert f"if ($code -ne {expect})" in script[position:]
        assert f"'build_package: chain: {step} exit '" in script and f"(expected {expect}) in " in script
    assert "if ($code -ne 1)" in script  # the regression step
    with pytest.raises(host.Refused):
        check_windows.windows_chain_script("/mnt/c/tmp/x", name + ".zip", name, commands)


def test_the_windows_python_scripts():
    work = "C:\\tmp\\w"
    python = "C:\\tmp\\w\\package\\p\\python\\python.exe"
    lister = check_windows.windows_python_script(work, python, ["-X", "utf8", "-I", "C:\\tmp\\w\\scripts\\l.py"], "list")
    assert "$env:PATH = 'C:\\tmp\\w\\empty-path'" in lister and "PYTHONPATH =" not in lister
    assert f"& '{python}' '-X' 'utf8' '-I' 'C:\\tmp\\w\\scripts\\l.py'" in lister
    probe = check_windows.windows_python_script(work, python, ["-X", "utf8", "C:\\tmp\\w\\scripts\\p.py"], "probe",
                                       pythonpath="C:\\tmp\\w\\engines")
    assert probe.index("Remove-Item") < probe.index("$env:PYTHONPATH = 'C:\\tmp\\w\\engines'") < probe.index("& ")
    assert f"& '{python}' '-X' 'utf8' 'C:\\tmp\\w\\scripts\\p.py'" in probe and "'-I'" not in probe


@pytest.mark.parametrize("case", ["no powershell", "wsl work", "unc work", "other drive", "existing work"])
def test_a_windows_check_that_cannot_start_copies_nothing(tmp_path, monkeypatch, capsys, case):
    archive = tmp_path / f"deltarecon-{VERSION}-x86_64-pc-windows-msvc.zip"
    archive.write_bytes(b"")

    def refuse(*arguments, **options):
        raise AssertionError("nothing is copied or run")

    for name in ("copyfile", "copy2", "copytree"):
        monkeypatch.setattr(check_windows.shutil, name, refuse)
    monkeypatch.setattr(host, "powershell", refuse)
    monkeypatch.setattr(host, "host_exists", (lambda windows: True) if case == "existing work" else refuse)
    monkeypatch.setattr(host, "powershell_path",
                        (lambda: None) if case == "no powershell" else (lambda: "/fake/powershell.exe"))
    work = {"no powershell": [], "wsl work": ["--work", "/mnt/c/tmp/x"],
            "unc work": ["--work", "\\\\wsl.localhost\\Ubuntu\\tmp\\x"], "other drive": ["--work", "D:\\tmp\\x"],
            "existing work": ["--work", "C:\\tmp\\deltarecon-package-check\\exists"]}
    assert tool.main(["check", str(archive), *work[case]]) == 2
    error = capsys.readouterr().err
    if case == "existing work":
        assert error == "build_package: the work folder C:\\tmp\\deltarecon-package-check\\exists exists already\n"
    elif case == "no powershell":
        assert error == ("build_package: powershell.exe is not on PATH; a Windows archive is checked in WSL on a "
                         "Windows host\n")
    else:
        assert error.startswith("build_package: the work folder: ")
    assert sorted(p.name for p in tmp_path.iterdir()) == [archive.name]


@pytest.mark.parametrize("existing", [f"deltarecon-{VERSION}-x86_64-unknown-linux-gnu",
                                      f"deltarecon-{VERSION}-x86_64-unknown-linux-gnu.tar.gz"])
def test_build_with_an_existing_output_writes_nothing(tmp_path, monkeypatch, capsys, existing):
    def refuse(*arguments, **options):
        raise AssertionError("nothing runs when the output exists")

    monkeypatch.setattr(assembly, "fetch_python", refuse)
    monkeypatch.setattr(assembly, "run", refuse)
    (tmp_path / existing).mkdir()
    before = sorted(tmp_path.iterdir())
    assert tool.main(["build", "--output", str(tmp_path)]) == 2
    assert sorted(tmp_path.iterdir()) == before
    assert "exists already" in capsys.readouterr().err


def test_a_shallow_clone_is_refused(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "--quiet")
    for number in (1, 2):
        git(source, "-c", "user.name=t", "-c", "user.email=t@example.org", "commit", "--quiet", "--allow-empty",
            "-m", f"commit {number}")
    shallow = tmp_path / "shallow"
    git(tmp_path, "clone", "--quiet", "--depth", "1", source.as_uri(), str(shallow))
    with pytest.raises(common.Failed, match="shallow"):
        assembly.clone_history(str(shallow), tmp_path / "from-shallow")
    assembly.clone_history(str(source), tmp_path / "full")
    assert not assembly.is_shallow(tmp_path / "full")


def test_check_refuses_a_work_folder_inside_the_checkout(tmp_path, capsys):
    archive = tmp_path / f"deltarecon-{VERSION}-x86_64-unknown-linux-gnu.tar.gz"
    archive.write_bytes(b"")
    assert tool.main(["check", str(archive), "--work", str(ROOT / "runs" / "package-check-refused")]) == 2
    assert "inside this checkout" in capsys.readouterr().err
    assert not (ROOT / "runs" / "package-check-refused").exists()


# A launcher that prints its folder and arguments and exits with $FAKE_STATUS; builtins only.
FAKE_LAUNCHER = '#!/bin/sh\nprintf "%s\\n" "$(pwd -P)" "$@"\nexit ${FAKE_STATUS:-0}\n'


def fake_starter_package(folder):
    folder.mkdir(parents=True)
    launcher = folder / "deltarecon"
    launcher.write_text(FAKE_LAUNCHER, "utf-8")
    launcher.chmod(0o755)
    return assembly.write_launcher(folder, LINUX, "starter")


@pytest.mark.parametrize("relative", [False, True])
@pytest.mark.parametrize("status", [0, 1, 130])
def test_the_starter_runs_the_demo_in_its_folder_with_an_empty_path(tmp_path, relative, status):
    package = tmp_path / "pack age"
    starter = fake_starter_package(package)
    assert starter.name == "quickstart" and stat.S_IMODE(starter.stat().st_mode) == 0o755
    elsewhere, empty = tmp_path / "elsewhere", tmp_path / "empty"
    elsewhere.mkdir()
    empty.mkdir()
    called = os.path.join("..", "pack age", "quickstart") if relative else str(starter)
    arguments = ["--no-pause", "--lang", "de", "a b", ""]
    done = subprocess.run([called, *arguments], cwd=elsewhere, capture_output=True, text=True,
                          stdin=subprocess.DEVNULL, env={"PATH": str(empty), "FAKE_STATUS": str(status)})
    assert done.returncode == status, done.stderr
    # No prompt: the input is not a terminal.
    assert done.stdout.split("\n")[:-1] == [str(package.resolve()), "quickstart", *arguments]


def test_the_starter_waits_for_enter_on_a_terminal(tmp_path):
    starter = fake_starter_package(tmp_path / "package")
    controller, terminal = os.openpty()
    try:
        os.write(controller, b"\n")
        done = subprocess.run([str(starter)], stdin=terminal, capture_output=True, timeout=30,
                              env={"PATH": str(tmp_path), "FAKE_STATUS": "1"})
    finally:
        os.close(controller)
        os.close(terminal)
    assert done.returncode == 1
    assert done.stdout.decode("utf-8").splitlines()[-1] == "Press Enter to close. / Enter schließt das Fenster."


def test_the_linux_starter_text():
    text = targets.STARTER_TEXT
    assert text.startswith("#!/bin/sh\n") and "\r" not in text
    assert '*/*) here=${0%/*} ;;' in text and 'CDPATH= cd -- "$here" || exit 2' in text
    assert text.index('./deltarecon quickstart "$@"') < text.index("status=$?") < text.index("[ -t 0 ]")
    assert text.rstrip().endswith("exit $status")


def test_the_windows_starter_text(tmp_path):
    starter = assembly.write_launcher(tmp_path, WINDOWS, "starter")
    assert starter.name == "quickstart.cmd"
    raw = starter.read_bytes()
    assert raw.count(b"\r\n") == raw.count(b"\n") and raw.endswith(b"\r\n")
    lines = [line for line in raw.decode("utf-8").split("\r\n") if not line.startswith("rem ")]
    assert lines == ["@echo off", "setlocal", 'pushd "%~dp0"', 'call "%~dp0deltarecon.cmd" quickstart %*',
                     'set "status=%ERRORLEVEL%"', "pause", "popd", "exit /b %status%", ""]


README = (ROOT / "README.md").read_text("utf-8")


@pytest.mark.parametrize("lang", ["de", "en"])
@pytest.mark.parametrize("target_name", sorted(targets.TARGETS))
def test_the_guides(lang, target_name):
    text = guides.guide_text(lang, target_name, "9.8.7")
    windows = target_name == targets.WINDOWS_TARGET
    if windows:
        assert text.count("\r\n") == text.count("\n") and text.endswith("\r\n")
    else:
        assert "\r" not in text and text.endswith("\n")
    lines = text.replace("\r\n", "\n").split("\n")
    assert lines[0] == ("DeltaRecon 9.8.7 " + ("für " if lang == "de" else "for ")
                        + ("Windows x86-64" if windows else "Linux x86-64"))
    assert "https://github.com/Degelmann-Solutions/deltarecon/blob/v9.8.7/README.md" in lines
    assert "LICENSE" in text and "--lang de" in text and "--lang en" in text and "--no-pause" in text
    single = [line.strip() for line in lines if line.strip().startswith(("deltarecon.cmd ", ".\\deltarecon.cmd ",
                                                                         "./deltarecon "))]
    first_command = lines.index("    " + single[0])
    if windows:
        assert "SmartScreen" in text and "runs\\quickstart-" in text
        demo = [lines.index("    quickstart.cmd"), lines.index("    .\\quickstart.cmd")]
        cmd = [line for line in single if line.startswith("deltarecon.cmd ")]
        powershell = [line for line in single if line.startswith(".\\deltarecon.cmd ")]
        assert len(cmd) == len(powershell) == 6 and single == cmd + powershell
        assert powershell == [".\\" + line for line in cmd]
        assert lines.index("In cmd:") < lines.index("    " + cmd[0]) < lines.index("In PowerShell:") \
            < lines.index("    " + powershell[0])
        in_readme = cmd + powershell
    else:
        assert "SmartScreen" not in text and "runs/quickstart-" in text and "quickstart.cmd" not in text
        demo = [lines.index("    ./quickstart")]
        assert len(single) == 6
        in_readme = single
    assert max(demo) < first_command
    for line in in_readme:
        assert f"\n{line}\n" in README, line
    assert [line.split()[1] for line in single[:6]] == list(measure.STEPS)


def test_the_guides_are_written_without_bom(tmp_path):
    paths = guides.write_guides(tmp_path, targets.WINDOWS_TARGET, "9.8.7")
    assert [path.name for path in paths] == ["LIESMICH.txt", "README.txt"]
    for path, lang in zip(paths, ("de", "en")):
        raw = path.read_bytes()
        assert not raw.startswith(b"\xef\xbb\xbf")
        assert raw.decode("utf-8") == guides.guide_text(lang, targets.WINDOWS_TARGET, "9.8.7")
    assert "Die geführte Demo" in paths[0].read_text("utf-8")


def test_the_windows_demo_scripts():
    package = "C:\\tmp\\w\\package\\deltarecon-9.8.7-x86_64-pc-windows-msvc"
    demo = check_windows.windows_demo_script(package)
    assert demo == ("@echo off\r\n"
                    f'call "{package}\\quickstart.cmd" --no-pause < NUL\r\n'
                    "exit /b %ERRORLEVEL%\r\n")
    script = check_windows.windows_demo_host_script("C:\\tmp\\w", "C:\\tmp\\w\\scripts\\demo.cmd")
    assert "$env:PATH = 'C:\\tmp\\w\\empty-path'" in script
    for variable in package_check.CLEARED:
        assert f"'{variable}'" in script
    assert script.index("Remove-Item") < script.index("& 'C:\\tmp\\w\\scripts\\demo.cmd'")
    assert "if ($LASTEXITCODE -ne 0)" in script and "guided demo" in script
    with pytest.raises(host.Refused):
        check_windows.windows_demo_host_script("/mnt/c/tmp/w", "C:\\tmp\\w\\scripts\\demo.cmd")


@pytest.mark.parametrize("code, new, compared, holds", [
    (0, ["quickstart-1"], 0, True),
    (1, ["quickstart-1"], 0, False),
    (0, [], 0, False),
    (0, ["quickstart-1", "quickstart-2"], 0, False),
    (0, ["quickstart-1"], 1, False),
])
def test_the_demo_claim(tmp_path, monkeypatch, capsys, code, new, compared, holds):
    calls = []

    def compare(folder):
        calls.append(folder)
        return compared, [f"{folder}: {'OK' if compared == 0 else 'FAILED'}"]

    monkeypatch.setattr(host, "compare", compare)
    old = {tmp_path / "runs" / "quickstart-0"}
    after = old | {tmp_path / "runs" / name for name in new}
    assert package_check.compare_demo(code, old, after) is holds
    assert calls == ([tmp_path / "runs" / new[0] / "search"] if code == 0 and len(new) == 1 else [])
    assert f"starter exit {code}" in capsys.readouterr().out


def test_the_report_names_the_demo_claim(capsys):
    assert package_check.report({"chain and pin": True, "guided demo and pin": False}) is False
    assert "build_package: guided demo and pin: FAILED" in capsys.readouterr().out
