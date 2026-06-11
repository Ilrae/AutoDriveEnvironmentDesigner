# 2026-04-01 Graduation Demo Report Summary

## 1. 프로젝트 개요
- 프로젝트명: `AutoDrive Environment Designer`
- 목표: CARLA 환경에서 자율주행 알고리즘 자체를 구현하는 것이 아니라, 주행 환경을 자동으로 만들고 평가한 뒤 다음 환경을 다시 구성하는 반복 실험 루프를 만드는 것이다.
- 핵심 개념: `생성 -> 로드 -> 차량 스폰 -> 주행 -> 평가 -> 다음 환경 생성`

## 2. 설계 방향
- 본 프로젝트는 난이도와 목적이 다른 3단계 구조로 구성된다.

### Track Stage
- 생성형 OpenDRIVE 트랙을 사용한다.
- 폐쇄 코스에서 기본 제어, 코스 완주, 안정성, 결과 기반 다음 맵 생성을 검증한다.

### Intermediate Stage
- 생성형 road-like OpenDRIVE 맵을 사용한다.
- lane keeping, wrong-lane, offroad 같은 도로 주행 기본 요소를 검증한다.

### Practical Stage
- CARLA 기본 Town 맵을 사용한다.
- route, traffic, pedestrian이 포함된 실제 도시형 시나리오를 생성하고 목적지 도달 기반으로 평가한다.

## 3. 현재 프로토타입에서 구현된 기능

### 3-1. Track Stage
- 결과 기반 다음 XODR 생성
- CARLA OpenDRIVE 맵 로드
- 차량 스폰 및 수동 주행
- finish line 기반 평가
- 결과 JSON 저장 및 다음 맵 자동 생성 루프

### 3-2. Intermediate Stage
- road-like XODR 생성
- wall 없는 lane-oriented 주행 환경
- lane discipline score, lane departure, opposite lane 평가
- 결과 기반 다음 road-like 맵 생성

### 3-3. Practical Stage
- Town / Weather / Traffic / Route preset 선택
- Town 기반 scenario JSON 생성
- ego vehicle + background traffic + pedestrian baseline spawn
- GOAL marker 기반 destination reached 평가
- 결과 JSON 저장
- 이전 Practical 결과 기반 다음 scenario 자동 적응
- 사용자 입력 필드만 고정하고 나머지는 자동 적응하는 partial override 구조

## 4. 이번 프로토타입의 핵심 의미
- Track와 Intermediate에서는 생성형 맵 실험 루프를 보여준다.
- Practical에서는 CARLA 기본 Town을 활용한 시나리오 기반 평가 루프를 보여준다.
- 따라서 본 프로젝트는 단순 맵 생성기가 아니라, 단계별 자율주행 검증 환경을 설계하고 반복 실행하는 도구라는 의미를 갖는다.

## 5. 시연 흐름 제안

### 시연 1. Track Stage
1. 이전 결과 선택
2. `Generate + Drive Next Map`
3. 트랙 주행
4. finish line 통과 후 점수와 결과 확인

### 시연 2. Intermediate Stage
1. `Intermediate Road Stage`
2. `Generate + Drive Next Map`
3. lane 유지 중심 주행
4. lane discipline 결과 확인

### 시연 3. Practical Stage
1. `Practical Road Stage`
2. Town / Weather / Traffic / Route 선택
3. `Generate + Run Practical Scenario`
4. GOAL marker를 따라 목적지까지 주행
5. destination reached 후 Practical score 확인

## 6. 현재 한계
- Practical Stage의 고급 이벤트는 아직 baseline 수준이다.
- 신호등 반응, 복합 교차로 이벤트, Scenario Runner 수준의 정교한 시나리오 구성은 아직 포함되지 않았다.
- 외부 자율주행 코드나 ROS bridge 연결은 지원 가능한 방향으로 설계했지만, 이번 프로토타입 범위에서는 직접 구현하지 않았다.
- Town의 시각 효과는 CARLA 기본 환경을 따르며, 커스텀 도로 에셋 수준의 비주얼 편집은 포함하지 않았다.

## 7. 프로토타입 완성 판단
- 현재 상태는 `Track / Intermediate / Practical` 3단계가 모두 실제 실행 가능한 baseline을 갖춘 상태다.
- 따라서 본 프로젝트는 “기능 아이디어 단계”를 넘어 “시연 가능한 프로토타입 단계”에 도달했다고 판단할 수 있다.

## 8. 향후 확장 방향
- Practical Stage의 richer adaptation
- pedestrian / weather / junction 난이도 조정 고도화
- 외부 자율주행 코드 연결 규약 정리
- 결과 해석 및 리포트 자동화
- 필요 시 Town 시나리오 이벤트 고도화
