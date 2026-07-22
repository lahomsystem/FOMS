# 생산 칸반 라운드2 — 벨 알림·빨간 일자·SW 스테일 JS·KPI 탭 필터 (2026-07-22)

라운드1: `2026-07-22-production-kanban-change-visibility-plan.md` (f2836ae3, CI green). 본 문서는 사용자 피드백 4건 후속.

## 확정 사실 (조사 완료 — 재탐색 금지)

### 벨 알림 인프라 (inv-bell 조사)
- 정본 패턴: `foms/services/notifications/drawing_order_change.py:807` `apply_drawing_order_change_alert` — 60초 debounce(같은 actor+order면 기존 알림 title/message 갱신, 신규 row 없음), 신규면 `Notification(...)` 생성 → `db.flush()` → `fan_out_new_notification(db, notif, actor_user_id)` (recipients.py:126, 같은 트랜잭션). `(notif, created_new)` 반환.
- `finalize_drawing_order_change_alert`(:911) — **commit 후** 호출 계약: created_new면 `enqueue_push_for_notification`, 항상 배지 무효화+realtime emit.
- 벨 목록 API(`foms/api/notifications/__init__.py:260`)는 user_id 기준 state JOIN — **target_team은 fan-out 시점에만 사용** → `target_team='PRODUCTION'` 알림 만들면 생산팀(User.team='PRODUCTION' 대문자 일치)+ADMIN 벨에 그대로 뜸. 소비측 코드 변경 불필요.
- notification_type 기존값: ERP_ORDER_CHANGED, DRAWING_REVISION, DRAWING_TRANSFERRED, URGENT_MENTION, URGENT_ESCALATION, ANNOUNCEMENT.
- `foms/web/orders/trash.py:141 delete_order` — 알림 훅 전무.

### 도면 워크벤치 — **이미 변경 알림 있음, 이번 라운드 작업 없음**
- 리스트 뱃지 `dw-order-change-badge`(workbench_dashboard_body.html:212-218), 모바일 카드 `is-order-change` 칩, 상세 배너 `dw-order-change-banner`+피드 `dw-order-change-feed`(workbench_detail_body.html:961-990). drawing_order_change 서비스가 데이터원. 사용자 보고만.

### SW 스테일 JS (변경버튼 불능 근본원인 — 규명 완료)
- `static/sw.js` `staticCacheFirst`: JS/CSS 동일 URL이면 캐시본 즉시 응답(5분 TTL 내 재검증도 생략) → `tablet-domain-sheets.js?v=20260713b` URL 불변이라 실기기(SW 등록)가 구버전 실행 → 신규 분기(변경 토글·change-ack)만 사망. sw.js v9 주석에 동일 사고 전례(tablet-measurement.js). **수정 = ?v 범프**(URL 변경=캐시 키 미스).
- 로드 지점 2곳: `templates/production/partials/tablet_kanban_body.html:257`, `templates/shipment/partials/dashboard_scripts.html:3` (둘 다 `?v=20260713b`). 계약 핀: `tests/domains/test_tablet_domain_sheets_contract.py`(:89,:117 부근 cachebuster 검증).

### KPI 타일 (질문 3 답)
- 현재 의도된 정적 표시(탭 배선 없음). 이번에 탭→필터 배선.

## 구현 스펙

### B1. 생산팀 벨 알림 (백엔드)
신규 `foms/services/notifications/production_change.py` — drawing_order_change 패턴 미러(단순화판):
- `apply_production_change_alert(db, order, kind, message_detail, actor_user_id, actor_name) -> tuple[Notification|None, bool]`
  - 게이트: `order.is_erp_order` and `order.erp_stage_code in PROD_STAGES`(production_change_alerts에서 import) 아니면 `(None, False)`.
  - kind: `'construction_date'`(시공일 변경) / `'drawing'`(도면 재전달·수정요청) / `'cancelled'`(주문 취소).
  - notification_type=`'PRODUCTION_ORDER_CHANGED'`, target_type/target_team='TEAM'/'PRODUCTION', order_id 연결. title 예: `[생산] 시공일 변경 — {고객명}`, message에 detail(예: `7/6 → 7/4`).
  - 60초 debounce: 같은 order+type 최근 알림이면 message 갱신만(actor 무관 — 생산 알림은 팀 공지 성격, drawing보다 단순하게) → `(prev, False)`.
  - 신규면 flush → `fan_out_new_notification`.
