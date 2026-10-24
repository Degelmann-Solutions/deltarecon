# Compare contract

Version 3 of the stage contracts, see [README.md](README.md). The compare
contract fixes how the results of two runs of one stage are compared coordinate
by coordinate, how the deviations are condensed into a signature table, how the
parameters of the two runs are compared, and when a run counts as reproduced.

Schema: [schemas/compare.schema.json](schemas/compare.schema.json).

The two runs are called left and right. By convention the left run is the older
or the recorded one. The output is the [compare result](#compare-result), the
[deviation file](#deviation-file) that lists every deviating coordinate, and the
[signature table](#signature-table) that condenses it.

## Compare request

```json
{
  "document": "compare_request",
  "contract_version": "3.0",
  "stage": "liability_cashflow",
  "compare_id": "compare-n-full-vs-subset-changes",
  "left": {
    "response": { "path": "full-run.response.json", "sha256": "…" },
    "run_record": { "path": "full-run.run-record.json", "sha256": "…" }
  },
  "right": {
    "response": { "path": "subset-run.response.json", "sha256": "…" },
    "run_record": { "path": "subset-run.run-record.json", "sha256": "…" }
  },
  "tolerance": { "per_quantity": { "Kosten 2. Ordnung ohne Provisionen": { "upper": { "abs_tol": 0.25, "rel_tol": 0 }, "lower": { "abs_tol": 0, "rel_tol": 0 }, "derivation": "…" } } }
}
```

| Member | Meaning |
|---|---|
| `compare_id` | The caller's identifier of this comparison. It is opaque. |
| `left.response`, `right.response` | The run responses of the two runs. Each references its export. |
| `left.run_record`, `right.run_record` | The run records of the two runs. Optional. The parameter diff is made when both are given. |
| `tolerance.per_quantity` | The tolerance profile: an object from quantity name to the tolerance of that quantity. It may be empty. |
| `upper`, `lower` | The two bounds of one quantity, each a pair `abs_tol`, `rel_tol`. `upper` limits how far the right value may lie above the left one, `lower` how far below. |
| `decimals` | Optional. The defined number of decimal places of the quantity. Both values are rounded to it before they are compared. |
| `derivation` | Where the decimal places and the widths of the bounds come from, as text or as a reference to a document. Required as soon as the entry rounds or a bound is above zero. |

The tolerance is a profile per quantity, not a setting for the whole
comparison. There is no general tolerance and no default: a quantity without an
entry is compared exactly. A tolerance states what the comparison deliberately
does not see, so every rounding and every bound above zero comes with its
derivation.

The first choice for a quantity with defined decimal places is to round and then
compare exactly: `decimals` with both bounds at zero. A bound above zero is for
what remains after that.

Schema assertions: `tolerance.per_quantity` is present and may be empty. Each
entry has `upper` and `lower`, each with both parts, and no part is negative.
`decimals`, when present, is an integer from 0 to 15. An entry with `decimals`
or with a part above zero has a non-empty `derivation`.

## Compatibility

Before any value is compared, the reader checks that the two runs can be compared.

Reader rules:

1. Both responses have the outcome `succeeded` and pass rules 7 to 13 of
   [run.md](run.md#result-completeness): the rules that need only the response
   and its export. Rule 10 is applied to the selection that the response itself
   repeats. The run requests are not part of a comparison, so rule 6, which
   needs the request, is not applied. Otherwise the comparison is
   `rejected` with the diagnostic of the broken rule. A response that has not
   succeeded is rejected with the code its outcome implies: `model_point_failed`
   for `failed`, and the code of its first diagnostic for `rejected` and
   `error`. For `error` the message says that the run has ended with an error.
2. Both responses and the request name the same stage. Otherwise the outcome is
   `incompatible` with `stage_mismatch`.
3. Both responses declare the same time basis identifier. Otherwise the outcome
   is `incompatible` with `time_basis_mismatch`. A reader never converts periods
   from one basis to another.
4. Both responses declare the same quantity names. Otherwise the outcome is
   `incompatible` with `quantity_mismatch`.
5. Both responses declare the same unit for every quantity. Otherwise the
   outcome is `incompatible` with `unit_mismatch`. A reader never converts units.

An incompatible or rejected comparison has no comparison result: no deviation
file, no coverage lists, and no parameter diff.

```json
{
  "document": "compare_result",
  "contract_version": "3.0",
  "stage": "liability_cashflow",
  "compare_id": "compare-unit-mismatch",
  "outcome": "incompatible",
  "diagnostics": [ { "code": "unit_mismatch", "message": "The left run declares amounts in EUR and the right run in kEUR." } ]
}
```

The release identities, the enabled changes, and the selections of the two runs
may differ. That is what a comparison is for.

## Alignment

Results are aligned by coordinate: stage, model point id, period, and quantity.

- The stage is the same on both sides by rule 2.
- Model point ids are equal when the strings are equal, code point by code point.
  There is no trimming, no case folding, and no numeric reading.
- Periods are equal when the integers are equal. They are indices on the same
  time basis by rule 3.
- Quantities are equal when the names are equal.

A coordinate present on both sides is a common coordinate. Only common
coordinates are compared. The order of rows in the exports carries no meaning.

A model point id must name the same result unit in both runs. If a change
regroups contracts into other model points, the old and the new units appear as
removed and added coordinates, not as deviations.

## Coverage differences

The two runs may cover different coordinates: the selections differ, a model
point exists in one release only, or the period range of a model point differs.

- A coordinate present only on the right side is **added**.
- A coordinate present only on the left side is **removed**.
- Added and removed coordinates are reported in their own lists, as period
  ranges per model point. A range covers every quantity for each of its periods.
  Each list holds the longest contiguous ranges, ordered by model point id and
  first period.
- An absent value is never replaced by zero, and an added or removed coordinate
  is never reported as a deviation.
- A model point with only added or removed coordinates is not a deviating model point.

## Tolerance rule

A common coordinate has a left and a right value. If the entry of its quantity
has `decimals`, both values are first rounded to that number of decimal places:

- Rounding is commercial: half away from zero. `0.125` gives `0.13` at two
  places, `-0.125` gives `-0.13`.
- It is applied to the decimal number that the writer form of the value denotes,
  see [README.md](README.md#number-format), not to its binary expansion. `2.675`
  gives `2.68` at two places.
- The rounded decimal number is read as the nearest binary64 value.
- Two values that lie close together on both sides of a rounding step still
  round apart: `0.6949` and `0.6951` give `0.69` and `0.70`. Rounding does not
  hide that; a bound above zero would.

With `left` and `right` as the values after this step, let

```
d = right - left
m = max(abs(left), abs(right))
```

The coordinate deviates when

```
 d > max(upper.abs_tol, upper.rel_tol * m)    or
-d > max(lower.abs_tol, lower.rel_tol * m)
```

- `upper` and `lower` are the bounds of the coordinate's quantity in
  `per_quantity`. A quantity without an entry is not rounded and has all four
  parts at zero.
- The two bounds are set separately, so the rule is not symmetric: exchanging
  left and right exchanges the roles of `upper` and `lower`. A profile with
  equal bounds gives a symmetric comparison.
- Each inequality is strict. A difference exactly equal to its bound is not a deviation.
- With all parts at zero, every difference is a deviation and equal values are not.
- The values and the tolerances are binary64 numbers, and the expressions are
  evaluated in binary64 arithmetic as written.

A model point deviates when at least one of its common coordinates deviates.

Reader rules:

6. Every name in `per_quantity` is a quantity that the two runs declare.
   Otherwise the comparison is `rejected` with `unknown_quantity`. The schema
   cannot check this, because the names are declared in the responses.

After rule 6 and before any value is rounded or judged, the reader checks that
every difference can be formed. For each common coordinate whose left and right
values differ, `right - left` of the exported values, evaluated in binary64
arithmetic, is a finite number. Two finite values can still give a non-finite
difference, for example `-1e308` and `1e308`. Otherwise the comparison is
`rejected` with `non_finite_difference`, and the diagnostic names every model
point with such a coordinate in `model_point_ids`. The compare result and its
run record are written; there is no deviation file and no signature table.

Worked values with this profile, as in the reference example:

| Quantity | Upper bound | Lower bound |
|---|---|---|
| `Bruttobeitrag` | relative 0.001 | relative 0.001 |
| `Kosten 2. Ordnung ohne Provisionen` | absolute 0.25 | zero |
| `Netto-Cashflow` | zero | absolute 0.25 |
| `Provisionen` | zero, after rounding to 2 places | zero, after rounding to 2 places |
| every other quantity | no entry: exact | no entry: exact |

| Quantity | Left | Right | d | Bound that applies | Deviation |
|---|---|---|---|---|---|
| `Kosten 2. Ordnung ohne Provisionen` | 100 | 100.25 | 0.25 | upper: 0.25 | No, exactly at the bound. |
| `Kosten 2. Ordnung ohne Provisionen` | 100.25 | 100 | -0.25 | lower: 0 | Yes. The same two values, exchanged. |
| `Netto-Cashflow` | 380 | 379.75 | -0.25 | lower: 0.25 | No, exactly at the bound. |
| `Bruttobeitrag` | 1200 | 1201 | 1 | upper: 0.001 * 1201 = 1.201 | No, within the relative bound. |
| `Beitragsverrechnung` | 400 | 401 | 1 | exact | Yes. |
| `garantierte Todesfallleistung` | 30 | 36 | 6 | exact | Yes. |
| `Anzahl Verträge` | 0.99 | 0.9905 | 0.0005 | exact | Yes. |
| `Provisionen` | 0.6972 | 0.6974 | 0 after rounding: 0.7 and 0.7 | exact | No. |
| `Provisionen` | 0.6949 | 0.6951 | 0.01 after rounding: 0.69 and 0.7 | exact | Yes. The values round apart. |

The second and the last row are not part of the reference example; they show the
asymmetry and a rounding step.

Not in version 3: a tolerance per tariff, per model point, or per period, and a
store of explained, accepted deviations per coordinate that a later comparison
subtracts instead of tolerating them. Version 3 sets a tolerance per quantity
only.

## Compare result

```json
{
  "document": "compare_result",
  "contract_version": "3.0",
  "stage": "liability_cashflow",
  "compare_id": "compare-n-full-vs-subset-changes",
  "outcome": "compared",
  "left": { "run_id": "run-n-full", "release_label": "N" },
  "right": { "run_id": "run-n-subset-changes", "release_label": "N" },
  "tolerance": { "per_quantity": { "Kosten 2. Ordnung ohne Provisionen": { "upper": { "abs_tol": 0.25, "rel_tol": 0 }, "lower": { "abs_tol": 0, "rel_tol": 0 }, "derivation": "…" } } },
  "time_basis": { "id": "policy_month" },
  "quantities": [ { "name": "Anzahl Verträge", "unit": "policies" }, { "name": "Bruttobeitrag", "unit": "EUR" } ],
  "compared_coordinates": 50,
  "deviations": { "path": "compare.deviations.csv", "sha256": "…" },
  "deviating_model_points": ["MP-0001"],
  "added": [ { "model_point_id": "MP-0002", "first_period": 146, "last_period": 146 } ],
  "removed": [ { "model_point_id": "MP-0003", "first_period": 0, "last_period": 1 } ],
  "parameter_diff": [ ]
}
```

| Member | Meaning |
|---|---|
| `outcome` | `compared`, `incompatible`, or `rejected`. |
| `left`, `right` | The run id and the release label of each side. |
| `engine_version` | Optional. The engine versions of the two runs, `{ "left": …, "right": … }`, when they differ. See below. |
| `tolerance` | The `tolerance` member of the request, unchanged, with every derivation. |
| `time_basis`, `quantities` | The declarations the two runs share. |
| `compared_coordinates` | The number of common coordinates. |
| `deviations` | The [deviation file](#deviation-file), by artifact reference with its byte hash. |
| `deviating_model_points` | The ids of the model points with at least one deviation. |
| `added`, `removed` | The coverage differences. |
| `parameter_diff` | The parameter diff. Present when both run records were given. |

A result with the outcome `compared` always references a deviation file, also
when nothing deviates. A result with another outcome has none.

`engine_version` is present only when both run records are given and each
holds exactly one release reference of the kind `engine_version`, and the two
values differ. It then holds the value of each, unchanged. It may appear in a
result with the outcome `compared` or `rejected`. It is information for a
person: a comparison across engine versions is allowed, and the member does not
change the outcome.

The comparison reports **no deviation** when the outcome is `compared`, the
deviation file holds no row, and `added` and `removed` are both empty.

## Deviation file

The deviation file lists every deviating coordinate of one comparison, one row
per coordinate, under the [CSV profile](README.md#csv-profile):

```
model_point_id,period,quantity,left,right
MP-0001,0,Beitragsverrechnung,400,401
MP-0001,1,garantierte Todesfallleistung,30,36
```

- The header is exactly `model_point_id,period,quantity,left,right`.
- Each row holds one coordinate whose values deviate by the
  [tolerance rule](#tolerance-rule): its model point id, period, and quantity
  name, and the left and the right value as exported, before any rounding.
- The file is complete: it holds every deviating coordinate and no other. A
  model point without a deviation has no row, and a coordinate within its
  tolerance has none. When nothing deviates the file holds the header alone.
- Periods and values are written in the writer form of the
  [number format](README.md#number-format). Rows are ordered as stated in
  [README.md](README.md#deterministic-ordering): by model point id, then by
  period, then in the order of `quantities` of the compare result.
- The file is written only for a comparison with the outcome `compared`.

Reader rules, for a compare result with the outcome `compared` and its
deviation file:

8. The deviation file exists and has the stated hash. Otherwise the reader
   rejects with `artifact_missing` or `artifact_hash_mismatch`.
9. The file can be read under the CSV profile and the reader grammar of the
   number format, its header is the one stated above, and every model point id
   is one the schema of an id allows. Otherwise the reader rejects with
   `export_format`, `number_format`, or `non_finite_value`.
10. Every quantity of a row is a quantity the compare result declares in
    `quantities`. Otherwise the reader rejects with `unknown_quantity`.
11. No coordinate occurs on two rows. Otherwise the reader rejects with
    `duplicate_coordinate`.
12. The rows stand in the order stated above. Otherwise the reader rejects with
    `export_format`.
13. Every row deviates by the [tolerance rule](#tolerance-rule) under the
    `tolerance` of the compare result. A row that does not, because its values
    are equal or differ within the tolerance, is rejected with
    `not_a_deviation`.

## Signature table

The signature table condenses the deviation file of one compare result: one row
per stage and quantity that deviates. It is a document of its own, with the type
`signature_table`, and not a member of the compare result.

The example is shortened to one of the four rows of
[examples/reference/compare.signature-table.json](examples/reference/compare.signature-table.json).
[examples/signature-table/](examples/signature-table/) shows a table with a tie,
a row with both directions, and several model points, and
[examples/signature-empty/](examples/signature-empty/) the table of a
comparison without deviation.

```json
{
  "document": "signature_table",
  "contract_version": "3.0",
  "stage": "liability_cashflow",
  "compare_id": "compare-n-full-vs-subset-changes",
  "left": { "run_id": "run-n-full", "release_label": "N" },
  "right": { "run_id": "run-n-subset-changes", "release_label": "N" },
  "rows": [
    {
      "stage": "liability_cashflow",
      "quantity": "Netto-Cashflow",
      "deviating_model_points": 1,
      "deviating_coordinates": 1,
      "right_above_left": 0,
      "right_below_left": 1,
      "first_period": 1,
      "last_period": 1,
      "largest_decrease": { "model_point_id": "MP-0001", "period": 1, "absolute": -6, "relative": -0.15584415584415584 }
    }
  ]
}
```

| Member | Meaning |
|---|---|
| `document`, `contract_version` | The document type `signature_table` and the contract version of the compare result. |
| `stage`, `compare_id`, `left`, `right` | Repeated from the compare result, unchanged. |
| `rows` | One row per quantity with at least one deviation. It is empty when the deviation file holds no row. |
| `stage` of a row | The stage identifier, equal to `stage` of the table. Every row carries it. |
| `quantity` | The quantity of the row. |
| `deviating_model_points` | The number of model points with at least one deviation of this quantity. |
| `deviating_coordinates` | The number of deviations of this quantity. |
| `right_above_left`, `right_below_left` | The number of these deviations whose right value lies above the left one, and below it. The two add up to `deviating_coordinates`. |
| `first_period`, `last_period` | The lowest and the highest period among these deviations. |
| `largest_increase` | The deviation with the greatest `absolute` among those with right above left. Present when `right_above_left` is above zero. |
| `largest_decrease` | The deviation with the least `absolute` among those with right below left. Present when `right_below_left` is above zero. |

`largest_increase` and `largest_decrease` each name their coordinate by
`model_point_id` and `period` and hold two numbers:

```
absolute = right - left
relative = absolute / max(abs(left), abs(right))
```

- `left` and `right` are the values of the deviation as the deviation file
  holds them: as exported, before any rounding. The expressions are evaluated in
  binary64 arithmetic as written.
- `absolute` is signed: above zero in `largest_increase`, below zero in
  `largest_decrease`. `relative` has the same sign.
- `largest_increase` names the deviation with the greatest `absolute`,
  `largest_decrease` the one with the least. Of several deviations with the
  same `absolute`, the one with the lowest model point id by Unicode code point
  is named, and of those the one with the lowest period. The choice does not
  depend on the order in which the deviations are stored.
- Whether right lies above or below left is judged on the same exported values.
  Rounding keeps the order of two values, so the direction is that of the
  difference the tolerance rule judged.

The table is a function of one compare result and its deviation file:

- It is derived from a result with the outcome `compared` and the deviation
  file it references, and from nothing else: not from the exports, the
  responses, or another comparison. An `incompatible` or `rejected` comparison
  has no signature table.
- It is written for every comparison with the outcome `compared`, with no rows
  when nothing deviates.
- It holds no timestamp and nothing else that differs between two derivations.
  A writer orders the rows as stated in
  [README.md](README.md#deterministic-ordering), so that the same compare
  result and deviation file give the same table: two derivations are equal as JSON values. Equal
  bytes hold for one writer, which writes the same value in the same way; there
  is no canonical JSON form, see [README.md](README.md#json-profile).
- Added and removed coordinates are not deviations and give no row.

Schema assertions: all members of the table and the first eight members of a row
are present; the counts are integers, `deviating_model_points` and
`deviating_coordinates` at least one; `largest_increase` is present exactly when
`right_above_left` is above zero, and `largest_decrease` exactly when
`right_below_left` is above zero.

Not in version 3: groups of model points that show the same pattern, and a
judgement whether two signature tables show the same pattern. Sums of the
differences per quantity are part of the walk result, see
[localise.md](localise.md#contribution).

## Parameter model

A parameter inventory lists every parameter of one run. It is part of the run
record, see [run.md](run.md#run-record). A parameter has a name, unique within
the inventory, and one of two types.

A **scalar** has one value: a number, a string, or a boolean.

```json
{ "name": "valuation_rate", "type": "scalar", "value": 0.01 }
```

A **keyed table** has named key columns, named value columns, and rows. Each row
has one key and one value per column, in column order. No two rows have the same key.

```json
{
  "name": "lapse_table",
  "type": "keyed_table",
  "key_columns": ["policy_year"],
  "value_columns": ["lapse_rate"],
  "rows": [
    { "key": [1], "values": [0.06] },
    { "key": [2], "values": [0.04] }
  ]
}
```

A table with several key columns, such as a mortality table by sex and age, has
one key element per key column. An engine that holds a parameter in another form
maps it to one of the two types and uses the same mapping in every run.

Reader rules:

7. No two parameters of an inventory have the same name, and no two rows of a
   table have the same key. Every row has as many key elements as key columns
   and as many values as value columns. Otherwise the reader rejects the
   inventory with `invalid_inventory`.

## Parameter diff

The parameter diff compares the inventories of the left and the right run. It is
exact: no tolerance applies.

Two values are equal when they have the same type and the same content: numbers
when they are the same binary64 value, strings when they are equal code point by
code point, booleans when they are the same. A number and a string are never
equal. Keys are compared in the same way, element by element.

The diff has one entry per parameter that differs, ordered by name, and no entry
for a parameter that is equal on both sides.

| State | Entry |
|---|---|
| Parameter only in the right inventory | `added`, with the whole parameter as `new`. |
| Parameter only in the left inventory | `removed`, with the whole parameter as `old`. |
| Scalar on both sides with different values | `changed`, type `scalar`, with `old` and `new`. |
| Keyed table on both sides, same key and value columns, different rows | `changed`, type `keyed_table`, with one row entry per differing key. |
| Different type, or keyed tables with different key or value columns | `replaced`, with the whole parameter as `old` and as `new`. |

A row entry of a changed table is `added` with the `new` values, `removed` with
the `old` values, or `changed` with both. Row entries are ordered by key.

```json
[
  { "name": "claim_expense", "change": "added", "new": { "name": "claim_expense", "type": "scalar", "value": 300 } },
  { "name": "lapse_table", "change": "changed", "type": "keyed_table",
    "rows": [ { "key": [1], "change": "changed", "old": [0.06], "new": [0.05] } ] },
  { "name": "legacy_loading", "change": "removed", "old": { "name": "legacy_loading", "type": "scalar", "value": 0 } },
  { "name": "valuation_rate", "change": "changed", "type": "scalar", "old": 0.01, "new": 0.0125 }
]
```

The parameter diff is independent of the result comparison. It is made also when
the results show no deviation, and it does not change the outcome.

## Replay criterion

A run that has succeeded is reproduced when a comparison of the recorded
outputs, as the left side, with the outputs of the repeated run, as the right
side, reports no deviation.

- The comparison follows this contract, and the caller supplies its tolerances.
- An engine that repeats its own results exactly is replayed with an empty
  tolerance profile, or with every part at zero and no rounding. The run is then
  **reproduced exactly**.
- Where the quantities have defined decimal places, the replay rounds to them
  and compares exactly: `decimals` with both bounds at zero. The run is then
  **reproduced at the stated decimal places**.
- An engine may not repeat its own results exactly, for example where the order
  of a summation is not fixed. Its replay sets at least one bound above
  zero in `per_quantity`, with its derivation, and the run is then
  **reproduced within the stated tolerances**. These tolerances bound the
  variation between two runs of the same release state.
- A statement that a run is reproduced names the decimal places and the
  tolerances it rests on. The
  compare result carries them unchanged, and the run record of the comparison
  lists that result.
- Except for a run with the outcome `error`, byte hashes do not decide reproduction. A hash covers the exact stored bytes
  of one file; a repeated run may write other bytes for the same values.
- A recorded run with the outcome `error` has no export to compare. It is
  reproduced exactly when the repeated run writes a response byte for byte
  equal to the recorded one, and not reproduced otherwise.
- The repeated run uses the release identity that the run record holds, and
  the enabled changes and the selection of the request that the record lists.

This version states the criterion only. It defines no replay procedure.
