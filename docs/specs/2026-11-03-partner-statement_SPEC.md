# 협력사 거래명세서 — 단가표 · 옵션 고르기 · 명세서 · 입금 장부 SPEC (2026-11-03 승인 · 5단계까지 구현)

등급: 코어 변경(DB · API · 권한 · 화면) — Spec → 승인 → 구현.
선행 설계서: `docs/specs/2026-10-08-partner-portal_SPEC.md`(§6.3 정산은 "갈라 보이기만"으로 남겨 둠) · `docs/specs/2026-10-19-partner-foms-mode_SPEC.md`(협력사 화면 틀).
목업: 전체 흐름 10화면(5차) + **협력사 옵션 입력**(2차 — 실제 `partner/new_order.html` 렌더 + 실제 CSS · 고르기 창에 옵션 칸만 바꿈). 실제 단가 · 업체 정보가 들어 있어 사용자 PC 에만 두고 **저장소에 넣지 않는다**(저장소 공개). 이 문서에도 단가 숫자 · 사업자번호 · 계좌는 적지 않는다.

## 0. 사용자 결정 (2026-11-03)

1. 이카운트와 연결하지 않는다. 거래명세서는 우리 ERP 가 직접 발행한다. 양식은 이카운트 모양에 조사해서 고른 칸을 더한다(5.8).
2. 하우드 도장은 견적서 도장(`static/images/company-stamp.png`)을 쓴다.
3. 자 수 = 가로 ÷ 300, **소수 둘째 자리에서 반올림**(12.33 → 12.3, 9.33 → 9.3).
4. 협력사는 금액을 **명세서가 발행된 뒤에만** 본다. 옵션 고르기 · 도면 확인 화면에는 금액이 없다.
5. 입금 확인 · 잔액 장부는 우리 ERP 가 갖는다.
6. 단가표는 사용자가 쓰던 "통합 단가표" 모양 그대로 우리 ERP 에서 고치고 저장한다(저장 = 새 판).
7. 제품이 여러 개인 주문은 명세서 한 장에 **제품마다 묶음 + 소계 + 제품별 최종 도면**.
8. **협력사가 옵션을 직접 고른다.** 단가표 품목 이름 목록에서 고르고, 없는 것은 "커스텀" 메뉴에 글 · 사진으로 적는다. 옵션 칸을 "사진참조"로만 끝낼 수 없다.
9. **내부 옵션은 기본 제품 가격에 들어 있다.** 협력사 단가표의 TYPE A~K(0원) · 깊이 줄임(값 빈칸)이 그렇다. 명세서에 따로 줄을 만들지 않고 기본 제품 줄 비고에 "내부 A·A·J · 깊이 줄임 포함"으로 적는다. 그래도 협력사는 고른다(도면팀이 볼 정보).
10. 단가표 제품 이름 "TV 월플렉스, 침대 벽박이장"은 "침대 붙박이장"으로 바꿔 쓴다(협력사가 고르는 이름도 "침대 붙박이장"). 단가 자료는 DB 에만 있으므로 단가표를 불러온 뒤 편집기에서 이름을 고친다.
11. "여닫이 통 추가 (한통)"은 기본 포함이 아니다 — 값을 정해 단가표에 넣는다.
12. 진행 중인 협력사 주문은 우리 CS 가 사진 · 도면을 보고 옵션을 채운다(CS 화면에 같은 고르기 부품).

## 1. 지금 코드 · 운영의 사실

