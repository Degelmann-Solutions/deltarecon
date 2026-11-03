"""``CHANGELOG.md`` holds an entry for every release tag, with the commit the tag names."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"


def tags() -> list[str]:
    try:
        done = subprocess.run(["git", "-C", str(ROOT), "tag", "--list", "v*"], capture_output=True, text=True)
    except OSError:
        return []
    return done.stdout.split() if done.returncode == 0 else []


def test_every_release_tag_has_an_entry_with_its_commit():
    found = tags()
    if not found:
        pytest.skip("no release tags in this clone")
    text = CHANGELOG.read_text("utf-8")
    for tag in found:
        commit = subprocess.run(["git", "-C", str(ROOT), "rev-parse", f"{tag}^{{commit}}"], capture_output=True,
                                text=True, check=True).stdout.strip()
        section = re.search(rf"^## {re.escape(tag[1:])} — published \d{{4}}-\d{{2}}-\d{{2}}\n(.*?)(?=^## |\Z)", text,
                            re.MULTILINE | re.DOTALL)
        assert section, f"CHANGELOG.md has no entry for {tag}"
        assert f"Tag `{tag}`, commit `{commit}`" in section.group(1), tag
