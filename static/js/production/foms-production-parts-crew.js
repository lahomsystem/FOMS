/* 생산 파트 도면 카드 — 한 도면 · 한 파트를 여러 명이 같이 작업(설계서 2026-11-25 multi-holder §5 · §8 · §10 M2, 시안 01 A ~ I · 창 셋).
 * 쓰기 없음(fetch 0) — 요청은 foms-production-parts.js 의 send() 하나. 이름 줄("이시영 · 김재단 외 1")은 서버가 카드(data-pp-crew)와
 * 응답 · 30초 받아 오기 표시(mark.crew)에 실어 준 글만 쓴다(foms/services/production/part_card_crew.py crew_view — 여기서 짓지 않는다).
 *   카드 칸(render — 안 봄 · 작업 필요 · 완료 상태, 템플릿 home_parts.html pp_act 와 같은 규칙): 안 봄 = [기본][재단 시작](재단) ·
 *     [<파트> 시작](옛 [작업 시작], 11-27) + 반장 · 관리자 [<파트> 완료](11-27) · 남이 작업 중 = [이름 칸 ›][같이 작업] ·
 *     내 몫만 완료 = "재단 1/2 완료 · 김재단 작업 중"('완료' 칸, 되돌리기 줄 "재단 1/2 완료") · 반장 · 관리자 = 이름 칸(둘째 줄 "재단 1/2 완료") +
 *     [재단 완료] · 보기만 = "이시영 · 김재단 작업 중" · 완료 = "재단 완료 · 이시영 · 김재단".
 *   창 글(plan — 창 그리기 foms-production-parts-modal.js 가 먼저 부른다): [같이 작업] 창 · [담당 바꾸기] 누구와(바꿀 수 있는 사람이
 *     둘 이상일 때만 고르기 창, 완료를 누른 사람은 빠짐 — 파트 계정은 하나면 지금 동작 그대로) · 반장 고르기([담당 바꾸기 ›] = 늘 다음 창
 *     "누구에게 줄까요?"(-parts-give.js, 11-28 — 바꿀 사람이 둘 이상이면 자리 고르기 · [다음] 먼저) [대신 완료] [같이 작업](Q22) [{이름} 시작 취소]) · 남은 사람이 있는 [완료] · [시작 취소] · 되돌리기.
 *     토씨가 붙는 문장은 서버가 준 완성 조각(who_subj 등 — "이시영 · 김재단 외 2명이")만 쓴다(여기서 토씨를 붙이지 않는다).
 *   넘김 말풍선(notice): 거의 같이 [작업 시작] = 서버 글 "이시영이 먼저 시작했어요."를 그림 칸 아래쪽 안(어느 단추도 안 덮음)에 그대로 —
 *     누르면 바로 닫히고, 6초 뒤 저절로 닫힌다(claim.notice).
 * 셸 조각 교체로 다시 실행된다 — 화면마다 한 번(window.__FOMS_PROD_PARTS_BOUND.crew). 읽기 전용(창 없음)도 싣는다(카드 고치기). */
