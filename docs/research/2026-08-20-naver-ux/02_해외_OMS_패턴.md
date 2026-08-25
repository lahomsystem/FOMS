# 해외 OMS·멀티채널 출고 SaaS 화면 설계 패턴 조사

조사일: 2026-08-20
조사 대상(6개): **ShipStation**, **Linnworks**, **Veeqo**, **Brightpearl**, **Shopify Admin Orders / Polaris**, **Zoho Inventory**, 보조로 **Amazon Seller Central Manage Orders**
목적: 국내 서비스 조사와 대조해 FOMS "수집 주문 확인 작업대(collected-order triage workbench)" 화면 설계 근거 확보

## 근거 신뢰도 표기 규칙
- **(원문)** = 해당 URL을 직접 fetch해서 본문에서 확인한 내용
- **(스니펫)** = 해당 URL이 fetch 차단(403/401)이라 검색엔진이 노출한 그 페이지의 발췌로만 확인. 인용문은 발췌 수준이므로 토씨까지 정확하다고 보증하지 않음
- **확인 불가** = 찾지 못함. 추측으로 채우지 않음

> fetch 차단 도메인: `help.shipstation.com`(403), `help.brightpearl.com`(401), `community.shipstation.com`(403). 이 3곳 관련 서술은 대부분 (스니펫)이다.

---

## 1. 작업 큐(Queue) 패턴 — "처리해야 할 주문"을 주는 화면 구조

### 결론 먼저
조사한 6개 제품 어디에도 **"슬라이드오버(slide-over)를 표준으로 한다"는 문서는 없었다**. 실제 표준은 두 층이다.

- **1층 = 리스트(그리드)가 집(home)이다.** 작업자는 리스트를 떠나지 않는 것이 기본이고, 리스트는 절대 사라지지 않는다.
- **2층 = 상세는 "리스트 옆 패널" 또는 "전체 페이지" 둘 중 하나**이며, 두 개를 **동시에 제공**하고 용도를 나눈다(가벼운 처리=패널, 무거운/예외 처리=전체 페이지).

### 제품별 사례

**ShipStation — 3단계 점층 구조(가장 참고할 만함)**
같은 주문을 세 가지 깊이로 볼 수 있게 해 놓았다.
1. **행 인라인 확장**: "Multi-item Order View" — 여러 품목이 든 주문을 그리드 안에서 펼쳐, **Order Details를 열지 않고** 라인아이템 전부를 본다. (스니펫)
   https://help.shipstation.com/hc/en-us/articles/48668385552027-Feature-Updates-in-ShipStation-s-New-Layout
2. **우측 사이드바 작업 패널**: Orders grid에서 주문을 선택하면 우측 **Shipping Sidebar**에 **Configure Shipment Widget**이 뜨고 무게·서비스·패키지·보험을 입력한다. 사이드바가 안 보이면 **"Show Sidebar"** 체크박스로 켠다. 즉 **그리드를 떠나지 않고 처리 완료**가 설계 의도다. (스니펫)
   https://help.shipstation.com/hc/en-us/articles/360026157591-Configure-Shipping
3. **전체 페이지 상세**: 주문번호 클릭 또는 행 더블클릭 → Order Details. (스니펫)
   https://help.shipstation.com/hc/en-us/articles/360025869052-View-Search-and-Sort-Orders

  좌측에는 **상태별 뷰 목록 사이드바**가 상시로 있다("The sidebar of the Orders grid displays the various order statuses your orders could be in"). 즉 **좌=큐 선택 / 중앙=리스트 / 우=작업 패널**의 3분할. (스니펫)

**ShipStation — 전체 페이지 상세를 "shipping workbench"로 재정의한 이유 (명시된 장점)** (원문)
https://www.shipstation.com/blog/order-details-page/
- 좌측 메뉴로 Shipments / Returns 이동, 좌측 메뉴 안에 **order summary panel**이 영수증 역할.
- 명시된 장점: **"focusing on the shipment at hand, eliminating any confusion with other shipments, such as back-ordered items."** → 전체 페이지 상세의 존재 이유는 "**한 건에만 집중시켜 혼동을 없앤다**"이다.
- 또 하나: "refer back to the original order seamlessly ... without the hassle of toggling between different systems" → **컨텍스트 전환 비용 제거**.
- 즉 ShipStation은 *사이드바 = 속도*, *전체 페이지 = 집중/무오류* 로 역할을 갈랐다.

**Shopify Admin / Polaris — 리스트는 "훑어보기", 상세는 전체 페이지** (원문)
https://shopify.dev/docs/api/app-home/patterns/compositions/index-table
- Index table의 정의부터가 이렇다: 같은 타입 객체 컬렉션을 보여주고 "**at-a-glance view**"를 준 다음 "**perform actions or navigate to a full-page representation of it**".
- 리스트를 깨끗하게 유지하는 장치: **"Reveal row actions on hover"** — 행 액션을 상시 노출하지 않고 hover 시에만 드러낸다.
- 구조: 정렬 가능한 헤더 행 + 데이터 행 + 상단 필터 컨트롤 + 검색 필드 + 정렬 popover + 하단 페이지네이션.
- Shopify는 주문 상세에 **슬라이드오버를 쓰지 않고 전체 페이지 이동**을 쓴다.

**Linnworks — 단일 그리드 + 뷰가 상세를 흡수** (원문)
https://help.linnworks.com/support/solutions/articles/7000032975-open-orders-custom-views-and-filtering
- 상세 패널을 따로 두는 대신, **뷰(view) 편집에서 "tick the columns and the details within the columns you want to be displayed"** — 즉 컬럼 안에 상세 항목을 접어 넣어 그리드 한 장에서 끝낸다.
- 액션은 **우클릭 컨텍스트 메뉴 / Actions 버튼**으로 붙는다. (원문: locked/parked 문서의 조작 경로)
- 대신 뷰마다 **Hot Buttons**를 얹어 "자주 쓰는 액션"을 뷰 안에 상주시킨다.
  https://help.linnworks.com/support/solutions/articles/7000035513-open-orders-working-with-open-orders

