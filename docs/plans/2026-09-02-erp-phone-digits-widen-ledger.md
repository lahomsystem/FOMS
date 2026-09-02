# 진행 원장 — erp_phone_digits 폭 확대 (B 등급)

플랜: `docs/plans/2026-09-02-erp-phone-digits-widen-plan.md`
워크트리: `c:\tmp\foms-s-phonedigits` · 브랜치 `session/phonedigits` (base `origin/deploy` 7b06c9663)
갱신 2026-09-02.

| # | Task | 상태 | 완료 기준 | 증거 |
|---|---|---|---|---|
| T1 | 격리 워크트리 + 플랜/원장 | DONE | 워크트리 `pwd` 확인, 두 문서 존재 | `/c/tmp/foms-s-phonedigits`, 본 파일 |
| T2 | 실패하는 계약 테스트 먼저| DONE | 수정 전 red 확인 | `4 failed` — `01089350264010587511` != `0108935026401058751125` |
| T3 | 코드 폭 확대| DONE | T2 green + `APP_OK` | `8 passed`, `APP_OK` |
| T4 | alembic 마이그레이션| DONE | 단일 head, upgrade/downgrade 왕복 | `alembic heads` = `phonewide_00` 1개; 실 PG 왕복: downgrade→폭20, upgrade→폭64 + 절단행 22자 복구, `len20 remaining: 0` |
| T5 | PG 레인| DONE | `tests/postgres` green, 컬럼 폭 64 실측 | `743 passed in 268.87s` (5441 레인), 신규 `test_phone_digits_width_pg.py` 5건 포함 |
| T6 | 전체 게이트| DONE | `pre_push_smoke` exit 0 | `=== PRE-PUSH SMOKE PASSED ===` EXIT=0 (377 passed) |
| T7 | 커밋 + deploy push + CI | DONE | 자기 커밋만, 전 워크플로 green | deploy `5d2bfb95a`(코드 `006200509`+AI_STATUS). cherry-pick 충돌은 AI_STATUS 1줄뿐 — 상류 판본 위에 내 줄만 재적용 |
| T8 | 스테이징 반영 확인 | 진행 중 | 절단 행 0 | 스테이징 1차: 폭 64·head `phonewide_00`·절단 56건 복구, **잔여 4건은 sd 소스라 미복구** → `phonewide_01` 로 후속 |

## 기록

* T7 push 시 AI_STATUS 상단 40줄 예산(4,000자)이 3,988자라 한 줄도 안 들어갔다. 같은 내용이
  "직전:" 헤더와 "기록 보관"에 이미 있는 엑셀·동선 중복 줄을 지우고 새 줄을 넣어 3,999자.
* 2026-09-02 착수. 브리프가 deploy 에 없어 `session/s0901-220206` 커밋 aac06fba4 에서 읽음.
* 브리프의 검색 소비자 5곳 중 2곳(`order_candidates.py`, `bulk_dispatch.py`)은 미병합
  naver 브랜치에만 있다. deploy 기준 소비자는 3곳
  (`erp_dashboard_search.py:44`, `foms_unified_search.py:265`, `foms/api/cs/dashboard.py:95`).
* 구분자 삽입안은 그 미병합 브랜치의 정확 일치 계약(`erp_phone_digits == digits`)을
  깨므로 기각. 순수 숫자열 유지.
* `DERIVED_COLUMNS` 백필은 부팅 자동이 아니라 approval 게이트 수동 인프라 —
  기존 81건은 새 마이그레이션이 직접 재계산해야 한다.

## 스테이징 실측 (2026-09-02, 읽기 전용)

`phonewide_00` 반영 후: 컬럼 폭 64, `alembic_version` = `phonewide_00`,
숫자열 20자 초과 56건(최대 22자) — 절단이 실제로 풀렸다.

남은 `length=20` 4건을 열어 보니 **전부 정본이 `structured_data` 에만 있는 주문**이었다.

```
#3246 phone='000-0000-0000'  sd='010-3501-5810 / 010-6411-0925'
#3337 phone='000-0000-0000'  sd='010-5286-6518 / 010-3158-2882'
#3792 phone='010-5217-7125'  sd='010-6899-7125(실측) / 010-5217-7125(상담)'
#4026 phone='010-2246-7668'  sd='010-2246-7668/010-8645-6696'
```

브리프의 "`phone` 과 `structured_data` 는 서로 같다"는 이 부분집합에서 사실이 아니다.
라이브 파생은 `parties.customer.phone` 을 먼저 보므로 복구도 같은 우선순위를 써야 한다 —
`phonewide_01` 이 그 축을 맡는다(`phonewide_00` 이 고친 행은 20자가 아니라 대상에서 빠짐).

## BLOCKED / 미해결

* 로컬 PG 레인(5441)에 마이그레이션 왕복 검증용 스크래치 DB `foms_test_phonewide_mig` 가
  남아 있다 — `DROP DATABASE` 는 guard 훅이 막는다. 정리는 수동.
