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
| R-4 ✅ | 교환 클레임이 불가역 3종을 안 막는다. `request_return` 주석은 "취소·반품·**교환**을 막는다"인데 `EXCHANGE_*` 가 `BLOCKING` 에 없다 | `mapping.py:362-365` · `fulfillment.py:294-295` | 중~상 | 없음 |
| R-5 ✅ | **끝난 반품을 pane 이 네 가지로 틀리게 말한다.** (초고의 "줄이 통째로 안 뜬다"는 실데이터로 반증됨 — 필요한 필드 3개가 25/25 전건 보유라 줄은 뜬다. 결함은 사라진 게 아니라 모양이 바뀌었다.) 운영 25건이 지금 이렇게 그려진다: `반품 진행 | 수거 완료 … | 회수 방법 RETURN_INDIVIDUAL | 환불 예정 … | 환불 대기 환불처리완료` — ① 제목 `반품 진행` 고정(`pane:172`) ② **`환불 대기 환불처리완료` 자기모순**(`:183-184`, 값이 단일값이라 25건 예외 0) ③ `환불 예정` 미래형(`:180`) ④ `RETURN_INDIVIDUAL` 영문 상수(`:177`, `collectDeliveryMethod` 라벨 맵 부재). 넷을 한 번에 푸는 `returnCompletedDate` 를 읽는 코드는 **0곳**(전수 grep 확인) | `mapping.py` return axis · `pane:170-187` | 중 | **있음 — 운영 25건, 예외 0. 유일하게 오늘 사람이 만나는 것** |
| R-1 ✅ | 수거 단계 반품을 **"취소"**라 표기. `label.startswith("RETURN")` 인데 `COLLECTING`/`COLLECT_DONE` 은 `RETURN` 으로 시작하지 않는다. 정답 축 `claimType` 을 버린다 | `ghost_orders.py` `claim_kind` | 중 | 없음(표본 0) |
| R-6 ✅ | `exchange` 블록 값이 `반품 진행` 이름으로 뜬다 — `cancel` 을 뺀 이유(50건 사고)와 같은 누출이 교환 방향으로 남음 | `mapping.py:283` · `pane:172` | 하 | 없음 |
| R-7 ✅ | 얇은 스냅샷 투영이 `return`/`returnInfo`/`exchange`/`delivery` 를 버린다 — docstring 은 "술어가 아니라 입력만 얇게 한다"는데 `_claim_blocks` 가 그 블록을 읽으므로 입력을 얇게 한 것이 곧 술어 변경 | `naver_ingest.py:781-793` | 하(잠복) | 없음 |
| R-8 ✅ | 라벨 truthiness 가 "거부"를 진행 중 클레임으로 센다 — 도크가 "반품 거부 건이 있어 환불액은 아직 빠지지 않았습니다"(환불이 영영 없는데) | `dock.py:498-503` · `erp-naver-dock.js:297` | 하 | 없음 |

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
| R-5 | **닫힘 + 운영 반영** — PR #183 `07a0e119`, 운영 실화면 8/8 확인 | 원장 `2026-08-28-naver-return-done-labeling-ledger.md` |
| R-6 | **닫힘**(R-5 와 같은 줄에서) — 반품 축 줄 제목이 `claimType` 을 따른다 | 〃 |
| R-3 | **닫힘 + 운영 반영**(PR #183) — 억제 판정이 표식 두 자리를 **종류별로** 본다 | 아래 |
| R-2 | **닫힘 + 운영 반영**(PR #183) — 유령 모집단·후보표가 종류를 본다(교환 제외) | 아래 |
| R-1 | **닫힘**(R-2 와 같은 줄에서) — 종류 판정이 접두어 대신 `claimType` | 아래 |
| R-4 | **닫힘 + 운영 반영** — PR #186 `2ad638c4` | 아래 |
| R-7 | **닫힘** — 투영 키를 `mapping` 에서 파생(deploy `a1502a65`, PG 레인 green) | — |
| R-8 | **닫힘** — 세 화면이 `is_money_back_claim` 을 본다(deploy) | 아래 |

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

## 운영 승격 (2026-08-28)

PR #183 `07a0e119` — R-5·R-6·R-3·R-2·R-1 을 **한 PR 로** 올렸다. 처음 만든 PR #181(R-5·R-6)은
닫았다: 후속 수정이 같은 파일을 건드려 따로 올리면 순서 의존이 생기고, 그 사이 운영이
PR #182 로 움직여 base 가 낡았다(현재 운영 tip 위로 재배열 후 전 스위트 재실행).

- 재배열 후 승격 트리 검증: `APP_OK` · `-k naver` 956 · `tests/contracts` 65 ·
  `tests/domains` 5266 · `pre_push_smoke` exit 0 · PR 검사 4/4 green.
- force push 는 가드가 막는다(정상) → 새 브랜치 `promote/naver-claim-r5-r3-r2` 로.
- 운영에 **문서는 안 올렸다** — `AI_STATUS`·이 원장은 계보가 deploy 쪽이라 델타만 가면
  반쪽 문서가 된다. 코드만 승격.
- 운영 실화면: `RETURN_DONE` 8건 pane 직접 열람, 8/8 `반품 완료` 로 정상. 옛 문구 4종 0건.
  `claude_master` 는 해제→열람→**재잠금** 완료(`is_active=false` 확인).

R-3·R-2 는 실화면 확인이 불가능하다 — 교환 실데이터 0건, 반품 자기표식 0건. 만들려면 실제
네이버에 반품을 접수해야 하는데 불가역이라 하지 않았다. 테스트가 유일한 관문이다.

### R-4 — 불가역 게이트와 '주문 만들기' 게이트를 가른다

`_claim_guard` 가 `claim["blocking"]` 을 봤는데 그 집합에 `EXCHANGE_*` 가 없어서, 교환이 도는
집에 **불가역 반품 접수**가 그대로 나갔다. `request_return` 은 주석에 "이미 클레임(취소·반품·
교환)이 도는 집에 반품을 또 걸지 않는다"고 적어 두고 지키지 않았다. 같은 구멍이 발주확인·
발송처리·취소에도 있었다.

`EXCHANGE_*` 를 `BLOCKING_CLAIM_STATUSES` 에 넣는 것은 **오답**이다 — 그 집합은 "주문을
만들면 안 되는가"라, 넣으면 교환 건이 주문 만들기에서 막힌다. 교환은 고객이 대체품을
받으므로 ERP 주문이 **있어야** 한다. 그래서 축을 갈랐다:

`mapping.blocks_irreversible(claim)` — 규칙 둘.

1. **진행 중인 클레임은 종류 불문 막는다**(불가역 호출 앞에서는 안전한 쪽으로).
2. **끝난 클레임은 돈이 되돌아간 종류만 막는다.** 교환 완료는 대체품 발송이 남아 있을 수
   있어 막지 않는다 — 막으면 보낼 길이 없어진다.

기존 9종(`BLOCKING_CLAIM_STATUSES`) 판정은 **한 개도 안 바뀐다**(계약 테스트로 잠갔다).
바뀌는 것은 `EXCHANGE_REQUEST` 가 이제 막힌다는 것 하나다.

음성 대조군 4개: 교환 **완료**는 안 막는다 · 거부 3종·보류·모르는 상태는 안 막는다 ·
기존 9종은 그대로 막는다 · 클레임 없는 집은 통과한다.

### R-4 운영 승격 (PR #186 `2ad638c4`)

승격 도중 운영이 PR #185 로 움직였고 **그쪽도 `fulfillment.py` 를 건드렸다** — 낡은 base 로
올린 브랜치를 지우고 현재 운영 tip(`b9b7bebc`) 위로 재배열한 뒤 전 스위트를 다시 돌렸다
(`-k naver` 992 · contracts 65 · domains 5266 · smoke exit 0 · PR 검사 4/4 green).

**같은 함정을 이 세션에서 두 번 만났다**(PR #183 때는 #182). 운영 승격은 하루가 아니라
**한 시간이면 낡는다** — 승격 트리에서 `git fetch` 후 `git diff <내base> origin/production`
으로 **내가 건드리는 파일이 겹치는지** 보고, 겹치면 재배열·재검증한다.

R-4 는 화면 변화가 없어 실화면 확인 대상이 아니다(교환 실데이터 0건). 운영 배포 후
`/login` 200 으로 부팅만 확인했다.

### R-8 — 거부된 클레임을 진행 중으로 세지 않는다

세 화면이 전부 **라벨 존재 여부**로 분기했다. `RETURN_REJECT`("반품 거부")면 환불이 영영
없는데 도크는 "환불액은 아직 빠지지 않은 금액입니다"라고 말하고, ⚠ 경고를 살아 있는 주문에
붙이고, 목록은 빨강 배지를 달았다.

`mapping.is_money_back_claim(claim)` 신설 — **돈이 되돌아가는가**. 취소·반품의 요청·처리중·
완료가 참이고, 거부 3종·교환·모르는 상태는 거짓이다. `blocks_irreversible` 과는 다른 질문이다
(그쪽은 불가역 호출 게이트라 진행 중 교환도 막는다).

- `dock._deposit_note`: 돈이 되돌아가는 클레임일 때만 환불 문장을 붙인다.
- `dock` payload 에 `claim_money_back` 을 싣고 `erp-naver-dock.js` 가 그것으로 ⚠ 와 빨강을
  가른다. 거부 건은 `--settled` 로 회색이 되고 **사실은 그대로 남는다**.
- 목록·상세 배지 4곳(`naver_ingest`·`naver_triage`·`naver_workbench` ×2·`workbench_detail`)은
  `claim_blocking` 일 때만 빨강, 아니면 중립.
- 자산 핀 `?v=20260827d` → `20260828a`(JS·CSS 동반), 핀 계약 테스트 3곳 갱신.

음성 대조군 5개: 진짜 취소는 여전히 빨강·환불 문장이 붙는다 · 교환은 환불 축이 아니다 ·
모르는 상태는 안 센다 · 완료 취소도 센다(결제액에서 아직 안 빠졌다).

### 이번 세션 범위 밖 (기록)

`tests/visual/test_erp_order_edit_mobile_form.py::test_edit_erp_order_ships_responsive_form_mounts_for_cohort`
가 **deploy tip 에서도 빨갛다**(`erp-share-url` 의 `form-control form-control-sm` 이 모바일 폼
마운트 안에 있다). 내 변경 전후로 같으므로 별건이고, CI 스위트에는 안 들어 있다.
