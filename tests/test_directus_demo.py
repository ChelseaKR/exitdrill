import json
import shutil
import subprocess
import sys
from pathlib import Path


def test_directus_native_canary_acceptance() -> None:
    project = Path(__file__).parents[1]
    completed = subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [sys.executable, str(project / "scripts" / "check_directus_canary_demo.py")],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0, completed.stderr
    assert completed.stderr == ""
    summary = json.loads(completed.stdout)
    assert summary == {
        "clean_overall_status": "structurally_restorable",
        "lossy_observed_remediation_signals": 6,
        "lossy_overall_status": "not_structurally_restorable",
        "row_and_file_counts_preserved": True,
        "source_profile": "directus-11.17.4-civic-case/v0.1",
        "status": "native_canary_verified",
    }


def test_lossy_builder_rejects_overlapping_output_paths(tmp_path: Path) -> None:
    project = Path(__file__).parents[1]
    committed = project / "examples" / "directus-11.17.4-civic-case" / "native"
    source = tmp_path / "native"
    shutil.copytree(committed, source)
    script = project / "scripts" / "build_directus_lossy_canary.py"

    cases = (
        (source / "nested-destination", tmp_path / "statement.json"),
        (tmp_path / "lossy-native", tmp_path / "lossy-native" / "statement.json"),
    )
    for destination, statement in cases:
        completed = subprocess.run(  # noqa: S603 - fixed interpreter and repository script
            [
                sys.executable,
                str(script),
                str(source),
                str(destination),
                "--statement",
                str(statement),
            ],
            cwd=project,
            check=False,
            capture_output=True,
            text=True,
        )
        assert completed.returncode == 2
        assert completed.stdout == ""
        assert not destination.exists()
        assert not statement.exists()

    assert not list(source.glob(".directus-lossy-canary.*"))
    assert set(path.name for path in source.iterdir()) == {
        "activity.json",
        "assets",
        "capture-manifest.json",
        "case-people.json",
        "cases.json",
        "files.json",
        "people.json",
        "permissions.json",
        "policies.json",
        "schema.json",
    }


def test_lossy_builder_rejects_unverified_source_without_outputs(tmp_path: Path) -> None:
    project = Path(__file__).parents[1]
    committed = project / "examples" / "directus-11.17.4-civic-case" / "native"
    source = tmp_path / "native"
    shutil.copytree(committed, source)
    (source / "people.json").write_bytes(b' {"data":[]}')
    destination = tmp_path / "lossy-native"
    statement = tmp_path / "statement.json"

    completed = subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [
            sys.executable,
            str(project / "scripts" / "build_directus_lossy_canary.py"),
            str(source),
            str(destination),
            "--statement",
            str(statement),
        ],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert completed.stdout == ""
    assert str(source) not in completed.stderr
    assert str(destination) not in completed.stderr
    assert not destination.exists()
    assert not statement.exists()


def test_lossy_builder_is_pinned_to_the_committed_clean_manifest(tmp_path: Path) -> None:
    project = Path(__file__).parents[1]
    committed = project / "examples" / "directus-11.17.4-civic-case" / "native"
    source = tmp_path / "native"
    shutil.copytree(committed, source)
    manifest_path = source / "capture-manifest.json"
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    manifest["exported_at"] = "2026-08-02T02:38:29.000Z"
    manifest_path.write_text(
        json.dumps(manifest, allow_nan=False, sort_keys=True, separators=(",", ":")) + "\n",
        encoding="utf-8",
    )
    destination = tmp_path / "lossy-native"
    statement = tmp_path / "statement.json"

    completed = subprocess.run(  # noqa: S603 - fixed interpreter and repository script
        [
            sys.executable,
            str(project / "scripts" / "build_directus_lossy_canary.py"),
            str(source),
            str(destination),
            "--statement",
            str(statement),
        ],
        cwd=project,
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 2
    assert "not the committed clean Directus canary" in completed.stderr
    assert str(source) not in completed.stderr
    assert not destination.exists()
    assert not statement.exists()
