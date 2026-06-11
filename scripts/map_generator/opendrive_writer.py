"""Generate minimal OpenDRIVE files for early CARLA validation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass, field
from datetime import datetime, timezone
import math
from pathlib import Path
from xml.dom import minidom
import xml.etree.ElementTree as ET


@dataclass
class RoadGeometrySegment:
    """One plan-view geometry segment in the generated OpenDRIVE road."""

    geometry_type: str
    length: float
    curvature: float = 0.0

    def validate(self) -> None:
        """Validate one geometry segment."""

        if self.geometry_type not in {"line", "arc"}:
            raise ValueError("geometry_type must be either 'line' or 'arc'")
        if self.length <= 0:
            raise ValueError("segment length must be greater than 0")
        if self.geometry_type == "arc" and abs(self.curvature) < 1e-9:
            raise ValueError("arc segments require a non-zero curvature")


@dataclass
class StraightRoadConfig:
    """Parameters for a minimal road with an optional single arc segment."""

    road_name: str = "straight_road"
    road_id: int = 1
    road_length: float = 100.0
    curve_length: float = 0.0
    curve_curvature: float = 0.0
    lane_width: float = 3.5
    lanes_per_direction: int = 1
    speed_limit_mps: float = 13.9
    start_x: float = 0.0
    start_y: float = 0.0
    heading_rad: float = 0.0
    vendor: str = "AutoDriveEnvironmentDesigner"
    track_radius: float = 0.0
    custom_segments: list[RoadGeometrySegment] = field(default_factory=list)
    center_mark_type: str = "solid"
    center_mark_color: str = "standard"
    center_mark_width: float = 0.12
    lane_mark_type: str = "solid"
    lane_mark_color: str = "standard"
    lane_mark_width: float = 0.12
    shoulder_width: float = 0.0

    def validate(self) -> None:
        """Validate config values before XML generation."""

        if self.road_length <= 0:
            raise ValueError("road_length must be greater than 0")
        if self.lane_width <= 0:
            raise ValueError("lane_width must be greater than 0")
        if self.lanes_per_direction <= 0:
            raise ValueError("lanes_per_direction must be greater than 0")
        if self.speed_limit_mps <= 0:
            raise ValueError("speed_limit_mps must be greater than 0")
        if self.curve_length < 0:
            raise ValueError("curve_length must be greater than or equal to 0")
        if self.curve_length > 0 and abs(self.curve_curvature) < 1e-9:
            raise ValueError("curve_curvature must be non-zero when curve_length is greater than 0")
        if self.track_radius < 0:
            raise ValueError("track_radius must be greater than or equal to 0")
        if self.center_mark_width <= 0:
            raise ValueError("center_mark_width must be greater than 0")
        if self.lane_mark_width <= 0:
            raise ValueError("lane_mark_width must be greater than 0")
        if self.shoulder_width < 0:
            raise ValueError("shoulder_width must be greater than or equal to 0")

        for segment in self.custom_segments:
            segment.validate()

    @property
    def total_length(self) -> float:
        """Return the full road length including the optional arc segment."""

        if self.custom_segments:
            return sum(segment.length for segment in self.custom_segments)
        return self.road_length + self.curve_length

    def build_segments(self) -> list[RoadGeometrySegment]:
        """Build the ordered geometry list for the current road."""

        if self.custom_segments:
            return self.custom_segments

        segments = [RoadGeometrySegment(geometry_type="line", length=self.road_length)]
        if self.curve_length > 0:
            segments.append(
                RoadGeometrySegment(
                    geometry_type="arc",
                    length=self.curve_length,
                    curvature=self.curve_curvature,
                )
            )

        for segment in segments:
            segment.validate()

        return segments


def build_stadium_track_config(
    road_name: str,
    road_id: int,
    straight_length: float,
    track_radius: float,
    lane_width: float,
    lanes_per_direction: int,
    curve_direction: str = "left",
    speed_limit_mps: float = 13.9,
    start_x: float = 0.0,
    start_y: float = 0.0,
    heading_rad: float = 0.0,
    vendor: str = "AutoDriveEnvironmentDesigner",
) -> StraightRoadConfig:
    """Build a stadium-style oval track with two straights and two half-circle turns."""

    if track_radius <= 0:
        raise ValueError("track_radius must be greater than 0")

    direction_sign = 1.0 if curve_direction == "left" else -1.0
    curve_curvature = direction_sign / track_radius
    curve_length = math.pi * track_radius
    segments = [
        RoadGeometrySegment(geometry_type="line", length=straight_length),
        RoadGeometrySegment(
            geometry_type="arc",
            length=curve_length,
            curvature=curve_curvature,
        ),
        RoadGeometrySegment(geometry_type="line", length=straight_length),
        RoadGeometrySegment(
            geometry_type="arc",
            length=curve_length,
            curvature=curve_curvature,
        ),
    ]

    return StraightRoadConfig(
        road_name=road_name,
        road_id=road_id,
        road_length=straight_length,
        curve_length=curve_length,
        curve_curvature=curve_curvature,
        lane_width=lane_width,
        lanes_per_direction=lanes_per_direction,
        speed_limit_mps=speed_limit_mps,
        start_x=start_x,
        start_y=start_y,
        heading_rad=heading_rad,
        vendor=vendor,
        track_radius=track_radius,
        custom_segments=segments,
    )


def build_open_course_config(
    road_name: str,
    road_id: int,
    lane_width: float,
    lanes_per_direction: int,
    segments: list[RoadGeometrySegment],
    speed_limit_mps: float = 13.9,
    start_x: float = 0.0,
    start_y: float = 0.0,
    heading_rad: float = 0.0,
    vendor: str = "AutoDriveEnvironmentDesigner",
) -> StraightRoadConfig:
    """Build a small open course with a fixed ordered list of segments."""

    if not segments:
        raise ValueError("segments must contain at least one geometry segment")

    for segment in segments:
        segment.validate()

    total_line_length = sum(
        segment.length for segment in segments if segment.geometry_type == "line"
    )
    total_curve_length = sum(
        segment.length for segment in segments if segment.geometry_type == "arc"
    )
    first_curve_curvature = next(
        (
            segment.curvature
            for segment in segments
            if segment.geometry_type == "arc"
        ),
        0.0,
    )

    return StraightRoadConfig(
        road_name=road_name,
        road_id=road_id,
        road_length=total_line_length if total_line_length > 0 else segments[0].length,
        curve_length=total_curve_length,
        curve_curvature=first_curve_curvature,
        lane_width=lane_width,
        lanes_per_direction=lanes_per_direction,
        speed_limit_mps=speed_limit_mps,
        start_x=start_x,
        start_y=start_y,
        heading_rad=heading_rad,
        vendor=vendor,
        custom_segments=list(segments),
    )


def _format_float(value: float) -> str:
    return f"{value:.6f}"


def _advance_pose(
    x: float,
    y: float,
    heading_rad: float,
    segment: RoadGeometrySegment,
) -> tuple[float, float, float]:
    """Advance the geometry cursor to the end of one plan-view segment."""

    if segment.geometry_type == "line":
        return (
            x + segment.length * math.cos(heading_rad),
            y + segment.length * math.sin(heading_rad),
            heading_rad,
        )

    curvature = segment.curvature
    end_heading = heading_rad + curvature * segment.length
    end_x = x + (math.sin(end_heading) - math.sin(heading_rad)) / curvature
    end_y = y - (math.cos(end_heading) - math.cos(heading_rad)) / curvature
    return end_x, end_y, end_heading


def _add_lane(
    parent: ET.Element,
    lane_id: int,
    lane_width: float,
    *,
    road_mark_type: str,
    road_mark_color: str,
    road_mark_width: float,
    lane_change: str,
    lane_type: str = "driving",
) -> None:
    lane = ET.SubElement(
        parent,
        "lane",
        {
            "id": str(lane_id),
            "type": lane_type,
            "level": "false",
        },
    )
    ET.SubElement(lane, "link")
    ET.SubElement(
        lane,
        "width",
        {
            "sOffset": "0.000000",
            "a": _format_float(lane_width),
            "b": "0.000000",
            "c": "0.000000",
            "d": "0.000000",
        },
    )
    ET.SubElement(
        lane,
        "roadMark",
        {
            "sOffset": "0.000000",
            "type": road_mark_type,
            "weight": "standard",
            "color": road_mark_color,
            "width": _format_float(road_mark_width),
            "laneChange": lane_change,
        },
    )


def build_straight_road_tree(config: StraightRoadConfig) -> ET.ElementTree:
    """Build a minimal OpenDRIVE tree for a straight or straight-plus-arc road."""

    config.validate()

    root = ET.Element("OpenDRIVE")
    ET.SubElement(
        root,
        "header",
        {
            "revMajor": "1",
            "revMinor": "4",
            "name": config.road_name,
            "version": "1.00",
            "date": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "north": "0.000000",
            "south": "0.000000",
            "east": "0.000000",
            "west": "0.000000",
            "vendor": config.vendor,
        },
    )

    road = ET.SubElement(
        root,
        "road",
        {
            "name": config.road_name,
            "length": _format_float(config.total_length),
            "id": str(config.road_id),
            "junction": "-1",
        },
    )
    ET.SubElement(road, "link")

    road_type = ET.SubElement(
        road,
        "type",
        {
            "s": "0.000000",
            "type": "town",
        },
    )
    ET.SubElement(
        road_type,
        "speed",
        {
            "max": _format_float(config.speed_limit_mps),
            "unit": "m/s",
        },
    )

    plan_view = ET.SubElement(road, "planView")
    current_s = 0.0
    current_x = config.start_x
    current_y = config.start_y
    current_heading = config.heading_rad

    for segment in config.build_segments():
        geometry = ET.SubElement(
            plan_view,
            "geometry",
            {
                "s": _format_float(current_s),
                "x": _format_float(current_x),
                "y": _format_float(current_y),
                "hdg": _format_float(current_heading),
                "length": _format_float(segment.length),
            },
        )

        if segment.geometry_type == "line":
            ET.SubElement(geometry, "line")
        else:
            ET.SubElement(
                geometry,
                "arc",
                {"curvature": _format_float(segment.curvature)},
            )

        current_x, current_y, current_heading = _advance_pose(
            current_x,
            current_y,
            current_heading,
            segment,
        )
        current_s += segment.length

    elevation_profile = ET.SubElement(road, "elevationProfile")
    ET.SubElement(
        elevation_profile,
        "elevation",
        {
            "s": "0.000000",
            "a": "0.000000",
            "b": "0.000000",
            "c": "0.000000",
            "d": "0.000000",
        },
    )

    ET.SubElement(road, "lateralProfile")
    lanes = ET.SubElement(road, "lanes")
    ET.SubElement(
        lanes,
        "laneOffset",
        {
            "s": "0.000000",
            "a": "0.000000",
            "b": "0.000000",
            "c": "0.000000",
            "d": "0.000000",
        },
    )

    lane_section = ET.SubElement(lanes, "laneSection", {"s": "0.000000"})
    left = ET.SubElement(lane_section, "left")
    center = ET.SubElement(lane_section, "center")
    right = ET.SubElement(lane_section, "right")

    center_lane = ET.SubElement(
        center,
        "lane",
        {
            "id": "0",
            "type": "none",
            "level": "false",
        },
    )
    ET.SubElement(center_lane, "link")
    ET.SubElement(
        center_lane,
        "roadMark",
        {
            "sOffset": "0.000000",
            "type": config.center_mark_type,
            "weight": "standard",
            "color": config.center_mark_color,
            "width": _format_float(config.center_mark_width),
            "laneChange": "none",
        },
    )

    for lane_index in range(1, config.lanes_per_direction + 1):
        _add_lane(
            left,
            lane_index,
            config.lane_width,
            road_mark_type=config.lane_mark_type,
            road_mark_color=config.lane_mark_color,
            road_mark_width=config.lane_mark_width,
            lane_change="both",
        )
        _add_lane(
            right,
            -lane_index,
            config.lane_width,
            road_mark_type=config.lane_mark_type,
            road_mark_color=config.lane_mark_color,
            road_mark_width=config.lane_mark_width,
            lane_change="both",
        )

    if config.shoulder_width > 0.0:
        _add_lane(
            left,
            config.lanes_per_direction + 1,
            config.shoulder_width,
            road_mark_type="solid",
            road_mark_color="white",
            road_mark_width=0.10,
            lane_change="none",
            lane_type="shoulder",
        )
        _add_lane(
            right,
            -(config.lanes_per_direction + 1),
            config.shoulder_width,
            road_mark_type="solid",
            road_mark_color="white",
            road_mark_width=0.10,
            lane_change="none",
            lane_type="shoulder",
        )

    return ET.ElementTree(root)


def build_straight_road_xml(config: StraightRoadConfig) -> str:
    """Return the generated OpenDRIVE XML as a string."""

    root = build_straight_road_tree(config).getroot()
    rough_xml = ET.tostring(root, encoding="utf-8")
    return minidom.parseString(rough_xml).toprettyxml(indent="  ", encoding="UTF-8").decode("utf-8")


def write_straight_road_file(output_path: Path, config: StraightRoadConfig) -> Path:
    """Write a minimal OpenDRIVE road file to disk."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    xml_body = build_straight_road_xml(config)
    output_path.write_text(xml_body, encoding="utf-8")
    return output_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a minimal OpenDRIVE road file with an optional arc segment.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("maps/generated/straight_road_test_001.xodr"),
        help="Output .xodr path.",
    )
    parser.add_argument(
        "--road-length",
        type=float,
        default=100.0,
        help="Straight segment length in meters.",
    )
    parser.add_argument(
        "--curve-length",
        type=float,
        default=0.0,
        help="Optional arc segment length in meters.",
    )
    parser.add_argument(
        "--curve-curvature",
        type=float,
        default=0.0,
        help="Optional arc curvature. Positive turns left, negative turns right.",
    )
    parser.add_argument(
        "--lane-width",
        type=float,
        default=3.5,
        help="Lane width in meters.",
    )
    parser.add_argument(
        "--lanes-per-direction",
        type=int,
        default=1,
        help="Number of driving lanes on each side.",
    )
    parser.add_argument(
        "--road-name",
        default="straight_road_test_001",
        help="Road name to embed in the OpenDRIVE file.",
    )
    parser.add_argument(
        "--stadium-track",
        action="store_true",
        help="Generate a stadium-style oval track with two straights and two half-circle turns.",
    )
    parser.add_argument(
        "--track-radius",
        type=float,
        default=60.0,
        help="Track radius in meters when --stadium-track is used.",
    )
    parser.add_argument(
        "--curve-direction",
        choices=("left", "right"),
        default="left",
        help="Turn direction used for the generated stadium track.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.stadium_track:
        config = build_stadium_track_config(
            road_name=args.road_name,
            road_id=1,
            straight_length=args.road_length,
            track_radius=args.track_radius,
            lane_width=args.lane_width,
            lanes_per_direction=args.lanes_per_direction,
            curve_direction=args.curve_direction,
        )
    else:
        config = StraightRoadConfig(
            road_name=args.road_name,
            road_length=args.road_length,
            curve_length=args.curve_length,
            curve_curvature=args.curve_curvature,
            lane_width=args.lane_width,
            lanes_per_direction=args.lanes_per_direction,
        )
    written_path = write_straight_road_file(args.output, config)
    print(f"Wrote OpenDRIVE draft to: {written_path}")


if __name__ == "__main__":
    main()