**Zoho Inventory — 목록 + 커스텀 뷰 드롭다운**, 상세는 문서(sales order) 전체 페이지. (원문)
https://www.zoho.com/us/inventory/help/sales-orders/sales-order-managing.html

### 각 방식의 "명시된" 장단점
OMS 제품 문서는 장단점을 이론적으로 정리해 두지 않는다. **명문화된 유일한 출처는 Microsoft의 List/details 패턴 문서**였다. (원문)
https://learn.microsoft.com/en-us/windows/apps/design/controls/list-details

- **언제 쓰나(= side-by-side의 장점)**: "Locate and prioritize a large collection of content." / "Allow the quick addition and removal of items from a list while **working back-and-forth between contexts**."
  → 즉 list+detail 분할의 본질적 이점은 **대량 컬렉션에서 우선순위를 매기며 앞뒤로 왔다갔다 하는 작업**이다. "수집 주문 확인 작업대"가 정확히 이 유형이다.
- **폭 기준 전환 규칙(수치 명시)**: 320–640epx → **Stacked**, 641epx 이상 → **Side-by-side**.
- **Stacked의 단점 서술**: "To the user, it appears as though the list and details views exist on two separate pages." → 좁은 화면에서는 분할을 억지로 유지하지 말고 페이지 2장처럼 드릴다운시키라는 뜻.
- 보조: 마스터-디테일 패턴 일반론(목록/개요와 상세를 분리하면 사용자가 전체 목록 내 자기 위치를 잃지 않고 깊이 파고들 수 있음). https://en.wikipedia.org/wiki/Master%E2%80%93detail_interface

### 확인 불가
- "슬라이드오버 vs 전체 페이지"를 비교해 **명시적으로 우열을 선언한 OMS 공식 문서**는 찾지 못했다.

---

## 2. 일괄(bulk) 처리 vs 건별 처리

### 결론 먼저
**체크박스 다중선택 + (선택 시 나타나는) 액션바가 명백한 표준**이다. 건별 인라인 액션은 이를 대체하지 않고 **hover 시에만 드러나는 보조 수단**으로 공존한다.
되돌릴 수 없는 액션의 처리는 **3중 방어**로 수렴한다: ① 자격 없는 행은 애초에 비활성 ② 모달 확인 ③ 되돌릴 수 없음을 문서·문안으로 명시 + 사후 복구 경로 안내.

### 제품별 사례 — 선택과 액션바

**Shopify Polaris / app-home index table** (원문)
https://shopify.dev/docs/api/app-home/patterns/compositions/index-table
- **"Use checkboxes for bulk selection"**
- 선택하면 **bulk action bar가 나타나 선택 건수와 가능한 액션을 표시**한다.
- 부분 선택에는 **indeterminate 체크박스 상태**.
- **"Reveal row actions on hover"** — 건별 액션은 hover로만.
- 페이지 넘어가는 선택(selection across pages) 예제를 별도로 제공.
  https://polaris-react.shopify.com/components/tables/index-table?example=index-table-with-bulk-actions-and-selection-across-pages
- 알려진 함정: 페이지네이션된 index table에서 bulk action이 기본으로 전체 행을 선택해 버리는 이슈가 보고돼 있다(선택 범위의 모호성이 실제 버그로 이어진 사례).
  https://github.com/Shopify/polaris-react/issues/11786

**Veeqo — 액션바에 "같은 값 일괄 덮어쓰기"를 모아 둠** (스니펫)
https://help.veeqo.com/en/articles/3802783-shipping-your-first-order
- 좌측 체크박스로 건별 선택, 헤더 체크박스로 페이지 전체 선택.
- 테이블 상단 액션바: **Edit packages**(선택분이 전부 같은 무게·치수일 때) / **Edit services** / **Edit ship date** / **Buy labels**(선택 전부 한 번에 구매).
- **한 번에 최대 100건**까지 일괄 출고.
- 시사점: 일괄 액션의 정체는 "**여러 건에 같은 값을 덮어쓰기**"다. 값이 건마다 다르면 일괄이 성립하지 않는다는 걸 UI가 전제(“if all selected orders require the same weight and dimensions”)하고 있다.

**Linnworks — 액션바 대신 우클릭 컨텍스트 메뉴** (원문)
https://help.linnworks.com/support/solutions/articles/7000029276-open-orders-locked-and-parked-orders
- "Select the orders you want to lock/unlock/park/unpark" → "**Right-click on any of the select orders or click on the _Actions_ button**" → "Select _Other Actions_ > _Change Status_ > select the needed action".
- 즉 **선택 → 우클릭/Actions 버튼 → 계층 메뉴**. 데스크톱 그리드 관용구를 그대로 가져온 형태.

**Zoho Inventory — 선택 후 More Actions** (원문)
https://www.zoho.com/us/inventory/help/sales-orders/sales-order-managing.html
- "Select any two sales orders to merge" → "Click **More Actions** and select **Merge Sales Orders**".
- 일괄의 한계도 명시: 대량 취소 시 라인아이템·수량은 못 고치고 개별 주문을 열어야 한다.

**Amazon Seller Central** (스니펫)
- Unshipped 탭에서 주문 선택 후 **Confirm Shipment(s)** → 캐리어·송장번호 필수 입력.
- 다만 **일괄 취소는 화면이 아니라 Order Cancellation 업로드 파일**로 처리한다(위험 액션을 화면 일괄에서 빼서 파일 업로드로 밀어낸 사례).
  https://sell.amazon.com/blog/amazon-order-management

### 되돌릴 수 없는 액션의 확인 UX

