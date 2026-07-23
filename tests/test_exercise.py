import json
from collections.abc import Callable
from pathlib import Path
from shutil import copy
from typing import cast

import pytest

from exitdrill.exercise import ExercisePlanError, load_exercise_plan


def _copy_plan(tmp_path: Path) -> Path:
    source = Path(__file__).parents[1] / "examples" / "synthetic-exercise" / "plan.json"
    destination = tmp_path / "plan.json"
    copy(source, destination)
    return destination


def _raw(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write(path: Path, value: object) -> None:
    path.write_text(json.dumps(value), encoding="utf-8")


def _section(value: dict[str, object], key: str) -> dict[str, object]:
    item = value[key]
    assert isinstance(item, dict)
    return cast(dict[str, object], item)


def _items(value: dict[str, object], key: str) -> list[object]:
    item = value[key]
    assert isinstance(item, list)
    return cast(list[object], item)


def _remove_last_probe(value: dict[str, object]) -> None:
    _items(value, "workflow_probes").pop()


def _duplicate_probe(value: dict[str, object]) -> None:
    probes = _items(value, "workflow_probes")
    probes.append(probes[0])


def test_loads_synthetic_exercise_preflight() -> None:
    path = Path(__file__).parents[1] / "examples" / "synthetic-exercise" / "plan.json"
    plan = load_exercise_plan(path)
    assert plan.exercise_id == "invented-crm-target-preflight-001"
    assert plan.target_system == "Invented AlternateCase Sandbox"


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (lambda raw: raw.update({"data_mode": "production"}), "synthetic_only"),
        (
            lambda raw: _section(raw, "source").update({"customer_obtainable": False}),
            "must be true",
        ),
        (
            lambda raw: _section(raw, "source").update({"transform_command": "curl"}),
            "unknown field",
        ),
        (
            lambda raw: _section(raw, "baseline").update({"captured_before_export": False}),
            "must be true",
        ),
        (
            lambda raw: _section(_section(raw, "baseline"), "coverage").update(
                {"permissions": "assumed"}
            ),
            "coverage is unsupported",
        ),
        (
            lambda raw: _section(raw, "target_sandbox").update({"egress_blocked": False}),
            "must be true",
        ),
        (
            lambda raw: _section(raw, "target_sandbox").update({"production_data_allowed": True}),
            "must be false",
        ),
        (_remove_last_probe, "exactly the five"),
        (_duplicate_probe, "ids must be unique"),
        (
            lambda raw: _section(raw, "evidence_controls").update(
                {"target_readback_required": False}
            ),
            "must be true",
        ),
    ],
)
def test_rejects_unsafe_or_incomplete_exercise_plan(
    tmp_path: Path,
    mutation: Callable[[dict[str, object]], None],
    message: str,
) -> None:
    path = _copy_plan(tmp_path)
    raw = _raw(path)
    mutation(raw)
    _write(path, raw)
    with pytest.raises(ExercisePlanError, match=message):
        load_exercise_plan(path)


def test_rejects_duplicate_exercise_json_key(tmp_path: Path) -> None:
    path = _copy_plan(tmp_path)
    content = path.read_text(encoding="utf-8")
    path.write_text(
        content.replace(
            '"data_mode": "synthetic_only",',
            '"data_mode": "synthetic_only", "data_mode": "synthetic_only",',
        ),
        encoding="utf-8",
    )
    with pytest.raises(ExercisePlanError, match="duplicate object key"):
        load_exercise_plan(path)
