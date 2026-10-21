const { test } = require("node:test");
const assert = require("node:assert/strict");
const model = require("../frontend/scripts/business-profile.js");
const { create, defaults } = require("../frontend/scripts/profile-sync.js");
const profile = (name) =>
  model.normalize({
    businessName: name,
    segment: "barber",
    offers: ["services"],
    services: ["Barba"],
    modules: ["services"],
    completed: true,
  });
const deferred = () => {
  let resolve, reject;
  const promise = new Promise((r, e) => {
    resolve = r;
    reject = e;
  });
  return { promise, resolve, reject };
};
function fixture(remote = true) {
  const data = new Map(),
    writes = [],
    applied = [];
  let id = "account:1:workspace:2";
  const storage = { getItem: (k) => data.get(k) ?? null, setItem: (k, v) => data.set(k, v) };
  const local = model.repository(storage, () => id);
  const auth = {
    remote,
    current: { papel: "owner" },
    request: async (path, method = "GET", value) => {
      writes.push({ path, method, value });
      return path === "/workspace-profile"
        ? { schema_version: 1, revision: 0, profile: null }
        : { schema_version: 1, revision: 0, preferences: defaults() };
    },
  };
  const service = create({
    auth,
    local,
    storage,
    normalize: model.normalize,
    applyPreferences: (p) => applied.push(p),
  });
  return {
    service,
    auth,
    local,
    data,
    storage,
    writes,
    applied,
    setScope: (value) => (id = value),
  };
}
test("local profile stays synchronous and never calls account endpoints", () => {
  const f = fixture(false);
  const p = profile("Local");
  assert.equal(f.service.repository().save(p), true);
  assert.deepEqual(f.service.repository().read().profile, p);
  assert.deepEqual(f.writes, []);
});
test("loading authenticated settings never imports or replaces a legacy local profile", async () => {
  const f = fixture();
  f.local.save(profile("Antigo"));
  f.data.set("socialmei-active-theme", "dark");
  f.data.set("socialmei-app-data-v2", JSON.stringify({ prefs: { notificacoes: false } }));
  const before = new Map(f.data);
  await f.service.refresh();
  assert.equal(f.service.repository().read().profile, null);
  assert.equal(f.service.legacyProfile().businessName, "Antigo");
  for (const [k, v] of before) assert.equal(f.data.get(k), v);
  assert(f.writes.every((w) => w.method === "GET"));
  assert.equal(f.service.legacyPreferences().theme, "dark");
  assert.equal(f.service.legacyPreferences().notificationsEnabled, false);
  assert.equal(f.applied[0].theme, "auto");
});
test("authenticated profile save uses explicit revision and never writes local fallback", async () => {
  const f = fixture();
  await f.service.refresh();
  f.auth.request = async (path, method, value) => {
    f.writes.push({ path, method, value });
    return { schema_version: 1, revision: 1, profile: profile("Oficial") };
  };
  assert.equal(await f.service.repository().save(profile("Proposto"), f.local.scope(), 0), true);
  assert.equal(f.writes.at(-1).value.expected_revision, 0);
  assert.equal(f.service.repository().read().profile.businessName, "Oficial");
  assert.equal(f.local.read().profile, null);
});
test("offline preferences retain proposed values and retry the same revision", async () => {
  const f = fixture();
  await f.service.refresh();
  f.auth.request = async () => {
    throw Error("offline");
  };
  await assert.rejects(f.service.updatePreferences({ theme: "dark" }), /offline/);
  assert.equal(f.service.state().pending.theme, "dark");
  assert.equal(f.service.state().preferences.theme, "auto");
  f.auth.request = async (path, method, value) => {
    assert.equal(value.expected_revision, 0);
    return { schema_version: 1, revision: 1, preferences: value.preferences };
  };
  await f.service.retryPreferences();
  assert.equal(f.service.state().preferences.theme, "dark");
  assert.equal(f.service.state().pending, null);
});
test("conflicts keep the proposal and cannot silently acquire a fresh revision", async () => {
  const f = fixture();
  await f.service.refresh();
  let sent;
  f.auth.request = async (path, method, value) => {
    sent = value;
    throw Object.assign(Error("Conflito"), { status: 409 });
  };
  await assert.rejects(f.service.updatePreferences({ notificationsEnabled: false }), {
    status: 409,
  });
  assert.equal(f.service.state().preferencesState, "conflict");
  assert.equal(f.service.state().pending.notificationsEnabled, false);
  await assert.rejects(f.service.retryPreferences(), { status: 409 });
  assert.equal(sent.expected_revision, 0);
});
test("late loads from another workspace cannot populate the current presentation", async () => {
  const f = fixture();
  const gate = deferred();
  f.auth.request = () => gate.promise;
  const loading = f.service.refresh("profile");
  f.setScope("account:1:workspace:3");
  gate.resolve({ schema_version: 1, revision: 9, profile: profile("Negócio anterior") });
  await loading;
  assert.equal(f.service.repository().read().profile, null);
  assert.equal(f.service.state().profileRevision, null);
});
test("an old GET cannot overwrite a subsequent confirmed save", async () => {
  const f = fixture();
  await f.service.refresh();
  const gate = deferred();
  f.auth.request = (path, method = "GET", value) =>
    method === "GET"
      ? gate.promise
      : Promise.resolve({ schema_version: 1, revision: 1, profile: value.profile });
  const loading = f.service.refresh("profile");
  await f.service.repository().save(profile("Novo"), f.local.scope(), 0);
  gate.resolve({ schema_version: 1, revision: 0, profile: null });
  await loading;
  assert.equal(f.service.repository().read().profile.businessName, "Novo");
});
test("member and viewer cannot save the shared profile", async () => {
  for (const role of ["member", "viewer"]) {
    const f = fixture();
    await f.service.refresh();
    const count = f.writes.length;
    f.auth.current.papel = role;
    await assert.rejects(
      f.service.repository().save(profile("Novo"), f.local.scope(), 0),
      /responsável/,
    );
    assert.equal(f.writes.length, count);
  }
});
test("a draft bound to a previous workspace is not sent", async () => {
  const f = fixture();
  await f.service.refresh();
  const expected = f.local.scope(),
    count = f.writes.length;
  f.setScope("account:3:workspace:9");
  await assert.rejects(f.service.repository().save(profile("Antigo"), expected, 0), /sessão mudou/);
  assert.equal(f.writes.length, count);
});
test("unauthenticated or incompatible responses never mark settings ready", async () => {
  const f = fixture();
  f.auth.request = async () => [];
  await f.service.refresh();
  assert.equal(f.service.state().profileState, "error");
  assert.equal(f.service.state().preferencesState, "error");
  assert.equal(f.service.repository().read().profile, null);
  const n = f.writes.length;
  f.auth.current = null;
  await f.service.refresh();
  assert.equal(f.writes.length, n);
});
test("reading a cached profile gives a copy, not unconfirmed edits", async () => {
  const f = fixture();
  f.auth.request = async () => ({ schema_version: 1, revision: 2, profile: profile("Original") });
  await f.service.refresh("profile");
  f.service.repository().read().profile.services.push("Não salvo");
  assert.deepEqual(f.service.repository().read().profile.services, ["Barba"]);
});

