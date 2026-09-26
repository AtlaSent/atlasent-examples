#!/usr/bin/env node
// Fail if an example passes an action type that the API will reject.
//
// v1-evaluate and both published SDKs require dot-notation action types
// (^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$). "reports:generate" or a bare
// "send_message" is a 400 invalid_action_type at the server and a thrown
// error in the SDK before any request is sent — so an example using one
// fails the moment a reader runs it. CI only py_compile'd several of them,
// which is how the quickstarts shipped broken.
//
// Usage: node scripts/check-action-names.mjs [--self-test]
import { execFileSync } from "node:child_process";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { relative } from "node:path";

const ACTION_TYPE_RE = /^[a-z][a-z0-9_]*(\.[a-z][a-z0-9_]*)+$/;
// action / action_type / actionType / "action" as a key or keyword arg,
// followed by a string literal. Multiline-tolerant (whitespace incl. newlines).
const SITE_RE =
  /(?:\baction(?:_type|Type)?|["']action(?:_type)?["'])\s*[:=]\s*(["'`])([^"'`\n]*)\1/g;
// Python argparse `action=` values are not AtlaSent action types.
const NOT_ACTION_TYPES = new Set(["store_true", "store_false", "store", "append", "count", "version", "help"]);
const EXTENSIONS = /\.(ts|tsx|js|mjs|cjs|py|go|json)$/;

export function findings(text) {
  const out = [];
  for (const m of text.matchAll(SITE_RE)) {
    const value = m[2];
    if (value === "" || NOT_ACTION_TYPES.has(value)) continue;
    if (/[${}<>]/.test(value)) continue; // template / placeholder, not a literal
    if (!ACTION_TYPE_RE.test(value)) {
      const line = text.slice(0, m.index).split("\n").length;
      out.push({ line, value });
    }
  }
  return out;
}

function selfTest() {
  const bad = [
    'protect({ agent: "a", action: "reports:generate" })',
    'protect(agent="a", action="lims:write")',
    "{ action: 'send_message' }",
    '{"action_type": "documents:read"}',
    'evaluate({\n  actionType:\n    "ui:view-dashboard" })',
  ];
  const good = [
    'protect({ agent: "a", action: "report.generate" })',
    'parser.add_argument("--json", action="store_true")',
    '{"action_type": "production.deploy"}',
    "{ action: `${prefix}.run` }",
  ];
  let ok = true;
  for (const s of bad) if (findings(s).length !== 1) { console.error(`self-test: missed bad case: ${s}`); ok = false; }
  for (const s of good) if (findings(s).length !== 0) { console.error(`self-test: flagged good case: ${s}`); ok = false; }
  if (!ok) process.exit(1);
  console.log(`self-test: ${bad.length} bad and ${good.length} good cases classified correctly`);
}

if (process.argv.includes("--self-test")) {
  selfTest();
} else {
  // This file's own self-test fixtures are deliberately bad; skip it.
  const self = relative(process.cwd(), fileURLToPath(import.meta.url));
  const files = execFileSync("git", ["ls-files"], { encoding: "utf8" })
    .split("\n")
    .filter((f) => f !== self && EXTENSIONS.test(f) && !f.includes("node_modules/") && !f.endsWith("package.json") && !f.endsWith("package-lock.json"));
  if (files.length === 0) {
    console.error("no files scanned; refusing to report success on an empty scan set");
    process.exit(2);
  }
  let bad = 0;
  for (const f of files) {
    for (const { line, value } of findings(readFileSync(f, "utf8"))) {
      console.error(`${f}:${line}: action type "${value}" is not dot-notation (e.g. "data.export")`);
      bad++;
    }
  }
  if (bad) {
    console.error(`\n${bad} action type(s) the API would reject with 400 invalid_action_type.`);
    process.exit(1);
  }
  console.log(`OK: ${files.length} files scanned, every literal action type is dot-notation.`);
}
