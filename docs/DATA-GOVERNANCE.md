# Data governance

## Current permitted data

The current release permits only invented synthetic baselines, exports,
identities, cases, critical-field expected values, permissions, history, and
attachment bytes. Those fixtures are non-sensitive and committed for
reproducibility. No production-derived or merely “deidentified” vendor export
is permitted.

Receipts contain aggregates and input digests, not record fields or attachment
content. Generated receipts are disposable local artifacts and ignored by
version control.

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
