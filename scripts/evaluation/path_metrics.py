"""Path sampling and scoring helpers for manual and automated drive evaluation."""

from __future__ import annotations

from dataclasses import dataclass
import math
from typing import Iterable

from scripts.map_generator.opendrive_writer import (
    RoadGeometrySegment,
    StraightRoadConfig,
    _advance_pose,
)
from scripts.evaluation.scoring import (
    compute_lane_discipline_score,
    compute_path_tracking_score,
)


@dataclass(frozen=True)
class PathPoint:
    """One sampled point on a reference or target path."""

    x: float
    y: float
    s: float
    heading_rad: float


@dataclass(frozen=True)
class TrajectorySample:
    """One recorded vehicle state used for path evaluation."""

    timestamp_sec: float
    x: float
    y: float
    z: float
    speed_kmh: float


@dataclass(frozen=True)
class PathProjection:
    """Projection of one point onto a sampled path."""

    distance_m: float
    progress_s: float
    progress_ratio: float
    closest_x: float
    closest_y: float


@dataclass(frozen=True)
class FinishLine:
    """Explicit finish line used for completion checks."""

    x: float
    y: float
    s: float
    heading_rad: float
    half_width_m: float


@dataclass(frozen=True)
class PathEvaluationSummary:
    """Aggregated path-tracking metrics for one episode."""

    sample_count: int
    mean_lateral_error_m: float
    max_lateral_error_m: float
    path_match_score: float
    path_tracking_score: float
    lane_discipline_score: float
    completion_ratio: float
    crossed_finish_line: bool
    offroad_ratio: float
    offroad_sample_count: int
    lane_departure_ratio: float
    lane_departure_sample_count: int
    opposite_lane_ratio: float
    opposite_lane_sample_count: int
    finish_line_remaining_m: float


def resolve_lane_center_offset(
    lane_width: float,
    lane_side: str,
    lane_index: int = 1,
    lateral_offset_m: float = 0.0,
) -> float:
    """Resolve a signed lane-center offset from the OpenDRIVE reference line."""

    if lane_index <= 0:
        raise ValueError("lane_index must be greater than or equal to 1")

    base_offset = (lane_index - 0.5) * lane_width
    if lane_side == "right":
        signed_offset = base_offset
    elif lane_side == "left":
        signed_offset = -base_offset
    else:
        raise ValueError("lane_side must be 'left' or 'right'")

    return signed_offset + lateral_offset_m


def sample_path_from_config(
    config: StraightRoadConfig,
    *,
    sample_step_m: float = 1.0,
    lane_side: str | None = None,
    lane_index: int = 1,
    lateral_offset_m: float = 0.0,
) -> list[PathPoint]:
    """Sample a reference path or one driving-lane center path from the config."""

    if sample_step_m <= 0:
        raise ValueError("sample_step_m must be greater than 0")

    signed_offset = 0.0
    if lane_side is not None:
        signed_offset = resolve_lane_center_offset(
            lane_width=config.lane_width,
            lane_side=lane_side,
            lane_index=lane_index,
            lateral_offset_m=lateral_offset_m,
        )

    def _offset_point(x: float, y: float, heading_rad: float) -> tuple[float, float]:
        right_normal_heading = heading_rad + (math.pi / 2.0)
        return (
            x + (signed_offset * math.cos(right_normal_heading)),
            y + (signed_offset * math.sin(right_normal_heading)),
        )

    current_x = config.start_x
    current_y = config.start_y
    current_heading = config.heading_rad
    cumulative_s = 0.0

    offset_x, offset_y = _offset_point(current_x, current_y, current_heading)
    points = [PathPoint(x=offset_x, y=offset_y, s=0.0, heading_rad=current_heading)]

    for segment in config.build_segments():
        remaining_length = segment.length
        while remaining_length > 1e-9:
            step_length = min(sample_step_m, remaining_length)
            step_segment = RoadGeometrySegment(
                geometry_type=segment.geometry_type,
                length=step_length,
                curvature=segment.curvature,
            )
            current_x, current_y, current_heading = _advance_pose(
                current_x,
                current_y,
                current_heading,
                step_segment,
            )
            cumulative_s += step_length
            offset_x, offset_y = _offset_point(current_x, current_y, current_heading)
            points.append(
                PathPoint(
                    x=offset_x,
                    y=offset_y,
                    s=cumulative_s,
                    heading_rad=current_heading,
                )
            )
            remaining_length -= step_length

    return points


