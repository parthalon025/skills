---
name: "agent-office-ds"
description: "Use when building, extending or connecting anything with Justin's Agent Office design system (3D office UI for agent orchestration: Hermes, Copilot Studio, custom agents)."
---

# Agent Office DS: build with it

Agent Office DS is a design system for a live 3D office that shows AI agents and agent orchestration. Bots sit in rooms, rooms on floors, floors in a building. An orchestrator plans, delegates to subagents and calls tools; people approve risky steps.

**Source of truth:** the Design System artifact https://claude.ai/artifact/Jd1VwK6q9e9PWcHMuE83EX (private to Justin). Read its files with the Artifact tool (`action: "read"`, `path: "project/<file>"`). Never web-fetch it. Never guess a token, prop, event or API name: read it.

Write all explanations and UI copy in Simplified Technical English (ASD-STE100).

## 1. Read first (in this order)

1. `project/README.md`: the system, consistency rules, principles.
2. `project/Implementation.md`: load order, mounting, office API, adapter steps, task recipes, rules, definition of done, prompt templates. This skill is a summary of it; when they differ, the file wins.
3. `project/Orchestration.md`: Hermes / Copilot Studio concept map and adapter recipes.
4. `project/Foundations.md`, `project/Content.md`, `project/Accessibility.md`.
5. `project/components/<Name>/README.md` for each component you use (props table, "consumer provides").
6. `project/components/index.d.ts`: types for props, AgentEvent, AgentCommand, OfficeApi.

## 2. Load order (do not change)

1. `tokens.css` (generated from `tokens.json`)
2. `components/bundle.css` (imports the fonts)
3. React 18 + ReactDOM 18 (React components only)
4. `components/lib/three.min.js` (three.js 0.147.0)
5. `components/lib/three-orbit-controls.js`
6. `components/bundle.js` (sets `window.AgentOffice`)

Theme: `data-theme="light" | "dark" | "sublevel"` on `<html>` or any parent.

## 3. Mount

- React: `h(AgentOffice.OfficeScene, { building | solution, adapter, theme, height, onSelect, onReady })`.
- No React: `AgentOffice.office.mount(el, { building, adapter, root: el.parentNode })` returns the office API.
- Solutions: `"hermes"`, `"copilot"`, `"microsoft"`, `"hq"`. Leave out `adapter` for the mock; pass `null` for no connection.

## 4. Connect real agents

1. `AgentOffice.adapters.create({ name, subscribe(emit), send(cmd), dispose })`.
2. In `subscribe`, map platform events to Agent Office events (status, message, request, error, usage, plan, plan.step, delegate, subagent.done, tool.call, tool.result, knowledge, skill.load, checkpoint, rollback, trigger.run, model, floor/room/bot add/remove).
3. In `send`, map commands (message, approve, decline, retry, dismiss, pause, resume, assign, delegate, rollback, cron.pause, cron.resume) to platform calls. `cmd.bots` lists the targets.
4. The scene changes ONLY from adapter events. Never fake a state change in the UI.
5. Map risky steps (dangerous tool calls, spend, publishing) to `request` events.
6. Send `tokens` and `cost` on `tool.result` when known.
7. Write the mapping as a table first, then code. Recipes are mappings, not drop-in code: check the platform's current API.

## 5. Task recipes

- Show agents: pass `building` (floors -> rooms -> bots with `role`, `shape`). Do not draw custom 3D bots.
- Add a role: before mount, set `AgentOffice.office.ROLES[id] = { label, short, icon, tasks, asks }` and `AgentOffice.office.Work[id]` to an existing workstation builder; add a `role-<id>` icon. No role colors.
- Add a solution: `AgentOffice.solutions[id] = { id, label, summary, building }`.
- Add an office type: not supported without an engine change. Say so and stop.
- Add a theme: a value for every color and shadow token plus light tokens; check with ContrastCheck.
- Add a component: tokens only, README with props table and "consumer provides", preview with every state, types in index.d.ts, changelog row.
- Change the system itself: follow the Design System artifact type's own instructions (read its SKILL.md), publish only changed files, write the index last, set lastChange.

## 6. Must rules

- Tokens for every color, size, duration and light level. No literal colors.
- Icon set for every symbol. No emoji, no text glyphs.
- Color meanings: status = state, floor = floor, type = office type, accent = action/focus, emphasis = look now (one per decision, about 10% of the screen; 60-30-10 rule).
- Every color or status dot has a word or icon next to it.
- Version marks with the x prefix (for example x1.0) on file names, titles, scene signs and the changelog until the design is a SKU.
- Respect prefers-reduced-motion; keep the HUD keyboard path complete.

## 7. Definition of done (visual inspection is required)

- Screenshots in Day, Night and Sublevel, and at 1360 px, 1100 px and 400 px. Look at every one and fix what is wrong.
- ContrastCheck passes in each theme.
- No literal colors in new CSS.
- Loading, empty, error and long-text states have previews.
- Approve, decline, chat and broadcast send commands; the scene changes only after the adapter replies.
- Keyboard reaches every control; focus is visible.
- Version mark and changelog row updated.
- Report what you checked and what you did not check.

## 8. When to ask

If a required fact is missing (the platform, the agents, the target page, the theme), ask Justin for it. Do not guess.