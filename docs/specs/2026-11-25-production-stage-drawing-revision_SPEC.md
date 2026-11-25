# 생산 넘어간 주문의 도면 수정 — 도면팀 PC 화면 · 도면별 막기 · 공장 요청 — 설계서 (2판)

> 작성일 2026-11-25 | 상태 **승인(2026-11-25 사장님 시안 "이 모양으로 진행" + 정할 것 모두 답함) — 2판이 정본** | 등급: **코어 변경**(도면 전달 권한 · 생산 쓰기 막는 문 · 주문 JSON 서버 소유 칸 · 새 API 4 · 알림 — 설계 → 승인 → 구현)
> 계기: 사장님 2026-11-25 — "생산 넘어간 주문 중 도면 수정이 필요한 경우 > 도면팀이 수정 할 수 있게 UI만들어봐 > 도면은 pc로만 작업하니깐 pc 버전만 만들면 돼" + 답 여덟(§1) + 정할 것 답(§9).
> 기준 코드: 가지 `session/tablet-prod-ui` `85dc8813d`(조사 기준 `5a71d7310` · `e5ba168a3` 와 견주어 `foms/` · 생산 · 도면 템플릿 변경 없음 — 파일:줄 그대로 맞다). 조사 원문: 스크래치 `dfix/survey.md`(이 설계서의 "조사 §n").
> 화면 시안(저장소 밖, 2판으로 다시 찍음): 스크래치 `dfix/mock/01_workbench_list` · `02_workbench_detail` · `03_send_dialog` · `04_factory_tablet` (.html · .png).
> 형식은 11-23 설계서(`2026-11-23-production-self-claim-and-factory2_SPEC.md`)를 따른다. 그 설계서의 "승인 때 고친 것"(지금 글은 그대로 · 새 글만 · 생산 화면은 '체크' 대신 '작업' · 공장 색 칩 · 도면 고치는 중 = 보류처럼)은 여기서도 지킨다. 이름 · 번호는 모두 지어낸 값이다.

## 1판에서 바뀐 것 (2판)

| # | 1판 | 2판(사장님 답) | 절 |
|---|---|---|---|
| 1 | §9 "정할 것" 15 | **"정해진 것(사장님 답 원문)"**으로 바꿈 | §9 |
| 2 | 공장 요청 거절 단추 [요청 닫기] | **[요청 반려]**(사장님 "'요청 반려' 로 버튼 만들어") — 창 제목 · 기록 낱말 · 알림 글 · 이벤트 · API 주소 모두 '반려' | §2 · §4 · §5 · §6 · §10 |
| 3 | 한 장 막힌 주문의 통째 작업 = 막기(추천) | **고치는 도면만 빼고 처리** — 통째 완료를 도면별 표시로 풀어 적는다(새 절 §3-6). [제작 완료]는 그 도면이 끝날 때까지 막힘 | §3-6 · §4-3 |
| 4 | 손 체크 파트 + 도면 고쳐 보냄 = 추천만 | **고친 도면만 다시 할 일로** — §3-6 과 같은 함수 | §3-6 · §5 |
| 5 | 경고는 '완료'만(1판 풀이 4) | **작업 중인 도면도 경고** — 1판 풀이 4 지움 | §2-3 · §4-2 |
| 6 | '생산 중' 칸 = 생산 + 시공 단계 전부 | **생산 단계 + 시공일이 오늘이거나 남은 시공 대기(시공 시작 안 한 것)** | §2-1 · §7 |
| 7 | 패킹 = 추천만 | **고친 도면 줄의 체크 풀기**(고치는 동안 못 누름, 출발 보고 뒤 그대로) | §3-7 · §4-3 |
| 8 | 직접 올린 파일 = 추천만 | **바꿀 도면을 꼭 고르게**(새로 더하면 '새 도면') | §2-3 · §4-2 |
| 9 | 공장 요청 막기 · 사진 · 알림 = 추천만 | 바로 막기 · 사진 있으면 3장까지 · 영업 요청과 똑같은 알림 | §2-4 · §6 |
| 10 | [수정 시작] · [수정 취소] 누가 = 추천만 | **둘 다 도면팀 누구나**(누가 눌렀는지 기록) | §4-1 |
| 11 | 구현 묶음 표 | 묶음마다 파일 · API · 새 글 · 완료 기준 · 파일 겹침 표 | §8 |

---

## 1. 사장님 말 · 답 여덟 (원문)

요청: "생산 넘어간 주문 중 도면 수정이 필요한 경우 > 도면팀이 수정 할 수 있게 UI만들어봐 > 도면은 pc로만 작업하니깐 pc 버전만 만들면 돼"

| # | 물음 | 답(원문) |
|---|---|---|
| 1 | 모아 볼 범위 | 도면 작업실에 '생산 중' 탭 — "생산 · 시공 대기 주문 전부"(영업이 수정 요청한 주문은 맨 위에 '수정 요청' 표시로) |
| 2 | [수정 시작] 때 막기 | "고치는 도면만 막기"(도면 5장 중 2번을 고친다고 표시하면 공장에서 2번만 '도면 고치는 중'으로 막히고 나머지는 계속 작업, 수정본을 보내면 풀림) |
| 3 | 이미 작업된 도면 | "경고하고 보내기"(도면팀 화면에 도면마다 공장 진행 예: '도면 2 · 재단 완료 · 엣지 작업 중'을 보여 주고, 보내기 전 "도면 2는 재단이 완료된 도면입니다. 보내면 공장에서 다시 작업해야 합니다."를 한 번 확인) |
| 4 | 보내는 사람 | "도면팀 누구나"(누가 보냈는지 기록) |
| 5 | 영업 수정 요청 | "요청한 도면만 막기"(도면을 안 고른 요청은 지금처럼 전체) |
| 6 | 공장 메모 | "메모를 꼭 적게 하기"(생산으로 넘어간 주문의 수정본은 메모가 있어야 보냄, 바뀐 도면 번호는 자동 표시) |
| 7 | 시공 대기 주문 | "알림만 보내기 (지금 그대로)"(주문은 시공 대기에 두고 공장에 '도면 바뀜' 알림, 도면팀에게는 보내기 전 "이미 제작 완료된 주문입니다" 경고) |
| 8 | 공장 → 도면팀 | "공장 요청 단추도 같이"(태블릿 도면 카드에 [도면 수정 요청], 반장이나 파트 담당이 도면을 고르고 사유를 적으면 도면팀 '생산 중' 탭 맨 위에 올라옴) |

### 1-1. 지금 상태 요약 (조사 근거)

| 빈 곳 | 근거 |
|---|---|
| 생산 · 시공 단계 `CONFIRMED` 주문은 작업실 기본 목록에 없다. 검색 · [컨펌 포함]은 모든 단계 확정 주문을 섞고, 목록에 단계 칸이 없다 | `foms/services/drawing_workbench_read_model.py:78-123` · `foms/web/drawing/workbench.py:677-691` · `templates/drawing/partials/workbench_dashboard_body.html:180-215` |
| 작업실 상세에 생산 진행(파트 표시 · 공장 완료)이 하나도 없다. 생산 작업 시트는 볼 권한이 있지만 링크가 없다 | 조사 §2-1 끝 줄 · `foms/services/production/home_access.py:21-41` |
| "도면 고치는 중" 막힘은 `drawing_status` ∈ {RETURNED, TRANSFERRED} 일 때 **주문 통째**. 도면팀이 스스로 고칠 때는 한 번도 안 막힌다 | `foms/services/orders/confirm_drawing_gate.py:108-118` · `foms/services/production/part_mark_gates.py:93-108` |
| 전달 권한 = 관리자 · 지정 담당만 | `foms/services/orders/erp_policy_permissions.py:126-145` · `foms/api/drawing/erp_orders_drawing.py:191-210` |
| 마법사 저장 창 길은 메모를 늘 빈 글로 보낸다. '바뀐 것' 줄에 몇 번 도면이 바뀌었는지 없다 | `static/js/drawing/save-send.js:169` · `foms/services/production_change_alerts.py:252-276` |
| 작업된 도면을 고쳐 보내도 아무 경고가 없다(새 key = 모든 파트 '안 봄', 카드 쓴 파트 공정 칸 꺼짐, 그 공장 완료 풀림) | 조사 §5 끝 줄 · `foms/services/production/part_steps_sync.py:47-71` · `foms/services/orders/drawing_factory.py:232-245` |
| 손 체크(카드 안 쓴) 파트는 새 판도 완료로 보인다 · 공장 꼴 패킹 체크가 고친 도면에 남는다 | `part_steps_sync.py:1-8` · `foms/services/shipment/packing_factory.py:11-22` |
| 공장이 도면 수정을 요청할 길이 없다([불량 알리기]는 알림 0 · 도면팀에 안 보임) | `foms/api/production/orders.py:1218-1295` |
| 영업 수정 요청은 도면이 2장 이상이면 대상 번호를 **꼭** 고르게 한다 — "도면을 안 고른 요청"은 사실상 도면 1장 주문 · 협력사 요청 · 옛 자료뿐 | `foms/api/drawing/erp_orders_revision.py:132-152` · `foms/services/partners/revision.py:67-70` |
| 영업 요청은 `TRANSFERRED`/`CONFIRMED` 에서만 받는다 → **열린 영업 요청은 한 주문에 늘 하나** | `erp_orders_revision.py:154-155` |
| 공정 칸 통째 작업 = 주문 JSON `production.steps` 의 칸 하나(주문 하나에 값 하나). 도면별 진행은 `production_part_marks` 표. 카드를 한 장도 안 쓴 파트만 칸이 기준이고, 한 장이라도 쓰면 카드가 기준이다(B5′) | `foms/api/production/orders.py:1140-1215` · `part_steps_sync.py:1-8` · `part_mark_gates.py:180-225` |

---

## 2. 화면마다 바뀌는 것

### 2-1. 도면 작업실 목록 — '생산 중' 칸 (시안 01)

