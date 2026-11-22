# 큰 회사 생산 화면 조사 — 반장 · 작업자가 "할 일과 진행"을 한눈에 보는 법 (2026-11-22)

- 왜: 사장님 말씀(11-22, 5판을 보고) — "반장, 파트 계정의 화면은 필요해. 1. 직관적으로 하루 작업해야 될 전체 주문 건과 진행 프로세스가 한눈에 보여야 돼. 2. 파트도 마찬가지고. … 실제 대형 상업 ERP UI deep research."
- 쓰는 곳: 생산 화면 6판 시안 `docs/design/mockups/tablet-production-v6.html`
- 어떻게 찾았나: 회사마다 **공식 도움말 · 설명서 페이지를 직접 열어** 읽었어요. 검색 말에는 우리 회사 · 고객 이름을 넣지 않았어요.
  - SAP 도움말은 페이지가 스크립트로 그려져서, 같은 글을 SAP 도움말 사이트의 글 주소로 받아 읽었어요.
  - Epicor 는 공식 도움말이 공개돼 있지 않아 **사용자 모임 글**만, Siemens 는 **새 기능 소개 글**만 읽었어요. 이 둘은 참고로만 써요.
  - 남의 화면 그림은 저장소에 넣지 않았어요. 말로만 옮겼어요.

## 한 줄 결론

큰 제품들은 거의 다 두 가지 꼴을 써요.

- **반장(감독) 화면**: 주문 한 줄에 공정 칸을 나란히 놓고, 납기가 빠른 순으로 세우고, **늦은 줄에만 색**을 칠해요.
- **작업자 화면**: 기기를 한 공정(작업장)에 묶어 **내 공정 일만** 보여 줘요. 목록은 "지금 할 수 있는 것 · 앞 공정을 기다리는 것 · 끝난 것"으로 나눠요. 주문의 다른 공정은 작게 보여 줘요.

우리 말로 옮기면 이래요. 납기 = **시공일**, 공정 = **재단 · 엣지 · 조립 · 검수**, 작업장 = **파트 계정**, 일 하나 = **도면 한 장**.

## 핵심 발견 6가지

### 1. 주문 한 줄 = 공정 칸 여러 개 (반장 판의 뼈대)
- **Odoo 18 Shop Floor**: 주문 하나가 카드 한 장이에요. 카드 안에 공정(작업 지시)이 한 줄씩 들어가요. 끝난 공정은 회색으로 줄을 긋고, 지금 공정은 그 작업장으로 가는 단추가 돼요. "Completed work orders appear in grey and are struck out." — https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing/shop_floor/shop_floor_overview.html
- **SAP S/4HANA** Manage Production Operations 앱(도움말 "How to Solve a Delayed Operation"): 주문 일정을 진행 막대 하나로 보여 줘요. 공정마다 색이 달라요. "The order schedule with a progress bar indicating the progress of the operations by different colors" — https://help.sap.com/docs/SAP_S4HANA_CLOUD/2bba750d1e124e1ea2a039bb1cd9b6c5/1e293258fb9d2060e10000000a44147b.html
- **Microsoft Dynamics 365** 일정 그림의 주문 보기: 한 주문의 공정을 그 주문 밑에 모아요. "In Order view, activities are grouped under production orders." — https://learn.microsoft.com/en-us/dynamics365/supply-chain/production-control/visual-scheduling-production
- **Katana**: 주문 상태가 공정 상태에서 저절로 정해져요. 하나라도 시작하면 '하는 중', 다 끝나면 '끝'. "If at least one operation is In Progress or Completed, the MO status auto-updates to In Progress." — https://support.katanamrp.com/en/articles/5914345-production-operation-statuses
- **우리 6판**: 시공일 칸 안에 **주문 한 줄 + 공정 네 칸**을 둬요. 네 칸은 지금 태블릿 · PC 화면에 이미 있는 네모 칸 그대로예요. 채움 = 끝, 굵은 테두리 + 장 수 = 하는 중, 빈 칸 = 아직.

