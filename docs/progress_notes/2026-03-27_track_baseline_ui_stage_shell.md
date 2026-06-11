# 2026-03-27 Track Baseline and UI Stage Shell

## Summary

The project now has a submission-ready baseline for the current track-driving stage.

The core loop already works inside the app:

1. select or reuse a recent evaluation result
2. generate the next OpenDRIVE map
3. optionally load the map into CARLA
4. spawn the vehicle and drive manually
5. evaluate the run and save the result JSON
6. feed that result back into the next generation step

This note records the current baseline before implementing the unfinished intermediate and practical road stages.

## What Is Stable Now

### 1. Result-driven generation loop

The application can already use a recent evaluation result as the input for the next map generation step.

Current connected path:

- result selection from the UI
- next-map generation from evaluation JSON
- optional CARLA load
- manual drive on the generated map
- evaluation save after the drive

### 2. Track-stage generator refactoring baseline

The open-course generator was refactored toward a staged structure.

Current pieces:

- shared course-stage definitions
- stage-aware course composer
- validation and layout-signature metadata
- repetition guard in auto-generation

This means the generator is no longer only a small set of repeated hard-coded layouts. It now has a clearer internal structure for future extension.

### 3. Evaluation and score usability

Evaluation is now more practical for manual driving:

- raw path metric is still kept
- practical path tracking score is also computed
- single-lane and multi-lane target modes are separated
- finish crossing can show a score overlay in the driving window

This makes the score more aligned with "the car drove the course properly" instead of requiring overly strict ideal-line matching.

### 4. Finish-line workflow baseline

The finish line is now resolved from the generated course end rather than from a fixed hand-written coordinate.

Current behavior:

- finish contract is stored in the generated manifest
- runtime resolves the actual finish on the loaded map
- finish crossing is used for evaluation completion
- finish visualization is lightweight enough for the current baseline workflow

### 5. GUI control-panel baseline

The tkinter app was upgraded from a rough control panel into a more usable stage-aware shell.

Current UI improvements:

- cleaner panel layout
- progression-stage radio buttons
- persistent active stage selection in app state
- direct XODR run/load buttons in the drive setup area
- wider result list and score badge for the selected result
- scrollable left sidebar

## Current Stage Model

The UI now exposes three stages:

- Track Driving Stage
- Intermediate Road Stage
- Practical Road Stage

Current implementation status:

- Track Driving Stage: connected
- Intermediate Road Stage: placeholder only
- Practical Road Stage: placeholder only

This is intentional. The shell is now ready for the next two stages without needing another major UI rewrite.

## Why This Matters

At this point, the project has moved past the "can we make the loop work at all?" phase.

The important change is that the app, generator, runtime, and evaluation are already connected well enough to serve as a stable baseline. That gives us room to spend the next implementation effort on new environment modes instead of repeatedly rebuilding the same track-only scaffolding.

## Next Recommended Implementation Step

The next major feature step is:

1. define the environment logic for Intermediate Road Stage
2. define the environment logic for Practical Road Stage
3. connect those stages to the existing stage-aware UI and launcher path

Recommended interpretation:

- Track Driving Stage: current open-course / track-validation workflow
- Intermediate Road Stage: longer road-like layouts with lane-oriented evaluation
- Practical Road Stage: more realistic road-driving validation environments for later autonomous-driving experiments

## Commit Intent

This note marks a good checkpoint for source control:

- the current track baseline is usable
- the UI is organized enough for demonstration
- unfinished stages are already represented in the application shell
- future work can focus on adding new stage logic instead of revisiting the same baseline cleanup
