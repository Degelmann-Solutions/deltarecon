# Run contract

Version 3 of the stage contracts, see [README.md](README.md). The run contract
fixes how a caller asks an engine to run one stage for one release, what the
engine returns, how the results are exported, and what the run record holds.

Schemas: [schemas/run.schema.json](schemas/run.schema.json) and
[schemas/run-record.schema.json](schemas/run-record.schema.json).

## Run request

```json
{
  "document": "run_request",
  "contract_version": "3.0",
  "stage": "liability_cashflow",
  "run_id": "run-n-subset-changes",
  "release": { "label": "N", "references": [ { "kind": "engine_version", "value": "engine build 2026.09" } ] },
  "changes": {
    "enabled": ["chg-lapse-year-1-down"],
    "manifest": { "path": "changes.json", "sha256": "…" }
  },
  "selection": { "mode": "subset", "model_point_ids": ["MP-0001", "MP-0002"] }
}
```

| Member | Meaning |
|---|---|
| `stage` | The stage to run, see [README.md](README.md#stage-identifier). |
| `run_id` | The caller's identifier of this run. It is opaque. It names the request: what is to be calculated. Two executions of one request share it; each execution is named by the `record_id` of its [run record](#run-record). |
| `release` | The release identity, see [README.md](README.md#release-identity). |
| `changes.enabled` | The ids of the changes to apply on top of the release. An empty list runs the release as it is. |
| `changes.manifest` | The change manifest the ids refer to, see [changes.md](changes.md). Required when a change is enabled. |
| `changes.hold` | Optional. The kinds of release reference the engine takes from `release` while changes of the type `revision` are enabled, see [changes.md](changes.md#revision-profile). Without it nothing is held. |
| `selection` | The model points to run, see below. |

A request asks for all quantities the engine exports for the stage, for every
period of every selected model point. Which quantities these are is the
engine's declaration in the response, see rule 7. Version 3 has no member to
choose quantities or periods.

Schema assertions: all members above are present; `contract_version` is `3.0`;
the references are not empty; the enabled ids are distinct; the manifest is
present when a change is enabled; `changes.hold`, when present, names at least
one kind and no kind twice.

Reader rules for the engine:

1. Check the stage and the artifact references as stated in [README.md](README.md#stage-identifier)
   and [README.md](README.md#artifact-references-and-byte-hashes).
2. Check the enabled changes against the manifest as stated in
   [changes.md](changes.md#combination-rules).
3. Check the selection as stated below.
4. If any check fails, answer with a rejection and run nothing.

## Selection

A selection is full or a subset:

```json
{ "mode": "full" }
```

```json
{ "mode": "subset", "model_point_ids": ["MP-0001", "MP-0002"] }
```

- `full` selects every model point the release holds after the enabled changes
  are applied.
- `subset` selects exactly the model points named. Whether a subset run returns
  the same values for a model point as a full run of the same release and
  change set is declared by the domain reference of the stage. Where it declares
  that results depend on the selection, a result is valid only for its own
  selection.

Schema assertions: a subset names at least one model point id, and no id twice.
An empty or a duplicate selection is a schema violation.

Reader rules for the engine:

5. Every selected model point id exists in the release after the enabled changes
   are applied. Otherwise the engine rejects the whole request with
   `unknown_model_point` and names the unknown ids. It does not run the others.

## Run response

A response has one of four outcomes.

| Outcome | Meaning | Carries |
|---|---|---|
| `succeeded` | Every selected model point was calculated. | The export and its description. |
| `failed` | The engine accepted the request and at least one model point could not be calculated. | The failing model points. No export. |
| `error` | The engine accepted the request, but it could not restore or read the state the request names. | Diagnostics. No export. |
| `rejected` | The engine did not accept the request and ran nothing. | Diagnostics. No export. |

A response with the outcome `succeeded`:

```json
{
  "document": "run_response",
  "contract_version": "3.0",
  "stage": "liability_cashflow",
  "run_id": "run-n-subset-changes",
  "outcome": "succeeded",
  "release": { "label": "N", "references": [ { "kind": "engine_version", "value": "engine build 2026.09" } ] },
  "changes": { "enabled": ["chg-lapse-year-1-down"], "manifest": { "path": "changes.json", "sha256": "…" } },
  "selection": { "mode": "subset", "model_point_ids": ["MP-0001", "MP-0002"] },
  "time_basis": { "id": "policy_month" },
  "quantities": [ { "name": "Anzahl Verträge", "unit": "policies" }, { "name": "Bruttobeitrag", "unit": "EUR" } ],
  "model_points": [
    { "model_point_id": "MP-0001", "first_period": 0, "last_period": 2 },
    { "model_point_id": "MP-0002", "first_period": 144, "last_period": 146 }
  ],
  "export": { "artifact": { "path": "subset-run.results.csv", "sha256": "…" }, "data_rows": 6 }
}
```

| Member | Meaning |
|---|---|
| `stage`, `run_id`, `release`, `changes`, `selection` | Repeated from the request, unchanged. |
| `time_basis` | The declared time basis, by the identifier of the domain reference. |
| `quantities` | The quantities the engine exports, with their units, in export column order. |
| `model_points` | Every exported model point with its first and last period, both inclusive. |
| `export.artifact` | The export file, with its byte hash. |
| `export.data_rows` | The number of rows of the export, without the header. |

## Per-model-point export

The export is one CSV file under the [CSV profile](README.md#csv-profile).

```
model_point_id,period,Anzahl Verträge,Bruttobeitrag,Zahlbeitrag,Beitragsverrechnung,garantierte Todesfallleistung,garantierter Rückkaufswert,garantierte Erlebensfallleistung,Kosten 2. Ordnung ohne Provisionen,Provisionen,Netto-Cashflow
MP-0001,0,1,1200,800,400,20,0,0,100,300,380
MP-0001,1,0.995,0,0,0,30,0,0,2.5,0,-32.5
MP-0002,144,1,100,70,30,40,0,0,3,0.7,26.3
```

- The header is `model_point_id`, `period`, and then the quantity names in the
  order of `quantities` in the response.
- Each row holds one model point and one period, and one number per quantity.
  The key of a row is the pair of model point id and period.
- `model_point_id` is the opaque string, quoted where the CSV profile requires it.
- `period` is an integer. A writer writes periods and quantity values in the
  writer form of the [number format](README.md#number-format).
- Rows are ordered by model point id and then by period, see
  [README.md](README.md#deterministic-ordering).
- The export holds results only. Units, the time basis, the stage, and the
  contract version are in the response that references it.

## Result completeness

A caller accepts a response with the outcome `succeeded` only as a whole.

Reader rules for the caller:

6. The response repeats the stage, run id, release identity, change set, and
   selection of the request. A different stage is rejected with `stage_mismatch`,
   any other difference with `request_mismatch`.
7. Every declared quantity name is a name the domain reference of the stage
   defines, no name is declared twice, and the names stand in the order of the
   domain reference. An engine may export a subset of the quantities, with at
   least one. Otherwise the caller rejects with `quantity_mismatch`. The
   time basis identifier and the units are the run's own declaration and are
   not checked here; the compare contract checks that two runs agree on them.
8. The export file exists and has the stated hash, see
   [README.md](README.md#artifact-references-and-byte-hashes).
9. The export can be read under the CSV profile and the reader grammar of the
   number format, and its header matches `quantities`. Otherwise the caller rejects with `export_format`,
   `number_format`, or `non_finite_value`.
10. For a subset selection, `model_points` names exactly the selected ids. An id
    that was selected and is absent is rejected with `missing_coordinate`; an id
    that was not selected with `unrequested_coordinate`. For a full selection,
    the engine names every model point the release holds after the enabled
    changes are applied. The documents do not list the model points of a
    release, so a caller can detect an omission in a full run only if it knows
    that set from another source; it then applies the same two diagnostics.
11. No model point id occurs twice in `model_points`, and `first_period` is not
    greater than `last_period`. Otherwise the caller rejects with
    `inconsistent_response`.
12. The export holds exactly one row for every period from `first_period` to
    `last_period` of every model point in `model_points`, and no other row. A
    repeated key is rejected with `duplicate_coordinate`, an absent row with
    `missing_coordinate`, a further row with `unrequested_coordinate`.
13. `export.data_rows` equals the number of rows the ranges in `model_points`
    add up to. Otherwise the caller rejects with `inconsistent_response`.
14. If any rule fails, the caller rejects the whole result. It keeps no rows of
    it: there is no successful partial result.

## Failure outcome

If the engine cannot calculate a selected model point, the run has failed:

```json
{
  "document": "run_response",
  "contract_version": "3.0",
  "stage": "liability_cashflow",
  "run_id": "run-failed-run",
  "outcome": "failed",
  "release": { "label": "N", "references": [ { "kind": "code_state", "value": "revision 1047" } ] },
  "changes": { "enabled": [] },
  "selection": { "mode": "full" },
  "failed_model_points": [ { "model_point_id": "MP-0002", "message": "No lapse rate for policy year 13." } ]
}
```

- The outcome is `failed`, and `failed_model_points` names every failing model
  point the engine found, with a message for a person. A failed response has no
  `diagnostics` member; the code `model_point_failed` is implied by the outcome.
- A failed response carries no export. Results of the model points that did not
  fail are not returned.
- An engine may stop at the first failing model point or go on to find them all.
  It names at least one.

## Error outcome

If the engine has accepted the request but cannot restore or read the state the
request names, the run ends with the outcome `error`:

```json
{
  "document": "run_response",
  "contract_version": "3.0",
  "stage": "liability_cashflow",
  "run_id": "run-n-full",
  "outcome": "error",
  "release": { "label": "N", "references": [ { "kind": "code_state", "value": "revision 1047" } ] },
  "changes": { "enabled": [] },
  "selection": { "mode": "full" },
  "diagnostics": [ { "code": "no_model_point", "message": "The release state holds no model point." } ]
}
```

- The response repeats `stage`, `run_id`, `release`, `changes`, and `selection`
  of the request, as a failed response does, and carries `diagnostics` in place
  of `failed_model_points`. It carries no export.
- `diagnostics` holds one entry with one of three codes:

| Code | Raised when |
|---|---|
| `no_model_point` | The state holds no model point. A subset selection is checked first: an id the state does not hold gives `unknown_model_point` and a rejection. |
| `invalid_model_point_id` | The state yields a model point id that the schema of an id forbids: an empty string or one with a control character. It is checked before the export is written. The id cannot be named in `model_point_ids`; the message describes it. |
| `state_not_readable` | Anything else goes wrong while the engine restores the state, applies the enabled changes, or reads the model points, the parameters, the quantities, or the time basis. |

- The message of `state_not_readable` is the kind of error and the last line of
  its own message, `<kind>: <last line>`; an error with an empty message gives
  `<kind>` alone. Where it names the folder the state was
  restored to or the folder that holds what the engine restores a release from,
  these folders are written as `<scratch>` and `<repositories>`. So the message
  holds no path of one machine, and a repeated run of the same state writes the
  same message.
- A model point the engine cannot calculate still gives `failed`, and a request
  the engine does not accept still gives `rejected`. `error` is for a state that
  was accepted and cannot be read.

## Rejection

If the engine does not accept a request, it answers with the outcome `rejected`:

```json
{
  "document": "run_response",
  "contract_version": "3.0",
  "stage": "liability_cashflow",
  "run_id": "run-unknown-model-point",
  "outcome": "rejected",
  "diagnostics": [
    { "code": "unknown_model_point", "message": "The release holds no model point with this id.", "model_point_ids": ["MP-9999"] }
  ]
}
```

- `stage` and `run_id` are repeated from the request where they can be read. A
  request that is not JSON, or that lacks them, leaves nothing to repeat.
- Schema assertions: `document`, `contract_version`, `outcome`, and
  `diagnostics` are present; `stage` and `run_id` are optional.
- `diagnostics` holds at least one entry with a code from
  [README.md](README.md#diagnostics).
- A rejected run has calculated nothing and exports nothing.

## Run record

A run record makes one run of a procedure reproducible and auditable. It is one
envelope for every deterministic procedure, not only for a stage run:

```json
{
  "document": "run_record",
  "contract_version": "3.0",
  "stage": "liability_cashflow",
  "record_id": "record-6f1c2d3e-4a5b-4c6d-8e7f-0a1b2c3d4e5f",
  "procedure": { "type": "run" },
  "outcome": "succeeded",
  "recorded_at": "2026-10-03T09:00:00Z",
  "inputs": [ { "role": "request", "artifact": { "path": "full-run.request.json", "sha256": "…" } } ],
  "releases": [ { "label": "N", "references": [ { "kind": "engine_version", "value": "engine build 2026.09" } ] } ],
  "parameters": [ { "name": "valuation_rate", "type": "scalar", "value": 0.01 } ],
  "outputs": [
    { "role": "response", "artifact": { "path": "full-run.response.json", "sha256": "…" } },
    { "role": "export", "artifact": { "path": "full-run.results.csv", "sha256": "…" } }
  ]
}
```

| Member | Meaning |
|---|---|
| `record_id` | The identifier of this execution of the procedure: `record-` followed by a random UUID of version 4 in lower-case hexadecimal, as in the example. The writer generates it anew for every execution of every procedure and never repeats it. |
| `procedure.type` | The procedure that ran. Version 3 registers `run`, `compare`, `walk`, and `search`, see [localise.md](localise.md#run-record-of-a-walk) and [localise.md](localise.md#run-record-of-a-search). Other procedures use their own type name. |
| `outcome` | The outcome the procedure reported. |
| `recorded_at` | Optional time of recording, in UTC. It is information only and is never compared. |
| `inputs` | The documents handed to the procedure, each with a role and a byte hash. |
| `releases` | The release identities the caller supplied, unchanged. A run has one; a comparison has the left and the right one, in this order; a walk and a search the older and the newer one. |
| `parameters` | The parameter inventory of the run, see [compare.md](compare.md#parameter-model). It is empty for a procedure that evaluates no model, for a rejected run, and for a run with the outcome `error` whose engine could not read the inventory. |
| `outputs` | The documents and exports the procedure produced, each with a role and a byte hash. |

Registered roles:

| Procedure | Inputs | Outputs |
|---|---|---|
| `run` | `request`, and `change_manifest` when a change is enabled and the manifest has passed its artifact check; for the outcome `error` the check is made also when the engine failed before it | `response`, and `export` when the run succeeded |
| `compare` | `request` | `result`, and `deviations` and `signature_table` when the outcome is `compared` |
| `walk` | `older_record` and `newer_record`, and `tolerance` when a file names the tolerance profile | `change_manifest`, `result`, and one `compare_result` per comparison the walk kept |
| `search` | `older_record` and `newer_record`, `tolerance` when a file names the tolerance profile, and `walk_result`, the copied walk result, when the search is checked against a walk | `change_manifest`, `result`, and one `compare_result` per comparison the search kept |

Rules:

- Inputs and outputs are stored files, so each carries a byte hash. The
  artifacts of the registered roles are always listed. Any other artifact that
  a listed document references, such as a patch file of the manifest or the
  responses of a compare request, is covered through the hash of that document
  and is not listed.
- The inventory holds every parameter the run used, after the enabled changes
  were applied. It is what the parameter diff compares.
- The record stores what the caller supplied. If the engine does not record its
  own state, reproducibility rests on the caller's references.
- The record is written for every outcome, also for a failed run and for a run
  with the outcome `error`.
- `record_id` names one execution, `run_id` one request. Only a run record
  carries the identity of an execution. The identifier that a repetition with
  the same inputs receives anew is the `record_id`, not the `run_id`. When the
  engine repeats its own results, two executions of one request therefore write the same bytes in every
  other document, with one exception: a document
  that references a run record by its byte hash, such as a compare request that
  names the record of a run, differs with that record. Their run records differ
  in `record_id`, `recorded_at`, and the hash of a listed document that
  references a run record by its hash.
- The record of a comparison holds the release identities of both compared
  runs. A comparison that is rejected before both identities can be read writes
  its compare result alone and no record.

Reader rules:

15. Every artifact of the record exists and has the stated hash. Otherwise the
    reader rejects with `artifact_missing` or `artifact_hash_mismatch`.
16. The stage of the record and the stage of the documents it lists are the
    same. Otherwise the reader rejects with `stage_mismatch`.
17. The release identities equal those of the listed request or, for a
    comparison, those of the two compared runs. Otherwise the reader rejects
    with `request_mismatch`.

A run is reproduced when the criterion in [compare.md](compare.md#replay-criterion)
holds: exactly, at the decimal places the replay states, or within the tolerances it states. This version specifies the criterion and the record. It does not specify
a replay procedure.
