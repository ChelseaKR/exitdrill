import assert from "node:assert/strict";
import { spawn } from "node:child_process";
import { createHash, randomBytes } from "node:crypto";
import {
  chmod,
  lstat,
  mkdir,
  mkdtemp,
  readFile,
  realpath,
  rename,
  rm,
  writeFile,
} from "node:fs/promises";
import { tmpdir } from "node:os";
import { basename, dirname, join, resolve, sep } from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = dirname(fileURLToPath(import.meta.url));
const repositoryRoot = resolve(scriptDir, "..");
const composeFile = join(repositoryRoot, "lab", "civicrm-6.16.2-standalone", "compose.yaml");
const browserWorkflowScript = join(repositoryRoot, "scripts", "civicrm_browser_workflow.mjs");
const browserNodeModules = join(repositoryRoot, "node_modules");
const sourceNativeDir = join(
  repositoryRoot,
  "examples",
  "directus-11.17.4-civic-case",
  "native",
);
const sourceManifest = join(sourceNativeDir, "capture-manifest.json");

const applicationImage =
  "civicrm/civicrm:6.16.2-php8.5@sha256:cdf062708b054670cc0f9b452e0b883840af71ce6db21615304f9e7ffe44b93f";
const databaseImage =
  "mariadb:10.11.18@sha256:be981e4113326ada8d6004174dd09eeaefc03094037f811182a52d4f2e737350";
const browserImage =
  "mcr.microsoft.com/playwright:v1.62.0-noble@sha256:baed2032d533817f3dbe6425de795788430ba345e819a1201337009ba17c9d07";
const targetProfile =
  "directus-11.17.4-civic-case-to-civicrm-standalone-6.16.2/v0.1";
const sourceProfile = "directus-11.17.4-civic-case/v0.1";
const firstAssetId = "11111111-1111-4111-8111-111111111111";
const secondAssetId = "22222222-2222-4222-8222-222222222222";
const sourceAssetIds = [firstAssetId, secondAssetId];
const sourcePersonIds = ["1", "2", "3"];
const relationshipDescription = "ExitDrill assigned_to";
const caseTypeName = "exitdrill_civic_case";
const personGroupName = "exitdrill_person_profile";
const caseGroupName = "exitdrill_case_profile";
const httpMarkerSize = 4;
const maxCommandBytes = 32 * 1024 * 1024;
const identityKinds = new Set(["writer", "reader", "allow", "deny"]);
const expectedSourceNormalization = {
  adapter_profile: "directus-11.17.4-civic-case/v0.1",
  attachment_bundle_sha256: "b1e24857570523f2d1606bb3ef0d32708680b369b631c623df83db95f16c177d",
  counts: {
    attachment_bytes: 56,
    attachments: 2,
    audit_events: 2,
    entities: 7,
    permissions: 2,
    relationships: 2,
  },
  drill_id: "directus-civic-case-exit-001",
  export_sha256: "2e2a4280c7e9b2249b443a861e3eb8498a379bd462b2b4ad5637208d9698a51b",
  limitations: [
    "synthetic_fixture_only",
    "source_bundle_is_unsigned_and_unauthenticated",
    "normalization_does_not_prove_source_export_completeness",
    "normalization_does_not_prove_operational_equivalence",
  ],
  schema_version: "exitdrill/directus-normalization/v0.1",
  source_bundle_sha256: "a67048bf25c07b73aa0bff26372090c0a7e5ce77871b49259d0a96110998be49",
  source_system: "Directus 11.17.4 synthetic civic-case sandbox",
};

const capturePaths = [
  "contacts.json",
  "cases.json",
  "relationships.json",
  "files.json",
  "entity-files.json",
  "identity-writer.json",
  "identity-reader.json",
  "identity-allow.json",
  "identity-deny.json",
  "permission-allow.json",
  "permission-deny.json",
  "ui-contact-summary.json",
  "browser-workflow.json",
  "browser-accessibility.json",
  `assets/${firstAssetId}.txt`,
  `assets/${secondAssetId}.txt`,
];

let activeChild = null;
let interruption = null;
const secretValues = [];

function canonical(value) {
  if (Array.isArray(value)) return `[${value.map(canonical).join(",")}]`;
  if (value !== null && typeof value === "object") {
    return `{${Object.keys(value)
      .sort()
      .map((key) => `${JSON.stringify(key)}:${canonical(value[key])}`)
      .join(",")}}`;
  }
  return JSON.stringify(value);
}

function sha256(bytes) {
  return createHash("sha256").update(bytes).digest("hex");
}

function jsonDocument(value) {
  return Buffer.from(`${canonical(value)}\n`, "utf8");
}

function capturedApiEnvelope(result) {
  // Persist the closed, supported projection of the real REST response. These
  // bytes are evidence from API4, but are not a byte-raw HTTP response body.
  const envelope = {
    count: result.count,
    countFetched: result.countFetched,
    values: result.values,
  };
  if (result.countMatched !== undefined) envelope.countMatched = result.countMatched;
  return jsonDocument(envelope);
}

function secret(size = 32) {
  const value = randomBytes(size).toString("base64url");
  secretValues.push(value);
  return value;
}

function redact(value) {
  let text = String(value);
  for (const secretValue of secretValues) {
    if (secretValue) text = text.split(secretValue).join("[REDACTED]");
  }
  return text;
}

function fail(message) {
  throw new Error(message);
}

function requireObject(value, label) {
  if (value === null || typeof value !== "object" || Array.isArray(value)) {
    fail(`${label} must be a JSON object`);
  }
  return value;
}

function requireArray(value, label) {
  if (!Array.isArray(value)) fail(`${label} must be a JSON array`);
  return value;
}

function requireInteger(value, label) {
  if (!Number.isSafeInteger(value) || value < 1) fail(`${label} must be a positive integer`);
  return value;
}

function requireString(value, label) {
  if (typeof value !== "string" || !value || value.trim() !== value) {
    fail(`${label} must be a non-empty trimmed string`);
  }
  return value;
}

function requireExact(value, expected, label) {
  if (canonical(value) !== canonical(expected)) fail(`${label} did not match the pinned profile`);
}

function pathIsWithin(candidate, root) {
  return candidate === root || candidate.startsWith(`${root}${sep}`);
}

function parseArguments(argv) {
  let outputPath = null;
  let help = false;
  for (let index = 0; index < argv.length; index += 1) {
    const argument = argv[index];
    if (argument === "--help" || argument === "-h") {
      help = true;
    } else if (argument === "--output") {
      index += 1;
      if (index >= argv.length || !argv[index]) fail("--output requires a directory path");
      outputPath = argv[index];
    } else if (argument.startsWith("--output=")) {
      outputPath = argument.slice("--output=".length);
      if (!outputPath) fail("--output requires a directory path");
    } else {
      fail(`unknown argument: ${argument}`);
    }
  }
  return { help, outputPath };
}

async function pathExists(path) {
  try {
    await lstat(path);
    return true;
  } catch (error) {
    if (error?.code === "ENOENT") return false;
    throw error;
  }
}

function installSignalHandlers() {
  for (const signal of ["SIGINT", "SIGTERM", "SIGHUP"]) {
    process.once(signal, () => {
      interruption ??= new Error(`interrupted by ${signal}`);
      activeChild?.kill("SIGTERM");
    });
  }
}

async function runCommand(
  command,
  args,
  {
    env = {},
    input = null,
    timeoutMs = 120_000,
    label = basename(command),
    allowAfterInterruption = false,
  } = {},
) {
  if (interruption && !allowAfterInterruption) throw interruption;
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn(command, args, {
      env: { ...process.env, ...env },
      stdio: ["pipe", "pipe", "pipe"],
      shell: false,
    });
    activeChild = child;
    const stdout = [];
    const stderr = [];
    let stdoutBytes = 0;
    let stderrBytes = 0;
    let overflow = false;
    let timedOut = false;
    const timer = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
    }, timeoutMs);

    child.stdout.on("data", (chunk) => {
      stdoutBytes += chunk.length;
      if (stdoutBytes > maxCommandBytes) {
        overflow = true;
        child.kill("SIGTERM");
      } else {
        stdout.push(chunk);
      }
    });
    child.stderr.on("data", (chunk) => {
      stderrBytes += chunk.length;
      if (stderrBytes > maxCommandBytes) {
        overflow = true;
        child.kill("SIGTERM");
      } else {
        stderr.push(chunk);
      }
    });
    child.once("error", (error) => {
      clearTimeout(timer);
      if (activeChild === child) activeChild = null;
      rejectPromise(new Error(`${label} could not start: ${redact(error.message)}`));
    });
    child.once("close", (code, signal) => {
      clearTimeout(timer);
      if (activeChild === child) activeChild = null;
      const stdoutBuffer = Buffer.concat(stdout);
      const stderrText = redact(Buffer.concat(stderr).toString("utf8")).trim();
      if (interruption && !allowAfterInterruption) {
        rejectPromise(interruption);
      } else if (timedOut) {
        rejectPromise(new Error(`${label} timed out`));
      } else if (overflow) {
        rejectPromise(new Error(`${label} exceeded the bounded output limit`));
      } else if (code !== 0) {
        const detail = stderrText ? `: ${stderrText.slice(-4000)}` : "";
        rejectPromise(
          new Error(`${label} failed with ${signal ? `signal ${signal}` : `exit ${code}`}${detail}`),
        );
      } else {
        resolvePromise({ stdout: stdoutBuffer, stderr: stderrText });
      }
    });

    if (input === null) child.stdin.end();
    else child.stdin.end(input);
  });
}

function parseJsonBytes(bytes, label) {
  try {
    return JSON.parse(bytes.toString("utf8"));
  } catch {
    fail(`${label} was not valid JSON`);
  }
}

function boundedHttpErrorMessage(bytes) {
  let payload;
  try {
    payload = JSON.parse(bytes.toString("utf8"));
  } catch {
    return "";
  }
  if (payload === null || typeof payload !== "object" || Array.isArray(payload)) return "";
  for (const field of ["error_message", "message"]) {
    if (typeof payload[field] !== "string") continue;
    const firstLine = redact(payload[field]).split(/\r?\n/, 1)[0].replace(/[\x00-\x1f\x7f]/g, " ").trim();
    if (firstLine) return firstLine.slice(0, 500);
  }
  return "";
}

async function readJson(path, label) {
  return parseJsonBytes(await readFile(path), label);
}

