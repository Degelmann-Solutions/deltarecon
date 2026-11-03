"""``CHANGELOG.md`` holds an entry, with the commit the tag names, for every release tag in the history
of the checked-out commit except the newest: that entry comes in the first commit after the publication,
so the tagged commit itself cannot hold it."""
from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
CHANGELOG = ROOT / "CHANGELOG.md"


def git(*arguments: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", "-C", str(ROOT), *arguments], capture_output=True, text=True)


def tags_before_the_newest() -> list[str]:
    """The ``v*`` tags reachable from ``HEAD``, without the newest by version."""
    try:
        done = git("tag", "--list", "v*", "--merged", "HEAD", "--sort=-v:refname")
    except OSError:
        return []
    return done.stdout.split()[1:] if done.returncode == 0 else []


def test_every_earlier_release_tag_has_an_entry_with_its_commit():
    tags = tags_before_the_newest()
    if not tags:
        pytest.skip("no earlier release tags in the history of this clone")
    text = CHANGELOG.read_text("utf-8")
    for tag in tags:
        commit = git("rev-parse", f"{tag}^{{commit}}").stdout.strip()
        section = re.search(rf"^## {re.escape(tag[1:])} — published \d{{4}}-\d{{2}}-\d{{2}}\n(.*?)(?=^## |\Z)", text,
                            re.MULTILINE | re.DOTALL)
        assert section, f"CHANGELOG.md has no entry for {tag}"
        assert f"Tag `{tag}`, commit `{commit}`" in section.group(1), tag


def test_every_entry_names_the_commit_of_its_tag():
    text = CHANGELOG.read_text("utf-8")
    for version, commit in re.findall(r"^- Tag `v([0-9.]+)`, commit `([0-9a-f]{40})`$", text, re.MULTILINE):
        done = git("rev-parse", "--verify", "--quiet", f"v{version}^{{commit}}")
        if done.returncode != 0:
            continue  # a clone without that tag
        assert done.stdout.strip() == commit, version
