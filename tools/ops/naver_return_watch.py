"""네이버 **실물 반품 1건**이 들어왔는지 본다 — 읽기 전용 관측 도구.

왜 있는가
---------
반품 **승인** 기능의 차단 요인(B1)은 조사로 안 풀린다. `holdbackStatus`(보류)와
`claimDeliveryFeePayMethod`(반품 배송비 귀책)를 실물로 한 번 봐야 갈래를 정할 수 있는데,
스테이징 392행에 그 두 값이 0건이다 — 우리는 진짜 반품의 모양을 본 적이 없다.

2026-08-27 부터 `claim_watch` 가 클레임 **모양이 바뀔 때마다**
``triage_state['claim_sync']['history']`` 에 1건씩 남긴다(값 + 출처 블록 이름). 이 스크립트는
그 이력을 읽어 **볼 만한 것이 생겼는지**만 말한다. 아무것도 안 쓴다.

쓰는 법
-------
production 또는 staging 의 ``DATABASE_PUBLIC_URL`` 을 환경변수로 넘긴다::

    NAVER_WATCH_DB_URL=<postgres url> python tools/ops/naver_return_watch.py
    NAVER_WATCH_DB_URL=<...> python tools/ops/naver_return_watch.py --json

종료 코드
---------
0: 볼 것 없음(반품 이력 0건) · 1: **볼 것이 생겼다**(반품 클레임 이력 있음) · 2: 조회 실패
"""

from __future__ import annotations

import json
import os
import sys
from typing import Any, Optional

#: 반품 축으로 보는 클레임 상태. 취소(CANCEL_*)는 이 관측의 대상이 아니다.
RETURN_STATUSES = ("RETURN_REQUEST", "RETURN_REQUESTED", "COLLECTING",
                   "COLLECT_DONE", "RETURN_DONE", "RETURN_REJECT")

#: 우리가 아직 한 번도 못 본 값들 — 이게 잡히면 그날이 B1 을 푸는 날이다.
NEVER_SEEN_FIELDS = ("holdback_status", "fee_pay_method")


def _rows(cur) -> list[tuple]:
    """네이버 링크 중 클레임 이력이 있는 행만 뽑는다."""
    cur.execute("""
        SELECT id, external_id, external_order_no, triage_state
        FROM external_order_links
        WHERE channel = 'NAVER' AND triage_state IS NOT NULL
        ORDER BY id DESC
    """)
    return cur.fetchall()


def _history(state: Any) -> list[dict]:
    """``triage_state`` 에서 클레임 이력 목록을 꺼낸다(형식이 깨져 있으면 빈 목록)."""
    if isinstance(state, str):
        try:
            state = json.loads(state)
        except ValueError:
            return []
    if not isinstance(state, dict):
        return []
    sync = state.get("claim_sync")
    if not isinstance(sync, dict):
        return []
    return [row for row in (sync.get("history") or []) if isinstance(row, dict)]


def collect(url: str) -> dict:
    """DB 를 **읽기 전용**으로 열어 반품 이력을 모은다.

    Args:
        url: postgres 접속 URL.

    Returns:
        ``{"links": [...], "never_seen": {...}, "total_rows": int}``.
    """
    import psycopg2

    conn = psycopg2.connect(url)
    conn.set_session(readonly=True, autocommit=True)
    try:
        cur = conn.cursor()
        found: list[dict] = []
        never_seen: dict[str, list] = {field: [] for field in NEVER_SEEN_FIELDS}
        total = 0
        for link_id, external_id, order_no, state in _rows(cur):
            history = _history(state)
            if not history:
                continue
            total += len(history)
            returns = [row for row in history
                       if str(row.get("status") or "") in RETURN_STATUSES]
            if not returns:
                continue
            found.append({
                "link_id": link_id,
                "external_id": external_id,
                "order_no": order_no,
                "history": returns,
            })
            for field in NEVER_SEEN_FIELDS:
                for row in returns:
                    if row.get(field):
                        never_seen[field].append(
                            {"link_id": link_id, "at": row.get("at"),
                             "value": row.get(field),
                             "block": row.get(field.split("_")[0] + "_block")})
        cur.close()
        return {"links": found, "never_seen": never_seen, "total_rows": total}
    finally:
        conn.close()


def main(argv: Optional[list[str]] = None) -> int:
    """관측 결과를 사람이 읽는 문장으로 찍는다. 볼 것이 생겼으면 1을 준다."""
    # Win11 콘솔은 cp949 라 한글 문장 안의 em dash 하나에 UnicodeEncodeError 로 죽는다.
    # 관측 도구가 관측 결과를 못 찍고 터지는 것이 더 나쁘다.
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, ValueError):
        pass
    argv = list(argv if argv is not None else sys.argv[1:])
    url = os.environ.get("NAVER_WATCH_DB_URL")
    if not url:
        print("NAVER_WATCH_DB_URL 이 없다 (railway variables 의 DATABASE_PUBLIC_URL)")
        return 2
    try:
        result = collect(url)
    except Exception as exc:  # 조회 실패는 관측 실패지 '볼 것 없음'이 아니다
        print(f"조회 실패: {exc}")
        return 2

    if "--json" in argv:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 1 if result["links"] else 0

    print(f"클레임 이력 총 {result['total_rows']}건 · 반품 이력 링크 {len(result['links'])}건")
    if not result["links"]:
        print("아직 볼 것 없음 — 진짜 반품이 들어오면 여기에 뜬다.")
        return 0
    for link in result["links"]:
        print(f"\n[link {link['link_id']}] 주문 {link['order_no']} ({link['external_id']})")
        for row in link["history"]:
            print(f"  {row.get('at')} {row.get('status')}"
                  f" 사유={row.get('reason') or '-'}"
                  f" 보류={row.get('holdback_status') or '-'}"
                  f"({row.get('holdback_block') or '-'})"
                  f" 귀책={row.get('fee_pay_method') or '-'}"
                  f"({row.get('fee_block') or '-'})")
    for field, hits in result["never_seen"].items():
        if hits:
            print(f"\n*** {field} 를 처음으로 봤다 — B1 을 푸는 값이다: {hits}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
