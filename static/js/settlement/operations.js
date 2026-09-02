/**
 * 정산 대시보드 · 탭 2 "실무(경리·수금)" (SETTLE-TABS-01 / 스펙 개정 A §13).
 *
 * 원본 목업: docs/design/mockups/settlement-dashboard-v2-operations.html
 *
 * **데이터 소스는 `GET /api/settlement/rows` 하나뿐이다.** KPI 스트립도 그 응답의 `totals`
 * 에서 파생한다 — 집계 API 를 여기서 부르지 않는다. 한 화면에 소스가 둘이면 같은 숫자가 두
 * 계산 경로로 갈려 조용히 어긋난다(요약 탭이 집계 소스를 소유한다).
 *
 * **요약 탭(dashboard.js)과 상태 배선을 공유하지 않는다.** 그쪽의
 * `data-settlement-loading`/`-error`/`-denied` 와 `showState()` 는 **요약 pane 안에** 있어서,
 * 실무 탭에서 그것을 켜면 숨은 pane 안에서 켜진다 — 사용자는 아무것도 못 본다. 그래서 이
 * 파일이 자기 로딩·실패 노드(`data-settlement-ops-*`)를 따로 소유한다. 선택자도 전부
 * `-ops-` 로 갈랐다(둘은 같은 루트 안에 살아서 이름이 겹치면 서로의 노드를 잡는다).
 * 권한 거부는 셸이 전역으로 처리하므로 별도 denied 상태를 만들지 않고, 이 fetch 만 403 이면
 * 실패 노드가 그 사유를 사람 말로 적는다.
 *
 * **폭 0 함정이 없는 이유**: aging 막대를 SVG 가 아니라 **CSS 퍼센트 폭 HTML 막대**로 그린다.
 * 숨은 pane 은 `clientWidth === 0` 이라 그 사이에 그린 SVG 는 빈 그림으로 남지만, 퍼센트 폭은
 * 보이는 시점에 계산되므로 되그릴 필요 자체가 없다. 대신 **첫 로드 시점**만 탭 활성화에 맞춘다 —
 * 셸이 탭 전환 이벤트를 쏘지 않으므로(dashboard.js 에 dispatchEvent 가 없다) CSS 가 이미 SSOT
 * 로 쓰는 루트 속성 `data-settlement-active-tab` 을 MutationObserver 로 관찰한다. 두 번째
 * 신호를 발명하지 않고 기존 신호를 그대로 읽는다.
 *
 * **프래그먼트 재실행 규율(perf G4)**: 이 화면은 ERP 셸 프래그먼트로도 들어온다. 스왑 뒤
 * `<script src>` 만 재실행되고 DOMContentLoaded 는 다시 뜨지 않는다. 그래서
 *   (1) document/window 리스너는 `window.__FOMS_SETTLEMENT_OPS_BOUND` 싱글톤 뒤에서 1회만,
 *   (2) 실제 마운트는 루트의 `data-settlement-ops-mounted` 표식으로 루트당 1회만,
 *   (3) 스크립트 재실행과 swap 이벤트 **양쪽**에서 mountAll() 을 부른다.
 * (dashboard.js 하단 · order-change-banner.js:5-8 과 같은 패턴.)
 *
 * **실행 버튼 2종은 성격이 다르다**(원장 기록):
 *   [입금 확인] `POST /api/orders/<id>/payment-confirm` — `{type, confirmed}` 만으로 원클릭.
 *   [정산 청구] `POST /api/orders/<id>/settlement/issue` — `department`·`amount`·`reason`
 *               셋 다 필수(각각 없으면 400)라 컴팩트 폼을 연다.
 * 둘 다 기존 `FINANCE_MUTATION` 라우트이고 CSRF 헤더를 쓰지 않는다(같은 출처 세션 인증 —
 * `static/js/orders/erp-order-shared.js:2893` 와 같은 호출 형태). 부서 코드·라벨은 서버가
 * 렌더한 `<option>` 이 SSOT 다 — 이 파일에 부서 이름을 한 글자도 적지 않는다.
 *
 * 마크업은 전부 createElement + textContent 로 만든다(innerHTML 미사용) — 고객명이 그대로
 * 들어오는 자리라 이스케이프 실수의 여지를 남기지 않는다.
 */
