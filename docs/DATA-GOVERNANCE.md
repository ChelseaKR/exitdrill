# Data governance

## Current permitted data

The current release permits only invented synthetic baselines, exports,
identities, cases, critical-field expected values, permissions, history, and
attachment bytes. Those fixtures are non-sensitive and committed for
reproducibility. No production-derived or merely “deidentified” vendor export
is permitted.

This includes the committed Directus 11.17.4 civic-case canary. Its people,
cases, policy, activity, file metadata, and text attachments were invented for
the lab. The native bundle is a capture from a real local process, but it is not
customer, employer, client, or production-derived data. Re-capture is permitted
only in an isolated synthetic sandbox.

Receipts contain aggregates and input digests, not record fields or attachment
content. Normalized exports necessarily contain the synthetic record fields and
attachment bytes; the normalizer's stdout and manifest contain only fixed labels,
hashes, and aggregates. The acceptance command creates adversarial bundles,
normalized outputs, receipts, and reports only in a disposable temporary
directory. The documented root normalization directory and generated example
`out/` directories are ignored by version control.

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
