# FOMS 접목판 실행 계획 · 진행 원장 (2026-11-14)

> 설계서: `docs/specs/2026-11-14-foms-graft_SPEC.md` · 일꾼 지시문: `docs/plans/2026-11-14-foms-graft-worker-prompts.md`
> 크기: `**C`(며칠). 일감 하나 = 일꾼 한 세션. 일감이 끝나면 그 자리에서 아래 원장의 상태를 고친다. 막히면 `BLOCKED` + 까닭을 적고 다음 일감으로 간다.
> 일꾼 모델은 Opus. 깊이(effort)는 이 계획이 정했다(2절). 일꾼은 git 쓰기 명령을 하지 않는다 — 커밋 · 합치기는 본 세션(메인)이 확인한 뒤 한다.
> **판 2(11-14 사용자 결정 D206 ~ D212 반영)** — 처음 판(커밋 `7cedd2812`)에서 바뀐 것: 일감 넷이 늘었다(T13 특성 시험 · T14 처리기 떼어 내기 + 실행기 · T15 시공일 알림톡 + 폰 알림 · T16 상담 AI 평가). T10 이 물결 C 로 왔다. 일꾼은 모두 16.

## 1. 일하는 자리

| 무엇 | 값 |
|---|---|
| 바탕 | `origin/deploy` `01d596f7f` |
| 모으는 가지 | `session/foms-graft` — 워크트리 `c:\tmp\foms-s-foms-graft` |
| 셸 | Git Bash. 명령마다 `cd /c/tmp/<워크트리> && …`(턴이 바뀌면 자리가 되돌아간다) |
| 목업 | `docs/design/mockups/foms-graft/`(판 12장 + `foms-ds.css`) |
| 판 그림 | `C:\Users\USER\AppData\Local\Temp\claude\6e1e1701781f52ad\72115c98-d544-4383-b3f9-f740d10eabfc\scratchpad\graft\shots\<판 이름>.png` |
| 판 다시 찍기 | `python "C:\Users\USER\AppData\Local\Temp\claude\6e1e1701781f52ad\72115c98-d544-4383-b3f9-f740d10eabfc\scratchpad\dcshot\shoot3.py" <목업 폴더> <나올 폴더> <판 이름…>` |
| 화면 찍기 도구(T2 가 만든다) | `C:\Users\USER\AppData\Local\Temp\claude\6e1e1701781f52ad\72115c98-d544-4383-b3f9-f740d10eabfc\scratchpad\graft\screen_shot.py` — 저장소 밖(새 `tools/` · `docs/` 폴더를 만들지 않는다) |

## 2. 물결 · 일감 · 원장

| 물결 | 일감 | 일꾼 | 무엇 | 깊이 | 워크트리 | 기대는 것 | 상태 |
|---|---|---|---|---|---|---|---|
| A | T1 | W1 | 바탕 약속 — 새 표 셋 + 마이그레이션, ERP 물건 목록 · 읽기 도구, 할 일 목록(선언), AI 직원 목록(선언), 쓰인 곳 기록 도우미 | xhigh | `foms-s-foms-graft`(같이 씀) | — | DONE `e673ffd24`(11-14) |
| A | T2 | W2 | 새 화면 틀 — 스위치 모듈, `foms-ds.css` 가두어 싣기, 혼자 서는 문서 틀 · 위 줄 · 폰 아래 탭 · 긴급 빨간 창 · 공지 확인 창(D212), `/brain` 길 갈림, 빈 화면 여섯, 화면 찍기 도구 | high | `foms-s-foms-graft`(같이 씀) | — | DONE `001cb677e`(11-14) |
| B | T3 | W3 | 승인 대기(지식 고침) 새 화면 + 다시 확인 · 판 · 폰 승인(⑥ · ⑫ 의 지식 쪽) | xhigh | `foms-s-foms-graft` | T2 | DONE `1c89a3579` |
| B | T6 | W6 | 읽기 엔진 — 물어보기 ERP 읽기, 온톨로지 ERP 칸, 쓰인 곳 API, 내 질문 목록 | xhigh | 따로 `foms-s-graft-read` | T1 · T2(스위치) | DONE `bfbff2453` |
| B | T7 | W7 | 할 일 엔진 — 제안 생명주기 · 실행기 · 시공 메모 쓰기 · 승인 대기 API · 권한 · 감사 | max | 따로 `foms-s-graft-actions` | T1 · T2(스위치) | DONE `f3243babe` |
| B | T13 | W11 | **특성 시험**(D206) — 현재 작업 승인 · 도면 담당 맡기기 · 실측일 고치기 길의 지금 행동을 못박는다. 시험 파일만 | xhigh | `foms-s-foms-graft` | — (지금 코드. 물결 A 와 같이 띄워도 된다) | DONE `68b45778e` |
| C | T4 | W4 | 찾기 · 지식 표 · 지식 카드 새 화면 + 쓰인 곳(⑦ · ⑧) | high | `foms-s-foms-graft` | T2 · T6 | DONE `3f2b1b879` |
| C | T5 | W5 | 물어보기 · 온톨로지 새 화면 + ERP 읽기 답 · ERP 물건 · 할 일 종류(⑨ · ⑩) | high | `foms-s-foms-graft` | T2 · T6 | DONE `280406417` |
| C | T8 | W8 | AI 제안 화면 조각 — 승인 대기 ERP 칸 · 옆 창 · 폰 카드(⑥ · ⑫) + PC · 태블릿 · 폰 분홍 칸(② ③ ④) | high | `foms-s-foms-graft` | T3 · T7 | DONE(`a6d04731a`) |
| C | T10 | W10 | AI 직원 — 수준 표 · 승인율 · 실행 기록 · 훑기 규칙 셋 · 밤 단계 · AI 직원 화면(⑪ — 'AI 시험' 칸은 자리만) | high | 따로 `foms-s-graft-staff` | T1 · T2 · T7 | DONE `9899ef763` |
| C | T14 | W12 | **처리기 셋 떼어 내기 + 실행기 셋 + 목록 `mode` 를 `run` 으로**(D206 — 코어 변경) | max | 따로 `foms-s-graft-core` | T13(커밋됨) · T7 · T1 | DONE(`df32732b0` · 맞추기 `4e0b2a7ec`) |
| D | T9 | W9 | 상담 AI 접목 — 근거 남기기 · 규칙 제안 · 채널톡 작은 창 두 줄(⑤) | xhigh | 따로 `foms-s-graft-cs` | T1 · T7(· T14 — 실측 옮기기 제안이 실행까지 되려면) | DONE(`41922e4df` · 맞추기 `b4368b0aa`) |
| D | T15 | W13 | **바깥 알림 둘** — 시공일 안내 알림톡(D208: 스위치 · 서식 글 초안 · 실행기 · 훑기 `O4`) + 승인 대기 폰 알림(D210: 새 알림 종류 · 웹 푸시) | xhigh | 따로 `foms-s-graft-notify` | T7 · T10 · T14 · T2 | DONE(`dc8a9e011` · 맞추기 `9ca118614`) |
| D | T16 | W14 | **상담 AI 평가 묶음 + [시험 다시 돌리기]**(D209 — 돌릴 때 DB 에서 가린 글로 묶음 · WORKER 줄 일 · 돈 상한 · 결과 저장 · ⑪ 의 'AI 시험' 칸) | xhigh | 따로 `foms-s-graft-eval` | T10 · T1 | DONE(`12df85ba8`) |
| E | T11 | R1 | 검수(읽기만) — 설계서 맞춤 · 보안 · 품질 | xhigh | `foms-s-foms-graft`(읽기만) | T1 ~ T10 · T13 ~ T16 | DONE(검수 R-01 ~ R-43 — 고침 `f56741217` · `63f12b0ef` · `6e01dc5a0` · `28a2e131a` · `aa2b37f66`) |
| E | T12 | V1 | 합친 뒤 확인 — 명령 전부 · 스위치 끔 견주기 · 핀 · 머리 하나 · 소유 표 | high | `foms-s-foms-graft` | T11 고침 끝 | DONE(V1 — 명령 열둘 통과 · 스위치 끔 화면 deploy 와 바이트 같음 · 바깥 보내기 0 · 머리 graft_00 하나) |

- 물결마다 일꾼 수: A 2 · B 4 · C 5 · D 3 · E 2(차례로). 모두 16(만드는 일꾼 14 + 검수 1 + 확인 1).
- T13 은 아무것에도 기대지 않는다. 시험 파일만 만들므로 물결 A 가 도는 중에 띄워도 된다(그때 물결 A 는 셋).
- **T14 는 T13 이 커밋된 뒤에만 띄운다.** 특성 시험이 고치기 전 코드에서 초록이었다는 기록(메인이 다시 돌린 출력)이 원장에 있어야 한다.
- 깊이를 고른 까닭은 지시문 문서의 일꾼마다 한 줄. max 는 둘(T7 · T14) — 실제 주문을 바꾸는 길을 새로 만들거나, 모든 주문 흐름이 지나는 처리기를 고치는 일감이다. low · medium 은 없다.

## 3. 파일 주인 (같은 물결 안에서 겹치지 않는다)

새 파일은 주인이 만든다. 남의 파일을 고쳐야 하면 고치지 말고 보고서에 "누구 파일의 어디를 어떻게"를 적는다. 같은 파일을 여러 물결이 차례로 가질 때는 5절 표가 그 차례다.

### 물결 A

| 일감 | 가진 파일 |
|---|---|
| T1 | `foms/persistence/graft/__init__.py` · `models.py` · `models.py`(루트 — 끝의 import 한 줄만) · `migrations/versions/graft_00_action_proposals_usage_runs.py` · `foms/services/erp_ontology/__init__.py` · `objects.py` · `read.py` · `foms/services/erp_actions/__init__.py` · `registry.py` · `foms/services/ai_staff/__init__.py` · `registry.py` · `foms/services/brain/usage_events.py` · `tests/domains/test_graft_store.py` · `test_erp_ontology_read.py` · `test_erp_actions_registry.py` · `test_ai_staff_registry.py` · `test_brain_usage_events.py` |
| T2 | `foms/services/graft_flags.py` · `foms/web/brain.py` · `static/css/contexts/brain/ds/foms-ds.css` · `brain-ds-shell.css` · `templates/brain/ds/layout.html` · `_macros.html` · 빈 화면 `inbox.html` · `search.html` · `item.html` · `ask.html` · `onto.html` · `agents.html` · `static/js/brain/ds/ds-shell.js` · `tests/domains/test_graft_flags.py` · `test_brain_ds_scope.py` · `test_brain_ds_shell.py` · `tests/security/test_brain_ds_access.py` · 화면 찍기 도구(저장소 밖) |

### 물결 B

| 일감 | 가진 파일 |
|---|---|
| T3 | `templates/brain/ds/inbox.html` · `templates/brain/ds/partials/inbox_*.html`(이름이 `inbox_erp_` 로 시작하는 것은 T8 것) · `static/js/brain/ds/ds-inbox*.js`(이름이 `ds-inbox-erp` 로 시작하는 것은 T8 것) · `static/css/contexts/brain/ds/brain-ds-inbox.css` · `tests/domains/test_brain_ds_inbox.py` · `test_brain_ds_inbox_js.py` |
| T6 | `foms/services/erp_ontology/ask.py` · `foms/services/brain/chat_answer.py` · `chat_prompt.py` · `chat_retrieve.py` · `chat_log.py` · `ontology_view.py` · `ontology_cqs.py` · `usage_view.py`(새) · `foms/api/brain.py` · `foms/api/brain_chat.py` · `tests/domains/test_graft_ask_erp.py` · `test_graft_onto_erp.py` · `test_graft_usage_view.py` · `tests/security/test_graft_read_access.py` |
| T7 | `foms/services/erp_actions/lifecycle.py` · `runners.py` · `preview.py` · `access.py` · `views.py` · `foms/services/orders/construction_note.py` · `foms/api/erp_actions.py` · `foms/api/erp_action_runners.py` · `foms/platform/blueprints.py` · `docs/harness/foms_order_mutation_policy_manifest.json` · `tests/domains/test_erp_actions_lifecycle.py` · `test_erp_actions_runners.py` · `test_erp_actions_api.py` · `test_construction_note.py` · `tests/security/test_erp_actions_access.py` · `tests/postgres/test_erp_actions_pg.py` |
| T13 | `tests/domains/test_graft_char_quest_approve.py` · `test_graft_char_assign_draftsman.py` · `test_graft_char_measurement_date.py` · `tests/support/graft_char.py`(같이 쓰는 도우미 — 필요할 때만). **제품 코드는 한 줄도 고치지 않는다** |

T7 이 `registry.py`(T1 것)에 `check` · `preview` · `verify` 함수를 이어야 하면 `registry.py` 는 고치지 않고 `preview.py` 의 이름 → 함수 표로 잇는다.

### 물결 C

| 일감 | 가진 파일 |
|---|---|
| T4 | `templates/brain/ds/search.html` · `item.html` · `partials/search_*.html` · `partials/item_*.html` · `static/js/brain/ds/ds-search*.js` · `ds-item*.js` · `static/css/contexts/brain/ds/brain-ds-search.css` · `brain-ds-item.css` · `tests/domains/test_brain_ds_search.py` · `test_brain_ds_item.py` |
| T5 | `templates/brain/ds/ask.html` · `onto.html` · `partials/ask_*.html` · `partials/onto_*.html` · `static/js/brain/ds/ds-ask*.js` · `ds-onto*.js` · `static/css/contexts/brain/ds/brain-ds-ask.css` · `brain-ds-onto.css` · `tests/domains/test_brain_ds_ask.py` · `test_brain_ds_onto.py` |
| T8 | `templates/brain/ds/partials/inbox_erp_*.html` · `static/js/brain/ds/ds-inbox-erp*.js` · `static/css/contexts/brain/ds/brain-ds-inbox-erp.css` · `static/js/foms/graft-cells.js` · `static/css/components/foms-graft-cells.css` · `templates/orders/partials/tablet_sheet_ai_proposal.html`(새) · 고침: `templates/orders/partials/dashboard_grid.html` · `tablet_workqueue_grid.html` · `tablet_dashboard_sheet.html` · `dashboard_mobile_tower.html` · `templates/partials/shared/layout_nav.html` · `foms_tablet_rail.html` · `foms_side_tab.html` · `layout_head.html`(한 줄) · `layout_scripts.html`(한 줄) · `foms/web/orders/dashboard.py`(상세 조각 값) · `foms/web/brain.py`(ERP 제안만 보는 사람) · `tests/domains/test_graft_cells.py` · `test_brain_ds_inbox_erp.py` · 지금 계약 시험 가운데 이 고침에 닿는 것 |
| T10 | `foms/services/ai_staff/registry.py`(운영 AI `advance_stage` 수준 0 한 줄 — D214) · `foms/services/ai_staff/levels.py` · `metrics.py` · `runs.py` · `sweeps.py` · `views.py` · `foms/api/ai_staff.py` · `foms/platform/blueprints.py` · `docs/harness/foms_order_mutation_policy_manifest.json` · `tools/cron/erp_actions_expire.py` · `tools/cron/ai_staff_sweep.py` · `tools/cron/nightly.py` · `templates/brain/ds/agents.html` · `partials/agents_*.html`(`agents_evals` 는 T16 것) · `static/js/brain/ds/ds-agents*.js`(`ds-agents-evals` 는 T16 것) · `static/css/contexts/brain/ds/brain-ds-agents.css` · `tests/domains/test_ai_staff_levels.py` · `test_ai_staff_sweeps.py` · `test_ai_staff_api.py` · `test_brain_ds_agents.py` · `tests/security/test_ai_staff_access.py` |
| T14 | `foms/api/quest.py` · `foms/api/drawing/erp_orders_draftsman.py` · `foms/api/orders/field_update.py` · `foms/api/orders/__init__.py`(껍데기 줄만) · `foms/api/erp_action_runners.py` · `foms/services/erp_actions/registry.py` · `preview.py` · `tests/domains/test_erp_actions_core_runners.py` · `test_erp_actions_registry.py`(`mode` 기대값). **특성 시험 파일(T13 것)은 고치지 않는다** — 고쳐야 통과한다면 그것이 행동이 달라졌다는 뜻이다 |

