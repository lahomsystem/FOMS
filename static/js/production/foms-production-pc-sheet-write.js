/* 생산 PC 도면 목록 창의 쓰기 — [고치기] 켬일 때만 실린다(home_scripts.html). 창 · 그리기 · 두 번 누름 막기 · 다시 받기는
 * foms-production-pc-sheet.js, 여기는 **있는 쓰기 길만** 부른다(새 주소 없음 — 사장님 2026-11-24 "PC 에서도 도면별로 체크").
 *  · [완료 처리](미완료 장 → 완료, 옛 [작업]) = POST /api/production/part-marks {action:'check', seen} **한 요청**(2026-11-25 multi-holder
 *    판결 2). 서버가 한 tx 안에서 정한다 — 빈 장 = 누른 감독이 시작 + 완료, 남이 작업 중인 장(그사이 남이 시작한 장 포함) = 남은 사람 몫을
 *    한 번에 대신 완료(감독은 같이 작업하는 사람으로 안 들어감 — 감사 꼬리 "(관리자 덮어쓰기)" · "(대신 처리)"), 이미 완료 = 바뀜 없음.
 *    옛 두 요청 길(맡기 → 완료 → 막히면 맡기 취소)은 없다 — 첫 요청이 늦은 [작업 시작] 넘김(Q16)으로 감독을 같이 작업자로 넣어 버린다.
 *  · [완료 취소](완료 · 기본 장, 옛 [작업 취소]) = 같은 길 {action:'undo'} — 도면 판 [되돌리기]와 같다. 서버가 줄에 ``undo_releases``(작업하는
 *    사람이 나 하나이고 시작 → 완료가 2분 안 = PC [완료 처리]가 빈 장을 시작 + 완료한 흔적, 서버 UTC 로 판정)를 주고 되돌린 뒤에도 작업하는
 *    사람이 나 하나일 때만 시작 취소(release)까지 이어서 "안 봄 · 담당 미정"으로. 그 밖(태블릿에서 진짜 시작했다가 한참 뒤 완료 · 같이 작업한
 *    장 · 남의 장을 대신 완료)은 완료 취소만. 둘째 요청이 막히면 창이 서버 모습으로 다시 그리고 서버 글을 그 줄에(셋째 판).
 *  · 손으로 통째 체크한 파트의 [모두 완료 취소] = POST /api/orders/<id>/production/steps {key, done:false}. 옛 [모두 완료 처리](켜기)는
 *    창이 도면 1장 이상일 때만 열리고 도면 있는 주문은 서버가 켜기를 막아(409 STEP_PER_SHEET) 탈 길이 없어 뺐다(2026-11-27).
 *  · 마지막 검수 장을 완료해 서버가 order_ready 를 주면 창 안에 "제작 완료할까요?"(태블릿 창과 같은 글 · [나중에][제작 완료] · 실행 단추
 *    0.8초 잠금 · 초점 [나중에]) → [제작 완료] = 지금 제작 완료 API(POST /api/orders/<id>/production/complete) 그대로, 거절은 서버 글.
 *  · PC 로 연 작업 시트에서 쓰고 창을 닫으면 그 시트를 다시 받아 공정 칸 · n/4 · [제작 완료] 단추 상태를 서버 값으로 바꾼다(단계가
 *    바뀌었으면 — 첫 도면 = 제작 시작 · 제작 완료 — 화면 통째 다시 받기). 불량 줄 · 도면 넘기기는 건드리지 않는다.
 *    PC 첫 화면 창에서 [제작 완료]를 했으면(그 줄이 생산 단계를 벗어나 서버가 줄 칸을 못 그린다) 닫을 때 위 [다시 받기]와 같은 길
 *    (날짜 · 탭 · 고른 주문을 실은 주소, 셸이면 조각만)로 화면을 다시 받는다.
 *  · 서버가 막으면(보류 · 도면 고치는 중 · 검수 순서 · 손 체크 · 경합) 글은 서버 글 그대로 돌려준다. 결과는 늘 {ok, message} 로 끝난다. */
