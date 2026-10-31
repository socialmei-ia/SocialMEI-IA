/* Public marketing page only: no analytics or session recording in the authenticated CRM.
   Nothing leaves the browser before opt-in; identifiers come from public operator config. */
(() => {
  "use strict";
  if (document.body?.dataset?.socialmeiAuthenticatedApp === "true") return;
  if (location.pathname !== "/sobre.html" && !location.pathname.endsWith("/frontend/sobre.html")) return;
  const settings =
    typeof SOCIALMEI_CONFIG !== "undefined" ? SOCIALMEI_CONFIG.siteMetrics : null;
  const enabled = settings?.enabled === true;
  const ga = enabled && /^G-[A-Z0-9]{6,16}$/.test(settings.ga4MeasurementId || "")
    ? settings.ga4MeasurementId : null;
  const clarity = enabled && /^[a-z0-9]{8,32}$/i.test(settings.clarityProjectId || "")
    ? settings.clarityProjectId : null;
  const active = !!(ga || clarity);
  const key = "socialmei-public-metrics-consent-v1";
  const banner = document.getElementById("metrics-consent");
  const accept = document.getElementById("metrics-accept");
  const decline = document.getElementById("metrics-decline");
  const preferences = document.getElementById("privacy-preferences");
  if (!banner || !accept || !decline || !preferences) return;
  let granted = false;
  const stored = () => {
    try { return localStorage.getItem(key); } catch { return null; }
  };
  const save = (value) => {
    try { localStorage.setItem(key, value); } catch { /* private browsing */ }
  };
  function loadScript(src, label) {
    const script = document.createElement("script");
    script.async = true;
    script.src = src;
    script.dataset.publicMetrics = label;
    document.head.appendChild(script);
  }
  function startMetrics() {
    if (granted || !active) return;
    granted = true;
    if (ga) {
      window.dataLayer = window.dataLayer || [];
      window.gtag = function () { window.dataLayer.push(arguments); };
      window.gtag("consent", "default", {
        analytics_storage: "denied", ad_storage: "denied",
        ad_user_data: "denied", ad_personalization: "denied",
      });
      window.gtag("consent", "update", { analytics_storage: "granted" });
      window.gtag("js", new Date());
      window.gtag("config", ga, {
        send_page_view: true,
        allow_google_signals: false,
        allow_ad_personalization_signals: false,
      });
      loadScript("https://www.googletagmanager.com/gtag/js?id=" + encodeURIComponent(ga), "ga4");
    }
    if (clarity) {
      window.clarity = window.clarity || function () {
        (window.clarity.q = window.clarity.q || []).push(arguments);
      };
      loadScript("https://www.clarity.ms/tag/" + encodeURIComponent(clarity), "clarity");
    }
  }
  function clearFirstPartyMetricsCookies() {
    for (const cookie of document.cookie.split(";")) {
      const name = cookie.split("=", 1)[0].trim();
      if (/^(?:_ga(?:_|$)|_gid$|_gat(?:_|$)|_clck$|_clsk$)/.test(name)) {
        document.cookie = name + "=; Max-Age=0; path=/; SameSite=Lax";
      }
    }
  }
  function updateBanner() {
    banner.hidden = !active || stored() === "accepted" || stored() === "declined";
    if (!active) {
      preferences.title = "Métricas não estão habilitadas nesta página.";
      preferences.setAttribute("aria-disabled", "true");
    }
  }
  accept.addEventListener("click", () => {
    save("accepted");
    banner.hidden = true;
    startMetrics();
  });
  decline.addEventListener("click", () => {
    const wasGranted = granted || stored() === "accepted";
    save("declined");
    banner.hidden = true;
    if (wasGranted) {
      clearFirstPartyMetricsCookies();
      // Previously loaded third-party code cannot be unloaded safely.
      location.reload();
    }
  });
  preferences.addEventListener("click", () => {
    if (!active) return;
    banner.hidden = false;
    decline.focus();
  });
  if (active && stored() === "accepted") startMetrics();
  updateBanner();
})();
