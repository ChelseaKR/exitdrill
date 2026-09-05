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

// Each entry is a TOP-LEVEL key of the observation named on the left, not a
// dotted path, despite this table's name. Every live-only field these nine
// captures carry is top-level, so `blankDynamicFields` looks keys up directly.
// A nested live-only field cannot be expressed here today; adding one is
// rejected by name below rather than misreported as missing (issue #87).
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

// `evaluateLiteral` stubs `pageErrors` as a fabricated `{ length: 2 }` rather
// than a SENTINEL, and applies that stub to every script's literal. A SENTINEL
// landing anywhere unexpected compares unequal and fails loudly; a fabricated
// plausible number does not. That stub is safe only while two facts hold, so
// both are checked here on every run instead of being asserted in a comment
// (issue #87):
//
//   1. Exactly one capture script reads `pageErrors` inside its declared
//      literal. Three others collect `pageErrors` for their own assertions and
//      may not emit a count from it: `browser-contact-summary-workflow.json`
//      and `browser-workflow.json` both record an occurrence_count of 2, so a
//      literal that started reading `pageErrors.length` there would be
//      compared against the fabricated 2, match, and still report "verified 9".
//   2. That one script cannot reach its literal unless `pageErrors.length === 2`,
//      which is what makes the fabricated value a proven one rather than a guess.
const PAGE_ERRORS_STUB_OWNER = "civicrm_browser_case_search_workflow.mjs";
const PAGE_ERRORS_STUB_GUARD = /pageErrors\.length\s*!==\s*2/;
const PAGE_ERRORS_REFERENCE = /\bpageErrors\b/;

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
  // Floor the number of writes before locating one, the way `lint-lab` floors
  // its count with `test "$checked" -gt 0` and `main()` floors `checked` below
  // (issue #88). This extractor takes the FIRST `process.stdout.write(` and the
  // first `JSON.stringify(` after it, so a capture script that gains an earlier
  // write -- a progress line, a warning, a debug dump -- silently rebinds this
  // gate to a different literal. The loud outcome is an evaluation or
  // comparison failure; the quiet one is an earlier write that is itself
  // JSON-shaped, which gets compared against the committed capture instead
  // while the success line still reads "verified 9". Requiring exactly one
  // write makes that edit fail here, by name, instead. A count of zero lands
  // here too, so there is no separate not-found branch to leave untested.
  const writeCount = source.split(marker).length - 1;
  if (writeCount !== 1) {
    throw new Error(
      `${scriptName}: expected exactly one process.stdout.write( call, found ${writeCount}; ` +
        "this gate binds the committed capture to the literal that follows the first one, so a " +
        "second write can rebind it to a different document without changing its success line",
    );
  }
  const markerIndex = source.indexOf(marker);
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

