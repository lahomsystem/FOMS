# FOMS 접목판 — 일꾼 지시문 (2026-11-14)

> 설계서 `docs/specs/2026-11-14-foms-graft_SPEC.md` · 계획 · 원장 `docs/plans/2026-11-14-foms-graft-plan.md`
> 쓰는 법: 아래 `## W<번호>` 한 칸을 통째로 그 일꾼에게 붙여 넣는다. 일꾼 모델은 Opus, 깊이는 칸 머리에 적힌 값.
> 일꾼은 이 문서의 0절(공통 규칙)을 먼저 읽는다 — 칸마다 가장 중요한 줄은 다시 적어 두었다.
> **판 2(11-14 사용자 결정 D206 ~ D212 반영)** — 새 칸 넷: W11(T13 특성 시험) · W12(T14 처리기 떼어 내기 + 실행기) · W13(T15 시공일 알림톡 + 폰 알림) · W14(T16 상담 AI 평가). 고친 칸: W2 · W7 · W8 · W9 · W10 · R1 · V1. W1 · W2 는 처음 판 지시문으로 이미 도는 중이다(11-14).

## 0. 공통 규칙 (모든 일꾼)

**자리 · git**
- 편집 전에 `cd <내 워크트리> && pwd` 로 자리를 확인한다. 셸은 Git Bash, 명령마다 `cd <워크트리> && …`(턴이 바뀌면 자리가 되돌아간다). 한글 출력은 UTF-8(`PYTHONIOENCODING=utf-8`).
- **git 쓰기 명령 금지**(`add` · `commit` · `push` · `reset` · `checkout` · `stash` · `rebase` …). 읽기(`status` · `diff` · `log`)만. 커밋 · 합치기는 메인이 한다.
- 운영 · 스테이징에 닿지 않는다(DB · 열쇠 · 앱 주소로 가는 네트워크 호출 금지). alembic 실행 · 개발 서버 시작 DDL 도 하지 않는다(워크트리에서 막혀 있다).
- 계획서 3절의 **내 파일만** 고친다. 남의 파일을 고쳐야 하면 고치지 말고 보고서에 "누구 파일 · 어디 · 어떻게"를 적는다.
- 기존 파일은 CRLF 다. Edit 도구로 고치면 그대로 남는다. 파일을 통째로 다시 쓰는 스크립트로 줄 끝을 바꾸지 않는다.
- 새 패키지를 설치하지 않는다. 꼭 필요하면 이름 · 까닭을 보고하고 멈춘다.
- 워크트리를 같이 쓰는 물결에서는 남이 편집하는 중이라 `APP_OK` 나 남의 시험이 잠깐 깨질 수 있다. 오류 글의 파일이 내 것이 아니면 1분 뒤 다시 돌리고, 계속 깨지면 고치지 말고 보고한다.

**코드**
- 파이썬: 새 함수는 50줄 아래 · 한 가지 일 · docstring(목적 · 인자 · 돌려주는 값) · 타입 힌트. 맨 `except:` 금지(예외를 삼키려면 로그에 코드를 남긴다). 새 파이썬 파일은 500줄 아래, 새 JS 파일은 300줄 아래(`tests/harness/test_file_size_ratchet.py` — 기준선 파일을 고치지 않는다).
- 층 방향: services → api · services → web · api → web 의 **새 import 금지**, 함수 안에서 하는 지연 import 도 늘리지 않는다(`tests/contracts/runtime/test_layer_dependency_ratchet.py`). 기준선을 다시 만들지 않는다.
- API 응답은 `{'success', 'data', 'error'}`. 오류 글은 코드가 정한 말만. 사람마다 다른 답은 `Cache-Control: private, no-store`.
- `structured_data`(JSONB) 고치기: `copy.deepcopy` → 고침 → 다시 대입 → `flag_modified(order, 'structured_data')` → 커밋.
- 날짜는 `get_today_kst()`(`date.today()` 금지 — CI 는 UTC 라 밤에 깨진다). PostgreSQL 에서 한글 정렬은 `COLLATE "C"`.
- 프런트: jQuery 금지. `fetch` 는 try/catch + `data.success` 확인(회사 지식 화면은 `static/js/brain/brain-dom.js` 의 `getJson` · `postJson` 한 곳). Jinja → JS 값은 `data-*` + `safeJsonParse`. 글은 `textContent` 로만 넣는다. `<script>` 는 `defer`, 바깥 CDN 스크립트를 더하지 않는다. 조각이 다시 실려도 전역 듣개는 한 번만(`window.__FOMS_…_BOUND`).
- **인라인 스타일 금지** — 템플릿 · JS 에 `style="` 글자를 한 번도 쓰지 않는다(`INLINE_STYLE_RATCHET` 은 templates + static 의 `.html` · `.js` 안 `style="` 개수를 센다). 목업의 `style="…"` 는 CSS class 로 옮긴다. 너비처럼 값이 바뀌는 것은 `<progress>` 요소나 JS 의 `el.style.setProperty(…)` 로.
- 새 정적 파일은 `{{ asset_url('…') }}` 로 싣는다(내용 지문 핀 — 손으로 올릴 `?v=` 가 없다). 손 핀이 박힌 기존 파일을 고치면 핀을 올리고 `grep -rn "<옛 핀>" tests templates` 로 베낀 곳도 같이 고친다. CSS 안 `@import` 를 새로 쓰지 않는다.
- 새 글자 크기는 `calc(Npx * var(--foms-fs, 1))`(새 화면은 `--fs` 토큰). PC 글자 · 단추를 줄이지 않는다(사장님은 PC 를 80% 배율로 쓴다). 상태 배지는 무채색 금지 — 나란한 색끼리 색 차(ΔE2000) 10 이상.
- 목업에 없는 칩 · 상자 · 요약을 더하지 않는다. 화면 글은 쉬운 한글 · 같은 말 한 번 · 기계 말 금지. 한글 문장에 한자를 쓰지 않는다.

**자료 · 시험**
- 저장소가 공개다. 코드 · 시험 · 문서에 실제 손님 · 직원 이름, 전화, 주소, 금액, 열쇠를 적지 않는다. 시험 자료는 지어낸 값.
- 시험은 절대 바깥으로 보내지 않는다 — 알림톡 · 채널톡 · 푸시 · 모델 호출은 가짜로 바꿔 끼운다.
- 시험이 `docs/` 아래 파일을 읽지 않게 한다(읽으면 CI 문서 서브셋에 올려야 한다). 목업 파일과 견주는 시험을 만들지 않는다.
- **전체 시험을 돌리지 않는다.** 내 완료 명령 + `grep -rl <바꾼 파일 이름> tests` 로 나온 시험만, `-n` 없이.
- 스위치가 꺼졌을 때 **지금과 똑같다**는 시험을 꼭 둔다.
- 문제를 만나면 원인을 찾아 고친다. 오류 숨기기 · 조건문으로 피해 가기 · "나중에" 주석은 내지 않는다. 못 고치면 `BLOCKED` + 까닭 + 재현 명령을 보고한다.

**보고(마지막 글 — 한글)**
1. 바꾼 · 만든 파일 목록(절대 경로)과 파일마다 한 줄. 2. 완료 명령과 출력 원문(마지막 줄까지). 3. 화면 일감이면 판 그림 · 화면 그림 경로와 다른 곳 목록. 4. 설계서와 다르게 한 것과 까닭. 5. 못 끝낸 것 · `BLOCKED` · 남의 파일에 필요한 고침. 6. 설계서 · 목업이 코드와 달랐던 곳(`경로:줄`).

---

## W1 — T1 바탕 약속 (물결 A)

> 11-14: 처음 판 지시문으로 도는 중. 할 일 목록의 `advance_stage` · `assign_draftsman` · `move_measurement` 는 여기서 `link` 로 선언되고, T14(W12)가 `run` 으로 바꾼다. 넣을 값 꼴 `users` · `flag` 와 할 일 `send_construction_alimtalk` 은 T14 · T15 가 더한다.

- 모델 Opus · 깊이 **xhigh** — 뒤 일꾼 아홉이 이 이름 · 표 꼴을 믿고 따로 만든다. 마이그레이션은 되돌리기 비싸다.
- 워크트리 `c:\tmp\foms-s-foms-graft`(W2 와 같이 쓴다 — 파일은 겹치지 않는다).

**먼저 읽기**: 이 문서 0절 · 설계서 2절 · 3.1 ~ 3.4 · 3.10 · 3.11 · `AGENTS.md` · `foms/persistence/brain/models.py`(꼴 본보기) · `migrations/versions/brain_02_chat_usage.py`(마이그레이션 본보기) · `tests/domains/test_brain_store.py:300` 부근(ORM 과 마이그레이션 견주기 · 머리 하나) · `foms/services/cs_agent/order_block.py`(허용 목록 읽기 본보기) · `foms/services/brain/actions.py`(이름 있는 액션 목록 본보기) · `foms/services/orders/order_mutation_policy.py` 의 `POLICY_REGISTRY`.

**만들 것(내 파일 — 계획서 3절 물결 A)**
1. `foms/persistence/graft/models.py` — ORM 셋 `ErpActionProposal`(`erp_action_proposals`) · `BrainUsageEvent`(`brain_usage_events`) · `AiAgentRun`(`ai_agent_runs`). 칸 · 색인 · 검사는 설계서 3.4 그대로. FK 없음. JSON 칸은 회사 지식 모델과 같은 꼴(`JSON().with_variant(JSONB, 'postgresql')`). 부분 유일 색인은 `postgresql_where` · `sqlite_where` 둘 다. services 를 import 하지 않는다. 루트 `models.py` 끝에 회사 지식 모델을 올리는 줄과 같은 꼴로 한 줄만 더한다.
2. `migrations/versions/graft_00_action_proposals_usage_runs.py` — `revision = 'graft_00'`, `down_revision = 'prodpart_00'`(메인이 다른 값을 줬으면 그 값). `COLUMNS` · `CHECKS` · `INDEXES` 표를 두는 `brain_02` 꼴. `models` 를 import 하지 않는다. 빈 표 더하기만, `downgrade()` 는 표 셋을 지운다.
3. `foms/services/erp_ontology/objects.py` — 물건 종류 10개 목록(`OBJECT_TYPES` — 코드 이름 · 화면 이름 · 정본 자리 · 읽기 도구가 있나 · 가림)과 주문 속성 표(`ORDER_PROPS` — 설계서 3.2 의 '실제 정본' 칸 그대로). 선언만(DB 를 읽지 않는다).
4. `foms/services/erp_ontology/read.py` — `OrderCard` · `Visit`(frozen dataclass) · `order_card(order)` · `visits(order)` · `prompt_lines(card, visits)` · `order_key(order_id)`(`'erp:order/<번호>'`) · `ALLOWED_FIELDS`. 납작 칸을 먼저 읽고(`erp_stage_code` · `erp_stage_updated_at` · `erp_measurement_date` · `erp_construction_date` · `shipping_scheduled_date` · `is_regional` · `is_self_measurement` · `as_axis_status` · `erp_owner_team_code`), 시간대 · AS 방문 날 · 품목 이름만 `structured_data` 에서. 사람이 적은 글은 `foms.services.cs_agent.masking.require_masked` 를 지난 것만(걸리면 그 칸만 뺀다). `manager_label` 은 화면 전용 칸이고 `prompt_lines` 에는 넣지 않는다.
5. `foms/services/erp_actions/registry.py` — `Param` · `ActionSpec` · `ACTIONS`(설계서 3.3 표의 열 개 — 이름 · 화면 이름 · `policy_id` · `mode` · `level_cap` · `wraps` · `phone_ok` · `wam_inline` · `params`) · 상태 이름 상수 · `MODE_RUN` · `MODE_LINK` · `MODE_HUMAN` · `REJECT_CODES` · `REJECT_LABELS` · `FAILURES`(코드 → 화면 말: `ACTION_NOT_OPEN` · `ACTION_BASE_CHANGED` · `ACTION_PRECONDITION` · `ACTION_FORBIDDEN` · `ACTION_SHAPE` · `ACTION_FAILED`) · `parse_params(name, body)`(정한 칸만 · 꼴 검사 — 틀리면 칸 이름만 실은 오류) · `specs()` · `dedupe_key(action, order_id, params)`. 실행 · 미리 보기 함수는 넣지 않는다(T7 것).
6. `foms/services/ai_staff/registry.py` — `Agent` · `AGENTS`(다섯 — 설계서 3.10 표: 열쇠 · 화면 이름 · 아이콘 이름 · 도구 표 · 할 일과 처음 수준) · `proposer(key)`(`'agent:<열쇠>'`) · `agent_of(proposed_by)`. · `level_of(session, agent, action)`(`SystemSetting` 열쇠 `ai_staff_levels` 를 읽고, 없거나 꼴이 틀리면 처음 값 — 수준 0 은 '제안을 만들지 않음').
7. `foms/services/brain/usage_events.py` — `READERS = ('cs_draft', 'erp_action', 'chatbot')` · `record_uses(session, keys, reader, ref_kind, ref_id, now)`(겹친 키 한 번 · 50개까지 · 커밋은 부르는 쪽) · `uses_window(session, key, days)`(읽은 쪽마다 수) · `recent_uses(session, key, limit)` · `refs_of(session, ref_kind, ref_id)`(그 차례 · 제안이 쓴 키들).

**시험(내 파일)**: ORM ↔ 마이그레이션 칸 · 꼴 · 색인 · 검사 일치와 머리 하나(`test_graft_store.py`) · 읽기 도구가 이름 · 전화 · 주소 · 금액 · 메모를 어떤 값에도 싣지 않음(지어낸 값으로 채운 주문에서 모든 돌려준 글을 훑는다) · 가림에 걸리는 품목 이름은 빠짐 · 할 일 목록의 `policy_id` 가 모두 `POLICY_REGISTRY` 에 있음 · `mode = human` 은 넣을 값이 없음 · 처음 수준 ≤ `level_cap` · 수준 3 없음 · `dedupe_key` 가 같은 값이면 같고 다르면 다름 · 쓰인 곳 기록(겹친 키 · 창 · 최근 순서).

