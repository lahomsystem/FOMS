"""FOMS Brain PG-L3 — Product Archetype Types.

Defines known and candidate product archetypes beyond the base 4 types.

Base types (always available, have full factories):
  wardrobe / shoe_rack / kitchen_base / kitchen_wall

Extended archetypes (learned from approved design cases):
  무몰딩장      no_molding_wardrobe
  리폼장        reform_wardrobe
  내장고장      refrigerator_cabinet
  TV/거실장     tv_unit
  화장실장      bathroom_cabinet
  복합 수납      combined_storage
  드레스룸      dressroom
  상하분할장    split_wardrobe
  주방 상하복합  kitchen_combined
  신발장+행거    shoetrack_hanger
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ──────────────────────────────────────────────────────────
# Known extended archetypes
# ──────────────────────────────────────────────────────────

KNOWN_EXTENDED_ARCHETYPES: dict[str, dict[str, Any]] = {
    "no_molding_wardrobe": {
        "label_ko": "무몰딩 붙박이장",
        "base_type": "wardrobe",
        "tags": ["no_molding"],
        "description": "상단 몰딩 없는 붙박이장. 천장 밀착형.",
    },
    "reform_wardrobe": {
        "label_ko": "리폼 붙박이장",
        "base_type": "wardrobe",
        "tags": ["reform", "existing_furniture"],
        "description": "기존 가구 포함 리폼 도면.",
    },
    "refrigerator_cabinet": {
        "label_ko": "내장고장",
        "base_type": "custom_storage",
        "tags": ["refrigerator", "built_in"],
        "description": "냉장고 내장형 수납장.",
    },
    "tv_unit": {
        "label_ko": "TV/거실장",
        "base_type": "custom_storage",
        "tags": ["tv", "living_room"],
        "description": "TV 매립 거실 수납장.",
    },
    "bathroom_cabinet": {
        "label_ko": "화장실장",
        "base_type": "custom_storage",
        "tags": ["bathroom", "moisture_resistant"],
        "description": "방습/방수 처리 화장실 수납장.",
    },
    "combined_storage": {
        "label_ko": "복합 수납",
        "base_type": "custom_storage",
        "tags": ["combined", "multi_purpose"],
        "description": "복합 목적 수납 가구.",
    },
    "dressroom": {
        "label_ko": "드레스룸",
        "base_type": "wardrobe",
        "tags": ["dressroom", "walk_in"],
        "description": "워크인 드레스룸 구성.",
    },
    "split_wardrobe": {
        "label_ko": "상하분할장",
        "base_type": "wardrobe",
        "tags": ["split", "upper_lower"],
        "description": "상부/하부 분리 구성 붙박이장.",
    },
    "kitchen_combined": {
        "label_ko": "주방 상하부 복합",
        "base_type": "kitchen_base",
        "tags": ["kitchen", "combined", "upper_lower"],
        "description": "주방 상부+하부장 복합 도면.",
    },
    "shoetrack_hanger": {
        "label_ko": "신발장+행거",
        "base_type": "shoe_rack",
        "tags": ["shoe_rack", "hanger", "entry"],
        "description": "현관 신발장+행거 복합형.",
    },
}

ALL_ARCHETYPE_KEYS = frozenset(KNOWN_EXTENDED_ARCHETYPES.keys())


@dataclass
class ProductArchetypeCandidate:
    """Candidate for a new product archetype.

    Created by product_archetype_learning.py from repeated approved cases.
    Requires min 3 supporting cases and human approval before becoming
    a registered archetype or factory.
    """

    key: str
    label_ko: str
    base_type: str                          # closest base factory type
    supporting_case_ids: list[int]          # DesignerDesignCase IDs
    tag_pattern: list[str]                  # extracted tag pattern
    sample_options: dict[str, Any]          # representative options
    evidence_count: int = 0
    confidence: float = 0.0
    auto_generated: bool = True             # human review required
    approved: bool = False                  # human must approve
    approved_by_user_id: int | None = None

    def can_promote(self) -> bool:
        return (
            self.approved
            and self.evidence_count >= 3
            and not self.auto_generated
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label_ko": self.label_ko,
            "base_type": self.base_type,
            "supporting_case_ids": self.supporting_case_ids,
            "tag_pattern": self.tag_pattern,
            "sample_options": self.sample_options,
            "evidence_count": self.evidence_count,
            "confidence": self.confidence,
            "auto_generated": self.auto_generated,
            "approved": self.approved,
            "can_promote": self.can_promote(),
        }
