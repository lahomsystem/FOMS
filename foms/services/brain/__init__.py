"""HAUD master brain — 회사 지식 정본(설계서 2026-11-02-haud-master-brain). 판 1 ⑤-1: 표 · 저장 · 반영 동작 하나 ·
지식 문서 옮기기와 그림자 견주기. ⑤-2: '회사 지식' 읽기 화면 · 읽기 API(:mod:`foms.web.brain` · :mod:`foms.api.brain`).
⑤-3: 제안함 · 다시 확인 · 판 되돌리기 · 결정 숫자(:mod:`foms.api.brain_review`). 상담 두뇌 읽기 바꾸기는 아직 없다.

- :mod:`.constants` — 유형 · 층 · 링크 · 허용 짝 · 값 목록(코드 + 설계서로만 바꾼다).
- :mod:`.scope` — 보기 범위(찾는 단계에서 거른다).
- :mod:`.read` — 지금 항목 · 이력 · 이웃(재귀 CTE) · 찾기 · 개수.
- :mod:`.gates` — 꼴 · 글 관문(개인정보 0 · 한자 0 · 숫자는 승인 지식 · 계산기 값에서만).
- :mod:`.proposals` — 제안 만들기 · 되돌리기 제안 · 거절.
- :mod:`.apply` — **정본을 쓰는 유일한 동작**(권한 · 꼴 · 대상 · 기준 판 다시 확인 → 새 판 줄 · 앞 줄 닫기 · 판에 붙이기).
- :mod:`.doc_bridge` · :mod:`.doc_import` — 지식 문서 ↔ 표(옮기기 · 다시 만들기 · 견주기).
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
"""
