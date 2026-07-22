# 태블릿 생산 칸반 — 변경 가시성·지방뱃지·시공일 강조·정렬 (2026-07-22)

## 요구사항 (사용자 확정)
1. 지방주문(`Order.is_regional`) 카드 뱃지 표기
2. 시공일 가시성 대폭 강화 (3m 거리 글랜스 가독)
3. 생산 일정에 영향 주는 변경(시공일 변경·주문 취소·도면 변경)을 칸반에 확실히 표기 + 모아보기 필터
4. 3열(제작대기/제작중/제작완료) 시공일 빠른 순 정렬

설계 확정(사용자 답변): **팀 확인(ack)으로 해제** / **취소=묘비 카드 잔류** / **생산 파이프라인 진입 후 변경만 감지**

## 현행 구조 (조사 완료 — 재탐색 금지)
- 라우트: `foms/web/production/dashboard.py:81` `erp_production_dashboard()` — 정렬 `dashboard.py:117` `order_by(Order.created_at.desc())`
- 쿼리: `foms/services/production_read_model.py:23` `build_production_orders_query` — `Order.active_filter()` + `is_erp_order` + `erp_stage_code IN ('고객컨펌','생산','시공','CONFIRM','PRODUCTION','CONSTRUCTION')`
- 행 DTO: `foms/services/production_dashboard_display.py` `build_production_enriched_rows` — `construction_dday`/`construction_md`는 `sd['schedule']['construction']['date']` 파생 (`:172,195-196`)
- 칸반 템플릿: `templates/production/partials/tablet_kanban_body.html` — Jinja `selectattr('stage', ...)` 3열 그룹, 카드 `.foms-kanban-card`, 시공일은 foot 칩(`.foms-kanban-chip`, is-overdue/is-imminent 상태 존재)
- 사이드 시트: `dashboard.py:337` `erp_production_tablet_sheet` → `templates/production/partials/tablet_sheet.html`; 액션 배선 `static/js/foms/tablet-domain-sheets.js`(필터바 배선도 여기), 열이동 `static/js/foms/tablet-production-kanban.js`
- CSS: `static/css/foundation/foms-tablet-production-kanban.css` (번들 `foms-tablet-bundle.css:11` `?v=20260722a`, outer `templates/partials/shared/layout_head.html`도 ?v 동반)
- 이벤트: `models.py:255` `OrderEvent(order_id, event_type, payload JSONB, created_by_user_id, created_at)` — `CONSTRUCTION_DATE_CHANGED`는 구조화 PUT 경로만 기록(`foms/api/erp_orders_structured.py:389-400`). **빠른수정 `foms/api/orders/field_update.py:339-343`(scheduled_date)은 이벤트 미기록 — 결함, 이번에 근본수정**
- 도면 이력: `structured_data['drawing_transfer_history']` — TRANSFER(`foms/api/drawing/erp_orders_drawing.py:186-213`)·REQUEST_REVISION(`erp_orders_revision.py:101-115`) append, 각 entry에 `at`(구현자가 포맷 검증)
- 취소: soft delete only — `foms/web/orders/trash.py:141-169` `status='DELETED'`+`deleted_at` (하드삭제 없음). `active_filter()`가 제외하므로 묘비는 별도 조회 필요. `erp_stage_code`는 삭제 후에도 보존 → 버킷 판정 가능
- 지방뱃지 참고 구현: `templates/orders/partials/dashboard_grid.html:342-343` (`bg-success` "지방주문"), 모델 `models.py:41 is_regional`
- 생산 이동 API: `/api/orders/<id>/production/start|complete` (tablet-production-kanban.js가 호출 — ack API는 같은 blueprint·권한 패턴에 추가)

## 변경 감지 모델 (SSOT)
신규 서비스 `foms/services/production_change_alerts.py`:

- `PROD_STAGES = {'고객컨펌','CONFIRM','생산','PRODUCTION','시공','CONSTRUCTION'}`
- **window_start(주문별)** = 최근 `PRODUCTION_CHANGE_ACK` 이벤트 created_at; 없으면 **생산 진입 시점** = 최근 `STAGE_CHANGED` 이벤트 중 `payload.to ∈ PROD_STAGES and payload.from ∉ PROD_STAGES`의 created_at; 그것도 없으면 `order.erp_stage_updated_at`; 최후 `order.created_at`
- **감지 대상 (window_start 이후만)**:
  - `CONSTRUCTION_DATE_CHANGED` OrderEvent → `{'kind':'construction_date','label':'시공일 변경','detail':'7/20 → 7/28'}` (payload from/to를 M/D 포맷, 없으면 '미정')
  - `drawing_transfer_history` entry: action `TRANSFER` → `{'kind':'drawing','label':'도면 재전달',...}`, `REQUEST_REVISION` → `'도면 수정요청'` (entry `at` > window_start)
