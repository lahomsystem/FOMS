# FOMS 접목판 실행 계획 · 진행 원장 (2026-11-14)

> 설계서: `docs/specs/2026-11-14-foms-graft_SPEC.md` · 일꾼 지시문: `docs/plans/2026-11-14-foms-graft-worker-prompts.md`
> 크기: `**C`(며칠). 일감 하나 = 일꾼 한 세션. 일감이 끝나면 그 자리에서 아래 원장의 상태를 고친다. 막히면 `BLOCKED` + 까닭을 적고 다음 일감으로 간다.
> 일꾼 모델은 Opus. 깊이(effort)는 이 계획이 정했다(3절). 일꾼은 git 쓰기 명령을 하지 않는다 — 커밋 · 합치기는 본 세션(메인)이 확인한 뒤 한다.

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
| A | T1 | W1 | 바탕 약속 — 새 표 셋 + 마이그레이션, ERP 물건 목록 · 읽기 도구, 할 일 목록(선언), AI 직원 목록(선언), 쓰인 곳 기록 도우미 | xhigh | `foms-s-foms-graft`(같이 씀) | — | PENDING |
| A | T2 | W2 | 새 화면 틀 — 스위치 모듈, `foms-ds.css` 가두어 싣기, 혼자 서는 문서 틀 · 위 줄 · 폰 아래 탭, `/brain` 길 갈림, 빈 화면 여섯, 화면 찍기 도구 | high | `foms-s-foms-graft`(같이 씀) | — | PENDING |
| B | T3 | W3 | 승인 대기(지식 고침) 새 화면 + 다시 확인 · 판 · 폰 승인(⑥ · ⑫ 의 지식 쪽) | xhigh | `foms-s-foms-graft` | T2 | PENDING |
| B | T6 | W6 | 읽기 엔진 — 물어보기 ERP 읽기, 온톨로지 ERP 칸, 쓰인 곳 API, 내 질문 목록 | xhigh | 따로 `foms-s-graft-read` | T1 · T2(스위치) | PENDING |
| B | T7 | W7 | 할 일 엔진 — 제안 생명주기 · 실행기 · 시공 메모 쓰기 · 승인 대기 API · 권한 · 감사 | max | 따로 `foms-s-graft-actions` | T1 · T2(스위치) | PENDING |
| C | T4 | W4 | 찾기 · 지식 표 · 지식 카드 새 화면 + 쓰인 곳(⑦ · ⑧) | high | `foms-s-foms-graft` | T2 · T6 | PENDING |
| C | T5 | W5 | 물어보기 · 온톨로지 새 화면 + ERP 읽기 답 · ERP 물건 · 할 일 종류(⑨ · ⑩) | high | `foms-s-foms-graft` | T2 · T6 | PENDING |
| C | T8 | W8 | AI 제안 화면 조각 — 승인 대기 ERP 칸 · 옆 창 · 폰 카드(⑥ · ⑫) + PC · 태블릿 · 폰 분홍 칸(② ③ ④) | high | `foms-s-foms-graft` | T3 · T7 | PENDING |
| D | T9 | W9 | 상담 AI 접목 — 근거 남기기 · 규칙 제안 · 채널톡 작은 창 두 줄(⑤) | xhigh | 따로 `foms-s-graft-cs` | T1 · T7 | PENDING |
| D | T10 | W10 | AI 직원 — 수준 표 · 승인율 · 실행 기록 · 훑기 규칙 · 밤 단계 · AI 직원 화면(⑪) | high | 따로 `foms-s-graft-staff` | T1 · T2 · T7 | PENDING |
| E | T11 | R1 | 검수(읽기만) — 설계서 맞춤 · 보안 · 품질 | xhigh | `foms-s-foms-graft`(읽기만) | T1 ~ T10 | PENDING |
| E | T12 | V1 | 합친 뒤 확인 — 명령 전부 · 스위치 끔 견주기 · 핀 · 머리 하나 · 소유 표 | high | `foms-s-foms-graft` | T11 고침 끝 | PENDING |

- 물결마다 일꾼 수: A 2 · B 3 · C 3 · D 2 · E 2(차례로). 모두 12.
- D 물결은 C 물결에 기대지 않는다. 한도 · 검수 여유가 있으면 C 와 같이 돌려도 된다(그때 다섯).
- 깊이를 고른 까닭은 지시문 문서의 일꾼마다 한 줄. low · medium 은 없다 — 모든 일감이 "지금 기능은 그대로 + 새 약속을 지킴" 둘을 같이 봐야 해서다.

## 3. 파일 주인 (같은 물결 안에서 겹치지 않는다)

새 파일은 주인이 만든다. 남의 파일을 고쳐야 하면 고치지 말고 보고서에 "누구 파일의 어디를 어떻게"를 적는다.

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

