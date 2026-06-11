"""Application launcher that centralizes current AED demo workflows."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
from types import SimpleNamespace

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.app.auto_generation import generate_next_map_from_result
from scripts.app.factory import (
    build_current_manual_demo_session,
    format_session_summary,
)
from scripts.app.practical_stage import (
    practical_junction_focus_choices,
    practical_route_choices,
    practical_town_choices,
    practical_traffic_choices,
    practical_weather_choices,
)
from scripts.app.training_stages import training_stage_choices
from scripts.app.runtime_support import (
    configure_runtime_workspace,
    run_module_main,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the current AutoDriveEnvironmentDesigner application entrypoints.",
    )

    def add_common_arguments(target_parser: argparse.ArgumentParser) -> None:
        target_parser.add_argument(
            "--host",
            default="localhost",
            help="CARLA server host.",
        )
        target_parser.add_argument(
            "--port",
            type=int,
            default=2000,
            help="CARLA server port.",
        )
        target_parser.add_argument(
            "--timeout",
            type=float,
            default=30.0,
            help="Connection timeout in seconds.",
        )
        target_parser.add_argument(
            "--pythonapi-path",
            default=None,
            help="CARLA root or PythonAPI path used by the launched workflow.",
        )
        target_parser.add_argument(
            "--session-name",
            default="aed_manual_sequence_session",
            help="Application session name used for summaries.",
        )
        target_parser.add_argument(
            "--training-stage",
            choices=training_stage_choices(),
            default="track",
            help="Current AED progression stage selected in the control panel.",
        )
        target_parser.add_argument(
            "--practical-town",
            choices=practical_town_choices(),
            default="Town03",
            help="Built-in CARLA Town used by the Practical Stage shell.",
        )
        target_parser.add_argument(
            "--practical-weather",
            choices=practical_weather_choices(),
            default="clear_noon",
            help="Weather preset used by the Practical Stage shell.",
        )
        target_parser.add_argument(
            "--practical-traffic",
            choices=practical_traffic_choices(),
            default="moderate",
            help="Traffic-density preset used by the Practical Stage shell.",
        )
        target_parser.add_argument(
            "--practical-route",
            choices=practical_route_choices(),
            default="urban_loop",
            help="Route-complexity preset used by the Practical Stage shell.",
        )
        target_parser.add_argument(
            "--practical-custom-enabled",
            action="store_true",
            help="Enable custom Practical Stage scenario overrides instead of preset-only adaptation.",
        )
        target_parser.add_argument(
            "--practical-custom-vehicle-count",
            type=int,
            default=None,
            help="Optional custom Practical Stage NPC vehicle count.",
        )
        target_parser.add_argument(
            "--practical-custom-pedestrian-count",
            type=int,
            default=None,
            help="Optional custom Practical Stage pedestrian count.",
        )
        target_parser.add_argument(
            "--practical-custom-route-length",
            type=int,
            default=None,
            help="Optional custom Practical Stage route-length hint in meters.",
        )
        target_parser.add_argument(
            "--practical-custom-junction-focus",
            choices=practical_junction_focus_choices(),
            default=None,
            help="Optional custom Practical Stage junction-focus override.",
        )
        target_parser.add_argument(
            "--practical-custom-note",
            default=None,
            help="Optional free-form note stored with the Practical Stage shell settings.",
        )
        target_parser.add_argument(
            "--integration-custom-enabled",
            action="store_true",
            help="Enable one custom ego vehicle / driver integration override.",
        )
        target_parser.add_argument(
            "--preferred-blueprint-id",
            default=None,
            help="Optional CARLA blueprint id used for the app-owned ego vehicle.",
        )
        target_parser.add_argument(
            "--role-name",
            default=None,
            help="CARLA role_name assigned to the app-owned ego vehicle.",
        )
        target_parser.add_argument(
            "--driver-backend",
            choices=("manual", "external_module", "external_command"),
            default="manual",
            help="Driving backend used after the app spawns the ego vehicle.",
        )
        target_parser.add_argument(
            "--vehicle-config-path",
            default=None,
            help="Optional JSON file describing ego vehicle overrides such as blueprint id and color.",
        )
        target_parser.add_argument(
            "--driver-module-path",
            default=None,
            help="Optional Python file that overrides the built-in manual keyboard-control mapping.",
        )
        target_parser.add_argument(
            "--external-driver-command",
            default=None,
            help="Optional shell command launched after ego spawn for ROS or autonomy integration.",
        )
        target_parser.add_argument(
            "--external-driver-working-dir",
            default=None,
            help="Optional working directory used when launching the external driving command.",
        )
        target_parser.add_argument(
            "--external-driver-startup-wait",
            type=float,
            default=2.0,
            help="Seconds to wait after launching the external driving command before evaluation begins.",
        )

    add_common_arguments(parser)
    subparsers = parser.add_subparsers(dest="command", required=False)

    show_parser = subparsers.add_parser(
        "show-session",
        help="Show the current AED application structure summary.",
    )
    add_common_arguments(show_parser)
    show_parser.add_argument(
        "--verbose",
        action="store_true",
        help="Reserved for future detailed output.",
    )

    gui_parser = subparsers.add_parser(
        "gui",
        help="Launch the basic AED desktop control panel.",
    )
    add_common_arguments(gui_parser)

    manual_sequence = subparsers.add_parser(
        "manual-sequence",
        help="Run the prepared two-map manual sequence demo.",
    )
    add_common_arguments(manual_sequence)
    manual_sequence.add_argument("--map-id", default="aed_sequence_demo")
    manual_sequence.add_argument(
        "--spectator-mode",
        choices=("fixed-overview", "follow"),
        default="fixed-overview",
    )
    manual_sequence.add_argument(
        "--keep-vehicle",
        action="store_true",
        help="Keep the current vehicle alive after exit.",
    )

    manual_track = subparsers.add_parser(
        "manual-track",
        help="Run the stadium manual driving demo.",
    )
    add_common_arguments(manual_track)
    manual_track.add_argument("--map-id", default="aed_manual_track_demo")
    manual_track.add_argument(
        "--spectator-mode",
        choices=("fixed-overview", "follow"),
        default="follow",
    )
    manual_track.add_argument(
        "--keep-vehicle",
        action="store_true",
        help="Keep the current vehicle alive after exit.",
    )

    manual_xodr = subparsers.add_parser(
        "manual-xodr",
        help="Load an existing .xodr file, spawn a vehicle, and drive it manually.",
    )
    add_common_arguments(manual_xodr)
    manual_xodr.add_argument(
        "--xodr-path",
        required=True,
        help="Path to the OpenDRIVE file to drive on.",
    )
    manual_xodr.add_argument(
        "--spectator-mode",
        choices=("fixed-overview", "follow"),
        default="fixed-overview",
    )
    manual_xodr.add_argument(
        "--keep-vehicle",
        action="store_true",
        help="Keep the current vehicle alive after exit.",
    )

    load_xodr = subparsers.add_parser(
        "load-xodr",
        help="Load a local .xodr file into CARLA without starting a drive demo.",
    )
    add_common_arguments(load_xodr)
    load_xodr.add_argument(
        "--xodr-path",
        required=True,
        help="Path to the OpenDRIVE file to load.",
    )

    load_town = subparsers.add_parser(
        "load-town",
        help="Load a built-in CARLA Town with the current Practical Stage weather preset.",
    )
    add_common_arguments(load_town)

    generate_practical_scenario = subparsers.add_parser(
        "generate-practical-scenario",
        help="Generate one Town-based Practical Stage scenario baseline manifest.",
    )
    add_common_arguments(generate_practical_scenario)
    generate_practical_scenario.add_argument(
        "--generated-dir",
        default="scenarios/practical",
        help="Directory where generated Practical scenario JSON files are written.",
    )
    generate_practical_scenario.add_argument(
        "--manifest-dir",
        default="experiments/practical",
        help="Directory where richer Practical scenario manifests are written.",
    )
    generate_practical_scenario.add_argument(
        "--scenario-prefix",
        default="aed_practical_scenario",
        help="Prefix used for generated Practical scenario ids.",
    )
    generate_practical_scenario.add_argument(
        "--sampling-resolution",
        type=float,
        default=2.0,
        help="Route sampling resolution passed to CARLA GlobalRoutePlanner.",
    )
    generate_practical_scenario.add_argument(
        "--candidate-budget",
        type=int,
        default=120,
        help="Approximate number of Practical spawn/destination route candidates to score.",
    )
    generate_practical_scenario.add_argument(
        "--result-path",
        default=None,
        help="Optional Practical result JSON used to adapt the next Town scenario.",
    )
    generate_practical_scenario.add_argument(
        "--result-dir",
        default="results/practical",
        help="Directory used to find the latest Practical result when --result-path is omitted.",
    )

    run_practical_scenario = subparsers.add_parser(
        "run-practical-scenario",
        help="Load a generated Practical Stage scenario, spawn the ego vehicle, and drive it manually.",
    )
    add_common_arguments(run_practical_scenario)
    run_practical_scenario.add_argument(
        "--scenario-path",
        required=True,
        help="Generated Practical scenario JSON file to run.",
    )
    run_practical_scenario.add_argument(
        "--spectator-mode",
        choices=("fixed-overview", "follow"),
        default="follow",
        help="Spectator mode used while driving the Practical scenario.",
    )
    run_practical_scenario.add_argument(
        "--keep-vehicle",
        action="store_true",
        help="Keep the Practical ego vehicle alive after exit.",
    )
    run_practical_scenario.add_argument(
        "--duration-seconds",
        type=float,
        default=0.0,
        help="Optional auto-exit duration passed to the Practical driving runner.",
    )

    generate_next_map = subparsers.add_parser(
        "generate-next-map",
        help="Generate the next map automatically from the latest or selected evaluation result.",
    )
    add_common_arguments(generate_next_map)
    generate_next_map.add_argument(
        "--result-path",
        default=None,
        help="Optional evaluation JSON file used as the source for the next map.",
    )
    generate_next_map.add_argument(
        "--result-dir",
        default="results/manual_sequence",
        help="Directory scanned when --result-path is omitted.",
    )
    generate_next_map.add_argument(
        "--generated-dir",
        default="maps/generated",
        help="Directory where generated .xodr files are written.",
    )
    generate_next_map.add_argument(
        "--manifest-dir",
        default="experiments",
        help="Directory where generated manifest JSON files are written.",
    )
    generate_next_map.add_argument(
        "--map-prefix",
        default="aed_auto_generated",
        help="Prefix used for the next automatically generated map id.",
    )
    generate_next_map.add_argument(
        "--default-level",
        type=float,
        default=0.30,
        help="Fallback difficulty level when the previous map level cannot be resolved.",
    )
    generate_next_map.add_argument(
        "--load-after-generate",
        action="store_true",
        help="Immediately load the generated map into CARLA.",
    )
    generate_next_map.add_argument(
        "--spectator-mode",
        choices=("fixed-overview", "follow"),
        default="fixed-overview",
        help="Spectator mode used when --manual-drive-after-generate is enabled.",
    )
    generate_next_map.add_argument(
        "--keep-vehicle",
        action="store_true",
        help="Keep the vehicle alive after exit when --manual-drive-after-generate is used.",
    )
    generate_next_map.add_argument(
        "--manual-drive-after-generate",
        action="store_true",
        help="After generation, launch manual driving on the generated map instead of stopping after load.",
    )

    raw_args = sys.argv[1:]
    known_commands = {
        "show-session",
        "gui",
        "manual-sequence",
        "manual-track",
        "manual-xodr",
        "load-xodr",
        "load-town",
        "generate-practical-scenario",
        "run-practical-scenario",
        "generate-next-map",
    }
    has_command = any(
        token in known_commands for token in raw_args if token and not token.startswith("-")
    )
    normalized_args = raw_args if has_command else ["gui", *raw_args]
    return parser.parse_args(normalized_args)


def _run_module(module_name: str, extra_args: list[str]) -> int:
    return int(run_module_main(module_name, extra_args))


def _build_runtime_args(args: argparse.Namespace) -> list[str]:
    runtime_args = [
        "--host",
        args.host,
        "--port",
        str(args.port),
        "--timeout",
        str(args.timeout),
    ]
    if args.pythonapi_path:
        runtime_args.extend(["--pythonapi-path", args.pythonapi_path])
    return runtime_args


def _append_integration_args(script_args: list[str], args: argparse.Namespace) -> None:
    preferred_blueprint_id = str(getattr(args, "preferred_blueprint_id", "") or "").strip()
    role_name = str(getattr(args, "role_name", "") or "").strip()
    driver_backend = str(getattr(args, "driver_backend", "manual") or "manual").strip() or "manual"
    vehicle_config_path = str(getattr(args, "vehicle_config_path", "") or "").strip()
    driver_module_path = str(getattr(args, "driver_module_path", "") or "").strip()
    external_command = str(getattr(args, "external_driver_command", "") or "").strip()
    external_working_dir = str(getattr(args, "external_driver_working_dir", "") or "").strip()
    if driver_backend == "manual":
        if driver_module_path:
            driver_backend = "external_module"
        elif external_command:
            driver_backend = "external_command"
    integration_active = bool(
        bool(getattr(args, "integration_custom_enabled", False))
        or preferred_blueprint_id
        or role_name
        or vehicle_config_path
        or driver_module_path
        or external_command
        or driver_backend != "manual"
    )
    if not integration_active:
        return
    script_args.append("--integration-custom-enabled")
    if preferred_blueprint_id:
        script_args.extend(["--preferred-blueprint-id", preferred_blueprint_id])
    if role_name:
        script_args.extend(["--role-name", role_name])
    script_args.extend(["--driver-backend", driver_backend])
    if vehicle_config_path:
        script_args.extend(["--vehicle-config-path", vehicle_config_path])
    if driver_backend == "external_module" and driver_module_path:
        script_args.extend(["--driver-module-path", driver_module_path])
    if driver_backend == "external_command":
        if external_command:
            script_args.extend(["--external-driver-command", external_command])
        if external_working_dir:
            script_args.extend(["--external-driver-working-dir", external_working_dir])
        startup_wait = float(getattr(args, "external_driver_startup_wait", 2.0) or 0.0)
        script_args.extend(["--external-driver-startup-wait", str(startup_wait)])


def _is_intermediate_stage(args: argparse.Namespace) -> bool:
    return str(getattr(args, "training_stage", "track")).strip().lower() == "intermediate"


def _append_stage_drive_args(
    script_args: list[str],
    args: argparse.Namespace,
    *,
    include_evaluation: bool,
) -> None:
    if not _is_intermediate_stage(args):
        return
    script_args.extend(["--wall-height", "0.0"])
    if include_evaluation:
        script_args.extend(["--offroad-margin", "0.10"])
        script_args.extend(["--path-tolerance", "1.25"])


def _run_manual_xodr_from_path(args: argparse.Namespace, xodr_path: str) -> int:
    script_args = [
        "--xodr-path",
        xodr_path,
        "--training-stage",
        str(getattr(args, "training_stage", "track")),
        "--spectator-mode",
        getattr(args, "spectator_mode", "fixed-overview"),
        *_build_runtime_args(args),
    ]
    _append_stage_drive_args(script_args, args, include_evaluation=True)
    _append_integration_args(script_args, args)
    if getattr(args, "keep_vehicle", False):
        script_args.append("--keep-vehicle")
    return _run_module("scripts.carla_runner.run_manual_xodr_demo", script_args)


def main() -> None:
    configure_runtime_workspace(Path(__file__))
    try:
        args = parse_args()
        session = build_current_manual_demo_session(
            session_name=args.session_name,
            pythonapi_path=args.pythonapi_path,
            training_stage=args.training_stage,
            practical_town=args.practical_town,
            practical_weather=args.practical_weather,
            practical_traffic=args.practical_traffic,
            practical_route=args.practical_route,
            practical_custom_enabled=args.practical_custom_enabled,
            practical_custom_vehicle_count=args.practical_custom_vehicle_count,
            practical_custom_pedestrian_count=args.practical_custom_pedestrian_count,
            practical_custom_route_length=args.practical_custom_route_length,
            practical_custom_junction_focus=args.practical_custom_junction_focus,
            practical_custom_note=args.practical_custom_note,
            integration_custom_enabled=args.integration_custom_enabled,
            preferred_blueprint_id=args.preferred_blueprint_id,
            role_name=args.role_name,
            driver_backend=args.driver_backend,
            external_driver_command=args.external_driver_command,
            external_driver_working_dir=args.external_driver_working_dir,
            external_driver_startup_wait=args.external_driver_startup_wait,
            vehicle_config_path=args.vehicle_config_path,
            driver_module_path=args.driver_module_path,
        )

        if args.command == "show-session":
            print(format_session_summary(session))
            return

        if args.command == "gui":
            script_args: list[str] = []
            if args.pythonapi_path:
                script_args.extend(["--pythonapi-path", args.pythonapi_path])
            raise SystemExit(_run_module("scripts.app.gui", script_args))

        if args.command == "manual-sequence":
            script_args = [
                "--map-id",
                args.map_id,
                "--spectator-mode",
                args.spectator_mode,
            ]
            script_args.extend(_build_runtime_args(args))
            if args.keep_vehicle:
                script_args.append("--keep-vehicle")
            raise SystemExit(_run_module("scripts.carla_runner.run_manual_map_sequence_demo", script_args))

        if args.command == "manual-track":
            script_args = [
                "--map-id",
                args.map_id,
                "--spectator-mode",
                args.spectator_mode,
            ]
            script_args.extend(_build_runtime_args(args))
            if args.keep_vehicle:
                script_args.append("--keep-vehicle")
            raise SystemExit(_run_module("scripts.carla_runner.run_manual_track_demo", script_args))

        if args.command == "manual-xodr":
            raise SystemExit(_run_manual_xodr_from_path(args, args.xodr_path))

        if args.command == "load-xodr":
            script_args = [
                "--xodr-path",
                args.xodr_path,
                *_build_runtime_args(args),
            ]
            _append_stage_drive_args(script_args, args, include_evaluation=False)
            raise SystemExit(_run_module("scripts.carla_runner.load_xodr_in_carla", script_args))

        if args.command == "load-town":
            script_args = [
                "--town-id",
                args.practical_town,
                "--weather-preset",
                args.practical_weather,
                *_build_runtime_args(args),
            ]
            raise SystemExit(_run_module("scripts.carla_runner.load_town_in_carla", script_args))

        if args.command == "generate-practical-scenario":
            script_args = [
                "--practical-town",
                args.practical_town,
                "--practical-weather",
                args.practical_weather,
                "--practical-traffic",
                args.practical_traffic,
                "--practical-route",
                args.practical_route,
                "--generated-dir",
                args.generated_dir,
                "--manifest-dir",
                args.manifest_dir,
                "--scenario-prefix",
                args.scenario_prefix,
                "--sampling-resolution",
                str(args.sampling_resolution),
                "--candidate-budget",
                str(args.candidate_budget),
                "--result-dir",
                args.result_dir,
                *_build_runtime_args(args),
            ]
            if args.result_path:
                script_args.extend(["--result-path", args.result_path])
            if args.practical_custom_enabled:
                script_args.append("--practical-custom-enabled")
            if args.practical_custom_vehicle_count is not None:
                script_args.extend(["--practical-custom-vehicle-count", str(args.practical_custom_vehicle_count)])
            if args.practical_custom_pedestrian_count is not None:
                script_args.extend(["--practical-custom-pedestrian-count", str(args.practical_custom_pedestrian_count)])
            if args.practical_custom_route_length is not None:
                script_args.extend(["--practical-custom-route-length", str(args.practical_custom_route_length)])
            if args.practical_custom_junction_focus is not None:
                script_args.extend(["--practical-custom-junction-focus", args.practical_custom_junction_focus])
            if args.practical_custom_note:
                script_args.extend(["--practical-custom-note", args.practical_custom_note])
            raise SystemExit(_run_module("scripts.app.practical_scenario_generation", script_args))

        if args.command == "run-practical-scenario":
            script_args = [
                "--scenario-path",
                args.scenario_path,
                "--spectator-mode",
                args.spectator_mode,
                "--duration-seconds",
                str(args.duration_seconds),
                *_build_runtime_args(args),
            ]
            _append_integration_args(script_args, args)
            if args.keep_vehicle:
                script_args.append("--keep-vehicle")
            raise SystemExit(_run_module("scripts.carla_runner.run_practical_scenario_demo", script_args))

        if args.command == "generate-next-map":
            auto_args = SimpleNamespace(
                result_path=Path(args.result_path).resolve() if args.result_path else None,
                result_dir=Path(args.result_dir),
                generated_dir=Path(args.generated_dir),
                manifest_dir=Path(args.manifest_dir),
                map_prefix=args.map_prefix,
                default_level=args.default_level,
                load_after_generate=bool(args.load_after_generate and not args.manual_drive_after_generate),
                host=args.host,
                port=args.port,
                timeout=args.timeout,
                pythonapi_path=args.pythonapi_path,
                training_stage=args.training_stage,
                vertex_distance=2.0,
                max_road_length=50.0,
                wall_height=0.0 if _is_intermediate_stage(args) else 1.0,
                additional_width=0.6,
                no_smooth_junctions=False,
                no_mesh_visibility=False,
                keep_settings=False,
            )
            decision = generate_next_map_from_result(auto_args)
            from scripts.app.auto_generation import _print_decision  # local import to avoid cycles during startup

            _print_decision(decision)
            if args.manual_drive_after_generate:
                raise SystemExit(_run_manual_xodr_from_path(args, str(decision.generated_xodr_path)))
            return

        raise SystemExit(f"Unsupported command: {args.command}")
    except Exception as error:
        print("AED launcher command failed.")
        print(f"Reason: {error}")
        raise SystemExit(1)


if __name__ == "__main__":
    main()
