# 2026-03-27 Practical Stage Runtime Baseline

## 요약
- Practical Stage에 Town 기반 scenario 실행 baseline을 연결했다.
- 이제 앱에서 `Generate Practical Scenario`로 Town route scenario를 생성하고, `Run Practical Scenario`로 ego 차량과 background traffic vehicle을 함께 올려 수동 주행할 수 있다.
- custom override를 켜지 않으면, 이전 Practical 결과를 읽어 다음 scenario의 traffic / route length / junction focus를 baseline 규칙으로 자동 조정한다.
- 결과는 `results/practical`에 JSON으로 저장된다.

## 이번에 연결된 흐름
1. Practical Stage 선택
2. Town / Weather / Traffic / Route preset 선택
3. 필요하면 Custom Scenario Settings에서 override 저장
4. `Generate Practical Scenario`
   - Town 기준 spawn / destination / route baseline 계산
   - custom override가 꺼져 있으면 이전 Practical result를 읽어 다음 scenario 난이도를 자동 조정
   - `scenarios/practical`에 scenario JSON 저장
   - `experiments/practical`에 manifest 저장
5. `Run Practical Scenario`
   - scenario JSON 로드
   - Town / weather 적용
   - ego vehicle spawn
   - Traffic Manager 기반 background traffic vehicle spawn
   - pygame 기반 manual driving 실행
   - route progress / remaining distance / collision HUD 표시
   - `results/practical`에 evaluation result JSON 저장

## 주요 구현 파일
- `scripts/app/gui.py`
- `scripts/app/launcher.py`
- `scripts/app/practical_stage.py`
- `scripts/app/practical_scenario_generation.py`
- `scripts/carla_runner/load_town_in_carla.py`
- `scripts/carla_runner/run_practical_scenario_demo.py`
- `scripts/carla_runner/carla_utils.py`

## 현재 평가 기준
- route completion
- collision count
- offroad ratio
- lane discipline score
- opposite lane ratio
- destination 미도달 시 `not_finished`

## 현재 한계
- pedestrian population은 아직 미연결
- result-driven adaptation은 traffic / route length / junction focus baseline까지만 연결되어 있고, weather / pedestrian / richer scenario event 적응은 아직 미연결
- ROS bridge / 외부 autonomous stack 연결은 지원 대상이지만, 현재 baseline 구현 범위에는 포함하지 않았다

## 다음 단계 후보
- generated practical scenario를 기준으로 NPC traffic population 연결
- destination reached / route deviation 평가 세부화
- practical 결과를 기반으로 다음 scenario difficulty 자동 조정
