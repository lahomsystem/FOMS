"""암호화 backfill artifact·run 공용 library (BACKFILL-ARTIFACT-00, §7.3 line 1249-1258).

모든 remediation audit/backfill 도구가 공유하는 **단일 공용 인프라**. 이 패키지는
메커니즘만 제공한다 — 실제 domain audit/backfill 로직은 각 consumer packet 몫이다.

* :mod:`~foms.services.security.backfill.artifact_root` — ``FOMS_REMEDIATION_ARTIFACT_ROOT``
  위치/ACL/OS 가드(fail-closed).
* :mod:`~foms.services.security.backfill.crypto` — DPAPI CurrentUser key-envelope +
  AES-256-GCM payload envelope(nonce·AAD 바인딩).
* :mod:`~foms.services.security.backfill.manifest` — manifest.json/sha.txt, mapping_sha256
  (RFC 8785 JCS), approval-scope.json, self-reference-0 payload hash 목록.
* :mod:`~foms.services.security.backfill.runs` — ``maintenance_backfill_runs`` state
  machine(lease/heartbeat/checkpoint/STOPPED_DRIFT) + OPS-APPROVAL(BACKFILL_APPLY/
  REAUTHORIZE) 소비.

raw data key / plaintext PII / raw lease token 은 어디에도 저장하지 않는다.
"""
