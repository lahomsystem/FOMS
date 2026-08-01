"""feature cutover 메커니즘 (CUTOVER-MODE-01).

legacy→new 무중단 cutover 를 fence/marker + build-compatibility generation 으로
원자 보장하는 메커니즘. 15 family 의 mode 전환을 소유한다. 이 패키지는 **메커니즘만**
제공한다 — 실제 business mutation 에 fence/mode 를 적용하는 것은 각 family packet 몫이다.

* :mod:`foms.services.security.cutover.families` — 15 family SSOT + §8.2/§8.2.1 per-family 스펙.
* :mod:`foms.services.security.cutover.mode_manifest` — mode manifest 로드 + 15-row 양방향 비교.
* :mod:`foms.services.security.cutover.transactional` — business tx 에 fence FOR KEY SHARE +
  marker read 를 거는 재사용 helper(mutation 미적용).
"""
