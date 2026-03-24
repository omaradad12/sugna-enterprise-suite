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

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-resources-hub]");
    if (!root) return;

    var input = root.querySelector("[data-resources-search]");
    var items = root.querySelectorAll("[data-resources-item]");
    var empty = root.querySelector("[data-resources-empty]");

    function apply() {
      var q = norm(input ? input.value : "");
      var n = 0;
      items.forEach(function (el) {
        var text = norm(el.textContent);
        var show = !q || text.indexOf(q) !== -1;
        el.hidden = !show;
        if (show) n += 1;
      });
      if (empty) empty.hidden = n > 0;
    }

    if (input) {
      input.addEventListener("input", debounce(apply, 180));
      input.addEventListener("search", apply);
    }
    apply();
  });
})();
