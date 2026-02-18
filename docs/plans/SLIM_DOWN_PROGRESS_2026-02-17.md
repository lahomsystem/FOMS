# app.py / erp.py 슬림다운 진행 계획서

> **작성일**: 2026-02-17  
> **기준**: 코드베이스 실제 상태 (복원 이후)  
> **목표**: app.py 300줄 이하, erp.py 500줄 이하

---

## 1. 현재 상태 요약 (코드 기준)

| 파일 | 현재 줄 수 | 목표 | 비고 |
|------|-----------|------|------|
| **app.py** | **~1,568줄** | 300줄 이하 | SLIM-025 완료: bulk_action → order_pages_bp (2026-02-17) |
| **apps/erp.py** | **2,078줄** | 500줄 이하 | Phase 4 주문 API 분리 완료, 페이지·헬퍼 잔존 |
| templates/erp_dashboard.html | 594줄 | 800줄 이하 | Phase 3-1 완료 (partials) |
| templates/chat.html | 229줄 | 800줄 이하 | Phase 3-2 완료 (partials) |

---

## 2. Phase별 실제 진행 상태 (코드 검증)

### Phase 1: services/ 폴더 도입 — ✅ 완료

| 작업 | 상태 | 검증 |
|------|------|------|
| 1-1 services/ + __init__.py | ✅ | `services/__init__.py` 존재 |
| 1-2 business_calendar → services/ | ✅ | `services/business_calendar.py` 존재 |
| 1-3 erp_policy → services/ | ✅ | `services/erp_policy.py` 존재 |
| 1-4 storage → services/ | ✅ | `services/storage.py` 존재 |

---

### Phase 2: app.py Blueprint 분리 — ⚠️ 진행 중 (2-2·2-3 완료)

| 작업 | 문서 | 코드 실제 | 비고 |
|------|------|-----------|------|
| **2-1** 채팅 API + SocketIO | ✅ 완료 | ✅ 완료 | `apps/api/chat/` (routes, socketio_handlers, utils, __init__) - 2026-02-17 |
| **2-2** 수납장 대시보드 | ✅ 완료 | ✅ 완료 | `apps/storage_dashboard.py` 존재, app.py 등록됨 (2026-02-17) |
| **2-3** 파일 URL 헬퍼 | ✅ 완료 | ✅ 완료 | `build_file_view_url`, `build_file_download_url` → apps/api/files.py (2026-02-17) |

---

### Phase 3: 템플릿 분리 — ✅ 완료

| 작업 | 상태 | 검증 |
|------|------|------|
| 3-1 erp_dashboard.html → partials | ✅ | partials/erp_dashboard_*.html 존재 |
| 3-2 chat.html → partials | ✅ | partials/chat_styles.html, chat_scripts.html 존재 |

---

### Phase 4: erp.py 세분화 — ✅ 완료 (주문 API 전부 분리)

| 작업 | 상태 | 산출물 |
|------|------|--------|
| 4-1 알림 API | ✅ | apps/api/notifications.py |
| 4-2 출고 설정 | ✅ | apps/api/erp_shipment_settings.py |
| 4-3 실측 API | ✅ | apps/api/erp_measurement.py |
| 4-4 지도/주소/유저 | ✅ | apps/api/erp_map.py |
| 4-5a 주문 Quick API | ✅ | apps/api/erp_orders_quick.py |
| 4-5b 도면 전달/취소 | ✅ | apps/api/erp_orders_drawing.py |
| 4-5c 도면 창구 업로드 | ✅ | erp_orders_drawing_bp |
| 4-5d 수정 요청 | ✅ | apps/api/erp_orders_revision.py |
| 4-5e 도면 담당자 | ✅ | apps/api/erp_orders_draftsman.py |
| 4-5f 생산 API | ✅ | apps/api/erp_orders_production.py |
| 4-5g 시공 API | ✅ | apps/api/erp_orders_construction.py |
| 4-5h CS/AS/confirm | ✅ | apps/api/erp_orders_cs.py, erp_orders_as.py, erp_orders_confirm.py |

**app.py Blueprint 등록**: auth, erp, files, address, orders, notifications, erp_shipment, erp_measurement, erp_map, erp_orders_quick/drawing/revision/draftsman/production/construction/cs/as/confirm, storage_dashboard, chat, wdcalculator, backup, admin, **user_pages** (23개)

**erp.py 잔존**: 대시보드 페이지 8개 라우트 + 헬퍼·필터·권한 (약 2,078줄)

---

## 3. 이후 진행 계획

### 우선순위 1: Phase 2 재수행 (app.py 슬림다운)

app.py 8,263줄 → 예상 ~6,800줄 (약 1,460줄 감소)

