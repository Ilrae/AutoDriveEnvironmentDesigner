"""Print the current AED application structure summary."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

if __package__ in {None, ""}:
    sys.path.append(str(Path(__file__).resolve().parents[2]))

from scripts.app.factory import (
    build_current_manual_demo_session,
    format_session_summary,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Show the current AutoDriveEnvironmentDesigner application structure.",
    )
    parser.add_argument(
        "--session-name",
        default="aed_manual_sequence_session",
        help="Application session name to display.",
    )
    parser.add_argument(
        "--pythonapi-path",
        default=None,
        help="Optional CARLA PythonAPI path to include in the session summary.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    session = build_current_manual_demo_session(
        session_name=args.session_name,
        pythonapi_path=args.pythonapi_path,
    )
    print(format_session_summary(session))


if __name__ == "__main__":
    main()
