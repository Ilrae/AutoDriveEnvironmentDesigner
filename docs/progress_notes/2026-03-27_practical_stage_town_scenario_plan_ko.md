# 2026-03-27 Practical Stage Town 기반 시나리오 설계 계획

## 배경

현재 프로젝트는 다음 두 단계를 이미 별도 성격으로 분리해서 다룰 수 있는 기반을 갖추었다.

- Track Stage: 생성형 OpenDRIVE 트랙 기반 검증
- Intermediate Stage: 생성형 OpenDRIVE road-like course 기반 차선 주행 검증

다음 단계인 Practical Stage는 같은 생성형 XODR를 더 복잡하게 만드는 방향보다, CARLA가 원래 잘 제공하는 기본 Town 맵과 교통 시뮬레이션 기능을 활용하는 방향이 더 현실적이다.

그 이유는 다음과 같다.

- CARLA 기본 Town 맵은 교차로, 신호등, 정적 환경, 도심형 시야 구조를 이미 높은 완성도로 제공한다.
- 직접 Town 수준의 맵 에셋을 생성기로 재현하려면 Unreal/asset 파이프라인까지 범위가 커진다.
- 프로젝트 핵심은 맵 에디터 자체보다 환경 설계, 반복 평가, 약점 기반 다음 환경 구성 루프에 있다.

따라서 Practical Stage는 "자동 맵 에디터"가 아니라 "Town 기반 scenario generation and evaluation tool"로 정의하는 것이 맞다.

## 목표 정의

Practical Stage의 목표는 다음과 같다.

1. CARLA 기본 Town 맵을 선택한다.
2. ego vehicle의 시작점과 목적지 또는 route를 정한다.
3. 해당 route를 기준으로 교통, 보행자, 날씨, 시간대, 정차 상황 등의 시나리오 요소를 구성한다.
4. 주행 결과를 평가한다.
5. 결과에서 약한 부분을 추출해 다음 Town 시나리오를 다시 구성한다.

즉 Practical Stage의 핵심 반복 루프는 다음과 같다.

`Town 선택 -> route 구성 -> scenario 요소 배치 -> 주행 -> 평가 -> 약점 반영 -> 다음 scenario 구성`

## Practical Stage의 성격

Practical Stage는 geometry generation보다 scenario generation에 가깝다.

- Track / Intermediate:
  - 주로 road geometry를 생성한다.
  - 맵 shape가 다음 단계 입력의 핵심이다.
- Practical:
  - 이미 존재하는 Town geometry를 사용한다.
  - route, traffic density, pedestrian density, traffic-light exposure, junction exposure, parked obstacle exposure 같은 scenario parameters가 다음 단계 입력의 핵심이다.

따라서 Practical Stage에서는 "맵을 만든다"는 표현보다 "주행 환경을 구성한다"는 표현이 더 정확하다.

## v1 범위

첫 Practical Stage 구현은 아래 범위로 제한하는 것이 좋다.

- Town 선택
- spawn point 선택
- destination 또는 route target 선택
- route 길이와 junction 포함 비율 제어
- NPC vehicle 수 제어
- weather preset 선택
- time-of-day 또는 조명 상태 선택
- 수동 주행 후 결과 저장
- 결과 기반 다음 scenario 난이도 조정

첫 버전에서는 아래 항목은 제외한다.

- custom Unreal asset 배치
- OpenSCENARIO 직접 편집
- 복잡한 scripted incident
- 보행자와 차량의 정교한 상호작용 시나리오
- lane change task를 강제하는 custom mission logic
- ScenarioRunner 의존 구현

## v1 구현 방향

Practical Stage v1은 CARLA PythonAPI와 Traffic Manager만으로 구현한다.

필요 구성 요소는 다음과 같다.

### 1. Town scenario config

새 manifest 또는 config JSON은 다음 정보를 포함한다.

- training_stage = practical
- town_id
- ego_spawn_index
- destination_spawn_index 또는 route_waypoint_set
- route_length_bucket
- junction_density_target
- traffic_vehicle_count
- pedestrian_count
- weather_preset
- time_of_day bucket
- scenario_seed

### 2. Route generator

Town 맵에서 다음 중 하나로 route를 만든다.

- spawn point index -> destination spawn point index
- waypoint graph 탐색 기반 route
- junction 통과 수를 기준으로 route 샘플링

초기 구현은 spawn point 기반 route 선택으로 시작하는 것이 가장 단순하다.

### 3. Scenario augmenter

route가 정해지면 다음 요소를 붙인다.

- Traffic Manager 기반 NPC 차량 수
- 선택적 pedestrian 수
- weather preset
- 라우트 상의 정차/혼잡 노출 정도

