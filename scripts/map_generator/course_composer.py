"""Stage-aware open-course segment composition helpers."""

from __future__ import annotations

from dataclasses import dataclass
import math

from scripts.curriculum.difficulty_controller import clamp_level
from scripts.map_generator.course_stages import (
    COURSE_STAGE_DEFINITIONS,
    CourseStageDefinition,
    resolve_adaptive_variant,
    resolve_course_stage,
    resolve_stage_for_variant,
)
from scripts.map_generator.opendrive_writer import RoadGeometrySegment


@dataclass(frozen=True)
class OpenCourseComposerProfile:
    """Resolved composition profile for one generated open course."""

    level: float
    variant: str
    curve_direction: str
    direction_sign: float
    layout_seed_key: str
    difficulty_stage: CourseStageDefinition
    layout_stage: CourseStageDefinition
    target_total_length_m: float
    target_curve_count: int
    target_direction_reversals: int
    recovery_length_budget_m: float
    curvature_scale: float
    turn_angle_boost_rad: float
    entry_length: float
    exit_length: float
    mid_length: float
    reset_length: float
    micro_reset_length: float
    wide_radius: float
    medium_radius: float
    tight_radius: float
    apex_radius: float
    setup_angle_rad: float
    main_angle_rad: float
    support_angle_rad: float
    reversal_angle_rad: float


@dataclass(frozen=True)
class OpenCourseComposition:
    """One fully composed open-course layout."""

    segments: list[RoadGeometrySegment]
    profile: OpenCourseComposerProfile
    actual_total_length_m: float
    actual_curve_count: int
    actual_line_count: int
    direction_reversal_count: int


def _interpolate(min_value: float, max_value: float, ratio: float) -> float:
    normalized_ratio = max(0.0, min(1.0, ratio))
    return min_value + ((max_value - min_value) * normalized_ratio)


def _layout_value(layout_seed_key: str, channel: str) -> float:
    token = f"{layout_seed_key}:{channel}"
    accumulator = 0
    for index, character in enumerate(token):
        accumulator = (accumulator + ((index + 1) * ord(character))) % 104729
    return (accumulator % 1000) / 999.0


def _radians_with_jitter(
    minimum_deg: float,
    maximum_deg: float,
    *,
    ratio: float,
    layout_seed_key: str,
    channel: str,
    extra_deg: float,
) -> float:
    return math.radians(
        _interpolate(minimum_deg, maximum_deg, ratio)
        + _interpolate(0.0, extra_deg, _layout_value(layout_seed_key, channel))
    )


def _resolve_stage_progress(level: float, stage_definition: CourseStageDefinition) -> float:
    stage_span = max(1e-9, stage_definition.max_level_exclusive - stage_definition.min_level)
    return max(0.0, min(1.0, (level - stage_definition.min_level) / stage_span))


