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
| D | T9 | W9 | 상담 AI 접목 — 근거 남기기 · 규칙 제안 · 채널톡 작은 창 두 줄(⑤) | xhigh | 따로 `foms-s-graft-cs` | T1 · T7(· T14 — 실측 옮기기 제안이 실행까지 되려면) | RUNNING(바탕 `795f93c79`) |
| D | T15 | W13 | **바깥 알림 둘** — 시공일 안내 알림톡(D208: 스위치 · 서식 글 초안 · 실행기 · 훑기 `O4`) + 승인 대기 폰 알림(D210: 새 알림 종류 · 웹 푸시) | xhigh | 따로 `foms-s-graft-notify` | T7 · T10 · T14 · T2 | RUNNING(바탕 `795f93c79`) |
| D | T16 | W14 | **상담 AI 평가 묶음 + [시험 다시 돌리기]**(D209 — 돌릴 때 DB 에서 가린 글로 묶음 · WORKER 줄 일 · 돈 상한 · 결과 저장 · ⑪ 의 'AI 시험' 칸) | xhigh | 따로 `foms-s-graft-eval` | T10 · T1 | DONE(`12df85ba8`) |
| E | T11 | R1 | 검수(읽기만) — 설계서 맞춤 · 보안 · 품질 | xhigh | `foms-s-foms-graft`(읽기만) | T1 ~ T10 · T13 ~ T16 | PENDING |
| E | T12 | V1 | 합친 뒤 확인 — 명령 전부 · 스위치 끔 견주기 · 핀 · 머리 하나 · 소유 표 | high | `foms-s-foms-graft` | T11 고침 끝 | PENDING |

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
| F-01 | 높음(지금 운영) | `foms/services/orders/order_mutation_policy.py:407-413` · `foms/services/erp_permissions.py:368-382` | CS · 영업 팀 VIEWER(조회 전용) 계정이 시공일 쓰기 길 셋(`foms_order_mutation_policy_manifest.json:803-816`)을 통과 — 정책 문지기 함수가 VIEWER 막기보다 먼저 돌고 `can_edit_erp` 가 VIEWER 를 거르지 않음. 접목판 할 일은 `access.policy_allows` 가 따로 막음(W7) | 접목판 밖 — 사용자에게 보고 · 따로 고침 | OPEN |
| F-02 | 낮음 | `foms/services/erp_actions/views.py:236` | 자세히 답 `params` 에 `required` 가 없다(registry `Param.required` 는 있음) — 화면(T8)이 `time_slot` · `flag` 말고는 꼭 넣을 값으로 미루어 판단 | T11 검수 뒤 정함(T7 답에 더하기 권함) | OPEN |
| F-03 | 낮음 | `foms/services/erp_actions/views.py:134` | 카드 답에 `base_version` 이 없다(설계서 3.6 카드 칸 목록과 같음) — 카드 [승인]은 자세히를 먼저 읽고 승인(요청 둘) | T11 검수 뒤 정함 | OPEN |
| F-04 | 낮음(색) | `static/css/components/foms-graft-cells.css` | AI 칩 글 · 테두리 #4a55b8 과 고객컨펌 단계 배지 #5a67d8 의 ΔE2000 7.5(제2색맹 흉내 뒤 7.3) — 바탕끼리는 42 이상, 옅은 칩과 꽉 찬 배지로 갈린다. 상태 쌍 기준(10)에는 미달 · 색약 기준(6)은 넘음 | T11 검수 뒤 정함(판의 남보라 유지가 기본) | OPEN |
| F-05 | 기록 | `templates/partials/shared/erp_mobile_queue_card_v2.html` | 파일 주인 표(3절) 밖 — 폰 목록 줄 칩(메모리 규칙 '새 기능은 폰 목록 줄에서 보여야')으로 T8 이 더함. 이 카드를 쓰는 6개 목록 모두에 칩이 나온다. 꺼지면 지금과 같음(시험) | — | 기록만 |
| F-06 | 결정 필요 | `foms/services/ai_staff/evals.py`(T16) · 마이그레이션 `csagent_03` | 상담 차례 `held_out` 을 참으로 쓰는 코드가 없다(떼어 두는 기능 C12-1 이 안 만들어짐) — 운영에서도 '지난 상담' 묶음이 0 · 화면 '묶음 0' | 사용자 결정 뒤 따로 | OPEN |
| F-07 | 중간 | `foms/services/erp_actions/registry.py`(T14) | 보는 사람 ≠ 실행할 수 있는 사람(설계서 3.5 와 어긋남): 도면 담당 맡기기는 정책 `STAFF_MUTATION` 이라 모든 직원이 보지만 본체는 관리자 · 도면팀 · 지정 담당만 실행(나머지 409) · 실측 옮기기는 정책이 모든 매니저를 통과시키지만 본체가 팀을 봄(다른 팀 매니저 409) | T11 검수 뒤 정함 | OPEN |
| F-08 | 낮음 | `foms/services/ai_staff/sweeps.py`(T10 규칙 O2) | 넣을 값이 비어 겹침 열쇠가 주문마다 하나 — 한 번 거절되면 그 주문엔 다시 제안되지 않음 | T11 검수 뒤 정함 | OPEN |
| F-09 | 조사 중 | `tests/domains/test_graft_char_quest_approve.py` | T14 합친 뒤 하네스 · 계약 시험과 한 프로세스에서 돌리면 특성 시험 하나가 빨개짐(`erp_stage_updated_at` 이 안 바뀜) — 혼자 · 도메인 묶음 순서대로는 초록. T14 전 같은 순서는 초록(730) | 메인 | OPEN |
| F-10 | 기록 | 설계서 · 지시문 | 코드와 다른 문장: 설계서 :63 `Idempotency-Key` 머리글 빠짐 · :310 '2xx 아니면 막힘'(코드는 5xx = 실패) · :311 '승인하는 사람의 팀'(실행기는 재전이 길만) · :300 · :339 `run_eval` · 줄 일 자리(실제 `evals_run.py` — `tasks.py` 는 층 래칫 · WORKER 가벼움 시험 때문에 못 씀) · :337 `check_codes`(말투 알림도 적힘) · 지시문 :446 `checks_same.py`(같은 뜻 판정은 `case_memory.judge_reply`) · 목업 'BOnto' 도면 담당 폰 승인(실제 PC 승인) · 'BAgents' '기준 밑이면 배포를 막아요'(없는 문지기) | 마무리 때 문서 고침 | 기록만 |
| F-11 | 할 일 | `docs/harness/foms_*_inventory.json` | T14 로 줄 번호만 밀린 인벤토리(audit_coverage · failopen) — push 전 `*_scan.py` 를 직접 돌려 커밋(refresh 는 줄 번호만 바뀐 것을 되돌린다) | 메인(push 전) | OPEN |

