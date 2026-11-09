"""The protocol between the core and a calculation engine, and the types an engine needs.

This module uses the standard library alone, so that an engine can import it without
loading the core (no jsonschema, no modelx). The core modules import these names from here;
:mod:`degelmann.deltarecon.run`, :mod:`degelmann.deltarecon.documents` and
:mod:`degelmann.deltarecon.errors` re-export them, so each name is one class wherever it is
imported from.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import ContextManager, Mapping, Protocol

# An engine restores a release into a folder of the system's temporary folder whose name
# starts with this prefix. A message of the outcome ``error`` names it ``<scratch>``.
SCRATCH_PREFIX = "deltarecon-"


class Rejection(Exception):
    """A broken rule of the contracts, with the diagnostic it leads to."""

    def __init__(self, code: str, message: str, *, model_point_ids=None, change_ids=None):
        super().__init__(f"{code}: {message}")
        self.code = code
        self.message = message
        self.model_point_ids = list(model_point_ids or [])
        self.change_ids = list(change_ids or [])

    def diagnostic(self) -> dict:
        entry = {"code": self.code, "message": self.message}
        if self.model_point_ids:
            entry["model_point_ids"] = self.model_point_ids
        if self.change_ids:
            entry["change_ids"] = self.change_ids
        return entry


class UsageError(Exception):
    """The procedure cannot start because of how it was called.

    A file or folder it reads is missing or unreadable, or an input it reads is not of the kind
    it takes (such as a tolerance file that violates its schema, or a recorded run with enabled
    changes where a run without one is required); a request it is about to write, such as a
    state request a walk or a search builds, would violate its schema; an output exists already;
    a number of workers is not a whole number of at least 1; a switch is given without the
    switch or the value it needs; an option has a value it does not take; the engine a command
    selects cannot be loaded or called; or the history of a clone is cut off. It writes no document and is not a :class:`Rejection`.
    """


class ModelPointFailure(Exception):
    """The engine could not calculate one model point."""


class Session(Protocol):
    """One release state, opened for a run."""

    time_basis: str
    quantities: list[tuple[str, str]]  # name and unit, in export column order

    def model_point_ids(self) -> list[str]:
        """The public id of every model point of the release state, repeats included."""

    def project(self, model_point_id: str) -> list[tuple[int, list[float]]]:
        """The periods of one model point with one value per quantity.

        Raises :class:`ModelPointFailure` when the model point cannot be calculated.
        """

    # A session may also offer ``project_many(model_point_ids)``: the outcome of each id in
    # the given order, its periods as ``project`` returns them or the ModelPointFailure that
    # ``project`` would raise. Any other exception propagates. A session without it is
    # projected point by point through ``project``.
    #
    # A session that computes a target offers ``project_target(model_point_ids, quantities,
    # periods)``: ``quantities`` are names the session declares, in its declared order, and
    # ``periods`` is ``(first, last)`` in projection periods or ``None``. The outcome of each id
    # in the given order is a ModelPointFailure or the periods of its target window, with one
    # value per name of ``quantities``: from the period of its valuation date s plus ``first`` to
    # the lesser of s plus ``last`` and its last period, or every period without ``periods``. A
    # point whose window is empty has no period. No model check is evaluated: a point fails only
    # when a target value cannot be calculated. A session without it cannot run a target.

    def parameters(self) -> list[dict]:
        """The parameter inventory of the release state, in the form of the run record.

        The order of the parameters and of the rows of a keyed table carries no meaning.
        """


@dataclass(frozen=True)
class DomainReference:
    """The domain reference of a stage, by its label: what the quantities, their units and signs,
    and the time basis of the stage mean. Both members are opaque non-empty strings; ``version``
    changes only when the text of the reference changes meaning."""

    id: str
    version: str


# The domain reference of ``liability_cashflow`` as published in version 3 of the contract pack,
# ``contracts/v3/domain/liability_cashflow.md``. The pair is reserved for that text.
LIABILITY_CASHFLOW = DomainReference("liability_cashflow", "3")


@dataclass(frozen=True)
class StageDeclaration:
    """A stage an engine declares: its domain reference and the quantity names that reference
    defines, in domain order."""

    domain_reference: DomainReference
    quantities: tuple[str, ...]


@dataclass(frozen=True)
class Revision:
    """One revision on the main line of a history, as an engine reports it."""

    id: str                 # the full identifier of the revision
    message: str            # its log message as written; it may be empty
    classes: frozenset[str]  # the classes of the paths it touches: data, parameter, code


@dataclass(frozen=True)
class History:
    """The history between two release identities."""

    source: str                # the kind of history, for example ``git``
    older: str                 # the identifier of the older revision
    newer: str                 # the identifier of the newer revision
    revisions: tuple[Revision, ...]  # the main line after ``older`` up to ``newer``, oldest first


class Engine(Protocol):
    """A calculation engine behind the run contract.

    The command line loads the engine class from ``--engine <module>:<class>``, else from the
    environment variable ``DELTARECON_ENGINE``, else it takes
    ``degelmann.deltarecon.engines.reference_model:ReferenceModel``, and calls the class with
    the worker count alone: ``cls()`` when the command is given no ``--workers``, so the engine
    takes its count from the environment itself; ``cls(N)`` with ``--workers N``; and ``cls(1)``
    for ``request`` and ``derive``, which project no model point. The core does not read
    ``DELTARECON_WORKERS``. An engine that has no use for workers accepts the argument and
    ignores it.

    ``request`` writes the release identity :meth:`describe` gives for the revision and the engine
    options it is given, and checks it through :meth:`resolve` before anything is written.
    ``regression`` describes its release with :meth:`describe`, given the input revision
    :meth:`input_revision` reads from the release identity of the recorded run.
    """

    # Each stage the engine supports, with its declaration: the domain reference the engine names
    # for it and the quantity names of that reference in domain order. The core admits a request
    # of a stage named here alone, checks the names a session declares against the declared
    # quantities (rule 7 of the run contract), and writes the domain reference into every response
    # of the stage. A comparison checks no list of its own: both sides name the same stage, domain
    # reference, and quantities. Walk, search, regression, and replay refuse a record whose domain
    # reference differs from the one declared here for its stage.
    stages: Mapping[str, StageDeclaration]
    realisations: frozenset[str]  # the realisation types of a change the engine can apply
    determines: frozenset[str]    # the kinds of release reference one revision fixes
    # The kinds the engine can hold at the release of a request while revisions are enabled,
    # each with the classes of the paths that carry it, for example ``input_data``: ``data``.
    holdable: Mapping[str, frozenset[str]]

    def resolve(self, stage: str, release: dict, repositories: Path) -> None:
        """Check that the release identity names a state of the stage ``stage`` the engine can restore.

        ``stage`` is the stage of the request, one of ``stages``.

        ``repositories`` is the folder that holds what the engine restores a release from,
        for example local clones. Nothing is restored and nothing is written.

        Raises a :class:`Rejection` with ``unknown_reference`` when the references cannot
        be resolved.
        """

    def describe(self, stage: str, label: str, revision: str, options: Mapping[str, str], repositories: Path,
                 input_revision: str | None = None) -> dict:
        """The release identity of the run contract for the revision ``revision`` of the stage ``stage``.

        The result is ``{"label": label, "references": [...]}``: the complete set of references
        that names the state of ``revision``, as :meth:`resolve` reads it. How ``revision`` is
        named is the engine's matter, for example a hash, a branch, a tag, or ``HEAD``.
        ``input_revision``, when given, is the identifier of a revision as a recorded release
        identity holds it, taken as given and not resolved again; the input data is then that
        of this revision. ``options`` are the engine options of the command line, by key, for
        example a computation path.

        Nothing is restored and nothing is written. Raises a :class:`UsageError` for an option
        the engine does not take, a key or a value, before it reads the revision, and a
        :class:`Rejection` with ``unknown_reference`` when ``revision`` names nothing.
        """

    def input_revision(self, release: dict) -> str:
        """The identifier of the revision the recorded release identity ``release`` takes its input data from.

        ``release`` is a recorded release identity of any engine version or computation path.
        The result is the identifier in the form :meth:`describe` takes for ``input_revision``.
        Nothing is restored and nothing is written. Raises a :class:`Rejection` with
        ``unknown_reference`` when ``release`` names no state the engine can read.
        """

    def open(self, stage: str, release: dict, enabled: list[dict], manifest_dir: Path | None,
             repositories: Path, hold: frozenset[str] = frozenset()) -> ContextManager[Session]:
        """Restore the release state of the stage ``stage``, apply the enabled changes, and open it for reading.

        ``stage`` is the stage of the request, one of ``stages``.

        ``enabled`` holds the enabled changes in application order; every one has a
        realisation type the engine declares. ``manifest_dir`` is the folder of the change
        manifest, which the paths of its artifacts are relative to; it is ``None`` when no
        change is enabled. What ``repositories`` holds is never altered. A scratch folder
        is created in the system's temporary folder with a name that starts with
        :data:`SCRATCH_PREFIX`.

        For changes of the type ``revision`` the engine restores the state after the last
        enabled revision. ``hold`` names the kinds of release reference it then takes from
        ``release`` instead of from that revision; each is a kind of ``holdable``.

        Raises a :class:`Rejection` with ``invalid_manifest`` when a change does not apply.
        Any other exception, here or from a call of the session other than ``project``,
        ends the run with the outcome ``error``.
        """

    def history(self, older: dict, newer: dict, repositories: Path) -> History:
        """The history between the revisions two release identities name.

        Which references of an identity name its revision is the engine's matter; it reads
        no reference that a revision does not fix and does not check its own version. The
        result lists every revision on the main line after the older one, up to and
        including the newer one, each with its log message and the classes of the paths it
        touches against the revision before it. It is empty when both identities name one
        revision. Nothing is restored and nothing is written.

        The message is the text of the revision as it was written, decoded by the engine:
        bytes that are not UTF-8 become U+FFFD. The line breaks at its end stay; the caller
        removes them and puts the identifier in the place of an empty message.

        Raises a :class:`Rejection` with ``unknown_reference`` when an identity names no
        revision the engine can read, and with ``unrelated_revisions`` when the older
        revision does not lie on the main line of the newer one. Raises a
        :class:`UsageError` when the history at hand is cut off.
        """

    def state_release(self, base: dict, revision: str | None, hold: frozenset[str],
                      repositories: Path) -> dict:
        """The release identity of the state after ``revision``, as this engine would record it.

        ``base`` is a recorded release identity, of any engine version. The result has the
        label of ``base``, names the present engine, on the computation path ``base`` names
        when the engine has several, and names the state after ``revision``
        with the kinds in ``hold`` taken from ``base``; for ``revision`` ``None`` it names
        the state of ``base`` itself. Nothing is restored and nothing is written.

        Raises a :class:`Rejection` with ``unknown_reference`` when ``base`` names no state
        the engine can read.
        """
