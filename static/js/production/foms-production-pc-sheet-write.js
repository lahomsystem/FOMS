/* 생산 PC 도면 목록 창의 쓰기 — [고치기] 켬일 때만 실린다(home_scripts.html). 창 · 그리기 · 두 번 누름 막기 · 다시 받기는
 * foms-production-pc-sheet.js, 여기는 **있는 쓰기 길만** 부른다(새 쓰기 API 없음 — 사장님 2026-11-24 "PC 에서도 도면별로 체크").
 *  · [체크](미완료 장 → 완료): 담당이 있는 장(작업 필요) = POST /api/production/part-marks {action:'done', seen:'need', seen_by}
 *    (남의 장은 서버가 대신 처리로 적는다 — 감사 꼬리 "(관리자 덮어쓰기)" · "(대신 처리)", 이벤트 holder_name, 지금 규칙 그대로).
 *    안 본 · 안 고른 장 = 같은 길로 맡기(take) → 완료(done) 두 번. 완료가 막히면 방금 맡은 것을 맡기 취소(release)로 되돌린다.
 *  · [체크 해제](완료 · 기본 장) = 같은 길 {action:'undo'} — 도면 판 [되돌리기]와 같다.
 *  · [모두 체크](아무도 안 맡은 파트) = 작업 시트와 같은 반장 손 체크 확인 창(foms-production-sheet-parts.js beforeToggle — 글 · 단추 그대로)
 *    → POST /api/orders/<id>/production/steps {key, done:true}. 손으로 통째 체크한 파트의 [체크 해제] = 같은 길 {done:false}.
 *  · 서버가 막으면(보류 · 도면 고치는 중 · 검수 순서 · 손 체크 · 경합) 글은 서버 글 그대로 돌려준다. 결과는 늘 {ok, message} 로 끝난다. */
(function () {
  'use strict';

  var OFFLINE = '연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.';

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
    if (seen === 'need') { body.seen_by = seenBy == null ? null : Number(seenBy); } // 본 담당까지 견준다(§4-5)
    return post('/api/production/part-marks', body);
  }

  // [체크] — 미완료 장을 완료로
  function check(d, r) {
    if (r.seen === 'need') { return mark(d, r.key, 'done', 'need', r.seen_by); }
    return mark(d, r.key, 'take', 'none').then(function (took) {
      if (!took.ok) { return took; }
      var me = (took.data.mark || {}).picked_by_user_id;
      return mark(d, r.key, 'done', 'need', me).then(function (fin) {
        if (fin.ok) { return fin; }
        return mark(d, r.key, 'release', 'need', me).then(function () { return fin; }); // 맡기만 남지 않게 되돌린다
      });
    });
  }
  // [체크 해제] — 완료 · 기본 장의 완료 취소
  function uncheck(d, r) { return mark(d, r.key, 'undo', r.seen); }
  // 공정 칸 통째(손 체크) — 켜기([모두 체크]) · 끄기([체크 해제])
  function stepSet(d, on) {
    return post('/api/orders/' + encodeURIComponent(d.order_id) + '/production/steps', { key: d.part, done: !!on });
  }
  // [모두 체크] 확인 창 — 작업 시트와 같은 창 · 같은 글(없으면 바로)
  function askAll(page, btn, go) {
    var sp = window.FomsSheetParts;
    if (sp && typeof sp.beforeToggle === 'function') { sp.beforeToggle(page, btn, true, go); return; }
    go();
  }

  window.FomsPcSheetWrite = { check: check, uncheck: uncheck, stepSet: stepSet, askAll: askAll };
})();
