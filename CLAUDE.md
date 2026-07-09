# FOMS 프로젝트 - Claude Code 규칙

## 응답 규칙 (절대)
- **완료 보고는 무조건 한글로 작성한다.** 작업 결과 요약·검증 결과·다음 단계 안내 등 사용자에게 보고하는 모든 문장은 한글. (코드·커밋 메시지·명령어는 예외)

## 하네스 정책 단일 기준 (Cursor · Claude · Codex)

- **공통 기준선**: 루트 `AGENTS.md`가 모든 도구에 공유되는 정책이다. 본 파일은 Claude Code 세션 보강이며, 충돌 시 `AGENTS.md`가 우선한다.
- **Cursor**: `.cursor/rules/00-project-context.mdc` 등 IDE 규칙이 추가로 적용된다.
- **앱 import 검증 성공 문자열(표준)**: `APP_OK` — `python -c "import app; print('APP_OK')"` (워크플로 `/verify-result`와 동일).
- **브라우저**: 수동 탐색·재현·디버깅은 **Cursor browser MCP**. 반복 가능한 QA·릴리스 스모크는 setup 완료된 **gstack browse** 런타임을 사용한다.
- **훅 fail-open**: 허용은 **실패가 로그 등으로 기록될 때만**. 묵시적 무시는 금지(`AGENTS.md`와 동일).

## 프로젝트 개요
- **이름**: FOMS (Furniture Order Management System) - 가구 주문 관리 ERP
- **스택**: Flask 2.3 + SQLAlchemy 2.0 + PostgreSQL + Jinja2 + Bootstrap 5 + Vanilla JS
- **배포**: Railway (PostgreSQL + Cloudflare R2 스토리지)
- **운영 환경**: Windows 11 — **저장소 공유 문서의 기본 명령 예시는 PowerShell 5.x**. 아래 “셸 환경 (Claude Code 전용)”의 bash 예시는 **Claude Code 세션에서만** 해당한다.
- **워크플로우**: RECEIVED → HAPPYCALL → MEASURE → DRAWING → CONFIRM → PRODUCTION → CONSTRUCTION → CS → COMPLETED

## 새 세션 시작 프로토콜
1. `docs/AI_STATUS.md` 읽기 → 50줄로 전체 상황 파악
2. **핵심 코어 변경(DB/Auth/API, 배포 인프라, 하네스 인프라)** → RPI 프로토콜 필수:
   - Research: `docs/harness/policy/DECISIONS.md` + `docs/ARCHIVE_INDEX.md` 조사
   - Plan: 작업 Spec 작성 → 사용자 승인 대기
   - Implement: 승인 후 코딩 → 검증
3. **단순 UI 변경/타이포** → 바로 코딩 허용
4. **대화가 길어지면** → 핵심 요약 후 새 세션 권유

## 하네스 자동 배선 (Claude Code 세션)
- **세션 시작/컴팩트**: `SessionStart` 훅이 AI_STATUS·RPI 안내를 주입하고, `PreCompact` 훅이 `docs/harness/runtime/COMPACT_CHECKPOINT.md`를 갱신한다.
- **Stop 게이트**: `.py` 편집 세션은 턴 종료 시 `import app` 검증을 자동 통과해야 한다 (실패 시 종료 차단, 근본 수정 후 재시도).
- **push 후 CI 게이트(논블로킹)**: `PostToolUse:Bash` 훅 `post_push_watch.py`가 `git push`/`gh pr merge` 성공을 감지하면 `additionalContext`로 CI 확인을 주입한다. 확인은 **블로킹 금지** — `python tools/harness/ci_watch.py`는 `run_in_background`로 돌리거나 `--quick`(폴링 없이 단발 조회: exit 0=green·1=코드 실패·4=진행 중·3=gh 불가)으로 즉시 상태만 보고 작업을 계속한다. CI green 확인이 push 완료의 정의이나 완주 대기로 세션을 막지 않는다.
- **MCP 정본 위치**: 프로젝트 MCP 서버는 루트 `.mcp.json` (postgres, context7만 유지 — 나머지는 네이티브 기능으로 대체되어 퇴역).
- **하네스 내부 작업 컨텍스트**: Cursor/Codex 러너 라우팅 상세는 `AGENTS.md` + `.cursor/rules/00-project-context.mdc` 소관 (본 파일에서 중복 제거). 상시 커밋 번들은 폐기됨(2026-07-08 재설계 Phase 1b) — 온디맨드 컨텍스트 번들이 필요하면 `python tools/harness/build_context_bundle.py --all`로 생성한다(커밋하지 않음).

## 디렉토리 구조
- `app.py`: Flask 앱 초기화 (최소화, 라우트 추가 금지)
- `apps/api/`: 도메인별 API Blueprint
- `services/`: 비즈니스 로직 및 정책 엔진
- `templates/`: Jinja2 HTML 템플릿
- `static/`: JS, CSS 자원
- `models.py`: DB 모델 (Order, User, OrderAttachment 등)
- `constants.py`: 상수 정의

## 코딩 규칙

