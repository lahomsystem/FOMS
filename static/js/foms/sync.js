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
              });
            });
          });
          chain.then(function () {
            resolve(items.length);
          });
        };
      });
    });
  }

  window.fomsRegisterServiceWorker = function () {
    if (!("serviceWorker" in navigator)) return Promise.resolve(false);
    return navigator.serviceWorker.register("/static/sw.js", { scope: "/" }).then(function () {
      return true;
    }).catch(function () {
      return false;
    });
  };

  if (window.__FOMS_SYNC_BOUND) return;
  window.__FOMS_SYNC_BOUND = true;

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
