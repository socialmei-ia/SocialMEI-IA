/* Native interaction layer; it observes presentation and never changes business records. */
const SocialMEIPremiumUI = (() => {
  const history = new Map(),
    seenRows = new Set();
  let owner = null,
    queued = false,
    frame = 0,
    jobs = [];
  const visible = (node) => node && node.getClientRects().length > 0;
  function cancelCounts() {
    cancelAnimationFrame(frame);
    frame = 0;
    jobs.forEach((job) => {
      if (history.get(job.key)?.node === job.node) history.get(job.key).current = job.end;
      job.node.classList.remove("premium-counting");
      job.node.removeAttribute("data-display");
      job.node.removeAttribute("role");
      job.node.removeAttribute("aria-label");
    });
    jobs = [];
  }
  function counts(view) {
    if (
      SocialMEIMotion.reduced ||
      areMoneyValuesHidden ||
      !CSS.supports("-webkit-text-fill-color", "transparent")
    )
      return;
    const nodes = [...view.querySelectorAll(".management-kpi > b,.internal-metric > b")];
    nodes.forEach((node, index) => {
      if (
        !visible(node) ||
        node.closest("#reportsView") ||
        node.classList.contains("premium-counting")
      )
        return;
      const target = node.textContent.trim(),
        value = target
          .replace(/[^\d,.-]/g, "")
          .replace(/\./g, "")
          .replace(",", ".");
      const isMoney = /R\$/.test(target),
        isNumber = /^\d+$/.test(target);
      if ((!isMoney && !isNumber) || !Number.isFinite(Number(value)) || !value) return;
      const end = Number(value),
        key = view.id + ":" + (node.closest("[id]")?.id || "metric") + ":" + index;
      const previous = history.get(key);
      if (previous?.target === end && previous.current === end) return;
      history.set(key, { target: end, current: previous?.current ?? 0, node });
      const start = previous?.current ?? 0;
      node.classList.add("premium-counting");
      node.setAttribute("role", "img");
      node.setAttribute("aria-label", target);
      const job = { node, start, end, isMoney, started: performance.now(), key };
      jobs.push(job);
      node.dataset.display = isMoney ? formatCurrency(start) : String(Math.round(start));
    });
    if (!frame && jobs.length) frame = requestAnimationFrame(tick);
  }
  function tick(now) {
    frame = 0;
    jobs = jobs.filter((job) => {
      const t = Math.min(1, (now - job.started) / 520);
      if (!job.node.isConnected || areMoneyValuesHidden || SocialMEIMotion.reduced || t >= 1) {
        if (history.get(job.key)?.node === job.node) history.get(job.key).current = job.end;
        job.node.classList.remove("premium-counting");
        job.node.removeAttribute("data-display");
        job.node.removeAttribute("role");
        job.node.removeAttribute("aria-label");
        return false;
      }
      const value = job.start + (job.end - job.start) * (1 - (1 - t) ** 3);
      if (history.get(job.key)?.node === job.node) history.get(job.key).current = value;
      job.node.dataset.display = job.isMoney ? formatCurrency(value) : String(Math.round(value));
      return true;
    });
    if (jobs.length) frame = requestAnimationFrame(tick);
  }
  function sidebar() {
    const nav = document.getElementById("nav"),
      active = nav.querySelector(".nl.active");
    if (!visible(active)) return;
    let marker = nav.querySelector(".nav-active-motion");
    if (!marker) {
      marker = document.createElement("span");
      marker.className = "nav-active-motion";
      marker.setAttribute("aria-hidden", "true");
      nav.prepend(marker);
    }
    const box = active.getBoundingClientRect(),
      bounds = nav.getBoundingClientRect();
    marker.style.left = box.left - bounds.left + "px";
    marker.style.width = box.width + "px";
    marker.style.height = box.height + "px";
    marker.style.transform = `translateY(${box.top - bounds.top + nav.scrollTop}px)`;
    nav.classList.add("nav-motion-ready");
  }
  function update() {
    queued = false;
    const next =
      SocialMEIBusinessProfile.browserRepository().scope() + "|" + SocialMEIDemoData.enabled();
    if (owner !== next) {
      owner = next;
      history.clear();
      seenRows.clear();
      cancelCounts();
    }
    const view = document.querySelector(".page-view.active");
    if (!view || !document.body.classList.contains("experience-app")) return;
    sidebar();
    counts(view);
    const rows = [
      ...view.querySelectorAll("[data-native-opportunity],.content-draft-row,[data-record-id]"),
    ].slice(0, 30);
    rows.forEach((node) => {
      const key =
        view.id +
        ":" +
        (node.dataset.nativeOpportunity ||
          node.dataset.recordId ||
          node.querySelector("[data-content-open]")?.dataset.contentOpen);
      if (view.id === "reportsView" || seenRows.has(key) || !visible(node)) return;
      seenRows.add(key);
      SocialMEIMotion.animate(
        node.closest("tr,article,li") || node,
        [
          { opacity: 0.65, transform: "translateY(5px)" },
          { opacity: 1, transform: "none" },
        ],
        220,
      );
    });
  }
  const queue = () => {
    if (!queued) {
      queued = true;
      requestAnimationFrame(update);
    }
  };
  document.addEventListener("DOMContentLoaded", () => {
    new MutationObserver((records) => {
      if (records.some((record) => [...record.addedNodes].some((node) => node.nodeType === 1)))
        queue();
    }).observe(document.getElementById("mainContent"), { childList: true, subtree: true });
    document.addEventListener("socialmei-view-change", () => {
      cancelCounts();
      queue();
    });
    document.addEventListener("socialmei-demo-change", queue);
    document.addEventListener("socialmei-data-change", queue);
    document.addEventListener("socialmei-motion-change", () => {
      if (SocialMEIMotion.reduced) cancelCounts();
    });
    window.addEventListener("resize", queue, { passive: true });
    window.addEventListener("pagehide", cancelCounts);
    document.addEventListener("click", (event) => {
      const popover = event.target.closest("#viewDemoControl,.opportunity-options");
      document
        .querySelectorAll("#viewDemoControl[open],.opportunity-options[open]")
        .forEach((details) => {
          if (details !== popover) details.open = false;
        });
    });
    document.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      document
        .querySelectorAll("#viewDemoControl[open],.opportunity-options[open]")
        .forEach((details) => {
          details.open = false;
          details.querySelector("summary").focus();
        });
    });
    document.addEventListener(
      "toggle",
      (event) => {
        const details = event.target;
        if (
          details instanceof HTMLDetailsElement &&
          details.matches(
            ".context-help,.workspace-data-info,.client-analysis-choice,.content-local-note",
          ) &&
          details.open &&
          !SocialMEIMotion.reduced
        ) {
          const children = [...details.children].filter((node) => node.tagName !== "SUMMARY");
          children.slice(0, 3).forEach((node) =>
            SocialMEIMotion.animate(
              node,
              [
                { opacity: 0.6, transform: "translateY(-3px)" },
                { opacity: 1, transform: "none" },
              ],
              160,
            ),
          );
        }
      },
      true,
    );
    queue();
  });
  return Object.freeze({ update });
})();
