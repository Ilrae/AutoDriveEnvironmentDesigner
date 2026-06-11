# 차량 수동 주행 테스트 구성 정리

## 1. 문서 목적

이 문서는 생성한 OpenDRIVE 트랙을 사람이 직접 주행하여 검증하는 시연 절차를 정리하기 위한 보조 문서이다.

본 프로젝트의 핵심은 자율주행 알고리즘 구현이 아니라, 주행 환경과 코스를 자동 생성하고 그 결과를 평가할 수 있는 구조를 만드는 데 있다. 따라서 차량 제어는 CARLA에서 제공하는 기본 수동 주행 기능을 활용하는 것이 프로젝트 목적에 더 적합하다.

## 2. 사용 방식

수동 주행 테스트는 다음 구조로 진행한다.

- 프로젝트 스크립트가 custom OpenDRIVE 트랙을 생성하고 CARLA에 로드한다.
- 이후 CARLA에서 제공하는 기본 예제 `manual_control.py`를 실행한다.
- 사용자는 키보드로 직접 차량을 조작하며 트랙을 주행한다.

즉, 맵 생성과 로딩은 본 프로젝트가 담당하고, 실제 조작은 CARLA 기본 기능을 사용하는 구조이다.

## 3. 사용 스크립트

- `scripts/carla_runner/launch_manual_drive_demo.py`
- `C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor\PythonAPI\examples\manual_control.py`

`launch_manual_drive_demo.py`는 다음을 한 번에 수행한다.

1. stadium 형태의 custom track 생성
2. OpenDRIVE 맵을 CARLA에 로드
3. CARLA 기본 `manual_control.py` 실행

## 4. 실행 명령

```powershell
cd C:\Users\user\Documents\Codex_Workspace\AutoDriveEnvironmentDesigner
py -3.7 scripts\carla_runner\launch_manual_drive_demo.py --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor --map-id manual_drive_demo_live --level 0.30 --curve-direction left
```

## 5. 조작 키

CARLA 기본 `manual_control.py` 기준 조작은 다음과 같다.

- `W`: 가속
- `S`: 브레이크
- `A`, `D`: 좌우 조향
- `Q`: 후진 전환
- `Space`: 핸드브레이크
- `P`: autopilot 토글
- `ESC`: 종료

즉, 수동 주행 시연에서는 사용자가 직접 차량을 몰며 코스의 난이도와 주행 가능성을 확인할 수 있다.

## 6. 보고서에 적을 수 있는 설명

본 프로젝트는 자율주행 제어 알고리즘 자체를 구현하는 것을 목표로 하지 않는다. 따라서 생성한 OpenDRIVE 맵의 주행 가능 여부 및 코스 특성을 검증하기 위해 CARLA에서 제공하는 기본 수동 주행 기능을 사용하였다. 맵 생성 및 로딩은 프로젝트에서 수행하고, 차량 제어는 CARLA 기본 도구를 활용함으로써 프로젝트의 범위를 환경 생성과 평가 구조에 집중하였다.
