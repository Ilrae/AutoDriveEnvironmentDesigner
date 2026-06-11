# Work Log

## 1. 문서 목적

이 문서는 현재 프로젝트의 진행 상태를 이어서 작업하기 위한 실전 기록 문서다.

이 문서에는 아래 내용을 계속 업데이트한다.

- 지금까지 확정된 결정
- 실제로 완료된 작업
- 현재 막혀 있는 문제
- 다음 작업 세션에서 바로 할 일

## 2. 프로젝트 현재 상태 스냅샷

### 현재 프로젝트 한 문장

`CARLA에서 사용할 OpenDRIVE 도로를 자동 생성하고, 차량 주행 결과를 평가해서 다음 도로를 다시 생성하는 시스템`

### 현재 단계

환경 구축 시작 전후 단계

정확히는:

- 기획/방향 정리는 완료된 상태
- 개발 환경은 아직 완전히 준비되지 않음
- CARLA 설치부터 시작해야 함

### 현재 가장 중요한 목표

`CARLA + Python + OpenDRIVE 최소 성공`

즉, 아래 순서를 실제로 성공시키는 것이 현재 최우선이다.

1. CARLA 실행
2. Python API 연결
3. 차량 spawn
4. autopilot 주행 확인
5. `.xodr` 로드
6. 직접 생성한 맵 위 주행

## 3. 지금까지 결정된 사항

### 기술/환경 결정

- 주 개발 OS는 `Windows`
- `WSL2 Ubuntu`는 필요 시 보조용으로만 사용
- 메인 언어는 `Python`
- 에디터는 `VS Code`
- 버전 관리는 `Git`
- 코드 작성/문서 정리는 `Codex` 적극 활용
- 시뮬레이터는 `CARLA binary release` 방식으로 설치
- 목표 CARLA 버전 후보는 `0.9.15`

### 하드웨어/환경 정보

- GPU: `RTX 3060 Ti`
- RAM: 아직 미기록
- CARLA 설치용 SSD 여유 공간: 아직 미기록

### 작업 원칙

- 처음부터 전체 시스템을 만들지 않는다.
- 작은 성공을 빠르게 반복한다.
- 지금은 강화학습, 고급 커리큘럼, 대형 시나리오를 하지 않는다.
- 현재는 "맵 생성 성공"보다 먼저 "CARLA 연결 성공"이 중요하다.

## 4. 현재 저장소 상태

현재 프로젝트 루트에는 아래 구조가 준비되어 있다.

```text
AutoDriveEnvironmentDesigner/
├─ docs/
├─ experiments/
├─ logs/
├─ maps/
├─ results/
├─ scripts/
└─ README.md
```

문서 상태:

- `docs/01_planning_stage.md` 존재
- `docs/02_execution_stage.md` 존재
- `TODO.md` 생성 완료
- `docs/WORKLOG.md` 생성 완료

## 5. 이미 완료된 일

- [x] 프로젝트 방향과 범위를 다시 좁혔다.
- [x] 핵심 구성 요소를 `도로 생성기 / CARLA 실행기 / 평가 로직`으로 정리했다.
- [x] 초기 1차 목표를 "직접 생성한 `.xodr`를 CARLA에서 로드하고 차량을 달리게 하는 것"으로 고정했다.
- [x] Windows 중심으로 개발하기로 결정했다.
- [x] Python 중심으로 구현하기로 결정했다.
- [x] Codex를 프로젝트 관리 및 코드 작성에 적극 활용하기로 결정했다.
- [x] 프로젝트 기본 폴더 구조를 만들었다.
- [x] TODO 문서와 진행 기록 문서를 만들었다.
- [x] 루트 `.gitignore`를 추가해 환경/실험 산출물 제외 규칙을 정리했다.
- [x] `scripts/` 하위에 Python 패키지 골격을 추가했다.
- [x] 직선 도로용 OpenDRIVE 생성기 초안을 추가했다.
- [x] 최소 결과 저장 모델과 JSON 저장 도우미를 추가했다.
- [x] 최소 난이도 업데이트 로직을 추가했다.
- [x] CARLA 연결 테스트 스크립트 초안을 추가했다.
- [x] CARLA 차량 spawn/autopilot 테스트 스크립트 초안을 추가했다.
- [x] `level -> .xodr + manifest` 초안 생성 스크립트를 추가했다.
- [x] `.xodr`를 CARLA standalone world로 로드하는 테스트 스크립트를 추가했다.
- [x] `맵 생성 -> 로드 -> 주행 -> 결과 저장` 통합 검증 스크립트를 추가했다.

