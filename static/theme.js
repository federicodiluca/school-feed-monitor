// Tema chiaro/scuro: rispetta prefers-color-scheme; il toggle salva la scelta in localStorage.
(function () {
  var KEY = "theme";
  function apply(t) {
    if (t === "dark" || t === "light") document.documentElement.setAttribute("data-theme", t);
    else document.documentElement.removeAttribute("data-theme");
  }
  var saved = null;
  try { saved = localStorage.getItem(KEY); } catch (e) {}
  apply(saved);
  document.addEventListener("DOMContentLoaded", function () {
    var btn = document.getElementById("theme-toggle");
    if (!btn) return;
    btn.addEventListener("click", function () {
      var dark = document.documentElement.getAttribute("data-theme") === "dark" ||
        (!document.documentElement.getAttribute("data-theme") && window.matchMedia("(prefers-color-scheme: dark)").matches);
      var next = dark ? "light" : "dark";
      apply(next);
      try { localStorage.setItem(KEY, next); } catch (e) {}
    });
  });
})();