### 물결 D

| 일감 | 가진 파일 |
|---|---|
| T9 | `foms/services/cs_agent/graft_step.py`(새) · `graft_settings.py`(새) · 고침: `drafting.py`(부르는 줄만) · `settings.py`(등록 줄만) · `send_view.py` · `wam_functions.py` · `send_flow.py`(꼭 필요할 때만) · `foms/api/channel/channel_functions.py`(필요할 때만) · `foms/web/cs_draft_wam.py` · `templates/cs/cs_agent_wam.html` · `static/js/cs-agent/wam-graft.js`(새) · `wam-draft.js` · `static/css/contexts/cs/cs-wam.css` · `tests/domains/test_cs_graft_step.py` · `test_cs_wam_graft.py` · 지금 작은 창 시험 가운데 닿는 것 |
| T15 | `foms/services/kakao_alimtalk_construction.py`(새) · `foms/services/kakao_alimtalk.py`(같이 쓸 부품을 밖에서 부를 수 있게 이름을 내놓는 줄만 — 지금 함수의 행동은 그대로) · `foms/services/notifications/erp_action_push.py`(새) · `push_sender.py`(새 종류 갈래만) · `static/sw.js` · `static/js/foms/mobile-push.js`(누르면 여는 주소가 `/brain` 을 막을 때만) · `foms/services/erp_actions/notify.py`(새) · `lifecycle.py`(부르는 줄) · `runners.py` · `registry.py` · `preview.py` · `foms/services/ai_staff/registry.py`(운영 AI 의 새 할 일 한 줄) · `sweeps.py`(`O4`) · `foms/services/graft_flags.py`(이름 둘) · `tests/domains/test_construction_alimtalk.py` · `test_erp_action_push.py` · `test_erp_actions_notify.py` · 닿는 지금 시험(`test_graft_flags.py` · `test_erp_actions_registry.py` · `test_erp_actions_runners.py` · `test_ai_staff_registry.py` · `test_ai_staff_sweeps.py`) |
| T16 | `foms/services/ai_staff/evals.py`(새) · `evals_run.py`(새) · `foms/services/cs_agent/brain_spend.py`(평가 쓰임 열쇠 — 꼭 필요할 때만) · `foms/services/jobs/tasks.py`(일 하나) · `foms/api/ai_staff.py` · `docs/harness/foms_order_mutation_policy_manifest.json` · `templates/brain/ds/partials/agents_evals.html` · `static/js/brain/ds/ds-agents-evals.js` · `static/css/contexts/brain/ds/brain-ds-agents-evals.css` · `tests/domains/test_ai_staff_evals.py` · `test_ai_staff_evals_api.py` · `tests/security/test_ai_staff_evals_access.py` |

### 아무도 고치지 않는 것 (고쳐야 하면 BLOCKED 로 보고)

`tests/harness/file_size_baseline.json` · `tests/contracts/runtime/layer_dependency_baseline.json` · `INLINE_STYLE_RATCHET` 값 · `static/css/foundation/foms-tablet-bundle.css` 와 그 핀 · 옛 회사 지식 화면 파일(`templates/brain/*.html` · `templates/brain/partials/*` · `static/js/brain/*.js` · `static/css/contexts/brain/brain.css`) · `CLAUDE.md` · `AGENTS.md` · `docs/AI_STATUS.md`(메인이 끝에 고친다).

## 4. 워크트리 · 합치기 (메인이 한다)

1. **화면 일꾼(T2 · T3 · T4 · T5 · T8)과 시험만 만드는 T13 은 `c:\tmp\foms-s-foms-graft` 를 같이 쓴다**(파일이 겹치지 않는다). 같은 자리에서 여러 일꾼이 시험을 돌리므로 일꾼은 `-n`(여러 일손) 없이 자기 시험 파일만 돈다. 남이 편집하는 중이라 `APP_OK` 가 잠깐 깨질 수 있다 — 오류 글의 파일이 내 것이 아니면 1분 뒤 다시 돌린다.
2. **파이썬을 많이 고치는 일꾼(T6 · T7 · T9 · T10 · T14 · T15 · T16)은 따로 워크트리**. 까닭: 만들다 만 블루프린트 · import 가 남의 `APP_OK` 확인을 깨뜨린다.
   - 만들기(메인): `cd /c/DEV/FOMS && python tools/harness/session_worktree.py create --name graft-read`(→ `c:\tmp\foms-s-graft-read`, 가지 `session/graft-read`). 이 도구는 `origin/deploy` 에서 가지를 딴다 — 앞 물결 커밋이 없다. 만든 직후(자기 커밋이 없을 때) `cd /c/tmp/foms-s-graft-read && git reset --hard session/foms-graft` 로 바탕을 맞춘다.
   - 이름: T6 `graft-read` · T7 `graft-actions` · T10 `graft-staff` · T14 `graft-core` · T9 `graft-cs` · T15 `graft-notify` · T16 `graft-eval`.
   - 워크트리에는 메인 트리의 커밋 안 한 파일이 없다. 앞 물결의 결과는 띄우기 전에 `session/foms-graft` 에 커밋돼 있어야 한다.
   - 워크트리에서는 alembic · 개발 서버 시작 DDL 이 막혀 있다. 마이그레이션은 파일과 시험으로만 확인한다.
3. **일감 하나를 닫는 차례(메인)**: 일꾼 보고서 → `git status --short` 로 가진 파일 밖을 건드렸나 → 완료 명령을 메인이 다시 돈다 → 판과 화면 그림을 본다(화면 일감) → 경로를 적어 커밋(`git commit -F <글 파일> -- <경로…>` — 한글 글은 UTF-8 파일로) → 따로 워크트리였으면 `cd /c/tmp/foms-s-foms-graft && git cherry-pick <커밋…>` → 원장 상태 `DONE` + 커밋 번호.
4. **물결 사이**: 다음 물결 일꾼을 띄우기 전에 `session/foms-graft` 에서 `python -c "import app; print('APP_OK')"` 와 그 물결까지의 새 시험을 한 번 돈다.
5. **T13 → T14 사이(코어 변경 문지기)**: T13 을 커밋하기 전에 메인이 특성 시험 셋을 **고치지 않은 제품 코드에서** 다시 돌려 초록인지 보고 그 출력을 원장 7절 아래에 붙인다. 그 커밋 번호를 T14 지시문의 '바탕 커밋' 자리에 넣어 띄운다.
6. **`deploy` 푸시 · 운영 반영은 이 계획의 일이 아니다.** 사용자가 말하면: `git fetch` 뒤 `origin/deploy` 위로 다시 올리기 → T12 다시 → `scripts/ops/pre_push_smoke.ps1` 이 0 으로 끝난 뒤에만 `git push origin HEAD:deploy`(`smoke && push` 로 묶는다) → CI 초록 → 스테이징에서 스위치를 QA 계정에만. 운영은 사용자가 따로 말할 때만 이 세션 커밋만 골라 PR.

## 5. 여러 일감이 차례로 갖는 자리 — 물결마다 주인 하나

| 자리 | 주인(물결 순) |
|---|---|
| 루트 `models.py` 끝 import 한 줄 | T1 |
| 마이그레이션(하나뿐 — `graft_00`, `down_revision = 'prodpart_00'`) | T1. 합칠 때 `origin/deploy` 에 새 마이그레이션이 생겼으면 메인이 `down_revision` 을 새 머리로 고치고 T1 시험을 다시 돈다(머리는 하나). 판 2 에서 늘어난 일감은 표를 더하지 않는다 |
| `foms/services/erp_actions/registry.py` | T1(A) → T14(C — `mode` 셋을 `run` 으로 · `user_ids` 값) → T15(D — `send_construction_alimtalk` · `notify_customer`) |
| `foms/services/erp_actions/preview.py` | T7(B) → T14(C) → T15(D) |
| `foms/services/erp_actions/runners.py` · `lifecycle.py` | T7(B) → T15(D) |
| `foms/api/erp_action_runners.py` | T7(B) → T14(C) |
| `foms/services/ai_staff/registry.py` | T1(A) → T10(C, 한 줄) → T15(D) |
| `foms/services/ai_staff/sweeps.py` | T10(C) → T15(D) |
| `foms/api/ai_staff.py` | T10(C) → T16(D) |
| `foms/platform/blueprints.py` 등록 | T7(B) → T10(C) |
| 길 목록 JSON(`guard_count` 포함) | T7(B) → T10(C) → T16(D) |
| `foms/services/graft_flags.py` | T2(A) → T15(D) |
| `foms/web/brain.py` | T2(A) → T8(C) |
| `foms/api/brain.py` · `foms/api/brain_chat.py` | T6 |
| `layout_head.html` · `layout_scripts.html` · `layout_nav.html` · 레일 둘 | T8 |
| `tools/cron/nightly.py` | T10 |
| `foms/services/cs_agent/settings.py` · `drafting.py` | T9 |
| 채널톡 작은 창 파일 핀(`cs_agent_wam.html` 의 `?v=`) | T9 — 올린 뒤 `grep -rn "<옛 핀>" tests templates` 로 베낀 곳을 같이 |

## 6. 일감마다 끝난 기준 (명령 그대로 — 모두 0 으로 끝나야 한다)

공통(모든 일감): `cd <워크트리> && python -c "import app; print('APP_OK')"` · 새 · 고친 `.js` 마다 `node --check <파일>` · `python -m pytest tests/harness/test_file_size_ratchet.py tests/contracts/runtime/test_layer_dependency_ratchet.py "tests/harness/test_harness_drift_guard.py::test_inline_style_ratchet" -q` · 바꾼 파일 이름으로 `grep -rl <이름> tests` 해서 나온 시험 파일.

| 일감 | 더 도는 명령 |
|---|---|
| T1 | `python -m pytest tests/domains/test_graft_store.py tests/domains/test_erp_ontology_read.py tests/domains/test_erp_actions_registry.py tests/domains/test_ai_staff_registry.py tests/domains/test_brain_usage_events.py tests/domains/test_alembic_single_head.py tests/domains/test_brain_store.py tests/domains/test_production_part_marks_model.py -q` |
| T2 | `python -m pytest tests/domains/test_graft_flags.py tests/domains/test_brain_ds_scope.py tests/domains/test_brain_ds_shell.py tests/security/test_brain_ds_access.py tests/security/test_brain_screens_access.py tests/security/test_brain_fix_menu_nav.py tests/domains/test_brain_fix_menu_query_count.py tests/domains/test_brain_screens_assets.py tests/performance/test_perf_regression_guard.py -q` + 화면 대조(틀 — ⑥ 의 위 줄 · 왼쪽 · 가운데 · 오른쪽 자리, ⑫ 의 아래 탭) |
| T3 | `python -m pytest tests/domains/test_brain_ds_inbox.py tests/domains/test_brain_ds_inbox_js.py tests/domains/test_brain_review_js.py tests/domains/test_brain_fix_inbox_js.py tests/domains/test_brain_inbox_boot_js.py tests/domains/test_brain_review.py tests/domains/test_brain_inbox_bins.py tests/security/test_brain_review_access.py -q` + 화면 대조 ⑥(지식 고침 칸) · ⑫ |
| T6 | `python -m pytest tests/domains/test_graft_ask_erp.py tests/domains/test_graft_onto_erp.py tests/domains/test_graft_usage_view.py tests/security/test_graft_read_access.py tests/domains/test_brain_chat.py tests/domains/test_brain_chat_audit.py tests/domains/test_brain_ontology_view.py tests/domains/test_brain_ontology_cq_props.py tests/domains/test_brain_d105.py tests/security/test_brain_chat_access.py -q` |
| T7 | `python -m pytest tests/domains/test_erp_actions_lifecycle.py tests/domains/test_erp_actions_runners.py tests/domains/test_erp_actions_api.py tests/domains/test_construction_note.py tests/security/test_erp_actions_access.py tests/domains/test_auth_enforcement.py -q` + `tests/postgres/test_erp_actions_pg.py`(로컬 PostgreSQL 레인이 있으면 돌리고, 없으면 "CI 에서 확인"이라고 보고) |
| T13 | `python -m pytest tests/domains/test_graft_char_quest_approve.py tests/domains/test_graft_char_assign_draftsman.py tests/domains/test_graft_char_measurement_date.py -q` — **제품 코드를 고치지 않은 채** 초록. 보고서에 길마다 못박은 것의 표 + 대조군(일부러 빼면 빨개지는 것) 결과 |
| T4 | `python -m pytest tests/domains/test_brain_ds_search.py tests/domains/test_brain_ds_item.py tests/domains/test_brain_screens_js.py tests/domains/test_brain3d_js.py tests/domains/test_brain_around.py -q` + 화면 대조 ⑦ · ⑧ |
| T5 | `python -m pytest tests/domains/test_brain_ds_ask.py tests/domains/test_brain_ds_onto.py tests/domains/test_brain_chat_js.py tests/domains/test_brain_ontology_view.py -q` + 화면 대조 ⑨ · ⑩ |
| T8 | `python -m pytest tests/domains/test_graft_cells.py tests/domains/test_brain_ds_inbox_erp.py tests/domains/test_tablet_dashboard_sheet_contract.py tests/domains/test_tablet_rail_contract.py tests/domains/test_tablet_t2_contract.py tests/domains/test_nav_badge_lazy_count.py tests/domains/test_brain_fix_menu_query_count.py tests/domains/test_layout_header_mobile_overlap.py tests/visual/test_p1_mockup_structure.py tests/performance/test_perf_regression_guard.py tests/security/test_brain_ds_access.py -q` + 화면 대조 ⑥(AI 할 일 제안 칸 · 옆 창) · ⑫ · ② ③ ④(분홍 칸 자리와 글) + 색 차 재기 결과 |
| T10 | `python -m pytest tests/domains/test_ai_staff_levels.py tests/domains/test_ai_staff_sweeps.py tests/domains/test_ai_staff_api.py tests/domains/test_brain_ds_agents.py tests/security/test_ai_staff_access.py tests/domains/test_nightly_cron_runner.py tests/contracts/runtime/test_cron_purge_wiring.py tests/domains/test_auth_enforcement.py -q` + 화면 대조 ⑪('AI 시험' 칸 빼고) |
| T14 | ① `python -m pytest tests/domains/test_graft_char_quest_approve.py tests/domains/test_graft_char_assign_draftsman.py tests/domains/test_graft_char_measurement_date.py -q`(시험 파일이 T13 커밋과 한 글자도 다르지 않은 채) ② `python -m pytest tests/domains/test_erp_actions_core_runners.py tests/domains/test_erp_actions_registry.py tests/domains/test_erp_actions_lifecycle.py tests/domains/test_erp_actions_api.py tests/domains/test_auth_enforcement.py -q` ③ `python -m pytest $(grep -rl -e "quest/approve" -e "assign-draftsman" -e "update_order_field" tests --include="*.py") -q`(그 길에 닿는 지금 시험 전부 — 60개 안팎) ④ `git diff <T13 커밋> -- tests/domains/test_graft_char_*.py tests/support/graft_char.py` 가 비어 있음 |
| T9 | `python -m pytest tests/domains/test_cs_graft_step.py tests/domains/test_cs_wam_graft.py tests/domains/test_cs_wam_draft.py tests/domains/test_cs_wam_send.py tests/domains/test_cs_handoff_send.py tests/domains/test_cs_order_lookup.py -q` + 화면 대조 ⑤ |
| T15 | `python -m pytest tests/domains/test_construction_alimtalk.py tests/domains/test_erp_action_push.py tests/domains/test_erp_actions_notify.py tests/domains/test_graft_flags.py tests/domains/test_erp_actions_registry.py tests/domains/test_erp_actions_runners.py tests/domains/test_erp_actions_lifecycle.py tests/domains/test_ai_staff_registry.py tests/domains/test_ai_staff_sweeps.py tests/performance/test_perf_regression_guard.py -q` + `grep -rl -e "kakao_alimtalk" -e "push_sender" -e "mobile-push" -e "sw.js" tests` 로 나온 것 가운데 닿는 시험 |
| T16 | `python -m pytest tests/domains/test_ai_staff_evals.py tests/domains/test_ai_staff_evals_api.py tests/security/test_ai_staff_evals_access.py tests/security/test_ai_staff_access.py tests/domains/test_ai_staff_api.py tests/domains/test_brain_ds_agents.py tests/domains/test_auth_enforcement.py -q` + `node --check static/js/brain/ds/ds-agents-evals.js` + 화면 대조 ⑪ 의 'AI 시험' 칸 |
| T11 | 검수 보고서(결함마다 `경로:줄` · 심각도 · 고칠 말). 메인이 받는 즉시 이 원장 7절에 옮긴다 |
| T12 | 지시문의 확인 명령 전부 + 스위치 끔 견주기 + 핀 · 머리 · 소유 표 대조. 전체 시험은 돌리지 않는다(푸시 직전 smoke 한 번이 맡는다) |

