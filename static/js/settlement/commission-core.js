/**
 * 정산 대시보드 · 탭 "영업 수수료" — 공용 조각(표기 · DOM · fetch) (FCOMM-01 §2.1 · 플랜 T6).
 *
 * 이 탭의 스크립트는 6개로 나뉜다(파일당 300줄 래칫 — tests/harness/test_file_size_ratchet.py):
 *   commission-core.js    표기 · DOM 만들기 · fetch 도우미(이 파일)
 *   commission-table.js   표 · 합계 줄 · 비슷한 이름 경고 그리기
 *   commission-edit.js    시공비 · 회계팀 지정 요율 자동 저장(주문마다 줄 세우기) · Enter 이동
 *   commission-deduct.js  차감 작은 창(넣기 · 취소)
 *   commission-close.js   달 마감 확인 창 · 마감 기록(내려받기 · 지급 완료 · 마감 취소)
 *   commission.js         마운트 · 조회 · 조작(진입점)
 * 서로는 전역 이름공간 `window.FomsSettleCommission` 하나로만 만난다. 프래그먼트 스왑 때 셸이
 * `<script src>` 를 다시 실행해도 같은 함수를 다시 대입할 뿐이라 누적되는 것이 없다.
 *
 * 서버 문자열(고객명 · 품목 · 사유)은 전부 textContent 로 넣는다(innerHTML 미사용).
 * 쓰기 요청의 CSRF 헤더는 공용 fetch 래퍼가 자동으로 싣는다(WRITE-GUARD-01).
 */
(function () {
  'use strict';

  var C = window.FomsSettleCommission = window.FomsSettleCommission || {};

  /* 거래구분 · 상태 · 본인 수정 칸 이름 — 화면 낱말은 여기 한 곳. */
  C.DEAL_LABELS = { LAHOM: '라홈', HAUD: '하우드', PERSONAL: '개인영업', MANUAL: '회계팀 지정' };
  C.STATE_LABELS = { WAIT_COST: '시공비 기다림', WAIT_RATE: '요율 정해 주세요', FORECAST: '예상' };
  /* 목적격 조사까지 붙인 이름("발주사를 11-12에 바꿨어요"). */
  C.SELF_EDIT_LABELS = {
    'parties.orderer.name': '발주사를',
    'schedule.measurement.date': '실측일을',
    'schedule.construction.date': '시공일을',
    'totals.shipping_price': '출고가를',
    'parties.manager.name': '대표 담당을',
    'parties.manager.names': '담당 명단을',
  };
  C.STALE_MESSAGE = '그사이 다른 사람이 고쳤어요. 새 값으로 바꿔 놓았어요.';
  C.NETWORK_MESSAGE = '연결이 끊겼어요. 잠시 뒤 다시 해 주세요.';

  /* ═══════════════ 표기 ═══════════════ */

  C.won = function (v) {
    if (v === null || v === undefined || v === '') return '—';
    var n = Number(v);
    return isFinite(n) ? Math.round(n).toLocaleString('ko-KR') : '—';
  };
  /** 100bp = 1%. 400 → "4%", 350 → "3.5%". */
  C.ratePct = function (bp) {
    if (bp === null || bp === undefined) return '';
    var n = Number(bp);
    if (!isFinite(n)) return '';
    return String(Math.round(n) / 100);
  };
  /** "2026-11-12 14:03" → "11-12". */
  C.shortDay = function (at) {
    var m = /^\d{4}-(\d{2}-\d{2})/.exec(String(at || ''));
    return m ? m[1] : String(at || '');
  };
  /** 숫자 칸 글자 → 정수. 빈칸은 null, 숫자가 아니면 NaN. 쉼표 · 공백 · "원" 은 무시한다. */
  C.parseWon = function (text) {
    var t = String(text == null ? '' : text).replace(/[\s,원]/g, '');
    if (!t) return null;
    if (!/^\d+$/.test(t)) return NaN;
    return parseInt(t, 10);
  };
  /** 요율 칸 글자(%) → bp. "4" → 400, "3.5" → 350. 빈칸은 null, 틀리면 NaN. */
  C.parseRateBp = function (text) {
    var t = String(text == null ? '' : text).replace(/[\s%]/g, '');
    if (!t) return null;
    if (!/^\d+(\.\d{1,2})?$/.test(t)) return NaN;
    var bp = Math.round(parseFloat(t) * 100);
    return bp > 10000 ? NaN : bp;
  };

  /* ═══════════════ DOM ═══════════════ */

  /** 요소 하나. text 는 textContent 로만 들어간다. */
  C.el = function (tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = String(text);
    return node;
  };
  C.hide = function (node, hidden) { if (node) node.hidden = !!hidden; };
  C.monthOk = function (m) { return /^\d{4}-(0[1-9]|1[0-2])$/.test(String(m || '')); };

  /* ═══════════════ fetch ═══════════════ */

  function failure(res, body) {
    if (body && (body.error || body.message)) return String(body.error || body.message);
    if (res && res.status === 403) return '회계팀과 관리자만 할 수 있어요.';
    return '불러오지 못했어요. 잠시 뒤 다시 해 주세요.';
  }

  /**
   * JSON 요청 한 번. 성공이면 body, 아니면 `err.status` · `err.body` 를 단 Error 를 던진다.
   * 네트워크 실패도 Error 로 바꿔 던진다 — 부르는 쪽은 try/catch 하나로 받는다.
   */
  C.request = async function (method, url, payload) {
    var opts = {
      method: method,
      credentials: 'same-origin',
      headers: { Accept: 'application/json' },
    };
    if (payload !== undefined) {
      opts.headers['Content-Type'] = 'application/json';
      opts.body = JSON.stringify(payload);
    }
    var res;
    try {
      res = await fetch(url, opts);
    } catch (networkError) {
      var netErr = new Error(C.NETWORK_MESSAGE);
      netErr.status = 0;
      throw netErr;
    }
    var body = null;
    try {
      body = await res.json();
    } catch (parseError) {
      body = null;
    }
    if (!res.ok || !body || body.success !== true) {
      var err = new Error(failure(res, body));
      err.status = res.status;
      err.body = body;
      throw err;
    }
    return body;
  };

  C.core = true;
  if (typeof C.mountAll === 'function') C.mountAll();
})();
