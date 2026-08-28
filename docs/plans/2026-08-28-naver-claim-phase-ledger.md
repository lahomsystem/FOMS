# 네이버 클레임 단계 축 — 진행 원장 (2026-08-28)

스펙 `docs/specs/2026-08-28-naver-claim-phase-labeling_SPEC.md`.
격리 워크트리 `c:\tmp\nvclaim` (브랜치 `session/naver-claim-phase`) ·
승격 트리 `c:\tmp\nvprom` (브랜치 `promote/naver-claim-phase`).

## 완료

| # | 항목 | 상태 |
|---|---|---|
| T1 | 조사(4에이전트 병렬 + CEO 총괄) — 데이터는 이미 있고 읽는 쪽 결함 | DONE |
| T2 | 스펙 작성 + 사용자 승인(범위·색·시점 4문항) | DONE |
| T3 | 구현 — `CLAIM_PHASES` + 소비자 2벌 교체 + 폐기 라우트 이중 가드 + 노랑 토큰 + 핀 범프 | DONE `2b9c6efd` |
| T4 | 음성 대조군 테스트 12개 | DONE |
| T5 | 검증 — `APP_OK` · `-k naver` 920 · contracts+domains 5356 · smoke exit 0 | DONE |
| T6 | deploy 푸시 + CI 4/4 green(커밋별 전 워크플로 나열 확인) | DONE `2b9c6efd` |
| T7 | 스테이징 실화면 검증(시드 → 확인 → 원상복구) | DONE |
| T8 | 운영 승격 cherry-pick + 승격 트리 검증 | 진행 중 `cbdd0404` |
| T9 | 반품 프로세스 점검 | DONE — 아래 |

## 운영 실데이터 (읽기 전용, 2026-08-28)

```
productOrderStatus / claimStatus      건수
PAYED              / (없음)            68
DELIVERING         / (없음)            51
RETURNED           / RETURN_DONE       25
CANCELED           / CANCEL_DONE       15
PAYED              / CANCEL_REQUEST     1   ← link 79 / 주문 #4998
```

`order.claimStatus` 보유 0 · 블록만 있고 `productOrder.claimStatus` 없는 행 0 → 폴백 불필요.
`triage_state.claim_sync.last_status` 와 raw 전수 일치(드리프트 0).

**식별자 정정**: 최초 지목된 `link_id=159` 는 무관하다. 159·160 은 같은 수취인의 **별건 신규
주문**(클레임 키 자체 없음). 실제 대상은 **link 79 / 주문 #4998 / 주문번호
`2026082525083121`** — 승인일·완료일·`completedClaims` 전부 부재, 잔여결제금액 558,400원 생존.

## T9 반품 프로세스 점검 — 미해결 결함 (원장 보존)

취소에서 고친 결함의 **반품 복사본은 없다.** 반품 5종이 전부 `CLAIM_PHASES`·
`CLAIM_STATUS_LABELS`·`BLOCKING_CLAIM_STATUSES` 에 등재돼 있고 두 판정 지점이 공통
`extract_claim` 을 쓰므로 `2b9c6efd` 가 반품도 함께 닫았다. `claimStatus` 를 truthiness 로만
보는 곳은 저장소에 **0곳** 남았다(전수 grep).

`COLLECT_DONE → in_progress` 배정은 옳다 — 네이버 공식 답변 #3106("판매자 반품 요청 후 자동
완료 처리 안 됨") + `RETURN_REJECT` 존재(수거 후에도 거부 가능) + 운영 실측상 `RETURN_DONE`
만 잔여수량·잔여금액 0.

### 남은 결함 (이번 커밋 범위 밖 — 별건)

