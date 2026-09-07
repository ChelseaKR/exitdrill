"""The public schemas, and the exact boundary of what passing one establishes.

ADR 0001 bets that other people write the source-specific normalizer. A contract
they can read but not execute is not a contract they can build against, so the
receipt and both input contracts now have committed JSON Schemas beside the
Python validators.

Two failure modes are worth more than the schemas themselves.

A schema **stricter** than the validators rejects documents the tool loads, and
an integrator who validates first and runs second gets a refusal the evaluator
would not have given. Every committed example, and every document the demo
writes, is validated here for that reason.

A schema **believed to check more than it does** is worse than no schema. Draft
2020-12 cannot express a relation between two values, so the count arithmetic,
the status algebra, the payload checksum and the offset-aware timestamp rule are
enforced by the validators alone. `docs/DATA-CONTRACTS.md` lists each of them,
and the last section here holds that list against the code in both directions:
an invariant the document forgets, or one the validators stop enforcing, fails.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from copy import deepcopy
from pathlib import Path
from typing import cast

import pytest
from jsonschema import Draft202012Validator

from exitdrill.canonical import canonical_json_bytes, sha256_bytes
from exitdrill.cli import main
from exitdrill.evaluator import run_drill
from exitdrill.exercise import ExercisePlanError, load_exercise_plan
from exitdrill.loader import PackageError, load_baseline, load_export
from exitdrill.models import JsonValue
from exitdrill.receipt import ReceiptError, build_receipt, verify_receipt
from exitdrill.schemas import (
    BASELINE_SCHEMA,
    EXERCISE_PLAN_SCHEMA,
    EXPORT_SCHEMA,
    PUBLIC_SCHEMA_NAMES,
    RECEIPT_SCHEMA,
    SchemaResourceError,
    read_schema_bytes,
    schema_validator,
)

PROJECT = Path(__file__).parents[1]
SCHEMAS = PROJECT / "schemas"
CLEAN = PROJECT / "examples" / "synthetic-crm"
LOSSY = PROJECT / "examples" / "synthetic-crm-lossy"
CONTRACTS = PROJECT / "docs" / "DATA-CONTRACTS.md"

# Every relation `docs/DATA-CONTRACTS.md` declares the schemas cannot express,
# paired with a literal from the module that does enforce it. Both halves are
# checked: the document must name the invariant, and the code must still carry
# the enforcement, so neither can drift away from the other unnoticed.
CROSS_OBJECT_INVARIANTS = (
    (
        "`payload_sha256` is the SHA-256 of the canonical payload",
        "src/exitdrill/receipt.py",
        'raise ReceiptError("receipt payload checksum mismatch")',
    ),
    (
        "`missing_count` does not exceed `expected_count`",
        "src/exitdrill/receipt_validation.py",
        'f"{context}.missing_count exceeds expected_count"',
    ),
    (
        "`invalid_count` is at least the restoration shortfall",
        "src/exitdrill/receipt_validation.py",
        'f"{context}.invalid_count is below the restoration shortfall"',
    ),
    (
        "`expected_count - missing_count` equals `exported_count - extra_count`",
        "src/exitdrill/receipt_validation.py",
        'f"{context} expected/exported intersection is inconsistent"',
    ),
    (
        "a dimension's `status` follows from its counts and coverage",
        "src/exitdrill/receipt_validation.py",
        'f"{context}.status contradicts its counts or coverage"',
    ),
    (
        "`overall_status` follows from the dimension statuses",
        "src/exitdrill/receipt_validation.py",
        '"receipt payload overall_status contradicts dimension statuses"',
    ),
    (
        "`observed_remediation_signals` is the sum of missing and invalid",
        "src/exitdrill/receipt_validation.py",
        '"receipt payload remediation signals contradict its dimensions"',
    ),
    (
        "every timestamp is offset-aware ISO 8601",
        "src/exitdrill/timestamps.py",
        'f"{context} must include a UTC offset"',
    ),
    (
        "identifiers are unique within each baseline and export collection",
        "src/exitdrill/loader.py",
        'f"{context} keys must be unique"',
    ),
    (
        "`required_fields` names are unique within one entity",
        "src/exitdrill/loader.py",
        'f"{context}.required_fields names must be unique"',
    ),
    (
        "a baseline and an export belong to the same drill",
        "src/exitdrill/cli.py",
        '"baseline and export identities do not match"',
    ),
)


def validator(name: str) -> Draft202012Validator:
    return Draft202012Validator(json.loads((SCHEMAS / name).read_text(encoding="utf-8")))


def receipt() -> dict[str, JsonValue]:
    result = run_drill(
        load_baseline(CLEAN / "baseline.json"),
        load_export(CLEAN / "export.json"),
        CLEAN / "export-files",
    )
    return build_receipt(result, claimed_generated_at="2026-07-22T20:00:00Z")


def rehashed(document: dict[str, JsonValue]) -> dict[str, JsonValue]:
    payload = cast(dict[str, JsonValue], document["payload"])
    document["payload_sha256"] = sha256_bytes(canonical_json_bytes(payload))
    return document


def dimension(document: dict[str, JsonValue], index: int = 0) -> dict[str, JsonValue]:
    payload = cast(dict[str, JsonValue], document["payload"])
    return cast(dict[str, JsonValue], cast(list[JsonValue], payload["dimensions"])[index])


# ---------------------------------------------------------------------------
# The schemas are schemas, and they are the ones the package publishes.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("name", PUBLIC_SCHEMA_NAMES)
def test_every_published_schema_compiles(name: str) -> None:
    Draft202012Validator.check_schema(json.loads(read_schema_bytes(name)))


def test_every_committed_schema_is_published_and_the_reverse() -> None:
    """A schema on disk nobody publishes is one nobody can run."""
    committed = sorted(path.name for path in SCHEMAS.glob("*.schema.json"))
    published = sorted(PUBLIC_SCHEMA_NAMES)

    assert published == sorted(set(published))
    for name in published:
        assert name in committed, name


def test_schema_show_prints_the_exact_committed_bytes(
    capsysbinary: pytest.CaptureFixture[bytes],
) -> None:
    assert main(["schema", "show", "receipt-v0.3.schema.json"]) == 0

    assert capsysbinary.readouterr().out == (SCHEMAS / RECEIPT_SCHEMA).read_bytes()


def test_schema_list_prints_every_published_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["schema", "list"]) == 0

    assert capsys.readouterr().out.split() == list(PUBLIC_SCHEMA_NAMES)


@pytest.mark.parametrize(
    "name",
    ["receipt", "receipt-v0.3", "receipt-v0.3.schema.json"],
)
def test_schema_show_accepts_the_names_an_integrator_would_type(
    name: str, capsysbinary: pytest.CaptureFixture[bytes]
) -> None:
    assert main(["schema", "show", name]) == 0

    assert capsysbinary.readouterr().out == (SCHEMAS / RECEIPT_SCHEMA).read_bytes()


def test_schema_show_refuses_an_ambiguous_or_unknown_name(
    capsys: pytest.CaptureFixture[str],
) -> None:
    assert main(["schema", "show", "invented"]) == 2
    assert "not a published schema" in capsys.readouterr().err

    assert main(["schema", "show"]) == 2
    assert "needs the name" in capsys.readouterr().err

    assert main(["schema", "list", "receipt"]) == 2
    assert "takes no name" in capsys.readouterr().err


def test_reading_an_unpublished_schema_is_refused() -> None:
    with pytest.raises(SchemaResourceError, match="not a published schema"):
        read_schema_bytes("../pyproject.toml")


def test_compiling_a_document_that_is_not_a_schema_is_refused(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A packaged file that is not a schema must be named, not silently accepted."""
    schema_validator.cache_clear()
    monkeypatch.setattr(
        "exitdrill.schemas.read_schema_bytes",
        lambda name: b'{"type": 17}',
    )

    with pytest.raises(SchemaResourceError, match="is invalid"):
        schema_validator(RECEIPT_SCHEMA)

    schema_validator.cache_clear()