- **자리**: 지금 프로세스 맵 줄 끝에 떨어진 칸 하나 "생산 중 N"(누적 완료 · 지연 · 미확인과 같은 꼴, `data-status="PRODUCTION"`). 새 탭 줄은 만들지 않는다(풀이 §11-1). 숫자 = 그 사람 범위(내 것만 · 협력사 거르개 그대로)의 아래 모집단 수.
- **모집단**(답 1 + §9 답 "시공일이 지난 것과 시공 시작한 것은 빼기"):
  - 생산 단계(`erp_stage_code IN ('PRODUCTION','생산')`) 전부, 그리고
  - 시공 단계(`'CONSTRUCTION','시공'`) 중 시공일(`orders.erp_construction_date`)이 **오늘(KST) 이거나 뒤**이고, **시공 방문이 열리지 않은**(`order_construction_attempts.is_current` 줄 없음) 주문.
  - 빠진 주문(시공일 지남 · 시공 시작)은 지금처럼 검색으로 찾는다(검색어가 있으면 컨펌 포함 — 지금 규칙).
  - 다른 칸 · 기본 목록은 지금 그대로(생산 주문을 기본 목록에 섞지 않는다).
- **줄 구성**: 칸(열)은 지금 그대로. 값만 생산 칸일 때 바뀐다.
  - 주문/고객 칸 아래: 요청 표시 "수정 요청 · 영업" / "수정 요청 · 공장" · 고치는 중 표시 "도면 고치는 중"(색 있는 표시 — 회색 금지).
  - 다음 액션: "영업 수정 요청 · 이영업" / "공장 수정 요청 · 박반장 · 도면 3" / "도면 2 고치는 중 · 김도면". 없으면 지금 글 그대로.
  - 상태: 둘째 줄 단계 "생산" / "시공 대기", 셋째 줄 공장 진행 요약 "재단 5/5 · 엣지 3/5 · 조립 1/5 · 검수 0/5"(2공장 장이 있으면 공장마다 한 줄, 앞에 공장 칩). 시공 대기는 "제작 완료".
  - 대상 번호: 요청 · 고치는 도면 번호 "도면 2" · "도면 2 · 3".
- **정렬**: ① 열린 요청(영업 · 공장, 요청 시각 오래된 것 먼저) ② 고치는 도면이 있는 주문 ③ 나머지 시공일 빠른 순(시공일 없음은 맨 뒤). `sort=` 를 고르면 그 정렬이 이긴다(지금 규칙).
- **상한 1,000건**: SQL 에서 ① 요청 · 고치는 중 주문을 먼저 모두(상한 없음) ② 나머지를 시공일 순 1,000건까지. 캡에 닿으면 경고 로그 + 목록 아래 "더 있는 N건은 안 보여요. 찾기로 찾아 주세요." 요청 주문이 잘리는 일은 없다.

### 2-2. 작업실 상세 (시안 02)

생산 단계 · 시공 대기 주문에서만(그 밖 단계는 지금 그대로).

- **머리 줄**: 끝에 링크 "생산 작업 시트 열기"(`/erp/production/sheet/<id>`, 새 탭). 지금 [생산 현황 보기](ERP 대시보드로 감)는 그대로.
- **본문 왼쪽 '공장 진행' 접는 칸**(지금 '타임라인' · '요청사항' · '파일 비교' 접는 칸과 같은 꼴, 맨 위에 펼친 채). 오른쪽 고정 패널 뒤에는 두지 않는다.
  - 도면마다 한 줄: "도면 2" + 공장 칩 · 재단 · 엣지 · 조립 · 검수 = "재단 완료 · 김재단" / "엣지 작업 중 · 박엣지" / "재단 기본" / "조립 미정" / 손 처리 "재단 완료 · 박반장(작업 시트)". 공장 제작 완료면 줄 끝 "1공장 제작 완료".
  - 줄 끝 [수정 시작] → 확인 창 "도면 2를 고치는 중으로 표시할까요? 공장에서 도면 2만 작업이 막혀요." `[취소]` `[수정 시작]`.
  - 고치는 중인 줄: 빨간 바탕 + "도면 고치는 중 · 김도면 · 11/25 14:10" + [수정 취소] → 확인 창 "도면 2 수정을 취소할까요? 공장에서 도면 2를 다시 작업할 수 있어요." `[닫기]` `[수정 취소]`.
  - 영업 · 공장 요청이 걸린 줄: "수정 요청 · 영업" / "수정 요청 · 공장" 표시(요청한 순간부터 막힘 — 빨간 바탕).
  - 시공 대기 주문은 줄마다 "제작 완료" 한 칸, **[수정 시작] 없음**(지휘 풀이 §11).
- **요청사항 칸**: 지금 그대로 + 공장 요청이 같은 목록에 쌓임 — "수정 요청 · 공장" · 시각 · 요청한 사람 · 대상 도면 칩 · "사유: …" · 사진(있으면, 누르면 크게) · [반영 완료](지금 단추) · **[요청 반려]**.
  - [요청 반려] → 창 제목 "요청 반려" · 본문 "반려 사유를 적어 주세요. 요청한 사람에게 알림이 가고, 도면 3 막힘이 풀려요." · 사유 칸(꼭 적기) · `[취소]` `[요청 반려]`. 반려된 요청은 "반려 · 오도면 · 11/25 16:02 · 사유: …"로 남는다.
- **결정 바 · 전달 단추**: 지금 그대로. 생산 · 시공 단계에서는 도면팀 누구나 [수정본 전달]이 켜진다(답 4).

### 2-3. 보내는 창 (시안 03)

두 길 같은 규칙: 작업실 [도면 전달]/[수정본 전달] 창(`POST /api/orders/<id>/transfer-drawing`) · 마법사 [저장] 창 '도면 발송'(`POST …/drawing-wizard/transfer-pending`).

- **바뀐 도면 자동 표시**: "바뀐 도면: 도면 2 (고침) · 도면 6 (새 도면)"(빠지면 "· 도면 4 (빠짐)"). 서버도 같은 계산을 해서 전달 이력에 적는다(§3-4).
- **메모 꼭 적기**(생산 · 시공 단계): 지금 메모 칸(작업실 "메모", 칸 안 안내 "전달 메모")에 빨간 "꼭 적기" + "생산으로 넘어간 주문은 메모를 적어야 보낼 수 있어요." 비우면 "공장에 남길 메모를 적어 주세요."(서버 400 `NOTE_REQUIRED`). 공백만은 빈 글.
- **마법사 저장 창**: 생산 · 시공 단계에서 '도면 발송'을 켜면 아래에 "바뀐 도면" 줄 + 새 칸 "전달 메모"(꼭 적기). `save-send.js:169` 의 빈 글 대신 이 값을 보낸다.
- **파일로 올린 도면 — 바꿀 도면 꼭 고르기**(§9 답): 직접 올린 파일이 섞이면 지금 '교체 대상' 고르기 자리에 "파일로 올린 도면은 바꿀 도면을 골라 주세요. 새로 더하는 도면이면 '새 도면'을 골라요." + 고르기(도면 1 ~ n · 새 도면). 안 고르면 400 `PICK_TARGET` "바꿀 도면을 골라 주세요." 고른 도면의 공장 지정 · 막힘 · '바뀐 도면' 표시를 새 파일이 이어받는다(§3-5). 마법사 시트는 지금처럼 같은 시트 자리로 저절로 간다(고르기 없음).
- **작업된 · 작업 중인 도면 경고**(답 3 + §9 답 "작업 중인 도면도 경고"): 서버가 바뀌는 도면 중 작업이 닿은 것이 있으면 409 `WORKED_DRAWING` + 도면별 글, 창이 한 번 묻는다 — 제목 "보내기 전 확인", 도면마다 한 문장, 그 아래 진행 줄 "도면 2 · 재단 완료 · 엣지 작업 중", `[취소]` `[그래도 보내기]` → `ack_worked=true` 로 다시. 지금 생산 확인 창 글(`save-send.js:193` · `workbench_detail_body.html:2923-2925`)은 이 창 아래 글로 합친다(확인 두 번 금지).
  - 완료: "도면 {n}{은/는} {파트들}{이/가} 완료된 도면입니다. 보내면 공장에서 다시 작업해야 합니다."
  - 작업 중: "도면 {n}{은/는} {이름}{이/가} {파트} 작업 중인 도면입니다. 보내면 공장에서 다시 작업해야 합니다."(예 "도면 2는 김재단이 재단 작업 중인 도면입니다. …")
  - 한 도면에 완료 · 작업 중이 같이 있으면 완료 문장 하나만(진행 줄이 나머지를 보인다).
  - 조사: 숫자 끝소리(1 · 3 · 6 · 7 · 8 · 0 → 은, 2 · 4 · 5 · 9 → 는), 파트 끝소리(재단 · 조립 → 이, 엣지 · 검수 → 가), 이름 끝소리(`part_mark_rules.subject_particle` 그대로).
  - "작업이 닿음" = 그 도면(지금 key)에 파트 표시 `DONE` · `BASIC` · 맡음(`NEED`, 맡은 사람 있음)이 하나라도 있거나, 손 처리로 그 파트가 완료거나, 그 도면 공장이 제작 완료.
- **시공 대기 주문 경고**(답 7): 같은 창, "이미 제작 완료된 주문입니다. 보내면 공장에 도면 바뀜 알림이 갑니다." + "주문은 시공 대기 그대로예요." 서버 409 `ORDER_MADE` → `ack_worked=true`. 단계는 그대로.

### 2-4. 공장 화면 (태블릿 · PC 보기, 시안 04)

- **막힌 도면 모양** = 지금 '도면 고치는 중' 그대로(`pp-st-revise`, 까닭 말풍선 "도면을 고치는 중이라 지금은 못 눌러요. 새 도면이 오면 다시 돼요."). 범위만 그 도면.
  - 그 파트가 이미 완료한 도면은 "재단 끝 · 김재단"으로 보이고 막힘이 안 보인다 — 지금 그대로(풀이 §11-5).
