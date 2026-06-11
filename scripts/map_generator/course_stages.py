"""Shared stage and variant rules for adaptive open-course generation."""

from __future__ import annotations

from dataclasses import dataclass

from scripts.curriculum.difficulty_controller import clamp_level

VARIANT_ORDER: tuple[str, ...] = (
    "single_turn",
    "gentle_chicane",
    "offset_bend",
    "s_curve",
    "compound_turn",
    "switchback",
    "double_apex",
    "snake_run",
)

_ADAPTIVE_VARIANT_THRESHOLDS: tuple[tuple[float, str], ...] = (
    (0.14, "single_turn"),
    (0.28, "gentle_chicane"),
    (0.42, "offset_bend"),
    (0.58, "s_curve"),
    (0.74, "compound_turn"),
    (0.88, "switchback"),
    (0.96, "double_apex"),
    (1.01, "snake_run"),
)


@dataclass(frozen=True)
class CourseStageDefinition:
    """One macro stage for adaptive open-course generation."""

    index: int
    stage_id: str
    display_name: str
    min_level: float
    max_level_exclusive: float
    intent: str
    candidate_variants: tuple[str, ...]
    target_total_length_band_m: tuple[float, float]
    target_curve_count_band: tuple[int, int]
    target_direction_reversal_band: tuple[int, int]
    target_recovery_ratio_band: tuple[float, float]
    curvature_scale_band: tuple[float, float]
    turn_angle_boost_band_deg: tuple[float, float]


COURSE_STAGE_DEFINITIONS: tuple[CourseStageDefinition, ...] = (
    CourseStageDefinition(
        index=0,
        stage_id="foundation_flow",
        display_name="Foundation Flow",
        min_level=0.0,
        max_level_exclusive=0.18,
        intent="easy completion, long recovery straights, basic turn adaptation",
        candidate_variants=("single_turn", "gentle_chicane"),
        target_total_length_band_m=(220.0, 360.0),
        target_curve_count_band=(2, 3),
        target_direction_reversal_band=(0, 1),
        target_recovery_ratio_band=(0.20, 0.32),
        curvature_scale_band=(0.94, 1.02),
        turn_angle_boost_band_deg=(0.0, 4.0),
    ),
    CourseStageDefinition(
        index=1,
        stage_id="offset_transition",
        display_name="Offset Transition",
        min_level=0.18,
        max_level_exclusive=0.38,
        intent="offset bends and mild direction changes with visible recovery space",
        candidate_variants=("gentle_chicane", "offset_bend", "s_curve"),
        target_total_length_band_m=(260.0, 420.0),
        target_curve_count_band=(3, 4),
        target_direction_reversal_band=(1, 2),
        target_recovery_ratio_band=(0.16, 0.26),
        curvature_scale_band=(1.00, 1.10),
        turn_angle_boost_band_deg=(2.0, 7.0),
    ),
    CourseStageDefinition(
        index=2,
        stage_id="curvy_medium",
        display_name="Curvy Medium",
        min_level=0.38,
        max_level_exclusive=0.62,
        intent="moderate curvature density with repeated steering commitment",
        candidate_variants=("s_curve", "compound_turn", "switchback"),
        target_total_length_band_m=(300.0, 460.0),
        target_curve_count_band=(4, 6),
        target_direction_reversal_band=(1, 3),
        target_recovery_ratio_band=(0.12, 0.22),
        curvature_scale_band=(1.08, 1.22),
        turn_angle_boost_band_deg=(4.0, 11.0),
    ),
    CourseStageDefinition(
        index=3,
        stage_id="technical_hard",
        display_name="Technical Hard",
        min_level=0.62,
        max_level_exclusive=0.84,
        intent="connected corners with reduced recovery space and sharper transitions",
        candidate_variants=("compound_turn", "switchback", "double_apex"),
        target_total_length_band_m=(260.0, 420.0),
        target_curve_count_band=(5, 7),
        target_direction_reversal_band=(2, 4),
        target_recovery_ratio_band=(0.08, 0.16),
        curvature_scale_band=(1.16, 1.34),
        turn_angle_boost_band_deg=(7.0, 16.0),
    ),
    CourseStageDefinition(
        index=4,
        stage_id="mixed_extreme",
        display_name="Mixed Extreme",
        min_level=0.84,
        max_level_exclusive=1.01,
        intent="high curvature density and repeated transitions without relying on long straights",
        candidate_variants=("switchback", "double_apex", "snake_run"),
        target_total_length_band_m=(240.0, 390.0),
        target_curve_count_band=(6, 8),
        target_direction_reversal_band=(3, 5),
        target_recovery_ratio_band=(0.06, 0.12),
        curvature_scale_band=(1.26, 1.48),
        turn_angle_boost_band_deg=(12.0, 22.0),
    ),
)


def course_variant_order() -> list[str]:
    """Return the canonical adaptive variant order."""

    return list(VARIANT_ORDER)


def resolve_adaptive_variant(level: float) -> str:
    """Resolve the default adaptive variant for one normalized level."""

    normalized_level = clamp_level(level)
    for threshold, variant in _ADAPTIVE_VARIANT_THRESHOLDS:
        if normalized_level < threshold:
            return variant
    return VARIANT_ORDER[-1]


def variant_index_for_level(level: float) -> int:
    """Resolve the fallback variant index for one normalized level."""

    variant = resolve_adaptive_variant(level)
    return VARIANT_ORDER.index(variant)


def resolve_course_stage(level: float) -> CourseStageDefinition:
    """Resolve the macro course stage for one normalized difficulty level."""

    normalized_level = clamp_level(level)
    for stage_definition in COURSE_STAGE_DEFINITIONS:
        if normalized_level < stage_definition.max_level_exclusive:
            return stage_definition
    return COURSE_STAGE_DEFINITIONS[-1]


def resolve_course_stage_index(level: float) -> int:
    """Resolve the integer macro stage index for one normalized difficulty level."""

    return resolve_course_stage(level).index


def stage_variant_indices(stage_index: int) -> list[int]:
    """Return the ordered variant indices that belong to one macro stage."""

    clamped_index = max(0, min(len(COURSE_STAGE_DEFINITIONS) - 1, stage_index))
    stage_definition = COURSE_STAGE_DEFINITIONS[clamped_index]
    return [VARIANT_ORDER.index(variant) for variant in stage_definition.candidate_variants]


def resolve_stage_for_variant(variant: str) -> CourseStageDefinition | None:
    """Resolve the first macro stage that owns the given variant."""

    for stage_definition in COURSE_STAGE_DEFINITIONS:
        if variant in stage_definition.candidate_variants:
            return stage_definition
    return None
