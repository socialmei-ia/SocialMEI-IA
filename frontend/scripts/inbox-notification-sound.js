/* An opt-in chime for new inbound messages from the authenticated Inbox poll. */
(() => {
  const Audio = window.AudioContext || window.webkitAudioContext;
  if (!Audio) return;
  let audio,
    activeScope,
    highWater,
    lastChime = 0;
  const storageKey = (scope) => "socialmei-inbox-sound:" + scope;
  const enabled = (scope) => {
    try {
      return localStorage.getItem(storageKey(scope)) === "on";
    } catch {
      return false;
    }
  };
  function chime() {
    if (audio?.state !== "running") return;
    const tone = audio.createOscillator();
    const gain = audio.createGain();
    const start = audio.currentTime;
    tone.frequency.value = 660;
    gain.gain.setValueAtTime(0.05, start);
    gain.gain.exponentialRampToValueAtTime(0.001, start + 0.18);
    tone.connect(gain);
    gain.connect(audio.destination);
    tone.start(start);
    tone.stop(start + 0.18);
  }
  function observe(scope, items) {
    const newest = items.reduce((max, row) => {
      if (["waha", "instagram"].includes(row.origin) && Number.isSafeInteger(row.last_inbound_id))
        return Math.max(max, row.last_inbound_id);
      return max;
    }, 0);
    if (activeScope !== scope || highWater === undefined) {
      activeScope = scope;
      highWater = newest;
      return;
    }
    const fresh =
      newest > highWater &&
      items.some(
        (row) =>
          ["waha", "instagram"].includes(row.origin) &&
          Number.isSafeInteger(row.last_inbound_id) &&
          row.last_inbound_id > highWater &&
          row.unread_count > 0 &&
          !row.snoozed_until,
      );
    highWater = Math.max(highWater, newest);
    const now = Date.now();
    if (fresh && enabled(scope) && !document.hidden && now - lastChime >= 2000) {
      try {
        chime();
        lastChime = now;
      } catch {
        /* Audio permission may change while the page is open. */
      }
    }
  }
  function mount(scope) {
    if (!scope) return;
    if (activeScope !== scope) {
      activeScope = scope;
      highWater = undefined;
    }
    for (const target of document.querySelectorAll("#v .cx4-th")) {
      let button = target.querySelector("[data-inbox-sound]");
      if (!button) {
        button = document.createElement("button");
        button.type = "button";
        button.className = "btn o sm2";
        button.dataset.inboxSound = "true";
        target.append(button);
      }
      const paint = () => {
        const playing = enabled(scope) && audio?.state === "running";
        button.textContent = playing ? "Desativar som" : "Ativar som";
        button.setAttribute("aria-pressed", String(playing));
      };
      paint();
      button.onclick = async () => {
        try {
          if (enabled(scope) && audio?.state === "running") {
            localStorage.removeItem(storageKey(scope));
          } else {
            audio ||= new Audio();
            await audio.resume();
            if (!button.isConnected || activeScope !== scope) return;
            localStorage.setItem(storageKey(scope), "on");
          }
          paint();
        } catch {
          button.textContent = "Som indisponível";
        }
      };
    }
  }
  window.SocialMEIInboxSound = { mount, observe };
  const host = window.SocialMEIV22,
    identity = host?.identity;
  if (host?.remote && identity?.usuario && identity?.negocio)
    mount(`${identity.usuario.id}:${identity.negocio.id}`);
})();