function assertPageErrorsStubStillProven(scriptName, source, literalSource) {
  // The two facts recorded above PAGE_ERRORS_STUB_OWNER, checked against the
  // extracted literal rather than the whole file: all four capture scripts
  // legitimately mention `pageErrors` outside their declared literal, so a
  // file-wide search would report every one of them.
  const declaresPageErrors = PAGE_ERRORS_REFERENCE.test(literalSource);
  if (scriptName !== PAGE_ERRORS_STUB_OWNER) {
    if (declaresPageErrors) {
      throw new Error(
        `${scriptName}: its declared literal reads pageErrors, but only ${PAGE_ERRORS_STUB_OWNER} ` +
          "proves pageErrors.length === 2 before reaching its literal; this gate would compare " +
          "the committed capture against a fabricated 2 that nothing in this script establishes",
      );
    }
    return;
  }
  if (!declaresPageErrors) {
    throw new Error(
      `${PAGE_ERRORS_STUB_OWNER}: its declared literal no longer reads pageErrors, so the ` +
        "fabricated { length: 2 } stub in evaluateLiteral has outlived the one literal it was " +
        "written for; delete the stub and this check together, or re-point them at their new owner",
    );
  }
  if (!PAGE_ERRORS_STUB_GUARD.test(source)) {
    throw new Error(
      `${PAGE_ERRORS_STUB_OWNER}: nothing here requires pageErrors.length === 2 before the ` +
        "declared literal is reached, so the fabricated { length: 2 } stub in evaluateLiteral is " +
        "no longer a proven value; restore the guard or stop stubbing pageErrors",
    );
  }
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
  //   of being excluded. Both halves of that proof -- the guard, and the
  //   fact that no other script's literal reads `pageErrors` -- are
  //   enforced by assertPageErrorsStubStillProven above, not assumed.
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
    // DYNAMIC_FIELD_PATHS holds top-level keys, not paths (see its comment).
    // A dotted entry would look up a key that no observation has and fail as
    // "expected live-only field is missing", which reads as a broken capture
    // rather than as an unsupported exclusion. Say which it is (issue #87).
    if (key.includes(".")) {
      throw new Error(
        `${outputName}: "${key}" reads as a nested path, but DYNAMIC_FIELD_PATHS excludes ` +
          "top-level keys only; teach blankDynamicFields to walk a path before excluding one",
      );
    }
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

const PRINT_LITERALS_FLAG = "--print-declared-literals";

function printDeclaredLiterals() {
  // Introspection for tests/test_gates.py, which pins the two facts that make
  // the fabricated `pageErrors` stub safe. It prints exactly the literal source
  // main() extracts and compares, so the test cannot pass against a second,
  // drifted copy of these extraction rules -- and cannot fall back to searching
  // whole files, which would match every script's `pageErrors` collection code
  // rather than what each one actually declares as its output (issue #87).
  const literals = {};
  for (const binding of BINDINGS) {
    const source = readFileSync(path.join(ROOT, "scripts", binding.script), "utf8");
    literals[binding.script] = extractStdoutLiteralSource(source, binding.script);
  }
  process.stdout.write(`${JSON.stringify(literals)}\n`);
}

function main() {
  const argv = process.argv.slice(2);
  if (argv.length === 1 && argv[0] === PRINT_LITERALS_FLAG) {
    printDeclaredLiterals();
    return;
  }
  // Anything else is a typo, and a gate that quietly verifies nothing -- or
  // quietly verifies everything -- because an argument was misspelled is the
  // failure shape this file exists to refuse.
  if (argv.length > 0) {
    process.stderr.write(`unrecognized argument(s): ${argv.join(" ")}\n`);
    process.exitCode = 1;
    return;
  }
  const failures = [];
  let checked = 0;
  for (const binding of BINDINGS) {
    const scriptPath = path.join(ROOT, "scripts", binding.script);
    const source = readFileSync(scriptPath, "utf8");
    let literalValue;
    try {
      const literalSource = extractStdoutLiteralSource(source, binding.script);
      assertPageErrorsStubStillProven(binding.script, source, literalSource);
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
      let expected;
      let actual;
      try {
        expected = canonical(blankDynamicFields(scriptValue, outputName));
        actual = canonical(blankDynamicFields(committedValue, outputName));
      } catch (error) {
        // An unusable exclusion table must be reported the way every other
        // failure here is -- one line, then exit 1 -- rather than thrown out of
        // main() as a stack trace in the middle of a canary run.
        failures.push(error.message);
        continue;
      }
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
  // Floor the count, the way `lint-lab` does with `test "$checked" -gt 0` and
  // check_wheel.py does with `if not referenced`. Without this, an emptied
  // BINDINGS table reports "verified 0 ..." and exits 0, so `make
  // demo-civicrm-target-canary` would pass having compared nothing.
  if (checked === 0) {
    process.stderr.write("no committed browser-*.json was compared: the binding table is empty\n");
    process.exitCode = 1;
    return;
  }
  process.stdout.write(
    `verified ${checked} committed browser-*.json files bind to the literal their capture script declares\n`,
  );
}

main();