# ---------------------------------------------------------------------------
# No schema is stricter than the validator it sits beside.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("path", "name"),
    [
        (CLEAN / "baseline.json", BASELINE_SCHEMA),
        (CLEAN / "export.json", EXPORT_SCHEMA),
        (LOSSY / "export.json", EXPORT_SCHEMA),
        (PROJECT / "examples" / "synthetic-exercise" / "plan.json", EXERCISE_PLAN_SCHEMA),
    ],
)
def test_every_committed_example_satisfies_its_schema(path: Path, name: str) -> None:
    validator(name).validate(json.loads(path.read_text(encoding="utf-8")))


def test_the_receipt_the_demo_writes_satisfies_its_schema() -> None:
    validator(RECEIPT_SCHEMA).validate(json.loads(canonical_json_bytes(receipt())))


def test_a_receipt_with_surrounding_whitespace_in_an_identifier_still_loads() -> None:
    """The loader strips before it matches, so the schema must allow the space.

    A pattern anchored without it would be stricter than the code, which is the
    failure mode that makes an integrator's local validation useless.
    """
    document = json.loads((CLEAN / "baseline.json").read_text(encoding="utf-8"))
    document["entities"][0]["id"] = f" {document['entities'][0]['id']} "

    validator(BASELINE_SCHEMA).validate(document)


