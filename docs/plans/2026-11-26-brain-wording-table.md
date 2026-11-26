# 회사 지식 · 온톨로지 화면 글 — 「지금 글 → 바꿀 글」 표 (2026-11-26)

사장님이 고른 번호만 고친다. 이 문서는 표까지이고, 화면 글(코드)은 아직 하나도 고치지 않았다.

- **출발점**: `docs/plans/2026-11-26-brain-decide-card-review-findings.md` §3(한글 표현 비평 — 일꾼 보고). 일꾼 보고는 주장이라, 표의 줄마다 그 글이 지금 코드에 있는지 다시 찾아 `파일:줄`을 붙였다. 줄 번호는 가지 `session/foms-graft` 기준이다.
- **고르는 법**: 「가-6, 나-1, 다-26」처럼 번호로 골라 주시면 된다. 같은 낱말이 여러 곳에 있는 것은 맨 앞 「가. 낱말 맞춤표」 번호 하나로 한꺼번에 고를 수 있다.
- **사장님 말 규칙**: 미정 · 완료 · 미완료 · 담당 · 체크 · 표기 · 지정 · 바뀐 기록 · 고객 · 직원 · 온톨로지 · 통 · 견적 · 상담 · 도면을 따른다. 「온톨로지」는 그대로 둔다. 「손님」은 모두 「고객」으로 올렸다.
- **「고치는 법」 칸**: 「저장 글은 그대로, 보일 때만 바꿈」이라고 적힌 줄은 그 글을 코드가 글자로 알아보거나 이미 저장된 카드에 들어 있는 글이다. 저장 글을 바꾸면 쌓인 카드를 못 알아본다.
- **「같이 고칠 시험」**: 그 글(또는 따옴표로 싼 짧은 이름)이 `tests/` 안 회사 지식 · 상담 · AI 직원 · 할 일 제안 쪽 시험 파일에 글자 그대로 있는 곳이다. 짧은 이름(두 글자 안팎)은 다른 뜻으로 걸렸을 수 있다 — 고치기 전에 그 시험을 열어 본다.
- **두 가지 공통 손질**(줄마다 적지 않음): 문장 안의 「A · B는」은 「A와 B는」으로 읽기 쉽게 바꾼다(메뉴 · 표 머리 같은 이름 나열은 그대로). 해요체 사이의 「~습니다 · ~다」와 「끝남 · 빔 · 뺌 · 거둠」 같은 명사형 끝은 해요체로 맞춘다.

## 먼저 고치면 좋은 스무 개

표 전체를 다 안 읽으셔도 되게, 무거운 것부터 스무 개만 뽑았다.

1. **나-1** ③ 카드 직원 쪽 글 첫 줄 「어긋남 — 회사 지식 「…」 ↔ 직원 「…」」 → 「다른 부분: 회사 지식은 「…」, 직원은 「…」」 (저장 글은 그대로, 보일 때만)
2. **나-2** 「승인된 규칙과 다름」 → 화면에서 뺌 (저장 글은 그대로)
3. **나-3** 「바깥 글」 → 「직원 안내」
4. **나-4** 「회사 지식이 맞아요 (바깥 글은 고칠 일로)」 → 「회사 지식이 맞아요 (지식 그대로)」
5. **나-5** 「바깥 글이 맞아요 (지식 고치기)」 → 「직원 안내가 맞아요 (지식 고치기)」
6. **가-6** 화면의 「손님」 (나-8 · 다 · 라-10 · 바-8 · 아-6 · 차-1 · 카 · 파 …) → 「고객」
7. **다-26** 자동 검사 꼬리표 「한자 0 안 됨 · 가림(개인정보 0) 안 됨 · 승인 지식과 부딪침 안 됨 · 꼴 안 됨」 (다-26~29) → 「한자 들어 있음 · 개인정보 들어 있음 · 기존 지식과 충돌 · 형식이 틀림」
8. **마-1** 「판 · 기록」 → 「날짜별 기록」 (마-2 설명 글도 같이)
9. **바-23** 「옛 판으로 되돌리기 제안」 (바로 아래 단추는 「버전 N」) → 「예전 버전으로 되돌리기 제안」
10. **나-14** 「③ 사장님이 정해 주실 것」 / 「③ 사장님이 정할 것」 → 「③ 사장님이 정할 것」 하나로
11. **다-1** 「어림 9 분」 · 「어림 = 한 장에 드는 시간 × 장 수」 (다-1 · 다-2) → 「예상 시간 9분」 · 설명 줄은 뺌
12. **다-21** 「거절 — 까닭 하나 누르면 끝」 → 「거절 이유를 하나 고르세요 (누르면 바로 거절돼요)」
13. **다-3** 「지식 고침」 → 「지식 수정」
14. **다-4** 「등급 A 모두 승인」 · 「등급 B 는 핵심 값 확인 칸을…」 (다-4~7) → 「A등급 N건 모두 승인」 · 「B등급은 바뀌는 값을 확인하고 체크해야…」
15. **라-1** 꼬리표 「새로 붙음」 (화면 여러 곳) → 「새 기능」
16. **나-7** 「새 글 — AI · 직원이 이 글로 안내해요」 → 「고칠 글 — 앞으로 AI와 직원이 이 글대로 안내해요」
17. **아-1** 이름 없는 칸 「바뀐 내용을 적어 주세요」 + [분석] → 「바뀐 회사 규칙이나 안내를 한 문장으로 적어 주세요」 + [고칠 곳 찾기]
18. **다-8** 「② 새로 · 바뀌는 지식」 · 「④ 같은 값 표시」 (다-8 · 다-9) → 「② 새 지식 · 바뀐 지식」 · 「④ 같은 값 적힌 곳」
19. **자-1** 「능력 질문(시험지)」 (온톨로지 화면) → 「답해야 할 질문」 — 「온톨로지」 이름은 그대로
20. **다-14** 「① 한글 이름 붙이기 · ④ … 은 지금 없어요」 → 「지금 없는 묶음: ① … · ④ …」

## 가. 낱말 맞춤표

같은 낱말이 여러 화면에 있는 것. 「화면 줄 수」는 새 회사 지식 화면 파일(`templates/brain/ds/` · `static/js/brain/ds/`)과 화면 글을 내보내는 서버 파일에서 주석 · 설명 글을 빼고 센 대략의 줄 수다(파일 수는 괄호). 한 글자 낱말(판 · 층 · 꼴 · 폰)은 앞뒤 글자로 걸러 셌지만 다른 뜻이 섞였을 수 있다.

| 번호 | 지금 낱말 | 바꿀 낱말 | 화면 줄 수 | 이 낱말을 쓰는 줄 |
|---|---|---|---|---|
| 가-1 | 바깥 글 | 직원 안내 (직원 말) | 8 (3파일) | 나-1, 나-3, 나-4, 나-5, 나-9, 나-15, 나-16 |
| 가-2 | 엇갈림 · 어긋남 · 부딪침 · 맞서요 | 충돌 (문장 안에서는 「서로 달라요」) | 18 (10파일) | 나-1, 다-28, 바-9, 사-5, 사-6, 아-24, 차-25, 파-4, 파-8 |
| 가-3 | 판 (하루 묶음 · 지식의 차례 두 뜻) | 하루 묶음은 「날짜별 기록 · N번 묶음」, 지식의 차례는 「버전」 | 37 (14파일) | 다-39, 마-1, 마-2, 마-3, 마-5, 마-6, 마-7, 마-9, 마-10, 바-20, 바-21, 바-22, 바-23, 자-14, 타-6 |
| 가-4 | 층 | 팀 | 7 (5파일) | 마-2, 마-4, 아-28, 자-35, 파-1 |
| 가-5 | 까닭 | 이유 | 23 (12파일) | 나-21, 다-20, 다-21, 라-5, 라-6, 라-8, 바-24, 바-29, 바-34, 아-5, 타-6 |
| 가-6 | 손님 | 고객 (사장님 말) | 34 (16파일) | 나-8, 나-22, 라-10, 라-11, 라-16, 라-17, 바-8, 아-6, 아-29, 아-30, 아-31, 아-32, 자-39, 차-1, 차-27, 카-7, 카-8, 카-16, 카-20, 카-21, 카-23, 파-15, 파-16 |
| 가-7 | 은퇴 | 사용 중지 | 11 (8파일) | 다-34, 마-3, 바-26, 바-32, 아-18, 파-11, 파-12, 파-13 |
| 가-8 | 낡음 | 확인 날짜 지남 | 5 (5파일) | 바-5, 바-6 |
| 가-9 | 끝남 · 끝 | 완료 (기간은 「지남」) | 9 (7파일) | 다-21, 바-7, 사-8, 카-10, 카-15 |
| 가-10 | 그 밖 | 기타 · 외 N개 | 8 (8파일) | 마-8, 바-13, 사-1, 파-15 |
| 가-11 | 잇기 · 이을 · 이어요 · 이어진 · 이어짐 | 연결 | 26 (13파일) | 다-10, 다-12, 다-13, 다-40, 바-33, 사-9, 아-27, 아-33, 자-22, 자-24, 타-3, 타-5 |
| 가-12 | 정본 · 사본 | 원본 · 복사본 | 22 (8파일) | 바-16, 아-33, 자-6, 자-14, 자-19, 파-3, 파-5, 파-6, 파-7, 파-14 |
| 가-13 | 꼴 | 형식 | 6 (5파일) | 아-21, 아-26, 자-11, 카-11, 타-8 |
| 가-14 | 능력 질문 | 답해야 할 질문 | 10 (5파일) | 자-1, 자-2, 자-3, 자-4, 자-5 |
| 가-15 | 어림 | 예상 시간 | 2 (1파일) | 다-1, 다-2 |
| 가-16 | ERP 물건 · ERP 재료 · 물건 종류 | ERP 자료 · 자료 종류 | 12 (7파일) | 바-33, 자-3, 자-21, 자-22, 자-23, 자-34, 차-13 |
| 가-17 | 새로 붙음 · 새로 (꼬리표) | 새 기능 | 12 (11파일) | 라-1, 사-3, 카-19 |
| 가-18 | 돈 상한 · 상한 | 비용 한도 · 한도 | 15 (6파일) | 아-19, 아-20, 차-21, 차-22, 차-23, 카-5, 타-3 |
| 가-19 | 폰 | 휴대폰 | 5 (4파일) | 다-30, 다-31, 자-40 |
| 가-20 | 지식 고침 | 지식 수정 | 9 (5파일) | 나-16, 다-3 |
| 가-21 | 수정 대기 · 기다리는 수정 · 승인을 기다리는 수정 | 승인 대기 N건 | 6 (5파일) | 라-18, 바-10, 사-5, 사-6 |
| 가-22 | 관문 | 자동 검사 | 5 (3파일) | 차-19, 타-2 |
| 가-23 | 단추 (화면 글 안) | 버튼 | 3 (3파일) | 바-27 |
| 가-24 | 유효 기간 · 유효 시작 · 유효 끝 | 적용 기간 · 적용 시작일 · 적용 종료일 | 5 (3파일) | 바-2, 바-3 |
| 가-25 | 다시 볼 날 | 다음 확인일 | 4 (4파일) | 바-4 |
| 가-26 | 묶음 (문장으로 고치기 한 번) | 요청 | — (아래 줄만) | 아-2, 아-4, 아-11, 아-12, 아-14, 아-15, 아-24 |
| 가-27 | 칸 (화면 글 안 「칸이 여럿 · 한 칸 고침」) | 항목 | — (아래 줄만) | 다-31, 다-32, 다-33, 다-34, 바-1, 바-19, 자-7, 자-12, 자-15, 파-14 |
| 가-28 | 영어 뒤 띄운 조사 「AI 가 · PC 에서 · FOMS 의」 | 붙여 씀 「AI가 · PC에서 · FOMS의」 | 39 (17파일) | 다-20, 다-25, 다-33, 다-34, 라-3, 바-8, 자-20, 카-22, 타-10 |
| 가-29 | 등급 A · 등급 B | A등급 · B등급 | 9 (4파일) | 다-4, 다-5, 다-6, 다-7 |
| 가-30 | 에이전트 | AI 직원 | 3 (2파일) | 자-25, 자-26, 파-2 |

## 나. ③ 사장님이 정할 것 카드 (질문 카드)

카드 하나에 「어느 쪽이 맞아요?」 · 직원 쪽 글 · 회사 지식 쪽 글 · 답 단추 셋이 나온다. 카드를 만드는 글은 상담 배우기(`foms/services/cs_agent/handoff_learning_*.py`)와 사진 다시 배우기(`foms/services/brain/photo_cards.py`)가 저장한다.

