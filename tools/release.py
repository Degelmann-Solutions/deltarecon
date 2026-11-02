"""Build both DeltaRecon packages from one commit and prepare the files of their GitHub release.

    uv run python tools/release.py [--output DIR] [--source URL|PATH]

The release folder is ``dist/release-v<version>/`` (the version of ``pyproject.toml``) unless
``--output`` names another; it must not exist. It must lie outside the working tree or in a folder
git ignores, such as ``dist/``: an archive in a folder git does not ignore is untracked, and the
release then fails after both builds. The steps, in this order:

1. The working tree must be clean: ``git status --porcelain`` prints nothing. A modified, staged,
   deleted or untracked file refuses the release and is named; an ignored file (``build/``,
   ``dist/``, ``repositories/``) does not count. A clean tree makes the wheel that
   ``uv build --wheel`` builds from the working tree the commit's.
2. The full commit of ``HEAD`` is recorded.
3. A local ``--source`` must not be behind its upstream: the upstream of its checked-out branch
   (``@{u}``) is read on its remote with ``git ls-remote``, nothing is fetched into the source, and
   the commit found there must be an ancestor of the source's ``HEAD``. A source behind its upstream
   (or whose upstream commit it does not hold) and a source without an upstream are refused. A URL
   source (``https://...``, ``file://...``, ``host:path``) is its own upstream and is not checked.
4. ``--source`` (default the GitHub repository of ``delib-history``) is cloned once, with
   ``git clone --bare``, into a temporary folder beside the release folder, so every branch of the
   source is a branch of that clone; its ``HEAD`` is recorded. The clone is removed when the
   release ends, however it ends.
5. ``build`` of ``tools/assembly.py`` (the build of ``tools/build_package.py``) builds the Linux package
   (``x86_64-unknown-linux-gnu``, ``.tar.gz``), then the Windows package
   (``x86_64-pc-windows-msvc``, ``.zip``), both into the release folder and both from that one
   clone, so both packages hold the same ``delib-history``; ``build`` sets the remote of each
   packaged clone to the GitHub repository. Each package folder stays beside its archive. A build
   that fails or refuses leaves what was built before it in the release folder, which then exists.
6. ``HEAD`` and the working tree are read again. When ``HEAD`` moved or the tree is no longer
   clean, the release fails and writes neither ``SHA256SUMS`` nor the notes.
7. ``SHA256SUMS`` gets one line per archive, ``<SHA-256>  <archive name>``, sorted by name, so
   ``sha256sum -c SHA256SUMS`` passes in the release folder. ``release-notes.md`` gets the notes
   of the release ``v<version>``: the commit, the commit of ``delib-history`` both packages hold,
   the platform and SHA-256 of each archive, how to start the guided demo (``quickstart.cmd`` on
   Windows, by double click, in cmd or as ``.\\quickstart.cmd`` in PowerShell; ``./quickstart`` on
   Linux) and the guides ``LIESMICH.txt`` and ``README.txt`` of each package, what a package holds,
   how to verify a download, that the Windows package is not signed, and a link to the quick start
   of the README at the tag. The notes hold no time and no path of this
   machine, so the same commit and archives give the same bytes. Both files are UTF-8 with LF.

The tool publishes nothing: it pushes no tag, creates no release and starts no ``gh``. It checks
no archive either; ``uv run python tools/build_package.py check ARCHIVE`` checks each archive of
the release folder.

Exit status: 0 when both archives, ``SHA256SUMS`` and the notes are written; 1 when a build step
fails (the clone of the source included) or ``HEAD`` or the working tree changed during the builds;
2 when the release cannot start (a working tree that is not clean, an existing release folder,
``git`` that cannot read this checkout, a local source behind its upstream or without one) or
``build`` refuses. Standard library and the DeltaRecon package of this checkout only,
beside what ``tools/assembly.py`` needs.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
import tempfile
from pathlib import Path

# Run as a file, the folder of this file is first on sys.path; the package ``tools`` needs its parent.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from tools import assembly, common, targets  # noqa: E402
from tools.common import REPOSITORY_URL, ROOT, Failed, Refused  # noqa: E402
from tools.python_runtime import project  # noqa: E402

SUMS = "SHA256SUMS"
NOTES = "release-notes.md"
# The targets in the order they are built, and the platform each names in the notes.
TARGETS = (targets.TARGET, targets.WINDOWS_TARGET)
PLATFORMS = {name: targets.TARGETS[name]["platform"] for name in TARGETS}


def default_output(version: str) -> Path:
    return assembly.DEFAULT_OUTPUT / f"release-v{version}"


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


def is_url(source: str) -> bool:
    """Whether ``source`` is a URL (``scheme://...``) or Git's ``host:path`` form rather than a local path:
    a colon before the first slash, a Windows drive letter aside."""
    return "://" in source or bool(re.match(r"[^/\\]{2,}:", source))


def require_upstream(source: str) -> None:
    """Refuse a local ``source`` that is behind the upstream of its checked-out branch or has none.

    The upstream commit is read with ``git ls-remote`` on the upstream's remote, so nothing is
    fetched into the source; the source is behind when that commit is not an ancestor of its
    ``HEAD`` (a commit the source does not hold counts as behind). A URL source is not checked."""
    if is_url(source):
        return
    git = common.git_text
    folder = Path(source)
    if git("rev-parse", "HEAD", folder=folder) is None:
        raise Refused(f"git cannot read a commit in the source {source}")
    branch = git("symbolic-ref", "--short", "-q", "HEAD", folder=folder)
    upstream = git("rev-parse", "--abbrev-ref", "@{u}", folder=folder)
    remote = branch and git("config", f"branch.{branch}.remote", folder=folder)
    merge = branch and git("config", f"branch.{branch}.merge", folder=folder)
    if not (upstream and remote and merge):
        raise Refused(f"the source {source} has no upstream to compare with; name a source whose checked-out "
                      f"branch tracks a remote branch, or the URL of the repository")
    url = git("remote", "get-url", remote, folder=folder) if remote != "." else "."
    listed = url and git("ls-remote", url, merge, folder=folder)
    commits = [line.split()[0] for line in (listed or "").splitlines() if line.split()[1:] == [merge]]
    if len(commits) != 1:
        raise Refused(f"the upstream {upstream} of the source {source} ({url}) names no commit for {merge}")
    if git("merge-base", "--is-ancestor", commits[0], "HEAD", folder=folder) is None:
        raise Refused(f"the source {source} is behind its upstream {upstream} ({url}): its commit {commits[0]} "
                      f"is not in the source's HEAD; update the source or name the URL of the repository")


def clone_source(source: str, folder: Path) -> str:
    """A bare clone of ``source`` at ``folder``, every branch of the source a branch of it; its ``HEAD``."""
    assembly.run(["git", "clone", "--quiet", "--bare", source, str(folder)], f"git clone of {source}")
    return assembly.run(["git", "-C", str(folder), "rev-parse", "--verify", "HEAD^{commit}"],
                        f"git rev-parse HEAD in the clone of {source}").stdout.strip()


def sums_text(hashes: dict[str, str]) -> str:
    """The text of ``SHA256SUMS``: one ``<SHA-256>  <name>`` line per archive, sorted by name."""
    return "".join(f"{hashes[name]}  {name}\n" for name in sorted(hashes))


def notes_text(version: str, python: str, commit: str, archives: dict[str, tuple[str, str]], history: str) -> str:
    """The text of ``release-notes.md``; ``archives`` maps each archive name to its platform and SHA-256,
    ``history`` is the commit of ``HEAD`` of the clone of ``delib-history`` both packages hold."""
    tag = f"v{version}"
    rows = "".join(f"| {platform} | `{name}` | `{digest}` |\n"
                   for name, (platform, digest) in sorted(archives.items()))
    return f"""# DeltaRecon {version}

Release `{tag}`, built from commit `{commit}`. Both packages hold the same clone of `delib-history`; its `HEAD` is commit `{history}`.

| Platform | Archive | SHA-256 |
|---|---|---|
{rows}
## Start with the demo

On Windows, unpack the zip (Explorer's "Extract All" or `Expand-Archive` in PowerShell) and double-click `quickstart.cmd` in the package folder. Or start it from the package folder in cmd:

```bat
quickstart.cmd
```

or in PowerShell:

```powershell
.\\quickstart.cmd
```

On Linux, unpack the archive and start the demo from the package folder:

```sh
tar -xzf deltarecon-{version}-x86_64-unknown-linux-gnu.tar.gz
cd deltarecon-{version}-x86_64-unknown-linux-gnu
./quickstart
```

The demo explains four steps of the quick start and waits for Enter before each. Each package folder holds a guide, `LIESMICH.txt` in German and `README.txt` in English, which says how to start the demo and where it writes its files. The single commands of the quick start are in the guide and in the README.

## What a package holds

A package is one folder that runs DeltaRecon without Python, uv or Git on the machine. It holds:

- `python/`: a standalone CPython {python}, the version that `requires-python` in `pyproject.toml` pins;
- the runtime libraries locked in `uv.lock` and DeltaRecon itself with its contract pack, installed in that Python;
- `delib-history/`: a full clone of the reference model repository, with its history, at the commit named above, its remote the repository on GitHub;
- `profiles/`: the tolerance profiles the quick start uses, the files Git tracks in `profiles/` of the commit;
- `LICENSE`, the licence of DeltaRecon, in the package folder itself;
- the launcher, `deltarecon` on Linux and `deltarecon.cmd` on Windows, which runs DeltaRecon on the clone in the package (`DELTARECON_REPOSITORIES`) with the packaged Python, started with `-P -s` and without `PYTHONHOME`, so neither the current folder nor the user's site-packages nor `PYTHONHOME` replaces the packaged code, while `PYTHONPATH` still reaches it;
- the starter of the guided demo, `quickstart` on Linux and `quickstart.cmd` on Windows, which runs `deltarecon quickstart` in the package folder;
- the guides `LIESMICH.txt` (German) and `README.txt` (English).

The quick start of the package is in the README at this tag: {REPOSITORY_URL}/blob/{tag}/README.md#quick-start

## Verify the download

Download `{SUMS}` beside the archive. On Linux, `sha256sum -c {SUMS}` in that folder must report `OK` for each archive (add `--ignore-missing` when only one archive is downloaded). On Windows, `Get-FileHash -Algorithm SHA256 <zip>` in PowerShell prints the SHA-256 of the zip; it must equal the value in the table above and in `{SUMS}`.

The Windows package is not signed, so SmartScreen or the browser may warn when it is downloaded or run.
"""


def release(output: Path, source: str, builder=None, git=None) -> tuple[str, str, list[Path]]:
    """Build both archives into ``output`` from one clone of ``source`` and write ``SHA256SUMS`` and the
    notes; the commit, the ``HEAD`` of the clone of ``delib-history``, and the archives.

    ``builder`` defaults to ``build`` of ``tools/assembly.py``, ``git`` to ``git_text`` of
    ``tools/common.py`` (git in this checkout, None on failure).
    """
    builder = builder or assembly.build
    git = git or common.git_text
    version, python = project()
    dirty = dirty_paths(git)
    if dirty:
        raise Refused(f"the working tree is not clean: {', '.join(dirty)}")
    if output.exists() or output.is_symlink():
        raise Refused(f"the output {output} exists already")
    commit = head(git)
    require_upstream(source)
    print(f"release: building {version} from commit {commit}", flush=True)
    output.parent.mkdir(parents=True, exist_ok=True)
    clones = Path(tempfile.mkdtemp(prefix=f".{output.name}.", dir=output.parent))
    try:
        clone = clones / f"{common.CLONE_NAME}.git"
        history = clone_source(source, clone)
        print(f"release: cloned {source} once; delib-history at commit {history}", flush=True)
        archives = []
        for target in TARGETS:
            archive = builder(output, str(clone), target)
            print(f"release: built {archive.name}", flush=True)
            archives.append(archive)
    finally:
        shutil.rmtree(clones, ignore_errors=True)
    after = git("rev-parse", "HEAD")
    if after != commit:
        raise Failed(f"HEAD changed during the build: it was {commit}, it is {after}")
    dirty = dirty_paths(git)
    if dirty:
        raise Failed(f"the working tree changed during the build: {', '.join(dirty)}")
    hashes = {archive.name: common.sha256_file(archive) for archive in archives}
    rows = {name: (PLATFORMS[targets.target_of(Path(name), version)], digest) for name, digest in hashes.items()}
    (output / SUMS).write_bytes(sums_text(hashes).encode("utf-8"))
    (output / NOTES).write_bytes(notes_text(version, python, commit, rows, history).encode("utf-8"))
    return commit, history, archives


def parse(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="release",
        description="Build the Linux and the Windows package from one clean commit into a release folder and "
                    f"write {SUMS} and {NOTES} there. Publishes nothing and checks no archive.")
    parser.add_argument("--output", type=Path,
                        help="the release folder, which must not exist and must lie outside the working tree or in an "
                             "ignored folder (default dist/release-v<version>/)")
    parser.add_argument("--source", default=assembly.DEFAULT_SOURCE,
                        help="what delib-history is cloned from, once for both packages: a URL or a local path, "
                             "which must not be behind the upstream of its checked-out branch "
                             f"(default {assembly.DEFAULT_SOURCE})")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    arguments = parse(argv)
    try:
        output = (arguments.output or default_output(project()[0])).resolve()
        commit, history, archives = release(output, arguments.source)
        print(f"release: written {', '.join(archive.name for archive in archives)}, {SUMS} and {NOTES} "
              f"of commit {commit} (delib-history {history}) in {output}")
        return 0
    except Refused as refusal:
        print(f"release: {refusal}", file=sys.stderr)
        return 2
    except Failed as failure:
        print(f"release: {failure}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