# ---------------------------------------------------------------------------
# The schema rejects what it claims to, per invariant.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("an extra receipt key", lambda item: item.update({"invented": 1})),
        (
            "an extra payload key",
            lambda item: cast(dict[str, JsonValue], item["payload"]).update({"invented": 1}),
        ),
        (
            "an extra envelope key",
            lambda item: cast(dict[str, JsonValue], item["envelope"]).update({"invented": 1}),
        ),
        ("a wrong receipt schema version", lambda item: item.update({"schema_version": "x"})),
        (
            "a wrong payload schema version",
            lambda item: cast(dict[str, JsonValue], item["payload"]).update(
                {"schema_version": "x"}
            ),
        ),
        (
            "a wrong decision scope",
            lambda item: cast(dict[str, JsonValue], item["payload"]).update(
                {"decision_scope": "anything_goes"}
            ),
        ),
        ("a claimed signature", lambda item: _envelope(item).update({"signature_status": "ok"})),
        ("a claimed trusted time", lambda item: _envelope(item).update({"trusted_time": True})),
        ("a malformed payload digest", lambda item: item.update({"payload_sha256": "NOTHEX"})),
        (
            "a malformed baseline digest",
            lambda item: cast(dict[str, JsonValue], item["payload"]).update(
                {"baseline_sha256": "0" * 63}
            ),
        ),
        ("an unknown dimension name", lambda item: dimension(item).update({"name": "invented"})),
        ("an unknown coverage value", lambda item: dimension(item).update({"coverage": "maybe"})),
        ("an unknown status value", lambda item: dimension(item).update({"status": "ok"})),
        ("a negative count", lambda item: dimension(item).update({"missing_count": -1})),
        ("a non-integer count", lambda item: dimension(item).update({"missing_count": 1.5})),
        ("a boolean count", lambda item: dimension(item).update({"missing_count": True})),
        ("an extra dimension key", lambda item: dimension(item).update({"invented": 1})),
        ("an unknown overall status", lambda item: _payload(item).update({"overall_status": "ok"})),
        ("a dropped dimension", lambda item: _dimensions(item).pop()),
        ("a duplicated dimension", lambda item: _duplicate_dimension(item)),
        ("a reordered limitation list", lambda item: _limitations(item).reverse()),
        ("a dropped limitation", lambda item: _limitations(item).pop()),
    ],
)
def test_the_receipt_schema_rejects_one_locally_expressible_violation(
    label: str, mutate: Callable[[dict[str, JsonValue]], object]
) -> None:
    """One mutated receipt per invariant the schema is claimed to carry."""
    document = json.loads(canonical_json_bytes(receipt()))
    validator(RECEIPT_SCHEMA).validate(document)

    mutate(document)

    assert list(validator(RECEIPT_SCHEMA).iter_errors(document)), label