def project_point_to_path(
    x: float,
    y: float,
    path_points: Iterable[PathPoint],
) -> PathProjection:
    """Project a 2D point onto a sampled polyline path."""

    points = list(path_points)
    if not points:
        raise ValueError("path_points must contain at least one point")

    if len(points) == 1:
        only = points[0]
        distance_m = math.hypot(x - only.x, y - only.y)
        return PathProjection(
            distance_m=distance_m,
            progress_s=0.0,
            progress_ratio=0.0,
            closest_x=only.x,
            closest_y=only.y,
        )

    total_length = max(points[-1].s, 1e-9)
    best_distance = float("inf")
    best_progress_s = 0.0
    best_x = points[0].x
    best_y = points[0].y

    for start, end in zip(points[:-1], points[1:]):
        delta_x = end.x - start.x
        delta_y = end.y - start.y
        segment_length_sq = (delta_x * delta_x) + (delta_y * delta_y)
        if segment_length_sq <= 1e-12:
            projection_ratio = 0.0
        else:
            projection_ratio = (
                ((x - start.x) * delta_x) + ((y - start.y) * delta_y)
            ) / segment_length_sq
            projection_ratio = max(0.0, min(1.0, projection_ratio))

        projected_x = start.x + (projection_ratio * delta_x)
        projected_y = start.y + (projection_ratio * delta_y)
        distance_m = math.hypot(x - projected_x, y - projected_y)
        if distance_m < best_distance:
            segment_length = math.sqrt(segment_length_sq)
            best_distance = distance_m
            best_x = projected_x
            best_y = projected_y
            best_progress_s = start.s + (projection_ratio * segment_length)

    return PathProjection(
        distance_m=best_distance,
        progress_s=best_progress_s,
        progress_ratio=max(0.0, min(1.0, best_progress_s / total_length)),
        closest_x=best_x,
        closest_y=best_y,
    )


def interpolate_path_point(
    path_points: Iterable[PathPoint],
    progress_s: float,
) -> PathPoint:
    """Interpolate one path point at the requested distance along the path."""

    points = list(path_points)
    if not points:
        raise ValueError("path_points must contain at least one point")

    if progress_s <= points[0].s:
        return points[0]
    if progress_s >= points[-1].s:
        return points[-1]

    for start, end in zip(points[:-1], points[1:]):
        if start.s <= progress_s <= end.s:
            delta_s = end.s - start.s
            if delta_s <= 1e-9:
                return start
            ratio = (progress_s - start.s) / delta_s
            return PathPoint(
                x=start.x + ((end.x - start.x) * ratio),
                y=start.y + ((end.y - start.y) * ratio),
                s=progress_s,
                heading_rad=start.heading_rad + ((end.heading_rad - start.heading_rad) * ratio),
            )

    return points[-1]


def _signed_lateral_offset_to_path(
    sample_x: float,
    sample_y: float,
    projection: PathProjection,
    path_points: Iterable[PathPoint],
) -> float:
    """Return the signed lateral offset from one sampled path."""

    reference_point = interpolate_path_point(path_points, projection.progress_s)
    right_normal_heading = reference_point.heading_rad + (math.pi / 2.0)
    return (
        ((sample_x - projection.closest_x) * math.cos(right_normal_heading))
        + ((sample_y - projection.closest_y) * math.sin(right_normal_heading))
    )


