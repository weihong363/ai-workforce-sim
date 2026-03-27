# CODING_RULES.md

## Core Rules

- core_engine MUST be game-agnostic
- game_modules contain all domain logic
- API must be thin (no workflow / no LLM calls)
- All LLM calls MUST go through agent_controller
- Do NOT hardcode business_sim into core_engine

---

## Separation

- agent logic ≠ workflow logic ≠ evaluation logic ≠ module logic
- NEVER mix them

---

## Style

- Python + type hints
- small functions
- clear interfaces
- no giant classes

---

## Non-Negotiable

- no direct LLM calls outside agent_controller
- no domain logic in engine
- no prompt scattered across files
