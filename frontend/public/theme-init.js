// Applies the saved theme before first paint so the page does not flash.
// External file (not inline) so the Content-Security-Policy can forbid
// inline scripts. theme/apply-theme.ts writes both keys.
(function () {
  try {
    var theme = localStorage.getItem("ui-theme");
    if (theme && /^[a-z0-9-]+$/.test(theme)) {
      document.documentElement.dataset.theme = theme;
    }
    if (localStorage.getItem("ui-theme-dark") === "1") {
      document.documentElement.classList.add("dark");
      document.documentElement.style.colorScheme = "dark";
      document.querySelector('link[rel="icon"]').setAttribute("href", "/favicon-dark.svg");
    }
  } catch (e) {}
})();
