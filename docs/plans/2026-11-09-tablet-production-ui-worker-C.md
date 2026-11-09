# 워커 C 보고 원문 — 회사 단계 흐름·알림 (2026-11-09)

> 원장 `2026-11-09-tablet-production-ui-ledger.md` §3.C 의 본문. 워커(Fable 5.1, effort high, 읽기 전용, 워크트리 `ea4376ea1`) 보고를 그대로 붙였다. 총괄 재확인 결과는 원장 §6 에.

## 표 1. 단계 접점 (생산팀 관점, 11행)

| 단계 | 생산팀이 봐야 하는 것 | 눌러야 하는 것 | 받아야 하는 알림 | 다음 사람에게 넘겨야 하는 것 | 근거 |
|---|---|---|---|---|---|
| RECEIVED 접수 | 없음(생산 보드 밖) | 없음 | 없음 | — | `erp_policy_constants.py:28-40` 담당 CS, `production_change_alerts.py:53-55` PROD_STAGES 에 없음 (확인됨) |
| MEASURE 실측 | 없음 | 없음 | 없음 | — | 같은 근거 (확인됨) |
| DRAWING 도면 | 없음. 도면 전달 알림(`DRAWING_TRANSFERRED`)은 담당 영업·CS 로만 간다 | 없음 | 없음(음성 대조: 도면 단계 전달 → 생산 알림 0, 스펙 `2026-10-27…fix_SPEC.md:88`) | — | `erp_orders_drawing.py:479-492`, `production_change.py:135` 단계 밖이면 `([], False)` (확인됨) |
| CONFIRM 고객컨펌 | **이미 보드에 뜬다** — 버킷 '제작대기'(호환 경로). 카드에 영업 승인 여부(`is_sales_approved`) · 시공일 변경/도면 변경 스트립 | [제작 시작] — CONFIRM quest 완료 + 도면 CONFIRMED 일 때만 200(아니면 409 `QUEST_INCOMPLETE`/`DRAWING_STATUS`) | 시공일 변경·도면 재전달/수정요청·취소 벨(PROD_STAGES 에 CONFIRM 포함) | — (영업·CS 가 승인) | `production_dashboard_display.py:150-163`, `orders.py:826-842`, `production_change_alerts.py:53` (확인됨) |
| **CONFIRM → PRODUCTION 진입** | 제작대기 버킷 = "단계 PRODUCTION + current run 없음". 들어오는 길: ① CONFIRM quest 최종 승인(CS·SALES 둘 다, 또는 assignee 모드 담당 1인 승인, 또는 status COMPLETED)이 곧 `CUSTOMER_CONFIRM` 전이 → PRODUCTION(2026-09-17부터) ② 호환: CONFIRM 주문에서 생산팀이 [제작 시작] | — | — | — | `quest_transition_service.py:6-17,75-78`, `order_transition_service.py:208-215`, `erp_policy_quests.py:46-110`, `quest.py:684-700`, 시험 `test_confirm_to_production_flow.py:1-10` (확인됨) |
| PRODUCTION 생산 | 카드: 고객명·품목(취소 품목 제외)·총 자수·시공(상차)일·D-day·보류·재제작 회차·도면 썸네일·변경 스트립·"취소 품목 N개 있음"·도면 수정 중 배지. KPI 4종(오늘 라인·오늘 상차·지연·보류·이번 주 자수) | [제작 시작](run 발급, 도면 RETURNED/TRANSFERRED 면 409) · [제작 완료] · [제작 취소](run 만 닫음, 단계 유지) · 공정 스텝/불량/보류 · [변경 확인] | 생산 변경 4종 벨·폰 push(생산팀 계정 전원) | [제작 완료] → 단계 CONSTRUCTION, run COMPLETED, 시공팀 몫 | `orders.py:748-905, 911-990, 1053-1060`, `dashboard.py:193-211, 288-325, 420-468`, `tablet_kanban_body.html:168-338` (확인됨) |
| **AUTO_PRODUCTION_D2** | 시공일이 영업일 0~2일 안이면 생산팀 소유 자동 할 일 "생산 D-2 임박 체크"가 붙는다(알림 아님, 할 일 목록) | 할 일 완료(생산 보드 밖, 주문 할 일 탭) | 없음(할 일만) | — | `erp_policy_tasks.py:131,146-158`, `data/erp_policy.json:7,27` (확인됨) |
| PRODUCTION → CONSTRUCTION 출고·시공 | 버킷 '제작완료'(CONSTRUCTION 단계). 출고 겹축 `shipment.logistics_status`(NONE/MEASURED/REGIONAL_MEASURED/SCHEDULED/SHIPPED_PENDING)는 **생산 화면에 안 보인다**(템플릿 grep 0). 출고 2주 판은 출고 PC 화면 전용 | [수정 제작](CONSTRUCTION→PRODUCTION, rework.count+1, 새 run) | 시공일 변경 벨(계속) | 출고팀이 `POST /logistics` 로 겹축 전이(SHIPMENT_EDIT 권한, 생산팀 아님) | `orders.py:1729-1785`, `state_axes.py:12,143-152`, `production_dashboard_display.py:160-161`, 스펙 `2026-11-04…board_SPEC.md:28`(PC 전용) (확인됨) |
| CS | 없음(보드 밖) | 없음 | 없음 | — | PROD_STAGES 밖 (확인됨) |
| COMPLETED 완료 | 없음 | 없음 | 없음 | — | 같음 (확인됨) |
| AS(AS/AS_RECEIVED/AS_COMPLETED) 옆길 | 없음. AS 는 `order.status` 겹축(`AS_RECEIVED` 투영)이고 메인 단계를 바꾸지 않음 → 생산 보드·생산 알림 모두 범위 밖 | 없음 | 없음 | — | `state_axes.py:76,87,312-325`, `as_orders.py:577`, `as_cycle_service.py:52-54` (확인됨) |

