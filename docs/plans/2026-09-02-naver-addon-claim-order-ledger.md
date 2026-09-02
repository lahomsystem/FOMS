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

## 2차 배 (2026-09-02 같은 날 이어서 완료)

| 항목 | 결과 |
|---|---|
| `clear_failure` 라인 단위화 | 완료 — 범위 축 = **사람이 본 그 줄의 작업**(`failure_action` SSOT 신설). 지운 사유는 `last_error_cleared` 로 **강등 보존**한다. 앵커 실패가 이미 사라졌으면 아무것도 안 지운다(다른 탭 레이스). |
| 상품주문 표 라인별 클레임·반품 칸 | 완료 — `_member_claim_view` 신설(추가 쿼리 0). 네이버 사실과 **우리 접수 여부**를 나란히 낸다(둘이 다른 사실이고 사고는 그 틈이었다). 본품/추가구성상품도 표기(호출 순서를 가르는 축). 표는 `.table-responsive` 로 감쌌다. |
| `dock.py` first-wins | 완료 — `aggregate_claim` 재사용, `claim_code` 를 payload 에 신설. 집계 모집단은 **주문의 링크 전부**(`superseded` 를 빼면 REPAY 가 붙은 이 사고 모양에서 반품이 모집단 밖으로 나간다). `claim_money_back` 을 라벨과 짝으로 바꿨다. |

**버튼 잠금(1차 T7)은 유지한다.** 좁히기와 잠금이 막는 손실이 다르다 — 좁히기는 *형제의 안 본 실패*를 막고,
잠금은 *사람이 보고 누른 바로 그 줄*을 막는다. 황민철 집은 실패가 하나뿐이라 좁히기만으로는 아무것도 못 막는다.
T3(실패 라인 `return` 축 기록)이 배포되기 전까지 잠금이 마지막 문이다.

### 아직 남은 것
- T3 실패 라인 `return` 축 기록 — 이게 들어가야 T7 버튼 잠금을 뗄 수 있다.
- `_group_queue` 의 `shipping_due` first-wins (이력 쪽은 `min()` — 두 화면이 갈릴 수 있다).
- `.wb-cmp { min-width: … }` — 좁은 화면에서 표가 제 폭을 지키게(지금은 `text-nowrap` 으로 유도).
- `test_naver_fulfillment.py:611 test_clear_failure_wipes_the_whole_household` 이름이 이제 과장이다(동작은 green).

## T3 완료 (2026-09-02) — 임시 잠금 회수

- `_mark_return_failures` 신설: 반품 접수에 **실패한 라인**도 반품 축에
  `failed_at`/`failed_reason` 을 받는다. `requested_at` 은 건드리지 않는다 —
  실패는 접수가 아니고 `is_return_pending` 이 그 키로 멱등을 판정하므로, 실패한 라인은
  **다시 보낼 대상으로 남아야** 한다. 다시 보내 성공하면 기록을 지운다.
- `return_failure(link)` 공통 술어 신설. 상품주문 표가 `우리 접수 실패 <시각> + 사유` 로 말한다.
- **`확인함` 임시 잠금 회수.** 잠금의 근거는 "실패의 유일한 흔적이 `last_error` 뿐"이었고,
  T3 기록은 `clear_failure` 가 지우지 않는다. 근거가 사라졌으니 잠금도 사라진다 —
  남겨 두면 실패 띠를 못 닫는 불편만 남는다.
  계약 테스트를 뒤집었다: `..._stays_locked_...` → `..._is_no_longer_locked_once_the_failure_is_recorded`.
  **잠금을 되살리려는 다음 사람은 T3 기록이 살아 있는지부터 확인해야 한다**고 도스트링에 적었다.
- 음성 대조군: `_mark_return_failures` 두 호출만 끄면 기록 계약 2건이 red, 되돌리면 10/10 green.
  (`다시 보내 성공하면 기록 삭제`는 기록이 없으면 지울 것도 없어 양쪽 green — 회귀 방지용.)

### 이제 남은 것
- `_group_queue` 의 `shipping_due` first-wins (이력은 `min()` — 두 화면이 갈릴 수 있다).
- `.wb-cmp { min-width: … }` (지금은 `text-nowrap` 으로 유도).
- `test_naver_fulfillment.py:611` 이름이 과장(`..._wipes_the_whole_household`, 동작은 green).