| 방어층 | 사례 | 근거 |
|---|---|---|
| ① 애초에 못 누르게 함 | Amazon: **"Pending orders are grayed out and non-actionable"** — 결제 검증 전에는 Confirm shipment / Cancel order 버튼 자체가 비활성. 검증되면 활성화됨 (스니펫) | https://sellercentral.amazon.com/seller-forums/discussions/t/10ea2d73-176e-46ab-8bd9-00f342535a03 |
| ① 애초에 못 누르게 함 | Linnworks: 미결제 주문은 자동 **Parked** + 회색 처리, "cannot be edited without being unlocked or unparked" (원문) | https://help.linnworks.com/support/solutions/articles/7000029276-open-orders-locked-and-parked-orders |
| ② 모달 확인 | Shopify app-home 패턴: **"Modal API for confirming destructive bulk operations"** — 파괴적 *일괄* 작업에 모달 확인을 명시적으로 지정 (원문) | https://shopify.dev/docs/api/app-home/patterns/compositions/index-table |
| ② 모달 확인 + 문안 | Zoho Inventory 주문 병합: **"You will not be able to undo this action"** 을 확인 단계에 노출(자식 주문이 영구 삭제됨) (원문) | https://www.zoho.com/us/inventory/help/sales-orders/sales-order-managing.html |
| ③ 불가역 명시 + 복구 경로 | ShipStation Void Label: 라벨을 void하면 **unvoid 불가**("cannot be unvoided")를 전용 도움말 문서로 못박음. 대신 void 후 주문은 Shipped → **Awaiting Shipment로 자동 복귀**시켜 "다시 라벨 만들기/발송처리/취소" 경로를 열어 준다 (스니펫) | https://help.shipstation.com/hc/en-us/articles/360045435052-Can-I-unvoid-a-label , https://help.shipstation.com/hc/en-us/articles/360026157751-Void-Labels |
| ③ 우회 경로로 되돌림 | Veeqo: void 기능 자체가 없고 **delete shipment**만 있음. 14일 이내 미사용 라벨이면 캐리어 환불 요청을 자동 트리거 (스니펫) | https://help.veeqo.com/en/articles/15602027-shipping-in-veeqo-uk |
| 액션 후 피드백 | Shopify app-home: 액션 확인 피드백에 **Toast API** 사용을 지정 (원문) | https://shopify.dev/docs/api/app-home/patterns/compositions/index-table |

**핵심 관찰**: 가장 강한 방어는 확인 대화상자가 아니라 **"자격 없는 행은 목록에 보이되 손댈 수 없게 만드는 것"**이다. Amazon과 Linnworks가 서로 독립적으로 같은 답(회색 처리 + 액션 비활성)에 도달했다.

---

## 3. 상태 모델 표기 — 축이 여러 개일 때 목록에서 압축하는 법

### 결론 먼저
성숙한 제품일수록 **"필터는 축별로 완전히 분리하고, 목록 행에서는 주축 배지 1개 + 부축 아이콘/점 n개로 압축"** 한다. 축을 하나로 뭉개 평탄화한 제품(Veeqo)도 있으나, 그 결과 상태 목록이 이질적인 것들의 나열이 된다.

### 제품별 사례

**Shopify Admin — 축을 7개 이상으로 완전 분리 (가장 극단적·가장 명확)** (원문)
https://help.shopify.com/en/manual/fulfillment/managing-orders/viewing-orders/filtering-orders
필터 카테고리와 값이 축별로 따로 존재한다(원문 발췌):
- **Payment status**: Authorized, Due, Expired, Paid, Partially paid, Partially refunded, Pending, Refunded, Unpaid, Voided
- **Fulfillment status**: Fulfilled, Unfulfilled, Partially fulfilled, Scheduled, **On hold**, Request declined
- **Delivery status**: In transit, Out for delivery, Attempted delivery, Delayed, Failed delivery, Delivered, Tracking added, No status
- **Return status**: Return requested, Return in progress, Return closed
- **Order status**: Open, Archived, Canceled
- **Label status**: No label, Draft created, Purchased, Printed
- **Chargeback and inquiry status**: Open, Submitted, Won, Lost
- **Fraud risk**: High, Medium, Low

→ 주목: **"결제"와 "이행"과 "배송"과 "예외"가 절대 한 축에 섞이지 않는다.** 그리고 목록 행에서는 이 축들을 Polaris **Badge**로 압축해 보여준다.

**Brightpearl — 축 분리를 문서로 명시** (스니펫)
https://help.brightpearl.com/hc/en-us/articles/211131446-Sales-Order-Statuses-Workflow
- **"Sales order statuses are for managing your own unique business sales cycle"** 이고, 별도로 **"Brightpearl provides separate statuses to represent the inventory, shipping and invoice status of an order, enabling you to search and view orders on any combination of these statuses."**
  → **커스텀 워크플로 축(사업 고유) + 시스템 축 3개(재고/배송/인보이스)** 라는 2계층 구조. 우리처럼 "가구 실측→도면→시공"이라는 **고유 축**을 가진 업무에 그대로 대응된다.
- 배송 축은 아이콘으로: "Every order has a shipping status indicated by the **shipping status icon**, which is automatically updated as items are marked as shipped on goods-out notes." (스니펫)
  https://help.brightpearl.com/hc/en-us/articles/211131426-Overview-of-sales-shipping
- 커스텀 상태에는 **색을 직접 지정**(color wheel)하며, API에도 color 필드가 있다(예: `"#E7E6E4"`). (스니펫)
  https://api-docs.brightpearl.com/order/order-status/post.html
- 재고 축은 계정 간 **고정 코드**다: "Order stock status codes indicate the fulfilment status of a sale, credit or purchase" / "consistent across all Brightpearl accounts" — 즉 **커스터마이즈 가능한 축과 고정 축을 의도적으로 분리**했다. (원문)
  https://api-docs.brightpearl.com/order/order-stock-status/index.html

**Zoho Inventory — 축을 "점(dot) 여러 개"로 압축 (행 압축의 모범 사례)** (원문)
https://www.zoho.com/us/inventory/help/sales-orders/sales-order-managing.html
- 목록 행에 **파랑/초록 점**이 있고, hover하면 **invoiced / packed / shipped** 여부를 알려준다.
- **"If the dots are grey, it means that the process is yet to be commenced."** → 회색 = 미착수.
- 별도로 문서 상태 축은 5개: **Draft / Confirmed / Closed / Void / On Hold**.
- → 즉 **문서 상태는 배지 텍스트로, 진행 3축은 점 3개로**. 컬럼을 3개 쓰지 않고 폭 한 칸에 3축을 우겨넣는 기법.

