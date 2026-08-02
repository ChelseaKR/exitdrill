from pathlib import Path


def test_adr_compatibility_index_covers_every_accepted_decision() -> None:
    project = Path(__file__).parents[1]
    index = (project / "docs/adr/0000-record-architecture-decisions.md").read_text(encoding="utf-8")
    decisions = sorted((project / "docs/decisions").glob("[0-9][0-9][0-9][0-9]-*.md"))

    assert decisions
    for decision in decisions:
        assert f"../decisions/{decision.name}" in index
