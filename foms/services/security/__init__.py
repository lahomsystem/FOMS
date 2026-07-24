"""보안 인프라 서비스 (OPS-APPROVAL-00 등).

고위험 ops 승인 flow 의 공용 라이브러리:

* :mod:`ops_control_root` — ``FOMS_OPS_CONTROL_ROOT`` 보호 토큰 저장소.
* :mod:`ops_approval` — scope 정규화/해시, same-DB one-time consume,
  cross-DB RESERVED snapshot consume, reconcile.
* :mod:`ops_approval_manifest` — operation manifest 로드/seed 검증/CLI 양방향 비교.
"""