**Veeqo — 반대 사례: 모든 축을 하나로 평탄화** (원문)
https://help.veeqo.com/en/articles/3802825-order-search-and-filter
- 단일 status 값 목록: **"Payment required, Waiting for stock, Ready to ship, Shipped, Cancelled, Refunded, Amazon to ship, Pending Amazon"**
- 여기엔 **결제 축(Payment required)·재고 축(Waiting for stock)·출고 축(Ready to ship/Shipped)·예외 축(Cancelled/Refunded)·채널 축(Amazon to ship/Pending Amazon)이 전부 한 줄에 섞여 있다.**
- 대신 Veeqo는 축을 필터 쪽으로 밀어냈다: picked status(not picked / picked / picking in progress), 인쇄 여부, 재고 할당(unassigned / partial / fully assigned) 등을 **별도 필터**로 제공.
- 교훈: 평탄화하면 배지는 하나로 단순해지지만, **상태 목록이 "서로 배타적이지 않은 것들의 나열"이 되어** 필터 설계가 곧바로 복잡해진다.

### 접근성 관례
Polaris **Badge** 기준 (스니펫 + 이슈 트래커)
- tone 값: neutral / info / success / warning / critical (+ attention).
- 명시된 원칙: **"Don't rely on color alone to signify whether a value is positive or negative."**
- 아이콘·색으로 정보를 전달하는 배지는 **visually hidden 컴포넌트로 텍스트를 함께 넣어 스크린리더가 읽게** 한다.
  https://polaris-react.shopify.com/components/feedback-indicators/badge
  https://github.com/Shopify/polaris-react/issues/1969
  https://github.com/Shopify/polaris-react/discussions/6579
- **실사용 반증 사례**: ShipStation 신 레이아웃에서 색을 대거 제거하자 사용자가 "**색이 없어서 자꾸 엉뚱한 버튼을 누른다**", "화면이 거의 전부 흰색이라 30분 만에 두통"이라고 보고했다. 색은 없애도 안 되고 색**만** 써도 안 된다는 양방향 제약. (스니펫)
  https://community.shipstation.com/t5/ShipStation-Features/New-Color-Scheme-Problems/m-p/25560

### 확인 불가
- Brightpearl의 shipping status 아이콘 **모양·색 대응표**(help center 401로 원문 미확인).

---

## 4. 예외(Exception) 처리 — 취소·반품·보류·오류 주문

### 결론 먼저
**두 가지 전략이 공존**하며, 성숙한 제품은 둘 다 쓴다.
- **(A) 별도 뷰/탭으로 분리** — 큐를 깨끗하게 유지
- **(B) 같은 목록에 남기되 회색 처리 + 액션 비활성** — "존재는 보이되 손댈 수 없다"

그리고 **공통적으로 예외 주문을 목록에서 완전히 숨기지 않는다.** 숨기면 사라진 줄 알기 때문이다.

### 뷰 이름과 그 안의 액션 제약

**ShipStation — 상태 = 사이드바 뷰. "On Hold"가 1급 상태** (스니펫)
- 좌측 사이드바가 상태별 뷰 목록: **Awaiting Payment / Awaiting Shipment / On Hold / Shipped / Cancelled**.
  https://help.shipstation.com/hc/en-us/articles/360025869712-Understanding-Order-Statuses
- **Hold 액션은 "날짜까지"** 보류한다: "The Hold action puts orders into the **On Hold** status **until a specified date**" — 선주문·품절·기타 사유로 미룰 때 쓰고, **그 날짜가 되면 자동으로 Awaiting Shipment로 되돌아온다.**
  https://help.shipstation.com/hc/en-us/articles/360026156911-Hold-Assign-and-Cancel-Orders
- 액션 제약의 부수효과: Shopify에서 On Hold 상태로 들어온 주문은 **품목 수량이 0으로 설정**되고 상태가 바뀌어야 정상화된다.
- → 배울 점: **보류에 "해제 조건"을 붙여 자동 복귀시킨다.** 보류가 블랙홀이 되지 않는다.

**Linnworks — "Parked / Locked" 2종의 예외 잠금 (가장 정교함)** (원문)
https://help.linnworks.com/support/solutions/articles/7000029276-open-orders-locked-and-parked-orders
- 표시: **"Locked orders will also display as greyed out in the _Open Orders_ screen."**
- 제약: **"_Locked_ or _Parked_ orders cannot be edited without being unlocked or unparked."**
- **Parked와 Locked의 의미 차이가 재고에 있다**:
  - Parked → "the items in the order **continue to affect** the available stock level calculations"
  - Locked → "the items in the order **do not** affect the available stock level calculations"
  → 즉 예외 플래그가 단순 UI 표식이 아니라 **하류 계산에 참여하느냐 마느냐**를 가른다.
- 자동 파킹 사유(원문): 모든 **Unpaid** 주문 자동 Parked / Fulfillment Centre 위치 / **Amazon FBA 위치로 이동 시 자동 locked+parked** / eBay PayPal 보안 이슈 / **Shopify 사기 조사 또는 취소 플래그** / **배송 우편번호 11자 초과**.
  → 데이터 품질 문제(우편번호 길이)까지 예외 큐로 밀어내는 게 인상적이다.
- 미결제 주문 서술: 미결제 주문은 회색 처리되고 기본 Parked라 **"실수로 처리되지 않게"** 한다. 채널에서 결제·고객정보가 갱신되면 **자동 unpark**. (스니펫)
  https://help.linnworks.com/support/solutions/articles/7000021888-open-orders-working-with-unpaid-orders
- 조직 차원 가드: **Settings > General Settings > Order Settings > Error Prevention > Pre Processing** 에 "미결제 주문 처리 금지" 설정이 별도로 있다. (스니펫)

**Amazon Seller Central — "Pending" 탭 + 비활성 행** (스니펫)
- Manage Orders에 **Pending 탭**이 따로 있고, 상태 필터는 Unshipped / Pending / Shipped.
- **"Pending orders are grayed out and non-actionable"** — 결제 검증 전에는 확인/취소 불가. 검증되면 Confirm shipment / Cancel order 버튼이 활성화되고 그때서야 리포트에도 나타난다.
  https://sellercentral.amazon.com/seller-forums/discussions/t/10ea2d73-176e-46ab-8bd9-00f342535a03
  https://www.sellermate.ai/post/amazon-manage-orders-pending-guide

