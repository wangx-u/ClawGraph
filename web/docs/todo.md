# Web Dashboard TODO

## Phase 0: Foundation

- [x] Create Next.js + TypeScript + Tailwind app skeleton
- [x] Add project configuration files
- [x] Add global CSS tokens and base styles
- [x] Define typed mock data model
- [x] Add route metadata and left nav configuration

## Phase 1: Shared Shell

- [x] Implement `DashboardShell`
- [x] Implement top bar
- [x] Implement sidebar navigation
- [x] Implement right rail
- [x] Implement bottom job tray
- [x] Implement reusable page header and filter row

## Phase 2: Shared UI Primitives

- [x] Buttons
- [x] Badges
- [x] Cards
- [x] KPI cards
- [x] Tables
- [x] Tabs
- [ ] Split panels
- [x] Empty states
- [ ] Action list blocks

## Phase 3: P0 Pages

- [x] Overview
- [x] Access
- [x] Session Inbox
- [x] Session detail
- [x] Replay
- [x] Supervision
- [x] Curation / Slice Registry
- [x] Curation / Candidate Pool
- [x] Curation / Cohort detail
- [x] Datasets
- [x] Dataset snapshot detail

## Phase 4: P1 Pages

- [x] Evaluation
- [x] Eval suite detail
- [x] Coverage
- [x] Feedback
- [x] Guided flow pages

## Phase 5: Polish

- [ ] Add responsive adjustments
- [ ] Add hover and focus states
- [ ] Ensure all object ids are linkable
- [ ] Add placeholder charts and trend blocks
- [ ] Add route-level metadata and titles

## Phase 6: Verification

- [x] Install dependencies
- [x] Run lint
- [x] Run typecheck
- [x] Run build
- [x] Fix any issues discovered during verification

## Phase 7: UI Productization

Reference:

- `clawgraph/docs/design/dashboard_ui_productization_review.zh-CN.md`

- [x] Rework top-level navigation into a pipeline-first information architecture
- [x] Add a global stage stepper and current-stage summary to the shell
- [x] Rebuild overview into a control-tower first screen instead of a preview disclaimer first screen
- [x] Add explicit trajectory gate and dataset eligibility checklist to replay
- [x] Convert supervision into a decision-first auto-judging workspace
- [x] Convert curation candidates into a decision-first human review workspace
- [x] Reframe datasets around snapshot lineage instead of builder-only browsing
- [x] Unify training, evaluation, and handoff into one replacement workflow
- [x] Promote coverage and handoff into a launch-control surface with rollout scope and router ack
- [x] Replace placeholder tabs with real content switching
- [x] Make the right-rail visible on standard desktop widths and make the job tray collapsible
- [x] Continue demoting raw technical identifiers behind technical-detail affordances
