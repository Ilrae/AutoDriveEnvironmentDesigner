# 2026-03-24 Result-Driven Auto Generation Baseline

## 1. Goal

The project direction was clarified again on March 24, 2026:

- The user should not manually tune map geometry parameters for each run.
- The AED application should read the latest driving/evaluation result.
- The application should automatically decide the next map difficulty.
- The application should generate the next OpenDRIVE map and optionally load it into CARLA.

This note records the first working baseline for that result-driven generation flow.

## 2. Implemented Components

### 2.1 Result-driven generation pipeline

New module:

- `scripts/app/auto_generation.py`

Responsibilities:

- Read a selected evaluation JSON file or the latest file in `results/manual_sequence/`
- Convert the result into a normalized driving score
- Resolve the previous difficulty level
- Update the difficulty level using the curriculum controller
- Select the next open-course layout variant automatically
- Generate the next `.xodr` file and manifest
- Optionally load the generated map into CARLA immediately

### 2.2 Level generator extension

Updated module:

- `scripts/map_generator/level_generator.py`

Added support for:

- `open_course=True`
- `course_variant=adaptive | single_turn | s_curve | compound_turn`

This allows the application to create start-to-finish courses, not only straight roads or stadium tracks.

### 2.3 App launcher integration

Updated module:

- `scripts/app/launcher.py`

Added command:

```powershell
py -3.7 scripts\app\launcher.py generate-next-map --map-prefix aed_auto_generated
```

This command now serves as the application-facing entry point for automatic next-map generation.

### 2.4 App GUI integration

Updated module:

- `scripts/app/gui.py`

Added a new **Automatic Map Generation** section with:

- `Map prefix`
- `Generate Next Map`
- `Generate + Load Next Map`

Behavior:

- If the user selects a result JSON in the result list, that file is used.
- If no result is selected, the latest result file is used automatically.
- After successful generation, the newest generated `.xodr` file is filled into the GUI's XODR file field.

## 3. Scoring Strategy Used for Generation

The automatic generator currently converts one evaluation result into a single `driving_score` in the range `0.0 ~ 1.0`.

The score is based on:

- completion ratio
- path match score
- finish-line crossing
- offroad penalty
- collision penalty
- failure reason penalty

This score is then used as the input to the current curriculum controller.

Interpretation:

- high score -> harder next map
- low score -> easier next map

## 4. Verification

Verified commands:

```powershell
py -3.7 -m py_compile scripts\map_generator\level_generator.py scripts\app\auto_generation.py scripts\app\launcher.py scripts\app\gui.py scripts\carla_runner\run_manual_map_sequence_demo.py
```

```powershell
py -3.7 scripts\app\auto_generation.py --result-path results\manual_sequence\sequence_demo_live_case_002_20260324_162726_503707_next_map.json --map-prefix auto_gen_smoke
```

```powershell
py -3.7 scripts\app\launcher.py generate-next-map --result-path results\manual_sequence\sequence_demo_live_case_002_20260324_162726_503707_next_map.json --map-prefix auto_gen_load_smoke --load-after-generate --pythonapi-path C:\Users\user\Documents\CARLA_0.9.15\WindowsNoEditor
```

Observed outcome:

- next map was generated successfully
- manifest was written successfully
- auto-generation metadata was stored in the manifest
- generated map could be loaded into CARLA successfully

## 5. Important Limitation

The current implementation is a baseline, not the final research-grade generator.

What is already true:

- the app can now decide and generate the next map automatically from score/result

What is still open:

- richer map topology generation
- more advanced difficulty adaptation logic
- tighter integration between generated maps and the final AED UI workflow
- final user-facing application flow without temporary pygame-driven manual demo windows

## 6. Next Step

The next practical step is:

1. make the app treat this result-driven generator as the default map-generation backend
2. connect generated maps to the application's map-load / vehicle-spawn cycle more tightly
3. spend the main implementation time on improving automatic map generation quality
