"""Spawn a vehicle in CARLA and keep autopilot on for a short test run."""

from __future__ import annotations

import argparse
from pathlib import Path
import random
import sys
import time

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.carla_runner.carla_utils import create_client
from scripts.carla_runner.vehicle_utils import (
    destroy_actor,
    enable_autopilot,
    select_spawn_point,
    select_vehicle_blueprint,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Spawn one vehicle in CARLA and enable autopilot.",
    )
    parser.add_argument("--host", default="localhost", help="CARLA server host.")
    parser.add_argument("--port", type=int, default=2000, help="CARLA server port.")
    parser.add_argument(
        "--timeout",
        type=float,
        default=10.0,
        help="Connection timeout in seconds.",
    )
    parser.add_argument(
        "--pythonapi-path",
        default=None,
        help="Optional path to the CARLA PythonAPI directory, dist directory, or .egg file.",
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
        "--duration-seconds",
        type=float,
        default=15.0,
        help="How long to keep autopilot enabled before cleaning up.",
    )
    parser.add_argument(
        "--traffic-manager-port",
        type=int,
        default=8000,
        help="Traffic Manager port for autopilot.",
    )
    parser.add_argument(
        "--random-seed",
        type=int,
        default=7,
        help="Random seed used when choosing a spawn point or blueprint.",
    )
    return parser.parse_args()

def main() -> None:
    args = parse_args()
    random.seed(args.random_seed)
    vehicle = None

    try:
        _, client, world = create_client(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            pythonapi_path=args.pythonapi_path,
        )

        blueprint = select_vehicle_blueprint(world, args.blueprint_filter)
        spawn_point = select_spawn_point(world, args.spawn_index)
        vehicle = world.spawn_actor(blueprint, spawn_point)
        enable_autopilot(vehicle, args.traffic_manager_port)

        print("Vehicle spawned and autopilot enabled.")
        print(f"Blueprint: {blueprint.id}")
        print(f"Client version: {client.get_client_version()}")
        print(f"Server version: {client.get_server_version()}")
        print(f"Map: {world.get_map().name}")
        print(f"Actor id: {vehicle.id}")
        print(f"Duration: {args.duration_seconds:.1f} seconds")

        if args.duration_seconds > 0:
            time.sleep(args.duration_seconds)
    except Exception as error:
        print("Failed to run the CARLA spawn/autopilot test.")
        print(f"Reason: {error}")
        raise SystemExit(1) from error
    finally:
        if vehicle is not None:
            vehicle_id = vehicle.id
            destroy_actor(vehicle)
            print(f"Destroyed vehicle actor {vehicle_id}.")


if __name__ == "__main__":
    main()