- **[도면 수정 요청]**(답 8): 그 공장 도면 위 작은 단추(`foms-prod-home__btn`, 높이 44). 남의 공장 도면 · 이미 막힌 도면('도면 고치는 중' 칸이 대신 선 카드)에는 없다. 창(지금 `home_parts_overlays.html` 겉틀): "도면 수정 요청" · "어느 도면인가요?"(그 사람이 요청할 수 있는 장 — 관리자는 모든 장, 반장 · 파트 계정은 자기 공장 장만(사장님 11-25 답 "자기 공장 도면만"), 이미 막힌 장(고치는 중 · 영업 요청 · 열린 공장 요청 — 카드 막힌 칸과 같은 `order_block`)은 빠짐 · 누른 도면이 미리 골라짐 · 여러 장. 보낸 뒤에는 같은 화면 다른 카드 창에서도 보낸 장이 빠진다) · "사유"(꼭 적기 — "꼭 적어 주세요") · "사진 (있으면 올려 주세요 · 3장까지)" + [사진 올리기](시안 글) · `[취소]` `[요청 보내기]` → "도면팀에 수정 요청을 보냈어요." 보낸 순간 고른 도면이 막힌다(§9 답 "요청하면 바로 막기").
  - 사진 칸은 앨범에서도 고르게 `data-foms-no-capture`(공용 photo-capture 가 카메라만 강제하는 함정). 고르는 즉시 한 장씩 올리고(다시 고르면 바꿔 넣음 — 빼기 단추 없음), 몸 상한에 걸리면(413) "사진이 너무 큽니다. 크기를 줄여 올려 주세요."(지금 글).
- **'바뀐 것' 탭**: 지금 줄 "도면 바뀜(바로 반영)" 그대로 + 자세한 글 "도면 2 바뀜 · 메모: 상판 깊이 600 → 580"(새 도면 "도면 6 새로 추가", 빠짐 "도면 4 빠짐"). [수정 시작]은 이 탭에 한 줄 "도면 고치는 중" · "도면 2 · 김도면"(폰 알림 없음 — §9 답). [수정 취소] "도면 수정 취소" · "도면 2 · 오도면". 반려 "도면 수정 요청 반려" · "도면 3 · 오도면 · 사유: …".
- **통째 작업 확인 창**(작업 시트 · PC [고치기] · '내 공정' [끝] — 지금 `sheet_step_confirm.html` 꼴): 막힌 도면이 있는 주문이면 본문만 새 글 "이 주문의 도면 5장 중 4장이 재단 완료로 처리돼요. 도면 2는 고치는 중이라 빼요."(여러 장 "도면 2 · 3은 …"). 제목 "재단을 작업 완료로 처리할까요?" · `[취소]` `[작업 완료]` 는 지금 글 그대로. 막힌 도면이 없으면 지금 글 그대로.
- **공정 줄 · 작업 시트 · PC 보드**: 주문 통째 막힘이 아니면 '도면 고치는 중' 대신 "도면 2 고치는 중".
- **생산 보드 배지**: 통째 막힘은 지금 글, 도면별 막힘은 "도면 2 고치는 중".

---

## 3. 자료 모양

### 3-1. 견줌 — 고치는 중 · 공장 요청을 어디에

| | 안 ⓐ 서버 소유 JSON 칸 `structured_data.drawing_fix` | 안 ⓑ 새 표 `drawing_fix_marks` |
|---|---|---|
| 생산 쪽 읽기 | 쿼리 0(첫 화면 · 도면 판 · 작업 시트 · PC 보드가 이미 주문 JSON 을 들고 있다 — `production_home_read_model.py:332`) | 화면마다 +1 쿼리, 생산 쿼리 가드 손봄 |
| 풀림(보내기)과 한 쓰기 | 전달 쓰기가 같은 사본에서 지운다 — 원자 | 같은 트랜잭션에서 다른 표도 지워야 함 |
| 동시 쓰기 | 드묾(도면팀 누름 · 공장 요청) — 주문 행 잠금 + `execute_single_order_write` | 버전 안 올림 |
| 마이그레이션 | **없음** | 표 1 + 두 DB 왕복 시험 |

**추천: 안 ⓐ** — 쿼리가 안 늘고, 수정본 전달이 같은 JSON 사본을 쓰는 순간 막힘이 같이 풀린다. 파트 표시를 따로 표로 뺀 까닭(여럿이 동시에 자주 누름)은 여기에 없다.

### 3-2. 모양

```json
"drawing_fix": {
  "fixing": {
    "sheet:Sk3a9": {"no": 2, "by_user_id": 31, "by_name": "김도면", "at": "2026-11-25T05:10:00Z"},
    "file:drawing_gateway/5801/abc.pdf": {"no": 4, "by_user_id": 31, "by_name": "김도면", "at": "…"}
  },
  "requests": [
    {"id": "fr_7c1e", "from": "factory", "targets": ["sheet:Q8b21"], "numbers": [3], "note": "측판 길이가 실측과 달라요",
     "photos": [{"key": "…", "filename": "…"}], "factory": 1, "by_user_id": 52, "by_name": "박반장", "at": "…",
     "state": "open", "done_at": null,
     "rejected_by_user_id": null, "rejected_by_name": null, "rejected_at": null, "reject_note": null}
  ],
  "log": [{"act": "start|stop|request|reject|done", "idents": ["sheet:Sk3a9"], "numbers": [2], "by_name": "김도면", "at": "…"}]
}
```

- **열쇠** = `sheet:<sheet_id>`(마법사 시트 — 판이 바뀌어도 같다) 또는 `file:<저장 key>`(직접 올린 파일). `drawing_factory.py:6-12` · 패킹 줄 열쇠 `sheet:<id>`(`packing_factory.py:11-22`)와 같은 꼴. 판정 함수 `fix_ident(entry)` 하나를 새 순수 모듈 `foms/services/orders/drawing_fix.py` 에 두고 모든 자리가 그것만 쓴다.
- `state` = `open` · `done`(수정본으로 풀림) · `rejected`(반려). [반영 완료]는 `checked` · `checked_by_name` · `checked_at` 만(상태 `open` 그대로 — 막힘은 수정본이 갈 때까지), 수정본이 건드린 열쇠는 `resolved` 에 쌓이고 대상이 모두 풀리면 `done`.
- 단계가 생산 밖으로 나가면(`release_on_stage_exit`) 열린 요청은 `done` + `done_at` + **`via: "stage_exit"`**(수정본도 반려도 아니라는 까닭) · `log` 에 `{"act": "done", "via": "stage_exit", "to": <나간 단계>, …}` 한 줄 — 알림 · '바뀐 것' 줄 없음. 작업실 줄은 [반영 완료] 안 누른 채 닫혔으면 기록 줄 "주문 단계 변경으로 수정불가 · {M/D HH:MM}"(사장님 11-25 답, 표 · 단추 없음), 누른 뒤 닫혔으면 "반영 완료" 그대로.
- `log` 는 누가 언제 눌렀나(§9 답 "누가 눌렀는지 기록") — 최근 50줄만(넘으면 앞을 버림, 이벤트 `OrderEvent` 가 전체 기록).
- 영업 요청은 지금처럼 `drawing_transfer_history` 의 `REQUEST_REVISION` 에 두고, 그 줄에 `target_idents` 를 더 적는다. 옛 줄은 `target_drawing_keys` 를 그때 `drawing_current_files` 로 풀고, 못 풀면 통째.
- 공장 요청은 `drawing_status` 를 바꾸지 않는다(영업 요청의 RETURNED 흐름 · [수정요청 취소] · 반영 완료 체크와 섞지 않음). 단 '수정 요청 · 공장'이 열려 있는 동안 [수정본 전달]은 지금 "미반영 수정 요청" 규칙과 같게 — 공장 요청도 [반영 완료] 또는 [요청 반려]가 돼야 보낸다(지휘 풀이 §11).

### 3-3. 막힘 판정 (순수 함수 하나)

`drawing_fix.blocked(sd) -> Block(whole: bool, idents: frozenset[str], why: dict)`:

1. **통째** = `drawing_status == TRANSFERRED`(옛 자료 — 지금 그대로) 또는 (`RETURNED` 이고 그 영업 요청에 대상이 없거나 못 풂)(답 5).
2. **도면별** = (`RETURNED` 이면 그 요청 `target_idents`) ∪ `fixing` 열쇠 ∪ 열린 공장 요청 `targets`(§9 답 "요청하면 바로 막기").
3. 지금 `drawing_revision_in_progress(sd)` 는 "통째"만 뜻하게 이름 그대로 둔다(지금 시험 · 관리자 뚫기 `GATE_DRAWING_REVISING` 그대로). 새 함수 `drawing_blocked(sd, entry)` · `blocked_entries(sd)` · `factory_has_blocked(sd, factory)` 를 더한다.
4. 고객컨펌 단계 영업 요청은 지금처럼 통째(풀이 §11-3) — 판정은 단계가 생산 · 시공일 때만 도면별.

### 3-4. 풀림 · 적기

- 생산 · 시공 단계 전달 쓰기 안에서: 이번 전달이 **건드린 열쇠**(같은 시트 자리 교체 · 고른 교체 대상 · 빠진 도면 · 새 시트)의 `fixing` 을 지우고, 그 열쇠를 가리키는 열린 공장 요청을 `done`. 안 건드린 도면은 그대로 막힘.
- 영업 요청은 지금처럼 `CONFIRMED` 로 돌아가며 풀린다.
- 전달 이력 `TRANSFER` 줄에 `changed: {"replaced": [2], "added": [6], "removed": [4]}` · `by_user_name`(지금 있음 — 답 4).

### 3-5. 파일로 올린 도면의 이어받기 (§9 답 "바꿀 도면을 꼭 고르게")

생산 · 시공 단계 전달에 직접 올린 파일이 있으면 파일마다 `replace_of` = 고른 도면 key 또는 `"NEW"` 를 받는다(없으면 400 `PICK_TARGET`). 고른 도면이 있으면 같은 쓰기에서:
- 공장: `drawing_factory.files[새 key] = 옛 열쇠의 공장`(1공장이면 줄 없음 — 지금 규칙).
- 막힘: 옛 열쇠의 `fixing` 은 풀림(§3-4 — 건드린 열쇠).
- '바뀐 도면' 짝: 파트 표시 짝짓기(`part_board.replaced_info`)는 `sheet_id` 만 본다 → 새 key 를 옛 key 의 대신으로 적는 작은 표 `drawing_fix.file_successor = {새 key: 옛 key}` 를 두고 `replaced_info` 가 이것도 본다(최근 50줄).

### 3-6. 통째 작업에서 한 장 빼기 · 손 처리 파트의 도면을 고쳐 보냄 (§9 답 둘 — 같은 설계)

지금 자료: 공정 칸 = `production.steps[파트].done`(주문 하나에 값 하나). 카드를 한 장도 안 쓴 파트는 이 칸이 기준(그 파트 모든 도면 완료로 보임), 한 장이라도 쓴 파트는 카드(`production_part_marks`)가 기준이고 칸은 동기화가 맞춘다(`part_steps_sync.py`).

