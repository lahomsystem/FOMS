# FOMS harness policy source registry and bundle defaults — claude-harness

## Profile metadata

- **Manifest schema**: `1.0.0`
- **Profile schema**: `1.0.0`
- **Profile**: `claude-harness`
- **Manifest**: `tools/harness/manifest.yaml`
- **Output**: `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE_HARNESS.md`

## Policy summary

### Source of truth

Phase 1 registry of canonical policy paths relative to the repository root. Values are JSON-compatible for tooling that parses with Python json.

### Shell

Default: `powershell`

Repository shared docs use PowerShell for Win11. Claude Code bash snippets apply only in contexts explicitly marked Claude Code-only.

### Browser

Mode: `delegate_web_to_cursor_browser_mcp`

Web exploration and manual QA still use Cursor browser MCP. Repeatable smoke/QA may route to generated gstack runtime assets after setup, but ad-hoc browsing remains Cursor-owned.

### Policy priority

1. Cross-tool agent baseline (AGENTS.md) (`agents_md`)
2. Claude Code session augmentation (CLAUDE.md) (`claude_md`)
3. Cursor IDE project context rules (`rules_00_project_context`)
4. Windows 11 / PowerShell shell conventions (`rules_50_win11_shell`)
5. Shared verify-result workflow contract (`workflow_verify_result`)
6. Harness engineering master plan (`plan_harness_engineering_master`)

### Additional runner notes

- **claude_code**: Use this expanded profile only for Claude-side harness work that needs both the Claude source policy and the full harness master plan in the same context.


## Included source files

## `AGENTS.md`

# FOMS 프로젝트 — AI 에이전트 공통 규칙

이 파일은 **어떤 IDE(Cursor, VS Code, JetBrains 등)**, **어떤 LLM 모델(Claude, GPT, Gemini, Codex 등)**을 사용하더라도 반드시 준수해야 하는 규칙을 정의한다.

---

## 하네스 정책 단일 기준 (Cursor · Claude · Codex 공통)

- **이식 가능한 기준선**: 본 파일(`AGENTS.md`)이 모든 도구에서 공유하는 정책의 기준이다. Codex·기타 CLI는 여기를 우선한다.
- **Cursor**: `.cursor/rules/`(특히 `00-project-context.mdc`)가 IDE 컨텍스트로 보강하며, **기준선과 충돌하면 안 된다.**
- **Claude Code**: 루트 `CLAUDE.md`가 세션 규칙으로 보강한다. **Unix/bash 예시는 “Claude Code 전용”으로 명시된 경우에만** 따른다(저장소 문서 기본값은 아래 셸 규칙).
- **앱 import 검증 성공 문자열(표준)**: `APP_OK` — `python -c "import app; print('APP_OK')"` 로 확인한다.
- **브라우저**: 탐색·수동 재현·디버깅은 **Cursor browser MCP**. 반복 가능한 QA·릴리스 스모크용 **gstack browse** 런타임은 로컬 setup가 완료된 경우 사용하고, setup 전에는 미도입으로 본다.
- **훅 fail-open**: 세션을 막지 않기 위해 예외를 삼키는 방식은 **실패가 로그 등으로 남는 경우에만** 허용한다. **묵시적 무시(조용한 swallow)는 금지**한다.
- **공통 작업 분류기**: `tools/harness/task_classifier.py`가 Cursor `beforeSubmitPrompt`, Codex 래퍼, Claude/Codex 플러그인 preflight의 단일 분류 기준이다. 출력은 `route_kind`, `level`, `context_mode`, 번들 경로, RPI·사용자 확인 필요 여부를 포함한다.
- **Wave 3 Codex wrapper**: `tools/harness/run_codex.ps1`는 작업을 `low / medium / high / top` 4단계로 자동 분류한다. 기본적으로 `low/medium`은 daily bundle, `high/top`은 `_HARNESS` bundle을 사용한다.
- **수동 override**: `-AdditionalPrompt "[level=top]"`, `-AdditionalPrompt "[레벨=최상]"`, `-AdditionalPrompt "이번 건 최상으로 진행"` 같은 형식을 지원한다.
- **고위험 downgrade 보호**: 자동 판정이 `high/top`인데 사용자가 더 낮은 레벨로 내리면, 대화형 확인이 필요하다. 비대화형 실행(CI 포함)은 `-AllowRiskyLevelOverride` 없이는 진행하지 않는다.

## 공통 실행 프로토콜 (핵심 코어 변경 시)

- **대상**: DB/Auth/API, 배포 인프라, 하네스 인프라(Hooks/Rules/Agents/검증 흐름) 같은 코어 변경
- **Research**: `docs/harness/policy/DECISIONS.md` + `docs/ARCHIVE_INDEX.md`를 먼저 조사한다.
- **Plan**: `docs/guides/SPEC_TEMPLATE.md` 기준으로 Spec 또는 실행 계획을 먼저 확정한다.
- **Implement**: 승인 후 구현하고, 완료 전 `.agents/workflows/verify-result.md` 기준으로 검증한다.
- **원칙**: 세부 절차는 도구별 문서(`CLAUDE.md`, `.cursor/rules/*.mdc`)가 보강할 수 있지만, 이 공통 프로토콜과 모순되면 안 된다.

## 절대 규칙: 문제 수정 정책

### 1. 근본 원인 파악 → 근본 수정 (Root Cause Fix Only)
- 문제 수정 시 **반드시 근본 원인(Root Cause)을 먼저 파악**한 뒤 수정한다.
- 코드 수정이나 문제 해결 시, 임시적인 방법(우회, 더 높은 규칙 적용으로 기존 코드 덮어쓰기 등)이나 근본 문제 해결 없는 수정은 **절대 금지**한다.
- **무조건 근본적인 해결(클린코드 원칙 입각)**을 하도록 수정해야 한다.
- 증상만 덮는 수정이나 "일단 돌아가게" 하는 임시 조치, 워크어라운드를 정식 수정으로 제출하지 않는다.