| 번호 | 지금 글 | 바꿀 글 | 왜 | 자리(`파일:줄`) | 고치는 법 · 같이 고칠 시험 |
|---|---|---|---|---|---|
| 나-1 | 어긋남 — 회사 지식 「…」 ↔ 직원 「…」 (직원 쪽 글 칸 첫 줄) | 다른 부분: 회사 지식은 「…」, 직원은 「…」 | 기계 표시 줄이 사람 글처럼 보임 · 제목과 같은 말을 또 함 | `foms/services/cs_agent/handoff_learning_gates.py:101`<br>`foms/services/cs_agent/handoff_learning_route.py:130`<br>`static/js/brain/ds/ds-inbox-question.js:91` | 저장 글은 그대로, 보일 때만 바꿈 — 학습 코드가 「어긋남 — 」 머리로 카드를 알아본다(`handoff_learning_gates.py:107,335` · `handoff_learning_resort.py:161`). 화면(`ds-inbox-question.js:91` 직원 쪽 글을 그리기 전)에서 첫 줄만 바꿔 보인다. — 시험: `domains/test_brain_ds_item.py`, `domains/test_brain_fix_menu_query_count.py`, `domains/test_brain_polish_f_prerender_key.py` 외 8개 |
| 나-2 | 승인된 규칙과 다름 (직원 쪽 글 칸 둘째 줄 · 이유 줄 끝) | 화면에서 뺌 (제목과 아래 회사 지식 칸이 이미 같은 말을 함) | 같은 말 두 번 · 기계 표시 줄 | `foms/services/brain/photo_cards.py:60` | 저장 글은 그대로, 보일 때만 바꿈 — 학습 코드가 이 글로 충돌 카드를 알아본다(`handoff_learning_gates.py:153,178` · `handoff_learning_place.py:157`). 보일 때만 이 줄을 지운다. — 시험: `domains/test_brain_ds_inbox_js.py`, `domains/test_brain_photo_cards.py`, `domains/test_cs_handoff_learning.py` 외 2개 |
| 나-3 | 바깥 글 (직원 쪽 글 칸 이름) | 직원 안내 (직원 말) | 「바깥」이 어디인지 모름 · 실제로는 상담 직원이 한 말 | `static/js/brain/ds/ds-inbox-question.js:91` | 가-1 낱말. 글만 바꿈. |
| 나-4 | 회사 지식이 맞아요 (바깥 글은 고칠 일로) | 회사 지식이 맞아요 (지식 그대로) | 일어나지 않는 일을 말함 — 누르면 질문만 닫힌다 | `static/js/brain/ds/ds-inbox-question.js:94` | 글만 바꿈. 「고칠 일」을 만드는 코드는 없다(`knowledge_right` 를 받는 곳은 판정자에게 보이는 말 `handoff_learning_place.py:75` 하나뿐). |
| 나-5 | 바깥 글이 맞아요 (지식 고치기) · 저장 답 이름 「바깥 글이 맞아요」 | 직원 안내가 맞아요 (지식 고치기) | 가-1 낱말과 같음 | `static/js/brain/ds/ds-inbox-question.js:22,96` | 단추 글과 `SAID` 표(`:22`)를 같이 바꿈. `SAID` 는 이유 글 「사장님 답 — …」(`:133`)으로 저장되지만 다시 읽는 코드가 없다 — 새 답부터 바뀜. — 시험: `domains/test_brain_ds_inbox_change_js.py`, `domains/test_brain_ds_inbox_js.py`, `domains/test_brain_inbox_bins.py` 외 1개 |
| 나-6 | 둘 다 맞아요 (경우 적기) | 둘 다 맞아요 (경우 나눠 적기) | 무엇을 적는지 모호함 | `static/js/brain/ds/ds-inbox-question.js:97` | 글만 바꿈. |
| 나-7 | 새 글 — AI · 직원이 이 글로 안내해요 | 고칠 글 — 앞으로 AI와 직원이 이 글대로 안내해요 | 무엇의 「새 글」인지 모호함 · 가운뎃점은 소리 내어 읽기 어려움 | `static/js/brain/ds/ds-inbox-question.js:68` | 글만 바꿈. |
| 나-8 | 손님에게 안내할 문장으로 적어요 — 지식 글 끝에 붙어요 | 어떤 경우에 고객에게 어떻게 안내하는지 한 줄로 적어 주세요 — 지식 글 끝에 붙어요 | 사장님 말과 다름(손님 → 고객) · 무엇을 적을지 모호함 | `static/js/brain/ds/ds-inbox-question.js:68` | 시험: `domains/test_brain_ds_inbox_change_js.py` |
| 나-9 | 지금 글 뒤에 바깥 글을 붙였어요 — 틀린 옛 문장은 지워 주세요. | 지금 지식 글 뒤에 직원 안내를 붙였어요 — 틀린 옛 문장은 지워 주세요. | 가-1 낱말 · 「지금 글」이 무엇인지 모호함 | `static/js/brain/ds/ds-inbox-question.js:69` | 글만 바꿈. |
| 나-10 | 바뀌는 곳 — 빨간 줄 그은 글은 빠지고, 초록 밑줄 글이 들어가요 | 달라지는 부분 — 빨간 줄 친 글은 빠지고, 초록 밑줄 친 글이 새로 들어가요 | 「곳」이 자리처럼 읽힘 | `static/js/brain/ds/ds-inbox-question.js:54` | 시험: `domains/test_brain_ds_inbox_change_js.py` |
| 나-11 | 다루는 지식을 못 찾아 「회사 지식이 맞아요」만 고를 수 있어요. | 관련 지식을 찾지 못해 「회사 지식이 맞아요」만 고를 수 있어요. | 「다루는」이 어색함 | `static/js/brain/ds/ds-inbox-question.js:105` | 글만 바꿈. |
| 나-12 | 하지 못했어요 — 다시 눌러 주세요. | 처리하지 못했어요 — 다시 눌러 주세요. | 무엇을 못 했는지 빠짐 | `static/js/brain/ds/ds-inbox-question.js:125` | 글만 바꿈. |
| 나-13 | 이 글로 바꾸기 | 이 글로 고치기 | 같은 카드의 「지식 고치기」와 낱말이 다름(작다) | `static/js/brain/ds/ds-inbox-question.js:72` | 글만 바꿈. |
| 나-14 | ③ 사장님이 정해 주실 것 (본문 제목) / ③ 사장님이 정할 것 (왼쪽 메뉴) | ③ 사장님이 정할 것 (하나로) | 같은 것을 두 이름으로 부름 | `static/js/brain/ds/ds-inbox-view.js:19`<br>`templates/brain/ds/partials/inbox_side.html:4` | 본문 제목 `title` 만 바꿈. 짧은 이름은 `inbox_side.html` 과 시험이 견준다(`inbox_side.html:3` 주석). — 시험: `domains/test_brain_ds_inbox_change_js.py`, `domains/test_brain_ds_inbox_js.py` |
| 나-15 | 거절 이유 이름표 「회사 지식이 맞음 — 바깥 글 고칠 일」 | 회사 지식이 맞음 | 일어나지 않는 일을 말함(나-4 와 같음) | `foms/services/brain/display.py:123` | 이름표만 바꿈. 거절 코드 `knowledge_right` 는 그대로. |
| 나-16 | 거절 이유 이름표 「바깥 글이 맞음 — 회사 지식 고침」 | 직원 안내가 맞음 — 지식 고침 | 가-1 낱말 | `foms/services/brain/display.py:124` | 이름표만 바꿈. 코드 `outside_right` 는 그대로. |
| 나-17 | 거절 이유 이름표 「둘 다 맞음 — 경우를 적음」 | 둘 다 맞음 — 경우 나눠 적음 | 나-6 과 같은 말로 | `foms/services/brain/display.py:125` | 이름표만 바꿈. 코드 `both_right` 는 그대로. |
| 나-18 | 만든 사람 이름표 「AI(넘긴 상담 배우기)」 | AI(직원 답에서 배움) | 「넘긴 상담 배우기」는 기능 이름이라 무슨 뜻인지 모름 | `foms/services/brain/display.py:109` | 이름표만 바꿈. 코드 `cs_handoff_learning` 는 그대로. — 시험: `domains/test_cs_handoff_learning.py` |
| 나-19 | 만든 사람 이름표 「AI(사진 다시 배우기)」 | AI(사진 보고 배움) | 「다시 배우기」가 무엇을 다시 하는지 모호함 | `foms/services/brain/display.py:108` | 시험: `domains/test_brain_fix_names_js.py`, `domains/test_brain_fix_names_labels.py` |
| 나-20 | 만든 사람 이름표 「AI(물어보기 틀림 신고)」 | AI(물어보기 틀린 답 신고) | 「틀림 신고」가 어색함 | `foms/services/brain/display.py:108` | 글만 바꿈. |
| 나-21 | 이유 줄 「넘긴 상담 배우기 · 근거 상담 N곳 · 넘긴 까닭 …」 | 직원에게 넘긴 상담에서 배움 · 근거 상담 N건 · 넘긴 이유 … | 기능 이름 · 「곳」은 상담 수 단위가 아님 · 까닭 → 이유 | `foms/services/cs_agent/handoff_learning_route.py:102`<br>`foms/services/cs_agent/handoff_learning_onto.py:68`<br>`foms/services/cs_agent/handoff_learning_route.py:102` | 이유 글은 저장된다 — 새 카드부터 바뀜. `handoff_learning_route.py:122` 가 「넘긴 상담 배우기 · 」 머리를 글자로 찾아 바꾸므로 그 줄도 같이 바꿔야 한다. — 시험: `domains/test_brain_learned.py`, `domains/test_cs_handoff_learning.py` |
| 나-22 | 이유 줄 「… 서로 다른 손님 N곳 …」 | … 서로 다른 고객 N명 … | 사장님 말과 다름(손님 → 고객) · 사람 수 단위 | `foms/services/cs_agent/handoff_learning_route.py:304` | 이유 글은 저장된다 — 새 카드부터 바뀜. — 시험: `domains/test_cs_handoff_learning.py`, `domains/test_cs_learn_everything.py`, `domains/test_cs_learn_place.py` 외 2개 |
| 나-23 | 이유 줄 「사진 + 상담 전체 대화 다시 학습 · 근거 상담 약 N곳」 | 사진과 상담 대화를 다시 보고 배움 · 근거 상담 약 N건 | 「+」 기호 · 「곳」 단위 | `foms/services/brain/photo_cards.py:136` | 이유 글은 저장된다 — 새 카드부터 바뀜. — 시험: `domains/test_brain_photo_cards.py` |
| 나-24 | 이유 줄 「사장님이 고름(자동 판정 넘김)」 | 사장님이 고름(자동 검사 건너뜀) | 「판정 넘김」이 「넘긴 상담」과 헷갈림 | `foms/services/brain/photo_cards.py:63` | 이유 글은 저장된다 — 새 카드부터 바뀜. |

## 다. 승인 대기 화면 (숫자 띠 · 왼쪽 메뉴 · 묶음 · 지식 카드 제안 · 휴대폰)

| 번호 | 지금 글 | 바꿀 글 | 왜 | 자리(`파일:줄`) | 고치는 법 · 같이 고칠 시험 |
|---|---|---|---|---|---|
| 다-1 | 어림 (숫자 띠 이름) | 예상 시간 | 「어림」은 이름표로 쓰지 않는 말 | `templates/brain/ds/partials/inbox_main.html:16` | 가-15 낱말. — 시험: `domains/test_brain_ds_inbox.py` |
| 다-2 | 어림 = 한 장에 드는 시간 × 장 수 | (이 줄은 뺌) 또는 「건당 걸리는 시간 × 건수」 | 「장」은 옆의 「개」와 단위가 다름 · 설명이 필요 없는 줄 | `templates/brain/ds/partials/inbox_main.html:21` | 시험: `domains/test_brain_ds_inbox.py` |
| 다-3 | 지식 고침 (숫자 띠 · 칸 제목 · 왼쪽 메뉴) | 지식 수정 | 「고침」을 이름표로 쓰면 어색함 · 같은 화면에 「수정 기록」이 있음 | `templates/brain/ds/partials/inbox_main.html:19,27,31`<br>`templates/brain/ds/partials/inbox_side.html:11`<br>`static/js/brain/ds/ds-inbox.js:151,189` | 가-20 낱말. — 시험: `domains/test_brain_ds_inbox.py`, `domains/test_brain_ds_inbox_erp.py`, `domains/test_brain_ds_inbox_js.py` |
| 다-4 | 등급 A 모두 승인 · 등급 A N개 모두 승인 | A등급 N건 모두 승인 | 가-29 낱말(우리말 순서는 「A등급」) · 승인 대기 단위는 「건」 | `templates/brain/ds/partials/inbox_main.html:34`<br>`static/js/brain/ds/ds-inbox.js:197` | 시험: `domains/test_brain_polish_e_ui.py` |
| 다-5 | 등급 A 제안 N개를 한꺼번에 승인할까요? | A등급 제안 N건을 한꺼번에 승인할까요? | 다-4 와 같은 말로 | `static/js/brain/ds/ds-inbox-act.js:149` | 글만 바꿈. |
| 다-6 | 등급 B 제안이에요 — 핵심 값을 보고 확인 칸을 눌러 주세요. | B등급 제안이에요 — 바뀌는 값을 확인하고 체크해 주세요. | 「핵심 값 확인 칸」이 낯섦 · 사장님 말은 「체크」 | `static/js/brain/ds/ds-inbox-act.js:69` | 시험: `domains/test_brain_ds_inbox_js.py` |
| 다-7 | 등급 B 는 핵심 값 확인 칸을 눌러야 승인돼요. | B등급은 바뀌는 값을 확인하고 체크해야 승인돼요. | 다-6 과 같은 말로 | `foms/services/brain/actions.py:64` | 시험: `domains/test_brain_polish_f_text.py` |
| 다-8 | ② 새로 · 바뀌는 지식 | ② 새 지식 · 바뀐 지식 | 「새로 · 바뀌는」은 문법이 깨짐 | `templates/brain/ds/partials/inbox_side.html:4`<br>`static/js/brain/ds/ds-inbox-view.js:17` | 짧은 이름은 두 곳이 같아야 한다(시험이 견줌). |
| 다-9 | ④ 같은 값 표시 | ④ 같은 값 적힌 곳 | 무엇을 표시하는지 안 보임 | `templates/brain/ds/partials/inbox_side.html:5`<br>`static/js/brain/ds/ds-inbox-view.js:21` | 짧은 이름은 두 곳이 같아야 한다. |
| 다-10 | ⑥ 규칙 잇기 | ⑥ 규칙 연결 | 가-11 낱말(잇기 → 연결) | `templates/brain/ds/partials/inbox_side.html:5`<br>`static/js/brain/ds/ds-inbox-view.js:25`<br>`static/js/brain/ds/ds-inbox-table.js:115` | 짧은 이름 · 제목 · 표 이름 같이. |
| 다-11 | ⑤ 설명 「금액은 계산기를 가리키기만 해요.」 | 금액은 계산기 값을 그대로 따라요. | 「가리키기만」이 무슨 뜻인지 모름 | `static/js/brain/ds/ds-inbox-view.js:24`<br>`foms/services/brain/display.py:141` | 글만 바꿈. |
| 다-12 | ⑥ 설명 「정책 · 가격 규칙이 어느 제품 · 옵션, 어느 공정 단계에 걸리는지 이어요. 글 · 금액은 그대로예요.」 | 정책과 가격 규칙이 어느 제품 · 옵션, 어느 공정 단계에 적용되는지 연결해요. 글과 금액은 그대로예요. | 「걸리는지 이어요」가 어색함 · 문장 안 가운뎃점 | `static/js/brain/ds/ds-inbox-view.js:26` | 글만 바꿈. |
| 다-13 | ⑥ 카드 줄 「규칙과 제품 · 옵션을 잇기만 해요. 글 · 금액은 그대로예요.」 | 규칙과 제품 · 옵션을 연결만 해요. 글과 금액은 그대로예요. | 가-11 낱말 | `foms/services/brain/display.py:142` | 글만 바꿈. |
| 다-14 | 「① 한글 이름 붙이기 · ④ … 은 지금 없어요」 | 「지금 없는 묶음: ① … · ④ …」 | 받침과 「은」이 안 맞음(「규칙 잇기 은」) | `static/js/brain/ds/ds-inbox-view.js:111` | 시험: `domains/test_brain_ds_inbox_js.py` |
| 다-15 | … (새로) (카드 제목 끝) | … (새 지식) | 무엇이 새로인지 빠짐 | `static/js/brain/ds/ds-inbox-view.js:94` | 글만 바꿈. |
| 다-16 | 승인 N개 · 못 함 N개(카드로 하나씩 봐 주세요) | 승인 N건 · 못 한 것 N건(하나씩 열어 봐 주세요) | 「못 함」 명사형 끝 · 단위 | `static/js/brain/ds/ds-inbox-view.js:181` | 글만 바꿈. |
| 다-17 | 묶음마다 한 줄 · 열면 그 묶음 카드만 보여요 | 종류별로 묶었어요. 열면 그 종류만 보여요 | 설계 말투 | `templates/brain/ds/partials/inbox_main.html:33` | 시험: `domains/test_brain_ds_inbox.py` |
| 다-18 | 승인하면 바로 반영 · 전 내용은 기록에 남아요 (휴대폰 칸) | 승인하면 바로 바뀌고, 바뀌기 전 내용은 수정 기록에 남아요. | 같은 화면 위 머리말(`inbox_main.html:7`)과 같은 뜻을 다른 꼴로 말함 | `templates/brain/ds/partials/inbox_main.html:52` | 글만 바꿈. |
| 다-19 | 승인하면 바로 반영되고, 바뀌기 전 내용은 수정 기록에 남아요. 승인 전에는 아무것도 바뀌지 않아요. | 승인하면 바로 바뀌고, 바뀌기 전 내용은 수정 기록에 남아요. 승인하기 전에는 아무것도 바뀌지 않아요. | 다-18 과 같은 문장으로 맞춤(작다) | `foms/services/brain/display.py:152` | 글만 바꿈. |
| 다-20 | 거절 까닭은 AI 가 배워요. | 거절 이유는 AI가 배워요. | 가-5 낱말 · 띄어쓰기 | `templates/brain/ds/partials/inbox_main.html:63` | 글만 바꿈. |
| 다-21 | 거절 — 까닭 하나 누르면 끝 | 거절 이유를 하나 고르세요 (누르면 바로 거절돼요) | 「끝」은 사장님이 거절한 말 · 「까닭」 | `static/js/brain/ds/ds-inbox-card.js:57`<br>`static/js/brain/ds/ds-inbox-erp-aside.js:201`<br>`static/js/brain/ds/ds-inbox-card.js:58`<br>`static/js/brain/ds/ds-inbox-erp-card.js:78` | 글만 바꿈. |
| 다-22 | (금액은 가격 재량이 있는 사람만 보여요) | (금액은 가격 권한이 있는 사람만 볼 수 있어요) | 「재량」이 어려움 | `static/js/brain/ds/ds-inbox-card.js:92` | 글만 바꿈. |
| 다-23 | AI · 직원이 알게 될 내용 | AI와 직원이 안내할 내용 | 나-7 과 같은 말로 · 가운뎃점 | `static/js/brain/ds/ds-inbox-card.js:100` | 글만 바꿈. |
| 다-24 | 같은 지식에 붙은 제안 N개 | 같은 지식에 대한 다른 제안 N건 | 「붙은」이 모호함 · 단위 | `static/js/brain/ds/ds-inbox-card.js:145` | 글만 바꿈. |
| 다-25 | AI 가 낸 이유 · / 이유 ·  | AI가 낸 이유: / 이유:  | 가운뎃점을 쌍점처럼 씀 · 띄어쓰기 | `static/js/brain/ds/ds-inbox-kit.js:119` | 글만 바꿈. |
| 다-26 | 자동 검사 꼬리표 「한자 0 안 됨」 | 한자 들어 있음 | 「0 안 됨」이 무슨 뜻인지 모름 | `foms/services/brain/display.py:118`<br>`foms/services/brain/display.py:120` | 꼬리표 = 검사 이름 + 결과(`ds-inbox-kit.js:164`). 검사 이름표(`GATE_LABELS`)와 결과 「안 됨」(`GATE_VALUE_LABELS`)을 같이 손봐야 한다 — 걸린 것만 보이므로 「검사 이름 + 들어 있음/틀림」 꼴이 맞음. 키는 그대로. — 시험: `domains/test_brain_review_js.py` |
| 다-27 | 자동 검사 꼬리표 「가림(개인정보 0) 안 됨」 | 개인정보 들어 있음 | 「0 안 됨」이 무슨 뜻인지 모름 | `foms/services/brain/display.py:118` | 글만 바꿈. |
| 다-28 | 자동 검사 꼬리표 「승인 지식과 부딪침 안 됨」 | 기존 지식과 충돌 | 「부딪침 안 됨」은 「안 부딪친다」로 거꾸로 읽힘 | `foms/services/brain/display.py:119` | 시험: `domains/test_brain_review_js.py`, `domains/test_cs_learn_everything.py` |
| 다-29 | 자동 검사 꼬리표 「꼴 안 됨」 · 「숫자 출처 안 됨」 | 형식이 틀림 · 숫자 근거가 없음 | 「꼴」은 지은 말 느낌 · 결과가 거꾸로 읽힘 | `foms/services/brain/display.py:118`<br>`foms/services/brain/display.py:118` | 시험: `domains/test_brain_d129.py`, `domains/test_brain_review_js.py` |
| 다-30 | 폰에서 승인 | 휴대폰에서 승인 | 가-19 낱말 | `templates/brain/ds/partials/inbox_main.html:49,51` | 시험: `domains/test_brain_ds_inbox_erp_fix.py`, `domains/test_brain_ds_inbox_js.py` |
| 다-31 | 폰에서는 한 칸 고침 · ERP 할 일만 승인해요 | 휴대폰에서는 한 항목 수정 · AI 할 일 제안만 승인할 수 있어요 | 「한 칸 고침」 · 「ERP 할 일」이 다른 곳 이름과 다름 | `templates/brain/ds/inbox.html:21`<br>`templates/brain/ds/inbox.html:20`<br>`templates/brain/ds/inbox.html:20` | `inbox.html:20` 목록 이름과 `:21` 문장을 같이 바꿈. |
| 다-32 | 한 칸 고침 (휴대폰 카드 꼬리표) | 한 항목 수정 | 다-31 과 같은 말로 | `static/js/brain/ds/ds-inbox-phone.js:90` | 글만 바꿈. |
| 다-33 | 휴대폰에서는 칸 하나만 바뀌는 제안만 승인할 수 있어요. 나머지는 PC 에서 해 주세요. | 휴대폰에서는 한 항목만 바뀌는 제안만 승인할 수 있어요. 나머지는 PC에서 해 주세요. | 「칸」 · 띄어쓰기 | `templates/brain/ds/partials/inbox_side.html:24` | 글만 바꿈. |
| 다-34 | 이 제안은 PC 에서 결정해요(칸이 여럿이거나 새 지식 · 은퇴 · 지우기 · 연결). | 이 제안은 PC에서 결정해 주세요(여러 항목이 바뀌거나 새 지식 · 사용 중지 · 삭제 · 연결이에요). | 「은퇴」 · 「칸이 여럿」 | `static/js/brain/ds/ds-inbox-phone.js:25`<br>`static/js/brain/ds/ds-inbox-phone.js:181` | 시험: `domains/test_brain_polish_e_ui.py` |
| 다-35 | AI 제안 이번 주 자리 N/M 남음 · 자리를 기다리는 AI 제안 N건 · AI 제안은 4주가 지나면 저절로 닫혀요 | 이번 주 AI 제안 남은 자리 N/M · 순서를 기다리는 AI 제안 N건 · AI 제안은 4주가 지나면 자동으로 닫혀요 | 「자리 … 남음」 어순이 어색함 | `static/js/brain/brain-review-view.js:175`<br>`static/js/brain/brain-review-view.js:176` | 글만 바꿈. |
| 다-36 | 비슷한 사례 없음(이 항목을 받치는 관찰이 아직 없어요) | 비슷한 사례 없음(뒷받침할 사례가 아직 없어요) | 「받치는 관찰」이 설계 말 | `static/js/brain/brain-review-view.js:148` | 글만 바꿈. |
| 다-37 | 사본 N곳(매크로 · 스토어 상세 같은 곳 — 함께 고칠 일) | 복사본 N곳(매크로 · 스토어 상세 등 — 같이 고쳐야 해요) | 「함께 고칠 일」 명사형 · 「사본」 | `static/js/brain/brain-review-view.js:162` | 글만 바꿈. |
| 다-38 | 함께 닿는 지식 없음 | 같이 영향받는 지식 없음 | 「닿는」이 모호함 | `static/js/brain/brain-review-view.js:163` | 시험: `domains/test_brain_rest_g_names.py` |
| 다-39 | 제안을 만든 뒤 이 지식이 바뀌었어요(기준 판 N → 지금 판 M). | 제안을 만든 뒤 이 지식이 바뀌었어요(제안 때 버전 N → 지금 버전 M). | 가-3 낱말(지식 차례는 「버전」) | `static/js/brain/brain-review-view.js:135`<br>`static/js/brain/brain-review-view.js:136` | 글만 바꿈. |
| 다-40 | 계산기 값 잇기 | 계산기 값 연결 | 가-11 낱말 | `static/js/brain/ds/ds-inbox-table.js:93` | 글만 바꿈. |
| 다-41 | 걸리는 제품 · 옵션 · 공정 단계 / 규칙마다 걸리는 제품 · 옵션이 맞는지 | 적용되는 제품 · 옵션 · 공정 단계 / 규칙마다 적용되는 제품 · 옵션이 맞는지 | 「걸리는」이 「검사에 걸림」과 헷갈림 | `static/js/brain/ds/ds-inbox-table.js:115`<br>`static/js/brain/ds/ds-inbox-table.js:116` | 글만 바꿈. |
| 다-42 | 목록을 훑어보고 맞으면 모두 고르기 → 체크한 줄 승인. | 목록을 훑어보고 맞으면 [모두 고르기]를 누른 뒤 [체크한 줄 승인]을 눌러 주세요. | 화살표로 줄인 말 | `static/js/brain/ds/ds-inbox-table.js:114` | 글만 바꿈. |

