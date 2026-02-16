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

- 대시보드별 또는 기능별로 Blueprint/모듈 분리 (apps/erp.py 5,000줄 → 여러 파일)

---

## 진행 상태

| Phase | 상태 | 비고 |
|-------|------|------|
| 1-1 | 완료 | services/ + __init__.py 생성 |
| 1-2 | 완료 | business_calendar → services/business_calendar.py, import 경로 수정, 서버 기동 검증 |
| 1-3 | 완료 | erp_policy → services/erp_policy.py, import 경로 수정, 서버 기동 검증 |
| 1-4 | 완료 | storage → services/storage.py, import 경로 수정, 서버 기동 검증 |
| 2-1 | 완료 | 채팅 → apps/api/chat/ (chat_bp, register_chat_socketio_handlers), app.py에서 라우트·헬퍼·SocketIO 블록 제거 |
| 2-2 | 완료 | 수납장 → apps/storage_dashboard.py (storage_dashboard_bp), app.py에서 라우트 제거 |
| 2-3 | 완료 | build_file_view_url, build_file_download_url → apps/api/files.py, app.py는 import로 사용 |
| 2-4 | - | (대규모 파일 라우트는 이미 files_bp에 있어 추가 이전 없음) |
| 3-1 | 완료 | erp_dashboard.html → partials (styles, filters, grid, modals, scripts). 메인 594줄 |
| 3-2 | 완료 | chat.html → partials (chat_styles, chat_scripts). 메인 229줄 |
| - | 완료 | erp_beta → ERP 이름 변경 (apps/erp.py, Blueprint erp). feature/erp-beta-rename-to-erp |

---

## 다음 계획 (GDM 더블체크 후, 2026-02-16)

### 더블체크 결과
- **앱 기동**: `from app import app` OK
- **DB**: 연결·vacuum·제약 정상
- **코드**: app.py가 `apps.erp`·`erp_bp` 정상 참조, apps/erp.py 라우트 45개

### 우선순위

| 순서 | 단계 | 작업 | 활용 자원 | 비고 |
|------|------|------|-----------|------|
| 0 | 배포 정리 | `feature/erp-beta-rename-to-erp` → deploy 머지 후 푸시 | Shell, Git | 한글 커밋 메시지 UTF-8 확인 |
| 1 | Phase 4 준비 | apps/erp.py 구조 파악 (라우트·기능 경계) 및 1차 분리 후보 1개 선정 | Grep/Read, sequential-thinking, Rules 02/06 | 500줄 이하·한 번에 1개 모듈 |
| 2 | Phase 4-1 | 선정된 블록 분리 (예: 출고 설정 API 또는 알림 API → 별도 Blueprint/모듈) | python-backend, context7(Flask), 기동 검증 | 브랜치 feature/erp-split-* |
| 3 | 반복 | Phase 4-2, 4-3… (erp.py 5,000줄 → 여러 파일로 점진 분리) | 동일 | 목표: erp.py 500줄 이하 |
| 4 | 선택 | app.py 잔여 라우트 정리·AI/카카오/불필요 파일 | - | 슬림다운 목표 300줄 달성 후 |
