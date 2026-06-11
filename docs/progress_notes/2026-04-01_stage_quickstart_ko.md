# 2026-04-01 Stage Quickstart Guide

## 목적
- 이 문서는 현재 프로토타입을 다시 실행하거나 시연할 때, Stage별 사용 순서를 짧게 확인하기 위한 빠른 가이드다.
- 목표는 “버튼 순서를 다시 고민하지 않고 바로 재현할 수 있는가”에 있다.

## 1. Track Stage

### 언제 쓰는가
- 생성형 OpenDRIVE 트랙에서 기본 제어, 코스 완주, result-driven 다음 맵 생성을 확인할 때 사용한다.

### 기본 순서
1. `Track Driving Stage` 선택
2. 결과 리스트에서 기준으로 삼을 결과를 선택하거나, 비워 두면 최신 결과를 사용
3. `Generate + Drive Next Map` 실행
4. pygame 창에서 수동 주행
5. finish line 통과 후 점수와 결과 JSON 확인
6. 필요하면 다시 같은 흐름으로 다음 맵 생성

### 확인 포인트
- 새 `.xodr`가 생성되는가
- CARLA에 맵이 로드되는가
- 차량이 스폰되는가
- finish line 통과 후 결과 JSON이 저장되는가

## 2. Intermediate Stage

### 언제 쓰는가
- 더 긴 road-like XODR에서 lane keeping과 road-following을 평가할 때 사용한다.

### 기본 순서
1. `Intermediate Road Stage` 선택
2. 필요하면 결과 리스트에서 이전 결과를 선택
3. `Generate + Drive Next Map` 실행
4. road-like 코스를 lane 중심으로 따라 주행
5. 종료 후 lane discipline, wrong-lane, offroad 관련 점수 확인

### 확인 포인트
- 트랙보다 긴 road-like map이 생성되는가
- lane-oriented evaluation이 결과 JSON에 반영되는가
- next map generation이 intermediate 결과를 다시 입력으로 사용하는가

## 3. Practical Stage

### 언제 쓰는가
- CARLA 기본 Town에서 route, traffic, pedestrian이 있는 목적지 주행 시나리오를 실행할 때 사용한다.

### 기본 순서
1. `Practical Road Stage` 선택
2. `Practical Town Setup`에서 `Town / Weather / Traffic / Route` 선택
3. 필요하면 `Open Custom Scenario Settings`
   - 직접 입력한 값만 고정된다
   - 비워 둔 값은 이전 결과 기반 자동 적응이 계속 적용된다
4. `Generate Practical Scenario` 또는 `Generate + Run Practical Scenario`
5. 주행이 시작되면 GOAL marker를 따라 destination까지 주행
6. goal 도달 후 background score 계산과 결과 저장 확인

### 확인 포인트
- `Prepared Scenario`에 현재 scenario id와 adaptation 요약이 보이는가
- Town 로드 후 ego 차량과 background traffic/pedestrian이 뜨는가
- GOAL marker를 보고 destination까지 이동할 수 있는가
- 결과 JSON이 `results/practical`에 저장되는가

## 4. 프로토타입 시연용 최소 재현 세트

### A. Track
1. 결과 하나 선택
2. `Generate + Drive Next Map`
3. finish line 통과
4. 결과 JSON 확인

### B. Intermediate
1. `Intermediate Road Stage`
2. `Generate + Drive Next Map`
3. lane discipline이 반영된 결과 JSON 확인

### C. Practical
1. `Practical Road Stage`
2. `Generate + Run Practical Scenario`
3. GOAL marker를 따라 destination 도달
4. destination-based 결과 JSON 확인

## 5. 현재 기준의 해석
- Track: 생성형 폐쇄 코스 검증
- Intermediate: 생성형 road-like lane 주행 검증
- Practical: CARLA Town 기반 scenario 검증

## 6. 메모
- Practical에서는 새 `.xodr` 맵을 만드는 것이 아니라, Town 위에서 실행할 scenario JSON을 생성한다.
- 따라서 Practical의 `Generate`는 “맵 생성”보다 “다음 Town 시나리오 준비”로 이해하는 것이 맞다.