### Python/Backend
- **app.py에 코드 추가 금지** → 새 API는 `apps/api/` Blueprint로
- **함수 50줄 이하**, 한 가지 역할만 수행
- **docstring 필수** (목적, 파라미터, 반환값)
- **타입 힌트 필수** (신규 함수)
- **API 응답 형식 통일**: `{'success': True/False, 'data': ..., 'error': ...}`
- **structured_data(JSONB) 수정 패턴**:
  ```python
  import copy
  from sqlalchemy.orm.attributes import flag_modified
  sd = copy.deepcopy(order.structured_data or {})
  # ... 수정 ...
  order.structured_data = sd
  flag_modified(order, 'structured_data')
  db.commit()
  ```

### Frontend
- **인라인 스타일 금지** → `static/css/foundation/erp-pro.css` 사용
- **jQuery 사용 금지** → `querySelector`, `fetch()` 사용
- **인라인 script 300줄 초과 시** 별도 `.js` 파일로 분리
- **템플릿 800줄 초과 시** `{% include 'partials/이름.html' %}` partial 분리
- **Jinja2 + JS 데이터 전달**: `JSON.parse('{{ x|tojson }}')` 금지
  - 권장: `data-*` 속성 + `safeJsonParse` 패턴
- **fetch 에러 처리 필수**: try/catch + `data.success` 검증

### Database
- **PostgreSQL 15+**, SQLAlchemy 2.0 ORM, Alembic 마이그레이션
- **마이그레이션**: autogenerate 후 수동 검토 필수, `downgrade()` 포함
- **JSONB 수정**: 반드시 `copy.deepcopy` + `flag_modified`

## 성능 회귀 원천 차단 (필수, 자동 강제)
코드/기능 추가가 서버·페이지를 느리게 만드는 것을 **머지 전에 차단**한다. 상세·사유: `docs/guides/PERFORMANCE_GUARDRAILS.md`. 자동 가드: `tests/performance/test_perf_regression_guard.py`(pre_push_smoke 포함, exit 0 아니면 push 금지).
- **프론트 `<script>`는 기본 `defer`**(또는 `type="module"`). 렌더 차단 동기 스크립트 신규 추가 금지(가드 G1). 코어 라이브러리만 예외(가드 allowlist + 사유).
- **외부 CDN 동기 `<script>` 신규 금지**(가드 G2). 무거운 라이브러리(html2canvas 등)는 **사용 시점 lazy 로드**(전역 로드 금지). 공용 partial에 페이지 전용 무거운 JS 추가 금지.
- **ERP shell fragment 재실행 JS는 idempotent 필수**(가드 G4). 모바일 shell/P2 bundle JS가 `window`/`document`/`body` 전역 listener를 추가하면 `window.__*_BOUND` 같은 singleton guard로 중복 바인딩을 차단.
- **서비스워커 network-first fetch는 timeout+캐시 폴백 필수**(가드 G3). 무한 대기→탭 스피너 금지.
- **JSONB/text `cast(...).ilike('%..%')`는 인덱스 없이 hot path 금지**: 부분일치=trigram(`gin_trgm_ops`), id 멤버십=`@>`. 새 인덱스는 생성 SQL과 byte-match + `EXPLAIN`로 인덱스 사용 확인.
- **N+1 금지**(리스트는 `in_(ids)` 배치), **매 요청 무거운 계산은 캐시**(Redis micro-cache).
- **마이그레이션 CONCURRENTLY + 다중 replica**: `env.py`는 세션 레벨 `pg_advisory_lock`(xact 락은 내부 COMMIT에 풀려 레이스→INVALID 인덱스).
- **검증**: 대시보드/리스트/검색/액션 변경은 머지 전 **서버 TTFB 측정 + `EXPLAIN`로 Seq Scan 없음** 확인. "느리다" 신고는 **서버 TTFB부터** 측정해 서버/프론트/SW 분리. SW 동작은 실제 Chrome에서 확인(헤드리스 미등록).

## 문제 수정 정책 (절대 규칙)

### 근본 원인 파악 → 근본 수정 (Root Cause Fix Only)
- 반드시 근본 원인(Root Cause)을 먼저 파악한 뒤 수정
- 코드 수정이나 문제 해결 시, 임시적인 방법(우회, 더 높은 규칙 적용으로 기존 코드 덮어쓰기 등)이나 근본 문제 해결 없는 수정은 **절대 금지**
- **무조건 근본적인 해결(클린코드 원칙 입각)**을 하도록 수정
- 증상만 덮는 수정 절대 금지

### 금지 행위
- 에러 숨기기: `try/except: pass`, 빈 catch, 경고 무시 (훅에서 로그 없이 실패를 삼키는 것 포함)
- 증상 우회: 조건문으로 에러 경로만 회피, 하드코딩 값 삽입
- 구시대 방식: deprecated API 사용, 레거시 패턴 복사
- 미봉책: `# TODO: 나중에 고치기` 식 주석

