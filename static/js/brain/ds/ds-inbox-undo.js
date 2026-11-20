/**
 * 새 승인 대기 화면 — 방금 정한 것 되돌리기(사장님 2026-11-20 "잘못 선택했는데 고치려면?" · 상담 원장 D275).
 *
 * 거절 칩 · ③ 질문 답(회사 지식이 맞아요 · 바깥 글이 맞아요 · 둘 다 맞아요)을 누른 바로 뒤, 알림 줄 아래 한 줄
 * [data-ds-inbox-undo] 에 '방금 정한 것 「제목」 [되돌리기]' 를 보인다. 누르면 POST /api/brain/proposals/<번호>/reopen
 * {undo_edit} — 서버가 내가 하루 안에 거절한 제안만 다시 열고, 그 답으로 넣은 지식 고침(undo_edit)은 앞 글로 되돌린다.
 * 새로 고쳐도 남게 이 탭에만 기억한다(sessionStorage · 30분 — 저장이 막히면 이 화면에서만). 다음 결정이 오면 그 결정으로
 * 바뀐다(되돌릴 수 있는 것은 마지막 하나).
 * FOMS_DS_INBOX_UNDO = { offer({id, edit, title}), clear() }. 글은 textContent 만 · 요청은 brain-dom.js 한 곳 · 듣개는 한 번만.
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var kit = window.FOMS_DS_INBOX_KIT;
  var c = dom && kit ? kit.ctx() : null;
  if (!c || window.__FOMS_DS_INBOX_UNDO_BOUND) return;
  var line = c.root.querySelector('[data-ds-inbox-undo]');
  var button = line && line.querySelector('[data-ds-inbox-undo-do]');
  if (!button) return;
  window.__FOMS_DS_INBOX_UNDO_BOUND = true;

  var KEEP_MS = 30 * 60 * 1000;
  var shell = c.root.closest('[data-ds-shell]') || document.body;
  var key = 'foms-ds-inbox-undo:' + (shell.getAttribute('data-ds-uid') || 'anon');
  var text = line.querySelector('[data-ds-inbox-undo-text]');
  var last = null;

  function store(value) {
    try {
      if (value) window.sessionStorage.setItem(key, JSON.stringify(value));
      else window.sessionStorage.removeItem(key);
    } catch (e) {
      return;  // 저장 막힘 — 이 화면에서만 기억
    }
  }

  function read() {
    try {
      var value = JSON.parse(window.sessionStorage.getItem(key) || 'null');
      return value && Number(value.id) > 0 && Date.now() - Number(value.at) < KEEP_MS ? value : null;
    } catch (e) {
      return null;  // 저장 막힘 · 깨진 값 = 기억 없음
    }
  }

  function show() {
    line.hidden = !last;
    if (text) text.textContent = last ? '방금 정한 것' + (last.title ? ' 「' + last.title + '」' : '') : '';
    button.disabled = false;
  }

  /** 방금 한 결정 하나를 되돌릴 수 있게 보인다 — id 는 닫힌 제안, edit 는 그 답으로 넣은 지식 고침(없으면 비움). */
  function offer(info) {
    if (!info || !(Number(info.id) > 0)) return;
    last = { id: Number(info.id), edit: Number(info.edit) > 0 ? Number(info.edit) : null,
             title: String(info.title || '').slice(0, 60), at: Date.now() };
    store(last);
    show();
  }

  function clear() {
    last = null;
    store(null);
    show();
  }

  async function undo() {
    if (!last || button.disabled) return;
    var status = c.root.querySelector('[data-ds-inbox-status]');
    button.disabled = true;
    dom.setStatus(status, '되돌리는 중…');
    var res = await dom.postJson(c.urls.proposals + '/' + last.id + '/reopen', last.edit ? { undo_edit: last.edit } : {});
    if (!res.ok) {
      var gone = res.status === 404 || (res.data && res.data.code === 'BRAIN_TARGET');  // 이미 되돌렸거나 되돌릴 수 없는 것
      if (gone) clear(); else button.disabled = false;
      dom.setStatus(status, res.error, 'error');
      return;
    }
    clear();
    var inbox = window.FOMS_DS_INBOX;
    if (inbox && inbox.reload) await inbox.reload();
    dom.setStatus(status, (res.data && res.data.message) || '되돌렸어요 — 다시 정해 주세요.');
  }

  button.addEventListener('click', undo);
  last = read();
  show();
  window.FOMS_DS_INBOX_UNDO = { offer: offer, clear: clear };
})();
