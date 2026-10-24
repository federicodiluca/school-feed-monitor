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

  // Menù: le voci che dipendono dalle preferenze («Le mie notizie», «Le mie fonti») e da
  // «Installa» si decidono qui, prima che la pagina venga disegnata. Deciderle in app.js
  // (defer, a pagina già disegnata) faceva saltare il menù a ogni cambio di pagina.
  var root = document.documentElement;
  function hasCookie(name) {
    return document.cookie.split("; ").some(function (c) {
      var v = c.indexOf(name + "=") === 0 ? c.slice(name.length + 1) : "";
      return v !== "" && v !== '""';
    });
  }
  if (hasCookie("sfm_fonti") || hasCookie("sfm_parole")) root.classList.add("has-prefs");
  var standalone = (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches) ||
    navigator.standalone === true;
  var ios = /iphone|ipad|ipod/i.test(navigator.userAgent) ||
    (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
  var installable = null;
  try { installable = localStorage.getItem("sfm-installable"); } catch (e) {}
  // su Chrome/Edge il browser lo propone solo dopo il caricamento: ci si ricorda che l'ha fatto
  if (!standalone && (ios || installable === "1")) root.classList.add("can-install");
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