T7 이 `registry.py`(T1 것)에 `check` · `preview` · `verify` 함수를 이어야 하면 `registry.py` 는 고치지 않고 `preview.py` 의 이름 → 함수 표로 잇는다.

### 물결 C

| 일감 | 가진 파일 |
|---|---|
| T4 | `templates/brain/ds/search.html` · `item.html` · `partials/search_*.html` · `partials/item_*.html` · `static/js/brain/ds/ds-search*.js` · `ds-item*.js` · `static/css/contexts/brain/ds/brain-ds-search.css` · `brain-ds-item.css` · `tests/domains/test_brain_ds_search.py` · `test_brain_ds_item.py` |
| T5 | `templates/brain/ds/ask.html` · `onto.html` · `partials/ask_*.html` · `partials/onto_*.html` · `static/js/brain/ds/ds-ask*.js` · `ds-onto*.js` · `static/css/contexts/brain/ds/brain-ds-ask.css` · `brain-ds-onto.css` · `tests/domains/test_brain_ds_ask.py` · `test_brain_ds_onto.py` |
| T8 | `templates/brain/ds/partials/inbox_erp_*.html` · `static/js/brain/ds/ds-inbox-erp*.js` · `static/css/contexts/brain/ds/brain-ds-inbox-erp.css` · `static/js/foms/graft-cells.js` · `static/css/components/foms-graft-cells.css` · `templates/orders/partials/tablet_sheet_ai_proposal.html`(새) · 고침: `templates/orders/partials/dashboard_grid.html` · `tablet_workqueue_grid.html` · `tablet_dashboard_sheet.html` · `dashboard_mobile_tower.html` · `templates/partials/shared/layout_nav.html` · `foms_tablet_rail.html` · `foms_side_tab.html` · `layout_head.html`(한 줄) · `layout_scripts.html`(한 줄) · `foms/web/orders/dashboard.py`(상세 조각 값) · `foms/web/brain.py`(ERP 제안만 보는 사람) · `tests/domains/test_graft_cells.py` · `test_brain_ds_inbox_erp.py` · 지금 계약 시험 가운데 이 고침에 닿는 것 |

### 물결 D

| 일감 | 가진 파일 |
|---|---|
| T9 | `foms/services/cs_agent/graft_step.py`(새) · `graft_settings.py`(새) · 고침: `drafting.py`(부르는 줄만) · `settings.py`(등록 줄만) · `send_view.py` · `wam_functions.py` · `send_flow.py`(꼭 필요할 때만) · `foms/api/channel/channel_functions.py`(실행기 표를 넘기는 줄 — 필요할 때만) · `foms/web/cs_draft_wam.py` · `templates/cs/cs_agent_wam.html` · `static/js/cs-agent/wam-graft.js`(새) · `wam-draft.js` · `static/css/contexts/cs/cs-wam.css` · `tests/domains/test_cs_graft_step.py` · `test_cs_wam_graft.py` · 지금 작은 창 시험 가운데 닿는 것 |
| T10 | `foms/services/ai_staff/levels.py` · `metrics.py` · `runs.py` · `sweeps.py` · `views.py` · `foms/api/ai_staff.py` · `foms/platform/blueprints.py` · `docs/harness/foms_order_mutation_policy_manifest.json` · `tools/cron/erp_actions_expire.py` · `tools/cron/ai_staff_sweep.py` · `tools/cron/nightly.py` · `templates/brain/ds/agents.html` · `partials/agents_*.html` · `static/js/brain/ds/ds-agents*.js` · `static/css/contexts/brain/ds/brain-ds-agents.css` · `tests/domains/test_ai_staff_levels.py` · `test_ai_staff_sweeps.py` · `test_ai_staff_api.py` · `test_brain_ds_agents.py` · `tests/security/test_ai_staff_access.py` |

### 아무도 고치지 않는 것 (고쳐야 하면 BLOCKED 로 보고)

`tests/harness/file_size_baseline.json` · `tests/contracts/runtime/layer_dependency_baseline.json` · `INLINE_STYLE_RATCHET` 값 · `static/css/foundation/foms-tablet-bundle.css` 와 그 핀 · 옛 회사 지식 화면 파일(`templates/brain/*.html` · `templates/brain/partials/*` · `static/js/brain/*.js` · `static/css/contexts/brain/brain.css`) · `CLAUDE.md` · `AGENTS.md` · `docs/AI_STATUS.md`(메인이 끝에 고친다).

## 4. 워크트리 · 합치기 (메인이 한다)

