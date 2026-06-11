"""Generate one Town-based Practical Stage scenario manifest from current presets."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import importlib
import json
import math
from pathlib import Path
import re
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.app.practical_stage import build_practical_stage_parameters
from scripts.carla_runner.carla_utils import create_client
from scripts.evaluation.result_models import load_episode_result
from scripts.evaluation.scoring import compute_driving_score


@dataclass(frozen=True)
class PracticalScenarioDecision:
    """One generated Practical Stage baseline scenario."""

    scenario_id: str
    scenario_path: Path
    manifest_path: Path
    town_id: str
    weather_preset: str
    traffic_vehicle_count: int
    pedestrian_count: int
    route_length_hint_m: int
    actual_route_length_m: float
    junction_focus: str
    actual_junction_ratio: float
    turn_count: int
    spawn_index: int
    destination_index: int
    spawn_count: int
    scenario_mode: str
    adaptation_mode: str
    adaptation_summary: str


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate one Town-based Practical Stage baseline scenario manifest.",
    )
    parser.add_argument("--host", default="localhost", help="CARLA server host.")
    parser.add_argument("--port", type=int, default=2000, help="CARLA server port.")
    parser.add_argument("--timeout", type=float, default=30.0, help="Connection timeout in seconds.")
    parser.add_argument(
        "--pythonapi-path",
        default=None,
        help="Optional CARLA root or PythonAPI path.",
    )
    parser.add_argument("--practical-town", default="Town03", help="Target CARLA Town id.")
    parser.add_argument("--practical-weather", default="clear_noon", help="Practical weather preset id.")
    parser.add_argument("--practical-traffic", default="moderate", help="Practical traffic preset id.")
    parser.add_argument("--practical-route", default="urban_loop", help="Practical route preset id.")
    parser.add_argument(
        "--practical-custom-enabled",
        action="store_true",
        help="Enable custom route/traffic overrides instead of preset-only adaptation.",
    )
    parser.add_argument("--practical-custom-vehicle-count", type=int, default=None)
    parser.add_argument("--practical-custom-pedestrian-count", type=int, default=None)
    parser.add_argument("--practical-custom-route-length", type=int, default=None)
    parser.add_argument("--practical-custom-junction-focus", default=None)
    parser.add_argument("--practical-custom-note", default=None)
    parser.add_argument(
        "--generated-dir",
        type=Path,
        default=Path("scenarios/practical"),
        help="Directory where generated practical scenario JSON files are written.",
    )
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        default=Path("experiments/practical"),
        help="Directory where richer practical scenario manifests are written.",
    )
    parser.add_argument(
        "--scenario-prefix",
        default="aed_practical_scenario",
        help="Prefix used for generated Practical scenario ids.",
    )
    parser.add_argument(
        "--sampling-resolution",
        type=float,
        default=2.0,
        help="Route sampling resolution passed to CARLA GlobalRoutePlanner.",
    )
    parser.add_argument(
        "--candidate-budget",
        type=int,
        default=120,
        help="Approximate number of origin/destination route candidates to score.",
    )
    parser.add_argument(
        "--result-path",
        type=Path,
        default=None,
        help="Optional Practical result JSON used as the adaptation source for the next scenario.",
    )
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=Path("results/practical"),
        help="Directory used to find the latest Practical result when --result-path is omitted.",
    )
    return parser.parse_args()


def _normalize_map_name(map_name: str) -> str:
    return map_name.replace("\\", "/").split("/")[-1].strip().lower()


def _ensure_town_loaded(client: Any, world: Any, town_id: str) -> Any:
    current_map_name = _normalize_map_name(world.get_map().name)
    if current_map_name == town_id.strip().lower():
        return world
    return client.load_world(town_id)


def _load_route_planner_type() -> Any:
    module = importlib.import_module("agents.navigation.global_route_planner")
    return getattr(module, "GlobalRoutePlanner")


def _build_next_scenario_id(prefix: str, generated_dir: Path) -> str:
    pattern = re.compile(rf"^{re.escape(prefix)}_(\d+)$")
    max_index = 0
    for candidate in generated_dir.glob(f"{prefix}_*.json"):
        match = pattern.match(candidate.stem)
        if match is None:
            continue
        max_index = max(max_index, int(match.group(1)))
    return f"{prefix}_{max_index + 1:03d}"


def _stable_seed(seed_key: str) -> int:
    return sum((index + 1) * ord(character) for index, character in enumerate(seed_key))


def _distance_between_locations(first: Any, second: Any) -> float:
    return math.sqrt(
        (float(first.x) - float(second.x)) ** 2
        + (float(first.y) - float(second.y)) ** 2
        + (float(first.z) - float(second.z)) ** 2
    )


def _route_metrics(route_trace: list[tuple[Any, Any]]) -> dict[str, Any]:
    if not route_trace:
        return {
            "route_length_m": 0.0,
            "junction_ratio": 0.0,
            "junction_waypoint_count": 0,
            "turn_count": 0,
            "waypoint_count": 0,
        }

    route_length_m = 0.0
    junction_waypoint_count = 0
    turn_count = 0
    previous_waypoint = route_trace[0][0]
    previous_turn_option: str | None = None
    for waypoint, road_option in route_trace:
        if waypoint.is_junction:
            junction_waypoint_count += 1
        option_name = getattr(road_option, "name", str(road_option))
        if option_name in {"LEFT", "RIGHT", "STRAIGHT"}:
            if option_name != previous_turn_option:
                turn_count += 1
            previous_turn_option = option_name
        else:
            previous_turn_option = None
        route_length_m += _distance_between_locations(
            previous_waypoint.transform.location,
            waypoint.transform.location,
        )
        previous_waypoint = waypoint

    waypoint_count = len(route_trace)
    return {
        "route_length_m": route_length_m,
        "junction_ratio": (junction_waypoint_count / waypoint_count) if waypoint_count else 0.0,
        "junction_waypoint_count": junction_waypoint_count,
        "turn_count": turn_count,
        "waypoint_count": waypoint_count,
    }


def _target_junction_ratio(junction_focus: str) -> float:
    if junction_focus == "low":
        return 0.05
    if junction_focus == "high":
        return 0.22
    return 0.12


def _score_route_candidate(
    *,
    route_metrics: dict[str, Any],
    target_length_m: int,
    target_junction_focus: str,
) -> float:
    actual_length = float(route_metrics["route_length_m"])
    actual_junction_ratio = float(route_metrics["junction_ratio"])
    turn_count = int(route_metrics["turn_count"])
    waypoint_count = int(route_metrics["waypoint_count"])

    length_penalty = abs(actual_length - float(target_length_m)) / max(float(target_length_m), 1.0)
    junction_penalty = abs(actual_junction_ratio - _target_junction_ratio(target_junction_focus)) * 4.0
    short_route_penalty = 0.0
    if actual_length < float(target_length_m) * 0.55:
        short_route_penalty += 1.25
    if waypoint_count < 50:
        short_route_penalty += 0.75
    turn_penalty = 0.0
    if target_junction_focus != "low" and turn_count == 0:
        turn_penalty += 1.0

    return length_penalty + junction_penalty + short_route_penalty + turn_penalty


def _candidate_index_pairs(spawn_count: int, budget: int, seed_key: str) -> list[tuple[int, int]]:
    if spawn_count < 2:
        return []

    seed = _stable_seed(seed_key)
    origin_budget = max(8, min(24, budget // 6))
    offset_budget = max(5, min(8, budget // max(origin_budget, 1)))
    origin_stride = max(1, spawn_count // origin_budget)
    base_offsets = [
        max(1, spawn_count // 11),
        max(1, spawn_count // 9),
        max(1, spawn_count // 7),
        max(1, spawn_count // 5),
        max(1, spawn_count // 4),
        max(1, spawn_count // 3),
        max(1, spawn_count // 2),
    ]
    offset_values = sorted(set(base_offsets[:offset_budget]))
    pairs: list[tuple[int, int]] = []
    seen_pairs: set[tuple[int, int]] = set()

    for origin_step in range(origin_budget):
        origin_index = (seed + (origin_step * origin_stride)) % spawn_count
        for offset_step, offset_value in enumerate(offset_values):
            destination_index = (
                origin_index
                + offset_value
                + ((offset_step + 1) * ((seed % 5) + 1))
            ) % spawn_count
            if destination_index == origin_index:
                continue
            pair = (origin_index, destination_index)
            if pair in seen_pairs:
                continue
            seen_pairs.add(pair)
            pairs.append(pair)
            if len(pairs) >= budget:
                return pairs

    lcg_state = max(seed, 1)
    while len(pairs) < budget:
        lcg_state = (1103515245 * lcg_state + 12345) % (2 ** 31)
        origin_index = lcg_state % spawn_count
        lcg_state = (1103515245 * lcg_state + 12345) % (2 ** 31)
        destination_index = lcg_state % spawn_count
        if destination_index == origin_index:
            continue
        pair = (origin_index, destination_index)
        if pair in seen_pairs:
            continue
        seen_pairs.add(pair)
        pairs.append(pair)

    return pairs


def _serialize_transform(transform: Any, *, spawn_index: int | None = None) -> dict[str, Any]:
    payload = {
        "x": round(float(transform.location.x), 3),
        "y": round(float(transform.location.y), 3),
        "z": round(float(transform.location.z), 3),
        "yaw": round(float(transform.rotation.yaw), 3),
        "pitch": round(float(transform.rotation.pitch), 3),
        "roll": round(float(transform.rotation.roll), 3),
    }
    if spawn_index is not None:
        payload["spawn_index"] = int(spawn_index)
    return payload


def _serialize_route_trace(route_trace: list[tuple[Any, Any]]) -> list[dict[str, Any]]:
    serialized: list[dict[str, Any]] = []
    for index, (waypoint, road_option) in enumerate(route_trace):
        serialized.append(
            {
                "index": index,
                "x": round(float(waypoint.transform.location.x), 3),
                "y": round(float(waypoint.transform.location.y), 3),
                "z": round(float(waypoint.transform.location.z), 3),
                "yaw": round(float(waypoint.transform.rotation.yaw), 3),
                "road_id": int(waypoint.road_id),
                "section_id": int(waypoint.section_id),
                "lane_id": int(waypoint.lane_id),
                "is_junction": bool(waypoint.is_junction),
                "road_option": getattr(road_option, "name", str(road_option)),
            }
        )
    return serialized


def _resolve_result_source(result_path: Path | None, result_dir: Path) -> Path | None:
    if result_path is not None:
        candidate = result_path.resolve()
        return candidate if candidate.exists() else None
    if not result_dir.exists():
        return None
    candidates = sorted(
        result_dir.glob("*.json"),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )
    return candidates[0].resolve() if candidates else None


def _shift_junction_focus(current_focus: str, delta: int) -> str:
    focus_order = ["low", "medium", "high"]
    try:
        current_index = focus_order.index(current_focus)
    except ValueError:
        current_index = 1
    next_index = max(0, min(len(focus_order) - 1, current_index + int(delta)))
    return focus_order[next_index]


def _build_adaptation_payload(
    practical_parameters: dict[str, Any],
    *,
    result_source_path: Path | None,
    previous_result: Any | None = None,
) -> tuple[dict[str, Any], dict[str, Any]]:
    parameters = dict(practical_parameters)
    custom_settings_enabled = bool(parameters.get("custom_settings_enabled"))
    applied_manual_overrides: list[str] = []
    traffic_vehicle_count = int(parameters.get("preset_traffic_vehicle_count", parameters["traffic_vehicle_count"]))
    pedestrian_count = int(parameters.get("preset_pedestrian_count", parameters["pedestrian_count"]))
    route_length_hint_m = int(parameters.get("preset_route_length_hint_m", parameters["route_length_hint_m"]))
    junction_focus = str(parameters.get("preset_junction_focus", parameters["junction_focus"]))

    if previous_result is None and result_source_path is None:
        if custom_settings_enabled:
            if parameters.get("custom_vehicle_count") is not None:
                traffic_vehicle_count = max(0, int(parameters["custom_vehicle_count"]))
                applied_manual_overrides.append("vehicles")
            if parameters.get("custom_pedestrian_count") is not None:
                pedestrian_count = max(0, int(parameters["custom_pedestrian_count"]))
                applied_manual_overrides.append("pedestrians")
            if parameters.get("custom_route_length_hint_m") is not None:
                route_length_hint_m = max(100, int(parameters["custom_route_length_hint_m"]))
                applied_manual_overrides.append("route_length")
            if parameters.get("custom_junction_focus") in {"low", "medium", "high"}:
                junction_focus = str(parameters["custom_junction_focus"])
                applied_manual_overrides.append("junction_focus")
        parameters["traffic_vehicle_count"] = traffic_vehicle_count
        parameters["pedestrian_count"] = pedestrian_count
        parameters["route_length_hint_m"] = route_length_hint_m
        parameters["junction_focus"] = junction_focus
        return parameters, {
            "mode": "preset_with_custom_overrides" if applied_manual_overrides else "preset_only",
            "source_result_path": None,
            "source_map_id": None,
            "source_score": None,
            "applied_manual_overrides": applied_manual_overrides,
            "summary": (
                "No previous Practical result was found, so the next scenario uses the selected Town presets directly."
                if not applied_manual_overrides
                else (
                    "No previous Practical result was found, so the next scenario uses the selected Town presets "
                    f"with manual overrides for {', '.join(applied_manual_overrides)}."
                )
            ),
        }

    if previous_result is None:
        previous_result = load_episode_result(result_source_path)
    source_score = compute_driving_score(
        completion_ratio=previous_result.completion_ratio,
        path_tracking_score=previous_result.path_tracking_score,
        crossed_finish_line=previous_result.crossed_finish_line,
        offroad_ratio=previous_result.offroad_ratio,
        collision_count=previous_result.collision_count,
        failure_reason=previous_result.failure_reason,
        success=previous_result.success,
        lane_discipline_score=previous_result.lane_discipline_score,
        lane_departure_ratio=previous_result.lane_departure_ratio,
        opposite_lane_ratio=previous_result.opposite_lane_ratio,
    )

    adaptation_reasons: list[str] = []

    if previous_result.collision_count > 0:
        traffic_vehicle_count = max(0, traffic_vehicle_count - 10)
        pedestrian_count = max(0, pedestrian_count - 4)
        route_length_hint_m = max(700, route_length_hint_m - 220)
        junction_focus = _shift_junction_focus(junction_focus, -1)
        adaptation_reasons.append("collision_recovery")
    elif previous_result.failure_reason == "not_finished" and previous_result.completion_ratio < 0.25:
        traffic_vehicle_count = max(0, traffic_vehicle_count - 6)
        pedestrian_count = max(0, pedestrian_count - 2)
        route_length_hint_m = max(700, route_length_hint_m - 180)
        if previous_result.lane_discipline_score < 0.92:
            junction_focus = _shift_junction_focus(junction_focus, -1)
        adaptation_reasons.append("completion_recovery")
    elif previous_result.failure_reason in {"course_departure", "wrong_lane"} or previous_result.offroad_ratio > 0.02:
        traffic_vehicle_count = max(0, traffic_vehicle_count - 8)
        pedestrian_count = max(0, pedestrian_count - 3)
        route_length_hint_m = max(700, route_length_hint_m - 140)
        junction_focus = _shift_junction_focus(junction_focus, -1)
        adaptation_reasons.append("stability_recovery")
    elif previous_result.lane_discipline_score < 0.88 or previous_result.lane_departure_ratio > 0.12:
        traffic_vehicle_count = max(0, traffic_vehicle_count - 4)
        pedestrian_count = max(0, pedestrian_count - 1)
        route_length_hint_m = max(800, route_length_hint_m)
        junction_focus = _shift_junction_focus(junction_focus, -1)
        adaptation_reasons.append("lane_focus")
    elif previous_result.success and previous_result.crossed_finish_line and source_score >= 0.90:
        traffic_vehicle_count = min(90, traffic_vehicle_count + 12)
        pedestrian_count = min(40, pedestrian_count + 6)
        route_length_hint_m = min(2600, route_length_hint_m + 320)
        junction_focus = _shift_junction_focus(junction_focus, +1)
        adaptation_reasons.append("difficulty_up")
    elif source_score >= 0.78:
        traffic_vehicle_count = min(80, traffic_vehicle_count + 6)
        pedestrian_count = min(32, pedestrian_count + 3)
        route_length_hint_m = min(2300, route_length_hint_m + 180)
        if previous_result.lane_discipline_score >= 0.95 and previous_result.offroad_ratio <= 0.0:
            junction_focus = _shift_junction_focus(junction_focus, +1)
        adaptation_reasons.append("gentle_up")
    else:
        adaptation_reasons.append("hold")

    if custom_settings_enabled:
        if parameters.get("custom_vehicle_count") is not None:
            traffic_vehicle_count = max(0, int(parameters["custom_vehicle_count"]))
            applied_manual_overrides.append("vehicles")
        if parameters.get("custom_pedestrian_count") is not None:
            pedestrian_count = max(0, int(parameters["custom_pedestrian_count"]))
            applied_manual_overrides.append("pedestrians")
        if parameters.get("custom_route_length_hint_m") is not None:
            route_length_hint_m = max(100, int(parameters["custom_route_length_hint_m"]))
            applied_manual_overrides.append("route_length")
        if parameters.get("custom_junction_focus") in {"low", "medium", "high"}:
            junction_focus = str(parameters["custom_junction_focus"])
            applied_manual_overrides.append("junction_focus")

    parameters["traffic_vehicle_count"] = traffic_vehicle_count
    parameters["pedestrian_count"] = pedestrian_count
    parameters["route_length_hint_m"] = route_length_hint_m
    parameters["junction_focus"] = junction_focus

    return parameters, {
        "mode": "result_driven_with_custom_overrides" if applied_manual_overrides else "result_driven",
        "source_result_path": str(result_source_path),
        "source_map_id": previous_result.map_id,
        "source_score": round(source_score, 4),
        "source_failure_reason": previous_result.failure_reason,
        "source_completion_ratio": round(previous_result.completion_ratio, 4),
        "source_lane_discipline_score": round(previous_result.lane_discipline_score, 4),
        "applied_reasons": adaptation_reasons,
        "applied_manual_overrides": applied_manual_overrides,
        "adjusted_vehicle_count": traffic_vehicle_count,
        "adjusted_pedestrian_count": pedestrian_count,
        "adjusted_route_length_hint_m": route_length_hint_m,
        "adjusted_junction_focus": junction_focus,
        "summary": (
            f"Previous Practical result '{previous_result.map_id}' scored {source_score * 100.0:.1f}/100, "
            f"so the next scenario uses {traffic_vehicle_count} vehicles, {pedestrian_count} pedestrians, "
            f"target~{route_length_hint_m}m, junction_focus={junction_focus}."
            + (
                f" Manual overrides were applied for {', '.join(applied_manual_overrides)}."
                if applied_manual_overrides
                else ""
            )
        ),
    }


def preview_practical_adaptation(
    *,
    traffic_vehicle_count: int,
    pedestrian_count: int,
    route_length_hint_m: int,
    junction_focus: str,
    result: Any,
) -> dict[str, Any]:
    """Summarize how the next Town scenario would adapt from one result."""

    baseline_parameters = {
        "preset_traffic_vehicle_count": int(traffic_vehicle_count),
        "traffic_vehicle_count": int(traffic_vehicle_count),
        "preset_pedestrian_count": int(pedestrian_count),
        "pedestrian_count": int(pedestrian_count),
        "preset_route_length_hint_m": int(route_length_hint_m),
        "route_length_hint_m": int(route_length_hint_m),
        "preset_junction_focus": str(junction_focus),
        "junction_focus": str(junction_focus),
        "custom_settings_enabled": False,
        "custom_vehicle_count": None,
        "custom_pedestrian_count": None,
        "custom_route_length_hint_m": None,
        "custom_junction_focus": None,
    }
    adjusted_parameters, adaptation_payload = _build_adaptation_payload(
        baseline_parameters,
        result_source_path=None,
        previous_result=result,
    )
    return {
        "mode": str(adaptation_payload["mode"]),
        "summary": str(adaptation_payload["summary"]),
        "applied_reasons": list(adaptation_payload.get("applied_reasons", [])),
        "traffic_vehicle_count": int(adjusted_parameters["traffic_vehicle_count"]),
        "pedestrian_count": int(adjusted_parameters["pedestrian_count"]),
        "route_length_hint_m": int(adjusted_parameters["route_length_hint_m"]),
        "junction_focus": str(adjusted_parameters["junction_focus"]),
        "source_score": adaptation_payload.get("source_score"),
    }


def generate_practical_scenario(args: argparse.Namespace) -> PracticalScenarioDecision:
    generated_dir = args.generated_dir.resolve()
    manifest_dir = args.manifest_dir.resolve()
    generated_dir.mkdir(parents=True, exist_ok=True)
    manifest_dir.mkdir(parents=True, exist_ok=True)

    scenario_id = _build_next_scenario_id(args.scenario_prefix, generated_dir)
    practical_parameters = build_practical_stage_parameters(
        town_id=args.practical_town,
        weather_preset=args.practical_weather,
        traffic_preset=args.practical_traffic,
        route_preset=args.practical_route,
        custom_settings_enabled=bool(args.practical_custom_enabled),
        custom_vehicle_count=args.practical_custom_vehicle_count,
        custom_pedestrian_count=args.practical_custom_pedestrian_count,
        custom_route_length_hint_m=args.practical_custom_route_length,
        custom_junction_focus=args.practical_custom_junction_focus,
        custom_note=args.practical_custom_note,
    )
    result_source_path = _resolve_result_source(args.result_path, args.result_dir.resolve())
    practical_parameters, adaptation_payload = _build_adaptation_payload(
        practical_parameters,
        result_source_path=result_source_path,
    )

    carla, client, world = create_client(
        host=args.host,
        port=args.port,
        timeout=args.timeout,
        pythonapi_path=args.pythonapi_path,
    )
    world = _ensure_town_loaded(client, world, practical_parameters["town_id"])
    weather_parameters = getattr(carla.WeatherParameters, practical_parameters["weather_carla_attribute"])
    world.set_weather(weather_parameters)
    current_map = world.get_map()
    spawn_points = current_map.get_spawn_points()
    if len(spawn_points) < 2:
        raise RuntimeError("The selected Town does not expose enough spawn points for route generation.")

    GlobalRoutePlanner = _load_route_planner_type()
    planner = GlobalRoutePlanner(current_map, args.sampling_resolution)

    best_candidate: dict[str, Any] | None = None
    scored_pair_count = 0
    target_length_m = int(practical_parameters["route_length_hint_m"])
    target_junction_focus = str(practical_parameters["junction_focus"])
    candidate_pairs = _candidate_index_pairs(
        len(spawn_points),
        max(16, int(args.candidate_budget)),
        seed_key=scenario_id + practical_parameters["town_id"] + practical_parameters["route_preset"],
    )
    if not candidate_pairs:
        raise RuntimeError("Could not build any spawn-point pairs for Practical route generation.")

    for spawn_index, destination_index in candidate_pairs:
        spawn_transform = spawn_points[spawn_index]
        destination_transform = spawn_points[destination_index]
        try:
            route_trace = planner.trace_route(
                spawn_transform.location,
                destination_transform.location,
            )
        except Exception:
            continue
        if len(route_trace) < 2:
            continue
        scored_pair_count += 1
        metrics = _route_metrics(route_trace)
        candidate_score = _score_route_candidate(
            route_metrics=metrics,
            target_length_m=target_length_m,
            target_junction_focus=target_junction_focus,
        )
        candidate_payload = {
            "spawn_index": spawn_index,
            "destination_index": destination_index,
            "spawn_transform": spawn_transform,
            "destination_transform": destination_transform,
            "route_trace": route_trace,
            "metrics": metrics,
            "score": candidate_score,
        }
        if best_candidate is None or candidate_score < float(best_candidate["score"]):
            best_candidate = candidate_payload

    if best_candidate is None:
        raise RuntimeError("Failed to find a valid Practical route candidate in the selected Town.")

    route_trace = best_candidate["route_trace"]
    route_metrics = best_candidate["metrics"]
    route_start_waypoint = route_trace[0][0]
    route_end_waypoint = route_trace[-1][0]
    scenario_payload = {
        "scenario_id": scenario_id,
        "training_stage": "practical",
        "scenario_mode": practical_parameters["scenario_mode"],
        "town_id": practical_parameters["town_id"],
        "weather_preset": practical_parameters["weather_preset"],
        "traffic_vehicle_count": practical_parameters["traffic_vehicle_count"],
        "pedestrian_count": practical_parameters["pedestrian_count"],
        "route_length_hint_m": practical_parameters["route_length_hint_m"],
        "junction_focus": practical_parameters["junction_focus"],
        "spawn": _serialize_transform(
            route_start_waypoint.transform,
            spawn_index=best_candidate["spawn_index"],
        ),
        "destination": _serialize_transform(
            route_end_waypoint.transform,
            spawn_index=best_candidate["destination_index"],
        ),
        "route_metrics": {
            "actual_route_length_m": round(float(route_metrics["route_length_m"]), 2),
            "actual_junction_ratio": round(float(route_metrics["junction_ratio"]), 4),
            "junction_waypoint_count": int(route_metrics["junction_waypoint_count"]),
            "turn_count": int(route_metrics["turn_count"]),
            "waypoint_count": int(route_metrics["waypoint_count"]),
            "sampling_resolution_m": float(args.sampling_resolution),
        },
        "route_waypoints": _serialize_route_trace(route_trace),
        "adaptation": adaptation_payload,
    }
    manifest_payload = {
        **scenario_payload,
        "route_preset": practical_parameters["route_preset"],
        "route_display": practical_parameters["route_display"],
        "traffic_preset": practical_parameters["traffic_preset"],
        "traffic_display": practical_parameters["traffic_display"],
        "weather_display": practical_parameters["weather_display"],
        "custom_settings_enabled": practical_parameters["custom_settings_enabled"],
        "custom_summary": practical_parameters["custom_summary"],
        "custom_note": practical_parameters["custom_note"],
        "candidate_search": {
            "candidate_budget": int(args.candidate_budget),
            "scored_pair_count": scored_pair_count,
            "best_candidate_score": round(float(best_candidate["score"]), 4),
            "spawn_count": len(spawn_points),
        },
    }

    scenario_path = (generated_dir / f"{scenario_id}.json").resolve()
    manifest_path = (manifest_dir / f"{scenario_id}.json").resolve()
    scenario_path.write_text(
        json.dumps(scenario_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    manifest_path.write_text(
        json.dumps(manifest_payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    return PracticalScenarioDecision(
        scenario_id=scenario_id,
        scenario_path=scenario_path,
        manifest_path=manifest_path,
        town_id=practical_parameters["town_id"],
        weather_preset=practical_parameters["weather_preset"],
        traffic_vehicle_count=int(practical_parameters["traffic_vehicle_count"]),
        pedestrian_count=int(practical_parameters["pedestrian_count"]),
        route_length_hint_m=int(practical_parameters["route_length_hint_m"]),
        actual_route_length_m=float(route_metrics["route_length_m"]),
        junction_focus=str(practical_parameters["junction_focus"]),
        actual_junction_ratio=float(route_metrics["junction_ratio"]),
        turn_count=int(route_metrics["turn_count"]),
        spawn_index=int(best_candidate["spawn_index"]),
        destination_index=int(best_candidate["destination_index"]),
        spawn_count=len(spawn_points),
        scenario_mode=str(practical_parameters["scenario_mode"]),
        adaptation_mode=str(adaptation_payload["mode"]),
        adaptation_summary=str(adaptation_payload["summary"]),
    )


def _print_decision(decision: PracticalScenarioDecision) -> None:
    print(f"Generated Practical scenario: {decision.scenario_id}")
    print(
        "Scenario mode: "
        f"{decision.scenario_mode} / {decision.town_id} / weather={decision.weather_preset}"
    )
    print(
        "Traffic + route: "
        f"{decision.traffic_vehicle_count} vehicles / {decision.pedestrian_count} pedestrians / "
        f"target~{decision.route_length_hint_m}m / actual~{decision.actual_route_length_m:.1f}m / "
        f"junction_focus={decision.junction_focus} ({decision.actual_junction_ratio:.3f}) / "
        f"turn_count={decision.turn_count}"
    )
    print(
        "Spawn selection: "
        f"spawn_index={decision.spawn_index}, destination_index={decision.destination_index}, "
        f"spawn_count={decision.spawn_count}"
    )
    print(f"Adaptation: {decision.adaptation_mode} / {decision.adaptation_summary}")
    print(f"Scenario JSON: {decision.scenario_path}")
    print(f"Scenario manifest: {decision.manifest_path}")


def main() -> None:
    args = parse_args()
    try:
        decision = generate_practical_scenario(args)
    except Exception as error:
        print("Failed to generate the Practical Stage scenario baseline.")
        print(f"Reason: {error}")
        raise SystemExit(1) from error
    _print_decision(decision)


if __name__ == "__main__":
    main()
