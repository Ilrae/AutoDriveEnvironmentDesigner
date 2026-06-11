# Execution Stage

## Current Status

현재 프로젝트는 `환경 구축 및 첫 번째 기술 검증 시작 전` 단계입니다.

이미 정리된 결정 사항은 아래와 같습니다.

- 주 개발 환경은 Windows로 간다.
- WSL2는 보조 환경일 뿐, 현재 단계에서는 필수로 사용하지 않는다.
- 프로젝트의 주 언어는 Python으로 잡는다.
- CARLA는 source build가 아니라 binary release로 시작한다.
- 첫 목표는 커리큘럼이 아니라 `CARLA + Python + OpenDRIVE 최소 성공`이다.
- GPU는 RTX 3060 Ti로, 성능상 CARLA 실행에는 충분하다.

## What Codex Should Help With

Codex는 아래 영역에서 적극적으로 활용합니다.

- 프로젝트 구조 설계
- 반복적인 Python 코드 작성
- OpenDRIVE XML 생성 코드 작성
- 실험 자동화 코드
- 결과 저장 및 분석 코드
- 문서 정리 및 TODO 관리

## What Must Be Done Manually

아래 항목은 직접 확인하고 실행해야 합니다.

- CARLA 다운로드
- CARLA 실행
- Python 환경 설치
- simulator 연결 확인
- GPU/그래픽 이슈 대응
- 경로 문제, 포트 문제 등 환경 디버깅

## Immediate Goal

가장 가까운 목표는 아래 4개입니다.

1. CARLA 실행
2. Python API 연결
3. 차량 spawn
4. autopilot 주행 확인

이 네 가지가 되면 환경 구축 완료로 봅니다.

## Week 1 Checklist

### 1. Base Environment

- [ ] Python 3.10 설치
- [ ] VS Code 준비
- [ ] Git 초기화 및 기본 저장소 구조 유지

### 2. CARLA Setup

- [ ] CARLA 0.9.15 binary release 다운로드
- [ ] 권한 문제 없는 경로에 압축 해제
- [ ] `CarlaUE4.exe` 실행 확인

추천 설치 경로 예시:

```text
D:\CARLA\
```

### 3. Python API Connection

- [ ] 가상환경 생성
- [ ] CARLA Python API 설치
- [ ] 연결 테스트 코드 실행

예상 연결 테스트:

```python
import carla

client = carla.Client("localhost", 2000)
client.set_timeout(10.0)
world = client.get_world()

print("Connected to CARLA")
print("Current map:", world.get_map().name)
```

### 4. First Driving Test

- [ ] 차량 blueprint 선택
- [ ] spawn point 선택
- [ ] 차량 spawn
- [ ] autopilot 활성화

## Next Technical Milestone

환경 구축이 끝나면 바로 아래 단계로 넘어갑니다.

1. 샘플 OpenDRIVE `.xodr` 파일 확보
2. CARLA에서 해당 맵 로드
3. 직접 생성한 직선 도로 `.xodr` 파일 테스트
4. 생성기 코드를 함수화

예상 형태:

```python
generate_road(
    road_length=100,
    lane_width=3.5,
    curvature=0.0,
    output_path="maps/generated/test_001.xodr",
)
```

## Current Project Priority

현재는 아래 항목을 아직 구현하지 않습니다.

- 강화학습
- 고급 커리큘럼 설계
- 복잡한 시나리오 생성
- 고급 평가 지표 확장

우선순위는 아래와 같습니다.

1. CARLA 연결 성공
2. OpenDRIVE 로드 성공
3. 직선 도로 생성기 성공
4. 결과 저장 성공

## Recommended Working Style

권장 워크플로우는 아래와 같습니다.

1. 사람이 설계 결정
2. Codex가 코드 생성 및 정리
3. 사람이 실행
4. 에러 확인
5. Codex가 수정

## Next Files To Add

다음 구현 단계에서 아래 폴더를 순서대로 추가하는 것을 권장합니다.

```text
experiments/
maps/generated/
maps/samples/
scripts/carla_runner/
scripts/evaluation/
scripts/map_generator/
logs/
results/
```
