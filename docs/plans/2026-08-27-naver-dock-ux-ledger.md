# 원장 — 네이버 도크·워크벤치 UI 개선 3건 (2026-08-27)

트리 `c:/tmp/foms-s-dock` · branch `session/dock` · base `origin/deploy`
PANE = `templates/admin/partials/naver_workbench_pane.html` · DOCKJS = `static/js/orders/erp-naver-dock.js`
DOCKCSS = `static/css/orders/erp-naver-dock.css` · DOCKPY = `foms/services/integrations/naver_commerce/dock.py`
PIN = `templates/orders/partials/erp_order_js.html`

## D1 — 발송처리 라벨 통일
`지금 닫기` 를 저장소에서 없앤다. 3자리 전부 무조건 발송처리 어휘로.
- `PANE:261` 버튼 → `발송처리`
- `PANE:869` 모달 제목 → `발송처리를 보내기 전에 확인하세요`
- `PANE:929` 모달 확인 → `발송처리 보내기`
- `PANE:104-107` `close_now_title` set 블록 삭제(소비처가 869 하나뿐)

`close_now` **술어·동작은 불변** — 그건 `can_dispatch`(`PANE:99`)를 여는 진짜 게이트다. 라벨만 바꾼다.
근거: 이 버튼은 실제로 dispatch 를 부르고(`submitDispatch` → `POST fulfillment{action:'dispatch'}`),
같은 모달 본문 3곳(`PANE:877/912/920`)이 이미 `발송처리` 어휘라 **반쪽 불일치** 상태였다.
계약 문서 `CONTRACT:189` 도 이 id 3종의 뜻을 이미 "발송처리"로 정의한다.

"물건이 안 나간다"는 사실은 **이미 있는 두 문장**이 계속 말한다 — `PANE:317-320`(상시 줄),
`PANE:907-917`(모달 alert). 꼬리만 버튼 이름으로 고치고 **머리 `물건이 따로 나가지 않습니다` 는 불변**
(새 테스트가 이 문자열을 close_now 판별자로 쓴다).

버린 대안: 버튼만 바꾸기(누르면 모달에서 같은 오해 재현) / 합성 라벨 `추가결제 발송처리`(폭·문장 붕괴)
/ title 툴팁(마우스 없는 기기에서 영영 안 읽힘 — 이 저장소가 두 번 결함으로 기록).

깨질 테스트 4건 → `"물건이 따로 나가지 않습니다"` 로 교체:
`test_naver_workbench_relation.py:238`(in, 즉시 red) · `:250`·`:270`·`:453`(not in, vacuous 화).

## D2 — 도크 그룹 금액 = 본품 + 귀속 옵션 합
**계산은 JS 에서 한다(서버 아님).** 사람이 귀속 드롭다운을 바꾸면 `DOCKJS:587-590` 이 `render()` 를
다시 부른다 — 서버가 로드 때 계산한 값은 그 순간 낡는다. `width_hints` 가 실제로 그 상태다(선재 결함).
정본 등식(`본품 + Σ 귀속 옵션`)은 서버 `mapping.map_group:952-995` 에 그대로 남고 `items[].price` 불변.
대가(파이썬으로 합계를 못 잡음)는 JS 소스 계약 + payload `amount` 키 계약 + 실화면 확인으로 갚는다.

- 귀속 정본: `effectiveMain(row)` = `assigned_main`(사람) > `guess_main` — 머리말 아래 그려진 행과 같은 술어.
- 본품 없는 그룹(공통/귀속 미정): 합계를 내되 라벨을 달리한다 → `옵션 합 12,000원`.
- `amount === null`: **절대 0으로 안 더한다**. 행 = `금액 모름` 칩(+title "0원이라는 뜻이 아닙니다"),
  머리말 = `· 모름 N건` + `.is-partial`. 전부 모름이면 머리말 합계 미표시.
