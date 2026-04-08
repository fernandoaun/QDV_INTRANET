/* Base para PWA: activación inmediata; ampliar con precache cuando definas estrategia offline. */
self.addEventListener("install", function (event) {
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(self.clients.claim());
});
