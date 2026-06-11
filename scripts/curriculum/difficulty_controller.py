"""Minimal curriculum logic for adaptive road difficulty."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class DifficultyUpdateConfig:
    """Thresholds and ranges for a simple curriculum controller."""

    min_level: float = 0.0
    max_level: float = 1.0
    increase_threshold: float = 0.8
    decrease_threshold: float = 0.5
    step: float = 0.08
    max_step: float = 0.24

    def validate(self) -> None:
        """Validate controller settings."""

        if self.min_level > self.max_level:
            raise ValueError("min_level must be less than or equal to max_level")
        if self.step <= 0:
            raise ValueError("step must be greater than 0")
        if self.max_step < self.step:
            raise ValueError("max_step must be greater than or equal to step")
        if not 0.0 <= self.decrease_threshold <= 1.0:
            raise ValueError("decrease_threshold must be between 0.0 and 1.0")
        if not 0.0 <= self.increase_threshold <= 1.0:
            raise ValueError("increase_threshold must be between 0.0 and 1.0")
        if self.decrease_threshold > self.increase_threshold:
            raise ValueError(
                "decrease_threshold must be less than or equal to increase_threshold"
            )


@dataclass
class RoadDifficultyProfile:
    """A simple level-to-road-parameter mapping for future generators."""

    level: float
    road_length: float
    lane_width: float
    curvature_hint: float


def clamp_level(level: float, config: DifficultyUpdateConfig | None = None) -> float:
    """Clamp a difficulty level into the configured range."""

    active_config = config or DifficultyUpdateConfig()
    active_config.validate()
    return max(active_config.min_level, min(active_config.max_level, level))


def update_difficulty(
    current_level: float,
    success_rate: float,
    config: DifficultyUpdateConfig | None = None,
) -> float:
    """Update the difficulty level from a recent success rate."""

    active_config = config or DifficultyUpdateConfig()
    active_config.validate()

    if not 0.0 <= success_rate <= 1.0:
        raise ValueError("success_rate must be between 0.0 and 1.0")

    if success_rate > active_config.increase_threshold:
        increase_denominator = max(1e-9, 1.0 - active_config.increase_threshold)
        increase_ratio = (
            (success_rate - active_config.increase_threshold)
            / increase_denominator
        )
        adaptive_step = active_config.step + (
            (active_config.max_step - active_config.step) * increase_ratio
        )
        next_level = current_level + adaptive_step
    elif success_rate < active_config.decrease_threshold:
        decrease_denominator = max(1e-9, active_config.decrease_threshold)
        decrease_ratio = (
            (active_config.decrease_threshold - success_rate)
            / decrease_denominator
        )
        adaptive_step = active_config.step + (
            (active_config.max_step - active_config.step) * decrease_ratio
        )
        next_level = current_level - adaptive_step
    else:
        next_level = current_level

    return clamp_level(next_level, active_config)


def build_profile_from_level(level: float) -> RoadDifficultyProfile:
    """Map a difficulty value to basic road-generation parameters."""

    normalized_level = clamp_level(level)
    road_length = 140.0 + (220.0 * normalized_level)
    lane_width = 4.0 - (1.0 * normalized_level)
    curvature_hint = 0.02 + (0.18 * normalized_level)

    return RoadDifficultyProfile(
        level=normalized_level,
        road_length=road_length,
        lane_width=lane_width,
        curvature_hint=curvature_hint,
    )
