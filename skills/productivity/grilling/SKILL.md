---
name: grilling
description: Grill the user relentlessly about a plan, decision, or idea, as scenes they can answer. Use when the user wants to stress-test their thinking, or uses any 'grill' trigger phrases.
---

Interview the user relentlessly until you reach a shared understanding. Map this as a **design tree**: every decision branches into the decisions that hang off it.

Work the tree in **rounds**. The **frontier** is every decision whose prerequisites are already settled — the questions you can ask _now_ without guessing at answers you haven't heard yet. Ask the whole frontier in one round: number each question and give your recommended answer. Then wait for the user's answers before the next round.

Each question is a **scene**: named people, a moment, a thing in front of them. The user answers by saying what happens next. The title names the decision; the body is the example.

Each choice carries **three orders** of outcome, still in the scene:

1. **First order** — what happens next to the people in front of you.
2. **Second order** — who else that move hits, right after.
3. **Third order** — the new normal that move installs.

```
❓ **Q1** - **<decision, as a title>**: <scene — who, where, what's in front of them>

- **A.** <first>. Then <second>. Then <third>.
- **B.** <first>. Then <second>. Then <third>.

➡️ **A.** <why that chain, still in the scene>
```

A round is not done while any frontier question is an abstract A/B with no one in it, or while a choice stops at what happens next. Rewrite it as a scene with three orders before you send the round.

```
❓ **Q1** - **Who can cancel?**: Sam's order #4412 is paid. The warehouse has started picking. Sam taps Cancel.

- **A.** It cancels; the picker puts it back. Then that pick slot is empty mid-wave. Then today's wave runs a unit short and the next paid order waits.
- **B.** Too late — picking has started. Then Sam retries Cancel and hits the same wall. Then every paid-not-shipped change of mind becomes a support ticket.

➡️ **A.** Paid and not yet gone still cancels. The wave taking the hit is cheaper than a support queue of Sams.
```

If a `CONTEXT.md` glossary exists, names in the scene come from it, and settled entries are **taken** — not on the frontier. Code that contradicts the glossary *is* a frontier scene: the choice is keep the glossary or sharpen it, each with three orders.

Each round the user answers reshapes the tree — settled decisions push the frontier outward and unblock questions that depended on them. Recompute the frontier and ask the next round. A question whose answer depends on another question still open in this round belongs to a _later_ round, not this one.

Finding _facts_ is your job, never the user's. When a frontier question needs a fact from the environment (filesystem, tools, etc.), dispatch a sub-agent to find it — don't ask the user for anything you could look up yourself. Don't block on it: a running exploration is an unsettled prerequisite, so only the questions downstream of it wait for the sub-agent to report — ask the rest of the frontier now. The _decisions_ are the user's — put each to them as a scene and wait.

The session is done when the frontier is empty: every branch of the design tree visited, nothing left silently assumed. Do not act on it until the user confirms you have reached a shared understanding.
