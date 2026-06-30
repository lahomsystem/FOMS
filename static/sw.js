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

  if (isFileDeliveryRequest(url)) {
    return;
  }

  if (url.pathname.indexOf("/static/") === 0) {
    // CSS/JS: 캐시 우선(즉시 응답) + TTL 지난 경우에만 백그라운드 재검증.
    // 과거 networkFirst(+cache:no-cache)는 매 네비게이션마다 ~90개 css/js를 서버에
    // 강제 재요청 → 2 vCPU 워커가 못 따라가 탭 전환이 2~5초로 들쭉날쭉했다(운영 실측).
    // staticCacheFirst는 TTL(기본 5분) 내에는 서버 요청을 보내지 않아 그 부하를 없애고,
    // 신선도는 TTL 창 + 배포 시 ?v= 변경 URL(캐시 미스→즉시 최신)로 보장한다.
    if (/\.(css|js)(\?|$)/i.test(url.pathname)) {
      event.respondWith(staticCacheFirst(req, STATIC_CACHE));
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

function isFileDeliveryRequest(url) {
  if (url.pathname.indexOf("/api/files/") === 0) return true;
  if (/\.(?:r2\.)?cloudflarestorage\.com$/i.test(url.hostname)) return true;
  return url.searchParams.has("X-Amz-Signature") || url.searchParams.has("Signature");
}

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

// CSS/JS 재검증 스로틀(초). 캐시본을 즉시 응답하고, 캐시가 이 시간보다 오래된
// 경우에만 백그라운드로 재검증한다. TTL 이내면 서버 요청을 아예 안 보내므로
// 매 네비게이션의 ~90개 정적 요청이 2 vCPU 워커를 막던 부하가 사라진다.
var STATIC_REVALIDATE_TTL_MS = 300000; // 5분

function _cacheAgeMs(response) {
  // 캐시본의 Date 헤더로 나이 추정. 헤더 없으면 Infinity → 항상 재검증(안전 폴백).
  if (!response) return Infinity;
  var dateHdr = response.headers.get("date");
  if (!dateHdr) return Infinity;
  var t = new Date(dateHdr).getTime();
  if (!t) return Infinity;
  return Date.now() - t;
}

function staticCacheFirst(request, cacheName) {
  return caches.open(cacheName).then(function (cache) {
    return cache.match(request).then(function (cached) {
      // 신선한 캐시본이 있으면 즉시 응답하고 서버 요청을 보내지 않는다.
      if (cached && _cacheAgeMs(cached) < STATIC_REVALIDATE_TTL_MS) {
        return cached;
      }
      // 캐시가 없거나 오래됨 → 캐시본 즉시 응답 + 백그라운드 재검증(stale-while-revalidate).
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

function networkFirstQueue(request) {
  var networkPromise = fetch(request)
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
      caches.match(request).then(function (cached) {
        if (cached) settle(cached);
      });
    }, NETWORK_FIRST_TIMEOUT_MS);
    networkPromise.then(function (resp) {
      clearTimeout(timer);
      settle(resp);
    });
  });
}