1. **물결 A · C 의 화면 일꾼은 `c:\tmp\foms-s-foms-graft` 를 같이 쓴다**(파일이 겹치지 않는다). 같은 자리에서 여러 일꾼이 시험을 돌리므로 일꾼은 `-n`(여러 일손) 없이 자기 시험 파일만 돈다. 남이 편집하는 중이라 `APP_OK` 가 잠깐 깨질 수 있다 — 오류 글의 파일이 내 것이 아니면 1분 뒤 다시 돌린다.
2. **파이썬을 많이 고치는 일꾼(T6 · T7 · T9 · T10)은 따로 워크트리**. 까닭: 만들다 만 블루프린트 · import 가 남의 `APP_OK` 확인을 깨뜨린다.
   - 만들기(메인): `cd /c/DEV/FOMS && python tools/harness/session_worktree.py create --name graft-read`(→ `c:\tmp\foms-s-graft-read`, 가지 `session/graft-read`). 이 도구는 `origin/deploy` 에서 가지를 딴다 — 앞 물결 커밋이 없다. 만든 직후(자기 커밋이 없을 때) `cd /c/tmp/foms-s-graft-read && git reset --hard session/foms-graft` 로 바탕을 맞춘다.
   - 이름: T6 `graft-read` · T7 `graft-actions` · T9 `graft-cs` · T10 `graft-staff`.
   - 워크트리에는 메인 트리의 커밋 안 한 파일이 없다. 목업 · 설계서 · 계획서는 물결 A 전에 `session/foms-graft` 에 커밋해 둔다(T0).
   - 워크트리에서는 alembic · 개발 서버 시작 DDL 이 막혀 있다. 마이그레이션은 파일과 시험으로만 확인한다.
3. **일감 하나를 닫는 차례(메인)**: 일꾼 보고서 → `git status --short` 로 가진 파일 밖을 건드렸나 → 완료 명령을 메인이 다시 돈다 → 판과 화면 그림을 본다(화면 일감) → 경로를 적어 커밋(`git commit -F <글 파일> -- <경로…>` — 한글 글은 UTF-8 파일로) → 따로 워크트리였으면 `cd /c/tmp/foms-s-foms-graft && git cherry-pick <커밋…>` → 원장 상태 `DONE` + 커밋 번호.
4. **물결 사이**: 다음 물결 일꾼을 띄우기 전에 `session/foms-graft` 에서 `python -c "import app; print('APP_OK')"` 와 그 물결까지의 새 시험을 한 번 돈다.
5. **`deploy` 푸시 · 운영 반영은 이 계획의 일이 아니다.** 사용자가 말하면: `git fetch` 뒤 `origin/deploy` 위로 다시 올리기 → T12 다시 → `scripts/ops/pre_push_smoke.ps1` 이 0 으로 끝난 뒤에만 `git push origin HEAD:deploy`(`smoke && push` 로 묶는다) → CI 초록 → 스테이징에서 스위치를 QA 계정에만. 운영은 사용자가 따로 말할 때만 이 세션 커밋만 골라 PR.

## 5. 한 줄짜리 같이 쓰는 자리 — 주인 하나

| 자리 | 주인 |
|---|---|
| 루트 `models.py` 끝 import 한 줄 | T1 |
| 마이그레이션(하나뿐 — `graft_00`, `down_revision = 'prodpart_00'`) | T1. 합칠 때 `origin/deploy` 에 새 마이그레이션이 생겼으면 메인이 `down_revision` 을 새 머리로 고치고 T1 시험을 다시 돈다(머리는 하나) |
| `foms/platform/blueprints.py` 등록 · 길 목록 JSON(`guard_count` 포함) | 물결 B 는 T7, 물결 D 는 T10 |
| `foms/web/brain.py` | 물결 A 는 T2, 물결 C 는 T8 |
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
| T4 | `python -m pytest tests/domains/test_brain_ds_search.py tests/domains/test_brain_ds_item.py tests/domains/test_brain_screens_js.py tests/domains/test_brain3d_js.py tests/domains/test_brain_around.py -q` + 화면 대조 ⑦ · ⑧ |
| T5 | `python -m pytest tests/domains/test_brain_ds_ask.py tests/domains/test_brain_ds_onto.py tests/domains/test_brain_chat_js.py tests/domains/test_brain_ontology_view.py -q` + 화면 대조 ⑨ · ⑩ |
| T8 | `python -m pytest tests/domains/test_graft_cells.py tests/domains/test_brain_ds_inbox_erp.py tests/domains/test_tablet_dashboard_sheet_contract.py tests/domains/test_tablet_rail_contract.py tests/domains/test_tablet_t2_contract.py tests/domains/test_nav_badge_lazy_count.py tests/domains/test_brain_fix_menu_query_count.py tests/domains/test_layout_header_mobile_overlap.py tests/visual/test_p1_mockup_structure.py tests/performance/test_perf_regression_guard.py tests/security/test_brain_ds_access.py -q` + 화면 대조 ⑥(AI 할 일 제안 칸 · 옆 창) · ⑫ · ② ③ ④(분홍 칸 자리와 글) + 색 차 재기 결과 |
| T9 | `python -m pytest tests/domains/test_cs_graft_step.py tests/domains/test_cs_wam_graft.py tests/domains/test_cs_wam_draft.py tests/domains/test_cs_wam_send.py tests/domains/test_cs_handoff_send.py tests/domains/test_cs_order_lookup.py -q` + 화면 대조 ⑤ |
| T10 | `python -m pytest tests/domains/test_ai_staff_levels.py tests/domains/test_ai_staff_sweeps.py tests/domains/test_ai_staff_api.py tests/domains/test_brain_ds_agents.py tests/security/test_ai_staff_access.py tests/domains/test_nightly_cron_runner.py tests/contracts/runtime/test_cron_purge_wiring.py tests/domains/test_auth_enforcement.py -q` + 화면 대조 ⑪ |
| T11 | 검수 보고서(결함마다 `경로:줄` · 심각도 · 고칠 말). 메인이 받는 즉시 이 원장 7절에 옮긴다 |
| T12 | 지시문의 확인 명령 전부 + 스위치 끔 견주기 + 핀 · 머리 · 소유 표 대조. 전체 시험은 돌리지 않는다(푸시 직전 smoke 한 번이 맡는다) |

