# FOMS 현재 상태

## 마지막 업데이트: 2026-02-17

## 세션 재개 시 이어서 작업 가용자원 (컨텍스트 풀 시)

- **Rules**: 08-context-engineering(점진 로딩), 02-architecture(Blueprint), 06-safe-changes(대형 변경), 11-grand-develop-master(GDM)
- **Skills**: grand-develop-master, architect-review, code-reviewer, python-pro, flask-pro
- **Agents**: grand-develop-master(총괄), python-backend(API), code-reviewer(검증), context-manager(기억)
- **복원 순서**: COMPACT_CHECKPOINT → CURRENT_STATUS → TASK_REGISTRY → (이어지는 작업) phase4-next-steps / DECISIONS
- **Memory MCP**: `memory read_graph` → GDM_DoubleCheck_2026-02-16 최신 관찰로 다음 스텝 확인

## 저장 메모리·컨텍스트 요약 (전체 확인용)

| 구분 | 위치 | 요약 |
|------|------|------|
| **Memory (MCP)** | memory read_graph | 엔티티 `GDM_DoubleCheck_2026-02-16` — 4-3·4-4 완료, 다음: deploy 머지·4-5 주문 API 분할 |
| **COMPACT_CHECKPOINT** | docs/context/COMPACT_CHECKPOINT.md | 압축 시 복원: CURRENT_STATUS → TASK_REGISTRY → DECISIONS → EDIT_LOG 순 참조 |
| **DECISIONS** | docs/context/DECISIONS.md | Flask 유지, MCP 6개, 컨텍스트 엔지니어링, services/ 도입 |
| **TASK_REGISTRY** | docs/context/TASK_REGISTRY.md | SLIM-001~006 완료 (4-1~4-4). 신규 작업 시 여기 등록 |
| **EDIT_LOG** | docs/context/EDIT_LOG.md | 최근 편집 파일 자동 추적 (Hook) |
| **DEPLOY_NOTES** | docs/DEPLOY_NOTES.md | 배포 시 쉬운 한글 요약 (Phase 4-2·4-1·ERP 이름 변경 반영) |

## 프로젝트 상태: 운영 중 + 고도화 진행

### 백업/복원
- 관리자 > 시스템 백업: **백그라운드 실행** (타임아웃/연결 끊김 방지). DB 설정은 `DATABASE_URL` 또는 `DB_*` 환경변수 사용.
- 백업 내용: **DB 전체**(주문·상태·실측·체크리스트·워크플로우 등 `structured_data` 포함) + 시스템 파일. 복원 시 동일 상태로 복원됨.
- **2026-02-17 GDM 분석**: 백업 시 콘솔에 보이던 Socket.IO 오류(ERR_CONNECTION_RESET, 400)는 채팅/실시간 연결 실패로, 백업 API와 무관. 관리자 페이지에서 Socket.IO 미로드하도록 `layout.html` 조건 추가 → 백업 화면에서 해당 콘솔 오류 제거. 상세: `docs/evolution/GDM_BACKUP_ISSUE_ANALYSIS_2026-02-17.md`.

## 기술 스택
- Flask 2.3 + SQLAlchemy 2.0 + PostgreSQL
- Jinja2 + Bootstrap 5 + Vanilla JS
- Flask-SocketIO (채팅)
- Cloudflare R2 (스토리지)
- Railway (배포)

## AI 개발 시스템 현황

### Rules (.cursor/rules/ - 14개, GDM 기준)
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
| 12 | macro-micro-migration-execution.mdc | 매크로/마이크로 마이그레이션 실행 | NO (필요시) |
| 13 | self-evolution-autoupgrade.mdc | 자가 진화 자동 업그레이드 | NO (필요시) |

### Subagents (.cursor/agents/ - 10개, GDM 기준)
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
| coding-research-center | 주간 딥리서치, 적용 큐 | 읽기/쓰기 |
| evolution-architect | 진화/업그레이드 설계 | 읽기/쓰기 |
| migration-executor | 매크로/마이크로 마이그레이션 실행 | 읽기/쓰기 |

### Hooks (.cursor/hooks.json - 5개)
| 훅 | 스크립트 | 역할 |
|----|---------|------|
| sessionStart | session_start.py | 세션 로그 시작 |
| stop | session_stop.py | 세션 종료 + 편집 기록 |
| afterFileEdit | track_edits.py | 파일 편집 자동 추적 |
| **preCompact** | **pre_compact.py** | **압축 전 체크포인트 (기억 상실 방지 핵심)** |
| beforeShellExecution | guard_shell.py | 위험 명령 차단 |

### MCP (활성 6개 + filesystem, GDM 기준)
sequential-thinking, mcp-reasoner, context7, postgres, memory, markitdown, filesystem

