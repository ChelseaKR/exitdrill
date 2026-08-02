import hashlib
import json
import shutil
import subprocess
import sys
from pathlib import Path


def _tree_digest(root: Path) -> str:
    digest = hashlib.sha256()
    for path in sorted(item for item in root.rglob("*") if item.is_file()):
        digest.update(path.relative_to(root).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def _run_builder(
    project: Path, source: Path, destination: Path
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [
            sys.executable,
            str(project / "scripts" / "build_civicrm_target_adversaries.py"),
            str(source),
            str(destination),
        ],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )


def test_civicrm_target_roundtrip_canary_acceptance() -> None:
    project = Path(__file__).parents[1]
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [
            sys.executable,
            str(project / "scripts" / "check_civicrm_target_roundtrip_demo.py"),
        ],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    assert json.loads(completed.stdout) == {
        "adversarial_controls_detected": 5,
        "clean_observed_remediation_signals": 6,
        "clean_overall_status": "not_structurally_restorable",
        "clean_target_probe_passes": 5,
        "source_profile": "directus-11.17.4-civic-case/v0.1",
        "status": "civicrm_target_roundtrip_canary_verified",
        "target_profile": ("directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1"),
    }


def test_civicrm_adversary_builder_preserves_source_and_publishes_closed_set(
    tmp_path: Path,
) -> None:
    project = Path(__file__).parents[1]
    committed = project / "examples" / "civicrm-6.16.2-target-roundtrip" / "native"
    source = tmp_path / "source"
    destination = tmp_path / "adversaries"
    shutil.copytree(committed, source)
    before = _tree_digest(source)

    completed = _run_builder(project, source, destination)

    assert completed.returncode == 0, completed.stderr
    assert completed.stdout == ""
    assert completed.stderr == ""
    assert _tree_digest(source) == before
    assert {item.name for item in destination.iterdir()} == {
        "scalar-substitution",
        "relationship-rewire",
        "attachment-corruption",
        "permission-escalation",
        "nonempty-precondition",
        "adversarial-derivatives.json",
    }
    statement = json.loads(
        (destination / "adversarial-derivatives.json").read_text(encoding="utf-8")
    )
    assert statement["target_data_row_counts_preserved"] is True
    assert statement["attachment_file_counts_and_sizes_preserved"] is True
    assert not list(tmp_path.glob(".civicrm-target-adversaries.*"))


def test_civicrm_adversary_builder_rejects_overlapping_output(tmp_path: Path) -> None:
    project = Path(__file__).parents[1]
    committed = project / "examples" / "civicrm-6.16.2-target-roundtrip" / "native"
    source = tmp_path / "source"
    shutil.copytree(committed, source)
    destination = source / "nested-adversaries"

    completed = _run_builder(project, source, destination)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "must not overlap" in completed.stderr
    assert str(source) not in completed.stderr
    assert not destination.exists()


def test_civicrm_adversary_builder_rejects_uncommitted_manifest_without_output(
    tmp_path: Path,
) -> None:
    project = Path(__file__).parents[1]
    committed = project / "examples" / "civicrm-6.16.2-target-roundtrip" / "native"
    source = tmp_path / "source"
    destination = tmp_path / "adversaries"
    shutil.copytree(committed, source)
    manifest_path = source / "capture-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["target_version"] = "6.16.3"
    manifest_path.write_text(
        json.dumps(manifest, allow_nan=False, separators=(",", ":"), sort_keys=True) + "\n",
        encoding="utf-8",
    )

    completed = _run_builder(project, source, destination)

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert "not the committed clean CiviCRM target canary" in completed.stderr
    assert str(source) not in completed.stderr
    assert not destination.exists()
    assert not list(tmp_path.glob(".civicrm-target-adversaries.*"))
