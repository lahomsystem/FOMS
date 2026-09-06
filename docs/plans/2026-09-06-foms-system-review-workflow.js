// FOMS 시스템 전체 개발 검토 — Workflow 도구용 실행 스크립트 (2026-09-06)
// 사용법: 새 세션에서 Workflow({ scriptPath: "C:/DEV/FOMS/docs/plans/2026-09-06-foms-system-review-workflow.js" })
// 유일한 컨텍스트 = docs/plans/2026-09-06-foms-system-review-prompt.md (이 스크립트는 그 문서 §7 의 실행 계획을 코드로 옮긴 것).
export const meta = {
  name: 'foms-system-review',
  description: 'FOMS 시스템 전체 검토: CEO 설계 → 8차원 워커 병렬 감사 → 보고서 통합 → 2판정 리뷰 → CEO 판정(fix 1회)',
  phases: [
    { title: 'CEO 설계', detail: '프롬프트 §4 차원 확정, HEAD 이동 보정' },
    { title: '차원 감사', detail: '워커 8 병렬, 읽기 전용, §7.3 스키마' },
    { title: '통합', detail: '보고서 ①~⑦ + 원장 작성, §8 스니펫 실행' },
    { title: '리뷰', detail: '스펙/품질 2판정, 편집 금지' },
    { title: 'CEO 판정', detail: 'ship/fix/block, fix 는 1회' },
  ],
}

const ROOT = 'C:/DEV/FOMS'
const PROMPT = 'docs/plans/2026-09-06-foms-system-review-prompt.md'
const REPORT = 'docs/plans/2026-09-06-foms-system-review-report.md'
const LEDGER = 'docs/plans/2026-09-06-foms-system-review-report-ledger.md'

const COMMON = `공통 규칙(절대):
- 먼저 Read 도구로 ${ROOT}/${PROMPT} 전체를 읽는다(길다 — 여러 번 나눠 읽는다). 그 파일이 유일한 컨텍스트 원본이다. §3 절대 규칙 12개를 전부 적용한다.
- 모든 명령은 \`cd ${ROOT} && ...\` 로 시작. bash. python/pytest 앞에 PYTHONIOENCODING=utf-8. 시간 제한은 timeout N.
- 읽기 전용: 저장소 파일 편집 금지(통합자만 §0 의 보고서·원장 2개), pip/npm 설치 금지, git 은 조회만, 전체 pytest 금지, DB 는 로컬 dev 읽기만, railway CLI·ssh 금지, production 접근 금지.
- 운영 수치(사용자 수·주문량·트래픽·비용) 추정 금지 → "확인 필요" + §6 ⑥ 열린 질문.
- 시스템 전체 관점(§1 판정 기준): 헤드라인은 구조·흐름·거버넌스 수준 + 왜 시스템 문제인지 + 영향 시점. 파일 한두 개짜리 발견은 minor_parked.
- 근거 의무: 모든 관측에 경로:행 앵커 또는 실행 명령의 결정적 출력 한 줄. 앵커 없으면 "가설".
- 출력 언어 한글, 한자 금지(코드·API·고유명사 예외). 한국어 낱말을 다른 언어로 바꾸지 않는다.
- 최종 텍스트는 사람이 읽는 메시지가 아니라 StructuredOutput 이다.`

const STR = { type: 'string' }
const STR_ARR = { type: 'array', items: STR }
const EVIDENCE = { type: 'object', required: ['claim', 'anchor', 'verified_by'], properties: { claim: STR, anchor: STR, verified_by: STR } }
const RISK = { type: 'object', required: ['title', 'why_systemic', 'severity', 'horizon', 'evidence'], properties: {
  title: STR, why_systemic: STR, severity: { enum: ['높음', '중간', '낮음'] }, horizon: { enum: ['지금', '6개월', '2년'] },
  evidence: { type: 'array', items: EVIDENCE } } }
const NEED = { type: 'object', required: ['title', 'what', 'why', 'first_step', 'verify'], properties: { title: STR, what: STR, why: STR, first_step: STR, verify: STR } }
const PRIOR = { type: 'object', required: ['item', 'result', 'anchor'], properties: { item: STR, result: { enum: ['확인 유지', '승격', '반박'] }, anchor: STR } }

