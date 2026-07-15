/* P2-03 Service Worker — queue snapshot + static stale-while-revalidate (new surfaces).
 * CACHE_VERSION bumped to v2: the v1 caches were populated while /static was served
 * 1-year-immutable, so they hold stale CSS/JS. Bumping purges them on activate; going
 * forward the origin serves CSS/JS as no-cache so revalidation keeps them fresh. */
/* v7: 데스크톱 SW 전역 등록 + erp-shell 하트비트(Wave 4) 배포 — 구 staticCacheFirst 캐시 purge. */
/* v8: Web Push(Phase 3B) push/notificationclick/notificationclose 핸들러 추가 —
   install/activate/fetch 로직은 무변경. 캐시 버전만 bump 해 구 캐시를 activate 시 purge.
   rollback: CACHE_VERSION 을 "foms-p2-v7" 로 되돌리면 됨(핸들러는 fetch 계약과 독립이라
   무해하게 남지만, 완전 롤백은 이 커밋 revert). */
/* v9: 태블릿 실측 우측 패널 stale-JS 봉합 — 근본원인 = tablet-measurement.js 의 동작이
   fragment 주입(구)→전용 폼 위임(신)으로 바뀌었는데 ?v 캐시버스터가 20260714a 그대로였다
   (커밋 52fb78b7→ce57d4f2, 두 커밋 모두 ?v=20260714a). staticCacheFirst 는 같은 ?v 키의
   캐시본을 즉시 응답(stale-while-revalidate)하므로, 리로드 시 구 fragment-주입 컨트롤러가
   실행돼 우측 패널에 PC erp_order_tab 폼이 주입됐다. CACHE_VERSION bump 은 activate 시
   구 foms-p2-* 정적 캐시(오염된 tablet-measurement.js?v=20260714a 포함)를 전량 purge 해
   다음 로드에서 최신본을 강제 미스→네트워크 취득하게 한다. 재발 방지는 "파일 내용 변경 시
   ?v 반드시 bump"(SW 신선도 계약) — 본 배포는 폼 전면 재작성으로 관련 ?v 가 함께 bump 된다. */
var CACHE_VERSION = "foms-p2-v9";
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

// 정적 자산 네트워크 취득(캐시 미스/만료 시 공용). 한국↔싱가포르 경로의 tail 구간에서
// 첫 fetch 가 간헐적으로 reject(TCP reset/혼잡) 하면, 캐시 폴백이 없을 때 기존 코드가
// undefined 로 resolve → event.respondWith(undefined) → render-blocking CSS 가 통째로
// 실패(무스타일 렌더)했다(배포 직후 ?v 신규 URL·CACHE_VERSION 범프로 캐시가 비어 특히 빈발).
// 근본 수정: 캐시 폴백이 없을 때는 요청을 죽이지 말고 짧은 backoff 로 유한 재시도해
// transient reject 를 흡수하고 성공 시 캐시에 저장한다. 캐시 폴백이 있으면(오프라인/stale)
// 재시도 없이 즉시 폴백한다(기존 동작 유지). 재시도를 소진해도 폴백이 없으면 정직하게
// reject 를 전파(브라우저 기본 에러 처리) — 절대 undefined 로 resolve 하지 않는다.
// 유한 재시도라 respondWith 무한 미해결(G3 무한 스피너)과는 무관하다.
var STATIC_NETWORK_RETRIES = 2; // 첫 시도 후 최대 2회 추가 재시도
var STATIC_RETRY_BACKOFF_MS = 400; // 재시도 간 backoff(선형 증가: 400ms, 800ms)

function staticNetwork(request, cache, cached) {
  var attempt = 0;
  function attemptFetch() {
    return fetch(request)
      .then(function (response) {
        if (response && response.ok) cache.put(request, response.clone());
        return response;
      })
      .catch(function (err) {
        // 캐시 폴백이 있으면 즉시 폴백(오프라인/네트워크 단절 정상 경로) — 재시도 불필요.
        if (cached) return cached;
        // 폴백이 없으면 transient reject 를 유한 재시도로 흡수(무스타일 렌더 방지).
        if (attempt < STATIC_NETWORK_RETRIES) {
          attempt += 1;
          return new Promise(function (resolve) {
            setTimeout(resolve, STATIC_RETRY_BACKOFF_MS * attempt);
          }).then(attemptFetch);
        }
        // 재시도 소진 + 폴백 없음 → 정직하게 실패 전파(undefined resolve 금지).
        throw err;
      });
  }
  return attemptFetch();
}