## 규격 감사 (2026-09-02) — 사고를 일반화해서 훑은 결과

사고 유형: *네이버 문서·FAQ 에만 있고 우리 코드에는 없는 규칙 + 위반이 불가역 + 실패 신호가 약함*.
`failProductOrderInfos[].code` 는 사유 불문 `"9999"` 다(공식 #1233).
**네이버에 질의할 창구는 없다**(사용자 확인) — 문서·FAQ·공식 Discussions 가 전부다.
답이 없는 자리는 추정 대신 **안전측 기본값 + 계약 테스트**로 닫는다.

### 문서만으로 풀린 것 2건
- **배치 배열 순서 = 처리 순서** (공식 #171): "각 주문건의 발송 처리를 **순서대로** 진행하게
  됩니다 … 일부 주문건의 처리가 실패할 경우에는 전체 대상 주문건 중 **일부분은 실제 발송
  처리가 진행될 수 있습니다**." → `dispatch_call_order` 는 작동한다. 동시에 **배치가 절반만
  적용될 수 있다**는 것도 공식 확인이다.
- **`RETURN_INDIVIDUAL` 선택이 옳다** (#2580, 2025-06-25 시행): `RETURN_DESIGNATED`/
  `RETURN_DELIVERY` 를 보내면 API 입력을 무시하고 **상품정보의 택배사가 자동 수거**를 간다.

### 고친 것 5건
| # | 내용 |
|---|---|
| F5 | 불가역 클레임 호출 **재시도 금지**(`_request(retry=False)` × 5경로). 타임아웃은 "안 나갔다"가 아니다. 401 토큰 재발급 1회는 유지(요청이 서버에 안 닿았다). |
| F4 | `request_return(approve=True)` 의 **승인 0건도 실패**. 접수 실패와 승인 실패는 다음 할 일이 달라 사유 문장을 갈랐다. |
| F6 | 취소 사유 게이트를 **endpoint 범례 7종**으로. 읽기 축 귀책 표(18종)는 `READABLE_CLAIM_REASONS` 로 분리. |
| F1 | `beforeClaim` **안전장치**(#3608, 2026-10-28). 판정을 추정으로 바꾸지 않고 **읽는 그릇만** 늘렸다. 얇은 투영에도 등재. |
| F11 | `client.py` 도스트링 정정 — "취소 거부 API 없다"는 사실이 아니다(#2823). 없어서가 아니라 `_claim_guard` 가 막아서 안 한다. |

### 미해결 (운영 실측이 선결)
- **F3 · 상** — 우리가 보낼 수 있는 반품 사유 2종(`INTENT_CHANGED`·`COLOR_AND_SIZE`)이
  **둘 다 구매자 귀책**이고, 흐름도 *C2 는 구매자 귀책 반품에 **자동 반품보류**를 적는다.
  우리는 보류를 안 풀기로 했으므로 → 승인도 거부도 안 열린다. **접수는 나가고 환불은 안
  나가는** 상태가 될 수 있다. 코드 주석의 "운영 25건 보류 0건"은 **읽기 관측**이고 그 25건은
  API 접수분이 아니다. → 가상주문 `CLAUDE-TEST-` 1건으로 접수 직후 `holdbackStatus`·
  `claimDeliveryFeeDemandAmount` 실측이 선결. 그 전에는 접수+승인 원클릭을 기본으로 열지 말 것.
- **F2 · 상** — 판매자센터 FAQ 3880 은 "본상품과 추가구성 상품을 **모두 접수하여**" 처리하라고
  적는데, 우리는 "대상에 든 본품마다 그 본품의 추가상품이 전부 대상 안인가"를 **적극 검사하지
  않는다**. T3 이후 부분 실패가 예외로 오르므로 조용히 성공하지는 않는다.
- F7 `reject_return` 순서(**NOT IN DOCS**) · F8 승인 가능 상태 3종이 관측 기반 ·
  F10 승인·거부가 낡은 스냅샷으로 판정(반품 승인만 재조회) · F12 `productClass` 없는 행 ·
  F13 모양 모르는 200 을 전건 성공으로.
