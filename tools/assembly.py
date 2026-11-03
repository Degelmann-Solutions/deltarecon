"""The build of a package: the folder ``deltarecon-<version>-<target>/`` and its archive.

``build`` unpacks the target's pinned Python (``tools/python_runtime.py``), installs the locked
runtime libraries and the DeltaRecon wheel into it (a wheel member that maps to no file Git tracks
fails the build), removes ``pip``, the script folders and the ``direct_url.json`` that names the
wheel's build folder, clones ``delib-history`` in full without the traces of this machine (its
remote is ``DEFAULT_SOURCE``, its reflogs are removed), copies the files of ``profiles/`` that Git
tracks and ``LICENSE``, writes the launcher, the starter of the guided demo (``tools/targets.py``)
and the guides (``tools/guides.py``), and packs the folder.
"""
from __future__ import annotations

import csv
import os
import shutil
import subprocess
import tarfile
import tempfile
import tomllib
import zipfile
from pathlib import Path, PurePosixPath

from tools.common import CLONE_NAME, ROOT, Failed, Refused
from tools.guides import write_guides
from tools.python_runtime import PYPROJECT, fetch_python, project, require_python
from tools.targets import TARGET, TARGETS, archive_name, package_name

DEFAULT_OUTPUT = ROOT / "dist"
DEFAULT_SOURCE = "https://github.com/Degelmann-Solutions/delib-history"
PROFILES = "profiles"
LICENSE = "LICENSE"


def run(argv: list[str], what: str, **options) -> subprocess.CompletedProcess:
    """Run a build command; a failing command fails the build with its output."""
    done = subprocess.run(argv, capture_output=True, text=True, **options)
    if done.returncode != 0:
        raise Failed(f"{what} failed with exit status {done.returncode}: {' '.join(argv)}\n"
                     f"{done.stdout}{done.stderr}".rstrip())
    return done


def remove_pip(folder: Path, target: dict) -> list[str]:
    """Remove the ``pip`` of the Python build and the ``bin`` and ``Scripts`` folders of the
    installed scripts from the package ``folder``; the paths removed, relative to that folder."""
    site = folder / target["site_packages"]
    paths = [site / "bin", site / "Scripts", site / "pip", *site.glob("pip-*.dist-info")]
    for pattern in target["pip"]:
        paths += folder.glob(pattern)
    removed = []
    for path in sorted(set(paths)):
        if path.is_symlink() or path.is_file():
            path.unlink()
        elif path.is_dir():
            shutil.rmtree(path)
        else:
            continue
        removed.append(path.relative_to(folder).as_posix())
    return removed


def drop_direct_url(site: Path) -> list[str]:
    """Remove each ``direct_url.json`` from the distributions in ``site`` and its row from the
    ``RECORD`` beside it; the paths removed, relative to ``site``. An installed wheel's
    ``direct_url.json`` names the folder the wheel was built in."""
    removed = []
    for path in sorted(site.glob("*.dist-info/direct_url.json")):
        name = path.relative_to(site).as_posix()
        path.unlink()
        record = path.parent / "RECORD"
        if record.is_file():
            lines = record.read_bytes().decode("utf-8").splitlines(keepends=True)
            kept = [line for line in lines if not line.strip() or next(csv.reader([line]))[0] != name]
            record.write_bytes("".join(kept).encode("utf-8"))
        removed.append(name)
    return removed


def tracked_files(*paths: str, root: Path = ROOT) -> list[str]:
    """The files below ``paths`` (all, without ``paths``) that Git tracks in ``root``, relative to it, sorted."""
    done = run(["git", "-C", str(root), "ls-files", "-z", "--", *paths], f"git ls-files in {root}")
    return sorted(name for name in done.stdout.split("\0") if name)


def copy_tracked(folder: str, destination: Path, root: Path = ROOT) -> list[str]:
    """Copy the files below ``folder`` that Git tracks in ``root`` to the same paths below
    ``destination``; ignored and untracked files stay behind. The paths copied."""
    names = tracked_files(folder, root=root)
    for name in names:
        source = root / name
        if not source.is_file():
            raise Failed(f"the tracked file {name} is missing from {root}")
        target = destination / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
    return names