function staleWhileRevalidate(request, cacheName) {
  return caches.open(cacheName).then(function (cache) {
    return cache.match(request).then(function (cached) {
      var network = staticNetwork(request, cache, cached);
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
      // 캐시본이 있으면(오래됨) 즉시 응답 + 백그라운드 재검증(stale-while-revalidate).
      // 캐시가 없으면(첫 로드/배포 직후 미스) staticNetwork 가 유한 재시도로 취득한다 —
      // transient reject 를 undefined 로 삼켜 무스타일 렌더를 유발하던 경로를 봉합한다.
      var network = staticNetwork(request, cache, cached);
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

/* ===========================================================================
 * Web Push (Phase 3B) — push 수신 → 알림 표시, 클릭/닫힘 처리.
 * install/activate/fetch 로직과 독립. 서버 이벤트 보고는 best-effort(실패 무시).
 * =========================================================================== */

// 기존 manifest 아이콘 재사용(별도 자산 추가 없음).
var PUSH_DEFAULT_ICON = "/static/icons/foms-icon-192.png";
var PUSH_DEFAULT_BADGE = "/static/icons/foms-icon-192.png";
// deep link 검증 실패 시 안전 폴백 경로.
var PUSH_FALLBACK_DEEP_LINK = "/erp/dashboard";
// 곧 추가될 서버 엔드포인트(다른 워커). 미존재해도 SW 동작이 죽으면 안 되므로
// best-effort 로만 호출하고 실패는 console.debug 로 흘린다.
var PUSH_EVENT_URL = "/erp/api/notifications/push/event";

self.addEventListener("push", function (event) {
  var payload = {};
  if (event.data) {
    try {
      payload = event.data.json() || {};
    } catch (e) {
      // JSON 파싱 실패 → text 폴백(그마저 실패하면 generic).
      try {
        payload = { body: event.data.text() };
      } catch (e2) {
        payload = {};
      }
    }
  }

  var title = payload.title || "FOMS 알림";
  var options = {
    body: payload.body || "",
    icon: payload.icon || PUSH_DEFAULT_ICON,
    badge: payload.badge || PUSH_DEFAULT_BADGE,
    tag: payload.tag || undefined,
    renotify: payload.renotify === true,
    requireInteraction: payload.requireInteraction === true,
    // vibrate 는 best-effort(미지원 브라우저는 무시).
    vibrate: payload.vibrate || [80, 40, 80],
    data: {
      notification_id: payload.notification_id != null ? payload.notification_id : null,
      deep_link: payload.deep_link || payload.deep_link_url || null
    }
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// deep link allowlist: same-origin 이면서 '/erp/' 로 시작하는 경로만 허용.
// 그 외(교차 출처, 임의 경로, javascript: 등)는 대시보드로 폴백한다(오픈 리다이렉트 차단).
function sanitizePushDeepLink(rawLink) {
  if (!rawLink || typeof rawLink !== "string") return PUSH_FALLBACK_DEEP_LINK;
  var target;
  try {
    target = new URL(rawLink, self.location.origin);
  } catch (e) {
    return PUSH_FALLBACK_DEEP_LINK;
  }
  if (target.origin !== self.location.origin) return PUSH_FALLBACK_DEEP_LINK;
  if (target.pathname.indexOf("/erp/") !== 0) return PUSH_FALLBACK_DEEP_LINK;
  return target.pathname + target.search + target.hash;
}

// 서버 이벤트 보고(best-effort). 엔드포인트 미존재/네트워크 실패해도 UX 를 막지 않는다.
function reportPushEvent(notificationId, eventName) {
  if (notificationId == null) return Promise.resolve();
  return fetch(PUSH_EVENT_URL, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      "X-FOMS-Notification-Write": "1"
    },
    body: JSON.stringify({ notification_id: notificationId, event: eventName })
  })
    .then(function () {
      /* best-effort: 응답 무시 */
    })
    .catch(function (err) {
      console.debug("[foms-sw] push event report skipped", err);
    });
}

self.addEventListener("notificationclick", function (event) {
  var notification = event.notification;
  notification.close();
  var data = notification.data || {};
  var url = sanitizePushDeepLink(data.deep_link);

  event.waitUntil(
    clients.matchAll({ type: "window", includeUncontrolled: true }).then(function (clientList) {
      for (var i = 0; i < clientList.length; i++) {
        var client = clientList[i];
        if ("focus" in client) {
          client.focus();
          if ("navigate" in client) {
            try {
              client.navigate(url);
            } catch (e) {
              /* navigate 실패해도 focus 는 유지 */
            }
          }
          return reportPushEvent(data.notification_id, "opened");
        }
      }
      var opened = clients.openWindow ? clients.openWindow(url) : null;
      return Promise.resolve(opened).then(function () {
        return reportPushEvent(data.notification_id, "opened");
      });
    })
  );
});

self.addEventListener("notificationclose", function (event) {
  var data = (event.notification && event.notification.data) || {};
  // 닫힘 보고는 best-effort — 실패 무시(console.debug), UX 차단 금지.
  event.waitUntil(reportPushEvent(data.notification_id, "closed"));
});
