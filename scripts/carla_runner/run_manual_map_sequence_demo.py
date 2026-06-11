"""Run a two-map manual driving demo that cycles through pre-generated tracks."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, replace
from datetime import datetime
import math
from pathlib import Path
import random
import sys
import time
from typing import Any

import pygame

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.carla_runner.carla_utils import create_client
from scripts.carla_runner.driver_profiles import create_manual_driver_profile
from scripts.carla_runner.finish_line_visuals import (
    draw_finish_line_overlay,
    draw_finish_line_marker,
    spawn_finish_line_marker_props,
)
from scripts.carla_runner.input_bindings import create_split_input_binding
from scripts.carla_runner.load_xodr_in_carla import (
    create_generation_parameters,
    load_opendrive_world,
)
from scripts.carla_runner.run_manual_track_demo import (
    CameraView,
    build_fixed_overview_transform,
    build_follow_vehicle_spectator_transform,
    build_map_id,
    create_camera_sensor,
    update_follow_vehicle_spectator,
)
from scripts.carla_runner.simple_track_driver import build_centered_spawn_transform
from scripts.carla_runner.vehicle_profiles import (
    VehicleProfile,
    create_builtin_vehicle_profile,
    resolve_vehicle_blueprint_for_profile,
)
from scripts.carla_runner.vehicle_utils import attach_collision_sensor, destroy_actor
from scripts.evaluation.path_metrics import (
    FinishLine,
    PathPoint,
    TrajectorySample,
    evaluate_trajectory_against_paths,
    interpolate_path_point,
    project_point_to_path,
    sample_path_from_config,
)
from scripts.evaluation.target_modes import (
    resolve_evaluation_target_mode,
    uses_road_center_target,
)
from scripts.evaluation.result_models import EpisodeResult, save_episode_result
from scripts.map_generator.opendrive_writer import (
    RoadGeometrySegment,
    StraightRoadConfig,
    build_open_course_config,
    write_straight_road_file,
)
from scripts.map_generator.level_generator import write_generation_manifest


@dataclass
class PreparedMapCase:
    map_id: str
    case_name: str
    generation_level_hint: float
    lane_width: float
    course_length_hint: float
    config: StraightRoadConfig
    xodr_path: Path
    spawn_point: "SpawnPointSpec"
    finish_line: "FinishLineSpec"


@dataclass
class SpawnPointSpec:
    distance_along_start_m: float
    lane_side: str = "right"
    lane_index: int = 1
    lateral_offset_m: float = 0.0
    yaw_offset_deg: float = 0.0


@dataclass
class FinishLineSpec:
    distance_before_end_m: float
    lane_side: str = "right"
    lane_index: int = 1
    lateral_offset_m: float = 0.0
    half_width_m: float = 6.0


@dataclass
class ActiveSequenceEpisode:
    case: PreparedMapCase
    world: Any
    vehicle: Any
    blueprint_id: str
    camera: Any
    camera_view: CameraView
    minimap_camera: Any | None
    minimap_view: CameraView | None
    collision_sensor: Any | None
    collision_state: dict[str, float]
    road_reference_path: list[PathPoint]
    raw_target_path: list[PathPoint]
    target_path: list[PathPoint]
    evaluation_target_mode: str
    finish_line: FinishLine
    finish_marker_actors: list[Any]
    started_monotonic: float
    trajectory_samples: list[TrajectorySample]
    last_sample_time_sec: float
    finish_crossed_override: bool = False
    finish_sample_count: int | None = None


def _apply_finish_cross_override(
    path_summary: "PathEvaluationSummary",
    *,
    finish_crossed: bool,
) -> "PathEvaluationSummary":
    """Keep saved sequence results aligned with the runtime finish trigger."""

    if not finish_crossed or path_summary.crossed_finish_line:
        return path_summary
    return replace(
        path_summary,
        completion_ratio=1.0,
        crossed_finish_line=True,
        finish_line_remaining_m=0.0,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Prepare two OpenDRIVE maps, load the first one in CARLA, and let the "
            "user manually drive while switching to the next prepared map."
        )
    )
    parser.add_argument("--host", default="localhost", help="CARLA server host.")
    parser.add_argument("--port", type=int, default=2000, help="CARLA server port.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=30.0,
        help="Connection timeout in seconds.",
    )
    parser.add_argument(
        "--pythonapi-path",
        default=None,
        help="Path to the CARLA root, PythonAPI directory, dist directory, or .egg file.",
    )
    parser.add_argument(
        "--map-id",
        default=None,
        help="Base map identifier. If omitted, a timestamp-based id is used.",
    )
    parser.add_argument(
        "--generated-dir",
        type=Path,
        default=Path("maps/generated"),
        help="Directory where generated .xodr files are stored.",
    )
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory where generated manifest JSON files are stored.",
    )
    parser.add_argument(
        "--blueprint-filter",
        default="vehicle.*",
        help="Blueprint filter for selecting a CARLA built-in vehicle.",
    )
    parser.add_argument(
        "--vehicle-profile-name",
        default="builtin_sequence_demo_vehicle",
        help="Application-facing vehicle profile name used for this demo run.",
    )
    parser.add_argument(
        "--preferred-blueprint-id",
        default=None,
        help="Optional fixed blueprint id. If omitted, one is chosen from --blueprint-filter.",
    )
    parser.add_argument(
        "--role-name",
        default="hero",
        help="CARLA role_name attribute for the spawned demo vehicle.",
    )
    parser.add_argument(
        "--spawn-index",
        type=int,
        default=None,
        help="Optional fixed spawn point index. If omitted, the first valid point is used.",
    )
    parser.add_argument(
        "--spawn-height-offset",
        type=float,
        default=0.6,
        help="Height offset applied when centering the spawn transform.",
    )
    parser.add_argument(
        "--resolution",
        default="1280x720",
        help="Pygame camera window resolution.",
    )
    parser.add_argument(
        "--camera-distance",
        type=float,
        default=8.0,
        help="Chase camera distance behind the vehicle in meters.",
    )
    parser.add_argument(
        "--camera-height",
        type=float,
        default=3.0,
        help="Chase camera height above the vehicle in meters.",
    )
    parser.add_argument(
        "--camera-pitch",
        type=float,
        default=-14.0,
        help="Chase camera pitch angle in degrees.",
    )
    parser.add_argument(
        "--spectator-mode",
        choices=("fixed-overview", "follow"),
        default="follow",
        help="Server window spectator mode.",
    )
    parser.add_argument(
        "--follow-distance",
        type=float,
        default=14.0,
        help="Spectator follow distance behind the vehicle in meters.",
    )
    parser.add_argument(
        "--follow-height",
        type=float,
        default=5.5,
        help="Spectator follow height above the vehicle in meters.",
    )
    parser.add_argument(
        "--follow-pitch",
        type=float,
        default=-16.0,
        help="Spectator follow pitch angle in degrees.",
    )
    parser.add_argument(
        "--follow-smoothing",
        type=float,
        default=0.18,
        help="Smoothing factor for the server spectator follow camera.",
    )
    parser.add_argument(
        "--overview-height",
        type=float,
        default=0.0,
        help="Fixed overview camera height. Use 0 to auto-compute from track size.",
    )
    parser.add_argument(
        "--overview-pitch",
        type=float,
        default=-88.0,
        help="Fixed overview camera pitch angle in degrees.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=0.0,
        help="Optional auto-exit duration. Use 0 or negative for unlimited driving.",
    )
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=Path("results/manual_sequence"),
        help="Directory where per-map evaluation JSON files are stored.",
    )
    parser.add_argument(
        "--trajectory-sample-interval",
        type=float,
        default=0.10,
        help="Interval in seconds between recorded trajectory samples.",
    )
    parser.add_argument(
        "--path-sample-step",
        type=float,
        default=1.0,
        help="Reference path sampling step in meters.",
    )
    parser.add_argument(
        "--path-tolerance",
        type=float,
        default=1.5,
        help="Distance threshold in meters used for path match scoring.",
    )
    parser.add_argument(
        "--offroad-margin",
        type=float,
        default=0.25,
        help="Extra margin in meters added to road half-width before marking course departure.",
    )
    parser.add_argument(
        "--keep-vehicle",
        action="store_true",
        help="Keep the spawned vehicle alive after the window closes.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=7,
        help="Random seed used for vehicle selection.",
    )
    parser.add_argument(
        "--vertex-distance",
        type=float,
        default=2.0,
        help="Mesh vertex distance in meters.",
    )
    parser.add_argument(
        "--max-road-length",
        type=float,
        default=50.0,
        help="Maximum road mesh chunk length in meters.",
    )
    parser.add_argument(
        "--wall-height",
        type=float,
        default=1.0,
        help="Boundary wall height in meters.",
    )
    parser.add_argument(
        "--additional-width",
        type=float,
        default=0.6,
        help="Extra junction lane width in meters.",
    )
    parser.add_argument(
        "--no-smooth-junctions",
        action="store_true",
        help="Disable CARLA's junction mesh smoothing.",
    )
    parser.add_argument(
        "--no-mesh-visibility",
        action="store_true",
        help="Generate the world without rendering the road mesh.",
    )
    parser.add_argument(
        "--keep-settings",
        action="store_true",
        help="Keep current world settings instead of resetting them after load.",
    )
    return parser.parse_args()


def build_prepared_cases(base_map_id: str, args: argparse.Namespace) -> list[PreparedMapCase]:
    cases: list[PreparedMapCase] = []
    case_definitions = [
        {
            "suffix": "case_001",
            "case_name": "start_left_finish",
            "generation_level_hint": 0.30,
            "curve_direction": "left",
            "course_variant": "single_turn",
            "lane_width": 5.8,
            "course_length_hint": 136.0,
            "config": build_open_course_config(
                road_name=f"{base_map_id}_case_001",
                road_id=1,
                lane_width=5.8,
                lanes_per_direction=1,
                speed_limit_mps=10.0,
                segments=[
                    RoadGeometrySegment("line", 36.0),
                    RoadGeometrySegment("arc", 30.0, 1.0 / 28.0),
                    RoadGeometrySegment("line", 70.0),
                ],
            ),
            "spawn_point": SpawnPointSpec(
                distance_along_start_m=8.0,
                lane_side="right",
                lane_index=1,
                lateral_offset_m=0.0,
                yaw_offset_deg=0.0,
            ),
            "finish_line": FinishLineSpec(
                distance_before_end_m=1.0,
                lane_side="right",
                lane_index=1,
                lateral_offset_m=0.0,
                half_width_m=6.0,
            ),
        },
        {
            "suffix": "case_002",
            "case_name": "start_s_curve_finish",
            "generation_level_hint": 0.45,
            "curve_direction": "right",
            "course_variant": "s_curve",
            "lane_width": 5.5,
            "course_length_hint": 148.0,
            "config": build_open_course_config(
                road_name=f"{base_map_id}_case_002",
                road_id=1,
                lane_width=5.5,
                lanes_per_direction=1,
                speed_limit_mps=10.0,
                segments=[
                    RoadGeometrySegment("line", 26.0),
                    RoadGeometrySegment("arc", 20.0, -1.0 / 20.0),
                    RoadGeometrySegment("line", 18.0),
                    RoadGeometrySegment("arc", 20.0, 1.0 / 20.0),
                    RoadGeometrySegment("line", 64.0),
                ],
            ),
            "spawn_point": SpawnPointSpec(
                distance_along_start_m=8.0,
                lane_side="right",
                lane_index=1,
                lateral_offset_m=0.0,
                yaw_offset_deg=0.0,
            ),
            "finish_line": FinishLineSpec(
                distance_before_end_m=1.0,
                lane_side="right",
                lane_index=1,
                lateral_offset_m=0.0,
                half_width_m=6.0,
            ),
        },
    ]

    for case_definition in case_definitions:
        map_id = f"{base_map_id}_{case_definition['suffix']}"
        xodr_path = args.generated_dir / f"{map_id}.xodr"
        write_straight_road_file(xodr_path, case_definition["config"])
        write_generation_manifest(
            args.manifest_dir / f"{map_id}.json",
            map_id=map_id,
            level=case_definition["generation_level_hint"],
            config=case_definition["config"],
            open_course=True,
            curve_direction=case_definition["curve_direction"],
            course_variant=case_definition["course_variant"],
        )
        cases.append(
            PreparedMapCase(
                map_id=map_id,
                case_name=case_definition["case_name"],
                generation_level_hint=case_definition["generation_level_hint"],
                lane_width=case_definition["lane_width"],
                course_length_hint=case_definition["course_length_hint"],
                config=case_definition["config"],
                xodr_path=xodr_path,
                spawn_point=case_definition["spawn_point"],
                finish_line=case_definition["finish_line"],
            )
        )
    return cases


def _sample_course_points(config: StraightRoadConfig, sample_step: float = 4.0) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = [(config.start_x, config.start_y)]
    x = config.start_x
    y = config.start_y
    heading = config.heading_rad

    for segment in config.build_segments():
        steps = max(1, int(math.ceil(segment.length / sample_step)))
        if segment.geometry_type == "line":
            for step_index in range(1, steps + 1):
                distance = min(segment.length, step_index * sample_step)
                points.append(
                    (
                        x + (distance * math.cos(heading)),
                        y + (distance * math.sin(heading)),
                    )
                )
            x = x + (segment.length * math.cos(heading))
            y = y + (segment.length * math.sin(heading))
        else:
            curvature = segment.curvature
            for step_index in range(1, steps + 1):
                distance = min(segment.length, step_index * sample_step)
                sample_heading = heading + (curvature * distance)
                points.append(
                    (
                        x + (math.sin(sample_heading) - math.sin(heading)) / curvature,
                        y - (math.cos(sample_heading) - math.cos(heading)) / curvature,
                    )
                )
            end_heading = heading + (curvature * segment.length)
            x = x + (math.sin(end_heading) - math.sin(heading)) / curvature
            y = y - (math.cos(end_heading) - math.cos(heading)) / curvature
            heading = end_heading

    return points


def build_case_spawn_transform(
    carla: object,
    world: object,
    config: StraightRoadConfig,
    spawn_point: SpawnPointSpec,
    z_offset: float,
) -> object:
    forward_distance = spawn_point.distance_along_start_m
    heading = config.heading_rad
    right_normal_heading = heading + (math.pi / 2.0)
    lane_center_offset = (spawn_point.lane_index - 0.5) * config.lane_width
    if spawn_point.lane_side == "right":
        lane_center_offset *= 1.0
    elif spawn_point.lane_side == "left":
        lane_center_offset *= -1.0
    else:
        raise ValueError("spawn_point.lane_side must be 'left' or 'right'")

    lateral_offset = lane_center_offset + spawn_point.lateral_offset_m

    start_x = (
        config.start_x
        + (forward_distance * math.cos(heading))
        + (lateral_offset * math.cos(right_normal_heading))
    )
    start_y = (
        config.start_y
        + (forward_distance * math.sin(heading))
        + (lateral_offset * math.sin(right_normal_heading))
    )
    reference_transform = carla.Transform(
        carla.Location(x=start_x, y=start_y, z=0.0),
        carla.Rotation(yaw=math.degrees(heading) + spawn_point.yaw_offset_deg),
    )
    transform = build_centered_spawn_transform(
        world=world,
        reference_transform=reference_transform,
        z_offset=z_offset,
    )
    transform.rotation.yaw = math.degrees(heading) + spawn_point.yaw_offset_deg
    transform.rotation.pitch = 0.0
    transform.rotation.roll = 0.0
    return transform


def build_case_finish_line(
    case: PreparedMapCase,
    target_path: list[PathPoint],
    road_half_width_m: float,
) -> FinishLine:
    """Build one explicit finish line for the prepared map case."""

    if not target_path:
        raise ValueError("target_path must contain at least one point")

    finish_line_progress_s = max(
        0.0,
        target_path[-1].s - case.finish_line.distance_before_end_m,
    )
    finish_path_point = interpolate_path_point(target_path, finish_line_progress_s)
    finish_half_width_m = (
        case.finish_line.half_width_m
        if case.finish_line.half_width_m > 0
        else road_half_width_m
    )
    return FinishLine(
        x=finish_path_point.x,
        y=finish_path_point.y,
        s=finish_line_progress_s,
        heading_rad=finish_path_point.heading_rad,
        half_width_m=finish_half_width_m,
    )


def set_case_overview_spectator(
    carla: object,
    world: object,
    case: PreparedMapCase,
    overview_height: float,
    overview_pitch: float,
) -> None:
    sampled_points = _sample_course_points(case.config)
    xs = [point[0] for point in sampled_points]
    ys = [point[1] for point in sampled_points]
    min_x, max_x = min(xs), max(xs)
    min_y, max_y = min(ys), max(ys)
    center_x = (min_x + max_x) / 2.0
    center_y = (min_y + max_y) / 2.0
    span = max(max_x - min_x, max_y - min_y)
    auto_height = max(90.0, (span * 1.7) + 30.0)
    spectator_transform = carla.Transform(
        carla.Location(x=center_x, y=center_y, z=overview_height if overview_height > 0 else auto_height),
        carla.Rotation(pitch=overview_pitch, yaw=0.0, roll=0.0),
    )
    world.get_spectator().set_transform(spectator_transform)


def _vehicle_finish_trigger_offset_m(vehicle: Any) -> float:
    """Approximate the front-bumper offset so finish timing matches the visible stripe."""

    try:
        return max(0.8, float(vehicle.bounding_box.extent.x))
    except Exception:
        return 1.8


def create_sequence_episode(
    *,
    args: argparse.Namespace,
    carla: object,
    client: object,
    generation_parameters: object,
    width: int,
    height: int,
    case: PreparedMapCase,
    vehicle_profile: VehicleProfile,
    preferred_blueprint_id: str | None,
) -> ActiveSequenceEpisode:
    xodr_content = case.xodr_path.read_text(encoding="utf-8")
    world = load_opendrive_world(
        client,
        xodr_content,
        generation_parameters,
        args.keep_settings,
    )
    blueprint = resolve_vehicle_blueprint_for_profile(
        world=world,
        vehicle_profile=vehicle_profile,
        preferred_blueprint_id=preferred_blueprint_id,
    )
    spawn_transform = build_case_spawn_transform(
        carla=carla,
        world=world,
        config=case.config,
        spawn_point=case.spawn_point,
        z_offset=args.spawn_height_offset,
    )
    vehicle = world.spawn_actor(blueprint, spawn_transform)
    camera, camera_view = create_camera_sensor(
        world=world,
        carla=carla,
        vehicle=vehicle,
        width=width,
        height=height,
        camera_distance=args.camera_distance,
        camera_height=args.camera_height,
        camera_pitch=args.camera_pitch,
    )
    collision_sensor, collision_state = attach_collision_sensor(world, vehicle)
    road_reference_path = sample_path_from_config(
        case.config,
        sample_step_m=args.path_sample_step,
    )
    raw_target_path = sample_path_from_config(
        case.config,
        sample_step_m=args.path_sample_step,
        lane_side=case.finish_line.lane_side,
        lane_index=case.finish_line.lane_index,
        lateral_offset_m=case.finish_line.lateral_offset_m,
    )
    evaluation_target_mode = resolve_evaluation_target_mode(case.config.lanes_per_direction)
    target_path = (
        list(road_reference_path)
        if uses_road_center_target(evaluation_target_mode)
        else list(raw_target_path)
    )
    finish_line = build_case_finish_line(
        case=case,
        target_path=target_path,
        road_half_width_m=case.config.lane_width * case.config.lanes_per_direction,
    )
    finish_marker_actors = spawn_finish_line_marker_props(
        carla=carla,
        world=world,
        finish_line=finish_line,
        finish_line_is_road_center=uses_road_center_target(evaluation_target_mode),
    )
    return ActiveSequenceEpisode(
        case=case,
        world=world,
        vehicle=vehicle,
        blueprint_id=blueprint.id,
        camera=camera,
        camera_view=camera_view,
        minimap_camera=None,
        minimap_view=None,
        collision_sensor=collision_sensor,
        collision_state=collision_state,
        road_reference_path=road_reference_path,
        raw_target_path=raw_target_path,
        target_path=target_path,
        evaluation_target_mode=evaluation_target_mode,
        finish_line=finish_line,
        finish_marker_actors=finish_marker_actors,
        started_monotonic=time.monotonic(),
        trajectory_samples=[],
        last_sample_time_sec=-1.0,
    )


def apply_keyboard_control(keys: Any, control: Any) -> Any:
    if keys[pygame.K_w] or keys[pygame.K_UP]:
        control.throttle = min(control.throttle + 0.04, 0.75)
    else:
        control.throttle = 0.0

    if keys[pygame.K_s] or keys[pygame.K_DOWN]:
        control.brake = min(control.brake + 0.2, 1.0)
    else:
        control.brake = 0.0

    if keys[pygame.K_a] or keys[pygame.K_LEFT]:
        control.steer = max(control.steer - 0.05, -0.7)
    elif keys[pygame.K_d] or keys[pygame.K_RIGHT]:
        control.steer = min(control.steer + 0.05, 0.7)
    else:
        control.steer *= 0.6

    control.hand_brake = bool(keys[pygame.K_SPACE])
    return control


def calculate_speed_kmh(vehicle: Any) -> float:
    """Return the current vehicle speed in km/h."""

    velocity = vehicle.get_velocity()
    return 3.6 * math.sqrt(
        (velocity.x ** 2) + (velocity.y ** 2) + (velocity.z ** 2)
    )


def record_trajectory_sample(
    episode: ActiveSequenceEpisode,
    *,
    force: bool = False,
    sample_interval_sec: float = 0.10,
) -> None:
    """Append one trajectory sample if enough time has passed."""

    now_monotonic = time.monotonic()
    elapsed_sec = now_monotonic - episode.started_monotonic
    if (
        not force
        and elapsed_sec - episode.last_sample_time_sec < sample_interval_sec
    ):
        return

    transform = episode.vehicle.get_transform()
    episode.trajectory_samples.append(
        TrajectorySample(
            timestamp_sec=elapsed_sec,
            x=float(transform.location.x),
            y=float(transform.location.y),
            z=float(transform.location.z),
            speed_kmh=calculate_speed_kmh(episode.vehicle),
        )
    )
    episode.last_sample_time_sec = elapsed_sec


def destroy_sequence_episode(
    episode: ActiveSequenceEpisode | None,
    *,
    keep_vehicle: bool = False,
) -> None:
    """Destroy spawned actors for one active sequence episode."""

    if episode is None:
        return

    for finish_marker_actor in episode.finish_marker_actors:
        destroy_actor(finish_marker_actor)
    if episode.collision_sensor is not None:
        destroy_actor(episode.collision_sensor)
    if episode.minimap_camera is not None:
        destroy_actor(episode.minimap_camera)
    if episode.camera is not None:
        destroy_actor(episode.camera)
    if episode.vehicle is not None and not keep_vehicle:
        destroy_actor(episode.vehicle)


def save_episode_evaluation(
    *,
    episode: ActiveSequenceEpisode,
    result_dir: Path,
    path_tolerance_m: float,
    offroad_margin_m: float,
    end_reason: str,
    vehicle_profile: VehicleProfile,
    driver_profile: Any,
    input_binding: Any,
) -> Path:
    """Evaluate one episode and save the result JSON file."""

    record_trajectory_sample(
        episode,
        force=True,
        sample_interval_sec=0.0,
    )
    trajectory_samples = episode.trajectory_samples
    if episode.finish_sample_count is not None:
        trajectory_samples = trajectory_samples[: episode.finish_sample_count]
    path_summary = evaluate_trajectory_against_paths(
        trajectory_samples,
        target_path=episode.target_path,
        road_reference_path=episode.road_reference_path,
        raw_target_path=episode.raw_target_path,
        road_half_width_m=(
            (episode.case.config.lane_width * episode.case.config.lanes_per_direction)
            + float(getattr(episode.case.config, "shoulder_width", 0.0))
        ),
        finish_line=episode.finish_line,
        path_tolerance_m=path_tolerance_m,
        offroad_margin_m=offroad_margin_m,
        lane_half_width_m=(episode.case.config.lane_width * 0.5),
        lane_guidance_active=(episode.evaluation_target_mode == "lane_center_guidance"),
    )
    path_summary = _apply_finish_cross_override(
        path_summary,
        finish_crossed=episode.finish_crossed_override,
    )
    collision_count = int(episode.collision_state.get("count", 0))

    failure_reason = None
    success = False
    if collision_count > 0:
        failure_reason = "collision"
    elif path_summary.offroad_sample_count > 0:
        failure_reason = "course_departure"
    elif path_summary.opposite_lane_ratio >= 0.35:
        failure_reason = "wrong_lane"
    elif not path_summary.crossed_finish_line:
        failure_reason = "not_finished"
    else:
        success = True

    last_timestamp = 0.0
    if episode.trajectory_samples:
        last_timestamp = episode.trajectory_samples[-1].timestamp_sec

    output_name = (
        f"{episode.case.map_id}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_"
        f"{end_reason}.json"
    )
    result = EpisodeResult(
        map_id=episode.case.map_id,
        success=success,
        time_sec=last_timestamp,
        collision_count=collision_count,
        offroad_ratio=path_summary.offroad_ratio,
        failure_reason=failure_reason,
        path_match_score=path_summary.path_match_score,
        path_tracking_score=path_summary.path_tracking_score,
        lane_discipline_score=path_summary.lane_discipline_score,
        lane_departure_ratio=path_summary.lane_departure_ratio,
        opposite_lane_ratio=path_summary.opposite_lane_ratio,
        mean_lateral_error_m=path_summary.mean_lateral_error_m,
        max_lateral_error_m=path_summary.max_lateral_error_m,
        completion_ratio=path_summary.completion_ratio,
        crossed_finish_line=path_summary.crossed_finish_line,
        sample_count=path_summary.sample_count,
        metadata={
            "case_name": episode.case.case_name,
            "lane_width_m": episode.case.lane_width,
            "course_length_hint_m": episode.case.course_length_hint,
            "generation_level_hint": episode.case.generation_level_hint,
            "spawn_point": {
                "distance_along_start_m": episode.case.spawn_point.distance_along_start_m,
                "lane_side": episode.case.spawn_point.lane_side,
                "lane_index": episode.case.spawn_point.lane_index,
                "lateral_offset_m": episode.case.spawn_point.lateral_offset_m,
                "yaw_offset_deg": episode.case.spawn_point.yaw_offset_deg,
            },
            "finish_line": {
                "distance_before_end_m": episode.case.finish_line.distance_before_end_m,
                "lane_side": episode.case.finish_line.lane_side,
                "lane_index": episode.case.finish_line.lane_index,
                "lateral_offset_m": episode.case.finish_line.lateral_offset_m,
                "half_width_m": episode.case.finish_line.half_width_m,
                "resolved_x": episode.finish_line.x,
                "resolved_y": episode.finish_line.y,
                "resolved_s": episode.finish_line.s,
                "resolved_heading_rad": episode.finish_line.heading_rad,
            },
            "path_tolerance_m": path_tolerance_m,
            "offroad_margin_m": offroad_margin_m,
            "evaluation_target_mode": episode.evaluation_target_mode,
            "raw_path_reference_mode": "lane_center_guidance",
            "lane_half_width_m": episode.case.config.lane_width * 0.5,
            "finish_line_half_width_m": episode.finish_line.half_width_m,
            "finish_line_remaining_m": path_summary.finish_line_remaining_m,
            "end_reason": end_reason,
            "vehicle_profile": vehicle_profile.describe(),
            "driver_profile": driver_profile.describe(),
            "input_binding": input_binding.describe(),
            "vehicle_blueprint": episode.blueprint_id,
        },
    )
    saved_path = save_episode_result(result, result_dir / output_name)
    print(
        "Saved evaluation result: "
        f"{saved_path}"
    )
    print(
        "Evaluation summary: "
        f"success={result.success}, "
        f"failure_reason={result.failure_reason}, "
        f"collisions={result.collision_count}, "
        f"offroad_ratio={result.offroad_ratio:.3f}, "
        f"path_score={result.path_tracking_score:.3f}, "
        f"lane_score={result.lane_discipline_score:.3f}, "
        f"path_match={result.path_match_score:.3f}, "
        f"lane_departure={result.lane_departure_ratio:.3f}, "
        f"wrong_lane={result.opposite_lane_ratio:.3f}, "
        f"mean_error={result.mean_lateral_error_m:.3f}m, "
        f"completion={result.completion_ratio:.3f}, "
        f"crossed_finish_line={result.crossed_finish_line}"
    )
    return saved_path


def main() -> None:
    args = parse_args()
    random.seed(args.random_seed)

    width, height = [int(value) for value in args.resolution.split("x")]
    base_map_id = build_map_id(args.map_id)
    prepared_cases = build_prepared_cases(base_map_id, args)

    pygame.init()
    pygame.font.init()
    display = pygame.display.set_mode((width, height))
    pygame.display.set_caption("AutoDrive Manual Map Sequence Demo")
    font = pygame.font.SysFont("Consolas", 20)

    episode: ActiveSequenceEpisode | None = None
    preferred_blueprint_id = None
    control = None
    vehicle_profile = create_builtin_vehicle_profile(
        profile_name=args.vehicle_profile_name,
        blueprint_filter=args.blueprint_filter,
        preferred_blueprint_id=args.preferred_blueprint_id,
        role_name=args.role_name,
        notes=(
            "CARLA built-in vehicle profile used for two-map manual sequence "
            "demonstrations."
        ),
    )
    driver_profile = create_manual_driver_profile(
        notes=(
            "Manual keyboard driving profile used while validating the map "
            "reload and respawn cycle."
        )
    )
    input_binding = create_split_input_binding(
        vehicle_profile=vehicle_profile,
        driver_profile=driver_profile,
        notes=(
            "Two-map reload demo uses split inputs so the app can keep map "
            "generation independent from the driving backend."
        ),
    )

    try:
        carla, client, _ = create_client(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            pythonapi_path=args.pythonapi_path,
        )
        generation_parameters = create_generation_parameters(carla, args)
        current_case_index = 0

        def load_case(case_index: int, current_blueprint_id: str | None) -> tuple[ActiveSequenceEpisode, object, Any]:
            case = prepared_cases[case_index]
            loaded_episode = create_sequence_episode(
                args=args,
                carla=carla,
                client=client,
                generation_parameters=generation_parameters,
                width=width,
                height=height,
                case=case,
                vehicle_profile=vehicle_profile,
                preferred_blueprint_id=current_blueprint_id,
            )
            loaded_control = carla.VehicleControl()
            loaded_spectator_state = None
            if args.spectator_mode == "fixed-overview":
                set_case_overview_spectator(
                    carla=carla,
                    world=loaded_episode.world,
                    case=case,
                    overview_height=args.overview_height,
                    overview_pitch=args.overview_pitch,
                )
            print("Manual map sequence demo vehicle spawned successfully.")
            print(f"Prepared map: {case.map_id}")
            print(f"Loaded map: {loaded_episode.world.get_map().name}")
            print(
                "Course parameters: "
                f"name={case.case_name}, "
                f"lane_width={case.lane_width:.2f}, "
                f"length_hint={case.course_length_hint:.1f}"
            )
            print(
                "Spawn point: "
                f"along_start={case.spawn_point.distance_along_start_m:.1f}m, "
                f"lane_side={case.spawn_point.lane_side}, "
                f"lane_index={case.spawn_point.lane_index}, "
                f"lateral_offset={case.spawn_point.lateral_offset_m:.1f}m, "
                f"yaw_offset={case.spawn_point.yaw_offset_deg:.1f}deg"
            )
            print(
                "Finish line: "
                f"before_end={case.finish_line.distance_before_end_m:.1f}m, "
                f"lane_side={case.finish_line.lane_side}, "
                f"lane_index={case.finish_line.lane_index}, "
                f"lateral_offset={case.finish_line.lateral_offset_m:.1f}m, "
                f"half_width={case.finish_line.half_width_m:.1f}m"
            )
            print(
                "Evaluation target: "
                f"{loaded_episode.evaluation_target_mode} "
                "(raw lane-center metric retained)"
            )
            print(f"Vehicle blueprint: {loaded_episode.blueprint_id}")
            print(f"Vehicle profile: {vehicle_profile.describe()}")
            print(f"Driver profile: {driver_profile.describe()}")
            print(f"Input binding: {input_binding.describe()}")
            print("Controls: WASD / Arrow keys, Space hand brake, R reload current map, N next prepared map, ESC exit")
            return loaded_episode, loaded_control, loaded_spectator_state

        episode, control, spectator_state = load_case(current_case_index, preferred_blueprint_id)
        preferred_blueprint_id = episode.blueprint_id

        clock = pygame.time.Clock()
        end_time = None
        if args.duration_seconds > 0:
            end_time = time.time() + args.duration_seconds

        while end_time is None or time.time() < end_time:
            reload_current_map = False
            load_next_map = False
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    if episode is not None:
                        save_episode_evaluation(
                        episode=episode,
                        result_dir=args.result_dir,
                        path_tolerance_m=args.path_tolerance,
                        offroad_margin_m=args.offroad_margin,
                        end_reason="window_closed",
                        vehicle_profile=vehicle_profile,
                        driver_profile=driver_profile,
                        input_binding=input_binding,
                        )
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    if episode is not None:
                        save_episode_evaluation(
                        episode=episode,
                        result_dir=args.result_dir,
                        path_tolerance_m=args.path_tolerance,
                        offroad_margin_m=args.offroad_margin,
                        end_reason="user_exit",
                        vehicle_profile=vehicle_profile,
                        driver_profile=driver_profile,
                        input_binding=input_binding,
                        )
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    reload_current_map = True
                if event.type == pygame.KEYDOWN and event.key == pygame.K_n:
                    load_next_map = True

            if reload_current_map or load_next_map:
                if episode is not None:
                    save_episode_evaluation(
                        episode=episode,
                        result_dir=args.result_dir,
                        path_tolerance_m=args.path_tolerance,
                        offroad_margin_m=args.offroad_margin,
                        end_reason="next_map" if load_next_map else "reload_current",
                        vehicle_profile=vehicle_profile,
                        driver_profile=driver_profile,
                        input_binding=input_binding,
                    )
                target_case_index = current_case_index
                if load_next_map:
                    target_case_index = (current_case_index + 1) % len(prepared_cases)
                    print(f"Loading next prepared map: {prepared_cases[target_case_index].map_id}")
                else:
                    print(f"Reloading current map: {prepared_cases[target_case_index].map_id}")

                previous_episode = episode

                try:
                    next_episode, next_control, next_spectator_state = load_case(
                        target_case_index,
                        preferred_blueprint_id,
                    )
                except Exception as error:
                    print("Failed to switch maps.")
                    print(f"Reason: {error}")
                    destroy_sequence_episode(previous_episode, keep_vehicle=False)
                    return
                else:
                    episode = next_episode
                    control = next_control
                    spectator_state = next_spectator_state
                    preferred_blueprint_id = episode.blueprint_id
                    current_case_index = target_case_index
                    destroy_sequence_episode(previous_episode, keep_vehicle=False)
                pygame.event.clear()
                continue

            keys = pygame.key.get_pressed()
            control = apply_keyboard_control(keys, control)
            episode.vehicle.apply_control(control)
            record_trajectory_sample(
                episode,
                force=False,
                sample_interval_sec=args.trajectory_sample_interval,
            )
            if args.spectator_mode == "follow":
                spectator_state = update_follow_vehicle_spectator(
                    carla=carla,
                    world=episode.world,
                    vehicle=episode.vehicle,
                    follow_distance=args.follow_distance,
                    follow_height=args.follow_height,
                    follow_pitch=args.follow_pitch,
                    smoothing=args.follow_smoothing,
                    state=spectator_state,
                )

            if episode.camera_view.surface is not None:
                display.blit(episode.camera_view.surface, (0, 0))
                draw_finish_line_marker(
                    carla=carla,
                    world=episode.world,
                    finish_line=episode.finish_line,
                    finish_line_is_road_center=uses_road_center_target(
                        episode.evaluation_target_mode
                    ),
                )
                draw_finish_line_overlay(
                    display,
                    pygame=pygame,
                    carla=carla,
                    world=episode.world,
                    camera=episode.camera,
                    finish_line=episode.finish_line,
                    finish_line_is_road_center=uses_road_center_target(
                        episode.evaluation_target_mode
                    ),
                )
            else:
                display.fill((30, 30, 30))

            transform = episode.vehicle.get_transform()
            target_projection = project_point_to_path(
                float(transform.location.x),
                float(transform.location.y),
                episode.target_path,
            )
            road_projection = project_point_to_path(
                float(transform.location.x),
                float(transform.location.y),
                episode.road_reference_path,
            )
            speed_kmh = calculate_speed_kmh(episode.vehicle)
            finish_trigger_progress_s = (
                target_projection.progress_s + _vehicle_finish_trigger_offset_m(episode.vehicle)
            )
            finish_line_remaining_m = max(
                0.0,
                episode.finish_line.s - finish_trigger_progress_s,
            )
            offroad_threshold = (
                episode.case.config.lane_width * episode.case.config.lanes_per_direction
            ) + args.offroad_margin
            crossed_finish_now = (
                finish_trigger_progress_s >= episode.finish_line.s
                and road_projection.distance_m <= offroad_threshold
            )
            if crossed_finish_now and not episode.finish_crossed_override:
                episode.finish_crossed_override = True
                episode.finish_sample_count = len(episode.trajectory_samples)
            case = episode.case
            lines = [
                f"Prepared map: {case.map_id}",
                f"Case {current_case_index + 1}/{len(prepared_cases)}",
                f"Course: {case.case_name}",
                f"Lane width: {case.lane_width:.1f}m  Length hint: {case.course_length_hint:.0f}m",
                (
                    "Spawn: "
                    f"{case.spawn_point.distance_along_start_m:.0f}m / "
                    f"{case.spawn_point.lane_side}{case.spawn_point.lane_index} / "
                    f"{case.spawn_point.lateral_offset_m:.1f}m"
                ),
                f"Vehicle: {episode.blueprint_id}",
                f"Speed: {speed_kmh:5.1f} km/h",
                (
                    "Tracking: "
                    f"progress {target_projection.progress_ratio * 100.0:5.1f}% / "
                    f"lane error {target_projection.distance_m:4.2f}m"
                ),
                (
                    "Evaluation: "
                    f"collisions {int(episode.collision_state.get('count', 0))} / "
                    f"road dist {road_projection.distance_m:4.2f}m / "
                    f"limit {offroad_threshold:4.2f}m"
                ),
                (
                    "Finish: "
                    f"remaining {finish_line_remaining_m:5.1f}m / "
                    f"half width {episode.finish_line.half_width_m:4.1f}m"
                ),
                f"Eval target: {episode.evaluation_target_mode}",
                "Controls: W/A/S/D, Space, R reload, N next map, ESC",
            ]
            y = 16
            for line in lines:
                text_surface = font.render(line, True, (255, 255, 255))
                display.blit(text_surface, (16, y))
                y += 24

            pygame.display.flip()
            clock.tick_busy_loop(60)
        if episode is not None:
            save_episode_evaluation(
                episode=episode,
                result_dir=args.result_dir,
                path_tolerance_m=args.path_tolerance,
                offroad_margin_m=args.offroad_margin,
                end_reason="duration_timeout",
                vehicle_profile=vehicle_profile,
                driver_profile=driver_profile,
                input_binding=input_binding,
            )
    finally:
        destroy_sequence_episode(episode, keep_vehicle=args.keep_vehicle)
        pygame.quit()


if __name__ == "__main__":
    main()
