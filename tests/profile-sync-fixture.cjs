// Same-origin API fixture shared by existing browser suites; real contracts run on PostgreSQL.
const { defaults } = require("../frontend/scripts/profile-sync.js");
module.exports = function profileFixture() {
  const profiles = new Map(),
    preferences = new Map();
  return (route, identity) => {
    const request = route.request(),
      pathname = new URL(request.url()).pathname;
    const shared = pathname === "/api/v1/workspace-profile";
    if (!shared && pathname !== "/api/v1/auth/preferences") return null;
    if (!identity) return route.fulfill({ status: 401, json: { detail: "Sessão ausente" } });
    const map = shared ? profiles : preferences;
    const key = shared ? identity.negocio.id : identity.usuario.id + ":" + identity.negocio.id;
    const field = shared ? "profile" : "preferences";
    let record = map.get(key) || {
      schema_version: 1,
      revision: 0,
      [field]: shared ? null : defaults(),
    };
    if (request.method() === "PATCH") {
      if (shared && !["owner", "admin"].includes(identity.papel))
        return route.fulfill({ status: 403, json: { detail: "Somente leitura" } });
      const input = request.postDataJSON();
      if (input.expected_revision !== record.revision)
        return route.fulfill({ status: 409, json: { detail: "Alterado em outra sessão" } });
      record = {
        schema_version: 1,
        revision: record.revision + 1,
        [field]: structuredClone(input[field]),
      };
      if (shared) record.profile.businessName = identity.negocio.nome;
      map.set(key, record);
    }
    return route.fulfill({ json: record });
  };
};
