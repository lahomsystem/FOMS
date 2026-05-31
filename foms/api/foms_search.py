"""Unified ERP mobile search API (P1-02)."""

from __future__ import annotations

from typing import Any

from flask import Blueprint, jsonify, render_template, request

from db import get_db
from foms.services.foms_unified_search import SearchGroup, search_unified
from foms.web.auth import login_required

foms_search_bp = Blueprint("foms_search", __name__, url_prefix="/api/foms")


@foms_search_bp.route("/search", methods=["GET"])
@login_required
def api_foms_search() -> tuple[Any, int]:
    """
    JSON autocomplete for mobile search overlay.

    Query params: ``q``, optional ``group`` (all|customer|order|drawing).
    """
    query = (request.args.get("q") or "").strip()
    group = (request.args.get("group") or "all").strip().lower()
    if group not in {"all", "customer", "order", "drawing"}:
        group = "all"

    db = get_db()
    data = search_unified(db, query, group=group)  # type: ignore[arg-type]
    return jsonify({"success": True, "data": data}), 200


@foms_search_bp.route("/search/fragment", methods=["GET"])
@login_required
def api_foms_search_fragment() -> str:
    """HTML fragment for HTMX-style delayed autocomplete (200ms)."""
    query = (request.args.get("q") or "").strip()
    group = (request.args.get("group") or "all").strip().lower()
    if group not in {"all", "customer", "order", "drawing"}:
        group = "all"

    db = get_db()
    data = search_unified(db, query, group=group)  # type: ignore[arg-type]
    return render_template(
        "partials/shared/foms_search_results_partial.html",
        results=data,
        active_group=group,
        query=query,
    )
