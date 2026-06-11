"""Shared scoring helpers used by evaluation, HUD feedback, and auto-generation."""

from __future__ import annotations

import math
from typing import Iterable


def clamp_unit_interval(value: float) -> float:
    """Clamp one floating-point value to the inclusive 0.0-1.0 range."""

    return max(0.0, min(1.0, float(value)))


def resolve_path_tracking_scale(
    *,
    path_tolerance_m: float,
    road_half_width_m: float,
    offroad_margin_m: float,
) -> float:
    """Return the lateral-error scale used for the softer practical path score."""

    if path_tolerance_m <= 0:
        raise ValueError("path_tolerance_m must be greater than 0")
    if road_half_width_m <= 0:
        raise ValueError("road_half_width_m must be greater than 0")
    if offroad_margin_m < 0:
        raise ValueError("offroad_margin_m must be greater than or equal to 0")

    road_limit_m = road_half_width_m + offroad_margin_m
    return max(
        path_tolerance_m * 1.8,
        road_limit_m * 0.60,
        path_tolerance_m + 0.75,
    )


def compute_path_tracking_sample_score(
    lateral_error_m: float,
    *,
    path_tolerance_m: float,
    road_half_width_m: float,
    offroad_margin_m: float,
) -> float:
    """Convert one lateral error into a soft 0.0-1.0 tracking score."""

    scale_m = resolve_path_tracking_scale(
        path_tolerance_m=path_tolerance_m,
        road_half_width_m=road_half_width_m,
        offroad_margin_m=offroad_margin_m,
    )
    normalized_error = max(0.0, float(lateral_error_m)) / max(scale_m, 1e-9)
    return 1.0 / (1.0 + (normalized_error * normalized_error))


def compute_path_tracking_score(
    lateral_errors_m: Iterable[float],
    *,
    path_tolerance_m: float,
    road_half_width_m: float,
    offroad_margin_m: float,
) -> float:
    """Average soft path scores across one evaluated trajectory."""

    errors = [max(0.0, float(error_m)) for error_m in lateral_errors_m]
    if not errors:
        return 0.0

    total_score = sum(
        compute_path_tracking_sample_score(
            error_m,
            path_tolerance_m=path_tolerance_m,
            road_half_width_m=road_half_width_m,
            offroad_margin_m=offroad_margin_m,
        )
        for error_m in errors
    )
    return clamp_unit_interval(total_score / len(errors))


def resolve_lane_discipline_scale(
    *,
    lane_half_width_m: float,
    path_tolerance_m: float,
) -> float:
    """Return the lateral-error scale used for stricter lane-discipline scoring."""

    if lane_half_width_m <= 0:
        raise ValueError("lane_half_width_m must be greater than 0")
    if path_tolerance_m <= 0:
        raise ValueError("path_tolerance_m must be greater than 0")

    return max(
        0.75,
        lane_half_width_m * 0.72,
        path_tolerance_m * 0.80,
    )


def compute_lane_discipline_sample_score(
    lateral_error_m: float,
    *,
    lane_half_width_m: float,
    path_tolerance_m: float,
) -> float:
    """Convert one lane-center error into a stricter 0.0-1.0 lane-discipline score."""

    scale_m = resolve_lane_discipline_scale(
        lane_half_width_m=lane_half_width_m,
        path_tolerance_m=path_tolerance_m,
    )
    normalized_error = max(0.0, float(lateral_error_m)) / max(scale_m, 1e-9)
    return 1.0 / (1.0 + (normalized_error * normalized_error))


def compute_lane_discipline_score(
    lateral_errors_m: Iterable[float],
    *,
    lane_half_width_m: float,
    path_tolerance_m: float,
) -> float:
    """Average stricter lane-discipline scores across one evaluated trajectory."""

    errors = [max(0.0, float(error_m)) for error_m in lateral_errors_m]
    if not errors:
        return 0.0

    total_score = sum(
        compute_lane_discipline_sample_score(
            error_m,
            lane_half_width_m=lane_half_width_m,
            path_tolerance_m=path_tolerance_m,
        )
        for error_m in errors
    )
    return clamp_unit_interval(total_score / len(errors))


def approximate_path_tracking_score(
    *,
    path_match_score: float,
    mean_lateral_error_m: float,
    max_lateral_error_m: float,
    path_tolerance_m: float,
    road_half_width_m: float,
    offroad_margin_m: float,
) -> float:
    """Approximate the soft path score from stored summary fields."""

    mean_component = compute_path_tracking_sample_score(
        mean_lateral_error_m,
        path_tolerance_m=path_tolerance_m,
        road_half_width_m=road_half_width_m,
        offroad_margin_m=offroad_margin_m,
    )
    max_component = compute_path_tracking_sample_score(
        max(0.0, float(max_lateral_error_m)) / 1.35,
        path_tolerance_m=path_tolerance_m,
        road_half_width_m=road_half_width_m,
        offroad_margin_m=offroad_margin_m,
    )
    return clamp_unit_interval(
        (0.55 * mean_component)
        + (0.20 * max_component)
        + (0.25 * clamp_unit_interval(path_match_score))
    )


def compute_driving_score(
    *,
    completion_ratio: float,
    path_tracking_score: float,
    crossed_finish_line: bool,
    offroad_ratio: float,
    collision_count: int,
    failure_reason: str | None,
    success: bool,
    lane_discipline_score: float = 1.0,
    lane_departure_ratio: float = 0.0,
    opposite_lane_ratio: float = 0.0,
) -> float:
    """Convert one evaluated episode into the practical 0.0-1.0 driving score."""

    score = (
        (0.45 * clamp_unit_interval(completion_ratio))
        + (0.35 * clamp_unit_interval(path_tracking_score))
        + (0.20 if crossed_finish_line else 0.0)
    )

    if offroad_ratio > 0:
        score *= max(0.10, 1.0 - (0.85 * offroad_ratio))

    if lane_discipline_score < 0.999:
        score *= max(
            0.35,
            0.40 + (0.60 * clamp_unit_interval(lane_discipline_score)),
        )

    if lane_departure_ratio > 0:
        score *= max(0.20, 1.0 - (0.80 * clamp_unit_interval(lane_departure_ratio)))

    if opposite_lane_ratio > 0:
        score *= max(0.10, 1.0 - (1.20 * clamp_unit_interval(opposite_lane_ratio)))

    if collision_count > 0:
        score *= 0.20
    elif failure_reason == "course_departure":
        score *= 0.55
    elif failure_reason == "not_finished":
        score *= 0.75

    if success:
        score = max(score, 0.82)

    return clamp_unit_interval(score)
