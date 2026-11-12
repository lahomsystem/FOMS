/**
 * 태블릿 가로 출고 탭 — 시공자 칸 이름판 (설계서 2026-11-09-tablet-production-ui_SPEC §14.3, 시안 16n).
 * 하루치 출고표(tablet_ship_grid.html)의 시공자 칸 단추(button[data-ship-worker-cell])를 누르면 그 칸 왼쪽에
 * 이름판을 띄운다. 이름을 누르면 그 줄의 이름 배열에 넣거나 빼고 바로 저장한다(POST /api/erp/shipment/update/<id>
 * — 보낸 키만 바뀜, settings_version 으로 동시 수정 막기, Idempotency-Key 로 중복 막기, CSRF 머리글은
 * csrf_bootstrap 이 fetch 를 감싸 싣는다 — tablet-domain-sheets.js 의 shipment-save 와 같은 길).
 * 판을 닫을 때(바깥 누름 · 닫기 · Esc) 바뀐 것이 있으면 그날 화면을 다시 받아 묶음을 새로 그린다(묶음 · 색은 서버 한 곳).
 * 시트와 안 겹치는 이유: tablet-side-sheet.js 는 줄 안 button 누름을 시트 대상에서 뺀다. 판이 열린 동안의 바깥
 * 누름은 여기서 먼저(capture) 받아 판만 닫고 삼킨다. 문서 위임 + 싱글턴, 실리는 곳 = shipment-entry.js CHAIN.
 */
