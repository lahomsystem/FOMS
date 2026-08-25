# 네이버 워크벤치 — 뱃지 얇게 읽기 + 조회 상한 상향 (2026-08-24)

상위 계약: `docs/specs/2026-08-23-naver-workbench-v3_CONTRACT.md` (§0 절대 규칙 6개가 판정 기준)
선행 원장: `docs/plans/2026-08-24-naver-workbench-async-result-ledger.md` (승격 게이트 1·3 완료분)
작업 위치: `c:\tmp\foms-s-naver-ingest` (브랜치 `session/naver-ingest`)

## 1. 문제

`QUEUE_LINK_FETCH_LIMIT = 250`. 스테이징이 큐 링크 **229건**(총 249건)이라 곧 닿는다. 닿으면
"상한에 닿아 일부 집이 안 보입니다" 띠가 **상시 발동**한다 — 늘 켜진 경고는 아무도 안 읽고,
정작 진짜로 잘릴 때 못 알아챈다(2026-08-24 에 같은 부류의 결함을 이미 한 번 고쳤다).

그냥 올리면 안 되는 이유: nav 뱃지가 **모든 페이지 렌더**에서 `_work_groups` 를 돌고,
그 비용이 링크 수에 비례한다. 게이트 ON 콜드 실측 113ms(최악 280ms, 스테이징 73집).

## 2. 실측 — 범인은 파싱이 아니라 스냅샷 행 전송이다

측정 리그: 스테이징과 같은 물량(249링크·82집·스냅샷 3.3KB — 스테이징 실측 중앙값 2969B·
평균 3498B에 맞춘 합성 시드)을 로컬 PG 에 심고 `_work_groups` 를 구간별로 쟀다.
총 83~204ms(중앙값 153ms) — 스테이징 콜드 113ms 와 같은 대역이라 대표성이 있다.

| 구간 | ms | 몫 |
|---|---|---|
| `_queue_links` 조회 | 77.5 | 51% |
| `_attach_household_counts`(조회 2회) | 31.4 | 21% |
| `_place_groups`(조회 3회 포함) | 21.3 | 14% |
| `_claim_blocked_group_keys` | 13.3 | 9% |
| `_group_queue` ×2 | 12.5 | 8% |
| **`summarize_snapshot` 979회** | **5.5** | **3.6%** |

같은 240행을 조회 방식만 바꾼 재측정:

| 조회 방식 | 중앙값 |
|---|---|
| ORM 통째(`raw_snapshot` 포함) | 22.3ms |
| ORM `load_only`(스냅샷 제외) | 4.4ms |
| 컬럼 튜플 | 2.0ms |
| `COUNT(DISTINCT group_key)` | 1.3ms |

**결론 3가지**
1. `summarize_snapshot` 은 979회에 5.5ms(건당 5.6µs)다. **"중복 파싱 줄이기"는 가치가 없다.**
2. 3.3KB `raw_snapshot` 본문이 행 조회 비용의 **약 80%** 다.
3. `_work_groups` 는 249개 링크를 보려고 **약 800행분**을 읽는다(큐 229 + 발주확인전 136 +
   형제 113 + 대표 82 + 집계용 249). 행마다 JSONB 2개를 역직렬화한다(943회 계측).

## 3. 설계 — 같은 코드, 다른 문서

**뱃지용 함수를 따로 만들지 않는다.** 모집단 코드가 두 벌이 되는 순간 계약 §2.4
(뱃지 == 탭 숫자 == 칩 '전체')가 깨진다 — 이 저장소가 이미 두 번 겪은 결함이다
(nav 67·탭 45 / nav 140·필터 43).

대신 **SQL 이 돌려주는 문서만 바꾼다.**

- `display=True`(화면): 지금 그대로 `raw_snapshot` 통째.
- `display=False`(뱃지): `raw_snapshot` 자리에 **판정에 필요한 경로만 담은 축소 문서**를
  SQL 이 조립해 준다. 뒤따르는 파이썬 코드는 **한 줄도 갈라지지 않는다** —
  `group_key()`·`extract_claim()`·`extract_place_status()`·`summarize_snapshot()` 이
  같은 함수로 같은 경로를 읽는다. 표시 전용 필드(제품명·고객명·금액·출고예정)만 빈 값이 된다.

