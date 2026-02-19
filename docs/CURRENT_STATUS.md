# FOMS 현재 상태

## 마지막 업데이트: 2026-02-19 (Phase 3 스모크 5건 통과, GDM 감사 반영)

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
- [2026-02-19] **NEXT-004 완료: db_admin 비밀번호 환경변수화**
  - scripts/db_admin.py: FOMS_ADMIN_DEFAULT_PASSWORD 사용. init·reset-admin 기본값 제거. DEPLOY_NOTES 반영.
- [2026-02-19] **완료 더블체크 + 다음 단계 정리 + NEXT-003 pytest 도입**
  - NEXT-002 PART-003·004·005 완료 확인. **NEXT-003 완료**: tests/, pytest 3 passed. **NEXT-004 완료**: db_admin 환경변수화.
- [2026-02-18] **NEXT-002 PART-005 완료: calculator.html partial 분리**
  - calculator.html 3,925줄 → 15줄 (메인: extends + include 3개).
  - wdcalculator/partials/wdcalculator_styles.html (~380줄), wdcalculator_body.html (266줄), wdcalculator_scripts.html (~3,454줄).
  - header-info, header-warning, border-left-info, border-left-warning 스타일 추가.
  - `python -c "import app"` OK. NEXT002 §4.5, TASK_REGISTRY 갱신 완료.
- [2026-02-19] **GDM 더블체크 + NEXT-002 PART-003·004 완료**
  - GDM 검증 체크리스트: `python -c "import app"` OK, ReadLints OK, 페이지 스모크(시공·생산 대시보드 302) OK.
  - Jinja2+JSON: `JSON.parse('{{ x|tojson }}')` 패턴 없음 — construction/production partials는 data-* + safeJsonParse 사용.
  - PART-003: erp_construction_dashboard.html 1,794줄 → 120줄 (styles, filters_grid, modals, scripts 분리).
  - PART-004: erp_production_dashboard.html 3,016줄 → 120줄 (동일 패턴).
  - NEXT002 지시서 §4.3·§4.4, TASK_REGISTRY 갱신 완료.
- [2026-02-18] **배포·정리·품질 감사**
  - DEPLOY_NOTES.md에 2026-02-18 배포 내용(ERP 화면 분리) 한글로 추가. deploy 브랜치 푸시 완료. (커밋 메시지는 한글 깨짐 방지로 영문 사용: `deploy: ERP split and 2026-02-18 deploy notes`)
  - 불필요 파일 정리: `docs/plans/SLIM_DOWN_PROGRESS_2026-02-17.md` 삭제(계획서로 대체), .gitignore에 `config/local*` 추가.
  - GDM 개발 품질 감사 실행: `docs/evolution/GDM_AUDIT_2026-02-18.md` 작성 (점수 72/100, 긴급 0건, 개선 권장 6건, 양호 8건).
- [2026-02-18] **ERP-SLIM-7~10 + erp.py 전체 분리 완료 (40줄)**
  - `apps/erp_shipment_page.py` 신규: `erp_shipment_page_bp` (/erp/shipment, ~250줄)
  - `apps/erp_as_page.py` 신규: `erp_as_page_bp` (/erp/as, ~60줄)
  - `apps/erp_production_page.py` 신규: `erp_production_page_bp` (/erp/production/dashboard, ~170줄)
  - `apps/erp_construction_page.py` 신규: `erp_construction_page_bp` (/erp/construction/dashboard, ~160줄)
  - erp.py → 허브 역할만 (필터 등록 + display re-export + _normalize_for_search). 656줄 → **40줄**
  - url_for 전수 수정: erp_sub_nav, erp_shipment_dashboard, erp_shipment_settings, erp_production_dashboard
- [2026-02-18] **ERP-SLIM-6: 실측 대시보드 분리**
  - `apps/erp_measurement_dashboard.py` 신규: `erp_measurement_dashboard_bp` (/erp/measurement). erp.py에서 해당 블록 제거 (~190줄 감소). url_for → erp_measurement_dashboard.erp_measurement_dashboard, layout endpoint 체크 수정.
- [2026-02-17] **SLIM-025: bulk_action → order_pages_bp**
  - order_pages_bp에 bulk_action 라우트 추가 (삭제/복사/상태변경). app.py ~146줄 감소 (~1,568줄).
