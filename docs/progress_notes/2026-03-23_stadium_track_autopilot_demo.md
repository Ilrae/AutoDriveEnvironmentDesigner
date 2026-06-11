# 경기장 트랙 자동차 자동주행 데모 기록

## 1. 작업 목적

이번 작업의 목적은 생성한 경기장형 OpenDRIVE 트랙 위에 실제 차량을 올리고, CARLA 내장 autopilot으로 주행이 가능한지 확인하는 것이다.

이 단계는 자율주행 제어 알고리즘을 직접 구현하기 위한 것이 아니라, 생성한 트랙이 실제 주행 검증에 사용할 수 있는 환경인지 확인하기 위한 보조 검증 단계로 진행했다.

## 2. 사용 방식

이번 데모에서는 아래 요소를 사용하였다.

- CARLA 기본 제공 차량 blueprint
- CARLA 내장 autopilot 기능

즉, 별도의 사용자 정의 자율주행 알고리즘은 사용하지 않았다.

## 3. 사용 스크립트

- `scripts/carla_runner/run_stadium_track_demo.py`

이 스크립트는 아래 순서를 한 번에 수행한다.

1. stadium track 생성
2. CARLA에 `.xodr` 로드
3. 차량 spawn
4. CARLA 내장 autopilot 활성화
5. 일정 시간 주행

## 4. 실행 명령

```powershell
cd C:\Users\user\Documents\Codex_Workspace\AutoDriveEnvironmentDesigner
py -3.7 scripts\carla_runner\run_stadium_track_demo.py --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor --map-id stadium_demo_001 --level 0.30 --curve-direction left --duration-seconds 10
```

## 5. 실행 결과

주요 출력:

```text
Stadium track demo vehicle spawned and autopilot enabled.
Map id: stadium_demo_001
Generated xodr: maps\generated\stadium_demo_001.xodr
Manifest: experiments\stadium_demo_001.json
Loaded map: Carla/Maps/OpenDriveMap
Blueprint: vehicle.dodge.charger_2020
Duration: 10.0 seconds
Vehicle control mode: CARLA built-in autopilot
```

즉, 생성된 stadium track 위에 CARLA 기본 차량이 정상적으로 생성되었고, CARLA 내장 autopilot을 이용해 자동 주행이 수행되었다.

## 6. 의미

이번 데모는 아래 사실을 보여준다.

- 생성한 경기장 트랙은 단순히 로드만 되는 것이 아니라 실제 주행 가능한 환경이다.
- 차량 제어를 별도로 구현하지 않더라도 CARLA 기본 기능으로 맵 검증이 가능하다.
- 본 프로젝트에서는 차량 제어 자체보다 맵 생성과 실험 환경 구성이 핵심이라는 점을 분명히 할 수 있다.

## 7. 보고서에 쓸 수 있는 설명

본 프로젝트에서는 자율주행 제어 알고리즘 자체를 구현하지 않고, CARLA에서 기본 제공하는 차량과 autopilot 기능을 사용하여 생성된 OpenDRIVE 트랙의 주행 가능 여부를 검증하였다.

## 8. 관련 문서

- `docs/report_notes/vehicle_autopilot_test_setup.md`
- `docs/progress_notes/2026-03-23_stadium_track_milestone.md`
- `docs/progress_notes/2026-03-23_project_progress_summary.md`