### 화면 대조 (판과 실제 화면을 나란히 읽기)

1. 판 그림은 1절의 `shots` 폴더에 있다(없으면 `shoot3.py` 로 다시 찍는다).
2. 화면 그림은 `screen_shot.py`(T2 가 만든다)로 찍는다: 시험용 앱(메모리 SQLite + 지어낸 자료) 안에서 그 주소를 그려 HTML 로 떨군 뒤, 서비스 워커를 막은 Playwright 로 1440×1000 과 390×844 를 찍는다. 운영 · 스테이징 · 실제 자료를 쓰지 않는다. 지어낸 자료에 실제 이름 · 전화 · 주소를 넣지 않는다.
3. 일꾼은 두 그림을 읽고 다른 곳을 적는다 — 자리(위 줄 · 왼쪽 · 가운데 · 오른쪽) · 순서 · 글 · 색 갈래 · 빠진 칸 · 더 생긴 칸. 자료가 달라서 생긴 차이(수 · 이름)는 빼고 적는다.
4. 문지기는 구조 시험이다. 그림 대조는 보고서 거리이고, 메인이 닫을 때 한 번 더 본다.
5. 지금 화면의 분홍 칸(② ③ ④ ⑤)은 지금 화면 조각을 시험용 앱에서 그려 "그 칸이 그 자리에 그 글로 있나"만 본다. 목업의 `foms-now.css` 흉내와 지금 화면이 다른 것은 차이가 아니다.

## 7. 검수 결함 원장 (T11 뒤 메인이 채운다)

| 번호 | 심각도 | 어디 | 무엇 | 맡은 일감 | 상태 |
|---|---|---|---|---|---|
| — | — | — | 아직 없음 | — | — |

## 8. 준비 (T0 — 메인, 일꾼을 띄우기 전)

- [ ] 사용자에게 설계서 11절 결정 일곱을 보여 주고 기본값으로 갈지 확인받는다(질문 창 안에 설명을 넣어 한글로). 답을 `docs/harness/policy/DECISIONS.md` 에 D206 부터 적는다.
- [ ] `docs/design/mockups/foms-graft/` · `docs/plans/2026-11-13-foms-zero-rebuild-design.md` · 이 계획서 · 설계서 · 지시문을 `session/foms-graft` 에 커밋한다(따로 워크트리가 이 파일들을 봐야 한다).
- [ ] `git fetch origin` 뒤 `origin/deploy` 가 `01d596f7f` 에서 얼마나 나갔는지 본다. 마이그레이션 머리(`python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())"`)가 `prodpart_00` 이 아니면 T1 지시문의 `down_revision` 을 고쳐서 넘긴다.
- [ ] 판 그림 12장이 1절 폴더에 있는지 본다.

## 9. 끝난 뒤 (메인)

- `docs/AI_STATUS.md` '진행 중'에 한 줄(위 4,000자 예산 안) · `docs/AI_CHANGELOG.md` 기록.
- 스테이징에서 켜는 차례: `FOMS_GRAFT_BRAIN_UI` → `FOMS_GRAFT_ERP_READ` → `FOMS_GRAFT_ACTIONS` → 칸 스위치 → 상담 관리 칸 → `FOMS_GRAFT_PROPOSERS`. 단계마다 QA 계정으로 화면을 직접 본다. 스테이징 영발방은 실제 직원 방이고 알림톡은 실제로 나간다 — 알림톡 할 일은 스테이징에서 승인하지 않는다.
- Railway env 는 서비스마다 따로다. 화면 스위치는 web, `FOMS_GRAFT_PROPOSERS_ENABLED` 는 밤 단계가 도는 서비스에.
