"""Helpers for choosing practical evaluation targets from road lane layout."""

from __future__ import annotations

ROAD_CENTER_CORRIDOR = "road_center_corridor"
LANE_CENTER_GUIDANCE = "lane_center_guidance"


def resolve_evaluation_target_mode(lanes_per_direction: int) -> str:
    """Resolve the practical target mode for the current lane layout."""

    if int(lanes_per_direction) <= 1:
        return ROAD_CENTER_CORRIDOR
    return LANE_CENTER_GUIDANCE


def uses_road_center_target(mode: str) -> bool:
    """Return whether the practical target should use the road center path."""

    return str(mode).strip() == ROAD_CENTER_CORRIDOR
