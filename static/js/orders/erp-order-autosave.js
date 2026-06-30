/**
 * ERP Order 자동저장 (add_order 전용).
 *
 * 2계층 안전망:
 *  - localStorage 즉시 미러(700ms debounce): 같은 기기 새로고침/탭이탈/크래시 복구. DB 비용 0.
 *  - 서버 draft 자동저장(2.5s debounce + blur + beforeunload beacon): 교차기기/스토리지 청소 생존.
 *    의미 있는 내용이 있을 때만 서버 draft를 생성/갱신한다(빈 draft row 폭증 방지).
 *
 * 승격(명시 저장)은 기존 PUT /orders/<id>/structured(erpSaveStructured)가 담당한다.
 * 자동저장 엔드포인트(/orders/erp/draft/autosave)는 검증·단계전환·side-effect 없이
 * 부분 입력만 보존한다.
 *
 * 재실행 안전(idempotent): window.__ERP_AUTOSAVE_BOUND 싱글톤 가드.
 */
(function () {
  "use strict";

  if (window.__ERP_AUTOSAVE_BOUND) return;

  var LS_KEY_PREFIX = "foms:erp-add-autosave:v1";
  var LEGACY_LS_KEY = LS_KEY_PREFIX;
  var LOCAL_DEBOUNCE_MS = 700;
  var SERVER_DEBOUNCE_MS = 2500;
  var AUTOSAVE_URL = "/api/orders/erp/draft/autosave";
  var GET_DRAFT_URL = "/api/orders/erp/draft";
  var DISCARD_URL = "/api/orders/erp/draft/discard";

  var _localTimer = null;
  var _serverTimer = null;
  var _lastServerJson = null;
  var _started = false;
  // 명시 저장(erp:order-saved) 후 자동저장을 일시 중단한다. 저장 직후 페이지 이탈로
  // visibilitychange/beforeunload가 발화하면 saveLocal/saveEditLocal이 "방금 저장한"
  // 내용을 localStorage에 다시 써서, 다음 진입 시 정상 저장건이 미저장 복원 배너로
  // 오인되는 버그를 막는다. 사용자가 다시 입력(schedule)하면 해제한다.
  var _suspended = false;

  /** 공유 PC에서 logout 후 타 사용자 PII 노출 방지: user id별 localStorage 키. */
  function resolveCurrentUserId() {
    var cfg = document.getElementById("erp-order-config");
    if (!cfg) return "";
    var raw = (cfg.getAttribute("data-current-user-id") || "").trim();
    return raw && /^\d+$/.test(raw) ? raw : "";
  }

  function localStorageKey() {
    var uid = resolveCurrentUserId();
    return uid ? LS_KEY_PREFIX + ":u" + uid : LS_KEY_PREFIX + ":anon";
  }

  function purgeLegacyLocalStorage() {
    try {
      localStorage.removeItem(LEGACY_LS_KEY);
    } catch (e) {}
  }

  function isAddDraftMode() {
    // add_order ERP 탭(신규 draft)에서만 true.
    return (
      typeof window.isErpOrderDraftMode === "function" &&
      window.isErpOrderDraftMode() &&
      window.ERP_ORDER_ENABLED
    );
  }

  // ── edit 모드(저장된 주문 편집) ────────────────────────────────────
  // 저장된 주문을 불러와 편집할 때도 작업분을 잃지 않게 한다. 단 라이브 주문에
  // 키 입력마다 PUT하면 미완성 데이터가 대시보드에 반영되고 단계전환/이벤트가
  // 오발생하므로, 편집 자동저장은 localStorage 작업본(working copy)으로만 보존하고
  // 재진입 시 복원 배너로 되살린다. 실제 주문 반영은 '저장'(명시 PUT)이 담당한다.
  function resolvedEditOrderId() {
    var id = parseInt(String(window.ORDER_ID || "0"), 10) || 0;
    if (id > 0) return id;
    var card = document.querySelector(".card[data-erp-order-id]");
    if (card) {
      var v = parseInt(card.getAttribute("data-erp-order-id") || "0", 10) || 0;
      if (v > 0) return v;
    }
    return 0;
  }

  function isEditMode() {
    return (
      !!window.ERP_ORDER_ENABLED &&
      typeof window.isErpOrderDraftMode === "function" &&
      !window.isErpOrderDraftMode() &&
      resolvedEditOrderId() > 0
    );
  }

  function editLocalStorageKey() {
    var uid = resolveCurrentUserId();
    return LS_KEY_PREFIX + ":edit:" + (uid ? "u" + uid : "anon") + ":o" + resolvedEditOrderId();
  }

  function clearEditLocal() {
    try {
      localStorage.removeItem(editLocalStorageKey());
    } catch (e) {}
  }

  function saveEditLocal() {
    if (_suspended) return;
    if (!isEditMode()) return;
    try {
      var payload = collectPayload();
      var snap = { ts: Date.now(), order_id: resolvedEditOrderId(), edit: true, payload: payload };
      localStorage.setItem(editLocalStorageKey(), JSON.stringify(snap));
      showIndicator("✓ 자동저장됨");
    } catch (e) {
      /* quota/iOS purge: 편집 복구는 best-effort */
    }
  }

  function draftToken() {
    if (typeof window.erpGetDraftRequestToken === "function") {
      return window.erpGetDraftRequestToken();
    }
    return "";
  }

  function getVal(id) {
    var el = document.getElementById(id);
    return el ? el.value || "" : "";
  }
  function getCheck(id) {
    var el = document.getElementById(id);
    return el ? !!el.checked : false;
  }

  function constructionType() {
    if (typeof window.erpGetRegionalConstructionType === "function") {
      try {
        return window.erpGetRegionalConstructionType() || "";
      } catch (e) {
        return "";
      }
    }
    return getVal("erp-regional-construction-type");
  }

  /** 현재 폼 상태를 자동저장 payload로 직렬화. */
  function collectPayload() {
    var structured = null;
    if (typeof window.erpCollectStructured === "function") {
      try {
        structured = window.erpCollectStructured();
      } catch (e) {
        structured = null;
      }
    }
    return {
      draft_token: draftToken(),
      structured_data: structured,
      received_date: getVal("erp-received-date"),
      received_time: getVal("erp-received-time"),
      notes: getVal("erp-notes"),
      is_self_measurement: getCheck("erp-self-measurement"),
      is_regional: getCheck("erp-regional-order"),
      construction_type: constructionType(),
    };
  }

  /** 사람이 의미 있게 입력했는지(서버 draft 생성 가치 판단). 서버와 동일 기준. */
  function hasMeaningfulContent(payload) {
    if ((payload.notes || "").trim()) return true;
    var sd = payload.structured_data;
    if (!sd || typeof sd !== "object") return false;
    var cust = (sd.parties && sd.parties.customer) || {};
    var name = (cust.name || "").trim();
    var phone = (cust.phone || "").trim();
    if (name && name !== "ERP Order") return true;
    if (phone && phone !== "000-0000-0000") return true;
    var site = sd.site || {};
    var addr = (site.address_full || site.address_main || "").trim();
    if (addr && addr !== "-") return true;
    var items = sd.items || [];
    for (var i = 0; i < items.length; i++) {
      var it = items[i] || {};
      // 사용자가 실제로 채우는 필드만 본다. color/handle/misc/option_detail/internal은
      // 기본값 "상담"이 들어 있어, 포함하면 빈 폼도 "내용 있음"으로 오판 → 빈 draft가
      // 기존 draft를 덮어써 데이터 유실(production bug). product_name/spec/price만 신호.
      var keys = ["product_name", "spec", "price"];
      for (var k = 0; k < keys.length; k++) {
        if (String(it[keys[k]] || "").trim()) return true;
      }
    }
    return false;
  }

  function showIndicator(text) {
    var el = document.getElementById("erp-autosave-indicator");
    if (!el) return;
    el.textContent = text || "✓ 자동저장됨";
    el.classList.remove("d-none");
    clearTimeout(el.__hideTimer);
    el.__hideTimer = setTimeout(function () {
      el.classList.add("d-none");
    }, 2200);
  }

  // ── localStorage 계층 ──────────────────────────────────────────────
  function saveLocal() {
    if (_suspended) return;
    try {
      var payload = collectPayload();
      if (!hasMeaningfulContent(payload)) {
        // 빈 폼이면 기존 스냅샷 제거(이미 비웠으면 복원 배너 안 뜨게).
        localStorage.removeItem(localStorageKey());
        return;
      }
      var snap = {
        ts: Date.now(),
        order_id: window.ORDER_ID || 0,
        payload: payload,
      };
      localStorage.setItem(localStorageKey(), JSON.stringify(snap));
    } catch (e) {
      /* quota/iOS purge 등은 서버 계층이 커버 */
    }
  }

  function readLocal() {
    try {
      var raw = localStorage.getItem(localStorageKey());
      if (!raw) return null;
      var snap = JSON.parse(raw);
      return snap && snap.payload ? snap : null;
    } catch (e) {
      return null;
    }
  }

  function clearLocal() {
    try {
      localStorage.removeItem(localStorageKey());
    } catch (e) {}
  }

  // ── 서버 draft 계층 ────────────────────────────────────────────────
  function serverPayloadJson(payload) {
    return JSON.stringify(payload);
  }

  function saveServer() {
    if (_suspended) return;
    if (!isAddDraftMode()) return;
    var payload = collectPayload();
    if (!hasMeaningfulContent(payload) && !(window.ORDER_ID > 0)) return;
    var json = serverPayloadJson(payload);
    if (json === _lastServerJson) return; // 변경 없음 → 네트워크/DB 절약
    _lastServerJson = json;
    fetch(AUTOSAVE_URL, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: json,
    })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data && data.success) {
          if (data.order_id && typeof window.erpSetOrderId === "function" && !(window.ORDER_ID > 0)) {
            window.erpSetOrderId(data.order_id);
          }
          showIndicator("✓ 자동저장됨");
        } else {
          _lastServerJson = null; // 실패 → 다음 변화 때 재시도
        }
      })
      .catch(function () {
        _lastServerJson = null;
        if (window.fomsOfflineEnqueueRequest) {
          window.fomsOfflineEnqueueRequest(AUTOSAVE_URL, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: json,
          });
        }
      });
  }

  function beaconFlush() {
    if (_suspended) return;
    if (!isAddDraftMode()) return;
    var payload = collectPayload();
    if (!hasMeaningfulContent(payload) && !(window.ORDER_ID > 0)) return;
    var json = serverPayloadJson(payload);
    try {
      if (navigator.sendBeacon) {
        navigator.sendBeacon(AUTOSAVE_URL, new Blob([json], { type: "application/json" }));
        return;
      }
    } catch (e) {}
    try {
      fetch(AUTOSAVE_URL, {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: json,
        keepalive: true,
      });
    } catch (e) {}
  }

  // ── 입력 → 디바운스 스케줄 ─────────────────────────────────────────
  function schedule() {
    // 실제 사용자 입력은 저장 후 중단(_suspended)을 해제한다(편집 재개).
    _suspended = false;
    if (isAddDraftMode()) {
      clearTimeout(_localTimer);
      _localTimer = setTimeout(saveLocal, LOCAL_DEBOUNCE_MS);
      clearTimeout(_serverTimer);
      _serverTimer = setTimeout(saveServer, SERVER_DEBOUNCE_MS);
    } else if (isEditMode()) {
      // 편집은 localStorage 작업본만(라이브 주문 오염 방지). 서버 반영은 '저장'.
      clearTimeout(_localTimer);
      _localTimer = setTimeout(saveEditLocal, LOCAL_DEBOUNCE_MS);
    }
  }

  function bindInputs() {
    var pane = document.getElementById("erp-order");
    if (!pane) return;
    // 이벤트 위임: 동적 추가되는 품목 행까지 포함.
    pane.addEventListener("input", schedule, true);
    pane.addEventListener("change", schedule, true);
    // 필드 이탈 시 즉시 flush.
    pane.addEventListener(
      "blur",
      function () {
        if (isAddDraftMode()) {
          clearTimeout(_serverTimer);
          saveServer();
        } else if (isEditMode()) {
          clearTimeout(_localTimer);
          saveEditLocal();
        }
      },
      true
    );
    window.addEventListener("beforeunload", beaconFlush);
    // 모바일 백그라운드 전환(앱 전환/전화 수신) 시 flush — beforeunload 미발화 대비.
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState !== "hidden") return;
      if (isAddDraftMode()) {
        saveLocal();
        beaconFlush();
      } else if (isEditMode()) {
        saveEditLocal();
      }
    });
  }

  // ── 복원 배너 ──────────────────────────────────────────────────────
  /** 간결한 상대 시간(모바일 가독성). 숫자 ts(ms) 또는 서버 문자열 모두 허용. */
  function relTime(value) {
    try {
      var d;
      if (typeof value === "number") {
        d = new Date(value);
      } else if (typeof value === "string" && value) {
        // 서버 "YYYY-MM-DD HH:MM:SS"는 로컬(KST 브라우저) 기준으로 파싱.
        d = new Date(value.replace(" ", "T"));
        if (isNaN(d.getTime())) d = new Date(value);
      } else {
        d = new Date();
      }
      if (isNaN(d.getTime())) return "";
      var diff = Math.max(0, Date.now() - d.getTime());
      var min = Math.floor(diff / 60000);
      if (min < 1) return "방금 전";
      if (min < 60) return min + "분 전";
      var hr = Math.floor(min / 60);
      if (hr < 24) return hr + "시간 전";
      if (hr < 48) return "어제";
      return d.getMonth() + 1 + "월 " + d.getDate() + "일";
    } catch (e) {
      return "";
    }
  }

  function showRestoreBanner(source, info) {
    var banner = document.getElementById("erp-restore-banner");
    if (!banner) return;
    var timeEl = document.getElementById("erp-restore-time");
    if (timeEl && info && info.timeText) timeEl.textContent = info.timeText;
    banner.style.display = "";

    var resumeBtn = document.getElementById("erp-restore-resume");
    var discardBtn = document.getElementById("erp-restore-discard");

    function hide() {
      banner.style.display = "none";
    }

    if (resumeBtn) {
      resumeBtn.onclick = function () {
        if (source === "server") {
          // 서버 draft를 정식 로드(전체 structured fetch + 폼 채움).
          if (typeof window.erpSetOrderId === "function") window.erpSetOrderId(info.order_id);
          window.ORDER_ID = info.order_id;
          if (typeof window.erpLoadStructured === "function") {
            window.erpLoadStructured().then(function () {
              showIndicator("작성 내용을 불러왔습니다");
            });
          }
        } else {
          applyLocalSnapshot(info.snap);
          showIndicator("작성 내용을 불러왔습니다");
        }
        hide();
      };
    }
    if (discardBtn) {
      discardBtn.onclick = function () {
        if (!confirm("저장하지 않은 수정 내용을 버리시겠습니까?")) return;
        if (source === "local-edit") {
          // 편집 작업본만 폐기. 라이브 주문/ORDER_ID는 건드리지 않는다.
          clearEditLocal();
          hide();
          return;
        }
        clearLocal();
        _lastServerJson = null;
        fetch(DISCARD_URL, {
          method: "POST",
          credentials: "same-origin",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ draft_token: draftToken() }),
        }).catch(function () {});
        if (typeof window.erpSetOrderId === "function") window.erpSetOrderId(0);
        window.ORDER_ID = 0;
        hide();
      };
    }
  }

  /** 서버 draft 없이 localStorage만 있는 경우(오프라인 등) 폼 직접 채움. */
  function applyLocalSnapshot(snap) {
    if (!snap || !snap.payload) return;
    var p = snap.payload;
    var sd = p.structured_data || {};
    function set(id, v) {
      var el = document.getElementById(id);
      if (el) el.value = v == null ? "" : v;
    }
    function check(id, v) {
      var el = document.getElementById(id);
      if (el) el.checked = !!v;
    }
    set("erp-received-date", p.received_date);
    set("erp-received-time", p.received_time);
    set("erp-notes", p.notes);
    var cust = (sd.parties && sd.parties.customer) || {};
    set("erp-customer-name", cust.name);
    set("erp-customer-phone", cust.phone);
    var orderer = (sd.parties && sd.parties.orderer) || {};
    set("erp-orderer", orderer.name);
    var mgr = (sd.parties && sd.parties.manager) || {};
    set("erp-manager", mgr.name);
    var site = sd.site || {};
    set("erp-address", site.address_full || site.address_main || "");
    var meas = (sd.schedule && sd.schedule.measurement) || {};
    set("erp-measurement-date", meas.date);
    var cons = (sd.schedule && sd.schedule.construction) || {};
    set("erp-construction-date", cons.date);
    check("erp-self-measurement", p.is_self_measurement);
    check("erp-regional-order", p.is_regional);
    set("erp-regional-construction-type", p.construction_type);
    // 품목 복원
    var wrap = document.getElementById("erp-items");
    if (wrap && typeof window.erpNewItemRow === "function") {
      var items = Array.isArray(sd.items) ? sd.items : [];
      if (items.length) {
        wrap.innerHTML = "";
        items.forEach(function (it) {
          wrap.appendChild(window.erpNewItemRow(it));
        });
        if (typeof window.erpRefreshItemRowIndices === "function") window.erpRefreshItemRowIndices();
        if (typeof window.erpOpenFirstItemRow === "function") window.erpOpenFirstItemRow();
        if (typeof window.erpRecalcItemsTotal === "function") window.erpRecalcItemsTotal();
      }
    }
  }

  function maybeOfferRestore() {
    if (!isAddDraftMode()) return;
    // 서버 draft 우선(교차기기/내구).
    fetch(GET_DRAFT_URL + "?draft_token=" + encodeURIComponent(draftToken()), {
      credentials: "same-origin",
    })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data && data.success && data.draft && data.draft.has_content) {
          showRestoreBanner("server", {
            order_id: data.draft.order_id,
            timeText: relTime(data.draft.updated_at_ms || data.draft.updated_at),
          });
          return;
        }
        // 서버 draft 없음 → localStorage 폴백.
        var snap = readLocal();
        if (snap && hasMeaningfulContent(snap.payload)) {
          showRestoreBanner("local", { snap: snap, timeText: relTime(snap.ts) });
        }
      })
      .catch(function () {
        var snap = readLocal();
        if (snap && hasMeaningfulContent(snap.payload)) {
          showRestoreBanner("local", { snap: snap, timeText: relTime(snap.ts) });
        }
      });
  }

  /** 편집 모드: 저장 안 한 수정 작업본이 있으면 복원 배너 제시. */
  function maybeOfferEditRestore() {
    if (!isEditMode()) return;
    var snap = null;
    try {
      var raw = localStorage.getItem(editLocalStorageKey());
      if (raw) {
        var s = JSON.parse(raw);
        if (s && s.payload) snap = s;
      }
    } catch (e) {
      snap = null;
    }
    if (snap) {
      showRestoreBanner("local-edit", { snap: snap, timeText: relTime(snap.ts) });
    }
  }

  function start() {
    if (_started) return;
    if (isAddDraftMode()) {
      _started = true;
      purgeLegacyLocalStorage();
      bindInputs();
      maybeOfferRestore();
      return;
    }
    // edit 모드(저장된 주문 편집): 주문 데이터가 비동기로 로드된 뒤에 바인딩·복원 제시.
    // 로드 전에 바인딩하면 erpLoadStructured의 폼 채움이 자동저장으로 잡힐 수 있다.
    if (
      window.ERP_ORDER_ENABLED &&
      typeof window.isErpOrderDraftMode === "function" &&
      !window.isErpOrderDraftMode()
    ) {
      _started = true;
      var tries = 0;
      (function waitLoaded() {
        if (!isEditMode()) {
          // 아직 ORDER_ID 미확정. 잠깐 대기(탭/마운트 지연).
          if (tries++ > 60) return;
          setTimeout(waitLoaded, 150);
          return;
        }
        if (window.__erpStructuredLoadSucceeded || tries++ > 40) {
          bindInputs();
          maybeOfferEditRestore();
          return;
        }
        setTimeout(waitLoaded, 150);
      })();
    }
  }

  // 명시 저장 성공 시 자동저장 흔적 정리(add draft + edit 작업본) → 재진입 복원 배너 미표시.
  document.addEventListener("erp:order-saved", function () {
    // 저장 직후 페이지 이탈(visibilitychange/beforeunload)이 방금 저장한 내용을
    // 다시 쓰지 못하게 중단. 사용자가 다시 입력하면 schedule()에서 해제된다.
    _suspended = true;
    clearLocal();
    clearEditLocal();
    _lastServerJson = null;
    clearTimeout(_localTimer);
    clearTimeout(_serverTimer);
  });

  window.__ERP_AUTOSAVE_BOUND = true;
  window.fomsErpAutosave = { clearLocal: clearLocal, saveServer: saveServer, start: start };

  // erp-order-shared.js가 surface를 준비한 뒤 시작. ERP 탭이 늦게 활성화되는
  // 경우(?open=erp-order 아님)도 탭 최초 표시에서 start.
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", start);
  } else {
    start();
  }
  document.getElementById("erp-order-tab")?.addEventListener("shown.bs.tab", start);
})();
