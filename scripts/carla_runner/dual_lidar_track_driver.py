"""Reactive dual-LiDAR driver for simple wall-following demos on custom tracks."""

from __future__ import annotations

from dataclasses import dataclass
import math
from threading import Lock
from typing import Any


@dataclass
class DualLidarReading:
    """One LiDAR sector summary."""

    distance_m: float
    point_count: int = 0
    timestamp: float = 0.0


@dataclass
class DualLidarTrackDriverConfig:
    """Settings for the reactive dual-LiDAR demo driver."""

    target_speed_kmh: float = 12.0
    min_speed_kmh: float = 7.0
    sensor_range_m: float = 25.0
    horizontal_fov_deg: float = 35.0
    sensor_tick: float = 0.05
    front_x_m: float = 2.1
    side_y_m: float = 0.85
    sensor_z_m: float = 1.3
    left_yaw_deg: float = -45.0
    right_yaw_deg: float = 45.0
    steer_gain: float = 2.2
    steer_smoothing: float = 0.68
    max_steering: float = 0.7
    max_throttle: float = 0.42
    max_brake: float = 0.35
    caution_distance_m: float = 3.0
    emergency_distance_m: float = 2.0
    nearest_point_sample: int = 16
    forward_point_min_x_m: float = 0.4
    channels: int = 8
    points_per_second: int = 24000
    upper_fov_deg: float = 5.0
    lower_fov_deg: float = -15.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _get_speed_kmh(vehicle: Any) -> float:
    velocity = vehicle.get_velocity()
    speed_mps = math.sqrt(
        (velocity.x ** 2) + (velocity.y ** 2) + (velocity.z ** 2)
    )
    return speed_mps * 3.6


