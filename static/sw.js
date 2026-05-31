/* P2-03 Service Worker — queue snapshot + static stale-while-revalidate (new surfaces). */
var CACHE_VERSION = "foms-p2-v1";
var STATIC_CACHE = CACHE_VERSION + "-static";
var API_CACHE = CACHE_VERSION + "-api";

var STATIC_URLS = [
  "/static/js/vendor/htmx.min.js",
  "/static/js/vendor/alpine.min.js",
  "/static/manifest.json",
];

self.addEventListener("install", function (event) {
  event.waitUntil(
    caches.open(STATIC_CACHE).then(function (cache) {
      return cache.addAll(STATIC_URLS);
    })
  );
  self.skipWaiting();
});

self.addEventListener("activate", function (event) {
  event.waitUntil(
    caches.keys().then(function (keys) {
      return Promise.all(
        keys
          .filter(function (key) {
            return key.indexOf("foms-p2-") === 0 && key.indexOf(CACHE_VERSION) !== 0;
          })
          .map(function (key) {
            return caches.delete(key);
          })
      );
    })
  );
  self.clients.claim();
});

self.addEventListener("fetch", function (event) {
  var req = event.request;
  var url = new URL(req.url);

  if (req.method !== "GET") return;

  if (url.pathname.indexOf("/static/") === 0) {
    event.respondWith(staleWhileRevalidate(req, STATIC_CACHE));
    return;
  }

  if (url.pathname === "/api/foms/offline/queue") {
    event.respondWith(networkFirstQueue(req));
    return;
  }

  if (/\.(png|jpg|jpeg|webp|gif)(\?|$)/i.test(url.pathname)) {
    event.respondWith(staleWhileRevalidate(req, STATIC_CACHE));
  }
});

function staleWhileRevalidate(request, cacheName) {
  return caches.open(cacheName).then(function (cache) {
    return cache.match(request).then(function (cached) {
      var network = fetch(request)
        .then(function (response) {
          if (response && response.ok) cache.put(request, response.clone());
          return response;
        })
        .catch(function () {
          return cached;
        });
      return cached || network;
    });
  });
}

function networkFirstQueue(request) {
  return fetch(request)
    .then(function (response) {
      if (response && response.ok) {
        return caches.open(API_CACHE).then(function (cache) {
          cache.put(request, response.clone());
          return response;
        });
      }
      return response;
    })
    .catch(function () {
      return caches.match(request);
    });
}
