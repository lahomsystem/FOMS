# 출고 대시보드 시공일 변경 알림 (설계 스펙)

- 작성일: 2026-07-30
- 등급: `**C`
- 상태: **승인 대기**
- 확정된 사용자 결정: ① 감지 범위 = **시공일만** ② ack = **사용자 개인별** ③ 채널 = **화면 + 알림센터 벨 + 모바일 푸시**

## 1. 문제

출고 대시보드는 특정 날짜의 시공 건을 보고 상차·팀 배정·차량을 준비한다.
그 주문의 **시공일이 다른 곳에서 바뀌어도 출고 화면에는 아무 흔적이 없다.**
준비해 둔 상차 목록과 팀 부하가 조용히 어긋난다.

조사 결과 **출고/시공 팀을 대상으로 하는 변경 알림은 코드베이스에 0건**이다
(`target_team` 전수: DRAWING·PRODUCTION·CS/HAUDD/SALES 뿐). 시공 단계 주문의 시공일
변경은 생산 칸반에는 뜨지만(`production_change_alerts.py`) 출고 대시보드에는 뜨지 않는다.

## 2. 기존 자산 조사 요약 (복제 대상 선정)

| 패턴 | 구현 | 구조 | 채택 여부 |
|---|---|---|---|
| ① 도면 | `foms/services/notifications/drawing_order_change.py` | sd pending 플래그 + history + **전역 1회 ack** + 벨 + 푸시 | 벨/푸시 배관만 참고 |
| ② 생산 벨 | `foms/services/notifications/production_change.py` | 호출자가 kind/detail 완성해 넘기는 얇은 emitter. sd 무변경 | 벨 emitter 형태 채택 |
| ③ 생산 칸반 | `foms/services/production_change_alerts.py` | **OrderEvent 윈도 + 개인별 ack + 캐시 밖 배치 1쿼리** | **화면 뼈대로 채택** |
| ④ AS 링크 | `foms/services/orders/as_schedule_link.py` | 값 비교 drift | 해당 없음(출고는 링크 개념이 없다) |

③을 택하는 이유: 사용자 결정(개인별 ack)과 구조가 일치하고, ack 클라이언트
(`static/js/foms/tablet-domain-sheets.js:211-235` `changeAck()`)가 **이미 출고 페이지에
로드돼 있다**(`templates/shipment/partials/dashboard_scripts.html:3`).

## 3. 감지 — 이벤트 SSOT 정리가 선행이다

③은 `OrderEvent(CONSTRUCTION_DATE_CHANGED)`를 읽는데, 그 이벤트를 **남기는 곳이 3곳뿐**이다.

| emit 하는 곳 | |
|---|---|
| `foms/api/erp_orders_structured.py:427-432` (PUT 전체 저장 / PATCH 필드) | O |
| `foms/api/orders/field_update.py:459-464` (`scheduled_date` 빠른 수정) | O |

**빠져 있는 경로(그대로 두면 알림이 안 뜨는 구멍):**

| # | 경로 | 왜 중요한가 |
|---|---|---|
| 1 | `foms/api/construction/orders.py:535` 시공불가 재예약 | 시스템에서 **가장 무거운 시공일 이동**인데 `CONSTRUCTION_REWORKED`만 남는다 |
| 2 | `foms/services/erp_inline_patch.py:66-75` `items.<n>.construction_date` | 출고 대시보드가 **실제로 날짜 필터에 쓰는 값**(`shipment_dashboard_helpers.py:94`) |
| 3 | PUT 전체 저장이 품목별 시공일만 바꾼 경우 | 위와 동일한 사각 |
| 4 | `foms/web/orders/edit.py:225,253` 레거시 주문수정 폼 | AS 링크 스펙에서도 동일하게 지적된 구멍 |
| 5 | 엑셀 임포트 `order_import.py:197` broadcast | 대량 이동이 통째로 무음 |
| 6 | `sync_erp_flat_columns` 간접 호출 32곳 | sd 시공일이 비면 레거시 값을 blank 로 덮는데 무음 |

**모든 쓰기가 예외 없이 통과하는 유일 지점**은
`foms/services/order_date_sync.py:282-315`의 전역 `before_flush` 다 — 4개 표현형
(`schedule.construction.date` · `items[].construction_date` · `erp_construction_date` ·
`scheduled_date`)을 전부 수집해 `OrderScheduleDate` 를 재빌드하고 이미 같은 훅에서
row 를 add/delete 한다(선례 존재).

