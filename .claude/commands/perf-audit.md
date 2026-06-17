# FOMS 성능 정기 점검·개선 (perf-audit)

정기적으로 FOMS 성능 후보를 찾아 **올립니다**. (perf-guard가 "느려짐 방지"라면,
이건 "더 빠르게".) 주 1회 등 주기 점검용.

## 언제
정기(주 1회), 또는 "요즘 느리다" 신고 시.

## 실행
1. 전체 코드베이스 후보 스캔(advisory):
   ```bash
   python tools/perf/perf_scan.py --audit
   ```
2. **운영급 측정** — `docs/guides/PERFORMANCE_GUARDRAILS.md` §"점검 스킬 실행 절차 B":
   - 서버 **TTFB**부터 측정해 서버/프론트/SW/네트워크 분리("느리다=서버" 단정 금지).
   - 주요 쿼리 `EXPLAIN (ANALYZE)` → **Seq Scan 없음** 확인.
   - 정적 자원 캐시 적중 + 탭전환 fragment 캐시 확인.
   - 약한 dev 인스턴스 절대 시간 신뢰 금지. SW 동작은 **실제 Chrome**에서만.
   - 측정은 gstack browse 활용 가능.
3. high/빈도순 우선순위화 → 안전 수정 설계(인덱스·캐시·lazy 로드·페이지네이션).

## 주요 개선 레버 (과거 효과 확인됨)
- JSONB ILIKE → trigram 인덱스 / `@>` / denormalized 컬럼
- 정적 자원: SW staticCacheFirst + 버전 max-age (매 네비 서버 폭주 제거)
- 무거운 lib lazy 로드 / 공용 partial 경량화 / 대시보드 fragment HTML 축소
- N+1 → `in_(ids)` 배치, 매요청 무거운 계산 → Redis micro-cache

## 결과 보고
```markdown
## Perf Audit 결과
### 상위 개선 후보 (효과순)
- [높음] 항목 — 현재 측정값 → 기대 효과 — 안전 수정안
## 측정 근거
- TTFB / EXPLAIN / 캐시 적중 등 실측 수치
```

> 변경은 반드시 perf-guard + smoke 통과 후 deploy→production(검증 후 승격).
