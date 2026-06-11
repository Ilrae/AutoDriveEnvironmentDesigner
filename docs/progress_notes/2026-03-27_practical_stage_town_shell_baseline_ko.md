# 2026-03-27 Practical Stage Town Shell Baseline

## 이번 단계에서 한 일

Practical Stage를 더 이상 placeholder 상태로 두지 않고, CARLA 기본 Town을 앱 안에서 바로 불러올 수 있는 shell baseline까지 연결했다.

이번 baseline의 목적은 아직 완전한 practical scenario generation을 끝내는 것이 아니라, 이후 route generation과 traffic population을 붙일 수 있는 공용 앱 구조를 먼저 만드는 데 있다.

## 현재 가능한 것

- UI에서 `Practical Road Stage`를 선택할 수 있다.
- Practical Stage 전용 Town / Weather / Traffic / Route preset을 고를 수 있다.
- 선택한 preset이 현재 session summary에 반영된다.
- `Load Selected Town` 버튼으로 CARLA 기본 Town을 바로 로드할 수 있다.
- Town 로드 시 선택한 weather preset도 같이 적용된다.

## 이번에 추가한 Practical Stage preset

### Town

- Town01
- Town02
- Town03
- Town04
- Town05
- Town10HD

### Weather

- clear_noon
- cloudy_noon
- wet_noon
- mid_rainy_noon
- clear_sunset
- wet_sunset

### Traffic

- light
- moderate
- dense

### Route

- urban_short
- urban_loop
- arterial_long
- junction_heavy

## 현재 구조에서의 의미

Track Stage와 Intermediate Stage는 여전히 생성형 OpenDRIVE 기반이다.

- Track Stage: generated track validation
- Intermediate Stage: generated road-like validation
- Practical Stage: built-in CARLA Town shell

즉 Practical Stage는 geometry를 새로 생성하는 단계가 아니라, Town 기반 scenario loop를 붙이기 위한 별도 축으로 분리되기 시작한 상태다.

## 아직 하지 않은 것

이번 shell baseline에는 아직 아래 기능이 포함되지 않는다.

- route 생성
- destination marker
- traffic population 실행
- pedestrian population 실행
- practical result JSON 저장
- result-driven next practical scenario generation
- CARLA manual control 기반 practical runtime 통합

## 다음 구현 순서

1. Town 위에서 ego spawn과 destination을 정하는 route baseline 추가
2. route completion / destination reached 평가 baseline 추가
3. Traffic Manager 기반 NPC vehicle preset 연결
4. practical stage용 결과 저장과 다음 scenario adaptation 연결

## 간단한 현재 판단

Practical Stage는 이제 계획만 있는 상태가 아니라, 앱 안에서 실제 Town을 불러오는 shell baseline까지는 연결된 상태다.

다음 단계부터는 Town shell 위에 route, traffic, evaluation을 순서대로 쌓아가면 된다.