**Shopify — 예외를 "축"으로 두고 큐에서 빼는 건 Archive로** (원문)
https://help.shopify.com/en/manual/fulfillment/managing-orders/viewing-orders/filtering-orders
- Order status 축이 **Open / Archived / Canceled** 3값. 처리 끝난 주문은 **Archive** 해서 기본 큐에서 뺀다(삭제가 아니라 큐 이탈).
- 예외성 값들이 각 축 안에 정식 값으로 존재: Fulfillment의 **On hold**, **Request declined**, Delivery의 **Delayed / Failed delivery / Attempted delivery**, Return 축 전체, Chargeback 축 전체, Fraud risk 축.
- → 예외는 "탭"이 아니라 **필터 값**이고, 자주 쓰는 조합을 **저장된 뷰(탭)** 로 승격시키는 구조.

**Veeqo** — Cancelled / Refunded를 상태값으로 두고 별도 필터로 뽑음. (원문)
https://help.veeqo.com/en/articles/3802825-order-search-and-filter

**Zoho Inventory** — 문서 상태에 **Void**(수동 무효화)와 **On Hold**(미청구 백오더 PO가 있을 때) 존재. (원문)

---

## 5. 키보드·대량 처리 효율 (파워유저 기능)

### 결론 먼저
**저장된 뷰(saved views)는 조사한 전 제품이 갖고 있는 사실상의 필수 기능**이고, **키보드 단축키는 제품마다 편차가 크다**. 특히 `j`/`k` 같은 행 이동 단축키는 **어느 공식 문서에서도 확인하지 못했다** — OMS는 이메일 클라이언트식 행 내비게이션을 쓰지 않는 것으로 보인다.

### 단축키

**ShipStation — 가장 발달함 + 바코드 연동 (스니펫)**
- **Basic hotkeys**(항상 활성) / **Advanced hotkeys**(계정 기본 활성, on-off 가능) 2종 체계. 목록은 **Help 메뉴 > Hotkeys**.
  https://help.shipstation.com/hc/en-us/articles/360051509071-Can-I-customize-my-ShipStation-account
- 예: 주문이 선택된 상태에서 **`s`** 를 누르면 라벨이 생성된다. (커뮤니티 스니펫)
  https://community.shipstation.com/t5/ShipStation-Features/Create-Print-Hotkey/m-p/11753
- **Shipping Presets에 hotkey를 배정**해 Orders grid에서 키 조합만으로 프리셋(캐리어·서비스·패키지 묶음)을 적용. 게다가 **"Print Hotkeys and Barcodes"** 로 그 hotkey를 **바코드로 인쇄해 스캐너로 적용**할 수 있다 — 스캐너를 키보드처럼 쓰는 경로.
  https://help.shipstation.com/hc/en-us/articles/360036323651-Use-Shipping-Presets
- 레거시에는 전용 리포트까지 있었다: Analytics > Reports > Hotkey and Barcode Scan Actions.
  https://help.shipstation.com/hc/en-us/articles/4403830407067-Analytics-Reports-Hotkeys-Barcode-Scan-Actions
- **회귀 사례(중요)**: 신 레이아웃(V3)에서 hotkey가 후퇴하자 "Bring hotkeys (keyboard shortcuts) back for V3", "Advanced Hotkey Support and New Layout", "Change Hotkeys" 등 별도 요청 스레드가 쌓였다. **파워유저에게 단축키 제거는 곧 성능 회귀로 인식된다.** (스니펫)
  https://community.shipstation.com/ideas/bring-hotkeys-keyboard-shortcuts-back-for-v3-3616
  https://community.shipstation.com/t5/New-Layout-Feedback/Advanced-Hotkey-Support-and-New-Layout/idi-p/12987

**Shopify Admin — 디스커버리 중심** (원문)
https://help.shopify.com/en/manual/shopify-admin/productivity-tools/keyboard-shortcuts
- **`?`** 로 단축키 목록 열기, **`esc`** 로 닫기. 테마 에디터는 `ctrl`/`cmd` + `/`.
- 시퀀스형 단축키(예: `A` `P` = add product)이며 **"The complete sequence of keys must be typed within about 1 second"**, 키는 표시된 순서대로 눌러야 한다.
- 전역 검색은 `ctrl`/`cmd` + `K`. (스니펫)
- **목록 행 선택·이동·일괄 액션에 대한 단축키는 이 문서에서 확인 불가.**

**Linnworks** — 단축키 대신 **Hot Buttons**(뷰마다 자주 쓰는 액션을 버튼으로 상주)라는 다른 답을 냈다. (원문)
https://help.linnworks.com/support/solutions/articles/7000032975-open-orders-custom-views-and-filtering

### 저장된 뷰 / 필터 프리셋

**Shopify — 뷰가 탭으로 뜨고 자동 갱신된다 (가장 정교한 명세)** (원문)
https://help.shopify.com/en/manual/shopify-admin/productivity-tools/searching-filtering-views
- **"Views display as separate tabs at the top the resource list"** (일부 리소스는 검색바 인라인 메뉴).
- 뷰가 저장하는 것: **검색어 + 필터 + 컬럼 선택 + 컬럼 순서**.
- **중요한 함정**: **"sort order isn't maintained for a particular view, so any time you navigate away from the view, the sort order resets."** → 정렬은 뷰에 저장되지 **않는다**.
- 뷰 관리(생성·이름변경·삭제)는 **데스크톱에서만** 가능.
- 컬럼은 숨기기/보이기/순서 변경 가능하되 **"with the exception of the main leftmost column"** — 첫 컬럼은 고정.
- 필터 문법: `is`/`is not` 로직, **콤마 = OR, 공백 = AND**.
- 자동 편입: 저장한 뷰의 조건을 나중에 충족한 주문은 **자동으로 그 뷰에 들어온다**(예: Paid 뷰). (스니펫)
  https://help.shopify.com/en/manual/fulfillment/managing-orders/viewing-orders/searching-orders

