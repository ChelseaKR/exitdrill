# Data contracts

Every document ExitDrill reads or writes on the synthetic path has a committed
JSON Schema (Draft 2020-12). `exitdrill schema list` prints their names and
`exitdrill schema show NAME` prints one schema's exact committed bytes, so an
integrator can validate their normalizer's output in their own language without
running the evaluator, and a reviewer handed a receipt can check its shape
without trusting the producer's code.

That is what [ADR 0001](decisions/0001-structural-evaluation-before-target-adapter.md)
rests on: if other people write the source-specific normalizer, the contract has
to be a machine-checkable artifact rather than a Python module they can read but
not execute.

## Which schema governs which command

| Command | Reads | Writes |
|---|---|---|
| `validate BASELINE EXPORT` | `baseline-v0.3`, `export-v0.1` | nothing |
| `validate-exercise PLAN` | `exercise-plan-v0.1` | nothing |
| `drill BASELINE EXPORT --out` | `baseline-v0.3`, `export-v0.1` | `receipt-v0.3` |
| `verify RECEIPT` | `receipt-v0.3` (and both inputs on replay) | nothing |
| `explain RECEIPT` | `receipt-v0.3` | nothing |
| `compare REFERENCE CANDIDATE` | `receipt-v0.3` twice | `receipt-comparison-v0.1` |
| `verify-comparison COMPARISON` | `receipt-comparison-v0.1`, `receipt-v0.3` twice | nothing |
| `history R1 R2 ...` | `receipt-v0.3` per receipt | `receipt-history-v0.1` |
| `verify-history HISTORY` | `receipt-history-v0.1`, `receipt-v0.3` per receipt | nothing |
| `report DOCUMENT --out` | any of the three document schemas | HTML, which has no schema |
| `schema list` / `schema show` | nothing | nothing |

The rendered HTML report has no schema and is not a contract. It is a view over
a document that has one, recomputed before it is rendered.

## What a passing schema check does and does not establish

The schemas express closed structure and every invariant that is *locally
expressible*: exact key sets, types, enumerations, digest patterns,
non-negative integer bounds, the fixed trust-limitation list, exactly one entry
per dimension, and the requirement that a declared field type and its expected
value agree.

They cannot express a relation between two values, and a schema that appeared to
would be worse than one that does not, because a reader would believe a passing
check had established something it had not. Each of the following is enforced by
the semantic validators alone. `tests/test_schemas.py` holds this list against
the code: an invariant that becomes locally expressible, or is dropped from the
validators, fails the suite.

| Invariant | Enforced by |
|---|---|
| `payload_sha256` is the SHA-256 of the canonical payload | `receipt.verify_receipt` |
| `missing_count` does not exceed `expected_count` | `receipt_validation._validate_dimension` |
| `extra_count`, `restored_count` and `invalid_count` do not exceed `exported_count` | `receipt_validation._validate_dimension` |
| `invalid_count` is at least the restoration shortfall | `receipt_validation._validate_dimension` |
| `expected_count - missing_count` equals `exported_count - extra_count` | `receipt_validation._validate_dimension` |
| a dimension's `status` follows from its counts and coverage | `models.classify_dimension_status` |
| `overall_status` follows from the dimension statuses | `models.classify_overall_status` |
| `observed_remediation_signals` is the sum of missing and invalid | `receipt_validation.validate_payload` |
| every timestamp is offset-aware ISO 8601 | `timestamps.parse_timestamp` |
| identifiers are unique within each baseline and export collection | `loader._require_unique` |
| `required_fields` names are unique within one entity | `loader._parse_expected_entity` |
| a baseline and an export belong to the same drill | `cli._validate` |

## Ordering

The schema check runs **after** the semantic validators, not before. The
semantic messages name the field and the relation that failed; a schema error
names conformance and nothing more, and the precise message is the more useful
of the two for whoever has to fix the document. The pairing is the one
`verify_comparison_document` already describes: the precise, source-bound check
first, the independently maintained schema after as a structural net over
arbitrary caller-supplied JSON.

The two checks are not redundant. The schemas are maintained apart from the
validators and can genuinely diverge from them, which is the whole reason for
having both.

## Versioning

A schema's version is in its filename and repeated as a `const` inside it, and
each name is pinned to exactly one published `$id` by
`scripts/check_wheel.py`. A contract change is a new file, never an edit to a
published one: a document that validated yesterday must validate tomorrow, or
the version in its `schema_version` field means nothing.
