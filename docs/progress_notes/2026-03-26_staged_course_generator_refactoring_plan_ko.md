# 2026-03-26 단계형 코스 생성기 리팩터링 계획

## 1. 왜 이 리팩터링이 필요한가

2026년 3월 26일 기준으로 AED baseline 루프는 끝까지 동작하고 있다.

- 다음 맵 생성
- CARLA 로드
- 차량 스폰
- 주행
- 평가
- 결과 저장
- 저장된 결과를 사용한 다음 맵 생성

지금의 병목은 더 이상 앱 루프 자체가 아니다.
현재 가장 큰 품질 문제는 맵 생성기다.

반복 수동 주행에서 관찰된 문제는 다음과 같다.

- map id가 달라도 체감상 같은 코스 계열처럼 느껴지는 경우가 있다
- 난이도가 올라가도 "직선이 길어지고 커브가 조금 달라진 정도"로 느껴질 때가 있다
- 상위 난이도에서는 반복적인 기술형 레이아웃 몇 개로 수렴하는 경향이 있다
- 생성 로직이 여러 파일에 퍼져 있고 threshold가 중복되어 있다

즉, 다음 구현 초점은 아래 3가지가 되어야 한다.

1. 난이도 상승이 숫자 증가가 아니라 단계 상승처럼 느껴지게 만들기
2. 생성되는 코스가 구조적으로 더 다양해지게 만들기
3. 생성기를 전체 재작성 없이 확장하기 쉬운 구조로 바꾸기

## 2. 현재 생성기의 형태

현재 흐름은 다음과 같다.

1. 평가 결과 -> driving score
2. driving score -> 다음 numeric level
3. 다음 level -> course variant 선택
4. variant + level -> line/arc 세그먼트 목록 생성
5. 세그먼트 목록 -> XODR + manifest 생성

현재 중요한 모듈:

- `scripts/app/auto_generation.py`
- `scripts/curriculum/difficulty_controller.py`
- `scripts/map_generator/level_generator.py`

현재 구조상의 한계:

- level threshold가 여러 모듈에 중복되어 있다
- "stage" 개념이 암묵적으로만 존재하고 명시적인 generator contract가 아니다
- variant 선택과 세그먼트 조합이 강하게 결합되어 있다
- manifest가 생성된 맵 자체는 설명하지만, 의도된 stage 의미를 충분히 담고 있지는 않다

## 3. 리팩터링 목표

이번 리팩터링의 목표는 현재 생성기를 완전히 다른 시스템으로 교체하는 것이 아니다.

목표는 현재 baseline을 아래 성질을 가진 단계형 procedural generator로 발전시키는 것이다.

- stage threshold와 stage 의도를 위한 단일 공통 기준을 갖기
- 아래 요소들을 명확히 분리하기
  - score / difficulty update
  - stage selection
  - variant selection
  - segment composition
  - validation and metadata
- 인간 운전자가 느끼기에 stage progression이 분명하게 드러나기
- 같은 stage 안에서도 반복 테스트가 똑같게 느껴지지 않을 정도의 다양성 확보

## 4. 목표 아키텍처

목표 생성기는 다음 계층으로 분리되어야 한다.

### 4.1 Difficulty Layer

책임:

- 결과 품질을 다음 numeric difficulty level로 변환

담당 모듈:

- `scripts/curriculum/difficulty_controller.py`

이 계층은 numeric 형태를 유지하는 것이 맞다.
부드러운 적응을 위해 여전히 유용하기 때문이다.

### 4.2 Stage Layer

책임:

- numeric level을 사람이 이해하기 쉬운 stage로 변환

예:

- `foundation_flow`
- `offset_transition`
- `curvy_medium`
- `technical_hard`
- `mixed_extreme`

이 계층은 다음을 정의해야 한다.

- stage id
- stage display name
- 의도된 주행 기술
- candidate variants
- target length band
- target curve-count band
- target curvature band

중요한 구분:

- `difficulty stage` = numeric level이 의미하는 stage
- `layout stage` = 실제로 선택된 variant family가 의미하는 stage

회복 규칙이나 다양화 규칙이 레이아웃을 의도적으로 더 쉬운 family 또는 다른 family로 끌어당길 때, 이 둘은 일시적으로 달라질 수 있다.

### 4.3 Variant Layer

책임:

- 현재 stage 안에서 하나의 layout family를 선택

예:

- `single_turn`
- `gentle_chicane`
- `offset_bend`
- `s_curve`
- `compound_turn`
- `switchback`
- `double_apex`
- `snake_run`

variant layer는 절대 다양성의 유일한 원천이 되어서는 안 된다.
이 계층은 family를 결정하는 역할이지, 정확한 코스 하나를 결정하는 역할이 아니다.

### 4.4 Segment Composer Layer

책임:

- stage + variant + seed를 바탕으로 구체적인 segment sequence를 생성

이 계층이 제어해야 하는 것:

- 총 코스 길이
- arc segment 수
- 방향 전환 횟수
- recovery straight 길이
- 최대 곡률 집중도

이 부분이 현재 generator의 실제 품질 병목이며, 이번 리팩터링의 주된 대상이다.

### 4.5 Validation and Metadata Layer

