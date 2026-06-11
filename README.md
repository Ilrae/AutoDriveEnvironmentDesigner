# AutoDrive Environment Designer

AutoDrive Environment Designer(AED)는 CARLA 기반 자율주행 검증 환경을 단계적으로 설계하고 반복 평가하기 위한 프로토타입입니다.  
핵심 목표는 자율주행 알고리즘 자체를 구현하는 것이 아니라, 다음과 같은 검증 루프를 하나의 앱으로 통합하는 것입니다.

`환경 생성 -> 맵/시나리오 로드 -> ego vehicle 스폰 -> 주행 -> 평가 -> 결과 저장 -> 다음 환경 생성`

현재 프로젝트는 다음 3단계 구조를 지원합니다.

- `Track Stage`
  - generated OpenDRIVE 트랙 생성
  - finish-line 기반 수동 주행 평가
  - 결과 기반 다음 트랙 자동 생성
- `Intermediate Road Stage`
  - road-like generated OpenDRIVE 코스 생성
  - lane-oriented 평가
  - 더 긴 도로형 코스 반복 검증
- `Practical Road Stage`
  - CARLA 기본 Town 기반 시나리오 생성
  - route / traffic / pedestrian baseline
  - 목적지 도달 기반 평가와 다음 시나리오 적응

즉 AED는 단순한 CARLA 데모가 아니라, **자율주행 검증 환경을 자동으로 설계하고 반복 평가하는 오케스트레이터**를 지향합니다.

## Latest Release

최신 Windows 배포본은 GitHub Releases에서 받을 수 있습니다.

