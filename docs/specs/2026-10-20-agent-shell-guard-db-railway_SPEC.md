# AI 도구 셸 가드 — DB 쓰기·Railway 변경은 사용자 확인 — SPEC (2026-10-20)

## 목적
사용자 결정(2026-10-20): "AI 도구는 사용자가 지시한 것만 DB 수정 등". 지금 Claude Code 셸 가드(`.claude/hooks/guard_shell.py` → `tools/harness/guard_policy.py`)는 git push·강제 삭제·DB 파괴 구문(drop·truncate·조건 없는 delete)만 본다. 그래서 다음이 확인 없이 지나간다.
- `railway redeploy`·`railway variables --set`·`railway ssh`·`railway run`·`railway connect` 처럼 배포·환경변수를 바꾸거나 운영 안으로 들어가는 명령.
- Railway 공개 DB 주소(`*.proxy.rlwy.net`)로 직접 붙는 명령.
- `psql -c "UPDATE ..."`·`python -c "...INSERT INTO..."` 같은 조건 있는 DB 쓰기 SQL.
- 가드 자체가 예외로 죽으면 그대로 통과(fail-open).

## 지금 구조
- `classify_command` 가 명령을 세그먼트로 나눠 각각 판정하고 가장 높은 위험(allow < ask < deny)을 고른다. 래퍼(`env`·`timeout`·`bash -c` 등)는 벗겨 안쪽을 본다. `echo`·`grep` 같은 내용-안전 명령은 인자를 데이터로 보고 통과.
- DB 판정 `_classify_db_sql` 은 첫 토큰이 SQL 동사이거나 DB 클라이언트(`psql` 등)일 때만 돈다.
- `guard_shell.main` 은 예외를 `hook_log` 에 남기고 통과시킨다.
- 세션 시작 훅(`.claude/hooks/session_start.py`)은 배포 drift 를 보려고 `tools/ops/check_deploy_drift.py` 를 부른다 — 개발 PC 의 Railway 계정 토큰으로 GraphQL **조회**만 한다(2026-09-22 사고 뒤 결정, 운영 접속 정보를 GitHub 에 두지 않으려고 로컬에서 본다).

## 변경
1. `guard_policy.py` 에 ask 규칙 3개(차단이 아니라 사용자 확인):
   - **Railway 변경 명령**: `railway` 의 하위 명령이 `up`·`deploy`·`redeploy`·`restart`·`down`·`delete`·`remove`·`ssh`·`run`·`shell`·`connect`·`add`·`scale`·`volume`·`domain` 이거나, `variables`/`variable` 에 `--set`·`set`·`delete`, `environment` 에 `new`·`delete` 가 붙으면 ask. `status`·`logs`·`link`·`variables`(조회)·`whoami`·`list` 는 그대로 통과.
   - **공개 DB 주소**: 세그먼트에 `.proxy.rlwy.net` 이 있으면 ask(운영·스테이징 공개 DB/Redis 프록시).
   - **DB 쓰기 SQL**: DB 클라이언트 세그먼트 또는 `python -c` 세그먼트에 `UPDATE … SET`·`INSERT INTO`·`DELETE FROM … WHERE`·`ALTER TABLE`·`CREATE TABLE/INDEX/DATABASE`·`GRANT`·`REVOKE` 가 있으면 ask. 기존 deny(drop·truncate·조건 없는 delete)는 그대로.
2. `guard_shell.py`: 판정 중 예외가 나면 통과 대신 **ask**("가드 오류 — 확인 필요")를 낸다. 기록(`hook_log`)은 그대로.
3. 세션 시작 drift 확인: 동작은 유지하고, `check_deploy_drift.py` 가 GraphQL `mutation` 을 보내지 않는다는 것을 테스트로 고정한다(조회 전용 범위).

## 건드리지 않는 것
- heredoc 본문으로 쓴 스크립트 파일 안쪽(가드는 heredoc 본문을 데이터로 본다) — 파일을 실행하는 순간의 명령만 본다.
- MCP postgres(로컬 DB, `.mcp.json`) — 로컬 개발 DB 라 대상 밖.
- 사용자 범위 설정·플러그인 훅(저장소 밖).

## 테스트
`tests/harness/test_guard_policy.py` 판정 표에 사례 추가:
- ask: `railway redeploy -s web`·`railway variables --set A=1`·`railway variable set A=1`·`railway ssh`·`railway run python x.py`·`railway connect Postgres`·`psql "postgresql://u@x.proxy.rlwy.net:1/db"`·`psql -c "UPDATE users SET is_active = true WHERE id = 1"`·`python -c "...INSERT INTO t VALUES (1)..."`·`timeout 5 railway up`.
- allow(음성 대조군): `railway status`·`railway logs -s web -n 50`·`railway variables --service Postgres --kv`·`railway link --project FOMS-DEV`·`psql -c "SELECT 1"`·`grep proxy.rlwy.net notes.md`.
- 가드 예외 → ask 출력.
- `check_deploy_drift.py` 에 `mutation` 0.
