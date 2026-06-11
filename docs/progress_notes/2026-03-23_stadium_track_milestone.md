# 경기장 트랙(OpenDRIVE Oval Track) 마일스톤 기록

## 1. 작업 목적

이번 작업의 목적은 기존 `직선` 또는 `직선 + 곡선 1개` 수준의 테스트 맵을 넘어서, 첫 번째 완성형 맵으로 사용할 수 있는 `경기장형 oval track`을 만드는 것이다.

목표는 아래와 같았다.

- 직선 2개와 반원 곡선 2개로 이루어진 폐곡선 트랙 생성
- CARLA에서 해당 `.xodr`를 정상 로드
- 차량 spawn 및 autopilot 주행 검증
- 결과 JSON 저장까지 한 번에 확인

## 2. 구현 내용

수정 파일:

- `scripts/map_generator/opendrive_writer.py`
- `scripts/map_generator/level_generator.py`
- `scripts/carla_runner/run_first_validation.py`

핵심 변경:

- `--stadium-track` 모드 추가
- `--track-radius` 파라미터 추가
- 경기장 트랙용 세그먼트 구성 추가
  - 직선
  - 반원 곡선
  - 직선
  - 반원 곡선
- level 기반 생성기와 통합 검증 러너에서도 동일한 트랙 모드 지원

## 3. 실행한 명령

### 3-1. 수동 트랙 생성

```powershell
cd C:\Users\user\Documents\Codex_Workspace\AutoDriveEnvironmentDesigner
py -3.7 scripts\map_generator\opendrive_writer.py --output maps\generated\stadium_track_test_001.xodr --road-name stadium_track_test_001 --stadium-track --road-length 220 --track-radius 70 --curve-direction left
```

### 3-2. 통합 검증

```powershell
py -3.7 scripts\carla_runner\run_first_validation.py --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor --map-id validation_stadium_track_001 --level 0.30 --stadium-track --curve-direction left --duration-seconds 8
```

## 4. 결과

### 4-1. 생성된 트랙 구조

생성된 트랙은 아래 구조를 가진다.

- 직선 1
- 반원 곡선 1
- 직선 2
- 반원 곡선 2

즉 `stadium` 또는 `oval` 트랙 형태의 폐곡선 코스가 완성되었다.

### 4-2. CARLA 검증 결과

검증 결과:

- OpenDRIVE world load 성공
- Current map: `Carla/Maps/OpenDriveMap`
- 차량 spawn 성공
- autopilot 주행 성공
- 결과 JSON 저장 성공

주요 결과 파일:

- `experiments/validation_stadium_track_001.json`
- `results/validation_stadium_track_001_validation.json`

핵심 수치:

- `shape_type`: `stadium_track_left`
- `segment_count`: `4`
- `total_length`: 약 `824.7 m`
- `success`: `true`
- `collision_count`: `0`

## 5. 스크린샷

관련 스크린샷:

- `docs/screenshots/2026-03-23/2026-03-23_05_stadium_track_map_loaded.png`

이 스크린샷은 경기장형 트랙이 CARLA에 정상 로드된 첫 완성형 맵 화면이다.

## 6. 결론

이번 단계로 프로젝트는 단순 로딩 테스트를 넘어서, `첫 번째 완성형 OpenDRIVE 맵`을 갖게 되었다.

의미는 아래와 같다.

- 졸업작품 1단계 목표를 더 설득력 있는 형태로 시연 가능
- 이후 평가기, 난이도 조절, 반복 실험 구조를 붙이기 좋은 기준 맵 확보
- 보고서와 발표 자료에 사용할 수 있는 시각적 결과 확보

## 7. 다음 작업

- 트랙 기반 실험 결과를 반복 저장하는 루프 강화
- offroad_ratio 계산 추가
- 좌/우 방향 트랙 비교
- 트랙 파라미터(직선 길이, 반경, 차선폭) 조절 실험
