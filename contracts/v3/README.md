# Stage contracts, version 3

A valuation process chain is a sequence of stages. This pack describes one stage
by three contracts that any calculation engine can implement:

| Contract | File | What it fixes |
|---|---|---|
| Run | [run.md](run.md) | How a caller asks an engine to run a stage for a release, and what the engine returns. |
| Changes | [changes.md](changes.md) | How the changes between two releases are listed, which combinations may be enabled, and how the list is derived from a revision history. |
| Compare | [compare.md](compare.md) | How the results and the parameters of two runs are compared, and how the deviations are condensed into a signature table. |

A fourth file, [localise.md](localise.md), is no stage contract: no engine
implements it. It fixes procedures of the tool built on run, changes, and
compare: the walk over every state between two recorded results, and its walk
result, which attributes the deviation to revisions per quantity; and the search,
which halves the history for a target with fewer runs, and its search result,
which states what it found, what it saved, and, checked against a walk, what it
missed.

A domain reference per stage names the quantities, their units and signs, and the
time basis: [domain/liability_cashflow.md](domain/liability_cashflow.md).

The pack stands alone. It prescribes messages and files, not an implementation.
The schemas under [schemas/](schemas/) state what a document must look like. The
text states what a reader must check beyond that. The examples under
[examples/](examples/) show both, and [examples/index.json](examples/index.json)
names every example, its expected outcome, and the rule it shows.

Each contract file separates two kinds of statement:

- **Schema assertions** hold for a single document and are checked by its schema.
- **Reader rules** need more than one document, an export file, or stored bytes.
  A schema cannot express them. They are numbered, and a reader must apply them.

## Vocabulary

- **Engine:** the system that calculates a stage, together with any layer that
  turns its native input and output into the documents and exports of this
  pack. Such a layer may rename columns, reshape an export, compute byte
  hashes, and write the response and the run record. Conformance is judged on
  the documents and exports, not on which part of the system writes them.
- **Caller:** the party that sends a request to an engine and reads the response.
- **Reader:** whoever consumes a document or an export. Callers and engines are both readers.
- **Stage:** one step of the process chain, named by a stage identifier.
- **Release:** one version of a stage: its input data, parameters, code, and engine.
- **Model point:** the smallest result unit an engine exports for a stage. It is a
  single insurance contract, an aggregated contract record, or an output group.
  The contracts do not prescribe which.
- **Model point id:** the public identifier of a model point. It is an opaque
  string. Two runs refer to the same model point when the strings are equal,
  code point by code point.
- **Time basis:** the declared meaning of the time coordinate. It belongs to the
  domain reference of a stage.
