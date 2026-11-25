---
name: p2-process-panels
description: Contribute reusable Process Forensics panels and headless integration metadata to the shared FAB Intelligence workspace.
---

# P2 UI contribution workflow

Use this skill when changing the P2 engineer investigation experience or its shared-shell integration contract.

1. P1 owns the canonical FAB Intelligence shell and common integration contracts. Reuse the shared shell, design tokens, table components, and approved visualization libraries when they are available. Until then, provide headless P2 panel contracts and composable panels only.
2. Do not add a P2 router, global app framework, independent design-token system, shared semantics store, or second general-purpose workspace. Preserve `product.json` and the frozen shared UI manifest shape.
3. Organize the investigation panels around the engineer's job: select an abnormal wafer/lot or a suspected process/condition event; inspect chronological history; compare exposure populations; review route/rework variants; inspect supporting and contradictory evidence; drill into source provenance and uncertainty; export a reproducible evidence package.
4. Every finding shown in a panel must be a projection of a validated evidence envelope. Clearly distinguish verified observations, unverified caller context, statistical association, and proposed explanation. Do not produce causal copy or synthetic/company mode ambiguity.
5. Use labeled chronology and relationship tables as alternatives to diagrams. Expose timezone, clock uncertainty, missing data, route coverage, exact equipment scope, and query bounds. Support keyboard navigation, visible focus, accessible names, empty/error/refused states, retry/cancel, stale-result clearing, and export status.
6. Keep panel callbacks narrow and deterministic: request preflight, run an authorized analysis entrypoint, cancel a bounded operation, inspect evidence, or export. No manufacturing writes or actuation.
7. Verify panel contracts and real browser interactions at desktop and narrow widths when a browser fixture is available. Do not claim browser or accessibility qualification from static markup or a screenshot.

Adapted references: `research/golden-agentic-engineering/opencode-skills/golden-react.SKILL.md`, `golden-nicegui.SKILL.md`, `docs/ARCHITECTURE.md`, and `workflows/task-routing.json`. Golden's UI examples are synthetic, not the P1-selected production stack.
