/* Apply the system theme before the first paint, without persisting a preference. */
document.documentElement.dataset.previewTheme = matchMedia("(prefers-color-scheme: dark)").matches
  ? "dark"
  : "light";
