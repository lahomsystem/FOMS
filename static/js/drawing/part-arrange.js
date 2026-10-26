/**
 * 도면 마법사 — 자동 배치를 시트에 붙이는 도우미(자재표 자리 · 놓는 순서 · 손댔는지 지문 · 층 순서 · 선택 창).
 *
 * 설계 정본: docs/plans/2026-10-23-drawing-part-label-feedback-spec.md §3.2
 * - 자재표 자리: 자리표 글자([SR]·[DOOR] …)의 가장 왼쪽 − 8 ~ 놓는 칸 오른쪽,
 *   머리 아래 ~ max(지금 글자 바닥 + 2줄, 머리글 줄 + 9줄). 자재표를 나중에 쳐도 그림 밑에 숨지 않게 비워 둔다.
 * - 놓는 순서: 지금 객체 순서. 같이 올린 묶음은 사람이 고른 파일 순서(업로드가 끝난 순서가 아님).
 * - 배치 뒤 그림 아래 깔린 글자는 그림 위로 올린다(시트 objects 순서 = 그리는 순서 = 저장 순서).
 *
 * window.FomsPartArrange = { isBomText, bomZone, order, signature, reorder, crowdedLines, keptText, kindsText, seedRects,
 *   skippedNote, guessNote, ask }
 */
