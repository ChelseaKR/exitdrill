import { createHash } from "node:crypto";
import { lstat, mkdir, readFile, writeFile } from "node:fs/promises";

const baseUrl = "http://127.0.0.1:8055";
const captureDir = "/tmp/exitdrill-directus-api-capture";
const policyId = "33333333-3333-4333-8333-333333333333";
const firstFileId = "11111111-1111-4111-8111-111111111111";
const secondFileId = "22222222-2222-4222-8222-222222222222";

function localUrl(path) {
  if (typeof path !== "string" || !path.startsWith("/") || path.startsWith("//")) {
    throw new Error("Directus request path must be an absolute local path");
  }
  const target = new URL(path, `${baseUrl}/`);
  if (
    target.protocol !== "http:" ||
    target.hostname !== "127.0.0.1" ||
    target.port !== "8055" ||
    target.origin !== baseUrl
  ) {
    throw new Error("refusing a non-local Directus request");
  }
  return target;
}

async function requireFreshCaptureDirectory() {
  try {
    await lstat(captureDir);
  } catch (error) {
    if (error?.code === "ENOENT") return;
    throw error;
  }
  throw new Error("capture directory already exists; use a fresh sandbox path");
}

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

async function request(path, { method = "GET", body, token } = {}) {
  const headers = {};
  if (token) headers.authorization = `Bearer ${token}`;
  if (body !== undefined) headers["content-type"] = "application/json";
  const response = await fetch(localUrl(path), {
    method,
    headers,
    body: body === undefined ? undefined : JSON.stringify(body),
    redirect: "error",
  });
  const text = await response.text();
  if (!response.ok) throw new Error(`${method} ${path}: HTTP ${response.status}`);
  return text ? JSON.parse(text) : null;
}

async function requestBytes(path, token) {
  const response = await fetch(localUrl(path), {
    headers: { authorization: `Bearer ${token}` },
    redirect: "error",
  });
  const bytes = Buffer.from(await response.arrayBuffer());
  if (!response.ok) {
    throw new Error(`GET ${path}: HTTP ${response.status}`);
  }
  return bytes;
}

async function createCollection(token, collection, icon, note) {
  await request("/collections", {
    method: "POST",
    token,
    body: { collection, meta: { icon, note }, schema: { name: collection } },
  });
}

async function createField(token, collection, field, type, meta = {}, schema = {}) {
  await request(`/fields/${collection}`, {
    method: "POST",
    token,
    body: { field, type, meta, schema },
  });
}

async function createRelation(token, collection, field, relatedCollection) {
  await request("/relations", {
    method: "POST",
    token,
    body: {
      collection,
      field,
      related_collection: relatedCollection,
      meta: {
        junction_field: null,
        many_collection: collection,
        many_field: field,
        one_allowed_collections: null,
        one_collection: relatedCollection,
        one_collection_field: null,
        one_field: null,
        one_deselect_action: "nullify",
        sort_field: null,
      },
      schema: { on_update: "NO ACTION", on_delete: "NO ACTION" },
    },
  });
}

async function uploadFile(token, id, filename, content) {
  const form = new FormData();
  form.append("id", id);
  form.append("title", filename.replace(".txt", ""));
  form.append("file", new Blob([content], { type: "text/plain" }), filename);
  const response = await fetch(localUrl("/files"), {
    method: "POST",
    headers: { authorization: `Bearer ${token}` },
    body: form,
    redirect: "error",
  });
  await response.arrayBuffer();
  if (!response.ok) throw new Error(`POST /files: HTTP ${response.status}`);
}

await requireFreshCaptureDirectory();
const adminEmail = process.env.ADMIN_EMAIL;
const adminPassword = process.env.ADMIN_PASSWORD;
if (!adminEmail?.trim() || !adminPassword) {
  throw new Error("ADMIN_EMAIL and ADMIN_PASSWORD must be set");
}

const login = await request("/auth/login", {
  method: "POST",
  body: {
    email: adminEmail,
    password: adminPassword,
  },
});
const token = login.data.access_token;
if (typeof token !== "string" || !token) {
  throw new Error("local Directus login did not return an access token");
}

