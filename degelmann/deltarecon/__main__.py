"""Command line of DeltaRecon. Start it from the root of this repository.

    git clone https://github.com/Degelmann-Solutions/delib-history repositories/delib-history
    uv run python -m degelmann.deltarecon request --revision fa368575a66d97c94e96dffc62b273ec95511b12 \\
        --label N --run-id run-n-full --output runs/n-full/request.json
    uv run python -m degelmann.deltarecon run runs/n-full/request.json
    uv run python -m degelmann.deltarecon replay runs/n-full/run-record.json
    uv run python -m degelmann.deltarecon regression runs/n-full/run-record.json --revision HEAD \\
        --output runs/regression-n
    uv run python -m degelmann.deltarecon derive runs/n-full/run-record.json \\
        runs/regression-n/run/run-record.json --output runs/changes.json
    uv run python -m degelmann.deltarecon walk runs/n-full/run-record.json \\
        runs/new-full/run-record.json --output runs/walk
    uv run python -m degelmann.deltarecon search runs/n-full/run-record.json \\
        runs/new-full/run-record.json --quantity Bruttobeitrag --periods 0-59 \\
        --walk runs/walk --output runs/search
    uv run python -m degelmann.deltarecon quickstart

``request`` writes a run request with the complete release identity the engine describes for
``--revision`` and the engine options, after the engine has checked that it can restore it.
How the revision is named is the engine's matter: the reference model reads a commit of the
local clone of its repository, named by a full or abbreviated hash, a branch, a tag, or
``HEAD``; an ancestry suffix such as ``HEAD~1`` is refused, and the request holds the full
hash. ``--engine-option KEY=VALUE`` (repeatable, each key once) passes an option to the
engine; the reference model takes only ``path=export|modelx``, the computation path the engine
version names, export by default. Another key or value, or a key given twice, is a usage error.
``--stage`` names the stage of the request; without it the request is of the engine's only
stage, and an engine that declares several needs it. A stage the engine does not declare is
rejected with ``unsupported_stage``, and nothing is written.
``run`` writes
``response.json``, ``results.csv``, and ``run-record.json`` beside the request.

``run`` ends with the outcome ``error`` when the engine cannot restore or read the state
the request names; the response and the run record are written as for every outcome.

``replay`` repeats a recorded run in ``replay/`` beside the record, compares the recorded
and the repeated run, and writes ``replay-compare.request.json``,
``replay-compare.result.json``, ``replay-compare.deviations.csv`` when the runs are
compared, and ``replay-record.json``. A recorded run with the outcome ``error`` is
repeated and its response compared byte for byte, apart from ``contract_version`` and
``domain_reference`` for a run recorded under 2.0, 3.0, or 3.1 and apart from ``contract_version`` for
one recorded under 3.2; nothing else is compared. The record must name one of the present engine
versions, and the replay repeats the run on the computation path it names. A run record written under
contract version 2.0, 3.0, 3.1, 3.2, or 3.3 is replayed; one written
under 1.0 is rejected with ``unsupported_version``.

``compare`` compares the two runs a compare request names and writes
``compare.result.json`` beside the request, ``compare.deviations.csv`` and
``signature-table.json`` when the outcome is ``compared``, and ``compare.run-record.json``
when the release identities of both runs can be read. A request that is not readable as a
compare request writes nothing.

``regression`` runs the revision ``--revision`` names, as the engine reads it (for the reference
model a commit), on the input data and the selection of
a recorded run, compares the recorded run with the new one, and prints "no deviation above
tolerance" or the deviating model points and the signature table. It writes everything
into the new folder ``--output``. For the reference model, ``--engine-option path=export|modelx``
chooses the computation path the engine version names, export by default. The recorded run may come
from another engine version; the new run uses the present engine on that path, and the output names both versions.
The record of a target-only run is rejected with ``target_only_record``, and nothing runs.

``derive`` reads the records of two succeeded runs without enabled changes, the older one
first, and writes the change manifest of the history between the revisions they name: one
change per revision on the main line, each with the change before it as its only
prerequisite. The same two records give the same bytes. The folder of ``--output`` must
exist. The record of a target-only run, revisions that are not on one main line, a revision
the clone does not hold, and records of two stages are rejected with their diagnostic code, and nothing is written.

``walk`` reads the same two records, derives the manifest, runs every state from the
older revision to the newer one on the selection of both records into the new folder
``--output``, checks state 0 against the older and the last state against the newer
record, and writes ``walk.result.json``: per revision and quantity whether the revision
contributes, the exact sum of the differences and of their absolute values, and the
signature row. It prints one line per step and every finding. Records of different
selections, references that do not fit the history, and the refusals of ``derive`` are
rejected with their diagnostic code, and nothing is written.

``search`` reads the same two records and makes the same checks as ``walk``, but runs only
the states it needs: state 0 and the last state, checked against the two records, and then
the states that halve the history for a target into the new folder ``--output``. The target
is every coordinate, or the quantities ``--quantity NAME`` (repeatable) names in the periods
``--periods FIRST-LAST`` (inclusive, counted from the valuation date); a list that names every
quantity, without periods, is every coordinate. It writes ``search.result.json``: the contributions per
revision and quantity, with the signature row of each quantity it contributes to when there is no
target, the intervals judged, its runs, and the runs saved against a walk.
With ``--walk FOLDER``, a walk folder of the same two records, it copies the walk into
``walk/`` and names the contributions it missed. A search does not see contributions that
cancel within one interval. A walk that does not attribute every revision or does not fit the
search is refused with ``walk_not_attributed`` or ``walk_mismatch``, also a walk folder one of whose
states names a target, and nothing is written;
an unknown quantity or an empty period range is a usage error. ``--reuse-walk`` (with ``--walk``
only) takes every state the search needs from the copied walk instead of running it, with the
same findings; a reused state is no run, and the result and the run record name the switch.
``--target-only`` (only with a narrowed target: ``--quantity`` for a proper subset of the
quantities, or ``--periods``) runs every inner state the search runs
itself on the target alone, without the model checks; state 0 and the last state stay full runs.
The comparison kept for a contribution is then on the target only: a full state, an end or a
reused walk state, is compared through its target view ``<state>.target/``, a derived response
and export that is no run. The result and the run record name the switch.

``run``, ``replay``, ``regression``, ``walk``, and ``search`` project the model points of each
state in ``--workers N`` worker processes, else as many as ``DELTARECON_WORKERS`` names, else
one per processor; ``N`` and the variable must be whole numbers of at least 1. Each worker
computes with single-threaded BLAS. The count changes no byte of any document and is not
recorded. ``request`` and ``derive`` project no point and do not
read the variable.

``quickstart`` is the guided quick start: it runs ``request``, ``run``, ``regression``, ``derive``
and ``search`` of the quick start, without ``replay``, on the same two revisions in the new folder
``runs/quickstart-<UTC timestamp>/`` below the working directory: it changes into that folder and
back when it ends, and writes ``release-n/``, ``regression/`` (the run of N+1 in ``regression/run/``),
``changes.json`` and ``search/`` there. In four steps, the first ``request`` and ``run``, it explains
each step, shows its commands as they run from that folder, with every path relative to it, waits for
Enter (not with ``--no-pause``), and summarises the outcome from the files the step wrote. A
command gets ``--repositories``, with the clone folder relative to the demo folder, only when the
demo is given ``--repositories`` or ``DELTARECON_REPOSITORIES`` names a relative folder; otherwise
the reference model of each command finds the clone itself. The search uses the tolerance profile
``tolerance-bruttobeitrag.json``: the nearest ``profiles/tolerance-bruttobeitrag.json`` in the
working directory or one of its parents, else the wheel's copy when installed, else ``profiles/`` of
the checkout; the regression compares exactly.
``--lang de|en`` chooses the language; without it the first non-empty one of ``LC_ALL``,
``LC_MESSAGES`` and ``LANG`` decides, else the locale of the system: German for a value that starts
with ``de`` or ``German``, else English. It exits with 0 when every step has its expected status,
1 when one has another (the demo prints the output of that step and stops), 2 when the folder
exists already, and 130 when it is interrupted.

``request``, ``run``, ``replay``, ``regression``, ``derive``, ``walk``, and ``search`` load the
engine class ``--engine MODULE:CLASS`` names, else the one the environment variable
``DELTARECON_ENGINE`` names, else ``degelmann.deltarecon.engines.reference_model:ReferenceModel``,
the reference model. ``--engine-path DIR``, else the folder ``DELTARECON_ENGINE_PATH`` names, is
put on the import path before the class is loaded; the variable is read only when no ``--engine``
is given, so ``--engine`` alone decides the engine. An option wins over its variable, and an empty
variable counts as unset. The class is called with the worker count alone: with no argument when
the command is given no ``--workers``, so the engine takes its count from the environment itself,
with ``N`` for ``--workers N``, and with 1 for ``request`` and ``derive``. A selection that is not
of the form ``MODULE:CLASS`` with an absolute module name, a module that is not found or whose
import raises ``ImportError``, an attribute the module does not hold or that is not a class, a
protocol or abstract class, a class that cannot be called with the worker count, and an engine path
that is not a folder are usage errors. ``compare`` and ``quickstart`` take no such option, and
``compare`` loads no engine. ``quickstart`` always computes with the reference model: it runs each
command with ``--engine`` and the reference model, which it does not show. ``replay``,
``regression``, ``walk``, and ``search`` refuse, before anything runs, a record whose response names
another domain reference than the engine declares for its stage with ``domain_reference_mismatch``,
and a record written before contract version 3.2, whose response names no domain reference, of a
stage other than ``liability_cashflow`` with ``unsupported_stage``. ``compare`` takes the stage, the
domain reference, and the quantities from the two responses and checks that they agree.
``regression`` asks the engine for the input revision of the recorded release identity, then
describes the release of ``--revision`` with its engine options and that input revision.

``compare`` takes its tolerance profile from the request. ``replay``, ``regression``,
``walk``, and ``search`` compare exactly unless ``--tolerance FILE`` names a tolerance profile: a JSON file in the
form of the ``tolerance`` member of a compare request. There is no default profile.

No command overwrites an existing file, and none writes into the clone or uses the network.
``--repositories DIR`` names the folder that holds what the engine restores a release from; without
it the engine looks the folder up itself (``Engine.repositories_folder``). The reference model reads
the clone from ``delib-history`` in the folder ``--repositories DIR`` names, else in the
folder the environment variable ``DELTARECON_REPOSITORIES`` names, else in the nearest folder
``repositories/`` that holds ``delib-history``, in the working directory or one of its parents, else
in ``repositories/`` in the working directory, where a missing clone is reported. A relative folder is taken from the working
directory. The run folders are
where ``--output`` or the path of a request or record names them, relative to the working
directory; neither the option nor the variable moves them.

Exit status: 0 for a succeeded run, a reproduced replay, a comparison or a regression run
without deviation, a written request, a written manifest, or a walk that attributes every
revision, also with findings of intermediate states, or a search whose two ends ran and are
reproduced, also with missed contributions; 1 for a failed or rejected
run or one that ends with an error, a replay that is not reproduced or is rejected, a
comparison or a regression run that
shows a deviation or a coverage difference, is incompatible, or is rejected, a
manifest that cannot be derived, a walk that is refused, stops, or leaves a revision
unattributed because state 0 or the last state does not run or is not reproduced, a
search that is refused or stops, a request of a stage the engine does not declare, and a
request or regression whose revision, release, or clone the repositories do not hold; 2
when the command cannot start, for example because an output exists already, an engine
option is not taken, a request names no ``--stage`` and the engine declares several stages,
or the history of the clone is cut off.
"""
from __future__ import annotations

