# 2026-03-23 Manual Drive Demo Setup

## 1. 작업 목적

생성한 OpenDRIVE 기반 custom track을 사람이 직접 운전하며 시연할 수 있도록, CARLA 기본 수동 주행 예제를 연결하는 절차를 구축하였다.

## 2. 진행 내용

- CARLA 설치 경로에서 `PythonAPI/examples/manual_control.py` 위치 확인
- Python 3.7 환경에 `pygame` 설치
- custom track을 생성하고 CARLA에 로드한 뒤, CARLA 기본 `manual_control.py`를 실행하는 래퍼 스크립트 추가

추가한 스크립트:

- `scripts/carla_runner/launch_manual_drive_demo.py`

## 3. 검증 내용

다음을 확인하였다.

- `manual_control.py`가 현재 Python 3.7 환경에서 정상적으로 실행 가능한 상태임
- `launch_manual_drive_demo.py --skip-launch`로 custom track 생성 및 로딩이 정상 동작함
- manual_control 실행 명령이 자동으로 출력되며, 해당 도구를 그대로 수동 조작 시연에 사용할 수 있음

## 4. 의미

이 작업으로 인해 차량 제어를 별도로 구현하지 않고도, 생성한 트랙 위에서 사용자가 직접 키보드로 차량을 운전하는 시연이 가능해졌다.

이는 본 프로젝트의 핵심이 자율주행 제어 알고리즘이 아니라, 주행 환경 생성 및 평가 구조 설계라는 점과도 잘 맞는다.
