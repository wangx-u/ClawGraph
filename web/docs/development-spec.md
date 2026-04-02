# Web Dashboard Development Spec

## Goal

Build a front-end-first ClawGraph dashboard in `web/` using:

- Next.js App Router
- TypeScript
- Tailwind CSS
- Mocked product data aligned with the PRD and wireframe docs

This phase focuses on high-fidelity static UI, consistent interaction structure,
and code organization that can later be wired to real APIs.

## Source Documents

- `clawgraph/docs/design/user_dashboard_prd.zh-CN.md`
- `clawgraph/docs/design/user_dashboard_wireframes.zh-CN.md`

## Implementation Scope

### In scope

- Global dashboard shell
- Shared UI primitives
- Shared dashboard section components
- P0 routes and pages
- Selected P1 pages with mocked data
- Guided flow entry surfaces
- Responsive desktop-first layout

### Out of scope

- Real backend integration
- Authentication
- Data persistence
- Websocket/live streaming
- Drag-and-drop builders
- Full charting library integration

## Route Map

- `/`
- `/access`
- `/sessions`
- `/sessions/[sessionId]`
- `/sessions/[sessionId]/runs/[runId]/replay`
- `/supervision`
- `/curation/slices`
- `/curation/candidates`
- `/curation/cohorts/[cohortId]`
- `/datasets`
- `/datasets/[snapshotId]`
- `/evaluation`
- `/evaluation/[suiteId]`
- `/coverage`
- `/feedback`
- `/flows/[flowId]`

## Code Organization

```text
web/
  docs/
  public/
  src/
    app/
    components/
      dashboard/
      layout/
      ui/
    lib/
      mock-data.ts
      navigation.ts
      types.ts
      utils.ts
```

## Design System Rules

### Visual direction

- Use a structured, operations-heavy dashboard aesthetic.
- Avoid generic SaaS white cards on flat white backgrounds.
- Use layered surfaces, gradients, and accent glows sparingly.
- Make P0 screens feel production-grade even with mock data.

### Tokens

Define CSS variables in `globals.css` for:

- page background
- panel background
- border
- text primary / secondary / muted
- accent colors
- status colors
- shadow recipes
- radius scale

### Layout

- Desktop first with left nav + top bar + right detail rail pattern.
- Mobile keeps a simplified stacked layout with the right rail moved below.
- Page width should remain readable with a `max-width` content container.

### Typography

- Use a non-default sans stack such as `"Space Grotesk", "Avenir Next", "Segoe UI", sans-serif`.
- Use a monospace stack for ids and system metrics.
- Support three text modes:
  - headline
  - dashboard body
  - technical/meta

## Component Rules

### UI primitives

All reusable presentational primitives go under `src/components/ui`.

Examples:

- `Badge`
- `Button`
- `Card`
- `DataTable`
- `MetricCard`
- `SectionHeading`
- `SplitPanel`
- `Tabs`

### Dashboard composites

Higher-level page blocks go under `src/components/dashboard`.

Examples:

- `OverviewKpis`
- `HealthMatrix`
- `OpportunityBoard`
- `SessionQualityTable`
- `ReplayTimeline`
- `BranchTreePanel`
- `ReadinessMatrix`

### Layout components

Global shell components go under `src/components/layout`.

Examples:

- `DashboardShell`
- `SidebarNav`
- `TopBar`
- `JobTray`
- `RightRail`

## Data Strategy

- Use a central `mock-data.ts` as the single source of truth.
- Strongly type all objects in `types.ts`.
- Keep object naming aligned with ClawGraph:
  - session
  - run
  - request
  - branch
  - artifact
  - slice
  - cohort
  - dataset snapshot
  - eval suite
  - scorecard
  - feedback item

## Interaction Rules

- Each page has one primary CTA.
- Page-level filters appear directly below the page header.
- Right rail is contextual, not global-only.
- Async actions render into a persistent bottom `JobTray`.
- Links between object types should be visible and frequent.

## Accessibility

- Use semantic landmarks and headings.
- Provide visible focus states.
- Keep text contrast high.
- Do not rely on color alone for status.

## Development Rules

- Prefer server components for static page shells.
- Use client components only for tabs, local interactions, and active nav state.
- Keep mock data pure and deterministic.
- Avoid deeply nested component trees for simple content blocks.
- Keep route-level pages thin; move rendering into components.

## Verification Rules

Before closing the implementation pass:

- ensure the app compiles
- ensure route links are valid
- ensure no unused imports or obvious TS errors remain
- ensure the visual hierarchy matches the wireframe intent