def evaluate_trajectory_against_paths(
    trajectory_samples: Iterable[TrajectorySample],
    *,
    target_path: Iterable[PathPoint],
    road_reference_path: Iterable[PathPoint],
    raw_target_path: Iterable[PathPoint] | None = None,
    road_half_width_m: float,
    finish_line: FinishLine | None = None,
    path_tolerance_m: float = 1.5,
    offroad_margin_m: float = 0.25,
    lane_half_width_m: float | None = None,
    lane_guidance_active: bool = False,
) -> PathEvaluationSummary:
    """Evaluate a recorded trajectory against an ideal path and road bounds."""

    if road_half_width_m <= 0:
        raise ValueError("road_half_width_m must be greater than 0")
    if path_tolerance_m <= 0:
        raise ValueError("path_tolerance_m must be greater than 0")
    if offroad_margin_m < 0:
        raise ValueError("offroad_margin_m must be greater than or equal to 0")
    if lane_half_width_m is not None and lane_half_width_m <= 0:
        raise ValueError("lane_half_width_m must be greater than 0 when provided")
    target_points = list(target_path)
    road_points = list(road_reference_path)
    raw_target_points = list(raw_target_path) if raw_target_path is not None else target_points
    samples = list(trajectory_samples)
    if not target_points or not road_points or not raw_target_points:
        raise ValueError("target_path, raw_target_path, and road_reference_path must not be empty")

    active_finish_line = finish_line or FinishLine(
        x=target_points[-1].x,
        y=target_points[-1].y,
        s=target_points[-1].s,
        heading_rad=target_points[-1].heading_rad,
        half_width_m=road_half_width_m + offroad_margin_m,
    )

    if not samples:
        finish_line_remaining_m = max(0.0, active_finish_line.s - target_points[0].s)
        return PathEvaluationSummary(
            sample_count=0,
            mean_lateral_error_m=0.0,
            max_lateral_error_m=0.0,
            path_match_score=0.0,
            path_tracking_score=0.0,
            lane_discipline_score=1.0,
            completion_ratio=0.0,
            crossed_finish_line=False,
            offroad_ratio=0.0,
            offroad_sample_count=0,
            lane_departure_ratio=0.0,
            lane_departure_sample_count=0,
            opposite_lane_ratio=0.0,
            opposite_lane_sample_count=0,
            finish_line_remaining_m=finish_line_remaining_m,
        )

    offroad_threshold = road_half_width_m + offroad_margin_m
    projection_records: list[
        tuple[TrajectorySample, PathProjection, PathProjection, PathProjection]
    ] = []
    crossed_finish_index: int | None = None

    for index, sample in enumerate(samples):
        target_projection = project_point_to_path(sample.x, sample.y, target_points)
        road_projection = project_point_to_path(sample.x, sample.y, road_points)
        raw_projection = project_point_to_path(sample.x, sample.y, raw_target_points)
        projection_records.append((sample, target_projection, road_projection, raw_projection))
        if (
            crossed_finish_index is None
            and target_projection.progress_s >= active_finish_line.s
            and road_projection.distance_m <= offroad_threshold
        ):
            crossed_finish_index = index

    crossed_finish_line = crossed_finish_index is not None
    evaluation_records = projection_records
    if crossed_finish_index is not None:
        evaluation_records = projection_records[: crossed_finish_index + 1]

    lateral_errors: list[float] = []
    within_tolerance_count = 0
    offroad_count = 0
    lane_departure_count = 0
    opposite_lane_count = 0
    max_progress_ratio = 0.0
    max_progress_s = 0.0
    effective_lane_half_width_m = (
        float(lane_half_width_m)
        if lane_half_width_m is not None
        else max(path_tolerance_m, road_half_width_m * 0.5)
    )
    lane_departure_threshold_m = effective_lane_half_width_m
    opposite_lane_threshold_m = max(0.25, effective_lane_half_width_m * 0.22)

    for sample, target_projection, road_projection, raw_projection in evaluation_records:
        lateral_errors.append(target_projection.distance_m)
        if raw_projection.distance_m <= path_tolerance_m:
            within_tolerance_count += 1
        if road_projection.distance_m > offroad_threshold:
            offroad_count += 1
        if lane_guidance_active:
            if target_projection.distance_m > lane_departure_threshold_m:
                lane_departure_count += 1
            sample_signed_offset_m = _signed_lateral_offset_to_path(
                sample.x,
                sample.y,
                road_projection,
                road_points,
            )
            road_reference_point = interpolate_path_point(
                road_points,
                road_projection.progress_s,
            )
            target_reference_point = interpolate_path_point(
                target_points,
                road_projection.progress_s,
            )
            right_normal_heading = road_reference_point.heading_rad + (math.pi / 2.0)
            expected_signed_offset_m = (
                ((target_reference_point.x - road_reference_point.x) * math.cos(right_normal_heading))
                + ((target_reference_point.y - road_reference_point.y) * math.sin(right_normal_heading))
            )
            if (
                abs(expected_signed_offset_m) > 1e-6
                and abs(sample_signed_offset_m) > opposite_lane_threshold_m
                and (sample_signed_offset_m * expected_signed_offset_m) < 0.0
            ):
                opposite_lane_count += 1
        max_progress_ratio = max(max_progress_ratio, target_projection.progress_ratio)
        max_progress_s = max(max_progress_s, target_projection.progress_s)

    sample_count = len(evaluation_records)
    mean_lateral_error_m = sum(lateral_errors) / sample_count
    max_lateral_error_m = max(lateral_errors)
    path_match_score = within_tolerance_count / sample_count
    path_tracking_score = compute_path_tracking_score(
        lateral_errors,
        path_tolerance_m=path_tolerance_m,
        road_half_width_m=road_half_width_m,
        offroad_margin_m=offroad_margin_m,
    )
    lane_discipline_score = (
        compute_lane_discipline_score(
            lateral_errors,
            lane_half_width_m=effective_lane_half_width_m,
            path_tolerance_m=path_tolerance_m,
        )
        if lane_guidance_active
        else 1.0
    )
    offroad_ratio = offroad_count / sample_count
    lane_departure_ratio = lane_departure_count / sample_count
    opposite_lane_ratio = opposite_lane_count / sample_count
    finish_line_remaining_m = max(0.0, active_finish_line.s - max_progress_s)

    return PathEvaluationSummary(
        sample_count=sample_count,
        mean_lateral_error_m=mean_lateral_error_m,
        max_lateral_error_m=max_lateral_error_m,
        path_match_score=path_match_score,
        path_tracking_score=path_tracking_score,
        lane_discipline_score=lane_discipline_score,
        completion_ratio=max_progress_ratio,
        crossed_finish_line=crossed_finish_line,
        offroad_ratio=offroad_ratio,
        offroad_sample_count=offroad_count,
        lane_departure_ratio=lane_departure_ratio,
        lane_departure_sample_count=lane_departure_count,
        opposite_lane_ratio=opposite_lane_ratio,
        opposite_lane_sample_count=opposite_lane_count,
        finish_line_remaining_m=finish_line_remaining_m,
    )