(function () {
  'use strict';
  if (window.FomsPartArrange) { return; }

  var PAD = 8;
  var TOP_BAND = 200;   // 자리표가 머리 바로 아래 이만큼 안에 있으면 자재표 자리는 머리 아래부터

  /** 첫 줄이 '[SR]' 처럼 대괄호 머리글로 시작하는 글자(자재표 자리표·자재표). */
  function isBomText(text) { return /^\s*\[[^\]\n]{1,12}\]/.test(String(text || '')); }

  /** rects: 자재표 글자 상자 [{x,y,w,h,line}] (line = 줄 높이) → 비워 둘 사각형 {x,y,w,h} 또는 null. */
  function bomZone(rects, area) {
    if (!rects || !rects.length || !area) { return null; }
    var minX = Infinity, minY = Infinity, bottom = -Infinity, line = 0;
    rects.forEach(function (r) {
      minX = Math.min(minX, r.x); minY = Math.min(minY, r.y);
      bottom = Math.max(bottom, r.y + r.h); line = Math.max(line, r.line > 0 ? r.line : 25);
    });
    var x0 = Math.max(area.x0, Math.floor(minX - PAD));
    var y0 = (minY - PAD <= area.y0 + TOP_BAND) ? area.y0 : Math.floor(minY - PAD);
    var y1 = Math.min(area.y1, Math.ceil(Math.max(bottom + 2 * line, minY + 9 * line) + PAD));
    if (x0 >= area.x1 || y1 <= y0) { return null; }
    return { x: x0, y: y0, w: area.x1 - x0, h: y1 - y0 };
  }

  /** 놓는 순서: images(지금 객체 순서) → { id: 순번 }. seq[id] = [묶음 번호, 고른 순서] 인 그림끼리는
      그 묶음이 차지한 자리 안에서 고른 순서대로 바꿔 앉힌다(안정 정렬). */
  function order(images, seq) {
    var out = {}, slots = {}, map = seq || {};
    images.forEach(function (o, i) {
      out[o.id] = i;
      var u = map[o.id];
      if (u) { (slots[u[0]] = slots[u[0]] || []).push(i); }
    });
    Object.keys(slots).forEach(function (b) {
      var pos = slots[b];
      var ids = pos.map(function (i) { return images[i]; }).sort(function (a, c) {
        return (map[a.id][1] - map[c.id][1]) || (out[a.id] - out[c.id]);
      });
      ids.forEach(function (o, k) { out[o.id] = pos[k]; });
    });
    return out;
  }

  /** 그림 자리 지문 — 배치 뒤 사람이 그림을 옮기거나 지우거나 더했는지 가린다. */
  function signature(objects) {
    return (objects || []).filter(function (o) { return o && o.type === 'image'; }).map(function (o) {
      return [o.id, o.x, o.y, o.w, o.h, o.rotation || 0, o.flipX ? 1 : 0, o.flipY ? 1 : 0, o.locked ? 1 : 0].join(',');
    }).join(';');
  }

  /** 놓은 그림은 놓은 순서로 제자리끼리 바꿔 앉히고, 그 그림들보다 아래 깔린 글자는 맨 위로 올린 새 배열. */
  function reorder(objects, placedIds) {
    var rank = {}, slots = [], imgs = [];
    placedIds.forEach(function (id, i) { rank[id] = i; });
    objects.forEach(function (o, i) { if (rank[o.id] != null) { slots.push(i); imgs.push(o); } });
    imgs.sort(function (a, b) { return rank[a.id] - rank[b.id]; });
    var out = objects.slice();
    slots.forEach(function (p, k) { out[p] = imgs[k]; });
    var last = slots.length ? slots[slots.length - 1] : -1;
    var below = function (o, i) { return o.type === 'text' && i < last; };
    var lifted = out.filter(below);
    return lifted.length ? out.filter(function (o, i) { return !below(o, i); }).concat(lifted) : out;
  }

  var KIND_WORDS = [['front', '모듈', '개'], ['iso', '입체 그림', '장'], ['plan', '평면', '장'], ['small', '서랍·부품', '장'],
    ['photo', '사진', '장'], ['other', '미분류', '장']];

  /** 옮길 그림 종류 글 — '모듈 1개 · 입체 그림 5장 · 평면 2장'(모듈 = 정면 묶음 수, 나머지는 장수). */
  function kindsText(c) {
    return KIND_WORDS.filter(function (k) { return c[k[0]] > 0; }).map(function (k) { return k[1] + ' ' + c[k[0]] + k[2]; }).join(' · ');
  }

  /** '너무 작음' 선택 창 글. minText(px|null) · split(part-split.js 계획|null) · opts { room: 더 만들 수 있는 시트 수, min: 지킬 글자,
      skipped: 돌리거나 잠가 그대로 둘 그림 수, photo: 글자는 되고 현장 사진만 작아질 때 그 높이(px), photoMin: 사진 높이 하한 }. */
  function crowdedLines(minText, split, opts) {
    var o = opts || {}, min = o.min || 8, n = split ? split.sheets.length : 0, moved = { n: 0 }, photo = o.photo != null;
    var stay = o.skipped > 0 ? '돌리거나 잠근 그림 ' + o.skipped + '장은 그대로 둬요.' : '';   // 실화면 V3: 창에 말이 없었다
    var lines = [photo ? '이 시트에 다 넣으면 현장 사진이 높이 ' + Math.max(1, Math.floor(o.photo)) + 'px 로 작아져요.'
      : (minText != null ? '이 시트에 다 넣으면 치수 글자가 ' + Math.max(1, Math.floor(minText)) + 'px 로 작아져요.'
        : '이 시트에 다 넣으면 그림이 아주 작게 놓여요.')];
    if (n < 2) {
      lines.push(o.room > 0 ? '한 묶음만으로도 글자가 작아지는 큰 그림이에요 — [그래도 이 시트에]로 놓아 주세요.'
        : '시트가 10장이라 더 나눌 수 없어요 — [그래도 이 시트에]로 작게 놓거나 시트를 정리해 주세요.');
      return stay ? lines.concat([stay]) : lines;
    }
    split.counts.slice(1).forEach(function (c) { Object.keys(c).forEach(function (k) { moved[k] = (moved[k] || 0) + c[k]; }); });
    lines.push(split.ok ? '시트 ' + n + '장으로 나누면 ' + (photo ? '현장 사진도 높이 ' + (o.photoMin || 120) + 'px 이상으로'
      : '치수 글자를 모두 ' + min + 'px 이상으로') + ' 놓을 수 있어요.'
      : '시트 ' + n + '장으로 나눠도 일부 그림은 ' + (photo ? '작게 놓여요' : '글자가 ' + min + 'px 보다 작아요') +
        (n > o.room ? ' — 시트는 10장까지예요.' : '.'));
    lines.push('이 시트에 ' + split.counts[0].n + '장을 두고 새 시트 ' + (n - 1) + '장에 ' + moved.n + '장을 옮겨요 — ' + kindsText(moved) + '.');
    if (stay) { lines.push(stay); }
    lines.push('나누면 시트마다 다시 배치해요. 이 시트에서 Ctrl+Z 한 번이면 새 시트와 옮긴 그림까지 처음대로 돌아와요.');
    return lines;
  }

  /** '그래도 이 시트에' 로 놓은 뒤 알림 — 글자를 못 지켰으면 가장 작은 글자, 글자는 되고 사진만 작으면 사진 높이(layout why). */
  function keptText(res) {
    var r = res || {}, tail = ' (되돌리기 Ctrl+Z)';
    if (!r.crowded) { return '종류에 맞춰 배치했습니다' + tail; }
    if (r.why === 'photo' && r.photo != null) { return '현장 사진을 작게 놓았어요 — 높이 ' + r.photo + 'px' + tail; }
    return '그림을 작게 놓았어요' + (r.minText != null ? ' — 가장 작은 글자 ' + Math.max(1, Math.floor(r.minText)) + 'px' : '') + tail;
  }

  /** 새 시트 자리표(seedPresetObjects 결과) → 글자 상자 어림 [{x,y,w,h,line}] — 나누기 계획의 새 시트 자재표 자리용. */
  function seedRects(objs, size) {
    var line = (size > 0 ? size : 20) * 1.25;
    return (objs || []).map(function (o) {
      var rows = String(o.text || '').split('\n');
      var w = Math.max.apply(null, rows.map(function (r) { return r.length; }));
      return { x: o.x, y: o.y, w: Math.ceil(w * line * 0.75), h: Math.round(rows.length * line), line: line };
    });
  }

  /** 배치에서 뺀 그림 안내 — n = 돌리거나 잠가서 그대로 둔 그림 수, out = 그중 테두리 밖에 있는 수(골라 둔다). */
  function skippedNote(n, out) {
    if (!(n > 0)) { return ''; }
    return ' · 돌리거나 잠근 그림 ' + n + '장은 그대로 두었어요' + (out > 0 ? ' — 테두리 밖 ' + out + '장을 골라 두었어요' : '');
  }

  var GUESS_KEYS = { '정면·내부': ['내부', 1], '정면·도어': ['도어', 2], '입체·내부': ['입체 내부', 3], '입체·도어': ['입체 도어', 4] };

  /** 부품·서랍으로 짐작했지만 크기가 같아 짝 자리에 놓은 그림(layout guess) 안내 — 맞으면 숫자키로 굳히게 이끈다.
      guesses = [짝 이름표, …](사람이 정한 그림은 뺀 것). */
  function guessNote(guesses) {
    var g = guesses || [], k = GUESS_KEYS[g[0]];
    if (!g.length || !k) { return ''; }
    var same = g.every(function (x) { return x === g[0]; });
    return ' · 크기가 같아 ' + (same ? k[0] : '짝') + ' 자리에 놓은 그림 ' + g.length + '장 — ' +
      (same ? '맞으면 골라서 숫자키 ' + k[1] : '종류를 확인해 주세요');
  }

  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }

  /** 화면 안 선택 창(마법사 대화 상자 모양). opts: { title, lines: [글], buttons: [{ id, label, primary }] }
      → Promise<고른 id | null(닫기·Esc)>. 창이 떠 있는 동안 마법사 단축키는 막는다.
      buttons 는 가로 줄 순서(덜 중요한 것 → 주 단추)로 받고, 세로로 쌓을 때는 뒤집어 주 단추를 맨 위·'나중에'를 맨 아래에 둔다
      (wizard.css .dws-arrange-dialog — 실화면 V3: 셋이 한 줄에 안 들어가 주 단추만 둘째 줄로 떨어졌다). 읽는 순서·Tab 순서도 같다. */
  function ask(opts) {
    var o = opts || {};
    return new Promise(function (resolve) {
      var dlg = el('dialog', 'dws-dialog dws-arrange-dialog dws-ui');
      var body = el('div', 'dws-dialog-body');
      var title = el('h2', 'dws-dialog-title', o.title || '');
      title.id = 'dws-arrange-title';
      dlg.setAttribute('aria-labelledby', title.id);
      body.appendChild(title);
      (o.lines || []).forEach(function (t, i) { body.appendChild(el('p', i ? 'dws-arrange-sub' : 'dws-arrange-msg', t)); });
      var actions = el('div', 'dws-dialog-actions'), done = false;
      function finish(v) {
        if (done) { return; }
        done = true;
        try { if (dlg.close) { dlg.close(); } } catch (e) { /* 이미 닫힘 */ }
        if (dlg.parentNode) { dlg.parentNode.removeChild(dlg); }
        resolve(v);
      }
      var list = (o.buttons || []).slice().reverse();
      list.filter(function (b) { return b.primary; }).concat(list.filter(function (b) { return !b.primary; })).forEach(function (b) {
        var btn = el('button', 'dws-btn' + (b.primary ? ' dws-btn-primary' : ''), b.label);
        btn.type = 'button';
        btn.addEventListener('click', function () { finish(b.id); });
        actions.appendChild(btn);
      });
      body.appendChild(actions);
      dlg.appendChild(body);
      dlg.addEventListener('cancel', function (e) { e.preventDefault(); finish(null); });
      dlg.addEventListener('keydown', function (e) { e.stopPropagation(); });   // 뒤의 Ctrl+Z·Delete 가 돌지 않게
      (document.getElementById('dws-root') || document.body).appendChild(dlg);
      if (dlg.showModal) {
        try { dlg.showModal(); } catch (e) { dlg.setAttribute('open', ''); }
      } else { dlg.setAttribute('open', ''); }
      var first = actions.querySelector('.dws-btn-primary') || actions.querySelector('button');
      if (first) { first.focus(); }
    });
  }

  window.FomsPartArrange = {
    isBomText: isBomText, bomZone: bomZone, order: order, signature: signature, reorder: reorder,
    crowdedLines: crowdedLines, keptText: keptText, kindsText: kindsText, seedRects: seedRects, skippedNote: skippedNote,
    guessNote: guessNote, ask: ask
  };
})();
