판정: 설계 — 사용자 "이대로 구현" 승인(11-14), 구현 전

# FOMS 접목판 설계서 — 지금 FOMS 위에 온톨로지 층 · 할 일 층 · AI 직원 얹기 (판 1, 2026-11-14)

> 목업(화면 정본): `docs/design/mockups/foms-graft/` 판 12장 — 살아 있는 캔버스 https://claude.ai/artifact/P83NJbo7Jer1fLnaJoVeUV
> 개념 정본: `docs/plans/2026-11-13-foms-zero-rebuild-design.md`(원점 설계). 접목판은 그 설계의 **새 서버 · 새 DB 를 쓰지 않는다** — Flask + PostgreSQL + 지금 표 그대로.
> 실행 계획 · 원장: `docs/plans/2026-11-14-foms-graft-plan.md` · 일꾼 지시문: `docs/plans/2026-11-14-foms-graft-worker-prompts.md`
> 목업 안 이름 · 주소 · 전화 · 금액 · 주문 번호는 모두 지어낸 예시다. 이 설계서 · 시험 · 지시문에도 실제 손님 · 직원 이름 · 금액 · 비밀 값은 적지 않는다(저장소가 공개다).

## 0. 한 줄

지금 화면 · 표 · API 는 그대로 두고, 그 위에 (1) 지금 칸을 가리키는 **ERP 물건 이름표**(읽기만), (2) 지금 기능을 이름 붙여 감싼 **할 일**(제안 → 사람 승인 → 지금 기능 실행 → 기록), (3) **AI 직원**(읽기 도구 + 할 일 제안)을 얹는다. 화면은 분홍 점선 칸만 더하고, 회사 지식(`/brain`)만 새 디자인 시스템으로 다시 그린다. 모든 새 칸은 스위치가 있고 처음 값은 끔이다.

## 1. 목표 · 하지 않는 것

### 1.1 목표 (Main 판의 다섯 단계 → 만들 것)

| 단계 | Main 판 글 | 만들 것 | 스위치 | 일감 |
|---|---|---|---|---|
| 1 | 회사 지식을 새 UI 로 | `/brain` 전 화면을 `foms-ds.css` 로 다시 그린다. 기능은 지금 그대로(승인 대기 · 찾기 · 지식 표 · 지식 카드 · 다시 확인 · 판 · 유형 지도 · 온톨로지 · 물어보기 · 뇌 보기). 옛 화면 파일은 지우지 않는다 | `FOMS_GRAFT_BRAIN_UI` | T2 · T3 · T4 · T5 |
| 2 | ERP 물건 이름표 | 물건 종류 10개를 코드 목록으로 선언(지금 표 · 칸을 가리킴). 주문 · 방문 읽기 도구(허용 목록 · 가림). 물어보기가 주문 번호가 든 질문에 주문 · 방문을 읽어 답한다. 온톨로지 화면에 ERP 물건 · 할 일 종류. 지식 카드 '쓰인 곳' | `FOMS_GRAFT_ERP_READ` | T1 · T6 · T4 · T5 |
| 3 | 할 일 다섯 감싸기 | 할 일 목록(이름 · 넣을 값 · 막는 조건 · 누가 · 감싼 기능) + 제안 표 + 승인 · 거절 · 나중에 + 실행 + 기록. 승인 대기 한 곳에 지식 고침과 ERP 할 일 제안이 같이 보인다 | `FOMS_GRAFT_ACTIONS` | T1 · T7 · T8 |
| 4 | 지금 화면에 칸 하나씩 | PC 작업 목록 '현재 작업' 칸 AI 칩 + 위 아이콘 줄 회사 지식 수(②), 태블릿 '현재 작업' 칩 + 오른쪽 AI 제안 상자 + 레일 회사 지식(③), 폰 '처리 대기' AI 제안 칸(④), 채널톡 작은 창 근거 줄 + 할 일 제안 줄(⑤) | `FOMS_GRAFT_CELL_PC` · `_TABLET` · `_MOBILE`, 상담 관리 칸 둘 | T8 · T9 |
| 5 | AI 수준 올리기 | AI 직원 화면(다섯 · 도구 · 할 일별 자율 수준 · 2주 승인율 · 시험 · 실행 기록). 수준 표 저장 · 사장님만 바꿈. 운영 AI · 일정 AI 의 제안 규칙(시험 중) | `FOMS_GRAFT_PROPOSERS` + 수준 표 | T10 |

### 1.2 하지 않는 것 (판 1)

- 지금 주문 · 실측 · 도면 · 생산 · 시공 화면의 모양 · 버튼 · API 를 바꾸지 않는다. 분홍 점선 칸만 더한다.
- 지금 화면 버튼을 할 일 층으로 돌려 보내지 않는다. 사람이 지금 화면에서 누르는 길은 그대로이고 기록도 지금 그대로다. 할 일 층은 **제안에서 시작한 실행**만 맡는다.
- AI 가 사람 승인 없이 실행하는 길(자율 수준 3)의 코드를 만들지 않는다. 수준 표는 0 ~ 2 까지만 받는다(3 은 저장 거절).
- 주문 상태 13단계 한 길, 시공 팀 · 인원 계산(폭 합 ÷ 300), 시공 날짜 안내 알림톡은 지금 코드에 바탕 자료 · 서식이 없어 만들지 않는다(9절 · 11절).
- 새 폰 알림(푸시) 종류를 만들지 않는다. 판 1 의 알림은 수 배지다.
- `foms-now.css` · `foms-now2.css` 는 목업에서 지금 화면을 흉내 낸 파일이다. 싣지 않는다.
- React · FastAPI · Blueprint npm 묶음을 넣지 않는다. `foms-ds.css`(값만 같은 작은 CSS)를 쓴다.

## 2. 지금 코드 (사실 — 11-14 `origin/deploy` `01d596f7f` 에서 읽음)

| 무엇 | 어디 |
|---|---|
| 회사 지식 화면 길 | `foms/web/brain.py:49`(탭 여덟) · `:120`(`/brain`) · `:151`(`/brain/items/<키>`) · `:180`(`/brain/ask`) · 메뉴 판정 `:54` |
| 회사 지식 읽기 API | `foms/api/brain.py:84` ~ `:159`(찾기 · 표 · 카드 · 유형 지도 · 판 · 이웃 · 점 · 품질 · 온톨로지) |
| 제안함 · 결정 API | `foms/api/brain_review.py:137` ~ `:208` — 쓰기는 모두 이름 있는 액션(`foms/services/brain/actions.py` 목록 · `action_runner.py` `perform`) |
| 물어보기 | `foms/api/brain_chat.py:85`(상태) · `:105`(묻기) · `:129`(피드백) · `:153`(설정), 답 길 `foms/services/brain/chat_answer.py:164`. **주문 질문은 지금 '모름'**(`chat_answer.py:95` · 지시문 `chat_prompt.py:38`) |
| 여는 사람 | 화면 `foms/services/brain/access.py:28`(ADMIN + 층 승인자 팀 MANAGER, 그 밖 404) · 결정 `:63` · 물어보기 `chat_access.py:37` |
| 온톨로지 탭 · 능력 질문 | `foms/services/brain/ontology_view.py:112` · `:178`, 질문 61개 `ontology_cqs.py`(ERP 물건은 '아직 없음' — `:33`) |
| 쓰인 횟수 | `foms/services/brain/usage.py:44` · `:65` — 표 `brain_usage`(키 · 읽은 쪽마다 합 · 마지막 때뿐, 날짜별 기록 없음) |
| 화면 파일 | `templates/brain/**`(17개) · `static/js/brain/*.js`(28개 — 순수 계산 `*-view.js` 는 node 시험이 있다) · `static/css/contexts/brain/brain.css` |
| 주문 정본 | `models.py:30` `Order` — 구조화 칸 `structured_data`(`:101`) · 납작 칸 `erp_stage_code`(`:115`) · `erp_measurement_date`(`:111`) · `erp_construction_date`(`:112`) · `as_axis_status`(`:124`) · 판 번호 `mutation_version`(`:108`) |
| 시공일 쓰기(정본 서비스) | `foms/services/orders/construction_schedule.py:65`(값 검사) · `:78`(`write_construction_schedule`) · `:147`(알림 마무리) · `:163`(협력사 희망 확정). 부르는 길 `foms/api/shipment/partner_request.py:55` |
| AS | 접수 본체 `foms/api/cs/as_orders.py:595`(`register_as_from_payload`) · 방문일 `foms/services/orders/as_cycle_service.py:575`(`schedule_as_cycle`) |
| 알림톡(실측 예약 서식 하나뿐) | `foms/services/kakao_alimtalk.py:879`(`send_alimtalk`) · 손으로 보내기 길 `foms/api/kakao/` `api_alimtalk_send_manual` |
| 단계 넘기기 | `foms/api/quest.py:370`(`api_order_quest_approve` — 약 430줄, 요청에 묶인 처리기) · 엔진 `foms/services/orders/quest_transition_service.py:201` · `order_transition_service.py:310` |
| 주문 읽기 권한 | `foms/services/orders/order_mutation_policy.py:456`(`user_can_read_order`) · 정책 표 `POLICY_REGISTRY` · 길 목록 `docs/harness/foms_order_mutation_policy_manifest.json` |
| 상담 AI 가 이미 하는 주문 읽기 | `foms/services/cs_agent/order_find.py` · `order_block.py`(허용 목록 `FIELDS`) · `order_step.py` — 설계서 `2026-11-12-ontology-grounded-cs` 5.5 · 5.6 |
| 채널톡 작은 창 | `templates/cs/cs_agent_wam.html` · `foms/web/cs_draft_wam.py` · `foms/services/cs_agent/wam_functions.py` · `static/js/cs-agent/wam-draft.js` |
| PC 대시보드 '현재 작업' 칸 | `templates/orders/partials/dashboard_grid.html:104` · 줄 자료 `foms/services/orders/dashboard_dto.py:30` |
| 태블릿 | 표 `templates/orders/partials/tablet_workqueue_grid.html:66` · 오른쪽 상세 `tablet_dashboard_sheet.html:23`(길 `foms/web/orders/dashboard.py:629`) · 레일 `templates/partials/shared/foms_tablet_rail.html`(항목 목록 `foms/services/context_processors.py:475`) · 나뉜 화면 레일 `foms_side_tab.html`(`foms/services/foms_split_view.py:132`) |
| 폰 홈 '처리 대기' | `templates/orders/partials/dashboard_mobile_tower.html:147` |
| PC 위 아이콘 줄 | `templates/partials/shared/layout_nav.html:11` ~ `:60`(긴급 · 내 할 일 · 협력사 · 알림) |
| 스위치 틀 | `foms/services/feature_flags.py:106`(`is_enabled_for_user` — `<이름>_ENABLED` + `<이름>_COHORT`) · 상담 관리 칸 `foms/services/cs_agent/onto_settings.py`(꼴 예시) |
| 밤 일 | `tools/cron/nightly.py:50`(`NIGHTLY_STEPS` — 단계 목록 정본) |
| 마이그레이션 머리 | `prodpart_00`(하나뿐 — 시험이 '머리 하나'를 강제) |

