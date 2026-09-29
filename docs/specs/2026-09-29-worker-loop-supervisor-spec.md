# WORKER 배경 루프 감독 통일 — 설계서

- 작성 2026-09-29 · 기준 `origin/deploy` · 상태: **승인 대기**
- 근거: 언어 이전 분석 보고서 ⑧ 권고 2(`docs/plans/2026-09-28-foms-language-migration-assessment-report.md`), 사고 `docs/incidents/2026-09-10-settle-loop-dies-after-success-tick.md`.
- 종류: 배포·런타임 코어 변경 → 이 설계서 승인 뒤 구현.

## 0. 쉬운 요약

WORKER 서비스에는 뒤에서 계속 도는 작업이 6개 있다. 그중 **주문 큐 처리(RQ) 하나만** "죽으면 다시 살리는 지킴이" 아래에 있고, 나머지 5개(알림 재촉·네이버 주문 동기화·네이버 자동 발송·네이버 정산 동기화·주소 좌표 채우기)는 한 번 켜고 끝이다. 하나가 죽으면 **다음 배포까지 조용히 멈춘다** — 2026-09-10 정산 동기화가 매일 05:31 에 죽고 배포 때만 살아난 사고가 그것이다. 이 설계는 6개를 모두 같은 지킴이 아래로 옮긴다.

## 1. 지금 모습 (확인한 사실)

| 항목 | 사실 | 출처 |
|---|---|---|
| 빌드 | 네 서비스 모두 루트 `Dockerfile`(`python:3.12-slim`)로 빌드된다. toml 의 `builder = "nixpacks"` 는 실제로 쓰이지 않는다 | 운영·스테이징 `railway deployment list --json` 의 `meta.serviceManifest.build.builder = DOCKERFILE`(2026-09-29) |
| 시작 명령 | WORKER = `sh start.sh`(`USE_RQ_WORKER=1`). `sh` 는 dash → bash 전용 문법(`wait -n`, 배열) 불가 | 같은 manifest, `Dockerfile:47` |
| 감독되는 것 | RQ 소비자 1개: `while true` + 백오프 5→60초 + TERM 전달 | `start.sh:88-125`, 계약 `tests/contracts/runtime/test_worker_supervisor_contract.py` |
| 감독 안 되는 것 | `--loop` 5개가 `&` 로 한 번 켜짐. PID 보관·재시작·TERM 전달 없음 | `start.sh:23-26, 34-37, 45-49, 56-60, 70-73` |
| 러너 안의 약점 | 하트비트 메타데이터 조립이 `try` 밖인 곳이 남아 있음(escalation·order_sync·geocode). 러너 4개는 모듈 맨 위에서 `from app import app` — 부팅 실패면 영구 사망 | 사고 문서 `:110-111`, 각 `scripts/maintenance/run_*.py` |
| 감시 | 하트비트 표 `side_effect_worker_heartbeats` + SIDEFX 안의 정지 감시(watchdog). 감시는 2026-09-09 오탐 뒤 `FOMS_WORKER_WATCHDOG_ENABLED=0` 로 꺼져 있음 | `foms/services/worker_watchdog.py:44-68`, 사고 `2026-09-09` |
| 시험 | `start.sh` 를 **실행**하는 시험은 없다(문자열 검사만). 러너 줄이 `&` 로 끝나는지 검사하는 시험 여럿 | `test_naver_settle_sync.py:806-825` 등 |

## 2. 목표와 범위

- 목표: WORKER 의 배경 작업 6개가 **어떤 이유로 끝나든** 백오프 뒤 다시 켜진다. 컨테이너 종료 신호(TERM)는 6개 모두에 전달되고, 정해진 시간 안에 정리된다. 재시작은 로그 한 줄로 남는다.
- 범위 밖: SIDEFX(자기 루프 1개, 별도 서비스), web(gunicorn), cron. 러너 내부 로직 변경은 3절 선택 C 로 따로 묻는다.

## 3. 설계 선택 (결정 필요)

