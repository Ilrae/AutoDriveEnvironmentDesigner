# CARLA 설치 및 첫 OpenDRIVE 맵 로딩 기록

## 1. 작업 목적

이번 작업의 목적은 다음과 같다.

- Windows 환경에서 CARLA 0.9.15를 실행한다.
- Python API로 CARLA 서버와 연결한다.
- 코드로 생성한 OpenDRIVE(`.xodr`) 파일을 CARLA에 로드한다.
- 로드된 맵 위에 차량을 spawn 하고 autopilot 주행이 가능한지 확인한다.

이번 단계의 1차 마일스톤은 다음과 같이 정의하였다.

`직접 생성한 직선 도로 OpenDRIVE 파일을 CARLA에서 로드하고, 그 위에서 차량이 실제로 주행하도록 만드는 것`

## 2. 개발 환경

- 운영체제: Windows
- 시뮬레이터: CARLA 0.9.15
- CARLA 설치 경로: `C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor`
- 프로젝트 경로: `C:\Users\user\Documents\Codex_Workspace\AutoDriveEnvironmentDesigner`
- 사용 Python: `Python 3.7`

## 3. CARLA 설치 및 실행 과정

### 3-1. 설치

1. CARLA 0.9.15 Windows 패키지를 다운로드하였다.
2. 압축을 `C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor` 경로에 해제하였다.

### 3-2. 초기 실행 오류

최초 실행 시 다음 오류가 발생하였다.

- `DirectX Runtime`

이는 DirectX 12 자체가 없다는 의미보다는, CARLA 실행에 필요한 추가 DirectX Runtime 구성요소가 없어서 발생한 것으로 판단하였다.

### 3-3. 해결

- Microsoft DirectX End-User Runtime을 설치하였다.
- 이후 `CarlaUE4.exe`를 다시 실행하였다.

### 3-4. 실행 결과

CARLA 기본 도시 맵 화면이 정상적으로 표시되었다.

즉, `CARLA 설치 및 기본 실행` 단계는 성공하였다.

## 4. Python API 연결 과정

### 4-1. 환경 변수 설정

PowerShell에서 아래와 같이 프로젝트 폴더로 이동하고 CARLA 경로를 설정하였다.

```powershell
cd C:\Users\user\Documents\Codex_Workspace\AutoDriveEnvironmentDesigner
$env:CARLA_ROOT="C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor"
```

### 4-2. 초기 연결 문제

처음에는 아래와 같이 실행하였다.

```powershell
python scripts\carla_runner\test_connection.py
```

하지만 다음 오류가 발생하였다.

```text
Failed to connect to CARLA.
Reason: module 'carla' has no attribute 'Client'
```

원인 분석 결과:

- 시스템 기본 `python`은 Python 3.13이었다.
- CARLA 0.9.15 설치 폴더에는 `carla-0.9.15-py3.7-win-amd64.egg`가 포함되어 있었다.
- 즉, 현재 CARLA API는 Python 3.7 기준으로 맞춰서 사용하는 것이 적절했다.
- 또한 `carla` 모듈 import 시 egg 대신 namespace 패키지가 먼저 잡히는 문제가 있었다.

### 4-3. 해결

- 스크립트에서 CARLA API egg 파일이 우선 로드되도록 수정하였다.
- Python 3.7로 실행하도록 변경하였다.

실행 명령:

```powershell
py -3.7 scripts\carla_runner\test_connection.py
```

### 4-4. 연결 결과

다음과 같은 결과를 확인하였다.

```text
Connected to CARLA.
Host: localhost:2000
Client version: 0.9.15
Server version: 0.9.15
Current map: Carla/Maps/Town10HD_Opt
Spawn point count: 155
```

즉, `Python API 연결`은 성공하였다.

## 5. OpenDRIVE 맵 생성 과정

프로젝트 내의 OpenDRIVE 생성 스크립트를 사용하여 가장 단순한 직선 도로 맵을 생성하였다.

사용한 스크립트:

- `scripts/map_generator/opendrive_writer.py`

실행 명령:

```powershell
py -3.7 scripts\map_generator\opendrive_writer.py --output maps\generated\straight_road_draft.xodr
```

실행 결과:

```text
Wrote OpenDRIVE draft to: maps\generated\straight_road_draft.xodr
```

생성된 파일:

- `maps/generated/straight_road_draft.xodr`

이 파일은 최소 OpenDRIVE 구조를 가지는 직선 도로 1개짜리 테스트 맵이다.

## 6. OpenDRIVE 맵 로딩 과정

### 6-1. 사용 스크립트

- `scripts/carla_runner/load_xodr_in_carla.py`

### 6-2. 실행 명령

```powershell
py -3.7 scripts\carla_runner\load_xodr_in_carla.py --xodr-path maps\generated\straight_road_draft.xodr
```

### 6-3. 실행 결과

```text
OpenDRIVE world loaded successfully.
Source file: C:\Users\user\Documents\Codex_Workspace\AutoDriveEnvironmentDesigner\maps\generated\straight_road_draft.xodr
Host: localhost:2000
Client version: 0.9.15
Server version: 0.9.15
Current map: Carla/Maps/OpenDriveMap
Spawn point count: 1
Generation parameters: vertex_distance=2.0, max_road_length=50.0, wall_height=1.0, additional_width=0.6, smooth_junctions=True, mesh_visibility=True, reset_settings=True
```

