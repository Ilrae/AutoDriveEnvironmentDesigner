"""Factory helpers that compose current demo modules into an app-level session."""

from __future__ import annotations

from pathlib import Path

from scripts.app.models import (
    ApplicationSessionSpec,
    CarlaRuntimeSpec,
    EvaluationSpec,
    MapGenerationSpec,
    SessionUiSpec,
)
from scripts.app.practical_stage import build_practical_stage_parameters
from scripts.app.training_stages import resolve_training_stage
from scripts.carla_runner.integration_loader import load_vehicle_integration_config
from scripts.carla_runner.driver_profiles import (
    create_external_driver_profile,
    create_manual_driver_profile,
)
from scripts.carla_runner.input_bindings import create_split_input_binding
from scripts.carla_runner.vehicle_profiles import create_builtin_vehicle_profile


def build_current_manual_demo_session(
    *,
    session_name: str = "aed_manual_sequence_session",
    pythonapi_path: str | None = None,
    training_stage: str = "track",
    practical_town: str = "Town03",
    practical_weather: str = "clear_noon",
    practical_traffic: str = "moderate",
    practical_route: str = "urban_loop",
    practical_custom_enabled: bool = False,
    practical_custom_vehicle_count: int | None = None,
    practical_custom_pedestrian_count: int | None = None,
    practical_custom_route_length: int | None = None,
    practical_custom_junction_focus: str | None = None,
    practical_custom_note: str | None = None,
    integration_custom_enabled: bool = False,
    preferred_blueprint_id: str | None = None,
    role_name: str = "hero",
    driver_backend: str = "manual",
    external_driver_command: str | None = None,
    external_driver_working_dir: str | None = None,
    external_driver_startup_wait: float | None = None,
    vehicle_config_path: str | None = None,
    driver_module_path: str | None = None,
) -> ApplicationSessionSpec:
    """Build the current app-level session around manual map sequence driving."""

    stage_option = resolve_training_stage(training_stage)
    is_intermediate_stage = stage_option.stage_id == "intermediate"
    is_practical_stage = stage_option.stage_id == "practical"
    is_road_stage = is_intermediate_stage or is_practical_stage
    path_tolerance_m = 1.25 if is_road_stage else 1.5
    offroad_margin_m = 0.10 if is_road_stage else 0.25
    practical_parameters = build_practical_stage_parameters(
        town_id=practical_town,
        weather_preset=practical_weather,
        traffic_preset=practical_traffic,
        route_preset=practical_route,
        custom_settings_enabled=practical_custom_enabled,
        custom_vehicle_count=practical_custom_vehicle_count,
        custom_pedestrian_count=practical_custom_pedestrian_count,
        custom_route_length_hint_m=practical_custom_route_length,
        custom_junction_focus=practical_custom_junction_focus,
        custom_note=practical_custom_note,
    )
    vehicle_config: dict[str, object] = {}
    normalized_driver_backend = (driver_backend or "manual").strip().lower()
    if normalized_driver_backend == "manual":
        if (driver_module_path or "").strip():
            normalized_driver_backend = "external_module"
        elif (external_driver_command or "").strip():
            normalized_driver_backend = "external_command"
    integration_active = bool(
        integration_custom_enabled
        or (vehicle_config_path or "").strip()
        or (preferred_blueprint_id or "").strip()
        or (role_name or "").strip()
        or (driver_module_path or "").strip()
        or (external_driver_command or "").strip()
        or normalized_driver_backend != "manual"
    )
    if integration_active and vehicle_config_path:
        try:
            vehicle_config = load_vehicle_integration_config(vehicle_config_path)
        except Exception:
            vehicle_config = {}
    active_role_name = (
        (role_name or "").strip()
        or str(vehicle_config.get("role_name", "")).strip()
        or "hero"
    )
    active_preferred_blueprint_id = None
    if integration_active:
        active_preferred_blueprint_id = (
            (preferred_blueprint_id or "").strip()
            or str(vehicle_config.get("preferred_blueprint_id", "")).strip()
            or None
        )
    active_blueprint_filter = (
        str(vehicle_config.get("blueprint_filter", "")).strip() or "vehicle.*"
    )
    active_color = str(vehicle_config.get("color", "")).strip() or None
    vehicle_profile = create_builtin_vehicle_profile(
        profile_name="app_builtin_vehicle",
        blueprint_filter=active_blueprint_filter,
        preferred_blueprint_id=active_preferred_blueprint_id,
        role_name=active_role_name,
        color=active_color,
        notes=(
            "Current application-owned ego vehicle profile used while validating "
            "generated tracks and Town scenarios."
        ),
    )
    if integration_active and normalized_driver_backend == "external_module":
        driver_profile = create_external_driver_profile(
            profile_name="app_external_module_driver",
            external_entrypoint=(driver_module_path or "").strip() or None,
            notes=(
                "Application loads one user-supplied Python keyboard-control module "
                "while continuing to own the ego vehicle, evaluation, and result saving."
            ),
            runtime_options={
                "backend": "external_module",
                "driver_module_path": (driver_module_path or "").strip() or None,
            },
        )
    elif integration_active and normalized_driver_backend == "external_command":
        driver_profile = create_external_driver_profile(
            profile_name="app_external_driver",
            external_entrypoint=(external_driver_command or "").strip() or None,
            notes=(
                "Application launches one user-supplied external driving command "
                "after spawning the ego vehicle. That external stack is expected "
                "to attach sensors and control the app-owned actor by role_name."
            ),
            runtime_options={
                "backend": "external_command",
                "working_dir": (external_driver_working_dir or "").strip() or None,
                "startup_wait_seconds": (
                    float(external_driver_startup_wait)
                    if external_driver_startup_wait is not None
                    else 0.0
                ),
            },
        )
    else:
        driver_profile = create_manual_driver_profile(
            profile_name="app_manual_driver",
            notes=(
                "Current application uses manual keyboard driving as the default "
                "validation backend."
            ),
        )
    input_binding = create_split_input_binding(
        vehicle_profile=vehicle_profile,
        driver_profile=driver_profile,
        notes=(
            "Vehicle selection and driving backend are kept separate so user "
            "driving stacks can reuse the same app-owned spawn flow."
        ),
    )
    return ApplicationSessionSpec(
        session_name=session_name,
        runtime=CarlaRuntimeSpec(
            pythonapi_path=pythonapi_path,
            spectator_mode="fixed-overview",
        ),
        map_generation=MapGenerationSpec(
            generator_mode=(
                "town_scenario_generation_shell"
                if is_practical_stage
                else "result_driven_auto_generation"
            ),
            generated_dir=(
                Path("scenarios/practical")
                if is_practical_stage
                else Path("maps/generated")
            ),
            manifest_dir=(
                Path("experiments/practical")
                if is_practical_stage
                else Path("experiments")
            ),
            parameters={
                "current_demo_case_count": 2,
                "map_reload_supported": True,
                "next_map_shortcut": "N",
                "reload_current_shortcut": "R",
                "result_source_dir": "results/manual_sequence",
                "auto_generation_mode": "latest_or_selected_result",
                "auto_generation_layout": (
                    "town_scenario_shell"
                    if is_practical_stage
                    else "intermediate_road_course"
                    if is_intermediate_stage
                    else "open_course"
                ),
                "traffic_side": "right",
                "training_stage": stage_option.stage_id,
                "training_stage_display": stage_option.display_name,
                "training_stage_status": stage_option.implementation_status,
                **practical_parameters,
            },
        ),
        vehicle_profile=vehicle_profile,
        driver_profile=driver_profile,
        input_binding=input_binding,
        evaluation=EvaluationSpec(
            path_tolerance_m=path_tolerance_m,
            offroad_margin_m=offroad_margin_m,
            finish_line_half_width_m=6.0,
            fail_on_collision=True,
            fail_on_course_departure=True,
            fail_on_not_finished=True,
        ),
        ui=SessionUiSpec(
            mode="aed_control_panel",
            notes=(
                f"Current UI is an AED control panel focused on the "
                f"{stage_option.display_name.lower()}. Manual driving still runs in "
                "a temporary pygame sub-window while the main application shell grows."
            ),
        ),
    )


