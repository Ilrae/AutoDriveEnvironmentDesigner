"""Validate one AED baseline result JSON against its expected score band."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.evaluation.result_models import EpisodeResult, load_episode_result
from scripts.evaluation.scoring import compute_driving_score


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate one baseline result JSON against the saved baseline expectations.",
    )
    parser.add_argument(
        "--result-path",
        type=Path,
        required=True,
        help="Result JSON file to validate.",
    )
    parser.add_argument(
        "--manifest-dir",
        type=Path,
        default=Path("experiments"),
        help="Fallback manifest directory if the result metadata does not carry a manifest path.",
    )
    return parser.parse_args()


def _load_manifest_for_result(
    result: EpisodeResult,
    result_path: Path,
    manifest_dir: Path,
) -> dict[str, Any]:
    metadata = result.metadata or {}
    manifest_path_value = metadata.get("manifest_path")
    if manifest_path_value:
        manifest_path = Path(str(manifest_path_value))
    else:
        manifest_path = manifest_dir / f"{result.map_id}.json"

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Matching manifest was not found for baseline validation: {manifest_path}"
        )
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _format_check_status(label: str, passed: bool, detail: str) -> str:
    status = "PASS" if passed else "FAIL"
    return f"[{status}] {label}: {detail}"


def validate_baseline_result(
    result_path: Path,
    *,
    manifest_dir: Path,
) -> tuple[bool, list[str]]:
    result = load_episode_result(result_path)
    manifest = _load_manifest_for_result(result, result_path, manifest_dir)
    baseline_suite = manifest.get("baseline_suite")
    if not isinstance(baseline_suite, dict):
        raise ValueError("The selected result does not point to a baseline-suite manifest.")

    expected = baseline_suite.get("expected_manual_result")
    if not isinstance(expected, dict):
        raise ValueError("The baseline manifest does not define expected_manual_result.")

    checks: list[tuple[str, bool, str]] = []
    driving_score = compute_driving_score(
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

    checks.append(
        (
            "success",
            bool(result.success),
            f"success={result.success}, failure_reason={result.failure_reason}",
        )
    )
    checks.append(
        (
            "finish_line",
            bool(result.crossed_finish_line),
            f"crossed_finish_line={result.crossed_finish_line}",
        )
    )

    min_completion_ratio = expected.get("min_completion_ratio")
    if min_completion_ratio is not None:
        checks.append(
            (
                "completion_ratio",
                result.completion_ratio >= float(min_completion_ratio),
                f"{result.completion_ratio:.3f} >= {float(min_completion_ratio):.3f}",
            )
        )

    min_path_tracking_score = expected.get("min_path_tracking_score")
    if min_path_tracking_score is not None:
        checks.append(
            (
                "path_tracking_score",
                result.path_tracking_score >= float(min_path_tracking_score),
                f"{result.path_tracking_score:.3f} >= {float(min_path_tracking_score):.3f}",
            )
        )

    min_path_match_score = expected.get("min_path_match_score")
    if min_path_match_score is not None:
        checks.append(
            (
                "raw_path_match_score",
                result.path_match_score >= float(min_path_match_score),
                f"{result.path_match_score:.3f} >= {float(min_path_match_score):.3f}",
            )
        )

    max_offroad_ratio = expected.get("max_offroad_ratio")
    if max_offroad_ratio is not None:
        checks.append(
            (
                "offroad_ratio",
                result.offroad_ratio <= float(max_offroad_ratio),
                f"{result.offroad_ratio:.3f} <= {float(max_offroad_ratio):.3f}",
            )
        )

    max_collision_count = expected.get("max_collision_count")
    if max_collision_count is not None:
        checks.append(
            (
                "collision_count",
                result.collision_count <= int(max_collision_count),
                f"{result.collision_count} <= {int(max_collision_count)}",
            )
        )

    max_mean_lateral_error_m = expected.get("max_mean_lateral_error_m")
    if max_mean_lateral_error_m is not None:
        checks.append(
            (
                "mean_lateral_error_m",
                result.mean_lateral_error_m <= float(max_mean_lateral_error_m),
                f"{result.mean_lateral_error_m:.3f} <= {float(max_mean_lateral_error_m):.3f}",
            )
        )

    lines = [
        f"Baseline case: {baseline_suite.get('display_name', result.map_id)}",
        f"Case id: {baseline_suite.get('case_id', result.map_id)}",
        f"Intent: {baseline_suite.get('intent', 'unknown')}",
        f"Evaluation target mode: {baseline_suite.get('evaluation_target_mode', 'unknown')}",
        (
            "Result summary: "
            f"driving_score={driving_score:.3f}, "
            f"path_tracking={result.path_tracking_score:.3f}, "
            f"raw_match={result.path_match_score:.3f}, "
            f"completion={result.completion_ratio:.3f}, "
            f"offroad={result.offroad_ratio:.3f}, "
            f"collisions={result.collision_count}, "
            f"mean_error={result.mean_lateral_error_m:.3f}"
        ),
        "Checks:",
    ]
    passed_all = True
    for label, passed, detail in checks:
        if not passed:
            passed_all = False
        lines.append(_format_check_status(label, passed, detail))

    lines.append(f"Baseline validation: {'PASS' if passed_all else 'FAIL'}")
    return passed_all, lines


def main() -> None:
    args = parse_args()
    result_path = args.result_path.resolve()
    if not result_path.exists():
        print(f"Result file does not exist: {result_path}")
        raise SystemExit(1)

    try:
        passed, lines = validate_baseline_result(
            result_path,
            manifest_dir=args.manifest_dir.resolve(),
        )
    except Exception as error:
        print("Failed to validate the baseline result.")
        print(f"Reason: {error}")
        raise SystemExit(1) from error

    for line in lines:
        print(line)
    raise SystemExit(0 if passed else 2)


if __name__ == "__main__":
    main()