### 6-4. 화면 결과

CARLA 화면에는 건물과 오브젝트가 없는 빈 공간 위에 직선 도로만 생성된 맵이 표시되었다.

관련 스크린샷:

- `docs/screenshots/2026-03-23/2026-03-23_01_carla_launch_success.png`
- `docs/screenshots/2026-03-23/2026-03-23_02_opendrive_map_loaded.png`

이 결과는 비정상이 아니라, 현재 목표가 `복잡한 도시 맵 생성`이 아니라 `텅 빈 환경에 도로 코스만 생성하는 것`이기 때문에 정상적인 결과이다.

즉, `직접 생성한 OpenDRIVE 맵을 CARLA에서 로드하는 것`은 성공하였다.

## 7. 차량 spawn 및 autopilot 주행 과정

### 7-1. 사용 스크립트

- `scripts/carla_runner/test_spawn_vehicle.py`

### 7-2. 실행 명령

```powershell
py -3.7 scripts\carla_runner\test_spawn_vehicle.py --duration-seconds 10
```

### 7-3. 실행 결과

```text
Vehicle spawned and autopilot enabled.
Blueprint: vehicle.dodge.charger_2020
Client version: 0.9.15
Server version: 0.9.15
Map: Carla/Maps/OpenDriveMap
Actor id: 25
Duration: 10.0 seconds
```

즉, OpenDRIVE 기반으로 생성된 단순 도로 맵 위에서 차량 spawn 과 autopilot 주행이 모두 가능함을 확인하였다.

## 8. 작업 중 발생한 오류 및 해결

### 오류 1. DirectX Runtime 오류

증상:

- CARLA 실행 시 `DirectX Runtime` 오류 발생

해결:

- Microsoft DirectX End-User Runtime 설치 후 재실행

### 오류 2. `module 'carla' has no attribute 'Client'`

증상:

- CARLA Python API 연결 시 `Client` 속성이 없다는 오류 발생

원인:

- egg가 아니라 잘못된 `carla` namespace 패키지가 먼저 import됨

해결:

- CARLA API egg 파일이 우선 로드되도록 스크립트 수정

### 오류 3. `dataclass() got an unexpected keyword argument 'slots'`

증상:

- Python 3.7 환경에서 dataclass 관련 오류 발생

원인:

- Python 3.7은 `dataclass(slots=True)`를 지원하지 않음

해결:

- 관련 코드에서 `slots=True` 제거

### 경고 1. `cannot parse georeference`

증상:

- OpenDRIVE 로드 시 georeference 관련 경고 표시

판단:

- 현재 단계의 단순 테스트에서는 치명적이지 않음
- 기본값으로 동작하며 맵 로딩과 주행은 정상 수행됨

### 경고 2. `No InMemoryMap cache found`

증상:

- 첫 주행 시 캐시 관련 경고 출력

판단:

- 내부 맵 캐시 생성 과정에서 발생하는 것으로 보임
- 차량 spawn 및 autopilot 주행에는 문제 없었음

## 9. 1차 마일스톤 결과

이번 단계에서 다음 항목을 모두 성공하였다.

- CARLA 설치 및 실행
- Python API 연결
- OpenDRIVE 파일 생성
- 생성한 `.xodr` 파일의 CARLA 로딩
- 로드된 맵 위 차량 spawn
- autopilot 기반 주행 확인

따라서 다음 질문에 대한 답은 `성공`이다.

`직접 생성한 OpenDRIVE 도로 코스를 CARLA에서 주행 가능한 맵으로 변환할 수 있는가?`

정답은 `예`이다.

## 10. 현재 단계에서의 의미

이번 결과는 프로젝트 아이디어의 핵심 기술 검증이 완료되었음을 의미한다.

즉, 프로젝트는 더 이상 `가능한가?`를 확인하는 단계가 아니라, 이제부터는 `맵 생성기를 어떻게 확장할 것인가?`를 고민하는 단계로 넘어간다.

현재까지의 결과를 통해 다음 방향이 현실적이라고 판단할 수 있다.

- 직선 도로를 여러 버전으로 생성
- 직선 + 곡선 조합 생성
- 결과 저장 로직 추가
- 이후 난이도 조절 및 커리큘럼 로직 연결

## 11. 다음 단계

다음으로 진행하기 좋은 작업은 아래와 같다.

1. 생성 -> 로드 -> 주행 -> 결과 저장까지 하나의 흐름으로 묶기
2. 직선만이 아니라 곡선 1개를 포함하는 OpenDRIVE 생성기로 확장하기
3. 주행 결과(JSON)를 저장하는 구조와 연결하기

현재 추천 우선순위는 다음과 같다.

1. `맵 생성 -> CARLA 로드 -> 차량 spawn -> 주행 -> 결과 저장` 통합
2. 직선 + 곡선 맵 생성기 확장
3. 최소 평가 지표 저장
