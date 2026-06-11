"""Generate a stadium track, load it in CARLA, and drive a vehicle with built-in autopilot."""

from __future__ import annotations

import argparse
import importlib
import json
from datetime import datetime
import math
import os
from pathlib import Path
import random
import sys
import time

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.carla_runner.carla_utils import create_client
from scripts.carla_runner.driver_profiles import (
    DriverMode,
    DriverProfile,
)
from scripts.carla_runner.dual_lidar_track_driver import (
    DualLidarTrackDriver,
    DualLidarTrackDriverConfig,
)
from scripts.carla_runner.load_xodr_in_carla import (
    create_generation_parameters,
    load_opendrive_world,
)
from scripts.carla_runner.simple_track_driver import (
    SimpleTrackDriver,
    SimpleTrackDriverConfig,
    build_centered_spawn_transform,
)
from scripts.carla_runner.vehicle_utils import (
    destroy_actor,
    enable_autopilot,
    select_spawn_point,
)
from scripts.carla_runner.vehicle_profiles import (
    create_builtin_vehicle_profile,
    resolve_vehicle_blueprint_for_profile,
)
from scripts.map_generator.level_generator import generate_map_from_level


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a stadium-style track, load it into CARLA, spawn a built-in vehicle, "
            "and drive it using CARLA's built-in autopilot."
        ),
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
        help="Optional path to the CARLA PythonAPI directory, dist directory, or .egg file.",
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
        "--driver-mode",
        choices=("autopilot", "basic-agent", "waypoint-loop", "dual-lidar"),
        default="dual-lidar",
        help="Driving backend used for the demo vehicle.",
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
        help="Lane width used for the stadium-track demo map.",
    )
    parser.add_argument(
        "--demo-straight-length",
        type=float,
        default=240.0,
        help="Straight segment length used for the stadium-track demo map.",
    )
    parser.add_argument(
        "--demo-track-radius",
        type=float,
        default=90.0,
        help="Turn radius used for the stadium-track demo map.",
    )
    parser.add_argument(
        "--blueprint-filter",
        default="vehicle.*",
        help="Blueprint filter for selecting a CARLA built-in vehicle.",
    )
    parser.add_argument(
        "--vehicle-profile-name",
        default="builtin_stadium_demo_vehicle",
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
        help="Optional fixed spawn point index. If omitted, a random point is used.",
    )
    parser.add_argument(
        "--traffic-manager-port",
        type=int,
        default=8000,
        help="Traffic Manager port for autopilot.",
    )
    parser.add_argument(
        "--agent-target-speed",
        type=float,
        default=30.0,
        help="Target speed in km/h when --driver-mode basic-agent is used.",
    )
    parser.add_argument(
        "--agent-destination-step",
        type=float,
        default=35.0,
        help="Waypoint lookahead distance in meters for the basic-agent loop.",
    )
    parser.add_argument(
        "--loop-target-speed",
        type=float,
        default=8.0,
        help="Target speed in km/h when --driver-mode waypoint-loop is used.",
    )
    parser.add_argument(
        "--loop-waypoint-step",
        type=float,
        default=2.5,
        help="Waypoint spacing in meters for the waypoint-loop route.",
    )
    parser.add_argument(
        "--loop-arrival-distance",
        type=float,
        default=5.0,
        help="Distance threshold for advancing to the next loop waypoint.",
    )
    parser.add_argument(
        "--loop-lookahead-points",
        type=int,
        default=6,
        help="Number of sampled waypoints to look ahead in waypoint-loop mode.",
    )
    parser.add_argument(
        "--lidar-target-speed",
        type=float,
        default=12.0,
        help="Target speed in km/h when --driver-mode dual-lidar is used.",
    )
    parser.add_argument(
        "--lidar-min-speed",
        type=float,
        default=7.0,
        help="Minimum speed in km/h used during tighter turns in dual-lidar mode.",
    )
    parser.add_argument(
        "--spawn-height-offset",
        type=float,
        default=0.6,
        help="Height offset applied when re-centering the spawn transform.",
    )
    parser.add_argument(
        "--duration-seconds",
        type=float,
        default=0.0,
        help="How long to keep the demo running. Use 0 or a negative value to keep driving until interrupted.",
    )
    parser.add_argument(
        "--keep-vehicle",
        action="store_true",
        help="Keep the spawned vehicle alive after the demo loop ends.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=7,
        help="Random seed used for blueprint and spawn selection.",
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
    parser.add_argument(
        "--camera-mode",
        choices=("topdown", "follow"),
        default="follow",
        help="Spectator camera mode for viewing the demo.",
    )
    parser.add_argument(
        "--spectator-height",
        type=float,
        default=320.0,
        help="Top-down spectator height in meters.",
    )
    parser.add_argument(
        "--follow-distance",
        type=float,
        default=14.0,
        help="Distance behind the vehicle when --camera-mode follow is used.",
    )
    parser.add_argument(
        "--follow-height",
        type=float,
        default=5.0,
        help="Height above the vehicle when --camera-mode follow is used.",
    )
    parser.add_argument(
        "--follow-pitch",
        type=float,
        default=-15.0,
        help="Spectator pitch angle when --camera-mode follow is used.",
    )
    parser.add_argument(
        "--camera-update-interval",
        type=float,
        default=0.05,
        help="Seconds between spectator updates in follow-camera mode.",
    )
    return parser.parse_args()


def build_map_id(explicit_map_id: str | None) -> str:
    """Build a stable map id for one demo run."""

    if explicit_map_id:
        return explicit_map_id
    return "stadium_demo_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def _load_manifest(manifest_path: Path) -> dict[str, object]:
    """Read the generation manifest for the current demo."""

    return json.loads(manifest_path.read_text(encoding="utf-8"))


def load_basic_agent_class(pythonapi_path: str | None = None) -> object:
    """Import CARLA's built-in BasicAgent helper."""

    candidate_dirs: list[Path] = []
    for raw_value in (
        pythonapi_path,
        os.environ.get("CARLA_PYTHONAPI"),
        os.environ.get("CARLA_ROOT"),
    ):
        if not raw_value:
            continue

        candidate = Path(raw_value)
        possible_dirs = [
            candidate / "PythonAPI" / "carla",
            candidate / "carla",
            candidate,
        ]
        for possible_dir in possible_dirs:
            if possible_dir.exists() and (possible_dir / "agents").exists():
                candidate_dirs.append(possible_dir)

    seen_paths = set(sys.path)
    for candidate_dir in candidate_dirs:
        candidate_str = str(candidate_dir)
        if candidate_str not in seen_paths:
            sys.path.append(candidate_str)
            seen_paths.add(candidate_str)

    basic_agent_module = importlib.import_module("agents.navigation.basic_agent")
    return basic_agent_module.BasicAgent


def load_vehicle_pid_controller_class(pythonapi_path: str | None = None) -> object:
    """Import CARLA's built-in VehiclePIDController helper."""

    candidate_dirs: list[Path] = []
    for raw_value in (
        pythonapi_path,
        os.environ.get("CARLA_PYTHONAPI"),
        os.environ.get("CARLA_ROOT"),
    ):
        if not raw_value:
            continue

        candidate = Path(raw_value)
        possible_dirs = [
            candidate / "PythonAPI" / "carla",
            candidate / "carla",
            candidate,
        ]
        for possible_dir in possible_dirs:
            if possible_dir.exists() and (possible_dir / "agents").exists():
                candidate_dirs.append(possible_dir)

    seen_paths = set(sys.path)
    for candidate_dir in candidate_dirs:
        candidate_str = str(candidate_dir)
        if candidate_str not in seen_paths:
            sys.path.append(candidate_str)
            seen_paths.add(candidate_str)

    controller_module = importlib.import_module("agents.navigation.controller")
    return controller_module.VehiclePIDController


def set_stadium_track_spectator(
    carla: object,
    world: object,
    straight_length: float,
    track_radius: float,
    curve_direction: str,
    spectator_height: float,
) -> None:
    """Place the spectator above the center of the stadium track."""

    center_y = track_radius if curve_direction == "left" else -track_radius
    center_x = straight_length / 2.0
    spectator = world.get_spectator()
    transform = carla.Transform(
        carla.Location(x=center_x, y=center_y, z=spectator_height),
        carla.Rotation(pitch=-90.0, yaw=0.0, roll=0.0),
    )
    spectator.set_transform(transform)


def set_follow_vehicle_spectator(
    carla: object,
    world: object,
    vehicle: object,
    follow_distance: float,
    follow_height: float,
    follow_pitch: float,
) -> bool:
    """Place the spectator behind the vehicle so movement is easy to see."""

    try:
        vehicle_transform = vehicle.get_transform()
        yaw_rad = math.radians(vehicle_transform.rotation.yaw)
        vehicle_location = vehicle_transform.location
        spectator_location = carla.Location(
            x=vehicle_location.x - (follow_distance * math.cos(yaw_rad)),
            y=vehicle_location.y - (follow_distance * math.sin(yaw_rad)),
            z=vehicle_location.z + follow_height,
        )
        spectator_rotation = carla.Rotation(
            pitch=follow_pitch,
            yaw=vehicle_transform.rotation.yaw,
            roll=0.0,
        )
        world.get_spectator().set_transform(
            carla.Transform(spectator_location, spectator_rotation)
        )
    except Exception:
        return False

    return True


def create_basic_agent(
    world: object,
    vehicle: object,
    pythonapi_path: str | None,
    target_speed: float,
) -> object:
    """Create CARLA's built-in BasicAgent for the spawned vehicle."""

    BasicAgent = load_basic_agent_class(pythonapi_path)
    return BasicAgent(
        vehicle,
        target_speed=target_speed,
        opt_dict={
            "ignore_traffic_lights": True,
            "ignore_stop_signs": True,
            "ignore_vehicles": True,
        },
        map_inst=world.get_map(),
    )


def build_loop_waypoints(
    world: object,
    start_location: object,
    step_distance: float,
    max_points: int = 2000,
) -> list[object]:
    """Sample a full route around the generated track and reuse it as a circular loop."""

    start_waypoint = world.get_map().get_waypoint(start_location)
    waypoints = [start_waypoint]
    current_waypoint = start_waypoint

    for _ in range(max_points):
        next_waypoints = current_waypoint.next(step_distance)
        if not next_waypoints:
            break

        next_waypoint = next_waypoints[0]
        if len(waypoints) > 10:
            start_distance = next_waypoint.transform.location.distance(
                start_waypoint.transform.location
            )
            if start_distance <= step_distance * 1.5:
                break

        waypoints.append(next_waypoint)
        current_waypoint = next_waypoint

    if len(waypoints) < 2:
        raise RuntimeError("Could not build a valid waypoint loop for the demo track.")

    return waypoints


def find_nearest_waypoint_index(route: list[object], vehicle_location: object) -> int:
    """Return the index of the nearest sampled route waypoint."""

    nearest_index = 0
    nearest_distance = float("inf")
    for index, waypoint in enumerate(route):
        distance = waypoint.transform.location.distance(vehicle_location)
        if distance < nearest_distance:
            nearest_index = index
            nearest_distance = distance
    return nearest_index


def create_loop_pid_controller(
    vehicle: object,
    pythonapi_path: str | None,
) -> object:
    """Create a conservative PID controller for slow stadium-track demos."""

    VehiclePIDController = load_vehicle_pid_controller_class(pythonapi_path)
    return VehiclePIDController(
        vehicle,
        args_lateral={
            "K_P": 1.25,
            "K_D": 0.2,
            "K_I": 0.02,
            "dt": 0.05,
        },
        args_longitudinal={
            "K_P": 1.0,
            "K_D": 0.0,
            "K_I": 0.05,
            "dt": 0.05,
        },
        max_throttle=0.45,
        max_brake=0.35,
        max_steering=0.55,
    )


def advance_basic_agent_destination(
    world: object,
    vehicle: object,
    current_waypoint: object | None,
    step_distance: float,
) -> object:
    """Move the basic-agent destination forward along the track."""

    active_waypoint = current_waypoint
    if active_waypoint is None:
        active_waypoint = world.get_map().get_waypoint(vehicle.get_location())

    next_waypoints = active_waypoint.next(step_distance)
    if not next_waypoints:
        active_waypoint = world.get_map().get_waypoint(vehicle.get_location())
        next_waypoints = active_waypoint.next(step_distance)
        if not next_waypoints:
            raise RuntimeError("Could not find a next waypoint for the stadium track demo.")

    return next_waypoints[0]


def main() -> None:
    args = parse_args()
    random.seed(args.random_seed)

    map_id = build_map_id(args.map_id)
    vehicle = None
    agent = None
    simple_track_driver = None
    dual_lidar_driver = None
    current_destination_waypoint = None
    vehicle_profile = create_builtin_vehicle_profile(
        profile_name=args.vehicle_profile_name,
        blueprint_filter=args.blueprint_filter,
        preferred_blueprint_id=args.preferred_blueprint_id,
        role_name=args.role_name,
        notes="CARLA built-in vehicle profile used for generated-track validation.",
    )
    driver_profile = DriverProfile(
        profile_name=f"{args.driver_mode}_driver_profile",
        mode=DriverMode(
            "carla_autopilot" if args.driver_mode == "autopilot" else args.driver_mode
        ),
        notes=(
            "Demo driving backend selected for generated-track validation. "
            "This module is replaceable and not the core target of the project."
        ),
        runtime_options={
            "traffic_manager_port": args.traffic_manager_port,
            "agent_target_speed": args.agent_target_speed,
            "loop_target_speed": args.loop_target_speed,
            "lidar_target_speed": args.lidar_target_speed,
        },
    )

    try:
        artifacts = generate_map_from_level(
            map_id=map_id,
            level=args.level,
            generated_dir=args.generated_dir,
            manifest_dir=args.manifest_dir,
            stadium_track=True,
            curve_direction=args.curve_direction,
            lane_width_override=args.demo_lane_width,
            straight_length_override=args.demo_straight_length,
            track_radius_override=args.demo_track_radius,
        )
        manifest = _load_manifest(artifacts.manifest_path)

        xodr_content = artifacts.xodr_path.read_text(encoding="utf-8")
        carla, client, _ = create_client(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            pythonapi_path=args.pythonapi_path,
        )
        parameters = create_generation_parameters(carla, args)
        world = load_opendrive_world(client, xodr_content, parameters, args.keep_settings)

        road_config = manifest["road_config"]
        blueprint = resolve_vehicle_blueprint_for_profile(
            world=world,
            vehicle_profile=vehicle_profile,
        )
        selected_spawn_point = select_spawn_point(world, args.spawn_index)
        spawn_transform = build_centered_spawn_transform(
            world=world,
            reference_transform=selected_spawn_point,
            z_offset=args.spawn_height_offset,
        )
        vehicle = world.spawn_actor(blueprint, spawn_transform)
        if args.driver_mode == "autopilot":
            enable_autopilot(vehicle, args.traffic_manager_port)
        elif args.driver_mode == "basic-agent":
            agent = create_basic_agent(
                world=world,
                vehicle=vehicle,
                pythonapi_path=args.pythonapi_path,
                target_speed=args.agent_target_speed,
            )
            current_destination_waypoint = advance_basic_agent_destination(
                world=world,
                vehicle=vehicle,
                current_waypoint=None,
                step_distance=args.agent_destination_step,
            )
            agent.set_destination(current_destination_waypoint.transform.location)
        elif args.driver_mode == "waypoint-loop":
            simple_track_driver = SimpleTrackDriver.create(
                world=world,
                vehicle=vehicle,
                pythonapi_path=args.pythonapi_path,
                start_location=spawn_transform.location,
                config=SimpleTrackDriverConfig(
                    route_step_distance=args.loop_waypoint_step,
                    lookahead_points=args.loop_lookahead_points,
                    target_speed_kmh=args.loop_target_speed,
                    spawn_height_offset=args.spawn_height_offset,
                ),
            )
        else:
            dual_lidar_driver = DualLidarTrackDriver.create(
                world=world,
                carla_module=carla,
                vehicle=vehicle,
                config=DualLidarTrackDriverConfig(
                    target_speed_kmh=args.lidar_target_speed,
                    min_speed_kmh=args.lidar_min_speed,
                ),
            )
            time.sleep(0.3)

        if args.camera_mode == "topdown":
            set_stadium_track_spectator(
                carla=carla,
                world=world,
                straight_length=float(road_config["road_length"]),
                track_radius=float(road_config["track_radius"]),
                curve_direction=args.curve_direction,
                spectator_height=args.spectator_height,
            )
        else:
            set_follow_vehicle_spectator(
                carla=carla,
                world=world,
                vehicle=vehicle,
                follow_distance=args.follow_distance,
                follow_height=args.follow_height,
                follow_pitch=args.follow_pitch,
            )

        print("Stadium track demo vehicle spawned successfully.")
        print(f"Map id: {map_id}")
        print(f"Generated xodr: {artifacts.xodr_path}")
        print(f"Manifest: {artifacts.manifest_path}")
        print(f"Loaded map: {world.get_map().name}")
        print(f"Blueprint: {blueprint.id}")
        print(f"Vehicle profile: {vehicle_profile.describe()}")
        print(f"Driver profile: {driver_profile.describe()}")
        print(f"Actor id: {vehicle.id}")
        if args.duration_seconds > 0:
            print(f"Duration: {args.duration_seconds:.1f} seconds")
        else:
            print("Duration: continuous until interrupted")
        print(
            "Track config: "
            f"straight_length={road_config['road_length']:.1f}m, "
            f"track_radius={road_config['track_radius']:.1f}m, "
            f"lane_width={road_config['lane_width']:.1f}m"
        )
        if args.driver_mode == "autopilot":
            print("Vehicle control mode: CARLA built-in autopilot")
        elif args.driver_mode == "basic-agent":
            print("Vehicle control mode: CARLA BasicAgent")
        elif args.driver_mode == "waypoint-loop":
            print("Vehicle control mode: CARLA PID waypoint loop controller")
        else:
            print("Vehicle control mode: reactive dual-LiDAR wall-following controller")
        print(f"Camera mode: {args.camera_mode}")
        print(f"Keep vehicle after demo: {args.keep_vehicle}")

        end_time = None
        if args.duration_seconds > 0:
            end_time = time.time() + args.duration_seconds

        while end_time is None or time.time() < end_time:
            try:
                if args.driver_mode == "basic-agent":
                    if agent.done():
                        current_destination_waypoint = advance_basic_agent_destination(
                            world=world,
                            vehicle=vehicle,
                            current_waypoint=current_destination_waypoint,
                            step_distance=args.agent_destination_step,
                        )
                        agent.set_destination(current_destination_waypoint.transform.location)
                    vehicle.apply_control(agent.run_step())
                elif args.driver_mode == "waypoint-loop":
                    if simple_track_driver is None:
                        raise RuntimeError("Simple track driver was not initialized.")

                    control = simple_track_driver.run_step()
                    vehicle.apply_control(control)
                elif args.driver_mode == "dual-lidar":
                    if dual_lidar_driver is None:
                        raise RuntimeError("Dual LiDAR track driver was not initialized.")

                    control = dual_lidar_driver.run_step()
                    vehicle.apply_control(control)
                if args.camera_mode == "follow":
                    camera_ok = set_follow_vehicle_spectator(
                        carla=carla,
                        world=world,
                        vehicle=vehicle,
                        follow_distance=args.follow_distance,
                        follow_height=args.follow_height,
                        follow_pitch=args.follow_pitch,
                    )
                    if not camera_ok:
                        print("Follow camera lost track of the vehicle actor. Ending the demo loop.")
                        break
                time.sleep(args.camera_update_interval)
            except KeyboardInterrupt:
                print("Demo interrupted by user. Stopping the drive loop.")
                break
    except Exception as error:
        print("Failed to run the stadium track autopilot demo.")
        print(f"Reason: {error}")
        raise SystemExit(1) from error
    finally:
        if dual_lidar_driver is not None:
            dual_lidar_driver.destroy()
        if vehicle is not None:
            vehicle_id = vehicle.id
            if args.keep_vehicle:
                print(f"Leaving vehicle actor {vehicle_id} alive for continued observation.")
            else:
                destroy_actor(vehicle)
                print(f"Destroyed vehicle actor {vehicle_id}.")


if __name__ == "__main__":
    main()