### 3.1 축소 문서(투영)

```sql
jsonb_build_object(
  'order', jsonb_build_object(
      'orderId',     raw_snapshot->'order'->'orderId',
      'claimStatus', raw_snapshot->'order'->'claimStatus'),
  'productOrder', jsonb_build_object(
      'shippingAddress',  COALESCE(raw_snapshot->'productOrder'->'shippingAddress',
                                   raw_snapshot->'shippingAddress'),
      'claimStatus',      COALESCE(raw_snapshot->'productOrder'->'claimStatus',
                                   raw_snapshot->'claimStatus'),
      'claimType',        COALESCE(raw_snapshot->'productOrder'->'claimType',
                                   raw_snapshot->'claimType'),
      'placeOrderStatus', COALESCE(raw_snapshot->'productOrder'->'placeOrderStatus',
                                   raw_snapshot->'placeOrderStatus')),
  'cancel',       raw_snapshot->'cancel',
  'currentClaim', raw_snapshot->'currentClaim')
```

`COALESCE` 는 `unwrap_detail` 의 **평평한 응답 폴백**(`detail.get("productOrder")` 가
dict 가 아니면 `detail` 자신을 쓴다)을 그대로 재현한 것이다. 이 4개 키가
`group_key`·`extract_claim`·`extract_place_status` 가 읽는 경로 전부다.

실측: 240행 기준 통째 16.6ms → 투영 **5.1ms**.

**SQLite 폴백**: `jsonb_build_object` 는 PostgreSQL 전용이다. 비 PG 방언에서는 투영을
포기하고 `raw_snapshot` 통째를 싣는다 — 결과는 같고 비용만 옛날 값이다(테스트 레인 보호).

### 3.2 얇은 행 객체

축소 문서를 ORM 인스턴스에 얹으면 **세션 identity map** 과 싸운다(같은 요청에서 pane 이
이미 통째로 읽어 둔 인스턴스를 뱃지 조회가 덮거나, 반대로 `defer` 된 인스턴스를 pane 이
건드려 N+1 이 된다). 그래서 얇은 경로는 ORM 을 쓰지 않고 **읽기 전용 행 객체**를 만든다:

```python
class _ThinLink:  # ExternalOrderLink 와 같은 속성 이름만 노출한다(오리 타이핑)
    id, external_id, external_order_no, order_id, sync_status,
    place_order_status, relation, group_key, created_at,
    triage_state, raw_snapshot(=축소 문서)
```

`household_key`·`is_place_pending`·`is_promotable`·`_place_view`·`_dispatched_count`·
`summarize_snapshot` 은 전부 **속성 읽기뿐**이라 그대로 통과한다(2026-08-24 확인).

### 3.3 배선

- `_work_groups(db, *, display: bool = True)` — 내부 조회 4곳(`_queue_links`·
  `_place_groups`·`_claim_blocked_group_keys`·`_attach_household_counts`)에 같은 플래그를
  내린다. 병합·필터·캡·플래그 부착 코드는 **손대지 않는다**.
- `triage_count._workbench_group_count` 가 `display=False` 로 부른다.
- 화면(`naver_ingest_triage`)은 기본값 그대로 `display=True`.

### 3.4 상한 (사용자 확정 2026-08-24)

| 상수 | 지금 | 바꿀 값 | 근거 |
|---|---|---|---|
| `QUEUE_LINK_FETCH_LIMIT` | 250 | **1500** | 스테이징 229 의 6.5배 — 평소엔 안 닿는 안전장치 |
| `WORK_GROUP_LIMIT` | 200 | **500** | 링크 1500 ÷ 평균 3.2건/집 ≈ 470집. 링크 상한만 올리면 집 캡이 대신 상시 발동한다 |
| `PROGRESS_LINK_ID_LIMIT` | 200 | **`WORK_GROUP_LIMIT`** | 이 값은 **집(대표 링크) 수** 상한이다(벌크가 보내는 id 는 집마다 하나). 벌크 대상 ⊆ 화면 목록(계약 §0-5)이므로 화면 집 상한을 그대로 가리키게 해 앞으로 드리프트를 없앤다 |

