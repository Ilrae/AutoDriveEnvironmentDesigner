"""Run one generated Practical Stage Town scenario with manual keyboard driving."""

from __future__ import annotations

import argparse
from datetime import datetime
import json
import math
from pathlib import Path
import queue
import random
import sys
import threading
import time
from typing import Any

import pygame

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.app.practical_stage import resolve_practical_weather
from scripts.carla_runner.carla_utils import create_client
from scripts.carla_runner.driver_profiles import (
    create_external_driver_profile,
    create_manual_driver_profile,
)
from scripts.carla_runner.external_driver_runtime import (
    build_external_driver_environment,
    launch_external_driver_process,
    terminate_external_driver_process,
)
from scripts.carla_runner.integration_loader import (
    load_driver_control_module,
    load_vehicle_integration_config,
)
from scripts.carla_runner.input_bindings import create_split_input_binding
from scripts.carla_runner.post_run_review import (
    build_episode_result_from_overlay,
    build_practical_adaptation_lines,
    build_result_comparison_lines,
    draw_review_panel,
)
from scripts.carla_runner.run_manual_xodr_demo import (
    FinishScoreOverlay,
    apply_keyboard_control,
    calculate_speed_kmh,
)
from scripts.carla_runner.run_manual_track_demo import (
    create_camera_sensor,
    update_follow_vehicle_spectator,
)
from scripts.carla_runner.vehicle_profiles import (
    create_builtin_vehicle_profile,
    resolve_vehicle_blueprint_for_profile,
)
from scripts.carla_runner.vehicle_utils import (
    attach_collision_sensor,
    spawn_autopilot_traffic,
    spawn_pedestrian_traffic,
)
from scripts.evaluation.path_metrics import (
    FinishLine,
    PathPoint,
    TrajectorySample,
    evaluate_trajectory_against_paths,
    project_point_to_path,
)
from scripts.evaluation.result_models import EpisodeResult, save_episode_result
from scripts.evaluation.scoring import compute_driving_score as compute_episode_driving_score


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load one Practical Stage scenario, spawn the ego vehicle, and drive manually in Town.",
    )
    parser.add_argument("--scenario-path", type=Path, required=True, help="Practical scenario JSON path.")
    parser.add_argument("--host", default="localhost", help="CARLA server host.")
    parser.add_argument("--port", type=int, default=2000, help="CARLA server port.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Connection timeout in seconds.")
    parser.add_argument(
        "--pythonapi-path",
        default=None,
        help="Path to the CARLA root, PythonAPI directory, dist directory, or .egg file.",
    )
    parser.add_argument(
        "--blueprint-filter",
        default="vehicle.*",
        help="Blueprint filter for selecting a CARLA built-in vehicle.",
    )
    parser.add_argument(
        "--preferred-blueprint-id",
        default=None,
        help="Optional fixed blueprint id. If omitted, one is chosen from --blueprint-filter.",
    )
    parser.add_argument("--role-name", default=None, help="CARLA role_name attribute.")
    parser.add_argument(
        "--integration-custom-enabled",
        action="store_true",
        help="Enable one custom ego vehicle / driver integration override.",
    )
    parser.add_argument(
        "--driver-backend",
        choices=("manual", "external_module", "external_command"),
        default="manual",
        help="Driving backend used after the app spawns the ego vehicle.",
    )
    parser.add_argument(
        "--vehicle-config-path",
        default=None,
        help="Optional JSON file describing ego vehicle overrides such as blueprint id and color.",
    )
    parser.add_argument(
        "--driver-module-path",
        default=None,
        help="Optional Python file that overrides the built-in manual keyboard-control mapping.",
    )
    parser.add_argument(
        "--external-driver-command",
        default=None,
        help="Optional shell command launched after ego spawn for ROS or autonomy integration.",
    )
    parser.add_argument(
        "--external-driver-working-dir",
        default=None,
        help="Optional working directory used when launching the external driving command.",
    )
    parser.add_argument(
        "--external-driver-startup-wait",
        type=float,
        default=2.0,
        help="Seconds to wait after launching the external driving command before evaluation begins.",
    )
    parser.add_argument("--spawn-height-offset", type=float, default=0.6, help="Height offset added to the saved spawn transform.")
    parser.add_argument("--resolution", default="1280x720", help="Pygame camera window resolution.")
    parser.add_argument("--camera-distance", type=float, default=8.0, help="Chase camera distance in meters.")
    parser.add_argument("--camera-height", type=float, default=3.0, help="Chase camera height in meters.")
    parser.add_argument("--camera-pitch", type=float, default=-14.0, help="Chase camera pitch in degrees.")
    parser.add_argument(
        "--spectator-mode",
        choices=("fixed-overview", "follow"),
        default="follow",
        help="Server window spectator mode.",
    )
    parser.add_argument("--follow-distance", type=float, default=14.0, help="Spectator follow distance.")
    parser.add_argument("--follow-height", type=float, default=5.5, help="Spectator follow height.")
    parser.add_argument("--follow-pitch", type=float, default=-16.0, help="Spectator follow pitch.")
    parser.add_argument("--follow-smoothing", type=float, default=0.18, help="Spectator smoothing factor.")
    parser.add_argument("--overview-height", type=float, default=170.0, help="Fixed overview camera height.")
    parser.add_argument("--overview-pitch", type=float, default=-88.0, help="Fixed overview camera pitch.")
    parser.add_argument("--duration-seconds", type=float, default=0.0, help="Optional auto-exit duration.")
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=Path("results/practical"),
        help="Directory where practical evaluation JSON files are stored.",
    )
    parser.add_argument(
        "--trajectory-sample-interval",
        type=float,
        default=0.10,
        help="Interval in seconds between recorded trajectory samples.",
    )
    parser.add_argument("--path-tolerance", type=float, default=1.25, help="Path tolerance in meters.")
    parser.add_argument("--offroad-margin", type=float, default=0.10, help="Extra road margin in meters.")
    parser.add_argument(
        "--collision-cooldown-seconds",
        type=float,
        default=0.5,
        help="Debounce window used when counting collision sensor events.",
    )
    parser.add_argument("--keep-vehicle", action="store_true", help="Keep the spawned vehicle after exit.")
    parser.add_argument(
        "--traffic-manager-port",
        type=int,
        default=8000,
        help="Traffic Manager port used for Practical background traffic vehicles.",
    )
    parser.add_argument("--random-seed", type=int, default=7, help="Random seed for vehicle selection.")
    return parser.parse_args()


def _load_scenario_payload(scenario_path: Path) -> dict[str, Any]:
    if not scenario_path.exists():
        raise FileNotFoundError(f"The requested Practical scenario JSON does not exist: {scenario_path}")
    return json.loads(scenario_path.read_text(encoding="utf-8"))


def _build_transform_from_payload(carla: Any, payload: dict[str, Any], *, z_offset: float = 0.0) -> Any:
    return carla.Transform(
        carla.Location(
            x=float(payload["x"]),
            y=float(payload["y"]),
            z=float(payload["z"]) + float(z_offset),
        ),
        carla.Rotation(
            yaw=float(payload.get("yaw", 0.0)),
            pitch=float(payload.get("pitch", 0.0)),
            roll=float(payload.get("roll", 0.0)),
        ),
    )


def _map_name_matches_town(map_name: str, town_id: str) -> bool:
    normalized_map_name = str(map_name or "").replace("\\", "/").strip().lower()
    normalized_town_id = str(town_id or "").strip().lower()
    if not normalized_map_name or not normalized_town_id:
        return False
    return (
        normalized_map_name == normalized_town_id
        or normalized_map_name.endswith(f"/{normalized_town_id}")
    )


