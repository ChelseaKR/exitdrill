# Security policy

ExitDrill is a synthetic-data technical alpha. Do not process real constituent,
client, patient, donor, employee, or case-management exports.

Any path that permits an attachment to escape its root, executes input-supplied
code, emits record-level values in a receipt, or describes a neutral restore as
operational equivalence is a security or assurance defect.

The input boundary rejects duplicate JSON keys, non-finite numbers, excessive
nesting or node count, non-regular document paths, unknown contract fields, and
documents beyond their byte budgets. Attachment size checks and hashing operate
on one open file descriptor, reject size changes during the read, and use
descriptor-relative no-follow parent traversal where the platform supports it.
Receipt fields, nested dimensions, arithmetic, and result states are closed.
Receipt checksums remain unauthenticated: an attacker can fabricate a different
internally valid receipt. Receipt writes verify the complete semantic contract
and encoded 2 MiB bound before creating a directory or temporary file, then use
exclusive randomized temporary files and atomic replacement.

The synthetic exercise-plan validator checks declared sandbox controls but
executes no connector or target action. A valid plan is not evidence that any
control exists or that a restoration occurred.

Offline HTML reports are rendered only after complete receipt verification,
escape every receipt-derived string, contain no scripts or external assets, and
carry the receipt's complete limitations. They remain unsigned summaries of
unauthenticated aggregate evidence.

The Directus canary normalizer accepts only the closed 11.17.4 synthetic
civic-case profile. It verifies the manifest, fixed captured file set, sizes, and
hashes before reading mapped records; pins the exact captured schema digest;
rejects links, unsafe paths, and output nesting beneath the source; applies
strict resource bounds and shapes; and creates output through a fresh temporary
directory followed by an atomic rename. Its summary and normalization manifest
contain aggregates and hashes only. These controls detect inconsistent local
bytes, not a fabricated but internally consistent bundle, incomplete source
acquisition, or effective permission equivalence.

The repository's adversarial builder accepts only a bundle that already passes
that normalizer and matches the committed clean manifest and bundle hashes,
validates a no-symlink copied snapshot, checks each of its six mutation
preconditions, validates the derivative again, and requires disjoint sibling
output paths. It publishes the aggregate derivative statement before the capture
directory so a normal runtime failure cannot leave an unlabeled derivative.

Use GitHub's
[private vulnerability reporting](https://github.com/ChelseaKR/exitdrill/security/advisories/new).
Do not include production exports, credentials, personal information, or
confidential data in a report.