## 라. AI 할 일 제안 · AI가 배운 것 · 다시 확인

| 번호 | 지금 글 | 바꿀 글 | 왜 | 자리(`파일:줄`) | 고치는 법 · 같이 고칠 시험 |
|---|---|---|---|---|---|
| 라-1 | 새로 붙음 (꼬리표) | 새 기능 | 무엇이 어디에 붙었는지 모름 | `templates/brain/ds/partials/inbox_erp_nav.html:8`<br>`templates/brain/ds/partials/inbox_erp_section.html:16`<br>`static/js/brain/ds/ds-inbox-erp-aside.js:52`<br>`templates/brain/ds/ask.html:43`<br>`templates/brain/ds/partials/item_glance.html:48`<br>`static/js/brain/ds/ds-ask-turn.js:179`<br>`static/js/brain/ds/ds-onto-detail.js:21`<br>`static/js/brain/ds/ds-search-preview.js:75` | 가-17 낱말 — 아래 곳 말고도 바·사·자·차·카 절 화면에 같은 꼬리표가 있다(가-17 곳 수). — 시험: `domains/test_ai_staff_screen_fix2.py`, `domains/test_brain_ds_ask.py`, `domains/test_brain_ds_inbox_erp.py` |
| 라-2 | AI 직원이 FOMS 할 일을 제안해요 · 승인 전에는 아무것도 안 바뀌어요 | AI 직원이 FOMS에서 할 일을 제안해요. 승인하기 전에는 아무것도 바뀌지 않아요 | 가운뎃점으로 두 문장을 이음 · 띄어쓰기 | `templates/brain/ds/partials/inbox_erp_section.html:17` | 시험: `domains/test_brain_ds_inbox_erp.py` |
| 라-3 | 승인하면 지금 FOMS 의 그 기능이 그대로 돌아요 · 할 일 기록에 남아요 | 승인하면 FOMS에서 직접 처리한 것과 똑같이 처리되고, 기록에 남아요 | 「기능이 돌아요」는 기계 말 | `static/js/brain/ds/ds-inbox-erp-aside.js:75` | 글만 바꿈. |
| 라-4 | ERP 할 일 · (옆 창 꼬리표) / ERP 할 일 (휴대폰 카드 꼬리표) | AI 할 일 제안 · / AI 할 일 제안 | 같은 것을 두 이름으로 부름(메뉴는 「AI 할 일 제안」) | `static/js/brain/ds/ds-inbox-erp-aside.js:48`<br>`static/js/brain/ds/ds-inbox-erp-card.js:140` | 글만 바꿈. |
| 라-5 | 바꾸는 까닭(변경 기록에 남아요) | 바꾸는 이유(바뀐 기록에 남아요) | 가-5 낱말 · 「바뀐 기록」이 사장님 말 | `static/js/brain/ds/ds-inbox-erp-aside.js:159` | 글만 바꿈. |
| 라-6 | 까닭을 골라 주세요 / 까닭 메모 / 바꾸는 까닭 | 이유를 골라 주세요 / 이유 메모 / 바꾸는 이유 | 가-5 낱말 | `static/js/brain/ds/ds-inbox-erp-aside.js:156`<br>`static/js/brain/ds/ds-inbox-erp-aside.js:158`<br>`static/js/brain/ds/ds-inbox-erp-aside.js:251`<br>`static/js/brain/ds/ds-inbox-erp-aside.js:155` | 글만 바꿈. |
| 라-7 | 고를 사람이 없어요. | 고를 수 있는 담당자가 없어요. | 사장님 말 「담당」 | `static/js/brain/ds/ds-inbox-erp-aside.js:117` | 글만 바꿈. |
| 라-8 | 거절 까닭은 X 가 다음 제안에 배워요. 같은 제안이 다시 오지 않아요. | 거절 이유는 X가 다음 제안 때 참고해요. 같은 제안은 다시 오지 않아요. | 가-5 낱말 · 띄어쓰기 | `static/js/brain/ds/ds-inbox-erp-aside.js:203` | 글만 바꿈. |
| 라-9 | 넣어야 승인할 수 있어요: … | 이 칸을 채워야 승인할 수 있어요: … | 무엇을 넣는지 빠짐 | `static/js/brain/ds/ds-inbox-erp-aside.js:256` | 시험: `domains/test_brain_ds_inbox_erp.py` |
| 라-10 | 손님에게 알림톡이 나가요 — 확인한 뒤 승인해 주세요. | 고객에게 알림톡이 나가요 — 확인한 뒤 승인해 주세요. | 손님 → 고객 | `static/js/brain/ds/ds-inbox-erp.js:27` | 시험: `domains/test_brain_ds_inbox_erp.py` |
| 라-11 | 손님 알림톡 (바뀌는 칸 이름 · 「승인하면 차례로」 줄 머리) | 고객 알림톡 | 손님 → 고객 | `static/js/brain/ds/ds-inbox-erp-aside.js:18`<br>`foms/services/erp_actions/views.py:63`<br>`foms/services/erp_actions/construction_notice.py:29`<br>`foms/services/erp_actions/registry.py:140`<br>`foms/services/erp_actions/measure_notice.py:27`<br>`foms/services/erp_actions/construction_notice.py:30`<br>`foms/services/erp_actions/measure_notice.py:28`<br>`foms/services/erp_actions/preview.py:387` | 저장 글은 그대로, 보일 때만 바꿈 — 저장된 제안 미리 보기(`row.preview`)의 칸 이름에 이 글이 들어 있고, `erp_actions/views.py:287` · `foms/web/orders/dashboard.py:672` · `ds-inbox-erp-aside.js:268` 이 이 머리 글자로 알림톡 줄을 알아본다. 머리 비교를 두 글 다 받게 고친 뒤 새 글로 바꾼다. — 시험: `domains/test_brain_ds_inbox_erp.py`, `domains/test_construction_alimtalk.py`, `domains/test_erp_actions_core_runners.py` 외 2개 |
| 라-12 | 봤어요 (꼬리표) | 확인함 | 같은 화면 단추 「맞아요」와 헷갈림 | `static/js/brain/ds/ds-inbox-learned.js:38` | 글만 바꿈. |
| 라-13 | 고치기 앞 글: … | 고치기 전 글: … | 「앞 글」은 위치로 읽힘 | `static/js/brain/ds/ds-inbox-learned.js:41` | 글만 바꿈. |
| 라-14 | 고쳐 넣기 / 그만 | 고쳐서 저장 / 취소 | 「그만」은 단추 이름으로 어색함 | `static/js/brain/ds/ds-inbox-learned.js:86`<br>`static/js/brain/ds/ds-inbox-learned.js:86` | 글만 바꿈. |
| 라-15 | 아직 안 본 것 N개 · 본 것 N개 | 확인 전 N건 · 확인함 N건 | 라-12 와 같은 말로 | `foms/services/brain/learned.py:128` | 글만 바꿈. |
| 라-16 | 손님이 쓰는 다른 이름: … | 고객이 쓰는 다른 이름: … | 손님 → 고객 | `foms/services/brain/learned.py:92` | 시험: `domains/test_brain_learned.py` |
| 라-17 | 손님이 부르는 다른 이름을 붙여요 (옮기기 제안 이유) | 고객이 부르는 다른 이름을 붙여요 | 손님 → 고객 | `foms/services/brain/plan_labels.py:90` | 이유 글은 저장된다 — 새로 옮기는 제안부터 바뀜. |
| 라-18 | 기다리는 수정 먼저 보기 | 승인 대기 먼저 보기 | 가-21 낱말 | `static/js/brain/ds/ds-inbox-recheck.js:37` | 글만 바꿈. |
| 라-19 | 틀림 — 고치기 | 틀렸어요 — 고치기 | 「틀림」 명사형 끝 | `static/js/brain/ds/ds-inbox-recheck.js:43` | 시험: `domains/test_brain_ds_item.py` |
| 라-20 | 아직 맞음 (다시 확인 단추) | 지금도 맞아요 | 명사형 끝 | `foms/services/brain/actions.py:135` | 시험: `domains/test_brain_review.py`, `domains/test_brain_review_js.py`, `postgres/test_brain_review_pg.py` |

## 마. 날짜별 기록 (지금 이름 「판 · 기록」)

「판」이 하루 묶음과 지식 한 개의 차례 두 뜻으로 쓰인다. 하루 묶음은 「날짜별 기록」 · 「N번 묶음」, 지식의 차례는 「버전」으로 나눈다(가-3).

