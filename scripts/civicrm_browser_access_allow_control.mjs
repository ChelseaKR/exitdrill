import { chromium } from "playwright-core";

function fail() {
  throw new Error("closed browser access allow-control probe failed");
}

function requireCredential(name) {
  const value = process.env[name];
  if (typeof value !== "string" || value.length < 8 || value.length > 256) fail();
  return value;
}

function requireContactId() {
  const value = process.env.EXITDRILL_PROTECTED_CONTACT_ID;
  if (!/^[1-9][0-9]{0,9}$/.test(value ?? "")) fail();
  return value;
}

const username = requireCredential("EXITDRILL_BROWSER_USERNAME");
const password = requireCredential("EXITDRILL_BROWSER_PASSWORD");
const contactId = requireContactId();

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
  let pageErrorCount = 0;
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
    pageErrorCount += 1;
    if (pageErrors.length < 3) pageErrors.push({ name: error.name, message: error.message });
  });
  page.on("requestfailed", () => {
    failedRequestCount += 1;
  });

  currentStep = "protected_contact_navigation";
  const response = await page.goto(`/civicrm/contact/view?reset=1&cid=${contactId}`, {
    timeout: 30_000,
    waitUntil: "load",
  });
  if (!response) fail();
  const navigationChain = [];
  let request = response.request();
  while (request) {
    const navigationResponse = await request.response();
    navigationChain.unshift({
      pathname: new URL(request.url()).pathname,
      status: navigationResponse?.status() ?? 0,
    });
    request = request.redirectedFrom();
  }
  const bodyText = (await page.locator("body").innerText()).replace(/\s+/g, " ").trim();
  if (
    unexpectedNetwork ||
    failedRequestCount !== 0 ||
    pageErrorCount !== 1 ||
    JSON.stringify(pageErrors) !==
      JSON.stringify([{ name: "TypeError", message: "$(...).notify is not a function" }]) ||
    JSON.stringify(navigationChain) !==
      JSON.stringify([{ pathname: "/civicrm/contact/view", status: 200 }]) ||
    response.status() !== 200 ||
    new URL(page.url()).pathname !== "/civicrm/contact/view" ||
    (await page.locator(".crm-contact-page").count()) !== 1 ||
    !bodyText.includes("Synthetic Person Alpha")
  ) {
    fail();
  }
  process.stdout.write(
    `${JSON.stringify({
      allow_signal: "protected_contact_content_present",
      authenticated_identity: "allow",
      browser_engine: "chromium",
      data_mode: "synthetic_only",
      known_runtime_errors: [
        { error_key: "jquery_notify_unavailable", occurrence_count: 1 },
      ],
      navigation_chain: [{ route: "civicrm/contact/view", status: 200 }],
      retained_artifacts: [],
      schema_version: "exitdrill/civicrm-browser-access-allow-control-observation/v0.1",
      steps: [
        "protected_contact_requested",
        "protected_contact_page_observed",
        "protected_contact_content_observed",
      ],
      target_profile:
        "directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1",
    })}\n`,
  );
  await context.close();
} catch {
  process.stderr.write(`CiviCRM browser access allow-control probe failed closed at ${currentStep}\n`);
  process.exitCode = 1;
} finally {
  await browser?.close().catch(() => undefined);
}
