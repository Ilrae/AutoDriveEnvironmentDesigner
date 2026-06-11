# Screenshots

이 폴더는 졸업작품 진행 과정에서 확보한 실행 화면, 오류 화면, 결과 화면 스크린샷을 저장하는 용도이다.

## 사용 목적

- 설치 및 실행 성공 증빙
- 오류 상황 기록
- 기능 구현 결과 시각화
- 발표 자료 및 최종 보고서 이미지 자산 관리

## 폴더 구조

- 날짜별 폴더를 사용한다.
- 형식: `YYYY-MM-DD`

예시:

```text
docs/screenshots/
├─ 2026-03-23/
└─ README.md
```

## 파일명 규칙

형식:

`YYYY-MM-DD_순번_설명.png`

예시:

- `2026-03-23_01_carla_launch_success.png`
- `2026-03-23_02_opendrive_map_loaded.png`
- `2026-03-23_03_vehicle_autopilot.png`
- `2026-03-23_04_error_directx_runtime.png`

## 권장 관리 방식

- 한 작업 세션이 끝나면 관련 스크린샷을 같은 날짜 폴더에 모은다.
- 진행 기록 파일(`docs/progress_notes/*.md`)에서 해당 이미지 파일명을 함께 적어 둔다.
- 의미 없는 중복 스크린샷은 줄이고, 보고서에 쓸 수 있는 핵심 화면 위주로 남긴다.

