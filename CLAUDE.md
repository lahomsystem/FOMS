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
- **Wave 3 자동 분류**: `run_codex.ps1`는 `low / medium / high / top` 4단계로 작업을 자동 분류한다. 기본적으로 `low/medium`은 daily bundle, `high/top`은 harness bundle을 사용한다.
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
- **인라인 스타일 금지** → `static/css/erp-pro.css` 사용
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
