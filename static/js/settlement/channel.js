/**
 * 정산 대시보드 · 탭 4 "네이버 정산"(채널 정산) — 구현 계약서 §7 (2026-09-02).
 *
 * 계약: `docs/plans/2026-09-02-naver-settlement-contracts.md` §5(응답 스키마)·§6(앵커)·§7(범위).
 * 레이아웃 원안: `docs/research/2026-09-02-naver-settlement/06-ceo-2.md` §B-3.
 *
 * **데이터 소스는 `GET /api/settlement/channel` 하나뿐이다.** KPI·차트·원장·예외가 전부 같은
 * 응답에서 파생한다 — 한 화면에 소스가 둘이면 같은 숫자가 두 계산 경로로 갈려 조용히 어긋난다
 * (요약 탭은 집계 API, 실무 탭은 rows API 를 각각 하나씩만 쓰는 것과 같은 규율).
 *
 * **다른 탭과 상태 배선을 공유하지 않는다.** 요약 탭(dashboard.js)의
 * `data-settlement-loading`/`-error` 와 실무 탭(operations.js)의 `data-settlement-ops-*` 는
 * 각자의 pane **안에** 있다. 숨은 pane 안에서 로딩을 켜면 사용자는 아무것도 못 본다. 그래서
 * 이 파일은 자기 상태 노드(`data-settlement-ch-*`)만 만지고, 선택자도 전부 `-ch-` 로 갈랐다.
 *
 * **차트는 dashboard.js 의 인라인 SVG 렌더러를 복제했다**(파일 간 import 없음 · 전역 의존 없음).
 * 계약 §7 의 지시대로 복제이고, 두 곳이 갈라질 수 있다는 점을 알고 한 선택이다 — 요약 탭 차트는
 * 완료일 축, 이 탭은 정산 예정일 축이라 눈금·색 규칙이 앞으로 따로 움직인다.
 * 확장 2종:
 *   (a) `stackColumnChart` — 3계열 스택(일반/빠른/공제환급) + 전기 비교선. **음수는 0선 아래로
 *       내려 그린다.** 취소·환급 정산이 음수로 오는데 절대값으로 접으면 회계 화면이 거짓말한다.
 *   (b) `waterfallChart` — 부동 막대(누적 시작→끝), 단일 축, 감소 단계는 아래로, 캡은 부호 포함.
 *
 * **프래그먼트 재실행 규율(perf G4)**: ERP 셸 프래그먼트로도 들어온다. 스왑 뒤 `<script src>` 만
 * 재실행되고 DOMContentLoaded 는 다시 뜨지 않는다. 그래서
 *   (1) document 리스너는 `window.__FOMS_SETTLEMENT_CHANNEL_BOUND` 싱글톤 뒤에서 1회만,
 *   (2) 실제 마운트는 루트의 `data-settlement-ch-mounted` 표식으로 루트당 1회만,
 *   (3) 스크립트 재실행과 swap 이벤트 **양쪽**에서 mountAll() 을 부른다.
 * 폭 의존 SVG 는 window resize 대신 **루트별 ResizeObserver** 로 되그린다 — 옵저버가 루트와 함께
 * 죽으므로 스왑 뒤 새 스코프에서도 리사이즈가 살아 있다(전역 리스너 1회 등록의 사각이 없다).
 *
 * **CSRF**: 같은 출처 mutation 은 `partials/shared/csrf_bootstrap.html` 이 `window.fetch` 를
 * 감싸 `X-CSRF-Token` 을 자동으로 실어 보낸다(WRITE-GUARD-01, 단일 choke point). 그래서
 * operations.js 의 `postJson` 과 **같은 형태**로 헤더를 직접 적지 않는다 — route 별 ad hoc 토큰
 * 주입은 그 파일이 명시적으로 금지한 패턴이다.
 *
 * 마크업은 전부 createElement + textContent 로 만든다(SVG 문자열만 예외 — `esc()` 를 통과시킨다).
 * 구매자명·상품명이 그대로 들어오는 자리라 이스케이프 실수의 여지를 남기지 않는다.
 * 인라인 style 은 쓰지 않는다. 동적 폭·좌표는 CSS 커스텀 프로퍼티(`style.setProperty`)로 넘긴다 —
 * dashboard.js 의 `--s-bar-pct`/`--s-tt-x` 와 같은 방식이다.
 */
