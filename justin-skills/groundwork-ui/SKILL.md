---
name: "groundwork-ui"
description: "Build or restyle any web UI, page, component, dashboard or React screen with Justin's Groundwork x0.1 design system (gw- classes, tokens, calm and intuitive UX)."
---

# Groundwork x0.1 UI

Use this skill for all front-end work: HTML pages, React or Next.js screens, dashboards, docs sites, landing pages, admin tools, and screens that agents compose at runtime.

Signature: caustic light. One warm source at the upper left shapes every surface. Foundations: color, type, space, shape, motion and light. The system is agent-ready: a component contract, a composer, a linter, delegation components and an adaptive layer.

## Locate the kit

1. Look for a `groundwork/` or `design-system/` folder in the project.
2. If none exists, copy `E:\Groundwork_x0.1\` into the project as `groundwork/`. Copy `tokens.css`, `components/`, `fonts/`, and the `assets/` you need.
3. Read `DESIGN.md` first (the whole system in one file). Then read these before you write UI code:
   - `docs/README.md`: rules, modes, psychology.
   - `docs/intuitive.md`: placement, feedback, the ship checklist.
   - `components/<Name>/README.md`: for each component you use.
   - `docs/react.md`: when the project uses React.
   - `docs/motion.md` and `recipes/`: when the page uses animation.
   - `docs/light.md`: when the page has a hero, cover, CTA, glass, onboarding or a featured card (caustic light).
   - `docs/patterns.md`: for hero, pricing, CTA, footer and nav sections (use `gw-hero`, `gw-pricing`, `gw-cta`, `gw-footer`).
   - `prompts/`: a complete prompt for the page type, if one matches. Follow it.
   - `adapters/`: when the project uses shadcn/ui, Tailwind, or components from shadcnblocks, 21st.dev, Aceternity or Magic UI.
   - `docs/generative.md`, `docs/lint.md`, `docs/delegation.md`, `docs/adaptive.md`: when an agent composes, checks, acts on, or adapts the UI (see "Agentic UI").

## Load order

```html
<link rel="stylesheet" href="groundwork/tokens.css">
<link rel="stylesheet" href="groundwork/components/bundle.css">
<!-- React 18 first, only if the project uses React -->
<script src="groundwork/components/bundle.js"></script>
```

Put `class="gw-root"` on the app root. Set modes on `<html>`:

- `data-theme`: `light`, `dark`, `contrast`, `auto`.
- `data-density`: `compact`, `comfortable`, `spacious`.
- `data-accent`: `walnut`, `olive`, `cognac`, `steel`.
- `data-motion`: `calm`, `lively`, `expressive`.
- `data-light`: `on` (default), `soft` (static, half strength, no shafts), `off`.
- `data-fidelity`: `wire` (grayscale wireframe), `mid`, or none (final).
- `data-transparency="reduce"`: solid glass.
- `data-text-scale` (1, 1.125, 1.25, 1.5, 2), `data-text-spacing` (`wide`), `data-reading-width` (`narrow`): set these through `Groundwork.prefs`, not by hand.

Let people pick a theme with `data-gw="theme-switch"` (React `ThemeSwitch`). Add `data-gw-auto-contrast` on `<html>` to follow the system contrast setting.

## Rules

- Use existing `gw-` classes and React components first. Copy markup from the component README.
- Use only token variables (`var(--ink)`, `var(--space-4)`, `var(--gw-accent)`). Do not hard-code colors, sizes or shadows.
- Write new CSS as `gw-` BEM classes that read tokens and `--gw-*` hooks.
- Give each view one primary action. Put it in the conventional place:
  - Page header: right.
  - Form: first, aligned with the fields.
  - Dialog footer: right.
- Give every icon action a visible text label. Do not use a placeholder as a label. Write button labels as verb + noun.
- Show system status:
  - Use `Freshness` for data age.
  - Use `Skeleton` for the first load only.
  - Use `Refresh` for updates: content stays, soft highlight, new-items bar.
  - Use `Toast` with Undo.
- Prefer Undo to "Are you sure". Validate fields on blur. Keep the user's input after an error.
- Make touch targets at least 44px (the primary action 48px on touch). Keep 16px between a destructive and a primary button. Prevent sideways page scroll at 360px.
- Do not use: pill buttons (except floating glass controls), colored left-border cards, emoji or dark patterns.
- Motion: set `data-motion` per container: `calm` (task screens, default), `lively` (dashboards, lists), `expressive` (landing, hero, onboarding, success). Animation libraries are welcome: Motion, GSAP, anime.js, Aceternity UI, Magic UI, motion-primitives, smoothui, Three.js. Read `docs/motion.md`. Take durations and easings from `Groundwork.motion` (`forMotion`, `forGsap`, `forAnime`). Restyle third-party components with token colors. Honor reduced motion, give loops a Pause control, and never use scroll-jacking.
- Gradients and glass: use the named gradients (`gw-bg-gradient--wash`, `--dawn`, `--walnut`, `--grove`, `--dusk`, `--mesh`, `gw-mesh`); wash is fine in calm, the rest show in lively and expressive. Liquid Glass (`gw-liquid`, React `LiquidGlass`) only for floating controls over media: one glass layer per view, controls on solid fills, never for body text or forms. Glow, beams and Aceternity or Magic UI effects stay in expressive. Token colors only, no neon.
- Light (a foundation; caustic light is the signature). Read `docs/light.md`.
  - Use one light source, at the upper left. Shadows and caustics fall to the lower right. Glass rims are lit on the top and left.
  - The system lights signature surfaces for you: hero, cover, CTA, scene, onboarding, art plates; glass casts a caustic. Add light yourself only with `gw-card--lit` (one featured card), `gw-caustic` or `gw-light` / `LightScene`. On task screens, light one featured tile at most.
  - Never light inputs, tables, list rows, code, nav bars, dialog bodies or dense text. Put text on a scrim over light, at 4.5:1.
  - Calm gets static pools. Lively adds shafts and glints. Expressive adds a slow drift. Keep one animated light layer in view. Use WebGL (`data-gw="caustic-gl"`) for one hero or landing only.
- Do not use military or tactical words in UI copy or examples.
- Write copy in short, plain sentences. Purpose over prose.
- Display font (Fraunces): use it once per page at most. Use Figtree for UI text and for numbers (tabular figures). Use JetBrains Mono only for code, keys and IDs that the user types or copies.
- Do not make a screen look like a spreadsheet:
  - Choose the collection pattern first: `List` (default), `CardGrid` (a picture identifies each item), `Feed` (activity), `Summary` (values about one record). Use `Table` only to compare, sort or select records.
  - Separate with space and soft surface tone. Rules are off by default; add `--ruled` only for long, dense data. No table header fill, no vertical lines, no card borders.
  - Show key numbers as stats in space or on tiles (`gw-stat-group--tiles`), not in a strip with dividers.
  - Write labels in sentence case. Uppercase is an opt-in (`--caps`), once per view.
  - Read `docs/composition.md` (Not a spreadsheet).

## Agentic UI

Use this when an agent builds a screen at runtime, acts for a person, or adapts the screen.

- Compose from the catalog only. Read `components/registry.json` (or `catalog.a2ui.json`, A2UI-style). Use only its types, props and slots. Do not invent components, props or raw HTML. Bind changing values with `{"$ref": "/path"}`.
- Validate before render: `Groundwork.compose.validate(spec)`, then `Groundwork.compose(spec, el, { strict: true, onAction })` (React `<Surface spec>`). Send the errors (`path`, `code`, `fix`) back to the agent. Show them to people only with `Groundwork.compose.report`. See `docs/generative.md`.
- Lint to 0 errors before a person sees the screen: `await Groundwork.lint(root)` in the page, or `node tools/gw-lint.mjs <page> --width 390`. Apply the `fix` of each error. If the linter cannot run, treat it as a failure. See `docs/lint.md`.
- Show every agent action with the delegation components: ActionPlan before a consequential change (run only after approval), PermissionPrompt for access (scope Once, For this task, Always; never Always by default), ActionReceipt with Undo after the change, AgentStatus with Pause and Stop while it works, ActivityTimeline, EvidencePanel, AutonomyLevel, RoleCard, BudgetMeter. Start from `TemplateAgentWorkspace`. See `docs/delegation.md`.
- Adapt only through `Groundwork.prefs` (text size, spacing, reading width, motion, theme, contrast). Each change shows its source and has Undo. Device settings are a floor. Ask first with `Groundwork.prefs.propose`. Use the Adjust panel in Settings. See `docs/adaptive.md`.
- Anchors never move: core navigation, the primary action, the page title, Help and Settings (`data-gw-anchor`). Users may hide, order and pin other items in `data-gw-editable` regions.
- The MCP server (`tools/mcp-groundwork/`) gives agents the catalog, tokens, rules, spec validation, rendering and lint as tools. Add it in Claude Code with `claude mcp add groundwork -- node E:/Groundwork_x0.1/tools/mcp-groundwork/server.mjs`.

## Structure first

For a new page or screen, build it first with real `gw-` components under `data-fidelity="wire"`. Fill the content inventory (user question, required content, primary action, priority, source) with `gw-wf-section`. Mark missing content with `gw-wf-gap`. Pass Gate 2 Structure in `docs/process.md`, then remove the attribute and style. Prompt: `prompts/wireframe-structure.md`.

## Imagery

Use the brand images in `assets/Imagery` and `assets/Textures`. Use `assets/Lighting` for glass and caustic light scenes; tint the two caustic masks with tokens. Keep the light at the upper left in new images. Use `assets/Icons3D` in a `.gw-art-plate` for empty states, onboarding and success moments, never as control icons. Make new graphics in Artlist with the "Groundwork x0.1" style kit. Name files with the version: `name-x0.1.webp`.

## Verify (required)

1. Render the page with Playwright at 1280px and 390px.
2. Render it in the light, dark and contrast themes.
3. Run axe-core on the page. Fix every violation.
4. Look at each screenshot. Fix overflow, clipped text, weak contrast and a missing primary action.
5. Check one lit render in light and dark: one source at the upper left, caustics to the lower right, text 4.5:1 or more over the light.
6. Run the linter: `node tools/gw-lint.mjs <page>` at 1280 and `--width 390`. Fix every error (0 errors).
7. Adaptive check: set `data-text-scale="2"` and `data-text-spacing="wide"` on `<html>`. Render at 390px. No sideways scroll, no clipped text.
8. Run the checklist in `docs/intuitive.md` and Gate 5 in `docs/process.md` before you report the work as done. If the screen reads as a spreadsheet, use List, Cards or Feed.

## Demos

Open `demos/index.html` from disk. Every component and template has a live demo with theme, density, accent, motion, fidelity, text size and spacing switches.