### Skills
- 기본: .cursor/skills/skills/ (624개+)
- 신규: .agents/skills/ (web-design-guidelines, find-skills, frontend-design, agent-browser)

### 컨텍스트 파일 (docs/context/)
SESSION_LOG.md, EDIT_LOG.md, COMPACT_CHECKPOINT.md, DECISIONS.md, TASK_REGISTRY.md

### 배포 내용 (쉬운 한글)
**docs/DEPLOY_NOTES.md** — deploy에 올릴 때마다 "뭘 했는지" 누구나 알 수 있게 쉬운 말로 정리

## 최근 변경
- [2026-02-17] **Phase 4-5c 완료: 도면 창구 업로드 분리** (GDM 더블체크 후 진행)
  - `erp_orders_drawing_bp`에 `/<id>/drawing-gateway-upload` POST 추가. `apps/erp.py`에서 1라우트 제거 (~45줄). erp.py **3,350줄·25라우트**.
- [2026-02-17] **Phase 4-5b 완료: 도면 전달/취소 API 분리**
  - `apps/api/erp_orders_drawing.py`: transfer-drawing, cancel-transfer. erp.py 2라우트 제거 (~460줄).
- [2026-02-17] **Phase 4-5a 완료: 주문 Quick API 분리** (GDM 지휘·전 자원 동원)
  - `apps/api/erp_orders_quick.py` 신규: `erp_orders_quick_bp`. 라우트 quick-search, quick-info, quick-status. erp.py 3라우트 제거 (~206줄).
- [2026-02-17] **Phase 4-4 완료: 지도/주소/유저 API 분리** (GDM 더블체크 후 가용자원 총동원)
  - `apps/api/erp_map.py` 신규: `erp_map_bp`. 라우트 `/api/map_data`, `/erp/api/users`, `/api/generate_map`, `/api/orders/<id>/update_address`. `apps/erp.py`에서 4라우트 제거 (~460줄 감소). 기동·린트 검증 통과.
- [2026-02-17] **Phase 4-3 완료: 실측 API 분리** (GDM 자원 동원)
  - `apps/api/erp_measurement.py` 신규: `erp_measurement_bp` (url_prefix=`/api/erp/measurement`). 라우트 `/update/<order_id>` POST, `/route` GET.
  - `apps/erp.py`에서 해당 2라우트 제거 (~206줄 감소). app.py에 `erp_measurement_bp` 등록. 기동·린트 검증 통과.
- [2026-02-17] **DEPLOY_NOTES.md**: Phase 4-2(출고 설정) 배포 내용 추가 (쉬운 한글).
- [2026-02-16] **채팅창 가로폭/입력창 잘림 수정**
  - `templates/partials/chat_styles.html`: `.chat-page-content`에 `flex-direction: row`, `width: 100%` 추가
  - `.col-lg-3` / `.col-lg-9`에 비율 고정(25%/75%), `.col-lg-9`에 `min-width: 0` 적용
  - `.chat-main-card`, `.chat-input-area`, `.chat-input-wrapper`에 `width: 100%`, `min-width: 0` 적용
  - 메시지 입력창이 전체 컨테이너 가로폭을 활용하도록 수정
- [2026-02-16] **Phase 4-1 완료: 알림 API 분리** (GDM 관장) → deploy 푸시 완료
  - `apps/api/notifications.py` 신규 (목록/배지/읽음 처리). `apps/erp.py`에서 해당 블록 제거 (~297줄 감소)
  - 배포 내용 쉬운 한글: `docs/DEPLOY_NOTES.md` 추가
- [2026-02-16] **erp_beta → ERP 이름 변경** (GDM 관장)
  - `apps/erp_beta.py` → `apps/erp.py`, Blueprint `erp_beta` → `erp`
  - `can_edit_erp_beta` → `can_edit_erp`, `apply_erp_beta_display_fields*` → `apply_erp_display_fields*`
  - 템플릿 `url_for('erp_beta.xxx')` → `url_for('erp.xxx')`, draft API `/api/orders/erp/draft`
  - DB 컬럼 `is_erp_beta`·env `ERP_BETA_ENABLED`는 호환 유지
- [2026-02-16] **Phase 3-2 완료: chat.html partial 분리** (GDM 지휘)
  - `chat.html` 3,244줄 → 229줄 (800줄 이하 달성)
  - partials: `partials/chat_styles.html` (935줄), `partials/chat_scripts.html` (2,172줄)
  - 브랜치: `feature/chat-partials`. deploy 머지 완료
