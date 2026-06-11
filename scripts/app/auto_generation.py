"""Result-driven automatic map generation for the AED application."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.carla_runner.carla_utils import create_client
from scripts.carla_runner.load_xodr_in_carla import (
    create_generation_parameters,
    load_opendrive_world,
)
from scripts.curriculum.difficulty_controller import (
    DifficultyUpdateConfig,
    clamp_level,
    update_difficulty,
)
from scripts.evaluation.scoring import compute_driving_score as compute_episode_driving_score
from scripts.evaluation.result_models import EpisodeResult, load_episode_result
from scripts.map_generator.course_composer import build_open_course_composition
from scripts.map_generator.course_stages import (
    course_variant_order,
    resolve_course_stage,
    resolve_course_stage_index,
    resolve_stage_for_variant,
    stage_variant_indices,
    variant_index_for_level,
)
from scripts.map_generator.course_validation import validate_open_course_composition
from scripts.map_generator.level_generator import generate_map_from_level


@dataclass(frozen=True)
class AutoGenerationDecision:
    """One automatic next-map generation decision."""

    source_result_path: Path
    source_map_id: str
    driving_score: float
    current_level: float
    current_level_source: str
    next_level: float
    difficulty_delta: float
    difficulty_stage_index: int
    difficulty_stage_id: str
    layout_stage_index: int
    layout_stage_id: str
    course_variant: str
    curve_direction: str
    next_map_id: str
    generated_xodr_path: Path
    generated_manifest_path: Path
    loaded_map_name: str | None = None
    training_stage: str = "track"
    bootstrap_mode: bool = False


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate the next OpenDRIVE map automatically from the latest or a selected "
            "evaluation result."
        ),
    )
    parser.add_argument(
        "--result-path",
        type=Path,
        default=None,
        help="Optional evaluation JSON file. If omitted, the latest file in --result-dir is used.",
    )
    parser.add_argument(
        "--result-dir",
        type=Path,
        default=Path("results/manual_sequence"),
        help="Directory scanned when --result-path is omitted.",
    )
    parser.add_argument(
        "--generated-dir",
        type=Path,
        default=Path("maps/generated"),
        help="Directory where generated .xodr files are written.",
    )
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        default=Path("experiments"),
        help="Directory where generation manifests are written.",
    )
    parser.add_argument(
        "--map-prefix",
        default="aed_auto_generated",
        help="Prefix used for the next automatically generated map id.",
    )
    parser.add_argument(
        "--default-level",
        type=float,
        default=0.30,
        help="Fallback difficulty level when the previous result cannot be mapped back to a known level.",
    )
    parser.add_argument(
        "--load-after-generate",
        action="store_true",
        help="Immediately load the generated .xodr into CARLA after generation.",
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
        help="Optional CARLA root, PythonAPI, dist directory, or .egg file.",
    )
    parser.add_argument(
        "--vertex-distance",
        type=float,
        default=2.0,
        help="Mesh vertex distance in meters when --load-after-generate is used.",
    )
    parser.add_argument(
        "--max-road-length",
        type=float,
        default=50.0,
        help="Maximum road mesh chunk length in meters when loading.",
    )
    parser.add_argument(
        "--wall-height",
        type=float,
        default=1.0,
        help="Boundary wall height in meters when loading.",
    )
    parser.add_argument(
        "--additional-width",
        type=float,
        default=0.6,
        help="Extra junction lane width in meters when loading.",
    )
    parser.add_argument(
        "--no-smooth-junctions",
        action="store_true",
        help="Disable CARLA junction smoothing during load.",
    )
    parser.add_argument(
        "--no-mesh-visibility",
        action="store_true",
        help="Generate the world without visible road mesh.",
    )
    parser.add_argument(
        "--keep-settings",
        action="store_true",
        help="Keep world settings instead of resetting them during load.",
    )
    parser.add_argument(
        "--training-stage",
        default="track",
        choices=("track", "intermediate", "practical"),
        help="Active AED progression stage used to pick the generation profile.",
    )
    return parser.parse_args()


def _find_latest_result(result_dir: Path) -> Path:
    candidates = sorted(
        result_dir.glob("*.json"),
        key=lambda candidate: candidate.stat().st_mtime,
        reverse=True,
    )
    if not candidates:
        raise FileNotFoundError(
            f"No evaluation result JSON files were found in '{result_dir}'."
        )
    return candidates[0]


def _resolve_result_path(
    result_path: Path | None,
    result_dir: Path,
) -> Path:
    if result_path is not None:
        resolved = result_path.resolve()
        if not resolved.exists():
            raise FileNotFoundError(f"The requested result file does not exist: {resolved}")
        return resolved
    return _find_latest_result(result_dir.resolve())


def _resolve_current_level(
    result: EpisodeResult,
    manifest_dir: Path,
    default_level: float,
) -> tuple[float, str]:
    metadata = result.metadata or {}
    for metadata_key in ("generation_level", "generation_level_hint", "level"):
        candidate = metadata.get(metadata_key)
        if candidate is not None:
            return clamp_level(float(candidate)), f"result.metadata.{metadata_key}"

    manifest_path = manifest_dir / f"{result.map_id}.json"
    if manifest_path.exists():
        payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        candidate = payload.get("level")
        if candidate is not None:
            return clamp_level(float(candidate)), f"manifest:{manifest_path.name}"

    return clamp_level(default_level), "default"


def compute_driving_score(result: EpisodeResult) -> float:
    """Convert one episode result into a 0.0-1.0 driving score."""

    return compute_episode_driving_score(
        completion_ratio=result.completion_ratio,
        path_tracking_score=result.path_tracking_score,
        crossed_finish_line=result.crossed_finish_line,
        offroad_ratio=result.offroad_ratio,
        collision_count=result.collision_count,
        failure_reason=result.failure_reason,
        success=result.success,
        lane_discipline_score=result.lane_discipline_score,
        lane_departure_ratio=result.lane_departure_ratio,
        opposite_lane_ratio=result.opposite_lane_ratio,
    )


def preview_track_adjustment(
    *,
    result: EpisodeResult,
    current_level: float,
) -> dict[str, Any]:
    """Summarize how the next generated track would adapt from one result."""

    normalized_current_level = clamp_level(float(current_level))
    driving_score = compute_driving_score(result)
    next_level = update_difficulty(
        current_level=normalized_current_level,
        success_rate=driving_score,
        config=DifficultyUpdateConfig(),
    )
    difficulty_delta = next_level - normalized_current_level
    current_stage = resolve_course_stage(normalized_current_level)
    next_stage = resolve_course_stage(next_level)

    if result.collision_count > 0:
        primary_reason = "collision_recovery"
        summary = "Collision occurred, so the next track should ease back and stay more forgiving."
    elif result.failure_reason in {"course_departure", "wrong_lane"} or result.offroad_ratio > 0.02:
        primary_reason = "stability_recovery"
        summary = "Road-exit or lane-instability signals push the next track toward a simpler, steadier layout."
    elif result.failure_reason == "not_finished" and result.completion_ratio < 0.45:
        primary_reason = "completion_recovery"
        summary = "Low completion keeps the next generated course shorter and easier to recover on."
    elif result.success and driving_score >= 0.95 and difficulty_delta >= 0.10:
        primary_reason = "difficulty_up"
        summary = "A very strong finish lets the next generated track step up aggressively."
    elif result.success and driving_score >= 0.88 and difficulty_delta > 0.0:
        primary_reason = "gentle_up"
        summary = "A stable finish raises difficulty gradually with denser curve structure."
    elif difficulty_delta > 0.0:
        primary_reason = "up"
        summary = "The run was solid enough to nudge the next track upward."
    elif difficulty_delta < 0.0:
        primary_reason = "down"
        summary = "The run struggled enough that the next track should ease off slightly."
    else:
        primary_reason = "hold"
        summary = "The run keeps the next generated track in roughly the same difficulty band."

    if difficulty_delta >= 0.10:
        next_bias = "Expect more curves and shorter recovery straights."
    elif difficulty_delta > 0.0:
        next_bias = "Expect a modest increase in curve density."
    elif difficulty_delta <= -0.10:
        next_bias = "Expect a noticeably easier curve family with more recovery space."
    elif difficulty_delta < 0.0:
        next_bias = "Expect a slightly more forgiving layout."
    else:
        next_bias = "Expect a similar overall layout family."

    return {
        "driving_score": driving_score,
        "current_level": normalized_current_level,
        "next_level": next_level,
        "difficulty_delta": difficulty_delta,
        "current_stage_id": current_stage.stage_id,
        "next_stage_id": next_stage.stage_id,
        "primary_reason": primary_reason,
        "summary": summary,
        "next_bias": next_bias,
    }


def _course_variant_order() -> list[str]:
    return course_variant_order()


def _shift_course_variant(variant: str, step: int) -> str:
    ordered_variants = _course_variant_order()
    if variant not in ordered_variants:
        return ordered_variants[max(0, min(len(ordered_variants) - 1, step))]
    current_index = ordered_variants.index(variant)
    next_index = max(0, min(len(ordered_variants) - 1, current_index + step))
    return ordered_variants[next_index]


def _variant_index_for_level(level: float) -> int:
    return variant_index_for_level(level)


def _course_stage_for_level(level: float) -> int:
    return resolve_course_stage_index(level)


def _stage_variant_indices(stage: int) -> list[int]:
    return stage_variant_indices(stage)


def _resolve_source_course_variant(result: EpisodeResult) -> str | None:
    metadata = result.metadata or {}
    auto_generation = metadata.get("auto_generation")
    if isinstance(auto_generation, dict):
        candidate = auto_generation.get("course_variant")
        if isinstance(candidate, str) and candidate in _course_variant_order():
            return candidate

    shape_type = metadata.get("shape_type")
    if isinstance(shape_type, str):
        lowered_shape_type = shape_type.lower()
        for variant in _course_variant_order():
            if variant in lowered_shape_type:
                return variant

    lowered_map_id = result.map_id.lower()
    for variant in _course_variant_order():
        if variant in lowered_map_id:
            return variant
    return None


def _stable_variant_seed(seed_key: str) -> int:
    numeric_match = re.search(r"(\d+)$", seed_key)
    if numeric_match is not None:
        return int(numeric_match.group(1))
    return sum((index + 1) * ord(character) for index, character in enumerate(seed_key))


def _load_recent_auto_generation_history(
    manifest_dir: Path,
    map_prefix: str,
    *,
    limit: int = 6,
) -> list[dict[str, Any]]:
    pattern = re.compile(rf"^{re.escape(map_prefix)}_(\d+)$")
    recent_candidates: list[tuple[int, Path]] = []
    for manifest_path in manifest_dir.glob(f"{map_prefix}_*.json"):
        match = pattern.match(manifest_path.stem)
        if match is None:
            continue
        recent_candidates.append((int(match.group(1)), manifest_path))

    history: list[dict[str, Any]] = []
    for _, manifest_path in sorted(recent_candidates, key=lambda item: item[0], reverse=True)[:limit]:
        try:
            payload = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        auto_generation = payload.get("auto_generation")
        composer_metadata = payload.get("open_course_composer")
        validation_metadata = payload.get("open_course_validation")
        history.append(
            {
                "map_id": payload.get("map_id", manifest_path.stem),
                "course_variant": (
                    auto_generation.get("course_variant")
                    if isinstance(auto_generation, dict)
                    else None
                ),
                "curve_direction": (
                    auto_generation.get("curve_direction")
                    if isinstance(auto_generation, dict)
                    else None
                ),
                "layout_stage_id": (
                    auto_generation.get("layout_stage_id")
                    if isinstance(auto_generation, dict)
                    else None
                ),
                "difficulty_stage_id": (
                    auto_generation.get("difficulty_stage_id")
                    if isinstance(auto_generation, dict)
                    else None
                ),
                "actual_total_length_m": (
                    composer_metadata.get("actual_total_length_m")
                    if isinstance(composer_metadata, dict)
                    else None
                ),
                "actual_curve_count": (
                    composer_metadata.get("actual_curve_count")
                    if isinstance(composer_metadata, dict)
                    else None
                ),
                "direction_reversal_count": (
                    composer_metadata.get("direction_reversal_count")
                    if isinstance(composer_metadata, dict)
                    else None
                ),
                "validation_passed": (
                    validation_metadata.get("validation_passed")
                    if isinstance(validation_metadata, dict)
                    else None
                ),
                "layout_signature": (
                    validation_metadata.get("layout_signature")
                    if isinstance(validation_metadata, dict)
                    else None
                ),
                "length_bucket_20m": (
                    validation_metadata.get("length_bucket_20m")
                    if isinstance(validation_metadata, dict)
                    else None
                ),
            }
        )
    return history


def _preview_candidate_layout_metadata(
    *,
    next_level: float,
    curve_direction: str,
    variant: str,
    seed_key: str,
) -> dict[str, Any]:
    composition = build_open_course_composition(
        next_level,
        curve_direction,
        requested_variant=variant,
        layout_seed_key=seed_key,
    )
    validation = validate_open_course_composition(composition)
    return {
        "actual_total_length_m": composition.actual_total_length_m,
        "actual_curve_count": composition.actual_curve_count,
        "direction_reversal_count": composition.direction_reversal_count,
        "validation_passed": validation["validation_passed"],
        "layout_signature": validation["layout_signature"],
        "length_bucket_20m": validation["length_bucket_20m"],
    }


def _score_variant_candidate(
    ordered_variants: list[str],
    *,
    candidate_index: int,
    fallback_index: int,
    source_variant: str | None,
    target_stage: int,
    recent_history: list[dict[str, Any]],
    preview_metadata: dict[str, Any],
) -> float:
    variant = ordered_variants[candidate_index]
    candidate_stage = resolve_stage_for_variant(variant)
    score = abs(candidate_index - fallback_index) * 0.35

    if source_variant in ordered_variants and candidate_index == ordered_variants.index(source_variant):
        score += 2.25

    if candidate_stage is not None:
        if candidate_stage.index == target_stage:
            score -= 0.75
        elif abs(candidate_stage.index - target_stage) == 1:
            score -= 0.20

    recent_variants = [
        str(entry.get("course_variant"))
        for entry in recent_history
        if isinstance(entry.get("course_variant"), str)
    ]
    for history_index, recent_variant in enumerate(recent_variants[:4]):
        if recent_variant == variant:
            score += 3.50 - (history_index * 0.60)

    recent_stage_ids = [
        str(entry.get("layout_stage_id"))
        for entry in recent_history
        if isinstance(entry.get("layout_stage_id"), str)
    ]
    if candidate_stage is not None and recent_stage_ids:
        if candidate_stage.stage_id == recent_stage_ids[0]:
            score += 0.90
        if len(recent_stage_ids) >= 3 and len(set(recent_stage_ids[:3])) == 1:
            if candidate_stage.stage_id == recent_stage_ids[0]:
                score += 1.80
            else:
                score -= 0.25

    if not bool(preview_metadata.get("validation_passed", True)):
        score += 6.00

    preview_signature = preview_metadata.get("layout_signature")
    if isinstance(preview_signature, str):
        recent_signatures = [
            str(entry.get("layout_signature"))
            for entry in recent_history
            if isinstance(entry.get("layout_signature"), str)
        ]
        for history_index, recent_signature in enumerate(recent_signatures[:4]):
            if recent_signature == preview_signature:
                score += 4.50 - (history_index * 0.75)

    preview_length_bucket = preview_metadata.get("length_bucket_20m")
    preview_curve_count = preview_metadata.get("actual_curve_count")
    preview_reversal_count = preview_metadata.get("direction_reversal_count")
    for history_entry in recent_history[:3]:
        if (
            history_entry.get("length_bucket_20m") == preview_length_bucket
            and history_entry.get("actual_curve_count") == preview_curve_count
            and history_entry.get("direction_reversal_count") == preview_reversal_count
        ):
            score += 1.40

    return score


def _choose_diverse_variant_index(
    ordered_variants: list[str],
    *,
    seed_key: str,
    source_variant: str | None,
    candidate_indices: list[int],
    fallback_index: int,
    target_stage: int,
    recent_history: list[dict[str, Any]],
    preview_by_index: dict[int, dict[str, Any]],
) -> int:
    if not candidate_indices:
        return fallback_index

    normalized_candidates = sorted(set(candidate_indices))
    seed = _stable_variant_seed(seed_key)
    scored_candidates = [
        (
            candidate_index,
            _score_variant_candidate(
                ordered_variants,
                candidate_index=candidate_index,
                fallback_index=fallback_index,
                source_variant=source_variant,
                target_stage=target_stage,
                recent_history=recent_history,
                preview_metadata=preview_by_index.get(candidate_index, {}),
            ),
        )
        for candidate_index in normalized_candidates
    ]
    best_score = min(score for _, score in scored_candidates)
    viable_candidates = [
        candidate_index
        for candidate_index, score in scored_candidates
        if score <= best_score + 0.75
    ]
    return viable_candidates[seed % len(viable_candidates)]


def _choose_course_variant(
    next_level: float,
    result: EpisodeResult,
    driving_score: float,
    difficulty_delta: float,
    curve_direction: str,
    next_map_id: str,
    recent_history: list[dict[str, Any]],
) -> str:
    ordered_variants = _course_variant_order()
    source_variant = _resolve_source_course_variant(result)
    target_stage = _course_stage_for_level(next_level)

    if result.collision_count > 0:
        target_stage -= 2
    elif result.failure_reason == "course_departure":
        target_stage -= 1
    elif result.failure_reason == "not_finished" and result.completion_ratio < 0.45:
        target_stage -= 1

    if result.success and driving_score >= 0.95 and difficulty_delta >= 0.10:
        target_stage += 1
    elif result.success and driving_score >= 0.88 and difficulty_delta > 0.0:
        target_stage += 1

    target_stage = max(0, min(4, target_stage))
    candidate_indices = list(_stage_variant_indices(target_stage))

    if result.success and driving_score >= 0.95 and target_stage < 4:
        candidate_indices.extend(_stage_variant_indices(target_stage + 1)[:2])
    elif result.failure_reason is not None and target_stage > 0:
        candidate_indices.extend(_stage_variant_indices(target_stage - 1)[-1:])

    recent_variants = [
        str(entry.get("course_variant"))
        for entry in recent_history
        if isinstance(entry.get("course_variant"), str)
    ]
    recent_stage_ids = [
        str(entry.get("layout_stage_id"))
        for entry in recent_history
        if isinstance(entry.get("layout_stage_id"), str)
    ]
    if len(recent_variants) >= 2 and len(set(recent_variants[:2])) == 1:
        if target_stage < 4:
            candidate_indices.extend(_stage_variant_indices(target_stage + 1))
        if target_stage > 0:
            candidate_indices.extend(_stage_variant_indices(target_stage - 1))
    elif len(recent_stage_ids) >= 3 and len(set(recent_stage_ids[:3])) == 1:
        if target_stage < 4:
            candidate_indices.extend(_stage_variant_indices(target_stage + 1)[:2])
        if target_stage > 0:
            candidate_indices.extend(_stage_variant_indices(target_stage - 1)[-2:])

    fallback_index = _variant_index_for_level(next_level)
    fallback_index = max(0, min(len(ordered_variants) - 1, fallback_index))
    preview_by_index = {
        candidate_index: _preview_candidate_layout_metadata(
            next_level=next_level,
            curve_direction=curve_direction,
            variant=ordered_variants[candidate_index],
            seed_key=next_map_id,
        )
        for candidate_index in sorted(set(candidate_indices + [fallback_index]))
    }

    chosen_index = _choose_diverse_variant_index(
        ordered_variants,
        seed_key=next_map_id,
        source_variant=source_variant,
        candidate_indices=candidate_indices,
        fallback_index=fallback_index,
        target_stage=target_stage,
        recent_history=recent_history,
        preview_by_index=preview_by_index,
    )
    return ordered_variants[chosen_index]


def _choose_curve_direction(
    source_map_id: str,
    next_map_id: str,
    recent_history: list[dict[str, Any]],
) -> str:
    recent_directions = [
        str(entry.get("curve_direction"))
        for entry in recent_history
        if isinstance(entry.get("curve_direction"), str)
    ]
    if len(recent_directions) >= 2 and len(set(recent_directions[:2])) == 1:
        return "right" if recent_directions[0] == "left" else "left"

    lowered_source = source_map_id.lower()
    if "left" in lowered_source:
        return "right"
    if "right" in lowered_source:
        return "left"

    numeric_seed = sum(ord(character) for character in next_map_id)
    return "left" if numeric_seed % 2 == 0 else "right"


def _build_next_map_id(map_prefix: str, generated_dir: Path) -> str:
    pattern = re.compile(rf"^{re.escape(map_prefix)}_(\d+)$")
    max_index = 0
    for candidate in generated_dir.glob(f"{map_prefix}_*.xodr"):
        match = pattern.match(candidate.stem)
        if match is None:
            continue
        max_index = max(max_index, int(match.group(1)))
    return f"{map_prefix}_{max_index + 1:03d}"


def _enrich_manifest(
    manifest_path: Path,
    *,
    decision: AutoGenerationDecision,
    result: EpisodeResult,
) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["auto_generation"] = {
        "source_result_path": str(decision.source_result_path),
        "source_map_id": decision.source_map_id,
        "driving_score": decision.driving_score,
        "current_level": decision.current_level,
        "current_level_source": decision.current_level_source,
        "next_level": decision.next_level,
        "difficulty_delta": decision.difficulty_delta,
        "difficulty_stage_index": decision.difficulty_stage_index,
        "difficulty_stage_id": decision.difficulty_stage_id,
        "layout_stage_index": decision.layout_stage_index,
        "layout_stage_id": decision.layout_stage_id,
        "course_variant": decision.course_variant,
        "curve_direction": decision.curve_direction,
        "training_stage": decision.training_stage,
        "source_success": result.success,
        "source_failure_reason": result.failure_reason,
        "source_completion_ratio": result.completion_ratio,
        "source_path_match_score": result.path_match_score,
        "source_path_tracking_score": result.path_tracking_score,
        "source_offroad_ratio": result.offroad_ratio,
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _enrich_manifest_bootstrap(
    manifest_path: Path,
    *,
    decision: AutoGenerationDecision,
) -> None:
    payload = json.loads(manifest_path.read_text(encoding="utf-8"))
    payload["auto_generation"] = {
        "bootstrap_mode": True,
        "source_result_path": None,
        "source_map_id": None,
        "driving_score": None,
        "current_level": decision.current_level,
        "current_level_source": decision.current_level_source,
        "next_level": decision.next_level,
        "difficulty_delta": decision.difficulty_delta,
        "difficulty_stage_index": decision.difficulty_stage_index,
        "difficulty_stage_id": decision.difficulty_stage_id,
        "layout_stage_index": decision.layout_stage_index,
        "layout_stage_id": decision.layout_stage_id,
        "course_variant": decision.course_variant,
        "curve_direction": decision.curve_direction,
        "training_stage": decision.training_stage,
        "bootstrap_summary": (
            "No prior evaluation result was available, so AED generated the first seed map "
            "from the default level."
        ),
    }
    manifest_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _load_generated_map(
    xodr_path: Path,
    args: argparse.Namespace,
) -> str:
    xodr_content = xodr_path.read_text(encoding="utf-8")
    carla, client, _ = create_client(
        host=args.host,
        port=args.port,
        timeout=args.timeout,
        pythonapi_path=args.pythonapi_path,
    )
    parameters = create_generation_parameters(carla, args)
    world = load_opendrive_world(client, xodr_content, parameters, args.keep_settings)
    return world.get_map().name


def _bootstrap_course_variant(training_stage: str) -> str:
    if training_stage == "intermediate":
        return "gentle_chicane"
    return "single_turn"


def _generate_bootstrap_map(
    args: argparse.Namespace,
    *,
    training_stage: str,
) -> AutoGenerationDecision:
    default_level = clamp_level(float(args.default_level))
    map_id = _build_next_map_id(args.map_prefix, args.generated_dir.resolve())
    curve_direction = _choose_curve_direction("bootstrap_seed", map_id, [])
    course_variant = _bootstrap_course_variant(training_stage)
    difficulty_stage_definition = resolve_course_stage(default_level)
    layout_stage_definition = resolve_stage_for_variant(course_variant) or difficulty_stage_definition

    artifacts = generate_map_from_level(
        map_id=map_id,
        level=default_level,
        generated_dir=args.generated_dir.resolve(),
        manifest_dir=args.manifest_dir.resolve(),
        road_id=1,
        open_course=True,
        training_stage=training_stage,
        curve_direction=curve_direction,
        course_variant=course_variant,
    )

    decision = AutoGenerationDecision(
        source_result_path=args.result_dir.resolve() / "_bootstrap_seed.json",
        source_map_id="bootstrap_seed",
        driving_score=0.0,
        current_level=default_level,
        current_level_source="bootstrap_default",
        next_level=default_level,
        difficulty_delta=0.0,
        difficulty_stage_index=difficulty_stage_definition.index,
        difficulty_stage_id=difficulty_stage_definition.stage_id,
        layout_stage_index=layout_stage_definition.index,
        layout_stage_id=layout_stage_definition.stage_id,
        course_variant=course_variant,
        curve_direction=curve_direction,
        next_map_id=map_id,
        generated_xodr_path=artifacts.xodr_path.resolve(),
        generated_manifest_path=artifacts.manifest_path.resolve(),
        training_stage=training_stage,
        bootstrap_mode=True,
    )
    _enrich_manifest_bootstrap(decision.generated_manifest_path, decision=decision)

    if args.load_after_generate:
        loaded_map_name = _load_generated_map(decision.generated_xodr_path, args)
        decision = AutoGenerationDecision(
            **{
                **asdict(decision),
                "loaded_map_name": loaded_map_name,
            }
        )

    return decision


def generate_next_map_from_result(args: argparse.Namespace) -> AutoGenerationDecision:
    training_stage = str(getattr(args, "training_stage", "track")).strip().lower() or "track"
    try:
        result_path = _resolve_result_path(args.result_path, args.result_dir)
    except FileNotFoundError:
        if args.result_path is not None:
            raise
        return _generate_bootstrap_map(args, training_stage=training_stage)
    result = load_episode_result(result_path)
    current_level, level_source = _resolve_current_level(
        result,
        args.manifest_dir.resolve(),
        args.default_level,
    )
    driving_score = compute_driving_score(result)
    next_level = update_difficulty(
        current_level=current_level,
        success_rate=driving_score,
        config=DifficultyUpdateConfig(),
    )
    difficulty_delta = next_level - current_level
    map_id = _build_next_map_id(args.map_prefix, args.generated_dir.resolve())
    recent_history = _load_recent_auto_generation_history(
        args.manifest_dir.resolve(),
        args.map_prefix,
    )
    curve_direction = _choose_curve_direction(result.map_id, map_id, recent_history)
    course_variant = _choose_course_variant(
        next_level,
        result,
        driving_score,
        difficulty_delta,
        curve_direction,
        map_id,
        recent_history,
    )
    difficulty_stage_definition = resolve_course_stage(next_level)
    layout_stage_definition = resolve_stage_for_variant(course_variant) or difficulty_stage_definition

    artifacts = generate_map_from_level(
        map_id=map_id,
        level=next_level,
        generated_dir=args.generated_dir.resolve(),
        manifest_dir=args.manifest_dir.resolve(),
        road_id=1,
        open_course=True,
        training_stage=training_stage,
        curve_direction=curve_direction,
        course_variant=course_variant,
    )

    decision = AutoGenerationDecision(
        source_result_path=result_path,
        source_map_id=result.map_id,
        driving_score=driving_score,
        current_level=current_level,
        current_level_source=level_source,
        next_level=next_level,
        difficulty_delta=difficulty_delta,
        difficulty_stage_index=difficulty_stage_definition.index,
        difficulty_stage_id=difficulty_stage_definition.stage_id,
        layout_stage_index=layout_stage_definition.index,
        layout_stage_id=layout_stage_definition.stage_id,
        course_variant=course_variant,
        curve_direction=curve_direction,
        next_map_id=map_id,
        generated_xodr_path=artifacts.xodr_path.resolve(),
        generated_manifest_path=artifacts.manifest_path.resolve(),
        training_stage=training_stage,
    )
    _enrich_manifest(decision.generated_manifest_path, decision=decision, result=result)

    if args.load_after_generate:
        loaded_map_name = _load_generated_map(decision.generated_xodr_path, args)
        decision = AutoGenerationDecision(
            **{
                **asdict(decision),
                "loaded_map_name": loaded_map_name,
            }
        )

    return decision


def _print_decision(decision: AutoGenerationDecision) -> None:
    if decision.bootstrap_mode:
        print("Source result: none (bootstrap seed)")
        print("Source map: bootstrap_seed")
        print(
            "Difficulty update: "
            f"{decision.current_level:.2f} -> {decision.next_level:.2f} "
            f"(source={decision.current_level_source}, delta={decision.difficulty_delta:+.2f})"
        )
        print("Bootstrap mode: generated the first seed map because no prior evaluation result existed.")
    else:
        print(f"Source result: {decision.source_result_path}")
        print(f"Source map: {decision.source_map_id}")
        print(f"Driving score: {decision.driving_score:.3f}")
        print(
            "Difficulty update: "
            f"{decision.current_level:.2f} -> {decision.next_level:.2f} "
            f"(source={decision.current_level_source}, delta={decision.difficulty_delta:+.2f})"
        )
    print(
        "Selected generator profile: "
        f"{decision.training_stage}/{decision.layout_stage_id}/{decision.course_variant}/{decision.curve_direction} "
        f"(difficulty_stage={decision.difficulty_stage_id})"
    )
    print(f"Generated map id: {decision.next_map_id}")
    print(f"Generated XODR: {decision.generated_xodr_path}")
    print(f"Generated manifest: {decision.generated_manifest_path}")
    if decision.loaded_map_name is not None:
        print(f"Loaded into CARLA: {decision.loaded_map_name}")


def main() -> None:
    args = parse_args()
    try:
        decision = generate_next_map_from_result(args)
    except Exception as error:
        print("Failed to generate the next map automatically.")
        print(f"Reason: {error}")
        raise SystemExit(1) from error

    _print_decision(decision)


if __name__ == "__main__":
    main()