const collections = await request("/collections", { token });
if (collections.data.some((item) => !item.collection.startsWith("directus_"))) {
  throw new Error("sandbox is not fresh: it already contains a user collection");
}
const collisionChecks = [
  `/policies?filter[id][_eq]=${policyId}&fields=id&limit=1`,
  `/files?filter[id][_eq]=${firstFileId}&fields=id&limit=1`,
  `/files?filter[id][_eq]=${secondFileId}&fields=id&limit=1`,
];
for (const endpoint of collisionChecks) {
  const collision = await request(endpoint, { token });
  if (collision.data.length) {
    throw new Error("sandbox is not fresh: a fixed canary identity already exists");
  }
}
await mkdir(captureDir);
await mkdir(`${captureDir}/assets`);

await createCollection(
  token,
  "exitdrill_people",
  "people",
  "Invented people for the ExitDrill synthetic canary.",
);
await createCollection(
  token,
  "exitdrill_cases",
  "folder_shared",
  "Invented cases for the ExitDrill synthetic canary.",
);
await createCollection(
  token,
  "exitdrill_case_people",
  "link",
  "Invented case-person links for the ExitDrill synthetic canary.",
);

await createField(token, "exitdrill_people", "display_name", "string", {
  interface: "input",
  required: true,
});
await createField(token, "exitdrill_people", "active", "boolean", {
  interface: "boolean",
  required: true,
});
await createField(token, "exitdrill_cases", "status", "string", {
  interface: "select-dropdown",
  required: true,
});
await createField(token, "exitdrill_cases", "priority", "integer", {
  interface: "input",
  required: true,
});
await createField(
  token,
  "exitdrill_cases",
  "document",
  "uuid",
  { interface: "file", required: true, special: ["file"] },
  { foreign_key_table: "directus_files", foreign_key_column: "id", is_nullable: false },
);
await createField(
  token,
  "exitdrill_case_people",
  "case_id",
  "integer",
  { interface: "select-dropdown-m2o", required: true, special: ["m2o"] },
  { foreign_key_table: "exitdrill_cases", foreign_key_column: "id", is_nullable: false },
);
await createField(
  token,
  "exitdrill_case_people",
  "person_id",
  "integer",
  { interface: "select-dropdown-m2o", required: true, special: ["m2o"] },
  { foreign_key_table: "exitdrill_people", foreign_key_column: "id", is_nullable: false },
);
await createField(token, "exitdrill_case_people", "relation_type", "string", {
  interface: "input",
  required: true,
});
await createRelation(token, "exitdrill_cases", "document", "directus_files");
await createRelation(token, "exitdrill_case_people", "case_id", "exitdrill_cases");
await createRelation(token, "exitdrill_case_people", "person_id", "exitdrill_people");

await uploadFile(token, firstFileId, "synthetic-intake-a.txt", "Invented intake note alpha.\n");
await uploadFile(token, secondFileId, "synthetic-intake-b.txt", "Invented intake note bravo.\n");

for (const person of [
  { id: 1, display_name: "Synthetic Person Alpha", active: true },
  { id: 2, display_name: "Synthetic Person Bravo", active: true },
  { id: 3, display_name: "Synthetic Person Canary", active: false },
]) {
  await request("/items/exitdrill_people", { method: "POST", token, body: person });
}
for (const item of [
  { id: 1, status: "open", priority: 2, document: firstFileId },
  { id: 2, status: "open", priority: 3, document: secondFileId },
]) {
  await request("/items/exitdrill_cases", { method: "POST", token, body: item });
}
for (const link of [
  { id: 1, case_id: 1, person_id: 1, relation_type: "assigned_to" },
  { id: 2, case_id: 2, person_id: 2, relation_type: "assigned_to" },
]) {
  await request("/items/exitdrill_case_people", { method: "POST", token, body: link });
}

await request("/policies", {
  method: "POST",
  token,
  body: {
    id: policyId,
    name: "Synthetic Case Worker",
    icon: "shield",
    description: "Invented policy for the ExitDrill synthetic canary.",
    app_access: true,
    admin_access: false,
  },
});
for (const permission of [
  {
    policy: policyId,
    collection: "exitdrill_cases",
    action: "read",
    permissions: {},
    validation: null,
    presets: null,
    fields: ["id", "status", "priority", "document"],
  },
  {
    policy: policyId,
    collection: "exitdrill_people",
    action: "read",
    permissions: {},
    validation: null,
    presets: null,
    fields: ["id", "display_name", "active"],
  },
]) {
  await request("/permissions", { method: "POST", token, body: permission });
}