import argparse
import inspect
import os
import sys
from pathlib import Path

from . import quickstart
from .documents import Rejection
from .compare import CompareResult, compare
from .derive import derive
from .engine_selection import DEFAULT_ENGINE, ENGINE_PATH_VARIABLE, ENGINE_VARIABLE, engine_class
from .search import TARGET_ONLY, search
from .walk import walk
from .regression import read_regression_input, regression
from .replay import replay
from .run import UsageError, run_request, write_request
from .signature import render_coverage, render_model_points, render_table
from .workers import WORKERS_VARIABLE, whole_number


# The ``--engine`` and ``--engine-path`` of the command ``main`` runs, ``None`` where it is not
# given; ``main`` sets them before it dispatches and resets them afterwards.
selection: tuple[str | None, str | None] = (None, None)


def engine(workers: int | None = None):
    """The engine the command selects: its class called with the worker count, or with no
    argument when the command is given none."""
    cls = engine_class(*selection)
    arguments = () if workers is None else (workers,)
    try:
        inspect.signature(cls).bind(*arguments)
    except TypeError:
        raise UsageError(f"the engine class {cls.__qualname__} cannot be called with "
                         f"{'no argument' if workers is None else 'the worker count'}; an engine class "
                         "takes the worker count as its one optional argument") from None
    except ValueError:  # no signature to inspect, as for some built-in classes; the call decides
        pass
    return cls(*arguments)


