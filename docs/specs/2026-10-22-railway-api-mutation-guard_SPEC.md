# Railway API 변경 요청도 허락을 묻게 — 안전 장치 보강 SPEC (2026-10-22)

상태: **R1·R2 구현 완료(2026-10-22, 사용자 승인 "스크립트 파일까지")**. R3 문구는 AGENTS.md «프로젝트 기본 정보» 절에 넣었다(2026-10-22 사용자 승인).
구현 확인: 저장소에서 Railway API 주소가 든 파일 5개 중 새로 ask 가 되는 것은 `railway_configure_cron_service.py`·`railway_pitr.py`
두 개뿐(나머지 `check_deploy_drift.py`·`prod_route_latency_compare.py`·`guard_policy.py` 는 allow). 새 ask 사례 9개는 옛 가드에서
전부 allow 였다(대조군).

## 목적
에이전트가 Railway 운영 설정(공개 주소·환경변수·배포·서비스)을 바꾸려 할 때 어떤 길로 가든 사용자 허락을 거치게 한다.
사용자 조건(2026-10-22): **"바깥 문을 닫아 비공개로 해도, 에이전트가 내 허락을 받고 수정할 수 있어야 한다."**
닫는 것과 필요할 때 허락받고 여는 것이 둘 다 되게 하고, 허락 없이 바뀌는 길을 줄인다.

## 배경 (2026-10-22 사실)
- Railway 공식 공지(10-21): 고객 환경변수 일부가 복호화된 채 유출. PostgreSQL 안내문은 "Public Access 가 켜져 있으면 샌
  비밀번호를 인터넷 어디서나 쓸 수 있다 — 바깥에서 안 쓰면 지금 끄라"고 한다. 배포는 전 요금제 정지 중.
- 같은 날 사용자 승인으로 운영 Redis 바깥 문(TCP 프록시 `centerbeam.proxy.rlwy.net:32661`)을 Railway 공개 GraphQL 의
  `tcpProxyDelete` 로 닫았다. 이 호출은 python 스크립트로 보냈고 **안전 장치는 아무것도 묻지 않았다.** 승인은 대화에서 받았지만,
  가드로는 잡히지 않는 길이 있다는 뜻이다.
- 공개 GraphQL 에는 `tcpProxies`(조회)·`tcpProxyDelete`(삭제)만 있고 **TCP 프록시를 만드는 mutation 이 없다**(introspection
  확인). Railway CLI 4.27.5 에도 만드는 명령이 없다. 다시 여는 것은 대시보드(사람 손)뿐이다.

## 지금 구조
줄 번호는 origin/deploy `5f07a35d2` 기준.
- `tools/harness/guard_policy.py:669-672` `_RAILWAY_MUTATING` — `railway up·deploy·redeploy·restart·down·delete·remove·ssh·run·shell·connect·add·scale·volume·domain` 은 ask.
- `:677-681` `_RAILWAY_SUB_MUTATING` — `railway variables --set/set/delete`, `environment new/delete` 는 ask. `:684-701` `_classify_railway`.
- `:930-932` 명령 글자에 `.proxy.rlwy.net` 이 있으면 ask(공개 DB/Redis 직접 접속).
- `:116-` `_strip_heredoc_bodies` — 셸이 아닌 소비자(`python - <<'PY'` 등)에 먹이는 heredoc 본문은 데이터로 보고 판정 전에 지운다
  (2026-09-09 오탐 수정 H-13·H-16). `:969` 에서 판정 전에 적용된다.
- 스크립트 파일(`python x.py`) 안쪽은 읽지 않는다.

**빈 곳**
1. `https://backboard.railway.com/graphql/v2` 로 직접 보내는 `mutation` — `curl`·`python -c` 인자, python heredoc 본문, 스크립트 파일.
2. 저장소 안 도구 중 같은 엔드포인트에 mutation 을 보내는 것: `tools/ops/railway_configure_cron_service.py`(serviceConnect·
   serviceInstanceUpdate·serviceInstanceDeployV2), `tools/ops/railway_pitr.py`(복원 fork·서비스 삭제). 지금은 묻지 않고 돈다.

## 설계

### R1 — 명령 글자에 Railway API 와 mutation 연산이 함께 있으면 ask
- 검사 대상: **heredoc 본문을 지우기 전** 원문. 단, 세그먼트 첫 명령(또는 heredoc 소비자)이 네트워크·실행기일 때만 —
  `curl`·`wget`·`python`·`python3`·`py`·`node`·`powershell`/`pwsh` 의 `Invoke-RestMethod`·`Invoke-WebRequest`(`irm`·`iwr`).
  `grep`·`echo`·`cat` 같은 내용-안전 명령은 지금처럼 allow(문서 검색 오탐 방지).
- heredoc 소비자로 보는 모양: `python - <<'PY'`, `python <<PY`(대시 없음), 그리고 **파이프로 실행기에 먹이는 경우**
  (`cat <<'EOF' | python -`). 파이프는 세그먼트가 갈려 앞쪽 `cat` 이 내용-안전으로 통과하므로, 파이프 다음 세그먼트가 python·node 이면
  앞 세그먼트의 heredoc 본문도 검사한다.
- 조건: `backboard.railway.com` 또는 `backboard.railway.app` 가 있고, **GraphQL 연산 모양의 mutation** 이 있다 —
  `\bmutation\s*(?:[A-Za-z_]\w*\s*)?[({]`(대소문자 무시; `mutation{`·`mutation Name(`·`mutation (` 가 걸린다).
  설명문의 "mutation 은 …", 정규식 리터럴 `r"\bmutation\b"` 은 걸리지 않는다(2026-10-22 표본 7개로 확인).
