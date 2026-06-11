# 2026-03-24 Track Evaluation Metrics

## 1. 목적

생성한 OpenDRIVE 코스를 CARLA에 로드한 뒤, 차량이 해당 코스를 얼마나 안정적으로 주행했는지 수치화하기 위한 기본 평가 구조를 정의하였다.  
이번 단계의 목표는 완성형 난이도 조절 알고리즘이 아니라, **주행 결과를 저장하고 다음 맵 생성에 활용할 수 있는 최소 평가 기준**을 마련하는 것이다.

## 2. 평가 구조

평가는 크게 두 층으로 나눈다.

### 2.1 Fail 판정

다음 조건이 발생하면 해당 주행은 실패(`Fail`)로 처리한다.

- 벽 또는 구조물과 충돌
- 코스 이탈
- 목표 지점에 도달하지 못한 채 주행이 종료됨

현재 구현에서는 다음 방식으로 판정한다.

- `collision_count > 0` 이면 `collision`
- 차량 중심이 도로 폭 기준 허용 범위를 벗어난 샘플이 존재하면 `course_departure`
- 충돌/이탈은 없지만 종료 시점까지 finish line을 통과하지 못하면 `not_finished`

### 2.2 품질 점수

주행 품질은 “이상적인 주행 경로”와 실제 주행 경로의 차이로 계산한다.

- 이상적인 경로: 생성한 맵의 목표 차선 중심선
- 실제 경로: 주행 중 일정 시간 간격으로 기록한 차량 위치

현재 저장하는 대표 지표는 다음과 같다.

- `path_match_score`
- `mean_lateral_error_m`
- `max_lateral_error_m`
- `completion_ratio`

## 3. 중심 경로 기준

이번 구현에서는 OpenDRIVE 기준선(reference line) 자체가 아니라, **실제로 차량이 따라야 하는 차선 중심선**을 기준 경로로 사용한다.

이유는 다음과 같다.

- 도로 중앙 기준선은 양방향 도로의 가운데에 위치한다.
- 차량은 보통 왼쪽 또는 오른쪽 차선 한가운데를 따라 주행한다.
- 따라서 평가 기준은 “도로 전체 중심”보다 “목표 차선 중심”이 더 자연스럽다.

현재 데모 코스는 `spawn_point`와 `finish_line`에 다음 정보를 함께 저장한다.

- 시작/종료 기준 거리
- 좌/우 차선 정보
- 차선 인덱스
- 추가 lateral offset
- finish line half width

즉, 맵 생성 시점에 차량 시작 지점과 목표 지점, 평가 기준 경로가 함께 결정되는 구조이다.

## 4. 허용 오차 설정

초기 구현에서는 **중심 경로에서 1.5m 이내**인 경우를 “경로 일치”로 본다.

이 수치는 다음 이유로 넉넉하게 설정하였다.

- 수동 주행 기준으로 지나치게 엄격한 판정을 피하기 위함
- 초기 프로토타입 단계에서 false negative를 줄이기 위함
- 향후 난이도 조절 시 더 엄격한 기준으로 축소 가능함

현재 기준:

- `path_tolerance = 1.5m`
- `offroad_margin = 0.25m`
- `finish_line.half_width = 6.0m`

## 5. 계산 방식

### 5.1 경로 일치율

주행 중 기록한 각 샘플에 대해 목표 차선 중심선까지의 최단 거리를 구한 뒤,  
그 거리값이 `1.5m` 이하인 샘플의 비율을 `path_match_score`로 저장한다.

예:

- 전체 샘플 100개
- 그중 88개가 1.5m 이내
- `path_match_score = 0.88`

### 5.2 평균/최대 오차

같은 샘플 거리값으로 다음을 계산한다.

- `mean_lateral_error_m`: 평균 편차
- `max_lateral_error_m`: 최대 편차

### 5.3 완료율

차량이 기준 경로를 따라 어디까지 진행했는지를 비율로 환산하여 `completion_ratio`로 저장한다.

- 시작 지점 근처: 0.0
- 종점 근처: 1.0

현재는 맵마다 명시적으로 정의한 `finish_line`의 진행 위치를 통과하면 `crossed_finish_line = true`로 처리한다.

## 6. 현재 구현 내용

이번 단계에서 다음 내용을 코드에 반영하였다.

- 기준 차선 중심선 샘플링
- 도로 기준선 샘플링
- 주행 중 차량 위치 기록
- 충돌 센서 기반 `collision_count` 기록
- 맵 종료 시 결과 JSON 저장
- 수동 주행 맵 전환(`R`, `N`, `ESC`) 시 현재 주행 결과 자동 저장

적용 파일:

- `scripts/evaluation/path_metrics.py`
- `scripts/evaluation/result_models.py`
- `scripts/carla_runner/run_manual_map_sequence_demo.py`

## 7. 결과 저장 방향

현재 결과 파일은 `results/manual_sequence/` 아래에 저장한다.

저장 항목 예시는 다음과 같다.

```json
{
  "map_id": "sequence_demo_live_case_001",
  "success": false,
  "time_sec": 18.4,
  "collision_count": 1,
  "offroad_ratio": 0.0,
  "failure_reason": "collision",
  "path_match_score": 0.82,
  "mean_lateral_error_m": 0.91,
  "max_lateral_error_m": 2.34,
  "completion_ratio": 0.73,
  "crossed_finish_line": false,
  "sample_count": 146
}
```

## 8. 다음 단계

다음 구현 단계에서는 다음 항목을 이어서 확장할 수 있다.

- 수동 주행뿐 아니라 외부 자율주행 코드 결과도 같은 형식으로 평가
- 평가 결과를 기반으로 맵 난이도 조절
- 결과 누적 분석 CSV/JSON 정리
- 기준 경로 시각화 및 주행 경로 비교 시각화