**Linnworks — 뷰에 액션까지 저장** (원문)
https://help.linnworks.com/support/solutions/articles/7000032975-open-orders-custom-views-and-filtering
- **Manage Views**로 생성, 톱니바퀴로 편집. 뷰가 저장하는 것: **컬럼(+컬럼 안의 상세 항목) + 정렬 + 필터 + Hot Buttons**.
- 필터가 2종으로 분리: **Persistent Filters**(뷰에 저장되는 고정 규칙) vs **Quick Filters**("temporarily" 임시 좁히기).
  → **"영구 규칙"과 "지금 잠깐"을 UI에서 분리**한 게 핵심. Shopify처럼 정렬이 리셋되는 혼란이 없다.

**ShipStation** — "Create Custom Order Views" 전용 문서 존재. (스니펫)
https://help.shipstation.com/hc/en-us/articles/360045864791-Create-Custom-Order-Views

**Brightpearl** — "Lists and reports can be filtered to include or exclude orders of any status allowing you to create your own **processing lists**, and all your different processing lists can be **saved as presets ready for you to visit regularly each day** and action all your orders." (스니펫)
https://help.brightpearl.com/hc/en-us/articles/211131446-Sales-Order-Statuses-Workflow
→ 뷰의 목적을 **"매일 방문하는 하루 루틴"** 으로 정의한 유일한 문서. 뷰 = 업무 리스트.

**Zoho Inventory** — Sales Orders 모듈 좌상단 **All Sales Orders 드롭다운 > + New Custom View**. (스니펫)

### 확인 불가
- `j`/`k` 행 이동, `e` 아카이브, `/` 검색 포커스 같은 **이메일식 단축키를 문서화한 OMS는 발견하지 못함.**

---

## 6. 정보 밀도 — 행 높이·컬럼 수·타이포

### 결론 먼저
**OMS 공식 문서는 행 높이·타이포 수치를 공개하지 않는다(확인 불가).** 대신 두 가지가 확인된다.
1. **모든 제품이 "밀도를 사용자에게 넘긴다"** — 컬럼 선택/순서/뷰를 사용자가 정하게 해서 밀도 논쟁을 회피한다.
2. **실사용 리뷰에서는 "너무 성김"과 "너무 빽빽"이 동시에 제기된다.** 즉 단일 정답이 없고 **화면 크기와 역할이 갈림길**이다.

### "너무 성김" — ShipStation 신 레이아웃 (가장 생생한 사례) (스니펫)
ShipStation이 레이아웃을 개편하자 전용 피드백 게시판이 생길 정도로 밀도 불만이 터졌다.
https://community.shipstation.com/t5/New-Layout-Feedback/idb-p/newlayout
- **"far too much spacing in this new layout requiring scrolling"**, 특히 **"on a smaller screen / laptop, there is just way to much space/padding"**
- **"poor density on smaller screens"** — 한 화면에 보이는 주문 수가 줄었다.
- **"the screen is almost entirely white with no color variation"** → 색 대비 소실로 **"배치 만들고 정렬하기가 더 어려워졌다, 계속 엉뚱한 버튼을 누른다"**, **"30분 만에 심한 두통"**
- 처리량 체감: **"it's like 5 times slower to get a label printed"**
- 스레드: https://community.shipstation.com/t5/ShipStation-Features/Old-layout-vs-new-layout/m-p/13340 , https://community.shipstation.com/t5/New-Layout-Feedback/Everything-is-worse/idi-p/14419 , https://community.shipstation.com/t5/ShipStation-Features/New-Layout-horrible-More-steps-required-to-do-the-same-work/m-p/22668
- 벤더 대응: "there are a lot of concerns being raised about the new layout" 를 인정하고 전담 태스크포스가 주간 단위로 리뷰. https://community.shipstation.com/t5/Blog/New-Layout-Feedback-Announcement/ba-p/14349

### "너무 빽빽" — 같은 제품, 반대 방향 (스니펫)
https://www.g2.com/products/shipstation/reviews?qs=pros-and-cons
- **메뉴 항목이 너무 많고 레이아웃이 산만하며 버튼이 너무 작다**는 지적, 개편 후 **쓰던 기능을 찾기 어렵다**는 반응.
- → **같은 제품에 "성김" 불만과 "산만/작은 버튼" 불만이 공존**한다. 밀도만의 문제가 아니라 **시각적 위계(hierarchy)**의 문제라는 신호.

### 오래된 UI 쪽 (스니펫)
- **Linnworks**: 기능 간 이동이 느리고 비직관적이며 시스템이 **outdated** 해 보인다는 리뷰.
- **Brightpearl**: UI가 다소 **dated**, **학습곡선이 가파르고** 도입 기간이 길다.
  https://www.unleashedsoftware.com/blog/5-best-linnworks-alternatives-for-2025/
  https://www.saashub.com/compare-brightpearl-vs-linnworks

### 수치 관례 (OMS 밖 디자인 시스템)
- **Carbon Design System**: 데이터 테이블 행 높이를 **5단계**(xs / sm / md / lg / xl)로 제공하고, Carbon 11에서 **Medium 40px** 가 추가됐다. 툴바 높이를 행 높이와 짝짓는다(**48px large 툴바 ↔ xl·lg 행**, small 툴바 ↔ sm·xs 행). (스니펫 — 정확한 5개 픽셀값 표는 페이지 fetch 실패로 **확인 불가**)
  https://carbondesignsystem.com/components/data-table/style/
  https://github.com/carbon-design-system/carbon/issues/8874
- 2차 자료 수준의 통용 범위(**공식 근거 아님, 참고만**): 진짜 dense 28–32px / 중간 36–40px / 여유 48–52px.
  https://www.setproduct.com/blog/data-table-ui-design

### 컬럼 수 — 전 제품 공통의 답: "고정하지 않는다"
- Shopify: 컬럼 숨기기·보이기·순서 변경 가능, **단 맨 왼쪽 주 컬럼은 고정**. (원문)
- Linnworks: 뷰 편집에서 **"tick the columns and the details within the columns you want to be displayed"**. (원문)
- ShipStation: Create Custom Order Views로 뷰별 컬럼 구성. (스니펫)
- → **권장 컬럼 수를 명시한 공식 문서는 없음(확인 불가).** 대신 "첫 컬럼(식별자)은 고정, 나머지는 사용자 결정"이 관례.

