"""The reference model is only read: no module of ``degelmann.deltarecon`` writes a modelx model,
except the export of the computation path ``export``, which the engine writes into its scratch folder.

The provenance, portfolio, and runner tests of release N live in the reference model
repository ``delib-history``, together with the pinned result hash.
"""
from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ENGINE = ROOT / "degelmann" / "deltarecon" / "engines" / "reference_model.py"


def test_no_modelx_writer_is_called():
    sources = list((ROOT / "degelmann" / "deltarecon").rglob("*.py"))
    assert len(sources) >= 9
    for path in sources:
        source = path.read_text(encoding="utf-8")
        for writer in ("write_model", "zip_model"):
            assert writer not in source, f"{path.name} mentions {writer}"
        if path != ENGINE:
            assert "export_model" not in source, f"{path.name} mentions export_model"


def test_the_export_is_written_into_the_scratch_state_only():
    calls = [line.strip() for line in ENGINE.read_text(encoding="utf-8").splitlines()
             if "export_model(" in line and not line.lstrip().startswith(("#", "``", "-"))]
    assert calls == ["mx.export_model(model, package)"]
    uses = [line.strip() for line in ENGINE.read_text(encoding="utf-8").splitlines() if "with _exported(" in line]
    assert uses and all(use.startswith("with _exported(model, state / PRODUCT_FOLDER,") for use in uses)
