"""디버그용 blueprint (라우트 없음).

OPS-ROUTE-01 / P0-18: 무인증 ``/debug-db`` 가 DB schema·table name·User count·env
존재 여부를 노출하고 실패 시 raw exception/traceback 까지 반환하던 진단 라우트를
제거했다. 이 blueprint 는 어디에도 등록되지 않으며(=deployed registration 0),
심볼(``debug_bp``)만 namespace surface 계약(tests/contracts/runtime)을 위해 유지한다.

진단이 다시 필요하면 무인증 public 이 아니라 ADMIN 세션 게이트 뒤에서
``Cache-Control: private, no-store`` 로만 노출할 것(무인증 public 복구 금지).
"""
from flask import Blueprint

debug_bp = Blueprint('debug', __name__)
