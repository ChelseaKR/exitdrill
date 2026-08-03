import { chromium } from "playwright-core";

const expected = {
  filteredSubject: "Synthetic ExitDrill Case Alpha",
  excludedSubject: "Synthetic ExitDrill Case Bravo",
  caseType: "ExitDrill Civic Case",
};

function fail() {
  throw new Error("closed browser case-search workflow failed");
}

function requireCredential(name) {
  const value = process.env[name];
  if (typeof value !== "string" || value.length < 8 || value.length > 256) fail();
  return value;
}

async function requireVisible(locator) {
  await locator.first().waitFor({ state: "visible", timeout: 15_000 });
}

const username = requireCredential("EXITDRILL_BROWSER_USERNAME");
const password = requireCredential("EXITDRILL_BROWSER_PASSWORD");

let browser;
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
  let unexpectedNetwork = false;
  let failedRequestCount = 0;
  const pageErrors = [];
  await context.route("**/*", async (route) => {
    const url = new URL(route.request().url());
    if (
      (url.protocol === "http:" && url.hostname === "application" && url.port === "") ||
      url.protocol === "data:" ||
      url.protocol === "about:"
    ) {
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
    if (pageErrors.length < 8) pageErrors.push({ name: error.name, message: error.message });
  });
  page.on("requestfailed", () => {
    failedRequestCount += 1;
  });

  currentStep = "case_dashboard_navigation";
  const dashboard = await page.goto("/civicrm/case?reset=1&all=1", {
    timeout: 30_000,
    waitUntil: "load",
  });
  if (!dashboard || dashboard.status() !== 200) fail();
  await requireVisible(page.getByText("Case Summary", { exact: true }));
  currentStep = "case_summary_drilldown";
  const caseTypeRow = page.locator("tr.crm-case-caseStatus").filter({ hasText: expected.caseType });
  await requireVisible(caseTypeRow);
  const drilldown = caseTypeRow
    .locator("a.crm-case-summary-drilldown")
    .filter({ hasText: /^2$/ });
  if ((await drilldown.count()) !== 1) fail();
  await drilldown.click();
  await page.waitForLoadState("load");
  if (new URL(page.url()).pathname !== "/civicrm/case/search") fail();
  currentStep = "unfiltered_results";
  const results = page.locator(".crm-search-results");
  await requireVisible(results);
  await requireVisible(results.getByText(expected.filteredSubject, { exact: true }));
  await requireVisible(results.getByText(expected.excludedSubject, { exact: true }));
  currentStep = "search_criteria";
  const searchAccordion = page.locator(".crm-case_search-accordion");
  currentStep = "search_criteria_accordion";
  if (!(await searchAccordion.evaluate((element) => element.open))) {
    currentStep = "search_criteria_expand";
    const editCriteria = page.getByText("Edit Search Criteria", { exact: true });
    await requireVisible(editCriteria);
    await editCriteria.click();
  }
  currentStep = "search_criteria_subject_locator";
  const subject = page.locator(".crm-case-common-form-block-case_subject input");
  if ((await subject.count()) !== 1) fail();
  currentStep = "search_criteria_subject_visible";
  await requireVisible(subject);
  currentStep = "search_criteria_subject_fill";
  await subject.fill(expected.filteredSubject);
  currentStep = "subject_filter_submit";
  const [searchResponse] = await Promise.all([
    page.waitForNavigation({ timeout: 30_000, waitUntil: "load" }),
    page.getByRole("button", { name: "Search", exact: true }).first().click(),
  ]);
  currentStep = "subject_filter_outcome";
  const filteredResults = page.locator(".crm-search-results");
  const emptyResults = page.locator(".crm-results-block-empty");
  if (
    searchResponse?.status() !== 500 ||
    (await page.title()) !== "Error" ||
    (await filteredResults.count()) !== 0 ||
    (await emptyResults.count()) !== 0 ||
    (await page.locator(".crm-case-search-form-block").count()) !== 0
  ) {
    fail();
  }
  if (
    unexpectedNetwork ||
    failedRequestCount !== 0 ||
    pageErrors.length !== 2 ||
    pageErrors.some(
      (error) =>
        error.name !== "TypeError" || error.message !== "$(...).notify is not a function",
    )
  ) {
    fail();
  }
  process.stdout.write(
    `${JSON.stringify({
      browser_engine: "chromium",
      data_mode: "synthetic_only",
      known_runtime_errors: [
        { error_key: "jquery_notify_unavailable", occurrence_count: pageErrors.length },
      ],
      search_outcome: "exact_subject_filter_http_500_observed",
      retained_artifacts: [],
      schema_version: "exitdrill/civicrm-case-search-workflow-observation/v0.1",
      steps: [
        "case_dashboard_opened",
        "case_summary_drilldown_activated",
        "unfiltered_case_results_observed",
        "case_subject_filter_submitted",
        "exact_subject_filter_http_500_observed",
      ],
      target_profile:
        "directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1",
    })}\n`,
  );
  await context.close();
} catch {
  process.stderr.write(`CiviCRM browser case-search workflow failed closed at ${currentStep}\n`);
  process.exitCode = 1;
} finally {
  await browser?.close().catch(() => undefined);
}