| 번호 | 지금 글 | 바꿀 글 | 왜 | 자리(`파일:줄`) | 고치는 법 · 같이 고칠 시험 |
|---|---|---|---|---|---|
| 마-1 | 판 · 기록 (메뉴 · 제목 · 나 메뉴) | 날짜별 기록 | 설계 말 · 「판」이 두 뜻 | `templates/brain/ds/inbox.html:11`<br>`templates/brain/ds/layout.html:93`<br>`templates/brain/ds/partials/inbox_side.html:18`<br>`templates/brain/ds/partials/inbox_releases.html:4` | 시험: `domains/test_brain_ds_inbox.py`, `domains/test_brain_ds_inbox_erp_fix.py` |
| 마-2 | 판은 하루에 하나씩 생겨요. 층 되돌리기는 사장님만 하고, 되돌려도 기록은 남아요. | 바뀐 내용은 하루 단위로 묶여요. 하루치를 팀별로 통째 되돌리는 것은 사장님만 할 수 있고, 되돌려도 기록은 남아요. | 판 · 층은 설계 말 | `templates/brain/ds/partials/inbox_releases.html:5` | 글만 바꿈. |
| 마-3 | 이 판에서 새로 만든 지식은 지워지고, 고친 · 은퇴한 · 지운 지식과 연결은 이 판 전으로 돌아가요. 기록은 남아요. | 이날 새로 만든 지식은 지워지고, 고치거나 사용 중지하거나 지운 지식과 연결은 이날 전으로 돌아가요. 기록은 남아요. | 판 · 은퇴 · 가운뎃점 | `static/js/brain/ds/ds-inbox-releases.js:26` | 글만 바꿈. |
| 마-4 | 층 없음 / 이 층 되돌리기 | 팀 없음 / 이 팀 되돌리기 | 가-4 낱말(층 → 팀) | `static/js/brain/ds/ds-inbox-releases.js:29`<br>`static/js/brain/ds/ds-inbox-releases.js:76` | 글만 바꿈. |
| 마-5 | 판 N · 날짜 · 문서에서 옮겨 옴 | N번 묶음 · 날짜 · 지식 문서에서 옮겨 옴 | 판 · 무슨 문서인지 빠짐 | `static/js/brain/ds/ds-inbox-releases.js:33`<br>`static/js/brain/ds/ds-inbox-releases.js:34` | 글만 바꿈. |
| 마-6 | 판 N X 되돌리기 (확인 단추) | N번 묶음 X팀 되돌리기 | 판 | `static/js/brain/ds/ds-inbox-releases.js:81` | 글만 바꿈. |
| 마-7 | 아직 판이 없어요. / 판 N개 | 아직 기록이 없어요. / 기록 N건 | 판 | `static/js/brain/ds/ds-inbox-releases.js:145`<br>`static/js/brain/ds/ds-inbox-releases.js:145` | 시험: `domains/test_brain_d129.py`, `domains/test_brain_ontology_cq_props.py`, `domains/test_brain_polish_e_ui.py` 외 1개 |
| 마-8 | 그 밖 N건 | 외 N건 | 가-10 낱말 | `static/js/brain/ds/ds-inbox-releases.js:54` | 글만 바꿈. |
| 마-9 | 판 되돌리기 (동작 이름) / 판을 되돌렸어요 — 되돌린 판도 이력에 남아요. | 하루치 되돌리기 / 되돌렸어요 — 되돌린 것도 기록에 남아요. | 판 · 「이력」과 「기록」 두 말 | `foms/services/brain/actions.py:140`<br>`foms/services/brain/actions.py:147` | 시험: `domains/test_brain_fix_perm_releases.py` |
| 마-10 | 뒤 판이 같은 지식을 또 고쳐 판째 되돌릴 수 없어요 — 지식마다 되돌려 주세요. | 그 뒤에 같은 지식을 또 고쳐서 하루치를 통째로 되돌릴 수 없어요 — 지식마다 따로 되돌려 주세요. | 「뒤 판 · 판째」가 설계 말 | `foms/services/brain/actions.py:67` | 글만 바꿈. |

## 바. 지식 카드 · 단추 (`item_*.html` · `ds-item.js` · `brain-item-actions.js`)

| 번호 | 지금 글 | 바꿀 글 | 왜 | 자리(`파일:줄`) | 고치는 법 · 같이 고칠 시험 |
|---|---|---|---|---|---|
| 바-1 | 속성 / 유형 '정책' 의 칸 | 세부 항목 / 정책 지식의 항목 | 「속성 · 칸」은 설계 말 | `templates/brain/ds/partials/item_glance.html:12`<br>`templates/brain/ds/partials/item_glance.html:12` | 시험: `domains/test_brain_ds_item.py` |
| 바-2 | 유효 기간 | 적용 기간 | 「유효」보다 「적용」이 화면 다른 곳 말과 맞음 | `templates/brain/ds/partials/item_glance.html:24` | 가-24 낱말. — 시험: `domains/test_brain_ds_item.py` |
| 바-3 | 유효 시작 / 유효 끝 (입력 칸 · 바뀐 항목 이름) | 적용 시작일 / 적용 종료일 | 「끝」은 사장님이 거절한 말 | `templates/brain/ds/partials/item_form.html:12`<br>`foms/services/brain/display.py:113`<br>`templates/brain/ds/partials/item_form.html:14`<br>`foms/services/brain/display.py:114` | 글만 바꿈. |
| 바-4 | 다시 볼 날 | 다음 확인일 | 지은 말 느낌 | `templates/brain/ds/partials/item_glance.html:26`<br>`templates/brain/ds/partials/search_main.html:83`<br>`static/js/brain/ds/ds-search-preview.js:67`<br>`foms/services/brain/table_export.py:22` | 가-25 낱말. 내보내기 표 머리(`table_export.py`)도 같은 글. — 시험: `domains/test_brain_ds_item.py`, `domains/test_brain_ds_search.py` |
| 바-5 | 낡음 (꼬리표) | 확인 날짜 지남 | 「낡음」은 물건이 헌 것처럼 읽힘 | `templates/brain/ds/partials/item_glance.html:82`<br>`static/js/brain/ds/ds-search-preview.js:48`<br>`static/js/brain/brain-view.js:45` | 가-8 낱말. — 시험: `domains/test_brain_screens_js.py` |
| 바-6 | 낡음 — 다시 확인할 때 | 확인할 때가 됐어요 | 가-8 낱말 | `templates/brain/ds/partials/item_head.html:23` | 시험: `domains/test_brain_ds_item.py` |
| 바-7 | 기간 끝남 — 찾기 · 표 · 연결에서 빠져요 | 적용 기간 지남 — 찾기 · 지식 표 · 연결에서 빠져요 | 「끝남」은 사장님이 거절한 말 | `templates/brain/ds/partials/item_head.html:22` | 글만 바꿈. |
| 바-8 | 손님에게 말하지 않음 — AI 는 판단에만 써요 | 내부용 — 고객에게 안내하지 않고 AI가 판단할 때만 써요 | 손님 → 고객 · 띄어쓰기 | `templates/brain/ds/partials/item_head.html:28`<br>`templates/brain/item.html:38` | 옛 카드 화면(`templates/brain/item.html`)에도 같은 글이 있다. |
| 바-9 | 엇갈림 N건 — 확인해 주세요 | 충돌 N건 — 확인해 주세요 | 가-2 낱말 | `templates/brain/ds/partials/item_head.html:38` | 시험: `domains/test_brain_chat_learning.py`, `domains/test_brain_inbox_bins.py` |
| 바-10 | 승인을 기다리는 수정 N개 | 승인 대기 N건 | 가-21 낱말 · 같은 화면 오른쪽 상자 이름이 「승인 대기」 | `templates/brain/ds/partials/item_head.html:26`<br>`static/js/brain/ds/ds-search-preview.js:47` | 시험: `domains/test_brain_ds_item.py`, `domains/test_brain_inbox_bins.py` |
| 바-11 | 연결 규칙: 적용 1 ~ 여럿 | 연결 규칙: 적용 1개 이상 | 「여럿」이 숫자 칸에 어색함 | `templates/brain/ds/partials/item_glance.html:65` | 시험: `domains/test_cs_order_find_closed.py` |
| 바-12 | 이웃 지도 | 연결 그림 | 「이웃」은 지은 말 느낌 | `templates/brain/ds/partials/item_glance.html:67` | 시험: `domains/test_brain3d_js.py` |
| 바-13 | 그 밖 N개 | 외 N개 | 가-10 낱말 | `templates/brain/ds/partials/item_glance.html:85` | 시험: `domains/test_brain_chat_learning.py`, `domains/test_brain_ds_inbox_erp.py`, `domains/test_brain_ds_search.py` 외 1개 |
| 바-14 | 빠진 연결 — 적용 0/1 | 연결이 모자라요 — 적용 0/1개 | 명사형 끝 | `templates/brain/ds/partials/item_more.html:7` | 글만 바꿈. |
| 바-15 | 자리가 없어요 — 키를 확인해 주세요 | 가리킨 곳을 찾을 수 없어요 — 관리자에게 알려 주세요 | 「키」는 기계 말 · 사장님이 고칠 수 없는 일 | `templates/brain/ds/partials/item_more.html:30` | 글만 바꿈. |
| 바-16 | 사본 — 자동 확인 안 해요 | 복사본 — 자동으로 확인하지 않아요 | 가-12 낱말(사본 → 복사본) | `templates/brain/ds/partials/item_more.html:31` | 글만 바꿈. |
| 바-17 | 지금 값은 볼 수 있는 사람만 | 지금 값은 권한이 있는 사람만 볼 수 있어요 | 문장이 끊김 | `templates/brain/ds/partials/item_more.html:35` | 시험: `domains/test_brain_d105.py` |
| 바-18 | 만든 이 | 만든 사람 | 「이」는 글말 | `templates/brain/ds/partials/item_more.html:17`<br>`templates/brain/ds/partials/item_history.html:10` | 글만 바꿈. |
| 바-19 | 바뀐 칸 (수정 기록 표 머리) | 바뀐 항목 | 「칸」은 설계 말 | `templates/brain/ds/partials/item_history.html:9` | 시험: `domains/test_brain_rest_h_words.py` |
| 바-20 | 판(하루 묶음) (수정 기록 표 머리) | 묶음 번호 | 가-3 낱말 | `templates/brain/ds/partials/item_history.html:10` | 시험: `domains/test_brain_polish_f_text.py` |
| 바-21 | 판 · 하루 묶음 (링크) | 날짜별 기록 | 마-1 과 같은 이름으로 | `templates/brain/ds/partials/item_aside.html:21` | 글만 바꿈. |
| 바-22 | 판 N (수정 기록 줄 꼬리표) | N번 묶음 | 같은 줄에 「버전 N」이 있어 판 · 버전이 섞임 | `templates/brain/ds/partials/item_aside.html:48` | 글만 바꿈. |
| 바-23 | 옛 판으로 되돌리기 제안 (바로 아래 단추는 「버전 N」) | 예전 버전으로 되돌리기 제안 | 한 화면에서 같은 것을 판 · 버전 두 이름으로 부름 | `templates/brain/ds/partials/item_aside.html:71` | 시험: `domains/test_brain_ds_item.py` |
| 바-24 | 까닭: … | 이유: … | 가-5 낱말 | `templates/brain/ds/partials/item_aside.html:30` | 시험: `domains/test_brain_fix_inbox_js.py` |
| 바-25 | · 승인 X (수정 기록 줄) | · 승인자 X | 「승인 X」가 「X를 승인」으로 읽힘 | `templates/brain/ds/partials/item_aside.html:53` | 시험: `domains/test_brain_ds_inbox_erp.py`, `domains/test_brain_ds_inbox_erp_fix.py`, `domains/test_brain_fix_names_js.py` 외 2개 |
| 바-26 | 은퇴 (단추 짧은 이름) | 사용 중지 | 가-7 낱말 | `templates/brain/ds/partials/item_aside.html:9` | 시험: `domains/test_brain_change_request_words.py`, `domains/test_brain_ds_item.py`, `domains/test_brain_ds_search.py` 외 2개 |
| 바-27 | 어느 단추도 바로 바꾸지 않아요. 모두 승인 대기로 가고, 사장님이나 담당 팀장이 승인하면 바뀌어요. | 어느 버튼을 눌러도 바로 바뀌지 않아요. 모두 승인 대기로 가고, 사장님이나 담당 팀장이 승인하면 바뀌어요. | 가-23 낱말 · 단추가 주어라 어색함 | `templates/brain/ds/partials/item_aside.html:88` | 글만 바꿈. |
| 바-28 | 글 (입력 칸 이름) | 내용 | 「글」만으로는 무엇인지 모름 | `templates/brain/ds/partials/item_form.html:9` | 글만 바꿈. |
| 바-29 | 까닭(꼭) — 사람 이름 · 전화 · 주소는 빼 주세요 | 이유(필수) — 고객 이름 · 전화번호 · 주소는 적지 마세요 | 가-5 낱말 · 「꼭」이 이름표로 어색함 | `templates/brain/ds/partials/item_form.html:36` | 글만 바꿈. |
| 바-30 | 쉼표로 나눠 적기 | 쉼표(,)로 나눠 적어 주세요 | 명사형 끝 | `templates/brain/ds/partials/item_form.html:31` | 글만 바꿈. |
| 바-31 | 고칠 말 제안 (단추) | 고칠 내용 제안 | 「말」이 무엇인지 모호함 | `foms/services/brain/actions.py:100`<br>`static/js/brain/ds/ds-search-preview.js:124` | 시험: `domains/test_brain_polish_f_text.py`, `domains/test_brain_rest_h_words.py` |
| 바-32 | 은퇴 제안 (단추) | 사용 중지 제안 | 가-7 낱말 | `foms/services/brain/actions.py:104` | 시험: `domains/test_brain_polish_f_text.py` |
| 바-33 | 이어진 ERP 물건이 없어요. / ERP 물건과 이어짐 / 이어진 ERP 물건 | 연결된 ERP 자료가 없어요. / ERP 자료와 연결됨 / 연결된 ERP 자료 | 가-16 낱말 · 명사형 끝 | `static/js/brain/ds/ds-item.js:136`<br>`static/js/brain/ds/ds-item.js:154`<br>`static/js/brain/ds/ds-search-preview.js:86` | 글만 바꿈. |
| 바-34 | 까닭을 적어 주세요. | 이유를 적어 주세요. | 가-5 낱말 | `static/js/brain/brain-item-actions.js:93` | 글만 바꿈. |
| 바-35 | AI 상담 · 챗봇이 N번 썼어요 | AI 상담과 챗봇이 N번 썼어요 | 문장 안 가운뎃점 | `templates/brain/ds/partials/item_glance.html:35` | 글만 바꿈. |

## 사. 찾기 · 지식 표

| 번호 | 지금 글 | 바꿀 글 | 왜 | 자리(`파일:줄`) | 고치는 법 · 같이 고칠 시험 |
|---|---|---|---|---|---|
| 사-1 | 그 밖 N 유형 | 다른 유형 N개 더 보기 | 단추가 무슨 일을 하는지 안 보임 | `templates/brain/ds/partials/search_main.html:53` | 시험: `domains/test_brain_chat_learning.py`, `domains/test_brain_ds_inbox_erp.py`, `domains/test_brain_ds_search.py` 외 1개 |
| 사-2 | 확인 (거르기 이름) | 확인 상태 | 무엇을 확인하는지 빠짐 | `templates/brain/ds/partials/search_main.html:59` | 시험: `domains/test_brain_ds_search.py` |
| 사-3 | [새로 붙음] 줄을 누르면 오른쪽에서 지난 2주 동안 어디에 쓰였는지 보여요. | [새 기능] 줄을 누르면 지난 2주 동안 어디에 쓰였는지 오른쪽에 보여요. | 가-17 낱말 | `templates/brain/ds/partials/search_main.html:101` | 글만 바꿈. |
| 사-4 | 지식 · 유형 (위 줄 찾기 칸 안내 글) | 지식 이름이나 유형 찾기 | 무엇을 넣는 칸인지 모호함 | `templates/brain/ds/layout.html:65` | 시험: `domains/test_brain_ds_shell.py` |
| 사-5 | 수정 대기 N / 엇갈림 N (표 줄 꼬리표) | 승인 대기 N / 충돌 N | 가-21 · 가-2 낱말 | `static/js/brain/ds/ds-search-view.js:62`<br>`static/js/brain/ds/ds-search-view.js:63` | 글만 바꿈. |
| 사-6 | 수정 대기 · 엇갈림 (내보내기 표 머리) | 승인 대기 · 충돌 | 사-5 와 같은 말로 | `foms/services/brain/table_export.py:22` | 내보내기 표 머리를 시험이 못 박았는지 확인 필요. — 시험: `domains/test_brain_chat_learning.py`, `domains/test_brain_inbox_bins.py` |
| 사-7 | 등급 (표 머리) | 위험 등급 | 거르기 이름(「위험 등급」)과 다름 | `templates/brain/ds/partials/search_main.html:82` | 시험: `domains/test_brain_ds_search.py` |
| 사-8 | 기간 끝남 (쓰인 곳 상태) | 기간 지남 | 「끝남」은 거절된 말 | `foms/services/brain/usage_view.py:50` | 글만 바꿈. |
| 사-9 | 주문 품목 이름과 이어져요 | 주문 품목 이름과 연결돼요 | 가-11 낱말 | `foms/services/brain/usage_view.py:153` | 시험: `domains/test_graft_usage_view.py` |

## 아. 문장으로 고치기 (`request*.html` · `ds-request*.js` · `change_request_*.py`)

한 번 넣은 문장을 화면은 「묶음」이라 부른다. 「요청」 하나로 맞춘다.