책임:

- 생성된 코스가 최소 규칙을 만족하는지 검사
- stage metadata를 manifest에 저장

최소 validation 목표:

- spawn zone이 충분히 길다
- finish zone이 안정적이다
- 총 길이가 stage 목표 범위 안에 있다
- segment count가 stage 목표 범위 안에 있다
- 우연히 거의 동일한 짧은 레이아웃으로 붕괴하지 않는다

## 5. 제안하는 Stage 모델

현재 코드도 사실상 다섯 개의 macro stage가 있는 것처럼 동작하고 있다.
리팩터링에서는 이 점을 명시적으로 드러내야 한다.

제안 stage 집합:

1. `foundation_flow`
   - intent: 쉬운 완주, 긴 recovery straight, 기본 turn 적응
   - variants: `single_turn`, `gentle_chicane`

2. `offset_transition`
   - intent: offset bend와 약한 방향 전환 학습
   - variants: `gentle_chicane`, `offset_bend`, `s_curve`

3. `curvy_medium`
   - intent: 반복 조향과 중간 정도의 코너 진입 부담
   - variants: `s_curve`, `compound_turn`, `switchback`

4. `technical_hard`
   - intent: 연결 코너와 줄어든 recovery space
   - variants: `compound_turn`, `switchback`, `double_apex`

5. `mixed_extreme`
   - intent: 높은 곡률 밀도와 반복 전환
   - variants: `switchback`, `double_apex`, `snake_run`

중요한 점:

- numeric `level`은 계속 유지된다
- stage는 level 위에 놓이는 해석 계층이다
- variant도 계속 존재한다
- 최종 맵은 하나의 variant 문자열만으로 설명되는 것이 아니라 `stage + variant + seed`로 설명되어야 한다

## 6. 리팩터링 단계

### Phase 1. Shared Stage Metadata

다음을 정의하는 공통 모듈을 하나 만든다.

- variant order
- level-to-adaptive-variant mapping
- stage definitions
- stage-to-variant family mapping

결과:

- `auto_generation.py`와 `level_generator.py`가 중복 threshold 로직을 더 이상 각각 들고 있지 않게 된다

### Phase 2. Manifest Enrichment

생성되는 manifest에 명시적 stage metadata를 넣는다.

- difficulty stage id / index
- layout stage id / index
- stage display name
- stage intent
- candidate variants

결과:

- 생성된 맵을 감사 가능하게 만들 수 있다
- 이후 분석이나 보고서에서 map id만이 아니라 stage 기준으로 비교할 수 있다

### Phase 3. Segment Composer Separation

open-course segment composition을 전용 builder layer로 분리한다.

현재:

- variant branch가 큰 함수 하나에 몰려 있음

목표:

- stage-aware composition helpers
- reusable composition utilities
- clearer per-stage targets

결과:

- 전체 generator를 불안정하게 만들지 않고도 다양성을 키우기 쉬워진다

### Phase 4. Anti-Repetition Rules

명시적인 반복 방지 규칙을 추가한다.

- 같은 family가 너무 자주 반복되지 않게 하기
- 거의 같은 총 길이 대역이 너무 자주 반복되지 않게 하기
- 연속 맵에서 동일한 곡률 리듬이 반복되지 않게 하기

결과:

- 반복 수동 테스트가 작은 cosmetic mutation처럼 느껴지는 현상이 줄어든다

### Phase 5. Baseline Validation

baseline suite를 사용해서 다음을 검증한다.

- easy track은 실제로 easy하게 유지되는가
- hard track은 실제로 더 기술적으로 어려운가
- 2차선 road-like case도 올바르게 평가되는가

결과:

- generator 변경을 고정 기준 케이스에 대해 평가할 수 있게 된다

## 7. 이번 리팩터링의 비목표

이번 리팩터링은 아직 아래를 목표로 하지 않는다.

- 교차로
- 도시형 road network
- 장애물
- traffic system
- multi-road route planning 전체

현재 목표는 그대로 다음이다.

- 먼저 더 좋고, 더 다양하고, stage가 읽히는 track/open-course 맵을 만드는 것

## 8. 즉시 구현 순서

이 문서 다음에 바로 들어가야 할 구현 순서는 다음과 같다.

1. shared stage-definition module 추가
2. auto-generation과 level-generator가 그 shared module을 사용하도록 변경
3. stage metadata를 manifest에 기록
4. open-course composition을 더 작은 helper들로 분리
5. 그 이후에야 실제 diversity rule을 공격적으로 바꾸기 시작

이 순서는 중요하다.
shared stage contract 없이 다양성만 먼저 바꾸면 generator가 더 이해하기 어려워진다.

## 9. 리팩터링 후 기대 결과

이 리팩터링이 성공하면 수동 테스트 드라이버는 다음처럼 느껴야 한다.

- "이번 맵은 이전 맵보다 확실히 더 높은 stage다"
- "같은 stage 안에서도 충분히 다양한 레이아웃이 나온다"
- "어려운 맵이 단순히 더 긴 맵은 아니다"
- "generator 구조가 읽히고, 나중에 road-driving mode로도 확장 가능해 보인다"

이것이 이번 리팩터링의 실제 성공 기준이다.