def _build_open_course_profile(
    level: float,
    curve_direction: str,
    *,
    requested_variant: str,
    layout_seed_key: str,
) -> OpenCourseComposerProfile:
    normalized_level = clamp_level(level)
    variant = (
        requested_variant
        if requested_variant != "adaptive"
        else resolve_adaptive_variant(normalized_level)
    )
    difficulty_stage = resolve_course_stage(normalized_level)
    layout_stage = resolve_stage_for_variant(variant) or difficulty_stage
    direction_sign = 1.0 if curve_direction == "left" else -1.0
    stage_progress = _resolve_stage_progress(normalized_level, difficulty_stage)
    layout_stage_ratio = layout_stage.index / max(1, len(COURSE_STAGE_DEFINITIONS) - 1)

    band_min, band_max = difficulty_stage.target_total_length_band_m
    length_ratio = (
        0.25
        + (0.30 * stage_progress)
        + (0.45 * _layout_value(layout_seed_key, "target_length"))
    )
    target_total_length_m = _interpolate(band_min, band_max, length_ratio)

    curve_count_min, curve_count_max = layout_stage.target_curve_count_band
    curve_count_ratio = (
        0.20
        + (0.45 * stage_progress)
        + (0.35 * _layout_value(layout_seed_key, "curve_count"))
    )
    target_curve_count = int(round(_interpolate(curve_count_min, curve_count_max, curve_count_ratio)))
    target_curve_count = max(curve_count_min, min(curve_count_max, target_curve_count))

    reversal_min, reversal_max = difficulty_stage.target_direction_reversal_band
    reversal_ratio = (
        0.10
        + (0.40 * stage_progress)
        + (0.50 * _layout_value(layout_seed_key, "reversal_count"))
    )
    target_direction_reversals = int(
        round(_interpolate(reversal_min, reversal_max, reversal_ratio))
    )
    target_direction_reversals = max(
        reversal_min,
        min(reversal_max, target_direction_reversals),
    )

    recovery_ratio_min, recovery_ratio_max = difficulty_stage.target_recovery_ratio_band
    recovery_ratio = _interpolate(
        recovery_ratio_min,
        recovery_ratio_max,
        _layout_value(layout_seed_key, "recovery_ratio"),
    )
    recovery_length_budget_m = target_total_length_m * recovery_ratio

    entry_length = max(
        28.0,
        (target_total_length_m * _interpolate(0.20, 0.11, layout_stage_ratio))
        + _interpolate(0.0, 12.0, _layout_value(layout_seed_key, "entry")),
    )
    exit_length = max(
        36.0,
        (target_total_length_m * _interpolate(0.28, 0.14, layout_stage_ratio))
        + _interpolate(0.0, 18.0, _layout_value(layout_seed_key, "exit")),
    )
    mid_length = max(
        8.0,
        (recovery_length_budget_m * _interpolate(0.42, 0.26, layout_stage_ratio))
        + _interpolate(0.0, 8.0, _layout_value(layout_seed_key, "mid")),
    )
    reset_length = max(
        4.0,
        (recovery_length_budget_m * _interpolate(0.22, 0.14, layout_stage_ratio))
        + _interpolate(0.0, 5.0, _layout_value(layout_seed_key, "reset")),
    )
    micro_reset_length = max(
        3.0,
        (recovery_length_budget_m * _interpolate(0.12, 0.08, layout_stage_ratio))
        + _interpolate(0.0, 3.0, _layout_value(layout_seed_key, "micro_reset")),
    )

    curvature_scale = _interpolate(
        difficulty_stage.curvature_scale_band[0],
        difficulty_stage.curvature_scale_band[1],
        (0.35 * stage_progress) + (0.65 * _layout_value(layout_seed_key, "curvature_scale")),
    )
    wide_radius = max(
        18.0,
        (
            _interpolate(78.0, 34.0, normalized_level)
            - _interpolate(0.0, 12.0, _layout_value(layout_seed_key, "wide_radius"))
        )
        / curvature_scale,
    )
    medium_radius = max(
        13.0,
        (
            _interpolate(54.0, 20.0, normalized_level)
            - _interpolate(0.0, 10.0, _layout_value(layout_seed_key, "medium_radius"))
        )
        / curvature_scale,
    )
    tight_radius = max(
        8.0,
        (
            _interpolate(30.0, 10.0, normalized_level)
            - _interpolate(0.0, 6.0, _layout_value(layout_seed_key, "tight_radius"))
        )
        / curvature_scale,
    )
    apex_radius = max(
        7.0,
        (
            _interpolate(20.0, 8.0, normalized_level)
            - _interpolate(0.0, 4.0, _layout_value(layout_seed_key, "apex_radius"))
        )
        / curvature_scale,
    )

    angle_ratio = max(stage_progress, normalized_level)
    turn_angle_boost_rad = math.radians(
        _interpolate(
            difficulty_stage.turn_angle_boost_band_deg[0],
            difficulty_stage.turn_angle_boost_band_deg[1],
            (0.40 * stage_progress) + (0.60 * _layout_value(layout_seed_key, "angle_boost")),
        )
    )
    setup_angle_rad = _radians_with_jitter(
        10.0,
        24.0,
        ratio=angle_ratio,
        layout_seed_key=layout_seed_key,
        channel="setup_angle",
        extra_deg=8.0,
    ) + (turn_angle_boost_rad * 0.30)
    main_angle_rad = _radians_with_jitter(
        34.0,
        74.0,
        ratio=angle_ratio,
        layout_seed_key=layout_seed_key,
        channel="main_angle",
        extra_deg=22.0,
    ) + turn_angle_boost_rad
    support_angle_rad = _radians_with_jitter(
        16.0,
        44.0,
        ratio=angle_ratio,
        layout_seed_key=layout_seed_key,
        channel="support_angle",
        extra_deg=18.0,
    ) + (turn_angle_boost_rad * 0.70)
    reversal_angle_rad = _radians_with_jitter(
        14.0,
        40.0,
        ratio=angle_ratio,
        layout_seed_key=layout_seed_key,
        channel="reversal_angle",
        extra_deg=16.0,
    ) + (turn_angle_boost_rad * 0.80)

    return OpenCourseComposerProfile(
        level=normalized_level,
        variant=variant,
        curve_direction=curve_direction,
        direction_sign=direction_sign,
        layout_seed_key=layout_seed_key,
        difficulty_stage=difficulty_stage,
        layout_stage=layout_stage,
        target_total_length_m=target_total_length_m,
        target_curve_count=target_curve_count,
        target_direction_reversals=target_direction_reversals,
        recovery_length_budget_m=recovery_length_budget_m,
        curvature_scale=curvature_scale,
        turn_angle_boost_rad=turn_angle_boost_rad,
        entry_length=entry_length,
        exit_length=exit_length,
        mid_length=mid_length,
        reset_length=reset_length,
        micro_reset_length=micro_reset_length,
        wide_radius=wide_radius,
        medium_radius=medium_radius,
        tight_radius=tight_radius,
        apex_radius=apex_radius,
        setup_angle_rad=setup_angle_rad,
        main_angle_rad=main_angle_rad,
        support_angle_rad=support_angle_rad,
        reversal_angle_rad=reversal_angle_rad,
    )


