# Directus 11.17.4 synthetic civic-case canary

This directory is one frozen, synthetic-only native capture from a fresh
Directus 11.17.4 sandbox. It is evidence for one exact adapter profile, not a
general Directus export claim. The native bundle has not been hand-normalized
into an ExitDrill export; a profile-specific normalizer must do that outside the
evaluator.

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

- [Directus API overview](https://docs.directus.io/reference/introduction)
- [Global API query parameters](https://docs.directus.io/reference/query)
- [Files and asset access](https://docs.directus.io/reference/files)
- [Policies API](https://docs.directus.io/reference/system/policies)
- [Permissions API](https://docs.directus.io/reference/system/permissions)
- [Schema snapshot API](https://docs.directus.io/reference/system/schema)
- [Official Docker guide](https://docs.directus.io/self-hosted/docker-guide)
- [Directus v11.17.4 release](https://github.com/directus/directus/releases/tag/v11.17.4)
- [Directus v11.17.4 license text](https://github.com/directus/directus/blob/v11.17.4/license)

## Native evidence

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
and before the native manifest's `exported_at`; none of those timestamps are
authenticated.

## Profile normalization contract

The accepted profile is `directus-11.17.4-civic-case/v0.1`:

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

- that the source export or separately authored baseline is authentic or
  complete;
- support for another Directus release, database, storage adapter, schema,
  permission shape, or activity shape;
- a successful load into a real target, workflow preservation, identity or
  permission-principal equivalence, or operational restoration;
- production readiness, customer use, vendor deletion, or legal compliance; or
- that Directus licensing permits any particular deployment.

The bundle and manifest are unsigned. Hashes detect byte changes but do not
authenticate the source, operator, or capture time.