**상한을 올려도 오늘 비용은 늘지 않는다.** 비용은 상한이 아니라 실제 행수에 비례한다.
얇게 읽기가 행당 비용을 약 1/3~1/5 로 낮추므로, 물량이 실제로 늘어도 여력이 있다.

## 4. 완료 기준

1. **모드 동치**(계약 §2.4 증명): 클레임·취소·분할배송·확인완료 형제가 섞인 픽스처에서
   `display=False` 와 `display=True` 의 **집 키 목록·`_filter_counts`·`truncated` 가 완전히 같다.**
2. **투영 충실성**(PG 레인): 중첩/평평/`cancel`/`currentClaim` 모양별로
   `group_key(투영) == group_key(통째)` 이고 `extract_claim(투영) == extract_claim(통째)`.
3. **실제로 얇은가**(PG 레인): 얇은 경로가 낸 SQL 에 `raw_snapshot` 본문 컬럼이 없다.
4. 상한 3종이 새 값이고, 벌크 진행률 상한이 화면 링크 상한과 같다.
5. `tests/services/integrations/` 전수 green · `APP_OK` · `pre_push_smoke` exit 0.
6. 스테이징 실측: 같은 계측기(`X-FOMS-EPT-B7-PHASES` 의 `nvbadge`)로 게이트 ON **콜드**가
   113ms 기준선보다 **의미 있게** 내려간 것을 확인하고 실수치를 원장에 적는다.
   목표치를 미리 못박지 않는 이유는 아래 §6 에 적었다. 뱃지 숫자 == 처리 탭 숫자 ==
   칩 '전체' 눈 확인도 같이 한다.
7. deploy 푸시 후 CI 전 워크플로 green(`gh run list` 로 확인).

## 5. 하지 않는 것

- 캐시 TTL 은 30초 그대로(사용자 결정 — 숫자가 낡는 대가를 지불하지 않는다).
- 클레임 컬럼 신설·마이그레이션 없음(운영 승격이 이미 마이그레이션 계보 문제로 막혀 있다).
- 게이트 OFF 경로(`naver_triage.html`·`_queue_group_count`)는 손대지 않는다.
- 운영 승격은 별건(사용자 명시 요청 시에만).

## 6. 절감폭에 대한 정직한 기록 (2026-08-24 로컬 실측)

처음 어림은 "113ms → 15~20ms" 였다. **그 어림은 틀렸다** — 조회 비용만 보고 파이썬 몫을
빼먹었다. 249링크 리그에서 `_work_groups` 최솟값을 재보면:

| | 통째(`display=True`) | 얇게(`display=False`) |
|---|---|---|
| 합계 | 76.6ms | **45.9ms** (-40%) |
| 큐 조회 | 16.8 | 10.3 |
| `_group_queue` ×2 | 11.8 | 8.3 |
| `_place_groups` | 17.9 | 12.3 |
| 형제 클레임 | 12.3 | 5.6 |
| 집계 | 19.0 | 12.1 |

얇은 경로에서는 이제 **파이썬이 더 크다**(조회 ~15ms vs 파이썬 ~30ms). 같은 링크를
큐·발주확인전·형제·집계에서 3~4번 다시 훑기 때문이다(249개 링크에 약 850회 통과).
그 중복을 없애려면 `_work_groups` 내부 구조를 바꿔야 하고, 그건 이번 범위가 아니다.

**로컬 수치는 절감폭을 과소평가한다.** 로컬 PG 는 같은 기계라 전송 시간이 거의 0 인데,
Railway 는 웹과 DB 가 다른 서비스다. 통째 경로는 249행 × 3.3KB ≈ 0.8MB(중복 조회까지
치면 약 2.4MB)를 실어 나르고 얇은 경로는 그 1/10 이다 — 스테이징 콜드가 로컬보다 큰
113ms 였던 이유가 그것이다. 그래서 **판정은 스테이징 실측으로 한다.**