- [2026-02-16] **Phase 3-1 완료: erp_dashboard.html partial 분리** (GDM 지휘)
  - `erp_dashboard.html` 4,309줄 → 594줄 (800줄 이하 달성)
  - partials: `erp_dashboard_styles.html`, `erp_dashboard_filters.html`, `erp_dashboard_grid.html`, `erp_dashboard_modals.html`, `erp_dashboard_scripts.html`
- [2026-02-16] **Phase 2-3 완료: 파일 URL 헬퍼 이전** (GDM 지휘)
  - `build_file_view_url`, `build_file_download_url` → `apps/api/files.py`로 이동, app.py는 import 사용
- [2026-02-16] **Phase 2-2 완료: 수납장 대시보드 분리** (app.py 슬림다운)
  - `apps/storage_dashboard.py`: storage_dashboard_bp (페이지 `/storage_dashboard`, API `/api/storage_dashboard/export_excel`)
- [2026-02-16] **Phase 2-1 완료: 채팅 API·SocketIO 분리** (app.py 슬림다운)
  - `apps/api/chat/` 패키지: `routes.py`, `socketio_handlers.py` — app.py에서 라우트·SocketIO 블록 제거 (~1,220줄 감소)
- [2026-02-16] **Phase 1 완료: services/ 도입** (GDM 지휘 하에)
  - business_calendar, erp_policy, storage → `services/` 이전
  - app.py·erp·files·erp_automation·erp_build_step_runner import 경로 수정
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
- app.py: ~6,500줄 (목표: 300줄, Phase 4·추가 분리 대기)
- apps/erp.py: ~3,350줄·25 라우트 (Phase 4-1~4-5c 분리 반영, 목표: 500줄 이하)
- templates/erp_dashboard.html: 594줄 (partial 분리 완료, 3-1)
- templates/chat.html: 229줄 (partial 분리 완료, 3-2)

## 가용 자원 더블체크 (GDM 기준, 2026-02-16)

| 구분 | 계획 | 실제 | 비고 |
|------|------|------|------|
| Rules | 14 (00~13) | 14개 .mdc | 12 매크로/마이그레이션, 13 자가진화 |
| Agents | GDM + 10 서브 | 11개 .md | coding-research-center, evolution-architect, migration-executor 포함 |
| Hooks | 5 | 5개 .py | session_start/stop, track_edits, pre_compact, guard_shell |
| MCP | 6+ | sequential-thinking, mcp-reasoner, context7, postgres, memory, markitdown, filesystem | GDM 문서 기준 |
| Skills | GDM/tech-stack/self-evolution/architect/code-review/production-audit | .cursor/skills/skills/ | 624개+ 공통 스킬 |
| 배포 노트 | DEPLOY_NOTES.md | docs/DEPLOY_NOTES.md | 쉬운 한글 배포 내용 |

## 다음 계획 (GDM 더블체크 2026-02-17)
- **0.** feature/erp-split-shipment-settings → deploy 머지·푸시 (Phase 4-2 반영, DEPLOY_NOTES 갱신 완료)
- **1.** Phase 4-3: 실측 API 분리 ✅ 완료 (erp_measurement_bp)
- **2.** Phase 4-4: 지도·주소·유저 API 분리 ✅ 완료 (erp_map_bp)
- **3.** Phase 4-5a: 주문 Quick API 분리 ✅ 완료 (erp_orders_quick_bp)
- **4.** Phase 4-5b: 도면 전달/취소 API 분리 ✅ 완료 (erp_orders_drawing_bp)
- **5.** Phase 4-5c: 도면 창구 업로드 분리 ✅ 완료 (drawing-gateway-upload → erp_orders_drawing_bp)
- **6.** Phase 4-5d~: 주문 API 잔여 블록 (request-revision, 도면/생산/시공/AS 등, erp.py 500줄 이하 목표)
- **계획서**: `docs/plans/2026-02-16-phase4-next-steps.md`

## 고도화 예정
- [x] app.py 채팅 분리 (Phase 2-1 완료)
- [x] app.py 수납장 대시보드 분리 (Phase 2-2 완료)
- [x] app.py 파일 URL 헬퍼 이전 (Phase 2-3 완료)
- [x] Phase 3 템플릿 분리 (erp_dashboard·chat partial 완료)
- [ ] app.py 추가 슬림다운 (Phase 4 ERP 모듈 세분화 등)
- [ ] AI 분석 툴 추가 (apps/api/ai.py)
- [ ] 카카오 알림톡 발송 (apps/api/kakao.py)
- [ ] 불필요 파일 정리

## 환경 정보
- 로컬 DB: postgresql://postgres:lahom@localhost:5432/furniture_orders
- 배포: Railway (deploy 브랜치)
- 스토리지: Cloudflare R2
