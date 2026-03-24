/**
 * "What Sugna helps you manage" — single-select toggleable tiles (platform marketing page).
 */
(function () {
  var grid = document.querySelector(".sugna-platform-page--marketing .sp-manage-grid");
  if (!grid) return;

  var items = grid.querySelectorAll("button.sp-manage-item");
  if (!items.length) return;

  function clearActive() {
    items.forEach(function (btn) {
      btn.classList.remove("is-active");
      btn.setAttribute("aria-pressed", "false");
    });
  }

  items.forEach(function (btn) {
    btn.addEventListener("click", function () {
      var wasActive = btn.classList.contains("is-active");
      clearActive();
      if (!wasActive) {
        btn.classList.add("is-active");
        btn.setAttribute("aria-pressed", "true");
      }
    });
  });
})();
