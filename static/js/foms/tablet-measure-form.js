/**
 * FOMS 태블릿 전용 ERP Order 폼 (W-MEASURE-FORM 확장판) — 태블릿 가로(코호트) 실측 split
 * view 우측 패널. 목업 frame13 "융합·키보드"의 ERP Order 편집 = PC 기능 전량을 태블릿
 * 네이티브로 구현한다. 기존 PC ERP Order edit fragment 주입을 대체하되, 데이터는 100%
 * 기존 구조화 API 로 읽고 쓴다(신규 백엔드 없음):
 *   - 읽기: GET  /api/orders/<id>/structured           (전사 공용 구조화 조회)
 *   - 쓰기: PUT  /api/orders/<id>/structured           (전사 공용 구조화 저장 = PC "저장"과 동일 경로)
 *   - 사진: GET  /api/orders/<id>/attachments?category=measurement (읽기전용 표시만)
 *   - 견적: GET  /api/orders/<id>/estimate-preview      (견적서 탭 렌더 데이터)
 *   - 계산기: iframe /wdcalculator?embedded=1&order_id=&customer_name=  (PC split 과 동일 임베드)
 *   - 채널톡: POST /api/channel/push-manual             (변환 텍스트 → 채널톡 수동 푸쉬)
 *
 * 구성(목업 frame13):
 *   1. 상단 바   : 고객명 + 단계 배지 + #주문번호 + "✓ 자동저장됨 · 방금" 라이브 배지
 *                  + [계산기 같이 보기 토글] + [Ctrl+S 저장]
 *   2. 외부 탭   : 주문(ERP) | 계산기 | 견적서
 *   3. 구조화 폼 : 고객·현장 / 제품 항목 N(규격·자수·제품명·항목추가) / 금액(출고가·예약금·잔금)
 *                  + 현장 메모 + 실측 사진(읽기전용)
 *   4. 하단 액션 : [변환 텍스트 → 채널톡] · [실측 완료 → 도면] [임시 저장] [저장]
 *   5. 계산기 split: 주문 탭에서 토글 시 폼(60%) + 계산기 임베드(40%) 나란히
 *   6. 계산기/견적서 탭: 우측 콘텐츠 전환(계산기=전폭 임베드, 견적서=견적 프리뷰 네이티브 렌더)
 *
 * 데이터 무결성(핵심):
 *   - read-merge-write: GET 전체 payload 를 메모리에 보관하고 편집 키만 변형한 뒤 "전체 shape
 *     그대로" PUT 한다 → 폼이 렌더하지 않는 키(도면/견적/채널톡/quests 등)를 절대 덮어쓰지
 *     않는다(서버 _preserve_operational_structured_state 와 이중 방어).
 *   - 규격 W/H/D 는 items[].spec_rows(=출고 W·자수 SSOT)에 직접 기록. 파생값(자수=W/300)은
 *     표시만 클라이언트 계산, 저장하지 않는다(서버 eval_spec_width_mm SSOT).
 *   - 금액(출고가·예약금·잔금)은 저장된 totals/payment 에서 파생 "표시 전용"이다. 가격 산정은
 *     계산기/PC(erpBuildTotals SSOT)가 소유 — 태블릿 실측 폼은 totals 를 재계산해 쓰지 않는다
 *     (잔금 파생·재파싱 금지, 이중계산·clobber 차단).
 *   - PC 폼이 함께 보내는 raw_order_text/received_date/received_time/is_regional/construction_type/
 *     is_self_measurement 는 이 폼이 편집하지 않으므로 PUT payload 에서 생략한다(키 부재=서버 보존).
 *
 * 동시성:
 *   - 명시 저장/실측완료 직전 GET 으로 structured_updated_at 을 baseline 과 비교 → 다른 곳에서
 *     수정됐으면 배너를 띄우고 PUT 을 중단한다(silent overwrite 금지).
 *   - 자동저장/임시저장은 last-write-wins(전체 merge payload 라 무관 필드 clobber 없음).
 *
 * 재실행 안전(perf G4): window.__FOMS_TABLET_MEASURE_FORM_BOUND 싱글턴 가드 + 위임 이벤트.
 * 이 모듈은 스스로 활성화하지 않는다 — 코호트 게이트를 통과한 tablet-measurement.js 가
 * load()/requestSave()/requestComplete()/requestDraft()/requestChannelPush()/switchTab()/
 * toggleCalc() 로 구동한다(중복 게이트 정의 금지).
 */