- superseded 그룹: `환불됨 · <취소선>704,200원`. 판정은 `mainRow.superseded`(서버가 이미 찍음).
- 라벨을 붙인다 — 사용자가 오해한 원인이 **라벨 없는 숫자**였다. `본품+옵션 N원`.
- 옵션 행 금액: 값은 `row.amount`(=`totalPaymentAmount`). **`optionPrice` 는 안 쓴다**(이중 계상).
  0원은 기존 `.naver-dock-zero` `'0원'` 유지, 모름은 `.naver-dock-amt.is-unknown`.
  **본품 행에도 붙인다** — 검산 못 하는 합계는 다시 안 믿는다.

## D3 — 예약금(선금) 안내
`#erp-deposit-amount` 의 정본 이름은 **예약금(선금)**. 출고가·잔금은 입력칸이 아니라 계산 표시다.

```
target  = Σ(superseded 아닌 집의 상품주문 결제액)     # 절대값
current = erp_deposit_amount_from_structured(sd)      # 페이지 로드 시점
diff    = target - current
```
도크는 **붙인 뒤 며칠 뒤** 화면이라 재결제식 상대값(`current + amount`)을 그대로 쓰면 사람이 이미
고쳐 놨을 때 이중 계상을 시킨다. 그래서 절대 target 을 먼저 정하고 문장만 `deposit_guidance` 에 위임:
superseded 있으면 `relation="REPAY", new_amount=target`, 아니면 `relation="ADDON", new_amount=diff`.
**`repay_reconcile.py` 는 한 글자도 안 고친다.**

상태 4종: `match`(한 줄 확인) · `differs`(카드+복사) · `over`(경고 한 줄, "낮추라"고 말하지 않는다 —
네이버 밖 입금이 정당할 수 있고 잔금을 타고 고객 청구로 간다) · `unknown`(숫자 없이 경고).
note: superseded 있으면 `환불된 이전 주문은 뺀 금액입니다`, claim 있으면 환불액 미반영 고지.

문장 생성은 **서버(DOCKPY payload)** — 재결제 정본이 그렇다(서버가 문장, 화면은 그리기만).
복사 버튼 붙인다(`data-naver-dock-copy` 위임이 이미 있다). **복사 값 = 쉼표 없는 정수 `"704200"`.**
**자동 기입 금지** — 명문 규약 4곳 + 재논의 금지 결정. 도크 JS 는 `erp-` 폼 id 를 읽지도 않는다.
위치: 머리 정보 블록 뒤 · 진행바 앞(스크롤 영역 밖이라 늘 보인다).

payload 계약(동결):
```python
payload["deposit_hint"] = {
    "state": "match"|"differs"|"over"|"unknown",
    "current": int, "target": int|None, "diff": int|None,
    "sentence": str, "copy_value": str, "unknown_count": int, "note": str,
}
```
`households[]` 에 `amount_total`·`amount_unknown` 추가. JS 는 키가 없어도 오늘과 똑같이 그린다.

## D4 — 자산 핀
`PIN:35` CSS `?v=20260826a` → `20260827c`, `PIN:36` JS `?v=20260827b` → `20260827c`.
핀 리터럴 테스트 6줄 동반 갱신: `test_naver_dock.py:705,706,887,888`,
`test_naver_dock_household_split.py:317,318`. PANE 은 서버 렌더라 핀 대상 아님.

## D5 — 슬롯 분할 (파일 배타, 동시 착수)
- **A**: PANE · `test_naver_workbench_relation.py` · `CONTRACT`
- **B**: `dock.py` · 신규 `tests/.../test_naver_dock_deposit_hint.py`
- **C**: DOCKJS · DOCKCSS · PIN · `test_naver_dock.py`(핀 4줄만) ·
  `test_naver_dock_household_split.py`(핀 2줄만) · 신규 `tests/.../test_naver_dock_amounts.py`

## 사용자 지시와 달라진 점
1. 버튼 하나 → **3자리 통일**(모달에서 같은 오해 재현 방지).
2. 숫자에 **라벨을 붙인다**(오해의 원인이 라벨 없는 숫자였다).
3. **본품 행에도** 금액 표기(합계 검산 가능하게).
4. "최종금액"이라 부르지 않고 **예약금(선금)** — 재결제 화면과 같은 말을 쓴다.
5. **자동 기입 안 한다**(명문 규약). 복사 버튼까지가 끝.
6. 값이 맞는 보통 주문에는 **큰 카드 대신 한 줄** — 상시 카드는 잡음이 되고 정말 틀린 날에 안 읽힌다.

