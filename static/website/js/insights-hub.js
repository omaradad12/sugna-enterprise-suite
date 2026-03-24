(function () {
  "use strict";

  function norm(s) {
    return (s || "")
      .toLowerCase()
      .replace(/\s+/g, " ")
      .trim();
  }

  function debounce(fn, ms) {
    var t;
    return function () {
      var ctx = this;
      var args = arguments;
      clearTimeout(t);
      t = setTimeout(function () {
        fn.apply(ctx, args);
      }, ms);
    };
  }

  function itemText(el) {
    if (el.hasAttribute("data-insights-text")) {
      return norm(el.getAttribute("data-search-index") || el.textContent);
    }
    return norm(el.textContent);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-insights-hub]");
    if (!root) return;

    var chips = root.querySelectorAll("[data-insights-filter]");
    var searchInput = root.querySelector("[data-insights-search]");
    var items = root.querySelectorAll("[data-insights-item]");
    var emptyMsg = root.querySelector("[data-insights-empty]");
    var featGroup = root.querySelector("[data-insights-featured-group]");
    var featArticle = root.querySelector(".insights-featured[data-insights-item]");

    var activeFilter = "all";
    var searchQ = "";

    items.forEach(function (el) {
      el.setAttribute("data-search-index", itemText(el));
    });

    function apply() {
      var q = norm(searchQ);
      var visibleCount = 0;

      items.forEach(function (el) {
        var cat = el.getAttribute("data-category") || "";
        var text = norm(el.getAttribute("data-search-index") || el.textContent);
        var matchCat = activeFilter === "all" || cat === activeFilter;
        var matchSearch = !q || text.indexOf(q) !== -1;
        var show = matchCat && matchSearch;
        el.hidden = !show;
        if (show) visibleCount += 1;
      });

      if (emptyMsg) {
        emptyMsg.hidden = visibleCount > 0;
      }
      if (featGroup && featArticle) {
        featGroup.hidden = featArticle.hidden;
      }
    }

    chips.forEach(function (btn) {
      btn.addEventListener("click", function () {
        var v = btn.getAttribute("data-insights-filter") || "all";
        activeFilter = v;
        chips.forEach(function (b) {
          var on = b === btn;
          b.classList.toggle("is-active", on);
          b.setAttribute("aria-selected", on ? "true" : "false");
        });
        apply();
      });
    });

    if (searchInput) {
      var onInput = debounce(function () {
        searchQ = searchInput.value || "";
        apply();
      }, 200);
      searchInput.addEventListener("input", onInput);
      searchInput.addEventListener("search", onInput);
    }

    apply();
  });
})();