async function normalizeSourceFixture(normalizedDir) {
  if (await pathExists(normalizedDir)) fail("source normalization output must be fresh");
  const completed = await runCommand(
    "uv",
    [
      "run",
      "--project",
      repositoryRoot,
      "--frozen",
      "exitdrill",
      "normalize-directus-canary",
      sourceManifest,
      "--out-dir",
      normalizedDir,
    ],
    { timeoutMs: 120_000, label: "fixed Directus source normalization" },
  );
  const normalization = requireObject(
    parseJsonBytes(completed.stdout, "Directus normalization stdout"),
    "Directus normalization stdout",
  );
  requireExact(normalization, expectedSourceNormalization, "Directus normalization aggregate");
  const persistedNormalization = requireObject(
    await readJson(
      join(normalizedDir, "normalization-manifest.json"),
      "Directus normalization manifest",
    ),
    "Directus normalization manifest",
  );
  requireExact(
    persistedNormalization,
    expectedSourceNormalization,
    "persisted Directus normalization aggregate",
  );

  const exportBytes = await readFile(join(normalizedDir, "export.json"));
  if (sha256(exportBytes) !== expectedSourceNormalization.export_sha256) {
    fail("normalized Directus export hash did not match the pinned source profile");
  }
  const sourceExport = requireObject(
    parseJsonBytes(exportBytes, "normalized Directus export"),
    "normalized Directus export",
  );
  requireExact(
    Object.keys(sourceExport).sort(),
    [
      "attachments",
      "audit_events",
      "drill_id",
      "entities",
      "exported_at",
      "permissions",
      "relationships",
      "schema_version",
      "source_system",
    ].sort(),
    "normalized Directus export fields",
  );
  requireExact(
    {
      drill_id: sourceExport.drill_id,
      exported_at: sourceExport.exported_at,
      schema_version: sourceExport.schema_version,
      source_system: sourceExport.source_system,
    },
    {
      drill_id: "directus-civic-case-exit-001",
      exported_at: "2026-08-02T02:38:28.542Z",
      schema_version: "exitdrill/export/v0.1",
      source_system: "Directus 11.17.4 synthetic civic-case sandbox",
    },
    "normalized Directus export identity",
  );

  const people = [];
  const cases = [];
  const technicalEntities = [];
  for (const [index, raw] of requireArray(sourceExport.entities, "normalized source entities").entries()) {
    const entity = requireObject(raw, `normalized source entities[${index}]`);
    if (entity.type === "person") {
      const fields = requireObject(entity.fields, `normalized source person ${index} fields`);
      requireExact(
        Object.keys(fields).sort(),
        ["active", "display_name"],
        `normalized source person ${index} field names`,
      );
      if (typeof fields.active !== "boolean") fail("normalized source person active must be boolean");
      people.push({
        active: fields.active,
        display_name: requireString(fields.display_name, "normalized source person display name"),
        id: requireInteger(Number(entity.id), "normalized source person id"),
      });
    } else if (entity.type === "case") {
      const fields = requireObject(entity.fields, `normalized source case ${index} fields`);
      requireExact(
        Object.keys(fields).sort(),
        ["document", "priority", "status"],
        `normalized source case ${index} field names`,
      );
      cases.push({
        document: requireString(fields.document, "normalized source case document"),
        id: requireInteger(Number(entity.id), "normalized source case id"),
        priority: requireInteger(fields.priority, "normalized source case priority"),
        status: requireString(fields.status, "normalized source case status"),
      });
    } else {
      technicalEntities.push(entity);
    }
  }
  people.sort((left, right) => left.id - right.id);
  cases.sort((left, right) => left.id - right.id);
  requireExact(
    people,
    [
      { active: true, display_name: "Synthetic Person Alpha", id: 1 },
      { active: true, display_name: "Synthetic Person Bravo", id: 2 },
      { active: false, display_name: "Synthetic Person Canary", id: 3 },
    ],
    "normalized Directus people",
  );
  requireExact(
    cases,
    [
      { document: firstAssetId, id: 1, priority: 2, status: "open" },
      { document: secondAssetId, id: 2, priority: 3, status: "open" },
    ],
    "normalized Directus cases",
  );
  requireExact(
    technicalEntities,
    [
      {
        fields: { collection: "exitdrill_cases" },
        id: "exitdrill_cases",
        type: "directus_collection_scope",
      },
      {
        fields: { collection: "exitdrill_people" },
        id: "exitdrill_people",
        type: "directus_collection_scope",
      },
    ],
    "normalized Directus technical entities",
  );

  const links = requireArray(sourceExport.relationships, "normalized source relationships").map(
    (raw, index) => {
      const relationship = requireObject(raw, `normalized source relationships[${index}]`);
      requireExact(
        Object.keys(relationship).sort(),
        ["from_id", "from_type", "to_id", "to_type", "type"],
        `normalized source relationship ${index} fields`,
      );
      if (
        relationship.from_type !== "case" ||
        relationship.to_type !== "person" ||
        relationship.type !== "assigned_to"
      ) {
        fail("normalized source relationship semantics did not match the pinned profile");
      }
      return {
        case_id: requireInteger(Number(relationship.from_id), "normalized relationship case id"),
        person_id: requireInteger(Number(relationship.to_id), "normalized relationship person id"),
        relation_type: "assigned_to",
      };
    },
  );
  links.sort((left, right) => left.case_id - right.case_id);
  requireExact(
    links,
    [
      { case_id: 1, person_id: 1, relation_type: "assigned_to" },
      { case_id: 2, person_id: 2, relation_type: "assigned_to" },
    ],
    "normalized Directus relationships",
  );

  const attachments = requireArray(sourceExport.attachments, "normalized source attachments");
  const assets = new Map();
  const files = [];
  for (const [index, raw] of attachments.entries()) {
    const attachment = requireObject(raw, `normalized source attachments[${index}]`);
    const sourceId = requireString(attachment.id, "normalized source attachment id");
    const expectedId = sourceAssetIds[index];
    requireExact(
      attachment,
      {
        content_sha256:
          expectedId === firstAssetId
            ? "71bcf1dbe17580338192d03a52e2ba5027ac08108a3c24441b1970df8a43cc31"
            : "b4a1c0ab3025360613416808fb3a56e0dea622431b07e0aa6a2cd7eeaae8f9a4",
        id: expectedId,
        owner_id: String(index + 1),
        owner_type: "case",
        relative_path: `attachments/${expectedId}.txt`,
      },
      `normalized source attachment ${index}`,
    );
    const bytes = await readFile(
      join(normalizedDir, "export-files", "attachments", `${sourceId}.txt`),
    );
    if (bytes.length !== 28 || sha256(bytes) !== attachment.content_sha256) {
      fail(`normalized source attachment ${index} bytes did not match its declared evidence`);
    }
    assets.set(sourceId, bytes);
    files.push({ filesize: bytes.length, id: sourceId, type: "text/plain" });
  }
  requireExact(
    {
      audit_events: requireArray(sourceExport.audit_events, "normalized source audit events").length,
      permissions: requireArray(sourceExport.permissions, "normalized source permissions").length,
    },
    { audit_events: 2, permissions: 2 },
    "normalized Directus omitted-dimension denominators",
  );

  return {
    assets,
    cases,
    files,
    links,
    people,
    sourceNormalization: {
      adapter_profile: normalization.adapter_profile,
      attachment_bundle_sha256: normalization.attachment_bundle_sha256,
      export_sha256: normalization.export_sha256,
      schema_version: normalization.schema_version,
      source_bundle_sha256: normalization.source_bundle_sha256,
    },
  };
}

const trustedPhp = String.raw`
$op = getenv('LAB_TRUSTED_OP');
$payloadText = getenv('LAB_TRUSTED_PAYLOAD');
$payload = $payloadText ? json_decode($payloadText, true, 512, JSON_THROW_ON_ERROR) : [];
if ($op === 'api4') {
  $entity = $payload['entity'] ?? '';
  $action = $payload['action'] ?? '';
  if (!preg_match('/^[A-Za-z][A-Za-z0-9_]*$/', $entity) || !preg_match('/^[A-Za-z][A-Za-z0-9_]*$/', $action)) {
    throw new RuntimeException('Invalid trusted API name');
  }
  $params = $payload['params'] ?? [];
  $params['checkPermissions'] = false;
  $result = civicrm_api4($entity, $action, $params);
  $exitdrillResult = ['values' => array_values((array) $result), 'count' => $result->count()];
}
elseif ($op === 'configure_safety') {
  Civi::settings()->set('mailing_backend', ['outBound_option' => (string) CRM_Mailing_Config::OUTBOUND_OPTION_DISABLED]);
  Civi::settings()->set('authx_guards', ['perm']);
  Civi::settings()->set('authx_header_cred', ['pass']);
  Civi::settings()->set('authx_header_user', 'require');
  $exitdrillResult = ['configured' => true];
}
elseif ($op === 'inspect_safety') {
  $mail = Civi::settings()->get('mailing_backend');
  $activeJobs = civicrm_api4('Job', 'get', [
    'checkPermissions' => false,
    'select' => ['id'],
    'where' => [['is_active', '=', true]],
    'limit' => 0,
  ]);
  $exitdrillResult = [
    'version' => CRM_Utils_System::version(),
    'hibp_disabled' => defined('CIVICRM_HIBP_URL') && CIVICRM_HIBP_URL === '',
    'mail_disabled' => isset($mail['outBound_option']) && (string) $mail['outBound_option'] === (string) CRM_Mailing_Config::OUTBOUND_OPTION_DISABLED,
    'authx_guards' => Civi::settings()->get('authx_guards'),
    'authx_header_cred' => Civi::settings()->get('authx_header_cred'),
    'authx_header_user' => Civi::settings()->get('authx_header_user'),
    'active_jobs' => $activeJobs->count(),
  ];
}
elseif ($op === 'rebuild') {
  Civi::rebuild(['system' => true])->execute();
  $exitdrillResult = ['rebuilt' => true];
}
else {
  throw new RuntimeException('Unknown trusted operation');
}
echo "EXITDRILL_JSON:", json_encode($exitdrillResult, JSON_UNESCAPED_SLASHES | JSON_UNESCAPED_UNICODE);
`;

