"""The package builder ``tools/build_package.py`` and its library modules (``tools/targets.py``,
``tools/python_runtime.py``, ``tools/assembly.py``, ``tools/guides.py``, ``tools/package_check.py``,
``tools/check_windows.py``): fast tests without network and without uv.

The launcher runs against a fake ``python/bin/python3`` script; the download goes through an
injected fetcher; the only commands started are ``/bin/sh`` and local ``git``. No test starts
``powershell.exe``: the Windows host scripts are checked as text.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import os
import stat
import subprocess
import sys
import tarfile
import tomllib
import zipfile
from pathlib import Path, PureWindowsPath

from packaging.markers import default_environment

import pytest

from conftest import ROOT, git
from tools import assembly, check_linux, check_windows, common, guides, host, package_check, python_runtime, targets
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
    assert done.stdout.split("\n")[:-1] == [str(package.resolve()), "-P", "-s", "-m", "degelmann.deltarecon",
                                           *arguments]


def test_launcher_is_executable_and_keeps_pythonpath(tmp_path):
    launcher = fake_package(tmp_path / "package")
    assert stat.S_IMODE(launcher.stat().st_mode) == 0o755
    text = launcher.read_text("utf-8")
    assert text.startswith("#!/bin/sh\n") and "\r" not in text
    assert ' -I' not in text and ' -E' not in text and "PYTHONPATH" not in text
    assert text.index("unset PYTHONHOME\n") < text.index('exec "$here/python/bin/python3" -P -s -m degelmann.deltarecon')


# The packaged code of ``launched_python``: reports where it was read from, its sys.path, PYTHONHOME,
# whether the user site is in force, and where the probe module of PYTHONPATH was read from.
REPORTER = """import json, os, site, sys
import deltarecon_probe_engine as probe
print(json.dumps({"main": __file__, "path": sys.path, "home": os.environ.get("PYTHONHOME"),
                  "user_site": site.ENABLE_USER_SITE, "probe": probe.__file__}))