| # | 결함 | 자리 | 심각도 | 오늘 노출 |
|---|---|---|---|---|
| R-3 ✅ | **우리가 낸 반품 접수가 5분 뒤 긴급 알림으로 되돌아온다.** `_is_our_cancel` 이 `fulfillment.canceled_at` 만 보는데 반품 표식은 `triage_state['return']['requested_at']` 이다. 취소는 억제하고 반품은 안 한다 | `claim_watch.py:202-219`·`:421` vs `fulfillment.py:1013` | **상** | **아직 0 — 다음 첫 클릭에서 발생.** 반품 버튼은 운영 활성(PR #171) |
| R-2 ✅ | **`EXCHANGE_DONE` 이 폐기(soft delete) 버튼을 연다.** `CANCEL_REJECT` 와 같은 부류인데 이번 수정이 취소·반품만 봤다. 라우트 이중 가드도 `phase != done` 뿐이라 통과 | `mapping.py` `CLAIM_PHASES` · `ghost_orders.py` · `naver_ingest.py:2745` | **상** | 없음(교환 실데이터 0건) |
| R-4 | 교환 클레임이 불가역 3종을 안 막는다. `request_return` 주석은 "취소·반품·**교환**을 막는다"인데 `EXCHANGE_*` 가 `BLOCKING` 에 없다 | `mapping.py:362-365` · `fulfillment.py:294-295` | 중~상 | 없음 |
| R-5 ✅ | **끝난 반품을 pane 이 네 가지로 틀리게 말한다.** (초고의 "줄이 통째로 안 뜬다"는 실데이터로 반증됨 — 필요한 필드 3개가 25/25 전건 보유라 줄은 뜬다. 결함은 사라진 게 아니라 모양이 바뀌었다.) 운영 25건이 지금 이렇게 그려진다: `반품 진행 | 수거 완료 … | 회수 방법 RETURN_INDIVIDUAL | 환불 예정 … | 환불 대기 환불처리완료` — ① 제목 `반품 진행` 고정(`pane:172`) ② **`환불 대기 환불처리완료` 자기모순**(`:183-184`, 값이 단일값이라 25건 예외 0) ③ `환불 예정` 미래형(`:180`) ④ `RETURN_INDIVIDUAL` 영문 상수(`:177`, `collectDeliveryMethod` 라벨 맵 부재). 넷을 한 번에 푸는 `returnCompletedDate` 를 읽는 코드는 **0곳**(전수 grep 확인) | `mapping.py` return axis · `pane:170-187` | 중 | **있음 — 운영 25건, 예외 0. 유일하게 오늘 사람이 만나는 것** |
| R-1 ✅ | 수거 단계 반품을 **"취소"**라 표기. `label.startswith("RETURN")` 인데 `COLLECTING`/`COLLECT_DONE` 은 `RETURN` 으로 시작하지 않는다. 정답 축 `claimType` 을 버린다 | `ghost_orders.py` `claim_kind` | 중 | 없음(표본 0) |
| R-6 ✅ | `exchange` 블록 값이 `반품 진행` 이름으로 뜬다 — `cancel` 을 뺀 이유(50건 사고)와 같은 누출이 교환 방향으로 남음 | `mapping.py:283` · `pane:172` | 하 | 없음 |
| R-7 | 얇은 스냅샷 투영이 `return`/`returnInfo`/`exchange`/`delivery` 를 버린다 — docstring 은 "술어가 아니라 입력만 얇게 한다"는데 `_claim_blocks` 가 그 블록을 읽으므로 입력을 얇게 한 것이 곧 술어 변경 | `naver_ingest.py:781-793` | 하(잠복) | 없음 |
| R-8 | 라벨 truthiness 가 "거부"를 진행 중 클레임으로 센다 — 도크가 "반품 거부 건이 있어 환불액은 아직 빠지지 않았습니다"(환불이 영영 없는데) | `dock.py:498-503` · `erp-naver-dock.js:297` | 하 | 없음 |

### T8(판매자 반품 접수) 배선 — 설계서 기록이 낡았다

"`request_return` 호출자 테스트 밖 0곳"은 더 이상 사실이 아니다. 버튼 → JS →
`naver_ingest.py:2826-2882` → `enqueue_naver_return` → `tasks.py:372` → `request_return`
체인이 완결됐고 **운영 승격 완료(PR #171)**. 그래서 R-3 이 급하다.

`_claim_guard` 를 `blocking` 대신 `phase in (requested, in_progress, done)` 로 바꾸면 R-4 가
한 번에 닫히고 거부만 통과한다.

### 테스트 사각

유령 목록 테스트 입력 10건이 전부 `done` 양성이고, `2b9c6efd` 가 넣은 음성 대조군 6건도
전부 취소다. **반품 단계는 유령 경로에 한 번도 안 흘러 본다.** 자기 접수 알림 억제 테스트도
취소판만 있다. 필요한 음성 대조군 10개는 `_investigation/E_return_process.md` 에 있다.

## 규율 기록

- 스테이징 시드 검증: DB 직접 INSERT 로 만든 주문은 `created_at` 이 NULL 이라
  후보 창(`Order.created_at >= since`)에서 조용히 빠진다. 관계 표가 안 떠서 5분 헤맸다.
- `ci_watch --quick` 이 exit 0 을 냈지만 `gh run list --commit` 으로 보면 4개 전부
  `in_progress` 였다. CI green 판정은 커밋별 전 워크플로 나열로만 한다.

## 처리 현황 (2026-08-28 갱신)

| # | 상태 | 어디서 |
|---|---|---|
| R-5 | **닫힘** — deploy `60d152de`·`183e54f6`, 운영 승격 PR #181(검사 4/4 green, 머지 대기) | 원장 `2026-08-28-naver-return-done-labeling-ledger.md` |
| R-6 | **닫힘**(R-5 와 같은 줄에서) — 반품 축 줄 제목이 `claimType` 을 따른다 | 〃 |
| R-3 | **닫힘** — 억제 판정이 표식 두 자리를 **종류별로** 본다 | 아래 |
| R-2 | **닫힘** — 유령 모집단·후보표가 종류를 본다(교환 제외) | 아래 |
| R-1 | **닫힘**(R-2 와 같은 줄에서) — 종류 판정이 접두어 대신 `claimType` | 아래 |
| R-4 | 미착수 — 교환 클레임이 불가역 3종을 안 막는다(`BLOCKING_CLAIM_STATUSES`) | — |
| R-7 | 미착수 — 얇은 스냅샷 투영이 반품·교환·배송 블록을 버린다 | — |
| R-8 | 미착수 — 라벨 truthiness 가 "거부"를 진행 중 클레임으로 센다 | — |

### R-3 — 우리가 낸 클레임은 경보로 돌아오지 않는다

원인은 **표식이 두 자리에 나뉘어 있는데 판정이 한 자리만 읽은 것**이다. 취소는
`triage_state['fulfillment']['canceled_at']`, 반품은 `triage_state['return']['requested_at']`.

- `claim_watch.OUR_CLAIM_MARKERS` 로 두 자리를 한 표에 모으고, `_is_our_cancel` 을
  `_is_our_claim(link, claim)` 으로 바꿨다.
- **종류가 맞을 때만 억제한다.** 표식 하나가 모든 클레임을 덮으면 반품을 한 번 접수한
  링크는 그 뒤 진짜 고객 취소가 나도 영영 조용해진다 — 억제가 사고를 삼키는 쪽으로
  틀리는 것이 이 함수의 유일한 위험이다. 종류를 모르면 억제하지 않는다.
- 집계 키 `self_canceled` → `self_claimed`(반품도 세므로 이름이 사실과 어긋났다).

음성 대조군 4개: 고객이 낸 반품은 알린다 · 반품 표식이 고객 **취소**를 안 삼킨다 ·
취소 표식이 반품을 안 삼킨다 · 억제해도 상태 갱신은 그대로.

### R-2 — 교환은 유령이 아니다

`mapping.MONEY_BACK_CLAIM_KINDS = {CANCEL, RETURN}` 을 세우고 두 소비처가 **같은 술어**를 쓴다.

- `ghost_orders`: 모집단 게이트가 단계 + **종류**를 본다(`GHOST_CLAIM_KINDS`).
  교환은 목록에 안 들어가므로 폐기 라우트도 "목록에 없습니다"로 거절한다(이중 가드 유지).
- `order_candidates`: `EXCHANGE_DONE` 을 `canceled` 로 세어 `전부 취소 완료` 라 적던 것을
  `살아 있음` 으로 고쳤다.
- 덤으로 R-1 이 닫혔다 — 종류 판정이 `label.startswith("RETURN")` 이라 `COLLECTING`·
  `COLLECT_DONE` 이 **취소**로 떨어졌다. 이제 `mapping.claim_kind`(claimType 우선, 없으면
  상태 이름)가 SSOT 다.

**실데이터 0건**이다(운영·스테이징 `%EXCHANGE%` 0). 그래서 테스트가 유일한 관문이고,
음성 대조군(취소·반품은 여전히 유령)을 같이 넣었다.