def state_engine(args):
    """The engine of a command that runs states. Without ``--workers`` the factory is called
    without an argument, and the engine takes its count from the environment."""
    return engine() if args.workers is None else engine(args.workers)


def worker_option(text: str) -> int:
    value = whole_number(text)
    if value is None:
        raise argparse.ArgumentTypeError(f"must be a whole number of at least 1, not {text!r}")
    return value


def print_diagnostic(diagnostic: dict) -> None:
    print(f"diagnostic: {diagnostic['code']}: {diagnostic['message']}")
    for member, label in (("model_point_ids", "model points"), ("change_ids", "changes")):
        if diagnostic.get(member):
            print(f"  {label}: {', '.join(diagnostic[member])}")


def engine_option(text: str) -> tuple[str, str]:
    """One ``--engine-option key=value``: the pair of a non-empty key and its value."""
    key, equals, value = text.partition("=")
    if not equals or not key:
        raise argparse.ArgumentTypeError(f"must be of the form key=value with a non-empty key, not {text!r}")
    return key, value


def engine_options(pairs) -> dict[str, str]:
    """The engine options of a command by key, without loading an engine. Which keys and values
    an engine takes is the engine's matter; a key given twice is a usage error."""
    options: dict[str, str] = {}
    for key, value in pairs or ():
        if key in options:
            raise UsageError(f"the engine option {key!r} is given twice")
        options[key] = value
    return options


