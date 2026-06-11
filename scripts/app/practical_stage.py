"""Shared Town-based Practical Stage presets for the AED application shell."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class PracticalTownOption:
    """One built-in CARLA Town available to the Practical Stage."""

    town_id: str
    display_name: str
    description: str


@dataclass(frozen=True)
class PracticalWeatherPreset:
    """One Practical Stage weather preset backed by CARLA WeatherParameters."""

    preset_id: str
    display_name: str
    carla_attribute: str
    description: str


@dataclass(frozen=True)
class PracticalTrafficPreset:
    """One Practical Stage traffic-density preset."""

    preset_id: str
    display_name: str
    vehicle_count: int
    pedestrian_count: int
    description: str


@dataclass(frozen=True)
class PracticalRoutePreset:
    """One Practical Stage route-complexity preset."""

    preset_id: str
    display_name: str
    route_length_hint_m: int
    junction_focus: str
    description: str


PRACTICAL_JUNCTION_FOCUS_CHOICES: tuple[str, ...] = ("low", "medium", "high")


PRACTICAL_TOWN_OPTIONS: tuple[PracticalTownOption, ...] = (
    PracticalTownOption("Town01", "Town01", "Compact urban grid with repeated junction exposure."),
    PracticalTownOption("Town02", "Town02", "Small residential layout with simpler route choices."),
    PracticalTownOption("Town03", "Town03", "Downtown-style grid with frequent intersections."),
    PracticalTownOption("Town04", "Town04", "Highway-leaning map with larger sweeping roads."),
    PracticalTownOption("Town05", "Town05", "Mixed urban and suburban road network."),
    PracticalTownOption("Town10HD", "Town10HD", "Dense city center baseline for practical validation."),
)

PRACTICAL_WEATHER_PRESETS: tuple[PracticalWeatherPreset, ...] = (
    PracticalWeatherPreset("clear_noon", "Clear Noon", "ClearNoon", "Bright daytime baseline for route validation."),
    PracticalWeatherPreset("cloudy_noon", "Cloudy Noon", "CloudyNoon", "Neutral daylight with reduced contrast."),
    PracticalWeatherPreset("wet_noon", "Wet Noon", "WetNoon", "Wet road baseline without heavy rain."),
    PracticalWeatherPreset("mid_rainy_noon", "Mid Rainy Noon", "MidRainyNoon", "Moderate rain for practical stress checks."),
    PracticalWeatherPreset("clear_sunset", "Clear Sunset", "ClearSunset", "Warmer low-angle lighting with longer shadows."),
    PracticalWeatherPreset("wet_sunset", "Wet Sunset", "WetSunset", "Reduced visibility baseline for later-stage validation."),
)

PRACTICAL_TRAFFIC_PRESETS: tuple[PracticalTrafficPreset, ...] = (
    PracticalTrafficPreset("light", "Light", 18, 0, "Sparse vehicle traffic, no pedestrians."),
    PracticalTrafficPreset("moderate", "Moderate", 42, 10, "Balanced vehicle flow with some pedestrian activity."),
    PracticalTrafficPreset("dense", "Dense", 70, 22, "Crowded route baseline with meaningful interaction density."),
)

PRACTICAL_ROUTE_PRESETS: tuple[PracticalRoutePreset, ...] = (
    PracticalRoutePreset("urban_short", "Urban Short", 700, "low", "Short baseline route with limited junction exposure."),
    PracticalRoutePreset("urban_loop", "Urban Loop", 1200, "medium", "Balanced route for repeated practical validation."),
    PracticalRoutePreset("arterial_long", "Arterial Long", 1800, "medium", "Longer practical route with steadier flow."),
    PracticalRoutePreset("junction_heavy", "Junction Heavy", 1400, "high", "Route biased toward repeated intersection handling."),
)


def _resolve_option_by_key(options: tuple[Any, ...], value: str | None, attribute_name: str) -> Any:
    if value is None:
        return options[0]
    normalized_value = value.strip().lower()
    for option in options:
        if str(getattr(option, attribute_name)).strip().lower() == normalized_value:
            return option
    return options[0]


def resolve_practical_town(town_id: str | None) -> PracticalTownOption:
    return _resolve_option_by_key(PRACTICAL_TOWN_OPTIONS, town_id, "town_id")


def resolve_practical_weather(preset_id: str | None) -> PracticalWeatherPreset:
    return _resolve_option_by_key(PRACTICAL_WEATHER_PRESETS, preset_id, "preset_id")


def resolve_practical_traffic(preset_id: str | None) -> PracticalTrafficPreset:
    return _resolve_option_by_key(PRACTICAL_TRAFFIC_PRESETS, preset_id, "preset_id")


def resolve_practical_route(preset_id: str | None) -> PracticalRoutePreset:
    return _resolve_option_by_key(PRACTICAL_ROUTE_PRESETS, preset_id, "preset_id")


def practical_town_choices() -> tuple[str, ...]:
    return tuple(option.town_id for option in PRACTICAL_TOWN_OPTIONS)


def practical_weather_choices() -> tuple[str, ...]:
    return tuple(option.preset_id for option in PRACTICAL_WEATHER_PRESETS)


def practical_traffic_choices() -> tuple[str, ...]:
    return tuple(option.preset_id for option in PRACTICAL_TRAFFIC_PRESETS)


def practical_route_choices() -> tuple[str, ...]:
    return tuple(option.preset_id for option in PRACTICAL_ROUTE_PRESETS)


def practical_junction_focus_choices() -> tuple[str, ...]:
    return PRACTICAL_JUNCTION_FOCUS_CHOICES


def build_practical_stage_parameters(
    *,
    town_id: str,
    weather_preset: str,
    traffic_preset: str,
    route_preset: str,
    custom_settings_enabled: bool = False,
    custom_vehicle_count: int | None = None,
    custom_pedestrian_count: int | None = None,
    custom_route_length_hint_m: int | None = None,
    custom_junction_focus: str | None = None,
    custom_note: str | None = None,
) -> dict[str, Any]:
    """Resolve one Practical Stage shell config dictionary for session summaries."""

    town_option = resolve_practical_town(town_id)
    weather_option = resolve_practical_weather(weather_preset)
    traffic_option = resolve_practical_traffic(traffic_preset)
    route_option = resolve_practical_route(route_preset)
    preset_vehicle_count = traffic_option.vehicle_count
    preset_pedestrian_count = traffic_option.pedestrian_count
    preset_route_length_hint_m = route_option.route_length_hint_m
    preset_junction_focus = route_option.junction_focus
    effective_vehicle_count = preset_vehicle_count
    effective_pedestrian_count = preset_pedestrian_count
    effective_route_length_hint_m = preset_route_length_hint_m
    effective_junction_focus = preset_junction_focus
    normalized_custom_note = (custom_note or "").strip()
    override_fields: list[str] = []

    if custom_settings_enabled:
        if custom_vehicle_count is not None:
            effective_vehicle_count = max(0, int(custom_vehicle_count))
            override_fields.append("vehicles")
        if custom_pedestrian_count is not None:
            effective_pedestrian_count = max(0, int(custom_pedestrian_count))
            override_fields.append("pedestrians")
        if custom_route_length_hint_m is not None:
            effective_route_length_hint_m = max(100, int(custom_route_length_hint_m))
            override_fields.append("route_length")
        if custom_junction_focus and custom_junction_focus in PRACTICAL_JUNCTION_FOCUS_CHOICES:
            effective_junction_focus = custom_junction_focus
            override_fields.append("junction_focus")

    traffic_display = (
        "Custom Override" if custom_settings_enabled and override_fields else traffic_option.display_name
    )
    route_display = (
        "Custom Route" if custom_settings_enabled and ("route_length" in override_fields or "junction_focus" in override_fields) else route_option.display_name
    )
    custom_summary = (
        "Auto practical adaptation is active."
        if not custom_settings_enabled
        else (
            (
                "Custom practical overrides are enabled, but no field is pinned yet. "
                "Any empty field will stay under automatic adaptation."
            )
            if not override_fields and not normalized_custom_note
            else (
                "Pinned overrides: "
                + ", ".join(
                    [
                        *([f"{effective_vehicle_count} vehicles"] if "vehicles" in override_fields else []),
                        *([f"{effective_pedestrian_count} pedestrians"] if "pedestrians" in override_fields else []),
                        *([f"~{effective_route_length_hint_m}m"] if "route_length" in override_fields else []),
                        *([f"junction_focus={effective_junction_focus}"] if "junction_focus" in override_fields else []),
                        *([f"note={normalized_custom_note}"] if normalized_custom_note else []),
                    ]
                )
                + ". Remaining fields stay under automatic adaptation."
            )
        )
    )
    return {
        "town_id": town_option.town_id,
        "town_display": town_option.display_name,
        "weather_preset": weather_option.preset_id,
        "weather_display": weather_option.display_name,
        "weather_carla_attribute": weather_option.carla_attribute,
        "traffic_preset": traffic_option.preset_id,
        "traffic_display": traffic_display,
        "preset_traffic_vehicle_count": preset_vehicle_count,
        "traffic_vehicle_count": effective_vehicle_count,
        "preset_pedestrian_count": preset_pedestrian_count,
        "pedestrian_count": effective_pedestrian_count,
        "route_preset": route_option.preset_id,
        "route_display": route_display,
        "preset_route_length_hint_m": preset_route_length_hint_m,
        "route_length_hint_m": effective_route_length_hint_m,
        "preset_junction_focus": preset_junction_focus,
        "junction_focus": effective_junction_focus,
        "custom_settings_enabled": custom_settings_enabled,
        "custom_vehicle_count": custom_vehicle_count,
        "custom_pedestrian_count": custom_pedestrian_count,
        "custom_route_length_hint_m": custom_route_length_hint_m,
        "custom_junction_focus": custom_junction_focus,
        "custom_note": normalized_custom_note,
        "custom_override_fields": tuple(override_fields),
        "custom_summary": custom_summary,
        "scenario_mode": "custom" if custom_settings_enabled and override_fields else "auto",
    }
