"""Minimal CARLA connection test script."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.carla_runner.carla_utils import create_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Connect to a running CARLA simulator and print basic info.",
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
    return parser.parse_args()


def main() -> None:
    args = parse_args()

    try:
        _, client, world = create_client(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            pythonapi_path=args.pythonapi_path,
        )
    except Exception as error:
        print("Failed to connect to CARLA.")
        print(f"Reason: {error}")
        raise SystemExit(1) from error

    current_map = world.get_map()
    spawn_points = current_map.get_spawn_points()

    print("Connected to CARLA.")
    print(f"Host: {args.host}:{args.port}")
    print(f"Client version: {client.get_client_version()}")
    print(f"Server version: {client.get_server_version()}")
    print(f"Current map: {current_map.name}")
    print(f"Spawn point count: {len(spawn_points)}")


if __name__ == "__main__":
    main()
