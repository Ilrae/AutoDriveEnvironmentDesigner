"""Shared helpers for spawning and monitoring vehicles in CARLA."""

from __future__ import annotations

import math
import random
import time
from typing import Any


def select_vehicle_blueprint(world: Any, blueprint_filter: str) -> Any:
    """Select one vehicle blueprint matching the requested filter."""

    blueprints = world.get_blueprint_library().filter(blueprint_filter)
    if not blueprints:
        raise RuntimeError(
            f"No vehicle blueprints matched filter '{blueprint_filter}'."
        )
    return random.choice(blueprints)


def select_spawn_point(world: Any, spawn_index: int | None) -> Any:
    """Select a spawn point from the current map."""

    spawn_points = world.get_map().get_spawn_points()
    if not spawn_points:
        raise RuntimeError(
            "The current map has no spawn points. Use a CARLA town map or choose a valid transform manually."
        )

    if spawn_index is None:
        return random.choice(spawn_points)

    if spawn_index < 0 or spawn_index >= len(spawn_points):
        raise RuntimeError(
            f"spawn_index must be between 0 and {len(spawn_points) - 1}, got {spawn_index}."
        )

    return spawn_points[spawn_index]


def enable_autopilot(vehicle: Any, traffic_manager_port: int) -> None:
    """Enable autopilot while supporting multiple CARLA signatures."""

    try:
        vehicle.set_autopilot(True, traffic_manager_port)
    except TypeError:
        vehicle.set_autopilot(True)


def _location_distance(first: Any, second: Any) -> float:
    return math.sqrt(
        (float(first.x) - float(second.x)) ** 2
        + (float(first.y) - float(second.y)) ** 2
        + (float(first.z) - float(second.z)) ** 2
    )


def _is_supported_traffic_blueprint(blueprint: Any) -> bool:
    if blueprint.has_attribute("number_of_wheels"):
        try:
            if int(blueprint.get_attribute("number_of_wheels")) != 4:
                return False
        except (TypeError, ValueError):
            return False

    excluded_keywords = ("microlino", "carlacola", "firetruck", "ambulance", "sprinter", "bike", "bicycle", "motor")
    blueprint_id = str(getattr(blueprint, "id", "")).lower()
    return not any(keyword in blueprint_id for keyword in excluded_keywords)


def spawn_autopilot_traffic(
    world: Any,
    client: Any,
    *,
    desired_count: int,
    traffic_manager_port: int,
    blueprint_filter: str = "vehicle.*",
    random_seed: int = 7,
    excluded_locations: list[Any] | None = None,
    min_spawn_distance_m: float = 14.0,
) -> tuple[list[Any], dict[str, int]]:
    """Spawn background traffic vehicles and hand them to CARLA Traffic Manager."""

    spawn_points = list(world.get_map().get_spawn_points())
    summary = {
        "requested_count": max(0, int(desired_count)),
        "spawned_count": 0,
        "available_spawn_points": len(spawn_points),
        "attempted_spawn_points": 0,
    }
    if desired_count <= 0 or not spawn_points:
        return [], summary

    traffic_manager = client.get_trafficmanager(traffic_manager_port)
    try:
        traffic_manager.set_random_device_seed(int(random_seed))
    except Exception:
        pass
    try:
        traffic_manager.set_global_distance_to_leading_vehicle(2.5)
    except Exception:
        pass
    try:
        traffic_manager.global_percentage_speed_difference(8.0)
    except Exception:
        pass
    try:
        traffic_manager.set_hybrid_physics_mode(True)
    except Exception:
        pass

    blueprints = [
        blueprint
        for blueprint in world.get_blueprint_library().filter(blueprint_filter)
        if _is_supported_traffic_blueprint(blueprint)
    ]
    if not blueprints:
        raise RuntimeError(f"No traffic vehicle blueprints matched filter '{blueprint_filter}'.")

    rng = random.Random(int(random_seed))
    indexed_spawn_points = list(enumerate(spawn_points))
    rng.shuffle(indexed_spawn_points)
    excluded_locations = excluded_locations or []

    traffic_vehicles: list[Any] = []
    for _, spawn_transform in indexed_spawn_points:
        if len(traffic_vehicles) >= desired_count:
            break
        if excluded_locations and any(
            _location_distance(spawn_transform.location, location) < float(min_spawn_distance_m)
            for location in excluded_locations
        ):
            continue

        blueprint = rng.choice(blueprints)
        if blueprint.has_attribute("color"):
            recommended_values = list(blueprint.get_attribute("color").recommended_values)
            if recommended_values:
                blueprint.set_attribute("color", rng.choice(recommended_values))
        if blueprint.has_attribute("driver_id"):
            recommended_values = list(blueprint.get_attribute("driver_id").recommended_values)
            if recommended_values:
                blueprint.set_attribute("driver_id", rng.choice(recommended_values))
        if blueprint.has_attribute("role_name"):
            blueprint.set_attribute("role_name", "autopilot")

        summary["attempted_spawn_points"] += 1
        vehicle = world.try_spawn_actor(blueprint, spawn_transform)
        if vehicle is None:
            continue
        enable_autopilot(vehicle, traffic_manager_port)
        traffic_vehicles.append(vehicle)

    summary["spawned_count"] = len(traffic_vehicles)
    return traffic_vehicles, summary