- 결과: ask, 사유 `Railway API 변경 요청(mutation)`.
- `query` 만 있는 호출은 allow — 상태 확인·`foms-ops-backup` 의 topology·variables 스냅샷·`check_deploy_drift.py` 가 막히지 않게.

### R2 — 실행하는 스크립트 파일 안에 같은 조합이 있으면 ask
- 판정 위치: 기존 `_reduce_wrappers`(`guard_policy.py:827`, env·timeout·nohup) **다음** — 래퍼를 벗긴 뒤의 실행기를 본다.
  `uv run`·`pipenv run`·`poetry run` 래퍼도 같은 단계에서 벗긴다.
- 실행기가 `python`·`python3`·`py`·`node` 이면 옵션을 건너뛰고(`-u`·`-B`·`-O`, 값을 받는 `-X`·`-W`, `py` 런처의 `-3`·`-3.12` 등)
  첫 비옵션 인자를 스크립트로 본다. `-m <모듈>` 은 저장소 기준 경로(`tools.ops.railway_pitr` → `tools/ops/railway_pitr.py`)로 풀어 읽는다.
- 그 파일(`.py`·`.js`·`.mjs`, 최대 256KB)에 R1 조건이 있으면 ask. 파일이 없거나 못 읽으면 판정을 바꾸지 않는다.
- 결과: `railway_configure_cron_service.py`·`railway_pitr.py` 가 ask 가 된다(의도된 두 도구).
  읽기 전용 `tools/perf/prod_route_latency_compare.py`(설명문·거부 정규식에만 `mutation` 단어, 19·85·350-352행)는 R1 조건을 좁혀 allow 로 남는다.
- 알려진 한계: `import` 로 끌어온 다른 모듈 안의 mutation 은 보지 않는다.

### R3 — 정해진 길 (AGENTS.md Railway 절에 추가)
바깥 문을 닫은 뒤 운영 DB·Redis 에 손댈 때:
1. 점검은 `railway ssh -s <서비스>` 로 컨테이너 안에서 내부망(`*.railway.internal`)으로 — 이미 ask.
2. 바깥 문이 꼭 필요하면: 사용자가 대시보드 Settings › Networking 에서 TCP 프록시를 만든다 → 에이전트가 작업한다
   (`.proxy.rlwy.net` 명령은 ask) → 끝나면 `tcpProxyDelete` 로 지운다(R1/R2 로 ask). 주소가 매번 바뀌어 옛 주소 유출이 무력화된다.
3. 운영 변경 전 승인은 **대화에서** 받는다(AskUserQuestion). 가드는 안전띠이지 승인 절차가 아니다.

## 테스트 (`tests/harness/test_guard_policy.py` 표 확장)
| 기대 | 명령 |
|---|---|
| ask | `curl -s https://backboard.railway.com/graphql/v2 -d '{"query":"mutation{tcpProxyDelete(id:\"x\")}"}'` |
| ask | `python - <<'PY'` 본문에 `backboard.railway.com` 과 `mutation{variableUpsert(...)}` |
| ask | `python <tmp>/s.py` — 파일에 엔드포인트와 `mutation` (tmp_path) |
| ask | `python tools/ops/railway_pitr.py --list` (R2, 의도된 ask) |
| ask | `python -m tools.ops.railway_pitr --list` (`-m` 모듈 풀기) |
| ask | `python -u <tmp>/s.py` · `py -3 <tmp>/s.py` (옵션 건너뛰기) |
| ask | `python <<PY` 본문에 엔드포인트와 `mutation{…}` (대시 없는 heredoc) |
| ask | `cat <<'EOF' \| python -` 본문에 엔드포인트와 `mutation{…}` (파이프 소비자) |
| allow | `curl ... backboard.railway.com ... '{"query":"query{me{id}}"}'` |
| allow | `python <tmp>/q.py` — 파일에 엔드포인트와 `query` 만 |
| allow | `python tools/perf/prod_route_latency_compare.py --help` — 읽기 전용, 설명문에만 `mutation` (회귀 대조군) |
| allow | `python tools/ops/check_deploy_drift.py` — push 마다 훅이 권하는 도구, `mutation` 0(기존 493-495행 단언) |
| allow | `grep -rn "mutation" docs/` · `grep proxy.rlwy.net notes.md`(기존 70·80행 유지) |

## 하지 않는 것 · 남는 위험
- 마음먹은 우회(문자열 쪼개기, 다른 언어, import 한 모듈)는 못 막는다. 승인 원칙은 대화가 담당한다.
- Railway 는 읽기 전용 토큰을 주지 않는다 — 토큰 권한으로 막는 길은 없다(2026-10-22 기준, 확인 필요).
- 엔드포인트 이름이 바뀌면(`backboard.railway.app` → `.com` 이 이미 한 번 바뀜) 규칙도 고친다.
- `foms-ops-backup` 저장소 스크립트는 그 저장소에서 돌릴 때 이 가드 밖이다. FOMS 창에서 돌리면 대상이다.

## 결정이 필요한 것
1. R2(스크립트 파일 읽기)까지 할지. R1 조건을 연산 모양으로 좁히면 R2 로 새로 ask 가 되는 것은 의도한 두 도구
   (`railway_configure_cron_service.py`·`railway_pitr.py`)뿐이라 **하는 쪽을 권한다.**
2. R3 문구를 AGENTS.md 에 넣을지(하네스 문서 변경).

## 검토
- 2026-10-22 보안 점검 세션(foms-3c, 기존 `_classify_railway` 규칙 작성자) 검토 반영: 연산 모양 조건(오탐 실례
  `prod_route_latency_compare.py`), allow 대조군 2개, `-m`·옵션·래퍼, 대시 없는 heredoc·파이프 소비자.