test("a failed legacy snapshot blocks remote preference application until preservation succeeds", async () => {
  const f = fixture();
  const set = f.storage.setItem;
  f.data.set("socialmei-app-data-v2", JSON.stringify({ prefs: { notificacoes: false } }));
  f.storage.setItem = (key, value) => {
    if (key.startsWith("socialmei-profile-sync-legacy")) throw Error("quota");
    set(key, value);
  };
  await f.service.refresh("preferences");
  assert.equal(f.applied.length, 0);
  assert.equal(f.service.state().preferencesState, "error");
  assert.equal(JSON.parse(f.data.get("socialmei-app-data-v2")).prefs.notificacoes, false);
  f.storage.setItem = set;
  await f.service.refresh("preferences");
  assert.equal(f.service.state().preferencesState, "ready");
  assert.equal(f.service.legacyPreferences().notificationsEnabled, false);
});
test("preference updates and retries cannot carry an old workspace into a newly bound scope", async () => {
  const f = fixture();
  await f.service.refresh();
  const old = f.local.scope();
  f.auth.request = async () => {
    throw Error("offline");
  };
  await assert.rejects(f.service.updatePreferences({ theme: "dark" }));
  const calls = [];
  f.auth.request = async (path, method, value) => {
    calls.push({ path, method, value });
    return { schema_version: 1, revision: 1, preferences: value?.preferences || defaults() };
  };
  f.setScope("account:1:workspace:99");
  assert.equal(await f.service.retryPreferences(), false);
  assert.equal(calls.length, 0);
  await assert.rejects(f.service.updatePreferences({ theme: "light" }), /Carregue/);
  assert.equal(calls.length, 0);
  await f.service.refresh("preferences");
  const count = calls.length;
  await assert.rejects(f.service.updatePreferences({ theme: "dark" }, 1, old), /sessão mudou/);
  assert.equal(calls.length, count);
});
