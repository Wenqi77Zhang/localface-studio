/** Validate the static showcase boundary without dependencies or network calls. */
import assert from "node:assert/strict";
import { readFileSync, readdirSync, statSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const repository = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const directory = resolve(process.argv[2] ?? resolve(repository, "showcase"));
const files = ["favicon.svg", "index.html", "styles.css"];
const entries = readdirSync(directory)
  .filter((file) => file !== "README.md")
  .sort();
assert.deepEqual(
  entries,
  files,
  "Only reviewed static assets may be published",
);
const sources = files.map((file) =>
  readFileSync(resolve(directory, file), "utf8"),
);
const html = sources[1];
const combined = sources.join("\n");
const bytes = files.reduce(
  (sum, file) => sum + statSync(resolve(directory, file)).size,
  0,
);
assert.ok(bytes < 50_000, "Keep the concise case study lightweight");
assert.ok(
  !/<(?:form|input|iframe|object|embed|video|audio)\b/i.test(html),
  "No uploads, forms or private media",
);
assert.ok(!/\bon\w+\s*=|javascript:/i.test(html), "No inline event code");
assert.ok(
  !/@import|\burl\s*\(/i.test(sources[2]),
  "No hidden CSS resource requests",
);
assert.ok(
  !/<(?:script|foreignObject|image)\b|\b(?:href|on\w+)\s*=/i.test(sources[0]),
  "Keep the icon self-contained",
);
assert.ok(
  !/<script\b/i.test(html),
  "No browser script is needed for this case study",
);
assert.ok(
  !/[A-Z]:[\\/]Users[\\/]|\b(?:ghp|github_pat)_[A-Za-z0-9_]+|BEGIN (?:RSA |OPENSSH |EC )?PRIVATE KEY/i.test(
    combined,
  ),
  "No local paths or credentials",
);
assert.ok(
  html.includes("script-src 'none'") &&
    html.includes("connect-src 'none'") &&
    html.includes("form-action 'none'"),
  "CSP must block scripts, API and form submission",
);
assert.ok(
  html.includes('lang="zh-CN"') && html.includes('name="viewport"'),
  "Language and mobile metadata required",
);
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
    assert.ok(
      ["github.com", "localface-studio.stonyring261.chatgpt.site"].includes(
        url.hostname,
      ),
      `Unexpected external destination: ${url.hostname}`,
    );
    const doc = url.pathname.match(
      /^\/Wenqi77Zhang\/localface-studio\/blob\/(?:main|[a-f0-9]{40})\/(.+)$/,
    );
    if (doc)
      assert.ok(
        statSync(resolve(repository, doc[1])).isFile(),
        `Missing linked document: ${doc[1]}`,
      );
  }
}
for (const [, source] of html.matchAll(/\bsrc="([^"]+)"/g)) {
  assert.ok(
    source.startsWith("./") && files.includes(source.slice(2)),
    `Unexpected resource: ${source}`,
  );
}
for (const [, target] of html.matchAll(
  /aria-(?:controls|labelledby)="([^"]+)"/g,
)) {
  for (const id of target.split(" "))
    assert.ok(ids.includes(id), `Missing accessible reference: ${id}`);
}
const bodyText = html
  .split(/<body\b[^>]*>/)[1]
  .replace(/<[^>]+>/g, "")
  .replace(/\s+/g, " ");
assert.ok(
  bodyText.includes("不提供在线换脸") &&
    bodyText.includes("AI 辅助开发") &&
    bodyText.includes("未自行训练"),
  "Disclose the online-service and contribution boundaries",
);
assert.ok(
  bodyText.includes("不是准确率") &&
    bodyText.includes("同一来源身份") &&
    bodyText.includes("134d452"),
  "Keep benchmark limits and dated engineering evidence",
);
const hanCharacters = (bodyText.match(/\p{Script=Han}/gu) ?? []).length;
assert.ok(
  hanCharacters < 1200,
  "Move detailed engineering records to linked docs, not the showcase",
);
console.log(
  JSON.stringify({
    status: "ok",
    files: files.length,
    bytes,
    links,
    hanCharacters,
    boundary: "static-case-study-only",
  }),
);