const hibpPatchPhp = String.raw`
$path = '/var/www/html/private/civicrm.settings.php';
if (!is_file($path) || is_link($path)) {
  fwrite(STDERR, "generated settings file is not a regular file\n");
  exit(70);
}
$contents = file_get_contents($path);
if ($contents === false || strpos($contents, 'CIVICRM_HIBP_URL') !== false) {
  fwrite(STDERR, "generated settings file is missing or already mentions the HIBP constant\n");
  exit(71);
}
$line = "\n// ExitDrill offline lab: prohibit browser-side HIBP requests.\ndefine('CIVICRM_HIBP_URL', '');\n";
$written = file_put_contents($path, $line, FILE_APPEND | LOCK_EX);
if ($written !== strlen($line)) {
  fwrite(STDERR, "could not install the HIBP safety control\n");
  exit(72);
}
`;

const httpPhp = String.raw`
$mode = getenv('LAB_HTTP_MODE');
$username = getenv('LAB_HTTP_USER');
$password = getenv('LAB_HTTP_PASSWORD');
if (!$mode || !$username || $password === false || $password === '') {
  fwrite(STDERR, "missing bounded HTTP request input\n");
  exit(70);
}
$method = 'GET';
$url = '';
$content = null;
if ($mode === 'identity') {
  $url = 'http://application/civicrm/authx/id';
}
elseif ($mode === 'api4') {
  $entity = getenv('LAB_HTTP_ENTITY');
  $action = getenv('LAB_HTTP_ACTION');
  $params = getenv('LAB_HTTP_PARAMS');
  if (!preg_match('/^[A-Za-z][A-Za-z0-9_]*$/', $entity) || !preg_match('/^[A-Za-z][A-Za-z0-9_]*$/', $action)) {
    fwrite(STDERR, "invalid API request input\n");
    exit(71);
  }
  json_decode($params, true, 512, JSON_THROW_ON_ERROR);
  $url = 'http://application/civicrm/ajax/api4/' . rawurlencode($entity) . '/' . rawurlencode($action);
  $method = 'POST';
  $content = http_build_query(['params' => $params], '', '&', PHP_QUERY_RFC3986);
}
elseif ($mode === 'download') {
  $url = getenv('LAB_HTTP_URL');
  $parts = parse_url($url);
  if (!is_array($parts)) {
    fwrite(STDERR, "refusing a non-local file URL\n");
    exit(73);
  }
  $hasAuthorityOrFragment = isset($parts['user']) || isset($parts['pass']) || isset($parts['fragment']);
  $relative = !isset($parts['scheme']) && !isset($parts['host']) && !isset($parts['port']) && !$hasAuthorityOrFragment && ($parts['path'] ?? null) === '/civicrm/file';
  $absolute = ($parts['scheme'] ?? null) === 'http' && ($parts['host'] ?? null) === 'application' && (!isset($parts['port']) || $parts['port'] === 80) && !$hasAuthorityOrFragment && ($parts['path'] ?? null) === '/civicrm/file';
  if (!$relative && !$absolute) {
    fwrite(STDERR, "refusing a non-local file URL\n");
    exit(73);
  }
  parse_str($parts['query'] ?? '', $query);
  $queryKeys = array_keys($query);
  sort($queryKeys, SORT_STRING);
  if ($queryKeys !== ['fcs', 'id', 'reset'] || ($query['reset'] ?? null) !== '1' || !ctype_digit((string) ($query['id'] ?? '')) || !is_string($query['fcs'] ?? null) || !preg_match('/^[A-Za-z0-9._~-]{16,2048}$/', $query['fcs'])) {
    fwrite(STDERR, "private file URL is not signed\n");
    exit(74);
  }
  if ($relative) $url = 'http://application' . $url;
}
elseif ($mode === 'ui') {
  $url = getenv('LAB_HTTP_URL');
  $parts = parse_url($url);
  if (!is_array($parts) || isset($parts['scheme']) || isset($parts['host']) || isset($parts['port']) || isset($parts['user']) || isset($parts['pass']) || isset($parts['fragment'])) {
    fwrite(STDERR, "refusing a non-local UI URL\n");
    exit(77);
  }
  parse_str($parts['query'] ?? '', $query);
  $queryKeys = array_keys($query);
  sort($queryKeys, SORT_STRING);
  $contactSummary = ($parts['path'] ?? null) === '/civicrm/contact/view' && $queryKeys === ['cid', 'reset'];
  if (!$contactSummary || ($query['reset'] ?? null) !== '1' || !ctype_digit((string) ($query['cid'] ?? '')) || (int) $query['cid'] < 1) {
    fwrite(STDERR, "refusing an unrecognized UI route\n");
    exit(78);
  }
  $url = 'http://application' . $url;
}
else {
  fwrite(STDERR, "unknown bounded HTTP mode\n");
  exit(75);
}
$headers = [
  'Authorization: Basic ' . base64_encode($username . ':' . $password),
  'Connection: close',
];
if ($mode !== 'ui') $headers[] = 'X-Requested-With: XMLHttpRequest';
if ($content !== null) $headers[] = 'Content-Type: application/x-www-form-urlencoded';
$context = stream_context_create(['http' => [
  'method' => $method,
  'header' => implode("\r\n", $headers),
  'content' => $content ?? '',
  'ignore_errors' => true,
  'follow_location' => 0,
  'max_redirects' => 0,
  'protocol_version' => 1.1,
  'timeout' => 20,
]]);
$body = @file_get_contents($url, false, $context);
if ($body === false) {
  fwrite(STDERR, "local HTTP request failed\n");
  exit(76);
}
$status = 0;
foreach (($http_response_header ?? []) as $header) {
  if (preg_match('/^HTTP\\/\\S+\\s+(\\d{3})\\b/', $header, $matches)) $status = (int) $matches[1];
}
fwrite(STDOUT, pack('N', $status));
fwrite(STDOUT, $body);
`;

const networkProbePhp = String.raw`
$dnsName = 'exitdrill-dns-probe.invalid';
$resolved = @gethostbyname($dnsName);
$dnsFailed = $resolved === $dnsName;
$errorNumber = 0;
$errorText = '';
$socket = @fsockopen('1.1.1.1', 443, $errorNumber, $errorText, 2.0);
$egressBlocked = $socket === false;
if (is_resource($socket)) fclose($socket);
echo "EXITDRILL_JSON:", json_encode(['dns_failed' => $dnsFailed, 'egress_blocked' => $egressBlocked]);
`;

