/**
 * 항목 카드의 제안 단추(HAUD master brain 설계서 7.5 화면 3 → 4 · 7.7 이름 있는 액션 · 속성 틀) — templates/brain/item.html.
 *
 * - 단추는 액션 이름을 단다(data-brain-propose-open="propose_edit" | "propose_retire" | "propose_delete").
 * - '고칠 말 제안': 이름 · 글 · 유효 기간 · 그 유형 속성 틀 칸(data-brain-field · data-datatype — 서버가 틀에서 그림)을 지금 값
 *   (data-current JSON → safeJsonParse)으로 채우고, 바꾼 칸만 자료형 값으로
 *   POST /api/brain/proposals {action: 'propose_edit', key, base_version, after, reason} 로 보낸다(제안함으로 — 바로 안 바뀜).
 * - '은퇴 제안' · '지우기 제안': 까닭만 받아 {action: 'propose_retire' | 'propose_delete'}.
 * - 이력의 되돌리기 단추: 옛 값을 새 제안으로 {action: 'item_rollback', to_version}.
 * 쓰기는 brain-dom.js postJson 한 곳(try/catch + data.success, CSRF 는 공용 부트스트랩). 글은 textContent · value 로만.
 */
(function () {
  'use strict';

  if (window.__FOMS_BRAIN_ITEM_ACTIONS_BOUND) return;
  var root = document.querySelector('[data-brain-card]');
  var dom = window.FOMS_BRAIN_DOM;
  var review = window.FOMS_BRAIN_REVIEW;
  if (!root || !dom || !review) return;
  window.__FOMS_BRAIN_ITEM_ACTIONS_BOUND = true;

  var key = root.getAttribute('data-brain-key');
  var version = Number(root.getAttribute('data-brain-version'));
  var current = dom.safeJsonParse(root.getAttribute('data-current'), {});
  var url = root.getAttribute('data-proposals-url');
  var inboxPage = root.getAttribute('data-inbox-page');
  var rollbackAction = root.getAttribute('data-rollback-action') || 'item_rollback';
  var form = root.querySelector('[data-brain-propose-form]');
  var fields = root.querySelector('[data-brain-propose-fields]');
  var title = root.querySelector('[data-brain-propose-title]');
  var status = root.querySelector('[data-brain-propose-status]');
  var rollbackStatus = root.querySelector('[data-brain-rollback-status]');
  var TITLES = { propose_edit: '고칠 칸만 바꾸고 까닭을 적어 주세요.',
                 propose_retire: '은퇴 제안 — 까닭을 적어 주세요(승인되면 에이전트가 더는 쓰지 않아요).',
                 propose_delete: '지우기 제안 — 까닭을 적어 주세요(승인되면 지금 판과 이어진 링크가 닫혀요. 이력은 남아요).' };
  var action = 'propose_edit';
  if (!form) return;

  function inputs() {
    return Array.prototype.slice.call(form.querySelectorAll('[data-brain-field]'));
  }

  function shown(value) {
    if (value === null || value === undefined) return '';
    return Array.isArray(value) ? value.join(', ') : String(value);
  }

  function fill() {
    inputs().forEach(function (box) { box.value = shown(current[box.getAttribute('data-brain-field')]); });
    form.querySelector('[name="reason"]').value = '';
  }

  function open(name) {
    action = name;
    fill();
    fields.hidden = name !== 'propose_edit';
    title.textContent = TITLES[name] || '';
    form.hidden = false;
    dom.setStatus(status, '');
    form.querySelector(name === 'propose_edit' ? '[data-brain-field="text"]' : '[name="reason"]').focus();
  }

  /** 칸 글 → 자료형 값 모음(이름 · 글은 글 그대로). */
  function typedValues() {
    var values = {};
    inputs().forEach(function (box) {
      var name = box.getAttribute('data-brain-field');
      var datatype = box.getAttribute('data-datatype') || 'text';
      values[name] = name === 'text' || name === 'name' ? box.value : review.fieldValue(datatype, box.value);
    });
    return values;
  }

  function done(res, box) {
    if (!res.ok) {
      var problems = res.data && res.data.problems ? ' (' + res.data.problems.join(' · ') + ')' : '';
      dom.setStatus(box, res.error + problems, 'error');
      return false;
    }
    dom.clear(box);
    box.appendChild(document.createTextNode(res.data.message + ' 제안 ' + res.data.change_id + '번 — '));
    box.appendChild(dom.el('a', { text: '제안함에서 보기', attrs: { href: inboxPage } }));
    return true;
  }

  async function submit(event) {
    event.preventDefault();
    var body = { action: action, key: key, base_version: version,
                 reason: form.querySelector('[name="reason"]').value.trim() };
    if (!body.reason) {
      dom.setStatus(status, '까닭을 적어 주세요.', 'error');
      return;
    }
    if (action === 'propose_edit') {
      var base = {};
      Object.keys(current).forEach(function (name) {
        base[name] = current[name] === undefined || current[name] === '' ? null : current[name];
      });
      body.after = review.changedAfter(base, typedValues());
      if (!body.after) {
        dom.setStatus(status, '바꾼 칸이 없어요.', 'error');
        return;
      }
    }
    var submitButton = form.querySelector('[data-brain-propose-submit]');
    submitButton.disabled = true;
    dom.setStatus(status, '보내는 중…');
    var res = await dom.postJson(url, body);
    submitButton.disabled = false;
    if (done(res, status)) form.hidden = true;
  }

  async function rollbackTo(button) {
    var target = Number(button.getAttribute('data-brain-rollback-to'));
    button.disabled = true;
    dom.setStatus(rollbackStatus, '보내는 중…');
    var res = await dom.postJson(url, { action: rollbackAction, key: key, to_version: target,
                                        reason: '판 ' + target + ' 의 값으로 되돌리기' });
    button.disabled = false;
    done(res, rollbackStatus);
  }

  root.addEventListener('click', function (event) {
    var opener = event.target.closest('[data-brain-propose-open]');
    if (opener && root.contains(opener)) {
      open(opener.getAttribute('data-brain-propose-open'));
      return;
    }
    if (event.target.closest('[data-brain-propose-cancel]')) {
      form.hidden = true;
      return;
    }
    var back = event.target.closest('[data-brain-rollback-to]');
    if (back && root.contains(back)) rollbackTo(back);
  });
  form.addEventListener('submit', submit);
  if (window.location.hash === '#brain-card-propose') open('propose_edit');
})();
