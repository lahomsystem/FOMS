"""H-01 — 정산 창 술어 COALESCE 식 인덱스 2종의 정적 계약 (naversettle_02, 2026-09-06).

DB 없이 잡는 것(CFO 감사 H-01, 백로그 3차 설계서 §2):

1. 리비전이 ``naversettle_01`` 위에 얹히고 ``models`` 를 import 하지 않는다(상수 동결).
2. alembic head 가 정확히 ``naversettle_02`` 하나다(이중 head 는 운영 predeploy 를 죽인다).
3. 모델 ``__table_args__`` 의 인덱스 2개가 ``(channel, coalesce(settle_expect_date, search_date))``
   로 컴파일된다 — create_all 베이스라인(PG 레인 왕복·신규 부트스트랩)이 같은 스키마를 만든다.
4. 커널 술어(``_case_scope``·``_commission_scope``)가 **같은 인자 순서**의 coalesce 로 컴파일된다.
   PG 플래너는 표현식 트리가 정확히 일치할 때만 식 인덱스를 고르므로, 누가 순서를 바꾸면
   인덱스를 못 타는 회귀를 여기서 잡는다(커널은 읽기만 한다 — BE-A 소유).
5. 리비전의 ``AXIS_EXPR`` 리터럴이 모델 식과 대소문자 무관 같고, 인덱스 이름 2개가 모델과 같다.

실제 DDL 왕복은 ``tests/postgres/test_migration_chain.py``(head 기준 창이라 자동 편입)가 맡는다.
"""

from __future__ import annotations

import datetime
import importlib.util
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex

from foms.services.settlement_channel import _case_scope, _commission_scope
from models import NaverSettleCase, NaverSettleCommission

_REPO_ROOT = Path(__file__).resolve().parents[2]
_MIGRATION_PATH = _REPO_ROOT / "migrations" / "versions" / "naversettle_02_expect_axis_index.py"

#: 모델 인덱스 이름 → 표 이름. 리비전 상수와 같아야 한다(테스트 5).
_INDEX_TABLES = {
    "ix_nsc_channel_expect_axis": NaverSettleCase.__table__,
    "ix_nscm_channel_expect_axis": NaverSettleCommission.__table__,
}
#: 인덱스 둘째 열 — 커널 술어와 인자 순서까지 같은 식(소문자 = PG 컴파일 결과).
_AXIS_LOWER = "coalesce(settle_expect_date, search_date)"


def _load_migration():
    """리비전 모듈을 파일 경로로 읽는다(alembic 로더와 이름이 겹치지 않게 별도 이름)."""
    spec = importlib.util.spec_from_file_location("naversettle_02_mig_unit", _MIGRATION_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _index_by_name(table, name: str):
    """표의 ``indexes`` 집합에서 이름으로 하나를 찾는다(없으면 AssertionError)."""
    found = [ix for ix in table.indexes if ix.name == name]
    assert len(found) == 1, f"{table.name}: {name} 인덱스 {len(found)}개 — {sorted(i.name for i in table.indexes)}"
    return found[0]


def test_revision_chains_onto_naversettle_01_without_importing_models() -> None:
    """리비전 헤더 + 상수 동결(models import 0)."""
    module = _load_migration()
    assert module.revision == "naversettle_02"
    assert module.down_revision == "naversettle_01"
    source = _MIGRATION_PATH.read_text(encoding="utf-8")
    assert "import models" not in source and "from models" not in source, (
        "마이그레이션이 models 를 import 한다 — 상수 동결 원칙 위반")


def test_naversettle_02_stays_on_the_head_chain() -> None:
    """naversettle_02 가 head 로 이어지는 체인 위에 남아 있다(끊기거나 갈라지지 않았다).

    head 이름을 문자열로 박아두면 뒤에 붙는 모든 마이그레이션이 이 테스트를 깬다 —
    실제로 그랬다(2026-09-10 ``mgrroom_00``). 이 테스트가 지키려는 것은 "이 리비전이
    적용 경로 위에 있다" 이고, head 가 하나라는 계약은
    ``tests/domains/test_alembic_single_head.py`` 가 따로 소유한다.
    """
    script = ScriptDirectory.from_config(Config(str(_REPO_ROOT / "alembic.ini")))
    heads = script.get_heads()
    assert heads, "alembic head 가 없다"
    chain = {rev.revision for rev in script.walk_revisions("base", heads[0])}
    assert "naversettle_02" in chain, (
        f"naversettle_02 가 head({heads[0]}) 체인에서 빠졌다 — 적용되지 않는 리비전이다")


def test_model_indexes_compile_to_the_channel_coalesce_expression() -> None:
    """두 모델의 식 인덱스가 ``(channel, coalesce(settle_expect_date, search_date))`` 로 끝난다."""
    for name, table in _INDEX_TABLES.items():
        ddl = str(CreateIndex(_index_by_name(table, name)).compile(dialect=postgresql.dialect()))
        assert ddl.startswith(f"CREATE INDEX {name} ON {table.name} "), ddl
        assert ddl.endswith(f"(channel, {_AXIS_LOWER})"), ddl


def test_kernel_window_predicate_matches_the_index_expression_literally() -> None:
    """커널 술어의 coalesce 인자 순서 = 인덱스 식(settle_expect_date 먼저, search_date 다음)."""
    d1, d2 = datetime.date(2026, 8, 1), datetime.date(2026, 8, 31)
    for scope, table in ((_case_scope, "naver_settle_case"), (_commission_scope, "naver_settle_commission")):
        lower = str(scope("NAVER", d1, d2)[1].compile(dialect=postgresql.dialect()))
        assert lower.startswith(f"coalesce({table}.settle_expect_date, {table}.search_date) >="), lower


def test_migration_index_expression_equals_the_model_expression_case_insensitively() -> None:
    """리비전 리터럴(식·이름 2개)이 모델 선언과 같다 — 한쪽만 고치면 여기서 red."""
    module = _load_migration()
    assert module.AXIS_EXPR.lower() == _AXIS_LOWER
    assert module.IX_CASE_AXIS in {ix.name for ix in NaverSettleCase.__table__.indexes}
    assert module.IX_COMMISSION_AXIS in {ix.name for ix in NaverSettleCommission.__table__.indexes}
    assert (module.T_SETTLE_CASE, module.T_SETTLE_COMMISSION) == (
        NaverSettleCase.__tablename__, NaverSettleCommission.__tablename__)
