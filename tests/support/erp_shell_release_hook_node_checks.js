'use strict';
/*
 * erp-shell.js → 새 배포 감시(foms-release-watch.js) 고리 — 셸 조각 응답(200 · 304)의 X-Foms-Release 를
 * FOMS_RELEASE_WATCH.observe 로 넘기는가. 판정은 tests/domains/test_foms_release_watch_js.py.
 * 환경 변수 FOMS_SIM_SHELL_JS 가 있으면 그 사본을 돌린다(음성 대조군).
 */
const { boot, ORIGIN } = require('./erp_shell_sim_boot.js');

(async () => {
  const b = boot({ path: '/erp/production/home', release: 'R9' });
  const seen = [];
  b.sandbox.FOMS_RELEASE_WATCH = { observe: (v) => seen.push(v) };
  await b.shell.prefetchShellFragment(ORIGIN + '/erp/shipment', { force: true }); // 200
  await b.drain();
  await b.shell.prefetchShellFragment(ORIGIN + '/erp/shipment', { force: true }); // ETag 있음 → 304
  await b.drain();
  const quiet = boot({ path: '/erp/production/home', release: 'R9' }); // 감시가 없는 문서(로그인 전 · 값 없음)
  await quiet.shell.prefetchShellFragment(ORIGIN + '/erp/shipment', { force: true });
  await quiet.drain();
  process.stdout.write(JSON.stringify({ seen, inm: b.calls.map((c) => !!c.inm), quietCalls: quiet.calls.length }));
})().catch((e) => { console.error(e); process.exit(1); });
