// Service worker minimo: la "shell" (CSS, icone, JS) sta in cache, le pagine passano dalla
// rete e, se la rete manca, si ricade sull'ultima versione vista.
const CACHE = "sfm-v1";
const SHELL = ["./", "./static/style.css", "./static/theme.js", "./static/favicon.svg", "./static/offline.html"];

self.addEventListener("install", (e) => {
  e.waitUntil(caches.open(CACHE).then((c) => c.addAll(SHELL)).then(() => self.skipWaiting()));
});

self.addEventListener("activate", (e) => {
  e.waitUntil(caches.keys().then((keys) =>
    Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k)))).then(() => self.clients.claim()));
});

self.addEventListener("fetch", (e) => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== self.location.origin) return;
  e.respondWith(
    fetch(req)
      .then((resp) => {
        const copy = resp.clone();
        caches.open(CACHE).then((c) => c.put(req, copy));
        return resp;
      })
      .catch(() => caches.match(req).then((hit) => hit || caches.match(new URL("./static/offline.html", self.location).pathname)))
  );
});
