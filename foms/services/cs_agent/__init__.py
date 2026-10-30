"""AI 상담팀원(CS 총괄 에이전트) — 설계서 ``docs/specs/2026-10-27-cs-ai-agent_SPEC.md``.

모듈은 플랜(``docs/plans/2026-10-27-cs-ai-agent-plan.md``) 공통 규칙대로 이 패키지 하나에 둔다.
지금 있는 것: 상태 계산(:mod:`~foms.services.cs_agent.state`, 순수 함수) · 채널톡 읽기
(:mod:`~foms.services.cs_agent.channel_read`, GET 만) · 읽기 한도(:mod:`~foms.services.cs_agent.read_budget`) ·
상태 표(:mod:`~foms.services.cs_agent.state_store`, 수신 기록 뒤돌아 읽기 · 누락 경보) · 감시 루프 한 바퀴
(:mod:`~foms.services.cs_agent.loop`, 바로 끄기 · 대표 잠금 · TERM 깃발 · 채널톡 보정) · 아침 보고 · 경보
(:mod:`~foms.services.cs_agent.report`, FOMS 앱 안 알림 — 한 번씩만) · 기준 답 · 지식
(:mod:`~foms.services.cs_agent.knowledge` DB 읽기 · 쓰기 · 되돌리기, :mod:`~foms.services.cs_agent.knowledge_doc` 꼴 검사 ·
승인 항목만 재료) · 보내기 전 검사(:mod:`~foms.services.cs_agent.checks` 판정, :mod:`~foms.services.cs_agent.checks_rules`
금지 꼴, :mod:`~foms.services.cs_agent.checks_read` 숫자 · 링크 읽기) · 가림(:mod:`~foms.services.cs_agent.masking`, 가림 검사 0 일 때만 모델 호출) ·
빠른 길(:mod:`~foms.services.cs_agent.realtime`, 5초 차례 · 따로 잠금 · 모아 받기 — 'AI 냐 사람이냐' 물음은
:mod:`~foms.services.cs_agent.ask_human`) · 사례 기억(:mod:`~foms.services.cs_agent.case_memory` 직원 직접 답 붙이기 ·
:mod:`~foms.services.cs_agent.case_material` 비슷한 지난 사례 재료 — 두뇌에 싣는 꼴은
:mod:`~foms.services.cs_agent.brain_cases`, 지시문 글은 :mod:`~foms.services.cs_agent.brain_instructions`).
"""
