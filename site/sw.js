/* Network-first app shell. Keep outage data and UI assets fresh, with offline fallback. */
const SHELL_CACHE = "nashe-svitlo-static-v52";
const STATIC = ["./", "./favicon.svg", "./touch-bulb-v2.png", "./manifest.webmanifest", "./pwa-icon-192.svg", "./pwa-icon-512.svg", "./ecoflow.css?v=52", "./ecoflow-live.js?v=52", "./ecoflow.js?v=52"];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(SHELL_CACHE).then(cache => cache.addAll(STATIC)).then(() => self.skipWaiting()));
});
self.addEventListener("activate", event => {
  event.waitUntil(
    caches.keys().then(keys => Promise.all(
      keys.filter(key => key.startsWith("nashe-svitlo-static-") && key !== SHELL_CACHE)
        .map(key => caches.delete(key))
    )).then(() => self.clients.claim())
  );
});
self.addEventListener("fetch", event => {
  const request = event.request;
  const url = new URL(request.url);
  if (request.method !== "GET" || url.origin !== self.location.origin) return;
  if (url.pathname.endsWith("/data.json") || url.pathname.endsWith("/ecoflow-live-config.json") || url.pathname.endsWith("/ecoflow-snapshot.json")) {
    // Never cache schedules.
    event.respondWith(fetch(request, {cache: "no-store"}));
    return;
  }
  if (request.mode === "navigate") {
    event.respondWith(
      fetch(request, {cache: "no-store"}).then(response => {
        if (response.ok) {
          const copy = response.clone();
          event.waitUntil(caches.open(SHELL_CACHE).then(cache => cache.put("./", copy)));
        }
        return response;
      }).catch(async () => (await caches.match("./")) || Response.error())
    );
    return;
  }
  if (url.pathname.endsWith("/ecoflow.css") || url.pathname.endsWith("/ecoflow.js") || url.pathname.endsWith("/ecoflow-live.js")) {
    // Network-first: a previous service worker must never pin old charging arrows or layouts.
    event.respondWith(
      fetch(request, {cache: "no-store"}).then(response => {
        if (response.ok) {
          const copy = response.clone();
          event.waitUntil(caches.open(SHELL_CACHE).then(cache => cache.put(request, copy)));
        }
        return response;
      }).catch(async () => (await caches.match(request)) || Response.error())
    );
    return;
  }
  if (STATIC.some(path => url.pathname.endsWith(path.split("?")[0].slice(1)))) {
    event.respondWith(caches.match(request).then(cached => cached || fetch(request)));
  }
});
