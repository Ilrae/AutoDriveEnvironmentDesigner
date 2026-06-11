# 2026-03-26 Staged Course Generator Refactoring Plan

## 1. Why This Refactor Is Needed

As of March 26, 2026, the AED baseline loop is working end to end:

- generate next map
- load into CARLA
- spawn vehicle
- drive
- evaluate
- save result
- use the result to generate the next map

The current bottleneck is no longer the app loop itself.
The main quality problem is the map generator.

Observed issues from repeated manual driving:

- different map ids can still feel like the same course family
- higher difficulty often feels like "longer straight + slightly different turn" instead of a clear stage jump
- top-end levels can settle into a narrow set of repeated technical layouts
- generation logic is spread across multiple files with duplicated thresholds

This means the next implementation focus should be:

1. make difficulty progression feel staged instead of numeric-only
2. make generated courses structurally more diverse
3. make the generator easier to extend without rewriting the whole pipeline

## 2. Current Generator Shape

Current flow:

1. evaluation result -> driving score
2. driving score -> next numeric level
3. next level -> course variant choice
4. variant + level -> line/arc segment list
5. segment list -> XODR + manifest

Current important modules:

- `scripts/app/auto_generation.py`
- `scripts/curriculum/difficulty_controller.py`
- `scripts/map_generator/level_generator.py`

Current limitations in structure:

- level thresholds are duplicated across modules
- "stage" exists implicitly, not as an explicit generator contract
- variant selection and segment composition are tightly coupled
- manifests describe the generated map, but not the intended stage semantics clearly enough

## 3. Refactoring Goal

The refactor goal is not to replace the current generator with a completely different system.

The goal is to evolve the current baseline into a staged procedural generator with these properties:

- one shared source of truth for stage thresholds and stage intent
- a clear separation between:
  - score/difficulty update
  - stage selection
  - variant selection
  - segment composition
  - validation and metadata
- stage progression that feels visible to a human driver
- enough diversity inside one stage that repeated runs do not feel identical

## 4. Target Architecture

The target generator should be split into the following layers.

### 4.1 Difficulty Layer

Responsibility:

- convert result quality into next numeric difficulty level

Owned by:

- `scripts/curriculum/difficulty_controller.py`

This layer should stay numeric.
It is still useful for smooth adaptation.

### 4.2 Stage Layer

Responsibility:

- convert numeric level into a human-meaningful stage

Examples:

- `foundation_flow`
- `offset_transition`
- `curvy_medium`
- `technical_hard`
- `mixed_extreme`

This layer should define:

- stage id
- stage display name
- intended driving skill
- candidate variants
- target length band
- target curve-count band
- target curvature band

Important distinction:

- `difficulty stage` = stage implied by numeric level
- `layout stage` = stage implied by the actual chosen variant family

These can diverge temporarily when recovery/diversity rules intentionally pull the layout toward an easier or different family.

### 4.3 Variant Layer

Responsibility:

- choose one layout family inside the active stage

Examples:

- `single_turn`
- `gentle_chicane`
- `offset_bend`
- `s_curve`
- `compound_turn`
- `switchback`
- `double_apex`
- `snake_run`

The variant layer should never be the only source of diversity.
It should decide the family, not the exact course.

### 4.4 Segment Composer Layer

Responsibility:

- build a concrete segment sequence from stage + variant + seed

This layer should control:

- total course length
- number of arc segments
- number of direction reversals
- recovery straight length
- maximum curvature concentration

This is the real quality bottleneck of the current generator, and the main target of the refactor.

### 4.5 Validation and Metadata Layer

Responsibility:

- check whether the generated course meets minimum rules
- persist stage metadata into the manifest

Minimum validation targets:

- spawn zone is long enough
- finish zone is stable
- total length is within stage target band
- segment count is within stage target band
- no accidental collapse into near-identical short layouts

## 5. Proposed Stage Model

The current code already behaves as if five macro stages exist.
The refactor should make that explicit.

Proposed stage set:

1. `foundation_flow`
   - intent: easy completion, stable recovery, basic turn adaptation
   - variants: `single_turn`, `gentle_chicane`

2. `offset_transition`
   - intent: learn bend offset and mild direction change
   - variants: `gentle_chicane`, `offset_bend`, `s_curve`

3. `curvy_medium`
   - intent: repeated steering with moderate commitment
   - variants: `s_curve`, `compound_turn`, `switchback`

4. `technical_hard`
   - intent: connected corners and reduced recovery space
   - variants: `compound_turn`, `switchback`, `double_apex`

5. `mixed_extreme`
   - intent: high curvature density and repeated transitions
   - variants: `switchback`, `double_apex`, `snake_run`

Important note:

- numeric `level` remains
- stage is the interpretation layer on top of level
- variant still exists
- the final map should be explained by `stage + variant + seed`, not only by one variant string

## 6. Refactoring Phases

### Phase 1. Shared Stage Metadata

Create one shared module that defines:

- variant order
- level-to-adaptive-variant mapping
- stage definitions
- stage-to-variant family mapping

Outcome:

- `auto_generation.py` and `level_generator.py` stop carrying duplicated threshold logic

### Phase 2. Manifest Enrichment

Add explicit stage metadata into generated manifests:

- difficulty stage id/index
- layout stage id/index when it differs
- stage display name
- stage intent
- candidate variants

Outcome:

- generated maps become auditable
- later analysis and reports can compare results by stage, not only by map id

### Phase 3. Segment Composer Separation

Move open-course segment composition into a dedicated builder layer.

From:

- one large function with variant branches

To:

- stage-aware composition helpers
- reusable composition utilities
- clearer per-stage targets

Outcome:

- easier to expand diversity without destabilizing the full generator

### Phase 4. Anti-Repetition Rules

Add explicit repetition controls:

- prevent same family repeating too often
- prevent near-equal total length bands repeating too often
- prevent identical curvature rhythm across consecutive maps

Outcome:

- repeated manual tests should feel less like small cosmetic mutations

### Phase 5. Baseline Validation

Use the baseline suite to verify that:

- easy tracks remain easy
- hard tracks remain technically harder
- two-lane road-like cases still evaluate correctly

Outcome:

- generator changes can be judged against stable reference cases

## 7. Non-Goals for This Refactor

This refactor does not yet target:

- intersections
- urban networks
- obstacles
- traffic systems
- full multi-road route planning

The current goal remains:

- produce better, more diverse, more stage-readable track/open-course maps first

## 8. Immediate Implementation Order

The immediate coding order after this document should be:

1. add shared stage-definition module
2. make auto-generation and level-generator consume that shared module
3. write stage metadata into manifests
4. split open-course composition into smaller helpers
5. only then start changing actual diversity rules aggressively

This order is important.
If diversity is changed first without a shared stage contract, the generator becomes harder to reason about.

## 9. Expected Outcome After This Refactor

If the refactor is successful, a manual tester should feel:

- "this is clearly a higher stage than the previous map"
- "this stage still has variety"
- "harder maps are not just longer maps"
- "the generator has a readable structure that can later extend to road-driving mode"

That is the real success criterion for this refactor.
