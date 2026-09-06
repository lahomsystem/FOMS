# 2026-08-24 폼 저장 한 번에 서버 소유 structured_data 최상위 키가 사라졌다

> 유형: 데이터 사고  ·  상태: 종결
> 작성 2026-09-07. 사후 등재 문서 — 사고 당시 기록이 아니라 저장소 근거로 재구성했다.

## 1. 요약 5축

| 축 | 내용 |
|---|---|
| 유형 | 데이터 사고 — 서버 소유 JSONB 최상위 키(`source`·`naver`·`pricing`) 무음 소실 |
| 원인 축 | ERP 폼 PUT 의 **보존 목록(`_OPERATIONAL_TOP_LEVEL_KEYS`) 누락**. `enforce_form_allowlist` 는 들어온 dict 에서 낯선 키를 걷어낼 뿐 **빠진 옛 키를 되살리지 않고**, strip 목록에도 안 남아 로그조차 없었다(`foms/api/erp_orders_structured.py:260-263`, `docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md:30-33`) |
| 복구 | 스테이징 백필 `written=5`(4242·4461·4462·4481·4485), 재실행 `written=0`·`already_marked=9`. **운영 백필 실행 여부는 `미상(근거 없음)`** |
| 구조 변경 여부 | 있음. 붙이기가 표식을 각인(`_stamp_source_marker`) + 보존 목록에 `source`·`naver`·`pricing` 등재 + 회귀 9건(둘 다 red 확인) |
| 재발 여부 | 같은 사고의 재발 기록은 없다. 다만 **같은 재발 경로가 코드 주석에 명시**돼 있고(`naver_linked`, `foms/api/erp_orders_structured.py:272-276`), 보존 목록은 지금도 사람이 손으로 유지하는 allowlist 다(`docs/plans/2026-09-06-foms-system-review-report.md:37`) |

## 2. 증상

신고는 "붙이기 버튼을 눌러도 액션이 없다" 였다(링크 264, 주문 4485 —
`docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md:8`).

사용자 관측으로 곧 정정됐다: **확인창은 뜨고 붙이기도 성공한다**("주문 #4485 에 붙어 있습니다").
정작 `/edit/4485?open=erp-order` 에 들어가면 **아무것도 없다**
(`docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md:10-11`).

즉 화면에서 사라진 것은 버튼의 반응이 아니라 **붙이기가 기록한 결과 전체**였다. 주문 편집
화면은 표식 하나로 네이버 도크 전체를 켜고(`foms/web/orders/edit.py:448` 기준
`structured_data['source'] == 'NAVER_SMARTSTORE'`), 붙이기가 기록한 추가결제
(`pricing.extra_payments`)를 읽는 코드는 **그 도크 하나뿐**이다
(`docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md:15-24`).

## 3. 타임라인

| 시각 | 사건 | 근거 |
|---|---|---|
| `미상(근거 없음)` | 주문 4485 에 붙이기 실행 → 추가결제 6건 `1,610,780원` 기록 | `docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md:47-48` |
| `미상(근거 없음)` | ERP 폼에서 그 주문을 한 번 저장 → `source`·`naver`·`pricing` 소실 | 같은 파일 `:30-33`, `:38-41`(로컬 재현 출력) |
| 2026-08-24 (HH:MM `미상(근거 없음)`) | 신고 접수("액션이 없다") → 사용자 관측으로 정정("확인창은 뜬다") | 같은 파일 `:8`, `:10-11` |
| 2026-08-24 | 실데이터 + 로컬 재현으로 원인 확정. 스테이징 전수 **9/9 일치** | 같은 파일 `:13`, `:44-45` |
| 2026-08-24 | 수정 3건(A1 각인 · A2 보존 · A3 백필) DONE, 검증·커밋·deploy 는 `A4 PENDING` 으로 남아 있음 | 같은 파일 Task 표 |
| 2026-08-28 | 붙이기 게이트를 `source` 가 아니라 `naver_linked` 로 갈라냄(출처와 게이트는 뜻이 다르다) | `foms/api/erp_orders_structured.py:272-276` |

## 4. 근본 원인

