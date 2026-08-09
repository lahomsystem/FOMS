# FOMS 프로젝트 - Claude Code 규칙

## 응답 규칙 (절대)
- **완료 보고는 무조건 한글로 작성한다.** (코드·커밋 메시지·명령어는 예외)
- **작업이 끝나면 항상 다음 진행 단계 선택지를 AskUserQuestion으로 모두 물어본다 — 초등학생도 알기 쉬운 표현으로.** 완료 보고만 하고 끝내지 말 것. (요청 단위 완료 시점 기준, 진행 중 중간 단계에는 강제 아님)

## 정책 기준선
- **공통 정책 SSOT = 루트 `AGENTS.md`** (문제 수정 정책·성능 가드 상세·git 승격 절차 전문). 본 파일은 Claude Code 세션 보강이며, 충돌 시 `AGENTS.md`가 우선한다. 절차 상세가 필요하면 그때 `AGENTS.md`를 읽는다.
- **앱 import 검증 성공 문자열(표준)**: `APP_OK` — `python -c "import app; print('APP_OK')"`
- **훅 fail-open**: 실패가 로그로 기록될 때만 허용. 묵시적 무시 금지.
- **브라우저 QA**: 반복 가능한 QA·릴리스 스모크는 gstack browse 런타임.
- **실서버 측정 계정 `claude_master`**: 기본=staging(전 활동 허용), production=사용자 명시 요청 1건당 1회·측정만·**기본 잠금**(해제→측정→재잠금)·실데이터 불가침(가상 주문 `CLAUDE-TEST-`+더미 연락처, 부하 금지). 정본: `docs/guides/REAL_SERVER_TEST_ACCOUNT.md`.

## 프로젝트 개요
- **이름**: FOMS (Furniture Order Management System) - 가구 주문 관리 ERP
- **스택**: Flask 2.3 + SQLAlchemy 2.0 + PostgreSQL + Jinja2 + Bootstrap 5 + Vanilla JS
- **배포**: Railway (PostgreSQL + Cloudflare R2 스토리지), 브랜치 `deploy`(스테이징) → `production`(운영)
- **운영 환경**: Windows 11 — 저장소 공유 문서의 명령 예시는 PowerShell 5.x, Claude Code 세션은 bash.
- **워크플로우**: RECEIVED → HAPPYCALL → MEASURE → DRAWING → CONFIRM → PRODUCTION → CONSTRUCTION → CS → COMPLETED

## 새 세션 시작 프로토콜
1. `docs/AI_STATUS.md` 상단 40줄만 읽기 → 전체 상황 파악 (아래는 상세 기록, 필요 시 grep)
2. **핵심 코어 변경(DB/Auth/API, 배포 인프라, 하네스 인프라)** → RPI 필수: Research(`docs/harness/policy/DECISIONS.md`+`docs/ARCHIVE_INDEX.md` 조사) → Plan(Spec 작성 → 사용자 승인 대기) → Implement
3. **단순 UI 변경/타이포** → 바로 코딩 허용
4. **대화가 길어지면** → 핵심 요약 후 새 세션 권유

## 작업 등급 마커 (프롬프트 맨 앞 `**A`~`**D` = 사용자 명시 선언 — 해당 절차 생략 금지)
- `**A` 소형: 완료 기준이 없으면 착수 전 1줄 스스로 정의. 나머지는 기본 프로토콜(직접/단일 위임 → 검증 → 보고, 플랜 생략).
- `**B` 하루: 플랜+progress ledger 작성(task마다 완료 기준 필수) → 요약 승인 1회 → 이 세션에서 완주(task마다 위임→검증→커밋→ledger 갱신).
- `**C` 릴레이: 프롬프트에 플랜/ledger 경로가 있으면 다음 PENDING부터 재개(막히면 BLOCKED 기록 후 전진), 없으면 스펙+플랜+ledger 설계 후 승인 대기. 작업 단위 끝나면 `/clear <이름>` 권고.
- `**D` 최고 안전등급: `**C` 설계 앞단에 CEO 리뷰+3-agent 교차검수+파일럿 1 task 추가. 무인 본진은 플랜 확정 후 `/overnight <플랜> <T범위>` 명령을 만들어 제시하고 사용자가 입력한다(자동 진입 금지).
- `**A출고버그`처럼 마커 뒤에 글자가 바로 붙어도 마커로 해석한다. 상세: `docs/guides/LONG_TASK_PROMPTS.md`(+`_EASY.md`).

