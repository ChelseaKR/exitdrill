.PHONY: install format lint lint-lab type test verify package demo demo-lossy demo-compare demo-compare-policy demo-directus-canary demo-civicrm-target-canary

install:
	uv sync --locked

format:
	uv run ruff format .

lint:
	uv run ruff format --check .
	uv run ruff check .

lint-lab:
	@set -e; \
	checked=0; \
	for script in $$(git ls-files '*.mjs'); do \
		node --check "$$script"; \
		checked=$$((checked + 1)); \
	done; \
	test "$$checked" -gt 0; \
	echo "syntax-checked $$checked browser-lab scripts"

type:
	uv run mypy

test:
	uv run pytest

verify: lint type test

package:
	uv build --clear
	uv run python scripts/check_wheel.py

demo:
	mkdir -p examples/synthetic-crm/out
	uv run exitdrill validate-exercise examples/synthetic-exercise/plan.json
	uv run exitdrill validate examples/synthetic-crm/baseline.json examples/synthetic-crm/export.json
	uv run exitdrill drill examples/synthetic-crm/baseline.json examples/synthetic-crm/export.json --attachment-root examples/synthetic-crm/export-files --out examples/synthetic-crm/out/receipt.json --claimed-generated-at 2026-07-22T20:00:00Z
	uv run exitdrill verify examples/synthetic-crm/out/receipt.json --baseline examples/synthetic-crm/baseline.json --export examples/synthetic-crm/export.json --attachment-root examples/synthetic-crm/export-files
	uv run exitdrill report examples/synthetic-crm/out/receipt.json --out examples/synthetic-crm/out/report.html

demo-lossy:
	@mkdir -p examples/synthetic-crm-lossy/out
	@receipt=$$(mktemp examples/synthetic-crm-lossy/out/receipt.XXXXXX); \
	status=0; \
	uv run exitdrill drill examples/synthetic-crm/baseline.json examples/synthetic-crm-lossy/export.json --attachment-root examples/synthetic-crm-lossy/export-files --out "$$receipt" --claimed-generated-at 2026-07-22T20:05:00Z || status=$$?; \
	test $$status -eq 2; \
	uv run python -c 'import json, sys; receipt = json.load(open(sys.argv[1], encoding="utf-8")); assert receipt["payload"]["overall_status"] == "not_structurally_restorable"' "$$receipt"; \
	mv "$$receipt" examples/synthetic-crm-lossy/out/receipt.json
	@uv run exitdrill report examples/synthetic-crm-lossy/out/receipt.json --out examples/synthetic-crm-lossy/out/report.html >/dev/null

demo-compare: demo demo-lossy
	@uv run exitdrill compare examples/synthetic-crm/out/receipt.json examples/synthetic-crm-lossy/out/receipt.json --out examples/synthetic-crm/out/comparison.json
	@uv run exitdrill verify-comparison examples/synthetic-crm/out/comparison.json --reference examples/synthetic-crm/out/receipt.json --candidate examples/synthetic-crm-lossy/out/receipt.json
	@uv run python scripts/summarize_synthetic_demo.py

demo-compare-policy: demo-compare
	@status=0; \
	uv run exitdrill compare examples/synthetic-crm/out/receipt.json examples/synthetic-crm-lossy/out/receipt.json --fail-on-loss-signal-increase || status=$$?; \
	test $$status -eq 3

demo-directus-canary:
	uv run python scripts/check_directus_canary_demo.py

demo-civicrm-target-canary:
	uv run python scripts/check_civicrm_target_roundtrip_demo.py
	node scripts/check_browser_capture_bindings.mjs
