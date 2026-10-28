/**
 * 도면 마법사 V2 — 주 그림 크기 막대(오른쪽 칸 '그림 크기' 아래).
 *
 * 사용자 요청 2026-10-28: 숫자가 몇 px 이면 안 읽히는지 기준을 정하자는 물음에 '아냐 컴퍼넌트 사이즈는 자유로 조절 가능하게' →
 * 막대로 크기 정하기를 골랐다. 막대를 끌면 주 그림이 '고르게' 때 높이의 100% ~ 큰 그림 칸이 허락하는 만큼 커지고, 나머지는
 * 남은 자리에 맞춰 줄어든다 — 숫자 8px 기준으로 막지 않는다(계산은 v2-hero.js refine, 값은 시트 폼 v2_hero_size).
 * - 손을 떼면(change) 한 번 다시 배치하고, 되돌리기 한 번이면 돌아간다. 끄는 동안(input)은 % 글자만 바꾼다.
 * - '고르게' 시트에서 끌면 주 그림 크게로 바뀐다. [자동으로] = 폼 값을 지워 예전 자동(숫자 기준 · 1.15배 넘게 커질 때만)으로.
 * - 손잡이로 끌어 바꾸는 것은 그대로 된다(바꾼 그림은 고정 · 나머지가 비켜 다시 놓임 — v2-shell moved).
 *
 * window.FomsV2Size = { render(box, res, api, style) }   res.size = { min, max, pct, manual } (없으면 막대를 숨긴다)
 */
(function () {
  'use strict';
  if (window.FomsV2Size) { return; }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }

  function apply(api, value) {   // value = % · 0 = 자동
    var sh = api.core.sheet();
    if (!sh) { return; }
    var form = sh.form, cur = parseInt(form.v2_hero_size, 10) || 0;
    if (value === cur && !(value && form.v2_style === 'even')) { return; }
    api.core.recordUndo();
    if (value) { form.v2_hero_size = String(value); } else { delete form.v2_hero_size; }
    if (value && form.v2_style === 'even') { form.v2_style = 'hero'; }
    if (api.core.markDirty) { api.core.markDirty(); }   // 배치가 그대로여도 막대 값은 저장한다
    api.arrange('size', {});
  }

  function render(box, res, api, style) {
    if (!box) { return; }
    var s = res && res.size, even = style === 'even', can = api.core.canSave();
    box.textContent = '';
    box.hidden = !s;
    if (!s) { return; }
    var head = el('div', 'dws-v2-size-head'), val = el('span', 'dws-v2-size-val', s.pct + '%'), range = el('input', 'dws-v2-size-range');
    head.appendChild(el('span', 'dws-v2-size-name', '주 그림 크기'));
    head.appendChild(val);
    if (s.manual && !even) {
      var auto = el('button', 'dws-v2-size-auto', '자동으로');
      auto.type = 'button';
      auto.title = '막대 값을 지우고 자동으로 정한 크기로 돌아가요';
      auto.disabled = !can;
      auto.addEventListener('click', function () { apply(api, 0); });
      head.appendChild(auto);
    }
    range.type = 'range';
    range.min = String(s.min);
    range.max = String(s.max);
    range.step = '1';
    range.value = String(Math.min(s.max, Math.max(s.min, s.pct)));
    range.disabled = !can;
    range.setAttribute('aria-label', '주 그림 크기(고르게 때 크기 대비 %)');
    range.addEventListener('input', function () { val.textContent = range.value + '%'; });
    range.addEventListener('change', function () { apply(api, parseInt(range.value, 10) || 0); });
    var ends = el('div', 'dws-v2-size-ends');
    ends.appendChild(el('span', null, '고르게 때 크기'));
    ends.appendChild(el('span', null, '칸 가득'));
    box.appendChild(head);
    box.appendChild(range);
    box.appendChild(ends);
    box.appendChild(el('p', 'dws-v2-size-note', even ? '지금은 고르게예요 · 끌면 주 그림 크게로 바뀌어요'
      : (s.manual ? '직접 정한 크기예요 · 나머지는 남은 자리에 맞춰 줄어요' : '자동으로 정한 크기예요 · 끌어서 바꿔요')));
  }

  window.FomsV2Size = { render: render };
})();