def _payload(document: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], document["payload"])


def _envelope(document: dict[str, JsonValue]) -> dict[str, JsonValue]:
    return cast(dict[str, JsonValue], document["envelope"])


def _dimensions(document: dict[str, JsonValue]) -> list[JsonValue]:
    return cast(list[JsonValue], _payload(document)["dimensions"])


def _limitations(document: dict[str, JsonValue]) -> list[JsonValue]:
    return cast(list[JsonValue], _payload(document)["trust_limitations"])


def _duplicate_dimension(document: dict[str, JsonValue]) -> None:
    dimensions = _dimensions(document)
    dimensions[1] = deepcopy(dimensions[0])


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("an extra baseline key", lambda item: item.update({"invented": 1})),
        ("a wrong schema version", lambda item: item.update({"schema_version": "x"})),
        ("a missing coverage dimension", lambda item: item["coverage"].pop("entities")),
        ("an unknown coverage value", lambda item: item["coverage"].update({"entities": "some"})),
        ("an identifier with a space inside", lambda item: _first_entity_id(item, "a b")),
        ("an empty identifier", lambda item: _first_entity_id(item, "")),
        ("an extra entity key", lambda item: item["entities"][0].update({"invented": 1})),
        ("a malformed attachment digest", lambda item: _first_attachment_digest(item, "nope")),
        (
            "a required field whose value contradicts its declared type",
            lambda item: item["entities"][0]["required_fields"][0].update(
                {"type": "number", "expected_value": "not a number"}
            ),
        ),
        (
            "a required field of an unsupported type",
            lambda item: item["entities"][0]["required_fields"][0].update({"type": "object"}),
        ),
    ],
)
def test_the_baseline_schema_rejects_one_locally_expressible_violation(
    label: str, mutate: Callable[[dict[str, object]], object]
) -> None:
    document = json.loads((CLEAN / "baseline.json").read_text(encoding="utf-8"))
    validator(BASELINE_SCHEMA).validate(document)

    mutate(document)

    assert list(validator(BASELINE_SCHEMA).iter_errors(document)), label


def _first_entity_id(document: dict[str, object], value: str) -> None:
    cast(list[dict[str, object]], document["entities"])[0]["id"] = value


def _first_attachment_digest(document: dict[str, object], value: str) -> None:
    cast(list[dict[str, object]], document["attachments"])[0]["content_sha256"] = value


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("an extra export key", lambda item: item.update({"invented": 1})),
        ("a wrong schema version", lambda item: item.update({"schema_version": "x"})),
        (
            "a field name that is not an identifier",
            lambda item: item["entities"][0]["fields"].update({"has space": "x"}),
        ),
        (
            "a field value that is not a scalar",
            lambda item: item["entities"][0]["fields"].update({"nested": {"a": 1}}),
        ),
        (
            "an attachment with no relative path",
            lambda item: item["attachments"][0].pop("relative_path"),
        ),
    ],
)
def test_the_export_schema_rejects_one_locally_expressible_violation(
    label: str, mutate: Callable[[dict[str, object]], object]
) -> None:
    document = json.loads((CLEAN / "export.json").read_text(encoding="utf-8"))
    validator(EXPORT_SCHEMA).validate(document)

    mutate(document)

    assert list(validator(EXPORT_SCHEMA).iter_errors(document)), label


