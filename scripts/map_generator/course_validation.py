"""Validation and signature helpers for stage-aware open-course generation."""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

from scripts.map_generator.opendrive_writer import RoadGeometrySegment, _advance_pose

if TYPE_CHECKING:
    from scripts.map_generator.course_composer import OpenCourseComposition


def _line_length_bucket(length_m: float) -> str:
    if length_m < 8.0:
        return "xs"
    if length_m < 18.0:
        return "s"
    if length_m < 40.0:
        return "m"
    if length_m < 80.0:
        return "l"
    return "xl"


def _arc_intensity_bucket(curvature: float) -> str:
    absolute_curvature = abs(curvature)
    if absolute_curvature >= 0.10:
        return "xt"
    if absolute_curvature >= 0.065:
        return "t"
    if absolute_curvature >= 0.035:
        return "m"
    return "w"


def _arc_angle_bucket(segment: RoadGeometrySegment) -> str:
    turn_angle_deg = abs(math.degrees(segment.length * segment.curvature))
    if turn_angle_deg >= 62.0:
        return "3"
    if turn_angle_deg >= 34.0:
        return "2"
    return "1"


def _segment_signature_token(segment: RoadGeometrySegment) -> str:
    if segment.geometry_type == "line":
        return f"L{_line_length_bucket(segment.length)}"
    direction_token = "CL" if segment.curvature > 0 else "CR"
    return f"{direction_token}{_arc_intensity_bucket(segment.curvature)}{_arc_angle_bucket(segment)}"


def build_layout_signature(segments: list[RoadGeometrySegment]) -> str:
    """Return a compact sequence signature for one concrete layout."""

    return "-".join(_segment_signature_token(segment) for segment in segments)


def _sample_centerline_points(
    segments: list[RoadGeometrySegment],
    *,
    sample_spacing_m: float = 4.0,
) -> list[tuple[float, float, float]]:
    """Sample one layout centerline as (s, x, y) tuples."""

    points: list[tuple[float, float, float]] = [(0.0, 0.0, 0.0)]
    current_s = 0.0
    current_x = 0.0
    current_y = 0.0
    current_heading = 0.0

    for segment in segments:
        segment_length = max(segment.length, 1e-6)
        step_count = max(1, int(math.ceil(segment_length / sample_spacing_m)))
        step_length = segment_length / step_count
        step_segment = RoadGeometrySegment(
            geometry_type=segment.geometry_type,
            length=step_length,
            curvature=segment.curvature,
        )

        for _ in range(step_count):
            current_x, current_y, current_heading = _advance_pose(
                current_x,
                current_y,
                current_heading,
                step_segment,
            )
            current_s += step_length
            points.append((current_s, current_x, current_y))

    return points


def _measure_minimum_nonlocal_clearance(
    segments: list[RoadGeometrySegment],
    *,
    lane_width_m: float,
    layout_stage_index: int,
) -> dict[str, object]:
    """Measure minimum distance between non-adjacent centerline samples."""

    points = _sample_centerline_points(segments)
    road_surface_width_m = lane_width_m * 2.0
    local_exclusion_s_m = max(road_surface_width_m * 2.6, 28.0)
    technical_tolerance_m = min(1.5, max(0.0, layout_stage_index - 1) * 0.45)
    minimum_clearance_required_m = max(
        road_surface_width_m + 1.6 - technical_tolerance_m,
        road_surface_width_m * 1.08,
        9.5,
    )

    minimum_clearance_m = float("inf")
    closest_pair: tuple[tuple[float, float, float], tuple[float, float, float]] | None = None

    for point_index, point in enumerate(points):
        point_s, point_x, point_y = point
        for other_point in points[point_index + 1 :]:
            other_s, other_x, other_y = other_point
            if (other_s - point_s) < local_exclusion_s_m:
                continue

            dx = other_x - point_x
            dy = other_y - point_y
            clearance_m = math.hypot(dx, dy)
            if clearance_m < minimum_clearance_m:
                minimum_clearance_m = clearance_m
                closest_pair = (point, other_point)

    if not math.isfinite(minimum_clearance_m):
        minimum_clearance_m = composition_length = sum(segment.length for segment in segments)
        closest_pair = ((0.0, 0.0, 0.0), (composition_length, 0.0, 0.0))

    closest_pair_payload = None
    if closest_pair is not None:
        first_point, second_point = closest_pair
        closest_pair_payload = {
            "first": {
                "s": first_point[0],
                "x": first_point[1],
                "y": first_point[2],
            },
            "second": {
                "s": second_point[0],
                "x": second_point[1],
                "y": second_point[2],
            },
            "delta_s_m": abs(second_point[0] - first_point[0]),
        }

    return {
        "minimum_nonlocal_clearance_m": minimum_clearance_m,
        "minimum_clearance_required_m": minimum_clearance_required_m,
        "clearance_ok": minimum_clearance_m >= minimum_clearance_required_m,
        "local_exclusion_s_m": local_exclusion_s_m,
        "closest_nonlocal_pair": closest_pair_payload,
    }


