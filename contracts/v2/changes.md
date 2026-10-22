# Changes contract

Version 1 of the stage contracts, see [README.md](README.md). The changes
contract fixes how the differences between two releases of a stage are listed as
individually switchable changes, and which combinations a run may enable.

Schema: [schemas/changes.schema.json](schemas/changes.schema.json).

## Change manifest

A change manifest lists the changes that can be applied on top of one base release:

```json
{
  "document": "change_manifest",
  "contract_version": "2.0",
  "stage": "liability_cashflow",
  "manifest_id": "changes-n-to-n1",
  "base_release": "N",
  "changes": [ ]
}
```

| Member | Meaning |
|---|---|
| `manifest_id` | The identifier of the manifest. It is opaque. |
| `base_release` | The label of the release the changes apply to. |
| `changes` | The change entries, in application order. |

A manifest is written by an author or derived from a revision history, see
[Derived manifest](#derived-manifest). A derived manifest carries the further
member `history`.

The base release with no change enabled is the old release. Every combination
of changes that the combination rules allow is a release state a run can be
asked for. The manifest does not single out one of them: the caller names the
combination that is the new release by enabling it in the run request.

## Change entry

```json
{
  "id": "chg-claim-expense-rule",
  "class": "code",
  "description": "Read the claim expense per death from the parameter claim_expense instead of the constant 250.",
  "prerequisites": ["chg-claim-expense-parameter"],
  "conflicts": [],
  "realisation": { "type": "text_patch", "format": "unified_diff", "artifact": { "path": "patches/chg-claim-expense-rule.patch", "sha256": "…" } }
}
```

| Member | Meaning |
|---|---|
| `id` | The identifier of the change. It is opaque and unique within the manifest. |
| `class` | `data`, `parameter`, or `code`: what the change alters, as one value or as a list of distinct values. In an authored manifest the author declares it. In a derived manifest it follows from the paths the revision touches, by a mapping the engine declares. |
| `description` | What the change does, for a person. |
| `prerequisites` | The ids of the changes that must be enabled with this one. |
| `conflicts` | The ids of the changes that must not be enabled with this one. |
| `realisation` | How the engine applies the change, see below. |

Classes:

| Class | Alters |
|---|---|
| `data` | Input data of the stage, for example a model point record. |
| `parameter` | A parameter of the parameter inventory, see [compare.md](compare.md#parameter-model). |
| `code` | The calculation logic of the stage. |

A change with a list of classes alters all of them. `"code"` and `["code"]`
say the same. The order of the list carries no meaning to a reader.

Schema assertions: every member is present; `prerequisites` and `conflicts` may
be empty and hold no id twice; a list in `class` holds no class twice. A
manifest without the member `history` holds at least one change, none of its
changes has an empty list in `class`, and none is realised as a `revision`. For a manifest with `history`, see
[Derived manifest](#derived-manifest).

Manifest rules, checked by every reader of a manifest. A manifest that breaks
one is rejected with `invalid_manifest`:

1. No two changes have the same id.
2. Every id in `prerequisites` and `conflicts` is the id of another change of
   the same manifest. A change names itself in neither list.
3. No id is in both lists of one change.
4. Every prerequisite of a change stands before that change in `changes`. This
   also excludes cycles.
5. No change conflicts with one of its own prerequisites, directly or through
   their prerequisites.

## Combination rules

A run request enables a set of changes by id, see [run.md](run.md#run-request).
The engine accepts the set only if all of these hold:

6. Every enabled id is the id of a change in the referenced manifest. Otherwise
   the engine rejects with `unknown_change`.
7. The stage of the manifest is the stage of the request; otherwise the engine
   rejects with `stage_mismatch`. `base_release` is the label of the release in
   the request; otherwise the engine rejects with `invalid_manifest`.
8. **Prerequisites.** For every enabled change, all its prerequisites are
   enabled. Otherwise the engine rejects with `unmet_prerequisite`.
9. **Conflicts.** No enabled change names another enabled change in
   `conflicts`. A conflict holds in both directions, whichever of the two changes
   declares it. Otherwise the engine rejects with `change_conflict`.
10. **Order.** The engine applies the enabled changes in the order of the
    manifest. The order of the ids in the request carries no meaning. For
    changes of the type `revision` the engine applies nothing in sequence: it
    restores the state after the last enabled revision in that order, see
    [Revision profile](#revision-profile).
11. The engine can realise every enabled change. Otherwise it rejects with
    `unsupported_realisation`.

A rejected combination is not run, in whole or in part. The diagnostic names the
changes concerned in `change_ids`.

The empty set is always valid and needs no manifest.

Two changes that the manifest declares neither prerequisite nor conflicting are
independent: each must be applicable with and without the other, and the result
must not depend on which was applied first. The author of the manifest is
responsible for this. Where it does not hold, the author declares a prerequisite
or a conflict.

If an engine can switch changes only in bundles, a bundle is one change entry.
The analysis then cannot separate the changes inside a bundle.

## Realisation

The realisation says how an engine applies the change. It is a typed, extensible
member: `type` names the realisation type, and the other members depend on it.

- Version 1 defines two types. `text_patch`, described below, is the reference
  profile. `revision` realises a change as one revision of a versioned model
  state, see [Revision profile](#revision-profile). No engine is required to
  support either.
- An engine with another mechanism declares its own type name and its own
  members, for example a named switch inside the engine:

  ```json
  { "type": "engine_switch", "switch": "RC-2041" }
  ```

  The schema accepts any type name that matches `^[a-z][a-z0-9_]*$`, with any
  further members. Only the types `text_patch` and `revision` have a closed
  shape.
- A realisation member that points to a stored file uses an artifact reference
  with a byte hash, see [README.md](README.md#artifact-references-and-byte-hashes).
- Everything outside `realisation` is engine-neutral. A reader that cannot apply
  a change can still read its id, class, description, prerequisites, and conflicts.

## Text-patch reference profile

The type `text_patch` realises a change as one patch file against a release that
is stored as text files in a folder.

```json
{ "type": "text_patch", "format": "unified_diff", "artifact": { "path": "patches/chg-lapse-year-1-down.patch", "sha256": "…" } }
```

```
--- lapse_table.csv
+++ lapse_table.csv
@@ -1,5 +1,5 @@
 policy_year,lapse_rate
-1,0.06
+1,0.05
 2,0.04
 3,0.04
 4,0.03
```

- `format` is `unified_diff`, the only format of version 2.
- The patch file is UTF-8 with line feeds. It may change several files.
- File names in the patch headers are relative to the root folder of the
  release, with forward slashes, and are used as written.
- A patch only changes existing text files. It creates, deletes, and renames none.
- The enabled patches are applied in manifest order to a copy of the base
  release. The base release itself is never altered.
- A hunk applies only where its context lines and removed lines match exactly.
  A shifted line number is allowed; an inexact match is not. If a hunk of an
  enabled patch does not apply, the engine rejects the request with
  `invalid_manifest` and runs nothing.
- The class of a text patch is the declared class. A patch to a data file is a
  `data` change, a patch to a parameter table a `parameter` change, and a patch
  to calculation logic a `code` change. One change has one class; a patch that
  would need two is split into two changes linked by a prerequisite.

## Revision profile

The type `revision` realises a change as one revision of a versioned model
state. The engine restores the state after that revision itself.

```json
{ "type": "revision", "source": "git", "revision": "9f2c41d07b6e5a3c8d1f0e2b4a6c8e0f1a3b5c7d" }
```

- `source` names the kind of history. Version 1 defines `git`.
- `revision` is the full identifier of the revision in that history. It is
  opaque to every reader but the engine.
- A change of this type stands only in a manifest with `history`, see
  [Derived manifest](#derived-manifest). There each change names the change
  before it as its only prerequisite, so by rule 8 a change of this type is
  enabled only together with all changes before it: the enabled set is a prefix
  of the manifest. A set that skips a revision is rejected with
  `unmet_prerequisite`. Revisions and text patches never stand in one manifest.
- The state of a prefix is the state after its last revision. The state of the
  empty prefix is the base release, the release of the request.
- The engine applies nothing in sequence; it restores the last revision.
- A revision is never split. It carries every class it touches, so `class` may
  be a list. In a derived manifest a revision that touches nothing the engine
  maps to a class has the empty list.

A revision fixes the kinds of release reference the engine declares in
`determines`, see [Derived manifest](#derived-manifest). By default the state
of a prefix takes all of them from its last revision. The request may name
kinds in `changes.hold`, see [run.md](run.md#run-request): the engine then takes
these kinds from the release of the request instead, and the effect of the
revisions on them is not part of the state. An engine declares which kinds it
can hold. The walk of [localise.md](localise.md#held-and-moving-kinds) holds an
input both results were calculated on.

Reader rule for the engine, after the combination rules:

12. **Held kinds.** Every kind in `changes.hold` is a kind the engine can hold,
    and at least one change of the type `revision` is enabled. Otherwise the
    engine rejects with `invalid_hold`.

Schema assertions: the realisation holds `type`, `source`, and `revision` and
no other member; a manifest without `history` holds no change of this type.

## Derived manifest

A manifest can be derived from the history between two revisions instead of
being written by an author. The two revisions are those of two results: the
release identities of two run records name them.

```json
{
  "document": "change_manifest",
  "contract_version": "2.0",
  "stage": "liability_cashflow",
  "manifest_id": "history-41ab…-9f2c…",
  "base_release": "N",
  "history": {
    "source": "git",
    "from": "41ab…",
    "to": "9f2c…",
    "determines": ["code_state", "input_data", "parameter_set"],
    "remainder": [
      {
        "kind": "engine_version",
        "from": [ { "kind": "engine_version", "value": "12.4.1" } ],
        "to": [ { "kind": "engine_version", "value": "12.5.0" } ]
      }
    ]
  },
  "changes": [ "…" ]
}
```

The block leaves the change entries out: `"…"` stands for one entry per
revision after `41ab…` up to `9f2c…`. `changes` is empty only when `from` and
`to` are one revision.

The changes:

- The older revision must lie on the main line of the newer one. Otherwise the
  manifest cannot be derived and the reader reports `unrelated_revisions`. This
  also holds when the two revisions are given in the wrong order.
- The changes are the revisions on the main line after the older revision, up
  to and including the newer one, in the order of the history. The older
  revision itself is the base release and is no change.
- In a history of the source `git` the main line of a revision is the chain of
  first parents. A branch that was merged is one change: the merge. The
  analysis cannot separate the revisions inside it. A revision that is an
  ancestor of the newer one only through a merged branch does not lie on its
  main line.
- Each change names the change before it as its only prerequisite; the first
  names none. `conflicts` is empty. By rule 8 the enabled set of a run is then a
  prefix of the manifest.
- `id` is the identifier of the revision and `description` its log message,
  whole and without the line breaks at its end. A message that is empty is
  replaced by the identifier, and bytes that are not UTF-8 by U+FFFD. The
  message is the author's claim, not a finding.
- `realisation` has the type `revision`, with the `source` of `history` and the
  identifier of the revision.
- `class` is always a list, in the order `data`, `parameter`, `code`. It holds
  the class of every path the revision adds, removes, or alters against the
  revision before it on the main line; for a merge that is its first parent. A
  file that is moved counts with its old and its new path. The engine declares
  the mapping from paths to classes.
- When both results name one revision, the manifest holds no change.
- `base_release` is the label of the release of the older result.
- `manifest_id` is `history-<from>-<to>`, with the two identifiers of
  `history` in full.

A reader of a manifest with `history` checks the chain as well as rules 1 to 5:
each change names the change before it as its only prerequisite and the first
names none; the realisation of each change names its own `id` and the `source`
of `history`; the last change is the revision `to`; and the manifest holds no
change only when `from` and `to` are one revision. A manifest that breaks one
of these is rejected with `invalid_manifest`.

The member `history`:

| Member | Meaning |
|---|---|
| `source` | The kind of history, as in the revision profile. |
| `from` | The identifier of the older revision. |
| `to` | The identifier of the newer revision. |
| `determines` | The kinds of release reference a revision fixes, ordered by name. The engine declares them. References of other kinds come from the caller and stay the same for every state. |
| `remainder` | The kinds of release reference that a revision does not fix and that differ between the two results, ordered by kind. They are named, not attributed. |

An entry of `remainder` holds `kind`, `from`, and `to`. `from` lists the
complete references of that kind in the release identity of the older result
and `to` those of the newer one, each ordered by `value`, then by the byte
hash of the artifact, then by the path of the artifact; a reference without an
artifact stands before one with the same value. A list is empty when the identity holds no reference of
the kind. A kind is in the remainder when no revision fixes it and the two
lists differ.

A writer yields the same manifest for the same two results, byte for byte: it
orders every list as stated here and writes no timestamp and no path. The
changes depend on the two revisions alone. `base_release` and `remainder` come
from the two results.

A caller may supply several sets of references that a revision does not fix,
each valid from a named revision. The revision at the boundary and the change
of the set are one change. Version 1 allows this and does not yet fix its
form: no member of a manifest names such a set or the revision it is valid
from, and no reference implementation exists.

There is no document for a manifest that cannot be derived. The reader reports
the diagnostic. Beside `unrelated_revisions`, two results that name different
stages are refused with `stage_mismatch`, and a revision that the history at
hand does not hold with `unknown_reference`.

Schema assertions for a manifest with `history`: `changes` may be empty; every
change has a list in `class`, at most one prerequisite, no conflict, and a
realisation of the type `revision`; `determines` holds no kind twice.
