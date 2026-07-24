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
/* v10: SW-01 PII 캐시 봉쇄 + subject purge. (1) network-first API 응답은 서버가
   Cache-Control:no-store 를 실었으면(고객명/전화/주소 등 PII) CacheStorage 에 저장하지
   않는다(responseForbidsStore 게이트). (2) 로그인 사용자(subject) 변경/logout 시 페이지가
   postMessage 로 통지하면 -api 캐시를 purge 해 공유 기기에서 이전 사용자 PII 잔존을 0 으로
   만든다. (3) network-first 는 cold miss(캐시 없음)에서도 timeout 후 합성 offline 응답으로
   반드시 settle 해 respondWith 무한 미해결(G3 무한 스피너)을 봉합한다. CACHE_VERSION bump 은
   activate 시 구 foms-p2-v9-api(=이전 PII 스냅샷) 캐시를 전량 purge 한다. offline mutation
   은 계속 OFF(쓰기 큐 미도입). rollback: CACHE_VERSION 을 "foms-p2-v9" 로 되돌리고 본 커밋
   revert. */
var CACHE_VERSION = "foms-p2-v10";
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

  // 교차 출처(cross-origin)는 SW 가 절대 가로채지 않는다. 근본 이유: no-cors 교차 출처
  // 응답은 opaque(status 0)라 staticNetwork 가 이를 transient 서버 오류로 분류해
  // 400ms+800ms backoff 재시도를 돌고(=요청당 +1.2초), response.ok 가 false 라
  // cache.put 도 못 해 영구히 캐시되지 않는다. 카카오 지도 타일(mts.daumcdn.net/**.png)이
  // 정확히 이 경로에 걸려 타일 1장당 37ms → 1243ms(33배)가 됐고, 확대·축소마다 전량
  // 재발생해 "지도가 계속 재로딩"으로 보였다(로컬 실측 2026-07-21, SW on/off A/B).
  // 교차 출처 자산은 브라우저 HTTP 캐시가 이미 처리한다(카카오 타일 max-age=21600).
  if (url.origin !== self.location.origin) return;

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

// 정적 자산 네트워크 취득(캐시 미스/만료 시 공용). 두 종류의 transient 실패를 흡수한다:
//  (A) fetch reject: 한국↔싱가포르 tail 구간의 TCP reset/혼잡 → 첫 fetch 가 reject.
//  (B) HTTP 에러 resolve: fetch 가 5xx/opaque 응답으로 **resolve** 하는 경우. Railway
//      롤링 재배포 중 502/503 이 정확히 이 경로다. 이때 .catch(reject 전용)를 안 타므로
//      기존 코드는 그 에러 응답을 그대로 반환 → render-blocking CSS 가 통째로 죽었다
//      (무스타일 렌더). (A)만 막던 종전 재시도의 잔존 구멍이었다.
// 근본 수정: (A)reject 와 (B)5xx/opaque 를 동일 취급 — 캐시 폴백이 있으면 즉시 폴백,
// 없으면 짧은 backoff 로 유한 재시도(400/800ms)하고 성공 시 캐시에 저장한다.
// 재시도를 소진해도 폴백이 없으면:
//   · (B) 마지막 응답(5xx 등)을 그대로 반환 — 4xx/최종 5xx 는 정직한 서버 상태라
//     브라우저에 전달한다(throw 아님).
//   · (A) 반환할 응답이 없으므로 정직하게 reject 를 전파(브라우저 기본 에러 처리).
// 4xx 는 정직한 응답이므로 재시도 없이 그대로 전달한다. 어떤 경로도 undefined 로 resolve
// 하지 않는다. 유한 재시도라 respondWith 무한 미해결(G3 무한 스피너)과는 무관하다.
var STATIC_NETWORK_RETRIES = 2; // 첫 시도 후 최대 2회 추가 재시도
var STATIC_RETRY_BACKOFF_MS = 400; // 재시도 간 backoff(선형 증가: 400ms, 800ms)

