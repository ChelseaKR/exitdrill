# Security policy

ExitDrill is a synthetic-data technical alpha. Do not process real constituent,
client, patient, donor, employee, or case-management exports.

Any path that permits an attachment to escape its root, executes input-supplied
code, emits record-level values in a receipt, or describes a neutral restore as
operational equivalence is a security or assurance defect.

The input boundary rejects duplicate JSON keys, non-finite numbers, excessive
nesting, unknown contract fields, and documents beyond their byte budgets.
Attachment size checks and hashing operate on one open file descriptor. Receipt
fields, nested dimensions, arithmetic, and result states are closed. Receipt
checksums remain unauthenticated: an attacker can fabricate a different
internally valid receipt. Receipt writes use exclusive randomized temporary
files and atomic replacement.

The synthetic exercise-plan validator checks declared sandbox controls but
executes no connector or target action. A valid plan is not evidence that any
control exists or that a restoration occurred.

Use GitHub's
[private vulnerability reporting](https://github.com/ChelseaKR/exitdrill/security/advisories/new).
Do not include production exports, credentials, personal information, or
confidential data in a report.
