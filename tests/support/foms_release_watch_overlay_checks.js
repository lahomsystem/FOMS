'use strict';
/*
 * foms-release-watch.js 시뮬레이션 둘째 묶음(2026-11-22 터치 감사 D1 · D2) — 열린 창 셀렉터(붙박이 도킹 시트 · 진짜 창) ·
 * 찾을 말을 쳐 둔 검색 칸. 가짜 창 · 시계는 foms_release_watch_node_checks.js 것을 쓴다(FOMS_SIM_WATCH_JS 도 같다).
 */
const { el, run, main, SEC } = require('./foms_release_watch_node_checks');

const S = {};
S.search_box_is_unsaved = () => run({}, async (t) => {
  const box = el({ type: 'search', value: '김' });
  await t.fire('document', 'input', { target: box });
  await t.advance(31 * SEC);
  await t.wake();
  const before = { n: t.env.reloads, why: t.why() };
  box.value = ''; // 비우면 막지 않는다
  await t.advance(15 * SEC);
  return { before };
});
S.untouched_search_box_does_not_block = () => run({}, async (t) => {
  t.document.activeElement = t.body; // 서버가 그린 찾을 말(defaultValue)은 그대로 — 고친 것이 아니다
  await t.fire('document', 'change', { target: el({ type: 'search', value: '박', defaultValue: '박' }) });
  await t.wake();
});
S.closed_overlay_search_does_not_block = () => run({}, async (t) => {
  await t.fire('document', 'input', { target: el({ type: 'search', value: '김', rendered: false }) }); // 닫힌 찾기 창 속 칸
  await t.wake();
});
const dialogEl = (attrs, classes) => el({ tagName: 'ASIDE', attrs, classes: classes || [] });
const SHEET = ['foms-tablet-sheet', 'is-open'];
S.docked_side_sheet_is_not_overlay = () => run({ overlays: [dialogEl({ role: 'dialog', 'aria-modal': 'false' }, SHEET.concat('foms-tablet-sheet--docked'))] },
  async (t) => { await t.wake(); return { why: t.why() }; });
S.undocked_open_side_sheet_blocks = () => run({ overlays: [dialogEl({ role: 'dialog', 'aria-modal': 'false' }, SHEET)] }, async (t) => {
  await t.wake();
  const before = { n: t.env.reloads, why: t.why() };
  t.env.overlays[0].classes = ['foms-tablet-sheet']; // 닫힘
  await t.advance(15 * SEC);
  return { before };
});
S.modal_dialog_role_blocks = () => run({ overlays: [dialogEl({ role: 'dialog', 'aria-modal': 'true' }), dialogEl({ role: 'alertdialog' })] },
  async (t) => {
    await t.wake();
    const before = { n: t.env.reloads, why: t.why() };
    t.env.overlays.forEach((o) => { o.hiddenUp = true; }); // 문서에 남아 있어도 숨으면(hidden) 열린 창이 아니다
    await t.advance(15 * SEC);
    return { before };
  });

main(S).catch((e) => { console.error(e); process.exit(1); });
