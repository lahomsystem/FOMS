"""HAUD master brain — 회사 지식 정본(설계서 2026-11-02-haud-master-brain). 판 1 ⑤-1: 표 · 저장 · 반영 동작 하나 ·
지식 문서 옮기기와 그림자 견주기. ⑤-2: '회사 지식' 읽기 화면 · 읽기 API(:mod:`foms.web.brain` · :mod:`foms.api.brain`).
⑤-3: 제안함 · 다시 확인 · 판 되돌리기 · 결정 숫자(:mod:`foms.api.brain_review`). 상담 두뇌는 여전히 지식 문서를 읽고, 그
문서는 반영 때마다 표에서 다시 쓴다(:mod:`.doc_sync` — 7.5).

- :mod:`.constants` — 유형 · 층 · 링크 · 허용 짝 · 값 목록(코드 + 설계서로만 바꾼다).
- :mod:`.scope` — 보기 범위(찾는 단계에서 거른다).
- :mod:`.read` — 지금 항목 · 이력 · 이웃(재귀 CTE) · 찾기 · 개수.
- :mod:`.gates` — 꼴 · 글 관문(개인정보 0 · 한자 0 · 숫자는 승인 지식 · 계산기 값에서만).
- :mod:`.proposals` — 제안 만들기 · 되돌리기 제안 · 거절.
- :mod:`.apply` — **정본을 쓰는 유일한 동작**(권한 · 꼴 · 대상 · 기준 판 다시 확인 → 새 판 줄 · 앞 줄 닫기 · 판에 붙이기).
- :mod:`.doc_bridge` · :mod:`.doc_import` · :mod:`.doc_sync` — 지식 문서 ↔ 표(옮기기 — 사람 판은 덮지 않음 · 다시 만들기 ·
  견주기 · 반영 때 문서 다시 쓰기 · 맞추기). :mod:`.template_fix` — 주간 고침 안 승인도 표를 거친다.
- :mod:`.access` — 화면 · API 를 여는 사람(ADMIN · 층 승인자 팀 MANAGER — D101, 그 밖 404).
- :mod:`.display` — 유형마다 색 · 아이콘 · 이름 하나(모든 화면 같은 표).
- :mod:`.browse` · :mod:`.card` · :mod:`.release_view` — 찾기 묶음 · 지식 표 · 유형 지도 · 항목 카드 · 판 목록과 차이(읽기만,
  모든 질의 · 수에 보기 범위).
- :mod:`.inbox` · :mod:`.decide` · :mod:`.review_rules` — 제안함(결정할 수 있고 볼 수 있는 것만 · 항목당 카드 하나 · AI 주
  상한) · 넣기 · 고쳐 넣기 · 거절 · 등급 A 한꺼번에 · AI 제안 4주 닫힘(정본 쓰기는 여전히 :mod:`.apply` 하나).
- :mod:`.recheck` · :mod:`.rollback` · :mod:`.metrics` — 다시 확인('아직 맞음' = 제안 → 반영) · 판 · 층 되돌리기(ADMIN) ·
  결정 숫자(ADMIN).
- :mod:`.actions` · :mod:`.action_runner` — 이름 있는 액션 유형(7.7 · D104 — 단추마다 하나, 매개변수 꼴 · 조건 · 실패 말 ·
  도구 목록)과 이름 → 서비스 실행 길(엔진은 :mod:`.apply` 그대로).
- :mod:`.schemas` — 유형별 속성 틀(SHACL 꼴 — 제안 · 반영 때 검사, 카드 눈에 띄는 칸 · 제안함 칸별 전 → 후).
- ⑤-4(7.5 화면 9 · 7.6 · 7.7 D105): :mod:`.around` — 이웃 찾기(Search Around — 종류 · 걸음 · 상한, 점 · 선 · 수 모두 보기
  범위) · 뇌 보기 바탕 점. :mod:`.quality` — 연결 개수 규칙(최대는 반영 때 막고 최소는 '빠진 링크' · 품질 수).
  :mod:`.external` — ``calc:`` · ``setting:`` 가리킴 실재 확인(제안 · 반영) · 카드의 지금 값(보기 범위 안에서만).
  유효 기간으로 읽기(끝난 항목 · 링크는 기본 읽기 · 이웃 · 수에서 빠짐)는 :mod:`.read` 의 조건 하나.
- ⑤-5(설계서 10절 · 7.7 D105 · D106 · D109 · D114 · 전사 지식 온톨로지 점검 '지금'): 물어보기(직원 챗봇) — :mod:`.chat_answer`
  (답하는 길 한 곳) · :mod:`.chat_retrieve` · :mod:`.chat_tools`(유형 있는 읽기 도구 셋) · :mod:`.chat_prompt` · :mod:`.chat_model`
  (상담 두뇌 부르기 · 따로 돈 줄) · :mod:`.chat_log` · :mod:`.chat_reports`(틀림 신고) · :mod:`.chat_gaps`(빈 지식) ·
  :mod:`.chat_settings` · :mod:`.chat_access`(여는 단계). 기본 읽기 거르기 하나는 :func:`.read.effective_clauses`.
  :mod:`.ai_gates`(AI 제안 관문 셋) · :mod:`.labels`(SKOS 이름표) · :mod:`.eval_set`(평가 질문 시험) · :mod:`.usage`(쓰인 횟수) ·
  :mod:`.conflicts`(열린 엇갈림 — ``about``) · :mod:`.embeddings` · :mod:`.embed_sources`(의미 찾기 — 처음 끔, 근원 셋:
  회사 지식 항목 · 물어보기 질문 · 상담 사례(백필만)).
"""
