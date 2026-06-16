/* P2-03 Service Worker — queue snapshot + static stale-while-revalidate (new surfaces).
 * CACHE_VERSION bumped to v2: the v1 caches were populated while /static was served
 * 1-year-immutable, so they hold stale CSS/JS. Bumping purges them on activate; going
 * forward the origin serves CSS/JS as no-cache so revalidation keeps them fresh. */
var CACHE_VERSION = "foms-p2-v4";
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
    // CSS/JS: network-first with revalidation so a deploy's edits (incl. @import-ed
    // sub-files that lack a ?v= cache-buster) reach the client on the next load
    // instead of being pinned to a stale copy. Falls back to cache when offline.
    if (/\.(css|js)(\?|$)/i.test(url.pathname)) {
      event.respondWith(networkFirst(req, STATIC_CACHE));
    } else {
      event.respondWith(staleWhileRevalidate(req, STATIC_CACHE));
    }
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

// 네트워크 응답이 이 시간을 넘기면 캐시본으로 즉시 응답한다(탭 로딩 스피너 무한
// 회전 방지). 네트워크 fetch는 백그라운드로 계속 진행되어 캐시를 갱신하므로
// 다음 로드는 최신본을 받는다(신선도 유지). 0/음수면 타임아웃 비활성.
var NETWORK_FIRST_TIMEOUT_MS = 3000;

function networkFirst(request, cacheName) {
  // cache:"no-cache" forces a conditional request even for entries the browser
  // still considers fresh (the legacy 1-year-immutable CSS/JS), so a stale copy
  // can't win. 304 keeps it cheap; the fresh body is cached for offline use.
  //
  // 타임아웃 없이 fetch가 (에러가 아니라) 느리게 지연되면 respondWith가 영원히
  // 미해결 → 페이지는 떴어도 탭 스피너가 계속 돈다. 그래서 네트워크를 캐시본과
  // 경주시키고, 느리면 캐시로 빠르게 응답한다. 네트워크 결과는 백그라운드로
  // 캐시에 반영되어 다음 로드의 신선도를 보장한다.
  var networkPromise = fetch(request, { cache: "no-cache" })
    .then(function (response) {
      if (response && response.ok) {
        // Clone synchronously, before returning the response to the page. If we
        // cloned inside the async caches.open().then() the page may have already
        // consumed the body → "Failed to execute 'clone': body is already used".
        var copy = response.clone();
        caches.open(cacheName).then(function (cache) {
          cache.put(request, copy);
        });
      }
      return response;
    })
    .catch(function () {
      return caches.match(request);
    });

  if (!(NETWORK_FIRST_TIMEOUT_MS > 0)) {
    return networkPromise;
  }

  return new Promise(function (resolve) {
    var settled = false;
    function settle(resp) {
      if (settled) return;
      settled = true;
      resolve(resp);
    }
    var timer = setTimeout(function () {
      // 네트워크가 느림 → 캐시본이 있으면 즉시 응답(스피너 종료). 캐시가 없으면
      // (최초 로드 등) settle하지 않고 networkPromise 완료를 계속 기다린다.
      caches.match(request).then(function (cached) {
        if (cached) settle(cached);
      });
    }, NETWORK_FIRST_TIMEOUT_MS);
    networkPromise.then(function (resp) {
      clearTimeout(timer);
      // 타임아웃으로 이미 캐시 응답했더라도 위 .then이 캐시를 갱신했으므로 OK.
      settle(resp);
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
