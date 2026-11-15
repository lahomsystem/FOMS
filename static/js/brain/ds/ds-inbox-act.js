/**
 * 새 승인 대기 화면 — 결정 보내기(설계서 2026-11-14-foms-graft 5.4 · 옛 brain-inbox.js 의 결정 흐름 그대로).
 * POST /api/brain/proposals/<id>/apply · reject · bulk-apply(fetch 는 brain-dom.js 한 곳 — try/catch + data.success).
 *
 * - 승인: 기준 판 · 화면이 잰 결정 시간(카드를 보인 뒤 누를 때까지) · 등급 B 확인 글을 같이 보낸다(서버가 다시 본다 —
 *   결정한 사람은 서버가 로그인 사용자로만 정한다). 확인 칸을 안 눌렀으면 보내지 않는다.
 * - 고쳐서 승인: 누르면 고칠 칸이 열리고 단추가 '고치기 닫기'로(다시 누르면 닫힘 — F08), '고친 값으로 승인'이 넣는다.
 * - 거절: 까닭 칩 줄을 열고, 칩 하나를 누르면 끝. 나중에 · PC 에서 볼게요: 이 화면에서만 접는다(서버 쓰기 없음).
 * - 표: 체크한 줄만, 확인 창 한 번 뒤(F24) — 안 고친 줄은 50개씩 한꺼번에, 이름을 고친 줄은 하나씩 '고쳐서 승인'.
 * - 등급 A 모두 승인: 확인 창 한 번 뒤 한꺼번에.
 * 오류 글은 서버가 정한 말 그대로(BRAIN_DOC_SYNC 지식 문서 엇갈림 · 기준 판 바뀜 …) 그 제안 줄에 적는다.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var review = window.FOMS_BRAIN_REVIEW;
  var iv = window.FOMS_DS_INBOX_VIEW;
  var tableKit = window.FOMS_DS_INBOX_TABLE;
  if (!dom || !review || !iv) return;

  /**
   * deps: { urls, findView(id), reload(), defer(cardId), status(text, kind) }.
   * 돌려주는 것: { onAct(button), applyTable(button), bulk(ids) }.
   */
  function create(deps) {
    function propStatus(box, text, kind) {
      dom.setStatus(box.querySelector('[data-ds-prop-status]'), text, kind);
    }

    function busy(box, on) {
      Array.prototype.slice.call(box.querySelectorAll('[data-ds-act]')).forEach(function (b) { b.disabled = on; });
    }

    async function send(box, url, body) {
      busy(box, true);
      propStatus(box, '보내는 중…');
      var res = await dom.postJson(url, body);
      if (!res.ok) {
        busy(box, false);
        propStatus(box, res.error, 'error');
        return;
      }
      propStatus(box, (res.data && res.data.message) || '했어요.');
      await deps.reload();
    }

    function viewMs(box) {
      return review.elapsed(box.getAttribute('data-shown-at'), window.performance.now());
    }

    function confirmed(box) {
      var input = box.querySelector('[data-ds-confirm]');
      return !!(input && input.checked);
    }

    function readEdits(box, prop) {
      var values = {};
      Array.prototype.slice.call(box.querySelectorAll('[data-ds-edit]')).forEach(function (input) {
        values[input.getAttribute('data-ds-edit')] = input.value;
      });
      return review.editsFrom(prop, values);
    }

    function apply(box, prop, edits) {
      if (prop.confirm && !confirmed(box)) {
        propStatus(box, '등급 B 제안이에요 — 핵심 값을 보고 확인 칸을 눌러 주세요.', 'error');
        return;
      }
      var body = review.applyBody(prop, { viewMs: viewMs(box), confirmed: confirmed(box), edits: edits });
      send(box, deps.urls.proposals + '/' + prop.id + '/apply', body);
    }

    /** '고쳐서 승인' 열고 닫기(F08). */
    function toggleEdit(box, start) {
      var editor = box.querySelector('[data-ds-edit-box]');
      var save = box.querySelector('[data-ds-act="edit-apply"]');
      var open = !!editor && editor.hidden;
      if (!start.hasAttribute('data-ds-label')) start.setAttribute('data-ds-label', start.textContent);
      if (editor) editor.hidden = !open;
      if (save) save.hidden = !open;
      start.removeChild(start.childNodes[start.childNodes.length - 1]);  // 아이콘은 두고 글만 바꾼다
      start.appendChild(document.createTextNode(open ? '고치기 닫기' : start.getAttribute('data-ds-label')));
      start.setAttribute('aria-expanded', open ? 'true' : 'false');
      if (open) {
        var first = editor.querySelector('[data-ds-edit]');
        if (first) first.focus();
      }
    }

    function onAct(button) {
      var box = button.closest('[data-change-id]');
      var prop = box && deps.findView(box.getAttribute('data-change-id'));
      if (!prop) return;
      var act = button.getAttribute('data-ds-act');
      if (act === 'apply') apply(box, prop, null);
      else if (act === 'edit') toggleEdit(box, button);
      else if (act === 'edit-apply') {
        var edits = readEdits(box, prop);
        if (!edits) { propStatus(box, '고친 값이 처음 제안과 같아요 — 그대로면 승인을 눌러 주세요.', 'error'); return; }
        apply(box, prop, edits);
      } else if (act === 'reject') {
        var chips = box.querySelector('[data-ds-reject-box]');
        if (chips) chips.hidden = !chips.hidden;
      } else if (act === 'reject-code') {
        send(box, deps.urls.proposals + '/' + prop.id + '/reject', { code: button.getAttribute('data-reject-code'), view_ms: viewMs(box) });
      } else if (act === 'later') {
        var card = button.closest('[data-card-id]');
        if (card) deps.defer(card.getAttribute('data-card-id'));
      }
    }

    /** 표의 체크한 줄 승인. */
    async function applyTable(button) {
      var list = button.closest('[data-ds-inbox-cards]') || deps.root;
      var tableStatus = list.querySelector('[data-ds-table-status]');
      var pick = tableKit.collect(list);
      if (!pick.ids.length && !pick.edits.length) { dom.setStatus(tableStatus, '체크한 줄이 없어요.', 'error'); return; }
      if (!window.confirm(iv.confirmTableText(pick.ids.length + pick.edits.length))) return;  // 취소면 안 보낸다(F24)
      button.disabled = true;
      dom.setStatus(tableStatus, '승인하는 중…');
      var done = 0;
      var failed = 0;
      for (var i = 0; i < pick.ids.length; i += 50) {
        var part = pick.ids.slice(i, i + 50);
        var res = await dom.postJson(deps.urls.bulk, { ids: part });
        if (!res.ok) { failed += part.length; continue; }
        done += res.data.applied.length;
        failed += (res.data.failed || []).length;
      }
      for (var j = 0; j < pick.edits.length; j += 1) {
        var view = deps.findView(pick.edits[j].id);
        var edits = {};
        edits[tableKit.prefField] = pick.edits[j].name;
        var one = view && await dom.postJson(deps.urls.proposals + '/' + view.id + '/apply',
                                             review.applyBody(view, { viewMs: 0, confirmed: true, edits: edits }));
        if (one && one.ok) done += 1; else failed += 1;
      }
      await deps.reload();
      deps.status(iv.doneText(done, failed), failed ? 'error' : undefined);
    }

    /** 등급 A 모두 승인 — 확인 창 한 번 뒤. */
    async function bulk(button, ids) {
      if (!ids.length || !window.confirm('등급 A 제안 ' + ids.length + '개를 한꺼번에 승인할까요?')) return;
      button.disabled = true;
      var res = await dom.postJson(deps.urls.bulk, { ids: ids });
      button.disabled = false;
      if (!res.ok) {
        deps.status(res.error, 'error');
        return;
      }
      await deps.reload();
      deps.status(iv.doneText(res.data.applied.length, (res.data.failed || []).length));
    }

    return { onAct: onAct, applyTable: applyTable, bulk: bulk };
  }

  window.FOMS_DS_INBOX_ACT = { create: create };
})();