const CEO_SCHEMA = { type: 'object', required: ['head', 'dimensions', 'worker_common_rules', 'synthesis_instructions'], properties: {
  head: STR,
  dimensions: { type: 'array', minItems: 8, maxItems: 8, items: { type: 'object', required: ['key', 'title', 'core_questions', 'anchors', 'commands', 'fit_criteria', 'pitfalls', 'prior_items'], properties: {
    key: STR, title: STR, core_questions: STR_ARR, anchors: STR_ARR, commands: STR_ARR, fit_criteria: STR, pitfalls: STR_ARR, prior_items: STR_ARR } } },
  worker_common_rules: STR, synthesis_instructions: STR } }

const WORKER_SCHEMA = { type: 'object', required: ['dimension', 'title', 'verdict', 'system_risks', 'lacking', 'needed', 'prior_observations', 'stack_questions', 'minor_parked', 'commands_run'], properties: {
  dimension: STR, title: STR,
  verdict: { type: 'object', required: ['fit', 'one_line'], properties: { fit: { enum: ['적합', '조건부', '부적합'] }, one_line: STR } },
  system_risks: { type: 'array', items: RISK }, lacking: { type: 'array', items: RISK }, needed: { type: 'array', items: NEED },
  prior_observations: { type: 'array', items: PRIOR },
  stack_questions: STR_ARR, minor_parked: STR_ARR,
  commands_run: { type: 'array', items: { type: 'object', required: ['cmd', 'decisive_line'], properties: { cmd: STR, decisive_line: STR } } } } }

const SYNTH_SCHEMA = { type: 'object', required: ['report_path', 'ledger_path', 'line_count', 'sections', 'anchor_bad', 'hanja', 'notes'], properties: {
  report_path: STR, ledger_path: STR, line_count: { type: 'integer' }, sections: STR_ARR, anchor_bad: { type: 'integer' }, hanja: { type: 'integer' }, notes: STR } }

const REVIEW_SCHEMA = { type: 'object', required: ['verdict', 'findings', 'anchors_checked', 'commands_run', 'snippet_output'], properties: {
  verdict: { enum: ['ship', 'fix', 'block'] },
  findings: { type: 'array', items: { type: 'object', required: ['severity', 'where', 'problem', 'fix'], properties: { severity: { enum: ['높음', '중간', '낮음'] }, where: STR, problem: STR, fix: STR } } },
  anchors_checked: { type: 'integer' }, commands_run: { type: 'integer' }, snippet_output: STR } }

const VERDICT_SCHEMA = { type: 'object', required: ['verdict', 'reasons', 'fix_list'], properties: { verdict: { enum: ['ship', 'fix', 'block'] }, reasons: STR_ARR, fix_list: STR_ARR } }

const DEFAULT_DIMS = [
  ['D1', '스택·의존성 적합성'], ['D2', '아키텍처·코드 구조'], ['D3', '데이터·마이그레이션'], ['D4', '테스트·CI·품질 시스템'],
  ['D5', '프론트엔드·자산 파이프라인'], ['D6', '보안·권한·개인정보'], ['D7', '운영·배포·관측·회복력'], ['D8', '개발 시스템(DX·하네스·문서·프로세스)'],
].map(([key, title]) => ({ key, title, core_questions: ['프롬프트 §4 의 해당 차원 핵심 질문 ①~⑥ 그대로'], anchors: ['프롬프트 §4'], commands: ['프롬프트 §4'], fit_criteria: '프롬프트 §4 판정 기준', pitfalls: ['프롬프트 §4 함정'], prior_items: ['프롬프트 §5 의 해당 차원 항목 전부'] }))

