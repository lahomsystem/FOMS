# 진행 원장 — nav 뱃지 중복 순회 제거 (2026-08-24)

선행 원장: `docs/plans/2026-08-24-naver-workbench-thin-badge-ledger.md`
상위 계약: `docs/specs/2026-08-23-naver-workbench-v3_CONTRACT.md` (§2.4 뱃지 == 탭 숫자 == 칩 '전체')
작업 위치: `c:\tmp\foms-nvphase` (브랜치 `tmp/nvbadge-phase`, origin/deploy tip 기준)

## 왜 이 작업인가 — 얇게 읽기는 이득이 0 이었다

`f1dcc098`(얇게 읽기)의 가설은 "3.3KB 스냅샷 본문 전송이 행 조회 비용의 80%" 였다.
로컬에서는 -40% 였으나 **스테이징에서 재현되지 않았다.**

| | 통째(구코드, 08-24 12:07) | 얇게(신코드, 실브라우저) |
|---|---|---|
| nvbadge 콜드 med | 113.0ms | **113.0ms** |
| 콜드 render − nvbadge (환경 지표) | 42.5 | 41.7 |

환경 지표가 42.5 vs 41.7 로 같아 비교가 성립한다. **개선 0.**
Railway 는 웹·DB 가 같은 리전이라 전송이 싸고, 아낀 전송량을 `jsonb_build_object`
의 DB CPU 가 도로 먹는다. 선행 원장의 로컬 표에 이미 단서가 있었다 —
얇은 경로에서도 조회 15ms vs 파이썬 30ms.

## 구간 계측이 지목한 진짜 범인 (`b8a915de`, 스테이징 실브라우저 콜드 8회)

| 구간 | med(ms) | 비중 |
|---|---|---|
| `nvb_hcnt` (집계 — 형제 조회+파싱) | 42.5 | 27% |
| `nvb_qfetch` (확인 큐 링크 조회) | 34.5 | 22% |
| `nvb_sib` (형제 클레임 — 형제 **또** 조회+파싱) | 25.0 | 16% |
| `nvb_pfetch` (발주확인 전 링크 조회) | 21.5 | 14% |
| `nvb_qgroup` | 8.5 | 5% |
| `nvb_pclaim` (형제 **또** 조회+파싱, 3번째) | 6.5 | 4% |
| `nvb_pgroup` | 4.0 | 3% |
| **합계 nvbadge** | **155.5** | |

- **형제 3벌 = 74.0ms = 48%** — `_claim_blocked_group_keys` 2회(`_place_groups`·
  `_mark_sibling_claims`) + `_attach_household_counts` 1회. 셋 다 같은
  `external_order_no` 집합으로 형제 행을 읽고 같은 스냅샷을 다시 판정한다.
- **링크 2벌 = 56.0ms = 36%** — 확인 큐와 발주확인 전이 크게 겹치는데 따로 읽는다.

원자료: 세션 scratchpad `nvphases.json`(구간) · `nvbadge_browser_thin.json`(얇게 판정).

## Task

| # | 내용 | 완료 기준 | 상태 |
|---|---|---|---|
| T1 | ~~형제 인덱스 1벌~~ — order_no 합집합으로 한 번 읽어 `{집키: 건수·발주확인전·클레임·취소·확정형제클레임}` 을 만들고 세 소비처가 그걸 쓴다 | 옛 3벌 결과와 **집합·건수가 완전히 같다**는 동치 테스트 green | PENDING |
| T2 | 링크 조회 1벌 — 큐 술어 ∨ 발주확인전 술어를 한 번에 읽고 파이썬에서 가른다 | 캡 미달 구간에서 옛 2벌과 집 키 목록·`filter_counts`·`truncated` 완전 일치 | PENDING |
| T3 | 계약 회귀 — 뱃지 == 탭 == 칩 · display 두 모드 동치 · 캡/truncated 동치 | 신규 테스트 green + `tests/services/integrations/` 전수 green | PENDING |
| T4 | 검증 — `APP_OK` · `pre_push_smoke` exit 0 · deploy 푸시 · CI 전 워크플로 green | `gh run list` 전수 확인 | PENDING |
| T5 | 스테이징 재측정(실브라우저 콜드 8회) + 계측 커밋 되돌리기 | 콜드 med 실수치 기록 · `b8a915de` revert | PENDING |

## 규칙 (계약에서 내려온 것)

- **판정 함수를 두 벌로 만들지 않는다.** 모집단·술어는 그대로 두고 **읽는 횟수만** 줄인다.
  뱃지와 화면이 다른 함수로 세면 §2.4 가 깨진다(이 저장소가 두 번 겪었다:
  nav 67·탭 45 / nav 140·필터 43).
