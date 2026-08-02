import { chromium } from "playwright-core";

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
    if (pageErrors.length < 3) {
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
    })}\n`,
  );
  await context.close();
} catch {
  process.stderr.write(`CiviCRM browser workflow failed closed at ${currentStep}\n`);
  process.exitCode = 1;
} finally {
  await browser?.close().catch(() => undefined);
}
