"""Load one built-in CARLA Town and apply a Practical Stage weather preset."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.app.practical_stage import resolve_practical_weather
from scripts.carla_runner.carla_utils import create_client


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Load a built-in CARLA Town for the Practical Stage shell.",
    )
    parser.add_argument("--town-id", default="Town03", help="CARLA Town map id to load.")
    parser.add_argument(
        "--weather-preset",
        default="clear_noon",
        help="Practical Stage weather preset id.",
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
        help="Optional CARLA root or PythonAPI path.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    weather_preset = resolve_practical_weather(args.weather_preset)

    try:
        carla, client, _ = create_client(
            host=args.host,
            port=args.port,
            timeout=args.timeout,
            pythonapi_path=args.pythonapi_path,
        )
        world = client.load_world(args.town_id)
        weather_parameters = getattr(carla.WeatherParameters, weather_preset.carla_attribute)
        world.set_weather(weather_parameters)
    except Exception as error:
        print("Failed to load the Practical Stage Town.")
        print(f"Reason: {error}")
        raise SystemExit(1) from error

    current_map = world.get_map()
    spawn_points = current_map.get_spawn_points()
    print("Practical Stage Town loaded successfully.")
    print(f"Town: {args.town_id}")
    print(f"Weather preset: {weather_preset.display_name}")
    print(f"Current map: {current_map.name}")
    print(f"Spawn point count: {len(spawn_points)}")


if __name__ == "__main__":
    main()
