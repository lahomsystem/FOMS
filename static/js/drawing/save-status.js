/**
 * 도면 마법사 — 저장 표시 글(순수 계산). 앱바 저장 상태 칩 · [저장] 알림 · 빈 화면 안내 글을 정한다.
 *
 * 저장은 두 가지다(wizard.js save()·saveAll()).
 * - 자동 저장(45초마다): 작업 내용(모든 시트)을 서버에 적는다. 전달 대기함에는 넣지 않는다.
 * - [저장]: 작업 내용을 적고, 지금 시트 그림(PNG)을 전달 대기함에 넣는다(= 전달본). [일괄 저장]은 모든 시트.
 * 예전 칩은 둘 다 '저장됨 09:10' 이라 다른 시트에서도 넣은 줄 알았다. 그래서 칩은 '지금 시트' 기준으로 말한다.
 * - 전달본 있음 → '전달 대기함 09:12'   · 넣은 뒤 이 시트를 고쳤으면 → '전달본 예전 것'
 * - 전달본 없음 → '자동 저장 09:15'(마지막 저장이 자동) · '전달본 없음'(마지막 저장이 [저장]이었는데 이 시트는 아님,
 *   또는 막 열어서 아직 저장 전 — 작업 내용은 이미 서버에 있다)
 * - '넣은 뒤 고쳤나'는 그림 지문(sheetSig)으로 가른다. 이 창에서 넣었으면 넣을 때 지문, 다시 연 창이면
 *   불러온 그대로의 지문(seedQueuedSigs)과 견준다 — 다시 열어 고친 시트도 '전달본 예전 것'이 된다.
 * - 전달 대기함 목록을 아직 못 받았으면(boxKnown false) '없음'이라고 말하지 않는다.
 *
 * window.FomsSaveStatus = { chip(st), atText(at, now), objJosa(word), sheetSig(sheet), sheetSigs(sheets),
 *                           seedQueuedSigs(queued, loaded, ids),
 *                           queuedToast(name), queueFailToast(name), allQueuedToast(ok, total, failNames),
 *                           emptyCopy(nProducts, canSave) }
 */