function staticNetwork(request, cache, cached) {
  var attempt = 0;
  // reject / 5xx·opaque 를 유한 재시도로 흡수하는 공용 폴백 경로.
  // cached 있으면 즉시 폴백. 재시도 소진 시 lastResponse(5xx 응답)면 그대로 반환,
  // 없으면(reject) rejectErr 전파 — 절대 undefined 로 resolve 하지 않는다.
  function retryOr(lastResponse, rejectErr) {
    if (cached) return cached;
    if (attempt < STATIC_NETWORK_RETRIES) {
      attempt += 1;
      return new Promise(function (resolve) {
        setTimeout(resolve, STATIC_RETRY_BACKOFF_MS * attempt);
      }).then(attemptFetch);
    }
    if (lastResponse) return lastResponse; // 4xx/최종 5xx: 정직한 서버 상태 그대로 전달.
    throw rejectErr || new TypeError("[foms-sw] static fetch failed");
  }
  function attemptFetch() {
    return fetch(request)
      .then(function (response) {
        // 성공(ok): 캐시에 저장하고 반환(기존 동작 보존).
        if (response && response.ok) {
          cache.put(request, response.clone());
          return response;
        }
        // HTTP 에러 게이트: 5xx/opaque(status 0 또는 type 'error')는 transient 로
        // 보고 reject 와 동일 취급(폴백/재시도). 4xx 는 정직한 응답이라 그대로 전달.
        var status = response ? response.status : 0;
        var isTransientServerErr =
          status >= 500 || status === 0 || (response && response.type === "error");
        if (isTransientServerErr) return retryOr(response, null);
        return response; // 4xx: 재시도 없이 그대로
      })
      .catch(function (err) {
        // fetch reject(오프라인/TCP reset/혼잡): 폴백/유한 재시도(기존 동작 보존).
        return retryOr(null, err);
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

// PII 봉쇄 게이트: 서버가 Cache-Control:no-store 를 실은 응답(고객명/전화/주소 등 PII 를
// 담는 API)은 CacheStorage 에 절대 저장하지 않는다. 표준 헤더라 no-store 를 다는 어떤
// same-origin API 든 자동으로 커버된다(엔드포인트별 하드코딩 불필요). 응답이 없거나 헤더가
// 없으면 보수적으로 '저장 금지'로 본다(fail-closed).
function responseForbidsStore(response) {
  if (!response) return true;
  var cc = response.headers ? response.headers.get("cache-control") : null;
  return !!cc && /no-store/i.test(cc);
}

// respondWith 가 절대 undefined/미해결로 남지 않도록 하는 최종 합성 응답. cold miss(캐시
// 없음)에서 네트워크가 지연/행(hang)될 때 timeout 이 이 응답으로 settle 해 무한 스피너를
// 원천 차단한다(G3). 503 이므로 캐시에 저장되지 않는다.
function offlineFallbackResponse() {
  return new Response(
    JSON.stringify({ success: false, error: "offline", data: [] }),
    { status: 503, headers: { "Content-Type": "application/json" } }
  );
}

// network-first API 계약:
//  · 성공(ok) 이고 저장 허용(no-store 아님)일 때만 CacheStorage 에 저장(PII 봉쇄).
//  · 네트워크가 NETWORK_FIRST_TIMEOUT_MS 를 넘기면 캐시본으로 폴백. 캐시본이 없으면
//    (cold miss) 합성 offline 응답으로 settle — respondWith 가 미해결로 남지 않는다
//    (cold miss ≤ timeout, G3 무한 스피너 봉합). 구 코드는 timeout 이 `if(cached)` 일
//    때만 settle 해 cold miss + 행 네트워크에서 respondWith 가 영원히 미해결이었다.
//  · 어떤 경로도 undefined 로 resolve 하지 않는다.
function networkFirstQueue(request) {
  var networkPromise = fetch(request)
    .then(function (response) {
      if (response && response.ok && !responseForbidsStore(response)) {
        return caches.open(API_CACHE).then(function (cache) {
          cache.put(request, response.clone());
          return response;
        });
      }
      return response; // no-store 이거나 에러 응답: 저장하지 않고 그대로 전달.
    })
    .catch(function () {
      return caches.match(request); // 네트워크 실패: 캐시 폴백(없으면 undefined).
    });

  if (!(NETWORK_FIRST_TIMEOUT_MS > 0)) {
    return networkPromise.then(function (resp) {
      return resp || offlineFallbackResponse();
    });
  }

  return new Promise(function (resolve) {
    var settled = false;
    function settle(resp) {
      if (settled) return;
      settled = true;
      resolve(resp || offlineFallbackResponse());
    }
    var timer = setTimeout(function () {
      // 캐시본 있으면 즉시 폴백; cold miss 면 settle(undefined)→합성 응답으로 마감.
      caches.match(request).then(function (cached) {
        settle(cached);
      });
    }, NETWORK_FIRST_TIMEOUT_MS);
    networkPromise.then(function (resp) {
      clearTimeout(timer);
      settle(resp);
    });
  });
}

/* ===========================================================================
 * Subject(로그인 사용자) 변경 시 API 캐시 purge — 공유 기기에서 이전 사용자의 캐시
 * 데이터가 다음 사용자에게 노출되지 않게 한다. PII API 는 no-store 로 애초에 캐시되지
 * 않지만(1차 방어), 이 purge 는 캐시명 잔존·향후 비-PII 캐시까지 훑어 지우는 2차 방어다.
 * 페이지(sync.js)가 로드 시 현재 subject 를, 로그아웃 시 purge 를 postMessage 한다.
 * =========================================================================== */
var _currentSubject; // SW 수명 내 마지막으로 관측한 subject(재시작 시 undefined).

function purgeApiCaches() {
  return caches.keys().then(function (keys) {
    return Promise.all(
      keys
        .filter(function (key) {
          return /-api$/.test(key); // -api 로 끝나는 캐시만(정적 캐시는 보존).
        })
        .map(function (key) {
          return caches.delete(key);
        })
    );
  });
}

self.addEventListener("message", function (event) {
  var data = (event && event.data) || {};
  if (data.type === "foms-purge-api-cache") {
    event.waitUntil(purgeApiCaches());
    return;
  }
  if (data.type === "foms-subject") {
    var subject = data.subject == null ? "" : String(data.subject);
    // 첫 관측(SW 재시작 직후 _currentSubject === undefined)은 purge 하지 않는다
    // (no-store 가 PII 를 이미 봉쇄). 관측된 subject 가 바뀌면(전환/재로그인/로그아웃)
    // 이전 사용자 캐시를 purge 한다.
    if (_currentSubject !== undefined && _currentSubject !== subject) {
      event.waitUntil(purgeApiCaches());
    }
    _currentSubject = subject;
  }
});

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

  // 발신 계약(push_sender._build_payload): notification_id/deep_link 는 payload.data.*
  // 에 nested 로 실린다. nested 를 우선 읽고, 없으면 구(top-level) 발신본과의 호환을 위해
  // top-level 로 fallback 한다(계약 정본=nested, top-level=legacy fallback).
  var pushData = (payload && typeof payload.data === "object" && payload.data) || {};
  var notificationId =
    pushData.notification_id != null
      ? pushData.notification_id
      : payload.notification_id != null
      ? payload.notification_id
      : null;
  var deepLink =
    pushData.deep_link ||
    pushData.deep_link_url ||
    payload.deep_link ||
    payload.deep_link_url ||
    null;

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
      notification_id: notificationId,
      deep_link: deepLink
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
