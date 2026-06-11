# 직선 + 곡선 OpenDRIVE 검증 기록

## 1. 작업 목적

이번 작업의 목적은 기존 `직선 도로만 생성하던 OpenDRIVE 생성기`를 확장해서, `직선 뒤에 곡선 1개가 붙는 코스`도 생성하고 CARLA에서 실제로 로드 및 주행 가능한지 검증하는 것이다.

이번 단계에서 확인하려고 한 핵심은 아래와 같다.

- `.xodr` 안에 `line`과 `arc` geometry를 함께 생성할 수 있는가
- CARLA가 해당 `.xodr`를 `OpenDriveMap`으로 정상 로드하는가
- 곡선이 포함된 맵에서도 차량 spawn과 autopilot 주행이 가능한가

## 2. 수정한 코드

### 2-1. OpenDRIVE 생성기 확장

수정 파일:

- `scripts/map_generator/opendrive_writer.py`

추가한 내용:

- `RoadGeometrySegment` 데이터 구조 추가
- `line`과 `arc` geometry를 순서대로 생성하는 planView 작성 로직 추가
- `--curve-length` 옵션 추가
- `--curve-curvature` 옵션 추가

즉, 이제 같은 생성기에서 아래 두 가지를 모두 만들 수 있다.

- 직선만 있는 도로
- 직선 + 곡선 1개가 있는 도로

### 2-2. level 기반 생성기 확장

수정 파일:

- `scripts/map_generator/level_generator.py`

추가한 내용:

- `--include-curve`
- `--curve-direction {left,right}`
- level 값으로 곡선 길이와 곡률을 계산하는 로직
- manifest에 `shape_type`, `curve_length`, `curve_curvature`, `total_length` 기록

### 2-3. 통합 검증 러너 확장

수정 파일:

- `scripts/carla_runner/run_first_validation.py`

추가한 내용:

- 곡선 포함 맵 생성 옵션 전달
- 검증 결과 metadata에 `include_curve`, `curve_direction` 기록

## 3. 실행한 명령

### 3-1. 직접 곡선 포함 `.xodr` 생성

```powershell
cd C:\Users\user\Documents\Codex_Workspace\AutoDriveEnvironmentDesigner
py -3.7 scripts\map_generator\opendrive_writer.py --output maps\generated\straight_arc_test_001.xodr --road-name straight_arc_test_001 --road-length 80 --curve-length 30 --curve-curvature 0.015
```

### 3-2. level 기반 곡선 맵 생성

```powershell
py -3.7 scripts\map_generator\level_generator.py --map-id level_curve_case_001 --level 0.45 --include-curve --curve-direction right
```

### 3-3. 곡선 포함 `.xodr` CARLA 로드

```powershell
py -3.7 scripts\carla_runner\load_xodr_in_carla.py --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor --xodr-path maps\generated\straight_arc_test_001.xodr
```

### 3-4. 곡선 포함 맵 통합 검증

```powershell
py -3.7 scripts\carla_runner\run_first_validation.py --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor --map-id validation_curve_case_001 --level 0.45 --include-curve --curve-direction right --duration-seconds 5
```

## 4. 확인한 결과

### 4-1. 생성된 `.xodr` 구조

생성된 `maps/generated/straight_arc_test_001.xodr` 파일 안에서 아래 구조를 확인했다.

```xml
<geometry hdg="0.000000" length="80.000000" s="0.000000" x="0.000000" y="0.000000">
  <line/>
</geometry>
<geometry hdg="0.000000" length="30.000000" s="80.000000" x="80.000000" y="0.000000">
  <arc curvature="0.015000"/>
</geometry>
```

즉, 직선 뒤에 곡선 geometry가 정상적으로 이어지는 최소 OpenDRIVE 구조가 만들어졌다.

### 4-2. CARLA 로드 결과

로드 결과:

- OpenDRIVE world loaded successfully.
- Current map: `Carla/Maps/OpenDriveMap`
- Spawn point count: `1`

즉, 곡선이 포함된 `.xodr`도 CARLA가 정상적으로 받아들였다.

### 4-3. 차량 주행 결과

통합 검증 결과:

- 차량 spawn 성공
- autopilot 활성화 성공
- 5초 동안 주행 성공
- 결과 JSON 저장 성공

결과 파일:

- `experiments/validation_curve_case_001.json`
- `results/validation_curve_case_001_validation.json`

결과 JSON 기준 주요 값:

- `map_id`: `validation_curve_case_001`
- `include_curve`: `true`
- `curve_direction`: `right`
- `collision_count`: `2`
- `loaded_map`: `Carla/Maps/OpenDriveMap`

## 5. 해석

이번 작업으로 아래 사항을 검증했다.

- 프로젝트가 더 이상 `직선 도로만 가능한 상태`가 아니다.
- `직선 + 곡선 1개` 수준의 단순 코스는 현재 구조로 충분히 자동 생성 가능하다.
- CARLA standalone OpenDRIVE 방식으로 곡선 코스도 실제 로드와 주행이 가능하다.

즉, 졸업작품 1단계 목표인 `텅 빈 맵 위에 도로 코스를 자동 생성하고 주행 가능한 환경으로 만드는 것`은 직선뿐 아니라 간단한 곡선 코스까지 확장 가능한 상태가 되었다.

## 6. 남은 과제

- 곡선 길이와 곡률의 안전 범위를 더 체계적으로 정리하기
- 좌회전/우회전 샘플을 각각 저장하기
- offroad_ratio 계산 로직 추가하기
- collision 판정 기준을 조금 더 안정화하기
- 여러 곡선 세기에서 반복 검증하기
