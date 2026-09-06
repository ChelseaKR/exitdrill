import re
from pathlib import Path

from exitdrill.cli import _parser


def _subcommands() -> list[str]:
    usage = _parser().format_usage()
    choices = re.search(r"\{([a-z0-9,-]+)\}", usage)
    assert choices, "could not read the subcommand list out of the CLI usage line"
    return choices.group(1).split(",")


def _describes(text: str, name: str) -> bool:
    """Whether `text` names this subcommand as a word of its own.

    The boundaries on both sides are what stop a longer command's name from
    standing in for a shorter one: without them, a document that mentions only
    `validate-exercise` would also credit `validate`, and deleting the one
    place `validate` is described would leave the check green.

    This is a presence check and nothing more. A subcommand named once in
    passing satisfies it; whether the surrounding prose is any good is the
    maintainer's judgement. It exists to stop a command being published with no
    prose at all.
    """
    return re.search(rf"(?<![\w-]){re.escape(name)}(?![\w-])", text) is not None


def _committed_prose() -> list[str]:
    project = Path(__file__).parents[1]
    documents = [project / "README.md", *sorted((project / "docs").rglob("*.md"))]
    return [path.read_text(encoding="utf-8") for path in documents]


def test_every_cli_subcommand_is_described_in_a_committed_document() -> None:
    texts = _committed_prose()
    subcommands = _subcommands()

    assert "validate-exercise" in subcommands
    for name in subcommands:
        assert any(_describes(text, name) for text in texts), f"{name} is documented nowhere"


def test_the_subcommand_binding_rejects_a_name_no_document_carries() -> None:
    """The check above must be able to fail; nothing asserted that it could.

    Its matcher was an inline regex whose word boundaries were explained by a
    comment -- the shape issue #96 removed elsewhere, where a construction
    states a fact and nothing proves it still holds. A matcher that answered
    True for anything would satisfy the check for every subcommand, including
    one described nowhere.

    Two cases. The first runs against the real corpus and differs from the
    check above only in the name it asks about. The second pins the boundary
    the comment claimed: `validate-exercise` must not credit `validate`, which
    is the one way the check could pass while a command went undescribed.
    """
    corpus = _committed_prose()

    assert not any(_describes(text, "validate-invented") for text in corpus)

    assert not _describes("run exitdrill validate-exercise plan.json", "validate")
    assert _describes("run exitdrill validate baseline.json export.json", "validate")
    assert _describes("`validate-exercise` is the first step", "validate-exercise")


def test_adr_compatibility_index_covers_every_accepted_decision() -> None:
    project = Path(__file__).parents[1]
    index = (project / "docs/adr/0000-record-architecture-decisions.md").read_text(encoding="utf-8")
    decisions = sorted((project / "docs/decisions").glob("[0-9][0-9][0-9][0-9]-*.md"))

    assert decisions
    for decision in decisions:
        assert f"../decisions/{decision.name}" in index


# Two limits `docs/plans/improvement-plan.md` published as open, and the fact in
# the tree that closes each. The pair is the whole point: a claim and the code
# that decides whether it is still true, checked against each other in both
# directions rather than either one alone.
_CLOSED_LIMITS = (
    (
        "Coverage does not measure `scripts/`.",
        "pyproject.toml",
        'source = ["exitdrill", "scripts"]',
    ),
    (
        "Nothing pins that this stays true.",
        "scripts/check_browser_capture_bindings.mjs",
        "PAGE_ERRORS_STUB_GUARD",
    ),
)


def test_the_plan_publishes_no_limit_the_code_has_closed() -> None:
    """The improvement plan may not go on naming a limit the tree has closed.

    Both entries under "Known limits this plan does not close" were true when
    they were written and are not true now: `[tool.coverage.run] source` gained
    `scripts` in #125, and the binding gate gained the guard that pins the
    `pageErrors` stub's precondition. Nothing noticed, because nothing read the
    plan against the code.

    That is the defect the plan itself is about, pointed at the plan: a
    statement about what is enforced outliving the enforcement. Here it
    understated the project rather than overstating it, which is the safer
    direction and still not a true one.

    Checked in both directions. If a closure is reverted, the plan has to say so
    again; if the plan reinstates a limit, the closure has to be gone.
    """
    project = Path(__file__).parents[1]
    plan = (project / "docs" / "plans" / "improvement-plan.md").read_text(encoding="utf-8")
    assert "Known limits this plan does not close" in plan, (
        "the section this test reads is gone; either restore it or delete this test, "
        "but do not leave a check that passes because it found nothing to read"
    )

    for sentence, source, evidence in _CLOSED_LIMITS:
        closed = evidence in (project / source).read_text(encoding="utf-8")
        published_as_open = sentence in plan and "~~" not in _entry_for(plan, sentence)
        if closed:
            assert not published_as_open, (
                f"{source} shows this limit is closed ({evidence!r} is present), but the "
                f"improvement plan still publishes {sentence!r} as open"
            )
        else:
            assert published_as_open, (
                f"{source} no longer carries {evidence!r}, so the limit is open again and "
                f"the improvement plan must say so: it does not carry {sentence!r}"
            )


def _entry_for(plan: str, sentence: str) -> str:
    """The bullet the sentence sits in, so a struck-through entry reads as closed.

    Without this the check could only ask whether the sentence appears at all,
    and the plan could not keep the history of what was once open, which is
    exactly what this repository's documents are for.
    """
    index = plan.index(sentence)
    start = plan.rfind("\n- ", 0, index)
    end = plan.find("\n- ", index)
    return plan[start if start >= 0 else 0 : end if end >= 0 else len(plan)]