### 2. 납기가 빠른 순이 기본 순서
- **Oracle Fusion** 작업 목록(dispatch list): "By default the records are sorted by the earliest completion date." — https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/faumf/how-you-review-a-dispatch-list.html
- **Odoo**: "The Shop Floor module prioritizes orders based on their scheduled date." 별표를 누르면 맨 위로 올라가요. — 1번과 같은 주소
- **MRPeasy** 작업자 화면: "Operations with the earliest start time are shown first." — https://www.mrpeasy.com/resources/user-manual/reporting/internet-kiosk/
- **Infor Factory Track** 작업 목록: 반장이 맡긴 일이 맨 위에 와요. 그다음은 주문 납기 · 시작일로 세울 수 있어요. "You can sort the list of tasks based on, the order due and start date; and the operation due and start date." — https://docs.infor.com/factorytrack/2026.10/en-us/ftlnolh/lnsf/ftsfoperatormachinedispatch-ts.html
- **우리 6판**: 날 칸은 시공일 순으로 왼쪽에서 오른쪽(내일 → 4일 뒤)이에요. 칸 안에서는 손을 써야 할 줄이 위로 가요(안 내려온 도면 → 만드는 중 → 기다림 → 제작 완료).

### 3. 늦은 것에만 색
- **SAP** 작업장 화면: "Operations in Progress displays all operations that are partially confirmed and therefore still in progress. A colored bar indicates delayed operations." — https://help.sap.com/docs/SAP_S4HANA_CLOUD/2bba750d1e124e1ea2a039bb1cd9b6c5/14c16d57284f346ae10000000a4450e5.html
- **SAP** 같은 앱: 늦음 표와 부품 없음 표를 같이 빨갛게 보여 줘요. 그러면 늦은 까닭이 보여요. "if the delay icon and the missing components icon are highlighted in red, the reason for the delay is probably due to missing components." — 1번의 SAP 주소
- **Oracle** 작업 목록: 시작 · 완료 날이 지났으면 날짜 옆에 경고 표가 붙어요. "The start date and time is displayed with a warning icon if it's past due…" — 2번의 Oracle 주소
- **MRPeasy** 일정표: 바탕색 = 진행(시작 전 · 하는 중 · 멈춤 · 끝), 빨간 빗금 = "Overdue. Should have been already started, if not started." — https://www.mrpeasy.com/resources/user-manual/production-planning/production-schedule/
- **우리 6판**: 늦은 줄에만 **왼쪽 빨간 막대**를 두고 시공일 칸을 빨갛게 해요. 늦음 규칙은 PC 생산 화면이 이미 쓰는 규칙(`foms/services/production/late_rule.py`) 그대로예요. 판 전체를 색칠하지 않아요("정신없다" 거절 이력).

### 4. 작업자 기기는 한 공정에 묶는다
- **Microsoft** 생산 현장 화면: 감독이 기기마다 생산 단위 · 자원 묶음 · 자원 거르개를 정해요. "These filters help ensure that only relevant jobs show on the device." — https://learn.microsoft.com/en-us/dynamics365/supply-chain/production-control/production-floor-execution-setup
- **Autodesk Fusion Operations**: "Tablets can be assigned to a section, which filters the set of operations displayed on it." — https://help.fusionoperations.autodesk.com/en/articles/5657200-why-can-t-i-find-this-production-order-operation-in-my-application
- **SAP Digital Manufacturing** 작업장 화면: "The Work Center POD queues SFCs or orders in a work center as well as specific operation activities" — https://help.sap.com/docs/SAP_DIGITAL_MANUFACTURING/97c9e9b9fac74be2a023638cd1700b46/d343fbbb5fbf42a0bc8455d4af138ba9.html
- **Katana**: "Each operator has a dedicated account and sees only their assigned tasks." — https://support.katanamrp.com/en/articles/5967424-using-the-shop-floor-control-app
- **우리 6판**: 파트 계정(재단 · 엣지 · 조립 · 검수)이 곧 작업장이에요. 판은 반장과 같고, **내 칸만 넓고 진하게** 그려요. 날 머리에는 "내 남은 장"이 나와요.