// ---------- 1. CEO 설계 ----------
phase('CEO 설계')
const ceo = await agent(`너는 이 워크플로의 CEO(총괄 설계자)다. 프롬프트 §7.1 1단계를 수행한다. 코드는 쓰지 않는다.
${COMMON}

할 일:
1. \`cd ${ROOT} && git log --oneline -1\` 로 현재 HEAD 를 적는다(head 필드). 프롬프트 §0 의 기준 커밋과 다르면 §2 사실 카드 수치 중 어긋날 만한 것(파일 수·줄 수·plans 수·수집 테스트 수)을 재측정해 dimensions 의 pitfalls 에 "재측정: 값 — 명령" 으로 보강한다.
2. 차원 8개(키 D1~D8·제목 고정)를 §4 그대로 확정한다 — core_questions(①~⑥ 전부), anchors(§4 목록, 실존 확인한 것만), commands(§4 목록), fit_criteria, pitfalls. prior_items 에는 §5 의 해당 차원 관측 항목 제목(태그 포함)을 전부 넣는다 — 워커가 하나씩 재검증한다.
3. worker_common_rules: §3 절대 규칙 + §7.1 2단계 + §7.3 스키마 규칙을 워커용 한 단락으로.
4. synthesis_instructions: 통합자가 보고서 ①~⑦(§6 계약)과 원장을 쓸 때 지킬 지침 — 워커 판정과 다른 판정을 낼 때 앵커 의무, ② 는 파일 한두 개짜리 금지, ③ 은 '새는 증거' 앵커, ④ 는 지금/이번 분기/12~24개월 + 첫 걸음·검증, ⑤ 는 유지/조건부 유지/교체 후보 + 교체 비용, ⑥ 은 §6 초안에서 출발, ⑦ 은 minor_parked 전부, 600줄·한 줄 600자·100KB 이하, [확인됨]/[가설] 표기, 한자 0.
결과는 StructuredOutput 으로만 반환.`, { label: 'ceo:design', phase: 'CEO 설계', effort: 'high', schema: CEO_SCHEMA })

const dims = (ceo && ceo.dimensions && ceo.dimensions.length === 8) ? ceo.dimensions : DEFAULT_DIMS
log(`CEO 설계 ${ceo ? `완료 · HEAD ${ceo.head}` : '실패 → 프롬프트 §4 기본 차원 사용'} · 차원 ${dims.length}개`)
const workerRules = (ceo && ceo.worker_common_rules) || '프롬프트 §3·§7.1·§7.3 규칙을 따른다.'

// ---------- 2. 차원 감사 (병렬) ----------
phase('차원 감사')
const workers = await parallel(dims.map((d) => () => agent(`너는 FOMS 시스템 검토 워커 ${d.key} "${d.title}" 담당이다. 프롬프트 §4 의 네 차원을 시스템 전체 관점에서 감사하고 §7.3 스키마로 판정을 낸다.
${COMMON}

CEO 가 정한 워커 공통 규칙:
${workerRules}

너의 차원 명세(CEO 확정):
${JSON.stringify(d, null, 2)}

절차:
1. 프롬프트 전체를 읽는다. 특히 §1(시스템 관점 정의)·§2(사실 카드 — 다시 재지 말고 인용, 어긋나면 "재측정: 값 — 명령")·§4(네 차원: 핵심 질문 ①~⑥·앵커·명령·판정 기준·함정)·§5(네 차원의 사전 관측 — 항목마다 재검증해 prior_observations 에 확인 유지/승격/반박 + 앵커)·§7.3(스키마).
2. anchors 파일을 실제로 연다. commands 를 실행하고 결정적 출력 한 줄을 commands_run 에 남긴다(리뷰어가 재실행한다).
3. 핵심 질문마다 답을 system_risks(구조적 위험: 왜 시스템 문제인지·심각도·시점·근거) / lacking(이미 새는 곳: '새는 증거' 앵커 필수) / needed(12~24개월 갖출 것: 무엇·왜·첫 걸음·검증)로 낸다. 각 3~6개(needed 3~5개). 앵커 없는 항목은 verified_by "가설".
4. 다른 차원과 겹치는 관측은 네 차원 관점으로만 쓰고 "→ Dn" 표시. 사소한 발견은 minor_parked. 운영 데이터가 있어야 답할 질문은 stack_questions.
5. verdict.fit 은 §4 판정 기준으로, one_line 에 한 문장 이유. §5 의 워커 판정(조건부)과 달라도 된다 — 근거를 앵커로.
결과는 StructuredOutput 으로만 반환.`, { label: `audit:${d.key}`, phase: '차원 감사', schema: WORKER_SCHEMA })))

const audits = workers.filter(Boolean)
const missing = dims.filter(d => !audits.some(a => a.dimension === d.key)).map(d => d.key)
log(`차원 감사 ${audits.length}/${dims.length} 회수 · 판정: ${audits.map(a => `${a.dimension}=${a.verdict.fit}`).join(' ')}${missing.length ? ` · 미회수 ${missing.join(',')}` : ''}`)

