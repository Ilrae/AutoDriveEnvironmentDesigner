# 2026-04-02 Windows 패키징 베이스라인

## 목적

현재 AutoDrive Environment Designer 프로토타입은 Python 스크립트 형태로 실행된다.  
졸업작품 시연과 배포 편의성을 높이기 위해, Windows 환경에서 다음 두 가지를 만들 수 있는 기본 패키징 구조를 추가하였다.

- 실행 파일(`.exe`)
- 설치 파일(`.exe` installer)

## 패키징 방향

패키징은 `scripts/app/launcher.py`를 단일 진입점으로 사용한다.

- 소스 실행 시:
  - `launcher.py`가 기존처럼 각 작업을 수행한다.
- 동결 실행 파일(frozen executable) 실행 시:
  - 실행 파일이 다시 자기 자신을 하위 프로세스로 호출한다.
  - GUI 버튼 흐름은 그대로 유지된다.

즉, GUI와 launcher를 따로 나누는 대신 `launcher -> GUI / manual drive / load / practical scenario` 구조를 하나의 실행 파일 안에서 재사용하는 방식으로 정리하였다.

## 런타임 작업공간

설치형 배포에서는 `Program Files` 아래에 직접 결과 파일을 쓰면 권한 문제가 생길 수 있다.  
따라서 동결 실행 파일에서는 사용자 문서 폴더 아래에 별도 작업공간을 자동 생성하도록 정리하였다.

- 기본 작업공간:
  - `%USERPROFILE%\\Documents\\AutoDriveEnvironmentDesignerRuntime`

생성되는 기본 폴더:

- `maps/generated`
- `experiments`
- `experiments/practical`
- `results/manual_sequence`
- `results/practical`
- `scenarios/practical`
- `logs`
- `output/doc`
- `output/pdf`

이 구조로 인해 설치 경로와 사용자 데이터 경로를 분리할 수 있다.

## 추가된 파일

### 1. 런타임 helper

- `scripts/app/runtime_support.py`

역할:

- 현재 실행이 소스 실행인지, 동결 실행인지 판단
- 동결 실행 시 사용자 문서 폴더 기반 작업공간 생성
- GUI 하위 프로세스 호출 명령 생성
- launcher가 다른 엔트리포인트를 같은 실행 파일 안에서 호출할 수 있도록 helper 제공

### 2. PyInstaller spec

- `packaging/windows/AutoDriveEnvironmentDesigner.spec`

역할:

- `scripts/app/launcher.py`를 기준으로 실행 파일 생성
- `scripts` 패키지 하위 모듈을 hidden import로 포함
- `README.md`를 기본 데이터 파일로 포함

### 3. Windows 빌드 스크립트

- `packaging/windows/build_windows_bundle.ps1`

역할:

- `py -3.7 -m pip install pyinstaller`
- `py -3.7 -m PyInstaller ...`
- Inno Setup이 설치되어 있으면 설치 파일까지 생성

### 4. Inno Setup 스크립트

- `packaging/windows/AutoDriveEnvironmentDesigner.iss`

역할:

- `dist/AutoDriveEnvironmentDesigner` 폴더를 설치형 실행 파일로 묶음
- 시작 메뉴/바탕 화면 바로가기 생성

## launcher 정리

`scripts/app/launcher.py`는 다음과 같이 조정하였다.

- 명령어가 없으면 기본으로 GUI 실행
- 기존의 파일 경로 기반 `subprocess.run(script.py)` 대신
  - 모듈의 `main()`을 직접 호출하는 구조로 정리
- 동결 실행 환경에서도 `manual-sequence`, `manual-track`, `manual-xodr`, `load-town`, `run-practical-scenario` 등이 같은 구조로 동작 가능

## GUI 정리

`scripts/app/gui.py`는 다음과 같이 조정하였다.

- 런타임 작업공간을 공용 helper에서 받아 사용
- 하위 프로세스 실행 시:
  - 소스 실행에서는 `python launcher.py ...`
  - 동결 실행에서는 `AutoDriveEnvironmentDesigner.exe ...`
- 하위 프로세스의 현재 작업 폴더를 런타임 작업공간으로 고정

## 현재 상태

이번 패키징 작업은 **배포 베이스라인을 추가한 단계**이다.

현재 보장되는 범위:

- 실행 파일 빌드에 필요한 구조 정리
- 동결 실행 환경을 고려한 launcher/GUI 보강
- 설치기 생성 스크립트 초안 추가

아직 확인이 필요한 범위:

- 실제 PyInstaller 빌드 결과 실행 검증
- 실제 설치기 실행 후 바로가기 동작 확인
- CARLA 설치 경로를 배포판에서 어떻게 안내할지 문서화

## 빌드 명령

PowerShell 기준:

```powershell
.\packaging\windows\build_windows_bundle.ps1
```

PyInstaller만 실행하고 설치 파일은 건너뛰려면:

```powershell
.\packaging\windows\build_windows_bundle.ps1 -SkipInstaller
```

## 결론

이번 정리로 AutoDrive Environment Designer는 단순 Python 스크립트 모음에서 벗어나, Windows 실행 파일과 설치 파일로 전개할 수 있는 기반을 갖추게 되었다.  
즉, 현재 단계는 “패키징 가능 구조 확보”까지 완료된 상태이며, 다음 단계는 실제 빌드 산출물을 확인하고 시연용 배포 절차를 마무리하는 것이다.
