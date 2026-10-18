/* Never read or write this origin's real browser data. Each reload starts fresh. */
(() => {
  class MemoryStorage {
    #data = new Map();
    get length() {
      return this.#data.size;
    }
    getItem(key) {
      return this.#data.get(String(key)) ?? null;
    }
    setItem(key, value) {
      this.#data.set(String(key), String(value));
    }
    removeItem(key) {
      this.#data.delete(String(key));
    }
    clear() {
      this.#data.clear();
    }
    key(index) {
      return [...this.#data.keys()][index] ?? null;
    }
  }
  Object.defineProperty(window, "localStorage", { value: new MemoryStorage() });
  Object.defineProperty(window, "sessionStorage", { value: new MemoryStorage() });
  sessionStorage.setItem("socialmei-business-demo-identity", "reports-v21-preview");
  const blocked = () => {
    throw Error("Prévia isolada: conexões externas e APIs bloqueadas.");
  };
  // Static scripts/styles/images still load normally; business transports cannot run.
  window.fetch = async () => blocked();
  XMLHttpRequest.prototype.open = blocked;
  window.WebSocket = class {
    constructor() {
      blocked();
    }
  };
  window.EventSource = class {
    constructor() {
      blocked();
    }
  };
  navigator.sendBeacon = () => false;
  window.REPORTS_PREVIEW = { onlySynthetic: true, storage: "memory", network: "blocked" };
})();
