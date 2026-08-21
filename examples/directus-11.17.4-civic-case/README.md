# Directus 11.17.4 synthetic civic-case canary

This directory is one frozen, synthetic-only custom API-response capture from a
fresh Directus 11.17.4 sandbox. It is evidence for one exact adapter profile,
not a general Directus export claim. The custom capture bundle has not been
hand-normalized into an ExitDrill export; a profile-specific normalizer must do
that outside the evaluator.

The `native/` path is an internal source-side label for bytes before ExitDrill
normalization; it does not identify a vendor-native Directus export format.

## Capture boundary

The lab used the official image pinned by digest:

```text
directus/directus@sha256:eb326f679ae847c0a776f93b972761dc2ebe84980e0b9d274a6bc31cd62809f7
```

The resolved application version was `11.17.4`. The container used SQLite and
local file storage inside an ephemeral Docker lab. Its Docker network was
internal (no external route), port 8055 was bound only to `127.0.0.1`, and the
capture program rejects every HTTP origin except `http://127.0.0.1:8055` and
rejects redirects. Only invented people, cases, text attachments, a policy, and
two case-creation events were present. Production data is prohibited.

The capture used documented first-party REST surfaces:

- `POST /auth/login`
- `GET` and `POST /collections`, `POST /fields/:collection`, and
  `POST /relations`
- `GET` and `POST /items/:collection`
- `GET` and `POST /files`, plus `GET /assets/:id`
- `GET` and `POST /policies` and `/permissions`
- `GET /activity`
- `GET /schema/snapshot`

The capture program is [`../../scripts/directus_canary_lab.mjs`](../../scripts/directus_canary_lab.mjs).
It intentionally refuses a non-fresh database or an existing fixed capture
directory. Supply admin credentials through `ADMIN_EMAIL` and `ADMIN_PASSWORD`;
the program never prints them or response bodies. Run it only against a
disposable, no-egress sandbox.

Official references:

- [Directus API overview](https://directus.com/docs/api)
- [Global API query parameters](https://directus.com/docs/guides/connect/query-parameters)
- [Files API](https://directus.com/docs/api/files) and
  [asset access](https://directus.com/docs/api/assets)
- [Policies API](https://directus.com/docs/api/policies)
- [Permissions API](https://directus.com/docs/api/permissions)
- [Schema snapshot API](https://directus.com/docs/api/schema)
- [Official self-hosting guide](https://directus.com/docs/self-hosting/deploying)
- [Directus v11.17.4 release](https://github.com/directus/directus/releases/tag/v11.17.4)
- [Directus v11.17.4 license text](https://github.com/directus/directus/blob/v11.17.4/license)

## API-response capture evidence

`native/capture-manifest.json` records each captured response or attachment by
relative path, exact byte count, and SHA-256. `bundle_sha256` is the SHA-256 of
the fixture program's recursively canonical JSON encoding of that sorted file
metadata array. The manifest itself is outside that digest.

The bundle contains:

| Surface | Captured evidence |
|---|---:|
| People items | 3 |
| Case items | 2 |
| Case-person junction items | 2 |
| Attachment metadata and bytes | 2 each |
| Policy records | 1 |
| Permission records | 2 |
| Case-create activity records | 2 |
| Schema snapshots | 1 |

The adjacent `baseline.json` is a separately authored assertion for this
controlled scenario. It declares complete coverage across all five ExitDrill
dimensions. Its synthetic `captured_at` is after both captured audit timestamps
and before the capture manifest's `exported_at`; none of those timestamps are
authenticated.

## Profile normalization contract

The accepted profile is `directus-11.17.4-civic-case/v0.1`:

- the exact captured `schema.json` bytes are pinned by SHA-256 in the adapter,
  in addition to the manifest inventory and structural schema checks;
- integer source IDs become decimal strings;
- `exitdrill_people` rows become `person` entities and SQLite `0`/`1` boolean
  values become JSON booleans;
- `exitdrill_cases` rows become `case` entities, retaining `status`, `priority`,
  and the document UUID as baseline-declared critical values;
- permission collection names become `directus_collection_scope` technical
  entities whose only required field is the exact `collection` name;
- junction rows become `assigned_to` relationships from `case` to `person`;
- each document UUID becomes an attachment owned by its case, with bytes read
  only from the corresponding `native/assets/<uuid>.txt` path;
- policy UUID `33333333-3333-4333-8333-333333333333` becomes principal ID
  `policy:33333333-3333-4333-8333-333333333333`; and
- activity IDs become event IDs `directus_activity:<decimal-id>`, collection
  `exitdrill_cases` maps to object type `case`, and source action and timestamp
  are retained exactly.

Permission roles preserve the action plus a digest of the semantics not
representable in ExitDrill's four-string permission tuple. Canonical JSON sorts
object keys recursively, emits no insignificant whitespace, and preserves array
order. The digest input has exactly these keys:

```text
{action,fields,permissions,presets,validation}
```

The role is `<action>:<sha256(canonical-input)>`. For this bundle:

| Scope | Canonical semantic SHA-256 | Resulting role |
|---|---|---|
| `exitdrill_cases` | `0fcaa4ece823393f4e5ccfc2426e26859693cf80052aaf4b8b78c7ceb3e45a8c` | `read:0fcaa4ece823393f4e5ccfc2426e26859693cf80052aaf4b8b78c7ceb3e45a8c` |
| `exitdrill_people` | `ce05c47ea42741b5272eccf39dd56d55f7e8d373dbff4c9d6da220266215a38b` | `read:ce05c47ea42741b5272eccf39dd56d55f7e8d373dbff4c9d6da220266215a38b` |

Keeping permission semantics out of the collection-scope entities ensures that
a permission-only mutation fails the permissions dimension without also
creating an entity-value failure.

## Adversarial derivative and observed loss signals

`../../scripts/build_directus_lossy_canary.py` builds one deterministic,
equal-count adversarial derivative of this profile. It is **not committed**:
`../../scripts/check_directus_canary_demo.py` generates it fresh into a
`TemporaryDirectory` on every run, verifies it against this directory's
committed `capture-manifest.json` bundle digest first, and discards it when
the process exits. Nothing under this directory holds lossy bytes.

The derivative applies exactly six mutations, one per source file, and each
is required to leave every row and file count unchanged --
`build_lossy_canary` raises `adversarial derivative changed row or file
counts` if it does not:

| Mutation | What it changes |
|---|---|
| `critical_field_value` | The second case's `status` flips from `open` to `closed`. |
| `unreferenced_identity_churn` | The third person's `id` changes from `3` to `4`, orphaning any reference to the old id. |
| `relationship_rewire` | The first case-person link's `person_id` changes from `1` to `2`. |
| `permission_field_collapse` | The case permission's `fields` list drops `document`. |
| `audit_action_substitution` | The first activity record's `action` changes from `create` to `update`. |
| `attachment_same_length_bytes` | One attachment's bytes change (`alpha` → `omega`) without changing its length. |

The mutation labels above are not a separately maintained list: the builder
returns the label for each mutation it actually applies, and that returned
list is what the derivative's `adversarial-derivative.json` statement
declares. A future mutation that is added, removed, or changed cannot leave
a stale label behind.

Running the unchanged ExitDrill evaluator against this derivative, with the
same baseline used for the clean bundle, produces six **observed** loss
signals -- the evaluator counts them; the six mutations above are what
produced them, not a target the evaluator was tuned to hit:

| Dimension | Expected | Exported | Missing | Extra | Invalid | Status | Signals |
|---|--:|--:|--:|--:|--:|---|--:|
| Entities | 7 | 7 | 1 | 1 | 1 | fail | 2 |
| Relationships | 2 | 2 | 1 | 1 | 0 | fail | 1 |
| Attachments | 2 | 2 | 0 | 0 | 1 | fail | 1 |
| Permissions | 2 | 2 | 1 | 1 | 0 | fail | 1 |
| Audit events | 2 | 2 | 1 | 1 | 0 | fail | 1 |

`overall_status` is `not_structurally_restorable` and
`observed_remediation_signals` is `6`. The row is a coincidence worth being
explicit about: the entities dimension absorbs two of the six mutations
(`critical_field_value` and `unreferenced_identity_churn`) and reports two
signals, so six mutations producing six signals holds by arithmetic on this
specific set, not by a one-to-one correspondence the evaluator enforces. A
future mutation that changed two dimensions at once, or none, would not
break anything -- but it would change which number is six, and this table
would need updating to match. `check_directus_canary_demo.py` asserts the
exact per-dimension counts above and the exact six mutation labels on every
run, so that drift is caught immediately rather than discovered by a reader.

`--fail-on-loss-signal-increase` exits `3` when comparing the clean receipt
against the lossy one, since a comparable result directly observes a
missing/invalid increase in every dimension above.

## License and claim limits

Directus 11.17.4 is vendor software distributed under the Business Source
License 1.1 with an additional use grant; it is source-available and should not
be described as OSI-approved open source. Consult the version-pinned license
text for applicable terms. This repository does not redistribute Directus
source code or its container image; it contains invented fixture data,
first-party API responses from the synthetic lab, and an independent capture
program.

This fixture can support a bounded claim that one pinned, synthetic Directus
profile was captured through documented APIs and has a declared normalization
contract. It does **not** prove:

- that the API-response capture or separately authored baseline is authentic or
  complete;
- support for another Directus release, database, storage adapter, schema,
  permission shape, or activity shape;
- a successful load into a real target, workflow preservation, identity or
  permission-principal equivalence, or operational restoration;
- production readiness, customer use, vendor deletion, or legal compliance; or
- that Directus licensing permits any particular deployment.

The bundle and manifest are unsigned. Hashes detect byte changes but do not
authenticate the source, operator, or capture time.

The adversarial derivative adds one further, narrower claim and does **not**
extend the above: it shows that six specific, hand-chosen mutations to this
one pinned profile each survive normalization (row and file counts are
unchanged) and each still produce a fail-closed structural result. It does
not claim these are the only loss-producing mutations possible, that six is
a meaningful score, or that a different source profile would show the same
count.
