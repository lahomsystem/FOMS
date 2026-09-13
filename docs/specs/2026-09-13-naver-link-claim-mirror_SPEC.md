# 수집 링크 클레임 축 사본 컬럼 (NVMIRROR-01) — Spec

> 상태: **승인 대기**. 코어 변경(DB 스키마 + 수집 경로)이라 구현 전 사용자 승인이 필요하다.
> 측정 원장: `docs/plans/2026-09-11-tab-roundtrip-slowdown-measurements.md` §11·§13·§14

## 1. 문제 — 한 요청이 같은 JSONB 를 네 번 detoast 한다

운영 `external_order_links` 실측(2026-09-13, 읽기 전용):

| 값 | 크기 |
|---|---|
| 테이블 총 | 13MB |
| 본체(heap) | 1,992kB |
| **TOAST** | **10,184kB** |
| `raw_snapshot` 평균 | **2,194 bytes** (TOAST 임계 약 2KB 초과) |
| `triage_state` 평균 | 280 bytes (본체에 들어간다) |
| 링크 | 2,388 |

평균 2,194 bytes 라 **대부분의 스냅샷이 본체 밖**이고, 그 컬럼을 건드리는 조회는 행마다 TOAST 를
한 번 더 읽는다. 같은 스캔을 두 번 재면 차이가 드러난다.

```
-- raw_snapshot 에서 스칼라 두 개를 뽑는다(지금 코드)
Seq Scan ... rows=2388   Buffers: shared hit=14736   Execution Time: 50.519 ms

-- raw_snapshot 을 아예 안 건드린다
Seq Scan ... rows=2388   Buffers: shared hit=249     Execution Time:  0.953 ms
```

**53배.** 스칼라 투영을 이미 쓰고 있으므로 투영으로는 더 줄지 않는다 — 컬럼을 건드리는 것 자체가
비용이다.

운영 페이지 요청 하나가 이 테이블을 서로 다른 투영으로 네 번 훑는다(§11 실측).

| 구간 | 모집단 | 운영 ms |
|---|---|---|
| `wb_work_groups` | 확인 대기 링크 + 형제 | 112~159 |
| `wb_ghosts` | 주문 붙은 링크 489 | 168 (§13 에서 투영으로 축소) |
| `wb_refresh` | 채널 전체 2,388 | 73~97 |
| `wb_history` | 이력 한 쪽(50집) | 99~145 |

## 2. 이미 있는 규약을 따른다 — "사본 컬럼"

이 저장소는 같은 이유로 사본 컬럼을 세 번 만들었다(`models.py` `ExternalOrderLink`):

* `place_order_status` — "raw_snapshot(JSONB) 안에도 있지만 그걸로 필터하면 인덱스 없는 JSONB
  스캔이 된다. 목록 필터 전용 사본이다."
* `group_key` — 주소 조립이 파이썬에서만 되므로 SQL 이 못 센다.
* `recipient_name` · `recipient_phone_digits` · `orderer_phone_digits` — 매칭 축이 캡에 갇히던 자리.

**정본은 언제나 `raw_snapshot`** 이고 사본은 필터·집계 전용이며, 값이 없으면 읽는 쪽이 옛 경로로
폴백한다. 이 Spec 은 그 규약에 **클레임 축**을 더하는 것이다.

## 3. 새 컬럼 (4개, 전부 nullable)

| 컬럼 | 타입 | 원본 경로 | 누가 읽나 |
|---|---|---|---|
| `product_order_status` | `String(30)` | `productOrder.productOrderStatus` (평평 폴백 `productOrderStatus`) | `claim_watch.refreshable_household_link_ids` 의 종결 판정 |
| `claim_status` | `String(40)` | `mapping.extract_claim(...)["status"]` | 유령 스캔·칩 집계 |
| `claim_type` | `String(20)` | `mapping.extract_claim(...)["type"]` | 유령 스캔(종류 축) |
| `payment_amount` | `Integer` | `productOrder.totalPaymentAmount` | 유령 띠 금액 합 |

`claim_status`/`claim_type` 은 **원본 필드 하나가 아니라 `extract_claim` 의 결과**를 담는다 —
그 함수가 6개 블록(`cancel`·`returnInfo`·`return`·`exchange`·`currentClaim`·`beforeClaim`)을
훑는 SSOT 이고, 손으로 경로를 고르면 R-7(얇은 경로만 "클레임 없음")이 재발한다.

