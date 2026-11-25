/**
 * 생산 넘어간 주문의 도면 수정 — 파일로 올린 도면의 '바꿀 도면' 고르기(설계서 docs/specs/2026-11-25-production-stage-drawing-revision_SPEC.md
 * §2-3 · §3-5, D2). 작업실 전달 창(workbench-transfer-fix.js)과 ERP 대시보드 [도면 전달] 창(erp-dashboard-drawing-fix.js)이 같이 쓴다.
 *
 * - 고름은 차례가 아니라 **파일마다** 묶는다(이름 · 크기 · 고친 때 · 같은 파일 차례) — 파일을 빼면 그 파일 고름만 사라진다.
 * - 다른 파일이 이미 고른 도면 · 막힌 시트(고른 전달 대기 시트의 새 판이 바꾸는 도면)는 단추를 끈다 — 서버는 400 PICK_TARGET.
 * - 부르는 쪽이 창을 열 때 · 주문이 바뀔 때 reset() 한다.
 */
(function () {
  'use strict';

  if (window.FomsFixPicks) { return; }   // ERP 셸 조각이 다시 읽어도 한 번만(G4)

  var NEW = 'NEW';

  /** 파일마다 열쇠 — 같은 파일이 두 번 올라오면 차례(#n)로 가른다. */
  function fileKeys(files) {
    var seen = {};
    return files.map(function (f) {
      var base = [f.name, f.size, f.lastModified].join('|');
      seen[base] = (seen[base] || 0) + 1;
      return base + '#' + seen[base];
    });
  }

  /**
   * 고르기 하나 — opts: {rows(): 줄 칸, wrap(): 감싼 칸(파일이 없으면 숨김), files(): File[], currents(): [{key, sheet_id}],
   * blockedSheets(): 막힌 시트 id[], blockedKeys(): 이번 시트가 바꾸거나 빼는 도면 key[](R1 sheet_taken), onChange(): 고름이 바뀐 뒤}.
   */
  function create(opts) {
    var picks = {};

    function list() { return fileKeys(opts.files()).map(function (k) { return picks[k] || ''; }); }

    function takenFor(fileKey) {
      var sheets = opts.blockedSheets ? opts.blockedSheets() : [];
      var taken = {};
      opts.currents().forEach(function (f) { if (f.sheet_id && sheets.indexOf(f.sheet_id) >= 0) { taken[f.key] = true; } });
      (opts.blockedKeys ? opts.blockedKeys() : []).forEach(function (k) { taken[k] = true; });   // 지운 시트의 옛 판 등(셋째 판 4)
      Object.keys(picks).forEach(function (k) { if (k !== fileKey && picks[k] !== NEW) { taken[picks[k]] = true; } });
      return taken;
    }

    function chip(label, value, fileKey, taken) {
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'dfx-chip' + (picks[fileKey] === value ? ' is-on' : '');
      btn.textContent = label;
      btn.disabled = value !== NEW && !!taken[value];
      btn.setAttribute('aria-pressed', picks[fileKey] === value ? 'true' : 'false');
      btn.addEventListener('click', function () {
        picks[fileKey] = value;
        render();
        if (opts.onChange) { opts.onChange(); }
      });
      return btn;
    }

    /** 파일마다 줄(파일 이름 + 도면 1 … n + 새 도면). 빠진 파일의 고름 · 이제 못 고르는 고름은 지운다. */
    function render() {
      var rows = opts.rows();
      var wrap = opts.wrap();
      if (!rows || !wrap) { return; }
      var files = opts.files();
      var keys = fileKeys(files);
      Object.keys(picks).forEach(function (k) { if (keys.indexOf(k) < 0) { delete picks[k]; } });
      keys.forEach(function (k) { if (picks[k] && picks[k] !== NEW && takenFor(k)[picks[k]]) { delete picks[k]; } });
      rows.textContent = '';
      files.forEach(function (file, i) {
        var taken = takenFor(keys[i]);
        var row = document.createElement('div');
        row.className = 'dfx-pick-row';
        var name = document.createElement('div');
        name.className = 'dfx-pick-name';
        name.textContent = file.name;
        var chips = document.createElement('div');
        chips.className = 'dfx-pick-chips';
        opts.currents().forEach(function (f, n) { chips.appendChild(chip('도면 ' + (n + 1), f.key, keys[i], taken)); });
        chips.appendChild(chip('새 도면', NEW, keys[i], taken));
        row.appendChild(name);
        row.appendChild(chips);
        rows.appendChild(row);
      });
      wrap.hidden = !files.length;
    }

    /** 올린 파일마다 고른 도면(replace_of) — 모두 올라갔으면 차례로, 실패한 파일이 빠졌으면 이름으로 짝을 짓는다. */
    function attach(created, originals) {
      var orig = Array.prototype.slice.call(originals || []);
      var keys = fileKeys(orig);
      var used = {};
      return (created || []).map(function (f, i) {
        var index = (created.length === orig.length) ? i : orig.findIndex(function (o, j) {
          return !used[j] && o && f && o.name === f.filename;
        });
        if (index < 0) { return f; }
        used[index] = true;
        return Object.assign({}, f, { replace_of: picks[keys[index]] || '' });
      });
    }

    return {
      render: render,
      reset: function () { picks = {}; },
      list: list,
      missing: function () { return list().some(function (p) { return !p; }); },
      attach: attach
    };
  }

  window.FomsFixPicks = { create: create, fileKeys: fileKeys, NEW: NEW };
})();