**표식이 없던 이유가 두 겹이다**(`docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md:26-33`).

1. **`attach_link_to_order` 가 표식을 안 찍었다.** `source` 는 주문 *생성* 매핑에서만 찍혔다
   (`mapping.py:320` 기준). 붙이기 경로는 그 각인을 지나지 않았다.
2. **ERP 폼 저장이 표식을 지웠다.** 보존 목록 `_OPERATIONAL_TOP_LEVEL_KEYS`
   (`foms/api/erp_orders_structured.py:231`)에 `source`·`naver`·`pricing` 이 없었다.
   `enforce_form_allowlist`(`structured_form_projection`)는 **들어온 dict 에서 낯선 키를 걷어낼 뿐
   빠진 옛 키를 되살리지 않는다** — 그리고 strip 목록에도 안 남아 **로그가 없다**
   (`foms/api/erp_orders_structured.py:260-263`).

이 두 번째 겹이 이 사고의 성질을 결정한다. **폼은 이 키들을 렌더하지도 보내지도 않으므로,
보존 목록에 없으면 주문을 한 번 열어 저장하는 것만으로 조용히 사라진다**
(`foms/api/erp_orders_structured.py:260-262`).

로컬 재현이 그대로 찍혔다(`docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md:37-42`):

```
strip 된 키: []            ← 경고 0
  source   저장 전 있음 → 저장 후: **사라짐**
  naver    저장 전 있음 → 저장 후: **사라짐**
  pricing  저장 전 있음 → 저장 후: **사라짐**
```

**규모(스테이징 실측, 9/9 일치).** 네이버 링크가 붙은 주문 9건 중 ERP 편집 흔적(`entity_type`)이
있는 **5건은 전부 `source` 를 잃었고**, 편집이 없던 **4건은 전부 남아 있었다**
(`foms/api/erp_orders_structured.py:264-265`,
`docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md:44-45`).
갈림 변수가 "ERP 편집을 했는가" 하나임을 음성 대조군까지 포함해 확정한 실측이다.

**운영 규모는 `미상(근거 없음)`** — 위 전수는 스테이징에서만 잰 값이다.

**돈이 걸려 있던 자리.** 세 키의 손실 비용이 서로 다르다
(`foms/api/erp_orders_structured.py:266-271`):

- `source` — 없으면 편집 화면이 네이버 원본 도크를 아예 렌더하지 않고, 대시보드의 채널 취급도 함께 꺼진다.
- `naver` — 수집 원본 참조(주문번호 등). **버리면 다시 만들 방법이 없다.**
- `pricing` — 붙이기가 기록한 추가결제·재결제 금액. 폼 저장 한 번에 **돈 기록이 통째로 날아가는
  자리**였다(주문 4485: `1,610,780원` 6건).

## 5. 복구

- **백필**: `tools/ops/backfill_naver_source_marker.py`(→ 2026-08-28 `backfill_naver_link_marker.py`
  로 개명·용도 변경). 기본 `--dry-run`, `--execute` 로만 쓴다. 조회는
  `ix_external_order_link_order` 인덱스를 타며 JSONB 스캔이 없다
  (`docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md` Task A3 · 구현 절).
- **스테이징 실행 결과**: `written=5`(4242·4461·4462·4481·4485) → 재실행 `written=0`,
  `already_marked=9`(멱등 확인). **주문 4485 의 추가결제 6건 `1,610,780원` 그대로 보존 확인**
  (같은 파일 검증 절).
- **운영 백필 실행 여부·운영 복구 건수 — `미상(근거 없음)`.** 원장은 스테이징 결과만 적는다.
- 잃은 `naver` 원본 참조가 백필로 되살아나는지는 원장이 말하지 않는다 — `미상(근거 없음)`.

## 6. 구조 변경

- `promotion._stamp_source_marker(order)` — **비어 있을 때만** 찍는다. 다른 채널 표식을
  네이버로 바꾸면 그 주문의 출처가 거짓이 되기 때문이다
  (`docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md` 구현 절).