**함정**: `orders.status` · `orders.measurement_date` · `orders.customer_name` 을 정본으로 쓰지 않는다(설계서 3.2 · 9절) · 실측 시간은 예정 값이다 · 새 마이그레이션이 머리를 둘로 만들면 시험이 빨개진다 · `models.py` 는 한 줄만 · PostgreSQL 전용 문법을 ORM 에 그냥 쓰면 SQLite 시험 레인이 죽는다.

**확인 명령**
```
cd /c/tmp/foms-s-foms-graft && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-foms-graft && python -m pytest tests/domains/test_graft_store.py tests/domains/test_erp_ontology_read.py tests/domains/test_erp_actions_registry.py tests/domains/test_ai_staff_registry.py tests/domains/test_brain_usage_events.py tests/domains/test_alembic_single_head.py tests/domains/test_brain_store.py tests/domains/test_production_part_marks_model.py -q
cd /c/tmp/foms-s-foms-graft && python -m pytest tests/harness/test_file_size_ratchet.py tests/contracts/runtime/test_layer_dependency_ratchet.py -q
```
보고: 0절 꼴 + 내놓은 이름 목록(모듈 · 함수 · 상수 — 뒤 일꾼이 그대로 쓴다).

---

## W2 — T2 새 화면 틀 (물결 A)

> 11-14: 처음 판 지시문으로 도는 중. 사용자 결정 D212 로 **공지 확인 창도 싣는다** — 메인이 따로 알렸다(아래 4번에 적어 둠).

- 모델 Opus · 깊이 **high** — 꾸밈이 밖으로 새지 않게 가두는 일과 길 갈림이 정확해야 하지만 모양은 목업이 정해 준다.
- 워크트리 `c:\tmp\foms-s-foms-graft`(W1 과 같이 쓴다).

**먼저 읽기**: 이 문서 0절 · 설계서 4절 · 5절 · 계획서 6절 '화면 대조' · 목업 `docs/design/mockups/foms-graft/foms-ds.css` · `BInbox.dc.html` · `BPhone.dc.html`(틀 · 위 줄 · 아래 탭 — 마크업은 `<x-dc>` 안, 예시 값은 아래 스크립트의 `renderVals()`) · `foms/web/brain.py` 전부 · `templates/brain/index.html` · `templates/partner/layout.html`(혼자 서는 문서 본보기) · `templates/partials/shared/layout_head.html:16`(CSRF) · `:67` ~ `:153`(화면 크기 · 글자 배율 첫 그림 전 처리) · `:636` ~ `:660`(긴급 빨간 창 · 소켓) · `foms/services/feature_flags.py:106` · `foms/services/asset_urls.py`.

**만들 것**
1. `foms/services/graft_flags.py` — 이름 일곱(설계서 4절) · `enabled(name, user)`(사람별 — `is_enabled_for_user`) · `enabled_global(name)`(전역 켬만) · 짧은 이름 표. `actions` 는 `brain_ui` 도 켜진 사람만, 칸 셋은 `actions` 도 켜진 사람만 참. DB 를 읽지 않는다. 템플릿 전역 `graft_enabled('<짧은 이름>')` 을 `brain_web_bp.app_template_global` 로 올린다(`g.current_user`).
2. `static/css/contexts/brain/ds/foms-ds.css` — 목업 파일을 옮기되 설계서 5.1 의 **네 가지를 고친다**(`:root` → `.f-app` · `.st-*` → `.f-tag.st-*` · `.i-*` → `.f-i.i-*` · `--fs: var(--foms-fs, 1)`). 출처 줄은 남긴다. 목업 마크업의 class 이름은 그대로 쓸 수 있어야 한다.
3. `static/css/contexts/brain/ds/brain-ds-shell.css` — 틀 배치(class 머리 `fb-`) · 640px 아래 폰 규칙(위 줄 줄이기 · 아래 탭 넷 · 누르는 것 44px 이상).
4. `templates/brain/ds/layout.html` — 혼자 서는 문서. 싣는 것: `partials/shared/csrf_bootstrap.html` · 파비콘 · 매니페스트 · 긴급 빨간 창 받는 쪽(필요한 CSS · 스크립트 · 소켓 싣기 — `layout_head.html` 에서 필요한 줄만 골라 같은 주소 · 같은 핀으로) · 공지 확인 창(`partials/shared/notice_popup.html` 과 그 스크립트 — D212. 전역 꾸러미를 통째로 실어야만 뜨면 `BLOCKED` 로 보고) · FOMS 글자 배율 값(같은 저장 값 — 새 저장소를 만들지 않는다). 싣지 않는 것: Bootstrap · `erp-pro.css` · 전역 메뉴 · `layout_scripts.html`. 몸: `<div class="f-app f-shell">` + 위 줄(← FOMS · 회사 지식 · 승인 대기(수) · 찾기 · 물어보기 · 온톨로지 · AI 직원 · 찾기 칸 · 사람) + `{% block side %}` · `{% block main %}` · `{% block aside %}` + 폰 아래 탭(승인 · 찾기 · 물어보기 · 나). 스크립트: `brain-view.js` · `brain-dom.js` · `ds-shell.js` 뒤 `{% block scripts %}`. 화면별 CSS 는 `{% block page_styles %}`.
5. `templates/brain/ds/_macros.html` — 아이콘 · 칩 · 꼬리표 · 수 · 길잡이 줄 매크로.
6. 빈 화면 여섯(`inbox` · `search` · `item` · `ask` · `onto` · `agents`) — 틀을 물려받아 제목과 빈 화면 한 줄만. 뒤 물결이 통째로 바꾼다(이 가지는 다 끝나기 전에 밖으로 나가지 않는다).
7. `foms/web/brain.py` — 스위치가 켜진 사람은 새 템플릿, 꺼진 사람은 **지금 줄 그대로**. `TABS` 는 건드리지 않고 `DS_TABS = (*TABS, 'agents')` 를 따로 둔다. 주소 → 템플릿은 설계서 5.2 표. 새 화면에는 옛 화면과 같은 값 전부(`tmap` · `display` · `options` · `counts` · `actions` · `wide_bins` · `is_admin` · `chat_tab` … 카드 화면은 `card` · `current` · `props` · `propose` · `around` …) + `page` 를 넘긴다(뒤 일꾼이 파이썬을 안 고쳐도 되게). `agents` 탭은 ADMIN + 화면 여는 MANAGER 만, 그 밖 404. 권한 규칙(404 · 물어보기만 여는 직원 보내기)은 한 글자도 바꾸지 않는다.
8. `static/js/brain/ds/ds-shell.js` — 지금 탭 표시 · 위 줄 찾기 칸(→ `/brain?tab=search&q=`) · 폰 아래 탭 · 승인 대기 수(서버가 넣은 지식 수 + `data-badge-url` 이 있을 때만 그 주소의 `total` 로 고침). 틀에 `data-badge-url="/api/erp-actions/badge"` 는 `graft_enabled('actions')` 일 때만 넣는다(그 API 는 물결 B 에서 생긴다 — `url_for` 로 만들지 않는다).
9. 화면 찍기 도구 — 계획서 1절의 저장소 밖 자리에 `screen_shot.py`. 시험용 앱(메모리 SQLite · 지어낸 자료 · 스위치 켬)에서 주소를 그려 HTML 로 떨구고, 서비스 워커를 막은 Playwright 로 1440×1000 · 390×844 를 찍는다. 쓰는 법을 파일 머리에 적는다. Playwright 가 없으면 설치하지 말고 보고한다.

**시험**: `foms-ds.css` 의 모든 선택자가 `.f-` 로 시작하거나 `.f-app` 아래 · `:root` 없음 · 맨 태그 선택자 없음 · 이 파일을 가리키는 템플릿이 `templates/brain/ds/` 뿐 · `layout_head.html` 에 없음(`test_brain_ds_scope.py` — `docs/` 를 읽지 않는다) · 스위치 끔이면 옛 템플릿이 그려짐(지금 권한 시험 전부 그대로) · 켬이면 새 틀(위 줄 · 길잡이 · 본문 자리 · 인라인 스타일 0 · 자산이 `asset_url`) · 탭별 템플릿 · `agents` 권한 · 스위치 판정(끔 · 사람 목록 · `all` · 기대는 스위치).

**함정**: 옛 화면 파일은 한 줄도 고치지 않는다 · 메뉴는 DB 질의를 늘리지 않는다(`test_brain_fix_menu_query_count.py`) · 긴급 빨간 창이 혼자 서는 문서에서 안 뜨면 `BLOCKED` 로 보고(전역 꾸러미를 통째로 싣는 것으로 풀지 않는다) · 폰 화면은 FOMS 모바일 셸 안이 아니다.

**확인 명령**
```
cd /c/tmp/foms-s-foms-graft && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-foms-graft && node --check static/js/brain/ds/ds-shell.js
cd /c/tmp/foms-s-foms-graft && python -m pytest tests/domains/test_graft_flags.py tests/domains/test_brain_ds_scope.py tests/domains/test_brain_ds_shell.py tests/security/test_brain_ds_access.py tests/security/test_brain_screens_access.py tests/security/test_brain_fix_menu_nav.py tests/domains/test_brain_fix_menu_query_count.py tests/domains/test_brain_screens_assets.py tests/performance/test_perf_regression_guard.py "tests/harness/test_harness_drift_guard.py::test_inline_style_ratchet" tests/harness/test_file_size_ratchet.py tests/contracts/runtime/test_layer_dependency_ratchet.py -q
```
화면 대조: 빈 승인 대기 화면을 찍어 ⑥ 의 틀(위 줄 · 왼쪽 · 가운데 · 오른쪽)과 ⑫ 의 아래 탭 자리를 견준다. 보고: 0절 꼴 + 뒤 일꾼이 쓸 블록 · 매크로 · `data-*` 이름 목록 + 화면 찍기 도구 쓰는 법.

---

## W3 — T3 승인 대기(지식 고침) 새 화면 + 폰 (물결 B)

- 모델 Opus · 깊이 **xhigh** — 회사 지식에서 행동이 가장 많은 화면이다(묶음 · 표 승인 · 질문 카드 · 고쳐서 승인 · 폰 규칙). 하나도 잃지 않고 새 모양으로 옮겨야 한다.
- 워크트리 `c:\tmp\foms-s-foms-graft`.

**먼저 읽기**: 이 문서 0절 · 설계서 5.3 ~ 5.5 · W2 보고서(블록 · 매크로 이름) · 목업 `BInbox.dc.html` · `BPhone.dc.html` · 지금 화면 `templates/brain/partials/tab_inbox.html` · `tab_recheck.html` · `tab_releases.html` · `static/js/brain/brain-inbox.js` · `brain-inbox-card.js` · `brain-inbox-bins.js` · `brain-inbox-table.js` · `brain-inbox-question.js` · `brain-recheck.js` · `brain-releases.js` · `brain-review-view.js`(순수 계산 — 그대로 쓴다) · 시험 `tests/domains/test_brain_fix_inbox_js.py` · `test_brain_review_js.py`(지금 기능 목록이 여기 있다) · API `foms/api/brain_review.py`.

**만들 것(내 파일 — 계획서 3절 물결 B)**: `templates/brain/ds/inbox.html` + `partials/inbox_*.html` · `static/js/brain/ds/ds-inbox*.js`(파일마다 300줄 아래) · `brain-ds-inbox.css`.
- 왼쪽 길잡이: 모두(수) · 'AI 할 일 제안' 자리(T8 것 — 아래 약속) · 지식 고침 묶음 ① ~ ⑥(수 0 은 흐리게) · 점검(다시 확인 수 · 판 · 기록 · 나중에 볼 것 수) · 폰 안내 상자.
- 가운데: 제목 + 한 줄, 숫자 띠(오늘 결정할 것 · 어림 · AI 할 일 제안 · 지식 고침), 'AI 할 일 제안' 자리(T8), '지식 고침' 칸 — 묶음마다 한 줄(제목 · 수 · 설명 · 첫 장 미리 보기 · 어림 분 · [열기]) + '등급 A n개 모두 승인'. 묶음을 열면 그 묶음 카드만(주소 `?tab=inbox&bin=` 유지).
- 카드 · 결정: 승인 · 고쳐서 승인 · 거절 까닭 칩 · 나중에 · 기준 판 바뀜 경고 · 관문 결과 · 등급 B 확인 글 · ① ④ 표 한 장 승인(확인 창) · ③ 질문 카드 · AI 제안 주 상한 글 · `BRAIN_DOC_SYNC` 오류 글. 판정은 `brain-review-view.js` 의 함수를 부른다(같은 판정을 새로 쓰지 않는다).
- 보기: `?tab=recheck`(아직 맞음) · `?tab=releases`(판 목록 · 차이 · ADMIN 의 판 되돌리기 — 번호 확인 포함).
- 폰(640px 아래 — ⑫): '폰에서 승인 n' 카드(칸 하나 고침만) + 'PC 에서 볼 것 n' 접힘 + 안내. 카드를 누르면 이유 · 근거 · 거절.
- **T8 과의 약속(이름 그대로)**: ① `{% include "brain/ds/partials/inbox_erp_nav.html" ignore missing %}`(왼쪽 'AI 할 일 제안' 자리) ② `{% include "brain/ds/partials/inbox_erp_section.html" ignore missing %}`(가운데, 지식 고침 칸 위) ③ 오른쪽 `<aside class="f-aside" data-ds-inbox-aside hidden>` ④ 폰 카드 목록 `data-ds-phone-list` ⑤ `window.FOMS_DS_INBOX = { setCount(kind, n), openAside(node), closeAside(), isPhone() }`(`kind` 는 `'knowledge'` · `'actions'` — 숫자 띠와 '모두' 수를 다시 센다) ⑥ 화면이 준비되면 뿌리에 `ds:inbox-ready` 이벤트. T8 partial 이 없어도 화면이 온전해야 한다.

**시험**: 스위치 켬 + ADMIN 으로 `?tab=inbox` · `recheck` · `releases` 가 200 · 길잡이 · 숫자 띠 · 자리 표시 · 인라인 스타일 0 · 새 순수 함수 node 시험(숫자 띠 합 · 어림 · 묶음 줄 글) · 지금 순수 계산 시험이 그대로 초록 · 스위치 끔이면 옛 화면.