1. 협력사 품목은 자유 글뿐이다. `clean_partner_items`(`foms/services/partners/orders.py:131`)가 받는 칸은 `product_name` · `spec_rows` · `quantity` · 속성 다섯 칸(`ATTRIBUTE_KEYS` = internal · color · option_detail · handle · misc, `:40`) · `extra_input`. 옵션을 구조로 담는 칸이 없다.
2. 제품명 ▾ 목록은 소비자 계산기 제품 이름이다(`_product_names`, `foms/web/partner/__init__.py:61` — 이름만, 금액 없음).
3. 협력사가 고칠 수 있는 때는 첫 도면 전달 전까지다(`partner_edit_open`, `foms/services/partners/items_edit.py:96`). 그 뒤는 수정 요청.
4. 협력사 "이대로 만들어 주세요" = `approve_partner_drawing`(`foms/services/partners/drawing_confirm.py:62`) → CONFIRM 승인 → 생산 이동.
5. 도면 전달 = `transfer-drawing`(`foms/api/drawing/erp_orders_drawing.py:181` 핵심 · `:595` 라우트) · 마법사 전달(`foms/api/drawing/wizard.py:1638`).
6. **우리 주문 화면 저장은 품목을 통째로 다시 쓴다.** 서버가 소유한 품목 칸은 폼 저장에 지워져 `preserve_item_cancel_state`(`foms/services/orders/drawing_confirm_partial.py:316`, 불리는 곳 `foms/api/erp_orders_structured.py:1635`)로 되살린다. → 옵션을 `items[]` 안에 넣으면 같은 일을 또 해야 한다. 품목 식별자는 `order_item_identities`(`models.py:429`).
7. 소비자 계산기(`foms/services/wdcalculator/pricing.py`)는 30cm + 1cm 규칙이다. 협력사 단가(자 소수)와 다르다 — 섞지 않는다.
8. 견적서(`OrderEstimate`, `models.py:1834`)는 번호 `YYYYMMDD_N` · 품목 JSON · 화면 내보내기(`static/js/orders/estimate-preview.js`, html2canvas)를 쓴다.
9. 출고 대시보드 = `foms/web/shipment/dashboard.py`(협력사 주문 필터 이미 있음).
10. 협력사 새 라우트는 문지기 허용 목록 `PARTNER_ALLOWED_ENDPOINTS`(`foms/services/auth/partner_scope.py:26`) + 매니페스트 2개(`docs/harness/foms_order_mutation_policy_manifest.json` · `docs/harness/foms_write_guard_manifest.json`)에 같이 넣는다.
11. **운영 실측(2026-11-03, 읽기 전용)**: 운영 협력사 1곳, 주문 34건(MEASURE 16 · DRAWING 10 · PRODUCTION 5 · 삭제 3). 품목 59개 중 내용을 적은 것 28개, 그중 **18개(64%)가 내부 · 옵션 칸에 "사진참조"**. 도면이 나간 8건 중 6건이 마법사 내보내기. 마법사 시트 7장: 자재표 계산 칸(`calc`) **0장**, `[마이다]`(서랍) 머리글 1장 · 빈칸, 옵션은 머리글 없는 글("LED" 등)로 흩어져 있다. → 지금 자료로는 도면이나 글에서 옵션을 자동으로 읽어 금액을 낼 수 없다(결정 8 의 근거).

## 2. 설계 원칙

- **금액 = 확정 옵션 목록 × 단가표 판.** 사람은 숫자를 계산하지 않는다(커스텀 금액만 넣는다). 모델(AI)은 금액을 내지 않는다.
- **발행본은 스냅샷이고 잠긴다.** 단가표 판 · 도면 회차 · 줄 전부를 복사해 둔다. 고칠 일은 "수정본"으로 새 명세서를 낸다.
- **같은 것인지는 ID 칸으로 가린다.** 협력사 = `partner_org_id`, 단가표 줄 = 판이 바뀌어도 이어지는 줄 열쇠(`key`). 이름 글자로 맞추지 않는다.
- **주문 JSON 을 무겁게 하지 않는다.** 옵션 · 명세서 · 입금은 새 표에 둔다(1장 6번 · JSONB TOAST 비용).
- **바꾸지 않는 것(11장)은 대조군 시험으로 고정한다.**

## 3. DB (Alembic, 단계마다 하나 · downgrade 포함)

### 3.1 `partner_price_lists` — 단가표 판
| 칸 | 형 | 설명 |
|---|---|---|
| id | int PK | |
| partner_org_id | int FK partner_orgs | |
| version | int | 협력사 안에서 1, 2, 3 … (`unique(partner_org_id, version)`) |
| label | varchar(40) | "11월판" 등 |
| effective_from | date | 이 날짜 출고분부터 쓴다 |
| status | varchar(10) | DRAFT · ACTIVE · RETIRED. 협력사마다 ACTIVE 하나(부분 유니크) |
| sheet | JSONB | 단가표 전체 — 카테고리(왼쪽/오른쪽 · 제목 · 열 · 칸 구성 · 폭) · 줄. 사용자 HTML 의 `<script id="data">` 모양을 받는다 |
| rules | JSONB | 자 수 반올림 자리 · 원 단위 · 번호 머리 |
| created_by / created_at | | |