## 3. 자료 약속 (이름을 그대로 쓴다 — 일꾼들이 같은 이름으로 따로 만든다)

### 3.1 꾸러미

| 꾸러미 | 뜻 | 층 규칙 |
|---|---|---|
| `foms/services/graft_flags.py` | 스위치 이름 · 판정 한 곳 | services |
| `foms/services/erp_ontology/` | ERP 물건 목록(`objects.py`) · 읽기 도구(`read.py`) · 물어보기 잇기(`ask.py`) | services — DB 는 읽기만 |
| `foms/services/erp_actions/` | 할 일 목록(`registry.py`) · 제안 생명주기(`lifecycle.py`) · 실행기(`runners.py`) · 미리 보기(`preview.py`) · 보는 사람(`access.py`) · 화면 값(`views.py`) | services |
| `foms/services/ai_staff/` | AI 직원 목록(`registry.py`) · 수준(`levels.py`) · 숫자(`metrics.py`) · 실행 기록(`runs.py`) · 훑기 규칙(`sweeps.py`) | services |
| `foms/persistence/graft/models.py` | 새 표 셋의 ORM | persistence — services 를 import 하지 않는다 |
| `foms/api/erp_actions.py` · `foms/api/erp_action_runners.py` · `foms/api/ai_staff.py` | JSON API · api 층에 있는 기능을 부르는 실행기 | api |

층 방향 래칫(`tests/contracts/runtime/test_layer_dependency_ratchet.py`): services → api · services → web · api → web 의 **새 import 금지**, 함수 안 지연 import 도 순증 금지. 그래서 api 층 함수(`register_as_from_payload`)를 부르는 실행기는 `foms/api/erp_action_runners.py` 에 두고, 감사 줄은 `foms.web.auth.log_access` 대신 `SecurityLog` 줄을 같은 트랜잭션에 직접 싣는다(본보기 `foms/api/orders/measurement_visit.py:90`).

### 3.2 ERP 물건 목록 — 지금 표를 가리키기만 한다 (`foms/services/erp_ontology/objects.py`)

물건 종류 10개. 새 표 없음. 표시 이름 · 코드 이름 · 정본 자리 · 읽기 도구가 있나.

| 화면 이름 | 코드 이름 | 정본 자리(코드에서 확인) | 판 1 읽기 도구 |
|---|---|---|---|
| 주문 | `erp:order` | `orders`(`models.py:30`) + `structured_data` | 있음 |
| 주문 품목 | `erp:order_item` | `structured_data.items[]`(이름 `product_name`) + `order_item_identities`(`models.py:429`) | 이름만(주문 읽기 안) |
| 손님 | `erp:customer` | `structured_data.parties.customer.{name, phone}` · 숫자만 `orders.erp_phone_digits` | 없음 — 가림(AI 에 안 감) |
| 현장 | `erp:site` | `structured_data.site.{address_full, address_main}` · `orders.is_regional` | 지방 여부만 |
| 방문 | `erp:visit` | 실측 `structured_data.schedule.measurement.{date, time}` · 시공 `schedule.construction.{date, time}` · AS `schedule.as_visit.date` · 배송 `orders.shipping_scheduled_date` · 날짜 찾기 표 `order_schedule_dates`(`models.py:319`) | 있음 |
| 도면 | `erp:drawing` | `drawing_revisions`(`models.py:699`) · `drawing_revision_requests`(`:804`) | 선언만 |
| 생산 작업 | `erp:production_run` | `production_runs`(`models.py:486`) | 선언만 |
| 출고 | `erp:shipment` | `orders.shipping_scheduled_date` + 물류 축(`foms/services/orders/state_axes.py`) | 선언만 |
| 협력사 발주 | `erp:partner_order` | `orders.partner_org_id`(`models.py:64`) + `partner_orgs` | 선언만 |
| AS 건 | `erp:as_case` | `order_as_cycles`(`models.py:609`) + `orders.as_axis_status` | 상태 · 방문 날만(주문 읽기 안) |

**주문 속성 표(온톨로지 화면 '속성 ↔ 지금 칸') — 목업 값을 코드에 맞춰 고친 것**

| 속성 | 목업에 적힌 칸 | 실제 정본(이 설계서가 정함) | 읽기 · 쓰기 |
|---|---|---|---|
| 주문 번호 | `orders.id` | `orders.id` — 화면 표기는 `#<번호>`. 목업의 `L-24117` 같은 머리글자 번호는 없다 | 읽기만 |
| 상태 | `orders.status` · 13단계 | 단계 `structured_data.workflow.stage` → 납작 칸 `orders.erp_stage_code`(`RECEIVED` · `MEASURE` · `DRAWING` · `CONFIRM` · `PRODUCTION` · `CONSTRUCTION` · `CS` · `COMPLETED` 여덟 — `erp_policy_constants.py:14`) + AS 축 `orders.as_axis_status`. `orders.status` 는 옛 화면용 비춤 값이라 정본이 아니다 | 할 일로만(단계 넘기기) |
| 손님 이름 | `orders.customer_name` | `structured_data.parties.customer.name`(ERP 주문). `orders.customer_name` 은 옛 칸 | 사람만 · 가림 |
| 전화 | `orders.phone` | `structured_data.parties.customer.phone` · 숫자만 `orders.erp_phone_digits` | 사람만 · 가림 |
| 현장 주소 | `orders.address` | `structured_data.site.address_full`(없으면 `address_main`) | 사람만 · 가림 |
| 품목 | `structured_data.items[]` | 같음 | 사람만(판 1 에 품목 고치기 할 일 없음) |
| 실측 날짜 | `orders.measurement_date` | `structured_data.schedule.measurement.date`(+ `.time` 은 예정 값) · 납작 칸 `orders.erp_measurement_date`. `orders.measurement_date` 는 옛 칸 | 바로가기(3.3 `move_measurement`) |
| 시공 날짜 | `structured_data.schedule.construction.date` | 같음(+ `.time`) · 납작 칸 `orders.erp_construction_date` — 근거 `construction_schedule.py` 머리말 | 할 일로만(시공 잡기 · 방문 옮기기) |
| 담당 영업 | `structured_data.parties.manager` | 같음 — 대표 `.name`, 여러 명 `.names` | 사람만 |
| 결제 금액 | `orders.payment_amount` | `structured_data.payment` · `pricing` 에서 계산해 맞춘 납작 칸 `orders.payment_amount`(`erp_sync_columns.py:151`) | 사람만 · 돈(AI 에 안 감) |