def _build_path_points(route_waypoints: list[dict[str, Any]]) -> tuple[list[PathPoint], list[dict[str, Any]]]:
    if not route_waypoints:
        raise ValueError("route_waypoints must not be empty")
    path_points: list[PathPoint] = []
    metadata_points: list[dict[str, Any]] = []
    cumulative_s = 0.0
    previous_x = float(route_waypoints[0]["x"])
    previous_y = float(route_waypoints[0]["y"])
    for index, waypoint_payload in enumerate(route_waypoints):
        x = float(waypoint_payload["x"])
        y = float(waypoint_payload["y"])
        yaw_deg = float(waypoint_payload.get("yaw", 0.0))
        if index > 0:
            cumulative_s += math.hypot(x - previous_x, y - previous_y)
        path_points.append(
            PathPoint(
                x=x,
                y=y,
                s=cumulative_s,
                heading_rad=math.radians(yaw_deg),
            )
        )
        metadata_points.append(
            {
                "road_id": int(waypoint_payload.get("road_id", 0)),
                "section_id": int(waypoint_payload.get("section_id", 0)),
                "lane_id": int(waypoint_payload.get("lane_id", 0)),
                "is_junction": bool(waypoint_payload.get("is_junction", False)),
                "road_option": str(waypoint_payload.get("road_option", "LANEFOLLOW")).upper(),
            }
        )
        previous_x = x
        previous_y = y
    return path_points, metadata_points


def _estimate_lane_half_width(world_map: Any, spawn_transform: Any, destination_transform: Any) -> float:
    lane_widths: list[float] = []
    for location in (spawn_transform.location, destination_transform.location):
        waypoint = world_map.get_waypoint(location, project_to_road=True)
        if waypoint is not None:
            lane_widths.append(float(waypoint.lane_width))
    if lane_widths:
        return max(1.5, sum(lane_widths) / (2.0 * len(lane_widths)))
    return 1.85


def _set_route_overview_spectator(
    carla: Any,
    world: Any,
    route_points: list[PathPoint],
    height: float,
    pitch: float,
) -> None:
    xs = [point.x for point in route_points]
    ys = [point.y for point in route_points]
    center_x = (min(xs) + max(xs)) / 2.0
    center_y = (min(ys) + max(ys)) / 2.0
    span = max(max(xs) - min(xs), max(ys) - min(ys), 40.0)
    world.get_spectator().set_transform(
        carla.Transform(
            carla.Location(x=center_x, y=center_y, z=max(height, span * 1.1)),
            carla.Rotation(pitch=pitch, yaw=0.0, roll=0.0),
        )
    )


def _draw_destination_marker(carla: Any, world: Any, destination_transform: Any) -> None:
    marker_center = destination_transform.location + carla.Location(z=0.22)
    ring_radius_m = 1.55
    for marker_index in range(16):
        angle_rad = (2.0 * math.pi * marker_index) / 16.0
        world.debug.draw_point(
            carla.Location(
                x=marker_center.x + (math.cos(angle_rad) * ring_radius_m),
                y=marker_center.y + (math.sin(angle_rad) * ring_radius_m),
                z=marker_center.z,
            ),
            size=0.09,
            color=carla.Color(255, 184, 56),
            life_time=0.12,
            persistent_lines=False,
        )
    world.debug.draw_string(
        destination_transform.location + carla.Location(z=1.8),
        "GOAL",
        draw_shadow=False,
        color=carla.Color(255, 180, 30),
        life_time=0.12,
        persistent_lines=False,
    )
    world.debug.draw_point(
        destination_transform.location + carla.Location(z=0.24),
        size=0.07,
        color=carla.Color(255, 230, 120),
        life_time=0.12,
        persistent_lines=False,
    )


def _project_world_point_to_screen(
    location: Any,
    *,
    camera: Any,
    width: int,
    height: int,
) -> tuple[float, float] | None:
    try:
        inverse_matrix = camera.get_transform().get_inverse_matrix()
        fov_deg = float(camera.attributes.get("fov", "90"))
    except Exception:
        return None

    point = [float(location.x), float(location.y), float(location.z), 1.0]
    camera_space = [
        sum(float(inverse_matrix[row][column]) * point[column] for column in range(4))
        for row in range(4)
    ]
    camera_x = camera_space[1]
    camera_y = -camera_space[2]
    camera_z = camera_space[0]
    if camera_z <= 0.05:
        return None

    focal_length = width / (2.0 * math.tan(math.radians(fov_deg) * 0.5))
    screen_x = (width * 0.5) + ((camera_x * focal_length) / camera_z)
    screen_y = (height * 0.5) + ((camera_y * focal_length) / camera_z)
    return (screen_x, screen_y)


def _draw_destination_goal_overlay(
    display: pygame.Surface,
    *,
    pygame: Any,
    carla: Any,
    camera: Any,
    destination_transform: Any,
) -> None:
    if display is None or camera is None:
        return

    width = int(display.get_width())
    height = int(display.get_height())
    projected = _project_world_point_to_screen(
        destination_transform.location + carla.Location(z=0.18),
        camera=camera,
        width=width,
        height=height,
    )
    if projected is None:
        return

    screen_x = int(projected[0])
    screen_y = int(projected[1])
    if screen_x < -40 or screen_x > width + 40 or screen_y < -40 or screen_y > height + 40:
        return

    overlay = pygame.Surface((width, height), pygame.SRCALPHA)
    glow_color = (255, 194, 64, 92)
    fill_color = (255, 224, 112, 70)
    ring_color = (255, 255, 255, 235)
    inner_ring_color = (255, 194, 64, 255)

    pygame.draw.circle(overlay, glow_color, (screen_x, screen_y), 32)
    pygame.draw.circle(overlay, fill_color, (screen_x, screen_y), 18)
    pygame.draw.circle(overlay, ring_color, (screen_x, screen_y), 18, width=4)
    pygame.draw.circle(overlay, inner_ring_color, (screen_x, screen_y), 10, width=3)

    font = pygame.font.SysFont("Consolas", 18, bold=True)
    goal_text = font.render("GOAL", True, (255, 240, 180))
    text_rect = goal_text.get_rect(center=(screen_x, screen_y - 28))
    overlay.blit(goal_text, text_rect)
    display.blit(overlay, (0, 0))


def _build_traffic_excluded_locations(
    carla: Any,
    spawn_transform: Any,
    destination_transform: Any,
    route_path: list[PathPoint],
) -> list[Any]:
    excluded_locations = [
        spawn_transform.location,
        destination_transform.location,
    ]
    if route_path:
        sample_indices = {
            0,
            min(8, len(route_path) - 1),
            min(24, len(route_path) - 1),
            max(0, len(route_path) - 25),
            max(0, len(route_path) - 9),
            len(route_path) - 1,
        }
        for index in sorted(sample_indices):
            point = route_path[index]
            excluded_locations.append(
                carla.Location(
                    x=float(point.x),
                    y=float(point.y),
                    z=float(spawn_transform.location.z),
                )
            )
    return excluded_locations


def _nearest_route_index(progress_s: float, route_path: list[PathPoint]) -> int:
    if not route_path:
        return 0
    best_index = 0
    best_delta = float("inf")
    for index, point in enumerate(route_path):
        delta = abs(point.s - progress_s)
        if delta < best_delta:
            best_delta = delta
            best_index = index
    return best_index


def _resolve_next_maneuver(
    progress_s: float,
    route_path: list[PathPoint],
    route_metadata: list[dict[str, Any]],
) -> tuple[str, float]:
    if not route_path:
        return "FOLLOW", 0.0
    start_index = _nearest_route_index(progress_s, route_path)
    for index in range(start_index, len(route_path)):
        option = str(route_metadata[index].get("road_option", "LANEFOLLOW")).upper()
        if option in {"LEFT", "RIGHT", "STRAIGHT"} and route_path[index].s >= progress_s + 8.0:
            return option, max(0.0, route_path[index].s - progress_s)
    return "FOLLOW", max(0.0, route_path[-1].s - progress_s)