## 6. 아직 안 된 것

### 환경 구축

- [ ] Python 3.10 설치 확인
- [ ] 가상환경 생성
- [ ] CARLA 다운로드
- [ ] CARLA 압축 해제
- [ ] CARLA 첫 실행

### 기술 검증

- [x] Python에서 `import carla` 성공
- [x] CARLA 서버 연결 성공
- [x] 차량 spawn 성공
- [x] autopilot 주행 확인

### OpenDRIVE 관련

- [ ] 샘플 `.xodr` 확보
- [ ] 샘플 `.xodr` 로드 성공
- [ ] 직접 생성한 직선 도로 `.xodr` 생성
- [ ] 생성한 맵 위 주행 성공

## 7. 지금 당장 해야 할 다음 액션

### 1순위

- [ ] Python 3.10 설치 여부 확인
- [ ] `.venv` 생성
- [ ] CARLA 다운로드 위치와 설치 위치 확정
- [ ] CARLA 다운로드 시작

### 2순위

- [ ] CARLA 압축 해제
- [ ] `CarlaUE4.exe` 실행
- [ ] 실행 성공 여부 기록

### 3순위

- [ ] OpenDRIVE 생성기 초안 로컬 실행 확인
- [ ] 생성된 `.xodr` 파일 구조 확인
- [ ] `test_connection.py` 실제 CARLA 환경에서 실행
- [ ] `import carla` 확인
- [ ] `client.get_world()` 호출 확인
- [ ] `load_xodr_in_carla.py`로 `.xodr` 로드 확인
- [ ] `test_spawn_vehicle.py` 실제 CARLA 환경에서 실행
- [ ] `run_first_validation.py` 실제 CARLA 환경에서 실행

## 8. 현재 기준으로 가장 먼저 만들 코드

아직 구현 전에 문서상으로만 정리된 후보:

- `scripts/carla_runner/test_connection.py`
- `scripts/carla_runner/test_spawn_vehicle.py`
- `scripts/map_generator/generate_straight_road.py`
- `scripts/evaluation/save_result.py`
- `scripts/curriculum/difficulty_controller.py`
- `scripts/map_generator/level_generator.py`
- `scripts/carla_runner/load_xodr_in_carla.py`
- `scripts/carla_runner/run_first_validation.py`

우선순위는 아래 순서다.

1. `test_connection.py`
2. `test_spawn_vehicle.py`
3. 샘플 `.xodr` 로드 테스트
4. `generate_straight_road.py`

## 9. 예상 리스크 / 막힐 가능성이 높은 부분

- CARLA 다운로드 용량이 큼
- Python 버전과 CARLA API 호환 문제가 생길 수 있음
- Windows 방화벽/포트 문제 가능성
- 첫 실행 시 그래픽/드라이버 이슈 가능성
- `.xodr` 로드 방식에서 초기에 헷갈릴 수 있음

## 10. 문제 발생 시 기록 규칙

문제가 생기면 아래 형식으로 남긴다.

### Issue Template

날짜:

작업:

문제:

에러 메시지:

내가 시도한 것:

결과:

다음에 확인할 것:

## 11. 작업 세션 기록

### Session 2026-03-12

한 일:

