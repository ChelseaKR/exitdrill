"""Prove the canary acceptance scripts' privacy assertions can actually fail.

`scripts/check_directus_canary_demo.py` and
`scripts/check_civicrm_target_roundtrip_demo.py` are the offline acceptance
gates behind `make demo-directus-canary` and `make demo-civicrm-target-canary`.
Between them they carry four privacy assertions: a raw-fixture-value scan over
the Directus command output and written artifacts, and, for CiviCRM, a
secret-shaped-key walk, a raw-sentinel scan, and a filesystem-path scan.

Until now the only thing exercising any of them was a subprocess run of the
whole script against evidence that passes. A passing run cannot distinguish an
assertion that is working from one that has stopped working, which is the same
defect ADR 0021 and ADR 0022 addressed for the sentinel corpora. This module
closes it from the other side: every assertion is shown to fire.

Two things here are derived rather than written down, deliberately:

- the sentinel cases are parametrized over each script's own `_RAW_SENTINELS`
  tuple, so a sentinel added later is proved to fire without anyone
  remembering to add a case; and
- the secret-key cases are parametrized over `_SENSITIVE_KEYS` itself, for the
  same reason.

ADR 0022 made those tuples non-vacuous with respect to the fixtures. This makes
them non-vacuous with respect to the check that consumes them.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from types import ModuleType
from typing import Any, cast

import pytest

PROJECT = Path(__file__).parents[1]


def _script_module(name: str) -> ModuleType:
    """Import one acceptance script without running it.

    Both scripts guard their entry point with `if __name__ == "__main__":`, so
    importing them executes only module-level definitions.
    """
    spec = importlib.util.spec_from_file_location(
        f"exitdrill_canary_gate_{name}", PROJECT / "scripts" / f"{name}.py"
    )
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _directus() -> Any:
    return _script_module("check_directus_canary_demo")


def _civicrm() -> Any:
    return _script_module("check_civicrm_target_roundtrip_demo")


def _directus_sentinels() -> tuple[str, ...]:
    return cast(tuple[str, ...], _directus()._RAW_SENTINELS)


def _civicrm_sentinels() -> tuple[str, ...]:
    return cast(tuple[str, ...], _civicrm()._RAW_SENTINELS)


def _sensitive_keys() -> tuple[str, ...]:
    return tuple(sorted(cast("frozenset[str]", _civicrm()._SENSITIVE_KEYS)))


def _clean_aggregate() -> dict[str, object]:
    """A small stand-in with the shape the CiviCRM assertion walks.

    Nested one level inside a list inside a dict, so a walk that only inspected
    top-level keys would be caught by the secret-key cases below.
    """
    return {
        "decision_scope": "separate_non_composite_evidence_families",
        "entries": [{"artifact_id": "target_interface", "bytes": 1234}],
        "probe_results": [{"id": "record_lookup", "state": "pass"}],
    }


# ---------------------------------------------------------------------------
# The tuples are non-empty. Everything below parametrizes over them, so an
# emptied tuple would silently produce zero test cases instead of failures.
# ---------------------------------------------------------------------------


def test_both_scripts_declare_non_empty_guard_tuples() -> None:
    assert len(_directus_sentinels()) >= 5
    assert len(_civicrm_sentinels()) >= 7
    assert len(_sensitive_keys()) >= 7


# ---------------------------------------------------------------------------
# Directus: _assert_no_raw_values
# ---------------------------------------------------------------------------


def test_directus_raw_value_scan_accepts_evidence_that_carries_none(tmp_path: Path) -> None:
    """The positive control. Without it, an always-raising scan would pass below."""
    artifact = tmp_path / "receipt.json"
    artifact.write_text('{"overall_status":"structurally_restorable"}', encoding="utf-8")

    _directus()._assert_no_raw_values((artifact,), "normalization complete")


@pytest.mark.parametrize("sentinel", _directus_sentinels())
def test_directus_raw_value_scan_fires_for_a_sentinel_in_command_output(sentinel: str) -> None:
    """Every sentinel, in the command-output half of the scanned text."""
    with pytest.raises(RuntimeError, match="disclosed a raw fixture value"):
        _directus()._assert_no_raw_values((), f"normalized {sentinel} into the export")


@pytest.mark.parametrize("sentinel", _directus_sentinels())
def test_directus_raw_value_scan_fires_for_a_sentinel_in_a_written_artifact(
    tmp_path: Path, sentinel: str
) -> None:
    """Every sentinel, in the written-artifact half.

    The two halves are concatenated into one string, so a change that dropped
    either source would leave the other still passing.
    """
    artifact = tmp_path / "report.html"
    artifact.write_text(f"<p>{sentinel}</p>", encoding="utf-8")

    with pytest.raises(RuntimeError, match="disclosed a raw fixture value"):
        _directus()._assert_no_raw_values((artifact,), "")


# ---------------------------------------------------------------------------
# CiviCRM: _assert_aggregate_privacy, three independent failure modes
# ---------------------------------------------------------------------------


def test_civicrm_aggregate_privacy_accepts_evidence_that_carries_none(tmp_path: Path) -> None:
    """The positive control for all three CiviCRM cases below."""
    _civicrm()._assert_aggregate_privacy(_clean_aggregate(), (tmp_path, PROJECT))


@pytest.mark.parametrize("sentinel", _civicrm_sentinels())
def test_civicrm_aggregate_privacy_fires_for_every_sentinel(sentinel: str) -> None:
    aggregate = _clean_aggregate()
    cast("list[dict[str, object]]", aggregate["entries"])[0]["artifact_id"] = sentinel

    with pytest.raises(RuntimeError, match="disclosed a raw fixture sentinel"):
        _civicrm()._assert_aggregate_privacy(aggregate, ())


@pytest.mark.parametrize("key", _sensitive_keys())
@pytest.mark.parametrize("spelling", ["lower", "upper", "title"])
def test_civicrm_aggregate_privacy_fires_for_every_secret_shaped_key(
    key: str, spelling: str
) -> None:
    """Every declared key, nested, and in three casings.

    The walk lowercases each key before comparing. Testing only the lowercase
    spelling would leave that `.lower()` free to be deleted, which is how a
    document carrying `Authorization` would start passing.
    """
    spelled = {"lower": key.lower(), "upper": key.upper(), "title": key.title()}[spelling]
    aggregate = _clean_aggregate()
    cast("list[dict[str, object]]", aggregate["probe_results"])[0][spelled] = "redacted"

    with pytest.raises(RuntimeError, match="exposed a secret field"):
        _civicrm()._assert_aggregate_privacy(aggregate, ())


def test_civicrm_aggregate_privacy_fires_for_a_filesystem_path(tmp_path: Path) -> None:
    aggregate = _clean_aggregate()
    cast("list[dict[str, object]]", aggregate["entries"])[0]["artifact_id"] = str(
        tmp_path / "clean-a"
    )

    with pytest.raises(RuntimeError, match="disclosed a filesystem path"):
        _civicrm()._assert_aggregate_privacy(aggregate, (tmp_path,))


def test_civicrm_aggregate_privacy_walks_past_the_first_level() -> None:
    """A secret key several containers deep must still be found.

    The real aggregate is dicts of lists of dicts, so a walk that stopped at
    the top level would pass on the committed evidence and miss a leak in any
    of the twelve nested result documents.
    """
    aggregate: dict[str, object] = {"a": [{"b": [{"c": {"password": "redacted"}}]}]}

    with pytest.raises(RuntimeError, match="exposed a secret field"):
        _civicrm()._assert_aggregate_privacy(aggregate, ())


def test_civicrm_aggregate_privacy_does_not_manufacture_a_finding(tmp_path: Path) -> None:
    """A value resembling neither a sentinel, a secret key, nor a path passes.

    Keeps the cases above honest: without this, an assertion that raised for
    every input would satisfy all of them.
    """
    aggregate = _clean_aggregate()
    cast("list[dict[str, object]]", aggregate["entries"])[0]["artifact_id"] = "invented-absent-001"

    _civicrm()._assert_aggregate_privacy(aggregate, (tmp_path, PROJECT))


def test_civicrm_aggregate_privacy_rejects_a_document_it_cannot_serialize() -> None:
    """The scan serializes with `allow_nan=False`, so a non-finite number stops it.

    Worth pinning: if that ever became permissive, a document could reach the
    sentinel scan in a form the scan had not actually inspected.
    """
    with pytest.raises(ValueError, match="Out of range float"):
        _civicrm()._assert_aggregate_privacy({"count": float("nan")}, ())


# ---------------------------------------------------------------------------
# The two scans read the same evidence the acceptance run does.
# ---------------------------------------------------------------------------


def test_the_committed_evidence_still_passes_both_scans() -> None:
    """A regression net over the real artifacts, not just constructed ones.

    Uses the committed CiviCRM native browser projections, which are the
    documents the verifier copies into its result artifacts, so this fails if
    a recapture ever lands one carrying a sentinel or a secret-shaped key.
    """
    native = PROJECT / "examples" / "civicrm-6.16.2-target-roundtrip" / "native"
    projections = sorted(native.glob("browser-*.json"))

    assert len(projections) >= 9
    for path in projections:
        _civicrm()._assert_aggregate_privacy(
            json.loads(path.read_text(encoding="utf-8")), (PROJECT,)
        )