(function () {
  'use strict';

  var root = document.querySelector('[data-foms-prod-home]');
  var board = window.FomsPartsBoard;
  if (!root || !board) { return; }
  var bound = window.__FOMS_PROD_PARTS_BOUND = window.__FOMS_PROD_PARTS_BOUND || {};
  if (bound.crew === root || board.root !== root) { return; }
  bound.crew = root;

  var cfg = board.cfg || {};
  var LABEL = cfg.label || '';
  var NAME = cfg.me || '';
  var ME = String(cfg.me_id);
  var MINE = cfg.mode === 'part';
  var BASIC = cfg.basic || {}; // 재단 '기본' · 조립 '조립 없음' 글(서버 설정 part_constants.basic_view — 여기서 짓지 않는다)
  var claim = window.FomsPartsClaim || {};
  function attr(card, name) { return card.getAttribute(name) || ''; }
  function safeJsonParse(value, fallback) {
    try { var text = String(value || '').trim(); return text ? JSON.parse(text) : fallback; } catch (e) { return fallback; }
  }
  function of(card) { return (card && safeJsonParse(card.getAttribute('data-pp-crew'), {})) || {}; }
  function el(tag, cls, text, act) {
    var node = document.createElement(tag);
    node.className = cls || '';
    node.textContent = text || '';
    if (act) { node.type = 'button'; node.setAttribute('data-pp-act', act); }
    return node;
  }
  function half(cr) { return cr.d ? LABEL + ' ' + cr.d + '/' + cr.n + ' 완료' : ''; }
  // 시작한 때 — 오늘 "08:10부터" · 어제 "어제부터" · 그 전 "11/23부터"(서버 KST 오늘 cfg.today 로만 셈)
  function since(day, iso) {
    var old = claim.sinceText ? claim.sinceText(day) : '';
    var at = !old && claim.sinceAt ? claim.sinceAt(iso) : '';
    return old || (at ? at.split(' ')[1] + '부터' : '');
  }
  function pending(cr) {
    return (cr.people || []).filter(function (p) { return !p.done && String(p.uid) !== ME; });
  }

  // ── 받은 표시(쓰기 응답 · 30초 받아 오기) → 카드 data-pp-crew. 내 몫(none · held · done)을 돌려준다 ──
  function setAttrs(card, mark) {
    var cr = (mark && mark.crew) || {};
    if (cr.n) { card.setAttribute('data-pp-crew', JSON.stringify(cr)); } else { card.removeAttribute('data-pp-crew'); }
    return cr;
  }

  // ── 카드 칸 — parts.js renderAct 가 claim.special 뒤에 부른다(손 체크 · 막힘 · 내 작업 한 층은 claim). 그렸으면 true ──
  function undoRow(st, text) {
    var row = el('div', 'fph-wi pp-act pp-undo-row pp-st-' + st + ' pp-only-done');
    row.appendChild(el('span', '', text));
    row.appendChild(el('button', 'foms-prod-home__btn pp-undo', st === 'basic' ? BASIC.undo : LABEL + ' 완료 취소', 'undo')); // 완료 단추와 짝(사장님 2026-11-26)
    return row;
  }
  function render(card, box, o) {
    var st = attr(card, 'data-state');
    var cr = of(card);
    var head = cr.head || (o.mine ? '다른 사람 작업 중' : '작업 중');
    var canUndo = o.writable && (!o.mine || attr(card, 'data-done-me') === '1');
    if (st === 'none') { // 안 봄 · 미정 — 재단 [기본][재단 시작] · 조립 [조립 없음][조립 시작](o.cut = 기본이 되는 파트, 11-28), 그 밖 [엣지 시작] 등. 반장 · 관리자는 [<파트> 완료](check — 한 장씩 바로 완료, 사장님 11-27)
      if (!o.writable) { return true; } // 보기만 = 단추 없음
      var row = o.cut || !o.mine ? el('div', 'pp-two') : box;
      if (o.cut) { row.appendChild(el('button', 'foms-prod-home__btn pp-pick-basic', BASIC.word, 'basic')); }
      // 진한 단추는 한 칸에 하나(C59) — 파트 계정 [<파트> 시작]은 진하게(재단처럼, 사장님 11-27), 반장 · 관리자 칸은 [<파트> 완료]가 진하니 옅게
      row.appendChild(el('button', 'foms-prod-home__btn' + (o.mine ? ' foms-prod-home__btn--pri' : '') + (o.cut ? '' : ' pp-act'), LABEL + ' 시작', 'take'));
      if (row !== box) { box.appendChild(row); }
      if (!o.mine) { (o.cut ? box : row).appendChild(el('button', 'fph-qr__done pp-act pp-fin is-pair', LABEL + ' 완료', 'check')); } // 재단은 둘째 줄
      return true;
    }
    if (st === 'need') {
      if (o.mine && attr(card, 'data-done-me') === '1') { // 내 몫만 완료(E1) — '완료' 칸
        box.appendChild(el('span', 'fph-wi pp-act pp-st-need' + (canUndo ? ' pp-not-done' : ''), half(cr) + (cr.left ? ' · ' + cr.left + ' 작업 중' : '')));
        if (canUndo) { box.appendChild(undoRow('done', half(cr))); }
      } else if (o.mine) { // 남이 작업 중(B · D · I) — 이름 칸(누르면 담당 바꾸기) + [같이 작업]
        var two = el('div', 'pp-two pp-two--join');
        two.appendChild(claim.held(card, head, 'pp-st-taken'));
        two.appendChild(el('button', 'foms-prod-home__btn foms-prod-home__btn--pri', LABEL + ' 같이\u00a0작업', 'join'));
        box.appendChild(two);
      } else if (!o.writable) {
        box.appendChild(el('span', 'fph-wi pp-act pp-st-need', head));
      } else { // 반장 · 관리자(G) — 이름 칸(둘째 줄 "재단 1/2 완료") + [재단 완료](= 대신 완료 check — 남은 사람 몫 모두)
        var own = attr(card, 'data-done-me') === '1'; // 같이 작업해 자기 몫 완료 — '완료' 칸에 자기 몫 되돌리기 줄(파트 계정과 같은 자리)
        box.appendChild(claim.held(card, head, 'pp-st-need pp-not-need' + (own ? ' pp-not-done' : ''), half(cr) || null));
        box.appendChild(el('button', 'fph-qr__done pp-act pp-fin pp-only-need', LABEL + ' 완료', 'check'));
        if (own) { box.appendChild(undoRow('done', half(cr))); }
      }
      return true;
    }
    if (st !== 'done' && st !== 'basic') { return false; }
    var by = (st === 'done' && cr.done) || attr(card, 'data-done-name');
    var word = (st === 'done' ? LABEL + ' 완료' : BASIC.word) + (by ? ' · ' + by : '');
    box.appendChild(el('span', 'fph-wi pp-act pp-st-' + st + (canUndo ? ' pp-not-done' : ''), word));
    if (canUndo) { box.appendChild(undoRow(st, word)); }
    return true;
  }

  // ── 창 글 — modal.plan 이 먼저 부른다. 여러 명 창이 아니면 null(지금 창 글) ──
  function swapPlan(cr, p) {
    var M = window.FomsPartsModal || {};
    var toward = M.toward ? M.toward(NAME) : NAME + '으로';
    return { title: '담당을 ' + p.name + '에서 ' + toward + ' 바꿀까요?', line: '담당 ' + cr.who + ' → 담당 ' + p.swap, run: '담당 바꾸기',
      tone: 'taken', target: p.uid,
      note: (M.heldSince ? M.heldSince(null, p.subj, p.at) : '') + ' 바꾸기 전에 ' + p.name + '에게 말해 주세요.' };
  }
  function plan(action, card) {
    var cr = of(card);
    var st = attr(card, 'data-state');
    if (action === 'join') { // 창 1 — [같이 작업]
      var who = cr.who || '다른 사람';
      var at = since(cr.day, cr.at);
      return { title: LABEL + ' 같이 작업할까요?', line: who + ' 작업 중 → ' + (cr.join || NAME) + ' 작업 중', run: LABEL + ' 같이 작업', tone: 'need',
        note: (cr.who_subj || '다른 사람이') + ' ' + (at ? at + ' ' : '') + '작업 중인 도면이에요. 같이 작업하면 ' +
          ((cr.n || 0) + 1 === 2 ? '두 사람 모두' : '모두') + ' [' + LABEL + ' 완료]를 눌러야 완료돼요.' };
    }
    if (!cr.n || st !== 'need' && action !== 'undo') { return null; }
    var left = pending(cr);
    if (action === 'takeover') { // 창 3 — 누구와 바꿀지(완료를 누른 사람은 빠짐 · 하나면 고르기 없이)
      if (left.length === 1) { return swapPlan(cr, left[0]); }
      if (!left.length) { return null; }
      return { title: '누구와 담당을 바꿀까요?', note: '완료를 누른 사람은 바꿀 수 없어요.', line: '담당 ' + cr.who, run: MINE ? '담당 바꾸기' : '다음',
        tone: 'taken', locked: true, next: MINE ? null : 'give', who: left.map(function (p) { // 반장 · 관리자는 자리만 고르고 [다음] → "누구에게 줄까요?"
          return { uid: p.uid, text: p.name + ' · ' + since(p.day, p.at) + ' 작업 중', line: '담당 ' + cr.who + (MINE ? ' → 담당 ' + p.swap : '') };
        }) };
    }
    if (action === 'held') { // 창 2 — 반장 · 관리자 고르기([담당 바꾸기 ›]는 늘 다음 창 — 바꿀 사람이 하나면 "누구에게 줄까요?", 둘 이상이면 자리 고르기 먼저)
      var M = window.FomsPartsModal || {};
      var swap = left.length === 1 ? [['give', '담당 바꾸기 ›', 'taken', left[0].uid, true]] : left.length ? [['takeover', '담당 바꾸기 ›', 'taken', null, true]] : [];
      var join = cr.me === 'none' ? [['join', '같이 작업', 'join', null, true]] : []; // Q22 — 아직 작업자가 아니면 [같이 작업] 창으로
      // 차례 = 카드 [시작 취소][<파트> 완료]와 같이 되돌리는 쪽 먼저 · 끝내는 [대신 완료] 맨 끝(C59). [대신 완료] = check(자기 몫 포함 남은 사람 모두)
      var choices = left.map(function (p) { return ['remove', p.name + ' 시작 취소', 'release', p.uid]; })
        .concat(swap, join, [['check', '대신 완료', 'done']]);
      return { title: cr.d || !M.heldTitle ? cr.who + ' 작업 중' : M.heldTitle(card, cr.who), line: '', run: '', tone: 'taken', choices: choices,
        note: cr.d ? half(cr) + ' — ' + cr.done + ' 완료 · ' + cr.left + ' 작업 중' : '' }; // 한 명만 완료한 도면은 그 줄만 남긴다(다른 정보)
    }
    if (action === 'done' && cr.me === 'held' && cr.others_left) { // 내 [재단 완료] — 남이 아직(재단 1/2 완료로)
      return { title: LABEL + ' 완료할까요?', line: '작업 중 → ' + LABEL + ' ' + (cr.d + 1) + '/' + cr.n + ' 완료 · ' + NAME,
        run: LABEL + ' 완료', tone: 'done',
        note: cr.others_left_subj + ' 아직 작업 중이라 ' + cr.others_left_subj + ' 완료해야 도면이 완료돼요.' };
    }
    if (action === 'release' && cr.me === 'held' && cr.n > 1) { // 내 [시작 취소] — 남은 사람이 있음
      var mine = (cr.people || []).filter(function (p) { return String(p.uid) === ME; })[0] || {};
      var rest = cr.d === cr.n - 1; // 남은 사람이 모두 완료 = 저절로 완료(Q6) — 바뀐 뒤는 완료 칸 글 그대로
      return { title: LABEL + ' 시작을 취소할까요?', run: LABEL + ' 시작 취소', tone: 'release',
        line: cr.who + ' 작업 중 → ' + (rest ? LABEL + ' 완료 · ' + cr.done : (mine.drop || '') + ' 작업 중'),
        note: rest ? '남은 사람이 모두 완료라 도면이 완료돼요.' : '' };
    }
    if (action === 'undo' && st === 'need' && cr.me === 'done') { // 내 몫 되돌리기(재단 1/2 완료 → 작업 필요) — 대상 = 본인(반장도 자기 몫만)
      return { title: LABEL + ' 완료를 취소할까요?', line: half(cr) + ' → 작업 중 · ' + NAME, run: LABEL + ' 완료 취소', tone: 'need', target: Number(ME) };
    }
    if (action === 'undo' && st === 'done' && cr.once && !MINE) { // 반장 · 관리자가 바로 완료한 도면(서버 표지 once) — 한 번에 미정(사장님 11-27)
      return { title: LABEL + ' 완료를 취소할까요?', line: LABEL + ' 완료 → 미정', run: LABEL + ' 완료 취소', tone: 'need' };
    }
    if (action === 'undo' && st === 'done' && (cr.me !== 'done' || !MINE)) { // 반장 · 관리자 대신 되돌리기 — 완료만 모두 끄고(자기 몫 포함, Q23) 작업하던 사람은 그대로
      return { title: LABEL + ' 완료를 취소할까요?', line: LABEL + ' 완료 → ' + cr.who + ' 작업 중', run: LABEL + ' 완료 취소', tone: 'need' };
    }
    return null;
  }

  // ── 넘김 말풍선 — 서버 글 그대로(그림 칸 아래쪽 안, 6초 · 누르면 닫힘 — 열린 동안 받아 오기는 그 카드를 건너뛴다) ──
  function notice(card, text) { if (card && text && claim.notice) { claim.notice(card, text); } }

  window.FomsPartsCrew = { of: of, setAttrs: setAttrs, render: render, plan: plan, notice: notice };
})();