def _arc(radius_m: float, angle_rad: float, curvature_sign: float) -> RoadGeometrySegment:
    return RoadGeometrySegment("arc", radius_m * angle_rad, curvature_sign / radius_m)


def _line(length_m: float) -> RoadGeometrySegment:
    return RoadGeometrySegment("line", length_m)


def _curve_count(segments: list[RoadGeometrySegment]) -> int:
    return sum(1 for segment in segments if segment.geometry_type == "arc")


def _line_floor(
    profile: OpenCourseComposerProfile,
    segments: list[RoadGeometrySegment],
    segment_index: int,
) -> float:
    if segment_index == 0:
        return max(26.0, profile.entry_length * 0.65)
    if segment_index == len(segments) - 1:
        return max(32.0, profile.exit_length * 0.55)
    if segment_index >= len(segments) - 3:
        return max(5.0, profile.micro_reset_length * 0.70)
    return 4.0


def _line_weight(segments: list[RoadGeometrySegment], segment_index: int) -> float:
    if segment_index == 0:
        return 2.6
    if segment_index == len(segments) - 1:
        return 2.2
    if segment_index >= len(segments) - 3:
        return 1.4
    return 1.0


def _rebalance_line_lengths(
    profile: OpenCourseComposerProfile,
    segments: list[RoadGeometrySegment],
) -> list[RoadGeometrySegment]:
    updated_segments = [
        RoadGeometrySegment(segment.geometry_type, segment.length, segment.curvature)
        for segment in segments
    ]
    length_delta = profile.target_total_length_m - sum(segment.length for segment in updated_segments)
    if abs(length_delta) < 0.5:
        return updated_segments

    line_indices = [
        index
        for index, segment in enumerate(updated_segments)
        if segment.geometry_type == "line"
    ]
    if not line_indices:
        return updated_segments

    if length_delta > 0.0:
        total_weight = sum(_line_weight(updated_segments, index) for index in line_indices)
        for offset, index in enumerate(line_indices):
            line_weight = _line_weight(updated_segments, index)
            share = length_delta * (line_weight / total_weight)
            if offset == len(line_indices) - 1:
                share = length_delta - sum(
                    updated_segments[line_index].length - segments[line_index].length
                    for line_index in line_indices[:-1]
                )
            updated_segments[index].length += share
        return updated_segments

    removable_lengths = {
        index: max(
            0.0,
            updated_segments[index].length - _line_floor(profile, updated_segments, index),
        )
        for index in line_indices
    }
    removable_total = sum(removable_lengths.values())
    if removable_total <= 1e-6:
        return updated_segments

    reduction_total = min(-length_delta, removable_total)
    for offset, index in enumerate(line_indices):
        removable_length = removable_lengths[index]
        if removable_length <= 0.0:
            continue
        share = reduction_total * (removable_length / removable_total)
        if offset == len(line_indices) - 1:
            share = reduction_total - sum(
                segments[line_index].length - updated_segments[line_index].length
                for line_index in line_indices[:-1]
            )
        updated_segments[index].length -= min(share, removable_length)
    return updated_segments


