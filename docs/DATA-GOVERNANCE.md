# Data governance

## Current permitted data

The current release permits only invented synthetic baselines, exports,
identities, cases, critical-field expected values, permissions, history, and
attachment bytes. Those fixtures are non-sensitive and committed for
reproducibility. No production-derived or merely “deidentified” vendor export
is permitted.

This includes the committed Directus 11.17.4 civic-case canary. Its people,
cases, policy, activity, file metadata, and text attachments were invented for
the lab. The custom capture bundle was assembled from responses and attachment
bytes collected from a real local process, but it is not customer, employer,
client, or production-derived data. Re-capture is permitted only in an isolated
synthetic sandbox.

It also includes the closed CiviCRM Standalone 6.16.2 target-roundtrip canary.
The target contacts, users, roles, groups, cases, relationships, ACL probes,
files, and attachment bytes are invented solely for the local run-owned lab.
The committed native target bundle contains record-level synthetic API response
projections and attachment content so the offline verifier can replay the
observation. It contains identity IDs and authentication-flow labels, but no
passwords, tokens, site keys, database credentials, signed download URLs, host
paths, or production identifiers. The aggregate target result contains none of
the native values or HTTP bodies. The native UI projection records only fixed
synthetic labels, a route name, status, and region name; raw HTML, cookies, and
tokens are not retained. Its separate aggregate result contains no record value
or target identifier.
The native browser projection contains only a fixed engine label, workflow-step
keys, an empty retained-artifact list, and a sanitized known-runtime-error key
and count. The browser container retains no screenshots, traces, downloads,
HTML, cookies, or credentials. Its aggregate result contains no synthetic record
value, target identifier, URL parameter, or filesystem path.
The native accessibility projection contains only the scanner name/version,
fixed rule tags, aggregate rule counts, and sanitized violation rule IDs,
impacts, and node counts. It excludes selectors, HTML snippets, help text, URLs,
screenshots, and traces. Its aggregate result adds fixed scope limitations but
no record values or browser artifacts.
The native keyboard projection contains only fixed semantic step keys, the
Chromium engine key, an aggregate Tab count, and an empty artifact list. It
retains no focused-element labels, accessible names, selectors, DOM paths, HTML,
screenshots, or traces.

Receipts contain aggregates and input digests, not record fields or attachment
content. Normalized exports necessarily contain the synthetic record fields and
attachment bytes; the normalizer's stdout and manifest contain only fixed labels,
hashes, and aggregates. The acceptance command creates adversarial bundles,
normalized outputs, receipts, and reports only in a disposable temporary
directory. The documented root normalization directories and generated example
`out/` directories are ignored by version control.

Live CiviCRM re-capture is permitted only with the reviewed digest-pinned
Compose topology, a fresh random project name, its run-owned volumes, no host
port, an internal network, disabled outbound mail and scheduled jobs, an empty
external-password-lookup URL, synthetic credentials generated for that run, and
the exact verified Directus source-normalization binding recorded in the target
manifest. The browser must use the reviewed digest-pinned, read-only,
capability-dropped container on that internal network with artifact retention
disabled. Cleanup may remove only those exact disposable project resources.
The live harness is not a production-data ingestion path.

## Production gate

Before any real or production-derived export is processed, an accepted design
must define:

- authority and data classification;
- encryption at rest and key handling;
- an ephemeral bounded workspace;
- access control and operator authorization;
- retention and verified deletion;
- backup prohibition or encrypted backup policy;
- incident and breach-response ownership;
- target-sandbox isolation and egress controls; and
- whether low counts or input digests create residual disclosure risk.

Until then, real client, constituent, patient, donor, employee, and case data
are prohibited.