@pytest.mark.parametrize(
    ("label", "mutate"),
    [
        ("real data permitted", lambda item: item.update({"data_mode": "real"})),
        (
            "a sandbox that allows production data",
            lambda item: item["target_sandbox"].update({"production_data_allowed": True}),
        ),
        (
            "a sandbox with egress open",
            lambda item: item["target_sandbox"].update({"egress_blocked": False}),
        ),
        ("a dropped safety probe", lambda item: item["workflow_probes"].pop()),
        (
            "a probe whose kind was swapped",
            lambda item: item["workflow_probes"][0].update({"kind": "attachment"}),
        ),
        (
            "an optional probe",
            lambda item: item["workflow_probes"][0].update({"required": False}),
        ),
        (
            "a waived evidence control",
            lambda item: item["evidence_controls"].update({"human_attestation_required": False}),
        ),
    ],
)
def test_the_exercise_plan_schema_rejects_one_locally_expressible_violation(
    label: str, mutate: Callable[[dict[str, object]], object]
) -> None:
    document = json.loads(
        (PROJECT / "examples" / "synthetic-exercise" / "plan.json").read_text(encoding="utf-8")
    )
    validator(EXERCISE_PLAN_SCHEMA).validate(document)

    mutate(document)

    assert list(validator(EXERCISE_PLAN_SCHEMA).iter_errors(document)), label


# ---------------------------------------------------------------------------
# The validators still run, and still run first.
# ---------------------------------------------------------------------------


def test_the_semantic_message_is_the_one_a_reader_gets() -> None:
    """Schema-first would replace every precise message with a conformance one."""
    document = receipt()
    dimension(document)["missing_count"] = 99
    rehashed(document)

    with pytest.raises(ReceiptError, match="missing_count exceeds expected_count"):
        verify_receipt(document)


def test_the_loaders_still_reject_what_only_they_can_see(tmp_path: Path) -> None:
    baseline = json.loads((CLEAN / "baseline.json").read_text(encoding="utf-8"))
    baseline["entities"].append(deepcopy(baseline["entities"][0]))
    path = tmp_path / "baseline.json"
    path.write_text(json.dumps(baseline), encoding="utf-8")

    # The duplicate satisfies the schema; only the loader can see it.
    validator(BASELINE_SCHEMA).validate(baseline)
    with pytest.raises(PackageError, match="keys must be unique"):
        load_baseline(path)


def test_the_exercise_loader_still_rejects_what_only_it_can_see(tmp_path: Path) -> None:
    plan = json.loads(
        (PROJECT / "examples" / "synthetic-exercise" / "plan.json").read_text(encoding="utf-8")
    )
    plan["baseline"]["source_descriptions"] = ["   "]
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")

    with pytest.raises(ExercisePlanError, match="source_descriptions"):
        load_exercise_plan(path)