def command_request(args) -> int:
    options = engine_options(args.engine_option)
    # One worker: a request projects no point, so DELTARECON_WORKERS does not concern it.
    selected = engine(1)
    repositories = selected.repositories_folder(args.repositories)
    try:  # the request names a release only if a run would accept it; nothing is written otherwise
        output = write_request(selected, Path(args.output), stage=args.stage, label=args.label,
                               revision=args.revision, options=options, run_id=args.run_id,
                               subset=args.subset, enable=args.enable,
                               manifest=Path(args.manifest) if args.manifest else None,
                               repositories=repositories)
    except Rejection as rejection:
        print("request: rejected")
        print_diagnostic(rejection.diagnostic())
        return 1
    print(f"request: {os.path.relpath(output)}")
    return 0


def command_run(args) -> int:
    result = run_request(Path(args.request), state_engine(args), args.repositories)
    print(f"outcome: {result.outcome}")
    for diagnostic in result.response.get("diagnostics", []):
        print_diagnostic(diagnostic)
    for failure in result.response.get("failed_model_points", []):
        print(f"failed: model point {failure['model_point_id']}: {failure['message']}")
    if result.outcome == "succeeded":
        print(f"model points: {len(result.response['model_points'])}")
        print(f"export rows: {result.response['export']['data_rows']}")
        print(f"export sha256: {result.response['export']['artifact']['sha256']}")
    for label, path in (("response", result.response_path), ("export", result.export_path),
                        ("run record", result.record_path)):
        if path is not None:
            print(f"{label}: {os.path.relpath(path)}")
    return 0 if result.outcome == "succeeded" else 1


def command_replay(args) -> int:
    try:
        result = replay(Path(args.run_record), state_engine(args), args.repositories, args.tolerance)
    except Rejection as rejection:
        print("replay: rejected")
        print_diagnostic(rejection.diagnostic())
        return 1
    compared = result.compare_result
    print(f"replay: {result.outcome}")
    if compared is None:  # a recorded run with the outcome error: its response is compared byte for byte
        same = "the same" if result.outcome == "reproduced_exactly" else "another"
        print(f"the recorded run has ended with an error; the repeated run writes {same} response")
        print(f"response: {os.path.relpath(result.response_path)}")
        print(f"replay record: {os.path.relpath(result.record_path)}")
        return 0 if result.outcome.startswith("reproduced_") else 1
    if compared["outcome"] == "compared":
        print(f"deviating coordinates: {len(result.comparison.deviations)}")
        if compared["added"] or compared["removed"]:
            print(f"coverage: {len(compared['added'])} added and {len(compared['removed'])} removed "
                  "period ranges")
    else:
        print(f"comparison: {compared['outcome']}")
        for diagnostic in compared["diagnostics"]:
            print_diagnostic(diagnostic)
    print(f"compare request: {os.path.relpath(result.compare_request_path)}")
    print(f"compare result: {os.path.relpath(result.compare_result_path)}")
    if result.comparison.deviations_path is not None:
        print(f"deviation file: {os.path.relpath(result.comparison.deviations_path)}")
    print(f"replay record: {os.path.relpath(result.record_path)}")
    return 0 if result.outcome.startswith("reproduced_") else 1


