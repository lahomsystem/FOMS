/**
 * 도면 마법사 V2 — 화면 둘레: 앱바 부제 · [자유 배치 | 자동 배치] · ⋯ 메뉴 · 알림 띠 · 끌어 놓기 칸 · 화면 % · 저장 상태 칩 자리 ·
 * 실측 사진 고르기(색 · 밝기 섞임 점수).
 *
 * 설계 정본: docs/plans/2026-10-26-drawing-wizard-v2-spec.md §1 · §5
 * window.FomsV2Chrome = { init(api), render(view), pickPhoto(photos) → Promise<photo|null> }
 */
(function () {
  'use strict';
  if (window.FomsV2Chrome) { return; }

  var api = null, els = {}, ZOOMS = [50, 70, 100, 150];

  function $(id) { return document.getElementById(id); }
  function el(tag, cls, text) {
    var n = document.createElement(tag);
    if (cls) { n.className = cls; }
    if (text != null) { n.textContent = text; }
    return n;
  }
  function btn(label, cls, onClick) {
    var b = el('button', 'dws-v2-banner-btn' + (cls ? ' ' + cls : ''), label);
    b.type = 'button';
    b.addEventListener('click', onClick);
    return b;
  }

  function closeMore() {
    if (els.moreMenu) { els.moreMenu.hidden = true; }
    if (els.more) { els.more.setAttribute('aria-expanded', 'false'); }
  }

  function wireMore() {
    if (!els.more || !els.moreMenu) { return; }
    els.more.addEventListener('click', function (e) {
      e.stopPropagation();
      var open = els.moreMenu.hidden;
      els.moreMenu.hidden = !open;
      els.more.setAttribute('aria-expanded', open ? 'true' : 'false');
    });
    document.addEventListener('click', function (e) {
      var item = e.target.closest('[data-v2-for]');   // PNG 단추 · ⋯ 메뉴 항목 = 원래 단추를 눌러 준다(처리 · 잠금 그대로)
      if (item) {
        closeMore();
        var target = $(item.getAttribute('data-v2-for'));
        if (target && !target.disabled) { target.click(); }
        return;
      }
      if (!e.target.closest('.dws-v2-more')) { closeMore(); }
    });
    document.addEventListener('keydown', function (e) { if (e.key === 'Escape') { closeMore(); } });
  }

  function wireDrop() {
    var d = els.drop;
    if (!d) { return; }
    d.addEventListener('click', function () { api.core.pickFiles(); });
    d.addEventListener('dragover', function (e) { e.preventDefault(); e.stopPropagation(); d.classList.add('dws-v2-drop-on'); });
    d.addEventListener('dragleave', function () { d.classList.remove('dws-v2-drop-on'); });
    d.addEventListener('drop', function (e) {
      e.preventDefault();
      e.stopPropagation();
      d.classList.remove('dws-v2-drop-on');
      var files = e.dataTransfer && e.dataTransfer.files;
      if (files && files.length) { api.core.addFiles(files); }
    });
  }

  function wireZoom() {
    var z = els.zoom;
    if (!z) { return; }
    z.addEventListener('change', function () {
      if (z.value === 'fit') { api.core.fitZoom(); } else if (z.value !== 'cur') { api.core.setZoom(parseInt(z.value, 10) / 100); }
      api.refresh();
    });
  }

  function init(a) {
    api = a;
    els.banner = $('dws-v2-banner');
    els.drop = $('dws-v2-drop');
    els.zoom = $('dws-v2-zoom');
    els.more = $('dws-v2-more');
    els.moreMenu = $('dws-v2-more-menu');
    els.sub = $('dws-customer');
    var chip = $('dws-save-status'), holder = $('dws-v2-tabstatus');
    if (chip && holder) { holder.appendChild(chip); }   // K2: 탭 줄 오른쪽 '자동 저장됨 10:42'
    Array.prototype.forEach.call(document.querySelectorAll('[data-v2-mode]'), function (b) {
      b.addEventListener('click', function () { api.setMode(b.getAttribute('data-v2-mode')); });
    });
    wireMore();
    wireDrop();
    wireZoom();
    var wrap = $('dws-stage-wrap');
    if (wrap && window.ResizeObserver) { new window.ResizeObserver(function () { fitWidths(); renderZoom(); }).observe(wrap); }   // Ctrl+휠 확대도 따라간다
  }

  /** 알림 띠 · 끌어 놓기 칸 · 범례 폭 = 종이 폭(확대 비율 따라). */
  function fitWidths() {
    var wrap = $('dws-stage-wrap'), w = wrap ? wrap.offsetWidth : 0;
    if (!w) { return; }
    [els.banner, els.drop, document.querySelector('.dws-v2-legend')].forEach(function (n) { if (n) { n.style.width = w + 'px'; } });
  }

  function imageCount(sheet) { return (sheet.objects || []).filter(function (o) { return o.type === 'image'; }).length; }

  function renderBanner(view) {
    var b = els.banner, sheet = view.sheet, plan = view.plan;
    if (!b) { return; }
    b.textContent = '';
    b.className = 'dws-v2-banner dws-ui';
    if (!sheet || !plan) { b.hidden = true; return; }
    b.hidden = false;
    var core = api.core, editable = core.canSave();
    function line(strong, rest, tone) {
      b.classList.add('dws-v2-banner-' + tone);
      b.appendChild(el('strong', 'dws-v2-banner-strong', strong));
      if (rest) { b.appendChild(el('span', 'dws-v2-banner-text', rest)); }
    }
    var n = imageCount(sheet), g = plan.g, arr = view.arranged && view.arranged.sheetId === sheet.id ? view.arranged : null;
    if (!n) { line('그림을 끌어 놓으세요', '아래 칸에 스케치업 그림을 끌어 놓거나 붙여넣으면 종류를 알아보고 칸에 넣어요', 'gray'); return; }
    if (!plan.laid) {
      line('예전 화면에서 놓은 그대로예요', '칸으로 정리하면 칸마다 이름이 붙고 그림이 커져요', 'blue');
      if (editable) { b.appendChild(btn('칸으로 정리하기', 'dws-v2-banner-main', function () { api.arrange('banner', { undo: true, photo: true }); })); }
      return;
    }
    var res = plan.out[plan.template] || plan.out[plan.out.best];
    var low = view.minPct != null && view.minPct < window.FomsV2Layout.CROWD_PCT;
    var tiny = res && res.minText != null && res.minText < window.FomsV2Layout.MIN_TEXT;
    if (low || tiny) {
      line(low ? '가장 작은 그림이 ' + Math.round(view.minPct * 100) + '%예요' : '치수 글자가 ' + Math.floor(res.minText) + 'px 로 작아요',
        '시트 2장으로 나누면 그림이 커져요', 'orange');
      if (editable) { b.appendChild(btn('시트 2장으로 나누기', 'dws-v2-banner-main', function () { api.split(); })); }
    } else {
      var pics = g.main.length + g.iso.length + g.detail.length + g.plan.length + g.unsorted.length;
      line('그림 ' + pics + '장' + (g.photo.length ? ' + 실측 사진 ' + g.photo.length + '장' : ''),
        '컴퓨터가 종류를 알아보고 칸에 넣었어요 · 확인 필요 ' + g.unsorted.length + '장', 'green');
    }
    if (arr && editable) { b.appendChild(btn('되돌리기', '', function () { core.undo(); })); }
  }

  function renderZoom() {
    var z = els.zoom;
    if (!z) { return; }
    var pct = Math.round(api.core.zoom() * 100), cur = z.querySelector('option[value="cur"]');
    if (cur) { cur.textContent = '화면 ' + pct + '%'; }
    z.value = ZOOMS.indexOf(pct) >= 0 ? String(pct) : 'cur';
  }

  function render(view) {
    renderBanner(view);
    renderZoom();
    fitWidths();
    Array.prototype.forEach.call(document.querySelectorAll('[data-v2-mode]'), function (b) {
      var on = b.getAttribute('data-v2-mode') === view.mode;
      b.classList.toggle('dws-v2-mode-on', on);
      b.setAttribute('aria-pressed', on ? 'true' : 'false');
    });
    if (els.sub && view.sheet) {
      var f = view.sheet.form || {}, bits = [String(f.product_name || '').trim(), f.construction_date ? '시공 ' + String(f.construction_date).trim() : '']
        .filter(Boolean);
      els.sub.textContent = '(' + api.core.customer() + ')' + (bits.length ? ' ' + bits.join(' · ') : '');
    }
  }

  /** 사진 한 장 점수 — 색 섞임(Hasler–Süsstrunk) + 밝기 퍼짐 + 가로 사진 · 지금 제품 사진 덤. 못 읽으면 -1. */
  function scorePhoto(p, productIndex) {
    return new Promise(function (resolve) {
      var img = new Image(), done = false;
      var timer = window.setTimeout(function () { if (!done) { done = true; resolve(-1); } }, 6000);
      function finish(v) { if (!done) { done = true; window.clearTimeout(timer); resolve(v); } }
      img.onload = function () {
        try {
          var c = document.createElement('canvas'), W = 48, H = 48, n = W * H;
          c.width = W; c.height = H;
          var x = c.getContext('2d');
          x.drawImage(img, 0, 0, W, H);
          var d = x.getImageData(0, 0, W, H).data, srg = 0, syb = 0, qrg = 0, qyb = 0, sl = 0, ql = 0;
          for (var i = 0; i < d.length; i += 4) {
            var rg = d[i] - d[i + 1], yb = 0.5 * (d[i] + d[i + 1]) - d[i + 2], l = 0.299 * d[i] + 0.587 * d[i + 1] + 0.114 * d[i + 2];
            srg += rg; syb += yb; qrg += rg * rg; qyb += yb * yb; sl += l; ql += l * l;
          }
          var mrg = srg / n, myb = syb / n, ml = sl / n;
          var cf = Math.sqrt(Math.max(0, qrg / n - mrg * mrg) + Math.max(0, qyb / n - myb * myb)) + 0.3 * Math.sqrt(mrg * mrg + myb * myb);
          var spread = Math.sqrt(Math.max(0, ql / n - ml * ml));
          finish(cf / 100 + spread / 64 + (img.naturalWidth > img.naturalHeight ? 0.3 : 0) +
            (productIndex != null && p.item_index === productIndex ? 0.5 : 0));
        } catch (e) { finish(-1); }
      };
      img.onerror = function () { finish(-1); };
      img.src = p.thumb_url || '';
    });
  }

  function pickPhoto(photos) {
    var list = (photos || []).filter(function (p) { return p && p.key && p.thumb_url; }).slice(0, 12);
    var sh = api && api.core.sheet(), idx = sh && typeof sh.product_index === 'number' ? sh.product_index : null;
    if (!list.length) { return Promise.resolve(null); }
    return Promise.all(list.map(function (p) { return scorePhoto(p, idx); })).then(function (scores) {
      var best = -1, at = -1;
      scores.forEach(function (s, i) { if (s > best) { best = s; at = i; } });
      return at >= 0 && best >= 0 ? list[at] : null;
    });
  }

  window.FomsV2Chrome = { init: init, render: render, pickPhoto: pickPhoto };
})();
