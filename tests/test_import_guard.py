"""The imports of the package keep the core apart from the reference model: no module outside
``engines/`` imports the reference model, in any form, and no module imports a private name (one
that starts with ``_``, dunder names excepted) from a module of the package. ``quickstart`` does not
import ``__main__``, so the two form no import cycle, and ``__main__`` imports ``quickstart`` at
module level only.

The check reads the source of every module with :mod:`ast`; it runs nothing. It is also run on
synthetic sources, so that it is known to report both kinds of forbidden import and to find an
import of ``__main__``, at module or function level.
"""
from __future__ import annotations

import ast
from pathlib import Path

import pytest

from conftest import ROOT

PACKAGE = "degelmann.deltarecon"
ENGINES = f"{PACKAGE}.engines"
REFERENCE_MODEL = f"{ENGINES}.reference_model"
SOURCES = ROOT / "degelmann" / "deltarecon"


def module_name(relative: Path) -> str:
    """The dotted name of the module at ``relative``, a path below the root of the checkout."""
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def absolute(module: str, is_package: bool, level: int, target: str | None) -> str:
    """The absolute name of the module ``from <level dots><target> import ...`` names in ``module``."""
    if level == 0:
        return target or ""
    base = module.split(".")
    if not is_package:
        base.pop()
    base = base[:len(base) - (level - 1)] if level > 1 else base
    return ".".join([*base, *([target] if target else [])])


def in_package(name: str) -> bool:
    return name == PACKAGE or name.startswith(f"{PACKAGE}.")


def is_reference_model(name: str) -> bool:
    return name == REFERENCE_MODEL or name.startswith(f"{REFERENCE_MODEL}.")


def is_private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def violations(source: str, relative: Path) -> list[str]:
    """Each forbidden import of the source of the module at ``relative`` (below the checkout root),
    as ``<file>:<line>: <import>``."""
    module = module_name(relative)
    is_package = relative.name == "__init__.py"
    inside_engines = module == ENGINES or module.startswith(f"{ENGINES}.")
    found = []
    for node in ast.walk(ast.parse(source, str(relative))):
        if isinstance(node, ast.Import):
            imported = [(alias.name, alias.name.rsplit(".", 1)[-1]) for alias in node.names]
            reference = any(is_reference_model(name) for name, _ in imported)
            private = any(in_package(name) and any(is_private(part) for part in name.split("."))
                          for name, _ in imported)
        elif isinstance(node, ast.ImportFrom):
            source_module = absolute(module, is_package, node.level, node.module)
            names = [alias.name for alias in node.names]
            reference = is_reference_model(source_module) or (
                source_module == ENGINES and "reference_model" in names)
            private = in_package(source_module) and (
                any(is_private(name) for name in names)
                or any(is_private(part) for part in source_module.split(".")))
        else:
            continue
        if (reference and not inside_engines) or private:
            kind = "imports the reference model" if reference and not inside_engines else "imports a private name"
            found.append(f"{relative.as_posix()}:{node.lineno}: {kind}: {ast.unparse(node)}")
    return found


QUICKSTART = f"{PACKAGE}.quickstart"
MAIN = f"{PACKAGE}.__main__"


def imports(source: str, relative: Path) -> list[tuple[int, str, bool]]:
    """Each module of the package the source of the module at ``relative`` imports, by its absolute
    name, with the line and whether the import is at module level: ``from <module> import <name>``
    counts as an import of ``<module>`` and of ``<module>.<name>``."""
    module = module_name(relative)
    is_package = relative.name == "__init__.py"
    tree = ast.parse(source, str(relative))
    top = {id(node) for node in tree.body}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom):
            source_module = absolute(module, is_package, node.level, node.module)
            names = [source_module, *(f"{source_module}.{alias.name}" for alias in node.names)]
        else:
            continue
        found += [(node.lineno, name, id(node) in top) for name in names if in_package(name)]
    return found


def test_quickstart_does_not_import_main_and_main_imports_quickstart_at_module_level():
    path = SOURCES / "quickstart.py"
    of_quickstart = imports(path.read_text("utf-8"), path.relative_to(ROOT))
    assert [entry for entry in of_quickstart if entry[1] == MAIN] == []
    path = SOURCES / "__main__.py"
    of_main = [entry for entry in imports(path.read_text("utf-8"), path.relative_to(ROOT)) if entry[1] == QUICKSTART]
    assert of_main and all(at_top for _, _, at_top in of_main), of_main


QUICKSTART_PATH = Path("degelmann/deltarecon/quickstart.py")


