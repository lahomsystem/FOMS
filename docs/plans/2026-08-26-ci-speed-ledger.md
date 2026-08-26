# CI 속도·위생 개선 진행 원장 (2026-08-26)

감리 근거: 멀티에이전트 정밀 감리(A 프로파일러 / B 워크플로 / C 테스트코드 / D 정상성 판정 / CEO 총괄).
보고서 원본은 세션 스크래치패드에 있고, 결론과 실측치는 아래에 옮겨 적는다.

## 배경 실측

| 항목 | 값 |
|---|---|
| FOMS CI median (2026-07-23) | 4.93분 |
| FOMS CI median (2026-08-26 수정 전) | 14.07분 (32일간 단조 증가 +0.231분/일) |
| `Run tests` 스텝 (수정 전) | 839초 = job 908초의 92% |
| 그중 PBKDF2 600,000 해싱 | 676초 (73%) |
| 그중 매 테스트 83테이블 DDL | 146초 (17%) |
| 실제 테스트 로직 | 92~98초 (11%) |
| 큐 대기 | p50/p90/max 전부 0초 (러너 부족 아님) |

분해 합이 총시간을 오차 2%로 재구성 → 숨은 병목 없음.

## P0 (완료, deploy 반영됨)

| ID | 내용 | 상태 | 결과 |
|---|---|---|---|
| P0-1 | 테스트 레인 PBKDF2 완화 (`DEFAULT_PBKDF2_ITERATIONS = 10`) | DONE `d9731236` | `Run tests` 839초 → 354초 |
| P0-2 | 봉인 계약 5건 (`tests/domains/test_password_kdf_contract.py`) | DONE `d9731236` | 패치 무효화 시 빨강 확인 |
| P0-3 | 전 워크플로 `timeout-minutes` (7파일) | DONE `01fd8e97` | 기본 6시간 → 15~30분 |
| P0-4 | 승격 PR(base=production)도 본 스위트·하네스 검증 | DONE `01fd8e97` | ci.yml·harness-ci.yml PR 필터에 production 추가 |

**P0 후 실측**: FOMS CI 14.07분 → **7.18분**, 전 워크플로 green.

## P1·P2 (이번 작업) — 전부 완료

| ID | 내용 | 결과 | 커밋 |
|---|---|---|---|
| T1 | `node --check` 148 spawn → 1프로세스 배치 파싱 | **12.5초 → 0.18초**. JS 에 파이썬 주석을 고의로 넣어 빨강 확인 | `642fb886` |
| T2 | pytest 설정 SSOT 신설 (`pytest.ini`) | 수집 3.42초 → 2.88초, 수집 개수·rootdir 불변, 4개 레인 정상 | `b395d8c7` |
| T3 | 스키마 세션 스코프화 + `after_create` 시드 5종 재실행 | **319초 → 120.7초**, 6154 passed / 0 failed | `04d489a6` |
| T4 | pytest-xdist `-n auto --dist loadfile` | **120.7초 → 48초**, 3회 연속 결과 집합 동일 | `0dbbecdc` |
| T5 | docs 전용 커밋 스코프 판정 + 레지스트리 계약 | 문서 커밋에 서브셋만 실행, 목록 누락 시 빨강 확인 | `66b064c7` |
| T6 | `ci_watch` cancelled→green 오판 수정 | green = success 하나로 fail-closed, 54 passed | (T6 커밋) |
| T7 | rum-daily 상시 red 정리 | **조치 불필요 — 이미 해소됨**(아래) | – |
| T8 | Actions 캐시 위생 | **45개 7.63GB → 4개 0.93GB** | (커밋 없음, 원격 상태 정리) |

### T4 가 드러낸 잠복 결함 2건 (병렬 이전부터 있던 것, 근본 수정함)
1. `tests/postgres/test_ops_approval.py` — parametrize 값을 수집 시점에
   `generate_password_hash` 로 만들어 salt 가 매번 달랐다. 워커끼리 수집 목록이
   어긋나 죽는다. 해시를 테스트 안에서 만들도록 바꿨다.
2. `tests/domains/test_auth_finance.py` — 거부 테스트가 "전역 SecurityLog 개수 동결"
   을 요구했는데, 정책 가드가 거부를 감사로 남기는 것은 설계된 동작이다. 옛 단언은
   `record_access_denied` 의 **60초 dedupe 창** 덕에 앞선 테스트가 같은 거부를 이미
   기록해 두었을 때만 성립했다 — 이 파일 단독 실행은 늘 3건 실패했다(P0 시점 conftest
   로 되돌려도 동일). 계약을 "handler 미실행" 으로 정확히 표현하도록 고쳤다.

### T7 판정: 조치 불필요
감리가 인용한 "실패율 28.6%" 는 7월~8월 초가 섞인 창의 값이다. 실측하니
**2026-08-09 이후 17회 연속 success** 이고, 마지막 실패는 2026-08-08
(`Fetch production RUM report` 스텝). 지금 고칠 red 가 없다. 감리가 지목한 진짜
위험이었던 192.9분 폭주(run 29707630560)는 P0-3 의 `timeout-minutes: 15` 가 이미 막는다.
없는 문제를 고치는 대신 이 판정을 남긴다.

### T8 상세
닫힌 승격 PR 의 merge ref 캐시 41개(6.18GB)를 삭제했다. 각 PR 은 base=production
에 캐시가 없어 매번 154MB 를 새로 저장하고 머지 후 다시 쓰이지 않았다. `deploy`
캐시 2개와 열린 PR(144·133) 캐시는 유지했다.
**남은 근본 원인**: production 브랜치에 pip 캐시가 없어 승격 PR 마다 miss →
새 캐시 저장이 반복된다. 이건 production push 에 CI 를 붙여야 풀리므로 별건으로 남긴다.

## 누적 효과

| 시점 | 로컬 전체 스위트 | FOMS CI |
|---|---:|---:|
| 감리 시작 (2026-08-26 오전) | 927초 | 14.07분 |
| P0 (PBKDF2 완화) 후 | 319초 | 7.18분 |
| T3 (스키마 세션화) 후 | 120.7초 | – |
| T4 (xdist) 후 | **48초** | (푸시 후 실측) |

## 기각 (재제안 금지 — 근거)

- **`concurrency: cancel-in-progress`** — `ci_watch.py` 가 cancelled 를 green 으로 오판(이미 4건 발생) + 커밋 단위 cherry-pick 승격 정책상 커밋마다 green 이 필요. P0-1 이후 실익도 소멸.
- **변경 파일 기반 선택 실행** — 트리 전수 스캐너 테스트 8종이 폭발 반경 매핑 불가. FOMS 의 과거 CI red 사고가 전부 "폭발 반경 밖"이었다.
- **larger runner** — 큐 대기 0초이고 public repo 라 이미 4 vCPU 무료.
- **matrix 샤딩** — `tests/domains` 가 99% 라 불균형, 판정면만 4배.
- **`requirements-ci.txt` 분리** — 운영 드리프트 전례(solapi).
- **테스트 삭제·스킵으로 시간 줄이기** — 프로젝트 정책 금지.
