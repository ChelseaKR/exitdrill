#!/usr/bin/env node
// Bind each committed browser-*.json to the exact literal its capture
// script declares as its output on a successful run -- without needing a
// live CiviCRM instance, Playwright, or Docker (issue #31).
//
// Most fields in these nine observations are hardcoded literals: the
// script writes them unconditionally once every live browser, network,
// and DOM assertion above them has passed. This check extracts that
// literal text directly from each committed .mjs script's source and
// requires it to canonically equal the corresponding committed JSON file.
// Editing the committed JSON without updating the script's declared
// output -- or the reverse -- now fails here, offline, on every run.
//
// It deliberately cannot verify the small set of fields that only a live
// page can produce: axe-core's rule counts, its version, and the violation
// list (browser-accessibility.json), and the measured tab-count to reach
// a keyboard target (browser-keyboard.json). Those fields are listed in
// DYNAMIC_FIELD_PATHS and excluded from comparison below rather than
// silently trusted. Nothing here proves they still match live CiviCRM
// behavior; only a real recapture can (see the repository docs for that
// separate, opt-in workflow).

import { readFileSync } from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const NATIVE_DIR = path.join(ROOT, "examples", "civicrm-6.16.2-target-roundtrip", "native");
const SENTINEL = "__EXITDRILL_LIVE_VALUE_NOT_STATICALLY_VERIFIED__";

const DYNAMIC_FIELD_PATHS = {
  "browser-accessibility.json": [
    "engine_version",
    "incomplete_rule_count",
    "inapplicable_rule_count",
    "passes_rule_count",
    "violations",
  ],
  "browser-keyboard.json": ["tab_steps_to_roles_summary"],
};

const BINDINGS = [
  { script: "civicrm_browser_access_allow_control.mjs", outputs: { top: "browser-access-allow-control.json" } },
  { script: "civicrm_browser_access_denial.mjs", outputs: { top: "browser-access-denial.json" } },
  { script: "civicrm_browser_case_search_workflow.mjs", outputs: { top: "browser-case-search-workflow.json" } },
  {
    script: "civicrm_browser_workflow.mjs",
    outputs: {
      activity_view: "browser-activity-view.json",
      accessibility: "browser-accessibility.json",
      case_client_workflow: "browser-case-client-workflow.json",
      contact_summary_workflow: "browser-contact-summary-workflow.json",
      keyboard: "browser-keyboard.json",
      workflow: "browser-workflow.json",
    },
  },
];

function extractStdoutLiteralSource(source, scriptName) {
  const marker = "process.stdout.write(";
  const markerIndex = source.indexOf(marker);
  if (markerIndex === -1) {
    throw new Error(`${scriptName}: no process.stdout.write(...) call found`);
  }
  const literalMarker = "JSON.stringify(";
  const literalMarkerIndex = source.indexOf(literalMarker, markerIndex);
  if (literalMarkerIndex === -1) {
    throw new Error(`${scriptName}: no JSON.stringify(...) after process.stdout.write`);
  }
  const literalStart = literalMarkerIndex + literalMarker.length;
  let depth = 1;
  let index = literalStart;
  while (depth > 0) {
    if (index >= source.length) {
      throw new Error(`${scriptName}: unbalanced parentheses while extracting the declared literal`);
    }
    if (source[index] === "(") depth += 1;
    else if (source[index] === ")") depth -= 1;
    index += 1;
  }
  return source.slice(literalStart, index - 1);
}