### 화면 대조 (판과 실제 화면을 나란히 읽기)

1. 판 그림은 1절의 `shots` 폴더에 있다(없으면 `shoot3.py` 로 다시 찍는다).
2. 화면 그림은 `screen_shot.py`(T2 가 만든다)로 찍는다: 시험용 앱(메모리 SQLite + 지어낸 자료) 안에서 그 주소를 그려 HTML 로 떨군 뒤, 서비스 워커를 막은 Playwright 로 1440×1000 과 390×844 를 찍는다. 운영 · 스테이징 · 실제 자료를 쓰지 않는다. 지어낸 자료에 실제 이름 · 전화 · 주소를 넣지 않는다.
3. 일꾼은 두 그림을 읽고 다른 곳을 적는다 — 자리(위 줄 · 왼쪽 · 가운데 · 오른쪽) · 순서 · 글 · 색 갈래 · 빠진 칸 · 더 생긴 칸. 자료가 달라서 생긴 차이(수 · 이름)는 빼고 적는다.
4. 문지기는 구조 시험이다. 그림 대조는 보고서 거리이고, 메인이 닫을 때 한 번 더 본다.
5. 지금 화면의 분홍 칸(② ③ ④ ⑤)은 지금 화면 조각을 시험용 앱에서 그려 "그 칸이 그 자리에 그 글로 있나"만 본다. 목업의 `foms-now.css` 흉내와 지금 화면이 다른 것은 차이가 아니다.
6. **목업에 있어도 그리지 않는 것**(설계서 9절 · D211): 시공 팀 번호 · 인원 수 · '폭 합 ÷ 300' 줄, `L-` · `H-` 주문 번호 머리, '출고 대기' 단계. 이것이 화면에 없는 것은 차이가 아니고, 있으면 결함이다.

## 7. 검수 결함 원장 (T11 뒤 메인이 채운다)

