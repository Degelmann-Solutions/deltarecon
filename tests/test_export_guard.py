"""The guard that the computation path ``export`` gives the bits of the path ``modelx``.

The guard projects every state of a first-parent chain on both paths and compares, on each
state, the list of model point ids and, per point, either every projected value as
``float.hex``, so that ``-0.0`` differs from ``0.0``, or the message of the failed point. A
state is the tree and the model point table of its own commit, without a patch: the older
end of the chain and every revision after it up to the newer end. The values are read
through the engine session, not through ``results.csv``, whose writer form gives ``-0.0``
and ``0.0`` the same text. The guard collects every difference across all states and fails
once, listing up to 20 of them; a state that cannot be opened on one path is a difference.

The ends are full commit hashes in ``DELTARECON_GUARD_OLDER`` and ``DELTARECON_GUARD_NEWER``
and default to the ends of the reference walk, the start commit of the reference chain, which holds
release N on the fixed model, and the newer revision of the oracle: 33 states of 350 model points
each. The guard ran about 49 minutes on the author's machine and is skipped unless it is asked
for: ``DELTARECON_GUARD=1``. The fast tests check the ends and the chain with Git alone.
"""
from __future__ import annotations

import os

import pytest

from degelmann.deltarecon.documents import Rejection
from degelmann.deltarecon.engines.reference_model import PATHS, ReferenceModel, release_references
from degelmann.deltarecon.run import ModelPointFailure

from conftest import CLONE, NEWER, REPOSITORIES, START, require_clone

LISTED = 20  # the differences a failing guard lists


def ends() -> tuple[str, str]:
    """The ends of the guard's chain: ``DELTARECON_GUARD_OLDER`` and ``DELTARECON_GUARD_NEWER``, or the
    ends of the reference walk."""
    return os.environ.get("DELTARECON_GUARD_OLDER", START), os.environ.get("DELTARECON_GUARD_NEWER", NEWER)


def chain(older: str, newer: str) -> list[str]:
    """The states of the guard: ``older`` and every revision of the history up to ``newer``, oldest first."""
    history = ReferenceModel().history({"references": release_references(older)},
                                       {"references": release_references(newer)}, REPOSITORIES)
    return [older] + [revision.id for revision in history.revisions]


def projected(revision: str, path: str) -> tuple[list[str], dict[str, object]]:
    """The model point ids of a state on one path and, per point, its values as ``float.hex``
    by period or the message of its failure."""
    release = {"label": "guard", "references": release_references(revision, revision, path)}
    with ReferenceModel().open(release, [], None, REPOSITORIES) as session:
        ids = session.model_point_ids()
        points = {}
        for point in ids:
            try:
                points[point] = [(period, [value.hex() for value in values])
                                 for period, values in session.project(point)]
            except ModelPointFailure as failure:
                points[point] = f"failed: {failure}"
        return ids, points


def differences(revision: str, export, modelx) -> list[str]:
    """The differences of one state between its outcome on the path export and on modelx."""
    if isinstance(export, str) or isinstance(modelx, str):
        return [f"{revision}: {name} {outcome}" for name, outcome in (("export", export), ("modelx", modelx))
                if isinstance(outcome, str)]
    (export_ids, export_points), (modelx_ids, modelx_points) = export, modelx
    if export_ids != modelx_ids:
        return [f"{revision}: the model point ids differ"]
    found = []
    for point in export_ids:
        left, right = export_points[point], modelx_points[point]
        if left == right:
            continue
        if isinstance(left, str) or isinstance(right, str) or len(left) != len(right):
            found.append(f"{revision} {point}: export {str(left)[:200]} | modelx {str(right)[:200]}")
            continue
        for (left_period, left_values), (right_period, right_values) in zip(left, right):
            if (left_period, left_values) != (right_period, right_values):
                found.append(f"{revision} {point} period {left_period}: export {left_values} "
                             f"| modelx {right_period} {right_values}")
                break
    return found


def test_the_chain_of_the_default_ends_holds_33_states_from_the_start():
    require_clone(CLONE, NEWER)
    states = chain(START, NEWER)
    assert len(states) == len(set(states)) == 33
    assert states[0] == START and states[-1] == NEWER


def test_the_ends_of_the_chain_are_read_from_the_environment(monkeypatch):
    require_clone(CLONE, NEWER)
    states = chain(START, NEWER)
    monkeypatch.delenv("DELTARECON_GUARD_OLDER", raising=False)
    monkeypatch.delenv("DELTARECON_GUARD_NEWER", raising=False)
    assert ends() == (START, NEWER)
    monkeypatch.setenv("DELTARECON_GUARD_OLDER", states[3])
    monkeypatch.setenv("DELTARECON_GUARD_NEWER", states[7])
    assert ends() == (states[3], states[7])
    assert chain(*ends()) == states[3:8]
    # Ends in the wrong order lie on no common main line: the guard fails, it does not pass empty.
    with pytest.raises(Rejection) as rejected:
        chain(NEWER, START)
    assert rejected.value.code == "unrelated_revisions"


@pytest.mark.skipif(os.environ.get("DELTARECON_GUARD") != "1",
                    reason="the guard that the export gives the bits of modelx runs on request: DELTARECON_GUARD=1")
def test_the_export_gives_the_bits_of_modelx_on_every_state_of_the_chain():
    older, newer = ends()
    require_clone(CLONE, newer)
    found = []
    states = chain(older, newer)
    for revision in states:
        outcomes = {}
        for path in PATHS:
            try:
                outcomes[path] = projected(revision, path)
            except Exception as exc:  # a state that cannot be opened is a difference
                outcomes[path] = f"could not be opened or computed: {type(exc).__name__}: {exc}"
        found += differences(revision, outcomes["export"], outcomes["modelx"])
    assert not found, (f"{len(found)} differences on {len(states)} states, the first {LISTED}:\n"
                       + "\n".join(found[:LISTED]))
