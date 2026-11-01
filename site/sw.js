/* Network-first app shell. Keep outage data and UI assets fresh, with offline fallback. */
const SHELL_CACHE = "nashe-svitlo-static-v46";
const STATIC = ["./", "./favicon.svg", "./touch-bulb-v2.png", "./manifest.webmanifest", "./ecoflow.css?v=46", "./ecoflow.js?v=46"];
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
  if (url.pathname.endsWith("/data.json")) {
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
  if (url.pathname.endsWith("/ecoflow.css") || url.pathname.endsWith("/ecoflow.js")) {
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