- GPT와 나눈 기존 대화를 바탕으로 프로젝트 방향을 다시 정리함
- 환경 구축 우선순위를 확정함
- `TODO.md`와 `docs/WORKLOG.md`를 만들어 작업 관리 체계를 정리함
- 루트 `.gitignore`를 추가함
- `scripts` 패키지 골격과 `scripts/map_generator/opendrive_writer.py` 초안을 추가함
- 시스템 Python으로 OpenDRIVE 생성기 초안 실행까지 확인함
- `scripts/evaluation/result_models.py`와 `scripts/curriculum/difficulty_controller.py`를 추가함
- `scripts/carla_runner/test_connection.py`와 `scripts/carla_runner/test_spawn_vehicle.py`를 추가함
- `scripts/map_generator/level_generator.py`를 추가하고 level 기반 draft map/manifest 생성까지 확인함
- `scripts/carla_runner/load_xodr_in_carla.py`를 추가함
- `scripts/carla_runner/run_first_validation.py`를 추가함
- CARLA 0.9.15 실행 확인
- `py -3.7 scripts\carla_runner\test_connection.py` 연결 성공 확인
- `py -3.7 scripts\carla_runner\load_xodr_in_carla.py --xodr-path maps\generated\straight_road_draft.xodr` 로드 성공 확인
- `py -3.7 scripts\carla_runner\test_spawn_vehicle.py --duration-seconds 10` 주행 성공 확인

현재 상태:

- CARLA 실행과 Python 연결은 성공
- 직접 생성한 OpenDRIVE를 CARLA에 로드하는 데 성공
- 차량 spawn/autopilot 주행까지 성공
- Python 3.7 기준 호환성 정리만 일부 남음

다음 세션에서 바로 할 일:

- Python 3.7 환경 기준으로 스크립트 호환성 정리
- 생성한 OpenDRIVE 맵에서 반복 실행 절차 정리
- 평가 결과 저장과 OpenDRIVE 로드/주행을 하나의 흐름으로 묶기

## 12. 다음 세션 시작용 체크

다음에 Codex와 이어서 작업할 때 가장 먼저 아래를 업데이트한다.

- [ ] Python 버전 확인 결과
- [ ] RAM 용량 기록
- [ ] SSD 여유 공간 기록
- [ ] CARLA 다운로드 진행 상태
- [ ] CARLA 실행 성공 여부
- [ ] Python API 연결 성공 여부

## 13. Session 2026-03-23 Update

### 추가 구현

- `scripts/carla_runner/vehicle_utils.py`를 추가해 차량 선택, spawn point 선택, autopilot 활성화, 충돌 센서 부착 로직을 공통화했다.
- `scripts/carla_runner/run_first_validation.py`를 추가해 아래 흐름을 한 번에 실행할 수 있게 했다.
- `맵 생성 -> CARLA 로드 -> 차량 spawn -> autopilot 주행 -> 결과 JSON 저장`

### 실제 실행 확인

- `py -3.7 scripts\carla_runner\run_first_validation.py --duration-seconds 5 --map-id validation_smoke_test_v2`
- 위 명령을 실제 CARLA 환경에서 실행했다.
- `maps/generated/validation_smoke_test_v2.xodr` 생성 확인
- `experiments/validation_smoke_test_v2.json` 생성 확인
- `results/validation_smoke_test_v2_validation.json` 생성 확인

### 관찰 결과

- 통합 실행 흐름 자체는 성공했다.
- collision sensor는 처음에는 과도하게 충돌을 집계했다.
- debounce를 넣어 같은 충돌이 여러 프레임에 걸쳐 과다 집계되는 문제를 줄였다.
- 수정 후 `collision_count`는 227에서 2 수준으로 감소했다.

### 현재 의미

- 프로젝트는 이제 수동 검증 단계를 넘어서, 재현 가능한 1회 실험을 자동 실행할 수 있는 상태다.
- 다음 핵심 과제는 곡선 도로 추가와 평가 지표 정교화다.
## 14. Session 2026-03-23 Curve Update

## 15. Session 2026-03-24 Evaluation and Application Structure Update

### 추가 구현