def format_session_summary(spec: ApplicationSessionSpec) -> str:
    """Return a readable text summary for the current application structure."""

    lines = [
        f"Session: {spec.session_name}",
        f"Runtime: host={spec.runtime.host}, port={spec.runtime.port}, spectator={spec.runtime.spectator_mode}",
    ]
    if spec.map_generation.parameters.get("training_stage") == "practical":
        lines.append(
            (
                "Scenario generation: "
                f"mode={spec.map_generation.generator_mode}, "
                f"town={spec.map_generation.parameters.get('town_display', 'Town03')}, "
                f"weather={spec.map_generation.parameters.get('weather_display', 'Clear Noon')}, "
                f"traffic={spec.map_generation.parameters.get('traffic_display', 'Moderate')} "
                f"({spec.map_generation.parameters.get('traffic_vehicle_count', 0)} vehicles / "
                f"{spec.map_generation.parameters.get('pedestrian_count', 0)} pedestrians), "
                f"route={spec.map_generation.parameters.get('route_display', 'Urban Loop')} "
                f"(~{spec.map_generation.parameters.get('route_length_hint_m', 0)}m, "
                f"junction_focus={spec.map_generation.parameters.get('junction_focus', 'medium')})"
            )
        )
        if spec.map_generation.parameters.get("custom_settings_enabled"):
            lines.append(
                (
                    "Scenario override: "
                    f"{spec.map_generation.parameters.get('custom_summary', 'custom practical settings active')}"
                )
            )
    else:
        lines.append(
            (
                "Map generation: "
                f"mode={spec.map_generation.generator_mode}, "
                f"generated_dir={spec.map_generation.generated_dir}, "
                f"manifest_dir={spec.map_generation.manifest_dir}, "
                f"result_source_dir={spec.map_generation.parameters.get('result_source_dir', 'n/a')}, "
                f"training_stage={spec.map_generation.parameters.get('training_stage_display', 'Track Driving Stage')}, "
                f"layout={spec.map_generation.parameters.get('auto_generation_layout', 'open_course')}, "
                f"traffic_side={spec.map_generation.parameters.get('traffic_side', 'right')}"
            )
        )
    lines.extend(
        [
            f"Vehicle profile: {spec.vehicle_profile.describe()}",
            f"Driver profile: {spec.driver_profile.describe()}",
            f"Input binding: {spec.input_binding.describe()}",
            (
                "Evaluation: "
                f"path_tolerance={spec.evaluation.path_tolerance_m:.2f}m, "
                f"offroad_margin={spec.evaluation.offroad_margin_m:.2f}m, "
                f"finish_line_half_width={spec.evaluation.finish_line_half_width_m:.2f}m"
            ),
            f"UI: mode={spec.ui.mode}",
        ]
    )
    return "\n".join(lines)
