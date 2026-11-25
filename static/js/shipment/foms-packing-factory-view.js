/**
 * 출고 패킹 공장마다 — 줄 · 묶음 · 단추 그리기(DOM 만, 상태 · 요청 없음). 부르는 쪽 = foms-packing-factory.js.
 * 설계서 2026-11-23 '승인 때 고친 것' 6. 옛 모듈(foms-packing.js)과 같은 칸 이름(.foms-packing-row 등)을 써서 모양을 같이 하고,
 * 누르는 표식은 data-pf-* 만 쓴다(옛 모듈 리스너가 반응하지 않게).
 */
(function () {
  'use strict';

  if (window.FomsPackingFactoryView) return;

  var ISSUE = { missing: '미입고', damaged: '파손', short: '수량 부족' };

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) n.className = cls;
    if (text != null) n.textContent = text;
    return n;
  }
  function attr(n, name, value) { n.setAttribute(name, value == null ? '' : String(value)); return n; }
  // 글 안의 "1공장" · "2공장"을 공장 칩으로(서버 거르개 factory_chips 와 같은 꼴 — foms-factory-chip.css, 사장님 2026-11-24 식별성)
  function facText(n, text) {
    n.textContent = '';
    String(text).split(/([12]공장)/).forEach(function (part, i) {
      if (part) n.appendChild(i % 2 ? el('em', 'foms-fac foms-fac--' + part.charAt(0), part) : document.createTextNode(part));
    });
    return n;
  }

  // ISO → "2026. 11. 24. 오전 09:40"(옛 모듈 출발 보고 글과 같은 꼴) · hm → "09:10"
  function when(iso) {
    var d = new Date(iso);
    if (!iso || isNaN(d.getTime())) return '';
    return d.toLocaleDateString('ko-KR', { timeZone: 'Asia/Seoul' }) + ' ' +
      d.toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit' });
  }
  function hm(iso) {
    var d = new Date(iso);
    if (!iso || isNaN(d.getTime())) return '';
    // hourCycle h23 — hour12:false 는 브라우저에 따라 자정을 '24:30'으로 그린다
    return d.toLocaleTimeString('ko-KR', { timeZone: 'Asia/Seoul', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
  }

  function issueBox(it) {
    var wrap = el('div', 'foms-packing-row__issue');
    var toggle = attr(attr(el('button', 'foms-packing-row__issue-btn', '누락 신고'), 'data-pf-issue-toggle'), 'aria-expanded', 'false');
    toggle.type = 'button';
    var chips = attr(attr(el('div', 'foms-packing-issue-chips'), 'role', 'group'), 'aria-label', '누락 사유 선택');
    chips.hidden = true;
    Object.keys(ISSUE).forEach(function (k) {
      var chip = attr(el('button', 'foms-packing-issue-chip' + (it.issue === k ? ' foms-packing-issue-chip--active' : ''), ISSUE[k]), 'data-pf-issue', k);
      chip.type = 'button';
      chips.appendChild(chip);
    });
    wrap.appendChild(toggle);
    wrap.appendChild(chips);
    return wrap;
  }

  function row(it, can) {
    var li = attr(el('li', 'foms-packing-row foms-pf__row' + (it.checked ? ' foms-packing-row--checked' : '') +
      (it.issue ? ' foms-packing-row--issue' : '')), 'data-pf-key', it.key);
    var main = el('label', 'foms-packing-row__main foms-pf__main');
    var cb = attr(el('input', 'foms-packing-row__check'), 'data-pf-check');
    cb.type = 'checkbox';
    cb.checked = !!it.checked;
    cb.disabled = !can;
    var body = el('span', 'foms-packing-row__body');
    body.appendChild(el('span', 'foms-packing-row__label', it.label));
    if (it.issue && ISSUE[it.issue]) body.appendChild(el('span', 'foms-packing-row__issue-label', '누락 · ' + ISSUE[it.issue]));
    if (it.checked && it.by_name) body.appendChild(el('span', 'foms-packing-row__meta', it.by_name + (it.at ? ' · ' + when(it.at) : '')));
    main.appendChild(cb);
    main.appendChild(body);
    main.appendChild(el('span', 'foms-packing-row__qty', '×' + (it.qty || 1)));
    li.appendChild(main);
    if (can) li.appendChild(issueBox(it));
    return li;
  }

  function group(g, items) {
    var sec = attr(el('section', 'foms-pf__g foms-pf__g--' + g.factory), 'aria-label', g.label);
    var head = el('h6', 'foms-pf__gh');
    head.appendChild(el('b', 'foms-fac foms-fac--' + g.factory, g.label));
    head.appendChild(el('span', 'foms-pf__n', g.checked + '/' + g.total));
    sec.appendChild(head);
    if (!g.can_check) sec.appendChild(el('p', 'foms-pf__note', g.label + ' 줄은 ' + g.label + '에서 체크해요.'));
    var list = attr(el('ul', 'foms-packing-list foms-pf__list'), 'aria-label', g.label + ' 패킹 체크리스트');
    items.forEach(function (it) { list.appendChild(row(it, g.can_check)); });
    sec.appendChild(list);
    return sec;
  }

  function addForm(d) {
    var form = attr(attr(el('form', 'foms-packing-add foms-pf__add'), 'data-pf-add'), 'autocomplete', 'off');
    var label = attr(attr(el('input', 'form-control foms-packing-add__label'), 'placeholder', '항목 추가 (예: 상판 유리)'), 'aria-label', '추가 항목 이름');
    label.name = 'label';
    form.appendChild(label);
    if (d.can_check.length > 1) {
      var pick = attr(el('select', 'form-select foms-pf__addf'), 'aria-label', '공장');
      pick.name = 'factory';
      (d.groups || []).forEach(function (g) {
        if (!g.can_check) return;
        var opt = el('option', null, g.label);
        opt.value = g.factory;
        pick.appendChild(opt);
      });
      form.appendChild(pick);
    }
    var qty = attr(attr(attr(el('input', 'form-control foms-packing-add__qty'), 'min', 1), 'step', 1), 'aria-label', '수량');
    qty.type = 'number';
    qty.name = 'qty';
    qty.value = '1';
    form.appendChild(qty);
    var btn = el('button', 'foms-btn foms-btn--secondary foms-btn--sm foms-packing-add__btn', '추가');
    btn.type = 'submit';
    form.appendChild(btn);
    return form;
  }

  function actions(d) {
    var bar = el('div', 'foms-packing-actions foms-pf__acts');
    (d.groups || []).forEach(function (g) {
      var b = attr(attr(el('button', 'foms-btn foms-btn--primary foms-packing-depart foms-pf__load foms-pf__load--' + g.factory),
        'data-pf-load', g.factory), 'aria-live', 'polite');
      b.type = 'button';
      if (g.loaded) {
        b.disabled = true;
        b.classList.add('foms-packing-depart--done');
        facText(b, g.label + ' 상차 완료 ' + hm(g.loaded.at) + (g.loaded.by_name ? ' ' + g.loaded.by_name : ''));
      } else {
        b.disabled = !g.can_check || g.checked < g.total || g.made === false;
        facText(b, g.label + ' 상차 완료');
      }
      bar.appendChild(b);
    });
    // 제작 완료 전 공장은 단추가 꺼진 까닭을 단추 바로 아래 한 줄로(사장님 2026-11-24 — 상차 완료는 제작 완료 뒤에만)
    (d.groups || []).forEach(function (g) {
      if (!g.loaded && g.can_check && g.made === false) {
        bar.appendChild(facText(attr(el('p', 'foms-pf__why'), 'data-pf-why', g.factory), g.label + ' 제작 완료 뒤에 상차 완료할 수 있어요.'));
      }
    });
    return bar;
  }

  window.FomsPackingFactoryView = {
    ISSUE: ISSUE, el: el, attr: attr, facText: facText, when: when, hm: hm, group: group, addForm: addForm, actions: actions
  };
})();