## Task
공통: `cd /c/tmp/foms-s-dock && pwd && ...` · 게이트 `python -c "import app; print('APP_OK')"`

### Slot A
- A1 `PANE:104-107` close_now_title 블록 삭제 — `grep -n close_now_title PANE` 0건 · DONE
- A2 `PANE:261` 버튼 라벨 → `발송처리` · DONE
- A3 `PANE:869` 모달 제목 무조건화 · DONE
- A4 `PANE:929` 확인 버튼 → `발송처리 보내기` · DONE
- A5 `PANE:319`·`909` 문장 꼬리만 버튼 이름으로(머리 불변). 착수 전 `grep -rn "여기서 바로 닫습니다" tests/ docs/specs/` · DONE
- A6 `test_naver_workbench_relation.py:238/250/270/453` 단언 교체 + docstring 어휘 정리 — 해당 파일 pytest green · DONE
- A7 `CONTRACT:214` 및 같은 절 안내 갱신 — `grep -n "지금 닫기" CONTRACT` 0건 · DONE
- A8 실화면: ADDON 집 상세에 파란 `발송처리` + `추가결제` 배지 + 안내 줄 동시 확인(스크린샷) · DONE

### Slot B
- B1 `_household_amounts(rows)` — int 아닌 amount 는 unknown 으로 **센다**(0 가산 금지) · DONE
- B2 `households[]` 에 `amount_total`·`amount_unknown` 병합 · DONE
- B3 `_deposit_hint(...)` 4 state · `deposit_guidance` 위임 · `copy_value` 쉼표 없는 정수 ·
  함수 50줄 이하 · docstring·타입힌트 · DONE
- B4 payload 에 `deposit_hint` 추가 · DONE
- B5 신규 `test_naver_dock_deposit_hint.py` 7케이스(match/differs·더해/differs·대신+note/unknown/over/claim note/copy_value 형식) · DONE
- B6 `repay_reconcile.py` 무변경 확인 + 재결제 테스트 2종 green · DONE

### Slot C
- C1 `sumRows(rows)` 신규(+ 왜 서버가 아닌지 주석) · DONE
- C2 `buildAmountChip(row)` — 0원 유지 / 모름 신설 / 본품·옵션 모두 · DONE
- C3 머리말 합계 교체 — `본품+옵션 `/`옵션 합 ` · `.is-partial`+`· 모름 N건` · `.is-superseded`+`환불됨 · ` · DONE
- C4 state 에 `depositHint: payload.deposit_hint || null` **새 줄 추가**(기존 순서 불변) · DONE
- C5 `hasFacts` 확장 + facts **맨 끝** append(match/over/unknown 한 줄) · DONE
- C6 `buildDepositCard()` — `differs` 일 때만, info 뒤 / pbar 앞 · DONE
- C7 DOCKCSS **추가만**(.naver-dock-amt/.is-unknown/.is-partial/.is-superseded/.naver-dock-deposit) · DONE
- C8 `PIN:35,36` → `?v=20260827c` (grep 2건) · DONE
- C9 핀 단언 6줄 동기 · DONE
- C10 신규 `test_naver_dock_amounts.py` 8케이스(포함: 도크 JS 소스에 `erp-deposit`·`getElementById('erp` 0건 — 폼 불가침 회귀 가드) · DONE

### 합동 검증
- V1 실화면: 머리말 합계 = 아래 행 합, 귀속 옮기면 양쪽 즉시 갱신(스크린샷 2장) · DONE
- V2 실화면: ADDON 주문에서 예약금 카드 + 복사값 쉼표 없음 · DONE
- V3 `grep -rn "지금 닫기" templates/ static/ foms/` 0건 · DONE
- V4 `pytest tests/services/integrations -q -k naver` green + APP_OK · DONE
- V5 `pre_push_smoke.ps1` exit 0 · DONE