def _destination_bearing_deg(vehicle_transform: Any, destination_transform: Any) -> float:
    dx = float(destination_transform.location.x - vehicle_transform.location.x)
    dy = float(destination_transform.location.y - vehicle_transform.location.y)
    yaw_rad = math.radians(float(vehicle_transform.rotation.yaw))
    forward = (math.cos(yaw_rad) * dx) + (math.sin(yaw_rad) * dy)
    lateral = (-math.sin(yaw_rad) * dx) + (math.cos(yaw_rad) * dy)
    return math.degrees(math.atan2(lateral, max(forward, 1e-6) if abs(forward) < 1e-6 else forward))


def _format_destination_hint(bearing_deg: float) -> str:
    if abs(bearing_deg) < 12.0:
        return "ahead"
    if bearing_deg > 0.0:
        return f"{abs(bearing_deg):.0f} deg left"
    return f"{abs(bearing_deg):.0f} deg right"


def _route_points_in_vehicle_frame(
    vehicle_transform: Any,
    route_path: list[PathPoint],
    *,
    step: int = 3,
) -> list[tuple[float, float, float]]:
    vehicle_x = float(vehicle_transform.location.x)
    vehicle_y = float(vehicle_transform.location.y)
    yaw_rad = math.radians(float(vehicle_transform.rotation.yaw))
    points: list[tuple[float, float, float]] = []
    for index in range(0, len(route_path), max(1, step)):
        point = route_path[index]
        dx = float(point.x) - vehicle_x
        dy = float(point.y) - vehicle_y
        forward = (math.cos(yaw_rad) * dx) + (math.sin(yaw_rad) * dy)
        lateral = (-math.sin(yaw_rad) * dx) + (math.cos(yaw_rad) * dy)
        points.append((forward, lateral, point.s))
    return points


def _draw_practical_minimap(
    display: pygame.Surface,
    *,
    vehicle_transform: Any,
    destination_transform: Any,
    route_path: list[PathPoint],
    progress_s: float,
) -> None:
    panel_width = 270
    panel_height = 190
    margin = 18
    panel_left = display.get_width() - panel_width - margin
    panel_top = display.get_height() - panel_height - margin
    overlay = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
    overlay.fill((16, 24, 32, 186))

    pygame.draw.rect(overlay, (207, 216, 220, 220), (0, 0, panel_width, panel_height), width=1)

    ahead_range_m = 120.0
    behind_range_m = 35.0
    lateral_range_m = 55.0
    scale = min((panel_width * 0.42) / lateral_range_m, (panel_height * 0.68) / ahead_range_m)
    center_x = panel_width // 2
    center_y = int(panel_height * 0.78)

    pygame.draw.line(overlay, (70, 86, 102, 220), (center_x, 16), (center_x, panel_height - 16), 1)

    route_points = _route_points_in_vehicle_frame(vehicle_transform, route_path, step=2)
    past_points: list[tuple[int, int]] = []
    future_points: list[tuple[int, int]] = []
    for forward, lateral, point_s in route_points:
        if forward < -behind_range_m or forward > ahead_range_m or abs(lateral) > lateral_range_m:
            continue
        px = int(center_x + (lateral * scale))
        py = int(center_y - (forward * scale))
        if point_s <= progress_s:
            past_points.append((px, py))
        else:
            future_points.append((px, py))

    if len(past_points) >= 2:
        pygame.draw.lines(overlay, (96, 110, 122), False, past_points, 3)
    if len(future_points) >= 2:
        pygame.draw.lines(overlay, (64, 196, 255), False, future_points, 4)

    bearing_deg = _destination_bearing_deg(vehicle_transform, destination_transform)
    vehicle_x = float(vehicle_transform.location.x)
    vehicle_y = float(vehicle_transform.location.y)
    dx = float(destination_transform.location.x - vehicle_x)
    dy = float(destination_transform.location.y - vehicle_y)
    yaw_rad = math.radians(float(vehicle_transform.rotation.yaw))
    destination_forward = (math.cos(yaw_rad) * dx) + (math.sin(yaw_rad) * dy)
    destination_lateral = (-math.sin(yaw_rad) * dx) + (math.cos(yaw_rad) * dy)
    if (
        -behind_range_m <= destination_forward <= ahead_range_m
        and abs(destination_lateral) <= lateral_range_m
    ):
        dest_px = int(center_x + (destination_lateral * scale))
        dest_py = int(center_y - (destination_forward * scale))
        pygame.draw.circle(overlay, (255, 176, 59), (dest_px, dest_py), 6)

    vehicle_points = [
        (center_x, center_y - 12),
        (center_x - 8, center_y + 10),
        (center_x + 8, center_y + 10),
    ]
    pygame.draw.polygon(overlay, (255, 255, 255), vehicle_points)
    pygame.draw.polygon(overlay, (15, 118, 110), vehicle_points, width=1)

    title_font = pygame.font.SysFont("Consolas", 18)
    overlay.blit(title_font.render("Route Guidance", True, (240, 244, 248)), (12, 10))
    overlay.blit(
        title_font.render(f"Goal: {_format_destination_hint(bearing_deg)}", True, (255, 214, 102)),
        (12, 34),
    )

    display.blit(overlay, (panel_left, panel_top))


def _record_trajectory_sample(
    samples: list[TrajectorySample],
    vehicle: Any,
    started_monotonic: float,
    last_sample_time_sec: float,
    *,
    force: bool,
    sample_interval_sec: float,
) -> float:
    elapsed_sec = max(0.0, time.monotonic() - started_monotonic)
    if not force and elapsed_sec - last_sample_time_sec < sample_interval_sec:
        return last_sample_time_sec
    transform = vehicle.get_transform()
    samples.append(
        TrajectorySample(
            timestamp_sec=elapsed_sec,
            x=float(transform.location.x),
            y=float(transform.location.y),
            z=float(transform.location.z),
            speed_kmh=calculate_speed_kmh(vehicle),
        )
    )
    return elapsed_sec


def _stop_sensor(sensor: Any) -> None:
    if sensor is None:
        return
    try:
        sensor.stop()
    except Exception:
        pass


def _destroy_actors_batch(carla: Any, client: Any, actors: list[Any]) -> None:
    valid_actor_ids = []
    for actor in actors:
        if actor is None:
            continue
        actor_id = getattr(actor, "id", None)
        if actor_id is None:
            continue
        valid_actor_ids.append(int(actor_id))
    if not valid_actor_ids:
        return
    try:
        client.apply_batch([carla.command.DestroyActor(actor_id) for actor_id in valid_actor_ids])
    except Exception:
        for actor in actors:
            if actor is None:
                continue
            try:
                actor.destroy()
            except Exception:
                pass


