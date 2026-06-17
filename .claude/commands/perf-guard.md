# FOMS 성능 회귀 점검 (perf-guard)

코드 수정이 FOMS를 느리게 만드는지 **머지 전에** 잡습니다. (FOMS는 SW 비전공자가
작성 — 어떤 변경이 느리게 하는지 자동으로 알려줍니다.)

## 언제
파일 수정/추가 후, 커밋·push 전. 특히 템플릿/JS/CSS/서비스워커/DB 쿼리 변경 시.

## 실행
1. 변경분 스캔(변경분만, high면 차단):
   ```bash
   python tools/perf/perf_scan.py --guard
   ```
2. 스크립트가 못 잡는 것을 **diff에서 직접** 점검 —
   `docs/guides/PERFORMANCE_GUARDRAILS.md` §"점검 스킬 실행 절차 A"의 수동 체크리스트
   (인덱스 EXPLAIN 확인 / N+1 / 매요청 캐시 / 공용 partial 무거운 JS / SW timeout).
3. 발견 시 같은 문서의 "필수 규칙"대로 수정.

## 핵심 안티패턴 (자동 탐지)
- `<script>` defer 없는 동기 로드 / 외부 CDN 동기 / 무거운 lib 전역 로드
- 서비스워커 `cache:"no-cache"` 강제 재검증
- `structured_data ... ilike` (JSONB→text 풀스캔 — 인덱스 확인 필요)
- `.limit()` 없는 `.query(...).all()` (무한 fetch)

## 결과 보고
```markdown
## Perf Guard 결과
- 판정: [차단(high) | 주의(medium) | 통과]
### [HIGH|MEDIUM] 규칙명
- 파일: path:line
- 문제: 무엇이 왜 느려지는지
- 수정: 구체안 (가이드 참조)
- 검증: 인덱스/EXPLAIN 등 확인 결과
```

> 자동 강제: 이 점검은 `scripts/ops/pre_push_smoke.ps1` + CI(`ci.yml`)의
> `tests/performance/`로도 차단됩니다. 정공법·사유: PERFORMANCE_GUARDRAILS.md
