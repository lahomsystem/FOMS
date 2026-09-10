# FOMS 프로젝트 — Claude Code 세션 규칙 (v3, ablation v2 2026-09-10)

## 응답 (사용자 취향)
- 완료 보고는 한글로. 한글 문장에 한자를 쓰지 않는다(고유명사·코드·API 이름 예외) — 압축 스킬(caveman)의 축약 지시보다 이 규칙이 우선한다. 요청 단위가 끝나면 다음 진행 선택지를 AskUserQuestion 으로 묻는다(초등학생도 알기 쉬운 표현).
- 커밋 메시지는 한글. UTF-8 파일로 저장해 `git commit -F <파일>` (Windows cp949 — `-m "한글"` 금지), 커밋 후 임시 파일 삭제.

## 프로젝트 사실 (저장소에서 유도 불가)
- FOMS 가구 주문 관리 ERP. Flask + SQLAlchemy 2.0 + PostgreSQL(JSONB) + Jinja2 + Vanilla JS. 코드는 `foms/`(api·services·web·persistence·platform), 모델 `models.py`, 템플릿 `templates/`, 정적 `static/`. 새 라우트는 `foms/api/`(JSON·API·webhook)·`foms/web/`(HTML) Blueprint, 등록 정본 `foms/platform/blueprints.py`. 상수는 도메인 모듈 옆에 둔다(예 `foms/services/orders/erp_policy_constants.py`) — 루트 단일 상수 모듈은 없다.
- 배포 Railway + Cloudflare R2. 브랜치 `deploy`(스테이징) → `production`(운영). Railway 서비스는 web·WORKER·FOMS-cron·SIDEFX 4종이고 환경변수가 서비스마다 다르다.
- 여러 창이 같은 워킹트리와 `deploy` 를 공유한다. 동시 2+창 코드 편집이면 `python tools/harness/session_worktree.py create`(핫파일 예외·함정은 AGENTS.md).
- Windows 11. Claude Code 셸은 Git Bash, `python` 은 PATH. 한글 출력은 UTF-8 강제(계약 PS-ENC-01, AGENTS.md).
- 실서버 측정 계정 `claude_master`: staging 은 자유, production 은 사용자 명시 요청 1건당 1회·측정만·기본 잠금·실데이터 불가침(가상 주문 `CLAUDE-TEST-`, 정본 `docs/guides/REAL_SERVER_TEST_ACCOUNT.md`).
- 브라우저: 탐색·수동 재현 = Cursor browser MCP, 반복 QA·릴리스 스모크 = gstack browse, 디자인 검수 = gstack-design-review.
- MCP 정본 = 루트 `.mcp.json`(postgres·context7·solapi).
- 세션 시작에 `docs/AI_STATUS.md` 상단 40줄을 읽는다. 상태가 바뀌면 갱신한다(상단 4,000자 예산은 테스트가 강제). 기록 `docs/AI_CHANGELOG.md`, 결정 `docs/harness/policy/DECISIONS.md`.
- 앱 import 검증 표준 문자열 `APP_OK` — `python -c "import app; print('APP_OK')"`.

## Git (절대 규칙 — 코드 가드가 함께 강제)
- 기본 push 대상은 `deploy`. **production push 는 사용자가 명시 요청할 때만.** "deploy 푸쉬" 는 절대 production 을 포함하지 않는다.
- production 승격 = 이 세션이 만든 커밋만 cherry-pick + PR(`python tools/harness/promote_own_to_production.py --session-id <id>`). deploy 전체 merge 는 "전체 푸쉬" 명시 시에만. cherry-pick 충돌 = 타 세션 의존 신호, 임의 해결 금지.
- push 직전 `scripts/ops/pre_push_smoke.ps1` exit 0. push 뒤 CI green 까지가 완료(훅이 안내). 세션 격리 훅이 ask 하면 "전체 포함" 승인 또는 자기 몫만(`push_own_session_commits.py`).
- 절차 전문·헬퍼·워크트리 함정: `AGENTS.md` §브랜치·푸시.

## 코딩 규약 (프로젝트 고유)
- structured_data(JSONB) 수정은 `copy.deepcopy` → 수정 → 재대입 → `flag_modified(order, 'structured_data')` → commit (코드 전문 AGENTS.md).
- API 응답 `{'success', 'data', 'error'}`. 프런트: jQuery 금지, `fetch` 는 try/catch + `data.success` 검증, Jinja→JS 는 `data-*` + `safeJsonParse`. 인라인 스타일 금지 → `static/css/foundation/erp-pro.css`(ratchet 테스트가 강제).
- 성능 가드(pre_push_smoke 가 강제)·문제 수정 정책(근본 원인만)·마이그레이션 규약 전문: `AGENTS.md`. 디버깅은 `diagnosing-bugs` 스킬부터.

## 작업 방식
- 프롬프트 맨 앞 `**A`~`**D` 는 사용자의 등급 선언이다(뜻과 절차 정본 `docs/guides/LONG_TASK_PROMPTS.md`). 코어 변경(DB/Auth/API·배포·하네스)은 Spec → 승인 → 구현. 단순 UI·타이포는 바로 코딩 — superpowers brainstorming 게이트보다 우선하고, git 관련 스킬보다 위 Git 규칙이 우선한다.
- 서브에이전트 보고는 주장이다 — diff·테스트를 직접 확인한 뒤에만 완료라고 한다. 위임 브리프에는 경로:행 컨텍스트·완료 기준(검증 명령)·변경 범위를 넣는다.

# Compact instructions
압축 시 보존 우선순위: 작업 브랜치·HEAD SHA, 검증 명령과 마지막 결과 원문, 미해결 실패, 편집 파일 경로, 사용자 승인·결정. 탐색성 read/grep 출력은 버린다. 상세 복원은 `docs/harness/runtime/COMPACT_CHECKPOINT.md`.