(function () {
  'use strict';
  if (window.__FOMS_SHIP_ASSIGN_BOUND) return;
  window.__FOMS_SHIP_ASSIGN_BOUND = true;

  var MAX_WORKERS = 10;
  // pop = 열린 판, cell = 판을 연 시공자 칸 단추, people = 판 자료(data-ship-people), changed = 저장한 것이 있음
  var pop = null, cell = null, people = [], busy = false, changed = false;

  function safeJsonParse(text, fallback) {
    try { var v = JSON.parse(text); return v == null ? fallback : v; } catch (e) { return fallback; }
  }
  function esc(s) {
    return String(s == null ? '' : s).replace(/[&<>"']/g, function (c) {
      return { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c];
    });
  }
  // 화면 크기(--foms-ui-zoom)가 붙으면 rect · scroll · innerWidth 는 보이는 px, style 은 배율 전 px 다.
  function uiZoom() {
    var z = typeof window.fomsUiZoom === 'function' ? Number(window.fomsUiZoom()) : 1;
    return z > 0 ? z : 1;
  }
  function newKey() {
    var c = window.crypto;
    return c && typeof c.randomUUID === 'function' ? c.randomUUID() : 'ship-' + Date.now() + '-' + Math.random().toString(16).slice(2);
  }
  function cellNames(btn) {
    var arr = safeJsonParse(btn.getAttribute('data-workers') || '[]', []);
    return Array.isArray(arr) ? arr.map(function (n) { return String(n || '').trim(); }).filter(Boolean) : [];
  }
  // 판에 없는 이름(직접 쓰기)은 다음 색으로 끝에 붙인다(닫으면 서버가 다시 정한다).
  function ensurePerson(name) {
    var p = people.filter(function (x) { return String(x.name).trim() === name; })[0];
    if (!p) {
      p = { name: name, count: 0, units: 0, capacity: null, over: false, off: false, color_index: people.length % 10 + 1 };
      people.push(p);
    }
    return p;
  }
  function personLine(p) {
    if (p.off) return '쉼';
    return p.count + '건' + (p.units > 0.05 ? ' · ' + (Math.round(p.units * 10) / 10).toFixed(1) + '자' : '');
  }
  function circled(n) {
    return n >= 1 && n <= 20 ? String.fromCharCode(0x2460 + n - 1) : String(n);
  }
  function renderGrid() {
    var on = cellNames(cell);
    var html = people.map(function (p) {
      var isOn = on.indexOf(String(p.name).trim()) >= 0;
      var off = p.off && !isOn;
      return '<button type="button" class="foms-ship-names__nb' + (isOn ? ' is-on' : '') + (off ? ' is-off' : '') +
        '" data-ship-name="' + esc(p.name) + '" data-ship-color="' + esc(p.color_index) + '"' +
        (off ? ' disabled' : '') + ' aria-pressed="' + (isOn ? 'true' : 'false') + '"><b>' + esc(p.name) +
        '</b><small' + (p.over && !p.off ? ' class="is-over"' : '') + '>' + esc(personLine(p)) + '</small></button>';
    }).join('');
    pop.querySelector('.foms-ship-names__grid').innerHTML = html;
  }
  function renderCell(btn, names) {
    btn.setAttribute('data-workers', JSON.stringify(names));
    btn.classList.add('is-top', 'is-bottom');
    btn.classList.toggle('is-empty', !names.length);
    if (!names.length) {
      btn.innerHTML = '<span class="foms-tablet-shipgrid__add">＋ 시공자</span>';
      return;
    }
    btn.innerHTML = names.slice(0, 2).map(function (n, i) {
      var p = ensurePerson(n);
      var more = i === 1 && names.length > 2 ? ' 외 ' + (names.length - 2) : '';
      return '<span class="foms-tablet-shipgrid__who" data-ship-color="' + esc(p.color_index) + '">' + esc(n) + more + '</span>';
    }).join('');
  }
  // 사람별 건수 · 자수를 고친다. 자수 = 줄 자수 ÷ 그 줄 사람 수(D25), AS 줄은 건수만.
  function applyCounts(btn, before, after) {
    var units = parseFloat(btn.getAttribute('data-units') || '0') || 0;
    var isAs = btn.getAttribute('data-is-as') === '1';
    function bump(list, sign) {
      var share = isAs || !list.length ? 0 : units / list.length;
      list.forEach(function (n) {
        var p = ensurePerson(n);
        p.count = Math.max(0, p.count + sign);
        p.units = Math.max(0, p.units + sign * share);
        p.over = p.capacity != null && p.units > p.capacity;
      });
    }
    bump(before, -1);
    bump(after, 1);
  }
  function setMsg(text) {
    var el = pop && pop.querySelector('.foms-ship-names__msg');
    if (el) el.textContent = text || '';
  }
  function setBusy(on) {
    busy = on;
    if (pop) pop.classList.toggle('is-busy', on);
  }
  function save(names) {
    if (busy || !cell) return;
    var btn = cell;
    var before = cellNames(btn);
    if (before.join('|') === names.join('|')) return;
    var body = { construction_workers: names };
    var ver = btn.getAttribute('data-version');
    if (ver) body.settings_version = Number(ver);
    setBusy(true);
    setMsg('');
    fetch('/api/erp/shipment/update/' + encodeURIComponent(btn.getAttribute('data-order-id')), {
      method: 'POST',
      credentials: 'same-origin',
      headers: { 'Content-Type': 'application/json', 'X-Requested-With': 'XMLHttpRequest', 'Idempotency-Key': newKey() },
      body: JSON.stringify(body)
    }).then(function (res) {
      return res.json().catch(function () { return { success: false, message: '서버 응답 형식 오류' }; })
        .then(function (data) { return { status: res.status, data: data || {} }; });
    }).then(function (result) {
      setBusy(false);
      var data = result.data;
      if (result.status === 409) {
        setMsg('다른 사람이 먼저 고쳤어요. 다시 받을게요');
        changed = true;
        var mine = pop;
        window.setTimeout(function () { if (pop === mine) close(); }, 1200);
        return;
      }
      if (result.status === 403 || !data.success) {
        setMsg(result.status === 403 ? (data.message || '권한이 없습니다.') : '오류: ' + (data.message || '저장 실패'));
        return;
      }
      var nv = data.data && data.data.version;
      if (nv != null) btn.setAttribute('data-version', String(nv));
      applyCounts(btn, before, names);
      renderCell(btn, names);
      changed = true;
      if (pop && cell === btn) renderGrid();
    }).catch(function (err) {
      setBusy(false);
      console.error('[tablet-ship-assign] 시공자 저장 실패:', err);
      setMsg('연결이 끊겼어요. 다시 연결되면 한 번 더 눌러 주세요.');
    });
  }
  function toggle(name) {
    var names = cellNames(cell);
    var at = names.indexOf(name);
    if (at >= 0) {
      names.splice(at, 1);
    } else if (names.length >= MAX_WORKERS) {
      return setMsg('한 줄에 ' + MAX_WORKERS + '명까지 넣을 수 있어요');
    } else {
      names.push(name);
    }
    save(names);
  }
  // 칸 왼쪽에 판을 둔다. 자리가 모자라면 오른쪽, 위아래는 화면 안으로 당긴다.
  function place() {
    if (!pop || !cell) return;
    var z = uiZoom();
    var r = cell.getBoundingClientRect();
    var w = pop.offsetWidth * z;
    var h = pop.offsetHeight * z;
    var vw = window.innerWidth;
    var vh = window.innerHeight;
    var left = r.left - w - 12;
    if (left < 8) left = Math.min(r.right + 12, vw - w - 8);
    left = Math.max(8, left);
    var top = Math.max(8, Math.min(r.top - 24, vh - h - 8));
    pop.style.left = ((window.scrollX + left) / z) + 'px';
    pop.style.top = ((window.scrollY + top) / z) + 'px';
  }
  function open(btn) {
    var wrap = btn.closest('.foms-tablet-shipgrid-wrap');
    if (!wrap || wrap.getAttribute('data-ship-can-assign') !== 'true') return;
    var list = safeJsonParse(wrap.getAttribute('data-ship-people') || '[]', []);
    people = Array.isArray(list) ? list : [];
    cell = btn;
    changed = false;
    pop = document.createElement('div');
    pop.className = 'foms-ship-names';
    pop.setAttribute('role', 'dialog');
    pop.setAttribute('aria-label', '시공자 고르기');
    pop.innerHTML =
      '<div class="foms-ship-names__top"><div class="foms-ship-names__head">' +
      '<div class="foms-ship-names__title">' + esc(circled(Number(btn.getAttribute('data-no')) || 0)) + '번 · ' +
      esc(btn.getAttribute('data-label') || '') + '</div>' +
      '<p class="foms-ship-names__hint">누르면 바로 저장돼요 · 한 명 더 누르면 함께 가요</p></div>' +
      '<button type="button" class="foms-ship-names__close" data-ship-act="close" aria-label="닫기">✕</button></div>' +
      '<div class="foms-ship-names__grid"></div>' +
      '<div class="foms-ship-names__write" hidden><input type="text" class="foms-ship-names__input" maxlength="40"' +
      ' placeholder="이름이나 지역" aria-label="직접 쓰기"><button type="button" class="foms-ship-names__btn" data-ship-act="add">넣기</button></div>' +
      '<div class="foms-ship-names__foot"><button type="button" class="foms-ship-names__btn" data-ship-act="write">직접 쓰기</button>' +
      '<button type="button" class="foms-ship-names__btn" data-ship-act="clear">비우기</button></div>' +
      '<div class="foms-ship-names__msg" role="status" aria-live="polite"></div>';
    document.body.appendChild(pop);
    btn.classList.add('is-open');
    renderGrid();
    place();
  }
  function refreshDay() {
    var shell = window.FOMS_ERP_SHELL;
    if (shell && typeof shell.navigateByShell === 'function') {
      shell.navigateByShell(window.location.pathname + window.location.search + window.location.hash, { bypassCache: true });
      return;
    }
    window.location.reload();
  }
  function close() {
    if (!pop) return;
    pop.remove();
    if (cell) cell.classList.remove('is-open');
    pop = null;
    cell = null;
    busy = false;
    if (changed) {
      changed = false;
      refreshDay();
    }
  }
  function onPopClick(target) {
    var nb = target.closest('[data-ship-name]');
    if (nb) {
      if (!nb.disabled) toggle(nb.getAttribute('data-ship-name'));
      return;
    }
    var act = target.closest('[data-ship-act]');
    var kind = act && act.getAttribute('data-ship-act');
    if (kind === 'close') close();
    else if (kind === 'clear') save([]);
    else if (kind === 'write') {
      var row = pop.querySelector('.foms-ship-names__write');
      row.hidden = false;
      row.querySelector('input').focus();
    } else if (kind === 'add') {
      var input = pop.querySelector('.foms-ship-names__input');
      var name = (input.value || '').trim();
      input.value = '';
      if (name && cellNames(cell).indexOf(name) < 0) toggle(name);
    }
  }
  // capture: 판이 열려 있으면 바깥 누름은 판만 닫고 삼킨다(뒤 줄의 시트가 열리지 않게).
  document.addEventListener('click', function (ev) {
    var t = ev.target;
    if (!t || !t.closest) return;
    if (pop && pop.contains(t)) {
      onPopClick(t);
      return;
    }
    var btn = t.closest('[data-ship-worker-cell]');
    if (pop) {
      var same = btn === cell;
      var willRefresh = changed;
      ev.preventDefault();
      ev.stopPropagation();
      close();
      if (btn && !same && !willRefresh) open(btn);
      return;
    }
    if (btn) {
      ev.preventDefault();
      ev.stopPropagation();
      open(btn);
    }
  }, true);

  document.addEventListener('keydown', function (ev) {
    if (!pop) return;
    if (ev.key === 'Escape') {
      ev.stopPropagation();
      close();
    } else if (ev.key === 'Enter' && ev.target && ev.target.classList.contains('foms-ship-names__input')) {
      ev.preventDefault();
      onPopClick(pop.querySelector('[data-ship-act="add"]'));
    }
  }, true);

  window.addEventListener('scroll', function (ev) {
    if (pop && !(ev.target && ev.target.nodeType === 1 && pop.contains(ev.target))) place();
  }, true);
  window.addEventListener('resize', place);

  // 다른 화면으로 바뀌어 칸이 사라지면 판만 치운다(다시 받기 없음 — 이미 새 화면이다).
  document.addEventListener('foms:erp-shell-fragment-swapped', function () {
    if (pop && cell && !document.body.contains(cell)) {
      changed = false;
      close();
    }
  });
})();