**함정**: 옛 스크립트 가운데 DOM 을 그리는 것은 옛 class 를 쓴다 — 싣지 말고 새로 그린다(순수 계산 파일만 싣는다) · 결정한 사람 · 등급 B 확인은 서버가 다시 본다(화면에서 건너뛰는 길을 만들지 않는다) · 빈 묶음 글(`''.split(' ')` 함정 — 지금 시험 F27) · 폰에서 승인할 수 없는 카드는 처음부터 접힘 칸(F05).

**확인 명령**
```
cd /c/tmp/foms-s-foms-graft && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-foms-graft && for f in static/js/brain/ds/ds-inbox*.js; do node --check "$f" || exit 1; done
cd /c/tmp/foms-s-foms-graft && python -m pytest tests/domains/test_brain_ds_inbox.py tests/domains/test_brain_ds_inbox_js.py tests/domains/test_brain_review_js.py tests/domains/test_brain_fix_inbox_js.py tests/domains/test_brain_inbox_boot_js.py tests/domains/test_brain_review.py tests/domains/test_brain_inbox_bins.py tests/security/test_brain_review_access.py "tests/harness/test_harness_drift_guard.py::test_inline_style_ratchet" tests/harness/test_file_size_ratchet.py -q
```
화면 대조: ⑥(지식 고침 쪽) · ⑫. 보고: 0절 꼴 + 지금 기능 목록에 하나씩 "옮김 · 어디"를 적은 표.

---

## W6 — T6 읽기 엔진 (물결 B)

- 모델 Opus · 깊이 **xhigh** — 손님 정보가 모델로 새지 않아야 하고, 답 속 날짜 · 숫자를 코드로 다시 확인해야 하며, 끄면 글자까지 지금과 같아야 한다.
- 워크트리 `c:\tmp\foms-s-graft-read`(따로 — 메인이 만들어 준다).

**먼저 읽기**: 이 문서 0절 · 설계서 3.2 · 3.7 · 3.8 · 7절 · W1 보고서(내놓은 이름) · `foms/services/brain/chat_answer.py` 전부 · `chat_prompt.py` · `chat_retrieve.py` · `chat_log.py` · `foms/api/brain_chat.py` · `foms/api/brain.py` · `foms/services/brain/ontology_view.py` · `ontology_cqs.py` · `usage.py` · `foms/services/cs_agent/order_find.py`(주문 번호 읽는 식) · `order_block.py`(주문 줄 머리말 · 규칙 본보기) · `foms/services/orders/order_mutation_policy.py:456`(`user_can_read_order`) · 시험 `tests/domains/test_brain_chat.py` · `test_brain_ontology_view.py`.

**만들 것(내 파일 — 계획서 3절 물결 B)**
1. `foms/services/erp_ontology/ask.py` — 질문에서 주문 번호 찾기(`#123` · `주문 123` · `주문번호 123` · `123번 주문`, 하나만) · 주문 읽기(삭제 · 초안 제외, `user_can_read_order` — 안 되면 없는 주문과 같은 결과) · `order_card` · `visits` · 모델에 줄 주문 줄 · 화면 값(`erp` 칸) · 도구 걸린 시간 재기.
2. 물어보기 길(`chat_answer.py` · `chat_prompt.py`) — `graft_flags.enabled('erp_read', user)` 이고 번호가 있고 읽을 수 있을 때만: 지시문에 주문 줄 칸을 더하고(차례 쪽에 — 앞부분 글은 그대로), 근거 키 목록에 `erp:order/<번호>` 를 넣고, `verify` 가 `kind = 'erp'` 답을 "근거에 주문 키가 있고 답 속 날짜 · 숫자가 주문 줄이나 근거 지식 글에 있음"일 때만 받아들인다. 그 밖은 지금 그대로('모름'). 기록: 근거 키에 주문 키 · `record_uses(..., reader='chatbot', ref_kind='question', ref_id=<질문 번호>)` · `ai_agent_runs` 한 줄(직원 `ask`, 단계 `mask.apply` · `erp.order.get` · `erp.visit.list` · `knowledge.search` + 걸린 시간). 답 값에 `kind` · `erp` 칸(설계서 3.7).
3. `GET /api/brain/chat/history` — 내가 물은 것만(오늘 · 지난 7일, 가린 글 앞 60자 · 모름 여부 · 주문 읽기 여부), 20줄까지.
4. 온톨로지(`ontology_view.py` · `foms/api/brain.py`) — `erp_read` 가 켜진 사람에게만 `erp` 칸(물건 종류 · 할 일 종류 · ERP 재료가 드는 질문 수)과 `GET /api/brain/ontology/erp/<종류>`(설계서 3.8). 능력 질문의 ERP 재료(`ERP_NEEDS`)는 읽기 도구가 있는 종류면 '있음'. 꺼진 사람의 답은 지금과 같다.
5. 쓰인 곳(`usage_view.py` + `GET /api/brain/items/<키>/usage`) — 지난 14일 읽은 쪽마다 수 · 최근 네 줄(가린 글만: 상담 차례 `masked_question` 앞부분 + 끝난 꼴, 제안 제목 + 상태, 물어보기 가린 질문) · 이어진 ERP 물건(적용 대상 제품 라인 → 그 품목 이름이 든 진행 중 주문 수는 **세지 않는다** — 색인 없는 글자 찾기가 된다. 공정 단계 → ERP 단계 이름 짝만).

**시험**: 번호 꼴마다 찾기 · 번호 둘이면 안 읽음 · 읽을 수 없는 주문은 없는 주문과 같은 답 · 프리랜서는 자기 주문만 · 모델에 간 글에 이름 · 전화 · 주소 · 금액이 없음(가짜 모델이 받은 글을 훑는다) · 주문 줄에 없는 날짜를 말한 답은 '모름' · 근거에 주문 키가 없으면 '모름' · 일정 바꾸기 질문은 지금 잡힌 날만 · **스위치 끔이면 지시문 · 출력 틀 · 답이 지금과 글자까지 같음** · 내 질문 목록에 남의 질문이 없음 · 온톨로지 `erp` 칸이 끔이면 없음 · 쓰인 곳 수 · 순서 · 가린 글만 · 권한(화면을 못 여는 사람 404, 로그인 안 함 401).

**함정**: 가리기 **전** 원문에서 번호를 찾되 로그 · 기록에는 가린 글과 번호만 · `BrainUsage.reader` 검사 제약(`chatbot` · `cs_brain`)은 건드리지 않는다(새 기록은 `brain_usage_events`) · 모델 호출은 시험에서 가짜 · 층 방향(이 일감은 services 와 `foms/api/brain*.py` 만) · `chat_answer.py` 가 길어지면 새 모듈로 뺀다(500줄).

**확인 명령**
```
cd /c/tmp/foms-s-graft-read && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-graft-read && python -m pytest tests/domains/test_graft_ask_erp.py tests/domains/test_graft_onto_erp.py tests/domains/test_graft_usage_view.py tests/security/test_graft_read_access.py tests/domains/test_brain_chat.py tests/domains/test_brain_chat_audit.py tests/domains/test_brain_ontology_view.py tests/domains/test_brain_ontology_cq_props.py tests/domains/test_brain_d105.py tests/security/test_brain_chat_access.py tests/harness/test_file_size_ratchet.py tests/contracts/runtime/test_layer_dependency_ratchet.py -q
```
보고: 0절 꼴 + 새 · 바뀐 API 답의 실제 예(지어낸 값) — 물결 C 화면 일꾼이 그대로 쓴다.

---

## W7 — T7 할 일 엔진 (물결 B)

- 모델 Opus · 깊이 **max** — 이 일감만 실제 주문을 바꾸고 손님에게 글이 나갈 수 있다. 권한 · 한 번만 · 되맞추기가 틀리면 일정이 잘못 바뀐다.
- 워크트리 `c:\tmp\foms-s-graft-actions`(따로).

**먼저 읽기**: 이 문서 0절 · 설계서 3.3 ~ 3.6 · 3.11 · 7절 · W1 보고서 · `foms/services/orders/construction_schedule.py` 전부 · `foms/api/shipment/partner_request.py` 전부(감싼 길이 하는 차례 — 권한 → 줄 잠금 → 검사 → 쓰기 → 감사 → 커밋 → 알림 마무리) · `foms/services/orders/as_cycle_service.py:575` · `foms/api/cs/as_orders.py:564` ~ `:700` · `foms/services/kakao_alimtalk.py:879` · `foms/api/orders/measurement_visit.py`(같은 트랜잭션 감사 줄 본보기 `:90`) · `foms/services/orders/revision.py:241`(`lock_order_row`) · `:290` · `foms/services/orders/change_reason.py:175` · `:267` · `foms/services/orders/order_mutation_policy.py`(`evaluate_policy` · `user_can_read_order`) · `foms/api/brain_review.py`(답 꼴 · 404 규칙 본보기) · `foms/platform/blueprints.py` · `docs/harness/foms_order_mutation_policy_manifest.json` · 시험 `tests/domains/test_auth_enforcement.py`.

**만들 것(내 파일 — 계획서 3절 물결 B)**
1. `foms/services/erp_actions/preview.py` — 할 일 이름 → `check(order, params)` · `preview(order, params)` · `verify(order, params)` · `steps(order, params)` 표. `steps` 는 감싼 기능이 실제로 하는 일만. · `param_choices(action, param, order)`(고를 값 목록 — 없으면 빈 목록. `detail` 답의 `params[].choices` 가 이것을 쓴다). 뒤 물결의 T14 · T15 가 이 표에 할 일을 더한다 — 이름 → 함수 표 한 곳에 더하면 되게 짠다.
2. `foms/services/erp_actions/lifecycle.py` — `propose(session, *, action, proposed_by, order, params, reason, evidence, source_kind, source_ref, level, now) -> ErpActionProposal | None` · `approve(session, proposal_id, *, actor, runners, base_version, edits=None, reason_code=None, reason_note=None, view_ms=None, now) -> dict` · `reject(session, proposal_id, *, actor, code, view_ms, now)` · `snooze(session, proposal_id, *, actor, now)` · `expire_due(session, now) -> int` · `reconcile(session, now) -> int`. 설계서 3.4 '생명주기' 그대로(승인 두 걸음 · 409 셋 · 되맞추기 2분). 가린 글 검사를 못 넘는 글이면 만들지 않는다. `propose` 는 커밋하지 않는다(부르는 쪽이 커밋한다) — T15 가 뒤에 폰 알림 줄을 같은 트랜잭션에 더하고 커밋 뒤에 푸시를 줄 세운다.
3. `foms/services/erp_actions/runners.py` — `SERVICE_RUNNERS`: `schedule_construction` · `move_construction` · `schedule_as_visit` · `send_measure_alimtalk` · `add_construction_note`. 실행기는 감싼 길과 **같은 차례**를 탄다. 감사 줄은 `SecurityLog` 를 같은 트랜잭션에(`detail.source = 'erp_action:<번호>'`). 사유가 필요한 변경이면 승인 때 받은 사유를 지금 사유 원장에 남긴다. 알림톡 중복 막기 열쇠 `alimtalk:measure:<주문>:action:<제안 번호>`. 실행기 표도 이름 → 함수 표 한 곳이다(T14 가 api 쪽 표에 셋, T15 가 이 표에 하나를 더한다).
4. `foms/services/orders/construction_note.py` — 시공 메모 한 줄 더하기(새 쓰기 길). `write_construction_schedule` 과 같은 부품 · 같은 순서(깊은 복사 → 고침 → 대입 → `flag_modified` → 납작 칸 맞춤 → 변경 원장 → 도면팀 알림). 글은 가린 글 · 200자.
5. `foms/api/erp_action_runners.py` — `RUNNERS = {**SERVICE_RUNNERS, 'register_as': …}`(`register_as_from_payload` 를 부르고 그 답의 상태 · 코드를 결과로 옮긴다).
6. `foms/services/erp_actions/access.py` — `actions_viewer(user) -> bool`(켜진 내부 계정 + `actions` 스위치 + 통과하는 `policy_id` 가 하나라도) · `can_run(user, spec, order) -> bool`.
7. `foms/services/erp_actions/views.py` — `badge(session, user)` · `open_for_orders(session, user, order_ids) -> dict[int, dict]` · `inbox(session, user, now)` · `detail(session, user, proposal_id, now)`(2주 승인율 포함). 볼 수 없는 제안은 질의 단계에서 거른다.
8. `foms/api/erp_actions.py`(블루프린트 `erp_actions_api_bp`, 머리 `/api/erp-actions`) — 설계서 3.6 의 길 일곱. `foms/platform/blueprints.py` 에 등록 줄, 길 목록 JSON 에 쓰기 길 셋(`STAFF_MUTATION`) + `guard_count`.

**시험**: 생명주기 전부(만들기 · 겹침 · 거절된 것 다시 안 만듦 · 승인 · 두 번 누름 409 · 기준 판 바뀜 409 와 새 카드 · 막는 조건 409 · 실행 실패 → `failed` · 되맞추기 두 갈래 · 기간 끝남 · 나중에) · 실행기마다 감싼 함수가 그 값으로 불렸나(바깥 보내기는 가짜) · 시공 메모 쓰기(판 번호 · 변경 원장 · 깊은 복사) · 권한(정책 못 넘는 사람 · 프리랜서 남의 주문 · 협력사 · 로그인 안 함 · 스위치 끔 → 404 · 401, 수 · 칩 · 카드 0) · 감사 줄에 글 없음 · 길 목록 정합(`test_auth_enforcement.py`) · PostgreSQL 에서 부분 유일 색인과 동시 승인 한 번만(`tests/postgres/test_erp_actions_pg.py`).

**함정**: `mode = link` · `human` 은 승인 길로 실행되지 않는다(409 가 아니라 꼴 오류) · `send_alimtalk` · `register_as_from_payload` 는 스스로 커밋한다 — 그래서 두 걸음이다 · 시험에서 알림톡 · 푸시 · 채널톡은 절대 실제로 나가면 안 된다 · `foms.web.auth` 를 import 하지 않는다 · 본문의 사람 칸을 읽지 않는다 · 이미 지난 날짜 · `TIME_CHOICES` 밖 시간 · 삭제된 주문 · 승격 전 초안 주문 · 협력사 주문(희망 확정 길)을 가른다 · 감싼 길의 처리기 코드를 고치지 않는다.

