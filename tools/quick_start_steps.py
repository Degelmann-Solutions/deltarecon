"""The quick-start commands of the README as steps, and how their ``runs/`` folders are rewritten.

The measurement, the package guides and the package checks read them from here.
"""
from __future__ import annotations

import shlex
from pathlib import Path

RUNS = "runs/"


def _step(command: str, needs: tuple[str, ...] = (), expect: int = 0) -> dict:
    return {"argv": shlex.split(command), "needs": needs, "expect": expect}


# The quick-start commands of the README, verbatim and in order; tests/test_measure.py keeps them in sync.
STEPS: dict[str, dict] = {
    "request": _step("uv run deltarecon request --revision fa368575a66d97c94e96dffc62b273ec95511b12 --label N "
                     "--run-id run-n-full --output runs/n-full/request.json"),
    "run": _step("uv run deltarecon run runs/n-full/request.json", ("request",)),
    "replay": _step("uv run deltarecon replay runs/n-full/run-record.json", ("run",)),
    "regression": _step("uv run deltarecon regression runs/n-full/run-record.json "
                        "--revision 887b7181d22550eda2fb52fa1a6bd77376d4eb2e --output runs/regression-n",
                        ("run",), expect=1),
    "derive": _step("uv run deltarecon derive runs/n-full/run-record.json runs/regression-n/run/run-record.json "
                    "--output runs/changes.json", ("run", "regression")),
    "search": _step("uv run deltarecon search runs/n-full/run-record.json runs/regression-n/run/run-record.json "
                    "--quantity Bruttobeitrag --periods 0-59 --tolerance profiles/tolerance-bruttobeitrag.json "
                    "--target-only --output runs/search", ("run", "regression")),
}

# Where a step's result names its number of states: the file below the work folder and the reader.
STATES = {
    "search": ("search/search.result.json", lambda result: result["runs"]["search"]),
}


def rewrite(argv: list[str], work: Path) -> list[str]:
    """``argv`` with the leading ``runs/`` of every argument replaced by the work folder."""
    return [str(work / argument[len(RUNS):]) if argument.startswith(RUNS) else argument for argument in argv]


def expand(names: list[str], steps: dict[str, dict] = STEPS) -> list[str]:
    """The named steps and every step they need, in the order of ``steps``."""
    wanted: set[str] = set()

    def add(name: str) -> None:
        if name not in wanted:
            wanted.add(name)
            for need in steps[name]["needs"]:
                add(need)

    for name in names:
        add(name)
    return [name for name in steps if name in wanted]
