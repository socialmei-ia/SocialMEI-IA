const test = require("node:test");
const assert = require("node:assert/strict");
const publisher = require("../frontend/scripts/instagram-publisher.js");

const origin = "https://socialmei.54-94-213-7.sslip.io";

test("o piloto não é aberto sem ativação explícita", () => {
  assert.equal(
    publisher.inspect({ mode: "disabled", formPath: "/form/instagram-post" }, origin).available,
    false,
  );
  assert.equal(publisher.inspect(undefined, origin).available, false);
});

test("o formulário autorizado usa somente o mesmo origin HTTPS", () => {
  assert.deepEqual(
    publisher.inspect({ mode: "external-pilot", formPath: "/form/instagram-post" }, origin),
    { available: true, href: origin + "/form/instagram-post" },
  );
  for (const formPath of [
    "//malicious.example/form/instagram-post",
    "https://malicious.example/form/instagram-post",
    "/webhook/instagram-post",
    "/form/../../admin",
    "/form/instagram-post?token=secret",
    "/form/instagram-post#secret",
    "/form/instagram post",
  ]) {
    assert.equal(
      publisher.inspect({ mode: "external-pilot", formPath }, origin).available,
      false,
      formPath,
    );
  }
  assert.equal(
    publisher.inspect(
      { mode: "external-pilot", formPath: "/form/instagram-post" },
      "http://localhost:5500",
    ).available,
    false,
  );
});

test("os formatos dão instruções específicas sem prometer publicação", () => {
  assert.match(publisher.guide("feed").guide, /carrossel/);
  assert.match(publisher.guide("story").guide, /um arquivo/);
  assert.match(publisher.guide("reel").guide, /um arquivo/);
  assert.equal(publisher.guide("desconhecido").label, "Feed");
});
