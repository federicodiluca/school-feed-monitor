// Registrazione del service worker (PWA). Richiede HTTPS: su http://IP viene semplicemente ignorato.
if ("serviceWorker" in navigator && (location.protocol === "https:" || location.hostname === "localhost")) {
  window.addEventListener("load", function () {
    navigator.serviceWorker.register("/sw.js").catch(function () { /* niente PWA, pazienza */ });
  });
}