// ---------- 3. 통합 ----------
phase('통합')
const synthPrompt = (fixList) => `너는 통합자다. 프롬프트 §7.1 3단계를 수행한다 — 워커 ${audits.length}명의 감사 결과와 §5 를 대조해 보고서 ${ROOT}/${REPORT} 와 원장 ${ROOT}/${LEDGER} 를 ${fixList ? '수정한다' : '쓴다'}. 쓰기 허용 파일은 이 2개뿐이다.
${COMMON}
(통합자 예외: 위 2개 파일은 Write/Edit 허용.)

CEO 통합 지침:
${(ceo && ceo.synthesis_instructions) || '프롬프트 §6 계약을 그대로 따른다.'}

워커 감사 결과(차원별 JSON):
${JSON.stringify(audits, null, 2)}
${missing.length ? `\n감사 미수행 차원: ${missing.join(', ')} — 보고서 ① 에 "감사 미수행" 으로 적고 §5 사전 관측을 [가설] 로만 인용한다.` : ''}
${fixList ? `\n**이번 실행은 수정 라운드다.** CEO fix 목록을 전부 반영한다(다른 부분은 건드리지 않는다):\n${fixList.map((f, i) => `${i + 1}. ${f}`).join('\n')}` : ''}

작성 규칙: 프롬프트 §6 의 섹션 ①~⑦ 이름·순서 고정(\`## ①\` … \`## ⑦\`). 판정 3축(더 필요한 것/부족한 것/스택 적합성)이 ③④⑤ 에 이름 그대로. 항목마다 [확인됨: 앵커] 또는 [가설]. 워커 간 중복은 가장 구조적인 차원에 한 번만. minor_parked 는 ⑦ 로만. 한글·한자 0·600줄 이하·한 줄 600자 이하·100KB 이하. 원장에는 단계별 완료 상태·워커 판정 표·검증 출력을 적는다.
작성 후 반드시: ① §8 앵커 실존 스니펫을 보고서 경로를 인자로 실행해 ANCHOR_BAD·HANJA 값을 얻는다(ANCHOR_BAD > 0 이면 앵커를 직접 열어 고치고 다시 실행, 최대 3회). ② \`grep -nE "^## " ${REPORT}\` 섹션 목록, \`wc -l ${REPORT}\` 줄 수. ③ \`git status --short\` 로 신규 2파일 외 변경이 없음을 확인(타 창 변경은 손대지 않고 notes 에 적는다).
결과는 StructuredOutput 으로만 반환.`

const synth = await agent(synthPrompt(null), { label: 'synth:report', phase: '통합', schema: SYNTH_SCHEMA })
log(`통합 ${synth ? `완료 · ${synth.line_count}줄 · ANCHOR_BAD ${synth.anchor_bad} · HANJA ${synth.hanja}` : '실패'}`)
if (!synth) return { ceo, audits, synth: null, error: '통합자 실패 — journal.jsonl 확인' }

// ---------- 4. 리뷰 (2판정, 병렬) ----------
phase('리뷰')
const reviewPrompt = (kind) => `너는 ${kind === 'spec' ? '스펙 리뷰어(사용자 요청 충족 판정)' : '품질 리뷰어(정확성·실행 가능성 판정)'} 다. 프롬프트 §7.4 의 ${kind === 'spec' ? '스펙 리뷰어 (1)~(7)' : '품질 리뷰어 (1)~(9)'} 를 그대로 적용한다. 편집 금지 — 판정만. 워커 출력을 먼저 보지 말고 보고서와 저장소만 본다.
${COMMON}

검토 대상: ${ROOT}/${REPORT} (Read 로 전체). 프롬프트 §1·§2·§5·§6·§7.4·§8 과 대조한다.
${kind === 'quality' ? `§8 앵커 실존 스니펫을 보고서 경로를 인자로 직접 실행하고 출력 원문(ANCHOR_BAD n / HANJA n)을 snippet_output 에 적는다. 앵커 표본 15개 이상(차원마다 1개 이상 + ② 위주)을 직접 열어 대조하고 anchors_checked 에 수를, 명령 표본 5개 이상을 실행하고 commands_run 에 수를 적는다.` : `snippet_output 에는 "해당 없음" 을 적는다. anchors_checked·commands_run 은 직접 확인한 수(0 가능).`}
verdict: ship(높음 0·중간 2 이하) / fix(그 외, findings 에 위치·문제·수정안) / block(사용자 요청 자체를 못 채우거나 프로젝트 절대 규칙을 어기라고 권함). 결과는 StructuredOutput 으로만 반환.`