- `scripts/evaluation/path_metrics.py`를 추가해 기준 경로 샘플링, 목표 차선 중심선 비교, 경로 일치율 계산 로직을 정리했다.
- `scripts/evaluation/result_models.py`를 확장해 `failure_reason`, `path_match_score`, `mean_lateral_error_m`, `max_lateral_error_m`, `completion_ratio`, `reached_goal`, `sample_count`를 저장하도록 바꿨다.
- `scripts/carla_runner/run_manual_map_sequence_demo.py`에 주행 경로 기록, 충돌 센서, 맵 전환 시 결과 저장 흐름을 연결했다.
- 맵 케이스에 `goal_point`를 명시적으로 추가해, 도로 끝이 아니라 끝에서 약간 안쪽의 목표 지점을 기준으로 성공 여부를 판정하도록 바꿨다.
- `scripts/app/` 패키지를 추가해 현재 AED 애플리케이션 구조를 앱 레벨 세션 모델로 정리했다.

### 현재 판단

- 지금까지 구현한 기능을 기준으로 보면, 앱의 기본 골격은 이미 갖춰졌다.
- 현재 앱이 직접 담당하는 것은 `맵 생성/로딩`, `차량 소환`, `평가`, `맵 전환`이다.
- `pygame`은 현재 임시 수동 주행 UI일 뿐이며, 장기적으로는 실제 애플리케이션 UI로 교체할 수 있다.
- 남은 가장 핵심 과제는 자동 맵 생성 알고리즘 고도화다.

### 검증 결과

- `run_manual_map_sequence_demo.py`를 CARLA에 연결해 짧은 스모크 테스트를 실행했다.
- 실행 후 `results/manual_sequence/` 아래에 평가 JSON이 저장되는 것을 확인했다.
- 저장된 결과에는 충돌 횟수, 코스 이탈 비율, 경로 일치율, 완료율, goal 거리, spawn/goal 메타데이터가 포함된다.

### 다음 우선순위

- 자동 맵 생성 파라미터 확장
- 생성 결과와 평가 결과를 연결하는 루프 강화
- 이후 난이도 조절 로직 연결

### 앱 구조 추가 업데이트

- `scripts/app/gui.py`를 추가해 AED 기본 앱 제어 패널을 만들었다.
- 현재 앱은 `manual-sequence`, `manual-track`, `load-xodr` 기능을 GUI에서 실행할 수 있다.
- 최근 결과 JSON 목록과 로그를 한 창에서 볼 수 있도록 정리했다.
- 현재 GUI는 완성형 제품 UI가 아니라, 자동 맵 생성 모듈을 붙이기 위한 최소 앱 베이스라인이다.

### 추가 구현

- `scripts/map_generator/opendrive_writer.py`에 `--curve-length`, `--curve-curvature` 옵션을 추가했다.
- 직선 geometry 뒤에 arc geometry 1개를 이어붙일 수 있도록 OpenDRIVE 생성 로직을 확장했다.
- `scripts/map_generator/level_generator.py`에 `--include-curve`, `--curve-direction` 옵션을 추가했다.
- `scripts/carla_runner/run_first_validation.py`에서도 곡선 포함 맵 생성/로드/주행 흐름을 지원하도록 연결했다.

### 실제 검증

- `py -3.7 scripts\map_generator\opendrive_writer.py --output maps\generated\straight_arc_test_001.xodr --road-name straight_arc_test_001 --road-length 80 --curve-length 30 --curve-curvature 0.015`
- 생성된 `.xodr` 안에 `<line />` 뒤에 `<arc curvature="0.015000" />`가 들어간 것을 확인했다.
- `py -3.7 scripts\carla_runner\load_xodr_in_carla.py --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor --xodr-path maps\generated\straight_arc_test_001.xodr`
- 곡선 포함 맵이 `Carla/Maps/OpenDriveMap`으로 정상 로드되는 것을 확인했다.
- `py -3.7 scripts\carla_runner\run_first_validation.py --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor --map-id validation_curve_case_001 --level 0.45 --include-curve --curve-direction right --duration-seconds 5`
- 곡선 포함 맵에서 차량 spawn, autopilot 주행, 결과 JSON 저장까지 한 번에 성공했다.

