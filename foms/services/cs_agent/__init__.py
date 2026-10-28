"""AI 상담팀원(CS 총괄 에이전트) — 설계서 ``docs/specs/2026-10-27-cs-ai-agent_SPEC.md``.

모듈은 플랜(``docs/plans/2026-10-27-cs-ai-agent-plan.md``) 공통 규칙대로 이 패키지 하나에 둔다.
지금 있는 것: 상태 계산(:mod:`~foms.services.cs_agent.state`, 순수 함수) · 채널톡 읽기
(:mod:`~foms.services.cs_agent.channel_read`, GET 만) · 읽기 한도(:mod:`~foms.services.cs_agent.read_budget`) ·
상태 표(:mod:`~foms.services.cs_agent.state_store`, 수신 기록 뒤돌아 읽기 · 누락 경보).
"""