def _align_recovery_budget(
    profile: OpenCourseComposerProfile,
    segments: list[RoadGeometrySegment],
) -> list[RoadGeometrySegment]:
    updated_segments = [
        RoadGeometrySegment(segment.geometry_type, segment.length, segment.curvature)
        for segment in segments
    ]
    internal_line_indices = [
        index
        for index, segment in enumerate(updated_segments)
        if segment.geometry_type == "line" and 0 < index < len(updated_segments) - 1
    ]
    if not internal_line_indices:
        return updated_segments

    actual_internal_recovery = sum(
        updated_segments[index].length for index in internal_line_indices
    )
    target_internal_recovery = profile.recovery_length_budget_m
    if actual_internal_recovery <= target_internal_recovery + 2.0:
        return updated_segments

    removable_lengths = {
        index: max(
            0.0,
            updated_segments[index].length - _line_floor(profile, updated_segments, index),
        )
        for index in internal_line_indices
    }
    removable_total = sum(removable_lengths.values())
    if removable_total <= 1e-6:
        return updated_segments

    reduction_total = min(actual_internal_recovery - target_internal_recovery, removable_total)
    reduction_applied = 0.0
    active_indices = [index for index in internal_line_indices if removable_lengths[index] > 0.0]
    for offset, index in enumerate(active_indices):
        removable_length = removable_lengths[index]
        share = reduction_total * (removable_length / removable_total)
        if offset == len(active_indices) - 1:
            share = reduction_total - reduction_applied
        applied = min(share, removable_length)
        updated_segments[index].length -= applied
        reduction_applied += applied

    terminal_line_indices = [
        index
        for index, segment in enumerate(updated_segments)
        if segment.geometry_type == "line" and index in {0, len(updated_segments) - 1}
    ]
    if terminal_line_indices and reduction_applied > 1e-6:
        total_terminal_weight = sum(
            1.6 if index == len(updated_segments) - 1 else 1.0
            for index in terminal_line_indices
        )
        redistributed = 0.0
        for offset, index in enumerate(terminal_line_indices):
            weight = 1.6 if index == len(updated_segments) - 1 else 1.0
            share = reduction_applied * (weight / total_terminal_weight)
            if offset == len(terminal_line_indices) - 1:
                share = reduction_applied - redistributed
            updated_segments[index].length += share
            redistributed += share

    return updated_segments


def _insert_before_terminal_line(
    segments: list[RoadGeometrySegment],
    insertion: list[RoadGeometrySegment],
) -> list[RoadGeometrySegment]:
    if not insertion:
        return list(segments)
    if segments and segments[-1].geometry_type == "line":
        return [*segments[:-1], *insertion, segments[-1]]
    return [*segments, *insertion]


