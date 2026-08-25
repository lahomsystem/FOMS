# 다음 세션 프롬프트 — 재결제 정리 R-3 (2026-08-25 R-1·R-2 완료 후)

아래를 그대로 붙여 넣으면 된다.

---

**C 네이버 — 재결제 정리 R-3.
작업 위치 `c:\tmp\nvfix` (브랜치 `tmp/naver-fix-20260825`)

설계부터 읽어라:
`docs/specs/2026-08-25-naver-repay-reconcile_SPEC.md` (§2.5 개정이 핵심 — 네이버 직접취소를 뺐다)
목업: `docs/design/mockups/naver-repay-reconcile.html` (2판)

## 지금 상태

**R-1·R-2 는 deploy 에 올라가 CI green 이고 스테이징 실화면 확인까지 끝났다.**
R-3 만 남았다. 운영에는 아직 안 올라갔다(R-1·R-2 미승격).

| 단계 | 무엇 | 상태 |
|---|---|---|
| **R-1** | 후보 표 판정 근거 2열(네이버 옛 결제 상태 · 금액 견주기) | **완료** `7daaa4fd` |
| **R-2** | 유령 주문 띠 + `주문 취소 처리`(soft delete) | **완료** `7ac7abb8` · 스테이징 3건 확인 |
| **R-3** | 정리 계획 — 붙이기 + ERP 처리를 **한 트랜잭션**으로 | **PENDING** |
| ~~R-4~~ | ~~네이버 판매자 직접취소~~ | **사라짐**(2026-08-25 결정) |

## R-3 이 만들 것

상세 pane 의 `관계` 섹션에서 후보 행을 고르면 뜨는 **정리 계획 카드**다.

```
1. 붙이기        새 집 -> 주문 #N (relation=REPAY|ADDON)
2. ERP 기존 주문  (a) 승계: 주문 유지 — 예약금에 넣을 금액을 **안내만** 한다
                 (b) 취소 처리: soft delete(휴지통)
   -- 1 과 2 는 같은 트랜잭션이다: 둘 다 되거나 둘 다 안 된다 --
i. 네이버 옛 결제  상태만 표시. 살아 있으면 "네이버에서 처리하세요" + 판매자센터 링크
```

**확정된 결정 (다시 묻지 마라)**

- **네이버로 나가는 호출은 이 흐름에 없다.** 판매자 직접취소는 뺐다(불가역이라).
  워크벤치의 기존 `취소처리` 버튼은 그대로 두되 이 흐름이 자동으로 누르지 않는다.
- **예약금은 자동 반영하지 않는다.** 화면이 "예약금(선금)에 넣을 금액: N원" 을 말하고
  입력은 사람이 한다. 정본은 `structured_data['payment']['deposit']`
  (`erp_display.erp_deposit_amount_from_structured`, 화면 `#erp-deposit-amount`).
  셈은 문장으로 알려 준다: **재결제는 바꾸고, 추가결제는 더한다.**
  출고가·품목은 어느 쪽도 건드리지 않는다(잔금 = 출고가 − 예약금 공식이 따라온다).
- **취소 처리는 soft delete** 다. 확인창 1회면 충분하다(4종 세트 모달은 불가역 전용).
  **접수 단계에서만** 열린다 — 실측 이후는 잠근다(서버도 거절한다).

## 재사용할 것

| 조각 | 위치 |
|---|---|
| 붙이기(집 단위·멱등·이력 1건) | `promotion.attach_link_to_order` — `(붙인 수, 주문 id, 바뀌었는가)` 3튜플 |
| soft delete | `foms/services/orders/soft_delete.py` |
| 유령 판정·취소 처리 라우트 | `foms/services/integrations/naver_commerce/ghost_orders.py`, `naver_ingest_ghost_discard` |
| 판정 근거 | `order_candidates.find_order_candidates` (R-1 에서 2열 추가됨) |
| 현재 예약금 읽기 | `erp_display.erp_deposit_amount_from_structured` |

## 함정 (이번 세션에서 실제로 걸린 것)

- **신규 mutation 라우트는 계약 4종**을 등재해야 한다: `foms_write_guard_manifest.json` ·
  `foms_order_mutation_policy_manifest.json` · `audit_message_display.py` 라벨 ·
  audit coverage 인벤토리. **pre_push_smoke 는 뒤 둘을 안 본다** — CI 에서만 red 난다.
- **인벤토리 2종은 재생성**해야 한다(새 라우트·`except` 추가 시):
  `python tools/harness/failopen_scan.py` · `python tools/harness/audit_coverage_scan.py`.
- 기존 JS/CSS 를 고치면 **`?v` 핀 범프 필수**. 지금 핀은 `20260825d`.
  참조처: `templates/admin/naver_workbench.html` 2곳 + 계약 테스트
  `test_naver_workbench_async_result.py`.
- 테스트에서 **요청 뒤 ORM 인스턴스는 detach 된다** — `order.id` 를 요청 전에 int 로 뽑아라.
- `tests/services/integrations/` 는 모듈 레벨 `from db import db_session` + `app` 픽스처
  (스키마 생성)를 쓴다. `db_session` 픽스처는 없다.
- **작업 디렉토리가 조용히 `C:\DEV\FOMS` 로 돌아간다.** git 명령 전에 `pwd` 를 확인해라.
- 스테이징 워크벤치 코호트는 `38`(upperkill)뿐이다. `claude_master`(58)로 화면을 보려면
  잠시 `38,58` 로 열고 **끝나면 원복**한다(이번 세션에서 그렇게 했다).

## 검증 기준

- `tests/services/integrations` 전량 green (지금 640 passed)
- `pre_push_smoke.ps1` exit 0 (`PYTHONIOENCODING` 설정하지 마라 — 가짜 red 5건)
- deploy CI **전 워크플로 나열**로 green 확인(`ci_watch` 는 1개만 본다)
- 스테이징 실화면: 후보 행 → 정리 카드 → 실행 → 붙이기+ERP 가 함께 반영, 실패 시 둘 다 미반영

## 남은 것 (R-3 밖)

- **R-1·R-2 운영 승격** — 사용자 승인 필요. 오늘 승격한 것은 `099568a2`(sticky·도크·쿠폰)까지다.
- 필드 인벤토리 §3 우선순위 중 사용자가 고른 3건: 취소·반품 사유 원문 ·
  발송처리 결과 시각/상태 · 부분취소 잔여(`remain*`). `docs/guides/NAVER_FIELD_INVENTORY.md`
