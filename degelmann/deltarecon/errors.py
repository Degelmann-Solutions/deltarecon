"""The error that keeps a procedure from starting.

This module uses the standard library alone, so that a module that needs the error alone,
such as :mod:`degelmann.deltarecon.workers`, loads nothing else. The error is defined in
:mod:`degelmann.deltarecon.protocol`, which an engine imports, and re-exported here.
"""
from __future__ import annotations

from .protocol import UsageError

__all__ = ["UsageError"]
