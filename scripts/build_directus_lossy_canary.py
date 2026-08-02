#!/usr/bin/env python3
"""Build one deterministic equal-count adversarial Directus canary derivative."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import cast

from exitdrill.directus_canary import DirectusCanaryError, normalize_directus_canary

_MANIFEST_NAME = "capture-manifest.json"
_CLEAN_BUNDLE_SHA256 = "a67048bf25c07b73aa0bff26372090c0a7e5ce77871b49259d0a96110998be49"
_CLEAN_MANIFEST_SHA256 = "b480d003ca7f90aac34c7bb506b67507bfbc32a6832e0b4f5b45b6d1c02ccb20"


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def _read_json(path: Path) -> dict[str, object]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError(f"{path.name} must contain an object")
    return cast(dict[str, object], value)


def _write_json(path: Path, value: object) -> None:
    path.write_bytes(_canonical_bytes(value))


def _data(path: Path) -> list[dict[str, object]]:
    document = _read_json(path)
    raw = document.get("data")
    if not isinstance(raw, list) or not all(isinstance(item, dict) for item in raw):
        raise ValueError(f"{path.name}.data must be an array of objects")
    return cast(list[dict[str, object]], raw)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _mutate(native: Path) -> None:
    cases_path = native / "cases.json"
    cases = _read_json(cases_path)
    case_rows = _data(cases_path)
    if case_rows[1].get("id") != 2 or case_rows[1].get("status") != "open":
        raise ValueError("expected clean synthetic case mutation source was not found")
    case_rows[1]["status"] = "closed"
    cases["data"] = case_rows
    _write_json(cases_path, cases)

    people_path = native / "people.json"
    people = _read_json(people_path)
    people_rows = _data(people_path)
    if people_rows[2].get("id") != 3:
        raise ValueError("expected clean synthetic person mutation source was not found")
    people_rows[2]["id"] = 4
    people["data"] = people_rows
    _write_json(people_path, people)

    links_path = native / "case-people.json"
    links = _read_json(links_path)
    link_rows = _data(links_path)
    if link_rows[0].get("case_id") != 1 or link_rows[0].get("person_id") != 1:
        raise ValueError("expected clean synthetic relationship mutation source was not found")
    link_rows[0]["person_id"] = 2
    links["data"] = link_rows
    _write_json(links_path, links)

    permissions_path = native / "permissions.json"
    permissions = _read_json(permissions_path)
    permission_rows = _data(permissions_path)
    fields = permission_rows[0].get("fields")
    if fields != ["id", "status", "priority", "document"]:
        raise ValueError("expected Directus case permission fields were not found")
    permission_rows[0]["fields"] = [item for item in fields if item != "document"]
    permissions["data"] = permission_rows
    _write_json(permissions_path, permissions)

    activity_path = native / "activity.json"
    activity = _read_json(activity_path)
    activity_rows = _data(activity_path)
    if activity_rows[0].get("id") != 21 or activity_rows[0].get("action") != "create":
        raise ValueError("expected clean synthetic activity mutation source was not found")
    activity_rows[0]["action"] = "update"
    activity["data"] = activity_rows
    _write_json(activity_path, activity)

    attachment_path = native / "assets" / "11111111-1111-4111-8111-111111111111.txt"
    content = attachment_path.read_bytes()
    changed = content.replace(b"alpha", b"omega", 1)
    if changed == content or len(changed) != len(content):
        raise ValueError("expected same-length synthetic attachment token was not found")
    attachment_path.write_bytes(changed)


def _refresh_manifest(native: Path) -> None:
    manifest_path = native / _MANIFEST_NAME
    manifest = _read_json(manifest_path)
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise ValueError("capture manifest files must be an array")
    files: list[dict[str, object]] = []
    for raw in raw_files:
        if not isinstance(raw, dict) or not isinstance(raw.get("path"), str):
            raise ValueError("capture manifest file entry is malformed")
        relative = cast(str, raw["path"])
        path = native / relative
        files.append(
            {
                "bytes": path.stat().st_size,
                "path": relative,
                "sha256": _sha256(path),
            }
        )
    files.sort(key=lambda item: cast(str, item["path"]))
    manifest["files"] = files
    manifest["bundle_sha256"] = hashlib.sha256(_canonical_bytes(files)).hexdigest()
    manifest_path.write_bytes(_canonical_bytes(manifest) + b"\n")


def _resolve_locations(
    source: Path,
    destination: Path,
    statement: Path,
) -> tuple[Path, Path, Path]:
    if source.is_symlink() or destination.is_symlink() or statement.is_symlink():
        raise ValueError("canary paths must not be symbolic links")
    try:
        resolved_source = source.resolve(strict=True)
        resolved_destination = destination.resolve(strict=False)
        resolved_statement = statement.resolve(strict=False)
    except OSError as exc:
        raise ValueError("canary paths could not be resolved") from exc
    if not resolved_source.is_dir():
        raise ValueError("source bundle must be a directory")
    if resolved_destination.exists() or resolved_destination.is_symlink():
        raise ValueError("destination already exists")
    if resolved_statement.exists() or resolved_statement.is_symlink():
        raise ValueError("statement already exists")
    if (
        resolved_destination == resolved_source
        or resolved_destination.is_relative_to(resolved_source)
        or resolved_source.is_relative_to(resolved_destination)
    ):
        raise ValueError("source and destination must not overlap")
    if (
        resolved_statement == resolved_source
        or resolved_statement.is_relative_to(resolved_source)
        or resolved_source.is_relative_to(resolved_statement)
    ):
        raise ValueError("source and statement must not overlap")
    if (
        resolved_statement == resolved_destination
        or resolved_statement.is_relative_to(resolved_destination)
        or resolved_destination.is_relative_to(resolved_statement)
    ):
        raise ValueError("destination and statement must not overlap")
    if resolved_destination.parent != resolved_statement.parent:
        raise ValueError("destination and statement must be siblings")
    return resolved_source, resolved_destination, resolved_statement


def _same_file_identity(left: os.stat_result, right: os.stat_result) -> bool:
    return left.st_dev == right.st_dev and left.st_ino == right.st_ino


def build_lossy_canary(source: Path, destination: Path, statement: Path) -> None:
    """Create a bounded derivative without changing any row or file count."""
    source, destination, statement = _resolve_locations(source, destination, statement)
    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(
            dir=destination.parent,
            prefix=".directus-lossy-canary.",
        ) as temporary_root:
            temporary = Path(temporary_root)
            clean_result = normalize_directus_canary(
                source / _MANIFEST_NAME,
                temporary / "verified-source",
            )
            if (
                clean_result["source_bundle_sha256"] != _CLEAN_BUNDLE_SHA256
                or _sha256(source / _MANIFEST_NAME) != _CLEAN_MANIFEST_SHA256
            ):
                raise ValueError("source is not the committed clean Directus canary")
            working = temporary / "native"
            shutil.copytree(source, working, symlinks=True)
            copied_result = normalize_directus_canary(
                working / _MANIFEST_NAME,
                temporary / "verified-copy",
            )
            if (
                copied_result != clean_result
                or _sha256(working / _MANIFEST_NAME) != _CLEAN_MANIFEST_SHA256
            ):
                raise ValueError("copied source does not match the committed clean canary")
            _mutate(working)
            _refresh_manifest(working)
            lossy_result = normalize_directus_canary(
                working / _MANIFEST_NAME,
                temporary / "verified-derivative",
            )
            if clean_result["counts"] != lossy_result["counts"]:
                raise ValueError("adversarial derivative changed row or file counts")

            staged_statement = temporary / "adversarial-derivative.json"
            staged_statement.write_bytes(
                _canonical_bytes(
                    {
                        "schema_version": "exitdrill/adversarial-derivative/v0.1",
                        "source_bundle": "committed_directus_synthetic_canary",
                        "source_bundle_sha256": _CLEAN_BUNDLE_SHA256,
                        "source_manifest_sha256": _CLEAN_MANIFEST_SHA256,
                        "row_and_file_counts_preserved": True,
                        "mutations": [
                            "critical_field_value",
                            "unreferenced_identity_churn",
                            "relationship_rewire",
                            "attachment_same_length_bytes",
                            "permission_field_collapse",
                            "audit_action_substitution",
                        ],
                    }
                )
                + b"\n"
            )
            staged_identity = staged_statement.stat()
            os.link(staged_statement, statement, follow_symlinks=False)
            try:
                working.rename(destination)
            except BaseException:
                try:
                    published_identity = statement.stat(follow_symlinks=False)
                    if _same_file_identity(staged_identity, published_identity):
                        statement.unlink()
                except OSError:
                    pass
                raise
    except DirectusCanaryError:
        raise
    except (OSError, shutil.Error) as exc:
        raise ValueError("adversarial derivative could not be built") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--statement", type=Path, required=True)
    args = parser.parse_args()
    try:
        build_lossy_canary(args.source, args.destination, args.statement)
    except (OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
