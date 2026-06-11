"""Compact post-run review helpers for pygame finish/goal screens."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from scripts.app.auto_generation import preview_track_adjustment
from scripts.app.practical_scenario_generation import preview_practical_adaptation
from scripts.evaluation.result_models import EpisodeResult, load_episode_result
from scripts.evaluation.scoring import compute_driving_score as compute_episode_driving_score


def build_episode_result_from_overlay(
    *,
    map_id: str,
    overlay: Any,
    crossed_finish_line: bool = True,
    metadata: dict[str, Any] | None = None,
) -> EpisodeResult:
    """Convert one runtime HUD overlay into an EpisodeResult-like object."""

    return EpisodeResult(
        map_id=str(map_id),
        success=bool(overlay.success),
        time_sec=float(overlay.time_sec),
        collision_count=int(overlay.collision_count),
        offroad_ratio=float(overlay.offroad_ratio),
        failure_reason=overlay.failure_reason,
        path_match_score=float(overlay.path_match_score),
        path_tracking_score=float(overlay.path_tracking_score),
        lane_discipline_score=float(overlay.lane_discipline_score),
        lane_departure_ratio=float(overlay.lane_departure_ratio),
        opposite_lane_ratio=float(overlay.opposite_lane_ratio),
        mean_lateral_error_m=float(overlay.mean_lateral_error_m),
        max_lateral_error_m=float(overlay.mean_lateral_error_m),
        completion_ratio=float(overlay.completion_ratio),
        crossed_finish_line=bool(crossed_finish_line),
        sample_count=0,
        metadata=dict(metadata or {}),
    )


def _result_score(result: EpisodeResult) -> float:
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


def _outcome_text(result: EpisodeResult) -> str:
    return "success" if result.success else str(result.failure_reason or "review")


def _iter_recent_results(
    result_dir: Path,
    *,
    exclude_paths: set[Path] | None = None,
    limit: int = 2,
) -> list[EpisodeResult]:
    exclude_paths = {path.resolve() for path in (exclude_paths or set())}
    candidates: list[Path] = []
    if result_dir.exists():
        candidates = sorted(
            result_dir.glob("*.json"),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    results: list[EpisodeResult] = []
    for candidate in candidates:
        resolved = candidate.resolve()
        if resolved in exclude_paths:
            continue
        try:
            results.append(load_episode_result(resolved))
        except Exception:
            continue
        if len(results) >= limit:
            break
    return results


def build_result_comparison_lines(
    *,
    current_result: EpisodeResult,
    result_dir: Path,
    exclude_paths: set[Path] | None = None,
    limit: int = 2,
) -> list[str]:
    """Build a compact current-vs-recent comparison table."""

    lines = [
        f"Current: {current_result.map_id}",
        "Run      Score  Comp  Coll  Offrd  Lane  Wrong  Outcome",
    ]
    rows: list[tuple[str, EpisodeResult]] = [("CURRENT", current_result)]
    recent_results = _iter_recent_results(
        result_dir,
        exclude_paths=exclude_paths,
        limit=limit,
    )
    rows.extend((f"PREV-{index + 1}", result) for index, result in enumerate(recent_results))
    for label, result in rows:
        lines.append(
            f"{label:<7} "
            f"{_result_score(result) * 100.0:5.1f}  "
            f"{result.completion_ratio * 100.0:5.1f}%  "
            f"{result.collision_count:>4}  "
            f"{result.offroad_ratio * 100.0:5.1f}%  "
            f"{result.lane_discipline_score * 100.0:5.1f}%  "
            f"{result.opposite_lane_ratio * 100.0:5.1f}%  "
            f"{_outcome_text(result)}"
        )
    if len(rows) == 1:
        lines.append("No earlier saved results were found yet.")
    return lines


def build_track_adaptation_lines(
    *,
    current_result: EpisodeResult,
    current_level: float,
) -> list[str]:
    """Preview the next Track/Intermediate map adjustment from the current result."""

    preview = preview_track_adjustment(
        result=current_result,
        current_level=current_level,
    )
    return [
        f"Current score: {preview['driving_score'] * 100.0:5.1f} / 100",
        (
            "Difficulty: "
            f"{preview['current_level']:.2f} -> {preview['next_level']:.2f} "
            f"({preview['difficulty_delta']:+.2f})"
        ),
        f"Stage band: {preview['current_stage_id']} -> {preview['next_stage_id']}",
        f"Rule: {preview['primary_reason']}",
        f"Why: {preview['summary']}",
        f"Next bias: {preview['next_bias']}",
    ]


def build_practical_adaptation_lines(
    *,
    current_result: EpisodeResult,
    traffic_vehicle_count: int,
    pedestrian_count: int,
    route_length_hint_m: int,
    junction_focus: str,
) -> list[str]:
    """Preview the next Practical Town scenario adjustment from the current result."""

    preview = preview_practical_adaptation(
        traffic_vehicle_count=traffic_vehicle_count,
        pedestrian_count=pedestrian_count,
        route_length_hint_m=route_length_hint_m,
        junction_focus=junction_focus,
        result=current_result,
    )
    return [
        f"Current score: {_result_score(current_result) * 100.0:5.1f} / 100",
        (
            "Traffic / pedestrians: "
            f"{traffic_vehicle_count} -> {preview['traffic_vehicle_count']} / "
            f"{pedestrian_count} -> {preview['pedestrian_count']}"
        ),
        (
            "Route / junctions: "
            f"{route_length_hint_m}m -> {preview['route_length_hint_m']}m / "
            f"{junction_focus} -> {preview['junction_focus']}"
        ),
        f"Rule: {', '.join(preview['applied_reasons']) or 'hold'}",
        f"Why: {preview['summary']}",
    ]


def draw_review_panel(
    display: Any,
    *,
    pygame: Any,
    width: int,
    top: int,
    anchor: str = "right",
    title_font: Any,
    body_font: Any,
    title: str,
    lines: list[str],
) -> int:
    """Draw one compact review panel in the top-right corner."""

    title_surface = title_font.render(title, True, (255, 255, 255))
    line_surfaces = [
        body_font.render(line, True, (236, 236, 236))
        for line in lines
    ]
    panel_width = max(
        420,
        title_surface.get_width() + 36,
        max((surface.get_width() for surface in line_surfaces), default=0) + 36,
    )
    panel_height = 28 + title_surface.get_height() + (len(line_surfaces) * 22) + 22
    panel = pygame.Surface((panel_width, panel_height), pygame.SRCALPHA)
    panel.fill((12, 16, 20, 220))
    rect = panel.get_rect()
    normalized_anchor = str(anchor).strip().lower()
    if normalized_anchor == "left":
        rect.topleft = (18, top)
    else:
        rect.topright = (width - 18, top)
    display.blit(panel, rect.topleft)
    display.blit(title_surface, (rect.x + 16, rect.y + 14))

    current_y = rect.y + 48
    for surface in line_surfaces:
        display.blit(surface, (rect.x + 16, current_y))
        current_y += 22
    return rect.bottom