def print_comparison(command: str, compared: CompareResult) -> int:
    """Print what a comparison found. Return the exit status: 0 only for "no deviation".

    The signature table comes before the line per deviating model point: the list grows
    with the portfolio, the table does not.
    """
    result = compared.result
    listed: list[str] = []
    if compared.no_deviation:
        print(f"{command}: no deviation above tolerance")
    elif result["outcome"] == "compared":
        print(f"{command}: {len(compared.deviations)} deviating coordinates in "
              f"{len(result['deviating_model_points'])} model points, {len(result['added'])} added and "
              f"{len(result['removed'])} removed period ranges")
        print(f"stage: {result['stage']}")
        listed = render_model_points(result, compared.deviations) + render_coverage(result)
    else:
        print(f"{command}: {result['outcome']}")
        for diagnostic in result["diagnostics"]:
            print_diagnostic(diagnostic)
    if "engine_version" in result:
        print(f"engine version: left {result['engine_version']['left']}, "
              f"right {result['engine_version']['right']}")
    if compared.table is not None:
        for line in render_table(compared.table):
            print(line)
    for line in listed:
        print(line)
    for label, path in (("compare result", compared.result_path), ("deviation file", compared.deviations_path),
                        ("signature table", compared.signature_path), ("compare record", compared.record_path)):
        if path is not None:
            print(f"{label}: {os.path.relpath(path)}")
    return 0 if compared.no_deviation else 1


def command_compare(args) -> int:
    try:
        compared = compare(Path(args.request))
    except Rejection as rejection:  # the request is not readable as a compare request
        print("compare: rejected")
        print_diagnostic(rejection.diagnostic())
        return 1
    return print_comparison("compare", compared)


def command_regression(args) -> int:
    output = Path(args.output).resolve()
    if output.exists():
        raise UsageError(f"{output} exists already; a regression run overwrites no file")
    # A key given twice is refused before the engine loads; the engine checks keys and values in describe.
    options = engine_options(args.engine_option)
    states = state_engine(args)
    repositories = states.repositories_folder(args.repositories)
    try:
        recorded = read_regression_input(Path(args.run_record), states.stages)
    except Rejection as rejection:
        print("regression: rejected")
        print_diagnostic(rejection.diagnostic())
        return 1
    try:
        # The newer revision is the state; the input data stays that of the recorded run. The
        # recorded run may come from another engine version or path; the new run uses this
        # engine with the engine options of the command line. Nothing is written.
        input_revision = states.input_revision(recorded.record["releases"][0])
        described = states.describe(recorded.request["stage"], args.label, args.revision, options,
                                    repositories, input_revision)
    except Rejection as rejection:  # nothing is written
        print("regression: rejected")
        print_diagnostic(rejection.diagnostic())
        return 1
    release = {"label": args.label, "references": described["references"]}
    result = regression(recorded, release, output, states, repositories, args.tolerance)
    if result.comparison is None:
        print(f"regression: the run of the revision has the outcome {result.run.outcome}; nothing is compared")
        for diagnostic in result.run.response.get("diagnostics", []):
            print_diagnostic(diagnostic)
        for failure in result.run.response.get("failed_model_points", []):
            print(f"failed: model point {failure['model_point_id']}: {failure['message']}")
        print(f"response: {os.path.relpath(result.run.response_path)}")
        return 1
    return print_comparison("regression", result.comparison)


def command_derive(args) -> int:
    try:
        # One worker: a derivation projects no point, so DELTARECON_WORKERS does not concern it.
        result = derive(Path(args.older_record), Path(args.newer_record), Path(args.output), engine(1),
                        args.repositories)
    except Rejection as rejection:  # nothing is written
        print("derive: rejected")
        print_diagnostic(rejection.diagnostic())
        return 1
    history = result.manifest["history"]
    print(f"derive: {len(result.manifest['changes'])} changes from {history['from']} to {history['to']}")
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    for change in result.manifest["changes"]:
        line = (f"  {change['id']} [{', '.join(change['class']) or 'no class'}] "
                f"{change['description'].splitlines()[0]}")
        # The manifest is written; a character stdout cannot encode must not end the command.
        print(line.encode(encoding, "replace").decode(encoding, "replace"))
    kinds = [entry["kind"] for entry in history["remainder"]]
    print(f"remainder: {', '.join(kinds) if kinds else 'none'}")
    print(f"manifest: {os.path.relpath(result.manifest_path)}")
    return 0


