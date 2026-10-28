"""The error that keeps a procedure from starting.

This module uses the standard library alone, so that a module that needs the error alone,
such as :mod:`degelmann.deltarecon.workers`, loads nothing else.
"""
from __future__ import annotations


class UsageError(Exception):
    """The procedure cannot start because of how it was called.

    A file or folder it reads is missing or unreadable, or an input it reads is not of the kind
    it takes (such as a tolerance file that violates its schema, or a recorded run with enabled
    changes where a run without one is required); a request it is about to write, such as a
    state request a walk or a search builds, would violate its schema; an output exists already;
    a number of workers is not a whole number of at least 1; a switch is given without the
    switch or the value it needs; an option has a value it does not take; or the history of a
    clone is cut off. It writes no document and is not a
    :class:`~degelmann.deltarecon.documents.Rejection`.
    """
