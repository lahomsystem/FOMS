/* 생산 파트 도면 카드 — 한 도면 · 한 파트를 여러 명이 같이 작업(설계서 2026-11-25 multi-holder §5 · §8 · §10 M2, 시안 01 A ~ I · 창 셋).
 * 쓰기 없음(fetch 0) — 요청은 foms-production-parts.js 의 send() 하나. 이름 줄("이시영 · 김재단 외 1")은 서버가 카드(data-pp-crew)와
 * 응답 · 30초 받아 오기 표시(mark.crew)에 실어 준 글만 쓴다(foms/services/production/part_card_crew.py crew_view — 여기서 짓지 않는다).
 *   카드 칸(render — 작업 필요 · 완료 상태, 템플릿 home_parts.html pp_act 와 같은 규칙): 남이 작업 중 = [이름 칸 ›][같이 작업] ·
 *     내 몫만 완료 = "재단 1/2 완료 · 김재단 작업 중"('완료' 칸, 되돌리기 줄 "재단 1/2 완료") · 반장 · 관리자 = 이름 칸(둘째 줄 "재단 1/2 완료") +
 *     [재단 완료] · 보기만 = "이시영 · 김재단 작업 중" · 완료 = "재단 완료 · 이시영 · 김재단".
 *   창 글(plan — 창 그리기 foms-production-parts-modal.js 가 먼저 부른다): [같이 작업] 창 · [담당 바꾸기] 누구와(둘 이상이면 고르기 창,
 *     완료를 누른 사람은 빠짐) · 반장 고르기([담당 바꾸기 ›] [대신 완료] [{이름} 시작 취소]) · 남은 사람이 있는 [완료] · [시작 취소] · 되돌리기.
 *   넘김 말풍선(notice): 거의 같이 [작업 시작] = 서버 글 "이시영이 먼저 시작했어요."를 카드 말풍선(.pp-why, 6초)에 그대로.
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
  var claim = window.FomsPartsClaim || {};
  function attr(card, name) { return card.getAttribute(name) || ''; }
  function safeJsonParse(value, fallback) {
    try {
      var text = String(value || '').trim();
      return text ? JSON.parse(text) : fallback;
    } catch (e) {
      return fallback;
    }
  }
  function of(card) { return (card && safeJsonParse(card.getAttribute('data-pp-crew'), {})) || {}; }
  function el(tag, cls, text, act) {
    var node = document.createElement(tag);
    node.className = cls || '';
    node.textContent = text || '';
    if (act) { node.type = 'button'; node.setAttribute('data-pp-act', act); }
    return node;
  }
  function josa(name) { return claim.josa ? claim.josa(name, '가', '이') : name; }
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
    row.appendChild(el('button', 'foms-prod-home__btn pp-undo', '되돌리기', 'undo'));
    return row;
  }
  function render(card, box, o) {
    var st = attr(card, 'data-state');
    var cr = of(card);
    var head = cr.head || (o.mine ? '다른 사람 작업 중' : '작업 필요');
    var canUndo = o.writable && (!o.mine || attr(card, 'data-done-me') === '1');
    if (st === 'need') {
      if (o.mine && attr(card, 'data-done-me') === '1') { // 내 몫만 완료(E1) — '완료' 칸
        box.appendChild(el('span', 'fph-wi pp-act pp-st-need' + (canUndo ? ' pp-not-done' : ''), half(cr) + (cr.left ? ' · ' + cr.left + ' 작업 중' : '')));
        if (canUndo) { box.appendChild(undoRow('done', half(cr))); }
      } else if (o.mine) { // 남이 작업 중(B · D · I) — 이름 칸(누르면 담당 바꾸기) + [같이 작업]
        var two = el('div', 'pp-two pp-two--join');
        two.appendChild(claim.held(card, head, 'pp-st-taken'));
        two.appendChild(el('button', 'foms-prod-home__btn foms-prod-home__btn--pri', '같이 작업', 'join'));
        box.appendChild(two);
      } else if (!o.writable) {
        box.appendChild(el('span', 'fph-wi pp-act pp-st-need', head));
      } else { // 반장 · 관리자(G) — 이름 칸(둘째 줄 "재단 1/2 완료") + [재단 완료](= 남은 사람 몫 대신 완료)
        box.appendChild(claim.held(card, head, 'pp-st-need pp-not-need', half(cr) || null));
        box.appendChild(el('button', 'fph-qr__done pp-act pp-fin pp-only-need', LABEL + ' 완료', 'done'));
      }
      return true;
    }
    if (st !== 'done' && st !== 'basic') { return false; }
    var by = (st === 'done' && cr.done) || attr(card, 'data-done-name');
    var word = (st === 'done' ? LABEL + ' 완료' : '기본') + (by ? ' · ' + by : '');
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
      note: (M.heldSince ? M.heldSince(null, p.name, p.at) : '') + ' 바꾸기 전에 ' + p.name + '에게 말해 주세요.' };
  }
  function plan(action, card) {
    var cr = of(card);
    var st = attr(card, 'data-state');
    if (action === 'join') { // 창 1 — [같이 작업]
      var who = cr.who || '다른 사람';
      var at = since(cr.day, cr.at);
      return { title: '같이 작업할까요?', line: who + ' 작업 중 → ' + (cr.join || NAME) + ' 작업 중', run: '같이 작업', tone: 'need',
        note: josa(who) + ' ' + (at ? at + ' ' : '') + '작업 중인 도면이에요. 같이 작업하면 ' + ((cr.n || 0) + 1 === 2 ? '두 사람 모두' : '모두') +
          ' [' + LABEL + ' 완료]를 눌러야 완료돼요.' };
    }
    if (!cr.n || st !== 'need' && action !== 'undo') { return null; }
    var left = pending(cr);
    if (action === 'takeover') { // 창 3 — 누구와 바꿀지(완료를 누른 사람은 빠짐 · 하나면 고르기 없이)
      if (left.length === 1) { return swapPlan(cr, left[0]); }
      if (!left.length) { return null; }
      return { title: '누구와 담당을 바꿀까요?', note: '완료를 누른 사람은 바꿀 수 없어요.', line: '담당 ' + cr.who, run: '담당 바꾸기',
        tone: 'taken', locked: true, who: left.map(function (p) {
          return { uid: p.uid, text: p.name + ' · ' + since(p.day, p.at) + ' 작업 중', line: '담당 ' + cr.who + ' → 담당 ' + p.swap };
        }) };
    }
    if (action === 'held') { // 창 2 — 반장 · 관리자 고르기
      var M = window.FomsPartsModal || {};
      var choices = [['takeover', '담당 바꾸기 ›', 'taken', null, true], ['done', '대신 완료', 'done']].concat(left.map(function (p) {
        return ['remove', p.name + ' 시작 취소', 'release', p.uid];
      }));
      return { title: cr.who + ' 작업 중인 도면이에요', line: cr.who + ' 작업 중', run: '', tone: 'taken', choices: choices,
        note: cr.d ? half(cr) + ' — ' + cr.done + ' 완료 · ' + cr.left + ' 작업 중' : (M.heldSince ? M.heldSince(card) : '') };
    }
    if (action === 'done' && cr.me === 'held' && cr.others_left) { // 내 [재단 완료] — 남이 아직(재단 1/2 완료로)
      return { title: LABEL + ' 완료로 바꿀까요?', line: '작업 필요 → ' + LABEL + ' ' + (cr.d + 1) + '/' + cr.n + ' 완료 · ' + NAME,
        run: LABEL + ' 완료', tone: 'done',
        note: josa(cr.others_left) + ' 아직 작업 중이라 ' + josa(cr.others_left) + ' 완료해야 도면이 완료돼요.' };
    }
    if (action === 'release' && cr.me === 'held' && cr.n > 1) { // 내 [시작 취소] — 남은 사람이 있음
      var mine = (cr.people || []).filter(function (p) { return String(p.uid) === ME; })[0] || {};
      return { title: '시작을 취소할까요?', line: cr.who + ' 작업 중 → ' + (mine.drop || '') + ' 작업 중', run: '시작 취소', tone: 'release',
        note: cr.d === cr.n - 1 ? '남은 사람이 모두 완료라 도면이 완료돼요.' : '' };
    }
    if (action === 'undo' && st === 'need' && cr.me === 'done') { // 내 몫 되돌리기(재단 1/2 완료 → 작업 필요)
      return { title: '작업 필요로 되돌릴까요?', line: half(cr) + ' → 작업 필요 · ' + NAME, run: '되돌리기', tone: 'need' };
    }
    return null;
  }

  // ── 넘김 말풍선 — 서버 글 그대로(6초, 열린 동안 받아 오기는 그 카드를 건너뛴다) ──
  function notice(card, text) { if (card && text && claim.say) { claim.say(card, text); } }

  window.FomsPartsCrew = { of: of, setAttrs: setAttrs, render: render, plan: plan, notice: notice };
})();
