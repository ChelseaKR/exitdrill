# Threat model

**Scope:** current synthetic, offline structural evaluator
**Reviewed:** 2026-07-22

| Threat or failure | Current control | Residual risk |
|---|---|---|
| Export declares itself complete | separate baseline and per-dimension coverage | baseline can be false or stale |
| Missing category disappears from denominator | closed five-dimension contract | real vendor semantics may need more dimensions |
| Path traversal or symlink escape | post-resolution bounded-root check and no-follow final open | operator can choose an overbroad root; concurrent parent-directory replacement remains platform-dependent |
| Ambiguous or hostile JSON | duplicate-key and non-finite-number rejection, 64-level nesting bound, exact schemas, and byte limits | a maximally wide in-bound document still consumes parser work |
| Attachment path-swap race | size check and hashing use one already-open descriptor | the selected source digest itself may be wrong |
| Attachment metadata without bytes | bounded descriptor read, 16 MiB per-file and 128 MiB cumulative budgets, and dual digest comparison | possession of matching bytes does not prove business usability |
| Orphaned graph records | per-row SQLite foreign keys, database read-back counts, and `foreign_key_check` | neutral schema cannot express all semantics |
| Audit event ID conceals changed history | baseline binds event object, action, and offset-aware occurrence time | baseline may still omit events |
| Permission role names look equivalent | exact grant comparison scoped to an entity | principal identity is not modeled; real equivalence needs allow/deny probes |
| PII leaks in receipt | aggregate-only payload | low counts and input hashes may remain sensitive |
| Rehashed fabricated receipt | closed receipt, envelope, payload, dimension, arithmetic, limitation, and result-algebra validation | an attacker can still fabricate an internally valid receipt; no authentication |
| Predictable receipt temporary path | exclusive random same-directory temporary file and atomic replacement | selected output directory remains operator-controlled |
| Export formula/script payload | fields are treated as scalar data and never rendered or executed | future target adapters could introduce injection |
| Production target receives messages/payments | no target integration in the current evaluator | a future target exercise needs a sandbox marker, egress block, and disabled automation |
| Synthetic preflight is mistaken for a target drill | plan-only CLI status and no load/read-back/result code path | readers may still overlook the label |
| Successful normalization presented as safe exit | structural-only labels and limitations | marketing pressure remains |
| Connector treadmill | no public SDK and one-target discovery gate | bespoke work may still dominate |

## Misuse cases

- Using the receipt as proof that a vendor exported or deleted all customer data.
- Treating matching row counts as semantic preservation.
- Hiding a failed dimension behind a composite portability score.
- Calling an opaque JSON blob operationally usable.
- Loading sensitive production exports into an unreviewed environment.
- Vendor-funded testing presented as independent without payer disclosure.

Production-derived work is blocked until encryption, ephemeral workspace,
retention/deletion, operator authorization, incident response, and target
sandboxing receive separate review.