줄(칸 목록) 하나에 단가 항목이 하나(이름 · 금액) 또는 둘(이름 · 금액 · 이름 · 금액). 항목마다: `{key, name_col, price_col, role, unit, kind, cond, partner_label, pick_names, for_products, pickable}` — 이름 · 금액은 칸(`cells`)에만 둔다.
- `role`: `product`(협력사 제품명 ▾ 목록) · `option`(옵션 칸 목록). 불러올 때 "기본 제품 가격" 카테고리와 가로 구간 줄(책상 · 오픈장)은 `product`, 나머지는 `option` 으로 저절로 나누고, 틀린 것은 관리 화면에서 고친다.
- 불러오기(`POST …/import`)는 화면에 띄우기만 하고 저장하지 않는다. "저장 (새 판)"을 눌러야 판이 생긴다(DRAFT 상태는 지금 쓰지 않는다). 쓰는 판(ACTIVE)이 있으면 같은 이름 줄은 같은 열쇠를 다시 쓴다.
- `key`: 판이 바뀌어도 그대로 이어지는 짧은 열쇠. 새 판은 옛 판을 복사해서 만들고, 줄을 지우면 `pickable=false` 로 남긴다(옛 선택이 끊기지 않게).
- `unit`: 자 · m · 개 · 짝 · 통 · 식.
- `kind`: 계산 방법 — `included`(기본 포함 — 값이 빈칸 · 0원, 줄 없이 기본 줄 비고에) · `ja`(자 단가) · `meter`(m 단가) · `band`(크기 구간) · `over`(넘친 만큼, 100mm 당) · `count`(개수) · `fixed`(정해진 값 한 번).
- `cond`: 구간 조건(예: 가로 801~900 · 깊이 601~800) · `over` 의 기준 줄.
- `partner_label`: 협력사에게 보일 이름(내부 말 "마이다" 대신 "서랍" 등). 비면 첫 칸 이름.
- `pick_names`: **협력사가 고르는 이름 목록**(제품명은 하나씩 고를 수 있어야 한다). 단가표 한 줄에 이름 여러 개가 붙고 모두 그 줄 단가로 계산한다. 예: 줄 "여닫이 / 몰딩, 무몰딩" → 고르는 이름 몰딩 여닫이 · 무몰딩 여닫이, 줄 "여닫이 / 아라 시리즈" → 아라 01 · 02 · 03 · 아라 투도어 01 · 02 · 03, 줄 "거울/유리도어 슬라이딩" → 거울도어 슬라이딩 · 유리도어 슬라이딩. 비면 `partner_label` 하나. 고른 품목에는 이름과 줄 열쇠(`key`)를 함께 남긴다.
- `for_products`: 이 옵션 줄을 보여 줄 제품 이름들(제품 줄의 `pick_names` 에서 고름). 비면 모든 제품. 예: 침대 프레임 SS · Q · K · LK · 침대 헤드 템바보드 → **침대 붙박이장만**(침대 프레임은 제품이 아니라 침대 붙박이장의 옵션). 협력사 옵션 고르기 창은 그 품목 제품명에 맞는 줄만 보여 준다.

### 3.2 `order_item_options` — 품목마다 고른 옵션
| 칸 | 형 | 설명 |
|---|---|---|
| id | int PK | |
| order_id | int FK orders | |
| item_uid | uuid | `order_item_identities` 의 품목 식별자 |
| stage | varchar(10) | `PARTNER`(협력사 원문) · `CURRENT`(최신 값 — 처음엔 원문과 같고 도면팀이 고친다) · `CONFIRMED`(협력사가 도면과 함께 확정) |
| state | varchar(10) | `chosen` · `none`(옵션 없음) · `later`(상담 후 정함 — 나중에 고름) |
| base_key | varchar | 기본 제품 줄 열쇠(제품명 ▾ 로 고른 단가표 줄). 크기 구간 제품은 이름 하나로 고르고, 구간 줄은 가로로 정한다. 직접 적은 제품명이면 null |
| lines | JSONB | 옵션 칸에서 고른 줄 `[{key, name, qty, memo}]`. name = 협력사가 고른 이름(단가표 한 줄에 여럿일 수 있다), memo = 위치(선택 — "좌측부터 2번 문" · "2번 통" · "왼쪽"). 서랍 · 피닉스바(손잡이 하나당) · 거울 도어 · 측면 마감판(EP) · 조명 등이 모두 이 한 목록에 든다 |
| customs | JSONB | 커스텀 `[{text, attachment_ids[]}]` — 단가표에 없는 것, 우리가 견적 |
| changes | JSONB | CURRENT 에서 도면팀이 바꾼 줄의 이유(`[{key, from, to, reason}]`) |
| price_list_id | FK | 고를 때 본 단가표 판(이름 표시용) |
| updated_by / updated_at | | |

`unique(order_id, item_uid, stage)`. 품목이 지워지면 그 품목 행도 지운다(품목 고치기 경로에서 함께). 우리 주문 화면 저장은 이 표를 건드리지 않는다(1장 6번 문제를 피한다).