- [2026-02-17] **SLIM-024: delete/trash/restore → order_trash_bp**
  - `apps/order_trash.py` 신규: delete_order, trash, restore_orders, permanent_delete_orders, permanent_delete_all_orders, reset_order_ids. `services/request_utils.py`: get_preserved_filter_args. app.py ~254줄 감소 (~1,714줄).
- [2026-02-17] **SLIM-023: index+add_order → order_pages_bp**
  - `apps/order_pages.py` 신규: index, add_order. `services/order_display_utils.py`: format_options_for_display, _ensure_dict. app.py ~576줄 감소.
- [2026-02-17] **SLIM-022: /api/orders 캘린더 API → orders_bp**
  - FullCalendar용 주문 이벤트 API `api_orders` → `apps/api/orders.py` (orders_bp). app.py ~200줄 감소.
- [2026-02-17] **주소/경로 API 4개 → erp_map_bp 통합**
  - calculate_route, address_suggestions, add_address_learning, validate_address. app.py ~130줄 감소.
- [2026-02-17] **structured API Blueprint 분리**
  - `apps/api/erp_orders_structured.py` 신규: structured GET/PUT, parse-text, erp/draft. app.py ~380줄 감소.
- [2026-02-17] **blueprint API Blueprint 분리**
  - `apps/api/erp_orders_blueprint.py` 신규: api_upload_blueprint, api_get_blueprint, api_delete_blueprint. app.py ~95줄 감소.
- [2026-02-17] **Quest Blueprint 분리**
  - `apps/api/quest.py` 신규: api_order_quest_get/create/approve/update_status. app.py ~700줄 감소.
- [2026-02-17] **events Blueprint 분리**
  - `apps/api/events.py` 신규: api_order_events, api_order_change_events, api_my_change_events, api_revert_change_event. app.py ~700줄 감소.
- [2026-02-17] **dashboards Blueprint 분리**
  - `apps/dashboards.py` 신규: regional_dashboard, metropolitan_dashboard, self_measurement_dashboard. app.py ~350줄 감소.
- [2026-02-17] **attachments Blueprint 분리**
  - `apps/api/attachments.py` 신규: api_order_attachments_list/upload/patch/delete. ensure_order_attachments_* 헬퍼 이전. app.py ~320줄 감소.