def _number(value) -> str:
    return "not finite" if value is None else f"{value:.12g}"


def command_walk(args) -> int:
    try:
        done = walk(Path(args.older_record), Path(args.newer_record), Path(args.output), state_engine(args),
                    args.repositories, args.tolerance)
    except Rejection as rejection:  # refused before the first run; nothing is written
        print("walk: rejected")
        print_diagnostic(rejection.diagnostic())
        return 1
    result = done.result
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"

    def say(line: str) -> None:  # the result is written; a character stdout cannot encode must not end it
        print(line.encode(encoding, "replace").decode(encoding, "replace"))

    say(f"walk: {'every revision attributed' if done.attributed else 'not every revision attributed'}; "
        f"{len(result['states'])} states run, {len(result['steps'])} steps")
    ends = result["ends"]
    say(f"state {ends['zero']['state']} against the older record: {ends['zero']['outcome'].replace('_', ' ')}")
    say(f"state {ends['n']['state']} against the newer record: {ends['n']['outcome'].replace('_', ' ')}")
    for held in result["held"]:
        say(f"held: {held['kind']}; the effect on it of {len(held['not_shown'])} revisions is not shown")
    kinds = [entry["kind"] for entry in result["remainder"]]
    say(f"remainder: {', '.join(kinds) if kinds else 'none'}")
    for step in result["steps"]:
        say(f"step {step['from_state']} to {step['to_state']}: {', '.join(step['revisions'])}")
        contributing = [c for c in step["contributions"] if c["contributes"]]
        if not contributing:
            say("  no contribution")
        for contribution in contributing:
            say(f"  {contribution['quantity']}: sum {_number(contribution.get('sum'))}, "
                f"absolute sum {_number(contribution.get('absolute_sum'))}")
    for finding in result["findings"]:
        where = f" (state {finding['state']})" if "state" in finding else ""
        say(f"finding: {finding['code']}{where}: {finding['message']}")
        if "diagnostic" in finding:
            say(f"  diagnostic: {finding['diagnostic']['code']}: {finding['diagnostic']['message']}")
    if result["unattributed"]:
        say(f"unattributed: {', '.join(result['unattributed'])}")
    say(f"walk result: {os.path.relpath(done.result_path)}")
    return 0 if done.attributed else 1