def wheel_strays(wheel: Path, tracked: set[str], pyproject: Path = PYPROJECT) -> list[str]:
    """The members of ``wheel`` that map to no file of ``tracked``, sorted. A member below a folder
    of ``[tool.hatch.build.targets.wheel.force-include]`` maps to the checkout folder it was copied
    from, any other to its own path; the ``.dist-info`` folder is written by the build and is skipped."""
    included = tomllib.loads(pyproject.read_text("utf-8"))["tool"]["hatch"]["build"]["targets"]["wheel"]
    sources = {inside.rstrip("/"): outside.rstrip("/") for outside, inside in included.get("force-include", {}).items()}
    strays = []
    with zipfile.ZipFile(wheel) as zip_file:
        names = [name for name in zip_file.namelist() if not name.endswith("/")]
    for name in names:
        if name.split("/", 1)[0].endswith(".dist-info"):
            continue
        source = name
        for inside in sorted(sources, key=len, reverse=True):
            if name.startswith(inside + "/"):
                source = sources[inside] + name[len(inside):]
                break
        if source not in tracked:
            strays.append(name)
    return sorted(strays)


def write_launcher(folder: Path, target: dict = TARGETS[TARGET], role: str = "launcher") -> Path:
    """The target's launcher (or, with ``role="starter"``, the starter of the guided demo) in ``folder``,
    its text written byte for byte (LF or CRLF as it stands), mode 0755."""
    name, text = target[role]
    path = folder / name
    path.write_bytes(text.encode("utf-8"))
    path.chmod(0o755)
    return path


def is_shallow(clone: Path) -> bool:
    done = run(["git", "-C", str(clone), "rev-parse", "--is-shallow-repository"], "git rev-parse")
    return done.stdout.strip() == "true"


def clone_history(source: str, destination: Path) -> None:
    """A full clone of ``source`` at ``destination``; a shallow result is refused.

    The clone keeps no trace of this machine: its remote ``origin`` is ``DEFAULT_SOURCE`` whatever
    ``source`` was, and ``.git/logs`` (the reflogs, which name the builder and ``source``) is removed.
    The objects are copied through Git's transport (``--no-local``), so no ``objects/info/alternates``
    names a folder of this machine. Its branches, remote-tracking branches and history stay as
    ``git clone`` made them."""
    # --no-local: the objects travel through Git's transport, so the clone holds them itself and keeps
    # no ``objects/info/alternates`` naming a folder of this machine (a source made with --shared).
    run(["git", "clone", "--quiet", "--no-local", source, str(destination)], f"git clone of {source}")
    if is_shallow(destination):
        raise Failed(f"the clone of {source} is shallow; the package needs the full history of {CLONE_NAME}")
    run(["git", "-C", str(destination), "remote", "set-url", "origin", DEFAULT_SOURCE], "git remote set-url")
    reflogs = destination / ".git" / "logs"
    if reflogs.exists():
        shutil.rmtree(reflogs)  # an error fails the build: reflogs left behind would name the builder


def _anonymous(member: tarfile.TarInfo) -> tarfile.TarInfo:
    """A member without the builder's user and group; mode and link target stay."""
    member.uid = member.gid = 0
    member.uname = member.gname = ""
    return member


def make_archive(folder: Path, archive: Path) -> None:
    """``archive`` with ``folder`` as its one top folder. A ``.zip`` is deflated and refuses a
    symbolic link in ``folder``; in a ``.tar.gz`` links stay links, and owners are recorded as uid
    and gid 0 without names."""
    partial = archive.with_name(archive.name + ".partial")
    try:
        if archive.name.endswith(".zip"):
            _write_zip(folder, partial)
        else:
            with tarfile.open(partial, "w:gz") as tar:
                tar.add(folder, arcname=folder.name, filter=_anonymous)
    except BaseException:
        partial.unlink(missing_ok=True)
        raise
    partial.replace(archive)


def _write_zip(folder: Path, archive: Path) -> None:
    entries = []
    for parent, folders, files in os.walk(folder):
        for name in folders + files:
            path = Path(parent) / name
            if path.is_symlink():
                raise Failed(f"the folder {folder} holds a symbolic link, which a .zip does not keep: {path}")
            entries.append(path)
    with zipfile.ZipFile(archive, "w", zipfile.ZIP_DEFLATED, strict_timestamps=False) as zip_file:
        zip_file.write(folder, folder.name)
        for path in sorted(entries):
            zip_file.write(path, f"{folder.name}/{path.relative_to(folder).as_posix()}")


