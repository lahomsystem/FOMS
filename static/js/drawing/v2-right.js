/**
 * 도면 마법사 V2 — 오른쪽 칸 '배치 확인': 가장 작게 줄어든 그림 · 틀 고르기 2 · 자세히 ▸(컴퓨터가 본 것 · 켜고 끄기 4) · [다시 자동 배치].
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §1 · §4 (화면 시안 K2 오른쪽 316px)
 * - %는 지금 양식 대비(같은 그림을 V1 자동 배치로 놓았을 때 높이). 칸으로 정리하기 전에는 '정리하면' 값을 보인다.
 *   지금 종이가 낡아(지운 뒤 · 손댄 뒤) 다시 놓으면 크게 커지면 '다시 배치하면 32% → 84%'와 [다시 자동 배치]를 먼저 보인다 —
 *   예전엔 낡은 32%만 보고 [시트 2장으로 나누기]를 권했다(스테이징 주문 4385, 2026-10-27).
 * - '컴퓨터가 본 것'은 아는 것만 말한다: AI 확신 · 사람이 고름 · 크기가 같아 짝 · 짝끼리 빗금 많고 적음(내부 판정 근거).
 *   켜고 끄기와 함께 '자세히 ▸'로 접는다(처음엔 접힘 · 이 브라우저에 기억) — 도면팀이 볼 것은 다 됐나 · 다시 정리 · 틀이다.
 * - [다시 자동 배치]는 칸 바닥(늘 보임)과 앱바(#dws-v2-rearrange — 오른쪽 칸이 숨는 좁은 창에서도) 두 곳. [고정 풀고 모두 다시]는
 *   고정 그림이 있으면 장수와 함께 보인다(⋯ 메뉴 항목도 같이 — 오른쪽 칸이 숨는 1280 밑 창).
 * - 틀 이름은 쉬운 말로('사진·상세를 위에' · '사진·상세를 왼쪽에' — 예전 '위 띠형 · 왼쪽 기둥형 · 선택됨 (고름)'이 낯설었다,
 *   도면팀 평가 2026-10-27). '추천'은 점수가 높은 틀(out.rec)에 늘 붙고, 고른 틀(v2_pick)이 추천과 다르면 그 아래
 *   [추천 틀로 돌아가기] — 고른 틀만 풀고 다시 놓는다(고정 그림은 그대로).
 * - 그림 밖 메모 · 선은 다시 배치가 비켜 간다(v2-plan.js plan.stay) — 그림이 작아진 까닭을 요약에 적는다.
 *
 * window.FomsV2Right = { init(api), render(view) }
 */