### 채택안 A (권장) — 이벤트를 그 지점 하나로 모은다
`before_flush` 에서 재빌드 전/후 construction 날짜 집합을 diff 해
`CONSTRUCTION_DATE_CHANGED` 를 **여기서만** emit 하고, 기존 2곳의 emit 은 제거한다.

- 장점: 구멍 6종이 **구조적으로** 닫힌다. 이벤트 중복도 없다.
- 부작용: 같은 이벤트를 읽는 **생산 칸반의 알림도 함께 늘어난다** — 지금까지 놓치던
  재예약·품목별 이동이 생산 화면에도 뜬다. 이는 결함 해소이지 회귀가 아니라고 본다.
- 부수 정정: 현재 `field_update.py:459` payload 는 **정규화 안 된 raw** 라
  `2026-07-20` vs `2026/07/20` 가 허위 이벤트를 만든다. 통합하며 정규화한다.

### 대안 B — 새 타입 `CONSTRUCTION_DATE_SYNCED` 를 추가하고 출고만 소비
생산 쪽 노출을 그대로 두려면 이쪽. 대신 같은 변경이 두 이벤트로 기록된다(중복).

> **본 스펙은 A 로 진행한다.** B 를 원하면 승인 시 지정하라.

payload: `{"from": "YYYY-MM-DD|,연결 다중값", "to": ..., "source": "<write path>"}`,
`created_by_user_id` 는 요청 컨텍스트가 있으면 세션 사용자, 배치/부팅 백필이면 `None`.

## 4. 화면 (PC · 태블릿)

### 4.1 수집
신규 `foms/services/shipment_change_alerts.py` — ③의 형태를 따른다.

- 진입점 `collect_shipment_change_alerts(db, orders, user_id) -> {order_id: {...}}`
- 쿼리 1회: `OrderEvent.order_id.in_(page_ids)` +
  `event_type.in_(("SHIPMENT_CHANGE_ACK", "CONSTRUCTION_DATE_CHANGED"))` — N+1 금지 규칙 준수
- 개인 윈도: 본인 최근 `SHIPMENT_CHANGE_ACK` 이후의 변경만 `alerts`,
  전체는 `history`(펼침용) — ③ `compute_window_start`(`production_change_alerts.py:97`)와 동형
- **대시보드 슬라이스 캐시 밖에서 계산**한다. 선례가 명시적으로 그렇게 정했다
  (`docs/plans/2026-07-22-production-kanban-change-visibility-plan.md` 경계 절, 구현
  `foms/web/production/dashboard.py:203`). 캐시에 넣으면 300초 동안 stale 경고가 뜬다.