def _draw_goal_score_overlay(
    display: Any,
    *,
    width: int,
    height: int,
    title_font: Any,
    body_font: Any,
    overlay: FinishScoreOverlay,
) -> None:
    """Draw one compact score card after the Practical goal is reached."""

    panel_width = 420
    panel_height = 214
    panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
    panel.fill((12, 16, 20, 214))
    panel_rect = panel.get_rect()
    panel_center_y = min(height - (panel_height // 2) - 18, int(height * 0.82))
    panel_rect.center = (width // 2, panel_center_y)
    display.blit(panel, panel_rect.topleft)

    title = "GOAL SCORE" if overlay.success else "GOAL EVALUATION"
    title_surface = title_font.render(title, True, (255, 255, 255))
    display.blit(title_surface, (panel_rect.x + 18, panel_rect.y + 14))

    outcome_text = "success" if overlay.success else str(overlay.failure_reason or "review")
    lines = [
        f"Score: {overlay.driving_score * 100.0:5.1f} / 100",
        f"Outcome: {outcome_text}",
        (
            f"Time: {overlay.time_sec:5.1f}s   "
            f"Path: {overlay.path_tracking_score * 100.0:5.1f}%"
        ),
        (
            f"Lane: {overlay.lane_discipline_score * 100.0:5.1f}%   "
            f"Raw match: {overlay.path_match_score * 100.0:5.1f}%"
        ),
        (
            f"Lane dep: {overlay.lane_departure_ratio * 100.0:4.1f}%   "
            f"Wrong lane: {overlay.opposite_lane_ratio * 100.0:4.1f}%"
        ),
        (
            f"Completion: {overlay.completion_ratio * 100.0:5.1f}%   "
            f"Offroad: {overlay.offroad_ratio * 100.0:4.1f}%"
        ),
        f"Mean err: {overlay.mean_lateral_error_m:4.2f}m   Collisions: {overlay.collision_count}",
    ]
    current_y = panel_rect.y + 52
    for line in lines:
        line_surface = body_font.render(line, True, (230, 230, 230))
        display.blit(line_surface, (panel_rect.x + 18, current_y))
        current_y += 22


def _draw_goal_pending_overlay(
    display: Any,
    *,
    width: int,
    height: int,
    title_font: Any,
    body_font: Any,
) -> None:
    """Draw one lightweight status card while the goal score is being computed."""

    panel_width = 420
    panel_height = 108
    panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
    panel.fill((12, 16, 20, 200))
    panel_rect = panel.get_rect()
    panel_center_y = min(height - (panel_height // 2) - 18, int(height * 0.84))
    panel_rect.center = (width // 2, panel_center_y)
    display.blit(panel, panel_rect.topleft)

    title_surface = title_font.render("GOAL REACHED", True, (255, 255, 255))
    display.blit(title_surface, (panel_rect.x + 18, panel_rect.y + 14))
    for index, line in enumerate(
        (
            "Calculating score in background...",
            "You can keep driving. Press ESC when you want to exit.",
        )
    ):
        line_surface = body_font.render(line, True, (230, 230, 230))
        display.blit(line_surface, (panel_rect.x + 18, panel_rect.y + 52 + (index * 22)))


def _expected_lane_id_for_progress(
    progress_s: float,
    route_path: list[PathPoint],
    route_metadata: list[dict[str, Any]],
) -> int:
    if not route_path:
        return 0
    best_index = 0
    best_delta = float("inf")
    for index, point in enumerate(route_path):
        delta = abs(point.s - progress_s)
        if delta < best_delta:
            best_delta = delta
            best_index = index
    return int(route_metadata[best_index].get("lane_id", 0))


def _sign(value: int) -> int:
    if value > 0:
        return 1
    if value < 0:
        return -1
    return 0


def _count_opposite_lane_samples(
    *,
    world_map: Any,
    samples: list[TrajectorySample],
    route_path: list[PathPoint],
    route_metadata: list[dict[str, Any]],
) -> int:
    opposite_lane_count = 0
    spawn_points = world_map.get_spawn_points()
    if not spawn_points:
        return 0
    location_type = type(spawn_points[0].location)
    for sample in samples:
        current_waypoint = world_map.get_waypoint(
            location_type(
                x=sample.x,
                y=sample.y,
                z=sample.z,
            ),
            project_to_road=False,
        )
        if current_waypoint is None:
            continue
        progress = project_point_to_path(sample.x, sample.y, route_path).progress_s
        expected_lane_id = _expected_lane_id_for_progress(progress, route_path, route_metadata)
        if _sign(int(current_waypoint.lane_id)) != 0 and _sign(expected_lane_id) != 0:
            if _sign(int(current_waypoint.lane_id)) != _sign(expected_lane_id):
                opposite_lane_count += 1
    return opposite_lane_count


def _save_practical_result(
    *,
    scenario_payload: dict[str, Any],
    scenario_path: Path,
    world_map: Any,
    vehicle: Any,
    collision_count: int,
    trajectory_samples: list[TrajectorySample],
    route_path: list[PathPoint],
    route_metadata: list[dict[str, Any]],
    lane_half_width_m: float,
    path_tolerance_m: float,
    offroad_margin_m: float,
    result_dir: Path,
    vehicle_profile: Any,
    driver_profile: Any,
    input_binding: Any,
    blueprint_id: str,
    end_reason: str,
    traffic_summary: dict[str, int],
    pedestrian_summary: dict[str, int] | None = None,
    destination_reached_override: bool = False,
) -> Path:
    finish_line = FinishLine(
        x=route_path[-1].x,
        y=route_path[-1].y,
        s=route_path[-1].s,
        heading_rad=route_path[-1].heading_rad,
        half_width_m=max(4.0, lane_half_width_m * 2.2),
    )
    summary = evaluate_trajectory_against_paths(
        trajectory_samples,
        target_path=route_path,
        road_reference_path=route_path,
        raw_target_path=route_path,
        road_half_width_m=max(4.5, lane_half_width_m * 2.6),
        finish_line=finish_line,
        path_tolerance_m=path_tolerance_m,
        offroad_margin_m=offroad_margin_m,
        lane_half_width_m=lane_half_width_m,
        lane_guidance_active=True,
    )
    opposite_lane_count = _count_opposite_lane_samples(
        world_map=world_map,
        samples=trajectory_samples,
        route_path=route_path,
        route_metadata=route_metadata,
    )
    sample_count = max(1, summary.sample_count)
    opposite_lane_ratio = opposite_lane_count / sample_count
    destination_reached = bool(destination_reached_override or summary.crossed_finish_line)
    failure_reason = None
    success = False
    if collision_count > 0:
        failure_reason = "collision"
    elif summary.offroad_sample_count > 0:
        failure_reason = "course_departure"
    elif opposite_lane_ratio >= 0.30:
        failure_reason = "wrong_lane"
    elif not destination_reached:
        failure_reason = "not_finished"
    else:
        success = True

    last_timestamp = trajectory_samples[-1].timestamp_sec if trajectory_samples else 0.0
    result = EpisodeResult(
        map_id=str(scenario_payload["scenario_id"]),
        success=success,
        time_sec=last_timestamp,
        collision_count=collision_count,
        offroad_ratio=summary.offroad_ratio,
        failure_reason=failure_reason,
        path_match_score=summary.path_match_score,
        path_tracking_score=summary.path_tracking_score,
        lane_discipline_score=summary.lane_discipline_score,
        lane_departure_ratio=summary.lane_departure_ratio,
        opposite_lane_ratio=opposite_lane_ratio,
        mean_lateral_error_m=summary.mean_lateral_error_m,
        max_lateral_error_m=summary.max_lateral_error_m,
        completion_ratio=summary.completion_ratio,
        crossed_finish_line=destination_reached,
        sample_count=summary.sample_count,
        metadata={
            "training_stage": "practical",
            "scenario_id": scenario_payload["scenario_id"],
            "scenario_mode": scenario_payload.get("scenario_mode"),
            "scenario_path": str(scenario_path),
            "town_id": scenario_payload.get("town_id"),
            "weather_preset": scenario_payload.get("weather_preset"),
            "traffic_vehicle_count": scenario_payload.get("traffic_vehicle_count"),
            "spawned_traffic_vehicle_count": int(traffic_summary.get("spawned_count", 0)),
            "requested_traffic_vehicle_count": int(traffic_summary.get("requested_count", 0)),
            "traffic_spawn_attempted_points": int(traffic_summary.get("attempted_spawn_points", 0)),
            "pedestrian_count": scenario_payload.get("pedestrian_count"),
            "spawned_pedestrian_count": int((pedestrian_summary or {}).get("spawned_count", 0)),
            "pedestrian_controller_count": int((pedestrian_summary or {}).get("controller_count", 0)),
            "route_length_hint_m": scenario_payload.get("route_length_hint_m"),
            "junction_focus": scenario_payload.get("junction_focus"),
            "spawn": scenario_payload.get("spawn"),
            "destination": scenario_payload.get("destination"),
            "route_metrics": scenario_payload.get("route_metrics"),
            "vehicle_profile": vehicle_profile.describe(),
            "driver_profile": driver_profile.describe(),
            "input_binding": input_binding.describe(),
            "vehicle_blueprint": blueprint_id,
            "path_tolerance_m": path_tolerance_m,
            "offroad_margin_m": offroad_margin_m,
            "lane_width_m": lane_half_width_m * 2.0,
            "evaluation_target_mode": "lane_center_guidance",
            "end_reason": end_reason,
            "road_map_name": world_map.name,
            "destination_reached": destination_reached,
        },
    )
    output_name = (
        f"{scenario_payload['scenario_id']}_"
        f"{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}_"
        f"{end_reason}.json"
    )
    saved_path = save_episode_result(result, result_dir.resolve() / output_name)
    driving_score = compute_episode_driving_score(
        completion_ratio=result.completion_ratio,
        path_tracking_score=result.path_tracking_score,
        crossed_finish_line=result.crossed_finish_line,
        offroad_ratio=result.offroad_ratio,
        collision_count=result.collision_count,
        failure_reason=result.failure_reason,
        success=result.success,
        lane_discipline_score=result.lane_discipline_score,
        lane_departure_ratio=result.lane_departure_ratio,
        opposite_lane_ratio=result.opposite_lane_ratio,
    )
    print(f"Saved Practical evaluation result: {saved_path}")
    print(
        "Practical evaluation summary: "
        f"success={result.success}, failure_reason={result.failure_reason}, "
        f"score={driving_score * 100.0:.1f}, completion={result.completion_ratio:.3f}, "
        f"collisions={result.collision_count}, offroad={result.offroad_ratio:.3f}, "
        f"lane_score={result.lane_discipline_score:.3f}, wrong_lane={result.opposite_lane_ratio:.3f}"
    )
    return saved_path


def _evaluate_practical_run(
    *,
    world_map: Any,
    collision_count: int,
    trajectory_samples: list[TrajectorySample],
    route_path: list[PathPoint],
    route_metadata: list[dict[str, Any]],
    lane_half_width_m: float,
    path_tolerance_m: float,
    offroad_margin_m: float,
    destination_reached_override: bool = False,
) -> tuple[Any, float, bool, str | None, float]:
    finish_line = FinishLine(
        x=route_path[-1].x,
        y=route_path[-1].y,
        s=route_path[-1].s,
        heading_rad=route_path[-1].heading_rad,
        half_width_m=max(4.0, lane_half_width_m * 2.2),
    )
    summary = evaluate_trajectory_against_paths(
        trajectory_samples,
        target_path=route_path,
        road_reference_path=route_path,
        raw_target_path=route_path,
        road_half_width_m=max(4.5, lane_half_width_m * 2.6),
        finish_line=finish_line,
        path_tolerance_m=path_tolerance_m,
        offroad_margin_m=offroad_margin_m,
        lane_half_width_m=lane_half_width_m,
        lane_guidance_active=True,
    )
    opposite_lane_count = _count_opposite_lane_samples(
        world_map=world_map,
        samples=trajectory_samples,
        route_path=route_path,
        route_metadata=route_metadata,
    )
    sample_count = max(1, summary.sample_count)
    opposite_lane_ratio = opposite_lane_count / sample_count
    destination_reached = bool(destination_reached_override or summary.crossed_finish_line)
    failure_reason = None
    success = False
    if collision_count > 0:
        failure_reason = "collision"
    elif summary.offroad_sample_count > 0:
        failure_reason = "course_departure"
    elif opposite_lane_ratio >= 0.30:
        failure_reason = "wrong_lane"
    elif not destination_reached:
        failure_reason = "not_finished"
    else:
        success = True
    driving_score = compute_episode_driving_score(
        completion_ratio=summary.completion_ratio,
        path_tracking_score=summary.path_tracking_score,
        crossed_finish_line=destination_reached,
        offroad_ratio=summary.offroad_ratio,
        collision_count=collision_count,
        failure_reason=failure_reason,
        success=success,
        lane_discipline_score=summary.lane_discipline_score,
        lane_departure_ratio=summary.lane_departure_ratio,
        opposite_lane_ratio=opposite_lane_ratio,
    )
    return summary, opposite_lane_ratio, success, failure_reason, driving_score


def _build_goal_score_overlay(
    *,
    world_map: Any,
    vehicle: Any,
    collision_count: int,
    trajectory_samples: list[TrajectorySample],
    route_path: list[PathPoint],
    route_metadata: list[dict[str, Any]],
    lane_half_width_m: float,
    path_tolerance_m: float,
    offroad_margin_m: float,
    started_monotonic: float,
    last_sample_time_sec: float,
    destination_reached_override: bool,
) -> tuple[FinishScoreOverlay, bool, float]:
    last_sample_time_sec = _record_trajectory_sample(
        trajectory_samples,
        vehicle,
        started_monotonic,
        last_sample_time_sec,
        force=True,
        sample_interval_sec=0.0,
    )
    summary, opposite_lane_ratio, success, failure_reason, driving_score = _evaluate_practical_run(
        world_map=world_map,
        collision_count=collision_count,
        trajectory_samples=trajectory_samples,
        route_path=route_path,
        route_metadata=route_metadata,
        lane_half_width_m=lane_half_width_m,
        path_tolerance_m=path_tolerance_m,
        offroad_margin_m=offroad_margin_m,
        destination_reached_override=destination_reached_override,
    )
    time_sec = trajectory_samples[-1].timestamp_sec if trajectory_samples else 0.0
    return (
        FinishScoreOverlay(
            success=success,
            failure_reason=failure_reason,
            driving_score=driving_score,
            time_sec=time_sec,
            collision_count=collision_count,
            path_match_score=summary.path_match_score,
            path_tracking_score=summary.path_tracking_score,
            lane_discipline_score=summary.lane_discipline_score,
            lane_departure_ratio=summary.lane_departure_ratio,
            opposite_lane_ratio=opposite_lane_ratio,
            offroad_ratio=summary.offroad_ratio,
            completion_ratio=summary.completion_ratio,
            mean_lateral_error_m=summary.mean_lateral_error_m,
        ),
        bool(destination_reached_override or summary.crossed_finish_line),
        last_sample_time_sec,
    )


def _calculate_goal_result_async(
    *,
    result_queue: "queue.Queue[tuple[FinishScoreOverlay | None, Path | None, str | None]]",
    scenario_payload: dict[str, Any],
    scenario_path: Path,
    world_map: Any,
    collision_count: int,
    trajectory_samples: list[TrajectorySample],
    route_path: list[PathPoint],
    route_metadata: list[dict[str, Any]],
    lane_half_width_m: float,
    path_tolerance_m: float,
    offroad_margin_m: float,
    result_dir: Path,
    vehicle_profile: Any,
    driver_profile: Any,
    input_binding: Any,
    blueprint_id: str,
    traffic_summary: dict[str, int],
    pedestrian_summary: dict[str, int],
) -> None:
    try:
        summary, opposite_lane_ratio, success, failure_reason, driving_score = _evaluate_practical_run(
            world_map=world_map,
            collision_count=collision_count,
            trajectory_samples=trajectory_samples,
            route_path=route_path,
            route_metadata=route_metadata,
            lane_half_width_m=lane_half_width_m,
            path_tolerance_m=path_tolerance_m,
            offroad_margin_m=offroad_margin_m,
            destination_reached_override=True,
        )
        overlay = FinishScoreOverlay(
            success=success,
            failure_reason=failure_reason,
            driving_score=driving_score,
            time_sec=(trajectory_samples[-1].timestamp_sec if trajectory_samples else 0.0),
            collision_count=collision_count,
            path_match_score=summary.path_match_score,
            path_tracking_score=summary.path_tracking_score,
            lane_discipline_score=summary.lane_discipline_score,
            lane_departure_ratio=summary.lane_departure_ratio,
            opposite_lane_ratio=opposite_lane_ratio,
            offroad_ratio=summary.offroad_ratio,
            completion_ratio=summary.completion_ratio,
            mean_lateral_error_m=summary.mean_lateral_error_m,
        )
        saved_path = _save_practical_result(
            scenario_payload=scenario_payload,
            scenario_path=scenario_path,
            world_map=world_map,
            vehicle=None,
            collision_count=collision_count,
            trajectory_samples=trajectory_samples,
            route_path=route_path,
            route_metadata=route_metadata,
            lane_half_width_m=lane_half_width_m,
            path_tolerance_m=path_tolerance_m,
            offroad_margin_m=offroad_margin_m,
            result_dir=result_dir,
            vehicle_profile=vehicle_profile,
            driver_profile=driver_profile,
            input_binding=input_binding,
            blueprint_id=blueprint_id,
            end_reason="destination_reached",
            traffic_summary=traffic_summary,
            pedestrian_summary=pedestrian_summary,
            destination_reached_override=True,
        )
        result_queue.put((overlay, saved_path, None))
    except Exception as exc:
        result_queue.put((None, None, f"{type(exc).__name__}: {exc}"))


def main() -> None:
    args = parse_args()
    random.seed(args.random_seed)
    scenario_path = args.scenario_path.resolve()
    scenario_payload = _load_scenario_payload(scenario_path)

    width, height = [int(value) for value in args.resolution.split("x")]
    pygame.init()
    pygame.font.init()
    display = pygame.display.set_mode((width, height))
    pygame.display.set_caption("AutoDrive Practical Scenario Demo")
    font = pygame.font.SysFont("Consolas", 20)
    overlay_title_font = pygame.font.SysFont("Consolas", 28, bold=True)
    overlay_body_font = pygame.font.SysFont("Consolas", 20)

    vehicle = None
    camera = None
    collision_sensor = None
    traffic_vehicles: list[Any] = []
    pedestrian_walkers: list[Any] = []
    pedestrian_controllers: list[Any] = []
    traffic_summary = {
        "requested_count": 0,
        "spawned_count": 0,
        "available_spawn_points": 0,
        "attempted_spawn_points": 0,
    }
    pedestrian_summary = {
        "requested_count": 0,
        "spawned_count": 0,
        "controller_count": 0,
        "attempted_spawn_locations": 0,
    }
    external_driver_process = None
    external_driver_backend = str(args.driver_backend).strip().lower() or "manual"
    if external_driver_backend == "manual":
        if str(args.driver_module_path or "").strip():
            external_driver_backend = "external_module"
        elif str(args.external_driver_command or "").strip():
            external_driver_backend = "external_command"
    external_driver_active = external_driver_backend == "external_command"
    external_module_active = external_driver_backend == "external_module"
    driver_module = None
    driver_control_override = None
    driver_control_hint = ""
    vehicle_config_overrides = load_vehicle_integration_config(args.vehicle_config_path)
    resolved_blueprint_filter = (
        str(vehicle_config_overrides.get("blueprint_filter", "")).strip()
        or args.blueprint_filter
    )
    resolved_preferred_blueprint_id = (
        args.preferred_blueprint_id
        or str(vehicle_config_overrides.get("preferred_blueprint_id", "")).strip()
        or None
    )
    resolved_role_name = (
        str(args.role_name or "").strip()
        or str(vehicle_config_overrides.get("role_name", "")).strip()
        or "hero"
    )
    resolved_color = str(vehicle_config_overrides.get("color", "")).strip() or None

    vehicle_profile = create_builtin_vehicle_profile(
        profile_name="practical_scenario_demo_vehicle",
        blueprint_filter=resolved_blueprint_filter,
        preferred_blueprint_id=resolved_preferred_blueprint_id,
        role_name=resolved_role_name,
        color=resolved_color,
        notes="Application-owned practical-stage ego vehicle profile for Town scenario validation.",
    )
    if external_module_active:
        if not str(args.driver_module_path or "").strip():
            print("External module driving was enabled, but no driver module file was provided.")
            raise SystemExit(1)
        driver_module, driver_control_override, driver_control_hint = load_driver_control_module(
            str(args.driver_module_path)
        )
        driver_profile = create_external_driver_profile(
            profile_name="practical_external_module_driver",
            external_entrypoint=args.driver_module_path,
            notes=(
                "User-supplied Python keyboard-control module loaded by the AED app "
                "for a quick Practical Stage integration check."
            ),
            runtime_options={
                "backend": "external_module",
                "driver_module_path": args.driver_module_path,
            },
        )
    elif external_driver_active:
        if not str(args.external_driver_command or "").strip():
            print("External driver integration was enabled, but no launch command was provided.")
            raise SystemExit(1)
        driver_profile = create_external_driver_profile(
            profile_name="practical_external_driver",
            external_entrypoint=args.external_driver_command,
            notes=(
                "User-supplied external driving command launched after the AED app spawns "
                "the ego vehicle in the selected Town scenario."
            ),
            runtime_options={
                "backend": "external_command",
                "working_dir": args.external_driver_working_dir,
                "startup_wait_seconds": args.external_driver_startup_wait,
            },
        )
    else:
        driver_profile = create_manual_driver_profile(
            notes="Manual keyboard driving backend used for the Practical Stage Town route baseline.",
        )
    input_binding = create_split_input_binding(
        vehicle_profile=vehicle_profile,
        driver_profile=driver_profile,
        notes="Practical Stage still owns scenario setup while leaving the driving backend replaceable.",
    )

    trajectory_samples: list[TrajectorySample] = []
    last_sample_time_sec = -1.0
    started_monotonic = time.monotonic()
    saved_result_path: Path | None = None
    goal_score_overlay: FinishScoreOverlay | None = None
    goal_score_pending = False
    goal_reached_for_result = False
    show_result_comparison = False
    show_adaptation_preview = False
    comparison_panel_top = 18
    adaptation_panel_top = 214
    goal_result_queue: "queue.Queue[tuple[FinishScoreOverlay | None, Path | None, str | None]]" = queue.Queue()
    goal_result_worker: threading.Thread | None = None

    try:
        carla, client, world = create_client(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            pythonapi_path=args.pythonapi_path,
        )
        requested_town_id = str(scenario_payload["town_id"])
        current_map_name = ""
        try:
            current_map_name = str(world.get_map().name)
        except Exception:
            current_map_name = ""
        if _map_name_matches_town(current_map_name, requested_town_id):
            print(f"Reusing already loaded Town map: {current_map_name}")
        else:
            world = client.load_world(requested_town_id)
        weather_preset = resolve_practical_weather(str(scenario_payload.get("weather_preset", "clear_noon")))
        world.set_weather(getattr(carla.WeatherParameters, weather_preset.carla_attribute))
        world_map = world.get_map()

        spawn_transform = _build_transform_from_payload(
            carla,
            dict(scenario_payload["spawn"]),
            z_offset=args.spawn_height_offset,
        )
        destination_transform = _build_transform_from_payload(
            carla,
            dict(scenario_payload["destination"]),
            z_offset=0.0,
        )
        route_path, route_metadata = _build_path_points(list(scenario_payload["route_waypoints"]))
        lane_half_width_m = _estimate_lane_half_width(world_map, spawn_transform, destination_transform)

        blueprint = resolve_vehicle_blueprint_for_profile(
            world=world,
            vehicle_profile=vehicle_profile,
            preferred_blueprint_id=resolved_preferred_blueprint_id,
        )
        vehicle = world.spawn_actor(blueprint, spawn_transform)
        traffic_vehicles, traffic_summary = spawn_autopilot_traffic(
            world,
            client,
            desired_count=int(scenario_payload.get("traffic_vehicle_count", 0)),
            traffic_manager_port=args.traffic_manager_port,
            random_seed=args.random_seed,
            excluded_locations=_build_traffic_excluded_locations(
                carla,
                spawn_transform,
                destination_transform,
                route_path,
            ),
            min_spawn_distance_m=18.0,
        )
        pedestrian_walkers, pedestrian_controllers, pedestrian_summary = spawn_pedestrian_traffic(
            world,
            desired_count=int(scenario_payload.get("pedestrian_count", 0)),
            random_seed=args.random_seed,
            excluded_locations=_build_traffic_excluded_locations(
                carla,
                spawn_transform,
                destination_transform,
                route_path,
            ),
            min_spawn_distance_m=12.0,
        )
        if external_driver_active:
            print("Launching external driving command for the app-owned Town ego vehicle...")
            external_driver_process = launch_external_driver_process(
                str(args.external_driver_command),
                working_dir=args.external_driver_working_dir,
                environment=build_external_driver_environment(
                    host=args.host,
                    port=args.port,
                    role_name=vehicle_profile.role_name,
                    training_stage="practical",
                    pythonapi_path=args.pythonapi_path,
                    blueprint_id=blueprint.id,
                    scenario_path=str(scenario_path),
                    town_id=str(scenario_payload.get("town_id", "")),
                    weather_preset=str(scenario_payload.get("weather_preset", "")),
                ),
                startup_wait_seconds=float(args.external_driver_startup_wait),
            )
        collision_sensor, collision_state = attach_collision_sensor(
            world,
            vehicle,
            cooldown_seconds=args.collision_cooldown_seconds,
        )
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

        if args.spectator_mode == "fixed-overview":
            _set_route_overview_spectator(
                carla=carla,
                world=world,
                route_points=route_path,
                height=args.overview_height,
                pitch=args.overview_pitch,
            )

        print("Practical scenario vehicle spawned successfully.")
        print(f"Scenario file: {scenario_path}")
        print(f"Loaded map: {world_map.name}")
        print(f"Scenario id: {scenario_payload['scenario_id']}")
        print(
            "Scenario context: "
            f"town={scenario_payload['town_id']}, weather={scenario_payload.get('weather_preset')}, "
            f"vehicles={scenario_payload.get('traffic_vehicle_count')}, pedestrians={scenario_payload.get('pedestrian_count')}"
        )
        print(
            "Route summary: "
            f"target~{scenario_payload.get('route_length_hint_m')}m, "
            f"actual~{scenario_payload.get('route_metrics', {}).get('actual_route_length_m', 0.0)}m, "
            f"junction_focus={scenario_payload.get('junction_focus')}"
        )
        print(
            "Background traffic: "
            f"requested={traffic_summary['requested_count']}, spawned={traffic_summary['spawned_count']}, "
            f"available_spawn_points={traffic_summary['available_spawn_points']}"
        )
        print(
            "Pedestrian traffic: "
            f"requested={pedestrian_summary['requested_count']}, spawned={pedestrian_summary['spawned_count']}, "
            f"controllers={pedestrian_summary['controller_count']}"
        )
        print(f"Vehicle blueprint: {blueprint.id}")
        print(f"Vehicle profile: {vehicle_profile.describe()}")
        print(f"Driver profile: {driver_profile.describe()}")
        print(f"Input binding: {input_binding.describe()}")
        if args.vehicle_config_path:
            print(f"Vehicle config file: {args.vehicle_config_path}")
        if external_module_active:
            print(
                "External driver module: "
                f"{args.driver_module_path} "
                f"(hint={driver_control_hint or 'custom keyboard mapping'})"
            )
        if external_driver_active:
            print(
                "External driver command: "
                f"{args.external_driver_command} "
                f"(cwd={args.external_driver_working_dir or 'current'}, "
                f"wait={float(args.external_driver_startup_wait):.1f}s)"
            )
            print("Controls: ESC exit (external driving stack owns throttle / steer / brake)")
        elif external_module_active:
            print(
                "Controls: "
                f"{driver_control_hint or 'custom keyboard mapping from external module'}"
            )
        else:
            print("Controls: W/A/S/D or arrows, Space, ESC")

        control = carla.VehicleControl()
        spectator_state = None
        clock = pygame.time.Clock()
        end_time = None if args.duration_seconds <= 0 else time.time() + args.duration_seconds

        def _consume_goal_result(*, block: bool = False) -> None:
            nonlocal saved_result_path, goal_score_overlay, goal_score_pending
            try:
                if block:
                    overlay, saved_path, error_text = goal_result_queue.get(timeout=5.0)
                else:
                    overlay, saved_path, error_text = goal_result_queue.get_nowait()
            except queue.Empty:
                return

            goal_score_pending = False
            if error_text:
                print(f"Goal score background evaluation failed: {error_text}")
                return
            goal_score_overlay = overlay
            if saved_path is not None:
                saved_result_path = saved_path
            if overlay is not None:
                print(
                    "Goal score ready. "
                    f"Runtime score={overlay.driving_score * 100.0:.1f}, "
                    f"outcome={'success' if overlay.success else overlay.failure_reason}"
                )

        def finalize_run(end_reason: str, *, destination_reached_override: bool = False) -> None:
            nonlocal saved_result_path, last_sample_time_sec, goal_score_pending
            if saved_result_path is not None:
                return
            if goal_score_pending and goal_result_worker is not None:
                goal_result_worker.join()
                _consume_goal_result(block=False)
                if saved_result_path is not None:
                    return
            if vehicle is None:
                return
            last_sample_time_sec = _record_trajectory_sample(
                trajectory_samples,
                vehicle,
                started_monotonic,
                last_sample_time_sec,
                force=True,
                sample_interval_sec=0.0,
            )
            saved_result_path = _save_practical_result(
                scenario_payload=scenario_payload,
                scenario_path=scenario_path,
                world_map=world_map,
                vehicle=vehicle,
                collision_count=int(collision_state.get("count", 0)),
                trajectory_samples=trajectory_samples,
                route_path=route_path,
                route_metadata=route_metadata,
                lane_half_width_m=lane_half_width_m,
                path_tolerance_m=args.path_tolerance,
                offroad_margin_m=args.offroad_margin,
                result_dir=args.result_dir,
                vehicle_profile=vehicle_profile,
                driver_profile=driver_profile,
                input_binding=input_binding,
                blueprint_id=blueprint.id,
                end_reason=end_reason,
                traffic_summary=traffic_summary,
                pedestrian_summary=pedestrian_summary,
                destination_reached_override=(
                    destination_reached_override or goal_reached_for_result
                ),
            )

        while end_time is None or time.time() < end_time:
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    finalize_run("window_closed")
                    return
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        finalize_run("user_exit")
                        return
                    if goal_score_overlay is not None and event.key in (pygame.K_1, pygame.K_KP1):
                        show_result_comparison = not show_result_comparison
                    if goal_score_overlay is not None and event.key in (pygame.K_2, pygame.K_KP2):
                        show_adaptation_preview = not show_adaptation_preview

            if external_driver_active:
                if external_driver_process is not None and external_driver_process.poll() is not None:
                    print("External driving command exited. Finishing the current Practical run.")
                    finalize_run("external_driver_exit")
                    return
            elif external_module_active:
                keys = pygame.key.get_pressed()
                control = driver_control_override(keys, control, pygame)
                vehicle.apply_control(control)
            else:
                keys = pygame.key.get_pressed()
                control = apply_keyboard_control(keys, control)
                vehicle.apply_control(control)
            last_sample_time_sec = _record_trajectory_sample(
                trajectory_samples,
                vehicle,
                started_monotonic,
                last_sample_time_sec,
                force=False,
                sample_interval_sec=args.trajectory_sample_interval,
            )
            _consume_goal_result(block=False)

            if args.spectator_mode == "follow":
                spectator_state = update_follow_vehicle_spectator(
                    carla=carla,
                    world=world,
                    vehicle=vehicle,
                    follow_distance=args.follow_distance,
                    follow_height=args.follow_height,
                    follow_pitch=args.follow_pitch,
                    smoothing=args.follow_smoothing,
                    state=spectator_state,
                )

            _draw_destination_marker(carla, world, destination_transform)

            if camera_view.surface is not None:
                display.blit(camera_view.surface, (0, 0))
            else:
                display.fill((30, 30, 30))

            _draw_destination_goal_overlay(
                display,
                pygame=pygame,
                carla=carla,
                camera=camera,
                destination_transform=destination_transform,
            )

            transform = vehicle.get_transform()
            target_projection = project_point_to_path(
                float(transform.location.x),
                float(transform.location.y),
                route_path,
            )
            remaining_m = max(0.0, route_path[-1].s - target_projection.progress_s)
            goal_distance_m = math.hypot(
                float(transform.location.x) - float(destination_transform.location.x),
                float(transform.location.y) - float(destination_transform.location.y),
            )
            goal_trigger_distance_m = max(10.0, lane_half_width_m * 3.5)
            route_near_complete = target_projection.progress_ratio >= 0.97
            goal_reached_now = route_near_complete and goal_distance_m <= goal_trigger_distance_m
            if (
                goal_reached_now
                and not goal_reached_for_result
                and not goal_score_pending
                and goal_score_overlay is None
            ):
                goal_reached_for_result = True
                last_sample_time_sec = _record_trajectory_sample(
                    trajectory_samples,
                    vehicle,
                    started_monotonic,
                    last_sample_time_sec,
                    force=True,
                    sample_interval_sec=0.0,
                )
                goal_score_pending = True
                goal_result_worker = threading.Thread(
                    target=_calculate_goal_result_async,
                    kwargs={
                        "result_queue": goal_result_queue,
                        "scenario_payload": dict(scenario_payload),
                        "scenario_path": scenario_path,
                        "world_map": world_map,
                        "collision_count": int(collision_state.get("count", 0)),
                        "trajectory_samples": list(trajectory_samples),
                        "route_path": list(route_path),
                        "route_metadata": list(route_metadata),
                        "lane_half_width_m": lane_half_width_m,
                        "path_tolerance_m": args.path_tolerance,
                        "offroad_margin_m": args.offroad_margin,
                        "result_dir": args.result_dir,
                        "vehicle_profile": vehicle_profile,
                        "driver_profile": driver_profile,
                        "input_binding": input_binding,
                        "blueprint_id": blueprint.id,
                        "traffic_summary": dict(traffic_summary),
                        "pedestrian_summary": dict(pedestrian_summary),
                    },
                    daemon=True,
                )
                goal_result_worker.start()
                print("Goal reached. Calculating score in background...")
            next_maneuver, next_maneuver_distance_m = _resolve_next_maneuver(
                target_projection.progress_s,
                route_path,
                route_metadata,
            )
            destination_hint = _format_destination_hint(
                _destination_bearing_deg(transform, destination_transform)
            )
            lines = [
                f"Town: {scenario_payload['town_id']}",
                f"Scenario: {scenario_payload['scenario_id']}",
                f"Vehicle: {blueprint.id}",
                f"Speed: {calculate_speed_kmh(vehicle):5.1f} km/h",
                (
                    "Route: "
                    f"progress {target_projection.progress_ratio * 100.0:5.1f}% / "
                    f"lane error {target_projection.distance_m:4.2f}m"
                ),
                (
                    "Destination: "
                    f"remaining {remaining_m:5.1f}m / "
                    f"goal {goal_distance_m:4.1f}m / "
                    f"collisions {int(collision_state.get('count', 0))}"
                ),
                (
                    "Guidance: "
                    f"goal {destination_hint} / "
                    f"next {next_maneuver.lower()} in {next_maneuver_distance_m:4.0f}m"
                ),
                (
                    "Scenario mode: "
                    f"{scenario_payload.get('scenario_mode', 'auto')} / "
                    f"traffic {traffic_summary.get('spawned_count', 0)} / "
                    f"pedestrians {scenario_payload.get('pedestrian_count', 0)}"
                ),
                (
                    "Goal score: calculating in background..."
                    if goal_score_pending
                    else (
                        f"Goal score: {goal_score_overlay.driving_score * 100.0:5.1f} / 100"
                        if goal_score_overlay is not None
                        else "Goal score: -"
                    )
                ),
                (
                    "Controls: ESC / external driver active"
                    if external_driver_active
                    else (
                        f"Controls: {driver_control_hint}"
                        if external_module_active and driver_control_hint
                        else "Controls: W/A/S/D or arrows, Space, ESC"
                    )
                ),
            ]
            if goal_score_overlay is not None:
                lines.append("Review: 1 comparison / 2 next adjustment / ESC exit")
            y = 16
            for line in lines:
                display.blit(font.render(line, True, (255, 255, 255)), (16, y))
                y += 24

            _draw_practical_minimap(
                display,
                vehicle_transform=transform,
                destination_transform=destination_transform,
                route_path=route_path,
                progress_s=target_projection.progress_s,
            )

            if goal_score_overlay is not None:
                _draw_goal_score_overlay(
                    display,
                    width=width,
                    height=height,
                    title_font=overlay_title_font,
                    body_font=overlay_body_font,
                    overlay=goal_score_overlay,
                )
                current_result = build_episode_result_from_overlay(
                    map_id=str(scenario_payload["scenario_id"]),
                    overlay=goal_score_overlay,
                    metadata={
                        "training_stage": "practical",
                        "town_id": scenario_payload.get("town_id"),
                        "traffic_vehicle_count": scenario_payload.get("traffic_vehicle_count"),
                        "pedestrian_count": scenario_payload.get("pedestrian_count"),
                        "route_length_hint_m": scenario_payload.get("route_length_hint_m"),
                        "junction_focus": scenario_payload.get("junction_focus"),
                    },
                )
                if show_result_comparison:
                    comparison_lines = build_result_comparison_lines(
                        current_result=current_result,
                        result_dir=args.result_dir.resolve(),
                        exclude_paths=(
                            {saved_result_path.resolve()} if saved_result_path is not None else None
                        ),
                    )
                    draw_review_panel(
                        display,
                        pygame=pygame,
                        width=width,
                        top=comparison_panel_top,
                        anchor="right",
                        title_font=overlay_title_font,
                        body_font=overlay_body_font,
                        title="RESULT COMPARISON (1)",
                        lines=comparison_lines,
                    )
                if show_adaptation_preview:
                    adaptation_lines = build_practical_adaptation_lines(
                        current_result=current_result,
                        traffic_vehicle_count=int(scenario_payload.get("traffic_vehicle_count", 0)),
                        pedestrian_count=int(scenario_payload.get("pedestrian_count", 0)),
                        route_length_hint_m=int(scenario_payload.get("route_length_hint_m", 0)),
                        junction_focus=str(scenario_payload.get("junction_focus", "medium")),
                    )
                    draw_review_panel(
                        display,
                        pygame=pygame,
                        width=width,
                        top=adaptation_panel_top,
                        anchor="right",
                        title_font=overlay_title_font,
                        body_font=overlay_body_font,
                        title="NEXT SCENARIO PREVIEW (2)",
                        lines=adaptation_lines,
                    )
            elif goal_score_pending:
                _draw_goal_pending_overlay(
                    display,
                    width=width,
                    height=height,
                    title_font=overlay_title_font,
                    body_font=overlay_body_font,
                )

            pygame.display.flip()
            clock.tick_busy_loop(60)

        finalize_run("duration_timeout")
    finally:
        terminate_external_driver_process(external_driver_process)
        _stop_sensor(collision_sensor)
        _stop_sensor(camera)
        actors_to_destroy = list(pedestrian_controllers) + list(pedestrian_walkers) + list(traffic_vehicles)
        if collision_sensor is not None:
            actors_to_destroy.append(collision_sensor)
        if camera is not None:
            actors_to_destroy.append(camera)
        if vehicle is not None and not args.keep_vehicle:
            actors_to_destroy.append(vehicle)
        if "carla" in locals() and "client" in locals():
            _destroy_actors_batch(carla, client, actors_to_destroy)
        pygame.quit()


if __name__ == "__main__":
    main()