| 번호 | 지금 글 | 바꿀 글 | 왜 | 자리(`파일:줄`) | 고치는 법 · 같이 고칠 시험 |
|---|---|---|---|---|---|
| 아-1 | 바뀐 내용을 적어 주세요 (이름 없는 칸) + [분석] | 바뀐 회사 규칙이나 안내를 한 문장으로 적어 주세요 + [고칠 곳 찾기] | 무엇이 바뀐 건지(주문? 지식?), 누르면 무슨 일이 생기는지 모름 | `templates/brain/ds/partials/request_input.html:11`<br>`templates/brain/ds/partials/request_input.html:12` | 시험: `domains/test_brain_ds_request.py` |
| 아-2 | 묶음 N (길 표시) | 요청 N번 | 가-26 낱말 · 「묶음」이 승인 대기 묶음 ①~⑥ 과 헷갈림 | `templates/brain/ds/request.html:116` | 글만 바꿈. |
| 아-3 | 문장으로 고친 것 (메뉴 · 제목 · 링크) | 문장으로 고친 기록 | 「것」만으로 목록인지 모름 | `templates/brain/ds/inbox.html:11`<br>`templates/brain/ds/request.html:115`<br>`templates/brain/ds/partials/request_list.html:6`<br>`templates/brain/ds/partials/request_input.html:14` | 시험: `domains/test_brain_ds_request.py` |
| 아-4 | 문장 하나로 고친 것을 묶음으로 모아 봐요. 누르면 고친 것 · 못 고친 것을 보고 묶음째 되돌릴 수 있어요. | 문장으로 고친 요청을 모아 봐요. 누르면 고친 것과 못 고친 것을 보고, 요청 하나를 통째로 되돌릴 수 있어요. | 「묶음째」 · 문장 안 가운뎃점 | `templates/brain/ds/partials/request_list.html:7` | 글만 바꿈. |
| 아-5 | 까닭 · … / 못 고치는 까닭 · … | 이유: … / 못 고치는 이유: … | 가-5 낱말 · 가운뎃점을 쌍점처럼 씀 | `templates/brain/ds/request.html:73`<br>`templates/brain/ds/request.html:75` | 시험: `domains/test_brain_ds_request.py`, `domains/test_brain_fix_inbox_js.py` |
| 아-6 | 틀리면 손님에게 '안 돼요'로 나가요 — 꼭 확인해 주세요 | 틀리면 고객에게 '안 된다'고 안내돼요 — 꼭 확인해 주세요 | 손님 → 고객 | `templates/brain/ds/request.html:78` | 시험: `domains/test_ai_staff_eval_calibrate.py`, `domains/test_ai_staff_eval_marks.py`, `domains/test_brain_ds_request.py` |
| 아-7 | 고칠 줄 (목록 제목) | 고칠 내용 | 「줄」은 화면 모양 말 | `templates/brain/ds/request.html:139` | 글만 바꿈. |
| 아-8 | 더 알아야 해요 | AI가 더 알아야 해요 | 누가 더 알아야 하는지 빠짐 | `templates/brain/ds/request.html:144` | 글만 바꿈. |
| 아-9 | 물음에 답을 적어 주세요 | 질문에 답을 적어 주세요 | 「물음」은 글말 | `templates/brain/ds/request.html:154` | 글만 바꿈. |
| 아-10 | 코드를 고쳐야 하는 것 / 이 길로는 못 고쳐요. 개발 쪽에 알려 주세요. | 개발이 필요한 것 / 여기서는 고칠 수 없어요. 개발 담당에게 알려 주세요. | 기계 말(코드) · 「이 길」 | `templates/brain/ds/request.html:163`<br>`templates/brain/ds/request.html:164` | 시험: `domains/test_brain_ds_request.py` |
| 아-11 | 버리면 아무것도 고치지 않고 이 묶음을 닫아요. 기록은 남아요. | 버리면 아무것도 고치지 않고 이 요청을 닫아요. 기록은 남아요. | 묶음 → 요청 | `templates/brain/ds/request.html:190` | 글만 바꿈. |
| 아-12 | 이 묶음 되돌리기 / 이 묶음이 고친 것만 전으로 돌아가고, 승인을 기다리는 것은 거둬요. | 이 요청 되돌리기 / 이 요청으로 고친 것만 전으로 돌아가고, 승인을 기다리던 것은 취소돼요. | 「거둬요」는 지은 말 느낌 | `templates/brain/ds/request.html:193`<br>`templates/brain/ds/request.html:193` | 시험: `domains/test_brain_ds_request.py` |
| 아-13 | 마쳤어요 — 화면을 새로 읽어요. | 완료했어요 — 화면을 새로 불러와요. | 사장님 말 「완료」 | `static/js/brain/ds/ds-request.js:72` | 글만 바꿈. |
| 아-14 | 분석을 맡겼어요 — 묶음 화면에서 결과가 나와요. | 분석을 시작했어요 — 요청 화면에서 결과를 볼 수 있어요. | 묶음 → 요청 | `static/js/brain/ds/ds-request-start.js:38` | 글만 바꿈. |
| 아-15 | 묶음 N개 | 요청 N건 | 묶음 → 요청 | `static/js/brain/ds/ds-request-list.js:76` | 시험: `domains/test_brain_d129.py`, `domains/test_brain_ontology_cq_props.py`, `domains/test_brain_polish_e_ui.py` 외 1개 |
| 아-16 | 되물음 / 분석 못 함 (상태 이름) | 질문 있음 / 분석 실패 | 「되물음」은 지은 말 느낌 · 명사형 끝 | `foms/services/brain/change_request_store.py:46`<br>`foms/services/brain/change_request_store.py:47` | 이름표만 바꿈. 상태 키(`asked` · `failed`)는 그대로. |
| 아-17 | 뺌 / 거둠 (줄 상태 이름) | 제외 / 취소됨 | 명사형 끝 · 지은 말 느낌 | `foms/services/brain/change_request_store.py:52`<br>`foms/services/brain/change_request_store.py:53` | 이름표만 바꿈. 키(`skipped` · `withdrawn`)는 그대로. |
| 아-18 | 은퇴 (줄 종류 이름) | 사용 중지 | 가-7 낱말 | `foms/services/brain/change_request_store.py:49` | 시험: `domains/test_brain_change_request_words.py`, `domains/test_brain_ds_item.py`, `domains/test_brain_ds_search.py` 외 2개 |
| 아-19 | 오늘 문장으로 고치기 돈 상한에 닿았어요 | 오늘 문장으로 고치기 비용 한도에 닿았어요 | 가-18 낱말 | `foms/services/brain/change_request_store.py:58` | 글만 바꿈. |
| 아-20 | 분석 준비가 안 됐어요(돈 상한 · 열쇠 설정) | 분석 준비가 안 됐어요(비용 한도 · AI 연결 설정) | 「열쇠」는 기계 말 | `foms/services/brain/change_request_store.py:59` | 글만 바꿈. |
| 아-21 | AI 답이 정한 꼴이 아니라서 아무것도 고치지 않았어요 | AI 답 형식이 맞지 않아 아무것도 고치지 않았어요 | 가-13 낱말 | `foms/services/brain/change_request_store.py:61` | 글만 바꿈. |
| 아-22 | 분석 중 쓸 수 있는 사람이 아니게 됐어요 | 분석하는 동안 사용 권한이 바뀌었어요 | 어순이 어색함 | `foms/services/brain/change_request_store.py:65` | 글만 바꿈. |
| 아-23 | 이 길로는 만들 수 없는 종류예요 / 이 길로는 아직 못 고치는 설정이에요 / 이 길로는 못 고치는 세부 칸이에요 | 「이 길로는」 → 「이 화면에서는」 | 「이 길」이 모호함 | `foms/services/brain/change_request_check.py:64,74,78` | 글만 바꿈. |
| 아-24 | 같은 묶음의 다른 줄과 맞서요 — 하나만 남겨 다시 넣어 주세요. | 같은 요청의 다른 줄과 내용이 서로 달라요 — 하나만 남기고 다시 넣어 주세요. | 가-2 낱말 · 묶음 → 요청 | `foms/services/brain/change_request_check.py:71` | 글만 바꿈. |
| 아-25 | 그 뒤 다른 고침이 같은 곳에 얹혀서 되돌리지 않았어요. | 그 뒤에 같은 곳을 또 고쳐서 되돌리지 않았어요. | 「얹혀서」가 어색함 | `foms/services/brain/change_request_check.py:77` | 글만 바꿈. |
| 아-26 | (… 정책 갈래 · 조건 꼴만 고쳐요) | (… 정책 종류 · 조건 형식만 고쳐요) | 가-13 낱말 | `foms/services/brain/change_request_check.py:78` | 글만 바꿈. |
| 아-27 | 이을 수 없는 연결 짝이에요. / 새 항목을 만들지 못해 이 연결도 잇지 않았어요. | 연결할 수 없는 짝이에요. / 새 항목을 만들지 못해 이 연결도 하지 않았어요. | 가-11 낱말 | `foms/services/brain/change_request_check.py:68`<br>`foms/services/brain/change_request_check.py:66` | 글만 바꿈. |
| 아-28 | X 층이라 그 층 승인자 · 관리자가 볼 것이에요 | X 팀 지식이라 그 팀 승인자나 관리자가 확인해야 해요 | 가-4 낱말 · 「볼 것이에요」 어색함 | `foms/services/brain/change_request_check.py:408` | 글만 바꿈. |
| 아-29 | 상황이 없어요 — 손님이 어떤 처지에서 묻는지… | 상황이 없어요 — 고객이 어떤 처지에서 묻는지… | 손님 → 고객 | `foms/services/brain/change_request_hints.py:46` | 글만 바꿈. |
| 아-30 | 용어가 없어요 — 손님이 쓰는 말이 무슨 뜻인지… | 용어가 없어요 — 고객이 쓰는 말이 무슨 뜻인지… | 손님 → 고객 | `foms/services/brain/change_request_hints.py:50` | 글만 바꿈. |
| 아-31 | 정책이 없어요 — 손님에게 적용하는 회사 규칙을… | 정책이 없어요 — 고객에게 적용하는 회사 규칙을… | 손님 → 고객 | `foms/services/brain/change_request_hints.py:52` | 글만 바꿈. |
| 아-32 | 기준 답 문구는 이 칸으로 못 채워요 — 손님에게 나가는 글이라… | 기준 답 문구는 이 칸으로 못 채워요 — 고객에게 나가는 글이라… | 손님 → 고객 | `foms/services/brain/change_request_hints.py:65` | 글만 바꿈. |
| 아-33 | 꼭 같이(필요) 연결이 없어요 / 공정 단계 잇기(공정 단계) 연결이 없어요 / 사장님 결정 잇기(정한 결정) 연결이 없어요 / 값 정본 연결이 없어요 | '꼭 같이 있어야 하는 것' 연결이 없어요 / '공정 단계' 연결이 없어요 / '정한 사장님 결정' 연결이 없어요 / '값 가져오는 곳' 연결이 없어요 | 같은 이름을 괄호로 두 번 · 「잇기 · 정본」 | `foms/services/brain/change_request_hints.py:70`<br>`foms/services/brain/change_request_hints.py:74`<br>`foms/services/brain/change_request_hints.py:80`<br>`foms/services/brain/change_request_hints.py:83` | 글만 바꿈. |
| 아-34 | … — 모자라요 | … — 부족해요 | 「모자라요」 자체는 통하지만 같은 화면 「부족」과 맞춤(작다) | `foms/services/brain/change_request_hints.py:111` | 글만 바꿈. |
| 아-35 | 모르는 연결 | 알 수 없는 연결 | 「모르는」이 사람을 탓하는 말로 읽힘 | `foms/services/brain/change_request_words.py:27` | 시험: `domains/test_brain_change_request_words.py` |
| 아-36 | 이 질문은 회사 지식 재료가 이미 다 있어요. | 이 질문에 필요한 회사 지식은 이미 다 있어요. | 「재료」는 설계 말 | `templates/brain/ds/partials/request_fill.html:14` | 글만 바꿈. |

## 자. 온톨로지 화면 (`onto*.html` · `ds-onto*.js` · `ontology_view.py`)

「온톨로지」라는 이름은 그대로 둔다(맨 끝 「그대로 둘 것」). 화면 안 설계서 말만 고친다.

