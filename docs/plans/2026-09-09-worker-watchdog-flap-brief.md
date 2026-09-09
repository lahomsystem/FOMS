# 워커 정지 감시 헛알림(15분 주기 반복) — 워크플로 브리프

작성 2026-09-09. worktree `C:\tmp\foms-s-wdflap`, 브랜치 `session/wdflap`(base `origin/deploy`).

## 현상 (사용자 실측, 운영 알림 센터)

`백그라운드 작업이 멈췄습니다` → 15분 뒤 `다시 돌고 있습니다` → 15분 뒤 다시 멎음… 이
왕복이 2026-09-08 17:18~22:30 사이 최소 10회 반복됐다. 본문은 매번
`NAVER_ORDER_SYNC(15분째)` 또는 `(16분째)`. 다른 kind 는 한 번도 안 나왔다.
알림 센터가 이 두 문장으로 덮여 네이버 취소·반품 긴급 알림이 밀렸다.

## 근본 원인 (코드 실측 — 이미 확정)

같은 사실(하트비트 나이)을 두 판정부가 **다른 예산**으로 읽는다.

| 판정부 | 위치 | 예산 |
|---|---|---|
| readiness 게이트 | `foms/services/sidefx_worker.py:626-641` `ReadinessThresholds.heartbeat_age_limit` | `max(등록부값, 신고간격 x 3)` — 루프가 신고한 tick 간격을 쓴다 |
| 정지 감시자 | `foms/services/worker_watchdog.py:94` | `WORKER_KIND_SPECS[kind].max_heartbeat_age` **고정** |

- `NAVER_ORDER_SYNC` 등록부값 = 900초(`sidefx_worker.py:92-94`, 주석은 "기본 간격 300초 x 3틱").
- 운영 루프 실제 간격은 **1800초** — `start.sh:35-36` 이 `FOMS_NAVER_SYNC_INTERVAL_SECONDS`
  로 넘기고, 루프는 그 값을 하트비트 metadata `interval_seconds` 로 신고한다
  (`scripts/maintenance/run_naver_order_sync.py:86-121`).
- 그래서 매 tick 마다: t+900 에 감시자가 "멎었다" → t+1800 에 하트비트 → "복구".
  15분 주기 왕복은 이 산수의 결과다. 워커는 처음부터 멀쩡했다.
- 운영 readiness 실측(원장 T25)은 같은 시각 `NAVER_ORDER_SYNC 나이 715초 / 신고 1800 /
  예산 5400 → OK`. 두 판정부가 같은 표를 보고 반대로 말했다.

## 계약 (이름 고정 — 워커는 이 이름 그대로 쓴다)

- `sidefx_worker.py` 에 공용 함수 `effective_heartbeat_budget(kind: str,
  declared_interval: Optional[int]) -> int` 를 신설하고 **`ReadinessThresholds.
  heartbeat_age_limit` 과 `worker_watchdog.evaluate_worker_health` 가 둘 다 그것을 부른다.**
  예산 규칙은 지금 readiness 것을 그대로 옮긴다(동작 변경 금지).
- 감시자는 하트비트 행의 `metadata_json` 에서 신고 간격을 읽는다
  (`sidefx_worker._declared_interval` 재사용, 새로 파싱하지 않는다).

### 금지 (증상 덮기)

- 등록부 900 을 키우는 것 — 간격은 env 로 바뀐다. 다음에 또 어긋난다.
- 감시자 알림 억제·쿨다운으로 반복만 줄이는 것 — 판정이 틀린 것이 문제다.
- `try/except: pass`, 하드코딩 우회, `# TODO` 미봉책.

## 검증 (완료 기준)

```
cd C:\tmp\foms-s-wdflap
PYTHONIOENCODING=utf-8 python -m pytest tests/domains/test_worker_watchdog.py tests/domains/test_sidefx_readiness*.py -q
PYTHONIOENCODING=utf-8 python -c "import app; print('APP_OK')"
```
- 새 계약 테스트 필수: **신고 간격 1800 · 나이 1000초 → stalled 아님**, **신고 간격 없음 ·
  나이 1000초 → stalled**(등록부 900 이 그대로 살아 있음), **신고 간격 1800 · 나이 5401 → stalled**.
- **변이 검증**: 공용 함수에서 `declared_interval * 3` 항을 지우면 위 첫 테스트가 red 가
  되는지 직접 확인하고 출력을 보고서에 적는다. 단언끼리 겹쳐 한쪽을 지워도 통과하면 실패다.

## 함정

- worktree cwd 는 턴 경계에서 리셋된다 — 모든 명령을 `cd C:\tmp\foms-s-wdflap &&` 로 시작.
- 루트에 새 파일 금지(`_PTC_ROOT_ALLOWLIST` 닫힌집합).
- 전체 pytest 금지. 단일 파일 실행만. `python` 앞에 `PYTHONIOENCODING=utf-8`.
- git 명령 금지(커밋·push 는 총괄 몫). CRLF 보존.
- `docs/` 를 읽는 테스트를 새로 만들지 않는다.