- **배치 API**: `collect_production_change_alerts(db, orders) -> dict[order_id, list[alert]]` — OrderEvent는 `order_id.in_(ids)` 단일 쿼리(N+1 금지), drawing 이력은 이미 로드된 structured_data에서 파생
- **묘비**: `collect_production_tombstones(db, user, erp_mine_only) -> list[dict]` — `status=='DELETED' and deleted_at is not null and is_erp_order and erp_stage_code ∈ PROD_STAGES and deleted_at ≥ 최근 14일`, 그리고 삭제 후 `PRODUCTION_CHANGE_ACK` 없음. dict: `{id, customer_name, bucket(제작대기/제작중/제작완료 ← erp_stage_code), deleted_md('M/D'), product_label}`
- **ack API**: `POST /api/orders/<id>/production/change-ack` — `OrderEvent(event_type='PRODUCTION_CHANGE_ACK', payload={'source': 'tablet_kanban'})` 추가만. 삭제 주문에도 허용(묘비 확인용 — active_filter 대신 존재만 확인). 권한·응답형식은 production start/complete API와 동일 패턴. 응답 `{'success': True, 'data': {'order_id': id}}`
- **근본수정**: `field_update.py` scheduled_date 분기에서 값 변경 시(old != new) `CONSTRUCTION_DATE_CHANGED` OrderEvent 기록 (구조화 PUT과 동일 payload 형태)

## 데이터 계약 (T1 산출 → T2 소비, 고정)
`enriched` 행 dict에 추가:
- `is_regional: bool`
- `change_alerts: list[{'kind','label','detail'}]` (빈 리스트 = 변경 없음)
- `has_changes: bool`

render_template 컨텍스트 추가:
- `tombstones: list[{'id','customer_name','bucket','deleted_md','product_label'}]`
- `changed_count: int` (has_changes 행 수 + 묘비 수)

사이드 시트 라우트 `sheet` dict에 추가: `change_alerts`(동일 구조), `has_changes: bool`

정렬: `dashboard.py:117` → `_q.order_by(Order.erp_construction_date.asc().nulls_last(), Order.created_at.desc())` (String(10) YYYY-MM-DD 사전순=시간순, ix 있음. PC 리스트도 동일 적용 — 의도됨)

## UI 스펙 (T2)
- **카드 변경 스트립**: 카드 최상단 full-width `.foms-kanban-card__alert` — kind별 아이콘+라벨+detail 1줄씩 (시공일=파랑 계열, 도면=주황 계열), 카드 자체 `is-changed` 상태(엠버 outline). HMI 색 규율 예외 승인됨(변경=주의 상태).
- **묘비 카드**: 해당 버킷 열 최상단 `.foms-kanban-card--tomb` — 빨강 톤, "취소됨 · {deleted_md}", 고객명+품목, `[확인]` 버튼(ack API 호출 후 reload). 카드 탭=시트 열기 금지(삭제 주문이라 시트 404 — data-foms-sheet-url 미부여).
- **지방 뱃지**: `.foms-kanban-card__regional` — top-right 뱃지열(보류·2공장 옆), 그린 톤 "지방". 
- **시공일 강조**: foot 칩 → 카드 내 제2 시각 앵커로 격상. 날짜+D-day 타이포 확대(≥1.25×, 날짜 weight 700), 무일정 카드는 "시공일 미정" 무채 칩 명시(현재는 아예 미표시 — 미정 구분 안 됨). is-overdue/is-imminent 유채 규율 유지.
- **모아보기 필터 칩**: `.tablet-prod-filter`에 토글 버튼 `data-tablet-prod-changed` "변경 {changed_count}" — changed_count>0이면 강조 상태. 클라 필터(카드 `data-changed="1"` 기준, 묘비는 항상 표시). 배선은 tablet-domain-sheets.js 기존 필터 로직에 추가(싱글톤 가드 준수).
- **시트 확인 버튼**: tablet_sheet.html — has_changes면 변경 목록 + `[변경 확인]` 버튼(ack API→성공 시 reload). tablet-domain-sheets.js 위임 배선.
- **CSS ?v 범프**: kanban css `20260722a`→`20260722b` — `foms-tablet-bundle.css` import + `layout_head.html` outer 번들 + **테스트 리터럴 핀 grep 전수 치환**(`test_p1_mockup_*`, `spec_calc_followup`, `tablet_t2`, 747eadc6 신설 테스트 등 — grep '20260722a' 전체) 후 전부 커밋.

## 검증
- `python -c "import app; print('APP_OK')"`
- 신규 pytest: 변경감지 서비스(윈도·ack·묘비)·ack API·field_update 이벤트 기록·정렬
- 기존: `pytest tests -k "production or tablet or kanban" -q` + 계약 테스트(?v 핀)
- 오케스트레이터 diff 직접 확인

## 경계 (손대지 말 것)
- `production_read_model.py`의 KPI/카운트 로직, 캐시 키 구조 (summary 캐시에 변경감지 넣지 말 것 — 페이지 행 기반 비캐시 계산)
- sw.js, erp-shell.js, 알림(fan_out) 시스템 — 이번 범위 아님 (벨 알림은 후속)
- PC `dashboard_body.html` 테이블 마크업 (정렬 변화만 자연 반영)
