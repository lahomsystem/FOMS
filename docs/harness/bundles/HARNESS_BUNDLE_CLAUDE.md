# FOMS harness policy source registry and bundle defaults — claude

## Profile metadata

- **Manifest schema**: `1.0.0`
- **Profile schema**: `1.0.0`
- **Profile**: `claude`
- **Manifest**: `tools/harness/manifest.yaml`
- **Output**: `docs/harness/bundles/HARNESS_BUNDLE_CLAUDE.md`

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

### Additional runner notes

- **claude_code**: When Claude is used inside Cursor, start from HARNESS_BUNDLE_CLAUDE.md. For harness-internal architecture or policy work, switch to HARNESS_BUNDLE_CLAUDE_HARNESS.md. Open CLAUDE.md separately only when editing or validating Claude-specific source policy text.


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
