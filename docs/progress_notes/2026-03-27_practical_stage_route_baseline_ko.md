# 2026-03-27 Practical Stage Route Baseline

## 이번 단계에서 추가한 것

Practical Stage에서 단순히 Town만 불러오는 수준을 넘어서, 실제로 다음 practical scenario를 하나 생성할 수 있는 baseline을 추가했다.

이번 baseline은 CARLA 기본 Town 위에서 다음 정보를 자동으로 정하는 데 목적이 있다.

- Town
- weather
- traffic/pedestrian 규모
- spawn point
- destination spawn point
- route trace
- route 길이
- junction 비중

## 현재 동작 방식

1. 선택한 Town을 CARLA에 맞춘다.
2. weather preset을 적용한다.
3. Town spawn point 목록을 읽는다.
4. 여러 spawn/destination 후보 쌍을 route planner로 평가한다.
5. 현재 route preset 또는 custom 설정과 가장 잘 맞는 route 후보를 고른다.
6. scenario JSON과 manifest JSON을 저장한다.

## 저장되는 산출물

- `scenarios/practical/<scenario_id>.json`
  - practical runtime이 바로 사용할 수 있는 route/scenario baseline
- `experiments/practical/<scenario_id>.json`
  - preset, custom override, route metric, candidate search 정보까지 포함한 자세한 manifest

## 현재 route baseline이 담는 정보

- `scenario_id`
- `training_stage=practical`
- `scenario_mode=auto/custom`
- `town_id`
- `weather_preset`
- `traffic_vehicle_count`
- `pedestrian_count`
- `route_length_hint_m`
- `junction_focus`
- `spawn`
- `destination`
- `route_metrics`
- `route_waypoints`

## UI 연결 상태

Practical Stage에서 이제 아래 흐름이 가능하다.

- Town / Weather / Traffic / Route preset 선택
- 필요하면 `Open Custom Scenario Settings`로 수동 override 저장
- `Generate Practical Scenario` 버튼으로 다음 practical baseline 생성

즉 Practical Stage는 이제

- Town shell
- custom scenario override shell
- route baseline generation

까지 연결된 상태다.

## 아직 남은 것

다음 단계에서 붙여야 하는 핵심은 아래와 같다.

1. generated practical scenario를 실제 주행 runtime에 연결
2. destination reached / route deviation 중심 practical 평가 추가
3. Traffic Manager 기반 NPC vehicle population 실행
4. 결과 기반 다음 practical scenario adaptation

## 현재 판단

Practical Stage는 이제 placeholder가 아니라 실제 scenario artifact를 만드는 baseline 단계까지 올라왔다.

다음부터는 geometry generation이 아니라, Town 기반 route/scenario runtime과 평가 루프를 순서대로 붙이면 된다.
