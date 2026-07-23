from pathlib import Path

from exitdrill.evaluator import run_drill
from exitdrill.loader import load_baseline, load_export
from exitdrill.models import Dimension, DimensionStatus, OverallStatus


def test_equal_entity_count_can_still_hide_unsafe_exit() -> None:
    project = Path(__file__).parents[1]
    good = project / "examples" / "synthetic-crm"
    lossy = project / "examples" / "synthetic-crm-lossy"
    baseline = load_baseline(good / "baseline.json")
    package = load_export(lossy / "export.json")

    assert len(baseline.entities) == len(package.entities)

    result = run_drill(baseline, package, lossy / "export-files")
    by_dimension = {item.dimension: item for item in result.dimensions}

    assert result.overall_status is OverallStatus.NOT_STRUCTURALLY_RESTORABLE
    assert by_dimension[Dimension.ENTITIES].missing_count == 1
    assert by_dimension[Dimension.ENTITIES].extra_count == 1
    assert by_dimension[Dimension.RELATIONSHIPS].status is DimensionStatus.FAIL
    assert by_dimension[Dimension.ATTACHMENTS].invalid_count == 1
    assert by_dimension[Dimension.PERMISSIONS].status is DimensionStatus.FAIL
    assert by_dimension[Dimension.AUDIT_EVENTS].status is DimensionStatus.FAIL