### 3.3 `partner_statements` — 거래명세서
| 칸 | 형 | 설명 |
|---|---|---|
| id | int PK | |
| partner_org_id | FK | |
| order_id | FK orders | 한 주문에 여러 장 가능(AS · 추가 작업 · 수정본) |
| doc_no | varchar(30) unique | `HD-<출고일 YYYYMMDD>-<그날 순번 2자리>` |
| statement_date | date | 일자 = 출고 · 시공일 |
| status | varchar(10) | DRAFT · ISSUED · VOID |
| revision_of | FK self null | 수정본이면 옛 명세서(옛 것은 VOID) |
| price_list_id | FK | 계산에 쓴 단가표 판 |
| drawing_round · drawing_keys | int · JSONB | 협력사가 확정한 도면 회차와 그때 최종 도면 파일 열쇠(4단계 구현: `drawing_revisions` 는 실행 중에 줄을 쓰지 않아 FK 대신 스냅샷) |
| groups | JSONB | 제품 묶음 스냅샷 `[{item_uid, title, lines:[{key?, name, spec, unit, qty, unit_price, amount, source, basis, reason}]}]` — source = `auto` · `custom` · `edited` |
| total / supply / vat | bigint | 판매 합계 · 공급가액 · 세액 |
| prev_balance / after_balance | bigint | 발행 때 잔액 스냅샷 |
| issued_at / issued_by | | |
| partner_viewed_at · partner_ack_at · partner_ack_by | | 협력사가 열어 봄 · "확인했어요" |
| reason · version | text · int | 수정본 · 취소 이유(협력사에게 보임) · 초안 저장 경합 막기 |

- **4단계 구현(11-03)**: 표 `partner_statements` · `partner_statement_questions`(마이그레이션 `pstmt_00`). 주문마다 DRAFT 하나(부분 유니크). 묶음 줄 모양 = `statement_calc.calc_item` 결과 + CS 값(`source` `custom` 은 `amount`, `edited` 는 `orig_unit_price` · `reason`). 로직 `foms/services/partners/statements.py`(초안 · 다시 계산 · 저장 · 발행 · 수정본 · 취소), 화면 값 `statement_view.py`(한글 금액 포함).
- **양식 정보**(공급자 · 공급받는자 블록 · 계좌 · 문서번호 머리 · 입금 기한 · 세금계산서 안내 · 주의 문구)는 저장소가 공개라 코드에 두지 않고 SystemSetting `partner_statement_profile` 한 줄에 둔다. 관리 화면 `/admin/partners/<id>/statement-profile`(ADMIN). 공급받는자 상호 · 등록번호는 협력사 정보 그대로. 열린 질문 8(세금계산서 안내) · 9(번호 머리)는 이 화면에서 정한다.

### 3.4 `partner_payments` — 입금
`id, partner_org_id, paid_on(date), amount, memo, statement_id(FK null — 어느 명세서 입금인지), recorded_by, created_at, voided_at`. 잔액 = ISSUED 명세서 합 − 지우지 않은 입금 합(날짜 순).

### 3.5 `partner_statement_questions` — 금액 문의
`id, statement_id, line_ref(묶음 · 줄 번호), text, asked_by, asked_at, answer, answered_by, answered_at`.

## 4. 계산 규칙 (순수 함수 하나 — `foms/services/partners/statement_calc.py`)

- **기본 제품 줄**: 품목 규격 줄마다 한 줄. 가로 = 그 줄 가로 칸의 값 — `2400+1200` 처럼 더하기면 합, `5700(2402+1864+1434)` 처럼 괄호가 있으면 괄호 앞 값(5700).
  - `ja`: 수량 = 가로 ÷ 300 을 소수 둘째 자리에서 반올림(둘째 자리가 5 면 올림 — 12.35 → 12.4). 금액 = 수량 × 단가.
  - `meter`: 수량 = 가로 ÷ 1000 을 소수 둘째 자리에서 반올림(같은 규칙 — 열린 질문 10).
  - `band`: 가로(또는 깊이)가 드는 구간 줄 하나. 가장 큰 구간을 넘으면 그 줄 + `over` 줄.
  - `over`: (가로 − 구간 최대) ÷ 100 올림.
- **옵션 줄**: 고른 줄 × 수. `count` 줄 중 측면 마감판(EP)처럼 폭 구간이 있는 것은 품목 깊이로 구간을 고른다.
- **기본 포함(`included`)**: TYPE A~K · 깊이 줄임처럼 값이 빈칸 · 0원인 줄은 명세서 줄을 만들지 않는다. 그 품목 기본 제품 줄 비고에 이름을 붙인다(예: "내부 A·A·J · 깊이 줄임 포함"). 판에서 값이 생기면(0 → 금액) 그 판부터 줄이 된다 — 규칙은 값으로만 판정한다.
- **커스텀**: 금액 빈 줄로 초안에 들어온다. CS 가 금액 · 이유를 넣는다. 이유는 협력사에게 보인다.
- **원 단위**: 줄 금액 = 반올림(수량 × 단가). 합계 = 줄 합. 공급가액 = 반올림(합계 ÷ 1.1), 세액 = 합계 − 공급가액. 단가는 VAT 포함으로 적는다.
- **취소 품목**(`is_item_cancelled`)은 묶음에서 뺀다.
- 금액 계산은 이 함수 하나뿐이다. 화면 JS 는 서버 값을 보여만 준다.