(function () {
  'use strict';
  if (window.FomsSaveStatus) { return; }

  var NOT_IN_BOX = '이 시트는 아직 전달 대기함에 없어요 — [저장]을 누르면 들어가요.';

  function two(n) { return (n < 10 ? '0' : '') + n; }
  function hhmm(d) { return two(d.getHours()) + ':' + two(d.getMinutes()); }

  /** 전달 대기함 시각('YYYY-MM-DD HH:MM', 서버 한국 시각) → 오늘이면 'HH:MM', 아니면 'M/D'. 못 읽으면 ''. */
  function atText(at, now) {
    var m = /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})/.exec(String(at || ''));
    if (!m) { return ''; }
    var d = (now instanceof Date) ? now : new Date();
    var today = d.getFullYear() === +m[1] && d.getMonth() + 1 === +m[2] && d.getDate() === +m[3];
    return today ? (m[4] + ':' + m[5]) : (+m[2] + '/' + +m[3]);
  }

  /**
   * 앱바 저장 상태 칩.
   * @param {Object} st { canSave, saving, failed, dirty, paused, savedAt(Date|null), savedAuto,
   *   queued(지금 시트에 전달본 있음), queuedAt('YYYY-MM-DD HH:MM'), queuedFresh(넣은 뒤 안 고침 — 모르면 true), now,
   *   boxKnown(전달 대기함 목록을 받았나 — 빠지면 받은 것으로 본다),
   *   onServer(지금 시트 작업 내용이 이미 서버에 있다 — 막 불러와 안 고침. 저장 시각이 없어도 '전달본 없음'을 보인다) }
   * @returns {{label:string, kind:string, title:string}} label 이 '' 이면 칩을 숨긴다.
   */
  function chip(st) {
    st = st || {};
    var hide = { label: '', kind: '', title: '' };
    if (!st.canSave) { return hide; }
    if (st.saving) { return { label: '저장 중…', kind: 'saving', title: '저장하는 중이에요.' }; }
    if (st.failed) { return { label: '저장 실패', kind: 'failed', title: '저장하지 못했어요. 알림의 [다시 시도]나 [저장]을 눌러 주세요.' }; }
    if (st.dirty && st.paused) { return { label: '저장 안 됨 · 자동 저장 멈춤', kind: 'paused', title: '자동 저장이 멈췄어요. [저장]을 눌러 주세요.' }; }
    if (st.dirty) { return { label: '저장 안 됨', kind: 'dirty', title: '고친 내용이 아직 저장되지 않았어요(45초마다 자동 저장).' }; }
    var saved = (st.savedAt instanceof Date) ? hhmm(st.savedAt) : '';
    var savedNote = saved ? (' 작업 내용은 ' + saved + '에 ' + (st.savedAuto ? '자동 저장됐어요.' : '저장됐어요.')) : '';
    if (st.queued) {
      var q = atText(st.queuedAt, st.now);
      if (st.queuedFresh !== false) {
        return { label: '전달 대기함' + (q ? ' ' + q : ''), kind: 'queued',
          title: '이 시트 그림이 전달 대기함에 있어요' + (st.queuedAt ? '(' + st.queuedAt + ' 넣음)' : '') + '.' + savedNote };
      }
      return { label: '전달본 예전 것', kind: 'stale',
        title: '전달 대기함에는 ' + (q ? q + '에 ' : '') + '넣은 그림이 있어요. 그 뒤 고친 내용은 [저장]을 눌러야 들어가요.' + savedNote };
    }
    if (st.boxKnown === false) {
      // 전달 대기함을 못 읽었다 — 작업 내용 저장만 말하고, 전달본이 있다·없다는 말하지 않는다.
      if (!saved) { return hide; }
      return { label: (st.savedAuto ? '자동 저장 ' : '작업 저장 ') + saved, kind: 'saved',
        title: '작업 내용이 ' + saved + '에 ' + (st.savedAuto ? '자동 저장됐어요.' : '저장됐어요.') + ' 전달 대기함은 아직 확인하지 못했어요.' };
    }
    if (!saved) {
      // 막 열었다: 작업 내용은 서버에 있으니 저장 시각이 없어도 '전달본 없음'을 말한다(첫 편집 때 칩이 새로 생기지 않게).
      return st.onServer ? { label: '전달본 없음', kind: 'none', title: '작업 내용은 저장돼 있어요. ' + NOT_IN_BOX } : hide;
    }
    if (st.savedAuto) { return { label: '자동 저장 ' + saved, kind: 'saved', title: '작업 내용이 ' + saved + '에 자동 저장됐어요. ' + NOT_IN_BOX }; }
    return { label: '전달본 없음', kind: 'none', title: '작업 내용은 ' + saved + '에 저장됐어요. ' + NOT_IN_BOX };
  }

  /** 받침 따라 '을'/'를'. 끝의 따옴표·괄호·점은 건너뛴다. 숫자·영문은 읽는 소리로, 모르면 '을(를)'. */
  function objJosa(word) {
    var s = String(word == null ? '' : word).replace(/[\s'"‘’“”()[\]{}<>.,!?~·…-]+$/, '');
    if (!s) { return '을(를)'; }
    var ch = s.charAt(s.length - 1);
    var code = ch.charCodeAt(0);
    if (code >= 0xAC00 && code <= 0xD7A3) { return ((code - 0xAC00) % 28) ? '을' : '를'; }
    if (/[0-9]/.test(ch)) { return '013678'.indexOf(ch) >= 0 ? '을' : '를'; }   // 영·일·삼·육·칠·팔
    if (/[a-z]/i.test(ch)) { return /[lmnr]/i.test(ch) ? '을' : '를'; }          // 엘·엠·엔·알
    return '을(를)';
  }

  /** 글 → 짧은 지문(53비트 섞기 + 길이). 시트 글 전체를 들고 있지 않으려고 줄인다. */
  function digest(str) {
    var h1 = 0xdeadbeef, h2 = 0x41c6ce57;
    for (var i = 0; i < str.length; i++) {
      var ch = str.charCodeAt(i);
      h1 = Math.imul(h1 ^ ch, 2654435761);
      h2 = Math.imul(h2 ^ ch, 1597334677);
    }
    h1 = Math.imul(h1 ^ (h1 >>> 16), 2246822507) ^ Math.imul(h2 ^ (h2 >>> 13), 3266489909);
    h2 = Math.imul(h2 ^ (h2 >>> 16), 2246822507) ^ Math.imul(h1 ^ (h1 >>> 13), 3266489909);
    return str.length.toString(36) + '.' + (4294967296 * (2097151 & h2) + (h1 >>> 0)).toString(36);
  }

  /** 시트 그림 지문 — 전달본(PNG)에 찍히는 것만 본다. 같은 지문이면 전달본이 지금 그림과 같다.
      뺀다: 계산 칸 입력(calc)·그림 종류 이름표(part) — 그림에 안 찍히고 AI 가 뒤늦게 바꾸기도 한다.
      자동 폭 글자의 폭(w) — 그릴 때마다 글꼴로 다시 재서 넣는 값이라(컴퓨터마다 1px 다를 수 있다)
      다시 연 뒤 손대지 않았는데 '고침'으로 보이면 안 된다. 폭을 정한 글자(autoWidth false)의 폭은 본다. */
  function sheetSig(sheet) {
    try {
      return digest(JSON.stringify(sheet || null, function (k, v) {
        if (k === 'calc' || k === 'part') { return undefined; }
        if (k === 'w' && this && this.type === 'text' && this.autoWidth !== false) { return undefined; }
        return v;
      }));
    } catch (e) { return ''; }
  }

  /** 시트들의 그림 지문 { 시트 id: 지문 } — 불러온 직후 한 번 잰다(다시 연 창의 기준). */
  function sheetSigs(sheets) {
    var out = {};
    (sheets || []).forEach(function (s) { if (s && s.id) { out[s.id] = sheetSig(s); } });
    return out;
  }

  /** 다시 연 창이 받은 첫 전달 대기함 목록: 이 창에서 넣지 않은 전달본(ids 중 queued 에 지문 없음)은
      불러온 그대로의 지문(loaded)을 기준으로 적는다 — 그 뒤 고치면 '전달본 예전 것'. 이 창에서 넣은 것은 그대로 둔다.
      ids 는 배열·Set 모두 된다. queued 를 고쳐 돌려준다. */
  function seedQueuedSigs(queued, loaded, ids) {
    var out = queued || {};
    if (!loaded || !ids || typeof ids.forEach !== 'function') { return out; }
    ids.forEach(function (id) {
      if (out[id] == null && loaded[id]) { out[id] = loaded[id]; }
    });
    return out;
  }

  function quoted(name) {
    var n = String(name == null ? '' : name).trim() || '도면';
    return "'" + n + "'" + objJosa(n);
  }

  /** [저장] 알림 — 어느 시트를 넣었는지 이름으로 말한다. */
  function queuedToast(name) { return quoted(name) + ' 전달 대기함에 넣었어요'; }

  /** 작업 내용 저장은 됐는데 그림(PNG)을 못 넣었을 때. */
  function queueFailToast(name) { return '작업 내용은 저장했지만 ' + quoted(name) + ' 전달 대기함에 넣지 못했어요'; }

  /** [일괄 저장] 마무리 알림. */
  function allQueuedToast(ok, total, failNames) {
    var fails = (failNames || []).filter(Boolean);
    if (!fails.length) { return '시트 ' + total + '장을 모두 전달 대기함에 넣었어요'; }
    return '시트 ' + total + '장 중 ' + ok + '장을 넣었어요 · 못 넣은 시트: ' + fails.join(', ');
  }

  /** 가운데 빈 화면 안내(시트 0개). 제품이 없는 주문에서 '좌측에서 제품을 선택'은 할 수 없는 일이라 빈 시트로 이끈다. */
  function emptyCopy(nProducts, canSave) {
    if (!canSave) {
      return { title: '아직 만든 도면이 없어요', sub: '열람 전용이에요. 도면 담당자·도면팀 또는 관리자만 도면을 만들 수 있어요.' };
    }
    if (!(nProducts > 0)) {
      return { title: '제품이 없는 주문이에요', sub: '아래 [빈 시트 추가]나 위의 [+ 시트]로 빈 시트를 만들어 시작하세요.' };
    }
    return { title: '좌측에서 제품을 선택해 도면을 시작하세요', sub: '제품을 클릭하면 해당 제품의 도면 시트가 자동으로 만들어집니다.' };
  }

  window.FomsSaveStatus = {
    chip: chip, atText: atText, objJosa: objJosa, sheetSig: sheetSig, sheetSigs: sheetSigs, seedQueuedSigs: seedQueuedSigs,
    queuedToast: queuedToast, queueFailToast: queueFailToast, allQueuedToast: allQueuedToast,
    emptyCopy: emptyCopy
  };
})();
