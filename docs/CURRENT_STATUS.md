# FOMS 현재 상태

## 마지막 업데이트: 2026-02-16

## 프로젝트 상태: 운영 중 + 고도화 진행

## 기술 스택
- Flask 2.3 + SQLAlchemy 2.0 + PostgreSQL
- Jinja2 + Bootstrap 5 + Vanilla JS
- Flask-SocketIO (채팅)
- Cloudflare R2 (스토리지)
- Railway (배포)

## AI 개발 시스템 현황

### Rules (.cursor/rules/ - 12개)
| # | 파일 | 용도 | alwaysApply |
|---|------|------|-------------|
| 00 | system.mdc | 프로젝트 컨텍스트 + 전체 도구 참조 | YES |
| 01 | clean-code.mdc | 클린코드 정책 | YES |
| 02 | architecture.mdc | 모듈 구조 (Blueprint) | YES |
| 03 | python.mdc | Python 코딩 규칙 | .py 파일만 |
| 04 | frontend.mdc | 프론트엔드 규칙 | templates/static만 |
| 05 | ai-workflow.mdc | Skills/Subagent/MCP 의무사용 | YES |
| 06 | safe-changes.mdc | 대형 변경 안전 프로토콜 | YES |
| 07 | skills-guide.mdc | 스킬/서브에이전트 가이드 | NO (필요시) |
| 08 | context-engineering.mdc | **컨텍스트 엔지니어링 마스터** | YES |
| 09 | instruction-compliance.mdc | **지시 준수 강제** | YES |
| 10 | self-upgrade.mdc | 자가 진화 프로토콜 | NO (필요시) |
| 11 | grand-develop-master.mdc | **GDM 개발 총괄 감독 프로토콜** | NO (필요시) |

### Subagents (.cursor/agents/ - 8개)
| 에이전트 | 역할 | 모드 |
|---------|------|------|
| **grand-develop-master** | **개발 총괄 감독 (Virtual CTO) - 품질 감사, 기술 스택 검증, 방향 제시, 자가 진화** | **오케스트레이션** |
| python-backend | Flask API, Blueprint | 읽기/쓰기 |
| frontend-ui | Bootstrap, Jinja2, JS | 읽기/쓰기 |
| database-specialist | PostgreSQL, SQLAlchemy | 읽기/쓰기 |
| code-reviewer | 코드 품질/보안 리뷰 | 읽기 전용 |
| devops-deploy | Git, Railway 배포 | 읽기/쓰기 |
| explore-codebase | 코드베이스 탐색 | 읽기 전용 |
| context-manager | 세션 기억, 토큰 최적화 | 읽기/쓰기 |

### Hooks (.cursor/hooks.json - 5개)
| 훅 | 스크립트 | 역할 |
|----|---------|------|
| sessionStart | session_start.py | 세션 로그 시작 |
| stop | session_stop.py | 세션 종료 + 편집 기록 |
| afterFileEdit | track_edits.py | 파일 편집 자동 추적 |
| **preCompact** | **pre_compact.py** | **압축 전 체크포인트 (기억 상실 방지 핵심)** |
| beforeShellExecution | guard_shell.py | 위험 명령 차단 |

### MCP (활성 6개)
sequential-thinking, mcp-reasoner, context7, postgres, memory, markitdown

### Skills
- 기본: .cursor/skills/skills/ (624개+)
- 신규: .agents/skills/ (web-design-guidelines, find-skills, frontend-design, agent-browser)

### 컨텍스트 파일 (docs/context/)
SESSION_LOG.md, EDIT_LOG.md, COMPACT_CHECKPOINT.md, DECISIONS.md, TASK_REGISTRY.md

## 최근 변경
- [2026-02-16] **Phase 3-2 완료: chat.html partial 분리** (GDM 지휘)
  - `chat.html` 3,244줄 → 229줄 (800줄 이하 달성)
  - partials: `partials/chat_styles.html` (935줄), `partials/chat_scripts.html` (2,172줄)
  - 브랜치: `feature/chat-partials`. 기동 검증 완료, deploy 머지 예정
