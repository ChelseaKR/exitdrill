#!/usr/bin/env python3
"""Build disposable adversarial derivatives of the pinned CiviCRM target capture."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
from collections.abc import Callable, Mapping
from pathlib import Path
from typing import cast

from exitdrill.civicrm_target_canary import (
    CiviCRMTargetCanaryError,
    normalize_civicrm_target_canary,
)

PROJECT = Path(__file__).parents[1]
COMMITTED_NATIVE = PROJECT / "examples" / "civicrm-6.16.2-target-roundtrip" / "native"
MANIFEST_NAME = "capture-manifest.json"

SCALAR_SUBSTITUTION = "scalar-substitution"
RELATIONSHIP_REWIRE = "relationship-rewire"
ATTACHMENT_CORRUPTION = "attachment-corruption"
PERMISSION_ESCALATION = "permission-escalation"
NONEMPTY_PRECONDITION = "nonempty-precondition"
STATEMENT_NAME = "adversarial-derivatives.json"

_ASSET_ID = "11111111-1111-4111-8111-111111111111"
_DATA_FILES = (
    "contacts.json",
    "cases.json",
    "relationships.json",
    "files.json",
    "entity-files.json",
)
_MAX_JSON_BYTES = 2 * 1024 * 1024


def _reject_constant(value: str) -> object:
    raise ValueError(f"non-finite JSON value is not permitted: {value}")


def _object_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
    result: dict[str, object] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON object key is not permitted")
        result[key] = value
    return result


def _read_object(path: Path) -> dict[str, object]:
    if path.stat().st_size > _MAX_JSON_BYTES:
        raise ValueError("adversarial source JSON exceeds its size limit")
    value = json.loads(
        path.read_text(encoding="utf-8"),
        object_pairs_hook=_object_pairs,
        parse_constant=_reject_constant,
    )
    if not isinstance(value, dict):
        raise ValueError("adversarial source JSON must contain an object")
    return cast(dict[str, object], value)


def _canonical_bytes(value: object) -> bytes:
    return json.dumps(
        value,
        allow_nan=False,
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")


def _write_object(path: Path, value: object) -> None:
    path.write_bytes(_canonical_bytes(value) + b"\n")


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _api_values(path: Path) -> tuple[dict[str, object], list[dict[str, object]]]:
    document = _read_object(path)
    raw_values = document.get("values")
    if not isinstance(raw_values, list) or not all(isinstance(item, dict) for item in raw_values):
        raise ValueError(f"{path.name} does not contain an APIv4 values array")
    return document, cast(list[dict[str, object]], raw_values)


def _replace_exact(value: object, before: str, after: str) -> tuple[object, int]:
    if value == before:
        return after, 1
    if isinstance(value, list):
        changed: list[object] = []
        replacements = 0
        for item in value:
            replacement, count = _replace_exact(item, before, after)
            changed.append(replacement)
            replacements += count
        return changed, replacements
    if isinstance(value, dict):
        changed_object: dict[str, object] = {}
        replacements = 0
        for key, item in value.items():
            replacement, count = _replace_exact(item, before, after)
            changed_object[key] = replacement
            replacements += count
        return changed_object, replacements
    return value, 0


def _mutate_scalar(native: Path) -> None:
    path = native / "contacts.json"
    document = _read_object(path)
    changed, replacements = _replace_exact(
        document,
        "Synthetic Person Alpha",
        "Synthetic Person Omega",
    )
    if replacements == 0:
        raise ValueError("expected clean synthetic scalar was not found")
    _write_object(path, changed)


def _relationship_endpoint(rows: list[dict[str, object]]) -> str:
    preferred = ("contact_id_b", "contact_id", "client_id", "case_id", "person_id")
    for key in preferred:
        values = [row.get(key) for row in rows]
        if all(
            isinstance(value, int | str) and not isinstance(value, bool) for value in values
        ) and len(set(values)) == len(values):
            return key
    common = set(rows[0])
    for row in rows[1:]:
        common &= set(row)
    for key in sorted(common):
        lowered = key.lower()
        if key == "id" or "type" in lowered or not lowered.endswith("_id"):
            continue
        values = [row[key] for row in rows]
        if all(
            isinstance(value, int | str) and not isinstance(value, bool) for value in values
        ) and len(set(values)) == len(values):
            return key
    raise ValueError("expected distinct relationship endpoints were not found")


def _mutate_relationship(native: Path) -> None:
    path = native / "relationships.json"
    document, rows = _api_values(path)
    if len(rows) != 2:
        raise ValueError("expected exactly two clean synthetic relationships")
    endpoint = _relationship_endpoint(rows)
    _contacts, contact_rows = _api_values(native / "contacts.json")
    contact_ids = [row.get("id") for row in contact_rows]
    if not all(
        isinstance(value, int | str) and not isinstance(value, bool) for value in contact_ids
    ):
        raise ValueError("expected clean synthetic contact ids were not found")
    existing_endpoints = {row[endpoint] for row in rows}
    replacements = [value for value in contact_ids if value not in existing_endpoints]
    if len(replacements) != 1:
        raise ValueError("expected one unreferenced synthetic relationship endpoint")
    rows[0][endpoint] = replacements[0]
    document["values"] = rows
    _write_object(path, document)


def _mutate_attachment(native: Path) -> None:
    path = native / "assets" / f"{_ASSET_ID}.txt"
    content = path.read_bytes()
    changed = content.replace(b"alpha", b"omega", 1)
    if changed == content or len(changed) != len(content):
        raise ValueError("expected same-length synthetic attachment token was not found")
    path.write_bytes(changed)


def _mutate_permission(native: Path) -> None:
    allow = _read_object(native / "permission-allow.json")
    deny_path = native / "permission-deny.json"
    deny = _read_object(deny_path)
    allow_values = allow.get("values")
    deny_values = deny.get("values")
    if (
        not isinstance(allow_values, list)
        or len(allow_values) != 1
        or not isinstance(deny_values, list)
        or deny_values
    ):
        raise ValueError("expected clean allow and deny probe outcomes were not found")
    _write_object(deny_path, allow)


def _mutate_nonempty_manifest(native: Path) -> None:
    manifest_path = native / MANIFEST_NAME
    manifest = _read_object(manifest_path)
    sandbox = manifest.get("sandbox")
    if not isinstance(sandbox, dict):
        raise ValueError("capture manifest sandbox must be an object")
    mutable = cast(dict[str, object], sandbox)
    if mutable.get("application_empty_before_write") is not True:
        raise ValueError("expected clean empty-target precondition was not found")
    mutable["application_empty_before_write"] = False
    manifest["sandbox"] = mutable
    _write_object(manifest_path, manifest)


def _refresh_manifest(native: Path) -> None:
    manifest_path = native / MANIFEST_NAME
    manifest = _read_object(manifest_path)
    raw_files = manifest.get("files")
    if not isinstance(raw_files, list):
        raise ValueError("capture manifest files must be an array")
    files: list[dict[str, object]] = []
    for raw in raw_files:
        if not isinstance(raw, Mapping) or not isinstance(raw.get("path"), str):
            raise ValueError("capture manifest file entry is malformed")
        relative = cast(str, raw["path"])
        path = native / relative
        files.append({"bytes": path.stat().st_size, "path": relative, "sha256": _sha256(path)})
    manifest["files"] = files
    manifest["bundle_sha256"] = hashlib.sha256(_canonical_bytes(files)).hexdigest()
    _write_object(manifest_path, manifest)


def _data_shape(native: Path) -> tuple[tuple[str, int], ...]:
    return tuple((name, len(_api_values(native / name)[1])) for name in _DATA_FILES)


def _asset_shape(native: Path) -> tuple[tuple[str, int], ...]:
    assets = native / "assets"
    return tuple(
        (path.name, path.stat().st_size)
        for path in sorted(assets.iterdir())
        if path.is_file() and not path.is_symlink()
    )


def _copy_and_mutate(
    source: Path,
    destination: Path,
    mutation: Callable[[Path], None],
    *,
    refresh: bool = True,
) -> None:
    shutil.copytree(source, destination, symlinks=True)
    mutation(destination)
    if refresh:
        _refresh_manifest(destination)


def _resolve_locations(source: Path, destination: Path) -> tuple[Path, Path]:
    if source.is_symlink() or destination.is_symlink():
        raise ValueError("adversarial bundle paths must not be symbolic links")
    try:
        resolved_source = source.resolve(strict=True)
        resolved_destination = destination.resolve(strict=False)
    except OSError as exc:
        raise ValueError("adversarial bundle paths could not be resolved") from exc
    if not resolved_source.is_dir():
        raise ValueError("adversarial source must be a directory")
    if resolved_destination.exists() or resolved_destination.is_symlink():
        raise ValueError("adversarial destination already exists")
    if (
        resolved_source == resolved_destination
        or resolved_destination.is_relative_to(resolved_source)
        or resolved_source.is_relative_to(resolved_destination)
    ):
        raise ValueError("adversarial source and destination must not overlap")
    return resolved_source, resolved_destination


def _require_committed_source(source: Path) -> None:
    committed_manifest = COMMITTED_NATIVE / MANIFEST_NAME
    if not committed_manifest.is_file():
        raise ValueError("committed clean target manifest is unavailable")
    if _sha256(source / MANIFEST_NAME) != _sha256(committed_manifest):
        raise ValueError("source is not the committed clean CiviCRM target canary")


def build_target_adversaries(source: Path, destination: Path) -> None:
    """Build five fresh derivatives without changing the committed source bundle."""
    source, destination = _resolve_locations(source, destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    try:
        with tempfile.TemporaryDirectory(
            dir=destination.parent,
            prefix=".civicrm-target-adversaries.",
        ) as temporary_root:
            temporary = Path(temporary_root)
            _require_committed_source(source)
            normalize_civicrm_target_canary(
                source / MANIFEST_NAME,
                temporary / "verified-clean",
            )
            clean_data_shape = _data_shape(source)
            clean_asset_shape = _asset_shape(source)
            staged = temporary / "adversaries"
            staged.mkdir()
            variants = (
                (SCALAR_SUBSTITUTION, _mutate_scalar, True),
                (RELATIONSHIP_REWIRE, _mutate_relationship, True),
                (ATTACHMENT_CORRUPTION, _mutate_attachment, True),
                (PERMISSION_ESCALATION, _mutate_permission, True),
                (NONEMPTY_PRECONDITION, _mutate_nonempty_manifest, True),
            )
            for name, mutation, refresh in variants:
                variant = staged / name
                _copy_and_mutate(source, variant, mutation, refresh=refresh)
                if _data_shape(variant) != clean_data_shape:
                    raise ValueError("adversarial derivative changed target data row counts")
                if _asset_shape(variant) != clean_asset_shape:
                    raise ValueError(
                        "adversarial derivative changed attachment file counts or sizes"
                    )
            _write_object(
                staged / STATEMENT_NAME,
                {
                    "attachment_file_counts_and_sizes_preserved": True,
                    "mutations": [name for name, _mutation, _refresh in variants],
                    "schema_version": "exitdrill/civicrm-target-adversaries/v0.1",
                    "source_manifest_sha256": _sha256(source / MANIFEST_NAME),
                    "target_data_row_counts_preserved": True,
                    "target_profile": (
                        "directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1"
                    ),
                },
            )
            staged.rename(destination)
    except CiviCRMTargetCanaryError:
        raise
    except (OSError, shutil.Error) as exc:
        raise ValueError("CiviCRM target adversaries could not be built") from exc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("destination", type=Path)
    args = parser.parse_args()
    try:
        build_target_adversaries(args.source, args.destination)
    except (CiviCRMTargetCanaryError, OSError, ValueError) as exc:
        parser.error(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