| 번호 | 심각도 | 어디 | 무엇 | 맡은 일감 | 상태 |
|---|---|---|---|---|---|
| F-01 | 높음(지금 운영) | `foms/services/orders/order_mutation_policy.py:407-413` · `foms/services/erp_permissions.py:368-382` | CS · 영업 팀 VIEWER(조회 전용) 계정이 시공일 쓰기 길 셋(`foms_order_mutation_policy_manifest.json:803-816`)을 통과 — 정책 문지기 함수가 VIEWER 막기보다 먼저 돌고 `can_edit_erp` 가 VIEWER 를 거르지 않음. 접목판 할 일은 `access.policy_allows` 가 따로 막음(W7) | 접목판 밖 — 사용자에게 보고 · 따로 고침 | 고침(`ae8c862dc` — 이 가지 · 운영 PR #855 에 들어감. 처음 고친 가지는 `session/viewer-schedule-guard` `be3c7e31c`) |
| F-02 | 낮음 | `foms/services/erp_actions/views.py:236` | 자세히 답 `params` 에 `required` 가 없다(registry `Param.required` 는 있음) — 화면(T8)이 `time_slot` · `flag` 말고는 꼭 넣을 값으로 미루어 판단 | T11 검수 뒤 정함(T7 답에 더하기 권함) | 고침(`9ca118614` — 자세히 답에 required) |
| F-03 | 낮음 | `foms/services/erp_actions/views.py:134` | 카드 답에 `base_version` 이 없다(설계서 3.6 카드 칸 목록과 같음) — 카드 [승인]은 자세히를 먼저 읽고 승인(요청 둘) | T11 검수 뒤 정함 | OPEN |
| F-04 | 낮음(색) | `static/css/components/foms-graft-cells.css` | AI 칩 글 · 테두리 #4a55b8 과 고객컨펌 단계 배지 #5a67d8 의 ΔE2000 7.5(제2색맹 흉내 뒤 7.3) — 바탕끼리는 42 이상, 옅은 칩과 꽉 찬 배지로 갈린다. 상태 쌍 기준(10)에는 미달 · 색약 기준(6)은 넘음 | T11 검수 뒤 정함(판의 남보라 유지가 기본) | OPEN |
| F-05 | 기록 | `templates/partials/shared/erp_mobile_queue_card_v2.html` | 파일 주인 표(3절) 밖 — 폰 목록 줄 칩(메모리 규칙 '새 기능은 폰 목록 줄에서 보여야')으로 T8 이 더함. 이 카드를 쓰는 6개 목록 모두에 칩이 나온다. 꺼지면 지금과 같음(시험) | — | 기록만 |
| F-06 | 결정 필요 | `foms/services/ai_staff/evals.py`(T16) · 마이그레이션 `csagent_03` | 상담 차례 `held_out` 을 참으로 쓰는 코드가 없다(떼어 두는 기능 C12-1 이 안 만들어짐) — 운영에서도 '지난 상담' 묶음이 0 · 화면 '묶음 0' | 사용자 결정 뒤 따로 | 고침(`58219b01c` — D219, 새 상담 10% 떼어 둠 · 평가는 고침 · 직접 답만) |
| F-07 | 중간 | `foms/services/erp_actions/registry.py`(T14) | 보는 사람 ≠ 실행할 수 있는 사람(설계서 3.5 와 어긋남): 도면 담당 맡기기는 정책 `STAFF_MUTATION` 이라 모든 직원이 보지만 본체는 관리자 · 도면팀 · 지정 담당만 실행(나머지 409) · 실측 옮기기는 정책이 모든 매니저를 통과시키지만 본체가 팀을 봄(다른 팀 매니저 409) | T11 검수 뒤 정함 | 결정 D217 — 지금처럼(기록만) |
| F-08 | 낮음 | `foms/services/ai_staff/sweeps.py`(T10 규칙 O2) | 넣을 값이 비어 겹침 열쇠가 주문마다 하나 — 한 번 거절되면 그 주문엔 다시 제안되지 않음 | T11 검수 뒤 정함 | 고침(`aa2b37f66` — O1 · O2 · O4 열쇠에 상황, O3 은 거절 존중) |
| F-09 | 고침 | `tests/support/graft_char.py` | 큰 묶음(-n 6, 하네스 · 보안 시험과 섞임)에서 특성 시험 정책 가드 403 셋이 감사 줄 빠짐으로 빨강 — 거부 감사 60초 겹침 거르기가 프로세스 안 캐시라 같은 일손의 앞선 거부(같은 번호 사용자 · 끝점)에 눌림. 한 번은 `erp_stage_updated_at` 안 바뀜(Windows 시계 눈금). 자국 뜨기 전 캐시 비우기 + 눈금 넘기기로 고침, 같은 묶음 두 번 초록. 함께 본 `test_db_leak_trace::test_closed_session_is_silent` 흔들림은 엔진 `id()` 재사용(접목판 밖 · 원래 있던 것) | 메인 | 고침(`f76d06476`) |
| F-10 | 기록 | 설계서 · 지시문 | 코드와 다른 문장: 설계서 :63 `Idempotency-Key` 머리글 빠짐 · :310 '2xx 아니면 막힘'(코드는 5xx = 실패) · :311 '승인하는 사람의 팀'(실행기는 재전이 길만) · :300 · :339 `run_eval` · 줄 일 자리(실제 `evals_run.py` — `tasks.py` 는 층 래칫 · WORKER 가벼움 시험 때문에 못 씀) · :337 `check_codes`(말투 알림도 적힘) · 지시문 :446 `checks_same.py`(같은 뜻 판정은 `case_memory.judge_reply`) · 목업 'BOnto' 도면 담당 폰 승인(실제 PC 승인) · 'BAgents' '기준 밑이면 배포를 막아요'(없는 문지기) | 마무리 때 문서 고침 | 기록만 |
| F-11 | 할 일 | `docs/harness/foms_*_inventory.json` | T14 로 줄 번호만 밀린 인벤토리(audit_coverage · failopen) — push 전 `*_scan.py` 를 직접 돌려 커밋(refresh 는 줄 번호만 바뀐 것을 되돌린다) | 메인(push 전) | 고침(`b4368b0aa`) |
| F-12 | 결정 필요 | `foms/services/cs_agent/order_find.py:39`(T9 규칙 ①) | 본인 확인이 완료 주문(열린 AS 없음)을 빼서 'AS 뜻 + 완료 · CS 단계 → AS 접수 제안'이 사실상 CS 단계에서만 듦 — 고치려면 상담 주문 찾기 규칙을 바꿔야 함(접목판 밖 파일) | 사용자 결정 뒤 | 고침(D220 — 끝난 지 1년 안 완료 주문도 찾음. 뒤에 D225 로 기간 없이 전체. 남음: AS 완료 단계 · '불만' 넘김이면 규칙 ① 안 듦) |
| F-13 | 낮음 | `foms/services/cs_agent/send_view.py`(T9) · `lifecycle.approve`(T7) | 기간이 지났지만 아직 `expired` 로 안 바뀐 제안이 작은 창 줄에 보일 수 있고, 승인도 `expires_at` 을 보지 않음 | T11 검수 뒤 정함 | 고침(`cccc60eb7` — 승인이 expires_at 을 본다. 읽는 길 · 작은 창 줄은 점검 2차 w6-12 · w5-02 로 마저 고침) |
| F-14 | 켜는 순서 | 설계서 4절 | 상담 AI 관리 칸(할 일 제안)은 켜고 `FOMS_GRAFT_ACTIONS` 는 끈 채면 AS 접수 · 방문 옮기기 제안이 생겨도 아무도 못 보고 7일 뒤 끝남 · 폰 알림은 FOMS-cron · WORKER 에 `REDIS_URL` · `FOMS_WEB_PUSH_ENABLED` · VAPID 열쇠가 없으면 알림 줄만 생기고 폰으로 안 나감 · 폰 알림 받는 사람 판정이 `FOMS_GRAFT_ACTIONS` · `FOMS_GRAFT_BRAIN_UI`(+`_COHORT`)를 제안을 만드는 FOMS-cron · WORKER 에서도 읽으므로 두 서비스에도 같은 값을 넣는다 · `FOMS_PUSH_P1_TYPES` 를 덮어쓴 서비스면 `ERP_ACTION_PROPOSAL` 을 더한다(검수 R-11) | 켜는 날 확인 목록 | 기록만 |
| F-15 | 기록(접목판 밖) | `static/sw.js:429` | 폰 알림 누름 허용 목록이 `/erp/` · `/partner/` 뿐이라 지금 공지(`/notices`) · 상담 초안(`/cs-agent/…`) 폰 알림도 누르면 대시보드로 감 — 이번엔 `/brain` 만 넓힘 | 따로 | 기록만 |
| F-16 | 기록 | `foms/services/erp_actions/registry.py`(T15) | 폰 알림 팀(`notify_team`)은 설계서에 없어 일꾼이 정함: 시공 잡기 · 방문 옮기기(시공) SHIPMENT · 방문 옮기기(AS) · AS 접수 · 시공 메모 · 단계 넘기기 · 시공일 안내 CS · 실측 예약 알림톡 · 방문 옮기기(실측) SALES · 도면 담당 DRAWING | 사용자 확인 | 고침(`e261f4222` — D221. 방문 옮기기(AS)는 D223 으로 영업 + CS) |
| R-01 | 보통 | `erp_actions/lifecycle.py:300` · `web/orders/dashboard.py:658` · `static/js/foms/graft-cells.js:182` | 사유가 필요한 시공일 변경을 사유 없이 실행 — 서버 승인이 `reason_required` 를 안 보고 태블릿 [승인]은 사유 없이 보냄 (검수 R1) | 고침 A | 고침(`6e01dc5a0`) |
| R-02 | 보통 | `ds-inbox-erp.js:179` · `graft-cells.js:182` · `erp_actions/runners.py:187` | 카드 · 폰 · 태블릿 빠른 [승인]이 손님 알림톡(처음 켬)까지 보내는데 그 줄을 본 적이 없음 (검수 R1) | 고침 A | 고침(`6e01dc5a0`) |
| R-03 | 보통 | `cs_agent/graft_step.py:307` | 넘김 까닭 '불만'이면 손님 글 전부(본인 확인 답 포함)를 시공 메모 제안에 실음 — 이름이 남을 수 있음 (검수 R1) | 고침 C | 고침(`63f12b0ef`) |
| R-04 | 보통 | `ai_staff/sweeps.py:151` | O1 이 실패 · 건너뜀 · 옛 날짜 알림톡 기록도 '보냄'으로 침 (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-05 | 보통 | `ai_staff/sweeps.py:119` | 후보 `order_by(id).limit(200)` — 오래된 200개 · 제안 걸린 주문이 자리를 차지해 새 주문에 못 닿음 (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-06 | 보통 | `ai_staff/sweeps.py:223` | 후보 하나의 예외가 그 밤 제안 전부를 되돌림 (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-07 | 보통 → 받아들임 | `templates/brain/ds/layout.html:27` | socket.io CDN — 전역 `layout_head.html:651` · 실측 지도 · 도면 마법사와 같은 SRI 고정 주소 · 같은 defer(새 라이브러리 아님, 브라우저 캐시 공유) (검수 R1) | 기록만 | 받아들임 |
| R-08 | 보통 | `brain-ds-inbox-erp.css:27` | 폰 ERP [승인] `min-height: 36px` 가 44px 를 이김 (검수 R1) | 고침 A | 고침(`6e01dc5a0`) |
| R-09 | 낮음 | `lifecycle.py:188` · `views.py:211` · `ai_staff/metrics.py:49` · `runs.py:199` | 새 표 질의 색인 못 탐(`_taken` 등) (검수 R1) | 고침 A(`_taken` 에 order_id) | 고침(`6e01dc5a0`) |
| R-10 | 낮음 | `lifecycle.py:304` · `ai_staff/levels.py:120` | 수준 0 으로 내려도 열린 제안이 승인 · 실행됨 (검수 R1) | 고침 A(승인 때 수준 다시 봄) | 고침(`6e01dc5a0`) |
| R-11 | 낮음 | `erp_actions/notify.py:61` · `push_sender.py:199` | 폰 알림 받는 사람 판정이 `FOMS_GRAFT_ACTIONS` · `BRAIN_UI` 를 cron · WORKER 에서 읽음 · `FOMS_PUSH_P1_TYPES` 덮어쓰기면 새 종류 빠짐 (검수 R1) | F-14 켜는 날 목록에 더함 | 고침(F-14 에 적음) |
| R-12 | 낮음(확신 낮음) | `kakao_alimtalk_construction.py:229` · `lifecycle.py:56` | 같은 시공일 두 통 경합(잠금 없이 '이미 보냄' 판정) (검수 R1) | 고침 A | 고침(`6e01dc5a0`) |
| R-13 | 낮음 | `tests/contracts/runtime/layer_dependency_baseline.json:179,193` | T7 · T10 이 층 기준선에 블루프린트 등록 두 줄을 더함 — V1 아홉째 명령이 내보냄 (검수 R1) | 기록(예외) · V1 기대값 맞춤 | 기록(예외 — 블루프린트 등록 두 줄) |
| R-14 | 낮음 | 지시문 V1 열한째 명령 | D211 글 찾기가 접목판 밖 옛 글에 늘 걸림 (검수 R1) | V1 에 더한 줄만 찾게 알림 | V1 에 알림 |
| R-15 | 낮음(기록) | `runners.py:141` · `api/erp_action_runners.py:146` | 설계서 3.4 `source=erp_action:<번호>` 는 services 실행기 감사 줄에만 — D206 본체 셋은 못 실음 (검수 R1) | 설계서 고침 | 고침(설계서 3.4) |
| R-16 | 낮음(기록) | 주인 표 밖 | `api/notifications/__init__.py` · `audit_message_display.py` · `order_mutation_writer_allowlist.json` · 네임스페이스 표면 시험 · `test_as_timeline_contract.py:289` · 새 파일 `construction_notice.py` · `evals_view.py` · (V1) `tests/domains/test_brain_screens_assets.py`(새 틀 소켓 CDN 예외 한 줄 — R-07) · `tests/domains/test_cs_settings.py`(관리 칸 둘 처음 값) (검수 R1) | 기록만 | 기록만 |
| R-17 | 낮음 | `static/js/brain/ds/ds-shell.js:110` | 화면 크기를 맨 끝 defer 에서 붙여 80% 배율 사람이 깜빡임 (검수 R1) | 메인 고침 | 고침(틀 스크립트를 head 앞쪽 defer 로) |
| R-18 | 낮음 | `ds-agents-kit.js:130` | '최근 실패'에 `error_code` 기계 말 (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-19 | 낮음 | `templates/brain/ds/layout.html:17` | `foms-ui-zoom.css?v=` 손 핀 베낌 (검수 R1) | 메인 고침(asset_url) | 고침(asset_url) |
| R-20 | 낮음 | `brain/partials/card_neighbours.html:33` · `tab_map.html:48` · `notice_popup.html:15` | 새 화면에 Font Awesome 없어 실은 조각 아이콘이 빈칸(글은 보임) (검수 R1) | 메인 고침 | 받아들임(옛 화면과 같이 쓰는 조각 — 글은 보임) |
| R-21 | 낮음(확신 낮음) | `graft-cells.js:99` | `paintSlot` 이 칸 켬을 다시 안 봄 (검수 R1) | 고침 A | 고침(`6e01dc5a0`) |
| R-22 | 낮음 | `ds-inbox-erp-card.js:46,88` | 서버 `href` 꼴 확인 없이 링크 (검수 R1) | 고침 A | 고침(`6e01dc5a0`) |
| R-23 | 낮음(결정) | `foms-ds.css:20` | 바탕 글자 14px(80% 배율이면 11.2px) (검수 R1) | 사용자 확인 | 고침(`b73e5df24` — D216 16px) |
| R-24 | 낮음(확신 낮음) | `foms-graft-cells.css:42` | 폰 목록 카드 AI 칩 22px — 누르기 작음 (검수 R1) | 고침 A | 고침(`6e01dc5a0`) |
| R-25 | 낮음 | `ai_staff/evals.py:408` · `evals_run.py:242` | '멈춘 채 끝남'으로 풀린 평가가 살아 있으면 계속 돈 쓰고 상태 덮어씀 (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-26 | 낮음 | `cs_agent/wam_functions.py:222` | 관리 칸 꺼져도 `with_action` 오면 답에 `action` 칸 (검수 R1) | 고침 C | 고침(`63f12b0ef`) |
| R-27 | 낮음 | `web/cs_draft_wam.py:35` | 작은 창 틀이 설정 읽기 실패면 500 (검수 R1) | 고침 C | 고침(`63f12b0ef`) |
| R-28 | 낮음 | `graft_step.py:176` · `send_view.py:180` | 줄 제안 생긴 차례를 건너뛰면 다음 차례 창에 줄 없음 (검수 R1) | 고침 C | 고침(`63f12b0ef`) |
| R-29 | 낮음 | `graft_step.py:133` | 같은 차례 다시 쓰면 근거 줄 부풀음 (검수 R1) | 고침 C | 고침(`63f12b0ef`) |
| R-30 | 낮음(확신 낮음) | `graft_step.py:254` | 60일 넘게 지난 날짜를 내년으로 읽음 (검수 R1) | 고침 C | 고침(`63f12b0ef`) |
| R-31 | 낮음 | `api/ai_staff.py:155` | 큐 넣기 실패 뒤 `update_run` · 커밋이 try 밖 (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-32 | 낮음(확신 낮음) | `test_cs_graft_step.py` · `test_cs_wam_graft.py` | `FOMS_GRAFT_*` env 를 안 지움 (검수 R1) | 고침 C | 고침(`63f12b0ef`) |
| R-33 | 낮음(성능) | `graft_step.py:135,189` | `doc_keys` 두 번 (검수 R1) | 고침 C | 고침(`63f12b0ef`) |
| R-34 | 낮음 | `ai_staff/sweeps.py:189` | O4 가 같은 날 실패 기록도 '보냄' (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-35 | 낮음 | `ai_staff/views.py:123` | 자세히 한 번에 질의 스물 안팎 (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-36 | 낮음 | `ai_staff/runs.py:209` · `metrics.py:78` | `cs_agent_turns` 를 `created_at` 만으로 거름 (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-37 | 낮음 | `erp_ontology/read.py:197` | `stage_since` 가 UTC 날짜 (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-38 | 낮음(확신 보통) | `erp_ontology/ask.py:202,249` | 날짜 확인이 날짜 뒤 요일만 봄 (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-39 | 낮음 | `brain/usage_view.py:64` | 제안 볼 수 있나 판정이 따로 · 줄마다 `session.get` (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-40 | 낮음(확신 낮음) | `brain/usage_view.py:180` | `by_reader.erp_action` 에 볼 수 없는 제안 쓰임도 셈 (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-41 | 낮음 | `brain/chat_prompt.py:33` | 까닭 없는 `FIELDS =(` 바뀜 (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-42 | 낮음 | `test_graft_ask_erp.py` | '켬 + 읽은 주문 + 지식 후보 0' 시험 없음 (검수 R1) | 고침 B | 고침(`28a2e131a`) |
| R-43 | 낮음(기록) | `erp_ontology/objects.py:119` | 코드가 맞고 설계서 3.2 '바로가기'가 옛 글 (검수 R1) | 설계서 고침 | 고침(설계서 3.2) |
| F-07 · F-08 덧붙임 | — | `notify.py` · `sweeps.py:153,175,191` | R1: 폰 알림 받는 사람도 `can_run` 이라 실행 못 하는 사람도 받음(F-07) · 겹침 열쇠 뿌리가 O1 · O3 · O4 에도(F-08 — O1 은 처음 수준 1 이라 보통으로 올림) | F-08 고침 B | F-08 고침 · F-07 OPEN |
| F-17 | 낮음(기록) | `foms/services/cs_agent/graft_step.py`(고침 C 보고) | 본인 확인 근거가 `contact` 인데 손님이 묻기 전에 성함 · 휴대폰을 뜻 낱말 글과 같이 적은 경우, 원래 규칙대로 그 글이 시공 메모 제안에 실림 | 따로 | OPEN |
| F-18 | 기록 | `static/js/brain/ds/ds-inbox-erp.js`(고침 A) | R-02 판정은 지금 차례(`steps`)의 '손님 알림톡' 줄을 본다 — 실측 옮기기의 자동 실측 알림톡 줄(`FOMS_ALIMTALK_AUTO_ENABLED` 켬)도 카드 [승인]에서 옆 창을 연다(시킨 범위보다 조금 넓음) · 옆 창 표의 `changes` 는 제안 때 값이라 스위치를 끈 뒤 낡은 알림톡 줄이 남을 수 있음(원래 있던 것) | — | 기록만 |
| F-19 | 낮음(기록) | `foms/services/kakao_alimtalk.py` `_record_history`(고침 B 보고) | 사람이 누른 실측 알림톡(`manual` · `action` 열쇠)은 기록에 일정이 없어 O1 이 일정과 견주지 못함 — 자동 발송이 꺼진 채 사람이 보낸 뒤 날짜를 옮기면 놓침 | 따로 | OPEN |
| F-20 | 낮음(기록) | `foms/services/kakao_alimtalk_construction.py`(고침 A) | 시공일 안내 '이미 보냄' 판정은 이제 주문 줄 잠금 아래 — SQLite 는 잠금을 무시해 진짜 겹침 증명은 PG 레인 몫(시험 없음) · 잠금이 벤더 왕복(최대 5초) 동안 이어짐 · 보내기 성공 뒤 기록 전 서버가 죽으면 다시 보낼 수 있음 | 따로 | 기록만 |
| F-21 | 보통(사용자 지적 11-14) | `templates/partials/shared/foms_tablet_rail.html` · `static/css/components/foms-graft-cells.css` | 태블릿 레일에 '회사 지식' 칸이 늘면 1180×820 에서 알림 · 내 정보가 화면 아래로 밀림(잰 값 820 → 878px) — 칸이 보일 때만 레일 칸 여백을 줄여 820px 로 맞춤 | 메인 | 고침(`d7f5759df`) 1180×820 · 100% 한 크기만 맞춰 덜 고쳐짐 → 점검 2차 w4-02 로 다시 고침 |
| F-22 | 보통(사용자 지적 11-14) | `static/css/components/foms-graft-cells.css` | AI 칩(width: max-content · 한 줄)이 '현재 작업' 칸을 넓혀 태블릿 '단계' 배지가 '컨/펌'처럼 세로로 꺾이고, 막으면 '첨부' 칸이 밀림(표 748px / 상자 730px) — 단계 한 줄 · 칩 fit-content + 낱말 사이 줄바꿈(PC 칸 폭은 스위치 끈 화면과 같음). PC 표 머리 '경/보' 꺾임은 스위치를 꺼도 같은 원래 것 | 메인 | 고침(`40643d00e`) 태블릿은 덜 고쳐짐 → 점검 2차 w4-01 · w4-04 로 다시 고침 |

### 점검 2차 (11-15 — 목업 · 계획서 · 결정 대 실제 화면 · 코드, 고치기 전 목록)

일꾼 여섯(모두 Opus — w1 · w2 · w3 · w5 effort high, w4 · w6 xhigh)이 시험용 앱(메모리 SQLite · 지어낸 자료 · 진짜 CSS)에서 찍고 재서 찾았다. 스테이징 · 운영 화면은 열지 않았다. 고친 것은 없다. 번호는 일꾼 이름을 그대로 쓴다. 그림 · 잰 값 · 다시 재는 도구는 저장소 밖 스크래치패드 `audit2\<일꾼>\` 에 있다(설계서 절별 대조표는 `audit2\w6\spec_matrix.md`).

본 수 — w1 새 화면 틀 · 승인 대기 · 찾기 70(맞음 47) · w2 지식 카드 · 온톨로지 · 물어보기 84(60) · w3 AI 직원 · 폰 · 세로 태블릿 · 배율 336(약 287) · w4 PC · 태블릿 칸 판 대조 37(24) + 켬/끔 요소 비교 · 레일 94장 · w5 폰 · 작은 창 72(64) · w6 설계서 요구 74(63) · 결정 21(17).

메인이 그림 · 잰 표 · 코드를 직접 다시 본 것: w4-01 · w4-02 · w4-04 · w4-05 · w3-01 · w3-02 · w3-03 · w2-08 · w2-09 · w2-11 · w5-01 · w6-01 · w6-04. 나머지는 일꾼 확인 그대로다(고칠 때 다시 본다).

바로 한 일(운영): w6-01 → AI 직원 '운영 AI — 알림톡 보내기(실측 예약)' 수준 1 → 0(D230, 관리 화면 저장 API, 측정 계정 다시 잠금). w6-04 → 사용자 '그대로 두기'(D231).

#### PC · 태블릿 AI 칸 · 레일 (w4)

| 번호 | 판/화면 | 크기 | 갈래 | 무게 | 기대 | 실제 | 확인 |
|---|---|---|---|---|---|---|---|
| w4-04 (F-22 덜 고침) | NowTablet 작업 큐 '현재 작업' 칩 | 1180×820 · 1176×626 · 100~130% | 잘못 | 높음 | 새 칸이 원래 칸을 흔들지 않는다 | 칩의 글 덩어리가 칸 최소 폭이 돼 '현재 작업' +40px · 제품 −36px, 26줄 중 21줄 높이 바뀜, 칩 글 3~6줄. 110% 부터 표 상자가 넘친 칸을 잘라 '담당'(130% 는 실측일 · 시공일 · 담당 · 첨부)이 안 보임. `foms-graft-cells.css` · `tablet_workqueue_grid.html:68-70` | 켬 · 끔 같은 자료 rect(`w4\measure\diff_tab_*.csv`) · 메인 그림 재확인 |
| w4-05 | NowTablet 오른쪽 상세(작업 시트) | 1180×820 | 잘못 | 높음 | 판: AI 제안 상자가 있어도 아래 단추 줄이 보임 | 'AI 제안' 상자(125~149px)가 들어가면 아래 단추 줄(전화 · ERP 편집 · 단계로)이 y 700 → 853 으로 화면 밖. `tablet_dashboard_sheet.html:40` · `:81` | rect · 메인 그림 재확인 |
| w4-02 (원래 있던 것 · F-21 범위 밖) | 태블릿 레일(일곱 화면 같음) | 1176×626 · 1180×820 의 110~130% · 글자 130 · 150% | 잘못 | 높음 | 레일 마지막 칸 아래 끝 ≤ 화면 아래 | 1180×820 · 100% 하나만 맞음. 1176×626 은 끈 화면도 내 정보 791px(화면 626), 켜면 797 · '회사 지식' 699. 고침 `c72d7e320` 은 한 크기만 맞춤. `foms-tablet-rail.css:37` | 94장 잼(`w4\measure\rail_table.csv`) · 메인 표 재확인 |
| w4-01 (F-22 덜 고침) | NowTablet 작업 큐 표 | 1180×820 · 1176×626 | 잘못 | 보통 | 단계 한 줄은 스위치와 상관없이 | '단계 한 줄' 규칙이 접목판 꾸밈 파일 안에만 — 스위치를 끄면 이름 3자 · 100% 에서도 '컨/펌' 세로. 켬에서는 제안 0 · 코호트 밖 직원도 표 칸 폭 · 줄 높이가 끈 화면과 다름 | 켬 · 끔 rect · 메인 그림 재확인 |
| w4-03 | 위 줄 · 레일(코호트 밖 직원) | 모두 | 잘못 | 낮음 | 볼 수 없는 사람에게 조용히 | 화면 열 때마다 `/api/erp-actions/badge` 404 + 콘솔 오류 한 줄 | 콘솔 |
| w4-06 | 상세 'AI 제안' 상자 머리 | 1180×820 | 잘못 | 낮음 | 판 한 줄 | '운영 AI' 두 줄 · 제목 낱말 가운데 꺾임 | 그림 |
| w4-07 | 상세 'AI 제안' 상자 단추 | 1180×820 | 잘못 | 낮음 | 44px | 43px | 잼 |
| w4-08 | NowPC 작업 목록 칩 | 1440 · 1280 · 110~130% | 잘못 | 낮음 | 판 한 줄 | 칩 7개 중 6개 두 줄 → 그 줄 +46px(다른 칸 폭은 그대로) | 잼 |
| w4-09 (확실하지 않음) | NowPC 칩 글 | 모두 | 부족 | 낮음 | 판 NowPC 칩에 값('토 11-21 로 옮기기') | 할 일 이름만(NowTablet 판은 이름이라 판끼리 다름) | 그림 |
| w4-10 | NowPC '현재 작업' 펼쳤을 때 | 모두 | 잘못 | 낮음 | 판: 칩이 제자리 | 칩이 큰 카드 아래로(템플릿으로만 확인) | 템플릿 |
| w4-11 | 상세 'AI 제안' [승인] 색 | 1180×820 | 잘못 | 낮음 | 판 · 태블릿 주 단추 남보라 | 부트스트랩 파랑 | 그림 |
| w4-12 | 상세 'AI 제안' 바뀌는 값 줄 | 1180×820 | 잘못 | 낮음 | 보낼 것으로 읽힘 | 알림톡 제안에 '1건 보냄'만 — 이미 보낸 것처럼 읽힘 | 그림 |

보완(의견) w4: B1 '단계 한 줄' 규칙을 태블릿 바탕 꾸밈으로(w4-01) / B2 칩이 칸 폭 계산에 안 끼게 · 한 줄 말줄임(w4-04 · 08) / B3 상세 아래 단추 줄을 패널 아래에 붙임(w4-05) / B4 키 낮은 화면 · 110% 이상에서 레일 한 단계 더 줄임(w4-02) / B5 badge 404 대신 200(w4-03) / B6 제안 둘 이상이면 '외 1'.

#### 글 대 코드 (w6)

| 번호 | 판/화면 | 크기 | 갈래 | 무게 | 기대 | 실제 | 확인 |
|---|---|---|---|---|---|---|---|
| w6-01 | 실측 예약 알림톡 제안(O1) — 운영 지금 | — | 잘못 | 높음 | 설계서 3.4 기간 '날짜가 지났거나 7일' · 3.10 O1 | 넣을 값이 비어 기간이 늘 7일(`sweeps.py:213` · `lifecycle.py:113-120`), 막는 조건이 실측일 지남 · 이미 보냄을 안 봄(`preview.py:277-280`), 손 발송은 서명 겹침 검사 건너뜀(`kakao_alimtalk.py:836-840`) → 실측 뒤 6일 동안 승인하면 손님에게 나가고 이미 보낸 뒤면 두 번째가 나감. 접목판 스위치 밖(`runners.py:294-319`). 시공일 안내는 둘 다 막음 | 코드 + 확인 시험 4개(`w6\probe\`) · 메인 코드 재확인 → **운영 수준 0 으로 끔(D230)** |
| w6-04 | 채널톡 작은 창 [같이 넣기] — 운영 지금 | — | 잘못 | 높음 | D226 '관리자만' | 관리 칸 `graft_actions_enabled` 하나로 켜지고 사람별 스위치를 안 봄(`wam_functions.py:220-222` · `access.py:86-99`) → 작은 창을 쓰는 모든 CS 직원에게 열림. 실제 주문에 시공 메모가 쓰이고 도면 일이 걸리면 도면팀 알림 | 메인 코드 재확인 → **사용자 '그대로 두기'(D231)** |
| w6-02 | 폰 알림(켜면) | — | 부족 | 높음 | 설계서 3.14 | 제안마다 알림이 따로 · 관리자는 모든 제안 → 새벽 2시에 한꺼번에 울림. 조용한 시간 · 묶음 장치 없음 | 코드 |
| w6-03 | 폰 알림 받는 팀 — 도면 담당 맡기기 | — | 잘못 | 보통 | D221 '도면 담당 = 도면팀' | 담당자가 있으면 팀에는 안 감(D215). 담당 영업이 받고 눌러도 막힘 → 도면팀 줄이 사실상 안 쓰임 | 코드 |
| w6-12 | 기간 지난 제안(F-13 반만 고침) | — | 잘못 | 보통 | F-13 '고침' | 승인만 막고 화면 · 작은 창에는 그대로 보임. 밤 단계가 '끝남 닫기' → '훑기' 순서라 7일째 낮 내내 보이고 누르면 막힘, 닫힌 밤에 다시 만들어짐(시각 순서는 짐작) | 코드 |
| w6-06 | 방문 옮기기(AS) 제안 | — | 부족 | 보통 | D223 받는 팀 | 이 제안을 만드는 쪽이 없음 | 코드 |
| w6-07 | AS 접수 제안 · D224 | — | 부족 | 보통 | 무상 AS 는 시공일로부터 1년 | 코드 주석 한 줄뿐. 몇 해 전 끝난 주문도 '무상 추정', 승인 창에 무상 기간 지남 표시 없음 | 코드 |
| w6-08 | 시공일 안내 알림톡(켜면) 실패 뒤 | — | 부족 | 보통 | 설계서 3.13 | 승인 때 같이 보내기가 실패하면 다시 보낼 길 없음(O4 처음 수준 0) | 코드 |
| w6-09 | 밤 훑기 글 | — | 잘못 | 낮음 | 설계서 4절 | '푸시 없음'이라 적혔지만 폰 알림 스위치를 켜면 보냄 | 코드 |
| w6-10 | 설계서 · 계획서 옛 글 | — | 잘못 | 낮음 | D223 · D225 · D226 | 설계서 3.14 '방문 옮기기(AS) = CS' · F-12 '1년 안' · F-16 상태 · 11절 7번이 옛 값 | 글 |
| w6-11 | 계획서 커밋 번호 · 끝난 기준 | — | 잘못 | 낮음 | 계획서 2 · 6절 | 커밋 번호 26개 중 22개가 합치기 전 옛 번호. T14 ④ · V1 열째 '비어 있어야 함'은 F-09 고침 뒤 거짓(격리만 바꿈) | git |
| w6-13 | 새 화면 틀 긴급 창 CSS 핀 | — | 잘못 | 낮음 | 설계서 5.1 | 손 핀 `?v=20261016a`, 전역 머리는 `20261019a` | 코드 |
| w6-14 | 계획서 8 · 9절 | — | 부족 | 낮음 | 체크 · 기록 | 8절 체크 셋 안 지워짐, `AI_CHANGELOG.md` 에 접목판 기록 없음 | 글 |

보완(의견) w6: w6-05 수준 1 · 2 가 코드에서 같은 동작(둘로 줄이기) / w6-15 전원으로 넓히면 모든 팀이 손님 알림톡 승인을 봄(손님에게 나가는 두 할 일만 영업 · CS 로) / w6-16 표 셋을 지우는 길 없음 · 카드 200장 상한과 배지 수가 갈릴 수 있음 / w6-17 웹 스위치만 끄면 작은 창 승인은 계속 돎(끄는 날 목록에 상담 관리 칸 둘도).

#### 새 화면 틀 · 승인 대기 · 찾기 (w1)

| 번호 | 판/화면 | 크기 | 갈래 | 무게 | 기대 | 실제 | 확인 |
|---|---|---|---|---|---|---|---|
| w1-01 | BInbox 왼쪽 길잡이(다시 확인 · 판 보기) | 1440 | 잘못 | 보통 | AI 직원별 수(설계서 5.2 세 보기는 한 화면) | 제안 5개인데 세 줄 모두 0('모두'는 10). `inbox_erp_nav.html:10` 처음 값 0, 채우는 `ds-inbox-erp.js` 는 `inbox_main.html` 에서만(`inbox.html:34-40`). `admin_many\recheck-pc.png` | 세 보기 견줌 |
| w1-02 | Main 첫 화면 `/brain` | 1440 | 잘못 | 보통 | 결정할 제안 있으면 승인 대기(설계서 7.9) | 지식 제안 0 · AI 할 일 제안 5 인 admin · cs_mgr 이 찾기로 감. `foms/web/brain.py:289` 가 지식 수만 셈. `admin_k0_amany\root-pc.png` | 사람 둘 |
| w1-03 | BInbox 옆 창, 처리 · 거절된 제안을 주소로 열 때 | 1440 | 잘못 | 보통 | 이미 처리됨 알림(폰 알림 주소 `?proposal=`, 설계서 3.14) | 처리 · 거절된 제안도 [승인] · [고쳐서 승인] · 거절 칩이 뜨고 '주문이 바뀌었어요' 경고. 누르면 409 글이 맨 아래(y≈995). 옆 창이 `status` 안 봄(`ds-inbox-erp-aside.js:146-185`). `admin_done\done-link-approve.png` | 주소로 다시 엶 |
| w1-04 | BSearch 표 | 1440 | 잘못 | 보통 | 목업 아홉 칸 879px 꼭 맞음 | 표 901 / 상자 879 → '다시 볼 날' 22px 잘림. 110% 152 · 120% 261 · 130% 353px. 2400 맞음. `admin_search\msearch.json` | 폭 잼 |
| w1-05 | BSearch 왼쪽 나무 | 1440 | 잘못 | 보통 | 유형 줄 32px 들여짐(목업 x=40) | 들여쓰기 없음(x=16). `.fb-tree__type{padding-left:32px}`(`brain-ds-search.css:16`)가 `.f-app a.f-nav-item`(`foms-ds.css:197`)에 짐 | x 잼 |
| w1-06 | BSearch 첫 화면 | 1440 | 부족 | 보통 | 목업 모든 유형 표 · 거르기 · 쪽 · 미리 보기 | 표 없음 '찾을 말을 적어 주세요'. 표 API 가 유형 하나만(`browse.py:88`). 옛 화면도 같은 꼴일 수 있음 — 목업과 '기능은 지금 그대로'(설계서 1.1)가 어긋나는 문제, 사용자 결정 거리 | 견줌 |
| w1-07 | 위 줄 · 거르기, 전역 120% 이상 | 1440 | 잘못 | 보통 | 한 줄 | 위 줄 101 · 109px(이름 둘째 줄), 거르기 이름 110% 부터 꺾임('위험 등/급'). `admin_zoom\zoom120-table.png` | 저장 값 넣고 읽음 |
| w1-08 | BInbox 지식 고침 빈 글 | 1440 | 잘못 | 낮음 | 지식만 없다는 글 | AI 제안 5개 있어도 '승인 대기가 없어요'(`ds-inbox.js:148`) | 찍음 |
| w1-09 | BSearch 거르기 고르기 칸 | 1440 | 잘못 | 낮음 | 글 다 보임 | '제작 조건 (2)' · '쓰인 횟수 많은 순' 잘림 | 글 폭 |
| w1-10 | BSearch 머리 | 1440 | 부족 | 낮음 | '지식 N개 · 사용 중 N개' + [내보내기] | 둘 다 없음(옛 화면에도 내보내기 없음) | 화면 |
| w1-11 | BSearch 이름 칸 꼬리표 | 1440 | 잘못 | 낮음 | '수정 대기 1' · '엇갈림 1' | '확인 필요' 하나(`ds-search-view.js:61`) | 화면 |
| w1-12 | BSearch 미리 보기 '마지막 확인' | 1440 | 부족 | 낮음 | 날짜 · 확인한 사람 | 날짜만(`ds-search-preview.js:64`) | 화면 |
| w1-13 | BSearch 나무 묶음 이름 | 1440 | 잘못 | 낮음 | '바깥 정본' 한 줄 | '바깥 정본(가리키기만)' 두 줄(51px) | 잼 |
| w1-14 | 위 줄 찾기 칸 | 1440 | 잘못 | 낮음 | 안내 글 '지식 · 유형 · 할 일 이름' | '시공 잡기' 찾으면 '찾은 지식이 없어요' — 할 일 이름은 안 찾음 | 찾아 봄 |
| w1-15 | BInbox 옆 창 단추 줄 | 1440 · 2400 | 잘못 | 낮음 | 승인 · 고쳐서 승인 · 나중에 한 줄 | '나중에' 둘째 줄(필요 309 > 304px). `admin_aside\maside.json` | 잼 |
| w1-16 | BInbox 승인율 글 | 1440 | 잘못 | 낮음 | '2주 승인율' | '14일 승인율'(`ds-inbox-erp-aside.js:86`) | 화면 |
| w1-17 | BInbox AI 제안 '나중에' | 1440 | 부족 | 낮음 | '나중에 볼 것'에서 다시 볼 수 있음 | 접은 AI 제안은 수(0)에 안 들어가고 다음 날 06:00 까지 볼 길 없음 | 눌러 봄 |
| w1-18 | BInbox 볼 수 없는 제안 주소 | 1440 | 잘못 | 낮음 | 화면 말투 · 까닭 | 빨간 '찾을 수 없습니다.' | 사람 바꿔 봄 |

보완(의견): 2400 에서 카드 글과 [승인] 1870px 떨어짐(가운데 칸 최대 폭) / 고쳐서 승인 칸 편 동안 아래 [승인] 숨기기 / 거절 까닭 다섯이 할 일과 상관없이 같음 / `?proposal` · `?agent` 를 주소에서 지워 새로고침하면 사라짐 / 주소로 연 제안이 '더 보기' 안이면 안 보임 / 두 칸 빈 글 모양 맞추기 / 제안만 보는 직원은 제안 0 이면 물어보기로 / 찾기 결과 0 이면 빈 표 머리 숨기기.

#### 지식 카드 · 온톨로지 · 물어보기 (w2)

| 번호 | 판/화면 | 크기 | 갈래 | 무게 | 기대 | 실제 | 확인 |
|---|---|---|---|---|---|---|---|
| w2-08 | BOnto 왼쪽 목록 '방문' | 1440 · 2400 | 잘못 | 높음 | 목업 `BOnto.dc.html:41` 한 줄 | '방/문' 세로 꺾임. 글 칸 27×41px, 줄 51px(다른 줄 32px). 옆 말 줄바꿈 금지 133px · 목록 폭 224px 고정(`brain-ds-onto.css:21,24`). `onto_on_home_1440.png` | 그림 + rect |
| w2-09 | BOnto '할 일 종류' 표 | 1440 | 잘못 | 높음 | 목업 `BOnto.dc.html:105-118` 네 칸 다 보임 | '승인 자리' 칸이 섹션 밖. 넘침 842>832 · 860>832 · 971>832(139px 가려짐). 제목 'AI 자율 수…' 잘림, 'AS/건' 꺾임. 2400 정상. `onto_on_defs_erp_actions_1440.png` | scrollWidth + 그림 |
| w2-10 | BOnto '속성 ↔ 지금 칸' 표 | 1440 | 잘못 | 보통 | 목업 92-95 줄바꿈 금지 | '값 모양' 칸 108px, 낱말 가운데 꺾임('주소 → 현/장' 등). 칸 폭 90/424/108/210(`ds-onto-detail.js:108-116`) | 줄 수 |
| w2-11 | BOnto '감싸는 지금 기능' | 1440 · 2400 | 잘못 | 보통 | 쉬운 말 + 길 이름 | 개발자 함수 이름 · 설계서 번호가 화면 글로(`validate_schedule_input → …`, '설계서 3.13'). `registry.py` `wraps` → `ontology_view.py:146` | 그림 |
| w2-16 | BAsk 가운데 칸 폭 | 1440 · 2400 | 잘못 | 보통 | 목업 오른쪽 '이 답이 읽은 것' 늘 있음 | 주문 읽은 답일 때만 오른쪽 창 → 가운데 폭 1160 ↔ 824(336px) 흔들림(`ds-ask.js:110-118`) | rect |
| w2-17 | BAsk '오늘 물은 것' 누르기(새로 고침 뒤) | 1440 | 부족·잘못 | 보통 | 고른 질문의 물음 · 답이 보임 | 지난 답 다시 볼 길 없음. 60자로 잘린 가린 글이 '…' 까지 묻기 칸에(`chat_log.py:41`). 보내면 잘린 질문 + 하루 수 하나 줄어듦 | 입력 값 |
| w2-18 | BAsk 물음 말풍선 | 1440 | 잘못 | 보통 | 목업 71-72 가린 글 + 가린 갈래 꼬리표 | 친 글 그대로(전화번호 화면에 남음, `ds-ask-turn.js:37-40`). 갈래 없이 '1곳을 가려서 보냄', 그것도 ERP 읽기 켠 사람만 | 그림 |
| w2-19 | BAsk '모름' 답 | 1440 | 부족 | 보통 | 목업 113-123 [도면팀에 묻기] · '찾은 회사 지식 0개' · '빈 지식에 올렸어요' | 셋 다 없음. '물어볼 곳' 상자만(답 글과 겹침). 설계서 5.4 목록에는 없는 칸 | 그림 |
| w2-01 | BItem 오른쪽 '승인 대기' 상자 | 1440 · 2400 | 부족 | 보통 | 목업 149-156 누가 · 언제 · 무엇 | 고정 글만(`item_aside.html:20-29`), 서버가 수만 줌(`card.py:203`) | 그림 + 코드 |
| w2-12 | BOnto 지식 유형 속성 표 · 능력 질문 표 | 1440 | 잘못 | 보통 | 줄바꿈 금지 | '하나 고/름' · '슬라이/딩' 등 낱말 가운데 꺾임 | 줄 수 |
| w2-03 | BItem 'ERP 물건과 이어짐' 칩 | 1440 | 잘못 | 낮음 | 누를 수 있는 칩 | `<span>` 이라 못 누름(`ds-item.js:118`), 글 '주문 · 도어 재단' | 그림 + 코드 |
| w2-05 | BItem '이어진 지식' 제목 | 1440 | 잘못 | 낮음 | 작은 제목 | 24px/700(h1 과 같음) — `.h6` 없음(`brain-ds-item.css:15`) | computed |
| w2-13 | BOnto '정본 자리' 값 | 1440 · 2400 | 잘못 | 낮음 | — | `word-break: break-all`(`brain-ds-onto.css:56`) → '없/음' · `sche/dule` | 그림 |
| w2-14 | BOnto 머리 '이어진 것' | 1440 | 부족 | 낮음 | 목업 70-72 '지식 쪽' 칩 | ERP 물건 칩만 | 그림 |
| w2-15 | BOnto '정본 자리' 줄 | 1440 | 부족 | 낮음 | 목업 152-157 읽는 길 · 바뀐 기록 | 넷만(`ds-onto-kit.js:209`) | 코드 |
| w2-20 | BAsk 관리 칸 자리 | 1440 | 잘못 | 낮음 | '빈 지식 · 이번 주' 오른쪽 창 안 | 가운데 묻기 칸 아래 | 그림 |
| w2-06 | BItem 제안 단추 글 | 1440 | 잘못 | 낮음 | '은퇴' · '지우기' | '은퇴 제안' · '지우기 제안' | 그림 |

보완(의견): w2-02 연결 18개가 1/3 폭 한 칸에 18줄(묶음 하나면 온 폭 · 5~8줄 + '그 밖 N개') / w2-04 '쓰인 횟수 4번' 과 쓰인 곳 '32 · 1 · 1' 수가 다름 / w2-07 연결 0 인데 '이웃 지도' 단추 / w2-21 빈 '지난 7일' 제목 / w2-22 남은 질문 0 인데 [물어보기] 눌림 / w2-23 오른쪽 창이 안 따라옴(sticky) / w2-24 2400 에서 답 카드 1750px.

#### AI 직원 · 폰 · 세로 태블릿 · 배율 (w3)

| 번호 | 판/화면 | 크기 | 갈래 | 무게 | 기대 | 실제 | 확인 |
|---|---|---|---|---|---|---|---|
| w3-01 | AI 직원 할 일 표 | 폰 390 | 잘못 | 높음 | 설계서 5.5 칸 다섯이 읽힘 | 표 621px · 상자 358px 가로 밀기, 첫 화면 두 칸만. 메모 칸 54px 로 글 한두 자씩 꺾임('알림톡 보내기' 줄 218px · 10줄). 원인 `foms-ds.css:179` `.f-table{width:100%}` + `f-td-nw`. 그림 `shots\agents\brain_tab_agents-phone.png` | 잼 + 그림 |
| w3-02 | 칸 제목(AI 직원 · 온톨로지) | 폰 390 | 잘못 | 높음 | 제목 한 줄 | 'AI 시험' 52px 2줄, '읽는 것 · 쓰는 도구' 2줄, 온톨로지 '할 일 종류' 37px 3줄. 원인 `foms-ds.css:171-173` `.f-section-head` 한 줄 고정 + 제목이 설명에 밀림 | 잼 + 그림 |
| w3-03 | AI 직원 도구 표 | PC 1440 · 화면 크기 120% | 잘못 | 높음 | 꺾임 없음 | 둘째 칸 17~25px, '회사 지식 찾기' 6줄 세로. 110 · 130% 는 없음. `shots\zoom\crop_agents_z12.png` · `measure-z1.2.json`. 100% 1200px 창도 같을 것(미확인) | 잼 + 그림 |
| w3-04 | 온톨로지 '할 일 종류' 머리 | 폰 390 | 잘못 | 보통 | 겹침 없음 | '새로 붙음' 꼬리표 상자 39px · 글 66px → 27px 겹침. `ds-onto-detail.js:124`, `shots\tabs\crop_onto_actions_head.png` | 잼 + 그림 |
| w3-05 | 승인 대기(BPhone) | 폰 390 | 잘못 | 보통 | 설계서 5.4 · 5.5 폰에서 승인 못 하는 것은 'PC 에서 볼 것' | 폰에서 승인 못 하는 ERP 카드 셋이 '폰에서 승인 4' 수 · 목록 맨 앞에. 'PC 에서 볼 것' 묶음 0 이라 숨음. 승인 가능한 지식 카드는 '1개 더 보기' 뒤. `ds-inbox-erp-card.js:152` · `ds-inbox-erp.js:5` | 잼 |
| w3-06 | 모든 탭 배치 | 세로 태블릿 768 | 잘못 | 보통 | 본문이 첫 화면에 | 왼쪽 길잡이가 한 줄 다 차지, 본문 아래로(승인 대기 y=722, 온톨로지 y=1020, AI 직원 y=608 · 실행 기록 y=1845, 물어보기 y=431). 위 줄 3줄 122px. 찾기 · 지식 표만 정상. `foms-ds.css:91-94` | 잼 + 그림 `shots\tabs\*-tab768.png` |
| w3-07 | 누르는 곳 | 세로 태블릿 768 | 잘못 | 보통 | 태블릿 44px | 탭 30px · 수준 고르기 26px · ERP 카드 [승인] 약 22px. 44px 규칙이 640px 아래만(`brain-ds-shell.css:57-62`) | 잼 |
| w3-08 | 누르는 곳 | 폰 390 | 잘못 | 보통 | 설계서 5.5 44px | 카드 제목 단추 21px · 주문 칩 24px · 온톨로지 탭 30 · 칩 24 · 경로 21 · 지식 표 이름 링크 21 · 옆 창 닫기 30×44 등 | 잼 |
| w3-09 | 지식 카드 'ERP 물건과 이어짐' | 폰 390 | 잘못 | 보통 | 꺾임 없음 | '주문 품목 이름과 이어져요' 30px 6줄. `ds-item.js:116`(`f-row-nw`) | 잼 + 그림 |
| w3-10 | AI 직원 · 온톨로지 | PC 1440 · 130% | 잘못 | 보통 | 목업: 실행 기록 오른쪽 | 오른쪽 옆 창이 본문 아래로(y=1618 / 1603). 120% 는 위 줄 2줄(101px) | 잼 |
| w3-11 | 온톨로지 길잡이 '방문' | 768 · 110~130% | 잘못 | 낮음 | 꺾임 없음 | '방/문' 2줄(27~36px). `erp_ontology/objects.py:64` | 잼 + 그림 |
| w3-12 | AI 직원 도구 표 | PC 100% · 768 · 폰 | 잘못 | 낮음 | 목업 한 줄 | '승인 대/기'(165px) 등 2줄 | 잼 |
| w3-13 | AI 시험 도는 중 | PC | 잘못 | 낮음 | 끝나기 전 판정 없음 | 17/40 인데 '지난 상담' 꼬리표 '통과'(초록). `evals_view.py:80`. 일부러인지 불확실 | 그림 |
| w3-14 | 수준 0 꼬리표 색 | 전부 | 잘못 | 낮음 | 목업 무채색 | 초록(`views.py` `_tag` · `_duties`). 무채색 금지 규칙 때문일 수 있음 — 불확실 | 잼 |
| w3-15 | 실행 기록 단계 아이콘 | 전부 | 잘못 | 낮음 | 목업 상태마다 아이콘 | 늘 초록 체크(`ds-agents-kit.js:180`), '건너뜀' · '걸림 N개' 도 체크 | 그림 + 코드 |
| w3-16 | 상담 AI 실행 기록 | PC | 부족 | 낮음 | 목업 7단계 | '손님 · 주문 찾기' · '회사 지식 찾기' 단계 없음(`runs.py:92-108`) | 코드 + 그림 |
| w3-17 | 머리 단추 | PC | 부족 | 낮음 | 목업 [지시문 보기] | 없음(설계서에 없음 — 일부러인지 불확실) | 그림 |
| w3-18 | 할 일 표 | PC | 부족 | 낮음 | 목업 '새로 붙음' 꼬리표 | 없음 | 그림 |
| w3-19 | 실행 기록 머리 | PC | 부족 | 낮음 | 목업 '담당 <이름>' | 없음 | 그림 |
| w3-20 | 물어보기의 AI 시험 칸 | PC | 부족 | 낮음 | 설계서 3.10 물어보기 평가 점수(있을 때) | 점수 저장하는 곳이 없어 늘 '시험 묶음이 없어요'(`brain_chat_eval.py` 출력만) | 코드 |
| w3-21 | AI 시험 '마지막 시험' 줄 | 폰 | 잘못 | 낮음 | 아이콘 · 글 한 줄 | 아이콘만 한 줄(y=2164 / 글 2188) | 잼 |
| w3-22 | 승인 대기 머리(BPhone) | 폰 | 잘못 | 낮음 | 목업 부제가 흰 머리 안 | 부제가 회색 본문 첫 줄. 16px 결정 탓일 수 있음 | 그림 |

보완: 수준 고르기 바로 저장(확인 없음, 알림톡 수준도) → '저장됨 · 되돌리기' 한 줄 / 쓰임 줄 기간 둘(7일 · 14일) 하나로 / 칸 제목은 안 줄고 설명은 다음 줄(w3-02 · 04 한 번에) / 폰 할 일 표 메모 칸 덜기(w3-01) / 641~991px 를 폰 모습으로(w3-06 · 07).

#### 폰 홈 · 폰 목록 · 채널톡 작은 창 (w5)

| 번호 | 판/화면 | 크기 | 갈래 | 무게 | 기대 | 실제 | 확인 |
|---|---|---|---|---|---|---|---|
| w5-01 | 폰 작업 목록 카드 머리 | 360×640, 390×844(경보 배지 있는 카드), 화면 130% · 글자 130% | 잘못 | 보통 | 새 칸이 원래 것의 자리를 흔들지 않는다(F-22 와 같은 꼴) | 칩 붙은 카드만 머리 줄 44→74px, 카드 30px 길어짐(254.3→284.3). 이력 단추가 둘째 줄 왼쪽(x 49)으로, 주문 번호 x 245.9→305.9. 130% 에서는 칩 카드 전부 꺾임. 칩의 넓힌 누르는 자리가 이력 단추 위 3px 와 겹침. `foms-graft-cells.css:46-63`(`max-width:55%`), `erp_mobile_queue_card_v2.html:55-57`. `shots\cmp-card-head.png` | 켬 · 끔 같은 자료 rect |
| w5-02 | 작은 창 할 일 제안 줄 | 390 | 잘못(F-13 남은 반쪽) | 낮음 | F-13 '고침' | 기간 지났지만 밤 정리 전 제안이 창에 보이고 [같이 넣기] 미리 골라짐. 보내면 '이미 처리된 제안이에요 — 새로 불러와 주세요'. `send_view.py:186-214`(`inline_proposal`)가 `expires_at` 안 봄. `wam\expired-send-open.png` | 진짜 `wam_functions.handle` + 가짜 채널톡 |
| w5-03 | 폰 목록 칩 · 어두운 화면 | 390 | 잘못 | 낮음 | 지금 색 · 토큰으로(설계서 6절) | 어두운 화면에서도 밝은 칩(바탕 rgb(243,244,255)). 접목 CSS 에 어두운 화면 규칙 없음. `shots\cmp-dark.png` | `color_scheme="dark"` |
| w5-04 | 폰 승인 대기 옆 창 | 360 · 390 | 잘못 | 낮음 | 창이 화면 안에 깔끔히 | 옆 창 아래 끝(564 · 768)과 아래 탭 줄(578 · 782) 사이 14px 틈으로 뒤 목록 글이 비침. `inbox\inbox-360-1b-aside-bottom.png` | 누름 → 이동 → [자세히] |

보완(의견): w5-05 근거 칩에 목업 아이콘 없음(글 머리로 읽히니 안 더해도 됨), https 아닌 주소면 못 누르는 글인데 머리말은 '누르면 열려요' / w5-06 130% 에서 셋째 이름 '…' / w5-07(보통) 폰 칩의 'AI 제안 · ' 머리글이 자리를 먹어 할 일 이름이 잘림 — 머리글을 빼면 w5-01 도 크게 줄어듦 / w5-08 [같이 넣기] 남보라와 [보내기] 파랑 ΔE 5.3(같지도 갈리지도 않음), 이어진 FOMS 계정 없는 상담원도 [같이 넣기] 골라진 채 보이고 보낸 뒤에야 알림.

### 점검 2차 고치기 기록 (11-15 — 사용자 "86가지 전부")

고침 일꾼 다섯(모두 Opus — cells · agents-shell · backend 는 effort xhigh, inbox-search · item-onto-ask 는 high)이 따로 워크트리에서 고치고 메인이 `session/foms-graft` 에 합쳤다. 번호마다 점검 때와 같은 도구로 고치기 전 → 뒤를 다시 쟀다(그림 · 잰 값은 스크래치패드 `audit2\fix-<일꾼>\`, 합친 화면은 `audit2\merged\`).

| 묶음 | 번호 | 커밋 | 다시 잰 값(요점) |
|---|---|---|---|
| PC · 태블릿 · 폰 AI 칸 (cells) | w4-01 ~ w4-12 · w5-01 · w5-03 | `d885f48eb` · `02e03551d` | 태블릿 칩 칸 폭 차이(켬 − 끔) 40 ~ 49px → 11가지 크기 모두 0 · 칩 3 ~ 6줄 → 1줄. 끈 화면 세로 꺾인 단계 배지 23/26 → 0. 상세 아래 단추 줄 y 853 ~ 905(화면 밖) → 752 ~ 804. 레일 아래 묶음(회사 지식 · 알림 · 내 정보)이 화면 안 14 → 94장(1180×820 · 100% 는 요소 차이 0). 폰 카드 머리 두 줄 30/32 → 1/32. badge 404 → 200 |
| 첫 화면 · 승인 대기 · 찾기 (inbox-search) | w1-01 ~ w1-13 · w1-15 ~ w1-18 · w3-05 | `35b4962e5` · `b56944f1f` · `fc4b7f8ab` | 찾기 표 잘림 22 · 152 · 261 · 353px → 1440 · 2400 · 110 ~ 130% 모두 0. 첫 화면은 모든 유형 표(D232), [내보내기](D233 — 관리자만 · 감사 기록 · 5,000줄 상한). 처리된 제안 주소는 '이미 처리된 제안이에요'. 폰 '폰에서 승인'은 폰에서 승인할 수 있는 카드만(나머지는 'PC 에서 볼 것') |
| 지식 카드 · 온톨로지 · 물어보기 (item-onto-ask) | w2-01 ~ w2-20 가운데 결함 17 · w3-04 · w3-09 · w3-11 | `142152d80` · `e5b642a7c` · `0e9d33722` | '방/문' 꺾임 → 모든 크기 0. '할 일 종류' 표 넘침 971/832 → 832/832(110 ~ 130% 도 0). 낱말 가운데 꺾임 115 → 0. 물음 말풍선은 가린 글 + 가린 갈래 꼬리표. 지난 질문 다시 보기(하루 수 안 줄어듦). [○○팀에 묻기](D233 — FOMS 안 알림, 같은 질문 한 번) |
| 공용 틀 · AI 직원 (agents-shell) | w3-01 ~ w3-03 · w3-06 ~ w3-08 · w3-10 · w3-12 ~ w3-22 · w1-07 위 줄 · w1-14 · w5-04 · w6-13 | `225c0de5a` · `11c0e36c5` · `71e03862b` | 세로 태블릿 768 은 폰 모습(본문 첫 y: 승인 대기 742 → 96). 화면 크기 120 · 130% 위 줄 한 줄 · 도구 표 꺾임 8곳 → 0. 폰 할 일 표 621 > 358px → 줄마다 카드. 44px 아래 누르는 곳(폰 · 768) → 모든 탭 0. [지시문 보기](D233 — 관리자만, 읽기만). 수준 색 넷(청록 · 파랑 · 금빛 · 빨강) |
| 제안 규칙 (backend) | w6-01 · w6-03 · w6-06 ~ w6-09 · w6-12 · w5-02 | `287666eea` · `8ae1a5440` · `a0236ae30` · `224ae2868` · `3d2c3aafe` | 실측 예약 알림톡 제안: 실측일 지남 · 이미 보냄이면 승인 · 실행을 막고, 기간은 실측일이 끝날 때 끝나고, 일정이 바뀌면 낡은 것으로 닫힘(새 시험 11개 빨강 → 초록). 기간 지난 제안은 배지 · 칩 · 승인 대기 · 작은 창에서 안 보임. 방문 옮기기(AS) 제안 만들기 · AS 접수 '무상 기간 지남' 표시(D235 · D224). 시공일 안내 실패 → 다시 보내기 제안 하나 |
| 합치기 (메인) | w6-07 의 실제 기록 · w2-19 알림 바로가기 · 쓰기 길 등록 · w6-10 · w6-11 · w6-14 | `ce5846005` · 이 커밋 | AS 접수 실행이 무상 기간이 지났거나 시공일을 모르면 무상/유상 칸을 '미정'으로 넣음(시험 고치기 전 3 빨강). 설계서 · 계획서 옛 글 바로잡음 |

고치지 않은 것(사용자 결정): w6-02 폰 알림은 지금처럼 하나씩(D234) · w6-04 작은 창 [같이 넣기]는 모든 CS 직원에게 그대로(D231).

합친 뒤 메인이 직접 다시 본 것: 새 회사 지식 화면 네 탭(승인 대기 · AI 직원 · 온톨로지 · 찾기) × 폰 390 · 세로 태블릿 768 · PC 1440 — 가로 넘침 0 · 글자 꺾임 0 · 폰 · 768 의 44px 아래 누르는 곳 0, 태블릿 표 · 상세 고치기 전 · 뒤 그림, 폰 승인 대기 묶음.

남은 것 · 알려 둘 것:
- 계획서 2 · 7절에 적힌 커밋 번호 대부분은 합치기(rebase) 전 번호라 지금 가지에서 찾을 수 없다(w6-11). 지금 번호는 `git log --grep` 으로 찾는다. T14 ④ · V1 열째의 '비어 있어야 함'은 F-09 고침(`7fb1ad132` — 격리만 바꿈) 뒤로는 `tests/support/graft_char.py` 19줄이 나온다.
- 태블릿 작업 표는 화면 크기 110% 부터 끈 화면에서도 오른쪽 칸이 잘린다(원래 있던 것). 단계 한 줄(w4-01)로 그 잘림이 조금 깊어졌다(110% 첨부 34 → 43px, 120% 시공일 6px).
- 폰 360 · 화면 크기 130% · 경보 배지 카드는 여전히 머리 두 줄(남는 폭 10px). PC 칩은 글자 배율 130 · 150% 에서 모두 말줄임.
- 태블릿 레일 메뉴를 굴리는 화면에서 지금 화면 강조 칸이 아래에 숨을 수 있다(`tablet-rail-nav.js`).
- 컨테이너 기준 배치(`@container`)는 크롬 105 · 사파리 16 아래에서 안 먹는다(그런 기기는 예전처럼 가로 밀기).
- [팀에 묻기] 알림은 알림 목록에만 뜬다(폰 푸시 종류 목록에는 넣지 않음). 받는 사람이 새 화면이 꺼진 사람이면 알림을 눌러도 그 질문이 열리지 않는다.
- 지식 유형 표(7칸)는 110 · 120% 와 폰에서 옆으로 밀어야 한다(w2-12 는 꺾임만).
- 일꾼이 찾아 같이 고친 원래 결함: 열린 엇갈림이 하나만 있어도 지식 표의 모든 줄이 '확인 필요'가 되던 것(`foms/services/brain/conflicts.py` 부분 질의가 바깥 질의에 안 묶임).
- 운영에 올릴 때: 새 화면 틀의 긴급 창 CSS 손 핀이 운영 전역 머리(`20261019a`)와 달라 묶는 시험이 운영 PR 에서 빨개진다 — 그때 운영 값에 맞춘다.

일꾼이 스스로 정한 것(사용자 확인 거리):
- 태블릿 표 칩은 할 일 이름 대신 '로봇 아이콘 + 제안' 표지(칸이 75px 라 이름이 한 글자만 보임 — 판 NowTablet 과 다름). PC 칩은 칸이 200px 아래면 'AI 제안 · ' 머리글을 감춤.
- 태블릿 레일: 아래 묶음은 붙박고 위 메뉴만 굴림(1176×626 · 130% 에서 위 메뉴 3/10 칸 보임). 레일을 화면 크기에서 빼지는 않음.
- 찾기: 1440(100%)에서 거르기 넷씩 두 줄(목업은 여덟 칸 한 줄 — 사용자 화면 2400 은 한 줄), 화면 크기 120 · 130% 에서는 왼쪽 나무를 접음. 내보내기 상한 5,000줄.
- 무상 AS 는 1년 되는 그날까지 '안'(2월 29일 시공은 다음 해 2월 28일까지). 방문 옮기기(AS) 처음 수준 2. 시공일 안내 다시 보내기 제안은 AI 수준 표를 보지 않음(사람이 이미 승인한 일의 뒷일).
- 훑기 제안 7일의 끝을 7일째 0시(한국)로 — 그 밤 '끝남 닫기'가 닫고 이어 도는 훑기가 다시 만든다.
- AI 직원: 수준 색 넷, 가운데 칸 720px 아래면 할 일 표를 카드로, '담당 이름'은 관리자에게만, 물어보기 평가 점수는 기본으로 남김(`--no-record` 로 끔).
- [팀에 묻기] 받는 사람은 그 팀의 켜진 직원 가운데 물어보기를 여는 사람(묻는 사람 뺌), 알림 글에 가린 질문 앞 80자.

### 점검 3차 — 남은 흠 고치기 기록 (11-15 밤 — 사용자 "남은 화면 흠 고치기")

위 '남은 것' 가운데 화면 흠 일곱을 고침 일꾼 둘(모두 Opus — cells 는 effort xhigh, brain 은 high)이 따로 워크트리에서 고치고 메인이 합쳤다. 번호마다 먼저 재서 왜 남았는지 찾고, 같은 도구로 고친 뒤를 다시 쟀다(그림 · 잰 값은 스크래치패드 `audit2\fix3-cells\` · `audit2\fix3-brain\`). 운영에는 올리지 않았다(스테이징만).

| 번호 | 무엇 | 커밋 | 고치기 전 → 뒤 |
|---|---|---|---|
| C1 | 태블릿 작업 표 오른쪽 칸 잘림(끈 화면도 원래 그랬음) | `ff4fce2b0` | 표의 가장 좁은 폭 663px > 상자(1180×820 · 130% 에서 458px)인데 상자가 넘침을 잘라 볼 길이 없었다 → 표 상자 안에서만 옆으로 민다(페이지는 안 밀림 · 쪽 번호 줄은 제자리). 볼 길 없는 칸 40 → 0(두 크기 × 100 ~ 130% · 글자 130 · 150% × 켬/끔 24장면). 넘치지 않는 화면(1180×820 · 100%)은 요소 차이 0 |
| C2 | 폰 360 · 130% · 경보 배지 카드 머리 두 줄 | `1a72a9147` | 남는 폭 10px 에 칩(최소 26px)이 못 서 이력 단추가 둘째 줄로 → 칩이 배지 밑 둘째 줄로 내려가고 머리 높이는 그대로. 칩 카드 머리 높이 = 끈 화면 31/32 → 32/32(문제 카드 96.2 → 57.2px), 칩 없는 카드 · 끈 화면 차이 0 |
| C3 | PC 칩 글자 배율 130 · 150% 말줄임 | `1a72a9147` | 대시보드 아이콘 규칙이 로봇 아이콘을 키워 이름 자리를 먹었다 → 칸이 칩 글자 11자 폭보다 좁을 때만 안쪽 여백 · 아이콘을 줄임. 130% 에서 이름이 다 보이는 칩 1440 0/7 → 3/7 · 2400 3/7 → 4/7(나머지는 칸 < 글이라 물리적으로 안 됨 — 앞 낱말 7/7 · 온전한 글은 title). 켬 − 끔 칸 폭 차이 0 그대로 |
| C4 | 태블릿 레일 강조 칸이 굴림 영역 아래 숨음 | `a51346885` | 강조 칸이 메뉴 묶음 밖인 장면 48/88 → 0/88(처음 그릴 때 · 강조가 바뀔 때 · 묶음 높이가 바뀔 때 묶음만 굴림). 1180×820 · 100% 요소 차이 0 |
| C5 · B3 | `@container` 를 모르는 옛 브라우저 | `1a72a9147` · `5bc037033` | 칩 머리글은 감춘 쪽을 기본으로, AI 직원 화면은 폰 폭(640px 아래)에서 카드로. 흉내(CSS 바꿔치기)로 잰 폰 390 문서 폭 638 → 390px. 진짜 옛 기기로는 보지 못했다 |
| B1 | 온톨로지 표 옆 밀기(지식 유형 7칸 등 여섯 표) | `7680f7e74` | 표가 칸보다 넓을 때만 줄마다 카드(칸 폭을 직접 잼). 옆으로 밀리는 표: 110% 6 · 120 · 130% 13 · 768 5 · 폰 13 → 여덟 크기 모두 0, 가려진 칸 최대 453 → 0. PC 100% · 2400 그림은 점 하나까지 같음 |
| B2 | [팀에 묻기] 알림을 눌러도 질문이 안 열림(새 화면이 꺼진 받는 사람) | `7898cfce6` | 옛 물어보기 화면이 주소의 `?question=` 을 읽어 그 한 건(가린 글 · '모름' 답)을 읽기 전용으로 맨 위에 보인다. 읽기는 그 알림을 받은 사람만(안 받은 꺼진 사람은 404 그대로). 폰 알림 종류에는 넣지 않았다 |

합친 뒤: 새 시험 13개(고치기 전 빨강) 초록 · 하네스 687 passed.

일꾼이 스스로 정한 것(사용자 확인 거리): 폰 칩은 배지 묶음 맨 끝(도면 수정 · 통화 배지 뒤) · 칩이 내려간 카드는 경보 배지가 11px 위로 / 온톨로지 표는 화면 크기가 아니라 '넘칠 때만' 카드라 같은 화면에 표와 카드가 섞일 수 있음 / 찾기 화면은 옛 브라우저 대비를 넣지 않음(화면 넘침 0 — 표는 지금처럼 칸 안에서 밈).

아직 남은 것: 태블릿 표를 미는 것은 흉내 낸 손가락으로만 확인(실제 아이패드 · 갤럭시 탭 아님) / 폰 '아이콘만' 칩의 아이콘이 테두리 밖으로 조금 나옴(390 × 130% · 360 · 글자 130% — 원래 있던 것) / 2400 · 글자 150% 의 아홉 글자 할 일 이름 7/9 / AI 직원 화면 폰 360 의 도구 이름 세 곳 세 줄 / 새 화면에서 알림을 받은 사람에게도 '○○팀에 물어보세요' 안내 글이 보임.

[팀에 묻기] 폰 알림(D240 — 11-15 밤): 알림 종류 `BRAIN_ASK_TEAM` 을 폰 보내기 목록에 넣었다(`foms/services/notifications/brain_ask_push.py` · `push_sender.py`). 잠금화면은 제목 '회사 지식 물어보기' + '○○팀에 물어본 질문이 왔어요' 뿐(질문 글 · 묻는 사람 · 답 없음), 누르면 그 질문(`/brain/ask?question=<번호>`), 같은 질문은 꼬리표 하나로 접힌다. 스테이징에 먼저 — 운영에는 따로 말할 때 올린다.

### 특성 시험 문지기 기록 (T13 뒤 메인이 채운다)

| 때 | 커밋 | 고치지 않은 코드에서 돌린 출력(마지막 줄) |
|---|---|---|
| 11-14 | `68b45778e` (`session/foms-graft`) | `95 passed in 3.00s` — 메인이 `foms/` 를 고치지 않은 트리에서 세 파일을 다시 돌림(W11 도 두 번 초록) |

### 스테이징 반영 기록

| 때 | 커밋 | 확인 |
|---|---|---|
| 11-14 | deploy `75b6803d9`(접목판 46커밋 + F-01 `ae8c862dc`, origin/deploy 위로 rebase) · `9352cf7bb`(상태 줄 예산) | smoke 19,012 passed(첫 회 prerender 열쇠 빨강 → `75b6803d9` 고침) · CI 셋 초록 · Railway staging `9352cf7b` 배포 SUCCESS · 운영 그대로 |

### 운영 반영 기록 (D226 — 11-15)

| 때 | 커밋 | 확인 |
|---|---|---|
| 11-15 | 운영 PR #855 → `a2559c4e6`(deploy 접목판 커밋 58개 `528bbc4b8` ~ `96270d94a` 를 운영 `4a76810e9` 위에 cherry-pick, 코드 충돌 0) | 세션 기록부 SHA 가 rebase 전 옛 번호 · 일꾼 커밋 빠짐이라 승격 도구 대신 범위로 골랐다. 문서 둘(`AI_STATUS.md` · `2026-10-27-cs-ai-agent-ledger.md`)만 부딪혀 운영 쪽 글을 두었고, 문서만 바뀐 커밋 하나는 비어 빠졌다(57개). 접목판 파일 250개 중 deploy 와 다른 것은 문서 둘 · `layout_head.html` 긴급 알림 핀 3줄(운영이 새것) · 주문 쓰기 인벤토리의 남의 파일 줄 번호뿐. 승격 트리 smoke 19,030 passed · 하네스 632 passed · `alembic heads` 하나 · PR 검사 넷 초록 · Railway production `a2559c4e` SUCCESS · `/healthz` commit 일치 |
| 11-15 | 운영 PR #856 → `521536cf1`(점검 2차 고침 — deploy `57399526b` ~ `1b2421b63` 23개를 운영 `a2559c4e6` 위에 cherry-pick, 코드 충돌 0 + 긴급 창 CSS 핀을 운영 값 `20261019a` 로 맞춘 커밋 하나) | 문서 셋만 부딪혀 운영 쪽 글을 둠. 승격 트리 smoke 19,178 passed(첫 회 `test_db_leak_trace.py::test_closed_session_is_silent` 한 번 빨강 — 이 PR 밖 파일, 지워진 엔진 `id()` 재사용으로 차례에 따라 흔들림, 다시 돌려 초록) · 하네스 632 · PR 검사 넷 초록 · Railway web · FOMS-cron · WORKER 모두 `521536cf1` SUCCESS · `/healthz` commit 일치. 스위치는 그대로(운영 DB 읽기 전용 확인: 실측 예약 알림톡 제안 수준 0, 오늘 밤 후보 S1 17 · O3 24 → 상한 30) |
| 11-15 밤 | 운영 PR #857 → `62e4f00a9`(점검 3차 남은 화면 흠 일곱 — deploy `7898cfce6` ~ `7b22ba62a` 일곱 커밋을 운영 `521536cf1` 위에 cherry-pick, 충돌 0 · D239) | 승격 트리 닿는 시험 206 passed · 하네스 632 passed · `APP_OK` · `alembic heads` 하나 · PR 검사 넷 초록 · Railway production web · FOMS-cron · WORKER · SIDEFX 모두 `62e4f00a` SUCCESS · `/healthz` commit 일치. 스위치 · 설정 · DB 는 그대로. [팀에 묻기] 폰 알림(D240 · `07c61bc6c`)은 스테이징에만 |
| 11-16 | 운영 PR #858 → `1b42448d3`([팀에 묻기] 폰 알림 D240 `07c61bc6c` · DB 누수 추적 engine 번호 물려받기 고침 `1a1969416` 을 운영 `62e4f00a9` 위에 cherry-pick — 사용자 '지금 운영에 올리기') | 문서 둘만 부딪혀 운영 쪽 글을 둠(문서만 바뀐 커밋 하나는 뺌). 승격 트리 닿는 시험 66 passed · 하네스 632 passed · PR 검사 넷 초록 · Railway production 네 서비스 모두 `1b42448d` SUCCESS · `/healthz` commit 일치. deploy 쪽은 smoke 19,210 passed · CI 넷 초록(앞 push `39792eca1` 은 `test_db_leak_trace.py::test_closed_session_is_silent` 가 흔들려 빨강 → 원인 고쳐 `1a1969416` 초록) |

운영 스위치(GraphQL `variableUpsert`, `RAILWAY_PROJECT_NAME=FOMS-PRODUCTION` 확인, skipDeploys 로 넣고 합치기 배포 한 번에 실음):

- web: `FOMS_GRAFT_BRAIN_UI` · `ACTIONS` · `CELL_PC` · `CELL_TABLET` · `CELL_MOBILE` `_ENABLED=1`, `_COHORT` = 운영 ADMIN 셋 + 측정 계정(읽기 전용으로 고름).
- FOMS-cron: `FOMS_GRAFT_PROPOSERS_ENABLED=1` — 밤 단계 `ai_staff_sweep --apply` 가 제안을 만든다(알림톡 · 푸시 없음).
- 그대로 끔: `FOMS_GRAFT_CONSTRUCTION_ALIMTALK` · `FOMS_GRAFT_PUSH`. `FOMS_GRAFT_ERP_READ` 는 사용자 지시(11-15 질문 창 '물어보기 ERP 주문 읽기 켜기')로 web 에 같은 관리자 목록으로 켬 — 물어보기가 주문 번호를 찾으면 허용 칸만 읽는다(손님 이름 · 전화 · 주소 · 금액 · 메모는 읽지 않음, `foms/services/erp_ontology/ask.py`). 상담 AI 접목 두 칸(관리 화면 '접목' — 근거 줄 보이기 · 할 일 제안 만들기)은 사용자 지시(11-15 "니가 켜")로 켬 — 측정 계정이 관리 화면과 같은 저장 API(`POST /api/admin/cs-agent/settings`, 두 칸만)로 넣어 설정 버전 17 → 18, 수정 기록에 남음. 넣은 뒤 다시 잠금.

운영 실측(11-15, 측정 계정 잠금 풀기 → 보기만 → 다시 잠금 확인, 승인 · 거절 단추 안 누름):

- 새 표 셋 생김(`alembic_version=graft_00`), 세 표 모두 0줄.
- `/brain` 새 화면 다섯 탭(승인 대기 · 찾기 · 지식 표 · 온톨로지 · 물어보기) 모두 200 · 새 틀 · `foms-ds.css`, 서버 응답 140 ~ 321ms.
- `/api/erp-actions/badge` on 넷 모두 참 · 할 일 0 · 지식 6. 승인 대기 0장. AI 직원 목록 200.
- 빈 자리: PC 작업 큐 50칸(1.2초) · 태블릿 50칸 + 레일 '회사 지식'(0.5초) · 폰 'AI 제안 승인 대기' 칸(0.43초).
- 밤 훑기 규칙 후보(읽기 전용 거래로 고르기 · 판정만, 제안 안 만듦): S1 시공 잡기 수준 2 후보 20 → 17 · O1 실측 알림톡 수준 1 후보 12 → 5 · O2 단계 넘기기 수준 0(돌지 않음) · O3 도면 담당 수준 2 후보 127 → 22 · O4 시공일 안내 수준 0 · 스위치 끔. 합 44 라 첫 밤은 상한 30개가 만들어진다. 고르기 질의 2 ~ 478ms.


운영 첫 밤 결과(11-16 02:04 한국 시각 — 읽기 전용 거래로 수 · 상태 · 시간만 읽음, 승인 · 거절 안 누름):

- 밤 단계 11개 모두 `rc=0`(`erp_actions_expire` 1.9초 · `ai_staff_sweep` 2.1초, `failed=none`).
- 제안 30개(한 번에 30개 상한에 닿음) — 도면 담당 맡기기(O3) 24 · 시공 잡기(S1) 6, 모두 수준 2 · 상태 열림 · 근거 1개씩, 주문 29개(한 주문에 둘이 붙은 것 1), 같은 제안 겹침 0. 기간 끝: 11-23 28개 · 11-21 2개.
- 실행 기록 둘: 운영 AI(ops) 281ms — O3 후보 131 → 제안 24, O1 · O2 · O4 는 수준 0 이라 건너뜀 / 일정 AI(schedule) 53ms — S1 후보 20 → 제안 6. 예상(S1 17 + O3 24 = 41 → 상한 30)대로이고, 운영 AI 가 먼저 돌아 24를 쓰고 일정 AI 가 남은 6을 썼다 — 시공 잡기 11개쯤은 다음 밤으로 넘어간다.
- 상담 AI 접목: 근거 쓰임 기록 27 → 36(지난 12시간 6), 상담에서 나온 할 일 제안 0. 폰 알림 줄 0(스위치 끔 — 맞음).
- 아직 아무도 승인 · 거절하지 않음(관리자 넷만 보임).


넓히기(11-16 아침 — D242): 운영 web 의 사람별 스위치 다섯(`FOMS_GRAFT_BRAIN_UI` · `ACTIONS` · `CELL_PC` · `CELL_TABLET` · `CELL_MOBILE`)의 `_COHORT` 를 관리자 넷에서 열아홉으로(켜진 영업 10 · CS 2 · 도면팀 3 을 더함 — 번호는 운영 `users` 를 읽기 전용으로 팀 · 등급 · 켜짐만 읽어 골랐다). `FOMS_GRAFT_ERP_READ_COHORT` 는 관리자 넷 그대로, 알림톡 · 폰 알림 스위치는 끔 그대로. 값은 GraphQL `variableUpsert` 로 넣고 마지막 값이 web 재배포 한 번을 걸었다(코드는 `1b42448d` 그대로). 시공 · 회계 · 협력사 · 꺼진 계정은 넣지 않았다.

둘째 밤 결과 · 상한 나누기(11-17 — D243, 읽기 전용 거래로 수 · 상태 · 시간만):

- 둘째 밤(11-17 02:03 한국 시각) 제안 13개 — 시공 잡기(S1) 후보 16 → 12 · 도면 담당 맡기기(O3) 후보 107 → 1. 첫 밤에 밀린 시공 잡기가 이 밤에 다 만들어져 상한 30개에는 닿지 않았다. 열린 제안 43개(O3 25 · S1 18, 주문 42개), 같은 제안 겹침 0, 이틀 동안 승인 · 거절 0.
- 그래도 구조는 그대로였다: 상한 하나를 규칙 차례대로 먼저 쓰는 꼴이라, 밀린 일이 많은 규칙을 새로 켜면(단계 넘기기 O2 · 처음 켠 날의 O3) 뒤 규칙이 며칠 밀리고, 내일 일 규칙(O4 시공일 안내 — 차례가 O3 뒤)은 그 밤을 놓치면 제안이 소용없다.
- 고침(`foms/services/ai_staff/sweeps.py`): 켜진 규칙마다 제 몫(상한 ÷ 켜진 규칙 수)을 먼저 주고, 남은 자리는 내일 일 규칙(`Rule.due` — O1 · O4)부터 규칙 차례로 채운다. 상한 30개 · 규칙 판정 · 실행 기록 꼴은 그대로. 첫 밤을 이 방식으로 돌렸다면 시공 잡기 15 · 도면 담당 15(시공 잡기 밀림 11 → 2).
- 시험 `tests/domains/test_ai_staff_sweep_share.py` 셋(제 몫 먼저 · 남은 자리는 내일 일부터 · 자리 없는 규칙은 후보도 안 고름) — 앞 둘은 고치기 전 코드에서 빨강. 운영에는 아직 안 올림(스테이징까지).


## 8. 준비 (T0 — 메인)

- [x] 설계서 11절 결정 일곱 — 사용자 답 받음(11-14). 원장 `docs/plans/2026-10-27-cs-ai-agent-ledger.md` D206 ~ D212.
- [x] 목업 · 원점 설계 · 설계서 · 계획서 · 지시문 커밋(`7cedd2812`). 판 2 고침은 다시 커밋해야 따로 워크트리가 본다.
- [x] 설계서 11절 '남은 일 · 아직 정할 것' 일곱 줄을 사용자에게 보인다(D213 ~ D235 로 정해짐)(기본값으로 만들고 있다 — 2 · 3 · 4 · 6 은 답에 따라 T15 · T10 지시문이 바뀐다).
- [x] 물결을 띄울 때마다 `git fetch origin` 뒤 마이그레이션 머리(`python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())"`)가 하나인지 본다.
- [x] 판 그림 12장이 1절 폴더에 있는지 본다.

## 9. 끝난 뒤 (메인)

- `docs/AI_STATUS.md` '진행 중'에 한 줄(위 4,000자 예산 안) · `docs/AI_CHANGELOG.md` 기록.
- 스테이징에서 켜는 차례: `FOMS_GRAFT_BRAIN_UI` → `FOMS_GRAFT_ERP_READ` → `FOMS_GRAFT_ACTIONS` → 칸 스위치 → 상담 관리 칸 → `FOMS_GRAFT_PUSH` → `FOMS_GRAFT_PROPOSERS`. 단계마다 QA 계정으로 화면을 직접 본다.
- **스테이징에서 절대 하지 않는 것**: 알림톡 할 일(실측 예약 · 시공일 안내) 승인 — 스테이징 알림톡은 실제로 나간다. `SOLAPI_TEMPLATE_CONSTRUCTION_ID_*` 를 스테이징에 넣지 않는다. 스테이징 영발방은 실제 직원 방이다. 평가 다시 돌리기는 스테이징에 두뇌 열쇠가 없어 '준비 안 됨'으로 끝나는 것이 정상이다.
- Railway env 는 서비스마다 따로다 — 화면 스위치는 web, `FOMS_GRAFT_PROPOSERS_ENABLED` 는 밤 단계가 도는 서비스, `FOMS_GRAFT_PUSH_ENABLED` 는 제안을 만드는 서비스 셋(web · WORKER · FOMS-cron), `FOMS_GRAFT_CONSTRUCTION_ALIMTALK_ENABLED` 와 서식 번호는 web · FOMS-cron.
- 시공일 안내 알림톡은 사용자가 카카오 서식 심사를 마치고 서식 번호를 준 뒤에만 운영에서 켠다. 코드의 서식 글을 심사 글과 글자까지 맞춘 뒤에.