const [specReview, qualityReview] = await parallel([
  () => agent(reviewPrompt('spec'), { label: 'review:spec', phase: '리뷰', schema: REVIEW_SCHEMA }),
  () => agent(reviewPrompt('quality'), { label: 'review:quality', phase: '리뷰', schema: REVIEW_SCHEMA }),
])
log(`리뷰 · 스펙=${specReview ? specReview.verdict : '실패'}(${specReview ? specReview.findings.length : 0}건) · 품질=${qualityReview ? qualityReview.verdict : '실패'}(${qualityReview ? qualityReview.findings.length : 0}건)`)

// ---------- 5. CEO 판정 (+ fix 1회) ----------
phase('CEO 판정')
const verdictPrompt = (round, fixReport) => `너는 CEO(최종 판정자)다. 프롬프트 §7.1 5단계 — 보고서 ${ROOT}/${REPORT} 를 ship/fix/block 으로 판정한다. 편집 금지.
${COMMON}

${round === 1 ? '1차 판정이다. fix 면 통합자가 1회 반영하고 너가 다시 판정한다.' : '2차(최종) 판정이다. fix 라운드 결과를 보고 ship 또는 block 만 낸다(더 이상 fix 없음). fix 목록이 반영됐는지 파일을 직접 열어 확인한다.'}

통합자 보고: ${JSON.stringify(synth)}
스펙 리뷰: ${JSON.stringify(specReview)}
품질 리뷰: ${JSON.stringify(qualityReview)}
${fixReport ? `fix 라운드 통합자 보고: ${JSON.stringify(fixReport)}` : ''}

판정 규칙: 사용자 요청(판정 3축 + 시스템 전체 관점 + 근거 앵커) 충족이 1순위. 리뷰 findings 중 높음은 전부, 중간은 실질적인 것만 fix_list 로(위치·수정 내용을 통합자가 그대로 반영 가능하게). 낮음은 reasons 에만. 보고서를 직접 열어 표본 확인 후 판정. 결과는 StructuredOutput 으로만 반환.`

let verdict = await agent(verdictPrompt(1, null), { label: 'ceo:verdict-1', phase: 'CEO 판정', effort: 'high', schema: VERDICT_SCHEMA })
log(`CEO 1차 판정: ${verdict ? verdict.verdict : '실패'}${verdict && verdict.fix_list.length ? ` · fix ${verdict.fix_list.length}건` : ''}`)

let fixReport = null
let finalVerdict = verdict
if (verdict && verdict.verdict === 'fix' && verdict.fix_list.length) {
  fixReport = await agent(synthPrompt(verdict.fix_list), { label: 'synth:fix', phase: 'CEO 판정', schema: SYNTH_SCHEMA })
  log(`fix 라운드 ${fixReport ? `완료 · ${fixReport.line_count}줄 · ANCHOR_BAD ${fixReport.anchor_bad} · HANJA ${fixReport.hanja}` : '실패 — 총괄이 fix_list 를 직접 반영'}`)
  finalVerdict = await agent(verdictPrompt(2, fixReport), { label: 'ceo:verdict-2', phase: 'CEO 판정', effort: 'high', schema: VERDICT_SCHEMA })
  log(`CEO 최종 판정: ${finalVerdict ? finalVerdict.verdict : '실패 — 총괄이 직접 판정'}`)
}

return {
  head: ceo ? ceo.head : null,
  audits_summary: audits.map(a => ({ dimension: a.dimension, fit: a.verdict.fit, one_line: a.verdict.one_line, risks: a.system_risks.length, lacking: a.lacking.length, needed: a.needed.length, prior: a.prior_observations.length, minor: a.minor_parked.length })),
  missing, synth, specReview, qualityReview, verdict1: verdict, fixReport, finalVerdict,
}
