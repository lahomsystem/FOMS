# NVCLAIM-ORDER-01 진행 원장

설계서: `docs/specs/2026-09-02-naver-addon-claim-order_SPEC.md` (v2, CEO CHANGE 반영)
워크트리: `c:\tmp\foms-s-s0902-084421` / 브랜치 `session/s0902-084421` (base origin/deploy)

## 계약 (두 에이전트 공통)

새 술어 이름과 시그니처를 여기서 못 박는다 — 양쪽이 같은 이름을 쓴다.

```python
# foms/services/integrations/naver_commerce/fulfillment.py
def claim_call_order(links: list[ExternalOrderLink]) -> list[ExternalOrderLink]: ...
def dispatch_call_order(links: list[ExternalOrderLink]) -> list[ExternalOrderLink]: ...
def return_sendable(link: ExternalOrderLink) -> bool: ...
def household_exchange_in_flight(links: list[ExternalOrderLink]) -> bool: ...
```

- `claim_call_order` — 클레임 **요청·승인**: 추가구성상품 먼저, 본품 나중 (안정정렬).
- `dispatch_call_order` — **발주확인·발송처리**: 본품 먼저, 추가구성상품 나중 (안정정렬).
- `return_sendable(link)` = `is_return_pending(link) and not blocks_irreversible(extract_claim(link.raw_snapshot or {}))`
- `household_exchange_in_flight(links)` = 형제 중 **진행 중 교환**이 있는가 (phase requested/in_progress + kind EXCHANGE).

## Task

| T | 내용 | 파일 | 담당 | 상태 |
|---|---|---|---|---|
| T1 | `claim_call_order` 신설 + 클레임 5경로 적용 | fulfillment.py | A | DONE |
| T2 | `dispatch_call_order` 신설 + confirm·dispatch 적용 | fulfillment.py | A | DONE |
| T3 | 부분 실패 = 실패 (4곳) | fulfillment.py | A | DONE |
| T4 | `_claim_guard` scope 인자 + 교환 예외 + `return_sendable` 신설 | fulfillment.py | A | DONE |
| T5 | 집 배지 first-wins → 부분/전부 집계 | naver_ingest.py | B | DONE |
| T6 | `return_sendable` 기반 버튼 술어 재작성 | pane.html + naver_ingest.py | B | DONE |
| T7 | 실패 남은 집은 `확인함` 비활성 | pane/workbench + naver_ingest.py | B | DONE |
| T8 | 계약 테스트 6종 | tests/ | 주 세션 | DONE |
| T9 | DECISIONS.md 두 방향 기록 + 설계서 확정 | docs/ | 주 세션 | DONE |
| T0 | 운영 복구(본품 반품 접수+승인) | — | 사용자 승인 후 | BLOCKED |

## 2차 배 (이번 제외)
- 실패 라인 `return` 축 기록(`failed_at`) — `last_error` 가 이미 사유를 담는다.
- `_member_rows` 라인별 클레임 칸.
- `clear_failure` 라인 단위화 (1차는 T7 버튼 비활성으로 버틴다).
- `reject_return:1384` 부분실패 — `return_reject_enabled` 게이트 뒤.

## 알려진 한계 (설계서에 명시할 것)
- `productClass` 가 없는 옛 원본 집은 전부 본품 판정 → 정렬이 무의미하고 `id.asc` 로 되돌아간다.
- `is_return_pending` 은 판매자센터 수동 처리분을 모른다(우리 표식으로만 멱등 판정).
- 교환 예외는 운영 표본 0이라 **테스트로만** 검증된다 → 안전측(막는 쪽)으로 둔다.

## 완료 기록 (2026-09-02)

- T1~T4 `fulfillment.py` / T5~T7 `naver_ingest.py`+`order_candidates.py`+템플릿 2벌 — 구현·검수 완료.
- **주 세션 추가 수정 1건**: 라인 가드가 막힌 형제 하나 때문에 멀쩡한 라인까지 막으면 RC3 이
  한 단계 아래에서 되살아난다. `request_return` 이 막힌 라인을 **사유를 남기고 빼되 실패로
  세어 예외를 올리도록** 변경(조용한 축소 아님). 모달 재진술도 `return_sendable_count` 로
  맞췄다(과대 진술 금지, 계약 §0-2).
- **기존 테스트 1건 뒤집음**: `test_naver_return_wiring.py` 의
  `test_return_button_is_absent_while_a_claim_is_in_flight`
  → `test_return_button_is_shown_disabled_while_a_claim_is_in_flight`.
  "버튼을 아예 안 낸다"가 RC3 그 자체였다.
- **브리프가 원장을 이겼다**: `reject_return` 부분실패도 이번 배에 포함(1줄, 같은 결함).
- 검증: `tests/services/integrations` 1389 passed · `tests/contracts`+`tests/harness` 457 passed ·
  `tests/domains -k "naver or workbench or claim"` 123 passed · `import app` APP_OK ·
  **음성 대조군**(수정 전 코드에서 신규 계약 테스트 5/6 red).

## 남은 것
- T0 운영 복구(본품 `2026082754601551` 반품 접수+승인) — **사용자 승인 대기**.
- 2차 배: `clear_failure` 라인 단위화 · `dock.py:833` first-wins · `_member_rows` 라인별 클레임 칸 ·
  `_group_queue` 의 `shipping_due` first-wins(이력은 `min()` — 두 화면이 갈릴 수 있다).