- [2026-02-16] **Phase 3-1 완료: erp_dashboard.html partial 분리** (GDM 지휘)
  - `erp_dashboard.html` 4,309줄 → 594줄 (800줄 이하 달성)
  - partials: `erp_dashboard_styles.html`, `erp_dashboard_filters.html`, `erp_dashboard_grid.html`, `erp_dashboard_modals.html`, `erp_dashboard_scripts.html`
  - 브랜치: `feature/erp-dashboard-partials`. 기동 검증 후 deploy 머지 예정
- [2026-02-16] **Phase 2-3 완료: 파일 URL 헬퍼 이전** (GDM 지휘)
  - `build_file_view_url`, `build_file_download_url` → `apps/api/files.py`로 이동, app.py는 import 사용
  - 파일 뷰/다운로드 라우트는 기존에 이미 files_bp에 있어 추가 이전 없음
- [2026-02-16] **Phase 2-2 완료: 수납장 대시보드 분리** (app.py 슬림다운)
  - `apps/storage_dashboard.py`: storage_dashboard_bp (페이지 `/storage_dashboard`, API `/api/storage_dashboard/export_excel`)
  - app.py에서 수납장 라우트 블록 제거 (~175줄), 템플릿 `url_for('storage_dashboard.storage_dashboard')` 반영
- [2026-02-16] **Phase 2-1 완료: 채팅 API·SocketIO 분리** (app.py 슬림다운)
  - `apps/api/chat/` 패키지: `routes.py` (HTTP API), `socketio_handlers.py` (실시간 이벤트), `__init__.py`
  - app.py에서 채팅 헬퍼·라우트·SocketIO 핸들러 블록 제거 (~1,220줄 감소)
  - `chat_bp` 등록 및 `register_chat_socketio_handlers(socketio)` 호출, `/chat` 페이지는 app.py 유지
- [2026-02-16] **Phase 1 완료: services/ 도입** (GDM 지휘 하에)
  - business_calendar, erp_policy, storage → `services/` 이전
  - app.py·erp_beta·files·erp_automation·erp_build_step_runner import 경로 수정
  - 서버 기동·린트 검증 통과
- [2026-02-16] **Grand Develop Master 시스템 구축** (Agent 1개 + Skills 3개 + Rule 1개)
  - `grand-develop-master` 에이전트: 개발 총괄 감독 (Virtual CTO)
  - `grand-develop-master` 스킬: 종합 감사 방법론
  - `tech-stack-evaluator` 스킬: 기술 스택 평가 프레임워크
  - `self-evolution-factory` 스킬: AI 시스템 자가 진화 공장
  - `11-grand-develop-master.mdc` 규칙: GDM 프로토콜
- [2026-02-16] **컨텍스트 엔지니어링 시스템 구축** (Rules 3개 + Hooks 5개 + Agent 1개 + docs/context/)
- [2026-02-16] Skills 4개 설치, Subagents 6개 생성
- [2026-02-16] Cursor Rules 전면 업데이트 (MCP 6개 기준)
- [2026-02-15] MCP 22개 → 6개 최적화
- [2026-02-15] Cursor Rules 초기 생성

## 핵심 파일 크기 현황 (분리 대상)
- app.py: ~6,600줄 (Phase 2-2 후 감소, 목표: 300줄)
- apps/erp_beta.py: ~5,000줄 (점진 분리)
- templates/erp_dashboard.html: ~4,500줄 (partial 분리)
- templates/chat.html: ~3,200줄 (partial 분리)

## 고도화 예정
- [x] app.py 채팅 분리 (Phase 2-1 완료)
- [x] app.py 수납장 대시보드 분리 (Phase 2-2 완료)
- [x] app.py 파일 URL 헬퍼 이전 (Phase 2-3 완료)
- [ ] app.py 추가 슬림다운 (Phase 3 템플릿 분리 또는 erp_beta 세분화)
- [ ] AI 분석 툴 추가 (apps/api/ai.py)
- [ ] 카카오 알림톡 발송 (apps/api/kakao.py)
- [ ] 불필요 파일 정리

## 환경 정보
- 로컬 DB: postgresql://postgres:lahom@localhost:5432/furniture_orders
- 배포: Railway (deploy 브랜치)
- 스토리지: Cloudflare R2
