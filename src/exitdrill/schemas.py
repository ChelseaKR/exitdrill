"""The public JSON Schemas, and the one place that finds and compiles them.

ADR 0001's whole bet is that other people write the source-specific normalizer.
Until now only the comparison document had a schema an outside implementer could
run: the receipt and both input contracts were defined by Python validators,
which such an implementer can read but cannot execute in their own language, and
a reviewer handed a receipt could check its shape only by trusting the producer's
code.

These schemas are a second, independently maintained check beside the semantic
validators, in the same relationship the comparison schema has always had to
`_build_comparison`. They express closed structure and every invariant that is
locally expressible in Draft 2020-12. They deliberately do not express the
arithmetic relations between sibling counts, the status algebra, the payload
checksum, or the offset-aware timestamp rule -- no schema can, and pretending
otherwise would leave a reader believing a passing schema check had established
something it had not. `docs/DATA-CONTRACTS.md` lists each of those by name, and
`tests/test_schemas.py` holds that list against the validators.

Schemas are read from the wheel when there is one and from the checkout
otherwise, so `exitdrill schema show` prints the same bytes either way.
"""

from __future__ import annotations

import json
from functools import lru_cache
from importlib.resources import files
from pathlib import Path

from jsonschema import Draft202012Validator, SchemaError, ValidationError

# Every schema this package publishes, in the order `schema list` prints them.
# The literals are what `scripts/check_wheel.py` greps for to decide that a
# committed schema is one real code can open (issue #33).
PUBLIC_SCHEMA_NAMES: tuple[str, ...] = (
    "baseline-v0.3.schema.json",
    "exercise-plan-v0.1.schema.json",
    "export-v0.1.schema.json",
    "receipt-comparison-v0.1.schema.json",
    "receipt-history-v0.1.schema.json",
    "receipt-v0.3.schema.json",
)

BASELINE_SCHEMA = "baseline-v0.3.schema.json"
EXERCISE_PLAN_SCHEMA = "exercise-plan-v0.1.schema.json"
EXPORT_SCHEMA = "export-v0.1.schema.json"
RECEIPT_SCHEMA = "receipt-v0.3.schema.json"


class SchemaResourceError(ValueError):
    """Raised when a published schema is missing, unreadable, or not a schema."""


def read_schema_bytes(name: str) -> bytes:
    """Return one published schema's exact committed bytes, wheel or checkout.

    The wheel carries the schemas under `exitdrill/schemas/`; a checkout has
    them at the repository root. Both paths are tried so the packaged command
    and a developer running from source print byte-identical documents.
    """
    if name not in PUBLIC_SCHEMA_NAMES:
        raise SchemaResourceError(f"{name} is not a published schema")
    packaged = files("exitdrill").joinpath("schemas", name)
    try:
        return packaged.read_bytes()
    except FileNotFoundError:
        return (Path(__file__).parents[2] / "schemas" / name).read_bytes()


@lru_cache(maxsize=len(PUBLIC_SCHEMA_NAMES))
def schema_validator(name: str) -> Draft202012Validator:
    """Compile one published schema, refusing a document that is not a schema."""
    schema = json.loads(read_schema_bytes(name))
    try:
        Draft202012Validator.check_schema(schema)
    except SchemaError as exc:
        raise SchemaResourceError(f"packaged schema {name} is invalid") from exc
    return Draft202012Validator(schema)


def validate_against_schema(
    name: str,
    document: object,
    error: type[Exception],
    label: str,
) -> None:
    """Require closed-structure conformance, raising the caller's own error type.

    `error` and `label` are the caller's, so each contract keeps the rejection
    wording its own tests match rather than every document failing with one
    generic sentence.
    """
    try:
        schema_validator(name).validate(document)
    except ValidationError as exc:
        raise error(f"{label} does not satisfy the public {label} schema") from exc