function createLabRuntime(envFile, projectName, composeEnvironment) {
  const baseArgs = [
    "compose",
    "--project-name",
    projectName,
    "--env-file",
    envFile,
    "-f",
    composeFile,
  ];

  async function docker(args, options = {}) {
    return runCommand("docker", args, options);
  }

  async function compose(args, options = {}) {
    return docker([...baseArgs, ...args], {
      ...options,
      env: { ...composeEnvironment, ...(options.env ?? {}) },
    });
  }

  async function trusted(operation, payload = {}) {
    const operationLabel =
      operation === "api4" ? `${payload.entity}.${payload.action}` : operation;
    const result = await compose(
      [
        "exec",
        "-T",
        "-u",
        "www-data",
        "-e",
        "LAB_TRUSTED_OP",
        "-e",
        "LAB_TRUSTED_PAYLOAD",
        "application",
        "cv",
        "ev",
        trustedPhp,
      ],
      {
        env: {
          LAB_TRUSTED_OP: operation,
          LAB_TRUSTED_PAYLOAD: JSON.stringify(payload),
        },
        timeoutMs: 120_000,
        label: `trusted CiviCRM ${operationLabel}`,
      },
    );
    const text = result.stdout.toString("utf8");
    const marker = "EXITDRILL_JSON:";
    const markerIndex = text.lastIndexOf(marker);
    if (markerIndex < 0) fail(`trusted CiviCRM ${operationLabel} did not return bounded JSON`);
    return parseJsonBytes(
      Buffer.from(text.slice(markerIndex + marker.length)),
      `trusted ${operationLabel}`,
    );
  }

  async function api4(entity, action, params = {}) {
    const result = requireObject(
      await trusted("api4", { entity, action, params }),
      `${entity}.${action} trusted response`,
    );
    requireArray(result.values, `${entity}.${action} trusted values`);
    if (result.count !== result.values.length) fail(`${entity}.${action} trusted count mismatch`);
    return result;
  }

  async function http(mode, identity, values = {}) {
    const environment = {
      LAB_HTTP_MODE: mode,
      LAB_HTTP_USER: identity.username,
      LAB_HTTP_PASSWORD: identity.password,
    };
    const args = [
      "exec",
      "-T",
      "-u",
      "www-data",
      "-e",
      "LAB_HTTP_MODE",
      "-e",
      "LAB_HTTP_USER",
      "-e",
      "LAB_HTTP_PASSWORD",
    ];
    if (mode === "api4") {
      environment.LAB_HTTP_ENTITY = values.entity;
      environment.LAB_HTTP_ACTION = values.action;
      environment.LAB_HTTP_PARAMS = JSON.stringify(values.params ?? {});
      args.push(
        "-e",
        "LAB_HTTP_ENTITY",
        "-e",
        "LAB_HTTP_ACTION",
        "-e",
        "LAB_HTTP_PARAMS",
      );
    } else if (mode === "download" || mode === "ui") {
      environment.LAB_HTTP_URL = values.url;
      args.push("-e", "LAB_HTTP_URL");
    }
    args.push("application", "php", "-r", httpPhp);
    const response = await compose(args, {
      env: environment,
      timeoutMs: 60_000,
      label: `local CiviCRM ${mode} request`,
    });
    if (response.stdout.length < httpMarkerSize) fail(`local CiviCRM ${mode} response was truncated`);
    const status = response.stdout.readUInt32BE(0);
    return { status, body: response.stdout.subarray(httpMarkerSize) };
  }

  async function api(identity, entity, action, params, expectedCount = null) {
    const identityKind = identityKinds.has(identity.kind) ? identity.kind : "unrecognized";
    const response = await http("api4", identity, { entity, action, params });
    if (response.status !== 200) {
      const detail = boundedHttpErrorMessage(response.body);
      fail(
        `${identityKind} ${entity}.${action} returned HTTP ${response.status}${detail ? `: ${detail}` : ""}`,
      );
    }
    const result = requireObject(parseJsonBytes(response.body, `${entity}.${action}`), `${entity}.${action}`);
    const values = requireArray(result.values, `${entity}.${action} values`);
    if (!Number.isSafeInteger(result.count) || result.count !== values.length) {
      fail(`${entity}.${action} returned an inconsistent count`);
    }
    if (!Number.isSafeInteger(result.countFetched) || result.countFetched !== values.length) {
      fail(`${entity}.${action} returned an inconsistent fetched count`);
    }
    if (
      result.countMatched !== undefined &&
      (!Number.isSafeInteger(result.countMatched) || result.countMatched !== values.length)
    ) {
      fail(`${entity}.${action} returned an inconsistent matched count`);
    }
    if (expectedCount !== null && result.count !== expectedCount) {
      fail(`${entity}.${action} expected ${expectedCount} row(s), received ${result.count}`);
    }
    return { body: response.body, result };
  }

  async function identity(identityRecord) {
    const response = await http("identity", identityRecord);
    if (response.status !== 200) fail(`AuthX identity request returned HTTP ${response.status}`);
    const result = requireObject(parseJsonBytes(response.body, "AuthX identity"), "AuthX identity");
    assert.deepEqual(Object.keys(result), ["contact_id", "user_id", "flow", "cred"]);
    if (
      requireInteger(result.contact_id, "AuthX contact id") !== identityRecord.contactId ||
      requireInteger(result.user_id, "AuthX user id") !== identityRecord.userId ||
      result.flow !== "header" ||
      result.cred !== "pass"
    ) {
      fail(`AuthX identity did not match the provisioned ${identityRecord.kind} principal`);
    }
    return { body: response.body, result };
  }

  const browserContainerName = `${projectName}-browser`;
  let browserContainerActive = false;

  async function browserWorkflow(identityRecord) {
    browserContainerActive = true;
    let completedCleanly = false;
    try {
      const completed = await docker(
        [
          "run",
          "--rm",
          "--init",
          "--pull",
          "never",
          "--name",
          browserContainerName,
          "--network",
          `${projectName}_lab`,
          "--read-only",
          "--tmpfs",
          "/tmp:rw,noexec,nosuid,size=268435456",
          "--shm-size",
          "1073741824",
          "--cap-drop",
          "ALL",
          "--security-opt",
          "no-new-privileges:true",
          "--mount",
          `type=bind,src=${browserWorkflowScript},dst=/work/civicrm_browser_workflow.mjs,readonly`,
          "--mount",
          `type=bind,src=${browserNodeModules},dst=/work/node_modules,readonly`,
          "-e",
          "EXITDRILL_BROWSER_USERNAME",
          "-e",
          "EXITDRILL_BROWSER_PASSWORD",
          browserImage,
          "node",
          "/work/civicrm_browser_workflow.mjs",
        ],
        {
          env: {
            EXITDRILL_BROWSER_USERNAME: identityRecord.username,
            EXITDRILL_BROWSER_PASSWORD: identityRecord.password,
          },
          timeoutMs: 120_000,
          label: "isolated CiviCRM browser workflow",
        },
      );
      const observation = requireObject(
        parseJsonBytes(completed.stdout, "browser workflow observation"),
        "browser workflow observation",
      );
      completedCleanly = true;
      return observation;
    } finally {
      if (completedCleanly) browserContainerActive = false;
    }
  }

  async function cleanupBrowser() {
    if (!browserContainerActive) return;
    const listed = await docker(
      ["container", "ls", "--all", "--quiet", "--filter", `name=^/${browserContainerName}$`],
      {
        timeoutMs: 10_000,
        label: "browser container cleanup inspection",
        allowAfterInterruption: true,
      },
    );
    const containerIds = listed.stdout.toString("utf8").trim().split(/\s+/).filter(Boolean);
    if (containerIds.length === 0) {
      browserContainerActive = false;
      return;
    }
    if (containerIds.length !== 1 || !/^[0-9a-f]{12,64}$/.test(containerIds[0])) {
      fail("browser container cleanup inspection returned an unexpected result");
    }
    await docker(["container", "rm", "--force", browserContainerName], {
      timeoutMs: 30_000,
      label: "browser container cleanup",
      allowAfterInterruption: true,
    });
    browserContainerActive = false;
  }

  return { api, api4, browserWorkflow, cleanupBrowser, compose, docker, http, identity, trusted };
}

async function validateCompose(runtime, composeEnvironment) {
  await runtime.docker(["image", "inspect", applicationImage, databaseImage, browserImage], {
    timeoutMs: 30_000,
    label: "pinned local image check",
  });
  const configured = await runtime.compose(["config", "--format", "json"], {
    timeoutMs: 30_000,
    label: "Compose configuration validation",
  });
  const config = requireObject(
    parseJsonBytes(configured.stdout, "Compose configuration"),
    "Compose configuration",
  );
  const services = requireObject(config.services, "Compose services");
  const application = requireObject(services.application, "Compose application service");
  const database = requireObject(services.database, "Compose database service");
  if (application.image !== applicationImage || database.image !== databaseImage) {
    fail("Compose did not resolve to the exact reviewed image references");
  }
  if (application.pull_policy !== "never" || database.pull_policy !== "never") {
    fail("every Compose service must use pull_policy never");
  }
  requireExact(
    application.environment,
    {
      CIVICRM_DB_HOST: "database",
      CIVICRM_DB_NAME: composeEnvironment.CIVICRM_DB_NAME,
      CIVICRM_DB_PASSWORD: composeEnvironment.CIVICRM_DB_PASSWORD,
      CIVICRM_DB_PORT: "3306",
      CIVICRM_DB_USER: composeEnvironment.CIVICRM_DB_USER,
      CIVICRM_UF_BASEURL: "http://application",
    },
    "Compose application environment",
  );
  requireExact(
    database.environment,
    {
      MYSQL_DATABASE: composeEnvironment.CIVICRM_DB_NAME,
      MYSQL_PASSWORD: composeEnvironment.CIVICRM_DB_PASSWORD,
      MYSQL_ROOT_PASSWORD: composeEnvironment.CIVICRM_DB_ROOT_PASSWORD,
      MYSQL_USER: composeEnvironment.CIVICRM_DB_USER,
    },
    "Compose database environment",
  );
  for (const [name, service] of Object.entries(services)) {
    if (service.ports !== undefined || service.expose !== undefined) {
      fail(`Compose service ${name} must not publish or expose a port`);
    }
  }
  const networks = requireObject(config.networks, "Compose networks");
  const labNetwork = requireObject(networks.lab, "Compose lab network");
  if (labNetwork.internal !== true) fail("Compose lab network must be internal");
}

async function countTrusted(runtime, entity, where = []) {
  const result = await runtime.api4(entity, "get", {
    select: ["id"],
    where,
    limit: 0,
  });
  return result.values.length;
}

function exactOne(result, label) {
  if (result.values.length !== 1) fail(`${label} must return exactly one row`);
  return requireObject(result.values[0], `${label} row`);
}

async function createTrusted(runtime, entity, values, requiredFields = ["id"]) {
  const row = exactOne(
    await runtime.api4(entity, "create", { values }),
    `${entity}.create`,
  );
  for (const field of requiredFields) {
    if (!Object.hasOwn(row, field)) {
      fail(`${entity}.create omitted required response field ${field}`);
    }
  }
  return row;
}

async function writeCapture(stageDir, relativePath, bytes, metadata) {
  if (!capturePaths.includes(relativePath)) fail(`refusing unexpected capture path ${relativePath}`);
  const absolutePath = join(stageDir, ...relativePath.split("/"));
  await writeFile(absolutePath, bytes, { flag: "wx", mode: 0o600 });
  metadata.set(relativePath, {
    path: relativePath,
    bytes: bytes.length,
    sha256: sha256(bytes),
  });
}

