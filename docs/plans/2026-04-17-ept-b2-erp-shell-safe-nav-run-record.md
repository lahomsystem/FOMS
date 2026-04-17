# EPT-B2 ERP shell 도입 (안전 네비) — Run Record
> 배치: **EPT-B2** | 상태: **동결 (완료)** | 상위: `2026-04-17-erp-fast-page-and-tab-navigation-execution-plan.md` §4.2 | 전제: `EPT-B1` 재동결·`EPT-R0`

## 1. Scope (재진술)
- **9 primary 전면 fragment 구현이 목적이 아님** — shell 클라이언트가 **fragment fetch를 시도하는 경로**를 **명시적으로 제한**한다.
- **`PRIMARY_NAV`**(잠금판 9개 URL)와 **`FRAGMENT_READY`**(현재 서버가 `view=fragment`+shell 헤더로 본문 조각을 내는 4탭)를 **다른 리스트**로 둔다.
- 기존 `runtime-shell.js` 동작: **FRAGMENT_READY에만** `fetch` + `pushState`; 그 외 **동일 출처 ERP 링크는 브라우저 기본 네비** (이중 요청 없음).

## 2. Acceptance
- [x] `PRIMARY_NAV` vs `FRAGMENT_READY` 구분이 **Python SSOT**(`erp_navigation_contract.py`)에 명문화된다.
- [x] **JS**에서 fetch 가드는 **FRAGMENT_READY 경로만** 통과한다 (`FAST_PATHS` 단순 9개 확장 **금지**).
- [x] `ERP_CANONICAL_TAB_PATHS` / SPEC §2와의 **하위 호환**: 여전히 **4탭 = fragment-ready canonical** 의미 유지.
- [x] focused pytest: fragment-ready 불변·primary 9개 등록·집합 관계.
- [x] 본 run record에 **설계 이유·Hard stop** 기록.

## 3. Stop rule / Hard stop
- `FAST_PATHS` / `FRAGMENT_READY`를 **9개로만** 늘려 전 탭에 fetch 시도 → **금지** (fragment 미구현 시 이중 GET).
- fragment 미구현 primary에 **fetch 선행** → **금지**.
- 라우트 URL·쿼리 의미·full HTML 응답·권한 변경 → **금지**.
- DB·migration·micro-cache 끔 → **금지**.

## 4. 설계 (요약)
| 개념 | 의미 | 현재 값 |
|------|------|---------|
| `ERP_PRIMARY_NAV_PATHS` | 잠금판 **9 primary** — 네비·문서·인벤토리 SSOT | 9 path |
| `ERP_FRAGMENT_READY_PATHS` | shell이 **fetch+swap** 해도 안전한 경로 (서버 fragment 구현됨) | 4 path |
| `ERP_CANONICAL_TAB_PATHS` | B1/SPEC 호환 별칭 | `FRAGMENT_READY`와 동일 튜플 |

**클라이언트**: `navigateByShell` 진입 전 `pathOnly(url)`이 **FRAGMENT_READY**에 속할 때만 fetch. (기존 로직 유지, 상수명만 명확화.)

**향후 (EPT-B3/B4)**: 추가 탭이 fragment 지원되면 해당 path만 `FRAGMENT_READY`에 **순차 추가** + 서버 분기 + 테스트.

## 5. 건드린 파일
- `foms/services/common/erp_navigation_contract.py`
- `static/js/erp/runtime-shell.js` (`window.FOMS_ERP_SHELL` PRIMARY/FRAGMENT 경로 노출)
- `docs/specs/2026-04-17-erp-shell-fragment-contract_SPEC.md`
- `tests/domains/test_erp_shell_fragment_contract.py`
- `docs/plans/2026-04-17-erp-fast-page-and-tab-navigation-execution-plan.md` §4.2
- 본 파일, `docs/ARCHIVE_INDEX.md`

## 6. 검증 명령
```text
python -c "import app; print('APP_OK')"
python tools/harness/verify_result.py --json
pytest tests/domains/test_erp_shell_fragment_contract.py -q
```

## 7. GDM super hard review (EPT-B2)

| 역할 | High | Medium | 메모 |
|------|------|--------|------|
| Semantic-preservation | 0 | 0 | 네비 의미 동일; 5탭은 기존과 같이 full load |
| Architecture | 0 | 0 | 이중 리스트로 fetch 경계 명시 |
| Route-inventory | 0 | 0 | 9 primary는 B1 v2와 동일 문자열 |
| UX/navigation | 0 | 0 | 이중 fetch 제거 설계 |
| Ops/evidence | 0 | 0 | 코드·문서 동기 |
| **Synthesis** | **0** | **0** | **EPT-B3** 계속 |

---

*Hard stop: §3 위반 시 배치 중단.*
