"""CHANNEL-INBOUND-ORDER-01: 채널 수신 주문 생성 파이프라인.

채널 webhook receipt 를 canonical ``create_order`` 로 정본 생성하는 dedicated worker 와,
그 encryption key 의 recovery/rotation/rewrap 상태기계(AUTH-ACCOUNT-01 동형), 전역 create
flag, receipt recovery/retention/create-state OPS operation 을 제공한다.

* :mod:`crypto`      — channel key at-rest envelope(master 아래) + per-receipt secret sealing + rewrap.
* :mod:`state_ops`   — channel key prepare/activate/finalize 상태 전이(old-reference 0 전 제거 0).
* :mod:`key_state`   — runtime bridge(활성/dual-accept 키 복호화) + rewrap 실행.
* :mod:`create_flag` — 전역 CHANNEL_CREATE_ENABLE/DISABLE + cutoff pause/resume.
* :mod:`receipt_ops` — receipt recovery(CREATE/IGNORE)·retention(EXTEND·expire)·create-state.
* :mod:`worker`      — dedicated worker(SKIP LOCKED·max10→RECOVERY_REQUIRED·heartbeat·readiness).
* :mod:`consume`     — 8 OPS-APPROVAL operation 의 same-DB consume 헬퍼(CLI 공용).
"""
