"""The reference model is only read: no module of ``degelmann.deltarecon`` calls a modelx writer.

The provenance, portfolio, and runner tests of release N live in the reference model
repository ``delib-history``, together with the pinned result hash.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def test_no_modelx_writer_is_called():
    sources = list((ROOT / "degelmann" / "deltarecon").rglob("*.py"))
    assert len(sources) >= 9
    for path in sources:
        source = path.read_text(encoding="utf-8")
        for writer in ("write_model", "export_model", "zip_model"):
            assert writer not in source, f"{path.name} mentions {writer}"