**읽기 도구(`read.py`)** — 상담 AI 의 허용 목록(`cs_agent/order_block.py` `FIELDS`)과 같은 생각으로, 납작 칸을 먼저 읽는다.

- `order_card(order) -> OrderCard`: `order_id` · `stage`(코드) · `stage_label` · `stage_since` · `products`(이름 다섯까지 · 가림 검사를 지난 것만) · `owner_team` · `regional` · `self_measure` · `as_state`. 화면 전용 칸 `manager_label`(직원 이름 — 화면 옆 창에만 쓰고 모델 재료에는 넣지 않는다).
- `visits(order) -> list[Visit]`: `kind`(`measurement` · `construction` · `as_visit` · `shipping`) · `day` · `time_label`(실측 시간은 '예정') · `state`(`planned` · `done`).
- 싣지 않는 것(시험이 강제): 손님 이름 · 전화 · 주소 · 금액 · 메모 · 협력사 이름 · 직원 연락처.
- `prompt_lines(card, visits) -> list[str]`: 모델에 주는 줄. 사람이 적은 글(품목 이름 · 시간대)은 가림 검사(`cs_agent/masking.require_masked`)를 지난 것만.
- 한 번에 주문 하나(기본 키로 읽기). 목록 질의가 필요하면 `order_schedule_dates` 의 `(kind, date, order_id)` 색인을 탄다.

### 3.3 할 일 목록 — 지금 기능에 이름을 붙여 감싼다 (`foms/services/erp_actions/registry.py`)

할 일 하나(`ActionSpec`)의 칸: `name` · `label` · `target`(물건 종류) · `params`(이름 · 꼴 · 화면 이름) · `policy_id`(지금 정책 표의 이름 — 감싼 길과 같은 것) · `mode`(`run` 승인하면 실행 · `link` 바로가기만 · `human` 사람만) · `level_cap`(AI 가 가질 수 있는 가장 높은 수준) · `wraps`(감싼 기능 글) · `phone_ok` · `wam_inline`.

| `name` | 화면 이름 | 감싼 지금 기능 | `policy_id` | `mode` | `level_cap` |
|---|---|---|---|---|---|
| `schedule_construction` | 시공 잡기 | `validate_schedule_input` → `write_construction_schedule` → `finalize_schedule_notifications`(시공일이 빈 주문). 협력사 주문은 `confirm_partner_request` | `CONSTRUCTION_SCHEDULE_EDIT` | `run` | 2 |
| `move_construction` | 방문 옮기기(시공) | 위와 같은 함수(시공일이 이미 있는 주문). 사유가 필요한 변경이면 승인 창에서 받은 사유를 지금 사유 원장(`change_reason.py` `attach_reason`)에 남긴다 | `CONSTRUCTION_SCHEDULE_EDIT` | `run` | 2 |
| `schedule_as_visit` | 방문 옮기기(AS) | `schedule_as_cycle` | `ERP_EDIT` | `run` | 2 |
| `register_as` | AS 접수 | `register_as_from_payload` | `CONSTRUCTION_EDIT` | `run` | 2 |
| `send_measure_alimtalk` | 알림톡 보내기(실측 예약) | `send_alimtalk`(서식은 지금 있는 실측 예약 하나) | `STAFF_MUTATION` | `run` | 1 — 손님에게 나가는 글 |
| `add_construction_note` | 시공 메모 더하기 | **새 서비스 함수**(`foms/services/orders/construction_note.py`) — `structured_data.notes.construction_note` 끝에 한 줄. 줄 잠금 · 판 번호 올리기 · 변경 원장 · 도면팀 알림은 `write_construction_schedule` 과 같은 부품 · 같은 순서 | `ERP_EDIT` | `run` | 2 · `wam_inline` |
| `advance_stage` | 단계 넘기기 | `quest.api_order_quest_approve`(요청에 묶인 처리기) | `STAFF_MUTATION` | `link` | 1 |
| `assign_draftsman` | 도면 담당 맡기기 | `erp_orders_draftsman.api_order_assign_draftsman` | `STAFF_MUTATION` | `link` | 1 |
| `move_measurement` | 방문 옮기기(실측) | `orders.update_order_field` 의 `measurement_date` | `ERP_EDIT` | `link` | 1 |
| `cancel_order` | 주문 취소 | — | — | `human` | 사람만 |

- `mode = link` 는 승인 대기 카드에 [승인] 대신 [주문에서 처리]가 뜬다(그 주문 화면으로 간다). 사람이 지금 화면에서 처리하면 다음 훑기 때 끝난 조건(`verify`)을 보고 제안을 닫는다. 까닭: 감싼 기능이 요청에 묶인 긴 처리기라 서버에서 그대로 부를 수 없고, 본체를 서비스 함수로 빼는 일은 코어 변경이라 이 판에 넣지 않았다(11절 결정 1).
- 넣을 값 꼴: `date`('YYYY-MM-DD' · 오늘 이후) · `time_slot`(`""` · `오전` · `오후` · `종일` — `construction_schedule.TIME_CHOICES`) · `masked_text`(가림 검사 0 · 길이 상한) · `choice`. 전화 · 주소 · 금액을 받는 꼴은 없다.
- 할 일마다 함수 셋: `check(order, params) -> 막는 까닭 | None`(막는 조건) · `preview(order, params) -> [바뀌는 칸]` · `verify(order, params) -> bool`(끝난 조건 — 되맞추기와 `link` 닫기에 쓴다).
- 거절 까닭 다섯(`REJECT_CODES`): `wrong_date` 날짜가 틀림 · `misread` 손님 말을 잘못 읽음 · `no_slot` 팀 자리 없음 · `already_done` 이미 처리함 · `other` 그 밖.

### 3.4 제안 표 — 새 표 `erp_action_proposals` (회사 지식 제안 표를 다시 쓰지 않는다)

**다시 쓰지 않는 까닭**: `brain_changes`(`foms/persistence/brain/models.py:121`)는 지식 항목 키 · 판 · 층 · 등급 · 관문에 묶여 있고, 검사 제약(`op` 여섯 · `status` 넷)과 제안함 질의 · 주 상한 · 판 만들기가 그 꼴을 믿는다. 주문 번호 · 실행 결과 · 되맞추기 상태를 끼워 넣으면 지식 쪽 규칙이 깨진다. 승인 대기 화면에서만 한 곳으로 모은다(3.6).

마이그레이션 `graft_00`(`down_revision = 'prodpart_00'`) — 빈 표 셋을 더하기만 한다. `downgrade()` 는 표를 지운다. 꼴은 `brain_02` 를 따른다(`COLUMNS` · `CHECKS` · `INDEXES` 표를 두고 시험이 ORM 과 견준다, `models` 를 import 하지 않는다). 머리는 하나여야 한다.

`erp_action_proposals`

| 칸 | 꼴 | 뜻 |
|---|---|---|
| `id` | Integer PK | |
| `action` | String(40) NOT NULL | 3.3 의 `name` |
| `proposed_by` | String(64) NOT NULL | `agent:cs` · `agent:ops` · `agent:schedule` |
| `order_id` | Integer NULL · FK 없음 | 감사 원장 규칙(주문을 지워도 기록은 남는다) |
| `params` | JSON | 실행기에 넣을 값(개인정보 꼴 없음) |
| `preview` | JSON | `[{"field", "before", "after"}]` — 제안 때 계산 |
| `reason` | Text | 가린 글만 · 500자 |
| `evidence` | JSON | `[{"kind": "brain"/"order"/"cs_turn"/"visit", "ref", "label"}]` 여덟까지 |
| `level` | Integer NOT NULL | 제안 때 수준(1 · 2) |
| `status` | String(16) NOT NULL | `open` · `executing` · `executed` · `failed` · `rejected` · `expired` · `superseded` |
| `reject_code` | String(24) NULL | 3.3 거절 까닭 |
| `base_version` | Integer NULL | 제안 때 `orders.mutation_version` |
| `dedupe_key` | String(120) NOT NULL | `<action>:<order_id>:<값 지문>` |
| `source_kind` · `source_ref` | String(16) · String(64) NULL | `cs_turn` · 차례 번호, `sweep` · 실행 기록 번호 |
| `decided_by` · `decided_at` · `decided_action` · `view_ms` | Integer · DateTime · String(16) · Integer NULL | 사람(로그인 사용자)만 |
| `edited_params` | JSON NULL | 고쳐서 승인한 값 |
| `result` · `error_code` | JSON · String(48) NULL | 실행 결과(코드 · 변경 묶음 번호 — 글 없음) |
| `snoozed_until` · `snoozed_by` | DateTime · Integer NULL | '나중에' |
| `created_at` · `expires_at` | DateTime NOT NULL · NULL | UTC |

