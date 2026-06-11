"""Load an OpenDRIVE file into CARLA using standalone OpenDRIVE mode."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.carla_runner.carla_utils import create_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load a local .xodr file into a running CARLA server.",
    )
    parser.add_argument(
        "--xodr-path",
        type=Path,
        default=Path("maps/generated/straight_road_test_001.xodr"),
        help="Path to the OpenDRIVE (.xodr) file to load.",
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


def create_generation_parameters(carla: Any, args: argparse.Namespace) -> Any:
    """Create CARLA OpenDRIVE generation parameters with compatibility fallback."""

    try:
        return carla.OpendriveGenerationParameters(
            vertex_distance=args.vertex_distance,
            max_road_length=args.max_road_length,
            wall_height=args.wall_height,
            additional_width=args.additional_width,
            smooth_junctions=not args.no_smooth_junctions,
            enable_mesh_visibility=not args.no_mesh_visibility,
        )
    except TypeError:
        return carla.OpendriveGenerationParameters(
            args.vertex_distance,
            args.max_road_length,
            args.wall_height,
            args.additional_width,
            not args.no_smooth_junctions,
            not args.no_mesh_visibility,
        )


def load_opendrive_world(client: Any, xodr_content: str, parameters: Any, keep_settings: bool) -> Any:
    """Load a world from OpenDRIVE content with compatibility fallback."""

    try:
        return client.generate_opendrive_world(
            xodr_content,
            parameters=parameters,
            reset_settings=not keep_settings,
        )
    except TypeError:
        return client.generate_opendrive_world(xodr_content, parameters)


def main() -> None:
    args = parse_args()
    xodr_path = args.xodr_path.resolve()

    if not xodr_path.exists():
        print("The requested .xodr file does not exist.")
        print(f"Path: {xodr_path}")
        raise SystemExit(1)

    xodr_content = xodr_path.read_text(encoding="utf-8")
    if not xodr_content.strip():
        print("The requested .xodr file is empty.")
        print(f"Path: {xodr_path}")
        raise SystemExit(1)

    try:
        carla, client, _ = create_client(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            pythonapi_path=args.pythonapi_path,
        )
        parameters = create_generation_parameters(carla, args)
        world = load_opendrive_world(client, xodr_content, parameters, args.keep_settings)
    except Exception as error:
        print("Failed to load the OpenDRIVE file into CARLA.")
        print(f"Reason: {error}")
        raise SystemExit(1) from error

    current_map = world.get_map()
    spawn_points = current_map.get_spawn_points()

    print("OpenDRIVE world loaded successfully.")
    print(f"Source file: {xodr_path}")
    print(f"Host: {args.host}:{args.port}")
    print(f"Client version: {client.get_client_version()}")
    print(f"Server version: {client.get_server_version()}")
    print(f"Current map: {current_map.name}")
    print(f"Spawn point count: {len(spawn_points)}")
    print(
        "Generation parameters: "
        f"vertex_distance={args.vertex_distance}, "
        f"max_road_length={args.max_road_length}, "
        f"wall_height={args.wall_height}, "
        f"additional_width={args.additional_width}, "
        f"smooth_junctions={not args.no_smooth_junctions}, "
        f"mesh_visibility={not args.no_mesh_visibility}, "
        f"reset_settings={not args.keep_settings}"
    )


if __name__ == "__main__":
    main()

