"""Worker processes for the model points of one release state.

This module knows no engine and uses the standard library alone. An engine that projects
the points of a session in parallel hands :func:`ordered_map` a start function, which
opens the state in each worker once, and a call, which projects one point there. Both are
module-level functions of the engine, so a worker can import them by name.

The number of workers is ``--workers N``, else the environment variable
``DELTARECON_WORKERS``, else the number of processors the process may use. It is never
written to a document: every worker count gives the same bytes.

``multiprocessing`` and ``concurrent.futures`` are imported when a pool starts, so that the
command line and the engine, which import this module, load no module that can start a
process before a pool starts.
"""
from __future__ import annotations

import os
import re
from typing import Callable, Iterable, Sequence

from .errors import UsageError

WORKERS_VARIABLE = "DELTARECON_WORKERS"
_WHOLE = re.compile(r"[0-9]+")


def whole_number(text: str) -> int | None:
    """``text`` as a whole number of at least 1, or ``None``."""
    if not _WHOLE.fullmatch(text) or int(text) < 1:
        return None
    return int(text)


def worker_count(given: int | None = None) -> int:
    """The number of worker processes: ``given``, else ``DELTARECON_WORKERS``, else the number of
    processors the process may use, or 1 when it is unknown.

    Raises :class:`UsageError` when ``given`` or the variable is not a whole number of at least 1.
    """
    if given is not None:
        if isinstance(given, bool) or not isinstance(given, int) or given < 1:
            raise UsageError(f"the number of workers must be a whole number of at least 1, not {given!r}")
        return given
    text = os.environ.get(WORKERS_VARIABLE)
    if text is not None:
        value = whole_number(text)
        if value is None:
            raise UsageError(f"{WORKERS_VARIABLE} must be a whole number of at least 1, not {text!r}")
        return value
    return os.process_cpu_count() or 1


def start_context(preload: Sequence[str] = ()):
    """The start method ``forkserver`` where the platform offers it, else ``spawn``.

    The fork server imports the modules ``preload`` names before it forks a worker; it does
    so only when this process starts it, the first time a pool asks for it.
    """
    import multiprocessing
    if "forkserver" in multiprocessing.get_all_start_methods():
        context = multiprocessing.get_context("forkserver")
        context.set_forkserver_preload(list(preload))
        return context
    return multiprocessing.get_context("spawn")


def ordered_map(start: Callable, start_arguments: Sequence, call: Callable, items: Iterable, workers: int,
                preload: Sequence[str] = ()) -> list:
    """``call(item)`` for every item, in the order of ``items`` whatever order the workers finish in.

    The pool has ``min(workers, len(items))`` processes; each runs ``start(*start_arguments)``
    once before its first call. An exception of a call or a broken pool propagates. The pool
    is shut down, its processes ended, before this function returns or raises.
    """
    from concurrent.futures import ProcessPoolExecutor
    items = list(items)
    if not items:
        return []
    processes = max(1, min(workers, len(items)))
    executor = ProcessPoolExecutor(max_workers=processes, mp_context=start_context(preload),
                                   initializer=start, initargs=tuple(start_arguments))
    try:
        return list(executor.map(call, items, chunksize=max(1, len(items) // (4 * processes))))
    finally:
        executor.shutdown(wait=True, cancel_futures=True)