## 5. 화면

### 5.1 관리 — 단가표 편집기 (ADMIN, `/admin/partners/<org_id>/price-list`)
- 사용자 단가표 HTML 과 같은 모양: 로고 · 왼쪽/오른쪽 카테고리 · 열 · 줄 · 칸 구성 1~4 · 칸 폭. 편집하기 / 편집 종료 · 줄 추가 · 지우기 · 위아래 · 카테고리 좌우 이동 · 복제 · 인쇄.
- "단가표 HTML 불러오기": HTML 파일의 `<script id="data">` JSON 을 읽어 화면에 띄운다(처음 한 번 + 백업 되살리기). 판은 "저장 (새 판)"을 눌러야 생긴다.
- 줄을 누르면 오른쪽 칸: 단위 · 계산 방법 · 조건 · 협력사에게 보일 이름 · **협력사가 고르는 이름들(`pick_names`, 한 줄에 여러 개)** · 협력사 목록에 보임.
- "저장" = 새 판(ACTIVE, 적용 시작일). 발행된 명세서는 옛 판 값을 그대로 갖는다.

### 5.2 협력사 — 새 주문 · 품목 고치기: **"옵션" 칸만 고르기 칸으로 바꾼다**
- **켜지는 조건(2단계 구현)**: 그 협력사에 쓰는 단가표 판(ACTIVE)이 있을 때만 켜진다. 없으면 예전 화면 그대로다(제품명 ▾ = 계산기 이름, 옵션 = 글 칸). 그래서 운영은 단가표를 저장하기 전까지 바뀌지 않는다. 고른 값 요약은 품목 `option_detail` 글에도 적어 우리 직원 · 도면팀 화면이 예전처럼 본다(기준 자료는 `order_item_options`). 옵션 칸 검사는 새 스크립트(`partner-item-options.js`)가 저장 단추 처리보다 먼저(캡처 단계) 하고, 서버(`foms/services/partners/item_options.py`)가 한 번 더 본다.
- 화면은 지금 협력사 새 주문(우리 erporder 틀) 그대로다. 제품 속성 다섯 칸 중 **옵션 칸만** 바뀐다. 내부 · 색상 · 손잡이 · 기타·설치는 지금처럼 글 칸.
  - 통 · 문 그림 · TYPE 칩 · 손잡이 칩 · 요약 상자는 넣지 않는다.
- 옵션 칸을 누르면 우리 계산기의 여러 개 고르기 창(`ErpSpecPicker.openMulti`, 검색 · 묶음 · 체크)이 열린다. 목록 = 협력사 단가표 옵션 줄의 `pick_names`(비면 `partner_label` — 금액 없음) + 맨 위 "옵션 없음" · "상담 후 정함" + 맨 아래 "커스텀 (직접 적기)".
- 고른 것은 옵션 칸 안에 한 줄씩: 이름 · 수(−/+) · 단위 · 위치(선택, 한 줄 글) · ×. 커스텀은 글 한 줄. 끝에 "+ 옵션 더 고르기". 휴대폰은 이름 · × 한 줄, 수 · 위치 다음 줄.
- **휴대폰(768px 미만) 제품 속성 다섯 칸은 두 줄**: 이름(내부 · 색상 · 옵션 · 손잡이 · 기타·설치)은 작은 글씨(11px)로 위, 입력 칸은 아래 한 줄을 꽉 채운다(이름이 왼쪽에 있으면 입력 칸이 너무 작다). 협력사 화면 CSS 에만 둔다(우리 직원 화면은 그대로).
- 제품명 ▾ 목록 = 단가표 기본 제품 줄의 `pick_names` 를 카테고리별로 묶고, 이름은 하나씩 따로 보인다(몰딩 여닫이 · 무몰딩 여닫이 · 아라 01 …). 예전 계산기 이름 목록 대신 쓰고, 고르기 창은 그대로다.
- **옵션 칸은 꼭 채워야 한다**: 비어 있으면 저장할 때 화면이 그 품목으로 옮겨 가 빨간 테두리와 "옵션을 골라 주세요. 없으면 '옵션 없음'"을 보인다. "상담 후 정함"은 첫 도면 전까지 고칠 수 있고, 도면 확인 때 꼭 골라야 확정된다.
- 사진은 예전처럼 붙인다(도면팀 참고). 고칠 수 있는 때는 1장 3번 규칙(`partner_edit_open`) 그대로다. 저장하면 `PARTNER` · `CURRENT` 두 기록을 함께 쓴다.

