# Localise contract

Version 1 of the stage contracts, see [README.md](README.md). The localise
contract fixes procedures of the tool that are built on the run, the changes,
and the compare contracts: the walk, which attributes the deviation between two
recorded results to the revisions between them, and its document, the walk
result; and the search, which finds the contributing revisions with fewer runs by
halving the history, and its document, the search result.
It is no stage contract. No engine implements it; a walk and a search call an
engine only through the run contract. The walk is the reference result; a search
never replaces it.

Schema: [schemas/localise.schema.json](schemas/localise.schema.json).

## Walk

A walk starts from two recorded results, the older and the newer one: the run
records of two runs that succeeded without an enabled change. It derives the
change manifest of the history between the revisions they name, see
[changes.md](changes.md#derived-manifest), and runs every state of that history.

- State 0 is the older release. State k is the state after the k-th change of
  the manifest, the revision k. State n, after the last revision, is the newer
  release. When both results name one revision, n is 0.
- Every state is one run of the run contract, with its own request, response,
  export, and run record. The request of state k names the release identity of
  the older result as the present engine records it, with the label of the older
  result, so that the base release of the manifest is the release of the request.
  It enables the first k changes of the manifest, a prefix, see
  [changes.md](changes.md#revision-profile), and selects what both results
  select.
- The states run one after the other, in history order.

### Held and moving kinds

A revision determines some kinds of release reference, see `history.determines`
of the manifest. The walk treats each of them in one of two ways:

- A kind the engine can hold, and whose references are present and equal in both
  recorded results, is **held**: every state takes it from the older release.
  Both results were calculated on it, so the walk calculates every state on it as
  well, even when the history versions it. The request of every state after state
  0 names the held kinds in `changes.hold`, see
  [run.md](run.md#run-request).
- Every other determined kind **moves** with the states: state k takes it from
  revision k.

The walk does not show the effect of a revision on a held input. The walk result
names every held kind with the revisions of the classes that carry it, see
[Walk result](#walk-result).

Kinds that no revision determines are not attributed. Where they differ between
the two results they are named as the remainder, as in the derived manifest. An
engine version that differs is such a kind: every state runs on the present
engine, and the walk goes on.

### Before the first run

The walk checks, in this order, and refuses with the diagnostic named here.
Nothing runs and nothing is written:

1. Both records are records of runs that succeeded without an enabled change, and
   pass the reader rules of [run.md](run.md#run-record). A record that does not is
   a fault of the input, not a diagnostic.
2. Both records name one stage. Otherwise `stage_mismatch`.
3. Both records hold the same selection: both full, or both the same set of
   model point ids. Otherwise `selection_mismatch`.
4. The manifest can be derived. Otherwise the diagnostic of the derivation, such
   as `unrelated_revisions` or `unknown_reference`.
5. For every kind that moves, the engine's identity of the state after the older
   revision names the same references of that kind as the older record, and its
   identity of the state after the newer revision, with the held kinds taken from
   the older release, the same as the newer record. Otherwise
   `reference_mismatch`. The walk compares references for equality only; what a
   reference names is the engine's matter.
6. The engine resolves the release identity of the requests, see rule 4 of
   [README.md](README.md#release-identity).

### Ends

State 0 must reproduce the older and state n the newer recorded result. The
recorded result is the left side, the state the right side, and the comparison
follows [compare.md](compare.md) under the tolerance profile of the walk; without
one it is exact. An end is reproduced when the comparison reports no deviation:
the outcome is `compared`, no coordinate deviates, and no coordinate is added or
removed.

- State 0 that does not run, or that does not reproduce the older result, stops
  the walk: no further state runs.
- State n that does not run, or that does not reproduce the newer result, ends
  the walk with a finding.
- When n is 0, state 0 is checked against both results.

### Steps

A step leads from one state that ran to the next state that ran, and carries the
revisions in between. Normally step k leads from state k-1 to state k and carries
revision k.

A state that ends `failed`, `rejected`, or `error` is a finding. The next state
that runs closes the step: a step from state k-1 to state k+1 carries revisions k
and k+1 together, and their contributions are one. When the last state does not
run, the revisions after the last state that ran are named as unattributed.

Each step compares its two states, the earlier one as the left side, under the
tolerance profile of the walk.

## Contribution

Per step and quantity, the walk states:

| Member | Meaning |
|---|---|
| `contributes` | Whether the step contributes to the quantity: a coordinate of the quantity deviates under the tolerance rule, or a coordinate is added or removed. It is true for every quantity of a step whose comparison has no outcome `compared`. |
| `sum` | The signed sum of `right - left` over every coordinate of the quantity in the two exports, a coordinate that one export lacks counted as 0. |
| `absolute_sum` | The sum of the absolute values of the same differences. It shows effects that cancel within the step, and does not add up across steps. |
| `signature` | The row of the quantity in the signature table of the step, see [compare.md](compare.md#signature-table), when the step contributes and the row exists. |

- Both sums are computed exactly from the values of the two exports, as decimal
  values of binary64 numbers, and written once, rounded to the nearest binary64
  value. A tolerance does not change them: they cover every coordinate.
- A sum that does not fit a finite binary64 value is not written, and the finding
  `non_finite_difference` names the step and the quantity.
- A step that does not contribute to any quantity has no comparison of its own in
  the walk result. A step that contributes references its compare result and, for
  the outcome `compared`, its deviation file.

### Attribution order

A contribution belongs to the revision in history order. A revision whose effect a
later revision overrides keeps its own non-zero step, and the later revision
carries the step back. Where two revisions interact, the interaction lands on the
later one. Another order could attribute differently; the walk does not try one.

### Additivity

Because each state is compared with the state before it, the exact signed sums
of a quantity over all steps add up to the exact difference between state n and
state 0. When both ends are reproduced exactly, that is the deviation between the
two recorded results: the signed sums add up to it exactly as computed, and up to
the rounding of each written sum as written. With a tolerance profile, state 0 and
state n may differ from the recorded results within the tolerances, and the sums
add up to the difference of the two states.

### Stage step

Localising starts with the stage, then the revisions within it. Version 1 defines
one stage, so the stage step is trivial: the walk runs in the stage both records
name, and `stage` of the walk result names it.

## Findings

| Code | Raised when | Then |
|---|---|---|
| `state_zero_not_reproduced` | State 0 does not reproduce the older recorded result. | The walk stops. The finding references the comparison. |
| `state_n_not_reproduced` | State n does not reproduce the newer recorded result. | The finding references the comparison. |
| `state_did_not_run` | A state ends `failed`, `rejected`, or `error`. | The finding holds the diagnostic of the run: its first diagnostic, or `model_point_failed` with the failing model points. Its revision is carried by the next state that runs. State 0 stops the walk. |
| `step_not_compared` | The comparison of a step has no outcome `compared`, for example `non_finite_difference`. | The sums are kept, every quantity contributes, and there is no signature row. The finding holds the diagnostic of the comparison and references it. |
| `non_finite_difference` | A sum does not fit a finite binary64 value. | The sum is not written. |

A walk **attributes every revision** when state 0 and state n ran and are
reproduced. Findings of intermediate states do not change that. Otherwise the
revisions it could not attribute are named in `unattributed`; when state 0 does
not run or is not reproduced, these are all of them.

## Walk result

```json
{
  "document": "walk_result",
  "contract_version": "1.0",
  "stage": "liability_cashflow",
  "walk_id": "walk-run-n-full-run-n1-full",
  "manifest": { "path": "changes.json", "sha256": "…" },
  "older": { "run_id": "run-n-full", "release_label": "N" },
  "newer": { "run_id": "run-n1-full", "release_label": "N+1" },
  "tolerance": { "per_quantity": {} },
  "held": [],
  "remainder": [],
  "ends": { "zero": { "state": 0, "outcome": "reproduced" }, "n": { "state": 4, "outcome": "reproduced" } },
  "states": [ { "state": 0, "run_id": "walk-run-n-full-run-n1-full-state-0", "outcome": "succeeded", "response": { "path": "state-00/response.json", "sha256": "…" }, "export": { "path": "state-00/results.csv", "sha256": "…" } } ],
  "steps": [ { "from_state": 0, "to_state": 1, "revisions": ["…"], "contributions": [ { "quantity": "Netto-Cashflow", "contributes": false, "sum": 0, "absolute_sum": 0 } ] } ],
  "unattributed": [],
  "totals": [ { "quantity": "Netto-Cashflow", "sum": -12.5 } ],
  "findings": []
}
```

The block is shortened: `"…"` stands for hashes and revisions, and the lists for
their full content. [examples/walk/](examples/walk/) holds the walk result of a walk over four revisions with the documents it references: the derived manifest, the response and export of every state with its copy of the manifest, and the compare results and deviation files of the steps that contribute. The requests, the run records, the copies of the recorded runs, and the run record of the walk are left out.

| Member | Meaning |
|---|---|
| `walk_id` | `walk-<older run id>-<newer run id>`, with the run ids of the two recorded requests. |
| `manifest` | The derived manifest, by artifact reference. |
| `older`, `newer` | The run id and the release label of each recorded result. |
| `tolerance` | The tolerance profile of the walk, in the form of [compare.md](compare.md#compare-request). It is empty without one. |
| `held` | Per held kind: `kind`, the `classes` of the paths that carry it as the engine declares them, and `not_shown`, the revisions of these classes, whose effect on that input the walk does not show. |
| `remainder` | The remainder of the manifest: the kinds no revision determines that differ between the two results. |
| `ends` | `zero` and `n`: the state checked, and `reproduced`, `not_reproduced` with the comparison, or `not_run`. |
| `states` | Every state that was requested: its number, its revision (absent for state 0), its run id, the outcome of its run, its response, and for `succeeded` its export. |
| `steps` | Every step: `from_state`, `to_state`, the `revisions` it carries, the comparison when it contributes, and one contribution per quantity. |
| `unattributed` | The revisions the walk could not attribute. |
| `totals` | Per quantity the signed sum of `newer - older` over every coordinate of the two recorded exports, computed and written as a contribution. |
| `findings` | The findings, see [Findings](#findings). Each has a `code` and a `message`, and where they apply the `state`, the `revisions`, the `quantity`, the `diagnostic`, and the comparison (`compare`). |

The walk result references the manifest, the responses and exports of the states,
and the compare results with their deviation files. It references no run record,
so the same two records and the same history give the same walk result, byte for
byte, for a writer that writes the same value in the same way.

Ids: a state run has the run id `<walk_id>-state-<k>`. A step is numbered by the
state it ends at; its comparison has the compare id `<walk_id>-step-<k>`. The
checks of the ends have `<walk_id>-state-<k>-check-older` and
`<walk_id>-state-<k>-check-newer`.

Orders:

- `states` and `steps` in history order; `revisions` of a step in history order.
- `contributions` and `totals` in the quantity order of the older recorded
  response, which is that of the domain reference.
- `held` by kind, by Unicode code point; `classes` in the order `data`,
  `parameter`, `code`; `not_shown` and `unattributed` in history order.
- `remainder` as in the derived manifest.
- `findings` in the order the walk meets them: state 0 and its check, then state
  by state with its step, then the check of state n, then the totals.

Schema assertions: every member above is present; a state has an export exactly
when it succeeded, and a revision exactly when it is not state 0; an end has a
comparison exactly when it is not reproduced; a step carries at least one
revision, holds at least one contribution, and has a comparison exactly when one
of its contributions contributes.

## Run record of a walk

A walk writes a run record with the procedure type `walk`, see
[run.md](run.md#run-record). Its outcome is `attributed` when the walk attributes
every revision and `not_attributed` otherwise. A walk that is refused before the
first run writes no record. It lists the two recorded run records, as copied for
the walk, and the tolerance file when there is one, as inputs; the manifest, the
walk result, and every compare result the walk kept, as outputs; and the release
identities of the older and the newer result, in this order.

## Search

A search starts, as the walk does, from two recorded results, and needs no walk.
It derives the manifest of the history between them and runs only some of its
states, to find the revisions that contribute to a target with fewer runs than a
walk. Its inputs and its checks before the first run are those of the walk, see
[Before the first run](#before-the-first-run): two records, an optional tolerance
profile, the same refusals, and the same held and moving kinds. Every state it
runs is a state of the walk, run in the same way, with its own request,
response, export, and run record.

Known limit: the search does not see contributions that cancel within one
interval. Two revisions whose effects on the target cancel, such as a revision
and its revert, leave the two ends of an interval equal, and the search does not
divide that interval. Only the walk sees them.

### Target

The target is the set of coordinates a search judges: quantities of the older
recorded response and an inclusive range of periods. Without a quantity it holds
every quantity; without a range every period. A search without either covers
every coordinate.

Target periods count from the valuation date, so that on `policy_month` a range
such as 0 to 59 means the first five projection years of every model point, new
business and business in force alike; on `valuation_year`, which is 1-based, the
same five projection years are 1 to 5. On a time basis whose origin is the valuation date the
target periods are the periods of the export, as they are. On `policy_month`,
whose origin is the issue date of a model point, the **projection period** of a
coordinate (model point p, period t) is t - s_p, where s_p is the first period of
p in the older recorded export, or, for a model point absent there, its first
period in the run being restricted; on `policy_month` the exported range of a
model point starts at the valuation date of the run, see
[domain/liability_cashflow.md](domain/liability_cashflow.md#time-basis). The
offsets s_p are fixed once per search and hold for every judgement and for the
check against a walk. A target with the periods 0 to 2 thus judges a model point
that starts at period 144 on its periods 144 to 146.

A quantity the older response does not declare, a range that is not
`FIRST-LAST` with integers 0 <= `FIRST` <= `LAST`, and a range in which neither
recorded export has a coordinate with a projection period inside it are faults of
the call: nothing runs and nothing is written.

Under a target, the search judges an interval on its two states **restricted to
the target**: the rows whose projection period lies in the target periods, the target quantities only, in the
quantity order of the response, and the entries of the tolerance profile for
those quantities. A failure outside the target, of a value or of its metadata,
cannot change the judgement. Without a target the judgement is that of the full
runs.

### Halving

State 0 and state n run first and are checked as the ends of a walk, see
[Ends](#ends). State 0 or state n that does not run, or that is not reproduced,
stops the search with a finding; when n is 0, state 0 is checked against both
results, and there is no interval.

The search then judges the interval from state 0 to state n for every quantity of
the target. An interval (a, b) is **judged** by comparing state a, the left side,
with state b under the tolerance profile, restricted to the target. It **differs**
for a quantity when a coordinate of the quantity deviates under the tolerance
rule or a coordinate within the target periods is added or removed, as
`contributes` of a walk step. A comparison without the outcome `compared`, for
example `non_finite_difference`, differs for every quantity it judges.

- An interval whose ends agree for a quantity is not divided further for it.
- An interval (a, b) with b - a > 1 that differs is split at m = (a + b) // 2.
  Both halves are judged for the quantities on which (a, b) differs, depth first
  in pre-order, the earlier half first. Each interval is judged once, for the
  quantities its parent passes on.
- A state runs at most once. A midpoint that does not run is replaced by the
  nearest state strictly inside the interval that runs, trying m + 1, m - 1,
  m + 2, and so on; a state that did not run stays known as such and is not
  requested again. When no inner state runs, the interval is one contribution of
  all its revisions together, as a carried step of the walk.
- An interval of one revision that differs is a contribution of that revision.
- An interval that differs for a quantity while neither of its halves differs for
  it gives the finding `interval_not_resolved` for that quantity. Nothing is
  attributed for it: each step inside is below the tolerance, and only their
  sum exceeds it.

A **contribution** of the search has the shape of a step of the walk, see
[Contribution](#contribution): the interval, the revisions it carries, its
comparison, and per quantity of the target `contributes`, the signed and the
absolute sum, written for every quantity of the target. `contributes` is true
for the quantities in `differs` of the interval: among the quantities the
interval is judged for, those its parent passes on, the ones for which its ends
differ. The sums run over the coordinates of the target only and are computed
exactly as in the walk on the restricted states. The comparison the search keeps
for a contribution is that of the two full states, as evidence; without a target
the contribution holds its signature row, under a target it holds none. A
contribution whose judging comparison has no outcome `compared` gives the finding
`step_not_compared`.

The attribution order of the walk holds: a contribution belongs to the revision
in history order, and when interacting revisions change the target together, the
interaction lands on the later one.

### Runs saved

A walk requests every state, n + 1 runs. The search reports the states it
requested, including those that did not run, and the runs it saved: n + 1 less
its own runs. The runs saved are reported with and without a walk.

### Check against a walk

A search may be given a walk folder of the same two records. It then checks
itself against the walk and names the contributions it **missed**: per revision
and quantity of the target, the walk shows that the step carrying the revision
changes a target coordinate of that quantity, above tolerance or added or
removed, and no contribution of the search names that revision for that
quantity. A carried step of the walk counts for each revision it carries. Missed
contributions are a measurement, not a failure. A search that stops, because state 0
or state n does not run or is not reproduced, judges no interval and names no missed
contribution.

The check reads the state exports of the walk folder and compares each pair of
consecutive states that ran, a step of the walk, on the target's coordinates
under the tolerance of the walk, as an interval is judged; nothing runs for it.
It always recomputes from the exports; without a target it gives the
`contributes` flags of the walk.

Before anything runs, the search reads the walk folder under the
[reader rules of a walk folder](#reader-rules-of-a-walk-folder) and refuses:

- with `walk_not_attributed` when the walk did not attribute every revision;
- with `walk_mismatch` when the walk folder fails a reader rule, or when the walk
  names other records (by the byte hashes of its copies of the two run records),
  another tolerance profile, other held kinds, or a manifest that differs, byte
  for byte, from the one the search derives again, or when it fails the
  [environment rule](#same-environment).

A refused search writes nothing.

### Reader rules of a walk folder

A walk folder is the folder a walk writes, see [Walk](#walk). A reader of a walk
folder applies these rules; a folder that breaks one is no reference:

- The run record `walk.run-record.json` passes the reader rules of
  [run.md](run.md#run-record), has the procedure type `walk`, and lists
  `walk.result.json` as its result, with its hash.
- The walk result `walk.result.json` passes its schema.
- `states` holds the numbers 0 to n, each once, in order, where n is the number
  of changes of the manifest. State k names revision k of the manifest and the
  run id `<walk_id>-state-<k>`, and `walk_id` is that of the two records.
- Every artifact the walk result and the documents it references list exists
  with its hash.
- The steps lead from each state that succeeded to the next one that succeeded
  and carry exactly the revisions between them.
- `ends` agree with the outcomes of state 0 and state n: an end that is
  reproduced belongs to a state that succeeded.

The **state folder** of state k is the folder of its response in the walk
result. It holds the request `request.json`, the response, the export, and the
run record `run-record.json` of the state, and from state 1 on a copy of the
manifest.

### Same environment

A walk is a reference only for the engine it ran on. For every state k, the
search builds the request it would send itself on the present engine and
compares, as JSON values, its `release`, `changes.enabled`, `changes.hold`, and
`selection` with those of `request.json` in the state folder of state k, and
the `releases` of `run-record.json` in that folder with the release the present
engine records for the request. Both documents must pass their schemas. For
every state after state 0 the manifest the request references must equal, byte
for byte, the manifest the search derives again, so that the enabled revisions
are the same changes. Any difference, for example another engine version, is
`walk_mismatch`, before anything runs.

### Findings of a search

A search has the findings of a walk, with these meanings, and one of its own:

| Code | Raised when | Then |
|---|---|---|
| `state_zero_not_reproduced`, `state_n_not_reproduced` | State 0 or state n does not reproduce its recorded result. | The search stops. The finding references the comparison. |
| `state_did_not_run` | A state ends `failed`, `rejected`, or `error`. | For state 0 or state n the search stops; for an inner state the nearest other state inside the interval that runs is used. The finding holds the diagnostic of the run. |
| `step_not_compared` | The comparison that judges a contribution has no outcome `compared`. | Every quantity the interval judges differs. The finding holds the diagnostic and references the kept comparison. |
| `non_finite_difference` | A sum of a contribution does not fit a finite binary64 value. | The sum is not written. |
| `interval_not_resolved` | An interval differs for a quantity while neither half differs for it. | Nothing is attributed for that quantity. The finding names the interval by its revisions and its later state, and the quantity. |

## Search result

```json
{
  "document": "search_result",
  "contract_version": "1.0",
  "stage": "liability_cashflow",
  "search_id": "search-run-n-full-run-n1-full",
  "walk": { "walk_id": "walk-run-n-full-run-n1-full", "result": { "path": "walk/walk.result.json", "sha256": "…" } },
  "manifest": { "path": "changes.json", "sha256": "…" },
  "older": { "run_id": "run-n-full", "release_label": "N" },
  "newer": { "run_id": "run-n1-full", "release_label": "N+1" },
  "tolerance": { "per_quantity": {} },
  "held": [],
  "remainder": [],
  "ends": { "zero": { "state": 0, "outcome": "reproduced" }, "n": { "state": 4, "outcome": "reproduced" } },
  "states": [ { "state": 0, "run_id": "search-run-n-full-run-n1-full-state-0", "outcome": "succeeded", "response": { "path": "state-00/response.json", "sha256": "…" }, "export": { "path": "state-00/results.csv", "sha256": "…" } } ],
  "target": { "quantities": ["Netto-Cashflow"], "periods": { "first": 0, "last": 59 } },
  "intervals": [ { "from_state": 0, "to_state": 4, "revisions": ["…"], "differs": ["Netto-Cashflow"] } ],
  "contributions": [ { "from_state": 0, "to_state": 1, "revisions": ["…"], "compare": { "result": { "path": "interval-00-01.compare.result.json", "sha256": "…" } }, "contributions": [ { "quantity": "Netto-Cashflow", "contributes": true, "sum": -12.5, "absolute_sum": 12.5 } ] } ],
  "runs": { "walk": 5, "search": 4, "saved": 1 },
  "missed": [],
  "findings": []
}
```

The block is shortened as that of the walk result.
[examples/search/](examples/search/) holds the search result of a search over the
four revisions of the walk example for the target `Anzahl Verträge` in period 0,
checked against that walk, with the documents it references, the copied walk
result among them. As in the walk example, the requests, the run records, the
copies of the recorded runs, and the run record of the search are left out.

| Member | Meaning |
|---|---|
| `search_id` | `search-<older run id>-<newer run id>`. It does not name the target; one folder holds one search. |
| `walk` | With a walk only: its `walk_id` and the copied walk result `walk/walk.result.json`, by artifact reference. |
| `manifest`, `older`, `newer`, `tolerance`, `held`, `remainder`, `ends` | As in the walk result. |
| `states` | Every state the search requested, in the form of the walk result. |
| `target` | `quantities`, in quantity order, and, when a range was asked for, `periods` with `first` and `last`, counted from the valuation date, see [Target](#target). |
| `intervals` | Every interval judged: `from_state`, `to_state`, the `revisions` between them, and `differs`: among the quantities the interval is judged for, those its parent passes on, the ones for which its ends differ. |
| `contributions` | Every contribution found, in the shape of a step of the walk. |
| `runs` | `walk`, the n + 1 states a walk requests; `search`, the states the search requested; `saved`, the difference. With a walk, `walk` equals the number of its states. |
| `missed` | With a walk only: the revisions and quantities the search missed, see [Check against a walk](#check-against-a-walk). |
| `findings` | The findings, see [Findings of a search](#findings-of-a-search), in the form of the walk result. |

The search folder holds, like a walk folder, `changes.json`, `older/`,
`newer/`, and `tolerance.json` when a file names the tolerance profile; one
folder `state-<k>/` per state run; at the root the comparisons it keeps,
`interval-<a>-<b>.compare.*` for a contribution and the checks of the ends as in
the walk; `search.result.json` and `search.run-record.json`. With a walk, the
folder `walk/` holds byte copies of `walk.result.json`, `walk.run-record.json`,
the request and the run record of every state, and every file any of them
references, directly or through a referenced document, in their relative layout,
so that every reference of the copied walk resolves inside the search folder.

The search result references no run record, so the same two records, the same
walk folder or none, and the same history give the same search result, byte for
byte.

Ids: a state run has the run id `<search_id>-state-<k>`; the comparison kept for
a contribution the compare id `<search_id>-interval-<a>-<b>`; the checks of the
ends `<search_id>-state-<k>-check-older` and `<search_id>-state-<k>-check-newer`.

Orders:

- `states` and `contributions` in history order; `revisions` in history order.
- `intervals` in the order judged.
- `quantities` of the target, `differs`, and the contributions of a contribution
  in the quantity order of the older recorded response.
- `missed` in history order, then in quantity order.
- `findings` in the order the search meets them.

Schema assertions: every member above is present, `walk` and `missed` exactly
together; a contribution has a comparison and contributes to at least one
quantity; the assertions of a state and an end of the walk result hold.

## Run record of a search

A search writes a run record with the procedure type `search`, see
[run.md](run.md#run-record). Its outcome is `searched` when both ends ran and are
reproduced, also with missed contributions, and `stopped` otherwise. A search
that is refused before the first run writes no record. It lists the two recorded
run records, as copied for the search, the tolerance file when there is one, and
the copied walk result when there is a walk, as inputs; the manifest, the search
result, and every compare result the search kept, as outputs; and the release
identities of the older and the newer result, in this order.
