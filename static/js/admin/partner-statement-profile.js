/**
 * 거래명세서 양식 정보 — ADMIN(설계서 docs/specs/2026-11-03-partner-statement_SPEC.md §5.8).
 * GET data-api-url → 칸 목록(이름 · 화면 이름 · 글자 수 · 여러 줄)과 값을 그린다. 저장 = POST {supplier, receiver, version}.
 */
(function () {
  'use strict';

  var root = document.querySelector('[data-sp-root]');
  if (!root) return;
  var url = root.getAttribute('data-api-url');
  var version = 0;

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text != null) node.textContent = String(text);
    return node;
  }

  function status(text) { root.querySelector('[data-sp-status]').textContent = text || ''; }

  async function call(body) {
    var res;
    try {
      res = await fetch(url, { method: body ? 'POST' : 'GET', credentials: 'same-origin',
        headers: { Accept: 'application/json', 'Content-Type': 'application/json' }, body: body ? JSON.stringify(body) : undefined });
    } catch (_) {
      return { ok: false, error: '서버에 닿지 못했습니다. 인터넷 연결을 확인해 주세요.' };
    }
    var data = null;
    try { data = await res.json(); } catch (_) { data = null; }
    if (!data || !data.success) return { ok: false, error: (data && data.error) || '저장하지 못했습니다. 잠시 뒤 다시 해 주세요.' };
    return { ok: true, data: data.data || {} };
  }

  function fields(box, group, list, values) {
    box.replaceChildren();
    list.forEach(function (f) {
      var id = 'sp-' + group + '-' + f[0];
      var wrap = box.appendChild(el('div', 'foms-sp__field'));
      var label = wrap.appendChild(el('label', 'form-label small mb-1', f[1]));
      label.htmlFor = id;
      var input = wrap.appendChild(el(f[3] ? 'textarea' : 'input', 'form-control form-control-sm'));
      input.id = id;
      input.name = group + '.' + f[0];
      input.maxLength = f[2];
      if (f[3]) input.rows = 3;
      input.value = values[f[0]] || '';
    });
  }

  function collect(group) {
    var out = {};
    root.querySelectorAll('[name^="' + group + '."]').forEach(function (n) { out[n.name.slice(group.length + 1)] = n.value; });
    return out;
  }

  function draw(data) {
    version = data.version;
    fields(root.querySelector('[data-sp-supplier]'), 'supplier', data.fields.supplier, data.supplier);
    fields(root.querySelector('[data-sp-receiver]'), 'receiver', data.fields.receiver, data.receiver);
    root.querySelector('[data-sp-org]').textContent = '상호 · 등록번호는 협력사 정보를 씁니다: ' + data.org.name +
      (data.org.biz_reg_no ? ' · ' + data.org.biz_reg_no : ' · 등록번호 없음(협력사 관리에서 넣어 주세요)');
  }

  root.querySelector('[data-sp-form]').addEventListener('submit', async function (ev) {
    ev.preventDefault();
    status('저장하는 중…');
    var res = await call({ supplier: collect('supplier'), receiver: collect('receiver'), version: version });
    if (!res.ok) { status(res.error); return; }
    draw(res.data);
    status('✓ 저장했습니다.');
  });

  call().then(function (res) { if (res.ok) draw(res.data); else status(res.error); });
})();