### 4.2 표시
- **상단 배너**: `현재 목록에서 시공일이 변경된 건 N건` + 대상 칩(고객명 · #id · `8/5 → 8/12`),
  칩 클릭 시 해당 행으로 점프. 톤·마크업은 오늘 배포한 AS 배너와 동일 규약
  (파스텔 채움 + 좌측 진한 띠, `static/css/contexts/cs/as-dashboard-body.css` 참조).
  칩 상한 5 + `외 N건`.
- **행 배지**: PC 테이블 행(`dashboard_main.html:481` `tr.shipment-row`)과
  태블릿 그리드 행(`tablet_ship_grid.html:99`) 양쪽. 문구 `시공일 8/5 → 8/12` + `확인`.
- **태블릿 시트**(`shipment/partials/tablet_sheet.html`)에도 같은 스트립 — 생산 시트 선례
  (`production/partials/tablet_sheet.html:66-85`).
- 모바일 v2/v3 표면은 **이번 범위 밖**(사용자 요청이 PC·태블릿). 게이트로 렌더 제외.

### 4.3 ack
`POST /api/orders/<int:order_id>/shipment/change-ack` — 생산 선례
(`foms/api/production/orders.py:983`) 복제:
- Order 를 건드리지 않고 `OrderEvent(SHIPMENT_CHANGE_ACK)` 1건만 남긴다(개인별).
- 권한: ADMIN / MANAGER / STAFF 중 출고 편집 정책 통과자(`_shipment_edit_decision` 재사용,
  시공팀 차단 규칙 `foms/api/shipment/recommendations.py:224-230` 과 동일 기준).
- 성공 후 출고 family 캐시 무효화.
- 클라이언트는 이미 있는 `changeAck()` 위임 핸들러 형태를 따른다.

## 5. 벨 + 푸시

- Notification 신규 타입 `SHIPMENT_ORDER_CHANGED`, `target_type="TEAM"`,
  `target_team=` **출고/시공 담당 팀 코드**(T6 에서 실제 코드값 확정 — 현재 이 팀을
  대상으로 한 알림이 0건이라 값 검증이 필요하다).
- 제목 `[출고] 시공일 변경 — {고객명}`, 본문 `주문 #N — 시공일 8/5 → 8/12`.
- 60초 debounce + merge: ② `production_change.py:44-61` 형태. 단 ② 의 결함
  (merge 시 title/message 를 덮어써 이전 변경이 소실)은 답습하지 않고, 최초 `from` 을
  보존하고 최신 `to` 만 갱신한다(① `drawing_order_change.py:756` 방식).
- `fan_out_new_notification` → `ensure_user_states` (공유 row 직접 수정 금지 규약 준수).
- **푸시는 타입 등록이 필요하다**: `SHIPMENT_ORDER_CHANGED` 를
  `_DEFAULT_P1_TYPES`(`push_sender.py:47`)에 넣지 않으면 enqueue 해도 발송되지 않는다 —
  생산(`PRODUCTION_ORDER_CHANGED`)이 지금 그 상태다. 등록까지 포함해야 "푸시 포함"이 성립한다.
- 푸시는 `created_new` 일 때만(debounce merge 는 조용히).

## 6. 성능 제약 (설계 구속)

- `/erp/shipment?view=fragment` TTFB 예산 **291ms**(`tools/perf/perf_budgets.json:32-35`).
  이 값은 과거 642ms 로 올렸다가 "증상 덮기"로 판정돼 되돌린 이력이 있다 —
  **예산 상향은 금지**, 추가 비용은 쿼리 1회로 묶는다.
- 배지/배너 데이터는 **`in_(ids)` 배치 1쿼리**(`PERFORMANCE_GUARDRAILS.md:132`).
- `order_events` 는 `order_id`·`event_type`·`created_at` **각각 단독 인덱스만** 있다.
  `in_(ids) + event_type.in_(...)` 실행계획을 `EXPLAIN` 으로 확인하고 Seq Scan 이면
  복합 인덱스를 마이그레이션으로 추가한다(측정 후 판단, 선제 추가 금지).
- G1: 새 `<script>` 는 반드시 `defer`(allowlist 는 빈 집합이라 예외 없음).
- G4: fragment 재실행 대비 `window.__*_BOUND` 싱글톤 가드.
- 기존 JS/CSS 수정 시 `?v=` 핀 전 저장소 동시 범프(SW `staticCacheFirst`).
- 태블릿 번들(`foms-tablet-bundle.css`) 범프 시 계약 테스트 2곳 락스텝
  (`test_tablet_rail_contract.py:162`, `test_tablet_t2_contract.py:715`).

## 7. 범위

### v1 (본 스펙)
- 시공일 변경 이벤트 SSOT 통합(구멍 6종 차단)
- 출고 변경 수집 서비스(개인 윈도) + ack API
- PC 테이블 · 태블릿 그리드 · 태블릿 시트 표시(배너 + 행 배지 + 확인)
- 벨 알림 + 푸시 타입 등록

### 범위 밖
- 모바일 v2/v3 출고 표면
- 시공일 외 필드(주소·시공팀·품목) — 사용자 결정으로 제외
- 상차 체크리스트(`sd.shipment.packing`)·AS 추천 스냅샷의 자동 무효화
  (날짜 이동 시 stale 인 것은 사실이나 별건)

## 8. 검증 기준

- `python -c "import app; print('APP_OK')"`
- 신규 테스트: 이벤트 emit 이 **구멍 6종 전부**에서 발생하는지(경로별 케이스), 수집
  서비스 윈도 판정, ack 후 배너 소멸, PC·태블릿 렌더 계약
- `tests/postgres` 전수(이벤트 쓰기 포함)
- `pre_push_smoke.ps1` exit 0
- 스테이징 TTFB 실측: `/erp/shipment?view=fragment` 291ms 예산 내 + `EXPLAIN` Seq Scan 없음
- 스테이징 실브라우저: 시공일 변경 → 출고 대시보드 배너·행 배지 → 확인 → 소멸,
  벨 알림 1건, 푸시 수신
