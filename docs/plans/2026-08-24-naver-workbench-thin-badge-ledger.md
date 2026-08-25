# 진행 원장 — 뱃지 얇게 읽기 + 조회 상한 상향 (2026-08-24)

스펙: `docs/specs/2026-08-24-naver-workbench-thin-badge_SPEC.md`
상위 계약: `docs/specs/2026-08-23-naver-workbench-v3_CONTRACT.md`
선행 원장: `docs/plans/2026-08-24-naver-workbench-async-result-ledger.md`
작업 위치: `c:\tmp\foms-s-naver-ingest` (브랜치 `session/naver-ingest`)

## 사용자 확정 (2026-08-24)
- 뱃지 비용 절감 = **얇게 읽기**(SQL 투영). 캐시 TTL 은 30초 그대로, 컬럼 마이그레이션 없음.
- 상한 = **링크 1500 · 집 500**.
- 이번 세션 범위 = 1순위만(뱃지 비용 + 상한 + 스테이징 실측 + deploy 푸시 + CI green).

## Task

| # | 내용 | 완료 기준 | 상태 |
|---|---|---|---|
| T1 | 투영 SQL + `_ThinLink` + 방언 폴백 | 투영 충실성 테스트 green(PG 레인) — `group_key`·`extract_claim` 동치 | DONE |
| T2 | `_work_groups(display=)` 배선(조회 4곳) | 모드 동치 테스트 green — 집 키·`_filter_counts`·`truncated` 완전 일치 | DONE |
| T3 | 뱃지가 `display=False` 사용 | 얇은 SQL 에 `raw_snapshot` 없음(PG 레인 계약 테스트) | DONE |
| T4 | 상한 상향(링크 1500 · 집 500 · 진행률=집 캡) | 벌크 진행률 상한이 화면 집 캡을 가리킨다 | DONE |
| T5 | 로컬 실측 전후 비교 | 249링크 리그에서 콜드 비용 하락 수치 기록 | DONE |
| T6 | 검증 전수 | `tests/services/integrations/` green · `APP_OK` · `pre_push_smoke` exit 0 | DONE |
| T7 | 스테이징 실측 | 콜드 med **113.0ms → 113.0ms (이득 0)** — 아래 기록 참조 | DONE(실패) |
| T8 | 커밋 · deploy 푸시 · CI 전 워크플로 green | `f1dcc098` CI 4/4 green 확인 | DONE |

## 기록

### 선행 세션 마무리
- 선행 원장 T9(커밋·푸시·CI)는 **완료**다. deploy HEAD `e9d2c959`, 코드 CI 4/4 green.

### 측정 리그 (2026-08-24)
- 스크립트: 세션 scratchpad `seed_perf.py`(시드/삭제) · `measure2.py`(구간) ·
  `measure3.py`(조회 방식 비교) · `measure4.py`(투영 vs 통째).
- **로컬 dev DB 에 합성 링크 249건이 심겨 있다**(`external_id` 접두어 `CLAUDE-PERF-`).
  실데이터 아님·PII 없음. **작업 끝나면 `python seed_perf.py wipe` 로 지운다.**

### 구현 (2026-08-24)
- `_ThinLink` + `_THIN_COLUMNS` + `_snapshot_projection` + `_fetch_links` 신설.
  `raw_snapshot` 자리에 **판정 경로만 담은 축소 문서**가 들어간다 — 뒤따르는 파이썬은
  한 줄도 갈라지지 않는다(`group_key`·`extract_claim`·`extract_place_status` 동일 함수).
- `display` 플래그를 `_work_groups` → `_queue_links`·`_place_groups`·
  `_claim_blocked_group_keys`·`_mark_sibling_claims`·`_attach_household_counts` 로 내렸다.
  병합·필터·캡·플래그 부착 코드는 **손대지 않았다**.
- ORM 이 아니라 평행 객체를 쓰는 이유는 **세션 identity map** 이다. 같은 요청에서 pane 이
  통째로 읽어 둔 인스턴스를 뱃지가 얇은 값으로 덮거나, 얇게 읽힌 인스턴스를 pane 이 건드려
  지연 로딩 N+1 이 나는 접점을 아예 없앤다.
- `_attach_household_counts` 의 대표 링크 조회는 **주문번호 한 컬럼만** 읽게 바꿨다
  (두 모드 공통 이득 — 거기서 스냅샷은 쓰이지 않았다).
- 상한: 링크 250 → **1500**, 집 200 → **500**,
  `PROGRESS_LINK_ID_LIMIT` = `WORK_GROUP_LIMIT`(집 수 상한이라 화면 집 캡을 그대로 가리킨다).

