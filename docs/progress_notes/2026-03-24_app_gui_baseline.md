# 2026-03-24 App GUI Baseline

## 1. 목적

기존에는 AED 기능이 여러 개의 CLI 스크립트로 분산되어 있었다.  
이번 단계에서는 이를 하나의 기본 애플리케이션 창으로 묶기 위해 **tkinter 기반 앱 GUI 베이스라인**을 추가하였다.

## 2. 현재 구현 위치

- `scripts/app/gui.py`
- `scripts/app/launcher.py`

## 3. 현재 GUI가 하는 일

현재 GUI는 완성형 제품 UI가 아니라, **앱 제어 패널(control panel)** 성격의 첫 버전이다.

지원 기능:

- CARLA runtime 정보 입력
- 현재 AED 세션 구조 요약 확인
- 수동 시퀀스 데모 실행
- 수동 트랙 데모 실행
- 로컬 `.xodr` 파일 로딩 실행
- 최근 평가 결과 JSON 목록 확인
- 프로세스 로그 확인

## 4. 실행 방법

### 직접 GUI 실행

```powershell
py -3.7 scripts\app\gui.py --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor
```

### 런처를 통한 GUI 실행

```powershell
py -3.7 scripts\app\launcher.py gui --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor
```

## 5. 현재 의미

이번 GUI는 다음 목적에 맞는다.

- 여러 기능을 “AED 앱”이라는 하나의 진입점 아래에 묶기
- 추후 맵 자동 생성 모듈을 GUI에서 호출할 수 있는 기반 마련
- 현재는 `pygame` 기반 수동 주행을 그대로 재사용하되, 실행/로딩/결과 확인은 앱 창에서 관리하기

즉, 지금은 **기본 앱 골격**을 만들었고, 핵심 연구/개발 시간은 여전히 맵 자동 생성 로직에 집중하면 된다.

## 6. 다음 단계

다음 우선순위는 GUI를 화려하게 꾸미는 것이 아니라 다음과 같다.

1. 자동 맵 생성 모듈 연결
2. 생성 결과를 앱에서 불러와 로드
3. 평가 결과를 앱 안에서 더 보기 쉽게 요약

현재 GUI는 이 다음 단계를 수용하기 위한 최소 기반이라고 보면 된다.
