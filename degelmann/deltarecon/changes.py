"""The changes contract: manifest rules, combination rules, and the text-patch profile.

Rule numbers refer to ``contracts/v1/changes.md``. A patch is a strict unified diff: a
hunk applies only where its context and removed lines match exactly and in one place.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from .documents import Rejection

TEXT_PATCH = "text_patch"
HUNK_HEADER = re.compile(r"@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@.*")
NO_NEWLINE = "\\ No newline at end of file"


def artifacts(realisation: dict) -> list[dict]:
    """The artifact references of a realisation: its members that point to a stored file."""
    return [value for value in realisation.values()
            if isinstance(value, dict) and set(value) == {"path", "sha256"}]


# --- manifest rules 1 to 5, and the chain of a derived manifest ----------------------------------------------------------


def _invalid(message: str, change_ids=None) -> Rejection:
    return Rejection("invalid_manifest", message, change_ids=change_ids)


def check_manifest_rules(manifest: dict) -> None:
    changes = manifest["changes"]
    ids = [change["id"] for change in changes]

    repeated = sorted({i for i in ids if ids.count(i) > 1})  # rule 1
    if repeated:
        raise _invalid("Two changes of the manifest have the same id.", repeated)

    for change in changes:  # rule 2
        for member in ("prerequisites", "conflicts"):
            if change["id"] in change[member]:
                raise _invalid(f"A change names itself in {member}.", [change["id"]])
            if any(other not in ids for other in change[member]):
                raise _invalid(f"A change names an id in {member} that the manifest does not hold.",
                               [change["id"]])

    for change in changes:  # rule 3
        if set(change["prerequisites"]) & set(change["conflicts"]):
            raise _invalid("A change names an id as a prerequisite and as a conflict.", [change["id"]])

    position = {change_id: index for index, change_id in enumerate(ids)}  # rule 4
    for change in changes:
        if any(position[other] > position[change["id"]] for other in change["prerequisites"]):
            raise _invalid("A prerequisite stands after the change that needs it.", [change["id"]])

    by_id = {change["id"]: change for change in changes}  # rule 5
    closure: dict[str, set[str]] = {}
    for change in changes:  # prerequisites stand first, so their closures exist already
        closure[change["id"]] = set(change["prerequisites"]).union(
            *(closure[other] for other in change["prerequisites"]))
    for change in changes:
        for other in sorted(closure[change["id"]]):
            if other in change["conflicts"] or change["id"] in by_id[other]["conflicts"]:
                raise _invalid("A change conflicts with one of its own prerequisites.",
                               [change["id"], other])

    if "history" in manifest:
        check_history_chain(manifest)


def check_history_chain(manifest: dict) -> None:
    """The changes of a derived manifest are the main line from ``history.from`` to ``to``.

    Each change names the change before it as its only prerequisite, the first names none,
    each is realised as its own revision, and the last is the newer revision. A manifest
    of one revision holds no change.
    """
    history, changes = manifest["history"], manifest["changes"]
    if not changes:
        if history["from"] != history["to"]:
            raise _invalid("A derived manifest of two revisions holds no change.")
        return
    if changes[-1]["id"] != history["to"]:
        raise _invalid("The last change of a derived manifest is not the newer revision.", [changes[-1]["id"]])
    for index, change in enumerate(changes):
        expected = [changes[index - 1]["id"]] if index else []
        if change["prerequisites"] != expected:
            raise _invalid("A change of a derived manifest does not name the change before it as its "
                           "only prerequisite.", [change["id"]])
        realisation = change["realisation"]
        if realisation.get("revision") != change["id"] or realisation.get("source") != history["source"]:
            raise _invalid("A change of a derived manifest is not realised as its own revision of the "
                           "history.", [change["id"]])


# --- combination rules 6 to 11 ------------------------------------------------------


def check_combination(manifest: dict, request: dict, realisations) -> list[dict]:
    """The enabled changes in application order, once the combination is allowed."""
    enabled = set(request["changes"]["enabled"])
    changes = manifest["changes"]
    known = {change["id"] for change in changes}

    unknown = sorted(enabled - known)  # rule 6
    if unknown:
        raise Rejection("unknown_change", "The manifest holds no change with this id.", change_ids=unknown)

    if manifest["stage"] != request["stage"]:  # rule 7
        raise Rejection("stage_mismatch", f"The manifest names the stage {manifest['stage']}, "
                        f"the request the stage {request['stage']}.")
    if manifest["base_release"] != request["release"]["label"]:
        raise _invalid("The base release of the manifest is not the release of the request.")

    selected = [change for change in changes if change["id"] in enabled]  # rule 10: manifest order

    unmet = [c["id"] for c in selected if not set(c["prerequisites"]) <= enabled]  # rule 8
    if unmet:
        raise Rejection("unmet_prerequisite", "An enabled change lacks an enabled prerequisite.",
                        change_ids=unmet)

    conflicting = sorted({i for c in selected for other in c["conflicts"] if other in enabled  # rule 9
                          for i in (c["id"], other)})
    if conflicting:
        raise Rejection("change_conflict", "Two enabled changes conflict.", change_ids=conflicting)

    unsupported = [c["id"] for c in selected if c["realisation"]["type"] not in realisations]  # rule 11
    if unsupported:
        raise Rejection("unsupported_realisation", "The engine cannot realise a change of this type.",
                        change_ids=unsupported)
    return selected


# --- the held kinds of a change set ---------------------------------------------------


REVISION = "revision"


def check_hold(request: dict, enabled: list[dict], holdable) -> frozenset[str]:
    """The kinds ``changes.hold`` names, once the engine can hold them while a revision is enabled.

    Without the member nothing is held. A kind the engine cannot hold, and a hold without
    an enabled change of the type ``revision``, are rejected with ``invalid_hold``.
    """
    hold = request["changes"].get("hold")
    if hold is None:
        return frozenset()
    unknown = sorted(set(hold) - set(holdable))
    if unknown:
        raise Rejection("invalid_hold", f"The engine cannot hold the kind {unknown[0]} at the release of "
                        "the request.")
    if not any(change["realisation"]["type"] == REVISION for change in enabled):
        raise Rejection("invalid_hold", "A kind is held only while a change of the type revision is enabled.")
    return frozenset(hold)


# --- text-patch reference profile ---------------------------------------------------


@dataclass
class Hunk:
    start: int            # the line number the header states for the old side, 1-based
    old: list[str]        # context and removed lines, each with its line end
    new: list[str]        # context and added lines, each with its line end


@dataclass
class FilePatch:
    path: str
    hunks: list[Hunk]


def _header_path(line: str) -> str:
    return line[4:].split("\t", 1)[0]


def parse_patch(text: str) -> list[FilePatch]:
    """Parse a unified diff strictly. Anything outside the grammar is an error."""
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    files: list[FilePatch] = []
    index = 0
    while index < len(lines):
        if not lines[index].startswith("--- ") or index + 1 >= len(lines) \
                or not lines[index + 1].startswith("+++ "):
            raise ValueError(f"line {index + 1}: a file header '--- path' and '+++ path' is expected")
        old_path, new_path = _header_path(lines[index]), _header_path(lines[index + 1])
        if "/dev/null" in (old_path, new_path):
            raise ValueError("a patch creates and deletes no file")
        if old_path != new_path:
            raise ValueError(f"a patch renames no file: {old_path} to {new_path}")
        index += 2
        patch = FilePatch(old_path, [])
        while index < len(lines) and lines[index].startswith("@@"):
            match = HUNK_HEADER.fullmatch(lines[index])
            if not match:
                raise ValueError(f"line {index + 1}: not a hunk header")
            old_count = int(match.group(2) or 1)
            new_count = int(match.group(4) or 1)
            index += 1
            hunk = Hunk(int(match.group(1)), [], [])
            last: list[list[str]] = []
            while len(hunk.old) < old_count or len(hunk.new) < new_count or (
                    index < len(lines) and lines[index] == NO_NEWLINE):
                if index >= len(lines):
                    raise ValueError("a hunk ends before its stated line counts")
                line = lines[index]
                index += 1
                if line == NO_NEWLINE:
                    if not last:
                        raise ValueError(f"line {index}: the marker follows no line")
                    for side in last:
                        side[-1] = side[-1][:-1]
                    last = []
                    continue
                mark, content = line[:1], line[1:] + "\n"
                if mark == " ":
                    hunk.old.append(content)
                    hunk.new.append(content)
                    last = [hunk.old, hunk.new]
                elif mark == "-":
                    hunk.old.append(content)
                    last = [hunk.old]
                elif mark == "+":
                    hunk.new.append(content)
                    last = [hunk.new]
                else:
                    raise ValueError(f"line {index}: not a context, removed, or added line")
                if len(hunk.old) > old_count or len(hunk.new) > new_count:
                    raise ValueError(f"line {index}: the hunk holds more lines than its header states")
            patch.hunks.append(hunk)
        if not patch.hunks:
            raise ValueError(f"the file {old_path} has no hunk")
        files.append(patch)
    if not files:
        raise ValueError("the patch changes no file")
    return files


def _split_lines(text: str) -> list[str]:
    parts = text.split("\n")
    return [part + "\n" for part in parts[:-1]] + ([parts[-1]] if parts[-1] else [])


def apply_hunks(lines: list[str], hunks: list[Hunk]) -> list[str]:
    """Apply the hunks of one file. Each must match the file exactly and in one place."""
    places = []
    for number, hunk in enumerate(hunks, start=1):
        size = len(hunk.old)
        found = [at for at in range(len(lines) - size + 1) if lines[at:at + size] == hunk.old]
        if not found:
            raise ValueError(f"hunk {number} matches the file in no place")
        if len(found) > 1:
            raise ValueError(f"hunk {number} matches the file in {len(found)} places")
        places.append((found[0], hunk))
    result, position = [], 0
    for at, hunk in places:
        if at < position:
            raise ValueError("two hunks overlap or stand in the wrong order")
        result.extend(lines[position:at])
        result.extend(hunk.new)
        position = at + len(hunk.old)
    result.extend(lines[position:])
    if any(not line.endswith("\n") for line in result[:-1]):
        raise ValueError("a line without a line end would stand inside the file")
    return result


def apply_patch(root: Path, patch_text: str) -> None:
    """Apply one patch file to the release state in ``root``, which is a scratch folder."""
    root = root.resolve()
    for patch in parse_patch(patch_text):
        parts = patch.path.split("/")
        if patch.path.startswith("/") or "\\" in patch.path or any(p in ("", ".", "..") for p in parts):
            raise ValueError(f"the path {patch.path} is not a path inside the release")
        target = root.joinpath(*parts)
        if target.is_symlink() or not target.is_file() or root not in target.resolve().parents:
            raise ValueError(f"the release holds no file {patch.path}")
        try:
            text = target.read_bytes().decode("utf-8")
        except UnicodeDecodeError:
            raise ValueError(f"the file {patch.path} is not a text file") from None
        try:
            lines = apply_hunks(_split_lines(text), patch.hunks)
        except ValueError as exc:
            raise ValueError(f"{patch.path}: {exc}") from None
        target.write_bytes("".join(lines).encode("utf-8"))


def apply_changes(root: Path, changes: list[dict], manifest_dir: Path) -> None:
    """Apply the enabled text patches in manifest order to the scratch folder ``root``."""
    for change in changes:
        path = manifest_dir / change["realisation"]["artifact"]["path"]
        try:
            apply_patch(root, path.read_bytes().decode("utf-8"))
        except (ValueError, UnicodeDecodeError) as exc:
            raise _invalid(f"The patch of the change does not apply: {exc}.", [change["id"]]) from None