- **Period:** an integer index on the time basis.
- **Projection period:** a period counted from the valuation date of its run. On
  a time basis whose origin is the issue date, `policy_month`, it is the period
  less the first exported period of the model point in that run; on every other
  basis it is the period. Comparisons pair values by projection period and write
  projection periods, see [compare.md](compare.md#alignment).
- **Quantity:** a named result value, with a unit, defined in the domain reference.
- **Coordinate:** a triple of model point id, period, and quantity. A result has
  one finite number per coordinate.
- **Change:** one switchable difference between two releases.
- **Revision:** one state of a versioned history, named by an identifier of that history.
- **Export:** the file that holds the results of a run, one row per model point and period.
- **Deviation file:** the file that lists the deviating coordinates of one comparison, one row per coordinate.
- **Run record:** the document that makes one execution of a procedure reproducible and auditable.
- **Document:** a JSON text defined by this pack. The member `document` names its type.

## Stage identifier

A stage identifier is a lower-case name that matches `^[a-z][a-z0-9_]*$`. Version 3
defines one stage:

| Stage identifier | Domain reference |
|---|---|
| `liability_cashflow` | [domain/liability_cashflow.md](domain/liability_cashflow.md) |

Every document carries the members `stage` and `contract_version`, with one
exception: a rejected run response omits `stage` when the request it answers
exposes none, see [run.md](run.md#rejection). An export file
has no place for them; it is read only together with the run response that
references it, and that response carries both.

Reader rules:

1. A reader rejects a document whose stage it does not support, with `unsupported_stage`.
2. A run response names the stage of its request, and a change manifest names
   the stage of the request that references it. Otherwise the reader rejects
   with `stage_mismatch`. A response with another `run_id` than its request is
   rejected with `request_mismatch`, see [run.md](run.md#result-completeness).
   For the stages of a comparison, see [compare.md](compare.md#compatibility).

## Version compatibility

The contract version is the string `3.0`: a major and a minor number.

- A minor version adds optional members, new diagnostic codes, or new registered
  names. It removes and redefines nothing.
- A major version may change anything.
- A reader accepts exactly the versions it implements. It rejects every other
  version with `unsupported_version` and does not guess. It checks the version
  before it applies a schema. The schemas in this pack
  accept `3.0` only, and they are closed: a member they do not name is an error.
- The path of this pack, `contracts/v3/`, names the major version. Version 1.0
  stays published unchanged under [`contracts/v1/`](../v1/README.md), and
  version 2.0 under [`contracts/v2/`](../v2/README.md).

Reader rule for documents of versions 1.0 and 2.0:

- A reader of version 3.0 also reads documents of versions 1.0 and 2.0. It
  checks each document against the schemas of its own version: a 1.0 document
  against the schemas under [`../v1/schemas/`](../v1/schemas/), a 2.0 document
  against the schemas under [`../v2/schemas/`](../v2/schemas/), a 3.0 document
  against the schemas of this pack. A schema fault in a 1.0 or 2.0 document is
  a fault against the schema of its version.
- A run request and a compare request of version 1.0 or 2.0 are accepted. Every
  document a 3.0 writer produces in answer, and every other document it writes,
  carries `3.0`.
- A run record of version 1.0 or 2.0, with the documents it lists, serves as
  input to every procedure that reads recorded runs, except the replay: a
  replay repeats only runs recorded under 2.0 or 3.0 and rejects a 1.0 run
  record with `unsupported_version`. For a run recorded under 2.0 with the
  outcome `error`, the recorded and the repeated response may differ in
  `contract_version` only, see [compare.md](compare.md#replay-criterion).
- A walk folder written under 1.0 or 2.0 is a reference for a search when it
  passes the reader rules of a walk folder, see
  [localise.md](localise.md#reader-rules-of-a-walk-folder); its change
  manifests may differ from the manifest derived again in `contract_version`
  only.

### Changes from 2.0

Version 3.0 changes the versions a reader accepts, adds computation paths to
the release identity, aligns every comparison on projection periods, and adds
the opt-in switch `reuse_walk` of the search. A document written without a
switch differs from 2.0 in `contract_version` and, for a comparison on
`policy_month`, in its period numbering only, as long as no model point's first
exported period moves between the compared runs; where one moves, the pairing
of values changes as described below.
The schemas change for the switch alone: they gain optional members, a search
under the switch may report 0 runs of its own, and the search result ties these
members to the switch, as listed below.

What changes in the versions a reader accepts:

- The replay of a run recorded under 2.0 with the outcome `error`: its repeated
  response is written under 3.0, so the byte comparison of the two responses
  ignores `contract_version`.
- A reader of 3.0 also reads documents of 1.0 and 2.0, under the
  [reader rule for documents of versions 1.0 and 2.0](#version-compatibility).
  A reader of 2.0 rejects a 3.0 document with `unsupported_version`, as its
  pack states.
- A walk folder written under 2.0 is a reference for a search, as a walk folder
  written under 1.0 already was under 2.0.

What the alignment on projection periods changes:

- On `policy_month`, whose origin is the issue date, a comparison puts each run
  on projection periods first: coordinate (p, t) becomes (p, t - s_p), where s_p
  is the first exported period of p in that run, see
  [compare.md](compare.md#alignment). Under 2.0 values were paired by policy
  month, so a model point whose first exported period moved between the two runs
  paired values of different projection periods and showed added and removed
  coordinates. The field names and the schemas do not change: `period`,
  `first_period`, and `last_period` of compare results, deviation files, and
  signature tables, and the sums of walk steps and search contributions, now
  rest on projection periods. Run responses, exports, and run requests keep
  policy months. On every other time basis nothing changes.
- The target of a search counts each model point from its first exported period
  in each run, recorded run or state, and no longer from the older recorded
  export alone, see [localise.md](localise.md#target).

What computation paths add:

- An engine may offer several computation paths for one release, each named by
  its own `engine_version` value, see [Release identity](#release-identity). The
  request chooses the path, and a run never falls back to another one. A state
  of a walk or a search names the release identity of the older result on the
  computation path of the older result, see [localise.md](localise.md#walk).

What the switch `reuse_walk` adds:

- A search checked against a walk may take every state it needs from the walk
  instead of running it, see
  [localise.md](localise.md#reuse-of-the-walks-states). A reused state is no
  run and is named as such.
- `localise.schema.json`: the search result has the optional member `switches`;
  under `reuse_walk` it requires `walk` and `runs.reused`, and `runs.search` may
  be 0; without the switch `runs.search` is at least 1, as before, and neither
  `runs.reused` nor a state with `reused` is allowed. A state of the search
  result may carry `reused` (`true`), in the new definition `search_state`; the
  walk's `state` is `search_state` without `reused`.
- `run-record.schema.json`: the run record has the optional member `switches`.

The 2.0 pack: [README](../v2/README.md), [run](../v2/run.md),
[changes](../v2/changes.md), [compare](../v2/compare.md),
[localise](../v2/localise.md), and
[domain reference](../v2/domain/liability_cashflow.md).

### Changes from 1.0

What version 2.0 changed from 1.0 is stated in
[Changes from 1.0](../v2/README.md#changes-from-10) of the 2.0 pack.

## Serialization

Messages, change manifests, signature tables, walk results, search results, and run records are
JSON. Result exports and deviation files are CSV.

### JSON profile

- A document is one JSON text as defined by [RFC 8259](https://datatracker.ietf.org/doc/html/rfc8259),
  encoded in UTF-8 without a byte order mark.
- The top-level value is an object. Its member `document` names the document type.
- Member names within one object are unique. A reader rejects a repeated name
  with `duplicate_member`. It does not pick one of the values.
- Numbers are finite. They are read as IEEE 754 binary64 values. JSON has no
  text for a non-finite number, and a reader rejects any extension that adds one
  with `invalid_json`. It rejects in the same way a number that is too large for
  a finite binary64 value, such as `1e999`.
- A reader rejects a document that violates its schema with `schema_violation`.
- There is no canonical JSON form. White space and member order carry no meaning.
  Equality of results is judged by the compare contract, never by comparing JSON text.

The schemas are [JSON Schema 2020-12](https://json-schema.org/draft/2020-12/json-schema-validation).
They reference each other by file name only and need no network access.

| Document type | Schema |
|---|---|
| `run_request`, `run_response` | [schemas/run.schema.json](schemas/run.schema.json) |
| `change_manifest`, authored or derived from a revision history | [schemas/changes.schema.json](schemas/changes.schema.json) |
| `compare_request`, `compare_result`, `signature_table` | [schemas/compare.schema.json](schemas/compare.schema.json) |
| `walk_result`, `search_result` | [schemas/localise.schema.json](schemas/localise.schema.json) |
| `run_record` | [schemas/run-record.schema.json](schemas/run-record.schema.json) |
| shared shapes | [schemas/common.schema.json](schemas/common.schema.json) |

### CSV profile

- An export and a deviation file are CSV files as defined by [RFC 4180](https://datatracker.ietf.org/doc/html/rfc4180),
  with these choices fixed: UTF-8 without a byte order mark, a comma as the
  separator, a line feed as the line end, and a line feed after the last row.
- The first row is the header. Every later row has as many fields as the header.
- A field is quoted only when it contains a comma, a double quote, or a line
  break. A double quote inside a quoted field is doubled.
- No field is empty.

### Number format

The number format is strict for a writer and tolerant for a reader.

**Writer grammar.** A writer writes every number of an export and of a
deviation file as decimal text in this form:

- It matches `-?(0|[1-9][0-9]*)(\.[0-9]*[1-9])?(e-?[1-9][0-9]*)?`. The decimal mark
  is a point. There is no thousands separator, no plus sign, no leading zero, no
  trailing zero after the point, and no locale variant.
- Zero is written `0` and in no other way: not `-0`, and not with an exponent.
- Its digits are the shortest that read back to the same binary64 value. `0.1` is
  in writer form; `0.10000000000000001` is not.
- A writer may use the exponent form or the positional form. `1e-7` and
  `0.0000001` are both in writer form.
- A writer writes a period index as an integer that matches `0|-?[1-9][0-9]*`.

**Reader grammar.** A reader accepts every finite decimal number with a point as
the decimal mark:

- It matches `-?[0-9]+(\.[0-9]+)?([eE][+-]?[0-9]+)?`: an optional minus sign,
  digits, an optional fraction, and an optional exponent with `e` or `E` and an
  optional sign.
- Leading zeros, trailing zeros, a plus sign in the exponent, digits beyond the
  shortest form, and `-0` are accepted. `007`, `1.50`, `1E+7`, and `-0` are read
  as 7, 1.5, 10000000, and 0.
- The text is read as the nearest binary64 value.
- A reader accepts a period index that matches `-?[0-9]+`.

A reader rejects everything else:

- Text for a non-finite value, such as `NaN`, `inf`, or `Infinity`, with any
  sign and in any case, is rejected with `non_finite_value`.
- A decimal comma, a thousands separator, a leading plus sign, hexadecimal
  text, a point without digits on both sides, an empty field, and a number too
  large for a finite binary64 value are rejected with `number_format`.

The exports and deviation files in this pack are in writer form.

## Release identity

A release is identified by a label and a set of opaque references:

```json
{
  "label": "2026Q3",
  "references": [
    { "kind": "input_data", "value": "portfolio extract 2026-09-30, run group 17" },
    { "kind": "parameter_set", "value": "assumption set 2026Q3 revision 4" },
    { "kind": "code_state", "value": "workspace revision 8841" },
    { "kind": "engine_version", "value": "12.4.1" }
  ]
}
```

- `label` is the caller's name for the release.
- Each reference has a `kind` and a `value`. The value is opaque: only the caller
  and the engine know how to resolve it.
- Version 3 registers four kinds: `input_data`, `parameter_set`, `code_state`, and
  `engine_version`. Other kinds are allowed. A release may hold several
  references of one kind. A derived change manifest that names a kind in its
  remainder lists all references of that kind, see
  [changes.md](changes.md#derived-manifest).
- The caller supplies the references. The engine runs the state they name and
  returns them unchanged. The run record stores them unchanged.
- The set should name the complete state: input data, parameters, own code, and
  engine version. What the references leave out cannot be restored later.
- An engine may offer several computation paths for one release, each with its
  own `engine_version` value. The request chooses the path by the value it
  names, and a run never falls back to another path: a path that cannot compute
  the state ends the run with the outcome `error`, see
  [run.md](run.md#error-outcome).

Reader rules:

3. Two release identities are equal when their labels are equal and their
   references are equal as sets. The order of the references carries no meaning.
4. An engine that cannot resolve a reference rejects the request with `unknown_reference`.

## Artifact references and byte hashes

An artifact is a file. A document references it by a relative path and the
SHA-256 of its exact stored bytes, in lower-case hexadecimal:

```json
{ "path": "release/model_points.csv", "sha256": "…64 hexadecimal digits…" }
```

- The path is relative to the directory of the document that carries the
  reference. It uses forward slashes and has no `.` or `..` segment.
- A response and a run record repeat the release identity and the manifest
  reference of the request unchanged, paths included. The documents of one run
  or one comparison that repeat a reference are therefore stored in one
  directory, so that each path resolves to the same file from each of them.
- A byte hash is required only where a reference points to an artifact stored as
  a file. Exports, change manifests, patch files, and the documents listed in a
  run record are such files and always carry a hash.
- A release reference carries the member `artifact` only when it points to a
  stored file. Without that member it carries no hash. An engine that cannot hash
  its own state still conforms: its release identity is made of opaque
  references alone.
- A hash covers stored bytes and nothing else. It does not say that two results
  are equal; the compare contract does.

Reader rules:

5. Before using an artifact, a reader checks that the file exists and that its
   bytes have the stated hash. A missing file is rejected with `artifact_missing`,
   a different hash with `artifact_hash_mismatch`. There is no partial acceptance.

## Deterministic ordering

A writer orders its output as follows, so that the same content gives the same file:

- Export rows: by model point id, then by period. Model point ids are ordered by
  Unicode code point; periods numerically.
- Export columns: `model_point_id`, `period`, then the exported quantities in the order of
  the domain reference.
- Lists of model points and period ranges: in the same order.
- Rows of a deviation file: by model point id, then by period; the rows of one
  model point and period follow the order of `quantities` of the compare result.
- Rows of a signature table: in the order of the member `quantities` of the
  compare result it is derived from.
- Parameter inventories and parameter diffs: by parameter name, by Unicode code
  point. Rows of a keyed table: by key, element by element; numbers numerically,
  strings by Unicode code point.
- Changes in a manifest: in application order. This order has a meaning, see
  [changes.md](changes.md#combination-rules).
- In a derived manifest: the classes of a change in the order `data`,
  `parameter`, `code`; `determines` by name and `remainder` by kind, both by
  Unicode code point; the references of a remainder entry by `value`, by
  Unicode code point, then by the byte hash of the artifact, then by the path
  of the artifact, a reference without an artifact first. See [changes.md](changes.md#derived-manifest).
- In a walk result: states, steps, and the revisions of a step in history order;
  contributions and totals in quantity order; the held kinds by name; findings in
  the order the walk meets them. See [localise.md](localise.md#walk-result).
- In a search result: states and contributions in history order; intervals in
  the order judged; the target quantities and the contributions of a
  contribution in quantity order; missed contributions in history order, then
  quantity order; findings in the order the search meets them. See
  [localise.md](localise.md#search-result).

Order carries meaning in these places only:

- `changes` of a manifest: the application order.
- `quantities` of a response or a compare result: the order of the export columns.
- `key_columns` and `value_columns` of a keyed table, and `key` and `values` of
  its rows: each element belongs to the column at the same position.
- `releases` of the run record of a comparison: the left release, then the right one.

A reader relies on no other order: not on the order of export rows, of
references, of enabled change ids, or of any other list.

## Diagnostics

A rejection, an incompatibility, and a run with the outcome `error` each carry
at least one diagnostic. A failed run names its failing model points instead and
has no `diagnostics` member; its code, `model_point_failed`, is implied by the
outcome.

```json
{ "code": "unknown_model_point", "message": "The release holds no model point with this id.", "model_point_ids": ["MP-9999"] }
```

A reader checks in this order: the JSON profile, the contract version, the
schema, and then the reader rules in the numbered order of the contract. A rule
of this file applies at the point where a contract rule refers to it. When
several rules are broken, the reader reports at least the diagnostic of the
first broken rule in that order.

`code` is one of the names below. `message` is free text for a person.
`model_point_ids` and `change_ids` name the subjects where there are any.

| Code | Raised when |
|---|---|
| `invalid_json` | The text is not JSON under the JSON profile. |
| `duplicate_member` | An object repeats a member name. |
| `schema_violation` | A document violates its schema. An empty or duplicate selection, a negative tolerance, a missing tolerance profile, and a rounding or a bound above zero without a derivation are cases of it. |
| `unsupported_version` | The contract version is not one the reader implements, or a replay is asked for a run record of version 1.0. |
| `unsupported_stage` | The reader does not support the stage. |
| `stage_mismatch` | Documents that belong together name different stages. |
| `request_mismatch` | A response does not repeat the run id, release identity, change set, or selection of its request, or a run record holds other release identities than the documents it lists. |
| `inconsistent_response` | A response contradicts itself: a model point is listed twice, a period range is reversed, or the stated row count does not fit the ranges. |
| `unknown_reference` | The engine cannot resolve a release reference. |
| `artifact_missing` | A referenced file does not exist. |
| `artifact_hash_mismatch` | A referenced file has another hash than stated. |
| `unknown_model_point` | A selection names a model point the release does not hold. |
| `unknown_change` | A change id is not in the manifest. |
| `invalid_inventory` | A parameter inventory repeats a name or a key, or a row does not fit its columns. |
| `invalid_manifest` | A manifest breaks a manifest rule of the changes contract. |
| `unmet_prerequisite` | An enabled change lacks an enabled prerequisite. |
| `change_conflict` | Two enabled changes conflict. |
| `unsupported_realisation` | The engine cannot realise a change of this realisation type. |
| `unrelated_revisions` | A change manifest cannot be derived: the older revision does not lie on the main line of the newer one. |
| `model_point_failed` | The engine could not calculate a model point. Implied by the outcome `failed`. |
| `no_model_point` | The engine has accepted the request and the state it restored holds no model point. Outcome `error`. |
| `invalid_model_point_id` | The engine has accepted the request and the state yields a model point id that the schema of an id forbids. Outcome `error`. |
| `state_not_readable` | The engine has accepted the request and cannot restore or read the state. Outcome `error`. |
| `number_format` | A number in an export cannot be read under the reader grammar of the number format. |
| `non_finite_value` | A value is not a finite number. |
| `export_format` | An export or a deviation file violates the CSV profile or has the wrong header, or the rows of a deviation file stand in another order than stated. |
| `duplicate_coordinate` | An export repeats a model point and period, or a deviation file repeats a coordinate. |
| `missing_coordinate` | A declared or requested coordinate is absent from the result. |
| `unrequested_coordinate` | A result holds a coordinate that was not requested or not declared. |
| `unit_mismatch` | Two runs declare different units for a quantity. |
| `time_basis_mismatch` | Two runs declare different time bases. |
| `quantity_mismatch` | A run declares a quantity name that the domain reference of its stage does not define, a name twice, or the names in another order than the domain reference; or two compared runs declare different quantity names. |
| `unknown_quantity` | A compare request sets a tolerance for a quantity that the two runs do not declare, or a deviation file names a quantity that its compare result does not declare. |
| `non_finite_difference` | The difference of the right and the left value of a common coordinate is not a finite number. |
| `not_a_deviation` | A row of a deviation file does not deviate by the tolerance rule of its compare result: its values are equal or differ within the tolerance. |
| `invalid_hold` | A request holds a kind the engine cannot hold, or holds a kind while no change of the type `revision` is enabled. |
| `selection_mismatch` | A walk is asked for two recorded results with different selections. Nothing runs. |
| `reference_mismatch` | A walk is asked for two recorded results whose moving references do not fit the history: the base revision does not name what the older result names, or the last revision not what the newer one names. Nothing runs. |
| `walk_not_attributed` | A search is checked against a walk that does not attribute every revision. Nothing runs. |
| `walk_mismatch` | A search is checked against a walk folder that fails the reader rules of a walk folder, or whose walk names other records, another tolerance profile, other held kinds, another manifest, or ran its states on another request or engine than the search would use. Nothing runs. |

A walk and a search report what they find in their result, not as a diagnostic:
the findings `state_zero_not_reproduced`, `state_n_not_reproduced`,
`state_did_not_run`, `step_not_compared`, and `non_finite_difference`, see
[localise.md](localise.md#findings), and for a search also
`interval_not_resolved`, see [localise.md](localise.md#findings-of-a-search).
Selections, references, and the derivation are refused for a search with the
diagnostics of the walk.

## Behaviour matrix

The matrix lists the behaviour the contracts require. The row identifiers appear
in [examples/index.json](examples/index.json) as `matrix_rows`.

| Row | Input or state | Required behaviour | Specified in |
|---|---|---|---|
| `complete-run` | Full or subset request with release identity and enabled change set; complete response and record | Accept. Stage, selection, quantities, units, and time basis agree. | [run.md](run.md#result-completeness) |
| `malformed-input` | Empty or duplicate selection, unknown model point id, unsupported version, duplicate member names or coordinates, non-finite value | Reject with the diagnostic of the table above. | [run.md](run.md#selection), [JSON profile](#json-profile), [number format](#number-format) |
| `opaque-release-identity` | Release identity made only of opaque references without byte hashes | Accept. | [Release identity](#release-identity) |
| `inconsistent-result` | Wrong stage; unrequested or missing result coordinates; for a reference that carries a byte hash, a missing artifact or a wrong hash | Reject. There is no successful partial result. | [run.md](run.md#result-completeness), [artifact references](#artifact-references-and-byte-hashes) |
| `model-point-failure` | One model point fails in the engine | The run outcome is `failed` and names the failing points. | [run.md](run.md#failure-outcome) |
| `engine-error` | The engine has accepted the request and cannot restore or read the state, or the state holds no model point or a forbidden id | The run outcome is `error` with its diagnostic. Response and run record are written; there is no export. | [run.md](run.md#error-outcome) |
| `incompatible-compare` | Compare with different units or time basis | Outcome `incompatible`. There is no comparison result. | [compare.md](compare.md#compatibility) |
| `coverage-difference` | Compare with different selections, or different period ranges for a model point | Added and removed coordinates are reported separately and never replaced by zero. | [compare.md](compare.md#coverage-differences) |
| `tolerance-boundary` | A value exactly at the tolerance boundary | Not a deviation. The inequality is strict. | [compare.md](compare.md#tolerance-rule) |
| `non-finite-difference` | Two finite values whose difference is not finite | The comparison is `rejected` with `non_finite_difference` and names the model points. There is no deviation file and no signature table. | [compare.md](compare.md#tolerance-rule) |
| `deviation-file` | A deviation file with a row that does not deviate by the tolerance rule (equal values or a difference within tolerance), a quantity the result does not declare, or a repeated coordinate | Reject with the diagnostic of the rule. | [compare.md](compare.md#deviation-file) |
| `parameter-diff` | Parameter added, removed, or changed | One typed entry per parameter with the old and the new value. | [compare.md](compare.md#parameter-diff) |
| `signature-table` | A compare result with the outcome `compared` | One row per stage and quantity that deviates, in quantity order, derived from the result and its deviation file alone. The same result and file give the same table; without deviation the table has no row. | [compare.md](compare.md#signature-table) |
| `change-combination` | Enabled changes with an unmet prerequisite or a conflict; a set of revisions that is no prefix; a change of the type `revision` in a manifest without `history`; a held kind the engine cannot hold | Reject the combination, or the manifest with `schema_violation`. | [changes.md](changes.md#combination-rules), [changes.md](changes.md#revision-profile) |
| `walk` | Two recorded results of one selection whose revisions lie on one main line | Every state from the older to the newer revision runs; state 0 and state n are checked against the two results; per revision and quantity the walk result states whether it contributes, the signed and the absolute sum of the differences, and the signature row. A state that does not run is a finding and its revisions are carried by the next state that runs. The signed sums add up to the difference of state n and state 0. Different selections give `selection_mismatch`, references that do not fit the history `reference_mismatch`, and nothing runs. | [localise.md](localise.md#walk) |
| `search` | Two recorded results as for a walk, a target of quantities and periods, and optionally a walk folder of the same two records | State 0 and state n run and are checked as the ends of a walk; the history is halved for the target, and only the states needed run. An interval whose ends agree on the target is not divided; an interval of one revision that differs is a contribution in the shape of a walk step; an interval that differs while neither half does gives `interval_not_resolved`. The result states the intervals judged, the contributions, and the runs of both arms with the runs saved; checked against a walk, it names the contributions it missed. A walk that does not attribute every revision gives `walk_not_attributed`, one that does not fit `walk_mismatch`, and nothing runs. Contributions that cancel within one interval are not seen. | [localise.md](localise.md#search) |
| `derived-manifest` | Two results whose release identities name two revisions of one history | One change per revision on the main line after the older revision, in history order, each with the change before it as its only prerequisite; the references no revision fixes and that differ are named as the remainder. The same two results give the same manifest. Revisions that are not on one main line give `unrelated_revisions` and no manifest. | [changes.md](changes.md#derived-manifest) |

## Capability map

Eight capabilities must be implementable from this pack alone. Each is specified
by the sections named here and shown by at least one example.

| Capability | Specified in | Example cases in `examples/index.json` |
|---|---|---|
| Stage identity | [Stage identifier](#stage-identifier); [run.md, Run request](run.md#run-request); [domain/liability_cashflow.md, Stage](domain/liability_cashflow.md#stage) | `full-run`, `wrong-stage` |
| Subset runs | [run.md, Selection](run.md#selection); [run.md, Result completeness](run.md#result-completeness); [domain/liability_cashflow.md, Selection independence](domain/liability_cashflow.md#selection-independence) | `subset-run`, `empty-selection`, `duplicate-selection`, `unknown-model-point`, `unrequested-coordinate` |
| Per-model-point export | [run.md, Per-model-point export](run.md#per-model-point-export); [CSV profile](#csv-profile); [Number format](#number-format); [domain/liability_cashflow.md, Quantities](domain/liability_cashflow.md#quantities) | `csv-export`, `opaque-identity`, `missing-coordinate`, `duplicate-coordinate`, `non-finite-value` |
| Parameter diff | [compare.md, Parameter model](compare.md#parameter-model); [compare.md, Parameter diff](compare.md#parameter-diff); [run.md, Run record](run.md#run-record) | `compare-result`, `run-record` |
| Signature table | [compare.md, Compare result](compare.md#compare-result); [compare.md, Deviation file](compare.md#deviation-file); [compare.md, Signature table](compare.md#signature-table); [Deterministic ordering](#deterministic-ordering) | `signature-table`, `signature-table-tie`, `signature-table-empty`, `compare-result` |
| Derived manifest | [changes.md, Revision profile](changes.md#revision-profile); [changes.md, Derived manifest](changes.md#derived-manifest); [Release identity](#release-identity); [Deterministic ordering](#deterministic-ordering) | `derived-manifest`, `change-manifest` |
| Walk | [localise.md, Walk](localise.md#walk); [localise.md, Contribution](localise.md#contribution); [localise.md, Walk result](localise.md#walk-result); [changes.md, Revision profile](changes.md#revision-profile) | `walk-result`, `authored-revision` |
| Search | [localise.md, Search](localise.md#search); [localise.md, Reader rules of a walk folder](localise.md#reader-rules-of-a-walk-folder); [localise.md, Search result](localise.md#search-result) | `search-result` |

## Examples

All example values are synthetic. They are built to show the rules and come from
no real portfolio and no real calculation.

| Folder | Content |
|---|---|
| [examples/reference/](examples/reference/) | One bundle: a change manifest with text patches, a full run, a subset run with enabled changes, their exports and run records, and a comparison of the two runs with its deviation file and signature table. Beside it `changes.derived.json`, a change manifest derived from a revision history; it stands for itself and no run of the bundle enables it. |
| [examples/opaque-identity/](examples/opaque-identity/) | A run whose release identity has no byte hash, whose time basis is the valuation year, whose model points are output groups, and which exports six of the eleven quantities. |
| [examples/signature-table/](examples/signature-table/) | A comparison of two runs whose signature table shows a tie, a row with both directions, and several model points. |
| [examples/signature-empty/](examples/signature-empty/) | A comparison of a run with itself: a deviation file with the header alone and a signature table without rows. |
| [examples/walk/](examples/walk/) | A walk over the four revisions of `reference/changes.derived.json`: the walk result, the derived manifest, the response and export of every state, and the compare results and deviation files of the steps that contribute. |
| [examples/search/](examples/search/) | A search over the same four revisions for the target `Anzahl Verträge` in period 0, checked against the walk of [examples/walk/](examples/walk/): the search result, the derived manifest, the response and export of every state it ran, the compare result and deviation file of its contribution, and the walk result with the documents it references, copied into `walk/`. |
| [examples/negative/](examples/negative/) | One folder per case that must be rejected, that fails, that ends with an error, or that is incompatible. |

`examples/index.json` lists every case with these members:

| Member | Meaning |
|---|---|
| `id` | Name of the case. |
| `expected` | `accept`, `reject`, `failed` (a run whose outcome is failed), `error` (a run whose outcome is error), or `incompatible` (a comparison without a result). |
| `level` | For `reject` only. `schema`: the file named in `failing` violates its schema. `parse`: it violates the JSON profile. `export_format`: a reader cannot read it under the CSV profile or the reader grammar of the number format. `semantic`: every file is well formed and a reader rule is broken. |
| `diagnostic` | The diagnostic code the case leads to. |
| `matrix_rows` | The rows of the behaviour matrix the case shows. |
| `rules` | The sections that specify the behaviour. |
| `shows` | What to look at. |
| `documents`, `exports` | The files of the case, with the schema of each document. `exports` holds the exports and the deviation files. |
