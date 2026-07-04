"""Designer API write guards.

The wdplanner-v2 React app runs in a same-origin iframe.  Mutating designer
endpoints require a custom same-origin header so a cross-site form POST cannot
reuse the user's session cookies silently.

실제 검증 로직은 `foms.services.request_write_guard` 공용 팩토리에 있다. 여기서는
designer 전용 헤더(`X-FOMS-Designer-Write`)로 바인딩만 한다.
"""

from __future__ import annotations

from typing import Callable, TypeVar

from foms.services.request_write_guard import require_same_origin_write

F = TypeVar("F", bound=Callable[..., object])

_WRITE_HEADER = "X-FOMS-Designer-Write"

require_designer_write: Callable[[F], F] = require_same_origin_write(_WRITE_HEADER)
"""Require same-origin write proof for mutating designer API calls."""