- 캡은 병합 뒤 한 곳에서만 건다. 원천마다 자르면 띠와 줄 수가 어긋난다.
- 조용한 잘림 금지 — 상한에 닿으면 로그 + 화면 고지.

## 기록

### T1·T2·T3 구현 (2026-08-24)

- `_SiblingIndex` + `_source_order_nos` + `_build_sibling_index` 신설. 형제 행을 한 번
  읽어 `counts`·`pending_counts`·`blocking`·`canceled`·`confirmed_claim_blocked` 를
  전부 만든다. 소비처 3곳(`_place_groups`·`_mark_sibling_claims`·
  `_attach_household_counts`)이 같은 색인을 나눠 쓴다. **옛 경로는 선택 인자를 안 줬을 때의
  분기로 그대로 살아 있다** — 동치 테스트가 그 둘을 직접 비교한다.
- `_work_source_links` 신설. 두 원천을 `or_(reviewed_at IS NULL, _place_pending_clause())`
  한 번으로 읽고 파이썬에서 가른다. 가르는 술어는 `_row_place_pending` 한 줄뿐이고
  SQL 술어와의 동치를 회귀 테스트가 못박는다.
- `_ThinLink`·`_THIN_COLUMNS` 에 `reviewed_at` 추가(가르기에 필요한 유일한 새 컬럼).
- `_attach_household_counts` 의 마지막 루프를 `_apply_household_counts` 로 뽑아 두 경로가
  **같은 규칙 한 벌**을 쓰게 했다.
- 캡: 상한은 합집합 하나에 걸고, 닿으면 두 원천 모두에 잘림 표식을 준다(조용한 잘림 금지).

**검증**
- 신규 회귀 5건 — 옛 3벌 경로와의 동치(얇은/표시 두 모드) · `_row_place_pending` ↔
  `_place_pending_clause` 동치 · 색인이 옛 클레임 키를 덮는지 · **링크 표 조회가 2회뿐**
  (옛 6회: 원천 2 + 형제 3 + 대표 링크 1).
- **테스트가 비어 있지 않다는 확인**: `_row_place_pending` 을 `return False` 로 비틀자
  동치 2건 + 술어 1건이 red. `return True` 로 넓히는 방향은 SQL 이 이미 막아 무해
  (합집합 밖 행은 파이썬이 되살릴 수 없다).
- `tests/services/integrations/` **542 passed** · `APP_OK` · `pre_push_smoke` **exit 0**.

### T4·T5 — 스테이징 재측정 (2026-08-24, 실브라우저 claude_master 콜드 8회)

deploy `181e8306` (CI: Harness·PG Lane·perf-gate green, FOMS CI 확인).

| 구간(ms, med) | 수술 전 | 수술 후 |
|---|---|---|
| `nvb_qfetch` (원천 조회) | 34.5 | 34.0 |
| `nvb_sibidx` (형제 색인 1벌) | — | 33.0 |
| `nvb_qgroup` | 8.5 | 5.0 |
| `nvb_place` (하위합) | 33.5 | 2.0 |
| `nvb_pfetch` | 21.5 | **0** |
| `nvb_pclaim` | 6.5 | **0** |
| `nvb_sib` | 25.0 | **0** |
| `nvb_hcnt` | 42.5 | **0** |
| **nvbadge 합계** | **155.5** | **75.0 (-52%)** |

수술 후 분포: min 67 · max 79(표본 7 — 1회는 캐시 히트라 제외). 조회는 2벌
(원천 합집합 + 형제 색인)만 남았다.

**화면 눈 확인**: nav 뱃지 62 == 처리 탭 62집 == 스트립 62집, 콘솔 에러 0.
(칩 '전체' 76집 은 어긋남이 아니다 — 타 세션 `a83e8044` 가 뱃지·탭·스트립을
`_actionable_count`(손댈 수 있는 집)로 바꾸고 잠긴 집은 `locked_count` 로 따로 고지한다.)

**정리**: 구간 계측(`b8a915de`)은 `record_phase("nvb_*")` 20줄을 걷어내 되돌렸다.
`context_processors` 의 `nvbadge` 총합 계측은 그대로 둔다(선행 커밋 자산).
로컬 dev DB 합성 시드 249건(`CLAUDE-PERF-`) 삭제 완료. 스테이징 코호트 38 원복.

**남은 것**: `nvb_qfetch` 34ms + `nvb_sibidx` 33ms = 67ms 가 이제 거의 전부다.
둘 다 조회 자체라 더 줄이려면 모집단 컬럼화(취소 표식을 JSONB 밖으로)가 필요하다 —
별건이다.
