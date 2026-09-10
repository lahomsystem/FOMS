# 브리프: 추가결제 건 — 이력 행 '주문 만듦' 배지 제거 + ERP 도크 예약금 설명문 제거 (2026-09-10)

> 사용자 지시(원문, 2026-09-10 10:20 KST, 주문 #5206 김도희 추가 결제 건 화면 캡처 2장):
> 1. "추가 결제 건 > 추가 결제 인데 '주문 만듦' 뱃지는 맞지 않지? 이 뱃지는 빼고 추가결제 뱃지만 남겨"
> 2. "https://lahom-production.up.railway.app/edit/5206?open=erp-order > 추가 결제 금액이 얼마인지만
>    1,290,850원 간단히 표기 해. ⚠ 예약금 칸이 아직 다릅니다 — 지금 (비어 있음) / 시스템이 넣지 않습니다 —
>    예약금(선금) 칸에 직접 입력하세요. 잔금은 출고가 − 예약금으로 따라옵니다. / 지금 값 100,000원에
>    1,290,850원을 더해 1,390,850원으로 고치세요. / 💰 예약금(선금)에 넣을 금액 — 이런 쓸데없는 설명문 삭제 해"
> 3. "멀티 에이전트 사용해서 병렬로 처리하고 CEO 에이전트가 총괄 지휘 해"

작업 트리: `c:/tmp/foms-s-s0908-102606` (브랜치 `session/s0908-102606` = origin/deploy). **git 명령 금지**(커밋·push 는 총괄).

## 0. 캡처가 보여준 것

- 이력 탭 행(네이버 수집 관리 › 전체): `수집 09-10 09:42 | 김도희 | 보테가 슬라이딩 붙박이장 (2건 묶음) | 17 | 1,290,850 |
  FOMS: [주문 만듦] [추가결제 → #5206] · 네이버: [발주확인 완료 2/2] [발송처리 완료 2/2] 09-10 10:11 · ERP발송 | #5206`.
  → 추가결제 집인데 `주문 만듦`(초록) 배지가 같이 뜬다. 추가결제는 주문을 **만든** 것이 아니라 기존 주문에 **붙인** 결제다.
- ERP 주문 화면(`/edit/5206?open=erp-order`) 네이버 도크의 호박색 카드:
  `💰 예약금(선금)에 넣을 금액 / 1,390,850원 / 지금 값 100,000원에 1,290,850원을 더해 1,390,850원으로 고치세요. /
  ⚠ 예약금 칸이 아직 다릅니다 — 지금 (비어 있음) / [📋 1390850] 시스템이 넣지 않습니다 — 예약금(선금) 칸에 직접 입력하세요.
  잔금은 출고가 − 예약금으로 따라옵니다.` 그 아래 행: `본품 — 라홈 보테가 붙박이장 … 본품+옵션 1,290,850원`.
  폼 값: 출고가 1,390,850 · 예약금(선금) 100,000 · 잔금 1,290,850.
  → 사용자가 원하는 것: **추가 결제 금액 1,290,850원 한 줄**. 목표액(1,390,850)·대조 줄·안내 문장·복사 칩 설명 전부 삭제.

## 1. T1 — 이력 행 FOMS 축 배지 (worker A)

### 앵커
- 행 dict 조립: `foms/web/admin/naver_ingest.py:1037-1047` — `foms_state = _history_foms_state(lead, statuses)` →
  `"foms_label": HISTORY_FOMS_LABELS[foms_state]`, `"relation": relation`, `"relation_label"`, `"related_order_id"`.
  `_history_foms_state`: `foms/web/admin/naver_ingest.py:633-660` (failed → review → collected → closed → linked).
  라벨 dict `HISTORY_FOMS_LABELS`: `:87-93` (`linked: "주문 만듦"`, `closed: "주문 접음"`). **이 dict 는 이력 탭 필터 칩과 행이
  한 벌로 쓴다 — 값을 바꾸지 마라**(`naver_workbench.html:934` 주석, 계약 `test_naver_history_status_axes.py`).
- 템플릿: `templates/admin/naver_workbench.html:1044-1066` — `foms_tone` 매핑 → `<span class="wb-st__b wb-st__b--{{ foms_tone }}">{{ row.foms_label }}</span>`
  다음에 `relation == 'NEW'` 면 ghost 배지, `ADDON/REPAY` 면 violet 배지 `{{ row.relation_label }} → #id`.
  **주석 계약(1036-1042)**: "판정은 서버가 한다 — 템플릿에 남는 것은 상태 키 → CSS 클래스 대응뿐".
- 계약 테스트: `tests/services/integrations/test_naver_history_status_axes.py` — `_row(body, order_no)`·`_status_cell(row)`·
  `_tight`·`_hash_numbers` 헬퍼(185-215), 관계 축 테스트 306-385(`test_addon_household_shows_the_relation_badge_and_the_other_order_number`
  등 4건). 픽스처 `_order`·`_link(order_no, product, amount, relation, order_id, sync_status)`·`_open(client)`·`workbench_on`.

### 계약(초안 — CEO 가 확정)
- 규칙: **FOMS 축 상태가 `linked` 이고 관계가 `ADDON`/`REPAY` 이고 `related_order_id` 가 있으면 `주문 만듦` 배지를 내지 않는다.**
  관계 배지(`추가결제 → #id`/`재결제 → #id`)가 이미 "주문이 있다" 를 말한다. 그 외(NEW·related 없음·closed·review·failed·collected)는 그대로.
  특히 `closed`(주문 접음)·`review`·`failed` 는 추가결제 집이어도 **반드시 그대로 보인다** — 신호가 사라지면 안 된다.
- 판정은 **서버**: 행 dict 에 `foms_badge_hidden: bool`(이름 고정) 을 싣고, 템플릿은 `{% if not row.foms_badge_hidden %}` 로만 가른다.
  `foms_state`·`foms_label` 값은 바꾸지 않는다(필터 칩·카운트가 그 축을 쓴다).
- 테스트(추가, 같은 파일): ① ADDON+붙은 주문 → 상태 칸에 `주문 만듦` **없음** + `추가결제` + `#id` 링크 있음 ② REPAY 도 같음
  ③ NEW 행은 `주문 만듦` **있음**(대조군) ④ ADDON 인데 붙은 주문이 삭제된(`closed`) 행은 `주문 접음` **있음**(대조군) ⑤ ADDON 인데 `related_order_id` 없음 → `주문 만듦` 여부는 기존 규칙(`collected`) 그대로.
  기존 4건은 손대지 않고 통과해야 한다.

### 검증 명령(worker A)
```
cd /c/tmp/foms-s-s0908-102606 && python -m pytest tests/services/integrations/test_naver_history_status_axes.py -q -p no:cacheprovider
python -c "import app; print('APP_OK')"
```

## 2. T2 — ERP 도크 예약금 카드 → 추가 결제 금액 한 줄 (worker B)

### 앵커
- JS: `static/js/orders/erp-naver-dock.js`
  - `buildDepositCard()` `:470-505` — `hint.state !== 'differs' || !hint.sentence` 면 null. 카드 = `.naver-dock-deposit` >
    `-hd`('💰 예약금(선금)에 넣을 금액') · `-won`(target_display) · `-say`(sentence) · `-state`(대조 줄, `syncDepositMatch` 가 씀) ·
    `-note` · `-acts`(복사 칩 `data-naver-dock-copy` + `-hint` 안내문).
  - `syncDepositMatch()` `:453-468`, `dockDepositMatch()` `:429-437`, `erpDepositField()` `:444-447`, 호출처 `:772`, `:1234`
    (document 리스너 — `data-erp="deposit_amount"` 입력을 듣는다).
  - 마운트 `:702` (`var deposit = buildDepositCard();` — info 블록과 진행바 사이, 계약 `test_deposit_card_sits_outside_the_scrolling_row_list`).
  - info 블록 `:283-300` — `facts.push(['예약금(선금)', …hint.sentence…])` 줄과 `state.depositHint.state === 'match' ? '' : 'naver-dock-fact-warn'` `:375`.
    **여기도 같은 설명문이다** — 카드만 고치면 문장이 info 줄에 남는다.
  - `state.depositHint = payload.deposit_hint || null` `:1429`.
- CSS: `static/css/orders/erp-naver-dock.css:585-640` (`.naver-dock-deposit*`).
- 서버: `foms/services/integrations/naver_commerce/dock.py:731-800` `_deposit_hint` → 키 `state·current·target·target_display·diff·sentence·copy_value·unknown_count·note·base·live_total`.
  `live_total`(살아 있는 집들의 네이버 결제액 합, 정수 — #5206 은 1,290,850) 은 있지만 **표시 문자열이 없다**. 돈 표기는 서버가 만든다(계약 `formatAmount(hint` 금지, `test_deposit_hint_is_optional_and_card_stands_only_when_values_differ`).
  집 사실(`households`)의 `relation`(`ADDON`/`REPAY`/`NEW`) 으로 낱말을 정한다: 살아 있는 집이 전부 ADDON → `추가 결제`, 전부 REPAY → `재결제`, 섞임 → `네이버 결제`.
- 핀: `templates/orders/partials/erp_order_js.html:35-36` — CSS·JS `?v=20260909a` → **`20260910a`** 로 둘 다(SW staticCacheFirst 라 안 올리면 옛 JS 가 산다).
- 테스트(JS 문자열 계약 — 지금 요구를 못박고 있어 **새 계약으로 고쳐 써야** 한다, 삭제 금지):
  - `tests/services/integrations/test_naver_dock_amounts.py:210-256` — `if (!hint || hint.state !== 'differs' || !hint.sentence) return null;`,
    `el('div', 'naver-dock-deposit-say', hint.sentence)`, `copy.setAttribute('data-naver-dock-copy', hint.copy_value);`,
    `facts.push(['예약금(선금)', ` 순서, `hint.state === 'differs' || !hint.sentence) return '';`, `'naver-dock-fact-warn'`, 마운트 순서, `.naver-dock-deposit` CSS.
  - `tests/services/integrations/test_naver_dock_deposit_match.py:80-105` — `syncDepositMatch` 존재·리스너·`naver-dock-deposit-state` 가 카드에 있어야 한다는 단언(2026-09-09 대조 줄). **사용자 지시로 폐기되는 요구** — 테스트를 "대조 줄·문장·안내문이 카드에 없다" 로 뒤집는다.
  - `tests/services/integrations/test_naver_dock_autofill_wire.py:481` — `buildDepositCard` 안에 `data-naver-dock-target` 없음(유지).
  - `tests/services/integrations/test_naver_dock_deposit_hint.py` — 서버 문장 계약 8건(유지; `live_total_display`·낱말 키 **추가** 테스트만).
  - `tests/domains/test_static_js_syntax.py` — JS 문법.

### 계약(초안 — CEO 가 확정)
- 서버 `_deposit_hint` 에 두 키 **추가**(기존 키·문장은 그대로 — 워크벤치·다른 테스트가 읽는다):
  `"live_total_display": f"{live_total:,}원"`(unknown 이면 빈 문자열), `"relation_label": "추가 결제"|"재결제"|"네이버 결제"`.
- JS 카드: `.naver-dock-deposit` 하나에 `-hd`(= `hint.relation_label`, 예: `추가 결제`) + `-won`(= `hint.live_total_display`). **그 외 노드 없음** —
  문장·대조 줄·note·복사 칩·안내문 전부 삭제. 카드는 `hint.live_total_display` 가 있을 때(금액 모름이 아닐 때) 선다 — state 무관.
  `syncDepositMatch`·`dockDepositMatch`·`erpDepositField`·리스너 호출은 **제거**(읽을 대조 줄이 없다). 폼 불가침 계약(`test_dock_js_never_touches_the_order_form`)은 그대로.
- info 블록의 `예약금(선금)` fact 줄: **삭제**(문장 전달 경로). `추가결제`/`재결제` fact 줄은 그대로.
- CSS: 안 쓰는 `-state`·`-say`·`-note`·`-acts`·`-hint` 규칙 제거, `.naver-dock-deposit`·`-hd`·`-won` 유지(호박색 카드 규격 그대로).
- 테스트를 새 계약으로: 카드 본문에 `naver-dock-deposit-say`·`-state`·`-hint`·`data-naver-dock-copy` 가 **없다**, `hint.relation_label`·`hint.live_total_display` 를 쓴다,
  `formatAmount(hint` 없음, 마운트 위치 불변, `syncDepositMatch` 가 소스에 **없다**. 서버: `live_total_display`·`relation_label` 값 3갈래(ADDON/REPAY/섞임) + unknown 이면 빈 문자열.

### 검증 명령(worker B)
```
cd /c/tmp/foms-s-s0908-102606 && python -m pytest tests/services/integrations/test_naver_dock_amounts.py tests/services/integrations/test_naver_dock_deposit_match.py tests/services/integrations/test_naver_dock_deposit_hint.py tests/services/integrations/test_naver_dock_autofill_wire.py tests/services/integrations/test_naver_dock_fill_all.py tests/services/integrations/test_naver_dock_deposit_base.py tests/domains/test_static_js_syntax.py -q -p no:cacheprovider
python -c "import app; print('APP_OK')"
```

## 3. 파일 소유권 (겹치면 안 된다)

| worker | 편집 허용 |
|---|---|
| A (배지) | `foms/web/admin/naver_ingest.py`(`_history_axes` 반환부·`_history_foms_state` 근처만), `templates/admin/naver_workbench.html`(1044-1066 블록만), `tests/services/integrations/test_naver_history_status_axes.py` |
| B (도크) | `static/js/orders/erp-naver-dock.js`, `static/css/orders/erp-naver-dock.css`, `foms/services/integrations/naver_commerce/dock.py`(`_deposit_hint` 만), `templates/orders/partials/erp_order_js.html`(핀 2줄만), `tests/services/integrations/test_naver_dock_amounts.py`, `test_naver_dock_deposit_match.py`, `test_naver_dock_deposit_hint.py`, `test_naver_dock_autofill_wire.py`(필요 시) |
| 통합 검증자 | 위 전부(수정은 게이트를 초록으로 만드는 최소만) + `docs/harness/*.json` 재생성 금지(총괄이 한다) |
| 리뷰어 | 편집 금지 |

## 4. 공통 규칙·함정

- 시작 시 `cd /c/tmp/foms-s-s0908-102606 && pwd`. git 명령 금지. docs 를 읽는 테스트(`test_docs_facing_registry` 등) 돌리지 않기.
- 개행: 파일마다 기존 개행(CRLF/LF) 유지. Edit 도구로 부분 편집.
- Python: 새 함수는 docstring(목적·인자·반환)·타입 힌트 필수, 50줄 이하. JS: 원본 문자열은 `textContent` 로만(XSS), 인라인 스타일 금지,
  jQuery 금지. 돈 표기는 서버 문자열만 쓴다(화면에서 다시 포맷 금지).
- 테스트를 **지우지 마라** — 요구가 바뀐 테스트는 새 요구를 단언하도록 고쳐 쓰고 docstring 에 "2026-09-10 사용자 지시로 대조 줄 폐기" 를 적는다.
- `HISTORY_FOMS_LABELS`·`HISTORY_RELATION_LABELS` 값 변경 금지(칩·배지 한 벌 계약).
- 워크벤치 쪽(`static/js/admin/naver-workbench.js:2480-2520, 2970`)에도 비슷한 문장이 있지만 **이번 범위 밖**(사용자 캡처는 ERP 도크). 손대지 마라.
- `docs/harness/*.json` 은 테스트가 재생성한다 — 편집·커밋 금지(총괄이 `git checkout -- docs/harness/`).

## 5. 완료 기준(통합)

```
cd /c/tmp/foms-s-s0908-102606
python -m pytest tests/services/integrations/test_naver_history_status_axes.py tests/services/integrations/test_naver_dock_amounts.py tests/services/integrations/test_naver_dock_deposit_match.py tests/services/integrations/test_naver_dock_deposit_hint.py tests/services/integrations/test_naver_dock_autofill_wire.py tests/services/integrations/test_naver_dock_fill_all.py tests/services/integrations/test_naver_dock_deposit_base.py tests/domains/test_static_js_syntax.py -q -p no:cacheprovider
python -m pytest tests/services/integrations -q -p no:cacheprovider -k "naver_dock or naver_history or naver_workbench or naver_ingest"
python -c "import app; print('APP_OK')"
powershell -NoProfile -ExecutionPolicy Bypass -File scripts/ops/pre_push_smoke.ps1   # exit 0
```
그 뒤 총괄: diff 직접 읽기 → 게이트 재실행 → 커밋·deploy push → CI → 스테이징 실화면(이력 탭 추가결제 행·ERP 도크) 확인.

## 6. 실행 결과 (Workflow `wf_c013f0fb-68b`, 7 에이전트 · 27분 · 약 77만 토큰)

- CEO 설계: 브리프 초안에 **보강 1건** — `주문 만듦` 접기 조건에 "관계 배지가 가리키는 주문 == 대표가 붙은 주문" 추가(섞인 집에서 대표 주문이 화면에서 사라지는 것 방지, 기존 테스트 `test_relation_number_comes_from_the_member_that_decided_the_relation` 이 실재 증명). T2 카드 조건은 `state` 무관, `relation_label`·`live_total_display` 둘 다 있을 때.
- 워커 A: 44 passed(신규 6). 워커 B: JS/CSS/dock.py/핀/테스트 3파일. 통합 검증: 게이트 4개 green — 소유권 밖 2파일(`test_naver_dock.py`·`test_naver_dock_household_split.py`)의 옛 핀 단언 6줄을 20260910a 로 맞춤(안 맞추면 CI red).
- 리뷰: 스펙 pass · 품질 pass. P2 6건 — 커밋 범위에 위 2파일 포함 / `.m.txt` 정리 / 게이트1 수치 107(계약 106+CSS 폐기 단언 1) / 낡은 주석 3곳(erp-naver-dock.js:594·dock.py:1179·test_naver_dock_amounts.py 머리말) / `test_naver_dock_deposit_hint.py:332·341` "(워크벤치가 읽는다)" 는 거짓 근거(워크벤치는 자기 라우트의 `deposit_guidance` 를 읽고 도크 옛 키는 런타임 소비처 0) → 총괄 직접 반영.
- CEO 판정: **ship**. 총괄 검증·커밋·push·스테이징 QA 는 아래.
- 총괄 직접 diff 확인: 서버 판정 함수 1 + 행 dict 키 1 + 템플릿 분기 1 / 서버 키 2 + 헬퍼 1 / JS 카드 2노드·문장/대조/리스너/사실줄 제거 / CSS 5규칙 제거 / 핀 2줄 / 테스트 재작성. 잔재 grep(`syncDepositMatch|depositFactLine|naver-dock-deposit-state`) 0.
- 후속 후보(범위 밖): dock.py `_deposit_hint` 의 옛 키(state·target·sentence·copy_value·note)와 `deposit_guidance` 호출은 이제 런타임 소비처가 없다 — 정리는 별도 판단. 워크벤치 정리 계획 카드의 예약금 문장(`naver-workbench.js:2480-2520`)은 그대로.

- 총괄 마감: deploy `5a0b9e665`(CI 4종 green) → 스테이징 실화면 QA PASS(#4242 추가결제·#4485 재결제 행, 도크 payload, 배포 JS) → PR #341 검사 4종 pass → production **`a1ec42996`**(2026-09-10 13:30 KST, healthz 62초). 승격 브랜치·워크트리 삭제.
