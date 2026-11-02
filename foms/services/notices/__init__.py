"""FOMS 공지사항(본사 · 협력사) 서비스 — 설계서 docs/specs/2026-11-02-foms-notices_SPEC.md §2 · §3.

* :mod:`.audience` — 받는 사람 판정(볼 때 판정 — 나중에 들어온 계정도 받는다) · 받는 쪽 이름.
* :mod:`.service` — 내 공지 목록 · 창 공지 · 읽음 · 확인 · 관리자 만들기 · 고치기 · 지우기 · 확인 현황.

기존 협력사 공지(:mod:`foms.services.partners.notices`, 알림 종류 ``PARTNER_NOTICE``)는 그대로 둔다.
"""