색인: `ix_erp_action_proposals_status_created(status, created_at)` · `ix_erp_action_proposals_order_status(order_id, status)` · `uq_erp_action_proposals_open_dedupe(dedupe_key) WHERE status = 'open'`(부분 유일 — PostgreSQL · SQLite 둘 다). 검사: `status` 값 목록.

`brain_usage_events` — '쓰인 곳'(지난 2주 수 · 최근 줄). 칸: `id` · `item_key` String(120) · `reader` String(16)(`cs_draft` · `erp_action` · `chatbot`) · `ref_kind` String(16) · `ref_id` String(64) · `used_at` DateTime. 색인 `(item_key, used_at)` · `(ref_kind, ref_id)`. `item_key` 에는 지식 키와 ERP 물건 키(`erp:order/<번호>`)를 같이 쓴다. `brain_usage`(합)는 그대로 둔다. 쓰기 · 읽기 도우미 `foms/services/brain/usage_events.py` — `record_uses(session, keys, reader, ref_kind, ref_id, now)` · `uses_window(session, key, days)` · `recent_uses(session, key, limit)` · `refs_of(session, ref_kind, ref_id)`.

`ai_agent_runs` — AI 직원 실행 기록. 칸: `id` · `agent` String(16) · `started_at` · `total_ms` · `source_kind` · `source_ref` · `steps` JSON(`[{"tool", "what", "detail", "ms"}]` — 코드 · 수만) · `outcome` String(24) · `proposals` Integer. 색인 `(agent, started_at)`.

**생명주기**

```
만들기(propose) ─▶ open ──승인──▶ executing ──성공──▶ executed
                    │                └──실패──▶ failed(카드에 [다시] — open 으로)
                    ├─거절(까닭)──▶ rejected   (같은 dedupe_key 는 다시 만들지 않는다)
                    ├─기간 끝남──▶ expired     (밤 단계 — 날짜가 지났거나 7일)
                    └─같은 주문 · 같은 할 일의 새 제안──▶ superseded
```

- **만들기**: `check` 가 막으면 만들지 않는다. 같은 `dedupe_key` 의 `open` 이 있으면 그대로, `rejected` 가 있으면 만들지 않는다. 근거 지식 키는 `record_uses(..., reader='erp_action')`.
- **승인(두 걸음)**: ① 제안 줄을 잠그고 `open` 인지 · 누른 사람이 `policy_id` 를 지나는지(`evaluate_policy`) · 주문 읽기 권한(`user_can_read_order`) · `check` 를 다시 본다. 주문 판 번호가 `base_version` 과 다르면 미리 보기를 새로 계산하고, 저장된 '지금' 값과 다르면 **409 `ACTION_BASE_CHANGED`** 로 새 카드를 돌려준다(제안은 `open` · 새 값으로 갱신). 통과하면 `executing` + 결정한 사람을 적고 커밋. ② 실행기를 돈다(감싼 기능의 커밋 방식 그대로 — `send_alimtalk` · `register_as_from_payload` 는 스스로 커밋한다). ③ `executed` · `failed` + 결과 + 감사 줄을 적고 커밋.
- **되맞추기**: `executing` 으로 2분 넘게 남은 줄(②와 ③ 사이에 죽음)은 `verify` 가 참이면 `executed`, 아니면 `open` 으로 되돌린다. 승인 대기 읽기와 밤 단계가 부른다.
- **감사**: `SecurityLog` 줄 `ERP_ACTION_APPROVED` · `ERP_ACTION_REJECTED` · `ERP_ACTION_EXECUTED` · `ERP_ACTION_FAILED`(제안 번호 · 할 일 이름 · 주문 번호 · AI 직원 · 수준 — 글 없음). 감싼 기능이 남기는 지금 기록(주문 일 기록 · 변경 원장 · 사유)은 그대로 남고 `source` 에 `erp_action:<제안 번호>` 를 싣는다. **할 일 기록 = 이 표의 `executed` · `failed` 줄 + 그 감사 줄**이다.
- **한 번만**: 같은 제안을 두 번 누르면 두 번째는 409 `ACTION_NOT_OPEN`. 알림톡 실행기의 중복 막기 열쇠는 `alimtalk:measure:<주문>:action:<제안 번호>`.

### 3.5 누가 보고 누가 누르나

- ERP 제안을 **보는 사람 = 그 할 일을 실행할 수 있는 사람**: 켜진 내부 계정 + `ACTIONS` 스위치 + `policy_id` 통과 + 그 주문 읽기 권한(프리랜서는 자기 주문만). 볼 수 없는 제안은 카드 · 수 · 칩 어디에도 없다(질의 단계에서 거른다 — 회사 지식 제안함과 같은 원칙).
- **승인 대기 화면을 여는 사람이 넓어진다**: 지금은 ADMIN + 층 승인자 팀 MANAGER 뿐이다(`access.py:28`). `ACTIONS` 가 켜진 사람 가운데 실행할 수 있는 할 일이 하나라도 있는 내부 직원은 `/brain?tab=inbox` 를 열 수 있고 **AI 할 일 제안 칸만** 본다(지식 고침 칸 · 다른 탭은 지금 규칙 그대로 — 없는 화면과 같은 404). 판정은 `foms/services/erp_actions/access.py` `actions_viewer(user)` 한 곳. 스위치가 꺼지면 지금과 글자까지 같다.
- 사장님만: 주문 취소 · 돈이 걸린 일은 `mode = human`(화면에 '사람만' 표시, 제안 · 실행 길 없음). 수준 표 바꾸기는 ADMIN 만.
- 협력사 · 바깥 역할 · 꺼진 계정은 어떤 새 API 에서도 404.
- 결정한 사람은 로그인 사용자에서만 받는다(본문의 사람 칸은 읽지 않는다).

### 3.6 한 곳 승인 대기 — API (`foms/api/erp_actions.py`, 머리 `/api/erp-actions`)

지식 고침은 지금 API(`/api/brain/inbox` 등)를 그대로 쓰고, ERP 제안은 아래 API 를 쓴다. 화면(⑥ · ⑫)이 둘을 나란히 그린다. 응답은 모두 `{"success", "data", "error"}` · `Cache-Control: private, no-store`.

| 길 | 답(`data`) |
|---|---|
| `GET /badge` | `{"on": {"actions", "pc", "tablet", "mobile"}, "actions": n, "knowledge": n, "total": n, "labels": [할 일 이름 셋까지]}` — 이 사람 기준 |
| `GET /open?order_ids=1,2,…`(100개까지) | `{"items": {"<주문 번호>": {"id", "action", "label", "agent_label", "can_decide"}}}` — 한 질의(`in_`) |
| `GET /inbox` | `{"cards": [카드], "counts": {"total", "by_agent": {"cs", "schedule", "ops"}, "snoozed"}, "reject_codes": [{"value", "label"}], "est_seconds": n}` |
| `GET /proposals/<id>` | 카드 + `{"reason", "changes": [{"field", "before", "after"}], "steps": [글], "rate": {"days": 14, "decided", "approved", "pct"}, "params": [{"name", "label", "kind", "value", "choices"}], "base_version"}` |
| `POST /proposals/<id>/approve` | 본문 `{"base_version", "edits"?, "reason_code"?, "reason_note"?, "view_ms"?}` → `{"status": "executed", "message", "result"}` · 409 `{"code": "ACTION_BASE_CHANGED" / "ACTION_NOT_OPEN" / "ACTION_PRECONDITION", "card"?}` |
| `POST /proposals/<id>/reject` | 본문 `{"code", "view_ms"?}` |
| `POST /proposals/<id>/snooze` | 다음 날 06:00(한국 시간)까지 접는다 |

카드: `{"id", "action", "action_label", "agent", "agent_label", "title", "created_at", "order_id", "order_href", "field", "before", "after", "evidence": [{"kind", "label", "href"}], "level", "mode", "phone_ok", "base_changed"}`.

- `steps`('승인하면 차례로')는 **감싼 기능이 실제로 하는 일만** 적는다(예: 시공일 쓰기 → 도면팀 · 생산팀 알림 → 협력사 주문이면 시공일 안내 푸시). 목업의 '2팀 폰 알림 · 손님 알림톡 1건'은 지금 기능에 없어 적지 않는다.
- 쓰기 길 셋은 길 목록(`foms_order_mutation_policy_manifest.json`)에 `STAFF_MUTATION` 으로 올리고, 처리기 안에서 할 일의 `policy_id` 를 다시 본다(가드가 꺼진 시험 맥락에서도 뚫리지 않게).

### 3.7 물어보기의 ERP 읽기 (`foms/services/erp_ontology/ask.py` + `chat_answer.py`)

