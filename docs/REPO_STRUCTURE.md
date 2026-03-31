# REPO_STRUCTURE.md

## Canonical Layout

```text
api/                    # HTTP entry + route wiring + API contracts/services
  app.py
  contracts/            # Pydantic request/response models
  routes/               # Route groups (users/tasks/runs/debug/system)
  services/             # API-layer helpers and task runner orchestration

core_engine/            # Game-agnostic engine components
game_modules/           # Game-specific modules
  business_sim/

docs/                   # Product/architecture docs
  reference/            # Deep-dive/archived design docs

scripts/                # Local setup and maintenance scripts
tests/                  # Automated tests
data/                   # Local runtime artifacts (non-source)
```

## Placement Rules

1. Reusable engine logic goes to `core_engine/`.
2. Business-specific gameplay logic goes to `game_modules/business_sim/`.
3. API endpoints belong in `api/routes/`; endpoint helpers belong in `api/services/`.
4. API schemas belong in `api/contracts/` (with compatibility exports if needed).
5. Long-form design docs go in `docs/` or `docs/reference/`, not project root.
6. Generated/debug artifacts go under `data/` (for example `data/artifacts/`), not project root.