## 회귀 위험 (손대면 안 되는 자리)
1. `_ADDON_FACT_LINE`·`_REPAY_FACT_LINE` 두 줄 — 한 글자도 금지. facts 는 **뒤에만 append**.
2. `buildPanel` 머리 4줄(`naver-dock-wb` 앵커·href·target·`workbenchUrl:`).
3. `buildRow` 의 `row.superseded ? ' is-superseded' : ''` 줄 — 머리말 쪽은 별도 줄로.
4. state 리터럴 기존 키 순서·표기 — 새 키는 추가만.
5. `.naver-dock-row.is-superseded`·`.naver-dock-hh` CSS — 삭제·병합 금지.
6. `repay_reconcile.py` — 전 파일 읽기 전용.
7. `close_now` 술어·`CLOSE_NOW_RELATIONS`·`can_dispatch` — D1 은 라벨만.
8. `mapping.map_group` 의 `items[].price` 등식 — D2 는 화면 표시만.

## 수용하는 위험(기록)
- ~~`width_hints` 는 사람 재귀속 후 낡는다(선재 결함, 이번 범위 밖 — 다음 세션 후보).~~
  → **해소**: 같은 세션에서 W1 로 고쳤다(아래 `## W1` 절). 총폭도 화면이 다시 센다.
- 예약금 `current` 는 로드 시점 값 → 문장이 비교 대상(`지금 값 N원`)을 명시해 사람이 알아채게 한다.
- D2 그룹 합(귀속 기준·superseded 포함)과 D3 target(집 기준·superseded 제외)은 다를 수 있다 → note 로 명시.
- 새 mutation 라우트 0건 → write manifest·감사 라벨 불필요(전부 읽기·표시).


## 완료 기록 (2026-08-27)

- Slot A/B/C 전부 DONE. 총괄 추가 수정 3건:
  1) `foms/web/admin/naver_ingest.py` 주석 2곳의 죽은 라벨(`지금 닫기`) 어휘 정리 → 전수 0건.
  2) 예약금 카드에 **라벨 + 큰 숫자**를 세웠다(원장 D3 규격). 돈 표기를 화면이 다시 만들지
     않도록 서버가 `target_display`("872,200원")를 함께 싣는다 — Slot C 의 "화면 재포맷 금지"
     계약과 CEO 의 "큰 숫자" 요구를 동시에 만족시킨 절충.
  3) 고지 문구를 원장 문안으로(`시스템이 넣지 않습니다 — 예약금(선금) 칸에 직접 입력하세요.
     잔금은 출고가 − 예약금으로 따라옵니다.`) + `.naver-dock-deposit-won` 18px/800 규격 추가.
- 검증: `tests/services/integrations` **843 passed** · `APP_OK` · `node --check` 통과.
- 실화면(로컬 렌더 + 헤드리스, 1440):
  - 머리말 `본품+옵션 872,200원` = 행 합(704,200 + 48,000 + 120,000 + 0) **눈으로 일치**
  - 행마다 금액 칩(0원은 기존 호박색 유지)
  - 예약금 카드: 라벨 · 872,200원 · 문장 · `📋 872200`(쉼표 없음) · 자동 기입 금지 고지
- 리뷰 에이전트 지적 1건("반품 버튼·모달 삭제 = 스코프 이탈")은 **오탐**. pane diff 는 7추가/9삭제
  전부 라벨 줄이고 반품 참조 29건이 그대로다 — 근거와 함께 반려.
- 미검증으로 남긴 것: V1 의 "귀속을 옮기면 양쪽 합계가 즉시 바뀐다"는 정적 렌더 하네스에서
  저장 fetch 가 나가지 않아 화면으로 못 봤다. 코드 경로(change 위임 → 저장 성공 → `render()`)와
  `sumRows` 단위 검증으로 갈음했다. 실서버 스모크 때 확인 대상.

## W1 — 총폭 힌트도 화면 계산으로 이관 (2026-08-27, 같은 세션 후속)

**결함**: 서버가 페이지 로드 시점에 계산한 `width_hints` 는 사람이 옵션 귀속 드롭다운을
다른 본품으로 옮겨도 갱신되지 않았다. 바로 옆 금액 합계는 D2 에서 화면이 세도록 바꿔
즉시 갱신된다 — **한 화면의 두 숫자가 서로 다른 시점을 말했다**.

**분업(금액과 동일)**: 파싱은 서버가 계속 한다. 화면은 합·문자열 조립만 다시 한다.

