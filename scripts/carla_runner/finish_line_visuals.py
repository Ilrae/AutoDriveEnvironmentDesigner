"""Helpers for drawing a visible finish line on top of generated CARLA maps."""

from __future__ import annotations

import math
import time
from typing import Any

from scripts.evaluation.path_metrics import FinishLine, PathPoint

_MARKER_REFRESH_DEADLINES: dict[tuple[int, int, int, int], float] = {}
_CENTERLINE_REFRESH_DEADLINES: dict[tuple[int, int, int, int, int], float] = {}


def _marker_cache_key(world: Any, finish_line: FinishLine) -> tuple[int, int, int, int]:
    """Build a stable cache key so we do not redraw the same marker every frame."""

    return (
        id(world),
        int(round(finish_line.x * 10.0)),
        int(round(finish_line.y * 10.0)),
        int(round(finish_line.heading_rad * 1000.0)),
    )


def _should_refresh_marker(
    world: Any,
    finish_line: FinishLine,
    *,
    refresh_interval_sec: float,
) -> bool:
    """Throttle debug redraws to avoid stacked labels."""

    now_monotonic = time.monotonic()
    cache_key = _marker_cache_key(world, finish_line)
    refresh_deadline = _MARKER_REFRESH_DEADLINES.get(cache_key, 0.0)
    if now_monotonic < refresh_deadline:
        return False

    _MARKER_REFRESH_DEADLINES[cache_key] = now_monotonic + refresh_interval_sec
    expired_keys = [
        key
        for key, deadline in _MARKER_REFRESH_DEADLINES.items()
        if deadline < now_monotonic - 1.0
    ]
    for expired_key in expired_keys:
        _MARKER_REFRESH_DEADLINES.pop(expired_key, None)
    return True


def _centerline_cache_key(
    world: Any,
    path_points: list[PathPoint],
) -> tuple[int, int, int, int, int]:
    """Build a stable cache key for one projected road centerline."""

    first_point = path_points[0]
    last_point = path_points[-1]
    return (
        id(world),
        int(round(first_point.x * 10.0)),
        int(round(first_point.y * 10.0)),
        int(round(last_point.x * 10.0)),
        int(round(last_point.y * 10.0)),
    )


def _should_refresh_centerline(
    world: Any,
    path_points: list[PathPoint],
    *,
    refresh_interval_sec: float,
) -> bool:
    """Throttle road-centerline redraws so the CARLA debug overlay stays stable."""

    if len(path_points) < 2:
        return False

    now_monotonic = time.monotonic()
    cache_key = _centerline_cache_key(world, path_points)
    refresh_deadline = _CENTERLINE_REFRESH_DEADLINES.get(cache_key, 0.0)
    if now_monotonic < refresh_deadline:
        return False

    _CENTERLINE_REFRESH_DEADLINES[cache_key] = now_monotonic + refresh_interval_sec
    expired_keys = [
        key
        for key, deadline in _CENTERLINE_REFRESH_DEADLINES.items()
        if deadline < now_monotonic - 1.0
    ]
    for expired_key in expired_keys:
        _CENTERLINE_REFRESH_DEADLINES.pop(expired_key, None)
    return True

def _resolve_lane_center_offset_m(road_waypoint: Any) -> float:
    """Estimate the current lane-center offset from the OpenDRIVE road reference line."""

    lane_id = int(getattr(road_waypoint, "lane_id", 0))
    lane_width_m = float(getattr(road_waypoint, "lane_width", 0.0))
    if lane_id == 0 or lane_width_m <= 0.0:
        return 0.0

    base_offset_m = (abs(lane_id) - 0.5) * lane_width_m
    if lane_id > 0:
        return -base_offset_m
    return base_offset_m