### 확인 불가
- OMS 제품들의 **실제 행 높이 px, 타이포 스케일** 수치.

---

## 우리 화면에 옮길 규칙 7개

**1. 좌=수집 주문 리스트 / 우=확인 작업 패널의 side-by-side를 기본으로, 좁아지면 stacked 드릴다운으로 전환한다.**
> 근거: Microsoft List/details가 "대량 컬렉션을 탐색·우선순위 매기며 컨텍스트를 앞뒤로 오가는 작업"을 이 패턴의 정확한 적용 대상으로 지목하고 641epx 이상 side-by-side / 640epx 이하 stacked라는 수치 기준까지 제시했으며, ShipStation은 Shipping Sidebar로 "그리드를 떠나지 않고 처리 완료"를 실제 설계 목표로 삼았기 때문이다.

**2. 한 집(주문) 안의 상품주문 2~14건은 별도 화면이 아니라 "행 인라인 확장"으로 편다.**
> 근거: ShipStation의 Multi-item Order View가 정확히 "Order Details를 열지 않고 여러 품목을 그리드 안에서 확인"하려고 도입된 기능이며, 우리 데이터 형태(1주문 : n상품주문)가 ShipStation의 multi-item 주문과 동형이기 때문이다.

**3. 상태는 축을 분리해 저장·필터하고, 행에서는 "주축 배지 1개 + 부축 점 n개(회색=미착수, hover=텍스트)"로 압축한다.**
> 근거: Brightpearl이 사업 고유 워크플로 축과 재고/배송/인보이스 축을 의도적으로 분리해 "어떤 조합으로도 검색"하게 했고, Zoho Inventory가 그 여러 축을 목록 행의 점 몇 개 + hover 툴팁으로 압축해 컬럼 폭을 아꼈기 때문이다. (반대로 Veeqo처럼 한 축에 뭉개면 상태 목록이 결제·재고·출고·채널이 섞인 비배타 나열이 된다.)

**4. 상태를 색으로만 구분하지 않는다 — 배지에 텍스트를 반드시 함께 두고, 동시에 색 대비도 죽이지 않는다.**
> 근거: Polaris Badge가 "Don't rely on color alone"을 명시하고 아이콘·색 배지에 스크린리더용 숨김 텍스트를 넣는 반면, ShipStation은 반대로 신 레이아웃에서 색을 거의 없앴다가 "색이 없어 엉뚱한 버튼을 누른다"는 실사용 불만을 받았기 때문이다(양방향 제약).

**5. 예외 주문(취소·중복·주소 불량·연락 두절)은 목록에서 숨기지 말고, 회색 처리 + 액션 비활성 상태로 같은 자리에 남긴다.**
> 근거: Linnworks가 미결제·주소 이상(우편번호 11자 초과) 주문을 자동 Parked로 만들고 "greyed out"으로 표시하되 목록에서 빼지 않으며, Amazon도 독립적으로 Pending 주문을 "grayed out and non-actionable"로 처리해 두 제품이 같은 답에 도달했기 때문이다.

**6. 되돌릴 수 없는 액션(수집 확정·주문 병합·고객 발송)은 모달 확인 + 대상 건수 명시 + "되돌릴 수 없음" 문안 + 사후 복구 경로를 세트로 붙인다.**
> 근거: Shopify app-home 패턴이 파괴적 *일괄* 작업에 Modal API 확인을 명시했고, Zoho가 주문 병합에 "You will not be able to undo this action"을 노출하며, ShipStation은 라벨 void가 unvoid 불가임을 전용 문서로 못박는 대신 주문 상태를 Awaiting Shipment로 자동 롤백시켜 복구 경로를 열어 주기 때문이다.

**7. CS의 하루 루틴을 "저장된 뷰(탭)"로 만들고, 뷰에는 필터·컬럼·정렬을 함께 저장하되 "영구 필터"와 "임시 빠른 필터"를 UI에서 분리한다.**
> 근거: Brightpearl이 저장 프리셋의 목적을 "매일 방문해 주문을 처리하는 processing list"로 정의했고, Shopify는 뷰를 탭으로 띄우고 조건 충족 주문을 자동 편입시키되 **정렬은 저장되지 않아 뷰를 떠나면 리셋되는 함정**을 남긴 반면, Linnworks는 Persistent Filters와 Quick Filters를 분리해 그 혼란을 피했기 때문이다.

---

## 우리 상황에 안 맞는 것 3개

**1. "체크박스 100건 선택 → 액션바로 같은 값 덮어쓰기" 중심의 대량 일괄 설계 (Veeqo·ShipStation형)**
Veeqo의 일괄 액션(Edit packages / Edit services / Edit ship date / Buy labels, 최대 100건)은 전제가 **"선택한 주문들이 전부 같은 처리를 받아도 되는 동질 집합"** 이다("if all selected orders require the same weight and dimensions"). 우리 작업의 축은 정반대다 — **여러 주문에 같은 값을 뿌리는 게 아니라, 한 집 안의 2~14개 상품주문을 사람이 조립해 하나의 실측 대상으로 판정**한다. 품목마다 규격·시공 조건이 달라 "같은 값 덮어쓰기"가 성립하는 필드가 거의 없다. 게다가 처리자가 CS 1~2명이라 일괄로 처리량을 벌 여지 자체가 작다.
→ **일괄은 저위험 액션에만 제한**하자: 수집 목록에서 "확인함/무시함" 토글, 태그 붙이기, 담당자 지정 정도. 실측 일정·시공 확정 같은 하류 영향 액션은 건별로 둔다.