(function () {
  'use strict';

  var ROOT_SELECTOR = '[data-foms-settlement-ops]';
  var ROWS_FALLBACK = '/api/settlement/rows';
  var OPS_TAB = 'ops';

  /* 실행 엔드포인트 경로. 주문 id 가 렌더 시점에 없어서 템플릿의 url_for 로 못 만든다 —
     기존 호출부(static/js/foms/tablet-completion-sheet.js:157)와 같은 상대 경로 표기다. */
  function paymentConfirmUrl(orderId) {
    return '/api/orders/' + encodeURIComponent(orderId) + '/payment-confirm';
  }
  function settlementIssueUrl(orderId) {
    return '/api/orders/' + encodeURIComponent(orderId) + '/settlement/issue';
  }

  /* 경과일 심각도 4단계. 서버 aging 버킷과 별개의 **표시 전용** 눈금이라 여기 둔다
     (버킷 목록·라벨 자체는 서버 `aging_options` 가 SSOT 다). */
  var ELAPSED_STEPS = [
    { max: 7, cls: 's-ops-b--e0' },
    { max: 30, cls: 's-ops-b--e1' },
    { max: 60, cls: 's-ops-b--e2' },
  ];
  var ELAPSED_WORST = 's-ops-b--e3';
  var PAGER_WINDOW = 2;   // 현재 페이지 좌우로 보여줄 번호 수

  /* 서버 렌더 표식. 이 속성이 루트에 있을 때만 12번째 칸("네이버 정산")을 그린다 —
     `<th>` 를 내는 조건(템플릿 `{% if can_view_channel_settlement %}`)과 **같은 신호**다.
     행 데이터(`row.naver_settlement` 유무)로 판정하면 권한자여도 네이버 행이 0건인 페이지에서
     `<td>` 수가 `<th>` 수보다 적어져 표가 통째로 한 칸씩 밀린다. */
  var CHANNEL_COL_ATTR = 'data-settlement-ops-channel-col';

  /* 네이버 정산 상태 코드 → 화면 문구. 서버는 코드(`SETTLED`/`PENDING`/`UNMATCHED`)와 날짜만
     내고 한글은 여기서 정한다(백엔드가 라벨을 만들면 이 화면의 금칙어가 API 를 타고 들어온다).
     **어휘 제약**: 이 표의 어떤 문구에도 금칙어를 쓰지 않는다. 대기 상태의 보조 정보는
     낱말 없이 `MM-DD` 날짜만 붙인다. */
  var NAVER_SETTLE_TEXT = {
    SETTLED: '정산완료',
    PENDING: '정산대기',
    UNMATCHED: '미매칭',
  };

  /* 배지 클래스는 `settlement-channel.css`(회계 게이트 뒤에서만 로드) 소유다 —
     컬럼이 그려지는 조건과 정확히 같아서 `settlement-operations.css` 를 열 필요가 없다. */
  var NAVER_SETTLE_CLASS = {
    SETTLED: 's-ch-ops-nv--done',
    PENDING: 's-ch-ops-nv--wait',
    UNMATCHED: 's-ch-ops-nv--none',
  };

  /* ═══════════════ 1. 헬퍼 ═══════════════ */

  function toggle(el, hidden) {
    if (el) el.classList.toggle('s-hidden', !!hidden);
  }

  function clear(el) {
    if (el) el.textContent = '';
  }

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  /** 금액 → "1,234,000". `null`(금액 미상)은 0 이 아니라 `null` 을 돌려준다 — 호출부가 "—"로 낸다. */
  function money(value) {
    return (typeof value === 'number' && isFinite(value)) ? value.toLocaleString('ko-KR') : null;
  }

  function count(value) {
    return (typeof value === 'number' && isFinite(value) ? value : 0).toLocaleString('ko-KR');
  }

  /** 원 → 만원(반올림). KPI·aging 요약 표기는 원 단위로 읽기엔 자릿수가 너무 길다. */
  function toMan(won) {
    return typeof won === 'number' && isFinite(won) ? Math.round(won / 10000) : 0;
  }

  /** 만원 → "2억 1,430만" / "838만" / "0" (요약 탭 fmtMan 과 같은 규칙). */
  function fmtMan(value) {
    value = Math.round(value);
    if (value === 0) return '0';
    var sign = value < 0 ? '−' : '';
    value = Math.abs(value);
    if (value >= 10000) {
      var eok = Math.floor(value / 10000);
      var man = value % 10000;
      return sign + (man ? eok + '억 ' + man.toLocaleString('ko-KR') + '만' : eok + '억');
    }
    return sign + value.toLocaleString('ko-KR') + '만';
  }

  /** "2026-03-01" → "3/1". 완료일 미상(빈 문자열)이면 "—". */
  function fmtDay(dayKey) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dayKey || ''));
    return m ? parseInt(m[2], 10) + '/' + parseInt(m[3], 10) : '—';
  }

  /**
   * "2026-09-05" → "09-05". 네이버 정산 칸 전용 표기다.
   *
   * 완료일 칸의 `fmtDay`("9/5")와 **일부러 다르다**: 이 칸의 날짜는 정산 사이클(월 2회)을
   * 세로로 훑어 같은 날짜끼리 묶어 보는 용도라 자릿수가 고정돼야 눈이 미끄러지지 않는다.
   * 값이 없으면 빈 문자열 — 호출부가 "아무것도 안 붙인다"로 처리한다.
   */
  function fmtMd(dayKey) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(String(dayKey || ''));
    return m ? m[2] + '-' + m[3] : '';
  }

  function elapsedClass(days) {
    for (var i = 0; i < ELAPSED_STEPS.length; i++) {
      if (days <= ELAPSED_STEPS[i].max) return ELAPSED_STEPS[i].cls;
    }
    return ELAPSED_WORST;
  }

  /** 서버가 낸 버킷 목록의 **마지막**이 가장 오래된 구간이다(코드를 이 파일에 적지 않는다). */
  function worstAgingCode(ctx) {
    var options = (ctx.state.data && ctx.state.data.aging_options) || [];
    return options.length ? options[options.length - 1].code : '';
  }

  /* ═══════════════ 2. 상태 표시 (이 탭이 자기 것을 소유한다) ═══════════════ */

  /**
   * 'loading' / 'error' / 'ready' 는 서로 다른 노드로 말한다. 무음 실패 금지 —
   * fetch 가 실패하면 사람이 읽는 사유와 재시도 버튼이 **이 탭 안에** 떠야 한다.
   *
   * **실패하면 KPI 스트립과 aging 막대도 함께 감춘다.** 셋 다 같은 응답에서 나오므로,
   * 목록만 실패로 바꾸고 위쪽 숫자를 남기면 "미수 624건"이 지금 조건의 값인 양 실패 문구
   * 옆에 계속 서 있게 된다 — 화면이 거짓말하는 자리다(실화면 스크린샷에서 실제로 그랬다).
   * 로딩 중에는 남긴다: 곧 교체될 값이고 로딩 문구가 그 사실을 말하고 있으며, 칩을 누를
   * 때마다 화면 위쪽이 사라졌다 나타나면 읽기가 더 어려워진다.
   */
  function showState(ctx, kind, detail) {
    toggle(ctx.els.loading, kind !== 'loading');
    toggle(ctx.els.error, kind !== 'error');
    toggle(ctx.els.gridwrap, kind !== 'ready');
    toggle(ctx.els.kpis, kind === 'error');
    toggle(ctx.els.agingPanel, kind === 'error');
    ctx.root.setAttribute('aria-busy', String(kind === 'loading'));
    if (kind !== 'ready') {
      toggle(ctx.els.emptyRows, true);
      clear(ctx.els.foot);
      clear(ctx.els.pager);
    }
    if (kind === 'error' && ctx.els.errorDetail && detail) {
      ctx.els.errorDetail.textContent = detail;
    }
  }

  /** 실행 버튼 결과 안내. `.alert` 를 쓰지 않는다(5초 뒤 자동으로 닫힌다). */
  function notice(ctx, kind, title, detail) {
    var node = ctx.els.notice;
    if (!node) return;
    node.classList.remove('s-hidden', 's-state--error', 's-state--loading');
    if (kind === 'error') node.classList.add('s-state--error');
    if (ctx.els.noticeTitle) ctx.els.noticeTitle.textContent = title;
    if (ctx.els.noticeDetail) ctx.els.noticeDetail.textContent = detail || '';
  }

  function clearNotice(ctx) {
    if (ctx.els.notice) ctx.els.notice.classList.add('s-hidden');
  }

  /** 응답에서 사람이 읽는 실패 사유를 뽑는다. 실행 API 는 `message`, 조회 API 는 `error` 를 쓴다. */
  function failureReason(res, body) {
    if (res && res.status === 403) {
      return '이 목록을 볼 권한이 없습니다. 관리자에게 권한을 요청하세요.';
    }
    if (body && (body.error || body.message)) return String(body.error || body.message);
    return '서버 응답 오류 (HTTP ' + (res ? res.status : '?') + ')';
  }

  /* ═══════════════ 3. 조회 ═══════════════ */

  function buildUrl(ctx) {
    var state = ctx.state;
    var base = ctx.root.getAttribute('data-rows-url') || ROWS_FALLBACK;
    var params = [
      'period=' + encodeURIComponent(state.period),
      'settlement=' + encodeURIComponent(state.settlement),
      'channel=' + encodeURIComponent(state.channel),
      'aging=' + encodeURIComponent(state.bucket),
      'page=' + encodeURIComponent(state.page),
    ];
    return base + (base.indexOf('?') === -1 ? '?' : '&') + params.join('&');
  }

  /** 공통 GET — 실패는 던진다(호출부가 상태 노드로 옮긴다). */
  async function getJson(url) {
    var res = await fetch(url, {
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    });
    var body = null;
    try {
      body = await res.json();
    } catch (parseError) {
      body = null;
    }
    if (!res.ok || !body || body.success !== true || !body.data) {
      var err = new Error(failureReason(res, body));
      err.handled = true;
      throw err;
    }
    return body.data;
  }

  async function loadRows(ctx) {
    var state = ctx.state;
    var seq = ++state.seq;
    showState(ctx, 'loading');
    try {
      var data = await getJson(buildUrl(ctx));
      if (seq !== state.seq) return;   // 늦게 온 응답이 최신 화면을 덮지 않게 한다
      state.data = data;
      // 서버가 필터·페이지의 최종 권위다(범위를 벗어난 page 는 서버가 접는다).
      if (data.filters) {
        state.period = data.filters.period;
        state.settlement = data.filters.settlement;
        state.channel = data.filters.channel;
        state.bucket = data.filters.aging || '';
      }
      state.page = data.page || 1;
      syncChips(ctx);
      showState(ctx, 'ready');
      renderAll(ctx);
    } catch (err) {
      if (seq !== state.seq) return;
      showState(ctx, 'error', err && err.handled
        ? err.message
        : '정산 서버에 연결하지 못했습니다. 네트워크를 확인한 뒤 다시 시도하세요.');
    }
  }

  /* ═══════════════ 4. 렌더 ═══════════════ */

  function appendKpi(wrap, spec) {
    var tile = el('div', 's-ops-kpi' + (spec.warn ? ' s-ops-kpi--warn' : ''));
    tile.setAttribute('data-settlement-ops-kpi', spec.key);
    tile.appendChild(el('div', 's-ops-kpi-k', spec.label));
    var value = el('div', 's-ops-kpi-v', spec.value);
    if (spec.unit) value.appendChild(el('i', null, spec.unit));
    tile.appendChild(value);
    tile.appendChild(el('div', 's-ops-kpi-sub', spec.sub));
    wrap.appendChild(tile);
  }

  function renderKpis(ctx) {
    var wrap = ctx.els.kpis;
    if (!wrap) return;
    clear(wrap);
    var data = ctx.state.data || {};
    var totals = data.totals || {};
    appendKpi(wrap, {
      key: 'receivable_count', label: '미수 건수',
      value: count(totals.receivable_count), unit: '건', warn: (totals.receivable_count || 0) > 0,
      sub: '잔금 입금 미확인 · 현재 필터 기준',
    });
    appendKpi(wrap, {
      key: 'balance', label: '미수 잔금 합',
      value: fmtMan(toMan(totals.balance)), unit: '원',
      sub: '잔금 = 출고가 − 예약금 (0 미만은 과입금으로 분리)',
    });
    appendKpi(wrap, {
      key: 'overpaid', label: '과입금 합',
      value: fmtMan(toMan(totals.overpaid)), unit: '원',
      // 잔금 클램프가 삼키는 금액이다. 0 이어도 칸을 없애지 않는다 — 사라지면 아무도 못 본다.
      sub: (totals.overpaid || 0) > 0 ? '예약금이 출고가를 넘은 금액 — 환급 대상' : '환급 대상 없음',
    });
    appendKpi(wrap, {
      key: 'unknown_completion', label: '완료일 미상',
      value: count(totals.unknown_completion_count), unit: '건',
      sub: '경과일을 셀 수 없어 기간 칩·aging 구간 밖입니다',
    });
  }

  /**
   * aging 구간 막대. 값은 **목록과 같은 응답**(`aging_summary`)에서 온다 — 구간마다 따로
   * 묻지 않는다. 예전에는 구간별로 `aging=<code>` 요청을 5번 직렬로 보냈는데, 한 요청이
   * 모집단 전량 스캔이라 스코프를 한 번 바꿀 때마다 같은 스캔이 6번 돌았다
   * (2026-08-31 운영 실측: 막대가 다 차기까지 2.9초, 그중 서버 1.26초).
   *
   * 서버가 내는 `aging_summary` 는 **선택된 구간과 무관한 스코프(기간·차감청구·채널) 기준**
   * 이라 막대를 눌러 목록만 좁혀도 값이 무너지지 않는다 — 옛 직렬 호출이 `aging` 파라미터를
   * 구간 코드로 덮어써서 지키던 성질을 서버가 대신 보장한다.
   */
  function renderAging(ctx, buckets) {
    var host = ctx.els.aging;
    if (!host) return;
    clear(host);
    var total = buckets.reduce(function (acc, b) { return acc + (b.count || 0); }, 0);
    toggle(ctx.els.emptyAging, total > 0);
    host.classList.toggle('s-ops-aging--has-sel', !!ctx.state.bucket);
    if (!total) return;

    var max = Math.max.apply(null, buckets.map(function (b) { return b.amount || 0; }).concat([1]));
    buckets.forEach(function (bucket, index) {
      var row = el('button', 's-ops-aging-row');
      row.type = 'button';
      row.setAttribute('data-settlement-ops-bucket', bucket.code);
      row.setAttribute('aria-pressed', String(ctx.state.bucket === bucket.code));
      row.appendChild(el('span', 's-ops-aging-lbl', bucket.label));
      var track = el('div', 's-ops-aging-track');
      // 0 인 구간은 막대를 **아예 그리지 않는다.** 막대에 최소 폭(3px)이 있어서 0 을 그리면
      // "적지만 있다"는 거짓 신호가 된다 — 요약 탭 aging 차트가 같은 이유로 같은 계약을 갖는다
      // (test_dashboard_js_draws_no_series_bar_for_zero_value). 값 글자가 0 을 정확히 말한다.
      if ((bucket.amount || 0) > 0) {
        var bar = el('span', 's-ops-aging-bar');
        // 폭·색은 인라인 스타일 금지 규칙 때문에 커스텀 프로퍼티로만 넘긴다(CSS 가 소비).
        bar.style.setProperty('--s-ops-bar-pct', (bucket.amount / max * 72).toFixed(2) + '%');
        bar.style.setProperty('--s-ops-bar-color', 'var(--s-ops-ramp-' + (index + 1) + ')');
        track.appendChild(bar);
      }
      var value = el('span', 's-ops-aging-val', fmtMan(toMan(bucket.amount)) + '원 ');
      value.appendChild(el('small', null, '· ' + count(bucket.count) + '건'));
      track.appendChild(value);
      row.appendChild(track);
      host.appendChild(row);
    });
  }

  function badge(cls, text) {
    return el('span', 's-ops-b ' + cls, text);
  }

  function dash() {
    return el('span', 's-ops-dash', '—');
  }

  /** 금액 칸 — `null`(금액 미상)은 0 이 아니라 "—"다. 둘을 섞으면 화면이 거짓말한다. */
  function moneyCell(value, cls) {
    var td = el('td', 's-ops-num' + (cls ? ' ' + cls : ''));
    var text = money(value);
    if (text === null) td.appendChild(dash());
    else td.textContent = text;
    return td;
  }

  function customerCell(row) {
    var td = el('td');
    td.appendChild(el('span', 's-ops-cust-nm', row.customer_name || '-'));
    td.appendChild(el('span', 's-ops-cust-no', '#' + row.order_id));
    return td;
  }

  function depositCell(row) {
    var td = el('td', 's-ops-num');
    var text = money(row.deposit);
    td.appendChild(text === null ? dash() : el('div', null, text));
    td.appendChild(el(
      'div',
      's-ops-subline ' + (row.deposit_confirmed ? 's-ops-subline--ok' : 's-ops-subline--warn'),
      row.deposit_confirmed ? '✓ 확인' : '미확인'
    ));
    return td;
  }

  function overpaidCell(row) {
    var td = el('td', 's-ops-num');
    // 0 은 값으로 내지 않는다 — 과입금 칸의 숫자는 "돌려줄 돈이 있다"는 신호여야 한다.
    if ((row.overpaid || 0) > 0) {
      td.classList.add('s-ops-over');
      td.textContent = money(row.overpaid);
    } else {
      td.appendChild(dash());
    }
    return td;
  }

  function elapsedCell(row) {
    var td = el('td');
    if (row.elapsed_days == null) {
      td.appendChild(dash());
      return td;
    }
    if (row.paid) {
      td.appendChild(badge('s-ops-b--paid', '입금 완료'));
      return td;
    }
    var chip = badge(elapsedClass(row.elapsed_days), count(row.elapsed_days) + '일');
    if (row.aging_label) chip.title = '완료 후 ' + row.aging_label;
    td.appendChild(chip);
    return td;
  }

  function cashCell(row) {
    var td = el('td');
    if (row.cash_receipt_state === 'issued') td.appendChild(badge('s-ops-b--cash-ok', '발행됨'));
    else if (row.cash_receipt_state === 'requested') td.appendChild(badge('s-ops-b--cash-req', '요청 · 미발행'));
    else td.appendChild(dash());
    return td;
  }

  function channelCell(row) {
    var td = el('td');
    // 코드와 표시 라벨이 다르면 외부 채널이다("NAVER"→"네이버"). 색은 표시 보조일 뿐,
    // 사실은 언제나 `channel_label` 글자가 말한다(색만으로 말하지 않는다).
    var external = String(row.channel || '') !== String(row.channel_label || '');
    td.appendChild(badge(
      external ? 's-ops-b--ch-ext' : 's-ops-b--ch-normal',
      row.channel_label || row.channel || '-'
    ));
    return td;
  }

  function settlementCell(row) {
    var td = el('td');
    td.appendChild(badge(
      row.settlement_issued ? 's-ops-b--settle-ok' : 's-ops-b--settle-wait',
      row.settlement_issued ? '청구완료' : '대기'
    ));
    return td;
  }

  /**
   * 12번째 칸 "네이버 정산" — 외부 채널(네이버)이 이 주문의 돈을 언제 줬는지/줄 것인지.
   *
   * 값은 서버가 판정해 내려준 `row.naver_settlement` 그대로다(상태 코드 + 날짜 2종).
   * **금액은 그리지 않는다** — 노출 최소화 원칙이고, 서버도 화면에 쓰라고 준 값이 아니다.
   *
   * 네 갈래를 문구로 구분한다(색만으로 말하지 않는다):
   *   값 없음(비네이버 주문) → "—" · 미매칭 → "미매칭" ·
   *   완료 → "정산완료" + 가장 최근 완료일 · 대기 → "정산대기" + 서버가 고른 가장 이른 날짜.
   * 대기 쪽 날짜는 **낱말 없이 날짜만** 붙인다(이 화면의 어휘 제약).
   */
  function naverSettleCell(row) {
    var td = el('td');
    var cell = row && row.naver_settlement;
    var text = cell && NAVER_SETTLE_TEXT[cell.status];
    if (!text) {
      // 비네이버 주문(값 None)과, 서버가 모르는 코드를 보낸 경우 둘 다 "—" 다.
      // 모르는 코드를 배지로 그리면 화면이 없는 상태를 지어내는 셈이라 하지 않는다.
      td.appendChild(dash());
      return td;
    }
    var chip = el('span', 's-ch-ops-nv ' + NAVER_SETTLE_CLASS[cell.status], text);
    // 날짜는 배지 **안쪽** 자식이다 — `.s-ch-ops-nv` 가 inline-flex + gap 이라 바깥에 두면
    // 간격도 색 단계도 설계와 어긋난다(스타일 SSOT 는 settlement-channel.css).
    var iso = cell.status === 'SETTLED' ? cell.settle_complete_date : cell.settle_expect_date;
    var day = fmtMd(iso);
    if (day) {
      chip.appendChild(el('span', 's-ch-ops-nv-date', day));
      td.title = iso;
    }
    td.appendChild(chip);
    return td;
  }

  function actionCell(ctx, row) {
    var td = el('td');
    var cell = el('div', 's-ops-actions');
    if (!row.paid && typeof row.balance === 'number' && row.balance > 0) {
      var confirmBtn = el('button', 's-ops-btn s-ops-btn--xs s-ops-btn--primary', '입금 확인');
      confirmBtn.type = 'button';
      confirmBtn.setAttribute('data-settlement-ops-confirm', String(row.order_id));
      cell.appendChild(confirmBtn);
    }
    if (!row.settlement_issued) {
      var issueBtn = el('button', 's-ops-btn s-ops-btn--xs', '정산 청구');
      issueBtn.type = 'button';
      issueBtn.setAttribute('data-settlement-ops-issue', String(row.order_id));
      cell.appendChild(issueBtn);
    }
    if (!cell.childElementCount) cell.appendChild(dash());
    td.appendChild(cell);
    return td;
  }

  function renderRows(ctx) {
    var body = ctx.els.rows;
    if (!body) return;
    clear(body);
    var data = ctx.state.data || {};
    var rows = data.rows || [];
    toggle(ctx.els.emptyRows, rows.length > 0);
    toggle(ctx.els.gridwrap, rows.length === 0);
    var worst = worstAgingCode(ctx);
    rows.forEach(function (row) {
      var tr = el('tr');
      tr.setAttribute('data-settlement-ops-row', String(row.order_id));
      if (row.receivable && worst && row.aging === worst) tr.classList.add('s-ops-row--overdue');
      tr.appendChild(customerCell(row));
      tr.appendChild(channelCell(row));
      tr.appendChild(el('td', null, fmtDay(row.completion_date)));
      tr.appendChild(moneyCell(row.shipping_price));
      tr.appendChild(depositCell(row));
      tr.appendChild(moneyCell(row.balance, 's-ops-balance' + (row.paid ? ' s-ops-balance--paid' : '')));
      tr.appendChild(overpaidCell(row));
      tr.appendChild(elapsedCell(row));
      tr.appendChild(cashCell(row));
      tr.appendChild(settlementCell(row));
      // 서버가 `<th>` 를 낸 렌더에서만 `<td>` 를 낸다(같은 신호 · CHANNEL_COL_ATTR 주석 참고).
      if (ctx.showChannelCol) tr.appendChild(naverSettleCell(row));
      tr.appendChild(actionCell(ctx, row));
      body.appendChild(tr);
    });
  }

  function renderFoot(ctx) {
    var foot = ctx.els.foot;
    if (!foot) return;
    clear(foot);
    var data = ctx.state.data || {};
    var totals = data.totals || {};
    var from = ((data.page || 1) - 1) * (data.per_page || 0) + 1;
    var to = Math.min((data.page || 1) * (data.per_page || 0), data.total_count || 0);
    var parts = [
      // 화면에 몇 건이 보이는지가 아니라 **필터에 걸린 전량**을 말한다(캡으로 자르지 않는다).
      ['조건 전체', count(data.total_count) + '건'],
      ['현재 페이지', (data.total_count ? count(from) + '–' + count(to) : '0') + '번째'],
      ['미수(조건 전체)', count(totals.receivable_count) + '건 · ' + fmtMan(toMan(totals.balance)) + '원'],
    ];
    if ((totals.overpaid || 0) > 0) {
      parts.push(['과입금(조건 전체)', fmtMan(toMan(totals.overpaid)) + '원']);
    }
    parts.forEach(function (pair) {
      var span = el('span', null, pair[0] + ' ');
      span.appendChild(el('b', null, pair[1]));
      foot.appendChild(span);
    });
  }

  function pageButton(label, page, opts) {
    var btn = el('button', 's-ops-page', label);
    btn.type = 'button';
    if (opts && opts.current) btn.setAttribute('aria-current', 'page');
    if (opts && opts.disabled) btn.disabled = true;
    else btn.setAttribute('data-settlement-ops-page', String(page));
    if (opts && opts.aria) btn.setAttribute('aria-label', opts.aria);
    return btn;
  }

  /** 번호 페이저(60건/page). 무한스크롤 금지 — 경리 업무는 "몇 페이지째"가 작업 기록이다. */
  function renderPager(ctx) {
    var pager = ctx.els.pager;
    if (!pager) return;
    clear(pager);
    var data = ctx.state.data || {};
    var total = data.total_pages || 1;
    var page = data.page || 1;
    if (total <= 1) return;

    pager.appendChild(pageButton('‹ 이전', page - 1, { disabled: page <= 1, aria: '이전 페이지' }));
    var pages = [];
    for (var i = 1; i <= total; i++) {
      if (i === 1 || i === total || Math.abs(i - page) <= PAGER_WINDOW) pages.push(i);
    }
    var prev = 0;
    pages.forEach(function (n) {
      if (prev && n - prev > 1) pager.appendChild(el('span', 's-ops-page-gap', '…'));
      pager.appendChild(pageButton(String(n), n, {
        current: n === page,
        aria: n + '페이지',
      }));
      prev = n;
    });
    pager.appendChild(pageButton('다음 ›', page + 1, { disabled: page >= total, aria: '다음 페이지' }));
  }

  /** aging 막대로 건 필터를 필터바에 되비친다 — 목록만 봐서는 어느 구간인지 알 수 없다. */
  function renderBucketChip(ctx) {
    var slot = ctx.els.bucketChip;
    if (!slot) return;
    clear(slot);
    if (!ctx.state.bucket) return;
    var options = (ctx.state.data && ctx.state.data.aging_options) || [];
    var match = options.filter(function (opt) { return opt.code === ctx.state.bucket; })[0];
    var chip = el('button', 's-ops-chip--clear', '경과 ' + (match ? match.label : ctx.state.bucket) + ' ✕');
    chip.type = 'button';
    chip.setAttribute('data-settlement-ops-bucket-clear', '1');
    slot.appendChild(chip);
  }

  function syncChips(ctx) {
    ctx.els.chipGroups.forEach(function (group) {
      var key = group.getAttribute('data-settlement-ops-filter');
      var active = ctx.state[key];
      group.querySelectorAll('[data-settlement-ops-value]').forEach(function (chip) {
        chip.setAttribute('aria-pressed', String(chip.getAttribute('data-settlement-ops-value') === active));
      });
    });
  }

  function renderAll(ctx) {
    renderKpis(ctx);
    renderRows(ctx);
    renderAging(ctx, (ctx.state.data && ctx.state.data.aging_summary) || []);
    renderFoot(ctx);
    renderPager(ctx);
    renderBucketChip(ctx);
  }

  /* ═══════════════ 5. 실행 버튼 2종 ═══════════════ */

  function rowById(ctx, orderId) {
    var rows = (ctx.state.data && ctx.state.data.rows) || [];
    return rows.filter(function (row) { return String(row.order_id) === String(orderId); })[0] || null;
  }

  /** 공통 POST(JSON). CSRF 헤더 없음 — 같은 출처 세션 인증이다(기존 호출부와 동일). */
  async function postJson(url, payload) {
    var res = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(payload),
    });
    var body = null;
    try {
      body = await res.json();
    } catch (parseError) {
      body = null;
    }
    if (!res.ok || !body || body.success !== true) {
      var err = new Error(failureReason(res, body));
      err.handled = true;
      throw err;
    }
    return body;
  }

  /** [입금 확인] — 원클릭. 성공하면 현재 페이지를 다시 읽어 금액·미수 집계를 되맞춘다. */
  async function confirmBalance(ctx, orderId) {
    if (ctx.state.busy) return;
    var row = rowById(ctx, orderId);
    ctx.state.busy = true;
    clearNotice(ctx);
    try {
      await postJson(paymentConfirmUrl(orderId), { type: 'balance', confirmed: true });
      notice(ctx, 'ok', '잔금 입금을 확인했습니다.',
        (row ? row.customer_name + ' ' : '') + '#' + orderId + ' — 목록을 다시 읽었습니다.');
      await loadRows(ctx);
    } catch (err) {
      notice(ctx, 'error', '입금 확인에 실패했습니다.',
        err && err.handled ? err.message : '네트워크 오류입니다. 잠시 후 다시 시도하세요.');
    } finally {
      ctx.state.busy = false;
    }
  }

  function openIssueForm(ctx, orderId) {
    var row = rowById(ctx, orderId);
    ctx.state.issueOrderId = orderId;
    if (ctx.els.issueTarget) {
      ctx.els.issueTarget.textContent = (row ? row.customer_name + ' ' : '') + '#' + orderId;
    }
    toggle(ctx.els.issueForm, false);
    if (ctx.els.issueDepartment) ctx.els.issueDepartment.focus();
  }

  function closeIssueForm(ctx) {
    ctx.state.issueOrderId = null;
    toggle(ctx.els.issueForm, true);
    if (ctx.els.issueAmount) ctx.els.issueAmount.value = '';
    if (ctx.els.issueReason) ctx.els.issueReason.value = '';
    if (ctx.els.issueDepartment) ctx.els.issueDepartment.value = '';
  }

  /**
   * [정산 청구] — `department`·`amount`·`reason` 3개가 모두 있어야 한다(없으면 서버 400).
   * 세 값을 보내기 전에 여기서 먼저 확인해 400 왕복 대신 사람이 읽는 안내를 낸다.
   */
  async function submitIssue(ctx) {
    if (ctx.state.busy) return;
    var orderId = ctx.state.issueOrderId;
    if (!orderId) return;
    var department = ctx.els.issueDepartment ? ctx.els.issueDepartment.value : '';
    var amountText = ctx.els.issueAmount ? ctx.els.issueAmount.value : '';
    var reason = ctx.els.issueReason ? ctx.els.issueReason.value.trim() : '';
    var amount = parseInt(amountText, 10);
    if (!department) {
      notice(ctx, 'error', '귀속 부서를 고르세요.', '세 항목이 모두 있어야 청구가 기록됩니다.');
      return;
    }
    if (!isFinite(amount) || amount === 0) {
      notice(ctx, 'error', '청구 금액을 숫자로 입력하세요.', '세 항목이 모두 있어야 청구가 기록됩니다.');
      return;
    }
    if (!reason) {
      notice(ctx, 'error', '사유를 입력하세요.', '세 항목이 모두 있어야 청구가 기록됩니다.');
      return;
    }

    ctx.state.busy = true;
    if (ctx.els.issueSubmit) ctx.els.issueSubmit.disabled = true;
    try {
      await postJson(settlementIssueUrl(orderId), {
        department: department,
        amount: amount,
        reason: reason,
      });
      notice(ctx, 'ok', '정산 비용 청구를 기록했습니다.', '#' + orderId + ' — 목록을 다시 읽었습니다.');
      closeIssueForm(ctx);
      await loadRows(ctx);
    } catch (err) {
      notice(ctx, 'error', '정산 청구에 실패했습니다.',
        err && err.handled ? err.message : '네트워크 오류입니다. 잠시 후 다시 시도하세요.');
    } finally {
      ctx.state.busy = false;
      if (ctx.els.issueSubmit) ctx.els.issueSubmit.disabled = false;
    }
  }

  /* ═══════════════ 6. CSV (화면에 있는 것만, 그 사실을 이름과 안내가 말한다) ═══════════════ */

  var CSV_HEADERS = [
    '주문번호', '고객명', '채널', '완료일', '출고가', '예약금', '예약금확인',
    '잔금', '과입금', '잔금확인', '경과일', '현금영수증', '차감청구',
  ];

  /**
   * 머리글 목록. 12번째 칸이 화면에 있을 때만 CSV 에도 한 칸이 는다 —
   * `csvRow` 와 **같은 조건**을 봐야 헤더와 데이터가 안 어긋난다.
   *
   * @param {object} ctx 마운트 컨텍스트(`showChannelCol` 을 읽는다).
   * @returns {string[]} 헤더 문자열 배열.
   */
  function csvHeaders(ctx) {
    return ctx.showChannelCol ? CSV_HEADERS.concat(['네이버 정산']) : CSV_HEADERS.slice();
  }

  function csvCell(value) {
    var text = value == null ? '' : String(value);
    return /[",\r\n]/.test(text) ? '"' + text.replace(/"/g, '""') + '"' : text;
  }

  /**
   * 한 줄. 네이버 정산 칸은 **상태 문구만** 넣는다 — 화면과 같은 낱말이라 사람이 대조할 수
   * 있고, 날짜·금액은 넣지 않는다(파일이 화면보다 많이 말하지 않는다).
   *
   * @param {object} ctx 마운트 컨텍스트.
   * @param {object} row 행 데이터.
   * @returns {string} CSV 한 줄.
   */
  function csvRow(ctx, row) {
    var cells = [
      row.order_id, row.customer_name, row.channel_label, row.completion_date,
      row.shipping_price == null ? '' : row.shipping_price,
      row.deposit == null ? '' : row.deposit,
      row.deposit_confirmed ? 'Y' : 'N',
      row.balance == null ? '' : row.balance,
      row.overpaid || 0,
      row.paid ? 'Y' : 'N',
      row.elapsed_days == null ? '' : row.elapsed_days,
      row.cash_receipt_state,
      row.settlement_issued ? '청구완료' : '대기',
    ];
    if (ctx.showChannelCol) {
      var cell = row.naver_settlement;
      cells.push((cell && NAVER_SETTLE_TEXT[cell.status]) || '');
    }
    return cells.map(csvCell).join(',');
  }

  /**
   * 지금 화면에 떠 있는 **한 페이지**만 내보낸다. 조건 전체(수백~수천 건)를 내려면 페이지 수만큼
   * 왕복해야 해서 서버에 파일 엔드포인트가 생기기 전에는 정직하지 않다 — 그래서 버튼 이름·파일명·
   * 안내가 전부 "현재 페이지"라고 말한다. 화면에 없는 것을 파일에 넣지 않는다.
   */
  function exportCsv(ctx) {
    var data = ctx.state.data;
    if (!data || !(data.rows || []).length) {
      notice(ctx, 'error', '내보낼 행이 없습니다.', '조건에 맞는 주문이 없습니다.');
      return;
    }
    var lines = [csvHeaders(ctx).join(',')].concat(data.rows.map(function (row) {
      return csvRow(ctx, row);
    }));
    // BOM 을 붙여야 Excel 이 UTF-8 로 연다(없으면 한글이 깨진 채 열린다).
    var blob = new Blob(['﻿' + lines.join('\r\n')], { type: 'text/csv;charset=utf-8' });
    var url = URL.createObjectURL(blob);
    var link = el('a');
    link.href = url;
    link.download = '정산수금_현재페이지_' + (data.as_of || '') + '_p' + (data.page || 1) + '.csv';
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
    notice(ctx, 'ok', 'CSV 를 내려받았습니다.',
      '현재 페이지 ' + count(data.rows.length) + '건만 담겨 있습니다(조건 전체 ' +
      count(data.total_count) + '건 중).');
  }

  /* ═══════════════ 7. 배선 ═══════════════ */

  // 사용자가 화면을 옮기면 직전 실행 결과 안내를 지운다. 실행 직후의 재조회에서는 지우지
  // 않는다 — "확인했습니다"가 그 재조회에 곧바로 덮여 사라지면 아무 일도 안 한 것처럼 보인다.
  function applyFilter(ctx, key, value) {
    if (ctx.state[key] === value) return;
    ctx.state[key] = value;
    ctx.state.page = 1;
    ctx.state.bucket = '';   // 스코프가 바뀌면 구간 선택은 의미를 잃는다
    clearNotice(ctx);
    syncChips(ctx);
    loadRows(ctx);
  }

  function toggleBucket(ctx, code) {
    ctx.state.bucket = ctx.state.bucket === code ? '' : code;
    ctx.state.page = 1;
    clearNotice(ctx);
    loadRows(ctx);
  }

  function bindControls(ctx) {
    // 리스너는 전부 이 루트 **안쪽**에만 붙는다. 프래그먼트 스왑으로 루트가 사라지면 리스너도
    // 같이 사라져 전역에 누적되지 않는다(perf G4).
    ctx.root.addEventListener('click', function (e) {
      var target = e.target;
      if (!target || !target.closest) return;

      var chip = target.closest('[data-settlement-ops-value]');
      if (chip && ctx.root.contains(chip)) {
        var group = chip.closest('[data-settlement-ops-filter]');
        if (group) applyFilter(ctx, group.getAttribute('data-settlement-ops-filter'),
          chip.getAttribute('data-settlement-ops-value'));
        return;
      }
      var bucket = target.closest('[data-settlement-ops-bucket]');
      if (bucket && ctx.root.contains(bucket)) {
        toggleBucket(ctx, bucket.getAttribute('data-settlement-ops-bucket'));
        return;
      }
      if (target.closest('[data-settlement-ops-bucket-clear]')) {
        toggleBucket(ctx, ctx.state.bucket);
        return;
      }
      var page = target.closest('[data-settlement-ops-page]');
      if (page && ctx.root.contains(page)) {
        var next = parseInt(page.getAttribute('data-settlement-ops-page'), 10);
        if (isFinite(next) && next !== ctx.state.page) {
          ctx.state.page = next;
          clearNotice(ctx);
          loadRows(ctx);
        }
        return;
      }
      var confirmBtn = target.closest('[data-settlement-ops-confirm]');
      if (confirmBtn && ctx.root.contains(confirmBtn)) {
        confirmBalance(ctx, confirmBtn.getAttribute('data-settlement-ops-confirm'));
        return;
      }
      var issueBtn = target.closest('[data-settlement-ops-issue]');
      if (issueBtn && ctx.root.contains(issueBtn)) {
        openIssueForm(ctx, issueBtn.getAttribute('data-settlement-ops-issue'));
        return;
      }
      if (target.closest('[data-settlement-ops-issue-cancel]')) {
        closeIssueForm(ctx);
        return;
      }
      if (target.closest('[data-settlement-ops-csv]')) {
        exportCsv(ctx);
        return;
      }
      if (target.closest('[data-settlement-ops-retry]')) {
        loadRows(ctx);
      }
    });
    if (ctx.els.issueForm) {
      ctx.els.issueForm.addEventListener('submit', function (e) {
        e.preventDefault();
        submitIssue(ctx);
      });
    }
  }

  /* ═══════════════ 8. 마운트 ═══════════════ */

  var mounts = [];

  function collectEls(root) {
    var q = function (sel) { return root.querySelector(sel); };
    return {
      kpis: q('[data-settlement-ops-kpis]'),
      aging: q('[data-settlement-ops-aging]'),
      agingPanel: q('[data-settlement-ops-aging-panel]'),
      emptyAging: q('[data-settlement-ops-empty="aging"]'),
      emptyRows: q('[data-settlement-ops-empty="rows"]'),
      bucketChip: q('[data-settlement-ops-bucket-chip]'),
      loading: q('[data-settlement-ops-loading]'),
      error: q('[data-settlement-ops-error]'),
      errorDetail: q('[data-settlement-ops-error-detail]'),
      notice: q('[data-settlement-ops-notice]'),
      noticeTitle: q('[data-settlement-ops-notice-title]'),
      noticeDetail: q('[data-settlement-ops-notice-detail]'),
      gridwrap: q('[data-settlement-ops-gridwrap]'),
      rows: q('[data-settlement-ops-rows]'),
      foot: q('[data-settlement-ops-foot]'),
      pager: q('[data-settlement-ops-pager]'),
      issueForm: q('[data-settlement-ops-issue-form]'),
      issueTarget: q('[data-settlement-ops-issue-target]'),
      issueDepartment: q('[data-settlement-ops-issue-department]'),
      issueAmount: q('[data-settlement-ops-issue-amount]'),
      issueReason: q('[data-settlement-ops-issue-reason]'),
      issueSubmit: q('[data-settlement-ops-issue-submit]'),
      chipGroups: Array.prototype.slice.call(root.querySelectorAll('[data-settlement-ops-filter]')),
    };
  }

  function ensureLoaded(ctx) {
    if (ctx.state.loaded) return;
    ctx.state.loaded = true;
    loadRows(ctx);
  }

  /**
   * 첫 조회를 **탭이 열릴 때**로 미룬다. 요약 탭만 보고 나가는 사용자에게 전량 스캔 왕복을
   * 물리지 않기 위해서다.
   *
   * 셸은 탭 전환 이벤트를 쏘지 않는다(dashboard.js 에 dispatchEvent 가 없다). 대신 CSS 가
   * 이미 SSOT 로 쓰는 루트 속성 `data-settlement-active-tab` 을 그대로 관찰한다 —
   * 두 번째 신호를 발명하지 않는다. 셸 밖(단독 렌더)이면 관찰할 대상이 없으니 즉시 연다.
   */
  function watchTabActivation(ctx) {
    var shell = ctx.root.closest('[data-settlement-active-tab]');
    if (!shell || typeof MutationObserver !== 'function') {
      ensureLoaded(ctx);
      return;
    }
    if (shell.getAttribute('data-settlement-active-tab') === OPS_TAB) ensureLoaded(ctx);
    ctx.observer = new MutationObserver(function () {
      if (shell.getAttribute('data-settlement-active-tab') === OPS_TAB) ensureLoaded(ctx);
    });
    ctx.observer.observe(shell, { attributes: true, attributeFilter: ['data-settlement-active-tab'] });
  }

  function mount(root) {
    if (!root || root.dataset.settlementOpsMounted === '1') return;
    root.dataset.settlementOpsMounted = '1';
    var ctx = {
      root: root,
      els: collectEls(root),
      // 마운트 시점 1회 판정. 서버 렌더 표식이라 응답마다 흔들리지 않는다.
      showChannelCol: root.hasAttribute(CHANNEL_COL_ATTR),
      state: {
        period: 'all', settlement: 'all', channel: 'all', bucket: '',
        page: 1, data: null, seq: 0, loaded: false, busy: false,
        issueOrderId: null,
      },
      observer: null,
    };
    mounts.push(ctx);
    syncChips(ctx);
    bindControls(ctx);
    watchTabActivation(ctx);
  }

  function mountAll() {
    // 떨어져 나간 루트는 정리한다 — 스왑으로 DOM 에서 사라진 화면의 옵저버를 남기지 않는다.
    mounts = mounts.filter(function (ctx) {
      if (ctx.root.isConnected) return true;
      if (ctx.observer) ctx.observer.disconnect();
      return false;
    });
    document.querySelectorAll(ROOT_SELECTOR).forEach(mount);
  }

  // 전역(document) 리스너는 싱글톤 뒤에서 1회만 — 프래그먼트 재실행 때 중복 누적 금지(perf G4).
  if (!window.__FOMS_SETTLEMENT_OPS_BOUND) {
    window.__FOMS_SETTLEMENT_OPS_BOUND = true;
    document.addEventListener('foms:main-content-swapped', mountAll);
    document.addEventListener('foms:erp-shell-fragment-swapped', mountAll);
    document.addEventListener('DOMContentLoaded', mountAll);
  }

  // defer 로 실린 첫 로드와, 셸이 <script src> 를 재실행하는 스왑 경로를 **둘 다** 덮는다.
  mountAll();
})();