def _build_density_motif(
    profile: OpenCourseComposerProfile,
    *,
    motif_index: int,
    arcs_needed: int,
    current_reversal_count: int,
) -> list[RoadGeometrySegment]:
    motif_ratio = _layout_value(profile.layout_seed_key, f"density_motif_{motif_index}")
    prefer_reversal = current_reversal_count < profile.target_direction_reversals
    first_sign = profile.direction_sign if motif_index % 2 == 0 else -profile.direction_sign
    second_sign = -first_sign if prefer_reversal else first_sign
    lead_in_length = max(
        4.0,
        profile.micro_reset_length * _interpolate(0.75, 1.10, motif_ratio),
    )
    bridge_length = max(
        4.0,
        profile.micro_reset_length * _interpolate(0.70, 1.00, 1.0 - motif_ratio),
    )
    first_radius = max(
        8.5,
        profile.medium_radius * _interpolate(0.92, 1.08, motif_ratio),
    )
    second_radius = max(
        7.5,
        (
            profile.tight_radius if prefer_reversal else profile.medium_radius
        ) * _interpolate(0.88, 1.02, 1.0 - motif_ratio),
    )
    first_angle = max(
        math.radians(14.0),
        profile.support_angle_rad * _interpolate(0.55, 0.82, motif_ratio),
    )
    second_angle = max(
        math.radians(18.0),
        profile.main_angle_rad * _interpolate(0.45, 0.72, motif_ratio),
    )

    motif = [
        _line(lead_in_length),
        _arc(first_radius, first_angle, first_sign),
    ]
    if arcs_needed <= 1:
        return motif

    motif.extend(
        [
            _line(bridge_length),
            _arc(second_radius, second_angle, second_sign),
        ]
    )
    return motif


def _augment_curve_density(
    profile: OpenCourseComposerProfile,
    segments: list[RoadGeometrySegment],
) -> list[RoadGeometrySegment]:
    augmented_segments = list(segments)
    motif_index = 0
    while _curve_count(augmented_segments) < profile.target_curve_count and motif_index < 6:
        arcs_needed = profile.target_curve_count - _curve_count(augmented_segments)
        motif = _build_density_motif(
            profile,
            motif_index=motif_index,
            arcs_needed=arcs_needed,
            current_reversal_count=_count_direction_reversals(augmented_segments),
        )
        augmented_segments = _insert_before_terminal_line(augmented_segments, motif)
        motif_index += 1
    return augmented_segments


def _compose_single_turn(profile: OpenCourseComposerProfile) -> list[RoadGeometrySegment]:
    setup_radius = profile.wide_radius + 10.0
    main_radius = profile.medium_radius
    return [
        _line(profile.entry_length),
        _arc(setup_radius, profile.setup_angle_rad, -profile.direction_sign),
        _line(profile.reset_length),
        _arc(main_radius, profile.main_angle_rad, profile.direction_sign),
        _line(profile.exit_length),
    ]


def _compose_gentle_chicane(profile: OpenCourseComposerProfile) -> list[RoadGeometrySegment]:
    first_radius = profile.wide_radius
    second_radius = profile.wide_radius + 6.0
    third_radius = profile.medium_radius + 4.0
    return [
        _line(profile.entry_length + 6.0),
        _arc(first_radius, profile.reversal_angle_rad, profile.direction_sign),
        _line(profile.reset_length),
        _arc(second_radius, profile.reversal_angle_rad, -profile.direction_sign),
        _line(max(18.0, profile.mid_length)),
        _arc(third_radius, profile.support_angle_rad, profile.direction_sign),
        _line(profile.exit_length + 4.0),
    ]


def _compose_offset_bend(profile: OpenCourseComposerProfile) -> list[RoadGeometrySegment]:
    setup_radius = profile.wide_radius
    main_radius = profile.medium_radius
    unwind_radius = profile.wide_radius + 4.0
    return [
        _line(profile.entry_length + 4.0),
        _arc(setup_radius, profile.setup_angle_rad, -profile.direction_sign),
        _line(max(12.0, profile.reset_length)),
        _arc(main_radius, profile.main_angle_rad + profile.support_angle_rad, profile.direction_sign),
        _line(max(10.0, profile.micro_reset_length)),
        _arc(unwind_radius, profile.setup_angle_rad, -profile.direction_sign),
        _line(profile.exit_length),
    ]


