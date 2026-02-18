# app.py 슬림다운 단계별 계획

> **목표**: app.py 300줄 이하, 규칙(02-architecture) 구조에 맞추기  
> **원칙**: 한 번에 하나씩, 단계마다 서버 기동 검증

---

## Phase 1: services/ 폴더 도입 (비즈니스 로직 이전)

규칙에 있는 `services/` 구조를 만들고, 루트에 흩어진 서비스 모듈을 옮깁니다.

| 순서 | 작업 | 영향 파일 | 검증 |
|------|------|-----------|------|
| 1-1 | `services/` 폴더 + `__init__.py` 생성 | 신규 | - |
| 1-2 | `business_calendar.py` → `services/business_calendar.py` | app, erp, erp_policy, erp_build_step_runner | `python app.py` |
| 1-3 | `erp_policy.py` → `services/erp_policy.py` | app, erp, erp_automation | `python app.py` |
| 1-4 | `storage.py` → `services/storage.py` | app, erp, apps/api/files | `python app.py` |

**의존성 순서**: business_calendar → erp_policy (erp_policy가 business_calendar 사용) → storage (독립)

---

## Phase 2: app.py에서 Blueprint 분리 (한 덩어리씩)

| 순서 | 작업 | 예상 감소 줄 수 | 검증 |
|------|------|-----------------|------|
| 2-1 | 채팅 API + SocketIO → `apps/api/chat/` 패키지 (routes + socketio_handlers) | ~1,220줄 | 채팅 페이지·API·실시간 동작 |
| 2-2 | 수납장 대시보드 → `apps/storage_dashboard.py` | ~175줄 | 수납장 페이지·엑셀 내보내기 |
| 2-3 | 파일 URL 헬퍼 이전 (뷰/다운로드 라우트는 이미 files_bp에 있음) | ~6줄 | build_file_view_url, build_file_download_url → apps/api/files |

---

## Phase 3: 템플릿 분리 (800줄 이하)

| 순서 | 작업 | 검증 |
|------|------|------|
| 3-1 | `erp_dashboard.html` → partials 분리 | ERP 대시보드 표시 |
| 3-1 완료 | 메인 4,309줄 → 594줄. partials: styles, filters, grid, modals, scripts (scripts는 2,112줄, 추후 800줄 이하 재분할 권장) | 서버 기동·대시보드 표시 |
| 3-2 | `chat.html` → partials 분리 | 채팅 페이지 표시 |
| 3-2 완료 | 메인 3,244줄 → 229줄. partials: chat_styles.html (935줄), chat_scripts.html (2,172줄) | 서버 기동·채팅 페이지 |

---

## Phase 4: erp.py 세분화 (장기)

- 대시보드별 또는 기능별로 Blueprint/모듈 분리 (apps/erp.py ~5,476줄 → 여러 파일)

### Phase 4 구조 분석 (2026-02-16, GDM)

| 블록 | 라우트 수 | 대략 줄 범위 | 비고 |
|------|-----------|--------------|------|
| 헬퍼/필터/권한 | - | 1~495 | can_edit_erp, apply_erp_display_fields*, 템플릿 필터, shipment 설정 load/save |
| 대시보드(페이지) | 9 | 496~4420 | erp_dashboard, drawing_workbench, measurement, shipment, as, production, construction 등 |
| 출고 설정 API | 4 | 1820~1936 | 페이지 + GET/POST settings + shipment/update |
| 실측 API | 2 | 1937~2145 | measurement/update, measurement/route |
| 지도/주소/유저 | 5 | 2146~2344 | api_map_data, api_generate_map, api_update_order_address, api_erp_users_list |
| 주문 API (다수) | 20+ | 2588~5180 | quick-search, quick-info, transfer-drawing, production/construction/as, 도면/수정 요청 등 |
| **알림 API** | **4** | **5180~5476** | **list, badge, mark read, read-all + 헬퍼 3개** ← **1차 분리 후보** |

**1차 분리 후보: 알림 API** (~297줄, 의존성: Notification/User/Order, get_db, session, _ensure_dict 인라인 가능)

| 4-1 | 완료 | 알림 API → apps/api/notifications.py (notifications_bp, url_prefix=/erp/api). erp.py ~297줄 감소 |
| 4-2 | 완료 | 출고 설정: services/erp_shipment_settings.py + apps/api/erp_shipment_settings.py (erp_shipment_bp). erp.py ~190줄 감소 |

**2차 분리 후보: 출고 설정** — 헬퍼 3개(load/save/normalize)는 shipment 대시보드에서도 사용 → services로 이전 후, API 4 routes만 새 Blueprint로 분리.

---

## 진행 상태

> **2026-02-17 코드 검증**: Phase 2-1·2-2·2-3은 복원으로 미적용된 것으로 확인. 실제 상태는 `docs/plans/SLIM_DOWN_PROGRESS_2026-02-17.md` 참조.

| Phase | 상태 | 비고 |
|-------|------|------|
| 1-1 | 완료 | services/ + __init__.py 생성 |
| 1-2 | 완료 | business_calendar → services/business_calendar.py, import 경로 수정, 서버 기동 검증 |
| 1-3 | 완료 | erp_policy → services/erp_policy.py, import 경로 수정, 서버 기동 검증 |
| 1-4 | 완료 | storage → services/storage.py, import 경로 수정, 서버 기동 검증 |
| 2-1 | **미완료** | 채팅 → apps/api/chat/ (chat_bp, socketio). 현재 app.py에 라우트·SocketIO 존재 (복원됨) |
| 2-2 | 완료 | 수납장 → apps/storage_dashboard.py (2026-02-17 진행) |
| 2-3 | 완료 | build_file_view_url, build_file_download_url → apps/api/files.py (2026-02-17 진행) |
| 2-4 | - | (대규모 파일 라우트는 이미 files_bp에 있어 추가 이전 없음) |
| 3-1 | 완료 | erp_dashboard.html → partials (styles, filters, grid, modals, scripts). 메인 594줄 |
| 3-2 | 완료 | chat.html → partials (chat_styles, chat_scripts). 메인 229줄 |
| - | 완료 | erp_beta → ERP 이름 변경 (apps/erp.py, Blueprint erp). feature/erp-beta-rename-to-erp |

---

## 다음 계획 (GDM 더블체크 후, 2026-02-16)

### 더블체크 결과 (최신)
- **앱 기동**: `from app import app` OK
- **apps/erp.py**: ~4,993줄, **37개 라우트** (4-1·4-2 분리 반영)
- **분리 완료**: notifications_bp, erp_shipment_bp 등록됨
- **deploy**: Phase 4-1까지 반영. Phase 4-2는 feature/erp-split-shipment-settings에 있음

### 다음 단계 계획서
**상세 문서**: `docs/plans/2026-02-16-phase4-next-steps.md`

| 순서 | 단계 | 작업 | 비고 |
|------|------|------|------|
| 0 | 배포 정리 | feature/erp-split-shipment-settings → deploy 머지·푸시, DEPLOY_NOTES 갱신 | Phase 4-2 반영 |
| 1 | Phase 4-3 | 실측 API 분리 (measurement/update, measurement/route) | ~200줄, 1개 Blueprint |
| 2 | Phase 4-4 | 지도/주소/유저 API 분리 후보 검토 | 500줄 이하 블록 여부 결정 |
| 3 | Phase 4-5~ | 주문 API 기능별 그룹 분할 | erp.py 500줄 이하 목표 |
| 4 | 선택 | app.py 300줄, AI/카카오/불필요 파일 | 슬림다운 최종 |