### 특성 시험 문지기 기록 (T13 뒤 메인이 채운다)

| 때 | 커밋 | 고치지 않은 코드에서 돌린 출력(마지막 줄) |
|---|---|---|
| 11-14 | `68b45778e` (`session/foms-graft`) | `95 passed in 3.00s` — 메인이 `foms/` 를 고치지 않은 트리에서 세 파일을 다시 돌림(W11 도 두 번 초록) |

## 8. 준비 (T0 — 메인)

- [x] 설계서 11절 결정 일곱 — 사용자 답 받음(11-14). 원장 `docs/plans/2026-10-27-cs-ai-agent-ledger.md` D206 ~ D212.
- [x] 목업 · 원점 설계 · 설계서 · 계획서 · 지시문 커밋(`7cedd2812`). 판 2 고침은 다시 커밋해야 따로 워크트리가 본다.
- [ ] 설계서 11절 '남은 일 · 아직 정할 것' 일곱 줄을 사용자에게 보인다(기본값으로 만들고 있다 — 2 · 3 · 4 · 6 은 답에 따라 T15 · T10 지시문이 바뀐다).
- [ ] 물결을 띄울 때마다 `git fetch origin` 뒤 마이그레이션 머리(`python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())"`)가 하나인지 본다.
- [ ] 판 그림 12장이 1절 폴더에 있는지 본다.

## 9. 끝난 뒤 (메인)

- `docs/AI_STATUS.md` '진행 중'에 한 줄(위 4,000자 예산 안) · `docs/AI_CHANGELOG.md` 기록.
- 스테이징에서 켜는 차례: `FOMS_GRAFT_BRAIN_UI` → `FOMS_GRAFT_ERP_READ` → `FOMS_GRAFT_ACTIONS` → 칸 스위치 → 상담 관리 칸 → `FOMS_GRAFT_PUSH` → `FOMS_GRAFT_PROPOSERS`. 단계마다 QA 계정으로 화면을 직접 본다.
- **스테이징에서 절대 하지 않는 것**: 알림톡 할 일(실측 예약 · 시공일 안내) 승인 — 스테이징 알림톡은 실제로 나간다. `SOLAPI_TEMPLATE_CONSTRUCTION_ID_*` 를 스테이징에 넣지 않는다. 스테이징 영발방은 실제 직원 방이다. 평가 다시 돌리기는 스테이징에 두뇌 열쇠가 없어 '준비 안 됨'으로 끝나는 것이 정상이다.
- Railway env 는 서비스마다 따로다 — 화면 스위치는 web, `FOMS_GRAFT_PROPOSERS_ENABLED` 는 밤 단계가 도는 서비스, `FOMS_GRAFT_PUSH_ENABLED` 는 제안을 만드는 서비스 셋(web · WORKER · FOMS-cron), `FOMS_GRAFT_CONSTRUCTION_ALIMTALK_ENABLED` 와 서식 번호는 web · FOMS-cron.
- 시공일 안내 알림톡은 사용자가 카카오 서식 심사를 마치고 서식 번호를 준 뒤에만 운영에서 켠다. 코드의 서식 글을 심사 글과 글자까지 맞춘 뒤에.
