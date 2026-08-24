/**
 * FOMS 태블릿 전용 ERP Order 폼 (W-MEASURE-FORM v2 전 필드 확장판) — 태블릿 가로(코호트)
 * 실측 split view 우측 패널. 목업 frame13 "융합·키보드"의 ERP Order 편집 = PC 편집 탭의 모든
 * 입력·데이터 필드 100%를 실측자(현장 작업자) 페르소나로 재구성한 터치 원장. 기존 PC ERP Order
 * edit fragment 주입을 대체하되, 데이터는 100% 기존 구조화 API로 읽고 쓴다(신규 백엔드 없음):
 *   - 읽기: GET  /api/orders/<id>/structured           (전사 공용 구조화 조회)
 *   - 쓰기: PUT  /api/orders/<id>/structured           (전사 공용 구조화 저장 = PC "저장"과 동일 경로)
 *   - 사진: GET  /api/orders/<id>/attachments?category=measurement (실측 사진 갤러리)
 *   - 첨부: POST /api/orders/<id>/attachments           (카메라/갤러리 업로드, 멀티파트)
 *   - 견적: iframe /edit/<id>?open=erp-estimate&embedded=1  (PC 견적서 탭 그대로)
 *   - 계산기: iframe /wdcalculator?embedded=1&order_id=&customer_name=  ([계산기] 탭 전면 임베드)
 *   - 완료: POST /api/orders/<id>/quest/approve  (MEASURE 퀘스트 승인 = 단계 전환 SSOT)
 *   - 채널톡: POST /api/channel/push-manual             (변환 텍스트 → 채널톡 수동 푸쉬; measurement/drawing)
 *
 * 실측자 IA(렌더 순서): ① 현장 컨텍스트(고객·연락처·주소·특이배지) ② 실측 기록(항목 칩·제품명·
 * 규격 W/D/H 복수행·자수·색상/옵션/손잡이/내부/기타·금액·항목일정·추가입력·항목사진) ③ 현장 사진
 * (카메라/갤러리 업로드 + 갤러리) ④ 특이사항 3종 + 비고 ⑤ 일정(실측·시공 날짜/시간) ⑥ 주문 정보
 * (접힘 아코디언: 접수·긴급·자가실측·지방·발주사·담당자·시공담당자·단계) ⑦ 금액(출고가·예약금·자유입력·
 * 할인·잔금·잔금메모·현금영수증) ⑧ 변환 텍스트/복사 + 채널톡 PUSH(실측/도면).
 *
 * 데이터 무결성(핵심):
 *   - read-merge-write: GET structured_data 전체를 deepClone 해 메모리에 보관하고 편집 키만 변형한 뒤
 *     "전체 shape 그대로" PUT 한다 → 폼이 렌더하지 않는 최상위 키(도면/견적/채널톡/quests 등)를 절대
 *     덮어쓰지 않는다(서버 _preserve_operational_structured_state 와 이중 방어).
 *   - 규격 W/H/D 는 items[].spec_rows(=출고 W·자수 SSOT)에 직접 기록. 자수(W/300) 표시는 클라 계산.
 *   - 금액(출고가·잔금)은 erpBuildTotals SSOT 를 파일 내부에 자체 미러 구현해 재계산 → structured.totals/
 *     payment 를 PC 와 동일하게 실어 보낸다(서버 sync_erp_flat_columns 가 파생; 이중계산 아님). payment 의
 *     *_confirmed* 확정 필드는 GET 값 보존(태블릿에서 토글 API 미사용).
 *   - top-level 컬럼(received_date/received_time/is_self_measurement/is_regional/construction_type)은
 *     load 시 baseline 저장 후, baseline 과 다를 때만 payload 에 포함(키 부재=서버 보존). is_regional 또는
 *     construction_type 변경 시 둘 다 함께 포함(쌍 계약). 지방 ON + 구분 미선택이면 명시 저장 차단(400 방지).
 *   - order.notes(비고)는 GET 에코 문자열을 그대로 전송 유지.
 *
 * 동시성:
 *   - 명시 저장/실측완료 직전 GET 으로 structured_updated_at 을 baseline 과 비교 → 다른 곳에서 수정됐으면
 *     배너를 띄우고 PUT 을 중단(silent overwrite 금지). 자동/임시 저장은 last-write-wins(전체 merge payload).
 *
 * 재실행 안전(perf G4): window.__FOMS_TABLET_MEASURE_FORM_BOUND 싱글턴 가드 + 위임 이벤트(1회 바인딩).
 * 이 모듈은 스스로 활성화하지 않는다 — 코호트 게이트를 통과한 tablet-measurement.js 가
 * load()/requestSave()/requestComplete()/requestDraft()/requestChannelPush()/switchTab()
 * 로 구동한다(중복 게이트 정의 금지). PC 번들(window.erp*)에는 의존하지 않는다(이 페이지 미로드).
 */
