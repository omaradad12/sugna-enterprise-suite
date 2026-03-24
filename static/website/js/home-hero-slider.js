/**
 * Home hero fade slider — auto-advance, dots, prev/next, respects prefers-reduced-motion.
 */
(function () {
  var root = document.querySelector("[data-home-hero-slider]");
  if (!root || root.dataset.sliderInit === "1") return;
  root.dataset.sliderInit = "1";

  var slides = Array.prototype.slice.call(root.querySelectorAll(".home-hero-slide"));
  var dots = Array.prototype.slice.call(root.querySelectorAll(".home-hero-slider-dot"));
  var btnPrev = root.querySelector(".home-hero-slider-prev");
  var btnNext = root.querySelector(".home-hero-slider-next");
  if (!slides.length) return;

  var i = 0;
  var timer = null;
  var INTERVAL_MS = 6000;

  function go(n) {
    var len = slides.length;
    i = ((n % len) + len) % len;
    slides.forEach(function (s, j) {
      var active = j === i;
      s.classList.toggle("is-active", active);
      s.setAttribute("aria-hidden", active ? "false" : "true");
    });
    dots.forEach(function (d, j) {
      var active = j === i;
      d.classList.toggle("is-active", active);
      d.setAttribute("aria-selected", active ? "true" : "false");
    });
  }

  function next() {
    go(i + 1);
  }

  function prev() {
    go(i - 1);
  }

  function armTimer() {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    clearInterval(timer);
    timer = setInterval(next, INTERVAL_MS);
  }

  function disarmTimer() {
    clearInterval(timer);
    timer = null;
  }

  dots.forEach(function (d, j) {
    d.addEventListener("click", function () {
      go(j);
      armTimer();
    });
  });

  if (btnNext) {
    btnNext.addEventListener("click", function () {
      next();
      armTimer();
    });
  }
  if (btnPrev) {
    btnPrev.addEventListener("click", function () {
      prev();
      armTimer();
    });
  }

  root.addEventListener("mouseenter", disarmTimer);
  root.addEventListener("mouseleave", armTimer);
  root.addEventListener("focusin", disarmTimer);
  root.addEventListener("focusout", function (e) {
    if (!root.contains(e.relatedTarget)) armTimer();
  });

  root.addEventListener("keydown", function (e) {
    var t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.isContentEditable)) return;
    if (e.key === "ArrowLeft") {
      e.preventDefault();
      prev();
      armTimer();
    } else if (e.key === "ArrowRight") {
      e.preventDefault();
      next();
      armTimer();
    }
  });

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) disarmTimer();
    else armTimer();
  });

  go(0);
  armTimer();
})();