### 생성된 산출물

- `maps/generated/straight_arc_test_001.xodr`
- `maps/generated/validation_curve_case_001.xodr`
- `experiments/validation_curve_case_001.json`
- `results/validation_curve_case_001_validation.json`

### 의미

- 프로젝트가 이제 `직선 전용 테스트`를 넘어서 `직선 + 곡선 1개 코스`까지 자동 생성하고 검증할 수 있는 단계로 올라왔다.
- 현재 범위인 `텅 빈 맵 + 도로 코스 생성` 관점에서는, 곡선 코스도 현실적으로 다룰 수 있다는 기술 검증이 끝난 상태다.
- 다음 작업은 곡선 파라미터 범위를 다듬고, offroad 판정 같은 평가 지표를 조금 더 실제화하는 것이다.
## 15. Session 2026-03-23 Stadium Track Update

### 추가 구현

- `opendrive_writer.py`에 `--stadium-track`, `--track-radius` 옵션을 추가했다.
- 경기장형 oval track을 만드는 전용 세그먼트 구성을 추가했다.
- `level_generator.py`와 `run_first_validation.py`에서도 stadium track 모드를 지원하도록 연결했다.

### 실제 검증

- `py -3.7 scripts\map_generator\opendrive_writer.py --output maps\generated\stadium_track_test_001.xodr --road-name stadium_track_test_001 --stadium-track --road-length 220 --track-radius 70 --curve-direction left`
- `py -3.7 scripts\carla_runner\load_xodr_in_carla.py --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor --xodr-path maps\generated\stadium_track_test_001.xodr`
- `py -3.7 scripts\carla_runner\run_first_validation.py --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor --map-id validation_stadium_track_001 --level 0.30 --stadium-track --curve-direction left --duration-seconds 8`

### 결과

- stadium track 형태의 폐곡선 코스가 CARLA에 정상 로드되었다.
- 차량 spawn 및 autopilot 주행이 성공했다.
- `results/validation_stadium_track_001_validation.json` 기준 `success: true`, `collision_count: 0`을 확인했다.
- 첫 번째 완성형 맵으로 사용할 수 있는 경기장 트랙을 확보했다.

## 16. Session 2026-03-23 Vehicle/Autopilot Note

### 정리 방향

- 차량 제어 알고리즘 자체는 이번 졸업작품의 핵심 구현 범위로 두지 않는다.
- CARLA 기본 차량 blueprint와 기본 autopilot을 생성 맵 검증용 보조 수단으로 사용한다.
- 보고서에서는 `맵 생성 시스템 검증을 위해 CARLA 내장 차량과 autopilot을 사용했다`고 명시한다.

### 문서화

- `docs/report_notes/vehicle_autopilot_test_setup.md`를 추가하여 보고서용 설명 문안을 분리 정리했다.
- 이후 보고서 작성 시 이 문서를 바탕으로 본문 또는 부록 설명을 옮겨 적을 수 있다.

## 17. Session 2026-03-23 Stadium Track Autopilot Demo

### 구현

- `scripts/carla_runner/run_stadium_track_demo.py`를 추가했다.
- stadium track 생성, CARLA 로드, 차량 spawn, CARLA 내장 autopilot 주행을 한 번에 실행하는 데모 스크립트다.

### 실제 검증

- `py -3.7 scripts\carla_runner\run_stadium_track_demo.py --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor --map-id stadium_demo_001 --level 0.30 --curve-direction left --duration-seconds 10`
- 실행 결과, CARLA 기본 차량이 경기장 트랙 위에 spawn 되었고 built-in autopilot으로 10초 주행했다.

### 의미

- 보고서에서 차량과 autopilot을 `검증용 보조 구성요소`로 분리해 설명할 근거가 마련되었다.
- 생성한 트랙이 실제 차량 주행 테스트에 사용 가능한 상태라는 점을 다시 확인했다.