(function () {
  "use strict";

  if (window.__FOMS_TABLET_MEASURE_FORM_BOUND) return;
  window.__FOMS_TABLET_MEASURE_FORM_BOUND = true;

  var AUTOSAVE_DEBOUNCE_MS = 1500;
  var DETAIL_SELECTOR = ".foms-tablet-measure-detail";
  var INJECT_SELECTOR = "[data-foms-tablet-measure-detail]";
  var STATUS_SELECTOR = "[data-foms-tablet-measure-status]";
  // 도면 단계 이후(=도면팀이 이미 착수) 스테이지 — 실측 수정 시 자동통지 안내 배너 게이트(T3).
  var POST_DRAWING_STAGES = [
    "DRAWING",
    "CONFIRM",
    "PRODUCTION",
    "CONSTRUCTION",
    "CS",
    "COMPLETED",
  ];

  // PC erp_order_tab.html SSOT 그대로의 select 옵션 목록(하드코딩 금지 원칙 하 마크업 계약 미러).
  var WORKFLOW_STAGE_OPTIONS = [
    ["", "-"],
    ["RECEIVED", "A. 주문접수"],
    ["MEASURE", "C. 실측"],
    ["DRAWING", "D. 도면"],
    ["CONFIRM", "E. 고객컨펌"],
    ["PRODUCTION", "F. 생산"],
    ["CONSTRUCTION", "G. 시공"],
    ["CS", "H. CS"],
    ["AS_RECEIVED", "AS접수"],
    ["AS_COMPLETED", "AS완료"],
    ["COMPLETED", "완료"],
    ["AS", "AS처리"],
  ];
  var CONSTRUCTION_TYPE_OPTIONS = [
    ["", "하우드/협력사 선택"],
    ["하우드 시공", "하우드"],
    ["협력사 시공", "협력사"],
  ];
  var ORDERER_SELECT_OPTIONS = [
    ["라홈", "라홈"],
    ["하우드", "하우드"],
  ];
  var TIME_SELECT_OPTIONS = [
    ["", "시간 선택"],
    ["오전", "오전"],
    ["오후", "오후"],
    ["종일", "종일"],
    ["__direct__", "직접 입력"],
  ];
  var ATTACHMENT_CATEGORY_OPTIONS = [
    ["measurement", "실측"],
    ["drawing", "도면"],
    ["construction", "시공"],
    ["as", "AS"],
  ];
  var TIME_PRESETS = ["오전", "오후", "종일"];

  // 활성 주문 1건의 편집 상태. 카드 전환 시 통째로 교체된다.
  var state = null;
  // 실측 완료(저장→퀘스트 승인) 진행 중 플래그 — 중복 클릭 차단(state 교체와 무관하게 유지).
  var completeBusy = false;

  function setCompleteBusy(busy) {
    completeBusy = !!busy;
    var btn = chromeQuery("[data-foms-tablet-measure-complete]");
    if (btn) btn.disabled = completeBusy;
  }

  function setCompleteVisible(on) {
    var btn = chromeQuery("[data-foms-tablet-measure-complete]");
    if (btn) btn.hidden = !on;
  }

  function structuredUrl(id) {
    return "/api/orders/" + encodeURIComponent(id) + "/structured";
  }
  function attachmentsUrl(id) {
    return "/api/orders/" + encodeURIComponent(id) + "/attachments?category=measurement";
  }
  function attachmentsUploadUrl(id) {
    return "/api/orders/" + encodeURIComponent(id) + "/attachments";
  }
  function estimateIframeSrc(id) {
    return (
      "/edit/" +
      encodeURIComponent(id) +
      "?open=erp-estimate&embedded=1&return_to=erp_measurement_dashboard"
    );
  }
  function calcIframeSrc(id, name) {
    return (
      "/wdcalculator?embedded=1&order_id=" +
      encodeURIComponent(id) +
      "&customer_name=" +
      encodeURIComponent(name || "")
    );
  }

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function deepClone(obj) {
    try {
      return obj == null ? {} : JSON.parse(JSON.stringify(obj));
    } catch (e) {
      return {};
    }
  }

  // 금액 정규화: 숫자/문자열/{amount} dict 모두 정수로. 서버가 예약금을 dict 로 저장한 레거시 방어.
  function coerceAmount(v) {
    if (v == null) return 0;
    if (typeof v === "object") v = v.amount != null ? v.amount : v.raw;
    var n = parseInt(String(v == null ? "" : v).replace(/[^0-9-]/g, ""), 10);
    return isNaN(n) ? 0 : n;
  }
  function formatWon(n) {
    try {
      return (n || 0).toLocaleString("ko-KR");
    } catch (e) {
      return String(n || 0);
    }
  }

  // 값이 비면 '상담' 기본(PC erpNewItemRow defaultConsult 미러).
  function defaultConsult(v) {
    var s = String(v == null ? "" : v).trim();
    return s ? s : "상담";
  }

  // 복합 규격 W(가로) → 총 폭(mm). Python foms.services.erp_template_filters.eval_spec_width_mm 미러.
  function evalSpecWidthMm(value) {
    if (value == null) return 0;
    var s = String(value).trim();
    if (!s) return 0;
    s = s.replace(/\([^)]*\)/g, "");
    var total = 0;
    var matched = false;
    s.split(/[+,]/).forEach(function (term) {
      var m = term.match(/[\d.]+/);
      if (!m) return;
      var n = parseFloat(m[0]);
      if (!isNaN(n)) {
        total += n;
        matched = true;
      }
    });
    return matched ? total : 0;
  }

  // 항목 자수(W/300) 표시값. spec_rows 각 행 W 합산 후 /300, 소수 1자리. 표시 전용(저장 안 함).
  function itemJasuDisplay(item) {
    if (!item || typeof item !== "object") return "";
    var rows = Array.isArray(item.spec_rows) ? item.spec_rows : [];
    var totalW = 0;
    rows.forEach(function (row) {
      if (row && typeof row === "object") {
        totalW += evalSpecWidthMm(row.spec_width != null ? row.spec_width : row.w);
      }
    });
    if (!totalW) return "";
    return String(Math.round((totalW / 300) * 10) / 10);
  }

  // ── 금액/자유입력 SSOT 미러(PC erp-order-shared.js — 이 페이지엔 미로드라 자체 구현) ──────
  function resolveDepositAmount(sd) {
    sd = sd || {};
    var payment = sd.payment || {};
    var legacy = sd.payments || {};
    var modern = coerceAmount(payment.deposit);
    if (modern > 0) return modern;
    return coerceAmount(legacy.deposit);
  }
  function resolveDiscountAmount(sd) {
    sd = sd || {};
    var payment = sd.payment || {};
    var totals = sd.totals || {};
    var modern = coerceAmount(payment.discount);
    if (modern > 0) return modern;
    return coerceAmount(totals.discount_amount);
  }
  function resolveCashReceipt(sd) {
    sd = sd || {};
    var payment = sd.payment || {};
    if (Object.prototype.hasOwnProperty.call(payment, "cash_receipt")) {
      return String(payment.cash_receipt || "").trim();
    }
    var legacy = (sd.payments || {}).cash_receipt;
    if (legacy && typeof legacy === "object") return String(legacy.value || legacy.raw || "").trim();
    return String(legacy || "").trim();
  }
  function resolveBalanceNote(sd) {
    sd = sd || {};
    var payment = sd.payment || {};
    if (Object.prototype.hasOwnProperty.call(payment, "balance_note")) {
      return String(payment.balance_note || "").trim();
    }
    return "";
  }
  function resolveFreeInputText(sd) {
    sd = sd || {};
    var payment = sd.payment || {};
    if (Object.prototype.hasOwnProperty.call(payment, "free_input")) {
      return String(payment.free_input || "").trim();
    }
    var legacy = (sd.payments || {}).free_input;
    if (legacy && typeof legacy === "object") return String(legacy.value || legacy.raw || "").trim();
    return String(legacy || "").trim();
  }
  // 저장된 free_input 문자열 → 폼용 {text, amount}(첫 비공백 라인 파싱). PC erpSplitFreeInputForForm 미러.
  function splitFreeInputForForm(stored) {
    var raw = String(stored || "").trim();
    if (!raw) return { text: "", amount: 0 };
    var lines = raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
    var first = "";
    for (var i = 0; i < lines.length; i += 1) {
      var line = String(lines[i] || "").trim();
      if (line) {
        first = line;
        break;
      }
    }
    if (!first) return { text: "", amount: 0 };
    var colonMatch = first.match(/^(.+?)[:：]\s*(.+)$/);
    if (colonMatch) {
      return { text: colonMatch[1].trim(), amount: coerceAmount(colonMatch[2]) };
    }
    var asAmount = coerceAmount(first);
    if (asAmount > 0 && String(first).replace(/[^0-9]/g, "").length >= String(asAmount).length) {
      return { text: "", amount: asAmount };
    }
    return { text: first, amount: 0 };
  }
  // 폼 {text, amount} → 저장 free_input 문자열. PC erpBuildFreeInputStoredValue 미러.
  function buildFreeInputStored(text, amount) {
    var label = String(text || "").trim();
    var amt = coerceAmount(amount);
    if (!label && amt <= 0) return "";
    if (!label) return formatWon(amt);
    if (amt <= 0) return label;
    return label + " : " + formatWon(amt);
  }
  // erpBuildTotals SSOT 미러: total = itemsTotal + freeInput; balance = total - deposit - discount;
  // shipping_price = total - discount(= itemsTotal + freeInput - discount).
  function buildTotals(itemsTotal, deposit, discount, freeInput) {
    var itemsSubtotal = coerceAmount(itemsTotal);
    var free = coerceAmount(freeInput);
    var total = itemsSubtotal + free;
    var dep = coerceAmount(deposit);
    var disc = coerceAmount(discount);
    var balance = Math.max(0, total - dep - disc);
    var shipping = Math.max(0, total - disc);
    return {
      items_total: itemsSubtotal,
      free_input_amount: free,
      contract_total: total,
      deposit_amount: dep,
      discount_amount: disc,
      balance_amount: balance,
      final_amount: balance,
      shipping_price: shipping,
    };
  }

  // 시공 담당자 문자열 → 배열(개행/콤마 split, trim, 중복 제거). PC erpNormalizeConstructionWorkers 미러.
  function normalizeConstructionWorkers(value) {
    var rawValues;
    if (Array.isArray(value)) rawValues = value;
    else rawValues = String(value || "").replace(/\n/g, ",").split(",");
    var workers = [];
    rawValues.forEach(function (item) {
      var rawName = item;
      if (item && typeof item === "object") rawName = item.name || item.text || item.value || "";
      var name = String(rawName || "").trim();
      if (name && workers.indexOf(name) === -1) workers.push(name);
    });
    return workers;
  }
  function formatConstructionWorkers(value) {
    return normalizeConstructionWorkers(value).join("\n");
  }

  // ── DOM 헬퍼 ───────────────────────────────────────────────────────
  function detailEl() {
    return document.querySelector(DETAIL_SELECTOR);
  }
  function injectEl() {
    return document.querySelector(INJECT_SELECTOR);
  }
  function statusEl() {
    var d = detailEl();
    return d ? d.querySelector(STATUS_SELECTOR) : null;
  }
  function formEl() {
    var inj = injectEl();
    return inj ? inj.querySelector("[data-foms-tmf]") : null;
  }
  function chromeQuery(sel) {
    var d = detailEl();
    return d ? d.querySelector(sel) : null;
  }

  function setStatus(text, kind) {
    var el = statusEl();
    if (!el) return;
    el.textContent = text || "";
    el.className = "foms-tmf-status foms-tablet-measure-actions__status" + (kind ? " foms-tmf-status--" + kind : "");
    el.hidden = !text;
  }

  // 상단 바 "✓ 자동저장됨 · 방금" 라이브 배지.
  function showAutosaveBadge(label) {
    var badge = chromeQuery("[data-foms-tmf-autosave]");
    var txt = chromeQuery("[data-foms-tmf-autosave-text]");
    if (txt) txt.textContent = label || "자동저장됨 · 방금";
    if (badge) badge.hidden = false;
  }
  function hideAutosaveBadge() {
    var badge = chromeQuery("[data-foms-tmf-autosave]");
    if (badge) badge.hidden = true;
  }
  function renderTopbarId() {
    var num = chromeQuery("[data-foms-tmf-ordernum]");
    if (num) num.textContent = state ? "#" + state.orderId : "";
  }

  // 탭 버튼 + 완료 버튼 노출 동기화(크롬은 __scroll 밖 형제라 재렌더에도 생존).
  function syncTabButtons() {
    if (!state) return;
    var tabs = detailEl() ? detailEl().querySelectorAll("[data-foms-tmf-tab]") : [];
    Array.prototype.forEach.call(tabs, function (b) {
      var on = b.getAttribute("data-foms-tmf-tab") === state.activeTab;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    // "실측 완료 → 도면 전달"은 실측 단계 주문에서만 노출(라벨-동작 일치).
    setCompleteVisible(isMeasureStage());
  }

  // ── 구조화 접근자(방어적) ───────────────────────────────────────────
  function ensureObj(parent, key) {
    if (!parent[key] || typeof parent[key] !== "object" || Array.isArray(parent[key])) {
      parent[key] = {};
    }
    return parent[key];
  }
  function ensureParty(kind) {
    var parties = ensureObj(state.structured, "parties");
    return ensureObj(parties, kind);
  }
  function ensureSite() {
    return ensureObj(state.structured, "site");
  }
  function ensureFlags() {
    return ensureObj(state.structured, "flags");
  }
  function ensureWorkflow() {
    return ensureObj(state.structured, "workflow");
  }
  function ensureNotesObj() {
    return ensureObj(state.structured, "notes");
  }
  function ensureShipment() {
    return ensureObj(state.structured, "shipment");
  }
  function ensureMeasurementSchedule() {
    var sch = ensureObj(state.structured, "schedule");
    return ensureObj(sch, "measurement");
  }
  function ensureConstructionSchedule() {
    var sch = ensureObj(state.structured, "schedule");
    return ensureObj(sch, "construction");
  }

  function partyValue(kind, key) {
    var p = state.structured.parties && state.structured.parties[kind];
    return p && typeof p === "object" ? p[key] || "" : "";
  }
  function siteAddress() {
    var s = state.structured.site;
    if (!s || typeof s !== "object") return "";
    var full = (s.address_full || s.address_main || "").trim();
    var detail = (s.address_detail || "").trim();
    // ADDR-DUP-01: full 이 이미 상세주소를 품은 행(외부 수집분·옛 문서)이 있다. 그대로 붙이면
    // 같은 동·호수가 두 번 붙고, 이 화면의 저장이 그 문자열을 주소로 굳힌다.
    if (!detail) return full;
    if (!full) return detail;
    return full.endsWith(detail) ? full : full + " " + detail;
  }
  function scheduleValue(group, key) {
    var g = state.structured.schedule && state.structured.schedule[group];
    return g && typeof g === "object" ? g[key] || "" : "";
  }
  function flagValue(key) {
    var f = state.structured.flags;
    return f && typeof f === "object" ? f[key] : undefined;
  }
  function notesValue(key) {
    var n = state.structured.notes;
    return n && typeof n === "object" && !Array.isArray(n) ? n[key] || "" : "";
  }
  function workflowStage() {
    var w = state.structured.workflow;
    return w && typeof w === "object" ? w.stage || "" : "";
  }
  // 도면 단계 이후(도면팀이 이미 작업 중) 여부 — 실측 폼 상단 자동통지 안내 배너 게이트.
  function isPostDrawingStage() {
    return POST_DRAWING_STAGES.indexOf(String(workflowStage()).toUpperCase()) !== -1;
  }
  // 좌측 큐에는 실측 외 단계 주문도 섞인다. quest/approve 는 "현재 단계" 퀘스트를 승인하므로
  // 비-MEASURE 주문에서 누르면 라벨("도면 전달")과 다른 단계로 전진한다 → 완료 버튼 게이트.
  function isMeasureStage() {
    return String(workflowStage()).toUpperCase() === "MEASURE";
  }
  function constructionWorkersText() {
    var sh = state.structured.shipment;
    return formatConstructionWorkers(sh && typeof sh === "object" ? sh.construction_workers : []);
  }

  function itemsList() {
    return Array.isArray(state.structured.items) ? state.structured.items : [];
  }

  function isEditable() {
    // ERP 원장(구조화 데이터)이 있는 주문만 편집 가능. 레거시 비-ERP 주문은 structured PUT 필수값
    // (고객/전화/주소/제품)이 없어 400 이 나므로 편집을 막고 안내한다.
    var sd = state && state.structured;
    if (!sd || typeof sd !== "object") return false;
    var hasItems = Array.isArray(sd.items) && sd.items.length > 0;
    var hasParties = sd.parties && typeof sd.parties === "object";
    return hasItems || hasParties;
  }

  // 항목 금액 합계(item.price 는 원문 문자열 보관 → coerce 합산).
  function sumItemsTotal() {
    var sum = 0;
    itemsList().forEach(function (item) {
      if (item && typeof item === "object") sum += coerceAmount(item.price);
    });
    return sum;
  }

  // 금액 재계산 → structured.totals/payment 갱신(PC 와 동일하게 클라 totals 전송; 이중계산 아님).
  function recomputeTotals() {
    if (!state) return buildTotals(0, 0, 0, 0);
    var a = state.amounts || {};
    var totals = buildTotals(sumItemsTotal(), a.deposit, a.discount, a.freeAmount);
    var base = state.paymentBase || {};
    state.structured.totals = totals;
    state.structured.payment = {
      deposit: totals.deposit_amount,
      discount: totals.discount_amount,
      free_input: buildFreeInputStored(a.freeText, a.freeAmount),
      cash_receipt: String(a.cashReceipt || ""),
      balance_note: String(a.balanceNote || "").trim(),
      deposit_confirmed: !!base.deposit_confirmed,
      deposit_confirmed_at: base.deposit_confirmed_at || null,
      deposit_confirmed_by: base.deposit_confirmed_by || null,
      deposit_confirmed_by_user_id: base.deposit_confirmed_by_user_id || null,
      balance_confirmed: !!base.balance_confirmed,
      balance_confirmed_at: base.balance_confirmed_at || null,
      balance_confirmed_by: base.balance_confirmed_by || null,
      balance_confirmed_by_user_id: base.balance_confirmed_by_user_id || null,
    };
    return totals;
  }

  // 저장 직전 항목 정규화(PC erpCollectStructured 미러): 상담 기본값, 금액 정수화, spec 파생.
  function normalizeItemsForSave() {
    itemsList().forEach(function (item) {
      if (!item || typeof item !== "object") return;
      ["option_detail", "handle", "internal", "misc"].forEach(function (k) {
        item[k] = defaultConsult(item[k]);
      });
      var colorRaw = String(item.color == null ? "" : item.color).replace(/(\s+\(SK\))+$/g, "").trim();
      item.color = colorRaw || "상담";
      var pd = String(item.price == null ? "" : item.price).replace(/[^0-9]/g, "");
      item.price = pd ? parseInt(pd, 10) : "";
      var rows = Array.isArray(item.spec_rows) ? item.spec_rows : [];
      var kept = [];
      rows.forEach(function (r) {
        if (!r || typeof r !== "object") return;
        var w = String(r.spec_width != null ? r.spec_width : r.w || "").trim();
        var d = String(r.spec_depth != null ? r.spec_depth : r.d || "").trim();
        var h = String(r.spec_height != null ? r.spec_height : r.h || "").trim();
        if (w || d || h) kept.push({ spec_width: w, spec_depth: d, spec_height: h });
      });
      if (kept.length) {
        item.spec_rows = kept;
        item.spec_width = kept[0].spec_width;
        item.spec_depth = kept[0].spec_depth;
        item.spec_height = kept[0].spec_height;
        var lines = kept
          .map(function (sr) {
            return [sr.spec_width, sr.spec_depth, sr.spec_height].filter(Boolean).join("x");
          })
          .filter(Boolean);
        item.spec = lines.join(", ") || String(item.spec || "");
      } else {
        item.spec_rows = [];
        item.spec_width = "";
        item.spec_depth = "";
        item.spec_height = "";
        item.spec = String(item.spec || "");
      }
    });
  }

  // ── 렌더: 필드 부품 ────────────────────────────────────────────────
  function textField(label, fieldKey, value, opts) {
    opts = opts || {};
    var full = opts.full ? " foms-tmf__ffield--full" : "";
    var mode = opts.inputmode ? ' inputmode="' + opts.inputmode + '"' : "";
    var type = opts.type ? opts.type : "text";
    var ph = opts.placeholder ? ' placeholder="' + escapeHtml(opts.placeholder) + '"' : "";
    var hidden = opts.hidden ? " hidden" : "";
    return (
      '<div class="foms-tmf__ffield' +
      full +
      '"><label class="foms-tmf__flabel">' +
      escapeHtml(label) +
      "</label>" +
      '<input class="foms-tmf__finput" type="' +
      type +
      '" autocomplete="off"' +
      mode +
      ' data-tmf-field="' +
      fieldKey +
      '" value="' +
      escapeHtml(value) +
      '"' +
      ph +
      hidden +
      "></div>"
    );
  }

  function textAreaField(label, fieldKey, value, opts) {
    opts = opts || {};
    var full = opts.full ? " foms-tmf__ffield--full" : "";
    var ph = opts.placeholder ? ' placeholder="' + escapeHtml(opts.placeholder) + '"' : "";
    return (
      '<div class="foms-tmf__ffield' +
      full +
      '"><label class="foms-tmf__flabel">' +
      escapeHtml(label) +
      "</label>" +
      '<textarea class="foms-tmf__textarea" rows="' +
      (opts.rows || 2) +
      '" data-tmf-field="' +
      fieldKey +
      '"' +
      ph +
      ">" +
      escapeHtml(value) +
      "</textarea></div>"
    );
  }

  function selectField(label, fieldKey, value, options, opts) {
    opts = opts || {};
    var full = opts.full ? " foms-tmf__ffield--full" : "";
    var disabled = opts.disabled ? " disabled" : "";
    var extraAttr = opts.attr ? " " + opts.attr : "";
    var optsHtml = options
      .map(function (o) {
        var sel = String(o[0]) === String(value == null ? "" : value) ? " selected" : "";
        return '<option value="' + escapeHtml(o[0]) + '"' + sel + ">" + escapeHtml(o[1]) + "</option>";
      })
      .join("");
    return (
      '<div class="foms-tmf__ffield' +
      full +
      '"><label class="foms-tmf__flabel">' +
      escapeHtml(label) +
      "</label>" +
      '<select class="foms-tmf__finput"' +
      (fieldKey ? ' data-tmf-field="' + fieldKey + '"' : "") +
      extraAttr +
      disabled +
      ">" +
      optsHtml +
      "</select></div>"
    );
  }

  function checkboxField(label, fieldKey, checked) {
    return (
      '<label class="foms-tmf__check"><input type="checkbox" data-tmf-field="' +
      fieldKey +
      '"' +
      (checked ? " checked" : "") +
      '><span>' +
      escapeHtml(label) +
      "</span></label>"
    );
  }

  function amountField(label, amountKey, value, opts) {
    opts = opts || {};
    var full = opts.full ? " foms-tmf__ffield--full" : "";
    var ph = opts.placeholder ? ' placeholder="' + escapeHtml(opts.placeholder) + '"' : "";
    return (
      '<div class="foms-tmf__ffield' +
      full +
      '"><label class="foms-tmf__flabel">' +
      escapeHtml(label) +
      "</label>" +
      '<input class="foms-tmf__finput foms-tmf__finput--amount" type="text" inputmode="numeric" autocomplete="off" data-tmf-amount="' +
      amountKey +
      '" value="' +
      escapeHtml(value > 0 ? formatWon(value) : "") +
      '"' +
      ph +
      "></div>"
    );
  }

  // ── 렌더: ① 현장 컨텍스트(고객·연락처·주소 + 특이 배지) ─────────────
  function renderBadges() {
    var out = "";
    if (String(notesValue("phone_note")).trim()) out += '<span class="foms-tmf__badge">연락처 특이</span>';
    if (String(notesValue("address_note")).trim()) out += '<span class="foms-tmf__badge">주소 특이</span>';
    if (String(notesValue("measurement_note")).trim()) out += '<span class="foms-tmf__badge">실측 특이</span>';
    return out || '<span class="foms-tmf__badge-none">특이사항 없음</span>';
  }
  function refreshBadges() {
    var host = formEl() ? formEl().querySelector("[data-tmf-badges]") : null;
    if (host) host.innerHTML = renderBadges();
  }

  function renderContextCard() {
    return (
      '<section class="foms-tmf__section">' +
      '<h5 class="foms-tmf__title">현장 컨텍스트</h5>' +
      '<div class="foms-tmf__badges" data-tmf-badges>' +
      renderBadges() +
      "</div>" +
      '<div class="foms-tmf__formgrid">' +
      textField("고객명", "customer_name", partyValue("customer", "name")) +
      textField("연락처", "customer_phone", partyValue("customer", "phone"), { inputmode: "tel" }) +
      textField("현장 주소", "site_address", siteAddress(), {
        full: true,
        placeholder: "도로명/지번 주소",
      }) +
      "</div></section>"
    );
  }

  // ── 렌더: ② 실측 기록(항목) ────────────────────────────────────────
  function renderItemChips() {
    var list = itemsList();
    var chips = list
      .map(function (item, idx) {
        var name = (item && (item.product_name || item.name)) || "제품 " + (idx + 1);
        var active = idx === state.activeItem ? " is-active" : "";
        return (
          '<button type="button" class="foms-tmf__chip' +
          active +
          '" data-tmf-item="' +
          idx +
          '">' +
          (idx + 1) +
          ". " +
          escapeHtml(name) +
          "</button>"
        );
      })
      .join("");
    chips +=
      '<button type="button" class="foms-tmf__chip foms-tmf__chip--add" data-tmf-add-item>' +
      '<i class="fas fa-plus" aria-hidden="true"></i> 항목 추가</button>';
    return '<div class="foms-tmf__chips" role="group" aria-label="제품 항목 선택">' + chips + "</div>";
  }

  // 규격 행의 한 차원 값(spec_width|spec_depth|spec_height, 레거시 w|d|h 폴백)을 문자열로.
  function specDim(row, primary, legacy) {
    if (!row || typeof row !== "object") return "";
    var v = row[primary];
    if (v == null) v = row[legacy];
    return v == null ? "" : String(v);
  }

  function renderSpecRow(itemIdx, rowIdx, row, rowCount) {
    var w = escapeHtml(specDim(row, "spec_width", "w"));
    var d = escapeHtml(specDim(row, "spec_depth", "d"));
    var h = escapeHtml(specDim(row, "spec_height", "h"));
    var rowLabelBar =
      '<div class="foms-tmf__spec-rowhead">' +
      '<span class="foms-tmf__spec-rowlabel">규격 ' +
      (rowIdx + 1) +
      "</span>" +
      (rowCount > 1
        ? '<button type="button" class="foms-tmf__spec-del" data-tmf-del-spec-row="' +
          rowIdx +
          '" aria-label="규격 행 삭제"><i class="fas fa-minus" aria-hidden="true"></i></button>'
        : "") +
      "</div>";
    function box(dim, label, value) {
      return (
        '<div class="foms-tmf__numfield">' +
        '<label class="foms-tmf__numlabel">' +
        label +
        "</label>" +
        '<div class="foms-tmf__numwrap">' +
        '<input class="foms-tmf__num" type="text" inputmode="numeric" autocomplete="off" ' +
        'data-tmf-spec="' +
        dim +
        '" data-item-index="' +
        itemIdx +
        '" data-row-index="' +
        rowIdx +
        '" value="' +
        value +
        '" aria-label="' +
        label +
        '">' +
        '<span class="foms-tmf__unit">mm</span>' +
        "</div>" +
        "</div>"
      );
    }
    return (
      '<div class="foms-tmf__spec-row">' +
      rowLabelBar +
      '<div class="foms-tmf__numgrid">' +
      box("width", "W (가로·총폭)", w) +
      box("depth", "D (깊이)", d) +
      box("height", "H (높이)", h) +
      "</div>" +
      "</div>"
    );
  }

  function renderItemSpec() {
    var list = itemsList();
    var item = list[state.activeItem];
    if (!item) return "";
    var rows = Array.isArray(item.spec_rows) && item.spec_rows.length ? item.spec_rows : [{}];
    var rowsHtml = rows
      .map(function (row, rIdx) {
        return renderSpecRow(state.activeItem, rIdx, row, rows.length);
      })
      .join("");
    var addRow =
      '<button type="button" class="foms-tmf__spec-add" data-tmf-add-spec-row>' +
      '<i class="fas fa-plus" aria-hidden="true"></i> 복합 규격 행 추가</button>';
    var jasu = itemJasuDisplay(item);
    var jasuHtml =
      '<div class="foms-tmf__jasu"' +
      (jasu ? "" : " hidden") +
      '>자수 (W/300) <strong>' +
      escapeHtml(jasu) +
      "</strong></div>";
    return rowsHtml + addRow + jasuHtml;
  }

  function itemFieldRow(label, field, value, opts) {
    opts = opts || {};
    var full = opts.full ? " foms-tmf__ffield--full" : "";
    var ph = opts.placeholder ? ' placeholder="' + escapeHtml(opts.placeholder) + '"' : "";
    var mode = opts.inputmode ? ' inputmode="' + opts.inputmode + '"' : "";
    return (
      '<div class="foms-tmf__ffield' +
      full +
      '"><label class="foms-tmf__flabel">' +
      escapeHtml(label) +
      "</label>" +
      '<input class="foms-tmf__finput" type="text" autocomplete="off"' +
      mode +
      ' data-tmf-itemfield="' +
      field +
      '" value="' +
      escapeHtml(value) +
      '"' +
      ph +
      "></div>"
    );
  }

  function itemPriceRow(value) {
    var amt = coerceAmount(value);
    return (
      '<div class="foms-tmf__ffield"><label class="foms-tmf__flabel">항목 금액 (원)</label>' +
      '<input class="foms-tmf__finput foms-tmf__finput--amount" type="text" inputmode="numeric" autocomplete="off" ' +
      'data-tmf-itemfield="price" value="' +
      escapeHtml(amt > 0 ? formatWon(amt) : "") +
      '" placeholder="0"></div>'
    );
  }

  function renderItemUpload() {
    // 항목 사진: 카메라(capture)·갤러리(no-capture) 업로드 → OrderAttachment(item_index=활성항목, category=measurement).
    return (
      '<div class="foms-tmf__uploads foms-tmf__uploads--item">' +
      '<label class="foms-tmf__uploadbtn"><i class="fas fa-camera" aria-hidden="true"></i><span>항목 사진 촬영</span>' +
      '<input type="file" accept="image/*" capture="environment" data-tmf-upload="item" hidden></label>' +
      '<label class="foms-tmf__uploadbtn"><i class="fas fa-images" aria-hidden="true"></i><span>항목 사진 선택</span>' +
      '<input type="file" accept="image/*,video/*" multiple data-foms-no-capture data-tmf-upload="item" hidden></label>' +
      "</div>"
    );
  }

  function renderItemBody() {
    var list = itemsList();
    if (!list.length) {
      return (
        renderItemChips() +
        '<div class="foms-tmf__empty-note">제품 항목이 없습니다. [+ 항목 추가]로 항목을 추가하세요.</div>'
      );
    }
    var item = list[state.activeItem];
    var head =
      '<div class="foms-tmf__item-head">' +
      '<span class="foms-tmf__item-headlabel">항목 ' +
      (state.activeItem + 1) +
      " / " +
      list.length +
      "</span>" +
      (list.length > 1
        ? '<button type="button" class="foms-tmf__item-del" data-tmf-del-item="' +
          state.activeItem +
          '"><i class="fas fa-trash" aria-hidden="true"></i> 이 항목 삭제</button>'
        : "") +
      "</div>";
    var nameField =
      '<div class="foms-tmf__ffield foms-tmf__ffield--full">' +
      '<label class="foms-tmf__flabel">제품명</label>' +
      '<input class="foms-tmf__finput" type="text" autocomplete="off" data-tmf-field="product_name" value="' +
      escapeHtml((item && item.product_name) || "") +
      '" placeholder="예: 붙박이장 W2400"></div>';
    var attrs =
      '<div class="foms-tmf__formgrid">' +
      itemFieldRow("색상", "color", defaultConsult(item.color), { placeholder: "상담" }) +
      itemFieldRow("옵션", "option_detail", defaultConsult(item.option_detail), { placeholder: "상담" }) +
      itemFieldRow("손잡이", "handle", defaultConsult(item.handle), { placeholder: "상담" }) +
      itemFieldRow("내부", "internal", defaultConsult(item.internal), { placeholder: "상담" }) +
      itemFieldRow("기타 / 설치위치", "misc", defaultConsult(item.misc), { full: true, placeholder: "상담" }) +
      itemPriceRow(item.price) +
      itemFieldRow("항목 실측일", "measurement_date", String(item.measurement_date || ""), {
        placeholder: "예: 2026-07-11",
      }) +
      itemFieldRow("항목 시공일", "construction_date", String(item.construction_date || ""), {
        placeholder: "예: 2026-07-24",
      }) +
      "</div>" +
      '<div class="foms-tmf__ffield foms-tmf__ffield--full"><label class="foms-tmf__flabel">추가 입력</label>' +
      '<textarea class="foms-tmf__textarea" rows="2" data-tmf-itemfield="extra_input" placeholder="현장 특이·주의사항">' +
      escapeHtml(String(item.extra_input || "")) +
      "</textarea></div>";
    return (
      renderItemChips() +
      head +
      nameField +
      '<div class="foms-tmf__spec" data-tmf-spec-panel>' +
      renderItemSpec() +
      "</div>" +
      attrs +
      renderItemUpload()
    );
  }

  function renderItemsCard() {
    return (
      '<section class="foms-tmf__section">' +
      '<h5 class="foms-tmf__title">실측 기록 · 제품 항목 ' +
      itemsList().length +
      "</h5>" +
      '<div data-tmf-item-body>' +
      renderItemBody() +
      "</div></section>"
    );
  }

  // ── 렌더: ③ 현장 사진(업로드 + 갤러리) ─────────────────────────────
  function renderPhotosCard() {
    return (
      '<section class="foms-tmf__section">' +
      '<h5 class="foms-tmf__title">현장 사진</h5>' +
      '<div class="foms-tmf__uploads">' +
      '<select class="foms-tmf__finput foms-tmf__uploadcat" data-tmf-photo-cat aria-label="첨부 분류">' +
      ATTACHMENT_CATEGORY_OPTIONS.map(function (o) {
        return '<option value="' + escapeHtml(o[0]) + '">' + escapeHtml(o[1]) + "</option>";
      }).join("") +
      "</select>" +
      '<label class="foms-tmf__uploadbtn"><i class="fas fa-camera" aria-hidden="true"></i><span>카메라 촬영</span>' +
      '<input type="file" accept="image/*" capture="environment" data-tmf-upload="scene" hidden></label>' +
      '<label class="foms-tmf__uploadbtn"><i class="fas fa-images" aria-hidden="true"></i><span>갤러리 선택</span>' +
      '<input type="file" accept="image/*,video/*" multiple data-foms-no-capture data-tmf-upload="scene" hidden></label>' +
      "</div>" +
      '<div class="foms-tmf__photos" data-tmf-photos><div class="foms-tmf__photo-loading">사진 불러오는 중…</div></div>' +
      "</section>"
    );
  }

  // ── 렌더: ④ 특이사항 3종 + 비고 (기본 접힘 아코디언, 배지로 내용 유무 표시) ─────────
  // 채워진 필드 수(특이사항 3종 + 비고). 접힘 요약 배지에 노출.
  function notesFilledCount() {
    var n = 0;
    ["phone_note", "address_note", "measurement_note"].forEach(function (k) {
      if (String(notesValue(k)).trim()) n += 1;
    });
    if (String(state && state.notes ? state.notes : "").trim()) n += 1;
    return n;
  }
  function renderNotesBadge() {
    var n = notesFilledCount();
    if (n > 0) return '<span class="foms-tmf__badge">작성 ' + n + "</span>";
    return '<span class="foms-tmf__badge-none">없음</span>';
  }
  function refreshNotesBadge() {
    var host = formEl() ? formEl().querySelector("[data-tmf-notes-badge]") : null;
    if (host) host.innerHTML = renderNotesBadge();
  }
  function renderNotesCard() {
    return (
      '<details class="foms-tmf__section foms-tmf__acc" data-tmf-notes-acc>' +
      '<summary class="foms-tmf__acc-summary"><span class="foms-tmf__title">특이사항 · 비고</span>' +
      '<span class="foms-tmf__acc-summary-right">' +
      '<span class="foms-tmf__acc-badge" data-tmf-notes-badge>' +
      renderNotesBadge() +
      "</span>" +
      '<i class="fas fa-chevron-down foms-tmf__acc-chev" aria-hidden="true"></i>' +
      "</span></summary>" +
      '<div class="foms-tmf__acc-body">' +
      '<div class="foms-tmf__formgrid">' +
      textAreaField("연락처 특이사항", "phone_note", notesValue("phone_note"), { full: true, rows: 2 }) +
      textAreaField("주소 특이사항", "address_note", notesValue("address_note"), { full: true, rows: 2 }) +
      textAreaField("실측 특이사항", "measurement_note", notesValue("measurement_note"), { full: true, rows: 2 }) +
      textAreaField("비고 (현장 메모)", "notes", state.notes || "", {
        full: true,
        rows: 3,
        placeholder: "현장 특이사항 · 시공 참고 메모",
      }) +
      "</div></div></details>"
    );
  }

  // ── 렌더: ⑤ 일정(실측·시공 날짜/시간) ──────────────────────────────
  function scheduleTimeControl(stored) {
    var s = String(stored || "").trim();
    if (!s) return { select: "", direct: "", isDirect: false };
    if (TIME_PRESETS.indexOf(s) !== -1) return { select: s, direct: "", isDirect: false };
    return { select: "__direct__", direct: s, isDirect: true };
  }

  function timeControlGroup(label, selectKey, directKey, group) {
    var ctrl = scheduleTimeControl(scheduleValue(group, "time"));
    return (
      selectField(label, selectKey, ctrl.select, TIME_SELECT_OPTIONS) +
      '<div class="foms-tmf__ffield" data-tmf-time-direct="' +
      group +
      '"' +
      (ctrl.isDirect ? "" : " hidden") +
      ">" +
      '<label class="foms-tmf__flabel">' +
      escapeHtml(label + " (직접 입력)") +
      "</label>" +
      '<input class="foms-tmf__finput" type="text" autocomplete="off" data-tmf-field="' +
      directKey +
      '" value="' +
      escapeHtml(ctrl.direct) +
      '" placeholder="예: 09:30"></div>'
    );
  }

  function renderScheduleCard() {
    return (
      '<section class="foms-tmf__section">' +
      '<h5 class="foms-tmf__title">일정</h5>' +
      '<div class="foms-tmf__formgrid">' +
      textField("실측일", "measurement_date", scheduleValue("measurement", "date"), {
        placeholder: "예: 2026-07-11 (여러 날짜는 쉼표로)",
      }) +
      timeControlGroup("실측시간", "measurement_time_select", "measurement_time", "measurement") +
      textField("시공일", "construction_date", scheduleValue("construction", "date"), {
        placeholder: "예: 2026-07-24",
      }) +
      timeControlGroup("시공시간", "construction_time_select", "construction_time", "construction") +
      "</div></section>"
    );
  }

  // ── 렌더: ⑥ 주문 정보(접힘 아코디언, 전부 편집) ─────────────────────
  function renderOrderInfoCard() {
    var urgent = !!flagValue("urgent");
    var regional = !!state.top.is_regional;
    var ordererName = partyValue("orderer", "name");
    var direct = state.ordererDirect;
    var selectVal = direct ? "" : ordererName;
    return (
      '<details class="foms-tmf__section foms-tmf__acc">' +
      '<summary class="foms-tmf__acc-summary"><span class="foms-tmf__title">주문 정보 (접수·발주·담당·단계)</span>' +
      '<i class="fas fa-chevron-down foms-tmf__acc-chev" aria-hidden="true"></i></summary>' +
      '<div class="foms-tmf__acc-body">' +
      '<div class="foms-tmf__formgrid">' +
      textField("접수일", "received_date", state.top.received_date, { type: "date" }) +
      textField("접수시간", "received_time", state.top.received_time, { type: "time" }) +
      "</div>" +
      '<div class="foms-tmf__checkrow">' +
      checkboxField("긴급 발주", "urgent", urgent) +
      checkboxField("자가 실측", "self_measurement", !!state.top.is_self_measurement) +
      checkboxField("지방 주문", "regional", regional) +
      checkboxField("라홈시스템(2공장)", "factory2", !!flagValue("factory2")) +
      "</div>" +
      '<div class="foms-tmf__ffield foms-tmf__ffield--full" data-tmf-urgent-field' +
      (urgent ? "" : " hidden") +
      '><label class="foms-tmf__flabel">긴급 사유</label>' +
      '<input class="foms-tmf__finput" type="text" autocomplete="off" data-tmf-field="urgent_reason" value="' +
      escapeHtml(flagValue("urgent_reason") || "") +
      '" placeholder="예: 시공일 임박/현장 변경/자재 이슈"></div>' +
      '<div data-tmf-ctype-field' +
      (regional ? "" : " hidden") +
      ">" +
      selectField(
        "지방주문 구분",
        "construction_type",
        state.top.construction_type,
        CONSTRUCTION_TYPE_OPTIONS,
        { full: true, disabled: !regional }
      ) +
      "</div>" +
      '<div class="foms-tmf__checkrow">' +
      checkboxField("발주사 직접 입력", "orderer_direct", direct) +
      "</div>" +
      '<div class="foms-tmf__formgrid">' +
      '<div class="foms-tmf__ffield" data-tmf-orderer-wrap="select"' +
      (direct ? " hidden" : "") +
      '><label class="foms-tmf__flabel">발주사</label>' +
      '<select class="foms-tmf__finput" data-tmf-field="orderer_select">' +
      ORDERER_SELECT_OPTIONS.map(function (o) {
        var sel = String(o[0]) === String(selectVal) ? " selected" : "";
        return '<option value="' + escapeHtml(o[0]) + '"' + sel + ">" + escapeHtml(o[1]) + "</option>";
      }).join("") +
      "</select></div>" +
      '<div class="foms-tmf__ffield" data-tmf-orderer-wrap="direct"' +
      (direct ? "" : " hidden") +
      '><label class="foms-tmf__flabel">발주사 직접 입력값</label>' +
      '<input class="foms-tmf__finput" type="text" autocomplete="off" data-tmf-field="orderer" value="' +
      escapeHtml(direct ? ordererName : "") +
      '" placeholder="발주사 직접 입력"></div>' +
      textField("담당자", "manager", partyValue("manager", "name")) +
      selectField("단계 (Workflow)", "workflow_stage", workflowStage(), WORKFLOW_STAGE_OPTIONS) +
      "</div>" +
      textAreaField("시공 담당자 (여러 명은 줄바꿈/쉼표)", "construction_workers", constructionWorkersText(), {
        full: true,
        rows: 2,
        placeholder: "예: 홍길동, 김철수",
      }) +
      "</div></details>"
    );
  }

  // ── 렌더: ⑦ 금액 ───────────────────────────────────────────────────
  function renderAmountsCard() {
    var t = recomputeTotals();
    var a = state.amounts;
    return (
      '<section class="foms-tmf__section">' +
      '<h5 class="foms-tmf__title">금액</h5>' +
      '<div class="foms-tmf__kvgrid">' +
      '<div class="foms-tmf__kv"><b>출고가 (품목+배송−할인)</b><span data-tmf-derived="shipping">' +
      formatWon(t.shipping_price) +
      "</span></div>" +
      '<div class="foms-tmf__kv foms-tmf__kv--accent"><b>잔금 = 출고가 − 예약금</b><span data-tmf-derived="balance">' +
      formatWon(t.balance_amount) +
      "</span></div>" +
      "</div>" +
      '<div class="foms-tmf__formgrid">' +
      amountField("예약금 (선금)", "deposit", a.deposit, { placeholder: "0" }) +
      amountField("할인", "discount", a.discount, { placeholder: "0" }) +
      textField("자유입력 항목명", "__free_text__", a.freeText, { placeholder: "예: 배송비" }) +
      amountField("자유입력 금액 (배송비)", "free_amount", a.freeAmount, { placeholder: "0" }) +
      textField("현금영수증", "__cash_receipt__", a.cashReceipt, { placeholder: "발행 정보/번호" }) +
      "</div>" +
      textAreaField("잔금 메모", "__balance_note__", a.balanceNote, { full: true, rows: 2 }) +
      '<p class="foms-tmf__amount-note">출고가·잔금은 항목 금액·예약금·자유입력·할인으로 자동 계산됩니다.</p>' +
      "</section>"
    );
  }

  // ── 렌더: ⑧ 변환 텍스트 / 채널톡 ───────────────────────────────────
  function renderConversionCard() {
    return (
      '<section class="foms-tmf__section">' +
      '<h5 class="foms-tmf__title">변환 텍스트 · 채널톡</h5>' +
      // 발송 흔적 칩(erp-alimtalk-trace.js 소유). 좁은 폭이라 축약형이고, 이 표면엔 이력
      // 패널 마크업이 없어 칩은 표시 전용으로 그려진다.
      '<div class="erp-alimtalk-trace-slot" data-erp-alimtalk-trace="compact" ' +
      'data-erp-alimtalk-trace-order="' + escapeHtml(String((state && state.orderId) || "")) + '"></div>' +
      '<div class="foms-tmf__convo-actions">' +
      '<button type="button" class="foms-btn foms-btn--secondary foms-btn--sm" data-tmf-gen-text>' +
      '<i class="fas fa-wand-magic-sparkles" aria-hidden="true"></i><span>변환 텍스트 생성</span></button>' +
      '<button type="button" class="foms-btn foms-btn--secondary foms-btn--sm" data-tmf-copy-text>' +
      '<i class="fas fa-copy" aria-hidden="true"></i><span>복사</span></button>' +
      '<button type="button" class="foms-btn foms-btn--secondary foms-btn--sm" data-tmf-push-measurement>' +
      '<i class="fas fa-comment-dots" aria-hidden="true"></i><span>실측 PUSH (영발)</span></button>' +
      '<button type="button" class="foms-btn foms-btn--secondary foms-btn--sm" data-tmf-push-drawing>' +
      '<i class="fas fa-compass-drafting" aria-hidden="true"></i><span>도면 PUSH (발주)</span></button>' +
      '<button type="button" class="foms-btn foms-btn--secondary foms-btn--sm erp-alimtalk-send-btn" data-tmf-alimtalk-send>' +
      '<i class="fas fa-comment-dots" aria-hidden="true"></i><span>알림톡 발송</span></button>' +
      '<button type="button" class="foms-btn foms-btn--secondary foms-btn--sm erp-share-open-btn" data-tmf-share-open>' +
      '<i class="fas fa-link" aria-hidden="true"></i><span>고객 공유</span></button>' +
      "</div>" +
      '<textarea class="foms-tmf__textarea foms-tmf__convo-text" data-tmf-conversion rows="6" readonly ' +
      'placeholder="[변환 텍스트 생성]을 누르면 현재 원장 내용이 채널톡용 텍스트로 만들어집니다.">' +
      // 렌더 시점 자동 생성 금지 — 사용자가 [변환 텍스트 생성]을 눌러야만 채워진다.
      // 이미 생성한 텍스트는 탭 왕복(재렌더)에도 유지되도록 state.convText 에서 복원한다.
      escapeHtml((state && state.convText) || "") +
      "</textarea>" +
      "</section>"
    );
  }

  // ── 렌더: 탭별 ─────────────────────────────────────────────────────
  function renderNotice(inj) {
    var editHref = state.ctx && state.ctx.editUrl ? escapeHtml(state.ctx.editUrl) : "";
    inj.innerHTML =
      '<div class="foms-tmf" data-foms-tmf>' +
      '<div class="foms-tmf__notice">' +
      "<p>이 주문은 ERP 원장(구조화 데이터)이 없어 태블릿 폼으로 편집할 수 없습니다.</p>" +
      (editHref
        ? '<a class="foms-btn foms-btn--secondary" href="' + editHref + '">ERP 편집 열기</a>'
        : "") +
      "</div></div>";
  }

  function renderOrderTab(inj) {
    var formCol =
      '<div class="foms-tmf__ordercol">' +
      renderContextCard() +
      renderItemsCard() +
      renderPhotosCard() +
      renderNotesCard() +
      renderScheduleCard() +
      renderOrderInfoCard() +
      renderAmountsCard() +
      renderConversionCard() +
      "</div>";
    inj.innerHTML =
      '<div class="foms-tmf" data-foms-tmf data-order-id="' +
      escapeHtml(state.orderId) +
      '">' +
      '<div class="foms-tmf__banner" data-tmf-banner hidden role="alert">' +
      "<span>다른 곳에서 이 주문이 수정되었습니다. 최신 내용을 불러오세요.</span>" +
      '<button type="button" class="foms-btn foms-btn--sm foms-btn--secondary" data-tmf-refresh>새로고침</button>' +
      "</div>" +
      // 도면 단계 이후 수정 안내 — 서버가 PUT /structured 에서 도면팀 알림 + 이력을 자동 기록한다
      // (apply_drawing_order_change_alert). 조건 불충족이면 [hidden](기존 배너 관례).
      '<div class="foms-tmf__banner foms-tmf__banner--notify" data-tmf-drawing-notice' +
      (isPostDrawingStage() ? "" : " hidden") +
      '><span>도면 진행 중 — 여기서 수정하면 도면팀에 변경 내용이 자동 통지됩니다.</span></div>' +
      '<div class="foms-tmf__ordergrid">' +
      formCol +
      "</div></div>";
    renderPhotos();
  }

  function renderCalcTab(inj) {
    inj.innerHTML =
      '<div class="foms-tmf foms-tmf--fullpane" data-foms-tmf>' +
      '<iframe class="foms-tmf__calcframe foms-tmf__calcframe--full" src="' +
      escapeHtml(calcIframeSrc(state.orderId, partyValue("customer", "name") || (state.ctx && state.ctx.customerName))) +
      '" title="WD 계산기" loading="lazy"></iframe>' +
      "</div>";
  }

  function renderEstimateTab(inj) {
    var orderId = state && state.orderId;
    if (!orderId) {
      inj.innerHTML =
        '<div class="foms-tmf" data-foms-tmf><div class="foms-tmf__notice"><p>주문을 선택하세요.</p></div></div>';
      return;
    }
    inj.innerHTML =
      '<div class="foms-tmf foms-tmf--fullpane" data-foms-tmf>' +
      '<iframe class="foms-tmf__calcframe foms-tmf__calcframe--full foms-tmf__estframe" src="' +
      escapeHtml(estimateIframeSrc(orderId)) +
      '" title="견적서" loading="lazy"></iframe>' +
      "</div>";
  }

  function renderActiveTab() {
    var inj = injectEl();
    if (!inj) return;
    if (!isEditable() && state.activeTab === "order") {
      renderNotice(inj);
      syncTabButtons();
      return;
    }
    if (state.activeTab === "calc") {
      renderCalcTab(inj);
    } else if (state.activeTab === "estimate") {
      renderEstimateTab(inj);
    } else {
      renderOrderTab(inj);
    }
    syncTabButtons();
    // 탭 재렌더는 칩 자리를 새로 만든다(innerHTML) — 칩 모듈에 다시 그리라고 알린다.
    if (typeof window.erpAlimtalkTraceRender === "function") window.erpAlimtalkTraceRender();
  }

  function refreshItemBody() {
    var host = formEl() ? formEl().querySelector("[data-tmf-item-body]") : null;
    if (host) host.innerHTML = renderItemBody();
    // 제품 항목 수 라벨 갱신(항목 추가/삭제 시).
    var sections = formEl() ? formEl().querySelectorAll(".foms-tmf__title") : [];
    Array.prototype.forEach.call(sections, function (h) {
      if (/^실측 기록 · 제품 항목/.test(h.textContent || "")) {
        h.textContent = "실측 기록 · 제품 항목 " + itemsList().length;
      }
    });
  }

  function refreshSpecPanel() {
    var host = formEl() ? formEl().querySelector("[data-tmf-spec-panel]") : null;
    if (host) host.innerHTML = renderItemSpec();
  }

  function refreshJasuOnly() {
    var form = formEl();
    if (!form) return;
    var item = itemsList()[state.activeItem];
    var wrap = form.querySelector(".foms-tmf__jasu");
    if (!wrap) return;
    var strong = wrap.querySelector("strong");
    var jasu = itemJasuDisplay(item);
    if (strong) strong.textContent = jasu;
    wrap.hidden = !jasu;
  }

  function updateDerivedAmounts() {
    var form = formEl();
    if (!form) return;
    var t = recomputeTotals();
    var shipEl = form.querySelector('[data-tmf-derived="shipping"]');
    var balEl = form.querySelector('[data-tmf-derived="balance"]');
    if (shipEl) shipEl.textContent = formatWon(t.shipping_price);
    if (balEl) balEl.textContent = formatWon(t.balance_amount);
  }

  // ── 사진(갤러리 + 업로드) ───────────────────────────────────────────
  function renderPhotos() {
    var host = formEl() ? formEl().querySelector("[data-tmf-photos]") : null;
    if (!host) return;
    var orderId = state.orderId;
    fetch(attachmentsUrl(orderId), { credentials: "same-origin" })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (!state || state.orderId !== orderId) return;
        var host2 = formEl() ? formEl().querySelector("[data-tmf-photos]") : null;
        if (!host2) return;
        var list = data && data.success && Array.isArray(data.attachments) ? data.attachments : [];
        state.photos = list;
        if (!list.length) {
          host2.innerHTML = '<div class="foms-tmf__photo-empty">등록된 실측 사진이 없습니다.</div>';
          return;
        }
        host2.innerHTML = list
          .map(function (att, idx) {
            var url = att.view_url || att.url || "";
            var name = att.filename || "사진";
            var isVideo = /\.(mp4|webm|ogg|mov)$/i.test(url) || /\.(mp4|webm|ogg|mov)$/i.test(name);
            var inner = isVideo
              ? '<span class="foms-tmf__photo-video"><i class="fas fa-play" aria-hidden="true"></i></span>'
              : '<img src="' + escapeHtml(url) + '" alt="' + escapeHtml(name) + '" loading="lazy">';
            return (
              '<button type="button" class="foms-tmf__photo" data-tmf-photo="' +
              idx +
              '" title="' +
              escapeHtml(name) +
              '">' +
              inner +
              "</button>"
            );
          })
          .join("");
      })
      .catch(function () {
        if (!state || state.orderId !== orderId) return;
        var host3 = formEl() ? formEl().querySelector("[data-tmf-photos]") : null;
        if (host3) host3.innerHTML = '<div class="foms-tmf__photo-empty">사진을 불러오지 못했습니다.</div>';
      });
  }

  function openPhoto(idx) {
    var list = state && Array.isArray(state.photos) ? state.photos : [];
    if (!list.length) return;
    if (window.GlobalImageViewer && typeof window.GlobalImageViewer.open === "function") {
      var files = list.map(function (att) {
        return {
          url: att.view_url || att.url || "",
          view_url: att.view_url || att.url || "",
          download_url: att.download_url || "",
          filename: att.filename || "사진",
          key: att.key || att.storage_key || null,
        };
      });
      window.GlobalImageViewer.open(files, idx);
      return;
    }
    var one = list[idx];
    if (one && (one.view_url || one.url)) window.open(one.view_url || one.url, "_blank", "noopener");
  }

  // 카메라/갤러리 파일 → 순차 업로드(멀티파트). scene=현장 사진(카테고리 select), item=활성 항목(item_index).
  function uploadFiles(input) {
    if (!state || !isEditable()) return;
    var files = input && input.files ? Array.prototype.slice.call(input.files) : [];
    if (!files.length) return;
    var kind = input.getAttribute("data-tmf-upload");
    var orderId = state.orderId;
    var form = formEl();
    var catEl = form ? form.querySelector("[data-tmf-photo-cat]") : null;
    var category = kind === "item" ? "measurement" : (catEl && catEl.value) || "measurement";
    var itemIndex = kind === "item" ? state.activeItem : null;
    var total = files.length;
    var done = 0;
    var failed = 0;
    setStatus("사진 업로드 중… (0/" + total + ")", "saving");

    function uploadOne(i) {
      if (i >= files.length) {
        input.value = "";
        if (!state || state.orderId !== orderId) return;
        if (failed) setStatus("사진 " + (total - failed) + "/" + total + " 업로드 (실패 " + failed + ")", failed === total ? "error" : "saved");
        else setStatus("사진 " + total + "장 업로드 완료", "saved");
        renderPhotos();
        return;
      }
      var fd = new FormData();
      fd.append("file", files[i]);
      fd.append("category", category);
      if (itemIndex != null) fd.append("item_index", String(itemIndex));
      fetch(attachmentsUploadUrl(orderId), { method: "POST", credentials: "same-origin", body: fd })
        .then(function (res) {
          return res.json().then(function (d) {
            return { ok: res.ok, data: d };
          });
        })
        .then(function (r) {
          if (!r.data || !r.data.success) failed += 1;
          done += 1;
          if (state && state.orderId === orderId) {
            setStatus("사진 업로드 중… (" + done + "/" + total + ")", "saving");
          }
          uploadOne(i + 1);
        })
        .catch(function () {
          failed += 1;
          done += 1;
          uploadOne(i + 1);
        });
    }
    uploadOne(0);
  }

  // ── 저장(PUT read-merge-write) ──────────────────────────────────────
  function normalizedConstructionType() {
    return String(state.top.construction_type || "").trim();
  }

  function buildPayload() {
    recomputeTotals();
    normalizeItemsForSave();
    var payload = {
      structured_data: state.structured,
      structured_schema_version: state.schemaVersion || 1,
      notes: state.notes != null ? state.notes : "",
    };
    if (state.confidence != null) payload.structured_confidence = state.confidence;

    // top-level 컬럼: baseline 과 다를 때만 포함(키 부재=서버 보존, GET 원값 에코=안전).
    var b = state.topBaseline;
    var t = state.top;
    if (t.received_date !== b.received_date) payload.received_date = t.received_date;
    if (t.received_time !== b.received_time) payload.received_time = t.received_time;
    if (t.is_self_measurement !== b.is_self_measurement) payload.is_self_measurement = !!t.is_self_measurement;

    // is_regional / construction_type 쌍 계약: 하나라도 변경 시 둘 다 함께 포함.
    // 단, 지방 ON + 구분 미선택(무효 쌍)이면 생략(서버 400 방지) — 명시 저장은 사전 가드에서 차단.
    var regionalChanged = !!t.is_regional !== !!b.is_regional;
    var ctypeChanged = normalizedConstructionType() !== String(b.construction_type || "").trim();
    if (regionalChanged || ctypeChanged) {
      var validPair = !t.is_regional || (t.is_regional && normalizedConstructionType());
      if (validPair) {
        payload.is_regional = !!t.is_regional;
        payload.construction_type = t.is_regional ? normalizedConstructionType() : "";
      }
    }
    return payload;
  }

  function scheduleAutosave() {
    if (!state) return;
    state.dirty = true;
    window.clearTimeout(state.saveTimer);
    state.saveTimer = window.setTimeout(function () {
      saveNow({ explicit: false });
    }, AUTOSAVE_DEBOUNCE_MS);
    setStatus("변경됨", "");
  }

  function checkConflict(orderId) {
    return fetch(structuredUrl(orderId), { credentials: "same-origin" })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.success) return false;
        if (state.baselineUpdatedAt == null) return false;
        return data.structured_updated_at !== state.baselineUpdatedAt;
      })
      .catch(function () {
        return false;
      });
  }

  function refreshBaseline(orderId) {
    return fetch(structuredUrl(orderId), { credentials: "same-origin" })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (data && data.success && state && state.orderId === orderId) {
          state.baselineUpdatedAt = data.structured_updated_at;
          // top-level baseline 재동기화(서버가 정규화한 값 반영 → 다음 저장 clobber 방지).
          state.topBaseline = {
            received_date: data.received_date || "",
            received_time: data.received_time || "",
            is_self_measurement: !!data.is_self_measurement,
            is_regional: !!data.is_regional,
            construction_type: data.construction_type || "",
          };
          state.top = {
            received_date: state.top.received_date,
            received_time: state.top.received_time,
            is_self_measurement: state.top.is_self_measurement,
            is_regional: state.top.is_regional,
            construction_type: state.top.construction_type,
          };
        }
      })
      .catch(function () {});
  }

  function putStructured(orderId, payload) {
    return fetch(structuredUrl(orderId), {
      method: "PUT",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    }).then(function (res) {
      return res.json().then(function (data) {
        return { ok: res.ok, status: res.status, data: data };
      });
    });
  }

  function showConflictBanner() {
    var form = formEl();
    var banner = form ? form.querySelector("[data-tmf-banner]") : null;
    if (banner) banner.hidden = false;
    setStatus("충돌 — 저장 중단", "conflict");
  }

  // 저장 성공 여부로 resolve 되는 Promise 를 반환한다(실측 완료가 "저장 성공 후에만 승인 호출"
  // 을 체이닝하는 데 사용 — 실패 시 승인 금지).
  function saveNow(opts) {
    opts = opts || {};
    if (!state || !isEditable()) return Promise.resolve(false);
    var explicit = !!opts.explicit;
    var isDraft = !!opts.draft;

    // 지방 ON + 구분 미선택 → 명시 저장/실측완료 차단(서버 쌍 400 방지, PC 미러).
    if (explicit && state.top.is_regional && !normalizedConstructionType()) {
      setStatus("지방주문 구분(하우드/협력사)을 선택해주세요.", "error");
      var ctypeSel = formEl() ? formEl().querySelector('[data-tmf-field="construction_type"]') : null;
      if (ctypeSel && typeof ctypeSel.focus === "function") ctypeSel.focus();
      return Promise.resolve(false);
    }

    if (state.saving) {
      state.pendingSave = true;
      return Promise.resolve(false);
    }
    window.clearTimeout(state.saveTimer);
    var orderId = state.orderId;
    var saved = false;

    state.saving = true;
    setStatus(isDraft ? "임시 저장 중…" : "저장 중…", "saving");

    var pre = explicit ? checkConflict(orderId) : Promise.resolve(false);
    return pre
      .then(function (conflict) {
        if (conflict) {
          state.saving = false;
          showConflictBanner();
          return null;
        }
        return putStructured(orderId, buildPayload());
      })
      .then(function (result) {
        if (result == null) return;
        if (!state || state.orderId !== orderId) return;
        if (result.data && result.data.success) {
          saved = true;
          state.dirty = false;
          setStatus(isDraft ? "임시 저장됨" : "저장됨", "saved");
          showAutosaveBadge((isDraft || !explicit ? "자동저장됨" : "저장됨") + " · 방금");
          refreshBaseline(orderId);
        } else {
          var msg = (result.data && result.data.message) || "저장 실패";
          setStatus(msg, "error");
        }
      })
      .catch(function () {
        setStatus("네트워크 오류 — 저장 실패", "error");
      })
      .then(function () {
        if (state && state.orderId === orderId) {
          state.saving = false;
          if (state.pendingSave) {
            state.pendingSave = false;
            saveNow({ explicit: false });
          }
        }
        return saved;
      });
  }

  function markCardCompleted() {
    var card = document.querySelector(".foms-tablet-measure-card.is-active");
    if (card) card.classList.add("is-completed");
  }

  // 실측 완료 = MEASURE 퀘스트 승인(POST /quest/approve) 단일 경로. 서버가 승인자·시각을 기록하고,
  // 최종 승인이면 같은 트랜잭션에서 정본 전이 엔진(quest_transition_service → order_transition_service)
  // 으로 workflow.stage MEASURE→DRAWING + order.status projection 까지 처리한다. DRAWING 퀘스트는
  // 만들지 않는다(도면은 전용 command 소관).
  // (클라이언트가 stage 를 직접 세팅하던 반쪽 전환 폐기 — 단계 전환 SSOT 는 서버 하나.)
  function approveMeasureQuest(orderId) {
    setStatus("도면 전달 중…", "saving");
    // MEASURE 는 approval_mode="assignee" → 팀 지정 없는 빈 body.
    return fetch("/api/orders/" + encodeURIComponent(orderId) + "/quest/approve", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: "{}",
    })
      .then(function (res) {
        return res.json().then(function (data) {
          return { ok: res.ok, data: data || {} };
        });
      })
      .then(function (result) {
        if (!result.ok || !result.data.success) {
          // 저장은 이미 성공했으므로 롤백하지 않는다(입력 데이터 보존 우선).
          setStatus(result.data.message || result.data.error || "도면 전달 실패", "error");
          return;
        }
        markCardCompleted();
        if (!state || state.orderId !== orderId) return;
        // 새 단계(DRAWING) 를 폼 전체에 반영 — 기존 리프레시 수단(load) 재사용.
        return load(orderId, state.ctx).then(function () {
          setStatus("실측 완료 — 도면 단계로 전달됨", "saved");
        });
      })
      .catch(function () {
        setStatus("네트워크 오류 — 도면 전달 실패(입력 내용은 저장됨)", "error");
      });
  }

  function flushPending() {
    if (state && state.dirty && !state.saving && isEditable()) {
      saveNow({ explicit: false });
    }
  }

  // ── 변환 텍스트 SSOT 미러 (PC static/js/orders/erp-order-shared.js) ─────────────────
  // 아래 conv* 헬퍼·buildConversionText·sliceConversionTextForChannelPush 는 PC 의
  //   erpGenerateConversionText / erpAppendConversion* / erpFormatFreeInputForConversion /
  //   erpSliceConversionTextForChannelPush
  // 를 문자 단위로 미러한 것이다(동일 입력 structured_data/amounts → PC 와 동일 출력이 계약).
  // PC 는 DOM input 에서 값을 읽지만 이 페이지엔 PC 번들이 없으므로 state 에서 같은 값을 읽는다.
  // ★ 동기화 지점: PC 함수가 바뀌면 여기도 함께 고쳐야 한다(라인 주석 = PC 원본 위치).

  // PC erpFormatMoneyKRW (erp-order-shared.js:709)
  function convFormatMoneyKRW(num) {
    var n = Number(num);
    if (!isFinite(n)) return "0원";
    return Math.round(n).toLocaleString("ko-KR") + "원";
  }
  // PC erpHasConversionTextValue (erp-order-shared.js:4046)
  function convHasValue(value) {
    return String(value == null ? "" : value).trim().length > 0;
  }
  // PC erpGenerateConversionText 내부 formatDateToKorean (erp-order-shared.js:4147)
  function convFormatDateToKorean(dateStr) {
    if (!dateStr) return "";
    var single = function (s) {
      var t = String(s).trim();
      var match = t.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (match) return parseInt(match[2], 10) + "월 " + parseInt(match[3], 10) + "일";
      return t || "";
    };
    var parts = String(dateStr).split(",").map(single).filter(Boolean);
    return parts.length ? parts.join(", ") : dateStr;
  }
  // PC erpAppendConversionTextLine (erp-order-shared.js:4050)
  function convAppendLine(text, label, value) {
    var raw = String(value == null ? "" : value).replace(/\r\n/g, "\n").replace(/\r/g, "\n");
    var trimmed = raw.trim();
    if (!trimmed) return text;
    if (trimmed.indexOf("\n") === -1) return text + label + " : " + trimmed + "\n";
    var lines = trimmed.split("\n");
    var out = text + label + " : " + String(lines[0] || "").trim() + "\n";
    for (var i = 1; i < lines.length; i += 1) {
      var line = lines[i].trim();
      if (line) out += line + "\n";
    }
    return out;
  }
  // PC erpAppendConversionExtraInputLine (erp-order-shared.js:4066)
  function convAppendExtraInputLine(text, value) {
    var raw = String(value == null ? "" : value).trim();
    if (!raw) return text;
    var lines = raw.replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
    var first = String(lines[0] || "").trim();
    if (!first) return text;
    var out = text + "추가 입력 : " + first + "\n";
    for (var i = 1; i < lines.length; i += 1) {
      var line = lines[i].trim();
      if (line) out += line + "\n";
    }
    return out;
  }
  // PC erpFormatFreeInputForConversionLine (erp-order-shared.js:812)
  function convFormatFreeInputLine(line) {
    var trimmed = String(line == null ? "" : line).trim();
    if (!trimmed) return "";
    var colonMatch = trimmed.match(/^(.+?)[:：]\s*(.+)$/);
    if (colonMatch) {
      var label = colonMatch[1].trim();
      var amountPart = colonMatch[2].trim();
      if (/원$/.test(amountPart)) return label + " : " + amountPart;
      var amount = coerceAmount(amountPart);
      if (amount > 0) return label + " : " + convFormatMoneyKRW(amount);
      return trimmed;
    }
    if (/원$/.test(trimmed)) return trimmed;
    var asAmount = coerceAmount(trimmed);
    if (asAmount > 0) return convFormatMoneyKRW(asAmount);
    return trimmed;
  }
  // PC erpFormatFreeInputForConversion (erp-order-shared.js:797)
  function convFormatFreeInputForConversion(value) {
    var raw = String(value == null ? "" : value).trim();
    if (!raw) return "";
    return raw
      .replace(/\r\n/g, "\n")
      .replace(/\r/g, "\n")
      .split("\n")
      .map(convFormatFreeInputLine)
      .filter(function (l) {
        return !!l;
      })
      .join("\n");
  }
  // PC erpAppendConversionFreeInputBlock (erp-order-shared.js:4080)
  function convAppendFreeInputBlock(text, value) {
    var formatted = convFormatFreeInputForConversion(value);
    if (!formatted) return text;
    var withSuffix = formatted
      .split("\n")
      .map(function (l) {
        return l ? l + "(총견적 포함)" : l;
      })
      .join("\n");
    return text + withSuffix + "\n";
  }
  // PC erpAppendConversionMoneyLine (erp-order-shared.js:4096)
  function convAppendMoneyLine(text, label, amount, suffix) {
    var n = coerceAmount(amount);
    if (n <= 0) return text;
    var tail = suffix ? String(suffix) : "";
    return text + label + " : " + convFormatMoneyKRW(n) + tail + "\n";
  }
  // PC erpSliceConversionTextForChannelPush (erp-order-shared.js) — 채널톡 전송용 슬라이스.
  // 실측일/시간 헤더만 제거. ★★·실측 특이사항·주소/연락처 특이사항은 유지.
  function sliceConversionTextForChannelPush(text) {
    var raw = String(text == null ? "" : text).trim();
    if (!raw) return "";
    var hasFactory2Stars = raw.split("\n").some(function (line) {
      return /^\s*★★\s*$/.test(line);
    });
    var body = raw
      .split("\n")
      .filter(function (line) {
        return !/^\s*★★\s*$/.test(line) && !/^\s*실측일\s*:/.test(line) && !/^\s*시\s*간\s*:/.test(line);
      })
      .join("\n")
      .replace(/^\n+/, "")
      .trim();
    if (!hasFactory2Stars) return body;
    if (!body) return "★★";
    return "★★\n" + body;
  }

  // ── 채널톡 변환 텍스트 → 수동 푸쉬 ──────────────────────────────────
  // PC erpGenerateConversionText (erp-order-shared.js:4141) 의 문자 단위 미러.
  function buildConversionText() {
    if (!state) return "";
    var measurementDate = convFormatDateToKorean(scheduleValue("measurement", "date"));
    var measurementTime = scheduleValue("measurement", "time");

    var customerName = partyValue("customer", "name");
    var orderer = String(partyValue("orderer", "name") || "").trim();
    if (!orderer) orderer = "라홈";

    var constructionDate = scheduleValue("construction", "date");
    if (!constructionDate) constructionDate = "상담";
    else constructionDate = convFormatDateToKorean(constructionDate);

    var constructionTime = scheduleValue("construction", "time");
    var address = siteAddress();
    var phone = partyValue("customer", "phone");
    var factory2Checked = !!flagValue("factory2");

    // 헤더 + 고객(값 없는 라인은 제외). factory2 체크 시 실측일 위에 ★★.
    var text = "";
    if (factory2Checked) text += "★★\n";
    text = convAppendLine(text, "실측일", measurementDate);
    text = convAppendLine(text, "시   간", measurementTime);
    // 실측 특이사항 → 실측 블록(실측일/시간) 바로 아래 (PC erpGenerateConversionText 미러)
    text = convAppendLine(text, "실측 특이사항", notesValue("measurement_note"));
    if (text) text += "\n";
    text = convAppendLine(text, "고객명", customerName);
    text = convAppendLine(text, "발주사", orderer);
    text = convAppendLine(text, "시공일", constructionDate);
    // 시공 특이사항 → 시공일 바로 아래 (PC 변환·채널톡 PUSH 흐름 미러)
    text = convAppendLine(text, "시공 특이사항", notesValue("construction_note"));
    text = convAppendLine(text, "시공시간", constructionTime);
    text = convAppendLine(text, "주  소", address);
    // 주소 특이사항 → 주소 바로 아래
    text = convAppendLine(text, "주소 특이사항", notesValue("address_note"));
    text = convAppendLine(text, "연락처", phone);
    // 연락처 특이사항 → 연락처 바로 아래
    text = convAppendLine(text, "연락처 특이사항", notesValue("phone_note"));
    if (text && text.slice(-2) !== "\n\n") text += "\n";

    // 항목
    var items = itemsList();
    var itemCount = items.length;
    var visibleItemIndex = 0;
    items.forEach(function (item) {
      if (!item || typeof item !== "object") return;
      var extraInput = item.extra_input;
      var pName = item.product_name || item.name || "";
      // PC: rawSpec(=data-erp="spec") || spec 행 W*D*H 를 '*' 로, 행은 ', ' 로. item.spec 이 rawSpec 대응.
      var rawSpec = String(item.spec == null ? "" : item.spec).trim();
      var specParts = [];
      (Array.isArray(item.spec_rows) ? item.spec_rows : []).forEach(function (row) {
        if (!row || typeof row !== "object") return;
        var w = String(specDim(row, "spec_width", "w")).trim();
        var d = String(specDim(row, "spec_depth", "d")).trim();
        var h = String(specDim(row, "spec_height", "h")).trim();
        var one = [w, d, h].filter(Boolean).join("*");
        if (one) specParts.push(one);
      });
      var spec = rawSpec || (specParts.length ? specParts.join(", ") : "");

      // PC erpNewItemRow 미러: internal/option/handle/misc 는 defaultConsult, color 는 (SK) 접미어 제거 후 상담 기본.
      var internal = defaultConsult(item.internal);
      var color = String(item.color == null ? "" : item.color).replace(/(\s+\(SK\))+$/g, "").trim() || "상담";
      var option = defaultConsult(item.option_detail);
      var handle = defaultConsult(item.handle);
      var misc = defaultConsult(item.misc);
      var itemPrice = item.price;

      var itemText = "";
      itemText = convAppendLine(itemText, "제품명", pName);
      itemText = convAppendLine(itemText, "규 격", spec);
      itemText = convAppendLine(itemText, "내 부", internal);
      itemText = convAppendLine(itemText, "색 상", color);
      itemText = convAppendLine(itemText, "옵 션", option);
      itemText = convAppendLine(itemText, "손잡이", handle);
      itemText = convAppendLine(itemText, "기 타", misc);
      itemText = convAppendMoneyLine(itemText, "항목 견적", itemPrice);
      itemText = convAppendExtraInputLine(itemText, extraInput);
      if (!itemText) return;
      visibleItemIndex += 1;
      if (itemCount >= 2) text += visibleItemIndex + ".\n";
      text += itemText;
      text += "\n";
    });

    // 푸터: 담당자 + 출고가 + 예약금 + 자유입력 + 잔금(+메모/현금영수증).
    var manager = partyValue("manager", "name");
    var a = state.amounts || {};
    var totals = buildTotals(sumItemsTotal(), a.deposit, a.discount, a.freeAmount);
    var freeInputVal = buildFreeInputStored(a.freeText, a.freeAmount);

    var footerStart = text.length;
    text = convAppendLine(text, "담당자", manager);
    if (text.length > footerStart) text += "\n";
    text = convAppendMoneyLine(text, "출고가", totals.shipping_price);
    text = convAppendMoneyLine(text, "예약금(선금)", totals.deposit_amount);
    text = convAppendFreeInputBlock(text, freeInputVal);
    var balanceSuffix = state.paymentBase && state.paymentBase.balance_confirmed ? "(결제 완)" : "";
    text = convAppendMoneyLine(text, "잔금", totals.final_amount, balanceSuffix);
    text = convAppendLine(text, "잔금메모", a.balanceNote);
    var cashReceiptVal = a.cashReceipt;
    if (convHasValue(cashReceiptVal) && totals.final_amount > 0) text += "\n";
    text = convAppendLine(text, "현금영수증", cashReceiptVal);
    text = text.replace(/\n+$/, "");
    return text;
  }

  function refreshConversionText() {
    var form = formEl();
    var ta = form ? form.querySelector("[data-tmf-conversion]") : null;
    var text = buildConversionText();
    if (state) state.convText = text; // 재렌더에도 미리보기 유지(=생성한 결과 보존).
    if (ta) ta.value = text;
    return ta;
  }

  function copyConversionText() {
    var ta = refreshConversionText();
    var text = ta ? ta.value : buildConversionText();
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(text).then(
        function () {
          setStatus("변환 텍스트 복사됨", "saved");
        },
        function () {
          legacyCopy(ta);
        }
      );
      return;
    }
    legacyCopy(ta);
  }
  function legacyCopy(ta) {
    try {
      if (ta && typeof ta.select === "function") {
        ta.removeAttribute("readonly");
        ta.select();
        document.execCommand("copy");
        ta.setAttribute("readonly", "readonly");
        setStatus("변환 텍스트 복사됨", "saved");
        return;
      }
    } catch (e) {}
    setStatus("복사 실패 — 텍스트를 직접 선택해 복사하세요.", "error");
  }

  // PC erpRunChannelPush (erp-order-shared.js:4649) 미러: POST /api/channel/push-manual 로
  // {order_id, text, push_kind, change_note?} 를 보낸다. text 는 PC 와 동일하게 슬라이스된 변환 텍스트.
  // 재전송(prev push)은 PC 처럼 서버 400('재전송 시 변경 내용...') 감지 → note 프롬프트 → 재시도로
  // 처리한다(PC 의 M1 복구 경로). 이 페이지엔 PC 의 client push-state/모달이 없어 서버 구동 흐름만
  // 미러하며, push 이력은 서버가 structured_data 에 저장하므로 다음 전송의 재전송 판정도 서버가 담당.
  function pushManual(orderId, text, pushKind, changeNote, resendUsed) {
    var body = { order_id: orderId, text: text, push_kind: pushKind || "measurement" };
    if (changeNote) body.change_note = changeNote;
    fetch("/api/channel/push-manual", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    })
      .then(function (res) {
        return res.json().then(function (d) {
          return { ok: res.ok, status: res.status, data: d };
        });
      })
      .then(function (r) {
        if (!state || state.orderId !== orderId) return;
        if (r.data && r.data.success) {
          setStatus(pushKind === "drawing" ? "발주 PUSH 전송 완료" : "영발 PUSH 전송 완료", "saved");
          return;
        }
        var msg = (r.data && (r.data.error || r.data.message)) || "채널톡 전송 실패";
        // PC erpIsChannelPushResendNoteRequired 미러: 메시지에 '재전송 시 변경 내용' 포함 = note 필수.
        if (!resendUsed && String(msg).indexOf("재전송 시 변경 내용") >= 0) {
          var note = window.prompt("이미 전송된 이력이 있습니다. 변경 내용을 입력하면 재전송합니다.", "");
          if (note && note.trim()) {
            setStatus("채널톡 재전송 중…", "saving");
            pushManual(orderId, text, pushKind, note.trim(), true);
            return;
          }
          setStatus("채널톡 전송 취소", "");
          return;
        }
        setStatus(msg, "error");
      })
      .catch(function () {
        if (state && state.orderId === orderId) setStatus("채널톡 전송 실패(네트워크)", "error");
      });
  }

  // 알림톡 사유 코드 → 문구. erp-alimtalk-send.js 의 REASON_LABELS 미러(태블릿은 그 파일이
  // 로드되지 않는 대시보드에서 동작하므로 채널톡 pushManual 선례대로 자체 구현한다).
  var ALIMTALK_REASONS = {
    order_not_found: "주문을 찾을 수 없습니다",
    not_configured: "알림톡 서버 설정이 없습니다",
    not_eligible: "실측 일정이 확정되지 않았습니다",
    no_valid_phone: "고객 휴대폰 번호가 올바르지 않습니다",
    brand_profile_missing: "이 발주사의 알림톡 발신프로필이 아직 등록되지 않았습니다",
    auth: "알림톡 인증 정보가 올바르지 않습니다",
    balance: "알림톡 잔액이 부족합니다",
    template_mismatch: "승인된 템플릿과 본문이 일치하지 않습니다",
    invalid_phone: "수신 번호가 올바르지 않습니다",
    length_exceeded: "본문이 1,000자를 넘었습니다",
    network: "전송 중 네트워크 오류가 발생했습니다",
  };

  function alimtalkReason(code) {
    return ALIMTALK_REASONS[code] || String(code || "알 수 없는 오류");
  }

  // 발송 흔적 칩(erp-alimtalk-trace.js)도 실패 사유를 사람 문구로 그린다. 이 표면엔
  // erp-alimtalk-send.js 가 없으므로 여기 맵을 같은 이름으로 내준다(문구 갈림 방지).
  if (typeof window.erpAlimtalkReasonLabel !== "function") {
    window.erpAlimtalkReasonLabel = alimtalkReason;
  }

  /**
   * 마지막 발송 이력을 발송 흔적 칩에 전달한다(erp-alimtalk-trace.js 가 듣는다).
   *
   * 칩 모듈은 PC 화면의 전역 구조화 데이터를 읽는데 태블릿엔 그 전역이 없다. 그래서 이력만
   * 이벤트로 실어 보낸다 — 칩 마크업·문구·상태 판정은 한 곳(칩 모듈)에만 둔다.
   *
   * @param {Object|null} record `alimtalk_measurement` 이력.
   */
  function publishAlimtalkTrace(record) {
    document.dispatchEvent(
      new CustomEvent("foms:alimtalk-trace-update", { detail: { record: record || null } })
    );
  }

  function sendAlimtalk(orderId) {
    setStatus("알림톡 발송 중…", "saving");
    // CSRF 헤더는 layout_head 전역 fetch 래퍼가 붙인다(라우트별 ad hoc 주입 금지).
    fetch("/api/kakao/alimtalk/send-manual/" + orderId, {
      method: "POST",
      credentials: "same-origin",
    })
      .then(function (res) {
        return res.json();
      })
      .then(function (body) {
        if (!state || state.orderId !== orderId) return;
        var last = body && body.data ? body.data.last : null;
        if (last) {
          state.structured.alimtalk_measurement = last;
          publishAlimtalkTrace(last);
        }
        if (body && body.success && body.data && body.data.sent) {
          setStatus("알림톡 발송 완료", "saved");
          return;
        }
        var code = (body && (body.error || (body.data && body.data.error))) || "network";
        setStatus("알림톡 발송 실패 · " + alimtalkReason(code), "error");
      })
      .catch(function () {
        if (state && state.orderId === orderId) {
          setStatus("알림톡 발송 실패 · " + alimtalkReason("network"), "error");
        }
      });
  }

  // 미리보기(서버 렌더) 확인 후 발송. 태블릿에는 미리보기 modal 마크업이 없으므로
  // window.confirm 으로 본문을 보여준다(PC/모바일은 erp_alimtalk_modal.html 사용).
  function requestAlimtalk() {
    if (!state) return;
    var orderId = state.orderId;
    setStatus("알림톡 미리보기 불러오는 중…", "saving");
    fetch("/api/kakao/alimtalk/preview/" + orderId, { credentials: "same-origin" })
      .then(function (res) {
        return res.json();
      })
      .then(function (body) {
        if (!state || state.orderId !== orderId) return;
        if (!body || !body.success || !body.data) {
          setStatus("미리보기 실패 · " + alimtalkReason(body && body.error), "error");
          return;
        }
        var d = body.data;
        if (!d.configured) {
          setStatus("알림톡 서버 설정이 없습니다", "error");
          return;
        }
        if (!d.eligible) {
          setStatus("발송 불가 · " + alimtalkReason(d.ineligible_reason), "error");
          return;
        }
        var warn = "";
        if (d.last && (d.last.sent_at || d.last.error)) {
          warn = "\n\n[주의] 이미 발송 이력이 있습니다. 확인 시 고객에게 다시 발송됩니다.";
        }
        if (!window.confirm("아래 내용으로 알림톡을 발송합니다.\n\n" + (d.text || "") + warn)) {
          setStatus("", "");
          return;
        }
        sendAlimtalk(orderId);
      })
      .catch(function () {
        if (state && state.orderId === orderId) {
          setStatus("미리보기 실패 · " + alimtalkReason("network"), "error");
        }
      });
  }

  // ── 고객 공유 링크 (Phase A T9) ─────────────────────────────────────
  // erp-share.js 미러 — 태블릿엔 공유 모달 마크업이 없으므로(알림톡 선례) confirm/
  // setStatus 로 같은 흐름을 자체 구현한다. 발급 → URL 복사 → (선택) 문자 발송.
  // 토큰 원문은 발급 응답 지역변수에만 존재한다(§1 해시-온리 — 저장·재표시 불가).
  var SHARE_REASONS = {
    order_not_found: "주문을 찾을 수 없습니다",
    token_mismatch: "링크 정보가 맞지 않습니다 — 다시 발급해 주세요",
    share_expired: "만료된 링크입니다 — 다시 발급해 주세요",
    share_revoked: "회수된 링크입니다 — 다시 발급해 주세요",
    no_valid_phone: "고객 휴대폰 번호가 올바르지 않습니다",
    not_configured: "문자 발신 설정이 없습니다",
    duplicate_send: "방금 발송을 시도했습니다 — 잠시 후 다시 시도해 주세요",
    network: "네트워크 오류가 발생했습니다",
  };

  function shareReason(code) {
    return SHARE_REASONS[code] || String(code || "알 수 없는 오류");
  }

  function copyShareUrl(url) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      navigator.clipboard.writeText(url).then(
        function () {
          setStatus("공유 링크 복사됨 (30일 유효)", "saved");
        },
        function () {
          setStatus("복사 실패 — 문자 발송으로 전달해 주세요.", "error");
        }
      );
      return;
    }
    setStatus("복사 실패 — 문자 발송으로 전달해 주세요.", "error");
  }

  function sendShareSms(shareId, token, orderId) {
    setStatus("공유 링크 문자 발송 중…", "saving");
    fetch("/api/share/send-sms/" + shareId, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token: token }),
    })
      .then(function (res) {
        return res.json();
      })
      .then(function (body) {
        if (!state || state.orderId !== orderId) return;
        var sent = !!(body && body.success && body.data && body.data.sent);
        if (sent) {
          setStatus("공유 링크 문자 발송 완료", "saved");
          return;
        }
        var code = (body && (body.error || (body.data && body.data.error))) || "network";
        setStatus("문자 발송 실패 · " + shareReason(code), "error");
      })
      .catch(function () {
        if (state && state.orderId === orderId) {
          setStatus("문자 발송 실패 · " + shareReason("network"), "error");
        }
      });
  }

  function requestShare() {
    if (!state) return;
    var orderId = state.orderId;
    if (!window.confirm("고객이 로그인 없이 볼 수 있는 도면 열람 링크를 발급할까요?\n(링크는 30일간 유효합니다)")) {
      return;
    }
    setStatus("공유 링크 발급 중…", "saving");
    fetch("/api/share/create/" + orderId, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ kind: "drawing" }),
    })
      .then(function (res) {
        return res.json();
      })
      .then(function (body) {
        if (!state || state.orderId !== orderId) return;
        if (!body || !body.success || !body.data) {
          setStatus("공유 링크 발급 실패 · " + shareReason(body && body.error), "error");
          return;
        }
        var d = body.data;
        copyShareUrl(d.url);
        // 문자는 발급 직후에만 가능(§1 — 토큰 원문은 이 응답에만 존재).
        if (window.confirm("고객 휴대폰으로 링크를 문자로도 보낼까요?")) {
          sendShareSms(d.share_id, d.token, orderId);
        }
      })
      .catch(function () {
        if (state && state.orderId === orderId) {
          setStatus("공유 링크 발급 실패 · " + shareReason("network"), "error");
        }
      });
  }

  function requestPush(pushKind) {
    if (!state || !isEditable()) return;
    var text = sliceConversionTextForChannelPush(buildConversionText());
    if (!text) {
      setStatus("변환할 내용이 없습니다. 주문 정보를 입력해주세요.", "error");
      return;
    }
    setStatus(pushKind === "drawing" ? "발주 PUSH 전송 중…" : "영발 PUSH 전송 중…", "saving");
    pushManual(state.orderId, text, pushKind, "", false);
  }

  // ── 공개 API(tablet-measurement.js 가 구동) ────────────────────────
  // 렌더 완료 시 resolve 되는 Promise 를 반환한다(실측 완료 후 새 단계 반영 체이닝에 사용).
  function load(orderId, ctx) {
    // 이전 주문의 미저장 편집을 새 주문 로드 전에 flush(카드 전환 시 유실 방지).
    flushPending();

    var inj = injectEl();
    if (inj) {
      inj.innerHTML = '<div class="foms-tmf__loading">주문 원장 불러오는 중…</div>';
    }
    setStatus("", "");
    hideAutosaveBadge();
    // 새 주문의 단계가 확정될 때까지 완료 버튼 숨김(이전 주문 게이트 상태 잔류 방지).
    setCompleteVisible(false);

    return fetch(structuredUrl(orderId), { credentials: "same-origin" })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.success) {
          if (inj) inj.innerHTML = '<div class="foms-tmf__loading">주문 원장을 불러오지 못했습니다.</div>';
          return;
        }
        var sd = deepClone(data.structured_data);
        var payment = sd.payment && typeof sd.payment === "object" ? sd.payment : {};
        var freeParts = splitFreeInputForForm(resolveFreeInputText(sd));
        var ordererName = (sd.parties && sd.parties.orderer && sd.parties.orderer.name) || "";
        ordererName = String(ordererName).trim();
        var topBase = {
          received_date: data.received_date || "",
          received_time: data.received_time || "",
          is_self_measurement: !!data.is_self_measurement,
          is_regional: !!data.is_regional,
          construction_type: data.construction_type || "",
        };
        state = {
          orderId: orderId,
          ctx: ctx || {},
          structured: sd,
          notes: data.notes || "",
          schemaVersion: data.structured_schema_version || 1,
          confidence: data.structured_confidence != null ? data.structured_confidence : null,
          baselineUpdatedAt: data.structured_updated_at || null,
          topBaseline: topBase,
          top: {
            received_date: topBase.received_date,
            received_time: topBase.received_time,
            is_self_measurement: topBase.is_self_measurement,
            is_regional: topBase.is_regional,
            construction_type: topBase.construction_type,
          },
          amounts: {
            deposit: resolveDepositAmount(sd),
            discount: resolveDiscountAmount(sd),
            freeText: freeParts.text,
            freeAmount: freeParts.amount,
            cashReceipt: resolveCashReceipt(sd),
            balanceNote: resolveBalanceNote(sd),
          },
          paymentBase: {
            deposit_confirmed: !!payment.deposit_confirmed,
            deposit_confirmed_at: payment.deposit_confirmed_at || null,
            deposit_confirmed_by: payment.deposit_confirmed_by || null,
            deposit_confirmed_by_user_id: payment.deposit_confirmed_by_user_id || null,
            balance_confirmed: !!payment.balance_confirmed,
            balance_confirmed_at: payment.balance_confirmed_at || null,
            balance_confirmed_by: payment.balance_confirmed_by || null,
            balance_confirmed_by_user_id: payment.balance_confirmed_by_user_id || null,
          },
          ordererDirect: !(ordererName === "" || ordererName === "라홈" || ordererName === "하우드"),
          activeItem: 0,
          activeTab: "order",
          convText: "", // 변환 텍스트 미리보기 — [변환 텍스트 생성] 클릭 전까지 빈 값.
          photos: [],
          saving: false,
          pendingSave: false,
          dirty: false,
          saveTimer: null,
        };
        renderTopbarId();
        renderActiveTab();
        publishAlimtalkTrace(sd.alimtalk_measurement || null);
      })
      .catch(function () {
        if (inj) inj.innerHTML = '<div class="foms-tmf__loading">주문 원장을 불러오지 못했습니다.</div>';
      });
  }

  function requestSave() {
    if (!state) return;
    saveNow({ explicit: true });
  }

  function requestDraft() {
    if (!state) return;
    // 기존 주문(비-draft) 편집이라 신규주문 draft_token 플로우는 부적합. "임시 저장"은 진행분을
    // 즉시(비-충돌게이트, last-write-wins) 저장한다 — 자동저장과 같은 경로, 사용자 트리거 라벨만 다름.
    saveNow({ explicit: false, draft: true });
  }

  // 저장(명시) → 성공 시에만 퀘스트 승인. 진행 중에는 버튼을 비활성화해 중복 클릭을 막는다.
  function requestComplete() {
    if (!state || completeBusy) return;
    if (!isEditable()) {
      setStatus("이 주문은 실측 폼으로 완료할 수 없습니다.", "error");
      return;
    }
    // 버튼은 비-MEASURE 에서 숨겨지지만, 위임 클릭·API 직접 호출 대비 방어 가드.
    if (!isMeasureStage()) {
      setStatus("실측 단계 주문만 도면으로 전달할 수 있습니다.", "error");
      return;
    }
    if (!window.confirm("실측을 완료하고 도면 단계로 전달하시겠습니까?")) return;
    var orderId = state.orderId;
    setCompleteBusy(true);
    saveNow({ explicit: true })
      .then(function (ok) {
        return ok ? approveMeasureQuest(orderId) : null;
      })
      .then(function () {
        setCompleteBusy(false);
      });
  }

  function requestChannelPush() {
    requestPush("measurement");
  }

  function switchTab(tab) {
    if (!state) return;
    if (tab !== "order" && tab !== "calc" && tab !== "estimate") return;
    if (state.activeTab === tab) return;
    state.activeTab = tab;
    renderActiveTab();
  }

  window.FomsTabletMeasureForm = {
    load: load,
    requestSave: requestSave,
    requestDraft: requestDraft,
    requestComplete: requestComplete,
    requestChannelPush: requestChannelPush,
    switchTab: switchTab,
  };

  // ── 위임 이벤트(싱글턴 가드 하 1회 바인딩) ─────────────────────────
  function withinForm(target) {
    return target && target.closest && target.closest("[data-foms-tmf]");
  }

  // input: 텍스트/텍스트영역/숫자 필드(select·checkbox·file 제외 — change 에서 처리).
  document.addEventListener("input", function (ev) {
    if (!state) return;
    var t = ev.target;
    if (!withinForm(t)) return;
    if (t.tagName === "SELECT") return;
    if (t.type === "checkbox" || t.type === "radio" || t.type === "file") return;

    var field = t.getAttribute("data-tmf-field");
    if (field) {
      applyFieldEdit(field, t);
      return;
    }
    var itemField = t.getAttribute("data-tmf-itemfield");
    if (itemField) {
      applyItemFieldEdit(itemField, t);
      return;
    }
    var amount = t.getAttribute("data-tmf-amount");
    if (amount) {
      applyAmountEdit(amount, t);
      return;
    }
    var spec = t.getAttribute("data-tmf-spec");
    if (spec) {
      applySpecEdit(t, spec);
      refreshJasuOnly();
      scheduleAutosave();
    }
  });

  // change: select / checkbox / file. + 숫자 필드 blur 시 콤마 재포맷.
  document.addEventListener("change", function (ev) {
    if (!state) return;
    var t = ev.target;
    if (!withinForm(t)) return;

    if (t.type === "file" && t.getAttribute("data-tmf-upload")) {
      uploadFiles(t);
      return;
    }
    if (t.tagName === "SELECT" || t.type === "checkbox") {
      var field = t.getAttribute("data-tmf-field");
      if (field) applyFieldEdit(field, t);
      return;
    }
    var amount = t.getAttribute("data-tmf-amount");
    if (amount && (amount === "deposit" || amount === "discount" || amount === "free_amount")) {
      var stored =
        amount === "deposit"
          ? state.amounts.deposit
          : amount === "discount"
          ? state.amounts.discount
          : state.amounts.freeAmount;
      t.value = stored > 0 ? formatWon(stored) : "";
    }
    var itemAmount = t.getAttribute("data-tmf-itemfield");
    if (itemAmount === "price") {
      var item = itemsList()[state.activeItem];
      var n = item ? coerceAmount(item.price) : 0;
      t.value = n > 0 ? formatWon(n) : "";
    }
  });

  function applyOrdererEdit() {
    var form = formEl();
    if (!form) return;
    var direct = form.querySelector('[data-tmf-field="orderer_direct"]');
    var sel = form.querySelector('[data-tmf-field="orderer_select"]');
    var inp = form.querySelector('[data-tmf-field="orderer"]');
    var selWrap = form.querySelector('[data-tmf-orderer-wrap="select"]');
    var dirWrap = form.querySelector('[data-tmf-orderer-wrap="direct"]');
    var isDirect = !!(direct && direct.checked);
    state.ordererDirect = isDirect;
    if (selWrap) selWrap.hidden = isDirect;
    if (dirWrap) dirWrap.hidden = !isDirect;
    var val = isDirect ? (inp ? inp.value.trim() : "") : sel ? sel.value : "";
    ensureParty("orderer").name = val;
  }

  function applyFieldEdit(field, input) {
    var v = input.value;
    switch (field) {
      case "customer_name":
        ensureParty("customer").name = v;
        var nameEl = chromeQuery("[data-foms-tablet-measure-context-name]");
        if (nameEl) nameEl.textContent = v || "-";
        break;
      case "customer_phone":
        ensureParty("customer").phone = v;
        break;
      case "site_address":
        var site = ensureSite();
        site.address_full = v;
        site.address_main = v; // PC 미러(address_main=address_full, detail 공란).
        if (site.address_detail == null) site.address_detail = "";
        break;
      case "orderer":
      case "orderer_select":
      case "orderer_direct":
        applyOrdererEdit();
        break;
      case "manager":
        ensureParty("manager").name = v;
        break;
      case "construction_workers":
        ensureShipment().construction_workers = normalizeConstructionWorkers(v);
        break;
      case "workflow_stage":
        ensureWorkflow().stage = v;
        break;
      case "product_name":
        var it = itemsList()[state.activeItem];
        if (it) it.product_name = v;
        var chip = formEl() && formEl().querySelector('[data-tmf-item="' + state.activeItem + '"]');
        if (chip) chip.textContent = state.activeItem + 1 + ". " + (v || "제품 " + (state.activeItem + 1));
        break;
      case "notes":
        state.notes = v;
        refreshNotesBadge();
        break;
      case "phone_note":
        ensureNotesObj().phone_note = v;
        refreshBadges();
        refreshNotesBadge();
        break;
      case "address_note":
        ensureNotesObj().address_note = v;
        refreshBadges();
        refreshNotesBadge();
        break;
      case "measurement_note":
        ensureNotesObj().measurement_note = v;
        refreshBadges();
        refreshNotesBadge();
        break;
      case "measurement_date":
        ensureMeasurementSchedule().date = v;
        break;
      case "measurement_time_select":
        applyTimeSelect("measurement", input);
        break;
      case "measurement_time":
        ensureMeasurementSchedule().time = v;
        break;
      case "construction_date":
        var cs = ensureConstructionSchedule();
        cs.date = v;
        if (cs.raw == null) cs.raw = "";
        break;
      case "construction_time_select":
        applyTimeSelect("construction", input);
        break;
      case "construction_time":
        var cs2 = ensureConstructionSchedule();
        cs2.time = v;
        if (cs2.raw == null) cs2.raw = "";
        break;
      case "received_date":
        state.top.received_date = v;
        break;
      case "received_time":
        state.top.received_time = v;
        break;
      case "self_measurement":
        state.top.is_self_measurement = !!input.checked;
        break;
      case "regional":
        applyRegionalToggle(!!input.checked);
        break;
      case "construction_type":
        state.top.construction_type = v;
        break;
      case "urgent":
        applyUrgentToggle(!!input.checked);
        break;
      case "urgent_reason":
        ensureFlags().urgent_reason = v;
        break;
      case "factory2":
        ensureFlags().factory2 = !!input.checked;
        break;
      case "__free_text__":
        state.amounts.freeText = v;
        recomputeTotals();
        break;
      case "__cash_receipt__":
        state.amounts.cashReceipt = v;
        recomputeTotals();
        break;
      case "__balance_note__":
        state.amounts.balanceNote = v;
        recomputeTotals();
        break;
      default:
        return;
    }
    scheduleAutosave();
  }

  function applyTimeSelect(group, select) {
    var sch = group === "measurement" ? ensureMeasurementSchedule() : ensureConstructionSchedule();
    var form = formEl();
    var directWrap = form ? form.querySelector('[data-tmf-time-direct="' + group + '"]') : null;
    var directInput = form ? form.querySelector('[data-tmf-field="' + group + '_time"]') : null;
    if (select.value === "__direct__") {
      if (directWrap) directWrap.hidden = false;
      sch.time = directInput ? directInput.value : "";
    } else {
      if (directWrap) directWrap.hidden = true;
      sch.time = select.value;
    }
    if (group === "construction" && sch.raw == null) sch.raw = "";
  }

  function applyRegionalToggle(checked) {
    state.top.is_regional = checked;
    var form = formEl();
    var field = form ? form.querySelector("[data-tmf-ctype-field]") : null;
    var sel = form ? form.querySelector('[data-tmf-field="construction_type"]') : null;
    if (field) field.hidden = !checked;
    if (sel) sel.disabled = !checked;
    if (!checked) {
      if (sel) sel.value = "";
      state.top.construction_type = "";
    }
  }

  function applyUrgentToggle(checked) {
    ensureFlags().urgent = checked;
    var form = formEl();
    var field = form ? form.querySelector("[data-tmf-urgent-field]") : null;
    if (field) field.hidden = !checked;
    if (!checked) {
      var input = form ? form.querySelector('[data-tmf-field="urgent_reason"]') : null;
      if (input) input.value = "";
      ensureFlags().urgent_reason = "";
    }
  }

  function applyItemFieldEdit(field, input) {
    var item = itemsList()[state.activeItem];
    if (!item || typeof item !== "object") return;
    if (field === "price") {
      item.price = input.value;
      updateDerivedAmounts();
    } else {
      item[field] = input.value;
    }
    scheduleAutosave();
  }

  // 숫자 금액 필드(예약금/할인/자유입력 금액). 자유입력 항목명·현금영수증·잔금 메모는 텍스트라
  // data-tmf-field(__free_text__ 등)로 applyFieldEdit 가 처리한다.
  function applyAmountEdit(key, input) {
    var digits = String(input.value || "").replace(/[^0-9]/g, "");
    var n = digits ? parseInt(digits, 10) : 0;
    if (key === "deposit") state.amounts.deposit = n;
    else if (key === "discount") state.amounts.discount = n;
    else if (key === "free_amount") state.amounts.freeAmount = n;
    else return;
    updateDerivedAmounts();
    scheduleAutosave();
  }

  function applySpecEdit(input, dim) {
    var itemIdx = parseInt(input.getAttribute("data-item-index") || "-1", 10);
    var rowIdx = parseInt(input.getAttribute("data-row-index") || "-1", 10);
    var list = itemsList();
    var item = list[itemIdx];
    if (!item || typeof item !== "object") return;
    if (!Array.isArray(item.spec_rows)) item.spec_rows = [];
    while (item.spec_rows.length <= rowIdx) item.spec_rows.push({});
    var row = item.spec_rows[rowIdx];
    if (!row || typeof row !== "object") {
      row = {};
      item.spec_rows[rowIdx] = row;
    }
    var key = dim === "width" ? "spec_width" : dim === "depth" ? "spec_depth" : "spec_height";
    row[key] = input.value;
    // erpCollectStructured 파생 미러링: 첫 행을 spec_width/depth/height 로, spec 원문(WxDxH, 행은 ', ') 재생성.
    var first = item.spec_rows[0] || {};
    item.spec_width = first.spec_width || "";
    item.spec_depth = first.spec_depth || "";
    item.spec_height = first.spec_height || "";
    var lines = item.spec_rows
      .map(function (r) {
        return [r.spec_width, r.spec_depth, r.spec_height]
          .filter(function (val) {
            return val != null && String(val).trim() !== "";
          })
          .join("x");
      })
      .filter(Boolean);
    item.spec = lines.join(", ");
  }

  document.addEventListener("click", function (ev) {
    if (!state) return;
    var t = ev.target;
    if (!t || !t.closest) return;
    if (!withinForm(t)) return;

    var addItem = t.closest("[data-tmf-add-item]");
    if (addItem) {
      ev.preventDefault();
      if (!Array.isArray(state.structured.items)) state.structured.items = [];
      // PC collect 호환 최소 shape + 상담 기본값(정규화 저장과 정합).
      state.structured.items.push({
        product_name: "",
        spec_rows: [{}],
        color: "상담",
        option_detail: "상담",
        handle: "상담",
        internal: "상담",
        misc: "상담",
      });
      state.activeItem = state.structured.items.length - 1;
      refreshItemBody();
      scheduleAutosave();
      return;
    }

    var delItem = t.closest("[data-tmf-del-item]");
    if (delItem) {
      ev.preventDefault();
      var list = itemsList();
      if (list.length <= 1) {
        setStatus("최소 1개 항목이 필요합니다.", "error");
        return;
      }
      var didx = parseInt(delItem.getAttribute("data-tmf-del-item") || "-1", 10);
      if (didx >= 0 && didx < list.length) {
        list.splice(didx, 1);
        if (state.activeItem >= list.length) state.activeItem = list.length - 1;
        refreshItemBody();
        updateDerivedAmounts();
        scheduleAutosave();
      }
      return;
    }

    var addSpec = t.closest("[data-tmf-add-spec-row]");
    if (addSpec) {
      ev.preventDefault();
      var itemA = itemsList()[state.activeItem];
      if (itemA) {
        if (!Array.isArray(itemA.spec_rows)) itemA.spec_rows = [];
        itemA.spec_rows.push({});
        refreshSpecPanel();
        scheduleAutosave();
      }
      return;
    }

    var delSpec = t.closest("[data-tmf-del-spec-row]");
    if (delSpec) {
      ev.preventDefault();
      var itemD = itemsList()[state.activeItem];
      if (itemD && Array.isArray(itemD.spec_rows)) {
        var sidx = parseInt(delSpec.getAttribute("data-tmf-del-spec-row") || "-1", 10);
        if (sidx >= 0 && sidx < itemD.spec_rows.length) {
          itemD.spec_rows.splice(sidx, 1);
          if (!itemD.spec_rows.length) itemD.spec_rows.push({});
          // 파생 재계산(첫 행 기준).
          var f = itemD.spec_rows[0] || {};
          itemD.spec_width = f.spec_width || "";
          itemD.spec_depth = f.spec_depth || "";
          itemD.spec_height = f.spec_height || "";
          var ln = itemD.spec_rows
            .map(function (r) {
              return [r.spec_width, r.spec_depth, r.spec_height]
                .filter(function (val) {
                  return val != null && String(val).trim() !== "";
                })
                .join("x");
            })
            .filter(Boolean);
          itemD.spec = ln.join(", ");
          refreshSpecPanel();
          scheduleAutosave();
        }
      }
      return;
    }

    var chip = t.closest("[data-tmf-item]");
    if (chip) {
      ev.preventDefault();
      var idx = parseInt(chip.getAttribute("data-tmf-item") || "0", 10);
      if (idx !== state.activeItem) {
        state.activeItem = idx;
        refreshItemBody();
      }
      return;
    }

    var photo = t.closest("[data-tmf-photo]");
    if (photo) {
      ev.preventDefault();
      openPhoto(parseInt(photo.getAttribute("data-tmf-photo") || "0", 10));
      return;
    }

    var genText = t.closest("[data-tmf-gen-text]");
    if (genText) {
      ev.preventDefault();
      refreshConversionText();
      setStatus("변환 텍스트 생성됨", "saved");
      return;
    }
    var copyText = t.closest("[data-tmf-copy-text]");
    if (copyText) {
      ev.preventDefault();
      copyConversionText();
      return;
    }
    var pushMeas = t.closest("[data-tmf-push-measurement]");
    if (pushMeas) {
      ev.preventDefault();
      requestPush("measurement");
      return;
    }
    var pushDraw = t.closest("[data-tmf-push-drawing]");
    if (pushDraw) {
      ev.preventDefault();
      requestPush("drawing");
      return;
    }
    var alimtalk = t.closest("[data-tmf-alimtalk-send]");
    if (alimtalk) {
      ev.preventDefault();
      requestAlimtalk();
      return;
    }
    var shareOpen = t.closest("[data-tmf-share-open]");
    if (shareOpen) {
      ev.preventDefault();
      requestShare();
      return;
    }

    var refresh = t.closest("[data-tmf-refresh]");
    if (refresh) {
      ev.preventDefault();
      load(state.orderId, state.ctx);
      return;
    }
  });

  // 백그라운드 전환/이탈 시 미저장분 flush.
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "hidden") flushPending();
  });
  window.addEventListener("pagehide", flushPending);
})();