def validate_open_course_composition(composition: "OpenCourseComposition") -> dict[str, object]:
    """Validate one open-course composition and return manifest-friendly metadata."""

    segments = composition.segments
    line_lengths = [
        segment.length
        for segment in segments
        if segment.geometry_type == "line"
    ]
    first_line_length = line_lengths[0] if line_lengths else 0.0
    last_line_length = line_lengths[-1] if line_lengths else 0.0
    internal_recovery_length_m = sum(line_lengths[1:-1]) if len(line_lengths) >= 3 else 0.0
    actual_recovery_ratio = (
        internal_recovery_length_m / composition.actual_total_length_m
        if composition.actual_total_length_m > 1e-6
        else 0.0
    )

    difficulty_stage = composition.profile.difficulty_stage
    layout_stage = composition.profile.layout_stage
    length_band = difficulty_stage.target_total_length_band_m
    curve_band = layout_stage.target_curve_count_band
    reversal_band = difficulty_stage.target_direction_reversal_band

    total_length_in_band = length_band[0] <= composition.actual_total_length_m <= length_band[1]
    curve_count_in_band = curve_band[0] <= composition.actual_curve_count <= curve_band[1]
    reversal_count_in_band = (
        reversal_band[0] <= composition.direction_reversal_count <= reversal_band[1]
    )
    recovery_ratio_band = difficulty_stage.target_recovery_ratio_band
    recovery_ratio_in_band = (
        (recovery_ratio_band[0] - 0.03)
        <= actual_recovery_ratio
        <= (recovery_ratio_band[1] + 0.05)
    )
    spawn_zone_stable = first_line_length >= 24.0
    finish_zone_stable = last_line_length >= 28.0
    signature = build_layout_signature(segments)
    clearance_metrics = _measure_minimum_nonlocal_clearance(
        segments,
        lane_width_m=4.5,
        layout_stage_index=layout_stage.index,
    )
    clearance_ok = bool(clearance_metrics["clearance_ok"])

    passed = (
        total_length_in_band
        and curve_count_in_band
        and reversal_count_in_band
        and recovery_ratio_in_band
        and spawn_zone_stable
        and finish_zone_stable
        and clearance_ok
    )

    return {
        "validation_passed": passed,
        "layout_signature": signature,
        "length_bucket_20m": int(round(composition.actual_total_length_m / 20.0)),
        "curve_count_bucket": composition.actual_curve_count,
        "direction_reversal_bucket": composition.direction_reversal_count,
        "internal_recovery_length_m": internal_recovery_length_m,
        "actual_recovery_ratio": actual_recovery_ratio,
        "minimum_nonlocal_clearance_m": clearance_metrics["minimum_nonlocal_clearance_m"],
        "minimum_clearance_required_m": clearance_metrics["minimum_clearance_required_m"],
        "local_exclusion_s_m": clearance_metrics["local_exclusion_s_m"],
        "closest_nonlocal_pair": clearance_metrics["closest_nonlocal_pair"],
        "checks": {
            "total_length_in_stage_band": total_length_in_band,
            "curve_count_in_layout_band": curve_count_in_band,
            "direction_reversal_in_stage_band": reversal_count_in_band,
            "recovery_ratio_in_stage_band": recovery_ratio_in_band,
            "spawn_zone_stable": spawn_zone_stable,
            "finish_zone_stable": finish_zone_stable,
            "minimum_nonlocal_clearance_ok": clearance_ok,
        },
        "bands": {
            "target_total_length_band_m": list(length_band),
            "target_curve_count_band": list(curve_band),
            "target_direction_reversal_band": list(reversal_band),
            "target_recovery_ratio_band": list(recovery_ratio_band),
        },
    }