## 하네스 자동 배선 (Claude Code 세션)
- **Stop 게이트**: `.py` 편집 세션은 턴 종료 시 `import app` 검증 자동 통과 필수 (실패 시 종료 차단, 근본 수정 후 재시도).
- **push 후 CI 확인(논블로킹)**: push 성공 시 훅이 리마인드 주입. `python tools/harness/ci_watch.py`를 `run_in_background` 또는 `--quick`(exit 0=green·1=코드 실패·4=진행 중·3=gh 불가)으로. **CI green까지가 push 완료의 정의**, 단 완주 대기로 세션을 막지 않는다. exit 1이면 근본 수정 → pre_push_smoke → 재푸시까지가 한 작업 단위.
- **컴팩트**: `PreCompact` 훅이 `docs/harness/runtime/COMPACT_CHECKPOINT.md` 갱신, 재개 시 그 파일부터 읽기.
- **MCP 정본**: 루트 `.mcp.json` (postgres, context7, youtube). youtube=자막 조회(uvx mcp-youtube-transcript), 메타데이터 보조=`yt-dlp` CLI.
- **온디맨드 컨텍스트 번들**: `python tools/harness/build_context_bundle.py --all` (커밋하지 않음).

## 스킬 (2026-08-03 ablation 후 — 근거: DECISIONS.md)
- **프로젝트 스킬 5종**(`.claude/skills/`): diagnosing-bugs(디버깅 진입점, tight feedback loop — 버그를 빨강으로 만드는 단일 명령 먼저)·wayfinder·handoff·writing-great-skills·overnight. 범용 발췌 7종(ECC 5·taste 2)은 모델 기본 지식과 중복이라 제거.
- **superpowers 방법론 스킬**(brainstorming·writing-plans 등): 필요 시 온디맨드 호출. **git 관련 스킬보다 본 파일 Git 규칙이 항상 우선.** "단순 UI 변경/타이포 → 바로 코딩" 예외가 brainstorming HARD-GATE보다 우선.
- **디자인 작업**: gstack-design-review 주력(실브라우저 검증 루프). 인라인 스타일 금지·erp-pro.css 체계가 항상 우선.

## 디렉토리 구조
- `app.py`: Flask 앱 초기화 (최소화, 라우트 추가 금지) / 새 API는 `apps/api/` Blueprint로
- `services/`: 비즈니스 로직·정책 엔진, `templates/`: Jinja2, `static/`: JS·CSS
- `models.py`: DB 모델, `constants.py`: 상수

## 코딩 규칙

### Python/Backend
- 함수 50줄 이하, 한 가지 역할. **docstring 필수**(목적·파라미터·반환값), **타입 힌트 필수**(신규 함수).
- **API 응답 형식 통일**: `{'success': True/False, 'data': ..., 'error': ...}`
- **structured_data(JSONB) 수정 패턴** (필수):
  ```python
  import copy
  from sqlalchemy.orm.attributes import flag_modified
  sd = copy.deepcopy(order.structured_data or {})
  # ... 수정 ...
  order.structured_data = sd
  flag_modified(order, 'structured_data')
  db.commit()
  ```
- bare except 금지(구체적 예외 명시), 하드코딩 비밀키 절대 금지.

### Frontend
- **인라인 스타일 금지** → `static/css/foundation/erp-pro.css` 사용
- **jQuery 금지** → `querySelector`, `fetch()`. fetch는 try/catch + `data.success` 검증 필수.
- 인라인 script 300줄 초과 시 `.js` 분리, 템플릿 800줄 초과 시 partial 분리.
- **Jinja2→JS 데이터**: `JSON.parse('{{ x|tojson }}')` 금지 → `data-*` 속성 + `safeJsonParse`.

### Database
- PostgreSQL 15+, SQLAlchemy 2.0 ORM, Alembic. 마이그레이션은 autogenerate 후 수동 검토 + `downgrade()` 포함.

