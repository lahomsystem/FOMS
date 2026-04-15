"""importlib helpers for namespace retirement contract tests."""

import importlib.util


def find_spec_or_none(name: str):
    """Like ``importlib.util.find_spec``, but return ``None`` if a parent package is missing.

    For nested names (e.g. ``apps.api.orders``), CPython may raise ``ModuleNotFoundError``
    when ``apps.api`` is absent, instead of returning ``None``.
    """
    try:
        return importlib.util.find_spec(name)
    except ModuleNotFoundError:
        return None
