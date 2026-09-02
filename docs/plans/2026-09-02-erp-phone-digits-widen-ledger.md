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
| T7 | 커밋 + deploy push + CI | PENDING | 자기 커밋만, 전 워크플로 green | |
| T8 | 스테이징 반영 확인 | PENDING | 절단 행 0 | |

## 기록

* 2026-09-02 착수. 브리프가 deploy 에 없어 `session/s0901-220206` 커밋 aac06fba4 에서 읽음.
* 브리프의 검색 소비자 5곳 중 2곳(`order_candidates.py`, `bulk_dispatch.py`)은 미병합
  naver 브랜치에만 있다. deploy 기준 소비자는 3곳
  (`erp_dashboard_search.py:44`, `foms_unified_search.py:265`, `foms/api/cs/dashboard.py:95`).
* 구분자 삽입안은 그 미병합 브랜치의 정확 일치 계약(`erp_phone_digits == digits`)을
  깨므로 기각. 순수 숫자열 유지.
* `DERIVED_COLUMNS` 백필은 부팅 자동이 아니라 approval 게이트 수동 인프라 —
  기존 81건은 새 마이그레이션이 직접 재계산해야 한다.

## BLOCKED / 미해결

* 로컬 PG 레인(5441)에 마이그레이션 왕복 검증용 스크래치 DB `foms_test_phonewide_mig` 가
  남아 있다 — `DROP DATABASE` 는 guard 훅이 막는다. 정리는 수동.