- **언제**: `ERP_READ` 가 켜진 사람의 질문에 주문 번호가 있을 때만(`#123` · `주문 123` · `주문번호 123` · `123번 주문`). 번호가 없으면 지금 그대로('모름 + 주문 화면에서 확인').
- **순서**(지금 순서 사이에 낀다): 가림 → 번호 찾기 → 주문 읽기 권한(`user_can_read_order` — 안 되면 없는 주문과 같은 말) → `order_card` · `visits` → 회사 지식 찾기 → 모델(주문 줄 + 지식 후보 — 도구 없음 · 출력 꼴 고정) → 코드 확인 → 기록.
- **코드 확인**: 근거에 주문 키(`erp:order/<번호>`)가 있어야 `kind = 'erp'` 답을 쓴다. 답 속 날짜 · 숫자는 주문 줄 또는 근거 지식 글에 있어야 한다(없으면 '모름'). 손님 이름 · 전화 · 주소는 모델에 간 적이 없다.
- **바꾸기는 없다**: 일정을 바꿔 달라는 질문이면 "지금 잡힌 날"만 답하고 화면이 '방문 옮기기는 승인 대기로 가요' 줄을 보인다. 물어보기는 제안도 만들지 않는다(판 1).
- **기록**: `brain_questions.evidence_keys` 에 주문 키까지, `record_uses(..., reader='chatbot')`, 실행 기록 `ai_agent_runs`(도구 이름 `mask.apply` · `erp.order.get` · `erp.visit.list` · `knowledge.search` 와 걸린 시간).
- **답 값에 더하는 칸**: `"kind"` · `"erp": null | {"order": {"id", "stage_label", "stage_tone", "products", "manager_label", "masked": ["손님", "현장"]}, "visits": [{"kind", "label", "day", "time_label", "state"}], "tools": [{"name", "what", "ms"}]}`.
- 스위치가 꺼졌으면 지시문 · 출력 틀 · 답이 지금과 글자까지 같다(시험).
- 새 읽기 길: `GET /api/brain/chat/history` — 내가 물은 것만(오늘 · 지난 7일, 가린 글 앞부분).

### 3.8 온톨로지 · 쓰인 곳 읽기 API (`foms/api/brain.py` 에 더한다)

| 길 | 답 |
|---|---|
| `GET /api/brain/ontology`(더함 — `ERP_READ` 켬일 때만 `erp` 칸) | `"erp": {"types": [{"type", "label", "sub", "readable"}], "actions": [{"name", "label", "wraps", "target", "level_label", "mode", "where"}], "cq_erp": n}` · 능력 질문 줄의 ERP 재료는 읽기 도구가 있는 종류면 '있음' |
| `GET /api/brain/ontology/erp/<종류>` | `{"type", "label", "source": {"table", "json"}, "masked": n, "props": [{"name", "column", "shape", "access", "via"}], "links": […], "actions": […], "cq": [번호]}` |
| `GET /api/brain/items/<키>/usage` | `{"days": 14, "by_reader": {"cs_draft", "erp_action", "chatbot"}, "recent": [{"day", "reader", "agent_label", "text", "state", "tone"}], "erp_links": [{"rel", "type", "label", "note"}]}` |

- 능력 질문 점수는 **꺼져 있을 때 지금 값 그대로**다. 켜면 `erp:order` · `erp:schedule` 재료가 '있음'으로 세어져 점수가 오른다(시험지를 쉽게 만드는 것이 아니라 재료가 생긴 것 — 켜기 전 · 뒤 수를 화면에 같이 적는다).
- `recent` 의 글은 가린 글만(상담 차례의 `masked_question` 앞부분 · 제안 제목 · 물어보기 가린 질문).

### 3.9 채널톡 작은 창에 더하는 것 (⑤)

- **근거 줄**: 초안이 쓴 지식 키와 확인된 주문을 차례에 남긴다 — `record_uses(..., reader='cs_draft', ref_kind='cs_turn', ref_id=<차례 번호>)`. 주문은 `erp:order/<번호>` 키로. `cs.draft.get` 답에 `evidence: [{"kind", "label", "href"}]`(셋까지 · `href` 는 FOMS 절대 주소 — 채널톡이 거쳐 여는 창이라 상대 주소는 풀리지 않는다). 칩을 누르면 새 탭으로 지식 카드 · 주문 화면.
- **할 일 제안 줄**: 그 차례에서 나온 `wam_inline` 제안 하나(판 1 은 `add_construction_note` 뿐). `cs.draft.get` 답에 `action: null | {"id", "label", "text"}`. [같이 넣기]를 고른 채 [보내기]가 성공하면 그 제안을 **보낸 직원 이름으로** 승인 · 실행한다(`cs.draft.send` 값 `with_action`). [빼기]면 거절(`other`). 답 보내기가 실패하면 실행하지 않는다. 실행 실패는 답 보내기를 되돌리지 않고 창에 한 줄로 알린다.
- **상담 AI 의 제안 만들기(규칙 — 모델 지시문은 건드리지 않는다)**: 본인이 확인된 주문(`order_step`)이 있을 때만. ① AS 뜻 + 단계가 완료 · CS → `register_as` 제안(승인 대기로) ② AS · 불편 뜻 + 시공일이 앞날 → `add_construction_note`(작은 창 줄) ③ 넘김 까닭 `schedule` + 손님 글에 달 · 날이 똑바로 적힘 → `move_construction` 제안(승인 대기로). 요일만 적힌 글은 만들지 않는다.
- 스위치: 상담 관리 칸 둘 `graft_evidence_enabled` · `graft_actions_enabled`(처음 끔 — 끄면 창 · 답 값이 지금과 같다). 작은 창은 FOMS 로그인이 없어 사람별 스위치를 쓸 수 없다.

### 3.10 AI 직원 (`foms/services/ai_staff/`)

| 열쇠 | 화면 이름 | 지금 | 쓰는 도구(화면 표) | 할 일 |
|---|---|---|---|---|
| `cs` | 상담 AI | 있음 | `knowledge.search` · `cs.thread.read` · `erp.order.find`(11-12 부터 있음) · `risk.check` · `actions.propose`(새로) | 상담 답 초안(1) · 주문 · 방문 읽기(0) · 방문 옮기기 제안(2) · AS 접수 제안(2) · 알림톡 보내기(못 함) |
| `drawing` | 도면 AI 팀원 | 있음(주 1회 루틴) | 지금 그대로 | 판 1 에 새 할 일 없음 |
| `ask` | 지식 물어보기 | 있음 | `mask.apply` · `knowledge.search` · `erp.order.get`(새로) · `erp.visit.list`(새로) | 읽기만(0) |
| `ops` | 운영 AI | 새로 · 시험 중 | `erp.order.list` · `actions.propose` | 알림톡 보내기(1) · 도면 담당 맡기기(바로가기) |
| `schedule` | 일정 AI | 새로 · 시험 중 | `erp.visit.list` · `actions.propose` | 시공 잡기(2) |

- **수준 표**: `SystemSetting` 열쇠 `ai_staff_levels` — `{"<직원>": {"<할 일>": 0 ~ 2}}`. 없으면 목록의 처음 값. 읽기는 `ai_staff/registry.py` `level_of`, 고치기는 `levels.py`. `level_cap` 을 넘는 값 · 3 은 저장 거절. ADMIN 만 바꾼다(`POST /api/ai-staff/levels` — 길 목록 `ADMIN_OPS`). 수준 0 이면 그 직원은 그 할 일 제안을 만들지 않는다.
- **2주 승인율**: `erp_action_proposals` 에서 (직원, 할 일)마다 지난 14일 결정 수 · 승인 수. 결정이 0 이면 `null`(화면 '—').
- **훑기 규칙(운영 AI · 일정 AI — 모델을 부르지 않는 규칙이다. 화면에 '시험 중 · 규칙'이라고 적는다)**
  - 일정 `S1`: 협력사가 바란 시공일이 있고(`partner_intake.requested_construction`) 우리 시공일이 비었고 요청이 열려 있음 → `schedule_construction`(그 날 · 그 시간대).
  - 운영 `O1`: 실측일이 내일인데 실측 예약 알림톡 기록(`structured_data.alimtalk_measurement`)이 없음 → `send_measure_alimtalk`.
  - 운영 `O3`: 단계가 도면인데 도면 담당이 2일 넘게 비어 있음 → `assign_draftsman`(바로가기).
  - 날짜는 `get_today_kst()`. 한 번 훑기에 제안 30개까지. 밤 단계(`NIGHTLY_STEPS`)에 `erp_actions_expire` · `ai_staff_sweep` 둘을 더한다. `FOMS_GRAFT_PROPOSERS_ENABLED` 가 꺼져 있으면 아무것도 만들지 않고 끝난다(단계는 초록).