| 순서 | 단계 | 작업 | 예상 감소 | 검증 |
|------|------|------|-----------|------|
| **2-3** | 파일 URL 헬퍼 | `build_file_view_url`, `build_file_download_url` → apps/api/files.py | ~6줄 | app.py import로 사용 |
| **2-2** | 수납장 대시보드 | `apps/storage_dashboard.py` (storage_dashboard_bp) 생성 | ~175줄 | 페이지·엑셀 내보내기 |
| **2-1** | 채팅 API + SocketIO | `apps/api/chat/` 패키지 (routes + socketio_handlers) | ~1,220줄 | 채팅·실시간 동작 |

**권장 순서**: 2-3 → 2-2 → 2-1 (의존성·리스크 낮은 것부터)

---

### 우선순위 2: erp.py 추가 슬림다운 (2,078줄 → 500줄 이하)

| 블록 | 예상 규모 | 분리 후보 | 비고 |
|------|-----------|-----------|------|
| 대시보드 페이지 8개 | ~1,500줄 | erp_dashboard_bp 등 별도 Blueprint | 단계적 분리 |
| 헬퍼/필터/권한 | ~500줄 | services/ 또는 유틸 모듈 | 재사용성 검토 |

---

### 우선순위 3: app.py 추가 분리 — 진행 중

| 단계 | 상태 | 산출물 |
|------|------|--------|
| **wdcalculator** | ✅ 완료 (2026-02-17) | apps/api/wdcalculator.py (~530줄, app.py ~992줄 감소) |
| **backup** | ✅ 완료 (2026-02-17) | apps/api/backup.py (~120줄, app.py ~110줄 감소) |
| **admin** | ✅ 완료 (2026-02-17) | apps/admin.py (~145줄, app.py ~126줄 감소) |
| **user_pages** | ✅ 완료 (2026-02-17) | apps/user_pages.py (~115줄, app.py ~110줄 감소) |
| **dashboards** | ✅ 완료 (2026-02-17) | apps/dashboards.py (regional/metropolitan/self_measurement 대시보드) |
| **attachments** | ✅ 완료 (2026-02-17) | apps/api/attachments.py (주문 첨부 CRUD) |
| **tasks** | ✅ 완료 (2026-02-17) | apps/api/tasks.py (주문 팔로업 Task CRUD) |
| **events** | ✅ 완료 (2026-02-17) | apps/api/events.py (이벤트·변경 로그·되돌리기) |
| **quest** | ✅ 완료 (2026-02-17) | apps/api/quest.py (Quest GET/POST/approve/status) |
| **blueprint** | ✅ 완료 (2026-02-17) | apps/api/erp_orders_blueprint.py (upload/get/delete) |
| **structured** | ✅ 완료 (2026-02-17) | apps/api/erp_orders_structured.py (structured GET/PUT, parse-text, erp/draft) |
| **주소/경로 API** | ✅ 완료 (2026-02-17) | erp_map_bp에 4개 통합 (calculate_route, address_suggestions, add_address_learning, validate_address) |
| **/api/orders 캘린더** | ✅ 완료 (2026-02-17) | orders_bp에 api_orders 라우트 추가 (FullCalendar 이벤트, ~200줄 감소) |
| **order_pages (index+add)** | ✅ 완료 (2026-02-17) | apps/order_pages.py 신규, services/order_display_utils.py (~576줄 감소) |
| **order_trash (delete/trash/restore)** | ✅ 완료 (2026-02-17) | apps/order_trash.py 신규, services/request_utils.py (~254줄 감소) |
| **bulk_action → order_pages** | ✅ 완료 (2026-02-17) | order_pages_bp에 bulk_action 추가 (~146줄 감소) |
| **목표** | - | app.py 300줄 이하 |

---

## 4. 실행 절차 (Phase 2 재수행 시)

1. **한 번에 1개 단계만** (06-safe-changes 준수)
2. **단계별 검증**: `python app.py` 기동, 해당 기능 수동 확인
3. **단위 커밋**: 각 단계 완료 시 별도 커밋
4. **문서 갱신**: 완료 시 docs/plans/2026-02-16-app-slim-down.md 진행 상태 수정

---

## 5. 관련 문서

| 문서 | 용도 |
|------|------|
| docs/plans/2026-02-16-app-slim-down.md | 전체 슬림다운 계획 (Phase 1~4) |
| docs/plans/2026-02-16-phase4-next-steps.md | Phase 4 erp.py 다음 단계 |
| docs/CURRENT_STATUS.md | 프로젝트 현재 상태 |
| .cursor/rules/02-architecture.mdc | Blueprint·services 구조 규칙 |