async function configureTarget(runtime, credentials) {
  await runtime.compose(
    [
      "exec",
      "-T",
      "-u",
      "www-data",
      "-e",
      "CIVICRM_ADMIN_USER",
      "-e",
      "CIVICRM_ADMIN_PASS",
      "application",
      "civicrm-docker-install",
    ],
    {
      env: {
        CIVICRM_ADMIN_USER: credentials.adminUsername,
        CIVICRM_ADMIN_PASS: credentials.adminPassword,
      },
      timeoutMs: 420_000,
      label: "CiviCRM Standalone installation",
    },
  );

  await runtime.compose(
    ["exec", "-T", "-u", "www-data", "application", "php", "-r", hibpPatchPhp],
    { timeoutMs: 30_000, label: "HIBP offline control installation" },
  );
  await runtime.compose(
    ["exec", "-T", "-u", "www-data", "application", "cv", "en", "civi_case"],
    { timeoutMs: 120_000, label: "CiviCase enablement" },
  );
  await runtime.trusted("configure_safety");
  await runtime.api4("Job", "update", {
    values: { is_active: false },
    where: [["is_active", "=", true]],
  });

  const safety = requireObject(await runtime.trusted("inspect_safety"), "CiviCRM safety state");
  assert.deepEqual(safety, {
    version: "6.16.2",
    hibp_disabled: true,
    mail_disabled: true,
    authx_guards: ["perm"],
    authx_header_cred: ["pass"],
    authx_header_user: "require",
    active_jobs: 0,
  });

  const freshCounts = {
    contacts: await countTrusted(runtime, "Contact"),
    cases: await countTrusted(runtime, "Case"),
    relationships: await countTrusted(runtime, "Relationship"),
    files: await countTrusted(runtime, "File"),
    entityFiles: await countTrusted(runtime, "EntityFile"),
  };
  assert.deepEqual(freshCounts, {
    contacts: 2,
    cases: 0,
    relationships: 0,
    files: 0,
    entityFiles: 0,
  });

  const relationshipType = exactOne(
    await runtime.api4("RelationshipType", "get", {
      select: ["id", "name_a_b", "name_b_a", "is_active"],
      where: [["name_a_b", "=", "Case Coordinator is"]],
      limit: 2,
    }),
    "built-in Case Coordinator relationship type",
  );
  if (
    requireInteger(relationshipType.id, "built-in relationship type id") !== 9 ||
    relationshipType.name_b_a !== "Case Coordinator" ||
    !relationshipType.is_active
  ) {
    fail("CiviCRM 6.16.2 did not contain the exact built-in Case Coordinator relationship type");
  }

  const personGroup = await createTrusted(runtime, "CustomGroup", {
    name: personGroupName,
    title: "ExitDrill Person Profile",
    extends: "Contact",
    style: "Inline",
    collapse_display: false,
    is_active: true,
    is_multiple: false,
  });
  const caseGroup = await createTrusted(runtime, "CustomGroup", {
    name: caseGroupName,
    title: "ExitDrill Case Profile",
    extends: "Case",
    style: "Inline",
    collapse_display: false,
    is_active: true,
    is_multiple: false,
  });

  const customFields = [
    [personGroup.id, "source_id", "Source ID", "String", "Text"],
    [personGroup.id, "source_display_name", "Source Display Name", "String", "Text"],
    [personGroup.id, "source_active", "Source Active", "Boolean", "Radio"],
    [caseGroup.id, "source_id", "Source ID", "String", "Text"],
    [caseGroup.id, "source_status", "Source Status", "String", "Text"],
    [caseGroup.id, "source_priority", "Source Priority", "Int", "Text"],
    [caseGroup.id, "source_document_id", "Source Document ID", "String", "Text"],
  ];
  for (let index = 0; index < customFields.length; index += 1) {
    const [customGroupId, name, label, dataType, htmlType] = customFields[index];
    await createTrusted(runtime, "CustomField", {
      custom_group_id: customGroupId,
      name,
      label,
      data_type: dataType,
      html_type: htmlType,
      is_required: false,
      is_searchable: name === "source_id",
      is_active: true,
      weight: index + 1,
    });
  }

  const configuredCaseType = await createTrusted(
    runtime,
    "CaseType",
    {
      name: caseTypeName,
      title: "ExitDrill Civic Case",
      is_active: true,
      weight: 1,
      definition: {
        activityTypes: [
          { name: "Open Case", max_instances: 1 },
          { name: "Change Case Type" },
          { name: "Change Case Status" },
          { name: "Change Case Start Date" },
        ],
        activitySets: [
          {
            name: "standard_timeline",
            label: "Standard Timeline",
            timeline: 1,
            activityTypes: [{ name: "Open Case", status: "Completed" }],
          },
        ],
        caseRoles: [{ name: "Case Coordinator", creator: 1, manager: 1 }],
      },
    },
    ["id", "name"],
  );
  if (configuredCaseType.name !== caseTypeName) fail("configured case type name changed");

  const configuredCounts = {
    customGroups: await countTrusted(runtime, "CustomGroup", [
      ["name", "IN", [personGroupName, caseGroupName]],
    ]),
    customFields: await countTrusted(runtime, "CustomField", [
      ["custom_group_id", "IN", [personGroup.id, caseGroup.id]],
    ]),
    caseTypes: await countTrusted(runtime, "CaseType", [["name", "=", caseTypeName]]),
  };
  assert.deepEqual(configuredCounts, { customGroups: 2, customFields: 7, caseTypes: 1 });

  return {
    caseTypeId: requireInteger(configuredCaseType.id, "configured case type id"),
    relationshipTypeId: requireInteger(relationshipType.id, "relationship type id"),
  };
}

async function provisionPrincipals(runtime, runSuffix) {
  const roles = [
    {
      kind: "writer",
      permissions: [
        "access AJAX API",
        "access CiviCRM",
        "access uploaded files",
        "add contacts",
        "view all contacts",
        "edit all contacts",
        "access all custom data",
        "add cases",
        "access all cases and activities",
      ],
    },
    {
      kind: "reader",
      permissions: [
        "access AJAX API",
        "access CiviCRM",
        "access uploaded files",
        "view all contacts",
        "access all custom data",
        "access all cases and activities",
      ],
    },
    {
      kind: "deny",
      permissions: ["access AJAX API", "access CiviCRM", "view my contact"],
    },
    {
      kind: "allow",
      permissions: ["access AJAX API", "access CiviCRM", "view my contact"],
    },
  ];

  const identities = new Map();
  for (const roleDefinition of roles) {
    const role = await createTrusted(
      runtime,
      "Role",
      {
        name: `exitdrill_${roleDefinition.kind}`,
        label: `ExitDrill ${roleDefinition.kind}`,
        permissions: roleDefinition.permissions,
        is_active: true,
      },
      ["id", "name"],
    );
    const contactValues = {
      contact_type: "Individual",
      first_name: `ExitDrill ${roleDefinition.kind} principal`,
    };
    if (roleDefinition.kind === "allow") {
      contactValues[`${personGroupName}.source_id`] = "target-principal-allowed";
      contactValues[`${personGroupName}.source_display_name`] = "ExitDrill allowed principal";
      contactValues[`${personGroupName}.source_active`] = true;
    }
    const contact = await createTrusted(runtime, "Contact", contactValues, ["id"]);
    const password = secret();
    const username = `exitdrill_${roleDefinition.kind}_${runSuffix}`;
    const user = await createTrusted(
      runtime,
      "User",
      {
        username,
        uf_name: `${username}@invalid.example`,
        contact_id: contact.id,
        password,
        is_active: true,
      },
      ["id", "contact_id", "username"],
    );
    await createTrusted(runtime, "UserRole", {
      user_id: user.id,
      role_id: role.id,
    });
    identities.set(roleDefinition.kind, {
      kind: roleDefinition.kind,
      username,
      password,
      contactId: requireInteger(contact.id, `${roleDefinition.kind} contact id`),
      userId: requireInteger(user.id, `${roleDefinition.kind} user id`),
      roleId: requireInteger(role.id, `${roleDefinition.kind} role id`),
    });
  }

  const helper = await createTrusted(
    runtime,
    "Contact",
    {
      contact_type: "Individual",
      first_name: "ExitDrill target helper",
      [`${personGroupName}.source_id`]: "target-helper",
      [`${personGroupName}.source_display_name`]: "ExitDrill target helper",
      [`${personGroupName}.source_active`]: true,
    },
    ["id"],
  );

  const principalIds = [...identities.values()].flatMap((identity) => [
    `contact:${identity.contactId}`,
    `user:${identity.userId}`,
    `role:${identity.roleId}`,
  ]);
  if (new Set(principalIds).size !== principalIds.length) {
    fail("writer, reader, allow, and deny principal records must all be distinct");
  }
  if (
    (await countTrusted(runtime, "Role", [
      ["name", "IN", ["exitdrill_writer", "exitdrill_reader", "exitdrill_deny", "exitdrill_allow"]],
    ])) !== 4
  ) {
    fail("exactly four ExitDrill roles must exist");
  }
  await runtime.trusted("rebuild");
  const identityEvidence = new Map();
  for (const identity of identities.values()) {
    identityEvidence.set(identity.kind, await runtime.identity(identity));
  }
  return {
    identities,
    identityEvidence,
    helperContactId: requireInteger(helper.id, "helper contact id"),
  };
}

async function assertApplicationEmptyBeforeWrite(runtime) {
  const counts = {
    sourceContacts: await countTrusted(runtime, "Contact", [
      [`${personGroupName}.source_id`, "IN", sourcePersonIds],
    ]),
    cases: await countTrusted(runtime, "Case"),
    relationships: await countTrusted(runtime, "Relationship"),
    files: await countTrusted(runtime, "File"),
    entityFiles: await countTrusted(runtime, "EntityFile"),
  };
  assert.deepEqual(counts, {
    sourceContacts: 0,
    cases: 0,
    relationships: 0,
    files: 0,
    entityFiles: 0,
  });
}

async function loadBusinessSubset(runtime, fixture, targetConfig, principals) {
  const writer = principals.identities.get("writer");
  const contactIds = new Map();
  for (const person of fixture.people) {
    const created = await runtime.api(
      writer,
      "Contact",
      "create",
      {
        values: {
          contact_type: "Individual",
          first_name: person.display_name,
          [`${personGroupName}.source_id`]: String(person.id),
          [`${personGroupName}.source_display_name`]: person.display_name,
          [`${personGroupName}.source_active`]: Boolean(person.active),
        },
      },
      1,
    );
    const contactId = requireInteger(
      created.result.values[0].id,
      `target contact id for source person ${person.id}`,
    );
    contactIds.set(person.id, contactId);
  }

  const caseIds = new Map();
  for (const sourceCase of fixture.cases) {
    const link = fixture.links.find((candidate) => candidate.case_id === sourceCase.id);
    if (!link || link.relation_type !== "assigned_to") {
      fail(`source case ${sourceCase.id} does not have its exact assigned_to row`);
    }
    const clientContactId = contactIds.get(link.person_id);
    if (!clientContactId) fail(`source case ${sourceCase.id} refers to an unknown source person`);
    const created = await runtime.api(
      writer,
      "Case",
      "create",
      {
        values: {
          case_type_id: targetConfig.caseTypeId,
          contact_id: principals.helperContactId,
          creator_id: clientContactId,
          "status_id:name": "Open",
          start_date: "2026-08-02",
          subject:
            sourceCase.id === 1
              ? "Synthetic ExitDrill Case Alpha"
              : "Synthetic ExitDrill Case Bravo",
          [`${caseGroupName}.source_id`]: String(sourceCase.id),
          [`${caseGroupName}.source_status`]: sourceCase.status,
          [`${caseGroupName}.source_priority`]: sourceCase.priority,
          [`${caseGroupName}.source_document_id`]: sourceCase.document,
        },
      },
      1,
    );
    const caseId = requireInteger(
      created.result.values[0].id,
      `target case id for source case ${sourceCase.id}`,
    );
    caseIds.set(sourceCase.id, caseId);

    const generatedRelationship = await runtime.api(
      writer,
      "Relationship",
      "get",
      {
        select: ["id", "contact_id_a", "contact_id_b", "relationship_type_id", "case_id"],
        where: [
          ["case_id", "=", caseId],
          ["relationship_type_id", "=", targetConfig.relationshipTypeId],
        ],
        limit: 2,
      },
      1,
    );
    const relationship = generatedRelationship.result.values[0];
    if (
      requireInteger(relationship.contact_id_a, "generated relationship contact A") !==
        principals.helperContactId ||
      requireInteger(relationship.contact_id_b, "generated relationship contact B") !==
        clientContactId ||
      requireInteger(relationship.case_id, "generated relationship case id") !== caseId
    ) {
      fail(`CiviCase generated an unexpected coordinator relationship for source case ${sourceCase.id}`);
    }
    await runtime.api(
      writer,
      "Relationship",
      "update",
      {
        values: { description: relationshipDescription },
        where: [["id", "=", relationship.id]],
      },
      1,
    );
    requireInteger(relationship.id, "relationship id");
  }

  const fileIds = new Map();
  for (const sourceFile of fixture.files) {
    const created = await runtime.api(
      writer,
      "File",
      "create",
      {
        values: {
          file_name: `${sourceFile.id}.txt`,
          mime_type: sourceFile.type,
          content: fixture.assets.get(sourceFile.id).toString("utf8"),
          description: sourceFile.id,
          is_public: false,
        },
      },
      1,
    );
    const row = created.result.values[0];
    if (row.is_public !== false) {
      fail(`target file for ${sourceFile.id} was not private`);
    }
    const fileId = requireInteger(row.id, `target file id for ${sourceFile.id}`);
    const sourceCase = fixture.cases.find((candidate) => candidate.document === sourceFile.id);
    const caseId = sourceCase && caseIds.get(sourceCase.id);
    if (!caseId) fail(`source file ${sourceFile.id} has no exact target case owner`);
    await runtime.api(
      writer,
      "EntityFile",
      "create",
      {
        values: {
          entity_table: "civicrm_case",
          entity_id: caseId,
          file_id: fileId,
        },
      },
      1,
    );
    fileIds.set(sourceFile.id, fileId);
  }

  if (contactIds.size !== 3 || caseIds.size !== 2 || fileIds.size !== 2) {
    fail("target write did not preserve the frozen business subset denominator");
  }
  return { contactIds };
}

