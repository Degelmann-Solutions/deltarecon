"""A toy engine with two stages, built against the protocol module of DeltaRecon alone.

It shows what an engine implements to be connected to DeltaRecon. It uses the standard library
and :mod:`degelmann.deltarecon.protocol`, nothing else of DeltaRecon. Select it with

    --engine toy_engine:ToyEngine --engine-path examples/toy_engine

The values are trivial on purpose; ``DOMAIN.md`` beside this module says what they mean.

Its history is a folder, not a Git repository: ``history/log.json`` lists the revisions, oldest
first, and that order is the main line. Each revision ``<id>`` has a folder ``history/<id>/``
with three files, each of one class of the changes contract:

- ``points.csv`` (``id,sum_insured,premium,term``), class ``data``
- ``parameters.csv`` (``name,value``, the one row ``rate``), class ``parameter``
- ``rules.json`` (``{"claims": "plain"|"loaded"}``, an optional ``"comment"``), class ``code``

A revision touches the classes of the files whose bytes differ from the revision before it.
A release identity names one revision for each kind it holds: ``code_state`` (``rules.json``),
``parameter_set`` (``parameters.csv``), and ``input_data`` (``points.csv``), each as
``toy:<revision>``, and ``engine_version`` ``toy-engine 1``. A regression mixes them: the state
of the newer revision on the input data of the recorded run.
"""
from __future__ import annotations

import csv
import json
import shutil
import tempfile
from contextlib import contextmanager
from pathlib import Path

from degelmann.deltarecon.protocol import (SCRATCH_PREFIX, DomainReference, History, ModelPointFailure,
                                           Rejection, Revision, StageDeclaration, UsageError)

ENGINE_VERSION = "toy-engine 1"
PREFIX = "toy:"
# The file of each kind a revision fixes, and the class of that file.
FILES = {"code_state": ("rules.json", "code"), "parameter_set": ("parameters.csv", "parameter"),
         "input_data": ("points.csv", "data")}
KINDS = tuple(FILES)  # the order of the references of a release identity
# The factor of the expected claims under each claims rule.
CLAIMS_FACTOR = {"plain": 1.0, "loaded": 1.05}
# Version 3 of the changes contract defines the history source ``git`` alone, so the toy history,
# a folder, reports that source; it has the same shape: a main line of revisions, oldest first.
HISTORY_SOURCE = "git"

PREMIUM = "toy_premium"
CLAIMS = "toy_claims"
# The quantities of each stage, with their units, in domain order (see DOMAIN.md).
QUANTITIES = {PREMIUM: [("policies", "policies"), ("premium", "EUR")],
              CLAIMS: [("expected_claims", "EUR")]}


class ToySession:
    """One release state of a stage: the three files in a scratch folder."""

    time_basis = "projection_year"  # period 0 is the valuation year

    def __init__(self, stage: str, folder: Path):
        self.quantities = list(QUANTITIES[stage])
        with open(folder / "points.csv", newline="", encoding="utf-8") as stream:
            self.points = list(csv.DictReader(stream))
        with open(folder / "parameters.csv", newline="", encoding="utf-8") as stream:
            self.params = {row["name"]: row["value"] for row in csv.DictReader(stream)}
        self.rate = float(self.params["rate"])
        rules = json.loads((folder / "rules.json").read_text("utf-8"))
        self.factor = CLAIMS_FACTOR[rules["claims"]]

    def model_point_ids(self) -> list[str]:
        return [point["id"] for point in self.points]

    def project(self, model_point_id: str) -> list[tuple[int, list[float]]]:
        """For t = 0 ... n-1: policies (1-q)^t, premium P(1-q)^t, expected claims S q (1-q)^t f."""
        point = next(point for point in self.points if point["id"] == model_point_id)
        try:
            insured, premium, term = float(point["sum_insured"]), float(point["premium"]), int(point["term"])
        except ValueError:
            raise ModelPointFailure(f"the model point {model_point_id} holds a value that is not a number") from None
        if term < 1:
            raise ModelPointFailure(f"the model point {model_point_id} has no remaining year")
        q = self.rate
        periods = []
        for t in range(term):
            in_force = (1 - q) ** t
            values = {"policies": in_force, "premium": premium * in_force,
                      "expected_claims": insured * q * in_force * self.factor}
            periods.append((t, [values[name] for name, _ in self.quantities]))
        return periods

    def parameters(self) -> list[dict]:
        return [{"name": "rate", "type": "scalar", "value": self.rate}]