### 수정 프로세스
1. **현상 확인** → 에러 메시지, 로그, 재현 조건 기록
2. **근본 원인 분석** → 코드/데이터/환경 수준 추적
3. **수정 설계** → 올바른 현대적 방법으로 해결책 설계
4. **수정 구현** → 근본 원인 제거
5. **검증** → 원래 문제 미재현 확인

## 디버깅 원칙 (Occam's Razor)
- **가설 기반 대규모 리팩토링 금지**: 원인 100% 규명 전 구조적 결함 핑계 금지
- **정확한 라인 매핑 우선**: 브라우저 에러 라인의 실제 코드 먼저 확보
- **국소적 수정 우선**: 오타/문법 오류면 국소 수정 후, 리팩토링은 별도 제안
- **단순화 우선**: "이 코드를 고칠 수 있는가?"보다 "이 코드를 없앨 수 있는가?"
- **시간 차원 인지**: "지금 보인다" ≠ "아까도 있었다" (Timing Gap 경계)

## Git 규칙
- **커밋 메시지**: 한글로, 무엇을 왜 수정했는지 명확히 기록
- **한글 커밋 (Win11)**: UTF-8 파일 저장 후 `git commit -F 파일경로` 사용 (`-m "한글"` 금지)
- **커밋 후 임시 파일 삭제**: commit_msg.txt 등 정리
- **선택적 접두어**: `feat:`, `fix:`, `refactor:`, `docs:`, `chore:`
- **대형 변경**: feature 브랜치에서 작업
- **브랜치 전략**: `deploy` (스테이징) → `production` (운영)
- **운영(production) 푸시는 사용자 명시 요청 시에만 (절대 규칙)**: 기본 푸시 대상은 항상 `deploy`(스테이징, lahom-dev)다. `production`(운영) 브랜치로의 push·force-push·reset은 **사용자가 명시적으로 "production 푸시/배포"를 요청했을 때만** 수행한다. **"deploy 푸쉬"는 절대 `production`을 포함하지 않는다.** 스테이징 검증 → 사용자 승인 → 운영 승격 순서를 지키며, 임의 운영 푸시는 금지한다.
- **푸시 전 스모크**: `deploy`/`main` push **직전** `powershell -NoProfile -File scripts/ops/pre_push_smoke.ps1` (APP_OK·harness verify·SSOT lint·CI subset·`test_p1_mockup_*` 구조 테스트). **UI/CSS/템플릿 변경** 시 PNG `-Visual`/win32 baseline은 필수 아님(선택). exit 0 확인 후 push. `-Full`은 머지 직전 전체 pytest. 상세: `docs/guides/PRE_PUSH_SMOKE.md`
- **푸시 후 CI green 확인 (push 완료의 정의)**: push 직후 `python tools/harness/ci_watch.py`(기본 HEAD·deploy; production은 `... HEAD production`)로 CI 완료를 감시한다. exit 0=green, **exit 1=코드 실패 → 근본 수정 → pre_push_smoke → 재푸시까지가 한 작업 단위**, exit 2=자동 재실행(재폴링), exit 3=gh 미설치/미인증. `post_push_watch` 훅이 push 감지 시 이 실행을 자동 리마인드하므로 생략 금지.

## 셸 환경 (Claude Code 전용)
- Claude Code는 **bash 셸** 사용 (Unix 문법: `/dev/null`, `&&`, forward slash). **이 절의 예시는 Claude Code에만 적용**; 저장소 README·규칙 문서에 적는 기본 예시는 PowerShell 5.x를 따른다.
- 단, Git 커밋 메시지는 Win11 인코딩 이슈로 `-F` 방식 유지
- `python` 명령은 시스템 PATH 기준

## 보안 규칙
- SQL injection 방지: ORM 사용
- XSS 방지: Jinja2 autoescaping
- 하드코딩 비밀키/비밀번호 절대 금지
- CSRF 보호 적용
- bare except 금지 (구체적 예외 명시)

## 위험 명령 차단
다음 명령은 절대 실행 금지:
- `rm -rf /`, `rm -rf ..`
- `drop database`, `drop table`, `truncate table`
- `git push --force main|master|deploy|production` (특히 `production` 강제푸시·리셋은 사용자 명시 승인 필수)
- 사용자 명시 요청 없는 `production` 브랜치 push (일반 push 포함)
- `git reset --hard origin`
- `git clean -fdx`

## 작업 완료 체크리스트
- [ ] `python tools/harness/verify_result.py --json` 또는 최소 `python -c "import app; print('APP_OK')"` 성공
- [ ] 주요 수정 파일 lint 확인
- [ ] docs/AI_STATUS.md 갱신 (상태 변경 시)
- [ ] `deploy`/`main` push 직전 `scripts/ops/pre_push_smoke.ps1` 실행 → exit 0 확인

## 참조 문서
- `docs/AI_STATUS.md` → 프로젝트 현재 상태
- `docs/AI_CHANGELOG.md` → 작업 기록
- `docs/harness/policy/DECISIONS.md` → 기술/아키텍처 결정 기록
- `docs/ARCHIVE_INDEX.md` → 과거 장애/진화/계획 인덱스
- `.cursor/agents/` → Cursor 에이전트 상세 (참고용)
