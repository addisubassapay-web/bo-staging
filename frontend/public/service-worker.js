/* Ocean — Service Worker
 * - App shell + navigation offline fallback
 * - Cache-first for static assets, network-first for API
 */
const VERSION = "v2-ocean-rebrand";
const APP_SHELL_CACHE = `ocean-shell-${VERSION}`;
const RUNTIME_CACHE   = `ocean-runtime-${VERSION}`;

const APP_SHELL = [
  "/",
  "/index.html",
  "/manifest.json",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open(APP_SHELL_CACHE).then((cache) => cache.addAll(APP_SHELL)).catch(() => {})
  );
  self.skipWaiting();
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(
        keys
          .filter((k) => k !== APP_SHELL_CACHE && k !== RUNTIME_CACHE)
          .map((k) => caches.delete(k))
      )
    )
  );
  self.clients.claim();
});

self.addEventListener("fetch", (event) => {
  const req = event.request;
  if (req.method !== "GET") return;
  const url = new URL(req.url);

  // Never intercept API calls or auth-sensitive endpoints — always go to network.
  if (url.pathname.startsWith("/api/")) return;

  // SPA navigation: try network, fall back to cached shell for offline.
  if (req.mode === "navigate") {
    event.respondWith(
      fetch(req).catch(() => caches.match("/index.html").then((r) => r || Response.error()))
    );
    return;
  }

  // Same-origin static assets: cache-first with runtime population.
  if (url.origin === self.location.origin) {
    event.respondWith(
      caches.match(req).then((cached) => {
        if (cached) return cached;
        return fetch(req)
          .then((resp) => {
            if (!resp || resp.status !== 200 || resp.type !== "basic") return resp;
            const copy = resp.clone();
            caches.open(RUNTIME_CACHE).then((c) => c.put(req, copy)).catch(() => {});
            return resp;
          })
          .catch(() => cached);
      })
    );
    return;
  }

  // Cross-origin (fonts, unsplash images): stale-while-revalidate.
  event.respondWith(
    caches.match(req).then((cached) => {
      const network = fetch(req)
        .then((resp) => {
          if (resp && resp.status === 200) {
            const copy = resp.clone();
            caches.open(RUNTIME_CACHE).then((c) => c.put(req, copy)).catch(() => {});
          }
          return resp;
        })
        .catch(() => cached);
      return cached || network;
    })
  );
});
