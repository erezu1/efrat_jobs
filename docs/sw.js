// Service worker for the installable app. Network first, so the daily job list is always fresh
// when online; the last copy is shown when offline.
const CACHE = "biojobs-v5";

self.addEventListener("install", () => self.skipWaiting());
self.addEventListener("activate", e => e.waitUntil(
  caches.keys().then(keys => Promise.all(keys.filter(k => k !== CACHE).map(k => caches.delete(k))))
    .then(() => self.clients.claim())));

self.addEventListener("fetch", e => {
  const req = e.request;
  if (req.method !== "GET" || new URL(req.url).origin !== self.location.origin) return;
  if (req.url.endsWith(".webmanifest")) return;   // always let the browser fetch the manifest fresh
  e.respondWith(
    // "no-cache" = always ask the server for the newest version (bypasses the 10-minute HTTP cache)
    fetch(req, {cache: "no-cache"})
      .then(res => {
        const copy = res.clone();
        caches.open(CACHE).then(c => c.put(req, copy));
        return res;
      })
      .catch(() => caches.match(req).then(hit => hit || caches.match("./")))
  );
});
