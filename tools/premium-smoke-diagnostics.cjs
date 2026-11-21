/* Read-only release checks. Never retain headers, bodies, cookies or query strings. */
const { performance } = require("node:perf_hooks");

function attachRequestDiagnostics(page, origin) {
  const active = new Map();
  const events = [];
  const summary = (request) => {
    const url = new URL(request.url());
    return url.origin === origin ? { method: request.method(), path: url.pathname } : null;
  };
  page.on("request", (request) => {
    const record = summary(request);
    if (record) active.set(request, { ...record, started: performance.now() });
  });
  const finish = (request, failed) => {
    const record = active.get(request);
    if (!record) return;
    active.delete(request);
    events.push({
      method: record.method,
      path: record.path,
      milliseconds: Math.round(performance.now() - record.started),
      failed,
    });
  };
  page.on("requestfinished", (request) => finish(request, false));
  page.on("requestfailed", (request) => finish(request, true));
  return {
    events,
    pending: () => [...active.values()].map(({ method, path }) => ({ method, path })),
  };
}

async function readWorkspaceApi(page, path, records) {
  if (!/^\/[A-Za-z0-9_/-]+(?:\?[A-Za-z0-9_=&-]+)?$/.test(path))
    throw Error("Invalid readonly smoke path");
  const record = { path: path.split("?")[0], started: performance.now() };
  try {
    const outcome = await page.evaluate(async (p) => {
      try {
        return { ok: true, value: await window.SocialMEIAuth.request(p) };
      } catch (error) {
        return {
          ok: false,
          code: ["request_timeout", "connection_failed"].includes(error.code)
            ? error.code
            : "request_failed",
        };
      }
    }, path);
    if (!outcome.ok) {
      record.code = outcome.code;
      throw Error("Read failed");
    }
    records.push({
      path: record.path,
      milliseconds: Math.round(performance.now() - record.started),
      ok: true,
    });
    return outcome.value;
  } catch (_) {
    records.push({
      path: record.path,
      milliseconds: Math.round(performance.now() - record.started),
      ok: false,
      code: record.code || "request_failed",
    });
    throw Error(
      "Readonly smoke request failed: " +
        record.path +
        " (" +
        (record.code || "request_failed") +
        ")",
    );
  }
}

async function waitForApp(page, userId, workspaceId, previousDocument) {
  await page.waitForFunction(
    ({ userId, workspaceId, previousDocument }) =>
      (!previousDocument || performance.timeOrigin !== previousDocument) &&
      window.SocialMEIAuth?.current?.usuario.id === userId &&
      (!workspaceId || window.SocialMEIAuth.current.negocio.id === workspaceId) &&
      !!window.SocialMEIV22 &&
      !document.getElementById("app").hidden,
    { userId, workspaceId, previousDocument },
    { timeout: 30000 },
  );
  await page.evaluate(() => window.SocialMEIV22.ready);
  await page.locator("#app #v").waitFor({ state: "visible" });
  await page.waitForFunction(() => !!window.SocialMEIBusinesses, {}, { timeout: 30000 });
}

async function attachChromeTimings(context, page, origin) {
  const session = await context.newCDPSession(page);
  const requests = new Map(),
    records = [],
    sent = new Set();
  session.on("Network.requestWillBeSent", (event) => {
    const url = new URL(event.request.url);
    if (url.origin !== origin) return;
    const record = {
      path: url.pathname,
      method: event.request.method,
      started: event.timestamp,
      extraInfoObserved: sent.has(event.requestId),
    };
    requests.set(event.requestId, record);
    records.push(record);
  });
  session.on("Network.requestWillBeSentExtraInfo", (event) => {
    sent.add(event.requestId);
    const record = requests.get(event.requestId);
    if (record) record.extraInfoObserved = true;
  });
  session.on("Network.responseReceived", (event) => {
    const record = requests.get(event.requestId);
    if (!record) return;
    record.status = event.response.status;
    record.protocol = event.response.protocol;
    record.sendStart = event.response.timing?.sendStart;
    record.receiveHeadersEnd = event.response.timing?.receiveHeadersEnd;
  });
  const finish = (event, failed) => {
    const record = requests.get(event.requestId);
    if (!record) return;
    record.duration = Math.round((event.timestamp - record.started) * 1000);
    record.failed = failed;
    if (failed)
      record.error = /^net::ERR_[A-Z0-9_]+$/.test(event.errorText || "")
        ? event.errorText
        : "network_failed";
  };
  session.on("Network.loadingFinished", (event) => finish(event, false));
  session.on("Network.loadingFailed", (event) => finish(event, true));
  await session.send("Network.enable");
  return { records };
}

module.exports = { attachRequestDiagnostics, attachChromeTimings, readWorkspaceApi, waitForApp };
