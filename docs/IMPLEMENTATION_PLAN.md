# IMPLEMENTATION_PLAN.md

## Goal

Build minimal vertical slice:

run_task → workflow → agent → evaluate → asset

---

## Steps

1. Project setup
2. Module loader
3. Agent controller
4. Workflow runner (sequential)
5. Evaluation adapter
6. Asset serializer
7. Minimal business_sim module

---

## First Demo

- 1 task
- 2 agents
- 1 evaluation
- 1 asset output

---

## Constraints

- no PVP
- no complex systems
- no overengineering

---

## Priority

working system > perfect design

---

## Phase Separation

### Phase 1 (Current MVP)

Focus:
- player loop
- task execution
- wallet + cost
- agent behavior (basic)

Do NOT include:
- agent-level workers
- vector database
- hiring system
- market system

---

### Phase 2 (After MVP Validation)

Introduce:

1. async worker scaling
2. semantic retrieval (pgvector)
3. agent memory (lightweight)
4. better model routing

---

### Phase 3 (Game Expansion)

Introduce:

1. hiring / firing
2. employee lifecycle
3. market system
4. multi-user interaction
5. PvP

---

## Rule for Codex

If feature is not in Phase 1:
DO NOT implement.