| 후보 | 방법 | 좋은 점 | 나쁜 점 |
|---|---|---|---|
| **ⓐ 도면별 표시로 풀어 적기** | 반장이 칸을 켤 때 막힌 도면이 있으면 칸을 켜지 않고, 막히지 않은 지금 도면마다 그 파트 표시 줄을 `DONE`(재단 기본 장은 그대로 `BASIC`) · 완료한 사람 = 반장으로 쓴다. 그 순간 파트는 "카드를 쓴 파트"가 되어 칸은 동기화가 맞춘다(막힌 도면이 남아 꺼짐 → 그 도면 새 판이 완료되면 저절로 켜짐) | 지금 규칙(B5′ · 동기화 · [제작 완료] 판정 · 공장 완료 판정 · 날짜 줄 이름)을 하나도 안 바꾼다. 막힌 도면이 할 일로 남는 것이 저절로 맞다. 표 칸 · 마이그레이션 없음 | 반장 한 번 누름이 표시 줄 n개를 쓴다(주문 하나 · 많아야 수십 줄). 되돌리기는 칸 끄기가 아니라 도면마다 [되돌리기] — 지금 "카드로 모두 완료한 파트" 규칙(`STEP_SET_BY_CARDS`)과 같다 |
| ⓑ 칸에 "뺀 도면" 목록 | `steps[파트] = {done: true, except: ["sheet:…"]}` | 줄 쓰기 없음 | 칸을 읽는 모든 곳(진행 · 완료 판정 · 손 처리 칸 · 날짜 줄 · PC · 공장 완료 · 동기화)이 `except` 를 알아야 함 — 자리가 많고 빠뜨리기 쉽다 |
| ⓒ 막혀 있는 동안 통째 작업 막기 | 1판 추천 | 쉬움 | **사장님 답과 다름** |

**추천: ⓐ.** 같은 함수 `expand_hand_step(sd, marks, part, *, exclude_keys, by_user, at)` 를 두 곳에서 부른다:
1. **통째 작업 켜기**(`POST /api/orders/<id>/production/steps`, `done=true`, 그 파트 카드 0장, 막힌 도면 1장 이상): 칸은 켜지 않고 막히지 않은 도면 줄을 쓴다. 응답 `data.expanded = {part, done_n, skipped_numbers}` — 화면은 그 파트 칸을 "재단 4/5 · 1장 미완료"로 그린다(지금 `PART_USES_CARDS` 진행 글 꼴). 막힌 도면이 없으면 지금 그대로(칸만 켬).
2. **손 처리한 파트가 있는 주문의 도면을 고쳐 보냄**(생산 단계 전달 쓰기 안, `sync_steps_in_drawing_write` 바로 앞): 칸이 손으로 켜져 있고 카드 0장인 파트마다, 이번에 **안 바뀐** 지금 도면 줄을 `DONE` · 완료한 사람 = 칸을 켠 사람 이름(`steps[파트].by_name`) · 시각 = 칸 시각으로 쓴다. 그러면 동기화가 새 판(줄 없음)을 보고 칸을 끈다 = "고친 도면만 다시 할 일, 나머지는 완료"(§9 답).
- 표시 줄은 `updated_by_user_id` = 누른 사람(2번은 보낸 도면팀원), 이벤트 `PRODUCTION_STEP_CHECKED` payload 에 `expanded_keys` · `via: 'step_expand'`. 같은 파트 다른 공장 장은 공장 범위 규칙 그대로(반장은 자기 공장 장만 — 지금 `factory_gate`).
- 이름 · 시각 스냅샷이라 날짜 줄 "재단 완료 · 박반장"이 지금처럼 보인다.

### 3-7. 패킹 줄 (§9 답 "고친 도면 줄의 체크 풀기")

- 대상: 공장 꼴 패킹(2공장 장이 섞인 주문 — 줄 열쇠 `sheet:<id>`)만. 1공장뿐 주문은 제품마다 3줄이라 도면 줄이 없다 — 그대로.
- 막힌 도면 줄: 체크 · 체크 풀기 모두 409 `DRAWING_REVISING`(패킹 API). 
- 전달 쓰기 안: 바뀐 열쇠(§3-4)의 패킹 줄 체크를 지운다(출발 보고 `departed_at` 뒤에는 그대로). 그 공장 상차 완료는 지금 규칙(제작 완료가 풀리면 같이 풀림)대로.
- 패킹은 `shipment.packing` 서버 소유 칸 — 전달 API 가 같은 JSON 사본에서 지운다(패킹 API 를 부르지 않음).

### 3-8. 폼 저장 · 초안 · 주문 만들기가 덮지 못하게

- `structured_form_projection.SERVER_LOCKED_KEYS`(`:78-101`)에 `"drawing_fix"`.
- `drawing_factory.strip_client_factory_state`(`:385-400`)가 `drawing_fix` 도 뺀다 → 주문 만들기(`order_create.py:116`) · 초안 자동 저장(`erp_orders_structured.py:2391`)이 저절로 따른다.

### 3-9. 마이그레이션 — **필요 없음**

새 칸은 주문 JSON 안, 없으면 "고치는 중 없음". 표시 줄은 지금 표 그대로 쓴다(§3-6). 옛 영업 요청 줄은 읽을 때 푼다.

---

## 4. 규칙

### 4-1. 누가 무엇을 (서버가 막는다)

| 일 | 도면팀 STAFF · MANAGER | 지정 도면 담당 | 관리자 | 영업 | 반장(`production_lead`) | 파트 계정 | 보기만 |
|---|---|---|---|---|---|---|---|
| '생산 중' 칸 · 상세 · 공장 진행 보기 | 됨 | 됨 | 됨 | 지금 작업실 규칙 | — | — | 지금 규칙 |
| [수정 시작] | **됨** | 됨 | 됨 | 안 됨 | 안 됨 | 안 됨 | 안 됨 |
| [수정 취소] | **됨**(누가 시작했든) | 됨 | 됨 | 안 됨 | 안 됨 | 안 됨 | 안 됨 |
| 수정본 보내기(생산 · 시공 단계) | **됨(답 4)** | 됨 | 됨 | 안 됨 | 안 됨 | 안 됨 | 안 됨 |
| 수정본 보내기(그 밖 단계) | 지금 그대로(지정 담당 · 관리자) | | | | | | |
| 공장 [도면 수정 요청] | 안 됨 | 안 됨 | 됨(모든 도면) | 안 됨 | **자기 공장 도면만(사장님 11-25 답)** | **자기 공장 도면만(답 8)** | 안 됨 |
| 공장 요청 [반영 완료] · [요청 반려] | **됨** | 됨 | 됨 | 안 됨 | 안 됨 | 안 됨 | 안 됨 |
| 통째 작업(공정 칸) | 지금 그대로(반장 · 관리자) — 막힌 도면은 뺌(§3-6) | | | | | | |
| 영업 수정 요청 | 지금 그대로(영업 담당 · 관리자) | | | | | | |

- 도면팀 술어 = 새 `can_fix_production_drawing(user, order)` = 단계가 생산 · 시공이고 `can_set_sheet_factory(user)`(도면팀 STAFF · MANAGER + 관리자, `erp_policy_permissions.py:148-168`)와 같은 판정. 전달 API · 작업실 단추 · 마법사 '도면 발송' 칸 잠금 · N1 · N2 · N4 가 같은 술어(화면 == 서버). 그 단계에서는 "도면 담당자가 지정되지 않아…" 400 도 넘어간다(지휘 풀이).
- 공장 요청 술어 = 새 `can_request_drawing_fix(user, order, entries)` = 관리자는 모든 도면, 반장 · 파트 계정은 자기 공장 도면만(사장님 11-25 답 "자기 공장 도면만" — 카드 쓰기 `factory_gate` 와 같은 `can_write_sheet`), 단계가 생산일 때만. 창 고르기 · 판 단추 · 사진 길 주문 문 · 서버 판정이 같은 `can_request_entry` 하나를 쓴다.

### 4-2. 거절 code · 글

| code | 상태 | 언제 | 글 |
|---|---|---|---|
| `NOTE_REQUIRED` | 400 | 생산 · 시공 단계 전달에 메모 빈 글 | 공장에 남길 메모를 적어 주세요. |
| `PICK_TARGET` | 400 | 생산 · 시공 단계 직접 파일에 바꿀 도면 안 고름 | 바꿀 도면을 골라 주세요. |
| `WORKED_DRAWING` | 409 | 작업이 닿은 도면 + `ack_worked` 없음 | 도면마다 §2-3 두 문장 중 하나 |
| `ORDER_MADE` | 409 | 시공 단계 + `ack_worked` 없음 | 이미 제작 완료된 주문입니다. 보내면 공장에 도면 바뀜 알림이 갑니다. |
| `FIX_FORBIDDEN` | 403 | [수정 시작] · [수정 취소] · [요청 반려] 권한 없음 | 도면 수정은 도면팀이나 관리자만 표시할 수 있어요. |
| `FIX_STAGE` | 409 | 생산 단계가 아닌데 [수정 시작](시공 대기 포함) | 생산 중인 주문만 수정 시작을 표시할 수 있어요. |
| `FIX_NOT_CURRENT` | 409 | 고른 도면이 지금 확정 도면에 없음 | 지금 도면에 없는 장이에요. 화면을 다시 열어 주세요.(지금 글 `drawing_factory.NOT_CURRENT_MESSAGE`) |
| `REQUEST_FORBIDDEN` | 403 | 공장 요청 권한 없음 · 남의 공장 도면 | 도면 수정 요청은 반장이나 그 도면 파트 담당만 할 수 있어요. |
| `REQUEST_NOTE_REQUIRED` | 400 | 공장 요청 사유 빈 글 | 사유를 적어 주세요. |
| `REQUEST_PICK` | 400 | 공장 요청 도면 0장 | 수정할 도면을 골라 주세요. |
| `REQUEST_FORBIDDEN`(남의 공장) | 403 | 반장 · 파트 계정이 남의 공장 도면을 고름 | 카드 쓰기 공장 문의 지금 글 "{N}공장에서 작업하는 도면이에요. 위 [다시 받기]를 눌러 주세요." |
| `REQUEST_PHOTOS` | 400 | 사진 4장 이상 · 경로 이상 · 사진 길에 그림 아닌 파일(저장소 `get_file_type`) | 사진은 3장까지 올릴 수 있어요. / 사진을 다시 올려 주세요. |
| `REQUEST_BLOCKED` | 409 | 이미 막힌 도면(고치는 중 · 영업 요청 · 열린 공장 요청)이 낀 요청 | 그 막힘의 지금 글(`order_block` 의 `why` — "도면을 고치는 중이라 지금은 못 눌러요. 새 도면이 오면 다시 돼요.") |
| `INVALID_STAGE` | 409 | 공장 요청 · 사진 길인데 생산 단계 아님 | 공장 완료 API 의 지금 글 "생산 단계 주문이 아니에요. 다시 받아 주세요." |
| `REJECT_NOTE_REQUIRED` | 400 | [요청 반려] 사유 빈 글 | 반려 사유를 적어 주세요. |
| `REQUEST_CLOSED` | 409 | 이미 반영된 요청을 반려 · 닫힌 요청에 [반영 완료] · 같은 멱등 열쇠인데 요청 줄이 없음 | 이미 처리된 요청이에요. 화면을 다시 열어 주세요. |
| `REQUEST_NOT_FOUND` | 404 | [요청 반려] · [반영 완료]의 요청 번호가 없음 | `REQUEST_CLOSED` 와 같은 글 |
| `FACTORY_REQUEST_OPEN` | 400 | 열린 공장 요청이 있는데 전달 | 공장 수정 요청을 [반영 완료]나 [요청 반려]로 처리한 뒤에 보낼 수 있어요. |
| `DRAWING_REVISING` | 409 | 막힌 도면 누름 · 패킹 줄 · [제작 완료] · [N공장 완료] | 지금 글 그대로 — 자료에 `numbers` 를 더 싣는다 |

