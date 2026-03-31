# AI Workforce Sim (Playable MVP)

A playable AI workforce simulation game backend.

You act as a manager: write instructions for AI workers, run tasks, and improve prompts to earn more rewards.

Better prompts -> better scores -> better wallet outcomes.

## Core Gameplay Loop

1. Start game (`POST /game/start`)
   note: register user first via `POST /users/register`
2. Receive initial worker (`junior`)
3. Complete tutorial tasks
4. Unlock normal task board
5. Run tasks repeatedly (`POST /run-task`)
6. Spend cost every run, get reward on success
7. Read feedback, improve prompt, retry

## Project Structure

- `api/`: HTTP routes and response shaping
- `core_engine/`: game-agnostic runtime (module loading, workflow, providers, persistence)
- `game_modules/business_sim/`: business gameplay logic (tasks, progression, evaluation, rewards)
- `tests/`: unit/integration tests for the MVP loop

## 3-Minute Local Setup

1. Install dependencies:

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Configure env:

```bash
cp .env.example .env
```

3. Initialize schema + seed tasks/agents:

```bash
python scripts/bootstrap_storage.py
```

4. Start API:

```bash
python -m uvicorn api.app:app --reload
```

API base: `http://127.0.0.1:8000`

## How To Play (Minimal API Flow)

1. Start player:

```bash
curl -X POST http://127.0.0.1:8000/users/register \
  -H 'Content-Type: application/json' \
  -d '{"username":"demo_player"}'
```

2. Enter game session:

```bash
curl -X POST http://127.0.0.1:8000/game/start \
  -H 'Content-Type: application/json' \
  -d '{"user_id":"<user_id_from_register>"}'
```

3. Fetch visible tasks (tutorial first):

```bash
curl "http://127.0.0.1:8000/tasks?user_id=usr_demo_001"
```

4. Run tutorial task:

```bash
curl -X POST http://127.0.0.1:8000/run-task \
  -H 'Content-Type: application/json' \
  -d '{
    "task_id":"tsk_tutorial_1_define_the_ta_4e9617a3",
    "user_id":"usr_demo_001",
    "instructions":"Define target customer, pricing, timeline, budget, and key risk."
  }'
```

5. Fetch tasks again after progression:

```bash
curl "http://127.0.0.1:8000/tasks?user_id=usr_demo_001"
```

Tip: use `python scripts/demo_playable_flow.py` for an end-to-end local walkthrough.

## Debug / Tuning Tools

- `GET /debug/tuning`: read effective runtime tuning
- `PATCH /debug/tuning`: patch gameplay tuning parameters
- `POST /debug/benchmark-models`: compare models on one task
- `POST /debug/benchmark`: benchmark matrix runner
- `GET /debug/compare`: junior vs senior comparison
- Optional local UI: [`api/static/tuning-ui.html`](/Users/ironion/workspace/ai-workforce-sim/api/static/tuning-ui.html)

## Provider Mode

Mock mode (default for local MVP):

```env
DEFAULT_PROVIDER=mock
PROVIDER_FOR_TASK=mock
PROVIDER_FOR_EVALUATION=mock
```

Real provider mode (OpenAI-compatible):

```env
DEFAULT_PROVIDER=siliconflow
PROVIDER_FOR_TASK=siliconflow
PROVIDER_FOR_EVALUATION=siliconflow
PROVIDER_SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
PROVIDER_SILICONFLOW_API_KEY=your_api_key
```

## Known MVP Limitations

- No production auth or multi-tenant security layer
- Debug endpoints are internal/developer-oriented
- No advanced market/economy systems (no trading/PVP/hiring tree)
- Local-first workflow (not production deployment automation)

## Tests

```bash
pytest -q
```
