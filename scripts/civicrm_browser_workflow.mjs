import { chromium } from "playwright-core";
import axe from "axe-core";

const expected = {
  coordinatorName: "Synthetic Person Alpha",
  caseSubject: "Synthetic ExitDrill Case Alpha",
  caseType: "ExitDrill Civic Case",
  caseStatus: "Ongoing",
};

function fail() {
  throw new Error("closed browser workflow did not match the pinned profile");
}

function requireCredential(name) {
  const value = process.env[name];
  if (typeof value !== "string" || value.length < 8 || value.length > 256) fail();
  return value;
}

async function requireVisible(locator) {
  await locator.first().waitFor({ state: "visible", timeout: 15_000 });
}

async function requireExactText(locator, expectedText) {
  await requireVisible(locator);
  const observed = (await locator.first().innerText()).replace(/\s+/g, " ").trim();
  if (observed !== expectedText) fail();
}

async function requireExactTextLink(page, expectedText) {
  const label = page.getByText(expectedText, { exact: true }).first();
  await requireVisible(label);
  if ((await label.evaluate((element) => element.tagName)) === "A") return label;
  const parent = label.locator("..");
  if ((await parent.evaluate((element) => element.tagName)) !== "A") fail();
  return parent;
}

const username = requireCredential("EXITDRILL_BROWSER_USERNAME");
const password = requireCredential("EXITDRILL_BROWSER_PASSWORD");