def spawn_pedestrian_traffic(
    world: Any,
    *,
    desired_count: int,
    random_seed: int = 7,
    excluded_locations: list[Any] | None = None,
    min_spawn_distance_m: float = 12.0,
) -> tuple[list[Any], list[Any], dict[str, int]]:
    """Spawn simple walker traffic and start AI controllers for Practical baseline runs."""

    summary = {
        "requested_count": max(0, int(desired_count)),
        "spawned_count": 0,
        "controller_count": 0,
        "attempted_spawn_locations": 0,
    }
    if desired_count <= 0:
        return [], [], summary

    rng = random.Random(int(random_seed))
    blueprint_library = world.get_blueprint_library()
    walker_blueprints = list(blueprint_library.filter("walker.pedestrian.*"))
    if not walker_blueprints:
        return [], [], summary
    controller_blueprint = blueprint_library.find("controller.ai.walker")
    excluded_locations = excluded_locations or []
    reference_transform = world.get_spectator().get_transform()
    transform_type = type(reference_transform)
    location_type = type(reference_transform.location)
    rotation_type = type(reference_transform.rotation)

    spawn_locations: list[Any] = []
    attempt_budget = max(40, desired_count * 20)
    for _ in range(attempt_budget):
        if len(spawn_locations) >= desired_count:
            break
        nav_location = world.get_random_location_from_navigation()
        if nav_location is None:
            continue
        if excluded_locations and any(
            _location_distance(nav_location, location) < float(min_spawn_distance_m)
            for location in excluded_locations
        ):
            continue
        spawn_locations.append(nav_location)

    walkers: list[Any] = []
    controllers: list[Any] = []
    for nav_location in spawn_locations:
        blueprint = rng.choice(walker_blueprints)
        if blueprint.has_attribute("is_invincible"):
            blueprint.set_attribute("is_invincible", "false")
        if blueprint.has_attribute("speed"):
            recommended_values = list(blueprint.get_attribute("speed").recommended_values)
            if len(recommended_values) >= 2:
                blueprint.set_attribute("speed", recommended_values[1])
        summary["attempted_spawn_locations"] += 1
        spawn_transform = transform_type(
            location_type(
                x=float(nav_location.x),
                y=float(nav_location.y),
                z=float(nav_location.z) + 0.2,
            ),
            rotation_type(),
        )
        walker_actor = world.try_spawn_actor(blueprint, spawn_transform)
        if walker_actor is None:
            continue
        controller_actor = world.try_spawn_actor(controller_blueprint, transform_type(), attach_to=walker_actor)
        if controller_actor is None:
            try:
                walker_actor.destroy()
            except Exception:
                pass
            continue
        walkers.append(walker_actor)
        controllers.append(controller_actor)

    try:
        world.wait_for_tick(1.0)
    except Exception:
        time.sleep(0.2)

    for controller_actor in controllers:
        try:
            controller_actor.start()
            target_location = world.get_random_location_from_navigation()
            if target_location is not None:
                controller_actor.go_to_location(target_location)
            controller_actor.set_max_speed(rng.uniform(1.0, 1.6))
        except Exception:
            pass

    summary["spawned_count"] = len(walkers)
    summary["controller_count"] = len(controllers)
    return walkers, controllers, summary


def attach_collision_sensor(
    world: Any,
    vehicle: Any,
    cooldown_seconds: float = 0.5,
) -> tuple[Any, dict[str, float]]:
    """Attach a collision sensor and track debounced collision events."""

    collision_state = {"count": 0, "last_timestamp": -1.0}
    blueprint = world.get_blueprint_library().find("sensor.other.collision")
    sensor_transform = type(vehicle.get_transform())()
    sensor = world.spawn_actor(blueprint, sensor_transform, attach_to=vehicle)

    def _handle_collision(event: Any) -> None:
        event_timestamp = float(getattr(event, "timestamp", 0.0))
        last_timestamp = float(collision_state["last_timestamp"])
        if last_timestamp < 0 or event_timestamp - last_timestamp >= cooldown_seconds:
            collision_state["count"] += 1
            collision_state["last_timestamp"] = event_timestamp

    sensor.listen(_handle_collision)
    return sensor, collision_state


def destroy_actor(actor: Any) -> None:
    """Destroy a CARLA actor without raising if cleanup fails."""

    if actor is None:
        return

    try:
        actor.destroy()
    except Exception:
        pass