const captureRequests = [
  ["people.json", "/items/exitdrill_people?fields=id,display_name,active&sort=id&limit=-1"],
  ["cases.json", "/items/exitdrill_cases?fields=id,status,priority,document&sort=id&limit=-1"],
  [
    "case-people.json",
    "/items/exitdrill_case_people?fields=id,case_id,person_id,relation_type&sort=id&limit=-1",
  ],
  [
    "files.json",
    "/files?fields=id,filename_download,type,filesize&sort=id&limit=-1",
  ],
  [
    "policies.json",
    `/policies?filter[id][_eq]=${policyId}&fields=id,name,app_access,admin_access&sort=id&limit=-1`,
  ],
  [
    "permissions.json",
    `/permissions?filter[policy][_eq]=${policyId}&fields=id,policy,collection,action,permissions,validation,presets,fields&sort=collection,action&limit=-1`,
  ],
  [
    "activity.json",
    "/activity?filter[collection][_eq]=exitdrill_cases&filter[action][_eq]=create&fields=id,action,collection,item,timestamp&sort=id&limit=-1",
  ],
  ["schema.json", "/schema/snapshot"],
];

const files = [];
for (const [path, endpoint] of captureRequests) {
  const bytes = await requestBytes(endpoint, token);
  await writeFile(`${captureDir}/${path}`, bytes, { flag: "wx" });
  files.push({ path, bytes: bytes.length, sha256: sha256(bytes) });
}
for (const id of [firstFileId, secondFileId]) {
  const path = `assets/${id}.txt`;
  const bytes = await requestBytes(`/assets/${id}`, token);
  await writeFile(`${captureDir}/${path}`, bytes, { flag: "wx" });
  files.push({ path, bytes: bytes.length, sha256: sha256(bytes) });
}
files.sort((left, right) => left.path.localeCompare(right.path));

const schema = JSON.parse(await readFile(`${captureDir}/schema.json`, "utf8"));
if (schema.data.directus !== "11.17.4" || schema.data.vendor !== "sqlite") {
  throw new Error("capture source must be Directus 11.17.4 backed by SQLite");
}
const expectedRelations = [
  ["exitdrill_case_people", "case_id", "exitdrill_cases"],
  ["exitdrill_case_people", "person_id", "exitdrill_people"],
  ["exitdrill_cases", "document", "directus_files"],
];
for (const [collection, field, relatedCollection] of expectedRelations) {
  const relation = schema.data.relations.find(
    (item) =>
      item.collection === collection &&
      item.field === field &&
      item.related_collection === relatedCollection,
  );
  if (
    !relation ||
    relation.meta?.many_collection !== collection ||
    relation.meta?.many_field !== field ||
    relation.meta?.one_collection !== relatedCollection ||
    relation.meta?.one_deselect_action !== "nullify" ||
    relation.schema?.table !== collection ||
    relation.schema?.column !== field ||
    relation.schema?.foreign_key_table !== relatedCollection ||
    relation.schema?.foreign_key_column !== "id" ||
    relation.schema?.on_update !== "NO ACTION" ||
    relation.schema?.on_delete !== "NO ACTION"
  ) {
    throw new Error(`captured schema is missing exact relation ${collection}.${field}`);
  }
}
const bundleSha256 = sha256(Buffer.from(canonical(files), "utf8"));
const manifest = {
  schema_version: "exitdrill/directus-api-capture-bundle/v0.1",
  adapter_profile: "directus-11.17.4-civic-case/v0.1",
  acquisition_surface: "documented_first_party_rest_api",
  data_mode: "synthetic_only",
  drill_id: "directus-civic-case-exit-001",
  source_system: "Directus 11.17.4 synthetic civic-case sandbox",
  source_version: schema.data.directus,
  exported_at: new Date().toISOString(),
  isolated_sandbox: true,
  production_data_allowed: false,
  files,
  bundle_sha256: bundleSha256,
  limitations: [
    "operator_asserted_acquisition_context",
    "bundle_is_unsigned_and_unauthenticated",
    "does_not_prove_export_completeness",
    "does_not_prove_operational_equivalence",
  ],
};
const manifestBytes = Buffer.from(`${canonical(manifest)}\n`, "utf8");
await writeFile(`${captureDir}/capture-manifest.json`, manifestBytes, { flag: "wx" });
console.log(
  JSON.stringify({
    status: "synthetic_api_capture_bundle_captured",
    source_version: schema.data.directus,
    files: files.length,
    bundle_sha256: bundleSha256,
  }),
);