(function () {
  "use strict";

  if (window.__FOMS_TABLET_MEASURE_FORM_BOUND) return;
  window.__FOMS_TABLET_MEASURE_FORM_BOUND = true;

  var AUTOSAVE_DEBOUNCE_MS = 1500;
  var DETAIL_SELECTOR = ".foms-tablet-measure-detail";
  var INJECT_SELECTOR = "[data-foms-tablet-measure-detail]";
  var STATUS_SELECTOR = "[data-foms-tablet-measure-status]";
  // 실측 완료 → 도면 단계(목업 "실측 완료 → 도면 전달"; PC 단계 select 의 "D. 도면" = DRAWING).
  // 서버 _handle_stage_transition 이 workflow.stage 변경을 감지해 order.status/OrderEvent/Quest 를 처리한다.
  var NEXT_STAGE_ON_COMPLETE = "DRAWING";

  // 활성 주문 1건의 편집 상태. 카드 전환 시 통째로 교체된다.
  var state = null;

  function structuredUrl(id) {
    return "/api/orders/" + encodeURIComponent(id) + "/structured";
  }
  function attachmentsUrl(id) {
    return "/api/orders/" + encodeURIComponent(id) + "/attachments?category=measurement";
  }
  function estimatePreviewUrl(id) {
    return "/api/orders/" + encodeURIComponent(id) + "/estimate-preview";
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
    if (typeof v === "object") v = v.amount;
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

  // 탭 버튼/계산기 토글 활성 상태 동기화(크롬은 __scroll 밖 형제라 재렌더에도 생존).
  function syncTabButtons() {
    if (!state) return;
    var tabs = detailEl() ? detailEl().querySelectorAll("[data-foms-tmf-tab]") : [];
    Array.prototype.forEach.call(tabs, function (b) {
      var on = b.getAttribute("data-foms-tmf-tab") === state.activeTab;
      b.classList.toggle("is-active", on);
      b.setAttribute("aria-selected", on ? "true" : "false");
    });
    var toggle = chromeQuery("[data-foms-tmf-calc-toggle]");
    if (toggle) {
      toggle.hidden = state.activeTab !== "order";
      toggle.setAttribute("aria-pressed", state.calcOpen ? "true" : "false");
      toggle.classList.toggle("is-active", !!state.calcOpen);
    }
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
    return s.address_full || s.address_main || "";
  }
  function scheduleValue(group, key) {
    var g = state.structured.schedule && state.structured.schedule[group];
    return g && typeof g === "object" ? g[key] || "" : "";
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

  function computeAmounts() {
    // 표시 전용 파생. 저장된 totals/payment 를 읽고, 없으면 SPEC 공식으로 파생.
    // 출고가 = 품목합 + 자유입력(배송) − 할인. 잔금 = 출고가 − 예약금.
    var t = (state.structured && state.structured.totals) || {};
    var p = (state.structured && state.structured.payment) || {};
    var itemsTotal = coerceAmount(t.items_total);
    var freeInput = coerceAmount(t.free_input_amount);
    var discount = coerceAmount(t.discount_amount != null ? t.discount_amount : p.discount);
    var shipping =
      t.shipping_price != null
        ? coerceAmount(t.shipping_price)
        : Math.max(0, itemsTotal + freeInput - discount);
    var deposit = coerceAmount(p.deposit != null ? p.deposit : t.deposit_amount);
    var balance = Math.max(0, shipping - deposit);
    return { shipping: shipping, deposit: deposit, balance: balance };
  }

  // ── 렌더: 필드 부품 ────────────────────────────────────────────────
  function textField(label, fieldKey, value, opts) {
    opts = opts || {};
    var full = opts.full ? " foms-tmf__ffield--full" : "";
    var mode = opts.inputmode ? ' inputmode="' + opts.inputmode + '"' : "";
    var ph = opts.placeholder ? ' placeholder="' + escapeHtml(opts.placeholder) + '"' : "";
    return (
      '<div class="foms-tmf__ffield' +
      full +
      '"><label class="foms-tmf__flabel">' +
      escapeHtml(label) +
      "</label>" +
      '<input class="foms-tmf__finput" type="text" autocomplete="off"' +
      mode +
      ' data-tmf-field="' +
      fieldKey +
      '" value="' +
      escapeHtml(value) +
      '"' +
      ph +
      "></div>"
    );
  }

  function renderCustomerSiteCard() {
    return (
      '<section class="foms-tmf__section">' +
      '<h5 class="foms-tmf__title">고객 · 현장</h5>' +
      '<div class="foms-tmf__formgrid">' +
      textField("고객명", "customer_name", partyValue("customer", "name")) +
      textField("연락처", "customer_phone", partyValue("customer", "phone"), { inputmode: "tel" }) +
      textField("현장 주소", "site_address", siteAddress(), { full: true }) +
      textField("발주사", "orderer", partyValue("orderer", "name")) +
      textField("담당자", "manager", partyValue("manager", "name")) +
      textField("실측 예정(일)", "measurement_date", scheduleValue("measurement", "date"), {
        placeholder: "예: 2026-07-11 (여러 날짜는 쉼표로)",
      }) +
      textField("실측 예정(시간)", "measurement_time", scheduleValue("measurement", "time"), {
        placeholder: "예: 오전 / 오후 / 09:30",
      }) +
      textField("시공 예정", "construction_date", scheduleValue("construction", "date"), {
        placeholder: "예: 2026-07-24",
      }) +
      "</div></section>"
    );
  }

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
    var rowLabel = rowCount > 1 ? '<div class="foms-tmf__spec-rowlabel">규격 ' + (rowIdx + 1) + "</div>" : "";
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
      rowLabel +
      '<div class="foms-tmf__numgrid">' +
      box("width", "W (가로)", w) +
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
    var jasu = itemJasuDisplay(item);
    var jasuHtml =
      '<div class="foms-tmf__jasu"' +
      (jasu ? "" : " hidden") +
      '>자수 (W/300) <strong>' +
      escapeHtml(jasu) +
      "</strong></div>";
    return rowsHtml + jasuHtml;
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
    var nameField =
      '<div class="foms-tmf__ffield foms-tmf__ffield--full">' +
      '<label class="foms-tmf__flabel">제품명</label>' +
      '<input class="foms-tmf__finput" type="text" autocomplete="off" data-tmf-field="product_name" value="' +
      escapeHtml((item && item.product_name) || "") +
      '" placeholder="예: 붙박이장 W2400"></div>';
    return (
      renderItemChips() +
      nameField +
      '<div class="foms-tmf__spec" data-tmf-spec-panel>' +
      renderItemSpec() +
      "</div>"
    );
  }

  function renderItemsCard() {
    return (
      '<section class="foms-tmf__section">' +
      '<h5 class="foms-tmf__title">제품 항목 ' +
      itemsList().length +
      "</h5>" +
      '<div data-tmf-item-body>' +
      renderItemBody() +
      "</div></section>"
    );
  }

  function renderAmountsCard() {
    var a = computeAmounts();
    return (
      '<section class="foms-tmf__section">' +
      '<h5 class="foms-tmf__title">금액</h5>' +
      '<div class="foms-tmf__kvgrid">' +
      '<div class="foms-tmf__kv"><b>출고가 (품목+배송−할인)</b><span>' +
      formatWon(a.shipping) +
      "</span></div>" +
      '<div class="foms-tmf__kv"><b>예약금</b><span>' +
      formatWon(a.deposit) +
      "</span></div>" +
      '<div class="foms-tmf__kv foms-tmf__kv--accent"><b>잔금 = 출고가 − 예약금</b><span>' +
      formatWon(a.balance) +
      "</span></div>" +
      "</div>" +
      '<p class="foms-tmf__amount-note">금액은 계산기·PC 견적에서 산정됩니다. 여기선 최신 저장값을 표시합니다.</p>' +
      "</section>"
    );
  }

  function renderNotesCard() {
    return (
      '<section class="foms-tmf__section">' +
      '<h5 class="foms-tmf__title">현장 메모</h5>' +
      '<textarea class="foms-tmf__textarea" data-tmf-field="notes" rows="3" ' +
      'placeholder="현장 특이사항 · 시공 참고 메모">' +
      escapeHtml(state.notes || "") +
      "</textarea></section>"
    );
  }

  function renderPhotosCard() {
    var editHref = state.ctx && state.ctx.editUrl ? escapeHtml(state.ctx.editUrl) : "";
    return (
      '<section class="foms-tmf__section">' +
      '<h5 class="foms-tmf__title">실측 사진</h5>' +
      '<div class="foms-tmf__photos" data-tmf-photos><div class="foms-tmf__photo-loading">사진 불러오는 중…</div></div>' +
      (editHref
        ? '<a class="foms-tmf__photo-add foms-btn foms-btn--secondary foms-btn--sm" href="' +
          editHref +
          '"><i class="fas fa-camera" aria-hidden="true"></i><span>ERP 편집에서 첨부</span></a>'
        : "") +
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
      renderCustomerSiteCard() +
      renderItemsCard() +
      renderAmountsCard() +
      renderNotesCard() +
      renderPhotosCard() +
      "</div>";
    var calcAside = state.calcOpen
      ? '<aside class="foms-tmf__calcpane" data-tmf-calcpane>' +
        '<div class="foms-tmf__calcpane-head"><span>계산기 같이 보기</span><span class="foms-tmf__calcpane-tag">WDC</span></div>' +
        '<iframe class="foms-tmf__calcframe" src="' +
        escapeHtml(calcIframeSrc(state.orderId, partyValue("customer", "name") || (state.ctx && state.ctx.customerName))) +
        '" title="WD 계산기" loading="lazy"></iframe>' +
        "</aside>"
      : "";
    inj.innerHTML =
      '<div class="foms-tmf" data-foms-tmf data-order-id="' +
      escapeHtml(state.orderId) +
      '">' +
      '<div class="foms-tmf__banner" data-tmf-banner hidden role="alert">' +
      "<span>다른 곳에서 이 주문이 수정되었습니다. 최신 내용을 불러오세요.</span>" +
      '<button type="button" class="foms-btn foms-btn--sm foms-btn--secondary" data-tmf-refresh>새로고침</button>' +
      "</div>" +
      '<div class="foms-tmf__ordergrid' +
      (state.calcOpen ? " is-split" : "") +
      '">' +
      formCol +
      calcAside +
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

  function estimateFallback() {
    var editHref = state.ctx && state.ctx.editUrl ? escapeHtml(state.ctx.editUrl) : "";
    return (
      '<div class="foms-tmf" data-foms-tmf><div class="foms-tmf__notice">' +
      "<p>견적서 데이터를 불러오지 못했습니다.</p>" +
      (editHref
        ? '<a class="foms-btn foms-btn--secondary" href="' + editHref + '">PC 견적서에서 열기</a>'
        : "") +
      "</div></div>"
    );
  }

  function renderEstimateView(data) {
    var editHref = state.ctx && state.ctx.editUrl ? escapeHtml(state.ctx.editUrl) : "";
    var items = Array.isArray(data.items) ? data.items : [];
    var rowsHtml = items.length
      ? items
          .map(function (it) {
            var name = escapeHtml(it.product_name || "-");
            var spec = escapeHtml(it.spec || "");
            var qty = it.quantity != null ? it.quantity : 1;
            var amount = formatWon(coerceAmount(it.amount));
            return (
              '<tr><td class="foms-tmf__est-name">' +
              name +
              (spec ? '<span class="foms-tmf__est-spec">' + spec + "</span>" : "") +
              "</td><td class=\"foms-tmf__est-qty\">" +
              escapeHtml(qty) +
              '</td><td class="foms-tmf__est-amt">' +
              amount +
              "</td></tr>"
            );
          })
          .join("")
      : '<tr><td colspan="3" class="foms-tmf__empty-note">견적 항목이 없습니다.</td></tr>';
    var shipping = coerceAmount(data.shipping_price != null ? data.shipping_price : data.total_amount);
    var deposit = coerceAmount(data.deposit_amount);
    var balance = coerceAmount(data.balance_amount != null ? data.balance_amount : data.final_amount);
    return (
      '<div class="foms-tmf" data-foms-tmf>' +
      '<section class="foms-tmf__section">' +
      '<div class="foms-tmf__est-hero"><b>총 견적</b><span>' +
      formatWon(shipping) +
      "</span></div>" +
      '<table class="foms-tmf__est-table"><thead><tr><th>품목</th><th>수량</th><th class="foms-tmf__est-amt">금액</th></tr></thead>' +
      "<tbody>" +
      rowsHtml +
      "</tbody></table>" +
      "</section>" +
      '<section class="foms-tmf__section">' +
      '<h5 class="foms-tmf__title">금액 요약</h5>' +
      '<div class="foms-tmf__kvgrid">' +
      '<div class="foms-tmf__kv"><b>출고가</b><span>' +
      formatWon(shipping) +
      "</span></div>" +
      '<div class="foms-tmf__kv"><b>예약금</b><span>' +
      formatWon(deposit) +
      "</span></div>" +
      '<div class="foms-tmf__kv foms-tmf__kv--accent"><b>잔금</b><span>' +
      formatWon(balance) +
      "</span></div></div>" +
      (editHref
        ? '<a class="foms-tmf__photo-add foms-btn foms-btn--secondary foms-btn--sm" href="' +
          editHref +
          '"><i class="fas fa-file-invoice" aria-hidden="true"></i><span>PC 견적서(문서·인쇄) 열기</span></a>'
        : "") +
      "</section></div>"
    );
  }

  function renderEstimateTab(inj) {
    inj.innerHTML =
      '<div class="foms-tmf" data-foms-tmf><div class="foms-tmf__loading">견적서 불러오는 중…</div></div>';
    var orderId = state.orderId;
    fetch(estimatePreviewUrl(orderId), { credentials: "same-origin" })
      .then(function (res) {
        return res.json();
      })
      .then(function (res) {
        if (!state || state.orderId !== orderId || state.activeTab !== "estimate") return;
        var inj2 = injectEl();
        if (!inj2) return;
        if (!res || !res.success || !res.data) {
          inj2.innerHTML = estimateFallback();
          return;
        }
        inj2.innerHTML = renderEstimateView(res.data);
      })
      .catch(function () {
        if (!state || state.orderId !== orderId || state.activeTab !== "estimate") return;
        var inj3 = injectEl();
        if (inj3) inj3.innerHTML = estimateFallback();
      });
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
  }

  function refreshItemBody() {
    var host = formEl() ? formEl().querySelector("[data-tmf-item-body]") : null;
    if (host) host.innerHTML = renderItemBody();
    // 제품 항목 수 라벨 갱신(항목 추가 시).
    var sections = formEl() ? formEl().querySelectorAll(".foms-tmf__title") : [];
    Array.prototype.forEach.call(sections, function (h) {
      if (/^제품 항목/.test(h.textContent || "")) h.textContent = "제품 항목 " + itemsList().length;
    });
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

  // ── 사진(읽기전용) ──────────────────────────────────────────────────
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

  // ── 저장(PUT read-merge-write) ──────────────────────────────────────
  function buildPayload() {
    // 이 폼이 편집하는 키만 담고, 나머지(raw_order_text/received_*/is_regional/construction_type/
    // is_self_measurement)는 생략한다 → 서버가 키 부재를 보존으로 처리(clobber 방지).
    var payload = {
      structured_data: state.structured,
      structured_schema_version: state.schemaVersion || 1,
      notes: state.notes != null ? state.notes : "",
    };
    if (state.confidence != null) payload.structured_confidence = state.confidence;
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

  function saveNow(opts) {
    opts = opts || {};
    if (!state || !isEditable()) return;
    if (state.saving) {
      state.pendingSave = true;
      return;
    }
    window.clearTimeout(state.saveTimer);
    var orderId = state.orderId;
    var explicit = !!opts.explicit;
    var isComplete = !!opts.complete;
    var isDraft = !!opts.draft;

    // 실측 완료: workflow.stage=DRAWING 을 이 PUT 에만 실어 서버가 단계 전환하게 한다.
    var stageApplied = false;
    var prevStage;
    if (isComplete) {
      var wf = ensureObj(state.structured, "workflow");
      prevStage = wf.stage;
      wf.stage = NEXT_STAGE_ON_COMPLETE;
      stageApplied = true;
    }
    function revertStage() {
      if (stageApplied && state && state.structured && state.structured.workflow) {
        state.structured.workflow.stage = prevStage;
      }
    }

    state.saving = true;
    setStatus(isDraft ? "임시 저장 중…" : "저장 중…", "saving");

    var pre = explicit ? checkConflict(orderId) : Promise.resolve(false);
    pre
      .then(function (conflict) {
        if (conflict) {
          revertStage();
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
          state.dirty = false;
          setStatus(isComplete ? "도면 전달 완료" : isDraft ? "임시 저장됨" : "저장됨", "saved");
          showAutosaveBadge((isDraft || !explicit ? "자동저장됨" : "저장됨") + " · 방금");
          if (isComplete) onCompleteSaved();
          refreshBaseline(orderId);
        } else {
          revertStage();
          var msg = (result.data && result.data.message) || "저장 실패";
          setStatus(msg, "error");
        }
      })
      .catch(function () {
        revertStage();
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
      });
  }

  function onCompleteSaved() {
    var card = document.querySelector(".foms-tablet-measure-card.is-active");
    if (card) card.classList.add("is-completed");
  }

  function flushPending() {
    if (state && state.dirty && !state.saving && isEditable()) {
      saveNow({ explicit: false });
    }
  }

  // ── 채널톡 변환 텍스트 → 수동 푸쉬 ──────────────────────────────────
  function buildConversionText() {
    var sd = state.structured || {};
    var c = (sd.parties && sd.parties.customer) || {};
    var lines = [];
    lines.push("[고객] " + (c.name || "") + (c.phone ? " " + c.phone : ""));
    var addr = siteAddress();
    if (addr) lines.push("[현장] " + addr);
    var mDate = scheduleValue("measurement", "date");
    if (mDate) lines.push("[실측] " + mDate + (scheduleValue("measurement", "time") ? " " + scheduleValue("measurement", "time") : ""));
    var cDate = scheduleValue("construction", "date");
    if (cDate) lines.push("[시공] " + cDate);
    var items = itemsList();
    if (items.length) {
      lines.push("[제품]");
      items.forEach(function (it, i) {
        var name = (it && (it.product_name || it.name)) || "제품 " + (i + 1);
        var spec = it && it.spec ? it.spec : "";
        var jasu = itemJasuDisplay(it);
        lines.push(
          "  " + (i + 1) + ". " + name + (spec ? " (" + spec + ")" : "") + (jasu ? " 자수 " + jasu : "")
        );
      });
    }
    var a = computeAmounts();
    lines.push("[금액] 출고가 " + formatWon(a.shipping) + " / 예약금 " + formatWon(a.deposit) + " / 잔금 " + formatWon(a.balance));
    return lines.join("\n");
  }

  function pushManual(orderId, text, changeNote) {
    fetch("/api/channel/push-manual", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        order_id: orderId,
        text: text,
        push_kind: "measurement",
        change_note: changeNote || "",
      }),
    })
      .then(function (res) {
        return res.json().then(function (d) {
          return { ok: res.ok, status: res.status, data: d };
        });
      })
      .then(function (r) {
        if (!state || state.orderId !== orderId) return;
        if (r.data && r.data.success) {
          setStatus("채널톡 전송 완료", "saved");
          return;
        }
        var msg = (r.data && r.data.message) || "채널톡 전송 실패";
        // 재전송 시 변경 내용 필요(서버 400) → 프롬프트 후 재시도.
        if (r.status === 400 && /변경/.test(msg)) {
          var note = window.prompt(msg + "\n\n변경 내용을 입력하세요(재전송):", "");
          if (note && note.trim()) {
            pushManual(orderId, text, note.trim());
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

  // ── 공개 API(tablet-measurement.js 가 구동) ────────────────────────
  function load(orderId, ctx) {
    // 이전 주문의 미저장 편집을 새 주문 로드 전에 flush(카드 전환 시 유실 방지).
    flushPending();

    var inj = injectEl();
    if (inj) {
      inj.innerHTML = '<div class="foms-tmf__loading">주문 원장 불러오는 중…</div>';
    }
    setStatus("", "");
    hideAutosaveBadge();

    fetch(structuredUrl(orderId), { credentials: "same-origin" })
      .then(function (res) {
        return res.json();
      })
      .then(function (data) {
        if (!data || !data.success) {
          if (inj) inj.innerHTML = '<div class="foms-tmf__loading">주문 원장을 불러오지 못했습니다.</div>';
          return;
        }
        state = {
          orderId: orderId,
          ctx: ctx || {},
          structured: deepClone(data.structured_data),
          notes: data.notes || "",
          schemaVersion: data.structured_schema_version || 1,
          confidence: data.structured_confidence != null ? data.structured_confidence : null,
          baselineUpdatedAt: data.structured_updated_at || null,
          activeItem: 0,
          activeTab: "order",
          calcOpen: false,
          photos: [],
          saving: false,
          pendingSave: false,
          dirty: false,
          saveTimer: null,
        };
        renderTopbarId();
        renderActiveTab();
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

  function requestComplete() {
    if (!state) return;
    if (!isEditable()) {
      setStatus("이 주문은 실측 폼으로 완료할 수 없습니다.", "error");
      return;
    }
    if (!window.confirm("실측을 완료하고 도면 단계로 전달하시겠습니까?")) return;
    saveNow({ explicit: true, complete: true });
  }

  function requestChannelPush() {
    if (!state || !isEditable()) return;
    setStatus("채널톡 전송 중…", "saving");
    pushManual(state.orderId, buildConversionText(), "");
  }

  function switchTab(tab) {
    if (!state) return;
    if (tab !== "order" && tab !== "calc" && tab !== "estimate") return;
    if (state.activeTab === tab) return;
    state.activeTab = tab;
    renderActiveTab();
  }

  function toggleCalc() {
    if (!state) return;
    state.calcOpen = !state.calcOpen;
    if (state.activeTab !== "order") state.activeTab = "order";
    renderActiveTab();
  }

  window.FomsTabletMeasureForm = {
    load: load,
    requestSave: requestSave,
    requestDraft: requestDraft,
    requestComplete: requestComplete,
    requestChannelPush: requestChannelPush,
    switchTab: switchTab,
    toggleCalc: toggleCalc,
  };

  // ── 위임 이벤트(싱글턴 가드 하 1회 바인딩) ─────────────────────────
  function withinForm(target) {
    return target && target.closest && target.closest("[data-foms-tmf]");
  }

  document.addEventListener("input", function (ev) {
    if (!state) return;
    var t = ev.target;
    if (!withinForm(t)) return;

    var field = t.getAttribute("data-tmf-field");
    if (field) {
      applyFieldEdit(field, t);
      return;
    }

    var spec = t.getAttribute("data-tmf-spec");
    if (spec) {
      applySpecEdit(t, spec);
      refreshJasuOnly();
      scheduleAutosave();
    }
  });

  function applyFieldEdit(field, input) {
    var v = input.value;
    switch (field) {
      case "customer_name":
        ensureParty("customer").name = v;
        // 좌측 카드/컨텍스트 이름 라이브 반영(서버 재렌더 전 UX).
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
        ensureParty("orderer").name = v;
        break;
      case "manager":
        ensureParty("manager").name = v;
        break;
      case "measurement_date":
        ensureMeasurementSchedule().date = v;
        break;
      case "measurement_time":
        ensureMeasurementSchedule().time = v;
        break;
      case "construction_date":
        var cs = ensureConstructionSchedule();
        cs.date = v;
        if (cs.raw == null) cs.raw = "";
        break;
      case "product_name":
        var it = itemsList()[state.activeItem];
        if (it) it.product_name = v;
        var chip = formEl() && formEl().querySelector('[data-tmf-item="' + state.activeItem + '"]');
        if (chip) chip.textContent = state.activeItem + 1 + ". " + (v || "제품 " + (state.activeItem + 1));
        break;
      case "notes":
        state.notes = v;
        break;
      default:
        return;
    }
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
      // PC collect 호환 최소 shape: product_name + spec_rows[1] (price 등은 계산기/PC 산정).
      state.structured.items.push({ product_name: "", spec_rows: [{}] });
      state.activeItem = state.structured.items.length - 1;
      refreshItemBody();
      scheduleAutosave();
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
