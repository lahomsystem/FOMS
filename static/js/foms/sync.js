/**
 * P2-03 offline form queue + service worker registration (default off via flag).
 */
(function () {
  "use strict";

  var DB_NAME = "foms-offline-v1";
  var STORE = "pending-writes";

  function openDb() {
    return new Promise(function (resolve, reject) {
      var req = indexedDB.open(DB_NAME, 1);
      req.onupgradeneeded = function () {
        req.result.createObjectStore(STORE, { keyPath: "id", autoIncrement: true });
      };
      req.onsuccess = function () {
        resolve(req.result);
      };
      req.onerror = function () {
        reject(req.error);
      };
    });
  }

  window.fomsOfflineQueueWrite = function (entry) {
    return openDb().then(function (db) {
      return new Promise(function (resolve, reject) {
        var tx = db.transaction(STORE, "readwrite");
        tx.objectStore(STORE).add(
          Object.assign({ createdAt: Date.now() }, entry || {})
        );
        tx.oncomplete = function () {
          resolve(true);
        };
        tx.onerror = function () {
          reject(tx.error);
        };
      });
    });
  };

  window.fomsOfflineEnabled = function () {
    if (window.FOMS_OFFLINE_SW_ENABLED === true) {
      return true;
    }
    return !!document.querySelector("[data-offline-sw='true']");
  };

  window.fomsOfflineEnqueueRequest = function (url, options) {
    if (!window.fomsOfflineEnabled() || !window.fomsOfflineQueueWrite) {
      return Promise.reject(new Error("offline queue disabled"));
    }
    options = options || {};
    return window.fomsOfflineQueueWrite({
      url: url,
      method: options.method || "GET",
      headers: options.headers || {},
      body: options.body || null,
    });
  };

  function flushQueue() {
    if (!navigator.onLine) return Promise.resolve(0);
    return openDb().then(function (db) {
      return new Promise(function (resolve) {
        var tx = db.transaction(STORE, "readwrite");
        var store = tx.objectStore(STORE);
        var req = store.getAll();
        req.onsuccess = function () {
          var items = req.result || [];
          var failed = false; // B7: flush 실패(전송 실패 배지) 신호.
          var chain = Promise.resolve();
          items.forEach(function (item) {
            chain = chain.then(function () {
              return fetch(item.url, {
                method: item.method || "PUT",
                headers: item.headers || { "Content-Type": "application/json" },
                body: item.body || null,
                credentials: "same-origin",
              }).then(function (res) {
                if (res.ok) store.delete(item.id);
                else failed = true;
              });
            });
          });
          chain.then(function () {
            // B7: flush 결과를 sync 배지에 통지(기존 flush 로직 무변경, 이벤트 발행만).
            try {
              window.dispatchEvent(new CustomEvent("foms:sync-changed", {
                detail: { source: "flush", failed: failed },
              }));
            } catch (e) {
              /* CustomEvent 미지원 — 배지 갱신 생략(무해). */
            }
            resolve(items.length);
          });
        };
      });
    });
  }

  // SW 등록 SSOT — 전 페이지(데스크톱 포함)에서 이 helper 한 곳만
  // navigator.serviceWorker.register 를 호출한다(a2hs-prompt / mobile-push 는 경유).
  // Promise<ServiceWorkerRegistration|null> 을 반환하고, 진행 중/완료된 등록
  // Promise 를 window 스코프에 캐시해 중복 register 와 fragment 재실행 재등록을 막는다.
  // offline flag 와 독립적으로 호출 가능(web push 켜기 flow 가 직접 확보).
  window.fomsRegisterServiceWorker = function () {
    if (!("serviceWorker" in navigator)) return Promise.resolve(null);
    if (window.__fomsSwRegistrationPromise) return window.__fomsSwRegistrationPromise;
    window.__fomsSwRegistrationPromise = navigator.serviceWorker
      .register("/static/sw.js", { scope: "/" })
      .then(function (registration) {
        // 구 SW 잔존 창 단축(iOS 완화): register() 는 기존 등록이 있으면 그대로 반환하므로
        // update() 로 새 sw.js 바이트 검사를 명시 트리거해야 구 SW 가 브라우저 기본 갱신
        // 주기까지 살아남는 창(무스타일 렌더 잔존 구멍 2)을 단축한다. best-effort —
        // 실패해도 등록 자체는 유효하므로 삼킨다(등록 SSOT 는 그대로 register 1회 유지).
        if (registration && typeof registration.update === "function") {
          Promise.resolve(registration.update()).catch(function () {
            /* 갱신 실패는 등록 유효성과 무관 — 무시 */
          });
        }
        return registration;
      })
      .catch(function (err) {
        // 실패 시 캐시를 비워 다음 호출에서 재시도 가능하게 한다(무등록 방지).
        window.__fomsSwRegistrationPromise = null;
        console.warn("[foms-sync] service worker registration failed", err);
        return null;
      });
    return window.__fomsSwRegistrationPromise;
  };

  if (window.__FOMS_SYNC_BOUND) return;
  window.__FOMS_SYNC_BOUND = true;

  // Subject(로그인 사용자) 통지 — SW 가 subject 변경 시 API 캐시를 purge 한다(공유 기기에서
  // 이전 사용자 PII 잔존 0). subject 는 layout 이 노출한 #foms-sw-config[data-foms-subject]
  // 에서 읽는다. controller/구성 미노출 페이지에서는 no-op(구성 없으면 거짓 purge 방지 위해
  // 전송 생략). 로그인→다른 사용자 로그인 전이는 subject 변화로 SW 가 감지한다.
  function fomsPostSubjectToSw() {
    if (!("serviceWorker" in navigator)) return;
    var cfg = document.getElementById("foms-sw-config");
    if (!cfg) return;
    var controller = navigator.serviceWorker.controller;
    if (!controller) return;
    controller.postMessage({
      type: "foms-subject",
      subject: cfg.getAttribute("data-foms-subject") || "",
    });
  }

  document.addEventListener("DOMContentLoaded", fomsPostSubjectToSw);
  if ("serviceWorker" in navigator) {
    // 새 SW 가 제어권을 잡는 순간(controller null→활성)에도 subject 를 재통지한다.
    navigator.serviceWorker.addEventListener("controllerchange", fomsPostSubjectToSw);
  }

  window.addEventListener("online", function () {
    flushQueue().then(function (count) {
      if (count && window.fomsShowToast) {
        window.fomsShowToast("오프라인 변경 " + count + "건 동기화");
      }
    });
  });

  document.addEventListener("DOMContentLoaded", function () {
    var root = document.querySelector("[data-erp-mobile-shell][data-offline-sw='true']");
    if (!root) return;
    window.fomsRegisterServiceWorker();
  });
})();
