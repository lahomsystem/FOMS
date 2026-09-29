# 야간 정리(FOMS-cron) 단일 러너 — `&&` 사슬이 첫 명령만 도는 문제

- 작성 2026-09-29 · 상태: **설계, 승인 대기** · 원인 기록: `docs/plans/2026-09-28-foms-language-migration-assessment-ledger.md` §7 끝

## 1. 문제

`railway-cron.toml` 과 대시보드의 startCommand 는 세 명령을 `&&` 로 잇는다.

```
python tools/cron/cleanup_order_drafts.py --execute && python tools/ops/purge_order_mutation_receipts.py ... --apply && python tools/ops/purge_audit_logs.py --apply
```

실제로는 **첫 명령만 돈다.**
- FOMS-cron 은 설정(RAILPACK, toml `nixpacks`)과 달리 실제 배포 builder 가 **DOCKERFILE** 이다(루트 `/Dockerfile` 자동 감지, `deployment.meta.serviceManifest.build.builder`). Railway 는 Dockerfile 빌드의 start command 를 셸 없이 exec 한다(https://docs.railway.com/guides/start-command, 확인 2026-09-29).
- 스테이징·운영 모두 매일 밤 로그에 cleanup 한 줄만 있다. purge 두 도구는 성공·건너뜀·실패 어느 경우에도 한 줄을 남기는데 0줄이다 → 시작도 안 했다.
- 영향: 운영 `order_mutation_receipts` 중 7일 넘게 만료된 행 **2952/4359**(가장 오래된 만료 2026-09-07), 스테이징 368/399. 감사 로그 4표는 보존 기간 초과 행 0 이라 아직 영향 없음.
- 기존 계약 `tests/contracts/runtime/test_cron_purge_wiring.py` 는 startCommand **문자열**에 purge 가 있는지만 봐서 green 이었다.

## 2. 결정

**셸 문법 없이 파이썬 러너 하나를 실행한다.**

- 새 `tools/cron/nightly.py`: 정해진 단계 3개를 차례로 `subprocess.run([sys.executable, <스크립트>, *인자], cwd=저장소 루트)` 로 부른다. 각 단계의 CLI·로그는 지금과 똑같다(도구 코드 무변경).
- **단계는 서로 독립**: 앞 단계가 실패해도 다음 단계를 돈다(지금의 `&&` 는 cleanup 이 실패하면 purge 를 막는다 — 서로 무관한 청소라 막을 이유가 없다). 끝에 `[nightly] step=<이름> rc=<코드> elapsed=<초>` 요약을 남기고, 하나라도 실패하면 exit 1.
- 단계마다 제한 시간 20분. Railway 는 앞 실행이 안 끝나면 다음 실행을 건너뛰므로(https://docs.railway.com/reference/cron-jobs) 한 단계가 멈추면 다음 날 밤부터 전부 멈춘다.
- startCommand = `python tools/cron/nightly.py` (toml·`tools/ops/railway_configure_cron_service.py` `CRON_START_COMMAND` 동시 변경).

대안과 버린 이유:
- `sh -c "A && B && C"` 로 감싸기: 한 줄 수정이지만 셸 인용이 대시보드·toml·상수 세 곳에서 글자까지 같아야 하고, 단계 독립·요약 로그·제한 시간이 없다.
- builder 를 Railpack 으로 강제: 루트 Dockerfile 이 있는 한 다른 서비스(web)와 빌드 방식이 갈라지고, 빌드 방식이 바뀌면 다시 조용히 깨진다.

## 3. 계약(테스트)

- `test_cron_purge_wiring.py` 개정: startCommand 는 `python tools/cron/nightly.py` 이고, `nightly.py` 의 단계 목록에 cleanup·purge 두 개가 모두 있으며, 각 스크립트 파일이 존재한다. toml·상수 일치 검사는 유지.
- **모든 `railway*.toml` 의 startCommand 에 셸 연산자(`&&` `||` `;` `|` `>` `<` `$`) 금지** — 이번 결함이 다시 들어오는 길을 막는다. (web·worker 는 `sh start.sh` 라 해당 없음.)
- 러너 동작: 첫 단계가 실패해도 나머지가 불리고 exit 1, 모두 성공이면 exit 0, 요약 줄이 단계마다 한 줄(subprocess 를 가짜로 바꿔 검사).

## 4. 배포·확인

1. deploy 푸시 → CI green.
2. 스테이징 대시보드 startCommand 갱신: `python tools/ops/railway_configure_cron_service.py --target staging`(먼저 `--dry-run`). 이 도구는 대시보드 필드를 쓰고 재배포한다.
3. 다음 02:00 KST 실행 뒤 스테이징 로그에 세 단계 줄 + `[nightly]` 요약, DB 에서 7일 넘게 만료된 receipt 0(읽기 전용 확인).
4. 사용자 요청 시 운영 승격 + `--target production`. 첫 실행에서 운영 receipt 약 2952행이 1000행 단위로 지워진다(재실행 막는 기록이라 7일 지난 행은 삭제 대상이 맞다 — `purge_order_mutation_receipts.py` 머리말).

## 5. 범위 밖

- FOMS-cron 이외 서비스의 builder 정리.
- `cleanup_order_drafts.py:88` 의 `datetime.utcnow()` 경고.