### 4-3. 막는 문 자리 전수

`git grep -n "drawing_revision_in_progress\|revision_in_flight_block\|production_drawing_badge\|production_start_block" -- foms templates static/js`(시험 · 정의 모듈 밖) = **7 파일 9 줄 + 표시 모듈 1 파일 2 줄**, 그 값을 그리는 템플릿 4 · JS 2.

| 자리 | 지금 | 2판 |
|---|---|---|
| 도면 누름 `part_mark_gates.order_gate`(`:93-108`) ← `part_mark_write.py:366` · 일괄 기본 `:435` | 통째 | **도면별** — 인자에 도면 항목 |
| 도면 판 막힌 칸 `part_card_state.order_block`(`:41-57`) ← `part_board.py:274` · `:344` · `:465` | 통째 | **도면별** — (주문, key) |
| 작업 시트 PC 줄 `pc_sheet.py:133` · `:196` | 통째 | **도면별** |
| 공정 칸 통째 작업 `step_cell_gate`(`:213`) ← `api/production/orders.py:1168` | 통째면 막음 | 통째면 막음 · **도면별이면 막힌 도면을 빼고 처리**(§3-6) |
| PC [모두 작업] `pc_sheet.py:206` | 통째면 숨김 | 통째면 숨김 · 도면별이면 보임(같은 API) |
| 공정 줄 [<공정> 끝] `production_home_read_model.py:332` · `home_step_panel.py:139-155` · `home_steps.html` · `home_step_panel.html` · `home_pc_macros.html` | 통째면 '도면 고치는 중' | 통째면 그대로 · 도면별이면 [끝] 보임(확인 창 새 글 §2-4) |
| [N공장 완료] `factory_complete.py:194` | 통째 | 통째 또는 **그 공장에 막힌 도면이 있으면** 막음(지휘 풀이) |
| [제작 완료] `complete_order.py:255` ← `order_write_helpers.py:113-120` | 통째 | 통째 또는 **막힌 도면 하나라도** 막음(§9 답 "그 도면이 끝날 때까지") · 관리자 뚫기 그대로 |
| 마지막 검수 장 "제작 완료할까요?" `part_mark_write.py:310` · `:321` · `:333` | 통째면 안 물음 | 위 두 줄과 같은 판정 |
| [제작 시작] `api/production/orders.py:567` | 통째 | 그대로 통째만(답 2 "나머지는 계속 작업") |
| [수정 제작] `api/production/orders.py:748` | 통째 | 그대로 통째만 |
| ERP 보드 단계 칸 `board_state_display.py:72` | 통째 | 그대로 통째만 |
| 생산 보드 배지 · 시작 막힘 `production_drawing_gate_display.py:39-55` | 통째 | 배지에 "도면 2 고치는 중" 더함 · 시작 막힘 그대로 |
| 도면 도착 까닭 `drawing_arrival.py:154-162` | 생산 전 | 그대로 |
| 패킹 줄 작업 `foms/api/shipment/packing.py` · `packing_factory.py` | 막힘 없음 | **막힌 도면 줄만 막음**(§3-7) |
| 상차 완료 | 없음 | 그대로([N공장 완료] 막힘이 대신 막음) |
| 공장 지정 `drawing_factory.py:290-355` | 없음 | 그대로 |
| 관리자 뚫기 `admin_override.py:54-70` · `foms-admin-override.js:41` | — | 그대로 |

---

## 5. API

공통: 응답 `{success, data, error}`(생산 API 꼴 — `part_mark_gates.Gate.body`), 주문 행 잠금 + `execute_single_order_write`(버전 +1 · 영수증 = 멱등), `OrderEvent` + `log_access`. 새 라우트 넷은 매니페스트 둘(`docs/harness/foms_order_mutation_policy_manifest.json` · `foms_write_guard_manifest.json`)에 `mode: guard`.

| # | 주소 | 정책 id | 요청 | 응답 | 멱등 | 이벤트 · 감사 | 알림 | 묶음 |
|---|---|---|---|---|---|---|---|---|
| N1 | `POST /api/orders/<id>/drawing/fix/start` | `DRAWING_TEAM` | `{targets: [{sheet_id}|{key}]}` | `{fixing: [{no, ident, by_name, at}], mutation_version}` | 이미 고치는 중 → 200 `changed:false` | `DRAWING_FIX_STARTED` `{numbers, idents}` | 생산 '바뀐 것' 한 줄(폰 없음) | D3 |
| N2 | `POST /api/orders/<id>/drawing/fix/stop` | `DRAWING_TEAM` | `{targets}` | 같음 | 고치는 중 아님 → 200 `changed:false` | `DRAWING_FIX_STOPPED` | 생산 '바뀐 것' 한 줄 | D3 |
| N3 | `POST /api/orders/<id>/production/drawing-request` | `PRODUCTION_EDIT` | `{targets, note, photos?(≤3)}` | `{request}` | 헤더 `Idempotency-Key` | `PRODUCTION_DRAWING_REQUESTED` | 도면팀 전원 + 관리자(확인 창 + 폰 + 종) | D4 |
| N4 | `POST /api/orders/<id>/drawing/fix/requests/<rid>/reject` | `DRAWING_TEAM` | `{note}` | `{request}` | 이미 반려 → 200 `changed:false` · 반영된 것 409 `REQUEST_CLOSED` | `DRAWING_FIX_REQUEST_REJECTED` | 요청한 사람(종 + 폰) + 생산 '바뀐 것' 한 줄 | D4 |
| N5 | 공장 요청 [반영 완료] — 지금 영업 요청 체크 `POST /api/orders/<id>/request-revision-check`(`erp_orders_revision.py:531`)의 짝 `POST /api/orders/<id>/drawing/fix/requests/<rid>/check` | `DRAWING_TEAM` | `{checked: bool}` | `{request}` | 같은 값 → 200 | `DRAWING_FIX_REQUEST_CHECKED` | 없음 | D4 |
| C1 | `POST /api/orders/<id>/transfer-drawing`(고침) | 지금 | + `ack_worked` · 파일마다 `replace_of` | 지금 + `changed` | 지금 | payload `changed` | 지금 + 글에 번호 · 메모 | D2 |
| C2 | `POST /api/orders/<id>/drawing-wizard/transfer-pending`(고침) | 지금 | `note`(이미 받음) · `ack_worked` | 같음 | 지금 | 같음 | 같음 | D2 |
| C3 | `POST /api/orders/<id>/request-revision`(고침) | 지금 | 그대로 | 그대로 | — | 이력 줄 `target_idents` | 지금 | D1 |
| C4 | `POST /api/orders/<id>/production/steps`(고침) | 지금 | 그대로 | + `data.expanded` | 지금 | payload `expanded_keys` · `via` | — | D1 |
| C5 | 패킹 줄 작업(`foms/api/shipment/packing.py`, 고침) | 지금 | 그대로 | 막힌 줄 409 | 지금 | — | — | D1 |
| R1 | `GET /api/orders/<id>/drawing/fix/progress` | 읽기 | — | 도면마다 `{no, ident, factory, parts{cut:{state,name}…}, worked, fixing, requests}` | — | — | — | D2 |

- N5 는 1판에 없던 것: 공장 요청도 [반영 완료]를 해야 보내는 규칙(§3-2)이라 체크 길이 필요하다. 매니페스트 등재 대상은 N1 ~ N5 다섯.
- R1 = 마법사 저장 창이 "바뀐 도면" · 경고를 미리 그릴 때(작업실 상세는 페이지 그릴 때 같은 값). 쿼리 = 주문 1 + 표시 1.
- C1 · C2 순서: 권한(§4-1) → 메모(400) → 파일 바꿀 도면(400) → 열린 공장 요청(400) → 지금 검사들(반영 안 한 영업 요청 400 등) → 작업 닿은 도면 · 시공 단계(409, `ack_worked` 면 지나감) → 쓰기(§3-4 풀림 · §3-5 이어받기 · §3-6 손 처리 풀기 · §3-7 패킹 풀기 — 같은 사본).
- N3 사진: 영업 요청 참고 파일과 같은 저장 · 검사(`foms/services/orders/drawing_revision_files.normalize_revision_files`, `drawing_gateway/` key). 영업 업로드 길(`drawing-gateway-upload`)은 `ERP_EDIT`(CS · 영업)라 생산 계정이 못 지나서 D4 가 생산 쪽 길 `POST /api/orders/<id>/production/drawing-request/photo`(`PRODUCTION_EDIT`, 매니페스트 둘)를 열었다 — 그 주문에 이 사람 몫 도면(사람 · 공장 — 막힘은 안 봄)이 없으면 403 `REQUEST_FORBIDDEN` · 그림 파일만(400 `REQUEST_PHOTOS`) · 몸 상한은 영업 창구 업로드와 같은 줄(`foms/platform/request_limits.py`, 1 MiB 기본 캡 밖).
- N3 멱등은 REV-00 `execute_order_mutation` 의 `idempotency_key`(`execute_single_order_write` 는 열쇠를 안 받는다) — 막힘 검사는 엔진 콜백 안이라 같은 열쇠로 다시 온 요청은 영수증 답으로 돌아간다.

