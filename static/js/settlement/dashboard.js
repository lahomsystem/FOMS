/**
 * 정산 대시보드 (SETTLE-DASH-01 M3) — 목업 확정본의 SVG 렌더 함수 이식 + 집계 API 배선.
 *
 * 원본: docs/design/mockups/settlement-dashboard-v1-executive.html <script> :330-883.
 * 차트는 목업 그대로 **자체 인라인 SVG** 다. 외부 차트 라이브러리를 쓰지 않는다(perf G2).
 *
 * 데이터: GET /api/settlement/aggregates (M2). 목업의 하드코딩 배열은 전부 걷어냈고
 * 렌더 함수(lineChart/columnChart/sparkSvg)는 시그니처까지 그대로 살렸다.
 *
 * 목업에서 뺀 카드: 월 매출 목표 미터 · 현금흐름 30일 카드(둘 다 근거 데이터가 시스템에
 * 없다) · 목업 워터마크 배지. 단계 라벨은 API 의 `stages[].label` 을 그대로 쓴다 — 이 파일에
 * 단계 이름을 한 글자도 적지 않는다(목업이 지어낸 단계가 실화면에 남는 사고 방지).
 *
 * **프래그먼트 재실행 규율(perf G4)**: 이 화면은 ERP 셸 탭으로도 들어온다. 셸은 프래그먼트
 * 를 innerHTML 로 갈아끼운 뒤 `<script src>` 를 재실행하고(erp-shell.js:309-339, 403-415)
 * DOMContentLoaded 는 다시 뜨지 않는다. 그래서
 *   (1) document/window 리스너는 `window.__FOMS_SETTLEMENT_DASHBOARD_BOUND` 싱글톤 뒤에서 1회만,
 *   (2) 실제 마운트는 루트의 `data-settlement-mounted` 표식으로 루트당 1회만,
 *   (3) 스크립트 재실행과 swap 이벤트 **양쪽**에서 mountAll() 을 불러 어느 순서로 와도 뜨게 한다.
 * (order-change-banner.js:5-8 · mobile-queue-scroll.js:107 과 같은 패턴.)
 *
 * 금액 단위: API 는 **원**, 목업 렌더러는 **만원** 기준이다. 경계에서 toMan() 한 번만 통과시킨다.
 *
 * **분석 탭(§4.5)**: 같은 응답을 다른 축으로 본다 — 채널 3지표 · 담당자별(권한 게이트) ·
 * 단계별 · 부서별 차감 · 수금 구성 · AS 분포. 매출 추이는 요약 탭이 이미 그려서 복제하지
 * 않는다. 집계 막대는 SVG 가 아니라 CSS 퍼센트 폭이라 숨은 pane 폭 0 함정 밖이다.
 *
 * **탭 3종(SETTLE-TABS-01)**: 요약(경영진) · 실무(경리·수금) · 분석이 한 라우트 안의 탭이다.
 * 탭 배선도 루트 안쪽 위임 리스너 + `mount()` 안에서만 이뤄진다(위 (1)(2) 규율 그대로).
 * 탭 전환의 핵심 함정은 **숨은 pane 의 폭이 0** 이라는 것이다 — 그 상태에서 그린 차트는
 * 폴백 폭(400px)으로 굳어 눌린 채 남으므로 activateTab() 이 활성화 직후 renderAll 로
 * 되그린다(실측 수치와 함께 그쪽 주석에 적어 뒀다).
 */
