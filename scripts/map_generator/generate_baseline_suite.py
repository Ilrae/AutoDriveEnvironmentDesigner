"""Generate a small fixed AED baseline course suite for repeatable comparisons."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.evaluation.target_modes import resolve_evaluation_target_mode
from scripts.map_generator.level_generator import write_generation_manifest
from scripts.map_generator.opendrive_writer import (
    RoadGeometrySegment,
    StraightRoadConfig,
    build_open_course_config,
    write_straight_road_file,
)


@dataclass(frozen=True)
class BaselineCourseSpec:
    """One fixed baseline course used to compare generator changes over time."""

    case_id: str
    display_name: str
    intent: str
    level_hint: float
    lane_width: float
    lanes_per_direction: int
    curve_direction: str
    course_variant_tag: str
    speed_limit_mps: float
    expected_manual_result: dict[str, float]
    segments: tuple[RoadGeometrySegment, ...]


def build_baseline_course_specs() -> list[BaselineCourseSpec]:
    """Return the fixed AED baseline suite."""

    return [
        BaselineCourseSpec(
            case_id="track_short_easy",
            display_name="Track Short Easy",
            intent="track_like",
            level_hint=0.18,
            lane_width=5.8,
            lanes_per_direction=1,
            curve_direction="left",
            course_variant_tag="baseline_track_short_easy",
            speed_limit_mps=10.0,
            expected_manual_result={
                "min_completion_ratio": 0.985,
                "min_path_tracking_score": 0.90,
                "max_offroad_ratio": 0.01,
                "max_collision_count": 0.0,
                "max_mean_lateral_error_m": 1.25,
            },
            segments=(
                RoadGeometrySegment("line", 56.0),
                RoadGeometrySegment("arc", 30.0, 1.0 / 58.0),
                RoadGeometrySegment("line", 92.0),
            ),
        ),
        BaselineCourseSpec(
            case_id="track_long_easy",
            display_name="Track Long Easy",
            intent="track_like",
            level_hint=0.28,
            lane_width=5.8,
            lanes_per_direction=1,
            curve_direction="right",
            course_variant_tag="baseline_track_long_easy",
            speed_limit_mps=10.0,
            expected_manual_result={
                "min_completion_ratio": 0.985,
                "min_path_tracking_score": 0.87,
                "max_offroad_ratio": 0.01,
                "max_collision_count": 0.0,
                "max_mean_lateral_error_m": 1.45,
            },
            segments=(
                RoadGeometrySegment("line", 84.0),
                RoadGeometrySegment("arc", 28.0, -1.0 / 66.0),
                RoadGeometrySegment("line", 42.0),
                RoadGeometrySegment("arc", 24.0, 1.0 / 74.0),
                RoadGeometrySegment("line", 118.0),
            ),
        ),
        BaselineCourseSpec(
            case_id="track_curvy_medium",
            display_name="Track Curvy Medium",
            intent="track_like",
            level_hint=0.52,
            lane_width=5.4,
            lanes_per_direction=1,
            curve_direction="left",
            course_variant_tag="baseline_track_curvy_medium",
            speed_limit_mps=11.0,
            expected_manual_result={
                "min_completion_ratio": 0.980,
                "min_path_tracking_score": 0.78,
                "max_offroad_ratio": 0.015,
                "max_collision_count": 0.0,
                "max_mean_lateral_error_m": 1.85,
            },
            segments=(
                RoadGeometrySegment("line", 42.0),
                RoadGeometrySegment("arc", 34.0, 1.0 / 34.0),
                RoadGeometrySegment("line", 16.0),
                RoadGeometrySegment("arc", 30.0, -1.0 / 26.0),
                RoadGeometrySegment("line", 14.0),
                RoadGeometrySegment("arc", 24.0, 1.0 / 22.0),
                RoadGeometrySegment("line", 94.0),
            ),
        ),
        BaselineCourseSpec(
            case_id="track_switchback_hard",
            display_name="Track Switchback Hard",
            intent="track_like",
            level_hint=0.82,
            lane_width=5.2,
            lanes_per_direction=1,
            curve_direction="right",
            course_variant_tag="baseline_track_switchback_hard",
            speed_limit_mps=12.0,
            expected_manual_result={
                "min_completion_ratio": 0.970,
                "min_path_tracking_score": 0.68,
                "max_offroad_ratio": 0.02,
                "max_collision_count": 0.0,
                "max_mean_lateral_error_m": 2.20,
            },
            segments=(
                RoadGeometrySegment("line", 36.0),
                RoadGeometrySegment("arc", 18.0, -1.0 / 22.0),
                RoadGeometrySegment("line", 10.0),
                RoadGeometrySegment("arc", 26.0, 1.0 / 18.0),
                RoadGeometrySegment("line", 10.0),
                RoadGeometrySegment("arc", 22.0, -1.0 / 20.0),
                RoadGeometrySegment("line", 12.0),
                RoadGeometrySegment("arc", 18.0, 1.0 / 26.0),
                RoadGeometrySegment("line", 76.0),
            ),
        ),
        BaselineCourseSpec(
            case_id="road_two_lane_flow",
            display_name="Road Two Lane Flow",
            intent="road_like",
            level_hint=0.44,
            lane_width=3.7,
            lanes_per_direction=2,
            curve_direction="left",
            course_variant_tag="baseline_road_two_lane_flow",
            speed_limit_mps=13.0,
            expected_manual_result={
                "min_completion_ratio": 0.980,
                "min_path_tracking_score": 0.74,
                "min_path_match_score": 0.55,
                "max_offroad_ratio": 0.01,
                "max_collision_count": 0.0,
                "max_mean_lateral_error_m": 1.60,
            },
            segments=(
                RoadGeometrySegment("line", 88.0),
                RoadGeometrySegment("arc", 36.0, 1.0 / 80.0),
                RoadGeometrySegment("line", 48.0),
                RoadGeometrySegment("arc", 24.0, -1.0 / 72.0),
                RoadGeometrySegment("line", 126.0),
            ),
        ),
    ]


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a fixed AED baseline course suite.",
    )
    parser.add_argument(
        "--suite-prefix",
        default="aed_baseline",
        help="Map id prefix used for the generated baseline suite.",
    )
    parser.add_argument(
        "--generated-dir",
        type=Path,
        default=Path("maps/generated"),
        help="Directory where baseline .xodr files are written.",
    )
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory where baseline manifests are written.",
    )
    return parser.parse_args()


def _enrich_baseline_manifest(
    manifest_path: Path,
    *,
    spec: BaselineCourseSpec,
) -> None:
    """Attach explicit baseline metadata after the standard manifest is written."""

    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["baseline_suite"] = {
        "suite_name": "aed_core_baselines",
        "case_id": spec.case_id,
        "display_name": spec.display_name,
        "intent": spec.intent,
        "evaluation_target_mode": resolve_evaluation_target_mode(spec.lanes_per_direction),
        "expected_manual_result": spec.expected_manual_result,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def generate_baseline_suite(
    *,
    suite_prefix: str,
    generated_dir: Path,
    manifest_dir: Path,
) -> list[tuple[Path, Path]]:
    """Generate all fixed baseline courses and return their artifact paths."""

    artifacts: list[tuple[Path, Path]] = []
    generated_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    for spec in build_baseline_course_specs():
        map_id = f"{suite_prefix}_{spec.case_id}"
        config = build_open_course_config(
            road_name=map_id,
            road_id=1,
            lane_width=spec.lane_width,
            lanes_per_direction=spec.lanes_per_direction,
            segments=list(spec.segments),
            speed_limit_mps=spec.speed_limit_mps,
        )
        xodr_path = generated_dir / f"{map_id}.xodr"
        manifest_path = manifest_dir / f"{map_id}.json"
        write_straight_road_file(xodr_path, config)
        write_generation_manifest(
            manifest_path,
            map_id=map_id,
            level=spec.level_hint,
            config=config,
            open_course=True,
            curve_direction=spec.curve_direction,
            course_variant=spec.course_variant_tag,
        )
        _enrich_baseline_manifest(manifest_path, spec=spec)
        artifacts.append((xodr_path, manifest_path))

    return artifacts


def main() -> None:
    args = parse_args()
    artifacts = generate_baseline_suite(
        suite_prefix=args.suite_prefix,
        generated_dir=args.generated_dir.resolve(),
        manifest_dir=args.manifest_dir.resolve(),
    )
    print(f"Generated baseline suite: {len(artifacts)} cases")
    for xodr_path, manifest_path in artifacts:
        print(f"- {xodr_path}")
        print(f"  {manifest_path}")


if __name__ == "__main__":
    main()