def test_the_schema_check_is_on_every_load_path(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wiring, not the schemas.

    For a receipt, a baseline, a plan or an export, the semantic validators are
    already at least as strict as the schema, so no document exists that passes
    one and fails the other. That is what makes the schema a net rather than a
    duplicate -- and it also means nothing would notice if the call were
    deleted. Standing in for the validator proves each call site is reached.
    """
    calls: list[str] = []
    # Built before the stand-in is installed: `receipt()` loads a baseline and an
    # export, and those go through the same call sites.
    document = receipt()

    def refuse(name: str, document: object, error: type[Exception], label: str) -> None:
        calls.append(label)
        raise error(f"{label} was checked against {name}")

    for module in ("receipt", "loader", "exercise"):
        monkeypatch.setattr(f"exitdrill.{module}.validate_against_schema", refuse)

    with pytest.raises(ReceiptError, match="was checked against"):
        verify_receipt(document)
    with pytest.raises(PackageError, match="was checked against"):
        load_baseline(CLEAN / "baseline.json")
    with pytest.raises(PackageError, match="was checked against"):
        load_export(CLEAN / "export.json")
    with pytest.raises(ExercisePlanError, match="was checked against"):
        load_exercise_plan(PROJECT / "examples" / "synthetic-exercise" / "plan.json")

    assert calls == ["receipt", "baseline", "export", "exercise plan"]


# ---------------------------------------------------------------------------
# The boundary is published, and published truthfully.
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(("sentence", "source", "evidence"), CROSS_OBJECT_INVARIANTS)
def test_each_cross_object_invariant_is_published_and_still_enforced(
    sentence: str, source: str, evidence: str
) -> None:
    """Both directions. The document must name it, and the code must still do it.

    An invariant dropped from the validators leaves a sentence in
    `docs/DATA-CONTRACTS.md` claiming a check nobody runs; an invariant dropped
    from the document leaves a reader believing the schema covers more than it
    does. Either is the same defect pointed the other way.
    """
    assert sentence in CONTRACTS.read_text(encoding="utf-8"), sentence
    assert evidence in (PROJECT / source).read_text(encoding="utf-8"), (source, evidence)


def test_the_invariant_binding_can_fail() -> None:
    """Keeps the check above from passing on a document that says anything."""
    contracts = CONTRACTS.read_text(encoding="utf-8")

    assert "`overall_status` is whatever the producer says" not in contracts
    assert len(CROSS_OBJECT_INVARIANTS) >= 11


def _invariant_table_rows() -> list[str]:
    """The rows of the cross-object invariant table, read out of the document."""
    contracts = CONTRACTS.read_text(encoding="utf-8")
    block = contracts.split("| Invariant | Enforced by |")[1].split("\n## ")[0]
    return [line for line in block.splitlines() if line.startswith("|") and set(line) - set("|- ")]


def test_the_document_states_what_the_invariant_table_costs() -> None:
    """The table is a list of gaps in ADR 0001's bet, and it did not say so.

    `docs/DATA-CONTRACTS.md` quotes ADR 0001 in its opening paragraphs: if other
    people write the normalizer, the contract has to be "a machine-checkable
    artifact rather than a Python module they can read but not execute". Twelve
    rows later it says each of these invariants is enforced by the semantic
    validators alone. Both sentences were true and neither drew the conclusion,
    which is that for those relations the contract *is* the Python module ADR
    0001 said it must not be, and an implementer in another language can satisfy
    every published schema and still emit documents this tool refuses.

    The gap is real either way; what this holds is that it stays stated. The
    count is read from the table rather than trusted from the prose, so adding
    an invariant without updating the disclosure fails here, and so does
    deleting the disclosure while the table still has rows.
    """
    contracts = CONTRACTS.read_text(encoding="utf-8")
    rows = _invariant_table_rows()
    assert rows, "the invariant table is empty, and this section describes it"

    heading = "### What that table costs an outside implementer"
    assert heading in contracts, (
        "docs/DATA-CONTRACTS.md no longer states what its invariant table costs "
        "somebody implementing a normalizer in another language"
    )
    # Collapsed, because the document hard-wraps and every claim below straddles a
    # line break in it. The first form of this check matched raw text and failed on
    # the ADR 0001 quote for that reason alone.
    section = " ".join(contracts.split(heading)[1].split("\n## ")[0].split())

    assert f"{len(rows)} rows" in section, (
        f"the invariant table has {len(rows)} rows and the disclosure does not say so"
    )
    assert f"these {len(rows)} relations" in section, (
        f"the invariant table has {len(rows)} rows and the disclosure does not say so"
    )
    assert "machine-checkable artifact rather than a Python module" in section, (
        "the disclosure no longer quotes the ADR 0001 bet it is about"
    )
    assert "satisfy every schema this project publishes and still emit documents" in section
    assert "#147" in section, "the disclosure does not say where the gap is tracked"


def test_every_subcommand_appears_in_the_contract_table() -> None:
    """A command whose inputs have a schema nobody documented is undiscoverable."""
    from exitdrill.cli import _parser

    contracts = CONTRACTS.read_text(encoding="utf-8")
    usage = _parser().format_usage()
    documented = contracts[contracts.index("| Command |") : contracts.index("The rendered HTML")]

    for name in ("validate", "drill", "verify", "compare", "history", "report", "schema"):
        assert name in usage
        assert f"`{name} " in documented or f"`{name}`" in documented, name