(function () {
  'use strict';

  var ROOT_SELECTOR = '[data-foms-settlement-dashboard]';
  var API_FALLBACK = '/api/settlement/aggregates';

  /* ── 색 사전 (목업 확정본 :379-393 — 팔레트 검증 기록은 목업 하단 주석) ────────── */
  var ACCENT = '#2a78d6';                                          // 매출 가족 (slot-1)
  var CTX = '#8a94a3';                                             // 전월 비교 = 강조용 그레이
  var BLUE_BUCKET4 = ['#86b6ef', '#5598e7', '#2a78d6', '#104281']; // 매출 금액구간 램프
  var BUCKET_EDGES = [450, 700, 900];                              // 만원
  var BUCKET_LABELS = ['~449만', '450~699만', '700~899만', '900만~'];
  // 비교 라인이 y축 상한을 끌어올릴 수 있는 배수. 막대가 주 마크라 그 1.5배까지만
  // 양보하고, 그 위는 축 상단에 고정하고 캐럿으로 표시한다(columnChart 주석 참조).
  var LINE_HEADROOM = 1.5;
  var ORANGE_RAMP5 = ['#f19979', '#eb6834', '#c74b12', '#9f3701', '#752600']; // 미수 aging 램프
  var FAM = { rev: '#2a78d6', ar: '#eb6834', col: '#1baf7a', vol: '#6b7280' };
  var FAM_TINT = { rev: '#f1f6fd', ar: '#fdf3ed', col: '#eefaf5', vol: '#f4f6f8' };
  var CHANNEL_COLORS = { '일반': '#2a78d6', '네이버': '#eb6834' };
  var CHANNEL_FALLBACK = ['#6b7280', '#7b4bd6', '#0f8a8a', '#b45309', '#8a3b6b'];

  function bucketColor(v) {
    for (var i = 0; i < BUCKET_EDGES.length; i++) {
      if (v < BUCKET_EDGES[i]) return BLUE_BUCKET4[i];
    }
    return BLUE_BUCKET4[BLUE_BUCKET4.length - 1];
  }

  function channelColor(name, index) {
    if (CHANNEL_COLORS[name]) return CHANNEL_COLORS[name];
    return CHANNEL_FALLBACK[index % CHANNEL_FALLBACK.length];
  }

  /* ═══════════════ 1. 헬퍼 ═══════════════ */

  /** SVG 문자열에 넣는 텍스트 이스케이프. 채널명·단계 라벨은 DB/상수에서 온다. */
  function esc(text) {
    return String(text == null ? '' : text)
      .replace(/&/g, '&amp;').replace(/</g, '&lt;')
      .replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  /** 원 → 만원(반올림). API 는 원, 목업 렌더러는 만원이 단위다. */
  function toMan(won) {
    return typeof won === 'number' && isFinite(won) ? Math.round(won / 10000) : 0;
  }

  /** 만원 → "2억 1,430만" / "838만" / "0". */
  function fmtMan(v) {
    v = Math.round(v);
    if (v === 0) return '0';
    var neg = v < 0 ? '−' : '';
    v = Math.abs(v);
    if (v >= 10000) {
      var eok = Math.floor(v / 10000);
      var man = v % 10000;
      return neg + (man ? eok + '억 ' + man.toLocaleString('ko-KR') + '만' : eok + '억');
    }
    return neg + v.toLocaleString('ko-KR') + '만';
  }

  /** 축 눈금·막대 캡용 압축 표기. 좁은 카드에서 캡이 서로 겹치지 않게 억은 소수 1자리. */
  function fmtTick(v) {
    if (v === 0) return '0';
    if (v >= 10000) {
      var e = v / 10000;
      return (Number.isInteger(e) ? e : e.toFixed(1)) + '억';
    }
    return v.toLocaleString('ko-KR') + '만';
  }

  /** 원 → "4,411만원" (각주·툴팁용 — 단위까지 붙인다). */
  function fmtWon(won) {
    return fmtMan(toMan(won)) + '원';
  }

  function fmtCount(n) {
    return (typeof n === 'number' && isFinite(n) ? n : 0).toLocaleString('ko-KR');
  }

  function niceScale(maxV, tickCount) {
    tickCount = tickCount || 5;
    if (!(maxV > 0)) return { top: 1, ticks: [0, 1] };
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

  function cumsum(arr) {
    var s = 0;
    return arr.map(function (v) { return (s += v); });
  }

  function sum(arr, pick) {
    return (arr || []).reduce(function (acc, item) {
      var v = pick ? pick(item) : item;
      return acc + (typeof v === 'number' && isFinite(v) ? v : 0);
    }, 0);
  }

  function roundTopRect(x, y, w, h, r) {
    r = Math.min(r, w / 2, h);
    return 'M' + x + ',' + (y + h) + ' L' + x + ',' + (y + r) +
      ' Q' + x + ',' + y + ' ' + (x + r) + ',' + y +
      ' L' + (x + w - r) + ',' + y +
      ' Q' + (x + w) + ',' + y + ' ' + (x + w) + ',' + (y + r) +
      ' L' + (x + w) + ',' + (y + h) + ' Z';
  }

  function toggle(el, hidden) {
    if (el) el.classList.toggle('s-hidden', !!hidden);
  }

  function clear(el) {
    if (el) el.textContent = '';
  }

  /** 서울 달력 기준 "YYYY-MM-DD". Intl 이 없거나 타임존 미지원이면 null(서버 기본값에 맡긴다). */
  function kstDay() {
    try {
      var text = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Seoul', year: 'numeric', month: '2-digit', day: '2-digit',
      }).format(new Date());
      return /^\d{4}-\d{2}-\d{2}$/.test(text) ? text : null;
    } catch (e) {
      return null;
    }
  }

  function kstMonth() {
    var day = kstDay();
    return day ? day.slice(0, 7) : null;
  }

  /** "조회 2026-08-31 09:04 (KST)" — 데이터 신선도 표기. */
  function kstStamp() {
    var day = kstDay();
    if (!day) return '';
    try {
      var time = new Intl.DateTimeFormat('ko-KR', {
        timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hour12: false,
      }).format(new Date());
      return '조회 ' + day + ' ' + time + ' (KST)';
    } catch (e) {
      return '조회 ' + day + ' (KST)';
    }
  }

  function shiftMonth(monthKey, delta) {
    if (!/^\d{4}-\d{2}$/.test(monthKey || '')) return null;
    var index = parseInt(monthKey.slice(0, 4), 10) * 12 + (parseInt(monthKey.slice(5, 7), 10) - 1) + delta;
    var year = Math.floor(index / 12);
    var month = (index % 12) + 1;
    return String(year).padStart(4, '0') + '-' + String(month).padStart(2, '0');
  }

  function monthLabel(monthKey) {
    if (!/^\d{4}-\d{2}$/.test(monthKey || '')) return '';
    return parseInt(monthKey.slice(0, 4), 10) + '년 ' + parseInt(monthKey.slice(5, 7), 10) + '월';
  }

  /** 짧은 월 라벨 "8월" — 범례처럼 폭이 좁은 자리용(긴 라벨은 범례를 두 줄로 접는다). */
  function shortMonthLabel(monthKey) {
    if (!/^\d{4}-\d{2}$/.test(monthKey || '')) return '';
    return parseInt(monthKey.slice(5, 7), 10) + '월';
  }

  /** 서버 일별 라벨 "8/1" → 목업 x축 표기 "1일". 다른 형식이면 그대로 둔다. */
  function dayLabel(label) {
    var m = /^(\d{1,2})\/(\d{1,2})$/.exec(String(label || ''));
    return m ? parseInt(m[2], 10) + '일' : label;
  }

  /* ═══════════════ 2. 툴팁 (라벨은 전부 textContent — innerHTML 미사용) ═══════════════ */

  function showTip(ctx, x, y, title, rows) {
    var tt = ctx.els.tooltip;
    if (!tt) return;
    tt.textContent = '';
    var head = document.createElement('div');
    head.className = 's-tt-title';
    head.textContent = title;
    tt.appendChild(head);
    rows.forEach(function (r) {
      var row = document.createElement('div');
      row.className = 's-tt-row';
      if (r.color) {
        var key = document.createElement('i');
        key.className = 's-tt-key';
        key.style.setProperty('--s-key-color', r.color);
        row.appendChild(key);
      }
      var val = document.createElement('span');
      val.className = 's-tt-val';
      val.textContent = r.val;
      row.appendChild(val);
      if (r.lbl) {
        var lbl = document.createElement('span');
        lbl.className = 's-tt-lbl';
        lbl.textContent = r.lbl;
        row.appendChild(lbl);
      }
      tt.appendChild(row);
    });
    tt.classList.add('s-on');
    var box = tt.getBoundingClientRect();
    var px = x + 14;
    var py = y + 16;
    if (px + box.width > window.innerWidth - 8) px = x - box.width - 12;
    if (py + box.height > window.innerHeight - 8) py = y - box.height - 12;
    tt.style.setProperty('--s-tt-x', Math.max(4, px) + 'px');
    tt.style.setProperty('--s-tt-y', Math.max(4, py) + 'px');
  }

  function hideTip(ctx) {
    if (ctx.els.tooltip) ctx.els.tooltip.classList.remove('s-on');
  }

  /* ═══════════════ 3. 차트 렌더러 (데이터 배열 → SVG, 좌표 하드코딩 없음) ═══════════════ */

  /* ── 차트 높이 (2026-09-02 폭·높이 개편) ─────────────────────────────
     1440 캡을 풀어 폭이 1.5배가 됐는데 높이가 268 그대로면 차트가 납작해진다. 추이 차트는
     뷰포트 세로의 38% 를 320~460 사이로 쓴다(1080 화면 ≈ 410, 노트북 768 ≈ 320). aging 은
     막대 5개 + 값 캡이라 300 고정. 리사이즈는 이미 renderMountedRoots 가 되그린다. */
  var AGING_CHART_HEIGHT = 300;
  function trendChartHeight() {
    return Math.max(320, Math.min(460, Math.round(window.innerHeight * 0.38)));
  }

  /* ── 집중 모드 ────────────────────────────────────────────────────────
     body 클래스 하나로 공용 크롬(글로벌 헤더·nav·ERP 헤더·서브탭)을 접는다. 실제 숨김은 CSS 가
     `body.foms-settle-focus:has(.foms-settlement-root)` 로 스코프하므로, 셸 스왑으로 정산 루트가
     사라지면 클래스가 남아도 다른 화면 메뉴는 멀쩡하다. 선택은 localStorage 에 기억한다 —
     경리는 이 화면에 몇 시간 붙어 있어 매번 다시 누르게 하면 안 쓴다. */
  var FOCUS_CLASS = 'foms-settle-focus';
  var FOCUS_STORAGE_KEY = 'foms.settlement.focus';
  function isFocusMode() { return document.body.classList.contains(FOCUS_CLASS); }
  function readFocusPreference() {
    try { return window.localStorage.getItem(FOCUS_STORAGE_KEY) === '1'; }
    catch (err) { return false; }   // 프라이빗 모드 등 저장소 접근 거부 — 기억만 못 할 뿐 기능은 산다
  }
  function syncFocusButtons() {
    var on = isFocusMode();
    document.querySelectorAll('[data-settlement-focus]').forEach(function (btn) {
      btn.setAttribute('aria-pressed', String(on));
    });
  }
  function setFocusMode(on) {
    document.body.classList.toggle(FOCUS_CLASS, !!on);
    try {
      if (on) window.localStorage.setItem(FOCUS_STORAGE_KEY, '1');
      else window.localStorage.removeItem(FOCUS_STORAGE_KEY);
    } catch (err) { /* 저장소 거부 — 위 readFocusPreference 와 같은 이유로 무시 */ }
    syncFocusButtons();
  }

  /**
   * 라인 차트: crosshair 스냅 + 전 시리즈 툴팁 + 키보드(←→).
   * 목업 대비 유일한 변경: 시리즈 길이가 서로 달라도 된다(전월이 30일, 당월이 31일).
   * 목업은 series[0] 길이를 n 으로 못박아 짧은 쪽이 축을 밀어버렸다.
   */
  function lineChart(ctx, host, cfg) {
    var w = host.clientWidth || 640;
    var h = cfg.height;
    var pad = { t: 16, r: 16, b: 28, l: 48 };
    var pw = w - pad.l - pad.r;
    var ph = h - pad.t - pad.b;
    var n = Math.max.apply(null, cfg.series.map(function (s) { return s.values.length; }));
    if (n < 1 || pw <= 0) { clear(host); return; }
    var maxV = Math.max.apply(null, cfg.series.reduce(function (acc, s) { return acc.concat(s.values); }, [0]));
    var sc = niceScale(maxV, cfg.tickCount || 5);
    var X = function (i) { return pad.l + (n === 1 ? pw / 2 : i * pw / (n - 1)); };
    var Y = function (v) { return pad.t + ph - v / sc.top * ph; };

    var s = '<svg width="' + w + '" height="' + h + '" role="img" aria-label="' + esc(cfg.aria || '') + '">';
    sc.ticks.forEach(function (tv) {
      s += '<line x1="' + pad.l + '" x2="' + (w - pad.r) + '" y1="' + Y(tv) + '" y2="' + Y(tv) +
        '" stroke="' + (tv === 0 ? 'var(--s-axis)' : 'var(--s-grid)') + '" stroke-width="1"/>';
      if (tv > 0) {
        s += '<text class="s-axis-t" x="' + (pad.l - 6) + '" y="' + (Y(tv) + 3.5) +
          '" text-anchor="end">' + esc(fmtTick(tv)) + '</text>';
      }
    });
    for (var i = 0; i < n; i++) {
      if (cfg.xTick(i, n)) {
        s += '<text class="s-axis-t" x="' + X(i) + '" y="' + (h - 8) + '" text-anchor="middle">' +
          esc(cfg.xLabel(i)) + '</text>';
      }
    }
    cfg.series.forEach(function (ser) {
      var m = ser.values.length;
      if (!m) return;
      if (ser.area) {
        var d = 'M' + X(0) + ',' + Y(ser.values[0]);
        ser.values.forEach(function (v, ix) { d += ' L' + X(ix).toFixed(1) + ',' + Y(v).toFixed(1); });
        d += ' L' + X(m - 1) + ',' + Y(0) + ' L' + X(0) + ',' + Y(0) + ' Z';
        s += '<path d="' + d + '" fill="' + ser.color + '" opacity="0.1"/>';
      }
      var pts = ser.values.map(function (v, ix) { return X(ix).toFixed(1) + ',' + Y(v).toFixed(1); }).join(' ');
      s += '<polyline points="' + pts + '" fill="none" stroke="' + ser.color +
        '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"' +
        (ser.dash ? ' stroke-dasharray="6 5"' : '') + '/>';
      if (ser.endDot) {
        s += '<circle cx="' + X(m - 1) + '" cy="' + Y(ser.values[m - 1]) +
          '" r="4.5" fill="' + ser.color + '" stroke="var(--s-surface)" stroke-width="2"/>';
      }
    });
    s += '<line class="s-cross" x1="0" x2="0" y1="' + pad.t + '" y2="' + (pad.t + ph) +
      '" stroke="#b9c4d4" stroke-width="1" visibility="hidden"/>';
    s += '<rect class="s-hit" x="' + pad.l + '" y="' + pad.t + '" width="' + pw + '" height="' + ph +
      '" fill="transparent" tabindex="0" aria-label="차트 값 탐색 — 좌우 화살표 키"/>';
    s += '</svg>';
    host.innerHTML = s;

    var svg = host.firstElementChild;
    var cross = svg.querySelector('.s-cross');
    var hit = svg.querySelector('.s-hit');
    function activate(i, cx, cy) {
      cross.setAttribute('x1', X(i));
      cross.setAttribute('x2', X(i));
      cross.setAttribute('visibility', 'visible');
      showTip(ctx, cx, cy, cfg.tipTitle(i), cfg.tipRows(i));
    }
    function deactivate() {
      cross.setAttribute('visibility', 'hidden');
      hideTip(ctx);
    }
    hit.addEventListener('pointermove', function (e) {
      var box = svg.getBoundingClientRect();
      var step = n === 1 ? pw : pw / (n - 1);
      var i = Math.max(0, Math.min(n - 1, Math.round((e.clientX - box.left - pad.l) / step)));
      activate(i, e.clientX, e.clientY);
    });
    hit.addEventListener('pointerleave', deactivate);
    var fi = n - 1;
    hit.addEventListener('focus', function () {
      var box = svg.getBoundingClientRect();
      activate(fi, box.left + X(fi), box.top + pad.t + 40);
    });
    hit.addEventListener('blur', deactivate);
    hit.addEventListener('keydown', function (e) {
      if (e.key === 'ArrowLeft') fi = Math.max(0, fi - 1);
      else if (e.key === 'ArrowRight') fi = Math.min(n - 1, fi + 1);
      else return;
      e.preventDefault();
      var box = svg.getBoundingClientRect();
      activate(fi, box.left + X(fi), box.top + pad.t + 40);
    });
  }

  /**
   * 컬럼 차트: 그룹 단위 hit 영역(≥밴드폭), hover 리프트 + 툴팁 + 포커스.
   * cfg.line = { color, values } 로 동일 축·동일 단위의 비교 라인 오버레이(이중 y축 아님).
   *
   * 목업 대비 변경 2가지 — 둘 다 실데이터에서만 드러나는 거짓말을 막는다:
   *  (a) 0 인 막대에 1.5px 하한을 주지 않는다(목업 :553). 0 건인데 막대가 보이면 안 된다.
   *      대신 0 이 아닌 값은 3px 하한을 줘서 aging 처럼 한 버킷이 압도할 때도 안 사라진다.
   *  (b) 비교 라인 길이가 그룹 수와 달라도 있는 데까지만 그린다(전월이 30일일 때).
   */
  function columnChart(ctx, host, cfg) {
    var w = host.clientWidth || 400;
    var h = cfg.height;
    var pad = { t: cfg.caps ? 26 : 16, r: 10, b: cfg.twoLineX ? 40 : 28, l: 48 };
    var pw = w - pad.l - pad.r;
    var ph = h - pad.t - pad.b;
    var g = cfg.groups.length;
    if (!g || pw <= 0) { clear(host); return; }
    var band = pw / g;
    var barMax = Math.max.apply(null, cfg.groups.reduce(function (acc, gr) {
      return acc.concat(gr.bars.map(function (b) { return b.v; }));
    }, [0]));
    var lineMax = cfg.line && cfg.line.values.length ? Math.max.apply(null, cfg.line.values) : 0;
    // 축 상한: 막대가 주(主) 마크다. 비교 라인이 막대보다 아무리 커도 축을 끌고 올라갈 수
    // 있는 한도를 둔다 — 목업은 두 시리즈 규모가 비슷한 가정치라 `max(barMax, lineMax)` 로
    // 충분했지만, 실데이터에서는 전월의 큰 하루 하나가 축 상한을 잡아 **당월 막대 전체를
    // 납작하게** 만든다(스테이징 2026-08 실측: 전월 스파이크 2,200만이 축을 3,000만으로
    // 끌어올려 막대가 전부 눌렸다). 넘치는 라인 구간은 아래에서 축 상단에 고정하고
    // 캐럿으로 "여기서 축을 넘어간다"를 표시한다 — 잘라놓고 말 안 하면 그게 거짓말이다.
    var axisMax = barMax > 0
      ? Math.max(barMax, Math.min(lineMax, barMax * LINE_HEADROOM))
      : lineMax;
    var sc = niceScale(axisMax, cfg.tickCount || 4);
    var Y = function (v) { return pad.t + ph - v / sc.top * ph; };
    var centerX = function (gi) { return pad.l + gi * band + band / 2; };

    var s = '<svg width="' + w + '" height="' + h + '" role="img" aria-label="' + esc(cfg.aria || '') + '">';
    sc.ticks.forEach(function (tv) {
      s += '<line x1="' + pad.l + '" x2="' + (w - pad.r) + '" y1="' + Y(tv) + '" y2="' + Y(tv) +
        '" stroke="' + (tv === 0 ? 'var(--s-axis)' : 'var(--s-grid)') + '" stroke-width="1"/>';
      if (tv > 0) {
        s += '<text class="s-axis-t" x="' + (pad.l - 6) + '" y="' + (Y(tv) + 3.5) +
          '" text-anchor="end">' + esc(fmtTick(tv)) + '</text>';
      }
    });
    cfg.groups.forEach(function (gr, gi) {
      var nb = gr.bars.length;
      var inset = Math.min(12, band * 0.25); // 밴드가 좁아도(일별 31개) 인접 막대 갭 ≥2px 보장
      var bw = Math.max(1, Math.min(24, (band - inset - (nb - 1) * 2) / nb));
      var total = nb * bw + (nb - 1) * 2;
      var x0 = pad.l + gi * band + (band - total) / 2;
      var cx = centerX(gi);
      s += '<g class="s-cgrp">';
      gr.bars.forEach(function (b, bi) {
        var bx = x0 + bi * (bw + 2);
        // 0 은 기본적으로 그리지 않는다(aging 처럼 한 버킷이 압도하는 서열 차트에서
        // 최소 높이 하한은 "적지만 있다"는 거짓 신호가 된다).
        // 시계열 차트만 cfg.zeroFloor 로 목업과 같은 baseline 스텁을 켠다 — 거기서는
        // "그날 0원"이 실재하는 사실이고, 스텁이 없으면 빈 날이 통째로 사라져
        // 막대의 리듬이 무너지고 비교 라인만 남아 라인 차트로 읽힌다.
        var bh = b.v > 0 ? Math.max(3, b.v / sc.top * ph) : 0;
        if (bh > 0) {
          s += '<path d="' + roundTopRect(bx, pad.t + ph - bh, bw, bh, 4) + '" fill="' + b.color + '"/>';
        } else if (cfg.zeroFloor) {
          s += '<path d="' + roundTopRect(bx, pad.t + ph - 1.5, bw, 1.5, 0) + '" fill="var(--s-zero-bar)"/>';
        }
        if (b.cap) {
          s += '<text class="s-cap-t" x="' + (bx + bw / 2) + '" y="' + (pad.t + ph - bh - 6) +
            '" text-anchor="middle">' + esc(b.cap) + '</text>';
        }
      });
      if (gr.label) {
        s += '<text class="s-axis-t" x="' + cx + '" y="' + (h - (cfg.twoLineX ? 20 : 8)) +
          '" text-anchor="middle">' + esc(gr.label) + '</text>';
      }
      if (cfg.twoLineX && gr.sub) {
        s += '<text class="s-axis-sub" x="' + cx + '" y="' + (h - 7) + '" text-anchor="middle">' +
          esc(gr.sub) + '</text>';
      }
      s += '</g>';
    });
    if (cfg.line && cfg.line.values.length) {
      var pts = [];
      var clipped = [];
      for (var li = 0; li < cfg.line.values.length && li < g; li++) {
        var lv = cfg.line.values[li];
        // 축을 넘는 값은 상단에 고정하되 그 사실을 캐럿으로 남긴다. 툴팁은 축이 아니라
        // 원본 값을 읽으므로 실제 숫자는 그대로 확인된다.
        if (lv > sc.top) { clipped.push(li); lv = sc.top; }
        pts.push(centerX(li).toFixed(1) + ',' + Y(lv).toFixed(1));
      }
      if (pts.length > 1) {
        s += '<polyline points="' + pts.join(' ') + '" fill="none" stroke="' + cfg.line.color +
          '" stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>';
      }
      clipped.forEach(function (li) {
        var cxi = centerX(li);
        var top = pad.t;
        s += '<path class="s-clip-mark" d="M' + (cxi - 4).toFixed(1) + ',' + (top + 5) +
          ' L' + cxi.toFixed(1) + ',' + top + ' L' + (cxi + 4).toFixed(1) + ',' + (top + 5) +
          ' Z" fill="' + cfg.line.color + '"><title>축 위로 넘어간 구간입니다. 값은 툴팁에서 확인하세요.</title></path>';
      });
    }
    cfg.groups.forEach(function (gr, gi) { // hit 레이어는 라인 위 — 밴드 전체가 타깃
      s += '<rect class="s-ghit" x="' + (pad.l + gi * band) + '" y="' + pad.t + '" width="' + band +
        '" height="' + ph + '" fill="transparent" tabindex="0"/>';
    });
    s += '</svg>';
    host.innerHTML = s;

    var grps = host.querySelectorAll('.s-cgrp');
    host.querySelectorAll('.s-ghit').forEach(function (hit, gi) {
      var grp = grps[gi];
      var on = function (x, y) {
        grp.classList.add('s-on');
        showTip(ctx, x, y, cfg.tipTitle(gi), cfg.tipRows(gi));
      };
      var off = function () {
        grp.classList.remove('s-on');
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

  /** 스파크라인: 회색 추세 + 현재 구간 강조 (accent = 지표 가족색). */
  function sparkSvg(values, accent) {
    var w = 92;
    var h = 30;
    var p = 3;
    var n = values.length;
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
      '<circle cx="' + X(n - 1) + '" cy="' + Y(values[n - 1]) + '" r="3" fill="' + accent +
      '" stroke="var(--s-surface)" stroke-width="1.5"/>' +
      '</svg>';
  }

  /* ═══════════════ 4. 섹션 렌더 ═══════════════ */

  /** 증감률. 비교 기준이 0/없음이면 null — "+∞%" 같은 거짓 수치를 만들지 않는다. */
  function deltaOf(cur, prev) {
    if (!isFinite(cur) || !isFinite(prev) || prev <= 0) return null;
    var pct = (cur / prev - 1) * 100;
    var flat = Math.abs(pct) < 0.05;
    return {
      text: (pct >= 0 ? '+' : '−') + Math.abs(pct).toFixed(1) + '%',
      arrow: flat ? '=' : (pct > 0 ? '▲' : '▼'),
      cls: flat ? 's-flat' : (pct > 0 ? 's-good' : 's-bad'),
    };
  }

  function appendKpi(wrap, spec) {
    var tile = document.createElement('div');
    tile.className = 's-kpi s-fam';
    tile.setAttribute('data-settlement-kpi', spec.key);
    tile.style.setProperty('--s-fam', FAM[spec.fam]);
    tile.style.setProperty('--s-fam-tint', FAM_TINT[spec.fam]);
    var label = document.createElement('div');
    label.className = 's-kpi-label';
    label.textContent = spec.label;
    tile.appendChild(label);
    var mid = document.createElement('div');
    mid.className = 's-kpi-mid';
    var value = document.createElement('span');
    value.className = 's-kpi-value';
    value.textContent = spec.value;
    var unit = document.createElement('i');
    unit.textContent = spec.unit;
    value.appendChild(unit);
    mid.appendChild(value);
    if (spec.spark && spec.spark.length > 1 && Math.max.apply(null, spec.spark) > 0) {
      var spark = document.createElement('span');
      spark.className = 's-kpi-spark';
      spark.innerHTML = sparkSvg(spec.spark, FAM[spec.fam]);
      mid.appendChild(spark);
    }
    tile.appendChild(mid);
    var delta = document.createElement('div');
    if (spec.delta) {
      delta.className = 's-kpi-delta ' + spec.delta.cls;
      delta.textContent = spec.delta.arrow + ' ' + spec.delta.text;
      var vs = document.createElement('span');
      vs.textContent = spec.vs;
      delta.appendChild(vs);
    } else {
      delta.className = 's-kpi-delta s-flat';
      delta.textContent = spec.noDelta;
    }
    tile.appendChild(delta);
    var sub = document.createElement('div');
    sub.className = 's-kpi-sub';
    sub.textContent = spec.sub;
    tile.appendChild(sub);
    wrap.appendChild(tile);
  }

  function renderKpis(ctx) {
    var data = ctx.state.data;
    var wrap = ctx.els.kpis;
    if (!wrap) return;
    clear(wrap);
    var kpi = data.kpi || {};
    var buckets = data.buckets || [];
    var prev = data.prev_buckets || [];
    var prevRevenue = sum(prev, function (b) { return b.revenue; });
    var prevCount = sum(prev, function (b) { return b.count; });
    var prevAvg = prevCount ? prevRevenue / prevCount : 0;
    var vs = 'vs ' + (ctx.state.gran === 'month' ? '이전 동일 기간' : '전월');
    var overpaid = kpi.overpaid_total || 0;

    appendKpi(wrap, {
      key: 'revenue', label: '기간 매출', value: fmtMan(toMan(kpi.revenue)), unit: '원', fam: 'rev',
      delta: deltaOf(kpi.revenue || 0, prevRevenue), vs: vs,
      noDelta: '비교 기준 기간에 매출 없음',
      sub: '완료일 기준 · ' + fmtCount(kpi.completed_count) + '건',
      spark: buckets.map(function (b) { return toMan(b.revenue); }),
    });
    appendKpi(wrap, {
      key: 'receivable', label: '미수금 잔액', value: fmtMan(toMan(kpi.receivable_total)), unit: '원', fam: 'ar',
      delta: null, noDelta: '시점 잔액 — 기간 비교 없음',
      sub: fmtCount(kpi.receivable_count) + '건 · 잔금 입금 미확인 · 기간 무관 전체',
    });
    appendKpi(wrap, {
      key: 'completed', label: '완료 건수', value: fmtCount(kpi.completed_count), unit: '건', fam: 'vol',
      delta: deltaOf(kpi.completed_count || 0, prevCount), vs: vs,
      noDelta: '비교 기준 기간에 완료 건 없음',
      sub: '완료 · AS접수 · AS완료',
      spark: buckets.map(function (b) { return b.count || 0; }),
    });
    appendKpi(wrap, {
      key: 'avg', label: '평균 출고가', value: fmtMan(toMan(kpi.avg_shipping_price)), unit: '원', fam: 'rev',
      delta: deltaOf(kpi.avg_shipping_price || 0, prevAvg), vs: vs,
      noDelta: '비교 기준 기간에 완료 건 없음',
      sub: '출고가 = 품목합 + 배송 − 할인',
    });
    appendKpi(wrap, {
      key: 'collected', label: '기간 수금(근사)', value: fmtMan(toMan(kpi.collected_approx)), unit: '원', fam: 'col',
      delta: null, noDelta: '입금 확인 토글 기반 근사 — 기간 비교 없음',
      // 과입금은 잔금 0 클램프가 삼키는 금액이다. 0 이면 줄을 내지 않는다.
      sub: overpaid > 0
        ? '예약금 + 잔금확인분 · 과입금 ' + fmtWon(overpaid) + ' 별도'
        : '예약금 + 잔금확인분',
    });
  }

  function mainSeries(ctx) {
    var data = ctx.state.data;
    var cur = (data.buckets || []).map(function (b) { return toMan(b.revenue); });
    var prev = (data.prev_buckets || []).map(function (b) { return toMan(b.revenue); });
    return { cur: cur, prev: prev };
  }

  function renderLegend(ctx, els, mode) {
    var lg = els.legend;
    if (!lg) return;
    clear(lg);
    if (mode === 'none') return;
    // 목업과 같은 축약형("8월(당월)"/"7월(전월)"). 긴 형식은 스와치 4개가 붙는
    // bucketcmp 모드에서 범례가 두 줄로 접혀 카드 헤드 높이가 밀린다.
    var curMonth = shortMonthLabel(ctx.state.month);
    var prevMonth = shortMonthLabel(shiftMonth(ctx.state.month, -1));
    var curLabel = curMonth ? curMonth + '(당월)' : '당월';
    var prevLabel = prevMonth ? prevMonth + '(전월)' : '전월';
    function mk(color, label, keyCls) {
      var span = document.createElement('span');
      span.className = 's-lg';
      var key = document.createElement('i');
      key.className = keyCls;
      key.style.setProperty('background', color);
      span.appendChild(key);
      span.appendChild(document.createTextNode(label));
      return span;
    }
    // 범례 키는 마크를 그대로 반영: 막대=사각 스와치, 라인=선 키.
    if (mode === 'bucket' || mode === 'bucketcmp') {
      BUCKET_LABELS.forEach(function (lb, i) { lg.appendChild(mk(BLUE_BUCKET4[i], lb, 's-lg-rect')); });
      if (mode === 'bucketcmp') lg.appendChild(mk(CTX, prevLabel, 's-lg-line'));
      return;
    }
    lg.appendChild(mk(ACCENT, curLabel, mode === 'line' ? 's-lg-line' : 's-lg-rect'));
    lg.appendChild(mk(CTX, prevLabel, 's-lg-line'));
  }

  function renderMainTable(ctx, els, cmp) {
    var table = els.table;
    if (!table) return;
    clear(table);
    var data = ctx.state.data;
    var buckets = data.buckets || [];
    var prev = data.prev_buckets || [];
    var thead = document.createElement('thead');
    var tbody = document.createElement('tbody');
    var headRow = document.createElement('tr');
    var headers = cmp ? ['구간', '매출 (만원)', '건수', '이전 구간 (만원)'] : ['구간', '매출 (만원)', '건수'];
    headers.forEach(function (text) {
      var th = document.createElement('th');
      th.textContent = text;
      headRow.appendChild(th);
    });
    buckets.forEach(function (b, i) {
      var cells = [b.label, toMan(b.revenue).toLocaleString('ko-KR'), fmtCount(b.count)];
      if (cmp) cells.push(prev[i] ? toMan(prev[i].revenue).toLocaleString('ko-KR') : '—');
      var tr = document.createElement('tr');
      cells.forEach(function (c) {
        var td = document.createElement('td');
        td.textContent = c;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);
    table.appendChild(tbody);
  }

  function renderMainChart(ctx, els) {
    var state = ctx.state;
    var data = state.data;
    var host = els.chart;
    if (!host) return;
    var buckets = data.buckets || [];
    var prevBuckets = data.prev_buckets || [];
    var totalCount = sum(buckets, function (b) { return b.count; });
    var empty = buckets.length === 0 || (totalCount === 0 && sum(buckets, function (b) { return b.revenue; }) === 0);
    toggle(els.empty, !empty);
    toggle(els.tableWrap, empty);
    if (empty) {
      clear(host);
      renderLegend(ctx, els, 'none');
      if (els.sub) els.sub.textContent = '완료일 기준 · 이 기간에 집계할 매출이 없습니다';
      return;
    }

    var cmp = state.cmp && state.gran !== 'month' && prevBuckets.length > 0;
    var series = mainSeries(ctx);
    var granWord = state.gran === 'day' ? '일별' : (state.gran === 'week' ? '주별' : '월별');
    // 목업 부제: "8월 일별(막대) vs 7월 동일자(라인) · 완료일 기준" / 누적은 "8월 누적 vs 7월 누적".
    var curWord = shortMonthLabel(state.month);
    var prevMonthWord = shortMonthLabel(shiftMonth(state.month, -1)) || '전월';
    var prevWord = prevMonthWord +
      (state.gran === 'day' ? ' 동일자' : (state.gran === 'week' ? ' 동주차' : ''));
    // 누적(라인) 축도 목업과 같은 "1일" 표기를 쓴다 — 막대 축과 어긋나면 토글할 때 축이 바뀐다.
    var xLabelOf = function (i) {
      if (!buckets[i]) return '';
      return state.gran === 'day' ? dayLabel(buckets[i].label) : buckets[i].label;
    };
    var tipTitleOf = function (i) { return (buckets[i] ? buckets[i].label : '') + ' · 완료일 기준'; };
    var prevRow = function (i) {
      if (!cmp || !prevBuckets[i]) return null;
      return { color: CTX, val: fmtMan(series.prev[i]), lbl: prevBuckets[i].label + '(이전)' };
    };

    if (state.gran === 'day' && state.cum) {
      // 누적 = 영역 라인차트 (순증=막대, 누적=영역)
      var curCum = cumsum(series.cur);
      var prevCum = cumsum(series.prev);
      if (els.sub) {
        var cumHead = curWord ? curWord + ' 누적' : granWord + ' 누적';
        els.sub.textContent = cmp
          ? cumHead + ' vs ' + prevMonthWord + ' 누적 · 완료일 기준'
          : cumHead + ' · 완료일 기준';
      }
      renderLegend(ctx, els, cmp ? 'line' : 'none');
      var lineSeries = [];
      if (cmp) lineSeries.push({ color: CTX, values: prevCum });
      lineSeries.push({ color: ACCENT, values: curCum, endDot: true, area: true });
      lineChart(ctx, host, {
        height: trendChartHeight(), tickCount: 5,
        aria: '누적 출고가 매출' + (cmp ? ' — 이전 구간과 비교' : ''),
        series: lineSeries,
        xLabel: xLabelOf,
        xTick: function (i, n) { return i % 5 === 0 || i === n - 1; },
        tipTitle: function (i) { return tipTitleOf(i) + ' · 누적'; },
        tipRows: function (i) {
          var rows = [{ color: ACCENT, val: fmtMan(curCum[i]), lbl: '누적' }];
          if (cmp && prevCum[i] != null) rows.push({ color: CTX, val: fmtMan(prevCum[i]), lbl: '이전 누적' });
          return rows;
        },
      });
      renderMainTable(ctx, els, cmp);
      return;
    }

    // 목업의 분기 기준은 granularity 다(일별=금액구간 램프·캡 없음, 주/월별=단색·캡 있음).
    // 버킷 수로 가르면 범위 UI 가 붙어 13주 이상을 볼 때 주별 차트가 조용히 램프로 바뀐다.
    var dense = state.gran === 'day';
    if (els.sub) {
      // 월별은 당월이 아니라 최근 N개월을 본다(buildUrl 이 6개월을 요청한다) — 목업과 같이
      // 구간 길이를 말한다. 일/주별만 "8월 일별" 처럼 당월을 앞에 붙인다.
      var head = state.gran === 'month'
        ? '최근 ' + buckets.length + '개월'
        : (curWord ? curWord + ' ' + granWord : granWord);
      els.sub.textContent = cmp
        ? head + '(막대) vs ' + prevWord + '(라인) · 완료일 기준'
        : head + ' · 완료일 기준';
    }
    renderLegend(ctx, els, dense ? (cmp ? 'bucketcmp' : 'bucket') : (cmp ? 'barline' : 'none'));
    var groups = buckets.map(function (b, i) {
      var v = series.cur[i];
      return {
        // 일별 31개는 라벨이 겹친다 — 목업과 같이 5칸마다·마지막만 낸다.
        label: dense ? ((i % 5 === 0 || i === buckets.length - 1) ? dayLabel(b.label) : '') : b.label,
        bars: [{
          name: b.label,
          color: dense ? bucketColor(v) : ACCENT,
          // 목업은 주별 캡이 fmtMan("8,240만"), 월별 캡이 fmtTick("1.2억") 이다.
          v: v,
          cap: dense ? '' : (state.gran === 'week' ? fmtMan(v) : fmtTick(v)),
        }],
      };
    });
    columnChart(ctx, host, {
      height: trendChartHeight(), caps: !dense, tickCount: 4, zeroFloor: true,
      aria: '출고가 매출 ' + granWord + (cmp ? ' — 막대는 이번 구간, 라인은 이전 구간' : ''),
      groups: groups,
      line: cmp ? { color: CTX, values: series.prev } : null,
      tipTitle: tipTitleOf,
      tipRows: function (i) {
        var rows = [
          { color: dense ? bucketColor(series.cur[i]) : ACCENT, val: fmtMan(series.cur[i]), lbl: '매출' },
          { val: fmtCount(buckets[i].count) + '건', lbl: '완료' },
        ];
        var pr = prevRow(i);
        if (pr) rows.push(pr);
        return rows;
      },
    });
    renderMainTable(ctx, els, cmp);
  }

  /** 완료일 미상 각주 — 어느 기간 버킷에도 못 들어가는 건이라 암묵 drop 을 금지한다. */
  function renderUnknownCompletion(ctx, node) {
    if (!node) return;
    var unknown = ctx.state.data.unknown_completion || {};
    var count = unknown.count || 0;
    toggle(node, count === 0);
    if (count === 0) return;
    node.textContent = '완료일 미상 ' + fmtCount(count) + '건 · ' + fmtWon(unknown.amount || 0) +
      ' — 완료일이 없어 어느 기간 버킷에도 들어가지 않습니다(위 매출 합계에서 제외).';
  }

  function renderAging(ctx) {
    var data = ctx.state.data;
    var rows = data.aging || [];
    var unknown = data.aging_unknown || {};
    var bucketCount = sum(rows, function (r) { return r.count; });
    var host = ctx.els.agingChart;

    toggle(ctx.els.emptyAging, bucketCount > 0);
    if (bucketCount === 0) {
      clear(host);
      toggle(ctx.els.agingCritical, true);
    } else {
      var groups = rows.map(function (r, i) {
        return {
          label: r.label,
          sub: fmtCount(r.count) + '건',
          bars: [{ name: r.label, color: ORANGE_RAMP5[i % ORANGE_RAMP5.length], v: toMan(r.amount), cap: fmtTick(toMan(r.amount)) }],
        };
      });
      // 실데이터는 91일+ 한 버킷에 압도적으로 쏠린다. 최대값 스케일이면 나머지가 실선처럼 보이므로
      // (a) 모든 막대에 값 캡을 달고 (b) 0 아닌 막대에 3px 하한을 둔다(columnChart 주석 참고).
      columnChart(ctx, host, {
        height: AGING_CHART_HEIGHT, caps: true, twoLineX: true, tickCount: 3,
        aria: '미수금 aging 5구간 — 경과일이 길수록 진한 주황',
        groups: groups,
        tipTitle: function (gi) { return '경과 ' + rows[gi].label; },
        tipRows: function (gi) {
          return [
            { color: ORANGE_RAMP5[gi % ORANGE_RAMP5.length], val: fmtWon(rows[gi].amount), lbl: '미수 잔금' },
            { val: fmtCount(rows[gi].count) + '건', lbl: '주문 수' },
          ];
        },
      });
      var critical = rows[rows.length - 1];
      var hasCritical = !!(critical && critical.count > 0);
      toggle(ctx.els.agingCritical, !hasCritical);
      if (hasCritical && ctx.els.agingCriticalText) {
        ctx.els.agingCriticalText.textContent = critical.label + ' 장기 미수 ' + fmtCount(critical.count) +
          '건 · ' + fmtWon(critical.amount) + ' — 우선 회수 대상';
      }
    }

    var unknownCount = unknown.count || 0;
    toggle(ctx.els.agingUnknown, unknownCount === 0);
    if (unknownCount > 0) {
      ctx.els.agingUnknown.textContent = '완료일 미상 미수 ' + fmtCount(unknownCount) + '건 · ' +
        fmtWon(unknown.amount || 0) + ' — 경과일을 산출할 수 없어 위 버킷 밖에서 따로 셉니다.';
    }
    if (ctx.els.agingSub) {
      ctx.els.agingSub.textContent = '잔금 입금 미확인 ' +
        fmtCount((ctx.state.data.kpi || {}).receivable_count) + '건 · 기간 무관 전체';
    }
  }

  function factRow(dot, text, tail) {
    var row = document.createElement('div');
    row.className = 's-fact';
    var icon = document.createElement('i');
    icon.className = 's-fdot';
    icon.style.setProperty('--s-dot', dot);
    row.appendChild(icon);
    var span = document.createElement('span');
    span.textContent = text;
    row.appendChild(span);
    if (tail) {
      var tailEl = document.createElement('span');
      tailEl.className = 's-tail';
      tailEl.textContent = tail;
      row.appendChild(tailEl);
    }
    return row;
  }

  function renderSettlementStatus(ctx) {
    var data = ctx.state.data;
    var st = data.settlement_status || {};
    var base = (data.kpi || {}).completed_count || 0;
    var body = ctx.els.statusBody;
    if (!body) return;
    clear(body);
    var issued = st.issued_count || 0;
    var pending = st.pending_count || 0;
    var deductions = (st.deductions_by_department || []).filter(function (d) { return (d.amount || 0) > 0; });
    var deductionTotal = sum(st.deductions_by_department, function (d) { return d.amount; });
    var allZero = issued === 0 && (st.cash_receipt_requested || 0) === 0 &&
      (st.cash_receipt_issued || 0) === 0 && (st.as_billing_paid_count || 0) === 0 && deductionTotal === 0;

    if (ctx.els.statusSub) ctx.els.statusSub.textContent = '기간 완료 ' + fmtCount(base) + '건 기준';
    toggle(ctx.els.emptySettlement, !allZero);

    if (base === 0) {
      var note = document.createElement('div');
      note.className = 's-srow-sub';
      note.textContent = '이 기간에 완료된 주문이 없어 정산 처리 대상도 없습니다.';
      body.appendChild(note);
      return;
    }

    var pct = base > 0 ? (issued / base) * 100 : 0;
    var srow = document.createElement('div');
    srow.className = 's-srow';
    var label = document.createElement('span');
    label.textContent = '청구완료 ';
    var strong = document.createElement('b');
    strong.textContent = fmtCount(issued) + '건';
    label.appendChild(strong);
    srow.appendChild(label);
    var meter = document.createElement('div');
    meter.className = 's-meter';
    meter.setAttribute('role', 'img');
    meter.setAttribute('aria-label', '청구완료 ' + pct.toFixed(1) + '%');
    var fill = document.createElement('div');
    fill.className = 's-meter-fill';
    fill.style.setProperty('--s-meter-pct', pct.toFixed(1) + '%');
    meter.appendChild(fill);
    srow.appendChild(meter);
    var pctEl = document.createElement('span');
    pctEl.className = 's-pct';
    pctEl.textContent = pct.toFixed(1) + '%';
    srow.appendChild(pctEl);
    body.appendChild(srow);

    var sub = document.createElement('div');
    sub.className = 's-srow-sub';
    sub.textContent = '청구 대기 ' + fmtCount(pending) + '건';
    body.appendChild(sub);

    body.appendChild(factRow('#fab219',
      '현금영수증 발행 대기 ' + fmtCount(st.cash_receipt_requested) + '건',
      '발행 완료 ' + fmtCount(st.cash_receipt_issued) + '건'));
    body.appendChild(factRow(ACCENT,
      'AS 유상 확정 ' + fmtCount(st.as_billing_paid_count) + '건 · ' + fmtWon(st.as_billing_paid_amount || 0)));
    body.appendChild(factRow('#9aa3af',
      '부서 귀속 차감 계 ' + fmtWon(deductionTotal),
      deductions.length
        ? deductions.map(function (d) { return d.label + ' ' + fmtMan(toMan(d.amount)); }).join(' · ')
        : '차감 기록 없음'));
  }

  function renderStages(ctx) {
    var stages = ctx.state.data.stages || [];
    var wrap = ctx.els.stages;
    if (!wrap) return;
    clear(wrap);
    toggle(ctx.els.emptyStages, stages.length > 0);
    if (!stages.length) return;
    var maxAmount = Math.max.apply(null, stages.map(function (s) { return s.amount || 0; }).concat([0]));
    var maxCount = Math.max.apply(null, stages.map(function (s) { return s.count || 0; }).concat([0]));
    // 출고가가 아직 안 잡힌 단계(품목 미입력)만 있으면 금액 축이 전부 0 이라 막대가 사라진다.
    // 그때는 건수로 폭을 잡고 값 텍스트가 사실을 말한다.
    var useAmount = maxAmount > 0;
    stages.forEach(function (st) {
      var row = document.createElement('div');
      row.className = 's-stage-row';
      row.setAttribute('data-settlement-stage', st.stage || '');
      var label = document.createElement('span');
      label.className = 's-stage-lbl';
      label.textContent = st.label || st.stage || '';   // 라벨 SSOT = API(STAGE_LABELS)
      row.appendChild(label);
      var track = document.createElement('div');
      track.className = 's-stage-track';
      var bar = document.createElement('div');
      bar.className = 's-stage-bar';
      var ratio = useAmount
        ? (st.amount || 0) / maxAmount
        : (maxCount ? (st.count || 0) / maxCount : 0);
      bar.style.setProperty('--s-bar-pct', (ratio * 62).toFixed(2) + '%');
      track.appendChild(bar);
      var value = document.createElement('span');
      value.className = 's-stage-val';
      value.textContent = fmtMan(toMan(st.amount)) + ' ';
      var count = document.createElement('span');
      count.textContent = '· ' + fmtCount(st.count) + '건';
      value.appendChild(count);
      track.appendChild(value);
      row.appendChild(track);
      row.addEventListener('pointermove', function (e) {
        var per = st.count ? Math.round((st.amount || 0) / st.count) : 0;
        showTip(ctx, e.clientX, e.clientY, (st.label || st.stage) + ' 단계', [
          { color: ACCENT, val: fmtWon(st.amount || 0), lbl: '물린 금액' },
          { val: fmtCount(st.count) + '건', lbl: '진행 주문' },
          { val: fmtWon(per), lbl: '건당 평균' },
        ]);
      });
      row.addEventListener('pointerleave', function () { hideTip(ctx); });
      wrap.appendChild(row);
    });
  }

  function renderChannels(ctx) {
    var channels = ctx.state.data.channels || [];
    var bar = ctx.els.channelBar;
    var legend = ctx.els.channelLegend;
    if (!bar || !legend) return;
    clear(bar);
    clear(legend);
    var totalRevenue = sum(channels, function (c) { return c.revenue; });
    var totalCount = sum(channels, function (c) { return c.count; });
    var empty = totalRevenue === 0 && totalCount === 0;
    toggle(ctx.els.emptyChannels, !empty);
    if (ctx.els.channelSub) {
      ctx.els.channelSub.textContent = totalRevenue > 0 ? '기간 · 출고가 기준' : '기간 · 건수 기준(매출 0원)';
    }
    if (empty) return;

    // 매출이 0 이면 비중을 건수로 잡는다. 실데이터는 '일반' 단일 조각(100%)이라
    // 조각이 하나여도 막대·범례가 깨지지 않아야 한다.
    var basisTotal = totalRevenue > 0 ? totalRevenue : totalCount;
    var pickBasis = function (c) { return totalRevenue > 0 ? (c.revenue || 0) : (c.count || 0); };
    channels.forEach(function (ch, i) {
      var value = pickBasis(ch);
      var pct = basisTotal > 0 ? (value / basisTotal) * 100 : 0;
      var color = channelColor(ch.channel, i);
      if (pct > 0) {
        var seg = document.createElement('div');
        seg.className = 's-chseg';
        seg.setAttribute('data-settlement-channel', ch.channel || '');
        seg.style.setProperty('--s-seg-pct', pct.toFixed(2) + '%');
        seg.style.setProperty('--s-seg-color', color);
        // 조각이 좁으면 안쪽 글자가 잘린다 — 그때는 범례가 값을 말한다.
        seg.textContent = pct >= 10 ? Math.round(pct) + '%' : '';
        seg.addEventListener('pointermove', function (e) {
          showTip(ctx, e.clientX, e.clientY, (ch.channel || '미상') + ' 채널', [
            { color: color, val: fmtWon(ch.revenue || 0), lbl: '매출' },
            { val: fmtCount(ch.count) + '건', lbl: '완료 주문' },
            { val: pct.toFixed(1) + '%', lbl: '비중' },
          ]);
        });
        seg.addEventListener('pointerleave', function () { hideTip(ctx); });
        bar.appendChild(seg);
      }
      var row = document.createElement('div');
      row.className = 's-chrow';
      var swatch = document.createElement('i');
      swatch.className = 's-sw';
      swatch.style.setProperty('--s-sw-color', color);
      row.appendChild(swatch);
      var name = document.createElement('b');
      name.textContent = ch.channel || '미상';
      row.appendChild(name);
      row.appendChild(document.createTextNode(
        fmtWon(ch.revenue || 0) + ' · ' + fmtCount(ch.count) + '건 · ' + pct.toFixed(1) + '%'
      ));
      legend.appendChild(row);
    });
  }

  function renderRangeLine(ctx) {
    var range = ctx.state.data.range || {};
    var node = ctx.els.rangeLine;
    if (!node) return;
    var from = monthLabel(range.month_from);
    var to = monthLabel(range.month_to);
    var scope = from && to && from !== to ? from + ' ~ ' + to : (to || from || '');
    var cmpTarget = monthLabel(shiftMonth(range.month_from, -1));
    node.textContent = ctx.state.gran === 'month' || !cmpTarget
      ? scope
      : scope + ' · 비교 대상 ' + cmpTarget;
    if (ctx.els.stamp) ctx.els.stamp.textContent = kstStamp();
  }

  /* ═══════════════ 4.5 탭 3 · 분석 ═══════════════
   *
   * 요약 탭이 못 보여주는 축만 맡는다: 채널 3지표 · 담당자별 · 단계별 · 부서별 차감 ·
   * 수금 구성(예약금/잔금) · AS 청구 분포. 매출 추이 카드는 **일부러 복제하지 않는다**
   * (요약 탭이 같은 buckets/prev_buckets 를 같은 기간 스코프로 이미 그린다 — 템플릿 주석).
   *
   * 데이터는 요약과 **같은 한 번의 fetch** 결과(ctx.state.data)를 읽고, 렌더 진입점도
   * renderAll 하나다(탭 활성화·리사이즈가 그 경로로 들어온다).
   */

  /**
   * 집계 막대(담당자별·단계별)용 금액 램프의 경계.
   *
   * `BUCKET_EDGES`(450/700/900만)는 **주문 한 건**의 출고가에 맞춘 경계라 합계 축에 그대로
   * 쓰면 안 된다 — 실측(2026-08-31 dev 5011 시드): 담당자 7명이 1,120만~1,808만이라 전원이
   * 최상단 색으로 칠해져 램프가 아무 말도 하지 않는다. 그래서 **그 시리즈 최댓값의 4분위**로
   * 경계를 새로 잡고, 범례 문구도 그 경계에서 생성한다(고정 문구를 적으면 색과 글자가 갈린다).
   */
  var AGG_RAMP_QUARTILES = [0.25, 0.5, 0.75];

  /** 시리즈 최댓값(만원) → 4분위 경계 3개. 최댓값이 0 이하면 램프 자체가 의미 없어 null. */
  function aggEdges(maxMan) {
    if (!(maxMan > 0)) return null;
    return AGG_RAMP_QUARTILES.map(function (ratio) { return Math.round(maxMan * ratio); });
  }

  /** 금액(만원) → 램프 색. 경계가 없으면(전부 0) 단색으로 떨어뜨린다. */
  function aggColor(man, edges) {
    if (!edges) return ACCENT;
    for (var i = 0; i < edges.length; i++) {
      if (man < edges[i]) return BLUE_BUCKET4[i];
    }
    return BLUE_BUCKET4[BLUE_BUCKET4.length - 1];
  }

  /** 램프 범례를 경계에서 생성한다 — 색 칸과 글자가 같은 숫자에서 나온다. */
  function renderRampLegend(host, edges) {
    if (!host) return;
    clear(host);
    if (!edges) return;
    var labels = [
      fmtMan(edges[0]) + ' 미만',
      fmtMan(edges[0]) + '~' + fmtMan(edges[1]),
      fmtMan(edges[1]) + '~' + fmtMan(edges[2]),
      fmtMan(edges[2]) + ' 이상',
    ];
    labels.forEach(function (label, i) {
      var span = document.createElement('span');
      span.className = 's-lg';
      var key = document.createElement('i');
      key.className = 's-lg-rect';
      key.style.setProperty('--s-lg-color', BLUE_BUCKET4[i]);
      span.appendChild(key);
      span.appendChild(document.createTextNode(label));
      host.appendChild(span);
    });
  }

  /**
   * 가로 막대 리스트(담당자·단계·부서·aging 공용).
   *
   * 폭은 CSS 퍼센트(`--s-bar-pct`)라 호스트 `clientWidth` 를 읽지 않는다 — 숨은 pane 에서
   * 그려도 눌리지 않는다(SVG 차트와 다른 점). 최댓값 막대가 트랙을 꽉 채우지 않도록 92% 를
   * 상한으로 두어 값 텍스트와 붙지 않게 한다.
   *
   * @param {object} ctx 마운트 컨텍스트.
   * @param {Element} host 막대를 담을 컨테이너.
   * @param {Array} items [{label, amount(원), count, color, tipTitle, tipRows}].
   */
  function renderBarList(ctx, host, items) {
    if (!host) return;
    clear(host);
    var maxAmount = Math.max.apply(null, items.map(function (it) { return it.amount || 0; }).concat([0]));
    items.forEach(function (item) {
      var row = document.createElement('div');
      row.className = 's-brow';
      var label = document.createElement('span');
      label.className = 's-blab';
      label.textContent = item.label;
      row.appendChild(label);
      var track = document.createElement('div');
      track.className = 's-btrack';
      var bar = document.createElement('div');
      bar.className = 's-bbar';
      var ratio = maxAmount > 0 ? (item.amount || 0) / maxAmount : 0;
      bar.style.setProperty('--s-bar-pct', (ratio * 92).toFixed(2) + '%');
      bar.style.setProperty('--s-bar-color', item.color);
      track.appendChild(bar);
      row.appendChild(track);
      var value = document.createElement('span');
      value.className = 's-bval';
      value.textContent = fmtMan(toMan(item.amount)) + ' ';
      var count = document.createElement('span');
      count.textContent = '· ' + fmtCount(item.count) + '건';
      value.appendChild(count);
      row.appendChild(value);
      if (item.tipRows) {
        row.addEventListener('pointermove', function (e) {
          showTip(ctx, e.clientX, e.clientY, item.tipTitle, item.tipRows);
        });
        row.addEventListener('pointerleave', function () { hideTip(ctx); });
      }
      host.appendChild(row);
    });
  }

  /** 스탯 상자 하나(수금 구성·AS 3분할 공용). */
  function statBox(spec) {
    var box = document.createElement('div');
    box.className = 's-dbox' + (spec.family ? ' s-dbox--' + spec.family : '');
    var label = document.createElement('div');
    label.className = 's-dbox-label';
    label.textContent = spec.label;
    box.appendChild(label);
    var value = document.createElement('div');
    value.className = 's-dbox-val';
    value.textContent = spec.value;
    if (spec.unit) {
      var unit = document.createElement('i');
      unit.textContent = spec.unit;
      value.appendChild(unit);
    }
    box.appendChild(value);
    if (spec.sub) {
      var sub = document.createElement('div');
      sub.className = 's-dbox-sub';
      sub.textContent = spec.sub;
      box.appendChild(sub);
    }
    return box;
  }

  /** 비율 미터 한 줄(라벨 + 퍼센트 + 트랙). 분모 0 이면 0% 로 그리되 문구가 분모를 말한다. */
  function meterRow(text, pct) {
    var wrap = document.createElement('div');
    wrap.className = 's-mrow';
    var lab = document.createElement('div');
    lab.className = 's-mlab';
    var left = document.createElement('span');
    left.textContent = text;
    lab.appendChild(left);
    var right = document.createElement('span');
    var strong = document.createElement('b');
    strong.textContent = pct.toFixed(1) + '%';
    right.appendChild(strong);
    lab.appendChild(right);
    wrap.appendChild(lab);
    var meter = document.createElement('div');
    meter.className = 's-meter';
    meter.setAttribute('role', 'img');
    meter.setAttribute('aria-label', text + ' ' + pct.toFixed(1) + '%');
    var fill = document.createElement('div');
    fill.className = 's-meter-fill';
    fill.style.setProperty('--s-meter-pct', Math.max(0, Math.min(100, pct)).toFixed(1) + '%');
    meter.appendChild(fill);
    wrap.appendChild(meter);
    return wrap;
  }

  /** 차감처럼 **늘어나는 게 나쁜** 지표의 델타 색을 뒤집는다(수치·화살표는 그대로). */
  function invertDelta(delta) {
    if (!delta) return delta;
    var cls = delta.cls === 's-good' ? 's-bad' : (delta.cls === 's-bad' ? 's-good' : delta.cls);
    return { text: delta.text, arrow: delta.arrow, cls: cls };
  }

  function deductionTotalOf(data) {
    return sum((data.settlement_status || {}).deductions_by_department, function (d) { return d.amount; });
  }

  function renderAnalyticsKpis(ctx) {
    var data = ctx.state.data;
    var wrap = ctx.els.anKpis;
    if (!wrap) return;
    clear(wrap);
    var kpi = data.kpi || {};
    // 이전 구간 스칼라는 서버가 준다(prev_totals). 화면이 직접 만들어 내지 않는다.
    var prev = data.prev_totals || {};
    var buckets = data.buckets || [];
    var vs = 'vs ' + (ctx.state.gran === 'month' ? '이전 동일 기간' : '전월');
    var deduction = deductionTotalOf(data);

    appendKpi(wrap, {
      key: 'an-revenue', label: '매출 (출고가 · 완료일 기준)', value: fmtMan(toMan(kpi.revenue)), unit: '원', fam: 'rev',
      delta: deltaOf(kpi.revenue || 0, prev.revenue || 0), vs: vs,
      noDelta: '비교 기준 기간에 매출 없음',
      sub: '완료일 기준 · ' + fmtCount(kpi.completed_count) + '건',
      spark: buckets.map(function (b) { return toMan(b.revenue); }),
    });
    appendKpi(wrap, {
      key: 'an-completed', label: '완료 건수', value: fmtCount(kpi.completed_count), unit: '건', fam: 'vol',
      delta: deltaOf(kpi.completed_count || 0, prev.completed_count || 0), vs: vs,
      noDelta: '비교 기준 기간에 완료 건 없음',
      sub: '이전 구간 ' + fmtCount(prev.completed_count) + '건',
      spark: buckets.map(function (b) { return b.count || 0; }),
    });
    appendKpi(wrap, {
      key: 'an-avg', label: '평균 출고가', value: fmtMan(toMan(kpi.avg_shipping_price)), unit: '원', fam: 'rev',
      delta: deltaOf(kpi.avg_shipping_price || 0, prev.avg_shipping_price || 0), vs: vs,
      noDelta: '비교 기준 기간에 완료 건 없음',
      sub: '이전 구간 ' + fmtWon(prev.avg_shipping_price || 0),
    });
    appendKpi(wrap, {
      // 차감은 늘수록 나쁘다 — 증감 색만 뒤집는다(수치는 deltaOf 그대로).
      key: 'an-deduction', label: '부서 차감 합계', value: fmtMan(toMan(deduction)), unit: '원', fam: 'ar',
      delta: invertDelta(deltaOf(deduction, prev.deduction_total || 0)), vs: vs,
      noDelta: '이전 구간에 차감 기록 없음',
      sub: '기간 완료 건에 기록된 귀속 차감',
    });
  }

  function renderAnalyticsChannels(ctx) {
    var channels = ctx.state.data.channels || [];
    var bar = ctx.els.anChannelBar;
    var table = ctx.els.anChannelTable;
    if (!bar || !table) return;
    clear(bar);
    clear(table);
    var totalRevenue = sum(channels, function (c) { return c.revenue; });
    var totalCount = sum(channels, function (c) { return c.count; });
    var empty = totalRevenue === 0 && totalCount === 0;
    toggle(ctx.els.emptyAnChannels, !empty);
    toggle(ctx.els.anChannelTableWrap, empty);
    if (ctx.els.anChannelSub) {
      ctx.els.anChannelSub.textContent = totalRevenue > 0
        ? '기간 · 출고가 기준 · 채널 ' + fmtCount(channels.length) + '종'
        : '기간 · 건수 기준(매출 0원)';
    }
    if (empty) return;

    var basisTotal = totalRevenue > 0 ? totalRevenue : totalCount;
    channels.forEach(function (ch, i) {
      var value = totalRevenue > 0 ? (ch.revenue || 0) : (ch.count || 0);
      var pct = basisTotal > 0 ? (value / basisTotal) * 100 : 0;
      var color = channelColor(ch.channel, i);
      if (pct > 0) {
        var seg = document.createElement('div');
        seg.className = 's-chseg';
        seg.setAttribute('data-settlement-channel', ch.channel || '');
        seg.style.setProperty('--s-seg-pct', pct.toFixed(2) + '%');
        seg.style.setProperty('--s-seg-color', color);
        seg.textContent = pct >= 10 ? Math.round(pct) + '%' : '';
        bar.appendChild(seg);
      }
    });

    var thead = document.createElement('thead');
    var headRow = document.createElement('tr');
    ['채널', '매출', '건수', '건당 평균'].forEach(function (text) {
      var th = document.createElement('th');
      th.textContent = text;
      headRow.appendChild(th);
    });
    thead.appendChild(headRow);
    table.appendChild(thead);
    var tbody = document.createElement('tbody');
    channels.forEach(function (ch) {
      var count = ch.count || 0;
      // 건당 평균은 0 건에서 정의되지 않는다 — `_build_channels` 는 데이터가 없어도 '일반'
      // 행을 항상 내므로(0건 0원) 나누기 전에 반드시 막는다.
      var per = count > 0 ? Math.round((ch.revenue || 0) / count) : null;
      var cells = [
        ch.channel || '미상',
        fmtMan(toMan(ch.revenue)),
        fmtCount(count),
        per === null ? '—' : fmtMan(toMan(per)),
      ];
      var tr = document.createElement('tr');
      cells.forEach(function (text) {
        var td = document.createElement('td');
        td.textContent = text;
        tr.appendChild(td);
      });
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
  }

  /**
   * 담당자별 매출 — **ADMIN·MANAGER 전용**(SPEC §13.6).
   *
   * 서버가 권한 밖 사용자에게는 `managers`/`managers_total` **키 자체를 payload 에서 뺀다**.
   * 그래서 여기서 보는 것은 "값이 0" 이 아니라 "키가 없음" 이다 — 빈 카드를 그리거나
   * `data.managers.length` 로 던지지 않고 **카드째 감춘다**. 값이 없는 카드가 남으면
   * STAFF 는 "실적이 0" 으로 오해하고, 던지면 뒤따르는 카드가 통째로 안 그려진다.
   */
  function renderAnalyticsManagers(ctx) {
    var data = ctx.state.data;
    var card = ctx.els.anManagerCard;
    if (!card) return;
    var granted = Object.prototype.hasOwnProperty.call(data, 'managers') && Array.isArray(data.managers);
    toggle(card, !granted);
    if (!granted) return;

    var managers = data.managers;
    var total = data.managers_total || {};
    var host = ctx.els.anManagers;
    var empty = managers.length === 0;
    toggle(ctx.els.emptyManagers, !empty);
    if (ctx.els.anManagerTotal) toggle(ctx.els.anManagerTotal, empty);
    if (empty) {
      clear(host);
      renderRampLegend(ctx.els.anManagerLegend, null);
      return;
    }

    var maxMan = Math.max.apply(null, managers.map(function (m) { return toMan(m.revenue); }).concat([0]));
    var edges = aggEdges(maxMan);
    renderRampLegend(ctx.els.anManagerLegend, edges);
    renderBarList(ctx, host, managers.map(function (m) {
      var per = m.count ? Math.round((m.revenue || 0) / m.count) : 0;
      return {
        label: m.manager,
        amount: m.revenue || 0,
        count: m.count || 0,
        color: aggColor(toMan(m.revenue), edges),
        tipTitle: m.manager,
        tipRows: [
          { color: aggColor(toMan(m.revenue), edges), val: fmtWon(m.revenue || 0), lbl: '매출' },
          { val: fmtCount(m.count) + '건', lbl: '완료 주문' },
          { val: fmtWon(per), lbl: '건당 평균' },
        ],
      };
    }));
    if (ctx.els.anManagerTotal) {
      ctx.els.anManagerTotal.textContent = '합계 ' + fmtWon(total.revenue || 0) + ' · ' +
        fmtCount(total.count) + '건 — 기간 매출 전체와 같습니다(미지정 담당자 포함).';
    }
    if (ctx.els.anManagerSub) {
      ctx.els.anManagerSub.textContent = '기간 · 출고가 · ' + fmtCount(managers.length) + '명';
    }
  }

  function renderAnalyticsStages(ctx) {
    var stages = ctx.state.data.stages || [];
    var host = ctx.els.anStages;
    if (!host) return;
    toggle(ctx.els.emptyAnStages, stages.length > 0);
    if (!stages.length) {
      clear(host);
      renderRampLegend(ctx.els.anStageLegend, null);
      return;
    }
    var maxMan = Math.max.apply(null, stages.map(function (s) { return toMan(s.amount); }).concat([0]));
    var edges = aggEdges(maxMan);
    renderRampLegend(ctx.els.anStageLegend, edges);
    renderBarList(ctx, host, stages.map(function (st) {
      var per = st.count ? Math.round((st.amount || 0) / st.count) : 0;
      var color = aggColor(toMan(st.amount), edges);
      return {
        // 라벨 SSOT = API(stages[].label). 이 파일에 단계 이름을 적지 않는다.
        label: st.label || st.stage || '',
        amount: st.amount || 0,
        count: st.count || 0,
        color: color,
        tipTitle: (st.label || st.stage || '') + ' 단계',
        tipRows: [
          { color: color, val: fmtWon(st.amount || 0), lbl: '물린 금액' },
          { val: fmtCount(st.count) + '건', lbl: '진행 주문' },
          { val: fmtWon(per), lbl: '건당 평균' },
        ],
      };
    }));
  }

  function renderAnalyticsDeductions(ctx) {
    var data = ctx.state.data;
    var rows = ((data.settlement_status || {}).deductions_by_department || [])
      .filter(function (d) { return (d.amount || 0) > 0; });
    var host = ctx.els.anDeductions;
    if (!host) return;
    var total = deductionTotalOf(data);
    var empty = rows.length === 0;
    toggle(ctx.els.emptyAnDeductions, !empty);
    if (ctx.els.anDeductionTotal) toggle(ctx.els.anDeductionTotal, empty);
    if (empty) {
      clear(host);
      return;
    }
    renderBarList(ctx, host, rows.map(function (d) {
      return {
        // 부서명·순서 SSOT 도 API(label) 다 — 목업의 이름·순서는 실제와 다르다.
        label: d.label || d.department || '',
        amount: d.amount || 0,
        count: d.count || 0,
        color: '#eb6834',
        tipTitle: (d.label || d.department || '') + ' 귀속 차감',
        tipRows: [
          { color: '#eb6834', val: fmtWon(d.amount || 0), lbl: '차감액' },
          { val: fmtCount(d.count) + '건', lbl: '기록된 건' },
        ],
      };
    }));
    if (ctx.els.anDeductionTotal) {
      ctx.els.anDeductionTotal.textContent = '차감 합계 ' + fmtWon(total) + ' · 기록이 없는 부서는 줄을 내지 않습니다.';
    }
  }

  function renderAnalyticsCollection(ctx) {
    var data = ctx.state.data;
    var kpi = data.kpi || {};
    var host = ctx.els.anCollect;
    if (!host) return;
    clear(host);
    host.appendChild(statBox({
      label: '수금 근사 · 예약금', value: fmtMan(toMan(kpi.collected_deposit)), unit: '원',
      family: 'col', sub: '완료월 귀속',
    }));
    host.appendChild(statBox({
      label: '수금 근사 · 잔금(입금 확인분)', value: fmtMan(toMan(kpi.collected_balance)), unit: '원',
      family: 'col', sub: '완료월 귀속',
    }));

    // 과입금은 잔금 0 클램프가 삼키는 금액이다 — 0 이면 줄을 내지 않는다.
    var overpaid = kpi.overpaid_total || 0;
    toggle(ctx.els.anOverpaid, overpaid === 0);
    if (overpaid > 0 && ctx.els.anOverpaid) {
      ctx.els.anOverpaid.textContent = '과입금 ' + fmtWon(overpaid) + ' 은 위 수금액에 포함되지 않습니다(잔금 0 클램프 밖).';
    }

    var rows = data.aging || [];
    var bucketCount = sum(rows, function (r) { return r.count; });
    toggle(ctx.els.emptyAnAging, bucketCount > 0);
    if (ctx.els.anReceivable) {
      ctx.els.anReceivable.textContent = '미수(잔금 입금 미확인) ' + fmtWon(kpi.receivable_total || 0) +
        ' · ' + fmtCount(kpi.receivable_count) + '건 — 기간 무관 전체';
    }
    if (bucketCount === 0) {
      clear(ctx.els.anAging);
      return;
    }
    renderBarList(ctx, ctx.els.anAging, rows.map(function (r, i) {
      var color = ORANGE_RAMP5[i % ORANGE_RAMP5.length];
      return {
        label: r.label,
        amount: r.amount || 0,
        count: r.count || 0,
        color: color,
        tipTitle: '경과 ' + r.label,
        tipRows: [
          { color: color, val: fmtWon(r.amount || 0), lbl: '미수 잔금' },
          { val: fmtCount(r.count) + '건', lbl: '주문 수' },
        ],
      };
    }));
  }

  function renderAnalyticsAs(ctx) {
    var data = ctx.state.data;
    var st = data.settlement_status || {};
    var host = ctx.els.anAs;
    var meters = ctx.els.anAsMeters;
    if (!host || !meters) return;
    clear(host);
    clear(meters);
    // 3분할은 서버에서 정확히 상호배타다(합 = as_total_count) — 화면이 다시 나누지 않는다.
    var total = st.as_total_count || 0;
    var paid = st.as_billing_paid_count || 0;
    var completed = (data.kpi || {}).completed_count || 0;
    var issued = st.issued_count || 0;
    toggle(ctx.els.emptyAnAs, total > 0);
    if (ctx.els.anAsSub) {
      ctx.els.anAsSub.textContent = '기간 완료 ' + fmtCount(completed) + '건 중 AS ' + fmtCount(total) + '건';
    }
    if (total > 0) {
      host.appendChild(statBox({
        label: 'AS 유상', value: fmtCount(paid), unit: '건',
        sub: fmtWon(st.as_billing_paid_amount || 0),
      }));
      host.appendChild(statBox({
        label: 'AS 무상', value: fmtCount(st.as_billing_free_count), unit: '건', sub: '청구 없음',
      }));
      host.appendChild(statBox({
        label: 'AS 미확정', value: fmtCount(st.as_billing_undecided_count), unit: '건', sub: '청구 판정 전',
      }));
      meters.appendChild(meterRow(
        '유상 비중 (AS ' + fmtCount(total) + '건 중 ' + fmtCount(paid) + '건)',
        total > 0 ? (paid / total) * 100 : 0
      ));
    }
    meters.appendChild(meterRow(
      '정산 청구완료 ' + fmtCount(issued) + '건 / 대기 ' + fmtCount(st.pending_count) + '건',
      completed > 0 ? (issued / completed) * 100 : 0
    ));
  }

  /** 분석 탭 전체. 카드가 하나 죽어도 나머지가 살도록 카드 단위로 나눠 부른다. */
  function renderAnalytics(ctx) {
    if (!ctx.els.analyticsGrid) return;
    renderAnalyticsKpis(ctx);
    // 요약 탭과 **같은 함수**를 다른 호스트 묶음으로 한 번 더 부른다(복제 아님).
    renderMainChart(ctx, ctx.els.anMainEls);
    renderUnknownCompletion(ctx, ctx.els.anUnknownCompletion);
    renderAnalyticsChannels(ctx);
    renderAnalyticsManagers(ctx);
    renderAnalyticsStages(ctx);
    renderAnalyticsDeductions(ctx);
    renderAnalyticsCollection(ctx);
    renderAnalyticsAs(ctx);
  }

  function renderAll(ctx) {
    if (!ctx.state.data) return;
    renderRangeLine(ctx);
    renderKpis(ctx);
    renderMainChart(ctx, ctx.els.mainEls);
    renderUnknownCompletion(ctx, ctx.els.unknownCompletion);
    renderAging(ctx);
    renderSettlementStatus(ctx);
    renderStages(ctx);
    renderChannels(ctx);
    // 탭 3(분석). 진입점을 두 벌로 만들지 않는다 — 탭 활성화·리사이즈가 여기로 들어온다.
    renderAnalytics(ctx);
  }

  /* ═══════════════ 5. 상태 표시 + fetch ═══════════════ */

  /**
   * 화면 상태 전환. 'loading' / 'error' / 'denied' / 'ready' 는 서로 **다른 노드**로 말한다 —
   * 무음 실패 금지이고, 권한 실패를 통신 오류처럼 보이게 하지도 않는다.
   *
   * 상태 3종 노드는 탭 pane **밖**(루트 직속)이라 어느 탭에서 실패해도 보인다. pane 안에
   * 있으면 분석 탭에서 fetch 가 깨질 때 실패 문구가 `display:none` 인 요약 pane 안에서
   * 켜져 **분석 탭만 아무 설명 없이 비는** 무음 실패가 된다(템플릿 주석에 같은 내용).
   * 그래서 감추는 대상(그리드)도 요약·분석 **양쪽**이다.
   */
  function showState(ctx, kind, detail) {
    toggle(ctx.els.loading, kind !== 'loading');
    toggle(ctx.els.error, kind !== 'error');
    toggle(ctx.els.denied, kind !== 'denied');
    toggle(ctx.els.grid, kind !== 'ready');
    toggle(ctx.els.analyticsGrid, kind !== 'ready');
    toggle(ctx.els.filterbar, kind === 'denied');
    toggle(ctx.els.foot, kind === 'denied');
    // 권한 거부는 화면 전체에 대한 거부다 — 탭바를 감추고 거부 문구가 있는 요약 탭으로
    // 되돌린다. 그러지 않으면 "권한 없음"인데 실무·분석 탭은 눌리는 화면이 된다.
    toggle(ctx.els.tabbar, kind === 'denied');
    if (kind === 'denied' && ctx.state.tab !== DEFAULT_TAB) activateTab(ctx, DEFAULT_TAB, false);
    if (kind === 'error' && ctx.els.errorDetail && detail) {
      ctx.els.errorDetail.textContent = detail;
    }
    if (kind !== 'ready') hideTip(ctx);
  }

  function buildUrl(ctx) {
    var base = ctx.root.getAttribute('data-aggregates-url') || API_FALLBACK;
    var gran = ctx.state.gran;
    var month = ctx.state.month;
    var params = ['granularity=' + encodeURIComponent(gran)];
    // 월 모드는 목업과 같이 최근 6개월을 본다. 일/주 모드는 당월 1개월 —
    // 그래야 서버의 prev_buckets 가 정확히 '전월'이 된다(같은 길이의 직전 구간).
    var from = gran === 'month' ? shiftMonth(month, -5) : month;
    if (month && from) {
      params.push('month_from=' + encodeURIComponent(from));
      params.push('month_to=' + encodeURIComponent(month));
    }
    return base + (base.indexOf('?') === -1 ? '?' : '&') + params.join('&');
  }

  async function load(ctx) {
    var state = ctx.state;
    var seq = ++state.seq;
    showState(ctx, 'loading');
    try {
      var res = await fetch(buildUrl(ctx), {
        credentials: 'same-origin',
        headers: { Accept: 'application/json' },
      });
      var body = null;
      try {
        body = await res.json();
      } catch (parseError) {
        body = null;
      }
      if (seq !== state.seq) return;   // 늦게 도착한 응답이 최신 화면을 덮지 않게 한다
      if (res.status === 403) {
        showState(ctx, 'denied');
        return;
      }
      if (!res.ok || !body || body.success !== true || !body.data) {
        var reason = (body && body.error) ? String(body.error) : ('서버 응답 오류 (HTTP ' + res.status + ')');
        showState(ctx, 'error', reason);
        return;
      }
      state.data = body.data;
      if (body.data.range && /^\d{4}-\d{2}$/.test(body.data.range.month_to || '')) {
        // 서버가 KST 기준 월의 최종 권위다 — 클라 계산이 틀렸어도 여기서 교정된다.
        state.month = body.data.range.month_to;
      }
      showState(ctx, 'ready');
      renderAll(ctx);
    } catch (err) {
      if (seq !== state.seq) return;
      showState(ctx, 'error', '집계 서버에 연결하지 못했습니다. 네트워크를 확인한 뒤 다시 시도하세요.');
    }
  }

  /* ═══════════════ 6. 필터바 배선 ═══════════════ */

  function syncToggles(ctx) {
    var state = ctx.state;
    ctx.els.granButtons.forEach(function (btn) {
      btn.setAttribute('aria-pressed', String(btn.getAttribute('data-settlement-granularity') === state.gran));
    });
    var cumAllowed = state.gran === 'day';
    if (!cumAllowed) state.cum = false;
    if (ctx.els.cumToggle) {
      ctx.els.cumToggle.disabled = !cumAllowed;
      ctx.els.cumToggle.setAttribute('aria-pressed', String(state.cum));
    }
    // 월 모드는 최근 6개월 단일 시리즈 — 전월 비교 축이 없다.
    var cmpAllowed = state.gran !== 'month';
    if (ctx.els.cmpToggle) {
      ctx.els.cmpToggle.disabled = !cmpAllowed;
      ctx.els.cmpToggle.setAttribute('aria-pressed', String(cmpAllowed && state.cmp));
    }
  }

  /* ═══════════════ 6.5 탭 3종 (요약 · 실무 · 분석) ═══════════════ */

  var DEFAULT_TAB = 'summary';

  /** 좌우 화살표 이동 폭(표준 tablist 패턴 — 이동 즉시 활성화, 양끝에서 순환). */
  var TAB_ARROW_STEP = { ArrowLeft: -1, ArrowRight: 1 };

  function tabKeyOf(el) {
    return el ? el.getAttribute('data-settlement-tab') : null;
  }

  /**
   * 탭 활성화 — 선택 상태 · pane 표시 · 차트 재렌더를 한 곳에서 처리한다.
   *
   * **숨은 pane 안에서 그린 차트는 폭이 틀린다.** `hidden` pane 은 `display:none` 이라
   * 안쪽 호스트의 `clientWidth` 가 0 이고, 렌더러는 `host.clientWidth || 400`(lineChart 는
   * 640)로 폴백한다 — 즉 **빈 차트가 아니라 400px 짜리 눌린 차트**가 남는다.
   * (폴백이 없었다면 `pw <= 0` 조기반환으로 호스트가 비워진다. 폭이 1~57px 인 실제 좁은
   * 경우엔 지금도 그 가지를 탄다.) 어느 쪽이든 스스로 낫지 않는다.
   *
   * 실측(2026-08-31, dev 5011 · 시드 707건): 분석 탭에 있는 동안 창을 1440→1100 으로 줄이면
   * onResize 가 숨은 요약 탭을 폭 0 으로 다시 그려 `svg width=400` 이 되고, 이 재렌더가
   * 없으면 요약 탭으로 돌아왔을 때 `svgW 400 vs hostW 1006` 인 눌린 차트가 그대로 보인다.
   *
   * 그래서 pane 을 보이게 만든 **직후** 다시 그린다 — onResize 가 쓰는 것과 **같은
   * 경로**(renderAll)다. 렌더 진입점을 두 벌로 만들면 한쪽만 고치는 회귀가 난다.
   * 탭 3 차트도 renderAll 에 렌더 함수를 등록하면 이 경로를 그대로 탄다.
   */
  function activateTab(ctx, key, moveFocus) {
    var tabs = ctx.els.tabs;
    if (!tabs.length) return;
    var known = tabs.some(function (tab) { return tabKeyOf(tab) === key; });
    if (!known) key = DEFAULT_TAB;
    ctx.state.tab = key;
    // CSS 가 보는 SSOT(실무 탭에서 필터바를 감추는 선택자). 클래스가 아니라 속성인 이유는
    // CSS 쪽 주석 참조 — s-hidden 은 showState() 의 권한거부 분기가 쓰는 자리다.
    ctx.root.setAttribute('data-settlement-active-tab', key);
    tabs.forEach(function (tab) {
      var on = tabKeyOf(tab) === key;
      tab.setAttribute('aria-selected', String(on));
      tab.tabIndex = on ? 0 : -1;   // roving tabindex — Tab 키는 탭바를 한 번만 지난다
      if (on && moveFocus) tab.focus();
    });
    ctx.els.panes.forEach(function (pane) {
      pane.hidden = pane.getAttribute('data-settlement-pane') !== key;
    });
    if (ctx.state.data) renderAll(ctx);
  }

  /** ←/→(+Home/End)로 탭 이동. 차트의 `.s-hit` 도 ←→ 를 쓰지만 탭 버튼이 아니라 안 걸린다. */
  function onTabKeydown(ctx, e) {
    var tab = e.target.closest ? e.target.closest('[data-settlement-tab]') : null;
    if (!tab || !ctx.root.contains(tab)) return;
    var tabs = ctx.els.tabs;
    var index = tabs.indexOf(tab);
    if (index < 0) return;
    var next;
    if (Object.prototype.hasOwnProperty.call(TAB_ARROW_STEP, e.key)) {
      next = (index + TAB_ARROW_STEP[e.key] + tabs.length) % tabs.length;
    } else if (e.key === 'Home') {
      next = 0;
    } else if (e.key === 'End') {
      next = tabs.length - 1;
    } else {
      return;
    }
    e.preventDefault();
    activateTab(ctx, tabKeyOf(tabs[next]), true);
  }

  function bindControls(ctx) {
    // 리스너는 전부 이 루트 **안쪽**에만 붙는다. 루트가 프래그먼트 스왑으로 사라지면
    // 리스너도 같이 사라져 전역에 누적되지 않는다(perf G4).
    ctx.root.addEventListener('click', function (e) {
      var tabBtn = e.target.closest('[data-settlement-tab]');
      if (tabBtn && ctx.root.contains(tabBtn)) {
        activateTab(ctx, tabKeyOf(tabBtn), false);
        return;
      }
      var granBtn = e.target.closest('[data-settlement-granularity]');
      if (granBtn && ctx.root.contains(granBtn)) {
        var next = granBtn.getAttribute('data-settlement-granularity');
        if (next && next !== ctx.state.gran) {
          ctx.state.gran = next;
          syncToggles(ctx);
          load(ctx);   // granularity 는 서버 재버킷이다
        }
        return;
      }
      if (e.target.closest('[data-settlement-compare]')) {
        if (ctx.els.cmpToggle && ctx.els.cmpToggle.disabled) return;
        ctx.state.cmp = !ctx.state.cmp;
        syncToggles(ctx);
        if (ctx.state.data) renderMainChart(ctx, ctx.els.mainEls);   // prev_buckets 는 이미 응답에 있다 — 재조회 없음
        return;
      }
      if (e.target.closest('[data-settlement-cumulative]')) {
        if (ctx.els.cumToggle && ctx.els.cumToggle.disabled) return;
        ctx.state.cum = !ctx.state.cum;
        syncToggles(ctx);
        if (ctx.state.data) renderMainChart(ctx, ctx.els.mainEls);   // 누적은 클라이언트 누산 — 재조회 없음
        return;
      }
      if (e.target.closest('[data-settlement-retry]')) {
        load(ctx);
        return;
      }
      if (e.target.closest('[data-settlement-focus]')) {
        setFocusMode(!isFocusMode());
        return;
      }
      if (e.target.closest('[data-settlement-focus-exit]')) {
        setFocusMode(false);
      }
    });
    ctx.root.addEventListener('keydown', function (e) { onTabKeydown(ctx, e); });
  }

  /* ═══════════════ 7. 마운트 + 전역 배선 ═══════════════ */

  var mounts = [];

  function collectEls(root) {
    var q = function (sel) { return root.querySelector(sel); };
    return {
      kpis: q('#foms-settle-kpis'),
      // 추이 차트 묶음 2벌(요약·분석). 같은 렌더 함수가 els 만 바꿔 두 번 돈다.
      // `.s-tblv` 는 이제 문서에 둘이라 카드 안으로 스코프해서 잡는다 — 루트 querySelector
      // 로 잡으면 분석 카드가 요약 카드의 표를 토글한다.
      mainEls: {
        chart: q('#foms-settle-main-chart'),
        table: q('#foms-settle-main-table'),
        tableWrap: root.querySelector('.s-card--main .s-tblv'),
        legend: q('#foms-settle-main-legend'),
        sub: q('[data-settlement-main-sub]'),
        empty: q('[data-settlement-empty="buckets"]'),
      },
      anMainEls: {
        chart: q('#foms-settle-an-main-chart'),
        table: q('#foms-settle-an-main-table'),
        tableWrap: root.querySelector('#foms-settle-an-trend-card .s-tblv'),
        legend: q('#foms-settle-an-main-legend'),
        sub: q('[data-settlement-an-main-sub]'),
        empty: q('[data-settlement-empty="an_buckets"]'),
      },
      anUnknownCompletion: q('[data-settlement-an-unknown-completion]'),
      agingChart: q('#foms-settle-aging-chart'),
      agingSub: q('[data-settlement-aging-sub]'),
      agingCritical: q('[data-settlement-aging-critical]'),
      agingCriticalText: q('[data-settlement-aging-critical-text]'),
      agingUnknown: q('[data-settlement-aging-unknown]'),
      unknownCompletion: q('[data-settlement-unknown-completion]'),
      stages: q('#foms-settle-stages'),
      channelBar: q('#foms-settle-channel-bar'),
      channelLegend: q('#foms-settle-channel-legend'),
      channelSub: q('[data-settlement-channel-sub]'),
      statusBody: q('[data-settlement-status-body]'),
      statusSub: q('[data-settlement-status-sub]'),
      emptySettlement: q('[data-settlement-empty="settlement_status"]'),
      emptyAging: q('[data-settlement-empty="aging"]'),
      emptyStages: q('[data-settlement-empty="stages"]'),
      emptyChannels: q('[data-settlement-empty="channels"]'),
      loading: q('[data-settlement-loading]'),
      error: q('[data-settlement-error]'),
      errorDetail: q('[data-settlement-error-detail]'),
      denied: q('[data-settlement-denied]'),
      grid: q('[data-settlement-grid]'),
      filterbar: q('.s-filterbar'),
      foot: q('.s-foot'),
      rangeLine: q('[data-settlement-range]'),
      stamp: q('[data-settlement-stamp]'),
      tooltip: q('#foms-settle-tooltip'),
      granButtons: Array.prototype.slice.call(root.querySelectorAll('[data-settlement-granularity]')),
      cmpToggle: q('[data-settlement-compare]'),
      cumToggle: q('[data-settlement-cumulative]'),
      tabbar: q('.s-tabs'),
      tabs: Array.prototype.slice.call(root.querySelectorAll('[data-settlement-tab]')),
      panes: Array.prototype.slice.call(root.querySelectorAll('[data-settlement-pane]')),
      // ── 탭 3 · 분석 ──
      analyticsGrid: q('[data-settlement-analytics-grid]'),
      anKpis: q('#foms-settle-an-kpis'),
      anChannelBar: q('#foms-settle-an-channel-bar'),
      anChannelTable: q('#foms-settle-an-channel-table'),
      anChannelTableWrap: q('.s-atbl'),
      anChannelSub: q('[data-settlement-an-channel-sub]'),
      anManagerCard: q('[data-settlement-manager-card]'),
      anManagers: q('#foms-settle-an-managers'),
      anManagerLegend: q('#foms-settle-an-manager-legend'),
      anManagerSub: q('[data-settlement-an-manager-sub]'),
      anManagerTotal: q('[data-settlement-an-manager-total]'),
      anStages: q('#foms-settle-an-stages'),
      anStageLegend: q('#foms-settle-an-stage-legend'),
      anDeductions: q('#foms-settle-an-deductions'),
      anDeductionTotal: q('[data-settlement-an-deduction-total]'),
      anCollect: q('#foms-settle-an-collect'),
      anOverpaid: q('[data-settlement-an-overpaid]'),
      anReceivable: q('[data-settlement-an-receivable]'),
      anAging: q('#foms-settle-an-aging'),
      anAs: q('#foms-settle-an-as'),
      anAsMeters: q('#foms-settle-an-as-meters'),
      anAsSub: q('[data-settlement-an-as-sub]'),
      emptyAnChannels: q('[data-settlement-empty="an_channels"]'),
      emptyManagers: q('[data-settlement-empty="managers"]'),
      emptyAnStages: q('[data-settlement-empty="an_stages"]'),
      emptyAnDeductions: q('[data-settlement-empty="an_deductions"]'),
      emptyAnAging: q('[data-settlement-empty="an_aging"]'),
      emptyAnAs: q('[data-settlement-empty="an_as"]'),
    };
  }

  function mount(root) {
    if (!root || root.dataset.settlementMounted === '1') return;
    root.dataset.settlementMounted = '1';
    var ctx = {
      root: root,
      els: collectEls(root),
      state: { gran: 'day', cum: false, cmp: true, month: kstMonth(), data: null, seq: 0, tab: DEFAULT_TAB },
    };
    mounts.push(ctx);
    syncToggles(ctx);
    // 탭 상태는 마운트마다 기본값(요약)으로 시작한다 — gran/cmp/cum 과 같은 규율이다.
    // 프래그먼트 스왑은 루트를 통째로 갈아끼우므로 여기가 스왑 후 재배선 지점이기도 하다.
    activateTab(ctx, DEFAULT_TAB, false);
    bindControls(ctx);
    // 집중 모드 기억 복원 — 스왑 후 재마운트도 같은 경로라 버튼 aria-pressed 가 body 상태와 다시 맞는다.
    if (readFocusPreference()) setFocusMode(true); else syncFocusButtons();
    load(ctx);
  }

  function mountAll() {
    // 떨어져 나간 루트는 정리한다 — 프래그먼트 스왑으로 DOM 에서 사라진 화면을 리사이즈가 다시 그리지 않게.
    mounts = mounts.filter(function (ctx) { return ctx.root.isConnected; });
    document.querySelectorAll(ROOT_SELECTOR).forEach(mount);
  }

  /** 마운트된 화면을 다시 그린다. 차트는 폭 의존 렌더라 폭이 바뀌면 반드시 되그려야 한다. */
  function renderMountedRoots() {
    mounts.forEach(function (ctx) {
      if (ctx.root.isConnected && ctx.state.data) renderAll(ctx);
    });
  }

  var resizeTimer = null;
  function onResize() {
    window.clearTimeout(resizeTimer);
    resizeTimer = window.setTimeout(renderMountedRoots, 150);
  }

  // 전역(document/window) 리스너는 싱글톤 뒤에서 1회만 — 프래그먼트 재실행 때 중복 누적 금지(perf G4).
  if (!window.__FOMS_SETTLEMENT_DASHBOARD_BOUND) {
    window.__FOMS_SETTLEMENT_DASHBOARD_BOUND = true;
    document.addEventListener('foms:main-content-swapped', mountAll);
    document.addEventListener('foms:erp-shell-fragment-swapped', mountAll);
    document.addEventListener('DOMContentLoaded', mountAll);
    window.addEventListener('resize', onResize);
    // Esc 는 window 에 1회(싱글톤 가드 안) — 루트 위임으로는 포커스가 차트 밖에 있을 때 못 받는다.
    window.addEventListener('keydown', function (e) {
      if (e.key === 'Escape' && isFocusMode()) setFocusMode(false);
    });
  }

  // defer 로 실린 첫 로드와, 셸이 <script src> 를 재실행하는 스왑 경로를 **둘 다** 덮는다.
  // (스왑 이벤트가 재실행보다 먼저 오든 나중에 오든 mount 표식이 중복 마운트를 막는다.)
  mountAll();
})();