@pytest.mark.parametrize("source", [
    "from .__main__ import main",
    "from . import __main__",
    "from degelmann.deltarecon.__main__ import DEFAULT_ENGINE",
    "import degelmann.deltarecon.__main__",
    "def step():\n    from .__main__ import main",
])
def test_the_checker_finds_an_import_of_main(source):
    found = imports(f"import os\n\n{source}\n", QUICKSTART_PATH)
    assert MAIN in [name for _, name, _ in found], found


def test_the_checker_tells_a_function_level_import():
    found = imports("from . import run\n\ndef command():\n    from . import quickstart\n",
                    Path("degelmann/deltarecon/__main__.py"))
    assert (4, QUICKSTART, False) in found and (1, f"{PACKAGE}.run", True) in found, found


def test_the_tests_name_the_clone_and_its_variable_as_the_reference_model_does():
    """``conftest`` names them itself, so that loading the stub engines loads no reference model."""
    import conftest
    from degelmann.deltarecon.engines import reference_model

    assert (conftest.CLONE_NAME, conftest.REPOSITORIES_VARIABLE) == (reference_model.CLONE_NAME,
                                                                     reference_model.REPOSITORIES_VARIABLE)


def test_no_module_imports_the_reference_model_outside_engines_or_a_private_name():
    sources = sorted(SOURCES.rglob("*.py"))
    assert {p.name for p in sources} >= {"run.py", "compare.py", "quickstart.py", "reference_model.py"}
    found = [v for p in sources for v in violations(p.read_text("utf-8"), p.relative_to(ROOT))]
    assert found == [], "\n".join(found)


CORE = Path("degelmann/deltarecon/run.py")
SUBPACKAGE = Path("degelmann/deltarecon/sub/module.py")
REFERENCE = Path("degelmann/deltarecon/engines/reference_model.py")
OTHER_ENGINE = Path("degelmann/deltarecon/engines/other.py")


@pytest.mark.parametrize("path, source", [
    (CORE, "from .engines import reference_model"),
    (CORE, "from .engines import changes, reference_model as model"),
    (CORE, "from .engines.reference_model import CLONE_NAME"),
    (CORE, "from .engines.reference_model import *"),
    (CORE, "from degelmann.deltarecon.engines.reference_model import CLONE_NAME"),
    (CORE, "from degelmann.deltarecon.engines import reference_model"),
    (CORE, "import degelmann.deltarecon.engines.reference_model"),
    (CORE, "import degelmann.deltarecon.engines.reference_model as model"),
    (CORE, "def lookup():\n    from .engines.reference_model import repositories_folder"),
    (SUBPACKAGE, "from ..engines import reference_model"),
    (SUBPACKAGE, "from ..engines.reference_model import CLONE_NAME"),
    (Path("degelmann/deltarecon/__init__.py"), "from .engines import reference_model"),
], ids=lambda value: value if isinstance(value, str) else value.as_posix())
def test_the_checker_reports_an_import_of_the_reference_model_outside_engines(path, source):
    found = violations(f"import os\n\n{source}\n", path)
    assert len(found) == 1 and found[0].startswith(f"{path.as_posix()}:") and "the reference model" in found[0], found
    line = int(found[0].split(":")[1])
    assert line >= 3, found


@pytest.mark.parametrize("path, source", [
    (CORE, "from .run import _key_order"),
    (CORE, "from .run import key_order, _typed_key as typed"),
    (CORE, "from degelmann.deltarecon.run import _EngineError"),
    (SUBPACKAGE, "from ..documents import _reference_key"),
    (CORE, "from ._private import helper"),
    (CORE, "from . import _private"),
    (CORE, "import degelmann.deltarecon._private"),
    (REFERENCE, "from ..run import _engine"),
], ids=lambda value: value if isinstance(value, str) else value.as_posix())
def test_the_checker_reports_an_import_of_a_private_name(path, source):
    found = violations(f"import os\n\n{source}\n", path)
    assert found == [f"{path.as_posix()}:3: imports a private name: {source}"], found


@pytest.mark.parametrize("path, source", [
    (CORE, "from .documents import key_order, typed_key"),
    (CORE, "from .protocol import Engine"),
    (CORE, "from . import __version__"),
    (CORE, "from os import _exit"),
    (CORE, "import os._private_thing"),
    (CORE, "from .engines import other"),
    (CORE, "DEFAULT = 'degelmann.deltarecon.engines.reference_model:ReferenceModel'"),
    (REFERENCE, "from ..run import from_worker_outcome"),
    (OTHER_ENGINE, "from .reference_model import CLONE_NAME"),
    (OTHER_ENGINE, "from . import reference_model"),
], ids=lambda value: value if isinstance(value, str) else value.as_posix())
def test_the_checker_lets_an_allowed_import_pass(path, source):
    assert violations(f"import os\n\n{source}\n", path) == []