class ToyEngine:
    """The toy engine. Its default repositories folder is ``history/`` beside this module."""

    stages = {
        PREMIUM: StageDeclaration(DomainReference("deltarecon-examples/toy_premium", "1"), ("policies", "premium")),
        CLAIMS: StageDeclaration(DomainReference("deltarecon-examples/toy_claims", "1"), ("expected_claims",)),
    }
    realisations = frozenset({"revision"})
    determines = frozenset(KINDS)
    holdable = {"input_data": frozenset({"data"})}

    def __init__(self, workers=None):
        """The toy engine projects in one process; the worker count is accepted and ignored."""

    # --- the history ---------------------------------------------------------------------

    def repositories_folder(self, given):
        return Path(given) if given is not None else Path(__file__).parent / "history"

    @staticmethod
    def _log(repositories: Path) -> list[dict]:
        """The revisions of ``log.json``, oldest first."""
        path = Path(repositories) / "log.json"
        try:
            log = json.loads(path.read_text("utf-8"))
        except (OSError, ValueError) as error:
            raise UsageError(f"the toy history {path} cannot be read ({error})") from None
        return log

    def _ids(self, repositories: Path) -> list[str]:
        return [entry["id"] for entry in self._log(repositories)]

    @staticmethod
    def _value(release: dict, kind: str) -> str:
        """The one value of ``kind`` in ``release``."""
        values = [reference["value"] for reference in release["references"] if reference["kind"] == kind]
        if len(values) != 1:
            raise Rejection("unknown_reference", f"The release identity holds no single {kind} reference.")
        return values[0]

    def _revision(self, release: dict, kind: str, ids: list[str] | None = None) -> str:
        """The revision the reference of ``kind`` names; with ``ids``, one of them."""
        value = self._value(release, kind)
        revision = value[len(PREFIX):] if value.startswith(PREFIX) else None
        if not revision or (ids is not None and revision not in ids):
            raise Rejection("unknown_reference", f"The {kind} reference {value!r} names no revision of the "
                            "toy history.")
        return revision

    @staticmethod
    def _identity(label: str, revisions: dict[str, str]) -> dict:
        return {"label": label, "references": [{"kind": kind, "value": PREFIX + revisions[kind]} for kind in KINDS]
                + [{"kind": "engine_version", "value": ENGINE_VERSION}]}

    def history(self, older, newer, repositories):
        ids = self._ids(repositories)
        # A revision fixes all three kinds; code_state names it, as the others name the same one
        # in an identity this engine records for a revision.
        first, last = (ids.index(self._revision(release, "code_state", ids)) for release in (older, newer))
        if first > last:
            raise Rejection("unrelated_revisions", f"The revision {ids[first]} does not stand before "
                            f"{ids[last]} on the main line of the toy history.")
        messages = {entry["id"]: entry.get("message", "") for entry in self._log(repositories)}
        revisions = []
        for before, after in zip(ids[first:last], ids[first + 1:last + 1]):
            classes = frozenset(cls for name, cls in FILES.values()
                                if (Path(repositories) / before / name).read_bytes()
                                != (Path(repositories) / after / name).read_bytes())
            revisions.append(Revision(after, messages[after], classes))
        return History(HISTORY_SOURCE, ids[first], ids[last], tuple(revisions))

    # --- release identities ----------------------------------------------------------------

    def describe(self, stage, label, revision: str, options, repositories, input_revision: str | None = None):
        if options:
            raise UsageError(f"the toy engine takes no engine option, not {sorted(options)[0]!r}")
        if revision not in self._ids(repositories):
            raise Rejection("unknown_reference", f"The toy history holds no revision {revision!r}.")
        revisions = dict.fromkeys(KINDS, revision)
        if input_revision is not None:
            revisions["input_data"] = input_revision
        return self._identity(label, revisions)

    def input_revision(self, release):
        return self._revision(release, "input_data")

    def state_release(self, base, revision: str | None, hold, repositories):
        ids = self._ids(repositories)
        recorded = {kind: self._revision(base, kind, ids) for kind in KINDS}
        if revision is None:
            return self._identity(base["label"], recorded)
        moved = dict.fromkeys(KINDS, revision)
        for kind in hold:
            moved[kind] = recorded[kind]
        return self._identity(base["label"], moved)

    def _files(self, release: dict, repositories: Path) -> dict[str, Path]:
        """The file of each kind the release names; the identity must be one this engine records."""
        ids = self._ids(repositories)
        kinds = sorted(reference["kind"] for reference in release["references"])
        if kinds != sorted([*KINDS, "engine_version"]) or self._value(release, "engine_version") != ENGINE_VERSION:
            raise Rejection("unknown_reference", f"The release identity is not one of {ENGINE_VERSION}: it names "
                            f"the kinds {', '.join(KINDS)} and engine_version {ENGINE_VERSION!r} once each.")
        return {kind: Path(repositories) / self._revision(release, kind, ids) / FILES[kind][0] for kind in KINDS}

    def resolve(self, stage, release, repositories):
        self._files(release, repositories)

    # --- a release state -----------------------------------------------------------------

    @contextmanager
    def open(self, stage, release, enabled, manifest_dir, repositories, hold=frozenset()):
        """The files of the release, or of the last enabled revision with ``points.csv`` of the
        release when ``input_data`` is held, copied to a scratch folder."""
        files = self._files(release, repositories)
        revisions = [change["realisation"]["revision"] for change in enabled]
        if revisions:
            ids = self._ids(repositories)
            for change, revision in zip(enabled, revisions):
                if revision not in ids:
                    raise Rejection("invalid_manifest", f"The change {change['id']} names the revision {revision!r}, "
                                    "which the toy history does not hold.", change_ids=[change["id"]])
            last = revisions[-1]
            files = {kind: (path if kind in hold else Path(repositories) / last / FILES[kind][0])
                     for kind, path in files.items()}
        with tempfile.TemporaryDirectory(prefix=SCRATCH_PREFIX) as scratch:
            for kind, path in files.items():
                shutil.copyfile(path, Path(scratch) / FILES[kind][0])
            yield ToySession(stage, Path(scratch))
