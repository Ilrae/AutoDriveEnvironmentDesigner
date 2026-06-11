# 차량 모델/주행 방식 입력 구조 정리

## 1. 구조 정리의 필요성

본 프로젝트의 핵심 목표는 자율주행 알고리즘 자체를 구현하는 것이 아니라, OpenDRIVE 기반 주행 환경을 생성하고 CARLA에서 반복적으로 평가 가능한 형태로 운영하는 것이다. 따라서 차량 제어 방식은 프로젝트 본체라기보다, 생성된 환경을 검증하기 위한 외부 입력 또는 연결 가능한 모듈로 보는 것이 적절하다.

초기에는 CARLA 기본 autopilot을 이용하여 생성된 트랙의 주행 가능성을 확인하려고 하였다. 그러나 custom OpenDRIVE 트랙에서 기본 autopilot의 주행 성능이 충분히 안정적이지 않았기 때문에, 중간 단계 검증 및 시연은 수동 주행 기반으로 전환하였다.

## 2. 현재 기준으로 정리한 역할 분리

현재 프로젝트에서 책임을 다음과 같이 구분하는 것이 가장 적절하다.

### 앱(본 프로젝트)이 담당하는 역할

- OpenDRIVE 맵 생성
- 생성된 `.xodr` 맵을 CARLA에 로드
- 차량 모델 선택
- 차량 소환 및 재소환
- 맵 재로딩 및 다음 맵 전환
- 주행 결과 저장 및 평가

### 외부 주행 모듈 또는 사용자 입력이 담당하는 역할

- 이미 소환된 차량을 어떤 방식으로 조작할지 결정
- 수동 주행, CARLA 기본 autopilot, BasicAgent, 사용자 자율주행 코드 등 선택
- 차량 제어 명령(`throttle`, `steer`, `brake`) 생성

즉, 차량 소환 자체는 앱이 담당하고, 주행 로직은 앱이 제공하는 차량을 받아 조작하는 구조가 기본이 된다.

## 3. CARLA 일반 사용 방식과의 정합성

CARLA 공식 예제와 문서 기준으로도 이 구조가 자연스럽다.

- `manual_control.py`는 ego vehicle을 스폰한 뒤, 키보드 입력으로 해당 차량을 제어한다.
- `BasicAgent`나 `BehaviorAgent` 예제는 먼저 차량을 스폰하고, 그 차량을 agent에 전달한 뒤 `vehicle.apply_control(agent.run_step())` 방식으로 제어한다.
- ScenarioRunner/Leaderboard 계열에서는 시나리오 또는 환경 쪽이 ego vehicle을 준비하고, agent는 센서/상태를 받아 제어 명령만 반환하는 구조를 사용한다.

따라서 본 프로젝트도 CARLA 사용 관례에 맞게, `환경 생성기/실행기`와 `주행 주체`를 분리하는 것이 타당하다.

## 4. 앱 입력 구조 방향

향후 애플리케이션 입력은 다음 두 가지 형태를 모두 수용할 수 있도록 설계하는 것이 적절하다.

### 4-1. 분리형 입력

- 차량 모델 입력
- 주행 방식 입력

예시:

- 차량 모델: `vehicle.tesla.model3`
- 주행 방식: `manual`, `carla_autopilot`, `basic_agent`, `external_driver_module`

이 경우 앱은 차량 모델과 주행 방식을 각각 입력받고, 앱이 차량을 소환한 뒤 해당 주행 모듈을 연결한다.

### 4-2. 통합형 입력

- 하나의 외부 모듈 또는 설정이 차량 정보와 주행 방식 정보를 함께 제공

예시:

- 외부 자율주행 패키지가 `선호 차량 모델 + 제어 코드`를 같이 제공

이 경우에도 차량 소환은 앱이 수행하고, 외부 모듈은 차량 선택 정보와 제어 로직을 함께 전달하는 구조로 해석한다.

즉, 통합형 입력이라 하더라도 `차량 소환 주체`는 앱으로 유지한다.

## 5. 현재 코드 기반 정리

현재 코드에서는 이 구조를 위한 기반 파일을 분리해두었다.

- 차량 프로필: [vehicle_profiles.py](C:/Users/user/Documents/Codex_Workspace/AutoDriveEnvironmentDesigner/scripts/carla_runner/vehicle_profiles.py)
- 주행 프로필: [driver_profiles.py](C:/Users/user/Documents/Codex_Workspace/AutoDriveEnvironmentDesigner/scripts/carla_runner/driver_profiles.py)
- 앱 입력 바인딩: [input_bindings.py](C:/Users/user/Documents/Codex_Workspace/AutoDriveEnvironmentDesigner/scripts/carla_runner/input_bindings.py)

이 구조를 통해 현재는 수동 주행 데모와 맵 순환 데모가 `split input` 형태로 동작하도록 정리되어 있으며, 향후에는 외부 자율주행 코드 입력도 같은 구조 안에 연결할 수 있다.

## 6. 중간보고서용 정리 문장

중간보고서에는 다음과 같이 정리할 수 있다.

> 본 프로젝트는 OpenDRIVE 기반 주행 환경 생성 및 반복 평가 구조를 목표로 하며, 차량 제어 알고리즘 자체는 프로젝트의 핵심 범위에 포함하지 않는다. 따라서 애플리케이션은 맵 생성, 맵 로딩, 차량 소환 및 재소환을 담당하고, 차량 주행 방식은 수동 주행, CARLA 기본 기능, 또는 외부 자율주행 모듈 형태로 분리하여 연결 가능한 구조로 설계하였다.

> 초기 검증 단계에서는 CARLA 기본 autopilot을 시험적으로 적용하였으나, custom OpenDRIVE 트랙에서의 주행 품질이 충분하지 않아 중간 시연 및 검증은 수동 주행 기반으로 진행하였다. 향후에는 외부 자율주행 코드를 입력받아 동일한 평가 루프에 연결할 수 있도록 확장할 계획이다.