def command_search(args) -> int:
    # The switches are checked here under their flags; search keeps its own checks for library callers.
    if args.reuse_walk and not args.walk:
        raise UsageError("the switch --reuse-walk takes the states from a walk folder and needs --walk")
    if args.target_only and not args.quantity and args.periods is None:
        raise UsageError("the switch --target-only runs the inner states on the target and needs a target "
                         "narrowed by --quantity or --periods")
    try:
        done = search(Path(args.older_record), Path(args.newer_record), Path(args.output), state_engine(args),
                      args.repositories, args.tolerance, args.quantity, args.periods,
                      Path(args.walk) if args.walk else None, args.reuse_walk, args.target_only)
    except Rejection as rejection:  # refused before the first run; nothing is written
        print("search: rejected")
        print_diagnostic(rejection.diagnostic())
        return 1
    result = done.result
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"

    def say(line: str) -> None:  # the result is written; a character stdout cannot encode must not end it
        print(line.encode(encoding, "replace").decode(encoding, "replace"))

    runs = result["runs"]
    reused = f"{runs['reused']} reused from the walk, " if "reused" in runs else ""
    say(f"search: {'searched' if done.searched else 'stopped'}; {runs['search']} states run, {reused}"
        f"{runs['walk']} for a walk, {runs['saved']} saved")
    ends = result["ends"]
    say(f"state {ends['zero']['state']} against the older record: {ends['zero']['outcome'].replace('_', ' ')}")
    say(f"state {ends['n']['state']} against the newer record: {ends['n']['outcome'].replace('_', ' ')}")
    target = result["target"]
    periods = target.get("periods")
    say(f"target: {', '.join(target['quantities'])}"
        + (f"; periods {periods['first']} to {periods['last']}" if periods else "; every period"))
    if TARGET_ONLY in result.get("switches", []):
        ends_run = {ends["zero"]["state"], ends["n"]["state"]}
        inner = [entry for entry in result["states"] if not entry.get("reused") and entry["state"] not in ends_run]
        if inner:
            say("inner states: run on the target only, without the model checks")
        elif "reused" in runs:
            say("inner states: none run on the target; every inner state was taken from the walk")
        else:
            say("inner states: none run on the target")
    for held in result["held"]:
        say(f"held: {held['kind']}; the effect on it of {len(held['not_shown'])} revisions is not shown")
    say(f"intervals judged: {len(result['intervals'])}")
    for entry in result["contributions"]:
        say(f"contribution from state {entry['from_state']} to {entry['to_state']}: {', '.join(entry['revisions'])}")
        for contribution in entry["contributions"]:
            if contribution["contributes"]:
                say(f"  {contribution['quantity']}: sum {_number(contribution.get('sum'))}, "
                    f"absolute sum {_number(contribution.get('absolute_sum'))}")
    if not result["contributions"]:
        say("no contribution found")
    for finding in result["findings"]:
        where = f" (state {finding['state']})" if "state" in finding else ""
        say(f"finding: {finding['code']}{where}: {finding['message']}")
        if "diagnostic" in finding:
            say(f"  diagnostic: {finding['diagnostic']['code']}: {finding['diagnostic']['message']}")
    if "missed" in result:
        say(f"checked against the walk {result['walk']['walk_id']}: {len(result['missed'])} missed")
        for entry in result["missed"]:
            say(f"  missed: {entry['revision']} {entry['quantity']}")
    say(f"search result: {os.path.relpath(done.result_path)}")
    return 0 if done.searched else 1