**확인 명령**
```
cd /c/tmp/foms-s-graft-actions && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-graft-actions && python -m pytest tests/domains/test_erp_actions_lifecycle.py tests/domains/test_erp_actions_runners.py tests/domains/test_erp_actions_api.py tests/domains/test_construction_note.py tests/security/test_erp_actions_access.py tests/domains/test_auth_enforcement.py tests/harness/test_file_size_ratchet.py tests/contracts/runtime/test_layer_dependency_ratchet.py -q
cd /c/tmp/foms-s-graft-actions && grep -rl "construction_schedule\|partner_request\|as_cycle_service\|kakao_alimtalk" tests | head -30
```
세 번째 명령에 나온 시험 가운데 내가 닿은 모듈의 것을 돈다. PostgreSQL 레인이 로컬에 없으면 그 시험은 "CI 에서 확인"이라고 보고한다. 보고: 0절 꼴 + API 답의 실제 예(지어낸 값) + 실행기마다 "감싼 함수 · 남는 기록" 표.

---

## W4 — T4 찾기 · 지식 표 · 지식 카드 (물결 C)

- 모델 Opus · 깊이 **high** — 화면 둘을 옮기고 '쓰인 곳'을 붙인다. 판정은 지금 API · 지금 순수 계산이 한다.
- 워크트리 `c:\tmp\foms-s-foms-graft`.

**먼저 읽기**: 이 문서 0절 · 설계서 5.3 · 5.4 · 3.8 · W2 · W6 보고서 · 목업 `BSearch.dc.html` · `BItem.dc.html` · 지금 화면 `templates/brain/partials/tab_search.html` · `tab_table.html` · `templates/brain/item.html` · `partials/card_*.html` · `static/js/brain/brain-page.js` · `brain-table.js` · `brain-item-actions.js` · `brain-neighbours.js` · `brain3d-tab.js` · `brain-view.js` · 시험 `tests/domains/test_brain_screens_js.py`.

**만들 것(내 파일 — 계획서 3절 물결 C)**
- 찾기 · 표(`search.html` — ⑦): 왼쪽 유형 묶음 나무(묶음 · 유형 · 수) · 큰 찾기 칸 · 유형별 수 칩 · 거르기 여덟 · 표(이름 + 유형 + 표시 · 쓰는 팀 · 브랜드 · 상태 · 확실한 정도 · 등급 · 쓰인 횟수 · 마지막 확인 · 다시 볼 날) · 쪽 · 오른쪽 미리 보기(요약 · 값 · 쓰인 곳 · 연결된 지식 수 · [카드 열기] · [고칠 말 제안]). 찾는 말이 있으면 유형별 묶음 결과. 주소(`?tab=search&q=` · `?tab=table&type=…`)는 지금 그대로.
- 지식 카드(`item.html` — ⑧): 길 표시 · 머리(유형 · 이름 · 층 · 브랜드 · 상태 · 승인 대기 수정 · 보기 범위 · 글) · 탭(한눈에 · 수정 기록 · 연결된 지식 · 뇌 보기) · 속성 표 · 쓰인 곳 · 연결된 지식 · 오른쪽 수정 기록 + 제안 단추(고칠 말 · 옛 판 되돌리기 · 은퇴 · 지우기 — `POST /api/brain/proposals`, 액션 이름은 서버가 준 목록).
- 쓰인 곳: `graft_enabled('erp_read')` 일 때만 `GET /api/brain/items/<키>/usage` 를 불러 그린다. 꺼져 있으면 그 칸이 없다.
- 그림 위젯(이웃 지도 · 뇌 보기)은 **지금 partial · 지금 스크립트 · `brain.css` 를 그대로 싣는다** — 다시 그리지 않는다. 무거운 라이브러리는 그 탭을 열 때만.

**시험**: 스위치 켬에서 두 화면 200 · 자리 표시 · 거르기 값 · 인라인 스타일 0 · 새 순수 함수 node 시험 · 쓰인 곳 칸이 스위치 따라 있고 없음 · 볼 수 없는 카드 404 그대로.

**함정**: 표의 등급 · 상태 색은 무채색 금지 규칙을 지킨다(목업의 '초안 · 은퇴' 꼬리표가 회색이면 색 갈래를 골라 색 차를 재고 보고) · 진행 막대는 인라인 스타일 없이 · 고칠 말 제안은 바로 바꾸지 않는다(승인 대기로).

**확인 명령**
```
cd /c/tmp/foms-s-foms-graft && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-foms-graft && for f in static/js/brain/ds/ds-search*.js static/js/brain/ds/ds-item*.js; do node --check "$f" || exit 1; done
cd /c/tmp/foms-s-foms-graft && python -m pytest tests/domains/test_brain_ds_search.py tests/domains/test_brain_ds_item.py tests/domains/test_brain_screens_js.py tests/domains/test_brain3d_js.py tests/domains/test_brain_around.py "tests/harness/test_harness_drift_guard.py::test_inline_style_ratchet" tests/harness/test_file_size_ratchet.py -q
```
화면 대조: ⑦ · ⑧. 보고: 0절 꼴.

---

## W5 — T5 물어보기 · 온톨로지 (물결 C)

- 모델 Opus · 깊이 **high** — 화면 둘 + 새로 붙는 ERP 읽기 답 · ERP 물건 칸. 답 판정은 서버가 한다.
- 워크트리 `c:\tmp\foms-s-foms-graft`.

**먼저 읽기**: 이 문서 0절 · 설계서 3.7 · 3.8 · 5.3 · 5.4 · 9절 · W2 · W6 보고서 · 목업 `BAsk.dc.html` · `BOnto.dc.html` · 지금 화면 `templates/brain/partials/ask_panel.html` · `tab_onto.html` · `tab_map.html` · `static/js/brain/brain-ask.js` · `brain-ask-view.js` · `brain-ask-admin.js` · `brain-onto.js` · `brain-onto-view.js` · `brain-map.js` · 시험 `tests/domains/test_brain_chat_js.py`.

**만들 것(내 파일 — 계획서 3절 물결 C)**
- 물어보기(`ask.html` — ⑨, `/brain?tab=ask` 와 `/brain/ask` 둘 다): 왼쪽(새 질문 · 오늘 물은 것 · 지난 7일 — `GET /api/brain/chat/history` · 관리: 설정 · 빈 지식 · 틀림 신고는 ADMIN 만) · 가운데(안내 상자 · 물음과 답 · 근거 칩 · 확인 중 칩 · 확신 · 도움 됨 · 안 됨 · 틀림 · 모름이면 물어볼 팀 상자 · 묻기 칸 · 남은 수) · 오른쪽 '이 답이 읽은 것'(답에 `erp` 칸이 있을 때만: 주문 요약 · 방문 · 쓴 도구 · '읽기만' 안내). 설정 · 빈 지식 · 틀림 신고 기능은 지금 그대로.
- 온톨로지(`onto.html` — ⑩, `?tab=onto` · `?tab=map`): 왼쪽(찾기 칸 · 지식 유형 묶음 · ERP 물건 종류 · 정의: 연결 종류 · 할 일 종류 · 능력 질문) · 가운데(길 표시 · 머리 · 탭 · 속성 표 · 연결 · 할 일 · 질문) · 오른쪽 능력 질문(점수 · 막대 · ERP 재료 안내 · 아직 못 푸는 질문 · 모두 보기 · 정본 자리). ERP 물건 상세는 `GET /api/brain/ontology/erp/<종류>`. 유형 지도는 지금 partial · `brain-map.js` · `brain.css` 를 그대로 싣는 보기.
- ERP 칸은 API 답에 `erp` 가 있을 때만 그린다(없으면 지금 내용만).

**목업과 다르게 그릴 것(설계서 9절 — 코드가 정본)**: 주문 번호는 `#<번호>` · 단계 이름은 지금 여덟 + AS · 방문 줄에 팀 · 인원 · 사진 수 없음 · 속성 표의 '지금 칸'은 API 가 준 값 그대로.

**시험**: 두 화면 200(ADMIN · 물어보기만 여는 직원의 `/brain/ask`) · 자리 표시 · 인라인 스타일 0 · 새 순수 함수 node 시험(내 질문 목록 글 · ERP 답 옆 창 값) · `erp` 가 없는 답이면 옆 창이 안 뜸 · 스위치 끔이면 옛 화면.

**함정**: 막대는 인라인 스타일 없이 · 묻기 전에 가림을 거친다는 안내 글은 그대로 · 손님 이름 · 전화 · 주소를 화면이 다시 만들지 않는다(서버가 준 값만) · 무거운 그림 라이브러리는 지도 보기를 열 때만.

**확인 명령**
```
cd /c/tmp/foms-s-foms-graft && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-foms-graft && for f in static/js/brain/ds/ds-ask*.js static/js/brain/ds/ds-onto*.js; do node --check "$f" || exit 1; done
cd /c/tmp/foms-s-foms-graft && python -m pytest tests/domains/test_brain_ds_ask.py tests/domains/test_brain_ds_onto.py tests/domains/test_brain_chat_js.py tests/domains/test_brain_ontology_view.py tests/security/test_brain_chat_access.py "tests/harness/test_harness_drift_guard.py::test_inline_style_ratchet" tests/harness/test_file_size_ratchet.py -q
```
화면 대조: ⑨ · ⑩. 보고: 0절 꼴.

---

## W8 — T8 AI 제안 화면 조각 (물결 C)

- 모델 Opus · 깊이 **high** — 새 판정은 없지만 여러 사람이 같이 고치는 파일(전역 메뉴 · 머리 · 태블릿 계약 시험)과 캐시 함정을 지나야 한다.
- 워크트리 `c:\tmp\foms-s-foms-graft`.

**먼저 읽기**: 이 문서 0절 · 설계서 3.5 · 3.6 · 4절 · 6절 · 9절 · W3 보고서(자리 약속) · W7 보고서(API 예) · 목업 `BInbox.dc.html`(AI 할 일 제안 칸 · 오른쪽 '제안 자세히') · `BPhone.dc.html` · `NowPC.dc.html` · `NowTablet.dc.html` · `NowMobile.dc.html`(분홍 점선 `n-graft` 가 붙은 곳만 새 칸이다 — `foms-now*.css` 는 싣지 않는다) · `templates/orders/partials/dashboard_grid.html:104` · `tablet_workqueue_grid.html:66` · `tablet_dashboard_sheet.html:23` ~ `:37` · `dashboard_mobile_tower.html:147` · `templates/partials/shared/layout_nav.html:11` ~ `:60` · `foms_tablet_rail.html` · `foms_side_tab.html` · `foms/web/orders/dashboard.py:629` · `static/js/foms/fragment-loader.js`(조각이 실릴 때 쏘는 이벤트) · `static/js/foms/foms-nav-triage-badge.js`(그린 뒤 수 채우기 본보기).

**만들 것(내 파일 — 계획서 3절 물결 C)**
1. 승인 대기 ERP 칸(⑥ · ⑫): `templates/brain/ds/partials/inbox_erp_nav.html`(직원마다 수) · `inbox_erp_section.html`(카드 — AI 직원 표시 · 제목 · 때 · 근거 칩 · 칸 · 전 → 후 · [승인] · [자세히] · [거절], 셋까지 + 'n개 더 보기') · `ds-inbox-erp*.js` · `brain-ds-inbox-erp.css`. 오른쪽 '제안 자세히'(이유 · 근거 · 바뀌는 칸 표 · 승인하면 차례로 · 2주 승인율 · 승인 · 고쳐서 승인(넣을 값 칸) · 나중에 · 거절 까닭 칩). `mode = link` 카드는 [승인] 대신 [주문에서 처리]. 409 `ACTION_BASE_CHANGED` 면 새 카드를 보이고 "제안 뒤 주문이 바뀌었어요 — 다시 봐 주세요". 폰: `phone_ok` 카드만 [승인], 나머지는 'PC 에서 볼 것'. W3 의 `window.FOMS_DS_INBOX` 로 수 · 옆 창을 맞춘다. 넣을 값 칸은 꼴대로 그린다 — `date` · `time_slot` · `choice` · `masked_text` · `users`(여러 명 고르기 — 목록은 `params[].choices`) · `flag`(켜고 끄기). 꼭 있어야 하는 값이 비어 있으면 [승인]이 눌리지 않는다(도면 담당 맡기기는 승인자가 사람을 고른 뒤에만).
2. `foms/web/brain.py` — 회사 지식 화면은 못 열지만 `actions_viewer(user)` 인 사람: `/brain` · `/brain?tab=inbox` 가 새 승인 대기 화면을 **ERP 칸만** 보이게 연다(지식 칸 · 다른 탭은 지금처럼 없음). 그 밖 규칙은 그대로.
3. 분홍 칸: `static/js/foms/graft-cells.js` + `static/css/components/foms-graft-cells.css` — 설계서 6절 표. 템플릿에는 빈 자리만(`data-graft-slot="<주문 번호>"` · `data-graft-badge` · `data-graft-tile` — 모두 `hidden`), 스크립트가 `GET /api/erp-actions/badge` 한 번 + 보이는 주문 번호로 `GET /api/erp-actions/open` 한 번으로 채운다. 자리 자체는 `graft_flags.enabled_global(…)` 로만 가른다(사람별 값을 캐시되는 조각에 넣지 않는다).
4. 태블릿 오른쪽 AI 제안 상자: `templates/orders/partials/tablet_sheet_ai_proposal.html` + `foms/web/orders/dashboard.py` 의 상세 조각에 값 한 칸(`open_for_orders` — `cell_tablet` 이 켜진 사람만). 단추 셋(승인 · 고쳐서 → 승인 대기의 그 제안으로 · 거절 → 까닭 칩 한 번).
5. `layout_head.html` 에 CSS 한 줄 · `layout_scripts.html` 에 스크립트 한 줄(전역 스위치가 하나라도 켜졌을 때만 · `asset_url`).

**시험**: 전역 스위치 끔이면 템플릿 출력이 지금과 같음(자리도 없음) · 켬이면 자리가 정한 곳에 · 스크립트가 주문 번호를 한 번에 모아 부름 · 두 번 실려도 한 번만 묶임 · 메뉴 DB 질의 수 그대로 · 태블릿 계약 시험 · PC 머리 겹침 시험 · 구조 시험 · 성능 가드 · ERP 제안만 보는 사람의 화면(지식 칸 0 · 다른 탭 404) · 인라인 스타일 0.

