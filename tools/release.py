"""Build both DeltaRecon packages from one commit and prepare the files of their GitHub release.

    uv run python tools/release.py [--output DIR] [--source URL|PATH]

The release folder is ``dist/release-v<version>/`` (the version of ``pyproject.toml``) unless
``--output`` names another; it must not exist. The steps, in this order:

1. The working tree must be clean: ``git status --porcelain`` prints nothing. A modified, staged,
   deleted or untracked file refuses the release and is named; an ignored file (``build/``,
   ``dist/``, ``repositories/``) does not count. A clean tree makes the wheel that
   ``uv build --wheel`` builds from the working tree the commit's.
2. The full commit of ``HEAD`` is recorded.
3. ``build`` of ``tools/build_package.py`` builds the Linux package
   (``x86_64-unknown-linux-gnu``, ``.tar.gz``), then the Windows package
   (``x86_64-pc-windows-msvc``, ``.zip``), both into the release folder and both from ``--source``
   (default the GitHub repository of ``delib-history``), which is passed on unchanged. Each
   package folder stays beside its archive. A build that fails or refuses leaves what was built
   before it in the release folder, which then exists.
4. ``HEAD`` and the working tree are read again. When ``HEAD`` moved or the tree is no longer
   clean, the release fails and writes neither ``SHA256SUMS`` nor the notes.
5. ``SHA256SUMS`` gets one line per archive, ``<SHA-256>  <archive name>``, sorted by name, so
   ``sha256sum -c SHA256SUMS`` passes in the release folder. ``release-notes.md`` gets the notes
   of the release ``v<version>``: the commit, the platform and SHA-256 of each archive, what a
   package holds, how to verify a download, that the Windows package is not signed, and a link
   to the quick start of the README at the tag. The notes hold no time and no path of this
   machine, so the same commit and archives give the same bytes. Both files are UTF-8 with LF.

The tool publishes nothing: it pushes no tag, creates no release and starts no ``gh``. It checks
no archive either; ``uv run python tools/build_package.py check ARCHIVE`` checks each archive of
the release folder.

Exit status: 0 when both archives, ``SHA256SUMS`` and the notes are written; 1 when a build step
fails or ``HEAD`` or the working tree changed during the builds; 2 when the release cannot start
(a working tree that is not clean, an existing release folder, ``git`` that cannot read this
checkout) or ``build`` refuses. Standard library only, beside what ``tools/build_package.py``
needs.
"""
from __future__ import annotations

import argparse
import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
BUILD_PACKAGE_TOOL = ROOT / "tools" / "build_package.py"
REPOSITORY_URL = "https://github.com/Degelmann-Solutions/deltarecon"
SUMS = "SHA256SUMS"
NOTES = "release-notes.md"