(function () {
  'use strict';
  if (window.FomsV2Right) { return; }

  var api = null, els = {}, last = null;
  var TOGGLES = [['lowToUnsorted', '확신이 낮으면 미분류로'], ['photoFirst', '사진은 늘 왼쪽 위'],
    ['sameScale', '같은 칸은 같은 배율'], ['lockMoved', '손으로 옮긴 그림은 고정']];
  var MINI = { w: 72, h: 53 };
  var NAMES = { photo: '사진', bom: '자재', notes: '특이', stamp: '강조', main: 'A', iso: 'B', detail: '상세', plan: '평면', unsorted: '?' };
  var TPL = { band: '사진·상세를 위에', column: '사진·상세를 왼쪽에' };   // v2-chrome.js 알림 글과 같은 이름
  var DETAIL_KEY = 'foms.dws.v2.detail';

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }
  function pct(v) { return v == null ? '—' : Math.round(v * 100) + '%'; }

  function init(a) {
    api = a;
    els.summary = $('dws-v2-summary');
    els.templates = $('dws-v2-templates');
    els.seen = $('dws-v2-seen');
    els.toggles = $('dws-v2-toggles');
    els.relayout = $('dws-v2-relayout');
    els.rearrange = $('dws-v2-rearrange');
    els.unpin = $('dws-v2-unpin');
    els.unpinMenu = document.querySelector('[data-v2-for="dws-v2-unpin"]');   // ⋯ 메뉴 항목(원래 단추를 눌러 준다 — v2-chrome.js)
    els.detailBtn = $('dws-v2-detail-toggle');
    els.detail = $('dws-v2-detail');
    [els.relayout, els.rearrange].forEach(function (b) { if (b) { b.addEventListener('click', relayout); } });
    if (els.unpin) { els.unpin.addEventListener('click', function () { api.unpinAll(); }); }
    if (els.detailBtn && els.detail) {
      showDetail(readOpen());
      els.detailBtn.addEventListener('click', function () {
        var on = !!els.detail.hidden;
        showDetail(on);
        saveOpen(on);
        if (on && last && last.sheet && last.plan) { renderSeen(last); }   // 접혀 있는 동안은 그리지 않았다
      });
    }
  }

  /** '자세히' 펼침 — 이 브라우저에 기억한다(사생활 보호 모드 · 막힌 저장소면 늘 접힘으로 시작). */
  function readOpen() { try { return window.localStorage.getItem(DETAIL_KEY) === '1'; } catch (e) { return false; } }
  function saveOpen(on) { try { window.localStorage.setItem(DETAIL_KEY, on ? '1' : '0'); } catch (e) { /* 이 창에서만 */ } }
  function showDetail(on) {
    els.detail.hidden = !on;
    els.detailBtn.setAttribute('aria-expanded', on ? 'true' : 'false');
    els.detailBtn.textContent = on ? '자세히 ▾' : '자세히 ▸';
  }
  function detailOpen() { return !els.detail || !els.detail.hidden; }

  function relayout() { api.arrange('button', { undo: true, photo: true }); }

  function labelOf(view, id) {
    var g = view.plan.g;
    return g.guess[id] ? String(g.lay[id] || '').replace('·', ' · ') + '?' : (g.labels[id] || '그림').replace('·', ' · ');
  }

  function minIn(view, keys) {
    var g = view.plan.g, best = null;
    keys.forEach(function (k) { (g[k] || []).forEach(function (o) { var p = view.pct[o.id]; if (p > 0 && (best == null || p < best)) { best = p; } }); });
    return best;
  }

  function renderSummary(view) {
    var box = els.summary, plan = view.plan;
    box.textContent = '';
    var res = plan.out[plan.template] || plan.out[plan.out.best];
    var now = plan.laid, low = now ? view.minPct : (res ? res.minPct : null);
    var lowId = now ? view.minId : (res ? res.minId : null), main = now ? minIn(view, ['main', 'iso']) : (res ? res.mainPct : null);
    var top = el('div', 'dws-v2-sum-top');
    top.appendChild(el('span', 'dws-v2-sum-label', now ? '가장 작게 줄어든 그림' : '칸으로 정리하면 가장 작은 그림'));
    if (lowId) { top.appendChild(el('span', 'dws-v2-sum-name', labelOf(view, lowId))); }
    box.appendChild(top);
    var row = el('div', 'dws-v2-sum-row');
    row.appendChild(el('span', 'dws-v2-sum-big', pct(low)));
    var after = now ? window.FomsV2Plan.afterPct(plan, view.pct) : null, stale = after != null && low != null && after > low + 0.05;
    var crowded = (low != null && low < window.FomsV2Layout.CROWD_PCT) || (res && res.minText != null && res.minText < window.FomsV2Layout.MIN_TEXT);
    row.appendChild(el('span', 'dws-v2-sum-state' + (crowded && !stale ? ' dws-v2-sum-warn' : ''), stale ? '다시 배치하면 ' + pct(low) + ' → ' + pct(after)
      : (crowded ? '그림이 작아요 · 2장으로 나누기를 권해요' : '한 장에 다 들어가요' + (main != null ? ' · 큰 그림 ' + pct(main) : ''))));
    box.appendChild(row);
    if ((stale || crowded) && api.core.canSave()) {   // 낡은 배치면 나누기보다 다시 놓기가 먼저
      var b = el('button', 'dws-v2-split', stale ? '다시 자동 배치' : '시트 2장으로 나누기');
      b.type = 'button';
      b.addEventListener('click', stale ? relayout : function () { api.split(); });
      box.appendChild(b);
    }
    if (plan.stay) { box.appendChild(el('span', 'dws-v2-sum-note', '그림 밖 메모 ' + plan.stay + '개는 그 자리에 두고 비켜 놓아요')); }
    var note = el('span', 'dws-v2-sum-note', res && res.pctBase === 'natural' ? '% = 원본 그림 대비' : '% = 지금 양식(예전 화면 자동 배치) 대비');
    box.appendChild(note);
  }

  function mini(res) {
    var m = el('div', 'dws-v2-mini'), A = window.FomsV2Layout.AREA, sx = MINI.w / (A.x1 - A.x0), sy = MINI.h / (A.y1 - A.y0);
    (res ? res.slots : []).forEach(function (s) {
      var r = el('span', 'dws-v2-mini-slot' + (s.key === 'photo' ? ' dws-v2-mini-photo' : ''), NAMES[s.key] || '');
      r.style.left = Math.round((s.x - A.x0) * sx) + 'px';
      r.style.top = Math.round((s.y - A.y0) * sy) + 'px';
      r.style.width = Math.max(4, Math.round(s.w * sx)) + 'px';
      r.style.height = Math.max(4, Math.round(s.h * sy)) + 'px';
      m.appendChild(r);
    });
    return m;
  }

  function detailPct(res, view) {
    if (!res) { return null; }
    var g = view.plan.g, ids = {}, low = null;
    ['detail', 'plan'].forEach(function (k) { (g[k] || []).forEach(function (o) { ids[o.id] = true; }); });
    Object.keys(res.pct || {}).forEach(function (id) { if (ids[id] && (low == null || res.pct[id] < low)) { low = res.pct[id]; } });
    return low;
  }

  function renderTemplates(view) {
    var box = els.templates, plan = view.plan, rec = plan.out.rec, can = api.core.canSave();
    box.textContent = '';
    ['band', 'column'].forEach(function (key) {
      var res = plan.out[key], b = el('button', 'dws-v2-tpl');
      b.type = 'button';
      var chosen = plan.laid && plan.template === key;
      b.classList.toggle('dws-v2-tpl-on', chosen);
      b.setAttribute('aria-pressed', chosen ? 'true' : 'false');
      b.disabled = !res || !can;
      b.appendChild(mini(res));
      var txt = el('span', 'dws-v2-tpl-text');
      txt.appendChild(el('span', 'dws-v2-tpl-name', TPL[key]));
      var dp = detailPct(res, view);
      txt.appendChild(el('span', 'dws-v2-tpl-meta', res ? '큰 그림 ' + pct(res.mainPct) + (dp != null ? ' · 상세 ' + pct(dp) : '') : '이 그림으로는 못 놓아요'));
      var state = [chosen ? '지금 쓰는 틀' : '', rec === key && res ? '추천' : ''].filter(Boolean).join(' · ');   // 추천은 고른 틀과 따로 늘 붙는다
      if (state) { txt.appendChild(el('span', 'dws-v2-tpl-state', state)); }
      b.appendChild(txt);
      b.addEventListener('click', function () { api.pickTemplate(key); });
      box.appendChild(b);
    });
    if (plan.pick && rec && plan.pick !== rec && plan.out[rec] && can) {   // 고른 틀만 풀고 추천 틀로 다시(고정 그림은 그대로)
      var back = el('button', 'dws-v2-link dws-v2-tpl-back', '추천 틀로 돌아가기');
      back.type = 'button';
      back.title = '고른 틀을 풀고 추천 틀(' + TPL[rec] + ')로 다시 놓아요 · 고정된 그림은 그 자리에 둬요 · 되돌리기 Ctrl+Z';
      back.addEventListener('click', function () { api.pickTemplate(''); });
      box.appendChild(back);
    }
  }

  /** 그림 종류 기억을 따른 이름표 — 닮음은 이 창에서 따른 그림만 안다(part-memory.js). */
  function memText(id) {
    var m = window.FomsPartMemory, sim = m ? m.simOf(id) : null;
    return '사람이 고른 비슷한 그림을 따름' + (typeof sim === 'number' ? ' · 닮음 ' + Math.round(sim * 100) + '%' : '');
  }

  function reasonOf(o, view, partner) {
    var p = o.part || {}, bits = [], gs = view.plan.g.guess[o.id];
    if (p.src === 'user') { bits.push('사람이 고름'); }
    else if (typeof p.conf === 'number') { bits.push('AI 확신 ' + Math.round(p.conf * 100) + '%'); }
    else { bits.push('종류를 아직 몰라요'); }
    if (gs) { bits.push('칸 확신 ' + Math.round(gs.conf * 100) + '% · 종류 확인'); }
    else if (p.src !== 'user' && view.plan.g.labels[o.id] === '미분류' && typeof p.conf === 'number') { bits.push('확신이 낮아 미분류'); }
    else if (p.src !== 'user' && /\.m$/.test(String(p.head || ''))) { bits.push(memText(o.id)); }
    else if (p.ai && p.label && p.label !== '미분류' && p.ai !== p.label && p.src !== 'user') { bits.push('짝 규칙으로 고침'); }
    if (partner) {
      var h1 = api.core.hatch(o), h2 = api.core.hatch(partner);
      if (typeof h1 === 'number' && typeof h2 === 'number' && Math.abs(h1 - h2) >= 0.05) { bits.push(h1 > h2 ? '빗금이 짝보다 많음' : '빗금이 짝보다 적음'); }
      else { bits.push('크기가 같은 짝'); }
    }
    return bits.join(' · ');
  }

  function renderSeen(view) {
    var box = els.seen, plan = view.plan, partner = {};
    box.textContent = '';
    plan.input.units.forEach(function (u) {
      if (u.members.length === 2) { partner[u.members[0].id] = u.members[1].id; partner[u.members[1].id] = u.members[0].id; }
    });
    var imgs = (view.sheet.objects || []).filter(function (o) { return o.type === 'image'; });
    if (!imgs.length) { box.appendChild(el('span', 'dws-v2-seen-empty', '아직 그림이 없어요')); return; }
    var byId = {};
    imgs.forEach(function (o) { byId[o.id] = o; });
    imgs.slice(0, 10).forEach(function (o) {
      var row = el('button', 'dws-v2-seen-row');
      row.type = 'button';
      var img = el('img', 'dws-v2-seen-img');
      img.alt = '';
      img.loading = 'lazy';
      img.src = api.core.viewUrl(o.key);
      row.appendChild(img);
      var t = el('span', 'dws-v2-seen-text');
      t.appendChild(el('span', 'dws-v2-seen-label', labelOf(view, o.id)));
      t.appendChild(el('span', 'dws-v2-seen-why', reasonOf(o, view, byId[partner[o.id]])));
      row.appendChild(t);
      row.addEventListener('click', function () { api.selectIds([o.id]); });
      box.appendChild(row);
    });
    if (imgs.length > 10) { box.appendChild(el('span', 'dws-v2-seen-empty', '그 밖 ' + (imgs.length - 10) + '장')); }
  }

  function renderToggles(view) {
    var box = els.toggles;
    box.textContent = '';
    TOGGLES.forEach(function (t) {
      var on = view.settings[t[0]] !== false, row = el('button', 'dws-v2-toggle');
      row.type = 'button';
      row.setAttribute('role', 'switch');
      row.setAttribute('aria-checked', on ? 'true' : 'false');
      row.appendChild(el('span', 'dws-v2-toggle-label', t[1]));
      row.appendChild(el('span', 'dws-v2-switch' + (on ? ' dws-v2-switch-on' : '')));
      row.addEventListener('click', function () { api.setSetting(t[0], !on); });
      box.appendChild(row);
    });
  }

  function render(view) {
    if (!els.summary) { return; }
    last = view;
    var has = !!(view.sheet && view.plan), can = api.core.canSave();
    var pics = has && (view.sheet.objects || []).some(function (o) { return o.type === 'image'; });
    [els.summary, els.templates, els.seen].forEach(function (n) { if (n && !has) { n.textContent = ''; } });
    [els.relayout, els.rearrange].forEach(function (b) { if (b) { b.disabled = !pics || !can; } });
    if (els.unpin) {   // 고정 그림이 있을 때만 — 다시 배치해도 그대로인 까닭을 풀어 준다(고른 틀은 틀 고르기의 [추천 틀로 돌아가기])
      var fixed = has ? Object.keys(view.plan.g.fixed).length : 0;
      els.unpin.hidden = !fixed || !can;
      els.unpin.textContent = '고정 풀고 모두 다시 (고정 ' + fixed + '장)';
      if (els.unpinMenu) { els.unpinMenu.hidden = els.unpin.hidden; els.unpinMenu.textContent = els.unpin.textContent; }
    }
    renderToggles(view);
    if (!has) { return; }
    renderSummary(view);
    renderTemplates(view);
    if (detailOpen()) { renderSeen(view); }   // 접혀 있으면 펼 때 그린다(작은 그림 10장을 매번 다시 만들지 않게)
  }

  window.FomsV2Right = { init: init, render: render };
})();