### 옆길 요약
- **도면팀 바로 반영(hotfix)**: 생산·시공 단계에서 도면팀 전달 → 영업 확인 없이 CONFIRMED, 이력 `TRANSFER{hotfix:true}` → 카드 스트립 "도면 바뀜(바로 반영)" + 벨 `[생산] 도면 바뀜` **합치기 없음(merge=False → 매번 폰 push)**. `erp_orders_drawing.py:498-506`, `production_change_alerts.py:196-198` (확인됨)
- **품목 일부 취소**: `items[].cancel` 표시. 생산 대표 품목·카드 자수·시트 자수·규격 표·KPI 이번 주 자수는 `active_items`/`drop_cancelled` 로 **뺀다**. 카드에는 "취소 품목 N개 있음" 배지(원본 items 세어 표시). **벨·폰 알림은 안 간다**(`erp_orders_item_cancel.py` 는 `ITEM_CANCELLED_AFTER_CONFIRM` 이벤트 + 캐시 비우기만, `apply_production_change_alert` 호출자 목록에 없음). `dashboard.py:199-202,317,427,447`, `production_dashboard_display.py:44`, `erp_orders_item_cancel.py:20,46` (확인됨)
- **주문 취소(소프트 삭제)**: 벨 `[생산] 주문 취소` + 묘비 카드 14일(개인별 확인 마커 `payload.deleted_at`). `trash.py:242-246`, `mobile_delete.py:138`, `production_change_alerts.py:264-350` (확인됨)
- **시공일 변경**: 카드 스트립 원천 = `CONSTRUCTION_DATE_CHANGED` 이벤트(전역 before_flush `order_date_sync.py:584` 한 곳). 벨은 쓰는 경로가 명시 호출(ERP 폼 `erp_orders_structured.py:803`, 대시보드 칸 `field_update.py:896`, 일정 서비스 `construction_schedule.py:122` — 출고 2주 판도 이 서비스를 탐, 스펙 `:68`). (확인됨)
- **관리자 단계 되돌림**: `stage-override` 는 status+workflow.stage 만 바꾸고 regress 때 그 단계 quest 를 OPEN 으로 되돌림. **production run 은 건드리지 않는다**(`stage_override.py` 에 ProductionRun 참조 0) → PRODUCTION(제작중) 주문을 DRAWING 으로 되돌리면 보드에서 사라지고 run 은 IN_PROGRESS 로 남아, 다시 PRODUCTION 이 되면 바로 '제작중'으로 뜸(추정). 생산 되돌리기 3종(수정 제작·제작 취소·완료 취소)의 관리자 뚫기는 `test_admin_override_production_reverts.py:82-167` 이 계약. `stage_override.py:323-335` (확인됨/추정 표기)
- **AS → 재제작 경로: 없음(확정)**. `as_orders.py`·`as_cycle_service.py`·`as_round_chart.py`·`foms/api/cs/*` 에 PRODUCTION/rework 참조 0. 유일한 "다시 만들기" 경로 2개는 모두 시공 쪽: ① 생산 보드 [수정 제작] `POST /production/rework`(CONSTRUCTION→PRODUCTION, `orders.py:997-1145`) ② 시공 불가 `POST /construction/fail` 사유 `product_defect` → PRODUCTION 되돌림(`construction/orders.py:626-631,640-650`). AS 접수 뒤 재제작이 필요하면 ERP 표현 수단이 없다(메모·채널톡만, 추정).

