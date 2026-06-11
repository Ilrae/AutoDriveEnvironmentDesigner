"""Load a generated custom track, then launch CARLA's built-in manual_control.py."""

from __future__ import annotations

import argparse
from datetime import datetime
import math
from pathlib import Path
import subprocess
import sys
import time

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.carla_runner.carla_utils import create_client
from scripts.carla_runner.load_xodr_in_carla import (
    create_generation_parameters,
    load_opendrive_world,
)
from scripts.map_generator.level_generator import generate_map_from_level


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate a stadium-style track, load it in CARLA, and launch CARLA's "
            "built-in manual_control.py for keyboard driving."
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
        "--manual-filter",
        default="vehicle.*",
        help="Blueprint filter passed to CARLA manual_control.py.",
    )
    parser.add_argument(
        "--manual-generation",
        default="2",
        help="Vehicle generation filter passed to CARLA manual_control.py.",
    )
    parser.add_argument(
        "--manual-resolution",
        default="1280x720",
        help="Window resolution for CARLA manual_control.py.",
    )
    parser.add_argument(
        "--manual-role-name",
        default="hero",
        help="Role name passed to CARLA manual_control.py.",
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
        "--skip-launch",
        action="store_true",
        help="Only generate/load the map and print the manual_control command.",
    )
    return parser.parse_args()


def build_map_id(explicit_map_id: str | None) -> str:
    if explicit_map_id:
        return explicit_map_id
    return "manual_drive_demo_" + datetime.now().strftime("%Y%m%d_%H%M%S")


def resolve_manual_control_path(pythonapi_path: str | None) -> Path:
    candidate_roots: list[Path] = []
    for raw_value in (pythonapi_path,):
        if not raw_value:
            continue
        candidate = Path(raw_value)
        candidate_roots.extend(
            [
                candidate,
                candidate / "PythonAPI",
                candidate.parent / "PythonAPI",
            ]
        )

    for root in candidate_roots:
        manual_control = root / "examples" / "manual_control.py"
        if manual_control.exists():
            return manual_control

    raise FileNotFoundError(
        "Could not find CARLA manual_control.py. Pass --pythonapi-path to the CARLA root "
        "or PythonAPI directory."
    )


def find_role_vehicle(world: object, role_name: str) -> object | None:
    """Find the current vehicle actor that matches the requested role name."""

    for actor in world.get_actors().filter("vehicle.*"):
        attributes = getattr(actor, "attributes", {})
        if attributes.get("role_name") == role_name:
            return actor
    return None


def follow_actor_with_spectator(
    carla: object,
    world: object,
    actor: object,
    follow_distance: float = 8.0,
    follow_height: float = 3.5,
    follow_pitch: float = -12.0,
) -> None:
    """Move the spectator behind the active actor so the server window shows it."""

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
    map_id = build_map_id(args.map_id)

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

    xodr_content = artifacts.xodr_path.read_text(encoding="utf-8")
    carla, client, _ = create_client(
        host=args.host,
        port=args.port,
        timeout=args.timeout,
        pythonapi_path=args.pythonapi_path,
    )
    generation_parameters = create_generation_parameters(carla, args)
    world = load_opendrive_world(
        client,
        xodr_content,
        generation_parameters,
        args.keep_settings,
    )

    manual_control_path = resolve_manual_control_path(args.pythonapi_path)
    command = [
        sys.executable,
        str(manual_control_path),
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--filter",
        args.manual_filter,
        "--generation",
        args.manual_generation,
        "--res",
        args.manual_resolution,
        "--rolename",
        args.manual_role_name,
    ]

    print("Custom manual-drive demo map loaded successfully.")
    print(f"Map id: {map_id}")
    print(f"OpenDRIVE file: {artifacts.xodr_path}")
    print(f"Manifest file: {artifacts.manifest_path}")
    print(f"Loaded map: {world.get_map().name}")
    print("Next step: use CARLA's built-in manual_control.py to drive the spawned vehicle.")
    print("Command:")
    print(" ".join(command))

    if args.skip_launch:
        return

    process = subprocess.Popen(
        command,
        cwd=str(manual_control_path.parent),
    )
    try:
        print(
            "manual_control.py launched. Use the pygame window for keyboard driving, "
            "and the CARLA server window will try to follow the hero vehicle."
        )
        while process.poll() is None:
            hero_vehicle = find_role_vehicle(world, args.manual_role_name)
            if hero_vehicle is not None:
                follow_actor_with_spectator(carla, world, hero_vehicle)
            time.sleep(0.05)
    except KeyboardInterrupt:
        print("Interrupted by user. Closing manual_control.py...")
        process.terminate()
        process.wait(timeout=5)
    finally:
        if process.poll() is None:
            process.wait()

    if process.returncode != 0:
        raise SystemExit(process.returncode)


if __name__ == "__main__":
    main()