### 5.3 우리 도면팀 — 도면 전달 창에 "옵션 확인"
- **3단계 구현(11-03)**: 도면 작업실 "도면 전달" 창(PC · 폰 같은 창, `#dwTransferModal`)에만 붙였다(`static/js/drawing/partner-option-review.js`, 읽기 `GET /api/orders/<id>/partner-options`). 대시보드 전달 창 · 태블릿 "시트 전달"은 옵션 칸 없이 보내고, 이때 `CURRENT` 는 협력사가 고른 값 그대로 남는다.
- 품목마다 `CURRENT` 옵션 목록을 보여 주고 고칠 수 있게 한다(같은 고르기 부품). 바꾼 품목은 이유 한 줄이 꼭 있어야 하고, 그 이유는 그 품목의 바뀐 줄 모두에 붙는다.
- `state = later` 인 품목이 있으면 "옵션이 아직 안 정해진 품목이 있어요" 경고(전달은 막지 않음 — 협력사가 도면 확인 때 고른다).
- 전달 처리(1장 5번)와 같은 트랜잭션에서 CURRENT 를 저장한다.

### 5.4 협력사 — 도면 확인
- **3단계 구현(11-03)**: 도면 탭 최종 도면 아래 "옵션" 칸(`templates/partner/partials/order_options.html`). "상담 후 정함" 품목은 도면 확인 차례에만 고르는 칸이 된다. 고른 값은 "이대로 만들어 주세요" 요청(`options`)에 실려 같은 트랜잭션에서 `CURRENT` · `PARTNER` · `CONFIRMED` 에 쓰인다(`approve_partner_drawing` → `confirm_partner_options`). 홈 "내 차례" 목록의 승인 단추는 고를 품목이 남아 있으면 409 를 돌려주고, 주문 화면 도면 탭에서 고르라고 안내한다. 옵션 지문은 감사 `PARTNER_DRAWING_APPROVED` 의 `options_fingerprint`.
- 도면 아래 "옵션" 칸: `CURRENT` 목록을 보여 주고, `PARTNER` 원문과 다른 줄은 "바뀐 옵션"으로 이유와 함께 보여 준다.
- "이대로 만들어 주세요" = 기존 `approve_partner_drawing` + 같은 트랜잭션에서 `CURRENT` → `CONFIRMED` 복사. 감사 기록에 옵션 지문(sha256)과 도면 회차를 남긴다.
- "수정 요청"은 지금 그대로.

### 5.5 우리 CS — 발행 대기 · 명세서 만들기 (`/erp/partner-statements`)
- 목록: 도면 확정(CONFIRMED 있음) 주문, 출고일 가까운 순. 내일 출고 · 다음 출고 · 출고일 없음 세 갈래로 나눈다. 초안 상태 = 자동 완성 / 커스텀 금액 필요. "자동 완성만 한꺼번에 발행".
- 명세서 화면: 왼쪽 확정 도면(제품별 탭), 오른쪽 묶음별 줄(자동 줄은 글자 · "고치기", 커스텀 줄만 금액 칸). 단가를 고치면 원래 값 · 이유가 남는다(`edited`).
- 발행: 일자(출고일) · 번호 · 잠금 · 잔액 스냅샷 · 협력사 화면에 보임. 수정본 · 취소(VOID)는 이유 필수.
- **4단계 구현(11-03)**: 화면 `/erp/partner-statements`(ERP 하위 메뉴 "협력사 명세서" — 정책 `PARTNER_STATEMENT` 로 숨김) · 한 장 `/erp/partner-statements/<id>` · 양식 `/<id>/print`(`templates/partner/statement_form.html`, 공급받는자용 · 공급자용 2장). API `/api/partner-statements`(`foms/api/partner_statements_staff.py`). 권한 = ADMIN, 또는 CS 권한 팀(회계팀 포함)의 STAFF · MANAGER(게이트 `statements.can_manage_statements`). 일자 = 출고 대시보드와 같은 시공일, 단가표 판 = 적용 시작일이 그 날 이전인 가장 새 판. 갈래는 "내일까지 출고(지난 날 포함) · 다음 출고 · 출고일 없음". 발행은 사람이 누른다(열린 질문 7 기본값). 잔액은 발행 명세서 합 − 입금 합(5단계).