**함정**: `foms-tablet-bundle.css` 와 그 핀은 건드리지 않는다(핀을 베껴 둔 시험이 다섯이다) · 태블릿 규칙은 `(min-width: 992px) and (orientation: landscape) and (pointer: coarse)` + `body.erp-mobile-v2-layout` 안에만 · 판 ③ 의 레일은 `foms_tablet_rail.html` 모양이다 — 태블릿 대시보드에서 실제로 어느 레일이 뜨는지 템플릿 include 조건을 읽어 확인하고 뜨는 쪽에만 붙인다 · `dashboard_grid.html` 에는 이미 인라인 스타일이 많다 — 하나도 더하지 않는다 · AI 칩 색(남보라)과 같은 칸의 '할 일' 배지 · 단계 배지의 색 차를 재서 보고(10 이상, 색약 흉내 뒤 6 이상) · 폰 칸은 수가 0 이면 숨김 · 목업의 '2팀 3명' · '폭 합 ÷ 300' 줄은 그리지 않는다(API 가 준 글만) · 여러 창이 같은 파일을 고친다 — 전역 파일 고침은 맨 마지막에, 가장 작게. · **시공 팀 · 인원 · '폭 합 ÷ 300' 은 사용자 결정(D211)으로 아예 뺐다** — 목업 ② ③ 의 '2팀 3명' · '폭 합 … = 3명' 줄을 어떤 꼴로도 그리지 않는다(시험이 그 글이 없음을 본다) · T14 가 끝나면 `link` 카드는 없지만 `mode` 로 가르는 코드는 둔다(T14 가 막히면 쓰인다).

**확인 명령**
```
cd /c/tmp/foms-s-foms-graft && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-foms-graft && node --check static/js/foms/graft-cells.js && for f in static/js/brain/ds/ds-inbox-erp*.js; do node --check "$f" || exit 1; done
cd /c/tmp/foms-s-foms-graft && python -m pytest tests/domains/test_graft_cells.py tests/domains/test_brain_ds_inbox_erp.py tests/domains/test_tablet_dashboard_sheet_contract.py tests/domains/test_tablet_rail_contract.py tests/domains/test_tablet_t2_contract.py tests/domains/test_nav_badge_lazy_count.py tests/domains/test_brain_fix_menu_query_count.py tests/domains/test_layout_header_mobile_overlap.py tests/visual/test_p1_mockup_structure.py tests/performance/test_perf_regression_guard.py tests/security/test_brain_ds_access.py tests/security/test_brain_screens_access.py "tests/harness/test_harness_drift_guard.py::test_inline_style_ratchet" tests/harness/test_file_size_ratchet.py -q
cd /c/tmp/foms-s-foms-graft && grep -rl "dashboard_grid.html\|tablet_workqueue_grid\|dashboard_mobile_tower\|layout_nav.html\|layout_scripts.html" tests | head -40
```
마지막 명령에 나온 시험도 돈다. 화면 대조: ⑥(AI 할 일 제안 칸 · 옆 창) · ⑫ · ② ③ ④(분홍 칸의 자리와 글). 보고: 0절 꼴 + 색 차 숫자.

---

## W9 — T9 상담 AI 접목 (물결 D)

- 모델 Opus · 깊이 **xhigh** — 운영 중인 상담 보내기 길과 서명 함수에 손을 댄다. 끄면 지금과 같아야 하고, 답 보내기와 할 일 실행이 서로를 깨뜨리면 안 된다.
- 워크트리 `c:\tmp\foms-s-graft-cs`(따로).

**먼저 읽기**: 이 문서 0절 · 설계서 3.9 · 3.11 · 7절 · W1 · W7 보고서 · 목업 `NowWam.dc.html` · `foms/services/cs_agent/drafting.py:400` ~ `:440` · `order_step.py` · `order_block.py` · `onto_settings.py`(관리 칸 꼴) · `settings.py`(등록 자리) · `send_view.py:123` · `wam_functions.py` 전부 · `send_flow.py` · `foms/api/channel/channel_functions.py`(서명 · 부른 상담원) · `foms/web/cs_draft_wam.py` · `templates/cs/cs_agent_wam.html` · `static/js/cs-agent/wam-draft.js` · `static/css/contexts/cs/cs-wam.css` · `foms/services/brain/usage.py:54`(`doc_keys`) · 시험 `tests/domains/test_cs_wam_draft.py` · `test_cs_wam_send.py` · `test_cs_order_lookup.py`.

**만들 것(내 파일 — 계획서 3절 물결 D)**
1. `foms/services/cs_agent/graft_settings.py` — 관리 칸 둘 `graft_evidence_enabled` · `graft_actions_enabled`(처음 끔 · 묶음 이름 '접목(근거 줄 · 할 일 제안)' · 쉬운 한글 도움말). `settings.py` 에는 등록 줄만(그 파일은 480줄 — 500줄을 넘기지 않는다).
2. `foms/services/cs_agent/graft_step.py` — 초안 뒤 한 걸음 `after_draft(ctx, row, result, facts)`: ① 근거 남기기(`doc_keys` 로 지식 키 + 확인된 주문 키 → `record_uses(..., reader='cs_draft', ref_kind='cs_turn', ref_id=<차례 번호>)`) ② 규칙 제안 셋(설계서 3.9 — AS 뜻 + 완료 · CS 단계 → `register_as` · AS · 불편 뜻 + 시공일 앞날 → `add_construction_note` · 넘김 까닭 `schedule` + 달 · 날이 똑바로 적힌 글 → 실측이 아직 앞날이면 `move_measurement`, 시공일이 앞날이면 `move_construction`). 수준은 `foms.services.ai_staff.registry.level_of(session, 'cs', <할 일>)` 로 읽고 0 이면 만들지 않는다. 저장점 안에서 돌고, 실패는 초안 길을 깨지 않되 경고 로그에 코드를 남긴다. `drafting.py` 에는 부르는 줄만(그 파일은 478줄).
3. 작은 창 값(`send_view.py` · `wam_functions.py`): `cs.draft.get` 답에 `evidence`(셋까지 — `{"kind", "label", "href"}`, `href` 는 FOMS 절대 주소) · `action`(`null` 또는 `{"id", "label", "text"}`). `cs.draft.send` 가 `with_action`(제안 번호)을 받는다 — 답 보내기가 성공한 뒤에만 `lifecycle.approve(…, actor=<서명된 상담원에 이어진 FOMS 사용자>, runners=SERVICE_RUNNERS)`. [빼기]면 `lifecycle.reject(…, code='other')`. 이어진 FOMS 사용자가 없거나 권한이 없으면 실행하지 않고 결과 글에 한 줄. 함수 목록(`FUNCTION_SCHEMAS`)에 새 칸을 올린다.
4. 작은 창 화면: `templates/cs/cs_agent_wam.html`(근거 줄 · 할 일 제안 줄 자리) · `static/js/cs-agent/wam-graft.js`(새 — 칩 그리기 · [같이 넣기] · [빼기] 고르기) · `wam-draft.js`(값을 넘기는 줄만) · `cs-wam.css` · `foms/web/cs_draft_wam.py`(새 스크립트를 화면 아래 상대 주소로 내주는 줄). 핀(`?v=`)을 올리고 베낀 곳을 같이.

**시험**: 관리 칸 끔이면 `cs.draft.get` · `cs.draft.send` 값과 초안 길이 지금과 같음 · 근거 남기기(겹침 · 주문 키) · 규칙 셋의 만들기와 안 만들기(주문 확인 안 됨 · 요일만 적힘 · 시공일이 지남 · 수준 0) · 실패해도 초안이 나감(로그 코드) · 답 보내기 실패면 실행 안 함 · 성공하면 그 직원 이름으로 승인 · 한 번만 · [빼기] · 이어진 사용자 없음 · 근거 주소가 절대 주소 · 로그에 손님 글 없음.

**함정**: 스테이징의 영발방은 실제 직원 방이고 채널톡 보내기는 실제로 나간다 — 시험은 전부 가짜 · 작은 창은 채널톡 주소를 거쳐 열려서 `/` 로 시작하는 주소가 채널톡 쪽으로 풀린다(파일은 화면 아래 상대 주소, 링크는 절대 주소) · 누른 사람은 서명된 `context.caller` 뿐 — `params` 의 값으로 사람을 정하지 않는다 · 모델 지시문 · 출력 틀을 건드리지 않는다 · 근거 이름에 손님 글을 넣지 않는다(지식 항목 이름 · 주문 번호 · 날짜만) · services → api import 금지(실행기 표는 `foms.services.erp_actions.runners.SERVICE_RUNNERS`).

**확인 명령**
```
cd /c/tmp/foms-s-graft-cs && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-graft-cs && node --check static/js/cs-agent/wam-graft.js && node --check static/js/cs-agent/wam-draft.js
cd /c/tmp/foms-s-graft-cs && python -m pytest tests/domains/test_cs_graft_step.py tests/domains/test_cs_wam_graft.py tests/domains/test_cs_wam_draft.py tests/domains/test_cs_wam_send.py tests/domains/test_cs_handoff_send.py tests/domains/test_cs_order_lookup.py tests/harness/test_file_size_ratchet.py tests/contracts/runtime/test_layer_dependency_ratchet.py -q
cd /c/tmp/foms-s-graft-cs && grep -rl "drafting\|send_flow\|wam_functions\|send_view" tests | head -40
```
마지막 명령에 나온 시험 가운데 내가 닿은 함수의 것을 돈다. 화면 대조: ⑤(근거 줄 · 할 일 제안 줄의 자리와 글). 보고: 0절 꼴.

---

## W10 — T10 AI 직원 (물결 C)

> 판 2: 물결 C 로 왔다(T16 이 이 화면의 'AI 시험' 칸을 물결 D 에서 채운다). 시공일 안내 훑기 `O4` 는 T15 가 뒤에 더한다.

- 모델 Opus · 깊이 **high** — 규칙은 정해져 있고 쓰기는 제안 만들기뿐이다. 수준 표 권한과 밤 단계 배선만 정확하면 된다.
- 워크트리 `c:\tmp\foms-s-graft-staff`(따로).

**먼저 읽기**: 이 문서 0절 · 설계서 3.10 · 3.11 · 4절 · 9절 · W1 · W2 · W7 보고서 · 목업 `BAgents.dc.html` · `tools/cron/nightly.py` · `tools/cron/expire_brain_proposals.py`(밤 단계 스크립트 본보기) · `tests/domains/test_nightly_cron_runner.py` · `tests/contracts/runtime/test_cron_purge_wiring.py` · `foms/services/partners/schedule_request.py`(협력사 희망 시공일 — `pending_request` · `request_open`) · `foms/services/orders/dashboard_dto.py:108` · `foms/services/cs_agent/metrics.py` · `foms/services/brain/eval_set.py` · `foms/services/brain/ontology_view.py:99` · `foms/api/brain_review.py`(답 꼴 본보기).

**만들 것(내 파일 — 계획서 3절 물결 D)**
1. `foms/services/ai_staff/levels.py` — `levels_view(session)` · `save_levels(session, actor, body)`(읽기 `level_of` 는 T1 이 `registry.py` 에 만들어 두었다 — 그것을 쓴다)(`SystemSetting` 열쇠 `ai_staff_levels` · ADMIN 만 · `level_cap` 넘음 · 3 · 모르는 이름은 거절 · 감사 줄).
2. `metrics.py` — (직원, 할 일)마다 지난 14일 결정 수 · 승인 수 · 비율(결정 0 이면 `None`) · 상담 초안 '그대로 보냄' 비율(지금 숫자 함수 다시 쓰기).
3. `runs.py` — `record_run(session, agent, steps, …)` · `latest_run(session, agent)` · 상담 AI 는 차례 줄에서 단계를 엮는다(시간은 전체만).
4. `sweeps.py` — 규칙 셋 `S1` · `O1` · `O3` + `O2`(D214 — 처음 수준 0: `foms/services/ai_staff/registry.py` 운영 AI 에 `Duty("advance_stage", "단계 넘기기(규칙)", 0)` 한 줄을 이 일감이 더한다)(설계서 3.10). 후보는 납작 칸 · `order_schedule_dates` 색인으로 고르고 후보만 `structured_data` 를 읽는다. 제안은 `lifecycle.propose(…)` 로(직접 쓰지 않는다). 한 번에 30개까지. `graft_flags.enabled_global('proposers')` 가 꺼져 있으면 0 개. `O3` 제안의 담당 칸은 비워 둔다(승인자가 고른다). 규칙은 이름 → 함수 표로 짜 둔다(T15 가 `O4` 를 더한다).
5. `tools/cron/ai_staff_sweep.py` · `tools/cron/erp_actions_expire.py`(기간 끝남 + 되맞추기) + `NIGHTLY_STEPS` 에 두 줄.
6. `views.py` + `foms/api/ai_staff.py`(`GET /api/ai-staff` · `GET /api/ai-staff/<열쇠>` · `POST /api/ai-staff/levels`) + 블루프린트 등록 · 길 목록(`ADMIN_OPS`) + `guard_count`.
7. AI 직원 화면(`templates/brain/ds/agents.html` — ⑪): 왼쪽 다섯(상태 꼬리표) · 가운데(머리 · 읽는 것 · 쓰는 도구 · 할 일과 자율 수준 · 2주 승인율 · AI 시험 · 최근 실패 · 비용 · 시간) · 오른쪽 실행 기록 하나. 수준 고치기는 ADMIN 에게만 보인다. 'AI 시험' 칸은 자리만 둔다 — `{% include "brain/ds/partials/agents_evals.html" ignore missing %}` 와 `data-ds-agents-evals`(T16 이 채운다). 그 partial 이 없어도 화면이 온전해야 한다.

**목업과 다르게 그릴 것(설계서 9절)**: 모델 이름은 설정 값 · 상담 AI 실행 기록은 전체 시간만 · 상담 AI 의 주문 읽기는 '있음'(새로 붙음 아님) · 운영 AI · 일정 AI 는 '시험 중 · 규칙' · 시공 팀 · 인원 · '폭 합 ÷ 300' 글은 어디에도 없다(D211). 'AI 시험' 칸의 내용과 [시험 다시 돌리기]는 T16 것이다.