- **시험(화면 'AI 시험' 칸)**: 판 1 은 지금 있는 숫자만 보인다 — 능력 질문 재료 점수(온톨로지와 같은 값) · 물어보기 평가 묶음의 마지막 점수(있을 때) · 상담 초안 '그대로 보냄' 비율(지난 2주, `cs_agent/metrics.py`). [시험 다시 돌리기] 단추는 판 1 에 없다(11절 결정 4).
- **실행 기록**: 새 길(물어보기 ERP 읽기 · 훑기)은 `ai_agent_runs` 에 단계마다 시간을 남긴다. 상담 AI 는 지금 차례 줄(`cs_agent_turns`)에서 단계를 엮어 보이고 시간은 전체만(`latency_ms`) 보인다.
- API: `GET /api/ai-staff`(목록) · `GET /api/ai-staff/<열쇠>`(상세 — 읽는 것 · 도구 · 할 일 · 수준 · 승인율 · 시험 · 최근 실패 · 비용 · 시간 · 실행 기록 하나) · `POST /api/ai-staff/levels`. 여는 사람: ADMIN + 회사 지식 화면을 여는 MANAGER(읽기), 비용 칸은 ADMIN 만.

### 3.11 함수 · 화면 사이 약속 (따로 일하는 일꾼들이 이 이름으로 만난다)

| 어디 | 이름 | 만드는 일감 | 쓰는 일감 |
|---|---|---|---|
| `foms/services/graft_flags.py` | `enabled(name, user)` · `enabled_global(name)` · 템플릿 전역 `graft_enabled('<짧은 이름>')` | T2 | 전부 |
| `foms/services/erp_ontology/read.py` | `order_card(order)` · `visits(order)` · `prompt_lines(card, visits)` · `order_key(order_id)` | T1 | T6 · T7 · T9 · T10 |
| `foms/services/erp_actions/registry.py` | `ACTIONS` · `parse_params(name, body)` · `dedupe_key(action, order_id, params)` · `REJECT_CODES` · `FAILURES` | T1 | T7 · T8 · T9 · T10 |
| `foms/services/ai_staff/registry.py` | `AGENTS` · `proposer(key)` · `agent_of(proposed_by)` · `level_of(session, agent, action)`(수준 표 `ai_staff_levels` 를 읽고 없으면 처음 값) | T1 | T7 · T9 · T10 |
| `foms/services/brain/usage_events.py` | `record_uses(session, keys, reader, ref_kind, ref_id, now)` · `uses_window` · `recent_uses` · `refs_of` | T1 | T6 · T7 · T9 |
| `foms/services/erp_actions/lifecycle.py` | `propose(session, *, action, proposed_by, order, params, reason, evidence, source_kind, source_ref, level, now)` · `approve(session, proposal_id, *, actor, runners, base_version, edits, reason_code, reason_note, view_ms, now)` · `reject(…, code, …)` · `snooze(…)` · `expire_due(session, now)` · `reconcile(session, now)` | T7 | T9 · T10 |
| `foms/services/erp_actions/runners.py` · `foms/api/erp_action_runners.py` | `SERVICE_RUNNERS`(services 만으로 도는 실행기) · `RUNNERS`(+ `register_as`) | T7 | T9(작은 창은 `SERVICE_RUNNERS`) |
| `foms/services/erp_actions/access.py` · `views.py` | `actions_viewer(user)` · `can_run(user, spec, order)` · `badge(session, user)` · `open_for_orders(session, user, order_ids)` · `inbox(…)` · `detail(…)` | T7 | T8 |
| 새 승인 대기 화면 | `{% include "brain/ds/partials/inbox_erp_nav.html" ignore missing %}` · `inbox_erp_section.html` · `<aside data-ds-inbox-aside>` · `data-ds-phone-list` · `window.FOMS_DS_INBOX = { setCount(kind, n), openAside(node), closeAside(), isPhone() }` · 이벤트 `ds:inbox-ready` | T3 | T8 |
| 지금 화면의 빈 자리 | `data-graft-slot="<주문 번호>"`(현재 작업 칸) · `data-graft-badge`(위 아이콘 · 레일) · `data-graft-tile`(폰 처리 대기) — 모두 `hidden` 으로 그리고 `static/js/foms/graft-cells.js` 가 채운다 | T8 | — |

## 4. 스위치 (모두 처음 끔)

| 이름 | 켜면 | 어디 | 누가 읽나 |
|---|---|---|---|
| `FOMS_GRAFT_BRAIN_UI` | `/brain` 이 새 화면(끄면 옛 화면) | env `_ENABLED` + `_COHORT`(사용자 번호들 또는 `all`) | web |
| `FOMS_GRAFT_ERP_READ` | 물어보기 ERP 읽기 · 온톨로지 ERP 칸 · 쓰인 곳 | 같음 | web |
| `FOMS_GRAFT_ACTIONS` | AI 할 일 제안 보기 · 승인 · 실행 | 같음(쓸모가 있으려면 `BRAIN_UI` 도 켜져 있어야 한다 — 판정 함수가 같이 본다) | web |
| `FOMS_GRAFT_CELL_PC` · `_TABLET` · `_MOBILE` | 지금 화면의 분홍 칸(`ACTIONS` 도 켜진 사람만) | 같음 | web |
| `FOMS_GRAFT_PROPOSERS` | 훑기 규칙이 제안을 만든다 | env `_ENABLED` 만(사람별 아님) | FOMS-cron(밤 단계가 도는 서비스) |
| `graft_evidence_enabled` · `graft_actions_enabled` | 채널톡 작은 창 근거 줄 · 할 일 제안 줄과 상담 AI 제안 만들기 | 상담 관리 칸(DB) | WORKER · web |
| `ai_staff_levels` | 직원 · 할 일마다 수준 | `SystemSetting` | 전부 |

- 판정은 `foms/services/graft_flags.py` 한 곳: `enabled(name, user)` · `enabled_global(name)` · 템플릿 전역 `graft_enabled('<짧은 이름>')`(짧은 이름 `brain_ui` · `erp_read` · `actions` · `cell_pc` · `cell_tablet` · `cell_mobile`).
- **Railway 서비스마다 env 가 다르다.** 화면 스위치는 web 에, `PROPOSERS` 는 밤 단계가 도는 서비스에 넣는다. 한쪽만 넣으면 조용히 꺼진 채다.
- **미리 그려 두는 조각 · 캐시 주의**: 대시보드 표 · 폰 홈은 사람마다 다른 값을 서버 템플릿에 넣지 않는다. 분홍 칸은 빈 자리(`hidden`)만 그리고, 스크립트가 `GET /api/erp-actions/badge` · `/open` 답(`on` 칸 포함)으로 채운다. 자리 자체는 전역 스위치(`enabled_global`)로만 가른다.
- **켜는 차례**: 스테이징 QA 계정 → 사장님 계정 → 팀장 → `all`. 단계 1 → 2 → 3 → 4 순서로, 앞 단계가 1주 탈 없으면 다음. 운영에서 켜는 일은 사장님 말이 있을 때만.
- **되돌리기**: 스위치를 끄면 그 칸이 사라진다(코드 되돌리기 없음). 새 표 셋은 남겨 둔다(빈 표 — 지우려면 `graft_00` 내림).

## 5. 새 회사 지식 화면의 짜임 (⑥ ~ ⑫)

### 5.1 디자인 시스템을 밖으로 새지 않게 싣기

- 실제 파일: `static/css/contexts/brain/ds/foms-ds.css` — 목업 `docs/design/mockups/foms-graft/foms-ds.css` 를 옮기되 **넷을 고친다**: ① `:root { … }` 토큰을 `.f-app { … }` 로(이름이 `--primary` · `--bg` · `--text` 처럼 흔해서 전역에 두면 안 된다) ② 상태 색 `.st-*` 여덟 줄을 `.f-tag.st-*` 로 ③ 아이콘 `.i-*` 88줄을 `.f-i.i-*` 로 ④ `--fs: 1` 을 `--fs: var(--foms-fs, 1)` 로(FOMS 글자 배율을 따른다 — 새 저장 값을 만들지 않는다). 출처 줄(Blueprint © Palantir Technologies, Apache-2.0)은 남긴다.
- 화면별 배치는 `brain-ds-<화면>.css`(class 머리 `fb-`). 목업의 `style="…"` 는 전부 이 파일의 class 로 옮긴다 — 인라인 스타일 래칫(`INLINE_STYLE_RATCHET`)에 새 화면이 더하는 수는 0.
- `@import` 를 쓰지 않는다(자식 핀이 안 올라가는 함정). 화면마다 `asset_url()` 로 따로 싣는다(내용 지문 핀 — 손으로 올릴 `?v=` 없음).
- 이 CSS 들은 `templates/brain/ds/**` 에서만 싣는다. `layout_head.html` 에는 넣지 않는다.
- 시험이 막는 것: `foms-ds.css` 의 모든 선택자가 `.f-` 로 시작(또는 `.f-app` 아래) · `:root` 없음 · 맨 태그 선택자 없음 · 이 파일을 가리키는 템플릿은 `templates/brain/ds/` 뿐.