### 2. 금지 행위
- **에러 숨기기 금지**: `try/except: pass`, 빈 catch, 경고 무시, lint 비활성화 (훅의 fail-open도 **로그 없는** 실패 삼킴은 동일하게 금지)
- **증상 우회 금지**: 조건문으로 에러 경로만 회피, 하드코딩 값 삽입
- **구시대 방식 적용 금지**: deprecated API 사용, 레거시 패턴 복사, 폴리필 남용
- **미봉책 금지**: `# TODO: 나중에 고치기` 식의 주석으로 대체

### 3. 수정 프로세스 (필수 순서)
1. **현상 확인** — 에러 메시지, 로그, 재현 조건을 정확히 기록
2. **근본 원인 분석** — 왜 발생하는지 코드·데이터·환경 수준에서 추적
3. **수정 설계** — 올바른 현대적 방법으로 해결책 설계
4. **수정 구현** — 근본 원인을 제거하는 코드 작성
5. **검증** — 수정 후 원래 문제가 재현되지 않음을 확인

### 4. 예외 없음
- "긴급", "시간 부족"은 이 규칙의 예외 사유가 될 수 없다.
- 진짜 긴급 대응이 필요하면, 임시 조치임을 **명시적으로 선언**하고 즉시 후속 근본 수정 계획을 문서화한다.

---

## 프로젝트 기본 정보
- **이름**: FOMS (Furniture Order Management System)
- **스택**: Flask 2.3 + SQLAlchemy 2.0 + PostgreSQL + Jinja2 + Bootstrap 5 + Vanilla JS
- **운영 환경**: Windows 11 — **저장소 문서·예시 명령의 기본 셸은 PowerShell 5.x**(`.cursor/rules/50-win11-shell.mdc` 참고). bash/`&&` 등은 **Claude Code 전용**으로 문서에 명시된 때만 적용한다.
- **Git 커밋**: 한글, 무엇을 왜 수정했는지 명확히 기록

---

## `CLAUDE.md`

# FOMS 프로젝트 - Claude Code 규칙

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

## Cursor 내 Runner 사용 기준
- **Claude 확장 in Cursor**: 권장 수동 진입점은 `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE.md`이다. Cursor/확장이 이 파일을 자동 로드하는 것은 아니므로, 작업 시작 시 사용자가 직접 열거나 참조한다. 하네스 내부 작업은 `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE_HARNESS.md`를 사용한다. `CLAUDE.md`는 Claude 전용 원문 정책을 수정/검증할 때만 추가로 연다.
- **Codex 확장/CLI in Cursor**: 권장 수동 진입점은 `docs/harness/bundles/HARNESS_BUNDLE_CODEX.md`이다. Codex 확장 세션은 사용자가 bundle을 직접 열거나 참조해야 하고, `tools/harness/run_codex.ps1`를 사용할 때만 선택된 bundle이 자동으로 prompt에 포함된다. 하네스 내부 작업은 `docs/harness/bundles/HARNESS_BUNDLE_CODEX_HARNESS.md` 또는 `tools/harness/run_codex.ps1` 자동 라우팅을 사용한다.
- **공통 작업 분류기**: `tools/harness/task_classifier.py`가 Cursor 훅, `run_codex.ps1`, Claude/Codex 플러그인 preflight의 단일 기준이다. 플러그인 창이 Cursor hook을 타지 않는 경우 `python tools/harness/task_classifier.py --profile auto --prompt "..." --json`으로 같은 분류 결과를 확인한다.
- **Wave 3 자동 분류**: `run_codex.ps1`는 공통 분류기의 `low / medium / high / top` 결과를 사용한다. 기본적으로 `low/medium`은 daily bundle, `high/top`은 harness bundle을 사용한다.
- **override 형식**: `-AdditionalPrompt "[level=top]"`, `-AdditionalPrompt "[레벨=최상]"`, `-AdditionalPrompt "이번 건 최상으로 진행"`을 지원한다.
- **고위험 downgrade**: 자동 판정이 `high/top`인데 더 낮은 레벨로 내리면 대화형 재확인 또는 `-AllowRiskyLevelOverride`가 필요하다.
- **Cursor 기본 에이전트**: 기본은 `docs/harness/bundles/HARNESS_BUNDLE_CURSOR.md`와 `.cursor/rules/*.mdc`, 하네스 내부 작업은 `docs/harness/bundles/HARNESS_BUNDLE_CURSOR_HARNESS.md`를 따른다.
- **브라우저 역할 분리**: Cursor browser MCP는 탐색·재현·수동 디버깅, gstack browse는 setup 완료 후 반복 가능한 smoke/QA 자동화에 사용한다.
- **공유 명령 기준**: Cursor 안에서 Claude/Codex 확장을 써도 저장소 공용 명령 예시는 계속 PowerShell 5.x를 기준으로 본다.

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
- `git push --force main|master|deploy`
- `git reset --hard origin`
- `git clean -fdx`

## 작업 완료 체크리스트
- [ ] `python tools/harness/verify_result.py --json` 또는 최소 `python -c "import app; print('APP_OK')"` 성공
- [ ] 주요 수정 파일 lint 확인
- [ ] docs/AI_STATUS.md 갱신 (상태 변경 시)

## 참조 문서
- `docs/AI_STATUS.md` → 프로젝트 현재 상태
- `docs/AI_CHANGELOG.md` → 작업 기록
- `docs/harness/policy/DECISIONS.md` → 기술/아키텍처 결정 기록
- `docs/ARCHIVE_INDEX.md` → 과거 장애/진화/계획 인덱스
- `.cursor/agents/` → Cursor 에이전트 상세 (참고용)

---

## `.cursor/rules/00-project-context.mdc`

---
description: FOMS 프로젝트 컨텍스트. 새 세션 시작 시 AI_STATUS.md를 읽어 상황 파악.
alwaysApply: true
---

# FOMS 프로젝트 컨텍스트

## 하네스 정책 단일 기준 (Cursor · Claude · Codex)

- **공통 기준선**: 루트 `AGENTS.md`가 이식 가능한 단일 기준이다. Codex·기타 도구는 우선 `AGENTS.md`를 따른다.
- **Cursor(본 규칙)**: IDE 컨텍스트·워크플로 보강; **기준선과 모순되면 안 된다.**
- **Claude Code**: `CLAUDE.md`가 세션 규칙. **bash/Unix 예시는 “Claude Code 전용”으로 명시된 경우에만** 적용한다.
- **앱 import 검증 성공 문자열(표준)**: `APP_OK` — `python -c "import app; print('APP_OK')"` (`/verify-result`와 동일).
- **브라우저**: 탐색·수동 재현·디버깅은 **Cursor browser MCP**. 반복 가능한 QA·릴리스 스모크는 setup 완료된 **gstack browse** 런타임을 사용한다.
- **훅 fail-open**: 세션 차단을 피하려면 **실패가 로그 등에 남는 경우에만** 허용. **묵시적 무시는 금지.**