- `_OPERATIONAL_TOP_LEVEL_KEYS` 에 `source`·`naver`·`pricing` 추가
  (`foms/api/erp_orders_structured.py:277-279`). **폼이 값을 보내면 여전히 그 값이 이긴다** —
  보존이 편집을 막지 않는다(회귀로 못박음).
- 회귀 **9건** 신설(폼 보존 6 + 붙이기 각인 3). **둘 다 red 확인**: 보존 목록에서 3키를 빼면 4건 red,
  `_stamp_source_marker` 호출을 빼면 2건 red. `APP_OK` 성공(같은 파일 검증 절).
- 2026-08-28 후속: 붙이기는 출처(`source`)가 아니라 **`naver_linked`** 를 켠다 — 출처와 렌더 게이트는
  뜻이 다르고, ERP 에 직접 등록한 주문(예약금 건)에 재결제를 붙였다고 출처가 네이버가 되지는
  않기 때문이다(`foms/api/erp_orders_structured.py:272-276`). 그 키도 같은 보존 목록에 등재됐다(`:280`).

## 7. 재발 여부·남은 것

- 같은 사고의 **재발 기록은 없다**.
- 다만 **재발 경로가 코드에 명시돼 있다**: `naver_linked` 가 보존 목록에서 빠지면 "편집 한 번에
  도크가 닫힌다 — 2026-08-24 사고와 정확히 같은 재발 경로다"
  (`foms/api/erp_orders_structured.py:274-276`).
- 남은 것 ①: **보존 목록은 사람이 유지하는 allowlist 다.** 검토 보고서가 R1 근거로 이 자리를
  직접 지목한다 — "`foms/api/erp_orders_structured.py:231-235`(보존 목록을 사람이 유지)"
  (`docs/plans/2026-09-06-foms-system-review-report.md:37`). 새 서버 소유 키가 생길 때마다 등재를
  잊으면 같은 무음 소실이 다시 난다.
- 남은 것 ②: 소실이 **로그를 남기지 않는다**는 성질은 그대로다. 보존 목록에 든 키는 지켜지지만,
  목록 밖 키가 빠져도 strip 경고가 나지 않는다(`foms/api/erp_orders_structured.py:262-263`).
- 남은 것 ③: 검토 보고서는 이 사고를 "두 달 안 같은 유형 사고 4건" 의 하나로 세었다
  (`docs/plans/2026-09-06-foms-system-review-report.md:37`, `:107`).

## 8. 근거 앵커

- `foms/api/erp_orders_structured.py:231` — `_OPERATIONAL_TOP_LEVEL_KEYS` 정의 시작
- `foms/api/erp_orders_structured.py:260-263` — "보존 목록에 없으면 주문을 한 번 열어 저장하는 것만으로 조용히 사라진다" · allowlist 가 빠진 옛 키를 되살리지 않음 · strip 목록에도 안 남아 로그 없음
- `foms/api/erp_orders_structured.py:264-265` — 2026-08-24 스테이징 실측 9/9 일치(편집 흔적 5건 전부 `source` 상실 · 편집 없던 4건 전부 잔존)
- `foms/api/erp_orders_structured.py:266-271` — `source`·`naver`·`pricing` 각각의 손실 비용(주문 4485: 1,610,780원 6건)
- `foms/api/erp_orders_structured.py:272-276` — `naver_linked` 와 "2026-08-24 사고와 정확히 같은 재발 경로"
- `foms/api/erp_orders_structured.py:277-280` — 보존 목록에 등재된 네 키
- `docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md:8-11` — 신고와 사용자 관측 정정
- `docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md:15-24` — 도크 렌더 게이트와 `pricing` 유일 소비자
- `docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md:26-33` — 원인 두 겹
- `docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md:37-48` — 로컬 재현 출력 · 9/9 · 1,610,780원
- `docs/plans/2026-08-24-naver-attach-invisible-result-ledger.md` Task 표·구현·검증 절 — 백필 결과(`written=5`→`0`, `already_marked=9`)·회귀 9건 red 확인·`A4 PENDING`
- `docs/plans/2026-09-06-foms-system-review-report.md:37` · `:107` — R1·R8, 보존 목록 수동 유지와 같은 유형 4건 판정