**시험**: 수준 저장 권한 · 거절 꼴 · 처음 값 · 수준 0 이면 그 직원 제안 0 · 승인율 계산 · 규칙마다 만들기와 안 만들기(시공일 이미 있음 · 요청 닫힘 · 알림톡 기록 있음 · 직접 실측 · 담당 있음) · 날짜가 한국 시간 기준 · 스위치 끔이면 0 개이고 단계는 0 으로 끝남 · 밤 단계 목록 · 배선 계약 · API 권한(읽기: ADMIN + 화면 여는 MANAGER, 비용 칸 ADMIN 만, 그 밖 404) · 화면 200 · 자리 표시 · 인라인 스타일 0.

**함정**: Railway cron 은 셸이 없어 `&&` 뒤가 돌지 않는다 — 명령을 잇지 말고 `NIGHTLY_STEPS` 에 단계로 넣는다 · 훑기는 알림톡을 보내지 않는다(제안만) · `date.today()` 금지 · JSONB 를 글자로 바꿔 찾지 않는다 · 비용 · 금액 숫자를 시험 · 문서에 적지 않는다.

**확인 명령**
```
cd /c/tmp/foms-s-graft-staff && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-graft-staff && for f in static/js/brain/ds/ds-agents*.js; do node --check "$f" || exit 1; done
cd /c/tmp/foms-s-graft-staff && python -m pytest tests/domains/test_ai_staff_levels.py tests/domains/test_ai_staff_sweeps.py tests/domains/test_ai_staff_api.py tests/domains/test_brain_ds_agents.py tests/security/test_ai_staff_access.py tests/domains/test_nightly_cron_runner.py tests/contracts/runtime/test_cron_purge_wiring.py tests/domains/test_auth_enforcement.py "tests/harness/test_harness_drift_guard.py::test_inline_style_ratchet" tests/harness/test_file_size_ratchet.py tests/contracts/runtime/test_layer_dependency_ratchet.py -q
```
화면 대조: ⑪. 보고: 0절 꼴.

---

## W11 — T13 특성 시험: 지금 길의 행동 못박기 (물결 B · D206)

- 모델 Opus · 깊이 **xhigh** — 이 시험이 놓친 옆 효과는 떼어 낼 때 아무도 모르게 사라진다. 처리기 셋을 끝까지 읽고 갈래마다 못박아야 한다.
- 워크트리 `c:\tmp\foms-s-foms-graft`(화면 일꾼과 같이 쓴다 — 나는 시험 파일만 만든다).

**맥락**: 사용자 결정 D206 — 단계 넘기기 · 도면 담당 맡기기 · 실측 옮기기를 승인 대기에서 바로 실행한다. 그러려면 요청에 묶인 처리기 셋의 본체를 떼어 내야 한다(다음 일감 T14). 이 일감은 그 전에 **지금 행동을 그대로 찍어 두는 시험**만 만든다. 제품 코드는 한 줄도 고치지 않는다.

**먼저 읽기**: 이 문서 0절 · 설계서 3.12 · 10절 · `foms/api/quest.py:238` ~ `:803`(현재 작업 승인 — `/api/orders/<id>/quest/approve`) · `foms/api/drawing/erp_orders_draftsman.py:45` ~ `:285`(도면 담당 — `/api/orders/<id>/assign-draftsman`) · `foms/api/orders/field_update.py:49` ~ `:160` · `:497` ~ `:1080`(칸 고치기 — `/api/update_order_field`, 칸 `measurement_date` 만) · `foms/api/orders/__init__.py:54` · 본체가 부르는 서비스(`quest_transition_service.py` · `order_transition_service.py` · `quest_approve_authz.py` · `confirm_drawing_gate.py` · `admin_override.py` · `draft_guard.py` · `drawing_assignee_write.py` · `change_reason.py` · `foms/services/notifications/drawing_order_change.py` · `production_change.py`) · 지금 시험에서 앱 · 로그인 · 주문 준비물을 쓰는 법(`grep -rl -e "quest/approve" -e "assign-draftsman" -e "update_order_field" tests --include="*.py"` — 60개 안팎. 가짜 보내기를 끼우는 법도 여기서 따른다).

**만들 것(내 파일)**: `tests/domains/test_graft_char_quest_approve.py` · `test_graft_char_assign_draftsman.py` · `test_graft_char_measurement_date.py` · (같이 쓰는 도우미가 필요하면) `tests/support/graft_char.py`.

1. **찍는 도우미**: 길을 부르기 전 · 뒤에 주문 하나의 '자국'을 뜬다 — 주문 일 기록(`order_events`) 종류별 수 · 감사 줄(`security_logs`) `action` 별 수 · 변경 원장(`order_field_changes`) `path_template` 별 수 · 알림(`notifications`) 종류와 받는 팀 · 줄 세운 바깥 일(`domain_side_effect_outbox`) `effect_type` 별 수 · 사유 줄 · 담당 줄(`order_assignments`) · 날짜 찾기 표(`order_schedule_dates`) · 고른 `structured_data` 경로 값 · 납작 칸 · `mutation_version` 이 오른 폭. 시험은 **뒤 − 앞**을 글자 그대로 적은 기대값과 견준다(시각 · 일련번호는 뺀다).
2. **현재 작업 승인**: 시험 레인에서 닿는 단계마다(주문접수 → … → CS) 팀 승인 한 번 · 마지막 승인으로 단계가 넘어감(단계 코드 · 다음 현재 작업 · 일 기록 종류 · 알림) · 고객컨펌의 도면 문지기 막힘(409 + 코드)과 관리자 뚫기 · 승격 전 초안(409) · 현재 단계 없음(400) · 권한 없는 팀(403) · 로그인 안 함 · 이미 넘어간 주문의 다시 넘기기 · CS 승인으로 완료 처리. 답 코드와 답 값의 칸 이름까지.
3. **도면 담당 맡기기**: 한 명 · 여러 명 · 빈 목록(400) · 없는 주문(404) · 권한 갈래(ADMIN · 도면팀 · 그 밖 403 과 그 글) · 담긴 칸 · 담당 줄 · 감사 `action` · 알림.
4. **실측일 고치기**(칸 `measurement_date` 만): ERP 주문에서 날짜 넣기 · 바꾸기 · 비우기 → `structured_data.schedule.measurement.date` · 납작 칸 · 옛 칸 · 날짜 찾기 표 · 일 기록 · 변경 원장 · 감사 · 알림 · 답 값(사유가 필요한가 포함) · 권한(편집 못 하는 팀 403 과 그 글 · 로그인 안 함 401) · 허용 안 된 칸(400) · 없는 주문(404) · 날짜 꼴 고르기 · 팀 범위 오류 · 승격 전 초안 · 완료 주문.
5. **대조군(잡는 힘 시험)**: 길마다 둘 이상 — 옆 효과 하나를 시험 안에서 바꿔 끼워 없앤 뒤(감사 줄 쓰기 · 알림 만들기 같은 것) 같은 견주기가 **빨개지는지** 본다. 견주기가 그대로 초록이면 그 자국은 못박히지 않은 것이다.

**함정**: 제품 코드를 고치지 않는다(이상한 행동을 봐도 고치지 말고 보고에 적는다 — 그 행동까지가 지금 행동이다) · 알림톡 · 채널톡 · 푸시는 지금 시험이 하는 대로 가짜로 · 실제 이름 · 전화 · 주소를 쓰지 않는다 · `date.today()` 금지 · 시험이 `docs/` 를 읽지 않는다 · 시험 이름 · 글은 한글로 무엇을 못박는지 · 순서에 기대지 않는다(시험마다 자기 주문) · SQLite 레인에서 안 닿는 갈래(FK · 잠금 경합)는 못박지 못한 것으로 표에 적는다.

**확인 명령**(두 번 돌려 둘 다 초록)
```
cd /c/tmp/foms-s-foms-graft && python -m pytest tests/domains/test_graft_char_quest_approve.py tests/domains/test_graft_char_assign_draftsman.py tests/domains/test_graft_char_measurement_date.py -q
cd /c/tmp/foms-s-foms-graft && python -m pytest tests/domains/test_graft_char_quest_approve.py tests/domains/test_graft_char_assign_draftsman.py tests/domains/test_graft_char_measurement_date.py -q
cd /c/tmp/foms-s-foms-graft && python -m pytest tests/harness/test_file_size_ratchet.py tests/domains/test_ci_shard_contract.py -q
```
보고: 0절 꼴 + 길마다 "장면 → 답 코드 → 못박은 자국" 표 + 대조군 결과 + 못박지 못한 갈래와 까닭 + 읽다가 본 이상한 행동(`경로:줄`).

---

## W12 — T14 처리기 셋 떼어 내기 + 실행기 셋 (물결 C · D206 · 코어 변경)

- 모델 Opus · 깊이 **max** — 모든 주문이 지나는 처리기를 고친다. 한 줄이라도 행동이 달라지면 단계 · 일정 · 알림이 틀어진다.
- 워크트리 `c:\tmp\foms-s-graft-core`(따로). 바탕: 특성 시험(T13)이 든 커밋 `<메인이 채운다>`.

**먼저 읽기**: 이 문서 0절 · 설계서 3.3 · 3.11 · 3.12 · W11 보고서(못박은 것 · 못박지 못한 갈래) · W7 보고서(실행기 표 · `lifecycle.approve`) · 본보기 `foms/api/cs/as_orders.py:564` ~ `:620`(`register_as_from_payload` — 길과 다른 길이 같은 본체를 부르는 꼴) · `foms/api/quest.py:367` ~ `:803` · `foms/api/drawing/erp_orders_draftsman.py:186` ~ `:285` · `foms/api/orders/field_update.py:497` ~ `:1080` · `foms/api/orders/__init__.py:50` ~ `:62` · `foms/api/erp_action_runners.py` · `foms/services/erp_actions/registry.py` · `preview.py` · `tests/contracts/runtime/layer_dependency_baseline.json`(이 파일들이 이미 가진 api → web 줄).

**차례(바꾸지 않는다)**
0. 손대기 전에 특성 시험 셋과 그 길에 닿는 지금 시험을 돌려 초록인 출력을 적어 둔다.
1. **한 번에 처리기 하나** — 현재 작업 승인 → 도면 담당 → 칸 고치기 순서. 처리기마다:
   - 같은 파일에 `approve_quest_from_payload(order_id, payload, user_id, username)` · `assign_draftsman_from_payload(order_id, data, user_id)` · `update_order_field_from_payload(data, user_id, username, *, clean_dict_like_name)` 를 만든다. 몸은 지금 처리기 몸 그대로이고 **바꾸는 것은 셋뿐**: `request.get_json(…)` → 인자 · `session.get('user_id')` · `session['user_id']` → 인자 · `session.get('username')` → 인자.
   - 지금 길은 장식자를 그대로 두고 그 함수를 부르는 한 줄짜리 껍데기가 된다(요청 본문 · 세션 값을 읽어 넘긴다).
   - 판정 · 순서 · 글 · 로그 · 커밋 자리 · 돌려주는 Flask 답을 손대지 않는다. `foms/services/` 로 옮기지 않는다(설계서 3.12 '어디에 두나').
   - 하나 끝낼 때마다 특성 시험 + 그 길의 지금 시험을 돈다. 빨개지면 다음으로 가지 않는다.
2. **실행기 셋**(`foms/api/erp_action_runners.py` — `RUNNERS` 에 `advance_stage` · `assign_draftsman` · `move_measurement`): 승인한 사람(번호 · 이름)으로 위 함수를 부른다. 본문은 **검사를 지난 넣을 값으로만** 만든다 — `emergency_override` · 관리자 뚫기 · 다른 칸 이름을 넘길 길이 없어야 한다. `move_measurement` 의 본문은 `{"order_id", "field": "measurement_date", "value": <날짜>}` 뿐. 돌려받은 답이 2xx 가 아니면 주문은 바뀌지 않은 것 — 막힘(409 `ACTION_PRECONDITION` + 그 글)으로 돌리고 제안은 `open` 에 둔다.
3. `preview.py` — 셋의 `check` · `preview` · `verify` · `steps` · `param_choices`(도면 담당: 켜진 도면팀 사람 목록 — 승인 창을 열 때만 읽는다. 제안 줄에 이름을 남기지 않는다).
4. `registry.py` — 셋의 `mode` 를 `run` 으로, `assign_draftsman` 넣을 값 `user_ids`(꼴 `users` · 꼭 있어야 함 — AI 는 비워 두고 승인자가 고른다), `move_measurement` 넣을 값 `date`. 넣을 값 꼴에 `users` · `flag` 가 없으면 더한다. `tests/domains/test_erp_actions_registry.py` 의 기대값을 맞춘다.
5. 시험 `tests/domains/test_erp_actions_core_runners.py` — **같음 시험**: 똑같이 만든 주문 둘에서 하나는 지금 길로, 하나는 제안 승인(실행기)으로 처리한 뒤 T13 의 찍는 도우미로 뜬 자국이 같다(실행기 쪽에만 `ERP_ACTION_*` 감사 줄이 더 있다). 막힘 갈래(도면 문지기 · 권한 없는 팀 · 승격 전 초안 · 담당을 안 고름)가 409 로 돌고 주문 · 제안이 그대로임. 뚫기 값을 넣을 값에 끼워도 본체에 닿지 않음.

**하지 않는 것**: 특성 시험 파일(T13 것)을 고치지 않는다 — 고쳐야 통과한다면 행동이 달라진 것이다. 판정 로직 · 오류 글 · 권한 규칙을 '고치는 김에' 손대지 않는다. 기준선 파일(크기 · 층 방향)을 다시 만들지 않는다. 처리기 밖의 길(한꺼번에 맡기기 · 한꺼번에 상태 바꾸기)은 건드리지 않는다.

**막히면**: 어느 처리기가 셋 치환만으로 안 떼어지면(요청 · 세션을 더 깊이 쓰거나 답 꼴이 길에 묶임) 그 처리기는 **고친 것을 되돌려 지금 그대로** 두고(Edit 로 — git 쓰기 금지), 그 할 일만 `link` 로 남기고 `BLOCKED` + 걸린 줄(`경로:줄`)을 보고한다. 나머지 둘은 계속한다.

