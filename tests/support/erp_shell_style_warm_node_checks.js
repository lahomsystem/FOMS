'use strict';
/*
 * 미리 받은 조각의 CSS 미리 받기(11-19) 시뮬레이션 — 판정은 tests/domains/test_erp_shell_style_warm.py 가 한다.
 *
 *   warm  — 미리 받은 조각의 새 stylesheet 만 <link rel="preload" as="style"> 로 head 에 붙는다. 응답 처리 안에서는 0개(다음 작업).
 *           문서 머리 · 본문에 이미 있는 stylesheet · 이미 건 style preload · rel=icon/manifest 는 빼고, 같은 조각을 다시 받아도
 *           (하트비트 304) 다른 조각이 같은 CSS 를 들어도 한 번만. 데이터 절약이면 0개.
 *   nav   — 누름(스왑)은 stylesheet 를 곧바로 달고 preload 는 걸지 않는다.
 *
 * 환경 변수 FOMS_SIM_SHELL_JS 가 있으면 그 사본을 돌린다(음성 대조군).
 */
const { boot, ORIGIN } = require('./erp_shell_sim_boot.js');

const CONS = [
  '<link rel="stylesheet" href="/static/css/a.css?v=1">',
  '<link rel="icon" type="image/svg+xml" href="/static/favicon.svg?v=1">',
  '<link rel="manifest" href="/static/manifest.json?v=1">',
  '<link href="/static/css/b.css?v=1" rel="stylesheet">',
  '<link rel="stylesheet" href="/static/css/head.css?v=1">',
  '<div class="erp-dashboard">시공</div>',
  "<link rel='stylesheet' href='/static/css/body.css?v=1'>",
  '<link rel="stylesheet" href="/static/css/pre.css?v=1">',
  '<link rel="stylesheet" href="/static/css/late.css?v=1">',
].join('\n');
const SHIP = '<link rel="stylesheet" href="/static/css/a.css?v=1">\n<link rel="stylesheet" href="/static/css/d.css?v=1"><div>출고</div>';
const FRAGMENTS = { '/erp/construction/dashboard': CONS, '/erp/shipment': SHIP };
const DOC_LINKS = [
  ['stylesheet', '/static/css/head.css?v=1'],
  ['stylesheet', '/static/css/body.css?v=1', null, 'body'],
  ['preload', '/static/css/pre.css?v=1', 'style'],
  ['icon', '/static/favicon.svg?v=1'],
];

const short = (l) => [l.rel, l.getAttribute('as'), l.href.replace(ORIGIN, '')];

async function warm(saveData) {
  const b = boot({ path: '/erp/dashboard', docLinks: DOC_LINKS, fragmentHtml: (p) => FRAGMENTS[p], saveData });
  await b.shell.prefetchShellFragment(ORIGIN + '/erp/construction/dashboard');
  await b.drain();
  const atResponse = b.appended.length;
  await b.advance(50);
  const first = b.appended.map(short);
  await b.shell.prefetchShellFragment(ORIGIN + '/erp/construction/dashboard', { force: true }); // 하트비트 다시 받기(304)
  await b.advance(50);
  const afterRefetch = b.appended.length;
  await b.shell.prefetchShellFragment(ORIGIN + '/erp/shipment');
  await b.advance(50);
  return { atResponse, first, afterRefetch, afterOther: b.appended.slice(first.length).map(short),
    refetchCalls: b.calls.filter((c) => c.inm).length };
}

async function nav() {
  const b = boot({ path: '/erp/dashboard', docLinks: DOC_LINKS, fragmentHtml: (p) => FRAGMENTS[p] });
  await b.shell.navigateByShell(ORIGIN + '/erp/shipment');
  await b.advance(50);
  return { appended: b.appended.map(short), swapped: b.swaps.length };
}

(async function run() {
  const out = { warm: await warm(false), saveData: await warm(true), nav: await nav() };
  process.stdout.write(JSON.stringify(out) + '\n');
})().catch((err) => {
  process.stderr.write(String((err && err.stack) || err) + '\n');
  process.exit(1);
});