- 최신 릴리스: [AutoDrive Environment Designer v0.2.0](https://github.com/Ilrae/Codex_Workspace/releases/tag/autodrive-environment-designer-v0.2.0)
- 제공 자산
  - `Windows Setup`
  - `Windows Portable ZIP`

## Current Prototype Status

현재 기준으로 다음 기능이 동작합니다.

- Track / Intermediate / Practical 3단계 GUI 제어
- OpenDRIVE 맵 생성 및 CARLA 로드
- Town 기반 Practical scenario 생성 및 실행
- ego vehicle / background traffic / pedestrian baseline 스폰
- finish-line / destination 기반 점수 계산
- 결과 JSON 저장 및 다음 환경 자동 적응
- 결과 비교 패널과 다음 조정 미리보기 패널
- 사용자 vehicle config / driver module / external command 연동 baseline
- Windows 실행 파일 / 설치 파일 / GitHub release 자산 배포

즉, **졸업작품 시연이 가능한 프로토타입 baseline**은 확보된 상태입니다.

## Validation Flow

### 1. Track Stage

- 결과가 없으면 seed map부터 시작
- generated XODR를 CARLA에 로드
- ego vehicle 수동 주행
- finish line 통과 후 점수 계산
- 결과를 다음 맵 생성 입력으로 재사용

### 2. Intermediate Road Stage

- Track보다 긴 road-like generated 코스 생성
- lane-centered guidance 기반으로 주행 평가
- lane discipline / wrong-lane / offroad를 더 엄격하게 반영

### 3. Practical Road Stage

- Town / Weather / Traffic / Route preset 선택
- 필요하면 일부 항목만 custom override
- Town 기반 scenario 생성 후 실행
- destination 도달 후 goal score 계산
- 결과를 다음 Town scenario 적응 입력으로 재사용

## Vehicle / Driver Integration

현재 앱은 기본 내장 차량 + 수동 주행을 기본값으로 사용하지만, 사용자가 별도 차량/주행 로직을 연결할 수 있는 baseline도 포함합니다.

- `Vehicle Config File`
  - CARLA blueprint id, color, role_name 등을 JSON으로 지정
- `Driver Module File`
  - Python 파일을 불러와 키맵 또는 제어 로직을 교체
- `External Launch Command`
  - ROS bridge 또는 외부 자율주행 실행 스택을 명령 기반으로 시작

동작 방식:

- 차량 설정만 넣으면 차량만 override
- driver module만 넣으면 주행 로직만 override
- 둘 다 넣으면 함께 적용
- 지정하지 않은 항목은 built-in 기본값 유지

예제 파일:

- [examples/integration/sample_vehicle_blue_charger.json](./examples/integration/sample_vehicle_blue_charger.json)
- [examples/integration/sample_vehicle_tesla_blue.json](./examples/integration/sample_vehicle_tesla_blue.json)
- [examples/integration/sample_driver_uhjk.py](./examples/integration/sample_driver_uhjk.py)

## Post-Run Review

Track/Intermediate finish 이후, Practical goal 이후에는 결과 카드 외에 다음 두 개의 리뷰 패널을 볼 수 있습니다.

- `1`: 최근 결과 비교표
  - score, completion, collision, offroad, lane, wrong-lane, outcome 비교
- `2`: 다음 조정 미리보기
  - Track/Intermediate의 난이도 조정 방향
  - Practical의 traffic / pedestrian / route / junction_focus 조정 방향

즉 사용자는 점수를 확인하는 데서 끝나지 않고, **다음 환경이 왜 그렇게 바뀌는지**를 바로 확인할 수 있습니다.

## Practical Override Policy

Practical Stage는 `자동 적응`과 `사용자 지정 override`를 함께 지원합니다.

- 사용자가 설정창에서 직접 넣은 값
  - 해당 필드는 강제로 반영
- 비워 둔 값
  - 이전 결과 기반 자동 적응 유지

예를 들면:

- `vehicle_count`만 직접 지정
- `route_length`만 직접 고정
- `junction_focus`만 수동 지정
- 나머지는 자동 적응 유지

이 구조 덕분에 Practical Stage는 완전 자동 모드와 부분 수동 제어 모드를 동시에 제공합니다.

## First-Run Behavior

첫 실행에서도 바로 사용할 수 있도록 fallback을 넣었습니다.

- Track Stage
  - 결과 JSON이 하나도 없으면 seed map 자동 생성
- Practical Stage
  - scenario file이 비어 있어도 baseline scenario를 자동 생성 후 실행

즉 빈 작업공간에서도 바로 시연 흐름을 시작할 수 있습니다.

## Recommended Environment

- `CARLA 0.9.15`
- `Python 3.7`
- `Windows 10 / 11`

소스 코드로 실행할 때는 Python 3.7 환경이 필요합니다.  
설치형/포터블 배포본은 Python 설치 없이 실행 가능하지만, **CARLA 설치와 PythonAPI 경로 지정은 필요합니다.**

## Quick Start

### 1. CARLA 실행

먼저 CARLA 서버를 실행합니다.

- 기본 주소: `localhost:2000`

### 2. AED 실행

다음 중 하나로 AED를 실행합니다.

- 소스 실행
  - `py -3.7 scripts\app\gui.py --pythonapi-path <CARLA 경로>`
- 설치형 실행
  - Setup으로 설치 후 앱 실행
- 포터블 실행
  - ZIP 압축 해제 후 `AutoDriveEnvironmentDesigner.exe` 실행

### 3. PythonAPI 경로 설정

앱 상단의 `PythonAPI` 항목에 CARLA 설치 경로를 지정합니다.

예시:

- `C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor`

### 4. Stage 선택

왼쪽 `Progression Stage`에서 사용할 검증 단계를 선택합니다.

- `Track Driving Stage`
- `Intermediate Road Stage`
- `Practical Road Stage`

### 5. 단계별 실행

#### Track Stage

1. `Generate + Drive Next Map` 또는 `Run Selected XODR`
2. finish line 통과
3. 점수 카드 및 리뷰 패널 확인
4. 결과 기반 다음 맵 생성

#### Intermediate Stage

1. road-like 코스 생성
2. lane 중심으로 주행
3. finish line 통과 후 lane-oriented 평가 확인

#### Practical Stage

1. `Town / Weather / Traffic / Route` 설정
2. 필요하면 `Open Custom Scenario Settings`
3. `Generate Practical Scenario` 또는 `Run Practical Scenario`
4. destination 도달 후 점수 카드와 리뷰 패널 확인

## Runtime Workspace

실행 방식에 따라 결과 저장 위치가 달라집니다.

### Source Mode

소스 실행 시 저장소 내부 폴더를 사용합니다.

- `maps/generated/`
- `experiments/`
- `results/manual_sequence/`
- `results/practical/`
- `scenarios/practical/`

### Packaged Mode

설치형/포터블 실행 시 사용자 문서 폴더 아래 별도 런타임 작업공간을 사용합니다.

- `C:\Users\<USER>\Documents\AutoDriveEnvironmentDesignerRuntime`

주요 하위 폴더:

- `maps/generated/`
- `experiments/`
- `experiments/practical/`
- `results/manual_sequence/`
- `results/practical/`
- `scenarios/practical/`

이 구조는 설치 폴더를 깨끗하게 유지하면서도 결과 파일을 안전하게 저장하기 위한 방식입니다.

## Repository Structure

```text
AutoDriveEnvironmentDesigner/
├─ docs/
│  ├─ progress_notes/
│  ├─ report_notes/
│  └─ screenshots/
├─ examples/
│  └─ integration/
├─ experiments/
├─ maps/
│  └─ generated/
├─ packaging/
│  └─ windows/
├─ results/
│  ├─ manual_sequence/
│  └─ practical/
├─ scenarios/
│  └─ practical/
└─ scripts/
   ├─ app/
   ├─ carla_runner/
   ├─ evaluation/
   └─ map_generator/
```

## Important Files

### App / GUI

- [scripts/app/gui.py](./scripts/app/gui.py)
  - tkinter 기반 메인 제어 패널
- [scripts/app/launcher.py](./scripts/app/launcher.py)
  - GUI와 각 실행 루틴을 연결하는 진입점
- [scripts/app/auto_generation.py](./scripts/app/auto_generation.py)
  - Track / Intermediate 결과 기반 다음 맵 생성
- [scripts/app/practical_stage.py](./scripts/app/practical_stage.py)
  - Practical preset 및 override 해석
- [scripts/app/practical_scenario_generation.py](./scripts/app/practical_scenario_generation.py)
  - Town 기반 scenario JSON / manifest 생성

### CARLA Runtime

- [scripts/carla_runner/run_manual_xodr_demo.py](./scripts/carla_runner/run_manual_xodr_demo.py)
  - Track / Intermediate 주행 및 평가
- [scripts/carla_runner/run_practical_scenario_demo.py](./scripts/carla_runner/run_practical_scenario_demo.py)
  - Practical Town scenario 실행 및 평가
- [scripts/carla_runner/load_xodr_in_carla.py](./scripts/carla_runner/load_xodr_in_carla.py)
  - generated OpenDRIVE 맵 로드
- [scripts/carla_runner/load_town_in_carla.py](./scripts/carla_runner/load_town_in_carla.py)
  - CARLA Town 로드
- [scripts/carla_runner/vehicle_utils.py](./scripts/carla_runner/vehicle_utils.py)
  - ego / traffic / pedestrian spawn
- [scripts/carla_runner/integration_loader.py](./scripts/carla_runner/integration_loader.py)
  - vehicle config / driver module 로딩
- [scripts/carla_runner/external_driver_runtime.py](./scripts/carla_runner/external_driver_runtime.py)
  - external command 실행과 종료 lifecycle
- [scripts/carla_runner/post_run_review.py](./scripts/carla_runner/post_run_review.py)
  - 결과 비교표와 다음 조정 미리보기 패널 생성

### Map Generation

- [scripts/map_generator/level_generator.py](./scripts/map_generator/level_generator.py)
  - generated OpenDRIVE 생성 핵심
- [scripts/map_generator/course_composer.py](./scripts/map_generator/course_composer.py)
  - segment 조합 기반 코스 생성
- [scripts/map_generator/course_stages.py](./scripts/map_generator/course_stages.py)
  - stage별 길이/곡선/recovery 규칙
- [scripts/map_generator/course_validation.py](./scripts/map_generator/course_validation.py)
  - 이상 레이아웃 검증
- [scripts/map_generator/track_contract.py](./scripts/map_generator/track_contract.py)
  - spawn / finish 계약 정의

### Evaluation

- [scripts/evaluation/path_metrics.py](./scripts/evaluation/path_metrics.py)
  - path, lane, offroad, completion 계산
- [scripts/evaluation/scoring.py](./scripts/evaluation/scoring.py)
  - 실사용 점수 계산
- [scripts/evaluation/result_models.py](./scripts/evaluation/result_models.py)
  - 결과 JSON 저장/로딩 모델
- [scripts/evaluation/target_modes.py](./scripts/evaluation/target_modes.py)
  - 단계별 평가 타깃 모드

### Windows Packaging

- [packaging/windows/AutoDriveEnvironmentDesigner.spec](./packaging/windows/AutoDriveEnvironmentDesigner.spec)
  - PyInstaller 빌드 설정
- [packaging/windows/AutoDriveEnvironmentDesigner.iss](./packaging/windows/AutoDriveEnvironmentDesigner.iss)
  - Inno Setup 설치 파일 스크립트
- [packaging/windows/build_windows_bundle.ps1](./packaging/windows/build_windows_bundle.ps1)
  - exe / setup 빌드
- [packaging/windows/build_windows_release_assets.ps1](./packaging/windows/build_windows_release_assets.ps1)
  - release 업로드용 setup / portable zip 생성

## Windows Release Assets

배포 파일은 GitHub Releases에서 받을 수 있습니다.

- [GitHub Releases](https://github.com/Ilrae/Codex_Workspace/releases)
- 최신 배포본: [AutoDrive Environment Designer v0.2.0](https://github.com/Ilrae/Codex_Workspace/releases/tag/autodrive-environment-designer-v0.2.0)

릴리스 자산 구성:

- `Windows Setup`
  - 설치형 배포본
- `Windows Portable ZIP`
  - 압축 해제 후 바로 실행 가능한 포터블 배포본

## Limitations

현재 버전은 시연 가능한 프로토타입이지만, 다음 한계가 남아 있습니다.

- Practical Stage 목적지 안내 UI는 더 개선 가능
- 외부 자율주행 코드 / ROS bridge 연동은 baseline 단계
- Intermediate / Practical 적응 규칙은 더 정교화 가능
- pedestrian 및 richer scenario augmentation은 baseline 수준

## Related Documents

주요 진행 메모:

- [docs/progress_notes/2026-04-07_next_feature_todo_ko.md](./docs/progress_notes/2026-04-07_next_feature_todo_ko.md)
- [docs/progress_notes/2026-04-02_windows_packaging_baseline_ko.md](./docs/progress_notes/2026-04-02_windows_packaging_baseline_ko.md)
- [docs/progress_notes/2026-04-01_stage_quickstart_ko.md](./docs/progress_notes/2026-04-01_stage_quickstart_ko.md)
- [docs/progress_notes/2026-04-01_prototype_completion_checklist_ko.md](./docs/progress_notes/2026-04-01_prototype_completion_checklist_ko.md)
- [docs/progress_notes/2026-03-27_practical_stage_runtime_baseline_ko.md](./docs/progress_notes/2026-03-27_practical_stage_runtime_baseline_ko.md)
- [docs/report_notes/2026-04-01_final_report_draft.md](./docs/report_notes/2026-04-01_final_report_draft.md)

## Notes

- Track / Intermediate는 generated OpenDRIVE 기반입니다.
- Practical는 generated map이 아니라 **CARLA 기본 Town 기반 scenario generation** 구조입니다.
- Track의 비정상 근접 레이아웃은 validation으로 걸러지도록 보강했습니다.
- 결과 저장뿐 아니라, 저장된 결과를 다음 환경 설계 규칙의 입력으로 다시 사용합니다.