### 5.2 문서 틀

- `templates/brain/ds/layout.html` — **혼자 서는 문서**(본보기 `templates/partner/layout.html`). 전역 CSS(Bootstrap · `erp-pro.css`)와 전역 메뉴를 싣지 않는다. 그래서 전역 스타일이 새 화면 안으로 새어 들지도 않는다.
- 꼭 싣는 것: `partials/shared/csrf_bootstrap.html`(쓰기 머리글) · 파비콘 · 매니페스트 · **긴급 호출 빨간 창 받는 쪽**(`foms-urgent-alert.css` · `urgent-sound.js` · `foms-urgent-alert.js` + 소켓 싣기 — 새 화면에 있어도 긴급 호출은 떠야 한다. 혼자 서는 문서에서 안 뜨면 그 일감을 BLOCKED 로 보고한다).
- 위 줄(`f-navbar`): ← FOMS(대시보드로) · 회사 지식 · 승인 대기(수) · 찾기 · 물어보기 · 온톨로지 · AI 직원 · 찾기 칸 · 사람. 탭은 지금 권한 그대로 가린다(물어보기 여는 단계 · AI 직원은 ADMIN + 화면 여는 MANAGER).
- 주소는 지금 그대로: `/brain?tab=inbox|search|table|recheck|releases|map|onto|ask|agents` · `/brain/items/<키>` · `/brain/ask`. 탭마다 서버가 그 화면 템플릿 하나를 그린다(옛 화면처럼 한 문서에 탭 여덟을 다 싣지 않는다).

| 주소 | 템플릿 | 판 |
|---|---|---|
| `?tab=inbox` · `recheck` · `releases` | `brain/ds/inbox.html`(왼쪽 길잡이의 보기) | ⑥ · ⑫ |
| `?tab=search` · `table` | `brain/ds/search.html` | ⑦ |
| `/brain/items/<키>` | `brain/ds/item.html` | ⑧ |
| `?tab=ask` · `/brain/ask` | `brain/ds/ask.html` | ⑨ |
| `?tab=onto` · `map` | `brain/ds/onto.html`(유형 지도는 온톨로지 화면의 보기) | ⑩ |
| `?tab=agents` | `brain/ds/agents.html` | ⑪ |

### 5.3 스크립트 — 다시 쓰는 것과 그대로 쓰는 것

- **그대로 쓴다**: 순수 계산 파일(`brain-view.js` · `brain-review-view.js` · `brain-ask-view.js` · `brain-onto-view.js`)과 `brain-dom.js` 의 요청 · 요소 도우미. node 시험이 지키는 판정(휴대폰에서 승인할 수 있나 · 기준 판 경고 · 등급 A 한꺼번에 · 거절 칩 · 확인 글)은 한 벌만 둔다.
- **그대로 싣는다(다시 그리지 않는다)**: 그림 위젯 — 이웃 지도(`brain-neighbours.js` · `brain-graph-view.js`) · 뇌 보기(`brain3d-*.js`) · 유형 지도(`brain-map.js`)와 그 꾸밈(`brain.css` 의 `.brain-*` — 이름 머리가 달라 새 화면과 부딪치지 않는다). 무거운 라이브러리는 지금처럼 그 보기를 열 때만 `import()`.
- **새로 쓴다**: 화면을 그리는 스크립트 `static/js/brain/ds/ds-*.js`(파일마다 300줄 아래 · `defer` · 전역 듣개는 `window.__FOMS_DS_*_BOUND` 한 번만 · 글은 `textContent` 만 · `fetch` 는 `brain-dom.js` 한 곳).
- 옛 화면 파일(`templates/brain/*.html` · `static/js/brain/*.js` · `brain.css`)은 **고치지 않는다** — 스위치가 꺼진 사람은 옛 화면을 그대로 쓰고, 옛 회사 지식 시험(`tests/domains` 48개 · `tests/security` 5개 파일)이 그대로 초록이어야 한다. 옛 화면 지우기는 새 화면이 `all` 로 자리 잡은 뒤 따로 한다.

### 5.4 지금 기능을 하나도 잃지 않는다 (새 화면이 꼭 갖출 것)

승인 대기: 묶음 여섯(① ~ ⑥) 한 줄씩 → 열면 그 묶음 카드 · ① ④ 의 표 한 장 승인(확인 창) · ③ 질문 카드 · 등급 A 모두 승인 · 고쳐서 승인 · 거절 까닭 칩 · 나중에 · 기준 판 바뀜 경고 · 관문 결과 · AI 제안 주 상한 글 · 지식 문서 엇갈림 오류 글(`BRAIN_DOC_SYNC`) · 주소에 연 묶음 남기기. 폰: 칸 하나 고침만 승인, 나머지는 'PC 에서 볼 것'. 다시 확인(아직 맞음) · 판 목록 · 차이 · 판 되돌리기(ADMIN).
찾기 · 표: 유형별 묶음 찾기 · 거르기 여덟 · 정렬 · 쪽 · 미리 보기. 카드: 속성 · 수정 기록 · 연결된 지식 · 이웃 지도 · 뇌 보기 · 고칠 말 · 은퇴 · 지우기 · 옛 판 되돌리기 제안.
물어보기: 묻기 · 근거 칩 · 확인 중 칩 · 확신 · 도움 됨 · 안 됨 · 틀림 · 남은 수 · (ADMIN) 설정 · 빈 지식 · 틀림 신고. 온톨로지: 왼쪽 목록 · 종류 상세(속성 틀 · 채움 · 연결 · 예시) · 연결 종류 · 동작 · 능력 질문 · 유형 지도.

### 5.5 폰

- 640px 아래: 위 줄은 제목 + 수, 아래 탭 넷(승인 · 찾기 · 물어보기 · 나) — ⑫. 누르는 것은 44px 이상.
- 폰에서 승인: 지식은 지금 규칙(칸 하나 고침), ERP 제안은 `phone_ok` 인 `run` 할 일. 카드를 누르면 이유 · 근거를 보고 거절할 수 있다.
- 새 화면은 FOMS 모바일 셸 안이 아니다(혼자 서는 문서). 폰 홈의 분홍 칸(④)만 모바일 셸 안에 있다.

## 6. 지금 화면에 더하는 칸 (② ~ ④ — 지금 모양 그대로, 지금 색 · 글자 · 아이콘으로)

| 판 | 칸 | 붙는 자리 | 채우는 법 |
|---|---|---|---|
| ② PC | '현재 작업' 칸 아래 AI 칩(`AI 제안 · <한 줄>`) → 승인 대기로 | `dashboard_grid.html:104` 칸 안 빈 자리 `data-graft-slot` | 스크립트가 보이는 주문 번호를 모아 `/open` 한 번 |
| ② PC | 위 아이콘 줄 회사 지식 아이콘 + 수 | `layout_nav.html` 알림 단추 앞 | `/badge` · 메뉴는 DB 를 읽지 않는다(지금 시험 `test_nav_badge_lazy_count` · `test_brain_fix_menu_query_count` 그대로 초록) |
| ③ 태블릿 | '현재 작업' 칸 칩 | `tablet_workqueue_grid.html:66` | `/open` |
| ③ 태블릿 | 오른쪽 상세 '현재 작업' 상자 아래 AI 제안 상자(승인 · 고쳐서 · 거절) | `tablet_dashboard_sheet.html:37` 뒤('현재 작업' 묶음 끝) — 새 partial | 서버가 그린다(이 조각은 요청마다 새로 · 캐시 없음) |
| ③ 태블릿 | 레일 회사 지식 + 수 | `foms_tablet_rail.html` 알림 단추 앞(판 ③ 의 레일이 이 모양이다). 태블릿 대시보드에서 실제로 뜨는 레일이 `foms_side_tab.html` 이면 그쪽에도 — 일꾼이 화면에서 확인하고 뜨는 쪽에만 붙인다 | `/badge` |
| ④ 폰 | '처리 대기'에 'AI 제안 승인 대기' 칸(수 + 할 일 이름) | `dashboard_mobile_tower.html:148` `.foms-tower__quick` 안 맨 끝 | `/badge` — 0 이면 숨김 |