| 번호 | 지금 글 | 바꿀 글 | 왜 | 자리(`파일:줄`) | 고치는 법 · 같이 고칠 시험 |
|---|---|---|---|---|---|
| 자-1 | 능력 질문(시험지) | 답해야 할 질문 | 설계서 말 | `templates/brain/ds/partials/onto_aside.html:5`<br>`static/js/brain/ds/ds-onto-detail.js:222` | 가-14 낱말. |
| 자-2 | 능력 질문 (왼쪽 정의 · 길 표시) | 답해야 할 질문 | 가-14 낱말 | `static/js/brain/ds/ds-onto-view.js:65`<br>`static/js/brain/ds/ds-onto-detail.js:221`<br>`templates/brain/ds/partials/onto_aside.html:4`<br>`foms/services/ai_staff/evals_view.py:165` | 시험: `domains/test_brain_ds_onto.py` |
| 자-3 | 왼쪽에서 물건 종류 · 연결 종류 · 능력 질문을 고르세요. | 왼쪽에서 자료 종류 · 연결 종류 · 답해야 할 질문을 고르세요. | 「물건」 · 「능력 질문」 | `templates/brain/ds/onto.html:36` | 글만 바꿈. |
| 자-4 | 능력 질문 N개가 필요 / 능력 질문 N개가 씀 | 답해야 할 질문 N개에 필요 / 답해야 할 질문 N개에 쓰임 | 「N개가 씀」 문법이 깨짐 | `static/js/brain/ds/ds-onto-view.js:80`<br>`static/js/brain/ds/ds-onto-view.js:116` | 시험: `domains/test_ai_staff_evals.py` |
| 자-5 | 이 종류가 필요한 능력 질문이 없어요. | 이 종류가 필요한 질문이 없어요. | 가-14 낱말 | `static/js/brain/ds/ds-onto-detail.js:55` | 글만 바꿈. |
| 자-6 | 정본 자리 — X | 원본 위치 — X | 가-12 낱말 | `static/js/brain/ds/ds-onto-kit.js:264`<br>`templates/brain/ds/partials/onto_aside.html:8` | 글만 바꿈. |
| 자-7 | 모자란 재료는 질문 표의 [문장으로 채우기]로 넣을 수 있어요. 종류 · 칸은 설계서와 코드로만 바꿔요. | 부족한 내용은 질문 표의 [문장으로 채우기]로 넣을 수 있어요. 종류와 항목은 개발 담당만 바꿀 수 있어요. | 설계서 · 코드는 기계 말 | `templates/brain/ds/partials/onto_aside.html:10`<br>`templates/brain/ds/partials/onto_aside.html:10,12` | 시험: `domains/test_brain_ds_onto.py` |
| 자-8 | ERP 붙으면 풀림 | ERP 연결되면 답할 수 있음 | 「풀림」이 모호함 | `static/js/brain/ds/ds-onto-detail.js:38`<br>`static/js/brain/ds/ds-onto-kit.js:210` | 글만 바꿈. |
| 자-9 | 모자람 (꼬리표) | 부족 | 명사형 끝 | `static/js/brain/ds/ds-onto-detail.js:60`<br>`static/js/brain/ds/ds-onto-kit.js:208` | 시험: `domains/test_brain_ontology_view.py` |
| 자-10 | 답 재료 (표 머리) | 답할 내용 | 「재료」는 설계 말 | `static/js/brain/ds/ds-onto-detail.js:56` | 시험: `domains/test_brain_ds_item.py` |
| 자-11 | 이 종류는 아직 속성 틀이 없어요(꼴 검사만). | 이 종류는 아직 정해진 항목이 없어요(형식만 검사해요). | 「속성 틀 · 꼴」 | `static/js/brain/ds/ds-onto-detail.js:72` | 글만 바꿈. |
| 자-12 | 표 머리 「칸 · 자료형 · 꼭 · 단위 · 범위 · 고를 값 · 표준 · 채움」 | 항목 · 값 종류 · 필수 · 단위 · 범위 · 고를 수 있는 값 · 표준 · 채운 수 | 설계서 표 머리 그대로 | `static/js/brain/ds/ds-onto-detail.js:73` | 시험: `domains/test_brain_ds_fit_narrow.py`, `domains/test_brain_plan_proposals.py` |
| 자-13 | 나감 → / ← 들어옴 | 나가는 연결 → / ← 들어오는 연결 | 명사형 끝 | `static/js/brain/ds/ds-onto-detail.js:83,150` | 글만 바꿈. |
| 자-14 | 판 1 에서는 속성 표 없이 정본 자리만 가리켜요 — … | (뺌) 또는 「아직 항목 표가 없어요 — 원본 위치만 보여요」 | 설계 차례(판 1) 말 | `static/js/brain/ds/ds-onto-detail.js:120` | 글만 바꿈. |
| 자-15 | 속성 ↔ 지금 칸 / 지금 FOMS 칸에 이름만 붙여 읽어요 | 항목 ↔ FOMS 칸 / FOMS에 있는 칸을 그대로 읽어요 | 설계 말 | `static/js/brain/ds/ds-onto-detail.js:122`<br>`static/js/brain/ds/ds-onto-detail.js:122` | 글만 바꿈. |
| 자-16 | 새 API 없이 지금 기능을 이름 붙여 감싸요 | FOMS에 있는 기능을 그대로 써요 | 기계 말(API · 감싸요) | `static/js/brain/ds/ds-onto-detail.js:139` | 글만 바꿈. |
| 자-17 | 표 머리 「감싸는 지금 기능 · AI 자율 수준 · 승인 자리」 | 실제로 처리하는 FOMS 기능 · AI에게 맡긴 수준 · 승인하는 곳 | 설계 말 | `static/js/brain/ds/ds-onto-detail.js:141` | 시험: `domains/test_graft_onto_erp.py` |
| 자-18 | 0 읽기만 · 1 초안 · 2 제안 · 사람만 | 0 읽기만 · 1 초안 쓰기 · 2 제안하기 · 사람만 | 카-2 와 같은 말로 | `static/js/brain/ds/ds-onto-detail.js:140` | 글만 바꿈. |
| 자-19 | 정본 = 지금 FOMS X 표 | 원본: FOMS의 X 자료 | 「=」 기호 · 「표」는 기계 말 | `static/js/brain/ds/ds-onto-detail.js:157` | 글만 바꿈. |
| 자-20 | 쓰기는 할 일로만 / AI 에 안 감 | 바꾸기는 AI 할 일 제안으로만 / AI에게 보내지 않음 | 명사형 끝 · 「쓰기」가 「글쓰기」로 읽힘 | `static/js/brain/ds/ds-onto-detail.js:158`<br>`static/js/brain/ds/ds-onto-detail.js:159` | 글만 바꿈. |
| 자-21 | ERP 물건 종류 | ERP 자료 종류 | 가-16 낱말 | `static/js/brain/ds/ds-onto-detail.js:172,185`<br>`static/js/brain/ds/ds-onto-kit.js:160` | 글만 바꿈. |
| 자-22 | 이 물건에 붙은 할 일이 없어요. / 이어진 물건이 없어요. | 이 자료에 붙은 할 일이 없어요. / 연결된 자료가 없어요. | 가-16 낱말 | `static/js/brain/ds/ds-onto-detail.js:143`<br>`static/js/brain/ds/ds-onto-detail.js:148` | 글만 바꿈. |
| 자-23 | ERP 물건이 필요한 질문 N | ERP 자료가 필요한 질문 N | 가-16 낱말 | `static/js/brain/ds/ds-onto-kit.js:230` | 글만 바꿈. |
| 자-24 | 지식 사이를 잇는 선 — 허용된 짝만 이어요 | 지식끼리 잇는 선 — 정해진 짝끼리만 이어요 | 「허용된」이 딱딱함(작다) | `static/js/brain/ds/ds-onto-detail.js:201` | 글만 바꿈. |
| 자-25 | 동작 종류 / 사람 승인 동작과 AI 에이전트 동작 — 쓰기는 이 동작으로만 해요 | 처리 종류 / 사람이 승인하는 처리와 AI 직원 처리 — 바꾸는 일은 이 처리로만 해요 | 「에이전트」는 영어 · 「AI 직원」과 같은 것 | `static/js/brain/ds/ds-onto-view.js:64`<br>`static/js/brain/ds/ds-onto-detail.js:215` | 시험: `domains/test_brain_ds_onto.py` |
| 자-26 | AI 에이전트 (누가 칸) | AI 직원 | 가-30 낱말 | `static/js/brain/ds/ds-onto-detail.js:217` | 글만 바꿈. |
| 자-27 | 내용이 맞는지는 평가 단계에서 재요. | 내용이 맞는지는 AI 시험에서 따로 확인해요. | 「평가 단계」는 설계 말 · AI 직원 화면 이름은 「AI 시험」 | `static/js/brain/ds/ds-onto-detail.js:222`<br>`static/js/brain/ds/ds-onto-kit.js:226` | 글만 바꿈. |
| 자-28 | 주문 · 일정을 읽기만 해도 풀리는 질문이에요. 읽기 도구가 있는 재료는 '있음'으로 세요. | 주문 · 일정을 읽기만 해도 답할 수 있는 질문이에요. 읽을 수 있는 자료는 '있음'으로 쳐요. | 「풀리는 · 재료 · 세요」 | `static/js/brain/ds/ds-onto-kit.js:231` | 시험: `domains/test_ai_staff_api.py`, `domains/test_ai_staff_registry.py`, `domains/test_ai_staff_screen_fix2.py` 외 3개 |
| 자-29 | 아직 못 푸는 질문 / 모두 답 재료가 있어요. | 아직 답 못 하는 질문 / 모든 질문에 답할 내용이 있어요. | 「푸는 · 재료」 | `static/js/brain/ds/ds-onto-kit.js:233-234`<br>`static/js/brain/ds/ds-onto-kit.js:237` | 시험: `domains/test_brain_ds_onto.py` |
| 자-30 | 값: 지금 FOMS 표 그대로 · 새 표 없음 / 정본 / 읽는 길 / 쓰는 길 / → 지금 기능 | 값: FOMS 자료 그대로 · 새로 만든 것 없음 / 원본 / 읽는 방법 / 바꾸는 방법 / → FOMS 기능 | 설계 말 · 「길」이 모호함 | `static/js/brain/ds/ds-onto-kit.js:258`<br>`static/js/brain/ds/ds-onto-kit.js:258`<br>`static/js/brain/ds/ds-onto-kit.js:259` | 글만 바꿈. |
| 자-31 | 표 X + JSONB 칸 N · 새 표 없음 | (뒤에 붙는 칸 수 꼬리는 뺌) FOMS 자료 그대로 | 기계 말(JSONB) | `static/js/brain/ds/ds-onto-view.js:114` | 글만 바꿈. |
| 자-32 | 가림 N칸 | 개인정보 가림 N칸 | 무엇을 가리는지 빠짐 | `static/js/brain/ds/ds-onto-view.js:115` | 시험: `domains/test_brain_ds_fit_narrow.py` |
| 자-33 | 꼭 / 반영 때 꼭 | 필수 / 저장할 때 필수 | 「꼭」이 이름표로 어색함 | `static/js/brain/ds/ds-onto-view.js:92` | 시험: `domains/test_brain_ds_fit_narrow.py` |
| 자-34 | ERP 재료를 세기 전 N → 지금 M | ERP 자료를 세기 전 N개 → 지금 M개 | 「재료」 | `static/js/brain/ds/ds-onto-view.js:139` | 시험: `domains/test_brain_ds_onto.py` |
| 자-35 | 층 … (유형 줄 요약) | 팀 … | 가-4 낱말 | `static/js/brain/ds/ds-onto-view.js:79` | 글만 바꿈. |
| 자-36 | 하나 고름 / 때 (값 종류 이름) | 하나 고르기 / 날짜와 시각 | 명사형 끝 · 「때」만으로는 모름 | `static/js/brain/ds/ds-onto-view.js:15` | 글만 바꿈. |
| 자-37 | 지금 시공 일정 잡기 · 지금 AS 접수 … (앞에 「지금」 붙은 기능 이름 여덟) | FOMS 시공 일정 잡기 · FOMS AS 접수 … (「지금」 대신 「FOMS」) | 「지금」이 시각으로 읽힘 | `foms/services/brain/ontology_view.py:96-100,102-104` | 시험: `domains/test_brain_chat_audit.py`, `domains/test_cs_edit_detail.py` |
| 자-38 | 지금 작업 승인(단계 넘기기) | FOMS 작업 승인(다음 단계로) | 자-37 과 같음 | `foms/services/brain/ontology_view.py:102` | 글만 바꿈. |
| 자-39 | 손님 (ERP 주문 연결 이름) | 고객 | 손님 → 고객 | `foms/services/brain/ontology_view.py:81` | 시험: `domains/test_cs_graft_as.py`, `domains/test_cs_learn_photos.py`, `domains/test_graft_ask_erp.py` 외 1개 |
| 자-40 | 폰 승인 (승인하는 곳) | 휴대폰 승인 | 가-19 낱말 | `foms/services/brain/ontology_view.py:166`<br>`static/js/brain/ds/ds-onto-view.js:20` | 화면 표(`ds-onto-view.js:20` WHERE_ICONS)가 이 글을 열쇠로 아이콘을 고른다 — 두 곳을 같이 바꿔야 아이콘이 안 빠진다. — 시험: `domains/test_graft_onto_erp.py` |

## 차. 물어보기 (`ask*.html` · `ds-ask*.js` · `chat_settings.py`)

| 번호 | 지금 글 | 바꿀 글 | 왜 | 자리(`파일:줄`) | 고치는 법 · 같이 고칠 시험 |
|---|---|---|---|---|---|
| 차-1 | 손님 이름 · 전화 · 주소는 적지 마세요(적어도 가려서 보내요). | 고객 이름 · 전화번호 · 주소는 적지 마세요(적어도 가린 뒤 보내요). | 손님 → 고객 | `templates/brain/ds/ask.html:42,45`<br>`templates/brain/partials/ask_panel.html:12` | 옛 화면 `templates/brain/partials/ask_panel.html` 에도 앞부분이 있다. |
| 차-2 | 보내기 전에 상담과 같은 가림을 거쳐요 | 보내기 전에 개인정보를 가려요 | 「가림을 거쳐요」는 설계 말 | `templates/brain/ds/ask.html:58` | 시험: `domains/test_brain_ds_ask.py` |
| 차-3 | 바뀐 내용으로 넣기 (단추) | 문장으로 고치기 | 같은 기능을 다른 이름으로 부름 | `templates/brain/ds/ask.html:62` | 시험: `domains/test_brain_ds_request.py` |
| 차-4 | 이 답이 읽은 것 | 이 답이 본 자료 | 「읽은 것」이 모호함 | `templates/brain/ds/partials/ask_aside.html:6,8` | 시험: `domains/test_brain_ds_ask.py` |
| 차-5 | 빈 지식(주 1회) / 빈 지식 · 이번 주 | 답 못 한 질문(주 1회) / 답 못 한 질문 · 이번 주 | 「빈 지식」이 무엇인지 모름 | `templates/brain/ds/partials/ask_side.html:14`<br>`templates/brain/ds/partials/ask_admin.html:5` | 시험: `domains/test_brain_ds_ask.py` |
| 차-6 | 아직 없어요. "빈 지식 묶기"를 켜면 주 1회 만들어요. | 아직 없어요. "답 못 한 질문 묶기"를 켜면 주 1회 만들어요. | 차-5 와 같은 말로 | `static/js/brain/ds/ds-ask-admin.js:83` | 글만 바꿈. |
| 차-7 | 틀림 신고 (메뉴) / 고마워요 — 틀림 신고를 남겼어요. | 틀린 답 신고 / 고마워요 — 틀린 답 신고를 남겼어요. | 명사형 끝 | `templates/brain/ds/partials/ask_side.html:15`<br>`static/js/brain/ds/ds-ask.js:188` | 글만 바꿈. |
| 차-8 | 틀림 보내기 | 틀렸다고 알리기 | 명사형 끝 | `static/js/brain/ds/ds-ask-turn.js:70` | 글만 바꿈. |
| 차-9 | 누르면 이 질문(가린 글)이 X 직원에게 FOMS 알림으로 가요. | 누르면 이 질문이 개인정보를 가린 채 X 직원에게 FOMS 알림으로 가요. | 「가린 글」이 모호함 | `static/js/brain/ds/ds-ask-turn.js:111` | 글만 바꿈. |
| 차-10 | 답 — 모름 (화면 읽기 이름) | 답을 찾지 못했어요 | 명사형 끝 | `static/js/brain/ds/ds-ask-turn.js:120` | 글만 바꿈. |
| 차-11 | 방문 옮기기는 승인 대기로 가요 / '방문 옮기기' 할 일 제안이 승인 대기로 가요 | 방문 날짜 변경은 승인 대기로 가요 / '방문 날짜 변경' 제안이 승인 대기로 가요 | 「옮기기」가 장소를 옮기는 말로 읽힘 | `static/js/brain/ds/ds-ask-turn.js:130`<br>`static/js/brain/ds/ds-ask-turn.js:190` | 할 일 이름 「방문 옮기기(실측 · 시공 · AS)」(`foms/services/erp_actions/registry.py:150,154,172`)와 같은 말이라 그 이름까지 같이 바꿀지 먼저 정해야 한다(다른 화면에도 나옴). — 시험: `domains/test_brain_ds_ask.py` |
| 차-12 | 빈 지식에 올렸어요 — 주 1회 묶어서 관리자가 봐요 | 답 못 한 질문으로 남겼어요 — 관리자가 일주일에 한 번 모아서 봐요 | 차-5 와 같은 말로 | `static/js/brain/ds/ds-ask-turn.js:139` | 글만 바꿈. |
| 차-13 | 가려서 안 받음 / ERP 물건 · 주문 / 쓴 도구 | 가려서 안 보여요 / ERP 자료 · 주문 / 확인한 자료 | 명사형 끝 · 가-16 낱말 · 「도구」는 기계 말 | `static/js/brain/ds/ds-ask-turn.js:174`<br>`static/js/brain/ds/ds-ask-turn.js:178`<br>`static/js/brain/ds/ds-ask-turn.js:187` | 글만 바꿈. |
| 차-14 | 0.1초 아래 | 0.1초 미만 | 「아래」가 위치로 읽힘 | `static/js/brain/ds/ds-ask-view.js:42` | 글만 바꿈. |
| 차-15 | ERP 읽음 / ERP 읽기 | 주문 확인 (하나로) | 같은 것을 두 이름으로 부름 | `static/js/brain/ds/ds-ask-view.js:62`<br>`static/js/brain/ds/ds-ask-view.js:84` | 시험: `domains/test_brain_ds_ask.py` |
| 차-16 | N곳을 가려서 보냄 | N곳 가린 뒤 보냄 | 어순(작다) | `static/js/brain/ds/ds-ask-view.js:113` | 시험: `domains/test_brain_ds_ask.py` |
| 차-17 | 물을 말을 적어 주세요. | 질문을 적어 주세요. | 「물을 말」이 어색함 | `static/js/brain/ds/ds-ask.js:245` | 글만 바꿈. |
| 차-18 | 설정 묶음 「켜기 · 여는 단계」 · 칸 「여는 단계」 | 켜기 · 사용 범위 / 사용 범위 | 「여는 단계」가 모호함 | `foms/services/brain/chat_settings.py:44`<br>`foms/services/brain/chat_settings.py:56` | 이름표만 바꿈. 저장 키(`stage`)는 그대로. — 시험: `domains/test_brain_polish_f_text.py` |
| 차-19 | 설정 묶음 「돈 · 남용 막기」 · 「빈 지식 · 관문」 | 비용 · 사용량 한도 / 답 못 한 질문 · 자동 검사 | 「남용 · 관문」은 설계 말 | `foms/services/brain/chat_settings.py:44` | 글만 바꿈. |
| 차-20 | 의미 찾기(Voyage AI — D114) | 뜻으로 찾기(Voyage AI) | 결정 번호(D114)가 화면에 보임 | `foms/services/brain/chat_settings.py:45` | 글만 바꿈. |
| 차-21 | 하루 돈 상한 · 문장으로 고치기 하루 돈 상한 · 의미 찾기 하루 돈 상한 | 하루 비용 한도 · 문장으로 고치기 하루 비용 한도 · 뜻으로 찾기 하루 비용 한도 | 가-18 낱말 | `foms/services/brain/chat_settings.py:64,66,78` | 시험: `domains/test_brain_chat_js.py` |
| 차-22 | 하루 돈 상한이 비어 있어 아직 답하지 않아요. | 하루 비용 한도가 비어 있어 아직 답하지 않아요. | 가-18 낱말 | `static/js/brain/ds/ds-ask-admin.js:141` | 글만 바꿈. |
| 차-23 | 시간 상한 · 의미 찾기 시간 상한 | 시간 한도 · 뜻으로 찾기 시간 한도 | 가-18 낱말 | `foms/services/brain/chat_settings.py:62,80` | 글만 바꿈. |
| 차-24 | 최대 출력 (단위 토큰) | 답 길이 한도 | 「출력 · 토큰」은 기계 말(단위 이름은 그대로 둬도 됨) | `foms/services/brain/chat_settings.py:61` | 글만 바꿈. |
| 차-25 | AI 제안 부딪침 판정 | AI 제안 충돌 검사 | 가-2 낱말 | `foms/services/brain/chat_settings.py:71` | 글만 바꿈. |
| 차-26 | 상담 사례 벡터(백필만) | 지난 상담 뜻 찾기 자료 만들기 | 기계 말(벡터 · 백필) | `foms/services/brain/chat_settings.py:82` | 글만 바꿈. |
| 차-27 | 도움말 「연결 열쇠가 없거나 실패하면」 · 「'바뀐 내용 넣기' 분석」 · 「가린 손님 질문」 | 「연결 설정이 없거나 실패하면」 · 「'문장으로 고치기' 분석」 · 「가린 고객 질문」 | 기계 말 · 같은 기능 다른 이름 · 손님 → 고객 | `foms/services/brain/chat_settings.py:77`<br>`foms/services/brain/chat_settings.py:67`<br>`foms/services/brain/chat_settings.py:83` | 시험: `domains/test_cs_case_memory.py` |

