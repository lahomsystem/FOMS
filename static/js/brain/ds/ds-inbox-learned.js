/**
 * 새 승인 대기 화면의 'AI 가 배운 것' 보기(?tab=learned — ADMIN 만, 사장님 2026-11-19 '매번 승인 대신 즉시 반영 · 내가 확인하고
 * 추후 수정 및 삭제'). GET /api/brain/learned(상담에서 배워 승인 없이 바로 넣은 지식 — 아직 안 본 것 먼저 · 새 것부터),
 * [맞아요] = POST …/<번호>/seen(지식은 그대로) · [고치기] = POST …/<번호>/fix {after: {text}} · [지우기] = POST …/<번호>/undo
 * (새 지식은 지우고, 고친 것은 앞 글로 되돌린다 — 한 번 더 눌러야 지운다).
 * 글은 textContent 만 · 인라인 스타일 없음 · 전역 듣개는 한 번만(window.__FOMS_DS_LEARNED_BOUND).
 */
(function () {
  'use strict';

  var dom = window.FOMS_BRAIN_DOM;
  var view = window.FOMS_BRAIN_VIEW;
  var kit = window.FOMS_DS_INBOX_KIT;
  if (!dom || !view || !kit || window.__FOMS_DS_LEARNED_BOUND) return;
  var c = kit.ctx();
  var list = c && c.root.querySelector('[data-ds-learned]');
  if (!list || !c.urls.learned) return;
  window.__FOMS_DS_LEARNED_BOUND = true;

  var line = c.root.querySelector('[data-ds-learned-line]');
  var status = c.root.querySelector('[data-ds-learned-status]');
  var items = {};
  var STATE_NOTES = { changed: '그 뒤에 사람이 고친 지식이에요. 지금 글: ', gone: '지금은 없는 지식이에요.' };

  function act(text, name, cls, iconName) {
    var button = kit.button(text, null, cls, iconName);
    button.setAttribute('data-learned-act', name);
    return button;
  }

  function renderRow(item) {
    var li = dom.el('li', { cls: 'f-card f-card-compact f-col fb-learned' + (item.seen ? ' is-seen' : ''),
                            attrs: { 'data-learned-id': item.id } });
    var href = item.state === 'gone' ? null : view.itemHref(c.urls.itemBase, item.key);
    var head = dom.el('div', { cls: 'f-row f-gap4', children: [
      dom.el('span', { cls: 'f-tag f-tag-primary', text: item.kind }), kit.typeTag(c, item, null),
      dom.el(href ? 'a' : 'span', { cls: 'f-strong', text: item.title, attrs: { href: href } })] });
    if (item.seen) head.appendChild(dom.el('span', { cls: 'f-tag f-tag-success', text: '봤어요' }));
    li.appendChild(head);
    li.appendChild(dom.el('p', { text: item.text, attrs: { 'data-learned-text': '1' } }));
    if (item.before) li.appendChild(dom.el('p', { cls: 'f-small f-muted', text: '고치기 앞 글: ' + item.before }));
    if (STATE_NOTES[item.state]) {
      li.appendChild(dom.el('p', { cls: 'f-small fb-late', text: STATE_NOTES[item.state] + (item.now || '') }));
    }
    li.appendChild(dom.el('p', { cls: 'f-small f-muted', text: item.at + ' · ' + item.why }));
    var bar = dom.el('div', { cls: 'f-actions', attrs: { 'data-learned-bar': '1' } });
    if (!item.seen) bar.appendChild(act('맞아요', 'seen', 'f-btn-primary', 'tick'));
    if (item.can_fix) bar.appendChild(act('고치기', 'edit', '', 'edit'));
    bar.appendChild(act('지우기', 'undo', 'f-btn-minimal', 'cross'));
    li.appendChild(bar);
    li.appendChild(kit.statusLine('data-learned-status'));
    return li;
  }

  function setCount(n) {
    Array.prototype.slice.call(document.querySelectorAll('[data-ds-count="learned"]')).forEach(function (node) {
      node.textContent = String(n);
    });
  }

  async function load() {
    dom.setStatus(status, '불러오는 중…');
    var res = await dom.getJson(c.urls.learned);
    if (!res.ok) {
      dom.setStatus(status, res.error, 'error');
      return;
    }
    items = {};
    dom.clear(list);
    res.data.items.forEach(function (item) {
      items[item.id] = item;
      list.appendChild(renderRow(item));
    });
    if (line) line.textContent = res.data.counts.line;
    dom.setStatus(status, '');
    setCount(res.data.counts.new);
  }

  /** [고치기] — 줄 안에 글 칸을 연다(지금 글을 채워서). */
  function openEditor(row, item) {
    if (row.querySelector('[data-learned-editor]')) return;
    var area = dom.el('textarea', { cls: 'f-input', attrs: { rows: '4', maxlength: '2000', 'aria-label': '고친 글' } });
    area.value = item.now || item.text;
    var box = dom.el('div', { cls: 'f-col f-gap4', attrs: { 'data-learned-editor': '1' }, children: [area,
      dom.el('div', { cls: 'f-actions', children: [act('고쳐 넣기', 'fix', 'f-btn-primary', 'tick'), act('그만', 'cancel', 'f-btn-minimal')] })] });
    row.insertBefore(box, row.querySelector('[data-learned-status]'));
    area.focus();
  }

  async function send(row, item, path, body, button) {
    var rowStatus = row.querySelector('[data-learned-status]');
    button.disabled = true;
    dom.setStatus(rowStatus, '보내는 중…');
    var res = await dom.postJson(c.urls.learned + '/' + item.id + '/' + path, body || {});
    if (!res.ok) {
      button.disabled = false;
      dom.setStatus(rowStatus, res.error, 'error');
      return;
    }
    dom.setStatus(rowStatus, res.data.message);
    row.classList.add('is-done');
    window.setTimeout(load, 600);
  }

  list.addEventListener('click', function (event) {
    var button = event.target.closest('[data-learned-act]');
    var row = button && button.closest('[data-learned-id]');
    var item = row && items[row.getAttribute('data-learned-id')];
    if (!item || !list.contains(button)) return;
    var name = button.getAttribute('data-learned-act');
    var editor = row.querySelector('[data-learned-editor]');
    if (name === 'seen') return void send(row, item, 'seen', {}, button);
    if (name === 'edit') return void openEditor(row, item);
    if (name === 'cancel') return void (editor && editor.remove());
    if (name === 'fix') {
      var text = editor ? editor.querySelector('textarea').value.trim() : '';
      if (!text) return void dom.setStatus(row.querySelector('[data-learned-status]'), '고친 글을 적어 주세요.', 'error');
      return void send(row, item, 'fix', { after: { text: text } }, button);
    }
    if (name === 'undo') {  // 한 번 더 눌러야 지운다
      button.setAttribute('data-learned-act', 'undo-sure');
      button.lastChild.textContent = '정말 지울까요? 한 번 더 누르면 지워요';
      return;
    }
    if (name === 'undo-sure') send(row, item, 'undo', {}, button);
  });
  load();
})();
