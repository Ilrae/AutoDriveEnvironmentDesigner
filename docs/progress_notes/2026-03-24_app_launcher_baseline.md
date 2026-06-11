# 2026-03-24 App Launcher Baseline

## 1. 목적

기존에는 CARLA 검증 기능이 각각 별도의 스크립트로 흩어져 있었다.  
이번 단계에서는 이를 AED 애플리케이션의 첫 진입점 형태로 묶기 위해 **앱 실행기(app launcher)** 를 추가하였다.

## 2. 현재 구현 범위

새 파일:

- `scripts/app/launcher.py`

현재 지원 기능:

1. `show-session`
2. `manual-sequence`
3. `manual-track`

즉, 아직 GUI는 아니지만 **AED 앱이 어떤 실행 모드를 제공하는지 한 곳에서 관리하는 첫 형태**가 만들어진 상태다.

## 3. 실행 예시

### 3.1 현재 앱 구조 확인

```powershell
py -3.7 scripts\app\launcher.py show-session --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor
```

### 3.2 두 맵 수동 시퀀스 실행

```powershell
py -3.7 scripts\app\launcher.py manual-sequence --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor --map-id aed_sequence_demo --spectator-mode fixed-overview
```

### 3.3 경기장 트랙 수동 주행 실행

```powershell
py -3.7 scripts\app\launcher.py manual-track --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor --map-id aed_manual_track_demo
```

## 4. 의미

이번 단계의 의미는 다음과 같다.

- 기존 검증 스크립트들이 AED 앱 하위 기능으로 묶이기 시작함
- 향후 GUI가 추가되더라도 내부 실행 모드는 유지 가능함
- 자동 맵 생성 로직이 완성되면 같은 launcher 아래에 새 실행 모드를 추가할 수 있음

즉, 지금은 “완성형 UI 앱”은 아니지만, **앱 구조로 가는 첫 실행 허브**가 생긴 상태라고 볼 수 있다.

## 5. 다음 단계

다음 우선순위는 launcher를 더 키우는 것이 아니라, 여기에 연결될 핵심 기능인 **자동 맵 생성**을 확장하는 것이다.
