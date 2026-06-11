"""Simple result models and JSON persistence helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
import json
from pathlib import Path
from typing import Any

from scripts.evaluation.scoring import approximate_path_tracking_score


def _resolve_road_half_width_from_metadata(metadata: dict[str, Any]) -> float:
    """Recover the evaluation road half-width from saved metadata when possible."""

    road_config = metadata.get("road_config")
    if isinstance(road_config, dict):
        lane_width = road_config.get("lane_width")
        lanes_per_direction = road_config.get("lanes_per_direction", 1)
        shoulder_width = road_config.get("shoulder_width", 0.0)
        if lane_width is not None:
            return max(
                0.1,
                (float(lane_width) * max(1, int(lanes_per_direction)))
                + max(0.0, float(shoulder_width)),
            )

    lane_width_m = metadata.get("lane_width_m")
    if lane_width_m is not None:
        return max(0.1, float(lane_width_m))

    return 4.5


@dataclass
class EpisodeResult:
    """Run result format for manual and automated track evaluation."""

    map_id: str
    success: bool
    time_sec: float
    collision_count: int
    offroad_ratio: float
    failure_reason: str | None = None
    path_match_score: float = 0.0
    path_tracking_score: float = 0.0
    lane_discipline_score: float = 1.0
    lane_departure_ratio: float = 0.0
    opposite_lane_ratio: float = 0.0
    mean_lateral_error_m: float = 0.0
    max_lateral_error_m: float = 0.0
    completion_ratio: float = 0.0
    crossed_finish_line: bool = False
    sample_count: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    def validate(self) -> None:
        """Validate values before saving or post-processing."""

        if self.time_sec < 0:
            raise ValueError("time_sec must be greater than or equal to 0")
        if self.collision_count < 0:
            raise ValueError("collision_count must be greater than or equal to 0")
        if not 0.0 <= self.offroad_ratio <= 1.0:
            raise ValueError("offroad_ratio must be between 0.0 and 1.0")
        if not 0.0 <= self.path_match_score <= 1.0:
            raise ValueError("path_match_score must be between 0.0 and 1.0")
        if not 0.0 <= self.path_tracking_score <= 1.0:
            raise ValueError("path_tracking_score must be between 0.0 and 1.0")
        if not 0.0 <= self.lane_discipline_score <= 1.0:
            raise ValueError("lane_discipline_score must be between 0.0 and 1.0")
        if not 0.0 <= self.lane_departure_ratio <= 1.0:
            raise ValueError("lane_departure_ratio must be between 0.0 and 1.0")
        if not 0.0 <= self.opposite_lane_ratio <= 1.0:
            raise ValueError("opposite_lane_ratio must be between 0.0 and 1.0")
        if self.mean_lateral_error_m < 0:
            raise ValueError("mean_lateral_error_m must be greater than or equal to 0")
        if self.max_lateral_error_m < 0:
            raise ValueError("max_lateral_error_m must be greater than or equal to 0")
        if self.max_lateral_error_m < self.mean_lateral_error_m:
            raise ValueError("max_lateral_error_m must be greater than or equal to mean_lateral_error_m")
        if not 0.0 <= self.completion_ratio <= 1.0:
            raise ValueError("completion_ratio must be between 0.0 and 1.0")
        if self.sample_count < 0:
            raise ValueError("sample_count must be greater than or equal to 0")

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-serializable dictionary."""

        self.validate()
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "EpisodeResult":
        """Build an instance from a saved dictionary."""

        metadata = dict(payload.get("metadata", {}))
        path_match_score = float(payload.get("path_match_score", 0.0))
        mean_lateral_error_m = float(payload.get("mean_lateral_error_m", 0.0))
        max_lateral_error_m = float(payload.get("max_lateral_error_m", 0.0))
        path_tracking_score_payload = payload.get("path_tracking_score")
        if path_tracking_score_payload is None:
            path_tracking_score = approximate_path_tracking_score(
                path_match_score=path_match_score,
                mean_lateral_error_m=mean_lateral_error_m,
                max_lateral_error_m=max_lateral_error_m,
                path_tolerance_m=float(metadata.get("path_tolerance_m", 1.5)),
                road_half_width_m=_resolve_road_half_width_from_metadata(metadata),
                offroad_margin_m=float(metadata.get("offroad_margin_m", 0.25)),
            )
        else:
            path_tracking_score = float(path_tracking_score_payload)
        lane_discipline_score = float(payload.get("lane_discipline_score", path_tracking_score))
        lane_departure_ratio = float(payload.get("lane_departure_ratio", 0.0))
        opposite_lane_ratio = float(payload.get("opposite_lane_ratio", 0.0))

        result = cls(
            map_id=str(payload["map_id"]),
            success=bool(payload["success"]),
            time_sec=float(payload["time_sec"]),
            collision_count=int(payload["collision_count"]),
            offroad_ratio=float(payload["offroad_ratio"]),
            failure_reason=payload.get("failure_reason"),
            path_match_score=path_match_score,
            path_tracking_score=path_tracking_score,
            lane_discipline_score=lane_discipline_score,
            lane_departure_ratio=lane_departure_ratio,
            opposite_lane_ratio=opposite_lane_ratio,
            mean_lateral_error_m=mean_lateral_error_m,
            max_lateral_error_m=max_lateral_error_m,
            completion_ratio=float(payload.get("completion_ratio", 0.0)),
            crossed_finish_line=bool(
                payload.get(
                    "crossed_finish_line",
                    payload.get("reached_goal", False),
                )
            ),
            sample_count=int(payload.get("sample_count", 0)),
            metadata=metadata,
        )
        result.validate()
        return result


def save_episode_result(result: EpisodeResult, output_path: Path) -> Path:
    """Save a result JSON file."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps(result.to_dict(), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return output_path


def load_episode_result(input_path: Path) -> EpisodeResult:
    """Load a result JSON file."""

    payload = json.loads(input_path.read_text(encoding="utf-8"))
    return EpisodeResult.from_dict(payload)
