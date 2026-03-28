# AI Workforce Sim

Minimal backend for an AI workforce simulation game.

## Project Overview

This repo provides a playable backend loop:

1. initialize user
2. tutorial tasks
3. unlocked task board
4. run task with agent
5. evaluate output
6. persist run + asset
7. update wallet and return feedback

## Architecture Summary

- `core_engine/`: game-agnostic engine pieces (module loading, workflow, agent controller, provider routing, persistence)
- `game_modules/business_sim/`: business-specific game logic (agents, tasks, progression, evaluation, rewards)
- `api/`: thin HTTP layer (validation + orchestration entry)

Important boundary:
- API must not directly import `game_modules.business_sim.*`
- API talks to modules through `core_engine.module_facade.ModuleFacade`

## Module Interface Contract

A game module must expose:

- `agents`
- `tasks`
- `evaluation`
- `asset_transform`
- `progression`

Loader validation is enforced in [`core_engine/module_loader.py`](/Users/ironion/workspace/ai-workforce-sim/core_engine/module_loader.py).

## Local Run

```bash
python -m uvicorn api.app:app --reload
```

Server default: `http://127.0.0.1:8000`

## Provider Configuration

Configure in `.env` (see `.env.example`):

- provider routing: `DEFAULT_PROVIDER`, `PROVIDER_FOR_TASK`, `PROVIDER_FOR_EVALUATION`
- role routing: `PROVIDER_TASK_JUNIOR`, `PROVIDER_TASK_MID`, `PROVIDER_TASK_SENIOR`, `PROVIDER_EVALUATOR`
- model routing: `MODEL_TASK_JUNIOR`, `MODEL_TASK_MID`, `MODEL_TASK_SENIOR`, `MODEL_EVALUATOR`
- fallback: `FALLBACK_PROVIDER`, `FALLBACK_MODEL`

## Mock vs Real Mode

Mock mode (recommended for tests):

```env
DEFAULT_PROVIDER=mock
PROVIDER_FOR_TASK=mock
PROVIDER_FOR_EVALUATION=mock
```

Real provider mode (OpenAI-compatible endpoint):

```env
DEFAULT_PROVIDER=siliconflow
PROVIDER_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
PROVIDER_SILICONFLOW_API_KEY=your_key
MODEL_TASK_JUNIOR=Qwen/Qwen3-8B
MODEL_TASK_SENIOR=Qwen/Qwen3-32B
MODEL_EVALUATOR=Qwen/Qwen3-14B
```

## Example API Usage

Create async run:

```bash
curl -X POST http://127.0.0.1:8000/run-task \
  -H 'Content-Type: application/json' \
  -d '{
    "task_name":"launch_coffee_subscription",
    "module_name":"business_sim",
    "instructions":"Give a 4-step launch plan with budget and risks"
  }'
```

Poll run:

```bash
curl http://127.0.0.1:8000/runs/<run_id>
```

Read asset:

```bash
curl http://127.0.0.1:8000/assets/<asset_id>
```

## Tests

```bash
pytest -q
```

Focused decoupling checks:

```bash
pytest -q tests/test_module_interface.py tests/test_api_module_decoupling.py
```