### 5. 작업자 목록은 "지금 할 수 있음 · 앞 공정 기다림 · 끝"으로 나눈다
- **SAP** 작업장 화면은 무리를 셋으로 나눠요. 오늘 할 수 있는 공정(Today's Operations), 하는 중(Operations in Progress), 아직 시작 안 한 줄(Queuing Operations). — 3번의 SAP 작업장 주소
- **Epicor Kinetic MES** 작업 줄: Current = 앞 공정이 끝나 지금 할 수 있음, Expected = 앞 공정이 아직, Active = 내가 하는 중. 사용자 모임 글이라 참고로만 써요. "Operations scheduled for the selected resource group, but quantities have not yet been completed on previous operations." — https://www.epiusers.help/t/work-queue-in-full-kinetic/112822
- **MRPeasy**: "Completed operations of the unfinished MO-s are at the end of the list." — 2번의 MRPeasy 주소
- **Fusion Operations**: 앞 공정이 끝날 때까지 이 공정을 숨기는 설정이 있어요("hide an operation until production has occurred or has been completed on the previous operation"). — 4번의 Autodesk 주소
- **우리 6판**: 파트 판의 칸 안 줄 순서 = 내 일이 남은 집 → 내 일이 끝난 집(흐리게) → 도면이 아직인 집(얇은 줄). 엣지 · 조립 · 검수는 "지금 n장 · 기다림 m장"을 보여 줘요. 앞 공정을 기다리는 장도 **숨기지 않아요**. 사장님 규칙이 "다른 파트는 표시만, 막지 않음"이기 때문이에요.

### 6. 작업자도 주문 전체 공정을 본다 — 자기 것만 강조
- **Katana** 작업자 앱: 일을 열면 그 주문의 공정 목록이 다 나오고, 지금 일만 강조돼요("This task" is highlighted). 공정마다 누가 하는지도 나와요. — 4번의 Katana 주소
- **HOMAG productionAssist Feedback**(가구): 부품을 끝냈다고 알리면 주문 진행에 바로 반영돼요. 알리는 법은 둘이에요. "Components and items can be reported as "finished" by scanning (tablet or scanner) or by clicking on them." — https://www.homag.com/en/features/productionassist-feedback . 사무실 화면에서는 "The status of articles and components is automatically updated and directly visible in the job progress." — https://www.homag.com/en/product-detail/software/work-preparation/productionmanager
- **imos iX Scout**(가구): 부품마다 · 작업장마다 끝을 알리고, 생산 진행을 한눈에 봐요. 태블릿에서 써요. "Everywhere in the user interface it is possible to scan the QR code of a component." — https://www.imos3d.com/en/products/manufacturing-assembly/ix-share/cloud-service-for-order-management-ix-scout/
- **우리 6판**: 파트 판 줄에 남의 공정 세 칸도 작게 남겨요. 그래서 "재단은 끝났나"가 줄에서 바로 보여요. 장 단위 끝 알리기는 지금 있는 도면 카드 단추를 그대로 써요.

## 그 밖에 본 것 (짧게)

- **터치 크기 모드**: SAP Digital Manufacturing 에는 태블릿용 'Cozy' 크기가 따로 있어요. "The dimensions of the POD controls are optimized for touch-enabled devices, such as tablets." — https://help.sap.com/docs/SAP_DIGITAL_MANUFACTURING/57088d83d7f24b71821704db82ba8cbd/74f0d713f48841478abb14a563791bc0.html . Microsoft 도 "The production floor execution interface is optimized for touch interaction." — https://learn.microsoft.com/en-us/dynamics365/supply-chain/production-control/production-floor-execution-use . → 우리: 누르는 것은 모두 실제 48px 이상(80% 화면에서 60).
- **상태 표 셋**: Microsoft 일 목록은 상태를 표 하나로 보여 줘요. 표 없음 = 시작 전, 초록 세모 = 시작, 노란 두 줄 = 멈춤. 급한 일은 느낌표 칸이 따로 있어요. — 위 Microsoft 사용 주소. → 우리: 이미 있는 네모 칸(채움 · 굵은 테두리 · 빈 칸)과 같은 생각이라 새로 만들지 않아요.
- **반장의 작업장 카드**: Oracle 감독 화면의 '살펴보기' 탭은 작업장마다 카드 한 장이에요. 카드에는 상태 · 들어온 작업자 · 지금 공정 · 수량 진행 · 문제 표가 나와요. "Each workstation card includes the following information: The workstation status, … the quantity progress for the operation, and an exception indicator…" — https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/faumf/how-you-monitor-and-manage-your-workstations.html . → 우리: 파트별 "남은 장" 상자를 반장 판에 더 얹는 것은 뺐어요(위젯을 쌓지 않기). 파트 판의 날 머리 숫자로 대신해요.
- **급한 일 맨 위**: Oracle 은 급하게 바꾼 주문이 정렬과 상관없이 맨 위로 가요. "Expedited work orders always appear at the top of the list, irrespective of the sort order." — https://docs.oracle.com/en/cloud/saas/readiness/scm/24d/mfg24d/24D-mfg-wn-f34298.htm . → 우리: "시공일 당겨짐" 집이 빨간 테두리로 눈에 띄어요. 순서는 시공일이 이미 맡아요.
- **반장의 배정 목록**: Infor 는 한 줄에 일 · 시작일 · 맡은 사람 · 공정 진행 막대를 두고, 끌어다 놓아 사람을 맡겨요. "Use the drag and drop capabilities to assign and unassign the resources." — https://docs.infor.com/factorytrack/2025.x/en-us/ftslolh/slmes_sub/lac1753419769729.html . → 우리: 일 나누기는 "추후 통보"라 자리만 비워 둬요.
- **사용자 모임 · 소개 글만 본 것**: Siemens Opcenter 2501 은 작업 지시 목록에 "percentage of completion and status visible"을 더했어요 — https://blogs.sw.siemens.com/opcenter/whats-new-in-opcenter-execution-discrete-2501/ . Microvellum Processing Center 는 "Supports touch-based interaction for shopfloor use on industrial touch screens."라고 해요 — https://intercom.help/microvellum-knowledge-base/en/articles/14726261-microvellum-processing-center-application . Cabinet Vision · Biesse 는 공개된 현장 화면 설명을 찾지 못했어요.

## 6판에 쓴 것 · 안 쓴 것

| 빌려 온 꼴 | 어디서 | 6판 어디에 |
|---|---|---|
| 주문 한 줄 + 공정 칸 나란히 | Odoo · SAP · Microsoft · Katana | 반장 판 · 파트 판 · PC 의 모든 주문 줄 |
| 납기(시공일) 빠른 순 | Oracle · Odoo · MRPeasy · Infor | 날 칸 넷이 시공일 순, 칸 안은 손 쓸 줄이 위 |
| 늦은 것에만 색 | SAP · Oracle · MRPeasy | 늦은 줄 왼쪽 빨간 막대 + 시공일 칸 빨강 |
| 기기 = 공정 하나 | Microsoft · Fusion Operations · SAP DM · Katana | 파트 계정 = 같은 판에서 내 칸만 넓게 |
| 지금 할 것 · 기다릴 것 · 끝 | SAP 작업장 · Epicor · MRPeasy | 파트 판 줄 순서, "지금 n · 기다림 m" |
| 남의 공정은 작게, 내 것만 강조 | Katana · HOMAG · imos | 파트 판 줄의 작은 칸 셋 |
| 끝난 것은 흐리게 · 아래로 | Odoo · MRPeasy | 제작 완료 줄은 맨 아래 한 줄, 파트 판의 "내 일 끝" 줄은 흐리게 |
| 터치 크기 | SAP DM · Microsoft | 줄 · 단추 실제 48px 이상 |

**안 쓴 것과 까닭**
- **시간 막대 일정 그림(간트)**: 우리는 공정마다 시작 · 끝 시각을 계획하지 않고, 하루 단위로 충분해요. 줄이 가늘어져 장갑 손으로 누르기도 어려워요.
- **맨 위 숫자 상자 줄**(Oracle 첫 화면의 지난 주문 수 같은 것): "너무 정신없다"(3판 거절)와 부딪혀요. 숫자는 날 머리 한 마디로만 둬요.
- **숫자판 · 수량 보고 · 타이머 · 출퇴근**: 우리 일 단위는 도면 한 장이에요. 수량을 넣거나 시간을 재지 않아요.
- **끌어다 놓아 사람 맡기기**: 일 나누기 방법은 사장님이 "추후 통보"라 비워 둬요.

**나중에 볼 만한 것**: 도면 장마다 QR 을 붙이고 찍어서 끝 알리기(HOMAG · imos). 장갑 손에는 화면 단추를 찾는 것보다 빠를 수 있어요. 지금은 넣지 않았어요.

## 출처 목록 (2026-11-22)

"페이지 원문" = 직접 열어 따옴표 글을 대조했어요. "조사 일꾼 확인" = 조사 일꾼이 열어 읽었고, 직접 대조는 안 했어요.


| 제품 | 주소 | 확인 |
|---|---|---|
| Microsoft Dynamics 365 — 현장 화면 쓰기 | https://learn.microsoft.com/en-us/dynamics365/supply-chain/production-control/production-floor-execution-use | 페이지 원문 |
| Microsoft — 기기 설정(거르개) | https://learn.microsoft.com/en-us/dynamics365/supply-chain/production-control/production-floor-execution-setup | 페이지 원문 |
| Microsoft — 일정 그림 주문 보기 | https://learn.microsoft.com/en-us/dynamics365/supply-chain/production-control/visual-scheduling-production | 페이지 원문 |
| SAP S/4HANA — 늦은 공정 고치기(Manage Production Operations) | https://help.sap.com/docs/SAP_S4HANA_CLOUD/2bba750d1e124e1ea2a039bb1cd9b6c5/1e293258fb9d2060e10000000a44147b.html | 도움말 글 주소로 원문 |
| SAP S/4HANA — 작업장 화면 | https://help.sap.com/docs/SAP_S4HANA_CLOUD/2bba750d1e124e1ea2a039bb1cd9b6c5/14c16d57284f346ae10000000a4450e5.html | 도움말 글 주소로 원문 |
| SAP Digital Manufacturing — 작업장 화면 | https://help.sap.com/docs/SAP_DIGITAL_MANUFACTURING/97c9e9b9fac74be2a023638cd1700b46/d343fbbb5fbf42a0bc8455d4af138ba9.html | 조사 일꾼 확인 |
| SAP Digital Manufacturing — 터치 크기 | https://help.sap.com/docs/SAP_DIGITAL_MANUFACTURING/57088d83d7f24b71821704db82ba8cbd/74f0d713f48841478abb14a563791bc0.html | 도움말 글 주소로 원문 |
| Oracle — 작업 목록 | https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/faumf/how-you-review-a-dispatch-list.html | 페이지 원문 |
| Oracle — 작업장 카드 | https://docs.oracle.com/en/cloud/saas/supply-chain-and-manufacturing/26a/faumf/how-you-monitor-and-manage-your-workstations.html | 페이지 원문 |
| Oracle — 급한 주문 맨 위 | https://docs.oracle.com/en/cloud/saas/readiness/scm/24d/mfg24d/24D-mfg-wn-f34298.htm | 조사 일꾼 확인 |
| Oracle — 작업자 줄 순서 | https://docs.oracle.com/en/cloud/saas/readiness/scm/25a/mfg25a/25A-mfg-wn-f35477.htm | 페이지 원문 |
| Infor Factory Track — 작업 목록 | https://docs.infor.com/factorytrack/2026.10/en-us/ftlnolh/lnsf/ftsfoperatormachinedispatch-ts.html | 페이지 원문 |
| Infor Factory Track — 배정 목록 | https://docs.infor.com/factorytrack/2025.x/en-us/ftslolh/slmes_sub/lac1753419769729.html | 페이지 원문 |
| Epicor Kinetic MES — 작업 줄 탭 | https://www.epiusers.help/t/work-queue-in-full-kinetic/112822 | 사용자 모임 글(공식 아님) |
| Siemens Opcenter 2501 | https://blogs.sw.siemens.com/opcenter/whats-new-in-opcenter-execution-discrete-2501/ | 새 기능 소개 글 · 조사 일꾼 확인 |
| Odoo 18 Shop Floor | https://www.odoo.com/documentation/18.0/applications/inventory_and_mrp/manufacturing/shop_floor/shop_floor_overview.html | 페이지 원문 |
| Katana — 작업자 앱 | https://support.katanamrp.com/en/articles/5967424-using-the-shop-floor-control-app | 페이지 원문 |
| Katana — 공정 상태 | https://support.katanamrp.com/en/articles/5914345-production-operation-statuses | 페이지 원문 |
| MRPeasy — 일정표 색 | https://www.mrpeasy.com/resources/user-manual/production-planning/production-schedule/ | 페이지 원문 |
| MRPeasy — 작업자 화면 | https://www.mrpeasy.com/resources/user-manual/reporting/internet-kiosk/ | 페이지 원문 |
| HOMAG productionAssist Feedback | https://www.homag.com/en/features/productionassist-feedback | 페이지 원문 |
| HOMAG productionManager | https://www.homag.com/en/product-detail/software/work-preparation/productionmanager | 페이지 원문 |
| imos iX Scout | https://www.imos3d.com/en/products/manufacturing-assembly/ix-share/cloud-service-for-order-management-ix-scout/ | 페이지 원문 |
| Microvellum Processing Center | https://intercom.help/microvellum-knowledge-base/en/articles/14726261-microvellum-processing-center-application | 조사 일꾼 확인 |
| Autodesk Fusion Operations | https://help.fusionoperations.autodesk.com/en/articles/5657200-why-can-t-i-find-this-production-order-operation-in-my-application | 페이지 원문 |

따옴표 안 영어는 페이지 글 그대로 옮겼어요. 페이지는 바뀔 수 있어요(SAP 도움말 글 주소는 판 번호가 바뀌면 달라져요).
