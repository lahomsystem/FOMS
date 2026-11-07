"""Canonical admin API package anchor."""

from foms.api.admin.cs_agent import cs_agent_admin_api_bp
from foms.api.admin.sales_freelancers import sales_freelancers_admin_api_bp

__all__: list[str] = ["cs_agent_admin_api_bp", "sales_freelancers_admin_api_bp"]