---

## 6. 알림

| 일 | 받는 사람 | 꼴 | 근거 |
|---|---|---|---|
| 공장 요청(N3) | 도면팀 전원 + 관리자 | **영업 수정 요청과 똑같이**(`DRAWING_REVISION` 꼴 — 확인 창 + 폰 + 종, `erp_orders_revision.py:194-247` · `push_sender.py:104-119`), 제목 "공장 도면 수정 요청", 글 "주문 #5801 (정하늘) 공장 도면 수정 요청이 접수되었습니다. 대상: 3번 도면. 사유: …" | §9 답 |
| 수정 시작(N1) | 생산팀 | '바뀐 것' 한 줄만 "도면 고치는 중" · "도면 2 · 김도면"(폰 없음) | §9 답 |
| 수정 취소(N2) | 생산팀 | '바뀐 것' 한 줄 "도면 수정 취소" · "도면 2 · 오도면"(폰 없음) | 지휘 풀이(시작과 같게) |
| 수정본(C1 · C2) | 생산 · CS · 영업(지금 `drawing_hotfix`, `production_change.py:45`) | 지금 그대로 + 글에 바뀐 번호 · 메모 | 답 6 |
| 반려(N4) | 요청한 사람(종 + 폰) + 생산 '바뀐 것' | "도면 수정 요청 반려" · "도면 3 · 오도면 · 사유: …". 반려한 사람이 요청한 사람 본인이거나 요청한 사람 계정이 꺼졌으면 알림 줄 · state · 폰 0('바뀐 것' 줄은 그대로) | §9 답 |
| 알림 종류(D4) | — | `DRAWING_FACTORY_REQUEST`(P1 · 높은 긴급도 · 확인 창, 누르면 작업실 요청사항 칸) · `DRAWING_FACTORY_REQUEST_REJECTED`(P1 · 요청자 한 명, 누르면 생산 '바뀐 것') — 폰 배너는 제목 · 번호 · 고객 이름 · 고정 글(사유 없음), 벨 목록 · PC 종 누름 갈래도 같은 곳 | 구현 |
| 생산 변경 알림을 도면팀이 | 지금처럼 안 받음 | — | 지휘 풀이 |

- 생산 '바뀐 것' 줄은 `production_change_alerts.py` 가 `drawing_transfer_history` · `OrderEvent` 를 읽어 만든다 — N1 · N2 · N4 는 `OrderEvent` 로 남기고 공장 바뀜 줄(`_factory_change_item`)과 같은 꼴의 읽기 함수를 더한다. 생산 진입(D22) 앞 일은 지금처럼 안 보인다.

---

## 7. 성능 · 예산

- **'생산 중' 칸**: 모집단 SQL 두 번(① 요청 · 고치는 중 — `structured_data ? 'drawing_fix'` 또는 `drawing_status='RETURNED'` · ② 나머지 — `erp_stage_code` 색인 + `erp_construction_date >= 오늘` + `NOT EXISTS(order_construction_attempts is_current)`) + 지금 하이드레이트 + **파트 표시 1번**(그 쪽 25줄 주문 IN). 다른 칸 · 기본 목록 = 0 증가. 가드: `tests/domains/test_drawing_workbench_query_count.py` 에 생산 칸 경우 — "주문 8건 더해 증가 0 · 절대 상한 지금 + 3".
- **작업실 상세**: 생산 · 시공 대기만 파트 표시 1번 더. 다른 단계 0.
- **생산 첫 화면 · 도면 판 · 작업 시트 · PC 보드**: 막힘 판정은 든 주문 JSON 에서 — **쿼리 0 증가**. `test_production_home_query_count.py` · `test_production_selfclaim_query_count.py` · `test_production_factory_query_count.py` 숫자 그대로.
- **통째 작업(C4)**: 표시 읽기는 지금도 잠금 아래 1번(`order_marks`). 풀어 쓰기는 `insert … on conflict` 한 문장(주문 하나 줄 n개) — N+1 금지.
- **출고 조각(fragment)은 건드리지 않는다**(패킹 막힘은 패킹 쓰기 API 안 판정만).

---

## 8. 구현 묶음 (넷 — D1 먼저, D2 · D3 · D4 는 D1 위)

### D1 자료 · 막힘 판정 (화면 새 칸 없음 — 먼저 올림)

- **건드리는 파일**:
  - 새: `foms/services/orders/drawing_fix.py`(열쇠 · `blocked` · `drawing_blocked` · `blocked_entries` · `factory_has_blocked` · 글 꼴 · 조사) · `tests/domains/test_drawing_fix_gate.py` · `tests/domains/test_production_step_expand.py`.
  - 고침: `foms/services/orders/structured_form_projection.py`(잠금 칸) · `foms/services/orders/drawing_factory.py`(strip) · `foms/api/drawing/erp_orders_revision.py`(C3 `target_idents`) · `foms/services/production/part_mark_gates.py` · `part_card_state.py` · `part_board.py` · `part_mark_write.py` · `pc_sheet.py` · `factory_complete.py` · `complete_order.py` · `order_write_helpers.py` · `foms/services/production_home_read_model.py` · `foms/services/production/home_step_panel.py` · `foms/services/production_drawing_gate_display.py` · `foms/services/production/part_steps_sync.py`(`expand_hand_step` — D2 가 부름) · `foms/api/production/orders.py`(C4) · `foms/services/shipment/packing_factory.py` · `foms/api/shipment/packing.py`(C5 · 풀기 함수 — D2 가 부름) · `static/js/production/foms-production-sheet-parts.js`(확인 창 본문 새 글 — 도면별 막힘이 있을 때만).
- **새 API**: 없음(C3 · C4 · C5 고침).
- **새 글**: "도면 {n} 고치는 중"(배지 · 공정 줄 · 작업 시트) · 확인 창 "이 주문의 도면 {N}장 중 {M}장이 {파트} 완료로 처리돼요. 도면 {n}{은/는} 고치는 중이라 빼요."
- **완료 기준**: 새 시험 둘 초록(열쇠 · 통째/도면별 · 옛 영업 요청 줄 풀기 · 공장별 · 통째 작업 풀어 쓰기 · 막힌 줄 패킹 409 · [제작 완료] · [N공장 완료] 막힘) · 지금 `tests/domains/test_confirm_drawing_gate_paths.py` · `test_drawing_production_hotfix.py` · `test_production_rework_drawing_gate.py` · `test_production_part_marks_api.py` · `test_production_part_steps_sync.py` · `test_production_pc_sheet.py` 초록 · 생산 쿼리 가드 셋 숫자 그대로 · `python -c "import app; print('APP_OK')"` · 실화면: 로컬 PG 에서 도면 3장 주문에 대상 1장 영업 요청 → 태블릿 1176 도면 판 그림(그 도면만 빨강) 1장 · 작업 시트 통째 작업 확인 창 그림 1장.
- 이 묶음만으로 바뀌는 행동: 생산 · 시공 단계 영업 요청이 고른 도면만 막는다(답 5). 다른 새 길은 아직 없다.

### D2 보내기

- **건드리는 파일**: `foms/api/drawing/erp_orders_drawing.py`(C1 · 순서 · 풀림 · 이어받기 · 손 처리 풀기 · 패킹 풀기 · 알림 글) · `foms/api/drawing/wizard.py`(C2) · 새 `foms/api/drawing/erp_orders_drawing_fix_read.py`(R1) · `foms/services/orders/drawing_transfer.py`(`changed` 계산) · `foms/services/orders/erp_policy_permissions.py`(`can_fix_production_drawing`) · `foms/services/production_change_alerts.py`(번호 · 메모 글) · `foms/services/production/part_board.py`(`replaced_info` 가 `file_successor` 봄 — D1 과 같은 파일, D1 뒤라 겹침 없음) · `foms/web/drawing/wizard.py`(칸 잠금 술어) · `foms/web/drawing/workbench.py`(상세 `can_transfer` 자리 `:1298` 만) · `templates/drawing/wizard.html`(저장 창 칸) · `static/js/drawing/save-send.js` · `templates/drawing/partials/workbench_detail_body.html`(전달 창 부분 `:1757-1925` · `:2873-2945` 만) · 새 CSS 줄은 `static/css/contexts/drawing/workbench-fix.css`(새 파일, D3 · D4 도 씀 — §8-5).
- **새 API**: R1. 매니페스트 등재 없음(읽기).
- **새 글**: 바뀐 도면 줄 · 꼭 적기 · 메모 안내 · `NOTE_REQUIRED` · `PICK_TARGET` · 파일 고르기 안내 · 보내기 전 확인 창 전부 · 시공 대기 경고 · 마법사 "전달 메모" · '바뀐 것' "도면 {n} 바뀜 · 메모 …".
- **완료 기준**: 새 `tests/domains/test_drawing_fix_transfer.py`(두 길 같은 규칙 — 도면팀 누구나 · 담당 없음 통과 · 메모 400 · 파일 400 · 열린 공장 요청 400 · 409 둘 · ack · 풀림 원자 · 손 처리 풀기 · 패킹 풀기 · `changed`) · 지금 `test_drawing_production_hotfix.py` 고쳐 초록 · `node --check static/js/drawing/save-send.js` · 인라인 스타일 래칫 · 실화면 1440 · 80%: 작업실 전달 창(경고) 1장 · 마법사 저장 창 1장 · 태블릿 '바뀐 것' 1장.

### D3 작업실 화면

