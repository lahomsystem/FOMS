"""AUTH-ACCOUNT-01: auth anti-abuse rate-limit key bootstrap/rotation.

SESSION-SIGNING-STATE-00 동형 상태기계로 rate limiter 의 서명 key 를 OPS-APPROVAL
게이트 하에 bootstrap/rotate 한다. runtime bridge(:mod:`key_state`)는 미engage 시
bucket 키를 byte-identical 로 통과시킨다(기존 rate 강제 무효화 0).
"""
