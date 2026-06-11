"""Follow the current hero vehicle with the CARLA spectator camera."""

from __future__ import annotations

import argparse
import math
from pathlib import Path
import sys
import time

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.carla_runner.carla_utils import create_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Attach the CARLA spectator camera to the current hero vehicle."
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
        help="Path to the CARLA root, PythonAPI directory, dist directory, or .egg file.",
    )
    parser.add_argument(
        "--role-name",
        default="hero",
        help="Vehicle role name to follow.",
    )
    parser.add_argument(
        "--follow-distance",
        type=float,
        default=8.0,
        help="Distance behind the vehicle in meters.",
    )
    parser.add_argument(
        "--follow-height",
        type=float,
        default=3.5,
        help="Height above the vehicle in meters.",
    )
    parser.add_argument(
        "--follow-pitch",
        type=float,
        default=-12.0,
        help="Pitch angle of the spectator camera.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=float,
        default=0.05,
        help="Update interval for the spectator camera.",
    )
    return parser.parse_args()


def find_role_vehicle(world: object, role_name: str) -> object | None:
    for actor in world.get_actors().filter("vehicle.*"):
        attributes = getattr(actor, "attributes", {})
        if attributes.get("role_name") == role_name:
            return actor
    return None


def set_spectator_follow(
    carla: object,
    world: object,
    actor: object,
    follow_distance: float,
    follow_height: float,
    follow_pitch: float,
) -> None:
    transform = actor.get_transform()
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
    world.get_spectator().set_transform(
        carla.Transform(spectator_location, spectator_rotation)
    )


def main() -> None:
    args = parse_args()
    carla, client, _ = create_client(
        host=args.host,
        port=args.port,
        timeout=args.timeout,
        pythonapi_path=args.pythonapi_path,
    )
    world = client.get_world()

    print(f"Following vehicle role: {args.role_name}")
    print("Press Ctrl+C to stop spectator following.")

    try:
        while True:
            actor = find_role_vehicle(world, args.role_name)
            if actor is not None:
                set_spectator_follow(
                    carla=carla,
                    world=world,
                    actor=actor,
                    follow_distance=args.follow_distance,
                    follow_height=args.follow_height,
                    follow_pitch=args.follow_pitch,
                )
            time.sleep(args.interval_seconds)
    except KeyboardInterrupt:
        print("Stopped spectator follow.")


if __name__ == "__main__":
    main()
