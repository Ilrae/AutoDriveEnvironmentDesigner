"""Run the first end-to-end CARLA validation for a generated OpenDRIVE map."""

from __future__ import annotations

import argparse
from datetime import datetime
from pathlib import Path
import random
import sys
import time

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.carla_runner.carla_utils import create_client
from scripts.carla_runner.load_xodr_in_carla import (
    create_generation_parameters,
    load_opendrive_world,
)
from scripts.carla_runner.vehicle_utils import (
    attach_collision_sensor,
    destroy_actor,
    enable_autopilot,
    select_spawn_point,
    select_vehicle_blueprint,
)
from scripts.evaluation.result_models import EpisodeResult, save_episode_result
from scripts.map_generator.level_generator import generate_map_from_level


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a draft map, load it into CARLA, drive once, and save a validation result.",
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
        help="Difficulty level used for draft road generation.",
    )
    parser.add_argument(
        "--include-curve",
        action="store_true",
        help="Append one arc segment after the generated straight segment.",
    )
    parser.add_argument(
        "--stadium-track",
        action="store_true",
        help="Generate a larger stadium-style oval track instead of a straight or single-curve road.",
    )
    parser.add_argument(
        "--curve-direction",
        choices=("left", "right"),
        default="left",
        help="Direction of the generated turns when a curved road shape is used.",
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
        "--results-dir",
        type=Path,
        default=Path("results"),
        help="Directory where validation results are stored.",
    )
    parser.add_argument(
        "--road-id",
        type=int,
        default=1,
        help="Road identifier embedded in the generated .xodr file.",
    )
    parser.add_argument(
        "--blueprint-filter",
        default="vehicle.*",
        help="Blueprint filter for selecting a vehicle.",
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
        "--duration-seconds",
        type=float,
        default=10.0,
        help="How long to keep autopilot enabled during validation.",
    )
    parser.add_argument(
        "--collision-cooldown-seconds",
        type=float,
        default=0.5,
        help="Minimum interval between counted collision events.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=7,
        help="Random seed used for blueprint/spawn selection.",
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
    """Build a stable map id for one validation run."""

    if explicit_map_id:
        return explicit_map_id
    return "validation_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def save_result_payload(
    result_path: Path,
    map_id: str,
    success: bool,
    drive_duration: float,
    collision_count: int,
    metadata: dict[str, object],
) -> Path:
    """Persist the validation result JSON."""

    result = EpisodeResult(
        map_id=map_id,
        success=success,
        time_sec=drive_duration,
        collision_count=collision_count,
        offroad_ratio=0.0,
        metadata=metadata,
    )
    return save_episode_result(result, result_path)


def main() -> None:
    args = parse_args()
    random.seed(args.random_seed)

    map_id = build_map_id(args.map_id)
    result_path = args.results_dir / f"{map_id}_validation.json"

    vehicle = None
    collision_sensor = None
    collision_state = {"count": 0}
    drive_started_at = None

    metadata: dict[str, object] = {
        "validation_stage": "first_end_to_end_validation",
        "level": args.level,
        "include_curve": args.include_curve,
        "stadium_track": args.stadium_track,
        "curve_direction": args.curve_direction,
        "host": args.host,
        "port": args.port,
        "pythonapi_path": args.pythonapi_path,
    }

    try:
        artifacts = generate_map_from_level(
            map_id=map_id,
            level=args.level,
            generated_dir=args.generated_dir,
            manifest_dir=args.manifest_dir,
            road_id=args.road_id,
            include_curve=args.include_curve,
            stadium_track=args.stadium_track,
            curve_direction=args.curve_direction,
        )
        metadata["xodr_path"] = str(artifacts.xodr_path.resolve())
        metadata["manifest_path"] = str(artifacts.manifest_path.resolve())

        xodr_content = artifacts.xodr_path.read_text(encoding="utf-8")
        carla, client, _ = create_client(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            pythonapi_path=args.pythonapi_path,
        )
        parameters = create_generation_parameters(carla, args)
        world = load_opendrive_world(client, xodr_content, parameters, args.keep_settings)
        metadata["client_version"] = client.get_client_version()
        metadata["server_version"] = client.get_server_version()
        metadata["loaded_map"] = world.get_map().name
        metadata["spawn_point_count"] = len(world.get_map().get_spawn_points())

        blueprint = select_vehicle_blueprint(world, args.blueprint_filter)
        spawn_point = select_spawn_point(world, args.spawn_index)
        vehicle = world.spawn_actor(blueprint, spawn_point)
        collision_sensor, collision_state = attach_collision_sensor(
            world,
            vehicle,
            cooldown_seconds=args.collision_cooldown_seconds,
        )
        enable_autopilot(vehicle, args.traffic_manager_port)
        drive_started_at = time.time()

        print("Validation vehicle spawned and autopilot enabled.")
        print(f"Map id: {map_id}")
        print(f"Generated xodr: {artifacts.xodr_path}")
        print(f"Manifest: {artifacts.manifest_path}")
        print(f"Loaded map: {world.get_map().name}")
        print(f"Blueprint: {blueprint.id}")
        print(f"Actor id: {vehicle.id}")
        print(f"Duration: {args.duration_seconds:.1f} seconds")

        if args.duration_seconds > 0:
            time.sleep(args.duration_seconds)

        drive_duration = 0.0
        if drive_started_at is not None:
            drive_duration = time.time() - drive_started_at

        metadata["blueprint_id"] = blueprint.id
        metadata["vehicle_actor_id"] = vehicle.id
        metadata["collision_cooldown_seconds"] = args.collision_cooldown_seconds
        metadata["result_note"] = "offroad_ratio is a placeholder until lane/offroad tracking is added"

        result_file = save_result_payload(
            result_path=result_path,
            map_id=map_id,
            success=collision_state["count"] == 0,
            drive_duration=drive_duration,
            collision_count=collision_state["count"],
            metadata=metadata,
        )
        print(f"Saved validation result: {result_file}")
    except Exception as error:
        drive_duration = 0.0
        if drive_started_at is not None:
            drive_duration = time.time() - drive_started_at

        metadata["error"] = str(error)
        save_result_payload(
            result_path=result_path,
            map_id=map_id,
            success=False,
            drive_duration=drive_duration,
            collision_count=collision_state["count"],
            metadata=metadata,
        )
        print("Failed to run the first validation flow.")
        print(f"Reason: {error}")
        print(f"Saved failure result: {result_path}")
        raise SystemExit(1) from error
    finally:
        destroy_actor(collision_sensor)
        if vehicle is not None:
            vehicle_id = vehicle.id
            destroy_actor(vehicle)
            print(f"Destroyed vehicle actor {vehicle_id}.")


if __name__ == "__main__":
    main()