def _resolve_visual_reference(
    carla: Any,
    world: Any,
    finish_line: FinishLine,
    *,
    line_inset_m: float,
    finish_line_is_road_center: bool,
) -> tuple[float, float, float, float, float, float, float]:
    """Resolve road-centered marker placement data for one finish line."""

    heading_rad = finish_line.heading_rad
    forward_x = math.cos(heading_rad)
    forward_y = math.sin(heading_rad)
    left_x = math.cos(heading_rad + (math.pi / 2.0))
    left_y = math.sin(heading_rad + (math.pi / 2.0))
    road_surface_z = 0.0
    visual_center_x = finish_line.x
    visual_center_y = finish_line.y

    try:
        road_waypoint = world.get_map().get_waypoint(
            carla.Location(
                x=finish_line.x,
                y=finish_line.y,
                z=2.0,
            ),
            project_to_road=True,
            lane_type=carla.LaneType.Driving,
        )
    except Exception:
        road_waypoint = None
    if road_waypoint is not None:
        road_surface_z = float(road_waypoint.transform.location.z)
        if not finish_line_is_road_center:
            lane_center_offset_m = _resolve_lane_center_offset_m(road_waypoint)
            lane_center_location = road_waypoint.transform.location
            visual_center_x = float(lane_center_location.x) - (left_x * lane_center_offset_m)
            visual_center_y = float(lane_center_location.y) - (left_y * lane_center_offset_m)

    half_width_m = max(2.0, finish_line.half_width_m)
    visible_half_width_m = max(1.0, half_width_m - line_inset_m)
    return (
        visual_center_x,
        visual_center_y,
        road_surface_z,
        forward_x,
        forward_y,
        left_x,
        left_y,
    )


def spawn_finish_line_marker_props(
    carla: Any,
    world: Any,
    finish_line: FinishLine,
    *,
    line_inset_m: float = 0.35,
    finish_line_is_road_center: bool = False,
) -> list[Any]:
    """Spawn low-profile finish gate props so the marker stays visible without bloom."""

    (
        visual_center_x,
        visual_center_y,
        road_surface_z,
        forward_x,
        forward_y,
        left_x,
        left_y,
    ) = _resolve_visual_reference(
        carla,
        world,
        finish_line,
        line_inset_m=line_inset_m,
        finish_line_is_road_center=finish_line_is_road_center,
    )
    half_width_m = max(2.0, finish_line.half_width_m)
    visible_half_width_m = max(1.0, half_width_m - line_inset_m)
    blueprint_library = world.get_blueprint_library()
    cone_blueprint_id = "static.prop.trafficcone01"
    lateral_anchor_m = visible_half_width_m + 0.90
    heading_deg = math.degrees(finish_line.heading_rad)

    actor_specs = [
        (0.0, -lateral_anchor_m, cone_blueprint_id, heading_deg, 0.01),
        (0.0, lateral_anchor_m, cone_blueprint_id, heading_deg, 0.01),
    ]

    spawned_actors: list[Any] = []
    for longitudinal_offset_m, lateral_offset_m, blueprint_id, yaw_deg, z_extra_m in actor_specs:
        try:
            blueprint = blueprint_library.find(blueprint_id)
        except Exception:
            continue
        transform = carla.Transform(
            carla.Location(
                x=visual_center_x + (forward_x * longitudinal_offset_m) + (left_x * lateral_offset_m),
                y=visual_center_y + (forward_y * longitudinal_offset_m) + (left_y * lateral_offset_m),
                z=road_surface_z + z_extra_m,
            ),
            carla.Rotation(
                pitch=0.0,
                yaw=yaw_deg,
                roll=0.0,
            ),
        )
        actor = world.try_spawn_actor(blueprint, transform)
        if actor is None:
            continue
        try:
            actor.set_simulate_physics(False)
        except Exception:
            pass
        spawned_actors.append(actor)

    return spawned_actors


