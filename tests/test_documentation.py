import re
from pathlib import Path

from exitdrill.cli import _parser


def _subcommands() -> list[str]:
    usage = _parser().format_usage()
    choices = re.search(r"\{([a-z0-9,-]+)\}", usage)
    assert choices, "could not read the subcommand list out of the CLI usage line"
    return choices.group(1).split(",")


def test_every_cli_subcommand_is_described_in_a_committed_document() -> None:
    project = Path(__file__).parents[1]
    documents = [project / "README.md", *sorted((project / "docs").rglob("*.md"))]
    texts = [path.read_text(encoding="utf-8") for path in documents]
    subcommands = _subcommands()

    assert "validate-exercise" in subcommands
    for name in subcommands:
        # A bare name must appear on its own, so `validate` is not credited to
        # a mention of `validate-exercise`.
        token = re.compile(rf"(?<![\w-]){re.escape(name)}(?![\w-])")
        assert any(token.search(text) for text in texts), f"{name} is documented nowhere"


def test_adr_compatibility_index_covers_every_accepted_decision() -> None:
    project = Path(__file__).parents[1]
    index = (project / "docs/adr/0000-record-architecture-decisions.md").read_text(encoding="utf-8")
    decisions = sorted((project / "docs/decisions").glob("[0-9][0-9][0-9][0-9]-*.md"))

    assert decisions
    for decision in decisions:
        assert f"../decisions/{decision.name}" in index