## 표 2. 알림 표

| 종류 | 발생 조건 | 받는 팀 | 벨 | 폰 push | 카드 빨간 표시 | 60초 합치기 | 사람마다 확인 저장 | 근거 |
|---|---|---|---|---|---|---|---|---|
| 생산 변경 `construction_date` | PROD_STAGES 주문 시공일 바뀜(ERP 폼·대시보드 칸·일정 서비스) | CS·SALES·PRODUCTION (팀당 row 1) | O `[생산] 시공일 변경 — 고객` | O(P1 등록) 신규 row 일 때만 | O 스트립 "시공일 변경 M/D→M/D" | O(같은 주문·같은 종류·같은 팀, 제목 덮어씀 → 이전 from 소실) | 벨: `notification_user_states.read_at` / 카드: `order_events PRODUCTION_CHANGE_ACK(created_by_user_id)` | `production_change.py:44-45,68-98,148-172`, `push_sender.py:102`, `production_change_alerts.py:121-130,173-188` |
| 생산 변경 `drawing`(재전달·수정요청) | 생산 단계 도면 재전달(비hotfix) / 영업 수정 요청 | 같음 | O `[생산] 도면 변경` | O | O "도면 재전달"/"도면 수정요청" | O | 같음 | `erp_orders_drawing.py:508-510`, `erp_orders_revision.py:216-218`, `production_change_alerts.py:190-211` |
| 생산 변경 `drawing_hotfix` | 생산·시공 단계 도면팀 전달(바로 최종) | 같음 | O `[생산] 도면 바뀜` 본문 "…새 도면으로 만들어 주세요" | **O 매번**(merge=False) | O "도면 바뀜(바로 반영)" | **X** | 같음 | `erp_orders_drawing.py:498-506,100-105`, `production_change.py:122-124` |
| 생산 변경 `cancelled` | PROD_STAGES 주문 소프트 삭제 | 같음 | O `[생산] 주문 취소` | O | 묘비 카드 14일 | O | 묘비: ACK payload `deleted_at` 동등 비교(개인별) | `trash.py:242`, `mobile_delete.py:138`, `production_change_alerts.py:311-335` |
| 도면 수정 요청 `DRAWING_REVISION` | 영업/CS 가 수정 요청 | DRAWING 팀 | O | O(P1) | 생산 카드에는 위 `drawing` 종류로만 | — | states | `erp_orders_revision.py:196-205`, `push_sender.py:95` |
| 발주 PUSH(채널톡 발주방) | 영업이 수동 PUSH(`push_kind=drawing`) | **채널톡 도면 그룹방(229625) 멤버 — FOMS 알림 아님** | X | X(채널톡 앱) | X. 재전달로 도면이 바뀌면 주문 화면 칩 "도면 바뀜 — 다시 보내기"(생산 보드엔 없음) | — | 없음 | `channel_policy.py:129-130`, `channel_integration.py:651,837`, `erp_orders_drawing.py:152-174` |
| 긴급 호출 `URGENT_MENTION` | ⚡ 보내기, 사람 직접 지정(팀 탭에 생산 포함) | 지정 사용자 각자 row(`target_user_id`, is_urgent) | O | O(P0 항상) | X | X(주문당 시간당 5회 한도) | states + 긴급 가로막기 창 | `notifications/__init__.py:1112-1114,1155-1192`, `urgent-call.js:18-20,211` |
| 공지 `FOMS_NOTICE` | 관리자 공지(대상: 본사 전체/팀 목록 — PRODUCTION 팀 가능) | 받는 사람마다 row(`target_user_id`) | O(배지) + POPUP 모드면 확인 창 | O(게시 시 1회) | X | — | `notice_acks(read_at, ack_at)` 사람마다 | `models.py:4537-4600`, `notices/push.py:3-4,56-59`, `notices/service.py:89-104` |
| 그 밖 PRODUCTION 수신 | `foms/services/notifications/*` 에서 팀 PRODUCTION 을 수신자로 두는 모듈은 `production_change.py` 하나뿐(출고 `SHIPMENT_ORDER_CHANGED` 는 CONSTRUCTION, 실측 당일은 SALES) | — | — | — | — | — | — | grep 결과, `shipment_change.py:72`, `measure_same_day.py:74` |

**팀 → 사람 퍼짐**: `fan_out_new_notification`(`recipients.py:265-295`) 이 `resolve_recipients_for_notification` 로 `User.team`(정규화 별칭 포함) 활성 내부 직원을 골라 `notification_user_states` 행을 사람마다 만든다. ADMIN 은 팀 경로로 자동 수신 안 함(`recipients.py:14-19`). 폰 push 는 커밋 뒤 `enqueue_push_for_notification` → 수신자별 `notification_push_subscriptions(revoked_at IS NULL)` 기기 전부(`push_sender.py:497-503,777`). 실시간은 `user_<id>` 소켓 방으로 벨 배지(`realtime_notifications.py:21-54`).