def _build_finish_strip_tile_world_points(
    carla: Any,
    *,
    visual_center_x: float,
    visual_center_y: float,
    road_surface_z: float,
    forward_x: float,
    forward_y: float,
    left_x: float,
    left_y: float,
    visible_half_width_m: float,
    stripe_depth_m: float,
    tile_width_m: float,
    z_offset_m: float,
) -> list[tuple[bool, list[Any]]]:
    """Build alternating world-space quads for one finish stripe."""

    tile_quads: list[tuple[bool, list[Any]]] = []
    lateral_start_m = -visible_half_width_m
    tile_index = 0
    half_depth_m = stripe_depth_m * 0.5
    while lateral_start_m < visible_half_width_m - 1e-6:
        lateral_end_m = min(visible_half_width_m, lateral_start_m + tile_width_m)

        def make_location(
            longitudinal_offset_m: float,
            lateral_offset_m: float,
        ) -> Any:
            return carla.Location(
                x=visual_center_x + (forward_x * longitudinal_offset_m) + (left_x * lateral_offset_m),
                y=visual_center_y + (forward_y * longitudinal_offset_m) + (left_y * lateral_offset_m),
                z=road_surface_z + z_offset_m,
            )

        tile_quads.append(
            (
                tile_index % 2 == 0,
                [
                    make_location(-half_depth_m, lateral_start_m),
                    make_location(-half_depth_m, lateral_end_m),
                    make_location(half_depth_m, lateral_end_m),
                    make_location(half_depth_m, lateral_start_m),
                ],
            )
        )
        lateral_start_m = lateral_end_m
        tile_index += 1
    return tile_quads


def _project_world_point_to_screen(
    location: Any,
    *,
    camera: Any,
    width: int,
    height: int,
) -> tuple[float, float] | None:
    """Project one CARLA world point into pygame screen coordinates."""

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


def _iter_dashed_path_segments(
    path_points: list[PathPoint],
    *,
    dash_length_m: float,
    gap_length_m: float,
) -> list[tuple[PathPoint, PathPoint]]:
    """Return sampled polyline segments that belong to visible dashed center marks."""

    if len(path_points) < 2:
        return []

    cycle_length_m = max(0.2, dash_length_m + gap_length_m)
    visible_segments: list[tuple[PathPoint, PathPoint]] = []
    for start_point, end_point in zip(path_points[:-1], path_points[1:]):
        delta_s = end_point.s - start_point.s
        if delta_s <= 1e-6:
            continue
        midpoint_s = start_point.s + (0.5 * delta_s)
        if (midpoint_s % cycle_length_m) > dash_length_m:
            continue
        visible_segments.append((start_point, end_point))
    return visible_segments


def draw_centerline_marker(
    carla: Any,
    world: Any,
    path_points: list[PathPoint],
    *,
    dash_length_m: float = 2.6,
    gap_length_m: float = 1.8,
    z_offset_m: float = 0.04,
    thickness_m: float = 0.06,
    life_time_sec: float = 0.28,
    refresh_interval_sec: float = 0.18,
) -> None:
    """Draw a muted dashed road centerline in the CARLA world debug view."""

    if not _should_refresh_centerline(
        world,
        path_points,
        refresh_interval_sec=refresh_interval_sec,
    ):
        return None

    dash_segments = _iter_dashed_path_segments(
        path_points,
        dash_length_m=dash_length_m,
        gap_length_m=gap_length_m,
    )
    centerline_color = carla.Color(196, 168, 68)
    for start_point, end_point in dash_segments:
        world.debug.draw_line(
            carla.Location(
                x=float(start_point.x),
                y=float(start_point.y),
                z=z_offset_m,
            ),
            carla.Location(
                x=float(end_point.x),
                y=float(end_point.y),
                z=z_offset_m,
            ),
            thickness=thickness_m,
            color=centerline_color,
            life_time=life_time_sec,
            persistent_lines=False,
        )
    return None


def draw_centerline_overlay(
    display: Any,
    *,
    pygame: Any,
    carla: Any,
    camera: Any,
    path_points: list[PathPoint],
    dash_length_m: float = 2.6,
    gap_length_m: float = 1.8,
    z_offset_m: float = 0.05,
    outline_width_px: int = 5,
    line_width_px: int = 3,
) -> None:
    """Project a dashed road centerline onto the pygame chase-camera image."""

    if display is None or camera is None or len(path_points) < 2:
        return None

    width = int(display.get_width())
    height = int(display.get_height())
    outline_color = (96, 74, 24)
    center_color = (214, 184, 76)

    dash_segments = _iter_dashed_path_segments(
        path_points,
        dash_length_m=dash_length_m,
        gap_length_m=gap_length_m,
    )
    for start_point, end_point in dash_segments:
        start_screen = _project_world_point_to_screen(
            carla.Location(
                x=float(start_point.x),
                y=float(start_point.y),
                z=z_offset_m,
            ),
            camera=camera,
            width=width,
            height=height,
        )
        end_screen = _project_world_point_to_screen(
            carla.Location(
                x=float(end_point.x),
                y=float(end_point.y),
                z=z_offset_m,
            ),
            camera=camera,
            width=width,
            height=height,
        )
        if start_screen is None or end_screen is None:
            continue
        pygame.draw.line(
            display,
            outline_color,
            start_screen,
            end_screen,
            outline_width_px,
        )
        pygame.draw.line(
            display,
            center_color,
            start_screen,
            end_screen,
            line_width_px,
        )
    return None