## 성능 회귀 차단 (자동 강제)
- 가드 `tests/performance/test_perf_regression_guard.py`가 코드로 강제(G1 defer·G2 CDN·G3 SW timeout·G4 idempotent — pre_push_smoke 포함, exit 0 아니면 push 금지). 규칙 상세: `AGENTS.md` + `docs/guides/PERFORMANCE_GUARDRAILS.md`.
- hot path 쿼리: JSONB `ilike` 인덱스 없이 금지(trigram/`@>`), N+1 금지(`in_(ids)` 배치), 무거운 계산 캐시. 대시보드/리스트 변경은 머지 전 TTFB 측정 + `EXPLAIN` Seq Scan 없음 확인.

## 문제 수정 정책 (절대 규칙 — 전문: AGENTS.md)
- **근본 원인 수정만.** 증상 덮기·우회·에러 숨기기(`try/except: pass`)·하드코딩 우회·`# TODO` 미봉책 금지. 프로세스: 현상 확인 → 근본 원인 분석 → 설계 → 구현 → 원문제 미재현 검증.
- **디버깅(Occam)**: 정확한 라인 매핑 우선, 국소 수정 우선, "고칠 수 있는가"보다 "없앨 수 있는가", "지금 보인다"≠"아까도 있었다"(Timing Gap 경계). 원인 100% 규명 전 가설 기반 대규모 리팩토링 금지.

## Git 규칙 (절차 전문: AGENTS.md §브랜치·푸시)
- **커밋 메시지 한글**, Win11 인코딩 이슈로 UTF-8 파일 저장 후 `git commit -F 파일경로` (`-m "한글"` 금지). 커밋 후 임시 파일 삭제. 접두어 `feat:`/`fix:`/`refactor:`/`docs:`/`chore:` 선택적.
- **production push는 사용자 명시 요청 시에만 (절대 규칙).** 기본 푸시 대상은 항상 `deploy`. **"deploy 푸쉬"는 절대 production을 포함하지 않는다.**
- **production 승격 = 세션 자기 커밋 cherry-pick 기본 (절대 규칙).** "전체 푸쉬" 명시 없으면 deploy HEAD 전체 merge 금지(타 세션 미검증 커밋 혼입). 절차·헬퍼(`promote_completeness.py`·`promote_own_to_production.py`)는 AGENTS.md. cherry-pick 충돌 = 타 세션 의존 신호 → 임의 해결 금지, 사용자 확인.
- **deploy push 세션 격리**: 타 세션 커밋 포함 시 훅이 ask — 자기 몫만은 `push_own_session_commits.py`.
- **동시 2+창 코드 편집** 시 `python tools/harness/session_worktree.py create` (선택 표준, 절차는 AGENTS.md). 핫파일(tablet 계약테스트·layout_head·tablet-bundle.css)은 공유 트리 유지.
- **push 직전** `scripts/ops/pre_push_smoke.ps1` exit 0 확인. 위험 명령(보호 브랜치 강제푸시·DB drop·`reset --hard` 등)은 `guard_policy.py` 훅이 코드로 차단.

## 셸 환경 (Claude Code 전용)
- bash 셸 (Unix 문법). 저장소 공유 문서 예시는 PowerShell 5.x 기준 유지. `python`은 시스템 PATH.

## 작업 완료 체크리스트
- [ ] `python tools/harness/verify_result.py --json` 또는 최소 `APP_OK` 성공
- [ ] 주요 수정 파일 lint 확인
- [ ] docs/AI_STATUS.md 갱신 (상태 변경 시)
- [ ] `deploy`/`main` push 직전 pre_push_smoke exit 0

# Compact instructions
컨텍스트 압축 시 보존 우선순위: 작업 브랜치·HEAD SHA, 검증 명령과 마지막 결과(성공/실패 원문), 미해결 실패, 편집 파일 경로 목록, 사용자 승인·결정 사항. 탐색성 read/grep/대형 도구 출력은 버린다. 상세 복원은 `docs/harness/runtime/COMPACT_CHECKPOINT.md`가 담당.

## 참조 문서
- `docs/AI_STATUS.md` → 현재 상태 / `docs/AI_CHANGELOG.md` → 작업 기록
- `docs/harness/policy/DECISIONS.md` → 기술 결정 기록 / `docs/ARCHIVE_INDEX.md` → 과거 인덱스