class DualLidarTrackDriver:
    """Keep a vehicle roughly centered between two walls using narrow LiDAR sectors."""

    def __init__(
        self,
        world: Any,
        carla_module: Any,
        vehicle: Any,
        left_sensor: Any,
        right_sensor: Any,
        config: DualLidarTrackDriverConfig,
    ) -> None:
        self.world = world
        self.carla = carla_module
        self.vehicle = vehicle
        self.left_sensor = left_sensor
        self.right_sensor = right_sensor
        self.config = config
        self._lock = Lock()
        self._filtered_steer = 0.0
        self.left_reading = DualLidarReading(distance_m=config.sensor_range_m)
        self.right_reading = DualLidarReading(distance_m=config.sensor_range_m)

    @classmethod
    def create(
        cls,
        world: Any,
        carla_module: Any,
        vehicle: Any,
        config: DualLidarTrackDriverConfig | None = None,
    ) -> "DualLidarTrackDriver":
        active_config = config or DualLidarTrackDriverConfig()
        blueprint_library = world.get_blueprint_library()
        lidar_blueprint = blueprint_library.find("sensor.lidar.ray_cast")

        lidar_blueprint.set_attribute("channels", str(active_config.channels))
        lidar_blueprint.set_attribute("range", f"{active_config.sensor_range_m:.2f}")
        lidar_blueprint.set_attribute(
            "points_per_second",
            str(active_config.points_per_second),
        )
        lidar_blueprint.set_attribute("rotation_frequency", "20")
        lidar_blueprint.set_attribute(
            "upper_fov",
            f"{active_config.upper_fov_deg:.2f}",
        )
        lidar_blueprint.set_attribute(
            "lower_fov",
            f"{active_config.lower_fov_deg:.2f}",
        )
        lidar_blueprint.set_attribute(
            "horizontal_fov",
            f"{active_config.horizontal_fov_deg:.2f}",
        )
        lidar_blueprint.set_attribute("dropoff_general_rate", "0.0")
        lidar_blueprint.set_attribute("dropoff_zero_intensity", "0.0")
        lidar_blueprint.set_attribute("dropoff_intensity_limit", "1.0")
        lidar_blueprint.set_attribute("noise_stddev", "0.0")
        lidar_blueprint.set_attribute("sensor_tick", f"{active_config.sensor_tick:.3f}")

        left_transform = carla_module.Transform(
            carla_module.Location(
                x=active_config.front_x_m,
                y=-active_config.side_y_m,
                z=active_config.sensor_z_m,
            ),
            carla_module.Rotation(yaw=active_config.left_yaw_deg),
        )
        right_transform = carla_module.Transform(
            carla_module.Location(
                x=active_config.front_x_m,
                y=active_config.side_y_m,
                z=active_config.sensor_z_m,
            ),
            carla_module.Rotation(yaw=active_config.right_yaw_deg),
        )

        left_sensor = world.spawn_actor(lidar_blueprint, left_transform, attach_to=vehicle)
        right_sensor = world.spawn_actor(
            lidar_blueprint,
            right_transform,
            attach_to=vehicle,
        )

        driver = cls(
            world=world,
            carla_module=carla_module,
            vehicle=vehicle,
            left_sensor=left_sensor,
            right_sensor=right_sensor,
            config=active_config,
        )
        left_sensor.listen(lambda data: driver._update_reading("left", data))
        right_sensor.listen(lambda data: driver._update_reading("right", data))
        return driver

    def _extract_distance(self, lidar_measurement: Any) -> tuple[float, int]:
        distances: list[float] = []
        for detection in lidar_measurement:
            point = detection.point
            if point.x < self.config.forward_point_min_x_m:
                continue
            distances.append(math.sqrt((point.x ** 2) + (point.y ** 2)))

        if not distances:
            return self.config.sensor_range_m, 0

        distances.sort()
        nearest_distances = distances[: self.config.nearest_point_sample]
        representative_distance = sum(nearest_distances) / len(nearest_distances)
        return representative_distance, len(distances)

    def _update_reading(self, side: str, lidar_measurement: Any) -> None:
        distance_m, point_count = self._extract_distance(lidar_measurement)
        reading = DualLidarReading(
            distance_m=distance_m,
            point_count=point_count,
            timestamp=float(getattr(lidar_measurement, "timestamp", 0.0)),
        )
        with self._lock:
            if side == "left":
                self.left_reading = reading
            else:
                self.right_reading = reading

    def run_step(self) -> Any:
        """Compute one reactive wall-centering control step."""

        with self._lock:
            left_distance = self.left_reading.distance_m
            right_distance = self.right_reading.distance_m

        balance_error = (right_distance - left_distance) / max(
            left_distance + right_distance,
            1e-6,
        )
        target_steer = _clamp(
            self.config.steer_gain * balance_error,
            -self.config.max_steering,
            self.config.max_steering,
        )
        self._filtered_steer = (
            (self.config.steer_smoothing * self._filtered_steer)
            + ((1.0 - self.config.steer_smoothing) * target_steer)
        )

        target_speed_kmh = self.config.target_speed_kmh
        nearest_wall = min(left_distance, right_distance)
        if nearest_wall < self.config.caution_distance_m:
            target_speed_kmh = min(target_speed_kmh, self.config.min_speed_kmh + 1.0)
        if nearest_wall < self.config.emergency_distance_m:
            target_speed_kmh = self.config.min_speed_kmh
        if abs(balance_error) > 0.22:
            target_speed_kmh = min(target_speed_kmh, self.config.min_speed_kmh)

        current_speed_kmh = _get_speed_kmh(self.vehicle)
        speed_error = target_speed_kmh - current_speed_kmh

        if speed_error >= 0.0:
            throttle = min(
                self.config.max_throttle,
                0.18 + (0.035 * speed_error),
            )
            brake = 0.0
        else:
            throttle = 0.0
            brake = min(self.config.max_brake, 0.08 * abs(speed_error))

        if abs(self._filtered_steer) > 0.45:
            throttle = min(throttle, 0.24)

        return self.carla.VehicleControl(
            throttle=throttle,
            steer=self._filtered_steer,
            brake=brake,
            hand_brake=False,
            manual_gear_shift=False,
        )

    def destroy(self) -> None:
        """Stop and destroy attached LiDAR sensors."""

        for sensor in (self.left_sensor, self.right_sensor):
            if sensor is None:
                continue
            try:
                sensor.stop()
            except Exception:
                pass
            try:
                sensor.destroy()
            except Exception:
                pass
