# 진행 원장 — 붙이기 결과가 화면에 안 나타나는 결함 (2026-08-24)

상위 계약: `docs/specs/2026-08-23-naver-workbench-v3_CONTRACT.md`
작업 위치: `c:\tmp\foms-s-naver-ingest` (브랜치 `session/naver-ingest`)

## 신고

> "추가결제로 붙이기 / 재결제로 붙이기 버튼을 눌러도 액션이 없다" (링크 264, 주문 4485)

이후 사용자 관측으로 정정: **확인창은 뜨고 붙이기도 성공한다**("주문 #4485 에 붙어 있습니다").
정작 `/edit/4485?open=erp-order` 에 들어가면 아무것도 없다.

## 근본 원인 (2026-08-24 실데이터 + 로컬 재현으로 확정)

주문 편집 화면은 표식 하나로 네이버 도크 전체를 켠다:

```python
# foms/web/orders/edit.py:448
if (order.structured_data or {}).get('source') == 'NAVER_SMARTSTORE':
    payload['naver_origin'] = build_dock_payload(get_db(), order)
```

그리고 붙이기가 기록한 추가결제(`pricing.extra_payments`)를 읽는 코드는 **그 도크 하나뿐**이다
(`dock.py:233 _extra_payment_summary`). 표식이 없으면 붙이기는 성공했는데 볼 자리가 없다.

표식이 없던 이유가 두 겹이다.

1. **`attach_link_to_order` 가 표식을 안 찍었다.** `source` 는 주문 *생성* 매핑에서만
   찍혔다(`mapping.py:320`).
2. **ERP 폼 저장이 표식을 지웠다.** 보존 목록 `_OPERATIONAL_TOP_LEVEL_KEYS`
   (`erp_orders_structured.py:223-`)에 `source`·`naver`·`pricing` 이 없었고,
   `enforce_form_allowlist` 는 들어온 dict 에서 낯선 키를 걷어낼 뿐 **빠진 옛 키를
   되살리지 않는다** — strip 목록에도 안 남아 로그조차 없었다.

로컬 재현(저장 경로 그대로 호출):

```
strip 된 키: []            ← 경고 0
  source   저장 전 있음 → 저장 후: **사라짐**
  naver    저장 전 있음 → 저장 후: **사라짐**
  pricing  저장 전 있음 → 저장 후: **사라짐**
```

스테이징 전수가 **9/9 로 일치**했다. 네이버 링크가 붙은 주문 9건 중 ERP 편집 흔적
(`entity_type`)이 있는 5건은 전부 `source` 없음, 편집이 없던 4건은 전부 있음.

**더 나쁜 것**: `pricing` 이 같이 걸려 있었다. 주문 4485 를 ERP 에서 한 번 저장하면
방금 기록된 추가결제 6건 **1,610,780원**이 경고 없이 사라질 자리였다.

## 조사 경과에 대한 기록 (재발 방지)

멀티 에이전트 조사에서 나온 진단 2개(`window.confirm` 억제 / 서버 400 alert 유실)는
**둘 다 틀렸다**. 적대 검증자가 원 진단을 확정해 주지 않고 자기모순을 짚은 것
(`alert` 도 `confirm` 과 같은 네이티브 대화상자 채널이라, confirm 이 억제되는 환경이면
서버 400 도 무흔적이 되어 "서버 배제" 논거가 무너진다)이 결정적이었다. 서버 거절 가지는
실데이터로 닫았고(주문 4485 생존·형제 6건 전부 `order_id` NULL·클레임 없음), 후보가
바닥난 지점에서 **사용자 관측 한 줄**("확인창은 뜬다")이 방향을 뒤집었다.
교훈: 화면 밖에서 코드만 읽어 원인을 확정하지 말 것.

## Task

| # | 내용 | 완료 기준 | 상태 |
|---|---|---|---|
| A1 | 붙이기가 `source` 각인(`_stamp_source_marker`) | 회귀 3건 green · 기존 값 안 덮음 | DONE |
| A2 | 폼 저장이 `source`·`naver`·`pricing` 보존 | 회귀 6건 green · 폼이 보낸 값은 여전히 우선 | DONE |
| A3 | 이미 잃은 주문 백필(`tools/ops/backfill_naver_source_marker.py` → 2026-08-28 `backfill_naver_link_marker.py` 로 개명·용도 변경) | 스테이징 5건 복구 · 재실행 0건(멱등) | DONE |
| A4 | 검증 전수 + 커밋 + deploy 푸시 + CI green | `gh run list` 4종 | PENDING |

## 기록

### 구현
- `promotion._stamp_source_marker(order)` — **비어 있을 때만** 찍는다. 다른 채널 표식을
  네이버로 바꾸면 그 주문의 출처가 거짓이 된다.
- `_OPERATIONAL_TOP_LEVEL_KEYS` 에 `source`·`naver`·`pricing` 추가. 폼이 값을 보내면
  여전히 그 값이 이긴다(보존이 편집을 막지 않는다 — 회귀로 못박음).
- 백필은 기본 `--dry-run`, `--execute` 로만 쓴다. 조회는 `ix_external_order_link_order`
  인덱스를 타며 JSONB 스캔이 없다.

### 검증
- 신규 회귀 **9건**(폼 보존 6 + 붙이기 각인 3). **둘 다 red 확인함**: 보존 목록에서
  3키를 빼면 4건 red, `_stamp_source_marker` 호출을 빼면 2건 red. 되돌림.
- 스테이징 백필: `written=5` (4242·4461·4462·4481·4485) → 재실행 `written=0`,
  `already_marked=9`. 4485 의 추가결제 6건 1,610,780원 그대로 보존 확인.
- `APP_OK` 성공.
