# 실서버 측정·테스트 계정 (claude_master) — 정책 정본

> 2026-08-04 신설 (사용자 지시). AI 세션의 staging·production 실서버 측정/QA 전용.

## 계정

| 항목 | 값 |
|---|---|
| username | `claude_master` |
| role | ADMIN (양쪽 동일) |
| staging | lahom-dev.up.railway.app — users.id **58** |
| production | lahom-production.up.railway.app — users.id **57** |
| password_policy_version | 1 (STRONG) |

**비밀번호는 이 저장소에 없다.** 로컬 전용 파일:
`C:\Users\USER\.claude\projects\c--DEV-FOMS\secrets\claude_master.json`
(username·password·양쪽 base URL 포함. 저장소에 커밋 절대 금지. 유출 의심 시 아래 로테이션 절차로 즉시 교체.)

## 사용 정책 (절대 규칙)

1. **기본 테스트는 staging.** staging에서는 모든 활동 허용 (쓰기·시드·삭제·부하 측정 포함).
2. **production 측정은 사용자 명시 요청 시에만.** 허용 범위: TTFB/HTTP 측정, F12 devtools(콘솔·네트워크 로그), 페이지 열람 등 관측 전반.
3. **production 실데이터는 절대 건드리지 않는다.** 실주문·사용자·설정·첨부 등 기존 행의 생성 외 변경/삭제 일절 금지. DB 직결 조회는 읽기전용(`set_session(readonly=True)`)만.
4. production에서 쓰기 동작 검증이 필요하면 **가상 테스트 주문을 새로 만들어** 테스트한다:
   - 식별 마킹 필수: 고객명 `CLAUDE-TEST-` 접두어
   - 테스트 종료 시 **본인이 만든 가상 데이터만** 정리(soft delete 포함 확인)
   - 실주문을 테스트 대상으로 삼는 것 금지

## 측정 레시피

- 로그인: `POST /login` form(username/password), CSRF 불요, 성공=302.
- **desktop UA 필수** (모바일 UA는 v2/v3 셸 리다이렉트로 측정 오염).
- 쓰기 API는 페이지 HTML `<meta name="csrf-token">` 추출 후 `X-CSRFToken` 헤더.
- TTFB 대표값은 warm 표본 **min** (tail 오염 면역 — tools/perf/staging_perf_gate.py 방법론).
- 대시보드 검색 판정: 검색어 에코 오탐 주의 — 없는 문자열 검색과 응답 길이 비교.

## 비밀번호 로테이션 절차

1. 새 비번 생성 + `werkzeug.security.generate_password_hash`.
2. scratchpad 하위 별도 디렉토리에서 `railway link -p FOMS-DEV` / `-p FOMS-PRODUCTION` (링크는 디렉토리별 — 저장소 디렉토리 링크 오염 금지) → `railway variables --service Postgres --json`의 `DATABASE_PUBLIC_URL`.
3. 양쪽 DB `UPDATE users SET password=<hash>, password_policy_version=1 WHERE username='claude_master'`.
4. 로컬 secrets 파일 갱신 → HTTP 302 오라클로 양쪽 검증.

## 관련

- CI perf-gate는 별도 계정 `perfgate_ci`(staging 전용) — 이 계정과 혼용 금지.
- staging QA 계정 `qa_claude`(id 57, staging 전용)는 기존 용도 유지.
