# 현재까지 진행 요약

## 1. 프로젝트 목표

프로젝트 목표는 `CARLA에서 사용할 OpenDRIVE 도로를 자동 생성하고, 차량 주행 결과를 평가하여 다음 도로를 다시 생성하는 시스템`을 만드는 것이다.

현재까지는 그중에서도 가장 중요한 기초 단계, 즉 아래 흐름을 실제로 작동시키는 데 집중했다.

1. OpenDRIVE 맵 생성
2. CARLA 로드
3. 차량 spawn
4. autopilot 주행
5. 결과 저장

## 2. 현재까지 완료한 마일스톤

### 마일스톤 1. CARLA 설치 및 실행

- Windows 환경에서 CARLA 0.9.15 설치
- DirectX Runtime 오류 해결
- `CarlaUE4.exe` 정상 실행 확인

### 마일스톤 2. Python API 연결

- Python 3.7 환경에서 CARLA API 연결 성공
- `test_connection.py`로 서버 접속 확인
- CARLA 0.9.15와 Python 3.7 조합이 안정적임을 확인

### 마일스톤 3. 첫 OpenDRIVE 로딩

- `opendrive_writer.py`로 직선 `.xodr` 생성
- `load_xodr_in_carla.py`로 CARLA 로드 성공
- 빈 공간 위에 도로만 생성되는 최소 맵 검증 완료

### 마일스톤 4. 차량 spawn 및 autopilot 주행

- `test_spawn_vehicle.py`로 차량 생성 확인
- autopilot 주행 확인

### 마일스톤 5. 통합 검증 자동화

- `run_first_validation.py` 추가
- 맵 생성 -> 로드 -> 주행 -> 결과 저장을 한 번에 실행 가능
- 결과 JSON 저장 구조 확보

### 마일스톤 6. 직선 + 곡선 맵 확장

- `line + arc` 구조의 OpenDRIVE 생성 성공
- 단일 곡선 코스 로드 및 주행 성공

### 마일스톤 7. 첫 번째 완성형 맵 확보

- `stadium-track` 모드 추가
- 경기장형 oval track 생성 성공
- CARLA 로드 및 autopilot 검증 성공
- `collision_count = 0` 결과 확보

## 3. 현재 사용 중인 핵심 스크립트

### 맵 생성

- `scripts/map_generator/opendrive_writer.py`
- `scripts/map_generator/level_generator.py`

### CARLA 실행 및 검증

- `scripts/carla_runner/test_connection.py`
- `scripts/carla_runner/load_xodr_in_carla.py`
- `scripts/carla_runner/test_spawn_vehicle.py`
- `scripts/carla_runner/run_first_validation.py`
- `scripts/carla_runner/run_stadium_track_demo.py`
- `scripts/carla_runner/vehicle_utils.py`

### 평가 및 난이도

- `scripts/evaluation/result_models.py`
- `scripts/curriculum/difficulty_controller.py`

## 4. 현재 확보된 문서/자료

### 진행 기록 문서

- `2026-03-23_carla_install_and_first_xodr_load.md`
- `2026-03-23_integrated_first_validation_run.md`
- `2026-03-23_straight_plus_curve_validation.md`
- `2026-03-23_stadium_track_milestone.md`
- `2026-03-23_stadium_track_autopilot_demo.md`

### 보고서용 보조 문서

- `docs/report_notes/vehicle_autopilot_test_setup.md`

### 스크린샷

- `docs/screenshots/2026-03-23/2026-03-23_01_carla_launch_success.png`
- `docs/screenshots/2026-03-23/2026-03-23_02_opendrive_map_loaded.png`
- `docs/screenshots/2026-03-23/2026-03-23_03_single_curve_close_view.png`
- `docs/screenshots/2026-03-23/2026-03-23_04_single_curve_map_loaded.png`
- `docs/screenshots/2026-03-23/2026-03-23_05_stadium_track_map_loaded.png`

## 5. 현재 프로젝트 상태

현재 프로젝트는 `아이디어 검토 단계`를 넘어서, `실제로 동작하는 OpenDRIVE 기반 코스 생성 시스템의 초기 버전`을 확보한 상태다.

특히 아래가 중요하다.

- CARLA 연결이 이미 검증되었다.
- 직접 생성한 `.xodr`를 CARLA가 실제로 받아들인다.
- 차량이 생성된 맵 위에서 주행 가능하다.
- 결과가 JSON으로 저장된다.
- 직선 테스트 맵이 아니라 첫 완성형 트랙 맵까지 확보했다.

추가로, 현재 주행 검증은 `CARLA 기본 차량 blueprint`와 `CARLA 내장 autopilot`을 사용해 수행하고 있다. 이는 자율주행 제어 알고리즘 개발이 본 프로젝트의 핵심 범위가 아니기 때문이며, 생성한 맵의 주행 가능성을 빠르게 검증하기 위한 보조 수단으로 정리할 수 있다.

즉, 프로젝트는 이제 `가능한가?`를 묻는 단계가 아니라, `평가 시스템과 실험 구조를 어떻게 붙일 것인가?`를 다루는 단계로 넘어갔다.

## 6. 다음 우선순위

1. stadium track을 기준으로 평가 지표를 더 실제적으로 다듬기
2. offroad_ratio 계산 로직 추가
3. 좌/우 방향 트랙과 반경/직선 길이 조절 실험
4. 반복 실험 러너 개선
5. 이후 난이도(level)와 커리큘럼 로직을 실험 루프에 연결

## 7. 한 줄 요약

현재까지의 가장 큰 성과는 `CARLA에서 주행 가능한 첫 번째 완성형 OpenDRIVE 경기장 트랙 맵을 직접 생성하고 검증한 것`이다.