### 5.6 협력사 — 거래명세서 메뉴
- 월 장부: 지난달 이월 · 이달 판매 · 이달 입금 · 지금 잔액. 줄 = 일자 · 문서번호 · 고객(현장) · 제품 수 · 판매 · 입금 · 잔액 · 상태(새 명세서 · 확인함 · 입금 대기 · 수정본). 제품 여러 개 주문은 ▾ 로 제품별 금액. 엑셀 받기.
- 명세서 보기: 양식(5.8) + 오른쪽 제품별 최종 도면 + "명세서 확인했어요" + "금액 문의"(줄 골라 묻기) + 인쇄(공급받는자용 · 공급자용 2장) · PDF(브라우저 인쇄). 휴대폰은 제품 묶음 접기 · 입금 계좌 복사.
- 주문 화면에도 "거래명세서" 탭.
- **4단계 구현(11-03)**: 메뉴 "거래명세서"(PC 메뉴 줄 · 휴대폰 더보기) → `/partner/statements`(월 장부 — 이월 · 이달 판매 · 이달 입금 · 지금 잔액, 제품 여러 개는 ▾) · `/partner/statements/<id>`(양식 한 장 + 최종 도면 + 확인했어요 + 금액 문의 · 입금 계좌 복사, 처음 열면 `partner_viewed_at`) · `/<id>/print`(2장, 온라인 원본 QR). 주문 화면 "거래명세서" 탭은 발행 명세서가 있을 때만. 우리 CS 는 명세서 화면에서 문의에 답한다(발행함 목록에 "답할 문의 N"). 로직 `foms/services/partners/statement_partner.py`, API `foms/api/partner/statements.py`, 화면 `foms/web/partner/statements.py`. 엑셀 받기 · 이달 입금은 5단계에서 채웠다. 휴대폰 양식은 계산 근거 칸을 숨긴다(인쇄 · PC 에는 있다).

### 5.7 입금 · 출고
- CS 입금 기록 화면: 날짜 · 금액 · 메모 · 명세서 맞추기. 지우기는 이유 필수.
- 출고 대시보드(1장 9번): 그 명세서 금액만큼 입금이 아직 다 들어오지 않은 협력사 주문 카드에 "입금 대기"를 붙인다. 막지는 않고 표시만 한다.
- **5단계 구현(11-03)**: 표 `partner_payments`(마이그레이션 `ppay_00`, 금액 > 0 · 지우기는 줄을 남기고 이유만). 로직 `foms/services/partners/payments.py` — 잔액 = 발행 합 − 지우지 않은 입금 합(다음 명세서 전일 잔액에 그대로 들어간다), 명세서별 받은 돈 = 고른 입금은 그 명세서, 고르지 않은 입금은 일자가 오래된 덜 받은 명세서부터 채운다(넘치면 다음으로). 우리 CS 화면 `/erp/partner-statements` 의 "입금" 칸(API `/api/partner-payments`, 정책 `PARTNER_STATEMENT`). 출고 대시보드(PC 표 · 태블릿 표) 고객 칸에 "입금 대기". 월 장부 받기는 CSV(엑셀로 열림 — 저장소 관례대로 UTF-8 BOM · CRLF · 콤마 없는 정수, 새 라이브러리 없음), 협력사 `/partner/statements/export.csv` 와 CS `/api/partner-payments/export.csv` 가 같은 값. 협력사 월 장부에는 입금 줄이 날짜 순으로 섞이고 발행본을 다 받지 못했으면 상태에 "입금 대기".

### 5.8 양식 칸 (이카운트 양식 + 조사로 더한 것)
문서번호 · 발행일 · 출고일 · 담당자 · 쪽 · QR(온라인 원본) · 공급받는자 / 공급자 블록(등록번호 · 상호 · 성명 · 주소 · 업태 · 종목) · 도장 · 합계 금액(한글 + 숫자) · 공급가액 / 세액 · "단가는 VAT 포함" · 현장(고객) · 주문번호 · 최종 도면 회차 · 제품 묶음 · 소계 · 기본 포함 비고(내부 · 깊이 줄임) · 계산 근거 칸 · 전일 잔액 / 판매 합계 / 금일 잔액 · 입금 계좌 · 입금 기한(출고 전날 16:00) · 받는 쪽 확인(누가 · 언제, 온라인) · 세금계산서 발행 안내 · 주의 문구 · 공급받는자용 / 공급자용.

## 6. 권한

- 협력사: 자기 회사 명세서 중 ISSUED · VOID 만(DRAFT 는 안 보임). 자기 회사 주문의 옵션 읽기 · 고르기(고칠 수 있는 때만). 단가표는 고르는 이름(`pick_names` · `partner_label`)만 받는다 — 금액은 발행 명세서에만.
- 우리: 명세서 만들기 · 발행 · 입금 기록 = CS 팀 + ADMIN(새 정책 id `PARTNER_STATEMENT`). 단가표 = ADMIN. 옵션 확인 = 도면팀 + ADMIN.
- 새 협력사 라우트는 허용 목록 + 매니페스트 2개 + "다른 회사 주문 · 명세서로 부르면 거부" 시험을 1:1 로 둔다(선행 설계서 §11).
- 감사 기록: 단가표 저장 · 옵션 확정 · 발행 · 수정본 · 취소 · 입금 · 입금 지우기.

## 7. 단계 (각 단계 끝마다 deploy · 스테이징 실화면)

