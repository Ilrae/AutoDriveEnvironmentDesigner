# 2026-03-23 Stadium Track PID Follow Demo

## 1. 작업 목적

경기장 형태의 OpenDRIVE 트랙 위에서 차량이 화면에 계속 보이는 상태로 천천히 주행하는 데모를 만드는 것을 목표로 하였다.

이번 단계의 목적은 자율주행 알고리즘 자체를 연구하는 것이 아니라, 생성한 맵이 실제 주행 가능한 환경인지 시각적으로 확인할 수 있는 보조 데모 환경을 만드는 것이다.

## 2. 문제 상황

초기에는 `run_stadium_track_demo.py`에서 CARLA 내장 autopilot 또는 매우 단순한 waypoint loop steering 로직을 사용하였다.

이 방식에서는 다음 문제가 관찰되었다.

- 차량이 잠깐 보였다가 화면에서 사라짐
- spectator 시점에서는 차량이 너무 멀어 잘 보이지 않음
- 차량이 트랙 중심을 따라가기보다 벽을 비비면서 이동함

즉, "움직이기는 하지만 안정적인 트랙 추종 데모"라고 보기 어려운 상태였다.

## 3. 적용한 개선

`scripts/carla_runner/run_stadium_track_demo.py`를 수정하여 waypoint loop 모드에서 직접 계산한 단순 steering 대신, CARLA PythonAPI에 포함된 `VehiclePIDController`를 사용하도록 변경하였다.

적용 내용은 다음과 같다.

- `follow` spectator 카메라 모드 유지
- sampled waypoint route를 기준으로 nearest waypoint를 계속 다시 계산
- nearest waypoint보다 몇 개 앞선 target waypoint를 lookahead target으로 선택
- CARLA `VehiclePIDController`로 조향 및 속도 제어 수행
- 기본 loop 주행 속도를 낮춰 느리고 안정적인 데모에 맞춤

## 4. 현재 데모 제어 방식

현재 `run_stadium_track_demo.py`는 세 가지 모드를 지원한다.

- `autopilot`: CARLA built-in autopilot
- `basic-agent`: CARLA BasicAgent
- `waypoint-loop`: CARLA PID 기반 waypoint loop 추종 데모

이 중 경기장형 standalone OpenDRIVE 트랙에서 가장 안정적으로 보조 데모를 수행하는 모드는 현재 `waypoint-loop`이다.

## 5. 실행 예시

```powershell
cd C:\Users\user\Documents\Codex_Workspace\AutoDriveEnvironmentDesigner
py -3.7 scripts\carla_runner\run_stadium_track_demo.py --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor --map-id stadium_demo_pid_loop --level 0.30 --curve-direction left --duration-seconds 20 --camera-mode follow --follow-distance 12 --follow-height 4 --follow-pitch -12 --keep-vehicle --driver-mode waypoint-loop
```

## 6. 확인 결과

수정 후에는 다음을 확인하였다.

- 차량이 트랙 위에 정상 spawn 됨
- follow camera 상태에서 차량을 계속 관찰 가능
- 데모 종료 후에도 `--keep-vehicle` 옵션으로 차량을 남겨둘 수 있음
- 기존의 단순 steering 방식보다 트랙 중심을 더 잘 따라가는 방향으로 개선됨

다만 이 기능은 본 프로젝트의 핵심 산출물이 아니라, 생성된 맵을 시각적으로 검증하기 위한 보조 데모 기능으로 위치시킨다.

## 7. 보고서에 적을 때의 정리

보고서에서는 다음과 같이 구분하는 것이 자연스럽다.

- 생성 맵의 기본 주행 가능 여부 검증: CARLA built-in vehicle + CARLA built-in autopilot 사용
- 경기장형 트랙의 연속 시각 데모: CARLA PythonAPI의 PID 기반 waypoint 추종 보조 스크립트 사용

즉, 차량 제어 알고리즘 자체는 본 프로젝트의 연구 주제가 아니며, 맵 생성 결과를 확인하기 위한 side 검증 구성으로 정리한다.