def command_quickstart(args) -> int:
    return quickstart.quickstart(args.lang or quickstart.system_language(), not args.no_pause, args.repositories,
                                 command=main)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="deltarecon", description="Run and compare releases through the stage contracts.")
    commands = parser.add_subparsers(dest="command", required=True)

    request = commands.add_parser("request", help="write a run request with the complete release identity")
    request.add_argument("--revision", required=True, metavar="REVISION",
                         help="the release, a name the engine reads; for the reference model a commit of the "
                              "clone of its repository, named by a full or abbreviated hash, a branch, a tag, "
                              "or HEAD (no suffix such as HEAD~1)")
    request.add_argument("--stage", help="the stage of the request, one the engine declares "
                                         "(default: the engine's only stage)")
    request.add_argument("--label", required=True, help="label of the release, for example N")
    request.add_argument("--run-id", required=True)
    request.add_argument("--output", required=True, help="path of the request to write")
    request.add_argument("--subset", nargs="+", default=[], metavar="MODEL_POINT_ID",
                         help="model point ids to run; without it the run is full")
    request.add_argument("--enable", nargs="+", default=[], metavar="CHANGE_ID",
                         help="ids of the changes to enable")
    request.add_argument("--manifest", help="change manifest, in the folder of the request or below it")
    request.set_defaults(handler=command_request)

    run = commands.add_parser("run", help="run a request and write response, export, and run record")
    run.add_argument("request")
    run.set_defaults(handler=command_run)

    again = commands.add_parser("replay", help="repeat a recorded run and state whether it is reproduced")
    again.add_argument("run_record")
    again.set_defaults(handler=command_replay)

    comparison = commands.add_parser("compare", help="compare the two runs a compare request names")
    comparison.add_argument("request")
    comparison.set_defaults(handler=command_compare)

    regress = commands.add_parser("regression", help="check a recorded run against a newer revision")
    regress.add_argument("run_record", help="the record of a succeeded full run without enabled changes")
    regress.add_argument("--revision", required=True, metavar="REVISION",
                         help="the newer release, a name the engine reads; for the reference model a commit "
                              "of the clone of its repository, named by a full or abbreviated hash, a branch, "
                              "a tag, or HEAD (no suffix such as HEAD~1)")
    regress.add_argument("--output", required=True, help="the folder to write; it must not exist")
    regress.add_argument("--label", default="regression",
                         help="label of the release that is run (default: regression)")
    regress.set_defaults(handler=command_regression)

    history = commands.add_parser("derive", help="derive the change manifest of the history between two "
                                                 "recorded runs")
    history.add_argument("older_record", help="the record of a succeeded full run without enabled changes")
    history.add_argument("newer_record", help="the record of such a run of a newer revision")
    history.add_argument("--output", required=True,
                         help="path of the manifest to write; its folder must exist")
    history.set_defaults(handler=command_derive)

    stepper = commands.add_parser("walk", help="run every state between two recorded runs and attribute "
                                               "the deviation to revisions")
    stepper.add_argument("older_record", help="the record of a succeeded full run without enabled changes")
    stepper.add_argument("newer_record", help="the record of such a run of a newer revision, on the same selection")
    stepper.add_argument("--output", required=True, help="the folder to write; it must not exist")
    stepper.set_defaults(handler=command_walk)

    halver = commands.add_parser("search", help="halve the history between two recorded runs for a target "
                                               "and check it against a walk")
    halver.add_argument("older_record", help="the record of a succeeded full run without enabled changes")
    halver.add_argument("newer_record", help="the record of such a run of a newer revision, on the same selection")
    halver.add_argument("--output", required=True, help="the folder to write; it must not exist")
    halver.add_argument("--quantity", action="append", default=[], metavar="NAME",
                        help="a quantity of the target; repeatable; without it every quantity")
    halver.add_argument("--periods", metavar="FIRST-LAST",
                        help="the periods of the target, inclusive, counted from the valuation date; "
                             "without it every period")
    halver.add_argument("--walk", metavar="FOLDER",
                        help="a walk folder of the same two records to check the search against")
    halver.add_argument("--reuse-walk", action="store_true",
                        help="take every state from the walk folder instead of running it; needs --walk")
    halver.add_argument("--target-only", action="store_true",
                        help="run every inner state on the target alone, without the model checks; "
                             "needs a narrowed target: --quantity for a proper subset of the quantities, or --periods")
    halver.set_defaults(handler=command_search)

    guided = commands.add_parser("quickstart", help="the guided quick start: run and explain the quick start "
                                                    "step by step")
    guided.add_argument("--no-pause", action="store_true", help="do not wait for Enter before each step")
    guided.add_argument("--lang", choices=("de", "en"),
                        help="the language of the texts (default: the language of the system)")
    guided.set_defaults(handler=command_quickstart)

    for command in (again, regress, stepper, halver):
        command.add_argument("--tolerance", metavar="FILE",
                             help="tolerance profile, JSON in the form of the tolerance member of a "
                                  "compare request; without it the comparison is exact")

    for command in (run, again, regress, stepper, halver):
        command.add_argument("--workers", type=worker_option, metavar="N",
                             help="the number of worker processes that project the model points of a "
                                  f"state (default: {WORKERS_VARIABLE}, else one per processor)")

    for command in (request, run, again, regress, history, stepper, halver):
        command.add_argument("--engine", metavar="MODULE:CLASS",
                             help="the engine class to load (default: the one "
                                  f"{ENGINE_VARIABLE} names, else the reference model)")
        command.add_argument("--engine-path", metavar="DIR",
                             help="a folder to put on the import path before the engine is loaded "
                                  f"(default: the folder {ENGINE_PATH_VARIABLE} names, read only without --engine)")

    for command in (request, regress):
        # Parsed into pairs here; the engine checks keys and values, so parsing loads no engine.
        command.add_argument("--engine-option", type=engine_option, action="append", default=[],
                             metavar="KEY=VALUE",
                             help="an option of the engine; repeatable, each key once. The reference model "
                                  "takes path=export|modelx, the computation path the engine version of the "
                                  "release names: export, through the modelx export of the model (default), "
                                  "or modelx, through modelx itself; a run never falls back to the other")

    for command in (request, run, again, regress, history, stepper, halver, guided):
        command.add_argument("--repositories", metavar="DIR",
                             help="folder that holds what the engine restores a release from; for the "
                                  "reference model, the folder that holds the clone of the reference model "
                                  "repository (default: the folder DELTARECON_REPOSITORIES names, else the nearest "
                                  "repositories/ that holds the clone, in the working directory or one of its "
                                  "parents)")

    args = parser.parse_args(argv)
    global selection
    previous, selection = selection, (getattr(args, "engine", None), getattr(args, "engine_path", None))
    try:
        return args.handler(args)
    except (UsageError, FileExistsError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    finally:
        selection = previous


if __name__ == "__main__":
    sys.exit(main())