### 검증 (2026-08-24)
- 신규 회귀 13건. **SQLite 레인 3건**(모드 동치·뱃지==탭==칩·얇은 경로는 주문 조회 0) +
  **PG 레인 10건**(투영 충실성 8모양 · 얇은 SQL 에 스냅샷 본문 0 · 진짜 투영 하에서 모드 동치).
- **테스트가 비어 있지 않다는 확인**: 투영에서 `cancel` 경로 하나를 일부러 비틀자
  PG 레인 2건이 red 로 떨어졌다(모양별 충실성 + 모집단 동치). 되돌림.
- `tests/services/integrations/` **537 passed**.
- `python -c "import app; print('APP_OK')"` 성공.
- `scripts/ops/pre_push_smoke.ps1` **exit 0**(pytest 서브셋 324 passed).
- `failopen_scan.py` unclassified 0 — 새 broad except 없음. 인벤토리 3종 변경 없음.
- JS·CSS 무변경이라 `?v` 핀 범프 없음.

### 로컬 실측 — 절감폭 (249링크·82집 리그, 최솟값 15회)

| 구간(ms) | 통째 | 얇게 |
|---|---|---|
| **합계** | **76.6** | **45.9 (-40%)** |
| 큐 조회 | 16.8 | 10.3 |
| `_group_queue` ×2 | 11.8 | 8.3 |
| `_place_groups` | 17.9 | 12.3 |
| 형제 클레임 | 12.3 | 5.6 |
| 집계 | 19.0 | 12.1 |

**처음 어림(113ms → 15~20ms)은 틀렸다** — 조회만 보고 파이썬 몫을 빼먹었다. 얇은 경로에서는
파이썬이 더 크다(조회 ~15ms vs 파이썬 ~30ms): 같은 링크를 큐·발주확인전·형제·집계에서
3~4번 다시 훑는다(249링크에 약 850회 통과). 그 중복 제거는 `_work_groups` 내부 구조 변경이라
이번 범위 밖이다.

**로컬은 절감폭을 과소평가한다.** 로컬 PG 는 같은 기계라 전송이 거의 공짜인데 Railway 는
웹·DB 가 다른 서비스다. 통째 경로는 약 2.4MB 를 실어 나르고 얇은 경로는 그 1/10 이다 —
스테이징 콜드가 로컬(76ms)보다 큰 113ms 였던 이유다. **판정은 스테이징 실측으로 한다(T7).**

## 스테이징 실측 결과 — **얇게 읽기의 이득은 0이었다** (2026-08-24, 병렬 세션 측정)

| 조건 | 콜드 nvbadge med |
|---|---|
| 통째(구코드 08-24 12:07) | 113.0ms |
| 얇게(신코드) | **113.0ms** |

환경 지표(콜드 render 에서 nvbadge 를 뺀 값) 42.5 vs 41.7 로 거의 같아 비교가 성립한다.
측정: claude_master, 콜드 8회, 실브라우저.

**내 예측이 틀렸다.** 이 원장은 "로컬은 전송이 거의 공짜라 절감폭을 **과소**평가한다"고
적었는데, 실제로는 반대였다. Railway 는 웹·DB 가 같은 리전이라 3.3KB 스냅샷 본문의 전송이
싸고, 아낀 전송량만큼 `jsonb_build_object` 의 DB CPU 가 도로 먹는다. 로컬 표에 이미 단서가
있었다 — 얇은 경로에서 조회 15ms 대 파이썬 30ms 로 **이미 파이썬이 더 컸다**. 그때 "전송이
병목일 것"이라는 가정을 실측으로 검증하지 않고 스테이징 예측에 그대로 썼다.

**남은 것**: 코드는 무해하다(계약 동치가 PG 레인 10건으로 증명돼 있고 전 스위트 green).
다만 **복잡도만 늘고 이득이 없다.** 진짜 범인을 구간 계측으로 찾는 작업이 별도 커밋
(`b8a915de`)으로 진행 중이다 — 큐 조회·큐 묶기·발주확인 전·형제 클레임·집계 중 어디가
113ms 를 먹는지 응답 헤더로 읽는다.

**상한 상향(링크 1500·집 500)의 근거는 이 결과와 무관하게 유효하다.** 비용은 상한이 아니라
실제 행수에 비례하므로 오늘 비용은 그대로다. 다만 "얇게 읽기가 물량 여력을 만든다"는
부수 논거는 **취소한다** — 그 여력은 없다.