function evaluateLiteral(literalSource, scriptName) {
  // Stub the small, fixed set of identifiers these literals reference
  // inline instead of embedding as constants. Two kinds:
  //
  // - Genuinely live-only (civicrm_browser_workflow.mjs's accessibility
  //   and keyboard blocks): stubbed to SENTINEL. Every value a SENTINEL
  //   can reach lands only at a DYNAMIC_FIELD_PATHS location below and is
  //   excluded from comparison, never trusted as a real observation.
  // - Provably constant by an assertion earlier in the same script
  //   (civicrm_browser_case_search_workflow.mjs requires
  //   `pageErrors.length === 2` before it can reach this literal):
  //   stubbed to that proven value, so the comparison stays real instead
  //   of being excluded.
  const stubPrelude = `
    const rawAccessibility = {
      incomplete: { length: ${JSON.stringify(SENTINEL)} },
      inapplicable: { length: ${JSON.stringify(SENTINEL)} },
      passes: { length: ${JSON.stringify(SENTINEL)} },
    };
    const violations = ${JSON.stringify(SENTINEL)};
    const tabStepsToRolesSummary = ${JSON.stringify(SENTINEL)};
    const axe = { version: ${JSON.stringify(SENTINEL)} };
    const pageErrors = { length: 2 };
  `;
  try {
    // eslint-disable-next-line no-new-func -- evaluating this repository's
    // own committed source, the same trust boundary `node --check` uses.
    return new Function(`${stubPrelude}\nreturn (${literalSource});`)();
  } catch (error) {
    throw new Error(`${scriptName}: could not evaluate its declared literal: ${error.message}`);
  }
}

function blankDynamicFields(value, outputName) {
  const dynamicKeys = DYNAMIC_FIELD_PATHS[outputName];
  if (!dynamicKeys) return value;
  const clone = JSON.parse(JSON.stringify(value));
  for (const key of dynamicKeys) {
    if (!(key in clone)) {
      throw new Error(`${outputName}: expected live-only field "${key}" is missing`);
    }
    clone[key] = SENTINEL;
  }
  return clone;
}

function canonical(value) {
  const sortKeys = (input) => {
    if (Array.isArray(input)) return input.map(sortKeys);
    if (input !== null && typeof input === "object") {
      return Object.fromEntries(Object.keys(input).sort().map((key) => [key, sortKeys(input[key])]));
    }
    return input;
  };
  return JSON.stringify(sortKeys(value));
}

function main() {
  const failures = [];
  let checked = 0;
  for (const binding of BINDINGS) {
    const scriptPath = path.join(ROOT, "scripts", binding.script);
    const source = readFileSync(scriptPath, "utf8");
    let literalValue;
    try {
      const literalSource = extractStdoutLiteralSource(source, binding.script);
      literalValue = evaluateLiteral(literalSource, binding.script);
    } catch (error) {
      failures.push(error.message);
      continue;
    }
    const outputEntries = Object.entries(binding.outputs);
    const isSingleOutput = outputEntries.length === 1 && outputEntries[0][0] === "top";
    for (const [key, outputName] of outputEntries) {
      const scriptValue = isSingleOutput ? literalValue : literalValue[key];
      if (scriptValue === undefined) {
        failures.push(`${binding.script}: declared no "${key}" field for ${outputName}`);
        continue;
      }
      const committedPath = path.join(NATIVE_DIR, outputName);
      let committedValue;
      try {
        committedValue = JSON.parse(readFileSync(committedPath, "utf8"));
      } catch (error) {
        failures.push(`${outputName}: could not read or parse the committed file: ${error.message}`);
        continue;
      }
      const expected = canonical(blankDynamicFields(scriptValue, outputName));
      const actual = canonical(blankDynamicFields(committedValue, outputName));
      checked += 1;
      if (expected !== actual) {
        const excluded = DYNAMIC_FIELD_PATHS[outputName];
        failures.push(
          `${outputName} does not match the literal ${binding.script} declares as its output` +
            (excluded ? ` (excluding live-only fields: ${excluded.join(", ")})` : ""),
        );
      }
    }
  }
  if (failures.length > 0) {
    for (const failure of failures) process.stderr.write(`${failure}\n`);
    process.exitCode = 1;
    return;
  }
  process.stdout.write(
    `verified ${checked} committed browser-*.json files bind to the literal their capture script declares\n`,
  );
}

main();