**2. 스캐너·핫키 기반 파워유저 최적화 (ShipStation hotkey + 바코드 프리셋, j/k 행 이동)**
ShipStation이 hotkey를 바코드로 인쇄해 스캔 적용까지 만든 이유는 **하루 수백~수천 건 라벨을 찍는 창고 오퍼레이터**가 사용자이기 때문이다. 우리 CS는 건수가 적은 대신 **건당 판단 시간이 길다**(고객 연락, 주소 확인, 실측 가능 여부, 품목 조립). 병목은 키 입력 횟수가 아니라 **판단에 필요한 정보가 한 화면에 있느냐**다. 단축키 체계를 먼저 만드는 건 투자 대비 효과가 낮고, 오히려 ShipStation이 신 레이아웃에서 단축키를 뺐다가 욕먹은 사례처럼 **한 번 만들면 못 뺀다**는 유지 비용만 진다.
→ 지금 필요한 건 저장된 뷰(규칙 7)와 **진입 시 첫 미처리 건에 포커스가 가는 것** 정도. 단축키는 CS가 "이 화면을 하루 종일 본다"가 확인된 뒤에 붙인다.

**3. 배송·물류 축 중심의 상태 모델 통째 이식 (Shopify의 Delivery status / Label status / Return·Chargeback 축, ShipStation의 날짜 기반 On Hold 자동복귀)**
Shopify의 7축 중 **Delivery status(In transit / Out for delivery / Delivered), Label status(No label / Purchased / Printed), Chargeback, Fraud risk**는 우리에게 대응물이 아예 없다. 우리 이행 축은 **실측 → 도면 → 확정 → 생산 → 시공**이고, 캐리어도 추적번호도 라벨도 없다. 이 축들을 형식만 베끼면 **영원히 비어 있는 컬럼**이 생겨 밀도만 깎아먹는다(ShipStation 성김 불만 참고).
또 ShipStation의 **"On Hold until a specified date → 그날 자동으로 Awaiting Shipment 복귀"** 는 매력적이지만 그대로는 못 쓴다. 재입고는 날짜로 예측되지만 **우리 보류는 대개 "고객 응답 대기"** 여서 해제 트리거가 시간이 아니라 이벤트다.
→ Brightpearl 방식을 취하자: **시스템 고정 축(수집 상태: 신규/확인됨/제외됨/오류)과 사업 고유 축(실측·시공 워크플로)을 분리**하고, 보류에는 날짜가 아니라 **해제 조건(고객 회신, 주소 확인, 결제 확인)** 을 필수로 붙여 블랙홀이 되지 않게 한다.

---

## 인용 URL 목록 (32건)

ShipStation
1. https://help.shipstation.com/hc/en-us/articles/360025869052-View-Search-and-Sort-Orders
2. https://help.shipstation.com/hc/en-us/articles/360026157591-Configure-Shipping
3. https://help.shipstation.com/hc/en-us/articles/48668385552027-Feature-Updates-in-ShipStation-s-New-Layout
4. https://help.shipstation.com/hc/en-us/articles/360025869712-Understanding-Order-Statuses
5. https://help.shipstation.com/hc/en-us/articles/360026156911-Hold-Assign-and-Cancel-Orders
6. https://help.shipstation.com/hc/en-us/articles/360045435052-Can-I-unvoid-a-label
7. https://help.shipstation.com/hc/en-us/articles/360026157751-Void-Labels
8. https://help.shipstation.com/hc/en-us/articles/360036323651-Use-Shipping-Presets
9. https://help.shipstation.com/hc/en-us/articles/360045864791-Create-Custom-Order-Views
10. https://help.shipstation.com/hc/en-us/articles/360051509071-Can-I-customize-my-ShipStation-account
11. https://help.shipstation.com/hc/en-us/articles/4403830407067-Analytics-Reports-Hotkeys-Barcode-Scan-Actions
12. https://www.shipstation.com/blog/order-details-page/
13. https://community.shipstation.com/t5/New-Layout-Feedback/idb-p/newlayout
14. https://community.shipstation.com/t5/Blog/New-Layout-Feedback-Announcement/ba-p/14349
15. https://community.shipstation.com/t5/ShipStation-Features/New-Color-Scheme-Problems/m-p/25560
16. https://community.shipstation.com/ideas/bring-hotkeys-keyboard-shortcuts-back-for-v3-3616
17. https://www.g2.com/products/shipstation/reviews?qs=pros-and-cons

Linnworks
18. https://help.linnworks.com/support/solutions/articles/7000035513-open-orders-working-with-open-orders
19. https://help.linnworks.com/support/solutions/articles/7000032975-open-orders-custom-views-and-filtering
20. https://help.linnworks.com/support/solutions/articles/7000029276-open-orders-locked-and-parked-orders
21. https://help.linnworks.com/support/solutions/articles/7000021888-open-orders-working-with-unpaid-orders

Veeqo
22. https://help.veeqo.com/en/articles/3802825-order-search-and-filter
23. https://help.veeqo.com/en/articles/3802783-shipping-your-first-order
24. https://help.veeqo.com/en/articles/15602027-shipping-in-veeqo-uk

Shopify / Polaris
25. https://shopify.dev/docs/api/app-home/patterns/compositions/index-table
26. https://help.shopify.com/en/manual/fulfillment/managing-orders/viewing-orders/filtering-orders
27. https://help.shopify.com/en/manual/shopify-admin/productivity-tools/searching-filtering-views
28. https://help.shopify.com/en/manual/shopify-admin/productivity-tools/keyboard-shortcuts
29. https://polaris-react.shopify.com/components/feedback-indicators/badge
30. https://github.com/Shopify/polaris-react/issues/1969

Brightpearl
31. https://help.brightpearl.com/hc/en-us/articles/211131446-Sales-Order-Statuses-Workflow
32. https://api-docs.brightpearl.com/order/order-stock-status/index.html

Zoho Inventory / Amazon / 디자인 시스템
33. https://www.zoho.com/us/inventory/help/sales-orders/sales-order-managing.html
34. https://sell.amazon.com/blog/amazon-order-management
35. https://sellercentral.amazon.com/seller-forums/discussions/t/10ea2d73-176e-46ab-8bd9-00f342535a03
36. https://learn.microsoft.com/en-us/windows/apps/design/controls/list-details
37. https://carbondesignsystem.com/components/data-table/style/
38. https://www.unleashedsoftware.com/blog/5-best-linnworks-alternatives-for-2025/
