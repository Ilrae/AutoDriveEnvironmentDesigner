# Planning Stage

## Source Summary

이 문서는 다음 두 가지를 바탕으로 정리했습니다.

- 프로젝트 제안서: `AutoDrive_Environment_Designer_Project_Proposal.docx`
- ChatGPT와의 프로젝트 기획 대화

## Project in One Sentence

CARLA에서 사용할 OpenDRIVE 도로를 자동 생성하고, 차량 주행 결과를 평가해서 다음 도로를 다시 생성하는 적응형 자율주행 학습 환경 설계 시스템을 만든다.

## Core Goal

이 프로젝트의 핵심은 자율주행 알고리즘 자체를 새로 만드는 것이 아니라, 자율주행 에이전트를 학습시키고 평가하기 위한 환경을 자동으로 설계하는 시스템을 구현하는 데 있습니다.

핵심 구성요소는 3개입니다.

1. 도로 생성기
2. CARLA 실행기
3. 평가 후 다음 도로를 만드는 로직

## Non-Goals

초기 프로젝트 범위에서 제외하는 항목은 아래와 같습니다.

- 상용 수준 자율주행 제어 알고리즘 개발
- 딥러닝 기반 인지 모델 개발
- 복잡한 도시 전체 맵 생성
- 다수 차량, 보행자, 신호 전체 시스템 구현
- 실제 차량 연동

## Recommended Development Order

프로젝트는 아래 순서로 진행합니다.

### A. CARLA 익히기

- 설치
- 실행
- Python API 연결
- 차량 spawn
- autopilot 테스트

### B. OpenDRIVE 최소 예제 익히기

- OpenDRIVE XML 구조 확인
- 단순 직선 도로 파일 확인
- CARLA에서 로드 테스트

### C. 직접 생성기 만들기

- 길이, 곡률, 폭을 파라미터로 받아 `.xodr` 생성
- 여러 도로 자동 생성

### D. 자동 실험 구조 만들기

- 도로 생성
- CARLA 로딩
- 차량 주행
- 결과 저장

### E. 평가 시스템 만들기

- 성공/실패
- 충돌
- 주행 시간
- 평균 속도
- 이탈 정도

### F. 커리큘럼 로직 만들기

- 너무 쉬우면 더 어렵게
- 너무 어려우면 더 쉽게
- 적절한 난이도로 수렴시키기

## First Milestone

초기 1차 목표는 반드시 아래 범위로 고정합니다.

1. OpenDRIVE 파일 하나를 직접 생성한다.
2. 그 파일을 CARLA에서 로드한다.
3. 차 한 대를 올린다.
4. 자동 주행시킨다.
5. 결과를 확인한다.

이 단계 전에는 아래 기능을 서두르지 않습니다.

- 커리큘럼
- 난이도 조절
- 자동 반복
- 고급 평가 시스템

## Suggested Project Structure

```text
AutoDriveEnvironmentDesigner/
├─ docs/
├─ experiments/
├─ maps/
│  ├─ generated/
│  └─ samples/
├─ scripts/
│  ├─ carla_runner/
│  ├─ map_generator/
│  └─ evaluation/
├─ logs/
├─ results/
└─ README.md
```

## Recommended Tech Stack

- Main OS: Windows
- Optional secondary environment: WSL2 Ubuntu
- Main language: Python
- Editor: VS Code
- Simulator: CARLA
- Version control: Git
- AI assistance: Codex

## Why Python First

현재 프로젝트에서는 Python을 주 언어로 잡는 것이 적합합니다.

- CARLA Python 예제가 가장 많음
- OpenDRIVE 생성 자동화에 적합함
- 실험 반복, CSV/JSON 저장, 분석 코드 작성이 쉬움

## Initial Domain Model

프로젝트는 아래 개념을 중심으로 구조화합니다.

- `map_generator`: OpenDRIVE 도로 생성
- `simulation_runner`: CARLA 실행 및 차량 주행
- `evaluation`: 주행 결과 분석
- `curriculum`: 난이도 상태 업데이트

## Difficulty Design

난이도는 초기에 복잡하게 설계하지 않고, `0.0 ~ 1.0` 범위의 단일 `level` 값으로 시작합니다.

예시:

- level 낮음 -> 폭 넓음, 커브 적음, 길이 짧음
- level 높음 -> 폭 좁음, 커브 많음, 길이 길음

## Minimal Curriculum Logic

초기 커리큘럼 로직은 단순하게 시작합니다.

```python
if success_rate > 0.8:
    level += 0.05
elif success_rate < 0.5:
    level -= 0.05
else:
    level = level
```

## Success Criteria

프로젝트가 아이디어 단계에서 실행 단계로 넘어갔다고 볼 수 있는 기준은 아래와 같습니다.

1. CARLA가 실행된다.
2. Python API로 연결된다.
3. 차량이 spawn된다.
4. `.xodr` 파일을 CARLA가 읽는다.
5. 생성한 맵 위에서 차량이 주행한다.
6. 결과가 JSON 또는 CSV로 저장된다.

## Important Principle

이 프로젝트는 처음부터 전체를 한 번에 구현하지 않습니다.

작은 성공을 반복하며 확장합니다.

1. 먼저 돌려본다.
2. 그 다음 수정한다.
3. 그 다음 구조를 이해한다.