let browser;
let unexpectedNetwork = false;
let pageErrorCount = 0;
const pageErrors = [];
let failedRequestCount = 0;
let currentStep = "browser_launch";
try {
  browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({
    acceptDownloads: false,
    baseURL: "http://application",
    extraHTTPHeaders: {
      Authorization: `Basic ${Buffer.from(`${username}:${password}`, "utf8").toString("base64")}`,
    },
    serviceWorkers: "block",
    viewport: { width: 1440, height: 1000 },
  });
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (url.protocol === "http:" && url.hostname === "application" && url.port === "") {
      await route.continue();
    } else if (url.protocol === "data:" || url.protocol === "about:") {
      await route.continue();
    } else {
      unexpectedNetwork = true;
      await route.abort("blockedbyclient");
    }
  });

  const page = await context.newPage();
  page.on("dialog", (dialog) => dialog.dismiss());
  page.on("download", (download) => download.cancel());
  page.on("pageerror", (error) => {
    pageErrorCount += 1;
    if (pageErrors.length < 8) {
      pageErrors.push({ step: currentStep, name: error.name, message: error.message });
    }
  });
  page.on("requestfailed", () => {
    failedRequestCount += 1;
  });

  currentStep = "case_dashboard_navigation";
  const response = await page.goto("/civicrm/case?reset=1&all=1", {
    timeout: 30_000,
    waitUntil: "load",
  });
  if (!response) {
    currentStep = "case_dashboard_no_response";
    fail();
  }
  if (response.status() !== 200) {
    currentStep = `case_dashboard_status_${response.status()}`;
    fail();
  }
  currentStep = "case_dashboard_marker";
  await requireVisible(page.getByText("Case Summary", { exact: true }));
  currentStep = "case_locator";
  const manageCase = page.locator('a.manage-case, a[title="Manage Case"]');
  await requireVisible(manageCase);
  currentStep = "case_view";
  await manageCase.first().click();
  await requireVisible(page.locator(".crm-case-caseview-form-block"));
  currentStep = "case_subject";
  await requireVisible(
    page.locator(".crm-case-caseview-case_subject").getByText(expected.caseSubject, { exact: true }),
  );
  currentStep = "case_type";
  await requireExactText(
    page.locator(".crm-case-caseview-case_type"),
    `Type: ${expected.caseType}`,
  );
  currentStep = "case_status";
  await requireExactText(
    page.locator(".crm-case-caseview-case_status"),
    `Status: ${expected.caseStatus}`,
  );
  currentStep = "case_roles";
  const roles = page.locator(".crm-case-roles-block");
  await requireVisible(roles);
  if (!(await roles.evaluate((element) => element.open))) {
    await roles.locator("summary").click();
  }
  currentStep = "case_coordinator";
  await requireVisible(roles.getByText(expected.coordinatorName, { exact: true }));
  currentStep = "case_activities";
  await requireVisible(page.locator(".crm-case-activities-block"));
  currentStep = "accessibility_scan";
  await page.addScriptTag({ content: axe.source });
  const rawAccessibility = await page.evaluate(async () =>
    globalThis.axe.run(document, {
      runOnly: {
        type: "tag",
        values: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
      },
    }),
  );
  const violationImpacts = new Set(["minor", "moderate", "serious", "critical"]);
  const violations = rawAccessibility.violations
    .map((violation) => {
      if (
        !/^[a-z][a-z0-9-]{0,79}$/.test(violation.id) ||
        !violationImpacts.has(violation.impact) ||
        !Number.isSafeInteger(violation.nodes.length) ||
        violation.nodes.length < 1
      ) {
        fail();
      }
      return {
        impact: violation.impact,
        node_count: violation.nodes.length,
        rule_id: violation.id,
      };
    })
    .sort((left, right) => left.rule_id.localeCompare(right.rule_id));
  currentStep = "keyboard_roles_summary_navigation";
  const rolesSummary = roles.locator("summary");
  await page.evaluate(() => document.activeElement?.blur());
  let tabStepsToRolesSummary = null;
  for (let tabStep = 1; tabStep <= 80; tabStep += 1) {
    await page.keyboard.press("Tab");
    if (await rolesSummary.evaluate((element) => element === document.activeElement)) {
      tabStepsToRolesSummary = tabStep;
      break;
    }
  }
  if (tabStepsToRolesSummary === null) fail();
  currentStep = "keyboard_roles_summary_enter";
  await page.keyboard.press("Enter");
  if (await roles.evaluate((element) => element.open)) fail();
  currentStep = "keyboard_roles_summary_space";
  await page.keyboard.press("Space");
  if (!(await roles.evaluate((element) => element.open))) fail();
  currentStep = "activity_view_navigation";
  const viewActivity = page.locator(".crm-case-activities-block a.action-item.view");
  await requireVisible(viewActivity);
  await viewActivity.first().click();
  await page.waitForLoadState("load");
  if (new URL(page.url()).pathname !== "/civicrm/case/activity/view") fail();
  await requireVisible(page.getByText("Activity View", { exact: true }));
  await requireVisible(page.getByText("Open Case", { exact: true }));
  await requireVisible(page.getByText(expected.caseSubject, { exact: true }));
  await requireVisible(page.getByText("Completed", { exact: true }));
  currentStep = "contact_dashboard_navigation";
  const contactDashboardResponse = await page.goto("/civicrm/case?reset=1&all=1", {
    timeout: 30_000,
    waitUntil: "load",
  });
  if (!contactDashboardResponse || contactDashboardResponse.status() !== 200) fail();
  currentStep = "contact_dashboard_marker";
  await requireVisible(page.getByText("Case Summary", { exact: true }));
  currentStep = "contact_locator";
  const contactLink = page.getByRole("link", {
    name: expected.coordinatorName,
    exact: true,
  });
  await requireVisible(contactLink);
  currentStep = "contact_summary_navigation";
  await contactLink.first().click();
  await page.waitForLoadState("load");
  if (new URL(page.url()).pathname !== "/civicrm/contact/view") fail();
  currentStep = "contact_summary_marker";
  await requireVisible(page.locator(".crm-contact-page"));
  currentStep = "contact_name";
  await requireVisible(page.getByText(expected.coordinatorName, { exact: true }));
  currentStep = "contact_cases_affordance";
  await requireVisible(page.getByText("Cases", { exact: true }));
  currentStep = "case_client_dashboard_navigation";
  const caseClientDashboardResponse = await page.goto("/civicrm/case?reset=1&all=1", {
    timeout: 30_000,
    waitUntil: "load",
  });
  if (!caseClientDashboardResponse || caseClientDashboardResponse.status() !== 200) fail();
  currentStep = "case_client_dashboard_marker";
  await requireVisible(page.getByText("Case Summary", { exact: true }));
  currentStep = "case_client_locator";
  const caseClientLink = await requireExactTextLink(page, "ExitDrill target helper");
  currentStep = "case_client_summary_navigation";
  await caseClientLink.click();
  await page.waitForLoadState("load");
  if (new URL(page.url()).pathname !== "/civicrm/contact/view") fail();
  await requireVisible(page.locator(".crm-contact-page"));
  await requireVisible(page.getByText("ExitDrill target helper", { exact: true }));
  currentStep = "case_client_cases_affordance";
  const casesControl = await requireExactTextLink(page, "Cases");
  currentStep = "case_client_cases_click";
  await casesControl.click();
  currentStep = "case_client_cases_load";
  await page.waitForLoadState("load");
  currentStep = "case_client_cases_subject";
  const contactCaseSubject = page.getByText(expected.caseSubject, { exact: true });
  await requireVisible(contactCaseSubject);
  currentStep = "case_client_case_locator";
  const contactManageCase = await requireExactTextLink(page, "Manage");
  currentStep = "case_client_case_navigation";
  await contactManageCase.click();
  await page.waitForLoadState("load");
  await requireVisible(page.locator(".crm-case-caseview-form-block"));
  currentStep = "case_client_case_subject_reobserved";
  await requireVisible(
    page.locator(".crm-case-caseview-case_subject").getByText(expected.caseSubject, { exact: true }),
  );
  currentStep = "runtime_integrity";
  const expectedPageErrors = [
    {
      step: "case_dashboard_navigation",
      name: "TypeError",
      message: "$(...).notify is not a function",
    },
    {
      step: "case_view",
      name: "TypeError",
      message: "$(...).notify is not a function",
    },
    {
      step: "activity_view_navigation",
      name: "TypeError",
      message: "$(...).notify is not a function",
    },
    {
      step: "contact_dashboard_navigation",
      name: "TypeError",
      message: "$(...).notify is not a function",
    },
    {
      step: "contact_summary_navigation",
      name: "TypeError",
      message: "$(...).notify is not a function",
    },
    {
      step: "case_client_dashboard_navigation",
      name: "TypeError",
      message: "$(...).notify is not a function",
    },
    {
      step: "case_client_summary_navigation",
      name: "TypeError",
      message: "$(...).notify is not a function",
    },
    {
      step: "case_client_case_navigation",
      name: "TypeError",
      message: "$(...).notify is not a function",
    },
  ];
  if (
    unexpectedNetwork ||
    failedRequestCount !== 0 ||
    pageErrorCount !== expectedPageErrors.length ||
    JSON.stringify(pageErrors) !== JSON.stringify(expectedPageErrors)
  ) {
    fail();
  }

  process.stdout.write(
    `${JSON.stringify({
      activity_view: {
        browser_engine: "chromium",
        data_mode: "synthetic_only",
        known_runtime_errors: [
          {
            error_key: "jquery_notify_unavailable",
            occurrence_count: 1,
          },
        ],
        retained_artifacts: [],
        schema_version: "exitdrill/civicrm-activity-view-observation/v0.1",
        steps: [
          "activity_view_opened",
          "activity_subject_observed",
          "activity_type_observed",
          "activity_status_observed",
        ],
        target_profile:
          "directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1",
      },
      case_client_workflow: {
        browser_engine: "chromium",
        data_mode: "synthetic_only",
        known_runtime_errors: [
          {
            error_key: "jquery_notify_unavailable",
            occurrence_count: 3,
          },
        ],
        retained_artifacts: [],
        schema_version: "exitdrill/civicrm-case-client-workflow-observation/v0.1",
        steps: [
          "case_dashboard_reopened",
          "target_generated_case_client_opened",
          "contact_summary_observed",
          "cases_affordance_activated",
          "contact_cases_observed",
          "manage_case_opened_from_contact",
          "case_subject_reobserved",
        ],
        target_profile:
          "directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1",
      },
      contact_summary_workflow: {
        browser_engine: "chromium",
        data_mode: "synthetic_only",
        known_runtime_errors: [
          {
            error_key: "jquery_notify_unavailable",
            occurrence_count: 2,
          },
        ],
        retained_artifacts: [],
        schema_version: "exitdrill/civicrm-contact-summary-workflow-observation/v0.1",
        steps: [
          "case_dashboard_reopened",
          "case_contact_opened",
          "contact_summary_observed",
          "cases_affordance_observed",
        ],
        target_profile:
          "directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1",
      },
      accessibility: {
        data_mode: "synthetic_only",
        engine: "axe-core",
        engine_version: axe.version,
        incomplete_rule_count: rawAccessibility.incomplete.length,
        inapplicable_rule_count: rawAccessibility.inapplicable.length,
        page_scope: "manage_case_document",
        passes_rule_count: rawAccessibility.passes.length,
        retained_artifacts: [],
        rule_tags: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
        schema_version: "exitdrill/civicrm-accessibility-observation/v0.1",
        target_profile:
          "directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1",
        violations,
      },
      keyboard: {
        browser_engine: "chromium",
        data_mode: "synthetic_only",
        retained_artifacts: [],
        schema_version: "exitdrill/civicrm-keyboard-observation/v0.1",
        steps: [
          "roles_summary_reached_by_tab",
          "roles_summary_closed_by_enter",
          "roles_summary_reopened_by_space",
        ],
        tab_steps_to_roles_summary: tabStepsToRolesSummary,
        target_profile:
          "directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1",
      },
      workflow: {
        browser_engine: "chromium",
        data_mode: "synthetic_only",
        known_runtime_errors: [
          {
            error_key: "jquery_notify_unavailable",
            occurrence_count: 2,
          },
        ],
        retained_artifacts: [],
        schema_version: "exitdrill/civicrm-browser-workflow-observation/v0.1",
        steps: [
          "case_dashboard_opened",
          "case_located",
          "manage_case_opened",
          "case_controls_observed",
        ],
        target_profile:
          "directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1",
      },
    })}\n`,
  );
  await context.close();
} catch {
  process.stderr.write(`CiviCRM browser workflow failed closed at ${currentStep}\n`);
  process.exitCode = 1;
} finally {
  await browser?.close().catch(() => undefined);
}
