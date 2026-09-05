/* Service worker QDV PWA — estáticos con red primero; datos operativos nunca se cachean. */
var CACHE = "qdv-pwa-v5";
var PRECACHE = [
  "/static/favicon.png",
  "/static/pwa/icon-192.png",
  "/static/pwa/icon-512.png",
  "/static/pwa/site.webmanifest",
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(CACHE).then(function (cache) {
      return cache.addAll(PRECACHE);
    }).then(function () {
      return self.skipWaiting();
    })
  );
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys.filter(function (key) { return key !== CACHE; }).map(function (key) {
          return caches.delete(key);
        })
      );
    }).then(function () {
      return self.clients.claim();
    })
  );
});

function offlineShell(title, detail) {
  var html =
    "<!DOCTYPE html><html lang=\"es\"><head><meta charset=\"utf-8\">" +
    "<meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">" +
    "<title>" + title + "</title>" +
    "<style>body{font-family:system-ui,sans-serif;margin:2rem;max-width:36rem;line-height:1.45}" +
    "h1{font-size:1.25rem}code{background:#f3f4f6;padding:.1rem .35rem;border-radius:.25rem}</style>" +
    "</head><body><h1>" + title + "</h1><p>" + detail + "</p>" +
    "<p>En <code>project_web</code> ejecutá:</p>" +
    "<p><code>python run.py</code></p>" +
    "<p>Después recargá esta página (Ctrl+F5).</p></body></html>";
  return new Response(html, {
    status: 503,
    headers: { "Content-Type": "text/html; charset=utf-8", "Cache-Control": "no-store" },
  });
}

function isLiveDataRequest(url, request) {
  var path = url.pathname || "";
  // Cronómetros / JSON de planta: si se cachean, el celular queda en rojo aunque la PC ya esté bien.
  if (path.indexOf("/produccion/cronometros/estado") === 0) return true;
  if (path.indexOf("/api/") === 0) return true;
  var accept = (request.headers.get("Accept") || "").toLowerCase();
  if (accept.indexOf("application/json") !== -1) return true;
  return false;
}

function networkOnly(request) {
  return fetch(request);
}

function networkFirstThenCache(request) {
  return fetch(request).then(function (response) {
    if (response && response.status === 200 && response.type === "basic") {
      var copy = response.clone();
      caches.open(CACHE).then(function (cache) {
        cache.put(request, copy);
      });
    }
    return response;
  }).catch(function () {
    return caches.match(request);
  });
}

self.addEventListener("fetch", function (event) {
  if (event.request.method !== "GET") return;

  var url;
  try {
    url = new URL(event.request.url);
  } catch (e) {
    return;
  }
  if (url.origin !== self.location.origin) return;

  if (isLiveDataRequest(url, event.request)) {
    event.respondWith(networkOnly(event.request));
    return;
  }

  if (event.request.mode === "navigate") {
    event.respondWith(
      fetch(event.request).catch(function () {
        var path = url.pathname || "/";
        if (path === "/login" || path.indexOf("/login") === 0) {
          return offlineShell(
            "Servidor local apagado",
            "No se pudo abrir el inicio de sesión porque la app local no está corriendo."
          );
        }
        return offlineShell(
          "Servidor local apagado",
          "No se pudo abrir <code>" + path + "</code> porque la app local no está corriendo. Arrancá <code>python run.py</code> y recargá (Ctrl+F5)."
        );
      })
    );
    return;
  }

  var path = url.pathname || "";
  if (path.indexOf("/static/css/") === 0 || path.indexOf("/static/js/") === 0) {
    event.respondWith(networkFirstThenCache(event.request));
    return;
  }

  if (path.indexOf("/static/") === 0) {
    event.respondWith(
      caches.match(event.request).then(function (cached) {
        if (cached) return cached;
        return fetch(event.request).then(function (response) {
          if (!response || response.status !== 200 || response.type !== "basic") {
            return response;
          }
          var copy = response.clone();
          caches.open(CACHE).then(function (cache) {
            cache.put(event.request, copy);
          });
          return response;
        });
      })
    );
    return;
  }

  event.respondWith(networkOnly(event.request));
});