## 카. AI 직원 (`agents*.html` · `ds-agents*.js` · `ai_staff/*.py`)

| 번호 | 지금 글 | 바꿀 글 | 왜 | 자리(`파일:줄`) | 고치는 법 · 같이 고칠 시험 |
|---|---|---|---|---|---|
| 카-1 | 읽는 것 · 쓰는 도구 | 읽는 자료 · 쓰는 도구 | 「것」이 모호함 | `templates/brain/ds/agents.html:32` | 시험: `domains/test_brain_ds_agents.py` |
| 카-2 | 쓸 수 있는 할 일 · 자율 수준 / 0 읽기만 · 1 초안 · 2 제안 | 할 수 있는 일 · 맡긴 수준 / 0 읽기만 · 1 초안 쓰기 · 2 제안하기 | 「자율 수준」은 설계 말 | `templates/brain/ds/agents.html:40`<br>`templates/brain/ds/agents.html:40` | 시험: `domains/test_brain_ds_agents.py` |
| 카-3 | 2주 승인율 | 최근 2주 승인율 | 어느 2주인지 빠짐 | `templates/brain/ds/agents.html:43`<br>`static/js/brain/ds/ds-agents-kit.js:110,126` | 글만 바꿈. |
| 카-4 | 시험 세트 (메뉴) / 이 직원은 아직 시험 묶음이 없어요. | AI 시험 / 이 직원은 아직 AI 시험이 없어요. | 같은 것을 세 이름(AI 시험 · 시험 세트 · 시험 묶음)으로 부름 | `templates/brain/ds/partials/agents_side.html:9`<br>`static/js/brain/ds/ds-agents-evals.js:180` | 시험: `domains/test_brain_ds_agents.py` |
| 카-5 | 시험 설정 칸 「한 번 돈 상한(달러) · 지난 상담 수 · 위험 문장 수 · 지난 상담 기준(%)」 | 1회 비용 한도(달러) · 시험할 지난 상담 수 · 시험할 위험 문장 수 · 지난 상담 통과 기준(%) | 가-18 낱말 · 무엇의 수인지 빠짐 | `templates/brain/ds/partials/agents_evals.html:23`<br>`templates/brain/ds/partials/agents_evals.html:26` | 글만 바꿈. |
| 카-6 | 채점할 차례 | 채점할 답 | 「차례」가 순서로 읽힘 | `templates/brain/ds/partials/agents_evals.html:20`<br>`static/js/brain/ds/ds-agents-marks.js:44,150` | 글만 바꿈. |
| 카-7 | AI 초안을 손님에게 보내도 될지 골라 주세요 | AI 초안을 고객에게 보내도 될지 골라 주세요 | 손님 → 고객 | `static/js/brain/ds/ds-agents-marks.js:43` | 글만 바꿈. |
| 카-8 | 손님 글 (채점 줄 칸 이름) | 고객 글 | 손님 → 고객 | `static/js/brain/ds/ds-agents-marks.js:131` | 글만 바꿈. |
| 카-9 | 도는 중이에요 / 쓴 돈 | 시험 중이에요 / 쓴 비용 | 「돈다」는 기계 말 | `static/js/brain/ds/ds-agents-evals.js:97`<br>`static/js/brain/ds/ds-agents-evals.js:100` | 시험: `domains/test_ai_staff_evals.py`, `domains/test_ai_staff_evals_api.py` |
| 카-10 | 시험 상태 「줄 서는 중 · 도는 중 · 끝남 · 상한에서 멈춤 · 시간 상한에서 멈춤 · 멈춘 채 끝남」 | 대기 중 · 진행 중 · 완료 · 비용 한도로 멈춤 · 시간 한도로 멈춤 · 중간에 멈춤 | 「끝남」은 거절된 말 · 기계 말 | `foms/services/ai_staff/evals_view.py:43`<br>`foms/services/ai_staff/evals_view.py:44` | 이름표만 바꿈. 상태 키는 그대로. — 시험: `domains/test_ai_staff_api.py`, `domains/test_ai_staff_evals.py`, `domains/test_ai_staff_evals_api.py` 외 1개 |
| 카-11 | 실패 이유 「두뇌 열쇠 없음 · 열쇠 거절 · 돈 줄 꼴이 틀림 · 콘솔 돈 상한 · 줄이 없음 · 본문 디버그 로그가 켜짐 · 재료 꼴이 틀림」 | AI 연결 설정 없음 · AI 연결 거절 · 비용 기록 형식 오류 · AI 회사 쪽 비용 한도 · 기록 없음 · 개발용 기록이 켜져 있음 · 자료 형식 오류 | 기계 말 | `foms/services/ai_staff/evals_view.py:60`<br>`foms/services/ai_staff/evals_view.py:62`<br>`foms/services/ai_staff/evals_view.py:54` | 시험: `domains/test_ai_staff_evals.py` |
| 카-12 | 시험용으로 떼어 둔 상담이 없어요 — 묶음 0 / 검사에 걸린 적 있는 차례가 없어요 — 묶음 0 | 시험용 상담이 없어요 / 시험할 위험 문장이 없어요 | 「묶음 0」은 기계 말 | `foms/services/ai_staff/evals_view.py:128`<br>`foms/services/ai_staff/evals_view.py:151` | 글만 바꿈. |
| 카-13 | 아직 한 차례도 못 봤어요. / 견줄 차례가 아직 없어요 (옳은 넘김 N) | 아직 한 건도 시험하지 못했어요. / 비교할 건이 아직 없어요 (맞게 넘긴 것 N) | 「차례 · 옳은 넘김」 | `foms/services/ai_staff/evals_view.py:132,153`<br>`foms/services/ai_staff/evals_view.py:132` | 시험: `domains/test_ai_staff_eval_meaning.py` |
| 카-14 | 안 되는 답 N% 잡음 · 되는 답 N% 통과 | 틀린 답 N% 걸러냄 · 맞는 답 N% 통과 | 「잡음」이 소음으로 읽힘 | `foms/services/ai_staff/evals_view.py:108` | 글만 바꿈. |
| 카-15 | 실행 결과 「끝남」 · 단계 상태 「끝남」 | 완료 | 「끝남」은 거절된 말 | `foms/services/ai_staff/runs.py:47`<br>`foms/services/ai_staff/runs.py:117`<br>`static/js/brain/ds/ds-agents-kit.js:191` | 시험: `domains/test_ai_staff_api.py`, `domains/test_ai_staff_evals.py` |
| 카-16 | 지난 초안(손님이 더 씀) | 지난 초안(고객이 메시지를 더 보냄) | 손님 → 고객 · 「더 씀」 모호함 | `foms/services/ai_staff/runs.py:49` | 글만 바꿈. |
| 카-17 | 단계마다 시간은 없어요(전체 시간만) | 단계별 시간은 따로 없어요(전체 시간만 있어요) | 문장이 끊김 | `static/js/brain/ds/ds-agents-kit.js:224` | 글만 바꿈. |
| 카-18 | 걸림 (단계 상태) | 검사에 걸림 | 무엇에 걸렸는지 빠짐 | `static/js/brain/ds/ds-agents-kit.js:192` | 글만 바꿈. |
| 카-19 | 새로 / 새로 붙음 (꼬리표) | 새 기능 | 가-17 낱말 | `static/js/brain/ds/ds-agents-kit.js:84`<br>`static/js/brain/ds/ds-agents-kit.js:122` | 시험: `domains/test_ai_staff_screen_fix2.py`, `domains/test_brain_ds_ask.py`, `domains/test_brain_ds_inbox_erp.py` |
| 카-20 | AI 직원 설명 「손님 메시지」 · 「손님 정보」 · 「손님 이름 · 전화 · 주소는 가림」 · 「손님 글은 읽지 않아요」 · 「손님에게 나가는 글은…」 | 같은 자리를 모두 「고객」으로 (「고객 메시지」 · 「고객 정보」 …) | 손님 → 고객 | `foms/services/ai_staff/views.py:40-41,48-49,51-52,57,60` | 시험: `domains/test_cs_graft_as.py`, `domains/test_cs_learn_photos.py`, `domains/test_graft_ask_erp.py` 외 1개 |
| 카-21 | 실행 기록 단계 이름 「손님 · 주문 찾기」 · 「… · 손님 정보 가림」 · 「손님 글 읽기」 · 도구 설명 「학습 요약 읽기(손님 정보 없음)」 | 「고객 · 주문 찾기」 · 「… · 고객 정보 가림」 · 「고객 글 읽기」 · 「학습 요약 읽기(고객 정보 없음)」 | 손님 → 고객 | `foms/services/ai_staff/runs.py:131`<br>`foms/services/ai_staff/runs.py:132`<br>`foms/services/ai_staff/runs.py:146`<br>`foms/services/ai_staff/registry.py:39` | 시험: `domains/test_ai_staff_screen_fix2.py` |
| 카-22 | DB 를 직접 못 봐요 — 도구로만 읽어요 | 회사 자료를 직접 열지 않고 정해진 도구로만 읽어요 | 기계 말(DB) | `foms/services/ai_staff/views.py:55` | 글만 바꿈. |
| 카-23 | 손님에게 나가는 글은 사람이 보내요 · 운영 AI 몫 | 고객에게 가는 알림은 사람이 승인해야 나가요 | 「운영 AI 몫」 뜻이 흐림(바꿀 글은 추측) | `foms/services/ai_staff/views.py:60` | 글만 바꿈. |
| 카-24 | 도구 · 할 일 이름 「가림 · 주문 훑기 · 아침 훑기 · 도면 담당 맡기기 · 시공 잡기」 | 개인정보 가리기 · 주문 점검 · 아침 점검 · 도면 담당 지정 · 시공일 잡기 | 「훑기」는 지은 말 느낌 · 사장님 말 「지정」 | `foms/services/ai_staff/registry.py:35`<br>`foms/services/ai_staff/registry.py:38`<br>`foms/services/ai_staff/registry.py:119`<br>`foms/services/ai_staff/registry.py:121`<br>`foms/services/ai_staff/registry.py:125` | 시험: `domains/test_ai_staff_eval_marks.py`, `domains/test_ai_staff_sweep_share.py`, `domains/test_brain_change_request_words.py` 외 10개 |
| 카-25 | 우리 시공일 빔 | 우리 시공일 비어 있음 | 명사형 끝 | `foms/services/ai_staff/sweeps.py:271` | 글만 바꿈. |
| 카-26 | 고치려면 코드를 바꿔야 해요. | 고치려면 개발 담당에게 말해 주세요. | 기계 말(코드) | `foms/services/ai_staff/instructions.py:37` | 글만 바꿈. |
| 카-27 | 찾기만(돈 0) | 찾기만(비용 없음) | 「돈 0」 숫자 꼴 | `foms/services/ai_staff/ask_eval.py:25` | 글만 바꿈. |

## 타. 오류 · 안내 글 (공통)

| 번호 | 지금 글 | 바꿀 글 | 왜 | 자리(`파일:줄`) | 고치는 법 · 같이 고칠 시험 |
|---|---|---|---|---|---|
| 타-1 | 찾을 수 없습니다. | 찾을 수 없어요. | 해요체 사이에 합쇼체 | `foms/services/brain/actions.py:62`<br>`foms/services/ai_staff/evals.py:80`<br>`foms/services/ai_staff/levels.py:30` | 시험: `domains/test_ai_staff_api.py`, `domains/test_brain_ds_inbox_erp_fix.py`, `domains/test_brain_learned.py` 외 8개 |
| 타-2 | 글 관문을 넘지 못했어요(개인정보 · 한자 · 숫자 출처). | 자동 검사에 걸렸어요(개인정보 · 한자 · 숫자 근거). | 가-22 낱말(관문) | `foms/services/brain/actions.py:70` | 글만 바꿈. |
| 타-3 | 이 종류 링크는 더 이을 수 없어요(연결 개수 상한) — 앞 링크를 먼저 빼 주세요. | 이 종류 연결은 더 할 수 없어요(개수 한도) — 기존 연결을 먼저 빼 주세요. | 링크 · 연결 두 말 · 「앞 링크」 | `foms/services/brain/actions.py:71` | 글만 바꿈. |
| 타-4 | 가리킨 계산기 · 설정 자리가 없거나 지금 확인할 수 없어요 — 키를 확인해 주세요. | 가리킨 계산기 · 설정을 찾을 수 없거나 지금 확인할 수 없어요 — 관리자에게 알려 주세요. | 「키」는 기계 말 · 사장님이 고칠 수 없는 일 | `foms/services/brain/actions.py:72` | 글만 바꿈. |
| 타-5 | 이 링크는 이을 수 없어요(근거 종류와 맞지 않는 자리 · 필요와 제외를 함께 · 고리) — 앞 링크를 확인해 주세요. | 이 연결은 규칙에 맞지 않아 할 수 없어요 — 기존 연결을 확인해 주세요. | 설계 말(고리 · 자리) | `foms/services/brain/actions.py:73` | 글만 바꿈. |
| 타-6 | 문제 글 칸 이름 「항목 키 · 기준 판 · 까닭 · 되돌릴 판」 | 지식 · 제안 때 버전 · 이유 · 되돌릴 버전 | 기계 말(키) · 가-3 · 가-5 낱말 | `static/js/brain/brain-view.js:92`<br>`foms/services/brain/actions.py:85`<br>`foms/services/brain/actions.py:87` | `brain-view.js:92` PARAM_LABELS 와 `actions.py` Param 이름표는 시험이 서로 맞춘다(`brain-view.js:91` 주석) — 두 곳 같이. — 시험: `domains/test_brain_fix_inbox_js.py` |
| 타-7 | …날짜(YYYY-MM-DD)여야 한다 → 화면 「날짜(YYYY-MM-DD)여야 해요」 | 날짜를 2026-11-26처럼 적어 주세요 | 영어 틀 글자(YYYY) | `foms/services/brain/schemas.py:272`<br>`foms/services/brain/gates.py:167,240` | 서버 글은 시험 · 옮기기 도구가 칸 자리로 읽는다(`brain-view.js:98-99` 주석) — 서버 글은 그대로 두고 `problemText` 에서 바꿔 보이는 편이 안전. |
| 타-8 | 꼴(…)이 맞지 않는다 → 화면 「꼴(…)이 맞지 않아요」 | 형식이 맞지 않아요 | 가-13 낱말 | `foms/services/brain/schemas.py:280` | 타-7 과 같음. — 시험: `domains/test_brain_rest_h_words.py` |
| 타-9 | 값이 아래 끝 ~ 위 끝 밖이다 → 화면 「…밖이에요」 | 값이 정해진 범위를 벗어났어요 | 「아래 끝 ~ 위 끝」 설계 말 | `foms/services/brain/schemas.py:334` | 타-7 과 같음. — 시험: `domains/test_brain_rest_h_words.py` |
| 타-10 | FOMS 로 돌아가기 (그 밖에 「AI 가 · PC 에서 · FOMS 의」 꼴) | FOMS로 돌아가기 (영어 뒤 조사는 붙여 씀) | 띄어쓰기가 틀림 | `templates/brain/ds/layout.html:98` | 곳 수는 가-28. |

