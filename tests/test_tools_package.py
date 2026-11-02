"""The package ``tools/``: the four command-line files run as files from any folder, every module is
loaded once, nothing is loaded by its file path, and no library module imports a command-line
module.
"""
from __future__ import annotations

import ast
import subprocess
import sys

import pytest

from conftest import ROOT

TOOLS = ROOT / "tools"
COMMANDS = ("build_package", "release", "measure_quick_start", "windows_host")
# Each command line and subcommand with --help, as ``uv run python tools/<name>.py ...`` runs it.
HELP = [("build_package", []), ("build_package", ["build"]), ("build_package", ["check"]),
        ("measure_quick_start", []), ("release", []), ("windows_host", []), ("windows_host", ["quick-start"])]
LOADER = "spec_from" + "_file_location"  # split, so this file does not name it


@pytest.mark.parametrize("elsewhere", [False, True], ids=["root", "elsewhere"])
@pytest.mark.parametrize("name, subcommand", HELP, ids=[" ".join([n, *s]) for n, s in HELP])
def test_each_command_file_prints_its_help(tmp_path, name, subcommand, elsewhere):
    done = subprocess.run([sys.executable, str(TOOLS / f"{name}.py"), *subcommand, "--help"],
                          cwd=tmp_path if elsewhere else ROOT, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    assert done.stdout.startswith(f"usage: {name}"), done.stdout


# Run a command file as __main__ with its folder first on sys.path (as ``python tools/<name>.py``
# does), then print every module loaded from ``tools/`` with the file it was loaded from.
RUN_AS_FILE = """
import os, runpy, sys
sys.argv = [sys.argv[1], "--help"]
sys.path[0] = os.path.dirname(sys.argv[0])
try:
    runpy.run_path(sys.argv[0], run_name="__main__")
except SystemExit:
    pass
for name, module in sorted(sys.modules.items()):
    path = getattr(module, "__file__", None) or ""
    if path.startswith(sys.argv_tools):
        print(name, path)
"""


def loaded_tools_modules(code: str, *arguments: str, cwd=ROOT) -> list[tuple[str, str]]:
    script = code.replace("sys.argv_tools", repr(str(TOOLS)))
    done = subprocess.run([sys.executable, "-c", script, *arguments], cwd=cwd, capture_output=True, text=True)
    assert done.returncode == 0, done.stderr
    return [tuple(line.split(" ", 1)) for line in done.stdout.splitlines() if line.startswith("tools")]


@pytest.mark.parametrize("name", COMMANDS)
def test_a_command_file_loads_each_library_module_once(tmp_path, name):
    modules = loaded_tools_modules(RUN_AS_FILE, str(TOOLS / f"{name}.py"), cwd=tmp_path)
    files = [path for _, path in modules]
    assert modules and len(files) == len(set(files)), modules
    assert all(module.startswith("tools") for module, _ in modules)
    assert str(TOOLS / f"{name}.py") not in files  # the file ran as __main__ only


def test_all_four_commands_import_in_one_process_with_one_object_per_module():
    code = ("import sys\nimport " + ", ".join(f"tools.{name}" for name in COMMANDS) + "\n"
            "for name, module in sorted(sys.modules.items()):\n"
            "    path = getattr(module, '__file__', None) or ''\n"
            "    if path.startswith(sys.argv_tools):\n"
            "        print(name, path)\n")
    modules = loaded_tools_modules(code)
    files = [path for _, path in modules]
    assert len(files) == len(set(files)), modules
    assert {module for module, _ in modules} >= {f"tools.{name}" for name in COMMANDS}
    assert all(module == "tools" or module.startswith("tools.") for module, _ in modules)


def test_nothing_is_loaded_by_its_file_path():
    for path in [*TOOLS.rglob("*.py"), *(ROOT / "tests").rglob("*.py")]:
        assert LOADER not in path.read_text("utf-8"), path


def imported_modules(path) -> set[str]:
    names = set()
    for node in ast.walk(ast.parse(path.read_text("utf-8"))):
        if isinstance(node, ast.Import):
            names.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
            if node.module == "tools":
                names.update(f"tools.{alias.name}" for alias in node.names)
    return names


def test_no_library_module_imports_a_command_line_module():
    commands = {f"tools.{name}" for name in COMMANDS} | set(COMMANDS)
    libraries = [path for path in TOOLS.glob("*.py") if path.stem not in COMMANDS]
    assert {path.stem for path in libraries} >= {"__init__", "common", "host", "quick_start_steps", "targets",
                                                  "python_runtime", "assembly", "guides", "package_check",
                                                  "check_linux", "check_windows"}
    for path in libraries:
        assert not imported_modules(path) & commands, path