def _compose_s_curve(profile: OpenCourseComposerProfile) -> list[RoadGeometrySegment]:
    first_radius = profile.medium_radius + 4.0
    second_radius = profile.medium_radius
    third_radius = profile.wide_radius
    return [
        _line(profile.entry_length),
        _arc(first_radius, profile.main_angle_rad, profile.direction_sign),
        _line(profile.mid_length),
        _arc(second_radius, profile.main_angle_rad, -profile.direction_sign),
        _line(max(12.0, profile.reset_length)),
        _arc(third_radius, profile.support_angle_rad, profile.direction_sign),
        _line(profile.exit_length + 6.0),
    ]


def _compose_compound_turn(profile: OpenCourseComposerProfile) -> list[RoadGeometrySegment]:
    opening_radius = profile.medium_radius
    apex_radius = profile.tight_radius
    exit_radius = max(18.0, profile.medium_radius - 6.0)
    return [
        _line(max(28.0, profile.entry_length - 6.0)),
        _arc(opening_radius, profile.support_angle_rad, profile.direction_sign),
        _line(max(10.0, profile.reset_length * 0.85)),
        _arc(apex_radius, profile.main_angle_rad, profile.direction_sign),
        _line(max(8.0, profile.micro_reset_length)),
        _arc(exit_radius, profile.support_angle_rad, profile.direction_sign),
        _line(max(42.0, profile.exit_length - 8.0)),
    ]


def _compose_switchback(profile: OpenCourseComposerProfile) -> list[RoadGeometrySegment]:
    first_radius = profile.medium_radius
    second_radius = profile.tight_radius
    third_radius = profile.medium_radius
    fourth_radius = profile.wide_radius
    return [
        _line(max(26.0, profile.entry_length - 4.0)),
        _arc(first_radius, profile.support_angle_rad, profile.direction_sign),
        _line(max(8.0, profile.micro_reset_length)),
        _arc(second_radius, profile.main_angle_rad, -profile.direction_sign),
        _line(max(8.0, profile.reset_length * 0.75)),
        _arc(third_radius, profile.main_angle_rad, profile.direction_sign),
        _line(max(10.0, profile.reset_length)),
        _arc(fourth_radius, profile.support_angle_rad, -profile.direction_sign),
        _line(max(38.0, profile.exit_length - 4.0)),
    ]


def _compose_double_apex(profile: OpenCourseComposerProfile) -> list[RoadGeometrySegment]:
    first_radius = max(16.0, profile.medium_radius - 8.0)
    second_radius = profile.tight_radius
    third_radius = profile.apex_radius
    fourth_radius = max(18.0, profile.medium_radius - 4.0)
    return [
        _line(max(26.0, profile.entry_length - 10.0)),
        _arc(first_radius, profile.support_angle_rad, profile.direction_sign),
        _line(max(8.0, profile.reset_length * 0.70)),
        _arc(second_radius, profile.main_angle_rad, profile.direction_sign),
        _line(max(6.0, profile.micro_reset_length)),
        _arc(third_radius, profile.support_angle_rad, profile.direction_sign),
        _line(max(8.0, profile.reset_length * 0.60)),
        _arc(fourth_radius, profile.reversal_angle_rad, -profile.direction_sign),
        _line(max(48.0, profile.exit_length)),
    ]


def _compose_snake_run(profile: OpenCourseComposerProfile) -> list[RoadGeometrySegment]:
    first_radius = profile.medium_radius
    second_radius = profile.tight_radius
    third_radius = max(8.0, profile.apex_radius)
    fourth_radius = profile.tight_radius
    fifth_radius = profile.medium_radius
    return [
        _line(max(24.0, profile.entry_length - 12.0)),
        _arc(first_radius, profile.support_angle_rad, profile.direction_sign),
        _line(max(6.0, profile.micro_reset_length)),
        _arc(second_radius, profile.main_angle_rad, -profile.direction_sign),
        _line(max(5.0, profile.micro_reset_length * 0.90)),
        _arc(third_radius, profile.support_angle_rad, profile.direction_sign),
        _line(max(5.0, profile.micro_reset_length * 0.80)),
        _arc(fourth_radius, profile.main_angle_rad, -profile.direction_sign),
        _line(max(6.0, profile.micro_reset_length)),
        _arc(fifth_radius, profile.support_angle_rad, profile.direction_sign),
        _line(max(34.0, profile.exit_length - 8.0)),
    ]


