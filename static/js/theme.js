(() => {
  const storageKey = "vofknuht-theme";
  const root = document.documentElement;
  const preference = window.matchMedia("(prefers-color-scheme: dark)");
  let savedTheme = null;
  try {
    const stored = localStorage.getItem(storageKey);
    if (stored === "dark" || stored === "light") savedTheme = stored;
  } catch {
    // Theme switching still works when browser storage is unavailable.
  }
  let button;

  function applyTheme(theme) {
    root.dataset.theme = theme;
    if (!button) return;
    const isDark = theme === "dark";
    button.setAttribute("aria-pressed", String(isDark));
    button.setAttribute(
      "aria-label",
      isDark ? "Увімкнути світлу тему" : "Увімкнути темну тему",
    );
    button.title = button.getAttribute("aria-label");
    button.querySelector(".theme-label").textContent = isDark
      ? "Світла"
      : "Темна";
  }

  // Run in <head>, before styles paint, to avoid flashing the light theme.
  applyTheme(savedTheme || (preference.matches ? "dark" : "light"));
  preference.addEventListener("change", (event) => {
    if (!savedTheme) applyTheme(event.matches ? "dark" : "light");
  });
  document.addEventListener("DOMContentLoaded", () => {
    button = document.querySelector("[data-theme-toggle]");
    if (!button) return;
    applyTheme(root.dataset.theme);
    button.addEventListener("click", () => {
      savedTheme = root.dataset.theme === "dark" ? "light" : "dark";
      applyTheme(savedTheme);
      try {
        localStorage.setItem(storageKey, savedTheme);
      } catch {
        // Keep the selected theme for this page even without persistent storage.
      }
    });
  });
})();
