"""FOMS 접목판 표 셋(ORM) — 할 일 제안 · 회사 지식 쓰인 곳 기록 · AI 직원 실행 기록(설계서 2026-11-14-foms-graft 3.4).

:mod:`.models` 를 루트 :mod:`models` 끝에서 불러 ``Base`` 에 올린다(create_all 레인 · alembic env 가 같은 metadata).
DDL 정본은 마이그레이션 ``graft_00`` 이고, 시험(``tests/domains/test_graft_store.py``)이 둘을 견준다.
"""
