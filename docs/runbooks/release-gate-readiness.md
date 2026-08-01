# FOMS Remediation Release-Gate Runbook (RELEASE-GATE-00)

배포 준비도 최종 게이트 운영 절차. 이 게이트는 §3 버그감사 remediation 전체(124 packet)가
배포 준비되었는지 **읽기 전용**으로 종합 판정한다. 게이트는 판정만 한다 — **실 배포는 게이트
green 이후 사용자 승인으로만** 진행한다.

관련 packet: PACKET-HARNESS-00(manifest 124) · API-ERROR-01(leak inventory) ·
FAILOPEN-01(broad-catch inventory) · REV-99(writer inventory·enforcement flag) ·
SIDEFX-WORKER-01/SCALE-CHANNEL-01(worker readiness) · SURFACE-GATE-01(persona artifact).

---

## 1. 도구

```
python tools/ops/check_foms_remediation_readiness.py            # 전체 게이트(worker 포함)
python tools/ops/check_foms_remediation_readiness.py --json     # 기계 판독(값 노출 0)
python tools/ops/check_foms_remediation_readiness.py --skip-service   # worker 제외(비프로덕션 스모크 전용)
```

- **읽기 전용**: DB write·상태 변경 0. approval token 불필요.
- **값 노출 0**: 출력은 check 이름·도메인·bool·정수 count·고정 상태 토큰(on/off/default)만.
  비밀/PII/env 원문/경로를 절대 echo 하지 않는다.
- worker 검사는 `DATABASE_URL`(없으면 `FOMS_TEST_DATABASE_URL`) env 로 배포 대상 DB 를
  조회한다. env 미설정/도달 불가 = **fail-closed**(service 실패).

## 2. Exit code 규약

| exit | 도메인 | 의미 | 대표 원인 |
|---|---|---|---|
| 0 | — | READY | 모든 항목 통과 |
| 1 | data | 데이터 결함 | 필수 seed/reference JSON 누락·손상 |
| 2 | service | 서비스 결함 | SIDEFX/CHANNEL worker heartbeat stale·미준비·DB 도달 불가 |
| 3 | artifact/config | 아티팩트/설정 결함 | packet coverage·CI·persona·enforcement flag·API leak 성장·silent broad catch |

여러 도메인이 동시에 실패하면 **artifact/config(3) > service(2) > data(1)** 우선순위로 가장
높은 코드를 반환한다(config 결함이 가장 근본이라 먼저 막는다). exit≠0 이면 **deploy 중단**.

## 3. 검사 항목 (값 노출 없이 확인)

| check | domain | 통과 조건 |
|---|---|---|
| `packet_coverage` | artifact | manifest 124 packet 전부 존재·각 created_tests 파일 landed |
| `ci_coverage` | artifact | 필수 CI workflow 존재(`ci.yml`·`harness-ci.yml`·`perf-gate.yml`·`postgres-lane.yml`) |
| `persona_artifacts` | artifact | v3 persona home 6종 존재(construction·cs·drawing·production·sales·shipment) |
| `data_coverage` | data | 필수 seed/reference JSON 존재·정상 파싱(형태만, 값 미검사) |
| `enforcement_flags` | artifact | `REV_IF_MATCH_ENFORCED`·`WRITE_GUARD_ENABLED` 이 well-formed(미설정=안전 기본) |
| `api_leak` | artifact | response `str(e)` 500 leak 이 inventory baseline 무성장 + raw `print_exc` 0 |
| `broad_catch` | artifact | failopen inventory + live scan 의 unclassified(silent broad catch) 0 |
| `workers` | service | SIDEFX(DELIVERY/EXPIRY_SCAN/RETENTION) + CHANNEL(CHANNEL_CREATE) readiness green |

## 4. 배포 준비 절차

1. deploy 대상 브랜치를 스테이징(lahom-dev)에 반영하고 CI green 을 확인한다.
2. 배포 대상 DB 를 가리키는 `DATABASE_URL` 을 설정한 셸에서 게이트를 **전체** 실행한다:
   `python tools/ops/check_foms_remediation_readiness.py --json`.