async function configureContactAcl(runtime, principals, loaded) {
  const targetGroup = await createTrusted(
    runtime,
    "Group",
    {
      name: "exitdrill_target_records",
      title: "ExitDrill Target Records",
      group_type: ["Access Control"],
      is_active: true,
    },
    ["id"],
  );
  const allowGroup = await createTrusted(
    runtime,
    "Group",
    {
      name: "exitdrill_acl_allow_principals",
      title: "ExitDrill ACL Allow Principals",
      group_type: ["Access Control"],
      is_active: true,
    },
    ["id"],
  );
  const denyGroup = await createTrusted(
    runtime,
    "Group",
    {
      name: "exitdrill_acl_deny_principals",
      title: "ExitDrill ACL Deny Principals",
      group_type: ["Access Control"],
      is_active: true,
    },
    ["id"],
  );

  const memberships = [
    [targetGroup.id, loaded.contactIds.get(1)],
    [allowGroup.id, principals.identities.get("reader").contactId],
    [allowGroup.id, principals.identities.get("allow").contactId],
    [denyGroup.id, principals.identities.get("deny").contactId],
  ];
  for (const [groupId, contactId] of memberships) {
    await createTrusted(runtime, "GroupContact", {
      group_id: groupId,
      contact_id: contactId,
      status: "Added",
    });
  }

  const allowRole = await createTrusted(
    runtime,
    "OptionValue",
    {
      "option_group_id:name": "acl_role",
      name: "exitdrill_acl_allow",
      label: "ExitDrill ACL Allow",
      is_active: true,
    },
    ["id", "value"],
  );
  const denyRole = await createTrusted(
    runtime,
    "OptionValue",
    {
      "option_group_id:name": "acl_role",
      name: "exitdrill_acl_deny",
      label: "ExitDrill ACL Deny",
      is_active: true,
    },
    ["id", "value"],
  );
  const allowRoleValue = requireInteger(Number(allowRole.value), "allow ACL role value");
  const denyRoleValue = requireInteger(Number(denyRole.value), "deny ACL role value");
  if (allowRoleValue === denyRoleValue) fail("allow and deny ACL role values must differ");

  await createTrusted(runtime, "ACLEntityRole", {
    acl_role_id: allowRoleValue,
    entity_table: "civicrm_group",
    entity_id: allowGroup.id,
    is_active: true,
  });
  await createTrusted(runtime, "ACLEntityRole", {
    acl_role_id: denyRoleValue,
    entity_table: "civicrm_group",
    entity_id: denyGroup.id,
    is_active: true,
  });
  await createTrusted(runtime, "ACL", {
    name: "ExitDrill allow target record",
    deny: false,
    entity_table: "civicrm_acl_role",
    entity_id: allowRoleValue,
    operation: "View",
    object_table: "civicrm_group",
    object_id: targetGroup.id,
    is_active: true,
    priority: 10,
  });
  await createTrusted(runtime, "ACL", {
    name: "ExitDrill deny target record",
    deny: true,
    entity_table: "civicrm_acl_role",
    entity_id: denyRoleValue,
    operation: "View",
    object_table: "civicrm_group",
    object_id: targetGroup.id,
    is_active: true,
    priority: 10,
  });
  await runtime.trusted("rebuild");
  const aclCounts = {
    aclEntityRoles: await countTrusted(runtime, "ACLEntityRole", [
      ["acl_role_id", "IN", [allowRoleValue, denyRoleValue]],
      ["entity_table", "=", "civicrm_group"],
      ["entity_id", "IN", [allowGroup.id, denyGroup.id]],
    ]),
    acls: await countTrusted(runtime, "ACL", [
      ["name", "IN", ["ExitDrill allow target record", "ExitDrill deny target record"]],
    ]),
    groupContacts: await countTrusted(runtime, "GroupContact", [
      ["group_id", "IN", [targetGroup.id, allowGroup.id, denyGroup.id]],
      ["status", "=", "Added"],
    ]),
    groups: await countTrusted(runtime, "Group", [
      [
        "name",
        "IN",
        [
          "exitdrill_target_records",
          "exitdrill_acl_allow_principals",
          "exitdrill_acl_deny_principals",
        ],
      ],
    ]),
    roles: await countTrusted(runtime, "OptionValue", [
      ["option_group_id:name", "=", "acl_role"],
      ["name", "IN", ["exitdrill_acl_allow", "exitdrill_acl_deny"]],
    ]),
  };
  assert.deepEqual(aclCounts, {
    aclEntityRoles: 2,
    acls: 2,
    groupContacts: 4,
    groups: 3,
    roles: 2,
  });
}