def _compose_segments_for_variant(profile: OpenCourseComposerProfile) -> list[RoadGeometrySegment]:
    if profile.variant == "single_turn":
        return _compose_single_turn(profile)
    if profile.variant == "gentle_chicane":
        return _compose_gentle_chicane(profile)
    if profile.variant == "offset_bend":
        return _compose_offset_bend(profile)
    if profile.variant == "s_curve":
        return _compose_s_curve(profile)
    if profile.variant == "compound_turn":
        return _compose_compound_turn(profile)
    if profile.variant == "switchback":
        return _compose_switchback(profile)
    if profile.variant == "double_apex":
        return _compose_double_apex(profile)
    if profile.variant == "snake_run":
        return _compose_snake_run(profile)
    raise ValueError(
        "requested_variant must be one of 'adaptive', 'single_turn', "
        "'gentle_chicane', 'offset_bend', 's_curve', 'compound_turn', "
        "'switchback', 'double_apex', or 'snake_run'"
    )


def _count_direction_reversals(segments: list[RoadGeometrySegment]) -> int:
    previous_sign = 0
    reversal_count = 0
    for segment in segments:
        if segment.geometry_type != "arc":
            continue
        current_sign = 1 if segment.curvature > 0 else -1
        if previous_sign != 0 and current_sign != previous_sign:
            reversal_count += 1
        previous_sign = current_sign
    return reversal_count


def build_open_course_composition(
    level: float,
    curve_direction: str,
    *,
    requested_variant: str = "adaptive",
    layout_seed_key: str = "default_layout",
) -> OpenCourseComposition:
    """Compose one stage-aware open-course layout."""

    profile = _build_open_course_profile(
        level,
        curve_direction,
        requested_variant=requested_variant,
        layout_seed_key=layout_seed_key,
    )
    base_segments = _compose_segments_for_variant(profile)
    segments = _augment_curve_density(profile, base_segments)
    segments = _rebalance_line_lengths(profile, segments)
    segments = _align_recovery_budget(profile, segments)
    actual_total_length_m = sum(segment.length for segment in segments)
    actual_curve_count = sum(1 for segment in segments if segment.geometry_type == "arc")
    actual_line_count = sum(1 for segment in segments if segment.geometry_type == "line")
    return OpenCourseComposition(
        segments=segments,
        profile=profile,
        actual_total_length_m=actual_total_length_m,
        actual_curve_count=actual_curve_count,
        actual_line_count=actual_line_count,
        direction_reversal_count=_count_direction_reversals(segments),
    )


def build_open_course_manifest_metadata(composition: OpenCourseComposition) -> dict[str, object]:
    """Return compact composer metadata for manifest/debugging use."""

    return {
        "layout_seed_key": composition.profile.layout_seed_key,
        "difficulty_stage_id": composition.profile.difficulty_stage.stage_id,
        "layout_stage_id": composition.profile.layout_stage.stage_id,
        "target_total_length_m": composition.profile.target_total_length_m,
        "target_curve_count": composition.profile.target_curve_count,
        "target_direction_reversals": composition.profile.target_direction_reversals,
        "recovery_length_budget_m": composition.profile.recovery_length_budget_m,
        "curvature_scale": composition.profile.curvature_scale,
        "turn_angle_boost_rad": composition.profile.turn_angle_boost_rad,
        "actual_total_length_m": composition.actual_total_length_m,
        "actual_curve_count": composition.actual_curve_count,
        "actual_line_count": composition.actual_line_count,
        "direction_reversal_count": composition.direction_reversal_count,
        "length_error_m": composition.actual_total_length_m - composition.profile.target_total_length_m,
        "curve_count_error": composition.actual_curve_count - composition.profile.target_curve_count,
        "direction_reversal_error": (
            composition.direction_reversal_count - composition.profile.target_direction_reversals
        ),
    }