- **건드리는 파일**: `foms/services/drawing_workbench_read_model.py`(생산 칸 모집단) · `foms/web/drawing/workbench.py`(목록 칸 · 정렬 · 상한 · 상세 진행 값 — `:221-242` · `:658-1160` · 상세 값 조립) · 새 `foms/services/drawing_fix_progress.py`(도면별 진행 글 — R1 과 같은 함수, D2 가 먼저 만들면 D3 은 부르기만 → §8-5) · 새 `foms/api/drawing/erp_orders_drawing_fix.py`(N1 · N2) · `templates/drawing/partials/workbench_dashboard_body.html`(칸 · 줄 값) · 새 `templates/drawing/partials/workbench_fix_progress.html`(공장 진행 칸) + `workbench_detail_body.html` 에 include 한 줄 · 머리 줄 링크 · 새 `static/js/drawing/workbench-drawing-fix.js` · `static/js/drawing/workbench-dashboard.js`(칸 누름) · `foms/platform/blueprints.py`(새 Blueprint 등록) · 매니페스트 둘.
- **새 API**: N1 · N2.
- **새 글**: 칸 "생산 중" · 줄 표시 · 다음 액션 · 단계 · 진행 요약 · 상한 줄 · "생산 작업 시트 열기" · "공장 진행" · 진행 칸 글 · [수정 시작] · [수정 취소] · 두 확인 창 · `FIX_*` 글 · '바뀐 것' "도면 고치는 중" · "도면 수정 취소".
- **완료 기준**: 새 `tests/domains/test_drawing_workbench_production_tab.py`(모집단 — 시공일 지남 · 시공 시작 빠짐 · 정렬 · 요청 주문이 캡에 안 잘림) · `tests/domains/test_drawing_fix_start_api.py`(권한 · 409 · 멱등 · 이벤트 · '바뀐 것' 줄) · `test_drawing_workbench_query_count.py` 생산 칸 경우 · 매니페스트 시험 · `node --check` · 새 JS 300줄 래칫 · 실화면 1440 · 80%: 목록 '생산 중' 1장 · 상세 공장 진행 1장(시안 01 · 02 와 견줌).

### D4 공장 요청 · [요청 반려]

- **건드리는 파일**: 새 `foms/api/production/drawing_request.py`(N3) · `foms/api/drawing/erp_orders_drawing_fix.py`(N4 · N5 — D3 이 만든 파일에 라우트 더함 → §8-5) · `foms/services/notifications/push_sender.py`(새 알림 종류를 `DRAWING_REVISION` 과 같은 무리에) · `templates/production/partials/home_parts.html`(단추) · `templates/production/partials/home_parts_overlays.html`(창) · 새 `static/js/production/foms-production-drawing-request.js` · `static/css/contexts/production/parts.css`(단추 · 고르기 몇 줄) · 새 `templates/drawing/partials/workbench_fix_requests.html`(요청사항 안 공장 요청 · 반려 창) + `workbench_detail_body.html` include 한 줄 · 새 `static/js/drawing/workbench-factory-request.js` · `foms/web/drawing/workbench.py`(상세 값에 공장 요청 · 목록 맨 위 판정에 공장 요청 — D3 뒤) · `foms/services/production_change_alerts.py`(반려 줄 — D2 뒤) · `foms/platform/blueprints.py` · 매니페스트 둘.
- **새 API**: N3 · N4 · N5.
- **새 글**: [도면 수정 요청] · 창 글 전부 · 보낸 뒤 글 · `REQUEST_*` · `REJECT_NOTE_REQUIRED` · `REQUEST_CLOSED` · `FACTORY_REQUEST_OPEN` · [요청 반려] · 반려 창 · 반려 기록 줄 · 알림 제목 둘.
- **완료 기준**: 새 `tests/domains/test_production_drawing_request_api.py`(반장 · 파트 자기 공장 · 남의 공장 403 · 사진 3장 · 바로 막힘 · 멱등 · 알림 수신자 = 도면팀 전원 + 관리자 · 확인 창 종류) · `tests/domains/test_drawing_fix_reject_api.py`(사유 400 · 막힘 풀림 · 요청한 사람 알림 · 반영된 것 409) · 매니페스트 시험 · `node --check` · 래칫 · 실화면: 태블릿 1176 요청 창 1장 · 작업실 요청사항 공장 요청 + [요청 반려] 1장.

### 8-5. 파일 겹침 표

| 파일 | D1 | D2 | D3 | D4 | 겹침 푸는 법 |
|---|---|---|---|---|---|
| `foms/services/production/part_board.py` | 막힘 도면별 | `replaced_info` | | | D1 → D2 차례 |
| `foms/services/production/part_steps_sync.py` | `expand_hand_step` 정의 | (부름만, 파일 안 고침) | | | 없음 |
| `foms/services/shipment/packing_factory.py` | 풀기 함수 정의 | (부름만) | | | 없음 |
| `foms/web/drawing/workbench.py` | | `:1298` 술어 | 목록 · 상세 값 | 공장 요청 값 | D2 → D3 → D4 차례(D2 는 한 줄) |
| `templates/drawing/partials/workbench_detail_body.html` | | 전달 창 부분 | include 한 줄 · 머리 링크 | include 한 줄 | 새 칸은 새 partial 로 → 본문은 줄 몇 개만, 차례 D2 → D3 → D4 |
| `foms/services/production_change_alerts.py` | | 번호 · 메모 | 시작 · 취소 줄 | 반려 줄 | D2 가 읽기 함수 틀을 만들고 D3 · D4 는 종류만 더함 |
| `foms/api/drawing/erp_orders_drawing_fix.py`(새) | | | 만듦(N1 · N2) | 라우트 더함(N4 · N5) | D3 → D4 |
| 도면별 진행 함수(`drawing_fix_progress.py`, 새) | | R1 이 만듦 | 부름 | | D2 → D3 |
| `static/css/contexts/drawing/workbench-fix.css`(새) | | 만듦 | 줄 더함 | 줄 더함 | 차례대로, 겹치는 규칙 없음 |
| `foms/platform/blueprints.py` · 매니페스트 둘 | | | 줄 더함 | 줄 더함 | D3 → D4 |
| `foms/services/orders/drawing_fix.py`(새) | 만듦 | 쓰기 함수 더함 | 쓰기 함수 더함 | 쓰기 함수 더함 | 쓰기 함수는 따로 이름(풀림 · 시작/취소 · 요청/반려) — 같은 줄 안 건드림 |

- **올리는 차례**: D1 → D2 → D3 → D4(차례대로면 겹침 0). D3 · D4 를 동시에 하면 `workbench.py` · `erp_orders_drawing_fix.py` · 매니페스트가 겹치므로 같은 사람이 하거나 차례를 지킨다.
- **되돌리기**: 커밋 되돌림으로 끝(마이그레이션 없음). D1 만 되돌리면 막힘이 주문 통째(오늘)로 돌아간다. 통째 작업으로 풀어 쓴 표시 줄(§3-6)은 되돌려도 남는다 — 그 파트가 "카드를 쓴 파트"로 남을 뿐 진행은 맞다. 이미 적힌 `drawing_fix.fixing` 이 있는 주문은 되돌리면 막힘이 사라지므로 되돌리기 전에 '생산 중' 칸에서 세어 도면팀에 알린다.

---

## 9. 정해진 것 (사장님 답 원문, 2026-11-25)

| # | 물음 | 답(원문) | 설계 자리 |
|---|---|---|---|
| Q1 · Q15 | '생산 중' 칸에 시공일이 지난 시공 대기 · 시공 시작한 주문 | "시공일이 지난 것과 시공 시작한 것은 빼기"(생산 단계 + 시공일이 오늘이거나 남은 시공 대기만, 빠진 주문은 검색으로) | §2-1 · §7 |
| Q2 · Q3 | [수정 시작] · [수정 취소] 누가 | "둘 다 도면팀 누구나"(누가 눌렀는지 기록) | §4-1 · §3-2 `log` |
| Q4 | 공장 요청 사진 | "있으면 올리기"(3장까지) | §2-4 · §4-2 |
| Q5 | 도면팀이 공장 요청을 받아들이지 않을 때 | "도면팀이 사유를 적고 닫기" — "'요청 반려' 로 버튼 만들어" | §2-2 · N4 |
| Q6 | 공장 요청이 도면을 막나 | "요청하면 바로 막기" | §3-3 |
| Q7 | 한 장 막힌 주문의 통째 작업 · 제작 완료 | "고치는 도면만 빼고 처리"(반장이 통째 작업 완료하면 막힌 도면만 빼고 나머지 완료, [제작 완료]는 그 도면이 끝날 때까지 막힘) | §3-6 · §4-3 |
| Q8 | (지휘 풀이) 시공 대기 주문 [수정 시작] | 없음 | §2-2 |
| Q9 | [수정 시작] 알림 | "'바뀐 것'에 한 줄만"(폰 알림 없음) | §6 |
| Q10 | 고친 도면의 패킹 | "고친 도면 줄의 체크 풀기"(고치는 동안 그 줄 못 누름, 출발 보고 뒤는 그대로) | §3-7 |
| Q11 | 공장 요청 알림 | "영업 수정 요청과 똑같이"(도면팀 전원 + 관리자, 확인 창 + 폰 + 종) | §6 |
| Q12 | (지휘 풀이) 도면팀 생산 변경 알림 | 지금처럼 안 받음 | §6 |
| Q13 | 통째 완료한 파트가 있는 주문의 도면을 고쳐 보냄 | "고친 도면만 다시 할 일로"(그 파트의 통째 완료가 풀리고 나머지 도면은 완료, 새 판만 다시 할 일) | §3-6 |
| Q14 | 파일로 올린 도면 | "바꿀 도면을 꼭 고르게 하기"(공장 지정 · 막힘 · '바뀐 도면' 표시 이어받음, 새로 더하는 도면이면 '새 도면'을 고름) | §2-3 · §3-5 |
| 더함 | 경고 범위 | "작업 중인 도면도 경고"(완료된 도면뿐 아니라 누가 맡아 작업 중인 도면도) | §2-3 |

---

## 10. 새 글 목록 (화면 글 전부 — 지금 글은 바꾸지 않음)

