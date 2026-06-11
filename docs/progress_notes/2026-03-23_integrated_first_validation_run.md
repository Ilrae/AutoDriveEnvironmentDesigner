# 통합 검증 스크립트 실행 기록

## 1. 작업 목적

이번 작업의 목적은 기존에 수동으로 수행하던 다음 절차를 하나의 스크립트로 통합하는 것이었다.

- OpenDRIVE 맵 생성
- CARLA에 OpenDRIVE 맵 로드
- 차량 spawn
- autopilot 주행
- 결과 JSON 저장

즉, 프로젝트를 단순한 기능 데모가 아니라 `재현 가능한 1회 실험 흐름`으로 만드는 것이 목표였다.

## 2. 환경 정보

- 운영체제: Windows
- CARLA 버전: 0.9.15
- Python 버전: 3.7
- 프로젝트 경로: `C:\Users\user\Documents\Codex_Workspace\AutoDriveEnvironmentDesigner`
- CARLA 경로: `C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor`

## 3. 구현 내용

통합 검증용 스크립트:

- `scripts/carla_runner/run_first_validation.py`

이 스크립트는 아래 작업을 한 번에 수행한다.

1. `level` 값 기준으로 테스트용 OpenDRIVE 맵 생성
2. CARLA standalone OpenDRIVE world 로드
3. 차량 spawn 및 autopilot 활성화
4. 일정 시간 주행
5. 결과 JSON 저장

추가로 공통 차량 유틸을 분리하였다.

- `scripts/carla_runner/vehicle_utils.py`

## 4. 실행 명령어

```powershell
cd C:\Users\user\Documents\Codex_Workspace\AutoDriveEnvironmentDesigner
$env:CARLA_ROOT="C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor"
py -3.7 scripts\carla_runner\run_first_validation.py --duration-seconds 5 --map-id validation_smoke_test_v2
```

## 5. 실행 결과

터미널 출력 요약:

```text
Validation vehicle spawned and autopilot enabled.
Map id: validation_smoke_test_v2
Generated xodr: maps\generated\validation_smoke_test_v2.xodr
Manifest: experiments\validation_smoke_test_v2.json
Loaded map: Carla/Maps/OpenDriveMap
Blueprint: vehicle.dodge.charger_2020
Duration: 5.0 seconds
Saved validation result: results\validation_smoke_test_v2_validation.json
```

생성된 파일:

- `maps/generated/validation_smoke_test_v2.xodr`
- `experiments/validation_smoke_test_v2.json`
- `results/validation_smoke_test_v2_validation.json`

즉, 맵 생성부터 결과 저장까지 한 번에 수행하는 첫 통합 검증 흐름은 성공하였다.

## 6. 결과 파일 내용 요약

결과 JSON 주요 내용:

- `map_id`: `validation_smoke_test_v2`
- `success`: `false`
- `time_sec`: 약 5초
- `collision_count`: 2
- `loaded_map`: `Carla/Maps/OpenDriveMap`
- `spawn_point_count`: 1

여기서 중요한 점은 `실행 실패`가 아니라, `주행 중 충돌 이벤트가 2회 기록되어 success가 false로 저장되었다`는 것이다.

즉, `통합 흐름 자체는 성공`했고, `평가 지표 기준으로는 아직 개선 여지가 있음`을 의미한다.

## 7. 작업 중 보완한 사항

### 7-1. collision_count 과다 집계 문제

처음 통합 스크립트를 실행했을 때 collision_count가 비정상적으로 크게 기록되었다.

원인:

- 충돌 센서 이벤트가 같은 충돌을 여러 프레임에 걸쳐 중복 집계함

해결:

- collision sensor 집계에 debounce 개념을 추가하였다.
- 최소 간격(`collision_cooldown_seconds`)을 두고 충돌을 집계하도록 수정하였다.

수정 후 결과:

- 충돌 횟수가 227에서 2 수준으로 감소하였다.
- 아직 완벽한 평가는 아니지만, 훨씬 해석 가능한 수준이 되었다.

## 8. 결론

이번 작업으로 다음을 검증하였다.

- 기존의 개별 테스트 스크립트들을 하나의 실험 흐름으로 통합할 수 있다.
- OpenDRIVE 생성부터 CARLA 주행, 결과 저장까지 자동화할 수 있다.
- 결과 JSON 파일을 남기는 구조를 마련할 수 있다.

이것은 프로젝트가 단순한 기능 검증을 넘어서 `반복 가능한 실험 구조`로 진입했음을 의미한다.

## 9. 현재 한계

- `offroad_ratio`는 아직 placeholder 값(`0.0`)이다.
- collision_count는 debounce를 넣었지만, 아직 완전한 평가 지표는 아니다.
- 현재 맵은 직선 중심의 매우 단순한 테스트 코스이다.

## 10. 다음 단계

다음으로 진행하기 좋은 작업은 아래와 같다.

1. 직선 + 곡선 1개를 포함하는 OpenDRIVE 생성기 만들기
2. offroad_ratio 계산 방식 설계
3. collision 기준을 더 안정적으로 정리
4. 통합 실행 결과를 여러 케이스로 반복 비교할 수 있도록 naming 및 저장 규칙 정리