- 꾸밈은 새 파일 하나 `static/css/components/foms-graft-cells.css`, 스크립트 하나 `static/js/foms/graft-cells.js`. 전역 스위치가 하나라도 켜졌을 때만 `layout_head.html` · `layout_scripts.html` 에 한 줄씩 싣는다(`asset_url` — 태블릿 묶음 핀 · 그 핀을 베껴 둔 시험 다섯을 건드리지 않는다).
- 태블릿 규칙은 `(min-width: 992px) and (orientation: landscape) and (pointer: coarse)` + `body.erp-mobile-v2-layout` 안에만. 새 글자 크기는 `calc(Npx * var(--foms-fs, 1))`. PC 글자 · 단추를 줄이지 않는다.
- AI 칩 색은 무채색이 아니다 — 목업의 브랜드 남보라(지금 `--foms-color-brand-*` 토큰). 같은 칸에 나란한 '할 일' 배지(노랑) · 단계 배지와 색 차(ΔE2000) 10 이상 · 색약 흉내 뒤 6 이상을 재서 보고한다.
- 조각이 다시 실릴 때(ERP 셸) 스크립트가 다시 돌아도 한 번만 묶인다(`window.__FOMS_GRAFT_CELLS_BOUND`) · 새 조각은 다시 훑는다.
- 목업에 없는 칩 · 상자 · 요약을 더하지 않는다.

## 7. 보안 · 개인정보

- 모델에 가는 글은 가린 글뿐. ERP 읽기는 허용 목록 칸만. 금액은 어떤 AI 길에도 없다.
- 제안의 `reason` · `params` 의 글 칸 · 근거 이름은 가림 검사 0 일 때만 저장(걸리면 그 제안을 만들지 않고 코드만 로그).
- 로그 · 예외 · 감사 줄에 손님 글 · 이름 · 전화 · 주소를 싣지 않는다(번호 · 코드 · 수만).
- 모든 새 쓰기 길: 공용 CSRF · Origin 가드 뒤 + 길 목록 등재 + 처리기 안 권한 재확인. 없는 것과 볼 수 없는 것은 같은 404.
- 시험 · 지시문 · 문서에 실제 이름 · 전화 · 주소 · 금액 · 열쇠를 적지 않는다. 시험 주문은 지어낸 값.
- 시험은 절대 바깥으로 보내지 않는다 — 알림톡 · 채널톡 · 푸시 함수는 가짜로 바꿔 끼운다. 스테이징의 영발방은 실제 직원 방이고 스테이징 알림톡은 실제로 나간다.

## 8. 성능

- 메뉴 · 레일은 DB 질의 0(수는 그린 뒤 채운다). `/badge`: ERP 수 질의 1 + (지식 화면을 여는 사람만) 지금 제안함 수.
- 대시보드 줄마다 질의 금지 — `/open` 한 번(`in_`). 새 표 질의는 3.4 색인을 탄다. JSONB 를 글자로 바꿔 찾지 않는다.
- 새 스크립트는 `defer`. 바깥 CDN 스크립트 없음. 새 화면은 Bootstrap 을 싣지 않아 지금 회사 지식 화면보다 가볍다.
- 훑기는 `order_schedule_dates` 색인과 납작 칸으로 후보를 고르고, 후보만 `structured_data` 를 읽는다.
- `pre_push_smoke.ps1` 의 성능 회귀 가드(G1 ~ G4)가 그대로 초록.

## 9. 목업과 코드가 다른 곳 (코드에 맞춘다)

| 목업 | 코드 | 이 판에서 |
|---|---|---|
| 주문 번호 `L-24117` · `H-24130` | `orders.id` 정수 | `#<번호>` 로 보인다 |
| '상태 길 13단계' · '출고 대기' 단계 | 단계 여덟 + AS 축(`erp_policy_constants.py:14`) | 지금 단계 이름 그대로. '생산 끝 → 출고 대기' 제안은 없다 |
| 방문 옮기기 = `measurement-visit` | 그 길은 '실측만 완료' 체크다(`measurement_visit.py` 머리말). 실측일 바꾸기는 칸 고치기 처리기(`field_update.py:497`) | 실측 옮기기는 바로가기. 시공 · AS 방문만 실행 |
| 단계 넘기기 = `update_order_status` | ERP 주문 단계는 현재 작업 승인(`quest.py:370`)으로 넘어간다 | 바로가기 |
| '금 11-20 오전 · 2팀 3명' · '폭 합 3,000mm ÷ 300 = 3명' | 시공일 쓰기는 날짜 + 시간대뿐(`TIME_CHOICES`). 팀 번호 · 인원 계산 코드는 없다(시공 작업자는 사람 단위 `installation_workers`) | 칩 · 상자는 날짜 + 시간대만 |
| '손님 알림톡 1건 — 날짜 안내' · '알림톡 보내기 · 시공 안내' | 알림톡 서식은 실측 예약 하나(`kakao_alimtalk.py:73`) | 알림톡 할 일은 실측 예약만. 시공일 안내 서식은 카카오 심사가 먼저다 |
| 상담 AI 의 '주문 · 방문 읽기 — 새로 붙음' | 11-12 부터 있다(`order_find.py` · `order_block.py`, 관리 칸 `onto_order_enabled`) | 화면에 '있음'. 새로 붙는 것은 물어보기 쪽 읽기와 제안 |
| `orders.status` · `orders.measurement_date` · `orders.customer_name` · `orders.phone` · `orders.address` 가 정본 | 3.2 표 | 온톨로지 화면은 3.2 의 칸을 보인다 |
| 실행 기록의 단계마다 걸린 시간 | 상담 차례에는 전체 시간뿐 | 상담 AI 는 전체 시간만, 새 길은 단계마다 |
| '시험 다시 돌리기' 단추 · '지난 상담 400개' · '위험 문장 60개' | 물어보기 평가 묶음만 있다(`scripts/maintenance/brain_chat_eval.py`) | 있는 숫자만 보인다 |
| '김영업 폰에 알림' | 승인 대기용 폰 알림 종류 없음 | 수 배지만 |
| 모델 이름 꼬리표 | 설정에 든 값 | 설정 값을 그대로 보인다 |

## 10. 시험 · 내보내기

- **스위치 끔 = 지금과 같음**을 일감마다 시험한다(옛 템플릿 · 답 값 · 지시문 글자).
- 단위 · 화면 구조 시험은 `tests/domains/`, 권한은 `tests/security/`, PostgreSQL 만의 것(부분 유일 색인 · 줄 잠금)은 `tests/postgres/`. 순수 스크립트 함수는 node 시험(지금 꼴).
- 화면은 구조 시험이 문지기다(PNG 견주기 아님). 판과 화면을 나란히 찍어 읽는 일은 일감마다 한다(계획서 '화면 대조').
- 일꾼은 바꾼 파일에 닿는 시험만 돈다(`grep -rl <파일 이름> tests`). 전체 시험은 `deploy` 푸시 직전 `scripts/ops/pre_push_smoke.ps1` 한 번.
- 내보내기: `session/foms-graft` → (사용자 말이 있을 때) `deploy` → 스테이징에서 스위치를 QA 계정에만 켜고 본다 → (사용자가 운영 반영을 말할 때만) 이 세션 커밋만 골라 PR. 운영에서 스위치를 켜는 일도 사용자 말이 있을 때만.
- 승격 순서: 마이그레이션 `graft_00` 이 든 커밋이 먼저(빈 표라 앞뒤 코드와 같이 돌아도 탈이 없다).

## 11. 사용자가 정할 것 (기본값으로 진행하고, 다르면 말해 주면 바꾼다)

| 번호 | 정할 것 | 기본값(이 설계서) | 다른 길 |
|---|---|---|---|
| 1 | 단계 넘기기 · 도면 담당 맡기기 · 실측 옮기기를 승인 대기에서 바로 실행할까 | 판 1 은 바로가기(주문 화면에서 사람이 누름) | 처리기 본체를 서비스 함수로 빼는 코어 변경을 따로 승인받아 2판에 |
| 2 | 운영 AI · 일정 AI 의 첫 제안 | 모델 없이 규칙 셋(`S1` · `O1` · `O3`), 화면에 '시험 중 · 규칙' | 모델로 고르기(운영 열쇠 · 돈 상한 · 시험 묶음이 먼저) |
| 3 | 시공일 안내 알림톡 | 만들지 않음 | 카카오 서식 심사를 넣고 2판에 |
| 4 | 'AI 시험' 칸 | 지금 있는 숫자만, 다시 돌리기 단추 없음 | 상담 평가 묶음(지난 상담 · 위험 문장)을 새로 만들기 |
| 5 | 승인 대기용 폰 알림 | 수 배지만 | 새 알림 종류 + 푸시 |
| 6 | 시공 팀 · 인원 표시 | 날짜 + 시간대만 | 폭 합 ÷ 300 규칙을 코드로(올림 규칙 확인 필요) |
| 7 | 새 화면에서 공지 확인 창 | 뜨지 않음(다음 ERP 화면에서 뜬다). 긴급 호출 빨간 창은 뜬다 | 공지 창도 싣기 |

결정이 서면 `docs/harness/policy/DECISIONS.md` 에 D206 부터 적는다.
