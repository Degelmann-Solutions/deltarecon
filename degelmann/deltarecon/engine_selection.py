"""The engine selection of the command line: the variables that name the engine and its folder, the
reference model as the default engine, and :func:`engine_class`, which loads the class a selection
names. It imports the standard library and :mod:`.protocol` alone, so that ``__main__`` and
``quickstart`` share it without importing each other.
"""
from __future__ import annotations

import importlib
import inspect
import os
import sys
from pathlib import Path

from .protocol import UsageError


# The engine class a command loads: ``--engine <module>:<class>``, else this variable, else
# the reference model. ``--engine-path`` names a folder that is put on the import path first;
# the path variable does so only when no ``--engine`` is given (for the engine the engine
# variable names, or the reference model), so ``--engine`` alone decides the engine. An empty variable counts as unset.
ENGINE_VARIABLE = "DELTARECON_ENGINE"
ENGINE_PATH_VARIABLE = "DELTARECON_ENGINE_PATH"
DEFAULT_ENGINE = "degelmann.deltarecon.engines.reference_model:ReferenceModel"


def engine_class(spec: str | None = None, path: str | None = None):
    """The engine class a selection names, imported on use, so that parsing the command line
    and a command without an engine load no engine module.

    ``path``, else ``DELTARECON_ENGINE_PATH`` when ``spec`` is not given (the engine then comes
    from ``DELTARECON_ENGINE`` or is the reference model), is put on the import path first.

    Raises :class:`UsageError` when the folder is not a folder, the selection is not of the form
    ``<module>:<class>`` with an absolute module name, the module is not found or its import raises
    :class:`ImportError`, or the module has no such attribute or it is not a class.
    """
    if path is None and spec is None:  # without --engine: the path variable belongs to the engine variable or the default
        path = os.environ.get(ENGINE_PATH_VARIABLE) or None
    if path is not None:
        folder = Path(path).resolve() if path else None
        if folder is None or not folder.is_dir():
            raise UsageError(f"the engine path {path!r} is not a folder")
        if str(folder) in sys.path:
            sys.path.remove(str(folder))
        sys.path.insert(0, str(folder))
        importlib.invalidate_caches()
    if spec is None:
        spec = os.environ.get(ENGINE_VARIABLE) or DEFAULT_ENGINE
    module_name, colon, class_name = spec.partition(":")
    if not colon or not module_name or not class_name or module_name.startswith("."):
        raise UsageError(f"the engine {spec!r} is not of the form <module>:<class> with an absolute module name")
    try:
        module = importlib.import_module(module_name)
    except ImportError as error:
        raise UsageError(f"the engine {spec!r} cannot be loaded: the module {module_name!r} "
                         f"cannot be imported ({error})") from None
    try:
        cls = getattr(module, class_name)
    except AttributeError:
        raise UsageError(f"the engine {spec!r} cannot be loaded: the module {module_name!r} "
                         f"has no {class_name!r}") from None
    if not isinstance(cls, type):
        raise UsageError(f"the engine {spec!r} cannot be loaded: {class_name!r} of the module "
                         f"{module_name!r} is not a class")
    if getattr(cls, "_is_protocol", False) or inspect.isabstract(cls):
        raise UsageError(f"the engine {spec!r} cannot be loaded: {class_name!r} is a protocol or an "
                         "abstract class, which cannot be called")
    return cls