1. **단가표** — 3.1 표 · 편집기 · HTML 불러오기 · 판 저장. 계산 함수(4장)와 시험.
2. **협력사 옵션 고르기** — 3.2 표 · 새 주문 / 품목 고치기 · 제품명 목록 바꿈 · 보내기 막기 · 휴대폰.
3. **도면팀 옵션 확인 + 협력사 도면 확인의 바뀐 옵션** — 전달 창 · CONFIRMED 스냅샷.
4. **명세서** — 3.3 · 3.5 표 · 초안 계산 · CS 발행 대기 / 만들기 · 발행 · 수정본 · 협력사 목록 / 보기 / 인쇄 · 문의.
5. **입금 장부** — 3.4 표 · 입금 기록 · 잔액 · 출고 대시보드 배지 · 월 장부 엑셀.

## 8. 검증 (완료 기준)

- `python -c "import app; print('APP_OK')"`.
- 계산 시험(순수 함수): 자 수 경계(12.33 → 12.3 · 9.33 → 9.3 · 12.35 → 12.4 · 가로 3,000 → 10.0), 복합 폭 합, 구간 경계(900 · 901), 넘친 만큼(구간 최대 900 에서 가로 1000 → 1번 · 1001 → 2번), 원 단위 · 공급가액 · 세액 합 일치, 취소 품목 빠짐, 기본 포함 줄은 줄 없이 비고에만(값이 생긴 판에서는 줄이 됨).
- 스냅샷 시험: 단가표 새 판 저장 뒤 옛 발행 명세서 값 그대로. 발행본 고치기 409 · 수정본만 가능.
- 권한 시험: 문지기 전 라우트 래칫(`tests/security/test_partner_gate.py`) 초록, 다른 회사 · 내부 주문 명세서 · 옵션 거부(자기 회사는 200 — 음성 대조군), DRAFT 명세서 협력사에게 안 보임.
- 우리 주문 화면 저장(PUT structured) 뒤에도 `order_item_options` 그대로(대조군).
- PG 레인: 새 표와 그 FK 대상 표(orders · partner_orgs · drawing_revisions)를 `create_all(tables=[...])` 을 쓰는 PG 시험 2파일의 목록에 함께 넣는다(알려진 함정). `alembic upgrade head → downgrade -1 → upgrade head` 로컬 PG 왕복.
- `scripts/ops/pre_push_smoke.ps1` exit 0, push 뒤 CI 초록.
- 스테이징 실화면(시험 협력사 `CLAUDE-TEST-협력사` · 가짜 주문 `CLAUDE-TEST-`): 옵션 고르기 → 도면 전달(옵션 하나 고침) → 협력사 도면 확인에 바뀐 옵션 → 확정 → CS 발행 → 협력사 명세서 보기 · 확인했어요 → 입금 기록 → 출고 배지 사라짐. PC 1440 · 휴대폰 390.

## 9. 열린 질문 (구현 전에 정할 것)

답이 난 질문은 지웠다. 번호는 그대로 둔다(4장 `meter` 줄이 "열린 질문 10"을 가리킨다).

- **5.** 협력사 단가표는 하우드 시트만인가(라홈 시트는 누구 것인가).
- **7.** 명세서 발행: 사람이 누른다(기본) / 출고 전날 자동 발행.
- **8.** 세금계산서 안내 문구(언제 · 어떻게 발행하는지).
- **9.** 문서번호 머리 `HD-` 그대로인가.
- **10.** m 단가 수량의 소수 자리.

## 10. 남는 위험

- 협력사 입력이 늘어 거부감이 생길 수 있다 → 공지 + "상담 후 정함" + 위치 메모로 사진 붙이던 습관을 살린다.
- 도면팀이 옵션 고치기를 잊음 → 협력사 도면 확인의 "바뀐 옵션"이 마지막 그물. 전달 창에서 옵션 확인 체크를 필수로 할지는 3단계에서 실화면으로 정한다.
- 단가표 줄 열쇠가 끊기면 옛 선택이 고아가 된다 → 새 판은 복사로만 만들고 지우기는 `pickable=false`.
- 저장소 공개: 단가 · 업체 정보는 DB 에만 둔다. 시험 자료는 가짜 값.
- 동시에 발행하면 같은 날 순번이 겹칠 수 있다 → 번호는 발행 트랜잭션 안에서 협력사 · 날짜 줄을 잠그고 낸다.

## 11. 바꾸지 않는 것

- 소비자 계산기 값 · 계약 시험(`tests/contracts/wdcalculator/`).
- 우리 직원 주문 화면 · 저장 API · 단계 흐름(승인 · 수정 요청 서버 동작은 그대로 쓰고 옵션 스냅샷만 더한다).
- 협력사 고객 발송 차단 · 문지기 기본 거부 구조.