여기서 "약한 부분 반영"은 geometry 수정이 아니라 scenario parameter 수정으로 본다.

예시:

- lane keeping이 약함 -> 교차로 적고 긴 route 유지
- 교차로 통과가 약함 -> junction 포함 비율 증가
- 혼잡 대응이 약함 -> traffic_vehicle_count 증가
- 신호 대응이 약함 -> traffic-light가 많은 Town/route 선택

### 4. Evaluation

Practical Stage 평가 항목은 Intermediate보다 확장되어야 한다.

v1 후보 항목:

- route completion
- collision count
- offroad ratio
- lane departure ratio
- opposite lane ratio
- red-light violation count
- route deviation count
- blocked/stuck time
- destination reached

초기에는 이 중 다음을 우선한다.

- completion
- collision
- lane discipline
- route deviation
- destination reached

신호 위반은 v1.5 또는 v2로 미뤄도 된다.

## UI 방향

현재 UI의 stage selector는 이미 준비되어 있으므로, Practical Stage는 새 프로그램이 아니라 기존 앱에 연결하는 형태로 간다.

Practical Stage에서 UI에 추가될 핵심 요소:

- Town 선택 radio 또는 combobox
- traffic preset
- weather preset
- route difficulty preset
- Generate Scenario
- Load + Drive Scenario
- Recent Practical Results

이때 Track / Intermediate와 같은 버튼 이름을 유지하되, 내부 동작만 route/scenario generation으로 바꾸는 것이 좋다.

## 구현 단계 제안

### Step 1. Practical shell

- stage shell 활성화
- Town 선택 UI 추가
- Town map load action 연결
- scenario manifest JSON 저장 형식 정의

### Step 2. Route baseline

- spawn point -> destination 기반 route 생성
- ego spawn / destination marker 표시
- completion 평가 추가

### Step 3. Traffic baseline

- Traffic Manager 기반 NPC vehicle population
- traffic density preset
- 결과에 혼잡도 메타데이터 저장

### Step 4. Practical scoring baseline

- route completion
- lane discipline
- collision
- route deviation
- destination reached

### Step 5. Result-driven scenario adaptation

- 최근 결과를 읽어 다음 route difficulty와 traffic density를 조정
- 약점 기반 practical scenario generation baseline 완성

## ScenarioRunner의 위치

ScenarioRunner는 당장 첫 구현 필수 요소는 아니다.

권장 해석:

- v1: PythonAPI + Traffic Manager만으로 Practical Stage baseline 구현
- v2: 필요하면 ScenarioRunner 0.9.15를 연결해 scripted scenario 추가

이렇게 두는 이유는 다음과 같다.

- 현재 프로젝트는 앱 통합과 반복 평가 루프가 핵심이다.
- ScenarioRunner를 바로 도입하면 환경 셋업과 호환성 관리가 먼저 커질 수 있다.
- CARLA 0.9.15와 버전이 맞는 ScenarioRunner를 별도로 관리해야 한다.

따라서 ScenarioRunner는 Practical Stage를 확장하는 도구로 보는 것이 적절하다.

## 사용자가 먼저 읽으면 좋은 공식 문서

Practical Stage 구현 전, 아래 문서를 먼저 읽는 것이 좋다.

1. CARLA Maps and navigation
- https://carla.readthedocs.io/en/0.9.15/core_map/
- waypoint, lanes, junctions, spawn points, topology 이해에 필수

2. CARLA Traffic Manager
- https://carla.readthedocs.io/en/0.9.15/tuto_G_traffic_manager/
- NPC vehicle population과 route-guided traffic의 시작점

3. CARLA catalogue
- https://carla.readthedocs.io/en/0.9.15/catalogue/
- Town 성격과 차량/보행자/props 범위를 파악할 때 필요

4. ScenarioRunner repository
- https://github.com/carla-simulator/scenario_runner
- CARLA 0.9.15와 호환되는 ScenarioRunner 버전 확인에 필요

5. ScenarioRunner create-a-new-scenario tutorial
- https://scenario-runner.readthedocs.io/en/latest/creating_new_scenario/
- 나중에 scripted scenario를 붙일 때 참고

## 현재 결론

Practical Stage는 생성형 맵 에디터 방향보다 Town 기반 시나리오 생성 방향이 더 적절하다.

현재 프로젝트의 최종 단계 구조는 다음처럼 잡는 것이 가장 자연스럽다.

- Track Stage: generated track validation
- Intermediate Stage: generated road-like validation
- Practical Stage: Town-based scenario generation and evaluation

이 구조는 구현 현실성, CARLA 활용도, 시연 완성도, 보고서 설명력 측면에서 모두 유리하다.
