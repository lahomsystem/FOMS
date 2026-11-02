"""온톨로지 바로잡기(설계서 7.8) PostgreSQL 레인 — JSONB 실음 칸으로 가르는 질의가 진짜 PostgreSQL 에서도 같은 답인지.

① 품질 수: 가격 규칙 근거 종류(``payload->>'basis'``)로 나눈 최소 미달 · 넘음, 은퇴 항목을 가리키는 링크 수, 값 목록 밖 줄 수
② 비슷한 사례 날: 원본 시각(``payload->>'occurred_at'``)과 줄 쓴 때를 가른 집계 ③ ``supersedes`` 반영의 앞 항목 유효 끝 ·
고리 막기(단계마다 질의). ``FOMS_TEST_DATABASE_URL`` 이 없으면 건너뛴다. 합성 항목 · 꾸민 수만.
"""

from __future__ import annotations

import datetime

import pytest

from foms.services.brain.apply import apply_change
from foms.services.brain.errors import BrainLinkRuleError
from foms.services.brain.inbox import similar_cases
from foms.services.brain.proposals import Proposer, propose_link, propose_retire
from foms.services.brain.quality import off_list_counts, quality_counts
from foms.services.brain.scope import viewer_of
from foms.services.brain.store import current_object
from tests.support.brain_support import NOW, REASON, create, link, person

TODAY = datetime.date(2026, 11, 2)
DOC = {"approved_by": "합성", "approved_at": "2026-10-20"}


def _price(session, admin, key, basis=None):
    payload = {"doc_id": key.split("/")[-1], **DOC, **({"basis": basis} if basis else {})}
    create(session, admin, key, item_type="price_rule", name="합성 값 규칙", checked_at="2026-10-20",
           visibility="price", payload=payload)


def test_quality_counts_split_by_basis_on_postgres(pg_session):
    admin = person(pg_session, "pg129_admin")
    _price(pg_session, admin, "common/a", "calc")
    _price(pg_session, admin, "common/b", "calc")
    _price(pg_session, admin, "common/c")
    link(pg_session, admin, "value_from", "common/a", "calc:product/1")
    create(pg_session, admin, "common/fit", item_type="build_rule", name="합성 조건")
    create(pg_session, admin, "common/door", name="합성 문짝")
    link(pg_session, admin, "applies_to", "common/fit", "common/door")
    retire = propose_retire(pg_session, key="common/door", base_version=1, reason=REASON,
                            proposer=Proposer.user(admin.id), now=NOW)
    apply_change(pg_session, retire.id, actor=admin, now=NOW)
    counts = quality_counts(pg_session, viewer_of(admin), today=TODAY)
    rows = {r["basis"]: r for r in counts["rules"] if r["type"] == "price_rule"}
    assert (rows["calc"]["items"], rows["calc"]["missing"]) == (2, 1)
    assert (rows[""]["items"], rows[""]["missing"], rows["brain"]["items"]) == (1, 0, 0)
    assert counts["retired_links"] == 1 and off_list_counts(pg_session) == {
        "item_type": 0, "brand": 0, "status": 0, "kind": 0}


def test_similar_case_days_use_the_source_time_on_postgres(pg_session):
    admin = person(pg_session, "pg129_admin")
    create(pg_session, admin, "common/door", name="합성 문짝")
    create(pg_session, admin, "obs/a", item_type="case", name="합성 사례",
           payload={"occurred_at": "2026-09-30T23:30:00+00:00"})
    create(pg_session, admin, "obs/b", item_type="photo_observation", name="합성 사진 관찰")
    for key in ("obs/a", "obs/b"):
        link(pg_session, admin, "evidence_of", key, "common/door")
    found = similar_cases(pg_session, viewer_of(admin), ["common/door"])["common/door"]
    assert found == {"count": 2, "first": "2026-10-01", "last": "2026-11-02"}


def test_supersedes_end_and_cycle_on_postgres(pg_session):
    admin = person(pg_session, "pg129_admin")
    for key, no, start in (("common/d1", "D1", "2026-11-20"), ("common/d2", "D2", None)):
        create(pg_session, admin, key, item_type="owner_decision", name="합성 결정", valid_from=start,
               payload={"doc_id": key.split("/")[-1], **DOC, "decision_no": no})
    create(pg_session, admin, "common/old", item_type="term", name="합성 옛 말")
    link(pg_session, admin, "supersedes", "common/d1", "common/old")
    assert current_object(pg_session, "common/old").valid_to == datetime.date(2026, 11, 19)
    link(pg_session, admin, "supersedes", "common/d1", "common/d2")
    with pytest.raises(BrainLinkRuleError):
        propose_link(pg_session, op="link_add", kind="supersedes", from_key="common/d2", to_key="common/d1",
                     reason=REASON, proposer=Proposer.user(admin.id), now=NOW)