## H12 판정 — 확인됨(개인별, 서로 영향 없음)
- 카드 빨간 표시: `collect_production_change_alerts(db, orders, user.id)` 가 **요청한 사람의** `PRODUCTION_CHANGE_ACK`(`created_by_user_id == user_id`) 만 윈도로 쓴다(`production_change_alerts.py:121-130,256-257`). A 가 [확인]을 누르면 `PRODUCTION_CHANGE_ACK` OrderEvent 1건(Order 불변, `orders.py:1366-1375`)이 남고 A 화면만 리로드(`tablet-domain-sheets.js:269-293`). B 의 화면은 fragment 지문(ACK 이벤트도 지문 입력, `production_fragment_version.py:53-54`)이 바뀌어 다시 그려지지만 B 의 user_id 로 계산하므로 **빨간 표시 그대로**. 확인 뒤에도 양쪽에 조용한 "변경됨"(history)은 남는다(`tablet_kanban_body.html:254-256`).
- 벨: 카드 [확인]은 Notification/states 를 전혀 건드리지 않는다 → **B 의 벨도 그대로**, A 의 벨도 그대로(벨 읽음은 별도 `POST /notifications/<id>/read` 가 본인 `notification_user_states.read_at` 만 바꿈, `notifications/__init__.py:610-640`). 묘비는 ack payload `deleted_at` 마커로 개인별.
- 감사 기록: OrderEvent `PRODUCTION_CHANGE_ACK`(payload `source: tablet_kanban`[, `deleted_at`]) + 감사 로그 액션 `PRODUCTION_CHANGE_ACKNOWLEDGED`(표시명 "생산 변경 확인", `audit_message_display.py:198`). idempotency key 가 있으면 receipt 1건(`orders.py:1377-1382`).

## H11 판정 — 확인됨(KPI·시트에서 빠진다)
- 이번 주 자수 `_compute_tablet_prod_kpis` → `active_items(...)` 합(`dashboard.py:317-318`); 오늘 라인·지연·보류는 주문 수 기준이라 품목 무관. 카드 자수 `units_display`(`:199`), 시트 총 자수·규격 표(`:427,446-447`) 모두 `active_items`. 대표 품목 라벨도 `drop_cancelled`(`production_dashboard_display.py:44`). 유일하게 원본 `items` 를 세는 곳은 "취소 품목 N개" 배지(`:201-202`, 의도).

## 상차일 데이터원 (한 줄)
상차일 = 시공일과 같은 키 `structured_data.schedule.construction.date` (`dashboard.py:428,447` → `_prod_sheet_load_md`); 별도 상차일 키는 없음(grep "상차/load_date" 0) — 확인됨.

## 로컬 DB 숫자 (furniture_orders, 읽기만, 접속 문자열 미출력)
- 생산 단계(PRODUCTION) 주문: **0건** (보드 범위 CONFIRM·PRODUCTION·CONSTRUCTION 합 2건, current run 1건 — 단계 분포: 없음 9·완료 3·접수 3·고객컨펌 2, 전체 29건)
- 도면 2장 이상(`drawing_current_files` 길이≥2): **0건** (1장 이상 1건)
- 생산 변경 알림(`notifications.notification_type='PRODUCTION_ORDER_CHANGED'`): **14건** (CS 7·SALES 7 — 생산팀 row 0 = 10-27 변경 전 데이터). 참고: `PRODUCTION_CHANGE_ACK` 0, `CONSTRUCTION_DATE_CHANGED` 1, 생산팀 활성 계정 1, push 구독 0.

> 총괄 메모: 로컬 "생산 단계 0건"은 총괄 측정(erp_stage_code='PRODUCTION' 5건, 그중 2건 DELETED·3건 items 0)과 다르다 — 워커는 다른 열(main stage 투영)을 쓴 듯. 재측정 항목(원장 §2).

## 확인 못 한 것·이유
- 관리자 되돌림 뒤 run 잔존 동작은 코드 추론(추정) — 실행 시험 안 함(읽기 전용 지시).
- 스테이징·운영의 생산팀 계정 수·push 구독 수는 로컬만 셌다(운영 접속 범위 밖). 스펙 10-27 실측은 운영 생산팀 0명.
- 출고 2주 판이 생산에 보이는지는 스펙·템플릿 grep 근거(PC 출고 셸 전용)로 "안 보임" 판정 — 실화면 미확인.
