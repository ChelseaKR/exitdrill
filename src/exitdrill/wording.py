"""The one table of reader-facing prose every rendered artifact draws from.

Two surfaces publish sentences to a reader who will not run the tool: the
offline HTML report and, now, `exitdrill explain`. Each held its own copy of
the limitation sentences, the result-state names, and the dimension labels, so
the two could disagree about what a receipt says without anything noticing --
the same shape as a document restating a bound the code no longer enforces.

Every string a reader sees that is not a count, a digest, or free payload text
comes from here. Nothing in this module reads a receipt or decides anything: it
is vocabulary, and the modules that use it decide which entry applies.
"""

from __future__ import annotations

from exitdrill.models import Coverage, Dimension, DimensionStatus, OverallStatus

DIMENSION_LABELS = {
    Dimension.ATTACHMENTS.value: "Attachments",
    Dimension.AUDIT_EVENTS.value: "Audit events",
    Dimension.ENTITIES.value: "Entities",
    Dimension.PERMISSIONS.value: "Permissions",
    Dimension.RELATIONSHIPS.value: "Relationships",
}

# The lowercase noun each dimension's sentences count, singular and plural.
# "2 of 40 relationships could not be rebuilt" reads as English; "2 of 40
# Relationships" does not, and neither does "1 relationships".
DIMENSION_NOUNS = {
    Dimension.ATTACHMENTS.value: ("attachment", "attachments"),
    Dimension.AUDIT_EVENTS.value: ("audit event", "audit events"),
    Dimension.ENTITIES.value: ("entity", "entities"),
    Dimension.PERMISSIONS.value: ("permission grant", "permission grants"),
    Dimension.RELATIONSHIPS.value: ("relationship", "relationships"),
}

# The question each dimension asks, in the same words `README.md` publishes.
# `tests/test_explain.py` binds them to that table, so a reworded README has to
# reword this and a reworded narration has to reword the README.
DIMENSION_QUESTIONS = {
    Dimension.ATTACHMENTS.value: "Are the referenced bytes present and unchanged?",
    Dimension.AUDIT_EVENTS.value: "Are the expected events represented?",
    Dimension.ENTITIES.value: "Are the expected identities and declared critical values present?",
    Dimension.PERMISSIONS.value: "Are the declared grants represented?",
    Dimension.RELATIONSHIPS.value: "Can the expected links still be reconstructed?",
}

STATUS_LABELS = {
    DimensionStatus.FAIL.value: "Fail",
    DimensionStatus.FINDING.value: "Finding",
    DimensionStatus.INDETERMINATE.value: "Indeterminate",
    DimensionStatus.PASS.value: "Pass",
    OverallStatus.INDETERMINATE.value: "Indeterminate",
    OverallStatus.NOT_STRUCTURALLY_RESTORABLE.value: "Not structurally restorable",
    OverallStatus.STRUCTURALLY_RESTORABLE.value: "Structurally restorable",
    OverallStatus.STRUCTURALLY_RESTORABLE_WITH_FINDINGS.value: (
        "Structurally restorable with findings"
    ),
}

# One sentence per limitation code, receipt and comparison alike. These are the
# load-bearing claims: they are what the evidence does not establish, and they
# are quoted rather than paraphrased wherever they appear.
LIMITATION_SENTENCES = {
    "aggregate_only_cannot_observe_record_identity_churn": (
        "Aggregate counts cannot observe record-identity churn."
    ),
    "comparison_output_is_unsigned_and_unauthenticated": (
        "This comparison document is itself unsigned and unauthenticated."
    ),
    "does_not_authenticate_export_or_baseline": "Does not authenticate the export or baseline.",
    "does_not_bind_export_generation_or_evaluator_version": (
        "Does not bind the export generation or the evaluator version."
    ),
    "does_not_prove_operational_equivalence": "Does not prove operational equivalence.",
    "does_not_prove_vendor_deletion": "Does not prove vendor deletion.",
    "does_not_verify_permission_principal_identity": (
        "Does not verify permission-principal identity."
    ),
    "field_value_equivalence_limited_to_declared_required_fields": (
        "Field-value equivalence is limited to baseline-declared required fields."
    ),
    "inputs_are_unsigned_and_unauthenticated": (
        "Both input receipts are unsigned and unauthenticated."
    ),
    "operand_order_is_caller_supplied_unverified": (
        "Operand order is caller-supplied and unverified. It is not chronology."
    ),
}

# What each coverage declaration means for a reader who has never seen one.
# Written without a pronoun or a plural, so one clause fits every dimension and
# every count without a grammar branch deciding what a reader is told.
COVERAGE_SENTENCES = {
    Coverage.COMPLETE.value: "the baseline accounts for all of this evidence",
    Coverage.PARTIAL.value: "the baseline accounts for only part of this evidence",
    Coverage.UNAVAILABLE.value: "the baseline could not account for this evidence at all",
}

# One sentence per overall result state, saying what the state means and
# nothing more. `README.md`'s result-state table is the shorter form of the
# same statements.
OVERALL_SENTENCES = {
    OverallStatus.INDETERMINATE.value: (
        "The drill could not decide: at least one dimension had partial or unavailable "
        "baseline coverage, and nothing was observed missing or invalid elsewhere."
    ),
    OverallStatus.NOT_STRUCTURALLY_RESTORABLE.value: (
        "The drill observed structural loss: at least one dimension had expected evidence "
        "that was missing, invalid, or could not be loaded."
    ),
    OverallStatus.STRUCTURALLY_RESTORABLE.value: (
        "The drill observed no structural loss: every dimension had complete baseline "
        "coverage and nothing missing, invalid, or extra."
    ),
    OverallStatus.STRUCTURALLY_RESTORABLE_WITH_FINDINGS.value: (
        "The drill observed no structural loss, but the export carried items the baseline "
        "did not declare."
    ),
}


def label(table: dict[str, str], value: str) -> str:
    """Look a code up, falling back to a readable form of the code itself.

    A code with no entry is a gap in this table, not an error in the document
    that carries it, so it renders as words rather than stopping a render.
    """
    return table.get(value, value.replace("_", " ").capitalize())


def counted(count: int, nouns: tuple[str, str]) -> str:
    """Render a count with its noun in agreement, e.g. `1 entity` / `2 entities`."""
    singular, plural = nouns
    return f"{count} {singular if count == 1 else plural}"


def were(count: int) -> str:
    """The verb that agrees with a count, so `1 was missing` is not `1 were`."""
    return "was" if count == 1 else "were"
