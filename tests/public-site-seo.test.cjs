const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");

const html = fs.readFileSync("frontend/sobre.html", "utf8");
const app = fs.readFileSync("frontend/socialmei-app.html", "utf8");
const metrics = fs.readFileSync("frontend/scripts/site-metrics.js", "utf8");
const gateway = fs.readFileSync("deploy/team/Caddyfile", "utf8");
const robots = fs.readFileSync("frontend/robots.txt", "utf8");
const siteMap = fs.readFileSync("frontend/sitemap.xml", "utf8");
const llms = fs.readFileSync("frontend/llms.txt", "utf8");
const host = "https://socialmei-ia.54-94-213-7.sslip.io";

function headMeta(name, attr = "name") {
  const escaped = name.replace(/[.*+?^$()|[\]{}]/g, "\\$&");
  return new RegExp('<meta\\s+' + attr + '="' + escaped + '"[^>]*>', "i").test(html);
}

test("Search metadata identifies only the public page, with working OG and favicon", () => {
  assert.match(html, /<html lang="pt-BR">/);
  for (const n of ["description", "robots", "twitter:card", "twitter:title", "twitter:description", "twitter:image"]) {
    assert(headMeta(n), "missing " + n);
  }
  for (const n of ["og:title", "og:description", "og:type", "og:url", "og:image", "og:locale"]) {
    assert(headMeta(n, "property"), "missing " + n);
  }
  assert(html.includes('rel="canonical" href="' + host + '/sobre.html"'));
  assert(html.includes(host + "/assets/socialmei-og.png"));
  assert(fs.existsSync("frontend/assets/socialmei-og.png"), "social preview PNG not included");
  assert(fs.existsSync("frontend/assets/socialmei-favicon.svg"), "favicon absent");
  assert(app.includes('href="assets/socialmei-favicon.svg"'));
  assert(app.includes('<meta name="robots" content="noindex,nofollow">'));
  assert(!app.includes("googletagmanager.com") && !app.includes("clarity.ms/tag/"));
});

test("JSON-LD claims only verified site/app identity (no fake prices or ratings)", () => {
  const raw = html.match(/<script type="application\/ld\+json">([\s\S]*?)<\/script>/);
  assert(raw, "JSON-LD missing");
  const data = JSON.parse(raw[1]);
  assert.equal(data["@context"], "https://schema.org");
  assert.deepEqual(data["@graph"].map((x) => x["@type"]), ["WebSite", "Organization", "WebApplication"]);
  assert(data["@graph"].every((x) => x.url.startsWith(host)));
  assert(!raw[1].includes("aggregateRating"));
  assert(!raw[1].includes('"offers"'));
  assert(!raw[1].includes("priceCurrency"));
});

test("robots and sitemap only reveal public introduction; Caddy serves exact files", () => {
  assert.match(robots, /Disallow: \/api\//);
  assert.match(robots, /Disallow: \/webhooks\//);
  assert.match(robots, /Disallow: \/frontend\//);
  assert.match(robots, new RegExp(host.replaceAll(".", "\\.") + "/sitemap\\.xml"));
  assert.match(siteMap, /<urlset /);
  assert(siteMap.includes("<loc>" + host + "/sobre.html</loc>"));
  assert(!siteMap.includes("<loc>" + host + "/api/"));
  assert.match(llms, /ainda em implantação ou homologação/i);
  assert.match(gateway, /@public_discovery path \/sobre\.html \/robots\.txt \/sitemap\.xml \/llms\.txt/);
  assert.match(gateway, /handle @public_discovery\s*\{[^}]*file_server/s);
  assert(!/handle_path\s+\/api\/v1/.test(gateway), "API gateway rules must not be rewritten");
});

function simulate(config, pref = null, pathname = "/sobre.html") {
  const urls = [];
  const listeners = {};
  const storage = new Map(pref === null ? [] : [["socialmei-public-metrics-consent-v1", pref]]);
  let reloaded = false;
  const nodes = Object.fromEntries(["metrics-consent", "metrics-accept", "metrics-decline", "privacy-preferences"]
    .map((id) => [id, {
      hidden: true, title: "", dataset: {},
      addEventListener: (name, handler) => { listeners[id + ":" + name] = handler; },
      setAttribute() {}, focus() {},
    }]));
  const window = {};
  const ctx = {
    document: {
      body: { dataset: {} },
      head: { appendChild: (node) => urls.push(node.src) },
      createElement: () => ({ dataset: {} }),
      getElementById: (id) => nodes[id],
      cookie: "",
    },
    location: { pathname, reload: () => { reloaded = true; } },
    localStorage: {
      getItem: (k) => storage.get(k) || null,
      setItem: (k, v) => storage.set(k, v),
    },
    SOCIALMEI_CONFIG: { siteMetrics: config },
    window, Date, encodeURIComponent,
  };
  vm.runInNewContext(metrics, ctx, { timeout: 1000 });
  return {
    urls, nodes, storage, listeners, window,
    reloaded: () => reloaded,
    click: (id) => { assert(listeners[id + ":click"]); listeners[id + ":click"](); },
  };
}

test("analytics is disabled by default, rejects invalid IDs, never loads on dashboard", () => {
  const disabled = simulate({ enabled: false, ga4MeasurementId: "G-ABC12345", clarityProjectId: "abcdefgh" });
  disabled.click("privacy-preferences");
  assert.equal(disabled.urls.length, 0);
  assert.equal(disabled.nodes["metrics-consent"].hidden, true);
  const invalid = simulate({ enabled: true, ga4MeasurementId: "fake", clarityProjectId: "<script>" });
  invalid.click("metrics-accept");
  assert.equal(invalid.urls.length, 0);
  const privateSite = simulate({ enabled: true, ga4MeasurementId: "G-ABC12345", clarityProjectId: "abcdefgh" }, "accepted", "/");
  assert.equal(privateSite.urls.length, 0);
});

test("only explicit opt-in injects GA4/Clarity on public page; decline prevents loading", () => {
  const config = { enabled: true, ga4MeasurementId: "G-ABC12345", clarityProjectId: "abcdefgh" };
  const first = simulate(config);
  assert.equal(first.urls.length, 0);
  assert.equal(first.nodes["metrics-consent"].hidden, false);
  first.click("metrics-decline");
  assert.equal(first.urls.length, 0);
  assert.equal(first.storage.get("socialmei-public-metrics-consent-v1"), "declined");
  assert.equal(first.reloaded(), false);

  const accept = simulate(config);
  accept.click("metrics-accept");
  assert.equal(accept.urls.length, 2);
  assert(accept.urls.some((u) => u === "https://www.googletagmanager.com/gtag/js?id=G-ABC12345"));
  assert(accept.urls.some((u) => u === "https://www.clarity.ms/tag/abcdefgh"));
  assert.equal(accept.window.dataLayer[0][0], "consent");
  assert.equal(accept.window.dataLayer[0][2].analytics_storage, "denied");
  assert.equal(accept.window.dataLayer[1][2].analytics_storage, "granted");
  assert.equal(accept.storage.get("socialmei-public-metrics-consent-v1"), "accepted");
  accept.click("privacy-preferences");
  accept.click("metrics-decline");
  assert.equal(accept.reloaded(), true);
  const refused = simulate(config, "declined");
  assert.equal(refused.urls.length, 0);
});
