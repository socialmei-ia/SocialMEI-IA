const { test } = require("node:test"),
  assert = require("node:assert/strict");
const model = require("../frontend/scripts/content-drafts.js");
const input = {
  format: "feed",
  title: "Minha postagem",
  caption: "Texto",
  cta: "Fale comigo",
  hashtags: "#mei",
};
function fixture() {
  let scope = "a",
    counter = 0;
  const map = new Map();
  const repo = model.repository(
    { getItem: (k) => map.get(k) || null, setItem: (k, v) => map.set(k, v) },
    () => scope,
    { id: () => `id-${++counter}`, now: () => "2026-10-18T12:00:00Z" },
  );
  return { repo, map, switch: (v) => (scope = v) };
}
test("draft CRUD, duplicate and update preserve scoped local metadata without fake publication", () => {
  const { repo } = fixture();
  const saved = repo.save(input, "a");
  assert.equal(repo.read().items.length, 1);
  repo.save({ ...saved, title: "Editado" }, "a");
  assert.equal(repo.read().items[0].title, "Editado");
  const copy = repo.duplicate(saved.id, "a");
  assert.notEqual(copy.id, saved.id);
  assert.equal(repo.read().items.length, 2);
  repo.remove(saved.id, "a");
  assert.equal(repo.read().items.length, 1);
  assert.equal("published" in copy, false);
  assert.equal(model.caption(input), "Texto\n\nFale comigo\n\n#mei");
});
test("identities and workspace changes cannot load or overwrite other drafts", () => {
  const f = fixture();
  const saved = f.repo.save(input, "a");
  f.switch("b");
  assert.deepEqual(f.repo.read().items, []);
  assert.throws(() => f.repo.save(saved, "a"), /sessão/);
  assert.throws(() => f.repo.remove(saved.id, "b"), /encontrado/);
  f.switch(null);
  assert.equal(f.repo.read().status, "unavailable");
  f.switch("a");
  assert.equal(f.repo.read().items[0].title, input.title);
});
test("corrupt scope, unsupported data and quota do not report a save or overwrite content", () => {
  const f = fixture();
  f.repo.save(input, "a");
  const key = [...f.map.keys()][0],
    old = f.map.get(key);
  f.map.set(key, JSON.stringify({ version: 1, scope: "b", items: [] }));
  assert.equal(f.repo.read().status, "error");
  assert.throws(() => f.repo.save(input, "a"));
  assert.notEqual(f.map.get(key), old);
  const failed = model.repository(
    {
      getItem: () => null,
      setItem: () => {
        throw Error("quota");
      },
    },
    () => "a",
  );
  assert.throws(() => failed.save(input, "a"), /Não foi possível salvar/);
});
test("content limits, formats and media metadata are enforced without persisting blobs or URLs", () => {
  assert.throws(() => model.draft({ ...input, format: "unknown" }));
  assert.throws(() => model.draft({ ...input, title: " " }));
  assert.throws(() => model.draft({ ...input, caption: "a".repeat(2201) }));
  assert.throws(() =>
    model.draft({ ...input, media: { name: "video", size: 100, type: "video/mp4" } }),
  );
  const d = model.draft({
    ...input,
    url: "https://untrusted.example",
    media: { name: "p.png", type: "image/png", size: 100, url: "blob:secret" },
  });
  assert.equal("url" in d, false);
  assert.equal("url" in d.media, false);
});
test("planned dates stay local metadata and never imply publication", () => {
  const f = fixture();
  const date = "2026-11-03T13:30:00.000Z";
  const saved = f.repo.save({ ...input, scheduledFor: date }, "a");
  assert.equal(f.repo.read().items[0].scheduledFor, date);
  assert.equal("published" in saved, false);
  assert.equal("status" in saved, false);
  assert.throws(() => f.repo.save({ ...input, scheduledFor: "tomorrow" }, "a"), /data e a hora/);
  assert.throws(
    () => f.repo.save({ ...input, scheduledFor: { url: "https://untrusted.example" } }, "a"),
    /data e a hora/,
  );
  assert.equal(f.repo.read().items.length, 1);
  f.repo.save({ ...saved, scheduledFor: null }, "a");
  assert.equal(f.repo.read().items[0].scheduledFor, null);
  assert.equal(model.draft(input).scheduledFor, null);
});
test("local media requires compatible MIME, size and header before preview", async () => {
  const file = (type, bytes, size = bytes.length) => ({
    name: "file",
    type,
    size,
    slice: () => ({ arrayBuffer: async () => new Uint8Array(bytes).buffer }),
  });
  await model.validateMedia(file("image/png", [137, 80, 78, 71, 13, 10, 26, 10]), "story");
  await assert.rejects(model.validateMedia(file("image/png", [1, 2, 3]), "feed"), /conteúdo/);
  await assert.rejects(model.validateMedia(file("image/svg+xml", [1, 2, 3]), "story"));
  await assert.rejects(
    model.validateMedia(file("image/png", [137, 80, 78, 71], 11 * 1024 * 1024), "feed"),
    /10 MB/,
  );
  await assert.rejects(model.validateMedia(file("image/png", [137, 80, 78, 71]), "reel"), /vídeo/);
});