### payload 새 필드 (행마다 — DOCKPY `_row_width_facts`)
| 필드 | 형 | 뜻 |
| --- | --- | --- |
| `width_unit_mm` | int \| None | 이 행이 총폭에 내놓는 **1개당 길이**(mm). 본품=상품명·옵션에서 파싱, 추가옵션=**길이추가(1cm) 계열만**. 수납구성·거울도어는 None |
| `width_label` | str | 계산식 `parts` 라벨(상품명 24자, 비면 `본품`/`길이추가`) |
| `width_axes` | dict | 사양 축 값(`몰딩`·`문 방식`·`손잡이`) — 불일치 경고 대조용 |

- 찍는 자리: `build_dock_payload` 의 `role` 폴백 **뒤**(승격된 행이 본품 규칙으로 계산되게).
- `build_width_hint` · payload `width_hints` **유지**(계약 테스트 + 하위호환 폴백). 내부는
  같은 `_row_width_facts` 를 쓰도록 바꿔 두 경로가 갈릴 수 없게 했다.

### JS 계산 경로 (DOCKJS)
`buildPanel` 그룹 루프 → `widthHintFor(group.key, rows, mainRow)`
→ 본품 행에 `width_unit_mm` 키가 **있으면** `computeWidthHint(rows, mainRow)`,
**없으면**(옛 응답) `state.widthHints[groupKey]` 그대로.
`rows` 는 금액이 쓰는 그룹 목록과 **같은 변수**(`buildGroupAmount(sumRows(rows), mainRow)`)라
두 숫자가 언제나 같은 모집단이다. `computeWidthHint` 는 `total_mm`·`formula`·`parts`·
`mismatch` 를 서버와 **같은 문구**로 조립한다(`widthTerm` = `{unit:,}mm × {qty}`).

### 검증
- `node --check` OK · `tests/services/integrations` **854 passed** · `APP_OK`
- 신규 `tests/services/integrations/test_naver_dock_width_live.py` 12건 —
  Node 로 함수 실제 실행(재귀속 전후 3720/800 → 3600/920) + 서버 정본과 값 대조 4케이스
  + 옛 응답 폴백 + 소스 배선 계약.
- **음성 대조군**: `computeWidthHint` 의 그룹 술어를 `([mainRow])` 고정값으로 망가뜨리자
  5건 red(재귀속·불일치 문구·정본 대조 3케이스) → 즉시 원복, md5 일치 확인.
- 자산 핀 `?v=20260827c` → **`20260827d`** (PIN 2줄 + 핀 리터럴 테스트 6줄).

### 지킨 경계
- 폼 불가침: 도크 JS 는 여전히 `erp-` 폼 id 를 안 읽는다. 자동 기입 없음(복사 버튼까지).
- 화면에 길이 파서를 만들지 않았다 — `computeWidthHint` 는 `product_name`·`option_text` 를
  **한 번도 읽지 않는다**(테스트가 못박음).
- CSS 변경 0(렌더 함수 `buildWidthHint` 는 입력 모양이 같아 그대로).

## 운영 반영 확인 (2026-08-31 — 별 세션 점검)

**승격할 것이 남아 있지 않다.** 원장이 남긴 "스테이징 실화면 확인 → 운영 승격"은 낡았다 —
D1·D2·D3 과 총폭 힌트 수정(`eaed04ab`)의 내용이 이미 운영에 있다. 판정은 커밋 목록이 아니라
내용으로 했다(앞선 네이버 승격 PR 들이 cherry-pick 이라 SHA 는 안 맞는다).

- `git diff origin/production origin/deploy` 가 `dock.py` · `erp-naver-dock.js` ·
  `erp-naver-dock.css` · `naver_workbench_pane.html` 넷에 대해 **0줄**이다.
- 표식 확인: `본품+옵션` · `deposit_guidance` · `발송처리 보내기` · `금액 모름` 전부 운영에 존재.
- 음성 축: `지금 닫기` 는 운영 소스에 **0건**(D1 통일이 끝났다는 뜻).

남은 것은 운영 실화면 육안 확인뿐이고, 그것은 배포 여부와 다른 축이다(이 점검에서는 안 했다).