async function captureReadback(runtime, fixture, principals, stageDir) {
  const metadata = new Map();
  const reader = principals.identities.get("reader");
  const allow = principals.identities.get("allow");
  const deny = principals.identities.get("deny");

  const contacts = await runtime.api(
    reader,
    "Contact",
    "get",
    {
      select: [
        "id",
        "display_name",
        `${personGroupName}.source_id`,
        `${personGroupName}.source_display_name`,
        `${personGroupName}.source_active`,
      ],
      where: [[`${personGroupName}.source_id`, "IN", sourcePersonIds]],
      orderBy: { [`${personGroupName}.source_id`]: "ASC" },
      limit: 4,
    },
    3,
  );
  const contactSourceIds = contacts.result.values.map((row) => row[`${personGroupName}.source_id`]);
  assert.deepEqual(contactSourceIds, sourcePersonIds);
  const readerContactIds = new Map();
  for (const [index, row] of contacts.result.values.entries()) {
    const source = fixture.people[index];
    const targetId = requireInteger(row.id, "captured contact id");
    if (
      row.display_name !== source.display_name ||
      row[`${personGroupName}.source_display_name`] !== source.display_name ||
      row[`${personGroupName}.source_active`] !== Boolean(source.active)
    ) {
      fail(`reader contact readback changed source person ${source.id}`);
    }
    if (readerContactIds.has(source.id) || [...readerContactIds.values()].includes(targetId)) {
      fail("reader contact readback returned duplicate source or target identities");
    }
    readerContactIds.set(source.id, targetId);
  }

  const cases = await runtime.api(
    reader,
    "Case",
    "get",
    {
      select: [
        "id",
        "case_type_id:name",
        "subject",
        "start_date",
        "status_id:name",
        `${caseGroupName}.source_id`,
        `${caseGroupName}.source_status`,
        `${caseGroupName}.source_priority`,
        `${caseGroupName}.source_document_id`,
      ],
      where: [[`${caseGroupName}.source_id`, "IN", ["1", "2"]]],
      orderBy: { [`${caseGroupName}.source_id`]: "ASC" },
      limit: 3,
    },
    2,
  );
  const readerCaseIds = new Map();
  for (const [index, row] of cases.result.values.entries()) {
    const source = fixture.cases[index];
    const targetId = requireInteger(row.id, "captured case id");
    if (
      row["case_type_id:name"] !== caseTypeName ||
      row["status_id:name"] !== "Open" ||
      row[`${caseGroupName}.source_id`] !== String(source.id) ||
      row[`${caseGroupName}.source_status`] !== source.status ||
      row[`${caseGroupName}.source_priority`] !== source.priority ||
      row[`${caseGroupName}.source_document_id`] !== source.document
    ) {
      fail(`reader case readback changed source case ${source.id}`);
    }
    if (readerCaseIds.has(source.id) || [...readerCaseIds.values()].includes(targetId)) {
      fail("reader case readback returned duplicate source or target identities");
    }
    readerCaseIds.set(source.id, targetId);
  }

  const relationships = await runtime.api(
    reader,
    "Relationship",
    "get",
    {
      select: [
        "id",
        "contact_id_a",
        "contact_id_b",
        "relationship_type_id.name_a_b",
        "case_id",
        "description",
        "is_active",
      ],
      where: [["description", "=", relationshipDescription]],
      orderBy: { case_id: "ASC" },
      limit: 3,
    },
    2,
  );
  const readerRelationshipIds = new Set();
  const helperContactIds = new Set();
  for (const row of relationships.result.values) {
    const targetRelationshipId = requireInteger(row.id, "captured relationship id");
    const targetCaseId = requireInteger(row.case_id, "captured relationship case id");
    const sourceCaseId = [...readerCaseIds.entries()].find(
      ([, candidateTargetId]) => candidateTargetId === targetCaseId,
    )?.[0];
    const sourceLink = fixture.links.find((candidate) => candidate.case_id === sourceCaseId);
    const helperContactId = requireInteger(row.contact_id_a, "captured helper contact id");
    const mismatchedFields = [
      ["source_case", !sourceLink],
      [
        "contact_id_b",
        !sourceLink ||
          requireInteger(row.contact_id_b, "captured relationship person id") !==
            readerContactIds.get(sourceLink.person_id),
      ],
      [
        "relationship_type",
        row["relationship_type_id.name_a_b"] !== "Case Coordinator is",
      ],
      ["description", row.description !== relationshipDescription],
      ["is_active", row.is_active !== true],
    ]
      .filter(([, mismatched]) => mismatched)
      .map(([field]) => field);
    if (mismatchedFields.length > 0) {
      fail(`reader relationship readback mismatched fields: ${mismatchedFields.join(", ")}`);
    }
    if (readerRelationshipIds.has(targetRelationshipId)) {
      fail("reader relationship readback returned duplicate target identities");
    }
    readerRelationshipIds.add(targetRelationshipId);
    helperContactIds.add(helperContactId);
  }
  const probeContactIds = new Set(
    [...principals.identities.values()].map((identity) => identity.contactId),
  );
  const helperContactId = [...helperContactIds][0];
  if (
    helperContactIds.size !== 1 ||
    [...readerContactIds.values()].includes(helperContactId) ||
    probeContactIds.has(helperContactId)
  ) {
    fail("reader relationships did not reconstruct one independent target-only helper contact");
  }

  const files = await runtime.api(
    reader,
    "File",
    "get",
    {
      select: ["id", "file_name", "mime_type", "description", "is_public"],
      where: [["description", "IN", sourceAssetIds]],
      orderBy: { description: "ASC" },
      limit: 3,
    },
    2,
  );
  const readerFileIds = new Map();
  for (const [index, row] of files.result.values.entries()) {
    const sourceFile = fixture.files[index];
    // File.create preserves the requested basename semantically, but the
    // 6.16.2 storage path normalizes non-alphanumerics before get readback.
    const expectedFileName = `${sourceFile.id.replaceAll("-", "_")}.txt`;
    const targetId = requireInteger(row.id, "captured file id");
    const mismatchedFields = [
      ["file_name", row.file_name !== expectedFileName],
      ["mime_type", row.mime_type !== sourceFile.type],
      ["description", row.description !== sourceFile.id],
      ["is_public", row.is_public !== false],
    ]
      .filter(([, mismatched]) => mismatched)
      .map(([field]) => field);
    if (mismatchedFields.length > 0) {
      fail(`reader file metadata readback mismatched fields: ${mismatchedFields.join(", ")}`);
    }
    if (readerFileIds.has(sourceFile.id) || [...readerFileIds.values()].includes(targetId)) {
      fail("reader file readback returned duplicate source or target identities");
    }
    readerFileIds.set(sourceFile.id, targetId);
  }

  const entityFiles = await runtime.api(
    reader,
    "EntityFile",
    "get",
    {
      select: ["id", "entity_table", "entity_id", "file_id"],
      where: [
        ["entity_table", "=", "civicrm_case"],
        ["file_id", "IN", [...readerFileIds.values()]],
      ],
      orderBy: { file_id: "ASC" },
      limit: 3,
    },
    2,
  );
  for (const row of entityFiles.result.values) {
    const sourceFileId = [...readerFileIds.entries()].find(
      ([, targetFileId]) => targetFileId === requireInteger(row.file_id, "captured file link id"),
    )?.[0];
    const sourceCase = fixture.cases.find((candidate) => candidate.document === sourceFileId);
    if (
      row.entity_table !== "civicrm_case" ||
      !sourceCase ||
      requireInteger(row.id, "captured EntityFile id") < 1 ||
      requireInteger(row.entity_id, "captured EntityFile entity id") !==
        readerCaseIds.get(sourceCase.id)
    ) {
      fail("reader EntityFile readback changed a case attachment owner");
    }
  }

  const identities = {
    writer: principals.identityEvidence.get("writer"),
    reader: await runtime.identity(reader),
    allow: await runtime.identity(allow),
    deny: await runtime.identity(deny),
  };
  if (!identities.writer) fail("pre-write writer identity evidence was unavailable");
  const identityTuples = Object.values(identities).map(
    ({ result }) => `${result.contact_id}:${result.user_id}`,
  );
  if (new Set(identityTuples).size !== 4) fail("captured AuthX identities were not distinct");

  const permissionParams = {
    select: ["id", "display_name"],
    where: [["id", "=", readerContactIds.get(1)]],
    orderBy: { id: "ASC" },
    limit: 2,
  };
  const permissionAllow = await runtime.api(allow, "Contact", "get", permissionParams, 1);
  const permissionDeny = await runtime.api(deny, "Contact", "get", permissionParams, 0);
  if (
    requireInteger(permissionAllow.result.values[0].id, "permission allow contact id") !==
      readerContactIds.get(1) ||
    permissionAllow.result.values[0].display_name !== fixture.people[0].display_name
  ) {
    fail("allow ACL probe returned the wrong protected contact");
  }

  const contactSummary = await runtime.http("ui", reader, {
    url: `/civicrm/contact/view?reset=1&cid=${readerContactIds.get(1)}`,
  });
  if (contactSummary.status !== 200) {
    fail(`contact-summary UI returned HTTP ${contactSummary.status}`);
  }
  const contactHtml = contactSummary.body.toString("utf8");
  const contactMarkers = {
    contact_name: contactHtml.includes("Synthetic Person Alpha"),
    contact_summary: contactHtml.includes("crm-contact-page"),
    cases_tab: contactHtml.includes(">Cases<"),
  };
  if (Object.values(contactMarkers).some((observed) => !observed)) {
    fail(`contact-summary UI omitted required marker(s): ${Object.entries(contactMarkers).filter(([, observed]) => !observed).map(([name]) => name).join(", ")}`);
  }

  const browserRun = await runtime.browserWorkflow(reader);
  requireExact(Object.keys(browserRun).sort(), ["accessibility", "workflow"], "browser run fields");
  const browserObservation = requireObject(browserRun.workflow, "browser workflow observation");
  requireExact(
    browserObservation,
    {
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
      target_profile: targetProfile,
    },
    "browser workflow observation",
  );
  const accessibilityObservation = requireObject(
    browserRun.accessibility,
    "browser accessibility observation",
  );
  requireExact(
    accessibilityObservation,
    {
      data_mode: "synthetic_only",
      engine: "axe-core",
      engine_version: "4.12.1",
      inapplicable_rule_count: 29,
      incomplete_rule_count: 0,
      page_scope: "manage_case_document",
      passes_rule_count: 32,
      retained_artifacts: [],
      rule_tags: ["wcag2a", "wcag2aa", "wcag21a", "wcag21aa"],
      schema_version: "exitdrill/civicrm-accessibility-observation/v0.1",
      target_profile: targetProfile,
      violations: [
        { impact: "serious", node_count: 4, rule_id: "color-contrast" },
        { impact: "serious", node_count: 2, rule_id: "link-in-text-block" },
      ],
    },
    "browser accessibility observation",
  );

  const downloadedAssets = new Map();
  for (const sourceFile of fixture.files) {
    const signed = await runtime.api(
      reader,
      "File",
      "get",
      {
        select: ["id", "description", "url"],
        where: [["id", "=", readerFileIds.get(sourceFile.id)]],
        limit: 1,
      },
      1,
    );
    const url = signed.result.values[0].url;
    if (typeof url !== "string" || !url) fail(`target file ${sourceFile.id} had no signed URL`);
    const download = await runtime.http("download", reader, { url });
    if (download.status !== 200) fail(`signed target file download returned HTTP ${download.status}`);
    if (!download.body.equals(fixture.assets.get(sourceFile.id))) {
      fail(`signed target file download changed attachment ${sourceFile.id}`);
    }
    downloadedAssets.set(sourceFile.id, download.body);
  }

  const payloads = new Map([
    ["contacts.json", capturedApiEnvelope(contacts.result)],
    ["cases.json", capturedApiEnvelope(cases.result)],
    ["relationships.json", capturedApiEnvelope(relationships.result)],
    ["files.json", capturedApiEnvelope(files.result)],
    ["entity-files.json", capturedApiEnvelope(entityFiles.result)],
    ["identity-writer.json", jsonDocument(identities.writer.result)],
    ["identity-reader.json", jsonDocument(identities.reader.result)],
    ["identity-allow.json", jsonDocument(identities.allow.result)],
    ["identity-deny.json", jsonDocument(identities.deny.result)],
    ["permission-allow.json", capturedApiEnvelope(permissionAllow.result)],
    ["permission-deny.json", capturedApiEnvelope(permissionDeny.result)],
    [
      "ui-contact-summary.json",
      jsonDocument({
        authenticated_identity: "reader",
        http_status: contactSummary.status,
        observed_labels: ["Cases", "Synthetic Person Alpha"],
        observed_regions: ["contact_summary"],
        route: "civicrm/contact/view",
        surface: "contact_summary",
      }),
    ],
    ["browser-workflow.json", jsonDocument(browserObservation)],
    ["browser-accessibility.json", jsonDocument(accessibilityObservation)],
    [`assets/${firstAssetId}.txt`, downloadedAssets.get(firstAssetId)],
    [`assets/${secondAssetId}.txt`, downloadedAssets.get(secondAssetId)],
  ]);
  for (const path of capturePaths) {
    const bytes = payloads.get(path);
    if (!Buffer.isBuffer(bytes)) fail(`capture payload ${path} was not produced`);
    await writeCapture(stageDir, path, bytes, metadata);
  }
  return metadata;
}

async function verifyTargetCounts(runtime) {
  const counts = {
    contacts: await countTrusted(runtime, "Contact", [
      [`${personGroupName}.source_id`, "IN", sourcePersonIds],
    ]),
    cases: await countTrusted(runtime, "Case", [
      [`${caseGroupName}.source_id`, "IN", ["1", "2"]],
    ]),
    relationships: await countTrusted(runtime, "Relationship", [
      ["description", "=", relationshipDescription],
    ]),
    files: await countTrusted(runtime, "File", [["description", "IN", sourceAssetIds]]),
    entityFiles: await countTrusted(runtime, "EntityFile"),
    caseContacts: await countTrusted(runtime, "CaseContact"),
    caseActivities: await countTrusted(runtime, "CaseActivity"),
  };
  assert.deepEqual(counts, {
    contacts: 3,
    cases: 2,
    relationships: 2,
    files: 2,
    entityFiles: 2,
    caseContacts: 2,
    caseActivities: 2,
  });
}

async function verifyNetworkFailure(runtime) {
  const result = await runtime.compose(
    ["exec", "-T", "-u", "www-data", "application", "php", "-r", networkProbePhp],
    { timeoutMs: 30_000, label: "internal-network failure probes" },
  );
  const text = result.stdout.toString("utf8");
  const marker = "EXITDRILL_JSON:";
  const markerIndex = text.lastIndexOf(marker);
  if (markerIndex < 0) fail("internal-network probes returned no bounded JSON");
  const state = parseJsonBytes(
    Buffer.from(text.slice(markerIndex + marker.length)),
    "internal-network probes",
  );
  assert.deepEqual(state, { dns_failed: true, egress_blocked: true });
}