(function () {
  'use strict';

  var ROOT_SELECTOR = '[data-settlement-ch-root]';
  var CHANNEL_TAB = 'channel';
  var API_FALLBACK = '/api/settlement/channel';
  var SYNC_API_FALLBACK = '/api/settlement/channel/sync';

  /* v1.1 — 이 파일이 채널 pane 밖에서 맡는 한 자리(T12)와 pane 안의 새 도구 하나(T14).
     스트립 호스트는 **요약 탭 안**에 있어 채널 루트의 자손이 아니다. 그래서 마운트 축을
     둘로 나누되 새 document 리스너는 만들지 않는다 — 기존 mountAll() 이 둘 다 돈다. */
  var STRIP_SELECTOR = '[data-settlement-ch-strip]';
  var EXPORT_API_FALLBACK = '/api/settlement/channel/export.csv';

  /** 내려받기 항목. 앞 5종은 적재 원본을 그대로 쏟는 표고, 마지막 하나는 회계 제출용으로
      열을 골라 담은 표다(서버 정본 이름 `settle_case_sheet`). `filters` 가 false 인 표는
      유형·검색 조건을 받지 않는다(서버가 400 으로 거절하므로 화면이 애초에 안 싣는다 —
      일자 단위 표라 그 조건에 걸 열이 없다). `typeOf` 는 "유형 필터를 실을 수 있는 짝"이
      자기 kind 와 다른 표만 적는다(골라 담은 표는 건별 정산과 같은 유형 코드를 쓴다). */
  var EXPORT_KINDS = [
    { kind: 'settle_case', label: '건별 정산', sub: '상품주문 단위 · 매칭 상태 포함', filters: true },
    { kind: 'commission', label: '수수료', sub: '결제·판매·채널 수수료 내역', filters: true },
    { kind: 'vat_daily', label: '부가세 일별', sub: '일자 단위 과세·면세 집계', filters: false },
    { kind: 'vat_case', label: '부가세 건별', sub: '상품주문 단위 과세 내역', filters: true },
    { kind: 'settle_daily', label: '일별 정산', sub: '통장 입금 대사용 · 계좌는 마스킹', filters: false },
    { kind: 'settle_case_sheet', label: '정산내역 시트', sub: '구매자명·결제일·수수료 7열(회계 제출용)', filters: true, typeOf: 'settle_case' },
  ];

  var DEFAULT_BACK_DAYS = 30;      // 기본 조회 시작 = 오늘 − 30
  var DEFAULT_FORWARD_DAYS = 14;   // 기본 조회 끝 = 오늘 + 14 (정산 예정일은 미래를 본다)
  var PER_PAGE = 60;               // 원장 페이지 크기(계약 §7)
  var PAGER_WINDOW = 2;            // 현재 페이지 좌우로 보여줄 번호 수
  var POLL_INTERVAL_MS = 10000;    // 동기화 반영 확인 주기
  var POLL_MAX_TRIES = 6;          // 10초 × 6 = 60초까지만 기다린다
  var POLL_MAX_TRIES_BACKFILL = 60; // 소급 적재는 창을 여러 개 돌아 오래 걸린다(90일 ≈ 2분, 250일 ≈ 6분) — 10분
  var BACKFILL_MINUTES_PER_DAY = 0.025; // 실측(2026-09-03): 하루치 ≈ 1.5초 — 배너의 예상 시간용
  var SEARCH_DEBOUNCE_MS = 350;
  var RESIZE_DEBOUNCE_MS = 140;
  var LINE_HEADROOM = 1.5;         // 비교선이 축을 끌고 올라갈 수 있는 한도(막대가 주 마크다)

  /* ── 색 (dataviz 규칙: 형태 먼저, 범주 색은 고정 순서 배정) ──────────────
     스택 3계열은 "정산 금액 한 덩어리의 구성"이라 범주 3색이 아니라 **한 색상 램프**를 쓴다
     (settlement-dashboard.css 의 BLUE_BUCKET4 와 같은 스텝). 전기 비교선만 강조용 회색이다.
     워터폴 증감은 상태색(양호/경고/심각)을 쓰지 않는다 — 감소가 곧 나쁨이 아니기 때문이다. */
  var STACK_SERIES = [
    { key: 'normal', label: '일반 정산', color: '#104281' },
    { key: 'quick', label: '빠른 정산', color: '#2a78d6' },
    { key: 'deduction_restore', label: '공제 환급', color: '#86b6ef' },
  ];
  var COLOR_PREV = '#8a94a3';
  var COLOR_UP = '#2a78d6';
  var COLOR_DOWN = '#eb6834';
  var COLOR_TOTAL = '#104281';
  var CATEGORICAL = ['#2a78d6', '#eb6834', '#1baf7a', '#7b4bd6', '#b45309', '#0f8a8a'];
  var CATEGORICAL_REST = '#8a94a3';
  /** v1.2 F2 — "보류·한도" 상세 패널 id(타일의 aria-controls 가 가리킨다). */
  var HOLDBACK_DETAIL_ID = 'foms-settle-ch-holdback-detail';

  /** 원장 스위처 4종. `param` 이 null 인 뷰는 서버 재조회 없이 이미 받은 배열을 그린다. */
  var LEDGER_VIEWS = [
    { view: 'case', param: 'case', label: '건별 정산' },
    { view: 'commission', param: 'commission', label: '수수료' },
    { view: 'vat', param: 'vat_case', label: '부가세' },
    { view: 'exceptions', param: null, label: '예외' },
  ];

  /* 원장 표 컬럼. **라벨은 우리 화면의 열 이름**이고, 값 라벨(enum 한글)은 서버가 준
     `<field>_label` 을 그대로 쓴다 — 이 파일에 네이버 enum 한글을 적지 않는다. */
  var COLUMNS = {
    case: [
      { key: 'order_id', label: '주문번호', type: 'id' },
      { key: 'product_order_id', label: '상품주문번호', type: 'id' },
      { key: 'product_order_type', label: '유형', type: 'enum' },
      { key: 'settle_type', label: '구분', type: 'enum' },
      { key: 'purchaser_name', label: '구매자명', type: 'text' },
      { key: 'product_name', label: '상품명', type: 'text' },
      { key: 'pay_settle_amount', label: '결제 정산', type: 'money' },
      { key: 'total_pay_commission_amount', label: '수수료', type: 'money' },
      { key: 'settle_expect_amount', label: '정산 예정', type: 'money' },
    ],
    commission: [
      { key: 'order_no', label: '주문번호', type: 'id' },
      { key: 'product_order_id', label: '상품주문번호', type: 'id' },
      { key: 'product_name', label: '상품명', type: 'text' },
      { key: 'commission_type', label: '수수료 유형', type: 'enum' },
      { key: 'pay_means_type', label: '결제수단', type: 'enum' },
      { key: 'commission_basis_amount', label: '기준 금액', type: 'money' },
      { key: 'commission_amount', label: '수수료', type: 'money' },
    ],
    vat_case: [
      { key: 'settle_basis_date', label: '정산 기준일', type: 'text' },
      { key: 'order_id', label: '주문번호', type: 'id' },
      { key: 'product_order_id', label: '상품주문번호', type: 'id' },
      { key: 'detail_type', label: '구분', type: 'enum' },
      { key: 'status', label: '상태', type: 'enum' },
      { key: 'product_name', label: '상품명', type: 'text' },
      { key: 'total_sales_amount', label: '총매출', type: 'money' },
      { key: 'taxation_sales_amount', label: '과세', type: 'money' },
      { key: 'tax_exemption_sales_amount', label: '면세', type: 'money' },
    ],
  };

  /** 유형 필터가 읽는 필드 우선순위(원장 종류마다 "유형"의 정체가 다르다). */
  var TYPE_FIELDS = {
    case: ['product_order_type', 'settle_type'],
    commission: ['commission_type', 'pay_means_type'],
    vat_case: ['detail_type', 'status'],
  };

  /** 원장 행이 속한 날짜를 고르는 축(기준일 셀렉터가 표 그룹 축도 함께 바꾼다). */
  var BASIS_DATE_FIELD = {
    expect: 'settle_expect_date',
    complete: 'settle_complete_date',
    basis: 'settle_basis_date',
    pay: 'pay_date',
  };
  /** 원장마다 실제로 있는 축(서버 `_LEDGER_BASES` 와 같은 표). 없는 축은 셀렉트에서 잠근다 —
      수수료 표엔 결제일이, 부가세 표엔 정산 기준일밖에 없다(2026-09-03 실측: 라벨만 바뀌던 결함). */
  var LEDGER_BASES = {
    case: ['expect', 'complete', 'basis', 'pay'],
    commission: ['expect', 'complete', 'basis'],
    vat_case: ['basis'],
  };
  /** 축이 비어 표에서 빠진 행을 말할 때 쓰는 낱말. */
  var BASIS_NOUN = { complete: '완료일', basis: '정산 기준일', pay: '결제일' };

  /** VAT 기간표 8열. 키는 계약 §5 의 `vat.rows[]`·`vat.total` 과 정확히 같다. */
  var VAT_COLUMNS = [
    { key: 'total_sales', label: '총매출' },
    { key: 'taxation_sales', label: '과세매출' },
    { key: 'tax_exemption_sales', label: '면세매출' },
    { key: 'credit_card', label: '신용카드' },
    { key: 'cash_income_deduction', label: '현금(소득공제)' },
    { key: 'cash_outgoing_evidence', label: '현금(지출증빙)' },
    { key: 'cash_exclusion_issuance', label: '현금(발급제외)' },
    { key: 'other', label: '기타' },
  ];

  /* ═══════════════ 1. 헬퍼 ═══════════════ */

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text != null) node.textContent = text;
    return node;
  }

  function clearNode(node) {
    if (node) node.textContent = '';
  }

  /**
   * 표시/숨김. `hidden` 속성과 전용 클래스를 **둘 다** 쓴다 — 파셜은 상태 노드를 `hidden` 으로
   * 렌더하고, 전역 Bootstrap/erp-pro 가 display 를 덮는 자리도 있어서 한쪽만으로는 안 닫힌다.
   */
  function setHidden(node, hidden) {
    if (!node) return;
    node.hidden = !!hidden;
    node.classList.toggle('s-ch-hidden', !!hidden);
  }

  /** SVG 문자열에 넣는 텍스트 이스케이프(상품명·구매자명이 들어오는 자리). */
  function esc(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  function isNum(v) {
    return typeof v === 'number' && isFinite(v);
  }

  /**
   * 금액 → "₩1,234,000" / "-₩389,000". **음수는 부호를 그대로 남긴다**(계약 D-1: 절대값 변환
   * 금지). 값이 없으면 null 을 돌려준다 — 호출부가 "—" 로 낸다(0 과 미상은 다른 사실이다).
   */
  function money(value) {
    if (!isNum(value)) return null;
    var rounded = Math.round(value);
    var sign = rounded < 0 ? '-' : '';
    return sign + '₩' + Math.abs(rounded).toLocaleString('ko-KR');
  }

  function moneyText(value) {
    var text = money(value);
    return text == null ? '—' : text;
  }

  /** 워터폴 캡처럼 증감을 말해야 하는 자리 — 양수에도 `+` 를 붙인다. */
  function signedMoney(value) {
    if (!isNum(value)) return '—';
    return (value > 0 ? '+' : '') + money(value);
  }

  function toMan(won) {
    return isNum(won) ? Math.round(won / 10000) : 0;
  }

  /** 만원 → "2억 1,430만" / "838만" / "0". 축약은 **표시 계층에서만** 한다(계약 D-5). */
  function fmtMan(value) {
    value = Math.round(value);
    if (value === 0) return '0';
    var neg = value < 0 ? '-' : '';
    value = Math.abs(value);
    if (value >= 10000) {
      var eok = Math.floor(value / 10000);
      var man = value % 10000;
      return neg + (man ? eok + '억 ' + man.toLocaleString('ko-KR') + '만' : eok + '억');
    }
    return neg + value.toLocaleString('ko-KR') + '만';
  }

  /** 축 눈금용 압축 표기(만원 단위 입력). */
  function fmtTick(value) {
    if (value === 0) return '0';
    var neg = value < 0 ? '-' : '';
    var abs = Math.abs(value);
    if (abs >= 10000) {
      var e = abs / 10000;
      return neg + (Number.isInteger(e) ? e : e.toFixed(1)) + '억';
    }
    return neg + abs.toLocaleString('ko-KR') + '만';
  }

  function fmtCount(value) {
    return (isNum(value) ? value : 0).toLocaleString('ko-KR');
  }

  /** 비율(0~1) → "5.0%". 계약 §5 의 `commission_rate`·`match_rate` 는 **비(比)** 다. */
  function fmtRatio(ratio, digits) {
    if (!isNum(ratio)) return '—';
    return (ratio * 100).toFixed(digits == null ? 1 : digits) + '%';
  }

  function sumBy(rows, pick) {
    return (rows || []).reduce(function (acc, row) {
      var v = pick(row);
      return acc + (isNum(v) ? v : 0);
    }, 0);
  }

  /** 증감률. 비교 기준이 0/없음이면 null — "+∞%" 같은 거짓 수치를 만들지 않는다. */
  function deltaOf(cur, prev) {
    if (!isNum(cur) || !isNum(prev) || prev <= 0) return null;
    var pct = (cur / prev - 1) * 100;
    var flat = Math.abs(pct) < 0.05;
    return {
      text: (pct >= 0 ? '+' : '-') + Math.abs(pct).toFixed(1) + '%',
      arrow: flat ? '=' : (pct > 0 ? '▲' : '▼'),
      cls: flat ? 's-ch-flat' : (pct > 0 ? 's-ch-up' : 's-ch-down'),
    };
  }

  function niceScale(maxV, tickCount) {
    tickCount = tickCount || 5;
    if (!(maxV > 0)) return { top: 0, ticks: [0] };
    var rough = maxV / tickCount;
    var mag = Math.pow(10, Math.floor(Math.log10(rough)));
    var step = mag * 10;
    var candidates = [1, 2, 2.5, 5, 10];
    for (var i = 0; i < candidates.length; i++) {
      if (maxV / (candidates[i] * mag) <= tickCount) { step = candidates[i] * mag; break; }
    }
    var top = Math.ceil(maxV / step) * step;
    var ticks = [];
    for (var v = 0; v <= top + 1e-9; v += step) ticks.push(Math.round(v));
    return { top: top, ticks: ticks };
  }

  function roundTopRect(x, y, w, h, r) {
    r = Math.min(r, w / 2, h);
    return 'M' + x + ',' + (y + h) + ' L' + x + ',' + (y + r) +
      ' Q' + x + ',' + y + ' ' + (x + r) + ',' + y +
      ' L' + (x + w - r) + ',' + y +
      ' Q' + (x + w) + ',' + y + ' ' + (x + w) + ',' + (y + r) +
      ' L' + (x + w) + ',' + (y + h) + ' Z';
  }

  /* ── 날짜 ─────────────────────────────────────────────────────────
     정산 API 응답은 전부 KST 달력 날짜다(계약 D-4). 브라우저 로컬 타임존이 아니라 서울 달력을
     기준으로 기본 구간을 만든다 — 해외/UTC 로 맞춰 둔 PC 에서 하루가 밀리지 않게. */

  function kstToday() {
    try {
      var text = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
      }).format(new Date());
      if (/^\d{4}-\d{2}-\d{2}$/.test(text)) return text;
    } catch (err) { /* Intl 미지원/타임존 미탑재 — 아래 로컬 폴백 */ }
    var now = new Date();
    return now.getFullYear() + '-' +
      String(now.getMonth() + 1).padStart(2, '0') + '-' +
      String(now.getDate()).padStart(2, '0');
  }

  function isDay(text) {
    return /^\d{4}-\d{2}-\d{2}$/.test(String(text || ''));
  }

  /** "YYYY-MM-DD" + n일. UTC 로 계산해 DST·로컬 오프셋의 영향을 받지 않는다. */
  function addDays(day, delta) {
    if (!isDay(day)) return day;
    var base = Date.UTC(+day.slice(0, 4), +day.slice(5, 7) - 1, +day.slice(8, 10));
    var moved = new Date(base + delta * 86400000);
    return moved.getUTCFullYear() + '-' +
      String(moved.getUTCMonth() + 1).padStart(2, '0') + '-' +
      String(moved.getUTCDate()).padStart(2, '0');
  }

  /** 축 라벨: 일="9/1", 주="9/1주", 월="8월". 형식이 다르면 원문을 그대로 둔다. */
  function bucketLabel(key, granularity) {
    var text = String(key || '');
    if (/^\d{4}-\d{2}$/.test(text)) return parseInt(text.slice(5, 7), 10) + '월';
    if (!isDay(text)) return text;
    var short = parseInt(text.slice(5, 7), 10) + '/' + parseInt(text.slice(8, 10), 10);
    return granularity === 'week' ? short + '주' : short;
  }

  /** ISO 시각 → "09-02 04:23". 값이 없으면 빈 문자열(호출부가 문구를 갈라 쓴다). */
  function fmtStamp(iso) {
    var text = String(iso || '');
    var m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(text);
    return m ? m[2] + '-' + m[3] + ' ' + m[4] + ':' + m[5] : '';
  }

  /** 지금으로부터 몇 시간 전인지. 파싱 실패면 null — "N시간 전"을 지어내지 않는다. */
  function hoursSince(iso) {
    if (!iso) return null;
    var text = String(iso);
    var stamped = /[zZ]|[+-]\d{2}:\d{2}$/.test(text) ? text : text.replace(' ', 'T') + 'Z';
    var then = Date.parse(stamped);
    if (!isFinite(then)) return null;
    return Math.max(0, (Date.now() - then) / 3600000);
  }

  function agoText(iso) {
    var hours = hoursSince(iso);
    if (hours == null) return '';
    if (hours < 1) return '방금 전';
    if (hours < 48) return Math.floor(hours) + '시간 전';
    return Math.floor(hours / 24) + '일 전';
  }

  /* ═══════════════ 2. 툴팁 (이 탭이 자기 것을 소유한다) ═══════════════ */

  /**
   * 툴팁 노드는 파셜 앵커에 없다(계약 §6). 요약 탭의 툴팁을 빌려 쓰면 그쪽 pane 안에서 떠서
   * 보이지 않으므로 **루트 안에 직접 하나 만든다** — 루트가 스왑으로 사라지면 같이 사라진다.
   */
  function ensureTip(ctx) {
    if (ctx.tip && ctx.tip.isConnected) return ctx.tip;
    var tip = el('div', 's-ch-tip');
    tip.setAttribute('aria-hidden', 'true');
    ctx.root.appendChild(tip);
    ctx.tip = tip;
    return tip;
  }

  function showTip(ctx, x, y, title, rows) {
    var tip = ensureTip(ctx);
    clearNode(tip);
    tip.appendChild(el('div', 's-ch-tip-title', title));
    (rows || []).forEach(function (row) {
      var line = el('div', 's-ch-tip-row');
      if (row.color) {
        var key = el('i', 's-ch-tip-key');
        key.style.setProperty('--s-ch-key-color', row.color);
        line.appendChild(key);
      }
      line.appendChild(el('span', 's-ch-tip-val' + (row.neg ? ' s-ch-neg' : ''), row.val));
      if (row.lbl) line.appendChild(el('span', 's-ch-tip-lbl', row.lbl));
      tip.appendChild(line);
    });
    tip.classList.add('s-ch-on');
    var box = tip.getBoundingClientRect();
    var px = x + 14;
    var py = y + 16;
    if (px + box.width > window.innerWidth - 8) px = x - box.width - 12;
    if (py + box.height > window.innerHeight - 8) py = y - box.height - 12;
    tip.style.setProperty('--s-ch-tip-x', Math.max(4, px) + 'px');
    tip.style.setProperty('--s-ch-tip-y', Math.max(4, py) + 'px');
  }

  function hideTip(ctx) {
    if (ctx.tip) ctx.tip.classList.remove('s-ch-on');
  }

  /* ═══════════════ 3. 차트 (인라인 SVG — 외부 라이브러리 0) ═══════════════ */

  function chartHeight(min, max, ratio) {
    return Math.max(min, Math.min(max, Math.round(window.innerHeight * ratio)));
  }

  /**
   * 0선을 사이에 둔 축 스케일. 위/아래를 각각 nice 눈금으로 잡고 한 축에 합친다.
   *
   * @param {number} maxPos 양(+) 방향 최댓값.
   * @param {number} minNeg 음(−) 방향 최솟값(음수).
   * @param {number} tickCount 위쪽 눈금 개수 목표.
   * @returns {?object} {up, down, span} — 그릴 값이 없으면 null.
   */
  function bipolarScale(maxPos, minNeg, tickCount) {
    var up = niceScale(Math.max(0, maxPos), tickCount || 4);
    var down = niceScale(Math.max(0, -minNeg), 2);
    var span = up.top + down.top;
    return span > 0 ? { up: up, down: down, span: span } : null;
  }

  /** 0선 양쪽 눈금선 + 라벨(만원 단위). 아래쪽 눈금은 음수 라벨로 낸다. */
  function axisMarkup(scale, pad, w, Y) {
    var s = '';
    var draw = function (value) {
      var y = Y(value).toFixed(1);
      s += '<line x1="' + pad.l + '" x2="' + (w - pad.r) + '" y1="' + y + '" y2="' + y +
        '" stroke="' + (value === 0 ? 'var(--s-axis)' : 'var(--s-grid)') + '" stroke-width="1"/>';
      s += '<text class="s-ch-axis-t" x="' + (pad.l - 6) + '" y="' + (Y(value) + 3.5).toFixed(1) +
        '" text-anchor="end">' + esc(fmtTick(toMan(value))) + '</text>';
    };
    scale.up.ticks.forEach(draw);
    scale.down.ticks.forEach(function (tv) { if (tv > 0) draw(-tv); });
    return s;
  }

  /**
   * 3계열 스택 컬럼 + 전기 비교선.
   *
   * 음수 세그먼트는 0선 **아래로** 쌓는다(취소·환급 정산이 음수로 온다 — 절대값으로 접으면
   * 그 자리에서 화면이 거짓말한다). 비교선은 같은 축·같은 단위다(이중 y축 금지).
   *
   * @param {object} ctx 마운트 컨텍스트(툴팁 소유자).
   * @param {Element} host SVG 를 담을 컨테이너.
   * @param {object} cfg {groups:[{label,sub,segs:[{key,label,v,color}]}], line:{color,values},
   *                      height, tickCount, aria, tipTitle(i), tipRows(i)}.
   */
  function stackColumnChart(ctx, host, cfg) {
    var w = host.clientWidth || 640;
    var h = cfg.height;
    var pad = { t: 18, r: 12, b: 30, l: 56 };
    var pw = w - pad.l - pad.r;
    var ph = h - pad.t - pad.b;
    var g = cfg.groups.length;
    if (!g || pw <= 0 || ph <= 0) { clearNode(host); return; }

    var maxPos = 0;
    var minNeg = 0;
    cfg.groups.forEach(function (gr) {
      var up = 0;
      var down = 0;
      gr.segs.forEach(function (seg) { if (seg.v > 0) up += seg.v; else down += seg.v; });
      if (up > maxPos) maxPos = up;
      if (down < minNeg) minNeg = down;
    });
    var lineValues = (cfg.line && cfg.line.values) || [];
    var lineMax = lineValues.length ? Math.max.apply(null, lineValues) : 0;
    var lineMin = lineValues.length ? Math.min.apply(null, lineValues) : 0;
    // 비교선이 축을 끌고 올라갈 수 있는 한도(막대가 주 마크다 — dashboard.js 와 같은 규칙).
    var topV = maxPos > 0 ? Math.max(maxPos, Math.min(lineMax, maxPos * LINE_HEADROOM)) : Math.max(0, lineMax);
    var botV = minNeg < 0 ? Math.max(-minNeg, Math.min(-lineMin, -minNeg * LINE_HEADROOM)) : Math.max(0, -lineMin);
    var scale = bipolarScale(topV, -botV, cfg.tickCount || 4);
    if (!scale) { clearNode(host); return; }

    var band = pw / g;
    var zeroY = pad.t + ph * (scale.up.top / scale.span);
    var Y = function (v) { return zeroY - v / scale.span * ph; };
    var centerX = function (i) { return pad.l + i * band + band / 2; };
    var barW = Math.max(2, Math.min(26, band * 0.62));
    var labelEvery = Math.max(1, Math.ceil(g / 12));

    var s = '<svg width="' + w + '" height="' + h + '" role="img" aria-label="' + esc(cfg.aria || '') + '">';
    s += axisMarkup(scale, pad, w, Y);
    cfg.groups.forEach(function (gr, gi) {
      var x = centerX(gi) - barW / 2;
      var up = 0;
      var down = 0;
      var tops = gr.segs.filter(function (seg) { return seg.v > 0; });
      s += '<g class="s-ch-cgrp">';
      gr.segs.forEach(function (seg) {
        if (!isNum(seg.v) || seg.v === 0) return;
        var isLastPositive = seg.v > 0 && tops.length && tops[tops.length - 1] === seg;
        var y0 = seg.v > 0 ? Y(up + seg.v) : Y(down);
        var y1 = seg.v > 0 ? Y(up) : Y(down + seg.v);
        var height = Math.max(1.5, Math.abs(y1 - y0));
        if (isLastPositive) {
          s += '<path d="' + roundTopRect(x, y0, barW, height, 4) + '" fill="' + seg.color + '"/>';
        } else {
          s += '<rect x="' + x + '" y="' + Math.min(y0, y1).toFixed(1) + '" width="' + barW +
            '" height="' + height.toFixed(1) + '" fill="' + seg.color + '"/>';
        }
        if (seg.v > 0) up += seg.v; else down += seg.v;
      });
      if (up === 0 && down === 0) {
        // 그날 0원은 실재하는 사실이다. 스텁이 없으면 빈 날이 통째로 사라져 리듬이 무너진다.
        s += '<rect x="' + x + '" y="' + (zeroY - 0.75).toFixed(1) + '" width="' + barW +
          '" height="1.5" fill="var(--s-zero-bar)"/>';
      }
      s += '</g>';
      if (gr.label && gi % labelEvery === 0) {
        s += '<text class="s-ch-axis-t" x="' + centerX(gi).toFixed(1) + '" y="' + (h - 9) +
          '" text-anchor="middle">' + esc(gr.label) + '</text>';
      }
    });
    s += linePolyline(cfg.line, lineValues, g, scale, centerX, Y, pad);
    cfg.groups.forEach(function (gr, gi) {
      s += '<rect class="s-ch-ghit" x="' + (pad.l + gi * band).toFixed(1) + '" y="' + pad.t +
        '" width="' + band.toFixed(1) + '" height="' + ph + '" fill="transparent" tabindex="0"/>';
    });
    s += '</svg>';
    host.innerHTML = s;
    bindGroupHits(ctx, host, cfg);
  }

  /** 비교선 폴리라인 + 축을 넘어간 구간의 캐럿 표시(잘라놓고 말 안 하면 거짓말이다). */
  function linePolyline(line, values, groupCount, scale, centerX, Y, pad) {
    if (!line || !values.length) return '';
    var pts = [];
    var clipped = [];
    for (var i = 0; i < values.length && i < groupCount; i++) {
      var v = values[i];
      if (!isNum(v)) continue;
      if (v > scale.up.top) { clipped.push(i); v = scale.up.top; }
      if (v < -scale.down.top) { clipped.push(i); v = -scale.down.top; }
      pts.push(centerX(i).toFixed(1) + ',' + Y(v).toFixed(1));
    }
    var s = '';
    if (pts.length > 1) {
      s += '<polyline points="' + pts.join(' ') + '" fill="none" stroke="' + line.color +
        '" stroke-width="2" stroke-dasharray="6 5" stroke-linejoin="round" stroke-linecap="round"/>';
    }
    clipped.forEach(function (i) {
      var cx = centerX(i);
      s += '<path class="s-ch-clip" d="M' + (cx - 4).toFixed(1) + ',' + (pad.t + 5) +
        ' L' + cx.toFixed(1) + ',' + pad.t + ' L' + (cx + 4).toFixed(1) + ',' + (pad.t + 5) +
        ' Z" fill="' + line.color +
        '"><title>축 위로 넘어간 구간입니다. 값은 툴팁에서 확인하세요.</title></path>';
    });
    return s;
  }

  /** 밴드 단위 hit 레이어에 hover/포커스 툴팁을 건다(bar 는 per-mark 툴팁이 규칙). */
  function bindGroupHits(ctx, host, cfg) {
    var groups = host.querySelectorAll('.s-ch-cgrp');
    host.querySelectorAll('.s-ch-ghit').forEach(function (hit, gi) {
      var group = groups[gi];
      var on = function (x, y) {
        if (group) group.classList.add('s-ch-on');
        showTip(ctx, x, y, cfg.tipTitle(gi), cfg.tipRows(gi));
      };
      var off = function () {
        if (group) group.classList.remove('s-ch-on');
        hideTip(ctx);
      };
      hit.addEventListener('pointermove', function (e) { on(e.clientX, e.clientY); });
      hit.addEventListener('pointerleave', off);
      hit.addEventListener('focus', function () {
        var box = hit.getBoundingClientRect();
        on(box.left + box.width / 2, box.top + 30);
      });
      hit.addEventListener('blur', off);
    });
  }

  /**
   * 워터폴: 부동 막대(누적 시작 → 끝), 단일 축, 감소 단계는 0선 아래 방향으로 그린다.
   *
   * 마지막 항목(`total: true`)만 0 에서 시작하는 합계 막대다. 캡은 부호를 포함해 적는다
   * (`+`/`-`) — "수수료 3.1M" 이 아니라 "-3.1M" 이어야 회계가 읽을 수 있다.
   *
   * @param {object} ctx 마운트 컨텍스트.
   * @param {Element} host SVG 를 담을 컨테이너.
   * @param {object} cfg {items:[{key,label,short,amount,total,note}], height, aria}.
   */
  function waterfallChart(ctx, host, cfg) {
    var w = host.clientWidth || 420;
    var h = cfg.height;
    var pad = { t: 24, r: 10, b: 44, l: 56 };
    var pw = w - pad.l - pad.r;
    var ph = h - pad.t - pad.b;
    var items = cfg.items || [];
    var n = items.length;
    if (!n || pw <= 0 || ph <= 0) { clearNode(host); return; }

    var run = 0;
    var maxV = 0;
    var minV = 0;
    var steps = items.map(function (item) {
      var amount = isNum(item.amount) ? item.amount : 0;
      var from = item.total ? 0 : run;
      var to = item.total ? amount : run + amount;
      if (!item.total) run = to;
      maxV = Math.max(maxV, from, to);
      minV = Math.min(minV, from, to);
      return { from: from, to: to, amount: amount, item: item };
    });
    var scale = bipolarScale(maxV, minV, 4);
    if (!scale) { clearNode(host); return; }

    var band = pw / n;
    var zeroY = pad.t + ph * (scale.up.top / scale.span);
    var Y = function (v) { return zeroY - v / scale.span * ph; };
    var centerX = function (i) { return pad.l + i * band + band / 2; };
    var barW = Math.max(6, Math.min(38, band * 0.56));

    var s = '<svg width="' + w + '" height="' + h + '" role="img" aria-label="' + esc(cfg.aria || '') + '">';
    s += axisMarkup(scale, pad, w, Y);
    steps.forEach(function (step, i) {
      var x = centerX(i) - barW / 2;
      var y0 = Y(Math.max(step.from, step.to));
      var height = Math.max(2, Math.abs(Y(step.from) - Y(step.to)));
      var color = step.item.total ? COLOR_TOTAL : (step.amount < 0 ? COLOR_DOWN : COLOR_UP);
      s += '<g class="s-ch-cgrp"><path d="' + roundTopRect(x, y0, barW, height, 3) +
        '" fill="' + color + '"/>';
      if (step.item.note) s += '<title>' + esc(step.item.note) + '</title>';
      s += '</g>';
      // 연결선: 이 단계의 끝 높이에서 다음 단계의 시작으로. 합계 막대 앞에서는 그리지 않는다.
      if (i < n - 1 && !steps[i + 1].item.total) {
        s += '<line x1="' + (x + barW).toFixed(1) + '" x2="' + (centerX(i + 1) - barW / 2).toFixed(1) +
          '" y1="' + Y(step.to).toFixed(1) + '" y2="' + Y(step.to).toFixed(1) +
          '" stroke="var(--s-axis)" stroke-width="1" stroke-dasharray="3 3"/>';
      }
      var capY = step.amount < 0 && !step.item.total
        ? Y(Math.min(step.from, step.to)) + 13
        : y0 - 7;
      s += '<text class="s-ch-cap-t" x="' + centerX(i).toFixed(1) + '" y="' + capY.toFixed(1) +
        '" text-anchor="middle">' +
        esc((step.item.total ? '' : (step.amount > 0 ? '+' : step.amount < 0 ? '-' : '')) +
          fmtTick(Math.abs(toMan(step.amount)))) + '</text>';
      s += '<text class="s-ch-axis-t" x="' + centerX(i).toFixed(1) + '" y="' + (h - 12) +
        '" text-anchor="middle">' + esc(step.item.short || step.item.label) + '</text>';
    });
    steps.forEach(function (step, i) {
      s += '<rect class="s-ch-ghit" x="' + (pad.l + i * band).toFixed(1) + '" y="' + pad.t +
        '" width="' + band.toFixed(1) + '" height="' + ph + '" fill="transparent" tabindex="0"/>';
    });
    s += '</svg>';
    host.innerHTML = s;
    bindGroupHits(ctx, host, {
      tipTitle: function (i) { return steps[i].item.label; },
      tipRows: function (i) {
        var rows = [{
          val: steps[i].item.total ? moneyText(steps[i].amount) : signedMoney(steps[i].amount),
          neg: steps[i].amount < 0,
          lbl: steps[i].item.total ? '기간 합계' : '누계 ' + moneyText(steps[i].to),
        }];
        if (steps[i].item.note) rows.push({ val: '', lbl: steps[i].item.note });
        return rows;
      },
    });
  }

  /** 스파크라인: 회색 추세 + 마지막 구간 강조. 값이 2개 미만이면 빈 문자열. */
  function sparkSvg(values, accent) {
    var n = (values || []).length;
    if (n < 2) return '';
    var w = 92;
    var h = 30;
    var p = 3;
    var min = Math.min.apply(null, values);
    var max = Math.max.apply(null, values);
    var span = (max - min) || 1;
    var X = function (i) { return p + i * (w - 2 * p) / (n - 1); };
    var Y = function (v) { return h - p - (v - min) / span * (h - 2 * p); };
    var pts = values.map(function (v, i) { return X(i).toFixed(1) + ',' + Y(v).toFixed(1); }).join(' ');
    var lastPts = [n - 2, n - 1].map(function (i) { return X(i).toFixed(1) + ',' + Y(values[i]).toFixed(1); }).join(' ');
    return '<svg width="' + w + '" height="' + h + '" aria-hidden="true">' +
      '<polyline points="' + pts + '" fill="none" stroke="#c3cad4" stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>' +
      '<polyline points="' + lastPts + '" fill="none" stroke="' + accent + '" stroke-width="2" stroke-linecap="round"/>' +
      '<circle cx="' + X(n - 1).toFixed(1) + '" cy="' + Y(values[n - 1]).toFixed(1) + '" r="3" fill="' + accent +
      '" stroke="var(--s-surface)" stroke-width="1.5"/></svg>';
  }

  /**
   * 100% 누적 share bar(수수료 유형 구성). 폭은 CSS 퍼센트라 숨은 pane 에서도 눌리지 않는다.
   *
   * @param {Array} items [{label, amount, share, color}].
   * @returns {Element} 막대 컨테이너.
   */
  function shareBar(items) {
    var wrap = el('div', 's-ch-share');
    wrap.setAttribute('role', 'img');
    wrap.setAttribute('aria-label', items.map(function (it) {
      return it.label + ' ' + fmtRatio(it.share);
    }).join(', '));
    items.forEach(function (item) {
      var seg = el('span', 's-ch-share-seg');
      seg.style.setProperty('--s-ch-seg-pct', (Math.max(0, item.share || 0) * 100).toFixed(2) + '%');
      seg.style.setProperty('--s-ch-seg-color', item.color);
      seg.appendChild(el('span', 's-ch-sr', item.label + ' ' + fmtRatio(item.share)));
      wrap.appendChild(seg);
    });
    return wrap;
  }

  /** 랭킹 가로 막대 한 줄(최댓값 대비 92% 상한 — 값 텍스트와 붙지 않게). */
  function rankRow(item, maxAmount) {
    var row = el('div', 's-ch-rank');
    row.appendChild(el('span', 's-ch-rank-lbl', item.label));
    var track = el('div', 's-ch-rank-track');
    var bar = el('div', 's-ch-rank-bar');
    var ratio = maxAmount > 0 ? Math.abs(item.amount || 0) / maxAmount : 0;
    bar.style.setProperty('--s-ch-bar-pct', (ratio * 92).toFixed(2) + '%');
    bar.style.setProperty('--s-ch-bar-color', item.color);
    track.appendChild(bar);
    row.appendChild(track);
    var value = el('span', 's-ch-rank-val' + (item.amount < 0 ? ' s-ch-neg' : ''), moneyText(item.amount));
    value.appendChild(el('span', 's-ch-rank-share', ' · ' + fmtRatio(item.share)));
    row.appendChild(value);
    return row;
  }

  /** 비율 미터 한 줄. 분모가 없으면 미터 대신 "상한 미설정" 문구를 낸다(0% 로 그리지 않는다). */
  function meterRow(label, value, cap) {
    var wrap = el('div', 's-ch-meter-row');
    var head = el('div', 's-ch-meter-head');
    head.appendChild(el('span', null, label));
    if (!isNum(cap) || cap <= 0) {
      head.appendChild(el('b', 's-ch-meter-none', '상한 미설정'));
      wrap.appendChild(head);
      wrap.appendChild(el('div', 's-ch-note', '네이버가 이 가맹점에 매출 연동 수수료 상한을 주지 않았습니다.'));
      return wrap;
    }
    var pct = Math.max(0, Math.min(100, (value / cap) * 100));
    head.appendChild(el('b', null, moneyText(value) + ' / ' + moneyText(cap) + ' (' + pct.toFixed(1) + '%)'));
    wrap.appendChild(head);
    var meter = el('div', 's-ch-meter');
    meter.setAttribute('role', 'img');
    meter.setAttribute('aria-label', label + ' ' + pct.toFixed(1) + '%');
    var fill = el('div', 's-ch-meter-fill');
    fill.style.setProperty('--s-ch-meter-pct', pct.toFixed(1) + '%');
    meter.appendChild(fill);
    wrap.appendChild(meter);
    return wrap;
  }

  /* ═══════════════ 4. 상태 표시 · 조회 ═══════════════ */

  /**
   * 'loading' / 'error' / 'ready' / 'empty' 를 서로 다른 노드로 말한다. 무음 실패 금지.
   *
   * 실패하면 KPI·차트·원장을 **함께** 감춘다 — 목록만 실패로 바꾸고 위쪽 숫자를 남기면
   * 옛 값이 지금 조건의 값인 양 실패 문구 옆에 계속 서 있게 된다(요약·실무 탭과 같은 규율).
   */
  function showState(ctx, kind, detail) {
    var els = ctx.els;
    setHidden(els.loading, kind !== 'loading');
    setHidden(els.error, kind !== 'error');
    setHidden(els.empty, kind !== 'empty');
    [els.kpi, els.daily, els.waterfall, els.deposit, els.reconcile, els.ledgerSwitch, els.ledger]
      .forEach(function (node) { setHidden(node, kind === 'error'); });
    ctx.root.setAttribute('aria-busy', String(kind === 'loading'));
    if (kind === 'error') {
      var slot = els.errorDetail || ensureSlot(els.error, 'error-detail', 'div', 's-ch-state-detail');
      if (slot && detail) slot.textContent = detail;
    }
  }

  /** 응답에서 사람이 읽는 실패 사유를 뽑는다. */
  function failureReason(res, body) {
    if (res && res.status === 403) {
      return '이 화면을 볼 권한이 없습니다. 회계팀 권한을 관리자에게 요청하세요.';
    }
    if (res && (res.status === 401 || res.redirected)) {
      return '로그인이 풀렸습니다. 페이지를 새로고침한 뒤 다시 시도하세요.';
    }
    if (body && (body.error || body.message)) return String(body.error || body.message);
    return '서버 응답 오류 (HTTP ' + (res ? res.status : '?') + ')';
  }

  function buildUrl(ctx) {
    var state = ctx.state;
    var base = ctx.root.getAttribute('data-settlement-ch-api') || API_FALLBACK;
    var params = [
      'channel=' + encodeURIComponent(state.channel),
      'basis=' + encodeURIComponent(state.basis),
      'from=' + encodeURIComponent(state.from),
      'to=' + encodeURIComponent(state.to),
      'granularity=' + encodeURIComponent(state.granularity),
      'ledger=' + encodeURIComponent(currentLedgerParam(ctx)),
      'page=' + encodeURIComponent(state.page),
      'per_page=' + encodeURIComponent(PER_PAGE),
    ];
    if (state.type) params.push('type=' + encodeURIComponent(state.type));
    if (state.q) params.push('q=' + encodeURIComponent(state.q));
    return base + (base.indexOf('?') === -1 ? '?' : '&') + params.join('&');
  }

  /** 스위처 뷰 → API `ledger` 값. 서버 원장이 없는 뷰(예외)는 null. */
  function ledgerParam(view) {
    for (var i = 0; i < LEDGER_VIEWS.length; i++) {
      if (LEDGER_VIEWS[i].view === view) return LEDGER_VIEWS[i].param;
    }
    return 'case';
  }

  /**
   * 지금 조회에 실을 `ledger` 값. **예외 뷰는 서버 원장이 없으므로 마지막으로 본 원장을 유지한다** —
   * 여기서 무조건 'case' 로 되돌리면 "수수료 → 예외 → 수수료" 왕복이 조용히 건별 원장을
   * 불러와 수수료 화면에 건별 행이 실린다.
   */
  function currentLedgerParam(ctx) {
    var view = ctx.state.view === 'exceptions' ? (ctx.state.lastLedger || 'case') : ctx.state.view;
    return ledgerParam(view) || 'case';
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

  /**
   * 공통 POST(JSON). CSRF 헤더를 직접 적지 않는다 — `csrf_bootstrap.html` 이 same-origin
   * mutation 에 `X-CSRF-Token` 을 자동으로 싣는다(WRITE-GUARD-01 단일 choke point).
   */
  async function postJson(url, payload) {
    var res = await fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', Accept: 'application/json' },
      body: JSON.stringify(payload || {}),
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

  async function load(ctx) {
    var state = ctx.state;
    var seq = ++state.seq;
    showState(ctx, 'loading');
    try {
      var data = await getJson(buildUrl(ctx));
      if (seq !== state.seq) return;   // 늦게 온 응답이 최신 화면을 덮지 않게 한다
      adoptServerState(ctx, data);
      // 한 번도 동기화되지 않았으면 숫자가 0 이 아니라 **아직 모르는 상태**다. 파셜이 가진
      // 빈 상태 노드를 그때만 켠다(각 블록도 같은 사실을 자기 문구로 반복한다).
      showState(ctx, data.sync && data.sync.never ? 'empty' : 'ready');
      renderAll(ctx);
    } catch (err) {
      if (seq !== state.seq) return;
      showState(ctx, 'error', err && err.handled
        ? err.message
        : '정산 서버에 연결하지 못했습니다. 네트워크를 확인한 뒤 다시 시도하세요.');
    }
  }

  /** 서버가 필터·페이지의 최종 권위다(범위를 벗어난 page 는 서버가 접는다). */
  function adoptServerState(ctx, data) {
    var state = ctx.state;
    state.data = data;
    // 셀렉트는 **표에 실제로 걸린 축**을 보여야 한다. 최상위 `basis` 는 요청 echo 라 없는 축을
    // 골랐을 때 되돌림 전 값이 온다 — 그걸 채택하면 셀렉트가 표와 다른 말을 한다(C1).
    var axisBasis = data.ledger && data.ledger.axis && data.ledger.axis.basis;
    if (axisBasis) state.basis = axisBasis;
    else if (data.basis) state.basis = data.basis;
    if (data.granularity) state.granularity = data.granularity;
    if (data.range && data.range.from) state.from = data.range.from;
    if (data.range && data.range.to) state.to = data.range.to;
    var pagination = (data.ledger && data.ledger.pagination) || null;
    if (pagination && isNum(pagination.page)) state.page = pagination.page;
    state.rev = data.sync ? data.sync.rev : null;
    rememberTypeOptions(ctx, data);
  }

  /**
   * 유형 필터 후보를 누적한다. 서버 enum 목록 API 가 없어 **현재 원장 행에서 관측한 값**을
   * 모은다 — 필터를 걸면 후보가 줄어드는 문제를 막으려고 같은 원장 안에서는 지우지 않는다
   * (원장 종류가 바뀌면 초기화). 한글 라벨은 서버가 준 `<field>_label` 만 쓴다.
   */
  function rememberTypeOptions(ctx, data) {
    var kind = (data.ledger && data.ledger.kind) || 'case';
    if (ctx.state.typeKind !== kind) {
      ctx.state.typeKind = kind;
      ctx.state.typeOptions = {};
    }
    var fields = TYPE_FIELDS[kind] || TYPE_FIELDS.case;
    ((data.ledger && data.ledger.rows) || []).forEach(function (row) {
      for (var i = 0; i < fields.length; i++) {
        var code = row[fields[i]];
        if (code) {
          ctx.state.typeOptions[code] = row[fields[i] + '_label'] || code;
          return;
        }
      }
    });
  }

  /* ═══════════════ 5. 렌더 — S0 동기화 헤더 ═══════════════ */

  /**
   * 파셜이 소유한 컨테이너를 지우지 않고 JS 전용 슬롯만 만들어 쓴다(동기화 버튼·안내 문구를
   * 날리지 않는다). `atEnd` 면 뒤에 붙인다.
   */
  function ensureSlot(parent, key, tag, cls, atEnd) {
    if (!parent) return null;
    var found = parent.querySelector('[data-settlement-ch-slot="' + key + '"]');
    if (found) return found;
    var node = el(tag || 'div', cls || null);
    node.setAttribute('data-settlement-ch-slot', key);
    if (atEnd) parent.appendChild(node);
    else parent.insertBefore(node, parent.firstChild);
    return node;
  }

  /**
   * S0 — 동기화 헤더. "아직 한 번도"(never)와 "오래됐다"(stale)와 "정상"을 **다른 문구**로
   * 구분한다(계약 D-10: 결측·지연을 0 으로 그리지 않는다).
   */
  function renderSync(ctx) {
    var host = ctx.els.sync;
    if (!host && !ctx.els.syncState) return;
    // 파셜이 `[data-settlement-ch-sync-state]` 를 준다. 그 노드가 정본이고, 없을 때만
    // 슬롯을 만들어 쓴다 — 컨테이너를 통째로 지우면 [지금 동기화] 버튼이 날아간다.
    var slot = ctx.els.syncState || ensureSlot(host, 'sync-text', 'div', 's-ch-sync-text');
    if (!slot) return;
    clearNode(slot);
    if (!ctx.state.data) {
      // 아직 한 번도 못 읽었다. 여기서 "최종 동기화 시각 미상"을 내면 **없는 사실**을 말하게 된다.
      if (ctx.state.notice) {
        slot.appendChild(el('div', 's-ch-notice' + (ctx.state.notice.error ? ' s-ch-notice--error' : ''),
          ctx.state.notice.text));
      }
      return;
    }
    var sync = ctx.state.data.sync || {};

    var head = el('div', 's-ch-sync-head');
    var mode = sync.never ? 'never' : (sync.stale ? 'stale' : 'ok');
    head.appendChild(el('i', 's-ch-dot s-ch-dot--' + mode));
    if (mode === 'never') {
      head.appendChild(el('b', null, '아직 한 번도 동기화되지 않았습니다'));
      head.appendChild(el('span', 's-ch-sync-sub', '[지금 동기화]를 눌러 첫 적재를 시작하세요. 아래 숫자는 모두 비어 있는 상태입니다.'));
    } else {
      var stamp = fmtStamp(sync.last_ok_at || sync.last_run_at);
      var ago = agoText(sync.last_ok_at || sync.last_run_at);
      head.appendChild(el('b', null, '최종 동기화 ' + (stamp || '시각 미상') + (ago ? ' (' + ago + ')' : '')));
      head.appendChild(el('span', 's-ch-sync-sub', mode === 'stale'
        ? '36시간 넘게 갱신되지 않았습니다 — 아래 숫자는 그 시점의 값입니다.'
        : (sync.status ? '상태 ' + sync.status : '정상')));
    }
    slot.appendChild(head);

    var lines = el('div', 's-ch-sync-lines');
    lines.appendChild(el('span', null, '적재 구간 ' +
      (sync.coverage_from || '—') + ' ~ ' + (sync.coverage_to || '—') +
      (isNum(sync.rolling_days) ? ' · 롤링 재조회 ' + sync.rolling_days + '일' : '')));
    if (sync.final_before) lines.appendChild(el('span', null, '확정 구간 ~' + sync.final_before));
    lines.appendChild(el('span', null, sync.vat_available_to
      ? '부가세 자료는 ' + sync.vat_available_to + '까지 제공(당월분은 익월 마감 후)'
      : '부가세 자료 제공 구간 미상'));
    slot.appendChild(lines);

    var notice = ctx.state.notice;
    if (notice) {
      slot.appendChild(el('div', 's-ch-notice' + (notice.error ? ' s-ch-notice--error' : ''), notice.text));
    }
  }

  /* ── CSV 내보내기 드롭다운(T14) ────────────────────────────────────────
     S0 동기화 헤더 안, [지금 동기화] 뒤에 산다. 항목은 **링크**다 — `blob:` 다운로드는
     인앱 웹뷰에서 막히기 때문에(프로젝트 함정) 서버 파일 엔드포인트로 그냥 이동한다.
     조건(채널·기간·기준일·검색어)은 지금 화면 그대로 싣는다. 다만 **유형 필터는 그 필터를
     고른 원장과 같은 종류의 파일에만** 싣는다 — 수수료 원장에서 고른 유형 코드를 건별
     정산 파일에 실으면 조건이 아무 행에도 안 맞아 "0행짜리 정상 파일"이 내려간다. */

  /** 서버 원장 종류 → CSV 종류. 유형 필터를 실을 수 있는 짝인지 판정하는 데만 쓴다. */
  function exportKindOfLedger(kind) {
    return kind === 'commission' ? 'commission' : (kind === 'vat_case' ? 'vat_case' : 'settle_case');
  }

  /** 지금 화면에서 좁힌 조건(유형·검색)을 이 표에 실을 수 있는 짝인가.
      `type` 과 `q` 는 **같은 원장에서 좁힌 한 쌍**이라 판정도 하나여야 한다. 원장이 바뀌면
      `switchLedger` 가 둘 다 비우므로, 지금 실린 원장 하나만 보면 충분하다. */
  function exportCarriesFilters(ctx, spec) {
    return !!(spec.filters &&
      exportKindOfLedger(currentLedgerParam(ctx)) === (spec.typeOf || spec.kind));
  }

  /** 지금 화면 조건을 실은 내려받기 URL 하나. */
  function exportUrl(ctx, spec) {
    var host = ctx.els.exportHost;
    var base = (host && host.getAttribute('data-settlement-ch-export-api')) || EXPORT_API_FALLBACK;
    var params = [
      'kind=' + encodeURIComponent(spec.kind),
      'channel=' + encodeURIComponent(ctx.state.channel),
      'from=' + encodeURIComponent(ctx.state.from),
      'to=' + encodeURIComponent(ctx.state.to),
      'basis=' + encodeURIComponent(ctx.state.basis),
    ];
    var carries = exportCarriesFilters(ctx, spec);
    if (carries && ctx.state.q) params.push('q=' + encodeURIComponent(ctx.state.q));
    if (carries && ctx.state.type) params.push('type=' + encodeURIComponent(ctx.state.type));
    return base + (base.indexOf('?') === -1 ? '?' : '&') + params.join('&');
  }

  /** 메뉴를 지금 조건으로 다시 그린다(열 때마다 — 조건은 그 사이에 바뀌어 있다). */
  function renderExportMenu(ctx) {
    var menu = ctx.els.exportMenu;
    if (!menu) return;
    clearNode(menu);
    EXPORT_KINDS.forEach(function (spec) {
      var item = el('a', 's-ch-export-item');
      item.href = exportUrl(ctx, spec);
      item.setAttribute('role', 'menuitem');
      item.setAttribute('data-settlement-ch-export-kind', spec.kind);
      item.appendChild(document.createTextNode(spec.label));
      item.appendChild(el('span', 's-ch-export-sub', spec.sub));
      // 조건을 받는 표인데 원장이 달라 못 싣는 경우에만 말한다 — 일자 단위 표(filters:false)는
      // 애초에 검색어를 받지 않으니 '원장이 다르다'는 사유가 거짓이 된다(F10 리뷰 MINOR-1).
      if (ctx.state.q && spec.filters && !exportCarriesFilters(ctx, spec)) {
        item.appendChild(el('span', 's-ch-export-sub',
          '지금 검색어는 이 표에 안 실립니다(원장이 다릅니다)'));
      }
      menu.appendChild(item);
    });
    // 상시 안내(자동 닫힘 없는 일반 텍스트). 파일이 화면보다 많은 열을 담는다는 사실과
    // 여는 법을 늘 말한다 — 16자리 주문번호를 표 계산 프로그램이 지수표기로 여는 자리다.
    menu.appendChild(el('p', 's-ch-export-note',
      '화면보다 많은 원본 필드가 들어 있습니다 · 엑셀은 [데이터 → 텍스트/CSV 가져오기]로 ' +
      "열고 주문번호 열을 '텍스트'로 지정하세요"));
  }

  /** 메뉴를 열거나 닫는다. 상태는 버튼의 `aria-expanded` 하나로만 말한다. */
  function toggleExport(ctx, open) {
    var host = ctx.els.exportHost;
    var btn = ctx.els.exportBtn;
    if (!host || !btn) return;
    if (open && !ctx.els.exportMenu) {
      var menu = el('div', 's-ch-export-menu');
      menu.setAttribute('data-settlement-ch-export-menu', '');
      menu.setAttribute('role', 'menu');
      host.appendChild(menu);
      ctx.els.exportMenu = menu;
    }
    if (open) renderExportMenu(ctx);
    btn.setAttribute('aria-expanded', String(!!open));
    setHidden(ctx.els.exportMenu, !open);
  }

  /** 지금 열려 있는가. 두 번째 상태 변수를 만들지 않으려고 DOM 을 정본으로 읽는다. */
  function exportOpen(ctx) {
    return !!(ctx.els.exportBtn && ctx.els.exportBtn.getAttribute('aria-expanded') === 'true');
  }

  /* ═══════════════ 6. 렌더 — S-bar · S1 KPI ═══════════════ */

  /** 필터바의 컨트롤 값을 서버가 확정한 상태로 되맞춘다(값의 권위는 서버다). */
  function syncControls(ctx) {
    var els = ctx.els;
    if (els.basis && els.basis.value !== ctx.state.basis) els.basis.value = ctx.state.basis;
    if (els.basis) {
      // 원장마다 있는 축이 다르다 — 없는 축은 잠근다. 이미 골라 둔 값이 잠기면 표 머리가 되돌림을 말한다.
      var allowed = LEDGER_BASES[currentLedgerParam(ctx)] || LEDGER_BASES.case;
      Array.prototype.forEach.call(els.basis.options, function (opt) {
        opt.disabled = allowed.indexOf(opt.value) < 0;
      });
    }
    if (els.granularity && els.granularity.value !== ctx.state.granularity) {
      els.granularity.value = ctx.state.granularity;
    }
    if (els.from) els.from.value = ctx.state.from;
    if (els.to) els.to.value = ctx.state.to;
    var data = ctx.state.data;
    if (!data) return;
    // 축 라벨은 파셜이 서버 렌더로 이미 갖고 있다(계약 테스트가 그 문구를 잠근다). 여기에
    // basis_label 을 찍지 않는다: 위쪽 KPI·차트·워터폴은 기준일 셀렉트와 무관하게 늘 정산 예정일이라,
    // 찍으면 "완료일 기준 · 매출 인식(완료일)과 다릅니다" 같은 자기모순이 난다(2026-09-03 실측).
    // 원장의 축은 원장 머리(renderLedgerAxisNote)가 따로 말한다. 조회 구간만 앞에 붙인다.
    var note = els.axisNote || ensureSlot(els.bar, 'basis-note', 'p', 's-ch-axisnote', true);
    if (note) {
      note.textContent = ctx.state.from + ' ~ ' + ctx.state.to + ' · 정산 예정일 기준 · 매출 인식(완료일)과 다릅니다';
    }
  }

  function appendKpi(wrap, spec) {
    var tile = el('div', 's-ch-kpi-tile');
    tile.setAttribute('data-settlement-ch-kpi', spec.key);
    tile.style.setProperty('--s-ch-fam', spec.color);
    tile.appendChild(el('div', 's-ch-kpi-label', spec.label));
    var mid = el('div', 's-ch-kpi-mid');
    var value = el('span', 's-ch-kpi-value' + (spec.negative ? ' s-ch-neg' : ''), spec.value);
    if (spec.unit) value.appendChild(el('i', null, spec.unit));
    mid.appendChild(value);
    var spark = spec.spark && sparkSvg(spec.spark, spec.color);
    if (spark) {
      var sparkWrap = el('span', 's-ch-kpi-spark');
      sparkWrap.innerHTML = spark;    // 내부에서 만든 SVG 문자열만 들어간다(사용자 입력 없음)
      mid.appendChild(sparkWrap);
    }
    tile.appendChild(mid);
    var delta = el('div', 's-ch-kpi-delta ' + (spec.delta ? spec.delta.cls : 's-ch-flat'));
    delta.textContent = spec.delta ? spec.delta.arrow + ' ' + spec.delta.text : spec.noDelta;
    if (spec.delta) delta.appendChild(el('span', null, ' 전기 대비'));
    tile.appendChild(delta);
    tile.appendChild(el('div', 's-ch-kpi-sub', spec.sub));
    if (spec.toggle) bindKpiToggle(tile, spec.toggle);
    wrap.appendChild(tile);
    return tile;
  }

  /**
   * 타일을 펼침 버튼으로 만든다(v1.2 F2 — "보류·한도" 상세). 리스너는 **타일 자신**에만 붙는다 —
   * document 전역 리스너는 3개 그대로다(프래그먼트 스왑마다 재실행되는 파일이라 누적된다).
   */
  function bindKpiToggle(tile, toggle) {
    tile.setAttribute('role', 'button');
    tile.setAttribute('tabindex', '0');
    tile.setAttribute('aria-expanded', toggle.open ? 'true' : 'false');
    tile.setAttribute('aria-controls', toggle.controls);
    tile.classList.add('s-ch-kpi-tile--toggle');
    var flip = function () { toggle.onToggle(tile); };
    tile.addEventListener('click', flip);
    tile.addEventListener('keydown', function (e) {
      if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); flip(); }
    });
  }

  /** S1 — KPI 6타일. "정산 예정"과 "정산 완료"는 **절대 합산하지 않는다**(계약 D-6). */
  function renderKpis(ctx) {
    var host = ctx.els.kpi;
    if (!host) return;
    clearNode(host);
    // 그리드는 앵커가 아니라 **안쪽 한 겹**이 잡는다 — 앵커가 컨테이너 쿼리 기준이 되려면
    // 자기 폭으로 자기를 질의할 수 없기 때문이다(컨테이너는 자신을 못 본다).
    var wrap = el('div', 's-ch-kpis');
    host.appendChild(wrap);
    var data = ctx.state.data;
    var kpi = data.kpi || {};
    var prev = kpi.prev || {};
    var daily = data.daily || [];
    var paySettleTotal = sumBy(daily, function (d) { return d.pay_settle; });

    appendKpi(wrap, {
      key: 'settled', label: '정산 완료액', color: STACK_SERIES[1].color,
      value: moneyText(kpi.settled_amount), negative: kpi.settled_amount < 0,
      delta: deltaOf(kpi.settled_amount, prev.settled_amount), noDelta: '전기 비교 기준 없음',
      sub: '통장 입금 완료분 · 정산 완료일 기준',
      spark: daily.map(function (d) { return d.completed ? (d.settle_amount || 0) : 0; }),
    });
    appendKpi(wrap, {
      key: 'expected', label: '정산 예정액', color: STACK_SERIES[2].color,
      value: moneyText(kpi.expected_amount), negative: kpi.expected_amount < 0,
      delta: deltaOf(kpi.expected_amount, prev.expected_amount), noDelta: '전기 비교 기준 없음',
      sub: '아직 은행 미입금 · 계좌 ' + moneyText(kpi.expected_account_amount) +
        ' · 충전금 상계 ' + moneyText(kpi.expected_charge_amount),
      spark: daily.map(function (d) { return d.completed ? 0 : (d.settle_amount || 0); }),
    });
    appendKpi(wrap, {
      key: 'commission', label: '수수료 합계', color: COLOR_DOWN,
      value: moneyText(kpi.commission_total), negative: kpi.commission_total < 0,
      delta: deltaOf(Math.abs(kpi.commission_total), Math.abs(prev.commission_total)),
      noDelta: '전기 비교 기준 없음',
      sub: '결제·판매·채널 수수료 합 · 네이버가 차감한 금액',
      spark: daily.map(function (d) { return d.commission || 0; }),
    });
    appendKpi(wrap, {
      key: 'commission_rate', label: '실효 수수료율', color: COLOR_DOWN,
      value: fmtRatio(kpi.commission_rate, 2), delta: null,
      noDelta: kpi.commission_rate == null ? '분모(결제 정산액)가 0 입니다' : '비율 — 기간 비교 없음',
      sub: '분자 ' + moneyText(kpi.commission_total) + ' / 분모 ' + moneyText(paySettleTotal) + '(결제 정산액)',
    });
    var holdback = data.holdback || { rows: [], count: 0, total: {} };
    appendKpi(wrap, {
      key: 'holdback', label: '보류·한도', color: CATEGORICAL[4],
      value: moneyText(kpi.holdback_amount), negative: kpi.holdback_amount < 0,
      delta: deltaOf(kpi.holdback_amount, prev.holdback_amount), noDelta: '전기 비교 기준 없음',
      sub: '지급 보류 + 정산 한도 초과분 · ' + (holdback.count
        ? '일자별 ' + fmtCount(holdback.count) + '행 — 눌러서 펼치기'
        : '이 기간에 보류·한도 행이 없습니다'),
      spark: daily.map(function (d) { return d.holdback || 0; }),
      toggle: {
        open: !!ctx.state.holdbackOpen,
        controls: HOLDBACK_DETAIL_ID,
        onToggle: function (tile) {
          ctx.state.holdbackOpen = !ctx.state.holdbackOpen;
          tile.setAttribute('aria-expanded', ctx.state.holdbackOpen ? 'true' : 'false');
          setHidden(host.querySelector('[data-settlement-ch-holdback-detail]'), !ctx.state.holdbackOpen);
        },
      },
    });
    appendKpi(wrap, {
      key: 'match', label: '주문 매칭률', color: CATEGORICAL[2],
      value: fmtRatio(kpi.match_rate), delta: null,
      noDelta: kpi.match_rate == null ? '이 기간에 상품주문 행이 없습니다' : '비율 — 기간 비교 없음',
      sub: 'FOMS 미연결 ' + fmtCount(kpi.unmatched_count) + '건(워크벤치 대기 ' +
        fmtCount(kpi.unmatched_pending_count) + ' · 수집 전 ' + fmtCount(kpi.unmatched_unlinked_count) +
        ') · 정산 건수 ' + fmtCount(kpi.case_count) + '건',
    });
    renderHoldbackDetail(ctx, host, !!ctx.state.holdbackOpen);
  }

  /**
   * S1 보조 — "보류·한도" 타일이 펼치는 일자별 상세(v1.2 F2). 값은 서버 `data.holdback` 그대로
   * (payHoldbackAmount·settlementLimitAmount 를 더하기만 한다). 6열 그리드 **바깥**, KPI 앵커 안에
   * 둔다 — 컨테이너 쿼리가 폭을 재는 앵커는 그대로고 그리드는 타일만 담는다.
   */
  function renderHoldbackDetail(ctx, host, open) {
    var block = (ctx.state.data && ctx.state.data.holdback) || { rows: [], count: 0, total: {} };
    var panel = el('div', 's-ch-card s-ch-kpi-detail');
    panel.id = HOLDBACK_DETAIL_ID;
    panel.setAttribute('data-settlement-ch-holdback-detail', '');
    setHidden(panel, !open);
    panel.appendChild(cardHead('지급 보류·한도 일자별 상세',
      '일별 정산 행 기준 · 부호는 네이버 원본 그대로 — 같은 금액이 음수 뒤 양수로 다시 오면 보류와 해제의 짝입니다'));
    if (!block.rows.length) {
      panel.appendChild(emptyBox(ctx, '이 기간에 지급 보류·한도 보류 행이 없습니다.'));
      host.appendChild(panel);
      return;
    }
    var columns = [
      { key: 'date', label: '정산 예정일', type: 'text' },
      { key: 'settle_method_label', label: '입금 방식', type: 'text' },
      { key: 'pay_holdback', label: '지급 보류', type: 'money' },
      { key: 'settlement_limit', label: '정산 한도', type: 'money' },
      { key: 'amount', label: '합계', type: 'money' },
    ];
    var built = tableFor(columns, ['정산 완료']);
    block.rows.forEach(function (row) {
      var tr = el('tr');
      columns.forEach(function (col) { tr.appendChild(valueCell(row, col)); });
      tr.appendChild(el('td', null, row.completed ? '완료' : '미완료'));
      addRow(built, tr);
    });
    var total = block.total || {};
    var tfoot = el('tfoot');
    var foot = el('tr');
    foot.appendChild(el('th', null, '합계'));
    foot.appendChild(el('th', null, fmtCount(block.count) + '행'));
    ['pay_holdback', 'settlement_limit', 'amount'].forEach(function (key) {
      foot.appendChild(el('th', 's-ch-num' + (total[key] < 0 ? ' s-ch-neg' : ''), moneyText(total[key])));
    });
    foot.appendChild(el('th', null, ''));
    tfoot.appendChild(foot);
    built.table.appendChild(tfoot);
    panel.appendChild(built.wrap);
    host.appendChild(panel);
  }

  /* ═══════════════ 7. 렌더 — S2 일별 · S3 워터폴 ═══════════════ */

  function renderLegend(host, entries) {
    var legend = el('div', 's-ch-legend');
    entries.forEach(function (entry) {
      var item = el('span', 's-ch-lg');
      var key = el('i', entry.line ? 's-ch-lg-line' : 's-ch-lg-rect');
      key.style.setProperty('--s-ch-key-color', entry.color);
      item.appendChild(key);
      item.appendChild(document.createTextNode(entry.label));
      legend.appendChild(item);
    });
    host.appendChild(legend);
  }

  /** S2 — 일별 정산 흐름(3계열 스택 + 전기 비교선). */
  function renderDaily(ctx) {
    var host = ctx.els.daily;
    if (!host) return;
    clearNode(host);
    var data = ctx.state.data;
    var daily = data.daily || [];
    var prevDaily = data.daily_prev || [];
    // 일별 버킷은 늘 정산 예정일이다(서버 _build_daily) — 셀렉트 라벨을 여기 찍으면 차트가 거짓말을 한다.
    host.appendChild(cardHead('일별 정산 흐름', '정산 예정일 기준 · 취소·환급은 0선 아래로 그립니다'));
    renderLegend(host, STACK_SERIES.map(function (series) {
      return { label: series.label, color: series.color };
    }).concat([{ label: '전기 비교(정산 금액)', color: COLOR_PREV, line: true }]));
    if (!daily.length) {
      host.appendChild(emptyBox(ctx, '이 기간에 적재된 정산 일자가 없습니다.'));
      return;
    }
    // 전 계열이 0 이면 축을 세울 수 없어 SVG 가 빈 그림이 된다. 빈 그림은 "데이터가 없다"로
    // 읽히므로 **0 원이라는 사실**을 글자로 말한다(계약 D-10).
    var moved = daily.reduce(function (acc, row) {
      return acc + STACK_SERIES.reduce(function (sum, series) { return sum + Math.abs(row[series.key] || 0); }, 0);
    }, 0);
    if (moved === 0) {
      host.appendChild(emptyBox(ctx, '이 기간에 기록된 정산 금액이 모두 0 원입니다 (' + fmtCount(daily.length) + '일).'));
      return;
    }
    var chart = el('div', 's-ch-chart');
    host.appendChild(chart);
    stackColumnChart(ctx, chart, {
      height: chartHeight(280, 400, 0.32),
      aria: '일별 정산 흐름 스택 컬럼 차트',
      groups: daily.map(function (row) {
        return {
          label: bucketLabel(row.date, data.granularity),
          segs: STACK_SERIES.map(function (series) {
            return { key: series.key, label: series.label, v: row[series.key] || 0, color: series.color };
          }),
        };
      }),
      line: { color: COLOR_PREV, values: prevDaily.map(function (row) { return row.settle_amount || 0; }) },
      tipTitle: function (i) { return String(daily[i].date) + (daily[i].completed ? ' (정산 완료)' : ' (정산 예정)'); },
      tipRows: function (i) {
        var row = daily[i];
        var rows = STACK_SERIES.map(function (series) {
          return { color: series.color, val: moneyText(row[series.key]), lbl: series.label, neg: row[series.key] < 0 };
        });
        rows.push({ val: moneyText(row.settle_amount), lbl: '정산 금액', neg: row.settle_amount < 0 });
        rows.push({ val: moneyText(row.commission), lbl: '수수료', neg: row.commission < 0 });
        var prevRow = prevDaily[i];
        if (prevRow) rows.push({ color: COLOR_PREV, val: moneyText(prevRow.settle_amount), lbl: '전기 ' + prevRow.date });
        return rows;
      },
    });
  }

  /** S3 — 정산 구성 워터폴. 순서·부호는 서버 `waterfall[]` 을 그대로 따른다. */
  function renderWaterfall(ctx) {
    var host = ctx.els.waterfall;
    if (!host) return;
    clearNode(host);
    var steps = ctx.state.data.waterfall || [];
    host.appendChild(cardHead('정산 구성 (기간 합계)', '결제 정산액에서 차감·가산을 거쳐 정산 금액까지'));
    if (!steps.length) {
      host.appendChild(emptyBox(ctx, '이 기간에 정산 구성 데이터가 없습니다.'));
      return;
    }
    var chart = el('div', 's-ch-chart');
    host.appendChild(chart);
    var last = steps.length - 1;
    waterfallChart(ctx, chart, {
      height: chartHeight(280, 400, 0.32),
      aria: '정산 구성 워터폴 차트',
      items: steps.map(function (step, i) {
        return {
          key: step.key,
          label: step.label,
          short: shortStepLabel(step.label),
          amount: step.amount,
          total: i === last,
          note: step.key === 'benefit'
            ? '혜택 정산의 항목별 상세는 API 가 제공하지 않습니다(스마트스토어센터 엑셀에서만 확인).'
            : null,
        };
      }),
    });
    var list = el('div', 's-ch-steps');
    steps.forEach(function (step, i) {
      var row = el('div', 's-ch-step' + (i === last ? ' s-ch-step--total' : ''));
      row.appendChild(el('span', 's-ch-step-lbl', step.label));
      row.appendChild(el('span', 's-ch-step-val' + (step.amount < 0 ? ' s-ch-neg' : ''),
        i === last ? moneyText(step.amount) : signedMoney(step.amount)));
      list.appendChild(row);
    });
    host.appendChild(list);
    host.appendChild(el('div', 's-ch-note',
      '혜택 정산의 항목별 상세는 네이버 API 가 제공하지 않습니다(스마트스토어센터 엑셀에서만 확인).'));
  }

  /** 축 라벨용 짧은 이름. 서버 라벨의 공백·중점을 걷어내 6자 안쪽으로 줄인다. */
  function shortStepLabel(label) {
    var text = String(label || '').replace(/\s+/g, '');
    return text.length > 6 ? text.slice(0, 6) : text;
  }

  function cardHead(title, sub) {
    var head = el('div', 's-ch-card-head');
    head.appendChild(el('span', 's-ch-card-title', title));
    if (sub) head.appendChild(el('span', 's-ch-card-sub', sub));
    return head;
  }

  /**
   * 빈 상태 상자. **"0건"과 "아직 동기화 안 됨"을 다른 문구로 낸다**(계약 D-10) —
   * 동기화 전이면 0 이 사실이 아니라 "아직 모른다"이다.
   */
  function emptyBox(ctx, zeroText) {
    var sync = (ctx.state.data && ctx.state.data.sync) || {};
    var box = el('div', 's-ch-empty');
    if (sync.never) {
      box.appendChild(el('b', null, '아직 동기화되지 않았습니다'));
      box.appendChild(el('div', null, '[지금 동기화]를 누르면 네이버에서 정산 자료를 받아옵니다. 0 이라는 뜻이 아닙니다.'));
    } else {
      box.appendChild(el('b', null, zeroText));
      if (sync.coverage_from && sync.coverage_to) {
        box.appendChild(el('div', null, '적재 구간은 ' + sync.coverage_from + ' ~ ' + sync.coverage_to + ' 입니다.'));
      }
    }
    return box;
  }

  /* ═══════════════ 8. 렌더 — S4 입금 채널 · S9 대사 ═══════════════ */

  /**
   * S4 — 입금 채널. `ACCOUNT`(통장 입금)와 `CHARGE_AMT`(충전금 상계)를 **분리해서** 낸다.
   * 충전금은 통장에 기록되지 않는 상계라 은행 대사 대상이 아니다(계약 D-7).
   */
  function renderDeposit(ctx) {
    var host = ctx.els.deposit;
    if (!host) return;
    clearNode(host);
    var rows = ctx.state.data.deposit_channels || [];
    host.appendChild(cardHead('입금 채널', '계좌 입금과 충전금 상계를 나눠 봅니다'));
    if (!rows.length) {
      host.appendChild(emptyBox(ctx, '이 기간에 입금 채널 정보가 없습니다.'));
      return;
    }
    var list = el('div', 's-ch-deps');
    rows.forEach(function (row) {
      var isCharge = String(row.method || '').toUpperCase() === 'CHARGE_AMT';
      var item = el('div', 's-ch-dep' + (isCharge ? ' s-ch-dep--charge' : ''));
      var head = el('div', 's-ch-dep-head');
      head.appendChild(el('b', null, row.method_label || row.method || '방식 미상'));
      head.appendChild(el('span', 's-ch-badge ' + (isCharge ? 's-ch-badge--charge' : 's-ch-badge--account'),
        isCharge ? '통장 미기록' : (row.method ? '통장 입금' : '입금 방식 미정')));
      item.appendChild(head);
      var meta = [];
      if (row.bank_label || row.bank_type) meta.push(row.bank_label || row.bank_type);
      if (row.account_no_masked) meta.push(row.account_no_masked);
      if (row.depositor_name) meta.push(row.depositor_name);
      item.appendChild(el('div', 's-ch-dep-meta', meta.length ? meta.join(' · ') : '계좌 정보 없음'));
      var amount = el('div', 's-ch-dep-amt' + (row.amount < 0 ? ' s-ch-neg' : ''), moneyText(row.amount));
      amount.appendChild(el('span', 's-ch-dep-cnt', ' (' + fmtCount(row.count) + '건)'));
      item.appendChild(amount);
      list.appendChild(item);
    });
    host.appendChild(list);
    host.appendChild(el('div', 's-ch-note',
      '이 금액은 실제 계좌 입금과 자동으로 대사되지 않습니다. 충전금 상계는 통장에 기록되지 않는 차감입니다.'));
  }

  /** S9 — 대사 배너. 일별 합계 vs 건별 합계의 차이를 숨기지 않는다. */
  function renderReconcile(ctx) {
    var host = ctx.els.reconcile;
    if (!host) return;
    clearNode(host);
    var recon = ctx.state.data.reconcile || {};
    var diff = isNum(recon.diff) ? recon.diff : null;
    var sync = ctx.state.data.sync || {};
    // 동기화 전이거나 두 합계가 모두 0 이면 "일치"가 아니라 "대사 대상 없음"이다 —
    // 0 = 0 을 초록 배지로 보여 주면 빈 적재를 온전한 적재로 오독한다.
    var nothing = !!sync.never || (!recon.daily_total && !recon.case_total);
    if (nothing) {
      var empty = el('div', 's-ch-recon s-ch-recon--empty');
      empty.appendChild(el('div', 's-ch-recon-line', sync.never
        ? '대사 대상 없음 · 아직 동기화되지 않았습니다'
        : '대사 대상 없음 · 이 기간에 일별·건별 정산 행이 없습니다'));
      host.appendChild(empty);
      return;
    }
    var ok = diff === 0;
    var box = el('div', 's-ch-recon ' + (ok ? 's-ch-recon--ok' : 's-ch-recon--warn'));
    var line = el('div', 's-ch-recon-line');
    line.appendChild(el('span', null, '일별 합계 ' + moneyText(recon.daily_total)));
    line.appendChild(el('span', 's-ch-recon-vs', 'vs'));
    line.appendChild(el('span', null, '건별 합계 ' + moneyText(recon.case_total)));
    line.appendChild(el('span', 's-ch-recon-vs', '→'));
    line.appendChild(el('b', 's-ch-recon-diff' + (diff < 0 ? ' s-ch-neg' : ''),
      diff == null ? '차이 미상' : '차이 ' + moneyText(diff)));
    line.appendChild(el('span', 's-ch-badge ' + (ok ? 's-ch-badge--ok' : 's-ch-badge--warn'),
      ok ? '대사 일치' : '대사 불일치'));
    box.appendChild(line);
    box.appendChild(el('div', 's-ch-note', ok
      ? '같은 기간을 일별 API 와 건별 API 로 각각 합산한 값입니다. 두 값이 같으면 적재가 온전합니다.'
      : '두 API 의 합이 다릅니다. 적재 누락이거나 소급 변경입니다 — 예외 원장에서 확인하세요.'));
    host.appendChild(box);
  }

  /* ═══════════════ 9. 렌더 — 원장 스위처 ═══════════════ */

  function renderSwitch(ctx) {
    var host = ctx.els.ledgerSwitch;
    if (!host) return;
    var data = ctx.state.data;
    host.querySelectorAll('[data-settlement-ch-ledger]').forEach(function (btn) {
      var view = btn.getAttribute('data-settlement-ch-ledger');
      btn.setAttribute('aria-pressed', String(view === ctx.state.view));
      if (view !== 'exceptions') return;
      var slot = btn.querySelector('[data-settlement-ch-slot="exc-count"]');
      if (!slot) {
        slot = el('span', 's-ch-switch-count');
        slot.setAttribute('data-settlement-ch-slot', 'exc-count');
        btn.appendChild(slot);
      }
      // 조회 전에는 건수를 적지 않는다 — "예외 0" 은 읽기 전에 할 수 있는 말이 아니다.
      slot.textContent = data ? ' ' + fmtCount((data.exceptions || []).length) : '';
    });
    // 표 날짜 축 셀렉트는 이 줄의 마지막 자식이다. 예외 큐는 날짜 축이 없는 목록이라 감춘다 —
    // 고를 수는 있는데 표가 안 바뀌면 고장으로 읽힌다.
    var tools = host.querySelector('[data-settlement-ch-switch-tools]');
    if (tools) setHidden(tools, ctx.state.view === 'exceptions');
  }

  /**
   * 원장 본문. 도구줄(유형 필터·검색)은 **한 번만 만들고 재사용**한다 — 매번 다시 만들면
   * 검색창이 한 글자마다 포커스를 잃는다.
   */
  function renderLedger(ctx) {
    var host = ctx.els.ledger;
    if (!host) return;
    var tools = host.querySelector('[data-settlement-ch-slot="tools"]');
    if (!tools) {
      tools = el('div', 's-ch-tools');
      tools.setAttribute('data-settlement-ch-slot', 'tools');
      host.appendChild(tools);
    }
    var body = host.querySelector('[data-settlement-ch-slot="ledger-body"]');
    if (!body) {
      body = el('div', 's-ch-ledger-body');
      body.setAttribute('data-settlement-ch-slot', 'ledger-body');
      host.appendChild(body);
    }
    renderTools(ctx, tools);
    clearNode(body);
    if (ctx.state.view !== 'exceptions') renderLedgerAxisNote(ctx, body);
    if (ctx.state.view === 'exceptions') renderExceptions(ctx, body);
    else if (ctx.state.view === 'vat') renderVat(ctx, body);
    else if (ctx.state.view === 'commission') renderCommission(ctx, body);
    else renderCaseLedger(ctx, body);
  }

  /**
   * 유형 필터 + 주문번호 검색.
   *
   * **노드를 매번 새로 만들지 않는다.** 검색은 디바운스 뒤 재조회를 부르고 재조회는 다시 이
   * 함수를 부르므로, 여기서 input 을 갈아끼우면 한 번 검색할 때마다 커서가 사라진다.
   * 값·옵션만 갱신하고, 포커스가 그 노드에 있으면 값도 건드리지 않는다.
   */
  function renderTools(ctx, host) {
    var showFilters = ctx.state.view !== 'exceptions';
    var label = ensureSlot(host, 'tools-lbl', 'span', 's-ch-tools-lbl', true);
    label.textContent = currentLedgerLabel(ctx) + ' 원장';

    var select = host.querySelector('[data-settlement-ch-type]');
    if (!select) {
      select = el('select', 's-ch-select');
      select.setAttribute('data-settlement-ch-type', '');
      select.setAttribute('aria-label', '유형 필터');
      host.appendChild(select);
    }
    var search = host.querySelector('[data-settlement-ch-q]');
    if (!search) {
      search = el('input', 's-ch-input');
      search.type = 'search';
      search.setAttribute('data-settlement-ch-q', '');
      search.setAttribute('aria-label', '주문번호·상품주문번호·구매자명 검색');
      search.placeholder = '주문번호 · 상품주문번호 · 구매자명 검색';
      host.appendChild(search);
    }
    var note = ensureSlot(host, 'tools-note', 'span', 's-ch-note', true);
    note.textContent = '예외 큐는 조회 조건 전체를 대상으로 계산됩니다.';

    setHidden(select, !showFilters);
    setHidden(search, !showFilters);
    setHidden(note, showFilters);
    if (showFilters) syncTypeOptions(ctx, select);
    if (document.activeElement !== search) search.value = ctx.state.q || '';
  }

  /** 유형 `<option>` 은 후보 집합이 실제로 바뀐 때만 다시 만든다(선택 중 목록이 흔들리지 않게). */
  function syncTypeOptions(ctx, select) {
    var options = ctx.state.typeOptions || {};
    var codes = Object.keys(options).sort();
    if (ctx.state.type && codes.indexOf(ctx.state.type) === -1) codes.push(ctx.state.type);
    var signature = codes.join('|');
    if (select.getAttribute('data-settlement-ch-typesig') !== signature) {
      clearNode(select);
      select.appendChild(new Option('유형 전체', ''));
      codes.forEach(function (code) { select.appendChild(new Option(options[code] || code, code)); });
      select.setAttribute('data-settlement-ch-typesig', signature);
    }
    select.value = ctx.state.type || '';
  }

  function currentLedgerLabel(ctx) {
    for (var i = 0; i < LEDGER_VIEWS.length; i++) {
      if (LEDGER_VIEWS[i].view === ctx.state.view) return LEDGER_VIEWS[i].label;
    }
    return '건별 정산';
  }

  /* ── 표 조립 헬퍼 ─────────────────────────────────────────────── */

  /**
   * 표 뼈대. 좁은 폭에서 표가 카드로 접히면 열 머리가 사라지므로, 셀마다 `data-label` 을
   * 남겨 CSS 가 `::before` 로 되살린다(`addRow` 가 붙인다).
   *
   * @param {Array} columns [{key,label,type}].
   * @param {Array} extraHead 추가 열 이름.
   * @returns {object} {wrap, table, tbody, labels}.
   */
  function tableFor(columns, extraHead) {
    var wrap = el('div', 's-ch-tablewrap');
    var table = el('table', 's-ch-table');
    var thead = el('thead');
    var tr = el('tr');
    columns.forEach(function (col) {
      tr.appendChild(el('th', col.type === 'money' ? 's-ch-num' : null, col.label));
    });
    (extraHead || []).forEach(function (label) { tr.appendChild(el('th', null, label)); });
    thead.appendChild(tr);
    table.appendChild(thead);
    var tbody = el('tbody');
    table.appendChild(tbody);
    wrap.appendChild(table);
    return {
      wrap: wrap,
      table: table,
      tbody: tbody,
      labels: columns.map(function (col) { return col.label; }).concat(extraHead || []),
    };
  }

  /** 행을 붙이며 셀마다 열 이름을 `data-label` 로 남긴다(좁은 폭 카드 전환용). */
  function addRow(built, tr) {
    Array.prototype.forEach.call(tr.children, function (cell, index) {
      if (built.labels[index]) cell.setAttribute('data-label', built.labels[index]);
    });
    built.tbody.appendChild(tr);
  }

  function valueCell(row, col) {
    if (col.type === 'money') {
      var amount = row[col.key];
      return el('td', 's-ch-num' + (amount < 0 ? ' s-ch-neg' : ''), moneyText(amount));
    }
    if (col.type === 'enum') {
      return el('td', null, row[col.key + '_label'] || row[col.key] || '—');
    }
    var text = row[col.key];
    var cell = el('td', col.type === 'id' ? 's-ch-id' : null, text == null || text === '' ? '—' : String(text));
    if (col.type === 'text' && text) cell.title = String(text);
    return cell;
  }

  /** FOMS 연결 배지. 색만으로 말하지 않는다(글자가 같은 사실을 반복한다). */
  function matchCell(row) {
    var status = String(row.match_status || 'NA').toUpperCase();
    var cell = el('td');
    var text = status === 'MATCHED' ? 'FOMS 연결' : (status === 'UNMATCHED' ? '미연결' : '해당 없음');
    var cls = status === 'MATCHED' ? 's-ch-badge--ok'
      : (status === 'UNMATCHED' ? 's-ch-badge--warn' : 's-ch-badge--muted');
    cell.appendChild(el('span', 's-ch-badge ' + cls, text));
    if (status === 'MATCHED' && row.foms_order_id) {
      cell.appendChild(el('span', 's-ch-dep-cnt', ' #' + row.foms_order_id));
    }
    return cell;
  }

  /** 행 펼치기 — `raw` 전 필드 key/value 표(원본을 감추지 않는다). */
  function rawDetails(row) {
    var raw = row.raw;
    var details = el('details', 's-ch-raw');
    details.appendChild(el('summary', null, '원본 필드 보기'));
    if (!raw || typeof raw !== 'object') {
      details.appendChild(el('div', 's-ch-note', '이 행에는 원본 스냅샷이 없습니다.'));
      return details;
    }
    var table = el('table', 's-ch-raw-tbl');
    var tbody = el('tbody');
    Object.keys(raw).sort().forEach(function (key) {
      var tr = el('tr');
      tr.appendChild(el('th', null, key));
      var value = raw[key];
      tr.appendChild(el('td', null,
        value == null ? '' : (typeof value === 'object' ? JSON.stringify(value) : String(value))));
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    details.appendChild(table);
    return details;
  }

  /* ── S5 건별 정산 원장 ────────────────────────────────────────── */

  function rowDateOf(row, kind, basis) {
    if (kind === 'vat_case') return row.settle_basis_date || '';
    if (basis === 'expect' || !BASIS_DATE_FIELD[basis]) return row.settle_expect_date || row.search_date || '';
    // 완료일·기준일·결제일 축은 되돌리지 않는다(서버 _ledger_axis 와 같은 규칙 — 빈 행은 서버가 이미 뺐다).
    return row[BASIS_DATE_FIELD[basis]] || '';
  }

  /** 표에 실제로 적용된 축(서버가 확정). 없는 축을 골랐으면 서버가 되돌린 축이 온다. */
  function ledgerAxisBasis(ledger, ctx) {
    return (ledger && ledger.axis && ledger.axis.basis) || ctx.state.basis;
  }

  /** 표 머리 한 줄: 이 표의 날짜 축·되돌림·빠진 행 수. 위쪽 집계는 늘 정산 예정일이라 따로 말한다. */
  function renderLedgerAxisNote(ctx, host) {
    var ledger = ctx.state.data.ledger || {};
    var axis = ledger.axis || {};
    var label = axis.label || '정산 예정일 기준';
    // 되돌림 문장의 「X」 는 **요청한 축**이다(요청 echo `data.basis`). 셀렉트는 이제 실효 축을
    // 보이므로 selectedOptions 를 읽으면 "「정산 예정일」 축이 없어 정산 예정일 기준으로"라는
    // 자기모순이 난다(C1).
    var requested = ctx.state.data.basis || '';
    var option = ctx.els.basis ? ctx.els.basis.querySelector('option[value="' + requested + '"]') : null;
    var picked = option ? option.textContent.trim() : String(requested);
    var parts = ['표 날짜 축: ' + label];
    if (axis.supported === false) parts.push('이 표에는 「' + picked + '」 축이 없어 ' + label + '으로 보여 줍니다');
    if (axis.excluded) {
      parts.push((BASIS_NOUN[axis.basis] || '축 날짜') + '이 없는 ' + fmtCount(axis.excluded) +
        '건은 이 표에서 뺐습니다(정산 예정일 축에서 보세요)');
    }
    // 축을 바꾸면 날짜가 있는 행도 조회 창 밖으로 밀려난다 — 빠진 행이 "없는 행"으로 읽히지
    // 않게 수를 말한다(C2). `excluded`(축 날짜 NULL)와 서로소라 합쳐 세지 않는다.
    if (axis.shifted_out) {
      parts.push('이 축 날짜가 조회 기간 밖인 ' + fmtCount(axis.shifted_out) +
        '건은 이 기간 표에 없습니다(정산 예정일 축에서 보세요)');
    }
    parts.push('위 KPI·차트는 늘 정산 예정일 기준');
    host.appendChild(el('div', 's-ch-note s-ch-ledger-axis', parts.join(' · ')));
  }

  /**
   * 날짜 그룹 `<details>` + 행 표. 그룹 요약은 **기간 전체 합계**(서버 `groups`)를 말하고,
   * 펼친 안쪽은 **이 페이지에 있는 행**만 보여준다 — 둘을 같은 숫자인 척하지 않는다.
   */
  function renderCaseLedger(ctx, host) {
    var ledger = ctx.state.data.ledger || {};
    var kind = ledger.kind || 'case';
    var columns = COLUMNS[kind] || COLUMNS.case;
    var rows = ledger.rows || [];
    var groups = ledger.groups || [];
    if (!rows.length && !groups.length) {
      host.appendChild(emptyBox(ctx, '이 조건에 맞는 정산 건이 없습니다 (0건).'));
      return;
    }
    var byDate = {};
    rows.forEach(function (row) {
      var key = rowDateOf(row, kind, ledgerAxisBasis(ledger, ctx)) || '날짜 미상';
      (byDate[key] = byDate[key] || []).push(row);
    });
    var order = groups.length
      ? groups.map(function (group) { return { date: group.date, count: group.count, amount: group.amount }; })
      : Object.keys(byDate).sort().reverse().map(function (date) {
        return { date: date, count: byDate[date].length, amount: sumBy(byDate[date], function (r) { return r.settle_expect_amount; }) };
      });
    var opened = false;
    order.forEach(function (group) {
      var pageRows = byDate[group.date] || [];
      var details = el('details', 's-ch-group');
      if (pageRows.length && !opened) { details.open = true; opened = true; }
      var summary = el('summary', 's-ch-group-sum');
      summary.appendChild(el('b', null, group.date || '날짜 미상'));
      summary.appendChild(el('span', 's-ch-group-meta',
        '총 ' + fmtCount(group.count) + '건 · ' + moneyText(group.amount) +
        ' · 이 페이지 ' + fmtCount(pageRows.length) + '건'));
      details.appendChild(summary);
      if (!pageRows.length) {
        details.appendChild(el('div', 's-ch-note', '이 날짜의 행은 다른 페이지에 있습니다.'));
      } else {
        details.appendChild(ledgerTable(columns, pageRows, kind));
      }
      host.appendChild(details);
    });
    host.appendChild(ledgerFoot(ctx, ledger));
    host.appendChild(renderPager(ctx, ledger.pagination));
  }

  function ledgerTable(columns, rows, kind) {
    var built = tableFor(columns, kind === 'case' ? ['FOMS 연결', '원본'] : ['원본']);
    rows.forEach(function (row) {
      var tr = el('tr');
      columns.forEach(function (col) { tr.appendChild(valueCell(row, col)); });
      if (kind === 'case') tr.appendChild(matchCell(row));
      var rawTd = el('td');
      rawTd.appendChild(rawDetails(row));
      tr.appendChild(rawTd);
      addRow(built, tr);
    });
    return built.wrap;
  }

  function ledgerFoot(ctx, ledger) {
    var pagination = ledger.pagination || {};
    var foot = el('div', 's-ch-foot');
    foot.appendChild(el('span', null, '총 ' + fmtCount(pagination.total) + '건'));
    foot.appendChild(el('span', null, PER_PAGE + '건 / 페이지'));
    if (ctx.state.type) foot.appendChild(el('span', null, '유형 필터 적용 중'));
    if (ctx.state.q) foot.appendChild(el('span', null, '검색어 "' + ctx.state.q + '"'));
    foot.appendChild(el('span', 's-ch-note', '음수는 취소·환급입니다. 절대값으로 바꾸지 않습니다.'));
    return foot;
  }

  /* ── 페이저 ───────────────────────────────────────────────────── */

  function pageButton(label, page, opts) {
    var btn = el('button', 's-ch-page', label);
    btn.type = 'button';
    btn.setAttribute('data-settlement-ch-page', String(page));
    if (opts && opts.current) btn.setAttribute('aria-current', 'page');
    if (opts && opts.disabled) btn.disabled = true;
    return btn;
  }

  function renderPager(ctx, pagination) {
    var pager = el('div', 's-ch-pager');
    var pages = (pagination && pagination.pages) || 0;
    var current = (pagination && pagination.page) || 1;
    if (pages <= 1) return pager;
    pager.appendChild(pageButton('◂', current - 1, { disabled: current <= 1 }));
    var numbers = [];
    for (var n = 1; n <= pages; n++) {
      if (n === 1 || n === pages || Math.abs(n - current) <= PAGER_WINDOW) numbers.push(n);
    }
    var prev = 0;
    numbers.forEach(function (n) {
      if (prev && n - prev > 1) pager.appendChild(el('span', 's-ch-page-gap', '…'));
      pager.appendChild(pageButton(String(n), n, { current: n === current }));
      prev = n;
    });
    pager.appendChild(pageButton('▸', current + 1, { disabled: current >= pages }));
    return pager;
  }

  /* ── S6 수수료 ────────────────────────────────────────────────── */

  function renderCommission(ctx, host) {
    var data = ctx.state.data;
    var commission = data.commission || {};
    var byType = commission.by_type || [];
    var total = commission.total;
    var paySettleTotal = sumBy(data.daily || [], function (d) { return d.pay_settle; });
    host.appendChild(cardHead('수수료 구성',
      '기간 ' + moneyText(total) + ' · 결제 정산액 대비 ' +
      (paySettleTotal ? (Math.abs(total / paySettleTotal) * 100).toFixed(2) + '%' : '—')));
    if (!byType.length) {
      host.appendChild(emptyBox(ctx, '이 기간에 수수료 행이 없습니다 (0건).'));
    } else {
      var colored = byType.map(function (item, index) {
        return {
          label: item.label || item.type,
          amount: item.amount,
          share: item.share,
          color: index < CATEGORICAL.length ? CATEGORICAL[index] : CATEGORICAL_REST,
        };
      });
      host.appendChild(shareBar(colored));
      var maxAmount = Math.max.apply(null, colored.map(function (it) { return Math.abs(it.amount || 0); }).concat([0]));
      var ranking = el('div', 's-ch-ranks');
      colored.forEach(function (item) { ranking.appendChild(rankRow(item, maxAmount)); });
      host.appendChild(ranking);
    }
    var interlock = commission.max_interlock || {};
    host.appendChild(meterRow('매출 연동 수수료 상한', interlock.amount, interlock.cap));
    host.appendChild(el('div', 's-ch-note',
      '수수료·세액은 네이버가 계산한 값을 그대로 표시합니다. FOMS 가 다시 계산하지 않습니다.'));
    var ledger = data.ledger || {};
    if ((ledger.kind || '') === 'commission') {
      var rows = ledger.rows || [];
      if (rows.length) host.appendChild(ledgerTable(COLUMNS.commission, rows, 'commission'));
      else host.appendChild(emptyBox(ctx, '이 조건에 맞는 수수료 상세가 없습니다 (0건).'));
      host.appendChild(ledgerFoot(ctx, ledger));
      host.appendChild(renderPager(ctx, ledger.pagination));
    }
  }

  /* ── S7 부가세 ────────────────────────────────────────────────── */

  /**
   * VAT 기간표 + 합계 sticky 행. 당월처럼 **아직 제공되지 않는 구간은 0 으로 그리지 않고**
   * 안내를 낸다(계약 D-8). 빈 배열을 0 원 표로 만드는 순간 세무 자료가 거짓말이 된다.
   */
  function renderVat(ctx, host) {
    var vat = ctx.state.data.vat || {};
    var rows = vat.rows || [];
    var banner = el('div', 's-ch-banner');
    banner.setAttribute('data-foms-no-autodismiss', '');
    banner.appendChild(el('b', null, '부가세 자료는 ' + (vat.available_to || '전월 말일') + '까지 제공됩니다.'));
    banner.appendChild(el('span', null, ' 당월분은 익월 마감 후에 조회됩니다.'));
    host.appendChild(banner);
    if (!rows.length) {
      host.appendChild(emptyBox(ctx, '이 기간의 부가세 자료가 아직 제공되지 않았습니다.'));
      host.appendChild(vatFootnotes());
      return;
    }
    var columns = [{ key: 'date', label: '정산 기준일', type: 'text' }].concat(
      VAT_COLUMNS.map(function (col) { return { key: col.key, label: col.label, type: 'money' }; }));
    var built = tableFor(columns, []);
    rows.forEach(function (row) {
      var tr = el('tr');
      columns.forEach(function (col) { tr.appendChild(valueCell(row, col)); });
      addRow(built, tr);
    });
    var tfoot = el('tfoot', 's-ch-total');
    var totalRow = el('tr');
    totalRow.appendChild(el('th', null, '합계 (' + fmtCount(rows.length) + '일)' + (vat.final ? ' · 확정' : '')));
    VAT_COLUMNS.forEach(function (col) {
      var amount = (vat.total || {})[col.key];
      totalRow.appendChild(el('td', 's-ch-num' + (amount < 0 ? ' s-ch-neg' : ''), moneyText(amount)));
    });
    tfoot.appendChild(totalRow);
    built.table.appendChild(tfoot);
    host.appendChild(built.wrap);
    host.appendChild(vatFootnotes());
    var ledger = ctx.state.data.ledger || {};
    if ((ledger.kind || '') === 'vat_case' && (ledger.rows || []).length) {
      host.appendChild(cardHead('부가세 건별 원장', '조회 구간의 건별 자료'));
      host.appendChild(ledgerTable(COLUMNS.vat_case, ledger.rows, 'vat_case'));
      host.appendChild(ledgerFoot(ctx, ledger));
      host.appendChild(renderPager(ctx, ledger.pagination));
    }
  }

  function vatFootnotes() {
    var notes = el('div', 's-ch-note');
    notes.appendChild(el('div', null,
      '부가세 과세표준은 통장 입금액(정산액)이 아니라 결제금액 총액입니다.'));
    notes.appendChild(el('div', null,
      '네이버가 차감한 수수료는 네이버 발행 세금계산서로 매입세액 공제받으세요.'));
    return notes;
  }

  /* ── S8 예외 큐 ───────────────────────────────────────────────── */

  /**
   * 예외 표. **"0건"과 "아직 동기화되지 않음"을 다른 문구로 구분한다**(계약 D-10) —
   * 동기화 전의 빈 목록은 "예외 없음"이 아니라 "아직 모른다"이다.
   */
  function renderExceptions(ctx, host) {
    var data = ctx.state.data;
    var rows = data.exceptions || [];
    var sync = data.sync || {};
    if (sync.never) {
      host.appendChild(emptyBox(ctx, ''));
      return;
    }
    if (!rows.length) {
      var box = el('div', 's-ch-empty s-ch-empty--ok');
      box.appendChild(el('b', null, '조치가 필요한 예외가 없습니다 (0건).'));
      box.appendChild(el('div', null, '마지막 동기화 ' + (fmtStamp(sync.last_ok_at) || '시각 미상') + ' 기준입니다.'));
      host.appendChild(box);
      return;
    }
    var kpi = data.kpi || {};
    if (kpi.unmatched_count) {
      host.appendChild(el('div', 's-ch-note',
        'FOMS 미연결 ' + fmtCount(kpi.unmatched_count) + '건 = 워크벤치 대기 ' +
        fmtCount(kpi.unmatched_pending_count) + '건(링크 있음·주문 미생성 — [열기]가 그 집으로 갑니다) + 수집 전 주문 ' +
        fmtCount(kpi.unmatched_unlinked_count) + '건(링크 없음 — [열기]가 수집 운영 화면으로 갑니다). ' +
        '표에는 갈래마다 최근 것부터 상한까지만 실립니다.'));
    }
    var built = tableFor([
      { key: 'label', label: '사유', type: 'text' },
      { key: 'date', label: '일자', type: 'text' },
      { key: 'amount', label: '금액', type: 'money' },
    ], ['경과', '조치']);
    rows.forEach(function (row) {
      var tr = el('tr');
      var reason = el('td');
      reason.appendChild(el('span', 's-ch-badge s-ch-badge--' + excKindClass(row.kind), row.label || row.kind || '사유 미상'));
      tr.appendChild(reason);
      tr.appendChild(el('td', null, row.date || '—'));
      tr.appendChild(el('td', 's-ch-num' + (row.amount < 0 ? ' s-ch-neg' : ''), moneyText(row.amount)));
      tr.appendChild(el('td', null, isNum(row.age_days) ? row.age_days + '일' : '—'));
      tr.appendChild(actionCell(row));
      addRow(built, tr);
    });
    host.appendChild(built.wrap);
    host.appendChild(el('div', 's-ch-note',
      '예외는 조회 구간 전체를 대상으로 계산됩니다. 소급 변경은 값을 덮어쓰지 않고 여기에 남깁니다.'));
  }

  function excKindClass(kind) {
    var code = String(kind || '').toUpperCase();
    if (code === 'UNMATCHED' || code === 'COUNT_MISMATCH') return 'warn';
    if (code === 'UNLINKED') return 'info';
    if (code === 'NEGATIVE' || code === 'RETRO') return 'muted';
    return 'hold';
  }

  /** 조치 링크. **같은 출처 상대 경로만** 링크한다(서버가 준 값이라도 외부 URL 은 안 건다). */
  function actionCell(row) {
    var cell = el('td');
    var url = String(row.action_url || '');
    if (/^\/[^/]/.test(url)) {
      var link = el('a', 's-ch-link', '열기');
      link.href = url;
      cell.appendChild(link);
    } else {
      cell.appendChild(el('span', 's-ch-dash', '—'));
    }
    return cell;
  }

  /* ═══════════════ 10. 전체 렌더 ═══════════════ */

  function renderAll(ctx) {
    if (!ctx.state.data) return;
    syncControls(ctx);
    renderSync(ctx);
    renderBackfillBanner(ctx);
    renderKpis(ctx);
    renderDaily(ctx);
    renderWaterfall(ctx);
    renderDeposit(ctx);
    renderReconcile(ctx);
    renderSwitch(ctx);
    renderLedger(ctx);
  }

  /** 폭이 바뀌었을 때 SVG 만 되그린다(표·원장은 그대로 둬서 열어둔 `<details>` 가 안 닫힌다). */
  function redrawCharts(ctx) {
    if (!ctx.state.data) return;
    renderDaily(ctx);
    renderWaterfall(ctx);
  }

  /* ═══════════════ 11. 동기화 요청 + rev 폴링 ═══════════════ */

  function notice(ctx, text, isError) {
    ctx.state.notice = { text: text, error: !!isError };
    renderSync(ctx);
  }

  /** [지금 동기화] — enqueue 만 한다. 워커가 실제로 돌기까지 걸리므로 `rev` 로 반영을 확인한다. */
  /**
   * 동기화 요청. `backfillFrom`(YYYY-MM-DD) 이 있으면 그 날짜부터 소급 적재를 큐에 넣는다 —
   * 워커가 네이버 제약대로 창을 쪼개 받아오므로(30일 창·daily 28일·case 하루) 화면은 부탁만 한다.
   */
  async function requestSync(ctx, backfillFrom) {
    if (ctx.state.syncing) return;
    var url = ctx.root.getAttribute('data-settlement-ch-sync-api') || SYNC_API_FALLBACK;
    ctx.state.syncing = true;
    ctx.state.backfilling = !!backfillFrom;
    if (ctx.els.syncBtn) ctx.els.syncBtn.disabled = true;
    renderBackfillBanner(ctx);
    notice(ctx, backfillFrom ? backfillFrom + ' 부터 받아오기를 요청하는 중입니다…' : '동기화를 요청하는 중입니다…');
    try {
      var body = await postJson(url, backfillFrom ? { backfill_from: backfillFrom } : {});
      var queued = !!(body.data && body.data.queued);
      var minutes = backfillFrom ? Math.max(1, Math.round(daysBetween(backfillFrom, ctx.state.today) * BACKFILL_MINUTES_PER_DAY)) : 1;
      notice(ctx, queued
        ? (backfillFrom ? '받아오기를 요청했습니다. 워커가 받아오는 동안 최대 10분간 반영을 확인합니다(예상 약 ' + minutes + '분).'
                        : '동기화를 요청했습니다. 워커가 처리하는 동안 최대 1분간 반영을 확인합니다.')
        : '이미 대기 중인 동기화가 있습니다. 반영을 확인합니다.');
      startRevPoll(ctx, backfillFrom ? POLL_MAX_TRIES_BACKFILL : POLL_MAX_TRIES);
    } catch (err) {
      notice(ctx, err && err.handled ? err.message : '동기화 요청에 실패했습니다. 잠시 후 다시 시도하세요.', true);
      ctx.state.syncing = false;
      if (ctx.els.syncBtn) ctx.els.syncBtn.disabled = false;
    }
  }

  function stopRevPoll(ctx) {
    if (ctx.pollTimer) window.clearTimeout(ctx.pollTimer);
    ctx.pollTimer = null;
    ctx.state.syncing = false;
    ctx.state.backfilling = false;
    if (ctx.els.syncBtn) ctx.els.syncBtn.disabled = false;
    renderBackfillBanner(ctx);
  }

  function daysBetween(fromIso, toIso) {
    var a = new Date(fromIso + 'T00:00:00Z'), b = new Date(toIso + 'T00:00:00Z');
    return Math.max(0, Math.round((b - a) / 86400000));
  }

  /**
   * 기간 바 아래 배너: 요청 시작일이 적재 시작일보다 앞이면 "그 앞쪽은 아직 안 받아왔다" 고 말하고
   * [이 구간 받아오기] 로 소급 적재를 큐에 넣는다. 버튼 없이 자동으로 받지 않는다 — 넓은 구간을 잘못
   * 고르면 매번 수백 호출이 나간다. 적재 이력이 없으면(never) [지금 동기화] 가 그 역할이라 숨긴다.
   */
  function renderBackfillBanner(ctx) {
    var host = ensureSlot(ctx.els.bar, 'backfill', 'div', 's-ch-backfill', true);
    if (!host) return;
    host.setAttribute('data-settlement-ch-backfill', '');
    clearNode(host);
    var data = ctx.state.data;
    var sync = (data && data.sync) || {};
    var from = ctx.state.from;
    var missing = !!(data && !sync.never && sync.coverage_from && from && from < sync.coverage_from);
    setHidden(host, !missing && !ctx.state.backfilling);
    if (host.hidden) return;
    if (ctx.state.backfilling) {
      host.appendChild(el('span', 's-ch-backfill-text', '받아오는 중입니다… 워커가 창을 나눠 순서대로 받아옵니다. 반영되면 화면을 다시 읽습니다.'));
      return;
    }
    var lastMissing = addDays(sync.coverage_from, -1);
    // 워커는 시작일부터 오늘+14 까지 **전부** 다시 받는다(빠진 구간만이 아니다) — 예상 시간도 그 폭으로 센다.
    var minutes = Math.max(1, Math.round(daysBetween(from, ctx.state.today) * BACKFILL_MINUTES_PER_DAY));
    host.appendChild(el('span', 's-ch-backfill-text',
      '이 구간 앞쪽 ' + from + ' ~ ' + lastMissing + ' 은 아직 받아오지 않았습니다(적재 구간 ' +
      sync.coverage_from + ' ~ ' + (sync.coverage_to || '—') + '). 받아오면 약 ' + minutes + '분 걸립니다.'));
    var btn = el('button', 's-ch-btn', '이 구간 받아오기');
    btn.type = 'button';
    btn.setAttribute('data-settlement-ch-backfill-btn', '');
    btn.setAttribute('data-from', from);
    host.appendChild(btn);
  }

  /**
   * `sync.rev` 를 10초 간격으로 최대 6번 확인하고, 바뀌면 화면을 다시 읽는다.
   * 6번 안에 안 바뀌면 **조용히 포기하지 않고** 그 사실을 문구로 남긴다.
   */
  function startRevPoll(ctx, maxTries) {
    var limit = maxTries || POLL_MAX_TRIES;
    var before = ctx.state.rev;
    var tries = 0;
    var tick = async function () {
      if (!ctx.root.isConnected) { stopRevPoll(ctx); return; }
      tries += 1;
      try {
        var data = await getJson(buildUrl(ctx));
        var rev = data.sync ? data.sync.rev : null;
        if (rev !== before) {
          adoptServerState(ctx, data);
          showState(ctx, 'ready');
          renderAll(ctx);
          notice(ctx, '동기화가 반영되어 화면을 다시 읽었습니다.');
          stopRevPoll(ctx);
          return;
        }
      } catch (err) {
        notice(ctx, err && err.handled ? err.message : '반영 확인 중 통신에 실패했습니다.', true);
        stopRevPoll(ctx);
        return;
      }
      if (tries >= limit) {
        notice(ctx, Math.round(limit * POLL_INTERVAL_MS / 60000) + '분 안에 반영되지 않았습니다. 워커가 밀렸을 수 있으니 잠시 뒤 새로고침하세요.', true);
        stopRevPoll(ctx);
        return;
      }
      ctx.pollTimer = window.setTimeout(tick, POLL_INTERVAL_MS);
    };
    ctx.pollTimer = window.setTimeout(tick, POLL_INTERVAL_MS);
  }

  /* ═══════════════ 12. 배선 ═══════════════ */

  function reload(ctx, resetPage) {
    if (resetPage) ctx.state.page = 1;
    ctx.state.notice = null;
    load(ctx);
  }

  /**
   * 원장 뷰 전환. 재조회 여부는 **지금 실려 있는 원장 종류**(`data.ledger.kind`)와 비교해서
   * 정한다 — 뷰 이름끼리 비교하면 "수수료 → 예외 → 수수료" 왕복이 재조회 없이 지나가
   * 건별 행을 수수료 화면에 그리게 된다.
   */
  function switchLedger(ctx, view) {
    if (!view || ctx.state.view === view) return;
    var loadedKind = (ctx.state.data && ctx.state.data.ledger && ctx.state.data.ledger.kind) || null;
    var wanted = ledgerParam(view);
    var needsFetch = view !== 'exceptions' && wanted !== loadedKind;
    ctx.state.view = view;
    if (view !== 'exceptions') ctx.state.lastLedger = view;
    ctx.state.page = 1;
    if (needsFetch) {
      // 축은 **여기서 되맞추지 않는다.** 되돌림 정본은 서버 `_ledger_axis` 하나다 — 클라가
      // 요청 전에 고쳐 보내면 `supported=false` 가 영영 안 와서 "이 표에는 「결제일」 축이
      // 없어 정산 예정일 기준으로 보여 줍니다" 안내가 사라진다(조용한 되돌림 재발).
      // 원장이 바뀌면 유형 코드 체계가 통째로 바뀐다. 옛 필터를 들고 가면 0건이 나온다.
      ctx.state.type = '';
      ctx.state.q = '';
      reload(ctx, true);
    } else {
      renderSwitch(ctx);
      renderLedger(ctx);
    }
  }

  function bindControls(ctx) {
    // 리스너는 전부 이 루트 **안쪽**에만 붙는다. 프래그먼트 스왑으로 루트가 사라지면 리스너도
    // 같이 사라져 전역에 누적되지 않는다(perf G4).
    ctx.root.addEventListener('click', function (e) {
      var target = e.target;
      if (!target || !target.closest) return;
      // CSV 드롭다운: 바깥을 누르면 닫는다. **document 리스너를 새로 만들지 않으려고**
      // 이미 있는 루트 위임 하나에 얹는다(전역 리스너 3개 계약 유지).
      if (!target.closest('[data-settlement-ch-export]') && exportOpen(ctx)) toggleExport(ctx, false);
      if (target.closest('[data-settlement-ch-export-btn]')) {
        toggleExport(ctx, !exportOpen(ctx));
        return;
      }
      if (target.closest('[data-settlement-ch-export-kind]')) { toggleExport(ctx, false); return; }
      if (target.closest('[data-settlement-ch-sync-btn]')) { requestSync(ctx); return; }
      var backfillBtn = target.closest('[data-settlement-ch-backfill-btn]');
      if (backfillBtn) { requestSync(ctx, backfillBtn.getAttribute('data-from') || ctx.state.from); return; }
      if (target.closest('[data-settlement-ch-retry]')) { reload(ctx, false); return; }
      var ledgerBtn = target.closest('[data-settlement-ch-ledger]');
      if (ledgerBtn && ctx.root.contains(ledgerBtn)) {
        switchLedger(ctx, ledgerBtn.getAttribute('data-settlement-ch-ledger'));
        return;
      }
      var pageBtn = target.closest('[data-settlement-ch-page]');
      if (pageBtn && ctx.root.contains(pageBtn)) {
        var next = parseInt(pageBtn.getAttribute('data-settlement-ch-page'), 10);
        if (isFinite(next) && next >= 1 && next !== ctx.state.page) {
          ctx.state.page = next;
          reload(ctx, false);
        }
      }
    });

    ctx.root.addEventListener('change', function (e) {
      var target = e.target;
      if (!target || !target.matches) return;
      if (target.matches('[data-settlement-ch-basis]')) { ctx.state.basis = target.value; reload(ctx, true); return; }
      if (target.matches('[data-settlement-ch-granularity]')) { ctx.state.granularity = target.value; reload(ctx, true); return; }
      if (target.matches('[data-settlement-ch-from]')) { ctx.state.from = target.value; reload(ctx, true); return; }
      if (target.matches('[data-settlement-ch-to]')) { ctx.state.to = target.value; reload(ctx, true); return; }
      if (target.matches('[data-settlement-ch-type]')) { ctx.state.type = target.value; reload(ctx, true); }
    });

    // 검색은 입력마다 왕복하지 않는다(정산 원장은 전량 스캔 질의다).
    ctx.root.addEventListener('input', function (e) {
      var target = e.target;
      if (!target || !target.matches || !target.matches('[data-settlement-ch-q]')) return;
      window.clearTimeout(ctx.searchTimer);
      var value = target.value.trim();
      ctx.searchTimer = window.setTimeout(function () {
        if (value === ctx.state.q) return;
        ctx.state.q = value;
        reload(ctx, true);
      }, SEARCH_DEBOUNCE_MS);
    });

    ctx.root.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && exportOpen(ctx)) {
        toggleExport(ctx, false);
        if (ctx.els.exportBtn) ctx.els.exportBtn.focus();
        return;
      }
      if (e.key !== 'Enter') return;
      var target = e.target;
      if (!target || !target.matches || !target.matches('[data-settlement-ch-q]')) return;
      e.preventDefault();
      window.clearTimeout(ctx.searchTimer);
      ctx.state.q = target.value.trim();
      reload(ctx, true);
    });
  }

  /* ═══════════════ 12-B. 요약 탭 크로스 스트립(S11 · T12) ═══════════════
     이 한 줄만 **채널 pane 밖**(요약 탭 그리드)에 산다. 요약 탭의 5타일은 완료일 축이고
     이 줄은 정산 예정일 축이라 숫자가 원래 다르다 — 그래서 KPI 줄에 섞지 않고 아래 한 칸을
     따로 쓴다. 서버는 빈 앵커만 내고(요약 탭 목업 스캔이 "예정"을 금지한다) 문구는 전부
     여기 소유다.

     **"매출" 이라는 낱말을 쓰지 않는다.** 이 줄이 말하는 것은 전부 정산이고, 매출 인식은
     완료일 축의 요약 타일이 이미 말하고 있다. 두 낱말을 한 화면에서 섞으면 어느 쪽이
     매출인지 사람이 다시 헷갈린다. */

  /** 스트립 금액 축약 — 한 줄에 값 셋이 들어가야 하므로 만원 단위로 접는다(표시 계층 전용). */
  function stripMoney(value) {
    return isNum(value) ? '₩' + fmtMan(toMan(value)) : '—';
  }

  /** 값 한 칸(라벨 + 금액·건수). 음수 금액은 색으로 한 번 더 말한다(부호는 지우지 않는다). */
  function stripItem(label, text, negative) {
    var item = el('span', 's-ch-strip-item');
    item.appendChild(el('span', 's-ch-strip-lbl', label));
    item.appendChild(el('span', 's-ch-strip-val' + (negative ? ' s-ch-neg' : ''), text));
    return item;
  }

  /**
   * 탭 버튼을 눌러 채널 탭을 연다. **새 탭 API 를 만들지 않는다** — 셸의 탭 버튼을 그대로
   * 누르면 활성화·`aria`·pane 토글이 전부 기존 경로를 탄다(`dashboard.js` 무수정 유지).
   */
  function openChannelTab(host, tabKey) {
    var scope = host.closest('[data-settlement-active-tab]') || document;
    var btn = scope.querySelector('[data-settlement-tab="' + tabKey + '"]');
    if (btn) btn.click();
  }

  /** 스트립 한 줄을 그린다. 데이터를 받은 뒤에만 불린다(값 없이 자리만 차지하지 않는다). */
  function renderStrip(host, data) {
    var strip = data.strip || {};
    var sync = data.sync || {};
    clearNode(host);
    host.appendChild(el('span', 's-ch-strip-lead', '▸'));
    host.appendChild(el('span', 's-ch-strip-axis',
      (data.basis_label || '정산 예정일 기준') + ' · ' +
      (data.channel === 'NAVER' ? '네이버' : String(data.channel || ''))));

    if (sync.never) {
      // 0원과 미동기화는 다른 사실이다. 한 번도 안 맞춰 봤으면 숫자를 아예 내지 않는다.
      host.appendChild(el('span', 's-ch-strip-msg', '아직 한 번도 동기화되지 않았습니다'));
    } else {
      host.appendChild(stripItem('정산 완료', stripMoney(strip.settled_amount),
        strip.settled_amount < 0));
      host.appendChild(stripItem('정산 예정', stripMoney(strip.expected_amount),
        strip.expected_amount < 0));
      host.appendChild(stripItem('예외', fmtCount(strip.exception_count) + '건', false));
      // 오래된 값이면 "언제 기준인가"를 값 옆에서 한 번 더 말한다. 표기는 S0 헤더와 같은
      // 헬퍼를 쓴다 — 두 자리가 같은 시각을 다른 문장으로 말하면 사람이 둘을 대조한다.
      var ago = sync.stale ? agoText(sync.last_ok_at || sync.last_run_at) : '';
      if (ago) host.appendChild(el('span', 's-ch-strip-badge', '(' + ago + ' 기준)'));
    }

    var open = el('button', 's-ch-strip-open', '네이버 정산 열기 →');
    open.type = 'button';
    open.setAttribute('data-settlement-ch-strip-open', '');
    open.addEventListener('click', function () {
      openChannelTab(host, strip.tab_key ||
        host.getAttribute('data-settlement-ch-strip-tab') || CHANNEL_TAB);
    });
    host.appendChild(open);
    setHidden(host, false);
  }

  /**
   * 스트립 마운트 — 호스트당 1회. **탭 활성화를 기다리지 않는다**(요약 탭이 첫 화면이다).
   *
   * 실패는 **조용히 삼킨다**. 이 파일의 다른 모든 실패는 상태 노드로 말하지만 여기만
   * 예외인 이유: 이 줄이 통째로 없어도 요약 탭의 어떤 숫자도 틀리지 않고(다른 축의 보조
   * 정보다), 진짜 상태는 채널 탭이 자기 상태 노드로 말한다. 요약 탭 한복판에 빨간 배너를
   * 띄우면 "요약이 고장났다"는 잘못된 신호가 된다. 실패하면 `hidden` 을 유지한다 —
   * **0 을 그리지 않는다**(결측을 0 으로 말하지 않는 계약 D-10).
   */
  function mountStrip(host) {
    if (!host || host.dataset.settlementChStripMounted === '1') return;
    host.dataset.settlementChStripMounted = '1';
    // 셸 앵커가 클래스를 갖고 오지 않을 수 있다(총괄 hunk 판본). CSS 훅은 클래스 쪽이므로
    // 여기서 붙인다 — 이미 있으면 무해하고, 없으면 스트립이 무스타일로 떨어지는 것을 막는다.
    host.classList.add('s-ch-strip');
    var range = initialRange(host);
    var base = host.getAttribute('data-settlement-ch-strip-api') || API_FALLBACK;
    var url = base + (base.indexOf('?') === -1 ? '?' : '&') +
      'view=strip&channel=' +
      encodeURIComponent(host.getAttribute('data-settlement-ch-strip-channel') || 'NAVER') +
      '&from=' + encodeURIComponent(range.from) + '&to=' + encodeURIComponent(range.to);
    getJson(url).then(function (data) {
      if (host.isConnected && data && data.strip) renderStrip(host, data);
    }).catch(function () { /* 무음: 위 docstring 참조 */ });
  }

  /* ═══════════════ 13. 마운트 ═══════════════ */

  var mounts = [];

  /** 앵커는 `data-*` 를 먼저, 없으면 계약 §6 의 id 를 본다(파셜이 둘 중 하나만 줘도 산다). */
  function pick(root, attr, id) {
    return root.querySelector('[' + attr + ']') || root.querySelector('#' + id);
  }

  function collectEls(root) {
    return {
      sync: pick(root, 'data-settlement-ch-sync', 'foms-settle-ch-sync'),
      syncState: root.querySelector('[data-settlement-ch-sync-state]'),
      syncBtn: root.querySelector('[data-settlement-ch-sync-btn]'),
      bar: pick(root, 'data-settlement-ch-bar', 'foms-settle-ch-bar'),
      axisNote: root.querySelector('[data-settlement-ch-axis-note]'),
      basis: root.querySelector('[data-settlement-ch-basis]'),
      from: root.querySelector('[data-settlement-ch-from]'),
      to: root.querySelector('[data-settlement-ch-to]'),
      granularity: root.querySelector('[data-settlement-ch-granularity]'),
      kpi: pick(root, 'data-settlement-ch-kpi-wrap', 'foms-settle-ch-kpi'),
      daily: pick(root, 'data-settlement-ch-daily', 'foms-settle-ch-daily'),
      waterfall: pick(root, 'data-settlement-ch-waterfall', 'foms-settle-ch-waterfall'),
      deposit: pick(root, 'data-settlement-ch-deposit', 'foms-settle-ch-deposit'),
      reconcile: pick(root, 'data-settlement-ch-reconcile', 'foms-settle-ch-reconcile'),
      ledgerSwitch: pick(root, 'data-settlement-ch-ledger-switch', 'foms-settle-ch-ledger-switch'),
      exportHost: pick(root, 'data-settlement-ch-export', 'foms-settle-ch-export'),
      exportBtn: root.querySelector('[data-settlement-ch-export-btn]'),
      exportMenu: root.querySelector('[data-settlement-ch-export-menu]'),
      ledger: pick(root, 'data-settlement-ch-ledger-body-host', 'foms-settle-ch-ledger'),
      loading: root.querySelector('[data-settlement-ch-loading]'),
      error: root.querySelector('[data-settlement-ch-error]'),
      errorDetail: root.querySelector('[data-settlement-ch-error-detail]'),
      empty: root.querySelector('[data-settlement-ch-empty]'),
    };
  }

  /** 기본 구간: 오늘−30 ~ 오늘+14. `data-settlement-ch-today` 가 있으면 그 날짜가 "오늘"이다. */
  function initialRange(root) {
    var attr = root.getAttribute('data-settlement-ch-today');
    var today = isDay(attr) ? attr : kstToday();
    return { today: today, from: addDays(today, -DEFAULT_BACK_DAYS), to: addDays(today, DEFAULT_FORWARD_DAYS) };
  }

  function ensureLoaded(ctx) {
    if (ctx.state.loaded) return;
    ctx.state.loaded = true;
    load(ctx);
  }

  /**
   * 첫 조회를 **탭이 열릴 때**로 미룬다 — 요약 탭만 보고 나가는 사용자에게 정산 전량 집계
   * 왕복을 물리지 않는다. 셸은 탭 전환 이벤트를 쏘지 않으므로 CSS 가 이미 SSOT 로 쓰는 루트
   * 속성 `data-settlement-active-tab` 을 관찰한다(두 번째 신호를 발명하지 않는다).
   */
  function watchTabActivation(ctx) {
    var shell = ctx.root.closest('[data-settlement-active-tab]');
    if (!shell || typeof MutationObserver !== 'function') {
      ensureLoaded(ctx);
      return;
    }
    if (shell.getAttribute('data-settlement-active-tab') === CHANNEL_TAB) ensureLoaded(ctx);
    ctx.observer = new MutationObserver(function () {
      if (shell.getAttribute('data-settlement-active-tab') === CHANNEL_TAB) {
        ensureLoaded(ctx);
        redrawCharts(ctx);   // 숨은 pane 은 clientWidth 0 이라 열리는 순간 되그려야 한다
      }
    });
    ctx.observer.observe(shell, { attributes: true, attributeFilter: ['data-settlement-active-tab'] });
  }

  /**
   * 폭 변화 감시. window resize 리스너를 싱글톤 뒤에 1회 등록하면 스왑 후 **새 스코프의**
   * 마운트가 그 리스너에 잡히지 않는다(옛 스코프의 배열만 본다). 루트별 ResizeObserver 는
   * 루트와 함께 죽고 함께 태어나므로 그 사각이 없다.
   */
  function watchResize(ctx) {
    if (typeof ResizeObserver !== 'function') return;
    ctx.resizeObserver = new ResizeObserver(function () {
      window.clearTimeout(ctx.resizeTimer);
      ctx.resizeTimer = window.setTimeout(function () {
        if (ctx.root.isConnected) redrawCharts(ctx);
      }, RESIZE_DEBOUNCE_MS);
    });
    if (ctx.els.daily) ctx.resizeObserver.observe(ctx.els.daily);
    if (ctx.els.waterfall) ctx.resizeObserver.observe(ctx.els.waterfall);
  }

  function mount(root) {
    if (!root || root.dataset.settlementChMounted === '1') return;
    root.dataset.settlementChMounted = '1';
    var range = initialRange(root);
    var ctx = {
      root: root,
      els: collectEls(root),
      tip: null,
      observer: null,
      resizeObserver: null,
      resizeTimer: null,
      searchTimer: null,
      pollTimer: null,
      state: {
        channel: root.getAttribute('data-settlement-ch-channel') || 'NAVER',
        basis: 'expect',
        granularity: 'day',
        from: range.from,
        to: range.to,
        today: range.today,
        view: 'case',
        lastLedger: 'case',
        type: '',
        q: '',
        page: 1,
        per_page: PER_PAGE,
        typeKind: null,
        typeOptions: {},
        data: null,
        rev: null,
        notice: null,
        seq: 0,
        loaded: false,
        syncing: false,
        backfilling: false,
        holdbackOpen: false,
      },
    };
    // 서버가 셀렉트 기본값을 렌더했다면 그 값이 시작값이다(이 파일에 옵션을 적지 않는다).
    if (ctx.els.basis && ctx.els.basis.value) ctx.state.basis = ctx.els.basis.value;
    if (ctx.els.granularity && ctx.els.granularity.value) ctx.state.granularity = ctx.els.granularity.value;
    mounts.push(ctx);
    syncControls(ctx);
    renderSwitch(ctx);
    bindControls(ctx);
    // 포커스가 드롭다운 밖으로 나가면 닫는다(키보드 사용자에게 열린 채로 남지 않게).
    if (ctx.els.exportHost) {
      ctx.els.exportHost.addEventListener('focusout', function (e) {
        if (!ctx.els.exportHost.contains(e.relatedTarget)) toggleExport(ctx, false);
      });
    }
    watchTabActivation(ctx);
    watchResize(ctx);
  }

  function mountAll() {
    // 떨어져 나간 루트는 정리한다 — 스왑으로 DOM 에서 사라진 화면의 옵저버·타이머를 남기지 않는다.
    mounts = mounts.filter(function (ctx) {
      if (ctx.root.isConnected) return true;
      if (ctx.observer) ctx.observer.disconnect();
      if (ctx.resizeObserver) ctx.resizeObserver.disconnect();
      window.clearTimeout(ctx.resizeTimer);
      window.clearTimeout(ctx.searchTimer);
      window.clearTimeout(ctx.pollTimer);
      return false;
    });
    document.querySelectorAll(ROOT_SELECTOR).forEach(mount);
    // 두 번째 마운트 축(T12). 스트립 호스트는 요약 탭 안이라 채널 루트의 자손이 아니다 —
    // 그래도 **같은 mountAll()** 이 돌므로 프래그먼트 스왑 경로가 그대로 덮인다.
    document.querySelectorAll(STRIP_SELECTOR).forEach(mountStrip);
  }

  // 전역(document) 리스너는 싱글톤 뒤에서 1회만 — 프래그먼트 재실행 때 중복 누적 금지(perf G4).
  if (!window.__FOMS_SETTLEMENT_CHANNEL_BOUND) {
    window.__FOMS_SETTLEMENT_CHANNEL_BOUND = true;
    document.addEventListener('foms:main-content-swapped', mountAll);
    document.addEventListener('foms:erp-shell-fragment-swapped', mountAll);
    document.addEventListener('DOMContentLoaded', mountAll);
  }

  // defer 로 실린 첫 로드와, 셸이 <script src> 를 재실행하는 스왑 경로를 **둘 다** 덮는다.
  mountAll();
})();
