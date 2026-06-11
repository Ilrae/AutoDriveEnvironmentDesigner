# 2026-04-01 Prototype Completion Checklist

## 요약
- 현재 프로젝트는 `Track / Intermediate / Practical` 3단계 baseline이 모두 동작하는 상태다.
- 따라서 이제는 구조를 크게 바꾸기보다, “사용자가 바로 이해하고 재현 가능한 프로토타입” 기준으로 빈칸을 메우는 단계가 맞다.
- 프로토타입 완료 기준은 `기능이 많다`보다 `흐름이 끊기지 않고, 결과가 납득되며, 다시 실행하기 쉽다`에 두는 것이 좋다.

## 현재 이미 갖춘 것
- Track Stage
  - 결과 기반 XODR 생성
  - CARLA 로드
  - 차량 스폰 / 수동 주행
  - finish 기반 평가
  - 다음 맵 자동 생성 루프
- Intermediate Stage
  - road-like XODR 생성
  - lane-oriented 평가
  - offroad / wrong-lane / lane discipline 반영
- Practical Stage
  - Town 선택 및 로드
  - Town scenario 생성
  - Generate + Run 흐름
  - ego 차량 + background traffic + pedestrian baseline
  - destination goal 기반 평가
  - 이전 결과 기반 Practical adaptation
  - 사용자 지정 Practical override

## 프로토타입 완료라고 보기 전에 보강하면 좋은 항목

### 1. P0: Practical 사용 흐름의 직관성
- 사용자가 `Generate`와 `Run`의 차이를 즉시 이해할 수 있어야 한다.
- 현재는 `Prepared Scenario`와 `Generate + Run Practical Scenario`까지 들어와 있으므로, 이 흐름이 실제 사용 시 헷갈리지 않는지만 마지막으로 다듬으면 된다.
- 목표:
  - 어떤 scenario가 준비됐는지 보인다.
  - 왜 그렇게 바뀌었는지 보인다.
  - goal까지 가면 어떤 기준으로 점수가 나오는지 보인다.

### 2. P0: Practical goal score 흐름의 실주행 검증
- goal 도착 후 점수 계산을 백그라운드로 넘긴 구조는 프로토타입 품질에 매우 중요하다.
- 이 부분은 코드상 연결되어 있으므로, 실제 Town 주행에서 한 번 더 안정적으로 검증해 두면 프로토타입 완성도 판단이 쉬워진다.
- 목표:
  - goal 도착 시 프레임이 멈추지 않는다.
  - 점수 카드가 뜬다.
  - 결과 JSON이 정상 저장된다.
  - ESC 종료 시에도 결과가 유실되지 않는다.

### 3. P1: Practical adaptation의 설명 가능성
- 사용자는 “왜 traffic이 늘었는지”, “왜 route가 짧아졌는지”를 알 수 있어야 한다.
- 자동 적응은 이미 동작하고 있으므로, 남은 핵심은 그 판단을 UI/문서에서 설명 가능하게 만드는 것이다.
- 목표:
  - 이전 결과 기반으로 어떤 값이 바뀌었는지 표시된다.
  - 사용자가 일부 필드만 override한 경우, 나머지는 자동 적응이라는 점이 보인다.

### 4. P1: 단계별 최소 검증 시나리오 정리
- 발표/보고서/재시연을 위해 “이 단계가 정상 동작했다”는 최소 체크 케이스가 있어야 한다.
- 권장 baseline:
  - Track: 한 번 완주 + 결과 기반 다음 맵 생성
  - Intermediate: lane discipline이 반영된 결과 저장
  - Practical: Town scenario 생성 -> Run -> destination reached 결과 저장

### 5. P1: 짧은 사용자 가이드
- 지금은 기능이 꽤 많아서, 본인이 나중에 다시 봐도 잠깐 헷갈릴 수 있다.
- 각 Stage별로 “어떤 버튼을 누르고, 무엇을 보면 되는지”를 3~5줄로 정리해두면 프로토타입 제출/시연 안정성이 올라간다.

## 지금 당장 꼭 안 해도 되는 것
- Town 비주얼 고급화
- CARLA 기본 도로 에셋 수준의 렌더링 통합
- 신호등 / 교차로 이벤트 고도화
- 외부 자율주행 코드 / ROS bridge 본격 연결
- Scenario Runner 수준의 복합 이벤트 확장

## 권장 마감 기준
- 아래 네 가지가 만족되면 “프로토타입 완성”이라고 봐도 무리가 없다.
1. `Track / Intermediate / Practical`가 모두 한 번씩 끝까지 실행된다.
2. 각 Stage에서 결과 JSON이 저장되고, 점수 기준이 사용자 입장에서 납득 가능하다.
3. Practical에서 scenario 생성 이유와 goal 평가 결과가 UI상으로 확인된다.
4. 다음에 다시 실행할 때, Stage별 사용 순서를 짧은 메모만 보고 재현할 수 있다.

## 다음 작업 우선순위 제안
1. Practical scenario/adaptation 표시 보강
2. Practical goal score 실주행 재검증
3. Stage별 짧은 사용 가이드 문서화
4. 필요 시 adaptation 규칙 미세조정