### 선택 A — 파이썬 지킴이 1개가 모두 관리 (권장)
- 새 `tools/ops/worker_supervisor.py`: 켤 작업 목록을 **코드 한 곳**(이름·명령·켜짐 조건 env)에 선언하고, 각각 `subprocess.Popen` 으로 켠다. 끝나면 작업별로 백오프(5초에서 두 배씩, 최대 60초, 60초 이상 살았으면 5초로 되돌림 — 지금 RQ 규칙과 같음) 뒤 다시 켠다.
- `start.sh` WORKER 가지: `wait_for_redis` 뒤 `exec python tools/ops/worker_supervisor.py` — 지킴이가 PID 1 이 된다. RQ 소비자도 이 목록의 한 줄이 된다(`start.sh` 의 셸 감독 루프는 지운다).
- TERM/INT: 모든 자식에 TERM → 최대 20초 기다림 → 남은 자식 KILL → exit 0. 자식 종료는 `wait` 로 거두므로 좀비가 남지 않는다.
- 로그: `[supervisor] start name=... pid=...` · `[supervisor] exit name=... rc=... ran=...s restart_in=...s`.
- 장점: dash 제약이 없다. **윈도우 pre-push 에서도 실제로 실행하는 시험**을 쓸 수 있다(가짜 자식으로 재시작·백오프·신호 전달 단언). 작업 목록이 한 곳이라 문자열 검사 시험 여러 개가 목록 검사 하나로 준다.
- 단점: 2026-09-08 사고로 굳힌 셸 RQ 감독을 파이썬으로 옮기는 만큼 바뀌는 면이 넓다 → 계약 시험을 같은 의미로 옮겨 적는다(RQ 가 깨끗하게 끝나도 다시 켠다, Redis 대기 뒤 켠다).

### 선택 B — `start.sh` 안에 셸 함수로 감독
- `_supervise NAME CMD...` 를 dash 호환으로 만들어 작업마다 `( while true; do CMD & wait; backoff; done ) &` 로 켜고, 부모가 서브셸 PID 들에 TERM 을 전달.
- 장점: 바뀌는 파일이 `start.sh` 하나. 단점: dash 의 서브셸·trap 조합은 신호 전달이 까다롭고, 실행 시험을 윈도우에서 돌릴 수 없다(리눅스 CI 에서만).

### 선택 C — 러너 안의 약점도 같이 고칠지
- 지킴이가 생기면 "하트비트 조립이 try 밖" 결함은 **죽지 않고 재시작**으로 바뀐다. 매일 한 번 재시작 로그가 남는 소음이 되므로, 같은 변경에서 escalation·order_sync·geocode 의 조립을 가드 안으로 옮기는 것을 권장(각 러너 5줄 안팎, 정산 러너의 `_safe_heartbeat_metadata` 방식).

## 4. 시험

- 새 `tests/contracts/runtime/test_worker_supervisor_process.py`(선택 A): 가짜 자식(`python -c "import sys; sys.exit(1)"`, 오래 자는 자식)으로 ① 끝나면 다시 켠다 ② 백오프가 5→10→…→60, 오래 살면 되돌림 ③ TERM 을 모든 자식에 전달하고 기한 안에 끝남 ④ 켜짐 조건 env 가 꺼진 작업은 켜지 않음. 시계·잠은 주입해서 빠르게.
- 기존 문자열 계약(`test_worker_supervisor_contract.py`, 러너별 `&` 줄 검사, `test_loop_heartbeat_wiring.py` 의 `--loop` 5개 이상 규칙)은 **같은 뜻을 지킴이 목록에 대해** 검사하도록 옮긴다. 옮기면서 뜻이 약해지지 않았는지 음성 대조를 둔다.
- `Dockerfile:47` `CMD ["sh","start.sh"]` 는 그대로(`test_dockerfile_deploy_contract.py`).

## 5. 배포·확인

1. deploy → 스테이징 WORKER 로그에 `[supervisor] start` 6줄(켜짐 조건이 켜진 것만), 하트비트 9종 신선.
2. 스테이징에서 한 번 **일부러 죽여 보기**: 작업 하나의 간격 env 를 잘못된 값으로 바꿔 즉시 끝나게 한 뒤 `restart_in` 로그와 백오프를 확인하고 되돌린다(스테이징만).
3. 재배포 때 TERM 처리: 이전 컨테이너 로그에 모든 자식 정리 줄, 큐 잡 유실 없음(RQ 는 지금처럼 TERM 에 현재 잡을 마치고 끝냄).
4. 운영 승격은 사용자 요청 때. 승격 뒤 정지 감시(`FOMS_WORKER_WATCHDOG_ENABLED=1`) 재가동을 별도로 묻는다.

## 6. 되돌리기

`start.sh` WORKER 가지를 이전 커밋으로 되돌리면 끝(빌드 변경 없음, DB 변경 없음).

## 7. 부수 정리 (같은 변경에서, 동작 무관)

- toml 세 개의 `builder = "nixpacks"` 는 실제 빌드(Dockerfile)와 달라 오해를 부른다 → 지우거나 "실제는 Dockerfile" 주석(시험 영향 확인 후).
- `start.sh` 를 설명하는 낡은 docstring 4곳(`foms/services/loop_heartbeat.py:3-5` 등, "exec rq worker")을 새 구조로.

## 8. 사용자가 정할 것

1. 선택 A(파이썬 지킴이, 권장) / 선택 B(셸 함수).
2. 선택 C(러너 약점 같이 고치기) 포함 여부 — 권장: 포함.
3. 스테이징 "일부러 죽여 보기" 실험 허용 여부.