def unpack(archive: Path, destination: Path) -> Path:
    """Unpack ``archive`` (a ``.tar.gz`` with the ``data`` filter, or a ``.zip``) into ``destination``;
    its one top folder."""
    if archive.name.endswith(".zip"):
        with zipfile.ZipFile(archive) as zip_file:
            tops = {PurePosixPath(name).parts[0] for name in zip_file.namelist()}
            _one_top(archive, tops)
            zip_file.extractall(destination)
        return destination / tops.pop()
    with tarfile.open(archive, "r:*") as tar:
        tops = {Path(member.name).parts[0] for member in tar.getmembers()}
        _one_top(archive, tops)
        tar.extractall(destination, filter="data")
    return destination / tops.pop()


def _one_top(archive: Path, tops: set[str]) -> None:
    if len(tops) != 1:
        raise Failed(f"the archive {archive} holds {len(tops)} top folders, expected one: {sorted(tops)}")


def build(output: Path, source: str, target_name: str = TARGET) -> Path:
    """Assemble the package folder and its archive in ``output``; the archive."""
    target = TARGETS[target_name]
    version, python_pin = project()
    if f"cpython-{python_pin}%2B" not in target["url"] or target_name not in target["url"]:
        raise Refused(f"the Python archive of {target_name} does not name Python {python_pin}: {target['url']}")
    name = package_name(version, target_name)
    folder, archive = output / name, output / archive_name(version, target_name)
    for path in (folder, archive):
        if path.exists() or path.is_symlink():
            raise Refused(f"the output {path} exists already")
    for tool in ("uv", "git"):
        if shutil.which(tool) is None:
            raise Refused(f"{tool} is not on PATH")
    python_archive = fetch_python(target)
    print(f"build_package: Python archive {python_archive.name} verified", flush=True)
    output.mkdir(parents=True, exist_ok=True)
    staging = Path(tempfile.mkdtemp(prefix=f".{name}.", dir=output))
    try:
        package = staging / name
        package.mkdir()
        with tarfile.open(python_archive, "r:gz") as tar:
            tar.extractall(package, filter="data")
        found = require_python(package, target, python_pin)
        print(f"build_package: Python {found}", flush=True)
        site = package / target["site_packages"]
        requirements = staging / "requirements.txt"
        exported = run(["uv", "export", "--locked", "--no-dev", "--no-emit-project", "--format", "requirements-txt",
                        "--quiet"], "uv export", cwd=ROOT)
        requirements.write_text(exported.stdout, "utf-8")
        platform_options = ["--python-platform", target_name, "--python-version", python_pin]
        run(["uv", "pip", "install", "--quiet", "--target", str(site), *platform_options, "--require-hashes",
             "--no-deps", "--no-build", "-r", str(requirements)], "uv pip install of the locked libraries", cwd=ROOT)
        wheels = staging / "wheel"
        run(["uv", "build", "--wheel", "--quiet", "--out-dir", str(wheels)], "uv build --wheel", cwd=ROOT)
        wheel = list(wheels.glob("*.whl"))
        if len(wheel) != 1:
            raise Failed(f"uv build --wheel left {len(wheel)} wheels, expected one")
        strays = wheel_strays(wheel[0], set(tracked_files()))
        if strays:
            raise Failed(f"the wheel holds files Git does not track: {', '.join(strays)}")
        run(["uv", "pip", "install", "--quiet", "--target", str(site), *platform_options, "--no-deps",
             str(wheel[0])], "uv pip install of the DeltaRecon wheel", cwd=ROOT)
        removed = remove_pip(package, target)
        removed += [f"{target['site_packages']}/{name}" for name in drop_direct_url(site)]
        print(f"build_package: libraries installed; removed {', '.join(removed) or 'nothing'}", flush=True)
        clone_history(source, package / CLONE_NAME)
        print(f"build_package: cloned {source}; remote set to {DEFAULT_SOURCE}, reflogs removed", flush=True)
        copy_tracked(PROFILES, package)
        shutil.copy2(ROOT / LICENSE, package / LICENSE)
        write_launcher(package, target)
        write_launcher(package, target, "starter")
        write_guides(package, target_name, version)
        make_archive(package, staging / archive.name)
        package.replace(folder)
        (staging / archive.name).replace(archive)
    finally:
        shutil.rmtree(staging, ignore_errors=True)
    return archive