## 파. 유형 · 연결 · 상태 이름 (`foms/services/brain/display.py` 표)

모두 키(영어)에 붙은 이름표다. 키는 그대로 두고 이름표만 바꾼다. 이름표를 글자로 못 박은 시험이 많아 시험 칸을 꼭 본다.

| 번호 | 지금 글 | 바꿀 글 | 왜 | 자리(`파일:줄`) | 고치는 법 · 같이 고칠 시험 |
|---|---|---|---|---|---|
| 파-1 | 유형 묶음 「상담 층 · 도면 층」 | 상담 · 도면 | 가-4 낱말(층) | `foms/services/brain/display.py:67`<br>`foms/services/brain/display.py:68` | 글만 바꿈. |
| 파-2 | 유형 묶음 「에이전트 일」 | AI 직원 일 | 영어 낱말 · 「AI 직원」과 같은 것 | `foms/services/brain/display.py:70`<br>`static/js/brain/brain3d-core.js:45` | 글만 바꿈. |
| 파-3 | 유형 묶음 「바깥 정본(가리키기만) · 바깥 사본(점검만)」 | 다른 곳 원본(가리키기만) · 다른 곳 복사본(점검만) | 가-12 낱말 · 「바깥」 | `foms/services/brain/display.py:71`<br>`foms/services/brain/display.py:72` | 글만 바꿈. |
| 파-4 | 유형 이름 「엇갈림」 | 충돌 | 가-2 낱말 | `foms/services/brain/display.py:51` | 시험: `domains/test_brain_chat_learning.py`, `domains/test_brain_inbox_bins.py` |
| 파-5 | 유형 이름 「…(사본)」 다섯(매크로 · 스토어 상세 · 화면 · 양식 …) | …(복사본) | 가-12 낱말 | `foms/services/brain/display.py:58-61` | 글만 바꿈. |
| 파-6 | 연결 「값 정본 · 값 정본 자리 · 값을 가져가는 항목」 | 값 가져오는 곳 · 값 원본 위치 · 이 값을 쓰는 지식 | 가-12 낱말 | `foms/services/brain/display.py:80` | 글만 바꿈. |
| 파-7 | 연결 「사본 · 사본 · 정본」 | 복사본 · 복사본 · 원본 | 가-12 낱말 | `foms/services/brain/display.py:81` | 글만 바꿈. |
| 파-8 | 연결 「대한 것 · 무엇에 대한 것 · 이 항목에 대한 엇갈림 · 물어볼 것」 | 관련 · 무엇에 관련된 것 · 이 항목에 대한 충돌 · 물어볼 것 | 「대한 것」이 이름표로 어색함 · 가-2 | `foms/services/brain/display.py:86` | 글만 바꿈. |
| 파-9 | 연결 「걸린 공정 단계 · 이 단계에 걸린 항목」 | 적용되는 공정 단계 · 이 단계에 적용되는 항목 | 「걸린」이 「검사에 걸림」과 헷갈림 | `foms/services/brain/display.py:88` | 시험: `domains/test_cs_onto_follow.py` |
| 파-10 | 연결 짧은 이름 「씀 · 답함 · 다듬음 · 들어감」 | 사용 · 답변 · 보완 · 포함 | 명사형 끝 | `foms/services/brain/display.py:89`<br>`foms/services/brain/display.py:90`<br>`foms/services/brain/display.py:91`<br>`foms/services/brain/display.py:93` | 시험: `domains/test_graft_usage_view.py` |
| 파-11 | 상태 「은퇴」 | 사용 중지 | 가-7 낱말 | `foms/services/brain/display.py:98`<br>`templates/brain/ds/partials/item_glance.html:81` | 시험: `domains/test_brain_change_request_words.py`, `domains/test_brain_ds_item.py`, `domains/test_brain_ds_search.py` 외 2개 |
| 파-12 | 바뀐 일 이름 「고침 · 은퇴 · 지움 · 연결 더함 · 연결 뺌」 | 수정 · 사용 중지 · 삭제 · 연결 추가 · 연결 삭제 | 명사형 끝 · 가-7 | `foms/services/brain/display.py:103`<br>`foms/services/brain/display.py:104` | 시험: `domains/test_brain_change_request_words.py`, `domains/test_brain_ds_item.py`, `domains/test_brain_ds_search.py` 외 8개 |
| 파-13 | 바뀐 일 이름(승인 대기 상자) 「은퇴 · 지우기」 | 사용 중지 · 삭제 | 파-12 와 같은 말로 | `foms/services/brain/card_pending.py:34` | 시험: `domains/test_brain_change_request_words.py`, `domains/test_brain_ds_item.py`, `domains/test_brain_ds_search.py` 외 2개 |
| 파-14 | 바뀐 항목 이름 「글 · 유효 시작 · 유효 끝 · 사본 목록 · 세부 칸」 | 내용 · 적용 시작일 · 적용 종료일 · 복사본 목록 · 세부 항목 | 바-3 · 가-12 낱말 | `foms/services/brain/display.py:113`<br>`foms/services/brain/display.py:115` | 시험: `domains/test_brain_change_request_props.py`, `domains/test_brain_ds_search.py`, `domains/test_brain_plan_proposals.py` 외 7개 |
| 파-15 | 거절 이유 「숫자 틀림 · 한 손님 일 · 정책 아님 · 그 밖」 | 숫자가 틀림 · 한 고객만의 일 · 회사 규칙 아님 · 기타 | 손님 → 고객 · 가-10 | `foms/services/brain/display.py:126`<br>`foms/services/brain/display.py:127` | 이름표만 바꿈. 코드(`one_customer` 등)는 그대로. — 시험: `domains/test_brain_chat_learning.py`, `domains/test_brain_d104.py`, `domains/test_brain_ds_inbox_erp.py` 외 3개 |
| 파-16 | 가격 규칙 주의 「손님에게 가는 금액이 바뀔 수 있어요.」 · 상용구 주의 「손님에게 그대로 나가는 글이에요.」 | 고객에게 가는 금액이 … / 고객에게 그대로 나가는 글이에요. | 손님 → 고객 | `foms/services/brain/display.py:145`<br>`foms/services/brain/display.py:147` | 시험: `domains/test_brain_inbox_bins.py` |

## 그대로 둘 것 (까닭)

- **「온톨로지」** (위 메뉴 `foms/web/brain.py:87` · 제목 `templates/brain/ds/onto.html:14-15` · 왼쪽 메뉴 `onto_side.html:13` · 길 표시 `onto_map.html:4` · `ds-onto-detail.js` 길 표시 · `search_side.html:30` 안내 글 · `ds-item.js:129` 마우스 올림 글): 사장님이 직접 쓰는 말이다. 앞선 비평의 「먼저 고칠 스무 개」 19번 「온톨로지 → 지식 구조」 제안과 §4 의 「지식 구조」 바꿈(`search_side.html:30` 「유형 · 묶음은 온톨로지에서 정해요」 포함)은 표에 넣지 않았다.
- **저장 표시 줄 「어긋남 — 」(`handoff_learning_gates.py:101` CLASH_HEAD) · 「승인된 규칙과 다름」(`photo_cards.py:60` DIFFERS_LINE)**: 학습 코드가 이 글로 충돌 카드를 알아본다(`handoff_learning_gates.py:107,153,178,335` · `handoff_learning_resort.py:161` · `handoff_learning_place.py:157`). 저장 글은 그대로 두고 화면에서만 바꾼다(나-1 · 나-2).
- **이유 글 머리 「문장으로 고치기 #N — 」**(`change_request_check.py:155,354`): 반영할 때 코드가 「 — 」로 잘라 읽고(`change_request_check.py:375`) 지식 문서 승인 칸에도 들어간다. 「넘긴 상담 배우기 카드」(`handoff_learning_gates.py:99` APPROVED_BY)와 「D174 사진 다시 학습」(`photo_cards.py:58`)도 지식 문서 승인 칸 글이라 화면 말이 아니다.
- **거절 코드 · 답 코드 · 상태 키 · 동작 키**(`knowledge_right` · `one_customer` · `asked` · `retire` · `propose_edit` 등): 이름표만 바꾸고 키는 둔다.
- **묶음 번호 ①~⑥**: 사장님이 번호로 부르고, 「'③ …'에 모아요」 같은 안내 글도 번호를 쓴다.
- **이미 통하는 업무 말**: 승인 대기 · 찾기 · 물어보기 · AI 직원 · 상담 AI · 일정 AI · 운영 AI · 나중에 볼 것 · 한글 이름 붙이기 · 다시 확인 · 수정 기록 · 체크한 줄 승인 · 모두 고르기 · 되돌리기 · 한눈에 · 연결된 지식 · 뇌 보기 · 약 N분 · 방금 정한 것.
- **③ 카드의 「어느 쪽이 맞아요?」 · 「회사 지식이 맞아요」 · 「둘 다 맞아요」 · 묶음 설명 「두 곳에 다르게 적힌 내용이에요. 맞는 쪽을 골라 주세요.」**: 통하는 말이다. 단추의 괄호 속만 고친다(나-4~6).
- **「승인하면 바로 바뀌고, 바뀌기 전 내용은 수정 기록에 남아요.」**(`inbox_main.html:7`): 좋은 문장이다. 같은 뜻의 다른 두 문장(다-18 · 다-19)을 이 문장으로 맞추기만 한다.
- **물어보기의 「모름」 꼬리표**: 바로 위 안내 글이 「없으면 '모름'과 물어볼 팀을 알려 줘요」로 이미 뜻을 풀어 준다.
- **고객 질문 목록**(`foms/services/brain/ontology_cqs.py`, 「제 가구의 색상은 무엇이었나요?」 등): 고객 말투를 일부러 따라 쓴 것이다. 묶음 이름 「견적·제품」만 다른 곳처럼 「견적 · 제품」으로 띄우면 맞다(작다).
- **제품 이름 「Sonnet 5.5 · Haiku 5.5 · Voyage AI」**: 개인정보 처리방침의 「국외 이전」과 맞춰야 하는 이름이다. 결정 번호 「D114」만 뺀다(차-20).
- **사장님이 쓰는 말 「통 · 체크 · 실측 · 시공 · 견적 · 담당」 · 숫자 정보 「AI 비용 N달러 · 걸린 시간 N초」.**
- **AI에게 주는 지시문 · 재료 글**(`chat_prompt.py` · `change_request_model.py` · `handoff_learning_prompt.py` · `handoff_learning_place.py` · `handoff_learning_judge.py` · `brain_instructions.py` · `brain_cases.py` 등): 「손님」이 많지만 화면에 나가지 않는다. `handoff_learning_photos.py:76` 「손님」 · `handoff_learning.py:294` 「▶ 사진 N (손님)」도 AI에게 가는 재료 글이다.
- **서비스 안쪽 오류 글**(`errors.py` 의 「~다」): 화면에는 `actions.py` FAILURES 표 글(타 절)로 바뀌어 나간다. 다만 입력 검사 글(`schemas.py` · `gates.py`)은 `brain-view.js:100` problemText 를 거쳐 나가므로 타-7~9 에 넣었다.
- **옛 화면**(`templates/brain/*.html` · `templates/brain/partials/` · `static/js/brain/brain-inbox-*.js` 등): 새 화면 스위치가 꺼진 사람에게만 보인다. 표에는 새 화면 줄만 넣고, 「손님」처럼 옛 화면에도 같은 글이 있는 곳만 「고치는 법」에 적었다(바-8 · 차-1). 옛 화면을 계속 둘 거라면 같은 번호를 고를 때 옛 화면도 같이 고친다.

## 못 찾은 것

앞선 비평이 짚은 글 가운데, 지금 코드에서 그 글자 그대로를 못 찾아 표에서 뺀 것이다.

- 「기준 판이 달라요」(앞선 비평 `errors.py:43`): 지금 코드에는 「기준 판이 다르다 — 지금 판 N」(`foms/services/brain/errors.py:43`, 예외 글)로만 있다. 화면에는 FAILURES 표의 「제안을 만든 뒤 지식이 바뀌었어요 — 새로 불러온 뒤 다시 봐 주세요.」(`actions.py:63`)가 나가는 것으로 보여 뺐다.

그 밖에 표에 넣은 296줄은 모두 지금 코드에서 찾았다. 앞선 비평의 줄 번호가 몇 줄 밀린 곳(예: 위 메뉴 `brain.py:85` → 지금 `:87`)은 지금 번호로 고쳐 적었다.

## 내가 확신 없는 것

- **「확실한 정도」**(지식 카드 · 표 머리 · 거르기 — `item_glance.html:20` · `search_main.html:59,82` · `display.py:113`): 앞선 비평은 「신뢰도」를 권했지만, 지금 말도 풀어 쓴 말이라 초등학생도 알아듣고 「신뢰도」가 더 쉽다고 하기 어렵다. 표에 넣지 않았다. 값 「관찰」(→ 「관찰만 됨」)도 같이 미뤘다.
- **「관문 미통과: …」**(`errors.py:99`)가 화면에 그대로 나가는지 확인하지 못했다. 나간다면 「자동 검사에 걸렸어요」로 바꿀 줄이다.
- **나-4 「(지식 그대로)」**: 누르면 질문만 닫히는 것은 코드로 확인했다(`knowledge_right` 를 받는 곳은 판정자에게 보이는 말 `handoff_learning_place.py:75` 뿐). 다만 직원 쪽(매크로 · 상담 안내)을 고칠 일을 따로 남기고 싶으셨다면 「고칠 일로」가 바라던 뜻일 수 있다 — 그렇다면 글이 아니라 기능이 빠진 것이다.
- **나-3 「직원 안내」와 「직원 말」**: AI 판정자에게 보이는 말은 이미 「직원 말이 맞아요(지식을 고침)」(`handoff_learning_place.py:75`)이다. 화면도 「직원 말」로 맞출지, 「직원 안내」로 할지 사장님께 여쭤볼 일이다.
- **라-11 「손님 알림톡」**: 할 일 제안(`foms/services/erp_actions/`)은 회사 지식 밖 기능이라 주문 화면에도 같은 글이 나온다. 머리 글자 비교(`views.py:287` · `dashboard.py:672` · `ds-inbox-erp-aside.js:268`)를 먼저 손봐야 해서, 고르셔도 한 번에 끝나는 줄이 아니다.
- **차-11 「방문 옮기기」**: 할 일 이름(`foms/services/erp_actions/registry.py:150,154,172`)이 주문 화면 · AI 직원 화면에도 쓰인다. 물어보기 글만 바꾸면 이름이 둘이 된다.
- **카-23 「손님에게 나가는 글은 사람이 보내요 · 운영 AI 몫」**: 원래 뜻을 확실히 모른다. 바꿀 글은 추측이다.
- **온톨로지 화면의 화면 읽기 이름 「상세 나누기」 · 「길」**(`ds-onto-kit.js:96,119`): 화면에 보이는 글이 아니라 화면 읽기 프로그램용 이름이다. 표에 넣지 않았다.
- **「같이 고칠 시험」 칸**: 글자 그대로 찾은 것만 적었다. 시험이 글을 조각내 견주거나(예: 「'판 ' + 번호」) 화면 HTML 을 통째로 견주면 못 잡았을 수 있다. 짧은 이름(「은퇴」 · 「그 밖」 · 「확인」)으로 찾은 시험은 다른 뜻의 같은 글자일 수 있다. 고친 뒤에는 바뀐 파일에 닿는 시험을 돌려 본다.
- **「화면 줄 수」**: 주석 · 설명 글을 빼고 셌지만, 서버 파일의 로그 글 같은 것이 섞였을 수 있는 대략의 수다.

