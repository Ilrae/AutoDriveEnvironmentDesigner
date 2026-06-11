"""Shared AED training-stage definitions for the application shell."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class TrainingStageOption:
    """One selectable AED progression stage in the control panel."""

    stage_id: str
    display_name: str
    short_label: str
    description: str
    implementation_status: str


TRAINING_STAGE_OPTIONS: tuple[TrainingStageOption, ...] = (
    TrainingStageOption(
        stage_id="track",
        display_name="Track Driving Stage",
        short_label="Track",
        description=(
            "Current result-driven generator, manual track driving, finish-line evaluation, "
            "and next-map loop."
        ),
        implementation_status="available",
    ),
    TrainingStageOption(
        stage_id="intermediate",
        display_name="Intermediate Road Stage",
        short_label="Intermediate",
        description=(
            "Longer road-like layouts with lane-oriented evaluation and stronger road-departure penalties."
        ),
        implementation_status="available",
    ),
    TrainingStageOption(
        stage_id="practical",
        display_name="Practical Road Stage",
        short_label="Practical",
        description=(
            "Town-based scenario shell for route, traffic, weather, and later autonomous-driving validation."
        ),
        implementation_status="available_shell",
    ),
)


def resolve_training_stage(stage_id: str | None) -> TrainingStageOption:
    """Resolve one stage option, defaulting to track."""

    if stage_id is None:
        return TRAINING_STAGE_OPTIONS[0]
    normalized_stage_id = stage_id.strip().lower()
    for option in TRAINING_STAGE_OPTIONS:
        if option.stage_id == normalized_stage_id:
            return option
    return TRAINING_STAGE_OPTIONS[0]


def training_stage_choices() -> tuple[str, ...]:
    """Return valid CLI/UI stage ids."""

    return tuple(option.stage_id for option in TRAINING_STAGE_OPTIONS)
