/**
 * Smooth scroll to hash target on pricing subpages; respects scroll-margin for sticky header.
 */
(function () {
  if (!window.location.hash || window.location.hash.length < 2) return;

  function scrollToHash() {
    var id = window.location.hash.slice(1);
    if (!id) return;
    var el = document.getElementById(id);
    if (!el) return;
    el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", scrollToHash);
  } else {
    scrollToHash();
  }

  window.addEventListener("hashchange", scrollToHash);
})();