- [2026-02-17] **wdcalculator Blueprint 분리**
  - `apps/api/wdcalculator.py` 신규: wdcalculator_bp. 페이지 /wdcalculator, /wdcalculator/product-settings, API /api/wdcalculator/*. app.py ~992줄 감소 (~5,576줄).
- [2026-02-17] **Phase 4-5h(3)(4) 완료: drawing 2개·confirm/customer 분리**
  - erp_orders_revision_bp에 drawing/request-revision, drawing/complete-revision 추가. erp_orders_confirm.py 신규: confirm/customer. erp.py 주문 API 라우트 **전부 분리 완료** (~350줄 추가 감소).
- [2026-02-17] **Phase 4-5h(2) 완료: AS API 분리**
  - `apps/api/erp_orders_as.py` 신규: erp_orders_as_bp. 라우트 as/start, as/complete, as/schedule. erp.py 3라우트 제거 (~260줄).
- [2026-02-17] **Phase 4-5h(1) 완료: CS 완료 API 분리**
  - `apps/api/erp_orders_cs.py` 신규: erp_orders_cs_bp. 라우트 cs/complete. erp.py 1라우트 제거 (~70줄).
- [2026-02-17] **Phase 4-5g 완료: 시공 API 분리**
  - `apps/api/erp_orders_construction.py` 신규: erp_orders_construction_bp. 라우트 construction/start, construction/complete, construction/fail. erp.py 3라우트 제거 (~220줄).
- [2026-02-17] **Phase 4-5f 완료: 생산 API 분리**
  - `apps/api/erp_orders_production.py` 신규: erp_orders_production_bp. 라우트 production/start, production/complete. erp.py 2라우트 제거 (~125줄).
- [2026-02-17] **Phase 4-5e 완료: 도면 담당자 지정/확정 API 분리**
  - `apps/api/erp_orders_draftsman.py` 신규: erp_orders_draftsman_bp. 라우트 assign-draftsman, batch-assign-draftsman, confirm-drawing-receipt. erp.py 3라우트 제거 (~400줄).
- [2026-02-17] **Phase 4-5d 완료: 도면 수정 요청/체크 API 분리**
  - `apps/api/erp_orders_revision.py` 신규: erp_orders_revision_bp. 라우트 request-revision, request-revision-check. erp.py 2라우트 제거 (~250줄).
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
- app.py: **~319줄** (목표: 300줄 근접, SLIM-026~034 완료)
- apps/erp.py: **40줄** (허브 역할만 - 모든 대시보드 페이지 분리 완료, 목표 500줄 이하 달성)
- templates/erp_dashboard.html: 594줄 (partial 분리 완료, 3-1)
- templates/chat.html: 229줄 (partial 분리 완료, 3-2)
- templates/erp_construction_dashboard.html: **120줄** (PART-003 완료)
- templates/erp_production_dashboard.html: **120줄** (PART-004 완료)

## 가용 자원 더블체크 (GDM 기준, 2026-02-16)

| 구분 | 계획 | 실제 | 비고 |
|------|------|------|------|
| Rules | 14 (00~13) | 14개 .mdc | 12 매크로/마이그레이션, 13 자가진화 |
| Agents | GDM + 10 서브 | 11개 .md | coding-research-center, evolution-architect, migration-executor 포함 |
| Hooks | 5 | 5개 .py | session_start/stop, track_edits, pre_compact, guard_shell |
| MCP | 6+ | sequential-thinking, mcp-reasoner, context7, postgres, memory, markitdown, filesystem | GDM 문서 기준 |
| Skills | GDM/tech-stack/self-evolution/architect/code-review/production-audit | .cursor/skills/skills/ | 624개+ 공통 스킬 |
| 배포 노트 | DEPLOY_NOTES.md | docs/DEPLOY_NOTES.md | 쉬운 한글 배포 내용 |

## 다음에 시작할 작업 (2026-02-19 갱신)
- **완료**: GDM 감사 1회 실행 (`docs/evolution/GDM_AUDIT_2026-02-19.md`). Phase 3 스모크 5건 통과 (test_erp 404 허용 반영).
- **우선 착수**: Phase 3 계속(API/주문 상태 테스트 추가) 또는 CI(GitHub Actions) 검토. NEXT-003·NEXT-004 완료.
- **보류**: app.py SLIM-035 (319줄→300줄) — 일단 중단, 필요 시 app-slim 계획서에서 재개.
- **배포**: erp.py 분리·대형 템플릿 partial 반영 후 deploy 푸시 진행.
- **이후 순서**: Phase 3 테스트 확대·CI/CD. 계획표 §3 참조.
- **계획서**: `docs/plans/2026-02-18-file-cleanup-and-next-plan.md`, `docs/plans/2026-02-17-erp-split-plan.md`, `docs/plans/2026-02-18-app-slim-task-plan.md`

## 고도화 예정
- [x] app.py 채팅 분리 (Phase 2-1 완료)
- [x] app.py 수납장 대시보드 분리 (Phase 2-2 완료)
- [x] app.py 파일 URL 헬퍼 이전 (Phase 2-3 완료)
- [x] Phase 3 템플릿 분리 (erp_dashboard·chat partial 완료)
- [x] app.py·erp.py 슬림다운 (app ~319줄, erp 40줄 — 목표 달성)
- [x] **파일 정리** (CLEAN-001~005) — 완료
- [~] app.py 300줄 이하 (SLIM-035) — **보류**
- [x] order_pages.py 500줄 이하 분리 (NEXT-001) — edit_order → apps/order_edit.py
- [x] 대형 템플릿 partial PART-001~005 (NEXT-002) — chat_scripts, erp_dashboard_scripts, erp_construction, erp_production, calculator (wdcalculator/partials)
- [x] NEXT-003: pytest 도입 (tests/, 스모크 5건 통과)
- [x] NEXT-004: db_admin 비밀번호 환경변수화 (FOMS_ADMIN_DEFAULT_PASSWORD)
- [ ] AI 분석 툴 (apps/api/ai.py), 카카오 알림톡 (kakao.py) — 선택

## 환경 정보
- 로컬 DB: postgresql://postgres:lahom@localhost:5432/furniture_orders
- 배포: Railway (deploy 브랜치)
- 스토리지: Cloudflare R2
