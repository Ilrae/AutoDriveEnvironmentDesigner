"""Shared track-start and finish-line metadata rules for generated maps."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import math
from typing import Any

from scripts.map_generator.opendrive_writer import StraightRoadConfig


@dataclass(frozen=True)
class SpawnPointContract:
    """Application-owned spawn-point contract stored with generated maps."""

    distance_along_start_m: float = 8.0
    lane_side: str = "right"
    lane_index: int = 1
    lateral_offset_m: float = 0.0
    yaw_offset_deg: float = 0.0


@dataclass(frozen=True)
class FinishLineContract:
    """Application-owned finish-line contract stored with generated maps."""

    distance_before_end_m: float = 1.0
    lane_side: str = "right"
    lane_index: int = 1
    lateral_offset_m: float = 0.0
    half_width_m: float = 6.0


def build_default_spawn_contract(
    traffic_side: str = "right",
) -> SpawnPointContract:
    """Return the default application-wide spawn contract."""

    normalized_traffic_side = str(traffic_side).strip().lower()
    lane_side = "left" if normalized_traffic_side == "left" else "right"
    return SpawnPointContract(lane_side=lane_side)


def build_default_finish_line_contract(
    traffic_side: str = "right",
) -> FinishLineContract:
    """Return the default application-wide finish-line contract."""

    normalized_traffic_side = str(traffic_side).strip().lower()
    lane_side = "left" if normalized_traffic_side == "left" else "right"
    return FinishLineContract(lane_side=lane_side)


def resolve_spawn_metadata(
    config: StraightRoadConfig,
    contract: SpawnPointContract | None = None,
) -> dict[str, Any]:
    """Resolve one explicit spawn point from the generated road start pose."""

    active_contract = contract or build_default_spawn_contract()
    heading = config.heading_rad
    right_normal_heading = heading + (math.pi / 2.0)
    lane_center_offset = (active_contract.lane_index - 0.5) * config.lane_width
    if active_contract.lane_side == "right":
        lane_center_offset *= 1.0
    elif active_contract.lane_side == "left":
        lane_center_offset *= -1.0
    else:
        raise ValueError("lane_side must be either 'left' or 'right'")

    lateral_offset = lane_center_offset + active_contract.lateral_offset_m
    resolved_x = (
        config.start_x
        + (active_contract.distance_along_start_m * math.cos(heading))
        + (lateral_offset * math.cos(right_normal_heading))
    )
    resolved_y = (
        config.start_y
        + (active_contract.distance_along_start_m * math.sin(heading))
        + (lateral_offset * math.sin(right_normal_heading))
    )

    metadata = asdict(active_contract)
    metadata.update(
        {
            "resolved_x": resolved_x,
            "resolved_y": resolved_y,
            "resolved_heading_rad": heading,
            "resolved_yaw_deg": math.degrees(heading) + active_contract.yaw_offset_deg,
        }
    )
    return metadata


def serialize_finish_line_contract(
    contract: FinishLineContract | None = None,
    config: StraightRoadConfig | None = None,
) -> dict[str, Any]:
    """Return one finish-line contract anchored to the generated course end."""

    active_contract = contract or build_default_finish_line_contract()
    payload = asdict(active_contract)
    if config is None:
        return payload

    resolved_lane_id = -active_contract.lane_index
    if active_contract.lane_side == "left":
        resolved_lane_id = active_contract.lane_index
    elif active_contract.lane_side != "right":
        raise ValueError("lane_side must be either 'left' or 'right'")

    finish_line_progress_s = max(0.0, config.total_length - active_contract.distance_before_end_m)
    resolved_half_width_m = (
        active_contract.half_width_m
        if active_contract.half_width_m > 0
        else config.lane_width * config.lanes_per_direction
    )
    payload.update(
        {
            "placement_mode": "course_end",
            "resolved_road_id": config.road_id,
            "resolved_lane_id": resolved_lane_id,
            "resolved_s": finish_line_progress_s,
            "resolved_half_width_m": resolved_half_width_m,
        }
    )
    return payload