3. exit 0(READY) 이면 사용자에게 판정 결과를 보고하고 **배포 승인**을 받는다.
4. exit≠0 이면 §5 대응 후 재실행한다. 게이트가 green 이 될 때까지 배포하지 않는다.

> `--skip-service` 는 DB 가 없는 로컬/구조 스모크에서만 사용한다. **프로덕션 게이트에서 금지**
> (worker 검사를 건너뛴다). 사용 시 로그에 SKIP 경고가 남는다(fail-open 은 로그 기록 시에만 허용).

## 5. 게이트 실패 시 대응

- **exit 1 (data)**: 누락/손상 seed 파일을 복구한다(값 미노출이라 어떤 파일인지 count 만 표시 →
  `data/` 필수 목록과 대조). 손상 JSON 은 소스 커밋에서 재생성.
- **exit 2 (service)**: worker 미준비. `python tools/ops/check_sidefx_readiness.py --json` 과
  CHANNEL worker heartbeat 을 개별 확인한다. worker service 를 기동/재기동하고 heartbeat 신선도
  (<30s)·lag·DEAD 0 이 회복되면 재실행. DB 도달 불가면 `DATABASE_URL` 설정을 점검.
- **exit 3 (artifact/config)**: 실패 check 이름으로 원인 좁힌다.
  - `packet_coverage`: 누락 created_tests 를 land(해당 packet 재작업). manifest 는 직접 편집 금지.
  - `api_leak`: `str(e)` 500 응답이 baseline 초과 → API-ERROR-01 경계로 봉합(스캔은 값 미노출).
  - `broad_catch`: silent `except: pass` 신규 발생 → FAILOPEN-01 규약대로 disposition 부여
    (`# failopen: intentional: <reason>` 또는 로깅/fail-closed). `python tools/harness/failopen_scan.py --check` 로 확인.
  - `enforcement_flags`: env 값이 boolean 이 아님(malformed) → 오타 정정.

## 6. Enforcement flag cutover 순서 (안전 기본 → 강제)

enforcement flag 는 **안전 기본(opt-in)** 상태에서만 배포 게이트를 통과시킨다. 강제 전환은
전제조건이 충족된 뒤에만, 별도 단계로 수행한다(한 배포에 코드+강제 혼합 금지).

- **`WRITE_GUARD_ENABLED`** (WRITE-GUARD-01): 미설정 시 기본 `not TESTING` = 프로덕션 ON(secure
  default). 게이트는 well-formed 만 확인. OFF 로 낮추지 않는다.
- **`REV_IF_MATCH_ENFORCED`** (REV-99): **안전 기본 OFF**. 모든 order/JSONB writer 가
  version bump + If-Match/idempotency 를 경유하고(REV-99 writer inventory 무경유 0),
  모든 client 가 If-Match 를 전송하기 시작한 **이후에만** ON 으로 전환한다. writer/consumer
  마이그레이션 완료 전 ON 전환은 라이브 mutation 을 대량 428 로 파손시킨다.

cutover 절차: (1) writer/consumer 마이그레이션 배포·검증 → (2) client If-Match 전송 확인 →
(3) `REV_IF_MATCH_ENFORCED=1` 을 별도 배포로 전환 → (4) 428 발생률/에러 envelope 모니터.
문제 시 flag 를 OFF 로 되돌린다(코드 롤백 불필요). 단 **보안 취약 경로 재활성화 rollback 금지**.

## 7. 경계 / 금지

- 이 게이트는 **판정만** 한다. application mutation·DB write·상태 변경 0.
- manifest/inventory JSON 을 게이트가 편집하지 않는다(read-only). 결함은 소유 packet 에서 수정.
- 게이트 green ≠ 배포. 배포는 항상 **사용자 명시 승인**으로만. production push 금지 규칙(프로젝트
  CLAUDE.md)이 항상 우선한다.
