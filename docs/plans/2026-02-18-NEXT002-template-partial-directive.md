# NEXT-002 대형 템플릿 Partial 분리 실행 지시서

> **지휘**: Grand Develop Master (GDM)  
> **착수일**: 2026-02-18  
> **목표**: 800줄 초과 HTML 템플릿을 Jinja2 partial로 분리 (목표: 템플릿당 800줄 이하)

---

## 1. 배경

- GDM 감사 2026-02-18, 파일 정리 계획표(`2026-02-18-file-cleanup-and-next-plan.md`) §3 기준.
- NEXT-001 (order_pages.py edit_order 분리) 완료 후 **다음 착수** 항목.
- 규칙(01-clean-code): HTML 템플릿 **800줄 이하** 권장.

---

## 2. 대상 현황 (2026-02-18 기준)

| 순위 | 파일 | 줄 수 | 비고 |
|------|------|-------|------|
| 1 | `templates/wdcalculator/calculator.html` | 3,925 | 가장 큼, WD 계산기 |
| 2 | `templates/erp_construction_dashboard.html` | 2,702 | 시공 대시보드 |
| 3 | `templates/erp_production_dashboard.html` | 2,653 | 생산 대시보드 |
| 4 | `templates/regional_dashboard.html` | 2,126 | 지역 대시보드 |
| 5 | `templates/partials/chat_scripts.html` | 2,105 | 채팅 스크립트 (이미 partial) |
| 6 | `templates/partials/erp_dashboard_scripts.html` | 1,928 | ERP 대시보드 스크립트 |
| 7 | `templates/wdcalculator/product_settings.html` | 1,837 | WD 상품 설정 |
| 8 | `templates/erp_drawing_workbench_detail.html` | 1,558 | 도면 작업 상세 |
| 9 | `templates/erp_shipment_dashboard.html` | 1,539 | 출고 대시보드 |
| 10 | `templates/layout.html` | 1,490 | 공통 레이아웃 |
| 11 | `templates/map_view.html` | 1,435 | 지도 뷰 |
| 12 | `templates/edit_order.html` | 1,421 | 주문 수정 |
| 13 | `templates/metropolitan_dashboard.html` | 1,376 | 수도권 대시보드 |
| 14 | `templates/index.html` | 1,353 | 메인 목록 |
| 15 | `templates/partials/erp_dashboard_styles.html` | 1,338 | ERP 스타일 |
| 16 | `templates/self_measurement_dashboard.html` | 1,320 | 자가 실측 대시보드 |
| 17 | `templates/partials/erp_beta_js.html` | 1,286 | ERP Beta JS |
| 18 | `templates/partials/chat_styles.html` | 975 | 채팅 스타일 |
| 19 | `templates/erp_drawing_workbench_dashboard.html` | 796 | 도면 작업 대시보드 |
| 20 | `templates/add_order.html` | 743 | 주문 추가 |

---

## 3. 실행 우선순위 (GDM 지시)

| Phase | ID | 대상 | 예상 분할 | 담당 | 비고 |
|-------|-----|------|-----------|------|------|
| **1** | PART-001 | `partials/chat_scripts.html` (2,105줄) | chat_scripts_*.html 2~3개 | frontend-ui | 이미 partial, include 구조로 재분할 용이 |
| 2 | PART-002 | `partials/erp_dashboard_scripts.html` (1,928줄) | erp_dashboard_scripts_*.html 2~3개 | frontend-ui | ERP 공통 스크립트 |
| 3 | PART-003 | `erp_construction_dashboard.html` (2,702줄) | partials/erp_construction_*.html | frontend-ui | 시공 전용 블록 추출 |
| 4 | PART-004 | `erp_production_dashboard.html` (2,653줄) | partials/erp_production_*.html | frontend-ui | 생산 전용 블록 추출 |
| 5 | PART-005 | `calculator.html` (3,925줄) | wdcalculator/partials/*.html | frontend-ui | WD 계산기 모듈 단위 분할 |

**1차 착수**: **PART-001** (`chat_scripts.html` 분할)

---

## 4. 작업 원칙 (06-safe-changes, 01-clean-code)

- 한 번에 **1개 파일**만 분리 (동시 여러 분리 금지).
- `{% include %}` 패턴 사용, 기존 경로 유지.
- 분할 후 **서버 기동·채팅 동작** 검증 필수.
- `docs/plans/2026-02-18-file-cleanup-and-next-plan.md` 진행 상태 갱신.

---

## 4.1 PART-001 완료 (2026-02-19)

| 파일 | 줄 수 | 비고 |
|------|-------|------|
| `chat_scripts.html` | 13 | 메인 (include만) |
| `chat_scripts_core.html` | 153 | config, handleNewMessage, initializeSocketIO |
| `chat_scripts_lightbox.html` | 80 | 이미지 확대/축소 |
| `chat_scripts_utils.html` | 45 | escapeHtml, formatDate, formatDateTime, scrollToBottom |
| `chat_scripts_notifications.html` | 213 | 채팅 알림 팝업 |
| `chat_scripts_helpers.html` | 33 | autoResizeTextarea, adjustChatPageHeight |
| `chat_scripts_dom.html` | 324 | DOMContentLoaded 이벤트 |
| `chat_scripts_rooms.html` | 303 | loadRooms, renderRooms, selectRoom, renderRoomHeader |
| `chat_scripts_messages.html` | 183 | renderMessages, renderMessage, appendMessage, sendMessage |
| `chat_scripts_file.html` | 195 | 파일 미리보기, 다운로드 |
| `chat_scripts_modals.html` | 487 | 사용자, 채팅방 생성, 주문 연결, 초대, 삭제 |
| `chat_scripts_extras.html` | 168 | 타이핑 인디케이터, 메시지/전역 검색 |

---

## 5. 검증 체크리스트 (매 PART 완료 후)

- [ ] `python app.py` → 서버 기동
- [ ] 채팅 페이지 접근·메시지 송수신 확인 (PART-001)
- [ ] ReadLints (수정 파일)
- [ ] `2026-02-18-file-cleanup-and-next-plan.md` 진행 상태 갱신
- [ ] TASK_REGISTRY에 PART-00X 완료 등록

---

## 6. 산출물

- `templates/partials/chat_scripts_*.html` (PART-001 완료 시)
- 본 문서에 Phase별 완료일·비고 기록
