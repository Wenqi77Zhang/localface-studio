/** Validate the static showcase boundary without dependencies or network calls. */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const directory = resolve(process.argv[2] ?? resolve(repository, "showcase"));
const files = ["app.js", "favicon.svg", "index.html", "styles.css"];
const entries = readdirSync(directory).filter((file) => file !== "README.md").sort();
assert.deepEqual(entries, files, "Only reviewed static assets may be published");
const sources = files.map((file) => readFileSync(resolve(directory, file), "utf8"));
const html = sources[2];
const javascript = sources[0];
const combined = sources.join("\n");
const bytes = files.reduce((sum, file) => sum + statSync(resolve(directory, file)).size, 0);
assert.ok(bytes < 150_000, "Keep the buildless page lightweight");
assert.ok(!/<(?:form|input|iframe|object|embed|video|audio)\b/i.test(html), "No uploads, forms or private media");
assert.ok(!/\b(?:fetch|XMLHttpRequest|WebSocket|sendBeacon|localStorage|sessionStorage)\b/.test(javascript), "No data requests or visitor storage");
assert.ok(!/\bon\w+\s*=|javascript:/i.test(html), "No inline event code");
assert.ok(!/@import|\burl\s*\(/i.test(sources[3]), "No hidden CSS resource requests");
assert.ok(!/<(?:script|foreignObject|image)\b|\b(?:href|on\w+)\s*=/i.test(sources[1]), "Keep the icon self-contained");
const scripts = [...html.matchAll(/<script\b([^>]*)>([\s\S]*?)<\/script>/g)];
assert.equal(scripts.length, 1, "Exactly one reviewed browser script");
assert.ok(scripts[0][1].includes('src="./app.js"') && !scripts[0][2].trim(), "No inline or external scripts");
assert.ok(!/[A-Z]:[\\/]Users[\\/]|\b(?:ghp|github_pat)_[A-Za-z0-9_]+|BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY/i.test(combined), "No local paths or credentials");
assert.ok(html.includes("connect-src 'none'") && html.includes("form-action 'none'"), "CSP must block API and form submission");
assert.ok(html.includes('lang="zh-CN"') && html.includes('name="viewport"'), "Language and mobile metadata required");
assert.equal((html.match(/<h1\b/g) ?? []).length, 1, "One document title");

const ids = [...html.matchAll(/\bid="([^"]+)"/g)].map((match) => match[1]);
assert.equal(new Set(ids).size, ids.length, "IDs must be unique");
let links = 0;
for (const [, href] of html.matchAll(/href="([^"]+)"/g)) {
  links++;
  if (href.startsWith("#")) {
    assert.ok(ids.includes(href.slice(1)), `Missing anchor: ${href}`);
  } else if (href.startsWith("./")) {
    assert.ok(files.includes(href.slice(2)), `Unexpected asset: ${href}`);
  } else {
    const url = new URL(href);
    assert.equal(url.protocol, "https:");
    assert.ok(["github.com", "localface-studio.stonyring261.chatgpt.site"].includes(url.hostname), `Unexpected external destination: ${url.hostname}`);
    const doc = url.pathname.match(/^\/Wenqi77Zhang\/localface-studio\/blob\/(?:main|[a-f0-9]{40})\/(.+)$/);
    if (doc) assert.ok(statSync(resolve(repository, doc[1])).isFile(), `Missing linked document: ${doc[1]}`);
  }
}
for (const [, source] of html.matchAll(/\bsrc="([^"]+)"/g)) {
  assert.ok(source.startsWith("./") && files.includes(source.slice(2)), `Unexpected resource: ${source}`);
}
for (const [, target] of html.matchAll(/aria-(?:controls|labelledby)="([^"]+)"/g)) {
  for (const id of target.split(" ")) assert.ok(ids.includes(id), `Missing accessible reference: ${id}`);
}
assert.equal((html.match(/role="tab"/g) ?? []).length, 5);
assert.equal((html.match(/role="tabpanel"/g) ?? []).length, 5);
assert.equal((html.match(/<details>/g) ?? []).length, 5);
assert.ok(html.includes("非实拍") && html.includes("非换脸结果") && html.includes("不提供在线换脸"));
assert.ok(html.includes("不是准确率") && html.includes("不是实时状态"));
console.log(JSON.stringify({ status: "ok", files: files.length, bytes, links, boundary: "static-showcase-only" }));