**확인 명령**
```
cd /c/tmp/foms-s-graft-core && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-graft-core && python -m pytest tests/domains/test_graft_char_quest_approve.py tests/domains/test_graft_char_assign_draftsman.py tests/domains/test_graft_char_measurement_date.py -q
cd /c/tmp/foms-s-graft-core && python -m pytest tests/domains/test_erp_actions_core_runners.py tests/domains/test_erp_actions_registry.py tests/domains/test_erp_actions_lifecycle.py tests/domains/test_erp_actions_api.py tests/domains/test_auth_enforcement.py tests/harness/test_file_size_ratchet.py tests/contracts/runtime/test_layer_dependency_ratchet.py -q
cd /c/tmp/foms-s-graft-core && python -m pytest $(grep -rl -e "quest/approve" -e "assign-draftsman" -e "update_order_field" tests --include="*.py") -q
cd /c/tmp/foms-s-graft-core && git diff --stat HEAD -- tests/domains/test_graft_char_quest_approve.py tests/domains/test_graft_char_assign_draftsman.py tests/domains/test_graft_char_measurement_date.py tests/support/graft_char.py
```
넷째 명령은 그 길에 닿는 지금 시험 전부다(전체 시험이 아니다). 메모리 오류로 죽으면 파일 목록을 둘로 나눠 돈다. 다섯째 명령은 아무것도 나오지 않아야 한다. 보고: 0절 꼴 + 처리기마다 "바꾼 줄(치환 셋) · 그대로 둔 것" + 같음 시험 결과 + `git diff --stat` 원문.

---

## W13 — T15 바깥 알림 둘: 시공일 안내 알림톡 + 승인 대기 폰 알림 (물결 D · D208 · D210)

- 모델 Opus · 깊이 **xhigh** — 손님에게 글이 나가는 길과 직원 폰에 가는 길이다. 스위치 · 서식 번호 없이 한 통이라도 나가면 사고다.
- 워크트리 `c:\tmp\foms-s-graft-notify`(따로).

**먼저 읽기**: 이 문서 0절 · 설계서 3.3 · 3.4 · 3.6 · 3.11 · 3.13 · 3.14 · 4절 · 7절 · 11절 '남은 일' · W7 · W10 · W12 보고서 · `foms/services/kakao_alimtalk.py`(`:73` 서식 글 · `:263` 변수 · `:379` `is_configured` · `:397` · `:411` `brand_config` · `:433` 보내기 · `:537` ~ `:590` 보낼 수 없는 주문 · `:734` 이력 · `:807` 이미 보냄 · `:844` · `:879`) · `foms/api/kakao/` 의 손으로 보내기 길(감사 줄 꼴) · `foms/services/notifications/notice_push.py` · `foms/services/notices/push.py`(받는 사람마다 알림 줄 → 푸시 줄 세우기 본보기) · `foms/services/notifications/push_sender.py:215` ~ `:270`(보낼 종류 · 주소) · `:428` ~ `:470`(글) · `:797` · `recipients.py` · `static/sw.js` 와 `static/js/foms/mobile-push.js` 의 알림 누름 처리 · `foms/services/erp_actions/lifecycle.py` · `runners.py` · `registry.py` · `preview.py` · `foms/services/ai_staff/sweeps.py` · `registry.py` · `foms/services/graft_flags.py`.

**가 — 시공일 안내 알림톡(D208)**
1. `foms/services/kakao_alimtalk_construction.py` — `ALIMTALK_TEMPLATE_CONSTRUCTION`(서식 글 초안: 변수 `#{고객명}` · `#{시공일}` · `#{시간대}` · `#{주문처}`. 날짜 + 시간대만 — 팀 · 인원 글 없음) · `build_construction_variables(sd)` · `render_construction_preview(sd)` · `is_construction_ready(brand)`(스위치 + Solapi 설정 + 서식 번호 env `SOLAPI_TEMPLATE_CONSTRUCTION_ID_<브랜드>` 셋 다) · `send_construction_alimtalk(order_id, *, manual_by, dedupe_key)`(답 꼴은 `send_alimtalk` 과 같게). 브랜드 고르기 · 전화 고르기 · 보낼 수 없는 주문 가르기 · Solapi 보내기 · 이력 쓰기는 `kakao_alimtalk.py` 의 것을 다시 쓴다 — 밖에서 부를 이름이 없으면 그 파일에 이름을 내놓는 줄만 더한다(지금 함수의 행동은 그대로). 이력 칸 `structured_data.alimtalk_construction`, 감사 `ALIMTALK_CONSTRUCTION_SENT`(본문 없음).
2. `graft_flags.py` 에 이름 `FOMS_GRAFT_CONSTRUCTION_ALIMTALK`(전역 켬만).
3. 할 일 `send_construction_alimtalk`(`registry.py` — 수준 상한 1 · `STAFF_MUTATION` · `run`) + 실행기(`runners.py`) + `check`(쓸 수 있는 상태 · 시공일 있음 · 같은 시공일로 이미 나감) · `preview` · `verify` · `steps`(`preview.py`). 열쇠 `alimtalk:construction:<주문>:<시공일>:action:<제안 번호>`.
4. `schedule_construction` · `move_construction` 에 넣을 값 `notify_customer`(꼴 `flag`): 쓸 수 있는 상태일 때만 나타나고 처음 값 참. 참이면 미리 보기 · 차례에 '손님 알림톡 1건 — 시공일 안내'가 붙고, 시공일 쓰기가 성공한 뒤 보낸다. 보내기 실패는 시공일을 되돌리지 않고 결과에 코드 한 줄.
5. 훑기 `O4`(`sweeps.py`): 시공일이 내일 + 이력 없음 + 쓸 수 있는 상태 → 제안. 운영 AI 의 이 할 일 처음 수준은 0(`ai_staff/registry.py` 한 줄) — 수준 0 이면 만들지 않는다.

**나 — 승인 대기 폰 알림(D210)**
6. `foms/services/notifications/erp_action_push.py` — 종류 `ERP_ACTION_PROPOSAL` · 잠금화면 글(제목 'AI 제안 승인 대기', 본문 '<할 일 이름> · 주문 #<번호>') · 누르면 여는 주소 `/brain?tab=inbox&proposal=<번호>`. 다른 서비스를 import 하지 않는다(`notice_push.py` 와 같은 꼴).
7. `foms/services/erp_actions/notify.py` — `proposal_created(session, proposal)`: 받는 사람(그 주문 담당 → 없으면 목록의 `notify_team`; 그 가운데 켜진 내부 계정 + `actions` 스위치 + `policy_id` 통과 + 주문 읽기 권한; 20명까지) → 사람마다 `Notification` 한 줄 → 커밋 **뒤에** 푸시 줄 세우기(지금 공지 푸시가 하는 방식이나 세션의 커밋 뒤 한 번짜리 듣개 가운데 지금 코드에 맞는 것). `FOMS_GRAFT_PUSH_ENABLED`(전역) 가 꺼져 있으면 아무것도 만들지 않는다. 실패는 저장점 안 · 경고 로그에 코드 — 제안 만들기를 되돌리지 않는다.
8. `lifecycle.py` — `propose` 가 새 제안을 만든 때에만 `proposal_created` 를 부르는 줄(겹침 · 거절된 것 다시 만들기는 `None` 이라 안 부른다). `registry.py` 에 할 일마다 `notify_team`.
9. `push_sender.py` — 이 종류를 보낼 종류에 넣고 글 · 주소 갈래를 더한다. 서비스 워커 · 화면 스크립트가 `/erp` 로 시작하는 주소만 받으면 `/brain` 을 받게 넓힌다(같은 출처 경로만 · 바깥 주소는 계속 막는다).

**시험**: 가 — 스위치 끔 · Solapi 설정 없음 · 서식 번호 없음 가운데 하나라도면 보내기 함수가 불리지 않음(가짜 호출 수 0) · 셋 다 있으면 한 번 · 같은 시공일 두 번째는 안 보냄 · 협력사 · 삭제 · 초안 · 전화 없는 주문 · 변수에 팀 · 인원 글 없음 · 이력 · 감사 꼴 · `notify_customer` 참 · 거짓 · 보내기 실패 때 시공일은 그대로 · `O4` 만들기와 안 만들기(수준 0 · 이력 있음 · 쓸 수 없는 상태). 나 — 스위치 끔이면 알림 줄 0 · 받는 사람 갈래(담당 있음 · 없음 · 승인 못 하는 담당 빠짐 · 프리랜서 남의 주문 빠짐 · 20명 상한 · 0명) · 잠금화면 글에 손님 이름 · 날짜 없음 · 주소 · 겹친 제안은 알림 0 · 알림 실패해도 제안은 생김 · 커밋 전에 줄 세우지 않음. 공통 — 스위치 판정 · 목록 정합 · 지금 시험.

**함정**: **시험과 스테이징에서 절대 실제로 보내지 않는다**(Solapi · 웹 푸시 호출은 전부 가짜. 스테이징 알림톡은 실제로 나간다) · 서식 글은 초안이다 — 심사 글과 다르면 실제 보내기가 실패하니 "심사 글이 정해지면 이 글을 맞춘다"는 주석을 서식 옆에 둔다 · 서식 글 · 시험에 실제 이름 · 주소를 넣지 않는다 · `kakao_alimtalk.py` 는 큰 파일이다 — 몸을 옮기거나 고치지 않는다 · 시공 팀 · 인원 · '폭 합 ÷ 300' 글을 어디에도 쓰지 않는다(D211) · `sw.js` 를 고치면 그 파일의 판 값 · 그 값을 보는 시험을 같이 본다 · env 는 서비스마다 따로(설계서 4절) · services → api import 금지.

**확인 명령**
```
cd /c/tmp/foms-s-graft-notify && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-graft-notify && python -m pytest tests/domains/test_construction_alimtalk.py tests/domains/test_erp_action_push.py tests/domains/test_erp_actions_notify.py tests/domains/test_graft_flags.py tests/domains/test_erp_actions_registry.py tests/domains/test_erp_actions_runners.py tests/domains/test_erp_actions_lifecycle.py tests/domains/test_ai_staff_registry.py tests/domains/test_ai_staff_sweeps.py tests/performance/test_perf_regression_guard.py tests/harness/test_file_size_ratchet.py tests/contracts/runtime/test_layer_dependency_ratchet.py -q
cd /c/tmp/foms-s-graft-notify && grep -rl -e "kakao_alimtalk" -e "push_sender" -e "mobile-push" -e "sw.js" tests | head -60
```
셋째 명령에 나온 시험 가운데 내가 닿은 함수 · 파일의 것을 돈다(`sw.js` · `mobile-push.js` 를 고쳤으면 `node --check` 도). 보고: 0절 꼴 + 서식 글 초안 전문(사용자가 카카오 심사에 낼 바탕) + "나가는 조건" 표 + 받는 사람 규칙.

---

## W14 — T16 상담 AI 평가 묶음 + [시험 다시 돌리기] (물결 D · D209)

- 모델 Opus · 깊이 **xhigh** — 손님 상담 글로 묶음을 만들고 돈이 드는 모델을 돌린다. 글이 새거나 상한 없이 돌면 안 된다.
- 워크트리 `c:\tmp\foms-s-graft-eval`(따로).

**먼저 읽기**: 이 문서 0절 · 설계서 3.10 · 3.11 · 3.15 · 4절 · 7절 · W10 보고서(⑪ 화면 자리 · `foms/api/ai_staff.py` 답 꼴) · `foms/services/cs_agent/brain.py`(초안 한 번 만드는 들머리 · `DraftRequest`) · `brain_prompt.py` · `checks.py` · `checks_same.py`('같은 뜻' 판정) · `case_material.py:150` ~ `:180`(`held_out`) · `brain_spend.py:171` ~ `:270`(쓰임 열쇠 · 예약 · 정산) · `foms/services/brain/eval_set.py`(물어보기 평가 — 꼴 본보기) · `foms/services/jobs/tasks.py:238` 부근(줄 일 꼴)과 그 일을 줄에 넣는 곳(`push_sender.py:797`) · `tests/contracts/runtime/test_worker_boot_order.py` · `test_worker_supervisor_contract.py`(WORKER 가 무엇을 도는지) · `models.py` 의 `CsAgentTurn`.

**만들 것(내 파일 — 계획서 3절 물결 D)**
1. `foms/services/ai_staff/evals.py` — 설정(`SystemSetting` `ai_staff_eval_settings`: 한 번 돈 상한 · '지난 상담' 수 · '위험 문장' 수 — 처음 값 0) · `build_eval_set(session, now)`(돌릴 때 DB 에서: '지난 상담' = `held_out` 이고 직원 답이 있는 차례를 최근 것부터, '위험 문장' = `check_codes` 가 비지 않은 차례. 가린 칸만 읽는다) · `latest_results(session)` · 결과 저장(`ai_staff_eval_results` — 최근 10번, 글 없음).
2. `foms/services/ai_staff/evals_run.py` — `run_eval(session, *, actor_id, now, client)`: 차례마다 상담 두뇌로 초안을 다시 만들고(지금 들머리 그대로 — 지시문을 따로 만들지 않는다) ① 지난 상담은 직원 답과 같은 뜻인가 ② 위험 문장은 보내기 전 검사를 지나고도 근거 없는 약속을 담는가를 센다. 돈은 평가 전용 쓰임 열쇠 `cs_agent_eval_spend` 로 예약 · 정산하고 한 번 상한에 닿으면 멈춘다('상한에서 멈춤'). 두뇌 열쇠가 없으면 '준비 안 됨'으로 끝낸다. **부르지 않는 것**: 채널톡 메모 · 손님 답 보내기 · 사례 기억 · 쓰인 횟수 · 제안 만들기 · 차례 줄 고치기.
3. 줄 일(`foms/services/jobs/tasks.py` 에 일 하나) + 한 번에 하나만(도는 중 표시 + 오래 멈춘 표시는 풀림).
4. `foms/api/ai_staff.py` — `POST /api/ai-staff/evals/run`(ADMIN 만 · 상한 0 이면 409 와 "돈 상한을 먼저 넣어 주세요" · 도는 중이면 409) · 설정 저장(ADMIN) · `GET /api/ai-staff/cs` 답에 `evals` 칸. 길 목록에 `ADMIN_OPS` + `guard_count`.
5. 화면: `templates/brain/ds/partials/agents_evals.html`(T10 이 남긴 자리 `data-ds-agents-evals`) + `ds-agents-evals.js` + `brain-ds-agents-evals.css` — 줄 셋(지난 상담 · 위험 문장 · 능력 질문: 막대 · 결과 글 · 통과 꼬리표) · 최근 실패(차례 번호 · 까닭 코드 — 글 없음) · 마지막으로 돌린 때 · 쓴 돈(ADMIN 만) · [시험 다시 돌리기](ADMIN 만 · 도는 중이면 꺼짐) · 상한 · 묶음 크기 넣는 칸(ADMIN 만).