- `finalize_production_change_alert(notif, created_new)` — drawing과 동일 순서(commit 후: created_new면 push enqueue, 항상 배지 무효화+realtime). 헬퍼는 drawing_order_change가 쓰는 동일 함수 import 재사용(경로는 해당 파일 상단 import 참조).
- **훅 4곳** (각각 기존 commit 흐름 존중 — commit 전 apply, commit 후 finalize):
  1. `foms/api/erp_orders_structured.py` — CONSTRUCTION_DATE_CHANGED 기록 지점(:389-400 부근)과 같은 diff 조건에서 apply, 라우트의 기존 commit 후 finalize (기존 drawing finalize 호출부와 같은 위치에 병렬 추가).
  2. `foms/api/orders/field_update.py` — scheduled_date 분기(라운드1에서 이벤트 기록 추가한 곳)와 동일 조건. 이 파일의 기존 drawing_notif finalize 흐름(:363-389 부근) 미러.
  3. 도면 전달/수정요청: `foms/api/drawing/erp_orders_drawing.py`(TRANSFER 기록 지점 뒤)·`foms/api/drawing/erp_orders_revision.py`(REQUEST_REVISION 지점 뒤) — kind='drawing', detail='도면 재전달'/'도면 수정요청'.
  4. `foms/web/orders/trash.py delete_order` — kind='cancelled', detail 없음. 단 생산 파이프라인 게이트는 서비스가 판정.
- **소음 통제**: 파이프라인 게이트 + 60s debounce로 충분(1차). 그 이상 묶음은 비범위.
- pytest: 게이트(비생산 단계 무알림)·생성+fan_out(PRODUCTION 팀 유저 state 생성)·debounce 갱신·취소 알림·훅 4곳 각 1건.

### B2. alert 구조화 (빨간 일자용 백엔드)
`foms/services/production_change_alerts.py` `_build_alerts_for_order` — construction_date alert에 `'from_md'`/`'to_md'` 키 추가(기존 `detail` 유지 — 하위호환). 테스트 1건 보강.

### F1. 변경 일자 빨강 (프론트)
- `tablet_kanban_body.html` 스트립 + `tablet_sheet.html` 변경 목록: construction_date kind이고 `a.to_md` 있으면 `{{ a.from_md }} → <span class="foms-kanban-card__alert-to">{{ a.to_md }}</span>` 렌더(없으면 기존 detail 폴백 — `|default` 안전).
- CSS: `.foms-kanban-card__alert-to` = danger 토큰 빨강 + weight 800. 시트 동형 클래스.

### F2. JS ?v 범프 (SW 스테일 봉합)
- `tablet-domain-sheets.js?v=20260713b` → `?v=20260722a` — kanban body:257 + shipment dashboard_scripts.html:3 **둘 다**.
- `tests/domains/test_tablet_domain_sheets_contract.py` cachebuster 핀 갱신(파일 내 20260713b grep 전수).

### F3. KPI 타일 탭 필터 (프론트)
- `tablet_kanban_body.html` KPI 타일 3종에 `data-tablet-prod-kpi="line|load|delayed"` + `role="button"`/`tabindex`/`aria-pressed` (이번주 자수는 비인터랙티브 유지).
- 카드에 `data-dday="{{ o.construction_dday if o.construction_dday is not none else '' }}"` 속성 추가.
- `tablet-domain-sheets.js`: KPI 탭 토글(하나만 활성 — 상호 배타, 재탭=해제) → 필터 로직에 kpi 조건 추가: line=stage 제작중(status select와 동일 predicate 재사용), load=data-dday==0, delayed=data-dday<0. 리셋 버튼이 kpi 상태도 해제. 묘비 카드는 항상 표시 유지.
- CSS: 타일 탭 어포던스(cursor·active 상태 `is-on` 아웃라인). erp-pro-alert 공용 문법 무터치 — `.tablet-prod-board` 스코프 내 추가 클래스만.
- kanban css `?v=20260722b`→`20260722c` — bundle+layout_head+계약 핀 grep('20260722b') 전수 치환.

## 검증
- APP_OK + 신규/갱신 pytest + `pytest tests -k "production or tablet or kanban or notification" -q`
- 오케스트레이터 diff 검수 → pre_push_smoke → push → CI 3종(코드2+perf-gate).

## 경계
- 벨 소비측(API/UI)·sw.js·워크벤치 파일 무터치. NotificationUserState 스키마 무변경.
- escalation(P0 5/10분)은 긴급 전용 — 생산 알림에 연결하지 않음.