def draw_finish_line_overlay(
    display: Any,
    *,
    pygame: Any,
    carla: Any,
    world: Any,
    camera: Any,
    finish_line: FinishLine,
    line_inset_m: float = 0.35,
    stripe_depth_m: float = 0.70,
    tile_width_m: float = 0.85,
    z_offset_m: float = 0.035,
    finish_line_is_road_center: bool = False,
) -> None:
    """Draw a non-glowing checker stripe onto the pygame camera image."""

    if display is None or camera is None:
        return None

    (
        visual_center_x,
        visual_center_y,
        road_surface_z,
        forward_x,
        forward_y,
        left_x,
        left_y,
    ) = _resolve_visual_reference(
        carla,
        world,
        finish_line,
        line_inset_m=line_inset_m,
        finish_line_is_road_center=finish_line_is_road_center,
    )
    visible_half_width_m = max(1.0, max(2.0, finish_line.half_width_m) - line_inset_m)
    tile_quads = _build_finish_strip_tile_world_points(
        carla,
        visual_center_x=visual_center_x,
        visual_center_y=visual_center_y,
        road_surface_z=road_surface_z,
        forward_x=forward_x,
        forward_y=forward_y,
        left_x=left_x,
        left_y=left_y,
        visible_half_width_m=visible_half_width_m,
        stripe_depth_m=stripe_depth_m,
        tile_width_m=tile_width_m,
        z_offset_m=z_offset_m,
    )
    width = int(display.get_width())
    height = int(display.get_height())
    light_color = (220, 220, 220)
    dark_color = (32, 32, 32)
    outline_color = (120, 120, 120)

    for is_light_tile, world_points in tile_quads:
        screen_points = [
            _project_world_point_to_screen(
                point,
                camera=camera,
                width=width,
                height=height,
            )
            for point in world_points
        ]
        if any(projected_point is None for projected_point in screen_points):
            continue
        polygon = [(point[0], point[1]) for point in screen_points if point is not None]
        if len(polygon) != 4:
            continue
        pygame.draw.polygon(
            display,
            light_color if is_light_tile else dark_color,
            polygon,
        )
        pygame.draw.polygon(
            display,
            outline_color,
            polygon,
            width=1,
        )
    return None


def draw_finish_line_marker(
    carla: Any,
    world: Any,
    finish_line: FinishLine,
    *,
    line_inset_m: float = 0.35,
    label_height_m: float = 1.8,
    life_time_sec: float = 0.30,
    refresh_interval_sec: float = 0.20,
    finish_line_is_road_center: bool = False,
) -> None:
    """Draw only a simple FINISH world label without a bright line."""

    if not _should_refresh_marker(
        world,
        finish_line,
        refresh_interval_sec=refresh_interval_sec,
    ):
        return None

    (
        visual_center_x,
        visual_center_y,
        road_surface_z,
        _forward_x,
        _forward_y,
        _left_x,
        _left_y,
    ) = _resolve_visual_reference(
        carla,
        world,
        finish_line,
        line_inset_m=line_inset_m,
        finish_line_is_road_center=finish_line_is_road_center,
    )
    world.debug.draw_string(
        carla.Location(
            x=visual_center_x,
            y=visual_center_y,
            z=road_surface_z + label_height_m,
        ),
        "FINISH",
        draw_shadow=False,
        color=carla.Color(235, 235, 235),
        life_time=life_time_sec,
        persistent_lines=False,
    )

    return None
