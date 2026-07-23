# AGENTS.md — ExitDrill

## Product thesis

ExitDrill is chaos engineering for switching SaaS vendors. It tests whether a
customer-obtainable export can be reconstructed and used outside the source
vendor before an emergency exit is necessary.

The current evaluator proves only bounded structural normalization into a
neutral reference model. It may not be represented as a successful operational
exit.

## Load-bearing invariants

1. An export cannot prove its own completeness. Every pass requires a separately
   captured baseline with explicit coverage.
2. Preserve the denominator. Entities, relationships, attachment bytes,
   permissions, and audit history remain separate dimensions.
3. No single portability score may conceal a failed or indeterminate dimension.
4. Missing, structurally invalid, extra, and indeterminate are distinct.
5. No arbitrary mapping execution: no commands, SQL, JQ, expressions, dynamic
   imports, URLs, or model-generated transforms in the trust path.
6. A neutral restore proves representability only. Operational restoration
   requires a real target load, read-back, and declared workflow probes.
7. Receipts contain aggregates and hashes, never record fields or attachment
   contents.
8. Receipts are unsigned and carry no trusted time. A checksum is not
   authentication.
9. Only synthetic data is permitted until a reviewed sensitive-data design and
   design-partner agreement exist.

## Engineering conventions

- Python 3.12+, standard-library runtime, `src/` layout.
- Strict mypy, Ruff, and branch coverage ≥90%.
- Add a negative test for every parser or trust-boundary behavior.
- Keep all fixtures invented and visibly synthetic.
- Do not copy code, schemas, or mappings from adjacent portfolio projects.
- Do not create a general connector SDK before a real source/target pair tests
  the abstraction.