"""


def launched_python(folder: Path) -> Path:
    """A package in ``folder`` whose ``python/`` is a real Python (a virtual environment of the
    Python running the tests, with the system site-packages so a user site applies) holding a
    ``degelmann.deltarecon`` that prints ``REPORTER``; its launcher."""
    python = folder / "python"
    subprocess.run([sys.executable, "-m", "venv", "--without-pip", "--system-site-packages", str(python)], check=True)
    site_packages = Path(subprocess.run([str(python / "bin" / "python3"), "-I", "-c",
                                         "import sysconfig; print(sysconfig.get_path('purelib'))"],
                                        capture_output=True, text=True, check=True).stdout.strip())
    main = site_packages / "degelmann" / "deltarecon" / "__main__.py"
    main.parent.mkdir(parents=True)
    (main.parent / "__init__.py").write_text("", "utf-8")
    main.write_text(REPORTER, "utf-8")
    return assembly.write_launcher(folder)


def test_the_launcher_runs_the_packaged_code_whatever_the_caller_has(tmp_path):
    launcher = launched_python(tmp_path / "package")
    # The current folder holds another degelmann.deltarecon, which must not run.
    checkout = tmp_path / "checkout"
    planted = checkout / "degelmann" / "deltarecon"
    planted.mkdir(parents=True)
    (planted / "__init__.py").write_text("", "utf-8")
    (planted / "__main__.py").write_text("print('the planted package ran')\n", "utf-8")
    # A user site with a module, a bogus PYTHONHOME, and PYTHONPATH naming the engines folder (E7).
    user_base = tmp_path / "user-base"
    version = f"python{sys.version_info.major}.{sys.version_info.minor}"
    user_site = user_base / "lib" / version / "site-packages"
    user_site.mkdir(parents=True)
    (user_site / "deltarecon_user_module.py").write_text("", "utf-8")
    engines = tmp_path / "engines"
    engines.mkdir()
    (engines / f"{package_check.PROBE_MODULE}.py").write_text(package_check.PROBE_SOURCE, "utf-8")
    empty = tmp_path / "empty"
    empty.mkdir()
    environment = {"PATH": str(empty), "HOME": str(tmp_path), "PYTHONUSERBASE": str(user_base),
                   "PYTHONPATH": str(engines), "PYTHONHOME": str(tmp_path / "no-such-home")}
    done = subprocess.run([str(launcher)], cwd=checkout, capture_output=True, text=True, env=environment)
    assert done.returncode == 0, done.stderr
    report = json.loads(done.stdout)
    assert Path(report["main"]).is_relative_to(tmp_path / "package" / "python")
    assert report["home"] is None and report["user_site"] is False
    assert not any(entry in ("", ".", str(checkout)) for entry in report["path"])
    assert str(user_site) not in report["path"]
    assert Path(report["probe"]).parent == engines
    # The same Python without the launcher's flags puts the current folder and the user site first.
    control = subprocess.run([str(tmp_path / "package" / "python" / "bin" / "python3"), "-m", "degelmann.deltarecon"],
                             cwd=checkout, capture_output=True, text=True,
                             env={key: value for key, value in environment.items() if key != "PYTHONHOME"})
    assert control.stdout == "the planted package ran\n"


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
    assert lines.index("setlocal") < lines.index('set "PYTHONHOME="') < lines.index('set "DELTARECON_REPOSITORIES=%~dp0"')
    assert 'set "DELTARECON_REPOSITORIES=%DELTARECON_REPOSITORIES:~0,-1%"' in lines
    assert lines.index('set "PYTHONHOME="') < lines.index('"%~dp0python\\python.exe" -P -s -m degelmann.deltarecon %*')
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
    # The host user's environment stays as it is; only PATH is replaced.
    assert "Remove-Item" not in script and "Env:" not in script
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
    assert probe.index("$env:PATH") < probe.index("$env:PYTHONPATH = 'C:\\tmp\\w\\engines'") < probe.index("& ")
    # The probe starts the packaged Python directly, so it removes PYTHONHOME as the launcher does.
    assert "Remove-Item" not in lister
    assert probe.index("Remove-Item -LiteralPath 'Env:PYTHONHOME'") < probe.index("& ")
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


def test_the_packaged_clone_keeps_no_trace_of_its_source(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    git(source, "init", "--quiet", "--initial-branch", "main")
    for number in (1, 2):
        git(source, "-c", "user.name=Builder", "-c", "user.email=builder@example.org", "commit", "--quiet",
            "--allow-empty", "-m", f"commit {number}")
    git(source, "branch", "other", "HEAD~1")
    clone = tmp_path / "clone"
    assembly.clone_history(str(source), clone)
    assert not (clone / ".git" / "logs").exists()
    assert git(clone, "config", "remote.origin.url").decode().strip() == assembly.DEFAULT_SOURCE
    assert git(clone, "rev-parse", "HEAD") == git(source, "rev-parse", "HEAD")
    assert git(clone, "rev-parse", "origin/other") == git(source, "rev-parse", "other")
    assert git(clone, "rev-list", "--count", "HEAD").decode().strip() == "2"
    for path in (clone / ".git").rglob("*"):
        if path.is_file():
            assert str(tmp_path).encode() not in path.read_bytes() and b"builder@example.org" not in path.read_bytes(), path


def test_the_packaged_clone_holds_its_own_objects_when_the_source_borrows_them(tmp_path):
    store = tmp_path / "store"
    store.mkdir()
    git(store, "init", "--quiet", "--initial-branch", "main")
    git(store, "-c", "user.name=B", "-c", "user.email=b@example.org", "commit", "--quiet", "--allow-empty", "-m", "one")
    source = tmp_path / "source"
    git(tmp_path, "clone", "--quiet", "--shared", str(store), str(source))
    assert (source / ".git" / "objects" / "info" / "alternates").is_file()
    clone = tmp_path / "clone"
    assembly.clone_history(str(source), clone)
    assert not (clone / ".git" / "objects" / "info" / "alternates").exists()
    assert git(clone, "rev-parse", "HEAD") == git(store, "rev-parse", "HEAD")


def test_the_installed_wheel_forgets_its_build_folder(tmp_path):
    site = tmp_path / "site-packages"
    info = site / "degelmann_deltarecon-0.1.2.dist-info"
    info.mkdir(parents=True)
    (info / "direct_url.json").write_text('{"url":"file:///home/builder/dist/x.whl"}', "utf-8")
    record = ("degelmann/__init__.py,sha256=a,1\n"
              "degelmann_deltarecon-0.1.2.dist-info/RECORD,,\n"
              "degelmann_deltarecon-0.1.2.dist-info/direct_url.json,sha256=b,40\n"
              "degelmann_deltarecon-0.1.2.dist-info/INSTALLER,sha256=c,2\n")
    (info / "RECORD").write_text(record, "utf-8")
    other = site / "numpy-2.5.3.dist-info"
    other.mkdir()
    (other / "RECORD").write_text("numpy/__init__.py,sha256=d,1\n", "utf-8")
    assert assembly.drop_direct_url(site) == ["degelmann_deltarecon-0.1.2.dist-info/direct_url.json"]
    assert not (info / "direct_url.json").exists()
    assert (info / "RECORD").read_text("utf-8") == record.replace(
        "degelmann_deltarecon-0.1.2.dist-info/direct_url.json,sha256=b,40\n", "")
    assert (other / "RECORD").read_text("utf-8") == "numpy/__init__.py,sha256=d,1\n"
    assert assembly.drop_direct_url(site) == []


def tracked_checkout(folder: Path) -> Path:
    """A Git checkout in ``folder`` with a tracked, an ignored and an untracked file in ``profiles/`` and a
    ``pyproject.toml`` whose wheel force-includes ``profiles``."""
    folder.mkdir()
    git(folder, "init", "--quiet")
    (folder / ".gitignore").write_text("*.local.json\n", "utf-8")
    (folder / "profiles").mkdir()
    (folder / "profiles" / "tolerance.json").write_text("{}", "utf-8")
    (folder / "pyproject.toml").write_text('[tool.hatch.build.targets.wheel.force-include]\n'
                                           '"profiles" = "degelmann/deltarecon/profiles"\n', "utf-8")
    (folder / "degelmann").mkdir()
    (folder / "degelmann" / "__init__.py").write_text("", "utf-8")
    git(folder, "add", ".")
    (folder / "profiles" / "mine.local.json").write_text("{}", "utf-8")  # ignored
    (folder / "profiles" / "draft.json").write_text("{}", "utf-8")  # untracked
    return folder


def test_only_tracked_profiles_enter_the_package(tmp_path):
    checkout = tracked_checkout(tmp_path / "checkout")
    package = tmp_path / "package"
    assert assembly.copy_tracked("profiles", package, root=checkout) == ["profiles/tolerance.json"]
    assert sorted(path.name for path in (package / "profiles").iterdir()) == ["tolerance.json"]


def test_a_wheel_member_git_does_not_track_is_named(tmp_path):
    checkout = tracked_checkout(tmp_path / "checkout")
    tracked = set(assembly.tracked_files(root=checkout))
    wheel = tmp_path / "degelmann_deltarecon-0.1.2-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as zip_file:
        for name in ("degelmann/__init__.py", "degelmann/deltarecon/profiles/tolerance.json",
                     "degelmann_deltarecon-0.1.2.dist-info/METADATA", "degelmann_deltarecon-0.1.2.dist-info/RECORD"):
            zip_file.writestr(name, "")
    assert assembly.wheel_strays(wheel, tracked, checkout / "pyproject.toml") == []
    with zipfile.ZipFile(wheel, "a") as zip_file:
        zip_file.writestr("degelmann/deltarecon/profiles/mine.local.json", "")
        zip_file.writestr("degelmann/scratch.py", "")
    assert assembly.wheel_strays(wheel, tracked, checkout / "pyproject.toml") == [
        "degelmann/deltarecon/profiles/mine.local.json", "degelmann/scratch.py"]


def test_the_wheel_of_this_checkout_maps_to_tracked_files():
    included = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["tool"]["hatch"]["build"]["targets"][
        "wheel"]["force-include"]
    tracked = set(assembly.tracked_files())
    for outside in included:
        assert any(name.startswith(outside + "/") for name in tracked), outside


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
    # The file holds printf's escape \n, not a line break inside the quotes.
    assert "    printf '%s\\n' 'Press Enter to close. / Enter schließt das Fenster.'\n" in text
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
    assert "$env:PATH = 'C:\\tmp\\w\\empty-path'" in script and "Remove-Item" not in script
    assert script.index("$env:PATH") < script.index("& 'C:\\tmp\\w\\scripts\\demo.cmd'")
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


def test_the_check_keeps_the_callers_environment(monkeypatch, tmp_path):
    for name, value in (("PYTHONPATH", "/caller/path"), ("PYTHONHOME", "/caller/home"), ("VIRTUAL_ENV", "/caller/venv"),
                        (common.REPOSITORIES_VARIABLE, "/caller/repositories"), ("PATH", "/usr/bin")):
        monkeypatch.setenv(name, value)
    environment = package_check.check_environment(tmp_path)
    assert environment == {**os.environ, "PATH": str(tmp_path)}
    assert environment["PYTHONHOME"] == "/caller/home" and environment[common.REPOSITORIES_VARIABLE] == "/caller/repositories"
    assert package_check.check_environment(tmp_path, PYTHONPATH="/engines")["PYTHONPATH"] == "/engines"
    assert not hasattr(package_check, "CLEARED")


def write_archive(path: Path, members: dict[str, bytes]) -> Path:
    """A ``.zip`` or ``.tar.gz`` at ``path`` holding ``members`` (name to bytes)."""
    if path.name.endswith(".zip"):
        with zipfile.ZipFile(path, "w") as zip_file:
            for name, content in members.items():
                zip_file.writestr(name, content)
    else:
        with tarfile.open(path, "w:gz") as tar:
            for name, content in members.items():
                info = tarfile.TarInfo(name)
                info.size = len(content)
                tar.addfile(info, io.BytesIO(content))
    return path


CLEAN_MEMBERS = {"deltarecon-0.1.2-x/delib-history/.git/config": b"[remote \"origin\"]\n",
                 "deltarecon-0.1.2-x/LICENSE": b"Apache"}


@pytest.mark.parametrize("suffix", ["tar.gz", "zip"])
def test_the_traces_claim(tmp_path, suffix):
    needles = ["/home/builder", "/home/builder/deltarecon", str(tmp_path)]
    clean = write_archive(tmp_path / f"clean.{suffix}", CLEAN_MEMBERS)
    assert package_check.build_machine_traces(clean, needles) == []
    traced = write_archive(tmp_path / f"traced.{suffix}", {
        **CLEAN_MEMBERS,
        "deltarecon-0.1.2-x/delib-history/.git/logs/HEAD": b"0 1 Builder <b@example.org> clone: from x\n",
        "deltarecon-0.1.2-x/delib-history/.git/objects/info/alternates": b"../../../store/objects\n",
        "deltarecon-0.1.2-x/python/site/x-1.dist-info/direct_url.json":
            b'{"url":"file:///home/build%20er/deltarecon/dist/x.whl"}',
        "deltarecon-0.1.2-x/python/site/y.txt": b'{"url":"file:///home/builder/deltarecon/dist/x.whl"}',
        "deltarecon-0.1.2-x/notes.txt": f"built in {tmp_path}/out".encode(),
    })
    assert package_check.build_machine_traces(traced, needles) == [
        "deltarecon-0.1.2-x/delib-history/.git/logs/HEAD: the reflogs of delib-history",
        "deltarecon-0.1.2-x/delib-history/.git/objects/info/alternates: the alternates of delib-history, "
        "which name another object store",
        "deltarecon-0.1.2-x/python/site/x-1.dist-info/direct_url.json: the install source of a distribution",
        "deltarecon-0.1.2-x/python/site/y.txt: names /home/builder",
        "deltarecon-0.1.2-x/python/site/y.txt: names /home/builder/deltarecon",
        f"deltarecon-0.1.2-x/notes.txt: names {tmp_path}",
    ]


def test_a_zip_is_read_as_a_zip_under_a_name_without_its_suffix(tmp_path):
    traced = write_archive(tmp_path / "traced.zip", {
        **CLEAN_MEMBERS, "deltarecon-0.1.2-x/delib-history/.git/logs/HEAD": b"0 1 Builder clone\n"})
    resolved = tmp_path / "blob"  # what a correctly named link to the zip may resolve to
    traced.rename(resolved)
    assert package_check.build_machine_traces(resolved, []) == [
        "deltarecon-0.1.2-x/delib-history/.git/logs/HEAD: the reflogs of delib-history"]


def test_an_archive_folder_one_below_the_root_is_no_needle():
    needles = package_check.trace_needles(Path("/tmp/a.tar.gz"))
    assert "/tmp" not in needles and str(Path.home()) in needles and str(ROOT) in needles
    assert str(Path("/tmp/dr-1-19-rel")) in package_check.trace_needles(Path("/tmp/dr-1-19-rel/a.tar.gz"))


def test_the_linux_probe_runs_without_the_callers_pythonhome(monkeypatch, tmp_path):
    monkeypatch.setenv("PYTHONHOME", "/caller/home")
    monkeypatch.setenv("VIRTUAL_ENV", "/caller/venv")
    environment = check_linux.probe_environment(tmp_path / "empty", tmp_path / "engines")
    assert "PYTHONHOME" not in environment
    assert environment["PYTHONPATH"] == str(tmp_path / "engines") and environment["PATH"] == str(tmp_path / "empty")
    assert environment["VIRTUAL_ENV"] == "/caller/venv"


def test_the_trace_needles_name_home_checkout_and_archive_folder(tmp_path):
    needles = package_check.trace_needles(tmp_path / "out" / "a.zip")
    assert needles[:1] == [str(Path.home())] and str(ROOT) in needles and needles[-1] == str(tmp_path / "out")
    assert "/" not in needles


def test_a_trace_fails_the_check_and_the_other_claims_still_run(tmp_path, monkeypatch, capsys):
    archive = write_archive(tmp_path / f"deltarecon-{VERSION}-x86_64-unknown-linux-gnu.tar.gz", {
        **CLEAN_MEMBERS, "deltarecon-0.1.2-x/delib-history/.git/logs/HEAD": b"x"})
    ran = []

    def check_linux(archive, work, target, version):
        ran.append(archive)
        return {"chain and pin": True, "installed packages equal uv.lock": True,
                "import from a user-named folder": True, "guided demo and pin": True,
                **dict.fromkeys(TOY_CLAIM_NAMES, True)}

    monkeypatch.setattr(tool, "check_linux", check_linux)
    assert tool.main(["check", str(archive)]) == 1
    out = capsys.readouterr().out
    assert ran == [archive]
    assert "build_package: chain and pin: OK" in out and "build_package: guided demo and pin: OK" in out
    assert "build_package: toy engine: search: OK" in out
    assert len([line for line in out.splitlines() if line.endswith((": OK", ": FAILED"))]) == 10
    assert "build_package: traces: deltarecon-0.1.2-x/delib-history/.git/logs/HEAD: the reflogs" in out
    assert out.rstrip().endswith("build_package: no build-machine traces: FAILED")
    (tmp_path / "clean").mkdir()
    clean = write_archive(tmp_path / "clean" / archive.name, CLEAN_MEMBERS)
    assert tool.main(["check", str(clean)]) == 0


# The toy engine walkthrough of the package check.

def test_the_toy_table_is_that_of_the_toy_engine_test():
    from test_toy_engine import ENGINE, STATUSES, TARGETS

    assert package_check.TOY_STAGES == TARGETS
    assert list(package_check.TOY_STATUSES) == STATUSES
    assert ENGINE[:2] == ["--engine", package_check.TOY_ENGINE] and ENGINE[3] == package_check.TOY_FOLDER


def test_the_toy_commands_of_a_stage_run_the_launcher(tmp_path):
    package, folder, engine = tmp_path / "package", tmp_path / "toy" / "toy_claims", tmp_path / "toy-engine"
    commands = package_check.toy_commands(package, folder, "toy_claims", engine)
    assert [(step, expect) for step, _, expect in commands] == list(zip(package_check.TOY_STEPS,
                                                                         package_check.TOY_STATUSES))
    by_step = {step: command for step, command, _ in commands}
    assert all(command[0] == str(package / "deltarecon") for command in by_step.values())
    toy = ["--engine", "toy_engine:ToyEngine", "--engine-path", str(engine)]
    assert by_step["request-r1"][1:] == ["request", "--revision", "r1", "--stage", "toy_claims", "--label", "r1",
                                         "--run-id", "run-r1", "--output", str(folder / "r1" / "request.json"), *toy]
    assert by_step["run-r5"][1:] == ["run", str(folder / "r5" / "request.json"), *toy]
    assert by_step["regression"][1:] == ["regression", str(folder / "r1" / "run-record.json"), "--revision", "r5",
                                         "--output", str(folder / "regression"), *toy]
    # compare loads no engine; no command names --repositories.
    assert by_step["compare"][1:] == ["compare", str(folder / "compare.request.json")]
    assert by_step["search"][1:] == ["search", str(folder / "r1" / "run-record.json"),
                                     str(folder / "r5" / "run-record.json"), "--quantity", "expected_claims",
                                     "--output", str(folder / "search"), *toy]
    assert not any("--repositories" in command for command in by_step.values())


def test_the_toy_commands_on_windows_paths():
    work = PureWindowsPath("C:\\tmp\\check")
    package = work / "package" / "deltarecon-0.1.0-x86_64-pc-windows-msvc"
    commands = package_check.toy_commands(package, work / "toy" / "toy_premium", "toy_premium", work / "toy-engine",
                                          "deltarecon.cmd")
    by_step = {step: command for step, command, _ in commands}
    for command in by_step.values():
        assert command[0] == f"{package}\\deltarecon.cmd"
        assert not any("/" in argument for argument in command if argument.startswith("C:"))
    assert by_step["request-r1"][-1] == "C:\\tmp\\check\\toy-engine"
    assert by_step["compare"][-1] == "C:\\tmp\\check\\toy\\toy_premium\\compare.request.json"
    assert by_step["search"][by_step["search"].index("--quantity") + 1] == "premium"


def test_only_tracked_toy_files_are_copied(tmp_path):
    checkout = tmp_path / "checkout"
    toy = checkout / "examples" / "toy_engine"
    (toy / "history" / "r1").mkdir(parents=True)
    git(checkout, "init", "--quiet")
    (toy / "toy_engine.py").write_text("", "utf-8")
    (toy / "history" / "r1" / "rules.json").write_text("{}", "utf-8")
    git(checkout, "add", ".")
    (toy / "__pycache__").mkdir()
    (toy / "__pycache__" / "toy_engine.cpython-313.pyc").write_bytes(b"x")  # untracked
    destination = tmp_path / "work" / "toy-engine"
    assert package_check.copy_toy_engine(destination, root=checkout) == ["history/r1/rules.json", "toy_engine.py"]
    assert sorted(p.relative_to(destination).as_posix() for p in destination.rglob("*") if p.is_file()) == [
        "history/r1/rules.json", "toy_engine.py"]


def test_the_toy_engine_of_this_checkout_is_copied_without_pycache(tmp_path):
    copied = package_check.copy_toy_engine(tmp_path / "toy-engine")
    assert "toy_engine.py" in copied and "history/log.json" in copied
    assert not any("__pycache__" in name for name in copied)


ALL_RAN = dict(zip(package_check.TOY_STEPS, package_check.TOY_STATUSES))
TOY_CLAIM_NAMES = ["toy engine: request", "toy engine: run", "toy engine: regression", "toy engine: compare",
                   "toy engine: search"]


def test_the_toy_claims_hold_when_every_step_exits_as_expected():
    codes = {stage: dict(ALL_RAN) for stage in package_check.TOY_STAGES}
    claims = package_check.toy_claims(codes, dict.fromkeys(package_check.TOY_STAGES, True))
    assert list(claims) == TOY_CLAIM_NAMES and all(claims.values())


def test_a_failing_toy_step_fails_its_claim_and_those_of_the_skipped_steps(capsys):
    failed = {"request-r1": 0, "run-r1": 2}
    codes = {"toy_premium": dict(ALL_RAN), "toy_claims": failed}
    claims = package_check.toy_claims(codes, {"toy_premium": True, "toy_claims": False})
    assert claims == {"toy engine: request": False, "toy engine: run": False, "toy engine: regression": False,
                      "toy engine: compare": False, "toy engine: search": False}
    assert ("build_package: toy engine: toy_claims: skipped request-r5, run-r5, regression, compare, search"
            in capsys.readouterr().out)
    # A failing compare alone fails the compare claim and, skipped after it, the search.
    codes = {"toy_premium": dict(ALL_RAN), "toy_claims": {**ALL_RAN, "compare": 2}}
    del codes["toy_claims"]["search"]
    claims = package_check.toy_claims(codes, {"toy_premium": True, "toy_claims": False})
    assert [name for name, holds in claims.items() if not holds] == ["toy engine: compare", "toy engine: search"]
    # A search that exits 0 but whose result does not hold fails the search claim alone.
    codes = {stage: dict(ALL_RAN) for stage in package_check.TOY_STAGES}
    claims = package_check.toy_claims(codes, {"toy_premium": True, "toy_claims": False})
    assert [name for name, holds in claims.items() if not holds] == ["toy engine: search"]


def search_result(folder: Path, ends=("reproduced", "reproduced"), revisions=("r2", "r4")) -> None:
    (folder / "search").mkdir(parents=True)
    result = {"ends": {"zero": {"outcome": ends[0]}, "n": {"outcome": ends[1]}},
              "contributions": [{"revisions": [revision], "contributions": [{"contributes": revision in revisions}]}
                                for revision in ("r2", "r3", "r4", "r5")]}
    (folder / "search" / "search.result.json").write_text(json.dumps(result), "utf-8")


@pytest.mark.parametrize("case, ends, revisions, holds, printed", [
    ("good", ("reproduced", "reproduced"), ("r2", "r4"), True, "contributing r2, r4"),
    ("end", ("reproduced", "not_reproduced"), ("r2", "r4"), False, "search ends reproduced and not_reproduced, "
                                                                   "expected reproduced"),
    ("revisions", ("reproduced", "reproduced"), ("r2", "r4", "r5"), False,
     "contributing revisions r2, r4, r5, expected r2, r4"),
])
def test_the_toy_search_result_is_checked(tmp_path, capsys, case, ends, revisions, holds, printed):
    search_result(tmp_path, ends, revisions)
    assert package_check.check_toy_search(tmp_path, "toy_premium") is holds
    assert printed in capsys.readouterr().out


def test_a_missing_toy_search_result_does_not_hold(tmp_path, capsys):
    assert package_check.check_toy_search(tmp_path, "toy_claims") is False
    assert "cannot be read" in capsys.readouterr().out


def test_the_toy_compare_request_names_both_runs(tmp_path):
    for revision in ("r1", "r5"):
        (tmp_path / revision).mkdir()
        for name in ("response.json", "run-record.json"):
            (tmp_path / revision / name).write_text(f"{revision} {name}", "utf-8")
    request = json.loads(package_check.write_toy_compare_request(tmp_path, "toy_claims").read_text("utf-8"))
    assert request["document"] == "compare_request" and request["stage"] == "toy_claims"
    assert request["compare_id"] == "compare-toy_claims" and request["tolerance"] == {"per_quantity": {}}
    assert request["left"]["response"] == {"path": "r1/response.json",
                                           "sha256": common.sha256_file(tmp_path / "r1" / "response.json")}
    assert request["right"]["run_record"]["path"] == "r5/run-record.json"


def test_the_toy_walkthrough_skips_the_compare_after_a_failed_step(tmp_path):
    ran = []

    def run_steps(stage, steps):
        ran.append((stage, [step for step, _, _ in steps]))
        return {"request-r1": 0, "run-r1": 2} if stage == "toy_premium" else dict(
            (step, expect) for step, _, expect in steps)

    def commands_of(stage):
        return package_check.toy_commands(tmp_path / "package", tmp_path / "toy" / stage, stage, tmp_path / "engine")

    for revision in ("r1", "r5"):
        (tmp_path / "toy" / "toy_claims" / revision).mkdir(parents=True)
        for name in ("response.json", "run-record.json"):
            (tmp_path / "toy" / "toy_claims" / revision / name).write_text("{}", "utf-8")
    search_result(tmp_path / "toy" / "toy_claims", revisions=("r2", "r4", "r5"))
    claims = package_check.toy_walkthrough(tmp_path / "toy", commands_of, run_steps)
    earlier = ["request-r1", "run-r1", "request-r5", "run-r5", "regression"]
    assert ran == [("toy_premium", earlier), ("toy_claims", earlier), ("toy_claims", ["compare", "search"])]
    assert not (tmp_path / "toy" / "toy_premium" / "compare.request.json").exists()
    assert (tmp_path / "toy" / "toy_claims" / "compare.request.json").is_file()
    assert not any(claims.values())


# A launcher that runs the DeltaRecon of this checkout's environment, for the toy walkthrough of the
# Linux check; ``FAIL_STEP`` makes it exit 2 for one command.
DEV_LAUNCHER = """#!/bin/sh
if [ "$1" = "{fail}" ]; then exit 2; fi
exec "{python}" -m degelmann.deltarecon "$@"
"""


@pytest.mark.parametrize("fail", ["", "regression"], ids=["all good", "regression exits 2"])
def test_the_linux_toy_walkthrough_runs_both_stages(tmp_path, capsys, monkeypatch, fail):
    # The caller's engine variables reach the commands and must not decide the engine.
    monkeypatch.setenv("DELTARECON_ENGINE", "no_such_module:NoEngine")
    monkeypatch.setenv("DELTARECON_ENGINE_PATH", str(tmp_path / "no-such-folder"))
    package, work, empty = tmp_path / "package", tmp_path / "work", tmp_path / "empty"
    for folder in (package, work, empty):
        folder.mkdir()
    launcher = package / targets.LAUNCHER
    launcher.write_text(DEV_LAUNCHER.format(fail=fail, python=sys.executable), "utf-8")
    launcher.chmod(0o755)
    claims = check_linux.check_toy_engine(package, work, empty)
    captured = capsys.readouterr()
    assert list(claims) == TOY_CLAIM_NAMES
    tracked = assembly.tracked_files(package_check.TOY_FOLDER)
    assert sorted(f"{package_check.TOY_FOLDER}/{p.relative_to(work / 'toy-engine').as_posix()}"
                  for p in (work / "toy-engine").rglob("*") if p.is_file() and "__pycache__" not in p.parts) == tracked
    if not fail:
        assert all(claims.values()), captured.out + captured.err
        assert "build_package: toy engine: toy_claims: search ends reproduced and reproduced; contributing r2, r4, r5" \
            in captured.out
        assert sorted(p.name for p in (work / "logs").iterdir()) == sorted(
            f"toy-{stage}-{step}.log" for stage in package_check.TOY_STAGES for step in package_check.TOY_STEPS)
    else:
        assert claims == {"toy engine: request": True, "toy engine: run": True, "toy engine: regression": False,
                          "toy engine: compare": False, "toy engine: search": False}
        assert f"the step regression failed; log: {work / 'logs' / 'toy-toy_premium-regression.log'}" in captured.err


def test_the_windows_toy_host_script_runs_each_step_and_stops_on_an_unexpected_status():
    work = "C:\\tmp\\w"
    package = PureWindowsPath(work) / "package" / "deltarecon-0.1.0-x86_64-pc-windows-msvc"
    commands = package_check.toy_commands(package, PureWindowsPath(work) / "toy" / "toy_premium", "toy_premium",
                                          PureWindowsPath(work) / "toy-engine", "deltarecon.cmd")
    script = check_windows.toy_host_script(work, "toy_premium", commands)
    assert script.startswith(check_windows.host_environment(work))
    position = 0
    for step, command, expect in commands:
        call = "& " + " ".join(host.literal(argument) for argument in command)
        assert script.index(call) > position
        position = script.index(call)
        assert script[position:].split("\n")[1:4] == [
            "$code = $LASTEXITCODE",
            f"[Console]::Out.WriteLine('build_package: toy engine: toy_premium: {step} exit ' + $code + "
            f"' (expected {expect}) in ' + {check_windows.WATCH_SECONDS} + ' s')",
            f"if ($code -ne {expect}) {{ [Console]::Error.WriteLine('build_package: toy engine: toy_premium: step "
            f"{step} exit ' + $code + ', expected {expect}'); exit 1 }}"]
        assert f"'build_package: toy engine: toy_premium: {step} exit '" in script
    assert "--repositories" not in script and "Remove-Item" not in script
    with pytest.raises(host.Refused):
        check_windows.toy_host_script("/mnt/c/tmp/w", "toy_premium", commands)


def test_the_host_codes_are_read_from_the_step_lines():
    text = ("build_package: toy engine: toy_claims: step request-r1\r\n"
            "build_package: toy engine: toy_claims: request-r1 exit 0 (expected 0) in 1.2 s\r\n"
            "build_package: toy engine: toy_premium: run-r1 exit 0 (expected 0) in 1.2 s\n"
            "  build_package: toy engine: toy_claims: run-r1 exit -1 (expected 0) in 0.5 s  \n"
            "build_package: chain: regression exit 1 (expected 1) in 3.0 s\n")
    assert check_windows.host_codes(text, "toy engine: toy_claims") == {"request-r1": 0, "run-r1": -1}
    assert check_windows.host_codes(None, "toy engine: toy_claims") == {}


def test_the_windows_toy_walkthrough_writes_the_compare_request_between_the_host_scripts(tmp_path, monkeypatch,
                                                                                        capsys):
    """Each stage runs as two host scripts; the compare request is written from WSL between them, into
    the host folder reached through ``host.wsl_path``."""
    work = "C:\\tmp\\w"
    monkeypatch.setattr(host, "wsl_path", lambda windows: str(tmp_path / PureWindowsPath(windows).relative_to("C:\\")))
    scripts = []

    def runner(argv, **options):
        script = base64.b64decode(argv[4]).decode("utf-16-le")
        stage = "toy_premium" if "toy engine: toy_premium: " in script else "toy_claims"
        folder = tmp_path / "tmp" / "w" / "toy" / stage
        steps = [step for step in package_check.TOY_STEPS if f"toy engine: {stage}: {step} exit '" in script]
        scripts.append((stage, steps, (folder / "compare.request.json").exists()))
        for revision in ("r1", "r5"):
            (folder / revision).mkdir(parents=True, exist_ok=True)
            for name in ("response.json", "run-record.json"):
                (folder / revision / name).write_text("{}", "utf-8")
        if "search" in steps:
            search_result(folder, revisions=sorted(package_check.TOY_STAGES[stage][1]))
        lines = [f"build_package: toy engine: {stage}: {step} exit {ALL_RAN[step]} (expected {ALL_RAN[step]}) in 0.1 s"
                 for step in steps]
        return subprocess.CompletedProcess(argv, 0, stdout="\n".join(lines))

    package = PureWindowsPath(work) / "package" / "deltarecon-0.1.0-x86_64-pc-windows-msvc"
    claims = check_windows.check_toy_engine(work, package, "/host/powershell.exe", runner=runner)
    assert all(claims.values()) and list(claims) == TOY_CLAIM_NAMES
    earlier = ["request-r1", "run-r1", "request-r5", "run-r5", "regression"]
    assert scripts == [("toy_premium", earlier, False), ("toy_premium", ["compare", "search"], True),
                       ("toy_claims", earlier, False), ("toy_claims", ["compare", "search"], True)]
    assert (tmp_path / "tmp" / "w" / "toy-engine" / "toy_engine.py").is_file()
    count = len(assembly.tracked_files(package_check.TOY_FOLDER))
    copied = f"build_package: toy engine: {count} tracked files copied to C:\\tmp\\w\\toy-engine"
    assert copied in capsys.readouterr().out
