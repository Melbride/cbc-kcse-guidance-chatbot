(function () {
  const THEME_KEY = "kcseUiTheme";

  function getStoredTheme() {
    try {
      const value = localStorage.getItem(THEME_KEY);
      return value === "dark" || value === "light" ? value : null;
    } catch {
      return null;
    }
  }

  function getPreferredTheme() {
    const stored = getStoredTheme();
    if (stored) return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function updateThemeControls() {
    const isDark = document.body.classList.contains("theme-dark");
    const nextLabel = isDark ? "Light mode" : "Dark mode";
    const icon = isDark ? "Sun" : "Moon";

    document.querySelectorAll(".theme-toggle-text").forEach((el) => {
      el.textContent = nextLabel;
    });

    document.querySelectorAll(".theme-toggle-icon").forEach((el) => {
      el.textContent = icon;
    });

    document.querySelectorAll(".theme-toggle-button").forEach((el) => {
      el.setAttribute("aria-label", nextLabel);
      el.setAttribute("title", nextLabel);
    });
  }

  function applyTheme(theme, persist) {
    const resolved = theme === "dark" ? "dark" : "light";
    document.body.classList.remove("theme-dark", "theme-light");
    document.body.classList.add(resolved === "dark" ? "theme-dark" : "theme-light");

    if (persist) {
      try {
        localStorage.setItem(THEME_KEY, resolved);
      } catch {
        // Ignore storage failures.
      }
    }

    updateThemeControls();
  }

  function toggleTheme() {
    const isDark = document.body.classList.contains("theme-dark");
    applyTheme(isDark ? "light" : "dark", true);
  }

  function createThemeButton(extraClassName) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `theme-toggle-button ${extraClassName || ""}`.trim();
    button.innerHTML = '<span class="theme-toggle-text">Dark mode</span>';
    button.addEventListener("click", toggleTheme);
    return button;
  }

  function injectNavbarToggle() {
    const navActions = document.querySelector(".landing-nav-actions");
    
    if (navActions && !navActions.querySelector(".theme-toggle-button")) {
      navActions.appendChild(createThemeButton("kcse-nav-theme-toggle"));
      return;
    }
    
    const nav = document.querySelector(".landing-navbar .navbar-nav");
    if (!nav || nav.querySelector(".theme-toggle-button")) return;

    const item = document.createElement("li");
    item.className = "nav-item d-inline-block ms-lg-2 mt-2 mt-lg-0";
    item.appendChild(createThemeButton("kcse-nav-theme-toggle"));
    nav.appendChild(item);
  }

  function injectChatToggle() {
    const actions = document.querySelector(".chat-topbar-actions");
    if (!actions || actions.querySelector(".theme-toggle-button")) return;
    actions.appendChild(createThemeButton("kcse-chat-theme-toggle"));
  }

  function injectAdminToggle() {
    const adminInfo = document.querySelector(".admin-info");
    if (!adminInfo || adminInfo.querySelector(".theme-toggle-button")) return;
    adminInfo.appendChild(createThemeButton("kcse-admin-theme-toggle btn btn-sm"));
  }

  document.addEventListener("DOMContentLoaded", () => {
    applyTheme(getPreferredTheme(), false);
    injectNavbarToggle();
    injectChatToggle();
    injectAdminToggle();
    updateThemeControls();
  });

  applyTheme(getPreferredTheme(), false);
  window.toggleTheme = toggleTheme;
})();
