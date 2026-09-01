# 실서버 측정·테스트 계정 (claude_master) — 정책 정본

> 2026-08-04 신설·개정 (사용자 지시). AI 세션의 staging·production 실서버 측정/QA 전용.
> 전 에이전트(Claude Code·Cursor 등) 공통 구속. AGENTS.md·CLAUDE.md에서 이 문서를 가리킨다.

## 계정

| 항목 | staging | production |
|---|---|---|
| username | `claude_master` | `claude_master` |
| base | lahom-dev.up.railway.app | lahom-production.up.railway.app |
| users.id | 58 | 57 |
| role | ADMIN | ADMIN |
| 기본 상태 | **활성** | **잠금 (`is_active=false`)** |

**비밀번호는 이 저장소에 없다. 환경별로 서로 다르다.** 로컬 전용 파일:
`C:\Users\USER\.claude\projects\c--DEV-FOMS\secrets\claude_master.json`
(환경별 password·base URL·잠금 기본값 포함. 저장소 커밋 절대 금지. 유출 의심 시 로테이션 절차로 즉시 교체.)

## 사용 정책 (절대 규칙)

1. **기본 테스트는 staging.** staging에서는 모든 활동 허용 (쓰기·시드·삭제·부하 측정 포함).
   단 staging은 perf-gate 관측 대상 — 대량 시드/데이터 변형 후엔 원상 정리(예산 관측 오염 방지).
2. **production은 사용자 명시 요청 시에만, 요청 1건 = 그 작업 1회 한정.** 이전 승인은 다음 작업으로 이월되지 않는다.
   절차: 잠금 해제(아래 §잠금/해제) → 측정 → **종료 시 재잠금**.
   허용 범위: TTFB/HTTP 측정, F12 devtools(콘솔·네트워크 로그), 페이지 열람 등 관측 전반.
3. **production 부하 상한**: 직렬·저빈도 요청만. 스트레스/동시 부하 테스트(멀티 세션·고빈도 반복)는 staging 전용.
4. **production 실데이터 불가침**: 기존 행(주문·사용자·설정·첨부 등) 변경·삭제 일절 금지. 신규 생성은 아래 가상 주문만.
   DB 직결은 읽기전용(`set_session(readonly=True)`) — 유일한 쓰기 예외는 `users` 테이블 `claude_master` 행의 `is_active`/`password` 갱신.
5. **가상 주문 규칙** (production 쓰기 검증이 필요할 때만):
   - 고객명 `CLAUDE-TEST-` 접두어 필수
   - **실존 연락처 절대 금지** — 전화번호는 더미(`010-0000-0000`) 고정. 알림톡/채널톡 등 실발송 경로 차단이 목적. 발송 트리거가 걸리는 테스트면 사전에 발송 경로 무해 확인.
   - **DRAFT 상태 우선** — `Order.active_filter()`가 대시보드에서 숨겨 직원 노출·KPI 오염 방지
   - 워크플로 단계 전이 테스트(알림 fan-out 유발)는 staging에서. production 전이가 불가피하면 사전에 fan-out 영향 확인.
6. **정리 규칙**: 본인 생성분만, 앱 경로(soft delete)로 정리. 테스트 중 R2 업로드 파일도 정리 대상.
   `access_logs`·`order_events` 등 append-only 감사 흔적은 **허용 잔여물** — 지우려는 시도 자체가 변조라 금지.
   종료 시 브라우저 세션 로그아웃(ADMIN 쿠키 잔존 방지) + production 계정 재잠금.
7. **실사용자 계정 차용 금지**: upperkill 등 실계정으로 측정/테스트 금지. 실서버 테스트는 이 계정만 쓴다.

## production 잠금/해제

scratchpad 하위 별도 디렉토리에서 `railway link -p FOMS-PRODUCTION` → `railway variables --service Postgres --json`의 `DATABASE_PUBLIC_URL`로:

```sql
-- 해제 (사용자 요청 받은 그 작업에서만)
UPDATE users SET is_active = true  WHERE username = 'claude_master';
-- 재잠금 (작업 종료 시 필수)
UPDATE users SET is_active = false WHERE username = 'claude_master';
```

잠금 상태 로그인 시도는 302가 아닌 200(비활성 flash) — 잠금 검증 오라클로 쓴다.

### 해제는 `is_active`만 바꾼다 (2026-09-01 신설 — 사고 기록)

**해제 스크립트에서 비밀번호를 건드리지 마라.** 2026-08-31 21:58 한 세션의 해제 스크립트가
`unlock()` 안에서 `set_strong_password()`를 함께 불러 **잠금 해제가 비밀번호를 조용히 교체**했다
(함수명·docstring은 잠금 해제만 표방했다). 다음 세션은 secrets 파일 값으로 로그인하지 못했고
(`security_logs`의 `LOGIN_FAIL`, user 57), 원인을 찾느라 측정이 한 차례 실패했다.
2026-09-01 08:37 정식 로테이션으로 secrets 파일과 다시 맞췄다.

- 해제/재잠금이 만지는 컬럼은 **`is_active` 하나뿐**이다. `approval_status`·`password`를
  같이 바꾸는 해제 스크립트는 그 자체로 결함이다.
- 비밀번호 교체가 필요하면 **아래 §로테이션 절차를 따로** 밟는다.
- **로테이션했으면 그 작업 원장에 남긴다**: 시각·환경(staging/production)·secrets 파일 동기화 여부.
  **값은 절대 기록하지 않는다.** 기록이 없으면 다음 세션이 "왜 로그인이 안 되지"부터 다시 시작한다.
- 측정 스크립트에 비밀번호를 **하드코딩하지 마라** — secrets 파일에서 읽는다. 임시 스크립트에
  평문으로 박아두면 로테이션 후에도 파일과 세션 기록에 남는다(실제로 남았다).

## 측정 레시피

- 로그인: `POST /login` form(username/password), CSRF 불요, 성공=302.
- **desktop UA 필수** (모바일 UA는 v2/v3 셸 리다이렉트로 측정 오염).
- 쓰기 API는 페이지 HTML `<meta name="csrf-token">` 추출 후 `X-CSRFToken` 헤더.
- TTFB 대표값은 warm 표본 **min** (tail 오염 면역 — tools/perf/staging_perf_gate.py 방법론).

## 비밀번호 로테이션 (환경별 독립)

1. 새 비번 생성 + `werkzeug.security.generate_password_hash`.
2. 해당 환경 railway 링크(위 §잠금/해제와 동일 경로, 링크는 디렉토리별 — 저장소 디렉토리 링크 오염 금지).
3. `UPDATE users SET password=<hash>, password_policy_version=1 WHERE username='claude_master'`.
4. 로컬 secrets 파일의 해당 환경 password만 갱신 → HTTP 302 오라클 검증(production은 해제 상태에서 검증 후 재잠금).

## 관련

- CI perf-gate는 별도 계정 `perfgate_ci`(staging 전용) — 이 계정과 혼용 금지.
- staging QA 계정 `qa_claude`(staging id 57)는 기존 용도 유지.