**시험**: 묶음이 가린 칸만 읽음(원문 칸에 지어낸 표식 글을 넣어 두고 묶음 · 결과 · 로그 어디에도 없음을 본다) · `held_out` 이 없으면 묶음 0(배우기 차례로 채우지 않음) · 가짜 두뇌로 세 줄 계산 · 상한 0 이면 안 돎 · 상한에서 멈춤 · 열쇠 없음 → '준비 안 됨' · 보내기 · 배우기 · 쓰인 횟수 · 제안 함수가 한 번도 안 불림(가짜로 세어 본다) · 실제 초안의 하루 돈 줄이 안 바뀜 · 결과에 글 없음 · 최근 10번만 · 동시에 두 번 409 · 권한(ADMIN 만 돌림 · 설정 저장, MANAGER 는 결과만, 그 밖 404 · 비용 칸 ADMIN 만) · 길 목록 정합 · 화면 자리 · 인라인 스타일 0.

**함정**: 저장소 · 시험 · 로그에 손님 글 · 평가 문장을 두지 않는다 · 돈 숫자를 코드 기본값 · 시험 · 문서에 적지 않는다(처음 값은 0, 시험은 뜻 없는 작은 수) · 모델 호출은 시험에서 가짜 · 스테이징은 열쇠가 없다('준비 안 됨'이 정상) · 줄 일이 WORKER 에서 도는지 계약 시험으로 확인하고, 아니면 `BLOCKED` 로 보고한다(다른 서비스에서 돌리는 길을 새로 만들지 않는다) · 화면이 끝없이 물어보지 않게(도는 중일 때만, 간격을 두고, 화면을 떠나면 멈춤) · `brain_spend.py` 에는 쓰임 열쇠 한 줄만.

**확인 명령**
```
cd /c/tmp/foms-s-graft-eval && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-graft-eval && node --check static/js/brain/ds/ds-agents-evals.js
cd /c/tmp/foms-s-graft-eval && python -m pytest tests/domains/test_ai_staff_evals.py tests/domains/test_ai_staff_evals_api.py tests/security/test_ai_staff_evals_access.py tests/security/test_ai_staff_access.py tests/domains/test_ai_staff_api.py tests/domains/test_brain_ds_agents.py tests/domains/test_auth_enforcement.py "tests/harness/test_harness_drift_guard.py::test_inline_style_ratchet" tests/harness/test_file_size_ratchet.py tests/contracts/runtime/test_layer_dependency_ratchet.py -q
cd /c/tmp/foms-s-graft-eval && grep -rl -e "brain_spend" -e "jobs/tasks" -e "jobs.tasks" tests | head -30
```
넷째 명령에 나온 시험 가운데 내가 닿은 것을 돈다. 화면 대조: ⑪ 의 'AI 시험' 칸. 보고: 0절 꼴 + 묶음을 만드는 질의(어느 칸을 읽나) + 돈 상한이 걸리는 자리.

---

## R1 — T11 검수 (읽기만 · 물결 E)

- 모델 Opus · 깊이 **xhigh** — 일꾼 열 명의 결과를 설계서 한 장에 대어 보는 일이다. 놓친 권한 구멍 · 개인정보 새는 길이 가장 비싸다.
- 워크트리 `c:\tmp\foms-s-foms-graft`(읽기만 — 파일을 고치지 않는다. git 은 `status` · `diff` · `log` 만).

**읽을 것**: 설계서 전부 · 계획서 3절(파일 주인) · `git diff origin/deploy...HEAD` · 새 시험.

**볼 것(하나씩 답한다)**
1. 설계서 3절의 이름 · 답 꼴 · 표 꼴이 코드와 같은가(다르면 `경로:줄`).
2. 스위치 일곱 + 관리 칸 둘: 끔이면 지금과 같은가(템플릿 출력 · 답 값 · 지시문 글자) — 시험이 있는가, 빠진 갈래는.
3. 권한: 새 길마다 로그인 안 함 · 바깥 역할 · 꺼진 계정 · 정책 못 넘는 직원 · 프리랜서 남의 주문 · 스위치 끔. 수 · 칩 · 카드로 새는 것이 없는가. 본문의 사람 칸을 읽는 곳이 있는가.
4. 개인정보: 모델로 가는 글 · 제안의 글 · 로그 · 감사 줄 · 시험 자료 · 문서에 이름 · 전화 · 주소 · 금액이 있는가.
5. 할 일 실행: 두 번 누름 · 기준 판 바뀜 · 실행 뒤 기록 전 죽음 · 답 보내기 실패 뒤 실행 · 수준 0 · `mode = link` · `human` 이 실행되는 길이 있는가. 감싼 기능의 지금 기록이 그대로 남는가.
6. 바깥 보내기: 시험이 실제로 보낼 수 있는 길이 있는가.
7. 꾸밈이 새는가: `foms-ds.css` 가 새 화면 밖에서 실리는가 · 선택자가 가두어졌는가 · 옛 화면 파일이 바뀌었는가.
8. 성능: 메뉴 DB 질의 · 줄마다 질의 · 색인 없는 글자 찾기 · 막는 스크립트.
9. 규칙: 인라인 스타일 · 300줄 · 500줄 · 층 방향 · 손 핀과 베낀 곳 · 한자 · 기계 말 · 목업에 없는 칩.
10. 지금 기능을 잃은 곳(설계서 5.4 목록에 하나씩).
11. 파일 주인 표 밖을 고친 곳.
12. 코어 떼어 내기(D206): 특성 시험 파일이 T13 커밋과 같은가 · 처리기 셋의 diff 가 치환 셋(요청 본문 · 사용자 번호 · 사용자 이름)뿐인가 · 실행기가 뚫기 값이나 다른 칸 이름을 본체에 넘길 길이 있는가 · 지금 길과 실행기의 자국이 같은가(같음 시험이 그것을 보는가).
13. 시공일 안내 알림톡(D208): 스위치 · Solapi 설정 · 서식 번호 가운데 하나라도 없이 나갈 길이 있는가 · 시험이 실제 호출을 할 수 있는가 · 본문 · 손님 정보가 로그 · 감사에 남는가 · 같은 시공일로 두 번 나갈 길.
14. 승인 대기 폰 알림(D210): 승인할 수 없는 사람이 받는가 · 잠금화면 글에 손님 이름 · 날짜가 있는가 · 스위치 끔이면 알림 줄이 0 인가 · 커밋 전에 줄 세우는가 · 누르면 여는 주소가 바깥 주소를 받게 됐는가.
15. 상담 AI 평가(D209): 손님 글이 결과 · 로그 · 저장소 · 시험에 있는가 · 평가가 보내기 · 배우기 · 쓰인 횟수 · 제안을 부르는가 · 상한 0 이면 안 도는가 · 실제 초안의 돈 줄과 섞이는가 · 동시에 두 번 도는가 · ADMIN 아닌 사람이 돌릴 수 있는가.
16. D211: 시공 팀 · 인원 · '폭 합' · '÷ 300' 글이 코드 · 템플릿 · 스크립트 · 시험 · AI 글에 있는가.

**보고**: 결함마다 한 줄 `경로:줄 · 심각도(막음 · 높음 · 보통 · 낮음) · 무엇 · 고칠 말`. 칭찬 · 요약 없이. 확신이 낮으면 그렇게 적는다. 직접 돌려 본 명령과 출력은 따로.

---

## V1 — T12 합친 뒤 확인 (물결 E)

- 모델 Opus · 깊이 **high** — 명령을 돌리고 빨간 것의 원인을 가려야 한다(내 것인가 · 남의 세션 것인가 · 환경인가).
- 워크트리 `c:\tmp\foms-s-foms-graft`. 파일을 고치지 않는다(빨간 것은 원인과 함께 보고). git 쓰기 금지.

**돌릴 것(차례대로 — 출력 원문을 보고에 싣는다)**
```
cd /c/tmp/foms-s-foms-graft && git status --short && git log --oneline origin/deploy..HEAD
cd /c/tmp/foms-s-foms-graft && python -c "import app; print('APP_OK')"
cd /c/tmp/foms-s-foms-graft && python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; print(ScriptDirectory.from_config(Config('alembic.ini')).get_heads())"
cd /c/tmp/foms-s-foms-graft && python -m pytest tests/harness/test_file_size_ratchet.py tests/contracts/runtime/test_layer_dependency_ratchet.py "tests/harness/test_harness_drift_guard.py::test_inline_style_ratchet" tests/domains/test_alembic_single_head.py tests/domains/test_auth_enforcement.py tests/performance/test_perf_regression_guard.py tests/visual/test_p1_mockup_structure.py tests/domains/test_ci_shard_contract.py -q
cd /c/tmp/foms-s-foms-graft && python -m pytest tests/domains tests/security -k "brain or graft or erp_actions or erp_ontology or erp_action_push or ai_staff or cs_wam or cs_graft or construction_note or construction_alimtalk or tablet or nav_badge" -q
cd /c/tmp/foms-s-foms-graft && for f in static/js/brain/ds/*.js static/js/foms/graft-cells.js static/js/cs-agent/wam-graft.js static/js/cs-agent/wam-draft.js; do node --check "$f" || echo "FAIL $f"; done
cd /c/tmp/foms-s-foms-graft && grep -rn "foms-ds.css" templates | grep -v "templates/brain/ds/"
cd /c/tmp/foms-s-foms-graft && grep -rn "style=\"" templates/brain/ds static/js/brain/ds static/js/foms/graft-cells.js static/js/cs-agent/wam-graft.js | head
cd /c/tmp/foms-s-foms-graft && git diff --stat origin/deploy...HEAD -- templates/brain/index.html templates/brain/item.html templates/brain/ask.html templates/brain/partials static/js/brain/*.js static/css/contexts/brain/brain.css static/css/foundation/foms-tablet-bundle.css tests/harness/file_size_baseline.json tests/contracts/runtime/layer_dependency_baseline.json
cd /c/tmp/foms-s-foms-graft && git diff --stat <T13 커밋> HEAD -- tests/domains/test_graft_char_quest_approve.py tests/domains/test_graft_char_assign_draftsman.py tests/domains/test_graft_char_measurement_date.py tests/support/graft_char.py
cd /c/tmp/foms-s-foms-graft && grep -rn -e "폭 합" -e "÷ 300" -e "2팀 3명" foms templates static tests --include="*.py" --include="*.html" --include="*.js" --include="*.css"
cd /c/tmp/foms-s-foms-graft && python -m pytest $(grep -rl -e "quest/approve" -e "assign-draftsman" -e "update_order_field" tests --include="*.py") -q
```
- 일곱째 · 여덟째 · 아홉째 명령은 **아무것도 나오지 않아야** 한다(꾸밈이 새 화면 밖에 없음 · 인라인 스타일 없음 · 고치면 안 되는 파일이 안 바뀜).
- 열째(특성 시험이 T13 커밋과 다른가) · 열한째(D211 — 시공 팀 · 인원 글)도 **아무것도 나오지 않아야** 한다. `<T13 커밋>` 은 계획서 7절 '특성 시험 문지기 기록'의 커밋 번호다.
- 열두째는 처리기 셋에 닿는 지금 시험 전부다(60개 안팎 — 전체 시험이 아니다).
- 머리는 하나(`graft_00`)여야 한다. `origin/deploy` 에 새 마이그레이션이 생겨 둘이 되면 그 사실과 새 머리 이름을 보고한다(고치는 것은 메인).
- 다섯째 명령이 메모리 오류로 죽으면 일손 없이(`-n` 없이) 그대로 다시 돈다. 그래도 죽으면 `-k` 를 둘로 나눠 돈다.

**더 볼 것**
1. 스위치 끔 견주기: 스위치를 모두 끈 시험용 앱에서 `/brain` · `/brain?tab=inbox` · `/erp/dashboard` 조각 · 작은 창 화면을 그려, `origin/deploy` 의 같은 화면과 글자가 같은지(자산 주소의 지문 값만 다를 수 있다). 다르면 어디가.
2. 손 핀: 이 가지가 고친 손 핀(`grep -rn "?v=" $(git diff --name-only origin/deploy...HEAD -- templates)`)마다 옛 값이 `tests` · `templates` 에 남았는지.
3. 파일 주인: `git diff --name-only origin/deploy...HEAD` 의 모든 파일이 계획서 3절 표에 있는지. 없는 파일 목록.
4. 길 목록: 새 쓰기 길이 `foms_order_mutation_policy_manifest.json` 에 있고 `guard_count` 가 맞는지.
5. 판 열두 장마다 화면 그림이 있는지와 일꾼 보고서의 차이 목록이 닫혔는지.
6. 바깥 보내기: 스위치를 모두 끄고 서식 번호 env 없이 시험용 앱에서 시공 잡기 제안을 승인했을 때 Solapi · 웹 푸시 호출이 0 인지(가짜로 센다).
7. 평가: 돈 상한 0 인 채로 [시험 다시 돌리기] 길을 불렀을 때 409 이고 두뇌 호출이 0 인지.
8. 길 목록: 평가 돌리기 · 수준 저장이 `ADMIN_OPS`, 승인 · 거절 · 나중에가 `STAFF_MUTATION` 으로 올라 있고 `guard_count` 가 맞는지.

**보고**: 명령마다 출력 원문 · 빨간 것마다 원인 갈래(이 가지 · 다른 세션 · 환경)와 근거 · 전체 시험은 돌리지 않았다는 한 줄(푸시 직전 `scripts/ops/pre_push_smoke.ps1` 한 번이 맡는다).