(function () {
  'use strict';

  var OFFLINE = '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.';
  var LOCK_MS = 800; // 이어 뜨는 물음의 실행 단추 잠금(태블릿 창과 같다 — 두 번 누름이 바로 제작 완료가 되지 않게)

  function post(url, body) {
    var opts = { method: 'POST', credentials: 'same-origin', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) };
    var call = window.fomsMutationFetch || function (u, o) {
      return fetch(u, o).then(function (res) {
        return res.json().catch(function () { return null; }).then(function (data) {
          var good = !!data && res.ok && data.success === true;
          return { ok: good, kind: good ? 'ok' : 'error', status: res.status, data: data || {}, message: (data && (data.error || data.message)) || '' };
        });
      });
    };
    try {
      return call(url, opts).then(done, function () { return { ok: false, message: OFFLINE }; });
    } catch (e) { return Promise.resolve({ ok: false, message: OFFLINE }); }
  }
  function done(result) {
    if (!result) { return { ok: false, message: OFFLINE }; }
    var body = result.data || {};
    var good = !!result.ok && body.success !== false;
    var net = result.kind === 'network' || result.status === 0;
    return { ok: good, data: body.data || {}, message: good ? '' : (net ? OFFLINE : (body.error || result.message || OFFLINE)) };
  }

  function mark(d, key, action, seen, seenBy) {
    var body = { order_id: Number(d.order_id), drawing_key: key, part: d.part, action: action, seen: seen };
    if (seenBy !== undefined) { body.seen_by = seenBy == null ? null : Number(seenBy); } // 본 담당까지 견준다(시작 취소만, §4-5)
    return post('/api/production/part-marks', body);
  }
  function onlyMe(m, me) { // 작업하는 사람이 나 하나이고 내 몫이 아직(되돌린 뒤)
    var h = (m && m.holders) || [];
    return h.length === 1 && h[0].user_id != null && h[0].user_id === me && !h[0].done;
  }

  // [완료 처리] — 미완료 장을 완료로: action check 한 요청(빈 장 = 시작 + 완료, 남이 작업 중 = 남은 사람 몫 대신 완료 — 서버가 정한다)
  function check(d, r) { return mark(d, r.key, 'check', r.seen); }
  // [완료 취소] — 완료 · 기본 장의 완료 취소, 서버가 undo_releases 를 준 장이고 되돌린 뒤 작업하는 사람이 나 하나면 시작 취소까지
  function uncheck(d, r) {
    return mark(d, r.key, 'undo', r.seen).then(function (undone) {
      var m = undone.ok ? (undone.data.mark || {}) : {};
      if (!r.undo_releases || m.state !== 'need' || !onlyMe(m, d.me)) { return undone; }
      return mark(d, r.key, 'release', 'need', d.me);
    });
  }
  // 공정 칸 통째(손 체크) 끄기([모두 완료 취소])
  function stepSet(d, on) {
    return post('/api/orders/' + encodeURIComponent(d.order_id) + '/production/steps', { key: d.part, done: !!on });
  }

  // "제작 완료할까요?" — 창 안 물음(마지막 검수 장 완료 뒤). 본문은 태블릿 창과 같은 글
  function askBox(box) { return box.querySelector('[data-foms-pc-sheet-ask]'); }
  function hideAsk(box) { var a = askBox(box); if (a) { a.hidden = true; } }
  function ask(box, d) {
    var a = askBox(box);
    if (!a) { return false; }
    a.querySelector('[data-foms-pc-sheet-ask-body]').textContent = d.customer_name + ' #' + d.order_id + ' · 도면 ' + d.total +
      '장이 모두 완료됐어요. 제작 완료하면 시공 대기로 넘어가요.';
    a.hidden = false;
    var go = a.querySelector('[data-foms-pc-sheet-act="ask-yes"]');
    go.setAttribute('aria-disabled', 'true');
    window.setTimeout(function () { go.removeAttribute('aria-disabled'); }, LOCK_MS);
    a.scrollIntoView({ block: 'nearest' });
    a.querySelector('[data-foms-pc-sheet-act="ask-no"]').focus();
    return true;
  }
  function complete(box, d) {
    return post('/api/orders/' + encodeURIComponent(d.order_id) + '/production/complete', {}).then(function (res) {
      if (res.ok) { hideAsk(box); res.notice = '제작 완료했어요 — 시공 대기로 넘어갔어요'; res.reload = true; } // 태블릿과 같은 글
      return res;
    });
  }

  // PC 로 연 작업 시트 — 쓰고 닫으면 공정 줄을 서버 값으로(같은 주소를 다시 받아 그 칸들만 옮겨 온다)
  function copyAttr(el, from, name) {
    if (from.hasAttribute(name)) { el.setAttribute(name, from.getAttribute(name)); } else { el.removeAttribute(name); }
  }
  function adopt(el, from) { el.replaceChildren.apply(el, [].slice.call(from.childNodes).map(function (n) { return document.importNode(n, true); })); }
  function swapSheet(root, html) {
    var fresh = html ? new DOMParser().parseFromString(html, 'text/html').querySelector('[data-foms-prod-sheet-page]') : null;
    if (!fresh || fresh.getAttribute('data-foms-prod-page-stage') !== root.getAttribute('data-foms-prod-page-stage')) { window.location.reload(); return; }
    var box = root.querySelector('.foms-prod-page__box[aria-label="공정"]');
    var nbox = fresh.querySelector('.foms-prod-page__box[aria-label="공정"]');
    if (!box || !nbox) { window.location.reload(); return; }
    copyAttr(box, nbox, 'data-foms-sheet-parts');
    var had = document.activeElement && document.activeElement.getAttribute('data-foms-pc-sheet'); // 닫으며 돌려준 초점 — 새 칸으로 다시
    adopt(box.querySelector('.foms-prod-page__steps'), nbox.querySelector('.foms-prod-page__steps')); // 칸 · 체크 · 옆 글
    var back = had && box.querySelector('[data-foms-pc-sheet="' + had + '"]');
    if (back) { back.focus(); }
    box.querySelector('[data-foms-sheet-steps-count]').textContent = nbox.querySelector('[data-foms-sheet-steps-count]').textContent;
    var msgEl = box.querySelector('[data-foms-sheet-stepmsg]');
    if (msgEl) { msgEl.hidden = true; }
    var link = box.querySelector('[data-foms-sheet-loglink]');
    var nlink = nbox.querySelector('[data-foms-sheet-loglink]');
    if (!link && nlink) { // 첫 도면을 쓴 주문 — [바뀐 기록 보기]가 생긴다
      var anchor = box.querySelector('[data-foms-sheet-defect-recent]');
      [nlink, nbox.querySelector('[data-foms-sheet-log]')].forEach(function (n) { box.insertBefore(document.importNode(n, true), anchor); });
    } else if (link) { // 열어 둔 기록은 닫고 다음에 다시 받는다
      var log = box.querySelector('[data-foms-sheet-log]');
      link.setAttribute('aria-expanded', 'false');
      if (log) { log.hidden = true; log.removeAttribute('data-loaded'); }
    }
    var btn = root.querySelector('[data-foms-sheet-complete]');
    var nbtn = fresh.querySelector('[data-foms-sheet-complete]');
    if (btn && nbtn) {
      btn.className = nbtn.className;
      ['aria-disabled', 'data-foms-sheet-complete-why'].forEach(function (a) { copyAttr(btn, nbtn, a); });
      var hint = btn.querySelector('[data-foms-sheet-complete-hint]');
      var nhint = nbtn.querySelector('[data-foms-sheet-complete-hint]');
      if (hint && nhint) { hint.hidden = nhint.hidden; }
    }
  }
  function afterClose(root, reload) {
    if (!root.hasAttribute('data-foms-prod-sheet-page')) { // 첫 화면 줄은 쓸 때마다 이미 바꿔 끼웠다 — 제작 완료만 [다시 받기] 길로
      var again = reload && root.querySelector('[data-foms-home-reload]');
      if (again) { again.click(); } else if (reload) { window.location.reload(); }
      return;
    }
    try {
      fetch(window.location.href, { credentials: 'same-origin', headers: { Accept: 'text/html' } })
        .then(function (res) { return res.ok ? res.text() : ''; })
        .then(function (html) { swapSheet(root, html); })
        .catch(function () { window.location.reload(); });
    } catch (e) { window.location.reload(); }
  }

  window.FomsPcSheetWrite = { check: check, uncheck: uncheck, stepSet: stepSet, ask: ask, hideAsk: hideAsk,
    complete: complete, afterClose: afterClose };
})();
