"""Generate a draft map case from a simple difficulty level."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import sys
import math

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.curriculum.difficulty_controller import build_profile_from_level
from scripts.map_generator.course_composer import (
    build_open_course_composition,
    build_open_course_manifest_metadata,
)
from scripts.map_generator.course_stages import (
    course_variant_order,
    resolve_adaptive_variant,
    resolve_course_stage,
    resolve_stage_for_variant,
)
from scripts.map_generator.course_validation import validate_open_course_composition
from scripts.map_generator.opendrive_writer import (
    RoadGeometrySegment,
    StraightRoadConfig,
    build_open_course_config,
    build_stadium_track_config,
    write_straight_road_file,
)
from scripts.map_generator.track_contract import (
    build_default_finish_line_contract,
    build_default_spawn_contract,
    resolve_spawn_metadata,
    serialize_finish_line_contract,
)


@dataclass
class LevelGenerationArtifacts:
    """Paths and metadata produced by one draft level-based generation step."""

    map_id: str
    level: float
    xodr_path: Path
    manifest_path: Path


def _build_curve_parameters(level: float, curve_direction: str) -> tuple[float, float]:
    """Map a difficulty level to one safe single-arc curve profile."""

    direction_sign = 1.0 if curve_direction == "left" else -1.0
    curve_length = 20.0 + (30.0 * level)
    curve_curvature = direction_sign * (0.005 + (0.015 * level))
    return curve_length, curve_curvature


def _build_track_parameters(level: float) -> tuple[float, float]:
    """Map a difficulty level to one larger stadium-style track profile."""

    straight_length = 160.0 + (80.0 * (1.0 - level))
    track_radius = 70.0 - (25.0 * level)
    return straight_length, track_radius


def _resolve_open_course_variant(level: float, requested_variant: str) -> str:
    """Resolve one level-adaptive open-course variant name."""

    if requested_variant != "adaptive":
        return requested_variant
    return resolve_adaptive_variant(level)


def _intermediate_variant_label(variant: str) -> str:
    mapping = {
        "single_turn": "long_bend",
        "gentle_chicane": "lane_shift",
        "offset_bend": "offset_curve",
        "s_curve": "rolling_s",
        "compound_turn": "sweeping_curve",
        "switchback": "alternating_bends",
        "double_apex": "twin_apex",
        "snake_run": "meandering_road",
    }
    return mapping.get(variant, variant)


def _supports_composer_variant(course_variant: str | None) -> bool:
    if course_variant is None:
        return False
    return course_variant == "adaptive" or course_variant in course_variant_order()


def _interpolate(min_value: float, max_value: float, ratio: float) -> float:
    normalized_ratio = max(0.0, min(1.0, ratio))
    return min_value + ((max_value - min_value) * normalized_ratio)


def _layout_value(layout_seed_key: str, channel: str) -> float:
    token = f"{layout_seed_key}:{channel}"
    accumulator = 0
    for index, character in enumerate(token):
        accumulator = (accumulator + ((index + 1) * ord(character))) % 104729
    return (accumulator % 1000) / 999.0


def _line(length_m: float) -> RoadGeometrySegment:
    return RoadGeometrySegment("line", max(1.0, float(length_m)))


def _arc(radius_m: float, angle_deg: float, curvature_sign: float) -> RoadGeometrySegment:
    angle_rad = math.radians(max(1.0, float(angle_deg)))
    safe_radius_m = max(8.0, float(radius_m))
    return RoadGeometrySegment(
        "arc",
        safe_radius_m * angle_rad,
        curvature_sign / safe_radius_m,
    )


def _intermediate_sign_pattern(variant: str) -> list[int]:
    if variant == "single_turn":
        return [1, 1]
    if variant == "gentle_chicane":
        return [1, -1, 1]
    if variant == "offset_bend":
        return [1, 1, -1]
    if variant == "s_curve":
        return [1, -1, 1, -1]
    if variant == "compound_turn":
        return [1, 1, 1, -1]
    if variant == "switchback":
        return [1, -1, 1, -1, 1]
    if variant == "double_apex":
        return [1, 1, -1, 1, 1]
    return [1, -1, 1, -1, 1, -1]


def _build_intermediate_road_segments(
    level: float,
    curve_direction: str,
    requested_variant: str = "adaptive",
    layout_seed_key: str = "default_layout",
) -> tuple[list[RoadGeometrySegment], str]:
    """Build one longer road-like course for the intermediate stage."""

    variant = _resolve_open_course_variant(level, requested_variant)
    direction_sign = 1.0 if curve_direction == "left" else -1.0
    sign_pattern = _intermediate_sign_pattern(variant)
    stage_ratio = max(0.0, min(1.0, float(level)))
    route_stretch = _interpolate(
        0.96,
        1.28,
        _layout_value(layout_seed_key, "route_stretch"),
    )

    entry_length = _interpolate(
        175.0,
        135.0,
        stage_ratio,
    ) + _interpolate(0.0, 28.0, _layout_value(layout_seed_key, "entry"))
    exit_length = _interpolate(
        155.0,
        118.0,
        stage_ratio,
    ) + _interpolate(0.0, 24.0, _layout_value(layout_seed_key, "exit"))
    long_recovery = _interpolate(
        112.0,
        60.0,
        stage_ratio,
    ) + _interpolate(0.0, 18.0, _layout_value(layout_seed_key, "long_recovery"))
    short_recovery = _interpolate(
        66.0,
        34.0,
        stage_ratio,
    ) + _interpolate(0.0, 12.0, _layout_value(layout_seed_key, "short_recovery"))
    base_radius = _interpolate(
        125.0,
        52.0,
        stage_ratio,
    ) - _interpolate(0.0, 8.0, _layout_value(layout_seed_key, "radius_trim"))
    base_angle = _interpolate(
        20.0,
        46.0,
        stage_ratio,
    )

    segments: list[RoadGeometrySegment] = [_line(entry_length * route_stretch)]
    for index, relative_sign in enumerate(sign_pattern):
        radius = base_radius - (index * _interpolate(3.0, 6.0, stage_ratio))
        radius += _interpolate(-6.0, 6.0, _layout_value(layout_seed_key, f"radius_{index}"))
        angle_deg = base_angle + _interpolate(
            -4.0,
            10.0,
            _layout_value(layout_seed_key, f"angle_{index}"),
        )
        if index == 0:
            angle_deg *= 0.90
        elif index == len(sign_pattern) - 1:
            angle_deg *= 0.94
        segments.append(_arc(radius, angle_deg, direction_sign * relative_sign))
        if index == len(sign_pattern) - 1:
            continue
        recovery_length = long_recovery if index % 2 == 0 else short_recovery
        recovery_length += _interpolate(
            -8.0,
            8.0,
            _layout_value(layout_seed_key, f"recovery_{index}"),
        )
        segments.append(_line(recovery_length * route_stretch))

    segments.append(_line(exit_length * route_stretch))
    return segments, variant


def _build_open_course_segments(
    level: float,
    curve_direction: str,
    requested_variant: str = "adaptive",
    layout_seed_key: str = "default_layout",
) -> tuple[list[RoadGeometrySegment], str]:
    """Build one stage-driven start-to-finish open course."""
    composition = build_open_course_composition(
        level,
        curve_direction,
        requested_variant=requested_variant,
        layout_seed_key=layout_seed_key,
    )
    return list(composition.segments), composition.profile.variant


def build_straight_road_config_from_level(
    map_id: str,
    level: float,
    road_id: int = 1,
    include_curve: bool = False,
    stadium_track: bool = False,
    open_course: bool = False,
    training_stage: str = "track",
    curve_direction: str = "left",
    course_variant: str = "adaptive",
    lane_width_override: float | None = None,
    straight_length_override: float | None = None,
    track_radius_override: float | None = None,
    layout_seed_key: str | None = None,
) -> StraightRoadConfig:
    """Map a difficulty level to the current draft road generator config."""

    profile = build_profile_from_level(level)
    if open_course:
        normalized_stage = str(training_stage).strip().lower()
        if normalized_stage == "intermediate":
            lane_width = 3.7 if lane_width_override is None else lane_width_override
            segments, _ = _build_intermediate_road_segments(
                profile.level,
                curve_direction,
                requested_variant=course_variant,
                layout_seed_key=layout_seed_key or map_id,
            )
            config = build_open_course_config(
                road_name=map_id,
                road_id=road_id,
                lane_width=lane_width,
                lanes_per_direction=1,
                speed_limit_mps=12.0,
                segments=segments,
            )
            config.center_mark_type = "broken"
            config.center_mark_color = "yellow"
            config.center_mark_width = 0.14
            config.lane_mark_type = "solid"
            config.lane_mark_color = "white"
            config.lane_mark_width = 0.12
            config.shoulder_width = 0.85
            return config

        lane_width = (
            max(4.5, profile.lane_width + 1.1)
            if lane_width_override is None
            else lane_width_override
        )
        segments, _ = _build_open_course_segments(
            profile.level,
            curve_direction,
            requested_variant=course_variant,
            layout_seed_key=layout_seed_key or map_id,
        )
        return build_open_course_config(
            road_name=map_id,
            road_id=road_id,
            lane_width=lane_width,
            lanes_per_direction=1,
            speed_limit_mps=10.0,
            segments=segments,
        )

    if stadium_track:
        straight_length, track_radius = _build_track_parameters(profile.level)
        if straight_length_override is not None:
            straight_length = straight_length_override
        if track_radius_override is not None:
            track_radius = track_radius_override
        lane_width = profile.lane_width if lane_width_override is None else lane_width_override
        return build_stadium_track_config(
            road_name=map_id,
            road_id=road_id,
            straight_length=straight_length,
            track_radius=track_radius,
            lane_width=lane_width,
            lanes_per_direction=1,
            curve_direction=curve_direction,
        )

    curve_length = 0.0
    curve_curvature = 0.0
    if include_curve:
        curve_length, curve_curvature = _build_curve_parameters(level, curve_direction)

    return StraightRoadConfig(
        road_name=map_id,
        road_id=road_id,
        road_length=profile.road_length,
        curve_length=curve_length,
        curve_curvature=curve_curvature,
        lane_width=profile.lane_width if lane_width_override is None else lane_width_override,
        lanes_per_direction=1,
    )


def write_generation_manifest(
    output_path: Path,
    map_id: str,
    level: float,
    config: StraightRoadConfig,
    stadium_track: bool = False,
    open_course: bool = False,
    training_stage: str = "track",
    curve_direction: str | None = None,
    course_variant: str | None = None,
    layout_seed_key: str | None = None,
) -> Path:
    """Write a JSON manifest describing the generated draft map case."""

    profile = build_profile_from_level(level)
    shape_type = "straight"
    if stadium_track:
        shape_type = f"stadium_track_{curve_direction or 'left'}"
    elif open_course:
        variant = course_variant or _resolve_open_course_variant(profile.level, "adaptive")
        if str(training_stage).strip().lower() == "intermediate":
            shape_type = f"intermediate_road_{_intermediate_variant_label(variant)}_{curve_direction or 'left'}"
        else:
            shape_type = f"open_course_{variant}_{curve_direction or 'left'}"
    elif config.curve_length > 0:
        shape_type = f"straight_arc_{curve_direction or 'left'}"

    traffic_side = "right"
    evaluation_target_mode = (
        "lane_center_guidance"
        if str(training_stage).strip().lower() == "intermediate"
        else "road_center_corridor"
    )
    manifest = {
        "map_id": map_id,
        "level": profile.level,
        "training_stage": str(training_stage).strip().lower() or "track",
        "traffic_side": traffic_side,
        "evaluation_target_mode": evaluation_target_mode,
        "generation_stage": "draft_without_carla_validation",
        "generator": (
            "stadium_track_level_generator"
            if stadium_track
            else "intermediate_road_level_generator"
            if open_course and str(training_stage).strip().lower() == "intermediate"
            else "open_course_level_generator"
            if open_course
            else "single_curve_level_generator"
            if config.curve_length > 0
            else "straight_road_level_generator"
        ),
        "shape_type": shape_type,
        "road_profile": asdict(profile),
        "road_config": {
            "road_name": config.road_name,
            "road_id": config.road_id,
            "road_length": config.road_length,
            "curve_length": config.curve_length,
            "curve_curvature": config.curve_curvature,
            "track_radius": config.track_radius,
            "total_length": config.total_length,
            "segment_count": len(config.build_segments()),
            "segments": [asdict(segment) for segment in config.build_segments()],
            "lane_width": config.lane_width,
            "lanes_per_direction": config.lanes_per_direction,
            "speed_limit_mps": config.speed_limit_mps,
            "start_x": config.start_x,
            "start_y": config.start_y,
            "heading_rad": config.heading_rad,
            "traffic_side": traffic_side,
            "evaluation_target_mode": evaluation_target_mode,
            "center_mark_type": config.center_mark_type,
            "center_mark_color": config.center_mark_color,
            "lane_mark_type": config.lane_mark_type,
            "lane_mark_color": config.lane_mark_color,
            "shoulder_width": config.shoulder_width,
        },
        "spawn_point": resolve_spawn_metadata(
            config,
            build_default_spawn_contract(traffic_side),
        ),
        "finish_line": serialize_finish_line_contract(
            build_default_finish_line_contract(traffic_side),
            config=config,
        ),
    }
    if open_course and str(training_stage).strip().lower() == "intermediate":
        manifest["intermediate_layout"] = {
            "variant_id": variant,
            "display_variant": _intermediate_variant_label(variant),
            "intent": "two-way road-like corridor with lane guidance and stronger road-departure penalties",
        }
    if open_course and str(training_stage).strip().lower() != "intermediate":
        stage_definition = resolve_course_stage(profile.level)
        manifest["course_stage"] = {
            "index": stage_definition.index,
            "stage_id": stage_definition.stage_id,
            "display_name": stage_definition.display_name,
            "level_min": stage_definition.min_level,
            "level_max_exclusive": stage_definition.max_level_exclusive,
            "intent": stage_definition.intent,
            "candidate_variants": list(stage_definition.candidate_variants),
            "target_total_length_band_m": list(stage_definition.target_total_length_band_m),
            "target_curve_count_band": list(stage_definition.target_curve_count_band),
            "target_direction_reversal_band": list(stage_definition.target_direction_reversal_band),
            "target_recovery_ratio_band": list(stage_definition.target_recovery_ratio_band),
            "curvature_scale_band": list(stage_definition.curvature_scale_band),
            "turn_angle_boost_band_deg": list(stage_definition.turn_angle_boost_band_deg),
        }
        if _supports_composer_variant(variant):
            composition = build_open_course_composition(
                profile.level,
                curve_direction or "left",
                requested_variant=variant,
                layout_seed_key=layout_seed_key or map_id,
            )
            manifest["open_course_composer"] = build_open_course_manifest_metadata(composition)
            manifest["open_course_validation"] = validate_open_course_composition(composition)
        layout_stage_definition = resolve_stage_for_variant(variant)
        if (
            layout_stage_definition is not None
            and layout_stage_definition.stage_id != stage_definition.stage_id
        ):
            manifest["layout_stage"] = {
                "index": layout_stage_definition.index,
                "stage_id": layout_stage_definition.stage_id,
                "display_name": layout_stage_definition.display_name,
                "level_min": layout_stage_definition.min_level,
                "level_max_exclusive": layout_stage_definition.max_level_exclusive,
                "intent": layout_stage_definition.intent,
                "candidate_variants": list(layout_stage_definition.candidate_variants),
                "target_total_length_band_m": list(layout_stage_definition.target_total_length_band_m),
                "target_curve_count_band": list(layout_stage_definition.target_curve_count_band),
                "target_direction_reversal_band": list(
                    layout_stage_definition.target_direction_reversal_band
                ),
                "target_recovery_ratio_band": list(
                    layout_stage_definition.target_recovery_ratio_band
                ),
                "curvature_scale_band": list(layout_stage_definition.curvature_scale_band),
                "turn_angle_boost_band_deg": list(
                    layout_stage_definition.turn_angle_boost_band_deg
                ),
            }
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(manifest, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def generate_map_from_level(
    map_id: str,
    level: float,
    generated_dir: Path = Path("maps/generated"),
    manifest_dir: Path = Path("experiments"),
    road_id: int = 1,
    include_curve: bool = False,
    stadium_track: bool = False,
    open_course: bool = False,
    training_stage: str = "track",
    curve_direction: str = "left",
    course_variant: str = "adaptive",
    lane_width_override: float | None = None,
    straight_length_override: float | None = None,
    track_radius_override: float | None = None,
    layout_seed_key: str | None = None,
) -> LevelGenerationArtifacts:
    """Generate one draft .xodr file and a matching manifest from a level value."""

    config = build_straight_road_config_from_level(
        map_id=map_id,
        level=level,
        road_id=road_id,
        include_curve=include_curve,
        stadium_track=stadium_track,
        open_course=open_course,
        training_stage=training_stage,
        curve_direction=curve_direction,
        course_variant=course_variant,
        lane_width_override=lane_width_override,
        straight_length_override=straight_length_override,
        track_radius_override=track_radius_override,
        layout_seed_key=layout_seed_key or map_id,
    )
    xodr_path = generated_dir / f"{map_id}.xodr"
    manifest_path = manifest_dir / f"{map_id}.json"

    write_straight_road_file(xodr_path, config)
    write_generation_manifest(
        manifest_path,
        map_id=map_id,
        level=level,
        config=config,
        stadium_track=stadium_track,
        open_course=open_course,
        training_stage=training_stage,
        curve_direction=curve_direction if (include_curve or stadium_track or open_course) else None,
        course_variant=course_variant if open_course else None,
        layout_seed_key=layout_seed_key or map_id,
    )

    return LevelGenerationArtifacts(
        map_id=map_id,
        level=level,
        xodr_path=xodr_path,
        manifest_path=manifest_path,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a draft road map case from a difficulty level, optionally with one arc segment.",
    )
    parser.add_argument(
        "--map-id",
        default="level_case_001",
        help="Identifier used for the generated .xodr and manifest files.",
    )
    parser.add_argument(
        "--level",
        type=float,
        default=0.3,
        help="Difficulty level in the range 0.0 to 1.0.",
    )
    parser.add_argument(
        "--road-id",
        type=int,
        default=1,
        help="Road identifier to embed in the .xodr file.",
    )
    parser.add_argument(
        "--generated-dir",
        type=Path,
        default=Path("maps/generated"),
        help="Directory where the generated .xodr file will be saved.",
    )
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory where the generation manifest will be saved.",
    )
    parser.add_argument(
        "--include-curve",
        action="store_true",
        help="Append one arc segment after the initial straight segment.",
    )
    parser.add_argument(
        "--stadium-track",
        action="store_true",
        help="Generate a larger stadium-style oval track instead of a straight road.",
    )
    parser.add_argument(
        "--open-course",
        action="store_true",
        help="Generate a start-to-finish open course instead of a straight road.",
    )
    parser.add_argument(
        "--curve-direction",
        choices=("left", "right"),
        default="left",
        help="Direction of the generated turns.",
    )
    parser.add_argument(
        "--course-variant",
        choices=(
            "adaptive",
            "single_turn",
            "gentle_chicane",
            "offset_bend",
            "s_curve",
            "compound_turn",
            "switchback",
            "double_apex",
            "snake_run",
        ),
        default="adaptive",
        help="Open-course layout variant when --open-course is used.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    artifacts = generate_map_from_level(
        map_id=args.map_id,
        level=args.level,
        generated_dir=args.generated_dir,
        manifest_dir=args.manifest_dir,
        road_id=args.road_id,
        include_curve=args.include_curve,
        stadium_track=args.stadium_track,
        open_course=args.open_course,
        curve_direction=args.curve_direction,
        course_variant=args.course_variant,
    )
    print(f"Generated map case: {artifacts.map_id}")
    print(f"Level: {artifacts.level:.2f}")
    print(f"OpenDRIVE file: {artifacts.xodr_path}")
    print(f"Manifest file: {artifacts.manifest_path}")


if __name__ == "__main__":
    main()
