# REPO_STRUCTURE.md

## Structure

core_engine/      # reusable engine
game_modules/     # game-specific logic
api/              # HTTP layer
workers/          # async jobs
db/               # persistence
tests/            # tests

---

## core_engine

- agents/
- workflow/
- evaluation/
- assets/
- game_loader/
- providers/

NO business logic here

---

## game_modules

- business_sim/
  - agents.py
  - tasks.py
  - rules.py
  - evaluation.py
  - assets.py

ONLY domain logic here

---

## Rule

if reusable → core_engine  
if game-specific → game_modules