def _load_tool(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


BUILD = _load_tool("build_package", BUILD_PACKAGE_TOOL)
Failed, Refused = BUILD.Failed, BUILD.Refused
# The targets in the order they are built, and the platform each names in the notes.
TARGETS = (BUILD.TARGET, BUILD.WINDOWS_TARGET)
PLATFORMS = {BUILD.TARGET: "Linux x86-64", BUILD.WINDOWS_TARGET: "Windows x86-64"}


def default_output(version: str) -> Path:
    return BUILD.DEFAULT_OUTPUT / f"release-v{version}"


def dirty_paths(git) -> list[str]:
    """The paths ``git status --porcelain`` names, untracked ones included; refused when git fails."""
    status = git("status", "--porcelain")
    if status is None:
        raise Refused(f"git status failed in {ROOT}")
    # Each line is ``XY <path>``; git_text strips the output, so the first line may have lost a space of XY.
    return [line.split(None, 1)[1] for line in status.splitlines() if line.strip()]


def head(git) -> str:
    commit = git("rev-parse", "HEAD")
    if commit is None:
        raise Refused(f"git rev-parse HEAD failed in {ROOT}")
    return commit


def sums_text(hashes: dict[str, str]) -> str:
    """The text of ``SHA256SUMS``: one ``<SHA-256>  <name>`` line per archive, sorted by name."""
    return "".join(f"{hashes[name]}  {name}\n" for name in sorted(hashes))


def notes_text(version: str, python: str, commit: str, archives: dict[str, tuple[str, str]]) -> str:
    """The text of ``release-notes.md``; ``archives`` maps each archive name to its platform and SHA-256."""
    tag = f"v{version}"
    rows = "".join(f"| {platform} | `{name}` | `{digest}` |\n"
                   for name, (platform, digest) in sorted(archives.items()))
    return f"""# DeltaRecon {version}

Release `{tag}`, built from commit `{commit}`.

| Platform | Archive | SHA-256 |
|---|---|---|
{rows}
## What a package holds

A package is one folder that runs DeltaRecon without Python, uv or Git on the machine. It holds:

- `python/`: a standalone CPython {python}, the version that `requires-python` in `pyproject.toml` pins;
- the runtime libraries locked in `uv.lock` and DeltaRecon itself with its contract pack, installed in that Python;
- `delib-history/`: a full clone of the reference model repository, with its history;
- `profiles/`: the tolerance profiles the quick start uses, and `LICENSE`;
- the launcher, `deltarecon` on Linux and `deltarecon.cmd` on Windows, which runs DeltaRecon on the clone in the package (`DELTARECON_REPOSITORIES`).

The quick start of the package is in the README at this tag: {REPOSITORY_URL}/blob/{tag}/README.md#quick-start

## Verify the download

Download `{SUMS}` beside the archive. On Linux, `sha256sum -c {SUMS}` in that folder must report `OK` for each archive (add `--ignore-missing` when only one archive is downloaded). On Windows, `Get-FileHash -Algorithm SHA256 <zip>` in PowerShell prints the SHA-256 of the zip; it must equal the value in the table above and in `{SUMS}`.

The Windows package is not signed, so SmartScreen or the browser may warn when it is downloaded or run.
"""


def release(output: Path, source: str, builder=None, git=None) -> tuple[str, list[Path]]:
    """Build both archives into ``output`` and write ``SHA256SUMS`` and the notes; the commit and the archives.

    ``builder`` defaults to ``build`` of ``tools/build_package.py``, ``git`` to ``git_text`` of
    ``tools/measure_quick_start.py`` (git in this checkout, None on failure).
    """
    builder = builder or BUILD.build
    git = git or BUILD.MEASURE.git_text
    version, python = BUILD.project()
    dirty = dirty_paths(git)
    if dirty:
        raise Refused(f"the working tree is not clean: {', '.join(dirty)}")
    if output.exists() or output.is_symlink():
        raise Refused(f"the output {output} exists already")
    commit = head(git)
    print(f"release: building {version} from commit {commit}", flush=True)
    archives = []
    for target in TARGETS:
        archive = builder(output, source, target)
        print(f"release: built {archive.name}", flush=True)
        archives.append(archive)
    after = git("rev-parse", "HEAD")
    if after != commit:
        raise Failed(f"HEAD changed during the build: it was {commit}, it is {after}")
    dirty = dirty_paths(git)
    if dirty:
        raise Failed(f"the working tree changed during the build: {', '.join(dirty)}")
    hashes = {archive.name: BUILD.sha256_file(archive) for archive in archives}
    rows = {name: (PLATFORMS[BUILD.target_of(Path(name), version)], digest) for name, digest in hashes.items()}
    (output / SUMS).write_bytes(sums_text(hashes).encode("utf-8"))
    (output / NOTES).write_bytes(notes_text(version, python, commit, rows).encode("utf-8"))
    return commit, archives


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="release",
        description="Build the Linux and the Windows package from one clean commit into a release folder and "
                    f"write {SUMS} and {NOTES} there. Publishes nothing and checks no archive.")
    parser.add_argument("--output", type=Path,
                        help="the release folder, which must not exist (default dist/release-v<version>/)")
    parser.add_argument("--source", default=BUILD.DEFAULT_SOURCE,
                        help=f"what delib-history is cloned from, a URL or a local path (default {BUILD.DEFAULT_SOURCE})")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse(argv)
    try:
        output = (arguments.output or default_output(BUILD.project()[0])).resolve()
        commit, archives = release(output, arguments.source)
        print(f"release: written {', '.join(archive.name for archive in archives)}, {SUMS} and {NOTES} "
              f"of commit {commit} in {output}")
        return 0
    except Refused as refusal:
        print(f"release: {refusal}", file=sys.stderr)
        return 2
    except Failed as failure:
        print(f"release: {failure}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