| 자리 | 새 글 | 옆의 지금 글(그대로) |
|---|---|---|
| 작업실 프로세스 맵 칸 | 생산 중 | 전체 · 대기중 · 작업중 · 수정 요청됨 · 확정 대기 · 누적 완료 · 지연 · 미확인 |
| 목록 줄 표시 | 수정 요청 · 영업 / 수정 요청 · 공장 / 도면 고치는 중 | 수정 요청됨 |
| 목록 다음 액션 | 영업 수정 요청 · {이름} / 공장 수정 요청 · {이름} · 도면 {n} / 도면 {n} 고치는 중 · {이름} | 도면 완료 · 다음 단계 확인 |
| 목록 상태 칸 | 생산 / 시공 대기 / 재단 {a}/{n} · 엣지 … · 조립 … · 검수 … / 제작 완료 | 완료 |
| 목록 상한 | 더 있는 {N}건은 안 보여요. 찾기로 찾아 주세요. | — |
| 상세 머리 | 생산 작업 시트 열기 | 단계: 생산 · 주문 담당 · 도면 담당 |
| 상세 접는 칸 | 공장 진행 | 타임라인 · 요청사항 · 파일 비교 |
| 공장 진행 칸 | {파트} 완료 · {이름} / {파트} 작업 중 · {이름} / 재단 기본 / {파트} 미정 / {파트} 완료 · {이름}(작업 시트) / {N}공장 제작 완료 / 제작 완료 | — |
| 단추 | [수정 시작] · [수정 취소] · [요청 반려] · [그래도 보내기] · [도면 수정 요청] · [요청 보내기] · [닫기] | [반영 완료] · [전달하기] · [저장 + 전달] · [취소] · [작업 완료] |
| 수정 시작 확인 창 | 도면 {n}{을/를} 고치는 중으로 표시할까요? 공장에서 도면 {n}만 작업이 막혀요. | — |
| 수정 취소 확인 창 | 도면 {n} 수정을 취소할까요? 공장에서 도면 {n}{을/를} 다시 작업할 수 있어요. | — |
| 고치는 중 줄 | 도면 고치는 중 · {이름} · {M/D HH:MM} | 도면 고치는 중(공장 — 그대로) |
| 요청 반려 창 | 요청 반려 / 반려 사유를 적어 주세요. 요청한 사람에게 알림이 가고, 도면 {n} 막힘이 풀려요. | — |
| 반려 기록 줄 | 반려 · {이름} · {M/D HH:MM} · 사유: {사유} | 반영 완료 · 미완료 |
| 단계 나감 기록 줄 | 주문 단계 변경으로 수정불가 · {M/D HH:MM}(사장님 11-25 답 글자 그대로) | 반영 완료 |
| 공장 요청 줄(작업실) | 사유: {사유} | — |
| 보내는 창 | 바뀐 도면: 도면 {n} (고침) · 도면 {m} (새 도면) · 도면 {k} (빠짐) | 생산·시공 단계입니다. 보내면 영업 확인 없이 … |
| 보내는 창 메모 | 꼭 적기 / 생산으로 넘어간 주문은 메모를 적어야 보낼 수 있어요. / 공장에 남길 메모를 적어 주세요. | 메모 · 전달 메모 |
| 보내는 창 파일 | 파일로 올린 도면은 바꿀 도면을 골라 주세요. 새로 더하는 도면이면 '새 도면'을 골라요. / 새 도면 / 바꿀 도면을 골라 주세요. | 교체 대상 |
| 마법사 저장 창 | 전달 메모(새 칸) | 도면 발송 · 영업에게 전달해요 (전달본으로 올려요) |
| 보내기 전 확인 창 | 보내기 전 확인 / 도면 {n}{은/는} {파트}{이/가} 완료된 도면입니다. 보내면 공장에서 다시 작업해야 합니다. / 도면 {n}{은/는} {이름}{이/가} {파트} 작업 중인 도면입니다. 보내면 공장에서 다시 작업해야 합니다. / 이미 제작 완료된 주문입니다. 보내면 공장에 도면 바뀜 알림이 갑니다. / 주문은 시공 대기 그대로예요. | (지금 생산 확인 글은 이 창 아래로) |
| 공장 요청 창 | 도면 수정 요청 / 어느 도면인가요? / 사유 · 꼭 적어 주세요 / 사진 (있으면 올려 주세요 · 3장까지) / [사진 올리기](시안 글) / 도면팀에 수정 요청을 보냈어요. | 취소 · 사진이 너무 큽니다. 크기를 줄여 올려 주세요.(지금 글 — 사진 몸 상한) · {N}공장에서 작업하는 도면이에요. 위 [다시 받기]를 눌러 주세요.(지금 글 — 남의 공장 도면) |
| 통째 작업 확인 창 본문 | 이 주문의 도면 {N}장 중 {M}장이 {파트} 완료로 처리돼요. 도면 {n}{은/는} 고치는 중이라 빼요. | 제목 "{파트}{을/를} 작업 완료로 처리할까요?" · 본문 "이 주문의 도면 {N}장이 모두 {파트} 완료로 처리돼요." |
| 공장 '바뀐 것' | 도면 {n} 바뀜 · 메모: {메모} / 도면 {m} 새로 추가 / 도면 {k} 빠짐 / 도면 고치는 중 + 도면 {n} · {이름} / 도면 수정 취소 + 도면 {n} · {이름} / 도면 수정 요청 반려 + 도면 {n} · {이름} · 사유: {사유} | 도면 바뀜(바로 반영) · 확인했어요 |
| 공장 막힘(번호) | 도면 {n} 고치는 중 | 도면 고치는 중 · 도면을 고치는 중이라 지금은 못 눌러요. 새 도면이 오면 다시 돼요. |
| 거절 글 | §4-2 표의 새 글 열넷(`NOTE_REQUIRED` · `PICK_TARGET` · `WORKED_DRAWING` 둘 · `ORDER_MADE` · `FIX_FORBIDDEN` · `FIX_STAGE` · `REQUEST_FORBIDDEN` · `REQUEST_NOTE_REQUIRED` · `REQUEST_PICK` · `REQUEST_PHOTOS` 둘 · `REJECT_NOTE_REQUIRED` · `REQUEST_CLOSED` · `FACTORY_REQUEST_OPEN`) | `FIX_NOT_CURRENT` · `DRAWING_REVISING` 는 지금 글 |
| 알림 | 제목 "공장 도면 수정 요청" · 글 "주문 #{id} ({고객}) 공장 도면 수정 요청이 접수되었습니다. 대상: {n}번 도면. 사유: {사유}" / 제목 "도면 수정 요청 반려" · 글 "주문 #{id} ({고객}) 도면 {n} 수정 요청이 반려됐어요. 사유: {사유}" | 도면 바로 반영됨 · [생산] 도면 바뀜 |

---

## 11. 풀이 (답을 코드에 옮기며 정한 것 — 틀리면 고침)

**지휘 풀이(답에서 바로 따름)**
- 생산 · 시공 단계에서는 "도면 담당자 없음"이어도 도면팀이 보낸다(답 4).
- 시공 대기 주문에는 [수정 시작]이 없다(답 7 "알림만").
- 도면팀은 생산 변경 알림을 지금처럼 안 받는다.
- [N공장 완료]는 막힌 도면이 그 공장 것이면 막는다(Q7 답에 글이 없음 — [제작 완료] 규칙을 공장 단위로 옮김).

**설계 풀이(내가 정함)**
1. '탭' = 프로세스 맵 끝의 새 칸(작업실에 탭 줄이 없다 — 이미 있는 칸에 얹기).
2. [수정 취소]도 '바뀐 것'에 한 줄(시작과 같게, 폰 없음).
3. 영업 요청 "요청한 도면만 막기"(답 5)는 생산 · 시공 단계에만. 고객컨펌 단계는 지금처럼 통째(제작 시작 문이 따로).
4. 공장 요청도 [반영 완료] 또는 [요청 반려]가 돼야 수정본을 보낸다(영업 요청의 지금 규칙과 같게) — 그래서 N5 [반영 완료] 길이 생겼다.
5. 이미 완료한 파트에게는 막힘이 안 보인다(그 파트 일은 끝, 새 판이 새 도면으로 나옴) — 지금 그대로.
6. 통째 작업 풀어 쓰기(§3-6)는 막힌 도면이 있을 때만. 막힌 도면이 없으면 지금처럼 칸만 켠다.
7. 경고에서 한 도면에 완료 · 작업 중이 같이 있으면 완료 문장 하나만.

## 12. 조사와 다르게 · 새로 안 것 · 확신이 낮은 곳

- 영업 요청은 도면 2장 이상이면 번호를 꼭 고르게 되어 있어(`erp_orders_revision.py:132-152`) 답 5 의 "안 고른 요청"은 도면 1장 · 협력사 요청 · 옛 자료에만 생긴다.
- 작업실 전달 창 메모 칸 이름은 "메모"(칸 안 안내 "전달 메모"), 마법사 저장 창에는 메모 칸이 없다. 상세 [생산 현황 보기]는 ERP 대시보드로 간다.
- 요청사항의 지금 "미완료" 표시가 회색 — 무채색 배지 금지와 부딪히지만 지금 모양이라 이번에 안 바꾼다(따로 여쭐 일).
- **추측**: 생산 + 시공 대기 주문 수는 1,000건보다 훨씬 적다(운영 건수 안 셈).
- **추측**: N1 · N3 · N4 의 주문 버전 +1 이 열린 영업 주문 편집 폼 저장을 409 로 만들 수 있다 — 공장 지정 API 와 같은 성질. D1 에서 확인. 마법사 시트 저장은 If-Match 를 안 보낸다.
- **확신 낮음**: 숫자 조사(은/는) — `part_mark_rules.subject_particle` 은 이름 끝 한글 받침만 본다(`:153-156`). 숫자 읽기 표는 `drawing_fix.py` 에 새로 둔다.
- ~~**확신 낮음**: 공장 요청 사진 업로드~~ — D4 확인: 영업 길은 `ERP_EDIT` 라 생산 계정에 막혀 있어 생산 쪽 길을 열었다(§5 N3 사진).
- **확신 낮음**: §3-6 ① 에서 재단 파트의 '기본'(BASIC) 장을 반장 통째 작업이 `DONE` 으로 덮지 않게 — 이미 끝(DONE · BASIC)인 줄은 건드리지 않고 '안 봄' · '작업 필요' 줄만 `DONE` 으로 쓴다. 맡은 사람이 있는 '작업 필요' 줄을 반장 이름으로 완료하는 것이 지금 손 체크 뜻(그 파트 모두 완료)과 같다고 봤다.
- **확신 낮음**: '생산 중' 칸 SQL 의 `NOT EXISTS(order_construction_attempts …)` — 나눠 시공(N3)으로 생산 단계에서도 방문이 열린 주문은 생산 단계라 그대로 넣는다(빼는 것은 시공 단계뿐).