nullable 인 이유는 기존 세 사본과 같다 — 백필 전 행이 있고, **값이 없으면 읽는 쪽이 스냅샷 경로로
폴백**해 예전과 같은 답을 낸다.

## 4. 쓰는 자리 (4곳 — 전부 이미 사본을 쓰는 자리)

| 파일 | 자리 | 지금 하는 일 |
|---|---|---|
| `ingest.py:141` | 수집 생성 | `place_order_status`·`group_key`·`recipient_*` 를 넣는다 |
| `ingest.py:366` | 재수집 갱신 | 같음 |
| `claim_watch.py:448` | 클레임 스윕 | 스냅샷 교체 + `place_order_status`·`group_key` 갱신 |
| `fulfillment.py:892` | 발주확인 성공 | `place_order_status = "OK"` |

추출 실패가 수집을 막지 않는다는 규약도 그대로 따른다(`_place_status_value` docstring:
"추출이 실패해도 수집은 막지 않는다 — 못 받은 주문은 되돌릴 수 없다").

## 5. 마이그레이션·백필

1. Alembic 리비전: 컬럼 4개 추가(전부 nullable, server_default 없음).
2. 백필 스크립트 `scripts/maintenance/backfill_link_claim_mirror.py` — 배치 500행, 재실행 안전
   (idempotent), 진행 로그. 운영 2,388행이라 한 번에 끝난다.
3. 읽는 쪽 전환: 컬럼이 있으면 쓰고 NULL 이면 스냅샷 폴백. **게이트가 필요 없다** — 폴백이
   동치를 보장하므로 배포 순서가 어긋나도 답이 안 바뀐다.
4. 인덱스는 **이번에 만들지 않는다**. 지금 병목은 인덱스 부재가 아니라 TOAST 읽기이고,
   컬럼만으로 53배가 나온다. 필요해지면 실측 뒤 따로 판단한다.

## 6. 계약 테스트

| 테스트 | 지키는 것 |
|---|---|
| 사본 == 스냅샷 파생값 (모양 8종) | 드리프트 게이트. `extract_claim` 이 바뀌면 red |
| 컬럼 NULL 이면 옛 경로로 폴백해 **같은 답** | 백필 전에도 화면이 안 바뀐다 |
| 스윕·수집·발주확인 4자리가 전부 사본을 갱신한다 | 한 자리를 빼먹으면 사본이 조용히 낡는다 |
| PG 레인: 전환된 조회 SQL 에 `raw_snapshot AS` 본문이 없다 | 실제로 TOAST 를 안 읽는가 |
| 음성 대조군: 모양에 클레임 있는 것/없는 것 둘 다 | 빈 값끼리 비교해 통과하는 것을 막는다 |

## 7. 기대 효과 (측정으로 판정한다)

* `wb_refresh` 73~97ms → **한 자리 ms** 대(같은 스캔 50.5ms → 0.95ms 근거).
* `wb_ghosts` — §13 투영으로 이미 줄였고, 사본을 쓰면 스냅샷을 **아예 안 읽는다**.
* `wb_work_groups` 는 이 Spec 범위 밖이다. 그 경로는 주소·제품명까지 읽으므로 사본 4개로는
  안 끝난다 — 별도 판단이 필요하다.
* `wb_history` 도 범위 밖이다. 화면이 제품명·금액을 실제로 그린다.

판정은 운영 `X-FOMS-EPT-B7-PHASES` 로 한다(1회 세션 규칙).

## 8. 위험과 되돌리기

| 위험 | 대응 |
|---|---|
| 사본이 낡는다 | 갱신 자리 4곳을 계약 테스트로 고정. 정본은 스냅샷이라 재수집이 고친다 |
| `extract_claim` 규칙 변경 | 드리프트 계약이 red. 백필 스크립트를 다시 돌리면 맞는다 |
| 마이그레이션 실패 | 컬럼 추가뿐이라 `downgrade` 가 컬럼 4개 drop. 데이터 손실 없음 |
| 백필 중 부분 상태 | 폴백이 있으므로 섞여 있어도 답이 같다 |

## 9. 범위 밖 (하지 않는 것)

* `raw_snapshot` 을 줄이거나 압축 설정을 바꾸지 않는다.
* 인덱스를 만들지 않는다(§5-4).
* `wb_work_groups`·`wb_history` 경로를 건드리지 않는다.
* 화면·문장·권한은 한 글자도 바뀌지 않는다.
