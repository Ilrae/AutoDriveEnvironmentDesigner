"""Spawn a vehicle on the generated track and drive it manually with pygame."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import datetime
import math
from pathlib import Path
import random
import sys
import time
from typing import Any

import numpy as np
import pygame

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.carla_runner.carla_utils import create_client
from scripts.carla_runner.driver_profiles import create_manual_driver_profile
from scripts.carla_runner.input_bindings import create_split_input_binding
from scripts.carla_runner.load_xodr_in_carla import (
    create_generation_parameters,
    load_opendrive_world,
)
from scripts.carla_runner.simple_track_driver import build_centered_spawn_transform
from scripts.carla_runner.vehicle_profiles import (
    VehicleProfile,
    create_builtin_vehicle_profile,
    resolve_vehicle_blueprint_for_profile,
)
from scripts.carla_runner.vehicle_utils import (
    destroy_actor,
    select_spawn_point,
)
from scripts.map_generator.level_generator import generate_map_from_level


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a stadium track, load it in CARLA, spawn a vehicle, "
            "and let the user drive it manually with keyboard controls."
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
        help="Optional map identifier. If omitted, a timestamp-based id is used.",
    )
    parser.add_argument(
        "--level",
        type=float,
        default=0.3,
        help="Difficulty level used for stadium track generation.",
    )
    parser.add_argument(
        "--curve-direction",
        choices=("left", "right"),
        default="left",
        help="Direction of the generated oval track turns.",
    )
    parser.add_argument(
        "--next-level-step",
        type=float,
        default=0.1,
        help="Difficulty increase applied whenever the next map is requested.",
    )
    parser.add_argument(
        "--no-alternate-direction",
        action="store_true",
        help="Keep the same turn direction for every newly generated map.",
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
        help="Directory where generation manifests are stored.",
    )
    parser.add_argument(
        "--demo-lane-width",
        type=float,
        default=6.5,
        help="Lane width used for the manual-drive demo map.",
    )
    parser.add_argument(
        "--demo-straight-length",
        type=float,
        default=240.0,
        help="Straight segment length used for the manual-drive demo map.",
    )
    parser.add_argument(
        "--demo-track-radius",
        type=float,
        default=90.0,
        help="Turn radius used for the manual-drive demo map.",
    )
    parser.add_argument(
        "--blueprint-filter",
        default="vehicle.*",
        help="Blueprint filter for selecting a CARLA built-in vehicle.",
    )
    parser.add_argument(
        "--vehicle-profile-name",
        default="builtin_manual_demo_vehicle",
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
        help="Server window spectator mode. 'follow' trails the car, 'fixed-overview' shows the whole track.",
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
        help="Smoothing factor for the server spectator follow camera. Higher values react faster.",
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
        "--show-minimap",
        action="store_true",
        help="Show an optional top-left minimap inside the pygame window. Disabled by default.",
    )
    parser.add_argument(
        "--minimap-resolution",
        default="320x180",
        help="Top-left minimap overlay resolution inside the pygame window.",
    )
    parser.add_argument(
        "--minimap-margin",
        type=int,
        default=16,
        help="Top-left margin for the minimap overlay in pixels.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=0.0,
        help="Optional auto-exit duration. Use 0 or negative for unlimited driving.",
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


def build_map_id(explicit_map_id: str | None) -> str:
    if explicit_map_id:
        return explicit_map_id
    return "manual_track_demo_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def build_follow_vehicle_spectator_transform(
    carla: object,
    vehicle: object,
    follow_distance: float,
    follow_height: float,
    follow_pitch: float,
) -> object:
    transform = vehicle.get_transform()
    yaw_rad = math.radians(transform.rotation.yaw)
    spectator_location = carla.Location(
        x=transform.location.x - (follow_distance * math.cos(yaw_rad)),
        y=transform.location.y - (follow_distance * math.sin(yaw_rad)),
        z=transform.location.z + follow_height,
    )
    spectator_rotation = carla.Rotation(
        pitch=follow_pitch,
        yaw=transform.rotation.yaw,
        roll=0.0,
    )
    return carla.Transform(spectator_location, spectator_rotation)


def build_fixed_overview_transform(
    carla: object,
    straight_length: float,
    track_radius: float,
    curve_direction: str,
    overview_height: float,
    overview_pitch: float,
) -> object:
    center_y = track_radius if curve_direction == "left" else -track_radius
    center_x = straight_length / 2.0

    auto_height = max(
        140.0,
        (max(straight_length, track_radius * 2.0) * 1.15) + 40.0,
    )
    camera_height = overview_height if overview_height > 0 else auto_height

    spectator_transform = carla.Transform(
        carla.Location(x=center_x, y=center_y, z=camera_height),
        carla.Rotation(pitch=overview_pitch, yaw=0.0, roll=0.0),
    )
    return spectator_transform


def set_fixed_overview_spectator(
    carla: object,
    world: object,
    straight_length: float,
    track_radius: float,
    curve_direction: str,
    overview_height: float,
    overview_pitch: float,
) -> None:
    world.get_spectator().set_transform(
        build_fixed_overview_transform(
            carla=carla,
            straight_length=straight_length,
            track_radius=track_radius,
            curve_direction=curve_direction,
            overview_height=overview_height,
            overview_pitch=overview_pitch,
        )
    )


def _lerp_angle_deg(current: float, target: float, alpha: float) -> float:
    delta = ((target - current + 180.0) % 360.0) - 180.0
    return current + (delta * alpha)


@dataclass
class SpectatorFollowState:
    x: float
    y: float
    z: float
    pitch: float
    yaw: float


@dataclass
class EpisodeSpec:
    sequence_number: int
    map_id: str
    level: float
    curve_direction: str
    lane_width: float
    straight_length: float
    track_radius: float


def update_follow_vehicle_spectator(
    carla: object,
    world: object,
    vehicle: object,
    follow_distance: float,
    follow_height: float,
    follow_pitch: float,
    smoothing: float,
    state: SpectatorFollowState | None,
) -> SpectatorFollowState:
    target_transform = build_follow_vehicle_spectator_transform(
        carla=carla,
        vehicle=vehicle,
        follow_distance=follow_distance,
        follow_height=follow_height,
        follow_pitch=follow_pitch,
    )
    alpha = max(0.01, min(1.0, smoothing))
    if state is None:
        state = SpectatorFollowState(
            x=target_transform.location.x,
            y=target_transform.location.y,
            z=target_transform.location.z,
            pitch=target_transform.rotation.pitch,
            yaw=target_transform.rotation.yaw,
        )
    else:
        state.x += (target_transform.location.x - state.x) * alpha
        state.y += (target_transform.location.y - state.y) * alpha
        state.z += (target_transform.location.z - state.z) * alpha
        state.pitch = _lerp_angle_deg(state.pitch, target_transform.rotation.pitch, alpha)
        state.yaw = _lerp_angle_deg(state.yaw, target_transform.rotation.yaw, alpha)

    world.get_spectator().set_transform(
        carla.Transform(
            carla.Location(x=state.x, y=state.y, z=state.z),
            carla.Rotation(pitch=state.pitch, yaw=state.yaw, roll=0.0),
        )
    )
    return state


class CameraView:
    """Hold the latest RGB frame for the pygame window."""

    def __init__(self, width: int, height: int) -> None:
        self.width = width
        self.height = height
        self.surface: pygame.Surface | None = None

    def on_image(self, image: Any) -> None:
        array = np.frombuffer(image.raw_data, dtype=np.uint8)
        array = array.reshape((image.height, image.width, 4))
        rgb_array = array[:, :, :3][:, :, ::-1]
        self.surface = pygame.surfarray.make_surface(rgb_array.swapaxes(0, 1))


@dataclass
class ManualDemoEpisode:
    spec: EpisodeSpec
    world: Any
    vehicle: Any
    blueprint_id: str
    camera: Any
    camera_view: CameraView
    minimap_camera: Any | None
    minimap_view: CameraView | None


def create_camera_sensor(
    world: object,
    carla: object,
    vehicle: object,
    width: int,
    height: int,
    camera_distance: float,
    camera_height: float,
    camera_pitch: float,
    gamma: float = 2.2,
) -> tuple[object, CameraView]:
    blueprint = world.get_blueprint_library().find("sensor.camera.rgb")
    blueprint.set_attribute("image_size_x", str(width))
    blueprint.set_attribute("image_size_y", str(height))
    blueprint.set_attribute("fov", "90")
    blueprint.set_attribute("gamma", f"{gamma:.2f}")
    transform = carla.Transform(
        carla.Location(x=-camera_distance, z=camera_height),
        carla.Rotation(pitch=camera_pitch),
    )
    camera = world.spawn_actor(blueprint, transform, attach_to=vehicle)
    view = CameraView(width, height)
    camera.listen(view.on_image)
    return camera, view


def create_fixed_camera_sensor(
    world: object,
    carla: object,
    width: int,
    height: int,
    transform: object,
    fov: float = 90.0,
    gamma: float = 2.2,
) -> tuple[object, CameraView]:
    blueprint = world.get_blueprint_library().find("sensor.camera.rgb")
    blueprint.set_attribute("image_size_x", str(width))
    blueprint.set_attribute("image_size_y", str(height))
    blueprint.set_attribute("fov", f"{fov:.1f}")
    blueprint.set_attribute("gamma", f"{gamma:.2f}")
    camera = world.spawn_actor(blueprint, transform)
    view = CameraView(width, height)
    camera.listen(view.on_image)
    return camera, view


def clamp_level(level: float) -> float:
    return max(0.0, min(1.0, level))


def flip_curve_direction(curve_direction: str) -> str:
    return "right" if curve_direction == "left" else "left"


def build_episode_spec(
    base_map_id: str,
    args: argparse.Namespace,
    sequence_index: int,
) -> EpisodeSpec:
    sequence_number = sequence_index + 1
    level = clamp_level(args.level + (args.next_level_step * sequence_index))
    curve_direction = args.curve_direction
    if not args.no_alternate_direction and sequence_index % 2 == 1:
        curve_direction = flip_curve_direction(curve_direction)

    lane_width = max(4.5, args.demo_lane_width - (0.35 * sequence_index))
    straight_length = max(180.0, args.demo_straight_length - (12.0 * sequence_index))
    track_radius = max(60.0, args.demo_track_radius - (4.0 * sequence_index))

    return EpisodeSpec(
        sequence_number=sequence_number,
        map_id=f"{base_map_id}_case_{sequence_number:03d}",
        level=level,
        curve_direction=curve_direction,
        lane_width=lane_width,
        straight_length=straight_length,
        track_radius=track_radius,
    )


def resolve_vehicle_blueprint(
    world: Any,
    blueprint_filter: str,
    preferred_blueprint_id: str | None,
) -> Any:
    vehicle_profile = create_builtin_vehicle_profile(
        profile_name="legacy_manual_demo_vehicle",
        blueprint_filter=blueprint_filter,
        preferred_blueprint_id=preferred_blueprint_id,
        role_name="hero",
    )
    return resolve_vehicle_blueprint_for_profile(world, vehicle_profile)


def destroy_episode(
    episode: ManualDemoEpisode | None,
    keep_vehicle: bool = False,
) -> None:
    if episode is None:
        return

    if episode.minimap_camera is not None:
        destroy_actor(episode.minimap_camera)
    if episode.camera is not None:
        destroy_actor(episode.camera)
    if episode.vehicle is not None and not keep_vehicle:
        destroy_actor(episode.vehicle)


def create_manual_demo_episode(
    *,
    args: argparse.Namespace,
    carla: object,
    client: object,
    generation_parameters: object,
    width: int,
    height: int,
    minimap_width: int,
    minimap_height: int,
    spec: EpisodeSpec,
    vehicle_profile: VehicleProfile,
    preferred_blueprint_id: str | None,
) -> ManualDemoEpisode:
    artifacts = generate_map_from_level(
        map_id=spec.map_id,
        level=spec.level,
        generated_dir=args.generated_dir,
        manifest_dir=args.manifest_dir,
        stadium_track=True,
        curve_direction=spec.curve_direction,
        lane_width_override=spec.lane_width,
        straight_length_override=spec.straight_length,
        track_radius_override=spec.track_radius,
    )

    xodr_content = artifacts.xodr_path.read_text(encoding="utf-8")
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
    selected_spawn_point = select_spawn_point(world, args.spawn_index)
    spawn_transform = build_centered_spawn_transform(
        world=world,
        reference_transform=selected_spawn_point,
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

    minimap_camera = None
    minimap_view = None
    if args.show_minimap:
        overview_transform = build_fixed_overview_transform(
            carla=carla,
            straight_length=spec.straight_length,
            track_radius=spec.track_radius,
            curve_direction=spec.curve_direction,
            overview_height=args.overview_height,
            overview_pitch=args.overview_pitch,
        )
        minimap_camera, minimap_view = create_fixed_camera_sensor(
            world=world,
            carla=carla,
            width=minimap_width,
            height=minimap_height,
            transform=overview_transform,
        )

    return ManualDemoEpisode(
        spec=spec,
        world=world,
        vehicle=vehicle,
        blueprint_id=blueprint.id,
        camera=camera,
        camera_view=camera_view,
        minimap_camera=minimap_camera,
        minimap_view=minimap_view,
    )


def apply_keyboard_control(
    keys: Any,
    control: Any,
) -> Any:
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


def main() -> None:
    args = parse_args()
    random.seed(args.random_seed)

    width, height = [int(value) for value in args.resolution.split("x")]
    minimap_width, minimap_height = [int(value) for value in args.minimap_resolution.split("x")]
    base_map_id = build_map_id(args.map_id)

    pygame.init()
    pygame.font.init()
    display = pygame.display.set_mode((width, height))
    pygame.display.set_caption("AutoDrive Manual Track Demo")
    font = pygame.font.SysFont("Consolas", 20)

    episode: ManualDemoEpisode | None = None
    preferred_blueprint_id = None
    control = None
    vehicle_profile = create_builtin_vehicle_profile(
        profile_name=args.vehicle_profile_name,
        blueprint_filter=args.blueprint_filter,
        preferred_blueprint_id=args.preferred_blueprint_id,
        role_name=args.role_name,
        notes=(
            "CARLA built-in vehicle profile used for manual validation of "
            "generated OpenDRIVE tracks."
        ),
    )
    driver_profile = create_manual_driver_profile(
        notes=(
            "Manual keyboard driving used for map validation and demonstration; "
            "vehicle control is not the core target of this project."
        )
    )
    input_binding = create_split_input_binding(
        vehicle_profile=vehicle_profile,
        driver_profile=driver_profile,
        notes=(
            "Current manual demo uses split inputs: the app chooses the CARLA "
            "vehicle profile and the driving mode separately."
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
        sequence_index = 0

        def load_sequence(target_sequence_index: int, current_blueprint_id: str | None) -> tuple[ManualDemoEpisode, object, SpectatorFollowState | None]:
            spec = build_episode_spec(
                base_map_id=base_map_id,
                args=args,
                sequence_index=target_sequence_index,
            )
            loaded_episode = create_manual_demo_episode(
                args=args,
                carla=carla,
                client=client,
                generation_parameters=generation_parameters,
                width=width,
                height=height,
                minimap_width=minimap_width,
                minimap_height=minimap_height,
                spec=spec,
                vehicle_profile=vehicle_profile,
                preferred_blueprint_id=current_blueprint_id,
            )
            loaded_control = carla.VehicleControl()
            loaded_spectator_state = None
            if args.spectator_mode == "fixed-overview":
                set_fixed_overview_spectator(
                    carla=carla,
                    world=loaded_episode.world,
                    straight_length=loaded_episode.spec.straight_length,
                    track_radius=loaded_episode.spec.track_radius,
                    curve_direction=loaded_episode.spec.curve_direction,
                    overview_height=args.overview_height,
                    overview_pitch=args.overview_pitch,
                )
            print("Manual track demo vehicle spawned successfully.")
            print(f"Map id: {loaded_episode.spec.map_id}")
            print(f"Loaded map: {loaded_episode.world.get_map().name}")
            print(
                "Track parameters: "
                f"level={loaded_episode.spec.level:.2f}, "
                f"direction={loaded_episode.spec.curve_direction}, "
                f"lane_width={loaded_episode.spec.lane_width:.2f}, "
                f"straight_length={loaded_episode.spec.straight_length:.1f}, "
                f"track_radius={loaded_episode.spec.track_radius:.1f}"
            )
            print(f"Vehicle blueprint: {loaded_episode.blueprint_id}")
            print(f"Vehicle profile: {vehicle_profile.describe()}")
            print(f"Driver profile: {driver_profile.describe()}")
            print(f"Input binding: {input_binding.describe()}")
            print("Controls: WASD / Arrow keys, Space hand brake, R reload current map, N next map, ESC exit")
            return loaded_episode, loaded_control, loaded_spectator_state

        episode, control, spectator_state = load_sequence(
            target_sequence_index=sequence_index,
            current_blueprint_id=preferred_blueprint_id,
        )
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
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                    return
                if event.type == pygame.KEYDOWN and event.key == pygame.K_r:
                    reload_current_map = True
                if event.type == pygame.KEYDOWN and event.key == pygame.K_n:
                    load_next_map = True

            if reload_current_map or load_next_map:
                if load_next_map:
                    sequence_index += 1
                destroy_episode(episode, keep_vehicle=False)
                episode, control, spectator_state = load_sequence(
                    target_sequence_index=sequence_index,
                    current_blueprint_id=preferred_blueprint_id,
                )
                preferred_blueprint_id = episode.blueprint_id
                pygame.event.clear()
                continue

            keys = pygame.key.get_pressed()
            control = apply_keyboard_control(keys, control)
            episode.vehicle.apply_control(control)

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
            else:
                display.fill((30, 30, 30))

            if episode.minimap_view is not None and episode.minimap_view.surface is not None:
                minimap_rect = pygame.Rect(
                    args.minimap_margin,
                    args.minimap_margin,
                    minimap_width,
                    minimap_height,
                )
                frame_rect = minimap_rect.inflate(8, 8)
                pygame.draw.rect(display, (18, 18, 18), frame_rect, border_radius=6)
                pygame.draw.rect(
                    display,
                    (220, 220, 220),
                    frame_rect,
                    width=2,
                    border_radius=6,
                )
                minimap_surface = pygame.transform.smoothscale(
                    episode.minimap_view.surface,
                    (minimap_width, minimap_height),
                )
                display.blit(minimap_surface, minimap_rect)

            velocity = episode.vehicle.get_velocity()
            speed_kmh = 3.6 * math.sqrt(
                (velocity.x ** 2) + (velocity.y ** 2) + (velocity.z ** 2)
            )
            lines = [
                f"Map: {episode.spec.map_id}",
                f"Sequence: {episode.spec.sequence_number}  Level: {episode.spec.level:.2f}",
                (
                    "Track: "
                    f"{episode.spec.curve_direction}, "
                    f"LW {episode.spec.lane_width:.1f}m, "
                    f"ST {episode.spec.straight_length:.0f}m, "
                    f"R {episode.spec.track_radius:.0f}m"
                ),
                f"Vehicle: {episode.blueprint_id}",
                f"Speed: {speed_kmh:5.1f} km/h",
                "Controls: W/A/S/D or arrows, Space, R reload, N next map, ESC",
            ]
            y = 16
            for line in lines:
                text_surface = font.render(line, True, (255, 255, 255))
                display.blit(text_surface, (16, y))
                y += 24

            pygame.display.flip()
            clock.tick_busy_loop(60)
    finally:
        destroy_episode(episode, keep_vehicle=args.keep_vehicle)
        pygame.quit()


if __name__ == "__main__":
    main()