## 프로젝트 개요
- **이름**: FOMS (Furniture Order Management System) - 가구 주문 관리 ERP
- **스택**: Flask 2.3 + SQLAlchemy 2.0 + PostgreSQL + Jinja2 + Bootstrap 5 + Vanilla JS
- **배포**: Railway (PostgreSQL + R2 스토리지)
- **운영 환경**: Windows 11 (PowerShell 5.x, `\` 경로, `;` 명령 구분 — `.cursor/rules/50-win11-shell.mdc`)
- **워크플로우**: RECEIVED → HAPPYCALL → MEASURE → DRAWING → CONFIRM → PRODUCTION → CONSTRUCTION → CS → COMPLETED

## 새 세션 시작 시 + 작업 프로토콜 (RPI — 필수 준수)
1. `docs/AI_STATUS.md` 읽기 → **50줄로 전체 상황 파악**
2. **핵심 코어 변경(DB/Auth/API, 배포 인프라, 하네스 인프라) 포함 작업** → RPI 프로토콜 필수:
   - Research: `docs/harness/policy/DECISIONS.md` + `docs/ARCHIVE_INDEX.md`에서 관련 과거 기록 조사
   - Plan: `docs/guides/SPEC_TEMPLATE.md` 기반 Spec 작성 → 사용자 승인 대기
   - Implement: 승인 후 코딩 → `/verify-result` → `/auto-status-update` 실행
3. **단순 UI 변경/타이포** → 바로 코딩 허용
4. **대화가 길어지면** → 핵심 요약 후 새 세션 권유 (Dumb Zone 회피)

## Cursor 내 Runner 라우팅
- **Cursor 기본 에이전트**: 권장 수동 진입점은 `docs/harness/bundles/HARNESS_BUNDLE_CURSOR.md` + 본 `.mdc` 규칙이다. bundle 파일 자체는 Cursor가 자동 주입하지 않으므로, 사용자가 직접 열거나 참조한다. 하네스 내부 작업은 `docs/harness/bundles/HARNESS_BUNDLE_CURSOR_HARNESS.md`를 사용한다.
- **Claude 확장 in Cursor**: 권장 수동 진입점은 `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE.md`이다. bundle 파일은 자동 로드되지 않으므로, 작업 시작 시 사용자가 직접 열거나 참조한다. 하네스 내부 작업은 `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE_HARNESS.md`를 사용한다. `CLAUDE.md`는 Claude 전용 원문 정책을 수정/검증할 때만 추가로 연다.
- **Codex 확장/CLI in Cursor**: 권장 수동 진입점은 `docs/harness/bundles/HARNESS_BUNDLE_CODEX.md`이다. Codex 확장 세션은 사용자가 bundle을 직접 열거나 참조해야 하고, `tools/harness/run_codex.ps1`를 사용할 때만 선택된 bundle이 자동으로 prompt에 포함된다. 하네스 내부 작업은 `docs/harness/bundles/HARNESS_BUNDLE_CODEX_HARNESS.md` 또는 `tools/harness/run_codex.ps1` 자동 라우팅을 사용한다. repo-local gstack generated skills가 준비된 경우 `run_codex.ps1` / `run_gstack_qa.ps1` 경로를 우선 사용한다.
- **공통 작업 분류기**: `tools/harness/task_classifier.py`가 Cursor `beforeSubmitPrompt`, `run_codex.ps1`, Claude/Codex 플러그인 preflight의 단일 분류 기준이다. 플러그인 창이 hook을 타지 않으면 `python tools/harness/task_classifier.py --profile auto --prompt "..." --json` 결과를 기준으로 bundle/RPI/사용자 확인 여부를 맞춘다.
- **Wave 3 자동 레벨링**: `run_codex.ps1`는 공통 분류기의 `low / medium / high / top` 결과를 사용한다. 기본적으로 `low/medium`은 daily bundle, `high/top`은 harness bundle을 선택한다.
- **override**: `-AdditionalPrompt "[level=top]"`, `-AdditionalPrompt "[레벨=최상]"`, `-AdditionalPrompt "이번 건 최상으로 진행"`을 지원한다.
- **고위험 downgrade**: 자동 판정이 `high/top`인데 더 낮게 내리면 대화형 재확인 또는 `-AllowRiskyLevelOverride`가 필요하다.
- **브라우저 역할**: Cursor browser MCP는 탐색·수동 재현·디버깅, gstack browse는 setup 완료 후 반복 가능한 smoke/QA 자동화 전용이다.

## 문제 해결 및 디버깅 원칙 (Occam's Razor & Clean Code) - 필수 준수
프론트엔드(브라우저)에서 SyntaxError 등 라인 번호가 명시된 에러 발생을 포함한 모든 버그 해결 시:
1. **임시 방편 금지**: 코드 수정이나 문제 해결 시, 임시적인 방법(우회, 기존 코드 덮어쓰기 등)이나 근본 문제 해결 없는 수정은 절대 금지합니다. (훅의 로그 없는 실패 삼킴 포함)
2. **근본적 해결 (클린코드 입각)**: 무조건 근본적인 원인을 파악하고 클린코드 원칙에 입각하여 해결해야 합니다.
3. **가설 기반 대규모 리팩토링 금지**: 원인이 100% 규명되기 전에 구조적 결함 등을 핑계로 대규모 리팩토링을 선행하지 마세요.
4. **정확한 라인 매핑 우선**: 템플릿 렌더링 환경이라도 렌더링된 소스 확인, 스크립트 분리 테스트 등을 통해 에러가 지목한 정확한 코드 라인의 문자열(오타, 괄호 누락 등)을 반드시 먼저 확보하세요.
5. **국소적 근본 수정 우선**: 단순 오타/문법 오류가 확인되면 국소적/근본적 수정으로 먼저 해결한 뒤, 리팩토링이 필요하다면 별도 태스크로 제안만 하세요.

## 작업 완료 시 (자동)
- Cursor: Hook(session_stop)이 자동으로 AI_STATUS.md + AI_CHANGELOG.md 갱신
- 수동: `/auto-status-update` 워크플로우 실행

## 디렉토리 구조 핵심
- `app.py`: 플라스크 앱 초기화 (최소화)
- `apps/api/`: 도메인별 API Blueprint
- `services/`: 비즈니스 로직 및 정책 엔진
- `templates/`: 화면 구성 HTML
- `static/`: JS, CSS 자원

## Git 커밋 규칙
- **항상 한글 사용**, 무엇을 왜 수정했는지 명확하게 기록
- 변경 후 항상 Origin에 Push

---

## `.cursor/rules/50-win11-shell.mdc`

---
description: Windows 11 터미널/쉘 환경 규칙. 모든 명령은 Win11·PowerShell 기준으로 작성.
alwaysApply: true
---

# Win11 환경 규칙

**이 프로젝트의 로컬 운영 환경은 Windows 11입니다. 터미널 명령, 스크립트, Git 사용은 반드시 Win11에 맞게 작성·실행하세요.**

## 0. 저장소 문서 vs Claude Code (셸 소유권)

- **저장소에 공유하는 문서·README·규칙·워크플로 예시**의 **기본 셸은 Windows PowerShell 5.x**이다. 명령 연결은 `;`, 경로·따옴표 규칙은 아래 §2를 따른다.
- **bash**, `&&`, Unix 전용 리다이렉션 등은 **Claude Code 전용**이라는 문구가 있을 때만 문서에 넣는다. (Claude Code 세션은 `CLAUDE.md`의 bash 절을 따른다.)
- Cursor·Codex·기타 도구가 **복사-붙여넣기 가능한** 예시를 기대할 때는 PowerShell 예시를 쓴다.
- `pwsh`(PowerShell 7+)는 **설치된 환경에서만 선택 사용** 가능하지만, 저장소 문서의 기본 예시는 항상 **PowerShell 5.x 호환** 형태(`powershell -NoProfile -File ...`)를 우선한다.

## 1. 셸 및 명령 연결
- **기본 셸**: PowerShell (CMD가 아닌 PowerShell 기준).
- **명령 연결**: `&&` 사용 금지. PowerShell 5.x에서는 `&&`가 없어 에러가 난다. **반드시 `;`(세미콜론)**으로 명령을 이어 쓴다.
  - 예: `cd "C:\path"; git status` (O) / `cd "C:\path" && git status` (X)

## 2. 경로
- **구분자**: Windows 경로는 `\` 사용. 경로에 **공백이 있으면 반드시 큰따옴표**로 감싼다.
  - 예: `cd "c:\Users\USER\OneDrive\Desktop\SY\program\lahomproject\FOMS"`
- 상대 경로도 공백 포함 시 따옴표 사용.

## 3. Git
- **한글 커밋 메시지**: PowerShell 기본 인코딩 이슈로 `git commit -m "한글"` 사용 시 깨질 수 있다. **UTF-8로 저장한 파일을 사용해 `git commit -F 파일경로`** 로 커밋한다. 커밋 후 사용한 임시 메시지 파일은 삭제한다.
- 원격 푸시: `git push origin 브랜치이름` (동일).

## 4. 줄 연속·이스케이프
- **줄 연속**: Bash의 `\` 대신 PowerShell에서는 **백틱 `` ` ``** 사용.
- **문자 이스케이프**: PowerShell에서는 백틱 `` ` ``이 이스케이프 문자이다.

## 5. 환경 변수·스크립트
- 환경 변수 참조: Bash `$VAR` 대신 PowerShell은 **`$env:VAR`** 등 PowerShell 문법 사용.
- 실행 정책 이슈가 있으면 `Set-ExecutionPolicy` 등은 사용자에게 안내만 하고, 규칙 파일에서는 “Win11 기준으로 작성”만 명시.

## 6. 에이전트·코드 생성 시
- 터미널에서 실행할 명령을 생성할 때는 **항상 Windows 11 + PowerShell 5.x**를 가정한다.
- 문서·주석에 예시 명령을 쓸 때도 **기본은 Win11/PowerShell**; bash 스니펫은 **“(Claude Code — bash)”** 등으로 명시할 때만 사용한다.

## 7. Cursor 훅 (Agent Hooks)
- `.cursor/hooks.json` 이나 `.vscode/settings.json`에 등록된 훅 실행 시, Win11 환경에서는 `python` 명령이 사용되므로, 시스템 PATH에 등록된 Python이 올바르게 동작하도록 보장해야 한다.
- 가상환경(venv)을 사용하는 경우, `python` 대신 `.venv\Scripts\python.exe` 등 명시적 경로로 호출하거나, `terminal.integrated.env.windows` 에 PYTHONPATH를 등록해 훅에서 모듈을 찾을 수 있도록 세팅을 반영한다.

---

## `.agents/workflows/verify-result.md`

---
description: 코딩 완료 후 결과물 품질을 검증하는 워크플로우
---

# 결과 검증

0. **자동 baseline 검증(권장)**: 가능하면 먼저 `python tools/harness/verify_result.py --json` 를 실행한다.
   - Spec이 필수인 작업이면 `python tools/harness/verify_result.py --require-spec --json` 를 사용한다.
   - 이 스크립트는 `APP_OK` import 기준, 최신 Spec 탐지, "4. 검증 기준" 항목 수집 결과를 구조화해서 보여준다.

1. **앱 import 검증(표준 성공 문자열 `APP_OK`)**: `python -c "import app; print('APP_OK')"` 를 실행하여 import 오류가 없고 출력에 `APP_OK`가 포함되는지 확인한다. (`CLAUDE.md` 작업 완료 체크리스트와 동일한 기준)

2. 현재 작업의 Spec 파일(`docs/specs/*_SPEC.md`)이 있으면 읽는다.

3. Spec이 있는 경우, Spec의 "4. 검증 기준" 섹션의 항목을 하나씩 점검한다.
   - 통과하면 ✅ 표시
   - 실패하면 ❌ 표시 + 원인 기술
   - Spec이 없으면 이 단계는 생략하고 4단계 기본 품질 점검으로 진행한다.

4. 수정한 파일에 대해 기본 품질 점검:
   - 에러 처리(try-except): API 엔드포인트에 적절한 에러 처리가 있는가?
   - 하드코딩 변수: 비밀키, DB URL 등이 하드코딩되지 않았는가?
   - SQL Injection: raw SQL 사용 시 파라미터 바인딩이 되었는가?
   - XSS: 사용자 입력이 |safe 없이 렌더링되는가?

5. 모든 항목이 통과하면:
   > "✅ 검증 완료. 모든 기준을 충족합니다."

6. 실패 항목이 있으면:
   > "❌ 검증 실패. 아래 항목을 수정해야 합니다:
   > - [실패 항목 목록]
   > 수정을 진행할까요?"

---

## `docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md`

# FOMS Cursor·Claude·Codex Harness Engineering 마스터 플랜

> **작성일**: 2026-04-05  
> **작성자**: FOMS GDM / AI Development System  
> **Goal**: Cursor IDE 안에서 Cursor Agent, Claude, Codex CLI가 동일한 정책·컨텍스트·검증 루프를 공유하는 하네스 엔지니어링 체계를 구축한다.  
> **Architecture**: gstack의 강점(브라우저 QA/릴리즈/문서 동기화/운영 하네스)과 FOMS의 강점(Root Cause Fix, RPI, Hooks, Context Docs, GDM 오케스트레이션)을 혼합한 Hybrid 구조를 채택한다.  
> **Tech Stack**: Cursor IDE, Claude, Codex CLI, Python 3.12, PowerShell 5+/7, Git Bash(선택), Bun/Node(선택적 gstack 런타임), GitHub Actions  
> **상태**: Phase 5 완료 (runner UX, CI/drift, hook smoke, scripted verification baseline, operator handoff docs complete)
> **권장안**: Option C - Hybrid gstack + FOMS harness
> **후속 Spec**: `docs/specs/2026-04-05-harness-wave3-auto-level-routing_SPEC.md` (Wave 3 auto level routing / override / resource policy)

---

## 0. 배경 및 목적

### 0.1 왜 이 작업이 필요한가

- 현재 사용 환경은 **Cursor IDE + Claude + Codex CLI**의 혼합 운용이다.
- FOMS는 이미 `.cursor/rules`, `.cursor/hooks`, `.cursor/agents`, `.agents/workflows`, `docs/context/*` 기반의 강한 운영정책을 가지고 있다.
- 그러나 현재 구조는 **Cursor 중심**으로 설계되어 있어, Claude나 Codex CLI가 같은 수준의 정책·기억·검증 시스템을 자동 재사용하기 어렵다.
- gstack은 하네스 엔지니어링 측면에서 매우 강력하지만, FOMS의 Windows 11 / PowerShell / Cursor 브라우저 MCP / 도메인 정책과 그대로 맞물리지는 않는다.

### 0.2 목표

1. Cursor, Claude, Codex가 **같은 정책 그래프**를 읽게 한다.
2. gstack과 FOMS의 장점을 합쳐 **중복 없는 하네스**를 만든다.
3. 브라우저 QA, 리뷰, 출하 전 검증, 문서/컨텍스트 동기화를 **재현 가능한 시스템**으로 만든다.
4. Windows 11 + PowerShell + Cursor 환경에서 실제로 유지 가능한 구조를 만든다.
5. 하네스 자체도 테스트와 CI로 검증 가능하게 만든다.

### 0.3 비목표

- Flask 앱 기능 변경을 동시에 진행하지 않는다.
- gstack의 모든 규칙을 FOMS 위에 그대로 덮어씌우지 않는다.
- Cursor용 정책, Claude용 정책, Codex용 정책을 손으로 따로 유지하지 않는다.

### 0.4 완료 정의 (Definition of Done)

- `AGENTS.md` / `CLAUDE.md` / `.cursor/rules/*.mdc`가 **정식 정책 원본**으로 정리된다.
- Codex CLI용 컨텍스트 번들이 **자동 생성**된다.
- gstack는 repo-local로 도입되되, **명확한 역할**만 가진다.
- Cursor 훅과 Codex/CLI용 대체 검증 루틴이 분리 설계된다.
- 사용자가 Cursor 안에서 Cursor Agent / Claude / Codex 각각을 **정해진 진입점**으로 바로 사용할 수 있다.

---

## 1. 현재 상태 (AS-IS)

### 1.1 이미 강한 부분

| 카테고리 | 현재 자산 | 핵심 파일 |
|------|------|------|
| 공통 정책 | Root Cause Fix, 금지 패턴, Git/Win11 규칙 | `AGENTS.md`, `CLAUDE.md`, `.cursor/rules/*.mdc` |
| 에이전트 역할 | GDM + 역할별 서브에이전트 분리 | `.cursor/agents/*.md` |
| 훅 자동화 | 세션 시작/종료, 쉘 가드, 편집 로그, 품질 리마인더 | `.cursor/hooks.json`, `.cursor/hooks/*.py` |
| 컨텍스트 기억 | 상태/변경/세션/압축 로그 | `docs/AI_STATUS.md`, `docs/AI_CHANGELOG.md`, `docs/context/*` |
| 워크플로 | RPI, verify-result, auto-status-update | `.agents/workflows/*.md` |
| 테스트 기반 | 기본 pytest CI 존재 | `.github/workflows/ci.yml`, `tests/` |

### 1.2 현재 약한 부분

1. **Cursor 밖 runner**에 대한 정식 하네스 진입점이 없다.
2. Codex CLI가 읽어야 하는 정책 묶음이 **자동 생성되지 않는다**.
3. 브라우저 QA, canary, benchmark, release gate가 **문서/수동 절차** 중심이다.
4. 훅 구현 일부가 프로젝트 정책과 충돌한다.
5. 스킬/정책/워크플로의 **drift 검증**이 약하다.
6. `.cursor/skills`는 방대하지만, 실제 **하네스 코어**와 **보조 스킬**의 경계가 흐리다.

---

## 2. gstack 분석 요약

### 2.1 gstack에서 직접 가져올 가치

- 장수 브라우저 세션 기반 QA/Review 철학
- `/qa`, `/benchmark`, `/canary`, `/document-release` 같은 **릴리즈 트레인 사고방식**
- 스킬 문서와 명령 체계를 **자동 동기화**하려는 설계
- 운영 학습, 리뷰 준비도, 공통 프리앰블 같은 **하네스 일체화**

### 2.2 gstack를 그대로 도입하면 충돌하는 지점

- gstack는 기본적으로 `/browse` 중심 브라우저 사용을 강하게 권장하지만, FOMS는 이미 **Cursor 브라우저 MCP** 기반 운영 패턴이 있다.
- Windows에서는 Git Bash/WSL + Bun/Node 전제가 있어, PowerShell 중심 FOMS와 마찰이 있다.
- FOMS는 이미 `AGENTS.md`, `CLAUDE.md`, `.cursor/rules`, `.cursor/hooks`라는 **강한 상위 정책층**을 보유하고 있어, gstack 정책을 그대로 넣으면 중복된다.

### 2.3 채택 / 유지 / 제외 방침

| 분류 | 내용 |
|------|------|
| 채택 | repo-local skill/vendor 개념, QA/benchmark/canary/release flow, 문서 drift 방지 철학 |
| FOMS 유지 | Root Cause Fix, RPI, Hooks, Context Docs, GDM 오케스트레이션, Win11/PowerShell 규칙 |
| 수정 채택 | gstack 브라우저는 **반복 가능한 QA용**으로 한정하고, ad-hoc 탐색은 Cursor 브라우저 MCP 유지 |
| 제외 | "모든 브라우징을 gstack로 통일" 같은 전면 교체 정책 |

---

## 3. 아키텍처 선택지 비교

| 옵션 | 설명 | 장점 | 리스크 | 결론 |
|------|------|------|------|------|
| Option A | gstack 전격 도입, FOMS는 상단 규칙만 최소 유지 | 빠르게 강한 하네스 획득 | 정책 충돌, Windows/Git Bash 의존, FOMS 문맥 손실 | 비권장 |
| Option B | FOMS 자산만으로 하네스 재구현 | 완전한 자율성, Windows 친화 | 구현량 큼, 검증까지 오래 걸림 | 보조안 |
| Option C | gstack + FOMS 혼합, 역할 분리 | 현실적, 기존 자산 보존, 단계적 도입 가능 | 경계 설계가 중요 | **권장** |

### 최종 선택

**Option C - Hybrid gstack + FOMS harness**를 채택한다.

핵심 원칙은 다음과 같다.

1. **정책 원본은 FOMS가 가진다.**
2. **gstack는 런타임/QA/릴리즈 패턴 공급자**로 쓴다.
3. **Cursor / Claude / Codex는 진입점만 다르고 정책은 같아야 한다.**

---

## 4. 목표 아키텍처 (TO-BE)

```text
사용자 (Cursor IDE)
   │
   ├─ Cursor Agent
   ├─ Claude in Cursor
   └─ Codex CLI in Cursor Terminal
           │
           ▼
   Runner Profile Layer
   - cursor profile
   - claude profile
   - codex profile
           │
           ▼
   Harness Core
   - AGENTS.md
   - CLAUDE.md
   - .cursor/rules
   - .cursor/agents
   - .agents/workflows
   - docs/context
           │
           ├─ Cursor Hooks
           ├─ Bundle Generator
           ├─ Verification Scripts
           └─ gstack Runtime Adapters
                   │
                   ▼
   Outputs
   - generated context bundles
   - verify results
   - session/context logs
   - QA / benchmark / canary artifacts
```

### 4.1 단일 정책 그래프 (Single Source of Truth)

- `AGENTS.md`: 전 도구 공통 최상위 원칙
- `CLAUDE.md`: Claude 중심 세션 프로토콜
- `.cursor/rules/*.mdc`: Cursor 강제 규칙
- `.cursor/agents/*.md`: 역할별 지능 분리
- `.agents/workflows/*.md`: 실행 절차
- `docs/context/*`: 운영 메모리와 결정 로그

### 4.2 Runner Profile 계층 (신규)

Runner별로 “무슨 파일을 읽고, 무슨 절차를 강제하며, 무엇을 생략할지”를 선언형으로 관리한다.

예상 파일:

- `tools/harness/profiles/cursor.yaml`
- `tools/harness/profiles/claude.yaml`
- `tools/harness/profiles/codex.yaml`

### 4.3 gstack Vendor Zone (신규)

repo-local로 gstack를 도입하되, FOMS 하네스 바깥이 아닌 **관리 가능한 vendor zone**으로 둔다.

예상 위치:

- `.agents/skills/gstack/`

원칙:

- upstream 원본은 vendored 상태로 보존
- FOMS 전용 정책은 gstack 내부를 수정하지 않고 **브리지 레이어**에서 덮는다
- 필요 시 subtree 또는 copy-vendor 방식 중 하나를 선택한다

### 4.4 브라우저 역할 분리

| 용도 | 주 도구 |
|------|------|
| 빠른 탐색 / 화면 확인 / 디버그 | Cursor 브라우저 MCP |
| 반복 QA / release smoke / canary / benchmark | gstack 기반 브라우저 런타임 |

이 분리를 문서와 규칙에 명시하여, 브라우저 하네스 충돌을 방지한다.

---

## 5. 생성/수정 대상 파일 설계도

### 5.1 신규 생성 예정

- `.agents/skills/gstack/`
- `tools/harness/manifest.yaml`
- `tools/harness/build_context_bundle.py`
- `tools/harness/setup_gstack.ps1`
- `tools/harness/run_codex.ps1`
- `tools/harness/run_gstack_qa.ps1`
- `tools/harness/profiles/cursor.yaml`
- `tools/harness/profiles/claude.yaml`
- `tools/harness/profiles/codex.yaml`
- `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
- `docs/harness/bundles/HARNESS_BUNDLE_CURSOR.md` (generated)
- `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE.md` (generated)
- `docs/harness/bundles/HARNESS_BUNDLE_CODEX.md` (generated)
- `tests/harness/test_context_bundle.py`
- `.github/workflows/harness-ci.yml`

### 5.2 수정 예정

- `AGENTS.md`
- `CLAUDE.md`
- `.cursor/rules/00-project-context.mdc`
- `.cursor/rules/50-win11-shell.mdc`
- `.cursor/hooks.json`
- `.cursor/hooks/session_stop.py`
- `.cursor/hooks/auto_memory.py`
- `.cursor/hooks/post_task_quality_check.py`
- `.cursor/hooks/hook_payload_debug.py`
- `.cursor/agents/grand-develop-master.md`
- `.agents/workflows/verify-result.md`
- `docs/harness/policy/DECISIONS.md` (승인 후 결정 기록)
- `docs/ARCHIVE_INDEX.md`

### 5.3 유지하되 역할 명확화

- `.cursor/skills/` 전체
- `docs/AI_STATUS.md`
- `docs/AI_CHANGELOG.md`
- `docs/harness/runtime/SESSION_LOG.md`
- `docs/harness/runtime/EDIT_LOG.md`

---

## 6. 구현 Phase 설계

## Phase 0 — 정책 정합성 정리

**목표**: FOMS 내부 정책 충돌을 먼저 정리한다.

**핵심 작업**

- [x] 훅 예외 처리 정책과 `Root Cause Fix` 정책의 충돌 정리
- [x] `sessionEnd` / `stop` 이중 실행 가능성 정리
- [x] Cursor / Claude / Codex의 역할과 진입점 문서화
- [x] 브라우저 소유권 정책 확정
- [x] `OK` / `APP_OK` / 기타 성공 문자열을 단일 canonical 출력으로 통일
- [x] PowerShell 5.x 기준과 `pwsh` 선택 사용 기준을 문서로 고정

**대상 파일**

- `AGENTS.md`
- `CLAUDE.md`
- `.cursor/rules/00-project-context.mdc`
- `.cursor/rules/50-win11-shell.mdc`
- `.cursor/hooks.json`
- `.cursor/hooks/*.py`
- `.agents/workflows/verify-result.md`

**검증**

- `python -m compileall .cursor/hooks`
- `python -c "import app; print('APP_OK')"`
- 동일 세션 종료 조건에서 `session_stop.py`가 2회 호출되어도 `SESSION_LOG.md`와 `AI_CHANGELOG.md`가 중복 오염되지 않는지 확인
- Hook 실패 시 조용히 삼키지 않고 최소한의 운영 로그 또는 컨텍스트 로그가 남는지 확인
- PowerShell 5.x 기준 명령 예시와 `pwsh` 예시가 문서상 충돌하지 않는지 확인

## Phase 1 — Harness Core Manifest + Bundle Generator

**목표**: Codex/Claude/Cursor가 읽을 공통 컨텍스트 번들을 자동 생성한다.

**핵심 작업**

- [x] `manifest.yaml`로 정책 원본과 생성 규칙 정의
- [x] `build_context_bundle.py` 작성
- [x] runner profile 3종 정의
- [x] generated bundle test 추가

**대상 파일**

- `tools/harness/manifest.yaml`
- `tools/harness/build_context_bundle.py`
- `tools/harness/profiles/*.yaml`
- `tests/harness/test_context_bundle.py`

**검증**

- `python tools/harness/build_context_bundle.py --all`
- `pytest tests/harness -q`

## Phase 2 — gstack Vendor + Adapter Layer

**목표**: gstack를 전격 도입하되 FOMS 하네스와 충돌 없이 붙인다.

**핵심 작업**

- [x] `.agents/skills/gstack/` repo-local vendor 도입
- [x] PowerShell에서 Git Bash/WSL을 안전하게 호출하는 `setup_gstack.ps1` 작성
- [x] gstack QA/benchmark/canary 전용 래퍼 스크립트 작성
- [x] FOMS overlay 정책 문서화
- [x] pinned upstream snapshot 기준으로 Windows 런타임 entrypoint 최종 고정
- [x] raw fetch 가능한 static runtime subset (`ETHOS.md`, `review/*`, `qa/*`, `gstack-upgrade/*`) 확정 및 import
- [x] `setup --host codex` 실행에 필요한 build/generated-skill source layer 최소 범위 확정 및 import
- [x] `setup --host codex --no-prefix` 실행을 위한 generated Codex skills + `browse/dist` build path 검증
- [x] Bun + Codex CLI 로컬 설치 및 Windows preflight 오탐(`wsl.exe`, `browse.exe`) 수정

**대상 파일**

- `.agents/skills/gstack/`
- `.agents/skills/gstack/setup`
- `.agents/skills/gstack/package.json`
- `.agents/skills/gstack/VERSION`
- `.agents/skills/gstack/bin/*`
- `.agents/skills/gstack/browse/*`
- `.agents/skills/gstack/design/*`
- `.agents/skills/gstack/hosts/*`
- `.agents/skills/gstack/scripts/*`
- `.agents/skills/gstack/*/SKILL.md.tmpl`
- `tools/harness/setup_gstack.ps1`
- `tools/harness/import_gstack_source_slice.py`
- `tools/harness/run_gstack_qa.ps1`
- `docs/guides/HARNESS_ENGINEERING_OPERATOR_GUIDE.md`
- `.agents/skills/gstack/upstream/*`

**검증**

- `powershell -NoProfile -File tools/harness/setup_gstack.ps1 -WhatIf`
- `python tools/harness/import_gstack_source_slice.py --dry-run`
- `powershell -NoProfile -File tools/harness/run_gstack_qa.ps1 -DryRun`
- `codex login status`
- `& "C:\Program Files\Git\bin\bash.exe" -lc "cd '/c/.../.agents/skills/gstack' && bash ./setup --host codex --no-prefix"`
- `pwsh`가 설치된 환경에서는 동일 명령이 호환되는지 추가 확인

## Phase 3 — Cursor / Claude / Codex Runner Experience

**목표**: 사용자가 어떤 runner를 써도 동일한 하네스를 체감하게 만든다.

**핵심 작업**

- [x] Cursor profile 적용 규칙 작성
- [x] Claude in Cursor 전용 운영 섹션 정리
- [x] Codex CLI wrapper와 generated context 연결
- [x] GDM에서 runner별 실행 트랙 설명 가능하도록 보강
- [x] refreshed bundle 기준 runner dry-run 재검증
- [x] Cursor/Claude extension presence 기준 동등 운영자 확인

**대상 파일**

- `CLAUDE.md`
- `.cursor/rules/*.mdc`
- `.cursor/agents/grand-develop-master.md`
- `tools/harness/run_codex.ps1`
- `tools/harness/profiles/*.yaml`
- `docs/harness/bundles/HARNESS_BUNDLE_*.md`

**검증**

- Cursor chat dry run 1회
- Claude dry run 1회
- Codex CLI dry run 1회
- `python tools/harness/build_context_bundle.py --all`
- Cursor-installed Claude/Codex extension asset 존재 확인

## Phase 4 — Verification / CI / Drift Control

**목표**: 하네스 자체가 깨지지 않게 만든다.

**핵심 작업**

- [x] harness 전용 CI workflow 추가
- [x] generated bundle drift check 추가
- [x] 훅 단위 테스트 또는 smoke test 추가
- [x] verify-result를 스크립트화할지 결정

**대상 파일**

- `.github/workflows/harness-ci.yml`
- `.gitattributes`
- `tests/harness/*`
- `.agents/workflows/verify-result.md`

**검증**

- `python -m compileall -q .cursor/hooks`
- `python tools/harness/verify_result.py --json`
- `python tools/harness/build_context_bundle.py --all`
- `python -m pytest tests/harness -q`
- `git diff --exit-code -- docs/harness/bundles/HARNESS_BUNDLE_CURSOR.md docs/harness/bundles/HARNESS_BUNDLE_CLAUDE.md docs/harness/bundles/HARNESS_BUNDLE_CODEX.md`
- `powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" -Url "https://example.com" -Scenario "erp-smoke" -DryRun`
- GitHub Actions green

## Phase 5 — 운영 문서 / 팀 사용법 정착

**목표**: 사용자가 실제로 매일 쓸 수 있게 정리한다.

**핵심 작업**

- [x] 운영자 가이드 작성
- [x] runner별 시작 예시 추가
- [x] 장애 시 fallback 경로 정리
- [x] 새 계획/결정 파일 인덱싱 절차 반영

---

## 7. 병렬 에이전트 실행 구조

이 작업은 다음 4개 트랙으로 병렬화한다.

| 트랙 | 담당 에이전트 후보 | 범위 |
|------|------|------|
| Track A | `devops-deploy` | gstack vendor, PowerShell/Git Bash bridge, setup scripts |
| Track B | `python-backend` | hooks 정합성 수정, bundle generator, verify 스크립트 |
| Track C | `evolution-architect` | 정책 통합, runner profile 설계, hybrid 원칙 고도화 |
| Track D | `code-reviewer` | 하네스 자체 품질 게이트, drift/리스크 검토 |

원칙:

1. 같은 파일을 동시에 수정하는 병렬 작업은 금지한다.
2. Phase 0 완료 전에는 vendor 도입이나 runner wrapper 구현을 merge하지 않는다.
3. 각 Track는 결과를 `docs/harness/policy/DECISIONS.md` 또는 계획 문서에 반영 가능한 형태로 반환해야 한다.

---

## 8. 구현 후 사용 방법 (예정 운영 UX)

### 8.1 Cursor Agent in Cursor Chat

예정 사용 방식:

1. 계획서 또는 Spec를 열고 Cursor Chat에 참조한다.
2. 다음처럼 요청한다.

```text
GDM 방향 제시: @docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md
Phase 1부터 subagent-driven으로 실행해 줘
```

### 8.2 Claude in Cursor

예정 사용 방식:

1. `CLAUDE.md`와 generated bundle을 기준으로 세션을 시작한다.
   - 주의: Cursor/확장이 이 파일들을 자동 로드하는 것은 아니므로, 사용자가 직접 열거나 참조한다.
2. 다음처럼 요청한다.

```text
@docs/harness/bundles/HARNESS_BUNDLE_CLAUDE.md 를 기준으로
현재 브랜치 하네스 변경안 리뷰 후 Phase 2 작업 착수
```

### 8.3 Codex CLI in Cursor Terminal

예정 사용 방식:

```powershell
powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile review -Target "AGENTS.md"
powershell -NoProfile -File "tools/harness/run_codex.ps1" -Profile implement -Plan "docs/plans/2026-04-05-cursor-claude-codex-harness-engineering-master-plan.md"
powershell -NoProfile -File "tools/harness/run_gstack_qa.ps1" -Url "https://staging.example.com" -Scenario "erp-smoke"
```

`pwsh`가 설치된 환경에서는 `pwsh -File ...` 사용도 허용하되, 문서 기본값은 **Windows 기본 PowerShell 5.x 호환 예시**로 유지한다.

### 8.4 브라우저 사용 원칙

- 빠른 탐색 / 구조 확인: Cursor 브라우저 MCP
- 반복 회귀 / release smoke / canary / benchmark: gstack runtime

---

## 9. 리스크와 대응

| 리스크 | 설명 | 대응 |
|------|------|------|
| 정책 drift | Cursor/Claude/Codex 설명이 서로 달라짐 | generated bundle + manifest + CI diff check |
| Windows 마찰 | PowerShell, Git Bash, Bun/Node 혼합 | wrapper 스크립트로 표준화 |
| 훅 의존성 | Cursor 훅은 Codex CLI에서 자동 실행되지 않음 | Codex wrapper에 preflight/postflight 추가 |
| 브라우저 충돌 | Cursor MCP와 gstack browse가 서로 역할을 침범 | 사용 목적을 문서로 고정 |
| 하네스 비대화 | `.cursor/skills`와 gstack가 함께 비대해짐 | harness core vs optional skills 분리 |

---

## 10. 최종 권고

지금 단계에서 가장 현실적인 구현 순서는 다음과 같다.

1. **Phase 0**: 정책 충돌 제거
2. **Phase 1**: bundle generator + runner profile 구축
3. **Phase 2**: gstack vendor + adapter 도입
4. **Phase 3~4**: Codex/Claude/Cursor runner UX와 CI 고도화

즉, **gstack를 먼저 넣고 나중에 맞추는 방식**이 아니라,  
**FOMS 하네스 코어를 먼저 정리한 뒤 gstack를 연결하는 방식**이 정답이다.

이 순서를 지켜야 Cursor, Claude, Codex가 동시에 쓰여도 정책이 흐트러지지 않는다.