function buildManifest(metadata, sourceNormalization) {
  const files = capturePaths.map((path) => {
    const item = metadata.get(path);
    if (!item) fail(`capture metadata is missing ${path}`);
    return item;
  });
  return {
    schema_version: "exitdrill/civicrm-target-roundtrip-bundle/v0.1",
    target_profile: targetProfile,
    source_profile: sourceProfile,
    data_mode: "synthetic_only",
    source_system: "Directus 11.17.4 synthetic civic-case sandbox",
    target_system: "CiviCRM Standalone",
    target_version: "6.16.2",
    images: {
      application: applicationImage,
      browser: browserImage,
      database: databaseImage,
    },
    acquisition_surface:
      "supported_api_v4_authenticated_private_file_readback_authenticated_server_rendered_ui_isolated_browser_workflow_and_automated_accessibility_scan",
    source_normalization: sourceNormalization,
    sandbox: {
      application_empty_before_write: true,
      attachments_private: true,
      browser_artifact_retention_disabled: true,
      browser_container_read_only: true,
      browser_network_internal_only: true,
      egress_blocked: true,
      hibp_lookup_disabled: true,
      mail_disabled: true,
      no_public_ingress: true,
      run_owned: true,
      scheduled_jobs_disabled: true,
      source_identity_collisions_absent: true,
    },
    identity_separation: {
      all_principals_distinct: true,
      allow_and_deny_distinct: true,
      permission_checks_enabled: true,
      reader_independent_from_writer: true,
      same_permission_query_and_object: true,
      writer_credential_excluded_from_business_readback: true,
    },
    disposition_counts: {
      represented: {
        attachments: 2,
        audit_events: 0,
        entities: 5,
        permissions: 0,
        relationships: 2,
      },
      target_generated: {
        acl_entity_roles: 2,
        acl_group_contacts: 4,
        acl_groups: 3,
        acl_roles: 2,
        acls: 2,
        case_activities: 2,
        case_contacts: 2,
        case_types: 1,
        custom_field_groups: 2,
        custom_fields: 7,
        helper_contacts: 1,
        principals: 4,
        relationship_types_created: 0,
        relationship_types_referenced: 1,
        roles: 4,
      },
      unmapped: {
        attachments: 0,
        audit_events: 2,
        entities: 2,
        permissions: 2,
        relationships: 0,
      },
    },
    files,
    bundle_sha256: sha256(Buffer.from(canonical(files), "utf8")),
    limitations: [
      "operator_asserted_execution_context",
      "bundle_is_unsigned_and_unauthenticated",
      "synthetic_fixture_only",
      "source_capture_is_not_a_vendor_native_export",
      "does_not_prove_operational_equivalence",
      "server_rendered_ui_does_not_prove_browser_interaction",
      "single_case_browser_workflow_only",
      "browser_workflow_observed_with_known_jquery_notify_runtime_errors",
      "browser_workflow_does_not_prove_accessibility",
      "automated_accessibility_scan_does_not_establish_wcag_conformance",
    ],
  };
}

async function prepareOutput(requestedPath) {
  const defaultName = `exitdrill-civicrm-target-roundtrip-${randomBytes(8).toString("hex")}`;
  const requestedOutputPath = resolve(requestedPath ?? join(tmpdir(), defaultName));
  if (requestedOutputPath === resolve("/") || requestedOutputPath === resolve(tmpdir())) {
    fail("output must be a fresh child directory, not a broad filesystem location");
  }
  const requestedOutputParent = dirname(requestedOutputPath);
  let outputParent;
  try {
    outputParent = await realpath(requestedOutputParent);
  } catch {
    fail("output parent must be an existing directory");
  }
  if (!(await lstat(outputParent)).isDirectory()) fail("output parent must be a directory");
  const outputPath = join(outputParent, basename(requestedOutputPath));
  const canonicalSourceRoot = await realpath(sourceNativeDir);
  if (pathIsWithin(outputPath, canonicalSourceRoot)) {
    fail("output must not be placed inside the fixed closed Directus source bundle");
  }
  if (await pathExists(outputPath)) fail("output directory already exists; supply a fresh path");
  let stageDir = null;
  try {
    stageDir = await mkdtemp(join(outputParent, `.${basename(outputPath)}.partial-`));
    await chmod(stageDir, 0o700);
    await mkdir(join(stageDir, "assets"), { mode: 0o700 });
    if (dirname(await realpath(stageDir)) !== outputParent) {
      fail("output parent changed while the staging directory was created");
    }
    return { outputParent, outputPath, stageDir };
  } catch (error) {
    if (stageDir !== null) await rm(stageDir, { recursive: true, force: true });
    throw error;
  }
}

async function executeLab(outputRequest) {
  const runSuffix = randomBytes(6).toString("hex");
  const projectName = `exitdrill-civicrm-${runSuffix}`;
  const credentials = {
    adminUsername: `exitdrill_admin_${runSuffix}`,
    adminPassword: secret(),
    databaseRootPassword: secret(),
    databasePassword: secret(),
  };
  const composeEnvironment = {
    CIVICRM_DB_NAME: "exitdrill",
    CIVICRM_DB_PASSWORD: credentials.databasePassword,
    CIVICRM_DB_ROOT_PASSWORD: credentials.databaseRootPassword,
    CIVICRM_DB_USER: "exitdrill",
  };
  const environmentBytes = Buffer.from(
    [
      `CIVICRM_DB_ROOT_PASSWORD=${composeEnvironment.CIVICRM_DB_ROOT_PASSWORD}`,
      `CIVICRM_DB_NAME=${composeEnvironment.CIVICRM_DB_NAME}`,
      `CIVICRM_DB_USER=${composeEnvironment.CIVICRM_DB_USER}`,
      `CIVICRM_DB_PASSWORD=${composeEnvironment.CIVICRM_DB_PASSWORD}`,
      "",
    ].join("\n"),
    "utf8",
  );
  const { outputParent, outputPath, stageDir } = await prepareOutput(outputRequest);
  let runtimeDir = null;
  let runtime = null;
  let composeStarted = false;
  let primaryError = null;
  let cleanupError = null;
  try {
    runtimeDir = await mkdtemp(join(tmpdir(), "exitdrill-civicrm-lab-"));
    await chmod(runtimeDir, 0o700);
    const fixture = await normalizeSourceFixture(join(runtimeDir, "source-normalized"));
    const environmentFile = join(runtimeDir, "compose.env");
    await writeFile(environmentFile, environmentBytes, { flag: "wx", mode: 0o600 });
    await chmod(environmentFile, 0o600);
    runtime = createLabRuntime(environmentFile, projectName, composeEnvironment);
    await validateCompose(runtime, composeEnvironment);
    composeStarted = true;
    await runtime.compose(["up", "-d", "--pull", "never"], {
      timeoutMs: 180_000,
      label: "isolated CiviCRM lab startup",
    });
    const targetConfig = await configureTarget(runtime, credentials);
    const principals = await provisionPrincipals(runtime, runSuffix);
    await assertApplicationEmptyBeforeWrite(runtime);
    await verifyNetworkFailure(runtime);
    const loaded = await loadBusinessSubset(runtime, fixture, targetConfig, principals);
    await configureContactAcl(runtime, principals, loaded);
    await verifyTargetCounts(runtime);
    const metadata = await captureReadback(runtime, fixture, principals, stageDir);
    const safety = await runtime.trusted("inspect_safety");
    if (
      safety.version !== "6.16.2" ||
      safety.hibp_disabled !== true ||
      safety.mail_disabled !== true ||
      safety.active_jobs !== 0
    ) {
      fail("a required CiviCRM safety control changed during the target roundtrip");
    }
    const manifest = buildManifest(metadata, fixture.sourceNormalization);
    await writeFile(join(stageDir, "capture-manifest.json"), jsonDocument(manifest), {
      flag: "wx",
      mode: 0o600,
    });
  } catch (error) {
    primaryError = error;
  } finally {
    if (runtime !== null) {
      try {
        await runtime.cleanupBrowser();
      } catch (error) {
        cleanupError ??= error;
      }
    }
    if (composeStarted) {
      try {
        await runtime.compose(["down", "--volumes", "--remove-orphans", "--timeout", "10"], {
          timeoutMs: 120_000,
          label: "run-owned CiviCRM lab cleanup",
          allowAfterInterruption: true,
        });
      } catch (error) {
        cleanupError = error;
      }
    }
    if (runtimeDir !== null) {
      try {
        await rm(runtimeDir, { recursive: true, force: true });
      } catch (error) {
        cleanupError ??= error;
      }
    }
  }

  if (primaryError || cleanupError || interruption) {
    await rm(stageDir, { recursive: true, force: true });
    if (cleanupError) {
      throw new Error(
        `lab did not complete cleanly: ${redact(cleanupError.message)}`,
        primaryError ? { cause: primaryError } : undefined,
      );
    }
    throw primaryError ?? interruption;
  }
  try {
    if (
      (await realpath(dirname(outputPath))) !== outputParent ||
      dirname(await realpath(stageDir)) !== outputParent
    ) {
      fail("output parent changed during the run; refusing to publish the capture");
    }
    if (await pathExists(outputPath)) {
      fail("output path appeared during the run; refusing to replace it");
    }
    await rename(stageDir, outputPath);
  } catch (error) {
    await rm(stageDir, { recursive: true, force: true });
    throw error;
  }
  return outputPath;
}

async function main() {
  const { help, outputPath } = parseArguments(process.argv.slice(2));
  if (help) {
    process.stdout.write(
      "Usage: node scripts/civicrm_target_roundtrip_lab.mjs [--output FRESH_DIRECTORY]\n",
    );
    return;
  }
  installSignalHandlers();
  const completedPath = await executeLab(outputPath);
  process.stdout.write(
    `${JSON.stringify({
      state: "captured",
      target_profile: targetProfile,
      output: completedPath,
    })}\n`,
  );
}

await main().catch((error) => {
  process.stderr.write(`CiviCRM target roundtrip failed: ${redact(error?.message ?? error)}\n`);
  process.exitCode = 1;
});
